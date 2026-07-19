# Tushare 主数据源实施方案

## 目标

将 Tushare 设为 ETF 与指数数据的主来源。Tushare 出现配置、鉴权、权限、限流、网络、数据结构或接口能力问题时，明确提示用户并自动回退至 AkShare；只有两个来源均失败时任务失败。

## 全局规则

- Token 只从 `TUSHARE_TOKEN` 读取，禁止写入源码、配置、日志、测试和 Git。
- 代理地址优先读取 `TUSHARE_API_URL`，默认使用 `https://ts.gyzcloud.top/api`。
- 本地请求限制为 120 次/分钟，低于账号 150 次/分钟上限。
- Tushare 成功时不调用 AkShare，也不提示回退。
- AkShare 回退成功时状态为“完成但有警告”，并保留实际 `data_source`。
- `adjust="qfq"` 必须具备完整 `fund_adj`；禁止以未复权日线代替。
- 默认测试不访问真实服务；真实代理测试仅在设置 `RUN_TUSHARE_SMOKE=1` 后运行。

## 实施任务

1. 新建 `provider_runtime.py`：集中保存数据源配置、错误类型、Token 脱敏、`ProviderNotice`、批量告警汇总和限流器。
2. 新建 `tushare_provider.py`：通过 SDK 访问代理，支持 ETF 主列表、ETF 日线、基金净值、指数日线和交易日历。
3. 为指数目录增加可选的 `tushare_symbol`，并提供 SQLite 迁移；映射有歧义时回退，不使用前缀猜测。
4. 新建 `fallback_provider.py` 与 `factory.py`：Tushare 优先、AkShare 备用，并将每一次回退写入结构化 notice。
5. 修改命令行脚本：使用 factory；向 stderr 和批量汇总 JSON 写入已脱敏回退信息。
6. 修改 NiceGUI：同步任务显示黄色告警，后台维护任务持久化为 `warning` 状态，页面刷新后仍可见。
7. 修改 Streamlit：全部数据维护入口使用 factory，批量操作只显示一条汇总告警。
8. 新增真实代理冒烟测试并更新 README 和任务记忆；运行离线全量测试、真实测试和密钥扫描。

## 数据口径

- ETF 列表：使用 `fund_basic(market="E", status="L")` 并过滤 LOF 等非 ETF 场内基金。
- ETF 日线：使用 `fund_daily`；成交额由千元转换为元；主数据源标签为 `tushare_fund_daily`。
- ETF 前复权：日线与 `fund_adj` 按交易日一对一合并，按最新复权因子归一化 OHLC。
- ETF 净值：使用 `fund_nav`；未提供的 IOPV、溢价率保持空值。
- 指数日线：使用 `index_daily`；申万和未支持的港股指数明确标记为能力缺口后回退。
- 日历：使用 `trade_cal`，保留开市和闭市日期。

## 验收条件

- 所有应用和脚本入口均通过统一的 provider factory 构造数据源。
- 主源成功不产生 notice；回退成功必定有用户可见的告警。
- 双源失败展示双方已脱敏错误原因。
- 实际落盘数据带真实 `data_source`，告警不混入 Parquet 数据列。
- Token 不出现在 Git diff、日志、测试输出或数据库任务记录中。
- 离线完整测试通过，真实冒烟测试在显式启用后可复核。

详细的逐项测试先行步骤、文件级修改和命令保留在原实施计划：`docs/superpowers/plans/2026-07-19-tushare-primary-provider.md`。
