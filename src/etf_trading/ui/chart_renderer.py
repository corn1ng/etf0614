"""TradingView Lightweight Charts payload adapter."""

from __future__ import annotations

import pandas as pd


MA_COLORS = {
    "ma51": "#eab308",
    "ma120": "#2563eb",
    "ma250": "#16a34a",
    "ma850": "#9333ea",
}


def build_lightweight_chart_payload(prices: pd.DataFrame) -> list[dict]:
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

    line_series = []
    for column, color in MA_COLORS.items():
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

    main = {
        "chart": _chart_options(height=520),
        "series": line_series
        + [
            {
                "type": "Candlestick",
                "data": candle_data,
                "options": {
                    "upColor": "#16a34a",
                    "downColor": "#dc2626",
                    "borderVisible": False,
                    "wickUpColor": "#16a34a",
                    "wickDownColor": "#dc2626",
                },
            }
        ],
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
    }


def _time(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")
