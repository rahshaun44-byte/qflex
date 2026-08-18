#ifndef QUANTUM_FLEX_BRIE_NODE_HPP
#define QUANTUM_FLEX_BRIE_NODE_HPP

#include <string>
#include <vector>
#include <cstdint>
#include <utility>
#include <pqxx/pqxx>
#include "quantum_flex/crypto_signer.hpp"

namespace quantum_flex::node {

class BrieNode {
public:
    explicit BrieNode(const std::string& db_conn_str, crypto::HybridSigner& signer);
    
    // Core routine: Extracts data, creates AuditProof, wipes memory, and drops partition
    std::string neurogenesis_purge(const std::string& partition_name);

private:
    std::string db_conn_str_;
    crypto::HybridSigner& signer_;

    void setup_akashic_schema(pqxx::work& txn);
    
    // Extracts raw bytes and populates volume_out
    std::vector<uint8_t> execute_h_shift_and_extract(pqxx::work& txn, const std::string& partition_name, uint64_t& volume_out);
    
    std::string get_previous_k_value(pqxx::work& txn);
    
    // Returns pair of {k_t, s_brie} (as raw bytes in std::string)
    std::pair<std::string, std::string> compile_truth(const std::vector<uint8_t>& raw_data, const std::string& prev_k);
};

} // namespace quantum_flex::node

#endif // QUANTUM_FLEX_BRIE_NODE_HPP
