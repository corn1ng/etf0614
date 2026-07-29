from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from etf_trading.data.index_catalog import IndexCatalogEntry
from etf_trading.data.storage import ParquetStore
from etf_trading.research.index_data import add_index_trend_features, load_index_frames
from etf_trading.research.index_models import IndexResearchConfig, load_index_research_config


def valid_prices(rows: int, *, start: str = "2020-01-01") -> pd.DataFrame:
    close = pd.Series(range(100, 100 + rows), dtype=float)
    return pd.DataFrame(
        {
            "trade_date": pd.date_range(start, periods=rows, freq="D"),
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        }
    )


def test_config_locks_v1_without_parameter_grid():
    config = load_index_research_config("configs/index_research.yaml")

    assert config.strategy_version == "index_trend_v1"
    assert config.locked_at == date(2026, 7, 30)
    assert config.ma_window == 60
    assert config.slope_lookback == 20
    assert config.buffer_rate == 0.02
    assert config.atr_window == 20
    assert config.atr_multiple == 3.0
    assert config.buffer_ablation == (0.0, 0.02, 0.03)
    assert not hasattr(config, "sensitivity_ma_windows")


def test_official_and_reference_base_dates_are_separate(tmp_path):
    store = ParquetStore(tmp_path)
    store.write_index_prices("OFFICIAL", valid_prices(1100))
    store.write_index_prices("REFERENCE", valid_prices(1100))

    result = load_index_frames(
        tmp_path,
        (
            catalog_entry("OFFICIAL", "official_base_date"),
            catalog_entry("REFERENCE", "third_party_base_date"),
        ),
        locked_config(),
    )

    metadata = result.metadata.set_index("index_code")
    assert metadata.loc["OFFICIAL", "cohort"] == "official"
    assert metadata.loc["REFERENCE", "cohort"] == "reference"
    assert set(result.frames) == {"OFFICIAL", "REFERENCE"}


def test_duplicate_dates_are_excluded_not_silently_deduplicated(tmp_path):
    frame = valid_prices(1100)
    ParquetStore(tmp_path).write_index_prices("TEST", pd.concat([frame, frame.iloc[[5]]]))

    result = load_index_frames(
        tmp_path,
        (catalog_entry("TEST", "official_base_date"),),
        locked_config(),
    )

    assert result.exclusions.iloc[0]["reason_code"] == "duplicate_trade_date"
    assert result.frames == {}


@pytest.mark.parametrize(
    ("frame", "reason_code"),
    [
        (pd.DataFrame(), "missing_price_file"),
        (valid_prices(1100).drop(columns="close"), "missing_required_columns"),
        (valid_prices(1100).assign(trade_date="not-a-date"), "invalid_trade_date"),
        (valid_prices(1100).assign(close=0.0), "non_positive_ohlc"),
        (valid_prices(1100).assign(open=0.0), "non_positive_open"),
        (valid_prices(999), "insufficient_valid_rows"),
    ],
)
def test_invalid_or_insufficient_history_is_excluded(tmp_path, frame, reason_code):
    store = ParquetStore(tmp_path)
    if not frame.empty:
        store.write_index_prices("TEST", frame)

    result = load_index_frames(
        tmp_path,
        (catalog_entry("TEST", "official_base_date"),),
        locked_config(),
    )

    assert result.frames == {}
    assert result.exclusions.iloc[0]["reason_code"] == reason_code


@pytest.mark.parametrize("evidence_kind", ["publication_date", "unresolved"])
def test_non_base_date_evidence_is_excluded(tmp_path, evidence_kind):
    ParquetStore(tmp_path).write_index_prices("TEST", valid_prices(1100))

    result = load_index_frames(
        tmp_path,
        (catalog_entry("TEST", evidence_kind),),
        locked_config(),
    )

    assert result.frames == {}
    assert result.exclusions.iloc[0]["reason_code"] == evidence_kind


def test_admission_truncates_to_base_date_and_preserves_metadata(tmp_path):
    frame = valid_prices(1101, start="2019-12-31")
    ParquetStore(tmp_path).write_index_prices("TEST", frame)
    entry = catalog_entry("TEST", "official_base_date", index_base_date=date(2020, 1, 1))

    result = load_index_frames(tmp_path, (entry,), locked_config())

    admitted = result.frames["TEST"]
    metadata = result.metadata.iloc[0]
    assert admitted["trade_date"].min() == pd.Timestamp("2020-01-01")
    assert metadata["raw_start_date"] == pd.Timestamp("2019-12-31")
    assert metadata["raw_end_date"] == frame["trade_date"].max()
    assert metadata["valid_start_date"] == pd.Timestamp("2020-01-01")
    assert metadata["valid_end_date"] == frame["trade_date"].max()
    assert metadata["valid_rows"] == 1100
    assert metadata["name"] == "Test index"
    assert metadata["market"] == "A股"
    assert metadata["index_type"] == "宽基"
    assert metadata["pool"] == "core"
    assert metadata["cohort"] == "official"


def test_missing_open_is_allowed_but_present_open_must_be_positive(tmp_path):
    frame = valid_prices(1100)
    frame.loc[3, "open"] = None
    ParquetStore(tmp_path).write_index_prices("TEST", frame)

    result = load_index_frames(
        tmp_path,
        (catalog_entry("TEST", "official_base_date"),),
        locked_config(),
    )

    assert set(result.frames) == {"TEST"}


def test_numeric_string_ohlc_is_normalized_before_features_are_calculated(tmp_path):
    frame = valid_prices(1100)
    for column in ("open", "high", "low", "close"):
        frame[column] = frame[column].astype(str)
    ParquetStore(tmp_path).write_index_prices("TEST", frame)

    result = load_index_frames(
        tmp_path,
        (catalog_entry("TEST", "official_base_date"),),
        locked_config(),
    )

    admitted = result.frames["TEST"]
    assert all(pd.api.types.is_numeric_dtype(admitted[column]) for column in ("open", "high", "low", "close"))
    assert admitted["atr20"].notna().any()


def test_add_index_trend_features_uses_only_ma60_slope_and_atr20():
    frame = valid_prices(80).iloc[::-1].reset_index(drop=True)

    result = add_index_trend_features(frame)

    assert result["trade_date"].is_monotonic_increasing
    assert result.iloc[59]["ma60"] == pytest.approx(129.5)
    assert result.iloc[79]["ma60_slope_20"] == pytest.approx(20 / 129.5)
    assert result.iloc[19]["atr20"] == pytest.approx(2.0)
    assert {"ma50", "ma70", "atr14", "momentum", "rs_rank"}.isdisjoint(result.columns)


@pytest.mark.parametrize(
    ("locked_value", "changed_value", "field_name"),
    [
        ("ma_window: 60", "ma_window: 60.9", "ma_window"),
        ("min_valid_rows: 1000", "min_valid_rows: 1000.5", "min_valid_rows"),
    ],
)
def test_config_rejects_fractional_integer_values(tmp_path, locked_value, changed_value, field_name):
    path = tmp_path / "index_research.yaml"
    source = Path("configs/index_research.yaml").read_text(encoding="utf-8")
    path.write_text(source.replace(locked_value, changed_value), encoding="utf-8")

    with pytest.raises(ValueError, match=field_name):
        load_index_research_config(path)


def locked_config() -> IndexResearchConfig:
    return IndexResearchConfig(
        strategy_version="index_trend_v1",
        locked_at=date(2026, 7, 30),
        ma_window=60,
        slope_lookback=20,
        buffer_rate=0.02,
        atr_window=20,
        atr_multiple=3.0,
        buffer_ablation=(0.0, 0.02, 0.03),
        commission_rate=0.00015,
        slippage_rate=0.0002,
        stress_multiplier=2.0,
        min_valid_rows=1000,
        rolling_years=5,
        rolling_step_years=1,
        whipsaw_max_holding_days=20,
        stage_years=(2015, 2018, 2020, 2022),
        min_drawdown_win_rate=0.60,
        min_median_drawdown_reduction=0.20,
        max_median_annual_return_lag=0.02,
    )


def catalog_entry(
    index_code: str,
    baseline_evidence_kind: str,
    *,
    index_base_date: date = date(2020, 1, 1),
) -> IndexCatalogEntry:
    source = {
        "official_base_date": "official_api",
        "third_party_base_date": "third_party_reference",
        "publication_date": "third_party_publication",
        "unresolved": "unverified",
    }[baseline_evidence_kind]
    return IndexCatalogEntry(
        index_code=index_code,
        name="Test index",
        market="A股",
        category_level_1="宽基",
        category_level_2="大盘",
        index_type="宽基",
        pool="core",
        index_base_date=index_base_date if baseline_evidence_kind != "unresolved" else None,
        baseline_source=source,
        source_kind="csi",
        provider_symbol=index_code,
        baseline_evidence_kind=baseline_evidence_kind,
    )
