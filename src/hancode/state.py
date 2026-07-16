from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
from tempfile import mkstemp
from types import MappingProxyType
from typing import Mapping, TypeGuard

from hancode.errors import HanCodeError, StructuredError
from hancode.models import Phase, TaskStatus


_STATE_FIELDS = frozenset(
    {
        "schema_version",
        "task_id",
        "goal",
        "status",
        "current_phase",
        "files_changed",
        "latest_checkpoint",
        "checkpoint_seq",
        "tests_run",
        "latest_test_status",
        "test_status_consumed",
        "retry_budget_remaining",
        "inconsistent",
        "source_edits_this_phase",
        "rollback_required",
        "rollback_done",
        "phase_completed",
        "artifacts",
    }
)
_PHASE_NAMES = frozenset(phase.value for phase in Phase)
_ARTIFACT_NAMES = frozenset(
    {
        "SPEC.md",
        "PLAN.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "KNOWLEDGE.md",
        "DELIVERABLES.md",
    }
)
_TEST_STATUSES = frozenset({"none", "passed", "failed"})


@dataclass(frozen=True, slots=True)
class TaskState:
    schema_version: int
    task_id: str
    goal: str | None
    status: TaskStatus
    current_phase: Phase
    files_changed: tuple[str, ...]
    latest_checkpoint: str | None
    checkpoint_seq: int
    tests_run: tuple[str, ...]
    latest_test_status: str
    test_status_consumed: bool
    retry_budget_remaining: int
    inconsistent: bool
    source_edits_this_phase: int
    rollback_required: bool
    rollback_done: bool
    phase_completed: Mapping[str, bool]
    artifacts: Mapping[str, bool]

    def __post_init__(self) -> None:
        if not _is_nonnegative_int(self.schema_version) or self.schema_version != 1:
            raise _invalid_state_field("schema_version")
        if not isinstance(self.task_id, str) or not self.task_id:
            raise _invalid_state_field("task_id")
        if self.goal is not None and (
            not isinstance(self.goal, str) or not self.goal
        ):
            raise _invalid_state_field("goal")
        if not isinstance(self.status, TaskStatus):
            raise _invalid_state_field("status")
        if not isinstance(self.current_phase, Phase):
            raise _invalid_state_field("current_phase")
        if not _is_str_tuple(self.files_changed):
            raise _invalid_state_field("files_changed")
        if self.latest_checkpoint is not None and (
            not isinstance(self.latest_checkpoint, str) or not self.latest_checkpoint
        ):
            raise _invalid_state_field("latest_checkpoint")
        if not _is_nonnegative_int(self.checkpoint_seq):
            raise _invalid_state_field("checkpoint_seq")
        if not _is_str_tuple(self.tests_run):
            raise _invalid_state_field("tests_run")
        if (
            not isinstance(self.latest_test_status, str)
            or self.latest_test_status not in _TEST_STATUSES
        ):
            raise _invalid_state_field("latest_test_status")
        if not isinstance(self.test_status_consumed, bool):
            raise _invalid_state_field("test_status_consumed")
        if not _is_nonnegative_int(self.retry_budget_remaining):
            raise _invalid_state_field("retry_budget_remaining")
        if not isinstance(self.inconsistent, bool):
            raise _invalid_state_field("inconsistent")
        if not _is_nonnegative_int(self.source_edits_this_phase):
            raise _invalid_state_field("source_edits_this_phase")
        if not isinstance(self.rollback_required, bool):
            raise _invalid_state_field("rollback_required")
        if not isinstance(self.rollback_done, bool):
            raise _invalid_state_field("rollback_done")
        if not _is_bool_mapping(self.phase_completed, _PHASE_NAMES):
            raise _invalid_state_field("phase_completed")
        if not _is_bool_mapping(self.artifacts, _ARTIFACT_NAMES):
            raise _invalid_state_field("artifacts")
        object.__setattr__(
            self, "phase_completed", MappingProxyType(dict(self.phase_completed))
        )
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))


def load_state(task_root: Path) -> TaskState:
    try:
        state_file = task_root / "state.json"
        if _is_link(state_file):
            raise ValueError("Task state file must not be a link.")
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Task state must be a JSON object.")
        if set(data) != _STATE_FIELDS:
            raise ValueError("Task state fields do not match schema version 1.")

        schema_version = _required_int(data, "schema_version")
        if schema_version != 1:
            raise ValueError("Task state schema version is unsupported.")

        return TaskState(
            schema_version=schema_version,
            task_id=_required_str(data, "task_id"),
            goal=_optional_str(data, "goal"),
            status=TaskStatus(_required_str(data, "status")),
            current_phase=Phase(_required_str(data, "current_phase")),
            files_changed=_required_str_tuple(data, "files_changed"),
            latest_checkpoint=_optional_str(data, "latest_checkpoint"),
            checkpoint_seq=_required_int(data, "checkpoint_seq"),
            tests_run=_required_str_tuple(data, "tests_run"),
            latest_test_status=_required_choice(
                data, "latest_test_status", _TEST_STATUSES
            ),
            test_status_consumed=_required_bool(data, "test_status_consumed"),
            retry_budget_remaining=_required_int(data, "retry_budget_remaining"),
            inconsistent=_required_bool(data, "inconsistent"),
            source_edits_this_phase=_required_int(data, "source_edits_this_phase"),
            rollback_required=_required_bool(data, "rollback_required"),
            rollback_done=_required_bool(data, "rollback_done"),
            phase_completed=_required_bool_mapping(
                data, "phase_completed", _PHASE_NAMES
            ),
            artifacts=_required_bool_mapping(data, "artifacts", _ARTIFACT_NAMES),
        )
    except (OSError, UnicodeError, ValueError):
        raise _state_parse_error() from None


def reconcile_state(task_root: Path, state: TaskState) -> TaskState:
    has_artifact_drift = any(
        _is_link(task_root / artifact_name)
        or (task_root / artifact_name).is_file() is not expected_to_exist
        for artifact_name, expected_to_exist in state.artifacts.items()
    )
    if not has_artifact_drift:
        return state
    return replace(state, status=TaskStatus.INCONSISTENT, inconsistent=True)


def save_state(task_root: Path, state: TaskState) -> None:
    persisted_state = load_state(task_root)
    if state.task_id != persisted_state.task_id:
        raise _state_identity_mismatch_error(persisted_state.current_phase)
    if (
        state.files_changed != persisted_state.files_changed
        and (
            persisted_state.current_phase is not Phase.CODE
            or state.current_phase not in {Phase.CODE, Phase.TEST}
        )
    ):
        raise _files_changed_update_error(persisted_state.current_phase)

    state_data = {
        "schema_version": state.schema_version,
        "task_id": state.task_id,
        "goal": state.goal,
        "status": state.status.value,
        "current_phase": state.current_phase.value,
        "files_changed": list(state.files_changed),
        "latest_checkpoint": state.latest_checkpoint,
        "checkpoint_seq": state.checkpoint_seq,
        "tests_run": list(state.tests_run),
        "latest_test_status": state.latest_test_status,
        "test_status_consumed": state.test_status_consumed,
        "retry_budget_remaining": state.retry_budget_remaining,
        "inconsistent": state.inconsistent,
        "source_edits_this_phase": state.source_edits_this_phase,
        "rollback_required": state.rollback_required,
        "rollback_done": state.rollback_done,
        "phase_completed": dict(state.phase_completed),
        "artifacts": dict(state.artifacts),
    }
    state_file = task_root / "state.json"
    if _is_link(state_file):
        raise _state_write_error(persisted_state.current_phase)
    temporary_state_file: Path | None = None
    descriptor: int | None = None
    try:
        descriptor, temporary_name = mkstemp(
            prefix=".state-",
            suffix=".tmp",
            dir=task_root,
        )
        temporary_state_file = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temporary_file:
            descriptor = None
            temporary_file.write(json.dumps(state_data, ensure_ascii=False, indent=2) + "\n")
        temporary_state_file.replace(state_file)
    except (OSError, UnicodeError):
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if temporary_state_file is not None:
                temporary_state_file.unlink(missing_ok=True)
        except OSError:
            pass
        raise _state_write_error(persisted_state.current_phase) from None


def _required_str(data: Mapping[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Task state field is invalid: {field}.")
    return value


def _required_choice(
    data: Mapping[str, object], field: str, allowed_values: frozenset[str]
) -> str:
    value = _required_str(data, field)
    if value not in allowed_values:
        raise ValueError(f"Task state field is invalid: {field}.")
    return value


def _optional_str(data: Mapping[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"Task state field is invalid: {field}.")
    return value


def _required_int(data: Mapping[str, object], field: str) -> int:
    value = data.get(field)
    if not _is_nonnegative_int(value):
        raise ValueError(f"Task state field is invalid: {field}.")
    return value


def _required_bool(data: Mapping[str, object], field: str) -> bool:
    value = data.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Task state field is invalid: {field}.")
    return value


def _required_str_tuple(data: Mapping[str, object], field: str) -> tuple[str, ...]:
    value = data.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Task state field is invalid: {field}.")
    return tuple(value)


def _required_bool_mapping(
    data: Mapping[str, object], field: str, expected_keys: frozenset[str]
) -> dict[str, bool]:
    value = data.get(field)
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or any(not isinstance(key, str) or not isinstance(item, bool) for key, item in value.items())
    ):
        raise ValueError(f"Task state field is invalid: {field}.")
    return dict(value)


def _state_parse_error() -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="state_parse_error",
            message="Task state file is invalid.",
            phase="spec",
            denied_rule="valid_task_state_required",
            suggested_fix="Repair state.json before continuing the task.",
        )
    )


def _invalid_state_field(field: str) -> ValueError:
    return ValueError(f"Task state field is invalid: {field}.")


def _is_nonnegative_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except (OSError, RuntimeError):
        return True


def _is_str_tuple(value: object) -> bool:
    return isinstance(value, tuple) and all(
        isinstance(item, str) and bool(item) for item in value
    )


def _is_bool_mapping(value: object, expected_keys: frozenset[str]) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == expected_keys
        and all(isinstance(item, bool) for item in value.values())
    )


def _files_changed_update_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="files_changed_update_outside_code",
            message="files_changed can only be updated from the code phase.",
            phase=phase.value,
            denied_rule="files_changed_code_write_only",
            suggested_fix=(
                "Update files_changed only after a successful code-phase "
                "edit_file or write_file."
            ),
        )
    )


def _state_identity_mismatch_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="state_identity_mismatch",
            message="Task state identity does not match the persisted task.",
            phase=phase.value,
            denied_rule="state_task_identity_match_required",
            suggested_fix="Reload the persisted task state before saving changes.",
        )
    )


def _state_write_error(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="state_write_error",
            message="Task state file could not be saved.",
            phase=phase.value,
            denied_rule="state_persistence_required",
            suggested_fix="Restore task workspace write access before continuing.",
        )
    )
