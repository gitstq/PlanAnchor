#!/usr/bin/env bash
# PlanAnchor CI gate — copy into your repo and call from any pipeline.
# Exit codes: 0 pass · 1 findings · 2 usage · 3 input missing
set -euo pipefail

PLAN="${1:-PLAN.md}"
THRESHOLD="${2:-warning}"          # error | warning | info
FORMAT="${3:-text}"                # text | json | sarif | junit | md

if ! command -v plananchor >/dev/null 2>&1; then
  python -m pip install --quiet -e .
fi

plananchor status "$PLAN" --fail-on "$THRESHOLD" -f "$FORMAT"
