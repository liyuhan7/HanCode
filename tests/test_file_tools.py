from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from hancode.actions import Action, ActionType
from hancode.file_tools import list_files, read_file, search_text, write_file
from hancode.models import Phase
from hancode.tools import ToolRegistry, ToolResult


def test_read_file_inside_workspace(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("course notes\n", encoding="utf-8")

    result = read_file(tmp_path, "notes.txt")

    assert result == ToolResult(
        success=True,
        action_name="read_file",
        output={"path": "notes.txt", "content": "course notes\n", "redacted": False},
    )


def test_read_file_rejects_missing_file_with_structured_error(tmp_path: Path) -> None:
    result = read_file(tmp_path, "missing.txt")

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="File does not exist.",
    )


def test_read_file_rejects_directory(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()

    result = read_file(tmp_path, "src")

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Path is not a file.",
    )


def test_read_file_rejects_non_utf8_content(tmp_path: Path) -> None:
    (tmp_path / "binary.dat").write_bytes(b"\xff\xfe")

    result = read_file(tmp_path, "binary.dat")

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="File is not valid UTF-8.",
    )


@pytest.mark.parametrize("path", [".env", ".ENV", "config/.env.local"])
def test_read_file_rejects_credential_files(tmp_path: Path, path: str) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OPENAI_API_KEY=do-not-read\n", encoding="utf-8")

    result = read_file(tmp_path, path)

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Credential files cannot be accessed.",
    )


def test_read_file_rejects_absolute_path(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")

    result = read_file(tmp_path, str(outside.resolve()))

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Path must stay inside the project root.",
    )


def test_read_file_rejects_parent_traversal(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (tmp_path / "outside.txt").write_text("outside\n", encoding="utf-8")

    result = read_file(project_root, "../outside.txt")

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Path must stay inside the project root.",
    )


def test_read_file_rejects_symlink_escape(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = project_root / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"File symlink unsupported in this environment: {exc}")

    result = read_file(project_root, "link.txt")

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="Path must stay inside the project root.",
    )


def test_read_file_redacts_secret_like_content(tmp_path: Path) -> None:
    sensitive_values = ["env-secret", "bearer-secret", "sk-exampletoken", "json-secret"]
    (tmp_path / "config.txt").write_text(
        "HANCODE_API_KEY=env-secret\n"
        "Authorization: Bearer bearer-secret\n"
        "token_value=sk-exampletoken\n"
        '{"api_key": "json-secret"}\n',
        encoding="utf-8",
    )

    result = read_file(tmp_path, "config.txt")

    assert result.success is True
    assert isinstance(result.output, dict)
    assert result.output["redacted"] is True
    content = result.output["content"]
    assert isinstance(content, str)
    assert "[REDACTED]" in content
    assert all(value not in content for value in sensitive_values)


def test_read_file_redacts_quoted_assignment_and_password_json(tmp_path: Path) -> None:
    (tmp_path / "quoted.txt").write_text(
        'API_KEY="quoted-secret"\n{"password": "json-password"}\n',
        encoding="utf-8",
    )

    result = read_file(tmp_path, "quoted.txt")

    assert result.success is True
    assert isinstance(result.output, dict)
    content = result.output["content"]
    assert isinstance(content, str)
    assert "quoted-secret" not in content
    assert "json-password" not in content
    assert content.count("[REDACTED]") == 2


def test_write_file_inside_workspace(tmp_path: Path) -> None:
    result = write_file(tmp_path, "answer.txt", "你好\n")

    assert result == ToolResult(
        success=True,
        action_name="write_file",
        output={"path": "answer.txt", "bytes_written": len("你好\n".encode("utf-8"))},
    )
    assert (tmp_path / "answer.txt").read_text(encoding="utf-8") == "你好\n"
    assert (tmp_path / "answer.txt").read_bytes() == "你好\n".encode("utf-8")


def test_write_file_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "answer.txt"
    target.write_text("old\n", encoding="utf-8")

    result = write_file(tmp_path, "answer.txt", "new\n")

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "new\n"


def test_write_file_rejects_missing_parent_directory(tmp_path: Path) -> None:
    result = write_file(tmp_path, "missing/answer.txt", "content\n")

    assert result == ToolResult(
        success=False,
        action_name="write_file",
        error_summary="Parent directory does not exist.",
    )
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("path", [".env", "nested/.env.production"])
def test_write_file_rejects_credential_files(tmp_path: Path, path: str) -> None:
    (tmp_path / "nested").mkdir(exist_ok=True)

    result = write_file(tmp_path, path, "TOKEN=do-not-write\n")

    assert result == ToolResult(
        success=False,
        action_name="write_file",
        error_summary="Credential files cannot be accessed.",
    )


def test_write_file_rejects_path_outside_workspace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = write_file(project_root, "../outside.txt", "outside\n")

    assert result == ToolResult(
        success=False,
        action_name="write_file",
        error_summary="Path must stay inside the project root.",
    )
    assert not (tmp_path / "outside.txt").exists()


def test_write_file_rejects_content_that_cannot_be_encoded_as_utf8(tmp_path: Path) -> None:
    result = write_file(tmp_path, "invalid.txt", "\ud800")

    assert result == ToolResult(
        success=False,
        action_name="write_file",
        error_summary="Content is not valid UTF-8.",
    )
    assert not (tmp_path / "invalid.txt").exists()


def test_list_files_inside_workspace_is_recursive_and_sorted(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "z.txt").write_text("z\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("b\n", encoding="utf-8")
    (tmp_path / "src" / "a.py").write_text("a\n", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=hidden\n", encoding="utf-8")

    result = list_files(tmp_path)

    assert result == ToolResult(
        success=True,
        action_name="list_files",
        output={"path": ".", "files": ["src/a.py", "src/b.py", "z.txt"]},
    )


def test_list_files_supports_workspace_subdirectory(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("main\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme\n", encoding="utf-8")

    result = list_files(tmp_path, "src")

    assert result == ToolResult(
        success=True,
        action_name="list_files",
        output={"path": "src", "files": ["src/main.py"]},
    )


def test_list_files_rejects_missing_directory(tmp_path: Path) -> None:
    result = list_files(tmp_path, "missing")

    assert result == ToolResult(
        success=False,
        action_name="list_files",
        error_summary="Directory does not exist.",
    )


def test_search_text_inside_workspace_is_sorted_by_path_and_line(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "z.txt").write_text("needle z\n", encoding="utf-8")
    (tmp_path / "src" / "a.py").write_text(
        "needle first\nnot a match\nneedle third\n", encoding="utf-8"
    )

    result = search_text(tmp_path, "needle")

    assert result == ToolResult(
        success=True,
        action_name="search_text",
        output={
            "query": "needle",
            "matches": [
                {"path": "src/a.py", "line": 1, "text": "needle first"},
                {"path": "src/a.py", "line": 3, "text": "needle third"},
                {"path": "z.txt", "line": 1, "text": "needle z"},
            ],
            "skipped_files": [],
        },
    )


def test_search_text_skips_non_utf8_and_credential_files(tmp_path: Path) -> None:
    (tmp_path / "good.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / "binary.dat").write_bytes(b"\xff\xfe")
    (tmp_path / ".env.local").write_text("needle=secret\n", encoding="utf-8")

    result = search_text(tmp_path, "needle")

    assert result == ToolResult(
        success=True,
        action_name="search_text",
        output={
            "query": "needle",
            "matches": [{"path": "good.txt", "line": 1, "text": "needle"}],
            "skipped_files": [".env.local", "binary.dat"],
        },
    )


def test_search_text_does_not_follow_alias_to_credential_file(tmp_path: Path) -> None:
    credential = tmp_path / ".env"
    credential.write_text("SECRET=needle-value\n", encoding="utf-8")
    alias = tmp_path / "safe.txt"
    try:
        alias.symlink_to(credential)
    except OSError as exc:
        pytest.skip(f"File symlink unsupported in this environment: {exc}")

    result = search_text(tmp_path, "needle-value")

    assert result == ToolResult(
        success=True,
        action_name="search_text",
        output={"query": "needle-value", "matches": [], "skipped_files": ["safe.txt"]},
    )


def test_search_text_redacts_matching_secret_values(tmp_path: Path) -> None:
    (tmp_path / "config.txt").write_text(
        "Authorization: Bearer bearer-secret\n", encoding="utf-8"
    )

    result = search_text(tmp_path, "Authorization")

    assert result.success is True
    assert isinstance(result.output, dict)
    assert result.output["matches"] == [
        {"path": "config.txt", "line": 1, "text": "Authorization: Bearer [REDACTED]"}
    ]


def test_search_text_redacts_secret_like_query_in_output(tmp_path: Path) -> None:
    query = "sk-querysecret"
    (tmp_path / "config.txt").write_text(f"token={query}\n", encoding="utf-8")

    result = search_text(tmp_path, query)

    assert result.success is True
    assert isinstance(result.output, dict)
    assert result.output["query"] == "[REDACTED]"
    assert query not in str(result.output)


@pytest.mark.parametrize("query", ["", "   "])
def test_search_text_rejects_empty_query(tmp_path: Path, query: str) -> None:
    result = search_text(tmp_path, query)

    assert result == ToolResult(
        success=False,
        action_name="search_text",
        error_summary="Search query must be non-empty.",
    )


def test_read_file_converts_resolve_error_to_failed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_resolve(path: Path) -> Path:
        raise OSError("do-not-expose")

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    result = read_file(tmp_path, "notes.txt")

    assert result == ToolResult(
        success=False,
        action_name="read_file",
        error_summary="File operation failed: OSError.",
    )


def test_file_tool_can_be_registered_with_bound_project_root(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("notes\n", encoding="utf-8")
    registry = ToolRegistry()
    registry.register("read_file", partial(read_file, tmp_path))
    action = Action(
        type=ActionType.TOOL_CALL,
        phase=Phase.CODE,
        tool_name="read_file",
        args={"path": "notes.txt"},
        reason=None,
    )

    result = registry.dispatch(action)

    assert result.success is True
    assert result.action_name == "read_file"
