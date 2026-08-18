#ifndef QUANTUM_FLEX_GOSSIPSUB_HANDLER_HPP
#define QUANTUM_FLEX_GOSSIPSUB_HANDLER_HPP

#include "quantum_flex/replication_layer.hpp"

#include <atomic>
#include <cmath>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <shared_mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace quantum_flex::replication {

    struct PeerScore {
        double score = 1.0;
        uint64_t last_update = 0;
    };

    class GossipSubHandler {
    public:
        explicit GossipSubHandler(ReplicationLayer& repl);
        ~GossipSubHandler();
        
        GossipSubHandler(const GossipSubHandler&) = delete;
        auto operator=(const GossipSubHandler&) -> GossipSubHandler& = delete;
        GossipSubHandler(GossipSubHandler&&) = delete;
        auto operator=(GossipSubHandler&&) -> GossipSubHandler& = delete;

        void start();
        void stop();
        
        auto publish_block(const MycelialBlock& block) -> bool;
        auto validate_and_process(const std::string& msg) -> bool;

        // Serialization for Snapshotting
        void serialize_peer_scores(std::ostream& out) const;
        void deserialize_peer_scores(std::istream& in_stream);

    private:
        ReplicationLayer& repl_;
        std::map<std::string, std::vector<std::string>> mesh_peers_;  // topic -> peers
        std::unordered_map<std::string, PeerScore> peer_scores_;
        std::set<std::string> seen_msgs_;
        mutable std::shared_mutex mtx_;
        
        std::thread maintenance_thread_;
        std::atomic<bool> running_{false};

        void maintain_mesh();  // periodic graft/prune
        void forward(const std::string& msg, const std::string& topic);
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        static void send_to_peer(const std::string& peer_id, const std::string& msg);

        static void apply_decay_to_peer(PeerScore& peer_score, uint64_t now);
        [[nodiscard]] static auto get_decayed_score(const PeerScore& peer_score, uint64_t now) -> double;

        void reward_peer(const std::string& node_id, double amount);
        void penalize_peer(const std::string& node_id, double amount);
        void prune_peer(const std::string& node_id);
        [[nodiscard]] auto should_forward_to(const std::string& node_id) const -> bool;
    };

} // namespace quantum_flex::replication

#endif // QUANTUM_FLEX_GOSSIPSUB_HANDLER_HPP
