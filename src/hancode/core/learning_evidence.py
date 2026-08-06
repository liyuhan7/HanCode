"""Learning evidence domain models and stable ID validation — S14-R1.2.

These frozen models are the typed shape of the learning evidence that the
append-only learning event store persists and the delivery pipeline consumes.
They deliberately carry no ``Path`` objects: persisted references use POSIX
relative strings so the same JSON round-trips across platforms.

Stable evidence IDs use fixed prefixes and zero-padded sequences:

    R-0001    RequirementEvidence
    D-0001    DecisionEvidence
    P-0001    PlanStepEvidence
    C-0001    ChangeEvidence
    K-0001    KnowledgeCard
    T-000001  TestAttemptEvidence
    F-000001  FailureEvidence
    REC-0001  RecoveryEvidence
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EvidenceKind(str, Enum):
    REQUIREMENT = "requirement"
    DECISION = "decision"
    PLAN_STEP = "plan_step"
    CHANGE = "change"
    KNOWLEDGE = "knowledge"
    TEST_ATTEMPT = "test_attempt"
    FAILURE = "failure"
    RECOVERY = "recovery"


# prefix, zero-padded width
_KIND_SPECS: dict[EvidenceKind, tuple[str, int]] = {
    EvidenceKind.REQUIREMENT: ("R", 4),
    EvidenceKind.DECISION: ("D", 4),
    EvidenceKind.PLAN_STEP: ("P", 4),
    EvidenceKind.CHANGE: ("C", 4),
    EvidenceKind.KNOWLEDGE: ("K", 4),
    EvidenceKind.TEST_ATTEMPT: ("T", 6),
    EvidenceKind.FAILURE: ("F", 6),
    EvidenceKind.RECOVERY: ("REC", 4),
}
_PREFIX_TO_KIND: dict[str, EvidenceKind] = {
    prefix: kind for kind, (prefix, _width) in _KIND_SPECS.items()
}

# Fixed set of allowed traceability relations.
_TRACEABILITY_RELATIONS = frozenset(
    {
        "REQUIREMENT_DECISION",
        "REQUIREMENT_PLAN_STEP",
        "PLAN_STEP_CHANGE",
        "CHANGE_TEST",
        "TEST_FAILURE",
        "FAILURE_RECOVERY",
        "RECOVERY_CHANGE",
        "EVIDENCE_KNOWLEDGE",
    }
)


def format_evidence_id(kind: EvidenceKind, seq: int) -> str:
    """Return the canonical evidence ID for a kind and 1-based sequence."""
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise ValueError("Evidence sequence must be a positive integer.")
    prefix, width = _KIND_SPECS[kind]
    return f"{prefix}-{seq:0{width}d}"


def is_valid_evidence_id(evidence_id: object) -> bool:
    """Return True when the value is a canonical evidence ID."""
    if not isinstance(evidence_id, str):
        return False
    prefix, _dash, suffix = evidence_id.partition("-")
    if not _dash or prefix not in _PREFIX_TO_KIND:
        return False
    _kind_prefix, width = _KIND_SPECS[_PREFIX_TO_KIND[prefix]]
    if len(suffix) != width or not suffix.isdigit():
        return False
    return int(suffix) >= 1


def parse_evidence_kind(evidence_id: str) -> EvidenceKind:
    """Return the EvidenceKind for a canonical ID, or raise ValueError."""
    if not is_valid_evidence_id(evidence_id):
        raise ValueError(f"Invalid evidence ID: {evidence_id!r}.")
    prefix = evidence_id.partition("-")[0]
    return _PREFIX_TO_KIND[prefix]


def _require_id(evidence_id: str, kind: EvidenceKind) -> None:
    if not is_valid_evidence_id(evidence_id) or parse_evidence_kind(evidence_id) is not kind:
        raise ValueError(
            f"Evidence ID {evidence_id!r} is not a valid {kind.value} ID."
        )


def _require_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("Evidence task_id must be a non-empty string.")


@dataclass(frozen=True, slots=True)
class RequirementEvidence:
    id: str
    task_id: str
    source_text: str
    student_understanding: str
    acceptance_evidence: str
    priority: str
    is_core: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.REQUIREMENT)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class DecisionEvidence:
    id: str
    task_id: str
    chosen_option: str
    rejected_options: tuple[str, ...]
    rationale: str
    requirement_refs: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.DECISION)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class PlanStepEvidence:
    id: str
    task_id: str
    description: str
    requirement_refs: tuple[str, ...]
    planned_paths: tuple[str, ...]
    verification: str
    decision_ref: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.PLAN_STEP)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class ChangeEvidence:
    id: str
    task_id: str
    pre_change_checkpoint_id: str | None
    action_id: str
    changed_paths: tuple[str, ...]
    diff_digest: str
    reason: str
    requirement_refs: tuple[str, ...]
    plan_step_refs: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.CHANGE)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class TestAttemptEvidence:
    __test__ = False  # pytest: not a test class

    id: str
    task_id: str
    command: str
    started_at: str
    finished_at: str
    exit_code: int
    status: str
    passed_count: int
    failed_count: int
    failure_category: str | None
    summary: str
    output_digest: str
    tested_change_ids: tuple[str, ...]
    requirement_refs: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.TEST_ATTEMPT)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class FailureEvidence:
    id: str
    task_id: str
    test_attempt_id: str
    failure_digest: str
    category: str
    summary: str
    failing_tests: tuple[str, ...]
    affected_paths: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.FAILURE)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class RecoveryEvidence:
    id: str
    task_id: str
    failure_id: str
    decision: str
    planned_paths: tuple[str, ...]
    reason: str
    rollback_required: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.RECOVERY)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class KnowledgeCard:
    id: str
    task_id: str
    category: str
    problem: str
    context: str
    principle: str
    solution: str
    evidence_refs: tuple[str, ...]
    applicable_when: str
    not_applicable_when: str
    common_mistake: str
    transfer_example: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_id(self.id, EvidenceKind.KNOWLEDGE)
        _require_task_id(self.task_id)


@dataclass(frozen=True, slots=True)
class TraceabilityLink:
    source_id: str
    target_id: str
    relation: str

    def __post_init__(self) -> None:
        if self.relation not in _TRACEABILITY_RELATIONS:
            raise ValueError(f"Unknown traceability relation: {self.relation!r}.")


@dataclass(frozen=True, slots=True)
class LearningSnapshot:
    """Derived current view of validated learning evidence for one task."""

    task_id: str
    requirements: tuple[RequirementEvidence, ...] = ()
    decisions: tuple[DecisionEvidence, ...] = ()
    plan_steps: tuple[PlanStepEvidence, ...] = ()
    changes: tuple[ChangeEvidence, ...] = ()
    test_attempts: tuple[TestAttemptEvidence, ...] = ()
    failures: tuple[FailureEvidence, ...] = ()
    recoveries: tuple[RecoveryEvidence, ...] = ()
    knowledge_cards: tuple[KnowledgeCard, ...] = ()
    links: tuple[TraceabilityLink, ...] = ()
    source_event_seq: int = 0
    digest: str | None = None


__all__ = [
    "ChangeEvidence",
    "DecisionEvidence",
    "EvidenceKind",
    "FailureEvidence",
    "KnowledgeCard",
    "LearningSnapshot",
    "PlanStepEvidence",
    "RecoveryEvidence",
    "RequirementEvidence",
    "TestAttemptEvidence",
    "TraceabilityLink",
    "format_evidence_id",
    "is_valid_evidence_id",
    "parse_evidence_kind",
]
