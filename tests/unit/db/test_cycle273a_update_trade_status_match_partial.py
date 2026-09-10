# DEST: tests/unit/db/test_cycle273a_update_trade_status_match_partial.py
"""cycle273a Red — D2(가)-b: `update_trade_status` 의 PARTIAL 포괄은 **call-site opt-in**.

명세 = `_workspace/red/cycle273a_c235v2_cancel_timer_and_partial_spec.md`
정본 = `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` §2·§3.2·§3.3

## 무엇이 문제인가

`src/db/trade_history.py:107` 이 status 필터를 **`PENDING` 리터럴 단독**으로 박는다.
부분 체결로 이미 PARTIAL 이 된 행에 전량 체결의 1차 UPDATE 가 오면 `affected=0`
→ 보정 INSERT → UniqueViolation → 강제 UPDATE 라는 3단 우회를 매번 탄다.
대조군 `_update_trade_status_by_order_no`(`:212-229`)는 cycle235 N1-b 로 이미
`PENDING ∪ PARTIAL` 이다.

## 🔴 전역 확대는 무행위가 아니다 — 이 파일에서 가장 중요한 계약

`match_partial` 를 기본 True 로 하거나 SQL 리터럴을 통째로 넓히면
`_cancel_after_wait`(`order_engine.py:1515`)·`_cancel_and_reorder`(`:1541`)의
**CANCELLED** 호출이 함께 넓어져 **PARTIAL 행이 CANCELLED 로 뒤집힌다**. 그 행은
정산(`get_today_trades_for_settlement`, COMPLETED∪PARTIAL)에서도 sync
(`get_today_*_for_sync`, CANCELLED 제외)에서도 빠진다 = 실제로 산 3주가 "취소" 로
기록되고 `_sync_orders_to_db` 가 재-INSERT 를 시도한다(042700 핑퐁 계열).

## HEAD 기준 RED / GREEN

| 테스트 | HEAD | 이유 |
|---|---|---|
| `test_b2_default_sql_is_pending_only_byte_identical` | GREEN(계약 가드) | 기본 경로 SQL byte 동일 봉인 |
| `test_b2b_match_partial_true_widens_to_pending_or_partial` | **RED** | 키워드 미존재 → `TypeError` |
| `test_b2c_match_partial_is_keyword_only` | **RED** | 동상 |
| `test_b2d_match_partial_scopes_to_today` | **RED** | 직전 검증 HIGH#1 — WHERE 에 order_no 도 날짜 경계도 없어 다른 order_no 의 좌초 PARTIAL 행까지 잡힌다. 이 사이클은 KST 당일 하한을 회귀 가드로 신설(§Open Q O-A1 — order_no 자체는 cycle273b F-1 범위) |
"""

from __future__ import annotations

import inspect

import pytest

import src.db.pg as pg
from src.db.trade_history import update_trade_status
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit

# HEAD(`a10191b`) 의 기본 경로 SQL — 이 문자열이 바뀌면 "기본값이 현행을 byte 동일
# 보존한다" 는 계약이 깨진 것이다(scheduler 죽은 import·기존 스위트 무영향의 전제).
_DEFAULT_SQL = (
    "UPDATE trade_history SET status = $1, price = $2 "
    "WHERE ticker = $3 AND trade_type = $4 "
    "AND status = $5 AND strategy = $6"
)


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch):
    """`pg.execute` 를 가로채 (sql, args) 를 기록한다."""
    calls: list[tuple[str, tuple]] = []

    async def _execute(sql, *args):
        calls.append((sql, args))
        return "UPDATE 1"

    monkeypatch.setattr(pg, "execute", _execute)
    return calls


@pytest.mark.asyncio
async def test_b2_default_sql_is_pending_only_byte_identical(captured):
    """기본 호출(= C5/C6 CANCELLED 경로)은 현행 SQL 을 **byte 동일** 유지한다."""
    await update_trade_status(
        "005930", TradeType.BUY, TradeStatus.CANCELLED, strategy="kojiro", price=100,
    )
    sql, args = captured[0]

    assert sql == _DEFAULT_SQL, (
        "기본 경로 SQL 이 바뀌었다 — CANCELLED 호출까지 넓어지면 PARTIAL 행이 "
        "CANCELLED 로 뒤집혀 정산·sync 양쪽에서 소실된다(§3.3)"
    )
    assert "ANY(" not in sql
    assert args[4] == TradeStatus.PENDING.value
    assert not isinstance(args[4], list)


@pytest.mark.asyncio
async def test_b2b_match_partial_true_widens_to_pending_or_partial(captured):
    """RED (HEAD) — `match_partial=True` 만 PENDING∪PARTIAL 로 넓힌다."""
    await update_trade_status(
        "005930", TradeType.BUY, TradeStatus.COMPLETED, strategy="kojiro", price=100,
        match_partial=True,
    )
    sql, args = captured[0]

    assert "status = ANY(" in sql and "::text[]" in sql, (
        "match_partial=True 인데 status 필터가 여전히 단일 비교다"
    )
    status_arg = next(a for a in args if isinstance(a, list))
    assert status_arg == [TradeStatus.PENDING.value, TradeStatus.PARTIAL.value], (
        "cycle235 N1-b `_update_trade_status_by_order_no` 와 같은 형태여야 한다"
    )
    # COMPLETED/CANCELLED 는 종결 상태 — 갱신 대상에 절대 넣지 않는다.
    assert TradeStatus.COMPLETED.value not in status_arg
    assert TradeStatus.CANCELLED.value not in status_arg


@pytest.mark.asyncio
async def test_b2c_match_partial_is_keyword_only():
    """RED (HEAD) — `match_partial` 은 **keyword-only** 여야 한다.

    위치 인자로 열어 두면 기존 6-인자 호출부의 인자 밀림 하나가 조용히
    "전역 확대" 로 바뀐다(§3.3 이 막으려는 바로 그 사고).
    """
    sig = inspect.signature(update_trade_status)
    assert "match_partial" in sig.parameters, "match_partial 파라미터 미존재"
    param = sig.parameters["match_partial"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
        f"match_partial 이 keyword-only 가 아니다 (kind={param.kind})"
    )
    assert param.default is False, "기본값은 반드시 False (현행 보존)"


@pytest.mark.asyncio
async def test_b2d_match_partial_scopes_to_today(captured):
    """회귀 가드(직전 검증 HIGH#1) — `match_partial=True` 는 KST 당일 하한도 겸한다.

    WHERE 가 ticker+trade_type+strategy+status 뿐이면 같은 조합의 **다른 order_no**
    가 남긴 좌초 PARTIAL 행까지 오늘 전량 체결의 COMPLETED UPDATE 가 함께 덮어쓴다.
    order_no 자체를 WHERE 에 넣는 완전한 시정은 cycle273b F-1 범위(이 사이클 밖) —
    이 사이클은 KST 당일 하한으로 노출을 좁힌다: 어제 이전 좌초 행은 제외된다.
    """
    from src.db.trade_history import _today_kst_iso

    await update_trade_status(
        "005930", TradeType.BUY, TradeStatus.COMPLETED, strategy="kojiro", price=100,
        match_partial=True,
    )
    sql, args = captured[0]

    assert "timestamp >=" in sql, (
        "match_partial=True 인데 KST 당일 하한이 WHERE 에 없다 — 다른 order_no 의 "
        "좌초 PARTIAL 행이 오늘 전량체결의 COMPLETED UPDATE 에 휩쓸릴 수 있다"
    )
    from datetime import datetime as _dt
    bound = [a for a in args if isinstance(a, _dt)]
    assert bound and bound[0] == _dt.fromisoformat(_today_kst_iso()), (
        "하한 값이 KST 자정 계약과 다르거나 datetime 으로 바인딩되지 않았다"
    )
    assert not any(isinstance(a, str) and a.startswith(_today_kst_iso()[:10]) for a in args), (
        "KST 하한이 str 로 바인딩됐다 — timestamp 는 TIMESTAMPTZ 라 asyncpg 가 DataError 를 던진다"
        "(모듈 관례 = datetime.fromisoformat, trade_history.py:358 등; 검증 r2 HIGH#1)"
    )

    # match_partial=False(기본, CANCELLED 호출)는 이 하한이 붙지 않는다 — byte 동일
    # 봉인은 test_b2_default_sql_is_pending_only_byte_identical 이 별도로 지킨다.
    await update_trade_status(
        "005930", TradeType.BUY, TradeStatus.CANCELLED, strategy="kojiro",
    )
    default_sql, _default_args = captured[1]
    assert "timestamp >=" not in default_sql, (
        "기본(match_partial=False) 경로에 날짜 하한이 새어 들어갔다 — byte 동일 계약 위반"
    )
