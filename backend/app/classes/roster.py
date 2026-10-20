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
    if len(parts) == 1:
        return RosterEntry(parts[0], None)
    first, second = parts[0], parts[1]
    if _STUDENT_NO.match(first) and not _STUDENT_NO.match(second):
        return RosterEntry(second, first)
    if _STUDENT_NO.match(second) and not _STUDENT_NO.match(first):
        return RosterEntry(first, second)
    # ambiguous: "学号 姓名" for whitespace, "姓名,学号" for comma/tab
    if _COMMA_OR_TAB.search(line):
        return RosterEntry(first, second)
    return RosterEntry(second, first)


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
