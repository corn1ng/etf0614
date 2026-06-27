from pathlib import Path

import pytest

from etf_trading.research.config import load_research_candidates


def test_load_research_candidates_from_yaml(tmp_path: Path):
    config_path = tmp_path / "research.yaml"
    config_path.write_text(
        """
candidates:
  - name: balanced_breakout
    entry_ma: ma51
    trend_ma: ma120
    exit_ma: ma120
    momentum_windows: [20, 60]
    rs_rank_max: 0.30
    max_distance_from_entry_ma: 0.12
    max_recent_return_20: 0.25
    min_trade_interval_days: 10
    target_weight: 1.0
""",
        encoding="utf-8",
    )

    candidates = load_research_candidates(config_path)

    assert len(candidates) == 1
    assert candidates[0].name == "balanced_breakout"
    assert candidates[0].momentum_windows == (20, 60)
    assert candidates[0].rs_rank_max == 0.30
    assert candidates[0].target_weight == 1.0


def test_load_research_candidates_parses_trend_v1_fields(tmp_path: Path):
    config_path = tmp_path / "research.yaml"
    config_path.write_text(
        """
candidates:
  - name: etf_trend_v1_standard
    entry_ma: ma60
    trend_ma: ma60
    exit_ma: ma60
    momentum_windows: []
    skip_momentum_windows: [60, 120]
    required_ma_relations:
      - [ma20, ma60]
    slope_field: ma60_slope_20
    rs_rank_max: 0.30
    max_atr_distance_from_ma: 2.0
    trailing_atr_multiple: 3.0
    min_trade_interval_days: 10
    target_weight: 1.0
""",
        encoding="utf-8",
    )

    candidates = load_research_candidates(config_path)

    candidate = candidates[0]
    assert candidate.name == "etf_trend_v1_standard"
    assert candidate.skip_momentum_windows == (60, 120)
    assert candidate.required_ma_relations == (("ma20", "ma60"),)
    assert candidate.slope_field == "ma60_slope_20"
    assert candidate.max_atr_distance_from_ma == 2.0
    assert candidate.trailing_atr_multiple == 3.0


@pytest.mark.parametrize(
    "relations_yaml",
    [
        "ma20",
        "\n      - [ma20]",
        "\n      - [ma20, ma60, ma120]",
    ],
)
def test_load_research_candidates_rejects_malformed_required_ma_relations(
    tmp_path: Path, relations_yaml: str
):
    config_path = tmp_path / "research.yaml"
    config_path.write_text(
        f"""
candidates:
  - name: etf_trend_v1_standard
    required_ma_relations: {relations_yaml}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="required_ma_relations"):
        load_research_candidates(config_path)
