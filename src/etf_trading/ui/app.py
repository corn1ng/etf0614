"""Streamlit multi-tab ETF workbench."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from etf_trading.backtest.engine import BacktestEngine
from etf_trading.data.indexes import DEFAULT_INDEXES, INDEX_HISTORY_AUTO_START, get_index_definition, index_options
from etf_trading.data.initialization import InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.report.daily_report import DailyAdviceReport
from etf_trading.strategy.features import add_technical_features
from etf_trading.strategy.models import StrategySignal
from etf_trading.strategy.trend import TrendStrategy
from etf_trading.ui.chart_renderer import build_lightweight_chart_payload
from etf_trading.universe.classification import CATEGORIES, is_hk_cross_market

try:
    from streamlit_lightweight_charts import renderLightweightCharts
except Exception:  # pragma: no cover - import fallback for non-UI environments
    renderLightweightCharts = None


DB_PATH = Path("database/etf_system.sqlite")
PARQUET_ROOT = Path("data/parquet")
SAMPLE_CATEGORIES = ["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药", "商品", "债券"]


def main() -> None:
    st.set_page_config(page_title="ETF 交易指引工作台", layout="wide")
    st.title("A 股 ETF 交易指引工作台")
    st.caption("本系统只输出仓位比例和交易指引，不自动下单。")

    store = _store()
    parquet_store = _parquet()
    service = InitializationService(store=store, provider=None, parquet_store=parquet_store)

    tabs = st.tabs(["ETF 池", "指数观察", "行情 K 线", "每日建议", "回测", "数据中心", "日志与设置"])
    with tabs[0]:
        _tab_universe(store)
    with tabs[1]:
        _tab_index_watch(parquet_store)
    with tabs[2]:
        _tab_chart(store, parquet_store)
    with tabs[3]:
        _tab_advice(store, parquet_store)
    with tabs[4]:
        _tab_backtest(store, parquet_store)
    with tabs[5]:
        _tab_data_center(store, parquet_store)
    with tabs[6]:
        _tab_settings(store, service)


@st.cache_resource
def _store() -> SQLiteStore:
    store = SQLiteStore(DB_PATH)
    store.initialize_schema()
    return store


@st.cache_resource
def _parquet() -> ParquetStore:
    return ParquetStore(PARQUET_ROOT)


def _provider() -> AkShareProvider:
    return AkShareProvider()


def _tab_universe(store: SQLiteStore) -> None:
    st.subheader("ETF 池")
    master = store.list_etf_master()
    if master.empty:
        st.info("尚未初始化 ETF 主列表。请到“数据中心”执行轻量初始化。")
        return

    col1, col2, col3 = st.columns([2, 1, 1])
    query = col1.text_input("搜索代码或名称")
    category = col2.selectbox("分类", ["全部"] + CATEGORIES)
    only_hk = col3.checkbox("只看港股跨境 ETF")

    view = master.copy()
    if query:
        view = view[view["etf_code"].astype(str).str.contains(query) | view["name"].fillna("").str.contains(query)]
    if category != "全部":
        view = view[view["category"] == category]
    if only_hk:
        view = view[view["category"].map(is_hk_cross_market)]

    st.dataframe(view[["etf_code", "name", "exchange", "category", "amount", "latest_price", "is_active"]], use_container_width=True, hide_index=True)

    st.markdown("### 加入每日计算池")
    selected = st.selectbox("ETF", view["etf_code"].tolist() if not view.empty else [])
    if selected:
        row = master[master["etf_code"] == selected].iloc[0]
        selected_category = st.selectbox("分类修正", CATEGORIES, index=CATEGORIES.index(row["category"]) if row["category"] in CATEGORIES else 0)
        allow_buy = st.checkbox("允许买入", value=True)
        enabled = st.checkbox("纳入每日计算", value=True)
        if st.button("保存到每日计算池"):
            store.set_watchlist(selected, enabled=enabled, allow_buy=allow_buy, category=selected_category)
            st.success(f"{selected} 已保存")

    st.markdown("### 当前每日计算池")
    st.dataframe(store.list_watchlist(), use_container_width=True, hide_index=True)


def _tab_chart(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("行情 K 线")
    etf_code = _select_etf(store, "chart_etf")
    if not etf_code:
        return
    prices = parquet_store.read_prices(etf_code)
    if prices.empty:
        st.warning("本地尚无该 ETF 历史行情，请先到“数据中心”初始化历史。")
        return
    prices = add_technical_features(prices)
    recent = prices.tail(st.slider("显示最近交易日数量", 120, 1200, 500))
    master = store.list_etf_master()
    meta = master[master["etf_code"] == etf_code]
    if not meta.empty:
        row = meta.iloc[0]
        tags = [f"分类：{row['category']}", f"交易所：{row['exchange']}"]
        if is_hk_cross_market(row["category"]):
            tags.extend(["底层市场：港股", "跨境类型：A股上市人民币交易", "风险：关注折溢价和底层市场休市"])
        st.info(" ｜ ".join(tags))

    payload = build_lightweight_chart_payload(recent)
    if renderLightweightCharts is None:
        st.json(payload)
    else:
        renderLightweightCharts(payload, key=f"chart-{etf_code}")


def _tab_index_watch(parquet_store: ParquetStore) -> None:
    st.subheader("指数观察")
    st.caption("指数用于判断底层市场趋势；ETF 是后续交易载体。这里不输出具体买卖建议。")
    selected = st.selectbox("选择指数", index_options(), key="index_watch")
    index_code = selected.split()[0]
    definition = get_index_definition(index_code)
    st.info(f"指数：{definition.name} ｜ 市场：{definition.market} ｜ 分类：{definition.category}")

    prices = parquet_store.read_index_prices(index_code)
    if prices.empty:
        st.warning("本地尚无该指数历史数据。请在“数据中心”拉取指数历史。")
        return

    featured = add_technical_features(prices.rename(columns={"index_code": "etf_code"}))
    recent = featured.tail(st.slider("显示最近指数交易日数量", 120, 2000, min(800, len(featured)), key="index_days"))
    payload = build_lightweight_chart_payload(recent)
    if renderLightweightCharts is None:
        st.json(payload)
    else:
        renderLightweightCharts(payload, key=f"index-chart-{index_code}")

    last = featured.iloc[-1]
    cols = st.columns(5)
    cols[0].metric("最新收盘", f"{last['close']:.2f}")
    cols[1].metric("MA51", _fmt_optional(last.get("ma51")))
    cols[2].metric("MA120", _fmt_optional(last.get("ma120")))
    cols[3].metric("MA250", _fmt_optional(last.get("ma250")))
    cols[4].metric("MA850", _fmt_optional(last.get("ma850")))


def _tab_advice(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("每日建议")
    watchlist = store.list_watchlist()
    if watchlist.empty:
        st.info("每日计算池为空。请先在“ETF 池”中勾选 ETF。")
        return
    strategy = TrendStrategy()
    signals: list[StrategySignal] = []
    for row in watchlist.itertuples(index=False):
        if not row.enabled:
            continue
        prices = parquet_store.read_prices(row.etf_code)
        if prices.empty:
            signals.append(
                StrategySignal(
                    etf_code=row.etf_code,
                    trade_date=pd.Timestamp.today().normalize(),
                    action="FORBID",
                    target_weight=0.0,
                    reason="历史行情未初始化",
                    trigger_rules=["missing_history"],
                    risk_tags=["数据缺失"],
                )
            )
            continue
        featured = add_technical_features(prices).iloc[-1].copy()
        featured["etf_code"] = row.etf_code
        featured["category"] = row.category
        featured["relative_strength_rank"] = 0.2
        featured["premium_rate"] = 0.0
        featured["data_quality_score"] = 1.0
        featured["underlying_market_open"] = True
        signal = strategy.evaluate(featured, market_risk_on=True)
        if is_hk_cross_market(row.category):
            signal.risk_tags.append("港股跨境ETF")
        signals.append(signal)

    report = DailyAdviceReport().render(pd.Timestamp.today(), "震荡", signals)
    st.markdown(report)


def _tab_backtest(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("回测")
    etf_code = _select_etf(store, "backtest_etf")
    if not etf_code:
        return
    prices = parquet_store.read_prices(etf_code)
    if prices.empty:
        st.warning("本地尚无该 ETF 历史行情，请先初始化。")
        return
    category = _category_for(store, etf_code)
    target_weight = st.slider("测试目标仓位", 0.01, 0.15, 0.06, 0.01)
    start = pd.Timestamp(prices["trade_date"].min())
    first_signal_date = st.date_input("首个买入信号日期", value=start.date())
    if st.button("运行单 ETF 回测"):
        signal = StrategySignal(
            etf_code=etf_code,
            trade_date=pd.Timestamp(first_signal_date),
            action="BUY",
            target_weight=target_weight,
            reason="手动回测信号",
            trigger_rules=["manual_backtest"],
        )
        result = BacktestEngine().run_single_etf(etf_code, prices, [signal], category=category)
        st.metric("总收益", f"{result.metrics.get('total_return', 0) * 100:.2f}%")
        st.metric("最大回撤", f"{result.metrics.get('max_drawdown', 0) * 100:.2f}%")
        st.metric("港股跨境暴露", f"{result.metrics.get('max_hk_cross_market_exposure', 0) * 100:.2f}%")
        st.line_chart(result.nav.set_index("trade_date")["nav"])
        st.dataframe(pd.DataFrame(result.trades), use_container_width=True)


def _tab_data_center(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("数据中心")
    st.write("初始化采用“轻量主列表 -> 样本 ETF -> 用户选择池/全市场批量”的顺序。")
    if st.button("轻量初始化：拉取全量 A 股 ETF 列表"):
        provider = _provider()
        service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
        with st.spinner("正在拉取 ETF 主列表..."):
            try:
                master = service.initialize_master()
            except Exception as exc:  # noqa: BLE001 - UI should surface provider errors clearly
                st.error(str(exc))
            else:
                st.success(f"已写入 {len(master)} 只 ETF")

    if st.button("选择样本 ETF"):
        samples = InitializationService(store).select_sample_etfs(SAMPLE_CATEGORIES)
        st.dataframe(samples[["etf_code", "name", "category", "amount"]], use_container_width=True, hide_index=True)

    st.markdown("### 单只历史初始化")
    etf_code = _select_etf(store, "init_etf")
    col1, col2 = st.columns(2)
    start = col1.date_input("开始日期", value=date.today() - timedelta(days=365 * 5))
    end = col2.date_input("结束日期", value=date.today())
    if etf_code and st.button("拉取并保存历史行情"):
        provider = _provider()
        service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
        with st.spinner(f"正在拉取 {etf_code} 历史行情..."):
            try:
                frame = service.fetch_and_store_history(etf_code, start, end)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
            else:
                st.success(f"保存 {len(frame)} 行历史行情")

    st.markdown("### 指数历史初始化")
    selected_index = st.selectbox("指数", index_options(), key="init_index")
    index_code = selected_index.split()[0]
    st.caption(f"开始日期自动使用 {INDEX_HISTORY_AUTO_START.isoformat()} 请求，最终以数据源返回的最早交易日为准。")
    index_end = st.date_input("指数结束日期", value=date.today(), key="index_end")
    if st.button("拉取并保存指数历史"):
        provider = _provider()
        with st.spinner(f"正在拉取 {selected_index} 历史行情..."):
            try:
                frame = provider.fetch_index_daily(index_code, INDEX_HISTORY_AUTO_START, index_end)
                featured = add_technical_features(frame.rename(columns={"index_code": "etf_code"})).rename(columns={"etf_code": "index_code"})
                parquet_store.write_index_prices(index_code, featured)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
            else:
                if featured.empty:
                    st.warning("数据源没有返回指数历史行情。")
                else:
                    first_date = pd.Timestamp(featured["trade_date"].min()).date()
                    st.success(f"保存 {len(featured)} 行指数历史行情，起始交易日 {first_date}")

    st.markdown("### 一键初始化/补齐全部指数")
    st.caption("逐个检查本地指数数据：不存在则全量拉取，已存在则从最后交易日之后补到结束日期。单个指数失败不会中断其他指数。")
    if st.button("一键初始化/补齐全部指数"):
        provider = _provider()
        service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
        with st.spinner("正在检查并补齐全部指数历史..."):
            summary = service.ensure_all_index_history(index_end)
        st.dataframe(summary, use_container_width=True, hide_index=True)
        failed = summary[summary["status"] == "FAILED"] if not summary.empty else summary
        if failed is not None and not failed.empty:
            st.warning(f"{len(failed)} 个指数补齐失败，请查看表格中的 error_message。")
        else:
            st.success("全部指数检查完成。")

    st.markdown("### 每日计算池批量任务")
    if st.button("为每日计算池创建历史初始化任务"):
        count = InitializationService(store).create_history_jobs_for_watchlist()
        st.success(f"已创建 {count} 个历史任务")


def _tab_settings(store: SQLiteStore, service: InitializationService) -> None:
    st.subheader("日志与设置")
    st.write("港股跨境 ETF 关键词和仓位上限当前由配置文件控制：`configs/strategy.yaml`、`configs/risk.yaml`。")
    with store.connect() as conn:
        jobs = pd.read_sql_query("SELECT * FROM data_fetch_job ORDER BY job_id DESC LIMIT 100", conn)
        state = pd.read_sql_query("SELECT * FROM data_update_state ORDER BY updated_at DESC LIMIT 100", conn)
        quality = pd.read_sql_query("SELECT * FROM data_quality_log ORDER BY log_id DESC LIMIT 100", conn)
    st.markdown("### 更新状态")
    st.dataframe(state, use_container_width=True, hide_index=True)
    st.markdown("### 任务日志")
    st.dataframe(jobs, use_container_width=True, hide_index=True)
    st.markdown("### 数据质量日志")
    st.dataframe(quality, use_container_width=True, hide_index=True)


def _select_etf(store: SQLiteStore, key: str) -> str | None:
    master = store.list_etf_master()
    if master.empty:
        st.info("尚未初始化 ETF 主列表。")
        return None
    labels = [f"{r.etf_code} {r.name}" for r in master.itertuples(index=False)]
    selected = st.selectbox("选择 ETF", labels, key=key)
    return selected.split()[0] if selected else None


def _category_for(store: SQLiteStore, etf_code: str) -> str:
    master = store.list_etf_master()
    row = master[master["etf_code"] == etf_code]
    if row.empty:
        return "A股主题"
    return str(row.iloc[0]["category"])


def _fmt_optional(value: object) -> str:
    if pd.isna(value):
        return "不足"
    return f"{float(value):.2f}"


if __name__ == "__main__":
    main()
