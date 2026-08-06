"""Deterministic export of task delivery artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
import shutil
from pathlib import Path
import tempfile

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.state import load_state, reconcile_state
from hancode.storage.workspace import task_path


_EXPORT_ARTIFACTS = (
    "SPEC.md",
    "PLAN.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "KNOWLEDGE.md",
    "DELIVERABLES.md",
)


class ExportProfile(str, Enum):
    SUBMISSION = "submission"
    LEARNING = "learning"
    AUDIT = "audit"


_LEARNING_ARTIFACTS = (
    "SPEC.md",
    "PLAN.md",
    "IMPLEMENTATION.md",
    "TEST_REPORT.md",
    "REVIEW.md",
    "KNOWLEDGE.md",
    "DELIVERABLES.md",
)


@dataclass(frozen=True, slots=True)
class ExportResult:
    """The files copied by one export operation."""

    task_id: str
    output_dir: Path
    artifacts: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "output_dir": str(self.output_dir),
            "artifacts": list(self.artifacts),
        }


def export_task_artifacts(
    project_root: Path,
    task_id: str,
    output_dir: Path,
) -> ExportResult:
    """Copy state-declared delivery artifacts into a new output directory."""
    root = project_root.resolve()
    if not root.is_dir():
        raise _export_error(
            "export_project_root_invalid",
            "Project root must be an existing directory.",
            "Use an existing project directory for export.",
        )

    task_root = task_path(root, task_id)
    if not task_root.is_dir():
        raise _export_error(
            "export_task_missing",
            "Task workspace does not exist.",
            "Initialize the requested task before exporting its artifacts.",
        )
    try:
        state = reconcile_state(task_root, load_state(task_root))
    except HanCodeError:
        raise _export_error(
            "export_state_invalid",
            "Task state is invalid and cannot be exported.",
            "Repair state.json before exporting task artifacts.",
        ) from None
    if state.inconsistent:
        raise _export_error(
            "export_state_inconsistent",
            "Task state and delivery artifacts are inconsistent.",
            "Reconcile task artifacts before exporting.",
        )

    artifact_names = tuple(
        name for name in _EXPORT_ARTIFACTS if state.artifacts.get(name, False)
    )
    if not artifact_names:
        raise _export_error(
            "export_artifacts_missing",
            "The task has no delivery artifacts to export.",
            "Complete at least one delivery artifact before exporting.",
        )
    sources = tuple(task_root / name for name in artifact_names)
    if any(_is_link(source) or not source.is_file() for source in sources):
        raise _export_error(
            "export_state_inconsistent",
            "A state-declared delivery artifact is missing or linked.",
            "Restore regular artifact files before exporting.",
        )

    raw_output = Path(os.path.abspath(output_dir))
    _validate_output_target(root, raw_output)
    output = raw_output.resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise _export_error(
            "export_output_unavailable",
            "The export destination parent cannot be created.",
            "Choose a writable destination outside the task workspace.",
        ) from None

    staging: Path | None = None
    try:
        staging = Path(tempfile.mkdtemp(prefix=".hancode-export-", dir=output.parent))
        for name, source in zip(artifact_names, sources):
            shutil.copy2(source, staging / name)
        if _is_link(output) or output.exists():
            raise _export_error(
                "export_output_exists",
                "Export destination already exists.",
                "Choose a new output directory; existing files are never overwritten.",
            )
        staging.rename(output)
        staging = None
    except HanCodeError:
        raise
    except OSError:
        raise _export_error(
            "export_copy_failed",
            "Delivery artifacts could not be exported atomically.",
            "Check destination permissions and retry with a new output directory.",
        ) from None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)

    return ExportResult(task_id=task_id, output_dir=output, artifacts=artifact_names)


@dataclass(frozen=True, slots=True)
class ProfileExportResult:
    """The files published by one profile export operation."""

    task_id: str
    profile: str
    output_dir: Path
    files: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "profile": self.profile,
            "output_dir": str(self.output_dir),
            "files": list(self.files),
        }


def export_task_profile(
    project_root: Path,
    task_id: str,
    output_dir: Path,
    profile: ExportProfile,
) -> ProfileExportResult:
    """Publish a task's artifacts for a specific audience profile (S14-R6).

    Each profile uses an explicit allow-list and writes a self-describing
    manifest. Publication is atomic (stage then rename) and never overwrites an
    existing destination. Runtime internals (state, trace, memory, credentials,
    raw checkpoints) are never included.
    """
    if not isinstance(profile, ExportProfile):
        raise _export_error(
            "export_profile_invalid",
            "Export profile must be submission, learning, or audit.",
            "Pass an explicit ExportProfile value.",
        )
    root = project_root.resolve()
    if not root.is_dir():
        raise _export_error(
            "export_project_root_invalid",
            "Project root must be an existing directory.",
            "Use an existing project directory for export.",
        )
    task_root = task_path(root, task_id)
    if not task_root.is_dir():
        raise _export_error(
            "export_task_missing",
            "Task workspace does not exist.",
            "Initialize the requested task before exporting its artifacts.",
        )
    try:
        state = reconcile_state(task_root, load_state(task_root))
    except HanCodeError:
        raise _export_error(
            "export_state_invalid",
            "Task state is invalid and cannot be exported.",
            "Repair state.json before exporting task artifacts.",
        ) from None

    from hancode.app.delivery_service import DeliveryService

    decision = DeliveryService().evaluate_learning(root, task_id)

    staged_files: dict[str, bytes] = {}
    if profile is ExportProfile.SUBMISSION:
        staged_files = _stage_submission(root, task_root, state, decision)
    elif profile is ExportProfile.LEARNING:
        staged_files = _stage_learning(task_root, state, decision)
    else:
        staged_files = _stage_audit(task_root, decision)

    if not staged_files:
        raise _export_error(
            "export_artifacts_missing",
            "The task has no artifacts to export for this profile.",
            "Complete the required artifacts before exporting.",
        )

    raw_output = Path(os.path.abspath(output_dir))
    _validate_output_target(root, raw_output)
    output = raw_output.resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise _export_error(
            "export_output_unavailable",
            "The export destination parent cannot be created.",
            "Choose a writable destination outside the task workspace.",
        ) from None

    staging: Path | None = None
    try:
        staging = Path(tempfile.mkdtemp(prefix=".hancode-export-", dir=output.parent))
        for name, payload in staged_files.items():
            (staging / name).write_bytes(payload)
        if _is_link(output) or output.exists():
            raise _export_error(
                "export_output_exists",
                "Export destination already exists.",
                "Choose a new output directory; existing files are never overwritten.",
            )
        staging.rename(output)
        staging = None
    except HanCodeError:
        raise
    except OSError:
        raise _export_error(
            "export_copy_failed",
            "Artifacts could not be exported atomically.",
            "Check destination permissions and retry with a new output directory.",
        ) from None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)

    return ProfileExportResult(
        task_id=task_id,
        profile=profile.value,
        output_dir=output,
        files=tuple(sorted(staged_files)),
    )


def _read_artifact_bytes(task_root: Path, name: str) -> bytes | None:
    source = task_root / name
    if _is_link(source) or not source.is_file():
        return None
    try:
        return source.read_bytes()
    except OSError:
        return None


def _stage_submission(
    project_root: Path,
    task_root: Path,
    state: object,
    decision: object,
) -> dict[str, bytes]:
    staged: dict[str, bytes] = {}
    deliverables = _read_artifact_bytes(task_root, "DELIVERABLES.md")
    if deliverables is not None:
        staged["DELIVERABLES.md"] = deliverables
    readme = project_root / "README.md"
    if readme.is_file() and not _is_link(readme):
        try:
            staged["README.md"] = readme.read_bytes()
        except OSError:
            pass
    # submission_paths (exact project-relative files) are copied when present.
    try:
        from hancode.core.config import load_config

        for relative in load_config(project_root, task_root.name).submission_paths:
            candidate = (project_root / relative).resolve()
            if candidate.is_file() and not _is_link(candidate):
                staged[candidate.name] = candidate.read_bytes()
    except Exception:  # noqa: BLE001 - submission paths are optional
        pass
    staged["delivery-manifest.json"] = _manifest_bytes(
        "submission", state, decision
    )
    return staged


def _stage_learning(
    task_root: Path,
    state: object,
    decision: object,
) -> dict[str, bytes]:
    staged: dict[str, bytes] = {}
    for name in _LEARNING_ARTIFACTS:
        payload = _read_artifact_bytes(task_root, name)
        if payload is not None:
            staged[name] = payload
    final_diff = _read_artifact_bytes(task_root, "final.diff")
    if final_diff is not None:
        staged["final.diff"] = final_diff
    staged["LEARNING_INDEX.md"] = _learning_index_bytes(staged)
    staged["learning-manifest.json"] = _manifest_bytes("learning", state, decision)
    return staged


def _stage_audit(task_root: Path, decision: object) -> dict[str, bytes]:
    staged: dict[str, bytes] = {}
    evidence = task_root / "learning" / "evidence.json"
    if evidence.is_file() and not _is_link(evidence):
        try:
            staged["evidence.json"] = evidence.read_bytes()
        except OSError:
            pass
    traceability = task_root / "learning" / "traceability.json"
    if traceability.is_file() and not _is_link(traceability):
        try:
            staged["traceability.json"] = traceability.read_bytes()
        except OSError:
            pass
    staged["audit-manifest.json"] = _manifest_bytes("audit", None, decision)
    return staged


def _manifest_bytes(profile: str, state: object, decision: object) -> bytes:
    manifest: dict[str, object] = {"profile": profile}
    if decision is not None:
        manifest["status"] = getattr(getattr(decision, "status", None), "value", None)
        manifest["submission_eligible"] = getattr(
            decision, "submission_eligible", None
        )
        manifest["learning_contract_status"] = getattr(
            decision, "learning_contract_status", None
        )
        manifest["blockers"] = list(getattr(decision, "blockers", ()))
        manifest["learning_warnings"] = list(getattr(decision, "learning_warnings", ()))
        manifest["evidence_digest"] = getattr(decision, "latest_diff_sha256", None)
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _learning_index_bytes(staged: dict[str, bytes]) -> bytes:
    lines = ["# 学习资料索引\n"]
    for name in _LEARNING_ARTIFACTS:
        if name in staged:
            lines.append(f"- [{name}]({name})")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _validate_output_target(project_root: Path, output: Path) -> None:
    if _has_link_component(output):
        raise _export_error(
            "export_output_link_not_allowed",
            "Export destination contains a symbolic link or junction.",
            "Choose a destination path whose existing components are regular directories.",
        )
    hancode_root = (project_root / ".hancode").resolve()
    resolved_output = output.resolve()
    if resolved_output == hancode_root or hancode_root in resolved_output.parents:
        raise _export_error(
            "export_output_inside_workspace",
            "Export destination must not be inside the runtime workspace.",
            "Choose a destination outside .hancode.",
        )
    if output.exists():
        raise _export_error(
            "export_output_exists",
            "Export destination already exists.",
            "Choose a new output directory; existing files are never overwritten.",
        )


def _has_link_component(path: Path) -> bool:
    return any(_is_link(component) for component in (path, *path.parents))


def _is_link(path: Path) -> bool:
    try:
        junction_probe = getattr(path, "is_junction", None)
        return path.is_symlink() or (
            bool(junction_probe()) if callable(junction_probe) else False
        )
    except (AttributeError, OSError, RuntimeError):
        return True


def _export_error(error_code: str, message: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="deliver",
            denied_rule="delivery_export_boundary",
            suggested_fix=suggested_fix,
        )
    )
