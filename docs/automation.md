---
title: Automation Task System
status: active
---

# Automation Task System

## 1. 目标

自动化子系统服务两类场景：

- 定时触发某个 SOP/skill/main agent，生成分析并主动推送给用户
- 低成本监控事件，在事件真正发生后再启动 agent 做分析或发送告警

设计目标：

- 检测面便宜：轮询和定时判断不调用 LLM
- 反应面 agentic：事件触发后由主 agent、skill 或 subagent 自主决定后续研究
- 对话面清晰：自动执行和人工 follow-up 不共用 session，但可以自然衔接
- 定义可审计：任务定义可读、可确认、可手工检查

非目标：

- 不做工作流编排平台
- 不做自动交易
- 不允许自动化任务直接修改 `workspace/automation/tasks/**`

## 2. 核心抽象

系统只保留三个一级概念：

- `Trigger`
  - 确定性检测器，负责“什么时候触发”
- `Reaction`
  - 事件发生后执行一次，负责“由谁来处理”
- `Delivery`
  - 决定“什么时候、发到哪里”

这三层对应当前实现：

- Trigger
  - `cron`
  - `price_threshold`
- Reaction executor
  - `main_agent`
  - `skill`
  - `subagent`
- Delivery phase
  - `pre_alert`
  - `final_result`
  - `on_failure`

## 3. Task 生命周期

任务创建采用两阶段模型：

1. 用户在 IM/CLI 中用自然语言提出需求
2. agent 调 `task_plan` 生成结构化草案和预览
3. 用户确认后，agent 调 `task_apply`
4. 系统把定义写入 `workspace/automation/tasks/<task_id>.yaml`
5. worker 扫描到 active task 后开始调度

`task_plan` 只负责归一化和校验，不直接生效。  
`task_apply` 才会落地定义并初始化 runtime state。

## 4. 存储布局

任务定义和运行状态分开保存：

```text
workspace/
  automation/tasks/<task_id>.yaml
  notebook/automation/<task_id>/<run_id>.md

state/
  automation/drafts/<draft_id>.json
  automation/tasks/<task_id>.json
  automation/runs/<task_id>/<run_id>.json
  automation/receipts/<channel>/<target>/<message_id>.json
  sessions/automation/<task_id>.json
```

含义：

- `workspace/automation/tasks/*.yaml`
  - 用户可审计、可备份的任务定义
- `state/automation/tasks/*.json`
  - 运行态状态，如 `next_fire_at`、`last_side`、`cooldown_until`
- `state/automation/runs/**`
  - 单次触发记录
- `state/automation/receipts/**`
  - 主动推送消息和 `run_id/task_id` 的绑定关系
- `state/sessions/automation/*.json`
  - 自动任务自己的执行 session

## 5. Trigger 语义

### 5.1 Cron

字段：

- `cron_expr`
- `timezone`
- `misfire_grace_sec`

规则：

- 只支持普通 wall-clock cron
- 不支持“收盘后”“交易日前”这类市场日历语义
- 如果自然语言里包含这类语义，`task_plan` 返回 `needs_clarification`
- worker 只在 `misfire_grace_sec` 内补跑一次；超窗直接跳过并推进下一次计划时间

### 5.2 Price Threshold

字段：

- `symbol`
- `interval`
- `condition`
- `threshold`
- `poll_sec`
- `cooldown_sec`
- `max_data_age_sec`

规则：

- monitor 直接调用 market adapter，不经过 Kernel，不调用 LLM
- 只有真正发生 `cross_above` / `cross_below` 时才触发
- 触发后进入 cooldown
- 价格回到阈值另一侧后才重新布防
- 行情超过 `max_data_age_sec` 视为陈旧，不触发

## 6. Reaction 语义

Reaction 不是 workflow，而是“一次执行”。

支持三种 executor：

- `main_agent`
  - 调 `Kernel.turn(rendered_prompt, task_session)`
- `skill`
  - 调 `Kernel.turn("/skill:name " + rendered_prompt, task_session)`
- `subagent`
  - 调现有 `SubAgentSystem.invoke(name, rendered_prompt, context)`

设计原则：

- 平台只给 Reaction 一个轻量 `TriggerEvent`
- 如果还要继续研究，由 agent 自己再用 `market_ohlcv`、`compute`、`task_context` 或 skill/subagent 去拿更多信息
- 平台不预编排“自动采集 N 份数据再分析”

这样可以把 token 消耗压到“事件真正发生之后”。

## 7. Delivery 语义

每次 run 支持三个投递阶段：

- `pre_alert`
  - 事件刚触发时发短消息，不等 LLM
- `final_result`
  - Reaction 完成后发结论
- `on_failure`
  - Reaction 失败时发失败通知

当前 delivery channel：

- `discord`
- `telegram`
- `webhook`
- `none`

所有主动推送都会记录 `DeliveryReceipt`，用于后续 reply-to-run 绑定。
如果任务是在 Telegram/Discord 当前私聊会话里创建的，只写对应 `channel.type` 即可；系统会自动补当前 `conversation_id` 作为 target。

## 8. 对话桥接

自动化执行和人工 follow-up 明确分离：

- 自动执行使用 `task session`
- 用户聊天继续使用原 IM human session

如果用户回复了一条自动化推送消息：

1. IM adapter 解析 `reply_to_message_id`
2. IM driver 从 receipt store 反查 `task_id/run_id`
3. 当前轮输入附带轻量 `ContextRef`
4. agent 如需更多上下文，再调用 `task_context`

注意：

- 系统不会把旧 run 摘要直接塞进 prompt
- `ContextRef` 只是 selector，不是内容注入
- 这样能避免隐式状态污染主会话

## 9. Tool Surface

只暴露 4 个中层工具给 agent：

- `task_plan`
  - 生成任务草案和预览
- `task_apply`
  - 确认后生效草案
- `task_context`
  - 查询 task/run 状态、最近 runs、artifact 摘要
- `task_control`
  - `pause / resume / archive`

不直接暴露一堆细碎的 `run_get/task_get/...` 工具，原因是：

- 更容易让 LLM 选对工具
- 权限模型更清晰
- 审计维度更稳定

## 10. 安全边界

自动化任务默认套用 `AutomationToolPolicy`：

- 禁止 `bash`
- 禁止 `task_plan / task_apply / task_control`
- 禁止访问 `soul.md`、`memory.md`
- 禁止访问 `workspace/automation/tasks/**`
- 默认禁止写文件
- 只有 `report_writer` profile 才允许写 `notebook/automation/<task_id>/**`

同时，通用 `write/edit` 工具也显式拒绝修改 `automation/tasks/**`，任务定义只能通过 `task_apply` 生效。

## 11. 幂等与恢复

当前实现的稳定性约束：

- `run_id = task_id + event_key`
- executor 先查 run，已存在则直接返回，避免重复执行
- cron event key 使用计划触发时间
- price threshold event key 使用触发方向 + `as_of`
- worker 重启后，如果同一个事件再次被扫描到，会命中已有 run

当前 v1 没有做分布式锁和多实例调度；worker 默认单实例运行。

## 12. 示例

### 12.1 定时早报

```yaml
id: daily-watchlist
name: Daily Watchlist
description: 每天开盘前给我一份自选股观察
status: active
trigger:
  type: cron
  cron_expr: "0 8 * * 1-5"
  timezone: Asia/Shanghai
reaction:
  executor:
    type: main_agent
  prompt_template: |
    请检查我关注的标的，给出今天需要重点跟踪的变化。
  tool_profile: analysis
  budget:
    max_rounds: 6
    timeout_sec: 90
delivery:
  pre_alert:
    enabled: false
    channels:
      - type: discord
        target: "987654321012345678"
  final_result:
    enabled: true
    channels:
      - type: discord
        target: "987654321012345678"
  on_failure:
    enabled: true
    channels:
      - type: discord
        target: "987654321012345678"
```

### 12.2 价格阈值监控

```yaml
id: aapl-breakout
name: AAPL Breakout
description: AAPL 上穿 220 后做一次分析
status: active
trigger:
  type: price_threshold
  symbol: AAPL
  interval: 1m
  condition: cross_above
  threshold: 220
  poll_sec: 60
  cooldown_sec: 600
  max_data_age_sec: 120
reaction:
  executor:
    type: skill
    name: research
  prompt_template: |
    AAPL 刚刚上穿 220。请判断这次突破是否值得继续跟踪。
  tool_profile: analysis
  budget:
    max_rounds: 6
    timeout_sec: 90
delivery:
  pre_alert:
    enabled: true
    channels:
      - type: telegram
        target: "123456"
  final_result:
    enabled: true
    channels:
      - type: telegram
        target: "123456"
  on_failure:
    enabled: true
    channels:
      - type: telegram
        target: "123456"
```

## 13. 当前限制

- cron 不支持市场日历
- worker 默认单实例
- `subagent` executor 按次执行，不维护独立长期 session
- timeout 目前是 budget 字段，尚未做强制中断
- invalid task 文件目前不会进入独立“invalid”状态机
