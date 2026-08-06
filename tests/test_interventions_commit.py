"""Tests for revision linearization: commit_action + idempotency ledger (S17-R2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.core.errors import HanCodeError
from hancode.core.interventions import ActionCommitStatus, InterventionStatus
from hancode.storage.interventions import InterventionStore
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _make_task(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "AI4SE", "Harness")
    init_task_workspace(tmp_path, "task-042", goal="Steer me.")
    return tmp_path


def _delivered_snapshot(store: InterventionStore) -> object:
    snapshot = store.prepare_context("task-042", "run-a")
    if snapshot.delivery_sequences:
        store.mark_delivered(
            "task-042", "run-a", snapshot.revision, snapshot.delivery_sequences
        )
    return store.prepare_context("task-042", "run-a")


def test_commit_action_committed_when_revision_unchanged(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Only touch API validation.")
    snapshot = _delivered_snapshot(store)

    result = store.commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="run-a:step-1:digest-1",
        acknowledge=True,
    )

    assert result.status is ActionCommitStatus.COMMITTED
    assert result.current_revision == snapshot.revision
    # acknowledge marked the delivered steering CONSUMED, but it stays effective.
    after = store.prepare_context("task-042", "run-a")
    assert after.effective_records[0].status is InterventionStatus.CONSUMED


def test_steering_before_commit_forces_replan(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "First requirement.")
    snapshot = _delivered_snapshot(store)
    # Steering arrives after the snapshot is taken: revision advances.
    store.submit("task-042", "run-a", "A newer requirement.")

    result = store.commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="run-a:step-1:digest-1",
        acknowledge=True,
    )

    assert result.status is ActionCommitStatus.REPLAN
    assert result.current_revision == 2
    # REPLAN must not consume the older steering.
    context = store.prepare_context("task-042", "run-a")
    assert context.effective_records[0].status is InterventionStatus.DELIVERED


def test_commit_action_is_idempotent_by_commit_key(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Requirement.")
    snapshot = _delivered_snapshot(store)

    first = store.commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="commit-key-1",
        acknowledge=True,
    )
    second = store.commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="commit-key-1",
        acknowledge=True,
    )

    assert first.status is second.status is ActionCommitStatus.COMMITTED
    ledger_path = tmp_path / ".hancode" / "tasks" / "task-042" / "action_commits.jsonl"
    # Only one ledger row despite the retry.
    assert len(ledger_path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_replan_not_acknowledged(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Requirement.")
    snapshot = _delivered_snapshot(store)
    store.submit("task-042", "run-a", "Newer requirement.")

    store.commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="commit-key-1",
        acknowledge=True,
    )

    # No CONSUMED event was written for the stale action.
    context = store.prepare_context("task-042", "run-a")
    assert all(
        record.status is not InterventionStatus.CONSUMED
        for record in context.effective_records
    )


def test_commit_action_shared_across_store_instances(tmp_path: Path) -> None:
    _make_task(tmp_path)
    writer = InterventionStore(tmp_path)
    writer.submit("task-042", "run-a", "Requirement.")
    snapshot = _delivered_snapshot(writer)

    InterventionStore(tmp_path).commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="commit-key-1",
        acknowledge=True,
    )
    # A fresh instance sees the ledger and returns the first result.
    replay = InterventionStore(tmp_path).commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="commit-key-1",
        acknowledge=True,
    )
    assert replay.status is ActionCommitStatus.COMMITTED


def test_corrupt_ledger_fails_closed(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Requirement.")
    snapshot = _delivered_snapshot(store)
    store.commit_action(
        "task-042",
        "run-a",
        expected_revision=snapshot.revision,
        delivery_sequences=snapshot.delivery_sequences,
        action_digest="digest-1",
        commit_key="commit-key-1",
        acknowledge=False,
    )

    ledger_path = tmp_path / ".hancode" / "tasks" / "task-042" / "action_commits.jsonl"
    ledger_path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc:
        store.commit_action(
            "task-042",
            "run-a",
            expected_revision=snapshot.revision,
            delivery_sequences=snapshot.delivery_sequences,
            action_digest="digest-2",
            commit_key="commit-key-2",
            acknowledge=False,
        )
    assert (
        exc.value.structured_error.error_code
        == "intervention_commit_ledger_corrupt"
    )


def test_commit_key_required(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    with pytest.raises(HanCodeError) as exc:
        store.commit_action(
            "task-042",
            "run-a",
            expected_revision=0,
            delivery_sequences=(),
            action_digest="digest-1",
            commit_key="",
            acknowledge=False,
        )
    assert (
        exc.value.structured_error.error_code == "intervention_commit_key_required"
    )
