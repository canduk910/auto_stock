"""PARAM_RANGES VB 보드별 손절 키 등록 (사이클 3, 2026-05-17).

배경:
    사이클 3 — VB 보드별 손절 분리. OpenAI 자문이 `stop_loss_main` /
    `stop_loss_pre_nxt` 를 추천할 수 있게 `_validate_recommendations` 화이트리스트
    확장.

    `stop_loss_post_nxt` 는 VB POST_NXT 미사용이라 제외 — 사이클 3-B(LTV) 에서
    재검토.

신규 키 명세:
    stop_loss_main:    (-15.0, 0.0)
    stop_loss_pre_nxt: (-15.0, 0.0)

    범위는 기존 `stop_loss_rate` 와 동일 — top-level 호환성 유지.

Red 의도:
    J: PARAM_RANGES 에 새 2 키 등록 + 범위 정합성
    K: _validate_recommendations 가 새 키 추천값 통과
    L: 범위 밖 값은 무시 + WARNING 로그
"""

from __future__ import annotations

import logging


_NEW_BOARD_STOP_LOSS_KEYS = {
    "stop_loss_main": (-15.0, 0.0),
    "stop_loss_pre_nxt": (-15.0, 0.0),
}


# ---------------------------------------------------------------------------
# J. PARAM_RANGES 등록 + 범위 정합성
# ---------------------------------------------------------------------------
def test_param_ranges_includes_board_stop_loss_keys():
    """신규 2 키 모두 PARAM_RANGES 에 등록되어야 한다."""
    from src.engine.recommendation_engine import PARAM_RANGES

    for key in _NEW_BOARD_STOP_LOSS_KEYS:
        assert key in PARAM_RANGES, f"PARAM_RANGES 누락: {key}"


def test_param_ranges_board_stop_loss_bounds_match_spec():
    """신규 키 범위가 leader 명세 (-15.0, 0.0) 와 정확히 일치."""
    from src.engine.recommendation_engine import PARAM_RANGES

    for key, (lo, hi) in _NEW_BOARD_STOP_LOSS_KEYS.items():
        assert PARAM_RANGES[key] == (lo, hi), (
            f"{key}: 범위 불일치 — 명세 {(lo, hi)} vs 실제 {PARAM_RANGES[key]}"
        )
        assert lo < hi, f"{key}: invalid range ({lo}, {hi})"


# ---------------------------------------------------------------------------
# K. 정상 추천값 통과
# ---------------------------------------------------------------------------
def test_validate_recommendations_accepts_board_stop_loss_keys():
    """`stop_loss_main`=-3.0 / `stop_loss_pre_nxt`=-4.0 정상 범위 통과."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {
        "recommended_params": {
            "stop_loss_main": -3.0,
            "stop_loss_pre_nxt": -4.0,
        },
        "reasoning": "사이클 3 권고 반영",
    }
    current = {
        "stop_loss_main": -3.5,
        "stop_loss_pre_nxt": -3.5,
    }
    validated, reasoning, _w, _n, _wr = _validate_recommendations(raw, current)

    assert validated["stop_loss_main"] == -3.0
    assert validated["stop_loss_pre_nxt"] == -4.0
    assert reasoning == "사이클 3 권고 반영"


# ---------------------------------------------------------------------------
# L. 범위 밖 값은 무시 + WARNING 로그
# ---------------------------------------------------------------------------
def test_validate_recommendations_rejects_out_of_range_board_stop_loss(caplog):
    """범위 (-15.0, 0.0) 밖 값 무시 + WARNING 로그.

    - stop_loss_main = -20.0 → 하한(-15) 미달
    - stop_loss_pre_nxt = 1.0 → 상한(0) 초과
    """
    from src.engine.recommendation_engine import _validate_recommendations

    caplog.set_level(logging.WARNING, logger="src.engine.recommendation_engine")
    raw = {
        "recommended_params": {
            "stop_loss_main": -20.0,
            "stop_loss_pre_nxt": 1.0,
        },
        "reasoning": "",
    }
    current = {
        "stop_loss_main": -3.0,
        "stop_loss_pre_nxt": -3.0,
    }
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)

    assert "stop_loss_main" not in validated
    assert "stop_loss_pre_nxt" not in validated
    warning_msgs = [
        r.message for r in caplog.records
        if r.levelno == logging.WARNING and "범위 초과" in r.message
    ]
    assert len(warning_msgs) == 2, (
        f"WARNING 누락 — 실제 메시지: {warning_msgs}"
    )
