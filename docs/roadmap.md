# Roadmap — 开发路线图

> 从能跑到好用，从单一到丰富。
> 每个阶段都是完整可用的产品。

## 总体原则

```
1. 每个版本都是完整的——能跑起来，能出结果
2. 先做最小闭环，再扩展能力
3. 优化是验证正确性之后的事
4. 复杂度必须有对应的价值
```

## MVP — 最小完整回测

**目标**：一个 LLM Agent 在历史数据上做交易决策，跑完一轮回测，产出三维评估报告。

### 范围

```
包含:
  ✓ Engine: 数据回放、指标计算、市场订单撮合、仓位核算
  ✓ Tools: market + indicator + account + trade + memory (5 工具组)
  ✓ Memory: playbook + journal + notes，文件存储，关键词 recall
  ✓ Context: 分层组装，tabular 格式
  ✓ Agent: LLM Agent (Claude/OpenAI)，单一 AgentProtocol
  ✓ Runner: 主循环，EVERY_BAR 触发，框架驱动记忆时刻
  ✓ Eval: 绩效指标 + 遵循度报告
  ✓ 工作空间隔离

不包含:
  ✗ Limit/Stop 订单
  ✗ 指标缓存优化
  ✗ 上下文 token 预算管理
  ✗ 一致性评估 (需要多次 run)
  ✗ 矩阵实验
  ✗ 扩展工具 (MCP/Skills)
  ✗ 多资产
  ✗ 规则引擎 Agent
  ✗ recall 的 vector search
```

### MVP 验收标准

```
1. 用户可以:
   - 用自然语言描述一个策略
   - 选择一个 LLM 模型
   - 提供历史数据 (DataFrame)
   - 运行回测

2. 回测过程:
   - Agent 每根 bar 做一次决策
   - Agent 可调用 5 个核心工具组
   - Agent 可记录和回忆交易记忆
   - 所有决策被完整记录

3. 回测结果:
   - 收益率、夏普、最大回撤等绩效指标
   - 遵循度报告 (定量规则)
   - 完整的决策审计记录
   - 可浏览的 workspace 目录
```

### MVP 技术选型

```
语言: Python 3.12+
数据: Pandas DataFrame
LLM: litellm (统一调用 Claude/OpenAI/...)
指标: ta-lib 或 pandas-ta
序列化: JSON / JSONL
测试: pytest
```

## V2 — 完整评估与实验

**目标**：完整的三维评估体系，支持多维对比实验。

### 新增能力

```
评估:
  + 一致性评估 (随机一致性、场景一致性)
  + LLM-as-Judge 合规评估 (定性规则)
  + 遵循度 × 绩效 二维矩阵报告

实验:
  + 矩阵实验 (run_matrix)
  + Prompt A/B 测试
  + Model A/B 测试

引擎:
  + Limit / Stop 订单
  + 可配置手续费和滑点模型
  + 多资产支持

Agent:
  + 规则引擎 Agent (对照基准)
  + Agent vs Baseline 对比
  + temperature / max_tool_rounds 配置

记忆:
  + 阶段性总结 (周/月 review)
  + 时间衰减 recall
```

## V3 — 扩展与优化

**目标**：生态扩展，性能优化，生产级品质。

### 新增能力

```
扩展:
  + MCP Server 接入
  + Skills 机制
  + 自定义指标注册

优化:
  + 指标计算缓存
  + 上下文 token 预算管理
  + recall 升级: BM25 + vector hybrid search

体验:
  + 回测可视化 (权益曲线、决策时间线)
  + 交互式回测 (Human Agent)
  + 回测报告导出 (HTML/PDF)

高级:
  + 跨 run 记忆迁移
  + 记忆蒸馏 (多次 run 提炼共同经验)
  + 模型敏感性分析
  + Playbook 演化追踪
```

## V4 — 多 Agent 与实盘

**目标**：探索多 Agent 协作和实盘桥接。

### 新增能力

```
多 Agent:
  + 分析师 Agent + 交易员 Agent 协作
  + 风控 Agent 独立评估
  + Agent 间通信协议

实盘桥接:
  + 实盘数据源接入
  + 模拟→实盘 渐进切换
  + 实时风控

社区:
  + 策略 Prompt 分享
  + Playbook 模板库
  + 回测结果排行榜
```

## 里程碑概览

```
MVP  ── 最小闭环 ──  能跑、能评 ──────────── 验证核心架构
 │
V2   ── 完整评估 ──  能比、能测 ──────────── 验证评估体系
 │
V3   ── 扩展优化 ──  能扩、能优 ──────────── 验证扩展机制
 │
V4   ── 多Agent  ──  能协作、能实盘 ──────── 探索边界
```

## 开发优先级原则

```
1. 正确性 > 性能 > 美观
   先确保回测结果正确，再考虑速度，最后美化体验

2. 闭环 > 功能
   一个完整的简单闭环比十个未完成的功能更有价值

3. 可审计 > 可优化
   Decision 记录的完整性比指标缓存更重要

4. 用户体验 > 代码优雅
   如果牺牲代码简洁能让用户更容易上手，就牺牲
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
