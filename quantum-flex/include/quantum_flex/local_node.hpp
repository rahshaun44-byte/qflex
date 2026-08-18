#ifndef QUANTUM_FLEX_LOCAL_NODE_HPP
#define QUANTUM_FLEX_LOCAL_NODE_HPP

#include "quantum_flex/crypto_shamir.hpp"
#include "quantum_flex/evidence_engine.hpp"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "quantum_flex/crypto_signer.hpp"
#include "quantum_flex/forensic_lockdown.hpp"
#include "quantum_flex/gossipsub_handler.hpp"
#include "quantum_flex/ledger.hpp"
#include "quantum_flex/replication_layer.hpp"
#include "quantum_flex/state_manager.hpp"

namespace quantum_flex::node {

    enum class SystemState : std::uint8_t {
        UNINITIALIZED,
        LOCKED,
        ACTIVE,
        SUSPECT,
        QUARANTINED,
        LOCKDOWN_PENDING,
        LOCKDOWN_ACTIVE
    };

    enum class QuarantineReason : std::uint8_t {
        InvalidProof,
        SecretRecoveryFailure,
        TPMFailure,
        LedgerCorruption,
        ConfigurationIntegrityFailure,
        RuntimeIntegrityFailure
    };

    // The mathematical proof that a payload existed at a specific time
    struct ZkCommitment {
        std::string telemetry_id;
        std::string salt_hex;
        std::string commitment_hash;
    };

    class LocalNode {
    public:
        // Inject command executor and policy for lockdown routines
        explicit LocalNode(security::ICommandExecutor* executor = nullptr, const security::LockdownPolicy& policy = security::LockdownPolicy{.dry_run = true});

        // Ingests raw telemetry, creates a ZK commitment, and registers it to the engine.
        // The raw payload is NEVER stored.
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] auto append_evidence(const std::string& telemetry_id, const std::string& raw_payload, const std::string& signature_hex) -> ZkCommitment;

        void set_harvester_key(const std::string& hex_pub_key);
        
        [[nodiscard]] auto replication() -> replication::ReplicationLayer& { return replication_layer_; }
        [[nodiscard]] auto replication() const -> const replication::ReplicationLayer& { return replication_layer_; }

        [[nodiscard]] auto gossipsub() -> replication::GossipSubHandler& { return gossipsub_handler_; }
        [[nodiscard]] auto gossipsub() const -> const replication::GossipSubHandler& { return gossipsub_handler_; }
        
        [[nodiscard]] auto get_state_manager() -> StateManager& { return state_manager_; }

        // Cryptographically verifies if a provided raw payload matches the stored ZK commitment
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters,readability-convert-member-functions-to-static)
        [[nodiscard]] auto verify_zk_proof(const std::string& raw_payload, const ZkCommitment& proof) const -> bool;

        // Exposes the State Root of the underlying Evidence Engine
        [[nodiscard]] auto get_node_state_root() const -> std::string;

        // Serializes the local node state to disk for OS interrupts
        void serialize_state(const std::string& filepath) const;

        // Loads the ledger state from disk and reconstructs it
        void load_state(const std::string& filepath);

        [[nodiscard]] auto get_state() const -> SystemState { return current_state_; }
        void unlock_node(const std::vector<crypto::SecretShard>& shards, uint8_t threshold = 3);
        void initialize_node(const std::vector<crypto::SecretShard>& shards, uint8_t threshold = 3);
        void quarantine_node(QuarantineReason reason);

    private:
        EvidenceEngine engine_;
        std::string state_root_;
        SystemState current_state_{SystemState::LOCKED};
        std::string suspended_time_;
        std::string suspended_sig_;
        std::string active_salt_;
        
        crypto::HybridSigner node_signer_;
        StateManager state_manager_;
        replication::ReplicationLayer replication_layer_{node_signer_};
        replication::GossipSubHandler gossipsub_handler_{replication_layer_};
        ledger::LedgerManager ledger_manager_{*this};
        
        std::unique_ptr<crypto::Ed25519Signer> harvester_pub_key_;
        
        uint64_t events_since_snapshot_{0};
        static constexpr uint64_t SNAPSHOT_INTERVAL = 1000;
        
        security::ICommandExecutor* command_executor_;
        security::LockdownPolicy lockdown_policy_;
        std::unique_ptr<security::SystemCommandExecutor> default_executor_;
        
        [[nodiscard]] static auto quarantine_reason_to_string(QuarantineReason reason) -> std::string;
    };

} // namespace quantum_flex::node

#endif // QUANTUM_FLEX_LOCAL_NODE_HPP
