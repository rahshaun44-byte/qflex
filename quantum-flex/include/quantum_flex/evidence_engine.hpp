#ifndef QUANTUM_FLEX_EVIDENCE_ENGINE_HPP
#define QUANTUM_FLEX_EVIDENCE_ENGINE_HPP

#include "quantum_flex/crypto_signer.hpp"

#include <string>
#include <unordered_map>

namespace quantum_flex {
    class EvidenceEngine {
    public:
        // Hashes the raw data and permanently locks it into the ledger
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        void register_evidence(const std::string& evidence_id, const std::string& raw_data);

        // Re-hashes incoming data and compares it against the locked ledger record
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] auto verify_evidence(const std::string& evidence_id, const std::string& raw_data) const -> bool;

        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        void register_file_evidence(const std::string& evidence_id, const std::string& filepath);

        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] auto verify_file_evidence(const std::string& evidence_id, const std::string& filepath) const -> bool;

        // Dumps the ledger and signs the file output
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        void serialize_ledger(const std::string& filepath, const crypto::Ed25519Signer& signer) const;

        // Verifies the signature before allowing the file to be loaded into memory
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        void load_ledger(const std::string& filepath, const crypto::Ed25519Signer& verifier);

        // Collapses the entire ledger state into a single, deterministic SHA-256 hash.
        // Proves system equilibrium by detecting any omitted or injected data points.
        [[nodiscard]] auto get_state_root() const -> std::string;

        // Baseline method to prove linkage
        // NOLINTNEXTLINE(readability-convert-member-functions-to-static)
        [[nodiscard]] auto verify_state() const -> bool;

    private:
        std::unordered_map<std::string, std::string> ledger_;
    };
} // namespace quantum_flex

#endif // QUANTUM_FLEX_EVIDENCE_ENGINE_HPP
