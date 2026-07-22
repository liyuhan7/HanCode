"""Shared checkpoint manifest helpers for checkpoint query and S4 tool tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _write_minimal_manifest(checkpoint_dir: Path, **overrides: object) -> None:
    manifest = {
        "schema_version": 1,
        "project_id": "proj-001",
        "checkpoint_id": checkpoint_dir.name,
        "task_id": "task-001",
        "phase": "code",
        "reason": "Add validation.",
        "created_at": "2026-07-21T00:00:00+00:00",
        "status": "committed",
        "files": [
            {
                "path": "src/main.py",
                "action": "modify",
                "before_snapshot": "files/001-abc123def456.before",
                "before_sha256": "a" * 64,
                "after_sha256": "b" * 64,
            },
        ],
        "rollback_available": True,
    }
    manifest.update(overrides)
    (checkpoint_dir / "files").mkdir(parents=True, exist_ok=True)

    first_file = manifest["files"][0]
    if (
        isinstance(first_file, dict)
        and first_file.get("action") == "modify"
        and isinstance(first_file.get("before_snapshot"), str)
    ):
        snapshot_data = b"before-content"
        snapshot_path = checkpoint_dir / first_file["before_snapshot"]
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(snapshot_data)
        actual_sha = hashlib.sha256(snapshot_data).hexdigest()
        first_file["before_sha256"] = actual_sha

    (checkpoint_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _make_checkpoint_dir(task_root: Path, checkpoint_id: str) -> Path:
    checkpoints_root = task_root / "checkpoints"
    checkpoints_root.mkdir(parents=True, exist_ok=True)
    ckpt_dir = checkpoints_root / checkpoint_id
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    return ckpt_dir
