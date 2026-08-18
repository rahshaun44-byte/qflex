#include "quantum_flex/local_node.hpp"
#include "quantum_flex/ipc_server.hpp"
#include "quantum_flex/brie_node.hpp"

#include <atomic>
#include <csignal>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <string>

namespace {
    auto environment_value(const char* name, const std::string& fallback) -> std::string {
        const char* value = std::getenv(name);
        return value != nullptr && *value != '\0' ? std::string(value) : fallback;
    }
}

namespace {
    // Atomic flag ensures thread-safe, async-signal-safe state evaluation
    // NOLINTNEXTLINE(cppcoreguidelines-avoid-non-const-global-variables)
    std::atomic<bool> g_shutdown_requested{false};
    
    void handle_signal(int /*signum*/) {
        // ONLY set the flag. DO NOT execute complex logic or I/O here.
        g_shutdown_requested = true; 
    }
} // namespace

auto main() -> int {
    // Catch both terminal exits (SIGINT) and systemd shutdown calls (SIGTERM)
    static_cast<void>(std::signal(SIGINT, handle_signal));
    static_cast<void>(std::signal(SIGTERM, handle_signal));

    quantum_flex::node::LocalNode daemon;
    const std::string data_dir = environment_value("QF_DATA_DIR", "/home/rahshaunchambers/quantum-flex/data");
    const std::string postgres_conninfo = environment_value("QF_POSTGRES_CONNINFO", "");

    std::cout << "[*] Booting Quantum Flex Engine...\n";

    try {
        daemon.load_state(data_dir + "/ledger.dat");
        
        if (!postgres_conninfo.empty()) {
            try {
                std::cout << "[*] Executing BrieNode test sequence...\n";
                quantum_flex::crypto::HybridSigner signer(
                    environment_value("QF_ED_PRIVATE_KEY", data_dir + "/ed_priv.pem"),
                    environment_value("QF_PQC_PRIVATE_KEY", data_dir + "/pqc_priv.pem"));
                quantum_flex::node::BrieNode brie(postgres_conninfo, signer);
                brie.neurogenesis_purge("test_partition");
            } catch (const std::exception& e) {
                std::cerr << "[!] BrieNode test failed (Postgres unavailable): " << e.what() << "\n";
            }
        } else {
            std::cout << "[*] PostgreSQL integration disabled; QF_POSTGRES_CONNINFO is unset.\n";
        }
        
    } catch (const std::exception& e) {
        std::cerr << "[!] System Halt: " << e.what() << '\n';
        return 1;
    }

    quantum_flex::ipc::IpcServer server(
        9443,
        environment_value("QF_SERVER_CERT", data_dir + "/mtls/qf_server.crt"),
        environment_value("QF_SERVER_KEY", data_dir + "/mtls/qf_server.key"),
        environment_value("QF_ROOT_CA", data_dir + "/mtls/qf_root_ca.pem"),
        daemon
    );

    std::cout << "[*] Quantum Flex Engine Online. Awaiting Telemetry...\n";
    std::cout << "[*] mTLS TCP Socket listening on 127.0.0.1:9443\n";
    
    // Boot Postgres Event Listener
    if (!postgres_conninfo.empty()) {
        daemon.get_state_manager().start_postgres_listener(postgres_conninfo);
    }
    
    server.start();

    // The ingestion loop. If a signal is caught, accept() fails with EINTR, 
    // the loop evaluates g_shutdown_requested, and cleanly breaks.
    while (!g_shutdown_requested.load()) {
        static_cast<void>(server.process_single_connection());
    }

    std::cout << "\n[*] Engine Halt Requested. Initiating Cryptographic Serialization...\n";
    
    server.stop();
    
    try {
        // Write to our secure data directory before collapsing the process
        daemon.serialize_state(data_dir + "/ledger.dat");
        std::cout << "[+] Ledger successfully committed to disk. Superposition collapsed.\n";
    } catch (const std::exception& e) {
        std::cerr << "[!] Serialization Failed: " << e.what() << '\n';
        return 1;
    }

    return 0;
}
