import pandas as pd

from etf_trading.data.index_catalog import IndexCatalogEntry
from etf_trading.data.providers.akshare_provider import AkShareProvider


class _FakeAk:
    def fund_etf_hist_em(self, **kwargs):
        raise RuntimeError("eastmoney down")

    def fund_etf_hist_sina(self, symbol):
        assert symbol == "sz159337"
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-09-20", "2024-09-23", "2024-10-01"]),
                "open": [0.996, 0.991, 1.0],
                "high": [1.0, 1.006, 1.1],
                "low": [0.991, 0.991, 0.9],
                "close": [0.996, 0.996, 1.05],
                "volume": [100, 200, 300],
                "amount": [1000, 2000, 3000],
            }
        )


def test_fetch_etf_daily_falls_back_to_sina_when_eastmoney_fails():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeAk()

    result = provider.fetch_etf_daily("159337", "2024-09-21", "2024-09-30")

    assert result["etf_code"].tolist() == ["159337"]
    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-09-23"]
    assert result["close"].tolist() == [0.996]


class _FakeSse52Ak:
    def fund_etf_hist_em(self, **kwargs):
        raise RuntimeError("eastmoney down")

    def fund_etf_hist_sina(self, symbol):
        assert symbol == "sh520500"
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-07-03"]),
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "close": [1.05],
                "volume": [100],
                "amount": [1000],
            }
        )


def test_fetch_etf_daily_uses_sh_prefix_for_52_sina_fallback():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeSse52Ak()

    result = provider.fetch_etf_daily("520500", "2026-07-01", "2026-07-05")

    assert result["etf_code"].tolist() == ["520500"]
    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-03"]


class _FakeEtfListAk:
    def fund_etf_spot_em(self):
        return pd.DataFrame(
            {
                "代码": ["510300"],
                "名称": ["沪深300ETF"],
                "最新价": [4.0],
                "成交额": [1000000],
            }
        )

    def fund_name_em(self):
        return pd.DataFrame(
            {
                "基金代码": ["515080", "000001"],
                "基金简称": ["中证红利ETF招商", "华夏成长混合"],
                "基金类型": ["指数型-股票", "混合型-灵活"],
            }
        )


def test_fetch_etf_list_uses_spot_only_for_tradable_master():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeEtfListAk()

    result = provider.fetch_etf_list()

    assert result["etf_code"].tolist() == ["510300"]
    assert result.iloc[0]["tradability_status"] == "exchange_traded"
    assert result.iloc[0]["data_source"] == "fund_etf_spot_em"
    assert "515080" not in set(result["etf_code"])


def test_fetch_exchange_traded_etf_spot_normalizes_realtime_fields():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeEtfListAk()

    result = provider.fetch_exchange_traded_etf_spot()

    row = result.iloc[0]
    assert row["etf_code"] == "510300"
    assert row["exchange"] == "SSE"
    assert row["is_active"] == 1
    assert row["tradability_status"] == "exchange_traded"


def _catalog_entry(*, code: str, market: str, source_kind: str, provider_symbol: str) -> IndexCatalogEntry:
    return IndexCatalogEntry(
        index_code=code,
        name="测试指数",
        market=market,
        category_level_1="测试分类",
        category_level_2="测试分类",
        index_type="行业",
        pool="research",
        index_base_date=None,
        baseline_source="unverified",
        source_kind=source_kind,  # type: ignore[arg-type]
        provider_symbol=provider_symbol,
    )


class _FakeShenwanIndexAk:
    def index_hist_sw(self, *, symbol, period):
        assert symbol == "801010"
        assert period == "day"
        return pd.DataFrame(
            {
                "日期": ["1999-12-30", "2000-01-04"],
                "开盘": [1000.0, 1005.0],
                "最高": [1001.0, 1006.0],
                "最低": [999.0, 1004.0],
                "收盘": [1000.5, 1005.5],
                "成交量": [100, 101],
                "成交额": [1000, 1010],
            }
        )


def test_fetch_index_daily_uses_shenwan_route_for_catalog_entry():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeShenwanIndexAk()

    result = provider.fetch_index_daily(
        _catalog_entry(code="801010", market="A股", source_kind="shenwan", provider_symbol="801010"),
        "1990-01-01",
        "2000-01-04",
    )

    assert result["index_code"].tolist() == ["801010", "801010"]
    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["1999-12-30", "2000-01-04"]
    assert result["data_source"].tolist() == ["akshare_shenwan", "akshare_shenwan"]


class _FakeCsiHongKongIndexAk:
    def stock_zh_index_hist_csindex(self, *, symbol, start_date, end_date):
        assert symbol == "H30015"
        assert start_date == "19900101"
        assert end_date == "20260710"
        return pd.DataFrame(
            {
                "日期": ["2026-07-09"],
                "开盘": [1000.0],
                "最高": [1001.0],
                "最低": [999.0],
                "收盘": [1000.5],
                "成交量": [100],
                "成交额": [1000],
            }
        )


def test_fetch_index_daily_uses_csi_route_for_hong_kong_catalog_entry():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeCsiHongKongIndexAk()

    result = provider.fetch_index_daily(
        _catalog_entry(code="H30015", market="港股", source_kind="csi", provider_symbol="H30015"),
        "1990-01-01",
        "2026-07-10",
    )

    assert result["index_code"].tolist() == ["H30015"]
    assert result["data_source"].tolist() == ["akshare_csindex"]


class _FakeHongKongIndexAk:
    def stock_hk_index_daily_em(self, *, symbol):
        assert symbol == "HSTECH"
        return pd.DataFrame(
            {
                "日期": ["2026-07-09"],
                "开盘": [3000.0],
                "最高": [3001.0],
                "最低": [2999.0],
                "收盘": [3000.5],
                "成交量": [100],
                "成交额": [1000],
            }
        )


def test_fetch_index_daily_uses_hong_kong_route_for_catalog_entry():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeHongKongIndexAk()

    result = provider.fetch_index_daily(
        _catalog_entry(code="HSTECH", market="港股", source_kind="hk", provider_symbol="HSTECH"),
        "2026-07-01",
        "2026-07-10",
    )

    assert result["index_code"].tolist() == ["HSTECH"]
    assert result["data_source"].tolist() == ["akshare_hk_em"]
