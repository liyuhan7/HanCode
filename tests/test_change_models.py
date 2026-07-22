"""Tests for core/change_models.py — S4-R1 domain models."""

from __future__ import annotations

from dataclasses import asdict
import pytest

from hancode.core.change_models import (
    ChangeType,
    CheckpointSummary,
    DiffScope,
    FileDiff,
    TaskDiff,
)
from hancode.core.models import Phase


class TestChangeType:
    def test_change_type_has_three_values(self) -> None:
        assert {member.value for member in ChangeType} == {"created", "modified", "deleted"}

    def test_change_type_from_string(self) -> None:
        assert ChangeType("created") is ChangeType.CREATED
        assert ChangeType("modified") is ChangeType.MODIFIED
        assert ChangeType("deleted") is ChangeType.DELETED


class TestDiffScope:
    def test_diff_scope_has_two_values(self) -> None:
        assert {member.value for member in DiffScope} == {"latest", "task"}


class TestFileDiff:
    def test_file_diff_is_frozen(self) -> None:
        diff = FileDiff(
            path="src/main.py",
            change_type=ChangeType.MODIFIED,
            before_sha256="abc123",
            current_sha256="def456",
            binary=False,
            drifted=False,
            unified_diff="--- a\n+++ b\n",
            truncated=False,
        )
        with pytest.raises(Exception):
            diff.path = "other.py"  # type: ignore[misc]

    def test_file_diff_created_file_has_no_before(self) -> None:
        diff = FileDiff(
            path="src/new.py",
            change_type=ChangeType.CREATED,
            before_sha256=None,
            current_sha256="abc123",
            binary=False,
            drifted=False,
            unified_diff=None,
            truncated=False,
        )
        assert diff.before_sha256 is None
        assert diff.unified_diff is None

    def test_file_diff_binary_marks_binary(self) -> None:
        diff = FileDiff(
            path="img.png",
            change_type=ChangeType.MODIFIED,
            before_sha256="abc",
            current_sha256="def",
            binary=True,
            drifted=False,
            unified_diff=None,
            truncated=False,
        )
        assert diff.binary is True
        assert diff.unified_diff is None

    def test_file_diff_drifted_flag(self) -> None:
        diff = FileDiff(
            path="src/main.py",
            change_type=ChangeType.MODIFIED,
            before_sha256="abc",
            current_sha256="def",
            binary=False,
            drifted=True,
            unified_diff="...",
            truncated=False,
        )
        assert diff.drifted is True


class TestTaskDiff:
    def test_task_diff_holds_scope(self) -> None:
        diff = TaskDiff(
            task_id="task-001",
            scope=DiffScope.TASK,
            checkpoint_ids=("ckpt-001",),
            files=(),
            truncated=False,
            risks=(),
        )
        assert diff.scope is DiffScope.TASK

    def test_task_diff_truncated_flag(self) -> None:
        diff = TaskDiff(
            task_id="task-001",
            scope=DiffScope.LATEST,
            checkpoint_ids=(),
            files=(),
            truncated=True,
            risks=("diff_output_truncated",),
        )
        assert diff.truncated is True
        assert "diff_output_truncated" in diff.risks

    def test_task_diff_with_files(self) -> None:
        file_diff = FileDiff(
            path="src/a.py",
            change_type=ChangeType.MODIFIED,
            before_sha256="aaa",
            current_sha256="bbb",
            binary=False,
            drifted=False,
            unified_diff="...",
            truncated=False,
        )
        task_diff = TaskDiff(
            task_id="task-002",
            scope=DiffScope.TASK,
            checkpoint_ids=("ckpt-001", "ckpt-002"),
            files=(file_diff,),
            truncated=False,
            risks=(),
        )
        assert len(task_diff.files) == 1
        assert task_diff.checkpoint_ids == ("ckpt-001", "ckpt-002")


class TestCheckpointSummary:
    def test_checkpoint_summary_does_not_expose_absolute_paths(self) -> None:
        summary = CheckpointSummary(
            checkpoint_id="ckpt-001",
            phase=Phase.CODE,
            reason="Fix validation.",
            created_at="2026-07-21T00:00:00+00:00",
            status="committed",
            files=("src/main.py",),
            rollback_available=True,
        )
        data = asdict(summary)
        for val in data.values():
            if isinstance(val, str):
                assert "\\" not in val or "checkpoints" not in val.lower()

    def test_checkpoint_summary_hides_internal_paths_in_files(self) -> None:
        summary = CheckpointSummary(
            checkpoint_id="ckpt-002",
            phase=Phase.CODE,
            reason="Add feature.",
            created_at="2026-07-21T00:00:00+00:00",
            status="committed",
            files=("src/main.py", "tests/test_main.py"),
            rollback_available=False,
        )
        for f in summary.files:
            assert "before_snapshot" not in f
            assert "checkpoints" not in f.lower()
            assert not f.startswith("/")
