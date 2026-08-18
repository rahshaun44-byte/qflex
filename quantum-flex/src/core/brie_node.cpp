#include "quantum_flex/brie_node.hpp"
#include "quantum_flex/audit_proof.hpp"
#include <iostream>
#include <stdexcept>
#include <cstring>
#include <cstddef>
#include <endian.h>
#include <openssl/evp.h>

namespace quantum_flex::node {

namespace {
    std::string sha256_bytes(const std::string& input) {
        unsigned char hash[EVP_MAX_MD_SIZE];
        unsigned int hash_len = 0;
        EVP_MD_CTX* ctx = EVP_MD_CTX_new();
        if (!ctx) throw std::runtime_error("Failed to create EVP_MD_CTX");

        if (EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) != 1 ||
            EVP_DigestUpdate(ctx, input.data(), input.size()) != 1 ||
            EVP_DigestFinal_ex(ctx, hash, &hash_len) != 1) {
            EVP_MD_CTX_free(ctx);
            throw std::runtime_error("SHA256 computation failed");
        }
        EVP_MD_CTX_free(ctx);
        return std::string(reinterpret_cast<char*>(hash), hash_len);
    }
    
    std::string bytes_to_hex(const std::string& bytes) {
        static const char hex_chars[] = "0123456789abcdef";
        std::string hex;
        hex.reserve(bytes.size() * 2);
        for (unsigned char c : bytes) {
            hex.push_back(hex_chars[c >> 4]);
            hex.push_back(hex_chars[c & 15]);
        }
        return hex;
    }
}

BrieNode::BrieNode(const std::string& db_conn_str, crypto::HybridSigner& signer)
    : db_conn_str_(db_conn_str), signer_(signer) {}

void BrieNode::setup_akashic_schema(pqxx::work& txn) {
    txn.exec(
        "CREATE TABLE IF NOT EXISTS akashic_ledger ("
        "  pulse_id BIGSERIAL PRIMARY KEY,"
        "  k_value BYTEA NOT NULL,"
        "  brie_sig BYTEA NOT NULL,"
        "  volume_purged BIGINT NOT NULL,"
        "  audit_proof JSONB,"
        "  committed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    );
}

std::vector<uint8_t> BrieNode::execute_h_shift_and_extract(pqxx::work& txn, const std::string& partition_name, uint64_t& volume_out) {
    std::string query = "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = " + txn.quote(partition_name);
    pqxx::result cols = txn.exec(query);
    
    std::vector<std::string> math_columns;
    std::vector<std::string> struct_formats;
    
    for (const auto& row : cols) {
        std::string col_name = row[0].c_str();
        std::string data_type = row[1].c_str();
        
        if (col_name != "id" && col_name != "pulse_id") {
            if (data_type == "double precision" || data_type == "numeric") {
                math_columns.push_back(col_name);
                struct_formats.push_back("d");
            } else if (data_type == "real") {
                math_columns.push_back(col_name);
                struct_formats.push_back("f");
            } else if (data_type == "integer") {
                math_columns.push_back(col_name);
                struct_formats.push_back("i");
            } else if (data_type == "bigint") {
                math_columns.push_back(col_name);
                struct_formats.push_back("q");
            }
        }
    }
    
    if (math_columns.empty()) {
        volume_out = 0;
        return {};
    }
    
    std::string sel = "SELECT ";
    for (size_t i = 0; i < math_columns.size(); ++i) {
        sel += txn.quote_name(math_columns[i]);
        if (i < math_columns.size() - 1) sel += ", ";
    }
    sel += " FROM " + txn.quote_name(partition_name);
    
    pqxx::result data = txn.exec(sel);
    std::vector<uint8_t> raw_payload;
    
    for (const auto& row : data) {
        for (size_t i = 0; i < math_columns.size(); ++i) {
            if (row[i].is_null()) continue;
            
            std::string fmt = struct_formats[i];
            if (fmt == "d") {
                double val = row[i].as<double>();
                uint64_t v;
                std::memcpy(&v, &val, 8);
                v = htobe64(v);
                uint8_t bytes[8];
                std::memcpy(bytes, &v, 8);
                raw_payload.insert(raw_payload.end(), bytes, bytes+8);
            } else if (fmt == "f") {
                float val = row[i].as<float>();
                uint32_t v;
                std::memcpy(&v, &val, 4);
                v = htobe32(v);
                uint8_t bytes[4];
                std::memcpy(bytes, &v, 4);
                raw_payload.insert(raw_payload.end(), bytes, bytes+4);
            } else if (fmt == "i") {
                int32_t val = row[i].as<int32_t>();
                uint32_t v = htobe32(val);
                uint8_t bytes[4];
                std::memcpy(bytes, &v, 4);
                raw_payload.insert(raw_payload.end(), bytes, bytes+4);
            } else if (fmt == "q") {
                int64_t val = row[i].as<int64_t>();
                uint64_t v = htobe64(val);
                uint8_t bytes[8];
                std::memcpy(bytes, &v, 8);
                raw_payload.insert(raw_payload.end(), bytes, bytes+8);
            }
        }
    }
    
    volume_out = raw_payload.size();
    return raw_payload;
}

std::string BrieNode::get_previous_k_value(pqxx::work& txn) {
    pqxx::result res = txn.exec("SELECT k_value FROM akashic_ledger ORDER BY pulse_id DESC LIMIT 1");
    if (!res.empty()) {
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
        pqxx::binarystring bin(res[0][0]);
#pragma GCC diagnostic pop
        return std::string(reinterpret_cast<const char*>(bin.data()), bin.size());
    }
    return std::string(32, '\0');
}

std::pair<std::string, std::string> BrieNode::compile_truth(const std::vector<uint8_t>& raw_data, const std::string& prev_k) {
    std::string raw_str(reinterpret_cast<const char*>(raw_data.data()), raw_data.size());
    std::string base_hash = sha256_bytes(raw_str + prev_k);
    
    // The HybridSigner expects a message string and outputs hex signature
    std::string s_brie = signer_.sign_payload(bytes_to_hex(base_hash));
    
    std::string h_final_input = raw_str + prev_k + s_brie;
    std::string k_t = sha256_bytes(h_final_input);
    
    return {k_t, s_brie};
}

std::string BrieNode::neurogenesis_purge(const std::string& partition_name) {
    std::cout << "[Brie Node] Synchronous neurogenesis purge initiated for: " << partition_name << "\n";
    
    pqxx::connection conn(db_conn_str_);
    pqxx::work txn(conn);
    
    setup_akashic_schema(txn);
    
    pqxx::result check = txn.exec("SELECT to_regclass(" + txn.quote(partition_name) + ")");
    if (check.empty() || check[0][0].is_null()) {
        std::cout << "[Brie Node] Partition " << partition_name << " does not exist. Purge skipped.\n";
        txn.commit();
        return std::string(32, '\0');
    }
    
    uint64_t volume = 0;
    std::vector<uint8_t> raw_data = execute_h_shift_and_extract(txn, partition_name, volume);
    
    std::string raw_str(reinterpret_cast<const char*>(raw_data.data()), raw_data.size());
    std::string pre_purge_hash = bytes_to_hex(sha256_bytes(raw_str));
    
    try {
        std::string prev_k = get_previous_k_value(txn);
        auto [k_t, s_brie] = compile_truth(raw_data, prev_k);
        
        AuditProof proof;
        proof.pre_purge_hash = pre_purge_hash;
        proof.k_t_ascension_hash = bytes_to_hex(k_t);
        proof.hybrid_signature = s_brie;
        proof.timestamp = std::time(nullptr);
        proof.volume_purged_bytes = volume;
        
        if (!proof.verify_proof()) {
            throw std::runtime_error("PURGE INTEGRITY BREACH: AuditProof validation failed prior to partition drop.");
        }
        
        std::string proof_json = proof.to_canonical_json();
        
        // Escape binary strings manually for bytea insert if pqxx::binarystring fails binding
        std::string k_val_esc = txn.esc_raw(reinterpret_cast<const unsigned char*>(k_t.data()), k_t.size());
        std::string s_brie_esc = txn.esc_raw(reinterpret_cast<const unsigned char*>(s_brie.data()), s_brie.size());
        
        txn.exec(
            "INSERT INTO akashic_ledger (k_value, brie_sig, volume_purged, audit_proof) VALUES ("
            "'" + k_val_esc + "', "
            "'" + s_brie_esc + "', " +
            std::to_string(volume) + ", "
            "'" + txn.esc(proof_json) + "')"
        );
        
        txn.commit();
        
        std::cout << "[Brie Node] Purge AuditProof verified. k_t: " << proof.k_t_ascension_hash.substr(0, 16) 
                  << "... Purged " << volume << " bytes.\n";
        
        secure_zero_memory(raw_data.data(), raw_data.size());
        return k_t;
    } catch (...) {
        secure_zero_memory(raw_data.data(), raw_data.size());
        throw;
    }
}

} // namespace quantum_flex::node
