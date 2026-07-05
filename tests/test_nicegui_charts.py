import pandas as pd

from etf_trading.nicegui_app.components.charts import (
    build_chart_html,
    build_echart_options,
    build_static_chart_html,
    chart_record_label,
    chart_range_window,
)
from etf_trading.nicegui_app.state import etf_chart_payload, index_chart_payload


def test_build_chart_html_embeds_payload_and_container():
    html = build_chart_html([{"chart": {"height": 320}, "series": []}], element_id="chart-a")

    assert 'id="chart-a"' in html
    assert "LightweightCharts" in html
    assert '"height": 320' in html
    assert "ResizeObserver" in html


def test_build_static_chart_html_renders_svg_without_script_tags():
    payload = [
        {
            "chart": {"height": 320},
            "series": [
                {
                    "type": "Candlestick",
                    "data": [{"time": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10.5}],
                }
            ],
        }
    ]

    html = build_static_chart_html(payload, element_id="static-a")

    assert 'id="static-a"' in html
    assert "<svg" in html
    assert "<script" not in html
    assert "K线图" in html


def test_build_echart_options_preserves_candles_ma_volume_and_zoom():
    payload = [
        {
            "chart": {"height": 520},
            "series": [
                {
                    "type": "Candlestick",
                    "data": [
                        {"time": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10.5},
                        {"time": "2026-01-02", "open": 10.5, "high": 12, "low": 10, "close": 11.5},
                    ],
                },
                {
                    "type": "Line",
                    "options": {"title": "MA51", "color": "#eab308"},
                    "data": [
                        {"time": "2026-01-01", "value": 10.2},
                        {"time": "2026-01-02", "value": 10.4},
                    ],
                },
            ],
        },
        {
            "chart": {"height": 160},
            "series": [
                {
                    "type": "Histogram",
                    "data": [
                        {"time": "2026-01-01", "value": 1000, "color": "#dc2626"},
                        {"time": "2026-01-02", "value": 1200, "color": "#16a34a"},
                    ],
                }
            ],
        },
    ]

    options = build_echart_options(payload)

    assert options["xAxis"][0]["data"] == ["2026-01-01", "2026-01-02"]
    assert options["series"][0]["type"] == "candlestick"
    assert options["series"][0]["data"] == [[10, 10.5, 9, 11], [10.5, 11.5, 10, 12]]
    assert any(series["name"] == "MA51" and series["type"] == "line" for series in options["series"])
    assert any(series["type"] == "bar" and series["xAxisIndex"] == 1 for series in options["series"])
    assert len(options["dataZoom"]) == 2
    assert {zoom["type"] for zoom in options["dataZoom"]} == {"inside", "slider"}


def test_build_echart_options_uses_compact_aligned_tooltip_formatter():
    payload = [
        {
            "chart": {"height": 520},
            "series": [
                {
                    "type": "Candlestick",
                    "data": [{"time": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10.5}],
                },
                {
                    "type": "Line",
                    "options": {"title": "MA51", "color": "#eab308"},
                    "data": [{"time": "2026-01-01", "value": 10.234567}],
                },
            ],
        },
        {
            "chart": {"height": 160},
            "series": [
                {
                    "type": "Histogram",
                    "data": [{"time": "2026-01-01", "value": 3979605497, "color": "#16a34a"}],
                }
            ],
        },
    ]

    tooltip = build_echart_options(payload)["tooltip"]

    assert tooltip["trigger"] == "axis"
    assert ":formatter" in tooltip
    formatter = tooltip[":formatter"]
    assert "grid-template-columns" in formatter
    assert "tabular-nums" in formatter
    assert "formatVolume" in formatter
    assert "K线" in formatter
    assert "均线" in formatter
    assert "成交量" in formatter


def test_build_echart_options_defaults_long_history_to_recent_window():
    dates = [date.strftime("%Y-%m-%d") for date in pd.date_range("2024-01-01", periods=620, freq="B")]
    payload = [
        {
            "chart": {"height": 520},
            "series": [
                {
                    "type": "Candlestick",
                    "data": [
                        {"time": trade_date, "open": 10, "high": 11, "low": 9, "close": 10.5}
                        for trade_date in dates
                    ],
                }
            ],
        }
    ]

    options = build_echart_options(payload)

    assert options["dataZoom"][0]["startValue"] == dates[-500]
    assert options["dataZoom"][0]["endValue"] == dates[-1]
    assert options["dataZoom"][1]["startValue"] == dates[-500]
    assert options["dataZoom"][1]["endValue"] == dates[-1]


def test_build_echart_options_uses_custom_visible_window():
    dates = [date.strftime("%Y-%m-%d") for date in pd.date_range("2024-01-01", periods=620, freq="B")]
    payload = [_candlestick_payload(dates)]

    options = build_echart_options(payload, visible_start=dates[10], visible_end=dates[120])

    assert options["dataZoom"][0]["startValue"] == dates[10]
    assert options["dataZoom"][0]["endValue"] == dates[120]
    assert options["dataZoom"][1]["startValue"] == dates[10]
    assert options["dataZoom"][1]["endValue"] == dates[120]


def test_chart_range_window_matches_old_presets_and_custom_dates():
    dates = [date.strftime("%Y-%m-%d") for date in pd.date_range("2024-01-01", periods=620, freq="B")]
    payload = [_candlestick_payload(dates)]

    preset_start, preset_end = chart_range_window(payload, "近6月")
    threshold = (pd.Timestamp(dates[-1]) - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    expected_start = next(date for date in dates if date >= threshold)
    assert preset_start == expected_start
    assert preset_end == dates[-1]

    custom_start, custom_end = chart_range_window(payload, "自定义", start_date=dates[20], end_date=dates[60])
    assert custom_start == dates[20]
    assert custom_end == dates[60]

    assert chart_range_window(payload, "全部") == (None, None)


def test_chart_record_label_reports_full_count_and_default_window():
    payload = [
        {
            "series": [
                {
                    "type": "Candlestick",
                    "data": [{"time": str(index), "open": 1, "high": 1, "low": 1, "close": 1} for index in range(620)],
                }
            ]
        }
    ]

    assert chart_record_label(payload) == "共620条记录 · 默认显示近500条"


def test_build_echart_options_maps_trade_markers_to_candle_prices():
    payload = [
        {
            "chart": {"height": 520},
            "series": [
                {
                    "type": "Candlestick",
                    "data": [{"time": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10.5}],
                    "markers": [{"time": "2026-01-01", "position": "belowBar", "text": "BUY", "color": "#16a34a"}],
                },
            ],
        }
    ]

    options = build_echart_options(payload)

    assert options["series"][0]["markPoint"]["data"] == [
        {
            "name": "BUY",
            "coord": ["2026-01-01", 9],
            "value": "BUY",
            "itemStyle": {"color": "#16a34a"},
            "label": {"formatter": "BUY", "color": "#16a34a"},
        }
    ]


class FakeParquetStore:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def read_index_prices(self, index_code: str) -> pd.DataFrame:
        return self.frame

    def read_prices(self, etf_code: str) -> pd.DataFrame:
        return self.frame


def _prices(periods: int = 260) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=periods, freq="B"),
            "open": [10.0] * periods,
            "high": [10.5] * periods,
            "low": [9.8] * periods,
            "close": [10.2] * periods,
            "volume": [1000] * periods,
        }
    )


def _candlestick_payload(dates: list[str]) -> dict:
    return {
        "chart": {"height": 520},
        "series": [
            {
                "type": "Candlestick",
                "data": [
                    {"time": trade_date, "open": 10, "high": 11, "low": 9, "close": 10.5}
                    for trade_date in dates
                ],
            }
        ],
    }


def test_index_chart_payload_uses_lightweight_chart_shape():
    payload = index_chart_payload(FakeParquetStore(_prices()), "000300")

    assert payload[0]["series"]
    assert payload[0]["chart"]["height"] == 520


def test_index_chart_payload_keeps_full_history_for_zooming():
    payload = index_chart_payload(FakeParquetStore(_prices(periods=620)), "000300")

    candle = next(series for series in payload[0]["series"] if series["type"] == "Candlestick")
    assert len(candle["data"]) == 620


def test_etf_chart_payload_keeps_full_history_for_zooming():
    payload = etf_chart_payload(FakeParquetStore(_prices(periods=620)), "510300")

    candle = next(series for series in payload[0]["series"] if series["type"] == "Candlestick")
    assert len(candle["data"]) == 620


def test_etf_chart_payload_returns_empty_chart_for_missing_history():
    payload = etf_chart_payload(FakeParquetStore(pd.DataFrame()), "510300")

    assert payload[0]["series"] == []
