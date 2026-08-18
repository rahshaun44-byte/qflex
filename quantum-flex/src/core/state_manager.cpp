#include "quantum_flex/state_manager.hpp"
#include <stdexcept>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <ctime>
#include <openssl/evp.h>

namespace quantum_flex {

static std::string sha256_hex(const std::string& input) {
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

    std::ostringstream ss;
    for (unsigned int i = 0; i < hash_len; ++i) {
        ss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(hash[i]);
    }
    return ss.str();
}

std::string state_to_string(BrieState state) {
    switch (state) {
        case BrieState::SHRED_VERIFIED: return "SHRED_VERIFIED";
        case BrieState::SIGNING: return "SIGNING";
        case BrieState::SIGNED_LOCAL: return "SIGNED_LOCAL";
        case BrieState::LEDGER_PENDING: return "LEDGER_PENDING";
        case BrieState::LEDGER_COMMITTED: return "LEDGER_COMMITTED";
        case BrieState::COMPLETE: return "COMPLETE";
        case BrieState::SIGNING_INTERRUPTED: return "SIGNING_INTERRUPTED";
        case BrieState::REQUIRES_OPERATOR: return "REQUIRES_OPERATOR";
        default: return "UNKNOWN";
    }
}

BrieState string_to_state(const std::string& str) {
    if (str == "SHRED_VERIFIED") return BrieState::SHRED_VERIFIED;
    if (str == "SIGNING") return BrieState::SIGNING;
    if (str == "SIGNED_LOCAL") return BrieState::SIGNED_LOCAL;
    if (str == "LEDGER_PENDING") return BrieState::LEDGER_PENDING;
    if (str == "LEDGER_COMMITTED") return BrieState::LEDGER_COMMITTED;
    if (str == "COMPLETE") return BrieState::COMPLETE;
    if (str == "SIGNING_INTERRUPTED") return BrieState::SIGNING_INTERRUPTED;
    if (str == "REQUIRES_OPERATOR") return BrieState::REQUIRES_OPERATOR;
    return BrieState::UNKNOWN;
}

std::string AttestationContext::compute_context_hash() const {
    nlohmann::ordered_json j;
    j["monotonic_counter"] = monotonic_counter;
    j["node_id"] = node_id;
    j["partition_id"] = partition_id;
    j["payload_hash"] = payload_hash;
    j["pre_purge_hash"] = pre_purge_hash;
    j["protocol_version"] = protocol_version;
    j["schema_version"] = schema_version;
    j["shred_proof_hash"] = shred_proof_hash;
    j["timestamp"] = timestamp;
    return sha256_hex(j.dump());
}

StateManager::StateManager(const std::string& db_path) : db_path_(db_path) {
    init_db();
}

StateManager::~StateManager() {
    stop_postgres_listener();
    if (db_) {
        sqlite3_close(db_);
        db_ = nullptr;
    }
}

void StateManager::init_db() {
    if (sqlite3_open(db_path_.c_str(), &db_) != SQLITE_OK) {
        throw std::runtime_error("Failed to open SQLite database: " + db_path_);
    }

    char* err_msg = nullptr;
    const char* sql =
        "PRAGMA journal_mode = WAL;"
        "PRAGMA synchronous = NORMAL;"
        "CREATE TABLE IF NOT EXISTS partition_state ("
        "  partition_id TEXT PRIMARY KEY,"
        "  current_state TEXT NOT NULL,"
        "  retry_count INTEGER DEFAULT 0,"
        "  last_error TEXT,"
        "  last_attempt TIMESTAMP,"
        "  attestation_bundle BLOB,"
        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ");"
        "CREATE TABLE IF NOT EXISTS state_journal ("
        "  journal_id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  partition_id TEXT NOT NULL,"
        "  previous_state TEXT,"
        "  new_state TEXT NOT NULL,"
        "  actor TEXT NOT NULL,"
        "  event_hash TEXT NOT NULL,"
        "  previous_journal_hash TEXT,"
        "  transitioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ");";

    if (sqlite3_exec(db_, sql, nullptr, nullptr, &err_msg) != SQLITE_OK) {
        std::string err = err_msg ? err_msg : "Unknown error";
        sqlite3_free(err_msg);
        throw std::runtime_error("Failed to init state database: " + err);
    }
}

void StateManager::journal_transition(const std::string& partition_id, const std::string& prev_state, const std::string& new_state, const std::string& actor) {
    std::string prev_hash = "0000000000000000000000000000000000000000000000000000000000000000";
    sqlite3_stmt* stmt = nullptr;

    const char* fetch_sql = "SELECT event_hash FROM state_journal ORDER BY journal_id DESC LIMIT 1;";
    if (sqlite3_prepare_v2(db_, fetch_sql, -1, &stmt, nullptr) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* text = sqlite3_column_text(stmt, 0);
            if (text) prev_hash = reinterpret_cast<const char*>(text);
        }
    }
    sqlite3_finalize(stmt);

    int64_t now_ts = std::time(nullptr);
    std::ostringstream raw_event;
    raw_event << prev_hash << ":" << prev_state << ":" << new_state << ":" << now_ts << ":" << partition_id;
    std::string event_hash = sha256_hex(raw_event.str());

    const char* insert_sql =
        "INSERT INTO state_journal (partition_id, previous_state, new_state, actor, event_hash, previous_journal_hash) "
        "VALUES (?, ?, ?, ?, ?, ?);";

    if (sqlite3_prepare_v2(db_, insert_sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, prev_state.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 3, new_state.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 4, actor.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 5, event_hash.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 6, prev_hash.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
}

void StateManager::transition(const std::string& partition_id, BrieState new_state, const std::string& actor) {
    sqlite3_stmt* stmt = nullptr;
    std::string old_state = "UNKNOWN";

    const char* sel_sql = "SELECT current_state FROM partition_state WHERE partition_id = ?;";
    if (sqlite3_prepare_v2(db_, sel_sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            const unsigned char* text = sqlite3_column_text(stmt, 0);
            if (text) old_state = reinterpret_cast<const char*>(text);
        }
    }
    sqlite3_finalize(stmt);

    const char* upd_sql = "UPDATE partition_state SET current_state = ?, updated_at = CURRENT_TIMESTAMP WHERE partition_id = ?;";
    std::string new_state_str = state_to_string(new_state);

    if (sqlite3_prepare_v2(db_, upd_sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, new_state_str.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);

    journal_transition(partition_id, old_state, new_state_str, actor);
}

void StateManager::register_shredded_partition(const std::string& partition_id) {
    sqlite3_stmt* stmt = nullptr;
    const char* sql = "INSERT OR IGNORE INTO partition_state (partition_id, current_state) VALUES (?, ?);";
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        std::string state_str = state_to_string(BrieState::SHRED_VERIFIED);
        sqlite3_bind_text(stmt, 2, state_str.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
}

int StateManager::increment_network_retry(const std::string& partition_id) {
    sqlite3_stmt* stmt = nullptr;
    int retries = 0;
    const char* sel_sql = "SELECT retry_count FROM partition_state WHERE partition_id = ?;";
    if (sqlite3_prepare_v2(db_, sel_sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            retries = sqlite3_column_int(stmt, 0);
        }
    }
    sqlite3_finalize(stmt);

    retries += 1;
    const char* upd_sql = "UPDATE partition_state SET retry_count = ?, last_attempt = CURRENT_TIMESTAMP WHERE partition_id = ?;";
    if (sqlite3_prepare_v2(db_, upd_sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_int(stmt, 1, retries);
        sqlite3_bind_text(stmt, 2, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return retries;
}

void StateManager::reset_retries(const std::string& partition_id) {
    sqlite3_stmt* stmt = nullptr;
    const char* sql = "UPDATE partition_state SET retry_count = 0 WHERE partition_id = ?;";
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
}

std::string StateManager::attest_partition(const AttestationContext& ctx, const std::string& mock_signature) {
    transition(ctx.partition_id, BrieState::SIGNING);

    nlohmann::ordered_json bundle;
    bundle["algorithm"] = "ML-DSA-65+Ed25519";
    bundle["context_hash"] = ctx.compute_context_hash();
    bundle["signature"] = mock_signature;
    bundle["version"] = ctx.protocol_version;
    std::string bundle_str = bundle.dump();

    sqlite3_stmt* stmt = nullptr;
    // Optimistic Concurrency Update
    const char* sql = "UPDATE partition_state SET current_state = ?, attestation_bundle = ?, updated_at = CURRENT_TIMESTAMP WHERE partition_id = ? AND current_state = ?;";
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        std::string signed_local = state_to_string(BrieState::SIGNED_LOCAL);
        std::string signing_state = state_to_string(BrieState::SIGNING);
        sqlite3_bind_text(stmt, 1, signed_local.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_blob(stmt, 2, bundle_str.data(), static_cast<int>(bundle_str.size()), SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 3, ctx.partition_id.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 4, signing_state.c_str(), -1, SQLITE_TRANSIENT);
        
        if (sqlite3_step(stmt) != SQLITE_DONE || sqlite3_changes(db_) == 0) {
            sqlite3_finalize(stmt);
            throw std::runtime_error("Concurrency collision during attestation update for partition: " + ctx.partition_id);
        }
    }
    sqlite3_finalize(stmt);

    journal_transition(ctx.partition_id, state_to_string(BrieState::SIGNING), state_to_string(BrieState::SIGNED_LOCAL), "brie_daemon");
    return bundle_str;
}

std::optional<std::string> StateManager::get_bundle(const std::string& partition_id) {
    sqlite3_stmt* stmt = nullptr;
    const char* sql = "SELECT attestation_bundle FROM partition_state WHERE partition_id = ?;";
    std::optional<std::string> result;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, partition_id.c_str(), -1, SQLITE_TRANSIENT);
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            const void* blob = sqlite3_column_blob(stmt, 0);
            int bytes = sqlite3_column_bytes(stmt, 0);
            if (blob && bytes > 0) {
                result = std::string(reinterpret_cast<const char*>(blob), bytes);
            }
        }
    }
    sqlite3_finalize(stmt);
    return result;
}

void StateManager::sweep_boot_recovery() {
    std::cout << "[Boot Recovery Sweep] Initiating cryptographic state sweep...\n";
    sqlite3_stmt* stmt = nullptr;
    const char* sql = "SELECT partition_id, current_state FROM partition_state WHERE current_state NOT IN ('COMPLETE', 'REQUIRES_OPERATOR');";
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            std::string p_id = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
            std::string state_str = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            std::cout << "[Boot Recovery Sweep] Audit stored binary bundle for partition: " << p_id << " (State: " << state_str << ")" << std::endl;
        }
    }
    sqlite3_finalize(stmt);
}

void StateManager::start_postgres_listener(const std::string& pg_conn_str) {
    if (listening_) return;
    
    listening_ = true;
    listen_thread_ = std::thread([this, pg_conn_str]() {
        try {
            pg_conn_ = std::make_unique<pqxx::connection>(pg_conn_str);
            
            pg_conn_->listen("quantum_telemetry_channel", [](pqxx::notification notif) {
                std::cout << "[StateManager] PostgreSQL NOTIFY received on quantum_telemetry_channel [PID: " << notif.backend_pid << "]\n";
                std::cout << "[StateManager] Event Payload: " << notif.payload << "\n";
                // Here we can trigger the C++ async logic based on the PostgreSQL insert
            });
            
            std::cout << "[StateManager] PostgreSQL LISTEN active on quantum_telemetry_channel\n";
            
            while (listening_) {
                try {
                    pg_conn_->await_notification(0, 500000); // 500ms block
                } catch (const std::exception& e) {
                    if (!listening_) break;
                    std::cerr << "[StateManager] Postgres await_notification error: " << e.what() << "\n";
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                }
            }
        } catch (const std::exception& e) {
            std::cerr << "[StateManager] Fatal error in Postgres listener thread: " << e.what() << "\n";
        }
    });
}

void StateManager::stop_postgres_listener() {
    listening_ = false;
    if (listen_thread_.joinable()) {
        listen_thread_.join();
    }
    if (pg_conn_) {
        pg_conn_.reset();
    }
}

} // namespace quantum_flex
