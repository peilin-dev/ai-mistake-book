"""Benchmark vision models on hand-labelled exam photos (spec section 8).

Usage: python scripts/benchmark_models.py --dir bench --models qwen:qwen-vl-max doubao:<model> --out bench_report.csv
Layout: bench/<case_id>/page.jpg + truth.json {subject, grade, questions: [{no, is_correct, score}]}
"""
import argparse
import asyncio
import csv
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.ai.base import ModelCallError, ModelOutputError, VisionModel
from app.ai.registry import build_model
from app.config import get_settings
from app.grading.crop import prepare_image
from app.grading.prompts import build_grading_prompt
from app.grading.schema import GradedPage

log = logging.getLogger("benchmark")

CASE_COLUMNS = ["case_id", "model", "subject", "status", "matched", "total", "correct_agree",
                "score_abs_err", "latency_s", "input_tokens", "output_tokens", "cost_fen"]
SUMMARY_COLUMNS = ["model", "subject", "cases", "ok_cases", "agree_rate", "coverage",
                   "avg_latency_s", "avg_cost_fen"]


@dataclass(frozen=True)
class CaseScore:
    matched: int
    total: int
    correct_agree: int
    score_abs_err: float


def score_case(truth: dict, graded: GradedPage) -> CaseScore:
    model_qs = {q.no: q for q in graded.questions}
    matched = agree = 0
    err = 0.0
    for tq in truth["questions"]:
        mq = model_qs.get(str(tq["no"]))
        if mq is None:
            continue
        matched += 1
        agree += bool(tq["is_correct"]) == mq.is_correct
        err += abs(float(tq["score"]) - mq.score)
    return CaseScore(matched, len(truth["questions"]), agree, err)


def _cost(model: str, tin: int, tout: int) -> float:
    price_in, price_out = get_settings().PRICE_FEN_PER_1K.get(model, (0.0, 0.0))
    return tin / 1000 * price_in + tout / 1000 * price_out


async def _run_one(name: str, model: VisionModel, case_id: str, truth: dict, image: bytes) -> dict:
    row = dict.fromkeys(CASE_COLUMNS)
    row.update(case_id=case_id, model=name, subject=truth["subject"], total=len(truth["questions"]))
    prompt = build_grading_prompt(truth["subject"], truth["grade"], [], [])
    start = time.perf_counter()
    try:
        result = await model.complete_json(prompt, [image])
    except (ModelCallError, ModelOutputError) as exc:
        row.update(status="call_error" if isinstance(exc, ModelCallError) else "invalid_output",
                   latency_s=time.perf_counter() - start)
        log.warning("%s on %s failed: %s", name, case_id, exc)
        return row
    row["latency_s"] = time.perf_counter() - start
    row.update(input_tokens=result.input_tokens, output_tokens=result.output_tokens,
               cost_fen=_cost(result.model, result.input_tokens, result.output_tokens))
    try:
        graded = GradedPage.model_validate(result.data)
    except ValidationError as exc:
        row["status"] = "invalid_output"
        log.warning("%s on %s invalid output: %s", name, case_id, exc)
        return row
    s = score_case(truth, graded)
    row.update(status="ok", matched=s.matched, correct_agree=s.correct_agree, score_abs_err=s.score_abs_err)
    return row


def _ratio(num: float, den: float):
    return num / den if den else None


def _summarize(rows: list[dict]) -> list[dict]:
    out = []
    for name in dict.fromkeys(r["model"] for r in rows):
        mrows = [r for r in rows if r["model"] == name]
        groups = [(s, [r for r in mrows if r["subject"] == s]) for s in dict.fromkeys(r["subject"] for r in mrows)]
        for subject, grp in groups + [("ALL", mrows)]:
            ok = [r for r in grp if r["status"] == "ok"]
            out.append({
                "model": name, "subject": subject, "cases": len(grp), "ok_cases": len(ok),
                "agree_rate": _ratio(sum(r["correct_agree"] for r in ok), sum(r["matched"] for r in ok)),
                "coverage": _ratio(sum(r["matched"] for r in ok), sum(r["total"] for r in grp)),
                "avg_latency_s": _ratio(sum(r["latency_s"] for r in grp if r["latency_s"] is not None),
                                        len([r for r in grp if r["latency_s"] is not None])),
                "avg_cost_fen": _ratio(sum(r["cost_fen"] for r in ok), len(ok)),
            })
    return out


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, columns)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})


def summary_path(out_csv: Path) -> Path:
    return out_csv.with_name(f"{out_csv.stem}_summary.csv")


async def run_benchmark(cases_dir: Path, models: dict[str, VisionModel], out_csv: Path,
                        concurrency: int = 1) -> list[dict]:
    cases = []
    for d in sorted(p for p in Path(cases_dir).iterdir() if p.is_dir()):
        page, truth_file = d / "page.jpg", d / "truth.json"
        if not (page.is_file() and truth_file.is_file()):
            log.warning("skipping %s: needs page.jpg and truth.json", d.name)
            continue
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        cases.append((d.name, truth, prepare_image(page.read_bytes())))

    sem = asyncio.Semaphore(max(1, concurrency))

    async def guarded(name, model, cid, truth, image):
        async with sem:
            return await _run_one(name, model, cid, truth, image)

    rows = list(await asyncio.gather(*(
        guarded(name, model, cid, truth, image)
        for name, model in models.items() for cid, truth, image in cases)))
    _write_csv(out_csv, CASE_COLUMNS, rows)
    _write_csv(summary_path(out_csv), SUMMARY_COLUMNS, _summarize(rows))
    return rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--models", nargs="+", required=True, help="provider:model, e.g. qwen:qwen-vl-max")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    models = {spec: build_model(spec) for spec in args.models}
    asyncio.run(run_benchmark(args.dir, models, args.out, args.concurrency))
    with summary_path(args.out).open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            print("  ".join(f"{k}={v}" for k, v in r.items()))


if __name__ == "__main__":
    main()
