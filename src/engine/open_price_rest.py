"""cycle272 (2026-09-10) — `main` 목표가 기준가를 KRX REST 로 확정하는 leaf.

## ⚠️ 이 leaf 는 관측 leaf 가 아니라 **행위 leaf** 다

cycle264 `open_price_observe.py` 는 "행위 변경 0" 이 첫 계약인 관측 leaf 였다.
이 모듈은 반대다 — **목표가를 실제로 세운다.** `never-raise` 는 **관측(로그
emit)에만** 적용된다. 확보 실패(`rest_zero`/`rest_error`)는 침묵하지 않고
**계수·기록**한다 — 침묵하면 "REST 가 전부 일치했다" 와 "REST 가 N 종목에서
아무것도 못 줬다" 가 구별되지 않는다(cycle237 C237-L2-1 동형).

## 왜

통합 채널 `H0UNCNT0` `fields[7]`(세션 시가 — 프리장 체결이 있었으면 프리장
시가)이 실어 오는 값으로 `board=="main"` 목표가를 긋던 것을 멈춘다. `main`
기준가는 **KRX REST `stck_oprc`(`J`) 단일 출처**이고, 그 값이 프린트될 때까지
유계 재시도로 기다렸다가 프린트된 값으로만 선을 긋는다. 못 기다린 종목은
그 시점 매수 불가 — 틀린 목표선으로 들어간 포지션은 손절선까지 틀리지만,
안 들어간 종목은 기회비용만 남는다(자문 §0/§2).

## 좁은 목 — `on_open_price_confirmed` 게이트

`main` 기준가를 만드는 경로(스케줄러 1차 WS 폴링 · 2차 REST 폴백 · 전략 인라인
확정)가 전부 그 setter 로 수렴한다. `reject_untrusted_main_basis` 가 그 setter의
첫 문장에서 출처를 가른다 — `source` 기본값이 `"ws"`(불신)이므로 WS 3 호출부는
**한 글자도 고치지 않아도** 거부된다(`check_buy_signal` byte 동일 = cycle264
`_STRATEGY_PINS` 6개 불변 = 무접촉 6종의 기계적 증거).

②(`source in _TRUSTED_MAIN_SOURCES`)가 ③(`try`/`params` 접근)보다 **앞**이라는
것이 안전 계약이다 — 게이트가 무슨 이유로 터지든 REST 경로는 구조적으로
면역이고, "게이트 고장 = 종일 목표가 0" 이라는 P0-1 계열 사고가 성립하지 않는다.

## 라운드 일정

R1 = 09:00:35(09:00:30 프린트 무릎 + 5초, `_swing_rest_poll_loop` 정각 회피) →
30초 간격 **19라운드**(마지막 09:09:35) → 이후 5분 간격 15:20 까지(첫 slow
09:14:35 — 재-prepare 회수 + 킬스위치 카나리아의 종일 채널). 라운드 시각은
`_swing_buy_poll_loop`(09:05 정각)·cycle264 대조 배치(09:05:30)와 30초 격자상
겹치지 않는다. 09:05:00 이후는 `owns_board()` 가 False 로 떨어져 스케줄러의 기존
1차 WS 폴링·2차 REST 폴백이 백스톱으로 **함께** 돈다(중복 호출은 `_is_confirmed`
멱등으로 무해).

## 안전 계약

- **never-raise (관측만)** — 로그 emit·카나리아는 전부 `try/except` +
  `observer_trace.trace_observer_failure`(never-raise). cap 은
  `daily_emit_cap.KstDailyEmitCap` 재사용(신규 cap 클래스 정의 금지).
- **`logger` 만 쓴다** — DB 직접 기록 헬퍼/`await` 금지(20:10 리포트가
  `system_logs` 를 파싱한다).
- **`scanner.ticker_prices` 읽기 전용** — shadow 값(`[main_rest_basis_confirmed]`
  의 `ws_open`/`ws_src`)을 위해 REST 조회 **직전**에만 읽는다. `scanner.py` 는
  8영역이라 어떤 전역도 대입하지 않는다.
- **8영역 접촉 0** — `risk.py`/`order_engine.py`/`session.py`/`scanner.py`/
  `strategy_registry.py`/`src/api/order.py`/`src/realtime/**`/`src/auth/**`
  전부 무접촉. `session.py` 의 공개 헬퍼(`get_tradable_boards`/`MarketBoard`)는
  읽기 전용으로 import 한다(scheduler 의 기존 사용 패턴 답습).
"""
from __future__ import annotations

import asyncio
import logging
import time as _wall_clock
from datetime import datetime, timedelta, timezone
from datetime import time as _dtime

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# 킬스위치 (전략별 DEFAULT_PARAMS 키, cycle272 D-7)
# ---------------------------------------------------------------------------
MODE_KEY = "open_price_scope_mode"
MODE_ENFORCE = "enforce"
MODE_OFF = "off"

_MAIN_BOARD = "main"
# 채널 분리(P1-7 B) 뒤 "ws_krx" 가 여기에 꽂히는 seam. 지금은 REST 하나뿐이다.
_TRUSTED_MAIN_SOURCES = ("rest",)
_BASIS_STRATEGIES = ("volatility_breakout", "long_tail_volatility")

# ---------------------------------------------------------------------------
# 라운드 일정 상수 (자문 §2/§3-c, 실측 기반)
# ---------------------------------------------------------------------------
TIME_MAIN_REST_BASIS_R1 = _dtime(9, 0, 35)
MAIN_REST_BASIS_ROUND_INTERVAL_S = 30.0
# fast 19회 = 09:00:35 ~ **09:09:35** 를 30초 간격으로 **연속** 커버한다(cycle276 후속).
#
# 종전 9회는 09:04:35 에 끝나고 첫 slow 라운드가 09:09:35 였다 — 그 5분을 메우는 주체가
# 하나도 없었다. `owns_board` 가 09:05:00 에 스케줄러로 이관하지만 스케줄러의 재시도
# 경로(`_confirm_breakout_open_prices_if_pending`)는 `_scan_loop` 안에 있고 그 루프는
# **09:30**(`TIME_SCAN_START`)에 시작한다. 09-11 실측 노출은 0건(98종목 중 97이 R1
# 09:00:35 확정, 1종목이 09:02:35, `unresolved` 0행)이었지만 구조적 구멍이라 메운다.
#
# 비용 — 라운드는 `_pending_main_tickers` 만 조회하므로 전 종목이 확정된 뒤의 라운드는
# REST 콜 0 이다(09-11 라운드 6~9 실측 `calls=0 elapsed_ms=0`). 늘어난 10라운드는
# 평상시 빈 루프 10회이고, 결손이 남은 날에만 실제 콜이 나간다.
#
# 09:05:00 이관(`TIME_MAIN_REST_BASIS_HANDOFF`)은 **바꾸지 않는다** — 이관은 스케줄러가
# 다시 참여하는 시점이고 leaf 의 라운드와 별개 축이다. 09:05 이후 두 주체가 같은 종목에
# REST 를 중복 호출할 수 있으나, 확정은 `_is_confirmed` 로 멱등이라(이미 확정된 종목은
# pending 목록에서 빠지고, 같은 값 재확정도 목표가를 바꾸지 않는다) 무해하다.
MAIN_REST_BASIS_FAST_ROUNDS = 19
MAIN_REST_BASIS_SLOW_INTERVAL_S = 300.0
TIME_MAIN_REST_BASIS_STOP = _dtime(15, 20)
TIME_MAIN_REST_BASIS_HANDOFF = _dtime(9, 5, 0)
_TICKER_SLEEP_S = 0.05
_ROUND_WALL_CLOCK_MAX_S = 45.0
_READY_POLL_INTERVAL_S = 2.0
_READY_POLL_MAX_S = 90.0

# ---------------------------------------------------------------------------
# cap — 마커마다 별개 인스턴스(cycle245 R1 사각 선례). 전부 `reset_main_rest_basis_caps()`
# 로 강제 초기화된다(테스트·운영 훅).
# ---------------------------------------------------------------------------
_config_canary_cap: "KstDailyEmitCap[tuple[str, str, str]]" = KstDailyEmitCap()
_confirmed_marker_cap: "KstDailyEmitCap[tuple[str, str]]" = KstDailyEmitCap()
_unresolved_cap: "KstDailyEmitCap[tuple[str, str]]" = KstDailyEmitCap()


def reset_main_rest_basis_caps() -> None:
    """cycle272 마커 3종의 cap 을 전부 강제 초기화한다(테스트·운영 훅)."""
    global _config_canary_cap, _confirmed_marker_cap, _unresolved_cap
    _config_canary_cap = KstDailyEmitCap()
    _confirmed_marker_cap = KstDailyEmitCap()
    _unresolved_cap = KstDailyEmitCap()


# ===========================================================================
# 모드 해석
# ===========================================================================
def resolve_mode(params) -> str:
    """`open_price_scope_mode` 해석. `off` 로 해석되는 것은 대소문자·공백 무시
    정확히 `off` 뿐이다 — 나머지(부재·`None`·빈값·오타·타입 이상·예외)는 전부
    `enforce`(사용자 D1 "체크할 필요가 없이 KRX 시가를 쓰는 게 원칙" 의 직역).
    """
    try:
        raw = params.get(MODE_KEY, MODE_ENFORCE)
    except Exception:
        return MODE_ENFORCE
    try:
        text = str(raw or MODE_ENFORCE).strip().lower()
    except Exception:
        return MODE_ENFORCE
    return MODE_OFF if text == MODE_OFF else MODE_ENFORCE


def _raw_mode_value(params):
    """카나리아 표시용 원문 값(정규화 전). 오타 롤백 실패를 눈에 띄게 한다."""
    try:
        return params.get(MODE_KEY, MODE_ENFORCE)
    except Exception:
        return MODE_ENFORCE


# ===========================================================================
# 게이트 — `on_open_price_confirmed` 첫 문장에서 호출된다
# ===========================================================================
# `reject_untrusted_main_basis` — `board=="main"` 확정을 `source` 신뢰 목록
# 기준으로 가른다. 순서가 계약이다(C5, AST 봉인) — 첫 두 문장(①·②)은 예외가
# 날 수 없는 순수 비교이고 **`params` 접근·`try` 보다 앞**이다(그래서 body[0]
# 은 docstring 이 아니라 바로 그 If 여야 한다). REST 경로(`source="rest"`)는
# 게이트가 무슨 이유로 터지든 이 순서 덕에 구조적으로 면역이다.
def reject_untrusted_main_basis(
    params,
    board,
    source,
    *,
    strategy_id: str = "",
    ticker: str = "",
    tick_open: int = 0,
    dest_logger=None,
) -> bool:
    if board != _MAIN_BOARD:                      # ① 순수 비교 — 예외 불가
        return False
    if source in _TRUSTED_MAIN_SOURCES:            # ② REST 는 params 접근 전에 통과
        return False
    try:
        mode = resolve_mode(params)
    except Exception:
        mode = MODE_ENFORCE                        # 선언된 기본값(fail-closed 방향)
    if mode == MODE_OFF:
        return False
    _emit_config_canary(
        strategy_id=strategy_id, mode=mode, raw=_raw_mode_value(params),
        emitter="gate", dest_logger=dest_logger,
    )
    return True


# ===========================================================================
# 마커 1 — `[main_rest_basis_config]` (gate|leaf 공용)
# ===========================================================================
def _canary_source_label(raw) -> str:
    try:
        return "default" if str(raw).strip().lower() == MODE_ENFORCE else "override"
    except Exception:
        return "override"


def _emit_config_canary(
    *, strategy_id: str, mode: str, raw, emitter: str, dest_logger=None, now=None,
) -> None:
    """`[main_rest_basis_config]` — 1회/(전략,모드,emitter)/일, **값-민감 cap**.

    장중 유일 롤백 수단인 `PUT /api/strategies/{id}/params` 는 in-memory
    `config.params` 를 즉시 덮는다. 단일 키면 그날 첫 행이 cap 을 소진해 바뀐
    값을 볼 마커가 0행이 된다(cycle245 R1 사각) — 그래서 키에 `mode` 를 넣는다.
    """
    log = dest_logger if dest_logger is not None else logger
    try:
        key = (strategy_id or "-", mode, emitter)
        if not _config_canary_cap.should_emit(key, now=now):
            return
        source = _canary_source_label(raw)
        log.info(
            "[main_rest_basis_config] emitter=%s strategy=%s mode=%s raw=%r source=%s",
            emitter, strategy_id or "-", mode, raw, source,
        )
        _config_canary_cap.mark_emitted(key, now=now)
    except Exception:
        try:
            trace_observer_failure(
                "[main_rest_basis_config]", strategy_id or "-", _config_canary_cap,
                now=now, dest_logger=log,
            )
        except Exception:  # pragma: no cover — 2차 예외까지 흡수
            pass


def _maybe_emit_leaf_config_canary(sid: str, strategy) -> None:
    """leaf 라운드가 매번 자기 전략의 **현재** 모드를 독립적으로 보고한다.

    `select_strategies()` 의 mode==enforce 필터 **밖**에서 돈다 — 그래야 운영자가
    `mode=off` 로 롤백한 날에도(그 전략은 더 이상 REST 스윕 대상이 아니어도)
    "지금 off 다" 라는 한 줄을 볼 수 있다(종일 킬스위치 카나리아 채널).
    """
    try:
        params = strategy.config.params
        if not _tradable_boards_include_main(sid, params):
            return
        pending = _pending_main_tickers(strategy)
        if not pending:
            return
        mode = resolve_mode(params)
        _emit_config_canary(
            strategy_id=sid, mode=mode, raw=_raw_mode_value(params), emitter="leaf",
        )
    except Exception:
        try:
            trace_observer_failure("[main_rest_basis_config]", sid, _config_canary_cap)
        except Exception:  # pragma: no cover
            pass


# ===========================================================================
# 마커 2 — `[main_rest_basis_round]`
# ===========================================================================
def _emit_round_marker(
    sid, round_no, total_rounds, kind, total, confirmed, pending,
    ok, zero, err, calls, elapsed_ms, truncated,
) -> None:
    try:
        logger.info(
            "[main_rest_basis_round] round=%d/%d kind=%s mode=%s strategy=%s board=main "
            "total=%d confirmed=%d pending=%d ok=%d zero=%d err=%d calls=%d "
            "elapsed_ms=%d truncated=%d",
            round_no, total_rounds, kind, MODE_ENFORCE, sid,
            total, confirmed, pending, ok, zero, err, calls, elapsed_ms, truncated,
        )
    except Exception:
        try:
            trace_observer_failure("[main_rest_basis_round]", sid, None)
        except Exception:  # pragma: no cover
            pass


# ===========================================================================
# 마커 3 — `[main_rest_basis_confirmed]`
# ===========================================================================
def _read_ws_shadow(ticker: str) -> tuple[int, str]:
    """REST 조회 **직전** `scanner.ticker_prices` 를 읽는다 — 읽기만 한다.

    = "옛 코드가 그 순간 썼을 값" — cycle264 대조 마커의 `delta_bp` 가 REST↔REST
    산술 항등으로 붕괴한 뒤 오염 규모를 계속 잴 수 있는 새 정본(shadow).
    """
    try:
        from src.engine import scanner
        info = scanner.ticker_prices.get(ticker) or {}
        open_price = int(info.get("open_price", 0) or 0)
    except Exception:
        return 0, "absent"
    return (open_price, "cache") if open_price > 0 else (0, "absent")


def _emit_confirmed_marker(
    sid: str, strategy, ticker: str, round_no: int,
    rest_open: int, ws_open: int, ws_src: str,
) -> None:
    """`[main_rest_basis_confirmed]` — 1회/(전략,종목)/일, 오염 규모의 새 정본.

    ⚠️ leaf 가 읽는 시각(REST 조회 직전)과 옛 코드가 읽던 시각(09:00:05~14)은
    다르다 — `[7]` 이 일-스코프 상수라 실무상 같은 값이지만 동일 시각 대조는
    아니다(판독문에 남길 것).
    """
    try:
        key = (sid, ticker)
        if not _confirmed_marker_cap.should_emit(key):
            return
        board_info = ((getattr(strategy, "_targets", None) or {}).get(ticker) or {}).get(
            "boards", {},
        ).get(_MAIN_BOARD) or {}
        target_rest = int(board_info.get("target_price", 0) or 0)
        offset = target_rest - rest_open
        target_ws = (ws_open + offset) if ws_open > 0 else 0
        delta_bp = ((rest_open - ws_open) / ws_open * 10000) if ws_open > 0 else 0.0
        logger.info(
            "[main_rest_basis_confirmed] strategy=%s ticker=%s board=main round=%d "
            "rest_open=%d ws_open=%d ws_src=%s delta_bp=%+.1f target_rest=%d target_ws=%d",
            sid, ticker, round_no, rest_open, ws_open, ws_src, delta_bp,
            target_rest, target_ws,
        )
        _confirmed_marker_cap.mark_emitted(key)
    except Exception:
        try:
            trace_observer_failure(
                "[main_rest_basis_confirmed]", f"{sid}|{ticker}", _confirmed_marker_cap,
            )
        except Exception:  # pragma: no cover
            pass


# ===========================================================================
# 마커 4 — `[main_rest_basis_unresolved]`
# ===========================================================================
def _emit_unresolved(sid: str, ticker: str, reason: str, rounds: int) -> None:
    """`[main_rest_basis_unresolved]` — 1회/(전략,종목)/일, 커버리지 손실 정본.

    0 이 아니면 "고치려다 매수를 잃고 있다" 는 뜻이다.
    """
    try:
        key = (sid, ticker)
        if not _unresolved_cap.should_emit(key):
            return
        logger.info(
            "[main_rest_basis_unresolved] strategy=%s ticker=%s board=main "
            "reason=%s rounds=%d",
            sid, ticker, reason, rounds,
        )
        _unresolved_cap.mark_emitted(key)
    except Exception:
        try:
            trace_observer_failure(
                "[main_rest_basis_unresolved]", f"{sid}|{ticker}", _unresolved_cap,
            )
        except Exception:  # pragma: no cover
            pass


# ===========================================================================
# 대상 전략 선별
# ===========================================================================
def _tradable_boards_include_main(sid: str, params) -> bool:
    try:
        from src.engine.session import MarketBoard, get_tradable_boards
        allowed = get_tradable_boards(sid, params)
        return MarketBoard(_MAIN_BOARD) in allowed
    except Exception:
        return False


def select_strategies(registry) -> list[tuple[str, object]]:
    """`_BASIS_STRATEGIES` 중 (i) `main ∈ tradable_boards` (ii) `mode==enforce`.

    **`config.enabled` 는 보지 않는다**(D-9 — 09-10 17:07 부로 VB·LTV 가
    `enabled=False` 여도 REST 확보·오염 shadow·게이트·부하가 검증돼야 금요일
    실측이 성립한다. 비활성 전략은 `check_buy_signal` 자체가 불리지 않으므로
    매매 위험은 0 이다).
    """
    out: list[tuple[str, object]] = []
    for sid in _BASIS_STRATEGIES:
        strategy = registry.get(sid)
        if not strategy:
            continue
        try:
            params = strategy.config.params
            if resolve_mode(params) != MODE_ENFORCE:
                continue
            if not _tradable_boards_include_main(sid, params):
                continue
        except Exception:
            continue
        out.append((sid, strategy))
    return out


def _pending_main_tickers(strategy) -> list[str]:
    """`_targets` 중 `board="main"` 이 아직 확정 안 된 종목."""
    targets = getattr(strategy, "_targets", None) or {}
    confirmed_map = getattr(strategy, "_open_confirmed", None) or {}
    out: list[str] = []
    for ticker in targets:
        states = confirmed_map.get(ticker)
        ok = states.get(_MAIN_BOARD, False) if isinstance(states, dict) else bool(states)
        if not ok:
            out.append(ticker)
    return out


def _has_any_pending_targets(registry) -> bool:
    try:
        for sid in _BASIS_STRATEGIES:
            strategy = registry.get(sid)
            if strategy and getattr(strategy, "_targets", None):
                return True
    except Exception:
        return False
    return False


# ===========================================================================
# 라운드 일정 (순수 함수 — 벽시계 무의존)
# ===========================================================================
def round_schedule() -> list[tuple[int, int, str, "_dtime"]]:
    """`(round_no, total, kind, KST 시각)` 전체 일정.

    fast = 09:00:35 부터 30초 간격 19회(마지막 **09:09:35**).
    slow = 마지막 fast 로부터 300초 간격(첫 slow 09:14:35), 15:20 을 넘지 않는다.

    ⚠️ fast 마지막 라운드가 `[main_rest_basis_unresolved]`(커버리지 손실 정본)를 쏘는
    자리다 — 그 발화 시각이 09:04:35 → 09:09:35 로 이동했다. 배포 전후의 unresolved
    행 수를 같은 코호트로 합산하지 말 것(cycle263 `skipped_fresh` 계열 사고).
    """
    anchor = datetime(2000, 1, 1, TIME_MAIN_REST_BASIS_R1.hour,
                       TIME_MAIN_REST_BASIS_R1.minute, TIME_MAIN_REST_BASIS_R1.second)
    fast: list[tuple[int, int, str, "_dtime"]] = []
    for i in range(MAIN_REST_BASIS_FAST_ROUNDS):
        dt = anchor + timedelta(seconds=i * MAIN_REST_BASIS_ROUND_INTERVAL_S)
        fast.append((i + 1, MAIN_REST_BASIS_FAST_ROUNDS, "fast", dt.time()))

    stop_dt = datetime(2000, 1, 1, TIME_MAIN_REST_BASIS_STOP.hour,
                        TIME_MAIN_REST_BASIS_STOP.minute, TIME_MAIN_REST_BASIS_STOP.second)
    last_fast = anchor + timedelta(
        seconds=(MAIN_REST_BASIS_FAST_ROUNDS - 1) * MAIN_REST_BASIS_ROUND_INTERVAL_S,
    )
    cur = last_fast + timedelta(seconds=MAIN_REST_BASIS_SLOW_INTERVAL_S)
    slow_times: list["_dtime"] = []
    while cur <= stop_dt:
        slow_times.append(cur.time())
        cur += timedelta(seconds=MAIN_REST_BASIS_SLOW_INTERVAL_S)

    total_slow = len(slow_times)
    slow = [(i + 1, total_slow, "slow", t) for i, t in enumerate(slow_times)]
    return fast + slow


# ===========================================================================
# `owns_board` — 스케줄러가 09:00:05~09:05:00 구간 main 확정을 leaf 에 양보한다
# ===========================================================================
def owns_board(strategy, board, *, now=None) -> bool:
    """`board=="main" ∧ mode=="enforce" ∧ now < 09:05:00`. 예외는 False(fail-open)."""
    try:
        if board != _MAIN_BOARD:
            return False
        if resolve_mode(strategy.config.params) != MODE_ENFORCE:
            return False
        current = now if now is not None else datetime.now(_KST)
        return current.time() < TIME_MAIN_REST_BASIS_HANDOFF
    except Exception:
        return False


# ===========================================================================
# 벽시계 seam + KIS seam
# ===========================================================================
def _monotonic() -> float:
    return _wall_clock.monotonic()


async def _fetch_stock_detail(ticker: str) -> dict:
    """KIS 개별시세 지연 import (`_confirm_breakout_open_prices` 선례 답습)."""
    from src.api.condition import fetch_stock_detail
    return await fetch_stock_detail(ticker)


def _parse_stck_oprc(detail) -> int:
    try:
        if not isinstance(detail, dict):
            return 0
        raw = detail.get("stck_oprc")
        if raw is None:
            return 0
        return int(raw)
    except Exception:
        return 0


def _safe_trace(marker: str, key: str) -> None:
    try:
        trace_observer_failure(marker, key, None)
    except Exception:  # pragma: no cover
        pass


# ===========================================================================
# 라운드 본체 — **행위**(목표가를 실제로 세운다)
# ===========================================================================
async def run_main_rest_basis_round(sched, *, round_no: int, total_rounds: int, kind: str) -> dict:
    """한 라운드 — 미확정 `main` 종목만 REST 로 스윕해 확정한다.

    라운드 본체는 통째로 `try/except Exception` 이고 `CancelledError` 는
    re-raise 한다(never-return 흡수 금지 — task 취소가 라운드에 갇히면 안 된다).
    """
    from src.engine import open_price_observe

    start_mono = _monotonic()
    stats = {
        "total": 0, "confirmed": 0, "pending": 0,
        "ok": 0, "zero": 0, "err": 0, "calls": 0,
        "elapsed_ms": 0, "truncated": 0,
    }
    try:
        registry = sched.registry

        # 종일 킬스위치 카나리아 — select 필터(enforce) 밖에서, 두 전략 모두 매번.
        for sid in _BASIS_STRATEGIES:
            strategy = registry.get(sid)
            if strategy:
                _maybe_emit_leaf_config_canary(sid, strategy)

        fetch_targets = select_strategies(registry)

        ticker_needed_by: dict[str, list[str]] = {}
        for sid, strategy in fetch_targets:
            for ticker in _pending_main_tickers(strategy):
                ticker_needed_by.setdefault(ticker, []).append(sid)

        distinct_tickers = sorted(ticker_needed_by)

        calls = ok = zero = err = 0
        truncated = 0
        attempt_reason: dict[str, str] = {}

        for ticker in distinct_tickers:
            if _monotonic() - start_mono > _ROUND_WALL_CLOCK_MAX_S:
                truncated = 1
                break

            ws_open, ws_src = _read_ws_shadow(ticker)

            try:
                detail = await _fetch_stock_detail(ticker)
            except asyncio.CancelledError:
                raise
            except Exception:
                calls += 1
                err += 1
                attempt_reason[ticker] = "rest_error"
            else:
                calls += 1
                rest_open = _parse_stck_oprc(detail)
                if rest_open > 0:
                    ok += 1
                    for sid in ticker_needed_by.get(ticker, ()):
                        strategy = registry.get(sid)
                        if not strategy:
                            continue
                        try:
                            strategy.on_open_price_confirmed(
                                ticker, rest_open, board=_MAIN_BOARD, source="rest",
                            )
                        except Exception:
                            continue
                        open_price_observe.mark_confirmed_via_rest(sid, ticker, _MAIN_BOARD)
                        _emit_confirmed_marker(
                            sid, strategy, ticker, round_no, rest_open, ws_open, ws_src,
                        )
                else:
                    zero += 1
                    attempt_reason[ticker] = "rest_zero"

            await asyncio.sleep(_TICKER_SLEEP_S)

        elapsed_ms = int((_monotonic() - start_mono) * 1000)

        agg_total = agg_confirmed = 0
        for sid, strategy in fetch_targets:
            confirmed_n, total_n = open_price_observe.count_board_confirmed(
                strategy, _MAIN_BOARD,
            )
            agg_total += total_n
            agg_confirmed += confirmed_n
            pending_n = total_n - confirmed_n
            if kind == "fast" or pending_n > 0:
                _emit_round_marker(
                    sid, round_no, total_rounds, kind,
                    total_n, confirmed_n, pending_n,
                    ok, zero, err, calls, elapsed_ms, truncated,
                )

        if kind == "fast" and round_no == total_rounds:
            for sid, strategy in fetch_targets:
                for ticker in _pending_main_tickers(strategy):
                    reason = attempt_reason.get(ticker, "no_tick")
                    _emit_unresolved(sid, ticker, reason, round_no)

        stats.update(
            total=agg_total, confirmed=agg_confirmed, pending=agg_total - agg_confirmed,
            ok=ok, zero=zero, err=err, calls=calls,
            elapsed_ms=elapsed_ms, truncated=truncated,
        )
        return stats
    except asyncio.CancelledError:
        raise
    except Exception:
        _safe_trace("[main_rest_basis_round]", f"{round_no}/{total_rounds}")
        stats["elapsed_ms"] = int((_monotonic() - start_mono) * 1000)
        return stats


# ===========================================================================
# task lifecycle
# ===========================================================================
async def _wait_for_ready_targets(sched) -> bool:
    """`_targets` 가 하나라도 채워질 때까지 짧게 폴링한다 — 타임아웃은 침묵하지 않는다.

    task 는 `_boot()` **완료 직후**(prepare **이후**)에 만들어진다. 그래서 정상
    부팅이면 즉시 True 다. 비어 있는 경우는 (a) `_boot()` prepare 가 KIS 장애로
    실패한 아침(07:59 재-prepare 가 나중에 채운다) (b) 09:00:35 이후 장중 재시작
    (cycle264 MEDIUM #6 동형) 둘뿐이다. **반환값이 False 여도 호출자는 일정 루프로
    낙하한다**(cycle272 tester MEDIUM #1) — 라운드 본체는 pending 0 이면 REST 콜 0 으로
    자연 no-op 이라 부작용이 없고, 07:59 재-prepare 뒤의 R1(09:00:35)이 정상 동작한다.
    타임아웃을 종결로 다루면 그날 VB·LTV `main` 목표가는 09:30 백스톱에서야 서서
    개장 돌파 창을 통째로 잃는다.
    """
    waited = 0.0
    while getattr(sched, "_running", False):
        if _has_any_pending_targets(sched.registry):
            return True
        if waited >= _READY_POLL_MAX_S:
            try:
                logger.info(
                    "[main_rest_basis_round] skipped reason=no_target waited_s=%.0f "
                    "— boot prepare 실패 또는 장중 재시작으로 _targets 가 아직 비어 있다; "
                    "일정 루프는 계속 돈다(침묵 금지, cycle224 교훈)",
                    waited,
                )
            except Exception:  # pragma: no cover
                pass
            return False
        await asyncio.sleep(_READY_POLL_INTERVAL_S)
        waited += _READY_POLL_INTERVAL_S
    return False


async def main_rest_basis_task_loop(sched) -> None:
    """일정(`round_schedule()`)을 순서대로 대기하며 라운드를 1회씩 부른다.

    ⚠️ `advance_if_passed=True` 금지 — 09:06 재시작이면 내일까지 기다려 그날
    확보가 통째로 사라진다(KRX 시가는 종일 불변이라 늦은 시작은 즉시 실행이
    정답). 라운드 예외는 흡수하고 다음 라운드로 넘어간다; `CancelledError` 는
    re-raise(`stop()` 이 좀비 task 를 남기면 안 된다).
    """
    # cycle272 tester MEDIUM #1 — 준비 폴링 타임아웃은 **종결이 아니다**. 마커 1행을
    # 남긴 뒤 일정 루프로 낙하한다(07:59 재-prepare 가 `_targets` 를 채우면 R1 이 정상
    # 동작; 비어 있으면 라운드가 REST 콜 0 으로 자연 no-op). `_running` 이 False 면
    # 아래 첫 검사에서 즉시 종료한다.
    await _wait_for_ready_targets(sched)

    for round_no, total_rounds, kind, t in round_schedule():
        if not getattr(sched, "_running", False):
            return
        await sched._wait_until(t)
        if not getattr(sched, "_running", False):
            return
        try:
            await run_main_rest_basis_round(
                sched, round_no=round_no, total_rounds=total_rounds, kind=kind,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            _safe_trace("[main_rest_basis_round]", f"{round_no}/{total_rounds}")
