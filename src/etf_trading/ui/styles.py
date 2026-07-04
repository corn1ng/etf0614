"""CSS helpers for the Streamlit workbench."""

from __future__ import annotations

import streamlit as st


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.1rem;
        }
        [data-testid=\"stSidebar\"] {
            min-width: 15rem;
        }
        [data-testid=\"stMetricLabel\"] p {
            white-space: normal;
            overflow: visible;
            text-overflow: clip;
            line-height: 1.25;
        }
        .workbench-topbar {
            display: grid;
            grid-template-columns: minmax(220px, 1.6fr) repeat(5, minmax(120px, 1fr));
            gap: 1px;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            background: #e5e7eb;
            margin: 0 0 1rem 0;
        }
        .workbench-topbar__item {
            background: #ffffff;
            padding: 0.65rem 0.8rem;
            min-width: 0;
        }
        .workbench-topbar__label {
            color: #6b7280;
            font-size: 0.78rem;
            line-height: 1.2;
        }
        .workbench-topbar__value {
            color: #111827;
            font-size: 1.05rem;
            font-weight: 650;
            line-height: 1.25;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .index-status-code {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 1px;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            margin: 0.35rem 0 1rem 0;
            background: #e5e7eb;
        }
        .index-status-code__item {
            background: #ffffff;
            padding: 0.75rem 0.9rem;
            min-width: 0;
        }
        .index-status-code__label {
            color: #6b7280;
            font-size: 0.82rem;
            line-height: 1.2;
            margin-bottom: 0.35rem;
        }
        .index-status-code__value {
            color: #111827;
            font-size: 1.3rem;
            font-weight: 650;
            line-height: 1.2;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        @media (max-width: 900px) {
            .workbench-topbar {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .index-status-code {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
