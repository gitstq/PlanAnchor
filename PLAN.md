---
project: PlanAnchor
owner: gitstq
version: 1.0.0
---

# PlanAnchor 孵化计划

> 本文件是 PlanAnchor **自身的计划文件**，用于 dogfooding：CI 会用 PlanAnchor 校验 PlanAnchor。

## 阶段一 · 核心解析引擎

- [x] 1.1 设计数据模型：Plan / Task / Finding `@plananchor/model.py` #Plan
- [x] 1.2 实现 Markdown 计划解析器 `@plananchor/parser.py` #parse_text
  - [x] 1.2.1 处理五种状态符号与大小写变体 `@plananchor/parser.py` #TaskStatus
  - [x] 1.2.2 处理空格与 Tab 混排缩进 `@plananchor/parser.py` #_expand_indent
  - [x] 1.2.3 抽取文件引用、代码符号、负责人与备注 `@plananchor/parser.py` #_extract_markers
  - [x] 1.2.4 实现规范化回写，保证渲染往返稳定 `@plananchor/parser.py` #render_plan
- [x] 1.3 实现 front matter 头解析 `@plananchor/parser.py` #_read_front_matter

## 阶段二 · 规则引擎

- [x] 2.1 实现 14 条 PA 校验规则 `@plananchor/validate.py` #validate_plan
- [x] 2.2 实现行内抑制指令 `plananchor: ignore` `@plananchor/validate.py` #_collect_ignores
- [x] 2.3 实现极简 Git 集成层（零依赖） `@plananchor/gitutil.py` #changed_files
- [x] 2.4 实现 7 类 DF 漂移检测 `@plananchor/drift.py` #detect_drift
- [x] 2.5 实现 6 类 ST 停滞检测 `@plananchor/stall.py` #detect_stalls

## 阶段三 · 锚定与恢复

- [x] 3.1 实现快照存储与读取 `@plananchor/anchor.py` #AnchorStore
- [x] 3.2 实现 sha256 哈希链与校验 `@plananchor/anchor.py` #_digest
- [x] 3.3 实现压缩/回退检测 `@plananchor/anchor.py` #detect_compaction
- [x] 3.4 实现前向合并恢复 `@plananchor/anchor.py` #_forward_merge
- [x] 3.5 实现恢复简报生成（中英双语） `@plananchor/resume.py` #build_resume

## 阶段四 · 交付

- [x] 4.1 实现五种报告格式渲染 `@plananchor/report.py` #emit
- [x] 4.2 实现完整 CLI 与退出码规范 `@plananchor/cli.py` #main
- [x] 4.3 补齐单元测试套件 `@tests/test_parser.py` #ParseTextTest
- [x] 4.4 编写工程化配置（pyproject / Makefile / CI） `@pyproject.toml` #build-system
- [x] 4.5 编写三语 README 与贡献指南 `@README.md` #PlanAnchor
- [x] 4.6 编写端到端演示脚本 `@scripts/demo.py` #main
