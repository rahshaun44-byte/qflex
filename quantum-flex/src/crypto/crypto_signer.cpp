#include "quantum_flex/crypto_signer.hpp"

#include "quantum_flex/crypto_shamir.hpp"

#include <openssl/crypto.h>
#include <openssl/evp.h>
// NOLINTBEGIN(misc-include-cleaner)
#include <openssl/core_names.h>
#include <openssl/pem.h>
#include <openssl/provider.h>
// NOLINTEND(misc-include-cleaner)

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <ios>
#include <openssl/bio.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace quantum_flex::crypto {

    namespace {
        // Helper: Convert raw bytes to Hex string
        [[nodiscard]] auto to_hex(const unsigned char* data, std::size_t len) -> std::string {
            std::stringstream stream;
            for (std::size_t i = 0; i < len; ++i) {
                // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-pointer-arithmetic)
                stream << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(data[i]);
            }
            return stream.str();
        }

        // Helper: Convert Hex string to raw bytes
        [[nodiscard]] auto from_hex(const std::string& hex) -> std::vector<unsigned char> {
            std::vector<unsigned char> bytes;
            bytes.reserve(hex.length() / 2);
            constexpr int HEX_BASE = 16;
            for (std::size_t i = 0; i < hex.length(); i += 2) {
                bytes.push_back(static_cast<unsigned char>(std::stoul(hex.substr(i, 2), nullptr, HEX_BASE)));
            }
            return bytes;
        }
    } // namespace

    Ed25519Signer::Ed25519Signer() {
        EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new_id(EVP_PKEY_ED25519, nullptr);
        if (ctx == nullptr) {
            throw std::runtime_error("Failed to init Ed25519 context");
        }
        EVP_PKEY_keygen_init(ctx);
        EVP_PKEY_keygen(ctx, &pkey_);
        EVP_PKEY_CTX_free(ctx);
        if (pkey_ == nullptr) {
            throw std::runtime_error("Ed25519 Keygen failed");
        }
    }

    Ed25519Signer::Ed25519Signer(const std::string& hex_public_key) {
        const std::vector<unsigned char> raw_key = from_hex(hex_public_key);
        pkey_ = EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, nullptr, raw_key.data(), raw_key.size());
        if (pkey_ == nullptr) {
            throw std::runtime_error("Failed to import Ed25519 public key");
        }
    }

    Ed25519Signer::Ed25519Signer(const std::vector<SecretShard>& shards, uint8_t threshold) {
        std::string recovered_secret = ShamirSecretSharing::recover_secret(shards, threshold);
        
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        pkey_ = EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, nullptr, reinterpret_cast<const unsigned char*>(recovered_secret.data()), recovered_secret.size());
            
        // Securely wipe the recovered string from memory instantly
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        OPENSSL_cleanse(recovered_secret.data(), recovered_secret.size());
        
        if (pkey_ == nullptr) {
            throw std::runtime_error("SECURITY VIOLATION: Failed to reconstruct Ed25519 private key from shards");
        }
    }

    Ed25519Signer::~Ed25519Signer() {
        if (pkey_ != nullptr) {
            EVP_PKEY_free(pkey_);
        }
    }

    auto Ed25519Signer::get_public_key_hex() const -> std::string {
        constexpr std::size_t ED25519_KEY_LEN = 32; // Ed25519 public keys are strictly 32 bytes
        std::size_t len = ED25519_KEY_LEN;
        std::vector<unsigned char> pub_key(len);
        if (EVP_PKEY_get_raw_public_key(pkey_, pub_key.data(), &len) != 1) {
            throw std::runtime_error("Failed to export public key");
        }
        return to_hex(pub_key.data(), len);
    }

    auto Ed25519Signer::sign_payload(const std::string& data) const -> std::string {
        EVP_MD_CTX* mdctx = EVP_MD_CTX_new();
        if (EVP_DigestSignInit(mdctx, nullptr, nullptr, nullptr, pkey_) != 1) {
            EVP_MD_CTX_free(mdctx);
            throw std::runtime_error("Sign init failed");
        }
        
        std::size_t siglen = 0;
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        EVP_DigestSign(mdctx, nullptr, &siglen, reinterpret_cast<const unsigned char*>(data.data()), data.size());
        std::vector<unsigned char> sig(siglen);
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        EVP_DigestSign(mdctx, sig.data(), &siglen, reinterpret_cast<const unsigned char*>(data.data()), data.size());
        
        EVP_MD_CTX_free(mdctx);
        return to_hex(sig.data(), siglen);
    }

    HybridSigner::HybridSigner(const std::string& ed_priv_path, const std::string& pqc_priv_path) : pqc_provider_(OSSL_PROVIDER_load(nullptr, "default")) {
        BIO* bio_ed = BIO_new_file(ed_priv_path.c_str(), "rb");
        if (bio_ed != nullptr) {
            ed_key_ = PEM_read_bio_PrivateKey(bio_ed, nullptr, nullptr, nullptr);
            BIO_free(bio_ed);
        }

        BIO* bio_pqc = BIO_new_file(pqc_priv_path.c_str(), "rb");
        if (bio_pqc != nullptr) {
            pqc_key_ = PEM_read_bio_PrivateKey(bio_pqc, nullptr, nullptr, nullptr);
            BIO_free(bio_pqc);
        }
    }

    HybridSigner::~HybridSigner() {
        if (ed_key_ != nullptr) {
            EVP_PKEY_free(ed_key_);
        }
        if (pqc_key_ != nullptr) {
            EVP_PKEY_free(pqc_key_);
        }
        if (pqc_provider_ != nullptr) {
            OSSL_PROVIDER_unload(pqc_provider_);
        }
    }

    auto HybridSigner::sign_payload(const std::string& message) -> std::string {
        const std::string ed_sig = sign_with_pkey(ed_key_, message);
        const std::string pqc_sig = sign_with_pkey(pqc_key_, message);
        return ed_sig + "|" + pqc_sig;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto HybridSigner::verify_payload(const std::string& data, const std::string& signature_hex) const -> bool {
        const size_t delim = signature_hex.find('|');
        if (delim == std::string::npos) {
            return false;
        }
        const std::string ed_sig_hex = signature_hex.substr(0, delim);
        const std::string pqc_sig_hex = signature_hex.substr(delim + 1);

        const std::vector<unsigned char> ed_sig = hex_to_bytes(ed_sig_hex);
        const std::vector<unsigned char> pqc_sig = hex_to_bytes(pqc_sig_hex);

        const bool ed_valid = verify_with_pkey(ed_key_, data, ed_sig);
        const bool pqc_valid = verify_with_pkey(pqc_key_, data, pqc_sig);
        return ed_valid && pqc_valid;
    }

    auto HybridSigner::sign_with_pkey(EVP_PKEY* pkey, const std::string& msg) -> std::string {
        if (pkey == nullptr) {
            return "";
        }
        EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new(pkey, nullptr);
        if (ctx == nullptr || EVP_PKEY_sign_init(ctx) <= 0) {
            if (ctx != nullptr) {
                EVP_PKEY_CTX_free(ctx);
            }
            return "";
        }

        size_t sig_len = 0;
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        if (EVP_PKEY_sign(ctx, nullptr, &sig_len, reinterpret_cast<const unsigned char*>(msg.data()), msg.size()) <= 0) {
            EVP_PKEY_CTX_free(ctx);
            return "";
        }

        std::vector<unsigned char> sig(sig_len);
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        if (EVP_PKEY_sign(ctx, sig.data(), &sig_len, reinterpret_cast<const unsigned char*>(msg.data()), msg.size()) <= 0) {
            EVP_PKEY_CTX_free(ctx);
            return "";
        }
        EVP_PKEY_CTX_free(ctx);
        return bytes_to_hex(sig.data(), sig_len);
    }

    auto HybridSigner::verify_with_pkey(EVP_PKEY* pkey, const std::string& msg, const std::vector<unsigned char>& sig_bytes) -> bool {
        if (pkey == nullptr || sig_bytes.empty()) {
            return false;
        }
        EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new(pkey, nullptr);
        if (ctx == nullptr || EVP_PKEY_verify_init(ctx) <= 0) {
            if (ctx != nullptr) {
                EVP_PKEY_CTX_free(ctx);
            }
            return false;
        }

        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        const int ret = EVP_PKEY_verify(ctx, sig_bytes.data(), sig_bytes.size(), reinterpret_cast<const unsigned char*>(msg.data()), msg.size());
        EVP_PKEY_CTX_free(ctx);
        return ret == 1;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters)
    auto Ed25519Signer::verify_payload(const std::string& data, const std::string& signature_hex) const -> bool {
        EVP_MD_CTX* mdctx = EVP_MD_CTX_new();
        if (EVP_DigestVerifyInit(mdctx, nullptr, nullptr, nullptr, pkey_) != 1) {
            EVP_MD_CTX_free(mdctx);
            return false;
        }
        
        const std::vector<unsigned char> sig = from_hex(signature_hex);
        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        const int result = EVP_DigestVerify(mdctx, sig.data(), sig.size(), reinterpret_cast<const unsigned char*>(data.data()), data.size());
        
        EVP_MD_CTX_free(mdctx);
        return result == 1;
    }

    auto Ed25519Signer::export_key_shards(uint8_t total_shards, uint8_t threshold) const -> std::vector<SecretShard> {
        constexpr std::size_t ED25519_KEY_LEN = 32; // Ed25519 private keys are strictly 32 bytes
        std::size_t priv_len = ED25519_KEY_LEN;
        std::vector<unsigned char> priv_key(priv_len);
        
        // Extract raw bytes from the OpenSSL context
        if (EVP_PKEY_get_raw_private_key(pkey_, priv_key.data(), &priv_len) != 1) {
            throw std::runtime_error("Failed to extract raw private key for fracturing");
        }

        // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast)
        std::string secret(reinterpret_cast<const char*>(priv_key.data()), priv_len);
        
        // Fracture the key using the Galois Field engine
        auto shards = ShamirSecretSharing::split_secret(secret, total_shards, threshold);
        
        // Zero out the volatile extraction buffers
        OPENSSL_cleanse(priv_key.data(), priv_key.size());
        OPENSSL_cleanse(secret.data(), secret.size()); // It might use a different buffer internally but we zero the string's backing buffer
        
        return shards;
    }

    auto HybridSigner::hex_to_bytes(const std::string& hex) -> std::vector<unsigned char> {
        std::vector<unsigned char> bytes;
        if (hex.length() % 2 != 0) {
            return bytes;
        }
        bytes.reserve(hex.length() / 2);
        constexpr int HEX_BASE = 16;
        for (size_t i = 0; i < hex.length(); i += 2) {
            const std::string byteString = hex.substr(i, 2);
            const auto byte = static_cast<unsigned char>(std::stoul(byteString, nullptr, HEX_BASE));
            bytes.push_back(byte);
        }
        return bytes;
    }

    auto HybridSigner::bytes_to_hex(const unsigned char* data, size_t len) -> std::string {
        std::stringstream stream;
        for (std::size_t i = 0; i < len; ++i) {
            // NOLINTNEXTLINE(cppcoreguidelines-pro-bounds-pointer-arithmetic)
            stream << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(data[i]);
        }
        return stream.str();
    }

} // namespace quantum_flex::crypto
