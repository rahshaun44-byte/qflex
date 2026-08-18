#include <gtest/gtest.h>
#include "quantum_flex/crypto_hasher.hpp"
#include "quantum_flex/crypto_shamir.hpp"
#include "quantum_flex/crypto_signer.hpp"

TEST(CryptoSuite, ProveSHA256Determinism) {
    std::string payload = "quantum_flex_genesis";
    
    std::string hash_one = quantum_flex::crypto::Hasher::generate_sha256(payload);
    std::string hash_two = quantum_flex::crypto::Hasher::generate_sha256(payload);
    
    // The algorithm must be perfectly deterministic
    EXPECT_EQ(hash_one, hash_two);
    // A valid SHA-256 hex string must be exactly 64 characters
    EXPECT_EQ(hash_one.length(), 64); 
}

TEST(CryptoSuite, ProvesShamirSecretSharing) {
    const std::string master_secret = "QUANTUM_FLEX_ED25519_PRIVATE_KEY_SIMULATION";
    const uint8_t n = 5;
    const uint8_t k = 3;

    // 1. Fracture the secret into 5 shards
    auto shards = quantum_flex::crypto::ShamirSecretSharing::split_secret(master_secret, n, k);
    EXPECT_EQ(shards.size(), 5);

    // 2. Select shards 1, 3, and 5 (Indices 0, 2, 4)
    std::vector<quantum_flex::crypto::SecretShard> available_shards = { shards[0], shards[2], shards[4] };
    std::string recovered = quantum_flex::crypto::ShamirSecretSharing::recover_secret(available_shards, k);
    
    // 3. The math must perfectly reconstruct the exact string
    EXPECT_EQ(recovered, master_secret);

    // 4. Prove that 2 shards cannot recover the secret
    std::vector<quantum_flex::crypto::SecretShard> insufficient_shards = { shards[0], shards[4] };
    EXPECT_THROW(static_cast<void>(quantum_flex::crypto::ShamirSecretSharing::recover_secret(insufficient_shards, k)), std::runtime_error);
}

TEST(CryptoSuite, ProvesDecentralizedSignerBinding) {
    const std::string payload = "SHAMIR_AUTHORIZED_PAYLOAD";
    std::string public_key;
    std::vector<quantum_flex::crypto::SecretShard> master_shards;

    // Phase 1: Master boots, generates key, fractures it, and dies.
    {
        quantum_flex::crypto::Ed25519Signer master_signer;
        public_key = master_signer.get_public_key_hex();
        master_shards = master_signer.export_key_shards(5, 3);
    } // The Master Private Key is destroyed here when the scope closes

    // Phase 2: Distribute to nodes. We select shards 1, 4, and 5 to simulate a quorum
    std::vector<quantum_flex::crypto::SecretShard> quorum = { master_shards[0], master_shards[3], master_shards[4] };

    // Phase 3: Boot a decentralized signer using ONLY the shards
    quantum_flex::crypto::Ed25519Signer decentralized_signer(quorum, 3);
    
    // The reconstructed signer must be able to generate a valid signature
    const std::string signature = decentralized_signer.sign_payload(payload);

    // Phase 4: A trustless node verifies the dynamically signed payload using the original Public Key
    quantum_flex::crypto::Ed25519Signer verifier(public_key);
    EXPECT_TRUE(verifier.verify_payload(payload, signature));
}
