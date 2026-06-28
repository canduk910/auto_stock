"""사이클 182 회귀 가드 — is_call_auction_now() 시간창 게이트 (stale-1 HIGH + stale-5 LOW).

대상: ``src/engine/session.py::SessionTracker.is_call_auction_now``

domain-expert 자문: ``_workspace/domain_consult/cycle182_call_auction_time_gate.md``
    (방식 A 시간창 게이트 단독 채택)
Red 메모: ``_workspace/red/cycle182_call_auction_time_gate.md``

결함 (현재 코드 session.py L209)::

    if self._last_nxt_mkop_code in ("110", "121"):   # 시간창 게이트 0
        return True

= 고착 코드("121"/"110") 가 시간 무관 영구 True. KIS H0UNMKO0 가 동시호가 *종료*
전환 코드(112/129)를 reliably push 하지 않으면 ``_last_nxt_mkop_code`` 영구 고착 →
- stuck-121 (사용자 보고): 15:20 "121" 후 15:30 미전환 → 15:30~20:00 NXT 애프터 내내 stale OFF
- stuck-110 (자문 신규, 더 위험): 08:30 "110" 후 09:00 미전환 → 09:00~15:20 MAIN 전체 stale OFF
→ 보유 종목 WebSocket 끊김(손절/익일청산 틱) 누락 = 매매 안전성 직결.

시정 설계 (Green 목표 — 본 테스트는 이 동작을 가정. domain-expert load-bearing 조건식)::

    if code == "110" and time(8, 25) <= t < time(9, 5):    return True   # 110 유효창 ±5분
    if code == "121" and time(15, 15) <= t < time(15, 35): return True   # 121 유효창 ±5분
    if time(8, 30) <= t < time(9, 0):    return True   # 시간 폴백 (사이클 162 보존)
    if time(15, 20) <= t < time(15, 30): return True
    return False

stale-5 (LOW): ``now = now or datetime.now()`` (naive, KST 위반) → ``datetime.now(_KST)``.

작성 규칙: 시간 분기는 ``now`` 인자 직접 주입 = 날짜/타임존 의존 0 (사이클 176 교훈).
stale-5(now=None 경로) 만 freezegun 으로 KST-aware 강제 검증.
"""

from __future__ import annotations

from datetime import datetime

import pytest

try:  # freezegun 미설치 환경 graceful
    from freezegun import freeze_time
except ImportError:  # pragma: no cover
    freeze_time = None

from src.engine.session import SessionTracker


def _tracker(code: str = "") -> SessionTracker:
    """고착 코드(``_last_nxt_mkop_code``) 주입 헬퍼."""
    tracker = SessionTracker()
    tracker._last_nxt_mkop_code = code
    return tracker


# ───────── 가드 1: stuck 차단 (HIGH 핵심, 현재 코드 FAIL = Red) ─────────


@pytest.mark.parametrize(
    "code, hh, mm, label",
    [
        ("121", 16, 0, "stuck-121 @ 16:00 NXT 애프터 (사용자 보고 결함)"),
        ("110", 11, 0, "stuck-110 @ 11:00 MAIN 피크 (자문 신규 발견 — 더 위험)"),
        ("121", 10, 0, "stuck-121 @ 10:00 MAIN"),
        ("110", 14, 0, "stuck-110 @ 14:00 MAIN"),
    ],
)
def test_G_182_STUCK_blocked_outside_window(code, hh, mm, label):
    """G-182-STUCK (HIGH): 고착 코드가 자기 유효 시간창 밖이면 무시 → False.

    현재 코드 L209 `in ("110","121")` 무조건 True → 본 단언(False) FAIL = Red.
    Green(시간창 게이트) 후 = 시간창 밖 코드 무시 → 시간 폴백도 False → False.
    """
    tracker = _tracker(code)
    now = datetime(2026, 6, 18, hh, mm)
    assert tracker.is_call_auction_now(now) is False, label


# ───────── 가드 2: 마진 경계 (±5분, 포함/배제 명확) ─────────


@pytest.mark.parametrize(
    "code, hh, mm, ss, expected, label",
    [
        # 110 유효창: 08:25:00 ≤ t < 09:05:00
        ("110", 8, 24, 59, False, "110 @ 08:24:59 = 마진 직전 (배제, 폴백도 밖)"),
        ("110", 8, 25, 0, True, "110 @ 08:25:00 = 마진 시작 (포함 경계)"),
        ("110", 8, 29, 0, True, "110 @ 08:29:00 = 마진 내부"),
        ("110", 9, 4, 59, True, "110 @ 09:04:59 = 마진 끝 직전 (포함)"),
        ("110", 9, 5, 0, False, "110 @ 09:05:00 = 마진 끝 (배제, 창 밖+폴백 밖)"),
        # 121 유효창: 15:15:00 ≤ t < 15:35:00
        ("121", 15, 14, 59, False, "121 @ 15:14:59 = 마진 직전 (배제, 폴백도 밖)"),
        ("121", 15, 15, 0, True, "121 @ 15:15:00 = 마진 시작 (포함 경계)"),
        ("121", 15, 34, 59, True, "121 @ 15:34:59 = 마진 끝 직전 (포함, 15:40 NXT 전 복원)"),
        ("121", 15, 35, 0, False, "121 @ 15:35:00 = 마진 끝 (배제)"),
    ],
)
def test_G_182_MARGIN_window_boundaries(code, hh, mm, ss, expected, label):
    """G-182-MARGIN: 게이트 유효창 ±5분 경계 (포함=시작·끝직전 / 배제=직전·끝).

    배제 경계(08:24:59 / 09:05:00 / 15:14:59 / 15:35:00) 4종은 현재 코드가
    코드 분기 무조건 True 반환 → FAIL = Red. 포함 경계는 현재/Green 양쪽 True.
    """
    tracker = _tracker(code)
    now = datetime(2026, 6, 18, hh, mm, ss)
    assert tracker.is_call_auction_now(now) is expected, label


# ───────── 가드 3: 사이클 162 정당 skip 보존 (HIGH, 현재/Green 양쪽 동일) ─────────


@pytest.mark.parametrize(
    "code, hh, mm, expected, label",
    [
        ("110", 8, 45, True, "진짜 장전 동시호가 110 @ 08:45 (코드창+폴백 양쪽 True)"),
        ("121", 15, 25, True, "진짜 장후 동시호가 121 @ 15:25 (코드창+폴백 양쪽 True)"),
        ("", 8, 45, True, "VTS code='' @ 08:45 → 시간 폴백 True"),
        ("", 15, 25, True, "VTS code='' @ 15:25 → 시간 폴백 True"),
        ("", 11, 0, False, "평시 code='' @ 11:00 → False"),
        ("121", 15, 21, True, "사용자 사고 15:21:48 영역 → 재구독 폭주 차단 영속"),
    ],
)
def test_G_182_PRESERVE_cycle162(code, hh, mm, expected, label):
    """G-182-PRESERVE (HIGH): 진짜 동시호가/VTS 폴백 skip 100% 보존.

    domain-expert §의제4 충돌 검증 — 게이트는 사이클 162 정당 skip 을 깨지 않는다.
    현재 코드/Green 양쪽 동일 결과 (보존 가드, Red 아님).
    """
    tracker = _tracker(code)
    now = datetime(2026, 6, 18, hh, mm)
    assert tracker.is_call_auction_now(now) is expected, label


def test_G_182_TRANSITION_code_auto_clear():
    """G-182-TRANSITION: 방식 B 내재 증명 — 121→129(장마감) 재대입 후 16:00 → False.

    ``on_h0nxmko0`` L233 무조건 재대입이 고착 코드를 덮어씀 → 추가 코드 0 (방식 B 내재).
    129 는 동시호가 코드 아님 → 현재/Green 양쪽 False (보존 가드).
    """
    tracker = _tracker("121")
    # 장마감 코드 129 수신 (비-동시호가) → 자동 클리어 (방식 B 내재)
    tracker._last_nxt_mkop_code = "129"
    now = datetime(2026, 6, 18, 16, 0)
    assert tracker.is_call_auction_now(now) is False


# ───────── 가드 4: stale-5 KST 강제 (LOW, now=None 경로, freezegun) ─────────


@pytest.mark.skipif(freeze_time is None, reason="freezegun 미설치")
def test_G_182_STALE5_kst_aware_premarket():
    """G-182-STALE5 (LOW): now=None → KST-aware(datetime.now(_KST)) 사용 검증 (장전).

    freezegun UTC 23:45:00 = KST 익일 08:45 (장전 동시호가).
    현재 코드: naive ``datetime.now()`` → 23:45 → 창 밖 → False = Red.
    Green: ``datetime.now(_KST)`` → 08:45 → True.
    """
    tracker = _tracker("")  # 코드 미수신 → 시간 폴백 경로
    with freeze_time("2026-06-18 23:45:00"):
        assert tracker.is_call_auction_now() is True


@pytest.mark.skipif(freeze_time is None, reason="freezegun 미설치")
def test_G_182_STALE5_kst_aware_afterclose():
    """G-182-STALE5 (LOW): now=None KST-aware (장후 동시호가).

    freezegun UTC 06:25:00 = KST 15:25 (장후 동시호가).
    현재 코드: naive → 06:25 → 창 밖 → False = Red. Green: 15:25 → True.
    """
    tracker = _tracker("")
    with freeze_time("2026-06-18 06:25:00"):
        assert tracker.is_call_auction_now() is True
