#include <systemd/sd-journal.h>
#include <iostream>
#include <string>
#include <system_error>

class SentinelEngine {
public:
    SentinelEngine() {
        std::cout << "[SENTINEL] Initializing Quantum Flex telemetry core..." << std::endl;
    }

    ~SentinelEngine() {
        std::cout << "[SENTINEL] Shutting down telemetry core." << std::endl;
    }

    void start_monitoring() {
        sd_journal *j = nullptr;
        int r = sd_journal_open(&j, SD_JOURNAL_LOCAL_ONLY);
        if (r < 0) {
            throw std::system_error(-r, std::generic_category(), "Failed to open systemd journal");
        }

        r = sd_journal_add_match(j, "SYSLOG_IDENTIFIER=sshd-session", 0);
        if (r < 0) {
            sd_journal_close(j);
            throw std::system_error(-r, std::generic_category(), "Failed to add journal filter match");
        }

        sd_journal_seek_tail(j);
        sd_journal_previous(j);

        std::cout << "[SENTINEL] Active and listening for target telemetry..." << std::endl;

        while (true) {
            r = sd_journal_next(j);
            if (r < 0) {
                std::cerr << "[SENTINEL] Error iterating journal: " << r << std::endl;
                break;
            }
            if (r == 0) {
                sd_journal_wait(j, (uint64_t)-1);
                continue;
            }

            extract_event_payload(j);
        }

        sd_journal_close(j);
    }

private:
    void extract_event_payload(sd_journal *j) {
        const void *data = nullptr;
        size_t length = 0;
        std::string message = "NO_MESSAGE";
        std::string timestamp = "NO_TIMESTAMP";

        if (sd_journal_get_data(j, "MESSAGE", &data, &length) >= 0) {
            message.assign(static_cast<const char*>(data), length);
            auto pos = message.find('=');
            if (pos != std::string::npos) {
                message = message.substr(pos + 1);
            }
        }

        uint64_t realtime_usec = 0;
        if (sd_journal_get_realtime_usec(j, &realtime_usec) >= 0) {
            timestamp = std::to_string(realtime_usec);
        }

        std::cout << "[TELEMETRY CAPTURED]" 
                  << " | Timestamp: " << timestamp 
                  << " | Payload: " << message << std::endl;
    }
};

int main() {
    try {
        SentinelEngine engine;
        engine.start_monitoring();
    } catch (const std::exception& e) {
        std::cerr << "[CRITICAL ERROR] " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
