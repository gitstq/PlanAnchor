# 🤝 贡献指南 / Contributing / 貢獻指南

感谢你愿意让 PlanAnchor 变得更好！🎉

Thanks for making PlanAnchor better! 🎉
感謝你願意讓 PlanAnchor 變得更好！🎉

---

## 🚀 快速上手开发环境

```bash
git clone https://github.com/gitstq/PlanAnchor.git
cd PlanAnchor
make install        # pip install -e .（零依赖，秒装）
make test           # 跑完整单元测试
make demo           # 端到端演示
make build          # 构建 sdist + wheel
```

> 💡 项目**零第三方依赖**，不需要 `pip install -r requirements-dev.txt`，也不需要 `pytest` —— 测试直接用 `unittest`。

---

## 📐 提交规范（Angular Convention）

```
<type>: <subject>

[optional body]
[optional footer]
```

**type 白名单**

| type | 含义 | 示例 |
|---|---|---|
| `feat` | 新增功能 | `feat: 新增 PA015 循环依赖检测` |
| `fix` | 修复问题 | `fix: 修复 Tab 缩排解析错误` |
| `docs` | 文档更新 | `docs: 同步繁体中文文档` |
| `refactor` | 代码重构 | `refactor: 抽出报告渲染层` |
| `test` | 测试相关 | `test: 补充哈希链篡改用例` |
| `chore` | 构建/杂项 | `chore: 升级 CI 到 Python 3.12` |
| `perf` | 性能优化 | `perf: 缓存文件符号扫描结果` |

**规则**
- 📝 subject 用中文或英文均可，但**同一 commit message 内不混用**
- 🔤 subject 首字母不大写，结尾不加句号
- 📏 subject 控制在 72 字符内

---

## 🔀 PR 流程

1. 🍴 **Fork** 本仓库
2. 🌿 新建分支：`feat/your-feature` 或 `fix/your-bug`
3. ✍️ 编写代码，**同步更新中 / 繁 / 英三语文档**
4. 🧪 补充单元测试
5. ✅ 本地全量验证：

```bash
make test           # 必须全绿
make build          # 必须成功
make demo           # 端到端必须跑通
```

6. 📤 推送并发起 PR

### PR 描述模板

```markdown
## 动机
（为什么需要这个改动）

## 改动内容
- ...
- ...

## 验证方式
- [ ] `make test` 全绿
- [ ] `make build` 成功
- [ ] 新增规则的单元测试已覆盖
- [ ] 三语文档已同步

## 相关 Issue
Closes #xxx
```

---

## 🚫 硬性约束（会被直接拒绝的改动）

| 约束 | 原因 |
|---|---|
| ❌ 引入任何第三方**运行时**依赖 | 项目核心卖点就是零依赖 |
| ❌ 新增规则不给 `PAxxx` / `DFxxx` / `STxxx` 编号 | 破坏 CI 基线与抑制注释的稳定性 |
| ❌ 新增规则不登记进 `rules_catalog()` | `plananchor rules` 会漏项 |
| ❌ 新增代码没有单元测试 | 覆盖率是发布门槛 |
| ❌ 只改代码不更新文档 | 文档与代码必须同步 |
| ❌ 机翻式文档 | 必须母语级表达 |

---

## 🧩 新增一条规则的完整步骤

1. 在 `plananchor/validate.py`（或 `drift.py` / `stall.py`）中实现 `_rule_xxx()`
2. 在对应 `validate_plan()` / `detect_drift()` / `detect_stalls()` 中注册
3. 在 `rules_catalog()`（或 `_RULE_TEXT`）中登记编号、级别、摘要
4. 在 `tests/` 中补充**正向 + 反向**两个用例（即「应该报」和「不该报」）
5. 更新三语 README 的规则表格
6. 提 PR

---

## 🐛 Issue 反馈

请包含以下信息，能极大加快定位：

```
PlanAnchor 版本：x.y.z     （plananchor --version）
Python 版本：3.x.x
操作系统：Linux / macOS / Windows
Git 版本：（漂移检测相关时）

最小复现计划文件：
```markdown
- [x] 1 复现步骤 `@a.py`
```

实际输出：
期望输出：
```

---

## 📄 行为准则

- 🤝 友善、具体、对事不对人
- 🎯 讨论聚焦技术本身
- 🌍 中英文都可以，不必为语言道歉

---

再次感谢！每一个 PR 都会让更多 Agent 的计划不再随风而散。🧭
