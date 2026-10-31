"""PlanAnchor — 零依赖 · 离线优先的 AI 编码 Agent 计划锚定引擎。

PlanAnchor turns a plain Markdown plan file into a *verifiable*, *recoverable*
and *CI-ready* engineering artifact.  It is designed for AI coding agents that
lose their working memory after ``/clear``, context compaction or a crash.

Core capabilities:

* :mod:`plananchor.parser`   — structured parsing of Markdown plan files
* :mod:`plananchor.validate` — schema & hygiene lint rules
* :mod:`plananchor.drift`    — plan vs. repository drift detection
* :mod:`plananchor.anchor`   — tamper-evident snapshots & anti-compaction restore
* :mod:`plananchor.resume`   — hand-off / resume briefing generation
* :mod:`plananchor.stall`    — stall & churn detection
* :mod:`plananchor.report`   — multi-format reporting (text / json / sarif / junit / md)

Zero third-party dependencies — standard library only.
"""

from __future__ import annotations

__version__ = "1.0.1"
__all__ = [
    "__version__",
    "model",
    "parser",
    "validate",
    "drift",
    "anchor",
    "resume",
    "stall",
    "report",
    "cli",
]

# Convenience re-exports so that ``import plananchor`` gives access to the
# most frequently used entry points without deep imports.
from . import model  # noqa: F401,E402
from . import parser  # noqa: F401,E402
from . import validate  # noqa: F401,E402
from . import drift  # noqa: F401,E402
from . import anchor  # noqa: F401,E402
from . import resume  # noqa: F401,E402
from . import stall  # noqa: F401,E402
from . import report  # noqa: F401,E402

from .model import Plan, Task, TaskStatus, Finding, Severity  # noqa: F401,E402
from .parser import parse_file, parse_text  # noqa: F401,E402
from .validate import validate_plan  # noqa: F401,E402
from .drift import detect_drift  # noqa: F401,E402
from .anchor import AnchorStore  # noqa: F401,E402
from .resume import build_resume  # noqa: F401,E402
from .stall import detect_stalls  # noqa: F401,E402
