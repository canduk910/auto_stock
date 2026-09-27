"""cycle385 부록 R3 — 3차 검토(K1~K4) 반영 (TK1~TK13).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R3 (R3-1 ~ R3-4 · R3-7)
사용자 전제(2026-09-26) = R-INV-1 **과소 추적 금지** · R-INV-2 **운영자 몫을 팔지 않는다**.

## 부록 R3 가 바꾸는 것 (요지)

- **K1** — 재시작(또는 21:30 정산 리셋)으로 `_sell_notice_seen` 이 비면, 그 전에 접수된 주문의
  체결(복원 수량에 이미 들어간 것)까지 pending 에 세어 eff 가 작아지고 F-3 가 발사 0 으로 얼었다
  (N3 · N3b). → 원장 시작 시각 `_sell_ledger_since` 을 두고, TTTC0081R `ord_dt`+`ord_tmd` 가 그보다
  **앞**인 주문은 pending 에서 뺀다(부팅은 복원 수량을 KIS 에 맞추지 않는다 — R3-1-1, 그래서
  「다 봤다」 시드는 틀린 전제). 그 주문의 재대조 크레딧은 **상한**(재대조 폭 + 남은 크레딧 − 뒤 주문
  크레딧, R3-1-5). 걸린 매도 없이 보류할 때의 문구는 `[sell_qty_unnoticed_fills]`(R3-1-6).
- **K2** — 재주문 `KisApiError` 중 **APBK0400 만** 「안 걸렸다」(`_request` 는 주문 POST 도 전송 실패·
  5xx 에 재시도하므로 그 밖의 코드는 앞 시도가 접수됐을 수 있다).
- **K3** — 동결 표식이 서 있으면 손님 manual 의 재주문 거부도 `_selling` 을 푼다.
- **K4** — pending 의 `max(0, …)` 는 **주문별**(합 뒤 clamp 면 표 지연 주문의 음수가 다른 주문의
  대기분을 지운다).

## 하네스

`_Acct`(계좌 모형)·`_env`·`_reorder_env`·`_await_sell_timer`·`_apbk0400`·`drain` = 부록 R2 파일,
`_sell_notice`·`_map_order`·`_held`·`_warn_lines` = B7 파일. `_install_acct_t` 는 R2 `_install_acct`
와 같고 TTTC0081R 행에 `ord_dt`/`ord_tmd` 를 싣는다.

🔴 **벽시계 금지** — 원장 시작(`SINCE`)·행 시각(`PRE`·`POST`)은 전부 상수로 고정한다(메모리
   `feedback_wall_clock_gate_breaks_ci`). 판정은 「기록된 두 시각」의 비교다.
🔴 caplog 단언은 WARNING 이상 + prefix(CI 루트 로거 DEBUG — cycle252 T2).
🔴 새 심볼(`_sell_orders_placed_before` 등)은 함수 안에서 import 한다 — 구현 전 수집 에러로 파일
   전체가 뭉개지면 어느 행위가 붉은지 가려지지 않는다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    _apbk0400,
    _await_sell_timer,
    _env,
    _reorder_env,
    drain,
)

pytestmark = pytest.mark.unit

_OE_LOGGER = "src.engine.order_engine"
KST = timezone(timedelta(hours=9))
SINCE = datetime(2026, 9, 28, 12, 0, 0, tzinfo=KST)   # 원장 시작(고정)
PRE, POST = "100000", "123000"                          # 원장 시작 앞 · 뒤 접수 시각


def _row_t(odno, qty, tmd, *, pdno=TICKER, dvsn="01", dt="20260928"):
    """TTTC0081R 행. `tmd` 가 None 이면 `ord_dt`·`ord_tmd` 두 키를 싣지 않는다."""
    r = {"odno": odno, "pdno": pdno, "sll_buy_dvsn_cd": dvsn, "tot_ccld_qty": str(qty)}
    if tmd is not None:
        r["ord_dt"] = dt
        r["ord_tmd"] = tmd
    return r


def _install_acct_t(monkeypatch, env, acct, times, *, before_place=None, missing=False):
    """R2 `_install_acct` 와 같고 행에 접수 시각(`times[odno]`, 기본 POST)을 싣는다.

    `missing` 이면 시각 키를 빼고 싣는다. 원장 시작 = `SINCE` 로 **고정 대입**한다.
    """
    import src.api.balance as bal
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    async def place_order(ticker, side, quantity, price=0, **kw):
        acct.placed.append(quantity)
        if before_place is not None:
            before_place(len(acct.placed))
        if quantity > acct.sellable():
            raise _apbk0400()
        acct.n += 1
        no = f"OUR-{acct.n}"
        acct.rest_order(no, quantity)
        return OrderResult(order_no=no, order_time="123001", krx_org_no="00950")

    async def get_balance(*a, **k):
        h = SimpleNamespace(ticker=TICKER, quantity=acct.held, sellable_quantity=acct.sellable())
        return [h], SimpleNamespace(net_asset=0)

    async def get_daily_orders(*a, **k):
        return [_row_t(no, q, None if missing else times.get(no, POST))
                for no, q in acct.fills.items()]

    monkeypatch.setattr(_oe, "place_order", place_order)
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)
    env.engine._sell_ledger_since = SINCE


async def _fill_ours(env, acct):
    """걸린 우리 주문(OUR-*)을 전량 체결시키고 통보를 넣는다(map)."""
    for no, q in list(acct.rest.items()):
        if no.startswith("OUR-"):
            acct.fill(no, q)
            await _sell_notice(env, no, q, payload=q)


# ════════════════════════════════════════════════════════════════════════════
# TK1 — K1 · N3/N3b 이식: 원장 시작 전 체결은 pending 에 넣지 않는다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("tracked,case", [(5, "N3"), (7, "N3b")], ids=["N3", "N3b"])
async def test_tk1_pre_ledger_fills_do_not_freeze_the_stop(monkeypatch, caplog, drain, tracked, case):
    """🔴 TK1 (K1 · N3 / N3b) — 새 원장(`_sell_notice_seen` 빔) · 추적 5(N3) / 7(N3b — DB 7 · 메모리 4
    였던 `save_position` 실패의 복원판) · 계좌 4 · MTS-X 가 원장 시작 **전**(10:00)에 6 체결 · 걸린 것 없음.

    기대: 발사 `[추적, 4]` — 첫 발사 APBK0400 → pending 0(원장 시작 전 주문 제외) → eff = 추적 >
    보유 4 → 재대조 → 4 발사 · `[sell_qty_reconciled]` 1 · 「잠김」·`[sell_qty_unnoticed_fills]` 0 ·
    우리 체결 뒤 닫힘 · `_selling` 비움.

    R2: pending 이 재시작 전 체결 6 을 세어 eff ≤ 0 → F-3 발사 0 으로 그날 내내 동결(N3 발사
    `[5, 5, 5, 5]` 매도 0 · N3b 매도 1 뒤 동결 — B7·HEAD 는 다 판다).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": tracked})
    acct = _Acct(4)
    acct.fills["MTS-X"] = 6
    _install_acct_t(monkeypatch, env, acct, {"MTS-X": PRE})

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [tracked, 4], (
        f"{case} 발사 {acct.placed} (기대 [{tracked}, 4]) — 원장 시작 전 체결을 pending 에 세어 얼었다"
    )
    assert len(_warn_lines(caplog, "[sell_qty_reconciled]")) == 1
    assert not _warn_lines(caplog, "[sell_qty_partial_locked]")
    assert not _warn_lines(caplog, "[sell_qty_unnoticed_fills]")
    await _fill_ours(env, acct)
    assert _held(env, "kojiro") is None and acct.held == 0
    assert TICKER not in env.engine._selling


# ════════════════════════════════════════════════════════════════════════════
# TK3 — 걸린 것 없는 보류(N3c): 원장 시작 뒤 주문의 미통보 체결이 추적 전부를 덮는다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["post", "missing"])
async def test_tk3_post_ledger_unnoticed_cover_holds_without_selling_operator(
    monkeypatch, caplog, drain, when,
):
    """🔴 TK3 (R3-1-6 · N3c) — 추적 5 · 계좌 4(= 운영자 몫) · MTS-X 가 원장 시작 **뒤**(또는 접수 시각을
    못 읽음 = 뒤로 읽는다) 5 체결, 통보 대기 · 걸린 것 없음.

    기대: 발사 `[5]` 뿐 · `[sell_qty_unnoticed_fills]` 1행(`pending=5`·`eff=0`) · 「외부 부분
    매도주문 잠김」(`[sell_qty_partial_locked]`) 0 — 걸린 매도가 없다(held == sellable) ·
    `_selling`·동결 표식 섬 → MTS-X 통보 5 → 닫힘 · 둘 다 비움 · 계좌 4 보존.

    B7: 발사 `[5, 4]` — 운영자 4주 매도. 못 읽는 시각을 「앞」으로 읽으면(MK3) 같은 결과.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 5})
    acct = _Acct(4)
    acct.fills["MTS-X"] = 5
    _install_acct_t(monkeypatch, env, acct, {"MTS-X": POST}, missing=(when == "missing"))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [5], f"발사 {acct.placed} (기대 [5]) — 운영자 몫을 쐈다"
    hold = _warn_lines(caplog, "[sell_qty_unnoticed_fills]")
    assert len(hold) == 1 and "pending=5" in hold[0] and "eff=0" in hold[0], hold
    assert not _warn_lines(caplog, "[sell_qty_partial_locked]"), (
        "걸린 매도가 없는데(held == sellable) 「외부 부분 매도주문 잠김」 문구가 떴다"
    )
    assert TICKER in env.engine._selling and TICKER in env.engine._selling_locked_wait
    await _sell_notice(env, "MTS-X", 5, payload=5)
    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._selling and TICKER not in env.engine._selling_locked_wait
    assert acct.held == 4, f"운영자 몫 {acct.held} (기대 4)"


# ════════════════════════════════════════════════════════════════════════════
# TK4 — 원장 시작 전 주문이 아직 체결 중(N3d): 재대조 크레딧 상한
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tk4_pre_ledger_credit_is_capped_by_the_recount_drop(monkeypatch, caplog, drain):
    """🔴 TK4 (R3-1-5 · N3d) — 추적 6 · 계좌 4 · MTS-Y(원장 시작 전 접수) 누적 6 = 재시작 전 4(추적에
    이미 반영, 통보 다시 안 옴) + 뒤 2(통보 대기) · 잔량 3 걸림.

    기대: 재대조 크레딧 `{"MTS-Y": 2}`(상한 = 추적 6 − 목표 4 − 뒤 주문 0 + 남은 0) ·
    `[sell_qty_reconciled]` 에 `pre_orders=1 pre_cap=2` · Y 통보 2 · 우리 체결 · Y 3 체결·통보 —
    매 단계 추적 ≥ 계좌 · 끝 `(0, 0)`.

    상한이 없으면(MK6·MK20) 크레딧 6 이 뒤 통보 3 까지 삼켜 끝에 유령 보유가 남는다(부록 R2-11 ②).
    크레딧을 아예 안 주면(MK18) 뒤 2 가 두 번 빠진다(과소 추적).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 6})
    acct = _Acct(4)
    acct.fills["MTS-Y"] = 6
    acct.rest["MTS-Y"] = 3
    _install_acct_t(monkeypatch, env, acct, {"MTS-Y": PRE})

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert env.engine._sell_reflected_credit == {"MTS-Y": 2}, env.engine._sell_reflected_credit
    rec = _warn_lines(caplog, "[sell_qty_reconciled]")
    assert len(rec) == 1 and "pre_orders=1" in rec[0] and "pre_cap=2" in rec[0], rec
    trail = [(_held(env, "kojiro"), acct.held)]
    await _sell_notice(env, "MTS-Y", 2, payload=12)
    trail.append((_held(env, "kojiro"), acct.held))
    await _fill_ours(env, acct)
    trail.append((_held(env, "kojiro") or 0, acct.held))
    acct.fill("MTS-Y", 3)
    await _sell_notice(env, "MTS-Y", 3, payload=12)
    trail.append((_held(env, "kojiro") or 0, acct.held))
    for tr, h in trail:
        assert (tr or 0) >= h, f"과소 추적 {trail}"
    assert trail[-1] == (0, 0), f"유령 {trail}"


# ════════════════════════════════════════════════════════════════════════════
# TK4b — 한 execute_sell 안 두 번째 재대조: 남은 크레딧을 상한에 더한다(seed 5222)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tk4b_second_recount_adds_back_outstanding_credit(monkeypatch, drain):
    """🔴 TK4b (R3-1-5 「남은 크레딧을 더하는 이유」) — 추적 10 · 계좌 10 · MTS-A(원장 시작 전 접수) 8
    걸림 · A 3 체결(통보 대기) · 두 번째 발사 직전 A 2 더 체결(통보 대기).

    기대: 크레딧 A == 5 · A 통보 3·2 뒤 추적 == 계좌 == 5.
    남은 크레딧(첫 재대조 3)을 상한에서 빼먹으면(MK7·MK21) 두 번째 상한이 2 로 작아져 뒤 통보 중 1 이
    두 번 빠진다(시제품 첫 판: 정산점 추적 2 < 계좌 5).
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-A", 8)
    acct.fill("MTS-A", 3)

    def before(n):
        if n == 2:
            acct.fill("MTS-A", 2)

    _install_acct_t(monkeypatch, env, acct, {"MTS-A": PRE}, before_place=before)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert env.engine._sell_reflected_credit.get("MTS-A") == 5, env.engine._sell_reflected_credit
    await _sell_notice(env, "MTS-A", 3, payload=8)
    await _sell_notice(env, "MTS-A", 2, payload=8)
    assert _held(env, "kojiro") == acct.held == 5, (_held(env, "kojiro"), acct.held)


# ════════════════════════════════════════════════════════════════════════════
# TK5 — 분류 파서 `_sell_orders_placed_before`
# ════════════════════════════════════════════════════════════════════════════
def test_tk5_placed_before_parser():
    """🔴 TK5 (R3-1-3) — 이 종목 매도 주문 중 원장 시작 **전**에 접수된 것(정규화 주문번호).

    앞 = 넣는다 · 뒤·같은 시각(`<` 엄격) = 안 넣는다 · 시각 없음·못 읽음 = 안 넣는다(뒤로 읽는다) ·
    SOR 여러 행 = **가장 늦은** 시각 · 한 행이라도 못 읽으면 안 넣는다 · 다른 종목·매수 = 무시 ·
    전날 = 앞 · 8자리 아닌 날짜 = 못 읽음. `rows=None`·`since=None` → 빈 집합(never-raise).
    """
    from src.engine.order_engine import _sell_orders_placed_before as pb

    rows = [
        _row_t("0000000001", 1, PRE),                                  # 앞
        _row_t("0000000002", 1, POST),                                 # 뒤
        _row_t("0000000003", 1, "120000"),                             # 같은 시각 = 앞 아님
        _row_t("0000000004", 1, None),                                 # 시각 없음 = 앞 아님
        _row_t("0000000005", 1, "99x000"),                             # 못 읽음
        _row_t("0000000006", 1, PRE), _row_t("0000000006", 1, POST),   # SOR — 가장 늦은 값(뒤)
        _row_t("0000000007", 1, PRE), _row_t("0000000007", 1, "110000"),  # SOR — 앞 + 앞
        _row_t("0000000008", 1, PRE, pdno="000660"),                   # 다른 종목
        _row_t("0000000009", 1, PRE, dvsn="02"),                       # 매수
        _row_t("0000000010", 1, PRE, dt="20260927"),                   # 전날(가정 밖이지만 앞)
        _row_t("0000000011", 1, None) | {"ord_dt": "2026092", "ord_tmd": PRE},  # 7자리 날짜
        _row_t("0000000012", 1, PRE), _row_t("0000000012", 1, None),   # 하나라도 못 읽으면 앞 아님
    ]
    assert pb(rows, TICKER, SINCE) == frozenset({"1", "7", "10"})
    assert pb(None, TICKER, SINCE) == frozenset()
    assert pb([{"odno": "1"}], TICKER, None) == frozenset()


# ════════════════════════════════════════════════════════════════════════════
# TK6 · TK7 — K4: pending 은 원장 시작 전 주문을 빼고, `max(0, …)` 는 주문별
# ════════════════════════════════════════════════════════════════════════════
def test_tk6_pending_excludes_pre_and_clamps_per_order(monkeypatch, drain):
    """🔴 TK6 (R3-4 단위 · K1 · K4) — seen `{"1": 5}` · fills `{"1": 3, "2": 4, "3": 6}`.

    `pre={"3"}` → **4**(1 은 표 지연 −2 → 0 · 2 는 4 · 3 은 제외). 합 뒤 clamp 면 2(XF3c · MK16).
    `pre=∅` → **10**. pre 를 거르지 않으면(MK1) 첫 값이 10.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    eng = env.engine
    eng._sell_notice_seen.update({"1": 5})
    fills = {"1": 3, "2": 4, "3": 6}
    assert eng._sell_pending_dec(fills, frozenset({"3"})) == 4
    assert eng._sell_pending_dec(fills, frozenset()) == 10


@pytest.mark.asyncio
async def test_tk7_lagging_row_does_not_cancel_other_orders_pending(monkeypatch, drain):
    """🔴 TK7 (R3-4 행위 · XF3c 킬러) — 추적 5 · 계좌 5 · MTS-A 표 3(통보는 5 를 이미 처리 — 표 지연) ·
    MTS-B 4 체결(통보 대기) · MTS-C 2 걸림 → 참 전략 몫 1(= 5 − 4), 그 1 도 C 에 잠김.

    기대: 발사 `[5]` 뿐. 합 뒤 clamp 면 pending 2 → eff 3 → fire 1 → 운영자 1주 매도.
    """
    env = _env(monkeypatch, drain, {"kojiro": 5})
    acct = _Acct(5)
    acct.fills["MTS-A"] = 3
    env.engine._sell_notice_seen["MTS-A"] = 5
    acct.fills["MTS-B"] = 4
    acct.rest_order("MTS-C", 2)
    _install_acct_t(monkeypatch, env, acct, {})

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [5], f"발사 {acct.placed} — 표 지연이 B 의 대기분을 지워 운영자 몫을 쐈다"


# ════════════════════════════════════════════════════════════════════════════
# TK8 — 원장 시작 시각은 엔진 생성·일일 리셋에서 선다
# ════════════════════════════════════════════════════════════════════════════
def test_tk8_ledger_since_set_at_init_and_reset(monkeypatch, drain):
    """🔴 TK8 (R3-1-2) — 새 엔진의 `_sell_ledger_since` 는 tz-aware(+09:00). `reset_daily_state()`
    뒤에는 새 값(+09:00)이다 — 리셋이 원장을 비우면서 시각을 두면(MK5) 다음 날 모든 주문이 「뒤」로
    읽혀 전날 주문 체결까지 pending 에 센다."""
    env = _env(monkeypatch, drain, {"kojiro": 1})
    eng = env.engine
    assert eng._sell_ledger_since.tzinfo is not None
    assert eng._sell_ledger_since.utcoffset() == timedelta(hours=9)
    eng._sell_ledger_since = SINCE
    eng.reset_daily_state()
    assert eng._sell_ledger_since != SINCE
    assert eng._sell_ledger_since.utcoffset() == timedelta(hours=9)


# ════════════════════════════════════════════════════════════════════════════
# TK9 — K2: 재주문 거부는 APBK0400 만 「안 걸렸다」
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["EGW00201", "APBK0918", "APBK3013"])
async def test_tk9_reorder_non_quantity_rejection_keeps_selling(monkeypatch, caplog, drain, code):
    """🔴 TK9 (R3-2 · K2) — 자동 S1 10(매핑, `_selling`) · 통보 4 → 30초 타이머 → 원주문 취소 성공 →
    재주문이 `code` 로 거부.

    기대: `_selling` **유지** · `[reorder_selling_released]` 0. `_request` 는 주문 POST 도 전송 실패·
    5xx 에 재시도하므로 APBK0400 밖의 거부는 앞 시도의 접수를 배제하지 못한다.

    부록 R4 D2 뒤: 판정은 msg1 문구 기반(`_sell_not_placed_reason`)이다 — 이 표의 msg1 「거부」 는 시장가
    불가·장운영시간 분류기에 걸리지 않으므로 세 코드 모두 여전히 유지다. 실제 문구의 APBK0918(장운영시간
    외)·APBK3013(시장가 불가)는 「안 걸렸다」로 풀린다 — `test_cycle385r4_round4.py` TR4-2.
    """
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    monkeypatch.setattr(_oe, "place_order",
                        AsyncMock(side_effect=KisApiError(rt_cd="1", msg_cd=code, msg1="거부")))
    _map_order(env, "S1", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S1", 4, payload=10)
    await _await_sell_timer(env)

    assert TICKER in env.engine._selling, f"{code} 는 앞 시도 접수를 배제하지 못한다 — 유지"
    assert not _warn_lines(caplog, "[reorder_selling_released]")


# ════════════════════════════════════════════════════════════════════════════
# TK10 — K2 · N1 이식: 재주문 앞 시도 접수(응답 유실) + 뒤 시도 거부
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second,acct_qty", [("EGW00201", 20), ("physical", 13)], ids=["EGW00201-20", "physical-13"],
)
async def test_tk10_hidden_accepted_reorder_is_not_stacked(monkeypatch, drain, second, acct_qty):
    """🔴 TK10 (R3-2-3 · N1) — 계좌 20 / 13 · 추적 10 · 우리 10 → 4 체결 → 타이머 → 재주문 시도 1 접수
    (응답 유실) + 시도 2 = EGW00201 / 계좌가 판정(여기선 APBK0400).

    EGW: `_selling` **유지** → 다음 손절 중복 차단 → 끝 계좌 10(운영자 몫 보존).
    physical: APBK0400 = 거부 확정 → 해제 → 이어진 손절은 걸린 재주문을 빼고 계산 → 끝 계좌 3.
    둘 다 추적 닫힘. 모든 `KisApiError` 를 「안 걸렸다」로 읽으면(MK10) EGW 변형이 운영자 6주를 판다.
    """
    import src.engine.order_engine as _oe

    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(acct_qty)
    _install_acct_t(monkeypatch, env, acct, {})
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)

    async def cancel_order(order_no, qty, cancel_all=True, exchange=None, **kw):
        acct.rest.pop(order_no, None)

    monkeypatch.setattr(_oe, "cancel_order", cancel_order)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")        # OUR-1 10
    acct.fill("OUR-1", 4)
    orig = _oe.place_order

    async def hidden(*a, **k):
        await orig(*a, **k)                                                   # 시도 1 접수(응답 유실)
        if second == "physical":
            return await orig(*a, **k)                                        # 시도 2 — 계좌가 판정
        raise KisApiError(rt_cd="1", msg_cd="EGW00201", msg1="초당 거래건수를 초과하였습니다.")

    monkeypatch.setattr(_oe, "place_order", hidden)
    await _sell_notice(env, "OUR-1", 4, payload=10)
    await _await_sell_timer(env)
    monkeypatch.setattr(_oe, "place_order", orig)
    if second == "EGW00201":
        assert TICKER in env.engine._selling, "앞 시도 접수를 배제할 수 없는데 `_selling` 을 풀었다"
    else:
        assert TICKER not in env.engine._selling, "APBK0400 = 거부 확정인데 `_selling` 이 남았다"

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    for _ in range(3):
        for no, q in list(acct.rest.items()):
            acct.fill(no, q)
            await _sell_notice(env, no, q, payload=q)
        env.engine._selling.discard(TICKER)
        await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.held == acct_qty - 10, f"운영자 몫 {acct.held} (기대 {acct_qty - 10})"
    assert _held(env, "kojiro") is None


# ════════════════════════════════════════════════════════════════════════════
# TK12 — K3 (h4h5 이식): 동결 + 손님 manual 재주문 거부 → 우리 것이 없으면 푼다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tk12_freeze_with_guest_manual_reject_releases(monkeypatch, caplog, drain):
    """🔴 TK12 (R3-3 · K3) — 계좌 10 · MTS-9 10 걸림 → 손절 `[sell_qty_locked]` 동결 → 운영자가 앱에서
    MTS-9 취소(통보 없음) → 손님 MAN-1 3(`_manual_sell_orders` False) → 1 체결 → 타이머 → 취소 →
    재주문 APBK0400.

    기대: 걸린 것 없음 · `_selling`·동결 표식 비움 · `[reorder_selling_released] place=rejected` 1.
    R2(주인만): 손님이라 안 풀어 `selling_reconcile`(09:30 전에는 안 돈다)까지 손절이 멈춘다.
    """
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-9", 10)
    _install_acct_t(monkeypatch, env, acct, {})
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")        # [sell_qty_locked]
    assert TICKER in env.engine._selling_locked_wait
    acct.rest.pop("MTS-9")                                                    # 앱에서 취소(통보 없음)
    acct.rest_order("MAN-1", 3)
    _map_order(env, "MAN-1", 3, "kojiro")
    env.engine._manual_sell_orders["MAN-1"] = False                          # 손님
    acct.fill("MAN-1", 1)

    async def cancel(order_no, *a, **k):
        acct.rest.pop(order_no, None)

    monkeypatch.setattr(_oe, "cancel_order", cancel)
    monkeypatch.setattr(_oe, "place_order", AsyncMock(side_effect=_apbk0400()))
    await _sell_notice(env, "MAN-1", 1, payload=3)
    await _await_sell_timer(env)

    assert not acct.rest, f"걸린 주문 {acct.rest}"
    assert TICKER not in env.engine._selling and TICKER not in env.engine._selling_locked_wait, (
        "우리 것이 하나도 걸려 있지 않은데 `_selling` 이 남았다(좀비)"
    )
    lines = _warn_lines(caplog, "[reorder_selling_released]")
    assert len(lines) == 1 and "place=rejected" in lines[0], lines


# ════════════════════════════════════════════════════════════════════════════
# TK13 — N2 이식: 조회 실패 + 진짜 유령(통보 유실) = 문서화된 한계(R-13-4)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.xfail(strict=True, reason="부록 R-13-4 · R3 유지 — 종목 크레딧이 유실 통보를 싣는다(N2)")
@pytest.mark.asyncio
async def test_tk13_blind_credit_true_phantom_is_documented_limit(monkeypatch, drain):
    """🟡 TK13 (N2 — 부록 R-13-4 문서화된 한계, 아래는 한계가 풀렸을 때의 기대) — 추적 12 · 계좌 10 ·
    주문 조회 늘 실패 · 전량 매도 뒤 운영자가 5 매수 → 손절.

    기대(한계가 풀리면): 전량 매도 뒤 유령 없음 · 운영자가 뒤에 산 5 보존. 지금은 종목 크레딧이 유실
    통보 몫을 실어 유령 보유가 남고 그 유령이 운영자 몫을 판다 — XPASS 로 뒤집히면 한계가 풀린 것.
    """
    import src.api.balance as bal

    env = _env(monkeypatch, drain, {"kojiro": 12})
    acct = _Acct(10)
    _install_acct_t(monkeypatch, env, acct, {})
    monkeypatch.setattr(bal, "get_daily_orders", AsyncMock(side_effect=RuntimeError("down")))
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    await _fill_ours(env, acct)
    residual = _held(env, "kojiro")
    acct.held += 5                                   # 운영자가 5 를 따로 산다(추적 밖)
    env.engine._selling.discard(TICKER)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    await _fill_ours(env, acct)
    assert residual is None, f"전량 매도 뒤 유령 {residual}"
    assert acct.held == 5, f"운영자가 뒤에 산 몫 {acct.held} (기대 5)"
