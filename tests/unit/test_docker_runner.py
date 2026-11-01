"""Unit tests for Docker sandboxing runner and pluggable execution backends."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from kaufee.tools.python_runner import PythonRunnerTool
from kaufee.tools.runner_base import DockerRunner, SubprocessRunner


def test_runner_backends_availability():
    sub = SubprocessRunner()
    assert sub.name == "subprocess"
    assert sub.is_available() is True

    dock = DockerRunner()
    assert dock.name == "docker"
    assert dock.image == "python:3.11-slim"
    assert dock.memory_limit == "512m"


def test_python_runner_runner_type_selection():
    # Force subprocess
    tool_sub = PythonRunnerTool(runner_type="subprocess")
    assert isinstance(tool_sub.runner, SubprocessRunner)

    # Auto fallback when docker daemon is not running
    with patch.object(DockerRunner, "is_available", return_value=False):
        tool_auto = PythonRunnerTool(runner_type="auto")
        assert isinstance(tool_auto.runner, SubprocessRunner)

    # Auto selects docker when available
    with patch.object(DockerRunner, "is_available", return_value=True):
        tool_docker = PythonRunnerTool(runner_type="auto")
        assert isinstance(tool_docker.runner, DockerRunner)


def test_docker_runner_command_construction(tmp_path: Path):
    runner = DockerRunner(image="python:3.11-slim", memory_limit="256m", cpus="0.5")
    test_script = tmp_path / "hello.py"
    test_script.write_text("print('hello from sandbox')", encoding="utf-8")

    # Mock is_available to True
    with patch.object(runner, "is_available", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.returncode = 0
            mock_proc.stdout.read.side_effect = [b"hello from sandbox", b""]
            mock_proc.stderr.read.side_effect = [b""]
            mock_popen.return_value = mock_proc

            success, output, meta = runner.execute(
                exec_target=test_script,
                cli_args=["--verbose"],
                workspace=tmp_path,
                stdin_text=None,
                timeout=10,
                max_output_bytes=50000,
                cancellation_event=MagicMock(),
            )

            assert mock_popen.called
            called_cmd = mock_popen.call_args[0][0]
            assert called_cmd[0] == "docker"
            assert "run" in called_cmd
            assert "--network" in called_cmd
            assert "none" in called_cmd
            assert "--memory" in called_cmd
            assert "256m" in called_cmd
            assert "--cpus" in called_cmd
            assert "0.5" in called_cmd
            assert f"{tmp_path.resolve()}:/workspace" in called_cmd
            assert "hello.py" in called_cmd
            assert "--verbose" in called_cmd
            assert meta["runner"] == "docker"


def test_docker_runner_windows_daemon_detection():
    dock = DockerRunner(image="python:3.11-slim")
    mock_docker_info = "Containers: 0\nOSType: windows\nArchitecture: x86_64\n"
    with patch("shutil.which", return_value="docker"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_docker_info)
            assert dock.is_available() is False

    dock_linux = DockerRunner(image="python:3.11-slim")
    mock_docker_info_linux = "Containers: 0\nOSType: linux\nArchitecture: x86_64\n"
    with patch("platform.system", return_value="Linux"):
        with patch("shutil.which", return_value="docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_docker_info_linux)
                assert dock_linux.is_available() is True

