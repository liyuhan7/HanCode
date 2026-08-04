"""In-process cooperative pause signalling for a single agent run."""

from __future__ import annotations

from threading import Event


class PauseToken:
    """Thread-safe, one-way pause request scoped to one active run."""

    def __init__(self) -> None:
        self._requested = Event()

    def request(self) -> None:
        self._requested.set()

    def is_requested(self) -> bool:
        return self._requested.is_set()
