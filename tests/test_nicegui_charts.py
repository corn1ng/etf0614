import pandas as pd

from etf_trading.nicegui_app.components.charts import build_chart_html, build_static_chart_html
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


class FakeParquetStore:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def read_index_prices(self, index_code: str) -> pd.DataFrame:
        return self.frame

    def read_prices(self, etf_code: str) -> pd.DataFrame:
        return self.frame


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=260, freq="B"),
            "open": [10.0] * 260,
            "high": [10.5] * 260,
            "low": [9.8] * 260,
            "close": [10.2] * 260,
            "volume": [1000] * 260,
        }
    )


def test_index_chart_payload_uses_lightweight_chart_shape():
    payload = index_chart_payload(FakeParquetStore(_prices()), "000300")

    assert payload[0]["series"]
    assert payload[0]["chart"]["height"] == 520


def test_etf_chart_payload_returns_empty_chart_for_missing_history():
    payload = etf_chart_payload(FakeParquetStore(pd.DataFrame()), "510300")

    assert payload[0]["series"] == []
