from etf_trading.risk.position_sizing import PositionSizer


def test_uses_conservative_hong_kong_cross_market_position_caps():
    sizer = PositionSizer()

    assert sizer.single_etf_cap("港股宽基") == 0.10
    assert sizer.single_etf_cap("港股科技") == 0.06
    assert sizer.single_etf_cap("港股医药") == 0.06
    assert sizer.cross_market_hk_cap("bull") == 0.20
    assert sizer.cross_market_hk_cap("bear") == 0.10
    assert sizer.cross_market_hk_cap("high_volatility") == 0.10


def test_buy_recommendation_is_percentage_only_and_respects_caps():
    sizer = PositionSizer()

    recommendation = sizer.recommend_buy_percentage(
        category="港股科技",
        current_weight=0.04,
        target_weight=0.10,
        risk_multiplier=1.0,
    )

    assert recommendation.add_weight == 0.02
    assert recommendation.target_weight == 0.06
    assert recommendation.unit == "percentage"


def test_theme_group_and_aggregate_caps_are_available():
    sizer = PositionSizer()

    assert sizer.theme_group_cap("科技高相关") == 0.25
    assert sizer.aggregate_cap("industry_theme_total") == 0.50
    assert sizer.risk_budget("A股宽基") == 0.0075
    assert sizer.risk_budget("A股主题") == 0.0040


def test_drawdown_overlay_returns_equity_cap_multiplier():
    sizer = PositionSizer()

    assert sizer.drawdown_equity_multiplier(-0.05) == 1.0
    assert sizer.drawdown_equity_multiplier(-0.08) == 0.75
    assert sizer.drawdown_equity_multiplier(-0.12) == 0.30
    assert sizer.drawdown_equity_multiplier(-0.15) == 0.0
    assert sizer.drawdown_equity_multiplier(0.15) == 1.0
