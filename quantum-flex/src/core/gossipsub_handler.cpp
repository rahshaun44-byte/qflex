#include "quantum_flex/gossipsub_handler.hpp"
#include "quantum_flex/crypto_hasher.hpp"
#include "quantum_flex/replication_layer.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <iostream>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>

namespace quantum_flex::replication {

    GossipSubHandler::GossipSubHandler(ReplicationLayer& repl) : repl_(repl) {}

    GossipSubHandler::~GossipSubHandler() {
        stop();
    }

    void GossipSubHandler::start() {
        if (!running_.exchange(true)) {
            maintenance_thread_ = std::thread(&GossipSubHandler::maintain_mesh, this);
        }
    }

    void GossipSubHandler::stop() {
        if (running_.exchange(false)) {
            if (maintenance_thread_.joinable()) {
                maintenance_thread_.join();
            }
        }
    }

    auto GossipSubHandler::publish_block(const MycelialBlock& block) -> bool {
        static_cast<void>(block);
        const std::string serialized = repl_.get_latest_block(); // Approximation of serialize_block
        if (serialized.empty()) {
            return false;
        }

        const std::string msg_id = crypto::Hasher::generate_sha256(serialized);
        
        {
            const std::unique_lock<std::shared_mutex> lock(mtx_);
            if (seen_msgs_.contains(msg_id)) {
                return false;
            }
            seen_msgs_.insert(msg_id);
        }

        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        const std::string envelope = "GOSSUB|mycelial-ledger|" + msg_id + "|" +
                                     ReplicationLayer::get_node_id() + "|" + std::to_string(ReplicationLayer::get_current_term()) + "|" +
                                     serialized + "|SIGSTUB";

        forward(envelope, "mycelial-ledger");
        return true;
    }

    void GossipSubHandler::apply_decay_to_peer(PeerScore& peer_score, uint64_t now) {
        const double time_delta = static_cast<double>(now - peer_score.last_update) / 3600.0;  // hours
        if (time_delta > 0) {
            constexpr double DECAY_FACTOR = 0.85;
            peer_score.score *= std::pow(DECAY_FACTOR, time_delta);
            peer_score.score = std::max(0.0, peer_score.score);
            peer_score.last_update = now;
        }
    }

    auto GossipSubHandler::get_decayed_score(const PeerScore& peer_score, uint64_t now) -> double {
        const double time_delta = static_cast<double>(now - peer_score.last_update) / 3600.0;  // hours
        if (time_delta > 0) {
            constexpr double DECAY_FACTOR = 0.85;
            return std::max(0.0, peer_score.score * std::pow(DECAY_FACTOR, time_delta));
        }
        return peer_score.score;
    }

    void GossipSubHandler::reward_peer(const std::string& node_id, double amount) {
        const std::unique_lock<std::shared_mutex> lock(mtx_);
        const auto now = static_cast<uint64_t>(time(nullptr));
        auto& peer_score = peer_scores_[node_id];
        apply_decay_to_peer(peer_score, now);
        peer_score.score = std::min(1.0, peer_score.score + amount);
        peer_score.last_update = now;
    }

    void GossipSubHandler::penalize_peer(const std::string& node_id, double amount) {
        bool should_prune = false;
        {
            const std::unique_lock<std::shared_mutex> lock(mtx_);
            const auto now = static_cast<uint64_t>(time(nullptr));
            auto& peer_score = peer_scores_[node_id];
            apply_decay_to_peer(peer_score, now);
            peer_score.score = std::max(0.0, peer_score.score - amount);
            peer_score.last_update = now;
            
            constexpr double PRUNE_THRESHOLD = 0.3;
            if (peer_score.score < PRUNE_THRESHOLD) {
                should_prune = true;
            }
        }
        
        if (should_prune) {
            prune_peer(node_id);
        }
    }

    void GossipSubHandler::prune_peer(const std::string& node_id) {
        const std::unique_lock<std::shared_mutex> lock(mtx_);
        for (auto& [topic, peers] : mesh_peers_) {
            // NOLINTNEXTLINE(modernize-use-ranges,boost-use-ranges)
            auto iter = std::remove(peers.begin(), peers.end(), node_id);
            peers.erase(iter, peers.end());
        }
    }

    auto GossipSubHandler::should_forward_to(const std::string& node_id) const -> bool {
        const std::shared_lock<std::shared_mutex> lock(mtx_);
        auto iter = peer_scores_.find(node_id);
        if (iter == peer_scores_.end()) {
            return false;
        }
        const auto now = static_cast<uint64_t>(time(nullptr));
        const double effective_score = get_decayed_score(iter->second, now);
        constexpr double FORWARD_THRESHOLD = 0.4;
        return effective_score > FORWARD_THRESHOLD;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    void GossipSubHandler::forward(const std::string& msg, const std::string& topic) {
        const std::shared_lock<std::shared_mutex> lock(mtx_);
        const auto& peers = mesh_peers_[topic];
        
        constexpr size_t MAX_FANOUT = 8;
        const size_t fanout = std::min(MAX_FANOUT, peers.size());
        
        for (size_t i = 0; i < fanout; ++i) {
            send_to_peer(peers.at(i), msg);
        }
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    void GossipSubHandler::send_to_peer(const std::string& peer_id, const std::string& msg) {
        // Unix Domain Socket P2P routing mapping NODE_ID -> /tmp/quantum_flex_<peer_id>.sock
        const int sock = socket(AF_UNIX, SOCK_STREAM, 0);
        if (sock == -1) {
            return;
        }

        struct sockaddr_un addr{};
        addr.sun_family = AF_UNIX;
        const std::string sock_path = "/tmp/quantum_flex_" + peer_id + ".sock";
        
        // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-array-to-pointer-decay, hicpp-no-array-decay)
        strncpy(addr.sun_path, sock_path.c_str(), sizeof(addr.sun_path) - 1);

        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        if (connect(sock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) != -1) {
            // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-array-to-pointer-decay)
            const ssize_t bytes_written = write(sock, msg.c_str(), msg.length());
            static_cast<void>(bytes_written);
        }
        close(sock);
    }

    auto GossipSubHandler::validate_and_process(const std::string& msg) -> bool {
        // Parse GOSSUB|TOPIC|MSG_ID|NODE_ID|TERM|BLOCK_DATA|SIGNATURE
        if (!msg.starts_with("GOSSUB|")) {
            return false;
        }

        constexpr size_t GOSSUB_PREFIX_LEN = 7;
        const size_t pos1 = msg.find('|', GOSSUB_PREFIX_LEN);
        if (pos1 == std::string::npos) {
            return false;
        }
        
        const size_t pos2 = msg.find('|', pos1 + 1);
        if (pos2 == std::string::npos) {
            return false;
        }

        const size_t pos3 = msg.find('|', pos2 + 1);
        if (pos3 == std::string::npos) {
            return false;
        }
        
        const std::string msg_id = msg.substr(pos1 + 1, pos2 - pos1 - 1);
        const std::string node_id = msg.substr(pos2 + 1, pos3 - pos2 - 1);

        {
            const std::unique_lock<std::shared_mutex> lock(mtx_);
            if (seen_msgs_.contains(msg_id)) {
                return true; // Already processed
            }
            seen_msgs_.insert(msg_id);
        }

        // Validate sig and block here...
        // For simulation, we re-forward to continue the mesh flood
        
        // reward peer for good block
        constexpr double REWARD_AMOUNT = 0.08;
        reward_peer(node_id, REWARD_AMOUNT);
        
        forward(msg, "mycelial-ledger");
        return true;
    }

    void GossipSubHandler::maintain_mesh() {
        constexpr auto PRUNE_MS = std::chrono::milliseconds(200);
        while (running_.load()) {
            // Periodic graft/prune stub
            
            // Background full sweep decay
            {
                const std::unique_lock<std::shared_mutex> lock(mtx_);
                const auto now = static_cast<uint64_t>(time(nullptr));
                for (auto& [peer_id, peer_score] : peer_scores_) {
                    apply_decay_to_peer(peer_score, now);
                }
            }
            
            std::this_thread::sleep_for(PRUNE_MS);
        }
    }

    void GossipSubHandler::serialize_peer_scores(std::ostream& out) const {
        const std::shared_lock<std::shared_mutex> lock(mtx_);
        
        // Write map size
        const auto map_size = static_cast<uint32_t>(peer_scores_.size());
        out.write(reinterpret_cast<const char*>(&map_size), sizeof(map_size)); // NOLINT
        
        // Write each pair
        for (const auto& [node_id, peer_score] : peer_scores_) {
            const auto id_len = static_cast<uint32_t>(node_id.size());
            out.write(reinterpret_cast<const char*>(&id_len), sizeof(id_len)); // NOLINT
            out.write(node_id.data(), id_len);
            
            out.write(reinterpret_cast<const char*>(&peer_score.score), sizeof(peer_score.score)); // NOLINT
            out.write(reinterpret_cast<const char*>(&peer_score.last_update), sizeof(peer_score.last_update)); // NOLINT
        }
    }

    void GossipSubHandler::deserialize_peer_scores(std::istream& in_stream) {
        const std::unique_lock<std::shared_mutex> lock(mtx_);
        peer_scores_.clear();
        
        uint32_t map_size = 0;
        if (!in_stream.read(reinterpret_cast<char*>(&map_size), sizeof(map_size))) { // NOLINT
            return;
        }
        
        for (uint32_t i = 0; i < map_size; ++i) {
            uint32_t id_len = 0;
            if (!in_stream.read(reinterpret_cast<char*>(&id_len), sizeof(id_len))) { // NOLINT
                return;
            }
            
            std::string node_id(id_len, '\0');
            if (!in_stream.read(node_id.data(), id_len)) {
                return;
            }
            
            PeerScore peer_score;
            if (!in_stream.read(reinterpret_cast<char*>(&peer_score.score), sizeof(peer_score.score))) { // NOLINT
                return;
            }
            if (!in_stream.read(reinterpret_cast<char*>(&peer_score.last_update), sizeof(peer_score.last_update))) { // NOLINT
                return;
            }
            
            peer_scores_[node_id] = peer_score;
        }
    }

} // namespace quantum_flex::replication
