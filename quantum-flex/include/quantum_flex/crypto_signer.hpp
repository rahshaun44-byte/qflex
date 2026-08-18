#ifndef QUANTUM_FLEX_CRYPTO_SIGNER_HPP
#define QUANTUM_FLEX_CRYPTO_SIGNER_HPP

#include "quantum_flex/crypto_shamir.hpp"

#include <cstdint>
#include <string>
#include <vector>

// Forward declaration to hide OpenSSL headers from the public API
extern "C" {
    // NOLINTNEXTLINE(modernize-use-using)
    typedef struct evp_pkey_st EVP_PKEY;
    // NOLINTNEXTLINE(modernize-use-using)
    typedef struct ossl_provider_st OSSL_PROVIDER;
}

namespace quantum_flex::crypto {
    class Ed25519Signer {
    public:
        // Generates a new master keypair
        Ed25519Signer();
        
        // Imports a public key for verification (decentralized nodes)
        explicit Ed25519Signer(const std::string& hex_public_key);
        
        // NEW: Instantiate a live signer dynamically from Shards
        explicit Ed25519Signer(const std::vector<SecretShard>& shards, uint8_t threshold);
        
        ~Ed25519Signer();

        // Delete copy semantics to prevent private key duplication
        Ed25519Signer(const Ed25519Signer&) = delete;
        auto operator=(const Ed25519Signer&) -> Ed25519Signer& = delete;

        // Delete move semantics for rule of 5
        Ed25519Signer(Ed25519Signer&&) noexcept = delete;
        auto operator=(Ed25519Signer&&) noexcept -> Ed25519Signer& = delete;

        [[nodiscard]] auto get_public_key_hex() const -> std::string;
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] auto sign_payload(const std::string& data) const -> std::string;
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
        [[nodiscard]] auto verify_payload(const std::string& data, const std::string& signature_hex) const -> bool;

        // NEW: Extract, fracture, and return the private key as decentralized shards
        [[nodiscard]] auto export_key_shards(uint8_t total_shards, uint8_t threshold) const -> std::vector<SecretShard>;

    private:
        EVP_PKEY* pkey_{nullptr};
    };

    class HybridSigner {
    public:
        HybridSigner(const std::string& ed_priv_path, const std::string& pqc_priv_path);
        ~HybridSigner();
        
        HybridSigner(const HybridSigner&) = delete;
        auto operator=(const HybridSigner&) -> HybridSigner& = delete;
        HybridSigner(HybridSigner&&) = delete;
        auto operator=(HybridSigner&&) -> HybridSigner& = delete;

        [[nodiscard]] auto sign_payload(const std::string& message) -> std::string;
        [[nodiscard]] auto verify_payload(const std::string& data, const std::string& signature_hex) const -> bool;

    private:
        EVP_PKEY* ed_key_ = nullptr;
        EVP_PKEY* pqc_key_ = nullptr;
        OSSL_PROVIDER* pqc_provider_ = nullptr;

        [[nodiscard]] static auto sign_with_pkey(EVP_PKEY* pkey, const std::string& msg) -> std::string;
        [[nodiscard]] static auto verify_with_pkey(EVP_PKEY* pkey, const std::string& msg, const std::vector<unsigned char>& sig_bytes) -> bool;
        [[nodiscard]] static auto bytes_to_hex(const unsigned char* data, size_t len) -> std::string;
        [[nodiscard]] static auto hex_to_bytes(const std::string& hex) -> std::vector<unsigned char>;
    };
} // namespace quantum_flex::crypto

#endif // QUANTUM_FLEX_CRYPTO_SIGNER_HPP
