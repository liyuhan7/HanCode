"""Framework-agnostic read access to persisted trace and delivery artifacts.

The TUI (and any other presentation layer) must not read ``trace.jsonl`` or task
files directly. InspectionService is the only safe read path:

- :meth:`read_trace` validates sequence integrity and task-id binding, refuses
  symlinked trace files, and pages results.
- :meth:`read_artifact` only previews allow-listed delivery artifacts that the
  reconciled task state declares present, refusing source files, credentials,
  and links.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase
from hancode.core.state import load_state, reconcile_state
from hancode.storage.trace import TraceEvent
from hancode.storage.workspace import task_path
from hancode.tooling.file_tools import redact_text


_ARTIFACT_ALLOW_LIST = (
    "SPEC.md",
    "PLAN.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "KNOWLEDGE.md",
    "DELIVERABLES.md",
)


@dataclass(frozen=True, slots=True)
class TracePage:
    events: tuple[TraceEvent, ...]
    next_seq: int | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class ArtifactPreview:
    name: str
    content: str
    char_count: int
    truncated: bool


class InspectionService:
    """Read persisted trace events and preview declared delivery artifacts."""

    def read_trace(
        self,
        project_root: Path,
        task_id: str,
        *,
        after_seq: int = 0,
        limit: int = 200,
    ) -> TracePage:
        if after_seq < 0:
            raise _inspection_error(
                "inspection_after_seq_invalid",
                "The after_seq cursor must be non-negative.",
                "Pass a non-negative after_seq value.",
            )
        if limit <= 0:
            raise _inspection_error(
                "inspection_limit_invalid",
                "The page limit must be positive.",
                "Pass a positive limit value.",
            )

        task_root = task_path(project_root, task_id)
        trace_file = task_root / "trace.jsonl"
        if _is_link(trace_file):
            raise _inspection_error(
                "inspection_trace_link_not_allowed",
                "Task trace path must not be a symbolic link or junction.",
                "Replace trace.jsonl with a regular file inside the task workspace.",
            )
        if not trace_file.is_file():
            return TracePage(events=(), next_seq=None, has_more=False)

        all_events = _read_all_events(trace_file, task_id)
        newer = [event for event in all_events if event.seq > after_seq]
        page = newer[:limit]
        has_more = len(newer) > limit
        next_seq = page[-1].seq if page and has_more else None
        return TracePage(events=tuple(page), next_seq=next_seq, has_more=has_more)

    def read_artifact(
        self,
        project_root: Path,
        task_id: str,
        artifact_name: str,
        *,
        max_chars: int = 50_000,
    ) -> ArtifactPreview:
        if max_chars <= 0:
            raise _inspection_error(
                "inspection_max_chars_invalid",
                "The preview limit must be positive.",
                "Pass a positive max_chars value.",
            )
        if artifact_name not in _ARTIFACT_ALLOW_LIST:
            raise _inspection_error(
                "inspection_artifact_not_allowed",
                "Only declared delivery artifacts can be previewed.",
                "Preview one of the fixed delivery artifact names.",
            )

        task_root = task_path(project_root, task_id)
        state = reconcile_state(task_root, load_state(task_root))
        if not state.artifacts.get(artifact_name, False):
            raise _inspection_error(
                "inspection_artifact_not_declared",
                "The task state does not declare this artifact as present.",
                "Only artifacts marked present in state.json can be previewed.",
            )

        artifact_path = task_root / artifact_name
        if _is_link(artifact_path) or not artifact_path.is_file():
            raise _inspection_error(
                "inspection_artifact_unavailable",
                "A state-declared artifact is missing or linked.",
                "Restore the regular artifact file before previewing.",
            )
        try:
            raw = artifact_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise _inspection_error(
                "inspection_artifact_read_failed",
                "The artifact could not be read as UTF-8 text.",
                "Ensure the artifact is a readable UTF-8 file.",
            ) from None

        safe = redact_text(raw)
        truncated = len(safe) > max_chars
        content = safe[:max_chars] if truncated else safe
        return ArtifactPreview(
            name=artifact_name,
            content=content,
            char_count=len(safe),
            truncated=truncated,
        )


def _read_all_events(trace_file: Path, task_id: str) -> list[TraceEvent]:
    try:
        lines = trace_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        raise _trace_parse_error() from None

    events: list[TraceEvent] = []
    for expected_seq, line in enumerate(lines, start=1):
        if not line.strip():
            raise _trace_parse_error()
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            raise _trace_parse_error() from None
        if not isinstance(data, dict):
            raise _trace_parse_error()
        if (
            data.get("seq") != expected_seq
            or isinstance(data.get("seq"), bool)
            or data.get("event_id") != f"evt-{expected_seq:06d}"
            or data.get("task_id") != task_id
        ):
            raise _trace_parse_error()
        events.append(_event_from_dict(data))
    return events


def _event_from_dict(data: Mapping[str, object]) -> TraceEvent:
    try:
        phase = Phase(data["phase"])
        timestamp = datetime.fromisoformat(str(data["timestamp"]))
        seq = data["seq"]
        event_id = data["event_id"]
        event_type = data["event_type"]
        task_id = data["task_id"]
        status = data["status"]
    except (KeyError, ValueError, TypeError):
        raise _trace_parse_error() from None
    if not (
        isinstance(seq, int)
        and isinstance(event_id, str)
        and isinstance(event_type, str)
        and isinstance(task_id, str)
        and isinstance(status, str)
    ):
        raise _trace_parse_error()
    raw_error_summary = data.get("error_summary")
    error_summary = raw_error_summary if isinstance(raw_error_summary, str) else None
    return TraceEvent(
        event_id=event_id,
        seq=seq,
        event_type=event_type,
        task_id=task_id,
        phase=phase,
        timestamp=timestamp,
        status=status,
        action=_as_mapping(data.get("action")),
        observation=_as_mapping(data.get("observation")),
        error_summary=error_summary,
        state_transition=_as_mapping(data.get("state_transition")),
    )


def _as_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return None


def _is_link(path: Path) -> bool:
    try:
        junction_probe = getattr(path, "is_junction", None)
        return path.is_symlink() or (
            bool(junction_probe()) if callable(junction_probe) else False
        )
    except (AttributeError, OSError, RuntimeError):
        return True


def _trace_parse_error() -> HanCodeError:
    return _inspection_error(
        "inspection_trace_invalid",
        "The task trace is invalid and cannot be displayed.",
        "Repair or restore trace.jsonl before inspecting it.",
    )


def _inspection_error(
    error_code: str, message: str, suggested_fix: str
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="deliver",
            denied_rule=error_code,
            suggested_fix=suggested_fix,
        )
    )


__all__ = ["InspectionService", "TracePage", "ArtifactPreview"]
