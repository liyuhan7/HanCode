"""Atomic task-scoped persistence for test failure records."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from tempfile import mkstemp

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.test_remediation import RemediationDecision, TestFailureRecord
from hancode.storage.workspace import task_path


_MAX_RECORD_BYTES = 64 * 1024


class TestRemediationStore:
    __test__ = False

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def save_failure(self, record: TestFailureRecord) -> Path:
        _validate_failure(record)
        path = self._path(record.task_id, "test_failure.json")
        _atomic_write(path, record.to_dict())
        return path

    def load_failure(self, task_id: str) -> TestFailureRecord:
        path = self._path(task_id, "test_failure.json")
        data = _read_object(path)
        try:
            record = TestFailureRecord.from_dict(data)
        except (TypeError, ValueError) as exc:
            raise _invalid_record("Test failure record is invalid.") from exc
        if record.task_id != task_id:
            raise _invalid_record("Test failure task binding does not match.")
        return record

    def save_remediation(self, decision: RemediationDecision) -> Path:
        _validate_remediation(decision)
        path = self._path(decision.task_id, "test_remediation.json")
        _atomic_write(path, decision.to_dict())
        return path

    def load_remediation(self, task_id: str) -> RemediationDecision:
        path = self._path(task_id, "test_remediation.json")
        data = _read_object(path)
        try:
            decision = RemediationDecision.from_dict(data)
        except (TypeError, ValueError) as exc:
            raise _invalid_record("Test remediation decision is invalid.") from exc
        if decision.task_id != task_id:
            raise _invalid_record("Test remediation task binding does not match.")
        return decision

    def _path(self, task_id: str, name: str) -> Path:
        return task_path(self._project_root, task_id) / name


def _read_object(path: Path) -> dict[str, object]:
    if _is_link(path) or not path.is_file():
        raise _invalid_record("Test remediation record is missing or unsafe.")
    try:
        if path.stat().st_size > _MAX_RECORD_BYTES:
            raise ValueError("record exceeds size limit")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise _invalid_record("Test remediation record could not be loaded.") from exc
    if not isinstance(data, dict):
        raise _invalid_record("Test remediation record must be a JSON object.")
    return data


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    if _is_link(path.parent):
        raise _invalid_record("Linked test remediation directories cannot be used.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _is_link(path):
        raise _invalid_record("Linked test remediation records cannot be replaced.")
    encoded = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(encoded.encode("utf-8")) > _MAX_RECORD_BYTES:
        raise _invalid_record("Test remediation record exceeds the size limit.")
    descriptor, temporary_name = mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}-",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    if _is_link(temporary_path):
        raise _invalid_record("Temporary test remediation target must not be a link.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _invalid_record(message: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="test_remediation_invalid",
            message=message,
            phase="review",
            denied_rule="valid_test_remediation_required",
            suggested_fix="Recreate the record from the current task evidence.",
        )
    )


def _validate_failure(record: TestFailureRecord) -> None:
    try:
        if TestFailureRecord.from_dict(record.to_dict()) != record:
            raise ValueError("record did not round-trip")
    except (TypeError, ValueError) as exc:
        raise _invalid_record("Test failure record is invalid.") from exc


def _validate_remediation(decision: RemediationDecision) -> None:
    try:
        if RemediationDecision.from_dict(decision.to_dict()) != decision:
            raise ValueError("decision did not round-trip")
    except (TypeError, ValueError) as exc:
        raise _invalid_record("Test remediation decision is invalid.") from exc


def _is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False
    except (OSError, RuntimeError):
        return True
