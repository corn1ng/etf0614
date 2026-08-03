"""Tushare-first provider that records explicit AkShare fallbacks."""

from __future__ import annotations

from threading import Lock

from etf_trading.data.provider import DataProvider
from etf_trading.data.provider_runtime import ProviderCapabilityError, ProviderNotice, redact_provider_text


class CombinedProviderError(RuntimeError):
    pass


class PrimaryFallbackProvider(DataProvider):
    def __init__(self, primary: DataProvider, fallback: DataProvider, *, secrets=()) -> None:
        self.primary, self.fallback = primary, fallback
        self.secrets = tuple(value for value in secrets if value)
        self._notices: list[ProviderNotice] = []
        self._lock = Lock()

    def drain_notices(self) -> tuple[ProviderNotice, ...]:
        with self._lock:
            notices = tuple(self._notices)
            self._notices.clear()
            return notices

    def _dispatch(self, operation, code, primary_call, fallback_call):
        try:
            return primary_call()
        except Exception as primary_error:
            notice = ProviderNotice(operation, str(code), getattr(primary_error, "category", "provider"), redact_provider_text(primary_error, secrets=self.secrets), "akshare", isinstance(primary_error, ProviderCapabilityError))
            with self._lock: self._notices.append(notice)
            try: return fallback_call()
            except Exception as fallback_error:
                raise CombinedProviderError(f"Tushare {operation} failed: {notice.reason}; AkShare failed: {redact_provider_text(fallback_error, secrets=self.secrets)}") from fallback_error

    def fetch_etf_list(self): return self._dispatch("fetch_etf_list", "", self.primary.fetch_etf_list, self.fallback.fetch_etf_list)
    def fetch_exchange_traded_etf_spot(self): return self._dispatch("fetch_exchange_traded_etf_spot", "", self.primary.fetch_exchange_traded_etf_spot, self.fallback.fetch_exchange_traded_etf_spot)
    def fetch_etf_daily(self, code, start_date, end_date, adjust="qfq"): return self._dispatch("fetch_etf_daily", code, lambda: self.primary.fetch_etf_daily(code, start_date, end_date, adjust), lambda: self.fallback.fetch_etf_daily(code, start_date, end_date, adjust))
    def fetch_etf_nav(self, code, start_date, end_date): return self._dispatch("fetch_etf_nav", code, lambda: self.primary.fetch_etf_nav(code, start_date, end_date), lambda: self.fallback.fetch_etf_nav(code, start_date, end_date))
    def fetch_index_daily(self, code, start_date, end_date): return self._dispatch("fetch_index_daily", getattr(code, "index_code", code), lambda: self.primary.fetch_index_daily(code, start_date, end_date), lambda: self.fallback.fetch_index_daily(code, start_date, end_date))
    def fetch_index_official_valuations(self, index_code, start_date, end_date): return self.primary.fetch_index_official_valuations(index_code, start_date, end_date)
    def fetch_trade_calendar(self, market, start_date, end_date): return self._dispatch("fetch_trade_calendar", market, lambda: self.primary.fetch_trade_calendar(market, start_date, end_date), lambda: self.fallback.fetch_trade_calendar(market, start_date, end_date))
