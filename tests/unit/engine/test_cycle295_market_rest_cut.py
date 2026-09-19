"""cycle295 Red (B) — 15:30~16:00 **완전 휴식**: 주문을 보내지 않는다.

정본 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §3 · §4 · §5-2 · §9.
접촉 허용 프로덕션 파일 = `src/engine/order_engine.py` **하나**(8영역, 사용자 승인
2026-09-15). `scheduler.py` 무접촉, 나머지 8영역 4파일·전략 7파일·`strategy_base`
diff 0, `DEFAULT_PARAMS` 키 신설 0.

═══════════════════════════════════════════════════════════════════════════
🔴 되돌리기 전에 읽어라 — 이 컷은 «결함» 이 아니라 «결정» 이다 (§5-6)
═══════════════════════════════════════════════════════════════════════════

(가) **사실** — 15:40~16:00 은 KRX 에 연속 체결이 없고 NXT 애프터만 continuous 다
     (`market_state.MARKET_TABLE` 파생. 감시자 = `test_cycle294b::test_n1`).
(나) **cycle294 의 판단** — 따라서 그 구간을 KRX 채널로 덮으면 `nxt_true` 보유의
     손절 커버리지가 매일 20분 사라진다. **이 문장은 여전히 참이다.**
(다) **2026-09-15 사용자 결정** — "청산측으로도 참여를 하지 않고자 해.
     15:30~16:00 은 완전 휴식하도록 변경해야해." 그 20분의 커버리지 손실을
     **비용으로 수용**했다(§4: 청산 가능 시간의 3.0%, 알려진 실체결 표본 1건,
     16:00 KRX 애프터 재개까지 최대 20분 **유예**).

⇒ **이 파일의 테스트가 붉어졌다면 기대값을 고치기 전에** 먼저
`_workspace/00_URGENT_WORKLIST.md` 의 2026-09-15 결정을 확인하라.
**표가 바뀌어서인지 결정이 바뀌어서인지를 가르기 전에는 기대값을 고치지 마라.**
표가 바뀌어(KRX 가 15:40~16:00 에 연속체결을 갖게 되어) 붉어진 것이라면 그때
해야 할 일은 「컷 제거」가 아니라 「컷 재검토」다.

═══════════════════════════════════════════════════════════════════════════
설계 — 왜 라우터 **밖** 순수 술어인가 (§3-2, 실행값 반증)
═══════════════════════════════════════════════════════════════════════════

초안은 `_route_exchange_by_clock` 의 clause 5·6 **사이**에 컷 clause 를 넣자고
했다. 실매도 경로 `_strategy_exchange_async` 는 `_probe_nxt_downgrade_base` 를
**먼저** 부르고, 그 함수는 `stock_master.nxt_tradable=False` 종목에 `"KRX"` 를
돌려준다. 그 코호트는 라우터에 `base="KRX"` 로 들어가 **clause 1 `base_krx` 에서
즉시 반환**되어 clause 5·6·7 어디에도 닿지 않는다. `nxt_false` 는 마스터의
**83.2%** — 즉 컷이 가장 필요한 다수 코호트가 컷을 통째로 비껴간다(T6 가 봉인).

⇒ 채택 = 라우터 무접촉 + 같은 출처(`market_state`)를 읽는 **별도 순수 술어**
`_market_rest_now(now) -> (blocked, reason)` 를 **주문 발사점**에만 건다.
base·side·mode 와 무관하다 — 창은 시계의 성질이지 방향·거래소·다이얼의 성질이
아니다(T6·T7).

═══════════════════════════════════════════════════════════════════════════
테스트 표 (§5-2)
═══════════════════════════════════════════════════════════════════════════

| # | 내용 |
|---|---|
| T1·T2 | 15:30·15:35·15:45·15:55·15:59:59 → `(True, "market_rest")` |
| T3 | 15:29:59·16:00·16:05·19:00·10:00 → `(False, "krx_sendable")` — 과잉 차단 금지 |
| T4 🔴 | 08:00·08:05·08:30·08:45·**08:55** → `(False, "pre_nxt_keep")` |
| T5 | 02:00·07:59·20:00·22:00 → `(False, "no_session")` — 야간 안전망 보존 |
| T5b | 1분 스윕 1,440 × 4날짜 — 컷은 **정확히 [15:30, 16:00)** |
| T5c | 판정 예외 → `(False, "probe_error")` fail-open |
| T5d | 보드 출처 동치 — 캐시 핀 ↔ `boards_at` 폴백이 같은 답 |
| T6 🔴 | `nxt_tradable=False`(base=KRX) 코호트도 컷 — §3-2 구멍 부재 |
| T7 | `order_exchange_clock_mode` 3값 × side 2값 = 6조합 전부 컷 |
| T8 🔴 | `execute_sell` 컷 계약 5종(주문 0 · `_selling` 해제 · 포지션 보존 · TTL 미등록 · 익일청산 미전환) |
| T9 | 순수 취소 2경로는 **무접촉** |
| T10 🔴 | `_cancel_and_reorder` **쌍 게이트** — 취소도 재주문도 0 |
| T11 🔴 | 15:45 컷 → 16:05 재발사(회복 경로 실증) |
| T12 | 컷 창 길이 ≤ 30분 ∧ 시작 = KRX 미지원 전이 시각(표 파생) |
| T13 | `[market_rest_blocked]` 1회/(ticker,side)/일 |
| T14~T14e 🔴 | Q2 현실 관측 fail-open **철회** — 라이브 틱(나이 0.0s)에도 컷 유지 |
| T17·T17b | 관측 헬퍼 never-raise — 카나리아가 터져도 컷 판정 불변 |
| T15 | Q5 `execute_buy` 대칭 컷 (`get_buyable` 미호출 = 게이트 자리 증언) |
| T16 | `[market_rest_window]` 카나리아 1회/일 |

═══════════════════════════════════════════════════════════════════════════
freezegun 과 타임존 (cycle286/287 헤더 규약 답습)
═══════════════════════════════════════════════════════════════════════════

`order_engine` 은 `datetime.now(_KST_TZ)`(tz-aware) 로 판정한다. freezegun 은
naive 문자열을 **UTC** 로 동결하므로 이 파일의 `freeze_time` 인자는 전부 UTC 이고
KST = UTC + 9h 다. 순수 함수 격자는 `now=` 를 **명시 전달**해 시계와 완전히
분리한다 — 그쪽이 TZ 독립의 유일한 확실한 방법이고, 배관 테스트만 freezegun 으로
창 안·밖을 고정한다.

🔴 **모든 날짜는 2026-09-14 이상으로 pin 한다.** K6(KRX 애프터마켓)의
`effective_from=2026-09-14` 때문에 그 이전 날짜에서는 컷 창이 15:30~**20:00**
(4시간 30분)으로 벌어진다(§3-4 실측). T12b 가 그 사실 자체를 대조군으로 남긴다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import _SENDABLE_DIVISIONS, OrderEngine
from src.engine.session import MarketBoard, boards_at
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry

pytestmark = [
    pytest.mark.unit,
    # 🔴 cycle317 의 휴식 컷 중립화 픽스처를 **옵트아웃**한다.
    # 이 파일이 검증하는 것이 바로 그 컷이라, 중립화되면 전부 공허하게 통과한다.
    pytest.mark.real_market_rest,
]

KST_TZ = timezone(timedelta(hours=9))
_OE_LOGGER = "src.engine.order_engine"
_BLOCKED = "[market_rest_blocked]"
_WINDOW = "[market_rest_window]"
_MISMATCH = "[market_rest_reality_mismatch]"
_TICKER = "161580"
_TICKER2 = "000815"
_SID = "long_tail_volatility"

#: 🔴 K6(KRX 애프터마켓 16:00~20:00) 발효일. 이 날짜 **이상**으로만 pin 한다.
_REFORM = date(2026, 9, 14)
_DAY = date(2026, 9, 15)
#: K6 **미적용** 날짜 — T12b 대조군 전용(컷이 4시간 30분으로 벌어지는 것을 보인다).
_PRE_REFORM = date(2026, 9, 11)


def _kst(d: date, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=KST_TZ)


# ── freezegun 용 UTC 리터럴 ↔ KST (= UTC + 9h) ─────────────────────────────
_F_1100 = "2026-09-15 02:00:00"     # KST 2026-09-15 11:00:00 (KRX 정규장)
_F_1525 = "2026-09-15 06:25:00"     # KST 15:25:00 (컷 직전)
_F_1545 = "2026-09-15 06:45:00"     # KST 15:45:00 (컷 한가운데)
_F_1545_30 = "2026-09-15 06:45:30"  # KST 15:45:30 (부분체결 30초 뒤)
_F_1605 = "2026-09-15 07:05:00"     # KST 16:05:00 (KRX 애프터 — 회복)
_F_0830 = "2026-09-14 23:30:00"     # KST 2026-09-15 08:30:00 (NXT 프리장)


# ═══════════════════════════ 리그 ══════════════════════════════════════════
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


def _make_engine(*, with_position: bool = True, tickers=(_TICKER,), **params):
    reg = StrategyRegistry()
    strat = _DummyStrategy(**params)
    if with_position:
        for tk in tickers:
            strat.state.positions[tk] = Position(
                ticker=tk,
                buy_price=10_000,
                quantity=3,
                order_no=f"ORDER-PRE-{tk}",
                strategy_id=_SID,
                buy_date=date(2026, 9, 11),
            )
    reg.register(strat)
    eng = OrderEngine(reg)
    return eng, strat


@pytest.fixture
def engine_pair():
    return _make_engine()


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = SimpleNamespace(
        order_no="ORD-NEW", order_time="154500", krx_org_no="",
    )
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture
def mock_cancel_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "cancel_order", mock)
    return mock


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    """DB·LLM·시세 캐시·보드 캐시 격리 — 컷 판정과 무관한 I/O 를 전부 잘라낸다."""
    import src.engine.order_engine as _oe
    import src.db.stock_master as _sm
    import src.engine.scanner as _scanner
    from src.engine.session import session_tracker

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: None)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    # 부분체결 대기 30초 — 테스트에서는 0 (행위 분기 무관)
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    # `ticker_last_tick` 은 모듈 전역 dict 다. 종전 Q2 현실 관측의 입력이었고
    # 지금은 컷 게이트가 **읽지 않는다**(T14c 가 구조로 봉인). 다른 테스트의
    # 잔재가 판정에 섞이지 않도록 매 테스트 비우되, **라이브처럼 채워진 상태**는
    # T14·T14b·T14e 가 자기 안에서 직접 만든다(비우기만 하면 결함이 숨는다).
    monkeypatch.setattr(_scanner, "ticker_last_tick", {})
    monkeypatch.setattr(_scanner, "ticker_prices", {})
    # 보드 캐시 — 기본은 **빈 집합**(= `boards_at` 폴백 경로). T5d 가 두 경로의
    # 동치를 따로 잰다.
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return None


def _pin_boards(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> frozenset:
    """`session_tracker.active` 를 그 시각의 **fresh** 보드 집합으로 고정.

    컷의 프리장 예외는 라우터 clause 4 · 매도 프리장 사전 지정가 변환과
    **같은 출처**를 읽어야 셋이 갈라지지 않는다(§3-3 근거 3).
    """
    from src.engine.session import session_tracker

    boards = boards_at(moment.time())
    monkeypatch.setattr(session_tracker, "_active", boards)
    return boards


def _rest(moment: datetime):
    """`_market_rest_now(now)` 호출 — 부재 시 의도를 담아 FAIL(SKIP 금지)."""
    from src.engine import order_engine as _oe

    fn = getattr(_oe, "_market_rest_now", None)
    assert fn is not None, (
        "`order_engine._market_rest_now` 부재 — cycle295 §3-3 의 순수 술어가 "
        "아직 없다. 라우터(`_route_exchange_by_clock`) 안에 넣으면 안 된다(§3-2)"
    )
    return fn(moment)


def _lines(caplog, marker: str) -> list[str]:
    """레벨(INFO 이상) + 로거 + prefix 3중 한정.

    CI 루트 로거는 DEBUG 라 실패 흔적 debug 행까지 잡힌다(메모리
    「CI 환경 차이 교훈 2건」) — 개수 단언에는 반드시 이 헬퍼를 쓴다.
    """
    out = []
    for r in caplog.records:
        if r.name != _OE_LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg.startswith(marker):
            out.append(msg)
    return out


def _critical_lines(caplog, marker: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER
        and r.levelno >= logging.CRITICAL
        and r.getMessage().startswith(marker)
    ]


# ═══════════════════════════ T1~T5 — 순수 술어 ══════════════════════════════
@pytest.mark.parametrize("hms", [(15, 30, 0), (15, 35, 0), (15, 45, 0), (15, 55, 0), (15, 59, 59)])
def test_t1_t2_inside_the_rest_window_is_blocked(hms) -> None:
    """T1·T2 — 15:30~16:00 은 **완전 휴식**이다(사용자 결정 2026-09-15).

    ⚠️ 15:30~15:40 과 15:40~16:00 은 원인이 다르다. 앞 10분은 KRX `06`(장후
    시간외 종가) · NXT `()` 라 **둘 다** 우리 호가유형을 안 받고, 뒤 20분은
    KRX 는 안 받지만 NXT N6 가 `00` 을 받는다. 종전에는 앞 10분이 "나가서
    거부되는" 구간(그 거부가 다음-09:00 TTL 래치를 걸어 16:00~20:00 KRX 애프터
    청산 4시간을 통째로 잠글 수 있었다)이었고 뒤 20분이 "NXT 로 체결되는"
    구간이었다. 컷은 **둘을 같은 규칙 하나로** 덮는다.
    """
    assert _rest(_kst(_DAY, *hms)) == (True, "market_rest")


@pytest.mark.parametrize("hms", [(9, 0, 0), (10, 0, 0), (15, 19, 59), (15, 29, 59),
                                 (16, 0, 0), (16, 5, 0), (19, 0, 0), (19, 59, 59)])
def test_t3_normal_trading_hours_are_never_blocked(hms) -> None:
    """🔴 T3 (과잉 차단 금지) — 정규장·KRX 애프터는 **한 순간도** 막히지 않는다.

    이 단언이 없으면 "전부 막는" 퇴화 구현이 T1/T2 를 통과한다. 16:00 정각이
    통과해야 §3-5 의 회복 경로(= 컷은 취소가 아니라 최대 20분 **유예**)가
    성립한다.
    """
    blocked, reason = _rest(_kst(_DAY, *hms))
    assert blocked is False, f"{hms} 가 차단됐다 — 과잉 차단(reason={reason})"
    assert reason == "krx_sendable", (
        f"{hms} reason={reason} — 그 시각 KRX 는 우리 호가유형을 받는다(§3-4 세그먼트)"
    )


@pytest.mark.parametrize("hms", [(8, 0, 0), (8, 5, 0), (8, 30, 0), (8, 45, 0),
                                 (8, 55, 0), (8, 59, 59)])
def test_t4_pre_market_is_exempt_by_board_not_by_nxt_phase(hms) -> None:
    """🔴 T4 (§3-3 근거 3 · 과잉 차단 방지의 핵심 봉인) — 프리장은 예외다.

    **08:55 가 이 테스트의 심장이다.** 08:50~09:00 은 NXT 가 N2(휴장)라
    `market_state` 의 NXT phase 로 판정하면 컷이 발화한다. 그러나 보드는 아직
    PRE_NXT 이고(`session.py` 의 `_BOARD_SCHEDULE`), 라우터 clause 4 와 매도
    프리장 사전 지정가 변환(PR-F 대칭)이 **둘 다** `session_tracker.active` 를
    읽는다. 판정 출처가 셋으로 갈리면 그 10분에 LTV 청산이 조용히 죽는다.
    """
    blocked, reason = _rest(_kst(_DAY, *hms))
    assert blocked is False, f"프리장 {hms} 가 차단됐다 — 과잉 차단(reason={reason})"
    assert reason == "pre_nxt_keep", (
        f"프리장 {hms} reason={reason} — 보드(`PRE_NXT ∈ active ∧ MAIN ∉ active`) "
        "판정이어야 한다. `market_state` 의 NXT phase 로 판정하면 08:50~09:00 이 갈린다"
    )


@pytest.mark.parametrize("hms", [(0, 0, 0), (2, 0, 0), (7, 59, 59), (20, 0, 0),
                                 (22, 0, 0), (23, 59, 59)])
def test_t5_night_keeps_the_existing_verified_safety_net(hms) -> None:
    """T5 (§3-3 근거 4) — 야간은 컷하지 않는다. **현행 안전망을 보존**한다.

    00:00~08:00 · 20:00~24:00 의 현행 동작(주문 발사 → APBK0918 →
    `is_market_closed_rejection` → 포지션 보존 + `_pending_next_day_clear`
    전환)은 이미 검증된 경로다. 컷으로 덮으면 익일청산 전환이라는 **다른**
    안전망을 이 사이클이 조용히 끈다.

    ⚠️ 15:30~15:40 은 KRX `order_divisions=('06',)` 가 비지 않아 이 야간 가드를
    **통과하고** 컷에 걸린다 — 시각 리터럴 없이 두 구간이 갈리는 지점이다.
    """
    blocked, reason = _rest(_kst(_DAY, *hms))
    assert blocked is False, f"야간 {hms} 가 차단됐다 — 현행 안전망을 덮으면 안 된다"
    assert reason == "no_session", f"야간 {hms} reason={reason} — 'no_session' 이어야 한다"


@pytest.mark.parametrize("d", [date(2026, 9, 14), date(2026, 9, 15),
                               date(2026, 9, 16), date(2026, 11, 19)])
def test_t5b_minute_sweep_blocks_exactly_one_contiguous_window(d: date) -> None:
    """T5b — 1,440분 전수 스윕. 컷은 **정확히 [15:30, 16:00)** 하나다.

    세그먼트 단언은 "구멍이 없다(연속)" + "군더더기가 없다(1개)" 를 동시에
    잰다. 날짜는 전부 K6 발효일(2026-09-14) 이상으로 pin 했다.
    """
    blocked_minutes = [
        m for m in range(1440)
        if _rest(datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=KST_TZ))[0]
    ]
    assert blocked_minutes, f"{d} 에 컷 구간이 없다 — 컷이 아예 발화하지 않는다"
    start, end = blocked_minutes[0], blocked_minutes[-1]
    assert blocked_minutes == list(range(start, end + 1)), (
        f"{d} 컷 구간이 연속이 아니다 — {blocked_minutes}"
    )
    assert (start // 60, start % 60) == (15, 30), (
        f"{d} 컷 시작이 {start//60:02d}:{start%60:02d} — 15:30 이어야 한다"
    )
    assert (end // 60, end % 60) == (15, 59), (
        f"{d} 컷 끝이 {end//60:02d}:{end%60:02d} — 16:00 직전(15:59)이어야 한다"
    )


def test_t5c_predicate_fails_open_on_probe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """T5c (§3-3 근거 6 · M15) — 판정 예외는 **fail-open** 이다.

    fail-closed(예외 → 차단)는 P0-1 유령 키가 두 전략을 전 기간 체결 0건으로
    만든 바로 그 방향이다. 컷은 매매를 줄이는 통제라 판정이 죽었을 때
    "아무것도 못 보내는" 상태가 되면 손절이 통째로 무음이 된다.
    """
    import src.engine.market_state as _ms

    def _boom(*a, **kw):
        raise RuntimeError("표 조회 실패")

    monkeypatch.setattr(_ms, "get_market_state", _boom)
    assert _rest(_kst(_DAY, 15, 45)) == (False, "probe_error")


@pytest.mark.parametrize("hms", [(8, 55, 0), (11, 0, 0), (15, 35, 0), (15, 45, 0),
                                 (16, 5, 0), (22, 0, 0)])
def test_t5d_board_source_cache_and_fallback_agree(
    monkeypatch: pytest.MonkeyPatch, hms
) -> None:
    """🔵 T5d (양성 대조군) — 보드 캐시가 차 있든 비었든 **같은 답**이다.

    `session_tracker.active` 는 30초 주기 tick 이 채우는 캐시라 기동 직후
    첫 tick 전에는 빈 집합이다(라우터 clause 4 의 cycle287 적대 검증 시정).
    컷이 캐시만 읽으면 그 순간 프리장 예외가 죽고, `boards_at` 만 읽으면
    라우터와 출처가 갈린다. 둘 다 같아야 한다.
    """
    moment = _kst(_DAY, *hms)
    fallback = _rest(moment)             # 캐시 빈 상태(autouse 픽스처 기본)
    _pin_boards(monkeypatch, moment)
    pinned = _rest(moment)
    assert fallback == pinned, (
        f"{hms} — 캐시 폴백={fallback} ≠ 캐시 핀={pinned}. 컷은 "
        "`session_tracker.active or boards_at(now.time())` 한 출처로 판정하라"
    )


# ═══════════════════════════ T6 — §3-2 구멍 부재 ═══════════════════════════
@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t6_krx_downgraded_cohort_is_cut_too(
    engine_pair, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 T6 (§3-2 결정적 반증 봉인) — `nxt_tradable=False` 코호트도 컷된다.

    이 코호트는 `_probe_nxt_downgrade_base` 가 `base="KRX"` 로 만들어 라우터
    clause 1(`base_krx`)에서 즉시 반환된다 — 라우터 안에 컷을 넣었다면 마스터의
    **83.2%** 가 컷을 비껴간다. 컷이 라우터 밖에 있다는 것의 유일한 행위 증언이다.

    같은 순간 라우터는 여전히 `("KRX", "base_krx")` 를 돌려줘야 한다
    (`_route_exchange_by_clock` byte 동일 — AST 가드 C5 와 짝).
    """
    import src.db.stock_master as _sm
    from src.engine import order_engine as _oe

    engine, strat = engine_pair
    monkeypatch.setattr(
        _sm, "get", AsyncMock(return_value=SimpleNamespace(nxt_tradable=False)),
    )
    moment = _kst(_DAY, 15, 45)
    _pin_boards(monkeypatch, moment)

    assert _oe._route_exchange_by_clock("KRX", side="sell", now=moment) == (
        "KRX", "base_krx",
    ), "라우터가 바뀌었다 — §2-5 는 `_route_exchange_by_clock` byte 동일을 선언했다"

    await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)

    assert mock_place_order.await_count == 0, (
        "KRX 다운그레이드 코호트에 주문이 나갔다 — 컷을 라우터 clause 로 넣으면 "
        "정확히 이렇게 샌다(§3-2). 발사점 술어로 옮겨라"
    )
    assert strat.state.positions.get(_TICKER) is not None


# ═══════════════════════════ T7 — 다이얼 무종속 ════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "sell_only", "off"])
@freeze_time(_F_1545)
async def test_t7_cut_is_independent_of_the_rollback_dial_sell(
    mode: str, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T7 (§9-Q1 권고 = 무종속 · M5) — 롤백 다이얼이 컷을 품지 않는다.

    `order_exchange_clock_mode` 는 cycle287 의 라우팅 킬스위치다. 컷을 그
    다이얼 **뒤**에 두면 `mode="off"` 한 번으로 방금 없앤 참여가 조용히
    되살아난다 — 사용자가 없애자고 한 것이 다이얼인데 다이얼 하나가 결정을
    뒤집으면 자기모순이다.

    ⚠️ 대가는 명시적이다 — **장중 킬스위치가 없다**(롤백 수단은 1커밋 revert).
    cycle287 이 이미 같은 제약을 안고 착지했다.
    """
    engine, strat = _make_engine(order_exchange_clock_mode=mode)
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))
    await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert mock_place_order.await_count == 0, (
        f"mode={mode} 에서 주문이 나갔다 — 컷은 다이얼 판정 **앞**이어야 한다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "sell_only", "off"])
@freeze_time(_F_1545)
async def test_t7b_cut_is_independent_of_the_rollback_dial_buy(
    mode: str, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T7 (매수 축) — 같은 계약이 `execute_buy` 에도 성립한다."""
    engine, strat = _make_engine(
        with_position=False, order_exchange_clock_mode=mode,
    )
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))
    await engine.execute_buy(_TICKER, 10_000, strat)
    assert mock_place_order.await_count == 0, (
        f"mode={mode} 매수에 주문이 나갔다 — 컷은 다이얼과 무관해야 한다"
    )


# ═══════════════════════════ T8 — execute_sell 계약 ════════════════════════
@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t8_execute_sell_cut_contract(
    engine_pair, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔴 T8 (§3-5 ①) — 컷의 다섯 계약. **하지 말아야 할 것 4**가 여기 있다.

    ① 주문 0건 — "보내고 거부받기" 로 구현하면 ②③이 뒤집힌다(M7).
    ② `_selling` **해제** — 유지하면 그것이 곧 stale `_selling` 좀비(= 손절 마비).
       09-08 필옵틱스(161580)가 6시간 45분 26초 잠겼던 그 기전이다.
    ③ `SellRejectionTracker` **미등록** — **거부가 없었다.** 등록하면 15:3x 한 건이
       그 종목의 16:00~20:00 KRX 애프터 청산 4시간을 통째로 잠근다(§4-1).
    ④ `_pending_next_day_clear` **미전환** — 16:00 KRX 애프터가 열리므로 익일까지
       미룰 이유가 없다. 컷은 취소가 아니라 **최대 20분 유예**다.
    ⑤ 포지션·`high_since_buy` 보존.
    """
    engine, strat = engine_pair
    pending: set = set()
    engine._pending_next_day_clear_provider = lambda: pending
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))
    pos_before = strat.state.positions[_TICKER]
    high_before = pos_before.high_since_buy

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)

    # ① 주문 0건
    assert mock_place_order.await_count == 0, "컷 구간에 매도 주문이 나갔다"
    # ② _selling 해제 — 좀비 금지
    assert _TICKER not in engine._selling, (
        "`_selling` 이 남았다 — 그 자체가 stale `_selling` 좀비(손절 마비)다(§3-5)"
    )
    assert _TICKER not in engine._selling_since, "`_selling_since` 잔재"
    # ③ 거부 TTL 미등록 — 16:05 에 다시 열려 있어야 한다
    assert engine._sell_rejection.is_blocked(_TICKER, _kst(_DAY, 16, 5)) is False, (
        "컷이 `SellRejectionTracker` 를 등록했다 — **거부가 없었다**. 등록하면 "
        "다음-09:00 TTL 이 KRX 애프터 4시간을 잠근다(§4-1)"
    )
    # ④ 익일청산 미전환
    assert pending == set(), (
        "`_pending_next_day_clear` 로 전환했다 — 16:00 KRX 애프터가 열리므로 "
        "익일까지 미룰 이유가 없다(§3-5)"
    )
    # ⑤ 포지션 보존
    assert strat.state.positions.get(_TICKER) is pos_before
    assert strat.state.positions[_TICKER].high_since_buy == high_before

    # 관측 — 이 사이클이 무엇을 잃는지의 **유일한 분모**
    lines = _lines(caplog, _BLOCKED)
    assert len(lines) == 1, f"`{_BLOCKED}` 가 {len(lines)}행 — 1행이어야 한다"
    assert "side=sell" in lines[0] and f"ticker={_TICKER}" in lines[0], lines[0]
    assert f"strategy={_SID}" in lines[0], lines[0]
    # 적대 검증 시정(MEDIUM) — `base=` 없이는 `nxt_tradable=False` 코호트가 실제로
    # 컷에 걸렸는지(§3-2 구멍 부재의 라이브 증거)를 로그만으로 확인할 수 없다.
    assert "base=" in lines[0], (
        f"`{_BLOCKED}` 에 `base=` 가 없다 — §3-6 이 선언한 마커 형식이다: {lines[0]}"
    )
    assert "base=None" not in lines[0] and "base= " not in lines[0], lines[0]


# ═══════════════════════════ T9 · T10 — 취소 3경로 ═════════════════════════
@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t9_pure_cancel_paths_are_untouched(
    engine_pair, mock_cancel_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔵 T9 (§3-5 · M16) — 순수 취소 2경로는 **막지 않는다**.

    `_cancel_after_wait`(매수 잔여)·`cancel_remaining` 은 호가창에서 주문을
    빼기만 하므로 **노출 축소**다. 함께 막으면 컷이 "주문을 안 내는 것"이
    아니라 "이미 낸 주문을 못 거두는 것"이 된다.

    `_order_exchange` 매핑을 일부러 **비워** `_apply_clock` fail-open 경로를
    태운다 — 라우터가 "거부"를 내는 설계였다면 여기서 취소할 거래소를 못 얻어
    빈 문자열이 나간다(§3-2 두 번째 반증).
    """
    engine, strat = engine_pair
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))
    assert "ORD-X" not in engine._order_exchange

    await engine._cancel_after_wait(_TICKER, "ORD-X", _SID)
    assert mock_cancel_order.await_count == 1, "`_cancel_after_wait` 취소가 막혔다"
    ex1 = mock_cancel_order.await_args.kwargs.get("exchange")
    assert ex1, f"취소 거래소가 비었다({ex1!r}) — 라우터 fail-open 이 깨졌다"

    strat.state.positions[_TICKER].order_no = "ORD-Y"
    await engine.cancel_remaining(_TICKER, _SID)
    assert mock_cancel_order.await_count == 2, "`cancel_remaining` 취소가 막혔다"
    ex2 = mock_cancel_order.await_args.kwargs.get("exchange")
    assert ex2, f"취소 거래소가 비었다({ex2!r})"


@pytest.mark.asyncio
@freeze_time(_F_1545_30)
async def test_t10_cancel_and_reorder_is_gated_as_a_pair(
    engine_pair, mock_cancel_order: AsyncMock, mock_place_order: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 T10 (§3-5 ③ · M13) — `_cancel_and_reorder` 는 **쌍으로** 막는다.

    취소 3경로 중 이것만 다르다. 유일 호출자가 `is_stop_loss=True` 이고 내용은
    `sleep(30) → cancel_order → place_order` 의 **atomic replace** 다.
    절반만 막으면 결과는 "주문을 안 낸 것"이 아니라 **"호가창에 있던 손절을
    우리가 빼고 아무것도 안 넣은 것"** 이다.

    재현(전부 오늘 성립) — 15:45 손절 시장가 → NXT AFTER_MARKET 가 `'01'` 미지원
    → 거부 → `step_down` 지정가 `'00'` 폴백 접수 → 부분 체결 → 15:45:30
    `_cancel_and_reorder` → 취소 성공 → 재주문만 컷 → **잔여가 15분 무주문**.

    ⇒ 컷이면 취소도 하지 않고 작동 중인 주문을 그대로 둔다. 16:00 이후
    `cancel_remaining` 또는 `risk.on_tick` 재평가에 위임한다.
    """
    engine, strat = engine_pair
    engine._order_strategy["ORD-P"] = _SID
    engine._order_exchange["ORD-P"] = "NXT"
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45, 30))

    await engine._cancel_and_reorder(_TICKER, "ORD-P", 2, is_stop_loss=True)

    assert mock_cancel_order.await_count == 0, (
        "컷 구간인데 **취소만** 나갔다 — 호가창의 손절을 빼고 대체를 안 넣는 "
        "상태가 된다. 쌍으로 막아라(§3-5 ③)"
    )
    assert mock_place_order.await_count == 0, "컷 구간에 재주문이 나갔다"


@pytest.mark.asyncio
@freeze_time(_F_1605)
async def test_t10b_cancel_and_reorder_still_works_outside_the_window(
    engine_pair, mock_cancel_order: AsyncMock, mock_place_order: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔵 T10b (양성 대조군) — 창 **밖**에서는 쌍이 그대로 동작한다.

    T10 은 "0회" 부정 단언이라 `_cancel_and_reorder` 를 통째로 죽이는 구현도
    통과한다. 16:05 에서 취소·재주문이 각각 1회여야 그 구멍이 닫힌다.
    """
    engine, strat = engine_pair
    engine._order_strategy["ORD-P"] = _SID
    engine._order_exchange["ORD-P"] = "KRX"
    _pin_boards(monkeypatch, _kst(_DAY, 16, 5))

    await engine._cancel_and_reorder(_TICKER, "ORD-P", 2, is_stop_loss=True)

    assert mock_cancel_order.await_count == 1, "창 밖 취소가 막혔다 — 과잉 차단"
    assert mock_place_order.await_count == 1, "창 밖 손절 잔여 재주문이 막혔다 — 과잉 차단"


# ═══════════════════════════ T11 — 회복 경로 ═══════════════════════════════
@pytest.mark.asyncio
async def test_t11_cut_then_refires_after_krx_after_market_opens(
    engine_pair, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 T11 (§3-5 회복 경로 실증) — 컷은 **취소가 아니라 최대 20분 유예**다.

    16:00 KRX 애프터 개장 → `H0STCNT0` 연속 체결 프레임 → `risk.on_tick` 재평가
    → cycle287 의 44/41 경로로 발사. `risk.py` 에 "그날 이미 청산 신호를 냈다"
    류의 일일 래치는 **없다**(실측: `_exit_signaled|_exit_latch|sold_today|
    _stop_loss_sent|_exit_emitted` grep 무결과).

    그 재평가가 실제로 `execute_sell` 까지 오려면 `risk.on_tick` 의 선행 가드
    `if ticker in self.order_engine._selling: continue` 를 통과해야 한다 —
    그래서 컷 뒤 `_selling` 이 비어 있는지를 **재발사의 전제**로 함께 잰다.
    """
    engine, strat = engine_pair

    with freeze_time(_F_1545):
        _pin_boards(monkeypatch, _kst(_DAY, 15, 45))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert mock_place_order.await_count == 0
    assert _TICKER not in engine._selling, (
        "컷 뒤 `_selling` 이 남으면 `risk.on_tick` 의 선행 가드가 16:05 재평가를 "
        "통째로 건너뛴다 — 회복 경로가 구조적으로 죽는다"
    )

    with freeze_time(_F_1605):
        _pin_boards(monkeypatch, _kst(_DAY, 16, 5))
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert mock_place_order.await_count == 1, (
        "16:05 재발사가 안 됐다 — 컷이 하루 래치가 되어 버렸다(§3-5). "
        "컷은 유예이지 취소가 아니다"
    )


# ═══════════════════════════ T12 — 창 길이 ═════════════════════════════════
def _sendable_gap_start(d: date) -> int:
    """정오 이후 KRX 가 우리 호가유형을 **처음 안 받는** 분 — 표 파생(리터럴 아님)."""
    from src.engine.market_state import get_market_state
    from src.engine.order_engine import _SENDABLE_DIVISIONS

    for m in range(12 * 60, 24 * 60):
        now = datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=KST_TZ)
        if not (_SENDABLE_DIVISIONS & set(get_market_state(now, market="KRX").order_divisions)):
            return m
    raise AssertionError(f"{d} — KRX 미지원 전이 시각을 찾지 못했다")


@pytest.mark.parametrize("d", [date(2026, 9, 14), date(2026, 9, 15), date(2026, 12, 1)])
def test_t12_cut_window_is_at_most_thirty_minutes_and_starts_at_the_table_boundary(
    d: date,
) -> None:
    """🔴 T12 (§3-4 · M11) — 컷 창 ≤ **30분** ∧ 시작 = 표가 정한 전이 시각.

    K6(`effective_from=2026-09-14`)가 표에서 사라지거나 미적용 날짜로 돌아가면
    컷이 **4시간 30분**(15:30~20:00)으로 벌어진다. 상한 단언이 그 회귀를 잡는
    유일한 장치이고, 시작 시각을 **표에서 역산**해 비교하는 쪽이 `15:30` 리터럴
    비교보다 강하다(표가 정당하게 움직이면 둘이 함께 움직인다).
    """
    blocked = [
        m for m in range(1440)
        if _rest(datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=KST_TZ))[0]
    ]
    assert blocked, f"{d} 컷 구간 없음"
    length = blocked[-1] - blocked[0] + 1
    assert length <= 30, (
        f"{d} 컷 창이 {length}분 — 30분을 넘었다. K6(KRX 애프터마켓)이 표에서 "
        "빠졌거나 날짜 pin 이 2026-09-14 미만으로 돌아갔다(§3-4)"
    )
    assert blocked[0] == _sendable_gap_start(d), (
        f"{d} 컷 시작({blocked[0]//60:02d}:{blocked[0]%60:02d}) ≠ KRX 미지원 전이 "
        f"시각 — 컷의 경계는 표에서만 나와야 한다"
    )


def test_t12b_pre_reform_date_shows_why_the_date_pin_matters() -> None:
    """🔵 T12b (대조군 · §5-5) — K6 **미적용** 날짜에서는 컷이 4시간 30분이다.

    `test_cycle290::test_g290_23` 의 `2026-09-11` 픽스처 8건이 붉어지는 것은
    바로 이 사실 때문이다. 기대값을 덮어 초록으로 만들면 그 사실이 은폐된다 —
    옳은 처분은 **테스트 날짜를 2026-09-14 이상으로 re-pin** 하는 것이고,
    이 테스트가 그 이유를 리포에 남기는 자리다.

    ⚠️ 이 값이 30분으로 줄었다면 K6 의 `effective_from` 이 앞당겨졌다는 뜻이다.
    그건 결함이 아니라 제도 재해석이므로 `docs/kis/README.md` 부터 확인하라.
    """
    d = _PRE_REFORM
    blocked = [
        m for m in range(1440)
        if _rest(datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=KST_TZ))[0]
    ]
    assert blocked, f"{d} 컷 구간 없음"
    assert (blocked[0] // 60, blocked[0] % 60) == (15, 30)
    assert (blocked[-1] // 60, blocked[-1] % 60) == (19, 59), (
        f"{d} 컷 끝이 {blocked[-1]//60:02d}:{blocked[-1]%60:02d} — K6 미적용 날짜는 "
        "20:00 직전까지다(§3-4 실측)"
    )


# ═══════════════════════════ T13 · T16 — 관측 ══════════════════════════════
@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t13_blocked_marker_is_capped_once_per_ticker_side_per_day(
    mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔴 T13 (§3-6 · M9) — `[market_rest_blocked]` 1회/(ticker,side)/일.

    cap 없는 마커가 틱당 1행이 되는 사고는 cycle237(donchian 하루 1만 행)·
    cycle293(`tick_channel_flip`) 두 번 있었다. 게다가 **컷은 거부를 만들지
    않으므로** `SellRejectionTracker` 의 폭주 억제가 걸리지 않는다 — 오늘은
    거부가 억제기인데 컷이 그것을 없앤다.

    🔵 양성 대조군 — 두 번째 종목은 **따로** 1행. cap 키가 (ticker, side) 가
    아니라 전역이면 여기서 잡힌다("하루 1행" 로 뭉뚱그리면 분모가 사라진다).
    """
    engine, strat = _make_engine(tickers=(_TICKER, _TICKER2))
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        for _ in range(20):
            await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
        await engine.execute_sell(_TICKER2, Signal.STOP_LOSS, _SID)

    lines = _lines(caplog, _BLOCKED)
    assert len([m for m in lines if f"ticker={_TICKER} " in m + " "]) == 1, (
        f"`{_BLOCKED}` cap 미적용 — {_TICKER} 행 {lines}"
    )
    assert len([m for m in lines if f"ticker={_TICKER2} " in m + " "]) == 1, (
        f"두 번째 종목이 cap 에 삼켜졌다 — cap 키는 (ticker, side) 다: {lines}"
    )
    assert mock_place_order.await_count == 0


@pytest.mark.asyncio
@freeze_time(_F_1100)
async def test_t16_window_canary_emits_once_a_day_even_when_nothing_is_blocked(
    engine_pair, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔴 T16 (§3-6 카나리아) — `[market_rest_window]` 1회/일, **컷 0건인 날에도**.

    D+1 판독의 성공 서명은 "그 구간 주문 흔적 0건"이다. 그러나 0 은 «배선이
    죽었다»와 «정상»을 구별하지 못한다 — 카나리아가 그 둘을 가른다. 그래서
    **차단 여부와 무관하게** 게이트가 평가되면 그날 1행을 남긴다(11:00 정상
    매도에서도 나온다).

    `start=`/`end=` 는 리터럴이 아니라 표에서 역산한 값이고, `source=market_table`
    이 그 사실을 판독자에게 명시한다.
    """
    engine, strat = engine_pair
    _pin_boards(monkeypatch, _kst(_DAY, 11, 0))

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
        engine._selling.discard(_TICKER)
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)

    assert mock_place_order.await_count >= 1, "11:00 정상 매도가 막혔다 — 과잉 차단"
    lines = _lines(caplog, _WINDOW)
    assert len(lines) == 1, f"`{_WINDOW}` 가 {len(lines)}행 — 1회/일이어야 한다: {lines}"
    assert "source=market_table" in lines[0], lines[0]
    assert "start=15:30" in lines[0] and "end=16:00" in lines[0], (
        f"카나리아의 창이 표와 어긋난다: {lines[0]}"
    )


# ══════════════ T14 — Q2 현실 관측 fail-open «철회» (적대 검증) ══════════════
#
# 🔴 착지 직후 적대 검증이 CRITICAL 1 + HIGH 1 로 이 fail-open 을 무너뜨렸다.
#    종전 T14 는 "틱이 신선하면 컷을 푼다" 를 **계약으로 고정**하고 있었고,
#    그 계약이 참이면 컷은 라이브에서 **한 번도 발화하지 않는다**:
#
#    ① `risk.on_tick` 이 같은 콜스택에서 `ticker_last_tick[ticker] = now_kst` 를
#       **먼저** 쓰고(`risk.py:585`) 곧바로 `execute_sell`(`:688`)·
#       `execute_buy`(`:749`) 를 부른다 ⇒ 게이트가 재는 나이는 **항상 0.0초**.
#       그 구간의 청산 트리거는 **WS 틱 단독**이다(REST 폴은
#       `SWING_REST_POLL_WINDOW_END=15:20` 에 끝난다) — 즉 컷이 막으려던
#       **유일한 경로가 정확히 컷을 해제하는 경로**였다.
#    ② 설령 ①의 타이밍을 고쳐도 신선도는 애초에 판별력이 없다. KRX K5
#       (15:30~16:00 장후 시간외 종가, `fixed_price ('06',)`)가 **같은 채널
#       `H0STCNT0`** 로 실제 체결 프레임을 보낸다(표 실측, T14d). 게다가
#       15:30:00 정각 K4 종가단일가 매칭 프린트가 유동 종목을 한꺼번에
#       신선하게 만든다 — 손절 평가가 가장 일어나기 쉬운 바로 그 순간이다.
#
#    ⇒ "틱이 온다" 와 "우리 호가유형이 접수된다" 는 **완전히 분리된 사실**인데
#       신선도는 둘을 같은 것으로 취급한다. 해제 키로 성립하지 않는다.
#
# ⚠️ 남은 한계는 지우지 않고 **명시**한다(§9-Q2 "빼면 §4 에 명시해야 한다") —
#    `market_state` 표는 날짜 범위만 보는 고정 벽시계라 **특별 개장일(지연 개장,
#    수능일이 표준 사례)을 모른다**. 그런 날 15:30~16:00 은 실제로 연속체결 중인
#    정규장인데 컷이 30분 무음 차단한다(연 1회 수준). 닫는 방법은 신선도가 아니라
#    **표에 거래일·특별일 입력을 넣는 것**이다(별건 카드).
@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t14_cut_holds_against_a_live_fresh_tick(
    engine_pair, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔴 T14 (적대 검증 CRITICAL 재현) — **라이브 콜스택 그대로** 재현한다.

    `risk.on_tick` 이 하는 일을 그대로 흉내 낸다 — `ticker_last_tick[ticker]`
    를 **지금 이 순간**으로 쓰고(나이 0.0초) 곧바로 `execute_sell` 을 부른다.
    종전 구현은 여기서 컷을 풀었다(실측: `GATE BLOCKED? False` +
    `[market_rest_reality_mismatch]` CRITICAL). 컷은 **유지되어야 한다.**
    """
    import src.engine.scanner as _scanner

    engine, strat = engine_pair
    moment = _kst(_DAY, 15, 45)
    _pin_boards(monkeypatch, moment)
    # `risk.on_tick:585` 와 같은 자리·같은 값 — 이 틱이 곧 컷을 유발한 그 틱이다.
    _scanner.ticker_last_tick[_TICKER] = moment

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)

    assert mock_place_order.await_count == 0, (
        "라이브 콜스택(틱 나이 0.0초)에서 컷이 풀렸다 — 그 구간의 청산 트리거는 "
        "WS 틱 단독이므로 이 해제는 컷을 **100% 무력화**한다. 신선도는 해제 키로 "
        "성립하지 않는다(KRX K5 가 같은 채널로 실제 체결 프레임을 보낸다, T14d)"
    )
    assert _TICKER not in engine._selling, "`_selling` 좀비 — T8 ② 계약"
    lines = _lines(caplog, _BLOCKED)
    assert len(lines) == 1, f"`{_BLOCKED}` 가 {len(lines)}행: {lines}"
    assert _critical_lines(caplog, _MISMATCH) == [], (
        f"`{_MISMATCH}` 가 남아 있다 — 이 마커는 fail-open 과 함께 철회됐다. "
        "평상일에 상시 발화해 경보 피로만 만들고(K5 프린트), 정작 진짜 지연 "
        "개장일엔 무시된다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("age_secs", [None, 0, 1, 30, 119, 121, 3600])
@freeze_time(_F_1545)
async def test_t14b_cut_holds_for_every_tick_age(
    age_secs, engine_pair, mock_place_order: AsyncMock,
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """🔵 T14b — 틱 나이 **어떤 값에서도** 컷은 유지된다(임계 자체가 없다).

    종전 임계(120초) 양옆(119/121)을 포함해 스윕한다. 임계를 되살리는
    구현은 이 중 한 점에서 반드시 붉어진다. 음수 나이(미래 타임스탬프 —
    시계 왜곡·오염된 틱)도 컷을 풀면 안 되므로 `-60` 은 T14c 가 구조로 막고
    여기서는 정상 범위만 스윕한다.
    """
    import src.engine.scanner as _scanner

    engine, strat = engine_pair
    moment = _kst(_DAY, 15, 45)
    _pin_boards(monkeypatch, moment)
    if age_secs is not None:
        _scanner.ticker_last_tick[_TICKER] = moment - timedelta(seconds=age_secs)

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)

    assert mock_place_order.await_count == 0, (
        f"age={age_secs}s 에서 컷이 풀렸다 — 신선도 기반 해제가 되살아났다"
    )
    assert _critical_lines(caplog, _MISMATCH) == []


def test_t14c_no_freshness_release_key_exists_in_the_module() -> None:
    """🔴 T14c (구조) — 신선도 해제 키가 **소스에서 소멸**했는지 본다.

    행위 단언만으로는 "임계를 아주 크게 잡아 사실상 항상 해제" 같은 되살림을
    스윕 점 사이로 빠져나가게 둘 수 있다. 컷 게이트가 `ticker_last_tick` 을
    **읽지 않는다**는 사실 자체를 고정한다.

    🔵 양성 대조군 — 같은 스캔에서 `_market_rest_now`·`_market_rest_gate`·
    `[market_rest_blocked]` 는 **존재**해야 한다(스캐너가 파일을 못 읽어도
    부정 단언은 전부 참이 되므로, cycle292 교훈대로 양성 짝을 둔다).
    """
    import inspect

    from src.engine import order_engine as _oe

    src = inspect.getsource(_oe)

    for gone in (
        "_market_rest_reality_contradicts",
        "_MARKET_REST_REALITY_FRESH_SECS",
        "_emit_market_rest_mismatch",
        "market_rest_reality_mismatch",
    ):
        assert gone not in src, (
            f"`{gone}` 가 되살아났다 — 신선도 기반 fail-open 은 컷을 100% "
            "무력화한다(T14 재현). 특별 개장일 한계는 표에 거래일 입력을 넣어 "
            "닫는다(별건 카드)"
        )
    assert not hasattr(_oe.OrderEngine, "_market_rest_reality_contradicts")

    # 🔵 양성 대조군 — 스캐너가 실제로 이 파일을 읽고 있다는 증거
    assert "_market_rest_now" in src
    assert "def _market_rest_gate" in src
    assert "[market_rest_blocked]" in src
    assert "[market_rest_window]" in src


def test_t14d_krx_k5_sends_frames_on_the_subscribed_channel() -> None:
    """🔴 T14d — 신선도가 왜 판별력이 없는지의 **표 근거**(적대 검증 HIGH).

    KRX 15:30~16:00 구간(K5 장후 시간외 종가)은 `fixed_price` 라 우리
    호가유형을 하나도 받지 않지만(= 컷의 근거), **시세 채널은 정규장과 같은
    `H0STCNT0`** 다. cycle294 3단계에서 정규장+애프터 구독이 그 채널에 앉아
    있고 cycle295 (A) 가 갭 전환을 없앴으므로, 그 창 내내 체결 프레임이
    정상적으로 들어온다.

    ⇒ "틱이 온다"(참) 와 "우리 호가유형이 접수된다"(거짓)는 분리된 사실이다.
    이 테스트가 붉어지는 유일한 경우는 표가 바뀐 때이고, 그때는 컷 자체를
    재검토해야 한다(기대값만 고치지 마라).
    """
    from src.engine.market_state import MarketPhase, get_market_state

    regular = get_market_state(_kst(_DAY, 11, 0), market="KRX")
    rest = get_market_state(_kst(_DAY, 15, 45), market="KRX")

    assert rest.phase is MarketPhase.AFTER_CLOSE_FIXED
    assert not (_SENDABLE_DIVISIONS & set(rest.order_divisions)), (
        "15:45 KRX 가 우리 호가유형을 받는다 — 컷의 전제가 무너졌다"
    )
    assert rest.quote_channel == regular.quote_channel, (
        "K5 의 시세 채널이 정규장과 갈렸다 — 그렇다면 신선도 판별력 서술을 "
        "다시 검토해야 한다(지금은 같은 채널이라 프레임이 그대로 온다)"
    )


@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t14e_live_tick_does_not_release_the_other_two_firing_points(
    engine_pair, mock_place_order: AsyncMock, mock_cancel_order: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 T14e — 나머지 두 발사점도 라이브 틱에 풀리지 않는다.

    autouse 픽스처가 `ticker_last_tick` 을 매 테스트 비우므로, 그 dict 가
    라이브처럼 **채워진 상태**의 T10·T15 변형이 없으면 같은 결함이 다시
    숨는다(적대 검증 지적).
    """
    import src.engine.scanner as _scanner

    engine, strat = engine_pair
    moment = _kst(_DAY, 15, 45)
    _pin_boards(monkeypatch, moment)
    _scanner.ticker_last_tick[_TICKER] = moment

    engine._order_strategy["ORD-LIVE"] = _SID
    engine._order_exchange["ORD-LIVE"] = "NXT"
    await engine._cancel_and_reorder(_TICKER, "ORD-LIVE", 2, is_stop_loss=True)
    assert mock_cancel_order.await_count == 0, "라이브 틱이 쌍 게이트를 풀었다"
    assert mock_place_order.await_count == 0, "라이브 틱이 재주문 컷을 풀었다"

    strat.state.positions.pop(_TICKER, None)
    await engine.execute_buy(_TICKER, 10_000, strat)
    assert mock_place_order.await_count == 0, "라이브 틱이 매수 컷을 풀었다"


# ══════════════ T17 — 관측 헬퍼 never-raise (브리프 제약 6) ═════════════════
@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t17_canary_failure_never_changes_behavior(
    engine_pair, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔴 T17 — 관측이 고장 나도 **매매 판정은 그대로**다.

    `[market_rest_window]` 카나리아의 `except` 팔은 테스트에서 한 번도
    실행되지 않아 `raise` 삽입 뮤테이션이 통과했다(적대 검증 MEDIUM). 관측기를
    강제로 터뜨려 ① 예외가 새지 않고 ② 컷 판정과 `[market_rest_blocked]` 가
    불변임을 단언한다.
    """
    import src.engine.order_engine as _oe

    def _boom(now):  # noqa: ANN001 — 고장 주입용
        raise RuntimeError("canary boom")

    engine, strat = engine_pair
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))
    monkeypatch.setattr(_oe, "_market_rest_window_bounds", _boom)

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)

    assert mock_place_order.await_count == 0, (
        "관측기 고장이 컷 판정을 바꿨다 — 관측 실패가 매매를 바꾸면 안 된다"
    )
    assert _lines(caplog, _WINDOW) == [], "고장 난 카나리아가 행을 남겼다"
    assert len(_lines(caplog, _BLOCKED)) == 1, "분모 마커가 관측 고장에 휩쓸렸다"


@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t17b_canary_none_bounds_is_silently_skipped(
    engine_pair, mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔵 T17b — 표에서 창을 못 찾으면(`None`) 카나리아만 조용히 건너뛴다."""
    import src.engine.order_engine as _oe

    engine, strat = engine_pair
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))
    monkeypatch.setattr(_oe, "_market_rest_window_bounds", lambda now: None)

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)

    assert _lines(caplog, _WINDOW) == []
    assert mock_place_order.await_count == 0
    assert len(_lines(caplog, _BLOCKED)) == 1


# ═══════════════════════════ T15 — Q5 매수 대칭 ════════════════════════════
@pytest.mark.asyncio
@freeze_time(_F_1545)
async def test_t15_execute_buy_is_cut_before_the_balance_probe(
    mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔴 T15 (§3-5 ② · §9-Q5 권고 = 넣는다) — 매수 축도 **완전 휴식**이다.

    그 창의 매수는 지금 구조적 0 이다(`post_nxt` 보드를 가진 전략이 LTV 뿐인데
    운영 DB `tradable_boards=["main","pre_nxt"]`). 그래서 이 블록은 **순수
    방어선**이다 — 누군가 `post_nxt` 를 되돌리는 날 "완전 휴식" 이 매도 축에만
    적용되는 것을 막는다.

    🔴 **게이트 자리 증언 = `get_buyable` 미호출.** 자리는 중복매수 가드 **뒤**,
    `get_buyable` **앞**이어야 한다. 그보다 뒤로 내려가면 A-ATOMIC 구간
    (`calc_buy_quantity` ~ `pending_buys.add`, await 0건) 반경에 들어가고,
    그 구간은 매수 예산 원자성의 전제라 byte 동일로 남겨야 한다.
    """
    import src.engine.order_engine as _oe

    engine, strat = _make_engine(with_position=False)
    buyable = AsyncMock(
        return_value=SimpleNamespace(max_buy_quantity=100, max_buy_amount=1_000_000)
    )
    monkeypatch.setattr(_oe, "get_buyable", buyable)
    _pin_boards(monkeypatch, _kst(_DAY, 15, 45))

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine.execute_buy(_TICKER, 10_000, strat)

    assert mock_place_order.await_count == 0, "컷 구간에 매수 주문이 나갔다"
    assert buyable.await_count == 0, (
        "`get_buyable` 이 호출됐다 — 게이트가 잔고 조회 **뒤**에 있다. "
        "KIS 왕복을 낭비하고 A-ATOMIC 구간에 가까워진다(§3-5 ②)"
    )
    assert _TICKER not in strat.state.pending_buys, "`pending_buys` 잔재 — 게이트가 너무 뒤다"
    assert _TICKER not in strat.state.pending_buy_amounts

    lines = _lines(caplog, _BLOCKED)
    assert len(lines) == 1 and "side=buy" in lines[0], (
        f"매수 컷 마커가 없거나 side 가 틀렸다: {lines}"
    )


@pytest.mark.asyncio
@freeze_time(_F_1100)
async def test_t15b_execute_buy_still_works_in_regular_hours(
    mock_place_order: AsyncMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔵 T15b (양성 대조군) — 정규장 매수는 그대로 나간다(과잉 차단 금지)."""
    import src.engine.order_engine as _oe

    engine, strat = _make_engine(with_position=False)
    monkeypatch.setattr(
        _oe, "get_buyable",
        AsyncMock(return_value=SimpleNamespace(
            max_buy_quantity=100, max_buy_amount=1_000_000,
        )),
    )
    _pin_boards(monkeypatch, _kst(_DAY, 11, 0))

    await engine.execute_buy(_TICKER, 10_000, strat)
    assert mock_place_order.await_count == 1, "정규장 매수가 막혔다 — 과잉 차단"
