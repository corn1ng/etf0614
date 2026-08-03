import pandas as pd
import pytest
import warnings

from etf_trading.data.provider_runtime import ProviderCallError, ProviderCapabilityError, ProviderSettings
from etf_trading.data.index_catalog import IndexCatalogEntry
from etf_trading.data.providers.tushare_provider import TushareProvider


class _FakePro:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def query(self, api_name, fields="", **params):
        self.calls.append((api_name, fields, params))
        response = self.responses[api_name]
        if isinstance(response, Exception):
            raise response
        return response.copy()


def _provider(responses):
    return TushareProvider(ProviderSettings(token="test", attempts=1), pro_client=_FakePro(responses))


def test_etf_list_filters_lof_and_normalizes_code():
    provider = _provider({"fund_basic": pd.DataFrame({
        "ts_code": ["510300.SH", "501050.SH"], "name": ["沪深300ETF", "50AH优选LOF"],
        "management": ["华泰柏瑞", "华夏"], "fund_type": ["股票型", "股票型"],
        "type": ["ETF", "LOF"], "list_date": ["20120528", "20161128"], "status": ["L", "L"],
    })})
    result = provider.fetch_etf_list()
    assert result["etf_code"].tolist() == ["510300"]
    assert result.loc[0, "exchange"] == "SSE"
    assert result.loc[0, "data_source"] == "tushare_fund_basic"


def test_etf_list_filter_does_not_emit_pandas_reindex_warning():
    provider = _provider({"fund_basic": pd.DataFrame({
        "ts_code": ["510300.SH", "501050.SH"], "name": ["沪深300ETF", "50AH优选LOF"],
        "management": ["华泰柏瑞", "华夏"], "fund_type": ["股票型", "股票型"],
        "type": ["ETF", "LOF"], "list_date": ["20120528", "20161128"], "status": ["L", "L"],
    })})
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = provider.fetch_etf_list()
    assert result["etf_code"].tolist() == ["510300"]


def test_qfq_requires_factors_and_normalizes_amount():
    provider = _provider({
        "fund_daily": pd.DataFrame({"ts_code": ["510300.SH"], "trade_date": ["20260701"], "open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "vol": [10.0], "amount": [1.0]}),
        "fund_adj": pd.DataFrame({"ts_code": ["510300.SH"], "trade_date": ["20260701"], "adj_factor": [2.0]}),
    })
    result = provider.fetch_etf_daily("510300", "2026-07-01", "2026-07-01", adjust="qfq")
    assert result.loc[0, "amount"] == 1000.0
    assert result.loc[0, "adjust"] == "qfq"


def test_spot_is_explicit_capability_gap():
    with pytest.raises(ProviderCapabilityError, match="realtime ETF spot"):
        _provider({}).fetch_exchange_traded_etf_spot()


def test_missing_adjustment_factor_fails():
    provider = _provider({
        "fund_daily": pd.DataFrame({"ts_code": ["510300.SH"], "trade_date": ["20260701"], "open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "vol": [10.0], "amount": [1.0]}),
        "fund_adj": pd.DataFrame(),
    })
    with pytest.raises(ProviderCallError, match="adjustment factors"):
        provider.fetch_etf_daily("510300", "2026-07-01", "2026-07-01", adjust="qfq")


def test_trade_calendar_normalizes_tushare_dates():
    provider = _provider({"trade_cal": pd.DataFrame({"exchange": ["SSE"], "cal_date": ["20260701"], "is_open": [1]})})
    result = provider.fetch_trade_calendar("SSE", "2026-07-01", "2026-07-01")
    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-01"]


def test_index_daily_normalizes_tushare_prices():
    provider = _provider({"index_daily": pd.DataFrame({"ts_code": ["000300.SH"], "trade_date": ["20260701"], "open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "vol": [10.0], "amount": [2.0]})})
    result = provider.fetch_index_daily("000300", "2026-07-01", "2026-07-01")
    assert result.loc[0, "index_code"] == "000300"
    assert result.loc[0, "amount"] == 2000.0


def test_index_daily_uses_catalog_provider_symbol():
    pro = _FakePro({"index_daily": pd.DataFrame({"ts_code": ["399001.SZ"], "trade_date": ["20260701"], "open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "vol": [10.0], "amount": [2.0]})})
    provider = TushareProvider(ProviderSettings(token="test", attempts=1), pro_client=pro)
    entry = IndexCatalogEntry("custom", "custom", "A股", "broad", "broad", "broad", "core", None, "unverified", "csi", "399001.SZ")

    provider.fetch_index_daily(entry, "2026-07-01", "2026-07-01")

    assert pro.calls[-1][2]["ts_code"] == "399001.SZ"


def test_index_daily_uses_csi_symbol_for_hk_catalog_entry():
    pro = _FakePro({"index_daily": pd.DataFrame()})
    provider = TushareProvider(ProviderSettings(token="test", attempts=1), pro_client=pro)
    entry = IndexCatalogEntry("H30533", "China Internet 50", "HK", "theme", "theme", "broad", "core", None, "official", "hk", "H30533.CSI")

    provider.fetch_index_daily(entry, "2026-07-01", "2026-07-01")

    assert pro.calls[-1][2]["ts_code"] == "H30533.CSI"


def test_index_dailybasic_normalizes_all_official_fields():
    pro = _FakePro({"index_dailybasic": pd.DataFrame({
        "ts_code": ["000300.SH"],
        "trade_date": ["20260729"],
        "total_mv": [51_000_000.0],
        "float_mv": [42_000_000.0],
        "total_share": [3_000_000.0],
        "float_share": [2_500_000.0],
        "free_share": [1_800_000.0],
        "turnover_rate": [0.27],
        "turnover_rate_f": [0.45],
        "pe": [11.90],
        "pe_ttm": [11.60],
        "pb": [1.24],
    })})
    provider = TushareProvider(ProviderSettings(token="test", attempts=1), pro_client=pro)

    result = provider.fetch_index_official_valuations("000300", "2026-07-01", "2026-07-29")

    assert pro.calls[0][0] == "index_dailybasic"
    assert pro.calls[0][2]["ts_code"] == "000300.SH"
    assert result.loc[0, ["index_code", "pe_static", "pe_ttm", "pb", "turnover_rate", "data_source"]].to_dict() == {
        "index_code": "000300",
        "pe_static": 11.90,
        "pe_ttm": 11.60,
        "pb": 1.24,
        "turnover_rate": 0.27,
        "data_source": "tushare_index_dailybasic",
    }
