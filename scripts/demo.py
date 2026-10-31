#!/usr/bin/env python3
"""End-to-end PlanAnchor demo — runs entirely offline in a temporary directory.

Usage::

    python scripts/demo.py
    make demo

The script walks through the full lifecycle:

1. scaffold a plan with ``plananchor init``
2. parse it and show the task tree
3. create a recovery anchor (snapshot)
4. simulate a context compaction that deletes most of the plan
5. detect the regression and restore the plan
6. verify the snapshot hash chain
7. emit a copy-paste resume briefing
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from plananchor.anchor import AnchorStore  # noqa: E402
from plananchor.parser import parse_file  # noqa: E402


def run(args: list, cwd: str) -> int:
    """Run the CLI the way a user would."""
    proc = subprocess.run(
        [sys.executable, "-m", "plananchor"] + args,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": ROOT},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    sys.stdout.write(proc.stdout.decode("utf-8", errors="replace"))
    return proc.returncode


def banner(text: str) -> None:
    print("\n" + "=" * 68)
    print(text)
    print("=" * 68)


def simulate_compaction(path: str, keep: int = 1) -> None:
    """Delete every task after the first ``keep`` — a classic compaction loss."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    out, seen = [], 0
    for line in lines:
        if re.match(r"^\s*[-*+]\s+\[", line):
            seen += 1
            if seen > keep:
                continue
        out.append(line)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def main() -> int:
    work = tempfile.mkdtemp(prefix="plananchor-demo-")
    plan = os.path.join(work, "PLAN.md")
    try:
        banner("1/7  Scaffold a plan")
        run(["init", plan], work)

        banner("2/7  Parse the task tree")
        run(["parse", plan], work)

        banner("3/7  Create a recovery anchor")
        run(["snapshot", plan, "-m", "demo baseline"], work)

        before = len(parse_file(plan).all_tasks())

        banner("4/7  Simulate a context compaction")
        simulate_compaction(plan, keep=1)
        after = len(parse_file(plan).all_tasks())
        print("tasks before: %d   after compaction: %d" % (before, after))

        store = AnchorStore(plan)
        signal = store.detect_compaction(parse_file(plan))
        print("detected      : %s" % signal.message)
        print("lost tasks    : %s" % (", ".join(signal.lost_tasks) or "(none)"))

        banner("5/7  Restore from the anchor")
        run(["restore", plan], work)
        recovered = len(parse_file(plan).all_tasks())
        print("tasks after restore: %d" % recovered)
        if recovered != before:
            print("!! restore did not fully recover the plan")
            return 1

        banner("6/7  Verify the snapshot hash chain")
        rc = run(["verify", plan], work)
        if rc != 0:
            return rc

        banner("7/7  Emit a resume briefing")
        run(["resume", plan, "--lang", "zh"], work)

        print("\nDemo complete — plan anchored, compacted, restored and verified.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
