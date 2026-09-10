# DEST: tests/unit/engine/test_cycle273b_selling_hold_observe.py
"""cycle273b Red — F-7: `_selling` **장기 유지**의 가시화 (판정 불변).

명세 = `_workspace/red/cycle273b_philoptics_no_behavior_3_spec.md` §F-7
정본 = `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` §7
현행 = `src/engine/scheduler.py:3572-3601`

## 무엇이 안 보이는가

stale `_selling` 재대조는 **해제할 때만** WARNING 을 낸다(`:3593-3599`). 유지 3분기
(`held=0` `:3586` · `open_order` `:3588` · `too_young` `:3590`)는 전부 `continue` 뿐이라
**통째로 무음**이다. 필옵틱스 사례의 6h45m 유지가 로그에 한 행도 남지 않았다.

## 🔴 라인 예산 — 인라인 추가 불가

`scheduler.py` = **3,898L** / 영구 상한 **<3,900L**
(`tests/unit/ast/test_cycle257_ast_dead_code_removed.py` + cycle264 자매 가드).
여유 **1행**이라 3분기 안에 로그를 넣을 수 없다. ⇒ **블록 통째 leaf 위임**
(cycle233 `account_risk_watcher` · cycle259 `log_metrics_collector` ·
cycle264 `open_price_observe` 의 확립된 패턴, 약 −27행).

## ⚠️ 이 파일이 고정하는 leaf 인터페이스는 **제안**이다 (명세 open question O-B3)

```python
# src/engine/selling_reconcile.py
SELLING_HOLD_MARKER = "[selling_hold]"
async def reconcile_stale_selling(order_engine, holdings, *, min_age_s, now=None) -> None
```
채택이 갈리면 이 파일 상단 상수 2개만 고치면 된다. 판정(`continue` 3개 · `discard`
순서 · `write_log` 문자열)은 **byte 동일 이동**이 계약이다.

## HEAD 기준

전부 **RED** — `src/engine/selling_reconcile.py` 가 존재하지 않는다.
(모듈 부재는 수집 오류가 아니라 테스트 내부 `pytest.fail` 로 드러낸다.)
"""

from __future__ import annotations

import importlib
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

pytestmark = pytest.mark.unit

_LEAF_MODULE = "src.engine.selling_reconcile"
_ENTRY = "reconcile_stale_selling"
_MARKER = "[selling_hold]"

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 10, 14, 0, 0, tzinfo=KST)
TICKER = "161580"
MIN_AGE_S = 180.0


def _leaf():
    """leaf 를 지연 import — 부재는 수집 오류가 아니라 명시 RED 로 만든다."""
    try:
        return importlib.import_module(_LEAF_MODULE)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"RED — leaf `{_LEAF_MODULE}` 미구현 ({exc}). "
            f"scheduler.py 3,898L/상한 3,900L 이라 인라인 관측은 불가하다(UA §7)."
        )


def _entry():
    mod = _leaf()
    fn = getattr(mod, _ENTRY, None)
    if fn is None:
        pytest.fail(f"RED — `{_LEAF_MODULE}.{_ENTRY}` 미구현")
    return mod, fn


class _OrderedTickerSet:
    """결정론적 반복 순서를 보장하는 `set[str]` 대체.

    프로덕션 leaf 는 `_selling` 에 `discard`/`__contains__`/`for tk in list(...)` 만
    요구한다. 실 `set` 의 반복 순서는 해시 시드에 좌우돼 재현 불가능한데,
    observer-failure BLOCKER 회귀(2-ticker, "A 가 먼저 처리된다")는 순서 보장이
    반드시 필요하다 — `dict.fromkeys` 로 삽입 순서를 보존한다.
    """

    def __init__(self, items) -> None:
        self._items: list[str] = list(dict.fromkeys(items))

    def add(self, item: str) -> None:
        if item not in self._items:
            self._items.append(item)

    def discard(self, item: str) -> None:
        try:
            self._items.remove(item)
        except ValueError:
            pass

    def __contains__(self, item: object) -> bool:
        return item in self._items

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:  # pragma: no cover — 진단 편의
        return f"_OrderedTickerSet({self._items!r})"


class _FakeOrderEngine:
    def __init__(self, selling, since: dict[str, datetime]):
        self._selling = _OrderedTickerSet(selling)
        self._selling_since = dict(since)


def _holdings(**qty: int):
    return [SimpleNamespace(ticker=tk, quantity=q) for tk, q in qty.items()]


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):
    """KIS·DB 격리. 반환 dict 로 각 테스트가 일별 주문 목록을 갈아끼운다."""
    import src.api.balance as _balance
    import src.db.system_logs as _sys_logs

    state = {"daily_orders": [], "write_log": AsyncMock(return_value=None)}

    async def _get_daily_orders():
        return state["daily_orders"]

    monkeypatch.setattr(_balance, "get_daily_orders", _get_daily_orders)
    monkeypatch.setattr(_sys_logs, "write_log", state["write_log"])
    try:
        mod = importlib.import_module(_LEAF_MODULE)
    except ModuleNotFoundError:
        return state
    monkeypatch.setattr(mod, "write_log", state["write_log"], raising=False)
    monkeypatch.setattr(mod, "get_daily_orders", _get_daily_orders, raising=False)
    if hasattr(mod, "_hold_cap"):
        mod._hold_cap.reset_daily()
    return state


def _warns(caplog, prefix: str) -> list[str]:
    """WARNING 이상 + prefix 한정(CI 루트 로거는 DEBUG)."""
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


def _open_sell(ticker: str, rmn: int = 3) -> dict:
    return {"pdno": ticker, "sll_buy_dvsn_cd": "01", "rmn_qty": str(rmn)}


# ---------------------------------------------------------------------------
# 유지 3분기 — 각각 1행씩 남는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f7_hold_reason_held_zero_emits_warning(patched, caplog):
    """RED — 보유 잔량 0 이라 유지되는 경우(`scheduler.py:3586-3587`)."""
    _mod, fn = _entry()
    engine = _FakeOrderEngine({TICKER}, {TICKER: NOW - timedelta(hours=6)})

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(), min_age_s=MIN_AGE_S, now=NOW)

    assert TICKER in engine._selling, "판정 변경 — held=0 은 유지가 계약이다"
    rows = _warns(caplog, _MARKER)
    assert rows, f"{_MARKER} 미발화 — 유지 사유가 무음으로 남는다"
    assert f"ticker={TICKER}" in rows[0]
    assert "reason=held_zero" in rows[0]
    assert "elapsed_s=" in rows[0]


@pytest.mark.asyncio
async def test_f7_hold_reason_open_order_emits_warning(patched, caplog):
    """RED — 열린 매도주문이 있어 유지되는 경우(`:3588-3589`, double-sell 방지)."""
    _mod, fn = _entry()
    patched["daily_orders"] = [_open_sell(TICKER)]
    engine = _FakeOrderEngine({TICKER}, {TICKER: NOW - timedelta(hours=6)})

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)

    assert TICKER in engine._selling
    rows = _warns(caplog, _MARKER)
    assert rows and "reason=open_order" in rows[0], f"rows={rows}"


@pytest.mark.asyncio
async def test_f7_hold_reason_too_young_emits_warning(patched, caplog):
    """RED — 갓 접수된 매도(`:3590-3592`, KIS 전파 지연 레이스 방지)."""
    _mod, fn = _entry()
    engine = _FakeOrderEngine({TICKER}, {TICKER: NOW - timedelta(seconds=10)})

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)

    assert TICKER in engine._selling
    rows = _warns(caplog, _MARKER)
    assert rows and "reason=too_young" in rows[0], f"rows={rows}"


# ---------------------------------------------------------------------------
# 해제 경로 — byte 동일 이동
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f7_release_path_unchanged(patched, caplog):
    """RED — 해제 판정·로그 문자열·`write_log` 가 그대로여야 한다(무행위 증명의 본체)."""
    _mod, fn = _entry()
    engine = _FakeOrderEngine({TICKER}, {TICKER: NOW - timedelta(hours=6)})

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)

    assert TICKER not in engine._selling, "stale 해제가 사라졌다 — on_tick 손절이 종일 억제된다"
    assert TICKER not in engine._selling_since
    assert _warns(caplog, "stale 매도중 상태 해제"), "기존 해제 WARNING 문구가 바뀌었다"
    assert patched["write_log"].await_count == 1
    body = patched["write_log"].await_args.args
    assert body[0] == "WARNING"
    assert body[1] == f"[selling_reconcile] stale _selling 해제: {TICKER}"
    assert _warns(caplog, _MARKER) == [], "해제된 종목에 유지 관측이 함께 발화했다"


# ---------------------------------------------------------------------------
# cap · 자기실패 격리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f7_cap_is_per_ticker_and_reason(patched, caplog):
    """RED — cap 은 `KstDailyEmitCap` 1회/(ticker, reason)/일.

    reason 을 키에 넣지 않으면 사유 전이(too_young → held_zero)가 첫 사유에 먹힌다
    (cycle258 카드 #4 규약).
    """
    _mod, fn = _entry()
    engine = _FakeOrderEngine({TICKER}, {TICKER: NOW - timedelta(seconds=10)})

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)
    assert len(_warns(caplog, _MARKER)) == 1, "같은 (ticker, reason) 이 두 번 발화했다"

    caplog.clear()
    # 사유 전이 — 같은 ticker, 다른 reason 은 별도 1행
    engine2 = _FakeOrderEngine({TICKER}, {TICKER: NOW - timedelta(hours=6)})
    await fn(engine2, _holdings(), min_age_s=MIN_AGE_S, now=NOW)
    rows = _warns(caplog, _MARKER)
    assert rows and "reason=held_zero" in rows[0], (
        "사유가 바뀌었는데 cap 이 먹었다 — cap 키에 reason 이 빠졌다"
    )


@pytest.mark.asyncio
async def test_f7_observer_failure_does_not_change_decision(patched, caplog, monkeypatch):
    """관측기 자기 실패가 판정을 바꾸지 않는다(never-raise, cycle258 카드 #5).

    검증 라운드 1 BLOCKER 지적 — 1-ticker 단일 유지 분기만으로는 공허했다
    (그 ticker 는 예외가 나든 안 나든 어차피 유지되므로 `_emit_hold` 의
    `except Exception:` 을 `except ZeroDivisionError:` 로 좁혀도(M4b) 초록이었다).
    2-ticker 결정론적 순서(A=관측 발화·폭발 유발 → B=정상 해제 대상)로 강화한다 —
    M4b 가 걸리면 A 의 예외가 `_emit_hold` 내부에서 흡수되지 못하고 outer
    `except Exception:`(본체 전체 감싸기)까지 전파돼 **루프가 A 에서 멈추고 B 가
    평가되지 않는다**. 이 메커니즘이 그대로 Defect 2(risk.on_tick 손절 종일 억제)를
    재현한다 — 관측 안전망 자체의 결함이 실매매 안전 계약을 깨는 것이므로 이
    시나리오를 못 잡으면 안전 계약이 공허해진다.
    """
    mod, fn = _entry()
    if not hasattr(mod, "_hold_cap"):
        pytest.fail("RED — 모듈 레벨 `_hold_cap`(KstDailyEmitCap) 미구현")

    def _boom(*_a, **_kw):
        raise RuntimeError("관측기 폭발")

    monkeypatch.setattr(mod._hold_cap, "emit_once", _boom, raising=False)

    TICKER_A = "AAAAAA"  # too_young — 유지 분기 → `_emit_hold` 호출 → 폭발
    TICKER_B = "BBBBBB"  # aged·보유·열린주문 없음 — 정상 해제 대상, `_emit_hold` 미호출
    engine = _FakeOrderEngine(
        [TICKER_A, TICKER_B],  # 결정론적 순서 — A 가 먼저 처리된다
        {
            TICKER_A: NOW - timedelta(seconds=10),
            TICKER_B: NOW - timedelta(hours=6),
        },
    )

    caplog.set_level(logging.DEBUG)
    await fn(
        engine,
        _holdings(**{TICKER_A: 3, TICKER_B: 3}),
        min_age_s=MIN_AGE_S,
        now=NOW,
    )

    assert TICKER_A in engine._selling, "관측 실패가 A(유지 대상)의 판정을 바꿨다"
    assert TICKER_B not in engine._selling, (
        "B 가 해제되지 않았다 — A 의 관측 실패(`_emit_hold` 내부 흡수 실패)가 루프 "
        "전체를 outer except 로 조기 종료시켜 뒤 ticker 평가를 막았다 "
        "(M4b: `_emit_hold` 의 except 를 좁히면 재현된다 = Defect 2 재발 경로)"
    )


@pytest.mark.asyncio
async def test_f7_get_daily_orders_failure_is_graceful(patched, caplog, monkeypatch):
    """LOW 보강 — `get_daily_orders` 폭발은 outer graceful except 가 흡수한다.

    HEAD 인라인 코드와 byte 동일한 선재 gap(검증 라운드 1 지적 #5, 뮤테이션 M10
    ESCAPED) — 이 경로를 재현하는 테스트가 스위트 전체에 없었다. `_selling` 판정은
    바뀌지 않고(그 사이클은 통째로 재시도로 미뤄진다) `logger.exception` 이
    흔적을 남기는지로 고정한다.
    """
    import src.api.balance as _balance

    async def _boom_daily_orders():
        raise RuntimeError("KIS 일별주문 조회 실패")

    monkeypatch.setattr(_balance, "get_daily_orders", _boom_daily_orders)

    _mod, fn = _entry()
    engine = _FakeOrderEngine([TICKER], {TICKER: NOW - timedelta(hours=6)})

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)

    assert TICKER in engine._selling, "재대조 자체가 실패했는데 판정이 바뀌었다(해제됨)"
    assert any(
        r.levelno >= logging.ERROR and "재대조 실패" in r.getMessage()
        for r in caplog.records
    ), "graceful 흡수 로그(logger.exception '…재대조 실패…')가 보이지 않는다"


@pytest.mark.asyncio
async def test_f7_boundary_min_age_exact_seconds_releases(patched, caplog):
    """LOW 보강 — `elapsed_s == min_age_s` 정각 경계에서는 해제된다(뮤테이션 M7 방어).

    기존 `test_T3d`(179s)만으로는 `<` ↔ `<=` 를 구별하지 못한다(179s 는 두 연산자
    모두 True 라 유지로 판정되어 동일하게 통과한다). 정확히 180.0s 에서만 갈린다
    — `<` 는 해제, `<=` 는 유지. HEAD 코드와 byte 동일한 선재 gap(검증 라운드 1
    지적 #6, 뮤테이션 M7 ESCAPED)을 닫는 회귀 가드.
    """
    _mod, fn = _entry()
    engine = _FakeOrderEngine([TICKER], {TICKER: NOW - timedelta(seconds=MIN_AGE_S)})

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)

    assert TICKER not in engine._selling, (
        "elapsed_s == min_age_s 정각에서 유지됐다 — `<` 가 `<=` 로 뒤집혔다(M7)"
    )


# ---------------------------------------------------------------------------
# 검증 r2 후속 — logger 정체성(M12) · rmn_qty=0 은 열린 주문이 아니다(M13)
# ---------------------------------------------------------------------------
def test_f7_logger_identity_is_scheduler():
    """검증 r2 MEDIUM(뮤테이션 M12 ESCAPED) — leaf 의 logger 이름은 `src.engine.scheduler` 다.

    `src/main.py::_DbLogHandler.emit` 이 `f"[{record.name}] {msg}"` 로 `system_logs` 에
    적재하므로, `__name__` 으로 바뀌면 해제 WARNING 의 접두가 `[src.engine.scheduler]` →
    `[src.engine.selling_reconcile]` 로 조용히 갈라져 배포 전후 grep 합산이 무증상으로
    깨진다(사이클 60 I1 영속 관례 — scheduler 에서 갈라진 leaf 는 logger 이름을 물려받는다).
    """
    mod, _ = _entry()
    assert mod.logger.name == "src.engine.scheduler", (
        "leaf logger 정체성이 바뀌면 system_logs 접두가 갈라진다(사이클 60 I1)"
    )


@pytest.mark.asyncio
async def test_f7_open_order_rmn_zero_is_not_open_and_releases(patched, caplog):
    """검증 r2 LOW(뮤테이션 M13 ESCAPED) — `rmn_qty=0`(전량 체결) 매도 주문은 열린 주문이 아니다.

    `int(rmn_qty) > 0` 이 `>= 0` 으로 뒤집히면 체결 완료 주문까지 `open_order` 로 집계돼
    그 종목이 영구 유지되고, 그것이 곧 필옵틱스 Defect 2(손절·트레일링 종일 억제) 재현 경로다.
    aged·보유·rmn=0 이면 해제돼야 한다.
    """
    _mod, fn = _entry()
    engine = _FakeOrderEngine({TICKER}, {TICKER: NOW - timedelta(hours=6)})
    patched["daily_orders"] = [_open_sell(TICKER, rmn=0)]

    caplog.set_level(logging.DEBUG)
    await fn(engine, _holdings(**{TICKER: 3}), min_age_s=MIN_AGE_S, now=NOW)

    assert TICKER not in engine._selling, (
        "rmn_qty=0 주문이 열린 주문으로 집계돼 영구 유지됐다(M13 `>`→`>=`)"
    )
    assert _warns(caplog, _MARKER) == [], "해제된 종목에 유지 관측이 함께 발화했다"
