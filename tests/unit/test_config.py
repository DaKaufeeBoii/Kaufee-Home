"""Unit tests for configuration loading and validation."""

import os
from pathlib import Path
from kaufee.config import KaufeeConfig


def test_default_config(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path)
    assert cfg.workspace_root == tmp_path
    assert cfg.llm_provider == "ollama"
    assert cfg.max_steps == 12
    assert cfg.max_repairs == 3
    assert cfg.require_approval_for_delete is True
    assert cfg.allow_arbitrary_shell is False


def test_load_from_env_vars(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("KAUFEE_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("KAUFEE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("KAUFEE_MAX_STEPS", "8")
    monkeypatch.setenv("KAUFEE_MAX_REPAIRS", "2")
    monkeypatch.setenv("KAUFEE_REQUIRE_APPROVAL_FOR_DELETE", "false")
    monkeypatch.setenv("KAUFEE_OLLAMA_KEEP_ALIVE", "3m")
    monkeypatch.setenv("KAUFEE_OLLAMA_NUM_PREDICT", "1024")

    cfg = KaufeeConfig.load()
    assert cfg.workspace_root == tmp_path.resolve()
    assert cfg.llm_provider == "mock"
    assert cfg.max_steps == 8
    assert cfg.max_repairs == 2
    assert cfg.require_approval_for_delete is False
    assert cfg.ollama_keep_alive == "3m"
    assert cfg.ollama_num_predict == 1024


def test_load_from_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KAUFEE_WORKSPACE=./custom_ws\n"
        "KAUFEE_LLM_PROVIDER=remote\n"
        "REMOTE_MODEL=gpt-4o\n"
        "KAUFEE_STEP_TIMEOUT=30\n",
        encoding="utf-8",
    )
    cfg = KaufeeConfig.load(env_file=env_file)
    assert cfg.llm_provider == "remote"
    assert cfg.remote_model == "gpt-4o"
    assert cfg.step_timeout == 30
