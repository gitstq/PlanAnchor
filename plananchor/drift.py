"""Plan-vs-repository drift detection.

Drift is the failure mode PlanAnchor exists to catch: *the agent says it did
the work, the repository disagrees* — or the reverse, code changed with no plan
item claiming it.

Drift classes
-------------

``DF001`` claimed-done-untouched  — task is ``done`` but no referenced file changed
``DF002`` silent-change           — a changed file is claimed by no open task
``DF003`` symbol-missing          — the referenced symbol never appears in the diff
``DF004`` scope-creep             — a *done* task touched files outside its refs
``DF005`` orphan-reference        — a task references a file Git does not track
``DF006`` no-progress             — nothing changed at all while tasks remain open

Settled work trees
------------------

Drift is verified against a *change window* — by default the uncommitted diff
against ``HEAD``.  A freshly cloned repository (or one where every edit is
already committed) has an **empty window**, so per-task "claimed done but
untouched" verdicts would be pure noise: the work simply happened in an earlier
commit.  In that *settled* mode PlanAnchor collapses the verdicts into a single
informational ``DF001`` summary instead of one error per task.  Widen the
window with ``--base <rev>`` (or ``detect_drift(base=...)``) to audit a
specific range of history.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

from . import gitutil
from .anchor import ANCHOR_DIR
from .model import Plan, Severity, Task, TaskStatus


@dataclass
class DriftItem:
    """A single drift observation."""

    rule: str
    message: str
    severity: Severity = Severity.WARNING
    task_uid: str = ""
    path: str = ""
    hint: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "message": self.message,
            "task_uid": self.task_uid,
            "path": self.path,
            "hint": self.hint,
        }


@dataclass
class DriftReport:
    """Aggregate result of a drift run."""

    items: List[DriftItem] = field(default_factory=list)
    changed: Dict[str, str] = field(default_factory=dict)
    claimed: Set[str] = field(default_factory=set)
    repo_root: str = ""
    head: str = ""
    branch: str = ""
    git_available: bool = False
    settled: bool = False

    @property
    def clean(self) -> bool:
        """Whether no drift was observed."""
        return not self.items

    def counts(self) -> Dict[str, int]:
        """Drift item counts grouped by severity."""
        out = {"info": 0, "warning": 0, "error": 0}
        for item in self.items:
            out[item.severity.value] += 1
        return out

    def to_dict(self) -> Dict[str, object]:
        return {
            "git_available": self.git_available,
            "repo_root": self.repo_root,
            "head": self.head,
            "branch": self.branch,
            "settled": self.settled,
            "changed_files": sorted(self.changed.keys()),
            "claimed_files": sorted(self.claimed),
            "counts": self.counts(),
            "clean": self.clean,
            "items": [i.to_dict() for i in self.items],
        }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def detect_drift(
    plan: Plan,
    *,
    repo: Optional[str] = None,
    base: str = "HEAD",
    include_untracked: bool = True,
    ignore_paths: Optional[Sequence[str]] = None,
) -> DriftReport:
    """Compare a plan against the actual repository state.

    Args:
        plan: Parsed plan document.
        repo: Repository path.  Defaults to the directory of the plan file.
        base: Git revision used as the comparison baseline.
        include_untracked: Whether untracked files count as changes.
        ignore_paths: Path substrings to skip (e.g. ``.lock``, ``dist/``).

    Returns:
        A :class:`DriftReport`.  When Git is unavailable the report carries a
        single ``DF006``-style informational entry and ``git_available=False``.
    """
    root = repo or (os.path.dirname(os.path.abspath(plan.path)) if plan.path else ".")
    if not os.path.isdir(root):
        root = "."

    report = DriftReport(repo_root=root)

    # The plan file itself (and the anchor store next to it) are bookkeeping,
    # never "work" — counting them would make every run report a silent change.
    bookkeeping = list(ignore_paths or [])
    if plan.path:
        bookkeeping.append(os.path.basename(plan.path))
    bookkeeping.append(ANCHOR_DIR + "/")

    if not gitutil.is_repo(root):
        report.git_available = False
        open_tasks = [t for t in plan.all_tasks() if t.status.is_open]
        report.items.append(
            DriftItem(
                rule="DF000",
                message="git unavailable — drift detection skipped",
                severity=Severity.INFO,
                hint="run inside a git work tree to enable drift verification",
            )
        )
        if open_tasks:
            report.items.append(
                DriftItem(
                    rule="DF006",
                    message="%d task(s) remain open but no repository state could be verified"
                    % len(open_tasks),
                    severity=Severity.INFO,
                )
            )
        return report

    report.git_available = True
    root = gitutil.repo_root(root) or root
    report.repo_root = root
    report.head = gitutil.head_commit(root)
    report.branch = gitutil.current_branch(root)

    changed = gitutil.changed_files(root, base=base, include_untracked=include_untracked)
    if bookkeeping:
        changed = {
            p: s
            for p, s in changed.items()
            if not any(token in gitutil.norm(p) for token in bookkeeping)
        }
    report.changed = changed

    normalised = {gitutil.norm(p): s for p, s in changed.items()}
    symbols_by_file = gitutil.changed_symbols(root, base=base)
    normalised_symbols = {gitutil.norm(k): v for k, v in symbols_by_file.items()}

    tasks = plan.all_tasks()

    # Build the set of files claimed by *any* task, resolving basename refs.
    claimed: Dict[str, str] = {}  # normalised path -> task uid
    for t in tasks:
        for ref in t.refs:
            target = _resolve_ref(ref, normalised)
            if target:
                claimed.setdefault(target, t.uid)
                report.claimed.add(target)

    # -- DF001 / DF003 / DF005 --------------------------------------------- #
    #
    # An empty change window (nothing uncommitted) is a *settled* work tree:
    # per-task "you said done but nothing changed" verdicts would all fire and
    # all be meaningless, because the work already landed in an earlier commit.
    # In that mode we emit one aggregated informational verdict instead.
    settled = not changed
    report.settled = settled
    unverifiable: List[Task] = []

    for t in tasks:
        if not t.refs:
            continue
        resolved = [(ref, _resolve_ref(ref, normalised)) for ref in t.refs]
        touched = [target for _, target in resolved if target]

        if t.status is TaskStatus.DONE and not touched:
            if settled:
                unverifiable.append(t)
                continue
            report.items.append(
                DriftItem(
                    rule="DF001",
                    message="task %r is marked done but none of its files changed: %s"
                    % (t.title, ", ".join(t.refs)),
                    severity=Severity.ERROR,
                    task_uid=t.uid,
                    path=t.refs[0] if t.refs else "",
                    hint="revert the checkbox to `[ ]` or commit the actual change",
                )
            )
            continue

        if t.status is TaskStatus.DONE:
            for ref, target in resolved:
                if target is None:
                    report.items.append(
                        DriftItem(
                            rule="DF005",
                            message="task %r references %r which Git reports as unchanged"
                            % (t.title, ref),
                            severity=Severity.WARNING,
                            task_uid=t.uid,
                            path=ref,
                            hint="check the path spelling — an untracked rename is a common cause",
                        )
                    )

        for target in touched:
            if t.symbols:
                present = set(normalised_symbols.get(target, []))
                present |= _symbols_in_file(os.path.join(root, target))
                missing = [s for s in t.symbols if s not in present]
                if missing and t.status is TaskStatus.DONE:
                    report.items.append(
                        DriftItem(
                            rule="DF003",
                            message="task %r claims symbol(s) %s but the diff for %s does not add them"
                            % (t.title, ", ".join(missing), target),
                            severity=Severity.WARNING,
                            task_uid=t.uid,
                            path=target,
                            hint="the symbol may already exist — verify before trusting the checkbox",
                        )
                    )

    if settled and unverifiable:
        preview = ", ".join(repr(t.title) for t in unverifiable[:3])
        if len(unverifiable) > 3:
            preview += ", …"
        report.items.append(
            DriftItem(
                rule="DF001",
                message="%d done task(s) could not be verified — no uncommitted changes in the work tree (%s)"
                % (len(unverifiable), preview),
                severity=Severity.INFO,
                hint="the change window is empty, so drift is not decidable; the work may already be "
                "committed — re-run with --base <rev> to audit a specific range of history",
            )
        )

    # -- DF002 silent change ------------------------------------------------ #
    for path in sorted(normalised):
        if path in claimed:
            continue
        report.items.append(
            DriftItem(
                rule="DF002",
                message="%s changed but no task claims it" % path,
                severity=Severity.INFO,
                path=path,
                hint="add `@%s` to the responsible task, or revert the stray edit" % path,
            )
        )

    # -- DF004 scope creep -------------------------------------------------- #
    open_refs: Set[str] = set()
    for t in tasks:
        if t.status.is_open:
            for ref in t.refs:
                target = _resolve_ref(ref, normalised)
                if target:
                    open_refs.add(target)
    done_only: Dict[str, str] = {}
    for t in tasks:
        if t.status is TaskStatus.DONE:
            for ref in t.refs:
                target = _resolve_ref(ref, normalised)
                if target:
                    done_only.setdefault(target, t.uid)
    for path, uid in sorted(done_only.items()):
        if path in open_refs:
            report.items.append(
                DriftItem(
                    rule="DF004",
                    message="%s is claimed by closed task %s and still touched by an open task"
                    % (path, uid),
                    severity=Severity.INFO,
                    task_uid=uid,
                    path=path,
                    hint="split the file scope across tasks to avoid conflicting edits",
                )
            )

    # -- DF006 no progress -------------------------------------------------- #
    if not changed and any(t.status.is_open for t in tasks):
        report.items.append(
            DriftItem(
                rule="DF006",
                message="no file changes detected while tasks remain open",
                severity=Severity.INFO,
                hint="the session may have produced no diff — verify before resuming",
            )
        )

    report.items.sort(key=lambda i: (-i.severity.rank, i.rule, i.path))
    return report


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #

def _resolve_ref(ref: str, changed: Dict[str, str]) -> Optional[str]:
    """Match a plan reference against the changed-file map.

    Exact match wins; otherwise a *unique* basename match is accepted.
    """
    norm_ref = gitutil.norm(ref)
    if norm_ref in changed:
        return norm_ref
    return gitutil.basename_match(ref, changed)


def _symbols_in_file(path: str) -> Set[str]:
    """Identifiers present in the *current* content of ``path``.

    ``git diff`` only reports the lines that actually moved, so a symbol that
    already existed (or that landed in an earlier commit) would otherwise look
    "missing".  Reading the file closes that gap without needing a parser.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return set()
    return {m for m in _IDENT_RE.findall(text) if len(m) > 2}


_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")
