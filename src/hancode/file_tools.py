from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from hancode.tools import ToolResult


_ASSIGNMENT_SECRET = re.compile(
    r"(?im)\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET|PASSWORD))"
    r"(\s*=\s*)([^\s\"']+)"
)
_QUOTED_ASSIGNMENT_SECRET = re.compile(
    r"(?im)\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET|PASSWORD))"
    r"(\s*=\s*)([\"'])[^\"']*\3"
)
_BEARER_SECRET = re.compile(r"(?im)(Authorization\s*:\s*Bearer\s+)[^\s]+")
_JSON_SECRET = re.compile(
    r'(?i)(\"(?:api_key|token|secret|password)\"\s*:\s*\")[^\"]*(\")'
)
_SK_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]+\b")


@dataclass(frozen=True, slots=True)
class _ResolvedPath:
    root: Path
    target: Path
    relative: str


def read_file(project_root: Path, path: str) -> ToolResult:
    resolved = _resolve_path(project_root, path)
    if isinstance(resolved, str):
        return _failed("read_file", resolved)
    if not resolved.target.exists():
        return _failed("read_file", "File does not exist.")
    if not resolved.target.is_file():
        return _failed("read_file", "Path is not a file.")

    try:
        content = resolved.target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _failed("read_file", "File is not valid UTF-8.")
    except OSError as exc:
        return _failed("read_file", f"File operation failed: {type(exc).__name__}.")

    redacted_content = redact_text(content)
    return ToolResult(
        success=True,
        action_name="read_file",
        output={
            "path": resolved.relative,
            "content": redacted_content,
            "redacted": redacted_content != content,
        },
    )


def write_file(project_root: Path, path: str, content: str) -> ToolResult:
    resolved = _resolve_path(project_root, path)
    if isinstance(resolved, str):
        return _failed("write_file", resolved)
    if not resolved.target.parent.exists():
        return _failed("write_file", "Parent directory does not exist.")
    if not resolved.target.parent.is_dir():
        return _failed("write_file", "Parent path is not a directory.")
    if resolved.target.exists() and not resolved.target.is_file():
        return _failed("write_file", "Path is not a file.")

    try:
        encoded_content = content.encode("utf-8")
    except UnicodeEncodeError:
        return _failed("write_file", "Content is not valid UTF-8.")

    try:
        resolved.target.write_bytes(encoded_content)
    except OSError as exc:
        return _failed("write_file", f"File operation failed: {type(exc).__name__}.")

    return ToolResult(
        success=True,
        action_name="write_file",
        output={
            "path": resolved.relative,
            "bytes_written": len(encoded_content),
        },
    )


def list_files(project_root: Path, path: str = ".") -> ToolResult:
    resolved = _resolve_path(project_root, path)
    if isinstance(resolved, str):
        return _failed("list_files", resolved)
    if not resolved.target.exists():
        return _failed("list_files", "Directory does not exist.")
    if not resolved.target.is_dir():
        return _failed("list_files", "Path is not a directory.")

    files: list[str] = []
    try:
        candidates = resolved.target.rglob("*")
        for candidate in candidates:
            safe_relative = _safe_relative_file(resolved.root, candidate)
            if safe_relative is not None and not _is_credential_path(safe_relative):
                files.append(safe_relative)
    except OSError as exc:
        return _failed("list_files", f"File operation failed: {type(exc).__name__}.")

    return ToolResult(
        success=True,
        action_name="list_files",
        output={"path": resolved.relative, "files": sorted(files)},
    )


def search_text(project_root: Path, query: str) -> ToolResult:
    if not query.strip():
        return _failed("search_text", "Search query must be non-empty.")
    try:
        root = project_root.resolve()
    except (OSError, RuntimeError) as exc:
        return _failed("search_text", f"File operation failed: {type(exc).__name__}.")
    if not root.exists() or not root.is_dir():
        return _failed("search_text", "Project root is not a directory.")

    matches: list[dict[str, object]] = []
    skipped_files: list[str] = []
    credential_files: dict[str, str] = {}
    credential_aliases: set[str] = set()
    try:
        candidates = root.rglob("*")
        for candidate in candidates:
            relative = _lexical_relative(root, candidate)
            if relative is None or not candidate.is_file():
                continue
            safe_relative = _safe_relative_file(root, candidate)
            if _is_credential_path(relative):
                if safe_relative is not None:
                    credential_files.setdefault(safe_relative, relative)
                continue
            if (
                safe_relative is None
                or _is_credential_path(safe_relative)
            ):
                skipped_files.append(relative)
                if safe_relative is not None and _is_credential_path(safe_relative):
                    credential_aliases.add(safe_relative)
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                skipped_files.append(safe_relative)
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                if query in line:
                    matches.append(
                        {
                            "path": safe_relative,
                            "line": line_number,
                            "text": redact_text(line),
                        }
                    )
    except OSError as exc:
        return _failed("search_text", f"File operation failed: {type(exc).__name__}.")

    skipped_files.extend(
        relative
        for canonical, relative in credential_files.items()
        if canonical not in credential_aliases
    )
    matches.sort(key=lambda match: (str(match["path"]), cast(int, match["line"])))
    return ToolResult(
        success=True,
        action_name="search_text",
        output={
            "query": redact_text(query),
            "matches": matches,
            "skipped_files": sorted(set(skipped_files)),
        },
    )


def _resolve_path(project_root: Path, path: str) -> _ResolvedPath | str:
    requested = Path(path)
    if requested.is_absolute():
        return "Path must stay inside the project root."

    try:
        root = project_root.resolve()
        target = (root / requested).resolve()
    except (OSError, RuntimeError) as exc:
        return f"File operation failed: {type(exc).__name__}."
    if not target.is_relative_to(root):
        return "Path must stay inside the project root."
    relative = target.relative_to(root).as_posix() or "."
    if _is_credential_path(relative):
        return "Credential files cannot be accessed."
    return _ResolvedPath(root=root, target=target, relative=relative)


def _safe_relative_file(root: Path, candidate: Path) -> str | None:
    if not candidate.is_file():
        return None
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        return None
    return resolved.relative_to(root).as_posix()


def _lexical_relative(root: Path, candidate: Path) -> str | None:
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return None


def _is_credential_path(path: str) -> bool:
    return any(
        part.casefold() == ".env" or part.casefold().startswith(".env.")
        for part in Path(path).parts
    )


def redact_text(text: str) -> str:
    redacted = _QUOTED_ASSIGNMENT_SECRET.sub(r"\1\2\3[REDACTED]\3", text)
    redacted = _ASSIGNMENT_SECRET.sub(r"\1\2[REDACTED]", redacted)
    redacted = _BEARER_SECRET.sub(r"\1[REDACTED]", redacted)
    redacted = _JSON_SECRET.sub(r"\1[REDACTED]\2", redacted)
    return _SK_SECRET.sub("[REDACTED]", redacted)


def _failed(action_name: str, error_summary: str) -> ToolResult:
    return ToolResult(
        success=False,
        action_name=action_name,
        error_summary=error_summary,
    )
