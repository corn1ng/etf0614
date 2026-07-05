import numpy as np
import pandas as pd

from etf_trading.research.atomic_indicators import build_etf_atomic_indicator_snapshot


class FakeParquetStore:
    def __init__(self, frames: dict[str, pd.DataFrame | Exception]) -> None:
        self.frames = frames

    def read_prices(self, code: str) -> pd.DataFrame:
        value = self.frames.get(str(code))
        if isinstance(value, Exception):
            raise value
        return pd.DataFrame() if value is None else value.copy()


def _master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["510300", "512880", "513180", "515000"],
            "name": ["沪深300ETF", "证券ETF", "恒生科技ETF", "科技ETF联接"],
            "category": ["A股宽基", "A股行业", "港股科技", "A股科技"],
            "exchange": ["SSE", "SSE", "SSE", "SSE"],
            "amount": [1000.0, 900.0, 800.0, None],
            "tradability_status": ["exchange_traded", "exchange_traded", "exchange_traded", "auxiliary_only"],
        }
    )


def _prices(code: str, rows: int, end: str, close_start: float = 10.0) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=rows)
    close = np.linspace(close_start, close_start + rows - 1, rows)
    return pd.DataFrame(
        {
            "etf_code": code,
            "trade_date": dates,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(rows, 1000),
            "amount": np.linspace(1_000_000, 2_000_000, rows),
        }
    )


def test_atomic_snapshot_reports_history_feature_status_and_ranks():
    snapshot = build_etf_atomic_indicator_snapshot(
        _master(),
        FakeParquetStore(
            {
                "510300": _prices("510300", 300, "2026-07-03", 10.0),
                "512880": _prices("512880", 300, "2026-07-03", 20.0),
                "513180": _prices("513180", 20, "2026-07-03", 30.0),
            }
        ),
        today=pd.Timestamp("2026-07-05"),
    )

    assert snapshot["etf_code"].tolist() == ["510300", "512880", "513180"]
    ready = snapshot[snapshot["etf_code"] == "510300"].iloc[0]
    assert ready["history_status"] == "complete"
    assert ready["feature_status"] == "complete"
    assert ready["return_20_rank_all"] in {1, 2}
    short = snapshot[snapshot["etf_code"] == "513180"].iloc[0]
    assert short["history_status"] == "short_history"
    assert "ma60" in short["missing_feature_names"]


def test_atomic_snapshot_keeps_unreadable_and_missing_rows_diagnostic():
    snapshot = build_etf_atomic_indicator_snapshot(
        _master().iloc[:3],
        FakeParquetStore({"510300": RuntimeError("broken parquet")}),
        today=pd.Timestamp("2026-07-05"),
    )

    assert snapshot.loc[snapshot["etf_code"] == "510300", "history_status"].item() == "read_failed"
    assert snapshot.loc[snapshot["etf_code"] == "512880", "history_status"].item() == "missing_history"
    assert "read_failed" in snapshot.loc[snapshot["etf_code"] == "510300", "missing_feature_names"].item()


def test_atomic_snapshot_schema_excludes_scores_and_trade_advice():
    snapshot = build_etf_atomic_indicator_snapshot(
        _master(),
        FakeParquetStore({"510300": _prices("510300", 300, "2026-07-03")}),
        today=pd.Timestamp("2026-07-05"),
    )

    forbidden = {"score", "weighted_score", "action", "buy", "sell", "target_weight", "买入", "卖出", "目标仓位"}
    assert forbidden.isdisjoint({column.lower() for column in snapshot.columns})
