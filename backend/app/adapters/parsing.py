"""Shared result types for source parsers."""

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["warning", "blocking"]


@dataclass(frozen=True)
class ParseIssue:
    code: str
    detail: str
    severity: Severity
    record_key: str | None = None
    field_name: str | None = None


@dataclass
class ParseResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)

    def warn(self, code: str, detail: str, key: str | None = None, fld: str | None = None) -> None:
        self.issues.append(ParseIssue(code, detail, "warning", key, fld))

    def block(self, code: str, detail: str, key: str | None = None, fld: str | None = None) -> None:
        self.issues.append(ParseIssue(code, detail, "blocking", key, fld))

    @property
    def blocking(self) -> list[ParseIssue]:
        return [i for i in self.issues if i.severity == "blocking"]

    @property
    def first_blocking_code(self) -> str | None:
        return self.blocking[0].code if self.blocking else None
