from etf_trading.nicegui_app.components.charts import build_chart_html


def test_build_chart_html_embeds_payload_and_container():
    html = build_chart_html([{"chart": {"height": 320}, "series": []}], element_id="chart-a")

    assert 'id="chart-a"' in html
    assert "LightweightCharts" in html
    assert '"height": 320' in html
    assert "ResizeObserver" in html
