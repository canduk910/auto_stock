"""cycle335 — 매수 축 「접수 후 경계」.

자문 = `_workspace/domain_consult/cycle335_buy_post_send_boundary.md`
(권고 요약 §3 의 회귀 1~10 이 이 파일, 11~13 은 `tests/unit/ast/test_cycle328_sell_pending_helper.py`)

## 고치는 것

`place_order` 가 성공하면 **그 주문은 이미 거래소에 있다.** 그런데 그 뒤의 PENDING
영속화가 실패하면 `execute_buy` 의 **발사 실패 정리 코드**가 실행됐다:

| | 주 경로(`except Exception:`) | 폴백(`except KisApiError` 하나뿐) |
|---|---|---|
| `pending_buys` | `discard` → 같은 종목 재매수(momentum·VB·LTV) | 재등록된 채 남음 |
| `pending_buy_amounts` | `pop` → **전략 예산 이중 사용**(7전략) | 과대계상 |
| 예외 | `raise` → `risk.on_tick`(try 없음) 관통 | 형제 핸들러가 못 받아 **관통** |
| `cached_buyable_at` | 미무효화 → 60초 stale → 잔고부족 거부 → `block_buy(+900s)` | 미무효화 |

🔴 **계좌 레벨 방어(`get_buyable`)는 이것을 못 막는다.** 전략 예산은 계좌 잔고보다 훨씬
작아 계좌 방어는 통과하고 **전략 예산 관문만 조용히 무력화**된다. 그래서 화면·DB 어느
쪽을 봐도 정상으로 보인다.

## 계약 — 접수된 자금은 묶어 둔다

접수된 매수는 「예약된 자금」이 아니라 **이미 묶인 자금**이다(KIS 가 접수 시점에
주문가능금액에서 뺀다). 여기서 `pending` 을 푸는 것은 자금이 풀린 것이 아니라
**우리가 묶인 사실을 잊는 것**이다. 유지의 비용은 **체결이 0건인 주문 한정**으로
그 슬롯·금액이 21:30 `_reset_daily_state` 까지 노는 것뿐이다(첫 부분체결만 나도
`_handle_buy_fill` 이 정상 해제한다 — `order_engine.py:2573-2576` 은 전량 분기 **앞**이다).

## Red 유효성 (작성 시점, HEAD = `a3f4841`)

RED = 1·2·3·4·5·6·7·10 (경계가 없어 전부 예외가 새거나 상태가 풀린다)
GREEN(무회귀 대조군) = 8·9
"""
from __future__ import annotations

import ast
import logging
import time
from pathlib import Path

import pytest
from asyncpg.exceptions import UniqueViolationError

from src.api.base import KisApiError
from src.models.trade import TradeStatus, TradeType

from tests.unit.engine.test_cycle271_execute_buy_fill_during_insert import (
    PRICE,
    TICKER,
    make_env,
)

pytestmark = pytest.mark.unit

MARKER = "[buy_post_send_error]"
RACE_MARKER = "[buy_fill_during_insert]"

#: 시장가 거부 → 지정가 5호가 폴백을 여는 실제 거부(루트 CLAUDE.md 의 키워드 표).
MARKET_DISALLOWED = KisApiError("1", "APBK1943", "시장가매매불가 종목입니다")

#: 매핑 6종 — `place_order` 응답 직후 동기 영역에서 등록된다. 접수 후 실패가
#: 이것들을 지우면 체결통보가 기본값 "momentum" 으로 잘못 귀속된다.
MAPPINGS = (
    "_order_qty", "_order_strategy", "_order_ticker",
    "_order_exchange", "_order_division", "_pending_buy_orders",
)


@pytest.fixture
def env(monkeypatch):
    e = make_env(monkeypatch)
    yield e
    for task in list(e.engine._pending_cancel_tasks.values()):
        task.cancel()


def _records(caplog, prefix: str) -> list[str]:
    """WARNING 이상 + 접두 토큰으로 한정.

    🔴 CI 루트 로거는 DEBUG 라 레벨로 거르지 않으면 무관한 행이 섞인다(cycle252 T2 교훈).
    """
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


def _arm_post_send_failure(env, monkeypatch, exc: BaseException):
    """PENDING INSERT 가 `exc` 로 실패하게 만든다 — 주문은 이미 나간 뒤다."""
    async def boom(record):
        if record.trade_type is TradeType.BUY and record.status is TradeStatus.PENDING:
            raise exc
        env.db.insert(record)

    monkeypatch.setattr("src.engine.order_engine.insert_trade", boom)


# ---------------------------------------------------------------------------
# 1~3 — 주 경로
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_1_market_path_post_send_failure_does_not_release_pending(env, monkeypatch):
    """🔴 코어가 예외를 던져도 `execute_buy` 가 정상 종료하고 **pending 을 유지**한다.

    이 케이스가 이 사이클의 본체다. 지금은 `except Exception:` 이
    `pending_buys.discard` + `pending_buy_amounts.pop` 후 `raise` 한다 — 그 둘이
    각각 **같은 종목 재매수**와 **전략 예산 이중 사용**을 연다.
    """
    _arm_post_send_failure(env, monkeypatch, TimeoutError("RDS failover"))

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    state = env.momentum.state
    assert TICKER in state.pending_buys, (
        "접수된 주문의 pending 이 풀렸다 — `is_ticker_blocked_for_buy` 가 False 가 되어 "
        "같은 종목을 다시 산다"
    )
    assert state.pending_buy_amounts.get(TICKER, 0) > 0, (
        "접수된 주문의 예정 금액이 사라졌다 — `_calc_used_funds` 가 그만큼 덜 세어 "
        "전략 예산이 이중으로 쓰인다"
    )
    assert env.registry.is_ticker_blocked_for_buy(TICKER), (
        "재매수 차단이 풀렸다"
    )
    # 주문은 정확히 한 번만 나갔다 — 경계가 재발사 경로를 열지 않는다.
    assert len(env.calls.place_order) == 1, env.calls.place_order


@pytest.mark.asyncio
async def test_2_market_path_post_send_failure_still_invalidates_cache_and_logs_accept(
    env, monkeypatch, caplog,
):
    """접수 로그와 가용액 캐시 무효화는 **경계 밖**이라 정상 실행된다.

    `cached_buyable_at` 이 0 으로 안 돌아가면 최대 60초 stale 인 가용액으로 낸 다음
    주문이 잔고부족 거부를 받고 `block_buy(+900s)` = **그 전략 15분 전면 매수 정지**가 된다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    _arm_post_send_failure(env, monkeypatch, TimeoutError("RDS failover"))

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert env.momentum.state.cached_buyable_at == 0.0, (
        "가용액 캐시가 무효화되지 않았다 — 60초 stale 가용액이 다음 주문을 "
        "잔고부족 거부로 몰아 900초 매수 락을 만든다"
    )
    accepted = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.INFO and r.getMessage().startswith("매수 주문 접수")
    ]
    assert len(accepted) == 1, f"접수 INFO 가 {len(accepted)}행: {accepted}"
    assert not env.momentum.state.is_buy_blocked(time.time()), "매수 락이 걸렸다"


@pytest.mark.asyncio
async def test_3_market_path_post_send_failure_keeps_all_order_mappings(env, monkeypatch):
    """매핑 6종이 전부 남는다 — 체결통보 귀속의 전제다.

    매핑이 사라지면 그 체결통보는 기본값 `"momentum"` 으로 잘못 INSERT 된다
    (루트 `CLAUDE.md` 「주문번호 매핑」 금기).
    """
    _arm_post_send_failure(env, monkeypatch, TimeoutError("RDS failover"))

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    order_no = env.calls.place_order and "BUY-000001"
    for name in MAPPINGS:
        mapping = getattr(env.engine, name)
        assert order_no in mapping, f"매핑 `{name}` 에 {order_no} 가 없다"


# ---------------------------------------------------------------------------
# 4~5 — 폴백 경로 (`except KisApiError` 핸들러 **안**이라는 위험한 자리)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_4_fallback_path_post_send_failure_does_not_escape_execute_buy(
    env, monkeypatch, caplog,
):
    """🔴 폴백 경로의 non-`KisApiError` 는 `execute_buy` 를 **관통하면 안 된다**.

    그 자리는 `except KisApiError as e:` 핸들러 **안**이라, 형제 핸들러
    `except Exception:` 이 받지 못한다(파이썬: `except` 블록 안에서 난 예외는 같은
    `try` 의 다른 `except` 로 가지 않는다). 관통하면 `risk.on_tick` 이 죽어
    **그 틱의 뒤 전략들이 청산 평가를 통째로 잃는다**.
    """
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    env.state.place_order_error = MARKET_DISALLOWED
    _arm_post_send_failure(env, monkeypatch, ConnectionResetError("connection reset"))

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert len(env.calls.place_order) == 2, (
        f"폴백이 발사되지 않았다(전제 붕괴): {env.calls.place_order}"
    )
    state = env.momentum.state
    assert TICKER in state.pending_buys, "폴백 접수 뒤 pending 이 풀렸다"
    assert state.pending_buy_amounts.get(TICKER, 0) > 0, "폴백 예정 금액이 사라졌다"
    assert state.cached_buyable_at == 0.0, "폴백 경로의 캐시 무효화가 실행되지 않았다"
    fb = [
        r.getMessage() for r in caplog.records
        if r.getMessage().startswith("시장가 거부 → 지정가 5호가 폴백")
    ]
    assert len(fb) == 1, f"폴백 WARNING 이 {len(fb)}행: {fb}"


@pytest.mark.asyncio
async def test_5_fallback_post_send_failure_does_not_register_low_funds_cooldown(
    env, monkeypatch,
):
    """🔴 `block_low_funds` 는 **발사 실패 전용**이다 — 접수 성공에는 걸리지 않는다.

    걸리면 접수된 주문이 있는 종목이 900초 동안 차단되고, 더 나쁘게는 운영자가
    로그(`지정가 폴백도 거부 → cooldown`)를 보고 **주문이 안 나갔다고 믿는다**.
    """
    env.state.place_order_error = MARKET_DISALLOWED
    _arm_post_send_failure(env, monkeypatch, ConnectionResetError("connection reset"))

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert not env.momentum.state.is_low_funds_blocked(TICKER, time.time()), (
        "접수 성공한 주문에 저자금 cooldown 이 걸렸다 — `:1517` 은 발사 실패 전용이다"
    )


# ---------------------------------------------------------------------------
# 6~8 — 마커
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trigger_fallback", "expected_path", "expected_price"),
    [(False, "market", PRICE), (True, "fallback", 20_250)],
)
async def test_6_marker_is_error_with_six_fields(
    env, monkeypatch, caplog, trigger_fallback, expected_path, expected_price,
):
    """`[buy_post_send_error]` ERROR 1행 + 6필드의 **값**, `path` 가 경로마다 다르다.

    🔴 `qty=`·`price=` 는 매도 축에 없는 필드다. 매도는 포지션이 남아 사후에 규모를
    알 수 있지만 **매수는 포지션도 장부도 없다** — 이 줄이 그 주문의 규모를 아는
    유일한 채널이다(그 밖에는 KIS 주문내역뿐).

    🔴 **필드 「존재」가 아니라 「값」을 본다.** 관문(2026-09-21)이 실측한 구멍이다 —
    `quantity`↔`record_price` 를 맞바꾸면 `qty=1250 price=20000` 이
    `qty=20000 price=1250` 이 되는데 **둘 다 0이 아니고 둘 다 그럴듯해서** 회귀
    14+17+11 케이스가 전부 초록이었다. `ticker`↔`order_no` 맞바꿈도 마찬가지다.
    판독 절차가 「건별로 KIS 주문내역과 **대조**한다」인데 `ticker`/`order_no` 는 그
    대조의 **키**이고 `qty`/`price` 는 대조 **대상**이다 — 어느 쌍이 뒤집혀도
    운영자는 엉뚱한 주문을 찾거나 엉뚱한 수량을 맞다고 판정한다.
    ⚠️ 매도 축은 cycle328 시나리오 J 에서 같은 교훈을 이미 겪었다.

    🔴 `logger.exception` 이어야 한다(`logger.error` 아님) — 레벨도 메시지도 같고
    **traceback 만 사라지는데**, 롤백 판정(「하루 5건이면 RDS 가 아픈 것」)에는 예외의
    정체(타임아웃인가·UNIQUE 인가·풀 고갈인가)가 필요하고 유일한 전달 수단이 `exc_info` 다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    if trigger_fallback:
        env.state.place_order_error = MARKET_DISALLOWED
    _arm_post_send_failure(env, monkeypatch, TimeoutError("RDS failover"))

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    recs = [r for r in caplog.records if r.getMessage().startswith(MARKER)]
    assert len(recs) == 1, f"마커가 {len(recs)}행: {[r.getMessage() for r in recs]}"
    rec = recs[0]
    msg = rec.getMessage()

    # 🔴 판별력의 전제 — 네 값이 서로 전부 달라야 맞바꿈이 드러난다.
    expected_qty = env.calls.place_order[-1]["quantity"]
    order_no = "BUY-000001"
    distinct = {str(TICKER), order_no, str(expected_qty), str(expected_price)}
    assert len(distinct) == 4, (
        f"픽스처 결함 — 네 값 중 같은 것이 있어 맞바꿈을 못 잡는다: {distinct}"
    )

    assert f"ticker={TICKER}" in msg, f"ticker 값이 틀렸다: {msg}"
    assert f"order_no={order_no}" in msg, f"order_no 값이 틀렸다: {msg}"
    assert "strategy=momentum" in msg, msg
    assert f"path={expected_path}" in msg, msg
    assert f"qty={expected_qty} price={expected_price}" in msg, (
        f"수량·가격이 뒤바뀌었거나 틀렸다(기대 qty={expected_qty} price={expected_price}): {msg}"
    )

    assert rec.levelno == logging.ERROR, (
        f"마커 레벨이 {rec.levelname} — ERROR 여야 한다"
        "(매도 축 대칭 + 21:30 top_patterns 편입)"
    )
    assert rec.exc_info is not None, (
        "`logger.exception` 이 아니라 `logger.error` 다 — traceback 이 사라져 "
        "「RDS 가 아픈 것인가」를 판정할 근거가 없어진다"
    )


@pytest.mark.asyncio
async def test_7_normal_skip_path_does_not_emit_the_error_marker(env, caplog):
    """🔴 **정상** skip(체결통보 선행)은 예외가 아니므로 마커가 나오지 않는다.

    cycle328 `test_g328_4` 와 같은 오염 차단이다 — 정상 경로가 에러 마커를 뱉으면
    그 창의 유일한 관측 채널이 잡음으로 덮인다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    env.injector.armed = True
    env.injector.fill_ratio = 1.0

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert _records(caplog, MARKER) == [], "정상 race 흡수 경로에서 에러 마커가 찍혔다"


@pytest.mark.asyncio
async def test_8_unique_violation_without_evidence_is_caught_by_boundary_not_absorbed(
    env, caplog,
):
    """🔴 증거 없는 `UniqueViolationError` — **코어는 전파하고 경계가 받는다**.

    이 두 층을 헷갈리면 안 된다. 코어가 그것을 **흡수해 성공으로 만들면**
    `[buy_fill_during_insert]` 가 찍히는데, 그건 "체결통보가 먼저 INSERT 했다" 는
    거짓 보고다(그 증거 = `order_no ∈ _completed_orders` 가 없다).
    경계는 그 예외를 **밖으로 안 내보낼 뿐** 성공으로 바꾸지 않는다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    env.db.rows.append({
        "ticker": TICKER, "order_no": "BUY-000001", "trade_type": TradeType.BUY.value,
        "status": TradeStatus.CANCELLED.value, "price": float(PRICE),
        "quantity": 1, "strategy": "momentum",
    })

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert len(_records(caplog, MARKER)) == 1, "경계가 받지 않았다"
    race = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.INFO and r.getMessage().startswith(RACE_MARKER)
    ]
    assert race == [], (
        "증거 없는 UNIQUE 위반을 코어가 흡수해 '체결통보 선행' 으로 잘못 보고했다"
    )


# ---------------------------------------------------------------------------
# 9 — 무회귀 (양성 대조군)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_9_happy_path_is_unchanged_and_silent(env, caplog):
    """성공 경로는 마커 0행 + 기존 상태 그대로 — 경계가 평시에 아무것도 안 한다."""
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")

    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    assert _records(caplog, MARKER) == []
    rows = env.db.rows_for(TICKER, "BUY-000001", TradeType.BUY)
    assert len(rows) == 1 and rows[0]["status"] == TradeStatus.PENDING.value, rows
    assert TICKER in env.momentum.state.pending_buys


# ---------------------------------------------------------------------------
# 10 — swing poll 연동 (자문이 찾은, 요청서에 없던 행위 변화)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_swing_poll_buy_succeeded_predicate_stays_true(env, monkeypatch):
    """🔴 donchian·kojiro 의 **매수 직후 HIGH 구독**이 건너뛰어지지 않는다.

    `scheduler._swing_buy_poll_loop` 은 `execute_buy` 직후
    `buy_succeeded = (t in state.pending_buys or t in state.positions)` 로 성공을
    판정하고, 참일 때만 「안전 불변식: 보유 종목 손절/트레일링 평가 필수 → 매수 직후
    HIGH 구독」을 실행한다.

    경계가 없으면 접수 성공 + 장부 실패에서 `pending_buys` 가 지워지고 포지션은
    체결통보 전이라 아직 없어 **판정이 False** 가 된다 → 그 구독이 통째로
    건너뛰어지고 회복은 `_scan_loop` 5분 뒤다. donchian·kojiro 는 멀티데이 전략이라
    그 5분이 **손절 blind** 다. `total_bought` 집계도 어긋난다.

    ⚠️ 이 케이스는 스케줄러의 술어를 **거울**로 복제한다 — 아래 양성 대조군이
    그 술어가 `scheduler.py` 에 실제로 살아 있는지 확인해 거울이 조용히 낡는 것을 막는다.
    """
    src = Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"
    text = src.read_text(encoding="utf-8")
    assert "buy_succeeded = (" in text and "in strategy.state.pending_buys" in text, (
        "`_swing_buy_poll_loop` 의 `buy_succeeded` 술어를 찾지 못했다 — "
        "이 거울이 낡았다(가드가 공허해진다)"
    )

    _arm_post_send_failure(env, monkeypatch, TimeoutError("RDS failover"))
    await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    state = env.momentum.state
    buy_succeeded = TICKER in state.pending_buys or TICKER in state.positions
    assert buy_succeeded, (
        "swing poll 이 이 매수를 '실패' 로 읽는다 — 매수 직후 HIGH 구독이 "
        "건너뛰어져 다음 `_scan_loop`(5분)까지 손절 blind 다"
    )


# ---------------------------------------------------------------------------
# 11 — 🔴 **경계가 진짜 발사 실패까지 삼키면 안 된다** (관문 G5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_genuine_send_failure_still_releases_pending(env, monkeypatch):
    """`place_order` **자체**가 실패하면 `pending` 은 **풀려야** 한다.

    이 케이스가 위 1~10 의 **반대 극**이자 양성 대조군이다. 경계가 지키는 것은
    「주문이 나간 뒤」뿐이고, 나가지 **못한** 주문의 자금까지 묶으면 그 종목이 하루 종일
    `is_ticker_blocked_for_buy` 에 걸리고 예산을 점유한다 — 이 시정이 고치려던 것과
    정확히 반대 방향의 같은 크기 피해다.

    🔴 관문(2026-09-21)이 실측한 빈 곳이다 — `execute_buy` 의 outer `except Exception:`
    정리 블록을 **통째로 지워도, 둘 중 하나만 지워도** 리포 전체에서 0건이 붉었다
    (`except KisApiError` 쪽은 `test_order_engine_buy.py` 2건이 이미 막고 있다).
    그리고 cycle335 의 주석이 그 블록을 「발사 실패에만 닿는다」고 **명시적으로 가리켜**
    다음 사람을 그 줄로 유인한다. 그래서 이 사이클의 산출물로 닫는다.
    """
    class _Boom(RuntimeError):
        """`KisApiError` 가 **아닌** 발사 실패 — outer `except Exception:` 으로 간다."""

    async def never_sends(*args, **kwargs):
        raise _Boom("소켓 끊김 — 주문이 나가지 못했다")

    monkeypatch.setattr("src.engine.order_engine.place_order", never_sends)

    with pytest.raises(_Boom):
        await env.engine.execute_buy(TICKER, current_price=PRICE, strategy=env.momentum)

    state = env.momentum.state
    assert TICKER not in state.pending_buys, (
        "주문이 **나가지 못했는데** pending 이 남았다 — 그 종목이 하루 종일 "
        "재매수 차단에 걸리고 예산을 점유한다"
    )
    assert TICKER not in state.pending_buy_amounts, (
        "나가지 못한 주문의 예정 금액이 남았다 — 전략 예산이 과대계상된다"
    )
    assert not env.registry.is_ticker_blocked_for_buy(TICKER)


# ---------------------------------------------------------------------------
# 코어 층 — 타입 충실도 회수 (자문 「잃는 것」 대응)
# ---------------------------------------------------------------------------
# 경계가 서면 `execute_buy` 층에서는 예외 **타입**을 더 이상 볼 수 없다(래퍼가
# `except Exception` 으로 삼킨다). 코어가 예외를 **감싸서** 다른 타입으로 던지는
# 회귀는 위 케이스들을 전부 통과한다. 그래서 「코어는 전파한다」는 cycle334 계약을
# 코어 층에서 직접 단언한다 — 두 층의 계약이 나란히 봉인된다.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        UniqueViolationError("duplicate key"),
        ConnectionResetError("connection reset by peer"),
    ],
    ids=["unique_violation_without_evidence", "non_unique_db_error"],
)
async def test_core_still_propagates_the_original_exception_type(env, monkeypatch, exc):
    """🔴 코어 `_persist_pending_after_send` 는 예외를 **타입 그대로** 올려보낸다."""
    async def boom(record):
        raise exc

    monkeypatch.setattr("src.engine.order_engine.insert_trade", boom)

    with pytest.raises(type(exc)):
        await env.engine._persist_pending_after_send(
            trade_type=TradeType.BUY, ticker=TICKER, order_no="BUY-CORE-1",
            strategy_id="momentum", record_price=PRICE, quantity=1, path="market",
        )


def test_core_has_no_try_and_buy_wrapper_has_exactly_one():
    """🔴 경계는 **코어가 아니라 래퍼**에 있다 (구조 확인).

    코어에 `try` 를 들이면 두 축 래퍼의 `except` 가 영영 도달 불가가 되고,
    래퍼의 `except` 를 좁히거나 지우는 회귀가 **무증상**이 된다.
    """
    src = Path(__file__).resolve().parents[3] / "src" / "engine" / "order_engine.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    def _fn(name):
        for n in ast.walk(tree):
            if isinstance(n, ast.AsyncFunctionDef) and n.name == name:
                return n
        raise AssertionError(f"`{name}` 을 찾지 못했다")

    core_tries = [n for n in ast.walk(_fn("_persist_pending_after_send"))
                  if isinstance(n, ast.Try)]
    assert not core_tries, f"코어에 `try` 가 {len(core_tries)}개 있다"

    wrapper = _fn("_persist_buy_pending_after_send")
    wrapper_tries = [n for n in wrapper.body if isinstance(n, ast.Try)]
    assert len(wrapper_tries) == 1, (
        f"매수 래퍼의 최상위 `try` 가 {len(wrapper_tries)}개 (기대 1개)"
    )
