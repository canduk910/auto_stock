"""cycle364 S1 Red — TIME: 저녁 캡처 21:00 의 시각 불변식 (🔴 크리티컬 가드 2 · 카드2 (가)).

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §0-3 · §2.4 · §6.2 TIME · M13.

- 20:30~20:40 = 일봉 적재 창(`test_cycle273_daily_load_1810::test_g273f_2` 가 `TIME_*` 0건 강제)
- 20:35~20:53 = 보조 7계정 토큰 강제 재발급 직렬화 창(`test_cycle269…::test_c9 (vi)`) —
  그 창에 보조 풀 REST(A1 의 KIS 폴백·휴장일 조회)가 들어가면 자연 재발급이 겹쳐 발급 수가
  두 배가 된다(cycle296 사고의 재현). 21:00 = T + 15분(cycle269 (iv) 체인 상한).
- 정산(21:30) 전 30분 여유(준비 실측 60~75초 + 마커 대기 상한 15분).

기존 충돌 스캔 2종(`test_g273f_2` · `test_c9`)은 이 파일이 대신하지 않는다 — 그대로 초록이어야
한다(M13 `time(20, 45)` 은 `test_c9 (vi)` 와 이 파일의 (2)가 둘 다 잡는다).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

import src.engine.scheduler as sched

pytestmark = pytest.mark.unit

_BASE = datetime(2026, 9, 22)


def _dt(t: time) -> datetime:
    return _BASE.replace(hour=t.hour, minute=t.minute, second=t.second)


def test_time_0_capture_is_2100():
    assert sched.TIME_EVENING_FUNNEL_CAPTURE == time(21, 0), sched.TIME_EVENING_FUNNEL_CAPTURE


def test_time_1_capture_after_daily_load():
    """(1) 적재(20:30) 뒤 — A1 은 D 봉을 「전일」로 읽는다. 앞이면 D 봉이 없다."""
    assert sched.TIME_STOCK_MASTER_DAILY_LOAD < sched.TIME_EVENING_FUNNEL_CAPTURE


def test_time_2_capture_after_token_chain_upper_bound():
    """(2) 토큰 강제 재발급 T + 15분 이후 — 직렬화 창에 보조 풀 REST 를 넣지 않는다 (M13)."""
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as T

    assert _dt(T) + timedelta(minutes=15) <= _dt(sched.TIME_EVENING_FUNNEL_CAPTURE), (
        f"캡처 {sched.TIME_EVENING_FUNNEL_CAPTURE} 가 토큰 체인 상한 {(_dt(T) + timedelta(minutes=15)).time()} 앞이다"
    )


_PREPARE_BUDGET = timedelta(minutes=3)  # 준비 실측 60~75초(설계 §2.4) × 여유 — 하한 3분


def test_time_3_latest_start_plus_prepare_budget_before_settlement():
    """(3) 🔁 round 2(R8) — 가장 늦은 시작(캡처 + leaf 시작 마감 `EVENING_START_DEADLINE`) +
    준비 예산(≥3분) ≤ 정산. 리터럴 20분이 아니라 **leaf 상수에서 유도**한다 — 캡처 시각이나 시작
    마감이 바뀌면 이 식이 붉어져야 한다(21:30 `_reset_daily_state` 가 준비 도중
    `ticker_prev_close`·`positions` 를 비우면 미리보기와 보유 상태가 동시에 깨진다)."""
    from src.engine.funnel_capture import EVENING_START_DEADLINE

    assert isinstance(EVENING_START_DEADLINE, timedelta) and EVENING_START_DEADLINE > timedelta(0)
    latest_start = _dt(sched.TIME_EVENING_FUNNEL_CAPTURE) + EVENING_START_DEADLINE
    assert latest_start + _PREPARE_BUDGET <= _dt(sched.TIME_SETTLEMENT), (
        f"가장 늦은 시작 {latest_start.time()} + 준비 예산 {_PREPARE_BUDGET} 이 정산 "
        f"{sched.TIME_SETTLEMENT} 를 넘는다"
    )


def test_time_4_capture_after_trading_end_and_session_start_cutoff():
    """매매 종료(20:00) 뒤 · 기동 거부 경계(20:00) 뒤 — 장중·애프터장 라이브 목록을 바꾸지 않는다."""
    assert sched.TIME_NXT_POST_CLOSE < sched.TIME_EVENING_FUNNEL_CAPTURE
    assert sched.TIME_SESSION_START_CUTOFF < sched.TIME_EVENING_FUNNEL_CAPTURE


def test_time_5_capture_constant_comment_no_longer_claims_1620_rationale():
    """주석 정직화 — 옛 근거(「16:10 basics 직후, 16:30 마스터 직전」)가 남으면 다음 사람이
    16:20 으로 되돌릴 논거를 준다(cycle283 C2 선례)."""
    import inspect

    line = next(
        ln for ln in inspect.getsource(sched).splitlines()
        if ln.startswith("TIME_EVENING_FUNNEL_CAPTURE = time(")
    )
    assert "16:10 basics 직후" not in line and "16:30 마스터 직전" not in line, line
