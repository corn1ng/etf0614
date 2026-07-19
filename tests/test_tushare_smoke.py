"""Opt-in live probe for the configured Tushare proxy; never embeds credentials."""

from __future__ import annotations

import os

import pytest

from etf_trading.data.provider_runtime import ProviderSettings
from etf_trading.data.providers.tushare_provider import TushareProvider


@pytest.mark.skipif(os.environ.get("RUN_TUSHARE_SMOKE") != "1", reason="set RUN_TUSHARE_SMOKE=1 to call the live proxy")
def test_live_tushare_proxy_trade_calendar():
    pytest.importorskip("tushare")
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        pytest.skip("TUSHARE_TOKEN is not configured")

    provider = TushareProvider(ProviderSettings(token=token))
    frame = provider.fetch_trade_calendar("SSE", "2026-07-01", "2026-07-03")

    assert not frame.empty
    assert {"market", "trade_date", "is_open"}.issubset(frame.columns)
