<div align="center">

# 🧭 PlanAnchor

**零依賴 · 離線優先的 AI 編碼 Agent 計畫錨定、漂移稽核與崩潰還原引擎**

[![简体中文](https://img.shields.io/badge/切換-简体中文-gray?style=for-the-badge)](./README.zh-CN.md)
[![繁體中文](https://img.shields.io/badge/繁體中文-目前-red?style=for-the-badge)](./README.zh-TW.md)
[![English](https://img.shields.io/badge/switch-English-gray?style=for-the-badge)](./README.en.md)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](./LICENSE)
[![Dependencies](https://img.shields.io/badge/依賴-0%20個-brightgreen?style=for-the-badge)](./requirements.txt)

*讓 AI 編碼 Agent 的計畫檔案，從「易碎的 Markdown 約定」升級為「可校驗、可還原、可進 CI 的工程資產」。*

</div>

---

## 🎉 專案介紹

### 它解決什麼痛點？

每一位用 AI 編碼 Agent（Claude Code、Cursor、Codex、Copilot…）跑長任務的人，都踩過這些坑：

| 😱 痛點 | 🔥 後果 |
|---|---|
| 執行 `/clear` 或觸發上下文壓縮 | 計畫被壓成一句話，幾十個任務憑空消失 |
| Agent 把 `- [ ]` 改成 `- [x]` 就說做完了 | **程式碼根本沒改**，你在 Review 時才發現 |
| 工作階段中斷後重開一個 | 新工作階段不知道做到哪、下一步是什麼、卡在哪 |
| 改了計畫外的檔案 | 無人知曉，悄悄埋雷 |
| 計畫檔被誤刪／覆蓋 | 沒有歷史，只能憑記憶重寫 |

> 💡 **核心洞察**：`planning-with-files` 這類方案用 Markdown 約定解決了「有沒有計畫」，但它依賴 Agent 自覺維護——**沒有校驗、沒有還原、沒有稽核**。PlanAnchor 補上的正是這三層。

### 自研差異化亮點

🛠️ **從「約定」到「引擎」** — 不只是模板，而是一套可執行的解析器 + 規則引擎，14 條校驗規則 + 7 類漂移偵測 + 6 類停滯偵測。

🧲 **雜湊鏈錨點** — 每次快照形成 `sha256(prev + text)` 雜湊鏈，**歷史不可竄改**，可稽核、可驗證。

🧬 **前向合併還原** — 還原時不會粗暴覆蓋：只在狀態「前進」的方向上合併，你在壓縮後新做的工作也不會丟。

🌊 **計畫漂移偵測** — 交叉比對「計畫聲稱做了什麼」與「Git 實際改了什麼」，揪出**謊報完成**、**靜默改動**、**符號缺失**、**範圍蔓延**。

🧾 **一鍵產生還原簡報** — 輸出可直接貼給新工作階段的提示詞，包含目前任務、後續佇列、阻塞項、關鍵檔案清單。

🚦 **CI 門禁就緒** — 支援 `text` / `json` / `SARIF 2.1.0` / `JUnit XML` / `Markdown` 五種報告格式，一條命令接進任何 CI。

🪶 **真·零依賴** — 只用 Python 標準函式庫。沒有 `requests`、沒有 `click`、沒有 `pydantic`，`pip install` 之後 0 個傳遞依賴。

🔌 **函式庫 + CLI 雙型態** — 既能當命令列用，也能 `import plananchor` 直接程式呼叫。

---

## ✨ 核心特性

### 🔍 結構化解析
- ✅ 相容 GFM 與 Agent 事實標準狀態符號：`[ ]` 待辦 · `[~]` 進行中 · `[x]`/`[X]` 完成 · `[-]` 跳過 · `[!]` 阻塞
- ✅ 自動識別**大綱編號**（`1.2.3`）、**層級縮排**（空格與 Tab 混排也行）
- ✅ 抽取**檔案參照**（`@src/a.py` / `` `src/a.py` ``）、**程式碼符號**（`#func`）、**負責人**（`(owner: x)`）、**備註**（`(note: ...)` / `(blocked: ...)`）
- ✅ 支援 YAML 風格 `---` front matter 標頭

### 📏 14 條校驗規則（PA 系列）

| 規則 | 層級 | 說明 |
|---|---|---|
| `PA001` | 🔴 error | 計畫裡一個任務都沒有 |
| `PA002` | 🔴 error | 任務編號重複 |
| `PA003` | 🟡 warning | 已完成任務沒宣告檔案參照，無法驗證 |
| `PA004` | 🟡 warning | 阻塞任務沒寫原因，下個工作階段無法自救 |
| `PA005` | 🔵 info | 同時進行多個任務，還原時容易亂 |
| `PA006` | 🔴 error | 父任務已關閉但子任務還開著（**邏輯矛盾**） |
| `PA007` | 🔵 info | 有未完成工作卻沒有「進行中」錨點 |
| `PA008` | 🟡 warning | 任務很多卻沒有章節分隔 |
| `PA009` | 🟡 warning | 任務標題為空 |
| `PA010` | 🟡 warning | 巢狀過深（預設 > 4 層） |
| `PA011` | 🟡 warning | 參照的檔案在磁碟上不存在 |
| `PA012` | 🔵 info | 任務缺少驗收標準 |
| `PA013` | 🔵 info | 任務標題重複，簡報會產生歧義 |
| `PA014` | 🔵 info | 大綱編號跳號（通常意味著任務被誤刪） |

> 🎯 支援行內抑制：`- [x] foo <!-- plananchor: ignore PA003 -->`

### 🌊 7 類漂移偵測（DF 系列）

| 規則 | 層級 | 說明 |
|---|---|---|
| `DF001` | 🔴 error | **謊報完成**：標記 done 但參照檔案根本沒改 |
| `DF002` | 🔵 info | **靜默改動**：檔案改了但沒有任務認領 |
| `DF003` | 🟡 warning | **符號缺失**：聲稱改的函式在 diff 裡找不到 |
| `DF004` | 🔵 info | **範圍重疊**：同一檔案被已關閉與進行中的任務同時認領 |
| `DF005` | 🟡 warning | **參照懸空**：參照的檔案 Git 認為沒變化 |
| `DF006` | 🔵 info | **毫無進展**：任務還開著但倉庫零改動 |
| `DF000` | 🔵 info | Git 不可用（優雅降級，絕不崩潰） |

> 🪟 **變更視窗（change window）**：漂移預設比對相對 `HEAD` 的未提交改動。工作區乾淨時（剛 clone 下來、或改動已全部提交）視窗為空，逐任務判定 `DF001` 會把已落地的歷史工作全部誤報為 error —— 此時 PlanAnchor 進入 **settled（已落定）模式**，把結論摺疊成一條 info 級彙總。要審計某段歷史，用 `plananchor drift PLAN.md --base HEAD~5` 顯式放寬視窗。

### 🐌 6 類停滯偵測（ST 系列）

`ST001` 長期卡在同一任務 · `ST002` 狀態反覆橫跳 · `ST003` 阻塞項級聯影響下游 · `ST004` 整體進度原地踏步 · `ST005` 首個任務被遺棄 · `ST006` 沒有任何「進行中」錨點

### 🧲 抗壓縮錨點
- ⛓️ **雜湊鏈**：`sha256(prev + text)`，竄改任一歷史快照都會被 `verify` 抓到
- 🔁 **前向合併**：還原時保留只進不退的狀態變更，壓縮後的新進度不丟
- 🧹 **自動剪枝**：`--keep N` 保留最近 N 個快照並自動重連雜湊鏈
- 📸 **乾跑模式**：`--dry-run` 先看看會還原成什麼，不落盤

### 📊 五種報告格式

`text`（終端機彩色）· `json`（儀表板）· `sarif`（GitHub Code Scanning / IDE）· `junit`（測試報告 UI）· `md`（PR 留言）

---

## 🚀 快速開始

### 環境要求

| 項目 | 要求 |
|---|---|
| Python | **3.8+**（3.8 / 3.9 / 3.10 / 3.11 / 3.12 全數 CI 驗證） |
| 作業系統 | 🐧 Linux · 🍎 macOS · 🪟 Windows |
| 第三方依賴 | **無**（Python 標準函式庫即可） |
| Git（選用） | 僅漂移偵測需要；沒有 Git 會優雅降級而非報錯 |

### 安裝

```bash
# 方式一：從原始碼安裝（推薦，零依賴）
git clone https://github.com/gitstq/PlanAnchor.git
cd PlanAnchor
pip install -e .

# 方式二：免安裝，直接用
python -m plananchor --help

# 方式三：後續 PyPI 發布後
pip install plananchor
```

### 30 秒上手

```bash
# ① 產生一份計畫模板
plananchor init PLAN.md

# ② 看完整分析（校驗 + 漂移 + 停滯）
plananchor status PLAN.md

# ③ 儲存一個還原錨點（每次階段性完成都該做）
plananchor snapshot PLAN.md -m "完成解析引擎"

# ④ 上下文被壓縮後，一鍵還原
plananchor restore PLAN.md

# ⑤ 產生可直接貼給新工作階段的還原簡報
plananchor resume PLAN.md -o RESUME.md
```

### 計畫檔案長什麼樣？

```markdown
---
project: my-service
owner: agent
---

# 重構使用者服務

## 階段一 · 資料層

- [~] 1.1 定義資料模型 `@src/model.py` #User
- [x] 1.2 實作解析器 `@src/parser.py` #parse_text
  - [x] 1.2.1 處理巢狀縮排
  - [ ] 1.2.2 處理狀態符號 (accept: 5 種符號全覆蓋)
- [ ] 1.3 補單元測試 `@tests/test_parser.py` (accept: 覆蓋率 ≥ 90%)

## 階段二 · 交付

- [!] 2.1 發布套件 (blocked: 等待 registry token)
- [-] 2.2 遷移舊腳本 (note: 已廢棄)
```

**狀態符號速查**

| 符號 | 含義 | 符號 | 含義 |
|---|---|---|---|
| `[ ]` | 待辦 | `[x]` / `[X]` | 完成 |
| `[~]` | 進行中（**還原錨點**） | `[-]` | 已跳過 |
| `[!]` | 阻塞（**建議寫原因**） | | |

---

## 📖 詳細使用指南

### 命令一覽

| 命令 | 作用 | 常用參數 |
|---|---|---|
| `status` | 全量分析（校驗 + 漂移 + 停滯） | `--no-git` `--fail-on warning` |
| `check` | 只做校驗 | `--no-refs` `--max-depth 3` |
| `drift` | 只做漂移偵測 | `--base HEAD~1` `--ignore dist/` |
| `parse` | 印出任務樹 | `--json` `--stats` |
| `snapshot` | 建立錨點 | `-m "備註"` `--keep 50` |
| `restore` | 從錨點還原 | `--seq 3` `--exact` `--dry-run` |
| `verify` | 校驗雜湊鏈 | — |
| `resume` | 產生還原簡報 | `--lang en` `--next 5` `-o FILE` |
| `init` | 產生模板 | `--force` |
| `rules` | 印出規則目錄 | `--json` |

### 全域參數

```
-f, --format   text|json|sarif|junit|md    報告格式（預設 text）
-o, --output   PATH                         寫入檔案而非 stdout
```

**結束碼**：`0` 通過 · `1` 命中設定層級的發現項 · `2` 用法錯誤 · `3` 輸入檔案缺失

### 典型場景

#### 🎯 場景一：每次提交前做 CI 門禁

```bash
# 只有 error 層級才失敗
plananchor check PLAN.md --fail-on error

# 更嚴格：warning 也讓 CI 掛掉，並產出 SARIF 給 GitHub
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

#### 🎯 場景二：長任務的 Agent 迴圈（核心用法）

```bash
# 每個里程碑之後立刻打錨點 —— 這是抗壓縮的唯一保險
plananchor snapshot PLAN.md -m "階段一完成"

# 新工作階段 / 壓縮後 / 崩潰後，先還原再繼續
plananchor restore PLAN.md
plananchor resume PLAN.md -o RESUME.md   # 把 RESUME.md 貼給 Agent
```

> 💡 **最佳實踐**：把 `plananchor snapshot` 寫進 Agent 的指令檔（AGENTS.md / CLAUDE.md），讓它每完成一個任務就自動打錨點。

#### 🎯 場景三：稽核 Agent 是不是在「假裝做事」

```bash
# 比對計畫聲稱 vs 倉庫實際
plananchor drift PLAN.md --base HEAD~5
```

輸出範例：

```
❌ DF001  任務「實作解析器」標記已完成，但其檔案均未改動：src/parser.py
   ↳ 把勾選框改回 `[ ]`，或真正提交改動
```

#### 🎯 場景四：行內抑制誤報

```markdown
- [x] 1.5 更新文件 `@docs/` <!-- plananchor: ignore PA003, PA011 -->
        <!-- 整行全抑制：plananchor: ignore -->
```

#### 🎯 場景五：只想要機器可讀結果

```bash
plananchor status PLAN.md -f json | jq '.summary'
plananchor check PLAN.md -f junit -o report.xml
plananchor status PLAN.md -f md -o comment.md   # 貼到 PR
```

### Python API

```python
from plananchor import parse_file, validate_plan, detect_drift, AnchorStore, build_resume
from plananchor.resume import render_brief

# 1️⃣ 解析
plan = parse_file("PLAN.md")
print(plan.progress(), plan.counts())     # 33.3  {'done':1,'active':1,...}

# 2️⃣ 校驗
for f in validate_plan(plan, max_depth=4):
    print(f.rule, f.severity.value, f.message, f.line)

# 3️⃣ 漂移
drift = detect_drift(plan, repo=".", base="HEAD")
if not drift.clean:
    for item in drift.items:
        print(item.rule, item.message)

# 4️⃣ 錨點：儲存 / 偵測壓縮 / 還原
store = AnchorStore("PLAN.md")
store.create(plan, note="milestone 1")
signal = store.detect_compaction(plan)
if signal.compacted:
    text, _ = store.restore("PLAN.md")        # 前向合併還原
print(store.verify().ok)                       # True

# 5️⃣ 還原簡報
brief = build_resume(plan, store=store, drift=drift, lang="zh")
open("RESUME.md", "w").write(render_brief(brief))
```

**可用模組**

| 模組 | 職責 |
|---|---|
| `plananchor.parser` | Markdown 解析 / 規範化回寫 |
| `plananchor.model` | `Plan` / `Task` / `Finding` 資料模型 |
| `plananchor.validate` | 14 條 PA 規則 |
| `plananchor.drift` | 7 類 DF 漂移偵測 |
| `plananchor.stall` | 6 類 ST 停滯偵測 |
| `plananchor.anchor` | 快照、雜湊鏈、還原 |
| `plananchor.resume` | 還原簡報產生 |
| `plananchor.report` | 五格式報告渲染 |
| `plananchor.gitutil` | 極簡 Git 整合（無第三方依賴） |

---

## 💡 設計思路與迭代規劃

### 為什麼堅持零依賴？

Agent 生態裡，工具會被塞進各種不可控環境——容器、CI、離線機器、別人的專案。多一個依賴就多一個「裝不上」的可能。PlanAnchor 用純標準函式庫實作，**拷貝一個目錄就能跑**，這是刻意的架構選擇。

### 為什麼用雜湊鏈而不是普通備份？

普通備份能被靜默改寫。雜湊鏈讓「歷史」本身變成可驗證物件：任何人（包括你三個月後）都能 `plananchor verify` 確認還原依據沒有被污染。

### 為什麼漂移偵測要讀檔案內容而不只看 diff？

`git diff` 只顯示**移動過的行**。如果目標符號在早期提交裡已經存在，純 diff 判定會誤報。PlanAnchor 同時檢查 diff 新增行與檔案目前內容，顯著降低誤報率。

### 技術選型

| 選擇 | 理由 |
|---|---|
| Python 3.8+ | 覆蓋面最廣，Agent 生態主流環境 |
| `dataclasses` | 零依賴、可序列化、型別清晰 |
| `argparse` | 標準函式庫 CLI，無 `click` 依賴 |
| `subprocess` 呼叫 git | Git 是系統工具，不算 Python 依賴 |
| `hashlib.sha256` | 標準函式庫雜湊鏈 |

### 迭代規劃 🗺️

- [ ] 🔌 MCP Server 型態，讓 Agent 直接呼叫 `snapshot` / `resume`
- [ ] 🌐 計畫檔多語言（日 / 韓 / 西）簡報輸出
- [ ] 📈 進度曲線視覺化（ASCII + HTML）
- [ ] 🤖 Agent 指令檔產生器（`AGENTS.md` / `CLAUDE.md` 自動注入快照鉤子）
- [ ] 🔗 多計畫檔聯邦（子專案計畫聚合）
- [ ] 🧪 基於快照的「任務回放」回歸測試

---

## 📦 打包與部署指南

PlanAnchor 屬於**工具函式庫 / CLI 類專案**，無需上傳 Release 二進位套件；透過套件管理器與原始碼兩種方式分發。

### 本機打包

```bash
# 建置 sdist + wheel
make build          # 等價於 python -m build

# 產物
ls dist/
#   plananchor-1.0.0.tar.gz
#   plananchor-1.0.0-py3-none-any.whl
```

### 安裝 Wheel

```bash
pip install dist/plananchor-1.0.0-py3-none-any.whl
plananchor --version
```

### 單目錄免安裝部署

因為零依賴，整個套件可以直接搬走：

```bash
cp -r plananchor /目標專案/vendor/
cd /目標專案 && PYTHONPATH=vendor python -m plananchor status PLAN.md
```

### 發布到 PyPI（維護者）

```bash
make release                     # clean + build
python -m twine check dist/*
python -m twine upload dist/*
```

### 整合進 Docker

```dockerfile
FROM python:3.11-slim
COPY plananchor /app/plananchor
COPY PLAN.md /app/PLAN.md
WORKDIR /app
CMD ["python", "-m", "plananchor", "status", "PLAN.md"]
```

### 相容環境矩陣

| Python | Linux | macOS | Windows |
|:---:|:---:|:---:|:---:|
| 3.8 | ✅ | ✅ | ✅ |
| 3.9 | ✅ | ✅ | ✅ |
| 3.10 | ✅ | ✅ | ✅ |
| 3.11 | ✅ | ✅ | ✅ |
| 3.12 | ✅ | ✅ | ✅ |

> ⚠️ Git 漂移偵測需要系統安裝 `git`；缺失時工具降級為純計畫校驗，不會報錯退出。

---

## 🤝 貢獻指南

歡迎 PR！請遵循以下規範：

### 提交規範（Angular 約定）

```
feat: 新增 XX 規則
fix: 修復巢狀縮排解析錯誤
docs: 補充繁體中文文件
refactor: 重構報告渲染層
test: 補充漂移偵測案例
chore: 更新 CI 矩陣
```

### PR 流程

1. 🍴 Fork 本倉庫並新建分支（`feat/xxx` / `fix/xxx`）
2. 🧪 撰寫程式碼 + 對應單元測試
3. ✅ 確保 `make test` 全綠（**零依賴，不需要裝任何測試函式庫**）
4. 🏗️ 確保 `make build` 成功
5. 📝 更新相關文件（簡 / 繁 / 英 三語同步）
6. 🚀 提交 PR，描述清楚改動動機與驗證方式

### Issue 回報

請包含：
- PlanAnchor 版本、Python 版本、作業系統
- 重現用的最小計畫檔（Markdown）
- 實際輸出 vs 期望輸出

### 開發約定

- 🚫 **禁止引入任何第三方執行期依賴** —— 這是專案的核心約束
- 📐 新規則必須有穩定 `PAxxx` / `DFxxx` / `STxxx` 編號並登記進 `rules_catalog()`
- 🧪 新規則必須有對應單元測試
- 🔤 公開函式必須有 docstring（含 Args / Returns / Raises）

---

## 📄 開源協議說明

本專案基於 **MIT License** 開源，詳見 [LICENSE](./LICENSE)。

- ✅ 允許商用、修改、分發、私有化部署
- ✅ 允許閉源二次整合
- ⚠️ 需保留原始版權聲明與協議文本
- ❌ 作者不承擔任何使用風險與責任

---

<div align="center">

**🧭 PlanAnchor** — 讓 AI Agent 的計畫，不再隨風而散。

如果這個專案幫到了你，歡迎 ⭐ Star 支持！

</div>
