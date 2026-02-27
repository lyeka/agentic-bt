# scripts/ — 分析工具集

## analyze_trace.py

分析 AgenticBT 回测产生的 `trace.jsonl`，输出 agent 工具调用统计报告。

### 用法

```bash
# 分析已有 trace 文件
.venv/bin/python scripts/analyze_trace.py --trace-file /path/to/trace.jsonl

# 自定义错误率阈值（默认 50%）
.venv/bin/python scripts/analyze_trace.py --trace-file /path/to/trace.jsonl --threshold 30

# 指定 JSON 输出路径（默认写入 trace 同目录的 analysis.json）
.venv/bin/python scripts/analyze_trace.py --trace-file /path/to/trace.jsonl --json-out ./report.json
```

trace 文件由 `demo.py` 运行时自动生成，路径见运行输出末尾的 workspace 目录：

```bash
# 先跑一次 demo 拿到 trace
python demo.py --mock --strategy quant_compute
# 输出中找到 workspace: /tmp/agenticbt/run_xxx/
# 然后分析
.venv/bin/python scripts/analyze_trace.py --trace-file /tmp/agenticbt/run_xxx/trace.jsonl
```

### 报告结构

| Section | 内容 |
|---------|------|
| Overview | 策略、模型、bar/round/tool call 总数 |
| Tool Summary | 每个工具的调用次数、成功率、平均耗时 |
| Per-Bar Breakdown | 逐 bar 的 round 数、工具调用数、compute 错误数 |
| Compute Error Analysis | 错误分类、跨 bar 重复模式、helper 使用率 |
| Error Samples | 每类错误的首个样本（含代码片段） |
| Verdict | PASS/FAIL（基于 compute 错误率阈值） |

### 输出

- 终端：格式化文本报告
- JSON：`analysis.json`（供 AI 后续分析和回归对比）
