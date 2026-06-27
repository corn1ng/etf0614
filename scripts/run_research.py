"""Run local ETF strategy research over cached Parquet price data."""

from __future__ import annotations

import argparse
from pathlib import Path

from etf_trading.data.storage import SQLiteStore
from etf_trading.research.config import load_research_candidates
from etf_trading.research.runner import run_research


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF strategy research experiments.")
    parser.add_argument("--config", default="configs/research.yaml", help="Research YAML config path.")
    parser.add_argument("--parquet-root", default="data/parquet", help="Parquet storage root.")
    parser.add_argument("--sqlite-path", default="database/etf_system.sqlite", help="SQLite metadata path.")
    parser.add_argument("--output-dir", default="reports/research", help="Directory for CSV outputs.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max ETF count for quick smoke runs.")
    parser.add_argument("--min-rows", type=int, default=252, help="Minimum history rows required per ETF.")
    parser.add_argument("--no-relative-strength", action="store_true", help="Disable daily cross-sectional RS ranking.")
    args = parser.parse_args()

    candidates = load_research_candidates(args.config)
    categories = _load_categories(Path(args.sqlite_path))
    output = run_research(
        parquet_root=args.parquet_root,
        candidates=candidates,
        categories=categories,
        min_rows=args.min_rows,
        limit=args.limit,
        use_relative_strength=not args.no_relative_strength,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output.results.to_csv(output_dir / "research_results.csv", index=False)
    output.ranking.to_csv(output_dir / "candidate_ranking.csv", index=False)
    print(
        f"Wrote {len(output.results)} result rows for {len(candidates)} candidates "
        f"over {output.used_count} ETFs to {output_dir}; skipped {output.skipped_count} short histories"
    )


def _load_categories(sqlite_path: Path) -> dict[str, str]:
    if not sqlite_path.exists():
        return {}
    master = SQLiteStore(sqlite_path).list_etf_master()
    if master.empty or "etf_code" not in master.columns or "category" not in master.columns:
        return {}
    return dict(zip(master["etf_code"].astype(str), master["category"].fillna("A股行业").astype(str), strict=False))


if __name__ == "__main__":
    main()
