#ifndef QUANTUM_FLEX_ATTESTATION_CONTEXT_HPP
#define QUANTUM_FLEX_ATTESTATION_CONTEXT_HPP

#include <string>
#include <cstdint>

namespace quantum_flex {

struct AttestationContext {
    uint32_t schema_version{1};
    uint32_t protocol_version{2};
    std::string partition_id;
    std::string node_id;
    std::string pre_purge_hash;
    std::string payload_hash;
    std::string shred_proof_hash;
    uint64_t monotonic_counter{0};
    int64_t timestamp{0};

    [[nodiscard]] std::string compute_context_hash() const;
};

} // namespace quantum_flex

#endif // QUANTUM_FLEX_ATTESTATION_CONTEXT_HPP
