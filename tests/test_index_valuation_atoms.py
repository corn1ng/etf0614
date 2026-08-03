import numpy as np
import pandas as pd
import pytest

from etf_trading.research.index_valuation_atoms import (
    VALUATION_PERCENTILE_WINDOWS,
    build_index_valuation_atoms,
    valuation_band,
)


def _daily_valuations(start, periods):
    dates = pd.bdate_range(start, periods=periods)
    return pd.DataFrame(
        {
            "index_code": "000300",
            "trade_date": dates,
            "pe_static": np.linspace(9.0, 15.0, periods),
            "pe_ttm": np.linspace(8.0, 14.0, periods),
            "pb": np.linspace(1.0, 1.8, periods),
            "turnover_rate": np.linspace(0.2, 0.8, periods),
            "turnover_rate_f": np.linspace(0.3, 0.9, periods),
            "total_mv": np.linspace(100.0, 200.0, periods),
            "float_mv": np.linspace(80.0, 160.0, periods),
            "total_share": np.linspace(10.0, 20.0, periods),
            "float_share": np.linspace(8.0, 16.0, periods),
            "free_share": np.linspace(6.0, 12.0, periods),
            "data_source": "tushare_index_dailybasic",
        }
    )


def _by_key(rows):
    return {str(row["metric_key"]): row for row in rows}


def test_midrank_percentile_uses_valid_values_and_exact_window():
    history = _daily_valuations("2021-01-01", periods=1300)
    history.loc[history.index[-3:], "pe_ttm"] = [float("inf"), 10.0, 10.0]

    atoms = _by_key(
        build_index_valuation_atoms(
            "000300", history, pd.Timestamp("2026-01-01"), history["trade_date"], supported=True
        )
    )

    pe = atoms["pe_ttm_percentile_5y"]
    valid = history.loc[
        history["trade_date"].between("2021-01-01", "2026-01-01")
        & history["pe_ttm"].gt(0)
        & np.isfinite(history["pe_ttm"]),
        "pe_ttm",
    ]
    expected = ((valid < 10.0).sum() + 0.5 * (valid == 10.0).sum()) / len(valid)
    assert pe["value"] == pytest.approx(expected)
    assert pe["sample_count"] == len(valid)
    assert pe["window_start_date"] == "2021-01-01"
    assert pe["window_end_date"] == "2026-01-01"


def test_valuation_more_than_five_price_days_old_is_stale():
    one_row = _daily_valuations("2026-07-20", 1)

    atoms = _by_key(
        build_index_valuation_atoms(
            "000300",
            one_row,
            pd.Timestamp("2026-07-29"),
            pd.Series(pd.bdate_range("2026-07-20", "2026-07-29")),
            supported=True,
        )
    )

    assert atoms["valuation_lag_trading_days"]["value"] == 7
    assert atoms["valuation_freshness_status"]["value"] == "stale"


def test_duplicate_price_trade_dates_do_not_inflate_five_day_freshness_threshold():
    one_row = _daily_valuations("2026-07-20", 1)
    price_dates = pd.Series(
        pd.to_datetime(
            [
                "2026-07-20",
                "2026-07-21",
                "2026-07-22",
                "2026-07-23",
                "2026-07-24",
                "2026-07-25",
                "2026-07-25",
                "2026-07-25",
            ]
        )
    )

    atoms = _by_key(
        build_index_valuation_atoms(
            "000300", one_row, pd.Timestamp("2026-07-29"), price_dates, supported=True
        )
    )

    assert atoms["valuation_lag_trading_days"]["value"] == 5
    assert atoms["valuation_freshness_status"]["value"] == "fresh"


def test_unsupported_index_returns_explicit_atoms_without_tracks():
    atoms = _by_key(
        build_index_valuation_atoms(
            "801010", pd.DataFrame(), pd.Timestamp("2026-07-29"), pd.Series(dtype="datetime64[ns]"), supported=False
        )
    )

    assert atoms["valuation_support_status"]["value"] == "unsupported"
    assert "pe_ttm_percentile_5y" not in atoms
    assert all("window_start_date" in row and "window_end_date" in row for row in atoms.values())


def test_supported_index_without_history_marks_each_track_as_missing_data():
    atoms = _by_key(
        build_index_valuation_atoms(
            "000300", pd.DataFrame(), pd.Timestamp("2026-07-29"), pd.Series(dtype="datetime64[ns]"), supported=True
        )
    )

    assert atoms["valuation_support_status"]["value"] == "supported"
    assert atoms["pe_ttm_percentile_3y"]["status"] == "missing_data"
    assert atoms["pb_median_deviation_10y"]["sample_count"] == 0


def test_windows_require_configured_sample_counts_and_preserve_unavailable_status():
    history = _daily_valuations("2023-01-01", periods=600)

    atoms = _by_key(
        build_index_valuation_atoms(
            "000300", history, history.iloc[-1]["trade_date"], history["trade_date"], supported=True
        )
    )

    assert VALUATION_PERCENTILE_WINDOWS == (("3y", 3, 500), ("5y", 5, 900), ("10y", 10, 1800))
    assert atoms["pe_ttm_percentile_3y"]["status"] == "computed"
    assert atoms["pe_ttm_percentile_5y"]["status"] == "insufficient_history"
    assert pd.isna(atoms["pe_ttm_percentile_5y"]["value"])
    assert atoms["pe_ttm_percentile_5y"]["sample_count"] == 600


@pytest.mark.parametrize("window_name, minimum_samples", [("3y", 500), ("5y", 900), ("10y", 1800)])
def test_percentile_windows_are_available_at_their_exact_minimum_sample_counts(window_name, minimum_samples):
    insufficient = _daily_valuations("2015-01-01", minimum_samples - 1)
    available = _daily_valuations("2015-01-01", minimum_samples)

    insufficient_atoms = _by_key(
        build_index_valuation_atoms(
            "000300", insufficient, insufficient.iloc[-1]["trade_date"], insufficient["trade_date"], supported=True
        )
    )
    available_atoms = _by_key(
        build_index_valuation_atoms(
            "000300", available, available.iloc[-1]["trade_date"], available["trade_date"], supported=True
        )
    )

    for metric in ("pe_ttm", "pb"):
        assert insufficient_atoms[f"{metric}_percentile_{window_name}"]["status"] == "insufficient_history"
        assert insufficient_atoms[f"{metric}_percentile_{window_name}"]["sample_count"] == minimum_samples - 1
        assert available_atoms[f"{metric}_percentile_{window_name}"]["status"] == "computed"
        assert available_atoms[f"{metric}_percentile_{window_name}"]["sample_count"] == minimum_samples


def test_latest_record_invalid_fields_are_unavailable_without_backfilling_older_values():
    history = _daily_valuations("2026-01-01", periods=65)
    history["pe_static"] = history["pe_static"].astype(object)
    history.loc[history.index[-1], ["pe_static", "pb", "turnover_rate"]] = ["bad", -1.0, float("inf")]
    history.loc[history.index[-2], "turnover_rate"] = 0.0
    history.loc[history.index[-3], "turnover_rate"] = -0.2

    atoms = _by_key(
        build_index_valuation_atoms(
            "000300", history, history.iloc[-1]["trade_date"], history["trade_date"], supported=True
        )
    )

    assert atoms["pe_static"]["status"] == "missing_data"
    assert atoms["pb"]["status"] == "missing_data"
    assert atoms["pb_percentile_3y"]["status"] == "missing_data"
    assert atoms["turnover_rate"]["status"] == "missing_data"
    assert atoms["turnover_rate_mean_60d"]["sample_count"] == 57
    assert atoms["turnover_rate_mean_60d"]["status"] == "computed"
    assert atoms["turnover_rate_deviation_60d"]["status"] == "missing_data"


def test_band_boundaries_and_change_event_are_fixed_and_atomic():
    assert valuation_band(0.19) == "历史低位"
    assert valuation_band(0.20) == "偏低"
    assert valuation_band(0.40) == "中部"
    assert valuation_band(0.60) == "中部"
    assert valuation_band(0.61) == "偏高"
    assert valuation_band(0.81) == "历史高位"

    history = _daily_valuations("2021-01-01", periods=1300)
    history.loc[history.index[-2:], "pe_ttm"] = [8.0, 20.0]
    atoms = _by_key(
        build_index_valuation_atoms(
            "000300", history, pd.Timestamp("2026-01-01"), history["trade_date"], supported=True
        )
    )

    assert atoms["pe_ttm_5y_band_changed"]["value"] is True
    assert "pb_5y_band_changed" not in atoms
