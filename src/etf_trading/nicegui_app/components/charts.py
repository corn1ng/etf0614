"""Lightweight Charts rendering helpers for NiceGUI."""

from __future__ import annotations

from html import escape
import json
import math

from nicegui import ui


DEFAULT_VISIBLE_CANDLES = 500


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
    options = build_echart_options(payload)
    height = _echart_height(payload)
    ui.echart(options).classes("workbench-echart-panel w-full").style(f"height: {height}px")


def chart_record_label(payload: list[dict]) -> str:
    count = _chart_record_count(payload)
    if count <= 0:
        return "暂无记录"
    if count > DEFAULT_VISIBLE_CANDLES:
        return f"共{count}条记录 · 默认显示近{DEFAULT_VISIBLE_CANDLES}条"
    return f"共{count}条记录"


def build_echart_options(payload: list[dict]) -> dict:
    main = payload[0] if payload else {"series": []}
    volume_panel = payload[1] if len(payload) > 1 else {"series": []}
    main_series = main.get("series", [])
    volume_series = volume_panel.get("series", [])
    candle = _first_series(main_series, "Candlestick")
    categories = [str(point.get("time", "")) for point in candle.get("data", [])] if candle else []
    series: list[dict] = []

    if candle:
        candle_data = [
            [point.get("open"), point.get("close"), point.get("low"), point.get("high")]
            for point in candle.get("data", [])
        ]
        series.append(
            {
                "name": "K线",
                "type": "candlestick",
                "data": candle_data,
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "itemStyle": {
                    "color": "#dc2626",
                    "color0": "#16a34a",
                    "borderColor": "#dc2626",
                    "borderColor0": "#16a34a",
                },
                "markPoint": _marker_points(candle),
            }
        )

    for item in main_series:
        if item.get("type") != "Line":
            continue
        options = item.get("options", {})
        series.append(
            {
                "name": str(options.get("title") or "均线"),
                "type": "line",
                "data": [point.get("value") for point in item.get("data", [])],
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "showSymbol": False,
                "smooth": True,
                "lineStyle": {"width": options.get("lineWidth", 1), "color": options.get("color", "#2563eb")},
            }
        )

    histogram = _first_series(volume_series, "Histogram")
    if histogram:
        if not categories:
            categories = [str(point.get("time", "")) for point in histogram.get("data", [])]
        series.append(
            {
                "name": "成交量",
                "type": "bar",
                "data": [
                    {
                        "value": point.get("value"),
                        "itemStyle": {"color": point.get("color", "#94a3b8")},
                    }
                    for point in histogram.get("data", [])
                ],
                "xAxisIndex": 1,
                "yAxisIndex": 1,
            }
        )

    zoom_window = _default_zoom_window(categories)
    return {
        "animation": False,
        "backgroundColor": "#ffffff",
        "legend": {
            "top": 8,
            "left": 12,
            "itemWidth": 12,
            "itemHeight": 8,
            "textStyle": {"color": "#475569", "fontSize": 11},
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "cross"},
            "confine": True,
        },
        "axisPointer": {"link": [{"xAxisIndex": "all"}]},
        "grid": [
            {"left": 56, "right": 56, "top": 42, "height": "66%"},
            {"left": 56, "right": 56, "top": "78%", "height": "13%"},
        ],
        "xAxis": [
            {
                "type": "category",
                "data": categories,
                "boundaryGap": True,
                "axisLine": {"lineStyle": {"color": "#cbd5e1"}},
                "axisLabel": {"color": "#64748b", "fontSize": 11},
                "min": "dataMin",
                "max": "dataMax",
            },
            {
                "type": "category",
                "data": categories,
                "gridIndex": 1,
                "boundaryGap": True,
                "axisLine": {"lineStyle": {"color": "#cbd5e1"}},
                "axisLabel": {"show": False},
                "min": "dataMin",
                "max": "dataMax",
            },
        ],
        "yAxis": [
            {
                "scale": True,
                "splitArea": {"show": True},
                "splitLine": {"lineStyle": {"color": "#e5e7eb"}},
                "axisLabel": {"color": "#64748b", "fontSize": 11},
            },
            {
                "scale": True,
                "gridIndex": 1,
                "splitNumber": 2,
                "axisLabel": {"color": "#64748b", "fontSize": 10},
                "splitLine": {"lineStyle": {"color": "#eef2f7"}},
            },
        ],
        "dataZoom": [
            {"type": "inside", "xAxisIndex": [0, 1], **zoom_window},
            {"type": "slider", "xAxisIndex": [0, 1], "bottom": 8, "height": 24, **zoom_window},
        ],
        "series": series,
    }


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


def _echart_height(payload: list[dict]) -> int:
    if not payload:
        return 520
    total = 0
    for item in payload[:2]:
        total += int(item.get("chart", {}).get("height", 0) or 0)
    return max(520, min(760, total or 680))


def _chart_record_count(payload: list[dict]) -> int:
    main = payload[0] if payload else {"series": []}
    candle = _first_series(main.get("series", []), "Candlestick")
    if candle:
        return len(candle.get("data", []))
    line = _first_series(main.get("series", []), "Line")
    if line:
        return len(line.get("data", []))
    return 0


def _default_zoom_window(categories: list[str]) -> dict:
    if len(categories) > DEFAULT_VISIBLE_CANDLES:
        return {"startValue": categories[-DEFAULT_VISIBLE_CANDLES], "endValue": categories[-1]}
    return {"start": 0, "end": 100}


def _marker_points(candle: dict) -> dict:
    markers = candle.get("markers") or []
    candles_by_time = {str(point.get("time")): point for point in candle.get("data", [])}
    data = []
    for marker in markers:
        time = marker.get("time")
        if not time:
            continue
        candle_point = candles_by_time.get(str(time))
        if not candle_point:
            continue
        position = str(marker.get("position", "aboveBar"))
        price = candle_point.get("low") if position == "belowBar" else candle_point.get("high")
        data.append(
            {
                "name": str(marker.get("text", "")),
                "coord": [str(time), price],
                "value": str(marker.get("text", "")),
                "itemStyle": {"color": marker.get("color", "#2563eb")},
                "label": {"formatter": str(marker.get("text", "")), "color": marker.get("color", "#2563eb")},
            }
        )
    return {"symbolSize": 42, "data": data} if data else {"data": []}


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
