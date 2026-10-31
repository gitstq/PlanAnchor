<div align="center">

# 🧭 PlanAnchor

**零依赖 · 离线优先的 AI 编码 Agent 计划锚定、漂移审计与崩溃恢复引擎**

[![简体中文](https://img.shields.io/badge/简体中文-当前-red?style=for-the-badge)](./README.zh-CN.md)
[![繁體中文](https://img.shields.io/badge/切換-繁體中文-gray?style=for-the-badge)](./README.zh-TW.md)
[![English](https://img.shields.io/badge/switch-English-gray?style=for-the-badge)](./README.en.md)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](./LICENSE)
[![Dependencies](https://img.shields.io/badge/依赖-0%20个-brightgreen?style=for-the-badge)](./requirements.txt)

*让 AI 编码 Agent 的计划文件，从「易碎的 Markdown 约定」升级为「可校验、可恢复、可进 CI 的工程资产」。*

</div>

---

## 🎉 项目介绍

### 它解决什么痛点？

每一个用 AI 编码 Agent（Claude Code、Cursor、Codex、Copilot…）做长任务的人都踩过这些坑：

| 😱 痛点 | 🔥 后果 |
|---|---|
| 执行 `/clear` 或触发上下文压缩 | 计划文件被压成一句话，几十个任务凭空消失 |
| Agent 把 `- [ ]` 改成 `- [x]` 就说做完了 | **代码根本没改**，你在 Review 时才发现问题 |
| 会话中断后重新开一个 | 新会话不知道做到哪一步、下一步是什么、卡在哪 |
| 改了计划外的文件 | 无人知晓，悄悄埋雷 |
| 计划文件被误删/覆盖 | 没有历史，只能凭记忆重写 |

> 💡 **核心洞察**：`planning-with-files` 这类方案用 Markdown 约定解决了「有没有计划」，但它依赖 Agent 自觉维护——**没有校验、没有恢复、没有审计**。PlanAnchor 补上的正是这三层。

### 自研差异化亮点

🛠️ **从「约定」到「引擎」** — 不只是模板，而是一套可执行的解析器 + 规则引擎，14 条校验规则 + 7 类漂移检测 + 6 类停滞检测。

🧲 **哈希链锚点** — 每次快照形成 `sha256(prev + text)` 哈希链，**历史不可篡改**，可审计、可验证。

🧬 **前向合并恢复** — 恢复时不会粗暴覆盖：只在状态「前进」的方向上合并，你在压缩后新做的工作也不会丢。

🌊 **计划漂移检测** — 交叉比对「计划声称做了什么」与「Git 实际改了什么」，揪出**谎报完成**、**静默改动**、**符号缺失**、**范围蔓延**。

🧾 **一键生成恢复简报** — 输出可直接粘贴给新会话的提示词，包含当前任务、后续队列、阻塞项、关键文件清单。

🚦 **CI 门禁就绪** — 支持 `text` / `json` / `SARIF 2.1.0` / `JUnit XML` / `Markdown` 五种报告格式，一条命令接入任何 CI。

🪶 **真·零依赖** — 只用 Python 标准库。没有 `requests`、没有 `click`、没有 `pydantic`，`pip install` 之后 0 个传递依赖，装进任何环境都不会打架。

🔌 **库 + CLI 双形态** — 既能当命令行用，也能 `import plananchor` 直接编程调用。

---

## ✨ 核心特性

### 🔍 结构化解析
- ✅ 兼容 GFM 与 Agent 事实标准状态符号：`[ ]` 待办 · `[~]` 进行中 · `[x]`/`[X]` 完成 · `[-]` 跳过 · `[!]` 阻塞
- ✅ 自动识别**大纲编号**（`1.2.3`）、**层级缩进**（空格 & Tab 混排也行）
- ✅ 抽取**文件引用**（`@src/a.py` / `` `src/a.py` ``）、**代码符号**（`#func`）、**负责人**（`(owner: x)`）、**备注**（`(note: ...)` / `(blocked: ...)`）
- ✅ 支持 YAML 风格 `---` front matter 头

### 📏 14 条校验规则（PA 系列）
| 规则 | 级别 | 说明 |
|---|---|---|
| `PA001` | 🔴 error | 计划里一个任务都没有 |
| `PA002` | 🔴 error | 任务编号重复 |
| `PA003` | 🟡 warning | 已完成任务没声明文件引用，无法验证 |
| `PA004` | 🟡 warning | 阻塞任务没写原因，下个会话无法自救 |
| `PA005` | 🔵 info | 同时进行多个任务，恢复时容易乱 |
| `PA006` | 🔴 error | 父任务已关闭但子任务还开着（**逻辑矛盾**） |
| `PA007` | 🔵 info | 有未完成工作却没有「进行中」锚点 |
| `PA008` | 🟡 warning | 任务很多却没有章节分隔 |
| `PA009` | 🟡 warning | 任务标题为空 |
| `PA010` | 🟡 warning | 嵌套过深（默认 > 4 层） |
| `PA011` | 🟡 warning | 引用的文件在磁盘上不存在 |
| `PA012` | 🔵 info | 任务缺少验收标准 |
| `PA013` | 🔵 info | 任务标题重复，简报会产生歧义 |
| `PA014` | 🔵 info | 大纲编号跳号（通常意味着任务被误删） |

> 🎯 支持行内抑制：`- [x] foo <!-- plananchor: ignore PA003 -->`

### 🌊 7 类漂移检测（DF 系列）
| 规则 | 级别 | 说明 |
|---|---|---|
| `DF001` | 🔴 error | **谎报完成**：标记 done 但引用文件根本没改 |
| `DF002` | 🔵 info | **静默改动**：文件改了但没有任务认领 |
| `DF003` | 🟡 warning | **符号缺失**：声称改的函数在 diff 里找不到 |
| `DF004` | 🔵 info | **范围重叠**：同一文件被已关闭和进行中的任务同时认领 |
| `DF005` | 🟡 warning | **引用悬空**：引用的文件 Git 认为没变化 |
| `DF006` | 🔵 info | **毫无进展**：任务还开着但仓库零改动 |
| `DF000` | 🔵 info | Git 不可用（优雅降级，绝不崩溃） |

> 🪟 **变更窗口（change window）**：漂移默认比对相对 `HEAD` 的未提交改动。工作区干净时（刚 clone 下来、或改动已全部提交）窗口为空，逐任务判定 `DF001` 会把已落地的历史工作全部误报为 error —— 此时 PlanAnchor 进入 **settled（已落定）模式**，把结论折叠成一条 info 级汇总。要审计某段历史，用 `plananchor drift PLAN.md --base HEAD~5` 显式放宽窗口。

### 🐌 6 类停滞检测（ST 系列）
`ST001` 长期卡在同一任务 · `ST002` 状态反复横跳 · `ST003` 阻塞项级联影响下游 · `ST004` 整体进度原地踏步 · `ST005` 首个任务被遗弃 · `ST006` 没有任何「进行中」锚点

### 🧲 抗压缩锚点
- ⛓️ **哈希链**：`sha256(prev + text)`，篡改任一历史快照都会被 `verify` 抓到
- 🔁 **前向合并**：恢复时保留只进不退的状态变更，压缩后的新进度不丢
- 🧹 **自动剪枝**：`--keep N` 保留最近 N 个快照并自动重连哈希链
- 📸 **干跑模式**：`--dry-run` 先看看会恢复成什么，不落盘

### 📊 五种报告格式
`text`（终端彩色）· `json`（仪表盘）· `sarif`（GitHub Code Scanning / IDE）· `junit`（测试报告 UI）· `md`（PR 评论）

---

## 🚀 快速开始

### 环境要求

| 项目 | 要求 |
|---|---|
| Python | **3.8+**（3.8 / 3.9 / 3.10 / 3.11 / 3.12 全测过） |
| 操作系统 | 🐧 Linux · 🍎 macOS · 🪟 Windows（全平台 CI 验证） |
| 第三方依赖 | **无**（Python 标准库即可） |
| Git（可选） | 仅漂移检测需要；没有 Git 会优雅降级而不是报错 |

### 安装

```bash
# 方式一：从源码安装（推荐，零依赖）
git clone https://github.com/gitstq/PlanAnchor.git
cd PlanAnchor
pip install -e .

# 方式二：免安装，直接用
python -m plananchor --help

# 方式三：后续 PyPI 发布后
pip install plananchor
```

### 30 秒上手

```bash
# ① 生成一份计划模板
plananchor init PLAN.md

# ② 看完整分析（校验 + 漂移 + 停滞）
plananchor status PLAN.md

# ③ 保存一个恢复锚点（每次阶段性完成都该做）
plananchor snapshot PLAN.md -m "完成解析引擎"

# ④ 上下文被压缩后，一键恢复
plananchor restore PLAN.md

# ⑤ 生成可直接粘贴给新会话的恢复简报
plananchor resume PLAN.md -o RESUME.md
```

### 计划文件长什么样？

```markdown
---
project: my-service
owner: agent
---

# 重构用户服务

## 阶段一 · 数据层

- [~] 1.1 定义数据模型 `@src/model.py` #User
- [x] 1.2 实现解析器 `@src/parser.py` #parse_text
  - [x] 1.2.1 处理嵌套缩进
  - [ ] 1.2.2 处理状态符号 (accept: 5 种符号全覆盖)
- [ ] 1.3 补单元测试 `@tests/test_parser.py` (accept: 覆盖率 ≥ 90%)

## 阶段二 · 交付

- [!] 2.1 发布包 (blocked: 等待 registry token)
- [-] 2.2 迁移旧脚本 (note: 已废弃)
```

**状态符号速查**

| 符号 | 含义 | 符号 | 含义 |
|---|---|---|---|
| `[ ]` | 待办 | `[x]` / `[X]` | 完成 |
| `[~]` | 进行中（**恢复锚点**） | `[-]` | 已跳过 |
| `[!]` | 阻塞（**建议写原因**） | | |

---

## 📖 详细使用指南

### 命令一览

| 命令 | 作用 | 常用参数 |
|---|---|---|
| `status` | 全量分析（校验 + 漂移 + 停滞） | `--no-git` `--fail-on warning` |
| `check` | 只做校验 | `--no-refs` `--max-depth 3` |
| `drift` | 只做漂移检测 | `--base HEAD~1` `--ignore dist/` |
| `parse` | 打印任务树 | `--json` `--stats` |
| `snapshot` | 创建锚点 | `-m "备注"` `--keep 50` |
| `restore` | 从锚点恢复 | `--seq 3` `--exact` `--dry-run` |
| `verify` | 校验哈希链 | — |
| `resume` | 生成恢复简报 | `--lang en` `--next 5` `-o FILE` |
| `init` | 生成模板 | `--force` |
| `rules` | 打印规则目录 | `--json` |

### 全局参数

```
-f, --format   text|json|sarif|junit|md    报告格式（默认 text）
-o, --output   PATH                         写入文件而非 stdout
```

**退出码**：`0` 通过 · `1` 命中设定级别的发现项 · `2` 用法错误 · `3` 输入文件缺失

### 典型场景

#### 🎯 场景一：每次提交前做 CI 门禁

```bash
# 只有 error 级别才失败
plananchor check PLAN.md --fail-on error

# 更严格：warning 也让 CI 挂掉，并产出 SARIF 给 GitHub
plananchor status PLAN.md --fail-on warning -f sarif -o plananchor.sarif
```

GitHub Actions：

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

#### 🎯 场景二：长任务的 Agent 循环（核心用法）

```bash
# 每个里程碑之后立刻打锚点 —— 这是抗压缩的唯一保险
plananchor snapshot PLAN.md -m "阶段一完成"

# 新会话 / 压缩后 / 崩溃后，先恢复再继续
plananchor restore PLAN.md
plananchor resume PLAN.md -o RESUME.md   # 把 RESUME.md 粘给 Agent
```

> 💡 **最佳实践**：把 `plananchor snapshot` 写进 Agent 的指令文件（AGENTS.md / CLAUDE.md），让它每完成一个任务就自动打锚点。

#### 🎯 场景三：审计 Agent 是不是在「假装干活」

```bash
# 比对计划声称 vs 仓库实际
plananchor drift PLAN.md --base HEAD~5
```

输出示例：

```
❌ DF001  任务「实现解析器」标记已完成，但其文件均未改动：src/parser.py
   ↳ 把勾选框改回 `[ ]`，或真正提交改动
```

#### 🎯 场景四：行内抑制误报

```markdown
- [x] 1.5 更新文档 `@docs/` <!-- plananchor: ignore PA003, PA011 -->
        <!-- 整行全抑制：plananchor: ignore -->
```

#### 🎯 场景五：只想要机器可读结果

```bash
plananchor status PLAN.md -f json | jq '.summary'
plananchor check PLAN.md -f junit -o report.xml
plananchor status PLAN.md -f md -o comment.md   # 贴到 PR
```

### Python API

```python
from plananchor import parse_file, validate_plan, detect_drift, AnchorStore, build_resume
from plananchor.resume import render_brief

# 1️⃣ 解析
plan = parse_file("PLAN.md")
print(plan.progress(), plan.counts())     # 33.3  {'done':1,'active':1,...}

# 2️⃣ 校验
for f in validate_plan(plan, max_depth=4):
    print(f.rule, f.severity.value, f.message, f.line)

# 3️⃣ 漂移
drift = detect_drift(plan, repo=".", base="HEAD")
if not drift.clean:
    for item in drift.items:
        print(item.rule, item.message)

# 4️⃣ 锚点：保存 / 检测压缩 / 恢复
store = AnchorStore("PLAN.md")
store.create(plan, note="milestone 1")
signal = store.detect_compaction(plan)
if signal.compacted:
    text, _ = store.restore("PLAN.md")        # 前向合并恢复
print(store.verify().ok)                       # True

# 5️⃣ 恢复简报
brief = build_resume(plan, store=store, drift=drift, lang="zh")
open("RESUME.md", "w").write(render_brief(brief))
```

**可用模块**

| 模块 | 职责 |
|---|---|
| `plananchor.parser` | Markdown 解析 / 规范化回写 |
| `plananchor.model` | `Plan` / `Task` / `Finding` 数据模型 |
| `plananchor.validate` | 14 条 PA 规则 |
| `plananchor.drift` | 7 类 DF 漂移检测 |
| `plananchor.stall` | 6 类 ST 停滞检测 |
| `plananchor.anchor` | 快照、哈希链、恢复 |
| `plananchor.resume` | 恢复简报生成 |
| `plananchor.report` | 五格式报告渲染 |
| `plananchor.gitutil` | 极简 Git 集成（无第三方依赖） |

---

## 💡 设计思路与迭代规划

### 为什么坚持零依赖？

Agent 生态里，工具会被塞进各种不可控环境——容器、CI、离线机器、别人的项目。多一个依赖就多一个「装不上」的可能。PlanAnchor 用纯标准库实现，**拷贝一个目录就能跑**，这是刻意的架构选择。

### 为什么用哈希链而不是普通备份？

普通备份能被静默改写。哈希链让「历史」本身变成可验证对象：任何人（包括你三个月后）都能 `plananchor verify` 确认恢复依据没有被污染。

### 为什么漂移检测要读文件内容而不只看 diff？

`git diff` 只显示**移动过的行**。如果目标符号在早期提交里已经存在，纯 diff 判定会误报。PlanAnchor 同时检查 diff 新增行与文件当前内容，显著降低误报率。

### 技术选型

| 选择 | 理由 |
|---|---|
| Python 3.8+ | 覆盖面最广，Agent 生态主流环境 |
| `dataclasses` | 零依赖、可序列化、类型清晰 |
| `argparse` | 标准库 CLI，无 `click` 依赖 |
| `subprocess` 调 git | Git 是系统工具，不算 Python 依赖 |
| `hashlib.sha256` | 标准库哈希链 |

### 迭代规划 🗺️

- [ ] 🔌 MCP Server 形态，让 Agent 直接调用 `snapshot` / `resume`
- [ ] 🌐 计划文件多语言（日 / 韩 / 西）简报输出
- [ ] 📈 进度曲线可视化（ASCII + HTML）
- [ ] 🤖 Agent 指令文件模板生成器（`AGENTS.md` / `CLAUDE.md` 自动注入快照钩子）
- [ ] 🔗 多计划文件联邦（子项目计划聚合）
- [ ] 🧪 基于快照的「任务回放」回归测试

---

## 📦 打包与部署指南

PlanAnchor 属于**工具库 / CLI 类项目**，无需上传 Release 二进制包；通过包管理器与源码两种方式分发。

### 本地打包

```bash
# 构建 sdist + wheel
make build          # 等价于 python -m build

# 产物
ls dist/
#   plananchor-1.0.0.tar.gz
#   plananchor-1.0.0-py3-none-any.whl
```

### 安装 Wheel

```bash
pip install dist/plananchor-1.0.0-py3-none-any.whl
plananchor --version
```

### 单文件免安装部署

因为零依赖，整个包可以直接拷走：

```bash
cp -r plananchor /目标项目/vendor/
cd /目标项目 && PYTHONPATH=vendor python -m plananchor status PLAN.md
```

### 发布到 PyPI（维护者）

```bash
make release                     # clean + build
python -m twine check dist/*
python -m twine upload dist/*
```

### 集成到 Docker

```dockerfile
FROM python:3.11-slim
COPY plananchor /app/plananchor
COPY PLAN.md /app/PLAN.md
WORKDIR /app
CMD ["python", "-m", "plananchor", "status", "PLAN.md"]
```

### 兼容环境矩阵

| Python | Linux | macOS | Windows |
|:---:|:---:|:---:|:---:|
| 3.8 | ✅ | ✅ | ✅ |
| 3.9 | ✅ | ✅ | ✅ |
| 3.10 | ✅ | ✅ | ✅ |
| 3.11 | ✅ | ✅ | ✅ |
| 3.12 | ✅ | ✅ | ✅ |

> ⚠️ Git 漂移检测需要系统安装 `git`；缺失时工具降级为纯计划校验，不会报错退出。

---

## 🤝 贡献指南

欢迎 PR！请遵循以下规范：

### 提交规范（Angular 约定）

```
feat: 新增 XX 规则
fix: 修复嵌套缩进解析错误
docs: 补充繁体中文文档
refactor: 重构报告渲染层
test: 补充漂移检测用例
chore: 更新 CI 矩阵
```

### PR 流程

1. 🍴 Fork 本仓库并新建分支（`feat/xxx` / `fix/xxx`）
2. 🧪 编写代码 + 对应单元测试
3. ✅ 确保 `make test` 全绿（**零依赖，不需要装任何测试库**）
4. 🏗️ 确保 `make build` 成功
5. 📝 更新相关文档（中 / 繁 / 英 三语同步）
6. 🚀 提交 PR，描述清楚改动动机与验证方式

### Issue 反馈

请包含：
- PlanAnchor 版本、Python 版本、操作系统
- 复现用的最小计划文件（Markdown）
- 实际输出 vs 期望输出

### 开发约定

- 🚫 **禁止引入任何第三方运行时依赖** —— 这是项目的核心约束
- 📐 新规则必须有稳定 `PAxxx` / `DFxxx` / `STxxx` 编号并登记进 `rules_catalog()`
- 🧪 新规则必须有对应单元测试
- 🔤 公开函数必须有 docstring（含 Args / Returns / Raises）

---

## 📄 开源协议说明

本项目基于 **MIT License** 开源，详见 [LICENSE](./LICENSE)。

- ✅ 允许商用、修改、分发、私有化部署
- ✅ 允许闭源二次集成
- ⚠️ 需保留原始版权声明与协议文本
- ❌ 作者不承担任何使用风险与责任

---

<div align="center">

**🧭 PlanAnchor** — 让 AI Agent 的计划，不再随风而散。

如果这个项目帮到了你，欢迎 ⭐ Star 支持！

</div>
