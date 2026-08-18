#include "quantum_flex/ledger.hpp"

#include "quantum_flex/gossipsub_handler.hpp"
#include "quantum_flex/local_node.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <string>

namespace quantum_flex::ledger {

    LedgerManager::LedgerManager(quantum_flex::node::LocalNode& node) : node_(&node) {}

    void LedgerManager::create_snapshot() {
        std::ofstream out(SNAPSHOT_TMP_PATH, std::ios::binary);
        if (!out) {
            return;
        }

        SnapshotState state{};
        state.header.version = 1;
        state.header.timestamp = static_cast<uint64_t>(time(nullptr));
        
        const std::string root = node_->get_node_state_root();
        strncpy(state.header.state_root, root.c_str(), sizeof(state.header.state_root)); // NOLINT
        
        // Write header
        out.write(reinterpret_cast<const char*>(&state.header), sizeof(state.header)); // NOLINT
        
        // Write peer scores
        node_->gossipsub().serialize_peer_scores(out);
        
        out.close();
        
        // Atomic rename
        static_cast<void>(std::rename(SNAPSHOT_TMP_PATH, SNAPSHOT_PATH));
    }

    // NOLINTNEXTLINE(readability-convert-member-functions-to-static)
    void LedgerManager::compact_ledger() {
        // Very basic compaction stub: just clear the ledger or keep N lines.
        // For phase 9.2, we just rename to .tmp and copy back.
        // Full compaction requires tracking the exact timestamp.
        std::ifstream in_stream(LEDGER_PATH);
        if (!in_stream) {
            return;
        }
        
        std::ofstream out(LEDGER_TMP_PATH);
        std::string line;
        
        // Skip some old entries (stub)
        while (std::getline(in_stream, line)) {
            // Write only recent ones
            out << line << "\n";
        }
        
        in_stream.close();
        out.close();
        
        static_cast<void>(std::rename(LEDGER_TMP_PATH, LEDGER_PATH));
    }

    auto LedgerManager::load_snapshot() -> bool {
        std::ifstream in_stream(SNAPSHOT_PATH, std::ios::binary);
        if (!in_stream) {
            return false;
        }
        
        SnapshotState state{};
        if (!in_stream.read(reinterpret_cast<char*>(&state.header), sizeof(state.header))) { // NOLINT
            return false;
        }
        
        // Load peer scores
        node_->gossipsub().deserialize_peer_scores(in_stream);
        return true;
    }

} // namespace quantum_flex::ledger
