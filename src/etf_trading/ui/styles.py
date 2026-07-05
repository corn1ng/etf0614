"""CSS helpers for the Streamlit workbench."""

from __future__ import annotations

import streamlit as st


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.55rem;
            padding-bottom: 1rem;
        }
        [data-testid=\"stSidebar\"] {
            width: 11.5rem !important;
            min-width: 11.5rem !important;
            max-width: 11.5rem !important;
        }
        [data-testid=\"stSidebar\"] > div:first-child {
            width: 11.5rem !important;
            min-width: 11.5rem !important;
            max-width: 11.5rem !important;
        }
        [data-testid=\"stSidebarContent\"] {
            padding: 0.55rem 0.5rem;
        }
        [data-testid=\"stSidebar\"] h3 {
            font-size: 0.98rem;
            line-height: 1.2;
            margin: 0.15rem 0 0.5rem 0;
        }
        [data-testid=\"stSidebar\"] .stRadio {
            margin-top: 0.1rem;
        }
        [data-testid=\"stSidebar\"] .stRadio [role=\"radiogroup\"] {
            gap: 0.18rem;
        }
        [data-testid=\"stSidebar\"] .stRadio label {
            min-height: 1.75rem;
            padding: 0.14rem 0.2rem;
        }
        [data-testid=\"stMetricLabel\"] p {
            white-space: normal;
            overflow: visible;
            text-overflow: clip;
            line-height: 1.25;
        }
        [data-testid=\"stVerticalBlock\"] {
            gap: 0.45rem;
        }
        [data-testid=\"stAlert\"] {
            padding: 0.55rem 0.7rem;
        }
        div[data-testid=\"stCaptionContainer\"] {
            margin-bottom: 0.15rem;
        }
        h1, h2, h3 {
            margin-top: 0.25rem;
            margin-bottom: 0.35rem;
        }
        .workbench-topbar {
            display: grid;
            grid-template-columns: minmax(220px, 1.6fr) repeat(5, minmax(120px, 1fr));
            gap: 1px;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            background: #e5e7eb;
            margin: 0 0 0.45rem 0;
        }
        .workbench-topbar__item {
            background: #ffffff;
            padding: 0.48rem 0.65rem;
            min-width: 0;
        }
        .workbench-topbar__label {
            color: #6b7280;
            font-size: 0.78rem;
            line-height: 1.2;
        }
        .workbench-topbar__value {
            color: #111827;
            font-size: 0.98rem;
            font-weight: 650;
            line-height: 1.25;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .workbench-page-header {
            margin: 0 0 0.35rem 0;
        }
        .workbench-page-header__title {
            color: #111827;
            font-size: 1.35rem;
            font-weight: 720;
            line-height: 1.15;
            margin: 0;
        }
        .workbench-page-header__caption {
            color: #6b7280;
            font-size: 0.86rem;
            line-height: 1.25;
            margin-top: 0.12rem;
        }
        .index-status-code {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 1px;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            margin: 0.2rem 0 0.45rem 0;
            background: #e5e7eb;
        }
        .index-status-code__item {
            background: #ffffff;
            padding: 0.52rem 0.65rem;
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
