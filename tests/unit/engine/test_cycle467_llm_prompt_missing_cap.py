"""cycle467 — AI 매수평가 프롬프트의 「결측 3개면 50 상한」 제거 + 스윙 조회 전략의 결측 안내.

배경(주간 자문 2026-10-15 §4ⓓ · D5, 사용자 결정 2026-10-16 「실행」):
SYSTEM_PROMPT 의 「결측 필드가 3개 이상이면 score 는 50 을 넘기지 않는다」 가 cycle445 절
「없다는 사실을 감점 사유로 쓰지 마라 · 70 이상도 매겨도 된다」 와 정면으로 부딪혀 점수가
41~50 에 몰리고 통과가 0 건이었다. 운영 실측(llm_buy_evaluations, 10-16 조회) — 스윙 조회로
09:0x 에 주문하는 kojiro 9건 중 8건 · donchian 4건 중 3건이 누적거래량·거래량비·시가·갭
네 값이 전부 비어 있었다(틱이 아직 쌓이지 않은 시점). 나머지 1건씩은 값이 있었으므로 키를
빼지 않고(정보 손실), 「비어 있는 것이 정상 — 위험 신호가 아니다」 를 전략 블록에 싣는다.

VB·LTV user 메시지는 byte 동일이어야 한다(`test_cycle297_llm_strategy_context.py` G1-6).
"""
from __future__ import annotations

import importlib
import json

import pytest


def _lf():
    return importlib.import_module("src.engine.llm_features")


SWING_POLL = ("donchian_swing", "kojiro", "etf_trend", "ndx2x_riskoff")
TICK_DRIVEN = ("volatility_breakout", "long_tail_volatility", "momentum",
               "bull_flag_breakout", "vcp_breakout")


def _user_obj(sid: str) -> dict:
    msgs = _lf().build_messages({"strategy": sid, "board": "main"}, {}, [])
    content = msgs[1]["content"]
    return json.loads(content[content.index("{"):])


def test_t1_cap_sentence_removed() -> None:
    sp = _lf().SYSTEM_PROMPT
    assert "50 을 넘기지 않는다" not in sp
    assert "결측 수 자체를 점수 상한으로 쓰지는 마라" in sp


def test_t2_cycle445_section_kept() -> None:
    """양성 대조군 — 고친 것은 상한 문장 하나다. cycle445 절은 그대로 남는다."""
    sp = _lf().SYSTEM_PROMPT
    assert "## 데이터 범위와 점수 분포 (cycle445)" in sp
    assert "70점 이상을 매겨도 된다" in sp


@pytest.mark.parametrize("sid", SWING_POLL)
def test_t3_swing_poll_has_data_timing_note(sid: str) -> None:
    note = _user_obj(sid)["strategy"].get("data_timing", "")
    for key in ("acml_vol_shares", "vol_ratio_time_norm", "board_open_won", "gap_open_pct"):
        assert key in note, f"{sid}: data_timing 에 `{key}` 가 없다"
    assert "위험 신호가 아니다" in note


@pytest.mark.parametrize("sid", TICK_DRIVEN)
def test_t4_tick_driven_has_no_data_timing(sid: str) -> None:
    assert "data_timing" not in _user_obj(sid)["strategy"]


def test_t5_note_is_in_meta_so_prompt_version_tracks_it() -> None:
    """`_prompt_version` 해시는 `_STRATEGY_META.get(sid)` 를 넣는다 — 안내문이 META 안에
    있어야 문구를 고칠 때 버전이 갈린다."""
    meta = _lf()._STRATEGY_META
    for sid in SWING_POLL:
        assert "data_timing" in meta[sid], sid
    for sid in TICK_DRIVEN:
        assert "data_timing" not in meta.get(sid, {}), sid
