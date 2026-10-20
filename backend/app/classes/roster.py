import re
from dataclasses import dataclass

_STUDENT_NO = re.compile(r"^[A-Za-z]?\d+$")
_COMMA_OR_TAB = re.compile(r"[,，\t]")


@dataclass(frozen=True)
class RosterEntry:
    name: str
    student_no: str | None = None


def _parse_line(line: str) -> RosterEntry | None:
    if _COMMA_OR_TAB.search(line):
        parts = [p.strip() for p in _COMMA_OR_TAB.split(line)]
    else:
        parts = line.split()
    parts = [p for p in parts if p]
    if not parts:
        return None
    numbers = [p for p in parts if _STUDENT_NO.match(p)]
    if len(numbers) != 1:
        # no student_no-shaped token (or ambiguous): the whole line is the name
        return RosterEntry(" ".join(parts), None)
    name = " ".join(p for p in parts if p is not numbers[0])
    if not name:
        return RosterEntry(numbers[0], None)
    return RosterEntry(name, numbers[0])

def parse_roster(text: str) -> list[RosterEntry]:
    """One student per line; blank lines skipped; identical entries deduplicated."""
    entries: list[RosterEntry] = []
    seen: set[RosterEntry] = set()
    for line in text.splitlines():
        entry = _parse_line(line.strip())
        if entry is None or entry in seen:
            continue
        seen.add(entry)
        entries.append(entry)
    return entries
