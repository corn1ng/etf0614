from etf_trading.universe.classification import classify_etf


def test_classifies_hong_kong_cross_market_etfs_by_name_and_index():
    assert classify_etf("513130", "恒生科技ETF", "恒生科技指数") == "港股科技"
    assert classify_etf("513060", "恒生医疗ETF", "恒生医疗保健指数") == "港股医药"
    assert classify_etf("159920", "恒生ETF", "恒生指数") == "港股宽基"
    assert classify_etf("513690", "港股通红利ETF", "港股通高股息指数") == "港股高股息/红利"


def test_classifies_common_a_share_and_defensive_etfs():
    assert classify_etf("510300", "沪深300ETF", "沪深300指数") == "A股宽基"
    assert classify_etf("512010", "医药ETF", "中证医药指数") == "A股行业"
    assert classify_etf("518880", "黄金ETF", "黄金现货实盘合约") == "商品"
    assert classify_etf("511010", "国债ETF", "上证5年期国债指数") == "债券"
    assert classify_etf("511990", "华宝添益ETF", "货币市场基金") == "货币/现金替代"
    assert classify_etf("159003", "招商快线ETF", "") == "货币/现金替代"
