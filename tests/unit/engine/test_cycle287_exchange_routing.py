"""cycle287 Red — 규칙 1: 주문 채널(거래소)은 **시각**이 정한다.

정본 = cycle287 도메인 자문 §1·§8·§9-B (2026-09-12, 사용자 결정 2026-09-12).
접촉 허용 프로덕션 파일 = `src/models/order.py` · `src/engine/order_engine.py` ·
`src/api/order.py` **셋뿐**(뒤 둘은 8영역, 사용자 승인).

## 사용자 규칙과 자문이 환산한 원리

사용자 문장: "프리장은 NXT, 나머지는 전부 KRX."

문자 그대로 옮기면 두 곳이 부러진다(자문 §2·§6 실측):

* **15:40~16:00** — KRX K5 는 `06`(장후 시간외 종가) 하나만 받고 우리는 `06` 을 보내지
  않는다. 이 20분은 **오늘 열려 있다**(SOR → NXT N6 가 `00` 을 받아 09-08 15:45:45
  필옵틱스 매도가 실제로 체결됐다). KRX 로 묶으면 작동하던 청산 경로를 잃는다.
* **15:30~15:40** — KRX K5(`06`) · NXT N5(`()`) 라 오늘도 이미 구멍이다.

그래서 자문이 규칙을 **원리**로 환산했다:

> KRX 를 기본으로 하되, 그 시각 KRX 가 우리가 보낼 수 있는 호가유형
> (`_SENDABLE_DIVISIONS`)을 하나도 받지 않으면 현행 경로(base)를 유지한다.
> 프리장(`session_tracker.active` 가 PRE_NXT 단독)은 base 유지.

이 한 문장이 위 두 구멍과 **08:50~09:00**(NXT N2 휴장 10분)을 판정식 자체에서 닫고,
시각 리터럴을 한 글자도 새로 적지 않는다(`market_state.py` 표를 **읽는다**).

## Green 계약 (자문 §9-B)

    _SENDABLE_DIVISIONS = frozenset({"00", "01", "41", "44"})
    _CLOCK_ROUTED_BASES = ("NXT", "SOR")

    def _route_exchange_by_clock(base, *, side="sell", mode="enforce", now=None)
            -> tuple[str, str]:
        base not in _CLOCK_ROUTED_BASES            -> (base, "base_krx")
        mode == "off"                              -> (base, "mode_off")
        mode == "sell_only" and side != "sell"     -> (base, "mode_sell_only")
        PRE_NXT in active and MAIN not in active   -> (base, "pre_nxt_keep")
        _SENDABLE ∩ KRX.order_divisions            -> ("KRX", "krx_by_clock")
        _SENDABLE ∩ NXT.order_divisions            -> (base, "krx_unsupported_keep")
        else                                       -> (base, "both_unsupported_keep")
        예외                                        -> (base, "probe_error")   # fail-open

적용 자리 = `_strategy_exchange_async` 의 **반환 5곳 전부**(= 함수 말미에서 한 번 감싼다).
그래야 호출부 2곳(`:361` 매수 · `:666` 매도)을 한 번에 덮고, cycle286 `[nxt_post_reinforce]`
판정보다 **앞**이라 `target_exchange` = "실제로 보낸 거래소" 의미가 보존되며,
`[nxt_downgrade]`/`[stock_master_miss]` 관측이 라우팅 **전**에 발화해 회귀가 0 이다.
함수 **맨 앞**에 두면 09:00 이후 `[nxt_downgrade]` 가 조용히 사라진다 — 그렇게 하지 말 것.

| 항 | 내용 | 테스트 |
|---|---|---|
| R1 | 판정 격자(시각 × base) — 경계 16종 전수 | `test_r1_*` |
| R2 | `mode` 3값(`enforce`/`sell_only`/`off`) · 키 부재 = `enforce` | `test_r2_*` |
| R3 | 판정 불가·예외 = **base 유지**(fail-open — 주문이 안 나가는 일은 없어야 한다) | `test_r3_*` |
| R4 | `nxt_tradable=False` 다운그레이드가 라우팅보다 **우선**(KRX 를 되돌리지 않는다) | `test_r4_*` |
| R5 | 매수 배관 — `place_order(exchange=)` 에 실제로 실린다 + PR-F 불변 | `test_r5_*` |
| R6 | 매도 배관 — `place_order(exchange=)` + 익일청산·강제청산 신호 | `test_r6_*` |
| R7 | `limit_price > 0` 지정가 매도 분기도 라우팅을 탄다 | `test_r7_*` |
| R8 | 마커 `[order_channel]` — `base != exchange` 일 때만, 1회/(ticker,side,reason)/일 | `test_r8_*` |
| R9 | cycle286 `[nxt_post_reinforce]` 판정 **불변** + `_selling`/positions 계약 불변 | `test_r9_*` |

## freezegun 과 타임존 (cycle286 헤더 규약 답습)

`order_engine` 은 `datetime.now(_KST_TZ)`(tz-aware) 로 판정한다. freezegun 은 naive 문자열을
**UTC** 로 동결하므로 이 파일의 `freeze_time` 인자는 전부 UTC 이고 KST = UTC + 9h 다
(실측 확인: `freeze_time("2026-09-14 07:05:00")` → `datetime.now(KST)` = 16:05+09:00).
순수 함수 격자는 `now=` 를 **명시 전달**해 시계와 완전히 분리한다 — 그쪽이 TZ 독립의
유일한 확실한 방법이고, 배관 테스트만 freezegun 으로 창 안·밖을 고정한다.
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
from src.models.order import OrderDivision

pytestmark = [
    pytest.mark.unit,
    # 🔴 cycle317 의 휴식 컷 중립화 픽스처를 **옵트아웃**한다.
    # 이 파일의 `test_r6` 이 15:45(= cycle295 컷 구간)에 주문이 나가지 않는 것을 단언한다.
    pytest.mark.real_market_rest,
]

KST_TZ = timezone(timedelta(hours=9))
_OE_LOGGER = "src.engine.order_engine"
_ROUTE_MARKER = "[order_channel]"
_CONFIG_MARKER = "[order_channel_config]"
_TICKER = "161580"
_SID = "long_tail_volatility"

#: 제도 변경 시행일 (KRX 애프터마켓 16:00~20:00 신설 · 시간외 단일가 폐지).
_REFORM = date(2026, 9, 14)
#: 시행 **전** — 16:00~18:00 은 K7(시간외 단일가 `07`) 이라 우리 집합과 교집합이 없다.
_PRE_REFORM = date(2026, 9, 12)


def _kst(d: date, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=KST_TZ)


# ── freezegun 용 UTC 리터럴 ↔ KST (위 docstring 규약) ──────────────────────
_F_0830 = "2026-09-13 23:30:00"   # KST 2026-09-14 08:30:00 (NXT 프리마켓)
_F_0852 = "2026-09-13 23:52:00"   # KST 2026-09-14 08:52:00 (NXT N2 휴장 10분)
_F_1100 = "2026-09-14 02:00:00"   # KST 2026-09-14 11:00:00 (KRX 정규장)
_F_0900_05 = "2026-09-14 00:00:05"  # KST 2026-09-14 09:00:05 (익일청산 드레인)
_F_1520 = "2026-09-14 06:20:00"   # KST 2026-09-14 15:20:00 (강제청산)
_F_1545 = "2026-09-14 06:45:00"   # KST 2026-09-14 15:45:00 (KRX 미지원 · NXT N6)
_F_1605 = "2026-09-14 07:05:00"   # KST 2026-09-14 16:05:00 (KRX 애프터마켓)


# ===========================================================================
# 리그
# ===========================================================================
class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = _SID, **params) -> None:
        merged = {"exchange": "SOR"}
        merged.update(params)
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
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


def _make_engine(*, exchange: str = "SOR", with_position: bool = True, **params):
    reg = StrategyRegistry()
    strat = _DummyStrategy(exchange=exchange, **params)
    if with_position:
        strat.state.positions[_TICKER] = Position(
            ticker=_TICKER,
            buy_price=10_000,
            quantity=3,
            order_no="ORDER-PRE",
            strategy_id=_SID,
            buy_date=date(2026, 9, 11),
        )
    reg.register(strat)
    return OrderEngine(reg), strat


@pytest.fixture
def engine_pair():
    return _make_engine()


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = type(
        "R", (), {"order_no": "ORD-1", "order_time": "090000", "krx_org_no": ""}
    )()
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture(autouse=True)
def _isolate_db(monkeypatch: pytest.MonkeyPatch):
    """DB·LLM 훅 격리 — 라우팅 판정과 무관한 I/O 를 전부 잘라낸다."""
    import src.engine.order_engine as _oe
    import src.db.stock_master as _sm

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: None)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    return None


def _pin_boards(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> frozenset:
    """`session_tracker.active` 를 그 시각의 **fresh** 보드 집합으로 고정한다.

    실제 tracker 는 30초 주기 stale 캐시다. 라우팅의 프리장 clause 는 PR-F 사전
    변환과 **같은 출처**(`session_tracker.active`)를 써야 둘이 갈라지지 않으므로
    (자문 §G), 테스트도 같은 출처를 핀한다.
    """
    from src.engine.session import session_tracker

    boards = boards_at(moment.time())
    monkeypatch.setattr(session_tracker, "_active", boards)
    return boards


def _route(base: str, moment: datetime, **kw):
    from src.engine import order_engine as _oe

    fn = getattr(_oe, "_route_exchange_by_clock", None)
    assert fn is not None, (
        "`order_engine._route_exchange_by_clock` 부재 — cycle287 규칙 1 의 판정식이 "
        "아직 없다(자문 §9-B)"
    )
    return fn(base, now=moment, **kw)


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


def _closed_err() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다.")


# ===========================================================================
# R1 — 판정 격자 (경계 전수 × base 3값)
# ===========================================================================
#: (KST 시각, 기대 routed(base=SOR 기준), 기대 reason)
_GRID = [
    # ── 08:00 전 — 어느 시장도 우리 유형을 받지 않는다 ──────────────────
    ((7, 59, 59), "SOR", "both_unsupported_keep"),
    # ── NXT 프리마켓(보드 PRE_NXT 단독) = 현행 유지 ─────────────────────
    ((8, 0, 0), "SOR", "pre_nxt_keep"),
    ((8, 30, 0), "SOR", "pre_nxt_keep"),
    ((8, 49, 59), "SOR", "pre_nxt_keep"),
    # 08:50~09:00 — NXT 는 N2(휴장)지만 보드는 아직 PRE_NXT 다.
    # 자문 §G: 여기서 KRX 로 떨어지면 매도 사전 지정가 변환(PR-F 대칭)이 죽어
    # 시가 단일가에 **시장가**가 나간다. 그래서 base 유지가 계약이다.
    ((8, 50, 0), "SOR", "pre_nxt_keep"),
    ((8, 59, 59), "SOR", "pre_nxt_keep"),
    # ── KRX 정규장 ─────────────────────────────────────────────────────
    ((9, 0, 0), "KRX", "krx_by_clock"),
    ((11, 0, 0), "KRX", "krx_by_clock"),
    ((15, 19, 59), "KRX", "krx_by_clock"),
    # ── KRX 종가 단일가(K4 = 00·01) ─────────────────────────────────────
    ((15, 20, 0), "KRX", "krx_by_clock"),
    ((15, 29, 59), "KRX", "krx_by_clock"),
    # ── 15:30~15:40 — KRX K5(06) · NXT N5(없음) = 오늘도 구멍 ───────────
    ((15, 30, 0), "SOR", "both_unsupported_keep"),
    ((15, 39, 59), "SOR", "both_unsupported_keep"),
    # ── 15:40~16:00 — KRX 는 06 만, NXT N6 는 00 을 받는다 ⇒ 현행 유지 ──
    ((15, 40, 0), "SOR", "krx_unsupported_keep"),
    ((15, 59, 59), "SOR", "krx_unsupported_keep"),
    # ── 16:00~20:00 KRX 애프터마켓(41~47 ⊃ 41·44) ───────────────────────
    ((16, 0, 0), "KRX", "krx_by_clock"),
    ((16, 5, 0), "KRX", "krx_by_clock"),
    ((19, 59, 59), "KRX", "krx_by_clock"),
    # ── 20:00 — 양 시장 종료. 정각 **포함**이 계약이다(16:00 <= t < 20:00) ───
    ((20, 0, 0), "SOR", "both_unsupported_keep"),
    ((20, 0, 1), "SOR", "both_unsupported_keep"),
]


@pytest.mark.parametrize("hms, routed, reason", _GRID, ids=[
    f"{h:02d}{m:02d}{s:02d}-{r}" for (h, m, s), r, _ in _GRID
])
def test_r1_grid_base_sor(
    monkeypatch: pytest.MonkeyPatch, hms, routed: str, reason: str
) -> None:
    """R1 (RED) — base `SOR` 의 시각 격자. 09:00 이후는 KRX, 프리장·미지원 창은 현행.

    시각 리터럴은 이 테스트에만 있고 프로덕션에는 없어야 한다 — 판정은
    `market_state.MARKET_TABLE`(유일 정본)을 읽어 나온다.
    """
    moment = _kst(_REFORM, *hms)
    _pin_boards(monkeypatch, moment)
    assert _route("SOR", moment) == (routed, reason)


@pytest.mark.parametrize("hms, routed, reason", _GRID, ids=[
    f"{h:02d}{m:02d}{s:02d}-{r}" for (h, m, s), r, _ in _GRID
])
def test_r1b_grid_base_nxt(
    monkeypatch: pytest.MonkeyPatch, hms, routed: str, reason: str
) -> None:
    """R1 (RED) — base `NXT` 도 같은 판정. 유지되는 경우의 값만 `NXT` 다."""
    moment = _kst(_REFORM, *hms)
    _pin_boards(monkeypatch, moment)
    expected = "KRX" if routed == "KRX" else "NXT"
    assert _route("NXT", moment) == (expected, reason)


@pytest.mark.parametrize("hms, _routed, _reason", _GRID, ids=[
    f"{h:02d}{m:02d}{s:02d}" for (h, m, s), _, _ in _GRID
])
def test_r1c_base_krx_is_never_rerouted(
    monkeypatch: pytest.MonkeyPatch, hms, _routed, _reason
) -> None:
    """R1 (RED) — base 가 이미 `KRX` 면 시각과 무관하게 `base_krx` 로 즉시 통과.

    라우팅은 `nxt_tradable=False` 다운그레이드(cycle13 Phase G)가 내린 `KRX` 를
    되돌리는 장치가 아니다(R4 와 같은 계약의 순수 함수 쪽 증언).
    """
    moment = _kst(_REFORM, *hms)
    _pin_boards(monkeypatch, moment)
    assert _route("KRX", moment) == ("KRX", "base_krx")


def test_r1d_pre_reform_after_hours_keeps_current_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1 (RED) — **09-14 이전** 16:05 는 현행(base) 유지.

    그 날짜의 KRX 행은 K7(시간외 단일가 `07`) 이고 우리 집합과 교집합이 0 이다.
    NXT N6 는 `00` 을 받는다 ⇒ `krx_unsupported_keep`. 즉 이 커밋을 09-14 **전에**
    배포해도 저녁 청산 경로가 오늘과 같다(날짜 차원이 `market_state` 에 있어 공짜).
    """
    moment = _kst(_PRE_REFORM, 16, 5)
    _pin_boards(monkeypatch, moment)
    assert _route("SOR", moment) == ("SOR", "krx_unsupported_keep")


def test_r1e_sendable_divisions_are_exactly_what_we_can_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1 (RED) — `_SENDABLE_DIVISIONS` == 우리 `OrderDivision` 값 집합.

    판정의 전제가 "우리가 실제로 보낼 수 있는 코드" 라서, enum 과 갈리면 판정이
    조용히 거짓이 된다(예: `41` 을 enum 에 넣고 집합에 안 넣으면 16:00~20:00 이
    `both_unsupported_keep` 으로 떨어져 애프터 청산이 통째로 열리지 않는다).
    """
    from src.engine import order_engine as _oe

    sendable = getattr(_oe, "_SENDABLE_DIVISIONS", None)
    assert sendable is not None, "`_SENDABLE_DIVISIONS` 부재"
    assert set(sendable) == {d.value for d in OrderDivision}, (
        f"집합 {sorted(sendable)} != enum {sorted(d.value for d in OrderDivision)}"
    )


def test_r1f_empty_active_falls_back_to_time_based_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1f (적대 검증 시정 — exit 렌즈 M1 / test 렌즈 M4) — `session_tracker.active`

    가 비어 있어도(기동 직후 첫 `tick()` 전) 08:20~09:00 프리장 창에서는
    `pre_nxt_keep` 이 유지된다. `_pin_boards` 없이(=진짜 빈 캐시) 라우터를
    직접 부른다 — 채워진 캐시를 흉내 내면 이 회귀가 재현되지 않는다.

    이 창에서 `active` 가 비어 있는데 시각 기반 폴백이 없으면 clause 4 가
    실패해 KRX PRE_AUCTION(K1, `("00","01")`) 이 즉시 clause 5 를 성립시켜
    `("KRX", "krx_by_clock")` 로 떨어진다 — 매도 사전 지정가 변환(PR-F 대칭)이
    **같은** `session_tracker.active` 를 읽어 함께 실패하므로 시가 단일가에
    무변환 시장가가 나갈 수 있었다.
    """
    from src.engine.session import session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset())
    moment = _kst(_REFORM, 8, 30)
    assert _route("SOR", moment) == ("SOR", "pre_nxt_keep")


def test_r1g_empty_active_outside_pre_nxt_window_still_routes_by_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1g — 빈 캐시 폴백은 08:20~09:00 창 밖에서는 아무것도 바꾸지 않는다.

    정규장 시각에 캐시가 비어 있어도(예: 재기동 race) 시각 기반 스케줄이
    `PRE_NXT` 를 반환하지 않으므로 clause 5(KRX 정규장)로 정상 진행한다.
    """
    from src.engine.session import session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset())
    moment = _kst(_REFORM, 11, 0)
    assert _route("SOR", moment) == ("KRX", "krx_by_clock")


# ===========================================================================
# R2 — mode 3값 · 키 부재
# ===========================================================================
def test_r2_off_keeps_current_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2 (RED) — `mode="off"` 는 **알려진 작동 상태**(오늘의 SOR 경로)로 되돌린다."""
    moment = _kst(_REFORM, 16, 5)
    _pin_boards(monkeypatch, moment)
    assert _route("SOR", moment, mode="off") == ("SOR", "mode_off")


def test_r2b_sell_only_routes_sell_but_not_buy(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2 (RED) — `sell_only` = 청산만 라우팅(자문 카드 C 선택 ②)."""
    moment = _kst(_REFORM, 11, 0)
    _pin_boards(monkeypatch, moment)
    assert _route("SOR", moment, mode="sell_only", side="sell") == ("KRX", "krx_by_clock")
    assert _route("SOR", moment, mode="sell_only", side="buy") == ("SOR", "mode_sell_only")


def test_r2c_default_mode_is_enforce_and_default_side_is_sell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2 (RED) — 인자 부재 기본값 = `enforce` · `side="sell"`.

    `side` 기본이 `sell` 인 이유 = 청산 경로를 여는 쪽이 안전측이다. `mode` 기본이
    `enforce` 인 이유 = 키 부재가 `off` 면 신규 전략이 키 없이 추가될 때 그 전략만
    다른 거래소로 나가 **전략 간 라우팅이 갈린다**(자문 §5-A).
    """
    moment = _kst(_REFORM, 11, 0)
    _pin_boards(monkeypatch, moment)
    assert _route("SOR", moment) == ("KRX", "krx_by_clock")
    assert _route("SOR", moment, mode="sell_only") == ("KRX", "krx_by_clock")


def test_r2d_unknown_mode_is_treated_as_enforce(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2 (RED) — 미지 mode 문자열은 `enforce` 로 취급(오염 값이 조용히 끄지 않는다)."""
    moment = _kst(_REFORM, 16, 5)
    _pin_boards(monkeypatch, moment)
    assert _route("SOR", moment, mode="qwerty")[0] == "KRX"


@pytest.mark.asyncio
async def test_r2e_mode_is_read_from_strategy_params(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R2 (RED) — 킬스위치는 전략 파라미터 `order_exchange_clock_mode` 로 읽는다.

    ⚠️ 전략 7파일은 이 사이클에서 **diff 0** 이라 `DEFAULT_PARAMS` 에 키가 없다
    (브리프 제약). 따라서 **키 부재 = `enforce`** 가 유일한 운영 기본이고,
    `PUT /api/strategies/{id}/params` 로 `off` 를 넣는 것이 장중 롤백 경로다.
    """
    engine, _ = _make_engine(exchange="SOR", order_exchange_clock_mode="off")
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        got = await engine._strategy_exchange_async(_SID, ticker=None)
    assert got == "SOR", "params 의 `off` 가 무시됐다 — 장중 롤백 경로가 없다"


# ===========================================================================
# R3 — fail-open (주문이 안 나가는 일은 없어야 한다)
# ===========================================================================
def test_r3_probe_error_keeps_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """R3 (RED) — 판정 예외는 `(base, "probe_error")`.

    `reason=probe_error` 가 한 건이라도 뜨면 그날 라우팅이 안 걸린 것이므로
    D+1 판독의 **분모**를 그만큼 깎아야 한다(자문 §7-B F9).
    """
    moment = _kst(_REFORM, 16, 5)
    _pin_boards(monkeypatch, moment)

    import src.engine.market_state as _ms

    def _boom(*a, **k):
        raise RuntimeError("market_state 고장")

    monkeypatch.setattr(_ms, "get_market_state", _boom)
    assert _route("SOR", moment) == ("SOR", "probe_error")


def test_r3b_board_probe_error_keeps_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """R3 (RED) — 보드 조회(`session_tracker.active`) 예외도 fail-open."""
    from src.engine import session as _sess

    moment = _kst(_REFORM, 16, 5)

    class _Boom:
        @property
        def active(self):
            raise RuntimeError("tracker 고장")

    monkeypatch.setattr(_sess, "session_tracker", _Boom())
    assert _route("SOR", moment) == ("SOR", "probe_error")


@pytest.mark.asyncio
async def test_r3c_order_still_goes_out_when_routing_explodes(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R3 (RED) — 라우팅이 터져도 **주문은 나간다**(현행 거래소로).

    fail-safe 방향 = 판정 실패가 주문 자체를 막으면 안 된다(브리프 제약).
    """
    import src.engine.market_state as _ms

    engine, _ = _make_engine(exchange="SOR")
    monkeypatch.setattr(
        _ms, "get_market_state", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert mock_place_order.await_count == 1
    assert mock_place_order.await_args.kwargs["exchange"] == "SOR"


@pytest.mark.asyncio
async def test_r3d_probe_error_is_not_silenced_by_the_base_kept_gate(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R3d (적대 검증 시정 — exit 렌즈 MEDIUM-2 / contract 렌즈 M1) —

    `routed == base` 게이트가 정상 유지 사유(`pre_nxt_keep` 등, `test_r8b`)와
    라우팅 자체가 죽은 `probe_error` 를 구별하지 못하면 D+1 판독의 실패
    서명("`reason=probe_error` 1건 이상")이 원리적으로 관측 불가하다. 이
    사유만 게이트 밖에서 남는다 — `test_r8b` 의 침묵 계약은 무변경이다.
    """
    import src.engine.market_state as _ms

    engine, _ = _make_engine(exchange="SOR")
    monkeypatch.setattr(
        _ms, "get_market_state", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    lines = _marker_lines(caplog, _ROUTE_MARKER)
    assert len(lines) == 1, f"probe_error 가 침묵했다: {lines}"
    assert "reason=probe_error" in lines[0], lines[0]
    assert "base=SOR" in lines[0] and "exchange=SOR" in lines[0], lines[0]


# ===========================================================================
# R4 — nxt_tradable=False 다운그레이드 우선
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("frozen, label", [(_F_0830, "08:30"), (_F_1605, "16:05")])
async def test_r4_downgrade_wins_over_routing(
    monkeypatch: pytest.MonkeyPatch, frozen: str, label: str
) -> None:
    """R4 (RED) — `nxt_tradable=False` 종목은 프리장에서도 `KRX` 다.

    라우팅을 `target_exchange = "NXT"` 로 **못 박으면 안 되는** 이유가 이것이다
    (자문 §0 경고): 현재 보유 4/11 이 `nxt_tradable=False` 이고(003470·003490·
    032820·036540), 그 종목의 프리장 주문을 NXT 로 되돌리면 전멸한다.
    """
    import src.db.stock_master as _sm
    from src.models.stock import StockBasics

    engine, _ = _make_engine(exchange="SOR")
    monkeypatch.setattr(
        _sm,
        "get",
        AsyncMock(
            return_value=StockBasics(
                ticker=_TICKER,
                name="테스트",
                excg_dvsn_cd="01",
                nxt_tradable=False,
                krx_halted=False,
                admin_item=False,
                raw={},
            )
        ),
    )
    monkeypatch.setattr(_sm, "is_stale", AsyncMock(return_value=False))
    with freeze_time(frozen):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        got = await engine._strategy_exchange_async(_SID, ticker=_TICKER)
    assert got == "KRX", f"{label}: 다운그레이드가 라우팅에 의해 되돌려졌다 — {got}"


@pytest.mark.asyncio
async def test_r4b_nxt_tradable_true_still_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """R4 (RED) — `nxt_tradable=True` 종목은 16:05 에 라우팅이 걸린다(KRX)."""
    import src.db.stock_master as _sm
    from src.models.stock import StockBasics

    engine, _ = _make_engine(exchange="SOR")
    monkeypatch.setattr(
        _sm,
        "get",
        AsyncMock(
            return_value=StockBasics(
                ticker=_TICKER, name="테스트", excg_dvsn_cd="01",
                nxt_tradable=True, krx_halted=False, admin_item=False, raw={},
            )
        ),
    )
    monkeypatch.setattr(_sm, "is_stale", AsyncMock(return_value=False))
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        got = await engine._strategy_exchange_async(_SID, ticker=_TICKER)
    assert got == "KRX"


@pytest.mark.asyncio
async def test_r4c_stock_master_miss_still_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R4 (RED) — 캐시 miss(`get` → None) 도 라우팅 대상이다.

    라우팅은 **반환 5곳 전부**를 감싼다(자문 §9-B). miss 경로만 빼면 그 종목의
    16:xx 청산이 조용히 SOR 로 나가 애프터 변환을 못 탄다.
    """
    engine, _ = _make_engine(exchange="SOR")  # `_isolate_db` 가 get → None
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        got = await engine._strategy_exchange_async(_SID, ticker=_TICKER)
    assert got == "KRX"


@pytest.mark.asyncio
async def test_r4d_no_ticker_path_still_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """R4 (RED) — `ticker=None` 조기 반환 경로도 라우팅을 탄다."""
    engine, _ = _make_engine(exchange="SOR")
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        assert await engine._strategy_exchange_async(_SID, ticker=None) == "KRX"


# ===========================================================================
# R5 — 매수 배관 (`:361` → `place_order(exchange=)`)
# ===========================================================================
async def _run_buy(engine, strat, price: int = 10_000) -> None:
    strat.state.cached_buyable_qty = 100
    strat.state.cached_buyable_amount = 10_000_000
    strat.state.cached_buyable_at = _time.time()
    await engine.execute_buy(_TICKER, price, strat)


@pytest.mark.asyncio
async def test_r5_buy_exchange_is_krx_in_main_session(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R5 (RED) — 09:00~15:30 매수는 `EXCG_ID_DVSN_CD=KRX` 로 나간다.

    내부 변수만 보면 배관이 끊겨도 통과하므로 **`place_order` 호출 인자**를 본다.
    """
    engine, strat = _make_engine(exchange="SOR", with_position=False)
    with freeze_time(_F_1100):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await _run_buy(engine, strat)
    assert mock_place_order.await_count == 1
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "KRX", f"매수 거래소가 라우팅되지 않았다 — {kw['exchange']}"
    assert "order_division" not in kw, "정규장 매수는 시장가(생략) 계약이다"


@pytest.mark.asyncio
async def test_r5b_buy_prf_preconvert_unchanged_in_pre_market(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R5 (RED) — 프리장 매수 PR-F 사전 변환 **불변**.

    브리프 제약: "매수 경로는 규칙 1 만 적용된다. `execute_buy` 의 시장가 사전 변환
    (PR-F) 로직 자체는 byte 동일해야 한다." 라우팅이 프리장에서 base 를 유지하므로
    `buy_exchange in ("NXT","SOR")` 조건이 살아 사전 변환이 그대로 발화한다.
    """
    from src.engine.util.tick_size import step_up

    engine, strat = _make_engine(exchange="SOR", with_position=False)
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await _run_buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "SOR", "프리장 매수가 KRX 로 라우팅됐다 — PR-F 가 죽는다"
    assert kw["order_division"] is OrderDivision.LIMIT
    assert kw["price"] == step_up(10_000, steps=5)
    assert _marker_lines(caplog, "[market_order_preconvert_pre_nxt]"), (
        "PR-F 마커가 사라졌다"
    )


@pytest.mark.asyncio
async def test_r5c_buy_prf_survives_the_0850_to_0900_gap(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R5 (RED) — **08:50~09:00** 매수도 PR-F 를 탄다(보드 축을 쓰는 이유).

    `market_state` 의 NXT 는 그 10분을 N2(휴장)로 본다. 라우팅이 그 표를 프리장
    판정에 쓰면 여기서 base 가 KRX 로 떨어지고, `buy_exchange in ("NXT","SOR")` 가
    거짓이 되어 **시가 단일가에 시장가**가 나간다(악화). 그래서 프리장 clause 는
    `session_tracker.active` 를 쓴다 — PR-F 와 같은 출처다(자문 §G).
    """
    engine, strat = _make_engine(exchange="SOR", with_position=False)
    with freeze_time(_F_0852):
        boards = _pin_boards(monkeypatch, datetime.now(KST_TZ))
        assert MarketBoard.PRE_NXT in boards and MarketBoard.MAIN not in boards
        await _run_buy(engine, strat)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "SOR"
    assert kw["order_division"] is OrderDivision.LIMIT


@pytest.mark.asyncio
async def test_r5d_buy_side_is_declared_to_the_router(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R5 (RED) — 매수 호출부는 라우터에 `side="buy"` 를 알린다(`sell_only` 성립 조건).

    `sell_only` 는 매수/매도 축을 구분해야 성립한다. 매수 경로가 `side` 를 넘기지
    않으면 기본값 `sell` 이 적용돼 `sell_only` 가 매수까지 라우팅한다.
    """
    engine, strat = _make_engine(
        exchange="SOR", with_position=False, order_exchange_clock_mode="sell_only"
    )
    with freeze_time(_F_1100):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await _run_buy(engine, strat)
    assert mock_place_order.await_args.kwargs["exchange"] == "SOR", (
        "`sell_only` 인데 매수가 KRX 로 나갔다 — 호출부가 side 를 넘기지 않는다"
    )


# ===========================================================================
# R6 — 매도 배관 (`:666`) + 익일청산/강제청산
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, expected, label",
    [
        (_F_0830, "SOR", "프리장 = 현행"),
        (_F_1100, "KRX", "정규장 = KRX"),
        # cycle295 (B, 2026-09-15) — 15:30~16:00 완전 휴식. 이 행이 배관하던
        # "KRX 미지원 → 현행(SOR) 라우팅" 계약은 `_route_exchange_by_clock`
        # 안에서 여전히 참이다(§2-5 byte 동일 — G-295-C5). 다만 그 값이 실릴
        # 주문 자체가 발사점 게이트(§3-5①)에 걸려 나가지 않는다 — `expected`
        # 를 `None` 으로 표시해 "라우팅 계약이 사라졌다" 가 아니라 "발사가
        # 컷됐다" 임을 드러낸다(§5-5 "정상 파괴 — 기대값 갱신, 삭제 금지").
        (_F_1545, None, "15:45 = cycle295 컷 — 라우팅은 SOR 이지만 발사되지 않는다"),
        (_F_1605, "KRX", "애프터 = KRX"),
    ],
)
async def test_r6_sell_exchange_plumbing(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    frozen: str,
    expected: str | None,
    label: str,
) -> None:
    """R6 (RED) — 매도 `place_order(exchange=)` 가 라우팅 결과를 그대로 싣는다.

    cycle295 (B) 이후 — `expected is None` 인 행은 15:30~16:00 컷 구간이라
    place_order 자체가 나가지 않는다(위 주석).
    """
    engine, _ = _make_engine(exchange="SOR")
    with freeze_time(frozen):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    if expected is None:
        assert mock_place_order.await_count == 0, (
            f"{label} — cycle295 컷 구간인데 주문이 나갔다"
        )
        return
    assert mock_place_order.await_count == 1
    assert mock_place_order.await_args.kwargs["exchange"] == expected, label


@pytest.mark.asyncio
async def test_r6b_next_day_clear_goes_to_krx_market_order(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R6 (RED) — 익일청산(09:00:05 드레인)은 KRX 시장가.

    자문 §4·§I: `_execute_next_day_clear` 는 `place_order` 를 직접 부르지 않고
    `_drain_pending_next_day_clear` → `execute_sell(limit_price 미전달)` 로 흐른다.
    문서의 "09:00 KRX 시장가" 는 오늘은 거짓이다(`nxt_underthreshold` 사유 종목은
    SOR 로 나간다) — 규칙 1 이 그 문장을 **처음으로 참으로** 만든다. `scheduler.py`
    무접촉으로 성립하는 것이 계약이다.
    """
    engine, _ = _make_engine(exchange="SOR")
    with freeze_time(_F_0900_05):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.NEXT_DAY_CLEAR, _SID)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "KRX"
    assert kw["order_division"] is OrderDivision.MARKET
    assert kw["price"] == 0


@pytest.mark.asyncio
async def test_r6c_force_clear_1520_goes_to_krx_market_order(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R6 (RED) — 15:20 강제청산은 KRX 종가 단일가(`00`/`01` 유효) 시장가.

    오늘은 SOR 인데 같은 시각 NXT 는 N4(휴장)라 라우팅이 모호했다 — 규칙 1 이
    그 모호성을 없앤다(자문 §5 = 순수 개선).
    """
    engine, _ = _make_engine(exchange="SOR")
    with freeze_time(_F_1520):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.FORCE_CLEAR, _SID)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == "KRX"
    assert kw["order_division"] is OrderDivision.MARKET


# ===========================================================================
# R7 — `limit_price > 0` 지정가 매도 분기
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, expected", [(_F_0830, "NXT"), (_F_1100, "KRX"), (_F_1605, "KRX")]
)
async def test_r7_limit_price_branch_is_routed_too(
    monkeypatch: pytest.MonkeyPatch,
    mock_place_order: AsyncMock,
    frozen: str,
    expected: str,
) -> None:
    """R7 (RED) — `limit_price > 0 → target_exchange = "NXT"` 하드코딩도 라우팅을 탄다.

    호출자가 현재 0곳(dead)이지만 `test_cycle100_strategy_exchange_persistence_sell.py`
    가 그 소스 문자열을 영속 단정하므로 **지우지 않고** 결과에 라우팅을 씌운다.
    안 하면 누가 `limit_price` 를 쓰기 시작하는 날 규칙 1 이 조용히 샌다(자문 §4-I).
    """
    engine, _ = _make_engine(exchange="SOR")
    with freeze_time(frozen):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID, limit_price=9_500)
    kw = mock_place_order.await_args.kwargs
    assert kw["exchange"] == expected
    assert kw["order_division"] is OrderDivision.LIMIT
    assert kw["price"] == 9_500


# ===========================================================================
# R8 — 관측 마커
# ===========================================================================
@pytest.mark.asyncio
async def test_r8_marker_emitted_when_base_differs(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R8 (RED) — `[order_channel]` 1행 + 필수 필드.

    운영자는 화면에서 `SOR` 을 보면서 `KRX` 로 나가는 주문을 갖게 된다(자문 §4-E).
    이 마커가 그 불일치를 매일 남기는 **유일한 분모**다.
    """
    engine, _ = _make_engine(exchange="SOR")
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    lines = _marker_lines(caplog, _ROUTE_MARKER)
    assert len(lines) == 1, f"마커 {len(lines)}행 — 1행이어야 한다: {lines}"
    for field in ("side=", "ticker=", "strategy=", "base=SOR", "exchange=KRX",
                  "reason=krx_by_clock"):
        assert field in lines[0], f"필드 `{field}` 누락: {lines[0]}"


@pytest.mark.asyncio
async def test_r8b_marker_silent_when_base_kept(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R8 (RED) — `base == routed` 면 마커 0행(정규장 매수·매도 폭주 차단)."""
    engine, _ = _make_engine(exchange="SOR")
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert _marker_lines(caplog, _ROUTE_MARKER) == []


@pytest.mark.asyncio
async def test_r8c_marker_is_capped_per_ticker_side_reason_per_day(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R8 (RED) — 같은 (ticker, side, reason) 은 하루 1행.

    16:00~20:00 을 초당 1틱으로 잡으면 cap 없이는 ≈14,000행이다.
    """
    engine, strat = _make_engine(exchange="SOR")
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        for _ in range(3):
            engine._selling.discard(_TICKER)
            engine._sell_rejection.reset_daily()
            strat.state.positions.setdefault(
                _TICKER,
                Position(
                    ticker=_TICKER, buy_price=10_000, quantity=3, order_no="O",
                    strategy_id=_SID, buy_date=date(2026, 9, 11),
                ),
            )
            await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert len(_marker_lines(caplog, _ROUTE_MARKER)) == 1


@pytest.mark.asyncio
async def test_r8d_config_marker_is_emitted_once_per_strategy_per_day(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R8 (RED) — `[order_channel_config]` 카나리아 1행/(전략, 값 조합)/일.

    D+1 판독 층1-8 = "라우팅이 켜졌는가" 를 한 줄로 확인하는 채널. 자문 §S6 서식은
    `strategy=`/`mode=`/`division=` 3필드다(cycle245 `[ratio_cap_config]` 관례).
    """
    engine, strat = _make_engine(exchange="SOR")
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        for _ in range(2):
            engine._selling.discard(_TICKER)
            engine._sell_rejection.reset_daily()
            strat.state.positions.setdefault(
                _TICKER,
                Position(
                    ticker=_TICKER, buy_price=10_000, quantity=3, order_no="O",
                    strategy_id=_SID, buy_date=date(2026, 9, 11),
                ),
            )
            await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    lines = _marker_lines(caplog, _CONFIG_MARKER)
    assert len(lines) == 1, f"카나리아 {len(lines)}행: {lines}"
    for field in ("strategy=", "mode=enforce", "division=44"):
        assert field in lines[0], f"필드 `{field}` 누락: {lines[0]}"


# ===========================================================================
# R9 — cycle286 불변 + `_selling`/positions 계약
# ===========================================================================
@pytest.mark.asyncio
async def test_r9_cycle286_pre_window_write_is_preserved(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R9 (RED) — 08:30 프리장 거부는 여전히 `wrote=1 reason=nxt_pre_window`.

    라우팅이 프리장에서 base 를 유지하므로 cycle286 의 `_exchange_ok` 가 참인
    **유일한 창**이 그대로 보존된다 = 판정 불변(자문 §4-I · §7-B F5).
    """
    import src.db.stock_master as _sm

    engine, _ = _make_engine(exchange="SOR")
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    mock_place_order.side_effect = [_closed_err()]
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    lines = _marker_lines(caplog, "[nxt_post_reinforce]")
    assert lines and "wrote=1" in lines[0] and "reason=nxt_pre_window" in lines[0], lines
    assert _sm.upsert_one.await_count == 1


@pytest.mark.asyncio
async def test_r9b_cycle286_after_market_rejection_never_writes(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock, caplog
) -> None:
    """R9 (RED) — 16:05 거부는 `wrote=0` 이고 `reason` 에 `exchange` 가 들어간다.

    라우팅으로 `target_exchange` 가 KRX 가 되면 `_exchange_ok` 가 항상 거짓이다 —
    이는 cycle286 을 되돌리는 것이 아니라 그 조건의 mandate("KRX 로 보낸 주문의
    거부는 NXT 가용성의 증거가 0")를 **더 엄격히** 만족시키는 것이다.
    `reason` 은 복합값 `exchange+window` 이므로 기존 부분일치 판독과 호환된다.
    ⚠️ D+1 에 `reason=` 분포는 09-14 전후로 `window` → `exchange+window` 로 바뀐다
    (합산 금지).
    """
    import src.db.stock_master as _sm

    engine, _ = _make_engine(exchange="SOR")
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    mock_place_order.side_effect = [_closed_err()]
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    lines = _marker_lines(caplog, "[nxt_post_reinforce]")
    assert lines, "cycle286 마커가 사라졌다"
    # `reason=exchange` 로 단정한다 — `"exchange" in line` 은 `exchange=SOR` 필드에
    # 걸려 **오늘도 통과**하는 공허한 단정이다(복합값 앞자리가 항상 `exchange` 다).
    assert "wrote=0" in lines[0] and "reason=exchange" in lines[0], lines[0]
    assert _sm.upsert_one.await_count == 0


@pytest.mark.asyncio
async def test_r9c_selling_discard_and_positions_preserved_on_closed_rejection(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R9 (RED) — `_selling` discard + positions 보존 계약 불변(16:05).

    `_selling` 을 보존하면 그게 곧 stale `_selling` 좀비 = 손절 마비다
    (루트 CLAUDE.md 핵심 안전 규칙).
    """
    engine, strat = _make_engine(exchange="SOR")
    mock_place_order.side_effect = [_closed_err()]
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert _TICKER not in engine._selling
    assert _TICKER in strat.state.positions


@pytest.mark.asyncio
async def test_r9d_routing_does_not_add_await_before_pending_buys_add(
    monkeypatch: pytest.MonkeyPatch, mock_place_order: AsyncMock
) -> None:
    """R9 (RED) — A-ATOMIC 보존: 매수 라우팅은 `pending_buys.add` **뒤**에서만 일어난다.

    `calc_buy_quantity` ~ `pending_buys.add` 구간 `await` 0건이 예산 클램프 원자성의
    전제다(AST 가드 A-ATOMIC). 라우팅을 `_strategy_exchange_async` 안에 두면 호출
    지점이 `:361` 그대로라 이 구간이 byte 동일이다 — 여기서는 **행위**로 확인한다:
    라우팅이 예산 관문 결과를 바꾸지 않는다.
    """
    engine, strat = _make_engine(exchange="SOR", with_position=False)
    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, datetime.now(KST_TZ))
        await _run_buy(engine, strat)
    assert _TICKER in strat.state.pending_buys
    assert strat.state.pending_buy_amounts[_TICKER] == 10_000 * 1
