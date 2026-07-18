from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GITHUB_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
GITLAB_WORKFLOW = REPOSITORY_ROOT / ".gitlab-ci.yml"
QUALITY_COMMANDS = (
    "uv sync --locked --extra dev",
    "uv run pytest",
    "uv run ruff check src tests scripts",
    "uv run mypy src",
)
DELIVERY_COMMANDS = (
    "uv build",
    "uv run hancode --help",
    "uv run hancode demo --provider mock",
)


def _read_workflow(path: Path) -> str:
    assert path.is_file(), f"Missing CI workflow: {path.name}"
    return path.read_text(encoding="utf-8")


def test_github_ci_uses_uv_for_pytest_ruff_mypy() -> None:
    workflow = _read_workflow(GITHUB_WORKFLOW)

    assert "unit-test:" in workflow
    assert 'python-version: "3.11"' in workflow
    for command in QUALITY_COMMANDS:
        assert command in workflow


def test_gitlab_ci_contains_unit_test_job() -> None:
    workflow = _read_workflow(GITLAB_WORKFLOW)

    assert "unit-test:" in workflow
    assert "image: python:3.11-slim" in workflow
    for command in QUALITY_COMMANDS:
        assert command in workflow


def test_ci_builds_package_and_runs_mock_demo() -> None:
    workflows = (
        _read_workflow(GITHUB_WORKFLOW),
        _read_workflow(GITLAB_WORKFLOW),
    )

    for workflow in workflows:
        for command in DELIVERY_COMMANDS:
            assert command in workflow


def test_ci_installs_built_wheel_before_distribution_smoke() -> None:
    github_workflow = _read_workflow(GITHUB_WORKFLOW)
    gitlab_workflow = _read_workflow(GITLAB_WORKFLOW)

    assert 'wheel_venv="$RUNNER_TEMP/hancode-wheel-venv"' in github_workflow
    assert 'uv venv "$wheel_venv" --python 3.11' in github_workflow
    assert 'uv pip install --python "$wheel_venv/bin/python" dist/*.whl' in github_workflow
    assert '"$wheel_venv/bin/hancode" --help' in github_workflow
    assert '"$wheel_venv/bin/hancode" demo --provider mock' in github_workflow

    assert 'wheel_venv="$CI_BUILDS_DIR/hancode-wheel-venv"' in gitlab_workflow
    assert 'uv venv "$wheel_venv" --python 3.11' in gitlab_workflow
    assert 'uv pip install --python "$wheel_venv/bin/python" dist/*.whl' in gitlab_workflow
    assert '"$wheel_venv/bin/hancode" --help' in gitlab_workflow
    assert '"$wheel_venv/bin/hancode" demo --provider mock' in gitlab_workflow


def test_ci_installs_dependencies_builds_and_smokes_wheel_in_order() -> None:
    for workflow in (_read_workflow(GITHUB_WORKFLOW), _read_workflow(GITLAB_WORKFLOW)):
        assert workflow.index("uv sync --locked --extra dev") < workflow.index("uv run pytest")
        assert workflow.index("uv build") < workflow.index("uv pip install")


def test_ci_does_not_require_real_secret() -> None:
    workflows = (
        _read_workflow(GITHUB_WORKFLOW),
        _read_workflow(GITLAB_WORKFLOW),
    )
    combined = "\n".join(workflows)

    for forbidden in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "HANCODE_API_KEY",
        "secrets.",
        "secrets[",
    ):
        assert forbidden not in combined
