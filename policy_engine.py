from classifier_service import FailureCategory

def evaluate_recovery_policy(category: FailureCategory, diagnosis, retry_count: int, max_retries: int = 3) -> str:
    """Gatekeeper logic dictating Auto Recovery, Approval, or Escalation."""
    if retry_count >= max_retries or category == FailureCategory.HARD_STOP:
        return "ESCALATION"

    if category == FailureCategory.TECHNICAL_TRANSIENT:
        return "AUTO_RECOVERY"

    if diagnosis and diagnosis.risk_level == "LOW" and diagnosis.confidence_score >= 0.95 and diagnosis.corrected_payload:
        return "AUTO_RECOVERY"

    if diagnosis and diagnosis.corrected_payload:
        return "APPROVAL"

    return "ESCALATION"