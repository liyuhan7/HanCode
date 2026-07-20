from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hancode.core.interactions import InteractionRecord, InteractionStatus
from hancode.core.models import Phase, TaskStatus
from hancode.core.state import load_state, save_state
from hancode.storage.workspace import init_project_workspace, init_task_workspace


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    init_project_workspace(tmp_path, "project-001", "Course", "Assignment")
    task_root = init_task_workspace(tmp_path, "task-001")
    return tmp_path, task_root


def test_old_state_loads_with_empty_interactions(tmp_path: Path) -> None:
    _, task_root = _workspace(tmp_path)

    state = load_state(task_root)

    assert state.interaction_seq == 0
    assert state.interactions == ()
    assert state.pending_interaction_id is None


def test_state_roundtrips_interactions(tmp_path: Path) -> None:
    _, task_root = _workspace(tmp_path)
    state = load_state(task_root)
    interaction = InteractionRecord(
        interaction_id="ask-000001",
        phase=Phase.SPEC,
        question="Which framework should be used?",
        answer="FastAPI",
        status=InteractionStatus.ANSWERED,
    )
    updated = replace(
        state,
        interaction_seq=1,
        interactions=(interaction,),
        pending_interaction_id="ask-000001",
        status=TaskStatus.WAITING_INPUT,
    )

    save_state(task_root, updated)
    loaded = load_state(task_root)

    assert loaded == updated
    persisted = json.loads((task_root / "state.json").read_text(encoding="utf-8"))
    assert persisted["interactions"][0]["answer"] == "FastAPI"


@pytest.mark.parametrize(
    "updates",
    [
        {"pending_interaction_id": "ask-999999"},
        {
            "interactions": [
                {
                    "interaction_id": "ask-000001",
                    "phase": "spec",
                    "question": "First?",
                    "answer": None,
                    "status": "waiting",
                },
                {
                    "interaction_id": "ask-000002",
                    "phase": "spec",
                    "question": "Second?",
                    "answer": None,
                    "status": "waiting",
                },
            ],
            "interaction_seq": 2,
            "pending_interaction_id": "ask-000001",
            "status": "waiting_input",
        },
        {
            "interactions": [
                {
                    "interaction_id": "ask-000001",
                    "phase": "code",
                    "question": "Wrong phase?",
                    "answer": None,
                    "status": "waiting",
                }
            ],
            "interaction_seq": 1,
            "pending_interaction_id": "ask-000001",
            "status": "waiting_input",
        },
    ],
    ids=["dangling_pending_id", "multiple_waiting", "cross_phase"],
)
def test_state_rejects_invalid_interaction_invariants(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    _, task_root = _workspace(tmp_path)
    state_file = task_root / "state.json"
    data = json.loads(state_file.read_text(encoding="utf-8"))
    data.update(updates)
    state_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(Exception):
        load_state(task_root)


def test_non_waiting_state_cannot_have_waiting_interaction(tmp_path: Path) -> None:
    _, task_root = _workspace(tmp_path)
    state_file = task_root / "state.json"
    data = json.loads(state_file.read_text(encoding="utf-8"))
    data.update(
        {
            "interactions": [
                {
                    "interaction_id": "ask-000001",
                    "phase": "spec",
                    "question": "Question?",
                    "answer": None,
                    "status": "waiting",
                }
            ],
            "interaction_seq": 1,
            "pending_interaction_id": "ask-000001",
        }
    )
    state_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(Exception):
        load_state(task_root)
