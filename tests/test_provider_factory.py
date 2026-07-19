from etf_trading.data.provider_runtime import ProviderSettings
from etf_trading.data.providers.factory import create_data_provider
from etf_trading.data.providers.fallback_provider import PrimaryFallbackProvider
from etf_trading.data.providers.tushare_provider import TushareProvider


def test_factory_builds_lazy_tushare_primary_and_akshare_fallback():
    provider = create_data_provider(ProviderSettings(token="test-token"))

    assert isinstance(provider, PrimaryFallbackProvider)
    assert isinstance(provider.primary, TushareProvider)
    assert provider.primary._pro_client is None
