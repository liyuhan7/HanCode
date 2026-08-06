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


__all__ = [
    "GENERATED_END",
    "GENERATED_START",
    "GeneratedRegionError",
    "replace_generated_region",
]
