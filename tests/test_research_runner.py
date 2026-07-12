import pandas as pd

from etf_trading.data.storage import ParquetStore
from etf_trading.research.runner import attach_relative_strength_rank, load_price_frames


def test_attach_relative_strength_rank_ranks_etfs_by_momentum_each_day():
    frames = {
        "510300": pd.DataFrame(
            {
                "etf_code": ["510300", "510300"],
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "momentum_60": [0.10, 0.01],
            }
        ),
        "512800": pd.DataFrame(
            {
                "etf_code": ["512800", "512800"],
                "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                "momentum_60": [0.05, 0.03],
            }
        ),
    }

    ranked = attach_relative_strength_rank(frames)

    assert ranked["510300"].loc[0, "relative_strength_rank"] == 0.5
    assert ranked["512800"].loc[0, "relative_strength_rank"] == 1.0
    assert ranked["512800"].loc[1, "relative_strength_rank"] == 0.5
    assert ranked["510300"].loc[1, "relative_strength_rank"] == 1.0


def test_load_price_frames_filters_to_requested_etf_codes(tmp_path):
    store = ParquetStore(tmp_path)
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [1.0, 1.1],
            "high": [1.2, 1.3],
            "low": [0.9, 1.0],
            "close": [1.1, 1.2],
            "volume": [100, 120],
        }
    )
    store.write_prices("510300", frame)
    store.write_prices("512800", frame)

    frames, skipped_count = load_price_frames(tmp_path, min_rows=2, etf_codes=["510300"])

    assert list(frames) == ["510300"]
    assert skipped_count == 0
