"""Focused Textual modal dialogs for explicit human decisions (S5-R4)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from hancode.interfaces.tui.presenters import ApprovalView, RollbackView


class ApprovalDialog(ModalScreen[str | None]):
    """Approval decision modal; ordinary composer input cannot reach it."""

    BINDINGS = [
        ("y", "approve", "Approve"),
        ("n", "reject", "Reject"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, view: ApprovalView) -> None:
        super().__init__()
        self._view = view

    def compose(self) -> ComposeResult:
        view = self._view
        targets = "\n".join(f"- {target}" for target in view.targets) or "(none)"
        preview = view.diff_preview or "(none)"
        with Vertical(id="tui-approval-dialog"):
            yield Static("Approval required", markup=False)
            yield Static(f"Approval ID: {view.approval_id}", markup=False)
            yield Static(f"Tool: {view.tool_name}\nRisk: {view.risk_level}", markup=False)
            yield Static(f"Reason: {view.reason}\nTargets:\n{targets}", markup=False)
            yield Static(f"Preview:\n{preview}", markup=False)
            with Horizontal():
                yield Button("Approve [Y]", id="tui-approval-approve", variant="success")
                yield Button("Reject [N]", id="tui-approval-reject", variant="error")
                yield Button("Cancel [Esc]", id="tui-approval-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "tui-approval-approve": "approve",
            "tui-approval-reject": "reject",
            "tui-approval-cancel": None,
        }
        if event.button.id in actions:
            self.dismiss(actions[event.button.id])

    def action_approve(self) -> None:
        self.dismiss("approve")

    def action_reject(self) -> None:
        self.dismiss("reject")

    def action_cancel(self) -> None:
        self.dismiss(None)


class RollbackDialog(ModalScreen[str | None]):
    """Second-confirmation modal for the latest trusted checkpoint rollback."""

    BINDINGS = [
        ("y", "confirm", "Confirm"),
        ("n", "cancel", "Cancel"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, view: RollbackView) -> None:
        super().__init__()
        self._view = view

    def compose(self) -> ComposeResult:
        view = self._view
        files = "\n".join(f"- {name}" for name in view.files) or "(none)"
        with Vertical(id="tui-rollback-dialog"):
            yield Static("Rollback latest checkpoint?", markup=False)
            yield Static(
                f"Checkpoint: {view.checkpoint_id or 'none'}\n"
                f"Available: {'yes' if view.available else 'no'}\n"
                f"Files:\n{files}",
                markup=False,
            )
            with Horizontal():
                yield Button("Confirm [Y]", id="tui-rollback-confirm", variant="error")
                yield Button("Cancel [N/Esc]", id="tui-rollback-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tui-rollback-confirm":
            self.dismiss("confirm")
        elif event.button.id == "tui-rollback-cancel":
            self.dismiss("cancel")

    def action_confirm(self) -> None:
        self.dismiss("confirm")

    def action_cancel(self) -> None:
        self.dismiss("cancel")


__all__ = ["ApprovalDialog", "RollbackDialog"]
