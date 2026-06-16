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
