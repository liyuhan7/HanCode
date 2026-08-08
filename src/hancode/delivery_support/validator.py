"""DeliveryValidator — Validate step of the S14 delivery pipeline.

Turns collected learning evidence into hard blockers and soft warnings, per the
frozen contract in architecture S14.6. Hard blockers prevent ``completed``; the
warnings never change the terminal status.
"""

from __future__ import annotations

from dataclasses import dataclass

from hancode.core.learning_evidence import LearningSnapshot, TestAttemptEvidence
from hancode.core.models import TaskStatus
from hancode.delivery_support.collector import CollectedDelivery


@dataclass(frozen=True, slots=True)
class DeliveryValidation:
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    learning_contract_status: str


def validate_learning_delivery(collected: CollectedDelivery) -> DeliveryValidation:
    snapshot = collected.snapshot
    state = collected.state
    matrix = collected.matrix
    blockers: list[str] = []
    warnings: list[str] = []

    core_requirements = [item for item in snapshot.requirements if item.is_core]
    if not core_requirements:
        blockers.append("缺少核心需求证据。")
    for requirement in core_requirements:
        if matrix.coverage.get(requirement.id) != "covered":
            blockers.append(
                f"核心需求未形成完整实现+测试链：{requirement.id}。"
            )

    latest_attempt_status = (
        snapshot.test_attempts[-1].status if snapshot.test_attempts else None
    )
    if latest_attempt_status != "passed":
        blockers.append("最新测试未通过，任务不能标记为 completed。")

    if collected.build_required and collected.latest_build_status != "passed":
        blockers.append("配置了 Build 命令，但 Build 尚未通过。")

    # A passing test must cover the latest change (no stale coverage).
    if snapshot.changes and snapshot.test_attempts:
        latest_change_id = snapshot.changes[-1].id
        latest_passing_attempt = _last_passing_attempt(snapshot)
        if (
            latest_passing_attempt is not None
            and latest_change_id not in latest_passing_attempt.tested_change_ids
        ):
            blockers.append("最新通过的测试早于最新代码修改，覆盖已过期。")

    # Failure history requires a complete recovery chain.
    if snapshot.failures:
        recovered_failures = {rec.failure_id for rec in snapshot.recoveries}
        for failure in snapshot.failures:
            if failure.id not in recovered_failures:
                blockers.append(f"存在失败但缺少修复链：{failure.id}。")

    # KnowledgeCard evidence references must all resolve.
    known_ids = _known_evidence_ids(snapshot)
    for card in snapshot.knowledge_cards:
        for ref in card.evidence_refs:
            if ref not in known_ids:
                blockers.append(f"KnowledgeCard {card.id} 引用了无效证据：{ref}。")

    # Warnings
    if not snapshot.decisions:
        warnings.append("没有记录候选设计或舍弃原因。")
    if not snapshot.knowledge_cards:
        warnings.append("没有任何 KnowledgeCard，缺少可迁移知识复盘。")
    for change in snapshot.changes:
        if len(change.reason.strip()) < 8:
            warnings.append(f"修改 {change.id} 的“为什么”证据不足。")

    if state.inconsistent or state.status is TaskStatus.INCONSISTENT:
        contract_status = "inconsistent"
    elif blockers:
        contract_status = "incomplete"
    else:
        contract_status = "verified"

    return DeliveryValidation(
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        learning_contract_status=contract_status,
    )


def _last_passing_attempt(snapshot: LearningSnapshot) -> TestAttemptEvidence | None:
    for attempt in reversed(snapshot.test_attempts):
        if attempt.status == "passed":
            return attempt
    return None


def _known_evidence_ids(snapshot: object) -> set[str]:
    ids: set[str] = set()
    for attribute in (
        "requirements",
        "decisions",
        "plan_steps",
        "changes",
        "test_attempts",
        "failures",
        "recoveries",
    ):
        for item in getattr(snapshot, attribute, ()):
            ids.add(item.id)
    return ids


__all__ = ["DeliveryValidation", "validate_learning_delivery"]
