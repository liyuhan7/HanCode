from __future__ import annotations

from pathlib import Path

import pytest

from hancode.core.config import HanCodeConfig
from hancode.policy.path_policy import PathClassifier, PathZone
from hancode.policy.path_security import is_sensitive_path


_DEFAULT_TASK_ROOT = object()

@pytest.mark.parametrize(
    "artifact_name",
    [
        "SPEC.md",
        "PLAN.md",
        "TEST_REPORT.md",
        "REVIEW.md",
        "KNOWLEDGE.md",
        "DELIVERABLES.md",
    ],
)
def test_classifies_task_artifact(tmp_path: Path, artifact_name: str) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify(f".hancode/tasks/task-001/{artifact_name}")

    assert result is PathZone.ARTIFACT


def test_classifies_source_file_under_configured_writable_root(tmp_path: Path) -> None:
    classifier = PathClassifier(_config(tmp_path, writable_roots=(tmp_path / "student",)))

    result = classifier.classify("student/main.py")

    assert result is PathZone.SOURCE


@pytest.mark.parametrize(
    "target",
    [
        "assignment.md",
        "tests/teacher_solution.py",
        "grading/check.py",
        "samples/input.csv",
        ".env",
        "credentials/local.json",
    ],
)
def test_classifies_course_file_as_protected(tmp_path: Path, target: str) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify(target)

    assert result is PathZone.PROTECTED


@pytest.mark.parametrize(
    "target",
    [
        "credentials/local.json",
        "secrets/config.yaml",
        "certificates/client.pem",
        "keys/id_rsa",
        "private.key",
        "server.crt",
        "client.cer",
        "bundle.der",
        "identity.p12",
        "identity.pfx",
        "access.token",
        "id_rsa",
        ".pem",
        ".key",
        ".crt",
    ],
)
def test_classifies_file_tool_credential_paths_as_protected(
    tmp_path: Path, target: str
) -> None:
    classifier = PathClassifier(
        _config(tmp_path, writable_roots=(tmp_path.resolve(),))
    )

    assert classifier.classify(target) is PathZone.PROTECTED


@pytest.mark.parametrize("target", [".pem", ".key", ".crt"])
def test_sensitive_path_rejects_hidden_credential_suffix_name(target: str) -> None:
    assert is_sensitive_path(target) is True


def test_protected_pattern_overrides_writable_root(tmp_path: Path) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify("tests/teacher_answer.py")

    assert result is PathZone.PROTECTED


def test_custom_protected_pattern_matches_case_and_backslash(tmp_path: Path) -> None:
    classifier = PathClassifier(
        _config(tmp_path, protected_patterns=("docs\\SPEC.md",))
    )

    result = classifier.classify("DOCS/spec.md")

    assert result is PathZone.PROTECTED


@pytest.mark.parametrize(
    "target",
    [
        ".hancode/tasks/task-001/state.json",
        ".hancode/tasks/task-001/history.jsonl",
        ".hancode/tasks/task-001/trace.jsonl",
        ".hancode/tasks/task-001/checkpoints/ckpt-001/manifest.json",
    ],
)
def test_classifies_task_machine_file_as_protected(tmp_path: Path, target: str) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify(target)

    assert result is PathZone.PROTECTED


def test_classifies_unknown_task_file_as_out_of_scope(tmp_path: Path) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify(".hancode/tasks/task-001/notes.txt")

    assert result is PathZone.OUT_OF_SCOPE


def test_unknown_task_file_is_not_source_when_hancode_is_writable(tmp_path: Path) -> None:
    classifier = PathClassifier(
        _config(tmp_path, writable_roots=(tmp_path / ".hancode",))
    )

    result = classifier.classify(".hancode/tasks/task-001/notes.txt")

    assert result is PathZone.OUT_OF_SCOPE


def test_rejects_task_artifact_name_with_wrong_case(tmp_path: Path) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify(".hancode/tasks/task-001/spec.md")

    assert result is PathZone.OUT_OF_SCOPE


def test_classifies_unlisted_project_file_as_out_of_scope(tmp_path: Path) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify("README.md")

    assert result is PathZone.OUT_OF_SCOPE


def test_task_artifacts_are_out_of_scope_without_task_root(tmp_path: Path) -> None:
    classifier = PathClassifier(_config(tmp_path, task_root=None))

    result = classifier.classify(".hancode/tasks/task-001/SPEC.md")

    assert result is PathZone.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "target",
    [
        "../outside.py",
        "C:\\outside\\main.py",
        "\\\\server\\share\\main.py",
    ],
)
def test_rejects_path_escape_or_absolute_path(tmp_path: Path, target: str) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify(target)

    assert result is PathZone.OUT_OF_SCOPE


def test_rejects_absolute_path_inside_workspace(tmp_path: Path) -> None:
    classifier = PathClassifier(_config(tmp_path))

    result = classifier.classify(str((tmp_path / "src" / "main.py").resolve()))

    assert result is PathZone.OUT_OF_SCOPE


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    link = project_root / "src" / "link.py"
    link.parent.mkdir()
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"File symlink unsupported in this environment: {exc}")
    classifier = PathClassifier(_config(project_root))

    result = classifier.classify("src/link.py")

    assert result is PathZone.OUT_OF_SCOPE


def test_symlink_alias_to_protected_file_is_protected(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    protected = project_root / "assignment.md"
    protected.write_text("assignment\n", encoding="utf-8")
    alias = project_root / "src" / "safe.py"
    alias.parent.mkdir()
    try:
        alias.symlink_to(protected)
    except OSError as exc:
        pytest.skip(f"File symlink unsupported in this environment: {exc}")
    classifier = PathClassifier(_config(project_root))

    result = classifier.classify("src/safe.py")

    assert result is PathZone.PROTECTED


def test_resolve_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    classifier = PathClassifier(_config(tmp_path))

    def fail_resolve(path: Path) -> Path:
        raise OSError("do-not-expose")

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    assert classifier.classify("src/main.py") is PathZone.OUT_OF_SCOPE


def _config(
    project_root: Path,
    *,
    task_root: Path | None | object = _DEFAULT_TASK_ROOT,
    writable_roots: tuple[Path, ...] | None = None,
    protected_patterns: tuple[str, ...] | None = None,
) -> HanCodeConfig:
    resolved_root = project_root.resolve()
    resolved_task_root = (
        resolved_root / ".hancode" / "tasks" / "task-001"
        if task_root is _DEFAULT_TASK_ROOT
        else task_root
    )
    return HanCodeConfig(
        project_root=resolved_root,
        hancode_root=resolved_root / ".hancode",
        allowed_workspace_root=resolved_root,
        task_root=resolved_task_root if isinstance(resolved_task_root, Path) else None,
        llm_provider="mock",
        model_name=None,
        credential_source=None,
        test_command=None,
        build_command=None,
        max_steps=30,
        retry_budget=2,
        max_checkpoints_per_task=5,
        max_observation_bytes=8192,
        max_context_chars=24000,
        max_trace_events=40,
        protected_patterns=protected_patterns
        or (
            "assignment.md",
            "tests/teacher_*",
            "grading/**",
            "samples/**",
            ".env",
            ".env.*",
            "credentials/**",
        ),
        writable_roots=writable_roots or (resolved_root / "src", resolved_root / "tests"),
    )
