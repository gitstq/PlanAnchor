"""Stall detection and resume-briefing tests."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from plananchor.anchor import AnchorStore
from plananchor.parser import parse_text
from plananchor.resume import build_resume, render_brief
from plananchor.stall import detect_stalls


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class StallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.plan_path = os.path.join(self.tmp, "PLAN.md")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _store(self) -> AnchorStore:
        return AnchorStore(self.plan_path)

    def test_st001_stuck_active(self):
        text = "- [~] 1 working `@a.py`\n- [ ] 2 next `@b.py`\n"
        write(self.plan_path, text)
        store = self._store()
        for _ in range(3):
            store.create(parse_text(text, path=self.plan_path))
        report = detect_stalls(parse_text(text, path=self.plan_path), store)
        self.assertIn("ST001", [i.rule for i in report.items])
        self.assertIn("1", report.stuck_tasks)

    def test_st001_not_raised_below_threshold(self):
        text = "- [~] 1 working `@a.py`\n"
        write(self.plan_path, text)
        store = self._store()
        store.create(parse_text(text, path=self.plan_path))
        report = detect_stalls(parse_text(text, path=self.plan_path), store, stuck_threshold=3)
        self.assertNotIn("ST001", [i.rule for i in report.items])

    def test_st002_churn(self):
        store = self._store()
        for status in ["done", "pending", "done", "pending", "done"]:
            text = "- [%s] 1 flapping `@a.py`\n" % ("x" if status == "done" else " ")
            write(self.plan_path, text)
            store.create(parse_text(text, path=self.plan_path))
        report = detect_stalls(parse_text(text, path=self.plan_path), store)
        self.assertIn("ST002", [i.rule for i in report.items])

    def test_st003_blocked_cascade(self):
        text = "- [!] 1 blocked (blocked: no token)\n  - [ ] 1.1 downstream `@a.py`\n"
        report = detect_stalls(parse_text(text))
        self.assertIn("ST003", [i.rule for i in report.items])

    def test_st004_no_movement(self):
        text = "- [ ] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n"
        write(self.plan_path, text)
        store = self._store()
        for _ in range(3):
            store.create(parse_text(text, path=self.plan_path))
        report = detect_stalls(parse_text(text, path=self.plan_path), store)
        self.assertIn("ST004", [i.rule for i in report.items])

    def test_st005_abandoned_front(self):
        text = "- [ ] 1 untouched `@a.py`\n- [x] 2 done `@b.py`\n"
        report = detect_stalls(parse_text(text))
        self.assertIn("ST005", [i.rule for i in report.items])

    def test_st006_no_active_anchor(self):
        text = "- [ ] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n- [ ] 3 c `@c.py`\n"
        report = detect_stalls(parse_text(text))
        self.assertIn("ST006", [i.rule for i in report.items])

    def test_st006_not_raised_when_active_exists(self):
        text = "- [~] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n- [ ] 3 c `@c.py`\n"
        report = detect_stalls(parse_text(text))
        self.assertNotIn("ST006", [i.rule for i in report.items])

    def test_clean_plan_produces_no_stalls(self):
        text = "- [~] 1 active `@a.py`\n- [x] 2 done `@b.py`\n"
        report = detect_stalls(parse_text(text))
        self.assertTrue(report.clean)

    def test_progress_curve_recorded(self):
        text = "- [ ] 1 a `@a.py`\n"
        write(self.plan_path, text)
        store = self._store()
        store.create(parse_text(text, path=self.plan_path))
        write(self.plan_path, "- [x] 1 a `@a.py`\n")
        store.create(parse_text("- [x] 1 a `@a.py`\n", path=self.plan_path))
        report = detect_stalls(parse_text("- [x] 1 a `@a.py`\n", path=self.plan_path), store)
        self.assertEqual(report.progress_curve, [0.0, 100.0])


class ResumeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.plan_path = os.path.join(self.tmp, "PLAN.md")
        write(
            self.plan_path,
            "# Refactor\n\n## Phase 1\n\n"
            "- [x] 1.1 done `@a.py`\n"
            "- [~] 1.2 in flight `@b.py` #beta\n"
            "- [ ] 1.3 next `@c.py`\n"
            "- [ ] 1.4 later `@d.py`\n"
            "- [!] 1.5 blocked (blocked: waiting on CI)\n",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan(self):
        from plananchor.parser import parse_file

        return parse_file(self.plan_path)

    def test_brief_identifies_current_task(self):
        brief = build_resume(self._plan())
        self.assertEqual([t.uid for t in brief.current], ["1.2"])

    def test_brief_lists_next_tasks_in_order(self):
        brief = build_resume(self._plan(), next_count=2)
        self.assertEqual([t.uid for t in brief.next_tasks], ["1.3", "1.4"])

    def test_brief_lists_blockers(self):
        brief = build_resume(self._plan())
        self.assertEqual([t.uid for t in brief.blocked], ["1.5"])

    def test_brief_collects_key_files(self):
        brief = build_resume(self._plan())
        self.assertIn("b.py", brief.files)
        self.assertIn("c.py", brief.files)

    def test_brief_progress(self):
        brief = build_resume(self._plan())
        self.assertAlmostEqual(brief.progress, 20.0, places=3)

    def test_render_zh_contains_prompt(self):
        brief = build_resume(self._plan(), lang="zh")
        text = render_brief(brief)
        self.assertIn("会话恢复简报", text)
        self.assertIn("```text", text)
        self.assertIn("1.2", text)

    def test_render_en(self):
        brief = build_resume(self._plan(), lang="en")
        text = render_brief(brief)
        self.assertIn("Session Resume Briefing", text)
        self.assertIn("Resume the next task", text)

    def test_render_without_prompt(self):
        brief = build_resume(self._plan())
        text = render_brief(brief, with_prompt=False)
        self.assertNotIn("```text", text)

    def test_unknown_lang_falls_back_to_zh(self):
        brief = build_resume(self._plan(), lang="klingon")
        self.assertEqual(brief.lang, "zh")

    def test_serialisable(self):
        payload = build_resume(self._plan()).to_dict()
        self.assertIn("next", payload)
        self.assertIn("blocked", payload)
        self.assertIn("progress", payload)

    def test_snapshot_seq_reported(self):
        store = AnchorStore(self.plan_path)
        store.create(self._plan())
        brief = build_resume(self._plan(), store=store)
        self.assertEqual(brief.snapshot_seq, 1)


if __name__ == "__main__":
    unittest.main()
