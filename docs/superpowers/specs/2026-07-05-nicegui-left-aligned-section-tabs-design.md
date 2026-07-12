# NiceGUI 二级切换左对齐设计

日期：2026-07-05

## 背景

NiceGUI 工作台当前把页面二级切换按钮放在页面标题行最右侧。宽屏下用户从左侧主导航进入页面后，需要把鼠标移动到主内容区右端才能切换 `市场总览`、`指数买卖参考`、`指数K线` 等视图。这个路径过长，且二级切换与页面内容起点的视觉关系不够紧密。

## 目标

全站 NiceGUI 页面统一把二级切换按钮移动到页面标题和说明下方，并左对齐到主内容起点。按钮样式、选中态、路由和每个页面的 section 配置保持不变。

## 设计

`layout._render_page_header` 改为纵向页面头：

- 第一行只放页面标题和说明。
- 第二行放 section tab 列表，使用 `workbench-section-tabs` 专用样式。
- section tab 行左对齐、允许换行，避免窄屏或 section 较多时挤压。
- 不改变 `quote(item, safe="")` 生成的 section 路由。

`theme.WORKBENCH_CSS` 增加页面头和 section tab 行规则：

- `.workbench-page-header` 控制标题区和 tab 行的垂直间距。
- `.workbench-section-tabs` 固定左对齐、换行和最小高度。
- 保留现有 `.workbench-section-tab` 按钮尺寸和选中态。

## 验收

- 所有 NiceGUI 页面二级切换都出现在标题说明下方左侧。
- 右上角不再出现页面级 section 切换按钮组。
- section 路由、选中态和已有页面内容不变。
- `pytest tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -v` 通过。
