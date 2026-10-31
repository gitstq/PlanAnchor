<div align="center">

# 🧭 PlanAnchor

**Zero-dependency, offline-first plan anchoring, drift auditing and crash recovery for AI coding agents**

[![简体中文](https://img.shields.io/badge/switch-简体中文-gray?style=for-the-badge)](./README.zh-CN.md)
[![繁體中文](https://img.shields.io/badge/switch-繁體中文-gray?style=for-the-badge)](./README.zh-TW.md)
[![English](https://img.shields.io/badge/English-current-red?style=for-the-badge)](./README.en.md)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](./LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen?style=for-the-badge)](./requirements.txt)

*Turn an AI agent's plan file from "fragile Markdown convention" into a verifiable, recoverable, CI-ready engineering asset.*

</div>

---

## 🎉 Project Introduction

### The problem

Anyone who has run a long task with an AI coding agent (Claude Code, Cursor, Codex, Copilot…) has hit these walls:

| 😱 Pain | 🔥 Consequence |
|---|---|
| `/clear` or a context compaction fires | the plan collapses to one line — dozens of tasks evaporate |
| The agent flips `- [ ]` to `- [x]` | **the code never changed**, and you only notice at review time |
| The session dies and you open a new one | nobody knows what was in flight, what's next, or what's blocked |
| Files change outside the plan | silent scope creep nobody audits |
| The plan file gets overwritten | no history — you rewrite it from memory |

> 💡 **The insight**: `planning-with-files`-style approaches solve *having* a plan with Markdown conventions — but they rely on the agent's good behaviour. There is **no validation, no recovery, no audit**. PlanAnchor adds exactly those three layers.

### What makes it different

🛠️ **Convention → engine** — not a template, but a real parser plus rule engine: **14 validation rules + 7 drift classes + 6 stall classes**.

🧲 **Hash-chained anchors** — every snapshot extends a `sha256(prev + text)` chain, so history is **tamper-evident** and independently verifiable.

🧬 **Forward-merge restore** — recovery never blindly overwrites: it merges only in the *forward* direction, so work done after the compaction survives.

🌊 **Drift detection** — cross-checks "what the plan claims" against "what Git actually changed": **falsely-claimed completion**, **silent changes**, **missing symbols**, **scope creep**.

🧾 **One-command resume briefing** — emits a copy-paste prompt for a fresh session: current task, upcoming queue, blockers, key files.

🚦 **CI-ready** — `text` / `json` / `SARIF 2.1.0` / `JUnit XML` / `Markdown` reports; one command into any pipeline.

🪶 **Genuinely zero dependencies** — Python standard library only. No `requests`, no `click`, no `pydantic`. Zero transitive packages, so it never fights your environment.

🔌 **Library + CLI** — use it from the shell, or `import plananchor` and drive it programmatically.

---

## ✨ Core Features

### 🔍 Structured parsing
- ✅ GFM plus the de-facto agent status glyphs: `[ ]` pending · `[~]` active · `[x]`/`[X]` done · `[-]` skipped · `[!]` blocked
- ✅ Automatic **outline ids** (`1.2.3`) and **nesting** (tabs and spaces, mixed)
- ✅ Extracts **file refs** (`@src/a.py` / `` `src/a.py` ``), **symbols** (`#func`), **owners** (`(owner: x)`), **notes** (`(note: ...)` / `(blocked: ...)`)
- ✅ YAML-style `---` front matter

### 📏 14 validation rules (PA series)

| Rule | Level | Meaning |
|---|---|---|
| `PA001` | 🔴 error | The plan has no tasks at all |
| `PA002` | 🔴 error | Duplicate task id |
| `PA003` | 🟡 warning | A closed task declares no file reference — unverifiable |
| `PA004` | 🟡 warning | A blocked task gives no reason — the next session can't unblock itself |
| `PA005` | 🔵 info | Several tasks in progress at once |
| `PA006` | 🔴 error | Parent closed while children stay open — **logical contradiction** |
| `PA007` | 🔵 info | Outstanding work but no "in progress" anchor |
| `PA008` | 🟡 warning | Many tasks with no structuring heading |
| `PA009` | 🟡 warning | Empty task title |
| `PA010` | 🟡 warning | Nesting deeper than `max_depth` (default 4) |
| `PA011` | 🟡 warning | Referenced file does not exist on disk |
| `PA012` | 🔵 info | Task has no acceptance criterion |
| `PA013` | 🔵 info | Duplicate task title — ambiguous briefings |
| `PA014` | 🔵 info | Outline numbering skips a level (usually a deleted task) |

> 🎯 Inline suppression: `- [x] foo <!-- plananchor: ignore PA003 -->`

### 🌊 7 drift classes (DF series)

| Rule | Level | Meaning |
|---|---|---|
| `DF001` | 🔴 error | **Falsely claimed done** — marked done but referenced files never changed |
| `DF002` | 🔵 info | **Silent change** — a file changed and no task claims it |
| `DF003` | 🟡 warning | **Missing symbol** — the claimed symbol is absent from the diff |
| `DF004` | 🔵 info | **Scope overlap** — one file claimed by both a closed and an open task |
| `DF005` | 🟡 warning | **Dangling reference** — Git reports the referenced file as unchanged |
| `DF006` | 🔵 info | **No progress** — tasks open, repository untouched |
| `DF000` | 🔵 info | Git unavailable (graceful degradation — never a crash) |

> 🪟 **Change window**: drift compares the *uncommitted* diff against `HEAD`. When the work tree is clean — a fresh clone, or every edit already committed — the window is empty and per-task `DF001` verdicts would flag already-landed history as errors. PlanAnchor then switches to **settled mode** and collapses them into a single informational summary. To audit a slice of history, widen the window explicitly with `plananchor drift PLAN.md --base HEAD~5`.

### 🐌 6 stall classes (ST series)

`ST001` stuck on one task · `ST002` status churn · `ST003` blocker cascades downstream · `ST004` progress frozen · `ST005` first task abandoned · `ST006` no "in progress" anchor

### 🧲 Anti-compaction anchors
- ⛓️ **Hash chain** — `sha256(prev + text)`; tampering with any historical snapshot is caught by `verify`
- 🔁 **Forward merge** — restore keeps only forward status moves, so post-compaction progress survives
- 🧹 **Auto-prune** — `--keep N` retains the newest N snapshots and re-links the chain
- 📸 **Dry run** — `--dry-run` shows what would be restored without writing

### 📊 Five report formats

`text` (terminal, colourised) · `json` (dashboards) · `sarif` (GitHub code scanning / IDEs) · `junit` (test-report UIs) · `md` (PR comments)

---

## 🚀 Quick Start

### Requirements

| Item | Requirement |
|---|---|
| Python | **3.8+** (3.8 / 3.9 / 3.10 / 3.11 / 3.12 all CI-verified) |
| OS | 🐧 Linux · 🍎 macOS · 🪟 Windows |
| Third-party deps | **none** (standard library only) |
| Git (optional) | only for drift detection; degrades gracefully |

### Install

```bash
# Option 1 — from source (recommended, zero deps)
git clone https://github.com/gitstq/PlanAnchor.git
cd PlanAnchor
pip install -e .

# Option 2 — no install at all
python -m plananchor --help

# Option 3 — once published to PyPI
pip install plananchor
```

### 30-second tour

```bash
# 1. scaffold a plan
plananchor init PLAN.md

# 2. full analysis (validation + drift + stall)
plananchor status PLAN.md

# 3. save a recovery anchor after every milestone
plananchor snapshot PLAN.md -m "parser engine done"

# 4. recover after a compaction
plananchor restore PLAN.md

# 5. emit a copy-paste briefing for a fresh session
plananchor resume PLAN.md -o RESUME.md
```

### What does a plan file look like?

```markdown
---
project: my-service
owner: agent
---

# Refactor the user service

## Phase 1 · Data layer

- [~] 1.1 Define the data model `@src/model.py` #User
- [x] 1.2 Implement the parser `@src/parser.py` #parse_text
  - [x] 1.2.1 Handle nested indentation
  - [ ] 1.2.2 Handle status glyphs (accept: all 5 glyphs covered)
- [ ] 1.3 Add unit tests `@tests/test_parser.py` (accept: >= 90% coverage)

## Phase 2 · Delivery

- [!] 2.1 Publish the package (blocked: waiting for the registry token)
- [-] 2.2 Migrate the legacy script (note: deprecated)
```

**Status glyph cheat-sheet**

| Glyph | Meaning | Glyph | Meaning |
|---|---|---|---|
| `[ ]` | pending | `[x]` / `[X]` | done |
| `[~]` | in progress (**resume anchor**) | `[-]` | skipped |
| `[!]` | blocked (**state the reason**) | | |

---

## 📖 Detailed Usage

### Commands

| Command | Purpose | Common flags |
|---|---|---|
| `status` | full analysis (validation + drift + stall) | `--no-git` `--fail-on warning` |
| `check` | validation only | `--no-refs` `--max-depth 3` |
| `drift` | drift only | `--base HEAD~1` `--ignore dist/` |
| `parse` | print the task tree | `--json` `--stats` |
| `snapshot` | create an anchor | `-m "note"` `--keep 50` |
| `restore` | restore from an anchor | `--seq 3` `--exact` `--dry-run` |
| `verify` | verify the hash chain | — |
| `resume` | emit a briefing | `--lang en` `--next 5` `-o FILE` |
| `init` | scaffold a template | `--force` |
| `rules` | print the rule catalogue | `--json` |

### Global flags

```
-f, --format   text|json|sarif|junit|md    report format (default: text)
-o, --output   PATH                        write to a file instead of stdout
```

**Exit codes**: `0` pass · `1` findings at/above the threshold · `2` usage error · `3` input missing

### Typical scenarios

#### 🎯 1. A CI gate before every commit

```bash
# fail only on errors
plananchor check PLAN.md --fail-on error

# stricter: warnings fail too, and emit SARIF for GitHub
plananchor status PLAN.md --fail-on warning -f sarif -o plananchor.sarif
```

GitHub Actions:

```yaml
- name: PlanAnchor gate
  run: |
    pip install -e .
    plananchor status PLAN.md --fail-on warning -f sarif -o plananchor.sarif
- name: Upload SARIF
  if: always()
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: plananchor.sarif
```

#### 🎯 2. The long-running agent loop (the core use case)

```bash
# anchor after every milestone — the only insurance against compaction
plananchor snapshot PLAN.md -m "phase 1 complete"

# in a new session / after compaction / after a crash
plananchor restore PLAN.md
plananchor resume PLAN.md -o RESUME.md   # paste RESUME.md into the agent
```

> 💡 **Best practice**: put `plananchor snapshot` into your agent instruction file (`AGENTS.md` / `CLAUDE.md`) so it auto-anchors after each task.

#### 🎯 3. Audit whether the agent is actually working

```bash
plananchor drift PLAN.md --base HEAD~5
```

Sample output:

```
❌ DF001  task "implement the parser" is marked done but none of its files changed: src/parser.py
   ↳ revert the checkbox to `[ ]`, or actually commit the change
```

#### 🎯 4. Suppress a false positive inline

```markdown
- [x] 1.5 Update docs `@docs/` <!-- plananchor: ignore PA003, PA011 -->
        <!-- suppress everything on this line: plananchor: ignore -->
```

#### 🎯 5. Machine-readable output only

```bash
plananchor status PLAN.md -f json | jq '.summary'
plananchor check PLAN.md -f junit -o report.xml
plananchor status PLAN.md -f md -o comment.md   # paste into a PR
```

### Python API

```python
from plananchor import parse_file, validate_plan, detect_drift, AnchorStore, build_resume
from plananchor.resume import render_brief

# 1. parse
plan = parse_file("PLAN.md")
print(plan.progress(), plan.counts())     # 33.3  {'done':1,'active':1,...}

# 2. validate
for f in validate_plan(plan, max_depth=4):
    print(f.rule, f.severity.value, f.message, f.line)

# 3. drift
drift = detect_drift(plan, repo=".", base="HEAD")
if not drift.clean:
    for item in drift.items:
        print(item.rule, item.message)

# 4. anchors: save / detect compaction / restore
store = AnchorStore("PLAN.md")
store.create(plan, note="milestone 1")
signal = store.detect_compaction(plan)
if signal.compacted:
    text, _ = store.restore("PLAN.md")        # forward merge
print(store.verify().ok)                       # True

# 5. resume briefing
brief = build_resume(plan, store=store, drift=drift, lang="en")
open("RESUME.md", "w").write(render_brief(brief))
```

**Modules**

| Module | Responsibility |
|---|---|
| `plananchor.parser` | Markdown parsing / canonical rendering |
| `plananchor.model` | `Plan` / `Task` / `Finding` data model |
| `plananchor.validate` | the 14 PA rules |
| `plananchor.drift` | the 7 DF drift classes |
| `plananchor.stall` | the 6 ST stall classes |
| `plananchor.anchor` | snapshots, hash chain, restore |
| `plananchor.resume` | briefing generation |
| `plananchor.report` | five-format rendering |
| `plananchor.gitutil` | minimal Git integration (no deps) |

---

## 💡 Design Notes & Roadmap

### Why zero dependencies?

Agent tooling gets dropped into unpredictable environments — containers, CI runners, offline machines, other people's repos. Every extra dependency is one more way to fail to install. PlanAnchor is pure standard library, so **copying one directory is enough to run it**. That is a deliberate architectural choice.

### Why a hash chain instead of plain backups?

Plain backups can be silently rewritten. A hash chain makes history itself verifiable: anyone (including you, three months later) can run `plananchor verify` and confirm the recovery basis was never tampered with.

### Why read file contents instead of trusting only the diff?

`git diff` shows only the lines that *moved*. If the target symbol already existed in an earlier commit, a diff-only check reports a false positive. PlanAnchor checks both the added diff lines **and** the current file contents, which cuts false positives sharply.

### Tech choices

| Choice | Why |
|---|---|
| Python 3.8+ | widest reach across agent environments |
| `dataclasses` | dependency-free, serialisable, clearly typed |
| `argparse` | stdlib CLI — no `click` |
| `subprocess` → git | Git is a system tool, not a Python dependency |
| `hashlib.sha256` | stdlib hash chain |

### Roadmap 🗺️

- [ ] 🔌 MCP server form so agents can call `snapshot` / `resume` directly
- [ ] 🌐 More briefing languages (Japanese / Korean / Spanish)
- [ ] 📈 Progress-curve visualisation (ASCII + HTML)
- [ ] 🤖 Agent instruction-file generator (auto-inject snapshot hooks into `AGENTS.md` / `CLAUDE.md`)
- [ ] 🔗 Multi-plan federation (aggregate sub-project plans)
- [ ] 🧪 Snapshot-based "task replay" regression testing

---

## 📦 Packaging & Deployment

PlanAnchor is a **library / CLI** project — no Release binaries are published; it ships via package managers and source.

### Build locally

```bash
make build          # == python -m build

ls dist/
#   plananchor-1.0.0.tar.gz
#   plananchor-1.0.0-py3-none-any.whl
```

### Install the wheel

```bash
pip install dist/plananchor-1.0.0-py3-none-any.whl
plananchor --version
```

### Single-directory, install-free deployment

Because there are no dependencies, you can just copy the package:

```bash
cp -r plananchor /target/project/vendor/
cd /target/project && PYTHONPATH=vendor python -m plananchor status PLAN.md
```

### Publish to PyPI (maintainers)

```bash
make release                     # clean + build
python -m twine check dist/*
python -m twine upload dist/*
```

### Docker

```dockerfile
FROM python:3.11-slim
COPY plananchor /app/plananchor
COPY PLAN.md /app/PLAN.md
WORKDIR /app
CMD ["python", "-m", "plananchor", "status", "PLAN.md"]
```

### Compatibility matrix

| Python | Linux | macOS | Windows |
|:---:|:---:|:---:|:---:|
| 3.8 | ✅ | ✅ | ✅ |
| 3.9 | ✅ | ✅ | ✅ |
| 3.10 | ✅ | ✅ | ✅ |
| 3.11 | ✅ | ✅ | ✅ |
| 3.12 | ✅ | ✅ | ✅ |

> ⚠️ Drift detection needs `git` on the system. Without it the tool degrades to pure plan validation — it never exits with an error.

---

## 🤝 Contributing

PRs welcome! Please follow these conventions:

### Commit style (Angular convention)

```
feat: add rule PA015
fix: fix nested-indentation parsing
docs: update Traditional Chinese docs
refactor: rework the report rendering layer
test: add drift detection cases
chore: bump the CI matrix
```

### PR process

1. 🍴 Fork and branch (`feat/xxx` / `fix/xxx`)
2. 🧪 Write code plus matching unit tests
3. ✅ Make sure `make test` is green (**zero deps — no test libraries to install**)
4. 🏗️ Make sure `make build` succeeds
5. 📝 Update the docs (zh-CN / zh-TW / en in sync)
6. 🚀 Open the PR describing the motivation and how you verified it

### Issue reports

Please include:
- PlanAnchor version, Python version, OS
- A minimal plan file (Markdown) that reproduces it
- Actual vs. expected output

### Development rules

- 🚫 **Never add a third-party runtime dependency** — this is the project's core constraint
- 📐 New rules need a stable `PAxxx` / `DFxxx` / `STxxx` id and must be registered in `rules_catalog()`
- 🧪 New rules need matching unit tests
- 🔤 Public functions need docstrings (Args / Returns / Raises)

---

## 📄 License

Released under the **MIT License** — see [LICENSE](./LICENSE).

- ✅ Commercial use, modification, distribution, private deployment
- ✅ Closed-source integration
- ⚠️ Keep the original copyright notice and license text
- ❌ No warranty or liability

---

<div align="center">

**🧭 PlanAnchor** — so an AI agent's plan never blows away with the context.

If this helped you, a ⭐ Star is much appreciated!

</div>
