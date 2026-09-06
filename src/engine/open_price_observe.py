"""cycle264 (2026-09-06) — 시가(`[7] STCK_OPRC`) 스코프 shadow 관측 leaf. **행위 변경 0.**

`scheduler.py` 축의 관측 본체를 담는다(handler 축은 `src/realtime/handler.py` 의
`[open_scope_observe]`). 이 모듈은 **읽기만** 한다 — 전략 상태(`_targets` /
`_open_confirmed`)를 한 글자도 바꾸지 않고, 매수·매도·목표가·수량 산출에
어떤 입력도 제공하지 않는다.

## 왜 leaf 모듈인가 (C7 접촉 범위 확대 근거)

`scheduler.py` 는 **라인 상한 < 3,900L** 이다(cycle257 이 보드 전환 죽은 코드
−130L 을 삭제하며 3,864L 로 내리고 그 수치를 영구 가드로 박았다 —
`tests/unit/ast/test_cycle257_ast_dead_code_removed.py::TestA4SchedulerLineCount`).
09:05 대조 본체를 scheduler 안에 두면 3,979L 로 그 가드가 붉어진다(적대 검증
HIGH, 실측 `1 failed / 7,276 passed`). 주석 다이어트로는 80L 을 못 줄이므로
cycle233(`account_risk_watcher`) · cycle234 · cycle259(`log_metrics_collector`)
가 같은 이유로 쓴 **leaf 위임 패턴**을 답습한다. scheduler 에 남는 것은 상수
참조·task 생성·얇은 위임 메서드뿐이다.

## 무엇을 재는가

통합 채널 `H0UNCNT0` 의 일-스코프 필드는 09:00 에 리셋되지 않는다(cycle222-a2 가
`[8] STCK_HGPR` 에서 실측). 같은 성질이 `[7] STCK_OPRC` 에도 적용되면, MAIN 구간
틱이 실어 오는 "시가" 가 08:00~09:00 NXT 프리장 기준가일 수 있고 그 값이 VB/LTV
목표가의 기준가가 된다(포렌식 `_workspace/analysis/entry_price_0900_20260906/`).
09:05:30 에 같은 종목의 KRX REST 시가(`stck_oprc`, `J`=KRX)를 나란히 남겨 두면
익일 오프라인에서 `stock_master_daily` KRX 시가까지 합쳐 **3자 대조**가 된다.

## 이번 사이클이 고치지 않는 이유 (자문 §8.1)

1. 판별자 `[24] OPRC_HOUR` 를 **한 번도 찍어 본 적이 없다**(`grep fields[24]` 전
   소스 0건). "프리장 체결이 없던 종목에 이 필드가 무엇을 주는가" 는 추론이다.
2. 시정의 행위 영향이 크다 — 과거 VB 매수 116건 재계산상 진입의 27.6% 가 사라진다.
3. 같은 날 cycle262(진입 보류)·cycle263(일봉)이 배포됐고 월요일 09:00 이 그 둘의 첫
   실전 검증이다. 기준가 시정을 얹으면 진입 감소의 원인 분리가 불가능해진다.

⇒ 시정은 cycle265. 이 사이클은 하루치 코호트만 잰다.

## ⚠️ 월요일 판독 프로토콜 (적대 검증 LOW #12 / MEDIUM #5 반영)

- **오염 비율의 분모로 "구독 슬롯 ~287" 을 쓰지 마라.** 그것은 슬롯 **용량**이고
  실사용은 09-03/09-04 운영 `system_logs` 실측 `[tick_coverage] subscribed=`
  **107~148** 이다. 분모는 이 사이클이 만드는 `[open_scope_observe]` **발화 행
  총수**(= MAIN 창 틱을 1회 이상 받은 서로 다른 ticker 수)를 쓴다. 그 분모로
  다시 재면 `[day_high_scope_skip]` 93행(09-03)/71행(09-04)은 25~32% 가 아니라
  **53~63%** 다.
- **`in_main_window=false` 를 그대로 오염으로 세지 마라.** 그 라벨은 (i) `[24]` 가
  프리장 시각(진짜 오염) (ii) `000000`/빈 문자열(무체결·부재) (iii) 비숫자 파싱
  실패를 한 값으로 합친다. 원문 `oprc_hour` 가 정규화 없이 보존돼 있으므로
  판독 시 셋을 갈라야 한다.
- **`delta_bp≈0` 을 그대로 "오염 없음" 으로 세지 마라.** `used_src=rest` 행은
  09:00:05 폴백이 이미 REST 시가를 심은 종목이라 09:05 대조가 REST↔REST 이고
  `delta_bp=0.0` 이 **산술적으로 보장**된다. 오염 판정은 `used_src=ws` 행에서만
  성립한다(그래서 이 마커에 `used_src` 필드가 있다).
- `reason` 이 `ok` 가 아닌 행은 대조 자체가 성립하지 않은 행이다 —
  "REST 가 전부 일치했다" 와 "REST 가 N 종목에서 아무것도 못 줬다" 를 반드시
  구분해서 보고한다(그 구분이 cycle265 REST 폴백 배선의 성패다).

## 안전 계약

- **never-raise** — 09:05 백그라운드 task 가 죽어도 매매는 무관해야 한다. 본체와
  헬퍼 전부 예외를 흡수하고, 흡수기의 2차 예외까지 흡수한다(cycle258 카드 #5).
- **`logger` 만 쓴다** — `write_log`/DB 금지(20:10 리포트가 `system_logs` 를 파싱한다).
- **read-only** — `target_if_rest` 는 `rest_oprc + target_offset` **산술**이다.
  `on_open_price_confirmed(ticker, rest_oprc)` 로 계산하면 그 순간 보드 목표가가
  REST 시가로 갈아끼워진다 = 매매 행위 변경 = 이 사이클의 제1 계약 위반.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import time

from src.engine.daily_emit_cap import KstDailyEmitCap

logger = logging.getLogger(__name__)

# 09:05**:30**. KRX 시가는 프린트되면 하루 종일 불변이라 언제 읽어도 같다.
# - 09:00~09:01:30 은 cycle262 진입 보류 창 + 매수 주문 구간이라 전역 20건/초
#   한도를 매수와 다툰다.
# - 09:05:00 **정각**은 `_swing_buy_poll_loop` 의 `BUY_WINDOW_START` 와 겹친다
#   (donchian/kojiro 매수 평가 폴링이 정각에 깨어나 60초 주기로 돈다). 실피해는
#   작지만("전역 리미터는 하드 캡이라 거부가 아니라 지연" + `fetch_stock_detail`
#   5초 TTL single-flight) C2 계약 문언이 "스캔·폴 루프와 경합 금지" 이므로
#   30초 오프셋해 폴 정각을 피한다(적대 검증 LOW #7).
TIME_OPEN_SOURCE_COMPARE = time(9, 5, 30)

# REST 상한 (건/초) — 스캔·폴 루프와 경합 금지
_OPEN_SOURCE_COMPARE_MAX_PER_SEC = 5

# 준비 상태 대기 — task 는 `_boot()` 직후(시가 확정 **이전**)에 생성되고
# `_wait_until(..., advance_if_passed=False)` 는 09:05:30 이 지났으면 **즉시** 반환한다.
# 그래서 09:05:30 이후의 재시작(배포·크래시 복구)에서는 본체가 곧바로 도는데, 그
# 시점 `main` 보드 시가는 아직 0 이다(`scan_stocks()` 뒤 `_confirm_breakout_open_prices`
# 에서야 채워진다) ⇒ 전 종목 skip → **그날 0행**. `advance_if_passed=False` 로 막으려던
# 결과가 배치 때문에 그대로 발생한다(적대 검증 MEDIUM #6). 확정이 하나라도 생길
# 때까지 짧게 폴링하고, 타임아웃이면 **침묵하지 않고** 이유를 남긴다(cycle224 교훈).
_READY_POLL_INTERVAL_S = 2.0
_READY_POLL_MAX_S = 90.0

# 대조 대상 전략 (돌파 2종의 `main` 보드)
_COMPARE_STRATEGIES = ("volatility_breakout", "long_tail_volatility")

# 1회/(strategy_id, ticker)/일
_open_source_compare_cap: KstDailyEmitCap[tuple[str, str]] = KstDailyEmitCap()

# 09:00:05 시가 확정의 **출처** 라벨(WS 캐시 / REST 폴백). `KstDailyEmitCap` 을
# "KST 일자 자기 리셋 집합" 으로 쓴다 — `mark_emitted` 된 키가 곧 "REST 폴백으로
# 확정된 (전략, 종목, 보드)" 다. 별도 날짜 리셋 로직을 손으로 다시 쓰지 않는다.
_via_rest_marks: KstDailyEmitCap[tuple[str, str, str]] = KstDailyEmitCap()


def reset_open_source_compare_cap() -> None:
    """`[open_source_compare]` cap + 출처 라벨 강제 초기화 (테스트·운영 훅)."""
    global _open_source_compare_cap, _via_rest_marks
    _open_source_compare_cap = KstDailyEmitCap()
    _via_rest_marks = KstDailyEmitCap()


def mark_confirmed_via_rest(strategy_id: str, ticker: str, board: str) -> None:
    """그 종목의 시가가 **WS 캐시가 아니라 KIS REST 폴백**으로 확정됐음을 기록한다.

    `scheduler._confirm_breakout_open_prices` 의 2차 폴백 분기에서만 불린다.
    순수 기록이며 **never-raise** — 관측 라벨 하나가 시가 확정 루프를 죽이면 안 된다.
    """
    try:
        _via_rest_marks.mark_emitted((strategy_id, ticker, board))
    except Exception:  # pragma: no cover — 관측 라벨은 어떤 경우에도 조용히 통과
        pass


def was_confirmed_via_rest(strategy_id: str, ticker: str, board: str) -> bool:
    """`mark_confirmed_via_rest` 로 표시된 조합인가. 판정 실패는 False(= ws 가정)."""
    try:
        return not _via_rest_marks.should_emit((strategy_id, ticker, board))
    except Exception:  # pragma: no cover
        return False


def count_board_confirmed(strategy, board: str) -> tuple[int, int]:
    """`(truth_confirmed, truth_total)` — `_open_confirmed` 를 **board 스코프로 직접** 센다.

    cycle264 C3 의 본체다. `[breakout_open_confirm]` 이 쓰던
    `strategy.get_targets_status()` 는 `session_tracker.active ∩ tradable_boards` 로
    보드를 가리는데, 09:00:05~09:00:2x 에는 세션 트래커가 30초 주기 stale 캐시라
    `active={PRE_NXT}` 이고 VB 는 `tradable_boards=["main"]` 이라 교집합이 ∅ →
    전 종목이 `open_price: 0` 으로 덮인다. 그래서 같은 순간 비필터 로그가
    "VB 51/65종목" 인데 마커는 `confirmed=0 empty=65` 였고, 그 한 줄 위에 조사
    하나가 정반대 인과("REST 폴백 고장")를 세웠다(자문 §1.1/§1.3).

    분모는 **`_targets`** 다(`_open_confirmed` 가 아니다) — `_targets` 에는 있는데
    `_open_confirmed` 에 아직 항목이 없는 종목이 곧 "미확정" 이고, 그것이야말로
    이 수치가 세려는 대상이다.

    **never-raise** — `_targets` 가 property 로 승격돼 던지더라도 (0, 0) 으로
    떨어질 뿐 `_emit_breakout_open_confirm` 을 통과시킨다. 이 흡수기가 사라지면
    폭발 반경은 관측 실패가 아니라 **그날 매매 전체**다: 호출자
    `_confirm_breakout_open_prices` 는 이 emit 을 try 없이 부르고, 그 함수는
    `start()` 에서 09:00:05 에 await 되며, `start()` 의 except 가 KisApiError 가
    아닌 예외를 받으면 finally 로 떨어져 백그라운드 task 전부 cancel +
    `kis_ws.disconnect()` 를 하고 `run_daily` 가 같은 경로로 재진입한다(크래시 루프).
    """
    try:
        targets = getattr(strategy, "_targets", None) or {}
        confirmed_map = getattr(strategy, "_open_confirmed", None) or {}
        total = len(targets)
        confirmed = 0
        for ticker in targets:
            states = confirmed_map.get(ticker)
            ok = states.get(board, False) if isinstance(states, dict) else bool(states)
            if ok:
                confirmed += 1
        return confirmed, total
    except Exception:
        return 0, 0


def _has_confirmed_main_target(registry) -> bool:
    """VB/LTV 중 `main` 보드 시가가 하나라도 확정됐는가. 판정 실패는 False."""
    try:
        for sid in _COMPARE_STRATEGIES:
            strategy = registry.get(sid)
            if not strategy or not strategy.config.enabled:
                continue
            for info in (getattr(strategy, "_targets", None) or {}).values():
                if not isinstance(info, dict):
                    continue
                board_info = (info.get("boards") or {}).get("main")
                if isinstance(board_info, dict) and int(board_info.get("open_price") or 0) > 0:
                    return True
    except Exception:
        return False
    return False


def _collect_pending(registry) -> list[tuple[str, str, int, int]]:
    """대조 대상 `(strategy_id, ticker, used_open, target_offset)` 목록.

    `used_open` 정본은 `_targets`(그날 목표가를 만든 값)이지 `scanner.ticker_prices`
    (마지막 틱)가 아니다 — 후자를 쓰면 "목표가가 무엇을 썼나" 가 아니라 "지금
    캐시가 무엇인가" 를 잰다.

    cap 판정(`should_emit`, **비소모 peek**)과 `used_open <= 0`(미확정) skip 이
    REST **앞**이라 헛된 KIS 호출이 없다. 미확정 커버리지는
    `[breakout_open_confirm] truth_*` 가 센다.
    """
    pending: list[tuple[str, str, int, int]] = []
    for sid in _COMPARE_STRATEGIES:
        strategy = registry.get(sid)
        if not strategy or not strategy.config.enabled:
            continue
        for ticker, info in list((getattr(strategy, "_targets", None) or {}).items()):
            board_info = (info.get("boards") or {}).get("main") if isinstance(info, dict) else None
            if not isinstance(board_info, dict):
                continue
            used_open = int(board_info.get("open_price") or 0)
            if used_open <= 0 or not _open_source_compare_cap.should_emit((sid, ticker)):
                continue
            pending.append((sid, ticker, used_open, int(board_info.get("target_offset") or 0)))
    return pending


async def run_open_source_compare_once(sched) -> None:
    """VB/LTV `main` 확정 종목의 시가를 KRX REST 시가와 1행씩 대조한다 — **read-only**.

    형식::

        [open_source_compare] strategy=%s ticker=%s board=main used_open=%d
                              rest_oprc=%d delta_bp=%.1f target_used=%d
                              target_if_rest=%d used_src=%s reason=%s

    - `used_src` = `ws|rest` — 09:00:05 확정의 출처. `rest` 행은 대조가 REST↔REST 라
      `delta_bp=0.0` 이 산술적으로 보장된다(오염 없음의 증거가 **아니다**).
    - `reason` = `ok|rest_zero|rest_error` — 대조 성립 여부. **실패도 행을 남긴다**:
      `logger.debug` 단독은 `src/main.py::_DbLogHandler`(INFO 컷)를 못 넘어
      `system_logs` 에 도달하지 않고, 그러면 "REST 가 전부 일치했다" 와 "REST 가
      N 종목에서 아무것도 못 줬다" 가 구별되지 않는다(cycle237 C237-L2-1 동형).
      게다가 09:05 에 아직 체결이 없어 `stck_oprc="0"` 인 저유동 종목이야말로
      오염된 프리장 `[7]` 을 쓰고 있을 확률이 가장 높은 코호트다 — 결측이
      무작위가 아니므로 침묵하면 판독이 편향된다.
      실패 행의 `rest_oprc`/`delta_bp`/`target_if_rest` 는 0 이다(`reason` 이
      그 0 을 "값" 이 아니라 "미측정" 으로 읽게 하는 태그다).

    **never-raise.**
    """
    try:
        registry = sched.registry
        for sid, ticker, used_open, offset in _collect_pending(registry):
            if not getattr(sched, "_running", True):
                # 정지 요청이 들어오면 남은 REST 버스트(최대 ~28초)를 즉시 끊는다.
                return
            reason = "ok"
            rest = 0
            try:
                detail = await _fetch_stock_detail(ticker)
                rest = int((detail or {}).get("stck_oprc") or 0)
                if rest <= 0:
                    reason = "rest_zero"
            except Exception:
                reason, rest = "rest_error", 0
                logger.debug("[open_source_compare] %s %s 조회 실패 graceful", sid, ticker)
            ok = reason == "ok"
            _open_source_compare_cap.emit_once(
                (sid, ticker), logger.info,
                "[open_source_compare] strategy=%s ticker=%s board=main used_open=%d "
                "rest_oprc=%d delta_bp=%.1f target_used=%d target_if_rest=%d "
                "used_src=%s reason=%s",
                sid, ticker, used_open, rest,
                ((rest - used_open) / used_open * 10000) if ok else 0.0,
                used_open + offset, (rest + offset) if ok else 0,
                "rest" if was_confirmed_via_rest(sid, ticker, "main") else "ws", reason,
            )
            await asyncio.sleep(1.0 / _OPEN_SOURCE_COMPARE_MAX_PER_SEC)
    except Exception:
        _trace_failure()


async def open_source_compare_task_loop(sched) -> None:
    """09:05:30 대기 → 준비 상태 확인 → 본체 1회. 행위 변경 0.

    ⚠️ `advance_if_passed=True` 금지 — 09:06 재시작이면 내일까지 기다려 그날 관측이
    통째로 사라진다(KRX 시가는 종일 불변이라 늦은 시작은 즉시 실행이 정답).
    메인 루프는 09:00:05 확정 직후 09:30 까지 `_wait_until` 로 블록되므로 인라인
    호출로는 09:05:30 에 발화할 수 없다 ⇒ 백그라운드 task 여야 한다.

    본체는 `sched._run_open_source_compare_once()`(scheduler 의 얇은 위임)를 거친다 —
    그 메서드가 테스트·운영의 단일 seam 이다.
    """
    try:
        await sched._wait_until(TIME_OPEN_SOURCE_COMPARE)
        waited = 0.0
        while getattr(sched, "_running", False):
            if _has_confirmed_main_target(sched.registry):
                await sched._run_open_source_compare_once()
                return
            if waited >= _READY_POLL_MAX_S:
                logger.info(
                    "[open_source_compare] skipped reason=no_confirmed_target waited_s=%.0f "
                    "— 09:05:30 이후 재시작 등으로 `main` 보드 시가가 아직 확정되지 "
                    "않았다(그날 대조 0행). 침묵하지 않는 것이 계약이다",
                    waited,
                )
                return
            await asyncio.sleep(_READY_POLL_INTERVAL_S)
            waited += _READY_POLL_INTERVAL_S
    except asyncio.CancelledError:
        raise
    except Exception:
        _trace_failure()


async def _fetch_stock_detail(ticker: str):
    """KIS 개별시세 지연 import (`_confirm_breakout_open_prices` 선례 답습)."""
    from src.api.condition import fetch_stock_detail

    return await fetch_stock_detail(ticker)


def _trace_failure() -> None:
    """관측기 자기 실패 흔적 — 무흔적 `pass` 금지(cycle258 카드 #5 규약). never-raise."""
    try:
        from src.engine.observer_trace import trace_observer_failure

        trace_observer_failure(
            "[open_source_compare]", "-", _open_source_compare_cap, dest_logger=logger,
        )
    except Exception:  # pragma: no cover — 2차 예외도 흡수
        pass
