import pandas as pd

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


def test_fetch_etf_list_merges_fund_name_etf_fallback():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeEtfListAk()

    result = provider.fetch_etf_list()

    assert {"510300", "515080"}.issubset(set(result["etf_code"]))
    fallback = result[result["etf_code"] == "515080"].iloc[0]
    assert fallback["name"] == "中证红利ETF招商"
    assert fallback["is_active"] == 1
