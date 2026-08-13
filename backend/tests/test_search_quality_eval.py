import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_evaluator():
    path = REPO_ROOT / "scripts" / "evaluate_search_quality.py"
    spec = importlib.util.spec_from_file_location("evaluate_search_quality", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_search_quality_eval_default_cases_pass_thresholds() -> None:
    evaluator = _load_evaluator()
    data = yaml.safe_load((REPO_ROOT / "backend/tests/evals/search_cases.yaml").read_text(encoding="utf-8"))
    summary = evaluator.evaluate(data["cases"])

    assert summary["case_count"] == 3
    assert summary["official_hit_rate"] == 1.0
    assert summary["top3_official_hit_rate"] == 1.0
    assert summary["avg_field_recall"] >= 0.8
    assert summary["avg_low_quality_rate"] < 0.5
