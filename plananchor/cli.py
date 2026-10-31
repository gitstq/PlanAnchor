"""Command line interface for PlanAnchor.

Commands::

    plananchor status     <plan>   full analysis (validate + drift + stall)
    plananchor check      <plan>   schema / hygiene validation only
    plananchor drift      <plan>   plan vs. repository drift
    plananchor parse      <plan>   dump the parsed task tree
    plananchor snapshot   <plan>   create a recovery anchor
    plananchor restore    <plan>   restore from an anchor (forward merge)
    plananchor verify     <plan>   verify the snapshot hash chain
    plananchor resume     <plan>   emit a hand-off briefing
    plananchor init       [path]   scaffold a starter plan file
    plananchor rules               print the rule catalogue

Exit codes::

    0  no error-severity findings
    1  at least one error-severity finding (CI gate)
    2  usage error
    3  input file missing / unreadable
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from . import __version__
from . import anchor as anchor_mod
from . import drift as drift_mod
from . import gitutil
from . import parser as parser_mod
from . import report as report_mod
from . import resume as resume_mod
from . import stall as stall_mod
from . import validate as validate_mod
from .model import Plan, Severity

EXIT_OK = 0
EXIT_ERRORS = 1
EXIT_USAGE = 2
EXIT_INPUT = 3

#: Default plan file names probed when the user passes no path.
DEFAULT_PLAN_NAMES = ("PLAN.md", "plan.md", "PLAN.zh.md", ".agent/PLAN.md", "docs/PLAN.md")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point.  Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        return args.handler(args)
    except FileNotFoundError as exc:
        _err(str(exc))
        return EXIT_INPUT
    except BrokenPipeError:  # pragma: no cover - piping into head
        return EXIT_OK
    except KeyboardInterrupt:  # pragma: no cover
        _err("interrupted")
        return 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plananchor",
        description="PlanAnchor — zero-dependency plan anchoring, drift auditing and "
        "crash recovery for AI coding agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="exit codes: 0 ok · 1 errors found · 2 usage · 3 input missing",
    )
    parser.add_argument("-V", "--version", action="version", version="PlanAnchor %s" % __version__)
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        return p

    # -- status ------------------------------------------------------------ #
    p = add("status", "full analysis: validation + drift + stall")
    _plan_arg(p)
    _report_args(p)
    p.add_argument("--repo", help="repository root for drift detection")
    p.add_argument("--base", default="HEAD", help="git baseline revision (default HEAD)")
    p.add_argument("--max-depth", type=int, default=validate_mod.DEFAULT_MAX_DEPTH)
    p.add_argument("--no-git", action="store_true", help="skip drift detection entirely")
    p.add_argument("--fail-on", choices=("error", "warning", "info"), default="error")
    p.set_defaults(handler=cmd_status)

    # -- check ------------------------------------------------------------- #
    p = add("check", "schema & hygiene validation")
    _plan_arg(p)
    _report_args(p)
    p.add_argument("--repo", help="repository root used to resolve file references")
    p.add_argument("--max-depth", type=int, default=validate_mod.DEFAULT_MAX_DEPTH)
    p.add_argument("--no-refs", action="store_true", help="skip on-disk reference checks")
    p.add_argument("--fail-on", choices=("error", "warning", "info"), default="error")
    p.set_defaults(handler=cmd_check)

    # -- drift ------------------------------------------------------------- #
    p = add("drift", "plan vs. repository drift detection")
    _plan_arg(p)
    _report_args(p)
    p.add_argument("--repo", help="repository root")
    p.add_argument("--base", default="HEAD", help="git baseline revision (default HEAD)")
    p.add_argument("--no-untracked", action="store_true", help="ignore untracked files")
    p.add_argument("--ignore", action="append", default=[], help="ignore path substring (repeatable)")
    p.add_argument("--fail-on", choices=("error", "warning", "info"), default="error")
    p.set_defaults(handler=cmd_drift)

    # -- parse ------------------------------------------------------------- #
    p = add("parse", "dump the parsed task tree")
    _plan_arg(p)
    p.add_argument("--json", action="store_true", help="emit JSON instead of a tree")
    p.add_argument("--stats", action="store_true", help="print only aggregate statistics")
    p.set_defaults(handler=cmd_parse)

    # -- snapshot ---------------------------------------------------------- #
    p = add("snapshot", "create a recovery anchor for the current plan")
    _plan_arg(p)
    p.add_argument("-m", "--note", default="", help="annotation stored with the snapshot")
    p.add_argument("--keep", type=int, default=50, help="retain at most N snapshots")
    p.set_defaults(handler=cmd_snapshot)

    # -- restore ----------------------------------------------------------- #
    p = add("restore", "restore a compacted plan from an anchor")
    _plan_arg(p)
    p.add_argument("--seq", type=int, default=None, help="snapshot sequence (default: latest)")
    p.add_argument("--exact", action="store_true", help="write the snapshot verbatim (no merge)")
    p.add_argument("--dry-run", action="store_true", help="print the result without writing")
    p.set_defaults(handler=cmd_restore)

    # -- verify ------------------------------------------------------------ #
    p = add("verify", "verify the snapshot hash chain")
    _plan_arg(p)
    p.set_defaults(handler=cmd_verify)

    # -- resume ------------------------------------------------------------ #
    p = add("resume", "emit a copy-paste hand-off briefing")
    _plan_arg(p)
    p.add_argument("--lang", choices=("zh", "en"), default="zh", help="briefing language")
    p.add_argument("--next", type=int, default=3, help="how many upcoming tasks to list")
    p.add_argument("--no-prompt", action="store_true", help="omit the copy-paste prompt block")
    p.add_argument("-o", "--output", help="write to a file instead of stdout")
    p.set_defaults(handler=cmd_resume)

    # -- init -------------------------------------------------------------- #
    p = add("init", "scaffold a starter plan file")
    p.add_argument("path", nargs="?", default="PLAN.md", help="target path (default PLAN.md)")
    p.add_argument("--force", action="store_true", help="overwrite an existing file")
    p.set_defaults(handler=cmd_init)

    # -- rules ------------------------------------------------------------- #
    p = add("rules", "print the rule catalogue")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(handler=cmd_rules)

    return parser


def _plan_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "plan",
        nargs="?",
        help="path to the plan file (auto-detected: %s)" % ", ".join(DEFAULT_PLAN_NAMES),
    )


def _report_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "-f",
        "--format",
        choices=report_mod.FORMATS,
        default="text",
        help="report format (default: text)",
    )
    p.add_argument("-o", "--output", help="write the report to a file")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _resolve_plan(value: Optional[str]) -> str:
    """Resolve the plan path, probing default names when omitted."""
    if value:
        if not os.path.isfile(value):
            raise FileNotFoundError("plan file not found: %s" % value)
        return value
    for name in DEFAULT_PLAN_NAMES:
        if os.path.isfile(name):
            return name
    raise FileNotFoundError(
        "no plan file given and none of %s exists in %s" % (", ".join(DEFAULT_PLAN_NAMES), os.getcwd())
    )


def _out(text: str, path: Optional[str] = None) -> None:
    if path:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("written: %s" % path)
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _err(message: str) -> None:
    sys.stderr.write("plananchor: %s\n" % message)


def _decide(payload_counts: dict, fail_on: str) -> int:
    """Map a severity summary onto an exit code."""
    order = ["error", "warning", "info"]
    for level in order[: order.index(fail_on) + 1]:
        if payload_counts.get(level, 0):
            return EXIT_ERRORS
    return EXIT_OK


def _store(plan_path: str) -> anchor_mod.AnchorStore:
    return anchor_mod.AnchorStore(plan_path)


def _load(path: str) -> Plan:
    return parser_mod.parse_file(path)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def cmd_status(args: argparse.Namespace) -> int:
    path = _resolve_plan(args.plan)
    plan = _load(path)

    findings = validate_mod.validate_plan(
        plan, repo_root=args.repo, max_depth=args.max_depth, check_refs=not args.no_git
    )

    drift = None
    if not args.no_git:
        drift = drift_mod.detect_drift(plan, repo=args.repo, base=args.base)

    store = _store(path)
    stall = stall_mod.detect_stalls(plan, store if store.exists() else None)

    payload = report_mod.collect(plan, findings, drift, stall)
    _out(report_mod.emit(args.format, plan, findings, drift, stall), args.output)
    return _decide(payload["summary"], args.fail_on)


def cmd_check(args: argparse.Namespace) -> int:
    path = _resolve_plan(args.plan)
    plan = _load(path)
    findings = validate_mod.validate_plan(
        plan,
        repo_root=args.repo,
        max_depth=args.max_depth,
        check_refs=not args.no_refs,
    )
    payload = report_mod.collect(plan, findings)
    _out(report_mod.emit(args.format, plan, findings), args.output)
    return _decide(payload["summary"], args.fail_on)


def cmd_drift(args: argparse.Namespace) -> int:
    path = _resolve_plan(args.plan)
    plan = _load(path)
    drift = drift_mod.detect_drift(
        plan,
        repo=args.repo,
        base=args.base,
        include_untracked=not args.no_untracked,
        ignore_paths=args.ignore or None,
    )
    payload = report_mod.collect(plan, [], drift)
    _out(report_mod.emit(args.format, plan, [], drift), args.output)
    return _decide(payload["summary"], args.fail_on)


def cmd_parse(args: argparse.Namespace) -> int:
    path = _resolve_plan(args.plan)
    plan = _load(path)

    if args.json:
        import json

        _out(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return EXIT_OK

    if args.stats:
        counts = plan.counts()
        _out(
            "tasks=%d progress=%.1f%% done=%d active=%d pending=%d blocked=%d skipped=%d"
            % (
                len(plan.all_tasks()),
                plan.progress(),
                counts["done"],
                counts["active"],
                counts["pending"],
                counts["blocked"],
                counts["skipped"],
            )
        )
        return EXIT_OK

    lines: List[str] = []
    for t in plan.tasks:
        _tree(lines, t, 0)
    _out("\n".join(lines) if lines else "(no tasks)")
    return EXIT_OK


def _tree(out: List[str], task, depth: int) -> None:
    pad = "  " * depth
    extra = ""
    if task.refs:
        extra += "  @" + ", @".join(task.refs)
    if task.symbols:
        extra += "  #" + ", #".join(task.symbols)
    if task.owner:
        extra += "  (owner: %s)" % task.owner
    if task.note:
        extra += "  (%s)" % task.note
    out.append("%s- [%s] %s  %s%s" % (pad, task.status.glyph, task.uid, task.title, extra))
    for child in task.children:
        _tree(out, child, depth + 1)


def cmd_snapshot(args: argparse.Namespace) -> int:
    path = _resolve_plan(args.plan)
    plan = _load(path)
    store = _store(path)
    snap = store.create(plan, note=args.note)
    removed = store.prune(keep=args.keep)
    _out(
        "snapshot #%d created · digest %s · progress %.1f%%%s"
        % (snap.seq, snap.short, snap.progress, (" · pruned %d" % removed) if removed else "")
    )
    return EXIT_OK


def cmd_restore(args: argparse.Namespace) -> int:
    path = args.plan
    if path and not os.path.isfile(path):
        raise FileNotFoundError("plan file not found: %s" % path)
    path = _resolve_plan(path)
    store = _store(path)
    if not store.exists():
        _err("no anchor store next to %s — run `plananchor snapshot` first" % path)
        return EXIT_INPUT

    text, signal = store.restore(path, seq=args.seq, merge=not args.exact, dry_run=args.dry_run)
    _out(signal.message)
    if args.dry_run:
        _out("--- restored content (dry run) ---")
        _out(text)
    else:
        _out("restored: %s (%d tasks)" % (path, len(parser_mod.parse_text(text).all_tasks())))
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    path = _resolve_plan(args.plan)
    store = _store(path)
    if not store.exists():
        _err("no anchor store next to %s" % path)
        return EXIT_INPUT
    result = store.verify()
    _out("%s — %s" % ("OK" if result.ok else "BROKEN", result.message))
    return EXIT_OK if result.ok else EXIT_ERRORS


def cmd_resume(args: argparse.Namespace) -> int:
    path = _resolve_plan(args.plan)
    plan = _load(path)
    store = _store(path)
    drift = None
    if gitutil.is_repo(os.path.dirname(os.path.abspath(path)) or "."):
        drift = drift_mod.detect_drift(plan, repo=os.path.dirname(os.path.abspath(path)) or ".")
    brief = resume_mod.build_resume(
        plan, store=store, drift=drift, lang=args.lang, next_count=args.next
    )
    _out(resume_mod.render_brief(brief, with_prompt=not args.no_prompt), args.output)
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    path = args.path
    if os.path.exists(path) and not args.force:
        _err("%s already exists (use --force to overwrite)" % path)
        return EXIT_INPUT
    _out(_TEMPLATE, path)
    _out("created %s — mark tasks with [ ] [~] [x] [-] [!]" % path)
    return EXIT_OK


def cmd_rules(args: argparse.Namespace) -> int:
    rules = validate_mod.rules_catalog()
    if args.json:
        import json

        _out(json.dumps(rules, ensure_ascii=False, indent=2))
        return EXIT_OK
    lines = ["%-8s %-8s %s" % ("RULE", "SEVERITY", "SUMMARY")]
    for r in rules:
        lines.append("%-8s %-8s %s" % (r["rule"], r["severity"], r["summary"]))
    _out("\n".join(lines))
    return EXIT_OK


_TEMPLATE = """---
project: my-project
owner: agent
---

# My Project Plan

## Phase 1 — Foundations

- [~] 1.1 Define the data model `@src/model.py` #Model
- [ ] 1.2 Implement the parser `@src/parser.py` #parse_text
  - [ ] 1.2.1 Handle nested indentation
  - [ ] 1.2.2 Handle status glyphs
- [ ] 1.3 Add unit tests `@tests/test_parser.py` (accept: 90% coverage)

## Phase 2 — Hardening

- [ ] 2.1 Wire up the CLI `@src/cli.py`
- [!] 2.2 Publish the package (blocked: waiting for the registry token)
"""


# --------------------------------------------------------------------------- #

def _self_check() -> int:  # pragma: no cover - developer convenience
    """Smoke test used by ``python -m plananchor.selftest``."""
    plan = parser_mod.parse_text(_TEMPLATE, path="PLAN.md")
    findings = validate_mod.validate_plan(plan, check_refs=False)
    print("tasks=%d progress=%.1f%% findings=%d" % (len(plan.all_tasks()), plan.progress(), len(findings)))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
