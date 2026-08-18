# sentinel/ledger/exceptions.py
class TamperDetectionException(Exception):
    """Raised when the hash chain validation sweep detects database modification."""
    pass

class ReplayAttackException(Exception):
    """Raised when an identical ingress payload is repeatedly pushed."""
    pass
