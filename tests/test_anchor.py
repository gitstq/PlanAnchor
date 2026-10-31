"""Anchor store tests: snapshots, hash chain, compaction detection, restore."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from plananchor.anchor import AnchorStore, sha256_text
from plananchor.parser import parse_file, parse_text


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class AnchorStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.plan_path = os.path.join(self.tmp, "PLAN.md")
        write(self.plan_path, "- [ ] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n")
        self.store = AnchorStore(self.plan_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ensure_creates_layout(self):
        snap_dir = self.store.ensure()
        self.assertTrue(os.path.isdir(snap_dir))
        self.assertTrue(os.path.isfile(self.store.index_path))
        self.assertTrue(self.store.exists())

    def test_create_and_list(self):
        plan = parse_file(self.plan_path)
        self.store.create(plan)
        self.store.create(plan)
        self.assertEqual(len(self.store.list()), 2)

    def test_latest_is_the_newest(self):
        plan = parse_file(self.plan_path)
        first = self.store.create(plan)
        write(self.plan_path, "- [x] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n")
        second = self.store.create(parse_file(self.plan_path))
        self.assertEqual(self.store.latest().seq, second.seq)
        self.assertGreater(second.seq, first.seq)

    def test_hash_chain_links(self):
        plan = parse_file(self.plan_path)
        first = self.store.create(plan)
        self.assertEqual(first.prev, "")
        write(self.plan_path, "- [x] 1 a `@a.py`\n")
        second = self.store.create(parse_file(self.plan_path))
        self.assertEqual(second.prev, first.digest)
        self.assertTrue(second.verify())

    def test_verify_ok(self):
        plan = parse_file(self.plan_path)
        for _ in range(3):
            self.store.create(plan)
        result = self.store.verify()
        self.assertTrue(result.ok)
        self.assertEqual(result.snapshots, 3)

    def test_verify_detects_tampering(self):
        plan = parse_file(self.plan_path)
        snap = self.store.create(plan)
        # Corrupt the stored text without updating the digest.
        path = os.path.join(self.store.snapshot_dir, "%06d-%s.json" % (1, "x"))
        for entry in self.store.list():
            path = os.path.join(self.store.snapshot_dir, str(entry["file"]))
        import json

        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["text"] = "- [x] tampered\n"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        result = self.store.verify()
        self.assertFalse(result.ok)
        self.assertEqual(result.broken_at, snap.seq)

    def test_detect_compaction_lost_tasks(self):
        self.store.create(parse_file(self.plan_path))
        write(self.plan_path, "- [ ] 1 a `@a.py`\n")  # task 2 disappeared
        signal = self.store.detect_compaction(parse_file(self.plan_path))
        self.assertTrue(signal.compacted)
        self.assertIn("2", signal.lost_tasks)

    def test_detect_compaction_regression(self):
        self.store.create(parse_file(self.plan_path))
        write(self.plan_path, "- [ ] 1 a `@a.py`\n- [x] 2 b `@b.py`\n")
        self.store.create(parse_file(self.plan_path))
        write(self.plan_path, "- [ ] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n")  # 2 went done -> pending
        signal = self.store.detect_compaction(parse_file(self.plan_path))
        self.assertTrue(signal.compacted)
        self.assertEqual(len(signal.regressed_tasks), 1)
        self.assertEqual(signal.regressed_tasks[0][0], "2")

    def test_no_compaction_when_plan_advances(self):
        self.store.create(parse_file(self.plan_path))
        write(self.plan_path, "- [x] 1 a `@a.py`\n- [x] 2 b `@b.py`\n")
        signal = self.store.detect_compaction(parse_file(self.plan_path))
        self.assertFalse(signal.compacted)

    def test_detect_compaction_without_baseline(self):
        signal = self.store.detect_compaction(parse_file(self.plan_path))
        self.assertFalse(signal.compacted)
        self.assertIn("no baseline", signal.message)

    def test_restore_recovers_lost_tasks(self):
        self.store.create(parse_file(self.plan_path))
        write(self.plan_path, "- [ ] 1 a `@a.py`\n")  # compaction
        text, signal = self.store.restore(self.plan_path)
        self.assertTrue(signal.compacted)
        plan = parse_text(text)
        self.assertIsNotNone(plan.find("2"))

    def test_restore_forward_merge_keeps_new_progress(self):
        self.store.create(parse_file(self.plan_path))
        write(self.plan_path, "- [x] 1 a `@a.py`\n- [x] 2 b `@b.py`\n")
        # Simulate a compaction that resets task 1 but keeps 2 done.
        write(self.plan_path, "- [ ] 1 a `@a.py`\n- [x] 2 b `@b.py`\n")
        text, _ = self.store.restore(self.plan_path)
        plan = parse_text(text)
        self.assertIsNotNone(plan.find("2"))

    def test_restore_exact_overwrites(self):
        self.store.create(parse_file(self.plan_path))
        write(self.plan_path, "- [x] 1 a `@a.py`\n")
        text, _ = self.store.restore(self.plan_path, merge=False)
        self.assertEqual(text, "- [ ] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n")

    def test_restore_dry_run_does_not_write(self):
        self.store.create(parse_file(self.plan_path))
        before = open(self.plan_path, encoding="utf-8").read()
        self.store.restore(self.plan_path, dry_run=True)
        after = open(self.plan_path, encoding="utf-8").read()
        self.assertEqual(before, after)

    def test_restore_without_snapshots_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.restore(self.plan_path)

    def test_prune_keeps_newest(self):
        for _ in range(5):
            self.store.create(parse_file(self.plan_path))
        removed = self.store.prune(keep=2)
        self.assertEqual(removed, 3)
        self.assertEqual(len(self.store.list()), 2)

    def test_prune_is_a_noop_when_under_limit(self):
        self.store.create(parse_file(self.plan_path))
        self.assertEqual(self.store.prune(keep=10), 0)

    def test_load_missing_seq(self):
        self.assertIsNone(self.store.load(999))

    def test_snapshot_records_progress(self):
        write(self.plan_path, "- [x] 1 a `@a.py`\n- [ ] 2 b `@b.py`\n")
        snap = self.store.create(parse_file(self.plan_path))
        self.assertAlmostEqual(snap.progress, 50.0, places=3)

    def test_sha256_helper(self):
        self.assertEqual(len(sha256_text("abc")), 64)
        self.assertNotEqual(sha256_text("abc"), sha256_text("abd"))


if __name__ == "__main__":
    unittest.main()
