import json
from pathlib import Path

SUBJECT_RULES: dict[str, str] = json.loads(Path(__file__).with_name("subject_rules.json").read_text(encoding="utf-8"))
