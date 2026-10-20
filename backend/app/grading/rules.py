UNRESOLVED_STUDENT_STATUSES = {"fuzzy", "ambiguous", "none"}


def needs_review(
    confidence: float, student_status: str, threshold: float, answer_mismatch: bool = False
) -> bool:
    """Spec 7.3 (revised 2026-10-21): an unverified answer alone no longer needs review."""
    return (
        confidence < threshold
        or student_status in UNRESOLVED_STUDENT_STATUSES
        or answer_mismatch
    )


def filter_knowledge_point(kp_id: int | None, allowed: set[int]) -> int | None:
    return kp_id if kp_id in allowed else None
