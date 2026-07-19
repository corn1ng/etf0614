from datetime import date

import pandas as pd

from etf_trading.data.provider import DataProvider
from etf_trading.data.provider_runtime import ProviderCallError
from etf_trading.data.providers.fallback_provider import PrimaryFallbackProvider


class _Provider(DataProvider):
    def __init__(self, value): self.value = value
    def _call(self):
        if isinstance(self.value, Exception): raise self.value
        return self.value.copy()
    def fetch_etf_list(self): return self._call()
    def fetch_exchange_traded_etf_spot(self): return self._call()
    def fetch_etf_daily(self, code, start_date, end_date, adjust="qfq"): return self._call()
    def fetch_etf_nav(self, code, start_date, end_date): return self._call()
    def fetch_index_daily(self, code, start_date, end_date): return self._call()
    def fetch_trade_calendar(self, market, start_date, end_date): return self._call()


def test_primary_failure_returns_fallback_and_notice():
    fallback_data = pd.DataFrame({"data_source": ["akshare_eastmoney"]})
    provider = PrimaryFallbackProvider(_Provider(ProviderCallError("timeout", category="network")), _Provider(fallback_data))
    result = provider.fetch_etf_daily("510300", date(2026, 7, 1), date(2026, 7, 2))
    assert result["data_source"].tolist() == ["akshare_eastmoney"]
    notice = provider.drain_notices()[0]
    assert (notice.asset_code, notice.category) == ("510300", "network")


def test_primary_success_has_no_notice():
    provider = PrimaryFallbackProvider(_Provider(pd.DataFrame({"data_source": ["tushare_fund_daily"]})), _Provider(AssertionError("not called")))
    provider.fetch_etf_daily("510300", date(2026, 7, 1), date(2026, 7, 2))
    assert provider.drain_notices() == ()
