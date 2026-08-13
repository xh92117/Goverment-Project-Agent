from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_official(url: str, official_domains: list[str]) -> bool:
    domain = _domain(url)
    for official in official_domains:
        official = official.lower().strip().removeprefix("www.")
        if domain == official or domain.endswith(f".{official}"):
            return True
    return False


def _evaluate_case(case: dict) -> dict:
    expected = case.get("expected") or {}
    official_domains = list(expected.get("official_domains") or [])
    expected_fields = list(expected.get("fields") or [])
    results = list(case.get("results") or [])
    top3 = results[:3]
    official_results = [result for result in results if _is_official(str(result.get("url", "")), official_domains)]
    low_quality_results = [
        result
        for result in results
        if any(token in _domain(str(result.get("url", ""))) for token in ("mirror", "training", "wenku", "doc88", "docin"))
    ]
    found_fields = set()
    for result in official_results:
        extracted = result.get("extracted_fields") or {}
        found_fields.update(field for field in expected_fields if extracted.get(field))
    return {
        "id": case.get("id"),
        "official_hit": bool(official_results),
        "top3_official_hit": any(_is_official(str(result.get("url", "")), official_domains) for result in top3),
        "field_recall": len(found_fields) / len(expected_fields) if expected_fields else 1.0,
        "low_quality_rate": len(low_quality_results) / len(results) if results else 0.0,
        "result_count": len(results),
    }


def evaluate(cases: list[dict]) -> dict:
    case_results = [_evaluate_case(case) for case in cases]
    count = len(case_results) or 1
    return {
        "case_count": len(case_results),
        "official_hit_rate": sum(1 for item in case_results if item["official_hit"]) / count,
        "top3_official_hit_rate": sum(1 for item in case_results if item["top3_official_hit"]) / count,
        "avg_field_recall": sum(float(item["field_recall"]) for item in case_results) / count,
        "avg_low_quality_rate": sum(float(item["low_quality_rate"]) for item in case_results) / count,
        "cases": case_results,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _live_search_cases(cases: list[dict], *, max_results: int) -> list[dict]:
    """Replace fixture results with real web_search output for smoke evaluation.

    Live search validates source ranking and official-hit behavior. Field
    extraction is intentionally skipped because this script does not fetch and
    extract every returned page.
    """
    repo_root = _repo_root()
    harness_path = repo_root / "backend" / "packages" / "harness"
    if str(harness_path) not in sys.path:
        sys.path.insert(0, str(harness_path))

    from deerflow.community.hybrid_search.tools import web_search_tool

    live_cases = []
    for case in cases:
        response = web_search_tool.invoke({"query": str(case.get("query", "")), "max_results": max_results})
        payload = json.loads(response)
        live_case = dict(case)
        expected = dict(live_case.get("expected") or {})
        expected["fields"] = []
        live_case["expected"] = expected
        live_case["results"] = list(payload.get("results") or [])
        live_case["live_diagnostics"] = payload.get("diagnostics", [])
        live_cases.append(live_case)
    return live_cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate government-project web search quality cases.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("backend/tests/evals/search_cases.yaml"),
        help="YAML file containing search quality cases.",
    )
    parser.add_argument("--live", action="store_true", help="Call the configured web_search tool instead of using fixture results.")
    parser.add_argument("--max-results", type=int, default=5, help="Maximum results per live web_search call.")
    parser.add_argument("--min-official-hit-rate", type=float, default=1.0)
    parser.add_argument("--min-top3-official-hit-rate", type=float, default=1.0)
    parser.add_argument("--min-field-recall", type=float, default=0.8)
    args = parser.parse_args()

    data = yaml.safe_load(args.cases.read_text(encoding="utf-8")) or {}
    cases = list(data.get("cases") or [])
    if args.live:
        cases = _live_search_cases(cases, max_results=args.max_results)
    summary = evaluate(cases)
    if args.live:
        summary["live"] = True
        summary["field_recall_note"] = "Skipped in --live mode; live smoke test evaluates source ranking only."
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["official_hit_rate"] < args.min_official_hit_rate:
        return 1
    if summary["top3_official_hit_rate"] < args.min_top3_official_hit_rate:
        return 1
    if not args.live and summary["avg_field_recall"] < args.min_field_recall:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
