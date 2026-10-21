"""Persistence store for task state and execution history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from kaufee.state.models import TaskState


class StateStore:
    """Stores and retrieves task state files from disk."""

    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: TaskState) -> Path:
        """Persist task state to JSON file."""
        target_path = self.store_dir / f"{state.task_id}.state.json"
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))
        return target_path

    def load(self, task_id: str) -> Optional[TaskState]:
        """Load task state from JSON file."""
        target_path = self.store_dir / f"{task_id}.state.json"
        if not target_path.is_file():
            # Check without suffix if full path or partial
            candidates = list(self.store_dir.glob(f"*{task_id}*.state.json"))
            if not candidates:
                return None
            target_path = candidates[0]
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return TaskState(**data)
        except Exception:
            return None

    def list_tasks(self) -> list[dict[str, str]]:
        """List all persisted tasks."""
        results = []
        for p in sorted(self.store_dir.glob("*.state.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append({
                        "task_id": data.get("task_id", p.stem),
                        "goal": data.get("goal", ""),
                        "status": data.get("status", ""),
                        "created_at": data.get("created_at", ""),
                        "completed_at": data.get("completed_at", ""),
                    })
            except Exception:
                pass
        return results
