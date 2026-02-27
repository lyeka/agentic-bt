# Eval — 三维评估体系

> 传统回测只回答一个问题："策略赚钱吗？"
> Agent 回测必须回答三个问题。

## 三个评估维度

```
维度一: Performance  (绩效)     传统维度，策略赚不赚钱
维度二: Compliance   (遵循度)   Agent 是否遵守策略规则
维度三: Consistency  (一致性)   Agent 决策是否稳定可复现
```

## 维度一：绩效评估 (Performance)

与传统回测框架相同的量化指标。

### 收益指标

| 指标 | 说明 |
|------|------|
| Total Return | 总收益率 |
| CAGR | 年化复合收益率 |
| Monthly Returns | 月度收益分布 |
| Best/Worst Trade | 最佳/最差单笔交易 |

### 风险指标

| 指标 | 说明 |
|------|------|
| Max Drawdown | 最大回撤 |
| Sharpe Ratio | 夏普比率 |
| Sortino Ratio | 索提诺比率 |
| Calmar Ratio | 卡尔马比率 |
| Volatility | 波动率 |

### 交易指标

| 指标 | 说明 |
|------|------|
| Win Rate | 胜率 |
| Profit Factor | 盈亏比 |
| Avg Trade Return | 平均单笔收益 |
| Avg Holding Period | 平均持仓天数 |
| Trade Count | 总交易笔数 |

### 对比指标（如有基准）

| 指标 | 说明 |
|------|------|
| Alpha | 超额收益 |
| Beta | 市场敏感度 |
| Information Ratio | 信息比率 |

## 维度二：策略遵循度 (Compliance)

**Agent 回测独有的维度。** 衡量 Agent 是否按照 playbook 中的规则行事。

### 评估方法

```
Step 1: 规则提取
  从 playbook (strategy prompt) 中提取可量化的规则:

  原文: "只在 RSI 低于 30 时买入"
  → Rule(name="buy_when_RSI_lt_30", type="quantitative",
         check=lambda decision: decision.indicators["RSI"] < 30
               if decision.action == "buy" else True)

  原文: "下跌趋势中不做多"
  → Rule(name="no_long_in_downtrend", type="qualitative",
         description="Agent should not buy when market is in downtrend")

Step 2: 逐决策审计
  对每条 Decision 记录：

  确定性规则 (type=quantitative):
    直接从 Decision 记录中的市场数据验证
    "当时 RSI 确实 < 30 吗？"

  模糊性规则 (type=qualitative):
    使用 LLM-as-Judge 评估
    "根据当时的市场数据，Agent 的判断'不是下跌趋势'合理吗？"

Step 3: 生成遵循度报告
```

### 遵循度报告

```
┌─────────────────────────────────────────────────┐
│ Compliance Report                               │
│                                                 │
│ Rule: "RSI<30时买入"                             │
│   Type: quantitative                            │
│   Total buy decisions: 45                       │
│   Compliant: 38 (84.4%)                        │
│   Violations: 7                                 │
│   Top violation:                                │
│     2024-03-15 RSI=42                           │
│     Agent reasoning: "MACD 强势金叉, 破例入场"   │
│                                                 │
│ Rule: "单笔仓位≤10%"                            │
│   Type: quantitative                            │
│   Compliant: 45/45 (100%)                      │
│                                                 │
│ Rule: "下跌趋势不做多"                           │
│   Type: qualitative                             │
│   Assessed by: LLM-as-Judge                     │
│   Compliant: 40/45 (88.9%)                     │
│                                                 │
│ Overall Compliance Score: 91.1%                 │
└─────────────────────────────────────────────────┘
```

### 遵循度 × 绩效 二维矩阵

```
              高遵循度
                │
   纪律好但亏钱  │  纪律好且赚钱
   (策略本身有   │  (理想状态)
    问题)        │
                │
────────────────┼────────────────  高收益
                │
   不守纪律且亏  │  不守纪律但赚钱
   (最差情况)    │  (策略描述有漏洞,
                │   Agent 发现了
                │   更好的做法)
                │
              低遵循度
```

**各象限的解读**：

| 象限 | 含义 | 行动 |
|------|------|------|
| 右上 (高遵循+高收益) | 理想状态 | 策略有效，Agent 执行到位 |
| 左上 (高遵循+低收益) | 策略问题 | Agent 忠实执行了一个差策略，需改策略 |
| 右下 (低遵循+高收益) | 策略不完整 | Agent "直觉"优于规则，需补充策略描述 |
| 左下 (低遵循+低收益) | 全面失败 | Agent 不理解策略且判断力差 |

**右下象限最有研究价值**——分析 Agent 的违规决策和 reasoning，可以发现策略 prompt 中遗漏的有效规则。

### LLM-as-Judge 实现设计

#### 架构

```python
class ComplianceJudge(Protocol):
    """遵循度评审协议 — 可注入 mock 或真实 LLM 实现"""
    def evaluate(self, playbook: str, decision: Decision) -> Verdict: ...

@dataclass
class Verdict:
    compliant: bool           # 是否遵循
    rule_violated: str        # 违反的规则名（空串=无违反）
    reasoning: str            # 判定理由
```

#### 评估流程

```
遍历 decisions (排除 hold)
  → judge.evaluate(playbook, decision)
  → 收集 Verdict 列表
  → 汇总: compliance_rate, violations_by_rule, top_violations
```

#### Prompt 模板

```
你是一位严格的策略审计员。

## 策略规则
{playbook}

## 本次决策
- 时间: {decision.datetime}
- 动作: {decision.action} {decision.symbol} {decision.quantity}
- 当时行情: {decision.market_snapshot}
- 使用指标: {decision.indicators_used}
- Agent 理由: {decision.reasoning}

## 任务
判断该决策是否遵循策略规则。输出 JSON:
{"compliant": bool, "rule_violated": "规则名或空串", "reasoning": "判定理由"}
```

#### 集成点

```
BacktestConfig.compliance_judge: ComplianceJudge | None
  → Runner 传入 Evaluator
  → Evaluator.calc_compliance() 内部调用 judge（如有）
  → ComplianceReport 扩展 verdicts 字段
```

#### 测试策略

BDD 测试使用 mock judge（返回固定 Verdict），保证确定性。
真实 LLM judge 仅在集成测试中使用。

### Playbook 演化分析

```
评估 playbook.md 在回测过程中的变化:

  初始版本 (来自 strategy prompt):
    - 5 条入场规则
    - 3 条风控规则

  最终版本 (回测结束时):
    - 5 条入场规则 (未变)
    - 3 条风控规则 (未变)
    + 4 条新经验 (Agent 追加)
    + 1 条规则修正 (Agent 发现的例外)

  Playbook Evolution Score:
    - 新增经验: 4 条
    - 规则修正: 1 条
    - 初始规则稳定性: 100% (无删除)
```

## 维度三：一致性评估 (Consistency)

同样的输入条件下，Agent 的行为是否稳定？

### 三种一致性测试

#### A. 随机一致性 (Stochastic Consistency)

```
同一 prompt + 同一 model + 同一数据，运行 N 次

目的: 策略 prompt 够明确吗？还是模型在猜？

指标:
  - Decision Agreement Rate: 在相同 bar，N 次运行中多少次做出相同决策
  - Return Distribution: N 次运行的收益分布 (mean ± std)
  - Sharpe Distribution: N 次运行的夏普分布

报告:
  ┌──────────────────────────────────┐
  │ Stochastic Consistency (10 runs) │
  │                                  │
  │ Return: 15.2% ± 3.1%            │
  │ Sharpe: 1.1 ± 0.2               │
  │ Decision Agreement: 78.5%       │
  │                                  │
  │ 解读: 策略语义基本明确,          │
  │ 但在边缘情况下模型存在分歧       │
  └──────────────────────────────────┘
```

#### B. 模型敏感性 (Model Sensitivity)

```
同一 prompt + 不同 model + 同一数据

目的: 策略是否依赖特定模型的"个性"？

指标:
  - 各模型的绩效对比
  - 各模型之间的 Decision Overlap Rate (pairwise)

报告:
  ┌──────────────────────────────────┐
  │ Model Sensitivity                │
  │                                  │
  │ Claude Sonnet: 15.2%, 45 trades  │
  │ Claude Opus:   18.7%, 38 trades  │
  │ GPT-4o:        12.1%, 52 trades  │
  │                                  │
  │ Pairwise Decision Overlap:       │
  │   Sonnet-Opus: 72%               │
  │   Sonnet-GPT4: 65%               │
  │   Opus-GPT4:   61%               │
  │                                  │
  │ 解读: Opus 更保守 (少交易, 高质量)│
  │ GPT-4 更激进 (多交易, 低胜率)     │
  │ 建议: 为小模型加强规则约束        │
  └──────────────────────────────────┘
```

#### C. 场景一致性 (Situational Consistency)

```
在历史数据中找到相似的市场状态,
分析 Agent 在这些相似场景下是否做出一致决策

目的: Agent 是否真正理解了策略？还是随机应对？

方法:
  1. 识别相似场景 (如: 所有 RSI<30 的 bar)
  2. 统计 Agent 在这些场景中的决策分布
  3. 检查分布的集中度

报告:
  ┌──────────────────────────────────┐
  │ Situational Consistency          │
  │                                  │
  │ Scenario: RSI < 30 (n=23)        │
  │   Buy: 18 (78.3%)               │
  │   Hold: 5 (21.7%)               │
  │   Sell: 0 (0%)                  │
  │                                  │
  │ Hold 的 5 次分析:                │
  │   3 次: 大盘处于下跌趋势        │
  │   1 次: 已满仓                  │
  │   1 次: 无明确理由 (可能异常)    │
  │                                  │
  │ 解读: Agent 基本理解 RSI<30=买入 │
  │ 的 Hold 大部分有合理理由          │
  └──────────────────────────────────┘
```

## A/B 测试矩阵

框架天然支持多维对比实验：

```python
results = runner.run_matrix(
    prompts = [prompt_v1, prompt_v2],
    models  = ["claude-sonnet", "claude-opus"],
    data    = same_data,
    repeats = 5,
)
# → 2 × 2 × 5 = 20 次回测
# → 自动生成对比报告
```

### 实验类型

| 实验 | 变量 | 回答的问题 |
|------|------|-----------|
| Prompt A/B | 不同策略描述 | 哪种描述让 Agent 表现更好？ |
| Model A/B | 不同 LLM | 哪个模型最适合这个策略？ |
| Memory A/B | 有/无预设经验 | 先验经验能提升多少？ |
| Context A/B | 不同上下文策略 | 信息呈现方式如何影响决策？ |
| Agent vs Baseline | LLM vs 规则引擎 | Agent 推理比 if/else 强多少？ |

## BacktestResult 数据结构

```python
@dataclass
class BacktestResult:
    # 传统维度
    performance: PerformanceMetrics

    # Agent 维度
    compliance: ComplianceReport
    consistency: ConsistencyReport | None  # 多次 run 后才有

    # 审计数据
    decisions: list[Decision]          # 每笔决策完整记录
    equity_curve: Series               # 权益曲线
    trade_log: list[Trade]             # 交易明细

    # 工作空间
    workspace_path: str                # 完整的文件系统快照路径

    # 元信息
    config: BacktestConfig             # 回测配置
    agent_info: AgentInfo              # 模型名、版本等
    duration: float                    # 回测耗时
    total_llm_calls: int               # LLM 调用次数
    total_tokens: int                  # 总 token 消耗
```

[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
