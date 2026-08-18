#include <iostream>
#include <fstream>
#include <string>
#include <chrono>
#include <thread>
#include <atomic>
#include <csignal>
#include <cstring>
#include <systemd/sd-journal.h>

// Persistent, non-volatile state path on Fedora
const std::string CURSOR_FILE = "/var/lib/quantumflex/sentinel_cursor";
std::atomic<bool> g_running{true};

void signal_handler(int signal) {
    if (signal == SIGINT || signal == SIGTERM) {
        g_running = false;
    }
}

void save_cursor(sd_journal *j) {
    char *cursor = nullptr;
    if (sd_journal_get_cursor(j, &cursor) == 0) {
        std::ofstream out(CURSOR_FILE, std::ios::trunc);
        if (out.is_open()) {
            out << cursor;
        }
        free(cursor);
    }
}

int main() {
    // 1. Trap system signals for graceful shutdown
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    sd_journal *j = nullptr;
    int rc = sd_journal_open(&j, SD_JOURNAL_LOCAL_ONLY);
    if (rc < 0) {
        std::cerr << "[-] Failure: Unable to open system journal: " << strerror(-rc) << "\n";
        return 1;
    }

    // 2. Apply match filter: Listen strictly to systemd / sshd unit logs
    sd_journal_add_match(j, "_SYSTEMD_UNIT=sshd.service", 0);

    // 3. Restore state from persistent cursor if present
    std::ifstream in(CURSOR_FILE);
    if (in.is_open()) {
        std::string saved_cursor;
        in >> saved_cursor;
        if (!saved_cursor.empty()) {
            sd_journal_seek_cursor(j, saved_cursor.c_str());
            sd_journal_next(j); // Skip to next unread entry
        }
    } else {
        sd_journal_seek_tail(j); // If no cursor exists, seek to current journal tail
    }

    auto last_flush = std::chrono::steady_clock::now();
    int unwritten_events = 0;

    std::cout << "[+] Sentinel C++ Journal Listener Active. Listening on _SYSTEMD_UNIT=sshd.service...\n";

    while (g_running) {
        rc = sd_journal_next(j);
        if (rc < 0) {
            std::cerr << "[-] Error reading journal\n";
            break;
        }

        if (rc == 0) {
            // Block efficiently until new log events arrive (500ms poll timeout)
            sd_journal_wait(j, 500000);
            continue;
        }

        // 4. Extract raw message payload
        const void *data;
        size_t length;
        if (sd_journal_get_data(j, "MESSAGE", &data, &length) == 0) {
            std::string payload(static_cast<const char*>(data), length);
            
            // 5. Strip "MESSAGE=" prefix
            if (payload.rfind("MESSAGE=", 0) == 0) {
                payload = payload.substr(8);
            }

            std::cout << "[SENTINEL EVENT] " << payload << std::endl;
            unwritten_events++;
        }

        // 6. Throttled cursor write: Flush every 50 events OR every 1,000ms
        auto now = std::chrono::steady_clock::now();
        if (unwritten_events >= 50 || 
            (unwritten_events > 0 && std::chrono::duration_cast<std::chrono::milliseconds>(now - last_flush).count() >= 1000)) {
            save_cursor(j);
            unwritten_events = 0;
            last_flush = now;
        }
    }

    // Final cursor flush on exit
    save_cursor(j);
    sd_journal_close(j);
    std::cout << "[+] Sentinel Shutdown Cleanly. State Preserved.\n";
    return 0;
}
