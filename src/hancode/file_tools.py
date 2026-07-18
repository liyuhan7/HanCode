from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkstemp
from typing import cast

from hancode.path_security import is_sensitive_path
from hancode.tools import ToolResult


_ASSIGNMENT_SECRET = re.compile(
    r"(?im)\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET|PASSWORD))"
    r"(\s*=\s*)([^\s\"']+)"
)
_QUOTED_ASSIGNMENT_SECRET = re.compile(
    r"(?im)\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET|PASSWORD))"
    r"(\s*=\s*)([\"'])[^\"']*\3"
)
_BEARER_SECRET = re.compile(r"(?im)((?:Authorization\s*:\s*)?Bearer\s+)[^\s]+")
_JSON_SECRET = re.compile(
    r'(?i)(\"(?:api_key|token|secret|password|authorization|cookie|credential|'
    r'private[_-]?key|aws[_-]?access[_-]?key[_-]?id|aws[_-]?secret[_-]?access[_-]?key)'
    r'\"\s*:\s*)(\"(?:\\.|[^\"\\])*\"|\'(?:\\.|[^\'\\])*\')'
)
_QUOTED_GENERIC_SECRET = re.compile(
    r"(?im)\b(authorization|api[_-]?key|token|secret|password|private[_-]?key|"
    r"credential|cookie|aws[_-]?access[_-]?key[_-]?id|aws[_-]?secret[_-]?access[_-]?key)"
    r"(\s*[:=]\s*)(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
)
_GENERIC_SECRET = re.compile(
    r"(?im)\b(authorization|api[_-]?key|token|secret|password|private[_-]?key|"
    r"credential|cookie|aws[_-]?access[_-]?key[_-]?id|aws[_-]?secret[_-]?access[_-]?key)"
    r"(\s*[:=]\s*)(?!bearer\b)[^\s,;\"']+"
)
_SK_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]+\b")
_PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?P<label>(?:[A-Z0-9]+ )*PRIVATE KEY)-----\r?\n"
    r".*?"
    r"-----END (?P=label)-----",
    re.IGNORECASE | re.DOTALL,
)


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
        return _write_failed(resolved)
    if not resolved.target.parent.exists():
        return _write_failed("Parent directory does not exist.")
    if not resolved.target.parent.is_dir():
        return _write_failed("Parent path is not a directory.")
    if resolved.target.exists() and not resolved.target.is_file():
        return _write_failed("Path is not a file.")

    try:
        encoded_content = content.encode("utf-8")
    except UnicodeEncodeError:
        return _write_failed("Content is not valid UTF-8.")

    temporary_path: Path | None = None
    replacement_attempted = False
    try:
        file_descriptor, temporary_name = mkstemp(
            prefix=f".{resolved.target.name}.", suffix=".tmp", dir=resolved.target.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(encoded_content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        replacement_attempted = True
        os.replace(temporary_path, resolved.target)
        temporary_path = None
    except OSError as exc:
        return _write_failed(
            f"File operation failed: {type(exc).__name__}.",
            mutation_applied=None if replacement_attempted else False,
        )
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass

    return ToolResult(
        success=True,
        action_name="write_file",
        output={
            "path": resolved.relative,
            "bytes_written": len(encoded_content),
        },
        mutation_applied=True,
    )


def edit_file(project_root: Path, path: str, old_string: str, new_string: str) -> ToolResult:
    if not isinstance(old_string, str) or not old_string:
        return _edit_failed("Edit old_string must be non-empty.")
    if not isinstance(new_string, str):
        return _edit_failed("Edit new_string must be text.")
    if old_string == new_string:
        return _edit_failed("Edit would not change the file.")
    resolved = _resolve_path(project_root, path)
    if isinstance(resolved, str):
        return _edit_failed(resolved)
    if not resolved.target.exists():
        return _edit_failed("File does not exist.")
    if not resolved.target.is_file():
        return _edit_failed("Path is not a file.")

    try:
        content = resolved.target.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return _edit_failed("File is not valid UTF-8.")
    except OSError as exc:
        return _edit_failed(f"File operation failed: {type(exc).__name__}.")
    if content.count(old_string) != 1:
        return _edit_failed("Edit target must contain old_string exactly once.")

    updated_content = content.replace(old_string, new_string, 1)
    try:
        encoded_content = updated_content.encode("utf-8")
    except UnicodeEncodeError:
        return _edit_failed("Edit content is not valid UTF-8.")

    temporary_path: Path | None = None
    replacement_attempted = False
    try:
        file_descriptor, temporary_name = mkstemp(
            prefix=f".{resolved.target.name}.", suffix=".tmp", dir=resolved.target.parent
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(encoded_content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        replacement_attempted = True
        os.replace(temporary_path, resolved.target)
        temporary_path = None
    except OSError as exc:
        return _edit_failed(
            f"File operation failed: {type(exc).__name__}.",
            mutation_applied=None if replacement_attempted else False,
        )
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass

    return ToolResult(
        success=True,
        action_name="edit_file",
        output={
            "path": resolved.relative,
            "replacements": 1,
            "bytes_written": len(encoded_content),
        },
        mutation_applied=True,
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
            if safe_relative is not None and not is_sensitive_path(safe_relative):
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
            if is_sensitive_path(relative):
                if safe_relative is not None:
                    credential_files.setdefault(safe_relative, relative)
                continue
            if (
                safe_relative is None
                or is_sensitive_path(safe_relative)
            ):
                skipped_files.append(relative)
                if safe_relative is not None and is_sensitive_path(safe_relative):
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
    except (OSError, RuntimeError) as exc:
        return f"File operation failed: {type(exc).__name__}."
    if is_sensitive_path(requested.as_posix()):
        return "Credential files cannot be accessed."
    try:
        target = (root / requested).resolve()
    except (OSError, RuntimeError) as exc:
        return f"File operation failed: {type(exc).__name__}."
    if not target.is_relative_to(root):
        return "Path must stay inside the project root."
    relative = target.relative_to(root).as_posix() or "."
    if is_sensitive_path(relative):
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


def redact_text(text: str) -> str:
    redacted = _PEM_PRIVATE_KEY.sub("[REDACTED]", text)
    redacted = _QUOTED_ASSIGNMENT_SECRET.sub(r"\1\2\3[REDACTED]\3", redacted)
    redacted = _ASSIGNMENT_SECRET.sub(r"\1\2[REDACTED]", redacted)
    redacted = _BEARER_SECRET.sub(r"\1[REDACTED]", redacted)
    redacted = _QUOTED_GENERIC_SECRET.sub(_redact_quoted_generic, redacted)
    redacted = _JSON_SECRET.sub(_redact_quoted_json, redacted)
    redacted = _GENERIC_SECRET.sub(r"\1\2[REDACTED]", redacted)
    return _SK_SECRET.sub("[REDACTED]", redacted)


def _redact_quoted_generic(match: re.Match[str]) -> str:
    quoted_value = match.group(3)
    return f"{match.group(1)}{match.group(2)}{quoted_value[0]}[REDACTED]{quoted_value[0]}"


def _redact_quoted_json(match: re.Match[str]) -> str:
    quoted_value = match.group(2)
    return f"{match.group(1)}{quoted_value[0]}[REDACTED]{quoted_value[0]}"


def _failed(action_name: str, error_summary: str) -> ToolResult:
    return ToolResult(
        success=False,
        action_name=action_name,
        error_summary=error_summary,
    )


def _edit_failed(
    error_summary: str, *, mutation_applied: bool | None = False
) -> ToolResult:
    return ToolResult(
        success=False,
        action_name="edit_file",
        error_summary=error_summary,
        mutation_applied=mutation_applied,
    )


def _write_failed(
    error_summary: str, *, mutation_applied: bool | None = False
) -> ToolResult:
    return ToolResult(
        success=False,
        action_name="write_file",
        error_summary=error_summary,
        mutation_applied=mutation_applied,
    )
