"""ReflectionService — student reflection sections — S14-R7.

Student reflections are stored structurally in ``learning/reflections.json`` and
projected into the student region of each Markdown artifact. The Markdown is
never treated as the authoritative source; ``reflections.json`` is. A monotonic
``revision`` guards against lost updates: a save must declare the revision it
observed, otherwise it is rejected as a conflict.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
from tempfile import mkstemp

from hancode.core.errors import HanCodeError, StructuredError
from hancode.delivery_support.renderer import (
    GENERATED_END,
    GeneratedRegionError,
    replace_generated_region,
)
from hancode.delivery_support.result import _write_artifact
from hancode.storage.workspace import task_path
from hancode.tooling.file_tools import redact_text


class ReflectionSection(str, Enum):
    MY_UNDERSTANDING = "my_understanding"
    OPEN_QUESTIONS = "open_questions"
    PEER_FEEDBACK = "peer_feedback"


_SECTION_TITLES = {
    ReflectionSection.MY_UNDERSTANDING: "我的理解",
    ReflectionSection.OPEN_QUESTIONS: "我仍然不理解的地方",
    ReflectionSection.PEER_FEEDBACK: "教师或同伴反馈",
}
_SECTION_ORDER = (
    ReflectionSection.MY_UNDERSTANDING,
    ReflectionSection.OPEN_QUESTIONS,
    ReflectionSection.PEER_FEEDBACK,
)


class ReflectionConflictError(HanCodeError):
    """Raised when the observed reflection revision is stale."""


@dataclass(frozen=True, slots=True)
class ReflectionResult:
    task_id: str
    artifact: str
    section: str
    revision: int


@dataclass(frozen=True, slots=True)
class ReflectionState:
    task_id: str
    revision: int
    sections: dict[str, dict[str, str]]


class ReflectionService:
    """Persist and project student reflection sections."""

    def _path(self, task_root: Path) -> Path:
        return task_root / "learning" / "reflections.json"

    def read_reflections(self, project_root: Path, task_id: str) -> ReflectionState:
        task_root = task_path(project_root, task_id)
        return self._load(task_root, task_id)

    def save_reflection(
        self,
        project_root: Path,
        task_id: str,
        *,
        artifact: str,
        section: ReflectionSection,
        content: str,
        expected_reflection_revision: int,
    ) -> ReflectionResult:
        if not isinstance(section, ReflectionSection):
            raise _reflection_error(
                "reflection_section_invalid",
                "Reflection section is not recognized.",
                "Use a valid ReflectionSection value.",
            )
        if redact_text(content) != content:
            raise _reflection_error(
                "reflection_content_rejected",
                "Reflection content contains sensitive data.",
                "Remove secrets from the reflection before saving.",
            )
        task_root = task_path(project_root, task_id)
        state = self._load(task_root, task_id)
        if expected_reflection_revision != state.revision:
            raise ReflectionConflictError(
                StructuredError(
                    error_code="reflection_revision_conflict",
                    message="Reflection was modified since it was read.",
                    phase="deliver",
                    denied_rule="reflection_optimistic_lock",
                    suggested_fix="Re-read the reflection and retry your edit.",
                )
            )

        sections = {
            key: dict(value) for key, value in state.sections.items()
        }
        artifact_sections = sections.setdefault(artifact, {})
        artifact_sections[section.value] = content
        new_revision = state.revision + 1
        self._save(task_root, task_id, new_revision, sections)
        self._project(task_root, artifact, artifact_sections)
        return ReflectionResult(
            task_id=task_id,
            artifact=artifact,
            section=section.value,
            revision=new_revision,
        )

    # ------------------------------------------------------------------

    def _load(self, task_root: Path, task_id: str) -> ReflectionState:
        path = self._path(task_root)
        if not path.is_file():
            return ReflectionState(task_id=task_id, revision=0, sections={})
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise _reflection_error(
                "reflection_store_invalid",
                "Reflection store cannot be read.",
                "Repair or delete reflections.json.",
            ) from exc
        if not isinstance(data, dict) or data.get("task_id") != task_id:
            raise _reflection_error(
                "reflection_store_invalid",
                "Reflection store is malformed.",
                "Repair or delete reflections.json.",
            )
        revision = data.get("revision", 0)
        sections = data.get("sections", {})
        if not isinstance(revision, int) or not isinstance(sections, dict):
            raise _reflection_error(
                "reflection_store_invalid",
                "Reflection store is malformed.",
                "Repair or delete reflections.json.",
            )
        clean: dict[str, dict[str, str]] = {}
        for artifact, values in sections.items():
            if isinstance(artifact, str) and isinstance(values, dict):
                clean[artifact] = {
                    str(k): str(v) for k, v in values.items() if isinstance(v, str)
                }
        return ReflectionState(task_id=task_id, revision=revision, sections=clean)

    def _save(
        self,
        task_root: Path,
        task_id: str,
        revision: int,
        sections: dict[str, dict[str, str]],
    ) -> None:
        path = self._path(task_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "task_id": task_id,
            "revision": revision,
            "sections": sections,
        }
        descriptor: int | None = None
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = mkstemp(
                prefix=".reflections-", suffix=".tmp", dir=path.parent
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                descriptor = None
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        except OSError as exc:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise _reflection_error(
                "reflection_store_write_failed",
                "Reflection store could not be written.",
                "Restore task workspace write access before continuing.",
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _project(
        self, task_root: Path, artifact: str, sections: dict[str, str]
    ) -> None:
        target = task_root / artifact
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        student_block = _render_student_region(sections)
        try:
            rendered = _replace_student_region(existing, student_block)
        except GeneratedRegionError as exc:
            raise _reflection_error(
                "reflection_projection_failed",
                "Reflection could not be projected into the artifact.",
                "Repair the artifact's generated markers before editing reflections.",
            ) from exc
        _write_artifact(task_root, artifact, rendered)


def _render_student_region(sections: dict[str, str]) -> str:
    lines: list[str] = []
    for section in _SECTION_ORDER:
        lines.append(f"## {_SECTION_TITLES[section]}")
        lines.append("")
        content = sections.get(section.value, "").strip()
        if content:
            lines.append(content)
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _replace_student_region(existing: str, student_block: str) -> str:
    if GENERATED_END in existing:
        head, _sep, _tail = existing.partition(GENERATED_END)
        return f"{head}{GENERATED_END}\n\n{student_block}"
    # No generated region yet: create an empty one and attach student notes.
    seeded = replace_generated_region(existing, "（暂无生成内容）")
    head, _sep, _tail = seeded.partition(GENERATED_END)
    return f"{head}{GENERATED_END}\n\n{student_block}"


def _reflection_error(
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


__all__ = [
    "ReflectionConflictError",
    "ReflectionResult",
    "ReflectionSection",
    "ReflectionService",
    "ReflectionState",
]
