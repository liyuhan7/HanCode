from __future__ import annotations

import pytest

from hancode.delivery_support.renderer import (
    GENERATED_END,
    GENERATED_START,
    GeneratedRegionError,
    replace_generated_region,
)


def test_insert_into_document_without_markers_preserves_student_notes() -> None:
    existing = "## 我的理解\n\n这是我写的内容。\n"
    generated = "由证据生成的正文"

    result = replace_generated_region(existing, generated)

    assert GENERATED_START in result
    assert GENERATED_END in result
    assert "由证据生成的正文" in result
    # student content preserved verbatim after the generated block
    assert "这是我写的内容。" in result
    assert result.index(GENERATED_END) < result.index("这是我写的内容。")


def test_replace_only_between_existing_markers() -> None:
    existing = (
        f"{GENERATED_START}\nOLD GENERATED\n{GENERATED_END}\n\n"
        "## 我的理解\n\n学生笔记保留。\n"
    )
    generated = "NEW GENERATED"

    result = replace_generated_region(existing, generated)

    assert "OLD GENERATED" not in result
    assert "NEW GENERATED" in result
    assert "学生笔记保留。" in result


def test_replace_is_idempotent() -> None:
    existing = "## 我的理解\n\n笔记\n"
    once = replace_generated_region(existing, "G1")
    twice = replace_generated_region(once, "G1")
    assert once == twice


@pytest.mark.parametrize(
    "existing",
    [
        f"{GENERATED_START}\na\n{GENERATED_START}\nb\n{GENERATED_END}\n",
        f"{GENERATED_END}\nx\n{GENERATED_START}\n",
        f"{GENERATED_START}\nonly start\n",
        f"only end\n{GENERATED_END}\n",
        f"{GENERATED_START}\na\n{GENERATED_END}\n{GENERATED_END}\n",
    ],
)
def test_malformed_generated_markers_fail_closed(existing: str) -> None:
    with pytest.raises(GeneratedRegionError):
        replace_generated_region(existing, "new")


def test_generated_content_with_secret_is_rejected() -> None:
    with pytest.raises(GeneratedRegionError):
        replace_generated_region(
            "## 我的理解\n\n笔记\n",
            'api_key = "sk-1234567890abcdef1234"',
        )
