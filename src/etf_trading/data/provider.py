"""Provider contract for market data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from etf_trading.data.provider_runtime import ProviderCapabilityError

if TYPE_CHECKING:
    from etf_trading.data.index_catalog import IndexCatalogEntry


class DataProvider(ABC):
    """Data-source interface used by services and UI.

    Providers must normalize column names before returning data. This keeps
    strategies, storage, and charts independent from AkShare/Tushare/yfinance
    naming quirks.
    """

    @abstractmethod
    def fetch_etf_list(self) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_exchange_traded_etf_spot(self) -> pd.DataFrame:
        """Return the current exchange-traded ETF spot universe."""

        return self.fetch_etf_list()

    @abstractmethod
    def fetch_etf_daily(self, code: str, start_date: date | str, end_date: date | str, adjust: str = "qfq") -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_etf_nav(self, code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def fetch_index_daily(
        self,
        code: str | "IndexCatalogEntry",
        start_date: date | str,
        end_date: date | str,
    ) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_index_official_valuations(
        self,
        index_code: str,
        start_date: date | str,
        end_date: date | str,
    ) -> pd.DataFrame:
        raise ProviderCapabilityError(f"official index valuation is unsupported: {index_code}")

    @abstractmethod
    def fetch_trade_calendar(self, market: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        raise NotImplementedError
