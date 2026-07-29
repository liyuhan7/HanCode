"""Application service for safe project configuration inspection and updates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
from uuid import uuid4

from hancode.core.config import HanCodeConfig, validate_project_config_data
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.project_config import complete_project_config
from hancode.storage.workspace import load_project_metadata


@dataclass(frozen=True, slots=True)
class ProjectConfigView:
    config_path: Path
    values: tuple[tuple[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class ConfigUpdateResult:
    config_path: Path
    changed_fields: tuple[str, ...]
    provider: str
    next_command: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "config": str(self.config_path),
            "changed_fields": list(self.changed_fields),
            "provider": self.provider,
            "next_command": self.next_command,
        }


class ConfigService:
    """Load normalized drafts and atomically persist validated configuration."""

    def load(self, project_root: Path) -> ProjectConfigView:
        root = project_root.resolve()
        path = self._config_path(root)
        raw = load_project_metadata(path)
        validate_project_config_data(root, raw)
        complete = complete_project_config(raw, fallback_project_root=root)
        return ProjectConfigView(path, tuple(complete.items()))

    def validate(
        self,
        project_root: Path,
        values: Mapping[str, object],
    ) -> HanCodeConfig:
        root = project_root.resolve()
        validate_project_config_data(root, values)
        candidate = complete_project_config(values, fallback_project_root=root)
        return validate_project_config_data(root, candidate)

    def save(
        self,
        project_root: Path,
        values: Mapping[str, object],
    ) -> ConfigUpdateResult:
        root = project_root.resolve()
        current = self.load(root)
        validate_project_config_data(root, values)
        candidate = complete_project_config(values, fallback_project_root=root)
        validated = validate_project_config_data(root, candidate)
        changed_fields = tuple(
            key for key, value in candidate.items() if current.to_dict().get(key) != value
        )
        content = json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
        self._atomic_replace(current.config_path, content)
        provider = validated.llm_provider
        next_command = (
            f"hancode auth login --provider {provider}"
            if provider in {"openai_compatible", "anthropic"}
            else None
        )
        return ConfigUpdateResult(
            config_path=current.config_path,
            changed_fields=changed_fields,
            provider=provider,
            next_command=next_command,
        )

    @staticmethod
    def _config_path(project_root: Path) -> Path:
        path = project_root / ".hancode" / "project.json"
        if not path.is_file():
            raise HanCodeError(
                StructuredError(
                    error_code="project_workspace_not_initialized",
                    message="Project workspace is not initialized.",
                    phase="spec",
                    denied_rule="project_workspace_required",
                    suggested_fix="Run hancode init before opening project configuration.",
                )
            )
        return path

    @staticmethod
    def _atomic_replace(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise HanCodeError(
                StructuredError(
                    error_code="project_config_write_failed",
                    message="Project configuration could not be saved atomically.",
                    phase="spec",
                    denied_rule="atomic_project_config_write_required",
                    suggested_fix="Check .hancode directory permissions and retry.",
                )
            ) from exc


__all__ = ["ConfigService", "ConfigUpdateResult", "ProjectConfigView"]
