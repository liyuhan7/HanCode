from __future__ import annotations

from pathlib import Path
import tomllib


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _project_metadata() -> dict[str, object]:
    data = _pyproject_data()
    project = data["project"]
    assert isinstance(project, dict)
    return project


def _pyproject_data() -> dict[str, object]:
    return tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_python_package_metadata_has_console_script() -> None:
    project = _project_metadata()

    assert project["requires-python"] == ">=3.11"
    scripts = project["scripts"]
    assert isinstance(scripts, dict)
    assert scripts["hancode"] == "hancode.cli:app"


def test_quality_tools_target_python311() -> None:
    tools = _pyproject_data()["tool"]
    assert isinstance(tools, dict)
    ruff = tools["ruff"]
    mypy = tools["mypy"]
    assert isinstance(ruff, dict)
    assert isinstance(mypy, dict)

    assert ruff["target-version"] == "py311"
    assert mypy["python_version"] == "3.11"


def test_uv_lock_exists() -> None:
    assert (REPOSITORY_ROOT / "uv.lock").is_file()


def test_make_check_contains_lint_typecheck_test() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "check: lint typecheck test" in makefile


def test_make_commands_use_uv_contract() -> None:
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "uv run pytest" in makefile
    assert "uv run ruff check src tests scripts" in makefile
    assert "uv run mypy src" in makefile
