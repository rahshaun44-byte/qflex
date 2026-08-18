pragma circom 2.0.0;

template LedgerVerify() {
    signal input confidence_score;
    signal input validity;
    signal output final_decision;

    final_decision <== confidence_score * validity;
}

component main = LedgerVerify();
