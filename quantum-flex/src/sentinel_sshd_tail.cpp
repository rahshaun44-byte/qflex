#include <iostream>
#include <string_view>
#include <string>
#include <systemd/sd-journal.h>
#include <unistd.h>
#include <chrono>
#include <cstring>
#include <cstdlib>
#include <sqlite3.h>

sqlite3* db = nullptr;

void init_database() {
    if (sqlite3_open("/home/rahshaunchambers/quantum-flex/telemetry.db", &db) != SQLITE_OK) {
        std::cerr << "[CRITICAL] Cannot open database: " << sqlite3_errmsg(db) << "\n";
        exit(1);
    }
    sqlite3_exec(db, "PRAGMA journal_mode=WAL;", nullptr, nullptr, nullptr);

    const char* table_sql =
        "CREATE TABLE IF NOT EXISTS ssh_alerts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "event_payload TEXT);";
    sqlite3_exec(db, table_sql, nullptr, nullptr, nullptr);
}

void extract_and_analyze(sd_journal *journal_context) {
    const void *data;
    size_t length;

    if (sd_journal_get_data(journal_context, "MESSAGE", &data, &length) < 0)
        return;

    std::string_view raw_payload(static_cast<const char*>(data), length);
    // MESSAGE= prefix is 8 characters
    std::string_view message = raw_payload.length() > 8 ? raw_payload.substr(8) : raw_payload;

    if (message.find("Failed password") != std::string_view::npos ||
        message.find("Invalid user") != std::string_view::npos ||
        message.find("Connection closed") != std::string_view::npos ||
        message.find("Disconnected") != std::string_view::npos) {

        std::cout << "\n[ALERT_TRIGGERED] Logging to SQLite: " << message << std::endl;

        const char* insert_sql = "INSERT INTO ssh_alerts (event_payload) VALUES (?);";
        sqlite3_stmt* stmt = nullptr;

        if (sqlite3_prepare_v2(db, insert_sql, -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_text(stmt, 1, message.data(), static_cast<int>(message.length()), SQLITE_TRANSIENT);
            sqlite3_step(stmt);
            sqlite3_finalize(stmt);
        }
    }
}

int main() {
    init_database();

    sd_journal *journal_context = nullptr;
    int ret = sd_journal_open(&journal_context, SD_JOURNAL_LOCAL_ONLY);
    if (ret < 0) {
        std::cerr << "[CRITICAL] Failed to open journal: " << strerror(-ret) << "\n";
        return 1;
    }

    sd_journal_add_match(journal_context, "_SYSTEMD_UNIT=sshd.service", 0);
    sd_journal_seek_tail(journal_context);
    sd_journal_previous(journal_context);

    std::cout << "[SYSTEM ONLINE] Quantum Flex Sentinel: WAL Persistence Active.\n";

    while (true) {
        ret = sd_journal_wait(journal_context, 1000000ULL);
        if (ret < 0) {
            std::cerr << "[ERROR] Journal wait failed: " << strerror(-ret) << "\n";
            break;
        }

        if (ret == SD_JOURNAL_APPEND) {
            while (sd_journal_next(journal_context) > 0) {
                extract_and_analyze(journal_context);
            }
        }
    }

    sd_journal_close(journal_context);
    if (db) sqlite3_close(db);
    return 0;
}
