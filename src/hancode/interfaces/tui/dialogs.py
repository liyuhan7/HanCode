"""Focused Textual modal dialogs for explicit human decisions (S5-R4)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from hancode.interfaces.tui.presenters import ApprovalView, RollbackView
from hancode.interfaces.tui.copy.zh_cn import TOOL_LABELS, label_for


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
        targets = "\n".join(f"- {target}" for target in view.targets) or "（未记录目标文件）"
        preview = view.diff_preview or "（当前请求没有可展示的 Diff 预览）"
        title, approve, reject, cancel = _approval_copy(view.category, view.tool_name)
        with Vertical(id="tui-approval-dialog"):
            yield Static(title, markup=False)
            yield Static(f"操作：{label_for(view.tool_name, TOOL_LABELS)}\n技术标识：{view.tool_name}", markup=False)
            yield Static(f"操作目的\n{view.reason or '未提供具体说明'}", markup=False)
            yield Static(f"影响范围\n{targets}", markup=False)
            yield Static(f"证据预览\n{preview}", markup=False)
            yield Static("安全说明\n✓ 该决策仅对本次请求有效\n✓ 技术详情可在检查视图查看", markup=False)
            with Horizontal():
                yield Button(f"{approve} [Y]", id="tui-approval-approve", variant="success")
                yield Button(f"{reject} [N]", id="tui-approval-reject", variant="error")
                yield Button(f"{cancel} [Esc]", id="tui-approval-cancel")

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
        files = "\n".join(f"- {name}" for name in view.files) or "（未记录文件）"
        with Vertical(id="tui-rollback-dialog"):
            yield Static("恢复到最近检查点？", markup=False)
            yield Static(
                f"检查点：{view.checkpoint_id or '无'}\n"
                f"以下文件将恢复到修改前状态：\n{files}\n\n"
                "当前修改将被丢弃；取消不会改动任何文件。",
                markup=False,
            )
            with Horizontal():
                yield Button("恢复这些文件 [Y]", id="tui-rollback-confirm", variant="error")
                yield Button("保留当前修改 [N/Esc]", id="tui-rollback-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tui-rollback-confirm":
            self.dismiss("confirm")
        elif event.button.id == "tui-rollback-cancel":
            self.dismiss("cancel")

    def action_confirm(self) -> None:
        self.dismiss("confirm")

    def action_cancel(self) -> None:
        self.dismiss("cancel")


class RejectionReasonDialog(ModalScreen[str | None]):
    """Optional reason capture; explicit rejection still works when left blank."""

    BINDINGS = [("escape", "cancel", "取消")]

    def compose(self) -> ComposeResult:
        with Vertical(id="tui-rejection-dialog"):
            yield Static("拒绝本次操作", markup=False)
            yield Static("可选：说明拒绝原因。留空会以“未提供原因”记录。", markup=False)
            yield Input(placeholder="例如：先查看完整 Diff", id="tui-rejection-reason")
            with Horizontal():
                yield Button("确认拒绝", id="tui-rejection-confirm", variant="error")
                yield Button("返回", id="tui-rejection-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tui-rejection-confirm":
            reason = self.query_one("#tui-rejection-reason", Input).value.strip()
            self.dismiss(reason or "未提供原因")
        elif event.button.id == "tui-rejection-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


def _approval_copy(category: str, tool_name: str) -> tuple[str, str, str, str]:
    if category in {"source_write", "source_overwrite", "multi_file_write"}:
        return ("确认代码修改", "仅允许本次修改", "拒绝并说明原因", "稍后处理")
    if category == "run_tests":
        return ("确认运行测试", "运行本次测试", "拒绝执行", "稍后处理")
    if category == "run_build":
        return ("确认构建项目", "开始构建", "取消构建", "稍后处理")
    return (f"确认操作：{tool_name}", "允许本次操作", "拒绝本次操作", "稍后处理")


__all__ = ["ApprovalDialog", "RollbackDialog", "RejectionReasonDialog"]
