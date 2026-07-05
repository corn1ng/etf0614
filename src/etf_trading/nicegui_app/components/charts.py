"""Lightweight Charts rendering helpers for NiceGUI."""

from __future__ import annotations

from html import escape
import json

from nicegui import ui


def build_chart_html(payload: list[dict], element_id: str = "workbench-chart") -> str:
    safe_id = escape(element_id, quote=True)
    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""
<div id="{safe_id}" class="workbench-chart-panel"></div>
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
<script>
(() => {{
  const root = document.getElementById("{safe_id}");
  const payload = {payload_json};
  root.innerHTML = "";
  payload.forEach((item, index) => {{
    const chartNode = document.createElement("div");
    chartNode.style.height = `${{item.chart?.height || 320}}px`;
    chartNode.style.width = "100%";
    chartNode.dataset.chartIndex = index;
    root.appendChild(chartNode);
    const chart = LightweightCharts.createChart(chartNode, {{...item.chart, width: root.clientWidth}});
    (item.series || []).forEach((series) => {{
      const type = series.type || "Line";
      const factory = type === "Candlestick" ? chart.addCandlestickSeries :
        type === "Histogram" ? chart.addHistogramSeries : chart.addLineSeries;
      const created = factory.call(chart, series.options || {{}});
      created.setData(series.data || []);
      if (series.markers && created.setMarkers) created.setMarkers(series.markers);
    }});
    new ResizeObserver(() => chart.applyOptions({{width: root.clientWidth}})).observe(root);
  }});
}})();
</script>
"""


def render_lightweight_chart(payload: list[dict], element_id: str = "workbench-chart") -> None:
    ui.html(build_chart_html(payload, element_id=element_id)).classes("w-full")
