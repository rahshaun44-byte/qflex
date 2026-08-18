#include <climits>
#include <gtest/gtest.h>

namespace {

void cause_signed_overflow() noexcept {
    volatile int max_val = INT_MAX;
    volatile int increment = 1;
    // The compiler cannot optimize this out; will force an immediate runtime crash
    [[maybe_unused]] volatile int overflow = max_val + increment;
}

}  // namespace

TEST(SanitizerSuite, ProveUBSanBehavior) {
    // Enforce a regular expression lookup to confirm UBSan killed the execution flow
    EXPECT_DEATH(cause_signed_overflow(), "runtime error: signed integer overflow");
}

namespace {
    void cause_use_after_free() noexcept {
        // Allocate heap memory
        int* dangling_ptr = new int(100);
        // Free the memory
        delete dangling_ptr;
        // Attempt to access the destroyed memory location
        [[maybe_unused]] volatile int leak = *dangling_ptr;
    }
}

TEST(SanitizerSuite, ProveASanBehavior) {
    // Enforce execution death on heap-use-after-free
    EXPECT_DEATH(cause_use_after_free(), "AddressSanitizer: heap-use-after-free");
}
