from enum import Enum
from typing import Tuple

class FailureCategory(str, Enum):
    TECHNICAL_TRANSIENT = "TECHNICAL_TRANSIENT"
    LOGICAL_BUSINESS = "LOGICAL_BUSINESS"
    HARD_STOP = "HARD_STOP"

def classify_failure(error_msg: str) -> Tuple[FailureCategory, bool]:
    """Intercepts SAP MPL traces to prevent infinite blind retries."""
    msg = error_msg.lower() if error_msg else ""

    hard_stops = ['unauthorized', '401', 'forbidden', '403', 'certificate expired', 'sslhandshake']
    if any(k in msg for k in hard_stops):
        return FailureCategory.HARD_STOP, False

    transient_indicators = ['timeout', 'connection reset', '502', '503', '504', 'lock held', 'temporarily unavailable']
    if any(k in msg for k in transient_indicators):
        return FailureCategory.TECHNICAL_TRANSIENT, True

    return FailureCategory.LOGICAL_BUSINESS, False