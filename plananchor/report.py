"""Multi-format reporting.

Every analyser in PlanAnchor returns plain Python objects; this module turns
them into the artefacts CI systems actually consume:

* ``text``  — colourised terminal output (no ANSI when not a TTY)
* ``json``  — machine readable payload for dashboards
* ``sarif`` — SARIF 2.1.0 for GitHub code scanning / IDEs
* ``junit`` — JUnit XML for test-report UIs
* ``md``    — Markdown, for PR comments and chat
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .drift import DriftReport
from .model import Finding, Plan, Severity
from .stall import StallReport

#: Formats understood by :func:`emit`.
FORMATS = ("text", "json", "sarif", "junit", "md")

_SEV_TO_SARIF = {
    Severity.INFO: "note",
    Severity.WARNING: "warning",
    Severity.ERROR: "error",
}

_SEV_TO_JUNIT = {
    Severity.INFO: "info",
    Severity.WARNING: "warning",
    Severity.ERROR: "failure",
}

_ICON = {
    Severity.INFO: "ℹ️ ",
    Severity.WARNING: "⚠️ ",
    Severity.ERROR: "❌ ",
}


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #

def collect(
    plan: Plan,
    findings: Sequence[Finding],
    drift: Optional[DriftReport] = None,
    stall: Optional[StallReport] = None,
) -> Dict[str, Any]:
    """Merge all analyser outputs into a single payload."""
    payload: Dict[str, Any] = {
        "tool": "PlanAnchor",
        "version": __version__,
        "plan": {
            "path": plan.path,
            "title": plan.title,
            "sections": plan.sections,
            "counts": plan.counts(),
            "progress": plan.progress(),
            "tasks": len(plan.all_tasks()),
        },
        "findings": [f.to_dict() for f in findings],
    }
    if drift is not None:
        payload["drift"] = drift.to_dict()
    if stall is not None:
        payload["stall"] = stall.to_dict()

    counts = {"info": 0, "warning": 0, "error": 0}
    for f in findings:
        counts[f.severity.value] += 1
    if drift is not None:
        for item in drift.items:
            counts[item.severity.value] += 1
    if stall is not None:
        for item in stall.items:
            counts[item.severity.value] += 1
    payload["summary"] = counts
    payload["ok"] = counts["error"] == 0
    return payload


def emit(
    fmt: str,
    plan: Plan,
    findings: Sequence[Finding],
    drift: Optional[DriftReport] = None,
    stall: Optional[StallReport] = None,
) -> str:
    """Render an aggregated report in the requested format.

    Args:
        fmt: One of :data:`FORMATS`.
        plan: Parsed plan.
        findings: Validation findings.
        drift: Optional drift report.
        stall: Optional stall report.

    Returns:
        The rendered report as a string.

    Raises:
        ValueError: On an unknown format.
    """
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError("unknown format %r (expected one of %s)" % (fmt, ", ".join(FORMATS)))
    payload = collect(plan, findings, drift, stall)
    if fmt == "json":
        return _render_json(payload)
    if fmt == "sarif":
        return _render_sarif(payload)
    if fmt == "junit":
        return _render_junit(payload)
    if fmt == "md":
        return _render_markdown(payload)
    return _render_text(payload)


# --------------------------------------------------------------------------- #
# text
# --------------------------------------------------------------------------- #

def _render_text(payload: Dict[str, Any]) -> str:
    use_color = _supports_color()
    out: List[str] = []
    add = out.append

    info = payload["plan"]
    add(_head("PlanAnchor %s" % payload["version"], use_color))
    add("")
    add("  plan      : %s" % (info["path"] or "(in-memory)"))
    add("  title     : %s" % (info["title"] or "-"))
    add("  tasks     : %d" % info["tasks"])
    add(
        "  progress  : %.1f%%  (done %d / active %d / pending %d / blocked %d / skipped %d)"
        % (
            info["progress"],
            info["counts"]["done"],
            info["counts"]["active"],
            info["counts"]["pending"],
            info["counts"]["blocked"],
            info["counts"]["skipped"],
        )
    )
    add("")

    add(_head("Validation", use_color))
    findings = payload["findings"]
    if not findings:
        add("  ✅ no findings")
    else:
        for f in findings:
            add(
                "  %s%s  %s  line %s%s"
                % (
                    _ICON.get(Severity(f["severity"]), ""),
                    f["rule"],
                    f["message"],
                    f["line"] or "-",
                    "  [%s]" % f["task_uid"] if f["task_uid"] else "",
                )
            )
            if f["hint"]:
                add("        ↳ %s" % f["hint"])
    add("")

    if "drift" in payload:
        d = payload["drift"]
        add(_head("Drift (%s)" % ("git " + d["head"] if d.get("git_available") else "no git"), use_color))
        if not d["items"]:
            add("  ✅ no drift")
        else:
            for item in d["items"]:
                add("  %s%s  %s" % (_ICON.get(Severity(item["severity"]), ""), item["rule"], item["message"]))
                if item["hint"]:
                    add("        ↳ %s" % item["hint"])
        add("")

    if "stall" in payload:
        s = payload["stall"]
        add(_head("Stall (%d snapshots)" % s["snapshots"], use_color))
        if not s["items"]:
            add("  ✅ no stall signals")
        else:
            for item in s["items"]:
                add("  %s%s  %s" % (_ICON.get(Severity(item["severity"]), ""), item["rule"], item["message"]))
                if item["hint"]:
                    add("        ↳ %s" % item["hint"])
        add("")

    summary = payload["summary"]
    add(
        "%s %d error(s), %d warning(s), %d info"
        % ("✅" if payload["ok"] else "❌", summary["error"], summary["warning"], summary["info"])
    )
    return "\n".join(out)


def _head(text: str, color: bool) -> str:
    if color:
        return "\033[1m%s\033[0m" % text
    return text.upper()


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        return bool(sys.stdout.isatty())
    except Exception:  # pragma: no cover
        return False


# --------------------------------------------------------------------------- #
# json
# --------------------------------------------------------------------------- #

def _render_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# sarif
# --------------------------------------------------------------------------- #

_RULE_TEXT = {
    "PA001": "Plan contains no tasks.",
    "PA002": "Duplicate task uid.",
    "PA003": "Closed task declares no file reference.",
    "PA004": "Blocked task has no reason.",
    "PA005": "More than one active task.",
    "PA006": "Parent closed while children remain open.",
    "PA007": "No active task while work is outstanding.",
    "PA008": "Plan has no structuring heading.",
    "PA009": "Task title is empty.",
    "PA010": "Nesting deeper than max_depth.",
    "PA011": "Referenced file does not exist.",
    "PA012": "Task has no acceptance marker.",
    "PA013": "Duplicate task title.",
    "PA014": "Numeric outline ids skip a level.",
    "DF000": "Git unavailable — drift detection skipped.",
    "DF001": "Task marked done but referenced files did not change.",
    "DF002": "File changed but no task claims it.",
    "DF003": "Claimed symbol is absent from the diff.",
    "DF004": "File scope overlaps between a closed and an open task.",
    "DF005": "Task references a file Git reports as unchanged.",
    "DF006": "No file changes detected while tasks remain open.",
    "ST001": "Task stuck in progress across many snapshots.",
    "ST002": "Task status oscillates between snapshots.",
    "ST003": "Blocked task gates downstream work.",
    "ST004": "Overall progress did not move.",
    "ST005": "First open task is abandoned while later ones advance.",
    "ST006": "No task marked in progress.",
}


def _render_sarif(payload: Dict[str, Any]) -> str:
    results: List[Dict[str, Any]] = []

    def push(rule: str, severity: str, message: str, line: int, path: str) -> None:
        results.append(
            {
                "ruleId": rule,
                "level": _SEV_TO_SARIF.get(Severity(severity), "warning"),
                "message": {"text": message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": path or "PLAN.md"},
                            "region": {"startLine": max(1, line or 1)},
                        }
                    }
                ],
            }
        )

    path = payload["plan"]["path"]
    for f in payload["findings"]:
        push(f["rule"], f["severity"], f["message"], f["line"], path)
    if "drift" in payload:
        for item in payload["drift"]["items"]:
            push(item["rule"], item["severity"], item["message"], 1, item["path"] or path)
    if "stall" in payload:
        for item in payload["stall"]["items"]:
            push(item["rule"], item["severity"], item["message"], item["line"], path)

    rules = []
    seen = set()
    for r in results:
        if r["ruleId"] in seen:
            continue
        seen.add(r["ruleId"])
        rules.append(
            {
                "id": r["ruleId"],
                "shortDescription": {"text": _RULE_TEXT.get(r["ruleId"], r["ruleId"])},
                "helpUri": "https://github.com/gitstq/PlanAnchor#rule-catalogue",
            }
        )

    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "PlanAnchor",
                        "version": payload["version"],
                        "informationUri": "https://github.com/gitstq/PlanAnchor",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# junit
# --------------------------------------------------------------------------- #

def _render_junit(payload: Dict[str, Any]) -> str:
    def esc(value: object) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    cases: List[str] = []

    def push(suite: str, rule: str, severity: str, message: str) -> None:
        body = esc(message)
        case = ['<testcase classname="%s" name="%s"' % (esc(suite), esc(rule))]
        level = _SEV_TO_JUNIT.get(Severity(severity), "warning")
        if level == "failure":
            cases.append(
                "%s>\n  <failure message=%s>%s</failure>\n</testcase>"
                % (case[0], _q(esc(message)), body)
            )
        elif level == "warning":
            cases.append(
                "%s>\n  <system-out>warning: %s</system-out>\n</testcase>" % (case[0], body)
            )
        else:
            cases.append("%s>\n  <system-out>info: %s</system-out>\n</testcase>" % (case[0], body))

    for f in payload["findings"]:
        push("validation", f["rule"], f["severity"], f["message"])
    if "drift" in payload:
        for item in payload["drift"]["items"]:
            push("drift", item["rule"], item["severity"], item["message"])
    if "stall" in payload:
        for item in payload["stall"]["items"]:
            push("stall", item["rule"], item["severity"], item["message"])

    summary = payload["summary"]
    total = summary["error"] + summary["warning"] + summary["info"]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<testsuites name="PlanAnchor">\n'
        '  <testsuite name="plananchor" tests="%d" failures="%d" warnings="%d" time="0">\n'
        "%s\n"
        "  </testsuite>\n"
        "</testsuites>\n"
        % (total, summary["error"], summary["warning"], "\n".join("    " + c for c in cases))
    )


def _q(value: str) -> str:
    return '"%s"' % value.replace('"', "&quot;")


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #

def _render_markdown(payload: Dict[str, Any]) -> str:
    out: List[str] = []
    add = out.append
    info = payload["plan"]
    summary = payload["summary"]

    add("## 🧭 PlanAnchor report")
    add("")
    add("| Item | Value |")
    add("|---|---|")
    add("| Plan | `%s` |" % (info["path"] or "(in-memory)"))
    add("| Tasks | %d |" % info["tasks"])
    add("| Progress | **%.1f%%** |" % info["progress"])
    add("| Errors | %d |" % summary["error"])
    add("| Warnings | %d |" % summary["warning"])
    add("| Info | %d |" % summary["info"])
    add("")

    def table(title: str, rows: Sequence[Dict[str, Any]], key: str = "rule") -> None:
        add("### %s" % title)
        add("")
        if not rows:
            add("✅ nothing to report")
            add("")
            return
        add("| Severity | Rule | Message | Line |")
        add("|---|---|---|---|")
        for r in rows:
            add(
                "| %s | `%s` | %s | %s |"
                % (
                    _sev_badge(r["severity"]),
                    r[key],
                    str(r["message"]).replace("|", "\\|"),
                    r.get("line") or "-",
                )
            )
        add("")

    table("🔍 Validation", payload["findings"])
    if "drift" in payload:
        table("🌊 Drift", payload["drift"]["items"])
    if "stall" in payload:
        table("🐌 Stall", payload["stall"]["items"])
    return "\n".join(out)


def _sev_badge(severity: str) -> str:
    return {
        "error": "🔴 error",
        "warning": "🟡 warning",
        "info": "🔵 info",
    }.get(severity, severity)
