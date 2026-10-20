UNRESOLVED_STUDENT_STATUSES = {"fuzzy", "ambiguous", "none"}


def needs_review(
    confidence: float, answer_verified: bool, student_status: str, threshold: float
) -> bool:
    return (
        confidence < threshold
        or not answer_verified
        or student_status in UNRESOLVED_STUDENT_STATUSES
    )


def filter_knowledge_point(kp_id: int | None, allowed: set[int]) -> int | None:
    return kp_id if kp_id in allowed else None
