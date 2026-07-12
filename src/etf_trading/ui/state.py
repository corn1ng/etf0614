"""Shared UI state helpers for the Streamlit workbench."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class StatusSummary:
    data_health: str
    eligible_index_count: int
    eligible_category_count: int
    enabled_watchlist_count: int
    issue_count: int


def summarize_platform_status(status: Mapping[str, object]) -> StatusSummary:
    issues = status.get("issues", [])
    issue_count = len(issues) if isinstance(issues, list) else 0

    eligible_categories = status.get("eligible_categories", [])
    eligible_category_count = len(eligible_categories) if isinstance(eligible_categories, list) else 0

    enabled_watchlist = status.get("enabled_watchlist", pd.DataFrame())
    enabled_watchlist_count = len(enabled_watchlist) if isinstance(enabled_watchlist, pd.DataFrame) else 0

    return StatusSummary(
        data_health="已就绪" if issue_count == 0 else "需处理",
        eligible_index_count=int(status.get("eligible_index_count", 0) or 0),
        eligible_category_count=eligible_category_count,
        enabled_watchlist_count=enabled_watchlist_count,
        issue_count=issue_count,
    )
