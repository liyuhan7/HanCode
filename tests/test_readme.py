from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
README = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")


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
    assert "`hancode run` 尚未实现" in README
    assert "REPL/TUI/WebUI 尚未实现" in README
    assert "真实 Provider 执行尚未实现" in README
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
