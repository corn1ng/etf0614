"""Lightweight Charts rendering helpers for NiceGUI."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape
import json
import math

from nicegui import ui


DEFAULT_VISIBLE_CANDLES = 500
DEFAULT_CHART_RANGE_LABEL = "近2年"
CUSTOM_CHART_RANGE_LABEL = "自定义"
CHART_RANGE_PRESETS: dict[str, int | str | None] = {
    "近3月": 90,
    "近6月": 180,
    "近1年": 365,
    "近2年": 730,
    "全部": None,
    CUSTOM_CHART_RANGE_LABEL: "custom",
}


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


def render_lightweight_chart(
    payload: list[dict],
    element_id: str = "workbench-chart",
    *,
    visible_start: str | None = None,
    visible_end: str | None = None,
) -> None:
    options = build_echart_options(payload, visible_start=visible_start, visible_end=visible_end)
    height = _echart_height(payload)
    ui.echart(options).classes("workbench-echart-panel w-full").style(f"height: {height}px")


def render_ranged_lightweight_chart(
    payload: list[dict],
    *,
    element_id: str,
    title: str,
    default_range_label: str = DEFAULT_CHART_RANGE_LABEL,
) -> None:
    min_date, max_date = chart_date_bounds(payload)
    state = {
        "label": default_range_label if default_range_label in CHART_RANGE_PRESETS else DEFAULT_CHART_RANGE_LABEL,
        "start": min_date or "",
        "end": max_date or "",
    }

    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("workbench-toolbar w-full justify-between"):
            ui.label(title).classes("text-sm font-semibold text-slate-700")
            ui.toggle(
                list(CHART_RANGE_PRESETS),
                value=state["label"],
                on_change=lambda event: select_range(str(event.value)),
            ).props("dense unelevated no-caps").classes("workbench-range-toggle")
        custom_area = ui.row().classes("workbench-toolbar w-full justify-end")
        chart_area = ui.column().classes("w-full gap-2")

    def select_range(label: str) -> None:
        state["label"] = label
        if label == CUSTOM_CHART_RANGE_LABEL and min_date and max_date:
            state["start"] = state["start"] or min_date
            state["end"] = state["end"] or max_date
        render_custom_controls()
        render_chart()

    def update_start(value: object) -> None:
        state["start"] = str(value or "")
        render_chart()

    def update_end(value: object) -> None:
        state["end"] = str(value or "")
        render_chart()

    def render_custom_controls() -> None:
        custom_area.clear()
        if state["label"] != CUSTOM_CHART_RANGE_LABEL or not min_date or not max_date:
            return
        with custom_area:
            ui.input("开始日期", value=state["start"] or min_date, on_change=lambda event: update_start(event.value)).props(
                f"dense outlined type=date min={min_date} max={max_date}"
            ).classes("w-40")
            ui.input("结束日期", value=state["end"] or max_date, on_change=lambda event: update_end(event.value)).props(
                f"dense outlined type=date min={min_date} max={max_date}"
            ).classes("w-40")

    def render_chart() -> None:
        chart_area.clear()
        with chart_area:
            visible_start, visible_end = chart_range_window(
                payload,
                str(state["label"]),
                start_date=str(state["start"] or "") or None,
                end_date=str(state["end"] or "") or None,
            )
            if _is_invalid_custom_range(str(state["label"]), str(state["start"] or ""), str(state["end"] or "")):
                ui.label("开始日期晚于结束日期，已临时按完整区间显示。").classes("workbench-warning-line w-full")
            with ui.row().classes("workbench-toolbar w-full justify-end"):
                ui.label(
                    chart_record_label(
                        payload,
                        range_label=str(state["label"]),
                        visible_start=visible_start,
                        visible_end=visible_end,
                    )
                ).classes("text-xs text-slate-500")
            render_lightweight_chart(
                payload,
                element_id=element_id,
                visible_start=visible_start,
                visible_end=visible_end,
            )

    render_custom_controls()
    render_chart()


def chart_record_label(
    payload: list[dict],
    *,
    range_label: str | None = None,
    visible_start: str | None = None,
    visible_end: str | None = None,
) -> str:
    count = _chart_record_count(payload)
    if count <= 0:
        return "暂无记录"
    if range_label == "全部":
        return f"共{count}条记录 · 当前：全部"
    if range_label == CUSTOM_CHART_RANGE_LABEL and visible_start and visible_end:
        return f"共{count}条记录 · 当前：{visible_start} 至 {visible_end}"
    if range_label and range_label in CHART_RANGE_PRESETS:
        return f"共{count}条记录 · 当前：{range_label}"
    if count > DEFAULT_VISIBLE_CANDLES:
        return f"共{count}条记录 · 默认显示近{DEFAULT_VISIBLE_CANDLES}条"
    return f"共{count}条记录"


def build_echart_options(
    payload: list[dict],
    *,
    visible_start: str | None = None,
    visible_end: str | None = None,
) -> dict:
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

    zoom_window = _default_zoom_window(categories, visible_start=visible_start, visible_end=visible_end)
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
            "backgroundColor": "rgba(255, 255, 255, 0.98)",
            "borderColor": "#cbd5e1",
            "borderWidth": 1,
            "extraCssText": "border-radius: 6px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.14);",
            ":formatter": _tooltip_formatter(),
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


def chart_date_bounds(payload: list[dict]) -> tuple[str | None, str | None]:
    categories = _chart_categories(payload)
    if not categories:
        return None, None
    return categories[0], categories[-1]


def chart_range_window(
    payload: list[dict],
    range_label: str,
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> tuple[str | None, str | None]:
    categories = _chart_categories(payload)
    if not categories:
        return None, None
    preset = CHART_RANGE_PRESETS.get(range_label, CHART_RANGE_PRESETS[DEFAULT_CHART_RANGE_LABEL])
    if preset is None:
        return None, None
    if preset == "custom":
        start = _coerce_category_start(categories, start_date or categories[0])
        end = _coerce_category_end(categories, end_date or categories[-1])
        if start and end and start > end:
            return None, None
        return start, end

    max_date = _parse_date(categories[-1])
    min_date = _parse_date(categories[0])
    if max_date is None or min_date is None:
        return None, None
    threshold = max(min_date, max_date - timedelta(days=int(preset)))
    return _first_category_on_or_after(categories, threshold), categories[-1]


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


def _chart_categories(payload: list[dict]) -> list[str]:
    main = payload[0] if payload else {"series": []}
    candle = _first_series(main.get("series", []), "Candlestick")
    if candle:
        return [str(point.get("time", "")) for point in candle.get("data", []) if point.get("time")]
    line = _first_series(main.get("series", []), "Line")
    if line:
        return [str(point.get("time", "")) for point in line.get("data", []) if point.get("time")]
    return []


def _default_zoom_window(categories: list[str], *, visible_start: str | None = None, visible_end: str | None = None) -> dict:
    if visible_start or visible_end:
        start = _coerce_category_start(categories, visible_start or categories[0])
        end = _coerce_category_end(categories, visible_end or categories[-1])
        if start and end and start <= end:
            return {"startValue": start, "endValue": end}
        return {"start": 0, "end": 100}
    if len(categories) > DEFAULT_VISIBLE_CANDLES:
        return {"startValue": categories[-DEFAULT_VISIBLE_CANDLES], "endValue": categories[-1]}
    return {"start": 0, "end": 100}


def _first_category_on_or_after(categories: list[str], threshold: date) -> str:
    threshold_text = threshold.isoformat()
    return next((category for category in categories if category >= threshold_text), categories[-1])


def _coerce_category_start(categories: list[str], value: str | date | None) -> str | None:
    parsed = _parse_date(value)
    if parsed is None:
        return categories[0] if categories else None
    return _first_category_on_or_after(categories, parsed)


def _coerce_category_end(categories: list[str], value: str | date | None) -> str | None:
    parsed = _parse_date(value)
    if parsed is None:
        return categories[-1] if categories else None
    threshold_text = parsed.isoformat()
    return next((category for category in reversed(categories) if category <= threshold_text), categories[0])


def _parse_date(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _is_invalid_custom_range(range_label: str, start_date: str, end_date: str) -> bool:
    if range_label != CUSTOM_CHART_RANGE_LABEL:
        return False
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    return bool(start and end and start > end)


def _tooltip_formatter() -> str:
    return """
function (params) {
  const rows = Array.isArray(params) ? params : [params];
  if (!rows.length) return "";

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));

  const formatFixed = (value, digits = 2) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "--";
    return numeric.toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  };

  const formatVolume = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "--";
    const absolute = Math.abs(numeric);
    if (absolute >= 100000000) return `${formatFixed(numeric / 100000000, 2)}亿`;
    if (absolute >= 10000) return `${formatFixed(numeric / 10000, 2)}万`;
    return Math.round(numeric).toLocaleString("en-US");
  };

  const valueOf = (item) => {
    if (Array.isArray(item.value)) return item.value[0];
    if (item.value && typeof item.value === "object" && "value" in item.value) return item.value.value;
    return item.value;
  };

  const colorOf = (item) => {
    const color = Array.isArray(item.color) ? item.color[0] : item.color;
    return typeof color === "string" && color ? color : "#94a3b8";
  };

  const dot = (color) => `<span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block;flex:0 0 auto;"></span>`;
  const metricRow = (label, value, color) => `
    <div style="display:grid;grid-template-columns:72px minmax(104px,1fr);gap:12px;align-items:center;min-height:22px;">
      <span style="display:flex;align-items:center;gap:7px;min-width:0;color:#64748b;">${dot(color)}<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(label)}</span></span>
      <span style="text-align:right;color:#374151;font-weight:700;font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">${value}</span>
    </div>`;
  const section = (title, content) => content.length ? `
    <div style="padding-top:7px;margin-top:7px;border-top:1px solid #e5e7eb;">
      <div style="margin-bottom:3px;color:#334155;font-size:12px;font-weight:700;">${escapeHtml(title)}</div>
      ${content.join("")}
    </div>` : "";

  const axisLabel = rows[0].axisValueLabel || rows[0].name || "";
  const candle = rows.find((item) => item.seriesType === "candlestick");
  const candleValues = candle && Array.isArray(candle.value) ? candle.value : [];
  const candleOffset = candleValues.length >= 5 && typeof candleValues[0] === "string" ? 1 : 0;
  const candleRows = candle ? [
    metricRow("开盘", formatFixed(candleValues[candleOffset]), colorOf(candle)),
    metricRow("收盘", formatFixed(candleValues[candleOffset + 1]), colorOf(candle)),
    metricRow("最低", formatFixed(candleValues[candleOffset + 2]), colorOf(candle)),
    metricRow("最高", formatFixed(candleValues[candleOffset + 3]), colorOf(candle)),
  ] : [];

  const maRows = rows
    .filter((item) => item.seriesType === "line" && Number.isFinite(Number(valueOf(item))))
    .map((item) => metricRow(item.seriesName, formatFixed(valueOf(item)), colorOf(item)));

  const volume = rows.find((item) => item.seriesType === "bar");
  const volumeRows = volume ? [metricRow("成交量", formatVolume(valueOf(volume)), colorOf(volume))] : [];

  return `
    <div style="min-width:224px;color:#475569;font-size:13px;line-height:1.35;">
      <div style="color:#111827;font-weight:800;margin-bottom:2px;">${escapeHtml(axisLabel)}</div>
      ${section("K线", candleRows)}
      ${section("均线", maRows)}
      ${section("成交量", volumeRows)}
    </div>`;
}
"""


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
