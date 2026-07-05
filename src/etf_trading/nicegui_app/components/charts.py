"""Lightweight Charts rendering helpers for NiceGUI."""

from __future__ import annotations

from html import escape
import json
import math

from nicegui import ui


def build_chart_html(payload: list[dict], element_id: str = "workbench-chart") -> str:
    safe_id = escape(element_id, quote=True)
    return f'<div id="{safe_id}" class="workbench-chart-panel"></div>\n{_build_chart_script(payload, safe_id)}'


def _build_chart_script(payload: list[dict], safe_id: str) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""
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
    ui.html(build_static_chart_html(payload, element_id=element_id)).classes("w-full")


def build_static_chart_html(payload: list[dict], element_id: str = "workbench-chart") -> str:
    safe_id = escape(element_id, quote=True)
    item = payload[0] if payload else {"chart": {"height": 420}, "series": []}
    height = int(item.get("chart", {}).get("height", 420) or 420)
    series = item.get("series", [])
    candle = _first_series(series, "Candlestick")
    line = _first_series(series, "Line")
    if candle:
        svg = _candlestick_svg(candle.get("data", []), height=height)
    elif line:
        svg = _line_svg(line.get("data", []), height=height)
    else:
        svg = _empty_svg(height=height)
    return f'<div id="{safe_id}" class="workbench-chart-panel">{svg}</div>'


def _first_series(series: list[dict], kind: str) -> dict | None:
    for item in series:
        if item.get("type") == kind:
            return item
    return None


def _candlestick_svg(data: list[dict], height: int) -> str:
    points = _sample(data)
    if not points:
        return _empty_svg(height)

    width = 1000
    pad_x = 24
    pad_y = 20
    chart_h = max(120, height - pad_y * 2)
    values = [float(point[key]) for point in points for key in ("open", "high", "low", "close") if _is_number(point.get(key))]
    low = min(values)
    high = max(values)
    if math.isclose(high, low):
        high += 1
        low -= 1

    def y(value: object) -> float:
        numeric = float(value)
        return pad_y + (high - numeric) / (high - low) * chart_h

    step = (width - pad_x * 2) / max(1, len(points))
    body_w = max(2.0, min(8.0, step * 0.58))
    shapes = []
    for idx, point in enumerate(points):
        x = pad_x + step * idx + step / 2
        open_y = y(point["open"])
        close_y = y(point["close"])
        high_y = y(point["high"])
        low_y = y(point["low"])
        up = float(point["close"]) >= float(point["open"])
        color = "#dc2626" if up else "#16a34a"
        top = min(open_y, close_y)
        body_h = max(1.5, abs(close_y - open_y))
        shapes.append(f'<line x1="{x:.2f}" y1="{high_y:.2f}" x2="{x:.2f}" y2="{low_y:.2f}" stroke="{color}" stroke-width="1.2" />')
        shapes.append(
            f'<rect x="{x - body_w / 2:.2f}" y="{top:.2f}" width="{body_w:.2f}" height="{body_h:.2f}" fill="{color}" rx="1" />'
        )

    grid = _grid(width, height, pad_y, chart_h)
    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" aria-label="K线图">{grid}{"".join(shapes)}</svg>'


def _line_svg(data: list[dict], height: int) -> str:
    points = _sample(data)
    if not points:
        return _empty_svg(height)

    width = 1000
    pad_x = 24
    pad_y = 20
    chart_h = max(120, height - pad_y * 2)
    values = [float(point["value"]) for point in points if _is_number(point.get("value"))]
    low = min(values)
    high = max(values)
    if math.isclose(high, low):
        high += 1
        low -= 1

    def y(value: object) -> float:
        return pad_y + (high - float(value)) / (high - low) * chart_h

    step = (width - pad_x * 2) / max(1, len(points) - 1)
    path = " ".join(f"{'M' if idx == 0 else 'L'} {pad_x + step * idx:.2f} {y(point['value']):.2f}" for idx, point in enumerate(points))
    grid = _grid(width, height, pad_y, chart_h)
    return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" aria-label="走势图">{grid}<path d="{path}" fill="none" stroke="#2563eb" stroke-width="2" /></svg>'


def _empty_svg(height: int) -> str:
    return (
        f'<svg viewBox="0 0 1000 {height}" width="100%" height="{height}" role="img" aria-label="暂无图表">'
        '<text x="500" y="210" text-anchor="middle" fill="#94a3b8" font-size="18">暂无历史行情</text>'
        "</svg>"
    )


def _grid(width: int, height: int, pad_y: int, chart_h: int) -> str:
    lines = []
    for i in range(5):
        y = pad_y + chart_h * i / 4
        lines.append(f'<line x1="24" y1="{y:.2f}" x2="{width - 24}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1" />')
    return "".join(lines)


def _sample(data: list[dict], max_points: int = 180) -> list[dict]:
    if len(data) <= max_points:
        return data
    step = math.ceil(len(data) / max_points)
    return data[::step]


def _is_number(value: object) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return not math.isnan(float(value))
