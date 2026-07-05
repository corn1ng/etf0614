"""Dense table helpers."""

from __future__ import annotations


def table_columns(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    if not rows:
        return []
    return [{"name": key, "label": key, "field": key, "align": "left"} for key in rows[0].keys()]
