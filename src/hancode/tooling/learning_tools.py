"""Structured learning tools for the S14 learning contract.

These tools are LLM-exposed structured recording entry points used during the
spec, plan, review, and delivery phases. They feed validated structured
evidence to :class:`LearningService`, which appends authoritative learning
events and renders the generated region of the matching Markdown artifact.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from hancode.core.errors import HanCodeError
from hancode.tooling.registry import ToolResult


def record_requirements(
    project_root: Path,
    task_id: str,
    requirements: object,
    *,
    goal: object = "",
    boundaries: object = (),
    constraints: object = (),
    assumptions: object = (),
) -> ToolResult:
    """Record structured requirement understanding and render SPEC.md."""
    if not isinstance(goal, str):
        return _invalid_learning_input(
            "record_requirements", "goal must be a string."
        )
    parsed_boundaries = _str_list(boundaries, "boundaries")
    parsed_constraints = _str_list(constraints, "constraints")
    parsed_assumptions = _str_list(assumptions, "assumptions")
    if parsed_boundaries is None or parsed_constraints is None or parsed_assumptions is None:
        return _invalid_learning_input(
            "record_requirements", "boundaries/constraints/assumptions must be lists of strings."
        )
    parsed_requirements = _parse_requirements(requirements)
    if parsed_requirements is None:
        return _invalid_learning_input(
            "record_requirements", "Requirement evidence has an invalid shape."
        )
    try:
        from hancode.app.learning_service import LearningService

        LearningService().record_requirements(
            project_root,
            task_id,
            goal=goal,
            requirements=parsed_requirements,
            boundaries=parsed_boundaries,
            constraints=parsed_constraints,
            assumptions=parsed_assumptions,
        )
    except HanCodeError as exc:
        return _invalid_learning_input(
            "record_requirements", exc.structured_error.message
        )
    return ToolResult(
        success=True,
        action_name="record_requirements",
        output={"artifact": "SPEC.md"},
    )


def record_plan(
    project_root: Path,
    task_id: str,
    decisions: object,
    plan_steps: object,
) -> ToolResult:
    parsed_decisions = _parse_decisions(decisions)
    parsed_plan_steps = _parse_plan_steps(plan_steps)
    if parsed_decisions is None or parsed_plan_steps is None:
        return _invalid_learning_input(
            "record_plan", "Plan evidence has an invalid shape."
        )
    try:
        from hancode.app.learning_service import LearningService

        LearningService().record_plan(
            project_root,
            task_id,
            decisions=parsed_decisions,
            plan_steps=parsed_plan_steps,
        )
    except HanCodeError as exc:
        return _invalid_learning_input("record_plan", exc.structured_error.message)
    return ToolResult(
        success=True,
        action_name="record_plan",
        output={"artifact": "PLAN.md"},
    )


def guarded_record_review(
    project_root: Path,
    task_id: str,
    **kwargs: object,
) -> ToolResult:
    """Use S14 review evidence only after structured requirements exist.

    Tasks that have not entered the learning contract retain the legacy review
    tool contract. This keeps historical tasks and old runs on the existing
    delivery pipeline while making the shared tool name produce S14 output for
    newly structured tasks.
    """
    if not _has_learning_evidence(project_root, task_id):
        from hancode.tooling.delivery_tools import record_review

        return record_review(project_root, task_id, **kwargs)
    return _record_s14_review(project_root, task_id, **kwargs)


def guarded_record_knowledge(
    project_root: Path,
    task_id: str,
    **kwargs: object,
) -> ToolResult:
    """Use S14 knowledge cards for tasks with structured requirements."""
    if not _has_learning_evidence(project_root, task_id):
        from hancode.tooling.delivery_tools import record_knowledge

        return record_knowledge(project_root, task_id, **kwargs)
    return _record_s14_knowledge(project_root, task_id, **kwargs)


def _record_s14_review(
    project_root: Path,
    task_id: str,
    **kwargs: object,
) -> ToolResult:
    if "requirements" in kwargs and "requirement_reviews" not in kwargs:
        return _invalid_learning_input(
            "record_review",
            "This task uses the structured learning contract, so record_review "
            "requires requirement_reviews, not legacy requirements. Provide "
            "requirement_reviews=[{requirement_id, change_refs, test_refs, "
            "status, risk}] plus delivery_recommendation, using existing "
            "R-/C-/T- evidence IDs.",
        )
    requirement_reviews = _parse_requirement_reviews(kwargs.get("requirement_reviews"))
    quality_findings = _str_list(kwargs.get("quality_findings", []), "quality_findings")
    untested_risks = _str_list(kwargs.get("untested_risks", []), "untested_risks")
    plan_deviations = _str_list(kwargs.get("plan_deviations", []), "plan_deviations")
    delivery_recommendation = kwargs.get("delivery_recommendation")
    if (
        requirement_reviews is None
        or quality_findings is None
        or untested_risks is None
        or plan_deviations is None
        or not isinstance(delivery_recommendation, str)
        or not delivery_recommendation.strip()
    ):
        return _invalid_learning_input(
            "record_review", "Structured review evidence has an invalid shape."
        )
    try:
        from hancode.app.delivery_service import DeliveryService

        DeliveryService().record_review(
            project_root,
            task_id,
            requirement_reviews=requirement_reviews,
            quality_findings=quality_findings,
            untested_risks=untested_risks,
            plan_deviations=plan_deviations,
            delivery_recommendation=delivery_recommendation,
        )
    except HanCodeError as exc:
        return _invalid_learning_input(
            "record_review",
            exc.structured_error.message,
            error_code=exc.structured_error.error_code,
        )
    return ToolResult(
        success=True,
        action_name="record_review",
        output={"artifact": "REVIEW.md", "format": "structured"},
    )


def _record_s14_knowledge(
    project_root: Path,
    task_id: str,
    **kwargs: object,
) -> ToolResult:
    if "items" in kwargs and "cards" not in kwargs:
        return _invalid_learning_input(
            "record_knowledge",
            "This task uses the structured learning contract, so record_knowledge "
            "requires cards, not legacy items. Provide cards=[{category, "
            "problem, context, principle, solution, evidence_refs, "
            "applicable_when, not_applicable_when, common_mistake, "
            "transfer_example}], where each evidence_refs entry is an existing "
            "R-/D-/P-/C-/T-/F-/REC- evidence ID (for example the passing test "
            "attempt T-000001), never a file path.",
        )
    cards = _parse_knowledge_cards(kwargs.get("cards"))
    if cards is None:
        return _invalid_learning_input(
            "record_knowledge",
            "Knowledge cards have an invalid shape. Provide cards=[{category, "
            "problem, context, principle, solution, evidence_refs, "
            "applicable_when, not_applicable_when, common_mistake, "
            "transfer_example}]; every field must be a non-empty string and "
            "evidence_refs must list existing R-/D-/P-/C-/T-/F-/REC- IDs.",
        )
    try:
        from hancode.app.delivery_service import DeliveryService

        DeliveryService().record_knowledge(
            project_root,
            task_id,
            cards=cards,
        )
    except HanCodeError as exc:
        return _invalid_learning_input(
            "record_knowledge",
            exc.structured_error.message,
            error_code=exc.structured_error.error_code,
        )
    return ToolResult(
        success=True,
        action_name="record_knowledge",
        output={"artifact": "KNOWLEDGE.md", "format": "structured", "count": len(cards)},
    )


def _has_learning_evidence(project_root: Path, task_id: str) -> bool:
    from hancode.app.learning_service import LearningService

    return bool(LearningService().load_snapshot(project_root, task_id).requirements)


def _parse_requirements(requirements: object) -> list[Mapping[str, object]] | None:
    if not isinstance(requirements, list) or not requirements:
        return None
    parsed: list[Mapping[str, object]] = []
    for item in requirements:
        if not isinstance(item, Mapping):
            return None
        source_text = item.get("source_text")
        student_understanding = item.get("student_understanding")
        if not isinstance(source_text, str) or not source_text.strip():
            return None
        if not isinstance(student_understanding, str) or not student_understanding.strip():
            return None
        acceptance_evidence = item.get("acceptance_evidence", "")
        if not isinstance(acceptance_evidence, str) or not acceptance_evidence.strip():
            return None
        priority = item.get("priority", "normal")
        if not isinstance(priority, str):
            return None
        is_core = item.get("is_core", False)
        if not isinstance(is_core, bool):
            return None
        parsed.append(
            {
                "source_text": source_text,
                "student_understanding": student_understanding,
                "acceptance_evidence": acceptance_evidence,
                "priority": priority,
                "is_core": is_core,
            }
        )
    return parsed


def _parse_decisions(decisions: object) -> list[Mapping[str, object]] | None:
    if not isinstance(decisions, list):
        return None
    parsed: list[Mapping[str, object]] = []
    for item in decisions:
        if not isinstance(item, Mapping):
            return None
        chosen_option = item.get("chosen_option")
        rationale = item.get("rationale")
        if not isinstance(chosen_option, str) or not chosen_option.strip():
            return None
        if not isinstance(rationale, str) or not rationale.strip():
            return None
        requirement_refs = _str_list(item.get("requirement_refs", ()), "requirement_refs")
        if requirement_refs is None:
            return None
        rejected = _str_list(item.get("rejected_options", ()), "rejected_options")
        if rejected is None:
            return None
        parsed.append(
            {
                "chosen_option": chosen_option,
                "rationale": rationale,
                "requirement_refs": requirement_refs,
                "rejected_options": rejected,
            }
        )
    return parsed


def _parse_plan_steps(plan_steps: object) -> list[Mapping[str, object]] | None:
    if not isinstance(plan_steps, list) or not plan_steps:
        return None
    parsed: list[Mapping[str, object]] = []
    for item in plan_steps:
        if not isinstance(item, Mapping):
            return None
        description = item.get("description")
        if not isinstance(description, str) or not description.strip():
            return None
        verification = item.get("verification", "")
        if not isinstance(verification, str):
            return None
        requirement_refs = _str_list(item.get("requirement_refs", ()), "requirement_refs")
        if requirement_refs is None:
            return None
        planned_paths = _str_list(item.get("planned_paths", ()), "planned_paths")
        if planned_paths is None:
            return None
        parsed.append(
            {
                "description": description,
                "verification": verification,
                "requirement_refs": requirement_refs,
                "planned_paths": planned_paths,
            }
        )
    return parsed


def _parse_requirement_reviews(
    value: object,
) -> list[Mapping[str, object]] | None:
    if not isinstance(value, list):
        return None
    parsed: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        requirement_id = item.get("requirement_id")
        status = item.get("status")
        change_refs = _str_list(item.get("change_refs", []), "change_refs")
        test_refs = _str_list(item.get("test_refs", []), "test_refs")
        risk = item.get("risk")
        if (
            not isinstance(requirement_id, str)
            or not requirement_id.strip()
            or not isinstance(status, str)
            or not status.strip()
            or change_refs is None
            or test_refs is None
            or (risk is not None and not isinstance(risk, str))
        ):
            return None
        parsed.append(
            {
                "requirement_id": requirement_id,
                "change_refs": change_refs,
                "test_refs": test_refs,
                "status": status,
                "risk": risk,
            }
        )
    return parsed


def _parse_knowledge_cards(value: object) -> list[Mapping[str, object]] | None:
    if not isinstance(value, list) or not value:
        return None
    fields = (
        "category",
        "problem",
        "context",
        "principle",
        "solution",
        "applicable_when",
        "not_applicable_when",
        "common_mistake",
        "transfer_example",
    )
    parsed: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        if any(
            not isinstance(item.get(field), str) or not str(item[field]).strip()
            for field in fields
        ):
            return None
        evidence_refs = _str_list(item.get("evidence_refs", []), "evidence_refs")
        if evidence_refs is None or not evidence_refs:
            return None
        parsed.append(
            {
                field: item[field]
                for field in fields
            }
            | {"evidence_refs": evidence_refs}
        )
    return parsed


def _str_list(value: object, name: str) -> list[str] | None:
    if not isinstance(value, (list, tuple)):
        return None
    if any(not isinstance(item, str) for item in value):
        return None
    return list(value)


def _invalid_learning_input(
    action_name: str, message: str, *, error_code: str = "learning_input_invalid"
) -> ToolResult:
    return ToolResult(
        success=False,
        action_name=action_name,
        error_summary=message,
        error_code=error_code,
    )


__all__ = [
    "guarded_record_knowledge",
    "guarded_record_review",
    "record_plan",
    "record_requirements",
]
