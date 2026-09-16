"""cycle294 §4·§5 — 살아 있는 구독의 **채널 전환** + 자동 원복 (8영역 밖 leaf).

## 언제 — 전환 창 안에서만, 창 밖은 **전환 금지**

전환 창은 `tick_channel_clock.switch_windows()` 가 표에서 파생한다 — **cycle295
(2026-09-16)부터 아침 `pre_to_krx` 1개뿐이다**(cycle294 가 CRITICAL-1 커버리지로
추가했던 NXT 단독 연속 구간의 두 경계 창은 철회됐다 — 그 20분은 사용자 결정
「15:30~16:00 완전 휴식」으로 주문 자체를 내지 않으므로 시세만 NXT 를 따라갈
이유가 사라졌다). 🔴 창 밖에서는 어떤
경로도 살아 있는 구독의 채널을 바꾸지 않고, **창 안에서도 매 종목마다 시각을
다시 본다**(적대 검증 HIGH-3 — 120초 루프가 창 끝 직전에 진입하면 종전 구현은
`MAX_PER_CYCLE`/`BUDGET_SECS` 가 다 찰 때까지 창을 넘겨 계속 옮겼다. 그 경우
LOW 의 break-before-make 가 09:00 개장 직후 실제 blind 를 만들고 HIGH 의 이중
채널 창이 라이브 프레임 두 줄기에 노출된다). 아침 창의 근거 셋:

1. **그 창에만 프레임이 구조적으로 0 이다** — NXT 휴장 + KRX 시가 단일가.
   이중 채널 구간이 열려도 `tick_volume` last-write-wins 비결정론이 노출되지
   않는다. 정규장 중에 옮기면 두 채널이 동시에 프레임을 주고 BFB/VCP 거래량
   게이트가 도착 순서에 좌우된다.
2. **그 창에 주문이 0 건이다**(설계 · cycle241 시장 침묵 실측).
3. **못 옮겨도 blind 가 아니다** — 미전환 잔여는 NXT 에 남고 NXT 는 정규장·
   애프터에 체결을 싣는다. 비용은 "KRX 가격 대신 NXT 가격" 뿐이다.

## 누가 — 120초 stale watcher

`scheduler.py` 무접촉 계약 때문에 기존 주기 루프에 얹는다. `_scan_loop`(300초)은
스캔 시작 시각에 생성되므로 아침 전환 창에 **존재하지 않는다** — 창을 덮는
루프는 사실상 `stale_watcher_core.check_and_resubscribe_stale` 하나뿐이다.
**never-raise** 다: 전환 실패가 4중 안전망의 한 축을 끊으면 안 된다.

## 🔴 HIGH make-before-break (절대 규칙 2)

보유·익일청산 종목은 신 채널 **ACK 을 확인한 뒤에** 구 채널을 해제한다. 순서를
뒤집으면 그 사이가 blind 이고 그 구간에 손절이 걸리면 되돌릴 수 없다. ACK 실패는
신 채널만 즉시 회수하고 구 채널을 유지하며 **전환 예산을 소모하지 않는다**.
LOW 는 break-before-make — 그 창에 잃을 프레임이 없고 다음 사이클이 재시도한다.

## 전환 창 REST 백스톱에 대한 정직한 답 (절대 규칙 3 · §4-G)

전환 창은 NXT 휴장 + KRX 시가 단일가라 **WS 로도 REST 로도 새 체결가가 존재하지
않는다**. REST 현재가는 그 구간에 전일 종가/예상체결가를 주고, 그것을 손절
판정에 넣는 것은 프리장 왜곡 틱 문제(2026-08-06 사용자 결정)의 재현이다. 그래서
백스톱은 REST 호출이 아니라 **make-before-break + 창 밖 전환 금지 + 미전환 관측**
셋으로 구현한다. KIS 호출 증가 **0**. 전환이 만드는 가격 공백은 그 셋으로 0 이고,
그 창에 원래 가격이 없다는 것은 전환이 만든 사실이 아니다.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime as _datetime

from src.engine import tick_channel_clock, tick_channel_mode
from src.engine.stale_diagnostics import (
    SUBSCRIBE_GRACE_SECS as _DEFAULT_REVERT_PROBE_SECS,
)

logger = logging.getLogger(__name__)

MARKER_SWITCH = "[tick_channel_switch]"
MARKER_SUMMARY = "[tick_channel_switch_summary]"
MARKER_FAILED = "[tick_channel_switch_failed]"
MARKER_ORPHAN = "[tick_channel_switch_orphan]"
MARKER_WINDOW_MISSED = "[tick_channel_switch_window_missed]"
MARKER_REVERT_SKIPPED = "[tick_channel_revert_skipped]"

#: 운영자가 만질 축이 아니다 — 모듈 상수로 둔다(§9-E).
MAX_PER_CYCLE = 80
BUDGET_SECS = 90.0
INTER_TICKER_SLEEP = 0.05
#: 원복 판정 최소 표본 — 저유동 1종목이 시스템 전체를 되돌리면 안 된다(cycle241 선례).
MIN_REVERT_SAMPLE = 2
#: 교차 확인 하한 — 미전환 코호트가 이만큼 fresh 여야 "채널 문제" 로 본다.
MIN_CROSS_FRESH = 2

# ── 하루 수명 상태 (KST 날짜 키 자기 리셋) ─────────────────────────────────
_day: str = ""
#: ticker → 전환 **직전** 채널. 자동 원복의 되돌림 대상이자 표본이다.
_switched_high_today: dict[str, str] = {}
#: 그날 전환을 포기한 종목(ACK 실패). 재시도 폭주를 막는다.
_switch_giveup_today: set[str] = set()
_reverted_today: bool = False
_revert_probe_done: bool = False
_window_missed_emitted: bool = False
#: 비결론 판정은 래치하지 않으므로 재시도 상한이 필요하다(폭주 방지).
_revert_attempts: int = 0
MAX_REVERT_PROBE_ATTEMPTS = 10


def reset_state_for_test() -> None:
    """모듈 전역 상태 초기화 (테스트 격리 seam)."""
    global _day, _reverted_today, _revert_probe_done, _window_missed_emitted
    global _revert_attempts
    _day = ""
    _switched_high_today.clear()
    _switch_giveup_today.clear()
    _reverted_today = False
    _revert_probe_done = False
    _window_missed_emitted = False
    _revert_attempts = 0


def _sync_day(now) -> None:
    global _day, _reverted_today, _revert_probe_done, _window_missed_emitted
    global _revert_attempts
    try:
        key = now.date().isoformat()
    except Exception:
        return
    if _day == key:
        return
    _day = key
    _switched_high_today.clear()
    _switch_giveup_today.clear()
    _reverted_today = False
    _revert_probe_done = False
    _window_missed_emitted = False
    _revert_attempts = 0


def _as_dt(now, at_time):
    """같은 날짜의 `at_time` 을 `now` 와 비교 가능한 datetime 으로."""
    stamp = _datetime.combine(now.date(), at_time)
    if now.tzinfo is not None:
        stamp = stamp.replace(tzinfo=now.tzinfo)
    return stamp


def _is_after(value, threshold) -> bool:
    """`value >= threshold` — tz 혼재를 흡수한다(비교 불가 = 아님)."""
    try:
        if value is None:
            return False
        if (value.tzinfo is None) != (threshold.tzinfo is None):
            value = value.replace(tzinfo=threshold.tzinfo)
        return value >= threshold
    except Exception:
        return False


def _protected(scheduler) -> set[str]:
    """보유 + 익일청산 = HIGH (손절 커버리지 우선)."""
    held: set[str] = set()
    try:
        for strategy in scheduler.registry.all():
            try:
                held.update(strategy.state.positions.keys())
            except Exception:
                pass
    except Exception:
        pass
    try:
        held.update(t for (t, _sid) in scheduler._pending_next_day_clear)
    except Exception:
        pass
    return held


def _is_switchable(current: str, ticker: str) -> bool:
    """🔴 적대 검증 MEDIUM-2 시정 — 전환해도 되는 **시세 채널 구독**인가.

    종전 `_targets` 는 `pool._ticker_to_tr_id` 를 무조건 순회해 두 가지를 함께
    집었다: ① cycle253 **진단 프로브** 튜플(`is_probe_excluded`) — 전환하면 제외
    등록이 구 튜플 키에 남아 새 튜플이 TICK 집계·stale watcher·delta 해제에
    라이브처럼 섞여 프로브 격리 계약이 깨진다 ② TICK 이 아닌 라우팅 항목(예:
    누군가 `kis_ws_pool.subscribe("H0STCNI0", …)` 를 쓰면 계좌번호가 이 dict 에
    들어온다) — `wanted` 는 항상 전용 TICK 채널이라 **체결통보 구독이 전환
    대상**이 되어 루트 CLAUDE.md 의 「체결통보 구독 제거 금지」를 정면으로 깬다.
    현재 호출자는 없지만 가드도 없었다.
    """
    try:
        from src.engine.scanner import TICK_TR_IDS
        from src.realtime.websocket import is_probe_excluded

        if not isinstance(current, str) or current not in TICK_TR_IDS:
            return False
        return not is_probe_excluded(current, ticker)
    except Exception:  # pragma: no cover — never-raise
        return False


def _targets(scheduler, pool, now) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """`(high, low)` — 각 원소 `(ticker, old_tr_id, new_tr_id)`. 목표≠현행만."""
    from src.engine.scanner import DEDICATED_TICK_TR_IDS, desired_tick_tr_id

    high: list[tuple[str, str, str]] = []
    low: list[tuple[str, str, str]] = []
    protected = _protected(scheduler)
    mapping = getattr(pool, "_ticker_to_tr_id", None)
    if not isinstance(mapping, dict):
        return high, low
    for ticker, current in list(mapping.items()):
        if ticker in _switch_giveup_today:
            continue
        if not _is_switchable(current, ticker):
            continue
        priority = "HIGH" if ticker in protected else "LOW"
        try:
            wanted = desired_tick_tr_id(ticker, priority=priority, now=now)
        except Exception:
            continue
        if wanted == current or wanted not in DEDICATED_TICK_TR_IDS:
            continue
        (high if priority == "HIGH" else low).append((ticker, current, wanted))
    return high, low


async def run_switch_cycle(scheduler, pool, *, now) -> dict:
    """120초 stale watcher 안에서 불린다. **never-raise**. 반환은 관측용 dict."""
    try:
        _sync_day(now)
        mode = tick_channel_mode.current_mode()
        offset = tick_channel_mode.switch_offset_secs()

        # 🔴 적대 검증 MEDIUM-3(부팅) 시정 — 게이트에 막혀 나가더라도 **창을
        #    지나쳤는데 안 옮겨진 종목이 있으면** 그 사실을 남긴다. 종전에는
        #    `mode`/`disabled`/`reverted` 가 `_maybe_emit_window_missed` 보다
        #    먼저 return 해서, 창 안에 `off` 를 누르면 일부는 KRX·일부는 NXT 인
        #    채로 종일 남는데 로그에 한 줄도 안 남았다.
        gate = None
        if mode not in (tick_channel_mode.MODE_ENFORCE, tick_channel_mode.MODE_ENFORCE_LOW):
            gate = "mode"
        elif not tick_channel_mode.switch_enabled():
            gate = "disabled"
        elif _reverted_today:
            gate = "reverted"
        if gate is not None:
            _maybe_emit_window_missed(scheduler, pool, now, offset, reason=gate)
            return {"skip": gate}

        krx_regular_open, _nxt_pre_end, _krx_end = tick_channel_clock._windows(now.date())
        if krx_regular_open is None:
            return {"skip": "table"}

        # ── §5 자동 원복 판정이 전환보다 **먼저** ───────────────────────────
        if _revert_probe_due(now, krx_regular_open):
            outcome = await _run_revert_probe(scheduler, pool, now, krx_regular_open)
            if outcome is not None:
                return outcome

        window = tick_channel_clock.active_switch_window(now, offset_secs=offset)
        if window is None:
            _maybe_emit_window_missed(scheduler, pool, now, offset, reason="window_passed")
            return {"skip": "window"}
        _win_start, win_end, win_label = window

        high, low = _targets(scheduler, pool, now)
        ack_timeout = tick_channel_mode.switch_ack_timeout_secs()
        started, done = _time.monotonic(), 0
        stats = {"high_ok": 0, "high_fail": 0, "low_ok": 0, "low_fail": 0}
        left_window = False
        for group, make_first in ((high, True), (low, False)):
            if left_window:
                break
            for ticker, old, wanted in group:
                if done >= MAX_PER_CYCLE or (_time.monotonic() - started) > BUDGET_SECS:
                    break
                # 🔴 적대 검증 HIGH-3 시정 — 창 안에서도 **종목마다** 시각을 다시
                #    본다. 120초 루프는 부팅 시각 기준 고정 위상이라 08:59:4x 에
                #    창 안으로 들어올 수 있고, 종전 구현은 그 뒤 예산이 찰 때까지
                #    09:01:2x 까지 계속 옮겼다 — 개장 직후 LOW 의 break-before-make
                #    는 실제 blind 를, HIGH 의 이중 채널 창은 `tick_volume`
                #    last-write-wins 비결정론을 라이브 프레임에 노출한다.
                if _advanced(now, started).time() >= win_end:
                    left_window = True
                    break
                ok = await _switch_one(
                    pool, ticker, old, wanted,
                    make_before_break=make_first, ack_timeout=ack_timeout,
                )
                key = ("high_ok" if ok else "high_fail") if make_first else (
                    "low_ok" if ok else "low_fail"
                )
                stats[key] += 1
                done += 1
                await asyncio.sleep(INTER_TICKER_SLEEP)
        remaining = max(0, len(high) + len(low) - done)
        _emit_summary(stats, remaining, _time.monotonic() - started, win_label)
        return {
            "switched": done, "remaining": remaining, "window": win_label,
            "left_window": left_window, **stats,
        }
    except Exception:
        logger.debug("%s 사이클 실패 — 다음 주기 재시도", MARKER_SUMMARY, exc_info=True)
        return {"skip": "error"}


def _advanced(now, started_mono: float):
    """사이클 시작 시각 `now` 에 **경과 시간**을 더한 지금 시각.

    벽시계(`datetime.now`)를 다시 읽지 않는 이유 두 가지 — ① 호출자가 넘긴
    `now` 가 이 사이클의 시각 계약이고 그것과 다른 시계를 섞으면 창 판정이
    두 시계 사이에서 갈린다 ② 테스트가 합성 `now` 로 창 안/밖을 만드는데
    벽시계를 읽으면 **실행 시각에 따라 결과가 달라진다**(메모리 교훈:
    「시각 창 게이트 테스트는 시각 고정」). `monotonic` 은 시스템 시계 조정에
    영향받지 않아 경과 측정에 정확하다.
    """
    try:
        from datetime import timedelta

        return now + timedelta(seconds=max(0.0, _time.monotonic() - started_mono))
    except Exception:  # pragma: no cover — never-raise
        return now


async def _switch_one(pool, ticker, old, wanted, *, make_before_break, ack_timeout) -> bool:
    """한 종목의 채널 교체 — 세션은 **건드리지 않는다**(§4-D)."""
    try:
        result = await pool.switch_channel_same_session(
            ticker, wanted,
            make_before_break=make_before_break, ack_timeout_secs=ack_timeout,
        )
    except Exception:
        logger.debug("%s ticker=%s stage=call", MARKER_FAILED, ticker, exc_info=True)
        return False
    if result in ("switched", "switched_orphan"):
        if make_before_break:
            _switched_high_today.setdefault(ticker, old)
        _note_applied(ticker, wanted)
        if result == "switched_orphan":
            logger.warning("%s ticker=%s old=%s", MARKER_ORPHAN, ticker, old)
        logger.info(
            "%s ticker=%s from=%s to=%s mode=%s",
            MARKER_SWITCH, ticker, old, wanted, "high" if make_before_break else "low",
        )
        return True
    if result == "ack_timeout":
        _switch_giveup_today.add(ticker)
        logger.warning(
            "%s ticker=%s stage=ack_timeout old=%s new=%s",
            MARKER_FAILED, ticker, old, wanted,
        )
        return False
    if result in ("noop", "no_route"):
        return False
    logger.warning(
        "%s ticker=%s stage=%s old=%s new=%s", MARKER_FAILED, ticker, result, old, wanted,
    )
    return False


def _note_applied(ticker: str, tr_id: str) -> None:
    """성공 전환만 `scanner` 의 적용 이력·전환 예산에 기록한다(§4-C S6)."""
    try:
        from src.engine import scanner

        scanner.note_channel_switched(ticker, tr_id)
    except Exception:  # pragma: no cover — never-raise
        pass


def _emit_summary(stats: dict, remaining: int, elapsed: float, window: str) -> None:
    try:
        logger.warning(
            "%s window=%s high_ok=%d high_fail=%d low_ok=%d low_fail=%d "
            "remaining=%d elapsed_s=%.1f",
            MARKER_SUMMARY, window, stats["high_ok"], stats["high_fail"],
            stats["low_ok"], stats["low_fail"], remaining, elapsed,
        )
    except Exception:  # pragma: no cover — never-raise
        pass


def _unmoved(scheduler, pool, now) -> list[tuple[str, str, str]]:
    """모드를 **보지 않는** 미전환 잔여 — `(ticker, 현행, 시각축 희망)`.

    `desired_tick_tr_id` 는 모드 스코프를 거쳐 `off`/`observe` 에서 통합을 주므로
    그것으로 세면 킬스위치를 누른 순간 잔여가 **항상 0** 이 된다(그게 바로 세고
    싶은 상황이다). `scanner.clock_desired_tick_tr_id` 는 순수·모드 무관이다.
    """
    out: list[tuple[str, str, str]] = []
    try:
        from src.engine.scanner import DEDICATED_TICK_TR_IDS, clock_desired_tick_tr_id

        protected = _protected(scheduler)
        mapping = getattr(pool, "_ticker_to_tr_id", None)
        if not isinstance(mapping, dict):
            return out
        for ticker, current in list(mapping.items()):
            if not _is_switchable(current, ticker):
                continue
            priority = "HIGH" if ticker in protected else "LOW"
            wanted = clock_desired_tick_tr_id(ticker, priority=priority, now=now)
            if wanted == current or wanted not in DEDICATED_TICK_TR_IDS:
                continue
            out.append((ticker, current, wanted))
    except Exception:  # pragma: no cover — never-raise
        return out
    return out


def _maybe_emit_window_missed(scheduler, pool, now, offset, *, reason: str) -> None:
    """창을 **지나친 뒤** 남은 미전환 잔여를 하루 1행으로 올린다(§4-A).

    `reason` 은 왜 못 옮겼는지다 — `window_passed`(창 밖) / `mode`(리졸버 off·
    observe) / `disabled`(전환 다이얼 off) / `reverted`(자동 원복 뒤).
    """
    global _window_missed_emitted
    try:
        if _window_missed_emitted:
            return
        windows = tick_channel_clock.switch_windows(now.date(), offset_secs=offset)
        if not windows:
            return
        first_end = min(end for _s, end, _l in windows)
        if now.time() < first_end:
            return                      # 아직 첫 창 안 — 잔여는 정상 상태다
        pending = _unmoved(scheduler, pool, now)
        if not pending:
            return
        _window_missed_emitted = True
        logger.warning(
            "%s n=%d sample=%s reason=%s",
            MARKER_WINDOW_MISSED, len(pending), [t for t, _o, _n in pending[:5]], reason,
        )
    except Exception:  # pragma: no cover — never-raise
        pass


# ── §5 자동 원복 ───────────────────────────────────────────────────────────
def _revert_probe_secs() -> float:
    value = tick_channel_mode.revert_probe_secs()
    return float(value) if value is not None else float(_DEFAULT_REVERT_PROBE_SECS)


def _revert_probe_due(now, krx_regular_open) -> bool:
    """측정 시점 = `krx_regular_open + revert_probe_secs`. 그 전에 재면 100% 오탐.

    🔴 적대 검증 CRITICAL-2(C) 시정 — 종전에는 `_switched_high_today` 가 비면
    (= 그날 전환이 한 건도 성공하지 못했거나 `enforce_low` 단계라 HIGH 를 아예
    안 옮긴 날) 자동 원복 트리거가 **구조적으로 존재하지 않았다**. 표본은 이제
    "지금 KRX 전용 채널에 앉은 HIGH" 라 전환 여부와 무관하다(`_revert_sample`).
    """
    if _revert_probe_done or _revert_attempts >= MAX_REVERT_PROBE_ATTEMPTS:
        return False
    try:
        from datetime import timedelta

        due = _as_dt(now, krx_regular_open) + timedelta(seconds=_revert_probe_secs())
        return now >= due
    except Exception:
        return False


def _revert_sample(scheduler, pool) -> list[str]:
    """판정 표본 = **지금 KRX 전용 채널에 앉아 있는 HIGH(보유·익일청산)**.

    🔴 적대 검증 CRITICAL-2(A·D)/HIGH-2 시정 — 종전 표본은 `_switched_high_today`
    (그날 아침에 NXT→KRX 로 옮기는 데 성공한 HIGH)뿐이었다. 그러면 (a) 프리 창부터
    KRX 였던 `nxt_false` **보유** 종목 — 이 사이클이 겨냥한 바로 그 코호트 — 이
    표본에 영영 들어오지 않고 (b) `nxt_true` 보유가 0인 날이나 `enforce_low`
    단계에서는 표본이 비어 원복 자체가 없다. 지금은 "그 채널을 실제로 쓰고 있는
    보유 종목" 을 그대로 본다.
    """
    try:
        from src.engine.scanner import TICK_TR_ID_KRX

        mapping = getattr(pool, "_ticker_to_tr_id", None)
        if not isinstance(mapping, dict):
            return []
        return sorted(
            t for t in _protected(scheduler)
            if mapping.get(t) == TICK_TR_ID_KRX and _is_switchable(mapping.get(t), t)
        )
    except Exception:  # pragma: no cover — never-raise
        return []


def _revert_verdict(pool, now, krx_regular_open, sample) -> tuple[bool, str, int, bool]:
    """`(되돌릴 것인가, 사유, cross_fresh, 결론적인가)`.

    네 번째 원소가 **결론적인가**(decisive)다 — 거짓이면 래치를 걸지 않고 다음
    사이클이 다시 잰다(적대 검증 CRITICAL-2(C): 종전에는 판정 **전에**
    `_revert_probe_done=True` 를 세워 첫 측정이 비결론이면 그날 다시는 재지
    않았다 = 자동 원복이 사실상 죽은 장치였다).

    🔴 교차 확인 재설계(CRITICAL-2(A)) — 종전에는 비교 코호트가 전부 침묵이면
    `market_wide` 로 **결론지어 그날 다시 재지 않았다**. 그런데 3단계 `enforce` 의
    정상 상태는 전 종목이 같은 채널이라, 그 채널이 진짜 죽은 날에는 비교 코호트도
    함께 침묵한다 ⇒ **진짜 고장에서만 발화하지 못하는** 교차 확인이었다. 지금은
    세 갈래로 나눈다:

      ① 비교 코호트 ≥2 가 fresh          → 되돌린다(채널이 이 표본에만 안 온다)
      ② 비교 코호트는 있는데 전부 침묵    → 비결론. 2×probe 까지 기다렸다가
                                            그래도 전원 침묵이면 되돌린다
      ③ 비교 코호트 자체가 없다           → ②와 같은 시한 뒤 되돌린다

    ②③의 escalation 이 오발화(시장 전체 정지 등)해도 손실이 작다 — 되돌린 상태는
    "전원 NXT" 가 아니라 **프리 창 규칙**이라 `nxt_false` 는 KRX 를 유지하고,
    되돌림 자체가 make-before-break 이라 커버리지 공백이 0 이다.
    """
    from src.engine.scanner import ticker_last_tick

    if len(sample) < MIN_REVERT_SAMPLE:
        return False, "sample_too_small", 0, False
    opened = _as_dt(now, krx_regular_open)
    last_tick = dict(ticker_last_tick or {})
    if any(_is_after(last_tick.get(t), opened) for t in sample):
        return False, "frames_present", 0, True          # 건강 — 그날 종결
    mapping = getattr(pool, "_ticker_to_tr_id", None)
    mapping = mapping if isinstance(mapping, dict) else {}
    in_sample = set(sample)
    # 비교 코호트 = **표본이 아닌 모든 종목**. 두 출처를 합친다 — 풀 라우팅(지금
    # 구독 중인 것)과 `ticker_last_tick`(프레임을 실제로 받은 것). 후자만 보면
    # 아직 한 번도 안 받은 종목이 "비교 대상이 없다" 로 잘못 접히고, 전자만 보면
    # 풀 밖(레거시 직접 구독)에서 오는 프레임을 못 본다.
    cross = list(dict.fromkeys(
        [t for t, tr in mapping.items() if t not in in_sample and _is_switchable(tr, t)]
        + [t for t in last_tick if t not in in_sample]
    ))
    cross_fresh = sum(1 for t in cross if _is_after(last_tick.get(t), opened))
    if cross_fresh >= MIN_CROSS_FRESH:
        return True, "no_frame_after_open", cross_fresh, True
    from datetime import timedelta

    escalated = now >= opened + timedelta(seconds=_revert_probe_secs() * 2)
    if len(cross) >= MIN_CROSS_FRESH:
        # 비교 대상이 있는데 그쪽도 조용하다 = 우선은 세션·시장 문제로 본다
        # (cycle241 계열). **결론짓지 않는다** — 시장이 깨어나면 다시 재고,
        # 2×probe 까지도 전원 침묵이면 그때는 채널을 계속 믿을 근거가 없다.
        if escalated:
            return True, "all_silent_escalated", cross_fresh, True
        return False, "market_wide", cross_fresh, False
    if escalated:
        # 비교 대상이 **구조적으로 없다**(전 종목 같은 채널 = 3단계 정상 상태).
        return True, "all_silent_no_cross", cross_fresh, True
    return False, "awaiting_cross", cross_fresh, False


async def _run_revert_probe(scheduler, pool, now, krx_regular_open):
    """원복 판정. 결론적이었을 때만 래치한다. 되돌렸으면 결과 dict, 아니면 `None`."""
    global _revert_probe_done, _reverted_today, _revert_attempts
    _revert_attempts += 1
    sample = _revert_sample(scheduler, pool)
    should, reason, cross_fresh, decisive = _revert_verdict(
        pool, now, krx_regular_open, sample,
    )
    if decisive:
        _revert_probe_done = True
    if not should:
        logger.info(
            "%s reason=%s n=%d cross_fresh=%d decisive=%d attempt=%d",
            MARKER_REVERT_SKIPPED, reason, len(sample), cross_fresh,
            int(decisive), _revert_attempts,
        )
        return None

    # 🔴 래치를 **먼저** 건다 — 그래야 아래에서 계산하는 희망 채널이 원복 뒤의
    #    값(프리 창 규칙: `nxt_true`→NXT · `nxt_false`→KRX 유지)이 된다.
    tick_channel_clock.set_day_revert(now.date())
    _reverted_today = True
    reverted, failed = 0, 0
    for ticker in sample:
        try:
            from src.engine.scanner import clock_desired_tick_tr_id

            wanted = clock_desired_tick_tr_id(ticker, priority="HIGH", now=now)
        except Exception:
            failed += 1
            continue
        # 🔴 적대 검증 CRITICAL-3 시정 — 되돌림도 **make-before-break** 이다.
        #    종전에는 `make_before_break=False`(= `bypass_limit=False` + 선해제)
        #    를 **보유 종목에** 09:03 라이브 구간에서 걸었고 반환값도 읽지 않아,
        #    41-cap·OPSP 백오프에 걸리면 그 종목이 어느 채널에도 없는 채로 종일
        #    남았다. "되돌림의 전제가 프레임 0" 이라는 근거는 오발화 시 거짓이고,
        #    오발화 가능성이 0 이 아닌 이상 보유 종목에 break-before-make 를 쓸
        #    이유가 없다(모듈 docstring 의 절대 규칙 2 와도 모순이었다).
        result = None
        try:
            result = await pool.switch_channel_same_session(
                ticker, wanted, make_before_break=True,
                ack_timeout_secs=tick_channel_mode.switch_ack_timeout_secs(),
            )
        except Exception:
            result = "exception"
        if result in ("switched", "switched_orphan"):
            _note_applied(ticker, wanted)
            reverted += 1
        elif result == "noop":
            reverted += 1               # 이미 그 채널 — 되돌릴 것이 없다
        else:
            failed += 1
            logger.warning(
                "%s ticker=%s stage=revert old=%s new=%s result=%s",
                MARKER_FAILED, ticker, _switched_high_today.get(ticker, "-"),
                wanted, result,
            )
    # 🔴 ERROR 인 이유 = 되돌렸다는 것은 설계 가정(KRX 전용 채널이 종목 속성과
    #   무관하게 수신한다)이 틀렸다는 뜻이다. `pattern_by_level` 이 WARNING 이상만
    #   21:30 리포트 `top_patterns` 에 넣으므로 INFO 면 리포트에 한 글자도 안 뜬다.
    logger.error(
        "[tick_channel_auto_revert] n=%d reverted=%d failed=%d sample=%s "
        "probe_secs=%.0f cross_fresh=%d reason=%s",
        len(sample), reverted, failed, sample[:5], _revert_probe_secs(),
        cross_fresh, reason,
    )
    return {"reverted": reverted, "failed": failed, "reason": reason}
