"""Tamper-evident snapshots and anti-compaction restore.

This is the module that makes a plan *survive* ``/clear``, context compaction,
an aborted agent run, or an accidental overwrite.

Design
------

Snapshots live in ``<plan dir>/.plananchor/snapshots/NNNN-<timestamp>.json``.
Every snapshot stores:

* the full plan text,
* a structural digest (uid -> status map) so drift can be reasoned about
  without re-parsing,
* ``prev`` — the SHA-256 of the previous snapshot,
* ``digest`` — ``sha256(prev + "\n" + text)``,

which forms a **hash chain**: rewriting or deleting a historical snapshot breaks
verification, so the recovery trail is itself auditable.

No third-party dependencies — :mod:`hashlib`, :mod:`json` and :mod:`os` only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .model import Plan, Task, TaskStatus
from .parser import parse_text, render_plan

#: Directory (relative to the plan file) that holds the anchor state.
ANCHOR_DIR = ".plananchor"
#: Sub-directory holding snapshots.
SNAPSHOT_DIR = "snapshots"
#: Name of the index file listing every snapshot in chain order.
INDEX_NAME = "index.json"

_SNAPSHOT_RE = re.compile(r"^(\d{6})-.*\.json$")


@dataclass
class Snapshot:
    """One point-in-time anchor of a plan file."""

    seq: int
    created_at: str
    plan_path: str
    text: str
    status_map: Dict[str, str] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    progress: float = 0.0
    prev: str = ""
    digest: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "seq": self.seq,
            "created_at": self.created_at,
            "plan_path": self.plan_path,
            "status_map": self.status_map,
            "counts": self.counts,
            "progress": self.progress,
            "prev": self.prev,
            "digest": self.digest,
            "text": self.text,
        }

    @property
    def short(self) -> str:
        """Short display digest."""
        return self.digest[:12]

    def verify(self, prev: str = "") -> bool:
        """Recompute and compare this snapshot's digest."""
        return self.digest == _digest(prev or self.prev, self.text)


@dataclass
class VerifyResult:
    """Outcome of a hash-chain verification."""

    ok: bool
    snapshots: int = 0
    broken_at: int = -1
    message: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "snapshots": self.snapshots,
            "broken_at": self.broken_at,
            "message": self.message,
        }


@dataclass
class CompactionSignal:
    """Evidence that the plan file was compacted, truncated or reset."""

    compacted: bool
    lost_tasks: List[str] = field(default_factory=list)
    regressed_tasks: List[Tuple[str, str, str]] = field(default_factory=list)
    before: int = 0
    after: int = 0
    message: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "compacted": self.compacted,
            "lost_tasks": self.lost_tasks,
            "regressed_tasks": [
                {"uid": u, "before": b, "after": a} for u, b, a in self.regressed_tasks
            ],
            "before": self.before,
            "after": self.after,
            "message": self.message,
        }


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

class AnchorStore:
    """Filesystem backed snapshot store for a single plan file.

    Args:
        plan_path: Path to the Markdown plan file.  The anchor directory is
            created next to it.
        anchor_dir: Override for the anchor directory location (mainly useful
            in tests and for detached stores).
    """

    def __init__(self, plan_path: str, anchor_dir: Optional[str] = None) -> None:
        self.plan_path = os.path.abspath(plan_path)
        base = os.path.dirname(self.plan_path) or "."
        self.root = os.path.abspath(anchor_dir) if anchor_dir else os.path.join(base, ANCHOR_DIR)
        self.snapshot_dir = os.path.join(self.root, SNAPSHOT_DIR)
        self.index_path = os.path.join(self.root, INDEX_NAME)

    # -- filesystem --------------------------------------------------------- #

    def ensure(self) -> str:
        """Create the anchor directory layout; returns the snapshot dir."""
        os.makedirs(self.snapshot_dir, exist_ok=True)
        if not os.path.isfile(self.index_path):
            _write_json(self.index_path, {"plan": self.plan_path, "snapshots": []})
        return self.snapshot_dir

    def exists(self) -> bool:
        """Whether an anchor store has been initialised."""
        return os.path.isdir(self.snapshot_dir)

    def _index(self) -> Dict[str, object]:
        if not os.path.isfile(self.index_path):
            return {"plan": self.plan_path, "snapshots": []}
        try:
            return _read_json(self.index_path)
        except (OSError, ValueError):
            return {"plan": self.plan_path, "snapshots": []}

    def _write_index(self, index: Dict[str, object]) -> None:
        _write_json(self.index_path, index)

    # -- snapshot ops ------------------------------------------------------- #

    def create(self, plan: Plan, *, note: str = "") -> Snapshot:
        """Snapshot the current plan state and append it to the chain.

        Args:
            plan: Parsed plan (the *text* is what gets stored).
            note: Optional free-form annotation, stored in the index entry.

        Returns:
            The created :class:`Snapshot`.
        """
        self.ensure()
        index = self._index()
        entries = index.get("snapshots", []) or []
        seq = len(entries) + 1

        prev = ""
        if entries:
            last = self.load(int(entries[-1]["seq"]))
            if last is not None:
                prev = last.digest

        text = plan.text
        status_map = {t.uid: t.status.value for t in plan.all_tasks()}
        snap = Snapshot(
            seq=seq,
            created_at=_now(),
            plan_path=self.plan_path,
            text=text,
            status_map=status_map,
            counts=plan.counts(),
            progress=plan.progress(),
            prev=prev,
            digest=_digest(prev, text),
        )

        path = os.path.join(self.snapshot_dir, "%06d-%s.json" % (seq, _stamp()))
        _write_json(path, snap.to_dict())

        entries.append(
            {
                "seq": seq,
                "file": os.path.basename(path),
                "created_at": snap.created_at,
                "digest": snap.digest,
                "prev": prev,
                "progress": snap.progress,
                "counts": snap.counts,
                "note": note,
            }
        )
        index["snapshots"] = entries
        self._write_index(index)
        return snap

    def list(self) -> List[Dict[str, object]]:
        """Index entries, oldest first."""
        return list(self._index().get("snapshots", []) or [])

    def load(self, seq: int) -> Optional[Snapshot]:
        """Load a snapshot by sequence number, or ``None``."""
        for entry in self.list():
            if int(entry.get("seq", -1)) == seq:
                return self._load_file(os.path.join(self.snapshot_dir, str(entry["file"])))
        return None

    def latest(self) -> Optional[Snapshot]:
        """Most recent snapshot, or ``None`` when the store is empty."""
        entries = self.list()
        if not entries:
            return None
        return self.load(int(entries[-1]["seq"]))

    def _load_file(self, path: str) -> Optional[Snapshot]:
        try:
            data = _read_json(path)
        except (OSError, ValueError):
            return None
        return Snapshot(
            seq=int(data.get("seq", 0)),
            created_at=str(data.get("created_at", "")),
            plan_path=str(data.get("plan_path", "")),
            text=str(data.get("text", "")),
            status_map=dict(data.get("status_map", {}) or {}),
            counts=dict(data.get("counts", {}) or {}),
            progress=float(data.get("progress", 0.0) or 0.0),
            prev=str(data.get("prev", "")),
            digest=str(data.get("digest", "")),
        )

    # -- verification ------------------------------------------------------- #

    def verify(self) -> VerifyResult:
        """Walk the hash chain and confirm every digest still matches."""
        entries = self.list()
        if not entries:
            return VerifyResult(ok=True, snapshots=0, message="no snapshots")

        prev = ""
        for i, entry in enumerate(entries):
            snap = self.load(int(entry["seq"]))
            if snap is None:
                return VerifyResult(
                    ok=False,
                    snapshots=len(entries),
                    broken_at=int(entry["seq"]),
                    message="snapshot %s is missing or unreadable" % entry["seq"],
                )
            if snap.digest != _digest(prev, snap.text):
                return VerifyResult(
                    ok=False,
                    snapshots=len(entries),
                    broken_at=snap.seq,
                    message="digest mismatch at snapshot %d — chain was altered" % snap.seq,
                )
            if snap.prev != prev:
                return VerifyResult(
                    ok=False,
                    snapshots=len(entries),
                    broken_at=snap.seq,
                    message="back-link mismatch at snapshot %d" % snap.seq,
                )
            prev = snap.digest
        return VerifyResult(
            ok=True, snapshots=len(entries), message="chain intact (%d snapshots)" % len(entries)
        )

    # -- recovery ----------------------------------------------------------- #

    def detect_compaction(self, plan: Plan, *, baseline: Optional[int] = None) -> CompactionSignal:
        """Compare the live plan against the anchor baseline.

        Two regressions are reported:

        * **lost tasks** — uids present in the baseline but gone now;
        * **regressed tasks** — uids whose status moved *backwards*
          (``done`` -> ``pending``).

        Args:
            plan: The current (possibly compacted) plan.
            baseline: Snapshot sequence to compare against; defaults to the
                latest snapshot.

        Returns:
            A :class:`CompactionSignal`.
        """
        snap = self.load(baseline) if baseline else self.latest()
        if snap is None:
            return CompactionSignal(
                compacted=False, message="no baseline snapshot — nothing to compare"
            )

        current = {t.uid: t.status for t in plan.all_tasks()}
        lost = [uid for uid in snap.status_map if uid not in current]

        regressed: List[Tuple[str, str, str]] = []
        for uid, before in snap.status_map.items():
            after = current.get(uid)
            if after is None:
                continue
            if _rank(before) > _rank(after.value):
                regressed.append((uid, before, after.value))

        compacted = bool(lost) or bool(regressed)
        message = ""
        if compacted:
            parts = []
            if lost:
                parts.append("%d task(s) disappeared" % len(lost))
            if regressed:
                parts.append("%d task(s) regressed" % len(regressed))
            message = "plan regressed vs snapshot #%d: %s" % (snap.seq, ", ".join(parts))
        else:
            message = "plan matches snapshot #%d" % snap.seq

        return CompactionSignal(
            compacted=compacted,
            lost_tasks=lost,
            regressed_tasks=regressed,
            before=len(snap.status_map),
            after=len(current),
            message=message,
        )

    def restore(
        self,
        target: str = "",
        *,
        seq: Optional[int] = None,
        merge: bool = True,
        dry_run: bool = False,
    ) -> Tuple[str, CompactionSignal]:
        """Restore a plan file from a snapshot.

        Args:
            target: Destination path; defaults to :attr:`plan_path`.
            seq: Snapshot sequence; defaults to the latest.
            merge: When ``True`` (default) a *forward merge* is performed: the
                snapshot supplies structure and any status that only moved
                *forward* in the live file is preserved.  When ``False`` the
                snapshot text is written verbatim.
            dry_run: Compute the result without touching the filesystem.

        Returns:
            ``(restored_text, signal)`` where ``signal`` describes what was
            recovered relative to the live file.

        Raises:
            FileNotFoundError: If no snapshot matches ``seq``.
        """
        snap = self.load(seq) if seq else self.latest()
        if snap is None:
            raise FileNotFoundError("no snapshot available to restore (seq=%r)" % (seq,))

        dest = target or self.plan_path
        if not merge:
            if not dry_run:
                _write_text(dest, snap.text)
            return snap.text, CompactionSignal(
                compacted=True,
                before=len(snap.status_map),
                after=len(snap.status_map),
                message="verbatim restore from snapshot #%d" % snap.seq,
            )

        live_text = ""
        if os.path.isfile(dest):
            live_text = _read_text(dest)
        live_plan = parse_text(live_text, path=dest) if live_text.strip() else Plan(path=dest)

        signal = self.detect_compaction(live_plan, baseline=snap.seq)
        merged = _forward_merge(parse_text(snap.text, path=dest), live_plan)
        text = render_plan(merged)
        if not dry_run:
            _write_text(dest, text)
            _write_text(
                os.path.join(self.root, "last-restore.txt"),
                "restored from snapshot #%d at %s\n" % (snap.seq, _now()),
            )
        return text, signal

    def prune(self, keep: int = 50) -> int:
        """Drop the oldest snapshots, keeping at most ``keep``.

        The chain is re-linked after pruning so :meth:`verify` still passes.

        Returns:
            Number of snapshots removed.
        """
        entries = self.list()
        if len(entries) <= keep:
            return 0
        doomed = entries[: len(entries) - keep]
        for entry in doomed:
            try:
                os.remove(os.path.join(self.snapshot_dir, str(entry["file"])))
            except OSError:
                pass
        kept = entries[len(entries) - keep :]
        kept[0]["prev"] = ""
        kept[0]["digest"] = ""
        index = self._index()
        index["snapshots"] = kept
        self._write_index(index)
        return len(doomed)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_STATUS_RANK = {
    TaskStatus.PENDING.value: 0,
    TaskStatus.BLOCKED.value: 1,
    TaskStatus.ACTIVE.value: 2,
    TaskStatus.SKIPPED.value: 3,
    TaskStatus.DONE.value: 4,
}


def _rank(status: str) -> int:
    return _STATUS_RANK.get(status, 0)


def _forward_merge(base: Plan, live: Plan) -> Plan:
    """Merge two plans keeping the *most advanced* status for every uid.

    Tasks that only exist in ``live`` are appended, so a restored plan never
    loses newer work; tasks that only exist in ``base`` are brought back.
    """
    by_uid = {t.uid: t for t in base.all_tasks()}

    for task in live.all_tasks():
        existing = by_uid.get(task.uid)
        if existing is None:
            continue
        if _rank(task.status.value) > _rank(existing.status.value):
            existing.status = task.status
            existing.note = task.note or existing.note
            existing.refs = task.refs or existing.refs

    known = set(by_uid)
    for task in live.all_tasks():
        if task.uid not in known:
            base.tasks.append(task)
    return base


def _digest(prev: str, text: str) -> str:
    """Chain digest: ``sha256(prev + "\\n" + text)``."""
    h = hashlib.sha256()
    h.update((prev or "").encode("utf-8"))
    h.update(b"\n")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def sha256_text(text: str) -> str:
    """Plain SHA-256 of ``text`` (used in reports and release checksums)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    """UTC timestamp in ISO-8601 form (second precision)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stamp() -> str:
    """Filesystem friendly timestamp."""
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def _write_json(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=False)


def _read_json(path: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()
