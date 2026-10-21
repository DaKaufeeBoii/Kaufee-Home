"""Unit tests for Python process execution tool."""

from pathlib import Path
import threading
import time
from kaufee.tools.python_runner import PythonRunnerTool


def test_python_runner_success(tmp_path: Path):
    runner = PythonRunnerTool()
    script = tmp_path / "hello.py"
    script.write_text("print('Hello from Python runner!')", encoding="utf-8")

    ok, output, meta = runner.run({"script_path": "hello.py"}, tmp_path)
    assert ok is True
    assert "Hello from Python runner!" in output
    assert meta["returncode"] == 0


def test_python_runner_inline_code(tmp_path: Path):
    runner = PythonRunnerTool()
    code = "import math\nprint(f'PI={math.pi:.2f}')"

    ok, output, meta = runner.run({"code": code}, tmp_path)
    assert ok is True
    assert "PI=3.14" in output
    assert meta["returncode"] == 0


def test_python_runner_supplies_test_input(tmp_path: Path):
    runner = PythonRunnerTool()
    script = tmp_path / "largest.py"
    script.write_text(
        "numbers = [int(value) for value in input().split()]\n"
        "print(max(numbers))\n",
        encoding="utf-8",
    )

    ok, output, metadata = runner.run(
        {"script_path": "largest.py", "stdin": "-4 12 3 8\n"}, tmp_path
    )
    assert ok
    assert output.strip() == "12"
    assert metadata["returncode"] == 0


def test_python_runner_runtime_error(tmp_path: Path):
    runner = PythonRunnerTool()
    script = tmp_path / "error.py"
    script.write_text("x = 1 / 0", encoding="utf-8")

    ok, output, meta = runner.run({"script_path": "error.py"}, tmp_path)
    assert ok is False
    assert "ZeroDivisionError" in output
    assert meta["returncode"] != 0


def test_python_runner_timeout(tmp_path: Path):
    runner = PythonRunnerTool(default_timeout=2)
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(5)", encoding="utf-8")

    ok, output, meta = runner.run({"script_path": "sleep.py", "timeout": 1}, tmp_path)
    assert ok is False
    assert "timed out" in output.lower()
    assert meta["returncode"] == -1


def test_python_runner_bounds_output(tmp_path: Path):
    runner = PythonRunnerTool(max_output_bytes=32)
    script = tmp_path / "noisy.py"
    script.write_text("print('x' * 1000000)", encoding="utf-8")

    ok, output, meta = runner.run({"script_path": "noisy.py"}, tmp_path)
    assert ok
    assert len(meta["stdout"].encode("utf-8")) < 100
    assert meta["output_truncated"] is True
    assert "truncated" in output


def test_python_runner_does_not_inherit_secrets(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KAUFEE_TEST_SECRET", "should-not-leak")
    runner = PythonRunnerTool()

    ok, output, _ = runner.run({"code": "import os; print(os.getenv('KAUFEE_TEST_SECRET', 'missing'))"}, tmp_path)
    assert ok
    assert output.strip() == "missing"
    assert not list((tmp_path / ".kaufee" / "tmp").glob("run_*.py"))


def test_python_runner_rejects_invalid_timeout_and_conflicting_sources(tmp_path: Path):
    runner = PythonRunnerTool()

    ok, output, _ = runner.run({"code": "print('x')", "timeout": 0}, tmp_path)
    assert not ok
    assert "positive integer" in output

    ok, output, _ = runner.run({"script_path": "missing.py", "code": "print('x')"}, tmp_path)
    assert not ok
    assert "exactly one" in output


def test_python_runner_stops_child_when_cancelled(tmp_path: Path):
    cancel = threading.Event()
    runner = PythonRunnerTool(default_timeout=10, cancellation_event=cancel)
    script = tmp_path / "wait.py"
    script.write_text("import time\ntime.sleep(10)", encoding="utf-8")
    outcome = {}

    thread = threading.Thread(
        target=lambda: outcome.setdefault(
            "result", runner.run({"script_path": "wait.py"}, tmp_path)
        )
    )
    thread.start()
    time.sleep(0.3)
    cancel.set()
    thread.join(timeout=3)

    assert not thread.is_alive()
    ok, output, metadata = outcome["result"]
    assert not ok
    assert "cancelled" in output.lower()
    assert metadata["cancelled"] is True
