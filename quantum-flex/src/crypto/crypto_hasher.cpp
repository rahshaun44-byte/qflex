#include "quantum_flex/crypto_hasher.hpp"

#include <openssl/evp.h>

#include <array>
#include <cstddef>
#include <fstream>
#include <iomanip>
#include <ios>
#include <sstream>
#include <stdexcept>
#include <string>

namespace quantum_flex::crypto {
    auto Hasher::generate_sha256(const std::string& input) -> std::string {
        EVP_MD_CTX* context = EVP_MD_CTX_new();
        if (context == nullptr) {
            throw std::runtime_error("Failed to initialize EVP_MD_CTX");
        }

        if (EVP_DigestInit_ex(context, EVP_sha256(), nullptr) != 1) {
            EVP_MD_CTX_free(context);
            throw std::runtime_error("Failed to initialize SHA-256 digest");
        }

        if (EVP_DigestUpdate(context, input.c_str(), input.length()) != 1) {
            EVP_MD_CTX_free(context);
            throw std::runtime_error("Failed to update digest");
        }

        std::array<unsigned char, EVP_MAX_MD_SIZE> hash{};
        unsigned int lengthOfHash = 0;

        if (EVP_DigestFinal_ex(context, hash.data(), &lengthOfHash) != 1) {
            EVP_MD_CTX_free(context);
            throw std::runtime_error("Failed to finalize digest");
        }

        EVP_MD_CTX_free(context);

        std::stringstream hash_stream;
        for (unsigned int i = 0; i < lengthOfHash; ++i) {
            hash_stream << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(hash.at(i));
        }
        return hash_stream.str();
    }

    auto Hasher::generate_sha256_from_file(const std::string& filepath) -> std::string {
        std::ifstream file(filepath, std::ios::binary);
        if (!file.is_open()) {
            throw std::runtime_error("SECURITY VIOLATION: Cannot open file target for hashing.");
        }

        EVP_MD_CTX* context = EVP_MD_CTX_new();
        if (context == nullptr) {
            throw std::runtime_error("Failed to initialize EVP_MD_CTX");
        }

        if (EVP_DigestInit_ex(context, EVP_sha256(), nullptr) != 1) {
            EVP_MD_CTX_free(context);
            throw std::runtime_error("Failed to initialize SHA-256 digest");
        }

        // Stream the file in 8KB chunks
        constexpr std::size_t CHUNK_SIZE = 8192;
        std::array<char, CHUNK_SIZE> buffer{};
        while (file) {
            file.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
            const auto bytes_read = file.gcount();
            if (bytes_read > 0) {
                if (EVP_DigestUpdate(context, buffer.data(), static_cast<std::size_t>(bytes_read)) != 1) {
                    EVP_MD_CTX_free(context);
                    throw std::runtime_error("Failed to update digest from file stream");
                }
            }
        }

        std::array<unsigned char, EVP_MAX_MD_SIZE> hash{};
        unsigned int lengthOfHash = 0;

        if (EVP_DigestFinal_ex(context, hash.data(), &lengthOfHash) != 1) {
            EVP_MD_CTX_free(context);
            throw std::runtime_error("Failed to finalize file digest");
        }

        EVP_MD_CTX_free(context);

        std::stringstream hash_stream;
        for (unsigned int i = 0; i < lengthOfHash; ++i) {
            hash_stream << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(hash.at(i));
        }
        return hash_stream.str();
    }
} // namespace quantum_flex::crypto
