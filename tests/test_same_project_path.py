"""Evidence-chain regression tests for ``_same_project_path``.

``_record_learning_change`` links a source write back to its plan step by
matching the written path against each plan step's ``planned_paths``. If the
planned path and the actually-written path disagree only by directory prefix
(e.g. plan says ``index.html`` but the file is written to ``src/index.html``),
the link is lost and every core requirement degrades to ``not_covered``.

These tests lock the intended matching semantics: a written path matches a
planned path when one is a ``/``-separated suffix of the other.
"""

from __future__ import annotations

from hancode.runtime.agent_loop import _same_project_path


def test_exact_planned_path_matches() -> None:
    assert _same_project_path("src/index.html", "src/index.html") is True
    assert _same_project_path("index.html", "index.html") is True


def test_plan_path_is_basename_of_written_path() -> None:
    # Plan wrote "index.html", file landed at "src/index.html".
    assert _same_project_path("src/index.html", "index.html") is True


def test_plan_path_is_parent_of_written_path() -> None:
    # Plan wrote "src/index.html", file landed at project root "index.html".
    assert _same_project_path("index.html", "src/index.html") is True


def test_deep_written_path_matches_short_plan_path() -> None:
    assert _same_project_path("src/components/App.js", "App.js") is True


def test_unrelated_paths_do_not_match() -> None:
    assert _same_project_path("src/a.py", "tests/a.py") is False
    assert _same_project_path("src/index.html", "tests/index.html") is False


def test_invalid_planned_path_falls_back_to_plain_compare() -> None:
    # normalize_project_relative_path rejects "./index.html"; the fallback
    # must not accidentally treat it as a match.
    assert _same_project_path("index.html", "./index.html") is False
