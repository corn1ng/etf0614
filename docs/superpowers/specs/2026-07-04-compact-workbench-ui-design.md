# ETF 工作台全站紧凑 UI 设计

研究与设计时点：2026-07-04
目标项目：`etf0614`

## 1. 背景

当前 Streamlit 工作台已经完成左侧主导航、顶部状态栏和页面二级菜单改造，但实际页面仍然偏松散。典型问题是：

- 顶部状态栏、页面标题、页面说明、二级菜单和页面内标题连续堆叠，占用首屏。
- 页面模块里重复出现 `title -> caption -> subheader -> caption -> markdown heading`，视觉层级过多。
- 市场地图等页面的核心图表需要向下滚动才能看到，影响日常使用效率。
- 各页面虽然有统一导航，但主内容区密度规则不统一，整体不够聚合。

本轮目标是全站统一收紧，让它更像每天反复使用的投资工作台，而不是长文档式页面。

## 2. 目标

1. 全站压缩顶部与主内容区的垂直空隙。
2. 移除或降级重复页面标题，让页面标题、说明和二级菜单合并成紧凑头部。
3. 让每个页面的核心图表、表格或操作区尽量进入首屏。
4. 保持现有业务逻辑、数据口径、研究计算和数据维护动作不变。
5. 用测试覆盖关键 CSS 和路由行为，避免后续回退到松散布局。

## 3. 非目标

- 不新增交易策略、指数规则或 ETF 筛选逻辑。
- 不改 SQLite、Parquet、AkShare provider 或研究 runner。
- 不引入新的前端框架。
- 不做装饰型视觉改版、营销页或复杂主题系统。
- 不为了紧凑而隐藏必要的错误提示、风险提示和耗时动作确认。

## 4. 全局布局设计

### 4.1 紧凑应用头部

当前 `main()` 中的 `render_top_status_bar()`、`st.title(page.label)`、`st.caption(page.caption)`、`render_secondary_navigation(page)` 会形成较高顶部区域。

调整后采用统一的紧凑头部：

```text
顶部状态栏：更矮，指标 padding 更小，底部 margin 更小
页面头部：小标题 + 简短说明，和二级菜单靠近排列
二级菜单：紧贴页面头部，下方只留很小间距
```

页面标题不再使用大号 `st.title()`。推荐新增 `render_page_header(page)` 或在 `navigation.py` 中提供紧凑页面头渲染函数，输出小号标题与 caption，并继续复用 `render_secondary_navigation(page)`。

### 4.2 主内容密度规则

全局 CSS 应统一收紧：

- `.block-container` 的顶部、左右和底部 padding。
- 标题、caption、markdown heading 的 margin。
- Streamlit radio、segmented control、selectbox、multiselect、alert、metric 的外边距。
- `stDataFrame`、图表容器和 expander 之间的垂直间距。

收紧不应导致文字溢出、按钮重叠或表格不可读。表格行高可保持当前紧凑值，图表高度保持稳定。

### 4.3 页面内标题策略

页面模块不再重复渲染和一级页面同名的 `st.subheader()` 与长 caption。规则如下：

- 一级页面名只出现在紧凑页面头部。
- 页面模块若只是重复当前页面定位，删除 `subheader` 和 `caption`。
- 真正的内容分区标题降级为较小 markdown heading，且只在需要区分多个核心区块时保留。
- 长说明、规则解释、历史表和低频明细进入 expander 或短提示。

## 5. 页面级调整

### 5.1 今日行动

首屏优先级：

1. 顶部状态栏。
2. 紧凑页面头和二级菜单。
3. 状态卡、当前市场提示和下一步提醒。
4. 行动摘要中的可参与指数表或今日建议。

调整点：

- 删除页面模块里的重复 `今日行动` 标题和说明。
- 状态卡保持 4 列，但压缩 metric 外边距。
- 下一步提醒只在有问题时占据明显空间；无问题时使用短成功提示。

### 5.2 市场地图

首屏优先级：

1. 指数筛选控件。
2. 当前指数状态码。
3. 图表区间和信号规则控件。
4. 指数 K 线图。

调整点：

- 删除重复 `市场地图` 标题和说明。
- `指数级买卖参考` 的长规则说明改成默认折叠，或替换为单行短提示。
- `选择指数` 标题删除，筛选控件直接出现。
- 触发条件和风险提示保持在图表前，但应压缩为更短的两列提示。
- 图表说明 caption 与图表控件靠近，不再额外撑开。

### 5.3 ETF池

首屏优先级：

1. 搜索或计算池表格。
2. 当前计算池状态。

调整点：

- 删除重复 `ETF池` 标题和说明。
- 搜索加入页保留搜索控件，计算池预览紧跟其后。
- 每日计算池页直接展示表格，不再先显示大标题。

### 5.4 研究复盘

首屏优先级：

1. 研究任务状态。
2. 当前二级视图的核心表格或图表。

调整点：

- 保留研究任务状态，但压缩其上下空隙。
- 运行研究作为二级页时，不让辅助工具或低频说明挤占总览视图。
- 排名表、对比表、ETF 复盘图表的标题只保留必要分区。

### 5.5 数据维护

首屏优先级：

1. 数据健康。
2. 一键补齐指数入口。
3. 当前二级视图内容。

调整点：

- 删除重复 `数据维护` 标题和说明。
- 数据健康页保留可执行入口，但压缩提示文字。
- 数据中心、日志与设置页避免先出现过长说明。

## 6. 代码设计

### 6.1 建议改动文件

- `src/etf_trading/ui/styles.py`
  - 增加全站紧凑 CSS。
  - 调整顶部状态栏、状态码、控件和 heading 间距。

- `src/etf_trading/ui/navigation.py`
  - 新增紧凑页面头渲染函数，或调整二级导航渲染周边结构。

- `src/etf_trading/ui/app.py`
  - 用紧凑页面头替换 `st.title(page.label)` 和 `st.caption(page.caption)`。
  - 保持页面路由和业务依赖不变。

- `src/etf_trading/ui/pages/*.py`
  - 删除重复页面标题和重复说明。
  - 保留必要内容分区标题。

- `tests/test_ui_styles.py`
  - 增加紧凑 CSS 断言。

- `tests/test_ui_navigation.py`
  - 如新增页面头函数，补充渲染行为测试。

### 6.2 接口建议

新增函数：

```python
def render_page_header(page: PageSpec) -> None:
    ...
```

该函数只负责渲染页面小标题和 caption。当前二级 section 继续由现有 `render_secondary_navigation(page)` 返回：

```python
render_page_header(page)
section = render_secondary_navigation(page)
```

若实现上保持函数简单，也可以只删除 `st.title()` 并在 `main()` 中用小号 markdown 输出页面头。

## 7. 错误处理与可用性

- 数据缺失、同步失败、研究失败提示不能被隐藏。
- 长规则说明可以折叠，但影响判断的风险提示仍需默认可见。
- 耗时动作仍需用户主动点击，不做自动执行。
- 紧凑 CSS 必须对窄屏保留换行和滚动能力。

## 8. 测试与验证

### 8.1 单元测试

- `test_ui_styles.py`
  - 断言 `.block-container` 使用更紧凑 padding。
  - 断言顶部状态栏 item padding 与 margin 被收紧。
  - 断言存在页面头、heading、caption 或控件的紧凑 CSS。

- `test_ui_navigation.py`
  - 若新增 `render_page_header()`，用 monkeypatch 验证它渲染页面标题和说明，且不依赖业务数据。

### 8.2 手工验收

桌面宽屏：

- 顶部状态栏、页面头和二级菜单总高度明显降低。
- 市场地图的指数筛选、状态码、图表控件和图表顶部能更早进入首屏。
- 今日行动、ETF池、研究复盘、数据维护不再出现重复大标题。
- 页面没有控件重叠、文字被截断或表格异常挤压。

窄屏：

- 左侧导航仍可折叠。
- 顶部状态栏自动换列。
- 表格和图表仍可横向或纵向滚动。

### 8.3 验证命令

```powershell
python -m pytest tests/test_ui_styles.py tests/test_ui_navigation.py -v
python -m pytest
```

如环境允许，再运行：

```powershell
python -m streamlit run app.py
```

## 9. 验收标准

1. 全站不再使用大号 `st.title(page.label)` 作为页面头。
2. 各页面模块不再重复渲染与一级页面同名的大标题和长说明。
3. 市场地图的核心图表入口明显上移。
4. 顶部状态栏和二级菜单之间的空隙缩小。
5. 现有业务功能和页面路由保持不变。
6. UI 样式测试覆盖紧凑布局关键 CSS。
