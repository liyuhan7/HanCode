"""Tests for storage/checkpoint_queries.py — S4-R1 Checkpoint Query Repository."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.core.change_models import CheckpointSummary
from hancode.core.config import HanCodeConfig
from hancode.core.models import Phase
from hancode.storage.checkpoint_queries import CheckpointQueryRepository
from hancode.storage.workspace import init_project_workspace, init_task_workspace


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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

    # Only write snapshot for modify actions
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
        # fix sha to match actual content
        import hashlib
        actual_sha = hashlib.sha256(snapshot_data).hexdigest()
        first_file["before_sha256"] = actual_sha

    (checkpoint_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _make_checkpoint_dir(task_root: Path, checkpoint_id: str) -> Path:
    checkpoints_root = task_root / "checkpoints"
    checkpoints_root.mkdir(parents=True, exist_ok=True)
    ckpt_dir = checkpoints_root / checkpoint_id
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    return ckpt_dir


def _make_config(project_root: Path) -> HanCodeConfig:
    return HanCodeConfig(
        project_root=project_root.resolve(),
        hancode_root=project_root / ".hancode",
        allowed_workspace_root=project_root.resolve(),
        task_root=None,
        llm_provider="mock",
        model_name=None,
        credential_source=None,
        test_command=None,
        build_command=None,
        max_steps=30,
        retry_budget=2,
        max_checkpoints_per_task=5,
        max_observation_bytes=8192,
        max_context_chars=24000,
        max_trace_events=40,
        protected_patterns=(),
        writable_roots=(project_root.resolve(),),
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestCheckpointQueryRepositoryList:
    def test_list_returns_empty_for_no_checkpoints(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")
        manifests = repo.list(task_root)
        assert manifests == ()

    def test_list_returns_sorted_manifests(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        # Create ckpt-002 before ckpt-001 to test sorting
        for cid in ("ckpt-002", "ckpt-001", "ckpt-003"):
            ckpt_dir = _make_checkpoint_dir(task_root, cid)
            _write_minimal_manifest(
                ckpt_dir,
                checkpoint_id=cid,
                task_id="task-001",
            )

        manifests = repo.list(task_root)
        ids = [m.checkpoint_id for m in manifests]
        assert ids == ["ckpt-001", "ckpt-002", "ckpt-003"]

    def test_list_rejects_wrong_task_id(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(
            ckpt_dir,
            checkpoint_id="ckpt-001",
            task_id="task-002",  # wrong task
        )

        with pytest.raises(Exception):
            repo.list(task_root)

    def test_list_rejects_corrupt_manifest(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        (ckpt_dir / "manifest.json").write_text("not-json{{{", encoding="utf-8")

        with pytest.raises(Exception):
            repo.list(task_root)

    def test_list_rejects_symlink_manifest(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        real_manifest = ckpt_dir / "real.json"
        _write_minimal_manifest(ckpt_dir, checkpoint_id="ckpt-001", task_id="task-001")
        real_manifest.write_bytes((ckpt_dir / "manifest.json").read_bytes())
        (ckpt_dir / "manifest.json").unlink()
        try:
            (ckpt_dir / "manifest.json").symlink_to(real_manifest)
        except OSError:
            pytest.skip("Symlink not supported on this platform")

        with pytest.raises(Exception):
            repo.list(task_root)

    def test_list_accepts_committed_and_rolled_back(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        for cid, status in (("ckpt-001", "committed"), ("ckpt-002", "rolled_back")):
            ckpt_dir = _make_checkpoint_dir(task_root, cid)
            _write_minimal_manifest(
                ckpt_dir,
                checkpoint_id=cid,
                task_id="task-001",
                status=status,
                rollback_available=(status == "committed"),
            )

        manifests = repo.list(task_root)
        assert len(manifests) == 2


class TestCheckpointQueryRepositoryGet:
    def test_get_returns_manifest(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(ckpt_dir, checkpoint_id="ckpt-001", task_id="task-001")

        manifest = repo.get(task_root, "ckpt-001")
        assert manifest.checkpoint_id == "ckpt-001"
        assert manifest.task_id == "task-001"

    def test_get_raises_for_missing_checkpoint(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        with pytest.raises(Exception):
            repo.get(task_root, "ckpt-999")

    def test_get_rejects_invalid_checkpoint_id_format(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        with pytest.raises(Exception):
            repo.get(task_root, "../../etc/passwd")


class TestCheckpointQueryRepositoryReadBefore:
    def test_read_before_returns_snapshot_content(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(ckpt_dir, checkpoint_id="ckpt-001", task_id="task-001")

        content = repo.read_before(task_root, "ckpt-001", "src/main.py")
        assert content == b"before-content"

    def test_read_before_returns_none_for_created_file(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(
            ckpt_dir,
            checkpoint_id="ckpt-001",
            task_id="task-001",
            files=[
                {
                    "path": "src/new.py",
                    "action": "create",
                    "before_snapshot": None,
                    "before_sha256": None,
                    "after_sha256": None,
                },
            ],
            rollback_available=False,
        )

        content = repo.read_before(task_root, "ckpt-001", "src/new.py")
        assert content is None

    def test_read_before_rejects_snapshot_hash_mismatch(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(ckpt_dir, checkpoint_id="ckpt-001", task_id="task-001")
        # Tamper with the snapshot
        manifest = json.loads((ckpt_dir / "manifest.json").read_text("utf-8"))
        snapshot_path = ckpt_dir / manifest["files"][0]["before_snapshot"]
        snapshot_path.write_bytes(b"tampered-content")

        with pytest.raises(Exception):
            repo.read_before(task_root, "ckpt-001", "src/main.py")


class TestCheckpointSummaryConversion:
    def test_to_summary_hides_snapshot_paths(self, tmp_path: Path) -> None:
        repo = CheckpointQueryRepository()
        project_root = tmp_path / "proj"
        project_root.mkdir()
        init_project_workspace(project_root, "proj-001", "HanCode", "Test")
        task_root = init_task_workspace(project_root, "task-001")

        ckpt_dir = _make_checkpoint_dir(task_root, "ckpt-001")
        _write_minimal_manifest(ckpt_dir, checkpoint_id="ckpt-001", task_id="task-001")

        manifest = repo.get(task_root, "ckpt-001")
        summary = CheckpointSummary(
            checkpoint_id=manifest.checkpoint_id,
            phase=manifest.phase,
            reason=manifest.reason,
            created_at=manifest.created_at.isoformat(),
            status=manifest.status,
            files=tuple(f.path for f in manifest.files),
            rollback_available=manifest.rollback_available,
        )
        # Must not leak internal paths
        for f in summary.files:
            assert "before_snapshot" not in f
            assert "checkpoints" not in f.lower()
            assert not f.startswith("/")
