# docs/
> L2 | 父级: /CLAUDE.md

AgenticBT 完整设计文档集，指导全部开发工作。

## 成员清单

architecture.md: 架构总览，设计哲学，模块关系图，与现有框架对比
engine.md: 确定性引擎，数据回放/指标计算/订单撮合/仓位核算/风控拦截
tools.md: 五个核心工具组设计，market/indicator/account/trade/memory 接口定义
compute.md: 沙箱化 Python 计算工具设计，eval-first 策略/Trading Coreutils/安全边界/可行性审查
memory.md: 文件式记忆系统，工作空间隔离，log/note/recall 工具，受 OpenClaw 启发
context.md: 上下文工程，六层分层注入，市场数据格式，token 预算管理
eval.md: 三维评估体系，绩效/遵循度/一致性，A/B 测试矩阵
agent-protocol.md: AgentProtocol 接口规范，Decision 数据结构，多种 Agent 类型
runner.md: 回测编排器，主循环流程，触发策略，框架驱动记忆时刻，矩阵实验
tracer.md: Agent 可观测性，trace.jsonl 格式定义，对齐 OTel GenAI Semantic Conventions，观测点注入
roadmap.md: 开发路线图，MVP 范围定义，V2/V3/V4 演进规划

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
