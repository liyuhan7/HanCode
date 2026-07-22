"""DeliveryEvidenceStore — atomic persistence for delivery evidence (S4-R5)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import mkstemp
from typing import cast

from hancode.core.delivery_evidence import (
    DeliveryEvidence,
    KnowledgeCategory,
    KnowledgeItem,
    RequirementCoverage,
    RequirementStatus,
)
from hancode.core.errors import HanCodeError, StructuredError


class DeliveryEvidenceStore:
    """Persist and load DeliveryEvidence in .hancode/tasks/<id>/delivery/evidence.json."""

    def _evidence_path(self, task_root: Path) -> Path:
        return task_root / "delivery" / "evidence.json"

    def load(self, task_root: Path) -> DeliveryEvidence | None:
        path = self._evidence_path(task_root)
        if not path.is_file():
            return None
        if _is_link(path):
            raise _evidence_error(
                "delivery_evidence_invalid",
                "Delivery evidence path must not be a link.",
                "Replace evidence.json with a regular file.",
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            return self._from_dict(data, task_root.name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            raise _evidence_error(
                "delivery_evidence_invalid",
                "Cannot read delivery evidence.",
                "Repair or delete evidence.json.",
            )

    def save(self, task_root: Path, evidence: DeliveryEvidence) -> None:
        path = self._evidence_path(task_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        if _is_link(path):
            raise _evidence_error(
                "delivery_evidence_invalid",
                "Delivery evidence path must not be a link.",
                "Replace evidence.json with a regular file.",
            )
        data = {
            "schema_version": 1,
            "task_id": evidence.task_id,
            "requirements": [
                {
                    "requirement_id": r.requirement_id,
                    "status": r.status.value,
                    "evidence": r.evidence,
                    "risk": r.risk,
                    "is_core": r.is_core,
                }
                for r in evidence.requirements
            ],
            "review_risks": list(evidence.review_risks),
            "knowledge_items": [
                {
                    "category": k.category.value,
                    "summary": k.summary,
                    "detail": k.detail,
                    "source_trace_id": k.source_trace_id,
                }
                for k in evidence.knowledge_items
            ],
            "latest_test_report_sha256": evidence.latest_test_report_sha256,
            "latest_diff_sha256": evidence.latest_diff_sha256,
            "latest_build_status": evidence.latest_build_status,
        }
        temporary_path: Path | None = None
        descriptor: int | None = None
        try:
            descriptor, temporary_name = mkstemp(
                prefix=".evidence-", suffix=".tmp", dir=path.parent
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                descriptor = None
                handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        except (OSError, TypeError, UnicodeError) as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise _evidence_error(
                "delivery_evidence_invalid",
                "Cannot write delivery evidence.",
                "Verify task workspace write access.",
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _from_dict(self, data: dict[str, object], expected_task_id: str) -> DeliveryEvidence:
        expected_fields = {
            "schema_version",
            "task_id",
            "requirements",
            "review_risks",
            "knowledge_items",
            "latest_test_report_sha256",
            "latest_diff_sha256",
            "latest_build_status",
        }
        if set(data) != expected_fields or data.get("schema_version") != 1:
            raise ValueError
        task_id = data.get("task_id")
        if not isinstance(task_id, str) or task_id != expected_task_id:
            raise ValueError
        raw_requirements = data.get("requirements")
        raw_knowledge = data.get("knowledge_items")
        raw_risks = data.get("review_risks")
        if not isinstance(raw_requirements, list) or not isinstance(raw_knowledge, list):
            raise ValueError
        if not isinstance(raw_risks, list) or any(not isinstance(r, str) for r in raw_risks):
            raise ValueError

        requirements: list[RequirementCoverage] = []
        for raw in raw_requirements:
            if not isinstance(raw, dict) or set(raw) != {
                "requirement_id", "status", "evidence", "risk", "is_core"
            }:
                raise ValueError
            requirement_id = raw.get("requirement_id")
            status = raw.get("status")
            evidence = raw.get("evidence")
            risk = raw.get("risk")
            is_core = raw.get("is_core")
            if (
                not isinstance(requirement_id, str)
                or not isinstance(status, str)
                or not isinstance(evidence, str)
                or (risk is not None and not isinstance(risk, str))
                or not isinstance(is_core, bool)
            ):
                raise ValueError
            requirements.append(
                RequirementCoverage(
                    requirement_id=requirement_id,
                    status=RequirementStatus(status),
                    evidence=evidence,
                    risk=risk,
                    is_core=is_core,
                )
            )

        knowledge_items: list[KnowledgeItem] = []
        for raw in raw_knowledge:
            if not isinstance(raw, dict) or set(raw) != {
                "category", "summary", "detail", "source_trace_id"
            }:
                raise ValueError
            category = raw.get("category")
            summary = raw.get("summary")
            detail = raw.get("detail")
            source_trace_id = raw.get("source_trace_id")
            if (
                not isinstance(category, str)
                or not isinstance(summary, str)
                or not isinstance(detail, str)
                or (source_trace_id is not None and not isinstance(source_trace_id, str))
            ):
                raise ValueError
            knowledge_items.append(
                KnowledgeItem(
                    category=KnowledgeCategory(category),
                    summary=summary,
                    detail=detail,
                    source_trace_id=source_trace_id,
                )
            )

        latest_test = data.get("latest_test_report_sha256")
        latest_diff = data.get("latest_diff_sha256")
        build_status = data.get("latest_build_status")
        if (
            not _is_optional_sha256(latest_test)
            or not _is_optional_sha256(latest_diff)
            or build_status not in {"none", "passed", "failed", "timed_out"}
        ):
            raise ValueError
        return DeliveryEvidence(
            task_id=task_id,
            requirements=tuple(requirements),
            knowledge_items=tuple(knowledge_items),
            review_risks=tuple(raw_risks),
            latest_test_report_sha256=cast(str | None, latest_test),
            latest_diff_sha256=cast(str | None, latest_diff),
            latest_build_status=build_status,
        )


def _evidence_error(error_code: str, message: str, suggested_fix: str) -> HanCodeError:
    return HanCodeError(
        StructuredError(
            error_code=error_code,
            message=message,
            phase="deliver",
            denied_rule=error_code,
            suggested_fix=suggested_fix,
        )
    )


def _is_optional_sha256(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _is_link(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(is_junction and is_junction())
    except (AttributeError, OSError, RuntimeError):
        return True
