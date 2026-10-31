---
project: my-project
owner: agent
---

# My Project Plan

## Phase 1 — Foundations

- [~] 1.1 Define the data model `@src/model.py` #Model
- [ ] 1.2 Implement the parser `@src/parser.py` #parse_text
  - [ ] 1.2.1 Handle nested indentation
  - [ ] 1.2.2 Handle status glyphs
- [ ] 1.3 Add unit tests `@tests/test_parser.py` (accept: 90% coverage)

## Phase 2 — Hardening

- [ ] 2.1 Wire up the CLI `@src/cli.py`
- [!] 2.2 Publish the package (blocked: waiting for the registry token)
