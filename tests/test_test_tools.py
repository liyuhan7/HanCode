from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from hancode.tooling.test_tools import run_tests
from hancode.tooling.registry import ToolResult


def test_run_tests_executes_configured_command_as_argv(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args[0], 0, stdout="2 passed\n", stderr="")

    result = run_tests(tmp_path, "pytest -q", runner=runner)

    assert result == ToolResult(
        success=True,
        action_name="run_tests",
        exit_code=0,
        stdout="2 passed\n",
        stderr="",
        command="pytest -q",
    )
    assert calls == [
        {
            "args": (["pytest", "-q"],),
            "cwd": tmp_path,
            "text": True,
            "capture_output": True,
            "check": False,
            "shell": False,
            "timeout": 120.0,
        }
    ]


def test_run_tests_reports_timeout_without_leaking_command_arguments(tmp_path: Path) -> None:
    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="partial", stderr="late")

    result = run_tests(tmp_path, "pytest -q --token=secret-value", runner=runner)

    assert result == ToolResult(
        success=False,
        action_name="run_tests",
        error_summary="Test command timed out.",
        stdout="partial",
        stderr="late",
        timed_out=True,
        command="pytest -q --token=[REDACTED]",
    )


def test_run_tests_redacts_command_and_process_output(tmp_path: Path) -> None:
    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args[0],
            1,
            stdout="TOKEN=stdout-secret\n",
            stderr='{"api_key": "stderr-secret"}\n',
        )

    result = run_tests(
        tmp_path,
        "pytest -q --token=command-secret",
        runner=runner,
    )

    assert result.success is False
    assert result.command == "pytest -q --token=[REDACTED]"
    assert result.stdout == "TOKEN=[REDACTED]\n"
    assert result.stderr == '{"api_key": "[REDACTED]"}\n'
    assert "stdout-secret" not in str(result)
    assert "stderr-secret" not in str(result)


def test_run_tests_does_not_start_runner_without_a_configured_command(
    tmp_path: Path,
) -> None:
    calls: list[object] = []

    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0)

    for command in (None, "", "   "):
        result = run_tests(tmp_path, command, runner=runner)
        assert result.success is False
        assert result.command is None

    assert calls == []


@pytest.mark.parametrize(
    "command",
    [
        "gcc hello.c && ./a.out",
        "pytest -q || echo failed",
        "pytest -q | tee report.txt",
        "pytest -q > report.txt",
        "pytest -q < input.txt",
        "pytest -q; echo done",
        "pytest -q $(Get-Content secret.txt)",
        "pytest -q `Get-Content secret.txt`",
    ],
)
def test_run_tests_rejects_shell_syntax_without_starting_runner(
    tmp_path: Path, command: str
) -> None:
    calls: list[object] = []

    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0)

    result = run_tests(tmp_path, command, runner=runner)

    assert result.success is False
    assert result.error_summary == "Shell syntax is not supported for test commands."
    assert result.command is None
    assert calls == []
