"""Shared fail-closed classification for credential and sensitive file paths."""

from __future__ import annotations

from pathlib import PurePosixPath


_SENSITIVE_DIRECTORIES = frozenset({"credentials", "secrets", "certificates", "keys"})
_SENSITIVE_FILENAMES = frozenset(
    {
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials",
        "credential",
        "secrets",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "token",
        "private_key",
        "privatekey",
    }
)
_SENSITIVE_SUFFIXES = frozenset(
    {".key", ".pem", ".token", ".crt", ".cer", ".der", ".p12", ".pfx"}
)


def is_sensitive_path(path: str) -> bool:
    """Return whether a project-relative path must never be accessed or written."""
    parts = tuple(part.casefold() for part in path.replace("\\", "/").split("/") if part)
    if any(part == ".env" or part.startswith(".env.") for part in parts):
        return True
    if any(part in _SENSITIVE_DIRECTORIES for part in parts):
        return True

    filename = parts[-1] if parts else ""
    return (
        filename in _SENSITIVE_FILENAMES
        or filename in _SENSITIVE_SUFFIXES
        or PurePosixPath(filename).suffix in _SENSITIVE_SUFFIXES
    )
