from __future__ import annotations

from pathlib import Path

from hancode.app.credentials import (
    CredentialProvider,
    CredentialSource,
    CredentialStatus,
)


class AuthService:
    """Application facade for credential operations with explicit injection."""

    def __init__(self, credential_provider: CredentialProvider | None = None) -> None:
        self._credential_provider = (
            credential_provider if credential_provider is not None else CredentialProvider()
        )

    def status(
        self,
        provider: str,
        *,
        source: CredentialSource | None = None,
        project_root: Path | None = None,
    ) -> CredentialStatus:
        if source is None and project_root is None:
            return self._credential_provider.status(provider)
        return self._credential_provider.status(
            provider,
            source=source,
            project_root=project_root,
        )

    def set_secret(self, provider: str, secret: str) -> None:
        self._credential_provider.set_secret(provider, secret)

    def clear_secret(
        self,
        provider: str,
        *,
        source: CredentialSource | None = None,
    ) -> None:
        if source is None:
            self._credential_provider.clear_secret(provider)
            return
        self._credential_provider.clear_secret(provider, source=source)
