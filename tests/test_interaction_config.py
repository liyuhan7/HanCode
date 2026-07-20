from __future__ import annotations

import json
from pathlib import Path

import pytest

from hancode.core.config import load_config
from hancode.core.errors import HanCodeError
from hancode.storage.workspace import init_project_workspace


def _project(tmp_path: Path, updates: dict[str, object]) -> Path:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    project_file = tmp_path / ".hancode" / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(updates)
    project_file.write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_interaction_mode_is_disabled_by_default(tmp_path: Path) -> None:
    config = load_config(_project(tmp_path, {}))

    assert config.interaction_mode == "disabled"
    assert config.max_interactions_per_phase == 8
    assert config.max_interaction_question_chars == 2048
    assert config.max_interaction_answer_chars == 8192


def test_interaction_config_accepts_ask_user(tmp_path: Path) -> None:
    config = load_config(
        _project(
            tmp_path,
            {
                "interaction_mode": "ask_user",
                "max_interactions_per_phase": 3,
                "max_interaction_question_chars": 1000,
                "max_interaction_answer_chars": 4000,
            },
        )
    )

    assert config.interaction_mode == "ask_user"
    assert config.max_interactions_per_phase == 3
    assert config.max_interaction_question_chars == 1000
    assert config.max_interaction_answer_chars == 4000


@pytest.mark.parametrize(
    "updates",
    [
        {"interaction_mode": "always"},
        {"max_interactions_per_phase": 0},
        {"max_interaction_question_chars": 0},
        {"max_interaction_answer_chars": 0},
    ],
)
def test_interaction_config_rejects_invalid_values(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    with pytest.raises(HanCodeError):
        load_config(_project(tmp_path, updates))
