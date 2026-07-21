"""Approval request builder: constructs approval records with previews.

Converts an Action into a canonical ApprovalRecord with bounded diff previews,
target file hashing, and sensitive content detection.

This module does NOT mutate files or create side effects.
"""

from __future__ import annotations

import hashlib
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

from hancode.core.actions import Action
from hancode.core.approvals import (
    ApprovalActionSnapshot,
    ApprovalPreview,
    ApprovalRecord,
    ApprovalStatus,
    ApprovalTarget,
    format_approval_id,
)
from hancode.core.config import HanCodeConfig
from hancode.core.errors import HanCodeError, StructuredError
from hancode.core.state import TaskState
from hancode.policy.approval_policy import ApprovalRequirement


_SENSITIVE_PATTERNS = (
    "api_key",
    "apikey",
    "api-key",
    "secret_key",
    "secretkey",
    "secret-key",
    "password",
    "passwd",
    "token",
    "credential",
    "private_key",
    "privatekey",
    "private-key",
    "authorization",
    "Bearer ",
    "AWS_ACCESS_KEY",
    "AWS_SECRET",
)


def _contains_sensitive_content(text: str) -> bool:
    """Check whether text contains likely credential patterns."""
    lower = text.lower()
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.lower() in lower:
            return True
    return False


def _compute_file_hash(file_path: Path) -> str | None:
    """Compute sha256 hash of a file. Returns None if the file doesn't exist."""
    try:
        if not file_path.is_file():
            return None
        h = hashlib.sha256()
        h.update(file_path.read_bytes())
        return h.hexdigest()
    except (OSError, UnicodeError):
        return None


def _generate_diff(
    old_content: str | None,
    new_content: str,
    old_label: str = "before",
    new_label: str = "proposed",
    max_lines: int = 200,
) -> tuple[str | None, bool]:
    """Generate a unified diff. Returns (diff_text, truncated)."""
    old_lines = (old_content or "").splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_label,
            tofile=new_label,
            lineterm="",
        )
    )

    if not diff_lines:
        return None, False

    truncated = len(diff_lines) > max_lines
    result = "".join(diff_lines[:max_lines])
    if truncated:
        result += "\n... (diff truncated) ..."

    return result, truncated


class ApprovalRequestBuilder:
    """Constructs approval records from actions and task state."""

    def __init__(self, config: HanCodeConfig) -> None:
        self._config = config

    def build(
        self,
        *,
        project_id: str,
        task_id: str,
        state: TaskState,
        action: Action,
        requirement: ApprovalRequirement,
        project_root: Path,
    ) -> ApprovalRecord:
        """Build a complete ApprovalRecord from an action requiring approval.

        Raises HanCodeError if:
        - The action payload is too large
        - The action payload contains sensitive content
        - The category is invalid
        """
        if not requirement.required or requirement.category is None:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_not_required",
                    message="Cannot build approval for an action that does not require it.",
                    phase=state.current_phase.value,
                    denied_rule="approval_requirement_required",
                    suggested_fix="Check the approval requirement before building the record.",
                )
            )

        category = requirement.category
        tool_name = action.tool_name or "unknown"

        # 1. Build canonical action snapshot
        snapshot = ApprovalActionSnapshot.from_action(
            action_type=action.type,
            phase=action.phase,
            tool_name=tool_name,
            args=action.args,
            reason=action.reason or "No reason provided.",
        )

        # 2. Check payload size
        full_payload = json.dumps(
            snapshot.to_dict(), ensure_ascii=False, sort_keys=True
        )
        payload_bytes = len(full_payload.encode("utf-8"))
        if payload_bytes > self._config.max_approval_payload_bytes:
            raise HanCodeError(
                StructuredError(
                    error_code="approval_payload_too_large",
                    message=f"Action payload size ({payload_bytes} bytes) exceeds limit ({self._config.max_approval_payload_bytes} bytes).",
                    phase=state.current_phase.value,
                    denied_rule="approval_payload_limit",
                    suggested_fix="Use a smaller edit or split the work into multiple actions.",
                )
            )

        # 3. Check sensitive content in action args
        args_str = json.dumps(dict(action.args), ensure_ascii=False)
        if _contains_sensitive_content(args_str):
            raise HanCodeError(
                StructuredError(
                    error_code="approval_sensitive_payload_denied",
                    message="The proposed action contains content that looks like credentials.",
                    phase=state.current_phase.value,
                    denied_rule="approval_sensitive_payload",
                    suggested_fix="Remove credentials from the action before requesting approval.",
                )
            )

        # 4. Build targets with file hashes
        targets: list[ApprovalTarget] = []
        for target_path_str in requirement.targets:
            full_path = (project_root / target_path_str).resolve()
            try:
                full_path.relative_to(project_root.resolve())
            except ValueError:
                # Path outside project root - skip
                continue

            exists = full_path.is_file()
            file_hash = _compute_file_hash(full_path) if exists else None
            size = full_path.stat().st_size if exists else None
            targets.append(
                ApprovalTarget(
                    path=target_path_str,
                    exists=exists,
                    before_sha256=file_hash,
                    size_bytes=size,
                )
            )

        # 5. Build preview (diff)
        preview = self._build_preview(action, project_root, requirement)

        # 6. Construct record
        approval_id = format_approval_id(state.approval_seq + 1)

        return ApprovalRecord(
            schema_version=1,
            project_id=project_id,
            task_id=task_id,
            approval_id=approval_id,
            phase=state.current_phase,
            category=category,
            status=ApprovalStatus.PENDING,
            action=snapshot,
            targets=tuple(targets),
            preview=preview,
            checkpoint_seq_at_request=state.checkpoint_seq,
            latest_checkpoint_at_request=state.latest_checkpoint,
            expected_checkpoint_id=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            decided_at=None,
            executed_at=None,
            rejection_reason=None,
            execution_checkpoint_id=None,
        )

    def _build_preview(
        self,
        action: Action,
        project_root: Path,
        requirement: ApprovalRequirement,
    ) -> ApprovalPreview:
        """Build a bounded, redacted diff preview for the user."""
        tool_name = action.tool_name or "unknown"
        max_chars = self._config.max_approval_preview_chars

        if tool_name == "write_file":
            return self._preview_write_file(action, project_root, max_chars)
        elif tool_name == "edit_file":
            return self._preview_edit_file(action, project_root, max_chars)
        elif tool_name == "rollback_last_checkpoint":
            return ApprovalPreview(
                summary="Rollback to the last checkpoint.",
                unified_diff=None,
                truncated=False,
                redacted=False,
            )
        else:
            summary = f"Execute {tool_name} with reason: {action.reason or 'N/A'}"
            return ApprovalPreview(
                summary=summary,
                unified_diff=None,
                truncated=False,
                redacted=False,
            )

    def _preview_write_file(
        self, action: Action, project_root: Path, max_chars: int
    ) -> ApprovalPreview:
        path_value = action.args.get("path")
        content_value = action.args.get("content")
        path_str = str(path_value) if isinstance(path_value, str) else "unknown"
        new_content = str(content_value) if isinstance(content_value, str) else ""

        full_path = project_root / path_str
        old_content: str | None = None
        file_exists = False
        try:
            resolved = full_path.resolve()
            resolved.relative_to(project_root.resolve())
            if resolved.is_file():
                file_exists = True
                try:
                    old_content = resolved.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    old_content = "[binary or unreadable file]"
        except (ValueError, OSError):
            pass

        summary = (
            f"Write file: {path_str} ({'overwrite' if file_exists else 'create new'})"
        )

        diff_text: str | None = None
        truncated = False

        if file_exists and old_content is not None:
            diff_text, truncated = _generate_diff(
                old_content, new_content, old_label=path_str, new_label=f"{path_str} (proposed)"
            )
        else:
            # New file: show first N lines as preview
            lines = new_content.splitlines()
            preview_lines = lines[:50]
            diff_lines = ["--- /dev/null", f"+++ {path_str}", "@@ -0,0 +1,{len(lines)} @@"]
            diff_lines.extend("+" + line for line in preview_lines)
            if len(lines) > 50:
                diff_lines.append("... (content truncated) ...")
                truncated = True
            diff_text = "\n".join(diff_lines)

        # Bounding and redaction
        redacted = False
        if diff_text:
            if _contains_sensitive_content(diff_text):
                diff_text = "[Content redacted: may contain sensitive information.]"
                redacted = True
            elif len(diff_text) > max_chars:
                diff_text = diff_text[:max_chars] + "\n... (preview truncated to limit) ..."
                truncated = True

        return ApprovalPreview(
            summary=summary,
            unified_diff=diff_text,
            truncated=truncated,
            redacted=redacted,
        )

    def _preview_edit_file(
        self, action: Action, project_root: Path, max_chars: int
    ) -> ApprovalPreview:
        path_value = action.args.get("path")
        old_string = action.args.get("old_string")
        new_string = action.args.get("new_string")
        path_str = str(path_value) if isinstance(path_value, str) else "unknown"
        old_str = str(old_string) if isinstance(old_string, str) else ""
        new_str = str(new_string) if isinstance(new_string, str) else ""

        full_path = project_root / path_str
        old_content: str | None = None
        file_exists = False
        try:
            resolved = full_path.resolve()
            resolved.relative_to(project_root.resolve())
            if resolved.is_file():
                file_exists = True
                try:
                    old_content = resolved.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    old_content = "[binary or unreadable file]"
        except (ValueError, OSError):
            pass

        summary = f"Edit file: {path_str}"

        diff_text: str | None = None
        truncated = False
        redacted = False

        if file_exists and old_content is not None and old_str:
            # Simulate applying the edit in memory to generate diff
            proposed = old_content.replace(old_str, new_str, 1)
            if proposed != old_content:
                diff_text, truncated = _generate_diff(
                    old_content, proposed,
                    old_label=path_str,
                    new_label=f"{path_str} (proposed)",
                )
            else:
                diff_text = f"[Old string not found in {path_str}. The edit may be a no-op or target the wrong content.]"
        elif not file_exists:
            diff_text = f"[File {path_str} does not exist. Edit cannot be previewed.]"

        if diff_text:
            if _contains_sensitive_content(diff_text):
                diff_text = "[Content redacted: may contain sensitive information.]"
                redacted = True
            elif len(diff_text) > max_chars:
                diff_text = diff_text[:max_chars] + "\n... (preview truncated to limit) ..."
                truncated = True

        return ApprovalPreview(
            summary=summary,
            unified_diff=diff_text,
            truncated=truncated,
            redacted=redacted,
        )
