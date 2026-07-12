"""TradingView Lightweight Charts payload adapter."""

from __future__ import annotations

from collections.abc import Sequence
import math

import pandas as pd


MA_COLORS = {
    "ma51": "#eab308",
    "ma120": "#2563eb",
    "ma250": "#16a34a",
    "ma850": "#9333ea",
}
DEFAULT_MA_COLUMNS = tuple(MA_COLORS)
UP_COLOR = "#dc2626"
DOWN_COLOR = "#16a34a"


def build_lightweight_chart_payload(
    prices: pd.DataFrame,
    trades: Sequence[object] | None = None,
    ma_columns: Sequence[str] | None = None,
    chart_type: str = "candlestick",
    price_scale_mode: str = "normal",
) -> list[dict]:
    frame = prices.copy()
    if frame.empty:
        return [{"chart": _chart_options(price_scale_mode=price_scale_mode), "series": []}]
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date")

    transformed_view = price_scale_mode in {"percent", "log_return", "drawdown", "downside"}
    base_close = _first_positive_value(frame["close"]) if price_scale_mode in {"percent", "log_return"} and "close" in frame.columns else None
    frame["chart_reference"] = _chart_reference(frame, price_scale_mode, base_close)

    candle_data = [
        {
            "time": _time(row.trade_date),
            "open": _chart_value(row.open, row.chart_reference, price_scale_mode),
            "high": _chart_value(row.high, row.chart_reference, price_scale_mode),
            "low": _chart_value(row.low, row.chart_reference, price_scale_mode),
            "close": _chart_value(row.close, row.chart_reference, price_scale_mode),
        }
        for row in frame.itertuples(index=False)
        if _chart_value(row.close, row.chart_reference, price_scale_mode) is not None
    ]
    volume_data = [
        {
            "time": _time(row.trade_date),
            "value": float(getattr(row, "volume", 0) or 0),
            "color": "rgba(220, 38, 38, 0.45)" if row.close >= row.open else "rgba(22, 163, 74, 0.45)",
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
            {"time": _time(row.trade_date), "value": _chart_value(getattr(row, column), row.chart_reference, price_scale_mode)}
            for row in frame.itertuples(index=False)
            if _chart_value(getattr(row, column), row.chart_reference, price_scale_mode) is not None
        ]
        line_series.append(
            {
                "type": "Line",
                "data": data,
                "options": {"title": column.upper().replace("MA", "MA"), "color": color, "lineWidth": 1},
            }
        )
    if chart_type == "line" or transformed_view:
        title = "价格走势 Price"
        if price_scale_mode == "percent":
            title = "累计涨跌幅 Return %"
        elif price_scale_mode == "log_return":
            title = "对数收益 Log Return %"
        elif price_scale_mode == "drawdown":
            title = "回撤风险 Drawdown %"
        elif price_scale_mode == "downside":
            title = "回到低点需跌幅 Down to Low %"
        price_series = {
            "type": "Line",
            "data": [
                {"time": _time(row.trade_date), "value": _chart_value(row.close, row.chart_reference, price_scale_mode)}
                for row in frame.itertuples(index=False)
                if _chart_value(row.close, row.chart_reference, price_scale_mode) is not None
            ],
            "options": {
                "title": title,
                "color": "#111827",
                "lineWidth": 2,
                "priceFormat": {"type": "price", "precision": 2, "minMove": 0.01},
            },
            "markers": trade_markers,
        }
    elif chart_type == "candlestick":
        price_series = {
            "type": "Candlestick",
            "data": candle_data,
            "options": {
                "upColor": UP_COLOR,
                "downColor": DOWN_COLOR,
                "borderVisible": False,
                "wickUpColor": UP_COLOR,
                "wickDownColor": DOWN_COLOR,
            },
            "markers": trade_markers,
        }
    else:
        raise ValueError(f"unsupported chart_type: {chart_type}")

    main = {
        "chart": _chart_options(height=520, price_scale_mode=price_scale_mode),
        "series": ([price_series] + line_series) if chart_type == "line" or transformed_view else (line_series + [price_series]),
    }
    volume = {
        "chart": _chart_options(height=160),
        "series": [{"type": "Histogram", "data": volume_data, "options": {"priceFormat": {"type": "volume"}}}],
    }
    return [main, volume]


def _chart_options(height: int = 520, price_scale_mode: str = "normal") -> dict:
    if price_scale_mode not in {"normal", "logarithmic", "log_return", "percent", "drawdown", "downside"}:
        raise ValueError(f"unsupported price_scale_mode: {price_scale_mode}")
    price_scale = {"borderVisible": False}
    if price_scale_mode == "logarithmic":
        price_scale["mode"] = 1
    return {
        "height": height,
        "layout": {"background": {"type": "solid", "color": "#ffffff"}, "textColor": "#111827"},
        "grid": {"vertLines": {"color": "#e5e7eb"}, "horzLines": {"color": "#e5e7eb"}},
        "localization": {"locale": "zh-CN", "dateFormat": "yyyy.MM.dd"},
        "rightPriceScale": price_scale,
        "timeScale": {"borderVisible": False, "timeVisible": False, "secondsVisible": False},
        "crosshair": {"mode": 1},
        "handleScale": {"axisPressedMouseMove": True, "mouseWheel": True, "pinch": True},
        "handleScroll": {"mouseWheel": True, "pressedMouseMove": True, "horzTouchDrag": True, "vertTouchDrag": False},
    }


def _time(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _first_positive_value(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    values = values[values > 0]
    if values.empty:
        return None
    return float(values.iloc[0])


def _chart_reference(frame: pd.DataFrame, price_scale_mode: str, base_close: float | None) -> pd.Series:
    if price_scale_mode in {"percent", "log_return"}:
        return pd.Series(base_close, index=frame.index)
    if price_scale_mode == "drawdown":
        close = pd.to_numeric(frame["close"], errors="coerce")
        return close.where(close > 0).cummax()
    if price_scale_mode == "downside":
        close = pd.to_numeric(frame["close"], errors="coerce")
        low = _first_positive_value(close.sort_values())
        return pd.Series(low, index=frame.index)
    return pd.Series(None, index=frame.index)


def _chart_value(value: object, reference: object, price_scale_mode: str) -> float | None:
    if pd.isna(value):
        return None
    numeric = float(value)
    if price_scale_mode not in {"percent", "log_return", "drawdown", "downside"}:
        return numeric
    if pd.isna(reference):
        return None
    reference_value = float(reference)
    if numeric <= 0:
        return None
    if reference_value <= 0:
        return None
    if price_scale_mode == "log_return":
        return round(math.log(numeric / reference_value) * 100.0, 4)
    if price_scale_mode == "downside":
        return round((reference_value / numeric - 1.0) * 100.0, 4)
    return round((numeric / reference_value - 1.0) * 100.0, 4)


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
