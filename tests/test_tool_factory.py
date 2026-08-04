from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess

from hancode.core.actions import Action, ActionType
from hancode.core.config import load_config
from hancode.core.memory import MemoryBlob, MemoryKind, MemoryRecordDraft
from hancode.core.models import Phase
from hancode.core.state import load_state, save_state
from hancode.core.test_strategy import TestCoverageItem
from hancode.core.test_remediation import FailureCategory
from hancode.runtime.test_remediation import build_test_failure_record
from hancode.storage.test_remediations import TestRemediationStore
from hancode.storage.test_strategies import TestStrategyStore
from hancode.storage.memory import FilesystemMemoryStore
from hancode.tooling.test_tools import run_tests
from hancode.tooling.factory import build_default_tool_catalog, build_default_tool_registry
from hancode.core.tool_specs import TOOL_SPEC_BY_NAME
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def test_default_registry_registers_file_edit_and_configured_test_tools(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    project_file = tmp_path / ".hancode" / "project.json"
    project_file.write_text(
        project_file.read_text(encoding="utf-8").replace(
            '"assignment_name": "Harness"',
            '"assignment_name": "Harness",\n  "test_command": "pytest -q"',
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="1 passed\n", stderr="")

    registry = build_default_tool_registry(
        load_config(tmp_path),
        run_tests_tool=lambda command: run_tests(tmp_path, command, runner=runner),
    )
    (tmp_path / "notes.txt").write_text("notes\n", encoding="utf-8")

    read_result = registry.dispatch(_action("read_file", {"path": "notes.txt"}))
    list_result = registry.dispatch(_action("list_files", {"path": "."}))
    search_result = registry.dispatch(_action("search_text", {"query": "notes"}))
    write_result = registry.dispatch(
        _action("write_file", {"path": "new.txt", "content": "new\n"})
    )
    edit_result = registry.dispatch(
        _action(
            "edit_file",
            {"path": "notes.txt", "old_string": "notes", "new_string": "updated"},
        )
    )
    test_result = registry.dispatch(
        _action("run_tests", {"command": "pytest -q"})
    )

    assert read_result.success is True
    assert list_result.success is True
    assert search_result.success is True
    assert write_result.success is True
    assert edit_result.success is True
    assert test_result.success is True
    assert test_result.command == "pytest -q"
    assert calls == [["pytest", "-q"]]

    dynamic_result = registry.dispatch(
        _action("run_tests", {"command": "python -m pytest"})
    )

    assert dynamic_result.success is True
    assert dynamic_result.command == "python -m pytest"
    assert calls == [["pytest", "-q"], ["python", "-m", "pytest"]]


def test_task_registry_records_test_strategy(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    init_task_workspace(tmp_path, "task-001", goal="Test behavior.")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert True\n",
        encoding="utf-8",
    )
    registry = build_default_tool_registry(load_config(tmp_path, "task-001"))

    result = registry.dispatch(
        _action(
            "record_test_strategy",
            {
                "command": "python -m pytest tests/test_app.py -q",
                "framework": "pytest",
                "test_files": ["tests/test_app.py"],
                "coverage": [
                    {
                        "requirement": "REQ-001",
                        "verification": "test_app",
                    }
                ],
            },
        )
    )

    assert result.success is True
    assert isinstance(result.output, dict)
    assert len(result.output["test_strategy_digest"]) == 64


def test_task_registry_binds_memory_tools_to_current_task(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    init_task_workspace(tmp_path, "task-001", goal="Recover memory.")
    record = FilesystemMemoryStore(tmp_path).append(
        "task-001",
        MemoryRecordDraft(
            phase=Phase.CODE,
            kind=MemoryKind.TOOL_RESULT,
            tool_name="get_diff",
            success=True,
            summary="Needle summary.",
            blob=MemoryBlob.text("historical body\n"),
        ),
    ).record
    registry = build_default_tool_registry(load_config(tmp_path, "task-001"))

    searched = registry.dispatch(_action("memory_search", {"query": "needle"}))
    read = registry.dispatch(_action("memory_read", {"memory_id": record.memory_id}))

    assert searched.success is True
    assert searched.output["hits"][0]["memory_id"] == record.memory_id  # type: ignore[index]
    assert read.success is True
    assert read.output["content"] == "historical body\n"  # type: ignore[index]


def test_default_provider_catalog_projects_memory_tool_specs(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    catalog = {tool.name: tool for tool in build_default_tool_catalog(load_config(tmp_path))}

    for name in ("memory_read", "memory_search"):
        assert catalog[name].args_schema == TOOL_SPEC_BY_NAME[name].args_schema
        assert TOOL_SPEC_BY_NAME[name].allowed_phases == frozenset(Phase)
        assert TOOL_SPEC_BY_NAME[name].read_only is True


def test_task_registry_records_remediation_for_latest_failure(tmp_path: Path) -> None:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    task_root = init_task_workspace(tmp_path, "task-001", goal="Repair behavior.")
    failure = build_test_failure_record(
        task_id="task-001",
        attempt_seq=1,
        strategy_digest=None,
        command_argv=None,
        category=FailureCategory.ASSERTION_FAILURE,
        exit_code=1,
        timed_out=False,
        passed_count=0,
        failed_count=1,
        output="FAILED tests/test_app.py::test_app\nAssertionError",
        project_root=tmp_path,
    )
    TestRemediationStore(tmp_path).save_failure(failure)
    save_state(
        task_root,
        replace(
            load_state(task_root),
            current_phase=Phase.REVIEW,
            latest_test_status="failed",
            latest_test_failure_digest=failure.digest,
            test_attempt_seq=1,
        ),
    )
    registry = build_default_tool_registry(load_config(tmp_path, "task-001"))

    result = registry.dispatch(
        _action(
            "record_remediation",
            {
                "failure_digest": failure.digest,
                "kind": "modify_source",
                "diagnosis": "Implementation does not satisfy the assertion.",
                "planned_paths": ["src/app.py"],
                "question": None,
            },
        )
    )

    assert result.success is True
    decision = TestRemediationStore(tmp_path).load_remediation("task-001")
    assert decision.failure_digest == failure.digest
    assert decision.planned_paths == ("src/app.py",)


def test_task_registry_normalizes_remediation_paths_and_rejects_environment_source_fix(
    tmp_path: Path,
) -> None:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    task_root = init_task_workspace(tmp_path, "task-001", goal="Repair runner.")
    failure = build_test_failure_record(
        task_id="task-001",
        attempt_seq=1,
        strategy_digest=None,
        command_argv=None,
        category=FailureCategory.ENVIRONMENT_ERROR,
        exit_code=1,
        timed_out=False,
        passed_count=0,
        failed_count=0,
        output="PermissionError: [WinError 5] Access is denied",
        project_root=tmp_path,
    )
    TestRemediationStore(tmp_path).save_failure(failure)
    save_state(
        task_root,
        replace(
            load_state(task_root),
            current_phase=Phase.REVIEW,
            latest_test_status="failed",
            latest_test_failure_digest=failure.digest,
        ),
    )
    registry = build_default_tool_registry(load_config(tmp_path, "task-001"))

    rejected = registry.dispatch(
        _action(
            "record_remediation",
            {
                "failure_digest": failure.digest,
                "kind": "modify_source",
                "diagnosis": "Attempt a source fix.",
                "planned_paths": ["src\\app.py"],
                "question": None,
            },
        )
    )
    accepted = registry.dispatch(
        _action(
            "record_remediation",
            {
                "failure_digest": failure.digest,
                "kind": "replace_test_strategy",
                "diagnosis": "Use an installed Python runner.",
                "planned_paths": [],
                "question": None,
            },
        )
    )

    assert rejected.success is False
    assert accepted.success is True


def test_task_registry_rejects_command_mismatch_without_dispatch(
    tmp_path: Path,
) -> None:
    init_project_workspace(tmp_path, "project-001", "SE", "Harness")
    task_root = init_task_workspace(tmp_path, "task-001", goal="Test behavior.")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_app():\n    assert True\n",
        encoding="utf-8",
    )
    strategy = TestStrategyStore(tmp_path).record(
        "task-001",
        command="python -m pytest tests/test_app.py -q",
        framework="pytest",
        test_files=("tests/test_app.py",),
        coverage=(
            TestCoverageItem(
                requirement="REQ-001",
                verification="test_app",
            ),
        ),
    )
    save_state(
        task_root,
        replace(load_state(task_root), test_strategy_digest=strategy.digest),
    )
    calls: list[str | None] = []
    registry = build_default_tool_registry(
        load_config(tmp_path, "task-001"),
        run_tests_tool=lambda command: (
            calls.append(command)
            or run_tests(tmp_path, command)
        ),
    )

    result = registry.dispatch(
        _action("run_tests", {"command": "python -m pytest -q"})
    )

    assert result.success is False
    assert result.output == {"strategy_error": "test_command_mismatch"}
    assert calls == []


def _action(name: str, args: dict[str, object]) -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=name,
        args=args,
        reason="test",
    )
