import pandas as pd

from datetime import date

from etf_trading.data.indexes import DEFAULT_INDEXES, INDEX_HISTORY_AUTO_START, normalize_index_daily
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import ParquetStore


def test_default_indexes_include_csi500_and_hong_kong_indexes():
    codes = {item.index_code for item in DEFAULT_INDEXES}

    assert "000905" in codes
    assert "HSI" in codes
    assert "HSTECH" in codes


def test_default_indexes_include_verified_industry_indexes():
    by_code = {item.index_code: item for item in DEFAULT_INDEXES}

    expected = {
        "399986": "中证银行",
        "399975": "证券公司",
        "000933": "中证医药",
        "000932": "中证消费",
        "000934": "中证金融",
        "000935": "中证信息",
        "000928": "中证能源",
        "000819": "有色金属",
        "000827": "中证环保",
        "399812": "养老产业",
    }
    for code, name in expected.items():
        assert by_code[code].name == name
        assert by_code[code].category == "A股行业"


def test_default_indexes_include_more_verified_sector_and_theme_indexes():
    by_code = {item.index_code: item for item in DEFAULT_INDEXES}

    expected = {
        "930997": ("新能源车", "A股主题"),
        "931152": ("CS创新药", "A股行业"),
        "930707": ("中证畜牧", "A股行业"),
        "930697": ("家用电器", "A股行业"),
        "931009": ("建筑材料", "A股行业"),
        "930901": ("动漫游戏", "A股主题"),
        "930743": ("中证生科", "A股行业"),
        "930633": ("中证旅游", "A股行业"),
        "931087": ("科技龙头", "A股主题"),
        "931865": ("中证半导", "A股行业"),
        "931775": ("房地产", "A股行业"),
        "H11052": ("智能电车", "A股主题"),
        "H30015": ("800汽车", "A股行业"),
        "H30533": ("中国互联网50", "港股科技"),
    }
    for code, (name, category) in expected.items():
        assert by_code[code].name == name
        assert by_code[code].category == category


def test_index_history_auto_start_requests_full_available_history():
    assert INDEX_HISTORY_AUTO_START == date(1990, 1, 1)


def test_normalizes_index_daily_to_price_schema():
    raw = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "open": [5000.0],
            "high": [5100.0],
            "low": [4950.0],
            "close": [5050.0],
            "volume": [100],
            "amount": [200],
        }
    )

    result = normalize_index_daily(raw, index_code="000905", source="fake")

    assert result.columns.tolist() == [
        "index_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "data_source",
    ]
    assert result.iloc[0]["index_code"] == "000905"
    assert result.iloc[0]["data_source"] == "fake"


def test_parquet_store_reads_and_writes_index_prices(tmp_path):
    store = ParquetStore(tmp_path)
    frame = pd.DataFrame(
        {
            "index_code": ["000905"],
            "trade_date": pd.to_datetime(["2024-01-02"]),
            "open": [5000.0],
            "high": [5100.0],
            "low": [4950.0],
            "close": [5050.0],
            "volume": [100],
            "amount": [200],
        }
    )

    path = store.write_index_prices("000905", frame)
    result = store.read_index_prices("000905")

    assert path.name == "000905.parquet"
    assert len(result) == 1
    assert result.iloc[0]["close"] == 5050.0


class _FakeIndexAk:
    def stock_zh_index_daily_em(self, **kwargs):
        return pd.DataFrame()

    def stock_zh_index_daily(self, symbol):
        assert symbol == "sh000905"
        return pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "open": [5000.0, 5010.0],
                "high": [5100.0, 5110.0],
                "low": [4950.0, 4960.0],
                "close": [5050.0, 5060.0],
                "volume": [100, 110],
            }
        )

    def stock_zh_index_hist_csindex(self, **kwargs):
        raise AssertionError("csindex fallback should not be used for 000905")


class _FakeCsindexAk:
    def stock_zh_index_daily_em(self, **kwargs):
        return pd.DataFrame()

    def stock_zh_index_daily(self, symbol):
        return pd.DataFrame()

    def stock_zh_index_hist_csindex(self, symbol, start_date, end_date):
        assert symbol == "930997"
        return pd.DataFrame(
            {
                "日期": ["2024-01-02"],
                "指数代码": ["930997"],
                "开盘": [1200.0],
                "最高": [1220.0],
                "最低": [1190.0],
                "收盘": [1210.0],
                "成交量": [1000],
                "成交金额": [2000],
            }
        )


class _FakeCsindexAfterSinaErrorAk:
    def stock_zh_index_daily_em(self, **kwargs):
        return pd.DataFrame()

    def stock_zh_index_daily(self, symbol):
        raise KeyError("date")

    def stock_zh_index_hist_csindex(self, symbol, start_date, end_date):
        assert symbol == "930997"
        return pd.DataFrame(
            {
                "日期": ["2024-01-02"],
                "指数代码": ["930997"],
                "开盘": [1200.0],
                "最高": [1220.0],
                "最低": [1190.0],
                "收盘": [1210.0],
                "成交量": [1000],
                "成交金额": [2000],
            }
        )


class _FakeHongKongIndexAk:
    def stock_hk_index_daily_em(self, **kwargs):
        raise RuntimeError("hk em down")

    def stock_hk_index_daily_sina(self, symbol):
        assert symbol == "HSTECH"
        return pd.DataFrame(
            {
                "date": ["2020-08-17", "2020-08-18"],
                "open": [7037.86, 7147.73],
                "high": [7117.17, 7196.01],
                "low": [7004.77, 7075.06],
                "close": [7075.03, 7196.01],
                "volume": [668079483, 897377780],
                "amount": [30808865651, 43286242318],
            }
        )


def test_ashare_index_daily_falls_back_when_em_returns_empty():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeIndexAk()

    result = provider.fetch_index_daily("000905", "2024-01-02", "2024-01-02")

    assert len(result) == 1
    assert result.iloc[0]["index_code"] == "000905"
    assert result.iloc[0]["data_source"] == "akshare_zh_sina"


def test_ashare_index_daily_falls_back_to_csindex_when_sina_is_empty():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeCsindexAk()

    result = provider.fetch_index_daily("930997", "2024-01-02", "2024-01-02")

    assert len(result) == 1
    assert result.iloc[0]["index_code"] == "930997"
    assert result.iloc[0]["data_source"] == "akshare_csindex"
    assert result.iloc[0]["close"] == 1210.0


def test_ashare_index_daily_falls_back_to_csindex_when_sina_errors():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeCsindexAfterSinaErrorAk()

    result = provider.fetch_index_daily("930997", "2024-01-02", "2024-01-02")

    assert len(result) == 1
    assert result.iloc[0]["data_source"] == "akshare_csindex"


def test_hong_kong_index_daily_falls_back_to_sina_when_em_fails():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeHongKongIndexAk()

    result = provider.fetch_index_daily("HSTECH", "2020-08-18", "2020-08-18")

    assert len(result) == 1
    assert result.iloc[0]["index_code"] == "HSTECH"
    assert result.iloc[0]["data_source"] == "akshare_hk_sina"
