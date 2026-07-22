"""S5-R0: Textual app boundary checks."""

from __future__ import annotations

from pathlib import Path


def test_app_does_not_call_application_services_directly() -> None:
    app_path = Path(__file__).parents[1] / "src" / "hancode" / "interfaces" / "tui" / "app.py"
    source = app_path.read_text(encoding="utf-8")

    for service_attribute in (
        "self._task_service.",
        "self._interaction_service.",
        "self._approval_service.",
        "self._inspection_service.",
        "self._recovery_service.",
    ):
        assert service_attribute not in source
