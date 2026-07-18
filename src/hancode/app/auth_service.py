from __future__ import annotations

from hancode.app.credentials import CredentialProvider, CredentialStatus


class AuthService:
    """Application facade for credential operations with explicit injection."""

    def __init__(self, credential_provider: CredentialProvider | None = None) -> None:
        self._credential_provider = (
            credential_provider if credential_provider is not None else CredentialProvider()
        )

    def status(self, provider: str) -> CredentialStatus:
        return self._credential_provider.status(provider)

    def set_secret(self, provider: str, secret: str) -> None:
        self._credential_provider.set_secret(provider, secret)

    def clear_secret(self, provider: str) -> None:
        self._credential_provider.clear_secret(provider)
