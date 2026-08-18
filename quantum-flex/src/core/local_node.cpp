#include "quantum_flex/local_node.hpp"

#include "quantum_flex/crypto_hasher.hpp"
#include "quantum_flex/crypto_shamir.hpp"
#include "quantum_flex/crypto_signer.hpp"

#include <openssl/rand.h>

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <ios>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <unistd.h>

#include "quantum_flex/forensic_lockdown.hpp"

namespace {
    auto environment_value(const char* name, const std::string& fallback) -> std::string {
        const char* value = std::getenv(name);
        return value != nullptr && *value != '\0' ? std::string(value) : fallback;
    }

    auto data_path(const std::string& filename) -> std::string {
        return environment_value("QF_DATA_DIR", "/home/rahshaunchambers/quantum-flex/data") + "/" + filename;
    }
}

namespace quantum_flex::node {

    LocalNode::LocalNode(security::ICommandExecutor* executor, const security::LockdownPolicy& policy)
        : node_signer_(environment_value("QF_ED_PRIVATE_KEY", data_path("ed_priv.pem")),
          environment_value("QF_PQC_PRIVATE_KEY", data_path("pqc_priv.pem"))),
          state_manager_(data_path("brie_state.db")),
          command_executor_(executor),
          lockdown_policy_(policy) {
        
        if (command_executor_ == nullptr) {
            default_executor_ = std::make_unique<security::SystemCommandExecutor>();
            command_executor_ = default_executor_.get();
        }
    }

    auto LocalNode::quarantine_reason_to_string(QuarantineReason reason) -> std::string {
        switch (reason) {
            case QuarantineReason::InvalidProof: return "InvalidProof";
            case QuarantineReason::SecretRecoveryFailure: return "SecretRecoveryFailure";
            case QuarantineReason::TPMFailure: return "TPMFailure";
            case QuarantineReason::LedgerCorruption: return "LedgerCorruption";
            case QuarantineReason::ConfigurationIntegrityFailure: return "ConfigurationIntegrityFailure";
            case QuarantineReason::RuntimeIntegrityFailure: return "RuntimeIntegrityFailure";
        }
        return "Unknown";
    }

    void LocalNode::quarantine_node(QuarantineReason reason) {
        if (current_state_ == SystemState::LOCKDOWN_ACTIVE || current_state_ == SystemState::LOCKDOWN_PENDING) {
            return; // Already locked down
        }
        
        current_state_ = SystemState::QUARANTINED;
        
        // Ensure log directory exists
        const std::string log_dir = "/var/log/quantum_flex/quarantine_events";
        // NOLINTNEXTLINE(concurrency-mt-unsafe,cert-env33-c,bugprone-command-processor)
        std::system(("mkdir -p " + log_dir).c_str());
        // NOLINTNEXTLINE(concurrency-mt-unsafe,cert-env33-c,bugprone-command-processor)
        std::system(("chmod 700 " + log_dir).c_str());

        // Generate JSON payload
        const std::string timestamp = std::to_string(std::time(nullptr));
        const std::string event_id = crypto::Hasher::generate_sha256(timestamp + quarantine_reason_to_string(reason));
        const std::string log_file = log_dir + "/event_" + event_id + ".json";
        
        std::ofstream out(log_file, std::ios::app);
        if (out.is_open()) {
            out << "{\n"
                << R"(  "timestamp": ")" << timestamp << "\",\n"
                << R"(  "node_id": "quantum_node_1",)" << "\n"
                << R"(  "reason": ")" << quarantine_reason_to_string(reason) << "\",\n"
                << R"(  "state": "QUARANTINED",)" << "\n"
                << R"(  "event_id": ")" << event_id << "\",\n"
                << R"(  "last_ledger_commit": ")" << state_root_ << "\"\n"
                << "}\n";
            out.flush();
            out.close();
        }

        // Hard disk sync
        sync();

        current_state_ = SystemState::LOCKDOWN_PENDING;
        
        security::ForensicLockdown lockdown(command_executor_, lockdown_policy_);
        lockdown.execute();
        
        current_state_ = SystemState::LOCKDOWN_ACTIVE;
        
        std::cerr << "[!] Node is fully QUARANTINED and LOCKED DOWN.\n";
        // NOLINTNEXTLINE(concurrency-mt-unsafe)
        std::exit(EXIT_FAILURE); // Halt execution entirely
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto LocalNode::append_evidence(const std::string& telemetry_id, const std::string& raw_payload, const std::string& signature_hex) -> ZkCommitment {
        if (!harvester_pub_key_) {
            throw std::runtime_error("SECURITY BREACH: Node missing harvester public key. Cannot verify telemetry.");
        }

        if (!harvester_pub_key_->verify_payload(raw_payload, signature_hex)) {
            quarantine_node(QuarantineReason::InvalidProof);
        }

        // 1. Generate 32 bytes of cryptographically secure salt
        constexpr std::size_t SALT_LEN = 32;
        std::array<unsigned char, SALT_LEN> salt_bytes{};
        if (RAND_bytes(salt_bytes.data(), static_cast<int>(salt_bytes.size())) != 1) {
            throw std::runtime_error("SECURITY VIOLATION: RNG failure during ZK salt generation");
        }

        // 2. Convert salt to hex string
        std::stringstream salt_ss;
        for (const auto& byte : salt_bytes) {
            salt_ss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(byte);
        }
        const std::string salt_hex = salt_ss.str();

        // 3. Generate the Commitment: C = H(salt || payload)
        const std::string commitment_hash = crypto::Hasher::generate_sha256(salt_hex + raw_payload);

        // 4. Register ONLY the commitment into the Evidence Engine. 
        // The raw_payload falls out of scope and is destroyed.
        engine_.register_evidence(telemetry_id, commitment_hash);
        state_root_ = engine_.get_state_root();

        // Increment event counter and possibly snapshot
        if (++events_since_snapshot_ >= SNAPSHOT_INTERVAL) {
            ledger_manager_.create_snapshot();
            ledger_manager_.compact_ledger();
            events_since_snapshot_ = 0;
        }

        return { .telemetry_id = telemetry_id, .salt_hex = salt_hex, .commitment_hash = commitment_hash };
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters,readability-convert-member-functions-to-static)
    auto LocalNode::verify_zk_proof(const std::string& raw_payload, const ZkCommitment& proof) const -> bool {
        // Reconstruct the commitment using the provided payload and the known salt
        const std::string reconstructed_hash = crypto::Hasher::generate_sha256(proof.salt_hex + raw_payload);
        return reconstructed_hash == proof.commitment_hash;
    }

    auto LocalNode::get_node_state_root() const -> std::string {
        return engine_.get_state_root();
    }

    void LocalNode::set_harvester_key(const std::string& hex_pub_key) {
        harvester_pub_key_ = std::make_unique<crypto::Ed25519Signer>(hex_pub_key);
        std::cout << "[*] Harvester Public Key imported successfully.\n";
    }

    void LocalNode::serialize_state(const std::string& filepath) const {
        if (this->current_state_ != SystemState::ACTIVE) {
            throw std::runtime_error("FATAL: Cannot serialize a locked or unverified state.");
        }

        const std::string temp_path = filepath + ".tmp";
        std::ofstream out(temp_path, std::ios::trunc);
        
        if (!out.is_open()) {
            throw std::runtime_error("FATAL: Cannot open ledger file for writing.");
        }

        // 1. Construct the exact payload string
        const std::string state_root = get_node_state_root();
        // NOLINTNEXTLINE(concurrency-mt-unsafe)
        const std::string timestamp = std::to_string(std::time(nullptr));
        
        const std::string payload = "STATE_ROOT|" + state_root + "\nTIMESTAMP|" + timestamp + "\n";
        
        // 2. Generate the Cryptographic Signature using the active salt
        const std::string signature = crypto::Hasher::generate_sha256(payload + this->active_salt_);

        // 3. Write to disk
        out << payload;
        out << "LEDGER_SIGNATURE|" << signature << "\n";
        
        out.close();

        // Atomic kernel-level swap: Overwrite the old ledger with the new one
        if (std::rename(temp_path.c_str(), filepath.c_str()) != 0) {
            throw std::runtime_error("FATAL: Atomic rename failed during serialization.");
        }
    }

    void LocalNode::load_state(const std::string& filepath) {
        std::ifstream in_stream(filepath);
        
        // If the file doesn't exist, we gracefully assume this is the first ever boot
        if (!in_stream.is_open()) {
            std::cout << "[*] No existing ledger found at " << filepath << ". Initiating Genesis State.\n";
            this->current_state_ = SystemState::UNINITIALIZED;
            return;
        }

        const bool has_snapshot = ledger_manager_.load_snapshot();

        std::string line;
        std::string loaded_root;
        std::string loaded_time;
        std::string loaded_sig;

        while (std::getline(in_stream, line)) {
            std::istringstream iss(line);
            std::string key;
            std::string value;
            
            if (std::getline(iss, key, '|') && std::getline(iss, value)) {
                if (key == "STATE_ROOT") {
                    loaded_root = value;
                } else if (key == "TIMESTAMP") {
                    loaded_time = value;
                } else if (key == "LEDGER_SIGNATURE") {
                    loaded_sig = value;
                }
            }
        }

        in_stream.close();

        // Missing critical components = tampering or corruption
        if (loaded_root.empty() || loaded_time.empty() || loaded_sig.empty()) {
            quarantine_node(QuarantineReason::LedgerCorruption);
        }

        this->state_root_ = loaded_root;
        
        if (!has_snapshot) {
            // Re-bootstrap peers if no snapshot exists
        }
        this->suspended_time_ = loaded_time;
        this->suspended_sig_ = loaded_sig;
        this->current_state_ = SystemState::LOCKED;
        
        state_manager_.sweep_boot_recovery();
        
        std::cout << "[*] Ledger suspended in memory. Engine is LOCKED. Awaiting SSS unlock.\n";
    }

    void LocalNode::unlock_node(const std::vector<crypto::SecretShard>& shards, uint8_t threshold) {
        // 1. Reconstruct the dynamic salt via GF(256)
        const std::string dynamic_salt = crypto::ShamirSecretSharing::recover_secret(shards, threshold);

        // 2. Hash the suspended payload
        const std::string payload = "STATE_ROOT|" + this->state_root_ + "\nTIMESTAMP|" + this->suspended_time_ + "\n";
        const std::string expected_sig = crypto::Hasher::generate_sha256(payload + dynamic_salt);

        // 3. HARD STOP PROTOCOL
        if (expected_sig != this->suspended_sig_) {
            quarantine_node(QuarantineReason::SecretRecoveryFailure);
        }

        // 4. Collapse Superposition
        this->active_salt_ = dynamic_salt;
        this->suspended_time_.clear();
        this->suspended_sig_.clear();
        this->current_state_ = SystemState::ACTIVE;
        
        std::cout << "[+] Node Unlocked. Superposition collapsed into ACTIVE state.\n";
    }

    void LocalNode::initialize_node(const std::vector<crypto::SecretShard>& shards, uint8_t threshold) {
        if (this->current_state_ != SystemState::UNINITIALIZED) {
            throw std::runtime_error("FATAL: Cannot initialize a node that is already initialized.");
        }

        this->active_salt_ = crypto::ShamirSecretSharing::recover_secret(shards, threshold);
        this->current_state_ = SystemState::ACTIVE;
        
        // Immediate disk anchor
        this->serialize_state(data_path("ledger.dat"));
        
        std::cout << "[+] Node Initialized. Cryptographic entropy provided by Root Authority.\n";
    }

} // namespace quantum_flex::node
