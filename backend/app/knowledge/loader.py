"""Import a knowledge-point tree from YAML (idempotent upsert by `code`).

CLI: python -m app.knowledge.loader <yaml>...
"""
import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import KnowledgePoint, Subject


@dataclass
class _Node:
    code: str
    name: str
    parent_code: str | None
    grade_min: int
    grade_max: int


def _band(value, code: str) -> tuple[int, int]:
    ok = (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
        and 1 <= value[0] <= value[1] <= 12
    )
    if not ok:
        raise ValueError(f"{code}: grade_band must be [min, max] ints in 1-12 with min <= max, got {value!r}")
    return value[0], value[1]


def _parse(path: Path) -> tuple[Subject, list[_Node]]:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    try:
        subject = Subject(doc.get("subject"))
    except ValueError:
        raise ValueError(f"invalid subject: {doc.get('subject')!r}") from None
    top_band = doc.get("grade_band")

    nodes: list[_Node] = []
    seen: set[str] = set()

    def walk(items, parent_code: str | None, inherited) -> None:
        for item in items or []:
            code = str(item.get("code", "")).strip()
            if not code:
                raise ValueError(f"node without code: {item!r}")
            if code in seen:
                raise ValueError(f"duplicate code: {code}")
            seen.add(code)
            if not str(item.get("name", "")).strip():
                raise ValueError(f"{code}: missing name")
            band = item.get("grade_band", inherited)
            gmin, gmax = _band(band, code)
            nodes.append(_Node(code, str(item["name"]), parent_code, gmin, gmax))
            walk(item.get("children"), code, band)

    walk(doc.get("nodes"), None, top_band)
    return subject, nodes


async def import_yaml(db: AsyncSession, path: Path) -> int:
    """Upsert every node in the file by code; returns the node count. Commits."""
    subject, nodes = _parse(path)  # validate everything before touching the DB
    existing = {
        kp.code: kp
        for kp in (
            await db.execute(select(KnowledgePoint).where(KnowledgePoint.code.in_([n.code for n in nodes])))
        ).scalars()
    }
    for n in nodes:  # parents precede children
        kp = existing.get(n.code)
        if kp is None:
            kp = existing[n.code] = KnowledgePoint(code=n.code)
            db.add(kp)
        kp.name = n.name
        kp.subject = subject
        kp.grade_min, kp.grade_max = n.grade_min, n.grade_max
        if n.parent_code is None:
            kp.parent_id = None
        else:
            parent = existing[n.parent_code]
            if parent.id is None:
                await db.flush()
            kp.parent_id = parent.id
    await db.commit()
    return len(nodes)


async def _import_files(paths: list[Path]) -> list[tuple[Path, int]]:
    engine = create_async_engine(get_settings().DATABASE_URL)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        results = []
        for p in paths:
            async with factory() as db:
                results.append((p, await import_yaml(db, p)))
        return results
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import knowledge-point YAML files")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for path, count in asyncio.run(_import_files(args.files)):
        print(f"imported {count} nodes from {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
