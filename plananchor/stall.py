"""Stall, churn and abandonment detection.

A plan that has not *moved* is the strongest signal that an agent session died.
PlanAnchor infers movement from the snapshot chain written by
:mod:`plananchor.anchor`, so stall detection needs at least two snapshots — with
fewer it degrades to a purely structural analysis of the live file.

Stall classes
-------------

``ST001`` stuck-active      — a task stayed ``active`` across N snapshots
``ST002`` churn             — a task flipped done -> open -> done
``ST003`` blocked-cascade   — a blocked task gates downstream work
``ST004`` no-movement       — overall progress did not change across snapshots
``ST005`` abandoned-front   — the first open task is still untouched
``ST006`` deep-pending      — a long run of pending tasks with no active anchor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .anchor import AnchorStore, Snapshot
from .model import Finding, Plan, Severity, Task, TaskStatus


#: How many consecutive snapshots a task may stay ``active`` before ST001 fires.
DEFAULT_STUCK_THRESHOLD = 3
#: Minimum snapshots required before historical rules are meaningful.
MIN_HISTORY = 2


@dataclass
class StallReport:
    """Aggregate stall analysis."""

    items: List[Finding] = field(default_factory=list)
    snapshots: int = 0
    progress_curve: List[float] = field(default_factory=list)
    stuck_tasks: List[str] = field(default_factory=list)
    churn_tasks: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.items

    def to_dict(self) -> Dict[str, object]:
        return {
            "snapshots": self.snapshots,
            "progress_curve": self.progress_curve,
            "stuck_tasks": self.stuck_tasks,
            "churn_tasks": self.churn_tasks,
            "clean": self.clean,
            "items": [i.to_dict() for i in self.items],
        }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def detect_stalls(
    plan: Plan,
    store: Optional[AnchorStore] = None,
    *,
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD,
) -> StallReport:
    """Detect stalled or oscillating work.

    Args:
        plan: The current plan.
        store: Optional anchor store supplying snapshot history.
        stuck_threshold: Consecutive snapshots a task may stay ``active``.

    Returns:
        A :class:`StallReport`.
    """
    report = StallReport()

    if store is not None and store.exists():
        history = _load_history(store)
        report.snapshots = len(history)
        report.progress_curve = [s.progress for s in history]
        if len(history) >= MIN_HISTORY:
            report.items.extend(_rule_stuck_active(plan, history, stuck_threshold))
            report.items.extend(_rule_churn(plan, history))
            report.items.extend(_rule_no_movement(history))

    report.items.extend(_rule_blocked_cascade(plan))
    report.items.extend(_rule_abandoned_front(plan))
    report.items.extend(_rule_deep_pending(plan))

    report.stuck_tasks = sorted({i.task_uid for i in report.items if i.rule == "ST001" and i.task_uid})
    report.churn_tasks = sorted({i.task_uid for i in report.items if i.rule == "ST002" and i.task_uid})
    report.items.sort(key=lambda f: (-f.severity.rank, f.rule, f.line))
    return report


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #

def _load_history(store: AnchorStore) -> List[Snapshot]:
    """Load every snapshot in sequence order, skipping unreadable ones."""
    snaps: List[Snapshot] = []
    for entry in store.list():
        snap = store.load(int(entry["seq"]))
        if snap is not None:
            snaps.append(snap)
    return snaps


def _rule_stuck_active(
    plan: Plan, history: Sequence[Snapshot], threshold: int
) -> List[Finding]:
    """ST001 — a task that has been ``active`` for too many snapshots."""
    out: List[Finding] = []
    tail = list(history[-threshold:])
    if len(tail) < threshold:
        return out

    counts: Dict[str, int] = {}
    for snap in tail:
        for uid, status in snap.status_map.items():
            if status == TaskStatus.ACTIVE.value:
                counts[uid] = counts.get(uid, 0) + 1

    for uid, hits in counts.items():
        if hits < threshold:
            continue
        task = plan.find(uid)
        if task is None or task.status is not TaskStatus.ACTIVE:
            continue
        out.append(
            Finding(
                rule="ST001",
                severity=Severity.WARNING,
                message="task %r has been in progress for %d consecutive snapshots"
                % (task.title, hits),
                line=task.line,
                task_uid=uid,
                hint="split it into smaller steps, or mark it blocked with a reason",
            )
        )
    return out


def _rule_churn(plan: Plan, history: Sequence[Snapshot]) -> List[Finding]:
    """ST002 — a task that flipped backwards and forwards again."""
    out: List[Finding] = []
    series: Dict[str, List[str]] = {}
    for snap in history:
        for uid, status in snap.status_map.items():
            series.setdefault(uid, []).append(status)

    for uid, seq in series.items():
        if len(seq) < 3:
            continue
        regressions = 0
        recoveries = 0
        for i in range(1, len(seq)):
            if _rank(seq[i]) < _rank(seq[i - 1]):
                regressions += 1
            elif regressions and _rank(seq[i]) > _rank(seq[i - 1]):
                recoveries += 1
        if regressions >= 1 and recoveries >= 1:
            task = plan.find(uid)
            out.append(
                Finding(
                    rule="ST002",
                    severity=Severity.WARNING,
                    message="task %r oscillated %d time(s) across %d snapshots"
                    % (task.title if task else uid, regressions, len(seq)),
                    line=task.line if task else 0,
                    task_uid=uid,
                    hint="the acceptance criterion is ambiguous — restate it explicitly",
                )
            )
    return out


_RANK = {
    TaskStatus.PENDING.value: 0,
    TaskStatus.BLOCKED.value: 1,
    TaskStatus.ACTIVE.value: 2,
    TaskStatus.SKIPPED.value: 3,
    TaskStatus.DONE.value: 4,
}


def _rank(status: str) -> int:
    return _RANK.get(status, 0)


def _rule_no_movement(history: Sequence[Snapshot]) -> List[Finding]:
    """ST004 — progress has not moved across the whole recorded history."""
    if len(history) < MIN_HISTORY:
        return []
    first, last = history[0], history[-1]
    if abs(last.progress - first.progress) < 1e-9 and len(history) >= 3:
        return [
            Finding(
                rule="ST004",
                severity=Severity.WARNING,
                message="progress stayed at %.1f%% across %d snapshots"
                % (last.progress, len(history)),
                hint="the session is producing snapshots but no completed work",
            )
        ]
    return []


def _rule_blocked_cascade(plan: Plan) -> List[Finding]:
    """ST003 — a blocked task that gates downstream work."""
    out: List[Finding] = []
    tasks = plan.all_tasks()
    for t in tasks:
        if t.status is not TaskStatus.BLOCKED:
            continue
        downstream = [c for c in t.descendants if c.status.is_open]
        if downstream:
            out.append(
                Finding(
                    rule="ST003",
                    severity=Severity.WARNING,
                    message="blocked task %r gates %d downstream task(s)"
                    % (t.title, len(downstream)),
                    line=t.line,
                    task_uid=t.uid,
                    hint="record the blocker and the unlock condition in `(blocked: ...)`",
                )
            )
    return out


def _rule_abandoned_front(plan: Plan) -> List[Finding]:
    """ST005 — the first open task is still untouched while later ones advance."""
    tasks = plan.all_tasks()
    open_tasks = [t for t in tasks if t.status.is_open]
    if not open_tasks:
        return []
    first = open_tasks[0]
    advanced_after = [
        t for t in tasks if t.status is TaskStatus.DONE and t.line > first.line
    ]
    if advanced_after and first.status is TaskStatus.PENDING:
        return [
            Finding(
                rule="ST005",
                severity=Severity.INFO,
                message="task %r is the first open item but %d later task(s) are already done"
                % (first.title, len(advanced_after)),
                line=first.line,
                task_uid=first.uid,
                hint="reorder the plan or close the skipped item with `[-]`",
            )
        ]
    return []


def _rule_deep_pending(plan: Plan) -> List[Finding]:
    """ST006 — no active anchor at all while plenty of work remains."""
    tasks = plan.all_tasks()
    open_tasks = [t for t in tasks if t.status.is_open]
    if len(open_tasks) < 3:
        return []
    if any(t.status is TaskStatus.ACTIVE for t in tasks):
        return []
    return [
        Finding(
            rule="ST006",
            severity=Severity.INFO,
            message="%d task(s) remain open but none is marked in progress"
            % len(open_tasks),
            line=open_tasks[0].line,
            task_uid=open_tasks[0].uid,
            hint="mark the next task `[~]` — a session without an anchor resumes blindly",
        )
    ]
