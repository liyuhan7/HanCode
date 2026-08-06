"""TraceabilityBuilder — requirement coverage and evidence links — S14-R4.1.

The matrix is derived only from a validated :class:`LearningSnapshot`; it never
reads Markdown. Requirement coverage is intentionally strict: a core requirement
is ``covered`` only when a change references it and a passing test attempt also
references it (directly or through that change). Overall test success does not
implicitly cover unlinked requirements.
"""

from __future__ import annotations

from dataclasses import dataclass

from hancode.core.learning_evidence import LearningSnapshot, TraceabilityLink


@dataclass(frozen=True, slots=True)
class TraceabilityMatrix:
    links: tuple[TraceabilityLink, ...]
    coverage: dict[str, str]


def build_traceability(snapshot: LearningSnapshot) -> TraceabilityMatrix:
    links: list[TraceabilityLink] = []

    # Requirement → Decision / Plan step
    for decision in snapshot.decisions:
        for requirement_id in decision.requirement_refs:
            links.append(
                TraceabilityLink(requirement_id, decision.id, "REQUIREMENT_DECISION")
            )
    for step in snapshot.plan_steps:
        for requirement_id in step.requirement_refs:
            links.append(
                TraceabilityLink(requirement_id, step.id, "REQUIREMENT_PLAN_STEP")
            )
        for change in snapshot.changes:
            if step.id in change.plan_step_refs:
                links.append(
                    TraceabilityLink(step.id, change.id, "PLAN_STEP_CHANGE")
                )

    # Change → Test
    for attempt in snapshot.test_attempts:
        for change_id in attempt.tested_change_ids:
            links.append(TraceabilityLink(change_id, attempt.id, "CHANGE_TEST"))

    # Test → Failure → Recovery → Change
    for failure in snapshot.failures:
        links.append(
            TraceabilityLink(failure.test_attempt_id, failure.id, "TEST_FAILURE")
        )
    for recovery in snapshot.recoveries:
        links.append(
            TraceabilityLink(recovery.failure_id, recovery.id, "FAILURE_RECOVERY")
        )

    # Evidence → Knowledge
    for card in snapshot.knowledge_cards:
        for ref in card.evidence_refs:
            links.append(TraceabilityLink(ref, card.id, "EVIDENCE_KNOWLEDGE"))

    coverage = _coverage(snapshot)
    return TraceabilityMatrix(links=tuple(links), coverage=coverage)


def _coverage(snapshot: LearningSnapshot) -> dict[str, str]:
    # A requirement is covered by a change when the change references it directly,
    # or a plan step referencing it is referenced by the change.
    step_requirements: dict[str, set[str]] = {}
    for step in snapshot.plan_steps:
        step_requirements[step.id] = set(step.requirement_refs)

    changes_by_requirement: dict[str, set[str]] = {}
    for change in snapshot.changes:
        covered_requirements: set[str] = set(change.requirement_refs)
        for step_id in change.plan_step_refs:
            covered_requirements |= step_requirements.get(step_id, set())
        for requirement_id in covered_requirements:
            changes_by_requirement.setdefault(requirement_id, set()).add(change.id)

    passing_tests_by_requirement: dict[str, set[str]] = {}
    for attempt in snapshot.test_attempts:
        if attempt.status != "passed":
            continue
        covered_requirements = set(attempt.requirement_refs)
        for change_id in attempt.tested_change_ids:
            for requirement_id, change_ids in changes_by_requirement.items():
                if change_id in change_ids:
                    covered_requirements.add(requirement_id)
        for requirement_id in covered_requirements:
            passing_tests_by_requirement.setdefault(requirement_id, set()).add(
                attempt.id
            )

    coverage: dict[str, str] = {}
    for requirement in snapshot.requirements:
        has_change = requirement.id in changes_by_requirement
        has_passing_test = requirement.id in passing_tests_by_requirement
        if has_change and has_passing_test:
            coverage[requirement.id] = "covered"
        elif has_change or has_passing_test:
            coverage[requirement.id] = "partial"
        else:
            coverage[requirement.id] = "not_covered"
    return coverage


__all__ = ["TraceabilityMatrix", "build_traceability"]
