from __future__ import annotations

from pathlib import Path

import keyring.errors
import pytest

from hancode.app.credentials import CredentialProvider
from hancode.core.errors import HanCodeError, StructuredError


class FakeCredentialStore:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.values[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self.values.pop((service_name, username), None)


def test_fake_credential_provider_uses_keyring_first(tmp_path: Path) -> None:
    store = FakeCredentialStore()
    store.set_password("hancode", "openai_compatible", "keyring-secret-9f2a")
    provider = CredentialProvider(
        keyring_backend=store,
        environ={"OPENAI_API_KEY": "environment-secret"},
        dotenv_path=tmp_path / ".env",
    )

    status = provider.status("openai_compatible")

    assert status.configured is True
    assert status.source == "keyring"
    assert status.masked_id == "****9f2a"
    assert provider.get_secret("openai_compatible") == "keyring-secret-9f2a"


def test_credential_status_falls_back_to_environment(tmp_path: Path) -> None:
    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={"OPENAI_API_KEY": "environment-secret-12ab"},
        dotenv_path=tmp_path / ".env",
    )

    status = provider.status("openai_compatible")

    assert status.configured is True
    assert status.source == "env"
    assert status.masked_id == "****12ab"


def test_credential_status_falls_back_to_dotenv(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=dotenv-secret-34cd\n", encoding="utf-8")
    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=dotenv_path,
    )

    status = provider.status("openai_compatible")

    assert status.configured is True
    assert status.source == "dotenv"
    assert status.masked_id == "****34cd"


def test_credential_status_reports_missing_without_secret(tmp_path: Path) -> None:
    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    status = provider.status("anthropic")

    assert status.configured is False
    assert status.provider == "anthropic"
    assert status.source == "missing"
    assert status.masked_id is None


def test_auth_status_does_not_print_secret(tmp_path: Path) -> None:
    secret = "fake-secret-56ef"
    store = FakeCredentialStore()
    store.set_password("hancode", "openai_compatible", secret)
    provider = CredentialProvider(
        keyring_backend=store,
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    output = provider.status("openai_compatible").to_dict()

    assert secret not in str(output)
    assert output == {
        "configured": True,
        "masked_id": "****56ef",
        "provider": "openai_compatible",
        "source": "keyring",
    }


def test_credentials_set_writes_fake_keyring_only(tmp_path: Path) -> None:
    store = FakeCredentialStore()
    dotenv_path = tmp_path / ".env"
    provider = CredentialProvider(
        keyring_backend=store,
        environ={},
        dotenv_path=dotenv_path,
    )

    provider.set_secret("openai_compatible", "new-secret-78ab")

    assert store.get_password("hancode", "openai_compatible") == "new-secret-78ab"
    assert not dotenv_path.exists()


def test_credentials_clear_removes_secret(tmp_path: Path) -> None:
    store = FakeCredentialStore()
    store.set_password("hancode", "anthropic", "clear-me-90cd")
    provider = CredentialProvider(
        keyring_backend=store,
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    provider.clear_secret("anthropic")

    assert store.get_password("hancode", "anthropic") is None
    assert provider.status("anthropic").source == "missing"


def test_credentials_clear_reports_delete_failure(tmp_path: Path) -> None:
    class DeleteFailureCredentialStore(FakeCredentialStore):
        def delete_password(self, service_name: str, username: str) -> None:
            raise keyring.errors.PasswordDeleteError("delete failed")

    store = DeleteFailureCredentialStore()
    store.set_password("hancode", "anthropic", "delete-failure-12ab")
    provider = CredentialProvider(
        keyring_backend=store,
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    with pytest.raises(HanCodeError) as raised:
        provider.clear_secret("anthropic")

    assert raised.value.structured_error.error_code == "credential_keyring_unavailable"


def test_credentials_rejects_empty_secret(tmp_path: Path) -> None:
    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    with pytest.raises(HanCodeError) as raised:
        provider.set_secret("openai_compatible", "   ")

    assert raised.value.structured_error.error_code == "credential_value_required"


def test_credentials_rejects_unknown_provider(tmp_path: Path) -> None:
    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    with pytest.raises(HanCodeError) as raised:
        provider.status("unknown")

    assert raised.value.structured_error.error_code == "credential_unknown_provider"


def test_keyring_unavailable_fails_closed_without_writing_dotenv(
    tmp_path: Path,
) -> None:
    class UnavailableCredentialStore(FakeCredentialStore):
        def set_password(
            self, service_name: str, username: str, password: str
        ) -> None:
            raise keyring.errors.NoKeyringError("backend unavailable")

    dotenv_path = tmp_path / ".env"
    provider = CredentialProvider(
        keyring_backend=UnavailableCredentialStore(),
        environ={},
        dotenv_path=dotenv_path,
    )

    with pytest.raises(HanCodeError) as raised:
        provider.set_secret("openai_compatible", "never-written-abcd")

    assert raised.value.structured_error.error_code == "credential_keyring_unavailable"
    assert not dotenv_path.exists()


def test_keyring_read_failure_is_structured_when_no_fallback_exists(
    tmp_path: Path,
) -> None:
    class UnavailableCredentialStore(FakeCredentialStore):
        def get_password(self, service_name: str, username: str) -> str | None:
            raise keyring.errors.NoKeyringError("backend unavailable")

    provider = CredentialProvider(
        keyring_backend=UnavailableCredentialStore(),
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    with pytest.raises(HanCodeError) as raised:
        provider.status("openai_compatible")

    assert raised.value.structured_error.error_code == "credential_keyring_unavailable"


def test_mock_and_local_require_no_secret(tmp_path: Path) -> None:
    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    for name in ("mock", "local"):
        status = provider.status(name)
        assert status.configured is True
        assert status.source == "missing"
        assert status.masked_id is None


def test_dotenv_parse_failure_is_structured(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=not-used\n", encoding="utf-8")

    def fail_loader(path: Path) -> dict[str, str | None]:
        raise ValueError("malformed dotenv")

    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=dotenv_path,
        dotenv_loader=fail_loader,
    )

    with pytest.raises(HanCodeError) as raised:
        provider.status("openai_compatible")

    assert raised.value.structured_error.error_code == "credential_dotenv_unavailable"


def test_dotenv_loader_unexpected_failure_is_structured(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=not-used\n", encoding="utf-8")

    def fail_loader(path: Path) -> dict[str, str | None]:
        raise TypeError("unexpected parser failure")

    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=dotenv_path,
        dotenv_loader=fail_loader,
    )

    with pytest.raises(HanCodeError) as raised:
        provider.status("openai_compatible")

    error = raised.value.structured_error
    assert error.error_code == "credential_dotenv_unavailable"
    assert error.phase == "cli"
    assert error.denied_rule == "safe_dotenv_source_required"
    assert error.suggested_fix


def test_dotenv_loader_hancode_error_is_sanitized(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=not-used\n", encoding="utf-8")

    def fail_loader(path: Path) -> dict[str, str | None]:
        raise HanCodeError(
            StructuredError(
                error_code="loader_failure",
                message="loader leaked fake-sensitive-text",
                phase="cli",
                denied_rule="loader_boundary",
                suggested_fix="retry",
            )
        )

    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=dotenv_path,
        dotenv_loader=fail_loader,
    )

    with pytest.raises(HanCodeError) as raised:
        provider.status("openai_compatible")

    error = raised.value.structured_error
    assert error.error_code == "credential_dotenv_unavailable"
    assert "fake-sensitive-text" not in str(error)


def test_real_dotenv_decode_failure_is_structured(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_bytes(b"\xff\xfe\xfd")
    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=dotenv_path,
    )

    with pytest.raises(HanCodeError) as raised:
        provider.status("openai_compatible")

    assert raised.value.structured_error.error_code == "credential_dotenv_unavailable"


def test_mask_replaces_unicode_control_characters(tmp_path: Path) -> None:
    store = FakeCredentialStore()
    store.set_password("hancode", "anthropic", "ab\u0085cd")
    provider = CredentialProvider(
        keyring_backend=store,
        environ={},
        dotenv_path=tmp_path / ".env",
    )

    status = provider.status("anthropic")

    assert status.masked_id == "****b?cd"


def test_dotenv_symlink_is_structured(tmp_path: Path) -> None:
    target = tmp_path / "real.env"
    target.write_text("OPENAI_API_KEY=not-used\n", encoding="utf-8")
    dotenv_path = tmp_path / ".env"
    try:
        dotenv_path.symlink_to(target)
    except OSError:
        pytest.skip("current platform does not allow creating symlinks")

    provider = CredentialProvider(
        keyring_backend=FakeCredentialStore(),
        environ={},
        dotenv_path=dotenv_path,
    )

    with pytest.raises(HanCodeError) as raised:
        provider.status("openai_compatible")

    assert raised.value.structured_error.error_code == "credential_dotenv_unavailable"
