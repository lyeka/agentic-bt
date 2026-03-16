# AthenaClaw

## Repo Map

```text
src/athenaclaw/  - 主产品代码
docs/            - 架构与设计文档
tests/           - 自动化测试
.agents/         - skills / subagents 资产
scripts/         - 辅助脚本
```

## Current Shape

- 单一产品：AthenaClaw
- 单一顶层包：`athenaclaw`
- 单一测试主线：围绕当前 agent 能力

## Development Rule

- 保持 Kernel-centric 设计
- 不重新引入历史产品残留或新的共享顶层包
- 新功能优先放入现有边界：`kernel`、`runtime`、`llm`、`tools`、`automation`、`skills`、`subagents`、`interfaces`、`integrations`、`observability`
