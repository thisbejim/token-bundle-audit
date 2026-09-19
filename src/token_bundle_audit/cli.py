"""Command-line interface for token-bundle-audit."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .audit import audit_bundle
from .model import AuditReport


def _text(report: AuditReport) -> str:
    lines = [f"token-bundle-audit: {report.root}"]
    for finding in report.findings:
        location = f" [{finding.path}]" if finding.path else ""
        lines.append(f"{finding.severity.upper():7} {finding.code}{location} {finding.message}")
    lines.append(
        f"Summary: {len(report.errors)} error(s), {len(report.warnings)} warning(s), {len(report.infos)} info(s)"
    )
    return "\n".join(lines)


def _sarif(report: AuditReport) -> dict[str, Any]:
    rules: dict[str, dict[str, str]] = {}
    results = []
    for finding in report.findings:
        rules.setdefault(finding.code, {"id": finding.code, "name": finding.code})
        level = "error" if finding.severity == "error" else "warning" if finding.severity == "warning" else "note"
        result: dict[str, Any] = {
            "ruleId": finding.code,
            "level": level,
            "message": {"text": finding.message},
        }
        if finding.path:
            result["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": finding.path}}}]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "token-bundle-audit", "version": __version__, "rules": list(rules.values())}}, "results": results}],
    }


def _exit_code(report: AuditReport, strict: bool) -> int:
    return 0 if report.ok(strict=strict) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="token-bundle-audit", description="Audit a local tokenizer/chat bundle before loading it")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="audit a local bundle directory")
    check.add_argument("bundle", help="path to a Hugging Face-style model directory")
    check.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    check.add_argument("--strict", action="store_true", help="treat warnings as CI failures")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "check":
        return 2
    report = audit_bundle(args.bundle)
    if args.format == "json":
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    elif args.format == "sarif":
        print(json.dumps(_sarif(report), indent=2, sort_keys=True))
    else:
        print(_text(report))
    return _exit_code(report, args.strict)


if __name__ == "__main__":
    sys.exit(main())
