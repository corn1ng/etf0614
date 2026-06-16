"""ETF category rules.

The first release focuses on ETFs traded through A-share accounts. Hong Kong
exposure is therefore represented by mainland-listed cross-market ETFs rather
than HKEX-listed products.
"""

from __future__ import annotations

from dataclasses import dataclass


CATEGORIES = [
    "A股宽基",
    "A股行业",
    "A股主题",
    "港股宽基",
    "港股科技",
    "港股医药",
    "港股高股息/红利",
    "债券",
    "商品",
    "货币/现金替代",
]


@dataclass(frozen=True)
class CategoryRule:
    category: str
    keywords: tuple[str, ...]
    require_cross_market_context: bool = False


HK_CONTEXT = ("港股", "恒生", "H股", "中概", "中国企业")

RULES: tuple[CategoryRule, ...] = (
    CategoryRule("港股高股息/红利", ("港股通红利", "恒生高股息", "高股息", "红利"), True),
    CategoryRule("港股科技", ("恒生科技", "港股科技", "中概互联", "互联网"), True),
    CategoryRule("港股医药", ("港股医药", "恒生医疗", "医疗保健"), True),
    CategoryRule("港股宽基", ("恒生指数", "恒生中国企业", "H股", "恒生ETF", "恒生"), True),
    CategoryRule("债券", ("债", "国开", "政金", "信用", "可转债")),
    CategoryRule("商品", ("黄金", "豆粕", "有色", "能源化工", "商品", "原油")),
    CategoryRule("货币/现金替代", ("货币", "添益", "现金", "保证金", "快线", "快钱")),
    CategoryRule("A股宽基", ("沪深300", "中证500", "中证1000", "上证50", "创业板", "科创50", "A500")),
    CategoryRule("A股行业", ("医药", "医疗", "消费", "银行", "证券", "金融", "芯片", "半导体", "新能源", "军工", "传媒")),
)


def classify_etf(etf_code: str, name: str | None, tracking_index: str | None = None) -> str:
    """Classify an ETF into the system's first-release category set.

    The rule order is intentional: Hong Kong cross-market categories are
    matched before generic A-share industry terms so names such as "恒生医疗ETF"
    are not classified as ordinary A-share healthcare ETFs.
    """

    text = f"{etf_code or ''} {name or ''} {tracking_index or ''}"
    has_hk_context = any(keyword in text for keyword in HK_CONTEXT)

    for rule in RULES:
        if rule.require_cross_market_context and not has_hk_context:
            continue
        if any(keyword in text for keyword in rule.keywords):
            return rule.category

    return "A股主题"


def is_hk_cross_market(category: str) -> bool:
    return category.startswith("港股")
