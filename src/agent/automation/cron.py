"""
[INPUT]: datetime, zoneinfo
[OUTPUT]: SimpleCron
[POS]: 自动化子系统的轻量 cron 解析器：支持 5-field cron 的常用表达式
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SimpleCron:
    minute: set[int]
    hour: set[int]
    day: set[int]
    month: set[int]
    weekday: set[int]

    @classmethod
    def parse(cls, expr: str) -> "SimpleCron":
        parts = str(expr or "").split()
        if len(parts) != 5:
            raise ValueError("cron_expr 必须是 5 段：min hour day month weekday")
        return cls(
            minute=_parse_field(parts[0], 0, 59),
            hour=_parse_field(parts[1], 0, 23),
            day=_parse_field(parts[2], 1, 31),
            month=_parse_field(parts[3], 1, 12),
            weekday=_parse_field(parts[4], 0, 7, normalize_weekday=True),
        )

    def matches(self, dt: datetime) -> bool:
        cron_weekday = (dt.weekday() + 1) % 7  # python: mon=0 -> cron: mon=1, sun=0
        return (
            dt.minute in self.minute
            and dt.hour in self.hour
            and dt.day in self.day
            and dt.month in self.month
            and cron_weekday in self.weekday
        )

    def next_after(self, dt: datetime, *, timezone: str) -> datetime:
        zone = ZoneInfo(timezone)
        current = dt.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = current + timedelta(days=370)
        while current <= limit:
            if self.matches(current):
                return current
            current += timedelta(minutes=1)
        raise ValueError("cron_expr 在 370 天内没有匹配时间")


def preview(expr: str, *, timezone: str, now: datetime, count: int = 3) -> list[str]:
    cron = SimpleCron.parse(expr)
    out: list[str] = []
    cursor = now
    for _ in range(max(0, count)):
        nxt = cron.next_after(cursor, timezone=timezone)
        out.append(nxt.isoformat())
        cursor = nxt
    return out


def _parse_field(raw: str, minimum: int, maximum: int, *, normalize_weekday: bool = False) -> set[int]:
    parts = set()
    for token in str(raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        parts.update(_expand_token(token, minimum, maximum, normalize_weekday=normalize_weekday))
    if not parts:
        raise ValueError(f"无效 cron 字段: {raw!r}")
    return parts


def _expand_token(token: str, minimum: int, maximum: int, *, normalize_weekday: bool) -> set[int]:
    if token == "*":
        return set(range(minimum, maximum + 1))
    if token.startswith("*/"):
        step = int(token[2:])
        if step <= 0:
            raise ValueError("cron step 必须大于 0")
        return set(range(minimum, maximum + 1, step))

    if "/" in token:
        base, step_text = token.split("/", 1)
        step = int(step_text)
        values = sorted(_expand_token(base, minimum, maximum, normalize_weekday=normalize_weekday))
        if step <= 0:
            raise ValueError("cron step 必须大于 0")
        return {value for idx, value in enumerate(values) if idx % step == 0}

    if "-" in token:
        left, right = token.split("-", 1)
        start = int(left)
        end = int(right)
        if start > end:
            raise ValueError("cron range 起点不能大于终点")
        values = set(range(start, end + 1))
    else:
        values = {int(token)}

    normalized: set[int] = set()
    for value in values:
        if normalize_weekday and value == 7:
            value = 0
        if value < minimum or value > maximum:
            raise ValueError(f"cron 值 {value} 超出范围 [{minimum}, {maximum}]")
        normalized.add(value)
    return normalized
