#ifndef QUANTUM_FLEX_CRYPTO_HASHER_HPP
#define QUANTUM_FLEX_CRYPTO_HASHER_HPP

#include <string>

namespace quantum_flex::crypto {
    class Hasher {
    public:
        // Generates a SHA-256 hash using OpenSSL 3.0 EVP API
        [[nodiscard]] static auto generate_sha256(const std::string& input) -> std::string;
        
        // New: Streams a file from disk in 8KB chunks to prevent memory exhaustion
        [[nodiscard]] static auto generate_sha256_from_file(const std::string& filepath) -> std::string;
    };
} // namespace quantum_flex::crypto

#endif // QUANTUM_FLEX_CRYPTO_HASHER_HPP
