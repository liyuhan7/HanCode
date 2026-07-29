"""A compact semantic activity feed; Raw Trace remains available separately."""

from __future__ import annotations

from textual.widgets import RichLog

from hancode.interfaces.tui.semantic_presenters import ActivityGroupView


def format_activity_card(view: ActivityGroupView) -> str:
    evidence = "\n".join(f"  • {item}" for item in view.evidence)
    actions = "  ".join(f"[{item}]" for item in view.actions)
    lines = [f"{view.time}  {view.title}", f"  {view.summary}"]
    if evidence:
        lines.append(evidence)
    if actions:
        lines.append(f"  {actions}")
    return "\n".join(lines)


class ActivityFeed(RichLog):
    """Read-only activity cards rendered as plain text in chronological order."""

    def update_groups(self, groups: tuple[ActivityGroupView, ...]) -> None:
        self.clear()
        for view in groups:
            self.write(format_activity_card(view))


__all__ = ["ActivityFeed", "format_activity_card"]
