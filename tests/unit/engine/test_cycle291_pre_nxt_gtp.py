"""cycle291 Red — NXT 프리마켓 매수를 GTP(`27`) 로 + 취소 축 `order_division` 배관.

정본 = cycle291 도메인 자문(2026-09-13, 사용자 결정 "(나)안 — `OrderDivision` 에 GTP 를
추가하고 프리장 매수를 그 코드로 낸다"). 접촉 허용 프로덕션 파일 =
`src/models/order.py` · `src/engine/order_engine.py` · `src/api/order.py` 셋뿐
(뒤 둘은 8영역, 사용자 승인).

## 무엇을 왜 바꾸는가

2026-09-14 신설 GTP(Good Till Pre-Market, `27`/`28`/`29`)의 정체성은 **미체결 잔량을
거래소가 프리마켓 종료(08:50)에 일괄 취소**하는 것이다. 우리가 지금 프리장에 보내는
`00`(지정가 — 시장가 사전 변환 결과)은 그 자동취소를 받지 못하므로 미체결이 NXT
정규장(09:00:30~)으로 새고, 새는 방향이 **역선택 쪽으로만** 치우쳐 있다 — 프리장 매수는
`step_up(현재가, 5)` 라 상승이 이어지면 체결되지 않고, 가설이 깨져 시세가 내려올 때만
우리 호가를 때린다. 자문 §1-(a). 실측 표본 = 전 기간 프리장 매수 18건 중 1건이 3개월째
`PENDING`(07-06 08:00:04 · 101730 · 14주 @ 4,305원).

## 자문이 확정한 조건 6개 (이 파일이 그대로 잰다)

1. **매수만.** `execute_sell` diff 0 — 프리장 매도를 GTP 로 바꾸면 08:50 자동취소가
   `_selling` 을 ≈09:45(`_scan_loop` 첫 sync) 까지 잠가 손절 재평가를 억제한다
   (루트 CLAUDE.md 「매도/손절/Trailing 은 PRE/MAIN/POST 무관 항상 작동」 저촉). 자문 §2.
2. **`27` 만.** `28`(GTP최유리)은 `ORD_UNPR` 규약이 현금·신용 문서 사이에서 갈리고 얇은
   프리마켓 호가에서 1레벨에 멈춘다. `29`(GTP최우선)는 자기 방향 최우선호가라 크로스
   하지 않는다(cycle287 `47` 배제와 동일 논거). 자문 §3.
3. **`ORD_UNPR = step_up(현재가, 5)`** — 오늘 `00` 이 보내는 값과 **같은 값**이라 가격
   행위 변경 0. 행위 변경은 전부 08:50 이후의 주문 **수명**에만 있다. 자문 §3.
4. **GTP 거부 → 같은 가격 `00` 1회 폴백 필수.** GTP 거부 msg1 은 우리 분류기
   (`_MARKET_ORDER_DISALLOWED_KEYWORDS` 8종 = 전부 "시장가"/"지정가만" 계열 ·
   `_MARKET_CLOSED_KEYWORDS` = 시간 계열) 어디에도 걸리지 않아 미분류로 `raise` 되고,
   미분류 매수 거부는 `risk.on_tick` 을 죽인다(cycle229 실증). 그래서 폴백 게이트를
   키워드가 아니라 **"우리가 27 을 보냈다" 는 우리 쪽 사실**에 건다.
5. **게이트 4중** = `settings.is_production` ∧ `buy_exchange == "NXT"` ∧
   `"27" in get_market_state(now, market="NXT").order_divisions` ∧ 기존 프리장 판정.
   어느 하나라도 실패·예외면 **현행 `00`**.
6. **파라미터 추가 금지.** 롤백 = 1커밋 revert. 자문 §5.

## 취소 축 = Stage A (배관 + 매핑 + 관측만)

KIS 정본에 "취소 시 원주문 호가유형을 실어라" 는 규약이 **없다**(국내주식 정정취소
필드표에 취소 규약 문장 0건 / 선물옵션은 `[취소] 01 로 입력` = **고정값** / 예약주문
정정취소는 `ORD_DVSN_CD` 를 `[정정]` 전용으로 라벨 / 공식 샘플도 `ord_dvsn="00"`).
게다가 전송을 켜면 **실적 있는 정규장 부분체결 취소**의 `ORD_DVSN` 이 `00` → `01`
(원주문 시장가)로 바뀌어 "정규장 byte 동일" 을 정면 위반한다. 그래서 `cancel_order` 에
opt-in 인자만 열고(`None` = `"00"` byte 동일), `_order_division` 매핑을
`_order_exchange`(cycle287) 와 **완전 대칭**으로 채우고, `[after_cancel_result]` 에
`orig_dvsn=`/`dvsn_src=` 를 붙여 첫 실측으로 Stage B 를 판정한다. 자문 §4.

## freezegun 과 타임존

`order_engine` 은 `datetime.now(_KST_TZ)`(tz-aware) 로 판정한다. freezegun 은 naive
문자열을 **UTC** 로 동결하므로 이 파일의 `freeze_time` 인자는 전부 UTC 이고
KST = UTC + 9h 다(cycle287 헤더 규약 답습). `TZ=UTC` 로도 통과해야 한다.

⚠️ **freezegun 과 `asyncio.sleep` 은 같이 못 쓴다** — `_no_retry_sleep` 픽스처가
`order_engine.asyncio.sleep` 을 무력화한다(cycle287 실측: 미무력화 시 영구 hang).
"""

from __future__ import annotations

import logging
import time as _time
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.session import MarketBoard, boards_at
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry
from src.engine.util.tick_size import step_down, step_up
from src.models.order import CancelType, OrderDivision, OrderSide

pytestmark = pytest.mark.unit

KST_TZ = timezone(timedelta(hours=9))
_OE_LOGGER = "src.engine.order_engine"
_TICKER = "161580"
_SID = "long_tail_volatility"
_CUR = 10_000

_M_PRF = "[market_order_preconvert_pre_nxt]"
_M_SELL_PRF = "[sell_market_preconvert_pre_nxt]"
_M_GTP_FB = "[pre_nxt_gtp_fallback]"
_M_CANCEL = "[after_cancel_result]"

#: 제도 변경 시행일 — `27` 은 이 날 08:00 부터 존재한다(`market_state._REFORM_DAY`).
_REFORM = date(2026, 9, 14)

# ── UTC 리터럴 ↔ KST (위 docstring 규약) ──────────────────────────────────
_F_075959 = "2026-09-13 22:59:59"   # KST 09-14 07:59:59 — 보드 없음(프리장 전)
_F_0800 = "2026-09-13 23:00:00"     # KST 09-14 08:00:00 — NXT 프리마켓 개시
_F_0830 = "2026-09-13 23:30:00"     # KST 09-14 08:30:00 — 프리마켓 중앙
_F_084959 = "2026-09-13 23:49:59"   # KST 09-14 08:49:59 — 프리마켓 마지막 초
_F_0850 = "2026-09-13 23:50:00"     # KST 09-14 08:50:00 — NXT N2 휴장 시작
_F_085959 = "2026-09-13 23:59:59"   # KST 09-14 08:59:59 — N2 마지막 초
_F_0900 = "2026-09-14 00:00:00"     # KST 09-14 09:00:00 — KRX 정규장 개시
_F_1000 = "2026-09-14 01:00:00"     # KST 09-14 10:00:00 — 정규장
_F_1700 = "2026-09-14 08:00:00"     # KST 09-14 17:00:00 — KRX 애프터마켓
#: 시행 **전** 프리장 — `27` 이 아직 없다(`market_state` 날짜 차원이 공짜로 닫는다).
_F_PRE_0830 = "2026-09-12 23:30:00"  # KST 09-13 08:30:00


# ===========================================================================
# 리그
# ===========================================================================
class _DummyStrategy(StrategyBase):
    def __init__(self, **params) -> None:
        merged = {"exchange": "NXT"}
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


def _make_engine(*, with_position: bool = True, **params):
    reg = StrategyRegistry()
    strat = _DummyStrategy(**params)
    if with_position:
        strat.state.positions[_TICKER] = Position(
            ticker=_TICKER, buy_price=9_500, quantity=5, order_no="ORDER-PRE",
            strategy_id=_SID, buy_date=date(2026, 9, 11),
        )
    reg.register(strat)
    return OrderEngine(reg), strat


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = type(
        "R", (), {"order_no": "ORD-1", "order_time": "080005", "krx_org_no": ""}
    )()
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture
def mock_insert_trade(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "insert_trade", mock)
    return mock


@pytest.fixture
def mock_cancel_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = type(
        "R", (), {"order_no": "ORD-C", "order_time": "080035", "krx_org_no": ""}
    )()
    monkeypatch.setattr(_oe, "cancel_order", mock)
    return mock


@pytest.fixture
def mock_update_status(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock(return_value=1)
    monkeypatch.setattr(_oe, "update_trade_status", mock)
    return mock


@pytest.fixture(autouse=True)
def _rig(monkeypatch: pytest.MonkeyPatch):
    """DB·LLM 격리 + 현재가 캐시 + **실전 환경**(`settings.is_production=True`).

    GTP 게이트는 `settings.is_production` AND 로 게이팅된다(VTS 는
    `EXCG_ID_DVSN_CD` 가 KRX 만 허용해 NXT 주문 자체가 불가 — 자문 §6 · cycle287
    애프터 변환 선례). 기본 리그는 실전이고 모의는 `test_g6_*` 가 따로 잰다.
    """
    import src.db.stock_master as _sm
    import src.engine.order_engine as _oe
    from src.config import settings
    from src.engine import scanner

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: None)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "is_stale", AsyncMock(return_value=False))
    monkeypatch.setattr(scanner, "ticker_prices", {_TICKER: {"current_price": _CUR}})
    monkeypatch.setattr(settings, "kis_env", "real")
    return None


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch):
    """`asyncio.sleep` 무력화 — freezegun 아래서는 타이머가 영원히 만료되지 않는다."""
    import src.engine.order_engine as _oe

    async def _instant(_delay):
        return None

    monkeypatch.setattr(_oe.asyncio, "sleep", _instant)
    return None


def _pin_boards(monkeypatch: pytest.MonkeyPatch) -> frozenset:
    """`session_tracker.active` 를 그 시각의 fresh 보드 집합으로 고정한다.

    GTP 게이트의 프리장 판정은 PR-F 사전 변환과 **같은 출처**(`session_tracker.active`)
    를 써야 둘이 갈라지지 않는다(cycle287 자문 §G 와 같은 이유).
    """
    from src.engine.session import session_tracker

    boards = boards_at(datetime.now(KST_TZ).time())
    monkeypatch.setattr(session_tracker, "_active", boards)
    return boards


def _marker_lines(caplog, marker: str) -> list[str]:
    """레벨(INFO 이상) + 로거 + prefix 3중 한정 (CI 루트 로거 DEBUG 방어)."""
    out = []
    for r in caplog.records:
        if r.name != _OE_LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg.startswith(marker):
            out.append(msg)
    return out


def _unclassified_err() -> KisApiError:
    """GTP 미지원·주문유형 오류 계열 — 어느 분류기에도 걸리지 않는다(자문 §7)."""
    return KisApiError(rt_cd="1", msg_cd="APBK9999", msg1="주문구분코드 오류입니다.")


def _disallowed_err() -> KisApiError:
    """`is_market_order_disallowed` 로 분류되는 프리마켓 시장가 거부(실측 문장)."""
    return KisApiError(
        rt_cd="1", msg_cd="APBK0918", msg1="[프리마켓] 시장가매매불가 종목입니다."
    )


async def _buy(engine, strat, price: int = _CUR) -> None:
    strat.state.cached_buyable_qty = 100
    strat.state.cached_buyable_amount = 10_000_000
    strat.state.cached_buyable_at = _time.time()
    await engine.execute_buy(_TICKER, price, strat)


async def _sell(engine, *, signal: Signal = Signal.STOP_LOSS) -> None:
    await engine.execute_sell(_TICKER, signal, _SID)


# ===========================================================================
# G1 — enum (자문 §D: 쓰는 것만 넣는다)
# ===========================================================================
def test_g1_gtp_limit_member_exists_with_value_27() -> None:
    """G1 (RED) — `OrderDivision` 에 GTP 지정가 `27` 이 있다.

    프리마켓 미체결의 08:50 일괄취소를 거래소에 위임하는 유일한 수단이다.
    """
    values = {d.value for d in OrderDivision}
    assert "27" in values, (
        f"GTP 지정가 `27` 부재 — 프리장 미체결이 NXT 정규장으로 새는 경로가 열려 있다. "
        f"현재 값 집합 {sorted(values)}"
    )


def test_g1b_gtp_member_name_carries_limit() -> None:
    """G1 (RED) — `27` 멤버 이름에 `LIMIT` 이 들어간다(문자열 기반 기존 단언 호환).

    `test_order_engine_sell_pre_nxt_preconvert.py` 가 `"LIMIT" in str(div).upper()`
    로 단언하므로, 이름 규약을 여기서 못박아 그 가드가 자동 통과하게 한다.
    """
    member = next((d for d in OrderDivision if d.value == "27"), None)
    assert member is not None, "`27` 멤버 부재 (G1 참조)"
    assert "LIMIT" in member.name.upper(), (
        f"`27` 멤버 이름 {member.name!r} 에 LIMIT 이 없다 — 문자열 기반 기존 단언이 깨진다"
    )


def test_g1c_enum_value_set_is_exactly_five() -> None:
    """G1 (RED) — 값 집합 == `{00, 01, 27, 41, 44}`. `28`/`29` 는 넣지 않는다.

    cycle287 규율("쓰는 것만 넣고 근거를 enum 주석에")을 승계한다. `28` 은 `ORD_UNPR`
    규약이 현금·신용 문서 사이에서 갈려 **미확정**이고(리허설 창이 없는 첫날에 투입할
    수 없다), `29` 는 자기 방향 최우선호가라 크로스하지 않아 체결 보장이 없다.
    """
    values = {d.value for d in OrderDivision}
    assert values == {"00", "01", "27", "41", "44"}, f"enum 값 집합 {sorted(values)}"
    forbidden = values & {"28", "29", "42", "43", "45", "46", "47"}
    assert forbidden == set(), f"투기적 호가유형이 들어왔다: {sorted(forbidden)}"


def test_g1d_legacy_values_are_byte_identical() -> None:
    """G1 — `LIMIT="00"` / `MARKET="01"` / `41` / `44` 값 불변."""
    assert OrderDivision.LIMIT.value == "00"
    assert OrderDivision.MARKET.value == "01"
    assert OrderDivision.KRX_AFTER_LIMIT.value == "41"
    assert OrderDivision.KRX_AFTER_BEST.value == "44"


# ===========================================================================
# G2 — KIS body 배관 (내부 변수만 보면 배관이 끊겨도 통과한다)
# ===========================================================================
@pytest.mark.asyncio
async def test_g2_place_order_puts_27_and_a_real_price_into_kis_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G2 (RED) — `place_order` 가 `ORD_DVSN="27"` · `ORD_UNPR=<실가격>` · `NXT` 를 보낸다.

    `27` 은 **지정가 계열**이라 단가를 싣는다(자문 §3 비대칭 판정: 지정가에 유효
    가격을 실어 틀리는 경로는 없고, `0` 을 실었을 때만 상한가 기준 주문금액 선정으로
    `_apply_budget_limit` **밖에서** 증거금이 부풀 수 있다).
    """
    import src.api.order as _order

    member = next((d for d in OrderDivision if d.value == "27"), None)
    assert member is not None, "`27` 멤버 부재 (G1 참조)"

    captured: dict = {}

    async def _fake_post(url, tr_id, body, hashkey=None):
        captured.update(body)
        return {"output": {"ODNO": "X", "ORD_TMD": "080005", "KRX_FWDG_ORD_ORGNO": ""}}

    monkeypatch.setattr(_order, "kis_post", _fake_post)
    monkeypatch.setattr(_order, "generate_hashkey", AsyncMock(return_value="hk"))

    price = step_up(_CUR, steps=5)
    await _order.place_order(
        ticker=_TICKER, side=OrderSide.BUY, quantity=1, price=price,
        order_division=member, exchange="NXT",
    )
    assert captured["ORD_DVSN"] == "27", captured
    assert captured["ORD_UNPR"] == str(price), captured
    assert captured["EXCG_ID_DVSN_CD"] == "NXT", captured
    assert captured["PDNO"] == _TICKER


# ===========================================================================
# G3 — 프리장 매수 시각 격자 (08:00 / 08:30 / 08:49:59 = GTP)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("frozen", [_F_0800, _F_0830, _F_084959])
async def test_g3_pre_market_buy_uses_gtp_27(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, frozen: str
) -> None:
    """G3 (RED) — 프리마켓(08:00~08:50) NXT 매수는 `27` + `step_up(현재가, 5)` 로 나간다.

    가격은 오늘 `00` 이 보내는 값과 **같다** — 가격 행위 변경 0 이 조건 3 이다.
    """
    engine, strat = _make_engine(with_position=False)
    with freeze_time(frozen):
        boards = _pin_boards(monkeypatch)
        assert MarketBoard.PRE_NXT in boards and MarketBoard.MAIN not in boards
        await _buy(engine, strat)
    assert mock_place_order.await_count == 1
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"].value == "27", (
        f"프리장 매수가 `{kw.get('order_division')}` 로 나갔다 — GTP 승격이 없다"
    )
    assert kw["price"] == step_up(_CUR, steps=5), (
        "GTP 의 단가가 종전 `00` 과 달라졌다 — 가격 행위 변경 0 위반"
    )
    assert kw["exchange"] == "NXT"


@pytest.mark.asyncio
async def test_g3b_marker_keeps_the_four_legacy_fields_and_appends_div(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """G3 (RED) — `[market_order_preconvert_pre_nxt]` 는 기존 4필드 **byte 보존 + 꼬리 append**.

    09-14 전후 grep 합산이 가능해야 한다(cycle273-pre `ws_collapse` 선례). 그리고
    프리장 주문이 `00` 으로 나갔는지 `27` 로 나갔는지는 **이 마커가 유일한 판독축**
    이므로 `div=`/`gtp=`/`reason=` 이 반드시 붙어야 한다.
    """
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    lines = _marker_lines(caplog, _M_PRF)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    legacy = (
        f"{_M_PRF} ticker={_TICKER} exchange=NXT current_price={_CUR} "
        f"converted_to_limit_price={step_up(_CUR, steps=5)}"
    )
    assert lines[0].startswith(legacy), (
        f"기존 4필드의 순서·서식이 바뀌었다(합산 불가) — {lines[0]!r}"
    )
    tail = lines[0][len(legacy):]
    assert "div=27" in tail, f"호가유형 판독축 부재 — 꼬리 {tail!r}"
    assert "gtp=1" in tail, f"GTP 채택 여부 부재 — 꼬리 {tail!r}"
    assert "reason=ok" in tail, f"미채택 사유 필드 부재 — 꼬리 {tail!r}"


@pytest.mark.asyncio
async def test_g3c_before_0800_is_byte_identical_market_order(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """G3 — 07:59:59 는 프리장이 아니다 → 시장가 · `order_division` 키 부재(현행)."""
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_075959):
        boards = _pin_boards(monkeypatch)
        assert MarketBoard.PRE_NXT not in boards
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert "order_division" not in kw, "프리장 전 매수는 시장가(키 생략) 계약이다"
    assert kw["price"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("frozen", [_F_0850, _F_085959])
async def test_g3d_the_0850_to_0900_gap_stays_on_00(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog, frozen: str
) -> None:
    """G3 (RED) — **08:50~09:00 은 설계된 무주문 구간**이라 현행 `00` 과 byte 동일하다.

    보드(`session.py`)는 이 10분도 PRE_NXT 단독으로 보지만 NXT 는 N2(휴장)라
    `market_state` 표에 `27` 이 없다 ⇒ GTP 게이트가 `not_effective` 로 떨어져
    **지정가 `00` + 같은 가격**이 나간다. 이 창을 새로 열지도 막지도 않는다
    (전 기간 주문 0건이 정상).
    """
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(frozen):
        boards = _pin_boards(monkeypatch)
        assert MarketBoard.PRE_NXT in boards and MarketBoard.MAIN not in boards
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.LIMIT, (
        f"08:50~09:00 이 `{kw.get('order_division')}` 로 바뀌었다 — "
        "거래소가 받지 않는 호가유형이다"
    )
    assert kw["price"] == step_up(_CUR, steps=5)
    tail = _marker_lines(caplog, _M_PRF)
    assert tail and "gtp=0" in tail[0] and "reason=not_effective" in tail[0], tail


@pytest.mark.asyncio
async def test_g3e_regular_session_buy_is_byte_identical(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """G3 — 09:00 이후 매수는 시장가 · KRX · 마커 0행(현행 byte 동일)."""
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0900):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert "order_division" not in kw
    assert kw["price"] == 0
    assert kw["exchange"] == "KRX"
    assert _marker_lines(caplog, _M_PRF) == []


# ===========================================================================
# G4 — 거래소 게이트 (SOR 미확인 → 현행 `00`)
# ===========================================================================
@pytest.mark.asyncio
async def test_g4_sor_stays_on_00_because_gtp_sor_support_is_unconfirmed(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """G4 (RED) — `exchange=SOR` 는 GTP 승격하지 않는다(fail-safe).

    `market_state._gtp` 의 `exchanges=_ONLY_NXT` · `exchanges_unknown=_UNKNOWN_SOR`
    — 즉 **SOR 의 27 지원은 정본 미확인**이다. 현재 DB 는 7전략 전부 `exchange=NXT`
    라 실효 손실 0 이고, 누가 SOR 로 되돌리면 그 전략의 프리장 매수는 조용히 현행
    `00` 으로 돌아간다(`reason=exchange` 로만 보인다).
    """
    engine, strat = _make_engine(with_position=False, exchange="SOR")
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "SOR", "프리장은 base 유지(`pre_nxt_keep`)가 계약이다"
    assert kw["order_division"] is OrderDivision.LIMIT, (
        f"SOR 에 GTP 가 나갔다 — 지원 여부가 미확인이다: {kw.get('order_division')}"
    )
    assert kw["price"] == step_up(_CUR, steps=5)
    tail = _marker_lines(caplog, _M_PRF)
    assert tail and "gtp=0" in tail[0] and "reason=exchange" in tail[0], tail


@pytest.mark.asyncio
async def test_g4b_krx_base_never_preconverts(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """G4 — base 가 `KRX`(다운그레이드 결과 등)면 프리장에서도 사전 변환 없음(현행)."""
    engine, strat = _make_engine(with_position=False, exchange="KRX")
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "KRX"
    assert "order_division" not in kw, "KRX 프리장 매수는 현행 시장가 경로다"
    assert kw["price"] == 0


# ===========================================================================
# G5 — 날짜 게이트 (시행 전 = 현행)
# ===========================================================================
@pytest.mark.asyncio
async def test_g5_before_the_reform_day_stays_on_00(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """G5 (RED) — 09-14 **이전** 프리장은 현행 `00`.

    날짜 차원은 `market_state` 표(`effective_from=_REFORM_DAY`)에 이미 있으므로
    프로덕션에 날짜·시각 리터럴을 **한 글자도 새로 적지 않는다**. 그래서 이 커밋을
    09-14 전에 배포해도 프리장 경로가 오늘과 같다.
    """
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_PRE_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.LIMIT, (
        f"`27` 이 존재하지 않는 날짜에 GTP 가 나갔다: {kw.get('order_division')}"
    )
    assert kw["price"] == step_up(_CUR, steps=5)
    tail = _marker_lines(caplog, _M_PRF)
    assert tail and "reason=not_effective" in tail[0], tail


# ===========================================================================
# G6 — VTS 게이트 (모의는 NXT 주문 자체가 불가)
# ===========================================================================
@pytest.mark.asyncio
async def test_g6_vts_stays_on_00(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """G6 (RED) — 모의(VTS)는 GTP 승격 없음.

    `EXCG_ID_DVSN_CD` 정본: "모의투자는 KRX만 가능" ⇒ `27` 은 VTS 에서 도달 불가능한
    코드다. `settings.get_tr_id()` 는 TR_ID 접두 `T`→`V` 만 바꾸고 `ORD_DVSN` 은
    건드리지 않으므로 **명시 게이트**가 필요하다(cycle287 애프터 변환 선례).
    """
    from src.config import settings

    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    monkeypatch.setattr(settings, "kis_env", "vts")
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.LIMIT, (
        f"VTS 에 GTP 가 나갔다: {kw.get('order_division')}"
    )
    tail = _marker_lines(caplog, _M_PRF)
    assert tail and "gtp=0" in tail[0] and "reason=vts" in tail[0], tail


# ===========================================================================
# G7 — fail-safe (판정 예외는 현행 유지 + 주문은 나간다)
# ===========================================================================
@pytest.mark.asyncio
async def test_g7_probe_exception_keeps_00_and_still_orders(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """G7 (RED) — `get_market_state` 가 던지면 현행 `00` 유지 + 주문은 그대로 나간다.

    판정 실패가 **주문 자체를** 막으면 안 된다(fail-safe). P0-1 유령 키가 두 전략을
    전 기간 체결 0건으로 만든 방향이 fail-closed 다.
    """
    import src.engine.market_state as _ms

    def _boom(*a, **kw):
        raise RuntimeError("probe down")

    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        monkeypatch.setattr(_ms, "get_market_state", _boom)
        await _buy(engine, strat)
    assert mock_place_order.await_count == 1, "판정 실패가 주문을 막았다 — fail-safe 위반"
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.LIMIT
    assert kw["price"] == step_up(_CUR, steps=5)
    tail = _marker_lines(caplog, _M_PRF)
    assert tail and "reason=probe_error" in tail[0], tail


@pytest.mark.asyncio
async def test_g7b_session_probe_exception_keeps_market_order(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """G7 — 기존 프리장 판정 블록의 예외 경로는 **무접촉**(시장가/0 으로 되돌린다)."""
    from src.engine import session as _session

    engine, strat = _make_engine(with_position=False)

    class _Boom:
        @property
        def active(self):
            raise RuntimeError("tracker down")

    with freeze_time(_F_0830):
        monkeypatch.setattr(_session, "session_tracker", _Boom())
        await _buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert "order_division" not in kw, "예외 경로가 시장가로 되돌아가지 않았다"
    assert kw["price"] == 0


# ===========================================================================
# G8 — record_price 화이트리스트 (기록이 변환 전 가격으로 새지 않는다)
# ===========================================================================
@pytest.mark.asyncio
async def test_g8_record_price_follows_the_gtp_order_price(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_insert_trade: AsyncMock,
) -> None:
    """G8 (RED) — GTP 경로의 기록 가격 = `step_up(현재가, 5)`.

    `record_price` 게이트가 `order_division == OrderDivision.LIMIT` 열거로 남아 있으면
    `trade_history.price` · `_pending_buy_orders["price"]` · `llm_buy_gate` 의
    `order_price_won` 이 전부 변환 **전** 현재가로 기록된다(조용한 회귀).
    """
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    want = step_up(_CUR, steps=5)
    assert engine._pending_buy_orders["ORD-1"]["price"] == want, (
        f"`_pending_buy_orders` 가 변환 전 가격을 기록했다: "
        f"{engine._pending_buy_orders['ORD-1']['price']} (기대 {want})"
    )
    assert mock_insert_trade.await_count == 1
    record = mock_insert_trade.await_args.args[0]
    assert record.price == want, f"`trade_history` PENDING 가격 {record.price} (기대 {want})"


@pytest.mark.asyncio
async def test_g8b_llm_hook_receives_the_gtp_division_string(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """G8 — AI 매수평가 훅이 받는 `order_division` 은 전송한 코드 문자열이다.

    `llm_buy_evaluations.order_division` 은 TEXT 라 `"27"` 이 그대로 들어가야
    회고분석이 프리장 랏을 식별할 수 있다.
    """
    import src.engine.order_engine as _oe

    seen: dict = {}
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: seen.update(kw))
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    assert seen.get("order_division") == "27", seen.get("order_division")
    assert seen.get("order_price_won") == step_up(_CUR, steps=5)


# ===========================================================================
# G9 — GTP 거부 폴백 (조건 4 — 없으면 NO-GO)
# ===========================================================================
@pytest.mark.asyncio
async def test_g9_gtp_rejection_falls_back_to_00_at_the_same_price(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """G9 (RED) — `27` 이 **미분류로** 거부되면 같은 가격 `00` 으로 1회 재주문한다.

    GTP 거부 msg1 은 `_MARKET_ORDER_DISALLOWED_KEYWORDS`(전부 "시장가"/"지정가만"
    계열) · `_MARKET_CLOSED_KEYWORDS`(시간 계열) 어디에도 걸리지 않는다. 미분류
    매수 거부는 이 핸들러 끝 `raise` 로 `risk.on_tick` 을 죽인다(cycle229: 8/20~8/27
    매수 9건이 매일 15:30 WS 재연결을 유발). 그래서 폴백 게이트를 키워드가 아니라
    **"우리가 27 을 보냈다" 는 우리 쪽 사실**에 건다.
    """
    import src.engine.order_engine as _oe

    calls: list[dict] = []
    ok = type("R", (), {"order_no": "ORD-FB", "order_time": "080006", "krx_org_no": ""})()

    async def _fake_place(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise _unclassified_err()
        return ok

    monkeypatch.setattr(_oe, "place_order", _fake_place)
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)   # raise 하지 않는 것이 계약이다

    assert len(calls) == 2, f"GTP 거부 뒤 폴백 주문이 없다 — 호출 {len(calls)}회"
    assert calls[0]["order_division"].value == "27"
    assert calls[1]["order_division"] is OrderDivision.LIMIT, (
        f"폴백이 `00` 이 아니다: {calls[1].get('order_division')}"
    )
    assert calls[1]["price"] == step_up(_CUR, steps=5), (
        "폴백 가격이 GTP 주문과 다르다 — 가격 행위 변경 0 위반"
    )
    assert calls[1]["exchange"] == "NXT"
    lines = _marker_lines(caplog, _M_GTP_FB)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert "reason=rejected" in lines[0] and "APBK9999" in lines[0], lines[0]


@pytest.mark.asyncio
async def test_g9b_market_order_unclassified_rejection_still_raises(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """G9 — 시장가 주문의 **미분류** 거부는 여전히 전파된다(기존 계약 불변).

    폴백 게이트를 "우리가 27 을 보냈다" 로 좁혔다는 것의 이면이다 — GTP 가 아닌
    랏의 미분류 거부를 조용히 삼키면 다른 원인이 은폐된다.
    """
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "place_order", AsyncMock(side_effect=_unclassified_err()))
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_1000):
        _pin_boards(monkeypatch)
        with pytest.raises(KisApiError):
            await _buy(engine, strat)


@pytest.mark.asyncio
async def test_g9c_gtp_double_rejection_does_not_raise(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """G9 — GTP·`00` 둘 다 거부되면 cooldown 후 조용히 반환한다(기존 폴백 계약).

    알려진 비용 = 거부 2건 + `[kis_rejection]` 2행. 프리장 매수 0.15건/일 규모에서
    수용한 값이다.
    """
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "place_order", AsyncMock(side_effect=_unclassified_err()))
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    assert _TICKER not in strat.state.pending_buys, "거부 뒤 pending_buys 가 남았다"


@pytest.mark.asyncio
async def test_g9d_classified_market_rejection_path_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """G9 — 기존 `is_market_order_disallowed` 폴백은 byte 동일 · GTP 마커 0행."""
    import src.engine.order_engine as _oe

    calls: list[dict] = []
    ok = type("R", (), {"order_no": "ORD-FB", "order_time": "100006", "krx_org_no": ""})()

    async def _fake_place(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise _disallowed_err()
        return ok

    monkeypatch.setattr(_oe, "place_order", _fake_place)
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1000):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    assert len(calls) == 2
    assert calls[1]["order_division"] is OrderDivision.LIMIT
    assert _marker_lines(caplog, _M_GTP_FB) == [], "시장가 거부 폴백에 GTP 마커가 붙었다"


# ===========================================================================
# G10 — 매도는 현행 유지 (자문 §2 — 조건 1)
# ===========================================================================
@pytest.mark.asyncio
async def test_g10_pre_market_sell_stays_on_00(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """G10 — 프리장 **매도**는 `00` + `step_down(현재가, 5)` 그대로다.

    GTP 로 바꾸면 08:50 자동취소가 `_selling` 을 잠그고(거래소발 취소는 체결통보를
    만들지 않아 `_handle_sell_fill`·거부 경로 어디에도 안 걸린다) 해제 주체가
    `reconcile_stale_selling` ← `_sync_positions_from_balance` ← `_scan_loop`
    (`TIME_SCAN_START=09:30` 이후 생성 + 첫 문장 `sleep(300)`) 뿐이라 손절 재평가가
    **≈09:45 까지** 억제된다. 현행 `00` 은 N3(09:00:30~) 로 이월돼 시세 아래 지정가라
    개장 즉시 체결된다 — 누출이 안전망으로 기능하는 유일한 축이다.
    """
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.LIMIT, (
        f"프리장 매도가 `{kw.get('order_division')}` 로 바뀌었다 — 청산을 좁혔다"
    )
    assert kw["price"] == step_down(_CUR, steps=5)
    lines = _marker_lines(caplog, _M_SELL_PRF)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert lines[0] == (
        f"{_M_SELL_PRF} ticker={_TICKER} exchange=NXT current_price={_CUR} "
        f"converted_to_limit_price={step_down(_CUR, steps=5)}"
    ), f"매도 마커가 바뀌었다(매도 diff 0 위반) — {lines[0]!r}"


@pytest.mark.asyncio
async def test_g10b_after_market_sell_is_byte_identical(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """G10 — 애프터(17:00) 청산은 `44` + `unpr=0` 그대로(cycle287/290 계약 불변)."""
    engine, _ = _make_engine()
    with freeze_time(_F_1700):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.KRX_AFTER_BEST
    assert kw["price"] == 0
    assert kw["exchange"] == "KRX"


@pytest.mark.asyncio
async def test_g10c_regular_session_sell_is_byte_identical(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """G10 — 정규장(10:00) 청산은 시장가 · KRX 그대로."""
    engine, _ = _make_engine()
    with freeze_time(_F_1000):
        _pin_boards(monkeypatch)
        await _sell(engine)
    kw = mock_place_order.await_args.kwargs
    assert kw["order_division"] is OrderDivision.MARKET
    assert kw["price"] == 0
    assert kw["exchange"] == "KRX"


# ===========================================================================
# C1 — `cancel_order` opt-in (미전달 = byte 동일)
# ===========================================================================
def test_c1_cancel_order_has_a_keyword_only_order_division_defaulting_to_none() -> None:
    """C1 (RED) — `order_division` 은 **키워드 전용** · 기본값 `None`.

    위치 인자로 승격하면 `cancel_order(order_no, 0, cancel_all=…)` 호출 3곳의 위치
    의미가 흔들린다. 타입은 `str | None`(enum 아님) — cycle287 `test_s4d` 의
    화이트리스트 금지 원칙 승계다.
    """
    import ast
    import inspect

    import src.api.order as _order

    tree = ast.parse(inspect.getsource(_order))
    fn = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "cancel_order"
    )
    positional = [a.arg for a in fn.args.args]
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    assert "order_division" not in positional, (
        f"`order_division` 이 위치 인자로 들어왔다: {positional}"
    )
    assert "order_division" in kwonly, (
        f"`cancel_order` 에 키워드 전용 `order_division` 이 없다: kwonly={kwonly}"
    )
    idx = kwonly.index("order_division")
    default = fn.args.kw_defaults[idx]
    assert isinstance(default, ast.Constant) and default.value is None, (
        "기본값이 `None` 이 아니다 — 미전달 시 현행 byte 동일이 성립하지 않는다"
    )


@pytest.mark.asyncio
async def test_c2_cancel_body_is_byte_identical_when_not_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2 (RED) — 미전달 시 KIS body 10키가 **현행과 완전히 동일**하다.

    소스 리터럴이 아니라 **런타임**으로 잰다(소스 문자열 가드는 표현만 바꾸면
    무력해진다). 호출자 3곳이 전달하지 않는 Stage A 에서 정규장 취소가 한 글자도
    바뀌지 않는 것이 이 사이클의 절대 조건이다.
    """
    import src.api.order as _order
    from src.config import settings

    captured: dict = {}

    async def _fake_post(url, tr_id, body, hashkey=None):
        captured.update(body)
        return {"output": {"ODNO": "C", "ORD_TMD": "100031", "KRX_FWDG_ORD_ORGNO": ""}}

    monkeypatch.setattr(_order, "kis_post", _fake_post)
    monkeypatch.setattr(_order, "generate_hashkey", AsyncMock(return_value="hk"))

    await _order.cancel_order("0000000800", 0, cancel_all=True, exchange="NXT")
    assert captured == {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "KRX_FWDG_ORD_ORGNO": "",
        "ORGN_ODNO": "0000000800",
        "ORD_DVSN": "00",
        "RVSE_CNCL_DVSN_CD": CancelType.CANCEL.value,
        "ORD_QTY": "0",
        "ORD_UNPR": "0",
        "QTY_ALL_ORD_YN": "Y",
        "EXCG_ID_DVSN_CD": "NXT",
    }, captured


@pytest.mark.asyncio
@pytest.mark.parametrize("passed, want", [("27", "27"), ("44", "44"), ("", "00")])
async def test_c3_cancel_body_carries_the_opt_in_value(
    monkeypatch: pytest.MonkeyPatch, passed: str, want: str
) -> None:
    """C3 (RED) — 전달하면 그 값이 실린다. 빈 문자열은 `"00"`(필수 필드 위반 방어).

    화이트리스트·정규화 분기를 두지 않는다 — 다음 코드가 조용히 사라지는 함정이
    `place_order` 쪽에서 이미 한 번 발생했다(`execute_buy` 의 `== LIMIT` 열거).
    """
    import src.api.order as _order

    captured: dict = {}

    async def _fake_post(url, tr_id, body, hashkey=None):
        captured.update(body)
        return {"output": {"ODNO": "C", "ORD_TMD": "085031", "KRX_FWDG_ORD_ORGNO": ""}}

    monkeypatch.setattr(_order, "kis_post", _fake_post)
    monkeypatch.setattr(_order, "generate_hashkey", AsyncMock(return_value="hk"))

    await _order.cancel_order(
        "0000000800", 0, cancel_all=True, exchange="NXT", order_division=passed
    )
    assert captured["ORD_DVSN"] == want, captured


# ===========================================================================
# C4 — `_order_division` 매핑 (`_order_exchange` 완전 대칭)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, want", [(_F_0830, "27"), (_F_0850, "00"), (_F_1000, "01")]
)
async def test_c4_buy_main_path_records_the_division_it_actually_sent(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock,
    frozen: str, want: str,
) -> None:
    """C4 (RED) — 매수 주 경로가 **전송한 호가유형**을 `_order_division` 에 기록한다.

    🔴 지역변수가 아니라 `place_kwargs` 에서 뽑아야 한다. `place_kwargs` 화이트리스트를
    넓히는 것을 잊으면 지역변수는 `27`, 전송은 `01` 이 되어 매핑이 거짓말한다 —
    "전송한 것만 기록한다" 가 규약이다.
    """
    engine, strat = _make_engine(with_position=False)
    with freeze_time(frozen):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    sent = mock_place_order.await_args.kwargs.get(
        "order_division", OrderDivision.MARKET
    )
    mapping = getattr(engine, "_order_division", None)
    assert mapping is not None, "`OrderEngine._order_division` 부재"
    assert mapping.get("ORD-1") == want, f"{mapping!r} (기대 {want})"
    assert mapping["ORD-1"] == sent.value, (
        f"매핑 {mapping['ORD-1']!r} 과 전송 {sent.value!r} 이 다르다 — 매핑이 거짓말한다"
    )


@pytest.mark.asyncio
async def test_c4b_buy_fallback_path_records_00(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """C4 (RED) — 매수 지정가 5호가 폴백 경로도 매핑을 등록한다."""
    import src.engine.order_engine as _oe

    calls: list[dict] = []
    ok = type("R", (), {"order_no": "ORD-FB", "order_time": "100006", "krx_org_no": ""})()

    async def _fake_place(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise _disallowed_err()
        return ok

    monkeypatch.setattr(_oe, "place_order", _fake_place)
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_1000):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
    assert getattr(engine, "_order_division", {}).get("ORD-FB") == "00", (
        getattr(engine, "_order_division", None)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, want", [(_F_0830, "00"), (_F_1000, "01"), (_F_1700, "44")]
)
async def test_c4c_sell_main_path_records_the_division(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock,
    frozen: str, want: str,
) -> None:
    """C4 (RED) — 매도 주 경로도 `_order_exchange` 와 같은 자리에서 등록한다."""
    engine, _ = _make_engine()
    with freeze_time(frozen):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert getattr(engine, "_order_division", {}).get("ORD-1") == want, (
        getattr(engine, "_order_division", None)
    )


@pytest.mark.asyncio
async def test_c4d_sell_fallback_path_records_the_fallback_division(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """C4 (RED) — 매도 시장가거부 폴백(`step_down(5)` 지정가) 경로도 등록한다."""
    import src.engine.order_engine as _oe

    calls: list[dict] = []
    ok = type("R", (), {"order_no": "ORD-SFB", "order_time": "100007", "krx_org_no": ""})()

    async def _fake_place(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise _disallowed_err()
        return ok

    monkeypatch.setattr(_oe, "place_order", _fake_place)
    engine, _ = _make_engine()
    with freeze_time(_F_1000):
        _pin_boards(monkeypatch)
        await _sell(engine)
    assert len(calls) == 2, f"매도 폴백이 발화하지 않았다 — 호출 {len(calls)}회"
    assert getattr(engine, "_order_division", {}).get("ORD-SFB") == "00", (
        getattr(engine, "_order_division", None)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("frozen", [_F_0830, _F_1000, _F_1700])
async def test_c5_key_sets_of_the_two_mappings_are_identical(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, frozen: str
) -> None:
    """C5 (RED) — `_order_division` 키 집합 ≡ `_order_exchange` 키 집합.

    등록 4곳·pop 2곳·clear 1곳이 **같은 자리**라는 것의 관측 가능한 형태다.
    한쪽만 등록하면 취소 관측이 `dvsn_src=absent` 로 조용히 퇴화한다.
    """
    engine, strat = _make_engine()
    with freeze_time(frozen):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
        await _sell(engine)
    assert set(getattr(engine, "_order_division", {})) == set(engine._order_exchange), (
        f"division={sorted(getattr(engine, '_order_division', {}))} / "
        f"exchange={sorted(engine._order_exchange)}"
    )


@pytest.mark.asyncio
async def test_c6_full_fill_pops_the_division_mapping(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, mock_update_status
) -> None:
    """C6 (RED) — 전량 체결 시 `_order_exchange` 와 **같은 자리**에서 pop 된다.

    🔴 `if self._pending_cancel_order_no.get(ticker) == order_no:` 게이트 **안**에
    넣으면 그 게이트가 흔히 false 라 매핑이 하루치 누수되고, cycle273a AST3/AST4 의
    판정 영역까지 변형된다.
    """
    import src.db.positions as _pos

    # `_handle_buy_fill` 은 `from src.db.positions import save_position` 지역 import 다.
    monkeypatch.setattr(_pos, "save_position", AsyncMock(return_value=None))
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
        assert "ORD-1" in getattr(engine, "_order_division", {})
        await engine._handle_buy_fill(_TICKER, "ORD-1", step_up(_CUR, steps=5), 1, 1, 1)
    assert "ORD-1" not in engine._order_exchange, "선례(`_order_exchange`)가 안 지워졌다"
    assert "ORD-1" not in getattr(engine, "_order_division", {}), (
        "전량 체결 뒤 `_order_division` 이 남았다 — 무한 성장"
    )


def test_c7_reset_daily_state_clears_the_division_mapping() -> None:
    """C7 (RED) — `OrderEngine.reset_daily_state()` 가 `_order_division` 도 clear.

    🔴 clear 를 `scheduler._reset_daily_state` 에 두면 `scheduler.py` diff 0 이
    깨진다(cycle291 착수 시점 3,897L · 상한 3,900 — 여유 3줄. cycle292 가 예고대로
    leaf 추출을 수행해 3,726L 이 됐지만 **이 배치 결정은 그대로다**: clear 의 소유자는
    라인 예산이 아니라 `_order_division` 의 소유자다). `_order_exchange` 와 같은
    위임 쪽에 둔다 — order_no 는 하루 단위로만 유일하다.
    """
    engine, _ = _make_engine()
    mapping = getattr(engine, "_order_division", None)
    assert mapping is not None, "`OrderEngine._order_division` 부재"
    mapping["X"] = "27"
    engine._order_exchange["X"] = "NXT"
    engine.reset_daily_state()
    assert engine._order_exchange == {}, "선례가 안 지워졌다"
    assert getattr(engine, "_order_division") == {}, "`_order_division` 이 남았다"


# ===========================================================================
# C8 — `[after_cancel_result]` 관측 확장 + 호출자는 전달하지 않는다(Stage A)
# ===========================================================================
@pytest.mark.asyncio
async def test_c8_cancel_marker_carries_orig_dvsn_from_the_mapping(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
    caplog,
) -> None:
    """C8 (RED) — 마커가 `ord_dvsn=`(실제 전송) · `orig_dvsn=`(원주문) · `dvsn_src=` 를 싣는다.

    지금의 `result=error` 한 줄은 **왜** 를 말하지 않는다. `orig_dvsn=` 이 붙으면
    실패를 층화할 수 있다 — 비-`{00,01}` 원주문만 error 면 그것이 Stage B(전송)를
    정당화하는 정확한 증거이고, `00|01` 도 함께 error 면 원인은 호가유형이 아니다
    (APBK0927 잔량 0 계열). ⚠️ INFO 의 `system_logs` 보존은 **2일**이다.
    """
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
        engine._schedule_cancel(_TICKER, "ORD-1", 5, _SID)
        await engine._pending_cancel_tasks[_TICKER]
    lines = _marker_lines(caplog, _M_CANCEL)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert "ord_dvsn=00" in lines[0], (
        f"실제 전송 값 축이 사라졌다(Stage A 는 항상 `00`) — {lines[0]!r}"
    )
    assert "orig_dvsn=27" in lines[0], f"원주문 호가유형 축 부재 — {lines[0]!r}"
    assert "dvsn_src=map" in lines[0], f"출처 축 부재 — {lines[0]!r}"


@pytest.mark.asyncio
async def test_c8b_cancel_marker_says_absent_when_the_mapping_is_gone(
    monkeypatch: pytest.MonkeyPatch,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
    caplog,
) -> None:
    """C8 (RED) — 매핑이 없으면 `orig_dvsn=- dvsn_src=absent` (재시작·수동매도 등).

    fail-open 이 관측에서도 보여야 한다 — 취소가 안 되는 방향으로 실패하면 미체결이
    남으므로 `"00"` 유지가 유일한 방향이고, 그 사실이 로그에 남아야 Stage B 판정이
    표본을 오해하지 않는다.
    """
    engine, _ = _make_engine()
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1000):
        _pin_boards(monkeypatch)
        engine._order_strategy["ORD-Z"] = _SID
        engine._order_ticker["ORD-Z"] = _TICKER
        engine._schedule_cancel(_TICKER, "ORD-Z", 5, _SID)
        await engine._pending_cancel_tasks[_TICKER]
    lines = _marker_lines(caplog, _M_CANCEL)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert "orig_dvsn=-" in lines[0], f"부재 표기가 없다 — {lines[0]!r}"
    assert "dvsn_src=absent" in lines[0], f"출처 축이 absent 가 아니다 — {lines[0]!r}"
    assert "ord_dvsn=00" in lines[0]


@pytest.mark.asyncio
async def test_c9_cancel_callers_do_not_pass_order_division_yet(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
) -> None:
    """C9 — **Stage A**: 호출자 3곳은 `order_division` 을 전달하지 않는다.

    정본에 승계 규약이 없고(선물옵션은 `[취소] 01 로 입력` = 고정값), 전송을 켜면
    **실적 있는 정규장 부분체결 취소**의 `ORD_DVSN` 이 `00` → `01`(원주문 시장가)로
    바뀌어 "정규장 byte 동일" 을 정면 위반한다. Stage B 착수 조건 = D+1 이후
    `[after_cancel_result]` 에서 `orig_dvsn` 이 `41|44|27` **인 행만** error 로
    층화되는 것 + 별도 승인.
    """
    engine, strat = _make_engine(with_position=False)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
        engine._schedule_cancel(_TICKER, "ORD-1", 5, _SID)
        await engine._pending_cancel_tasks[_TICKER]
    kw = mock_cancel_order.await_args.kwargs
    assert "order_division" not in kw, (
        f"Stage A 인데 취소가 호가유형을 전송했다: {kw.get('order_division')!r}. "
        "전환은 매매 행위 변경 = 별도 승인 대상이다"
    )
    assert kw["exchange"] == "NXT", "원주문 거래소 계약(cycle287)이 깨졌다"


# ===========================================================================
# C8c/C8d — `[after_cancel_result]` 는 3경로 전부에서 orig_dvsn/dvsn_src 를 싣는다
#           (적대 검증 시정 — test 렌즈 MEDIUM #3, `_cancel_after_wait` 만 재던 결손)
# ===========================================================================
@pytest.mark.asyncio
async def test_c8c_cancel_and_reorder_marker_carries_orig_dvsn(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    mock_cancel_order: AsyncMock,
    mock_update_status: AsyncMock,
    caplog,
) -> None:
    """C8c (적대 검증 시정) — `_cancel_and_reorder`(정규장 부분체결 손절 잔여,
    **실적 있는 유일한 취소 경로군**) 도 `orig_dvsn=`/`dvsn_src=` 를 남긴다.

    실측 뮤테이션 — `_orig_div = self._order_division.get(order_no)` 를 `None`
    으로 바꿔도 표적 스위트 전원이 통과했다(`test_c8`/`test_c8b` 가
    `_cancel_after_wait` 만 쟀다). `remaining=0` 으로 재주문 분기(§4-C3)를
    비활성화해 이 경로 하나만 격리한다.
    """
    engine, strat = _make_engine(with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await _buy(engine, strat)
        assert engine._order_division.get("ORD-1") == "27", "선행조건: GTP 매핑 부재"
        await engine._cancel_and_reorder(_TICKER, "ORD-1", 0, is_stop_loss=True)
    lines = _marker_lines(caplog, _M_CANCEL)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert "ord_dvsn=00" in lines[0], f"실제 전송 값 축이 사라졌다 — {lines[0]!r}"
    assert "orig_dvsn=27" in lines[0], f"원주문 호가유형 축 부재 — {lines[0]!r}"
    assert "dvsn_src=map" in lines[0], f"출처 축 부재 — {lines[0]!r}"


@pytest.mark.asyncio
async def test_c8d_cancel_remaining_marker_carries_orig_dvsn(
    monkeypatch: pytest.MonkeyPatch,
    mock_cancel_order: AsyncMock,
    caplog,
) -> None:
    """C8d (적대 검증 시정) — `cancel_remaining` 도 `orig_dvsn=`/`dvsn_src=` 를
    남긴다(같은 뮤테이션이 이 경로도 무가드로 통과했다).
    """
    engine, strat = _make_engine(with_position=True)
    engine._order_exchange["ORDER-PRE"] = "NXT"
    engine._order_division["ORDER-PRE"] = "27"
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    await engine.cancel_remaining(_TICKER, _SID)
    lines = _marker_lines(caplog, _M_CANCEL)
    assert len(lines) == 1, f"{len(lines)}행: {lines}"
    assert "ord_dvsn=00" in lines[0], f"실제 전송 값 축이 사라졌다 — {lines[0]!r}"
    assert "orig_dvsn=27" in lines[0], f"원주문 호가유형 축 부재 — {lines[0]!r}"
    assert "dvsn_src=map" in lines[0], f"출처 축 부재 — {lines[0]!r}"


# ===========================================================================
# C6b — `_handle_sell_fill` 의 pop 은 `_pending_cancel_order_no` 게이트 밖이다
#       (적대 검증 시정 — test 렌즈 MEDIUM #5, 소스 개수 가드만으론 못 잡는다)
# ===========================================================================
@pytest.mark.asyncio
async def test_c6b_handle_sell_fill_pops_division_even_when_cancel_gate_is_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C6b (적대 검증 시정) — 전량 매도체결의 `_order_division`/`_order_exchange`
    pop 은 `_pending_cancel_order_no` 게이트가 **false 여도** 일어난다.

    실측 뮤테이션 — 두 pop 줄을 그 게이트 **안**으로 옮겨도(`.pop(` 총 호출
    개수는 그대로라 `test_a10c` 는 반응하지 않는다) 표적 스위트 전원이
    통과했다. 게이트는 대개 false(그 종목에 걸린 취소 타이머가 이 주문번호와
    다를 때)이므로 그 이동은 21:30 정산까지 두 매핑을 누수시킨다.
    """
    import src.db.positions as _positions

    engine, strat = _make_engine(with_position=False)
    strat.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=9_500, quantity=5, order_no="ORD-1",
        strategy_id=_SID, buy_date=date(2026, 9, 11),
    )
    engine._order_exchange["ORD-1"] = "NXT"
    engine._order_division["ORD-1"] = "27"
    engine._order_strategy["ORD-1"] = _SID
    # 게이트가 반드시 false 이도록 다른 order_no 를 심는다(현실의 대다수 경우).
    engine._pending_cancel_order_no[_TICKER] = "OTHER-ORDER"
    monkeypatch.setattr(
        "src.engine.order_engine.update_trade_status", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))
    monkeypatch.setattr(
        OrderEngine, "_unsubscribe_if_no_other_strategy", AsyncMock(return_value=None),
    )
    await engine._handle_sell_fill(_TICKER, "ORD-1", 9_600, 5, 5, 5)
    assert "ORD-1" not in engine._order_exchange, "선례가 게이트 안에 갇혔다"
    assert "ORD-1" not in engine._order_division, (
        "`_order_division` pop 이 `_pending_cancel_order_no` 게이트에 갇혔다 — 누수"
    )
