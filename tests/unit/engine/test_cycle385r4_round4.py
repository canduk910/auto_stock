"""cycle385 부록 R4 — 4차 검토 결정(D2 · D4 · D5) 반영 (TR4-1 ~ TR4-11).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R4
사용자 전제(2026-09-26) = R-INV-1 **과소 추적 금지** · R-INV-2 **운영자 몫을 팔지 않는다**.

## 부록 R4 가 바꾸는 것 (요지)

- **D2** — 「안 걸렸다」(= `_selling` 을 풀어도 되는 발사 실패)를 모듈 수준 판정 한 곳
  `order_engine._sell_not_placed_reason(exc)` 로 모은다. 참(이유 문자열) = APBK0400(부록 R3 K2 그대로) ·
  **주문 자체에 붙은 결정적 거부** — 같은 본문의 첫 전송 시도도 똑같이 거부됐을 것:
  시장가 불가(`is_market_order_disallowed` — APBK1943·APBK3013 계열) · 장운영시간 외
  (`is_market_closed_rejection` — APBK0918 + 장운영시간 문구). 그 밖(EGW00201 초당 한도 · 5xx · 전송 예외 ·
  모르는 코드 · 보유 부족 문구)은 None = 「전송 중」(유지). 분류는 `src.api.balance` 의 기존 판정 함수만
  쓴다 — 🔴 **msg1 문구 기반**이라 같은 코드라도 문구가 분류기에 안 걸리면 「전송 중」이다(덜 푸는 쪽).
  재주문(`_cancel_and_reorder`)과 수동 매도 라우트가 같은 판정을 쓴다.
- **D4** — 주문 조회가 실패했는데(`fills is None`) 걸린 매도가 없는 보류(조회 await 중 통보가 추적을
  줄였다 — seed 1177)는 `[sell_qty_unnoticed_fills]`(「거래소가 확인한 미통보 체결」)를 쓰지 않는다 →
  `[sell_qty_hold_orders_unavailable] … orders=<이유>`. 동작(보류)은 그대로(D1).
- **D5** — 행위 테스트 공백: MX12(원장 시작 전 주문 크레딧에서 `- seen` 누락) · MX3(`_pre_cap` 에서
  `- _post_credit` 누락) · MX4(`_old_credit` 에서 종목 크레딧 누락 — 과소 추적 쪽). MX7(손님 manual 의
  APBK0400 이 주인의 `_selling` 을 푼다)은 라우트 파일(`test_cycle385_manual_sell_selling.py`).
- **R5 T4** — 재주문 해제 조건에서 `_cancel_ok` 를 지우는 변이(원주문 취소 실패 뒤 `place=none` 해제)는
  AST AR2-3 만 잡았다 → TR4-11 이 행위로 잡는다.

## 하네스

`_Acct`·`_env`·`_reorder_env`·`_await_sell_timer`·`_apbk0400`·`drain` = 부록 R2 파일,
`_sell_notice`·`_map_order`·`_held`·`_warn_lines` = B7 파일, `_install_acct_t`·`_row_t`·`_fill_ours`·
`SINCE`·`PRE`·`POST` = 부록 R3 파일.

🔴 벽시계 금지 — 원장 시작·행 시각은 R3 파일의 상수 그대로.
🔴 caplog 단언은 WARNING 이상 + prefix(CI 루트 로거 DEBUG — cycle252 T2).
🔴 새 심볼(`_sell_not_placed_reason`)은 함수 안에서 import 한다 — 구현 전 수집 에러로 파일 전체가
   뭉개지면 어느 행위가 붉은지 가려지지 않는다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.base import KisApiError
from src.engine.strategy_base import Signal
from tests.unit.engine.test_cycle385_b7_partial_sell import (
    TICKER,
    _held,
    _map_order,
    _sell_notice,
    _warn_lines,
)
from tests.unit.engine.test_cycle385r2_round2 import (  # noqa: F401 — drain 은 픽스처
    _Acct,
    _await_sell_timer,
    _env,
    _reorder_env,
    drain,
)
from tests.unit.engine.test_cycle385r3_round3 import (
    KST,
    POST,
    PRE,
    _fill_ours,
    _install_acct_t,
    _row_t,
)

pytestmark = pytest.mark.unit

_OE_LOGGER = "src.engine.order_engine"

# ── 실측·정본 문구(분류기 키워드가 걸리는 모양) ──
_CLOSED = ("APBK0918", "장운영시간이 아닙니다.")
_CLOSED_PRE = ("APBK0918", "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)")
_DISALLOWED_1943 = ("APBK1943", "시장가호가불가 종목입니다.")
_DISALLOWED_AFTER = ("APBK3013", "[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다.")
_DISALLOWED_SINGLE = (
    "APBK3013", "[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선 취소 주문만 가능합니다",
)
_QTY = ("APBK0400", "주문 가능한 수량을 초과했습니다.")
_EGW = ("EGW00201", "초당 거래건수를 초과하였습니다.")
_HOLDING_SHORT = ("APBK0918", "매도가능수량이 부족합니다.")      # 보유 부족 — 앞 시도 접수가 만들 수 있다
_UNKNOWN = ("APBK9999", "처리 중 오류가 발생했습니다.")
_QTY_CODE_OTHER_MSG = ("APBK0400", "주문번호가 올바르지 않습니다.")  # 코드만 같고 문구가 다르다


def _kis(pair) -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd=pair[0], msg1=pair[1])


# ════════════════════════════════════════════════════════════════════════════
# TR4-1 — D2 판정표: `_sell_not_placed_reason`
# ════════════════════════════════════════════════════════════════════════════
def test_r4_1_not_placed_reason_table():
    """🔴 TR4-1 (D2) — 「우리 매도가 거래소에 걸리지 않았다」가 **확정되는** 예외만 이유 문자열.

    - APBK0400(수량 초과 문구) → `qty_exceeded`(부록 R3 K2 그대로)
    - 장운영시간 외 → `market_closed` · 프리마켓 문구(두 분류기에 다 걸림) → `market_closed`
      (`execute_sell` 과 같은 우선순위)
    - 시장가 불가(APBK1943 · APBK3013 애프터 · 단일가) → `market_order_disallowed`
    - EGW00201 · 보유 부족 문구(APBK0918) · 모르는 코드 · 코드만 APBK0400 인 다른 문구 · 전송 예외 ·
      HTTP 5xx · `RuntimeError` → None(「전송 중」)
    - never-raise — 판정 함수가 던지는 모양(msg1 이 문자열이 아니다)도 None.
    """
    from src.engine.order_engine import _sell_not_placed_reason as npr

    req = httpx.Request("POST", "https://openapi.koreainvestment.com:9443/uapi/x")
    cases = [
        (_kis(_QTY), "qty_exceeded"),
        (_kis(_CLOSED), "market_closed"),
        (_kis(_CLOSED_PRE), "market_closed"),
        (_kis(_DISALLOWED_1943), "market_order_disallowed"),
        (_kis(_DISALLOWED_AFTER), "market_order_disallowed"),
        (_kis(_DISALLOWED_SINGLE), "market_order_disallowed"),
        (_kis(_EGW), None),
        (_kis(_HOLDING_SHORT), None),
        (_kis(_UNKNOWN), None),
        (_kis(_QTY_CODE_OTHER_MSG), None),
        (RuntimeError("KIS down"), None),
        (httpx.ReadTimeout("read timeout", request=req), None),
        (httpx.HTTPStatusError("500", request=req, response=httpx.Response(500, request=req)), None),
        (KisApiError(rt_cd="1", msg_cd="APBK0400", msg1=object()), None),   # 판정 함수가 던진다
    ]
    for exc, want in cases:
        assert npr(exc) == want, f"{exc!r} → {npr(exc)!r} (기대 {want!r})"


# ════════════════════════════════════════════════════════════════════════════
# TR4-2 — D2 재주문: 결정적 거부는 「안 걸렸다」 → `_selling` 을 풀고 분류를 남긴다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pair,cls",
    [
        (_CLOSED, "market_closed"),
        (_CLOSED_PRE, "market_closed"),
        (_DISALLOWED_1943, "market_order_disallowed"),
        (_DISALLOWED_AFTER, "market_order_disallowed"),
        (_DISALLOWED_SINGLE, "market_order_disallowed"),
        (_QTY, "qty_exceeded"),
    ],
    ids=["closed", "closed_premarket", "disallowed_1943", "disallowed_after", "disallowed_single",
         "qty_exceeded"],
)
async def test_r4_2_reorder_deterministic_rejection_releases_selling(
    monkeypatch, caplog, drain, pair, cls,
):
    """🔴 TR4-2 (D2 · 재주문) — 자동 S1 10(매핑, `_selling`) · 통보 4 → 30초 타이머 → 원주문 취소 성공 →
    재주문이 `pair` 로 거부.

    기대: `_selling`·`_selling_since`·동결 표식 **해제** · `[reorder_selling_released]` 1행
    (`place=rejected` · `reject=<cls>`) · 이어진 다음 손절이 실제로 발사된다(추적 6).
    R3(APBK0400 만): 시장가 불가·장운영시간 외도 「전송 중」으로 읽어 `_selling` 을 `selling_reconcile`
    (15분 sync + 180초, 09:30 전에는 돌지 않는다)까지 남기고 그 사이 손절이 멈췄다.
    """
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    monkeypatch.setattr(_oe, "place_order", AsyncMock(side_effect=_kis(pair)))
    _map_order(env, "S1", 10, "kojiro")
    env.engine._selling.add(TICKER)
    env.engine._selling_since[TICKER] = datetime(2026, 9, 28, 10, 0, tzinfo=KST)

    await _sell_notice(env, "S1", 4, payload=10)
    await _await_sell_timer(env)

    assert TICKER not in env.engine._selling, f"{pair[0]} 결정적 거부인데 `_selling` 이 남았다(좀비)"
    assert TICKER not in env.engine._selling_since
    assert TICKER not in env.engine._selling_locked_wait
    lines = _warn_lines(caplog, "[reorder_selling_released]")
    assert len(lines) == 1 and "place=rejected" in lines[0] and f"reject={cls}" in lines[0], lines

    placed = AsyncMock(return_value=OrderResult(order_no="S2", order_time="100000",
                                                krx_org_no="00950"))
    monkeypatch.setattr(_oe, "place_order", placed)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert placed.await_count == 1 and placed.await_args.kwargs.get("quantity") == 6, (
        f"해제 뒤 다음 손절이 발사되지 않았다: {placed.await_args_list}"
    )


# ════════════════════════════════════════════════════════════════════════════
# TR4-3 — D2 재주문: 확정되지 않는 거부는 여전히 「전송 중」(유지)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [_kis(_EGW), _kis(_HOLDING_SHORT), _kis(_UNKNOWN), _kis(_QTY_CODE_OTHER_MSG),
     RuntimeError("KIS down")],
    ids=["EGW00201", "APBK0918-holding_short", "unknown_code", "APBK0400-other_msg", "runtime"],
)
async def test_r4_3_reorder_unproven_rejection_keeps_selling(monkeypatch, caplog, drain, exc):
    """🔴 TR4-3 (D2 · 재주문 유지) — TR4-2 와 같은 흐름에서 재주문이 `exc` 로 실패.

    기대: `_selling` **유지** · `[reorder_selling_released]` 0. EGW00201(초당 한도)·보유 부족 문구는
    **앞 시도의 접수가 만들 수 있는** 거부다(앞 시도가 걸리며 매도 가능 수량을 먹었다) — 풀면 N1 처럼
    다음 손절이 걸린 재주문 위에 또 나간다. 코드만 보고 풀면(「APBK 면 거부」) 이 행이 붉다.
    """
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    monkeypatch.setattr(_oe, "place_order", AsyncMock(side_effect=exc))
    _map_order(env, "S1", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S1", 4, payload=10)
    await _await_sell_timer(env)

    assert TICKER in env.engine._selling, f"{exc!r} 는 앞 시도 접수를 배제하지 못한다 — 유지"
    assert not _warn_lines(caplog, "[reorder_selling_released]")


# ════════════════════════════════════════════════════════════════════════════
# TR4-4 — D2 는 주인 규칙을 건너뛰지 않는다(손님 manual · 동결 아님)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("pair", [_CLOSED, _DISALLOWED_AFTER], ids=["closed", "disallowed"])
async def test_r4_4_guest_manual_deterministic_rejection_keeps_owner_selling(
    monkeypatch, caplog, drain, pair,
):
    """🔴 TR4-4 (D2 × 부록 R2-6 주인 · R3 K3) — 자동 손절이 `_selling` 의 주인(동결 표식 없음) ·
    손님 manual MAN-1 3(`_manual_sell_orders` False) → 1 체결(map) → 타이머 → 취소 성공 → 재주문이 결정적
    거부.

    기대: `_selling` **유지**(주인의 자동 손절이 따로 걸려 있다) · `[reorder_selling_released]` 0.
    D2 는 「무엇이 안 걸렸다」의 판정만 넓힌다 — 누구의 표식을 푸는지(주인 ∨ 동결)는 그대로다.
    """
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    monkeypatch.setattr(_oe, "place_order", AsyncMock(side_effect=_kis(pair)))
    _map_order(env, "S1", 7, "kojiro")                  # 주인 — 자동 손절이 걸려 있다
    env.engine._selling.add(TICKER)
    _map_order(env, "MAN-1", 3, "kojiro")
    env.engine._manual_sell_orders["MAN-1"] = False    # 손님

    await _sell_notice(env, "MAN-1", 1, payload=3)
    await _await_sell_timer(env)

    assert TICKER in env.engine._selling, "손님 manual 의 재주문 거부가 주인의 `_selling` 을 풀었다"
    assert not _warn_lines(caplog, "[reorder_selling_released]")


# ════════════════════════════════════════════════════════════════════════════
# TR4-5 — 해제 로그의 분류 칸: 재주문을 시도하지 않은 해제는 `reject=-`
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_r4_5_release_without_replace_logs_reject_dash(monkeypatch, caplog, drain):
    """🔴 TR4-5 (D2 마커) — 원주문 취소 뒤 재주문을 시도하지 않은 해제(`place=none`)는 분류 칸이
    `reject=-` 다(분류 변수를 `try` 앞에서 초기화한다 — 없으면 `finally` 가 `NameError` 로 무너진다)."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    _map_order(env, "S1", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await env.engine._cancel_and_reorder(TICKER, "S1", 0, is_stop_loss=False)

    lines = _warn_lines(caplog, "[reorder_selling_released]")
    assert len(lines) == 1 and "place=none" in lines[0] and "reject=-" in lines[0], lines
    assert TICKER not in env.engine._selling


# ════════════════════════════════════════════════════════════════════════════
# TR4-6 — D2 라우트의 결과: 결정적 거부 뒤 다음 손절이 거래소에 닿는가 (R4-2 이식)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc,stop_sent",
    [
        (_kis(_DISALLOWED_AFTER), [10]),
        (_kis(_CLOSED), [10]),
        (_kis(_QTY), [10]),
        (_kis(_EGW), []),
    ],
    ids=["APBK3013-after", "APBK0918-closed", "APBK0400", "EGW00201-kept"],
)
async def test_r4_6_manual_first_attempt_rejection_then_stop(monkeypatch, drain, exc, stop_sent):
    """🔴 TR4-6 (D2 · 라우트 · 적대 프로브 R4-2 이식) — 추적 10 · 계좌 10 · 걸린 것 없음. 운영자가 수동
    매도 5 → KIS 가 첫 시도에서 `exc` 로 거부(아무것도 안 걸림) → 이어서 손절.

    기대: APBK3013(애프터 시장가) · APBK0918(장운영시간 외) · APBK0400 = `_selling` 되돌림 → 손절 `[10]` 발사.
    EGW00201 = 「전송 중」 유지 → 손절이 `selling_reconcile` 까지 막힌다 — **D2 가 남기는 비용**(앞 시도
    접수를 배제할 수 없다 · 부록 R4 R4-4)이고 이 행이 그 동작을 고정한다.
    R3(APBK0400 만): APBK3013 에서도 손절 `[]`(애프터 시장가 버튼 한 번에 그 종목 손절이 멈췄다).
    """
    import src.api.order as _api_order
    import src.db.trade_history as _th
    import src.routes.trading as _tr
    from src.routes.trading import ManualSellRequest, manual_sell

    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    _install_acct_t(monkeypatch, env, acct, {})
    monkeypatch.setattr(_tr, "trading_scheduler",
                        SimpleNamespace(registry=env.registry, order_engine=env.engine))
    monkeypatch.setattr(_th, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_api_order, "place_order", AsyncMock(side_effect=exc))

    resp = await manual_sell(ManualSellRequest(ticker=TICKER, quantity=5))
    assert resp.success is False
    n0 = len(acct.placed)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed[n0:] == stop_sent, (
        f"수동 매도 {exc!r} 뒤 손절 발사 {acct.placed[n0:]} (기대 {stop_sent})"
    )
    await _fill_ours(env, acct)
    if stop_sent:
        assert _held(env, "kojiro") is None and acct.held == 0
        assert TICKER not in env.engine._selling
    else:
        assert TICKER in env.engine._selling and _held(env, "kojiro") == 10, (
            "EGW00201 는 「전송 중」 — 손절이 selling_reconcile 까지 막힌다(D2 가 남기는 비용)"
        )


# ════════════════════════════════════════════════════════════════════════════
# TR4-7 — D4: 조회 실패 · 걸린 것 없음 보류는 「미통보 체결」 을 주장하지 않는다 (seed 1177)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["error", "bad_row", "ok"])
async def test_r4_7_query_failure_hold_does_not_claim_unnoticed_fills(
    monkeypatch, caplog, drain, query,
):
    """🔴 TR4-7 (D4 · tester `c385r4/adv/test_r4_toctou.py` 이식) — 추적 10 · 운영자가 MTS-X 로 전략 몫
    4 를 팔았다(체결 · 통보 대기) · 계좌 6(초과분 0) · 걸린 것 없음. 손절 10 → APBK0400 → 잔고(보유 6 ·
    가능 6 < 추적 10) → 주문 조회 await **도중** MTS-X 통보 4 가 들어와 추적 6 → 조회는 `query`.

    - `error`/`bad_row`: `fills is None` · `eff = 추적 6 ≤ 보유 6` · 걸린 것 없음 → 보류(D1 — 동작 그대로).
      로그 = `[sell_qty_hold_orders_unavailable] … held=6 sellable=6 positions=6 orders=<이유>` 1행 ·
      `[sell_qty_unnoticed_fills]`·`[sell_qty_partial_locked]` 0 — 조회가 실패했으니 「거래소가 확인한
      미통보 체결」은 **모른다**. 다음 틱 손절은 6 을 판다(MTS-X 종료 통보가 `_selling` 을 이미 풀었다).
    - `ok`(대조): 원장이 MTS-X 4 를 이미 봤다 → pending 0 → F-3 가 6 발사 · 보류 문구 0.
    """
    import src.api.balance as bal

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(6)
    acct.fills["MTS-X"] = 4
    _install_acct_t(monkeypatch, env, acct, {})
    st = {"delivered": False}

    async def daily(*a, **k):
        if not st["delivered"]:
            st["delivered"] = True
            await _sell_notice(env, "MTS-X", 4, payload=4)   # 조회 await 도중 착지
        if query == "error":
            raise RuntimeError("TTTC0081R 5xx")
        rows = [_row_t(no, q, POST) for no, q in acct.fills.items()]
        if query == "bad_row":
            rows.append(_row_t("MTS-Z", "", POST))
        return rows

    monkeypatch.setattr(bal, "get_daily_orders", daily)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert st["delivered"]

    unnoticed = _warn_lines(caplog, "[sell_qty_unnoticed_fills]")
    locked = _warn_lines(caplog, "[sell_qty_partial_locked]")
    hold = _warn_lines(caplog, "[sell_qty_hold_orders_unavailable]")
    if query == "ok":
        assert acct.placed == [10, 6], acct.placed
        assert not unnoticed and not locked and not hold
    else:
        assert acct.placed == [10], acct.placed
        assert not unnoticed, (
            f"조회가 실패했는데 「거래소가 확인한 미통보 체결」 문구를 썼다: {unnoticed}"
        )
        assert not locked, "걸린 매도가 없는데 「외부 부분 매도주문 잠김」 문구를 썼다"
        assert len(hold) == 1 and f"orders={query}" in hold[0] and "held=6" in hold[0] \
            and "sellable=6" in hold[0] and "positions=6" in hold[0], hold
        assert TICKER in env.engine._selling_locked_wait, "보류(D1)가 동결 표식을 세우지 않았다"
        await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
        assert acct.placed == [10, 6], f"다음 틱 손절 {acct.placed} (기대 [10, 6])"
    await _fill_ours(env, acct)
    assert _held(env, "kojiro") is None and acct.held == 0


# ════════════════════════════════════════════════════════════════════════════
# TR4-8 — D5 · MX12: 원장 시작 전 주문의 크레딧은 `fills − seen` 을 상한과 min 한다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_r4_8_pre_ledger_credit_subtracts_seen_before_cap(monkeypatch, caplog, drain):
    """🔴 TR4-8 (D5 · MX12 킬러 · 부록 R3-1-5) — 추적 13(복원값 — 진짜 10 에 유령 3) · MTS-P(원장 시작
    **전** 접수, 재시작 전 체결 0) 6: 원장 시작 뒤 3 체결·통보 처리(seen 3 · 추적 10) → 2 더 체결(통보
    대기) · 잔량 1 · 계좌 5 · 초과분 0.

    기대: 재대조(보유 5)가 적는 P 크레딧 = `min(5 − 3, 상한 5)` = **2** · 발사 `[10, 5, 4]` ·
    P 통보 2 → 흡수 · 우리 4 체결 · P 1 체결·통보 → 매 단계 추적 ≥ 계좌 · 끝 `(None, 0)`.
    `- seen` 을 빼먹으면(MX12 — `min(fills, 상한)`) 크레딧 5 가 마지막 P 통보까지 삼켜 유령 1 이 남는다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 13})
    acct = _Acct(10)
    acct.rest_order("MTS-P", 6)
    _install_acct_t(monkeypatch, env, acct, {"MTS-P": PRE})
    acct.fill("MTS-P", 3)
    await _sell_notice(env, "MTS-P", 3, payload=6)
    assert _held(env, "kojiro") == 10
    acct.fill("MTS-P", 2)                                   # 통보 대기

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10, 5, 4], acct.placed
    assert env.engine._sell_reflected_credit == {"MTS-P": 2}, env.engine._sell_reflected_credit
    rec = _warn_lines(caplog, "[sell_qty_reconciled]")
    assert len(rec) == 1 and "pre_orders=1" in rec[0] and "pre_cap=5" in rec[0], rec
    trail = [(_held(env, "kojiro"), acct.held)]
    await _sell_notice(env, "MTS-P", 2, payload=6)
    trail.append((_held(env, "kojiro"), acct.held))
    await _fill_ours(env, acct)
    trail.append((_held(env, "kojiro"), acct.held))
    acct.fill("MTS-P", 1)
    await _sell_notice(env, "MTS-P", 1, payload=6)
    trail.append((_held(env, "kojiro"), acct.held))
    for tr, h in trail:
        assert (tr or 0) >= h, f"과소 추적 {trail}"
    assert trail[-1] == (None, 0), f"유령 {trail}"


# ════════════════════════════════════════════════════════════════════════════
# TR4-9 — D5 · MX3: 상한은 같은 재대조의 원장 시작 뒤 크레딧을 뺀다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_r4_9_pre_cap_subtracts_post_ledger_credit(monkeypatch, caplog, drain):
    """🔴 TR4-9 (D5 · MX3 킬러 · 부록 R3-1-5) — 추적 7(MTS-Y 재시작 전 체결 4 반영) · MTS-Y(원장 시작 **전**
    접수) 누적 6 = 재시작 전 4 + 뒤 2(통보 대기) · 잔량 3 · MTS-Q(원장 시작 **뒤** 접수) 1 체결(통보 대기) ·
    계좌 4 · 초과분 0.

    기대: 재대조(보유 4)의 뒤 주문 크레딧 Q = 1 · 상한 = 7 − 4 − **1** + 0 = 2 → Y 크레딧 2 ·
    `[sell_qty_reconciled]` 에 `pre_orders=1 pre_cap=2` · 발사 `[7, 4, 1]` · Y 2·Q 1 통보 흡수 · 우리 1 ·
    Y 3 체결·통보 → 매 단계 추적 ≥ 계좌 · 끝 `(None, 0)`.
    상한에서 뒤 주문 크레딧을 안 빼면(MX3) Y 크레딧 3 이 마지막 Y 통보 1 을 삼켜 유령 1 이 남는다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 7})
    acct = _Acct(7)
    acct.rest_order("MTS-Y", 5)
    acct.fills["MTS-Y"] = 4                                 # 재시작 전 체결(계좌·추적에 이미 반영)
    acct.fill("MTS-Y", 2)                                   # 재시작 뒤 · 통보 대기
    acct.rest_order("MTS-Q", 1)
    acct.fill("MTS-Q", 1)                                   # 원장 시작 뒤 접수 · 통보 대기
    _install_acct_t(monkeypatch, env, acct, {"MTS-Y": PRE, "MTS-Q": POST})

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [7, 4, 1], acct.placed
    assert env.engine._sell_reflected_credit == {"MTS-Y": 2, "MTS-Q": 1}, (
        env.engine._sell_reflected_credit
    )
    rec = _warn_lines(caplog, "[sell_qty_reconciled]")
    assert len(rec) == 1 and "pre_orders=1" in rec[0] and "pre_cap=2" in rec[0], rec
    trail = [(_held(env, "kojiro"), acct.held)]
    await _sell_notice(env, "MTS-Y", 2, payload=9)
    await _sell_notice(env, "MTS-Q", 1, payload=1)
    trail.append((_held(env, "kojiro"), acct.held))
    await _fill_ours(env, acct)
    trail.append((_held(env, "kojiro"), acct.held))
    acct.fill("MTS-Y", 3)
    await _sell_notice(env, "MTS-Y", 3, payload=9)
    trail.append((_held(env, "kojiro"), acct.held))
    for tr, h in trail:
        assert (tr or 0) >= h, f"과소 추적 {trail}"
    assert trail[-1] == (None, 0), f"유령 {trail}"


# ════════════════════════════════════════════════════════════════════════════
# TR4-10 — D5 · MX4: 남은 크레딧에는 종목 크레딧(조회 실패 재대조분)도 들어간다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_r4_10_old_credit_includes_blind_ticker_credit(monkeypatch, caplog, drain):
    """🔴 TR4-10 (D5 · MX4 킬러 · 부록 R3-1-5 「남은 크레딧」) — TK4b 의 첫 조회가 **실패**한 판.
    추적 10 · 계좌 10 · MTS-A(원장 시작 전 접수) 8 걸림 · A 3 체결(통보 대기) · 첫 재대조는 조회 실패 →
    종목 크레딧 3 · 두 번째 발사 직전 A 2 더 체결(통보 대기) · 두 번째 재대조는 조회 성공.

    기대: 두 번째 상한 = 7 − 5 − 0 + **종목 크레딧 3** = 5 → A 크레딧 5 · 종목 크레딧 비움 ·
    A 통보 3·2 뒤 추적 == 계좌 == 5.
    남은 크레딧에서 종목 크레딧을 빼먹으면(MX4) 상한 2 → A 통보 3 중 1·2 가 두 번 빠진다 = **과소 추적**
    (R-INV-1 위반 — 추적 2 < 계좌 5).
    """
    import src.api.balance as bal

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-A", 8)
    acct.fill("MTS-A", 3)

    def before(n):
        if n == 2:
            acct.fill("MTS-A", 2)

    _install_acct_t(monkeypatch, env, acct, {"MTS-A": PRE}, before_place=before)
    ok_rows = bal.get_daily_orders
    n_query = {"n": 0}

    async def first_fails(*a, **k):
        n_query["n"] += 1
        if n_query["n"] == 1:
            raise RuntimeError("TTTC0081R down")
        return await ok_rows(*a, **k)

    monkeypatch.setattr(bal, "get_daily_orders", first_fails)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _warn_lines(caplog, "[sell_qty_reconcile_orders_unavailable]"), "첫 재대조가 조회 실패 경로가 아니다"
    assert env.engine._sell_reflected_credit.get("MTS-A") == 5, env.engine._sell_reflected_credit
    assert TICKER not in env.engine._sell_blind_credit
    await _sell_notice(env, "MTS-A", 3, payload=8)
    await _sell_notice(env, "MTS-A", 2, payload=8)
    assert _held(env, "kojiro") == acct.held == 5, (_held(env, "kojiro"), acct.held)


# ════════════════════════════════════════════════════════════════════════════
# TR4-11 — R5 T4: 재주문의 원주문 취소가 실패하면 원주문 잔량이 걸려 있다 → `_selling` 유지
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cancel_exc",
    [
        _kis(_UNKNOWN),
        httpx.ReadTimeout(
            "read timeout",
            request=httpx.Request("POST", "https://openapi.koreainvestment.com:9443/uapi/x"),
        ),
    ],
    ids=["kis_reject", "transport"],
)
async def test_r4_11_reorder_cancel_failure_keeps_selling_and_blocks_next_stop(
    monkeypatch, caplog, drain, cancel_exc,
):
    """🔴 TR4-11 (R5 T4 킬러 · tester `c385r5/adv/test_t4_cancel_fail.py` 이식) — 계좌 13(전략 10 +
    운영자 3) · 추적 10 · 손절 OUR-1 10 발사 → 4 체결(map 통보) → 30초 타이머 → 원주문 취소가
    `cancel_exc` 로 **실패**.

    기대: 원주문 잔량 6 이 거래소에 그대로 걸려 있다 → `_selling` **유지** · `[reorder_selling_released]` 0 ·
    재주문 발사 0 · 이어진 손절 틱은 진입 게이트에서 막혀 발사 0(걸린 잔량 위에 쌓지 않는다) ·
    걸린 잔량 6 이 체결되면 추적이 닫히고 운영자 몫 3 은 남는다.
    해제 조건에서 `_cancel_ok` 를 지우면(T4) 취소 실패 뒤 `place=none` 해제가 일어나 다음 손절이 걸린 잔량
    위로 또 나간다 — AST AR2-3 만 잡던 변이를 행위로 잡는다.
    """
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(13)
    _install_acct_t(monkeypatch, env, acct, {})
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    cancel = AsyncMock(side_effect=cancel_exc)
    monkeypatch.setattr(_oe, "cancel_order", cancel)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")        # OUR-1 10
    assert acct.placed == [10] and TICKER in env.engine._selling
    acct.fill("OUR-1", 4)
    await _sell_notice(env, "OUR-1", 4, payload=10)                          # 타이머 → 취소 실패
    await _await_sell_timer(env)

    assert cancel.await_count == 1, "재주문 타이머가 원주문 취소를 시도하지 않았다"
    assert acct.rest == {"OUR-1": 6}, f"원주문 잔량이 걸려 있어야 한다: {acct.rest}"
    assert acct.placed == [10], f"취소가 실패했는데 재주문이 나갔다: {acct.placed}"
    assert TICKER in env.engine._selling, "원주문 잔량이 걸려 있는데 `_selling` 을 풀었다(T4)"
    assert not _warn_lines(caplog, "[reorder_selling_released]")
    assert _held(env, "kojiro") == 6

    n0 = len(acct.placed)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert acct.placed[n0:] == [], (
        f"걸린 잔량 6 위에 다음 손절이 또 나갔다: {acct.placed[n0:]}"
    )

    await _fill_ours(env, acct)                                               # 걸린 잔량 6 체결
    assert _held(env, "kojiro") is None and acct.held == 3, (_held(env, "kojiro"), acct.held)
    assert TICKER not in env.engine._selling
