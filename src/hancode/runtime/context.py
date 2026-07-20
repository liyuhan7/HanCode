"""Deterministic, phase-scoped context construction."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from hancode.core.config import HanCodeConfig
from hancode.core.interactions import InteractionStatus
from hancode.storage.checkpoints import _load_manifest, _validate_manifest_identity
from hancode.core.errors import HanCodeError, StructuredError
from hancode.tooling.file_tools import redact_text
from hancode.core.models import Phase
from hancode.policy.path_policy import PathClassifier, PathZone
from hancode.core.state import TaskState, load_state, reconcile_state
from hancode.policy.tool_policy import allowed_tools_for_phase
from hancode.storage.workspace import load_project_metadata, task_path


_REQUIRED_ARTIFACTS = {
    Phase.PLAN: ("SPEC.md",),
    Phase.CODE: ("SPEC.md", "PLAN.md"),
    Phase.TEST: ("PLAN.md",),
    Phase.REVIEW: ("SPEC.md", "PLAN.md", "TEST_REPORT.md"),
    Phase.DELIVER: ("SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md"),
}

_OMITTABLE_SECTIONS = frozenset(
    {"experience", "project_memory", "project_structure", "source_snippets"}
)

_TRUNCATION_ORDER = {
    Phase.SPEC: ("project_memory", "experience", "course_context"),
    Phase.PLAN: (
        "experience",
        "project_memory",
        "project_structure",
        "course_context",
        "spec",
    ),
    Phase.CODE: ("source_snippets", "protected_patterns", "allowed_tools", "plan", "spec"),
    Phase.TEST: ("checkpoint", "changed_files", "test_command", "plan"),
    Phase.REVIEW: ("checkpoint", "changed_files", "test_report", "plan", "spec"),
    Phase.DELIVER: ("trace_summary", "review", "test_report", "plan", "spec"),
}
_TRUNCATION_MARKER = "[TRUNCATED]"
_SENSITIVE_KEY_MARKERS = (
    "apikey",
    "authorization",
    "credential",
    "password",
    "privatekey",
    "secret",
    "token",
)
_MAX_TRACE_TRANSITION_DEPTH = 8
_ARTIFACT_NAMES = (
    "SPEC.md",
    "PLAN.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "KNOWLEDGE.md",
    "DELIVERABLES.md",
)


@dataclass(frozen=True, slots=True)
class ContextBuilder:
    """Adapt the functional context builder to the AgentLoop protocol."""

    project_root: Path
    config: HanCodeConfig

    def build(
        self, *, task_id: str, phase: Phase, state: TaskState
    ) -> dict[str, object]:
        return build_context(self.project_root, task_id, phase, self.config, state=state)


def build_context(
    project_root: Path,
    task_id: str,
    phase: Phase,
    config: HanCodeConfig,
    *,
    state: TaskState | None = None,
) -> dict[str, object]:
    """Build the minimum deterministic context for one task phase."""
    resolved_project_root = project_root.resolve()
    task_root = task_path(resolved_project_root, task_id)
    _validate_context_identity(resolved_project_root, task_root, task_id, phase, config)

    current_state = load_state(task_root) if state is None else state
    if current_state.task_id != task_id:
        raise _context_error(
            "context_task_mismatch",
            "Context state does not belong to the requested task.",
            phase,
            "matching_task_state_required",
            "Load state for the requested task before building context.",
        )
    if reconcile_state(task_root, current_state).inconsistent:
        raise _context_error(
            "context_state_inconsistent",
            "Task state is inconsistent with its artifacts.",
            phase,
            "consistent_task_state_required",
            "Repair task artifacts or state before building context.",
        )

    sections: dict[str, str] = {}
    risks: list[dict[str, object]] = []
    for artifact_name in _REQUIRED_ARTIFACTS.get(phase, ()):
        sections[_artifact_section_name(artifact_name)] = _read_required_artifact(
            task_root, current_state, artifact_name, phase
        )
    if phase is Phase.SPEC:
        if current_state.goal is None:
            raise _context_error(
                "context_goal_required",
                "Spec context requires a task goal.",
                phase,
                "task_goal_required",
                "Set a non-empty task goal before entering the spec phase.",
            )
        sections["course_context"] = _read_required_course_context(
            config.hancode_root / "course_context.md", phase
        )
        _add_optional_project_document(
            sections, risks, config.hancode_root / "project_memory.md", "project_memory"
        )
        _add_optional_project_document(
            sections, risks, config.hancode_root / "experience.md", "experience"
        )
    if phase is Phase.PLAN:
        sections["course_context"] = _read_required_course_context(
            config.hancode_root / "course_context.md", phase
        )
        _add_optional_project_document(
            sections, risks, config.hancode_root / "project_memory.md", "project_memory"
        )
        _add_optional_project_document(
            sections, risks, config.hancode_root / "experience.md", "experience"
        )
        sections["project_structure"] = _project_structure(config, resolved_project_root)
        if config.test_command is not None:
            sections["test_command"] = config.test_command
    if phase is Phase.CODE:
        sections["allowed_tools"] = _canonical_json(
            list(allowed_tools_for_phase(phase))
        )
        sections["protected_patterns"] = _canonical_json(
            list(config.protected_patterns)
        )
        sections["writable_roots"] = _writable_roots(config, resolved_project_root)
        _add_source_snippets(sections, risks, resolved_project_root, current_state, config)
    if phase in {Phase.TEST, Phase.REVIEW}:
        sections["changed_files"] = _canonical_json(
            _safe_changed_files(current_state, config, risks)
        )
        _add_checkpoint_summary(sections, risks, task_root, current_state, config, phase)
    if phase is Phase.TEST:
        if config.test_command is None:
            raise _context_error(
                "context_required_artifact_missing",
                "Test context requires a configured test command.",
                phase,
                "test_command_required",
                "Configure test_command before entering the test phase.",
            )
        sections["test_command"] = config.test_command
    if phase is Phase.DELIVER:
        sections["trace_summary"] = _read_trace_summary(
            task_root,
            task_id,
            config.max_trace_events,
            config.max_context_chars,
            phase,
            risks,
        )

    context: dict[str, object] = {
        "task_id": task_id,
        "phase": phase.value,
        "goal": None if current_state.goal is None else redact_text(current_state.goal),
        "task_workspace": task_root.relative_to(resolved_project_root).as_posix(),
        "artifact_targets": {
            name: f"{task_root.relative_to(resolved_project_root).as_posix()}/{name}"
            for name in _ARTIFACT_NAMES
        },
        "sections": sections,
        "context_risks": risks,
        "truncation": {
            "applied": False,
            "omitted_sections": [],
            "truncated_sections": [],
        },
    }
    interaction_history = [
        {
            "interaction_id": interaction.interaction_id,
            "phase": interaction.phase.value,
            "question": redact_text(interaction.question),
            "answer": redact_text(interaction.answer or ""),
        }
        for interaction in current_state.interactions
        if interaction.status is InteractionStatus.ANSWERED
    ]
    if interaction_history:
        context["interaction_history"] = interaction_history
    return _apply_context_budget(context, phase, config.max_context_chars)


def _apply_context_budget(
    context: dict[str, object], phase: Phase, max_context_chars: int
) -> dict[str, object]:
    """Fit a context deterministically without removing required structure."""
    if len(_canonical_json(context)) <= max_context_chars:
        return context

    sections = context["sections"]
    truncation = context["truncation"]
    if not isinstance(sections, dict) or not isinstance(truncation, dict):
        raise AssertionError("context shape must remain internal and deterministic")
    omitted = truncation["omitted_sections"]
    truncated = truncation["truncated_sections"]
    if not isinstance(omitted, list) or not isinstance(truncated, list):
        raise AssertionError("truncation shape must remain internal and deterministic")
    truncation["applied"] = True

    for metadata_name in ("artifact_targets", "task_workspace"):
        if metadata_name not in context:
            continue
        del context[metadata_name]
        omitted.append(metadata_name)
        if len(_canonical_json(context)) <= max_context_chars:
            return context

    for section_name in _TRUNCATION_ORDER[phase]:
        if section_name not in _OMITTABLE_SECTIONS or section_name not in sections:
            continue
        del sections[section_name]
        omitted.append(section_name)
        if len(_canonical_json(context)) <= max_context_chars:
            return context

    for section_name in _TRUNCATION_ORDER[phase]:
        value = sections.get(section_name)
        if not isinstance(value, str):
            continue
        truncated.append(section_name)
        best_length = _largest_fitting_prefix(
            context, section_name, value, max_context_chars
        )
        if best_length is None:
            sections[section_name] = _TRUNCATION_MARKER
        else:
            sections[section_name] = value[:best_length] + _TRUNCATION_MARKER
        if len(_canonical_json(context)) <= max_context_chars:
            return context

    raise _context_error(
        "context_budget_too_small",
        "The configured context budget cannot contain the required context skeleton.",
        phase,
        "context_budget_sufficient",
        "Increase max_context_chars or reduce the required task artifacts.",
    )


def _largest_fitting_prefix(
    context: dict[str, object], section_name: str, value: str, max_context_chars: int
) -> int | None:
    sections = context["sections"]
    if not isinstance(sections, dict):
        raise AssertionError("context shape must remain internal and deterministic")
    original = sections[section_name]
    sections[section_name] = _TRUNCATION_MARKER
    if len(_canonical_json(context)) > max_context_chars:
        sections[section_name] = original
        return None

    low, high = 0, len(value)
    while low < high:
        midpoint = (low + high + 1) // 2
        sections[section_name] = value[:midpoint] + _TRUNCATION_MARKER
        if len(_canonical_json(context)) <= max_context_chars:
            low = midpoint
        else:
            high = midpoint - 1
    sections[section_name] = original
    return low


def _read_required_artifact(
    task_root: Path, state: TaskState, artifact_name: str, phase: Phase
) -> str:
    path = task_root / artifact_name
    if not state.artifacts[artifact_name] or not path.is_file():
        raise _context_error(
            "context_required_artifact_missing",
            f"{artifact_name} is required for the current context phase.",
            phase,
            "required_artifact_available",
            f"Create {artifact_name} and update task state before continuing.",
        )
    if _is_link(path):
        raise _context_error(
            "context_required_artifact_unreadable",
            f"{artifact_name} cannot be read as UTF-8 context.",
            phase,
            "required_artifact_readable",
            f"Repair {artifact_name} before continuing.",
        )
    try:
        return redact_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        raise _context_error(
            "context_required_artifact_unreadable",
            f"{artifact_name} cannot be read as UTF-8 context.",
            phase,
            "required_artifact_readable",
            f"Repair {artifact_name} before continuing.",
        ) from None


def _artifact_section_name(artifact_name: str) -> str:
    return artifact_name.removesuffix(".md").casefold()


def _add_source_snippets(
    sections: dict[str, str],
    risks: list[dict[str, object]],
    project_root: Path,
    state: TaskState,
    config: HanCodeConfig,
) -> None:
    classifier = PathClassifier(config)
    snippets: dict[str, str] = {}
    for relative_path in sorted(state.files_changed, key=str.casefold):
        if classifier.classify(relative_path) is not PathZone.SOURCE:
            continue
        path = project_root / relative_path
        if _is_link(path):
            _append_risk(risks, "source_snippet_skipped", relative_path)
            continue
        try:
            snippets[relative_path] = redact_text(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            _append_risk(risks, "source_snippet_skipped", relative_path)
    if snippets:
        sections["source_snippets"] = _canonical_json(snippets)


def _safe_changed_files(
    state: TaskState, config: HanCodeConfig, risks: list[dict[str, object]]
) -> list[str]:
    classifier = PathClassifier(config)
    safe_paths: list[str] = []
    for relative_path in sorted(state.files_changed, key=str.casefold):
        if classifier.classify(relative_path) is not PathZone.SOURCE:
            _append_risk(risks, "changed_file_skipped", redact_text(relative_path))
            continue
        safe_paths.append(redact_text(relative_path))
    return safe_paths


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _add_checkpoint_summary(
    sections: dict[str, str],
    risks: list[dict[str, object]],
    task_root: Path,
    state: TaskState,
    config: HanCodeConfig,
    phase: Phase,
) -> None:
    checkpoint_id = state.latest_checkpoint
    if checkpoint_id is None:
        risks.append(
            {
                "level": "warning",
                "message": "No checkpoint is available for the current task.",
                "mitigation": "checkpoint_missing",
            }
        )
        return
    if not checkpoint_id.startswith("ckpt-") or not checkpoint_id.removeprefix(
        "ckpt-"
    ).isdigit():
        raise _checkpoint_error(phase)

    checkpoints_root = task_root / "checkpoints"
    checkpoint_root = checkpoints_root / checkpoint_id
    manifest_path = checkpoint_root / "manifest.json"
    try:
        if (
            _is_link(checkpoints_root)
            or _is_link(checkpoint_root)
            or _is_link(manifest_path)
            or not checkpoint_root.resolve().is_relative_to(checkpoints_root.resolve())
        ):
            raise ValueError
        manifest = _load_manifest(manifest_path, phase)
        metadata = load_project_metadata(config.hancode_root / "project.json")
        project_id = metadata.get("project_id")
        if not isinstance(project_id, str):
            raise ValueError
        _validate_manifest_identity(manifest, checkpoint_id, state, project_id)
        classifier = PathClassifier(config)
        files = tuple(
            file.path for file in manifest.files
            if classifier.classify(file.path) is PathZone.SOURCE
        )
        if len(files) != len(manifest.files):
            raise ValueError
    except (HanCodeError, OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        raise _checkpoint_error(phase) from None

    sections["checkpoint"] = _canonical_json(
        {
            "checkpoint_id": checkpoint_id,
            "files": sorted(files, key=str.casefold),
            "rollback_available": manifest.rollback_available,
            "status": manifest.status,
        }
    )


def _checkpoint_error(phase: Phase) -> HanCodeError:
    return _context_error(
        "context_checkpoint_invalid",
        "Latest checkpoint metadata is invalid for the current task.",
        phase,
        "valid_task_checkpoint_required",
        "Repair the current task checkpoint before building context.",
    )


def _read_trace_summary(
    task_root: Path,
    task_id: str,
    max_trace_events: int,
    max_context_chars: int,
    phase: Phase,
    risks: list[dict[str, object]],
) -> str:
    trace_path = task_root / "trace.jsonl"
    events: deque[dict[str, object]] = deque(maxlen=max_trace_events)
    try:
        if _is_link(trace_path):
            raise ValueError
        with trace_path.open(encoding="utf-8") as trace_file:
            for expected_seq, line in enumerate(trace_file, start=1):
                if len(line) > max_context_chars:
                    raise ValueError
                event = json.loads(line)
                if not isinstance(event, Mapping):
                    raise ValueError
                event_phase = event.get("phase")
                error_summary = event.get("error_summary")
                state_transition = event.get("state_transition")
                if (
                    event.get("seq") != expected_seq
                    or isinstance(event.get("seq"), bool)
                    or event.get("event_id") != f"evt-{expected_seq:06d}"
                    or event.get("task_id") != task_id
                    or not isinstance(event.get("event_type"), str)
                    or not isinstance(event_phase, str)
                    or event_phase not in {item.value for item in Phase}
                    or not isinstance(event.get("timestamp"), str)
                    or not isinstance(event.get("status"), str)
                    or (event.get("action") is not None and not isinstance(event.get("action"), Mapping))
                    or (
                        event.get("observation") is not None
                        and not isinstance(event.get("observation"), Mapping)
                    )
                    or (error_summary is not None and not isinstance(error_summary, str))
                    or (
                        state_transition is not None
                        and not isinstance(state_transition, Mapping)
                    )
                ):
                    raise ValueError
                events.append(
                    {
                        "event_id": event["event_id"],
                        "seq": expected_seq,
                        "event_type": event["event_type"],
                        "phase": event_phase,
                        "status": event["status"],
                        "error_summary": (
                            None if error_summary is None else redact_text(error_summary)
                        ),
                        "state_transition": _sanitize_trace_value(state_transition),
                    }
                )
    except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
        raise _trace_error(phase) from None
    if not events:
        risks.append(
            {
                "level": "warning",
                "message": "No trace events are available for the current task.",
                "mitigation": "trace_empty",
            }
        )
    return _canonical_json(list(events))


def _trace_error(phase: Phase) -> HanCodeError:
    return _context_error(
        "context_trace_invalid",
        "Task trace is invalid for context construction.",
        phase,
        "valid_task_trace_required",
        "Repair trace.jsonl before building context.",
    )


def _append_risk(
    risks: list[dict[str, object]], risk_code: str, relative_path: str
) -> None:
    risks.append(
        {
            "level": "warning",
            "message": f"Context source was skipped: {relative_path}.",
            "mitigation": risk_code,
        }
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_context_identity(
    project_root: Path,
    task_root: Path,
    task_id: str,
    phase: Phase,
    config: HanCodeConfig,
) -> None:
    if (
        config.project_root.resolve() != project_root
        or config.allowed_workspace_root.resolve() != project_root
        or config.hancode_root.resolve() != project_root / ".hancode"
    ):
        raise _context_error(
            "context_workspace_mismatch",
            "Context configuration does not belong to the requested project.",
            phase,
            "matching_project_config_required",
            "Load configuration from the requested project workspace.",
        )
    if config.task_root is None or config.task_root.resolve() != task_root:
        raise _context_error(
            "context_task_mismatch",
            "Context configuration does not belong to the requested task.",
            phase,
            "matching_task_config_required",
            f"Load configuration for task {task_id} before building context.",
        )


def _add_optional_project_document(
    sections: dict[str, str],
    risks: list[dict[str, object]],
    path: Path,
    section_name: str,
) -> None:
    try:
        if _is_link(path) or not path.is_file():
            raise OSError
        sections[section_name] = redact_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        risks.append(
            {
                "level": "warning",
                "message": f"Optional context section is unavailable: {section_name}.",
                "mitigation": f"Restore {path.name} before relying on this context.",
            }
        )


def _read_required_course_context(path: Path, phase: Phase) -> str:
    try:
        if _is_link(path) or not path.is_file():
            raise OSError
        return redact_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        raise _context_error(
            "context_required_artifact_missing",
            "Course context is required for the current context phase.",
            phase,
            "course_context_required",
            "Restore course_context.md before building context.",
        ) from None


def _project_structure(config: HanCodeConfig, project_root: Path) -> str:
    """Expose configured source roots without scanning arbitrary workspace files."""
    return _canonical_json({"writable_roots": _writable_root_paths(config, project_root)})


def _writable_roots(config: HanCodeConfig, project_root: Path) -> str:
    return _canonical_json(_writable_root_paths(config, project_root))


def _writable_root_paths(config: HanCodeConfig, project_root: Path) -> list[str]:
    roots: list[str] = []
    for writable_root in config.writable_roots:
        try:
            roots.append(writable_root.resolve().relative_to(project_root).as_posix())
        except (OSError, RuntimeError, ValueError):
            continue
    return sorted(roots, key=str.casefold)


def _sanitize_trace_value(value: object, depth: int = 0) -> object:
    if depth > _MAX_TRACE_TRANSITION_DEPTH:
        raise ValueError
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if _is_sensitive_key(str(key))
            else _sanitize_trace_value(nested_value, depth + 1)
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_trace_value(item, depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = "".join(character for character in key.casefold() if character.isalnum())
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _context_error(
    error_code: str,
    message: str,
    phase: Phase,
    denied_rule: str,
    suggested_fix: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=phase.value,
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )
