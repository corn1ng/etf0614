from datetime import date

import pandas as pd
import yaml

from etf_trading.data.baseline_evidence import (
    CSINDEX_BASIC_INFO_URL,
    BaselineEvidenceResolver,
    write_baseline_evidence,
)
from etf_trading.data.index_catalog import IndexCatalogEntry


def _entry(index_code: str, name: str, *, source_kind: str, aliases: tuple[str, ...] = ()) -> IndexCatalogEntry:
    return IndexCatalogEntry(
        index_code=index_code,
        name=name,
        market="A股",
        category_level_1="宽基",
        category_level_2="大盘",
        index_type="宽基",
        pool="core",
        index_base_date=None,
        baseline_source="unverified",
        source_kind=source_kind,  # type: ignore[arg-type]
        provider_symbol=index_code,
        aliases=aliases,
    )


def _fake_http_get(responses: dict[str, object], calls: list[str] | None = None):
    def get(url: str):
        if calls is not None:
            calls.append(url)
        response = responses.get(url)
        if isinstance(response, Exception):
            raise response
        return response

    return get


def test_resolver_prefers_matching_csindex_basic_date_over_third_party_publication():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get(
            {
                CSINDEX_BASIC_INFO_URL.format(index_code="000300"):
                    {"code": "200", "data": {"indexCode": "000300", "basicDate": "2004-12-31"}},
            }
        ),
        third_party_index_list=pd.DataFrame(
            [{"index_code": "000300", "display_name": "沪深300", "publish_date": "2005-04-08"}]
        ),
    )

    result = resolver.collect([_entry("000300", "沪深300", source_kind="csi")], as_of=date(2026, 7, 12))

    row = result.iloc[0]
    assert row["evidence_status"] == "OFFICIAL"
    assert row["reference_date"] == "2004-12-31"
    assert row["baseline_source"] == "official_api"
    assert row["baseline_evidence_kind"] == "official_base_date"


def test_resolver_records_joinquant_publication_only_when_official_api_has_no_basic_date():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get({}),
        third_party_index_list=pd.DataFrame(
            [{"index_code": "000905", "display_name": "中证500", "publish_date": "2007-01-15"}]
        ),
    )

    result = resolver.collect([_entry("000905", "中证500", source_kind="csi")], as_of=date(2026, 7, 12))

    row = result.iloc[0]
    assert row["evidence_status"] == "THIRD_PARTY_PUBLICATION"
    assert row["reference_date"] == "2007-01-15"
    assert row["baseline_evidence_kind"] == "publication_date"
    assert row["baseline_evidence_name"] == "聚宽"
    assert row["detail"] == "第三方仅提供发布日期，不能视为官方基日"


def test_resolver_rejects_csindex_response_with_another_index_code():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get(
            {
                CSINDEX_BASIC_INFO_URL.format(index_code="000300"):
                    {"code": "200", "data": {"indexCode": "000905", "basicDate": "2004-12-31"}},
            }
        ),
        third_party_index_list=pd.DataFrame(),
    )

    row = resolver.collect([_entry("000300", "沪深300", source_kind="csi")], date(2026, 7, 12)).iloc[0]

    assert row["evidence_status"] == "UNRESOLVED"
    assert "代码不一致" in row["detail"]


def test_resolver_accepts_joinquant_publication_when_normalized_alias_matches():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get({}),
        third_party_index_list=pd.DataFrame(
            [{"index_code": "000905", "display_name": "中证 小盘500", "publish_date": "2007-01-15"}]
        ),
    )

    row = resolver.collect(
        [_entry("000905", "中证500", source_kind="csi", aliases=("中证小盘500",))],
        date(2026, 7, 12),
    ).iloc[0]

    assert row["evidence_status"] == "THIRD_PARTY_PUBLICATION"


def test_resolver_does_not_use_official_api_for_non_csi_non_h_entries():
    calls: list[str] = []
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get({}, calls),
        third_party_index_list=pd.DataFrame(
            [{"index_code": "801010", "display_name": "农林牧渔", "publish_date": "2000-01-04"}]
        ),
    )

    row = resolver.collect([_entry("801010", "农林牧渔", source_kind="shenwan")], date(2026, 7, 12)).iloc[0]

    assert row["evidence_status"] == "THIRD_PARTY_PUBLICATION"
    assert calls == []


def test_resolver_keeps_batch_running_for_rejected_official_responses():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get(
            {
                CSINDEX_BASIC_INFO_URL.format(index_code="000300"): RuntimeError("offline"),
                CSINDEX_BASIC_INFO_URL.format(index_code="000905"):
                    {"code": "500", "data": {"indexCode": "000905", "basicDate": "2007-01-15"}},
                CSINDEX_BASIC_INFO_URL.format(index_code="000852"):
                    {"code": "200", "data": {"indexCode": "000852", "basicDate": "not-a-date"}},
            }
        ),
        third_party_index_list=pd.DataFrame(),
    )

    result = resolver.collect(
        [
            _entry("000300", "沪深300", source_kind="csi"),
            _entry("000905", "中证500", source_kind="csi"),
            _entry("000852", "中证1000", source_kind="csi"),
        ],
        date(2026, 7, 12),
    )

    assert result["evidence_status"].tolist() == ["UNRESOLVED", "UNRESOLVED", "UNRESOLVED"]
    assert result["detail"].map(bool).all()


def test_resolver_returns_documented_columns_for_empty_entries():
    resolver = BaselineEvidenceResolver(http_get=_fake_http_get({}), third_party_index_list=pd.DataFrame())

    result = resolver.collect([], date(2026, 7, 12))

    assert result.columns.tolist() == [
        "index_code",
        "evidence_status",
        "reference_date",
        "baseline_source",
        "baseline_evidence_kind",
        "baseline_evidence_name",
        "baseline_evidence_url",
        "checked_at",
        "detail",
    ]


def test_resolver_treats_malformed_third_party_response_as_unresolved():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get(
            {"https://www.joinquant.com/data/dict/indexData": {"data": {"index_code": "000300"}}}
        )
    )

    row = resolver.collect([_entry("801010", "农林牧渔", source_kind="shenwan")], date(2026, 7, 12)).iloc[0]

    assert row["evidence_status"] == "UNRESOLVED"


def test_write_baseline_evidence_writes_trusted_rows_and_preserves_existing_official_record(tmp_path):
    path = tmp_path / "index_baseline_evidence.yaml"
    path.write_text(
        "evidence:\n"
        "  '000300':\n"
        "    reference_date: '2004-12-31'\n"
        "    source: official_api\n"
        "    kind: official_base_date\n"
        "    source_name: 中证指数官方基础信息\n"
        "    source_url: https://example.test/000300\n"
        "    checked_at: '2026-07-11'\n"
        "    detail: 既有官方记录\n",
        encoding="utf-8",
    )
    frame = pd.DataFrame(
        [
            {
                "index_code": "000300",
                "evidence_status": "UNRESOLVED",
                "reference_date": None,
                "baseline_source": "unverified",
                "baseline_evidence_kind": "unresolved",
                "baseline_evidence_name": "",
                "baseline_evidence_url": "",
                "checked_at": "2026-07-12",
                "detail": "代码不一致",
            },
            {
                "index_code": "000905",
                "evidence_status": "THIRD_PARTY_PUBLICATION",
                "reference_date": date(2007, 1, 15),
                "baseline_source": "third_party_publication",
                "baseline_evidence_kind": "publication_date",
                "baseline_evidence_name": "聚宽",
                "baseline_evidence_url": "https://www.joinquant.com/data/dict/indexData",
                "checked_at": date(2026, 7, 12),
                "detail": "第三方仅提供发布日期，不能视为官方基日",
            },
            {
                "index_code": "000852",
                "evidence_status": "IGNORED",
                "reference_date": "2006-01-01",
                "baseline_source": "unverified",
                "baseline_evidence_kind": "unresolved",
                "baseline_evidence_name": "",
                "baseline_evidence_url": "",
                "checked_at": "2026-07-12",
                "detail": "",
            },
        ]
    )

    write_baseline_evidence(path, frame)

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(saved["evidence"]) == ["000300", "000905"]
    assert saved["evidence"]["000300"]["detail"] == "既有官方记录"
    assert saved["evidence"]["000905"] == {
        "reference_date": "2007-01-15",
        "source": "third_party_publication",
        "kind": "publication_date",
        "source_name": "聚宽",
        "source_url": "https://www.joinquant.com/data/dict/indexData",
        "checked_at": "2026-07-12",
        "detail": "第三方仅提供发布日期，不能视为官方基日",
    }


def test_write_baseline_evidence_serializes_pandas_timestamps_as_dates(tmp_path):
    path = tmp_path / "index_baseline_evidence.yaml"
    frame = pd.DataFrame(
        [
            {
                "index_code": "000300",
                "evidence_status": "OFFICIAL",
                "reference_date": pd.Timestamp("2004-12-31 00:00:00"),
                "baseline_source": "official_api",
                "baseline_evidence_kind": "official_base_date",
                "baseline_evidence_name": "中证指数官方基础信息",
                "baseline_evidence_url": "https://example.test/000300",
                "checked_at": pd.Timestamp("2026-07-12 13:00:00"),
                "detail": "",
            }
        ]
    )

    write_baseline_evidence(path, frame)

    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["evidence"]["000300"]["reference_date"] == "2004-12-31"
    assert saved["evidence"]["000300"]["checked_at"] == "2026-07-12"
