"""
[INPUT]: agenticbt.models (Context, Decision, ToolCall, BacktestConfig, RiskConfig, CommissionConfig),
         agenticbt.tools (ToolKit), agenticbt.data (make_sample_data)
[OUTPUT]: STRATEGIES 注册表, RsiMockAgent, BracketAtrMockAgent, BollingerLimitMockAgent,
          AdaptiveMemoryMockAgent, MultiAssetMockAgent, ComputeQuantMockAgent,
          get_strategy, list_strategies
[POS]: 策略定义层，Mock Agent + LLM Prompt + 数据配置三位一体；被 demo.py 消费
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agenticbt.data import make_sample_data
from agenticbt.models import (
    BacktestConfig,
    CommissionConfig,
    Context,
    Decision,
    RiskConfig,
    ToolCall,
)
from agenticbt.tools import ToolKit


# ─────────────────────────────────────────────────────────────────────────────
# 策略定义
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyDef:
    """策略注册表条目"""
    name: str
    description: str
    mock_cls: type | None          # None = LLM-only
    llm_prompt: str
    regime: str
    seed: int
    bars: int
    decision_start_bar: int = 14
    max_rounds: int = 15                   # LLMAgent 最大 ReAct 轮次
    symbol: str = "AAPL"
    risk: RiskConfig = field(default_factory=RiskConfig)
    features: list[str] = field(default_factory=list)
    extra_symbols: list[tuple[str, int]] | None = None  # 多资产: [(symbol, seed)]


# ─────────────────────────────────────────────────────────────────────────────
# Mock Agent 1: RSI 均值回归（从 demo.py 迁移）
# ─────────────────────────────────────────────────────────────────────────────

class RsiMockAgent:
    """RSI < 50 买入，RSI > 55 卖出。最基础的工具链验证。"""

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        market = toolkit.execute("market_observe", {})
        rsi_result = toolkit.execute("indicator_calc", {"name": "RSI", "period": 14})
        rsi = rsi_result.get("value")
        account = toolkit.execute("account_status", {})
        has_position = bool(account.get("positions"))

        action, symbol, qty, reasoning = "hold", None, None, ""
        close = market.get("close", 0)

        if rsi is not None:
            if rsi < 50 and not has_position:
                qty = max(1, int(account["cash"] * 0.95 / close))
                action, symbol = "buy", context.market["symbol"]
                reasoning = f"RSI={rsi:.1f}<50 买入{qty}股@{close}"
                toolkit.execute("trade_execute", {"action": "buy", "symbol": symbol, "quantity": qty})
                toolkit.execute("memory_log", {"content": f"买入 {symbol} {qty}股 RSI={rsi:.1f}"})
            elif rsi > 55 and has_position:
                action, symbol = "close", context.market["symbol"]
                reasoning = f"RSI={rsi:.1f}>55 平仓"
                toolkit.execute("trade_execute", {"action": "close", "symbol": symbol})
                toolkit.execute("memory_log", {"content": f"平仓 {symbol} RSI={rsi:.1f}"})
            else:
                reasoning = f"RSI={rsi:.1f} 无信号 持仓={'有' if has_position else '无'}"
        else:
            reasoning = "RSI 数据不足"

        return Decision(
            datetime=context.datetime, bar_index=context.bar_index,
            action=action, symbol=symbol, quantity=qty, reasoning=reasoning,
            market_snapshot=context.market, account_snapshot=context.account,
            indicators_used={"RSI": rsi}, tool_calls=list(toolkit.call_log),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mock Agent 2: 均线交叉 + Bracket 动态风控
# ─────────────────────────────────────────────────────────────────────────────

class BracketAtrMockAgent:
    """SMA10/30 交叉触发，ATR 计算动态止损止盈，Bracket 订单保护。"""

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        market = toolkit.execute("market_observe", {})
        sma10 = toolkit.execute("indicator_calc", {"name": "SMA", "period": 10}).get("value")
        sma30 = toolkit.execute("indicator_calc", {"name": "SMA", "period": 30}).get("value")
        atr = toolkit.execute("indicator_calc", {"name": "ATR", "period": 14}).get("value")
        account = toolkit.execute("account_status", {})
        has_position = bool(account.get("positions"))

        action, symbol, qty, reasoning = "hold", None, None, ""
        close = market.get("close", 0)
        indicators = {"SMA10": sma10, "SMA30": sma30, "ATR": atr}

        if sma10 is not None and sma30 is not None and atr is not None:
            if sma10 > sma30 and not has_position:
                # 金叉买入，ATR 动态止损止盈
                qty = max(1, int(account["cash"] * 0.90 / close))
                symbol = context.market["symbol"]
                stop_loss = round(close - 2 * atr, 2)
                take_profit = round(close + 3 * atr, 2)
                action = "buy"
                reasoning = f"金叉 SMA10={sma10:.1f}>SMA30={sma30:.1f} ATR={atr:.2f} bracket SL={stop_loss} TP={take_profit}"
                toolkit.execute("trade_execute", {
                    "action": "buy", "symbol": symbol, "quantity": qty,
                    "stop_loss": stop_loss, "take_profit": take_profit,
                })
                toolkit.execute("memory_log", {"content": f"金叉买入 bracket SL={stop_loss} TP={take_profit}"})
            elif sma10 < sma30 and has_position:
                symbol = context.market["symbol"]
                action = "close"
                reasoning = f"死叉 SMA10={sma10:.1f}<SMA30={sma30:.1f} 平仓"
                toolkit.execute("trade_execute", {"action": "close", "symbol": symbol})
            else:
                reasoning = f"SMA10={sma10:.1f} SMA30={sma30:.1f} 无交叉信号"
        else:
            reasoning = "指标数据不足"

        return Decision(
            datetime=context.datetime, bar_index=context.bar_index,
            action=action, symbol=symbol, quantity=qty, reasoning=reasoning,
            market_snapshot=context.market, account_snapshot=context.account,
            indicators_used=indicators, tool_calls=list(toolkit.call_log),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mock Agent 3: 布林带 + 限价单生命周期
# ─────────────────────────────────────────────────────────────────────────────

class BollingerLimitMockAgent:
    """下轨挂限价买单(valid_bars=3)，上轨平仓，管理挂单生命周期。"""

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        market = toolkit.execute("market_observe", {})
        bb = toolkit.execute("indicator_calc", {"name": "BBANDS", "period": 20})
        account = toolkit.execute("account_status", {})
        has_position = bool(account.get("positions"))

        # 检查并清理过期挂单
        pending = toolkit.execute("order_query", {})
        for order in pending.get("pending_orders", []):
            toolkit.execute("order_cancel", {"order_id": order["order_id"]})

        action, symbol, qty, reasoning = "hold", None, None, ""
        close = market.get("close", 0)
        upper, lower = bb.get("upper"), bb.get("lower")
        indicators = {"BB_upper": upper, "BB_lower": lower}

        if upper is not None and lower is not None:
            if not has_position and close <= lower * 1.02:
                # 在下轨附近挂限价买单
                qty = max(1, int(account["cash"] * 0.90 / lower))
                symbol = context.market["symbol"]
                limit_price = round(lower, 2)
                action = "buy"
                reasoning = f"BB下轨={lower:.2f} 挂限价买单@{limit_price} valid_bars=3"
                toolkit.execute("trade_execute", {
                    "action": "buy", "symbol": symbol, "quantity": qty,
                    "order_type": "limit", "price": limit_price, "valid_bars": 3,
                })
            elif has_position and close >= upper * 0.98:
                symbol = context.market["symbol"]
                action = "close"
                reasoning = f"BB上轨={upper:.2f} 触及 平仓"
                toolkit.execute("trade_execute", {"action": "close", "symbol": symbol})
            else:
                reasoning = f"BB [{lower:.2f}, {upper:.2f}] close={close:.2f} 无信号"
        else:
            reasoning = "BBANDS 数据不足"

        return Decision(
            datetime=context.datetime, bar_index=context.bar_index,
            action=action, symbol=symbol, quantity=qty, reasoning=reasoning,
            market_snapshot=context.market, account_snapshot=context.account,
            indicators_used=indicators, tool_calls=list(toolkit.call_log),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mock Agent 4: 记忆驱动自适应
# ─────────────────────────────────────────────────────────────────────────────

class AdaptiveMemoryMockAgent:
    """RSI 基础信号 + memory 记录胜率 + 胜率驱动仓位大小。"""

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        market = toolkit.execute("market_observe", {})
        rsi_result = toolkit.execute("indicator_calc", {"name": "RSI", "period": 14})
        rsi = rsi_result.get("value")
        account = toolkit.execute("account_status", {})
        has_position = bool(account.get("positions"))

        # 读取历史胜率
        recall = toolkit.execute("memory_recall", {"query": "performance"})
        results = recall.get("results", [])
        win_rate = self._parse_win_rate(results)

        # 仓位系数：胜率 > 50% 正常，否则减半
        position_pct = 0.90 if win_rate > 0.5 else 0.45

        action, symbol, qty, reasoning = "hold", None, None, ""
        close = market.get("close", 0)
        indicators = {"RSI": rsi, "win_rate": win_rate}

        if rsi is not None:
            if rsi < 45 and not has_position:
                qty = max(1, int(account["cash"] * position_pct / close))
                symbol = context.market["symbol"]
                action = "buy"
                reasoning = f"RSI={rsi:.1f}<45 胜率={win_rate:.0%} 仓位={position_pct:.0%} 买入{qty}股"
                toolkit.execute("trade_execute", {"action": "buy", "symbol": symbol, "quantity": qty})
                toolkit.execute("memory_log", {"content": f"买入 RSI={rsi:.1f} 仓位={position_pct:.0%}"})
            elif rsi > 55 and has_position:
                symbol = context.market["symbol"]
                action = "close"
                # 记录交易结果到 memory_note
                pnl = account.get("equity", 100000) - 100000
                wins = int(win_rate * 10) + (1 if pnl > 0 else 0)
                total = 10 + 1
                new_rate = wins / total
                toolkit.execute("memory_note", {
                    "key": "performance",
                    "content": f"累计胜率: {new_rate:.2f} (wins={wins}, total={total})",
                })
                reasoning = f"RSI={rsi:.1f}>55 平仓 PnL={pnl:+.0f} 更新胜率={new_rate:.0%}"
                toolkit.execute("trade_execute", {"action": "close", "symbol": symbol})
            else:
                reasoning = f"RSI={rsi:.1f} 胜率={win_rate:.0%} 无信号"
        else:
            reasoning = "RSI 数据不足"

        return Decision(
            datetime=context.datetime, bar_index=context.bar_index,
            action=action, symbol=symbol, quantity=qty, reasoning=reasoning,
            market_snapshot=context.market, account_snapshot=context.account,
            indicators_used=indicators, tool_calls=list(toolkit.call_log),
        )

    @staticmethod
    def _parse_win_rate(results: list) -> float:
        """从 memory recall 结果中解析胜率，默认 50%"""
        for r in results:
            text = str(r)
            if "累计胜率" in text:
                try:
                    return float(text.split("累计胜率:")[1].split()[0])
                except (IndexError, ValueError):
                    pass
        return 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Mock Agent 5: 多资产轮动
# ─────────────────────────────────────────────────────────────────────────────

class MultiAssetMockAgent:
    """比较 AAPL/GOOGL 的 RSI，持有最超卖的资产，动态轮换。"""

    SYMBOLS = ["AAPL", "GOOGL"]

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        account = toolkit.execute("account_status", {})
        positions = account.get("positions", {})

        # 查询每个资产的 RSI
        rsi_map: dict[str, float | None] = {}
        for sym in self.SYMBOLS:
            toolkit.execute("market_observe", {"symbol": sym})
            r = toolkit.execute("indicator_calc", {"name": "RSI", "period": 14, "symbol": sym})
            rsi_map[sym] = r.get("value")

        action, symbol, qty, reasoning = "hold", None, None, ""
        indicators = {f"RSI_{k}": v for k, v in rsi_map.items()}

        # 找最超卖的资产
        valid = {s: v for s, v in rsi_map.items() if v is not None}
        if not valid:
            reasoning = "RSI 数据不足"
        else:
            most_oversold = min(valid, key=lambda s: valid[s])
            most_oversold_rsi = valid[most_oversold]

            held_symbols = [s for s, p in positions.items() if p.get("size", 0) > 0]

            if most_oversold_rsi < 50 and most_oversold not in held_symbols:
                # 先平掉其他持仓
                for s in held_symbols:
                    if s != most_oversold:
                        toolkit.execute("trade_execute", {"action": "close", "symbol": s})

                market = toolkit.execute("market_observe", {"symbol": most_oversold})
                close = market.get("close", 0)
                cash = account.get("cash", 0)
                qty = max(1, int(cash * 0.40 / close)) if close > 0 else 0
                if qty > 0:
                    symbol = most_oversold
                    action = "buy"
                    reasoning = f"轮动: {most_oversold} RSI={most_oversold_rsi:.1f} 最超卖 买入{qty}股"
                    toolkit.execute("trade_execute", {"action": "buy", "symbol": symbol, "quantity": qty})
            elif all(v > 55 for v in valid.values()) and held_symbols:
                # 全部超买，清仓
                for s in held_symbols:
                    toolkit.execute("trade_execute", {"action": "close", "symbol": s})
                symbol = held_symbols[0]
                action = "close"
                reasoning = f"全部超买 RSI={dict(valid)} 清仓"
            else:
                reasoning = f"RSI={dict(valid)} 无轮动信号"

        return Decision(
            datetime=context.datetime, bar_index=context.bar_index,
            action=action, symbol=symbol, quantity=qty, reasoning=reasoning,
            market_snapshot=context.market, account_snapshot=context.account,
            indicators_used=indicators, tool_calls=list(toolkit.call_log),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mock Agent 6: compute 量化研究员 — 全面展示 compute 能力
# ─────────────────────────────────────────────────────────────────────────────

class ComputeQuantMockAgent:
    """纯 compute 驱动：市场状态识别 + 自定义指标 + 均线交叉 + ATR 仓位计算。
    不使用 indicator_calc，全部通过 compute 沙箱完成。"""

    def decide(self, context: Context, toolkit: ToolKit) -> Decision:
        account = toolkit.execute("account_status", {})
        has_position = bool(account.get("positions"))

        # ── compute 1: 市场状态识别（多行 exec + helper + dict 返回）──
        regime = toolkit.execute("compute", {"code": (
            "vol = latest(df.close.pct_change().rolling(20).std())\n"
            "trend = df.close.iloc[-1] / df.close.iloc[-min(20, len(df))] - 1\n"
            "result = {'regime': 'trending' if abs(trend) > 0.05 else 'ranging',"
            " 'vol': round(vol, 4) if vol else 0, 'trend': round(trend, 4)}"
        )})

        # ── compute 2: 自定义 RSI（单表达式 eval + ta 库）──
        rsi_r = toolkit.execute("compute", {"code": "latest(ta.rsi(df.close, 14))"})
        rsi = rsi_r.get("result")

        # ── compute 3: 均线交叉（helper crossover，bool 返回）──
        cross_r = toolkit.execute("compute", {
            "code": "crossover(df.close.rolling(10).mean(), df.close.rolling(30).mean())",
        })
        golden_cross = cross_r.get("result", False)

        # ── compute 4: ATR 仓位计算（多行 exec + equity 变量）──
        size_r = toolkit.execute("compute", {"code": (
            "atr_val = latest(ta.atr(df.high, df.low, df.close, 14))\n"
            "result = max(1, int(equity * 0.02 / atr_val)) if atr_val and atr_val > 0 else 0"
        )})
        position_size = size_r.get("result", 0)

        # 提取状态
        regime_info = regime.get("result", {}) if isinstance(regime.get("result"), dict) else {}
        market_regime = regime_info.get("regime", "unknown")

        action, symbol, qty, reasoning = "hold", None, None, ""
        indicators = {"rsi": rsi, "regime": market_regime, "golden_cross": golden_cross,
                       "position_size": position_size}

        if rsi is not None:
            if rsi < 45 and not has_position and (golden_cross or market_regime == "trending"):
                qty = min(position_size, max(1, int(account["cash"] * 0.90 / account.get("equity", 1) * position_size))) if position_size else 0
                if qty > 0:
                    symbol = context.market["symbol"]
                    action = "buy"
                    reasoning = (f"compute量化: regime={market_regime} RSI={rsi:.1f}<45 "
                                 f"cross={golden_cross} 仓位={qty}股(ATR)")
                    toolkit.execute("trade_execute", {"action": "buy", "symbol": symbol, "quantity": qty})
                    toolkit.execute("memory_log", {"content": f"compute买入 {symbol} {qty}股 RSI={rsi:.1f} regime={market_regime}"})
            elif rsi > 60 and has_position:
                symbol = context.market["symbol"]
                action = "close"
                reasoning = f"compute量化: RSI={rsi:.1f}>60 regime={market_regime} 平仓"
                toolkit.execute("trade_execute", {"action": "close", "symbol": symbol})
                toolkit.execute("memory_log", {"content": f"compute平仓 {symbol} RSI={rsi:.1f}"})
            else:
                reasoning = f"compute量化: RSI={rsi:.1f} regime={market_regime} cross={golden_cross} 无信号"
        else:
            reasoning = "compute: 数据不足"

        return Decision(
            datetime=context.datetime, bar_index=context.bar_index,
            action=action, symbol=symbol, quantity=qty, reasoning=reasoning,
            market_snapshot=context.market, account_snapshot=context.account,
            indicators_used=indicators, tool_calls=list(toolkit.call_log),
        )


# ─────────────────────────────────────────────────────────────────────────────
# LLM Prompt 定义
# ─────────────────────────────────────────────────────────────────────────────

_PROMPT_RSI = (
    "RSI 均值回归策略。\n"
    "规则：\n"
    "1. RSI < 50 且无持仓时：买入，仓位不超过账户净值的 90%\n"
    "2. RSI > 55 且有持仓时：平仓\n"
    "3. 其他情况：观望"
)

_PROMPT_BRACKET_ATR = (
    "均线交叉 + ATR 动态风控策略。\n"
    "规则：\n"
    "1. 计算 SMA(10) 和 SMA(30)，判断趋势方向\n"
    "2. SMA10 > SMA30（金叉）且无持仓：买入，用 ATR 设定止损止盈\n"
    "   - stop_loss = 当前价 - 2×ATR\n"
    "   - take_profit = 当前价 + 3×ATR\n"
    "   - 每笔交易必须带 bracket 保护（传 stop_loss 和 take_profit 参数）\n"
    "3. SMA10 < SMA30（死叉）且有持仓：平仓\n"
    "4. 其他情况：观望"
)

_PROMPT_BOLLINGER_LIMIT = (
    "布林带 + 限价单策略。\n"
    "规则：\n"
    "1. 计算 BBANDS(20)，获取上轨和下轨\n"
    "2. 价格接近下轨且无持仓：在下轨挂限价买单（order_type=limit, valid_bars=3）\n"
    "3. 价格接近上轨且有持仓：平仓\n"
    "4. 每轮决策前用 order_query 检查挂单，用 order_cancel 清理过期或不需要的挂单\n"
    "5. 其他情况：观望\n"
    "管理好挂单生命周期是你的核心能力。"
)

_PROMPT_ADAPTIVE_MEMORY = (
    "记忆驱动自适应策略。\n"
    "核心机制：\n"
    "1. 每次决策前：用 memory_recall('performance') 回顾历史胜率\n"
    "2. 用 RSI 做基础信号（RSI<45 买入，RSI>55 卖出）\n"
    "3. 仓位大小由历史胜率决定：\n"
    "   - 胜率 > 50%：正常仓位（90%）\n"
    "   - 胜率 ≤ 50%：减半仓位（45%）\n"
    "4. 每次交易后：用 memory_note('performance', ...) 更新累计胜率\n"
    "从过去的成功和失败中学习，动态调整策略。"
)

_PROMPT_MULTI_ASSET = (
    "多资产轮动策略，管理 AAPL 和 GOOGL。\n"
    "规则：\n"
    "1. 分别查询两个资产的 RSI（用 symbol 参数）\n"
    "2. 持有 RSI 最低（最超卖）的资产，单票仓位不超过 40%\n"
    "3. 当持有资产不再是最超卖时，轮换到更超卖的资产\n"
    "4. 全部资产 RSI > 55 时清仓\n"
    "分析两个资产的相对强弱，在它们之间动态配置资金。"
)

_PROMPT_FREE_PLAY = (
    "你是一位天生的赌徒型交易员。你热爱风险，享受每一次下注的快感。\n"
    "对你来说，空仓就是最大的风险——错过行情比亏损更让你难受。\n\n"
    "看 2-3 个指标就够了，别磨叽，快点出手。\n\n"
    "每次你必须交易，可以做多或者做空，也可以做T\n\n"
    "你的信条：市场奖励行动者，惩罚犹豫者。\n"
    "唯一目标：赚钱。大胆交易，享受过程。"
)

_PROMPT_REFLECTIVE = (
    "反思型交易风格。你的核心能力是从经验中学习。\n\n"
    "每次决策前：\n"
    "1. 用 memory_recall 回顾过去的交易记录和反思笔记\n"
    "2. 分析哪些决策是正确的，哪些是错误的\n"
    "3. 基于历史教训做出当前决策\n\n"
    "每次交易后：\n"
    "1. 用 memory_note 记录本次决策的理由和市场状态\n"
    "2. 用 memory_log 写下对本次决策的反思\n\n"
    "你的交易风格应该随着经验积累而进化。早期可以大胆试探，后期应该越来越精准。"
)

_PROMPT_QUANT_COMPUTE = (
    "量化研究风格，优先使用 compute 工具做分析。\n\n"
    "决策流程：\n"
    "1. 用 compute 一次性计算关键指标（RSI、均线、ATR 等）\n"
    "2. 根据指标值决策\n"
    "3. 用 trade_execute 执行交易\n\n"
    "compute 示例：\n"
    "  rsi = latest(ta.rsi(df.close, 14))\n"
    "  sma20 = latest(df.close.rolling(20).mean())\n"
    "  atr = latest(ta.atr(df.high, df.low, df.close, 14))\n"
    "  upper, mid, lower = bbands(df.close, 20, 2)\n"
    "  macd_val, signal, hist = macd(df.close)\n"
    "  cross = crossover(df.close.rolling(10).mean(), df.close.rolling(30).mean())\n"
    "  qty = max(1, int(equity * 0.02 / atr)) if atr else 0\n"
    "  result = {'rsi': rsi, 'sma20': sma20, 'bb_upper': upper, 'cross': cross, 'qty': qty}\n\n"
    "注意：bbands()/macd() 数据不足时返回 (None, None, None)，需判空。\n"
    "简洁高效：2-4 个指标足以做出好决策。"
)


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGIES 注册表
# ─────────────────────────────────────────────────────────────────────────────

STRATEGIES: dict[str, StrategyDef] = {
    "rsi": StrategyDef(
        name="rsi",
        description="RSI 均值回归 — 市价单 + 单指标",
        mock_cls=RsiMockAgent,
        llm_prompt=_PROMPT_RSI,
        regime="mean_reverting", seed=42, bars=60,
        decision_start_bar=14,
        features=["市价单", "单指标", "memory_log"],
    ),
    "bracket_atr": StrategyDef(
        name="bracket_atr",
        description="均线交叉 + Bracket 动态风控",
        mock_cls=BracketAtrMockAgent,
        llm_prompt=_PROMPT_BRACKET_ATR,
        regime="trending", seed=100, bars=80,
        decision_start_bar=30,
        features=["Bracket订单", "多指标融合", "动态止损止盈"],
    ),
    "bollinger_limit": StrategyDef(
        name="bollinger_limit",
        description="布林带 + 限价单生命周期",
        mock_cls=BollingerLimitMockAgent,
        llm_prompt=_PROMPT_BOLLINGER_LIMIT,
        regime="volatile", seed=200, bars=80,
        decision_start_bar=20,
        features=["限价单", "order_query", "order_cancel", "valid_bars"],
    ),
    "adaptive_memory": StrategyDef(
        name="adaptive_memory",
        description="记忆驱动自适应策略",
        mock_cls=AdaptiveMemoryMockAgent,
        llm_prompt=_PROMPT_ADAPTIVE_MEMORY,
        regime="mean_reverting", seed=300, bars=100,
        decision_start_bar=14,
        features=["memory_note", "memory_recall", "自适应仓位"],
    ),
    "multi_asset": StrategyDef(
        name="multi_asset",
        description="多资产轮动 + 保守风控",
        mock_cls=MultiAssetMockAgent,
        llm_prompt=_PROMPT_MULTI_ASSET,
        regime="bull_bear", seed=400, bars=80,
        decision_start_bar=14,
        symbol="AAPL",
        risk=RiskConfig(max_position_pct=0.45, max_open_positions=2),
        features=["多资产", "风控配置", "轮动"],
        extra_symbols=[("GOOGL", 401)],
    ),
    "free_play": StrategyDef(
        name="free_play",
        description="AI 自由交易员 — 全工具链自由探索",
        mock_cls=None,
        llm_prompt=_PROMPT_FREE_PLAY,
        regime="random", seed=42, bars=60,
        max_rounds=25,
        features=["全工具链", "AI自由度最高"],
    ),
    "reflective": StrategyDef(
        name="reflective",
        description="反思型交易员 — 记忆系统深度使用",
        mock_cls=None,
        llm_prompt=_PROMPT_REFLECTIVE,
        regime="random", seed=42, bars=80,
        max_rounds=25,
        features=["记忆系统深度", "自我反思"],
    ),
    "quant_compute": StrategyDef(
        name="quant_compute",
        description="compute 量化研究员 — 纯沙箱计算驱动",
        mock_cls=ComputeQuantMockAgent,
        llm_prompt=_PROMPT_QUANT_COMPUTE,
        regime="trending", seed=500, bars=80,
        decision_start_bar=30,
        features=["compute沙箱", "自定义指标", "ATR仓位", "市场状态识别", "helper函数"],
    ),
}


def get_strategy(name: str) -> StrategyDef:
    """按名称获取策略定义，未找到则 raise KeyError"""
    if name not in STRATEGIES:
        raise KeyError(f"未知策略: {name!r}，可选: {list(STRATEGIES)}")
    return STRATEGIES[name]


def list_strategies() -> list[str]:
    """返回所有策略名称"""
    return list(STRATEGIES)
