#ifndef QUANTUM_FLEX_CRYPTO_SHAMIR_HPP
#define QUANTUM_FLEX_CRYPTO_SHAMIR_HPP

#include <cstdint>
#include <string>
#include <vector>

namespace quantum_flex::crypto {

    struct SecretShard {
        uint8_t id{0};          // The 'x' coordinate (shard number)
        std::string payload;    // The 'y' values (fragmented data)
    };

    class ShamirSecretSharing {
    public:
        // Fragments a master secret into 'n' shards, requiring 'k' to reconstruct
        [[nodiscard]] static auto split_secret(const std::string& secret, uint8_t total_shards, uint8_t threshold) -> std::vector<SecretShard>;

        // Reconstructs the master secret from exactly 'k' shards via Lagrange Interpolation
        [[nodiscard]] static auto recover_secret(const std::vector<SecretShard>& shards, uint8_t threshold) -> std::string;
        
    private:
        // GF(256) Core Operations using Rijndael's Polynomial (0x11B)
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] static auto gf_add(uint8_t val_a, uint8_t val_b) -> uint8_t;
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] static auto gf_mul(uint8_t val_a, uint8_t val_b) -> uint8_t;
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] static auto gf_pow(uint8_t val_a, uint8_t power) -> uint8_t;
        [[nodiscard]] static auto gf_inv(uint8_t val_a) -> uint8_t;
    };

} // namespace quantum_flex::crypto

#endif // QUANTUM_FLEX_CRYPTO_SHAMIR_HPP
