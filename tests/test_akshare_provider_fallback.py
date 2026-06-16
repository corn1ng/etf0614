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
