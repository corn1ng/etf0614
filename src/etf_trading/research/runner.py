"""Reusable research runner utilities for CLI and Streamlit surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Mapping, Sequence

import pandas as pd

from etf_trading.data.storage import ParquetStore
from etf_trading.research.experiment import ResearchRunCancelled, StrategyExperimentRunner, rank_candidates
from etf_trading.research.models import StrategyCandidate


@dataclass(frozen=True)
class ResearchRunOutput:
    results: pd.DataFrame
    ranking: pd.DataFrame
    used_count: int
    skipped_count: int


def load_price_frames(
    parquet_root: str | Path,
    min_rows: int = 252,
    limit: int | None = None,
    etf_codes: Sequence[str] | None = None,
) -> tuple[dict[str, pd.DataFrame], int]:
    """Load local ETF price frames and skip histories that are too short."""

    root = Path(parquet_root)
    store = ParquetStore(root)
    price_dir = root / "prices"
    if not price_dir.exists():
        raise FileNotFoundError(f"price parquet directory not found: {price_dir}")

    frames: dict[str, pd.DataFrame] = {}
    skipped_count = 0
    paths = _price_paths(price_dir, etf_codes)
    for path in paths:
        if limit is not None and len(frames) >= limit:
            break
        if not path.exists():
            skipped_count += 1
            continue
        code = path.stem
        frame = store.read_prices(code)
        if len(frame) < min_rows:
            skipped_count += 1
            continue
        frames[code] = frame
    if not frames:
        raise ValueError(f"no ETF price parquet files with at least {min_rows} rows under {price_dir}")
    return frames, skipped_count


def _price_paths(price_dir: Path, etf_codes: Sequence[str] | None) -> list[Path]:
    if etf_codes is None:
        return sorted(price_dir.glob("*.parquet"))

    seen: set[str] = set()
    paths: list[Path] = []
    for raw_code in etf_codes:
        code = _normalize_etf_code(raw_code)
        if not code or code in seen:
            continue
        seen.add(code)
        paths.append(price_dir / f"{code}.parquet")
    return paths


def _normalize_etf_code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def attach_relative_strength_rank(price_frames: Mapping[str, pd.DataFrame], momentum_column: str = "momentum_60") -> dict[str, pd.DataFrame]:
    """Add daily cross-sectional relative-strength percentile rank to each ETF frame."""

    rows: list[pd.DataFrame] = []
    normalized_frames: dict[str, pd.DataFrame] = {}
    for code, frame in price_frames.items():
        data = frame.copy()
        data["etf_code"] = code
        data["trade_date"] = pd.to_datetime(data["trade_date"])
        data[momentum_column] = pd.to_numeric(data[momentum_column], errors="coerce")
        normalized_frames[code] = data
        rows.append(data[["etf_code", "trade_date", momentum_column]])

    combined = pd.concat(rows, ignore_index=True)
    combined["relative_strength_rank"] = combined.groupby("trade_date")[momentum_column].rank(ascending=False, pct=True)
    ranks = combined[["etf_code", "trade_date", "relative_strength_rank"]]

    ranked: dict[str, pd.DataFrame] = {}
    for code, frame in normalized_frames.items():
        ranked[code] = frame.merge(ranks[ranks["etf_code"] == code], on=["etf_code", "trade_date"], how="left")
    return ranked


def run_research(
    parquet_root: str | Path,
    candidates: Sequence[StrategyCandidate],
    categories: Mapping[str, str] | None = None,
    min_rows: int = 252,
    limit: int | None = None,
    use_relative_strength: bool = True,
    etf_codes: Sequence[str] | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> ResearchRunOutput:
    """Run configured candidates over local price data with optional RS ranking."""

    frames, skipped_count = load_price_frames(parquet_root, min_rows=min_rows, limit=limit, etf_codes=etf_codes)
    if should_stop is not None and should_stop():
        raise ResearchRunCancelled("research run cancelled")
    if use_relative_strength:
        frames = attach_relative_strength_rank(frames)
    if should_stop is not None and should_stop():
        raise ResearchRunCancelled("research run cancelled")

    results = StrategyExperimentRunner().run_universe(
        price_frames=frames,
        candidates=candidates,
        categories=categories or {},
        should_stop=should_stop,
        on_progress=on_progress,
    )
    ranking = rank_candidates(results)
    return ResearchRunOutput(results=results, ranking=ranking, used_count=len(frames), skipped_count=skipped_count)
