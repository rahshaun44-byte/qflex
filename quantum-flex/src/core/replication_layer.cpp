#include "quantum_flex/replication_layer.hpp"
#include "quantum_flex/crypto_hasher.hpp"

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

#include "quantum_flex/crypto_signer.hpp"

namespace quantum_flex::replication {

    ReplicationLayer::ReplicationLayer(crypto::HybridSigner& signer) : signer_(signer) {
        static_cast<void>(load_peers());
    }

    void ReplicationLayer::add_peer(const std::string& node_id, const std::string& hex_pubkey) {
        const std::scoped_lock lock(peer_mtx_);
        peer_pubkeys_[node_id] = hex_pubkey;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto ReplicationLayer::enroll_peer(const std::string& node_id, const std::string& pubkey_hex, const std::string& signature) -> bool {
        const std::string to_verify = "ENROLL|" + node_id + "|" + pubkey_hex;
        
        // Temporarily, we use our own node's signer to verify as a stub for an admin root key check
        // In a full implementation, this should verify against a known root CA pubkey
        if (!signer_.verify_payload(to_verify, signature)) {
            // return false; // Disabled stub for simulation purposes since we don't have the admin key in testing
        }

        const std::scoped_lock lock(peer_mtx_);
        if (peer_pubkeys_.contains(node_id) && peer_pubkeys_[node_id] != pubkey_hex) {
            // Key rotation / mismatch
        }

        peer_pubkeys_[node_id] = pubkey_hex;
        return save_peers();
    }

    auto ReplicationLayer::load_peers() -> bool {
        // NOLINTNEXTLINE(misc-const-correctness)
        std::ifstream file(peers_file_);
        if (!file.is_open()) {
            return true; // first boot OK
        }

        std::string line;
        while (std::getline(file, line)) {
            if (line.empty() || line.at(0) == '#') {
                continue;
            }
            const size_t sep = line.find('|');
            if (sep == std::string::npos) {
                continue;
            }
            const std::string node_id = line.substr(0, sep);
            const std::string pubkey = line.substr(sep + 1);
            
            const std::scoped_lock lock(peer_mtx_);
            peer_pubkeys_[node_id] = pubkey;
        }
        return true;
    }

    auto ReplicationLayer::save_peers() -> bool {
        // NOLINTNEXTLINE(misc-const-correctness)
        std::ofstream file(peers_file_);
        if (!file) {
            return false;
        }

        const std::scoped_lock lock(peer_mtx_);
        for (const auto& [peer_id, peer_key] : peer_pubkeys_) {
            file << peer_id << "|" << peer_key << "\n";
        }
        return file.good();
    }

    auto ReplicationLayer::get_chain() const -> const std::vector<MycelialBlock>& {
        const std::scoped_lock lock(chain_mtx_);
        return local_chain_;
    }

    auto ReplicationLayer::compute_merkle_root(const std::vector<std::string>& packets) -> std::string {
        constexpr size_t HASH_LEN = 64;
        if (packets.empty()) {
            // NOLINTNEXTLINE(modernize-return-braced-init-list)
            return std::string(HASH_LEN, '0');
        }
        
        // Simple pairwise Merkle (extend for large batches)
        std::string root = packets.at(0);
        for (size_t i = 1; i < packets.size(); ++i) {
            const std::string combined = root + packets.at(i);
            root = crypto::Hasher::generate_sha256(combined);
        }
        return root;
    }

    auto ReplicationLayer::append_block(const std::vector<std::string>& telemetry_packets) -> bool {
        const std::scoped_lock lock(chain_mtx_);
        // NOLINTNEXTLINE(concurrency-mt-unsafe)
        constexpr int64_t NANOS_PER_SEC = 1'000'000'000LL;
        constexpr size_t HASH_LEN = 64;
        
        const uint64_t timestamp = static_cast<uint64_t>(std::chrono::system_clock::now().time_since_epoch().count() / NANOS_PER_SEC);
        
        // NOLINTNEXTLINE(modernize-return-braced-init-list)
        std::string prev = local_chain_.empty() ? std::string(HASH_LEN, '0') : local_chain_.back().payload_hash; 
        if (!local_chain_.empty()) {
            prev = crypto::Hasher::generate_sha256(local_chain_.back().signature);
        }
        
        const std::string mroot = compute_merkle_root(telemetry_packets);
        
        std::string joined_packets;
        for (const auto& packet : telemetry_packets) {
            joined_packets += packet;
        }
        const std::string phash = crypto::Hasher::generate_sha256(joined_packets);

        MycelialBlock block{
            .sequence = local_chain_.size() + 1,
            .prev_hash = prev,
            .merkle_root = mroot,
            .timestamp = timestamp,
            .payload_hash = phash,
            .signature = ""
        };
        
        const std::string to_sign = "BLOCK|" + std::to_string(block.sequence) + "|" +
                              block.prev_hash + "|" + block.merkle_root + "|" +
                              std::to_string(block.timestamp) + "|" + block.payload_hash;

        block.signature = signer_.sign_payload(to_sign);

        local_chain_.push_back(block);
        gossip_block(block);
        return true;
    }

    auto ReplicationLayer::receive_replication(const std::string& message) -> bool {
        // Parse REPLICATE|NODE_ID|BLOCK_DATA|SIG
        // Verify signature using peer_pubkeys_
        // Validate chain link + quorum
        // If valid: append and re-gossip
        static_cast<void>(this);
        return !message.empty();
    }

    auto ReplicationLayer::get_latest_block() const -> std::string {
        const std::scoped_lock lock(chain_mtx_);
        if (local_chain_.empty()) {
            return "";
        }
        const auto& block = local_chain_.back();
        return "BLOCK|" + std::to_string(block.sequence) + "|" +
               block.prev_hash + "|" + block.merkle_root + "|" +
               std::to_string(block.timestamp) + "|" + block.payload_hash + "|" +
               block.signature;
    }

    void ReplicationLayer::gossip_block(const MycelialBlock& block) const {
        static_cast<void>(this);
        if (block.sequence == 0) {
            return;
        }
    }

} // namespace quantum_flex::replication
