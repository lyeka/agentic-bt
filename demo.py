#!/usr/bin/env python3
"""
AgenticBT 端到端 Demo
=====================
用一个真实 LLM 运行完整回测，打印结构化结果报告。

快速开始：
    # Claude (via Anthropic API)
    ANTHROPIC_API_KEY=sk-ant-... python demo.py

    # GPT-4o (via OpenAI API)
    OPENAI_API_KEY=sk-... python demo.py --provider openai

    # 本地 Ollama（无需 key）
    python demo.py --provider ollama --model qwen2.5:7b

    # 使用 mock agent（无需 API key，快速验证框架）
    python demo.py --mock
"""

import argparse
import os
import sys
import time
from datetime import datetime


# ── .env 加载器（无需 python-dotenv 依赖）───────────────────────────────────
def _load_dotenv(path: str = ".env") -> None:
    """从 .env 文件加载环境变量（不覆盖已有变量）。"""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key   = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass

# ── 把 src/ 加入路径（直接运行 demo.py 时用）────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agenticbt import BacktestConfig, LLMAgent, load_csv, make_sample_data, run
from agenticbt.models import CommissionConfig, Context, Decision, RiskConfig
from agenticbt.tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# Mock Agent（无需 API key，演示框架结构）
# ─────────────────────────────────────────────────────────────────────────────

class RsiMockAgent:
    """
    规则驱动的 mock agent：用工具查询 RSI，RSI < 50 买入，RSI > 55 卖出。
    模拟 LLM agent 的行为，但完全确定性，不调用真实 API。
    """

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        # 1. 观察市场
        market = toolkit.execute("market_observe", {})

        # 2. 查询 RSI
        rsi_result = toolkit.execute("indicator_calc", {"name": "RSI", "period": 14})
        rsi = rsi_result.get("value")

        # 3. 查询账户
        account = toolkit.execute("account_status", {})
        has_position = bool(account.get("positions"))

        # 4. 决策逻辑
        action, symbol, qty, reasoning = "hold", None, None, ""
        close = market.get("close", 0)

        if rsi is not None:
            if rsi < 50 and not has_position:
                qty = max(1, int(account["cash"] * 0.95 / close))
                action, symbol = "buy", context.market["symbol"]
                reasoning = f"RSI={rsi:.1f} < 50，超卖信号，买入 {qty} 股 @ {close}"
                toolkit.execute("trade_execute", {"action": "buy", "symbol": symbol, "quantity": qty})
                toolkit.execute("memory_log", {"content": f"买入 {symbol} {qty}股，RSI={rsi:.1f}"})
            elif rsi > 55 and has_position:
                action, symbol = "close", context.market["symbol"]
                reasoning = f"RSI={rsi:.1f} > 55，超买信号，平仓"
                toolkit.execute("trade_execute", {"action": "close", "symbol": symbol})
                toolkit.execute("memory_log", {"content": f"平仓 {symbol}，RSI={rsi:.1f}"})
            else:
                reasoning = f"RSI={rsi:.1f}，无交易信号，持仓={'有' if has_position else '无'}"
        else:
            reasoning = "RSI 数据不足，观望"

        return Decision(
            datetime=context.datetime,
            bar_index=context.bar_index,
            action=action,
            symbol=symbol,
            quantity=qty,
            reasoning=reasoning,
            market_snapshot=context.market,
            account_snapshot=context.account,
            indicators_used={"RSI": rsi},
            tool_calls=list(toolkit.call_log),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 结果报告
# ─────────────────────────────────────────────────────────────────────────────

def print_report(result, elapsed: float) -> None:
    p = result.performance
    c = result.compliance

    sep = "─" * 55

    print(f"\n{'═' * 55}")
    print(f"  AgenticBT 回测报告")
    print(f"{'═' * 55}")

    print(f"\n【绩效指标】")
    print(sep)
    initial = p.equity_curve[0] if p.equity_curve else 100_000
    final   = p.equity_curve[-1] if p.equity_curve else initial
    print(f"  总收益率      {p.total_return * 100:+.2f}%")
    print(f"  初始权益      {initial:,.0f}")
    print(f"  最终权益      {final:,.0f}   ({final - initial:+,.0f})")
    print(f"  最大回撤      {p.max_drawdown * 100:.2f}%")
    print(f"  夏普比率      {p.sharpe_ratio:.3f}  (年化)")
    print(f"  总交易次数    {p.total_trades}")
    if p.total_trades > 0:
        print(f"  胜率          {p.win_rate * 100:.1f}%")
        pf = p.profit_factor
        print(f"  盈亏比        {pf:.2f}" if pf != float('inf') else "  盈亏比        ∞ (无亏损)")

    print(f"\n【遵循度报告】")
    print(sep)
    print(f"  总决策次数    {c.total_decisions}")
    for action, cnt in sorted(c.action_distribution.items()):
        pct = cnt / c.total_decisions * 100
        print(f"  {action:<10}    {cnt:>4} 次  ({pct:.0f}%)")
    print(f"  使用指标次数  {c.decisions_with_indicators} / {c.total_decisions}")

    print(f"\n【回测元信息】")
    print(sep)
    print(f"  耗时          {elapsed:.1f}s")
    print(f"  LLM 调用次数  {result.total_llm_calls}")
    print(f"  Token 消耗    {result.total_tokens:,}")
    print(f"  工作空间      {result.workspace_path}")

    # 决策样本（首尾各 3 条）
    decisions = result.decisions
    sample = decisions[:3] + (["..."] if len(decisions) > 6 else []) + decisions[-3:]
    print(f"\n【决策日志（共 {len(decisions)} 条）】")
    print(sep)
    for d in sample:
        if d == "...":
            print(f"  ...")
            continue
        dt = d.datetime.strftime("%Y-%m-%d") if isinstance(d.datetime, datetime) else str(d.datetime)
        tag = {"buy": "🔼 买", "sell": "🔽 卖", "close": "⬛ 平", "hold": "⏸ 观"}.get(d.action, d.action)
        print(f"  {dt}  {tag}  {d.reasoning[:50]}")

    print(f"\n{'═' * 55}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────────────────────

def main():
    _load_dotenv()
    parser = argparse.ArgumentParser(description="AgenticBT 端到端 Demo")
    parser.add_argument("--provider", choices=["claude", "openai", "ollama"], default="claude",
                        help="LLM 提供商 (default: claude)")
    parser.add_argument("--model", default=None, help="模型名称（覆盖默认值）")
    parser.add_argument("--csv",   default=None, help="自定义 CSV 路径（默认使用内置模拟数据）")
    parser.add_argument("--symbol", default="AAPL", help="股票代码 (default: AAPL)")
    parser.add_argument("--bars",  type=int, default=60, help="回测 bar 数量 (default: 60)")
    parser.add_argument("--decision-start-bar", type=int, default=14,
                        help="从第几根 bar 开始触发决策 (default: 14, 适配 RSI14 预热)")
    parser.add_argument("--mock",  action="store_true", help="使用 mock agent（无需 API key）")
    args = parser.parse_args()

    # ── 数据 ────────────────────────────────────────────────────────────────
    if args.csv:
        print(f"加载数据: {args.csv}")
        df = load_csv(args.csv)
    else:
        print(f"使用模拟数据: {args.symbol}，{args.bars} 根 bar")
        df = make_sample_data(args.symbol, periods=args.bars)

    df = df.head(args.bars)

    # ── Agent ────────────────────────────────────────────────────────────────
    if args.mock:
        print("模式: Mock Agent（RSI 规则策略）\n")
        agent = RsiMockAgent()
    else:
        base_url, api_key, model = _resolve_provider(args.provider, args.model)
        print(f"模式: LLM Agent ({args.provider} / {model})\n")
        agent = LLMAgent(model=model, base_url=base_url, api_key=api_key, max_rounds=5)

    # ── 配置 ────────────────────────────────────────────────────────────────
    strategy = (
        "你是一位量化交易员，使用 RSI 均值回归策略。\n"
        "规则：\n"
        "1. RSI < 50 且无持仓时：买入，仓位不超过账户净值的 90%\n"
        "2. RSI > 55 且有持仓时：平仓\n"
        "3. 其他情况：观望\n"
        "每次决策前必须先调用 market_observe 和 indicator_calc(RSI) 获取最新数据。\n"
        "交易后用 memory_log 记录决策理由。"
    )

    config = BacktestConfig(
        data=df,
        symbol=args.symbol,
        strategy_prompt=strategy,
        risk=RiskConfig(max_position_pct=0.95),
        commission=CommissionConfig(rate=0.001),
        decision_start_bar=args.decision_start_bar,
    )

    # ── 运行 ────────────────────────────────────────────────────────────────
    print(f"开始回测: {len(df)} 根 bar ...")
    t0 = time.time()
    result = run(config, agent=agent)
    elapsed = time.time() - t0

    print_report(result, elapsed)


def _resolve_provider(provider: str, model_override: str | None) -> tuple[str | None, str | None, str]:
    if provider == "claude":
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1/")
        api_key  = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        model    = model_override or "claude-sonnet-4-20250514"
    elif provider == "openai":
        base_url = os.environ.get("OPENAI_BASE_URL")
        api_key  = os.environ.get("OPENAI_API_KEY")
        model    = model_override or "gpt-4o-mini"
    elif provider == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1/")
        api_key  = "ollama"
        model    = model_override or "qwen2.5:7b"
    else:
        raise ValueError(f"未知提供商: {provider}")

    if not api_key and provider != "ollama":
        print(f"警告: 未找到 API key（环境变量 ANTHROPIC_API_KEY / OPENAI_API_KEY）")
        print("使用 --mock 可跳过 API 调用\n")

    return base_url, api_key, model


if __name__ == "__main__":
    main()
