#ifndef QUANTUM_FLEX_STATE_MANAGER_HPP
#define QUANTUM_FLEX_STATE_MANAGER_HPP

#include <string>
#include <vector>
#include <memory>
#include <optional>
#include <cstdint>
#include "quantum_flex/state.hpp"
#include "quantum_flex/attestation_context.hpp"
#include "quantum_flex/audit_proof.hpp"
#include "sqlite3.h"

#include <pqxx/pqxx>
#include <thread>
#include <atomic>

namespace quantum_flex {

class StateManager {
public:
    explicit StateManager(const std::string& db_path = "brie_state.db");
    ~StateManager();

    StateManager(const StateManager&) = delete;
    StateManager& operator=(const StateManager&) = delete;

    void transition(const std::string& partition_id, BrieState new_state, const std::string& actor = "brie_daemon");
    int increment_network_retry(const std::string& partition_id);
    void reset_retries(const std::string& partition_id);
    void register_shredded_partition(const std::string& partition_id);
    
    [[nodiscard]] std::string attest_partition(const AttestationContext& ctx, const std::string& mock_signature);
    [[nodiscard]] std::optional<std::string> get_bundle(const std::string& partition_id);
    
    void sweep_boot_recovery();

    void start_postgres_listener(const std::string& pg_conn_str);
    void stop_postgres_listener();

private:
    sqlite3* db_{nullptr};
    std::string db_path_;
    const int max_retries_{5};

    std::thread listen_thread_;
    std::atomic<bool> listening_{false};
    std::unique_ptr<pqxx::connection> pg_conn_;

    void init_db();
    void journal_transition(const std::string& partition_id, const std::string& prev_state, const std::string& new_state, const std::string& actor);
};

} // namespace quantum_flex

#endif // QUANTUM_FLEX_STATE_MANAGER_HPP
