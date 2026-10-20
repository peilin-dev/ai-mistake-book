import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

MatchStatus = Literal["exact", "fuzzy", "ambiguous", "none", "continued"]


@dataclass(frozen=True)
class MatchResult:
    student_id: int | None
    status: MatchStatus


def _norm(name: str | None) -> str:
    return re.sub(r"\s+", "", name or "")


def match_student(
    name: str | None,
    roster: list[tuple[int, str]],
    prev_page_student_id: int | None,
    threshold: float,
) -> MatchResult:
    target = _norm(name)
    if not target:
        if prev_page_student_id is not None:
            return MatchResult(prev_page_student_id, "continued")
        return MatchResult(None, "none")

    normed = [(sid, _norm(n)) for sid, n in roster]

    exact = [sid for sid, n in normed if n == target]
    if len(exact) == 1:
        return MatchResult(exact[0], "exact")
    if len(exact) > 1:
        return MatchResult(None, "ambiguous")

    if not normed:
        return MatchResult(None, "none")
    scores = [(SequenceMatcher(None, target, n).ratio(), sid) for sid, n in normed]
    best = max(r for r, _ in scores)
    if best < threshold:
        return MatchResult(None, "none")
    winners = [sid for r, sid in scores if r == best]
    if len(winners) == 1:
        return MatchResult(winners[0], "fuzzy")
    return MatchResult(None, "ambiguous")
