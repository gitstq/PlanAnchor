#!/usr/bin/env bash
# The PlanAnchor agent loop — run after every milestone, and first thing
# after /clear, a compaction, or a crash.
set -euo pipefail

PLAN="${1:-PLAN.md}"

# 1. Did the last session lose part of the plan? Recover it first.
if [ -d "$(dirname "$PLAN")/.plananchor" ]; then
  plananchor restore "$PLAN" || true
fi

# 2. Show where we are.
plananchor status "$PLAN" --no-git

# 3. Emit the briefing and hand it to a fresh session.
plananchor resume "$PLAN" -o RESUME.md
echo "→ paste RESUME.md into the new session"

# 4. Anchor the current state so the next compaction is survivable.
plananchor snapshot "$PLAN" -m "auto anchor $(date -u +%Y-%m-%dT%H:%M:%SZ)"
