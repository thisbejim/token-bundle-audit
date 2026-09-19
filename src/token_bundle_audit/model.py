"""Stable report objects used by the CLI and library API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Finding:
    """One deterministic audit finding."""

    code: str
    severity: str
    message: str
    path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
        }


@dataclass
class AuditReport:
    """The complete result for a bundle directory."""

    root: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "warning"]

    @property
    def infos(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.severity == "info"]

    def ok(self, *, strict: bool = False) -> bool:
        return not self.errors and (not strict or not self.warnings)

    def as_dict(self, *, strict: bool = False) -> dict[str, Any]:
        return {
            "root": self.root,
            "ok": self.ok(strict=strict),
            "strict": strict,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "infos": len(self.infos),
            },
            "findings": [finding.as_dict() for finding in self.findings],
        }
