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
from src.engine.daily_emit_cap import DailyEmitCap

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환)

# 사이클 216 — LOW-only 재구독 throttle (동일 종목 중복 재발사 차단).
# 반드시 < 300s(`resubscribe_stale_priority` 5분 주기 자체) — 자기막힘/cycle215 원복 방지.
RESUBSCRIBE_THROTTLE_SECS = 3 * STALE_FRESHNESS_SECS  # = 180


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
# 날짜 키 자기 리셋(`_reset_daily_state` 훅 미의존 — 이 파일은 scheduler.py 무접촉
# 규약이라 scheduler 의 정산 훅에 배선할 수 없다. strategy_base.py `_budget_clamp_day`
# 등 기존 모듈 전역 self-reset 선례 답습).
_no_feed_held_logged: DailyEmitCap[str] = DailyEmitCap[str]()
_no_feed_held_day: str = ""
_NO_FEED_HELD_KEY = "no_feed_held"


def _maybe_emit_no_feed_held(tickers: set, now: datetime) -> None:
    """HIGH(보유/익일청산) ∩ no_feed 가 비어있지 않으면 WARNING 1회/일.

    peek→로그→mark(cycle226 D-3 순서 답습) — mark 를 먼저 하면 로그 자기실패가
    그날 관측을 지운다. 판정 자체(호출부의 `high_tickers` 계산)는 cap 밖 —
    cap 은 로그 빈도만 조절한다.

    관측기 자기 예외는 **여기서 흡수**한다(tester F-1, cycle237/242 "emit 헬퍼는
    예외 흡수 · 행위는 cap 밖" 계약). 호출부는 `if not stale_tickers: return` 과
    stale 루프 **앞**이라, 여기서 던지면 그 사이클의 HIGH 재등록까지 통째로 빠진다
    (`_stale_watcher_loop` 이 흡수해 프로세스는 살지만 결함 지속 시 120s 마다 반복).
    흔적은 debug 스택만 — `logger.warning` 자체가 깨진 상황이라 WARNING 승격은 무의미.
    """
    global _no_feed_held_day
    try:
        today = now.date().isoformat()
        if _no_feed_held_day != today:
            _no_feed_held_day = today
            _no_feed_held_logged.reset_daily()

        if not _no_feed_held_logged.should_emit(_NO_FEED_HELD_KEY):
            return
        logger.warning(
            "[no_feed_held] tickers=%s — WS 프레임 0(KRX 단독, H0UNCNT0 무송출). "
            "손절 평가는 REST 폴(donchian/kojiro 60s 09:05~15:20)만. tick 전략 보유면 사각",
            sorted(tickers),
        )
        _no_feed_held_logged.mark_emitted(_NO_FEED_HELD_KEY)
    except Exception:
        # 가장 안쪽은 어떤 경우에도 조용히 통과한다 (cycle237 `_trace_observer_failure`).
        try:
            logger.debug("[no_feed_held] emit 실패 — 관측 침묵, 행위 무관", exc_info=True)
        except Exception:
            pass


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

    from src.engine.scanner import KST_TZ as _KST_TZ, TICK_TR_ID, ticker_last_tick

    # 사이클 13-E (2026-05-18): 메인 단독 → 풀 전체로 확장
    subscribed = kis_ws_pool.get_subscribed_tickers()
    if not subscribed:
        return

    # cycle252 — no_feed 분류 신선도 보장(§2(a)). 예외는 흡수 — 관측 개선이
    # 사이클 완주를 막으면 안 된다(4중 안전망의 한 축, W6).
    try:
        await no_feed_registry.ensure_fresh(subscribed)
    except Exception:
        logger.debug(
            "[no_feed_registry] ensure_fresh 실패 — 이번 사이클 no_feed 판정 skip"
        )

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

    def _is_within_grace(t: str) -> bool:
        """grace 영역 영구 영속 판정 영구 영속.

        첫 시세 입수 후 영역 (`ticker_last_tick[t]` 존재) = False (grace 미적용, 기존 60s 영속).
        첫 시세 입수 *전* + ACK 미확인 = False (race 보호, 기존 60s 영속).
        첫 시세 입수 *전* + ACK 확인 + grace 이내 = True (stale 판정 skip).
        """
        if t in ticker_last_tick:
            return False  # 첫 시세 입수 후 = grace 미적용 (G-GRACE-7 영속)
        ack_at = ack_map.get((TICK_TR_ID, t))
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
    # 사이클 135 grace + 사이클 149 VI 패턴 답습 = stale 종목 *전체* skip + WARNING 1행.
    try:
        from src.engine.session import session_tracker as _session_tracker
        _is_call_auction = _session_tracker.is_call_auction_now(now)
    except Exception:
        _is_call_auction = False

    if _is_call_auction:
        # 동시호가 시간대 → stale 판정 *전체* 지연 (사이클 38 명문화 영속 — stale 판정 지연만)
        logger.warning(
            "[stale_skip_call_auction] subscribed=%d — 동시호가 시간대 stale 회피 "
            "(체결 부재 정상 영역)",
            len(subscribed),
        )
        # 누적 retry 카운터 보존 (fresh 회복 케이스 분기 미진입 = 정상 영역 영구 영속)
        return

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

    # cycle252(c) — HIGH ∩ no_feed 관측. `is_no_feed` 호출은 동시호가 조기
    # return **뒤**(위 262행)이므로 W9(동시호가 사이클에서 판정 0회)를 만족한다.
    if high_tickers:
        no_feed_high = {t for t in high_tickers if no_feed_registry.is_no_feed(t)}
        if no_feed_high:
            _maybe_emit_no_feed_held(no_feed_high, now)

    if not stale_tickers:
        # 모두 fresh — 누적 retry 카운터 리셋 (회복 케이스)
        scheduler._stale_retry_count.clear()
        # 사이클 28 — _stale_last_resubscribe_at 동행 clear (G5 cleanup 동행).
        # getattr 폴백으로 사전 init 누락 인스턴스(테스트 `__new__` 호출 등) 보호.
        if hasattr(scheduler, "_stale_last_resubscribe_at"):
            scheduler._stale_last_resubscribe_at.clear()
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
        if sub_priority == "LOW" and no_feed_registry.is_no_feed(ticker):
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
                await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)
                await asyncio.sleep(0.05)
                await kis_ws_pool.subscribe(
                    TICK_TR_ID, ticker,
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
            await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)
            await asyncio.sleep(0.05)
            await kis_ws_pool.subscribe(
                TICK_TR_ID, ticker,
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

    from src.engine.scanner import KST_TZ as _KST_TZ, TICK_TR_ID, ticker_last_tick

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
        try:
            if ticker in subscribed_snapshot:
                await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)
                await asyncio.sleep(0.05)
            else:
                try:
                    kis_ws_pool._ticker_to_session.pop(ticker, None)
                except Exception:
                    pass
            await kis_ws_pool.subscribe(
                TICK_TR_ID, ticker,
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
