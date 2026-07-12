"""Verify durable evidence for the formal index catalogue's history baselines."""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pandas as pd

import etf_trading.data.initialization as initialization
from etf_trading.data.index_catalog import DEFAULT_BASELINE_EVIDENCE_PATH
from etf_trading.data.initialization import InitializationService
from etf_trading.data.storage import SQLiteStore


def main(argv: Sequence[str] | None = None) -> int:
    """Run formal-index baseline verification and print one durable result per code."""

    parser = _argument_parser()
    args = parser.parse_args(argv)
    through = _parse_date(args.through, parser)
    evidence_path = Path(args.evidence_path) if args.evidence_path is not None else DEFAULT_BASELINE_EVIDENCE_PATH
    write_evidence = args.write_evidence or args.evidence_path is not None

    service = InitializationService(store=SQLiteStore(args.sqlite_path))
    with _evidence_path(evidence_path):
        results = service.verify_index_baseline_evidence(through, write_evidence=write_evidence)

    _print_results(results)
    return 0


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify history-baseline evidence for formal indexes.")
    parser.add_argument("--through", required=True, help="ISO date used as the evidence check date.")
    parser.add_argument(
        "--formal",
        action="store_true",
        required=True,
        help="Verify only the core and research index pools.",
    )
    parser.add_argument(
        "--write-evidence",
        action="store_true",
        help="Persist trusted results to the configured evidence YAML.",
    )
    parser.add_argument(
        "--evidence-path",
        help="Optional evidence YAML target; specifying it also requests a write.",
    )
    parser.add_argument(
        "--sqlite-path",
        default="database/etf_system.sqlite",
        help="SQLite catalogue projection path.",
    )
    return parser


def _parse_date(value: str, parser: argparse.ArgumentParser) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        parser.error("--through must be an ISO date (YYYY-MM-DD)")
        raise AssertionError("argparse.error does not return")


@contextmanager
def _evidence_path(path: Path) -> Iterator[None]:
    """Temporarily point the existing maintenance service at the requested YAML."""

    original_path = initialization.DEFAULT_BASELINE_EVIDENCE_PATH
    initialization.DEFAULT_BASELINE_EVIDENCE_PATH = path
    try:
        yield
    finally:
        initialization.DEFAULT_BASELINE_EVIDENCE_PATH = original_path


def _print_results(results: pd.DataFrame) -> None:
    statuses = results.get("evidence_status", pd.Series(dtype=str)).fillna("").astype(str)
    for status in ("OFFICIAL", "THIRD_PARTY_PUBLICATION", "UNRESOLVED"):
        print(f"{status}: {int((statuses == status).sum())}")

    for row in results.to_dict(orient="records"):
        code = str(row.get("index_code") or "")
        status = str(row.get("evidence_status") or "UNRESOLVED")
        reference_date = str(row.get("reference_date") or "")
        detail = str(row.get("detail") or "")
        print(" | ".join(part for part in (code, status, reference_date, detail) if part))


if __name__ == "__main__":
    raise SystemExit(main())
