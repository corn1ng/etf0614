"""Chart control components shared by ETF and index pages."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st


def filter_date_range_frame(frame: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    """Return a copy of rows whose trade dates fall within the inclusive window."""
    if frame.empty or "trade_date" not in frame.columns:
        return frame

    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return prepared[(prepared["trade_date"] >= start) & (prepared["trade_date"] <= end)].reset_index(drop=True)


def chart_display_controls(
    key_prefix: str,
    *,
    chart_type_options: dict[str, str],
    price_scale_options: dict[str, str],
    ma_display_options: dict[str, str],
    default_chart_label: str,
    default_ma_labels: list[str],
    default_price_scale_label: str,
    price_scale_help: dict[str, str] | None = None,
) -> tuple[str, str, list[str]]:
    """Render chart display controls and return the selected renderer options."""
    chart_type_label = "\u56fe\u8868\u7c7b\u578b Chart Type"
    price_scale_label_text = "\u663e\u793a\u53e3\u5f84 View"
    moving_average_label = "\u5747\u7ebf\u663e\u793a Moving Averages"
    control_cols = st.columns([1, 1, 2])
    chart_label = control_cols[0].radio(
        chart_type_label,
        list(chart_type_options),
        index=list(chart_type_options).index(default_chart_label),
        horizontal=True,
        key=f"{key_prefix}_chart_type",
    )
    price_scale_label = control_cols[1].radio(
        price_scale_label_text,
        list(price_scale_options),
        index=list(price_scale_options).index(default_price_scale_label),
        horizontal=True,
        key=f"{key_prefix}_price_scale",
    )
    if price_scale_help and price_scale_label in price_scale_help:
        control_cols[1].caption(price_scale_help[price_scale_label])
    selected_ma_labels = control_cols[2].multiselect(
        moving_average_label,
        list(ma_display_options),
        default=default_ma_labels,
        key=f"{key_prefix}_ma_columns",
    )
    return (
        chart_type_options[chart_label],
        price_scale_options[price_scale_label],
        [ma_display_options[label] for label in selected_ma_labels],
    )


def chart_range_controls(
    frame: pd.DataFrame,
    key_prefix: str,
    *,
    range_presets: dict[str, int | str | None],
    default_label: str,
) -> pd.DataFrame:
    """Render chart date-range controls and return the filtered frame."""
    chart_range_label = "\u56fe\u8868\u533a\u95f4"
    start_date_label = "\u5f00\u59cb\u65e5\u671f"
    end_date_label = "\u7ed3\u675f\u65e5\u671f"
    invalid_range_warning = "\u5f00\u59cb\u65e5\u671f\u665a\u4e8e\u7ed3\u675f\u65e5\u671f\uff0c\u5df2\u4e34\u65f6\u6309\u5b8c\u6574\u533a\u95f4\u663e\u793a\u3002"
    if frame.empty or "trade_date" not in frame.columns:
        return frame

    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    min_date = pd.Timestamp(prepared["trade_date"].min()).date()
    max_date = pd.Timestamp(prepared["trade_date"].max()).date()
    labels = list(range_presets)
    fallback_label = next((label for label, preset in range_presets.items() if preset == 730), labels[0])
    default_index = labels.index(default_label) if default_label in labels else labels.index(fallback_label)
    range_label = st.radio(
        chart_range_label,
        labels,
        index=default_index,
        horizontal=True,
        key=f"{key_prefix}_range_preset",
    )
    preset = range_presets[range_label]
    if preset == "custom":
        cols = st.columns(2)
        start_date = cols[0].date_input(
            start_date_label,
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            key=f"{key_prefix}_range_start",
        )
        end_date = cols[1].date_input(
            end_date_label,
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            key=f"{key_prefix}_range_end",
        )
        if start_date > end_date:
            st.warning(invalid_range_warning)
            return prepared
        return filter_date_range_frame(prepared, start_date, end_date)
    if preset is None:
        return prepared

    start_date = max(min_date, max_date - timedelta(days=int(preset)))
    return filter_date_range_frame(prepared, start_date, max_date)
