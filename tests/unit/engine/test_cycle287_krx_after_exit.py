"""cycle287 Red — 규칙 2: KRX 애프터마켓(16:00~20:00) 청산 수단 `ORD_DVSN=44`.

정본 = cycle287 도메인 자문 §3·§4·§9-C·§9-D (2026-09-12, 사용자 결정 2026-09-12).
접촉 허용 프로덕션 파일 = `src/models/order.py` · `src/engine/order_engine.py` ·
`src/api/order.py` **셋뿐**.

## 왜 이 사이클인가 — 없던 능력을 여는 것이 아니다

오늘 16:xx 시장가 매도는 APBK3013 로 거부되고, 기존 `is_market_order_disallowed`
지정가 5호가 폴백이 SOR 로 재발사해 **NXT N6 에서 체결된다**(30일 7/7 · SELL 3건 실측:
08-18 17:06 kojiro · 09-01 18:09 donchian · 09-08 15:45 momentum).

규칙 1 을 넣으면 그 창의 거래소가 KRX 가 되고 KRX 애프터는 `01`(시장가)도 `00`(지정가
폴백)도 받지 않는다 ⇒ **규칙 1 단독 배포는 오늘보다 나쁘다.** 두 규칙은 분리 배포가
불가하고, 이 파일이 그 짝의 나머지 반쪽을 잰다.

## Green 계약 (자문 §9-A/§9-C/§9-D)

* `OrderDivision` 에 **`KRX_AFTER_LIMIT="41"` · `KRX_AFTER_BEST="44"` 둘만** 추가.
  42/43/45/46(IOC/FOK)은 잔량 자동취소라 손절 잔여를 잃고, 47(최우선지정가)은 자기
  방향 최우선호가라 **크로스하지 않는다** = 손절 수단이 아니다(자문 §3-A).
* `execute_sell` 에서 매도 프리장 사전 변환 **뒤** · 재시도 루프 **앞**:
  `order_division == MARKET ∧ target_exchange == "KRX" ∧ KRX phase is AFTER_MARKET
  ∧ settings.is_production` → dial(`{"44","41"}`, 기본 `44`)대로 변환.
  `44` → `ORD_UNPR = 0` (자문 §4-A: 정본 필드표 "시장가 등 주문시 \"0\"으로 입력" 이
  유일하게 명시된 값이고, 틀렸을 때 **즉시 거부 = 관측 가능**이다. 현재가를 넣었다가
  지정가로 오인 접수되면 **미체결 잔존 = 손절 무음 실패**로 훨씬 나쁘다).
  `41` → `ORD_UNPR = step_down(현재가, 5)`.
* 폭주 봉인(§9-D)이 **GO 의 조건**이다 — 44 가 거부되면 기존 폴백 게이트
  (`order_division == MARKET`)가 거짓이 되어 ① 지정가 폴백 ② 30초 TTL
  ③ `_pending_next_day_clear` 전환이 **동시에** 죽는다. TTL 이 없으면 `on_tick` 이
  매 틱 재발사해 16:00~20:00 에 수만 요청 + CRITICAL 수천 행이 된다.
* **애프터 폴백은 분류에 의존하지 않는다**(자문 §1-E) — 44 거부의 `msg1` 원문이 완전
  미지이므로 `market_closed`/`sell_qty_exceeded`/`insufficient_quantity` 로 이미
  가로채이지 않은 **모든** `KisApiError` 가 41 폴백 1회를 받는다. `src/api/balance.py`
  는 diff 0 이고 키워드 추측 추가는 금지다(틀리면 다음 사람이 "처리됐다" 고 오독한다).

| 항 | 내용 | 테스트 |
|---|---|---|
| K1 | enum — `41`/`44` 만 추가, IOC/FOK·47 금지, `00`/`01` 값·순서 불변 | `test_k1_*` |
| K2 | **KIS body** 배관 — `ORD_DVSN="44"` · `ORD_UNPR="0"` · `EXCG_ID_DVSN_CD="KRX"` | `test_k2_*` |
| K3 | 시각 격자 — 16:00~20:00 만 변환, 15:30~16:00·정규장·프리장·20:00 불변 | `test_k3_*` |
| K4 | 날짜 차원 — 09-14 **이전** 16:05 는 변환 0(K7 시간외 단일가) | `test_k4_*` |
| K5 | dial `after_market_exit_division` — `44`(기본)/`41`, 그 밖은 `44` 로 폴백 | `test_k5_*` |
| K6 | 모의(VTS) 무접촉 — `settings.is_production` AND | `test_k6_*` |
| K7 | ETP 관측 — `[after_etp_exit_observe]` 1행, **행위 분기 없음**(fail-open) | `test_k7_*` |
| K8 | fail-safe — 현재가 결측·판정 예외는 시장가 유지 + 주문 발사 | `test_k8_*` |
| K9 | 폭주 봉인 — 폴백 게이트 확장(44→41) · 미분류 TTL · 포기 래치 · TTL 축 | `test_k9_*` |
| K10 | 마커 `[after_exit_division]` / `[after_exit_rejected]` / `[after_exit_giveup]` | `test_k10_*` |

## freezegun 규약

`freeze_time` 인자는 전부 **UTC** 이고 KST = UTC + 9h (`order_engine` 은
`datetime.now(_KST_TZ)` 로 판정한다 — cycle286 헤더 규약 답습).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.session import boards_at
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry
from src.engine.util.tick_size import step_down
from src.models.order import OrderDivision, OrderSide

pytestmark = pytest.mark.unit

KST_TZ = timezone(timedelta(hours=9))
_OE_LOGGER = "src.engine.order_engine"
_TICKER = "161580"
_SID = "long_tail_volatility"
_CUR = 24_800   # 롯데지주 매수가대 — 호가단위 경계와 무관한 평범한 값

_M_DIV = "[after_exit_division]"
_M_ETP = "[after_etp_exit_observe]"
_M_REJ = "[after_exit_rejected]"
_M_GIVEUP = "[after_exit_giveup]"

# ── UTC 리터럴 ↔ KST ──────────────────────────────────────────────────────
_F_0830 = "2026-09-13 23:30:00"     # KST 2026-09-14 08:30:00 (NXT 프리마켓)
_F_1100 = "2026-09-14 02:00:00"     # KST 2026-09-14 11:00:00 (KRX 정규장)
_F_1520 = "2026-09-14 06:20:00"     # KST 2026-09-14 15:20:00 (종가 단일가)
_F_1535 = "2026-09-14 06:35:00"     # KST 2026-09-14 15:35:00 (K5·N5 = 수단 0)
_F_1545 = "2026-09-14 06:45:00"     # KST 2026-09-14 15:45:00 (K5 `06` · N6 `00`)
_F_1600 = "2026-09-14 07:00:00"     # KST 2026-09-14 16:00:00 (애프터 개장 정각)
_F_1605 = "2026-09-14 07:05:00"     # KST 2026-09-14 16:05:00
_F_195959 = "2026-09-14 10:59:59"   # KST 2026-09-14 19:59:59 (애프터 상한 1초 전)
_F_2000 = "2026-09-14 11:00:00"     # KST 2026-09-14 20:00:00 (양 시장 종료)
_F_PRE_1605 = "2026-09-12 07:05:00"  # KST 2026-09-12 16:05:00 (시행 **전**)


# ===========================================================================
# 리그
# ===========================================================================
class _DummyStrategy(StrategyBase):
    def __init__(self, **params) -> None:
        merged = {"exchange": "SOR"}
        merged.update(params)
        super().__init__(
            StrategyConfig(
                strategy_id=_SID, name="ltv-dummy", enabled=True, weight=1.0,
                params=merged,
            )
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 1


def _make_engine(**params):
    reg = StrategyRegistry()
    strat = _DummyStrategy(**params)
    strat.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=24_000, quantity=5, order_no="ORDER-PRE",
        strategy_id=_SID, buy_date=date(2026, 9, 10),
    )
    reg.register(strat)
    return OrderEngine(reg), strat


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = type(
        "R", (), {"order_no": "ORD-1", "order_time": "160500", "krx_org_no": ""}
    )()
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture(autouse=True)
def _rig(monkeypatch: pytest.MonkeyPatch):
    """DB·LLM 격리 + 현재가 캐시 + **실전 환경**(`settings.is_production=True`).

    변환은 `settings.is_production` AND 로 게이팅된다(자문 §4-F) — 기본 리그는 실전이고
    모의는 `test_k6_*` 가 별도로 잰다.
    """
    import src.engine.order_engine as _oe
    import src.db.stock_master as _sm
    from src.config import settings
    from src.engine import scanner

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: None)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "is_stale", AsyncMock(return_value=False))
    monkeypatch.setattr(
        scanner, "ticker_prices", {_TICKER: {"current_price": _CUR}}
    )
    monkeypatch.setattr(settings, "kis_env", "real")
    return None


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch):
    """재시도 백오프 `asyncio.sleep` 무력화.

    ⚠️ **freezegun 과 `asyncio.sleep` 은 같이 못 쓴다** — freezegun 이
    `time.monotonic` 을 동결하면 이벤트 루프의 타이머가 영원히 만료되지 않아
    `await asyncio.sleep(1.0)` 이 **영구 hang** 한다(실측: 이 파일 첫 실행이 2분
    타임아웃으로 죽었다). 매도 재시도는 1s → 2s 백오프를 타므로 여기서 잘라낸다.
    """
    import src.engine.order_engine as _oe

    async def _instant(_delay):
        return None

    monkeypatch.setattr(_oe.asyncio, "sleep", _instant)
    return None


def _pin_boards(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engine.session import session_tracker

    monkeypatch.setattr(session_tracker, "_active", boards_at(datetime.now(KST_TZ).time()))


def _marker_lines(caplog, marker: str) -> list[str]:
    out = []
    for r in caplog.records:
        if r.name != _OE_LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg.startswith(marker):
            out.append(msg)
    return out


def _disallowed_err() -> KisApiError:
    """APBK3013 애프터마켓 변형 — `is_market_order_disallowed` 로 분류된다(실측 문장)."""
    return KisApiError(
        rt_cd="1", msg_cd="APBK3013",
        msg1="[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다.",
    )


def _unclassified_err() -> KisApiError:
    """44 미지원·ETP·가격제한 계열 — 어느 분류기에도 걸리지 않는다(자문 §3 실측 표)."""
    return KisApiError(rt_cd="1", msg_cd="APBK9999", msg1="주문구분코드 오류입니다.")


def _closed_err() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다.")


async def _sell(engine, *, signal: Signal = Signal.STOP_LOSS) -> None:
    await engine.execute_sell(_TICKER, signal, _SID)


# ===========================================================================
# K1 — enum
# ===========================================================================
def test_k1_after_market_divisions_exist() -> None:
    """K1 (RED) — `KRX_AFTER_BEST="44"` · `KRX_AFTER_LIMIT="41"`.

    사용자 선택 = **44 최유리지정가**. 손절은 체결이 목적이고 최유리는 접수 순간의
    반대편 최우선호가(매도면 best bid)를 지정가로 삼아 스프레드를 **크로스**한다
    (자문 §3-A). 41 은 폴백 대상(§9-D-1)이자 dial 의 두 번째 값이다.
    """
    assert getattr(OrderDivision, "KRX_AFTER_BEST", None) is not None, (
        "`OrderDivision.KRX_AFTER_BEST` 부재 — 16:00~20:00 청산 수단이 없다"
    )
    assert OrderDivision.KRX_AFTER_BEST.value == "44"
    assert getattr(OrderDivision, "KRX_AFTER_LIMIT", None) is not None
    assert OrderDivision.KRX_AFTER_LIMIT.value == "41"


def test_k1b_ioc_fok_and_best_priority_are_not_added() -> None:
    """K1 (RED) — 42/43/45/46(IOC/FOK) · 47(최우선지정가)는 **추가하지 않는다**.

    IOC/FOK 는 잔량을 자동취소해 `_schedule_cancel_and_reorder`(cycle273a) 계약과
    충돌하며 손절 잔여를 잃는다. 47 은 자기 방향 최우선호가라 크로스하지 않아
    체결 보장이 없다 = 손절 수단이 아니다.
    """
    values = {d.value for d in OrderDivision}
    forbidden = values & {"42", "43", "45", "46", "47"}
    assert forbidden == set(), f"금지 호가유형이 들어왔다: {sorted(forbidden)}"
    assert values == {"00", "01", "41", "44"}, f"enum 값 집합 {sorted(values)}"


def test_k1c_legacy_values_are_byte_identical() -> None:
    """K1 — `LIMIT="00"` / `MARKET="01"` 값 불변.

    `execute_buy` PR-F(`:410`)가 `order_division == OrderDivision.LIMIT` 화이트리스트로
    분기하므로 값·이름이 바뀌면 매수 경로가 조용히 시장가로 떨어진다.
    """
    assert OrderDivision.LIMIT.value == "00"
    assert OrderDivision.MARKET.value == "01"


# ===========================================================================
# K2 — KIS body 배관 (내부 변수만 보면 배관이 끊겨도 통과한다)
# ===========================================================================
@pytest.mark.asyncio
async def test_k2_place_order_puts_44_and_zero_unpr_into_kis_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """K2 (RED) — `place_order` 가 `ORD_DVSN="44"` · `ORD_UNPR="0"` 를 KIS 로 보낸다.

    `src/api/order.py:64` 는 `order_division.value` 를 **값 그대로** 흘려보내므로
    enum 멤버만 더하면 통하지만, 그 사실을 가드로 못박는다(누가 화이트리스트를
    끼워 넣으면 44 가 조용히 사라진다).
    """
    import src.api.order as _order

    captured: dict = {}

    async def _fake_post(url, tr_id, body, hashkey=None):
        captured.update(body)
        return {"output": {"ODNO": "X", "ORD_TMD": "160500", "KRX_FWDG_ORD_ORGNO": ""}}

    monkeypatch.setattr(_order, "kis_post", _fake_post)
    monkeypatch.setattr(_order, "generate_hashkey", AsyncMock(return_value="hk"))

    await _order.place_order(
        ticker=_TICKER, side=OrderSide.SELL, quantity=5, price=0,
        order_division=OrderDivision.KRX_AFTER_BEST, exchange="KRX",
    )
    assert captured["ORD_DVSN"] == "44", captured
    assert captured["ORD_UNPR"] == "0", captured
    assert captured["EXCG_ID_DVSN_CD"] == "KRX", captured
    assert captured["PDNO"] == _TICKER


@pytest.mark.asyncio
async def test_k2b_place_order_puts_41_with_a_real_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """K2 (RED) — `41` 은 우리가 가격을 통제하는 지정가다."""
    import src.api.order as _order

    captured: dict = {}

    async def _fake_post(url, tr_id, body, hashkey=None):
        captured.update(body)
        return {"output": {"ODNO": "X", "ORD_TMD": "160500", "KRX_FWDG_ORD_ORGNO": ""}}

    monkeypatch.setattr(_order, "kis_post", _fake_post)
    monkeypatch.setattr(_order, "generate_hashkey", AsyncMock(return_value="hk"))

    await _order.place_order(
        ticker=_TICKER, side=OrderSide.SELL, quantity=5,
        price=step_down(_CUR, steps=5),
        order_division=OrderDivision.KRX_AFTER_LIMIT, exchange="KRX",
    )
    assert captured["ORD_DVSN"] == "41"
    assert captured["ORD_UNPR"] == str(step_down(_CUR, steps=5))


# ===========================================================================
# K3 — 시각 격자
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("frozen", [_F_1600, _F_1605, _F_195959])
async def test_k3_after_market_exit_uses_44(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, frozen: str
) -> None:
    """K3 (RED) — 16:00:00 ~ 19:59:59 청산은 `44` · `ORD_UNPR=0` · `KRX`.

    실효 구간은 정확히 그 4시간이다 — 20:00 에 `unsubscribe_all()` 이 돌고
    `_swing_rest_poll_loop` 는 09:00:30~15:20 이라 그 뒤 청산 평가 자체가 0 이다.
    """
    engine, _ = _make_engine()
    with freeze_time(frozen):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert mock_place_order.await_count == 1
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.KRX_AFTER_BEST, kw
    assert kw["price"] == 0, kw
    assert kw["exchange"] == "KRX", kw
    assert kw["quantity"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, exchange, label",
    [
        (_F_1535, "SOR", "15:35 — K5(06)·N5(없음), 오늘도 구멍"),
        (_F_1545, "SOR", "15:45 — K5(06)·N6(00), 오늘 열려 있는 20분"),
    ],
)
async def test_k3b_1530_to_1600_keeps_today_path(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    frozen: str,
    exchange: str,
    label: str,
) -> None:
    """K3 (RED) — **15:30~16:00 은 현행 유지**(자문 카드 A = 선택 (가) 계열).

    선택지 (다)("그 30분 청산 불가로 못박음")는 `register_market_closed` 의
    **다음-09:00 래치** 때문에 성립하지 않는다 — 15:35 거부 한 건이 그 종목의
    매도를 16:00~20:00 애프터 4시간 내내 차단해 이 사이클의 목표를 무효화한다.
    """
    engine, _ = _make_engine()
    with freeze_time(frozen):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == exchange, label
    assert kw["order_division"] is OrderDivision.MARKET, label
    assert kw["price"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("frozen", [_F_1100, _F_1520])
async def test_k3c_main_session_stays_market_order(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, frozen: str
) -> None:
    """K3 (RED) — 09:00~15:30 은 시장가 그대로(거래소만 KRX)."""
    engine, _ = _make_engine()
    with freeze_time(frozen):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.MARKET
    assert kw["price"] == 0
    assert kw["exchange"] == "KRX"


@pytest.mark.asyncio
async def test_k3d_pre_market_preconvert_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K3 (RED) — 08:00~08:50 프리장 청산 = `[sell_market_preconvert_pre_nxt]` 불변.

    브리프 제약: "기존 청산 경로를 좁히지 않는다. 애프터 분기는 순수 추가."
    프리장은 라우팅이 base 를 유지하므로 이 변환이 그대로 발화한다.
    """
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "SOR"
    assert kw["order_division"] is OrderDivision.LIMIT
    assert kw["price"] == step_down(_CUR, steps=5)
    assert _marker_lines(caplog, "[sell_market_preconvert_pre_nxt]")
    assert _marker_lines(caplog, _M_DIV) == [], (
        "프리장에서 애프터 변환 마커가 발화했다 — 분기 스코프 오류"
    )


@pytest.mark.asyncio
async def test_k3e_2000_is_outside_the_after_window(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K3 (RED) — 20:00 정각은 애프터 밖(K6 은 `[16:00, 20:00)` 반개구간)."""
    engine, _ = _make_engine()
    with freeze_time(_F_2000):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.MARKET
    assert kw["exchange"] == "SOR"


# ===========================================================================
# K4 — 날짜 차원
# ===========================================================================
@pytest.mark.asyncio
async def test_k4_pre_reform_1605_is_untouched(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K4 (RED) — **09-14 이전** 16:05 는 변환 0 · 거래소 SOR = 오늘의 경로.

    `market_state` K6 은 `effective_from=2026-09-14` 이고 그 전날까지는 K7(시간외
    단일가 `07`)이다. 날짜 차원이 표에 있으므로 이 커밋을 09-14 전에 배포해도
    저녁 청산이 오늘과 같다 — 리터럴로 `16:00` 을 적으면 이 성질을 잃는다.
    """
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_PRE_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.MARKET
    assert kw["exchange"] == "SOR"
    assert _marker_lines(caplog, _M_DIV) == []


# ===========================================================================
# K5 — dial
# ===========================================================================
@pytest.mark.asyncio
async def test_k5_dial_41_uses_step_down_limit(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K5 (RED) — `after_market_exit_division="41"` → 5호가 아래 지정가.

    최유리가 호가 부재 시 하한가로 접수될 위험(자문 §3-C (ii))이 관측되면 이 dial 로
    **우리가 가격을 통제**한다. 코드 재배포 불필요 = 유일한 완화책.
    """
    engine, _ = _make_engine(after_market_exit_division="41")
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.KRX_AFTER_LIMIT
    assert kw["price"] == step_down(_CUR, steps=5)
    assert kw["exchange"] == "KRX"


@pytest.mark.asyncio
async def test_k5b_dial_default_is_44_when_key_absent(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K5 (RED) — 키 부재 = `44`.

    cycle290(2026-09-13)이 7 전략 전부의 `DEFAULT_PARAMS`/`param_catalog` 에 이 키를
    등재했다(등재 값은 코드 상수와 동일 — `"44"`) — **더 이상 "미등재"가 사실이
    아니다.** 이 테스트가 재는 것은 실 전략이 아니라 이 파일의 합성
    `_DummyStrategy`(키를 넣지 않으면 `config.params` 에 존재하지 않는다)의
    키 부재 시 **폴백 경로**이고, 그 경로 자체는 cycle290 이후에도 여전히 살아
    있다(운영 DB 드리프트로 이 키가 지워지는 경우의 안전망). 실 전략의 등재값이
    코드 상수와 같은지는 `tests/unit/engine/test_cycle290_killswitch_registration.py`
    (`test_g290_12` 등)가 잰다.
    """
    engine, _ = _make_engine()
    assert "after_market_exit_division" not in engine.registry.get(_SID).config.params
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert (
        mock_place_order.await_args.kwargs["order_division"]
        is OrderDivision.KRX_AFTER_BEST
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["47", "01", "42", "", "44 ", None, 44])
async def test_k5c_dial_whitelist_falls_back_to_44(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, bad
) -> None:
    """K5 (RED) — 허용 집합 `{"44","41"}` 밖은 **`44` 로 폴백**(클램프 아님, 화이트리스트).

    청산을 여는 방향으로 폴백한다 — 오염 값이 애프터 청산을 통째로 끄면 안 된다.
    `47`/`01`/IOC 계열이 조용히 나가는 것도 막는다.
    """
    engine, _ = _make_engine(after_market_exit_division=bad)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert (
        mock_place_order.await_args.kwargs["order_division"]
        is OrderDivision.KRX_AFTER_BEST
    ), f"dial={bad!r} 가 44 로 폴백되지 않았다"


# ===========================================================================
# K6 — 모의(VTS)
# ===========================================================================
@pytest.mark.asyncio
async def test_k6_vts_is_byte_identical(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K6 (RED) — 모의는 변환하지 않는다(`settings.is_production` AND).

    VTS 는 `EXCG_ID_DVSN_CD` KRX 만 허용하고 애프터 시뮬레이션이 없으며 **41~47 의
    모의 지원 여부가 정본에 전무**하다(자문 §4-F). 변환하면 모의 실패 사유가
    "호가유형 미지원" 으로 바뀌어 실전 판독을 오염시킨다. 모의는 오늘과 같다.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "kis_env", "vts")
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.MARKET
    assert kw["price"] == 0
    assert _marker_lines(caplog, _M_DIV) == []


# ===========================================================================
# K7 — ETP 관측 (행위 분기 없음 · **애프터 1차 거부 시에만**)
#
# ⚠️ 자문 §4-F/§S5 가 발화 자리를 **행복 경로 → 거부 후** 로 옮겼다:
#   "관측을 행복 경로(주문 직전)에 두면 손절에 DB 왕복 지연이 붙으므로 거부 후로
#    옮긴다 — 판정에 쓰지 않으니 정보 손실 0."
# 손절은 지연에 민감하고, ETP 정보가 필요한 순간은 **거부를 해석할 때**뿐이다.
# 구현은 `asyncio.create_task` fire-and-forget + never-raise 다.
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("grp", ["EF", "EN", "FE"])
async def test_k7_etp_is_observed_but_not_blocked(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog, grp: str
) -> None:
    """K7 (RED) — ETP 는 **관측 1행만**, 변환은 그대로 수행한다(fail-open).

    애프터마켓은 ETP(ETF/ETN) 거래 불가(공지 verbatim)이고 `stock_master.raw.
    scty_grp_id_cd ∈ {EF,EN,FE}` 가 판별 수단이다(신규 KIS 호출 0 — 값이 이미
    `stock_master.raw` JSONB 에 있다). 그러나 현재 보유 11종목 전부 `ST` 이고 노출이
    0 이라, **한 번도 검증하지 않은 값으로 청산 경로를 분기시키는 것이 거부 1건보다
    위험하다**(자문 §4-F: fail-open).

    ⚠️ `prdt_type_cd` 로 판정하면 안 된다 — `stock_master` **3,583행 전부가 `'300'`**
    (ETF 873 포함)이라 한 건도 걸러내지 못한다(조사 실측).

    발화 자리는 **애프터 1차 거부 직후**다(자문 §S5). 그래서 이 테스트는 거부를 먼저
    합성한다 — 성공 경로에서 마커를 기대하면 손절 경로에 DB 왕복을 강제하게 된다.
    """
    import src.db.stock_master as _sm
    from src.models.stock import StockBasics

    monkeypatch.setattr(
        _sm, "get",
        AsyncMock(return_value=StockBasics(
            ticker=_TICKER, name="ETF테스트", excg_dvsn_cd="01",
            nxt_tradable=True, krx_halted=False, admin_item=False,
            raw={"scty_grp_id_cd": grp},
        )),
    )
    engine, _ = _make_engine()
    mock_place_order.side_effect = [_disallowed_err(), _disallowed_err()]
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    # 적대 검증 시정(MEDIUM) — 관측이 `asyncio.create_task` fire-and-forget 로
    # 바뀌어 `_sell()` 반환 시점에 아직 실행되지 않았을 수 있다(41 폴백 주문
    # 발사를 막지 않기 위한 의도된 변경). `_no_retry_sleep` 이 이 파일 전역에서
    # `asyncio.sleep` 을 진짜 대기 없는 스텁으로 바꿔놔서(`await asyncio.sleep(N)`
    # 로는 이벤트 루프에 양보가 안 된다) 대신 백그라운드 task 를 직접 모아 기다린다.
    _pending = [tsk for tsk in asyncio.all_tasks() if tsk is not asyncio.current_task()]
    if _pending:
        await asyncio.gather(*_pending)
    lines = _marker_lines(caplog, _M_ETP)
    assert len(lines) == 1, f"ETP 관측 {len(lines)}행: {lines}"
    assert f"scty_grp={grp}" in lines[0] and f"ticker={_TICKER}" in lines[0], lines[0]
    assert "source=raw" in lines[0], lines[0]
    # fail-open — 관측이 1차 호가유형을 바꾸지 않았다.
    assert (
        mock_place_order.await_args_list[0].kwargs["order_division"]
        is OrderDivision.KRX_AFTER_BEST
    ), "ETP 관측이 변환을 막았다 — 행위 분기 금지(fail-open)"
    assert mock_place_order.await_count == 2, "ETP 라서 폴백을 건너뛰었다 — 행위 분기다"


@pytest.mark.asyncio
async def test_k7c_happy_path_does_not_touch_stock_master(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K7 (RED) — **접수 성공 경로에는 ETP 조회가 붙지 않는다**(자문 §4-F).

    손절은 지연에 민감하다. 주문 직전에 `stock_master.get` 을 한 번 더 부르면 모든
    애프터 청산에 DB 왕복이 얹힌다 — 그 정보는 **거부를 해석할 때만** 쓰이므로
    행복 경로에 둘 이유가 없다.
    """
    import src.db.stock_master as _sm

    async def _count(frozen: str) -> int:
        probe = AsyncMock(return_value=None)
        monkeypatch.setattr(_sm, "get", probe)
        engine, _ = _make_engine()
        with freeze_time(frozen):
            _pin_boards(monkeypatch)
            await _sell(engine)
        return probe.await_count

    # 정규장 성공 = 기준선. `_strategy_exchange_async` 의 `nxt_tradable` 프로브 1회는
    # **기존** 호출이고 이 사이클의 것이 아니다 — 그 상수를 빼고 증가분만 잰다.
    baseline = await _count(_F_1100)
    after = await _count(_F_1605)
    assert after == baseline, (
        f"애프터 성공 경로가 `stock_master.get` 을 {after}회(기준선 {baseline}) 불렀다 — "
        "ETP 조회가 행복 경로에 얹혔다. 그 정보는 거부를 해석할 때만 쓰인다"
    )

    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    engine, _ = _make_engine()
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert _marker_lines(caplog, _M_ETP) == []


@pytest.mark.asyncio
async def test_k7b_plain_stock_emits_no_etp_marker(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K7 (RED) — 보통주(`ST`)는 **거부가 나도** ETP 마커 0행.

    관측이 거부 때마다 무조건 1행이면 분모가 무의미해진다 — `EF/EN/FE` 일 때만 남아야
    "애프터 청산이 구조적으로 불가한 종목을 보유 중" 이라는 신호가 된다.
    """
    import src.db.stock_master as _sm
    from src.models.stock import StockBasics

    monkeypatch.setattr(
        _sm, "get",
        AsyncMock(return_value=StockBasics(
            ticker=_TICKER, name="롯데지주", excg_dvsn_cd="01",
            nxt_tradable=True, krx_halted=False, admin_item=False,
            raw={"scty_grp_id_cd": "ST"},
        )),
    )
    engine, _ = _make_engine()
    mock_place_order.side_effect = [_disallowed_err(), _disallowed_err()]
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert _marker_lines(caplog, _M_ETP) == []


# ===========================================================================
# K8 — fail-safe
# ===========================================================================
@pytest.mark.asyncio
async def test_k8_missing_price_keeps_market_for_dial_41(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K8 (RED) — `41` dial + 현재가 미수신 → **변환하지 않는다**.

    임의 가격 지정가가 더 위험하다(기존 프리장 변환과 같은 판단). 주문은 그대로
    나가고 거부 → 봉인이 받는다.
    """
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {})
    engine, _ = _make_engine(after_market_exit_division="41")
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.MARKET
    assert kw["price"] == 0


@pytest.mark.asyncio
async def test_k8b_missing_price_does_not_block_44(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K8 (RED) — `44` 는 `ORD_UNPR=0` 이라 현재가가 없어도 변환된다.

    최유리는 가격을 우리가 정하지 않으므로 현재가 캐시에 의존하지 않는다 —
    WS 무송출 종목(`nxt_tradable=False` 4종목)의 애프터 청산에서 중요하다.
    """
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {})
    engine, _ = _make_engine()
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.KRX_AFTER_BEST
    assert kw["price"] == 0


@pytest.mark.asyncio
async def test_k8c_probe_exception_keeps_market_and_still_sends(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K8 (RED) — 변환 판정 예외 → 시장가 유지 + **주문은 나간다**."""
    import src.engine.market_state as _ms

    engine, _ = _make_engine()
    monkeypatch.setattr(
        _ms, "get_market_state",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert mock_place_order.await_count == 1
    assert mock_place_order.await_args.kwargs["order_division"] is OrderDivision.MARKET


# ===========================================================================
# K9 — 폭주 봉인 (GO 의 조건)
# ===========================================================================
@pytest.mark.asyncio
async def test_k9_44_rejection_falls_back_to_41(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K9 (RED) — 44 가 분류된 거부를 받으면 `41` 지정가로 1회 폴백.

    기존 게이트는 `is_market_order_disallowed(e) and order_division == MARKET` 이라
    사전 변환으로 `44` 가 되는 순간 **세 개가 동시에 죽는다** — ① 지정가 폴백
    ② 30초 TTL ③ `_pending_next_day_clear` 전환. 이건 새 정책을 넣는 것이 아니라
    기존 정책("시장가 거부 → 지정가 5호가 폴백 1회")을 애프터 어휘로 **옮기는** 것이고,
    옮기지 않으면 그 정책을 삭제하는 셈이다(브리프 "기존 청산 경로를 좁히지 않는다").
    """
    engine, strat = _make_engine()
    mock_place_order.side_effect = [
        _disallowed_err(),
        type("R", (), {"order_no": "ORD-FB", "order_time": "160501", "krx_org_no": ""})(),
    ]
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert mock_place_order.await_count == 2, "폴백이 발사되지 않았다"
    first = mock_place_order.await_args_list[0].kwargs
    second = mock_place_order.await_args_list[1].kwargs
    assert first["order_division"] is OrderDivision.KRX_AFTER_BEST
    assert second["order_division"] is OrderDivision.KRX_AFTER_LIMIT, second
    assert second["price"] == step_down(_CUR, steps=5)
    assert second["exchange"] == "KRX"
    assert _TICKER in strat.state.positions


@pytest.mark.asyncio
async def test_k9b_44_rejection_registers_the_30s_ttl(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K9 (RED) — 폴백 성공에도 30초 TTL 이 등록된다(동일 tick 폭주 차단).

    TTL 등록 호출 2곳이 **모두 게이트 안**에 있어서, 게이트를 안 타면 TTL 이 전혀
    등록되지 않는다 — 그게 폭주의 직접 원인이다.
    """
    engine, _ = _make_engine()
    mock_place_order.side_effect = [
        _disallowed_err(),
        type("R", (), {"order_no": "ORD-FB", "order_time": "160501", "krx_org_no": ""})(),
    ]
    with freeze_time(_F_1605) as ft:
        _pin_boards(monkeypatch)
        await _sell(engine)
        now = datetime.now(KST_TZ)
        assert engine._sell_rejection.is_blocked(_TICKER, now + timedelta(seconds=10))
        assert not engine._sell_rejection.is_blocked(_TICKER, now + timedelta(seconds=31))
        del ft


@pytest.mark.asyncio
async def test_k9c_both_rejected_preserves_position_and_discards_selling(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K9 (RED) — 44 + 41 둘 다 거부 → positions 보존 · `_selling` discard · TTL 등록."""
    engine, strat = _make_engine()
    mock_place_order.side_effect = [_disallowed_err(), _disallowed_err()]
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
        assert engine._sell_rejection.is_blocked(
            _TICKER, datetime.now(KST_TZ) + timedelta(seconds=5)
        )
    assert _TICKER in strat.state.positions
    assert _TICKER not in engine._selling


@pytest.mark.asyncio
async def test_k9d_unclassified_rejection_registers_ttl(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K9 (RED) — **미분류 거부도 TTL 을 등록한다**(D-2, 봉인의 핵심).

    44 가 거부될 가장 유력한 3사유(ETP · 가격제한 ±30% · 미지원)는 어느 분류기에도
    걸리지 않는다(자문 §3 실측: 12종 중 9종 미분류). 오늘의 미분류 경로는
    3회 재시도 → `_selling.discard` → CRITICAL 1행으로 끝나고 **TTL 도 history 도
    남기지 않는다** ⇒ `on_tick` 이 다음 틱에 또 3회. 16:00~20:00 을 초당 1틱으로
    잡으면 ≈42,000 요청 + CRITICAL ≈14,000행 + **폭주 알람(10분 5건)조차 무발화**.
    """
    engine, strat = _make_engine()
    mock_place_order.side_effect = [_unclassified_err(), _unclassified_err()]
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
        now = datetime.now(KST_TZ)
        assert engine._sell_rejection.is_blocked(_TICKER, now + timedelta(seconds=5)), (
            "미분류 거부 뒤 TTL 미등록 — on_tick 이 매 틱마다 재발사한다"
        )
    assert _TICKER in strat.state.positions
    assert _TICKER not in engine._selling
    # 자문 §1-E — 애프터 창의 폴백은 **분류에 의존하지 않는다**(구조적 폴백).
    # 44 거부의 msg1 원문이 완전 미지라 키워드 매칭에 폴백을 인질로 줄 수 없다:
    # 실제 원인이 "44 미지원(41 은 지원)" 이면 폴백을 안 돌리는 쪽이 사이클 목적
    # 자체를 무효화한다. 그래서 1차(44) → 폴백(41) **2발**로 끝나고, 3회 재시도
    # 루프로 흐르지 않는다(재시도는 같은 호가유형을 반복해 봐야 같은 거부다).
    assert mock_place_order.await_count == 2, (
        f"미분류 거부가 {mock_place_order.await_count}발 — 애프터는 1차 44 → 폴백 41 "
        "2발이어야 한다(자문 §1-E 구조적 폴백)"
    )
    first, second = mock_place_order.await_args_list
    assert first.kwargs["order_division"] is OrderDivision.KRX_AFTER_BEST
    assert second.kwargs["order_division"] is OrderDivision.KRX_AFTER_LIMIT, (
        "미분류 거부인데 41 폴백이 안 나갔다 — 폴백이 분류기에 인질로 잡혀 있다"
    )


@pytest.mark.asyncio
async def test_k9e_unclassified_rejection_feeds_the_burst_alarm_history(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K9 (RED) — 미분류 거부가 `_history` 에 적재된다(폭주 알람 활성화).

    `_append_history` 는 `register_*` 4채널에서만 불린다. 미분류 경로가 그 어느
    채널도 타지 않으면 `[매도거부폭주]` CRITICAL 알람이 **구조적으로** 안 울린다.
    """
    engine, _ = _make_engine()
    mock_place_order.side_effect = [_unclassified_err(), _unclassified_err()]
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    hist = engine._sell_rejection._history.get(_TICKER, [])
    assert hist, "미분류 거부가 history 에 남지 않았다 — 폭주 알람이 영구 무발화다"


@pytest.mark.asyncio
async def test_k9f_daily_giveup_latch_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K9 (RED) — 같은 종목이 애프터에서 5회 실패하면 그날 포기(다음 09:00 래치).

    30초 TTL 만으로는 저녁 4시간에 ticker 당 ≈1,440 요청이 남는다. 포기 래치가
    그것을 ≈15 로 수렴시키고 `[after_exit_giveup]` CRITICAL 1행을 남긴다.
    """
    engine, strat = _make_engine()
    mock_place_order.side_effect = [_unclassified_err()] * 30
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605) as ft:
        _pin_boards(monkeypatch)
        for _ in range(5):
            engine._selling.discard(_TICKER)
            strat.state.positions.setdefault(
                _TICKER,
                Position(
                    ticker=_TICKER, buy_price=24_000, quantity=5, order_no="O",
                    strategy_id=_SID, buy_date=date(2026, 9, 10),
                ),
            )
            await _sell(engine)
            ft.tick(delta=timedelta(seconds=31))
        lines = _marker_lines(caplog, _M_GIVEUP)
        assert len(lines) == 1, f"포기 래치 {len(lines)}행: {lines}"
        assert "fails=" in lines[0] and f"ticker={_TICKER}" in lines[0], lines[0]
        # 래치 이후는 30초가 지나도 진입 게이트가 막는다 (다음 09:00 까지)
        assert engine._sell_rejection.is_blocked(
            _TICKER, datetime.now(KST_TZ) + timedelta(minutes=30)
        ), "포기 래치가 다음 09:00 TTL 을 걸지 않았다"


@pytest.mark.asyncio
async def test_k9g_exit_capable_window_uses_the_five_minute_ttl(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K9 (RED) — 16:05 `market_closed` 거부의 TTL 은 **5분**(다음 09:00 아님).

    2단계 TTL 의 설계 근거는 `register_market_closed` docstring 에 적힌 "그 시간엔
    어차피 팔 수 없다" 다. 09-14 부터 16:00~20:00 은 **팔 수 있는 시장**이라 그 전제가
    깨진다 — 다음-09:00 래치를 그대로 두면 애프터 거부 1건이 남은 4시간을 통째로
    잠근다. `sell_rejection.py` 는 **diff 0** 이고 호출부가 넘기는 인자의 **의미**만
    "매도 가능 창 안인가" 로 바꾼다(함수명↔의미 어긋남은 주석·가드로 명시).
    """
    engine, _ = _make_engine()
    mock_place_order.side_effect = [_closed_err()]
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
        now = datetime.now(KST_TZ)
        expiry = engine._sell_rejection._blocked_until.get(_TICKER)
    assert expiry is not None
    assert expiry == now + timedelta(minutes=5), (
        f"16:05 거부 TTL 이 {expiry} — 애프터 4시간을 잠그는 다음-09:00 래치다"
    )


@pytest.mark.asyncio
async def test_k9h_non_exit_capable_window_keeps_the_long_ttl(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """K9 (RED) — 15:35(K5 `06` · N5 없음)은 **팔 수단이 0** 이라 긴 TTL 유지.

    TTL 축을 "매도 가능 창" 으로 재정의하는 것이지 전부 5분으로 미는 것이 아니다.
    """
    engine, _ = _make_engine()
    mock_place_order.side_effect = [_closed_err()]
    with freeze_time(_F_1535):
        _pin_boards(monkeypatch)
        await _sell(engine)
        now = datetime.now(KST_TZ)
        expiry = engine._sell_rejection._blocked_until.get(_TICKER)
    assert expiry is not None
    assert expiry > now + timedelta(hours=1), (
        f"15:35 거부 TTL 이 {expiry} — 팔 수단이 없는 창은 길게 막는 것이 안전측이다"
    )


# ===========================================================================
# K10 — 마커
# ===========================================================================
@pytest.mark.asyncio
async def test_k10_division_marker_fields(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K10 (RED) — `[after_exit_division]` 1행 + 필수 필드.

    저녁 발화량이 수 건이라 cap 없이 무조건 INFO 로 남긴다(D+1 판독 층2-10).
    서식은 자문 §S6 정본 —
    `ticker= div= unpr= cur= exchange= dial=`. `cur=` 가 **주문 직전 현재가**라서
    체결가와 대조하면 44 가 최유리로 작동했는지(|slip_bp| ≲ 1틱) 판독된다.
    """
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    lines = _marker_lines(caplog, _M_DIV)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    for field in (f"ticker={_TICKER}", "div=44", "unpr=0", f"cur={_CUR}",
                  "exchange=KRX", "dial=44"):
        assert field in lines[0], f"필드 `{field}` 누락: {lines[0]}"


@pytest.mark.asyncio
async def test_k10b_rejected_marker_records_classification_and_ttl(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """K10 (RED) — `[after_exit_rejected]` 가 분류·TTL 등록 여부를 남긴다.

    "손절이 조용히 실패하지 않도록" 의 실체 = 침묵이 아니라 **폭주 + TTL 부재**였다.
    이 마커의 `classified=`/`ttl_registered=` 가 그 둘을 한 줄로 판독시킨다(F1~F4).
    """
    engine, _ = _make_engine()
    mock_place_order.side_effect = [_unclassified_err(), _unclassified_err()]
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
    lines = _marker_lines(caplog, _M_REJ)
    assert lines, "애프터 거부 마커 0행 — 판독 채널이 없다"
    assert any("classified=unclassified" in ln for ln in lines), lines
    assert any("ttl_registered=1" in ln for ln in lines), lines
    assert any("div=44" in ln for ln in lines), lines


# ===========================================================================
# K11 — 취소·잔여 재주문 (자문 §4-C1/C2/C3 — GO 조건 6)
#
# ⚠️ 취소의 `ORD_DVSN` 은 **`"00"` 유지 · 변경 0** 이다(자문 §4-C1/§S7). KIS 공식 취소
# 샘플이 `ord_dvsn="00"` 을 쓰고, 국내주식 스펙에 "취소 시 원주문 호가유형" 규약이 없고,
# 그 창의 취소·부분체결 실적이 **all-time 0건**이라 추측으로 바꾸면 작동 중인 정규장
# 취소를 위험에 넣는다. `cancel_order(order_division=)` opt-in 은 첫날 실측 뒤로 미룬다.
# 이 절이 재는 것은 **거래소 정합**(C2)과 **잔여 재주문 호가유형**(C3) 둘뿐이다.
# ===========================================================================
@pytest.fixture
def mock_cancel_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = type(
        "R", (), {"order_no": "ORD-C", "order_time": "160531", "krx_org_no": ""}
    )()
    monkeypatch.setattr(_oe, "cancel_order", mock)
    return mock


@pytest.fixture
def mock_update_status(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock(return_value=1)
    monkeypatch.setattr(_oe, "update_trade_status", mock)
    return mock


@pytest.mark.asyncio
async def test_k11_cancel_uses_the_exchange_the_order_was_sent_to(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
) -> None:
    """K11 (RED) — 취소는 **원주문이 나간 거래소**로 나간다.

    취소 3경로(`_cancel_after_wait` `:1644` · `_cancel_and_reorder` `:1672` ·
    `cancel_remaining` `:1722`)는 **동기** `_strategy_exchange(strategy_id)`(DB 값 직독
    = 현재 전부 `SOR`)를 쓴다. 규칙 1 을 async 관문에만 넣으면 **주문은 KRX, 취소는
    SOR** 로 갈린다(자문 §4-C 발견 4-α = 신규 계약 위반).

    시정 수단은 자문 §4-C2 가 명세한다 — 동기 3 호출부도 라우터를 통과시킨다:
    `ex = self._apply_clock(self._strategy_exchange(sid), sid, side="sell")`.
    (라우터가 **순수 동기** 함수여야 하는 이유가 이것이다.)

    ⚠️ 이 테스트는 **관측 계약만** 잰다 — 내부 자료구조를 지정하지 않는다. 종전 Red 는
    `_order_exchange[order_no]` 매핑을 구조로 요구했지만, 그 수단은 `place_order` 응답
    직후 동기 영역(주문번호 매핑 3종이 사는 자리)을 늘리는 더 큰 변경이다. 남는 간극 =
    **경계 교차**(15:29:5x 주문을 15:30:2x 에 취소하면 라우터가 그 시각의 base 를 준다)
    이고, 이는 후속 항목으로 보고한다.
    """
    engine, _ = _make_engine()
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
        order_no = mock_place_order.await_args.kwargs and "ORD-1"
        assert mock_place_order.await_args.kwargs["exchange"] == "KRX", (
            "원주문이 KRX 로 안 나갔다 — 이 테스트의 전제가 성립하지 않는다"
        )
        engine._schedule_cancel(_TICKER, order_no, 5, _SID)
        await engine._pending_cancel_tasks[_TICKER]
    assert mock_cancel_order.await_count == 1
    assert mock_cancel_order.await_args.kwargs["exchange"] == "KRX", (
        f"원주문은 KRX 인데 취소가 {mock_cancel_order.await_args.kwargs.get('exchange')!r} "
        "로 나갔다 — 동기 3 호출부가 라우터를 안 탄다(자문 §4-C2)"
    )


@pytest.mark.asyncio
async def test_k11b_stop_remainder_reorder_is_not_a_market_order_in_the_after_window(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
) -> None:
    """K11 (RED) — 손절 잔여 재주문(`:1678`)이 애프터에서 시장가로 나가지 않는다.

    `_handle_sell_fill` 은 **항상** `is_stop_loss=True` 로 스케줄하므로 애프터 부분체결은
    예외 없이 이 경로를 타고, 현재 `place_order(price=0)` 은 `order_division` 미지정 =
    `MARKET` 이라 **100% 거부**된다. 게다가 실패는 `logger.exception` 한 줄로 삼켜지고
    앞줄의 `update_trade_status(CANCELLED)` 도 실행되지 않아 `trade_history` 가 PARTIAL
    로 영구 잔존한다(필옵틱스 6h45m 사건과 동형). `execute_sell` 만 고치면 이 구멍이
    그대로 남는다 — 자문 GO 조건 2.
    """
    engine, _ = _make_engine()
    engine._order_strategy["ORD-P"] = _SID
    engine._order_ticker["ORD-P"] = _TICKER
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        engine._schedule_cancel_and_reorder(_TICKER, "ORD-P", 2, is_stop_loss=True)
        await engine._pending_cancel_tasks[_TICKER]
    assert mock_place_order.await_count == 1, "잔여 재주문이 발사되지 않았다"
    kw = mock_place_order.await_args.kwargs
    assert kw.get("order_division") is OrderDivision.KRX_AFTER_BEST, (
        f"애프터 잔여 재주문이 {kw.get('order_division')!r} 로 나갔다 — 구조적 거부다"
    )
    assert kw["exchange"] == "KRX"
    assert mock_cancel_order.await_args.kwargs["exchange"] == "KRX"


@pytest.mark.asyncio
async def test_k11c_main_session_cancel_and_reorder_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
) -> None:
    """K11 (RED) — 정규장 잔여 재주문은 **시장가 그대로**(순수 추가 계약).

    애프터 분기는 순수 추가다 — 09:00~15:30 의 잔여 재주문 동작은 오늘과 같아야 한다
    (거래소만 KRX).
    """
    engine, _ = _make_engine()
    engine._order_strategy["ORD-P"] = _SID
    engine._order_ticker["ORD-P"] = _TICKER
    with freeze_time(_F_1100):
        _pin_boards(monkeypatch)
        engine._schedule_cancel_and_reorder(_TICKER, "ORD-P", 2, is_stop_loss=True)
        await engine._pending_cancel_tasks[_TICKER]
    kw = mock_place_order.await_args.kwargs
    assert kw.get("order_division", OrderDivision.MARKET) is OrderDivision.MARKET
    assert kw["price"] == 0


@pytest.mark.asyncio
async def test_k11d_cancel_survives_a_clock_boundary_crossed_during_the_wait(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
) -> None:
    """K11d (적대 검증 시정 — exit 렌즈 HIGH-3) — 원주문·취소가 시각 경계를

    사이에 두고 **다른 거래소로 갈리지 않는다**. `PARTIAL_FILL_WAIT`(30초) 동안
    시각이 15:59:45 → 16:00:15 처럼 창 경계를 넘으면, 취소 시점에 라우터를
    다시 부르는 구현은 원주문(KRX·krx_unsupported_keep 유지 SOR)과 다른 값
    (KRX·krx_by_clock)을 낸다. `_order_exchange[order_no]` 가 원주문 시점 값을
    기억해 이 갈림을 막는다(자문 §4-C2 실제 의도 — "라우터를 거친다" 는
    "매번 새로 판정한다" 가 아니다).
    """
    engine, _ = _make_engine()
    with freeze_time(_F_1545):  # 15:45 — SOR base, krx_unsupported_keep 유지
        _pin_boards(monkeypatch)
        await _sell(engine)
    order_no = "ORD-1"
    assert order_no in engine._order_exchange, "원주문 거래소가 기록되지 않았다"
    recorded = engine._order_exchange[order_no]
    assert recorded == "SOR", f"원주문은 SOR 유지였어야 한다: {recorded!r}"

    with freeze_time(_F_1600):  # 16:00 — 그 사이 애프터가 열려 라우터라면 KRX 를 준다
        _pin_boards(monkeypatch)
        engine._schedule_cancel_and_reorder(_TICKER, order_no, 2, is_stop_loss=False)
        await engine._pending_cancel_tasks[_TICKER]
    assert mock_cancel_order.await_args.kwargs["exchange"] == recorded, (
        f"취소가 원주문 거래소({recorded!r}) 가 아니라 "
        f"{mock_cancel_order.await_args.kwargs.get('exchange')!r} 로 나갔다 — "
        "경계 교차 시 원주문·취소가 갈린다"
    )


@pytest.mark.asyncio
async def test_k11e_after_cancel_result_marker(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
    caplog,
) -> None:
    """K11e (적대 검증 시정 — sor/contract 렌즈 H2/MEDIUM-4) —

    `[after_cancel_result]` 가 실제로 구현돼 있다(자문 §4-C1 "관측만" 의
    유일한 산출물). `ORD_DVSN` 변경 0(하드코딩 `"00"` 유지) — 이 마커는
    성패만 남긴다.
    """
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
        order_no = "ORD-1"
        engine._schedule_cancel(_TICKER, order_no, 5, _SID)
        await engine._pending_cancel_tasks[_TICKER]
    lines = _marker_lines(caplog, "[after_cancel_result]")
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert f"ticker={_TICKER}" in lines[0]
    assert f"order_no={order_no}" in lines[0]
    assert "ord_dvsn=00" in lines[0]
    assert "result=ok" in lines[0]


@pytest.mark.asyncio
async def test_k11f_after_cancel_result_marker_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_update_status: AsyncMock,
    caplog,
) -> None:
    """K11f — `cancel_order` 가 거부돼도 관측 1행이 남고 예외는 전파된다."""
    import src.engine.order_engine as _oe

    failing_cancel = AsyncMock(side_effect=_disallowed_err())
    monkeypatch.setattr(_oe, "cancel_order", failing_cancel)
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch)
        await _sell(engine)
        order_no = "ORD-1"
        engine._schedule_cancel(_TICKER, order_no, 5, _SID)
        await engine._pending_cancel_tasks[_TICKER]
    lines = _marker_lines(caplog, "[after_cancel_result]")
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert "result=error" in lines[0]
    assert "APBK3013" in lines[0]
