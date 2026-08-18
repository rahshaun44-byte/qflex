#include "quantum_flex/crypto_shamir.hpp"

#include <openssl/rand.h>

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace quantum_flex::crypto {

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto ShamirSecretSharing::gf_add(uint8_t val_a, uint8_t val_b) -> uint8_t {
        return val_a ^ val_b; // In GF(2^n), addition is exactly equivalent to XOR
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto ShamirSecretSharing::gf_mul(uint8_t val_a, uint8_t val_b) -> uint8_t {
        uint8_t product = 0;
        constexpr int BITS_PER_BYTE = 8;
        constexpr uint8_t RIJNDAEL_POLY = 0x1B;
        constexpr uint8_t HI_BIT = 0x80;
        
        for (int i = 0; i < BITS_PER_BYTE; ++i) {
            if ((val_b & 1U) != 0U) {
                product ^= val_a;
            }
            const uint8_t hi_bit_set = (val_a & HI_BIT);
            val_a = static_cast<uint8_t>(val_a << 1U);
            if (hi_bit_set != 0U) {
                val_a ^= RIJNDAEL_POLY;
            }
            val_b = static_cast<uint8_t>(val_b >> 1U);
        }
        return product;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto ShamirSecretSharing::gf_pow(uint8_t val_a, uint8_t power) -> uint8_t {
        uint8_t res = 1;
        for (uint8_t i = 0; i < power; ++i) {
            // NOLINTNEXTLINE(readability-suspicious-call-argument)
            res = gf_mul(res, val_a);
        }
        return res;
    }

    auto ShamirSecretSharing::gf_inv(uint8_t val_a) -> uint8_t {
        if (val_a == 0) {
            throw std::runtime_error("FATAL: GF(256) division by zero");
        }
        // In GF(256), val_a^(255) = 1, therefore val_a^(-1) = val_a^(254)
        constexpr uint8_t INVERSE_POWER = 254;
        return gf_pow(val_a, INVERSE_POWER);
    }

    auto ShamirSecretSharing::split_secret(const std::string& secret, uint8_t total_shards, uint8_t threshold) -> std::vector<SecretShard> {
        if (threshold > total_shards || threshold < 2) {
            throw std::runtime_error("Invalid threshold parameters for SSS");
        }

        std::vector<SecretShard> shards(total_shards);
        for (uint8_t i = 0; i < total_shards; ++i) {
            shards.at(i).id = i + 1; // x-coordinates: 1 to total_shards
            shards.at(i).payload.resize(secret.length(), '\0');
        }

        // For each byte in the secret, create a unique polynomial of degree threshold-1
        for (std::size_t byte_idx = 0; byte_idx < secret.length(); ++byte_idx) {
            const auto secret_byte = static_cast<uint8_t>(secret.at(byte_idx));

            // Generate cryptographically secure random coefficients
            std::vector<unsigned char> coeffs(threshold - 1);
            if (RAND_bytes(coeffs.data(), static_cast<int>(coeffs.size())) != 1) {
                throw std::runtime_error("Cryptographic RNG failure during coefficient generation");
            }

            // Evaluate the polynomial for each shard (x = 1 to total_shards)
            for (uint8_t x_val = 1; x_val <= total_shards; ++x_val) {
                uint8_t y_val = secret_byte; // y-intercept is the secret
                uint8_t x_pow = x_val;

                for (uint8_t j = 0; j < threshold - 1; ++j) {
                    y_val = gf_add(y_val, gf_mul(coeffs.at(j), x_pow));
                    x_pow = gf_mul(x_pow, x_val);
                }
                shards.at(x_val - 1).payload.at(byte_idx) = static_cast<char>(y_val);
            }
        }
        return shards;
    }

    auto ShamirSecretSharing::recover_secret(const std::vector<SecretShard>& shards, uint8_t threshold) -> std::string {
        if (shards.size() < threshold) {
            throw std::runtime_error("Insufficient shards to recover the master secret");
        }

        const std::size_t secret_length = shards.at(0).payload.length();
        std::string recovered_secret(secret_length, '\0');

        // Reconstruct byte-by-byte using Lagrange Interpolation
        for (std::size_t byte_idx = 0; byte_idx < secret_length; ++byte_idx) {
            uint8_t secret_byte = 0;

            for (uint8_t i = 0; i < threshold; ++i) {
                const uint8_t x_i = shards.at(i).id;
                const auto y_i = static_cast<uint8_t>(shards.at(i).payload.at(byte_idx));

                uint8_t lagrange_basis = 1;
                for (uint8_t j = 0; j < threshold; ++j) {
                    if (i == j) {
                        continue;
                    }
                    const uint8_t x_j = shards.at(j).id;
                    
                    // basis = basis * (x_j / (x_j - x_i)) in GF(256)
                    const uint8_t numerator = x_j;
                    const uint8_t denominator = gf_add(x_i, x_j); // subtraction is addition
                    const uint8_t term = gf_mul(numerator, gf_inv(denominator));
                    
                    lagrange_basis = gf_mul(lagrange_basis, term);
                }
                secret_byte = gf_add(secret_byte, gf_mul(y_i, lagrange_basis));
            }
            recovered_secret.at(byte_idx) = static_cast<char>(secret_byte);
        }
        return recovered_secret;
    }

} // namespace quantum_flex::crypto
