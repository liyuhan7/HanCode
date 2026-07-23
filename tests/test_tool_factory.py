from __future__ import annotations

from pathlib import Path
import subprocess

from hancode.core.actions import Action, ActionType
from hancode.core.config import load_config
from hancode.core.models import Phase
from hancode.tooling.test_tools import run_tests
from hancode.tooling.factory import build_default_tool_registry
from hancode.storage.workspace import init_project_workspace


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
    test_result = registry.dispatch(_action("run_tests", {}))

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


def _action(name: str, args: dict[str, object]) -> Action:
    return Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name=name,
        args=args,
        reason="test",
    )
