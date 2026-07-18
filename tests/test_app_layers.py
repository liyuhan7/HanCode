from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from hancode.app.auth_service import AuthService
from hancode.app.delivery_service import DeliveryService
from hancode.app.project_service import ProjectService
from hancode.app.task_service import TaskService
from hancode.app.credentials import CredentialStatus
from hancode.interfaces import cli


def test_app_service_modules_are_importable() -> None:
    from hancode.app import auth_service, delivery_service, project_service, task_service

    assert auth_service.AuthService
    assert delivery_service.DeliveryService
    assert project_service.ProjectService
    assert task_service.TaskService


def test_project_service_delegates_workspace_initialization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hancode.app import project_service

    expected = tmp_path / ".hancode"

    def fake_initialize(
        project_root: Path, project_id: str, course_name: str, assignment_name: str
    ) -> Path:
        assert (project_root, project_id, course_name, assignment_name) == (
            tmp_path,
            "project-001",
            "Course",
            "Assignment",
        )
        return expected

    monkeypatch.setattr(project_service, "init_project_workspace", fake_initialize)

    result = ProjectService().initialize(tmp_path, "project-001", "Course", "Assignment")

    assert result is expected


def test_task_service_delegates_engine_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hancode.app import task_service

    expected = object()
    provider = object()

    def fake_run_task(
        project_root: Path,
        task_id: str,
        *,
        resume: bool,
        provider: object,
    ) -> object:
        assert (project_root, task_id, resume, provider) == (
            tmp_path,
            "task-001",
            True,
            provider,
        )
        return expected

    monkeypatch.setattr(task_service, "run_task", fake_run_task)

    result = TaskService().run(tmp_path, "task-001", resume=True, provider=provider)

    assert result is expected


def test_auth_service_uses_injected_credential_provider() -> None:
    status = CredentialStatus(
        configured=True,
        provider="mock",
        source="missing",
    )
    calls: list[tuple[str, str]] = []

    class FakeCredentialProvider:
        def status(self, provider: str) -> CredentialStatus:
            calls.append(("status", provider))
            return status

        def set_secret(self, provider: str, secret: str) -> None:
            calls.append(("set", f"{provider}:{secret}"))

        def clear_secret(self, provider: str) -> None:
            calls.append(("clear", provider))

    service = AuthService(cast(object, FakeCredentialProvider()))

    assert service.status("mock") is status
    service.set_secret("mock", "fake-secret")
    service.clear_secret("mock")
    assert calls == [
        ("status", "mock"),
        ("set", "mock:fake-secret"),
        ("clear", "mock"),
    ]


def test_delivery_service_delegates_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from hancode.app import delivery_service

    expected = object()

    def fake_export(project_root: Path, task_id: str, output_dir: Path) -> object:
        assert (project_root, task_id, output_dir) == (tmp_path, "task-001", tmp_path / "out")
        return expected

    monkeypatch.setattr(delivery_service, "export_task_artifacts", fake_export)

    result = DeliveryService().export(tmp_path, "task-001", tmp_path / "out")

    assert result is expected


def test_cli_uses_application_services_without_changing_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    expected_workspace = tmp_path / ".hancode"

    class FakeProjectService:
        def initialize(
            self,
            project_root: Path,
            project_id: str,
            course_name: str,
            assignment_name: str,
        ) -> Path:
            return expected_workspace

    monkeypatch.setattr(cli, "project_service", FakeProjectService())

    result = CliRunner().invoke(cli.app, ["init", str(tmp_path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "command": "init",
        "status": "completed",
        "workspace": str(expected_workspace),
    }


def test_delivery_support_modules_are_importable() -> None:
    from hancode.delivery_support import deliverables, knowledge, reports, review, result

    assert result.DeliveryResult
    assert result.ResultBuilder
    assert reports.write_test_report
    assert review.write_review
    assert knowledge.write_knowledge
    assert deliverables.write_deliverables


def test_delivery_support_exports_responsibility_modules() -> None:
    from hancode.delivery_support.deliverables import write_deliverables
    from hancode.delivery_support.knowledge import write_knowledge
    from hancode.delivery_support.reports import write_test_report
    from hancode.delivery_support.result import DeliveryResult
    from hancode.delivery_support.review import write_review

    assert DeliveryResult
    assert write_deliverables
    assert write_knowledge
    assert write_review
    assert write_test_report


def test_demo_support_modules_are_importable() -> None:
    from hancode.demo_support import actions, fixture, runner

    assert runner.run_mock_demo
    assert runner.run_packaged_mock_demo
    assert actions.build_first_actions
    assert actions.build_retry_actions
    assert fixture.validate_fixture
    assert fixture.copy_packaged_fixture


def test_demo_action_sequences_remain_deterministic() -> None:
    from hancode.demo_support.actions import (
        build_first_actions,
        build_finish_actions,
        build_recovery_actions,
        build_retry_actions,
    )

    assert build_first_actions() == build_first_actions()
    assert build_retry_actions() == build_retry_actions()
    assert build_recovery_actions() == build_recovery_actions()
    assert build_finish_actions() == build_finish_actions()
