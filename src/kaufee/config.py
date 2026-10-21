"""Configuration management for Kaufee-Home."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


def _read_env_file(env_path: Path) -> dict[str, str]:
    """Parse a simple .env file without external dependencies."""
    env_vars: dict[str, str] = {}
    if not env_path.is_file():
        return env_vars
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    env_vars[key] = val
    except Exception:
        pass
    return env_vars


class KaufeeConfig(BaseModel):
    """Runtime configuration for Kaufee-Home."""

    # Workspace
    workspace_root: Path = Field(
        default_factory=lambda: Path("./workspace").resolve(),
        description="Designated root directory where the agent can read and write files.",
    )

    # LLM Settings
    llm_provider: str = Field(
        default="ollama",
        description="LLM provider: 'ollama', 'remote', or 'mock'.",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for the local Ollama instance.",
    )
    ollama_model: str = Field(
        default="qwen2.5-coder:7b",
        description="Model name to use with Ollama.",
    )
    ollama_keep_alive: str = Field(
        default="10m",
        description="How long Ollama keeps the selected model loaded after a request.",
    )
    ollama_num_predict: int = Field(
        default=2048,
        ge=256,
        le=8192,
        description="Maximum generated tokens per Ollama response.",
    )
    remote_api_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for remote OpenAI-compatible API.",
    )
    remote_api_key: Optional[str] = Field(
        default=None,
        description="API key for remote provider.",
    )
    remote_model: str = Field(
        default="gpt-4o-mini",
        description="Model name for remote provider.",
    )

    # Execution limits
    max_steps: int = Field(
        default=12,
        ge=1,
        le=50,
        description="Maximum execution steps per task.",
    )
    max_repairs: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum bounded repair attempts on failure.",
    )
    step_timeout: int = Field(
        default=15,
        ge=1,
        le=120,
        description="Timeout in seconds for external process execution.",
    )
    max_output_bytes: int = Field(
        default=50000,
        description="Maximum bytes captured from command or file output.",
    )

    # Safety
    require_approval_for_delete: bool = Field(
        default=True,
        description="Require explicit user approval before deleting workspace files.",
    )
    require_approval_for_install: bool = Field(
        default=True,
        description="Require explicit approval before package installation.",
    )
    allow_arbitrary_shell: bool = Field(
        default=False,
        description="Whether arbitrary shell commands are allowed (disabled by default).",
    )

    # Storage and Audit
    audit_dir: Path = Field(
        default_factory=lambda: Path("./.kaufee/audit").resolve(),
        description="Directory where structured audit logs are persisted.",
    )
    backup_dir: Path = Field(
        default_factory=lambda: Path("./.kaufee/backups").resolve(),
        description="Directory where file backups and snapshots are preserved.",
    )

    @classmethod
    def load(
        cls,
        env_file: Optional[Path | str] = None,
        workspace: Optional[Path | str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> KaufeeConfig:
        """Load configuration from environment, .env file, and explicit overrides."""
        # Check standard .env locations
        env_dict: dict[str, str] = {}
        target_env = Path(env_file) if env_file else Path(".env")
        if target_env.exists():
            env_dict.update(_read_env_file(target_env))

        def get_val(key: str, default: Optional[str] = None) -> Optional[str]:
            return os.environ.get(key, env_dict.get(key, default))

        ws_str = workspace or get_val("KAUFEE_WORKSPACE", "./workspace")
        ws_path = Path(ws_str).resolve()

        chosen_provider = provider or get_val("KAUFEE_LLM_PROVIDER", "ollama")

        ollama_url = get_val("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_keep_alive = get_val("KAUFEE_OLLAMA_KEEP_ALIVE", "10m")
        ollama_num_predict = int(get_val("KAUFEE_OLLAMA_NUM_PREDICT", "2048"))
        ollama_mdl = (
            model if chosen_provider == "ollama" and model else get_val("OLLAMA_MODEL", "qwen2.5-coder:7b")
        )

        remote_url = get_val("REMOTE_API_BASE_URL", "https://api.openai.com/v1")
        remote_key = get_val("REMOTE_API_KEY", None)
        remote_mdl = (
            model if chosen_provider == "remote" and model else get_val("REMOTE_MODEL", "gpt-4o-mini")
        )

        max_steps = int(get_val("KAUFEE_MAX_STEPS", "12"))
        max_repairs = int(get_val("KAUFEE_MAX_REPAIRS", "3"))
        step_timeout = int(get_val("KAUFEE_STEP_TIMEOUT", "15"))
        max_out_bytes = int(get_val("KAUFEE_MAX_OUTPUT_BYTES", "50000"))

        req_del_appr = get_val("KAUFEE_REQUIRE_APPROVAL_FOR_DELETE", "true").lower() in ("1", "true", "yes")
        req_inst_appr = get_val("KAUFEE_REQUIRE_APPROVAL_FOR_INSTALL", "true").lower() in ("1", "true", "yes")
        allow_shell = get_val("KAUFEE_ALLOW_ARBITRARY_SHELL", "false").lower() in ("1", "true", "yes")

        audit_dir_str = get_val("KAUFEE_AUDIT_LOG_DIR", "./.kaufee/audit")
        audit_path = Path(audit_dir_str).resolve()
        backup_path = Path("./.kaufee/backups").resolve()

        return cls(
            workspace_root=ws_path,
            llm_provider=chosen_provider,
            ollama_base_url=ollama_url,
            ollama_model=ollama_mdl,
            ollama_keep_alive=ollama_keep_alive,
            ollama_num_predict=ollama_num_predict,
            remote_api_base_url=remote_url,
            remote_api_key=remote_key,
            remote_model=remote_mdl,
            max_steps=max_steps,
            max_repairs=max_repairs,
            step_timeout=step_timeout,
            max_output_bytes=max_out_bytes,
            require_approval_for_delete=req_del_appr,
            require_approval_for_install=req_inst_appr,
            allow_arbitrary_shell=allow_shell,
            audit_dir=audit_path,
            backup_dir=backup_path,
        )
