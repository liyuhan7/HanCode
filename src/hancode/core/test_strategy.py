"""Immutable evidence binding a task to its executable test strategy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping


@dataclass(frozen=True, slots=True)
class TestCoverageItem:
    __test__ = False

    requirement: str
    verification: str

    def to_dict(self) -> dict[str, str]:
        return {
            "requirement": self.requirement,
            "verification": self.verification,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TestCoverageItem:
        return cls(
            requirement=_required_text(data, "requirement"),
            verification=_required_text(data, "verification"),
        )


@dataclass(frozen=True, slots=True)
class TestFileEvidence:
    __test__ = False

    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TestFileEvidence:
        return cls(
            path=_required_text(data, "path"),
            sha256=_required_text(data, "sha256"),
        )


@dataclass(frozen=True, slots=True)
class TestStrategy:
    __test__ = False

    schema_version: int
    task_id: str
    framework: str
    command: str
    command_argv: tuple[str, ...]
    command_digest: str
    test_files: tuple[TestFileEvidence, ...]
    coverage: tuple[TestCoverageItem, ...]
    created_at: str
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "framework": self.framework,
            "command": self.command,
            "command_argv": list(self.command_argv),
            "command_digest": self.command_digest,
            "test_files": [item.to_dict() for item in self.test_files],
            "coverage": [item.to_dict() for item in self.coverage],
            "created_at": self.created_at,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TestStrategy:
        schema_version = data.get("schema_version")
        command_argv = data.get("command_argv")
        test_files = data.get("test_files")
        coverage = data.get("coverage")
        if schema_version != 1:
            raise ValueError("Unsupported test strategy schema version.")
        if not isinstance(command_argv, list) or not all(
            isinstance(item, str) and item for item in command_argv
        ):
            raise ValueError("Invalid test strategy command argv.")
        if not isinstance(test_files, list) or not test_files:
            raise ValueError("Test strategy must contain test files.")
        if not isinstance(coverage, list) or not coverage:
            raise ValueError("Test strategy must contain coverage evidence.")
        strategy = cls(
            schema_version=1,
            task_id=_required_text(data, "task_id"),
            framework=_required_text(data, "framework"),
            command=_required_text(data, "command"),
            command_argv=tuple(command_argv),
            command_digest=_required_text(data, "command_digest"),
            test_files=tuple(
                TestFileEvidence.from_dict(_mapping(item)) for item in test_files
            ),
            coverage=tuple(
                TestCoverageItem.from_dict(_mapping(item)) for item in coverage
            ),
            created_at=_required_text(data, "created_at"),
            digest=_required_text(data, "digest"),
        )
        if strategy.command_digest != digest_argv(strategy.command_argv):
            raise ValueError("Test strategy command digest does not match.")
        if strategy.digest != digest_strategy(strategy):
            raise ValueError("Test strategy digest does not match.")
        return strategy


def digest_argv(argv: tuple[str, ...]) -> str:
    payload = json.dumps(
        list(argv),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def digest_strategy(strategy: TestStrategy) -> str:
    data = strategy.to_dict()
    data.pop("digest", None)
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _required_text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid test strategy field: {key}.")
    return value


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Invalid test strategy item.")
    return value
