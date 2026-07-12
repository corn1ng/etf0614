from datetime import date

import pytest

from etf_trading.data.index_catalog import default_index_catalog, load_baseline_evidence, load_index_catalog


def test_default_catalog_has_target_pool_boundaries():
    entries = default_index_catalog()

    assert len(entries) == 210
    assert sum(entry.pool == "core" for entry in entries) == 100
    assert sum(entry.pool == "research" for entry in entries) == 80
    assert sum(entry.pool == "reserve" for entry in entries) == 30
    assert {entry.market for entry in entries} == {"A股", "港股"}
    assert all(entry.baseline_source in {"official_methodology", "official_factsheet", "unverified"} for entry in entries)
    assert all(
        isinstance(entry.index_base_date, date)
        for entry in entries
        if entry.baseline_source != "unverified"
    )


def test_catalog_rejects_duplicate_codes_and_missing_base_date(tmp_path):
    path = tmp_path / "index_universe.yaml"
    path.write_text(
        "entries:\n"
        "  - index_code: '000300'\n"
        "    name: 沪深300\n"
        "    market: A股\n"
        "    category_level_1: 宽基\n"
        "    category_level_2: 大盘\n"
        "    index_type: 宽基\n"
        "    pool: core\n"
        "    source_kind: csi\n"
        "    provider_symbol: '000300'\n"
        "  - index_code: '000300'\n"
        "    name: 重复\n"
        "    market: A股\n"
        "    category_level_1: 宽基\n"
        "    category_level_2: 大盘\n"
        "    index_type: 宽基\n"
        "    pool: core\n"
        "    source_kind: csi\n"
        "    provider_symbol: '000300'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate index_code"):
        load_index_catalog(path)


def test_catalog_accepts_unverified_baseline_without_claiming_history_complete(tmp_path):
    path = tmp_path / "index_universe.yaml"
    path.write_text(
        "entries:\n"
        "  - index_code: '931574'\n"
        "    name: 中证香港科技\n"
        "    market: 港股\n"
        "    category_level_1: 港股行业\n"
        "    category_level_2: 科技\n"
        "    index_type: 行业\n"
        "    pool: research\n"
        "    source_kind: csi\n"
        "    provider_symbol: '931574'\n"
        "    baseline_source: unverified\n",
        encoding="utf-8",
    )

    entry = load_index_catalog(path)[0]

    assert entry.index_base_date is None
    assert entry.baseline_source == "unverified"


def test_catalog_evidence_overlay_updates_only_named_index(tmp_path):
    overlay = tmp_path / "index_baseline_evidence.yaml"
    overlay.write_text(
        "evidence:\n"
        "  '000300':\n"
        "    reference_date: '2004-12-31'\n"
        "    source: official_api\n"
        "    kind: official_base_date\n"
        "    source_name: 中证指数官方基础信息\n"
        "    source_url: https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/000300\n"
        "    checked_at: '2026-07-12'\n",
        encoding="utf-8",
    )

    entries = load_index_catalog(evidence_path=overlay)
    by_code = {entry.index_code: entry for entry in entries}

    assert by_code["000300"].index_base_date == date(2004, 12, 31)
    assert by_code["000300"].baseline_source == "official_api"
    assert by_code["000300"].baseline_evidence_kind == "official_base_date"
    assert by_code["000905"].baseline_source == "unverified"


@pytest.mark.parametrize(
    ("source", "kind", "reference_date"),
    [
        ("official_api", "unresolved", None),
        ("official_api", "publication_date", "2004-12-31"),
        ("third_party_reference", "official_base_date", "2004-12-31"),
        ("official_api", "third_party_base_date", "2004-12-31"),
        ("official_api", "unresolved", "2004-12-31"),
        ("unverified", "third_party_base_date", "2004-12-31"),
        ("third_party_publication", "third_party_base_date", "2004-12-31"),
        ("third_party_reference", "unresolved", "2004-12-31"),
    ],
)
def test_baseline_evidence_rejects_incompatible_source_kind_or_missing_date(tmp_path, source, kind, reference_date):
    evidence = tmp_path / "index_baseline_evidence.yaml"
    reference_line = f"    reference_date: '{reference_date}'\n" if reference_date else ""
    evidence.write_text(
        "evidence:\n"
        "  '000300':\n"
        f"{reference_line}"
        f"    source: {source}\n"
        f"    kind: {kind}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_baseline_evidence(evidence)
