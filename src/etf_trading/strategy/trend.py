"""Low-frequency balanced-conservative trend strategy."""

from __future__ import annotations

import math

import pandas as pd

from etf_trading.risk.position_sizing import PositionSizer
from etf_trading.strategy.models import StrategySignal
from etf_trading.universe.classification import is_hk_cross_market


class TrendStrategy:
    def __init__(
        self,
        min_trade_interval_days: int = 10,
        min_avg_amount_20: float = 30_000_000,
        max_abs_premium_rate: float = 0.005,
        high_volatility_20: float = 0.04,
        sizer: PositionSizer | None = None,
    ) -> None:
        self.min_trade_interval_days = min_trade_interval_days
        self.min_avg_amount_20 = min_avg_amount_20
        self.max_abs_premium_rate = max_abs_premium_rate
        self.high_volatility_20 = high_volatility_20
        self.sizer = sizer or PositionSizer()

    def evaluate(
        self,
        row: pd.Series,
        market_risk_on: bool,
        current_weight: float = 0.0,
    ) -> StrategySignal:
        etf_code = str(row.get("etf_code", ""))
        trade_date = pd.Timestamp(row.get("trade_date"))
        category = str(row.get("category", "A股主题"))
        trigger_rules: list[str] = []
        risk_tags: list[str] = []

        quality = float(row.get("data_quality_score", 1.0) or 0.0)
        if quality < 0.9:
            return self._signal(etf_code, trade_date, "FORBID", 0.0, "数据质量不足", ["data_quality"], ["数据质量"])

        if is_hk_cross_market(category) and row.get("underlying_market_open") is False:
            return self._signal(etf_code, trade_date, "FORBID", 0.0, "底层市场休市，折溢价风险升高", ["hk_market_closed"], ["底层市场休市"])

        avg_amount = _safe_float(row.get("avg_amount_20"))
        if avg_amount < self.min_avg_amount_20:
            return self._signal(etf_code, trade_date, "FORBID", 0.0, "近20日成交额不足", ["liquidity"], ["流动性"])

        premium = _safe_float(row.get("premium_rate"))
        if abs(premium) > self.max_abs_premium_rate:
            return self._signal(etf_code, trade_date, "FORBID", 0.0, "折溢价异常，禁止新增买入", ["premium"], ["折溢价"])

        close = _safe_float(row.get("close"))
        ma51 = _safe_float(row.get("ma51"))
        ma120 = _safe_float(row.get("ma120"))
        ma250 = _safe_float(row.get("ma250"))
        momentum_20 = _safe_float(row.get("momentum_20"))
        momentum_60 = _safe_float(row.get("momentum_60"))
        rs_rank = _safe_float(row.get("relative_strength_rank", 1.0), default=1.0)

        if not market_risk_on:
            if current_weight > 0:
                return self._signal(etf_code, trade_date, "REDUCE", current_weight * 0.5, "大盘风险过滤关闭，降低权益仓位", ["market_risk_off"], ["大盘风险"])
            return self._signal(etf_code, trade_date, "HOLD", 0.0, "大盘风险过滤关闭，暂不新增", ["market_risk_off"], ["大盘风险"])

        if close < ma120 and current_weight > 0:
            return self._signal(etf_code, trade_date, "SELL", 0.0, "跌破MA120，趋势失效", ["close_below_MA120"], ["趋势失效"])

        buy_conditions = [
            close > ma51,
            close > ma120,
            momentum_20 > 0,
            momentum_60 > 0,
            rs_rank <= 0.30,
        ]
        if all(buy_conditions):
            trigger_rules.extend(["MA51", "MA120", "momentum_20_positive", "momentum_60_positive", "relative_strength_top_30pct"])
            if close > ma250:
                trigger_rules.append("MA250")
            if not _trade_interval_ok(row.get("last_action_date"), trade_date, self.min_trade_interval_days):
                return self._signal(etf_code, trade_date, "HOLD", current_weight, "低频交易约束：距离上次主动交易不足", ["低频交易约束"], risk_tags)

            volatility = _safe_float(row.get("volatility_20"))
            risk_multiplier = 0.5 if volatility > self.high_volatility_20 else 1.0
            if risk_multiplier < 1.0:
                risk_tags.append("高波动，目标仓位减半")

            target = self.sizer.recommend_buy_percentage(
                category=category,
                current_weight=current_weight,
                target_weight=self.sizer.single_etf_cap(category),
                risk_multiplier=risk_multiplier,
            ).target_weight
            return self._signal(etf_code, trade_date, "BUY", target, "趋势信号触发", trigger_rules, risk_tags)

        if close < ma51 and momentum_20 < 0 and current_weight > 0:
            return self._signal(etf_code, trade_date, "REDUCE", current_weight * 0.5, "跌破MA51且短期动量转弱", ["close_below_MA51", "momentum_20_negative"], risk_tags)

        return self._signal(etf_code, trade_date, "HOLD", current_weight, "趋势未满足新交易条件", ["no_action"], risk_tags)

    @staticmethod
    def _signal(
        etf_code: str,
        trade_date: pd.Timestamp,
        action: str,
        target_weight: float,
        reason: str,
        trigger_rules: list[str],
        risk_tags: list[str],
    ) -> StrategySignal:
        return StrategySignal(
            etf_code=etf_code,
            trade_date=trade_date,
            action=action,  # type: ignore[arg-type]
            target_weight=target_weight,
            reason=reason,
            trigger_rules=trigger_rules,
            risk_tags=risk_tags,
        )


class TrendV1Strategy:
    """MA60/ATR ETF trend strategy for research and semi-automated review."""

    def __init__(
        self,
        min_trade_interval_days: int = 10,
        min_avg_amount_20: float = 100_000_000,
        max_abs_premium_rate: float = 0.005,
        max_atr_distance_from_ma20: float = 2.0,
        sizer: PositionSizer | None = None,
    ) -> None:
        self.min_trade_interval_days = min_trade_interval_days
        self.min_avg_amount_20 = min_avg_amount_20
        self.max_abs_premium_rate = max_abs_premium_rate
        self.max_atr_distance_from_ma20 = max_atr_distance_from_ma20
        self.sizer = sizer or PositionSizer()

    def evaluate(
        self,
        row: pd.Series,
        market_risk_on: bool,
        current_weight: float = 0.0,
    ) -> StrategySignal:
        etf_code = str(row.get("etf_code", ""))
        trade_date = pd.Timestamp(row.get("trade_date"))
        category = str(row.get("category", "A股主题"))

        quality = _safe_float(row.get("data_quality_score"), default=1.0)
        if quality < 0.9:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "数据质量不足", ["data_quality"], ["数据质量"])

        if is_hk_cross_market(category) and row.get("underlying_market_open") is False:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "底层市场休市，折溢价风险升高", ["hk_market_closed"], ["底层市场休市"])

        avg_amount = _safe_float(row.get("avg_amount_20"))
        if avg_amount < self.min_avg_amount_20:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "近20日成交额不足", ["liquidity"], ["流动性"])

        premium = _safe_float(row.get("premium_rate"))
        if abs(premium) > self.max_abs_premium_rate:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "折溢价异常，禁止新增买入", ["premium"], ["折溢价"])

        close = _required_float(row.get("close"))
        ma60 = _required_float(row.get("ma60"))

        if close is None or ma60 is None:
            return TrendStrategy._signal(
                etf_code,
                trade_date,
                "HOLD",
                current_weight,
                "ETF趋势V1必需指标缺失，暂停交易",
                ["required_indicator_missing"],
                ["required_indicator_missing"],
            )

        momentum_20 = _safe_float(row.get("momentum_20"))

        if current_weight > 0 and close < ma60:
            return TrendStrategy._signal(etf_code, trade_date, "SELL", 0.0, "跌破MA60，趋势失效", ["close_below_MA60"], ["趋势失效"])

        if not market_risk_on:
            if current_weight > 0:
                return TrendStrategy._signal(etf_code, trade_date, "REDUCE", current_weight * 0.5, "大盘风险过滤关闭，降低权益仓位", ["market_risk_off"], ["大盘风险"])
            return TrendStrategy._signal(etf_code, trade_date, "HOLD", 0.0, "大盘风险过滤关闭，暂不新增", ["market_risk_off"], ["大盘风险"])

        ma20 = _required_float(row.get("ma20"))
        ma60_slope = _required_float(row.get("ma60_slope_20"))
        momentum_60_skip5 = _required_float(row.get("momentum_60_skip5"))
        momentum_120_skip5 = _required_float(row.get("momentum_120_skip5"))
        rs_rank = _required_float(row.get("relative_strength_rank"))
        distance_ma20_atr = _required_float(row.get("distance_ma20_atr"))
        if any(
            value is None
            for value in [
                ma20,
                ma60_slope,
                momentum_60_skip5,
                momentum_120_skip5,
                rs_rank,
                distance_ma20_atr,
            ]
        ):
            return TrendStrategy._signal(
                etf_code,
                trade_date,
                "HOLD",
                current_weight,
                "ETF趋势V1必需指标缺失，暂停新增",
                ["required_indicator_missing"],
                ["required_indicator_missing"],
            )

        if close < ma20 and momentum_20 < 0 and current_weight > 0:
            return TrendStrategy._signal(etf_code, trade_date, "REDUCE", current_weight * 0.5, "跌破MA20且短期动量转弱", ["close_below_MA20", "momentum_20_negative"], [])

        if distance_ma20_atr > self.max_atr_distance_from_ma20:
            return TrendStrategy._signal(etf_code, trade_date, "HOLD", current_weight, "价格相对MA20过热，暂停新增", ["no_new_buy"], ["overextended_2ATR"])

        buy_conditions = [
            close > ma60,
            ma20 > ma60,
            ma60_slope > 0,
            momentum_60_skip5 > 0,
            momentum_120_skip5 > 0,
            rs_rank <= 0.30,
        ]
        if all(buy_conditions):
            if not _trade_interval_ok(row.get("last_action_date"), trade_date, self.min_trade_interval_days):
                return TrendStrategy._signal(etf_code, trade_date, "HOLD", current_weight, "低频交易约束：距离上次主动交易不足", ["低频交易约束"], [])

            target = self.sizer.recommend_buy_percentage(
                category=category,
                current_weight=current_weight,
                target_weight=self.sizer.single_etf_cap(category),
            ).target_weight
            return TrendStrategy._signal(
                etf_code,
                trade_date,
                "BUY",
                target,
                "ETF趋势V1信号触发",
                [
                    "price_above_MA60",
                    "MA20_above_MA60",
                    "MA60_slope_positive",
                    "momentum_60_skip5_positive",
                    "momentum_120_skip5_positive",
                    "relative_strength_top_30pct",
                    "not_overextended_2ATR",
                ],
                [],
            )

        return TrendStrategy._signal(etf_code, trade_date, "HOLD", current_weight, "趋势未满足新交易条件", ["no_action"], [])


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(value_float):
        return default
    return value_float


def _required_float(value: object) -> float | None:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value_float):
        return None
    return value_float


def _trade_interval_ok(last_action_date: object, trade_date: pd.Timestamp, min_days: int) -> bool:
    if last_action_date is None or pd.isna(last_action_date):
        return True
    last = pd.Timestamp(last_action_date)
    return (trade_date - last).days >= min_days
