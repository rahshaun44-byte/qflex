#ifndef QUANTUM_FLEX_AUDIT_PROOF_HPP
#define QUANTUM_FLEX_AUDIT_PROOF_HPP

#include <string>
#include <cstdint>
#include <ctime>
#include <nlohmann/json.hpp>
#include <openssl/crypto.h>

namespace quantum_flex {

struct AuditProof {
    std::string pre_purge_hash;
    std::string k_t_ascension_hash;
    std::string hybrid_signature;
    uint64_t volume_purged_bytes{0};
    int64_t timestamp{0};

    /// Structural completeness check enforcing schema integrity
    [[nodiscard]] bool verify_proof() const noexcept {
        return !pre_purge_hash.empty() && 
               !k_t_ascension_hash.empty() && 
               !hybrid_signature.empty() && 
               volume_purged_bytes > 0 && 
               timestamp > 0;
    }

    /// Canonical JSON serialization for the Akashic Ledger
    [[nodiscard]] std::string to_canonical_json() const {
        nlohmann::ordered_json j;
        j["hybrid_signature"] = hybrid_signature;
        j["k_t_ascension_hash"] = k_t_ascension_hash;
        j["pre_purge_hash"] = pre_purge_hash;
        j["timestamp"] = timestamp;
        j["volume_purged_bytes"] = volume_purged_bytes;
        return j.dump();
    }
};

/// Hardware-level volatile memory wipe replacing Python ctypes.memset
inline void secure_zero_memory(void* ptr, std::size_t capacity) noexcept {
    if (ptr && capacity > 0) {
        OPENSSL_cleanse(ptr, capacity);
    }
}

} // namespace quantum_flex

#endif // QUANTUM_FLEX_AUDIT_PROOF_HPP
