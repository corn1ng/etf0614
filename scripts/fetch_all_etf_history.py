from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from etf_trading.data.initialization import InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.ui.data_coverage import expected_latest_trade_date


REQUIRED_COLUMNS = {
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "ma20",
    "ma60",
    "return_20",
    "return_60",
    "avg_amount_5",
    "avg_amount_20",
    "amount_ratio_5_20",
    "atr20",
    "distance_ma20_atr",
    "distance_ma20_pct",
    "rolling_high_close_60",
    "is_60d_close_breakout",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch full ETF master-pool history into local Parquet cache.")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-index", type=int, default=1, help="1-based inclusive index in the sorted master list.")
    parser.add_argument("--end-index", type=int, default=0, help="1-based inclusive index in the sorted master list; 0 means no cap.")
    parser.add_argument("--shard-count", type=int, default=1, help="Split selected codes into N deterministic shards.")
    parser.add_argument("--shard-index", type=int, default=0, help="0-based shard index to run when shard-count > 1.")
    parser.add_argument("--summary", default="logs/fetch_all_etf_history_summary.json")
    parser.add_argument("--no-refresh-master", action="store_true")
    args = parser.parse_args()

    store = SQLiteStore()
    store.initialize_schema()
    parquet = ParquetStore()
    provider = AkShareProvider()
    service = InitializationService(store=store, provider=provider, parquet_store=parquet)
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    start_date = date.today() - timedelta(days=365 * args.years)
    end_date = date.today()
    expected_latest = expected_latest_trade_date(pd.Timestamp(end_date))
    summary: dict[str, object] = {
        "started_at": pd.Timestamp.now().isoformat(),
        "start_date": str(start_date),
        "end_date": str(end_date),
        "expected_latest_trade_date": expected_latest.strftime("%Y-%m-%d"),
        "master_before": 0,
        "master_after": 0,
        "total": 0,
        "processed": 0,
        "stored": 0,
        "skipped": 0,
        "empty": 0,
        "failed": 0,
        "failures": [],
    }

    def save_summary() -> None:
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    current_master = store.list_etf_master()
    summary["master_before"] = int(len(current_master))
    if not args.no_refresh_master:
        try:
            refreshed = service.initialize_master()
            print(f"MASTER refreshed rows={len(refreshed)}", flush=True)
        except Exception as exc:  # noqa: BLE001 - fall back to local master for this operational task
            print(f"MASTER refresh failed; using local master: {exc}", flush=True)

    master = store.list_etf_master()
    summary["master_after"] = int(len(master))
    if master.empty:
        print("MASTER empty; nothing to fetch", flush=True)
        summary["finished_at"] = pd.Timestamp.now().isoformat()
        save_summary()
        return

    if "is_active" in master.columns:
        master = master[master["is_active"].fillna(1).astype(int) == 1]
    codes = master["etf_code"].astype(str).str.zfill(6).drop_duplicates().sort_values().tolist()
    if args.limit > 0:
        codes = codes[: args.limit]
    indexed_codes = list(enumerate(codes, start=1))
    if args.start_index > 1:
        indexed_codes = [(index, code) for index, code in indexed_codes if index >= args.start_index]
    if args.end_index > 0:
        indexed_codes = [(index, code) for index, code in indexed_codes if index <= args.end_index]
    if args.shard_count < 1:
        raise ValueError("--shard-count must be >= 1")
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("--shard-index must be between 0 and shard-count - 1")
    if args.shard_count > 1:
        indexed_codes = [
            (index, code)
            for index, code in indexed_codes
            if (index - 1) % args.shard_count == args.shard_index
        ]
    codes = [code for _, code in indexed_codes]
    summary["total"] = len(codes)
    summary["source_total"] = len(master)
    summary["start_index"] = args.start_index
    summary["end_index"] = args.end_index
    summary["shard_count"] = args.shard_count
    summary["shard_index"] = args.shard_index
    save_summary()
    print(
        f"FETCH total={len(codes)} start={start_date} end={end_date} "
        f"expected_latest={expected_latest.strftime('%Y-%m-%d')}",
        flush=True,
    )

    try:
        for index, code in enumerate(codes, start=1):
            try:
                existing = parquet.read_prices(code)
                if _is_fresh(existing, expected_latest):
                    summary["skipped"] = int(summary["skipped"]) + 1
                    summary["processed"] = index
                    if index % 25 == 0 or index == len(codes):
                        print(f"PROGRESS {index}/{len(codes)} skipped_fresh code={code}", flush=True)
                    save_summary()
                    continue

                frame = service.fetch_and_store_history(code, start_date, end_date)
                summary["processed"] = index
                if frame.empty:
                    summary["empty"] = int(summary["empty"]) + 1
                    store.upsert_update_state("etf_daily_price", code, None, status="EMPTY")
                    print(f"EMPTY {index}/{len(codes)} {code}", flush=True)
                else:
                    summary["stored"] = int(summary["stored"]) + 1
                    latest_text = pd.Timestamp(frame["trade_date"].max()).strftime("%Y-%m-%d") if "trade_date" in frame else ""
                    print(f"STORED {index}/{len(codes)} {code} rows={len(frame)} latest={latest_text}", flush=True)
            except Exception as exc:  # noqa: BLE001 - one failed ETF must not stop the batch
                summary["processed"] = index
                summary["failed"] = int(summary["failed"]) + 1
                message = str(exc)
                failures = list(summary["failures"])
                failures.append({"code": code, "error": message[:500]})
                summary["failures"] = failures
                store.upsert_update_state("etf_daily_price", code, None, status="FAILED", error_message=message[:1000])
                print(f"FAILED {index}/{len(codes)} {code} error={message}", flush=True)
            save_summary()
            time.sleep(args.sleep)
    finally:
        summary["finished_at"] = pd.Timestamp.now().isoformat()
        save_summary()
        print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)


def _is_fresh(frame: pd.DataFrame, expected_latest: pd.Timestamp) -> bool:
    if frame.empty or not REQUIRED_COLUMNS.issubset(frame.columns):
        return False
    latest = pd.to_datetime(frame["trade_date"], errors="coerce").dropna().max()
    return bool(pd.notna(latest) and pd.Timestamp(latest).normalize() >= expected_latest)


if __name__ == "__main__":
    main()
