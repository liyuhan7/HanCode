from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import keyring.errors
import pytest
from typer.testing import CliRunner

from hancode import cli
from hancode.credentials import CredentialProvider
from hancode.errors import HanCodeError, StructuredError
from hancode.state import load_state, save_state
from hancode.workspace import init_project_workspace, init_task_workspace


runner = CliRunner()


def _payload(result: object) -> dict[str, object]:
    output = getattr(result, "stdout")
    value = json.loads(output)
    assert isinstance(value, dict)
    return value


def test_cli_help_displays_supported_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "demo" in result.stdout
    assert "export" in result.stdout
    assert "auth" in result.stdout


def test_cli_auth_help_displays_four_commands() -> None:
    result = runner.invoke(cli.app, ["auth", "--help"])

    assert result.exit_code == 0
    assert "login" in result.stdout
    assert "status" in result.stdout
    assert "update" in result.stdout
    assert "clear" in result.stdout


class _FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.values[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self.values.pop((service_name, username), None)


def _fake_cli_provider(store: _FakeCredentialStore) -> CredentialProvider:
    return CredentialProvider(keyring_backend=store, environ={})


def test_cli_auth_status_returns_masked_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "cli-secret-9f2a"
    store = _FakeCredentialStore()
    store.set_password("hancode", "openai_compatible", secret)
    monkeypatch.setattr(cli, "credential_provider", _fake_cli_provider(store))

    result = runner.invoke(
        cli.app,
        ["auth", "status", "--provider", "openai_compatible"],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload == {
        "command": "auth status",
        "credential": {
            "configured": True,
            "masked_id": "****9f2a",
            "provider": "openai_compatible",
            "source": "keyring",
        },
        "status": "completed",
    }
    assert secret not in result.stdout


def test_cli_auth_login_uses_hidden_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeCredentialStore()
    provider = _fake_cli_provider(store)
    prompt_options: dict[str, object] = {}

    def fake_prompt(text: str, **kwargs: object) -> str:
        prompt_options.update(kwargs)
        return "login-secret-abcd"

    monkeypatch.setattr(cli, "credential_provider", provider)
    monkeypatch.setattr(cli.typer, "prompt", fake_prompt)

    result = runner.invoke(
        cli.app,
        ["auth", "login", "--provider", "openai_compatible"],
    )

    assert result.exit_code == 0
    assert prompt_options["hide_input"] is True
    assert store.get_password("hancode", "openai_compatible") == "login-secret-abcd"
    assert "login-secret-abcd" not in result.stdout


def test_cli_auth_login_rejects_unknown_provider_before_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_prompt(*args: object, **kwargs: object) -> str:
        raise AssertionError("unknown provider must not request a credential")

    monkeypatch.setattr(cli.typer, "prompt", fail_prompt)

    result = runner.invoke(
        cli.app,
        ["auth", "login", "--provider", "unknown"],
    )

    assert result.exit_code == 1
    assert _payload(result)["error"]["error_code"] == "credential_unknown_provider"  # type: ignore[index]


def test_cli_auth_login_for_mock_rejects_before_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "credential_provider", _fake_cli_provider(_FakeCredentialStore()))

    def fail_prompt(*args: object, **kwargs: object) -> str:
        raise AssertionError("mock provider must not request a credential")

    monkeypatch.setattr(cli.typer, "prompt", fail_prompt)

    result = runner.invoke(cli.app, ["auth", "login", "--provider", "mock"])

    assert result.exit_code == 1
    assert _payload(result)["error"]["error_code"] == "credential_not_required"  # type: ignore[index]


def test_cli_auth_login_keeps_json_on_stdout_with_real_hidden_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "real-prompt-secret-ef01"
    store = _FakeCredentialStore()
    monkeypatch.setattr(cli, "credential_provider", _fake_cli_provider(store))

    result = runner.invoke(
        cli.app,
        ["auth", "login", "--provider", "openai_compatible"],
        input=f"{secret}\n",
    )

    assert result.exit_code == 0
    assert _payload(result)["command"] == "auth login"
    assert secret not in (result.stdout + result.stderr)


def test_cli_auth_update_overwrites_fake_keyring_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeCredentialStore()
    store.set_password("hancode", "anthropic", "old-secret-1234")
    monkeypatch.setattr(cli, "credential_provider", _fake_cli_provider(store))
    monkeypatch.setattr(cli.typer, "prompt", lambda *args, **kwargs: "new-secret-5678")

    result = runner.invoke(cli.app, ["auth", "update", "--provider", "anthropic"])

    assert result.exit_code == 0
    assert store.get_password("hancode", "anthropic") == "new-secret-5678"
    assert "new-secret-5678" not in result.stdout


def test_cli_auth_clear_removes_fake_keyring_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeCredentialStore()
    store.set_password("hancode", "openai_compatible", "clear-secret-90ab")
    monkeypatch.setattr(cli, "credential_provider", _fake_cli_provider(store))
    monkeypatch.setattr(cli, "_confirm_clear", lambda: True)

    result = runner.invoke(
        cli.app,
        ["auth", "clear", "--provider", "openai_compatible"],
    )

    assert result.exit_code == 0
    assert store.get_password("hancode", "openai_compatible") is None
    assert "clear-secret-90ab" not in result.stdout


def test_cli_auth_clear_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeCredentialStore()
    store.set_password("hancode", "openai_compatible", "confirm-secret-12ab")
    monkeypatch.setattr(cli, "credential_provider", _fake_cli_provider(store))
    monkeypatch.setattr(cli, "_confirm_clear", lambda: False)

    result = runner.invoke(
        cli.app,
        ["auth", "clear", "--provider", "openai_compatible"],
    )

    assert result.exit_code == 1
    assert store.get_password("hancode", "openai_compatible") == "confirm-secret-12ab"
    assert _payload(result)["error"]["error_code"] == "credential_clear_cancelled"  # type: ignore[index]


def test_cli_auth_clear_keeps_json_on_stdout_with_real_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "real-confirm-secret-78cd"
    store = _FakeCredentialStore()
    store.set_password("hancode", "openai_compatible", secret)
    monkeypatch.setattr(cli, "credential_provider", _fake_cli_provider(store))

    result = runner.invoke(
        cli.app,
        ["auth", "clear", "--provider", "openai_compatible"],
        input="y\n",
    )

    assert result.exit_code == 0
    assert _payload(result)["command"] == "auth clear"
    assert secret not in (result.stdout + result.stderr)


def test_cli_auth_clear_does_not_claim_to_clear_external_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CredentialProvider(
        keyring_backend=_FakeCredentialStore(),
        environ={"OPENAI_API_KEY": "external-secret-34cd"},
    )
    monkeypatch.setattr(cli, "credential_provider", provider)

    result = runner.invoke(
        cli.app,
        ["auth", "clear", "--provider", "openai_compatible"],
    )

    assert result.exit_code == 1
    assert _payload(result)["error"]["error_code"] == (  # type: ignore[index]
        "credential_external_source_requires_manual_clear"
    )
    assert "external-secret-34cd" not in result.stdout


def test_cli_auth_unknown_provider_returns_exit_one() -> None:
    result = runner.invoke(
        cli.app,
        ["auth", "status", "--provider", "unknown"],
    )

    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["error"]["error_code"] == "credential_unknown_provider"  # type: ignore[index]


def test_cli_auth_keyring_failure_returns_exit_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableCredentialStore(_FakeCredentialStore):
        def set_password(self, service_name: str, username: str, password: str) -> None:
            raise keyring.errors.NoKeyringError("backend unavailable")

    monkeypatch.setattr(
        cli,
        "credential_provider",
        _fake_cli_provider(UnavailableCredentialStore()),
    )
    monkeypatch.setattr(cli.typer, "prompt", lambda *args, **kwargs: "blocked-secret-ef01")

    result = runner.invoke(
        cli.app,
        ["auth", "login", "--provider", "openai_compatible"],
    )

    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["error"]["error_code"] == "credential_keyring_unavailable"  # type: ignore[index]
    assert "blocked-secret-ef01" not in result.stdout


def test_cli_auth_does_not_accept_secret_option() -> None:
    result = runner.invoke(
        cli.app,
        [
            "auth",
            "login",
            "--provider",
            "openai_compatible",
            "--secret",
            "command-line-secret",
        ],
    )

    assert result.exit_code == 2
    assert "command-line-secret" not in (result.stdout + result.stderr)


def test_cli_init_creates_workspace_with_deterministic_defaults(tmp_path: Path) -> None:
    project_root = tmp_path / "course-project"
    project_root.mkdir()

    result = runner.invoke(cli.app, ["init", str(project_root)])

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["status"] == "completed"
    assert list(payload) == ["command", "status", "workspace"]
    project_data = json.loads(
        (project_root / ".hancode" / "project.json").read_text(encoding="utf-8")
    )
    assert project_data["project_id"] == "course-project"
    assert project_data["course_name"] == "unspecified-course"
    assert project_data["assignment_name"] == "unspecified-assignment"


def test_cli_init_accepts_explicit_project_metadata(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = runner.invoke(
        cli.app,
        [
            "init",
            str(project_root),
            "--project-id",
            "course-001",
            "--course-name",
            "软件工程",
            "--assignment-name",
            "作业一",
        ],
    )

    assert result.exit_code == 0
    project_data = json.loads(
        (project_root / ".hancode" / "project.json").read_text(encoding="utf-8")
    )
    assert project_data["project_id"] == "course-001"
    assert project_data["course_name"] == "软件工程"
    assert project_data["assignment_name"] == "作业一"


def test_cli_demo_runs_with_mock_provider_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HANCODE_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    result = runner.invoke(cli.app, ["demo", "--provider", "mock"])

    assert result.exit_code == 0
    assert _payload(result)["status"] == "completed"


def test_cli_unknown_provider_returns_clear_error() -> None:
    result = runner.invoke(cli.app, ["demo", "--provider", "openai"])

    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["status"] == "failed"
    assert payload["error"]["error_code"] == "cli_unknown_provider"  # type: ignore[index]
    assert "mock" in payload["error"]["suggested_fix"]  # type: ignore[index]


def test_cli_config_error_uses_stable_exit_code(tmp_path: Path) -> None:
    invalid_root = tmp_path / "not-a-directory"
    invalid_root.write_text("not a project directory", encoding="utf-8")

    result = runner.invoke(cli.app, ["init", str(invalid_root)])

    assert result.exit_code == 2
    payload = _payload(result)
    assert payload["status"] == "failed"
    assert payload["error"]["error_code"]  # type: ignore[index]


def test_cli_trace_error_uses_unrecoverable_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_demo() -> object:
        raise HanCodeError(
            StructuredError(
                error_code="trace_write_failed",
                message="trace unavailable",
                phase="code",
                denied_rule="trace_required",
                suggested_fix="repair trace storage",
            )
        )

    monkeypatch.setattr(cli, "run_packaged_mock_demo", fail_demo)

    result = runner.invoke(cli.app, ["demo", "--provider", "mock"])

    assert result.exit_code == 3
    assert _payload(result)["error"]["error_code"] == "trace_write_failed"  # type: ignore[index]


def test_cli_export_copies_declared_artifacts(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    init_project_workspace(project_root, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(project_root, "task-001")
    state = load_state(task_root)
    artifacts = dict(state.artifacts)
    artifacts["SPEC.md"] = True
    (task_root / "SPEC.md").write_text("# SPEC\n", encoding="utf-8")
    save_state(task_root, replace(state, artifacts=artifacts))
    output_dir = tmp_path / "deliverables"

    result = runner.invoke(
        cli.app,
        [
            "export",
            "--project-root",
            str(project_root),
            "--task",
            "task-001",
            "--out",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "export"
    assert payload["status"] == "completed"
    assert (output_dir / "SPEC.md").read_text(encoding="utf-8") == "# SPEC\n"


def test_cli_export_missing_required_options_uses_typer_exit_code() -> None:
    result = runner.invoke(cli.app, ["export", "--task", "task-001"])

    assert result.exit_code == 2
    assert "Missing option" in (result.stdout + result.stderr)
