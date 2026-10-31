"""Schema & hygiene validation for plan files.

Every rule has a stable ``PAxxx`` identifier so that CI baselines and
``# plananchor: ignore`` comments stay stable across releases.

Rule catalogue
--------------

``PA001`` empty-plan            — the file contains no tasks at all
``PA002`` duplicate-uid         — the same outline id appears twice
``PA003`` unreferenced-task     — a *closed* task declares no file reference
``PA004`` blocked-without-note  — a blocked task gives no reason
``PA005`` multiple-active       — more than one task is in progress at once
``PA006`` parent-inconsistent   — a parent is closed but children are open
``PA007`` stale-active          — an active task sits above a closed sibling flow
``PA008`` missing-section       — no Markdown heading structures the plan
``PA009`` untitled-task         — task title is empty
``PA010`` deep-nesting          — nesting deeper than ``max_depth`` (default 4)
``PA011`` dangling-reference    — a referenced file does not exist on disk
``PA012`` no-acceptance         — a task has no observable acceptance marker
``PA013`` duplicate-title       — two tasks share the exact same title
``PA014`` sequence-gap          — numeric outline ids skip a level
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .model import Finding, Plan, Severity, Task, TaskStatus

#: Default maximum nesting depth before ``PA010`` fires.
DEFAULT_MAX_DEPTH = 4

#: Tokens that mark a task as having an observable acceptance criterion.
_ACCEPTANCE_HINT_RE = re.compile(
    r"(accept|verify|assert|test|expect|criterion|criteria|验收|验证|测试|断言|通过率|覆盖)",
    re.IGNORECASE,
)

_IGNORE_RE = re.compile(r"plananchor:\s*ignore(?:\s+(PA\d{3}(?:\s*,\s*PA\d{3})*))?", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def validate_plan(
    plan: Plan,
    *,
    repo_root: Optional[str] = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    check_refs: bool = True,
) -> List[Finding]:
    """Run the full rule set against a parsed plan.

    Args:
        plan: Parsed plan document.
        repo_root: Optional repository root used to resolve ``PA011``.  When
            omitted it defaults to the directory containing the plan file.
        max_depth: Maximum allowed nesting depth.
        check_refs: Whether to stat referenced files on disk.

    Returns:
        Findings sorted by severity (desc) then line number (asc).
    """
    findings: List[Finding] = []
    tasks = plan.all_tasks()

    ignored = _collect_ignores(plan)

    if not tasks:
        findings.append(
            Finding(
                rule="PA001",
                severity=Severity.ERROR,
                message="plan contains no tasks",
                line=1,
                hint="add at least one `- [ ]` task item",
            )
        )
        return _sort(findings)

    root = repo_root
    if root is None and plan.path:
        root = os.path.dirname(os.path.abspath(plan.path)) or "."
    if root is None:
        root = "."

    findings.extend(_rule_duplicate_uid(tasks))
    findings.extend(_rule_duplicate_title(tasks))
    findings.extend(_rule_untitled(tasks))
    findings.extend(_rule_missing_section(plan, tasks))
    findings.extend(_rule_deep_nesting(tasks, max_depth))
    findings.extend(_rule_unreferenced(tasks))
    findings.extend(_rule_blocked_without_note(tasks))
    findings.extend(_rule_multiple_active(tasks))
    findings.extend(_rule_parent_inconsistent(tasks))
    findings.extend(_rule_no_acceptance(tasks))
    findings.extend(_rule_sequence_gap(tasks))
    if check_refs:
        findings.extend(_rule_dangling_reference(tasks, root))

    filtered = [f for f in findings if f.rule not in ignored.get(f.line, set())]
    return _sort(filtered)


def rules_catalog() -> List[Dict[str, str]]:
    """Return the rule catalogue as plain dictionaries (for docs / JSON)."""
    return [
        {"rule": "PA001", "severity": "error", "summary": "Plan contains no tasks"},
        {"rule": "PA002", "severity": "error", "summary": "Duplicate task uid"},
        {"rule": "PA003", "severity": "warning", "summary": "Closed task declares no file reference"},
        {"rule": "PA004", "severity": "warning", "summary": "Blocked task has no reason"},
        {"rule": "PA005", "severity": "info", "summary": "More than one active task"},
        {"rule": "PA006", "severity": "error", "summary": "Parent closed while children remain open"},
        {"rule": "PA007", "severity": "info", "summary": "No active task while work is outstanding"},
        {"rule": "PA008", "severity": "warning", "summary": "Plan has no structuring heading"},
        {"rule": "PA009", "severity": "warning", "summary": "Task title is empty"},
        {"rule": "PA010", "severity": "warning", "summary": "Nesting deeper than max_depth"},
        {"rule": "PA011", "severity": "warning", "summary": "Referenced file does not exist"},
        {"rule": "PA012", "severity": "info", "summary": "Task has no acceptance marker"},
        {"rule": "PA013", "severity": "info", "summary": "Duplicate task title"},
        {"rule": "PA014", "severity": "info", "summary": "Numeric outline ids skip a level"},
    ]


# --------------------------------------------------------------------------- #
# Ignore handling
# --------------------------------------------------------------------------- #

def _collect_ignores(plan: Plan) -> Dict[int, Set[str]]:
    """Collect per-line ``<!-- plananchor: ignore PA003 -->`` directives.

    A bare ``plananchor: ignore`` suppresses *all* rules on that line.
    """
    out: Dict[int, Set[str]] = {}
    for idx, raw in enumerate(plan.text.split("\n"), start=1):
        match = _IGNORE_RE.search(raw)
        if not match:
            continue
        codes = match.group(1)
        if codes:
            out[idx] = {c.strip().upper() for c in codes.split(",")}
        else:
            out[idx] = {r["rule"] for r in rules_catalog()}
    return out


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #

def _sort(findings: Sequence[Finding]) -> List[Finding]:
    return sorted(findings, key=lambda f: (-f.severity.rank, f.line, f.rule))


def _rule_duplicate_uid(tasks: Sequence[Task]) -> List[Finding]:
    seen: Dict[str, int] = {}
    out: List[Finding] = []
    for t in tasks:
        base = t.uid.split("#")[0]
        if base in seen:
            out.append(
                Finding(
                    rule="PA002",
                    severity=Severity.ERROR,
                    message="duplicate task id %r (first seen on line %d)" % (base, seen[base]),
                    line=t.line,
                    task_uid=t.uid,
                    hint="renumber the outline id, or remove the stale duplicate",
                )
            )
        else:
            seen[base] = t.line
    return out


def _rule_duplicate_title(tasks: Sequence[Task]) -> List[Finding]:
    seen: Dict[str, int] = {}
    out: List[Finding] = []
    for t in tasks:
        key = t.title.strip().lower()
        if not key:
            continue
        if key in seen:
            out.append(
                Finding(
                    rule="PA013",
                    severity=Severity.INFO,
                    message="duplicate task title %r (line %d)" % (t.title, seen[key]),
                    line=t.line,
                    task_uid=t.uid,
                    hint="make titles unique so hand-off briefings stay unambiguous",
                )
            )
        else:
            seen[key] = t.line
    return out


def _rule_untitled(tasks: Sequence[Task]) -> List[Finding]:
    return [
        Finding(
            rule="PA009",
            severity=Severity.WARNING,
            message="task has no title",
            line=t.line,
            task_uid=t.uid,
            hint="give the task a descriptive title",
        )
        for t in tasks
        if not t.title.strip() or t.title.strip() == t.uid
    ]


def _rule_missing_section(plan: Plan, tasks: Sequence[Task]) -> List[Finding]:
    if plan.sections or len(tasks) <= 5:
        return []
    return [
        Finding(
            rule="PA008",
            severity=Severity.WARNING,
            message="plan has %d tasks but no Markdown heading" % len(tasks),
            line=tasks[0].line,
            hint="group tasks under `##` headings so resume briefings stay readable",
        )
    ]


def _rule_deep_nesting(tasks: Sequence[Task], max_depth: int) -> List[Finding]:
    return [
        Finding(
            rule="PA010",
            severity=Severity.WARNING,
            message="task nested at depth %d (limit %d)" % (t.depth, max_depth),
            line=t.line,
            task_uid=t.uid,
            hint="flatten the outline — deep trees are easy for agents to lose",
        )
        for t in tasks
        if t.depth > max_depth
    ]


def _rule_unreferenced(tasks: Sequence[Task]) -> List[Finding]:
    out: List[Finding] = []
    for t in tasks:
        if t.status in (TaskStatus.DONE, TaskStatus.ACTIVE) and not t.refs and not t.children:
            out.append(
                Finding(
                    rule="PA003",
                    severity=Severity.WARNING,
                    message="%s task %r declares no file reference" % (t.status.value, t.title),
                    line=t.line,
                    task_uid=t.uid,
                    hint="reference the touched file (`@path/to/file.py`) so drift can be verified",
                )
            )
    return out


def _rule_blocked_without_note(tasks: Sequence[Task]) -> List[Finding]:
    return [
        Finding(
            rule="PA004",
            severity=Severity.WARNING,
            message="blocked task %r gives no reason" % t.title,
            line=t.line,
            task_uid=t.uid,
            hint="append `(blocked: <reason>)` so the next session can unblock itself",
        )
        for t in tasks
        if t.status is TaskStatus.BLOCKED and not t.note
    ]


def _rule_multiple_active(tasks: Sequence[Task]) -> List[Finding]:
    active = [t for t in tasks if t.status is TaskStatus.ACTIVE]
    if len(active) <= 1:
        return []
    return [
        Finding(
            rule="PA005",
            severity=Severity.INFO,
            message="%d tasks are marked in progress; agents resume best with one" % len(active),
            line=active[1].line,
            task_uid=active[1].uid,
            hint="keep a single `[~]` task or accept the parallel flow explicitly",
        )
    ]


def _rule_parent_inconsistent(tasks: Sequence[Task]) -> List[Finding]:
    out: List[Finding] = []
    for t in tasks:
        if not t.children:
            continue
        if t.status in (TaskStatus.DONE, TaskStatus.SKIPPED):
            open_children = [c for c in t.descendants if c.status.is_open]
            if open_children:
                out.append(
                    Finding(
                        rule="PA006",
                        severity=Severity.ERROR,
                        message="parent %r is %s but %d child task(s) remain open"
                        % (t.title, t.status.value, len(open_children)),
                        line=t.line,
                        task_uid=t.uid,
                        hint="close the children or reopen the parent",
                    )
                )
    return out


def _rule_no_acceptance(tasks: Sequence[Task]) -> List[Finding]:
    out: List[Finding] = []
    for t in tasks:
        if t.status is TaskStatus.DONE and t.children:
            continue  # rollup parents get their acceptance from children
        if t.status is TaskStatus.PENDING and not _ACCEPTANCE_HINT_RE.search(t.title + " " + t.note):
            out.append(
                Finding(
                    rule="PA012",
                    severity=Severity.INFO,
                    message="task %r has no acceptance marker" % t.title,
                    line=t.line,
                    task_uid=t.uid,
                    hint="state how completion is verified (test / assertion / criterion)",
                )
            )
    return out


def _rule_sequence_gap(tasks: Sequence[Task]) -> List[Finding]:
    """Detect numbering gaps inside an outline level.

    ``1.1`` ``1.2`` ``1.3`` is fine; ``1.1`` ``1.3`` is a gap — usually a task
    that was deleted without renumbering, which makes hand-off ambiguous.
    """
    groups: Dict[str, List[Tuple[int, int]]] = {}
    for t in tasks:
        uid = t.uid.split("#")[0]
        match = re.match(r"^(\d+(?:\.\d+)*)[a-zA-Z]?$", uid)
        if not match:
            continue
        parts = match.group(1).split(".")
        parent = ".".join(parts[:-1])
        groups.setdefault(parent, []).append((int(parts[-1]), t.line))

    out: List[Finding] = []
    for parent, items in groups.items():
        items.sort()
        for i in range(1, len(items)):
            prev, prev_line = items[i - 1]
            cur, cur_line = items[i]
            if cur == prev:
                continue  # duplicates are PA002's job
            if cur != prev + 1:
                label = parent or "top level"
                out.append(
                    Finding(
                        rule="PA014",
                        severity=Severity.INFO,
                        message="outline numbering skips from %d to %d under %r" % (prev, cur, label),
                        line=cur_line,
                        hint="renumber sequentially, or restore the deleted task",
                    )
                )
    return out


def _rule_dangling_reference(tasks: Sequence[Task], root: str) -> List[Finding]:
    out: List[Finding] = []
    checked: Dict[str, bool] = {}
    for t in tasks:
        for ref in t.refs:
            if ref in checked:
                exists = checked[ref]
            else:
                exists = os.path.exists(os.path.join(root, ref))
                checked[ref] = exists
            if not exists:
                out.append(
                    Finding(
                        rule="PA011",
                        severity=Severity.WARNING,
                        message="referenced file %r does not exist under %s" % (ref, root),
                        line=t.line,
                        task_uid=t.uid,
                        hint="create the file, fix the path, or mark the task blocked",
                    )
                )
    return out
