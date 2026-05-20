"""사이클 26 — get_active_tick_tr_ids() 시간대별 TR_ID set 검증.

계획서 H 영역: 6 케이스 (6개 시간 구간)
- 08:00~08:59:10 → {H0NXCNT0}
- 08:59:10~09:00 → {H0NXCNT0, H0STCNT0} (사전 마진)
- 09:00~15:30 → {H0STCNT0}
- 15:30~15:39:10 → {H0STCNT0} (종가 흡수 마진)
- 15:39:10~15:40 → {H0STCNT0, H0NXCNT0} (사전 마진)
- 15:40~20:00 → {H0NXCNT0}
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _get_tr_ids_at(t: time) -> set:
    """주어진 KST time 에 대한 활성 TR_ID set 반환."""
    from src.engine.scanner import get_active_tick_tr_ids
    # monkeypatching datetime.now 대신 직접 time 값 전달 지원 여부 확인
    # 함수가 time 파라미터를 받으면 직접 전달, 없으면 모듈 patch
    import inspect
    sig = inspect.signature(get_active_tick_tr_ids)
    if "now_t" in sig.parameters:
        return get_active_tick_tr_ids(now_t=t)
    # fallback: 모듈 내부 datetime.now 를 mock
    import src.engine.scanner as scanner_mod
    orig = getattr(scanner_mod, "_datetime_now_kst", None)
    # 함수가 내부적으로 datetime.now(KST).time() 를 사용한다면 monkeypatching 필요.
    # 여기서는 직접 시각을 인자로 받는 API 가 없다고 가정 — 테스트용 파라미터 추가
    return get_active_tick_tr_ids(now_t=t)


# ---------------------------------------------------------------------------
# 1. 08:00~08:59:10 — NXT 채널만
# ---------------------------------------------------------------------------
def test_tick_tr_ids_pre_nxt_window():
    """PRE_NXT 구간(08:00~08:59:10) 은 H0NXCNT0 단독."""
    for t in (time(8, 0), time(8, 30), time(8, 59, 9)):
        ids = _get_tr_ids_at(t)
        assert ids == {"H0NXCNT0"}, f"{t} 에서 H0NXCNT0 단독 기대, 실제: {ids}"


# ---------------------------------------------------------------------------
# 2. 08:59:10~09:00 — 사전 마진 (NXT + KRX 동시)
# ---------------------------------------------------------------------------
def test_tick_tr_ids_presubscribe_margin_krx():
    """08:59:10~08:59:59 는 H0NXCNT0 + H0STCNT0 동시 (KRX 사전 구독 마진)."""
    for t in (time(8, 59, 10), time(8, 59, 30), time(8, 59, 59)):
        ids = _get_tr_ids_at(t)
        assert "H0NXCNT0" in ids, f"{t} 에서 H0NXCNT0 유지 기대"
        assert "H0STCNT0" in ids, f"{t} 에서 H0STCNT0 추가 기대 (사전 마진)"


# ---------------------------------------------------------------------------
# 3. 09:00~15:30 — KRX 채널만
# ---------------------------------------------------------------------------
def test_tick_tr_ids_main_window():
    """MAIN 구간(09:00~15:30) 은 H0STCNT0 단독."""
    for t in (time(9, 0), time(12, 0), time(15, 20), time(15, 29, 59)):
        ids = _get_tr_ids_at(t)
        assert ids == {"H0STCNT0"}, f"{t} 에서 H0STCNT0 단독 기대, 실제: {ids}"


# ---------------------------------------------------------------------------
# 4. 15:30~15:39:10 — KRX 채널 유지 (종가 흡수)
# ---------------------------------------------------------------------------
def test_tick_tr_ids_gap_after_krx():
    """15:30~15:39:09 는 H0STCNT0 유지 (종가 흡수 마진)."""
    for t in (time(15, 30), time(15, 35), time(15, 39, 9)):
        ids = _get_tr_ids_at(t)
        assert ids == {"H0STCNT0"}, f"{t} 에서 H0STCNT0 유지 기대, 실제: {ids}"


# ---------------------------------------------------------------------------
# 5. 15:39:10~15:40 — 사전 마진 (KRX + NXT 동시)
# ---------------------------------------------------------------------------
def test_tick_tr_ids_presubscribe_margin_nxt():
    """15:39:10~15:39:59 는 H0STCNT0 + H0NXCNT0 동시 (NXT 사전 구독 마진)."""
    for t in (time(15, 39, 10), time(15, 39, 30), time(15, 39, 59)):
        ids = _get_tr_ids_at(t)
        assert "H0STCNT0" in ids, f"{t} 에서 H0STCNT0 유지 기대"
        assert "H0NXCNT0" in ids, f"{t} 에서 H0NXCNT0 추가 기대 (NXT 사전 마진)"


# ---------------------------------------------------------------------------
# 6. 15:40~20:00 — NXT 채널만
# ---------------------------------------------------------------------------
def test_tick_tr_ids_post_nxt_window():
    """POST_NXT 구간(15:40~20:00) 은 H0NXCNT0 단독."""
    for t in (time(15, 40), time(17, 0), time(19, 59)):
        ids = _get_tr_ids_at(t)
        assert ids == {"H0NXCNT0"}, f"{t} 에서 H0NXCNT0 단독 기대, 실제: {ids}"
