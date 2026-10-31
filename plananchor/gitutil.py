"""Minimal Git integration — no third-party dependencies.

PlanAnchor shells out to ``git`` (which is a *system* tool, not a Python
dependency) and degrades gracefully when Git is unavailable or the directory is
not a repository: every function returns an empty result instead of raising, so
that drift detection can run on a bare plan file too.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple


class GitUnavailable(RuntimeError):
    """Raised only by :func:`require_git` when the caller insists on Git."""


def is_repo(path: str) -> bool:
    """Whether ``path`` lives inside a Git work tree."""
    code, out, _ = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path)
    return code == 0 and out.strip() == "true"


def repo_root(path: str) -> Optional[str]:
    """Absolute path of the enclosing work tree, or ``None``."""
    code, out, _ = _run(["git", "rev-parse", "--show-toplevel"], cwd=path)
    if code == 0 and out.strip():
        return out.strip()
    return None


def require_git(path: str) -> str:
    """Return the repo root or raise :class:`GitUnavailable`."""
    root = repo_root(path)
    if root is None:
        raise GitUnavailable("not inside a git work tree: %s" % path)
    return root


def changed_files(
    path: str,
    *,
    base: str = "HEAD",
    include_untracked: bool = True,
    staged: bool = True,
) -> Dict[str, str]:
    """Collect files changed relative to ``base``.

    Args:
        path: Any path inside the repository.
        base: Revision to compare against (default ``HEAD``).
        include_untracked: Whether untracked files count as "changed".
        staged: Whether staged (index) changes are included.

    Returns:
        Mapping of repo-relative path -> status letter, where the letter is one
        of ``A`` (added), ``M`` (modified), ``D`` (deleted), ``R`` (renamed),
        ``U`` (untracked).
    """
    changed: Dict[str, str] = {}

    code, out, _ = _run(["git", "diff", "--name-status", "--no-renames", base], cwd=path)
    if code == 0:
        for line in out.splitlines():
            entry = _parse_name_status(line)
            if entry:
                changed[entry[0]] = entry[1]

    if staged:
        code, out, _ = _run(["git", "diff", "--name-status", "--no-renames", "--cached"], cwd=path)
        if code == 0:
            for line in out.splitlines():
                entry = _parse_name_status(line)
                if entry:
                    changed[entry[0]] = entry[1]

    if include_untracked:
        code, out, _ = _run(["git", "ls-files", "--others", "--exclude-standard"], cwd=path)
        if code == 0:
            for line in out.splitlines():
                rel = line.strip()
                if rel:
                    changed.setdefault(rel, "U")

    return changed


def diff_text(path: str, *, base: str = "HEAD") -> str:
    """Raw unified diff for the working tree relative to ``base``."""
    code, out, _ = _run(["git", "diff", "--no-renames", "-U0", base], cwd=path)
    if code == 0:
        return out
    return ""


def changed_symbols(path: str, *, base: str = "HEAD") -> Dict[str, List[str]]:
    """Approximate which identifiers changed in each file.

    PlanAnchor deliberately avoids embedding a language parser: it extracts
    identifiers that appear on *added* diff lines.  That is enough to answer
    "did this task actually touch the symbol it claimed?" without pulling in
    tree-sitter or a language server.

    Returns:
        Mapping of file path -> list of identifiers seen on added lines.
    """
    diff = diff_text(path, base=base)
    root = repo_root(path) or path
    result: Dict[str, List[str]] = {}
    current: Optional[str] = None

    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target.startswith("b/"):
                target = target[2:]
            current = None if target == "/dev/null" else target
            result.setdefault(current or "", [])
            continue
        if line.startswith("+") and not line.startswith("+++") and current:
            for ident in _IDENT_RE.findall(line[1:]):
                if len(ident) > 2:
                    result.setdefault(current, [])
                    if ident not in result[current]:
                        result[current].append(ident)
    # ``/dev/null`` and empty keys are noise.
    result.pop("", None)
    result.pop("/dev/null", None)
    return result


def head_commit(path: str) -> str:
    """Short HEAD sha, or ``""`` when unavailable."""
    code, out, _ = _run(["git", "rev-parse", "--short", "HEAD"], cwd=path)
    return out.strip() if code == 0 else ""


def current_branch(path: str) -> str:
    """Current branch name, or ``""`` when detached / unavailable."""
    code, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    return out.strip() if code == 0 else ""


_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #

def _parse_name_status(line: str) -> Optional[Tuple[str, str]]:
    """Parse one ``git diff --name-status`` line."""
    if not line.strip():
        return None
    parts = line.split("\t")
    if len(parts) < 2:
        parts = line.split()
        if len(parts) < 2:
            return None
    status = parts[0].strip()[:1].upper()
    rel = parts[-1].strip()
    if not rel or status not in "AMDRTU":
        return None
    return rel, status


def _run(args: List[str], cwd: str) -> Tuple[int, str, str]:
    """Run a command, never raising.  Returns ``(code, stdout, stderr)``."""
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, "", "git unavailable"
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode, out, err


def norm(path: str) -> str:
    """Normalise a path for comparison (posix separators, no leading ``./``)."""
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def basename_match(ref: str, changed: Dict[str, str]) -> Optional[str]:
    """Resolve a plan reference that is not an exact match by basename.

    Agents frequently write ``@model.py`` while the real path is
    ``src/plananchor/model.py``.  A unique basename match is a safe fallback;
    an ambiguous one returns ``None`` so we never guess wrong.
    """
    base = os.path.basename(norm(ref))
    if not base:
        return None
    hits = [c for c in changed if os.path.basename(norm(c)) == base]
    if len(hits) == 1:
        return hits[0]
    return None
