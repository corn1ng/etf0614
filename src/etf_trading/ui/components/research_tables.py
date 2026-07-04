"""Research table and chart components."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st


def research_column_config(
    frame: pd.DataFrame,
    *,
    compact_header_labels: dict[str, str],
    percent_labels: set[str],
    count_labels: set[str],
) -> dict[str, object]:
    config: dict[str, object] = {}
    for column in frame.columns:
        label = compact_header_labels.get(column, column)
        if column == "ETF浠ｇ爜 ETF Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "ETF鍚嶇О ETF Name":
            config[column] = st.column_config.TextColumn(label, width=160)
        elif column == "鎸囨暟浠ｇ爜 Index Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "鎸囨暟鍚嶇О Index Name":
            config[column] = st.column_config.TextColumn(label, width=150)
        elif column in {"澶ц秼鍔?Large Trend", "涓秼鍔?Medium Trend", "灏忚秼鍔?Small Trend"}:
            config[column] = st.column_config.TextColumn(label, width=132)
        elif column == "鍙紑浠?Eligible":
            config[column] = st.column_config.TextColumn(label, width=118)
        elif column in percent_labels:
            config[column] = st.column_config.NumberColumn(label, format="%.1f%%", width=112)
        elif column in count_labels:
            config[column] = st.column_config.NumberColumn(label, format="%.0f", width=82)
        elif pd.api.types.is_numeric_dtype(frame[column]):
            config[column] = st.column_config.NumberColumn(label, format="%.2f", width=88)
        elif column in {"鍊欓€夌瓥鐣?Strategy", "鍩哄噯绛栫暐 Base Strategy"}:
            config[column] = st.column_config.TextColumn(label, width=260)
        elif column == "鍒嗙被 Category":
            config[column] = st.column_config.TextColumn(label, width=88)
        else:
            config[column] = st.column_config.TextColumn(label, width=90)
    return config


def render_research_table(
    frame: pd.DataFrame,
    *,
    column_config: dict[str, object],
    height: int | None = None,
) -> None:
    st.dataframe(
        frame,
        width="stretch",
        height=height or "auto",
        hide_index=True,
        column_config=column_config,
        row_height=34,
    )


def research_bar_chart(
    frame: pd.DataFrame,
    index_column: str,
    value_column: str,
    *,
    title: str,
    color: str,
    percent_columns: set[str],
    column_labels: dict[str, str],
    candidate_display_name,
    height_per_row: int = 34,
) -> alt.Chart:
    if index_column not in frame.columns or value_column not in frame.columns:
        return alt.Chart(pd.DataFrame({"绛栫暐 Strategy": [], "鏁板€?Value": []})).mark_bar()

    data = frame[[index_column, value_column]].dropna().copy()
    if index_column in {"candidate_name", "base_candidate"}:
        data[index_column] = data[index_column].map(candidate_display_name)
    data = data.rename(columns={index_column: "绛栫暐 Strategy", value_column: "鏁板€?Value"})
    if value_column in percent_columns:
        data["鏁板€?Value"] = data["鏁板€?Value"] * 100
        value_format = ".1f"
        axis_title = f"{column_labels.get(value_column, value_column)} (%)"
        tooltip_title = axis_title
    else:
        value_format = ".3f"
        axis_title = column_labels.get(value_column, value_column)
        tooltip_title = axis_title

    data = data.sort_values("鏁板€?Value", ascending=False)
    chart_height = max(180, min(360, len(data) * height_per_row))
    return (
        alt.Chart(data)
        .mark_bar(color=color, cornerRadiusEnd=3)
        .encode(
            x=alt.X("鏁板€?Value:Q", title=axis_title, axis=alt.Axis(format=value_format)),
            y=alt.Y(
                "绛栫暐 Strategy:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=260),
            ),
            tooltip=[
                alt.Tooltip("绛栫暐 Strategy:N", title="绛栫暐 Strategy"),
                alt.Tooltip("鏁板€?Value:Q", title=tooltip_title, format=value_format),
            ],
        )
        .properties(title=title, height=chart_height)
    )
