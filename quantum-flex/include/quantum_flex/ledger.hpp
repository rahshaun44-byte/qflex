#ifndef QUANTUM_FLEX_LEDGER_HPP
#define QUANTUM_FLEX_LEDGER_HPP

#include <cstdint>
#include <string>

namespace quantum_flex::node {
    class LocalNode;
} // namespace quantum_flex::node

namespace quantum_flex::ledger {

    constexpr size_t STATE_ROOT_LEN = 64;

#pragma pack(push, 1)
    struct SnapshotHeader {
        uint64_t version;
        uint64_t timestamp;
        // NOLINTNEXTLINE(modernize-avoid-c-arrays,hicpp-avoid-c-arrays,cppcoreguidelines-avoid-c-arrays)
        char state_root[STATE_ROOT_LEN]; // SHA-256 hex string
        uint32_t peer_count;
    };

    struct SnapshotState {
        SnapshotHeader header;
    };
#pragma pack(pop)

    class LedgerManager {
    public:
        explicit LedgerManager(quantum_flex::node::LocalNode& node);
        
        void create_snapshot();
        void compact_ledger();
        [[nodiscard]] auto load_snapshot() -> bool;

    private:
        quantum_flex::node::LocalNode* node_;
        
        static constexpr auto SNAPSHOT_PATH = "data/snapshot.dat";
        static constexpr auto SNAPSHOT_TMP_PATH = "data/snapshot.tmp";
        static constexpr auto LEDGER_PATH = "data/ledger.dat";
        static constexpr auto LEDGER_TMP_PATH = "data/ledger.tmp";
    };

} // namespace quantum_flex::ledger

#endif // QUANTUM_FLEX_LEDGER_HPP
