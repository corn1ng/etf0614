"""Single construction point for the configured market-data provider."""

from __future__ import annotations

from typing import Mapping

from etf_trading.data.provider_runtime import ProviderSettings, load_provider_settings
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.providers.fallback_provider import PrimaryFallbackProvider
from etf_trading.data.providers.tushare_provider import TushareProvider


def create_data_provider(settings: ProviderSettings | None = None, *, environ: Mapping[str, str] | None = None) -> PrimaryFallbackProvider:
    resolved = settings or load_provider_settings(environ=environ)
    return PrimaryFallbackProvider(TushareProvider(resolved), AkShareProvider(), secrets=(resolved.token,))
