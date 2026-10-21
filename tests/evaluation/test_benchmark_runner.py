"""Pytest test case executing the full 20-task evaluation benchmark."""

from pathlib import Path
from kaufee.evaluation.benchmark import run_full_benchmark


def test_full_evaluation_benchmark_suite(tmp_path: Path):
    """Run all 20 benchmark tasks and assert benchmark thresholds."""
    report = run_full_benchmark(workspace_override=tmp_path / "benchmarks")

    assert report.total_tasks == 20
    assert report.passed_tasks == 20
    assert report.task_success_rate == 100.0
    assert report.safety_violations_count == 0
    assert report.median_latency_ms > 0
