#!/usr/bin/env python3
"""
[INPUT]:  trace.jsonl (JSONL 格式的 AgenticBT 回测追踪文件)
[OUTPUT]: 终端文本报告 + {workspace}/analysis.json
[POS]:    独立分析脚本，读取 Runner/Agent 产生的 trace 事件，输出工具调用统计
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

import json, re, sys, argparse
from pathlib import Path
from collections import defaultdict

# ── 常量 ──────────────────────────────────────────────────────────

HELPERS = ["bbands", "macd", "latest", "prev", "crossover", "crossunder", "above", "below"]

# 错误分类正则：(pattern, category_name)
ERROR_PATTERNS = [
    (re.compile(r"KeyError:.*BB[UML]_"),           "BBands KeyError"),
    (re.compile(r"KeyError:.*MACD"),               "MACD KeyError"),
    (re.compile(r"NameError"),                      "Cross-call NameError"),
    (re.compile(r"TypeError.*NoneType"),            "None comparison TypeError"),
    (re.compile(r"TypeError"),                      "TypeError"),
    (re.compile(r"SyntaxError"),                    "SyntaxError"),
    (re.compile(r"IndexError"),                     "IndexError"),
    (re.compile(r"计算超时"),                        "Timeout"),
]


# ── 解析 ──────────────────────────────────────────────────────────

def parse_trace(path: Path) -> list[dict]:
    """逐行读取 JSONL，返回事件列表"""
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def classify_error(error_msg: str) -> str:
    """将错误消息归类到已知模式"""
    for pattern, category in ERROR_PATTERNS:
        if pattern.search(error_msg):
            return category
    return "Other"


# ── 分析核心 ─────────────────────────────────────────────────────

def analyze(events: list[dict], threshold: float = 50.0) -> dict:
    """从 trace 事件列表生成完整分析报告"""

    # ── 按 bar 分组 ──
    bars_data: dict[int, dict] = {}
    tool_calls: list[dict] = []
    decisions: list[dict] = []
    model = ""

    for ev in events:
        bi = ev.get("bar_index")
        t = ev.get("type")

        if t == "agent_step":
            bars_data.setdefault(bi, {"date": ev.get("dt", ""), "rounds": 0,
                                       "tool_calls": 0, "compute_calls": 0,
                                       "compute_errors": 0, "action": "hold"})
        elif t == "llm_call":
            bars_data.setdefault(bi, {"date": "", "rounds": 0, "tool_calls": 0,
                                       "compute_calls": 0, "compute_errors": 0,
                                       "action": "hold"})
            r = ev.get("round", 0)
            if r > bars_data[bi]["rounds"]:
                bars_data[bi]["rounds"] = r
            if not model:
                model = ev.get("model", "")
        elif t == "tool_call":
            tool_calls.append(ev)
            if bi in bars_data:
                bars_data[bi]["tool_calls"] += 1
                if ev.get("tool") == "compute":
                    bars_data[bi]["compute_calls"] += 1
                    out = ev.get("output", {})
                    if isinstance(out, dict) and "error" in out:
                        bars_data[bi]["compute_errors"] += 1
        elif t == "decision":
            decisions.append(ev)
            if bi in bars_data:
                bars_data[bi]["action"] = ev.get("action", "hold")
            if not model:
                model = ev.get("model", "")

    # ── Overview ──
    strategy = _infer_strategy(events)
    decision_bars = len(bars_data)
    total_bars = max((ev.get("bar_index", 0) for ev in events), default=0) + 1
    total_rounds = sum(b["rounds"] for b in bars_data.values())
    total_tool_calls = len(tool_calls)

    overview = {
        "strategy": strategy, "model": model,
        "total_bars": total_bars, "decision_bars": decision_bars,
        "total_rounds": total_rounds, "total_tool_calls": total_tool_calls,
    }

    # ── Tool Summary ──
    tool_stats: dict[str, dict] = defaultdict(lambda: {"calls": 0, "ok": 0,
                                                        "errors": 0, "total_ms": 0.0})
    for tc in tool_calls:
        name = tc.get("tool", "unknown")
        s = tool_stats[name]
        s["calls"] += 1
        out = tc.get("output", {})
        if isinstance(out, dict) and "error" in out:
            s["errors"] += 1
        else:
            s["ok"] += 1
        s["total_ms"] += tc.get("duration_ms", 0)

    tool_summary = []
    for name, s in sorted(tool_stats.items(), key=lambda x: -x[1]["calls"]):
        rate = (s["ok"] / s["calls"] * 100) if s["calls"] else 0
        avg_ms = (s["total_ms"] / s["calls"]) if s["calls"] else 0
        tool_summary.append({"tool": name, "calls": s["calls"], "ok": s["ok"],
                             "errors": s["errors"], "success_rate": round(rate, 1),
                             "avg_duration_ms": round(avg_ms, 1)})

    # ── Per-Bar ──
    per_bar = []
    for bi in sorted(bars_data):
        b = bars_data[bi]
        per_bar.append({"bar_index": bi, "date": b["date"], "rounds": b["rounds"],
                        "tool_calls": b["tool_calls"], "compute_calls": b["compute_calls"],
                        "compute_errors": b["compute_errors"], "action": b["action"]})

    # ── Compute Error Analysis ──
    compute_calls_list = [tc for tc in tool_calls if tc.get("tool") == "compute"]
    compute_total = len(compute_calls_list)
    compute_errors_list = [tc for tc in compute_calls_list
                           if isinstance(tc.get("output"), dict) and "error" in tc["output"]]
    compute_error_count = len(compute_errors_list)
    compute_error_rate = (compute_error_count / compute_total * 100) if compute_total else 0

    # 错误分类
    categories: dict[str, dict] = defaultdict(lambda: {"count": 0, "bars": []})
    for tc in compute_errors_list:
        msg = tc["output"].get("error", "")
        cat = classify_error(msg)
        categories[cat]["count"] += 1
        bi = tc.get("bar_index")
        if bi is not None and bi not in categories[cat]["bars"]:
            categories[cat]["bars"].append(bi)

    cat_out = {}
    for cat, info in sorted(categories.items(), key=lambda x: -x[1]["count"]):
        pct = (info["count"] / compute_error_count * 100) if compute_error_count else 0
        cat_out[cat] = {"count": info["count"], "pct": round(pct, 1),
                        "bars": sorted(info["bars"])}

    # 重复模式
    repeat_patterns = []
    for cat, info in cat_out.items():
        bar_count = len(info["bars"])
        repeat_patterns.append({
            "category": cat, "bar_count": bar_count,
            "total_bars": decision_bars,
            "is_persistent": bar_count > decision_bars * 0.5 if decision_bars else False,
        })

    # Helper 使用统计
    helper_usage = {h: 0 for h in HELPERS}
    for tc in compute_calls_list:
        code = tc.get("input", {}).get("code", "")
        for h in HELPERS:
            helper_usage[h] += len(re.findall(rf"\b{h}\s*\(", code))

    compute = {
        "total": compute_total, "errors": compute_error_count,
        "error_rate": round(compute_error_rate, 1),
        "categories": cat_out, "repeat_patterns": repeat_patterns,
        "helper_usage": helper_usage,
    }

    # ── Error Samples ──
    seen_cats: set[str] = set()
    error_samples = []
    for tc in compute_errors_list:
        msg = tc["output"].get("error", "")
        cat = classify_error(msg)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        code = tc.get("input", {}).get("code", "")
        snippet = "\n".join(code.splitlines()[:3])
        if len(snippet) > 360:
            snippet = snippet[:360] + "..."
        error_samples.append({
            "category": cat, "bar_index": tc.get("bar_index"),
            "round": tc.get("round"), "error": msg[:200],
            "code_snippet": snippet,
        })

    # ── Verdict ──
    passed = compute_error_rate <= threshold
    verdict = {"pass": passed, "error_rate": round(compute_error_rate, 1),
               "threshold": threshold}

    return {"overview": overview, "tool_summary": tool_summary, "per_bar": per_bar,
            "compute": compute, "error_samples": error_samples, "verdict": verdict}


def _infer_strategy(events: list[dict]) -> str:
    """从 context 事件的 formatted_text 推断策略名"""
    for ev in events:
        if ev.get("type") == "context":
            text = ev.get("formatted_text", "")
            m = re.search(r"策略[：:]\s*(\S+)", text)
            if m:
                return m.group(1)
    return "unknown"


# ── 文本格式化 ────────────────────────────────────────────────────

def format_report(a: dict) -> str:
    """将分析结果格式化为终端可读文本"""
    lines: list[str] = []
    o = a["overview"]

    # Section 1: Overview
    lines.append(f"\n{'═' * 42}")
    lines.append(f"  AgenticBT Trace Analysis")
    lines.append(f"{'═' * 42}")
    lines.append(f"  Strategy: {o['strategy']} | Model: {o['model']}")
    lines.append(f"  Bars: {o['total_bars']} ({o['decision_bars']} decision bars)"
                 f" | Rounds: {o['total_rounds']} | Tool calls: {o['total_tool_calls']}")

    # Section 2: Tool Summary
    lines.append(f"\n{'─' * 42}")
    lines.append(f"  Tool Call Summary")
    lines.append(f"{'─' * 42}")
    lines.append(f"  {'Tool':<20} {'Calls':>5} {'OK':>4} {'Err':>4} {'Rate':>7} {'Avg ms':>7}")
    for t in a["tool_summary"]:
        lines.append(f"  {t['tool']:<20} {t['calls']:>5} {t['ok']:>4} {t['errors']:>4}"
                     f" {t['success_rate']:>6.1f}% {t['avg_duration_ms']:>6.1f}")

    # Section 3: Per-Bar Breakdown
    bars = a["per_bar"]
    if bars:
        lines.append(f"\n{'─' * 42}")
        lines.append(f"  Per-Bar Breakdown")
        lines.append(f"{'─' * 42}")
        lines.append(f"  {'Bar':>4}  {'Date':<12} {'Rnds':>5} {'Tools':>5}"
                     f" {'Comp':>5} {'Err':>4}  Action")
        for b in bars:
            lines.append(f"  {b['bar_index']:>4}  {str(b['date']):<12}"
                         f" {b['rounds']:>5} {b['tool_calls']:>5}"
                         f" {b['compute_calls']:>5} {b['compute_errors']:>4}"
                         f"  {b['action']}")
        n = len(bars)
        avg_r = sum(b["rounds"] for b in bars) / n
        avg_t = sum(b["tool_calls"] for b in bars) / n
        avg_c = sum(b["compute_calls"] for b in bars) / n
        avg_e = sum(b["compute_errors"] for b in bars) / n
        lines.append(f"  {'─' * 52}")
        lines.append(f"  {'Avg':>4}  {'':<12} {avg_r:>5.1f} {avg_t:>5.1f}"
                     f" {avg_c:>5.1f} {avg_e:>4.1f}")
        lines.append(f"  {'Ideal':>4}  {'':<12} {'2-3':>5} {'2-4':>5}"
                     f" {'1-2':>5} {'0':>4}")

    # Section 4: Compute Error Analysis
    c = a["compute"]
    if c["total"] > 0:
        lines.append(f"\n{'─' * 42}")
        lines.append(f"  Compute Error Analysis")
        lines.append(f"{'─' * 42}")
        lines.append(f"  Total: {c['total']} calls, {c['errors']} errors"
                     f" ({c['error_rate']}%)")
        if c["categories"]:
            lines.append(f"\n  Error Categories:")
            for cat, info in c["categories"].items():
                bar_str = ",".join(str(b) for b in info["bars"])
                lines.append(f"    {cat:<30} {info['count']:>3}  ({info['pct']:>5.1f}%)"
                             f"  <- bars: {bar_str}")
        for rp in c["repeat_patterns"]:
            if rp["is_persistent"]:
                lines.append(f"    ! \"{rp['category']}\" on"
                             f" {rp['bar_count']}/{rp['total_bars']} bars"
                             f" -- agent never learns")
        if any(v > 0 for v in c["helper_usage"].values()) or c["errors"] > 0:
            lines.append(f"\n  Helper Usage:")
            for h, cnt in c["helper_usage"].items():
                mark = "v" if cnt > 0 else "x"
                lines.append(f"    {h}(): {cnt} calls {mark}")

    # Section 5: Error Samples
    if a["error_samples"]:
        lines.append(f"\n{'─' * 42}")
        lines.append(f"  Error Samples (first per category)")
        lines.append(f"{'─' * 42}")
        for i, s in enumerate(a["error_samples"], 1):
            lines.append(f"\n  [{i}] {s['category']}"
                         f" (bar={s['bar_index']}, round={s['round']})")
            lines.append(f"      error: {s['error']}")
            if s["code_snippet"]:
                for cl in s["code_snippet"].splitlines():
                    lines.append(f"      code:  {cl}")

    # Verdict
    v = a["verdict"]
    tag = "PASS" if v["pass"] else "FAIL"
    lines.append(f"\n{'═' * 42}")
    lines.append(f"  VERDICT: {tag}")
    lines.append(f"  Compute error rate: {v['error_rate']}%"
                 f" {'<=' if v['pass'] else '>'} {v['threshold']}% threshold")
    lines.append(f"{'═' * 42}\n")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AgenticBT Trace Analyzer")
    parser.add_argument("--trace-file", type=Path, help="已有 trace.jsonl 路径")
    parser.add_argument("--threshold", type=float, default=50.0,
                        help="compute 错误率阈值 (默认 50%%)")
    parser.add_argument("--json-out", type=Path, default=None,
                        help="JSON 输出路径 (默认: trace 同目录/analysis.json)")
    args = parser.parse_args()

    if not args.trace_file:
        print("用法: python scripts/analyze_trace.py --trace-file /path/to/trace.jsonl")
        print("提示: 先运行 demo.py 生成 trace，workspace 路径见输出末尾")
        sys.exit(1)

    trace_path = args.trace_file
    if not trace_path.exists():
        print(f"错误: 文件不存在 {trace_path}")
        sys.exit(1)

    events = parse_trace(trace_path)
    if not events:
        print("错误: trace 文件为空")
        sys.exit(1)

    result = analyze(events, args.threshold)

    # 终端输出
    print(format_report(result))

    # JSON 输出
    json_path = args.json_out or trace_path.parent / "analysis.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  JSON saved: {json_path}")


if __name__ == "__main__":
    main()
