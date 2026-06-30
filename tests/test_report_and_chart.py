import pandas as pd

from etf_trading.backtest.engine import Trade
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


def test_chart_payload_adds_buy_and_sell_trade_markers_to_candles():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "open": [1.0, 2.0, 3.0],
            "high": [1.2, 2.2, 3.2],
            "low": [0.8, 1.8, 2.8],
            "close": [1.1, 2.1, 3.1],
            "volume": [100, 200, 300],
        }
    )
    trades = [
        Trade(
            etf_code="510300",
            trade_date=pd.Timestamp("2024-01-03"),
            action="BUY",
            price=2.0,
            weight_before=0.0,
            weight_after=1.0,
            signal_date=pd.Timestamp("2024-01-02"),
        ),
        Trade(
            etf_code="510300",
            trade_date=pd.Timestamp("2024-01-04"),
            action="SELL",
            price=3.0,
            weight_before=1.0,
            weight_after=0.0,
            signal_date=pd.Timestamp("2024-01-03"),
        ),
    ]

    payload = build_lightweight_chart_payload(prices, trades=trades)
    candle_series = next(series for series in payload[0]["series"] if series["type"] == "Candlestick")

    assert [marker["time"] for marker in candle_series["markers"]] == ["2024-01-03", "2024-01-04"]
    assert candle_series["markers"][0]["shape"] == "arrowUp"
    assert candle_series["markers"][1]["shape"] == "arrowDown"
    assert "0% -> 100%" in candle_series["markers"][0]["text"]


def test_chart_payload_can_hide_unselected_moving_averages():
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
        }
    )

    payload = build_lightweight_chart_payload(prices, ma_columns=["ma51"])
    line_titles = [series["options"].get("title") for chart in payload for series in chart["series"] if series["type"] == "Line"]

    assert line_titles == ["MA51"]


def test_chart_payload_can_render_close_line_with_trade_markers_instead_of_candles():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [1.0, 2.0],
            "high": [1.2, 2.2],
            "low": [0.8, 1.8],
            "close": [1.1, 2.1],
            "volume": [100, 200],
            "ma51": [1.0, 1.5],
        }
    )
    trades = [
        Trade(
            etf_code="510300",
            trade_date=pd.Timestamp("2024-01-03"),
            action="BUY",
            price=2.0,
            weight_before=0.0,
            weight_after=0.5,
            signal_date=pd.Timestamp("2024-01-02"),
        )
    ]

    payload = build_lightweight_chart_payload(prices, trades=trades, chart_type="line", ma_columns=[])
    series_types = [series["type"] for chart in payload for series in chart["series"]]
    price_series = payload[0]["series"][0]

    assert "Candlestick" not in series_types
    assert price_series["type"] == "Line"
    assert price_series["options"]["title"] == "收盘价 Close"
    assert price_series["markers"][0]["text"] == "BUY 0% -> 50% @ 2.00"


def test_chart_payload_enables_direct_zoom_and_pan_controls():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02"]),
            "open": [1.0],
            "high": [1.2],
            "low": [0.8],
            "close": [1.1],
            "volume": [100],
        }
    )

    payload = build_lightweight_chart_payload(prices, chart_type="line", ma_columns=[])
    options = payload[0]["chart"]

    assert options["handleScale"]["mouseWheel"] is True
    assert options["handleScale"]["pinch"] is True
    assert options["handleScroll"]["pressedMouseMove"] is True


def test_chart_payload_uses_custom_buy_sell_marker_text_for_index_signals():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [1.0, 2.0],
            "high": [1.2, 2.2],
            "low": [0.8, 1.8],
            "close": [1.1, 2.1],
            "volume": [100, 200],
        }
    )
    index_signals = [
        {
            "trade_date": pd.Timestamp("2024-01-03"),
            "action": "BUY",
            "price": 2.1,
            "marker_text": "BUY",
        }
    ]

    payload = build_lightweight_chart_payload(prices, trades=index_signals, chart_type="line", ma_columns=[])
    price_series = payload[0]["series"][0]

    assert price_series["markers"][0]["shape"] == "arrowUp"
    assert price_series["markers"][0]["text"] == "BUY"
