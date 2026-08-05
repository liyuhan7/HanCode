"""Task-bound deterministic tools for persisted runtime memory."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.memory import (
    MemoryKind,
    MemoryQuery,
    MemoryRecord,
    MemoryRecordDraft,
    MemorySearchHit,
    MemorySlice,
    MemorySnapshot,
)
from hancode.core.models import Phase
from hancode.core.state import load_state
from hancode.policy.path_policy import PathClassifier, PathZone
from hancode.storage.memory import FilesystemMemoryStore
from hancode.tooling.file_tools import probe_redacted_file_sha256
from hancode.tooling.registry import ToolResult


_INTEGRITY_ERRORS = frozenset(
    {
        "memory_corrupt",
        "memory_task_identity_mismatch",
        "memory_path_link_not_allowed",
        "memory_write_error",
    }
)
_TRUNCATION_MARKER = "[TRUNCATED]"


@dataclass(frozen=True, slots=True)
class MemoryFreshnessChecker:
    project_root: Path
    config: HanCodeConfig
    store: FilesystemMemoryStore

    def refresh_record(self, task_id: str, memory_id: str) -> MemorySnapshot:
        snapshot = self.store.load(task_id).snapshot
        if memory_id in dict(snapshot.invalidated_by):
            return snapshot
        current = {
            current_id: path for path, current_id in snapshot.latest_by_path
        }
        path = current.get(memory_id)
        if path is None:
            return snapshot
        record = _record_by_id(snapshot, memory_id)
        return self._refresh(task_id, ((path, record),), snapshot)

    def refresh_all(self, task_id: str) -> MemorySnapshot:
        snapshot = self.store.load(task_id).snapshot
        records = {record.memory_id: record for record in snapshot.records}
        selected: list[tuple[str, MemoryRecord]] = []
        for path, memory_id in snapshot.latest_by_path:
            record = records.get(memory_id)
            if record is None:
                phase = (
                    load_state(self.config.task_root).current_phase
                    if self.config.task_root is not None
                    else Phase.SPEC
                )
                raise _memory_corrupt(phase)
            selected.append((path, record))
        return self._refresh(task_id, tuple(selected), snapshot)

    def _refresh(
        self,
        task_id: str,
        selected: tuple[tuple[str, MemoryRecord], ...],
        snapshot: MemorySnapshot,
    ) -> MemorySnapshot:
        classifier = PathClassifier(self.config)
        reason_by_path: dict[str, str] = {}
        invalidates: list[str] = []
        for path, record in selected:
            if (
                record.tool_name != "read_file"
                or not record.success
                or record.content_sha256 is None
                or record.paths != (path,)
            ):
                phase = (
                    load_state(self.config.task_root).current_phase
                    if self.config.task_root is not None
                    else Phase.SPEC
                )
                raise _memory_corrupt(phase)
            probe = probe_redacted_file_sha256(self.project_root, path)
            reason = _stale_reason(
                probe.status, probe.content_sha256, record.content_sha256
            )
            if classifier.classify(path) in {
                PathZone.PROTECTED,
                PathZone.OUT_OF_SCOPE,
            }:
                reason = "unsafe"
            if reason is not None:
                reason_by_path[path] = reason
                invalidates.append(record.memory_id)
        if not invalidates:
            return snapshot
        phase = load_state(self.config.task_root).current_phase if self.config.task_root else Phase.SPEC
        return self.store.append(
            task_id,
            MemoryRecordDraft(
                phase=phase,
                kind=MemoryKind.INVALIDATION,
                tool_name=None,
                success=True,
                summary=_canonical_json(
                    {
                        "outcome": "invalidated",
                        "reason_by_path": reason_by_path,
                        "source": "context_fingerprint_probe",
                    }
                ),
                paths=tuple(sorted(reason_by_path)),
                invalidates=tuple(invalidates),
            ),
        ).snapshot


def memory_read(
    task_id: str,
    memory_id: str,
    *,
    checker: MemoryFreshnessChecker,
    store: FilesystemMemoryStore,
    max_observation_bytes: int,
    start_line: int = 1,
    end_line: int = 200,
    start_byte_offset: int = 0,
) -> ToolResult:
    try:
        checker.refresh_record(task_id, memory_id)
        slice_ = store.read(
            task_id,
            memory_id,
            start_line=start_line,
            end_line=end_line,
            start_byte_offset=start_byte_offset,
        )
        output = _fit_memory_slice(slice_, max_observation_bytes)
    except HanCodeError as exc:
        if exc.structured_error.error_code in _INTEGRITY_ERRORS:
            raise
        return _failed("memory_read", exc.structured_error.error_code, exc.structured_error.message)
    except ValueError as exc:
        if str(exc) == "memory_output_budget_too_small":
            return _failed(
                "memory_read",
                "memory_output_budget_too_small",
                "The observation budget cannot contain required memory metadata.",
            )
        raise
    return ToolResult(success=True, action_name="memory_read", output=output)


def memory_search(
    task_id: str,
    query: str,
    *,
    current_phase: Phase,
    checker: MemoryFreshnessChecker,
    store: FilesystemMemoryStore,
    max_observation_bytes: int,
    path: str | None = None,
    phase: str | None = None,
    include_stale: bool = False,
    limit: int = 5,
) -> ToolResult:
    task_root = checker.config.task_root
    if task_root is None or load_state(task_root).current_phase is not current_phase:
        return _failed(
            "memory_search",
            "memory_task_identity_mismatch",
            "Memory search phase does not match the current task state.",
        )
    try:
        query_phase = None if phase is None else Phase(phase)
    except (TypeError, ValueError):
        return _failed(
            "memory_search", "memory_invalid_record", "Memory search phase is invalid."
        )
    try:
        checker.refresh_all(task_id)
        hits = store.search(
            task_id,
            MemoryQuery(
                query=query,
                path=path,
                phase=query_phase,
                include_stale=include_stale,
                limit=limit,
            ),
        )
        output = _fit_search_hits(
            hits[:limit], max_observation_bytes, total_matches=len(hits)
        )
    except HanCodeError as exc:
        if exc.structured_error.error_code in _INTEGRITY_ERRORS:
            raise
        return _failed(
            "memory_search", exc.structured_error.error_code, exc.structured_error.message
        )
    except ValueError as exc:
        if str(exc) == "memory_output_budget_too_small":
            return _failed(
                "memory_search",
                "memory_output_budget_too_small",
                "The observation budget cannot contain required memory metadata.",
            )
        raise
    return ToolResult(success=True, action_name="memory_search", output=output)


def _fit_memory_slice(slice_: MemorySlice, budget: int) -> dict[str, object]:
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        raise ValueError("memory_output_budget_too_small")
    output = _slice_dict(replace(slice_, content=""))
    if _byte_len(output) > budget:
        raise ValueError("memory_output_budget_too_small")
    lines = slice_.content.splitlines(keepends=True)
    kept: list[str] = []
    for line in lines:
        candidate = dict(output)
        candidate["content"] = "".join((*kept, line))
        if _byte_len(candidate) > budget:
            break
        kept.append(line)
    if len(kept) == len(lines):
        output["content"] = slice_.content
        return output
    output["content_truncated"] = True
    if kept:
        output["content"] = "".join(kept)
        output["end_line"] = slice_.start_line + len(kept) - 1
        output["next_start_line"] = slice_.start_line + len(kept)
        return output
    # A single line does not fit: truncate within the line and expose a byte
    # cursor so the remainder of this same line can be recovered next call.
    output["next_start_line"] = slice_.start_line
    prefix_chars = _largest_fitting_prefix_chars(output, lines[0], budget)
    output["content"] = lines[0][:prefix_chars] + _TRUNCATION_MARKER
    consumed_bytes = len(lines[0][:prefix_chars].encode("utf-8"))
    output["next_byte_offset"] = slice_.start_byte_offset + consumed_bytes
    return output


def _largest_fitting_prefix_chars(
    output: dict[str, object], line: str, budget: int
) -> int:
    candidate = dict(output)
    candidate["content"] = _TRUNCATION_MARKER
    if _byte_len(candidate) > budget:
        raise ValueError("memory_output_budget_too_small")
    low, high = 0, len(line)
    while low < high:
        middle = (low + high + 1) // 2
        candidate["content"] = line[:middle] + _TRUNCATION_MARKER
        if _byte_len(candidate) <= budget:
            low = middle
        else:
            high = middle - 1
    return low


def _slice_dict(slice_: MemorySlice) -> dict[str, object]:
    return {
        "memory_id": slice_.memory_id,
        "phase": slice_.phase.value,
        "kind": slice_.kind.value,
        "tool_name": slice_.tool_name,
        "media_type": slice_.media_type.value,
        "paths": list(slice_.paths),
        "record_generation": slice_.record_generation,
        "current_generation": slice_.current_generation,
        "stale": slice_.stale,
        "invalidated_by": slice_.invalidated_by,
        "superseded_by": slice_.superseded_by,
        "invalidation_reason": slice_.invalidation_reason,
        "current_file_authoritative": slice_.current_file_authoritative,
        "warning": slice_.warning,
        "start_line": slice_.start_line,
        "end_line": slice_.end_line,
        "total_lines": slice_.total_lines,
        "content": slice_.content,
        "content_truncated": slice_.content_truncated,
        "next_start_line": slice_.next_start_line,
        "start_byte_offset": slice_.start_byte_offset,
        "next_byte_offset": slice_.next_byte_offset,
    }


def _fit_search_hits(
    hits: tuple[MemorySearchHit, ...], budget: int, *, total_matches: int
) -> dict[str, object]:
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
        raise ValueError("memory_output_budget_too_small")
    rendered = [_hit_dict(hit) for hit in hits]
    output: dict[str, object] = {
        "total_matches": total_matches,
        "returned_count": len(rendered),
        "truncated": total_matches > len(rendered),
        "hits": rendered,
    }
    if _byte_len(output) <= budget:
        return output
    output["truncated"] = True
    summaries = [hit["summary"] if isinstance(hit["summary"], str) else "" for hit in rendered]
    for hit in rendered:
        hit["summary"] = _TRUNCATION_MARKER
    while rendered and _byte_len(output) > budget:
        rendered.pop()
        summaries.pop()
        output["returned_count"] = len(rendered)
    if _byte_len(output) > budget:
        raise ValueError("memory_output_budget_too_small")
    for hit, summary in zip(rendered, summaries, strict=True):
        hit["summary"] = _largest_fitting_summary(output, hit, summary, budget)
    return output


def _largest_fitting_summary(
    output: dict[str, object],
    hit: dict[str, object],
    summary: str,
    budget: int,
) -> str:
    hit["summary"] = _TRUNCATION_MARKER
    if _byte_len(output) > budget:
        return _TRUNCATION_MARKER
    low, high = 0, len(summary)
    while low < high:
        middle = (low + high + 1) // 2
        hit["summary"] = summary[:middle] + _TRUNCATION_MARKER
        if _byte_len(output) <= budget:
            low = middle
        else:
            high = middle - 1
    return summary[:low] + _TRUNCATION_MARKER


def _hit_dict(hit: MemorySearchHit) -> dict[str, object]:
    return {
        "memory_id": hit.memory_id,
        "seq": hit.seq,
        "phase": hit.phase.value,
        "kind": hit.kind.value,
        "tool_name": hit.tool_name,
        "success": hit.success,
        "summary": hit.summary,
        "error_code": hit.error_code,
        "paths": list(hit.paths),
        "media_type": None if hit.media_type is None else hit.media_type.value,
        "blob_bytes": hit.blob_bytes,
        "record_generation": hit.record_generation,
        "current_generation": hit.current_generation,
        "stale": hit.stale,
        "invalidated_by": hit.invalidated_by,
        "superseded_by": hit.superseded_by,
        "invalidation_reason": hit.invalidation_reason,
        "match_sources": list(hit.match_sources),
    }


def _record_by_id(snapshot: MemorySnapshot, memory_id: str) -> MemoryRecord:
    for record in snapshot.records:
        if record.memory_id == memory_id:
            return record
    raise AssertionError("latest memory mapping must reference an existing record")


def _stale_reason(
    status: str, current_sha256: str | None, recorded_sha256: str | None
) -> str | None:
    if status != "available":
        return status
    return None if current_sha256 == recorded_sha256 else "content_changed"


def _memory_corrupt(phase: Phase) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code="memory_corrupt",
            message="Task runtime memory is invalid or corrupt.",
            phase=phase.value,
            denied_rule="valid_runtime_memory_required",
            suggested_fix="Repair task runtime memory before continuing.",
        )
    )


def _failed(action_name: str, error_code: str, message: str) -> ToolResult:
    return ToolResult(
        success=False,
        action_name=action_name,
        error_summary=message,
        error_code=error_code,
        mutation_applied=False,
    )


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _byte_len(value: object) -> int:
    return len(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


__all__ = ["MemoryFreshnessChecker", "memory_read", "memory_search"]
