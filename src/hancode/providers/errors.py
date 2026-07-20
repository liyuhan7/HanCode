"""Provider error model with retry classification."""

from __future__ import annotations

from hancode.core.errors import HanCodeError, StructuredError

__all__ = ["ProviderError"]


class ProviderError(HanCodeError):
    """Error raised by a provider adapter, classified by retryability."""

    def __init__(
        self,
        structured_error: StructuredError,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(structured_error)
        self._retryable = retryable

    @property
    def retryable(self) -> bool:
        return self._retryable
