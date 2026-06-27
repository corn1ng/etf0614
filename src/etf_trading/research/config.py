"""Configuration loading for research experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from etf_trading.research.models import StrategyCandidate


def load_research_candidates(path: str | Path) -> list[StrategyCandidate]:
    """Load strategy candidates from a YAML research config."""

    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("research config field 'candidates' must be a list")
    return [_candidate_from_mapping(item) for item in candidates]


def _candidate_from_mapping(item: Any) -> StrategyCandidate:
    if not isinstance(item, dict):
        raise ValueError("each research candidate must be a mapping")
    values = dict(item)
    if "name" not in values:
        raise ValueError("each research candidate must include a name")
    if "momentum_windows" in values:
        values["momentum_windows"] = tuple(int(window) for window in values["momentum_windows"])
    if "skip_momentum_windows" in values:
        values["skip_momentum_windows"] = tuple(int(window) for window in values["skip_momentum_windows"])
    if "required_ma_relations" in values:
        values["required_ma_relations"] = _parse_required_ma_relations(values["required_ma_relations"])
    return StrategyCandidate(**values)


def _parse_required_ma_relations(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("required_ma_relations must be a list of two-item pairs")

    relations: list[tuple[str, str]] = []
    for relation in value:
        if not isinstance(relation, (list, tuple)) or len(relation) != 2:
            raise ValueError("required_ma_relations must contain only two-item pairs")
        left, right = relation
        relations.append((str(left), str(right)))
    return tuple(relations)
