"""Tests for the Runtime Steering intervention store (S17-R1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hancode.core.errors import HanCodeError
from hancode.core.interventions import InterventionStatus
from hancode.storage.interventions import InterventionStore
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _make_task(tmp_path: Path) -> Path:
    init_project_workspace(tmp_path, "project-001", "AI4SE", "Harness")
    init_task_workspace(tmp_path, "task-042", goal="Steer me.")
    return tmp_path


def test_submit_assigns_task_global_increasing_sequence(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)

    first = store.submit("task-042", "run-a", "Do not modify the database layer.")
    second = store.submit("task-042", "run-a", "Only change API validation.")

    assert first.sequence == 1
    assert second.sequence == 2
    assert first.intervention_id == "iv-000001"
    assert second.intervention_id == "iv-000002"
    assert first.status is InterventionStatus.PENDING
    assert second.status is InterventionStatus.PENDING


def test_new_store_instance_replays_persisted_events(tmp_path: Path) -> None:
    _make_task(tmp_path)
    InterventionStore(tmp_path).submit("task-042", "run-a", "First requirement.")
    InterventionStore(tmp_path).submit("task-042", "run-a", "Second requirement.")

    reopened = InterventionStore(tmp_path)
    snapshot = reopened.prepare_context("task-042", "run-a")

    assert snapshot.revision == 2
    assert [record.sequence for record in snapshot.effective_records] == [1, 2]
    assert all(
        record.status is InterventionStatus.PENDING
        for record in snapshot.effective_records
    )


def test_multiple_store_instances_share_path_lock(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store_a = InterventionStore(tmp_path)
    store_b = InterventionStore(tmp_path)

    from hancode.storage.interventions import _lock_for

    path = tmp_path / ".hancode" / "tasks" / "task-042" / "interventions.jsonl"
    assert _lock_for(path) is _lock_for(path)

    store_a.submit("task-042", "run-a", "One.")
    store_b.submit("task-042", "run-a", "Two.")
    assert store_a.current_revision("task-042") == 2


def test_submit_redacts_secret_content(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)

    record = store.submit(
        "task-042", "run-a", "Use API_KEY=sk-supersecretvalue for the call."
    )

    assert "sk-supersecretvalue" not in record.content
    assert "[REDACTED]" in record.content


def test_submit_rejects_only_sensitive_content(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)

    with pytest.raises(HanCodeError) as exc:
        store.submit("task-042", "run-a", "sk-abcdefghijklmnopqrstuvwxyz")

    assert (
        exc.value.structured_error.error_code
        == "intervention_content_contains_only_sensitive_content"
    )


def test_corrupt_log_fails_closed(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Valid requirement.")

    log_path = tmp_path / ".hancode" / "tasks" / "task-042" / "interventions.jsonl"
    log_path.write_text("this is not json\n", encoding="utf-8")

    with pytest.raises(HanCodeError) as exc:
        store.current_revision("task-042")
    assert exc.value.structured_error.error_code == "intervention_log_corrupt"


def test_mark_delivered_is_idempotent(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Requirement one.")

    snapshot = store.prepare_context("task-042", "run-a")
    first = store.mark_delivered(
        "task-042", "run-a", snapshot.revision, snapshot.delivery_sequences
    )
    second = store.mark_delivered(
        "task-042", "run-a", snapshot.revision, snapshot.delivery_sequences
    )

    assert first.status.value == "delivered"
    assert second.status.value == "delivered"
    # No extra events beyond one submitted + one delivered.
    log_path = tmp_path / ".hancode" / "tasks" / "task-042" / "interventions.jsonl"
    assert len(log_path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_mark_delivered_detects_stale_revision(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Requirement one.")
    snapshot = store.prepare_context("task-042", "run-a")
    store.submit("task-042", "run-a", "A newer requirement raises the revision.")

    result = store.mark_delivered(
        "task-042", "run-a", snapshot.revision, snapshot.delivery_sequences
    )

    assert result.status.value == "stale"
    assert result.current_revision == 2


def test_consumed_replays_and_stays_effective(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-a", "Persisting requirement.")
    snapshot = store.prepare_context("task-042", "run-a")
    store.mark_delivered(
        "task-042", "run-a", snapshot.revision, snapshot.delivery_sequences
    )
    store.mark_consumed("task-042", "run-a", (1,))

    reopened = InterventionStore(tmp_path)
    snapshot = reopened.prepare_context("task-042", "run-a")

    assert len(snapshot.effective_records) == 1
    assert snapshot.effective_records[0].status is InterventionStatus.CONSUMED


def test_prepare_context_isolates_runs(tmp_path: Path) -> None:
    _make_task(tmp_path)
    store = InterventionStore(tmp_path)
    store.submit("task-042", "run-old", "Old run requirement.")
    store.submit("task-042", "run-new", "New run requirement.")

    snapshot = store.prepare_context("task-042", "run-new")

    assert [record.run_id for record in snapshot.effective_records] == ["run-new"]
    # Sequence space is task-global even though context is run-scoped.
    assert snapshot.effective_records[0].sequence == 2
    assert snapshot.revision == 2
