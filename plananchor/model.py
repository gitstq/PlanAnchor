"""Core data model for PlanAnchor.

Everything here is a plain, immutable-ish Python object built on
:mod:`dataclasses` so that the whole library stays dependency-free and
trivially serialisable to JSON.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #

class TaskStatus(str, enum.Enum):
    """Lifecycle status of a single plan task."""

    PENDING = "pending"      # ``- [ ]``  not started yet
    ACTIVE = "active"        # ``- [~]``  currently in progress
    DONE = "done"            # ``- [x]``  completed
    SKIPPED = "skipped"      # ``- [-]``  intentionally skipped
    BLOCKED = "blocked"      # ``- [!]``  blocked by an external dependency

    @property
    def glyph(self) -> str:
        """The Markdown checkbox glyph that represents this status."""
        return _STATUS_GLYPH[self]

    @classmethod
    def from_glyph(cls, ch: str) -> "TaskStatus":
        """Map a checkbox glyph back to a :class:`TaskStatus`.

        Both ``x`` and ``X`` mean *done*, matching GitHub Flavored Markdown.
        """
        try:
            return _GLYPH_STATUS[ch]
        except KeyError:
            if ch == "X":
                return cls.DONE
            raise ValueError("unknown task status glyph: %r" % (ch,)) from None

    @property
    def is_open(self) -> bool:
        """Whether the task still consumes agent attention."""
        return self in (TaskStatus.PENDING, TaskStatus.ACTIVE, TaskStatus.BLOCKED)


_STATUS_GLYPH: Dict["TaskStatus", str] = {
    TaskStatus.PENDING: " ",
    TaskStatus.ACTIVE: "~",
    TaskStatus.DONE: "x",
    TaskStatus.SKIPPED: "-",
    TaskStatus.BLOCKED: "!",
}

_GLYPH_STATUS: Dict[str, "TaskStatus"] = {v: k for k, v in _STATUS_GLYPH.items()}


class Severity(str, enum.Enum):
    """Severity of a finding raised by any PlanAnchor analyser."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def rank(self) -> int:
        """Numeric rank used for sorting and CI thresholding."""
        return _SEVERITY_RANK[self]


_SEVERITY_RANK: Dict["Severity", int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
}


# --------------------------------------------------------------------------- #
# Plan entities
# --------------------------------------------------------------------------- #

@dataclass
class Task:
    """A single actionable item inside a plan file.

    Attributes:
        uid: Stable identifier.  Either the numeric outline id parsed from the
            task text (``1.2.3``) or a positional fallback (``L12``).
        title: Human readable title with inline markers stripped out.
        status: Lifecycle status.
        depth: Zero based nesting depth in the Markdown tree.
        line: 1-based line number in the source file.
        raw: The original, unmodified source line.
        section: Nearest enclosing Markdown heading (without ``#`` markers).
        refs: File paths referenced from the task text (``@a/b.py`` or
            backtick-quoted paths).
        symbols: Code symbols referenced from the task text (``#func``).
        owner: Optional ``@owner``-style assignment, when distinguishable from
            a file reference.
        note: Optional free-form note captured after ``(note: ...)``.
        children: Direct sub tasks.
    """

    uid: str
    title: str
    status: TaskStatus = TaskStatus.PENDING
    depth: int = 0
    line: int = 0
    raw: str = ""
    section: str = ""
    refs: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)
    owner: str = ""
    note: str = ""
    children: List["Task"] = field(default_factory=list)

    # -- traversal helpers ------------------------------------------------- #

    def iter_tasks(self) -> List["Task"]:
        """Return ``self`` plus every descendant in document order."""
        out: List["Task"] = [self]
        for child in self.children:
            out.extend(child.iter_tasks())
        return out

    @property
    def descendants(self) -> List["Task"]:
        """Every descendant of this task (excluding ``self``)."""
        out: List["Task"] = []
        for child in self.children:
            out.extend(child.iter_tasks())
        return out

    def rollup(self) -> Dict[str, int]:
        """Aggregate status counts over the whole sub-tree."""
        counts = {s.value: 0 for s in TaskStatus}
        for t in self.iter_tasks():
            counts[t.status.value] += 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        """JSON friendly representation."""
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Plan:
    """A parsed plan document.

    Attributes:
        path: Source file path (``""`` when parsed from a string).
        title: First level-one heading, if any.
        sections: All headings in document order.
        tasks: Top level tasks (flatten the tree with :meth:`all_tasks`).
        front_matter: ``key: value`` pairs from an optional YAML-ish header.
        text: The full source text.
    """

    path: str = ""
    title: str = ""
    sections: List[str] = field(default_factory=list)
    headings: List[Tuple[int, str]] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)
    front_matter: Dict[str, str] = field(default_factory=dict)
    text: str = ""

    # -- traversal helpers ------------------------------------------------- #

    def all_tasks(self) -> List[Task]:
        """Every task in the document, flattened in document order."""
        out: List[Task] = []
        for t in self.tasks:
            out.extend(t.iter_tasks())
        return out

    def counts(self) -> Dict[str, int]:
        """Status counts over the entire document."""
        counts = {s.value: 0 for s in TaskStatus}
        for t in self.all_tasks():
            counts[t.status.value] += 1
        return counts

    def progress(self, precision: int = 1) -> float:
        """Completion ratio in percent.

        ``done`` counts as 1.0, ``skipped`` does not inflate the ratio but is
        excluded from the denominator — a skipped task is *closed*, not done.
        """
        counts = self.counts()
        total = sum(counts.values())
        if total == 0:
            return 0.0
        return round(counts["done"] * 100.0 / total, precision)

    def find(self, uid: str) -> Optional[Task]:
        """Look up a task by its uid."""
        for t in self.all_tasks():
            if t.uid == uid:
                return t
        return None

    def to_dict(self) -> Dict[str, Any]:
        """JSON friendly representation."""
        return {
            "path": self.path,
            "title": self.title,
            "sections": self.sections,
            "headings": [{"level": lv, "title": t} for lv, t in self.headings],
            "front_matter": self.front_matter,
            "counts": self.counts(),
            "progress": self.progress(),
            "tasks": [t.to_dict() for t in self.tasks],
        }


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    """A single diagnostic produced by any analyser.

    Attributes:
        rule: Stable rule identifier, e.g. ``PA002``.
        severity: How bad it is.
        message: Human readable description.
        line: 1-based source line, ``0`` when not line specific.
        task_uid: Uid of the offending task, when applicable.
        hint: Actionable remediation advice.
    """

    rule: str
    message: str
    severity: Severity = Severity.WARNING
    line: int = 0
    task_uid: str = ""
    hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """JSON friendly representation."""
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "message": self.message,
            "line": self.line,
            "task_uid": self.task_uid,
            "hint": self.hint,
        }

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        loc = "line %d" % self.line if self.line else "plan"
        return "[%s] %s (%s): %s" % (
            self.severity.value.upper(),
            self.rule,
            loc,
            self.message,
        )
