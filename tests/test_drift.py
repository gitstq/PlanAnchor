"""Drift detection tests against a real throwaway Git repository."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest

from plananchor.drift import detect_drift
from plananchor.parser import parse_text


def run(args, cwd):
    proc = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


@unittest.skipIf(shutil.which("git") is None, "git is not installed")
class DriftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        run(["git", "init", "-q"], self.tmp)
        run(["git", "config", "user.email", "t@example.com"], self.tmp)
        run(["git", "config", "user.name", "test"], self.tmp)
        run(["git", "config", "commit.gpgsign", "false"], self.tmp)
        # Baseline commit
        write(os.path.join(self.tmp, "a.py"), "def alpha():\n    return 1\n")
        write(os.path.join(self.tmp, "b.py"), "def beta():\n    return 2\n")
        run(["git", "add", "."], self.tmp)
        run(["git", "commit", "-q", "-m", "init"], self.tmp)
        self.plan_path = os.path.join(self.tmp, "PLAN.md")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan(self, text: str):
        write(self.plan_path, text)
        return self.tmp

    def _codes(self, report):
        return [i.rule for i in report.items]

    def test_clean_when_done_task_matches_changes(self):
        write(os.path.join(self.tmp, "a.py"), "def alpha():\n    return 99\n")
        self._plan("- [x] 1 change alpha `@a.py` #alpha\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertNotIn("DF001", self._codes(report))

    def test_df001_claimed_done_but_untouched(self):
        self._plan("- [x] 1 change alpha `@a.py`\n")  # a.py unchanged
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertIn("DF001", self._codes(report))

    def test_df002_silent_change(self):
        write(os.path.join(self.tmp, "a.py"), "def alpha():\n    return 99\n")
        self._plan("- [ ] 1 do something else `@b.py`\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertIn("DF002", self._codes(report))
        self.assertIn("a.py", [i.path for i in report.items])

    def test_df003_symbol_missing(self):
        write(os.path.join(self.tmp, "a.py"), "def gamma():\n    return 3\n")
        self._plan("- [x] 1 add alpha `@a.py` #alpha\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertIn("DF003", self._codes(report))

    def test_df003_not_raised_when_symbol_present(self):
        write(os.path.join(self.tmp, "a.py"), "def alpha():\n    return 3\n")
        self._plan("- [x] 1 add alpha `@a.py` #alpha\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertNotIn("DF003", self._codes(report))

    def test_df003_not_raised_when_symbol_already_existed(self):
        # The diff only moves the body, but `alpha` is already in the file.
        write(os.path.join(self.tmp, "a.py"), "def alpha():\n    return 99\n")
        self._plan("- [x] 1 rework alpha `@a.py` #alpha\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertNotIn("DF003", self._codes(report))

    def test_plan_file_is_not_reported_as_a_silent_change(self):
        self._plan("- [ ] 1 pending `@a.py`\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertNotIn("DF002", self._codes(report))

    def test_df006_no_changes_at_all(self):
        self._plan("- [ ] 1 pending work `@a.py`\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertIn("DF006", self._codes(report))

    def test_basename_fallback_resolution(self):
        write(os.path.join(self.tmp, "deep", "nested", "alpha.py"), "x = 1\n")
        self._plan("- [x] 1 touch `@alpha.py`\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertIn("deep/nested/alpha.py", report.claimed)

    def test_ignore_paths(self):
        write(os.path.join(self.tmp, "a.py"), "changed\n")
        self._plan("- [ ] 1 pending `@b.py`\n")
        report = detect_drift(
            parse_text(open(self.plan_path).read(), path=self.plan_path),
            repo=self.tmp,
            ignore_paths=["a.py"],
        )
        self.assertNotIn("DF002", self._codes(report))

    def test_untracked_files_count_as_changes(self):
        write(os.path.join(self.tmp, "new.py"), "x = 1\n")
        self._plan("- [x] 1 add new `@new.py`\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertNotIn("DF001", self._codes(report))
        self.assertIn("new.py", report.changed)

    def test_git_metadata_is_captured(self):
        self._plan("- [ ] 1 a `@a.py`\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        self.assertTrue(report.git_available)
        self.assertTrue(report.head)
        self.assertTrue(report.branch)

    def test_report_serialises(self):
        self._plan("- [ ] 1 a `@a.py`\n")
        report = detect_drift(parse_text(open(self.plan_path).read(), path=self.plan_path), repo=self.tmp)
        payload = report.to_dict()
        self.assertIn("items", payload)
        self.assertIn("changed_files", payload)


class NoGitTest(unittest.TestCase):
    def test_degrades_gracefully_outside_a_repo(self):
        tmp = tempfile.mkdtemp()
        try:
            plan = parse_text("- [ ] 1 a `@a.py`\n", path=os.path.join(tmp, "PLAN.md"))
            report = detect_drift(plan, repo=tmp)
            self.assertFalse(report.git_available)
            self.assertIn("DF000", [i.rule for i in report.items])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
