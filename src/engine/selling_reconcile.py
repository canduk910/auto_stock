"""cycle273b F-7 (2026-09-10) — stale `_selling` 유지 사유 가시화 leaf. **행위 변경 0.**

명세 = `_workspace/red/cycle273b_philoptics_no_behavior_3_spec.md` §3 ·
정본 = `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` §7

`scheduler.py:3572-3601`(cycle273b 이전)의 stale `_selling` 재대조 블록을
**판정 byte 동일**하게 옮긴다 — 3 유지 사유(`held_zero`/`open_order`/`too_young`)의
`continue` 순서·조건·해제 분기의 `discard`·`write_log` 문자열 전부 그대로다.
달라지는 것은 유지 3분기 각각에 `[selling_hold]` WARNING 1행을 더하는 것뿐이다.

## 왜 이 관측이 필요한가

해제할 때만 WARNING 을 냈고 유지 3분기는 전부 무음이었다 — 필옵틱스 사례의
6h45m 유지가 로그에 한 행도 남지 않았다. `_selling` 이 stale 로 오래 남으면
`risk.on_tick` 의 손절/트레일링 평가가 그 종목에서 종일 억제된다(Defect 2).

## 왜 leaf 모듈인가 (scheduler 라인 상한)

`scheduler.py` 는 영구 상한 **<3,900L**(cycle257 가드 + cycle264 자매) 인데
cycle273b 착수 시점 3,898L — 유지 3분기 안에 로그 한 줄도 인라인으로 넣을 여유가
없다. cycle233 `account_risk_watcher` · cycle259 `log_metrics_collector` ·
cycle264 `open_price_observe` 가 같은 이유로 쓴 **블록 통째 leaf 위임** 패턴을
답습한다. `SELLING_RECONCILE_MIN_AGE_S` 상수는 이 leaf 가 정본이고 scheduler 가
호출 자리에서 import 해 인자로 전달한다.

## 안전 계약

- **판정 byte 동일 이동** — `continue` 3개의 조건·순서, `discard`/`pop` 순서,
  해제 WARNING 문구, `write_log("WARNING", ...)` 문구 전부 불변.
- 관측 호출은 각 `continue` **직전**(판정 뒤·행동 앞)에 둔다.
- 관측은 `logger.warning` — `src/main.py::_DbLogHandler` 가 INFO 컷이라
  WARNING 미만은 `system_logs` 에 도달하지 않는다(cycle237 C237-L2-1 계열).
- cap = `KstDailyEmitCap` **1회/(ticker, reason)/일** — reason 을 키에서 빼면
  사유 전이(`too_young` → `held_zero`)가 첫 사유에 먹힌다(cycle258 카드 #4).
- 실패는 `observer_trace.trace_observer_failure`(무흔적 `pass` 금지, 카드 #5).
- **never-raise** — 관측(호출부 폭발 포함) 이 유지/해제 판정을 바꾸면 안 된다.
  본체 전체(재대조 로직)도 기존과 동일하게 `try/except Exception` 하나로 감싼다
  (`logger.exception` graceful — 다음 주기 재시도).

## 테스트 patch seam

`write_log` 는 (구 scheduler 관례를 그대로 이어) **모듈 최상단**에서 import 한다
— `tests/integration/conftest.py::scheduler_env` 가 `src.engine.scheduler.write_log`
와 나란히 `src.engine.selling_reconcile.write_log` 도 패치한다(cycle51 이
`boot_manager.write_log` 를 별도로 패치한 선례와 동형 — `write_log` 를 최상단
import 하는 모듈마다 자기 이름공간의 바인딩을 각자 패치해야 한다).
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.db.system_logs import write_log
from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환) —
# 이 leaf 로 옮겨진 해제 WARNING("stale 매도중 상태 해제 …")의 `system_logs` 접두를
# `[src.engine.scheduler]` 로 byte 보존한다(운영 로그 판독 문서가 이 접두를 인용,
# `_workspace/analysis/2026-09-10_161580_root_cause.md:137`). `__name__` 이었다면
# 배포 전후로 `[src.engine.selling_reconcile]` 로 갈라져 grep 합산이 깨졌을 것이다.

SELLING_HOLD_MARKER = "[selling_hold]"

# 정본 상수 — 갓 접수된 매도로 볼 최소 경과 초. `scheduler.py` 는 15분 전체 재대조
# 호출 자리에서 이 상수를 지연 import 해 `min_age_s` 로 넘긴다(자기 사본 없음 —
# `test_cycle432_followup.py::test_scheduler_has_no_own_selling_reconcile_min_age_constant`).
# `order_engine.SELL_UNKNOWN_RECONCILE_DELAY_S`(180초 단일 종목 확인 지연)는 같은
# 값의 별도 리터럴이다 — order_engine.py 의 모듈 최상단 `src.*` import 증가분을
# `src.engine.llm_buy_gate` 1건으로 고정한 구조 가드(`test_cycle276_ast_order_hook.py::
# test_c4_2_...` 외 cycle286·287·291 사본) 때문이고, 두 값의 일치는
# `test_order_engine_delay_equals_selling_reconcile_min_age_by_value` 가 지킨다.
SELLING_RECONCILE_MIN_AGE_S: float = 180.0

# 1회/(ticker, reason)/일 — cycle258 카드 #4 (reason 을 키에서 빼면 사유 전이가
# 첫 사유에 먹힌다).
_hold_cap: "KstDailyEmitCap[tuple[str, str]]" = KstDailyEmitCap()


def reset_selling_hold_cap() -> None:
    """`[selling_hold]` cap 강제 초기화 (테스트·운영 훅 — cycle264 선례 답습)."""
    global _hold_cap
    _hold_cap = KstDailyEmitCap()


# ---------------------------------------------------------------------------
# cycle428(F-422-1) — 15분 재대조와 180초 단일 종목 확인이 공유하는 판정 규칙.
# ---------------------------------------------------------------------------
def _stale_selling_verdict(
    *, held_qty: int, has_open_sell_order: bool, since, now_kst, min_age_s: float,
) -> "str | None":
    """stale `_selling` 유지 사유 — 「같은 3사유 판정」의 유일한 정본.

    반환 = 유지 사유(``held_zero``/``open_order``/``too_young``) 또는 ``None``
    (해제 — 보유 잔존 ∧ 열린 매도주문 없음 ∧ aged). 15분 전체 재대조
    (`reconcile_stale_selling`)와 180초 단일 종목 확인
    (`reconcile_selling_unknown_one`)이 이 함수 하나를 공유한다 — 규칙이
    둘이 되면 안 된다(F-422-1 자문 지시).
    """
    if held_qty <= 0:
        return "held_zero"
    if has_open_sell_order:
        return "open_order"
    if since is not None:
        try:
            elapsed_s = (now_kst - since).total_seconds()
        except Exception:
            elapsed_s = 0.0
        if elapsed_s < min_age_s:
            return "too_young"
    return None


def _emit_hold(ticker: str, reason: str, elapsed_s: float, *, now: "datetime | None" = None) -> None:
    """유지 판정 관측 1행. **never-raise** — 호출부 자체 폭발(모의 포함)도 흡수한다."""
    try:
        _hold_cap.emit_once(
            (ticker, reason), logger.warning,
            "[selling_hold] ticker=%s reason=%s elapsed_s=%.1f",
            ticker, reason, elapsed_s,
            now=now,
        )
    except Exception:
        try:
            trace_observer_failure(SELLING_HOLD_MARKER, f"{ticker}|{reason}", _hold_cap, now=now)
        except Exception:  # pragma: no cover — 2차 예외도 흡수(cycle258 J-3 계약)
            pass


async def reconcile_stale_selling(order_engine, holdings, *, min_age_s: float, now: "datetime | None" = None) -> None:
    """stale `_selling` 재대조 — `scheduler.py` 구 인라인 블록의 판정 byte 동일 이동.

    (보유 잔존 AND 열린 매도주문 없음 AND aged) 이면 stale → discard →
    `risk.on_tick` 손절 재평가 재개. 그 외 3사유(``held_zero``/``open_order``/
    ``too_young``)는 유지하며 `[selling_hold]` 로 1행씩 가시화한다.

    Args:
        order_engine: `_selling`(set[str])·`_selling_since`(dict[str, datetime])
            를 가진 `OrderEngine` 인스턴스.
        holdings: `get_balance()` 의 보유 목록(`.ticker`/`.quantity`).
        min_age_s: 갓 접수된 매도로 볼 최소 경과 초(구 `SELLING_RECONCILE_MIN_AGE_S`,
            소유권은 scheduler 에 남는다).
        now: 판정 기준 시각(KST, tz-aware). 생략 시 `datetime.now(KST_TZ)`.
    """
    try:
        from src.api.balance import get_daily_orders
        from src.engine.scanner import KST_TZ as _KST

        held_qty = {h.ticker: h.quantity for h in holdings if h.quantity > 0}
        daily_orders = await get_daily_orders()
        # KIS sll_buy_dvsn_cd: 01=매도, 02=매수. rmn_qty>0 = 미체결(열린) 주문.
        open_sell_tickers = {
            o.get("pdno", "")
            for o in daily_orders
            if o.get("sll_buy_dvsn_cd") == "01" and int(o.get("rmn_qty", "0") or 0) > 0
        }
        now_kst = now if now is not None else datetime.now(_KST)
        for tk in list(order_engine._selling):
            since = order_engine._selling_since.get(tk)
            try:
                elapsed_s = (now_kst - since).total_seconds() if since is not None else 0.0
            except Exception:
                # LOW 방어(cycle273b 검증 지적 #4) — 관측 요구로 뺄셈이 3분기 앞으로
                # 호이스팅되며 노출면이 `_selling` 전 종목으로 넓어졌다. 실 프로덕션
                # 기록점(order_engine.py:554)은 항상 tz-aware 라 정상 입력에서는
                # 도달하지 않지만, 도달해도 관측용 값 하나만 0.0 으로 낙하시키고
                # 판정(held/open_order/too_young/해제)은 그대로 진행한다.
                elapsed_s = 0.0
            verdict = _stale_selling_verdict(
                held_qty=held_qty.get(tk, 0),
                has_open_sell_order=tk in open_sell_tickers,
                since=since, now_kst=now_kst, min_age_s=min_age_s,
            )
            if verdict is not None:
                _emit_hold(tk, verdict, elapsed_s, now=now_kst)
                continue  # 유지 — held_zero(보유 없음)/open_order(double-sell 방지)/
                # too_young(KIS 전파 지연 레이스 방지), 건드리지 않음
            order_engine._selling.discard(tk)
            order_engine._selling_since.pop(tk, None)
            logger.warning(
                "stale 매도중 상태 해제 (보유 잔존·열린 매도주문 없음) "
                "→ on_tick 손절 재평가 재개: %s", tk,
            )
            await write_log("WARNING", f"[selling_reconcile] stale _selling 해제: {tk}")
    except Exception:
        logger.exception("stale _selling 재대조 실패 — graceful (다음 주기 재시도)")


# ---------------------------------------------------------------------------
# cycle428(F-422-1) — 매도 결과 모름(UNKNOWN) 단일 종목 확인 조회.
# ---------------------------------------------------------------------------
SELL_SEND_UNKNOWN_RESOLVED_MARKER = "[sell_send_unknown_resolved]"

# 15분 재대조의 held_zero/open_order/too_young → 단일 종목 확인의 어휘(사용자안
# 2 가 지정한 4값). 해제(verdict=None)는 `not_accepted`(주문이 접수되지 않았다
# — 다음 틱 손절이 새 발사 1회로 재평가한다).
_UNKNOWN_RESOLVE_RESULT_BY_VERDICT = {
    None: "not_accepted",
    "held_zero": "closed",
    "open_order": "open_order",
    "too_young": "too_young",
}


async def reconcile_selling_unknown_one(
    order_engine, ticker: str, strategy_id: str, *,
    min_age_s: float, now: "datetime | None" = None,
) -> str:
    """F-422-1 — 매도 결과 모름(UNKNOWN) 뒤 그 종목만 확인 조회한다.

    `reconcile_stale_selling`(15분 전체 재대조)과 **같은 판정 규칙**
    (`_stale_selling_verdict`)을 그 종목 하나에만 쓴다 — 조회는
    `get_balance()`(그 종목 보유) + `get_daily_orders(pdno=ticker)`(그 종목
    열린 매도주문)로 좁힌다.

    반환 = ``already_released``(cycle432 — 180초 전에 체결통보가 먼저 `_selling`
    을 풀었다. 그 사이 다른 체결(완결 또는 부분)로 주문이 끝났다는 뜻이라 이
    종목을 다시 판정하지 않는다. **KIS 조회 0회**) / ``not_accepted``(해제 —
    주문이 접수되지 않은 것으로 판정, 다음 틱 손절이 새로 발사한다) /
    ``closed``(보유 0 — 유지, 15분 sync 가 정리) / ``open_order``(열린
    매도주문 있음 — 유지) / ``too_young``(아직 이르다 — 유지, 보통 180초 뒤
    호출이라 드물다) / ``lookup_failed``(조회 실패 — **기본값 = 유지**, 15분
    `reconcile_stale_selling` 로 넘긴다).

    never-raise — 조회·판정 중 예외는 `lookup_failed` 로 흡수한다(재발사보다
    지연이 낫다, 자문 2026-10-10 「조회 실패의 기본값 = 유지」).
    """
    if ticker not in order_engine._selling:
        # cycle432(F-422-1 후속 LOW #1) — 체결통보가 먼저 풀었다. 판정할
        # `_selling` 표식이 이미 없으니 KIS 를 묻지 않는다(지금까지는 조회
        # 뒤 `not_accepted` 로 잘못 기록됐다).
        result = "already_released"
        logger.warning(
            "%s ticker=%s strategy=%s result=%s",
            SELL_SEND_UNKNOWN_RESOLVED_MARKER, ticker, strategy_id, result,
        )
        return result

    from src.api.balance import get_balance, get_daily_orders
    from src.engine.scanner import KST_TZ as _KST

    now_kst = now if now is not None else datetime.now(_KST)
    try:
        holdings, _summary = await get_balance()
        held_qty = next((h.quantity for h in holdings if h.ticker == ticker), 0)
        daily_orders = await get_daily_orders(pdno=ticker)
        has_open_sell_order = any(
            o.get("sll_buy_dvsn_cd") == "01" and int(o.get("rmn_qty", "0") or 0) > 0
            for o in daily_orders
        )
    except Exception:
        logger.debug(
            "[sell_send_unknown_resolve] 확인 조회 실패 — 유지: %s", ticker, exc_info=True,
        )
        result = "lookup_failed"
        logger.warning(
            "%s ticker=%s strategy=%s result=%s",
            SELL_SEND_UNKNOWN_RESOLVED_MARKER, ticker, strategy_id, result,
        )
        return result

    since = order_engine._selling_since.get(ticker)
    verdict = _stale_selling_verdict(
        held_qty=held_qty, has_open_sell_order=has_open_sell_order,
        since=since, now_kst=now_kst, min_age_s=min_age_s,
    )
    result = _UNKNOWN_RESOLVE_RESULT_BY_VERDICT[verdict]
    if verdict is None:
        # not_accepted — 180초가 지났는데도 보유>0 · 열린 주문 없음 =
        # 폴백/1차 주문이 접수되지 않았다고 본다. 해제해 다음 틱 손절이
        # 새로 발사(= 재발사가 아니라 새 발사)할 수 있게 한다.
        order_engine._selling.discard(ticker)
        order_engine._selling_since.pop(ticker, None)
        logger.warning(
            "매도 결과 모름 확인 — 접수 안 됨으로 판정, 해제 → on_tick 손절 재평가 "
            "재개: %s", ticker,
        )
    logger.warning(
        "%s ticker=%s strategy=%s result=%s",
        SELL_SEND_UNKNOWN_RESOLVED_MARKER, ticker, strategy_id, result,
    )
    return result
