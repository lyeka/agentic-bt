# Tracer

AthenaClaw 的 trace 是本地 JSONL 文件。

## 目标

- 记录 turn、llm、tool、subagent、memory、context 事件
- 不依赖外部 observability 服务
- 让 CLI、IM、automation worker 使用统一事件格式

## 存储位置

默认写入：

```text
~/.athenaclaw/state/traces/<adapter>/<conversation>.jsonl
```

## 事件来源

- `turn.*`
- `llm.*`
- `tool.*`
- `tool:*`
- `subagent.*`
- `memory.compressed`
- `context.*`

## 设计约束

- trace 由 runtime wiring 挂载，不侵入业务逻辑
- 每条记录都包含 UTC 时间戳
- 记录格式面向后续脚本分析和人工排查，不面向专有平台
