"""Tests for tooling/diff_tools.py — S4-R1 get_diff tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.core.change_models import ChangeType, DiffScope, TaskDiff
from hancode.core.models import Phase
from hancode.storage.checkpoint_queries import CheckpointQueryRepository
from hancode.storage.workspace import init_project_workspace, init_task_workspace
from hancode.tooling.diff_tools import get_diff


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_manifest(checkpoint_dir: Path, **overrides: object) -> dict:
    """Write a manifest and snapshot, return the manifest dict."""
    import hashlib
    files_dir = checkpoint_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "schema_version": 1,
        "project_id": "proj-001",
        "checkpoint_id": checkpoint_dir.name,
        "task_id": "task-001",
        "phase": "code",
        "reason": "Test checkpoint.",
        "created_at": "2026-07-21T00:00:00+00:00",
        "status": "committed",
        "files": [],
        "rollback_available": True,
    }
    manifest.update(overrides)

    for f in manifest["files"]:
        if f.get("action") == "modify" and f.get("before_snapshot"):
            content = f.get("_content", b"original content\n")
            snapshot_path = checkpoint_dir / f["before_snapshot"]
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_bytes(content)
            f["before_sha256"] = hashlib.sha256(content).hexdigest()
            f.pop("_content", None)

    (checkpoint_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _write_source(project_root: Path, rel_path: str, content: str) -> None:
    target = project_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _make_checkpoint(task_root: Path, cid: str) -> Path:
    ckpt_dir = task_root / "checkpoints" / cid
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    return ckpt_dir


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestGetDiffModifiedFile:
    def test_diff_modified_file(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # Write original source
        _write_source(project_root, "src/main.py", "original\n")

        # Create checkpoint with before snapshot
        ckpt_dir = _make_checkpoint(task_root, "ckpt-001")
        _write_manifest(
            ckpt_dir,
            files=[
                {
                    "path": "src/main.py",
                    "action": "modify",
                    "before_snapshot": "files/001-main.before",
                    "before_sha256": None,
                    "after_sha256": None,
                    "_content": b"original\n",
                }
            ],
        )

        # Modify source
        _write_source(project_root, "src/main.py", "modified\n")

        diff_result = get_diff(project_root, task_root, scope="task")

        assert diff_result.success is True
        assert isinstance(diff_result.output, dict)
        assert diff_result.output["task_id"] == "task-001"
        assert diff_result.output["scope"] == "task"
        assert len(diff_result.output["files"]) == 1
        f = diff_result.output["files"][0]
        assert f["path"] == "src/main.py"
        assert f["change_type"] == "modified"
        assert f["unified_diff"] is not None
        assert "-original" in f["unified_diff"]
        assert "+modified" in f["unified_diff"]


class TestGetDiffCreatedFile:
    def test_diff_created_file(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # Create checkpoint for a file being created
        ckpt_dir = _make_checkpoint(task_root, "ckpt-001")
        _write_manifest(
            ckpt_dir,
            files=[
                {
                    "path": "src/new.py",
                    "action": "create",
                    "before_snapshot": None,
                    "before_sha256": None,
                    "after_sha256": None,
                }
            ],
            rollback_available=False,
        )

        # Write the new source
        _write_source(project_root, "src/new.py", "new content\n")

        diff_result = get_diff(project_root, task_root, scope="task")

        assert diff_result.success is True
        assert len(diff_result.output["files"]) == 1
        f = diff_result.output["files"][0]
        assert f["path"] == "src/new.py"
        assert f["change_type"] == "created"
        assert f["before_sha256"] is None
        assert f["unified_diff"] is None  # created files have no unified diff


class TestGetDiffTaskBaseline:
    def test_task_diff_uses_earliest_baseline(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # First modification
        _write_source(project_root, "src/a.py", "v1\n")
        ckpt1 = _make_checkpoint(task_root, "ckpt-001")
        _write_manifest(
            ckpt1,
            files=[
                {
                    "path": "src/a.py",
                    "action": "modify",
                    "before_snapshot": "files/001-a.before",
                    "before_sha256": None,
                    "after_sha256": None,
                    "_content": b"v1\n",
                }
            ],
        )

        # Second modification (should NOT be used as baseline)
        _write_source(project_root, "src/a.py", "v2\n")
        ckpt2 = _make_checkpoint(task_root, "ckpt-002")
        _write_manifest(
            ckpt2,
            files=[
                {
                    "path": "src/a.py",
                    "action": "modify",
                    "before_snapshot": "files/001-a.before",
                    "before_sha256": None,
                    "after_sha256": None,
                    "_content": b"v2\n",
                }
            ],
        )

        # Current state
        _write_source(project_root, "src/a.py", "v3\n")

        diff_result = get_diff(project_root, task_root, scope="task")

        assert diff_result.success is True
        f = diff_result.output["files"][0]
        # Should use ckpt-001.before (v1) as baseline, not ckpt-002.before (v2)
        assert "-v1" in f["unified_diff"]
        assert "+v3" in f["unified_diff"]


class TestGetDiffLatest:
    def test_latest_diff_uses_latest_checkpoint(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # Simulate state with latest_checkpoint
        from hancode.core.state import load_state, save_state
        from dataclasses import replace
        state = load_state(task_root)
        state = replace(state, latest_checkpoint="ckpt-002")
        save_state(task_root, state)

        _write_source(project_root, "src/a.py", "v2\n")
        ckpt2 = _make_checkpoint(task_root, "ckpt-002")
        _write_manifest(
            ckpt2,
            files=[
                {
                    "path": "src/a.py",
                    "action": "modify",
                    "before_snapshot": "files/001-a.before",
                    "before_sha256": None,
                    "after_sha256": None,
                    "_content": b"v2\n",
                }
            ],
        )

        _write_source(project_root, "src/a.py", "v3\n")

        diff_result = get_diff(project_root, task_root, scope="latest")

        assert diff_result.success is True
        assert diff_result.output["scope"] == "latest"
        f = diff_result.output["files"][0]
        assert "-v2" in f["unified_diff"]


class TestGetDiffDrift:
    def test_diff_marks_workspace_drift(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        original = b"original\n"
        _write_source(project_root, "src/a.py", original.decode())

        ckpt = _make_checkpoint(task_root, "ckpt-001")
        _write_manifest(
            ckpt,
            files=[
                {
                    "path": "src/a.py",
                    "action": "modify",
                    "before_snapshot": "files/001-a.before",
                    "before_sha256": None,
                    "after_sha256": "b" * 64,  # fake committed after hash
                    "_content": original,
                }
            ],
        )

        # Modify after checkpoint — this will cause drift
        _write_source(project_root, "src/a.py", "drifted content\n")

        diff_result = get_diff(project_root, task_root, scope="task")

        assert diff_result.success is True
        f = diff_result.output["files"][0]
        assert f["drifted"] is True


class TestGetDiffBounds:
    def test_diff_does_not_require_git(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        _write_source(project_root, "src/a.py", "original\n")
        ckpt = _make_checkpoint(task_root, "ckpt-001")
        _write_manifest(
            ckpt,
            files=[
                {
                    "path": "src/a.py",
                    "action": "modify",
                    "before_snapshot": "files/001-a.before",
                    "before_sha256": None,
                    "after_sha256": None,
                    "_content": b"original\n",
                }
            ],
        )
        _write_source(project_root, "src/a.py", "modified\n")

        # No .git directory
        diff_result = get_diff(project_root, task_root, scope="task")
        assert diff_result.success is True
        assert diff_result.output["files"][0]["unified_diff"] is not None

    def test_diff_skips_binary_content(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        binary_content = bytes(range(256))
        _write_source(project_root, "src/data.bin", binary_content.decode("latin-1"))

        ckpt = _make_checkpoint(task_root, "ckpt-001")
        _write_manifest(
            ckpt,
            files=[
                {
                    "path": "src/data.bin",
                    "action": "modify",
                    "before_snapshot": "files/001-data.before",
                    "before_sha256": None,
                    "after_sha256": None,
                    "_content": binary_content,
                }
            ],
        )

        diff_result = get_diff(project_root, task_root, scope="task")

        assert diff_result.success is True
        f = diff_result.output["files"][0]
        assert f["binary"] is True
        assert f["unified_diff"] is None


class TestGetDiffConfig:
    def test_diff_respects_max_diff_files(self, tmp_path: Path) -> None:
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # Create many modified files
        for i in range(5):
            _write_source(project_root, f"src/file_{i}.py", f"v{i}\n")

        ckpt = _make_checkpoint(task_root, "ckpt-001")
        files = []
        for i in range(5):
            files.append({
                "path": f"src/file_{i}.py",
                "action": "modify",
                "before_snapshot": f"files/{i:03d}-file{i}.before",
                "before_sha256": None,
                "after_sha256": None,
                "_content": f"v{i}\n".encode(),
            })
        _write_manifest(ckpt, files=files)

        for i in range(5):
            _write_source(project_root, f"src/file_{i}.py", f"new_v{i}\n")

        # With max_diff_files=2, should be truncated
        diff_result = get_diff(project_root, task_root, scope="task", max_diff_files=2)

        assert diff_result.success is True
        assert diff_result.output["truncated"] is True
        assert len(diff_result.output["files"]) <= 2
