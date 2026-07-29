"""Pure semantic activity grouping for the Chinese-first workbench."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from hancode.interfaces.tui.copy.zh_cn import EVENT_LABELS, PHASE_LABELS, TOOL_LABELS, label_for
from hancode.storage.trace import TraceEvent


@dataclass(frozen=True, slots=True)
class ActivityGroupView:
    activity_id: str
    kind: str
    title: str
    summary: str
    phase: str
    status: str
    time: str
    related_event_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    actions: tuple[str, ...]


_READ_TOOLS = frozenset({"read_file", "list_files", "search_text"})
_WRITE_TOOLS = frozenset({"edit_file", "write_file"})


def present_activity_groups(events: tuple[TraceEvent, ...]) -> tuple[ActivityGroupView, ...]:
    """Group adjacent deterministic trace patterns without discarding events."""
    groups: list[ActivityGroupView] = []
    index = 0
    while index < len(events):
        event = events[index]
        tool_name = _tool_name(event)
        if event.event_type == "tool_called" and tool_name in _READ_TOOLS:
            consumed = [event]
            cursor = index + 1
            while cursor < len(events):
                candidate = events[cursor]
                if candidate.event_type != "tool_called" or _tool_name(candidate) not in _READ_TOOLS:
                    break
                consumed.append(candidate)
                cursor += 1
            groups.append(_read_group(consumed))
            index = cursor
            continue
        if event.event_type == "checkpoint_created" and index + 1 < len(events):
            candidate = events[index + 1]
            if candidate.event_type in {"tool_called", "tool_completed"} and _tool_name(candidate) in _WRITE_TOOLS:
                groups.append(_write_group(event, candidate))
                index += 2
                continue
        if event.event_type == "tool_called" and tool_name == "run_tests" and index + 1 < len(events):
            candidate = events[index + 1]
            if candidate.event_type in {"test_completed", "test_failed"}:
                groups.append(_test_group(event, candidate))
                index += 2
                continue
        groups.append(_single_group(event))
        index += 1
    return tuple(groups)


def _read_group(events: list[TraceEvent]) -> ActivityGroupView:
    first = events[0]
    return _group(
        first,
        "inspection",
        f"已检查 {len(events)} 个位置",
        "HanCode 正在收集实现与需求证据。",
        events,
        (),
        ("查看技术事件",),
    )


def _write_group(checkpoint: TraceEvent, write: TraceEvent) -> ActivityGroupView:
    path = _path(write) or "目标文件"
    return _group(
        checkpoint,
        "change",
        "已安全修改文件",
        f"修改前已创建检查点；已处理 {path}。",
        [checkpoint, write],
        (f"检查点：{_checkpoint_id(checkpoint) or '已创建'}",),
        ("查看改动", "查看技术事件"),
    )


def _test_group(start: TraceEvent, result: TraceEvent) -> ActivityGroupView:
    succeeded = result.event_type == "test_completed" and result.status != "failed"
    title = "测试通过" if succeeded else "测试未全部通过"
    summary = "测试已完成，可查看测试报告。" if succeeded else (result.error_summary or "请查看测试报告和下一步建议。")
    return _group(start, "test", title, summary, [start, result], (), ("查看测试结果", "查看改动"))


def _single_group(event: TraceEvent) -> ActivityGroupView:
    tool_name = _tool_name(event)
    actions: tuple[str, ...]
    if event.event_type == "policy_denied":
        title = "已阻止不安全操作"
        summary = event.error_summary or "该操作未执行。"
        actions = ("查看规则", "查看技术事件")
    elif event.event_type in {"rollback_started", "rollback_completed"}:
        title = label_for(event.event_type, EVENT_LABELS)
        summary = event.error_summary or "检查点恢复状态已记录。"
        actions = ("查看检查点", "查看技术事件")
    elif tool_name:
        title = label_for(tool_name, TOOL_LABELS)
        title = f"{title}：{label_for(event.event_type, EVENT_LABELS)}"
        summary = event.error_summary or "已记录本次工具操作。"
        actions = ("查看技术事件",)
    else:
        title = label_for(event.event_type, EVENT_LABELS)
        summary = event.error_summary or "已记录运行事件。"
        actions = ("查看技术事件",)
    return _group(event, event.event_type, title, summary, [event], (), actions)


def _group(
    event: TraceEvent,
    kind: str,
    title: str,
    summary: str,
    related: list[TraceEvent],
    evidence: tuple[str, ...],
    actions: tuple[str, ...],
) -> ActivityGroupView:
    return ActivityGroupView(
        activity_id=related[0].event_id,
        kind=kind,
        title=title,
        summary=summary,
        phase=label_for(event.phase.value, PHASE_LABELS),
        status=event.status,
        time=event.timestamp.astimezone().strftime("%H:%M"),
        related_event_ids=tuple(item.event_id for item in related),
        evidence=evidence,
        actions=actions,
    )


def _tool_name(event: TraceEvent) -> str | None:
    action = event.action
    value = action.get("tool_name") if action is not None else None
    return value if isinstance(value, str) else None


def _path(event: TraceEvent) -> str | None:
    action = event.action
    if action is None:
        return None
    args = action.get("args")
    value = args.get("path") if isinstance(args, Mapping) else None
    return value if isinstance(value, str) else None


def _checkpoint_id(event: TraceEvent) -> str | None:
    observation = event.observation
    value = observation.get("checkpoint_id") if observation is not None else None
    return value if isinstance(value, str) else None


__all__ = ["ActivityGroupView", "present_activity_groups"]
