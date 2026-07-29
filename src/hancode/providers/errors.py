"""Provider error model with retry classification."""

from __future__ import annotations

from hancode.core.errors import HanCodeError, StructuredError

__all__ = ["ProviderError"]


class ProviderError(HanCodeError):
    """Error raised by a provider adapter at the runtime boundary."""

    def __init__(
        self,
        structured_error: StructuredError,
        *,
        protocol_retryable: bool = False,
    ) -> None:
        super().__init__(structured_error)
        self._protocol_retryable = protocol_retryable

    @property
    def protocol_retryable(self) -> bool:
        return self._protocol_retryable
