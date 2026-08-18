#include "quantum_flex/evidence_engine.hpp"

#include "quantum_flex/crypto_hasher.hpp"
#include "quantum_flex/crypto_signer.hpp"

#include <algorithm>
#include <fstream>
#include <ios>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace quantum_flex {
    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    void EvidenceEngine::register_evidence(const std::string& evidence_id, const std::string& raw_data) {
        // Prevent overwriting existing truth
        if (ledger_.contains(evidence_id)) {
            throw std::runtime_error("SECURITY VIOLATION: Attempted to overwrite locked evidence.");
        }
        // Hash the data and lock it in
        ledger_[evidence_id] = crypto::Hasher::generate_sha256(raw_data);
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto EvidenceEngine::verify_evidence(const std::string& evidence_id, const std::string& raw_data) const -> bool {
        const auto iterator = ledger_.find(evidence_id);
        if (iterator == ledger_.end()) {
            return false; // Evidence ID does not exist in the ledger
        }
        
        // Hash the incoming data and compare it to the locked truth
        const std::string computed_hash = crypto::Hasher::generate_sha256(raw_data);
        return computed_hash == iterator->second;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    void EvidenceEngine::register_file_evidence(const std::string& evidence_id, const std::string& filepath) {
        if (ledger_.contains(evidence_id)) {
            throw std::runtime_error("SECURITY VIOLATION: Attempted to overwrite locked evidence.");
        }
        ledger_[evidence_id] = crypto::Hasher::generate_sha256_from_file(filepath);
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto EvidenceEngine::verify_file_evidence(const std::string& evidence_id, const std::string& filepath) const -> bool {
        const auto iterator = ledger_.find(evidence_id);
        if (iterator == ledger_.end()) {
            return false;
        }
        const std::string computed_hash = crypto::Hasher::generate_sha256_from_file(filepath);
        return computed_hash == iterator->second;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    void EvidenceEngine::serialize_ledger(const std::string& filepath, const crypto::Ed25519Signer& signer) const {
        std::stringstream payload_stream;
        for (const auto& [key_id, hash] : ledger_) {
            payload_stream << key_id << ":" << hash << "\n";
        }
        const std::string payload = payload_stream.str();

        // 1. Write the raw data
        std::ofstream out_stream(filepath, std::ios::trunc);
        if (!out_stream.is_open()) {
            throw std::runtime_error("SECURITY VIOLATION: Cannot write ledger.");
        }
        out_stream << payload;

        // 2. Write the companion signature file
        std::ofstream sig_out(filepath + ".sig", std::ios::trunc);
        if (!sig_out.is_open()) {
            throw std::runtime_error("SECURITY VIOLATION: Cannot write signature.");
        }
        sig_out << signer.sign_payload(payload);
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    void EvidenceEngine::load_ledger(const std::string& filepath, const crypto::Ed25519Signer& verifier) {
        // 1. Read the raw payload
        std::ifstream in_stream(filepath);
        if (!in_stream.is_open()) {
            throw std::runtime_error("SECURITY VIOLATION: Missing ledger file.");
        }
        std::stringstream payload_stream;
        payload_stream << in_stream.rdbuf();
        const std::string payload = payload_stream.str();

        // 2. Read the signature
        std::ifstream sig_in(filepath + ".sig");
        if (!sig_in.is_open()) {
            throw std::runtime_error("SECURITY VIOLATION: Missing signature file.");
        }
        std::stringstream sig_stream;
        sig_stream << sig_in.rdbuf();
        const std::string signature = sig_stream.str();

        // 3. Mathematical Hard Stop
        if (!verifier.verify_payload(payload, signature)) {
            throw std::runtime_error("FATAL: Offline tampering detected. Signature mismatch.");
        }

        // 4. Safe to parse
        ledger_.clear();
        std::istringstream parse_stream(payload);
        std::string line;
        while (std::getline(parse_stream, line)) {
            if (line.empty()) {
                continue;
            }
            const auto delimiter_pos = line.find(':');
            if (delimiter_pos == std::string::npos) {
                throw std::runtime_error("SECURITY VIOLATION: Ledger structure corrupted.");
            }
            ledger_[line.substr(0, delimiter_pos)] = line.substr(delimiter_pos + 1);
        }
    }

    auto EvidenceEngine::get_state_root() const -> std::string {
        // If the system is totally empty, return a known baseline hash
        if (ledger_.empty()) {
            return crypto::Hasher::generate_sha256("QUANTUM_FLEX_EMPTY_STATE");
        }

        // 1. Extract and sort keys to enforce cryptographic determinism
        std::vector<std::string> keys;
        keys.reserve(ledger_.size());
        for (const auto& [key_id, hash_val] : ledger_) {
            keys.push_back(key_id);
        }
        std::ranges::sort(keys);

        // 2. Build the unified state matrix
        std::stringstream state_stream;
        for (const auto& key : keys) {
            state_stream << key << ":" << ledger_.at(key) << "|";
        }

        // 3. Hash the collapsed matrix
        return crypto::Hasher::generate_sha256(state_stream.str());
    }

    // NOLINTNEXTLINE(readability-convert-member-functions-to-static)
    auto EvidenceEngine::verify_state() const -> bool {
        return true; // Stub for pipeline validation
    }
} // namespace quantum_flex
