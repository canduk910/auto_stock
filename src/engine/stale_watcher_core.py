"""사이클 67 = stale_manager.py 1,099L sub-module 분해 (Q1=A facade) — K stale watcher 본체.

사이클 63 Phase 2-A3 (2026-06-05): scheduler.py L2442~L2789 K stale watcher 핵심 2 함수 이주.
사이클 66 (2026-06-06): cap=10 결함 시정 영속 (Q3 옵션 A WARNING 로그).
사이클 67 (2026-06-06): sub-module 분해 후 stale_diagnostics 직접 import (Q2 옵션 P1).

절대 깨지 말 것:
- WebSocket 4 중 안전망 행위 보존 (F1 + scan_loop + K stale watcher + resubscribe)
- 사이클 29 005935 사고 패턴 영구 차단 (HIGH 종목 cap 밖 잘림 0건)
- Q4=B 영속 (사이클 60 답습하지 않는 유일 영역) — `emit_stale_session_detail` 직접 호출
- 사이클 66 시정 본체 영속 (priority 분리 *먼저* + cap 적용 *나중*)
- try/except 4중 가드 영속 (사이클 66 Q2)
- `sys.modules.get("src.engine.scheduler")` 패턴 영속 (D-1 AST 가드 + freezegun patch 호환)
- 함수 본체 변경 0 (라인 단위 동일, self.* → scheduler.* 치환만)

의존성 방향 (옵션 A 단방향, G-7 AST 가드 영속):
    stale_watcher_core → stale_diagnostics (단방향, Q2 옵션 P1 모듈-레벨 정적 import)
    stale_watcher_core → 외부 모듈 (scheduler / scanner / websocket_pool)
    역방향 (diagnostics/session_recovery/universe_guard → watcher_core) 금지
"""
from __future__ import annotations

import asyncio
import logging
from asyncio import wait_for as _wait_for
from datetime import datetime, timedelta
from typing import Any

# 사이클 67 Q2 옵션 P1 — cross-module 모듈-레벨 정적 import
# (Q4=B 영속, hot path 360 회/일 — 가독성 + AST G-7 가드 검증 명시성)
from src.engine.stale_diagnostics import (
    MAX_STALE_RETRIES,
    STALE_FORCE_RETRY_AFTER_SECS,
    STALE_FORCE_RETRY_HOURLY_CAP,
    STALE_FRESHNESS_SECS,
    SUBSCRIBE_GRACE_SECS,  # 사이클 135 — 구독 ACK grace period (180s, Q3=A 영속)
    emit_stale_session_detail,
)
# cycle252 — 무송출(no_feed) 종목 레지스트리. 모듈-레벨 정적 import (D-1/D-2 류
# 동적 조회 seam 이 아니다 — 그 계열 출현 수 불변, AST G-252-2).
from src.engine import no_feed_registry
from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환)

# 사이클 216 — LOW-only 재구독 throttle (동일 종목 중복 재발사 차단).
# 반드시 < 300s(`resubscribe_stale_priority` 5분 주기 자체) — 자기막힘/cycle215 원복 방지.
RESUBSCRIBE_THROTTLE_SECS = 3 * STALE_FRESHNESS_SECS  # = 180


# ── cycle293 — 채널 리졸버 보조 헬퍼 ────────────────────────────────────────
def _actual_or_desired_tick_tr_id(kis_ws_pool, ticker: str, priority: str) -> str:
    """그 종목이 **실제로 구독된** TICK 채널, 모르면 리졸버의 판정.

    해제·재등록 쌍이 이 값 **하나**를 함께 쓴다 — 그래서 이 경로는 채널을 바꾸지
    않는다(§3-C: 살아 있는 구독의 전환 경로를 만들지 않는다). 실제 구독 채널을
    우선하는 이유 = 틀린 채널로 UNSUBSCRIBE 를 보내면 KIS 가 `OPSP0003
    UNSUBSCRIBE ERROR not found!` 를 돌려주고(cycle215~218 이 잡은 그 ERROR) 구
    채널 튜플이 **영구 고아**로 41 슬롯을 잠식한다.

    풀이 mock 이거나 병행 dict 가 없는 환경은 리졸버 단독으로 fail-open 한다
    (`isinstance(dict)` 가드 = 사이클 135 `_ack_map_raw` 패턴 답습).

    ⚠️ 폴백은 **순수** 판정(`desired_tick_tr_id`)이다 — `tick_tr_id_for` 는 판정
    이력(`_channel_applied`/`_channel_flipped_today` = §6-D 하루 1회 전환 예산)을
    변이한다. 재등록 경로가 그 예산을 먹으면 같은 날 실제 구독 전환이 조용히
    차단된다(적대 검증 F4·MEDIUM-3).
    """
    from src.engine.scanner import TICK_TR_IDS, desired_tick_tr_id

    mapping = getattr(kis_ws_pool, "_ticker_to_tr_id", None)
    if isinstance(mapping, dict):
        current = mapping.get(ticker)
        if isinstance(current, str) and current in TICK_TR_IDS:
            return current
    return desired_tick_tr_id(ticker, priority=priority)


def _collect_protected_for_classification(scheduler) -> set[str]:
    """보유 + 익일청산 종목 (no_feed 분류 대상의 **채널 무관** 축, §6-E).

    `high_tickers` 계산과 목적이 다르다 — 그쪽은 재등록 우선순위를 정하고(그래서
    호출 위치·예외 규약이 cycle252 계약에 묶여 있다), 이쪽은 "누구를 분류해 둬야
    하는가" 만 답한다. 예외는 전부 흡수(빈 집합) — 분류 대상 수집 실패가 stale
    사이클을 끊으면 4중 안전망의 한 축이 사라진다.
    """
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


# ── 사이클 74 옵션 C 조건부 — [stale_watcher] 5분 aggregation collector ─────────────

_stale_watcher_collector: list[dict] = []


def record_stale_watcher_check(stats: dict) -> None:
    """5분 윈도우 누적 (사이클 74 옵션 C 조건부 aggregation).

    stats keys: subscribed / stale / force_reregistered / skipped_giveup /
                force_retried / cap_blocked / no_feed_skipped(cycle252)
    stale_count > 0 인 경우 `emit_stale_session_detail` 를 통한 individual
    `[stale_watcher_detail]` 는 별도 보존 (사이클 73 영속, 변경 0).
    """
    _stale_watcher_collector.append(stats)


def flush_stale_watcher_collector() -> None:
    """5분 윈도우 종료 시 `[stale_watcher_summary]` 1행 emit + collector 초기화.

    scheduler disconnect / cancel 직전 마지막 flush 1회 호출 의무 (Q5 옵션 A).
    collector 비어 있으면 emit skip (no-op).

    cycle252 — 기존 5필드 prefix 는 byte 보존, 끝에 ` no_feed_skipped=%d`(합계)
    를 추가만 한다(키 부재 = 0, 구 형태 stats 와 혼재해도 KeyError 없음).

    🔴 **cycle293 배포 전후 값을 합산하거나 나란히 놓지 말 것 (§9-B 의미 전환).**
    cycle252 계약에서 `no_feed_skipped` 는 "회복 가치 0 인 재등록을 건너뛴 수"
    였고 **높은 것이 정상**이었다. cycle293 이후 전용 채널로 옮긴 종목은 프레임이
    실제로 오므로 skip 대상에서 **빠진다** — 즉 이 값의 **감소가 성공 서명**이다.
    같은 이유로 `[stale_force_retry]` 도 감소가 정상이다. 두 사이클의 수치는
    서로 다른 것을 재는 계기다.
    """
    if not _stale_watcher_collector:
        return
    checks = len(_stale_watcher_collector)
    stale_total = sum(s.get("stale", 0) for s in _stale_watcher_collector)
    retried = sum(s.get("force_reregistered", 0) for s in _stale_watcher_collector)
    cap_blocked = sum(s.get("cap_blocked", 0) for s in _stale_watcher_collector)
    force_retried = sum(s.get("force_retried", 0) for s in _stale_watcher_collector)
    no_feed_skipped = sum(s.get("no_feed_skipped", 0) for s in _stale_watcher_collector)
    logger.info(
        "[stale_watcher_summary] checks=%d stale_total=%d retried=%d cap_blocked=%d force_retried=%d"
        " no_feed_skipped=%d",
        checks, stale_total, retried, cap_blocked, force_retried, no_feed_skipped,
    )
    _stale_watcher_collector.clear()


# ── cycle252 — [no_feed_held] 1회/일 cap (HIGH ∩ no_feed 관측) ─────────────────
# 날짜 키 자기 리셋 — `KstDailyEmitCap`(사이클 258 카드 #4)이 내부에서 KST 롤오버를
# 자체 처리한다(`_reset_daily_state` 훅 미의존 — 이 파일은 scheduler.py 무접촉
# 규약이라 scheduler 의 정산 훅에 배선할 수 없었던 사정은 그대로다).
_no_feed_held_logged: "KstDailyEmitCap[str]" = KstDailyEmitCap[str]()
_NO_FEED_HELD_KEY = "no_feed_held"


def _is_before_krx_continuous_open(now: datetime) -> bool:
    """cycle357 — 지금이 KRX 연속체결 시작(K3 REGULAR, 통상 09:00) 이전인가.

    NXT 프리장(N1) 동안 `nxt_tradable=False` 종목은 채널 리졸버가 전환 횟수를
    아끼려고 **KRX 전용 채널**에 미리 둔다(`src/engine/CLAUDE.md` 「시세 채널」
    절 — "그 종목은 그 시간 NXT 미거래 + KRX 시가 단일가라 어느 채널이든
    연속체결 프레임이 없고, KRX 에 두면 09:00 첫 체결을 전환 없이 받는다").
    그 구간은 KRX 도 시가 단일가라 **어느 채널에 있든** 연속체결 프레임이
    정의상 0 이다. `[no_feed_held]` 판정을 그 구간에도 돌리면 이 정의상 공백을
    「무송출」로 오판한다(운영 2026-09-22·23 08:00:1x 실측 거짓 경보).

    경계는 `tick_channel_clock._windows()`(공개 API `market_state.
    get_market_table` 파생, 시각 리터럴 0건 체인)의 `krx_regular_open` 을
    재사용한다 — 새 시각 리터럴을 박지 않는다(cycle252 G-252-6 "시간창 리터럴
    신설 0" 계약 보존). `tick_channel_switch.run_switch_cycle` 이 이미 같은
    private 헬퍼를 같은 방식으로 부른다(전례, `src/engine/tick_channel_switch.py`).

    판정 실패(표 조회 예외·경계 미확보)는 **판정을 억제하지 않는 방향**으로
    fail-open 한다 — `False`(= "창 이전이 아니다")를 돌려주면 호출부가 이
    시정 *전과 byte 동일하게* 평가를 계속한다. 관찰 마커를 죽이는 방향의
    fail-open 은 관찰 그 자체를 무력화하므로 금지 방향이다.
    """
    try:
        from src.engine import tick_channel_clock as _tick_channel_clock

        krx_regular_open, _pre_end, _krx_end = _tick_channel_clock._windows(now.date())
        if krx_regular_open is None:
            return False
        return now.time() < krx_regular_open
    except Exception:
        return False


# cycle393 — `[no_feed_held]` 는 **측정했을 때만** 말한다 (사용자 결정 7, 2026-10-02).
#
# 종전(cycle252~357) 판정은 `is_no_feed(t)`(stock_master.nxt_tradable==False, 정적
# 분류) 하나였다 — 프레임 수신 여부를 보지 않아 KRX 전용 보유 종목을 하나라도 들고
# 있으면 09:00 뒤 첫 사이클에 **반드시** 떴다(운영 09-28·09-29·09-30·10-01 5회 실측,
# 10-01 은 대상 4종목 전부가 마커보다 먼저 MAIN 체결 틱을 받은 거짓 경보였다).
#
# 이제 두 증거 다리가 **모두 측정됐을 때만** 확정한다:
#   W — WS 체결 기록 부재: `tick_volume.get_observed_acml_vol(t) is None`(오늘 KST).
#       REST 폴(`_run_swing_rest_poll_once` → `on_tick`)은 `acml_vol` 을 넘기지 않아
#       기록하지 않으므로 `ticker_last_tick` 과 달리 거짓 음성·양성을 만들지 않는다.
#   R — 구독 중 KRX 체결 발생: `inquire_acml_vol(t, market="J")` 를 600초 간격으로
#       두 번 읽어 늘었는가. 한 번만 읽으면 재기동·장전 누적이 "체결" 로 둔갑한다.
# 증분이 보인 뒤 60초(W 가 여전히 참이어야) 더 지나야 확정 — 그 사이 WS 기록이
# 생기거나(E4) 구독이 빠지면(E4b) 증거를 버리고 처음부터 다시 쌓는다.
#
# 판정 창 = KRX 정규장 K3 `[개장 + NO_FEED_OPEN_GRACE_SECS, 종료)`. 창 경계는
# `market_state.get_market_table` 에서만 읽는다(시각 리터럴 신설 0, G-252-6 승계) —
# 표 조회 실패는 **창 안으로** 본다(cycle357 "시각 게이트 실패는 억제하지 않는다"),
# 반대로 증거 다리 실패(REST 실패·타임아웃·예외)는 **말하지 않는다**(측정 없이
# 말하는 것이 이번 결함 그 자체였다). 두 실패가 다른 방향인 이유는 이 한 줄 때문
# 이다 — 시각 게이트는 REST 호출 수를 줄이는 장치일 뿐이고, 증거 다리는 메시지의
# 진실성 그 자체다.
NO_FEED_OPEN_GRACE_SECS = 180
NO_FEED_PROBE_INTERVAL_SECS = 600
NO_FEED_CONFIRM_SECS = STALE_FRESHNESS_SECS
NO_FEED_PROBE_TIMEOUT_SECS = 3.0
NO_FEED_PROBES_PER_CYCLE = 4

# 종목별 증거 상태(모듈 전역, KST 날짜 자기 리셋) — `{ticker: {"vol0":, "t0":, "vol1":,
# "t1":}}`. `"vol1"/"t1"` 은 증분이 확인된 뒤에만 생긴다(§3.5). 테스트 전용 리셋은
# `reset_no_feed_held_probe_for_test()`.
_no_feed_probe_state: dict = {}
_no_feed_probe_day = ""


def reset_no_feed_held_probe_for_test() -> None:
    """테스트 전용 — 종목별 증거 상태 + 날짜 키를 모두 비운다."""
    global _no_feed_probe_day
    _no_feed_probe_state.clear()
    _no_feed_probe_day = ""


async def _probe_krx_acml_vol(ticker: str):
    """REST 증거 다리(R) 의 유일한 KIS 호출 지점 — KRX 누적거래량 1회 조회.

    `quotation` 은 함수 안 lazy import(A3) — 테스트가 `core._probe_krx_acml_vol`
    자체를 통째로 갈아끼우는 것이 정상 seam 이고(conftest autouse 가 기본 None
    스텁으로 중립화한다), 이 함수는 그 seam 의 **실물**(`real_no_feed_probe`
    마커 테스트가 검증)이다. `market="J"` 를 명시한다 — KRX 외 누적은 이 판정의
    증거가 아니다.
    """
    from src.api import quotation

    return await quotation.inquire_acml_vol(ticker, market="J")


def _ws_tick_recorded_today(ticker: str) -> bool:
    """증거 다리(W) — 오늘(KST) WS 체결 프레임을 이 프로세스가 한 번이라도 받았나.

    `tick_volume.get_observed_acml_vol` 은 `risk.on_tick` 이 WS 체결(`fields[13]
    ACML_VOL`)에서만 기록한다 — 멀티데이 REST 폴 경로는 그 체결량 인자를 넘기지
    않아 기록하지 않으므로 `ticker_last_tick`(§3.2 기각 대안)과 달리 donchian·
    kojiro 보유분의 REST 폴이 이 값을 거짓으로 만들지 않는다.
    """
    from src.engine import tick_volume

    return tick_volume.get_observed_acml_vol(ticker) is not None


def _in_no_feed_probe_window(now: datetime) -> bool:
    """지금이 판정 창 K3 `[개장+grace, 종료)` 안인가 — 표 조회 실패는 창 안으로 본다.

    경계는 `market_state.get_market_table(now.date())` 의 KRX·REGULAR 행에서만
    얻는다(시각 리터럴 신설 0, A2). 실패·행 없음은 fail-open(판정 억제 방향이
    아니라 **진행** 방향 — W·R 두 증거 다리가 거짓 경보를 따로 막으므로 이 창은
    REST 호출 수를 줄이는 장치일 뿐이다).
    """
    try:
        from src.engine.market_state import MarketPhase, get_market_table

        rows = [
            r for r in get_market_table(now.date())
            if r.market == "KRX" and r.phase is MarketPhase.REGULAR
        ]
        if not rows:
            return True
        start = min(r.start for r in rows)
        end = max(r.end for r in rows)
        open_dt = datetime.combine(now.date(), start, tzinfo=now.tzinfo) + timedelta(
            seconds=NO_FEED_OPEN_GRACE_SECS
        )
        end_dt = datetime.combine(now.date(), end, tzinfo=now.tzinfo)
        return open_dt <= now < end_dt
    except Exception:
        return True


async def _read_krx_acml_vol(ticker: str):
    """`_probe_krx_acml_vol` 을 타임아웃 아래 실행 — 실패·비정수는 전부 `None`.

    타임아웃은 **호출 시점에** 모듈 전역 `NO_FEED_PROBE_TIMEOUT_SECS` 을 읽는다
    (기본 인자로 박으면 테스트가 줄인 값이 반영되지 않는다). `asyncio.wait_for`
    가 아니라 import 시점에 묶은 `_wait_for` 를 쓴다 — 많은 테스트가 `core.asyncio`
    를 `_SleepSpy` 로 바꿔치기하므로(A8), 모듈 `asyncio` 이름에 기대면 그 대역이
    타임아웃까지 집어삼킨다.
    """
    try:
        v = await _wait_for(_probe_krx_acml_vol(ticker), NO_FEED_PROBE_TIMEOUT_SECS)
    except Exception:
        return None
    return v if isinstance(v, int) and not isinstance(v, bool) else None


async def _observe_no_feed_held(cohort: set, subscribed, now: datetime) -> None:
    """`[no_feed_held]` 증거 상태 기계 — cohort(HIGH∩no_feed) 중 구독 중인 종목만 평가.

    종목별로: W(오늘 WS 기록)가 참이면 증거를 지우고 넘어간다(명세 §3.5-5). W 가
    거짓이고 증분 확인 대기 중이면 `NO_FEED_CONFIRM_SECS` 경과 후 확정 후보에
    넣는다. 기준이 없거나 `NO_FEED_PROBE_INTERVAL_SECS` 가 지났으면(사이클당
    `NO_FEED_PROBES_PER_CYCLE` 상한, 정렬 순) REST 를 읽어 기준→증분→확정 전이를
    진행한다(§3.5). 확정된 종목 전부를 한 번에 `_maybe_emit_no_feed_held` 로 넘긴다.

    cohort·subscribed 이탈도 증거 삭제 사유다(구독 공백이 끼면 "구독 중 체결" 증명이
    깨진다, E4b). 날짜가 바뀌면 전체 상태를 버린다(E10) — 전날 기준을 오늘 증거로
    쓰면 안 된다.

    본문 전체가 하나의 `try/except Exception` 이다(A5) — 이 함수는 재등록 루프의
    두 출구에서 불리므로(A4) 여기서 던지면 HIGH 재등록이 끊긴다. 흡수 흔적은
    `observer_trace.trace_observer_failure("[no_feed_held_observe_failed]", ...)`
    (debug) 뿐이다 — `CancelledError` 는 막지 않는다(`except Exception` 한정).
    """
    if not cohort:
        return
    try:
        global _no_feed_probe_day
        if not _no_feed_held_logged.should_emit(_NO_FEED_HELD_KEY, now=now):
            return

        day = now.date().isoformat()
        if _no_feed_probe_day != day:
            _no_feed_probe_day = day
            _no_feed_probe_state.clear()

        targets = sorted(t for t in cohort if t in subscribed)
        for stale_ticker in list(_no_feed_probe_state):
            if stale_ticker not in targets:
                del _no_feed_probe_state[stale_ticker]

        in_window = _in_no_feed_probe_window(now)
        budget = NO_FEED_PROBES_PER_CYCLE
        confirmed: set[str] = set()
        evidence: list[str] = []

        for ticker in targets:
            try:
                recorded = _ws_tick_recorded_today(ticker)
            except Exception:
                continue  # W 판정 자체가 예외면 그 종목은 모른다 — 건너뛴다
            if recorded:
                _no_feed_probe_state.pop(ticker, None)
                continue

            state = _no_feed_probe_state.get(ticker)
            if state is not None and "t1" in state:
                # 증분 확인됨 — 확인 대기(창 밖이어도 같은 날이면 진행, E6b).
                if (now - state["t1"]).total_seconds() >= NO_FEED_CONFIRM_SECS:
                    confirmed.add(ticker)
                    evidence.append(
                        f"{ticker}:{state['vol0']}->{state['vol1']}"
                        f"@{state['t0']:%H:%M:%S}->{state['t1']:%H:%M:%S}"
                    )
                continue
            if not in_window:
                continue
            if state is not None and (now - state["t0"]).total_seconds() < NO_FEED_PROBE_INTERVAL_SECS:
                continue
            if budget <= 0:
                continue
            budget -= 1

            vol = await _read_krx_acml_vol(ticker)
            if vol is None:
                phase = "failed"  # 실패는 기준을 바꾸지 않는다 — 다음 사이클 재시도
            elif state is None:
                _no_feed_probe_state[ticker] = {"vol0": vol, "t0": now}
                phase = "baseline"
            elif vol > state["vol0"]:
                state["vol1"] = vol
                state["t1"] = now
                phase = "traded"
            else:
                # vol <= vol0(동일 또는 감소) — 기준은 **내리지 않는다**(F1, cycle393
                # 리뷰). 누적거래량이 일중에 줄어드는 것은 하루 안에서는 있을 수 없는
                # 이상값(응답 결측 시 "0" 폴백·지연 시세 서버의 낮은 스냅샷)이고, 기준을
                # 그 값으로 내리면 다음 정상 읽기가 "증가"로 오판돼 이번 사이클이 없애려던
                # 바로 그 거짓 경보가 되살아난다. vol0 은 `max(vol0, vol)` 로 유지하고
                # 시각만 옮겨 간격을 재기 시작한다(정상 저유동 무체결은 vol==vol0 이라
                # max 가 그대로 vol0 이다).
                _no_feed_probe_state[ticker] = {"vol0": state["vol0"], "t0": now}
                phase = "flat" if vol == state["vol0"] else "decreased"
            logger.info(
                "[no_feed_held_probe] ticker=%s phase=%s vol=%s prev_vol=%s",
                ticker, phase, vol, None if state is None else state.get("vol0"),
            )

        if confirmed:
            _maybe_emit_no_feed_held(confirmed, now, evidence=evidence)
    except Exception:
        trace_observer_failure("[no_feed_held_observe_failed]", _NO_FEED_HELD_KEY, None)


def _maybe_emit_no_feed_held(tickers: set, now: datetime, *, evidence: list | None = None) -> None:
    """두 증거 다리가 모두 선 종목 집합을 WARNING 1회/일로 알린다.

    peek→로그→mark(cycle226 D-3 순서 답습) — mark 를 먼저 하면 로그 자기실패가
    그날 관측을 지운다. 호출자(`_observe_no_feed_held`)가 증거 상태 기계를
    책임지고, 이 함수는 메시지 조립 + cap + 프리장 억제만 한다.

    관측기 자기 예외는 **여기서 흡수**한다(tester F-1, cycle237/242 "emit 헬퍼는
    예외 흡수 · 행위는 cap 밖" 계약).

    🔴 **cycle393 — 이 WARNING 은 이제 측정됐을 때만 뜬다.** W(오늘 WS 체결 기록
    없음) + R(구독 중 KRX 누적거래량 증가, 600s 간격 두 읽기 + 60s 확인) 두 다리가
    모두 선 경우뿐이다(명세 §2). 종전(cycle252~357)의 `is_no_feed` 정적 분류만으로는
    더 이상 뜨지 않는다 — **배포 전후 건수를 합산하지 않는다**(판정 기준 자체가
    다른 것을 잰다).

    🔴 **cycle357 — KRX 연속체결 창(09:00~) 이전은 판정 자체를 억제한다**
    (`_is_before_krx_continuous_open`). cap **앞**에 두어 프리장 호출이 cap 을
    소비하지 않는다. 이 게이트는 판정 시점만 좁힐 뿐 HIGH 재등록 등 구독 행위는
    한 글자도 바꾸지 않는다(호출부·재등록 경로 무접촉).
    """
    try:
        if _is_before_krx_continuous_open(now):
            return
        if not _no_feed_held_logged.should_emit(_NO_FEED_HELD_KEY, now=now):
            return
        ev = "" if not evidence else " evidence=[" + ", ".join(evidence) + "]"
        logger.warning(
            "[no_feed_held] tickers=%s%s — KRX 전용 보유 종목이 구독 중 KRX 체결"
            "(REST 누적거래량 증가)이 있었는데 오늘 WS 체결 기록이 0건이다. 손절 평가는 "
            "donchian·kojiro 보유분만 REST 폴(60초)로 받는다 — 다른 전략 보유분은 손절 "
            "평가가 멈춘다",
            sorted(tickers), ev,
        )
        _no_feed_held_logged.mark_emitted(_NO_FEED_HELD_KEY, now=now)
    except Exception:
        trace_observer_failure("[no_feed_held_emit_failed]", _NO_FEED_HELD_KEY, None)


# ── A3 2 함수 — K stale watcher 핵심 (사이클 63 Phase 2-A3, 2026-06-05) ────────────

async def check_and_resubscribe_stale(scheduler: Any) -> None:
    """K stale watcher 본체 — 120s 주기 (사이클 17/28/29-R1/R3 영속).

    사이클 63 Phase 2-A3 (2026-06-05): scheduler.py L2442~L2663 그대로 이주.
    self.* → scheduler.* 치환만. 행위 변경 0건 (refactor).

    Q4=B (사이클 60 답습하지 않는 유일 영역):
    본체 마지막 `self._emit_stale_session_detail(stale_tickers, now)` 호출 →
    `emit_stale_session_detail(scheduler, stale_tickers, now)` 직접 호출 (1 hop 단축).
    scheduler.py L2678 wrapper 자체는 외부 호환 보존 (삭제 안 함).

    Q2 RECOMMEND — `try/except` 4 중 가드 그대로 보존:
    - `registry.all()` / `s.state.positions.keys()` / `_pending_next_day_clear` 4 중
    - `getattr(scheduler, "registry", None)` 폴백 도입 금지 (silent 실패 위험)

    사이클 29-R3 우선순위 분리 (메인 편중 73% → 5% 해소) 영속:
    - positions / _pending_next_day_clear → HIGH+bypass_limit=True (메인 절대 보장)
    - 그 외 후보 → LOW+bypass_limit=False (보조 라운드로빈 분산)

    사이클 29-R1 force_retry (영구 stale 무한 skip 결함 대응) 영속:
    - 1~5회: 즉시 unsubscribe + subscribe (KIS 정상 신규 등록 패턴)
    - 6회 초과: 5분 cooldown + 시간당 12회 cap (LMS / 앱키 정지 위험 차단)
    """
    import sys as _sys

    # 사이클 61 패턴 답습 — D-1 AST 가드 + D-2 sys.modules.get 출현 수 가드.
    # datetime 접근은 scheduler 모듈 네임스페이스 우선 참조 (freezegun patch 호환).
    # kis_ws_pool 은 src.realtime.websocket_pool 모듈 직접 참조 (테스트 patch 호환):
    #   `patch("src.realtime.websocket_pool.kis_ws_pool")` 패치 작동 보장.
    _sched_mod = _sys.modules.get("src.engine.scheduler")
    if _sched_mod is not None and hasattr(_sched_mod, "datetime"):
        _dt_mod = _sched_mod.datetime
    else:
        from datetime import datetime as _dt_mod  # type: ignore[assignment]

    # kis_ws_pool — websocket_pool 모듈에서 직접 접근 (테스트 patch 경로 호환)
    _wsp_mod = _sys.modules.get("src.realtime.websocket_pool")
    if _wsp_mod is not None:
        kis_ws_pool = _wsp_mod.kis_ws_pool
    else:
        from src.realtime.websocket_pool import kis_ws_pool  # type: ignore[assignment]

    # cycle293 — 리졸버는 `_actual_or_desired_tick_tr_id` 가 대신 부른다(그 헬퍼가
    # "실제 구독 채널 우선" 규약의 단일 지점이다). 여기서 `tick_tr_id_for` 를 직접
    # import 하면 "이 함수가 판정을 한다" 고 오독된다.
    from src.engine.scanner import (
        DEDICATED_TICK_TR_IDS,
        KST_TZ as _KST_TZ,
        TICK_TR_IDS,
        ticker_last_tick,
    )

    # cycle293 — 킬스위치 재조회(120초 주기). `scheduler.py` 무접촉 계약 때문에
    # 재조회 배선은 이 경로와 `scanner.subscribe_filtered_stocks`(5분) 둘이다 —
    # 둘 중 어느 쪽이든 `off` 가 ≤2분 안에 닿는다(재시작 요구 금지, §8-B).
    try:
        from src.engine import tick_channel_mode as _tick_channel_mode

        await _tick_channel_mode.refresh_mode()
        await _tick_channel_mode.refresh_switch_params()
    except Exception:
        logger.debug("[tick_channel_mode] refresh 실패 — 현재 모드 유지", exc_info=True)

    # 사이클 13-E (2026-05-18): 메인 단독 → 풀 전체로 확장
    subscribed = kis_ws_pool.get_subscribed_tickers()
    if not subscribed:
        return

    # cycle252 — no_feed 분류 신선도 보장(§2(a)). 예외는 흡수 — 관측 개선이
    # 사이클 완주를 막으면 안 된다(4중 안전망의 한 축, W6).
    #
    # cycle293 §6-E — 인자는 **채널 무관 집합**이어야 한다. `get_subscribed_tickers()`
    # 를 그대로 넘기던 종전 코드는(그 함수가 통합 채널만 세던 시절) 자기 강화
    # 플리커를 만들었다: 리졸버가 62종목을 전용 채널로 옮기면 → 다음 인자에서
    # 그 62개가 빠짐 → `_no_feed` 에서 탈락 → `is_no_feed()` False → 리졸버가
    # 다시 통합으로 판정 → **600s TTL 마다 채널 왕복**(KIS 공지 「비정상 케이스 2:
    # 무한 등록/해제」 그 자체). 지금은 집계도 세 채널 합집합이지만, 인자를 그
    # 함수에 다시 묶으면 같은 함정이 부활하므로 **보유·익일청산 합집합**을 더해
    # 채널 축과 구조적으로 분리한다.
    _classify_targets = set(subscribed) | _collect_protected_for_classification(scheduler)
    try:
        await no_feed_registry.ensure_fresh(_classify_targets)
    except Exception:
        logger.debug(
            "[no_feed_registry] ensure_fresh 실패 — 이번 사이클 no_feed 판정 skip"
        )

    # 🔴 cycle294 적대 검증 CRITICAL-1(부팅) — 매수 축 코호트 스탬프 **재시도**.
    # `scanner.tick_tr_id_for` 안의 스탬프는 LOW 종목에 대해 그날 07:59 한 번뿐이고
    # (`already_in_pool` skip 이 리졸버 호출보다 앞), 07:59 는 W2 도장 오염이 최악인
    # 시각이라 그때 출처 검사가 실패한 종목이 영영 미스탬프로 남는다. 이 120초 루프가
    # 07:47 부터 돌기 때문에 여기에 얹으면 08:08 진실 복원 뒤 **2분 안에** 코호트가
    # 닫힌다(5분 `_scan_loop` 은 09:30 에야 생긴다). 순수 메모리 연산 · 닫힘 우세
    # 단방향 래치라 재호출이 매수를 더 열 수 없다. never-raise.
    try:
        from src.engine import scanner as _scanner_mod

        _scanner_mod.restamp_cohorts(_classify_targets)
    except Exception:
        logger.debug("[tick_buy_gate] 코호트 재스탬프 실패 — 다음 주기 재시도")

    # cycle294 §4-B — 살아 있는 구독의 **채널 전환**은 이 120초 루프가 유일한
    # 트리거다. `_scan_loop`(300초)은 `TIME_SCAN_START`(09:30)에 생성되므로 아침
    # 전환 창에 **존재하지 않는다**. 자리는 `ensure_fresh` **직후**(레지스트리가
    # 더워진 뒤라야 시각축×속성축 합성이 성립한다) · stale 판정 루프 **앞**
    # (전환 직후 종목이 같은 사이클에서 stale 로 오인되지 않는다).
    # never-raise — 전환 실패가 4중 안전망의 한 축을 끊으면 안 된다.
    try:
        from src.engine import tick_channel_switch as _tick_channel_switch

        await _tick_channel_switch.run_switch_cycle(
            scheduler, kis_ws_pool, now=_dt_mod.now(_KST_TZ),
        )
    except Exception:
        logger.debug("[tick_channel_switch] 전환 사이클 실패 — 다음 주기 재시도", exc_info=True)

    now = _dt_mod.now(_KST_TZ)
    threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
    min_dt = _dt_mod.min.replace(tzinfo=_KST_TZ)

    # 사이클 135 (2026-06-15) — 구독 ACK grace period (180s).
    # 사용자 결정 Q1=A + Q2=180s + Q3=A 자문 정합 + Q4=A HIGH 일관 grace.
    # domain-expert 자문 산출물 _workspace/domain_consult/cycle135_websocket_grace_period.md
    #
    # 가드 동작:
    #   - 첫 시세 입수 후 (`ticker_last_tick[t]` 존재) → 기존 60s 영속 (사이클 29 005935 보호, G-GRACE-7)
    #   - 첫 시세 입수 *전* (`ticker_last_tick[t]` 부재) + ACK 시점 미확인 → 기존 60s 영속 (race 보호, G-GRACE-6)
    #   - 첫 시세 입수 *전* + ACK 시점 확인 + grace 이내 → stale 판정 skip
    #   - 첫 시세 입수 *전* + ACK 시점 확인 + grace 초과 → stale 판정 정상 발화
    grace = timedelta(seconds=SUBSCRIBE_GRACE_SECS)
    # 사이클 135 ack_map 영역 영구 영속 — dict 영역 영구 영속만 유효 영속 (MagicMock 등 spec 부재 안전 영속)
    _ack_map_raw = getattr(kis_ws_pool, "_subscribed_at", None)
    ack_map = _ack_map_raw if isinstance(_ack_map_raw, dict) else {}

    # cycle293 §4-B — ACK 조회 키를 **채널 무관**으로 만든다. `_subscribed_at` 은
    # `(tr_id, tr_key)` 키라(`websocket.py:186`) 전용 채널 ACK 은 `("H0STCNT0", t)`
    # 에 심긴다. 조회 키를 `(TICK_TR_ID, t)` 로 고정하면 그 종목만 **180초 구독
    # grace 가 영구 miss** → 구독 직후 stale 판정 → 즉시 강제 재등록 = cycle252 가
    # 없앤 하루 ≈14,600 SEND 폭주의 조용한 부활. 구독 사실(어느 채널에 심겼는가)이
    # 판정의 정본이므로 역인덱스를 1회 만들어 쓴다.
    ack_at_by_ticker: dict[str, object] = {}
    for _ack_key, _ack_val in list(ack_map.items()):
        if (
            isinstance(_ack_key, tuple)
            and len(_ack_key) == 2
            and _ack_key[0] in TICK_TR_IDS
        ):
            ack_at_by_ticker[_ack_key[1]] = _ack_val

    def _is_within_grace(t: str) -> bool:
        """grace 영역 영구 영속 판정 영구 영속.

        첫 시세 입수 후 영역 (`ticker_last_tick[t]` 존재) = False (grace 미적용, 기존 60s 영속).
        첫 시세 입수 *전* + ACK 미확인 = False (race 보호, 기존 60s 영속).
        첫 시세 입수 *전* + ACK 확인 + grace 이내 = True (stale 판정 skip).
        """
        if t in ticker_last_tick:
            return False  # 첫 시세 입수 후 = grace 미적용 (G-GRACE-7 영속)
        ack_at = ack_at_by_ticker.get(t)
        if not isinstance(ack_at, datetime):
            return False  # ACK 미확인 = race 보호, 기존 60s 영속 (G-GRACE-6)
        try:
            return (now - ack_at) <= grace  # grace 이내 = stale 판정 skip
        except (TypeError, ValueError):
            # mock/race 안전 폴백 영역 영구 영속 = 기존 60s 영속 (사이클 29 005935 보호 영속)
            return False

    # 사이클 149 (2026-06-16) — VI/거래정지 stale 회피 hook.
    # 의제 5 (자문 채택) = VI 활성 ∪ 거래정지 ∪ 종목상태 이상 ticker stale 판정 지연.
    # `_is_within_grace` 패턴 답습 (사이클 135) + try/except 안전 폴백.
    # domain-expert 자문 `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`.
    try:
        from src.engine.market_operation_monitor import is_ticker_stale_excluded as _is_market_op_excluded
    except Exception:
        def _is_market_op_excluded(t: str) -> bool:  # type: ignore[no-redef]
            return False

    _excluded_for_log: list[str] = []

    def _market_op_skip(t: str) -> bool:
        """stale 회피 = True 시 stale 판정 지연 + 로그 emit."""
        try:
            if _is_market_op_excluded(t):
                _excluded_for_log.append(t)
                return True
        except Exception:
            return False
        return False

    # 사이클 162 (2026-06-17) — 동시호가 시간대 stale 회피 hook (의제 E).
    # 사용자 보고 사고: 6/17 15:21:48 KST stale_watcher = subscribed=10 fresh=0 stale=10
    # ratio=0% → 5분 주기 재구독 시도 반복 = KIS LMS chain 위험.
    # 근본 원인 = 동시호가 시간대 (15:20~15:30) 체결 부재 = 정상 → stale 오판.
    # domain-expert 자문 산출물 `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md`.
    # 사이클 371 — cycle216(5분 우선 재구독)이 이미 LOW-scoped 로 좁혀 둔 것을 K watcher
    # 에도 미러한다: HIGH(보유·익일청산)는 09:00/15:30 갭개장·마감 손절 대비 그대로
    # 처리하고, LOW 후보만 skip 한다(사이클 38 「stale 판정 전체 지연」 명문화는 LOW
    # 전용으로 좁혀졌다 — HIGH 를 skip 하면 그 8분 잔류가 곧 005935 사고 패턴이다).
    try:
        from src.engine.session import session_tracker as _session_tracker
        _is_call_auction = _session_tracker.is_call_auction_now(now)
    except Exception:
        _is_call_auction = False

    stale_tickers = sorted(
        t for t in subscribed
        if (now - ticker_last_tick.get(t, min_dt)) > threshold
        and not _is_within_grace(t)
        and not _market_op_skip(t)
    )

    if _excluded_for_log:
        logger.info(
            "[stale_skip_market_op] count=%d tickers=%s — VI/거래정지 stale 회피",
            len(_excluded_for_log), _excluded_for_log[:20],
        )

    # 사이클 29-R3 (2026-05-21) — 우선순위 분리 (메인 편중 73% 해소)
    # 사이클 25-B `_resubscribe_stale_priority` 와 동일 패턴:
    #   - positions / _pending_next_day_clear → HIGH+bypass_limit=True (메인 절대 보장)
    #   - 그 외 후보 → LOW+bypass_limit=False (보조 라운드로빈 분산)
    # Q2 RECOMMEND — try/except 4 중 가드 그대로 보존
    # cycle252 — stale_tickers 가 비어도(전부 fresh) high_tickers 는 필요하다
    # (아래 [no_feed_held] 판정이 stale 여부와 무관하게 매 사이클 계산되므로
    # `if not stale_tickers: return` **앞**으로 끌어올렸다, §2(c)).
    # cycle371 — 동시호가 LOW-scoped skip 판정도 high_tickers 가 있어야 하므로 같은
    # 이유로 그 판정 **앞**에 둔다.
    high_tickers: set[str] = set()
    try:
        for s in scheduler.registry.all():
            try:
                high_tickers.update(s.state.positions.keys())
            except Exception:
                pass
    except Exception:
        # registry 미주입 인스턴스(테스트 __new__) 보호 — 모두 LOW 로 처리
        pass
    try:
        high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
    except Exception:
        pass

    if _is_call_auction:
        # cycle371 — LOW 만 skip(사이클 216 미러), HIGH 는 이어서 그대로 처리한다.
        low_stale = [t for t in stale_tickers if t not in high_tickers]
        high_stale = [t for t in stale_tickers if t in high_tickers]
        logger.warning(
            "[stale_skip_call_auction] subscribed=%d low=%d high=%d — 동시호가 시간대 "
            "LOW stale 회피 (HIGH 유지, 체결 부재 정상 영역)",
            len(subscribed), len(low_stale), len(high_stale),
        )
        if not high_stale:
            # HIGH stale 없음(LOW 뿐이거나 stale 자체가 없음) — 누적 retry 카운터 보존
            # (fresh 회복 케이스 분기 미진입 = 정상 영역 영구 영속, 사이클 162 원 계약).
            # `is_no_feed`(아래 no_feed_held 판정) 호출도 이 반환 *뒤*라 W9 불변 유지.
            return
        stale_tickers = sorted(high_stale)

    # cycle252(c)/cycle393 — HIGH ∩ no_feed 코호트(순수 계산만, I/O·로그 0). `is_no_feed`
    # 호출은 동시호가 LOW-scoped skip 이 HIGH stale 없이 조기 반환하는 경로의 **뒤**(위)
    # 이므로 W9(HIGH 없는 동시호가 사이클에서 판정 0회)를 만족한다. 실제 측정·emit 은
    # `_observe_no_feed_held` 가 두 출구에서 한다(cycle393 §4 — REST 대기가 이 사이클의
    # HIGH 재등록을 늦추면 안 된다).
    no_feed_held_cohort: set[str] = set()
    if high_tickers:
        no_feed_held_cohort = {t for t in high_tickers if no_feed_registry.is_no_feed(t)}

    if not stale_tickers:
        # 모두 fresh — 누적 retry 카운터 리셋 (회복 케이스)
        scheduler._stale_retry_count.clear()
        # 사이클 28 — _stale_last_resubscribe_at 동행 clear (G5 cleanup 동행).
        # getattr 폴백으로 사전 init 누락 인스턴스(테스트 `__new__` 호출 등) 보호.
        if hasattr(scheduler, "_stale_last_resubscribe_at"):
            scheduler._stale_last_resubscribe_at.clear()
        await _observe_no_feed_held(no_feed_held_cohort, subscribed, _dt_mod.now(_KST_TZ))
        return

    force_reregistered = 0
    skipped_giveup = 0
    force_retry_count = 0       # 사이클 29 — 영구 stale 시간 기반 강제 재시도 카운트
    force_retry_cap_blocked = 0  # 사이클 29 — 시간당 cap 초과 차단 카운트
    no_feed_skipped = 0          # cycle252 — LOW no_feed 종목 SEND 생략 카운트

    for ticker in stale_tickers:
        retry = scheduler._stale_retry_count.get(ticker, 0) + 1
        scheduler._stale_retry_count[ticker] = retry

        # 사이클 29-R3 — 종목별 priority 결정 (HIGH/LOW 분리)
        if ticker in high_tickers:
            sub_priority = "HIGH"
            sub_bypass = True
        else:
            sub_priority = "LOW"
            sub_bypass = False

        # cycle252(b) — LOW no_feed 종목은 재등록 SEND 를 아예 내지 않는다
        # (회복 가치 0, 포렌식 ②-5). HIGH 는 이 조건에서 구조적으로 면제된다
        # (§1 D1). retry 카운터는 정직하게 계속 증가시키되(§1 D2) r>5 는 기존
        # cooldown 분기(cycle218)와 같은 홀드로 정직화 — stale_universe_guard
        # 의 `retries > MAX_STALE_RETRIES` 저유동 축출 경로를 보존한다.
        # ⚠️ D2 의 2차 효과(tester F-3, 행위 결함 아님): 종전엔 force_retry 가
        # 20분 주기로 r 을 0 으로 되돌려 r>5 체류율이 ≈50% 였지만, 이제 LOW
        # no_feed 는 r=6 에 **영구 홀드** → universe guard 의 5분 평가 대상에
        # 100% 체류 = 유동 nxt_false 후보의 `inquire_ccnl`/`inquire_acml_vol`
        # REST 가 5분당 ≈1회 → 2회(+35~78 호출/5분 ≈0.12~0.26/s, KIS 20/s 대비
        # 무시 가능). D+1 은 `[universe_excluded]` 건수와 두 path 의 api_metrics
        # 로 예상 범위인지 확인한다. 근본 시정 B(H0STCNT0 리졸버) 착지 시 소멸.
        # cycle293 — 이 종목이 실제로 어느 채널에 있는가(모르면 리졸버 판정).
        # unsubscribe·subscribe 가 **같은 값**을 쓴다 = 이 경로는 채널을 바꾸지
        # 않는다(§3-C — 살아 있는 구독의 전환 경로를 만들지 않는다).
        tick_tr_id = _actual_or_desired_tick_tr_id(kis_ws_pool, ticker, sub_priority)

        # cycle252(b) 의 skip 을 cycle293 §9-B 로 좁힌다 — 전용 채널로 옮긴 종목은
        # 프레임이 실제로 오므로 **회복 가치가 생긴다**. skip 을 그대로 두면 그
        # 채널의 진짜 stale 을 영원히 못 고친다.
        # 🔴 cycle293 Green (적대 검증 H4) — 킬스위치 `off` 는 **churn 차단까지**
        # 복원한다. 판정만 끄면 이미 전용 채널에 올라간 종목은 채널이 그대로라
        # (§3-C 장중 전환 금지) 이 skip 조건이 거짓이 되어 하루 ≈14,600 SEND 의
        # 일부가 부활하고, `off` 로는 그날 멈출 수 없다(다음 `_boot` 까지). `off`
        # 는 "오늘과 동일" 을 뜻해야 하므로 그때는 채널 축을 보지 않는다.
        from src.engine import tick_channel_mode as _tcm

        _resolver_off = _tcm.current_mode() == _tcm.MODE_OFF
        if (
            sub_priority == "LOW"
            and no_feed_registry.is_no_feed(ticker)
            and (_resolver_off or tick_tr_id not in DEDICATED_TICK_TR_IDS)
        ):
            if retry > MAX_STALE_RETRIES:
                scheduler._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1
            no_feed_skipped += 1
            continue

        if retry > MAX_STALE_RETRIES:
            # 사이클 29 (2026-05-21) — 영구 stale 무한 skip 결함 대응.
            # 종목 단위 5분 cooldown + 시간당 12회 cap 으로 강제 재시도 발화.
            # 13:21:41 마지막 시도 후 8분 영구 잔류 결함 (보유 005935 손절 평가 지연) 차단.
            last_at = None
            if hasattr(scheduler, "_stale_last_resubscribe_at"):
                last_at = scheduler._stale_last_resubscribe_at.get(ticker)

            if last_at is not None:
                age_secs = (_dt_mod.now(_KST_TZ) - last_at).total_seconds()
                if age_secs < STALE_FORCE_RETRY_AFTER_SECS:
                    # cooldown 미경과 — 기존 skip 동작 보존 (LMS 위험 차단, 무SEND).
                    # 관찰성(cycle218): priority_resubscribe(5분)가 `_stale_last_resubscribe_at`
                    # 를 갱신해 force_retry 600s 게이트가 지속 미충족되면 r 이 무한 climb(실측
                    # 131)하며 실제 부하와 무관한 오해 숫자를 남긴다. r>5 는 전부 동일 경로
                    # (force_retry `>MAX` / universe_guard `<=MAX` / diagnostics `<2` 임계)라
                    # MAX_STALE_RETRIES+1 홀드 = 행위 불변 + 로그 정직. force_retry FIRE 경로
                    # (age>=600 / last_at 부재)는 이 분기 밖이라 기존 r=0 리셋 보존.
                    scheduler._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1
                    skipped_giveup += 1
                    continue
            else:
                # `_stale_last_resubscribe_at` 부재 = 영구 stale 의심 첫 진입.
                # age=infinity 로 간주 → 즉시 1회 시도.
                age_secs = float("inf")

            # 시간당 cap 가드 — 60분 슬라이딩 윈도우
            if not hasattr(scheduler, "_stale_force_retry_history"):
                scheduler._stale_force_retry_history = {}
            history = scheduler._stale_force_retry_history.setdefault(ticker, [])
            hour_ago = _dt_mod.now(_KST_TZ) - timedelta(hours=1)
            # 만료 항목 evict (60분 이전)
            history[:] = [t for t in history if t > hour_ago]

            if len(history) >= STALE_FORCE_RETRY_HOURLY_CAP:
                # 시간당 cap 초과 — LMS / 앱키 정지 위험 차단
                force_retry_cap_blocked += 1
                logger.warning(
                    "[stale_force_retry_cap] ticker=%s attempts_in_hour=%d "
                    "— LMS 위험 차단 skip",
                    ticker, len(history),
                )
                # 사이클 72 hotfix A4: write_log 제거 — logger.warning → _DbLogHandler 위임 단일 INSERT
                skipped_giveup += 1
                continue

            # 강제 재시도 발화
            # 사이클 29-R3 — sub_priority/sub_bypass 분기 적용 (HIGH/LOW)
            age_disp = f"{age_secs:.0f}s" if age_secs != float("inf") else "inf"
            try:
                await kis_ws_pool.unsubscribe_in_pool(tick_tr_id, ticker)
                await asyncio.sleep(0.05)
                await kis_ws_pool.subscribe(
                    tick_tr_id, ticker,
                    priority=sub_priority, bypass_limit=sub_bypass,
                )
                # 핵심: 카운터 0 리셋 (영구 stale 의심 해제 → 신규 사이클 시작).
                # 다음 사이클부터 다시 1~5회 정상 분기로 자연 회복.
                scheduler._stale_retry_count[ticker] = 0
                # 시각 갱신 + history 등록
                if hasattr(scheduler, "_stale_last_resubscribe_at"):
                    scheduler._stale_last_resubscribe_at[ticker] = _dt_mod.now(_KST_TZ)
                history.append(_dt_mod.now(_KST_TZ))
                force_retry_count += 1

                logger.info(
                    # 🔴 cycle293 §9-B — 이 마커의 건수는 **배포 전후 합산 금지**다.
                    # 전용 채널로 옮긴 종목은 프레임이 와서 stale 을 벗어나므로
                    # 감소가 정상이다(cycle252 기준선과 다른 것을 잰다).
                    "[stale_force_retry] ticker=%s retries=%d last_resub_age=%s "
                    "— 강제 재시도 + 카운터 리셋",
                    ticker, retry, age_disp,
                )
                # 사이클 72 hotfix A2: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
            except Exception:
                logger.exception("[stale_force_retry] 강제 재시도 실패: %s", ticker)

            await asyncio.sleep(0.05)  # Rate Limit 보호
            continue

        # 1~5회 — 첫 stale 즉시 강제 재등록 (KIS 정상 "신규 등록" 패턴, 재SEND 0건)
        # KIS 공식 답변: "기등록한 사항을 재등록하지 않도록" (LMS + 앱정보 이용중지 위험)
        # 사이클 29-R3 — sub_priority/sub_bypass 분기 적용 (사이클 25-B 패턴 K stale watcher 확장)
        try:
            await kis_ws_pool.unsubscribe_in_pool(tick_tr_id, ticker)
            await asyncio.sleep(0.05)
            await kis_ws_pool.subscribe(
                tick_tr_id, ticker,
                priority=sub_priority, bypass_limit=sub_bypass,
            )
            force_reregistered += 1
            # 사이클 28 — 강제 재등록 직후 시각 갱신 (진단 로그 출처).
            # 사전 init 누락 인스턴스(테스트 `__new__` 호출 등) 보호.
            if hasattr(scheduler, "_stale_last_resubscribe_at"):
                scheduler._stale_last_resubscribe_at[ticker] = _dt_mod.now(_KST_TZ)
        except Exception:
            logger.exception("[stale_watcher] 강제 재등록 실패: %s", ticker)

        await asyncio.sleep(0.05)  # Rate Limit 보호

    # 사이클 74 옵션 C 조건부 aggregation: [stale_watcher] 정상 흐름 INFO → 5분 collector 흡수
    record_stale_watcher_check({
        "subscribed": len(subscribed),
        "stale": len(stale_tickers),
        "force_reregistered": force_reregistered,
        "skipped_giveup": skipped_giveup,
        "force_retried": force_retry_count,
        "cap_blocked": force_retry_cap_blocked,
        "no_feed_skipped": no_feed_skipped,
    })
    # 사이클 72 hotfix A3: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
    # 사이클 74: 직접 logger.info("[stale_watcher] subscribed=...") 제거 → collector 흡수
    # stale_count > 0 시 individual [stale_watcher_detail] 보존 (사이클 73 영속, 하단 분기)

    # 사이클 28 — [stale_watcher_detail] 세션별 분포 + 종목 cap 20 (별도 행, G1 호환)
    # Q4=B (사이클 60 답습하지 않는 유일 영역) — 직접 호출 (1 hop 단축, wrapper 우회)
    emit_stale_session_detail(scheduler, stale_tickers, now)
    await _observe_no_feed_held(no_feed_held_cohort, subscribed, _dt_mod.now(_KST_TZ))


def _collect_low_desired(scheduler: Any) -> tuple[set[str], set[str]]:
    """cycle240 — LOW desired 소스 2종 (breakout, momentum). 각각 실패 시 빈 set.

    08-31 포렌식 결함 ⓑ(5분 우선 재구독 핑퐁) 시정 — `resubscribe_stale_priority` 의
    LOW 후보를 이 함수가 반환하는 desired 집합과 교집합한다(호출부 §2.2 참조).

    - breakout = `scheduler._collect_breakout_tickers()` — VB/LTV/BFB/VCP scanned
      ∖ `_universe_excluded_today` (scheduler **소유** 소스 = 활성 게이트의 유일 근거.
      인스턴스 메서드 호출뿐 — scheduler 정적 import 0, D-1 동형).
    - momentum = `scanner._last_scan_result` — 같은 `_scan_loop` 이터레이션의
      `scan_stocks()` 결과. **가산 전용**(활성 판정 불참 — 모듈 전역 잔여값이 행위를
      뒤집지 못하게).

    await 0 · DB 접근 0 · 예외 전파 0 (호출부/헬퍼 내부 모두 try 로 흡수).
    """
    breakout: set[str] = set()
    momentum: set[str] = set()
    try:
        breakout = set(scheduler._collect_breakout_tickers() or [])
    except Exception:
        breakout = set()
    try:
        from src.engine import scanner as _scanner_mod  # lazy — patch("src.engine.scanner._last_scan_result") 호환
        momentum = set(getattr(_scanner_mod, "_last_scan_result", None) or [])
    except Exception:
        momentum = set()
    return breakout, momentum


async def resubscribe_stale_priority(scheduler: Any, cap: int = 10) -> list[str]:
    """`_scan_loop` 5분 stale 우선순위 재구독 (사이클 25-B 우선순위 분리 영속).

    사이클 63 Phase 2-A3 (2026-06-05): scheduler.py L2690~L2789 그대로 이주.
    self.* → scheduler.* 치환만. 행위 변경 0건 (refactor).

    사이클 66 (2026-06-06) — cap=10 결함 시정 (카드 #5 HIGH):
    - 사이클 63 K-2 결함 confirm → 사이클 66 K-2 시정 confirm (Q6-4 의미 전환).
    - `targets = stale_tickers[: cap]` 결함 패턴 (priority 분리 *전* cap 적용) 영구 제거.
    - HIGH (positions ∪ next_day_clear) 절대 보장 + LOW 잔여 cap 채움.
    - HIGH > cap 시 cap 위반 허용 + WARNING 로그 (Q3 옵션 A 운영 가시화).
    - try/except 4중 가드 통일 — `_check_and_resubscribe_stale` L820-833 본체 패턴 답습 (Q2).
    - 사이클 29 005935 사고 패턴 (HIGH 종목 cap 밖 잘림 8분 영구 잔류 + LMS chain) 영구 차단.

    사이클 25-B (2026-05-20) — positions/next_day_clear 는 HIGH, 그 외 후보는 LOW:
    - 기존: 모든 stale 에 HIGH+bypass_limit=True → VB/LTV 후보 stale → 메인 승격
      → 2026-05-20 14:58 메인 sub=11 fresh=0 stale=11 silent inactive 사고
    - 변경: positions/next_day_clear = HIGH (보유·익일청산 보장 절대 유지)
            그 외 후보 = LOW (보조 분산, 사이클 24 자동 회복과 시너지)

    사이클 240 (2026-09-02) — 08-31 포렌식 결함 ⓑ(5분 우선 재구독 핑퐁) 시정:
    - 원인: LOW 후보 소스가 `ticker_last_tick` **전수**라 매도·후보이탈 종목도 20:10
      정산까지 stale 자격 유지 → `_scan_loop` 같은 이터레이션 안에서
      `delta_unsubscribe_dropped`(빼기) ↔ 여기(되살리기) 가 무한 핑퐁.
    - 시정: priority 분리(HIGH/LOW) **직후**, cycle216 A(동시호가)/B(throttle)/cap
      **앞**에 `low_targets` 만 `_collect_low_desired()` 의 desired 집합(breakout ∪
      momentum)과 교집합한다. HIGH 는 `low_targets` 에 애초에 들어가지 않으므로
      필터 경로를 지나지 않는다(구조적 면제). 활성 게이트 = breakout 비어있지 않음
      ∧ HIGH 수집 무예외(momentum 은 게이트 불참) — 게이트 off 시 현행 byte 동일
      (fail-open). 관측 = `[stale_priority_resubscribe]` 기존 INFO 1행에
      `desired_low=` / `filtered_not_desired=` / `filtered_sample=` 3필드 확장.

    Returns:
        재구독한 ticker 리스트 (호출 카운트 + 회귀 검증용)
    """
    import sys as _sys

    # 사이클 61 패턴 답습 — D-1 AST 가드 + D-2 sys.modules.get 출현 수 가드.
    # datetime 접근은 scheduler 모듈 네임스페이스 우선 참조 (freezegun patch 호환).
    # kis_ws_pool 은 src.realtime.websocket_pool 모듈 직접 참조 (테스트 patch 호환):
    #   `patch("src.realtime.websocket_pool.kis_ws_pool")` 패치 작동 보장.
    _sched_mod = _sys.modules.get("src.engine.scheduler")
    if _sched_mod is not None and hasattr(_sched_mod, "datetime"):
        _dt_mod = _sched_mod.datetime
    else:
        from datetime import datetime as _dt_mod  # type: ignore[assignment]

    # kis_ws_pool — websocket_pool 모듈에서 직접 접근 (테스트 patch 경로 호환)
    _wsp_mod = _sys.modules.get("src.realtime.websocket_pool")
    if _wsp_mod is not None:
        kis_ws_pool = _wsp_mod.kis_ws_pool
    else:
        from src.realtime.websocket_pool import kis_ws_pool  # type: ignore[assignment]

    # cycle293 — 채널 판정은 `_actual_or_desired_tick_tr_id`(위) 단일 지점.
    from src.engine.scanner import KST_TZ as _KST_TZ, ticker_last_tick

    now = _dt_mod.now(_KST_TZ)
    threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
    min_dt = _dt_mod.min.replace(tzinfo=_KST_TZ)

    # 사이클 149 (2026-06-16) — VI/거래정지 stale 회피 hook (`check_and_resubscribe_stale` 답습).
    try:
        from src.engine.market_operation_monitor import is_ticker_stale_excluded as _is_market_op_excluded
    except Exception:
        def _is_market_op_excluded(t: str) -> bool:  # type: ignore[no-redef]
            return False

    def _market_op_skip(t: str) -> bool:
        try:
            return bool(_is_market_op_excluded(t))
        except Exception:
            return False

    # sorted 로 결정적 순서 보장 — cap 적용 시 동일 입력에 동일 출력
    stale_tickers = sorted(
        t for t, last in ticker_last_tick.items()
        if (now - last if isinstance(last, datetime) else now - min_dt) > threshold
        and not _market_op_skip(t)
    )

    if not stale_tickers:
        return []

    # 사이클 25-B + 사이클 66 (2026-06-06) — HIGH 보장 대상 집합 (try/except 4중 가드 통일 Q2)
    # Q6-4 의미 전환: 사이클 63 K-2 결함 confirm → 사이클 66 K-2 시정 confirm.
    # 사이클 29 005935 사고 패턴 (HIGH 종목 cap 밖 잘림 8분 영구 잔류 + LMS chain) 영구 차단.
    high_tickers: set[str] = set()
    _high_collect_ok = True                          # cycle240 — HIGH 수집 실패 시 필터 fail-open
    try:
        for s in scheduler.registry.all():
            try:
                high_tickers.update(s.state.positions.keys())
            except Exception:
                _high_collect_ok = False
    except Exception:
        # registry 미주입 인스턴스(테스트 __new__) 보호 — 모두 LOW 로 처리
        _high_collect_ok = False
    try:
        high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
    except Exception:
        _high_collect_ok = False

    # Q1 시정: priority 분리 *먼저*, cap 적용 *나중* (HIGH 절대 우선)
    high_targets = [t for t in stale_tickers if t in high_tickers]
    low_targets = [t for t in stale_tickers if t not in high_tickers]

    # cycle240 — LOW desired 교집합 (재구독 핑퐁 차단). HIGH 는 이 블록을 지나지 않는다.
    try:
        _breakout_desired, _momentum_desired = _collect_low_desired(scheduler)
    except Exception:
        _breakout_desired, _momentum_desired = set(), set()
    _filter_active = bool(_breakout_desired) and _high_collect_ok   # momentum 은 게이트 불참(AST G-240-5)
    _desired_low = _breakout_desired | _momentum_desired
    filtered_not_desired: list[str] = []
    if _filter_active and low_targets:
        filtered_not_desired = [t for t in low_targets if t not in _desired_low]
        low_targets = [t for t in low_targets if t in _desired_low]

    # 사이클 216 보강 A — 동시호가 LOW-scoped skip (HIGH 는 면제, cycle162 전체
    # early-return 과 달리 LOW 후보만 비운다. 09:00 갭개장 손절 대비 HIGH 유지).
    try:
        from src.engine.session import session_tracker as _session_tracker
        _is_call_auction = _session_tracker.is_call_auction_now(now)
    except Exception:
        _is_call_auction = False
    if _is_call_auction and low_targets:
        logger.warning(
            "[stale_skip_call_auction_priority] low=%d skip — 동시호가 LOW 재구독 회피 (HIGH 유지)",
            len(low_targets),
        )
        low_targets = []

    # 사이클 216 보강 B — LOW-only per-ticker throttle (HIGH 는 완전 면제,
    # 300s 케이던스 자체가 LMS-safe + 손절 직결). throttle → cap 순서 (계약).
    _last_resub = getattr(scheduler, "_stale_last_resubscribe_at", {}) or {}
    low_targets = [
        t for t in low_targets
        if not (
            isinstance(_last_resub.get(t), datetime)
            and (now - _last_resub[t]).total_seconds() < RESUBSCRIBE_THROTTLE_SECS
        )
    ]

    # Q3 시정: HIGH > cap 시 cap 위반 허용 + WARNING 로그 (운영 가시화)
    if len(high_targets) > cap:
        logger.warning(
            "[stale_priority_resubscribe_cap_exceeded] high_count=%d cap=%d "
            "tickers=%s — HIGH 종목 cap 위반 허용 (보유/익일청산 절대 보장)",
            len(high_targets), cap, high_targets,
        )

    targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
    resubscribed: list[str] = []

    # 사이클 217 — 구독 상태 스냅샷 1회 (unsubscribe SEND 가드 소스).
    # 미구독(split-brain/stale 후보) 종목에 unsubscribe SEND 를 보내면 KIS 가
    # OPSP0003(UNSUBSCRIBE ERROR not found!) 을 반환 (ERROR 스팸 회피).
    try:
        subscribed_snapshot = kis_ws_pool.get_subscribed_tickers()
    except Exception:
        subscribed_snapshot = set()

    for ticker in targets:
        # positions/next_day_clear → HIGH (메인 절대 보장, bypass 한도 무시)
        # 그 외 후보 → LOW (보조 세션 분산 우선, 사이클 25-B)
        if ticker in high_tickers:
            sub_priority = "HIGH"
            sub_bypass = True
        else:
            sub_priority = "LOW"
            sub_bypass = False
        # cycle293 — 해제·재등록이 같은 tr_id 를 쓴다(채널 전환 경로 아님).
        tick_tr_id = _actual_or_desired_tick_tr_id(kis_ws_pool, ticker, sub_priority)
        try:
            if ticker in subscribed_snapshot:
                await kis_ws_pool.unsubscribe_in_pool(tick_tr_id, ticker)
                await asyncio.sleep(0.05)
            else:
                try:
                    kis_ws_pool._ticker_to_session.pop(ticker, None)
                    # cycle293 §5-C — 병행 dict 동행 pop. 한쪽만 남으면 유령
                    # 항목이 이중 채널 오탐·미탐을 동시에 만든다.
                    _t2tr = getattr(kis_ws_pool, "_ticker_to_tr_id", None)
                    if isinstance(_t2tr, dict):
                        _t2tr.pop(ticker, None)
                except Exception:
                    pass
            await kis_ws_pool.subscribe(
                tick_tr_id, ticker,
                priority=sub_priority, bypass_limit=sub_bypass,
            )
            resubscribed.append(ticker)
            # 사이클 28 — 강제 재구독 시각 갱신 (진단 로그 출처).
            # 사전 init 누락 인스턴스(테스트 `__new__` 호출 등) 보호.
            if hasattr(scheduler, "_stale_last_resubscribe_at"):
                scheduler._stale_last_resubscribe_at[ticker] = _dt_mod.now(_KST_TZ)
        except Exception:
            logger.exception("[stale_priority_resubscribe] 재구독 실패: %s", ticker)
            continue
        await asyncio.sleep(0.05)  # Rate Limit 보호

    logger.info(
        "[stale_priority_resubscribe] count=%d tickers=%s desired_low=%d "
        "filtered_not_desired=%d filtered_sample=%s",
        len(resubscribed), resubscribed,
        len(_desired_low) if _filter_active else 0,
        len(filtered_not_desired), filtered_not_desired[:10],
    )
    # 사이클 72 hotfix A5: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT

    return resubscribed
