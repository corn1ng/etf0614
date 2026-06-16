import pandas as pd

from etf_trading.report.daily_report import DailyAdviceReport
from etf_trading.strategy.models import StrategySignal
from etf_trading.ui.chart_renderer import build_lightweight_chart_payload


def test_daily_report_outputs_percentages_and_hong_kong_risk_tags():
    report = DailyAdviceReport().render(
        trade_date=pd.Timestamp("2024-12-31"),
        market_state="震荡",
        signals=[
            StrategySignal(
                etf_code="513130",
                trade_date=pd.Timestamp("2024-12-31"),
                action="BUY",
                target_weight=0.06,
                reason="趋势信号触发",
                trigger_rules=["MA51", "MA120"],
                risk_tags=["折溢价风险", "港股跨境ETF"],
            )
        ],
    )

    assert "6.00%" in report
    assert "港股跨境ETF" in report
    assert "折溢价风险" in report


def test_chart_payload_contains_candles_volume_and_required_moving_averages():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [1.0, 2.0],
            "high": [1.2, 2.2],
            "low": [0.8, 1.8],
            "close": [1.1, 2.1],
            "volume": [100, 200],
            "ma51": [1.0, 1.5],
            "ma120": [0.9, 1.4],
            "ma250": [0.8, 1.3],
            "ma850": [0.7, 1.2],
        }
    )

    payload = build_lightweight_chart_payload(prices)
    series_types = [series["type"] for chart in payload for series in chart["series"]]
    line_titles = [series["options"].get("title") for chart in payload for series in chart["series"]]

    assert "Candlestick" in series_types
    assert "Histogram" in series_types
    assert ["MA51", "MA120", "MA250", "MA850"] == line_titles[:4]
