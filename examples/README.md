# 📚 PlanAnchor 示例

| 文件 | 说明 |
|---|---|
| [`PLAN-demo.md`](./PLAN-demo.md) | 通过 `plananchor init` 生成的计划模板，含五种状态符号、嵌套任务、阻塞项 |
| [`ci-gate.sh`](./ci-gate.sh) | 可直接拷贝到项目里的 CI 门禁脚本 |
| [`agent-loop.sh`](./agent-loop.sh) | Agent 长任务循环：每个里程碑打锚点 + 中断后自动恢复 |

## 试一试

```bash
cd PlanAnchor
python -m plananchor parse   examples/PLAN-demo.md
python -m plananchor check   examples/PLAN-demo.md --no-refs
python -m plananchor snapshot examples/PLAN-demo.md -m "第一次锚定"
python -m plananchor resume  examples/PLAN-demo.md --lang en
```
