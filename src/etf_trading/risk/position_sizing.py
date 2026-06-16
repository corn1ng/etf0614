"""Position caps and percentage-only sizing rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionRecommendation:
    add_weight: float
    target_weight: float
    unit: str = "percentage"


class PositionSizer:
    """Balanced-conservative position sizing for a personal ETF account."""

    SINGLE_ETF_CAPS = {
        "A股宽基": 0.15,
        "A股行业": 0.08,
        "A股主题": 0.06,
        "港股宽基": 0.10,
        "港股科技": 0.06,
        "港股医药": 0.06,
        "港股高股息/红利": 0.08,
        "债券": 0.20,
        "商品": 0.10,
        "货币/现金替代": 0.50,
    }

    HK_TOTAL_CAPS = {
        "bull": 0.20,
        "range": 0.20,
        "bear": 0.10,
        "high_volatility": 0.10,
    }

    SINGLE_TRADE_ADD_CAPS = {
        "A股宽基": 0.05,
        "A股行业": 0.03,
        "A股主题": 0.02,
        "港股宽基": 0.03,
        "港股科技": 0.02,
        "港股医药": 0.02,
        "港股高股息/红利": 0.02,
        "债券": 0.05,
        "商品": 0.03,
        "货币/现金替代": 0.10,
    }

    def single_etf_cap(self, category: str) -> float:
        return self.SINGLE_ETF_CAPS.get(category, 0.06)

    def cross_market_hk_cap(self, market_state: str) -> float:
        return self.HK_TOTAL_CAPS.get(market_state, 0.20)

    def single_trade_add_cap(self, category: str) -> float:
        return self.SINGLE_TRADE_ADD_CAPS.get(category, 0.02)

    def recommend_buy_percentage(
        self,
        category: str,
        current_weight: float,
        target_weight: float,
        risk_multiplier: float = 1.0,
    ) -> PositionRecommendation:
        cap = self.single_etf_cap(category)
        capped_target = min(target_weight, cap) * max(min(risk_multiplier, 1.0), 0.0)
        add_cap = self.single_trade_add_cap(category)
        add_weight = min(max(capped_target - current_weight, 0.0), add_cap)
        final_target = current_weight + add_weight
        return PositionRecommendation(
            add_weight=round(add_weight, 4),
            target_weight=round(final_target, 4),
        )
