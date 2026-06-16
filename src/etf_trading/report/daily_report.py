"""Markdown report renderer for daily ETF advice."""

from __future__ import annotations

from datetime import date

import pandas as pd

from etf_trading.strategy.models import StrategySignal


class DailyAdviceReport:
    def render(self, trade_date: pd.Timestamp | date, market_state: str, signals: list[StrategySignal]) -> str:
        lines = [
            f"# ETF 每日交易指引 - {pd.Timestamp(trade_date).date()}",
            "",
            "## 市场状态",
            f"- 当前市场环境：{market_state}",
            "- 风险偏好：平衡偏保守",
            "",
            "## 今日买入建议",
        ]
        buys = [s for s in signals if s.action == "BUY"]
        lines.extend(self._signal_lines(buys, empty_text="今日没有满足规则的新买入。"))
        lines.extend(["", "## 今日卖出/减仓建议"])
        sells = [s for s in signals if s.action in {"SELL", "REDUCE"}]
        lines.extend(self._signal_lines(sells, empty_text="今日没有满足规则的卖出或减仓。"))
        lines.extend(["", "## 今日继续持有"])
        holds = [s for s in signals if s.action == "HOLD"]
        lines.extend(self._signal_lines(holds, empty_text="今日没有持有提示。"))
        lines.extend(["", "## 禁止操作清单"])
        forbids = [s for s in signals if s.action == "FORBID"]
        lines.extend(self._signal_lines(forbids, empty_text="今日没有禁止操作标记。"))
        lines.extend(["", "## 总结"])
        actionable = buys + sells
        lines.append(f"- 今日是否需要交易：{'是' if actionable else '否'}")
        lines.append("- 最高优先级动作：按风险过滤后的 BUY / SELL / REDUCE 信号排序执行，最多 1-3 个。")
        lines.append("- 当前最大风险：数据质量、流动性、折溢价和跨境 ETF 底层市场状态。")
        return "\n".join(lines)

    def _signal_lines(self, signals: list[StrategySignal], empty_text: str) -> list[str]:
        if not signals:
            return [f"- {empty_text}"]
        lines = []
        for signal in signals:
            risk = "、".join(signal.risk_tags) if signal.risk_tags else "无额外风险标签"
            rules = "、".join(signal.trigger_rules) if signal.trigger_rules else "无"
            lines.append(
                f"- {signal.etf_code}：{signal.action}，目标仓位 {_pct(signal.target_weight)}；"
                f"理由：{signal.reason}；触发规则：{rules}；风险：{risk}"
            )
        return lines


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"
