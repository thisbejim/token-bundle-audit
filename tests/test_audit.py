from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from token_bundle_audit import audit_bundle
from token_bundle_audit.cli import main

ROOT = Path(__file__).parent / "fixtures"


class AuditTests(unittest.TestCase):
    def test_good_bundle_is_clean(self) -> None:
        report = audit_bundle(ROOT / "good")
        self.assertTrue(report.ok())
        self.assertEqual([], report.errors)
        self.assertEqual([], report.warnings)

    def test_bad_bundle_reports_actionable_findings(self) -> None:
        report = audit_bundle(ROOT / "bad")
        codes = {finding.code for finding in report.findings}
        self.assertIn("TB110", codes)
        self.assertIn("TB113", codes)
        self.assertIn("TB104", codes)
        self.assertIn("TB124", codes)
        self.assertIn("TB128", codes)
        self.assertIn("TB107", codes)
        self.assertFalse(report.ok())

    def test_missing_path_is_an_error(self) -> None:
        report = audit_bundle(ROOT / "does-not-exist")
        self.assertEqual({"TB001"}, {finding.code for finding in report.errors})

    def test_invalid_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "config.json").write_text("{", encoding="utf-8")
            report = audit_bundle(path)
            self.assertIn("TB003", {finding.code for finding in report.findings})

    def test_json_cli_is_machine_readable(self) -> None:
        # The CLI output itself is deliberately exercised through its public entrypoint.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            import contextlib
            import io

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(0, main(["check", str(ROOT / "good"), "--format", "json"]))
            output.write_text(stream.getvalue(), encoding="utf-8")
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertIn("findings", payload)

    def test_strict_mode_fails_on_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "config.json").write_text('{"vocab_size": 1}', encoding="utf-8")
            (path / "vocab.json").write_text('{"x": 0}', encoding="utf-8")
            self.assertEqual(1, main(["check", str(path), "--strict", "--format", "json"]))

    def test_strict_json_reports_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "config.json").write_text('{"vocab_size": 1}', encoding="utf-8")
            (path / "vocab.json").write_text('{"x": 0}', encoding="utf-8")
            import contextlib
            import io

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                main(["check", str(path), "--strict", "--format", "json"])
            payload = json.loads(stream.getvalue())
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["strict"])


if __name__ == "__main__":
    unittest.main()
