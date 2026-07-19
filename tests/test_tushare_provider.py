import pandas as pd
import pytest
import warnings

from etf_trading.data.provider_runtime import ProviderCallError, ProviderCapabilityError, ProviderSettings
from etf_trading.data.providers.tushare_provider import TushareProvider


class _FakePro:
    def __init__(self, responses):
        self.responses = responses

    def query(self, api_name, fields="", **params):
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
