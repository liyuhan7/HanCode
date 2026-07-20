"""Real provider smoke test — skipped by default.

Enable with:
    HANCODE_RUN_PROVIDER_SMOKE=1 uv run pytest tests/integration/test_real_provider_smoke.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hancode.core.actions import ParseError, parse_action
from hancode.core.config import load_config
from hancode.core.models import Phase
from hancode.providers.factory import create_provider_adapter


pytestmark = pytest.mark.skipif(
    os.getenv("HANCODE_RUN_PROVIDER_SMOKE") != "1",
    reason="Set HANCODE_RUN_PROVIDER_SMOKE=1 to run real provider smoke test.",
)


def test_real_provider_returns_valid_action(tmp_path: Path) -> None:
    from hancode.storage.workspace import init_project_workspace

    init_project_workspace(
        tmp_path,
        project_id="smoke",
        course_name="AI4SE",
        assignment_name="HanCode",
    )
    project_file = tmp_path / ".hancode" / "project.json"
    import json

    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(
        {
            "llm_provider": "openai_compatible",
            "model_name": os.getenv("HANCODE_SMOKE_MODEL", "gpt-4o-mini"),
            "credential_source": "env",
            "provider_base_url": os.getenv(
                "HANCODE_SMOKE_BASE_URL",
                "https://api.openai.com/v1",
            ),
        }
    )
    project_file.write_text(json.dumps(data), encoding="utf-8")

    config = load_config(tmp_path)
    provider = create_provider_adapter(config, credential=os.getenv("OPENAI_API_KEY", ""))

    context = {
        "task_id": "smoke-001",
        "phase": Phase.SPEC.value,
        "goal": "List the files in the project root.",
        "sections": {},
        "context_risks": [],
        "truncation": {
            "applied": False,
            "omitted_sections": [],
            "truncated_sections": [],
        },
    }

    action = provider.next_action(context)

    assert isinstance(action, dict)
    assert "type" in action
    assert "phase" in action

    parsed = parse_action(action, Phase.SPEC)
    assert not isinstance(parsed, ParseError), (
        f"Action rejected by parse_action: {parsed}"
    )

    error_str = str(action)
    assert "sk-" not in error_str
    assert "OPENAI_API_KEY" not in error_str
