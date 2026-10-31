"""Markdown plan parser.

The parser is intentionally forgiving: real agent plan files are messy, mix
languages and use inconsistent indentation.  Rather than rejecting them,
PlanAnchor normalises them into a :class:`~plananchor.model.Task` tree and lets
:mod:`plananchor.validate` report the hygiene problems.

Supported checkbox glyphs (GFM plus the de-facto agent conventions)::

    - [ ]   pending       - [~]  active / in progress
    - [x]   done          - [X]  done
    - [-]   skipped       - [!]  blocked

Inline markers recognised inside a task title::

    @path/to/file.py      file reference
    `path/to/file.py`     file reference (backtick quoted)
    #symbol               code symbol reference
    @owner:               explicit owner assignment
    (note: ...)           free-form note
    (blocked: ...)        blocking reason
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from .model import Plan, Task, TaskStatus

# ``- [x] title`` — leading indentation is captured separately so that both
# space based (2/4) and tab based nesting styles work.
_TASK_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<bullet>[-*+])\s+\[(?P<glyph>[ xX~\-!])\]\s*(?P<body>.*)$"
)

_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.*?)\s*$")

# Numeric outline ids: ``1``, ``1.2``, ``1.2.3``, ``A1``, ``S2.1`` …
_UID_RE = re.compile(r"^(?P<uid>(?:\d+(?:\.\d+)*[a-zA-Z]?|[A-Za-z]\d+(?:\.\d+)*))(?:[\.\)、:：\s]|$)")

# ``@path/to/file.py`` — must look like a path (contains ``/`` or a dot-suffix)
_REF_RE = re.compile(r"@(?P<ref>[A-Za-z0-9_.\-/\\]+)")

# ``#symbol`` — a leading hash immediately followed by an identifier char
_SYMBOL_RE = re.compile(r"#(?P<sym>[A-Za-z_][A-Za-z0-9_]*)")

# ``(note: ...)`` / ``(blocked: ...)`` / ``(blocked by ...)``
_NOTE_RE = re.compile(r"\((?P<key>note|blocked(?:\s+by)?)\s*:\s*(?P<val>[^)]*)\)", re.IGNORECASE)

# ``(owner: alice)`` / ``@alice:``
_OWNER_RE = re.compile(r"\((?:owner|assignee)\s*:\s*(?P<owner>[^)]+)\)", re.IGNORECASE)

# Backtick quoted spans
_BACKTICK_RE = re.compile(r"`([^`]+)`")

# Front matter ``key: value`` lines fenced by ``---``
_FENCE_RE = re.compile(r"^\s*---+\s*$")

_INDENT_UNIT = 2


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def parse_file(path: str, encoding: str = "utf-8") -> Plan:
    """Parse a plan file from disk.

    Args:
        path: Filesystem path to the Markdown plan.
        encoding: Text encoding, defaults to UTF-8.  Falls back to UTF-8 with
            replacement characters when the file contains broken bytes.

    Returns:
        A populated :class:`~plananchor.model.Plan`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        OSError: If the file cannot be read.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError("plan file not found: %s" % path)
    with open(path, "r", encoding=encoding, errors="replace") as fh:
        text = fh.read()
    return parse_text(text, path=path)


def parse_text(text: str, path: str = "") -> Plan:
    """Parse plan content from a string.

    Args:
        text: Raw Markdown content.
        path: Optional origin path, stored on the plan for reporting.

    Returns:
        A populated :class:`~plananchor.model.Plan`.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    front_matter, body_start = _read_front_matter(lines)

    plan = Plan(path=path, text=text, front_matter=front_matter)

    # ``stack`` holds (depth, task) for the currently open ancestor chain.
    stack: List[Tuple[int, Task]] = []
    current_heading = ""
    seen_uids: Dict[str, int] = {}

    for idx, raw in enumerate(lines[body_start:], start=body_start + 1):
        line = raw.rstrip()
        if not line.strip():
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            current_heading = heading.group("title").strip()
            level = len(heading.group("hashes"))
            if not plan.title and level == 1:
                plan.title = current_heading
            plan.sections.append(current_heading)
            plan.headings.append((level, current_heading))
            # A new heading closes every open task branch.
            stack.clear()
            continue

        match = _TASK_RE.match(line)
        if not match:
            continue

        indent = _expand_indent(match.group("indent"))
        depth = indent // _INDENT_UNIT

        body = match.group("body")
        status = TaskStatus.from_glyph(match.group("glyph"))

        uid, title = _split_uid(body, seen_uids, idx)
        refs, symbols, note, owner = _extract_markers(body)
        title = _clean_title(title) or title

        task = Task(
            uid=uid,
            title=title,
            status=status,
            depth=depth,
            line=idx,
            raw=raw,
            section=current_heading,
            refs=refs,
            symbols=symbols,
            owner=owner,
            note=note,
        )

        while stack and stack[-1][0] >= depth:
            stack.pop()

        if stack:
            task.depth = stack[-1][0] + 1
            stack[-1][1].children.append(task)
        else:
            task.depth = 0
            plan.tasks.append(task)

        stack.append((task.depth, task))

    return plan


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #

def _expand_indent(indent: str) -> int:
    """Convert a raw indent string into a column count (tabs count as 4)."""
    return len(indent.replace("\t", "    "))


def _read_front_matter(lines: List[str]) -> Tuple[Dict[str, str], int]:
    """Extract a simple ``---`` fenced ``key: value`` header.

    Returns:
        ``(mapping, body_start_index)``.  ``body_start_index`` is 0 when no
        valid front matter block was found.
    """
    if not lines or not _FENCE_RE.match(lines[0] or ""):
        return {}, 0

    mapping: Dict[str, str] = {}
    end = -1
    for i in range(1, len(lines)):
        if _FENCE_RE.match(lines[i] or ""):
            end = i
            break
        if ":" in lines[i]:
            key, _, value = lines[i].partition(":")
            key = key.strip()
            if key:
                mapping[key] = value.strip()
    if end == -1:
        return {}, 0
    return mapping, end + 1


def _split_uid(body: str, seen: Dict[str, int], line_no: int) -> Tuple[str, str]:
    """Split a leading outline id off the task title.

    When the task has no outline id a positional fallback (``L12``) is used and
    registered in ``seen`` so later duplicates get a disambiguating suffix.
    """
    match = _UID_RE.match(body.strip())
    if match:
        uid = match.group("uid")
        title = body.strip()[match.end() :].strip()
    else:
        uid = "L%d" % line_no
        title = body.strip()

    if not title:
        title = uid

    seen[uid] = seen.get(uid, 0) + 1
    if seen[uid] > 1:
        uid = "%s#%d" % (uid, seen[uid])
    return uid, title


def _extract_markers(body: str) -> Tuple[List[str], List[str], str, str]:
    """Pull file refs, symbols, notes and owner out of a task body."""
    refs: List[str] = []
    symbols: List[str] = []
    notes: List[str] = []
    owner = ""

    # Backtick quoted spans are treated as file references when they look like
    # paths, and as symbols otherwise.
    for span in _BACKTICK_RE.findall(body):
        if _looks_like_path(span):
            refs.append(_clean_ref(span))
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", span.strip()):
            symbols.append(span.strip())

    for match in _REF_RE.finditer(body):
        ref = match.group("ref")
        if _looks_like_path(ref):
            refs.append(_clean_ref(ref))

    for match in _SYMBOL_RE.finditer(body):
        symbols.append(match.group("sym"))

    for match in _NOTE_RE.finditer(body):
        notes.append("%s: %s" % (match.group("key").lower().split()[0], match.group("val").strip()))

    owner_match = _OWNER_RE.search(body)
    if owner_match:
        owner = owner_match.group("owner").strip()

    # De-duplicate while preserving order.
    refs = _dedupe(refs)
    symbols = _dedupe(symbols)

    # A body such as ``(blocked: waiting on CI)`` should also flip the note.
    note = "; ".join(_dedupe(notes))
    return refs, symbols, note, owner


def _looks_like_path(value: str) -> bool:
    """Heuristic: does this token denote a file path?"""
    value = value.strip()
    if not value or len(value) > 260:
        return False
    if "/" in value or "\\" in value:
        return True
    return bool(re.search(r"\.[A-Za-z0-9]{1,10}$", value))


def _clean_ref(ref: str) -> str:
    """Normalise a file reference (strip quotes, punctuation, leading ``@``/``./``)."""
    ref = ref.strip().strip("`'\"")
    ref = ref.rstrip(".,;:")
    while ref.startswith("./"):
        ref = ref[2:]
    while ref.startswith("@"):
        ref = ref[1:]
    return ref


def _clean_title(body: str) -> str:
    """Strip inline PlanAnchor markers out of a task title.

    Keeps the human readable core: file references, symbols, ``(note: ...)``,
    ``(blocked: ...)`` and ``(owner: ...)`` markers are removed so that titles
    render cleanly in briefings and never duplicate the markers that
    :func:`render_plan` re-emits.
    """
    text = _NOTE_RE.sub("", body)
    text = _OWNER_RE.sub("", text)
    text = _REF_RE.sub("", text)
    text = _SYMBOL_RE.sub("", text)
    text = _BACKTICK_RE.sub(r"\1", text)
    text = re.sub(r"`\s*`", " ", text)  # drop empty backtick pairs left behind
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -–—:：")


def _dedupe(values: List[str]) -> List[str]:
    """Order preserving de-duplication."""
    out: List[str] = []
    seen = set()
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def render_plan(plan: Plan, indent_unit: int = 2) -> str:
    """Re-render a plan back to canonical Markdown.

    Useful after :func:`plananchor.anchor` restored a compacted file, or to
    normalise inconsistent indentation.

    Args:
        plan: The plan to render.
        indent_unit: Spaces per nesting level.

    Returns:
        Canonical Markdown text.
    """
    out: List[str] = []
    if plan.front_matter:
        out.append("---")
        for k, v in plan.front_matter.items():
            out.append("%s: %s" % (k, v))
        out.append("---")
        out.append("")

    if plan.title:
        out.append("# " + plan.title)
        out.append("")

    # Heading levels keyed by title, so a restored plan keeps its structure.
    levels: Dict[str, int] = {}
    for level, title in plan.headings:
        levels.setdefault(title, level)

    state = {"section": _NO_SECTION}

    def emit_heading(title: str) -> None:
        out.append("")
        out.append("%s %s" % ("#" * levels.get(title, 2), title))
        out.append("")

    def walk(tasks: List[Task], depth: int) -> None:
        for t in tasks:
            if t.section and t.section != state["section"]:
                state["section"] = t.section
                emit_heading(t.section)
            pad = " " * (depth * indent_unit)
            line = "%s- [%s] %s %s" % (pad, t.status.glyph, t.uid, t.title)
            for ref in t.refs:
                line += " `@%s`" % ref
            for sym in t.symbols:
                line += " #%s" % sym
            if t.owner:
                line += " (owner: %s)" % t.owner
            if t.note:
                line += " (%s)" % t.note
            out.append(line)
            walk(t.children, depth + 1)

    walk(plan.tasks, 0)
    return "\n".join(out).rstrip() + "\n"


_NO_SECTION = "\x00-no-section"
