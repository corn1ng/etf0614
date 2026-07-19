# 统一 Tushare 指数路由设计

## 目标

所有指数行情请求都先由 Tushare 处理；仅在 Tushare 无数据、无权限、参数不支持或调用异常时，才由既有主备 Provider 回退到 AkShare。

## 设计

`TushareProvider.fetch_index_daily()` 不再按 `source_kind` 预先拒绝港股或申万目录项。它始终使用目录的 `provider_symbol`；目录未配置标准代码时，才按既有 A 股规则推导 `.SH` 或 `.SZ` 后缀。目录中的 `H30533` 明确映射为 `H30533.CSI`。

Tushare 的空表维持为空表返回。`PrimaryFallbackProvider` 已将该调用包装为 Tushare 主源和 AkShare 备用源，因此无需改变其回退或告警语义。成功数据继续保留 `tushare_index_daily`，回退数据保留 AkShare 的来源标签。

## 验证

新增单元测试证明港股目录中配置 `.CSI` 标准代码时仍会调用 Tushare；保留主源失败后调用 AkShare 的回归测试。随后运行数据源相关测试和完整测试套件。
