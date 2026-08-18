#ifndef QUANTUM_FLEX_IPC_SERVER_HPP
#define QUANTUM_FLEX_IPC_SERVER_HPP

#include "quantum_flex/local_node.hpp"

#include <string>

#include <openssl/ssl.h>
#include <openssl/err.h>

namespace quantum_flex::ipc {

    class IpcServer {
    public:
        IpcServer(int port, const std::string& cert_file, const std::string& key_file, const std::string& ca_file, node::LocalNode& target_node, std::string bind_address = "127.0.0.1");
        ~IpcServer();

        // Prevent copying and moving to manage the socket descriptor safely
        IpcServer(const IpcServer&) = delete;
        auto operator=(const IpcServer&) -> IpcServer& = delete;
        IpcServer(IpcServer&&) = delete;
        auto operator=(IpcServer&&) -> IpcServer& = delete;

        // Initializes the socket, unlinks stale files, and binds to the kernel
        void start();

        // Processes exactly one connection. 
        // In a production daemon, this loops, but we isolate it for deterministic testing.
        [[nodiscard]] auto process_single_connection() -> bool;

        void stop();

    private:
        int port_;
        std::string cert_file_;
        std::string key_file_;
        std::string ca_file_;
        std::string bind_address_;
        node::LocalNode& node_;
        int server_fd_{-1};
        SSL_CTX* ssl_ctx_{nullptr};

        void configure_ssl_context();
    };

} // namespace quantum_flex::ipc

#endif // QUANTUM_FLEX_IPC_SERVER_HPP
