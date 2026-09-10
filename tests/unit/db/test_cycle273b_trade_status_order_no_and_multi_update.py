# DEST: tests/unit/db/test_cycle273b_trade_status_order_no_and_multi_update.py
"""cycle273b Red — D2(다) 무행위 3건 중 **F-3 관측**과 **F-1/F-2 WHERE order_no**.

명세 = `_workspace/red/cycle273b_philoptics_no_behavior_3_spec.md`
정본 = `_workspace/analysis/2026-09-10_161580_root_cause.md` ·
       `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` §5·§6

## 사건 (필옵틱스 161580)

`update_trade_status` 의 매칭 키가 `(ticker, trade_type, status='PENDING', strategy)`
라 **주문 단위가 아니다**. `ORDER BY`/`LIMIT` 도 없어 조건을 만족하는 행이 여럿이면
**전부** 갱신된다 — 한 주문의 체결이 같은 종목·같은 전략의 **다른 주문 행**을 덮는다.

- **F-3** `[trade_status_multi_update]` = `affected > 1` 관측(WARNING). 무행위.
- **F-1/F-2** = WHERE 에 `order_no` 추가. WHERE 를 **좁히기만** 하므로 무행위.

## ⚠️ F-3 의 진단력 한계(정직하게)

F-1 과 같은 커밋에 들어가면 migration 029 부분 UNIQUE `(ticker, order_no, trade_type)`
때문에 `affected > 1` 은 비어 있지 않은 order_no 에 대해 **구조적으로 불가능**해진다.
F-3 는 과거를 세지 못하고 **영구 회귀 감시자**(WHERE·인덱스가 후퇴하면 붉어진다 /
`order_no=''` 인 수기 행에는 여전히 유효)가 된다.

## HEAD 기준 RED / GREEN

| 테스트 | HEAD |
|---|---|
| `test_f3_multi_update_emits_warning` | **RED** |
| `test_f3_single_update_stays_silent` | GREEN(뮤테이션 가드 `>1`→`>=1`) |
| `test_f1_order_no_narrows_where` | **RED** |
| `test_f1_order_no_is_keyword_only` | **RED** |
| `test_f1_order_no_empty_string_still_narrows_where` | **RED** (직전 검증 LOW#3) |
| `test_f1_order_no_and_match_partial_placeholders_are_sequential` | **RED** (직전 검증 MEDIUM#2 companion) |
| `test_f1_default_sql_unchanged_when_order_no_absent` | GREEN(byte 동일 계약) |
"""

from __future__ import annotations

import inspect
import logging
import re

import pytest

import src.db.pg as pg
from src.db.trade_history import update_trade_status
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit

_MARKER = "[trade_status_multi_update]"

# HEAD(`a10191b`) 기본 경로 SQL — `order_no` 미전달 시 byte 동일 계약.
_DEFAULT_SQL_NO_PRICE = (
    "UPDATE trade_history SET status = $1 "
    "WHERE ticker = $2 AND trade_type = $3 "
    "AND status = $4 AND strategy = $5"
)


def _capture(monkeypatch: pytest.MonkeyPatch, result: str = "UPDATE 1"):
    calls: list[tuple[str, tuple]] = []

    async def _execute(sql, *args):
        calls.append((sql, args))
        return result

    monkeypatch.setattr(pg, "execute", _execute)
    return calls


def _warns(caplog, prefix: str) -> list[str]:
    """WARNING 이상 + prefix 한정(CI 루트 로거는 DEBUG — 실패 흔적 debug 혼입 차단)."""
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


# ---------------------------------------------------------------------------
# F-3 — affected > 1 관측
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f3_multi_update_emits_warning(monkeypatch, caplog):
    """RED (HEAD) — 한 주문의 체결이 다중 행을 덮어도 오늘은 `logger.debug` 뿐이다.

    `_DbLogHandler` 가 INFO 컷이라 debug 는 `system_logs` 에 도달하지 않는다
    (교훈 `feedback_caplog_debug_level`) — 그래서 이 관측은 **WARNING 이상**이어야 한다.
    """
    _capture(monkeypatch, result="UPDATE 2")
    caplog.set_level(logging.DEBUG)

    affected = await update_trade_status(
        "161580", TradeType.BUY, TradeStatus.COMPLETED, strategy="donchian_swing",
    )

    assert affected == 2
    rows = _warns(caplog, _MARKER)
    assert rows, f"{_MARKER} WARNING 이 없다 — 다중 행 덮어쓰기가 무증거로 지나간다"
    msg = rows[0]
    assert "ticker=161580" in msg
    assert "affected=2" in msg
    assert "trade_type=BUY" in msg


@pytest.mark.asyncio
async def test_f3_single_update_stays_silent(monkeypatch, caplog):
    """GREEN(뮤테이션 가드) — `affected > 1` 을 `>= 1` 로 바꾸면 붉어진다."""
    _capture(monkeypatch, result="UPDATE 1")
    caplog.set_level(logging.DEBUG)

    await update_trade_status(
        "161580", TradeType.BUY, TradeStatus.COMPLETED, strategy="donchian_swing",
    )

    assert _warns(caplog, _MARKER) == [], (
        "정상 1행 갱신에 관측이 발화하면 WARNING 이 매 체결마다 쌓인다"
    )


@pytest.mark.asyncio
async def test_f3_zero_update_stays_silent(monkeypatch, caplog):
    """GREEN(뮤테이션 가드) — `affected != 1` 류 뒤집기 차단.

    `affected == 0` 은 **정상 경로**다(진짜 체결통보 선행 race). 여기에 WARNING 이
    붙으면 매일 수십 행이 쌓여 진짜 신호가 묻힌다.
    """
    _capture(monkeypatch, result="UPDATE 0")
    caplog.set_level(logging.DEBUG)

    await update_trade_status(
        "161580", TradeType.BUY, TradeStatus.COMPLETED, strategy="donchian_swing",
    )

    assert _warns(caplog, _MARKER) == []


# ---------------------------------------------------------------------------
# F-1/F-2 — WHERE 에 order_no
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f1_order_no_narrows_where(monkeypatch):
    """RED (HEAD) — `order_no` 를 넘기면 WHERE 가 그 주문 한 건으로 좁혀진다."""
    calls = _capture(monkeypatch)

    await update_trade_status(
        "161580", TradeType.BUY, TradeStatus.COMPLETED, strategy="donchian_swing",
        price=25_000, order_no="0000123456",
    )

    sql, args = calls[0]
    assert "AND order_no = $" in sql, f"WHERE 에 order_no 조건이 없다 — sql={sql!r}"
    assert "0000123456" in args, "order_no 값이 바인딩되지 않았다"
    # 좁히기만 한다 — 기존 4-eq 조건은 그대로 남아야 한다(넓히면 무행위가 아니다).
    for token in ("ticker = $", "trade_type = $", "status = $", "strategy = $"):
        assert token in sql, f"기존 조건 {token!r} 이 사라졌다 — WHERE 를 넓히면 안 된다"


@pytest.mark.asyncio
async def test_f1_order_no_is_keyword_only():
    """RED (HEAD) — `order_no` 는 keyword-only 여야 한다.

    위치 인자로 열면 기존 6-인자 호출부의 인자 밀림 하나가 조용히 WHERE 를 바꾼다.
    """
    sig = inspect.signature(update_trade_status)
    assert "order_no" in sig.parameters, "order_no 파라미터 미존재"
    p = sig.parameters["order_no"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, f"kind={p.kind}"
    assert p.default is None, "기본값은 None (미전달 시 현행 SQL byte 동일)"


@pytest.mark.asyncio
async def test_f1_order_no_empty_string_still_narrows_where(monkeypatch):
    """직전 검증 LOW#3 — `order_no=""` (수기 입력 행 표기) 도 WHERE 를 좁혀야 한다.

    `if order_no is not None:` 은 `""` 를 truthy 판정과 달리 여전히 절을 붙인다.
    뮤테이션 M7(`is not None` → truthy `if order_no:`) 은 `order_no=""` 에서만
    행위가 갈린다 — 다른 전 케이스가 등가라 이 케이스 하나가 유일한 킬러다.
    """
    calls = _capture(monkeypatch)

    await update_trade_status(
        "161580", TradeType.BUY, TradeStatus.COMPLETED, strategy="donchian_swing",
        order_no="",
    )

    sql, args = calls[0]
    assert "AND order_no = $" in sql, f"order_no='' 도 WHERE 를 좁혀야 한다 — sql={sql!r}"
    assert args[-1] == "", "빈 문자열도 그대로 바인딩돼야 한다(수기 행 order_no='' 계약)."


@pytest.mark.asyncio
async def test_f1_order_no_and_match_partial_placeholders_are_sequential(monkeypatch):
    """직전 검증 MEDIUM#2 companion — SQL 레벨에서 동적 절 2개(`AND timestamp >= $n`
    + `AND order_no = $m`) 가 공존할 때 `$` 플레이스홀더가 `1..len(args)` 로 연속인지
    고정한다(오프바이원 류는 여기서 잡힌다 — 실 PG 왕복은 통합 스위트가 담당).
    """
    calls = _capture(monkeypatch)

    await update_trade_status(
        "161580", TradeType.BUY, TradeStatus.COMPLETED, strategy="donchian_swing",
        price=25_000, profit_loss=100.0, order_no="0000123456", match_partial=True,
    )

    sql, args = calls[0]
    placeholders = sorted(int(n) for n in re.findall(r"\$(\d+)", sql))
    assert placeholders == list(range(1, len(args) + 1)), (
        f"플레이스홀더가 연속(1..{len(args)})이 아니다 — {placeholders}, sql={sql!r}"
    )
    assert sql.rstrip().endswith(f"${len(args)}"), (
        "order_no 절이 SQL 의 마지막(가장 큰 번호)이어야 한다 — 뒤에 다른 동적 절이 없다."
    )
    assert args[-1] == "0000123456"


@pytest.mark.asyncio
async def test_f1_default_sql_unchanged_when_order_no_absent(monkeypatch):
    """GREEN(byte 동일 계약) — 미전달이면 SQL 문자열이 HEAD 와 같아야 한다.

    scheduler 의 죽은 import·기존 스위트 117 hit 무영향의 전제다.
    """
    calls = _capture(monkeypatch)

    await update_trade_status(
        "161580", TradeType.BUY, TradeStatus.CANCELLED, strategy="donchian_swing",
    )

    sql, args = calls[0]
    assert sql == _DEFAULT_SQL_NO_PRICE, f"기본 경로 SQL 이 바뀌었다 — {sql!r}"
    assert "order_no" not in sql
    assert args == (
        TradeStatus.CANCELLED.value, "161580", TradeType.BUY.value,
        TradeStatus.PENDING.value, "donchian_swing",
    )
