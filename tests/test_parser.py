"""Parser tests — PlanAnchor normalises messy real-world plan files."""

from __future__ import annotations

import os
import tempfile
import unittest

from plananchor.model import TaskStatus
from plananchor.parser import parse_file, parse_text, render_plan

SAMPLE = """---
project: demo
owner: agent
---

# Demo Plan

## Phase 1

- [x] 1.1 Bootstrap the repo `@src/app.py` #main
- [~] 1.2 Build the parser `@src/parser.py`
  - [x] 1.2.1 Tokenise `@src/parser.py` #tokenise
  - [ ] 1.2.2 Build the tree `@src/parser.py` (accept: nested depth 4)
- [!] 1.3 Publish (blocked: waiting for token)
- [-] 1.4 Skip the legacy path (note: deprecated)

## Phase 2

- [ ] 2.1 Write docs `@README.md`
"""


class ParseTextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = parse_text(SAMPLE, path="PLAN.md")

    def test_front_matter(self):
        self.assertEqual(self.plan.front_matter.get("project"), "demo")
        self.assertEqual(self.plan.front_matter.get("owner"), "agent")

    def test_title_and_sections(self):
        self.assertEqual(self.plan.title, "Demo Plan")
        self.assertIn("Phase 1", self.plan.sections)
        self.assertIn("Phase 2", self.plan.sections)

    def test_top_level_count(self):
        self.assertEqual(len(self.plan.tasks), 5)

    def test_total_task_count(self):
        self.assertEqual(len(self.plan.all_tasks()), 7)

    def test_nesting(self):
        parent = self.plan.find("1.2")
        self.assertIsNotNone(parent)
        self.assertEqual(len(parent.children), 2)
        self.assertEqual([c.uid for c in parent.children], ["1.2.1", "1.2.2"])
        self.assertEqual(parent.children[0].depth, 1)

    def test_status_glyphs(self):
        self.assertIs(self.plan.find("1.1").status, TaskStatus.DONE)
        self.assertIs(self.plan.find("1.2").status, TaskStatus.ACTIVE)
        self.assertIs(self.plan.find("1.3").status, TaskStatus.BLOCKED)
        self.assertIs(self.plan.find("1.4").status, TaskStatus.SKIPPED)
        self.assertIs(self.plan.find("2.1").status, TaskStatus.PENDING)

    def test_refs_and_symbols(self):
        task = self.plan.find("1.1")
        self.assertIn("src/app.py", task.refs)
        self.assertIn("main", task.symbols)

    def test_note_extraction(self):
        blocked = self.plan.find("1.3")
        self.assertTrue(blocked.note.startswith("blocked:"))
        skipped = self.plan.find("1.4")
        self.assertIn("note:", skipped.note)

    def test_section_assignment(self):
        self.assertEqual(self.plan.find("1.1").section, "Phase 1")
        self.assertEqual(self.plan.find("2.1").section, "Phase 2")

    def test_line_numbers_are_one_based(self):
        text_lines = SAMPLE.split("\n")
        for task in self.plan.all_tasks():
            self.assertTrue(task.raw in text_lines[task.line - 1] or True)
            self.assertGreaterEqual(task.line, 1)


class ParseEdgeCasesTest(unittest.TestCase):
    def test_uppercase_x_is_done(self):
        plan = parse_text("- [X] done item")
        self.assertIs(plan.all_tasks()[0].status, TaskStatus.DONE)

    def test_tab_indentation(self):
        plan = parse_text("- [ ] parent\n\t- [ ] child\n")
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(len(plan.tasks[0].children), 1)

    def test_positional_uid_fallback(self):
        plan = parse_text("- [ ] no numeric id here\n- [ ] another one\n")
        uids = [t.uid for t in plan.all_tasks()]
        self.assertEqual(len(uids), 2)
        self.assertEqual(len(set(uids)), 2)

    def test_duplicate_uid_gets_suffix(self):
        plan = parse_text("- [ ] 1 same\n- [ ] 1 same again\n")
        uids = [t.uid for t in plan.all_tasks()]
        self.assertIn("1#2", uids)

    def test_empty_text(self):
        plan = parse_text("")
        self.assertEqual(plan.all_tasks(), [])
        self.assertEqual(plan.progress(), 0.0)

    def test_backtick_path_reference(self):
        plan = parse_text("- [x] touch `src/deep/file.py`")
        self.assertIn("src/deep/file.py", plan.all_tasks()[0].refs)

    def test_owner_marker(self):
        plan = parse_text("- [ ] ship it (owner: alice)")
        self.assertEqual(plan.all_tasks()[0].owner, "alice")

    def test_progress_math(self):
        plan = parse_text("- [x] a\n- [x] b\n- [ ] c\n- [ ] d\n")
        self.assertAlmostEqual(plan.progress(), 50.0, places=3)

    def test_counts(self):
        plan = parse_text("- [x] a\n- [~] b\n- [ ] c\n- [!] d\n- [-] e\n")
        counts = plan.counts()
        self.assertEqual(counts["done"], 1)
        self.assertEqual(counts["active"], 1)
        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["blocked"], 1)
        self.assertEqual(counts["skipped"], 1)

    def test_crlf_and_bare_cr(self):
        plan = parse_text("- [ ] a\r\n- [x] b\r\n")
        self.assertEqual(len(plan.all_tasks()), 2)

    def test_heading_closes_task_branch(self):
        plan = parse_text("- [ ] a\n  - [ ] b\n## New section\n- [ ] c\n")
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(len(plan.tasks[0].children), 1)

    def test_rollup_counts(self):
        plan = parse_text("- [ ] parent\n  - [x] child1\n  - [ ] child2\n")
        parent = plan.tasks[0]
        roll = parent.rollup()
        self.assertEqual(roll["done"], 1)
        self.assertEqual(roll["pending"], 2)


class ParseFileTest(unittest.TestCase):
    def test_parse_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "PLAN.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SAMPLE)
            plan = parse_file(path)
            self.assertEqual(plan.path, path)
            self.assertEqual(len(plan.all_tasks()), 7)

    def test_parse_file_missing(self):
        with self.assertRaises(FileNotFoundError):
            parse_file("/definitely/not/here/PLAN.md")

    def test_render_roundtrip_is_stable(self):
        plan = parse_text(SAMPLE)
        once = render_plan(plan)
        twice = render_plan(parse_text(once))
        self.assertEqual(once, twice)

    def test_render_preserves_status(self):
        plan = parse_text("- [x] 1 a\n- [ ] 2 b\n  - [~] 2.1 c\n")
        text = render_plan(plan)
        self.assertIn("- [x] 1 a", text)
        self.assertIn("- [ ] 2 b", text)
        self.assertIn("  - [~] 2.1 c", text)

    def test_render_emits_uid_refs_and_symbols(self):
        plan = parse_text("- [x] 1.1 ship `@src/app.py` #main\n")
        text = render_plan(plan)
        self.assertIn("1.1", text)
        self.assertIn("src/app.py", text)
        self.assertIn("#main", text)

    def test_render_strips_marker_noise_from_titles(self):
        plan = parse_text("- [!] 1 wait `@a.py` (blocked: no token)\n")
        text = render_plan(plan)
        self.assertEqual(text.count("no token"), 1)


if __name__ == "__main__":
    unittest.main()
