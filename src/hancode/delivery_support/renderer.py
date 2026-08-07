"""Generated/student region rendering for learning Markdown — S14-R2.4.

Every re-renderable learning artifact (SPEC/PLAN/IMPLEMENTATION/TEST_REPORT/
REVIEW/KNOWLEDGE) is split into a Harness-owned generated region and a
student-owned notes region:

    <!-- hancode:generated:start -->
    ... generated from verified evidence ...
    <!-- hancode:generated:end -->

    ## 我的理解
    ## 我仍然不理解的地方
    ## 教师或同伴反馈

The renderer only ever rewrites the content between the two markers. It never
parses or edits the student region. Any marker ambiguity (missing, duplicated,
nested, or reversed markers) stops the rewrite so student content is never
corrupted. Generated content is secret-scanned before it is written.
"""

from __future__ import annotations

from collections.abc import Sequence

from hancode.tooling.file_tools import redact_text


GENERATED_START = "<!-- hancode:generated:start -->"
GENERATED_END = "<!-- hancode:generated:end -->"

_STUDENT_TEMPLATE = (
    "## 我的理解\n\n"
    "## 我仍然不理解的地方\n\n"
    "## 教师或同伴反馈\n"
)


class GeneratedRegionError(ValueError):
    """Raised when the generated region cannot be rewritten safely."""


def replace_generated_region(existing: str, generated: str) -> str:
    """Return ``existing`` with its generated region replaced by ``generated``.

    When ``existing`` has no markers, the original text is preserved verbatim as
    student notes below a freshly inserted generated block.
    """
    if redact_text(generated) != generated:
        raise GeneratedRegionError(
            "Generated content contains sensitive data and was not written."
        )

    block_core = f"{GENERATED_START}\n{generated}\n{GENERATED_END}"

    start_count = existing.count(GENERATED_START)
    end_count = existing.count(GENERATED_END)

    if start_count == 0 and end_count == 0:
        student = existing if existing.strip() else _STUDENT_TEMPLATE
        student = student.lstrip("\n")
        return f"{block_core}\n\n{student}"

    if start_count != 1 or end_count != 1:
        raise GeneratedRegionError(
            "Generated markers must appear exactly once each."
        )

    start_index = existing.index(GENERATED_START)
    end_index = existing.index(GENERATED_END)
    if end_index < start_index:
        raise GeneratedRegionError("Generated end marker precedes start marker.")

    before = existing[:start_index]
    after = existing[end_index + len(GENERATED_END):].lstrip("\n")
    if after:
        return f"{before}{block_core}\n\n{after}"
    return f"{before}{block_core}\n"


def _cell(value: object) -> str:
    from hancode.delivery_support.result import _cell as _delivery_cell

    return _delivery_cell(str(value))


def build_deliverables_markdown(
    *,
    task_id: str,
    status: str,
    test_status: str,
    build_status: str | None,
    core_covered: int,
    core_total: int,
    run_notes: str,
    test_notes: str,
    submission_files: Sequence[str],
    coverage_rows: Sequence[str],
    learning_links: Sequence[tuple[str, str]],
    known_limits: Sequence[str],
    evidence_digest: str | None,
    diff_digest: str | None,
    checkpoint_id: str | None,
) -> str:
    """Render the S14 design-format project delivery summary index.

    Mirrors the "DELIVERABLES.md" section of the delivery design:
    final status, how to run/test, submission files, coverage summary,
    learning-material links, known limits, and audit information. It stays an
    index and does not repeat the bodies of the other six documents.
    """
    covered_cell = f"{core_covered} / {core_total}" if core_total else "0 / 0"
    run_lines = "\n".join(f"- {_cell(item)}" for item in [run_notes]) or "- 无"
    test_lines = "\n".join(f"- {_cell(item)}" for item in [test_notes]) or "- 无"
    file_lines = "\n".join(f"- `{_cell(item)}`" for item in submission_files) or "- 无"
    coverage_lines = "\n".join(f"- {_cell(item)}" for item in coverage_rows) or "- 无"
    links_lines = "\n".join(
        f"- [{_cell(title)}]({_cell(href)})" for href, title in learning_links
    ) or "- 无"
    limits_lines = "\n".join(f"- {_cell(item)}" for item in known_limits) or "- 无"
    audit_lines = []
    audit_lines.append(f"- Evidence digest：{_cell(evidence_digest or '—')}")
    audit_lines.append(f"- Final diff digest：{_cell(diff_digest or '—')}")
    audit_lines.append(f"- Final checkpoint：{_cell(checkpoint_id or '—')}")
    return (
        "# 项目交付摘要\n\n"
        "## 1. 最终状态\n\n"
        f"- Task：{_cell(status)}\n"
        f"- Task ID：{_cell(task_id)}\n"
        f"- Test：{_cell(test_status)}\n"
        f"- Build：{_cell(build_status or 'none')}\n"
        f"- 核心需求覆盖：{_cell(covered_cell)}\n\n"
        "## 2. 如何运行\n\n"
        f"{run_lines}\n\n"
        "## 3. 如何测试\n\n"
        f"{test_lines}\n\n"
        "## 4. 提交文件\n\n"
        f"{file_lines}\n\n"
        "## 5. 需求覆盖摘要\n\n"
        f"{coverage_lines}\n\n"
        "## 6. 学习资料索引\n\n"
        f"{links_lines}\n\n"
        "## 7. 已知限制\n\n"
        f"{limits_lines}\n\n"
        "## 8. 审计信息\n\n"
        f"{chr(10).join(audit_lines)}\n"
    )


__all__ = [
    "GENERATED_END",
    "GENERATED_START",
    "GeneratedRegionError",
    "build_deliverables_markdown",
    "replace_generated_region",
]
