"""Validation rule tests."""

from __future__ import annotations

import os
import tempfile
import unittest

from plananchor.parser import parse_text
from plananchor.validate import rules_catalog, validate_plan


def codes(findings):
    return [f.rule for f in findings]


class RuleTest(unittest.TestCase):
    def test_pa001_empty_plan(self):
        findings = validate_plan(parse_text(""), check_refs=False)
        self.assertIn("PA001", codes(findings))

    def test_pa002_duplicate_uid(self):
        findings = validate_plan(parse_text("- [ ] 1 a\n- [ ] 1 b\n"), check_refs=False)
        self.assertIn("PA002", codes(findings))

    def test_pa003_closed_without_reference(self):
        findings = validate_plan(parse_text("- [x] did something\n"), check_refs=False)
        self.assertIn("PA003", codes(findings))

    def test_pa003_not_raised_when_ref_present(self):
        findings = validate_plan(parse_text("- [x] did something `@a.py`\n"), check_refs=False)
        self.assertNotIn("PA003", codes(findings))

    def test_pa004_blocked_without_note(self):
        findings = validate_plan(parse_text("- [!] stuck\n"), check_refs=False)
        self.assertIn("PA004", codes(findings))

    def test_pa004_not_raised_with_note(self):
        findings = validate_plan(parse_text("- [!] stuck (blocked: no token)\n"), check_refs=False)
        self.assertNotIn("PA004", codes(findings))

    def test_pa005_multiple_active(self):
        findings = validate_plan(parse_text("- [~] a\n- [~] b\n"), check_refs=False)
        self.assertIn("PA005", codes(findings))

    def test_pa006_parent_closed_children_open(self):
        text = "- [x] parent\n  - [ ] child\n"
        findings = validate_plan(parse_text(text), check_refs=False)
        self.assertIn("PA006", codes(findings))

    def test_pa006_not_raised_when_consistent(self):
        text = "- [x] parent\n  - [x] child\n"
        findings = validate_plan(parse_text(text), check_refs=False)
        self.assertNotIn("PA006", codes(findings))

    def test_pa008_missing_section(self):
        text = "\n".join("- [ ] task %d" % i for i in range(8))
        findings = validate_plan(parse_text(text), check_refs=False)
        self.assertIn("PA008", codes(findings))

    def test_pa009_untitled(self):
        findings = validate_plan(parse_text("- [ ] \n"), check_refs=False)
        self.assertIn("PA009", codes(findings))

    def test_pa010_deep_nesting(self):
        text = ""
        for depth in range(6):
            text += " " * (depth * 2) + "- [ ] level %d\n" % depth
        findings = validate_plan(parse_text(text), check_refs=False, max_depth=3)
        self.assertIn("PA010", codes(findings))

    def test_pa011_dangling_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = validate_plan(
                parse_text("- [x] touch `@nope/missing.py`\n"), repo_root=tmp
            )
            self.assertIn("PA011", codes(findings))

    def test_pa011_not_raised_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "exists.py"), "w", encoding="utf-8") as fh:
                fh.write("x = 1\n")
            findings = validate_plan(
                parse_text("- [x] touch `@exists.py`\n"), repo_root=tmp
            )
            self.assertNotIn("PA011", codes(findings))

    def test_pa012_no_acceptance_marker(self):
        findings = validate_plan(parse_text("- [ ] do the thing\n"), check_refs=False)
        self.assertIn("PA012", codes(findings))

    def test_pa012_suppressed_by_acceptance_word(self):
        findings = validate_plan(parse_text("- [ ] do the thing with tests\n"), check_refs=False)
        self.assertNotIn("PA012", codes(findings))

    def test_pa013_duplicate_title(self):
        findings = validate_plan(parse_text("- [ ] 1 same\n- [ ] 2 same\n"), check_refs=False)
        self.assertIn("PA013", codes(findings))

    def test_pa014_sequence_gap(self):
        findings = validate_plan(parse_text("- [ ] 1 a\n- [ ] 3 c\n"), check_refs=False)
        self.assertIn("PA014", codes(findings))

    def test_pa014_not_raised_for_sequential_ids(self):
        findings = validate_plan(
            parse_text("- [ ] 1.1 a\n- [ ] 1.2 b\n- [ ] 1.3 c\n"), check_refs=False
        )
        self.assertNotIn("PA014", codes(findings))

    def test_pa014_not_raised_without_a_parent_task(self):
        # 1.1 / 1.2 without a literal "1" task is a completely normal outline.
        findings = validate_plan(parse_text("- [ ] 1.1 a\n- [ ] 1.2 b\n"), check_refs=False)
        self.assertNotIn("PA014", codes(findings))


class IgnoreDirectiveTest(unittest.TestCase):
    def test_line_scoped_ignore(self):
        text = "- [x] done but no ref  <!-- plananchor: ignore PA003 -->\n"
        findings = validate_plan(parse_text(text), check_refs=False)
        self.assertNotIn("PA003", codes(findings))

    def test_ignore_does_not_hide_other_rules(self):
        text = "- [x] done but no ref  <!-- plananchor: ignore PA003 -->\n- [x] second also bare\n"
        findings = validate_plan(parse_text(text), check_refs=False)
        self.assertIn("PA003", codes(findings))

    def test_bare_ignore_suppresses_everything_on_the_line(self):
        text = "- [x] bare <!-- plananchor: ignore -->\n"
        findings = validate_plan(parse_text(text), check_refs=False)
        self.assertEqual([], findings)


class OrderingTest(unittest.TestCase):
    def test_errors_sort_before_warnings(self):
        text = "- [ ] 1 a\n- [ ] 1 b\n- [ ] plain task without acceptance\n"
        findings = validate_plan(parse_text(text), check_refs=False)
        ranks = [f.severity.rank for f in findings]
        self.assertEqual(ranks, sorted(ranks, reverse=True))


class CatalogTest(unittest.TestCase):
    def test_catalog_is_non_empty_and_unique(self):
        rules = rules_catalog()
        self.assertGreaterEqual(len(rules), 10)
        ids = [r["rule"] for r in rules]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
