from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.app.config_service import ConfigService
from hancode.core.errors import HanCodeError
from hancode.core.project_config import (
    PROJECT_CONFIG_KEYS,
    PROJECT_METADATA_KEYS,
    build_project_config,
)
from hancode.storage.workspace import init_project_workspace


def _initialize(project_root: Path) -> Path:
    return init_project_workspace(
        project_root,
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )


def test_init_writes_complete_ordered_project_configuration(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)
    content = (workspace / "project.json").read_text(encoding="utf-8")
    data = json.loads(content)

    assert data == build_project_config(
        project_id="course-project",
        course_name="AI4SE",
        assignment_name="Harness",
    )
    assert tuple(data)[5:] == PROJECT_CONFIG_KEYS
    assert content.endswith("\n")
    assert '\n  "llm_provider": "mock"' in content


def test_config_service_expands_legacy_minimal_config_only_on_save(
    tmp_path: Path,
) -> None:
    workspace = _initialize(tmp_path)
    path = workspace / "project.json"
    minimal = {
        "workspace_version": 1,
        "project_id": "course-project",
        "course_name": "AI4SE",
        "assignment_name": "Harness",
        "project_root": ".",
    }
    path.write_text(json.dumps(minimal), encoding="utf-8")
    service = ConfigService()

    view = service.load(tmp_path)

    assert len(view.to_dict()) == len(PROJECT_METADATA_KEYS) + len(PROJECT_CONFIG_KEYS)
    assert json.loads(path.read_text(encoding="utf-8")) == minimal

    result = service.save(tmp_path, view.to_dict())

    assert result.changed_fields == ()
    assert tuple(json.loads(path.read_text(encoding="utf-8"))) == tuple(view.to_dict())


def test_config_service_migrates_legacy_provider_mode_on_save(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)
    path = workspace / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("provider_action_mode")
    data["provider_response_mode"] = "json_schema"
    path.write_text(json.dumps(data), encoding="utf-8")
    service = ConfigService()

    view = service.load(tmp_path)
    service.save(tmp_path, view.to_dict())
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["provider_action_mode"] == "json_schema"
    assert "provider_response_mode" not in saved


def test_invalid_candidate_does_not_change_project_file(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)
    path = workspace / "project.json"
    before = path.read_bytes()
    values = ConfigService().load(tmp_path).to_dict()
    values["writable_roots"] = ["../outside"]

    with pytest.raises(HanCodeError):
        ConfigService().save(tmp_path, values)

    assert path.read_bytes() == before


def test_plaintext_secret_field_is_rejected_without_writing(tmp_path: Path) -> None:
    workspace = _initialize(tmp_path)
    path = workspace / "project.json"
    before = path.read_bytes()
    values = ConfigService().load(tmp_path).to_dict()
    values["api_key"] = "must-not-be-stored"

    with pytest.raises(HanCodeError) as exc_info:
        ConfigService().save(tmp_path, values)

    assert exc_info.value.structured_error.error_code == "plaintext_secret_not_allowed"
    assert path.read_bytes() == before


def test_atomic_replace_failure_preserves_original_and_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _initialize(tmp_path)
    path = workspace / "project.json"
    before = path.read_bytes()
    values = ConfigService().load(tmp_path).to_dict()
    values["course_name"] = "changed"

    def fail_replace(_source: object, _target: object) -> None:
        raise PermissionError("blocked")

    monkeypatch.setattr("hancode.app.config_service.os.replace", fail_replace)

    with pytest.raises(HanCodeError) as exc_info:
        ConfigService().save(tmp_path, values)

    assert exc_info.value.structured_error.error_code == "project_config_write_failed"
    assert path.read_bytes() == before
    assert list(workspace.glob(".project.json.*.tmp")) == []
