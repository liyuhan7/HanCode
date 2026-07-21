from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import hancode.runtime.context as context_module
from hancode.core.config import load_config
from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.runtime.context import ContextBuilder, build_context
from hancode.core.errors import HanCodeError
from hancode.core.models import Phase
from hancode.core.state import TaskState, load_state
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def test_context_builder_includes_course_context(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    (project_root / ".hancode" / "course_context.md").write_text(
        "# Course Context\n\nFollow the grading rubric.\n", encoding="utf-8"
    )
    config = load_config(project_root, "task-001")
    state = _state(task_root, goal="Implement the assignment.")

    context = build_context(project_root, "task-001", Phase.SPEC, config, state=state)
    adapter_context = ContextBuilder(project_root, config).build(
        task_id="task-001", phase=Phase.SPEC, state=state
    )

    assert context == adapter_context
    assert context["task_id"] == "task-001"
    assert context["phase"] == "spec"
    assert context["goal"] == "Implement the assignment."
    assert context["task_workspace"] == ".hancode/tasks/task-001"
    assert context["artifact_targets"]["SPEC.md"] == ".hancode/tasks/task-001/SPEC.md"
    assert context["sections"]["course_context"] == "# Course Context\n\nFollow the grading rubric.\n"
    assert context["sections"]["project_memory"] == "# Project Memory\n"
    assert context["sections"]["experience"] == "# Experience\n"
    assert "SPEC.md" not in context["sections"]
    assert context["context_risks"] == []
    assert context["truncation"] == {
        "applied": False,
        "omitted_sections": [],
        "truncated_sections": [],
    }


def test_code_phase_context_requires_spec_and_plan(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-001")

    with pytest.raises(HanCodeError) as error:
        build_context(
            project_root,
            "task-001",
            Phase.CODE,
            config,
            state=_state(task_root, goal="Implement the assignment."),
        )

    assert error.value.structured_error.error_code == "context_required_artifact_missing"
    assert error.value.structured_error.phase == "code"
    assert error.value.structured_error.denied_rule == "required_artifact_available"


def test_required_artifact_link_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root, task_root = _workspace(tmp_path)
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("SPEC.md", "PLAN.md"),
    )
    monkeypatch.setattr(context_module, "_is_link", lambda path: path.name == "SPEC.md")

    with pytest.raises(HanCodeError) as error:
        build_context(project_root, "task-001", Phase.CODE, config, state=state)

    assert error.value.structured_error.error_code == "context_required_artifact_unreadable"


def test_context_configuration_error_uses_requested_phase(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-002")

    with pytest.raises(HanCodeError) as error:
        build_context(
            project_root,
            "task-001",
            Phase.CODE,
            config,
            state=_state(task_root, goal="Implement the assignment."),
        )

    assert error.value.structured_error.error_code == "context_task_mismatch"
    assert error.value.structured_error.phase == "code"


def test_spec_phase_requires_course_context(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    (project_root / ".hancode" / "course_context.md").unlink()
    config = load_config(project_root, "task-001")

    with pytest.raises(HanCodeError) as error:
        build_context(
            project_root,
            "task-001",
            Phase.SPEC,
            config,
            state=_state(task_root, goal="Implement the assignment."),
        )

    assert error.value.structured_error.error_code == "context_required_artifact_missing"
    assert error.value.structured_error.denied_rule == "course_context_required"


def test_plan_phase_context_includes_spec_course_memory_and_test_command(
    tmp_path: Path,
) -> None:
    project_root, task_root = _workspace(tmp_path)
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    _set_project_config(project_root, test_command="uv run pytest")
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("SPEC.md",),
    )

    context = build_context(project_root, "task-001", Phase.PLAN, config, state=state)

    assert context["sections"]["spec"] == "# Spec\n"
    assert context["sections"]["course_context"] == "# Course Context\n"
    assert context["sections"]["project_memory"] == "# Project Memory\n"
    assert context["sections"]["experience"] == "# Experience\n"
    assert context["sections"]["test_command"] == "uv run pytest"
    assert json.loads(context["sections"]["project_structure"]) == {
        "writable_roots": ["src", "tests"]
    }


def test_code_phase_includes_policy_and_changed_source_snippets(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    (project_root / "src").mkdir()
    (project_root / "src" / "main.py").write_text(
        "VALUE = 1\nAPI_KEY=live-source-secret\n", encoding="utf-8"
    )
    (project_root / "assignment.md").write_text("teacher-only\n", encoding="utf-8")
    (task_root / "SPEC.md").write_text(
        "# Spec\nAPI_KEY=live-artifact-secret\n", encoding="utf-8"
    )
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("SPEC.md", "PLAN.md"),
        files_changed=("src/main.py", "assignment.md"),
    )

    context = build_context(project_root, "task-001", Phase.CODE, config, state=state)

    assert context["sections"]["spec"] == "# Spec\nAPI_KEY=[REDACTED]\n"
    assert context["sections"]["plan"] == "# Plan\n"
    assert json.loads(context["sections"]["allowed_tools"]) == [
        "edit_file",
        "list_files",
        "read_file",
        "run_tests",
        "search_text",
        "write_file",
    ]
    assert "assignment" in json.loads(context["sections"]["protected_patterns"])
    assert json.loads(context["sections"]["writable_roots"]) == ["src", "tests"]
    assert json.loads(context["sections"]["source_snippets"]) == {
        "src/main.py": "VALUE = 1\nAPI_KEY=[REDACTED]\n"
    }
    assert "live-source-secret" not in _canonical_context(context)
    assert "live-artifact-secret" not in _canonical_context(context)


def test_review_phase_includes_test_report_changed_files_and_checkpoint(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    (task_root / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (task_root / "TEST_REPORT.md").write_text("# Tests\n\n1 failed\n", encoding="utf-8")
    _write_checkpoint_manifest(task_root)
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("SPEC.md", "PLAN.md", "TEST_REPORT.md"),
        files_changed=("src/main.py",),
        latest_checkpoint="ckpt-001",
    )

    context = build_context(project_root, "task-001", Phase.REVIEW, config, state=state)

    assert context["sections"]["test_report"] == "# Tests\n\n1 failed\n"
    assert json.loads(context["sections"]["changed_files"]) == ["src/main.py"]
    assert json.loads(context["sections"]["checkpoint"]) == {
        "checkpoint_id": "ckpt-001",
        "files": ["src/main.py"],
        "rollback_available": True,
        "status": "committed",
    }


def test_test_phase_includes_plan_changed_files_checkpoint_and_test_command(
    tmp_path: Path,
) -> None:
    project_root, task_root = _workspace(tmp_path)
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    _write_checkpoint_manifest(task_root)
    _set_project_config(project_root, test_command="uv run pytest")
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("PLAN.md",),
        files_changed=("src/main.py",),
        latest_checkpoint="ckpt-001",
    )

    context = build_context(project_root, "task-001", Phase.TEST, config, state=state)

    assert context["sections"]["plan"] == "# Plan\n"
    assert context["sections"]["test_command"] == "uv run pytest"
    assert json.loads(context["sections"]["changed_files"]) == ["src/main.py"]
    assert json.loads(context["sections"]["checkpoint"])["checkpoint_id"] == "ckpt-001"


def test_test_phase_requires_a_configured_test_command(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    (task_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    config = load_config(project_root, "task-001")
    state = _state(task_root, goal="Implement the assignment.", artifact_names=("PLAN.md",))

    with pytest.raises(HanCodeError) as error:
        build_context(project_root, "task-001", Phase.TEST, config, state=state)

    assert error.value.structured_error.error_code == "context_required_artifact_missing"
    assert error.value.structured_error.denied_rule == "test_command_required"


def test_deliver_phase_includes_required_artifacts_and_trace_summary(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    _set_project_config(project_root, max_trace_events=2)
    for artifact_name, content in {
        "SPEC.md": "# Spec\n",
        "PLAN.md": "# Plan\n",
        "TEST_REPORT.md": "# Tests\n",
        "REVIEW.md": "# Review\n",
    }.items():
        (task_root / artifact_name).write_text(content, encoding="utf-8")
    _write_trace(task_root, "task-001", 1, "phase_started", "running", None)
    _write_trace(
        task_root,
        "task-001",
        2,
        "tool_failed",
        "failed",
        "Authorization: Bearer trace-secret",
        {"api_key": "trace-api-key"},
    )
    _write_trace(task_root, "task-001", 3, "tool_completed", "succeeded", None)
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md"),
    )

    context = build_context(project_root, "task-001", Phase.DELIVER, config, state=state)

    assert context["sections"]["spec"] == "# Spec\n"
    assert context["sections"]["plan"] == "# Plan\n"
    assert context["sections"]["test_report"] == "# Tests\n"
    assert context["sections"]["review"] == "# Review\n"
    assert json.loads(context["sections"]["trace_summary"]) == [
        {
            "error_summary": "Authorization: Bearer [REDACTED]",
            "event_id": "evt-000002",
            "event_type": "tool_failed",
            "phase": "test",
            "seq": 2,
            "state_transition": {"api_key": "[REDACTED]"},
            "status": "failed",
        },
        {
            "error_summary": None,
            "event_id": "evt-000003",
            "event_type": "tool_completed",
            "phase": "test",
            "seq": 3,
            "state_transition": None,
            "status": "succeeded",
        },
    ]
    assert "trace-secret" not in _canonical_context(context)


def test_context_builder_does_not_mix_other_task_trace(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    for artifact_name in ("SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md"):
        (task_root / artifact_name).write_text(f"# {artifact_name}\n", encoding="utf-8")
    _write_trace(task_root, "task-002", 1, "phase_started", "running", None)
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md"),
    )

    with pytest.raises(HanCodeError) as error:
        build_context(project_root, "task-001", Phase.DELIVER, config, state=state)

    assert error.value.structured_error.error_code == "context_trace_invalid"


def test_context_builder_rejects_oversized_trace_event(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    _set_project_config(project_root, max_context_chars=500)
    for artifact_name in ("SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md"):
        (task_root / artifact_name).write_text(f"# {artifact_name}\n", encoding="utf-8")
    _write_trace(task_root, "task-001", 1, "tool_failed", "failed", "x" * 1000)
    config = load_config(project_root, "task-001")
    state = _state(
        task_root,
        goal="Implement the assignment.",
        artifact_names=("SPEC.md", "PLAN.md", "TEST_REPORT.md", "REVIEW.md"),
    )

    with pytest.raises(HanCodeError) as error:
        build_context(project_root, "task-001", Phase.DELIVER, config, state=state)

    assert error.value.structured_error.error_code == "context_trace_invalid"


def test_context_builder_respects_max_context_chars(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    _set_project_config(project_root, max_context_chars=800)
    (project_root / ".hancode" / "course_context.md").write_text(
        "COURSE-" + "c" * 1000, encoding="utf-8"
    )
    (project_root / ".hancode" / "project_memory.md").write_text(
        "MEMORY-" + "m" * 1000, encoding="utf-8"
    )
    config = load_config(project_root, "task-001")
    context = build_context(
        project_root,
        "task-001",
        Phase.SPEC,
        config,
        state=_state(task_root, goal="Implement the assignment."),
    )

    assert len(_canonical_context(context)) <= 800
    assert "COURSE-" in context["sections"]["course_context"]
    assert context["sections"]["course_context"].endswith("[TRUNCATED]")
    assert "project_memory" not in context["sections"]
    assert context["truncation"]["applied"] is True
    assert "project_memory" in context["truncation"]["omitted_sections"]
    assert "task_workspace" in context["truncation"]["omitted_sections"]
    assert "course_context" in context["truncation"]["truncated_sections"]


def test_context_builder_includes_answered_interaction_history(tmp_path: Path) -> None:
    project_root, task_root = _workspace(tmp_path)
    config = load_config(project_root, "task-001")
    state = replace(
        _state(task_root, goal="Implement the assignment."),
        interaction_seq=1,
        interactions=(
            InteractionRecord(
                interaction_id="ask-000001",
                phase=Phase.SPEC,
                question="Which file should be changed?",
                answer="src/main.py",
                status=InteractionStatus.ANSWERED,
            ),
        ),
    )

    context = build_context(project_root, "task-001", Phase.SPEC, config, state=state)

    assert context["interaction_history"] == [
        {
            "interaction_id": "ask-000001",
            "phase": "spec",
            "question": "Which file should be changed?",
            "answer": "src/main.py",
        }
    ]


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "SE", "Harness")
    return project_root, init_task_workspace(project_root, "task-001")


def _state(
    task_root: Path,
    *,
    goal: str,
    artifact_names: tuple[str, ...] = (),
    files_changed: tuple[str, ...] = (),
    latest_checkpoint: str | None = None,
) -> TaskState:
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    for artifact_name in artifact_names:
        artifacts[artifact_name] = True
    return replace(
        state,
        goal=goal,
        artifacts=artifacts,
        files_changed=files_changed,
        latest_checkpoint=latest_checkpoint,
    )


def _write_checkpoint_manifest(task_root: Path) -> None:
    checkpoint_root = task_root / "checkpoints" / "ckpt-001"
    checkpoint_root.mkdir()
    (checkpoint_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "project-001",
                "task_id": "task-001",
                "phase": "code",
                "checkpoint_id": "ckpt-001",
                "reason": "Before update.",
                "created_at": "2026-07-13T00:00:00+00:00",
                "status": "committed",
                "files": [
                    {
                        "path": "src/main.py",
                        "action": "modify",
                        "before_snapshot": "files/src/main.py",
                        "before_sha256": "a" * 64,
                        "after_sha256": "b" * 64,
                    }
                ],
                "rollback_available": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _set_project_config(project_root: Path, **overrides: object) -> None:
    path = project_root / ".hancode" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(overrides)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_trace(
    task_root: Path,
    task_id: str,
    seq: int,
    event_type: str,
    status: str,
    error_summary: str | None,
    state_transition: dict[str, object] | None = None,
) -> None:
    event = {
        "event_id": f"evt-{seq:06d}",
        "seq": seq,
        "event_type": event_type,
        "task_id": task_id,
        "phase": "test",
        "timestamp": "2026-07-13T00:00:00+00:00",
        "status": status,
        "action": {"token": "must-not-be-loaded"},
        "observation": {"output": "must-not-be-loaded"},
        "error_summary": error_summary,
        "state_transition": state_transition,
    }
    with (task_root / "trace.jsonl").open("a", encoding="utf-8") as trace_file:
        trace_file.write(json.dumps(event, ensure_ascii=False) + "\n")


def _canonical_context(context: dict[str, object]) -> str:
    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
