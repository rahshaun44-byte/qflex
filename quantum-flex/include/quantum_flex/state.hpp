#ifndef QUANTUM_FLEX_STATE_HPP
#define QUANTUM_FLEX_STATE_HPP

#include <string>

namespace quantum_flex {

enum class BrieState {
    SHRED_VERIFIED,
    SIGNING,
    SIGNED_LOCAL,
    LEDGER_PENDING,
    LEDGER_COMMITTED,
    COMPLETE,
    SIGNING_INTERRUPTED,
    REQUIRES_OPERATOR,
    UNKNOWN
};

std::string state_to_string(BrieState state);
BrieState string_to_state(const std::string& str);

} // namespace quantum_flex

#endif // QUANTUM_FLEX_STATE_HPP
