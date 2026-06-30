"""TradingView Lightweight Charts payload adapter."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


MA_COLORS = {
    "ma51": "#eab308",
    "ma120": "#2563eb",
    "ma250": "#16a34a",
    "ma850": "#9333ea",
}
DEFAULT_MA_COLUMNS = tuple(MA_COLORS)


def build_lightweight_chart_payload(
    prices: pd.DataFrame,
    trades: Sequence[object] | None = None,
    ma_columns: Sequence[str] | None = None,
    chart_type: str = "candlestick",
) -> list[dict]:
    frame = prices.copy()
    if frame.empty:
        return [{"chart": _chart_options(), "series": []}]
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date")

    candle_data = [
        {
            "time": _time(row.trade_date),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        }
        for row in frame.itertuples(index=False)
    ]
    volume_data = [
        {
            "time": _time(row.trade_date),
            "value": float(getattr(row, "volume", 0) or 0),
            "color": "rgba(22, 163, 74, 0.45)" if row.close >= row.open else "rgba(220, 38, 38, 0.45)",
        }
        for row in frame.itertuples(index=False)
    ]
    trade_markers = _trade_markers(trades or [])

    line_series = []
    for column in _selected_ma_columns(ma_columns):
        color = MA_COLORS[column]
        if column not in frame.columns:
            continue
        data = [
            {"time": _time(row.trade_date), "value": float(getattr(row, column))}
            for row in frame.itertuples(index=False)
            if pd.notna(getattr(row, column))
        ]
        line_series.append(
            {
                "type": "Line",
                "data": data,
                "options": {"title": column.upper().replace("MA", "MA"), "color": color, "lineWidth": 1},
            }
        )
    if chart_type == "line":
        price_series = {
            "type": "Line",
            "data": [
                {"time": _time(row.trade_date), "value": float(row.close)}
                for row in frame.itertuples(index=False)
                if pd.notna(row.close)
            ],
            "options": {"title": "收盘价 Close", "color": "#111827", "lineWidth": 2},
            "markers": trade_markers,
        }
    elif chart_type == "candlestick":
        price_series = {
            "type": "Candlestick",
            "data": candle_data,
            "options": {
                "upColor": "#16a34a",
                "downColor": "#dc2626",
                "borderVisible": False,
                "wickUpColor": "#16a34a",
                "wickDownColor": "#dc2626",
            },
            "markers": trade_markers,
        }
    else:
        raise ValueError(f"unsupported chart_type: {chart_type}")

    main = {
        "chart": _chart_options(height=520),
        "series": ([price_series] + line_series) if chart_type == "line" else (line_series + [price_series]),
    }
    volume = {
        "chart": _chart_options(height=160),
        "series": [{"type": "Histogram", "data": volume_data, "options": {"priceFormat": {"type": "volume"}}}],
    }
    return [main, volume]


def _chart_options(height: int = 520) -> dict:
    return {
        "height": height,
        "layout": {"background": {"type": "solid", "color": "#ffffff"}, "textColor": "#111827"},
        "grid": {"vertLines": {"color": "#e5e7eb"}, "horzLines": {"color": "#e5e7eb"}},
        "rightPriceScale": {"borderVisible": False},
        "timeScale": {"borderVisible": False, "timeVisible": True},
        "crosshair": {"mode": 1},
        "handleScale": {"axisPressedMouseMove": True, "mouseWheel": True, "pinch": True},
        "handleScroll": {"mouseWheel": True, "pressedMouseMove": True, "horzTouchDrag": True, "vertTouchDrag": False},
    }


def _time(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _selected_ma_columns(ma_columns: Sequence[str] | None) -> list[str]:
    if ma_columns is None:
        return list(DEFAULT_MA_COLUMNS)
    selected = []
    for column in ma_columns:
        normalized = str(column).lower()
        if normalized in MA_COLORS and normalized not in selected:
            selected.append(normalized)
    return selected


def _trade_markers(trades: Sequence[object]) -> list[dict]:
    markers = []
    for trade in trades:
        action = str(_trade_value(trade, "action", "")).upper()
        if action not in {"BUY", "SELL", "REDUCE"}:
            continue
        weight_before = _safe_float(_trade_value(trade, "weight_before", 0.0))
        weight_after = _safe_float(_trade_value(trade, "weight_after", 0.0))
        price = _safe_float(_trade_value(trade, "price", 0.0))
        is_buy = action == "BUY"
        marker_text = _trade_value(trade, "marker_text", "")
        markers.append(
            {
                "time": _time(_trade_value(trade, "trade_date", None)),
                "position": "belowBar" if is_buy else "aboveBar",
                "color": "#16a34a" if is_buy else "#dc2626",
                "shape": "arrowUp" if is_buy else "arrowDown",
                "text": str(marker_text) if marker_text else f"{action} {_format_weight(weight_before)} -> {_format_weight(weight_after)} @ {price:.2f}",
            }
        )
    return sorted(markers, key=lambda marker: marker["time"])


def _trade_value(trade: object, key: str, default: object) -> object:
    if isinstance(trade, dict):
        return trade.get(key, default)
    return getattr(trade, key, default)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_weight(value: float) -> str:
    percent = value * 100
    if abs(percent - round(percent)) < 0.05:
        return f"{round(percent):.0f}%"
    return f"{percent:.1f}%"
