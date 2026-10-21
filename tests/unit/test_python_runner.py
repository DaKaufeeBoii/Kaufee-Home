"""Unit tests for Python process execution tool."""

from pathlib import Path
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
