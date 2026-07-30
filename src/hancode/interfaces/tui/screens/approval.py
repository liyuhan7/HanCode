"""Full-screen source-change approval surface."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Footer, Static

from hancode.interfaces.tui.decision_presenters import present_decision
from hancode.interfaces.tui.presenters import ApprovalView


SOURCE_APPROVAL_CATEGORIES = frozenset(
    {"source_write", "source_overwrite", "multi_file_write"}
)

_RISK_LABELS = {
    "low": "低风险",
    "medium": "中风险",
    "high": "高风险",
    "critical": "严重风险",
}


class SourceApprovalScreen(ModalScreen[str | None]):
    """Review a source Diff without allowing ordinary composer input through."""

    BINDINGS = [
        ("y", "approve", "允许本次修改"),
        ("n", "reject", "拒绝并说明原因"),
        ("escape", "cancel", "稍后处理"),
        ("j", "scroll_down", "向下滚动"),
        ("k", "scroll_up", "向上滚动"),
        ("pagedown", "page_down", "向下翻页"),
        ("pageup", "page_up", "向上翻页"),
    ]

    DEFAULT_CSS = """
    SourceApprovalScreen {
        background: $background;
        color: $text;
    }
    #source-approval-shell {
        width: 100%;
        height: 100%;
        background: $background;
    }
    #source-approval-header {
        height: 5;
        padding: 1 2;
        background: $surface;
        border-bottom: solid $primary;
    }
    #source-approval-title {
        width: 1fr;
        content-align: left middle;
        color: $primary;
        text-style: bold;
    }
    #source-approval-badges {
        width: auto;
        min-width: 24;
        content-align: right middle;
        color: $warning;
    }
    #source-approval-summary {
        height: auto;
        max-height: 9;
        padding: 1 2;
        background: $surface;
    }
    #source-approval-intent {
        width: 2fr;
        height: auto;
        padding-right: 2;
    }
    #source-approval-scope {
        width: 3fr;
        height: auto;
        color: $text-muted;
    }
    #source-approval-technical {
        height: auto;
        margin: 0 2;
        padding: 0 1;
        background: $surface;
    }
    #source-approval-evidence-title {
        height: 3;
        padding: 1 2 0 2;
        color: $primary;
        text-style: bold;
    }
    #source-approval-diff {
        height: 1fr;
        margin: 0 2;
        border: solid $panel;
        background: $surface;
    }
    #source-approval-diff-content {
        width: 100%;
        height: auto;
        padding: 1 2;
    }
    #source-approval-status {
        height: 3;
        padding: 1 2;
        background: $panel;
        color: $text-muted;
    }
    #source-approval-actions {
        height: 4;
        padding: 0 2;
        align-horizontal: right;
        background: $surface;
    }
    #source-approval-actions Button {
        margin-left: 1;
    }
    SourceApprovalScreen.-narrow #source-approval-header {
        height: 4;
        layout: vertical;
        padding: 0 1;
    }
    SourceApprovalScreen.-narrow #source-approval-title,
    SourceApprovalScreen.-narrow #source-approval-badges {
        width: 100%;
        min-width: 0;
        height: auto;
        content-align: left middle;
    }
    SourceApprovalScreen.-narrow #source-approval-summary {
        height: auto;
        max-height: 8;
        layout: vertical;
        padding: 0 1;
    }
    SourceApprovalScreen.-narrow #source-approval-intent,
    SourceApprovalScreen.-narrow #source-approval-scope {
        width: 100%;
        padding-right: 0;
    }
    SourceApprovalScreen.-narrow #source-approval-technical {
        display: none;
    }
    SourceApprovalScreen.-narrow #source-approval-evidence-title,
    SourceApprovalScreen.-narrow #source-approval-status {
        height: 2;
        padding: 0 1;
    }
    SourceApprovalScreen.-narrow #source-approval-actions {
        height: 6;
        layout: vertical;
        padding: 0 1;
    }
    SourceApprovalScreen.-narrow #source-approval-actions Button {
        width: 100%;
        height: 2;
        min-height: 2;
        margin: 0;
    }
    SourceApprovalScreen.-narrow Footer {
        display: none;
    }
    """

    def __init__(self, view: ApprovalView) -> None:
        super().__init__()
        self._view = view

    def compose(self) -> ComposeResult:
        decision = present_decision(self._view)
        targets = _present_targets(decision.scope)
        risk = _RISK_LABELS.get(self._view.risk_level, self._view.risk_level or "风险未知")
        recoverable = "✓ 可通过 Checkpoint 恢复" if decision.recoverable else "不可自动恢复"
        diff = self._view.diff_preview or "（当前请求没有可展示的 Diff 预览）"
        technical = "\n".join(
            f"{item.label}: {item.display_value or '未记录'}"
            for item in decision.technical_detail
        )

        with Vertical(id="source-approval-shell"):
            with Horizontal(id="source-approval-header"):
                yield Static(
                    f"{decision.title}\n仅决定当前这一次操作",
                    id="source-approval-title",
                    markup=False,
                )
                yield Static(
                    f"{risk}  ·  {recoverable}",
                    id="source-approval-badges",
                    markup=False,
                )
            with Horizontal(id="source-approval-summary"):
                yield Static(
                    f"将执行什么\n{decision.intent}\n\n为什么\n{decision.reason}",
                    id="source-approval-intent",
                    markup=False,
                )
                yield Static(
                    f"影响范围 · {len(decision.scope)} 个目标\n{targets}",
                    id="source-approval-scope",
                    markup=False,
                )
            with Collapsible(
                Static(technical, markup=False),
                title="技术详情",
                collapsed=True,
                id="source-approval-technical",
            ):
                pass
            yield Static(
                "变更证据  ·  J/K 或 PgUp/PgDn 滚动",
                id="source-approval-evidence-title",
                markup=False,
            )
            with VerticalScroll(id="source-approval-diff"):
                yield Static(diff, id="source-approval-diff-content", markup=False)
            yield Static(
                f"{decision.risk_summary}  批准后仍由 ToolPolicy、Checkpoint 和 Application Service 执行。",
                id="source-approval-status",
                markup=False,
            )
            with Horizontal(id="source-approval-actions"):
                yield Button(
                    f"{decision.primary_action} [Y]",
                    id="source-approval-approve",
                    variant="success",
                )
                yield Button(
                    f"{decision.reject_action} [N]",
                    id="source-approval-reject",
                    variant="error",
                )
                yield Button("稍后处理 [Esc]", id="source-approval-cancel")
            yield Footer()

    def on_mount(self) -> None:
        self._apply_layout(self.size.width)
        self.query_one("#source-approval-approve", Button).focus()

    def on_resize(self, event: object) -> None:
        size = getattr(event, "size", self.size)
        self._apply_layout(size.width)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "source-approval-approve":
            self.dismiss("approve")
        elif event.button.id == "source-approval-reject":
            self.dismiss("reject")
        elif event.button.id == "source-approval-cancel":
            self.dismiss(None)

    def action_approve(self) -> None:
        self.dismiss("approve")

    def action_reject(self) -> None:
        self.dismiss("reject")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_scroll_down(self) -> None:
        self.query_one("#source-approval-diff", VerticalScroll).scroll_down(
            animate=False
        )

    def action_scroll_up(self) -> None:
        self.query_one("#source-approval-diff", VerticalScroll).scroll_up(
            animate=False
        )

    def action_page_down(self) -> None:
        self.query_one("#source-approval-diff", VerticalScroll).scroll_page_down(
            animate=False
        )

    def action_page_up(self) -> None:
        self.query_one("#source-approval-diff", VerticalScroll).scroll_page_up(
            animate=False
        )

    def _apply_layout(self, width: int) -> None:
        self.set_class(width < 70, "-narrow")
        self.set_class(70 <= width < 100, "-medium")


def _present_targets(targets: tuple[str, ...]) -> str:
    visible = targets[:4]
    lines = [f"• {target}" for target in visible]
    if len(targets) > len(visible):
        lines.append(f"…另有 {len(targets) - len(visible)} 个目标")
    return "\n".join(lines) or "（未记录目标文件）"


__all__ = ["SOURCE_APPROVAL_CATEGORIES", "SourceApprovalScreen"]
