"""Import a knowledge-point tree from YAML (idempotent upsert by `code`).

CLI: python -m app.knowledge.loader [--prune] <yaml>...
Arguments containing `*` are globbed here, so `data/knowledge/*.yaml` also works on Windows.
"""
import argparse
import asyncio
import glob
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import delete, select
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
    if not nodes:
        raise ValueError(f"{path}: no nodes")  # an empty file would prune its whole subject
    return subject, nodes


async def _upsert(db: AsyncSession, subject: Subject, nodes: list[_Node]) -> None:
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


async def _prune(db: AsyncSession, subject: Subject, codes: set[str]) -> None:
    await db.flush()  # re-parenting must land before the stale parents are deleted
    await db.execute(
        delete(KnowledgePoint)
        .where(KnowledgePoint.subject == subject, KnowledgePoint.code.not_in(sorted(codes)))
        .execution_options(synchronize_session=False)
    )


async def import_yaml(db: AsyncSession, path: Path, prune: bool = False) -> int:
    """Upsert every node in the file by code; returns the node count. Commits.

    With prune=True, knowledge points of the file's subject whose code is not in the file are
    deleted in the same transaction; question_results pointing at them are set to NULL by the FK.
    """
    subject, nodes = _parse(path)  # validate everything before touching the DB
    await _upsert(db, subject, nodes)
    if prune:
        await _prune(db, subject, {n.code for n in nodes})
    await db.commit()
    return len(nodes)


def _expand(args: list[str]) -> list[Path]:
    paths: list[Path] = []
    for arg in args:
        if "*" in arg:
            matches = sorted(glob.glob(arg))
            if not matches:
                raise SystemExit(f"no files match {arg}")
            paths.extend(Path(m) for m in matches)
        else:
            paths.append(Path(arg))
    return paths


async def _import_files(parsed: list[tuple[Path, Subject, list[_Node]]], prune: bool) -> None:
    """Import every file, then prune once per subject, all in one transaction."""
    engine = create_async_engine(get_settings().DATABASE_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            codes: dict[Subject, set[str]] = {}
            for _, subject, nodes in parsed:
                await _upsert(db, subject, nodes)
                codes.setdefault(subject, set()).update(n.code for n in nodes)
            if prune:
                for subject, subject_codes in codes.items():
                    await _prune(db, subject, subject_codes)
            await db.commit()
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import knowledge-point YAML files")
    parser.add_argument("--prune", action="store_true",
                        help="delete knowledge points of each file's subject that the files no longer list")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    parsed = []
    for p in _expand(args.files):  # validate every file before importing any
        try:
            subject, nodes = _parse(p)
        except ValueError as e:
            raise SystemExit(f"refusing to import: {e}") from None
        parsed.append((p, subject, nodes))
    if args.prune:
        by_subject: dict[Subject, list[Path]] = {}
        for p, subject, _ in parsed:
            by_subject.setdefault(subject, []).append(p)
        dupes = {s: ps for s, ps in by_subject.items() if len(ps) > 1}
        if dupes:
            detail = "; ".join(f"{s.value}: {', '.join(str(p) for p in ps)}" for s, ps in dupes.items())
            raise SystemExit(f"refusing to prune: several files declare the same subject ({detail})")
    asyncio.run(_import_files(parsed, prune=args.prune))
    for p, _, nodes in parsed:
        print(f"imported {len(nodes)} nodes from {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
