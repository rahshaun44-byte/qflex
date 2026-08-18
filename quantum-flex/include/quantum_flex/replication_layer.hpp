#ifndef QUANTUM_FLEX_REPLICATION_LAYER_HPP
#define QUANTUM_FLEX_REPLICATION_LAYER_HPP

#include "quantum_flex/crypto_signer.hpp"

#include <cstdint>
#include <map>
#include <mutex>
#include <string>
#include <vector>

namespace quantum_flex::replication {

    struct MycelialBlock {
        uint64_t sequence;
        std::string prev_hash;
        std::string merkle_root;
        uint64_t timestamp;
        std::string payload_hash;
        std::string signature;  // hex
    };

    class ReplicationLayer {
    public:
        // PQC Hybrid signer constructor
        explicit ReplicationLayer(crypto::HybridSigner& signer);
        
        auto append_block(const std::vector<std::string>& telemetry_packets) -> bool;
        auto receive_replication(const std::string& message) -> bool;  // REPLICATE|...
        [[nodiscard]] auto get_latest_block() const -> std::string;
        
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        auto enroll_peer(const std::string& node_id, const std::string& pubkey_hex, const std::string& signature) -> bool;
        
        void add_peer(const std::string& node_id, const std::string& hex_pubkey);
        [[nodiscard]] auto get_chain() const -> const std::vector<MycelialBlock>&;
        
        [[nodiscard]] static auto get_node_id() -> std::string { return "quantum_node_1"; /* TODO: Inject from LocalNode */ }
        [[nodiscard]] static auto get_current_term() -> uint64_t { return 1; /* Stub */ }

    private:
        crypto::HybridSigner& signer_;
        std::map<std::string, std::string> peer_pubkeys_;
        mutable std::mutex peer_mtx_;
        std::vector<MycelialBlock> local_chain_;
        mutable std::mutex chain_mtx_;
        std::string peers_file_ = "data/peers.dat";

        auto load_peers() -> bool;
        auto save_peers() -> bool;

        static auto compute_merkle_root(const std::vector<std::string>& packets) -> std::string;
        [[nodiscard]] auto validate_block(const MycelialBlock& block, const std::string& node_id) const -> bool;
        void gossip_block(const MycelialBlock& block) const;
    };

} // namespace quantum_flex::replication

#endif // QUANTUM_FLEX_REPLICATION_LAYER_HPP
