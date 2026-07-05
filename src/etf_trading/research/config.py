"""Configuration loading for research experiments."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from collections.abc import Sequence

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


def append_research_candidate(path: str | Path, candidate: StrategyCandidate) -> None:
    """Append a parameterized strategy candidate to a YAML research config."""

    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("research config root must be a mapping")

    candidates = data.setdefault("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("research config field 'candidates' must be a list")
    existing_names = {str(item.get("name")) for item in candidates if isinstance(item, dict) and item.get("name")}
    if candidate.name in existing_names:
        raise ValueError(f"duplicate strategy name: {candidate.name}")

    candidates.append(_candidate_to_mapping(candidate))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def adopted_candidates(candidates: Sequence[StrategyCandidate]) -> list[StrategyCandidate]:
    return [candidate for candidate in candidates if candidate.status == "adopted"]


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


def _candidate_to_mapping(candidate: StrategyCandidate) -> dict[str, Any]:
    raw = asdict(candidate)
    result: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, tuple):
            result[key] = _tuple_to_list(value)
        else:
            result[key] = value
    return result


def _tuple_to_list(value: tuple[Any, ...]) -> list[Any]:
    converted: list[Any] = []
    for item in value:
        if isinstance(item, tuple):
            converted.append(_tuple_to_list(item))
        else:
            converted.append(item)
    return converted
