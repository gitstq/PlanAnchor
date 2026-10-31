"""Report rendering and CLI end-to-end tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from plananchor import cli as cli_mod
from plananchor.parser import parse_text
from plananchor.report import FORMATS, collect, emit
from plananchor.validate import validate_plan

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE = """# Demo

## Phase 1

- [x] 1.1 done `@a.py`
- [~] 1.2 active `@b.py`
- [ ] 1.3 pending `@c.py`
"""

SAMPLE_BAD = "- [x] 1 closed with no ref\n- [x] 1 duplicate\n"


class ReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = parse_text(SAMPLE, path="PLAN.md")
        self.findings = validate_plan(self.plan, check_refs=False)

    def test_all_formats_render(self):
        for fmt in FORMATS:
            text = emit(fmt, self.plan, self.findings)
            self.assertTrue(text.strip(), "format %s produced empty output" % fmt)

    def test_json_is_parseable(self):
        payload = json.loads(emit("json", self.plan, self.findings))
        self.assertEqual(payload["tool"], "PlanAnchor")
        self.assertIn("summary", payload)

    def test_sarif_shape(self):
        sarif = json.loads(emit("sarif", self.plan, self.findings))
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertIn("runs", sarif)
        self.assertIn("results", sarif["runs"][0])

    def test_sarif_levels_are_valid(self):
        sarif = json.loads(emit("sarif", self.plan, self.findings))
        allowed = {"note", "warning", "error", "none"}
        for result in sarif["runs"][0]["results"]:
            self.assertIn(result["level"], allowed)

    def test_junit_is_well_formed(self):
        import xml.etree.ElementTree as ET

        xml = emit("junit", self.plan, self.findings)
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "testsuites")
        self.assertTrue(root.find("testsuite") is not None)

    def test_markdown_has_tables(self):
        md = emit("md", self.plan, self.findings)
        self.assertIn("| Severity | Rule | Message | Line |", md)

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            emit("yaml", self.plan, self.findings)

    def test_collect_marks_ok_without_errors(self):
        payload = collect(parse_text("- [x] 1 a `@a.py`\n"), [])
        self.assertTrue(payload["ok"])

    def test_collect_marks_not_ok_with_errors(self):
        findings = validate_plan(parse_text(SAMPLE_BAD), check_refs=False)
        payload = collect(parse_text(SAMPLE_BAD), findings)
        self.assertFalse(payload["ok"])
        self.assertGreater(payload["summary"]["error"], 0)

    def test_text_report_contains_progress(self):
        text = emit("text", self.plan, self.findings)
        self.assertIn("progress", text)


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.plan_path = os.path.join(self.tmp, "PLAN.md")
        with open(self.plan_path, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, argv):
        return cli_mod.main(argv)

    def test_rules_command(self):
        self.assertEqual(self._run(["rules"]), 0)

    def test_parse_stats(self):
        self.assertEqual(self._run(["parse", self.plan_path, "--stats"]), 0)

    def test_parse_json(self):
        self.assertEqual(self._run(["parse", self.plan_path, "--json"]), 0)

    def test_check_clean_plan(self):
        with open(self.plan_path, "w", encoding="utf-8") as fh:
            fh.write("- [x] 1 a `@a.py`\n")
        self.assertEqual(self._run(["check", self.plan_path, "--no-refs"]), 0)

    def test_check_returns_one_on_errors(self):
        bad = os.path.join(self.tmp, "BAD.md")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write(SAMPLE_BAD)
        self.assertEqual(self._run(["check", bad, "--no-refs"]), 1)

    def test_fail_on_warning_lowers_the_bar(self):
        warn = os.path.join(self.tmp, "WARN.md")
        with open(warn, "w", encoding="utf-8") as fh:
            fh.write("- [x] 1 no ref here\n")
        self.assertEqual(self._run(["check", warn, "--no-refs", "--fail-on", "warning"]), 1)

    def test_missing_plan_returns_three(self):
        self.assertEqual(self._run(["check", os.path.join(self.tmp, "nope.md")]), 3)

    def test_snapshot_and_verify(self):
        self.assertEqual(self._run(["snapshot", self.plan_path]), 0)
        self.assertEqual(self._run(["verify", self.plan_path]), 0)
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, ".plananchor", "snapshots"))), 1)

    def test_verify_without_store_returns_three(self):
        self.assertEqual(self._run(["verify", self.plan_path]), 3)

    def test_restore_without_store_returns_three(self):
        self.assertEqual(self._run(["restore", self.plan_path]), 3)

    def test_resume_writes_briefing(self):
        out = os.path.join(self.tmp, "RESUME.md")
        self.assertEqual(self._run(["resume", self.plan_path, "-o", out]), 0)
        self.assertTrue(os.path.isfile(out))
        with open(out, encoding="utf-8") as fh:
            self.assertIn("PlanAnchor", fh.read())

    def test_resume_english(self):
        self.assertEqual(self._run(["resume", self.plan_path, "--lang", "en"]), 0)

    def test_init_scaffolds(self):
        target = os.path.join(self.tmp, "NEW.md")
        self.assertEqual(self._run(["init", target]), 0)
        self.assertTrue(os.path.isfile(target))

    def test_init_refuses_to_overwrite(self):
        target = os.path.join(self.tmp, "NEW.md")
        self._run(["init", target])
        self.assertEqual(self._run(["init", target]), 3)

    def test_status_command(self):
        self.assertEqual(self._run(["status", self.plan_path, "--no-git"]), 0)

    def test_drift_command_outside_repo(self):
        self.assertEqual(self._run(["drift", self.plan_path]), 0)

    def test_no_command_prints_help(self):
        self.assertEqual(self._run([]), 2)

    def test_report_to_file(self):
        out = os.path.join(self.tmp, "report.json")
        self.assertEqual(self._run(["check", self.plan_path, "--no-refs", "-f", "json", "-o", out]), 0)
        with open(out, encoding="utf-8") as fh:
            json.load(fh)


class ModuleEntryTest(unittest.TestCase):
    def test_python_dash_m_works(self):
        proc = subprocess.run(
            [sys.executable, "-m", "plananchor", "rules"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.assertIn(b"PA001", proc.stdout)

    def test_version_flag(self):
        proc = subprocess.run(
            [sys.executable, "-m", "plananchor", "--version"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn(b"PlanAnchor", proc.stdout)


if __name__ == "__main__":
    unittest.main()
