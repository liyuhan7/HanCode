from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
README = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")


def _section(title: str) -> str:
    start = README.index(title) + len(title)
    next_heading = README.find("\n## ", start)
    return README[start:] if next_heading == -1 else README[start:next_heading]


def test_readme_contains_mock_demo_command() -> None:
    assert "uv run hancode --help" in README
    assert "uv run hancode demo --provider mock" in README
    assert "无需真实凭据" in README


def test_readme_mentions_no_real_credentials() -> None:
    assert "headless CLI" in README
    assert "keyring -> env -> dotenv -> missing" in README
    assert "不得提交真实 API 密钥" in README
    assert "不要把 key 写入 README" in README


def test_readme_documents_known_limitations() -> None:
    assert "## 已知限制" in README
    assert "`hancode run` 已实现 Headless" in README
    assert "REPL/TUI/WebUI 尚未实现" in README
    assert "anthropic" in README
    assert "local" in README
    assert "Docker 不是当前必需分发路径" in README


def test_readme_documents_verification_commands() -> None:
    assert "uv sync --locked --extra dev" in README
    assert "uv build" in README
    assert "uv run hancode --help" in README
    assert "uv run hancode demo --provider mock" in README
    assert "uv run pytest" in README
    assert "uv run ruff check src tests scripts" in README
    assert "uv run mypy src" in README


def test_readme_documents_source_and_wheel_installation() -> None:
    assert "从源码安装" in README
    assert "Python 3.11+" in README
    assert "wheel" in README
    assert "uv tool install dist/hancode-0.1.0-py3-none-any.whl" in README
    assert ".env" in README
    assert "明文风险" in README


def test_readme_documents_auth_commands_and_hidden_input() -> None:
    assert "hancode auth status --provider <provider>" in README
    assert "hancode auth login --provider <provider>" in README
    assert "hancode auth update --provider <provider>" in README
    assert "hancode auth clear --provider <provider>" in README
    assert "隐藏输入" in README


def test_readme_scopes_available_and_installed_commands() -> None:
    available_commands = _section("## 当前可用命令")
    wheel_commands = _section("### wheel 安装后的命令")

    assert "hancode run" in available_commands
    assert "hancode task create" in available_commands
    assert "REPL/TUI/WebUI" not in available_commands
    assert "真实 Provider 执行" not in available_commands
    assert "hancode --help" in wheel_commands
    assert "hancode demo --provider mock" in wheel_commands


def test_readme_contains_no_secret_like_literals() -> None:
    forbidden_patterns = (
        r"\bsk-[A-Za-z0-9]{16,}\b",
        r"\bsk-ant-[A-Za-z0-9_-]{8,}\b",
        r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{16,}\b",
        r"(?i)authorization:\s*bearer\s+\S+",
    )

    for pattern in forbidden_patterns:
        assert re.search(pattern, README) is None
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        assert re.search(rf"{name}\s*=\s*\S+", README) is None


def test_readme_documents_runtime_temp_boundary() -> None:
    assert "TEMP/TMP" in README
    assert "可写" in README
    assert "cli_internal_error" in README


def test_readme_documents_init_and_export_boundaries() -> None:
    assert "`init` 只初始化项目级 `.hancode` 工作区" in README
    assert "`export` 只复制 state 声明的交付物" in README
    assert "不能覆盖已有目录" in README
