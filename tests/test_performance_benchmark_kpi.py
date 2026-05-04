import importlib.util
from pathlib import Path


def _load_benchmark_module():
    module_path = Path(__file__).parent / "performance_benchmark.py"
    spec = importlib.util.spec_from_file_location("performance_benchmark_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_kpi_uses_explicit_goal_when_set(monkeypatch):
    bench = _load_benchmark_module()
    monkeypatch.setenv("BENCHMARK_GOAL_SECONDS", "2.0")
    monkeypatch.delenv("BENCHMARK_PREVIOUS_SECONDS", raising=False)
    monkeypatch.delenv("BENCHMARK_REGRESSION_TOLERANCE", raising=False)

    status, passed = bench.evaluate_kpi_status(2.5)

    assert passed is False
    assert "Goal: 2.0s" in status


def test_kpi_passes_when_better_than_previous_without_goal(monkeypatch):
    bench = _load_benchmark_module()
    monkeypatch.delenv("BENCHMARK_GOAL_SECONDS", raising=False)
    monkeypatch.setenv("BENCHMARK_PREVIOUS_SECONDS", "3.72")
    monkeypatch.setenv("BENCHMARK_REGRESSION_TOLERANCE", "0.10")

    status, passed = bench.evaluate_kpi_status(2.5)

    assert passed is True
    assert "Baseline: 3.72s" in status


def test_kpi_fails_on_regression_without_goal(monkeypatch):
    bench = _load_benchmark_module()
    monkeypatch.delenv("BENCHMARK_GOAL_SECONDS", raising=False)
    monkeypatch.setenv("BENCHMARK_PREVIOUS_SECONDS", "3.72")
    monkeypatch.setenv("BENCHMARK_REGRESSION_TOLERANCE", "0.10")

    status, passed = bench.evaluate_kpi_status(4.3)

    assert passed is False
    assert "Threshold" in status
