"""Packaged Demo fixture validation and setup."""

from __future__ import annotations

from hashlib import sha256
from importlib import resources
import json
from pathlib import Path

from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.models import Phase


DEMO_TEST_COMMAND = "python -m unittest discover -s tests -q"
DEMO_FIXTURE_DIGESTS = {
    "assignment.md": "09f143742cbba87a8c1f44d935e472854d71cef829eb8efaf84d02bf62cb5312",
    "src/calculator.py": "8a35e58ba3afe3085a142727a379eeb4f77e0e4b889fb0e1213b12bcda55587c",
    "tests/test_calculator.py": "905d45b05d9363b1f326b53aea0ff88c70c05db7e4db06b86fb58135c1d829ce",
}
PACKAGED_FIXTURE_ROOT = resources.files("hancode").joinpath("_demo_fixture")


def validate_fixture(project_root: Path) -> Path:
    if not isinstance(project_root, Path) or is_link(project_root) or not project_root.is_dir():
        raise fixture_error(
            "mock_demo_fixture_required",
            "Mock demo requires a clean copy of examples/broken_project.",
        )
    root = project_root.resolve()
    entries = tuple(root.rglob("*"))
    files = {
        entry.relative_to(root).as_posix()
        for entry in entries
        if entry.is_file()
        and not is_link(entry)
        and "__pycache__" not in entry.relative_to(root).parts
    }
    if (
        (root / ".hancode").exists()
        or any(is_link(entry) for entry in entries)
        or files != set(DEMO_FIXTURE_DIGESTS)
        or any(
            fixture_digest(root / relative_path) != digest
            for relative_path, digest in DEMO_FIXTURE_DIGESTS.items()
        )
    ):
        raise fixture_error(
            "mock_demo_fixture_required",
            "Mock demo requires a clean copy of examples/broken_project.",
        )
    return root


def fixture_digest(path: Path) -> str:
    """Hash fixture text canonically so Git newline conversion is not semantic drift."""
    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    return sha256(normalized).hexdigest()


def configure_demo(project_root: Path) -> None:
    project_file = project_root / ".hancode" / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))
    data.update(
        {
            "llm_provider": "mock",
            "test_command": DEMO_TEST_COMMAND,
            "retry_budget": 1,
            "max_trace_events": 128,
            "protected_patterns": ["assignment.md"],
            "writable_roots": ["src"],
        }
    )
    project_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def copy_packaged_fixture(destination: Path) -> None:
    for relative_path in DEMO_FIXTURE_DIGESTS:
        source = PACKAGED_FIXTURE_ROOT.joinpath(*relative_path.split("/"))
        if not source.is_file():
            raise fixture_error(
                "mock_demo_fixture_unavailable",
                "Packaged mock demo fixture is incomplete.",
            )
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(source.read_bytes())
        except OSError:
            raise fixture_error(
                "mock_demo_fixture_unavailable",
                "Packaged mock demo fixture could not be copied.",
            ) from None


def fixture_error(error_code: str, message: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase=Phase.SPEC.value,
            denied_rule="mock_demo_fixture_required",
            suggested_fix="Copy examples/broken_project into an empty temporary directory.",
        )
    )


def is_link(path: Path) -> bool:
    try:
        junction_probe = getattr(path, "is_junction", None)
        return path.is_symlink() or (bool(junction_probe()) if callable(junction_probe) else False)
    except (AttributeError, OSError, RuntimeError):
        return True
