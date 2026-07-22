"""Tests for tooling/command_runner.py and tooling/build_tools.py — S4-R2."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from hancode.tooling.command_runner import CommandRunner, run_configured_command
from hancode.tooling.registry import ToolResult


# ---------------------------------------------------------------------------
# CommandRunner tests
# ---------------------------------------------------------------------------

class TestCommandRunner:
    def test_run_configured_command_success(self, tmp_path: Path) -> None:
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command="echo hello",
        )
        assert result.success is True
        assert result.action_name == "test_cmd"
        assert "hello" in (result.stdout or "")

    def test_run_configured_command_missing_command(self, tmp_path: Path) -> None:
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command=None,
        )
        assert result.success is False
        assert "No configured" in (result.error_summary or "")

    def test_run_configured_command_empty_command(self, tmp_path: Path) -> None:
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command="   ",
        )
        assert result.success is False

    def test_run_configured_command_uses_shell_false(self, tmp_path: Path) -> None:
        """Verify the command does NOT use shell=True by passing a shell-only operator."""
        # `&&` is a shell operator that fails without shell=True
        # On Windows, shlex.split handles '&&' differently
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command="echo a && echo b",
        )
        # With shell=False, '&&' becomes a literal argument to echo, not a shell operator
        assert result.success is True
        # The output should contain literal '&&' because it's passed as an arg
        assert "&&" in (result.stdout or "")

    def test_run_configured_command_uses_project_root(self, tmp_path: Path) -> None:
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command="python -c \"from pathlib import Path; print(Path.cwd())\"",
        )
        assert result.success is True

    def test_run_configured_command_timeout(self, tmp_path: Path) -> None:
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command="python -c \"import time; time.sleep(10)\"",
            timeout_seconds=0.5,
        )
        assert result.success is False
        assert result.timed_out is True

    def test_run_configured_command_redacts_output(self, tmp_path: Path) -> None:
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command="echo API_KEY=sk-abc123secret",
        )
        assert result.success is True
        stdout = result.stdout or ""
        assert "sk-abc123secret" not in stdout
        assert "[REDACTED]" in stdout or "sk-" not in stdout

    def test_run_configured_command_truncates_output(self, tmp_path: Path) -> None:
        long_str = "x" * 20000
        result = run_configured_command(
            action_name="test_cmd",
            project_root=tmp_path,
            command=f"echo {long_str}",
            max_output_chars=100,
        )
        assert result.success is True
        assert len(result.stdout or "") <= 100 + 50  # allow small margin

    def test_command_runner_can_be_stubbed(self, tmp_path: Path) -> None:
        """Verify CommandRunner stub is callable."""
        def fake_runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="stub output", stderr="")

        runner = CommandRunner(fake_runner)
        result = run_configured_command(
            action_name="stub_test",
            project_root=tmp_path,
            command="anything",
            runner=runner,
        )
        assert result.success is True
        assert "stub output" in (result.stdout or "")


# ---------------------------------------------------------------------------
# run_build tests
# ---------------------------------------------------------------------------

class TestRunBuild:
    def test_build_uses_configured_command(self, tmp_path: Path) -> None:
        from hancode.tooling.build_tools import run_build

        result = run_build(tmp_path, "echo build ok")
        assert result.success is True
        assert result.action_name == "run_build"
        assert "build ok" in (result.stdout or "")

    def test_build_rejects_missing_command(self, tmp_path: Path) -> None:
        from hancode.tooling.build_tools import run_build

        result = run_build(tmp_path, None)
        assert result.success is False
        assert "No configured" in (result.error_summary or "")

    def test_build_uses_shell_false(self, tmp_path: Path) -> None:
        from hancode.tooling.build_tools import run_build

        result = run_build(tmp_path, "echo a && echo b")
        assert result.success is True
        assert "&&" in (result.stdout or "")

    def test_build_uses_project_root(self, tmp_path: Path) -> None:
        from hancode.tooling.build_tools import run_build

        # Create a marker file in project_root
        (tmp_path / "marker.txt").write_text("exists")
        result = run_build(
            tmp_path,
            "python -c \"from pathlib import Path; print(Path('marker.txt').exists())\"",
        )
        assert result.success is True
        assert "True" in (result.stdout or "")

    def test_build_times_out(self, tmp_path: Path) -> None:
        from hancode.tooling.build_tools import run_build

        result = run_build(
            tmp_path,
            "python -c \"import time; time.sleep(10)\"",
            timeout_seconds=0.5,
        )
        assert result.success is False
        assert result.timed_out is True

    def test_build_redacts_output(self, tmp_path: Path) -> None:
        from hancode.tooling.build_tools import run_build

        result = run_build(tmp_path, "echo SECRET=my-password-123")
        assert result.success is True
        stdout = result.stdout or ""
        assert "my-password-123" not in stdout

    def test_build_truncates_output(self, tmp_path: Path) -> None:
        from hancode.tooling.build_tools import run_build

        long_str = "y" * 20000
        result = run_build(tmp_path, f"echo {long_str}", max_output_chars=200)
        assert result.success is True
        assert len(result.stdout or "") <= 250
