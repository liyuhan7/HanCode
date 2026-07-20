"""Credential access boundaries for local and real-provider execution."""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import keyring
from dotenv import dotenv_values
from keyring.errors import PasswordDeleteError

from hancode.core.errors import HanCodeError, StructuredError


CredentialSource = Literal["keyring", "env", "dotenv", "missing"]

_KEYRING_SERVICE = "hancode"
_SUPPORTED_PROVIDERS = frozenset(
    {"mock", "openai_compatible", "anthropic", "local"}
)
_NO_CREDENTIAL_PROVIDERS = frozenset({"mock", "local"})
_ENVIRONMENT_NAMES = {
    "openai_compatible": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
class SecretStore(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None:
        ...

    def set_password(self, service_name: str, username: str, password: str) -> None:
        ...

    def delete_password(self, service_name: str, username: str) -> None:
        ...


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    configured: bool
    provider: str
    source: CredentialSource
    masked_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "masked_id": self.masked_id,
            "provider": self.provider,
            "source": self.source,
        }


class CredentialProvider:
    """Resolve provider credentials without exposing secret values to callers."""

    def __init__(
        self,
        *,
        keyring_backend: SecretStore | None = None,
        environ: Mapping[str, str] | None = None,
        dotenv_path: Path | None = None,
        dotenv_loader: Callable[[Path], Mapping[str, str | None]] | None = None,
    ) -> None:
        self._keyring = keyring_backend if keyring_backend is not None else keyring
        self._environ = os.environ if environ is None else environ
        self._dotenv_path = (
            Path.cwd() / ".env" if dotenv_path is None else dotenv_path
        )
        self._dotenv_loader = dotenv_values if dotenv_loader is None else dotenv_loader

    def status(
        self,
        provider: str,
        *,
        source: CredentialSource | None = None,
        project_root: Path | None = None,
    ) -> CredentialStatus:
        self._validate_provider(provider)
        if provider in _NO_CREDENTIAL_PROVIDERS:
            return CredentialStatus(
                configured=True,
                provider=provider,
                source="missing",
            )

        secret, resolved_source = self._resolve_secret(
            provider, source=source, project_root=project_root
        )
        if secret is None or resolved_source is None:
            return CredentialStatus(
                configured=False,
                provider=provider,
                source="missing",
            )
        return CredentialStatus(
            configured=True,
            provider=provider,
            source=resolved_source,
            masked_id=_mask_secret(secret),
        )

    def get_secret(
        self,
        provider: str,
        *,
        source: CredentialSource | None = None,
        project_root: Path | None = None,
    ) -> str:
        self._validate_provider(provider)
        if provider in _NO_CREDENTIAL_PROVIDERS:
            raise _credential_error(
                "credential_not_required",
                "This provider does not require a credential.",
                "Use a remote provider when a credential is required.",
                denied_rule="provider_credential_not_required",
            )

        secret, _ = self._resolve_secret(
            provider, source=source, project_root=project_root
        )
        if secret is None:
            raise _credential_error(
                "credential_missing",
                "No credential is configured for this provider.",
                "Configure the provider through auth login or an approved local source.",
                denied_rule="credential_required",
            )
        return secret

    def set_secret(self, provider: str, secret: str) -> None:
        self._validate_provider(provider)
        if provider in _NO_CREDENTIAL_PROVIDERS:
            raise _credential_error(
                "credential_not_required",
                "This provider does not accept stored credentials.",
                "Use a remote provider when storing a credential.",
                denied_rule="provider_credential_not_required",
            )
        if not isinstance(secret, str) or not secret.strip():
            raise _credential_error(
                "credential_value_required",
                "Credential input must not be empty.",
                "Enter a non-empty credential through hidden input.",
                denied_rule="credential_input_required",
            )

        try:
            self._keyring.set_password(_KEYRING_SERVICE, provider, secret.strip())
        except Exception:
            raise _credential_error(
                "credential_keyring_unavailable",
                "The operating-system credential store is unavailable.",
                "Enable a supported keyring backend and retry; no plaintext file was written.",
                denied_rule="secure_credential_store_required",
            ) from None

    def clear_secret(self, provider: str) -> None:
        self._validate_provider(provider)
        if provider in _NO_CREDENTIAL_PROVIDERS:
            return

        external_secret, external_source = self._resolve_external_secret(provider)
        if external_secret is not None and external_source is not None:
            raise _credential_error(
                "credential_external_source_requires_manual_clear",
                "The active credential is managed outside the secure store.",
                "Unset the mapped environment variable or remove the local .env value, then retry.",
                denied_rule="external_credential_source_manual_clear",
            )

        try:
            current_secret = _non_empty(
                self._keyring.get_password(_KEYRING_SERVICE, provider)
            )
        except Exception:
            raise _credential_error(
                "credential_keyring_unavailable",
                "The operating-system credential store is unavailable.",
                "Check the keyring backend and retry the clear operation.",
                denied_rule="secure_credential_store_required",
            ) from None
        if current_secret is None:
            return

        try:
            self._keyring.delete_password(_KEYRING_SERVICE, provider)
        except PasswordDeleteError:
            raise _credential_error(
                "credential_keyring_unavailable",
                "The operating-system credential store could not clear this credential.",
                "Check the keyring backend and retry the clear operation.",
                denied_rule="secure_credential_store_required",
            ) from None
        except Exception:
            raise _credential_error(
                "credential_keyring_unavailable",
                "The operating-system credential store could not clear this credential.",
                "Check the keyring backend and retry the clear operation.",
                denied_rule="secure_credential_store_required",
            ) from None

    def _resolve_secret(
        self,
        provider: str,
        *,
        source: CredentialSource | None = None,
        project_root: Path | None = None,
    ) -> tuple[str | None, CredentialSource | None]:
        if source == "env":
            return self._resolve_external_secret(provider, source="env")
        if source == "dotenv":
            return self._resolve_external_secret(
                provider, source="dotenv", project_root=project_root
            )
        if source == "keyring":
            keyring_secret, keyring_unavailable = self._read_keyring(provider)
            if keyring_secret is not None:
                return keyring_secret, "keyring"
            if keyring_unavailable:
                raise _credential_error(
                    "credential_keyring_unavailable",
                    "The operating-system credential store is unavailable.",
                    "Enable a supported keyring backend or configure an approved fallback source.",
                    denied_rule="secure_credential_store_required",
                )
            return None, None

        keyring_secret, keyring_unavailable = self._read_keyring(provider)
        if keyring_secret is not None:
            return keyring_secret, "keyring"

        external_secret, external_source = self._resolve_external_secret(provider)
        if external_secret is not None and external_source is not None:
            return external_secret, external_source
        if keyring_unavailable:
            raise _credential_error(
                "credential_keyring_unavailable",
                "The operating-system credential store is unavailable.",
                "Enable a supported keyring backend or configure an approved fallback source.",
                denied_rule="secure_credential_store_required",
            )
        return None, None

    def _resolve_external_secret(
        self,
        provider: str,
        *,
        source: Literal["env", "dotenv"] | None = None,
        project_root: Path | None = None,
    ) -> tuple[str | None, CredentialSource | None]:
        environment_name = _ENVIRONMENT_NAMES[provider]
        if source in {None, "env"}:
            environment_secret = _non_empty(self._environ.get(environment_name))
            if environment_secret is not None:
                return environment_secret, "env"

        if source in {None, "dotenv"}:
            dotenv_secret = self._read_dotenv(environment_name, project_root=project_root)
            if dotenv_secret is not None:
                return dotenv_secret, "dotenv"
        return None, None

    def _read_keyring(self, provider: str) -> tuple[str | None, bool]:
        try:
            value = _non_empty(self._keyring.get_password(_KEYRING_SERVICE, provider))
            return value, False
        except Exception:
            return None, True

    def _read_dotenv(
        self, environment_name: str, *, project_root: Path | None = None
    ) -> str | None:
        path = (
            project_root.resolve() / ".env"
            if project_root is not None
            else self._dotenv_path
        )
        try:
            if path.is_symlink():
                raise _credential_error(
                    "credential_dotenv_unavailable",
                    "The local dotenv source is not a regular file.",
                    "Use a regular local .env file or an approved environment source.",
                    denied_rule="safe_dotenv_source_required",
                )
            if not path.exists():
                return None
            if not path.is_file():
                raise _credential_error(
                    "credential_dotenv_unavailable",
                    "The local dotenv source is not a regular file.",
                    "Use a regular local .env file or an approved environment source.",
                    denied_rule="safe_dotenv_source_required",
                )
            values = self._dotenv_loader(path)
            if not isinstance(values, Mapping):
                raise TypeError("dotenv loader returned a non-mapping")
            value = values.get(environment_name)
            if value is not None and not isinstance(value, str):
                raise TypeError("dotenv loader returned a non-string value")
        except Exception:
            raise _credential_error(
                "credential_dotenv_unavailable",
                "The local dotenv source could not be read safely.",
                "Repair or remove the local .env source and retry.",
                denied_rule="safe_dotenv_source_required",
            ) from None
        return _non_empty(value)

    @staticmethod
    def _validate_provider(provider: str) -> None:
        if provider not in _SUPPORTED_PROVIDERS:
            raise _credential_error(
                "credential_unknown_provider",
                "Credential provider is not supported.",
                "Use mock, local, openai_compatible, or anthropic.",
                denied_rule="supported_credential_provider_required",
            )


credential_provider = CredentialProvider()


def credentials_status(provider: str) -> CredentialStatus:
    return credential_provider.status(provider)


def credentials_set(provider: str, secret: str) -> None:
    credential_provider.set_secret(provider, secret)


def credentials_clear(provider: str) -> None:
    credential_provider.clear_secret(provider)


def _non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _mask_secret(secret: str) -> str:
    if len(secret) < 4:
        return "****"
    suffix = "".join(
        "?" if _is_unsafe_display_character(character) else character
        for character in secret[-4:]
    )
    return f"****{suffix}"


def _is_unsafe_display_character(character: str) -> bool:
    return unicodedata.category(character).startswith("C") or character in {
        "\u2028",
        "\u2029",
    }


def _credential_error(
    error_code: str,
    message: str,
    suggested_fix: str,
    *,
    denied_rule: str,
) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="cli",
            denied_rule=denied_rule,
            suggested_fix=suggested_fix,
        )
    )
