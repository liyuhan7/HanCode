"""DeliveryEvidenceStore — atomic persistence for delivery evidence (S4-R5)."""

from __future__ import annotations

import json
from pathlib import Path
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
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise _evidence_error(
                "delivery_evidence_invalid",
                "Cannot read delivery evidence.",
                "Repair or delete evidence.json.",
            )
        return self._from_dict(data)

    def save(self, task_root: Path, evidence: DeliveryEvidence) -> None:
        path = self._evidence_path(task_root)
        path.parent.mkdir(parents=True, exist_ok=True)
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
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            raise _evidence_error(
                "delivery_evidence_invalid",
                "Cannot write delivery evidence.",
                "Verify task workspace write access.",
            ) from exc

    def _from_dict(self, data: dict[str, object]) -> DeliveryEvidence:
        raw_requirements: list[dict[str, object]] = [
            cast(dict[str, object], r)
            for r in cast(list[object], data.get("requirements", []))
            if isinstance(r, dict)
        ]
        raw_knowledge: list[dict[str, object]] = [
            cast(dict[str, object], k)
            for k in cast(list[object], data.get("knowledge_items", []))
            if isinstance(k, dict)
        ]
        raw_risks: list[str] = [
            str(r) for r in cast(list[object], data.get("review_risks", []))
            if isinstance(r, str)
        ]
        return DeliveryEvidence(
            task_id=str(data["task_id"]),
            requirements=tuple(
                RequirementCoverage(
                    requirement_id=str(r["requirement_id"]),
                    status=RequirementStatus(str(r["status"])),
                    evidence=str(r.get("evidence", "")),
                    risk=str(r["risk"]) if isinstance(r.get("risk"), str) else None,
                    is_core=bool(r.get("is_core", False)),
                )
                for r in raw_requirements
            ),
            knowledge_items=tuple(
                KnowledgeItem(
                    category=KnowledgeCategory(str(k["category"])),
                    summary=str(k.get("summary", "")),
                    detail=str(k.get("detail", "")),
                    source_trace_id=str(k["source_trace_id"]) if isinstance(k.get("source_trace_id"), str) else None,
                )
                for k in raw_knowledge
            ),
            review_risks=tuple(raw_risks),
            latest_test_report_sha256=(
                str(data["latest_test_report_sha256"])
                if data.get("latest_test_report_sha256") is not None
                else None
            ),
            latest_diff_sha256=(
                str(data["latest_diff_sha256"])
                if data.get("latest_diff_sha256") is not None
                else None
            ),
            latest_build_status=str(data.get("latest_build_status", "none")),
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
