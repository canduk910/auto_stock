"""cycle286 Red — C4-a: 매도 거부의 `nxt_tradable=False` 사후 보강 판정축 교체.

자문 정본 = cycle286 도메인 자문 §2 + §명세 S2 (2026-09-12) — **C안 채택**.
8영역 `src/engine/order_engine.py` 단독 접촉(사용자 승인).

## 결함

`order_engine.py:774-780` (현행):

    from datetime import time as _dtime
    now_t = _now_kst.time()
    is_nxt_window = (
        _dtime(8, 0) <= now_t < _dtime(9, 0)
        or _dtime(15, 30) <= now_t < _dtime(20, 0)
    )
    if is_nxt_window:
        ... stock_master.upsert_one(nxt_tradable=False) ...

2026-09-14 부터 **KRX 애프터마켓(16:00~20:00)이 두 번째 창 안에 통째로 들어온다.**
KRX 로 보낸 애프터 주문이 거부되면 이 코드가 그 종목에 `nxt_tradable=False` 를 쓴다.
그런데 우리는 그 주문을 **어느 거래소로 보냈는지 이미 안다**(`target_exchange`, `:664`/`:666`)
— 시계로 추측할 이유가 없었다.

파급 4중(전부 **보유 종목**에만 발생한다 — 발화 조건이 "우리가 그 종목을 매도 중" 이다):

1. `_strategy_exchange_async` 가 NXT/SOR → **KRX 강제 다운그레이드**. 08:00~08:20 KRX 는
   완전히 닫혀 있으므로(market_state K1 시작 08:20) 다음 아침 프리장 청산 평가가 신호를
   내도 **닫힌 시장으로 주문이 가서 거부**된다 = LTV(프리장 청산이 설계된 유일 전략)의
   `overnight_stop_loss = -5.0` 이 실질 무력화된다.
2. 오염 write 가 `refreshed_at=now` 를 스탬프해 24h TTL 지연 갱신 4경로를 전부 skip
   시킨다 → **자기 강화 래치**.
3. `no_feed_registry` → `stale_watcher` LOW 재등록 skip + `r` 영구 홀드 / HIGH 는
   `[no_feed_held]` **거짓 경보** 1행/일.
4. `_execute_next_day_clear` 가 시가 폴링·30초 안정화를 생략하고 거짓 사유
   `reason="nxt_not_tradable"` 를 DB 에 남긴다.

지속 기간 — **창이 하필 딱 맞는다.** 권위 있는 복구는 매일 16:10
`TIME_STOCK_MASTER_BASICS_REFRESH` 의 TTL 없는 전수 CTPF1002R 재적재뿐이다. 08:00~09:00
오염은 같은 날 16:1x 에 복구되지만, **16:30~20:00 오염은 그날 16:1x 를 이미 지나쳐 다음
영업일 16:1x 까지 ≈24시간 존속**한다 — 즉 다음 영업일 프리장 전체 + 09:00 익일청산 판정 +
그날 종일의 stale 판정을 오염된 값으로 돈다. 09-14 신설 KRX 애프터가 정확히 그 최악 창이다.

## Green 계약 (자문 §명세 S2 — C안)

    _nxt_evidence = (
        target_exchange in ("NXT", "SOR")
        and _dtime(8, 0) <= now_t < _dtime(8, 50)
    )
    if _nxt_evidence: ... upsert_one(nxt_tradable=False) ...

| 항 | 내용 | 테스트 |
|---|---|---|
| C4-1 | **거래소 조건** — KRX 로 보낸 주문의 거부는 NXT 거래가능 여부의 증거가 0 | `test_c1_*` |
| C4-2 | **좁힌 창** 08:00~08:50 (상한 = NXT 프리마켓 실질 종료 = `market_state` N1.end, GTP 미체결 일괄취소) | `test_c2_*` |
| C4-3 | 판정 불가·미지 값·예외 = **쓰지 않는다**(fail-safe — 오염 write 가 되돌리기 어려운 쪽) | `test_c3_*` |
| C4-4 | 마커 `[nxt_post_reinforce] ticker= exchange= div= now= wrote=1|0 reason=` — `wrote=0` 이 D+1 판독의 **분모** | `test_c4_*` |
| C4-5 | `_selling.discard` · positions 보존 · tracker 등록 · 재시도 중단 · 분류 순서 **byte 동일** | `test_c5_*` |
| C4-6 | `sell_rejection.py`(TTL 축)·`balance.py`·`session.py` **무접촉** — TTL 은 "팔 수단이 없으니 길게 막는다" 가 안전측이라 15:30~20:00 유지, 학습은 "모르면 안 쓴다" 가 안전측이다. 두 축이 이제 **의도적으로 다른 창**을 쓴다 | `test_c6_*` |

## 왜 B안(거래소만) 단독이 아닌가

SOR 은 KRX·NXT 양쪽으로 라우팅될 수 있고 `msg1` 에 어느 leg 에서 거부됐는지가 없다.
게다가 시장가(`01`)는 **NXT 에 아예 없다**(`market_state` `_NXT_CONTINUOUS_DIVISIONS`) —
`SOR + 01` 의 16:xx 거부는 "KRX 애프터에 시장가가 없어서" 인지 "NXT 로 못 갔어서" 인지
**원리적으로 구분 불가**다. `in ("NXT","SOR")` 로 넓히면 16:05 오염이 그대로 남고(목표 미달),
`== "NXT"` 로만 좁히면 `limit_price>0` 호출자가 현재 0건이라 실질 dead code 가 된다.
C안이 둘을 동시에 닫는다 — 결과 집합은 현행의 **진부분집합**(순수 축소)이다.

## 킬스위치를 두지 않는 이유

매매 판정이 아니라 **DB 에 무엇을 쓰는가** 만 좁히고, 방향이 축소 일변이고, 롤백이 3줄
revert 다. 루트 CLAUDE.md 의 "매수를 막는 통제" 규약 적용 대상이 아니다.

## freezegun 과 타임존

`order_engine` 은 `datetime.now(_KST_TZ)` (tz-aware) 로 판정한다. freezegun 은 naive 문자열을
**UTC** 로 동결하므로 이 파일의 `freeze_time` 인자는 전부 UTC 이고 KST = UTC + 9h 다.
(⚠️ 기존 `tests/integration/test_sell_rejection_integration.py` 의 `tz_offset=-9` 관례는
**정정** — 실측(freezegun 1.5.5) 결과 `tz_offset` 은 naive `datetime.now()` 만 이동시키고
(`-9h` → 리터럴의 전날 시각), aware `datetime.now(tz)` 는 **그 리터럴 숫자를 그대로**
그 tz 로 태그해 돌려준다(값 자체를 변환하지 않는다). 즉 `order_engine` 처럼
`datetime.now(_KST_TZ)` 로 판정하는 코드에서는 **리터럴 문자열이 곧 KST 시각**이다 —
`freeze_time("2026-06-03 08:30:00", tz_offset=-9)` 는 `datetime.now(KST)` 를
`2026-06-03 08:30:00+09:00`(= KST 08:30)로 만든다. "KST 17:30"(리터럴+9h) 이 아니다 —
그 계산은 이 파일이 쓰는 `tz_offset` 없는 UTC 관례와 혼동한 것이다.)

    freeze_time("2026-09-13 23:30:00")  →  KST 2026-09-14 08:30:00
    freeze_time("2026-09-13 23:50:00")  →  KST 2026-09-14 08:50:00 (창 상한, 배타)
    freeze_time("2026-09-14 07:05:00")  →  KST 2026-09-14 16:05:00 (KRX 애프터)
"""

from __future__ import annotations

import ast
import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

KST_TZ = timezone(timedelta(hours=9))
_ROOT = Path(__file__).resolve().parents[3]
_ORDER_ENGINE_REL = "src/engine/order_engine.py"

_MARKER = "[nxt_post_reinforce]"
_OE_LOGGER = "src.engine.order_engine"
_TICKER = "161580"        # 필옵틱스 — 09-08 stale `_selling` 실사례 종목

# ── UTC 동결 시각 ↔ KST (위 docstring 규약) ────────────────────────────────
_KST_0759 = "2026-09-13 22:59:00"   # KST 07:59:00 (창 하한 1분 전)
_KST_0800 = "2026-09-13 23:00:00"   # KST 08:00:00 (창 하한 — 포함)
_KST_0830 = "2026-09-13 23:30:00"   # KST 08:30:00 (NXT 프리마켓 한복판)
_KST_084959 = "2026-09-13 23:49:59" # KST 08:49:59 (창 상한 1초 전)
_KST_0850 = "2026-09-13 23:50:00"   # KST 08:50:00 (창 상한 — 배타, GTP 일괄취소)
_KST_085001 = "2026-09-13 23:50:01" # KST 08:50:01 (창 상한 1초 후 — 추가 정밀도)
_KST_0855 = "2026-09-13 23:55:00"   # KST 08:55:00
_KST_1100 = "2026-09-14 02:00:00"   # KST 11:00:00 (KRX 정규장)
_KST_1535 = "2026-09-14 06:35:00"   # KST 15:35:00 (장후 시간외 / NXT 애프터 단일가)
_KST_1600 = "2026-09-14 07:00:00"   # KST 16:00:00 (구 창 `15:30~20:00` 하한 — 09-14 KRX 애프터마켓 개장 정각)
_KST_1605 = "2026-09-14 07:05:00"   # KST 16:05:00 (**KRX 애프터마켓** — 이 사이클의 핵심)
_KST_1930 = "2026-09-14 10:30:00"   # KST 19:30:00 (NXT 애프터)
_KST_195959 = "2026-09-14 10:59:59" # KST 19:59:59 (구 창 `15:30~20:00` 상한 1초 전)


# ===========================================================================
# 리그 — `tests/unit/engine/test_b1_market_closed_zombie_block.py` 패턴 재사용
# ===========================================================================
class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "long_tail_volatility") -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
                params={"exchange": "KRX"},
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
        return 0


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    strat = _DummyStrategy()
    strat.state.positions[_TICKER] = Position(
        ticker=_TICKER,
        buy_price=10_000,
        quantity=3,
        order_no="ORDER-PRE-161580",
        strategy_id="long_tail_volatility",
        buy_date=date(2026, 9, 11),
    )
    reg.register(strat)
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture
def mock_logs(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "write_log", mock)
    monkeypatch.setattr(_oe, "safe_write_log", mock)
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    return mock


@pytest.fixture
def mock_stock_master(monkeypatch: pytest.MonkeyPatch):
    """`stock_master.get`/`upsert_one` 더블 — 사후 보강 write 추적."""
    import src.db.stock_master as _sm

    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    return _sm


@pytest.fixture(autouse=True)
def _isolate_session_and_prices(monkeypatch: pytest.MonkeyPatch):
    """프리장 사전 지정가 변환(`:677-697`)을 결정적으로 비활성.

    그 변환은 `target_exchange` 를 바꾸지 않으므로 C4-a 판정과 무관하지만, 켜지면
    `div=` 필드가 `00`/`01` 사이에서 흔들려 마커 단정이 벽시계에 흔들린다.
    """
    from src.engine import scanner
    from src.engine.session import session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset())
    monkeypatch.setattr(scanner, "ticker_prices", {})
    return None


def _exchange(monkeypatch: pytest.MonkeyPatch, value):
    """`_strategy_exchange_async` 가 돌려줄 거래소를 고정한다.

    실제 구현은 `params["exchange"].upper()` 를 돌려주고 `nxt_tradable=False` 면
    NXT/SOR → KRX 로 **이미** 다운그레이드한다. 즉 `target_exchange` 는 "이 주문이
    실제로 어느 거래소로 나갔는지" 의 직접 증거다.
    """
    async def _fake(self, strategy_id, *, ticker=None, side="sell"):  # noqa: ARG001
        return value

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async", _fake,
    )


def _closed_err(msg1: str = "장운영시간이 아닙니다.") -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK0918", msg1=msg1)


#: 09-14 이후 KRX 애프터 거부가 프리마켓 실측 문장과 **대칭 형태**로 올 경우.
#: `장운영시간` · `매매 불가 시간` 두 키워드에 걸려 `is_market_closed_rejection` 이
#: 이기고(검사 순서 계약), 현행 코드는 그때 `nxt_tradable=False` 를 쓴다.
#: ⚠️ 이 문장형은 **미실측**이다(`docs/kis/README.md:85` 미실측 항목) — 배제할 수 없어
#: 가드로 남긴다.
_AFTER_CLOSED_MSG1 = "장운영시간이 아닙니다.([애프터마켓] 시장가 매매 불가 시간)"


def _marker_lines(caplog, *, wrote: str | None = None) -> list[str]:
    """레벨(INFO 이상) + 로거 + prefix 3중 한정 (CI 루트 로거 DEBUG 방어)."""
    out = []
    for r in caplog.records:
        if r.name != _OE_LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if not msg.startswith(_MARKER):
            continue
        if wrote is not None and f"wrote={wrote}" not in msg:
            continue
        out.append(msg)
    return out


async def _reject_sell(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    *,
    err: KisApiError | None = None,
) -> None:
    mock_place_order.side_effect = [err or _closed_err()]
    await engine.execute_sell(_TICKER, Signal.STOP_LOSS, "long_tail_volatility")


# ===========================================================================
# C4-1 / C4-2 — 판정 격자 (거래소 × 시각)
# ===========================================================================
#: (frozen UTC, KST 라벨, target_exchange, 기대 write 여부, 기대 reason)
_GRID = [
    # ── 창 안(08:00~08:50) ─────────────────────────────────────────────
    pytest.param(_KST_0800, "08:00:00", "NXT", True, "nxt_pre_window", id="0800-NXT-write"),
    pytest.param(_KST_0830, "08:30:00", "NXT", True, "nxt_pre_window", id="0830-NXT-write"),
    pytest.param(_KST_0830, "08:30:00", "SOR", True, "nxt_pre_window", id="0830-SOR-write"),
    pytest.param(_KST_084959, "08:49:59", "NXT", True, "nxt_pre_window", id="084959-NXT-write"),
    # ── 창 안이지만 KRX 로 보낸 주문 → 증거 0 ──────────────────────────
    pytest.param(_KST_0830, "08:30:00", "KRX", False, "exchange", id="0830-KRX-skip"),
    # ── 창 상한 배타(08:50) 이후 ────────────────────────────────────────
    pytest.param(_KST_0850, "08:50:00", "NXT", False, "window", id="0850-NXT-skip"),
    pytest.param(_KST_085001, "08:50:01", "NXT", False, "window", id="085001-NXT-skip"),
    pytest.param(_KST_0855, "08:55:00", "NXT", False, "window", id="0855-NXT-skip"),
    pytest.param(_KST_0759, "07:59:00", "NXT", False, "window", id="0759-NXT-skip"),
    # ── KRX 정규장 ─────────────────────────────────────────────────────
    pytest.param(_KST_1100, "11:00:00", "NXT", False, "window", id="1100-NXT-skip"),
    pytest.param(_KST_1100, "11:00:00", "KRX", False, "exchange", id="1100-KRX-skip"),
    pytest.param(_KST_1100, "11:00:00", "SOR", False, "window", id="1100-SOR-skip"),
    # ── 15:30~20:00 (구 코드가 "NXT 창" 으로 오판한 구간) ───────────────
    pytest.param(_KST_1535, "15:35:00", "NXT", False, "window", id="1535-NXT-skip"),
    # 구 창 `15:30~20:00` 의 하한·상한 경계 — 09-14 KRX 애프터마켓이 이 구간
    # 전체를 채운다는 것을 경계값으로 못박는다(등가류이나 "구 창이 통째로
    # 편입된다" 는 이 사이클의 핵심 명제를 경계로 직접 증언한다).
    pytest.param(_KST_1600, "16:00:00", "KRX", False, "exchange", id="1600-KRX-old-window-start"),
    pytest.param(_KST_1605, "16:05:00", "KRX", False, "exchange", id="1605-KRX-skip-CORE"),
    pytest.param(_KST_1605, "16:05:00", "SOR", False, "window", id="1605-SOR-skip"),
    pytest.param(_KST_1605, "16:05:00", "NXT", False, "window", id="1605-NXT-skip"),
    pytest.param(_KST_1930, "19:30:00", "SOR", False, "window", id="1930-SOR-skip"),
    pytest.param(_KST_195959, "19:59:59", "NXT", False, "window", id="195959-NXT-old-window-end"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("frozen, kst, exchange, should_write, reason", _GRID)
async def test_c1_attribution_grid(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    frozen: str,
    kst: str,
    exchange: str,
    should_write: bool,
    reason: str,
) -> None:
    """C4-1/C4-2 (RED): `nxt_tradable=False` 는 **NXT/SOR 로 보낸 프리장 거부에만** 쓴다.

    핵심 단정 = `1605-KRX-skip-CORE` — 09-14 부터 KRX 애프터마켓이 구 `15:30~20:00`
    창 안에 통째로 들어오므로, KRX 로 보낸 애프터 주문의 거부가 그 종목을 NXT 불가로
    낙인찍던 경로를 닫는다.
    """
    _exchange(monkeypatch, exchange)
    with freeze_time(frozen):
        await _reject_sell(engine, mock_place_order)

    if should_write:
        # ⚠️ 적대 검증 LOW-4(test) — `assert_awaited(), (msg)` 는 튜플 표현식이라
        # 실패 메시지가 출력되지 않고, `assert_awaited()` 는 2회 이상 await 도
        # 통과시켜 재시도 루프 안으로 write 가 잘못 이동하는 회귀를 못 잡는다.
        # `await_count == 1` 로 교체 — 메시지도 살고 중복 write 도 잡힌다.
        assert mock_stock_master.upsert_one.await_count == 1, (
            f"KST {kst} / exchange={exchange} — 진짜 NXT 프리장 거부의 학습이 사라졌거나 "
            f"중복 write 됐다 (await_count={mock_stock_master.upsert_one.await_count})"
        )
        wrote = mock_stock_master.upsert_one.await_args.args[0]
        assert wrote.ticker == _TICKER
        assert wrote.nxt_tradable is False
    else:
        assert mock_stock_master.upsert_one.await_count == 0, (
            f"KST {kst} / exchange={exchange} — `nxt_tradable=False` 오염 write "
            f"(기대 reason={reason}). 보유 종목의 프리장 청산 능력이 최대 24h 잠긴다"
        )


@pytest.mark.asyncio
@freeze_time(_KST_1605)
async def test_c2_1_krx_after_market_shaped_message_is_not_learned(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C4-1 (RED, 핵심): 애프터마켓 문장형 거부 + KRX 라우팅 → **학습 안 함**.

    `[애프터마켓] 시장가 매매 불가 시간` 은 `장운영시간`·`매매 불가 시간` 두 키워드에
    걸려 `is_market_closed_rejection` 이 이긴다(검사 순서 계약). 현행 코드는 그때
    `nxt_tradable=False` 를 쓴다.
    """
    _exchange(monkeypatch, "KRX")
    await _reject_sell(engine, mock_place_order, err=_closed_err(_AFTER_CLOSED_MSG1))
    assert mock_stock_master.upsert_one.await_count == 0
    assert mock_stock_master.get.await_count == 0, (
        "쓰지 않을 값을 위해 DB 조회까지 했다 — 거래소 판정이 조회보다 앞에 와야 한다"
    )


@pytest.mark.asyncio
@freeze_time(_KST_0850)
async def test_c2_2_window_upper_bound_is_exclusive_at_0850(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C4-2 (RED): 08:50:00 은 **배타** — NXT 프리마켓 GTP 미체결이 일괄 취소되는 시각.

    상한 근거 = `market_state` N1 `end=time(8, 50)`. 08:50~09:00 은 N2(휴장)다.
    """
    _exchange(monkeypatch, "NXT")
    await _reject_sell(engine, mock_place_order)
    assert mock_stock_master.upsert_one.await_count == 0


# ===========================================================================
# C4-3 — fail-safe: 판정 불가 · 미지 값 · 예외 → 쓰지 않는다
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exchange",
    ["", "UNKNOWN", "nxt", "Nxt", "SOR ", "KRX/NXT", None],
    ids=["empty", "unknown", "lowercase-nxt", "mixedcase-nxt", "trailing-space",
         "compound", "none"],
)
@freeze_time(_KST_0830)
async def test_c3_1_unknown_exchange_is_not_learned(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    exchange,
) -> None:
    """C4-3 (RED): 미지·정규화 안 된 거래소 값이면 **쓰지 않는다**(fail-safe).

    여기서 fail-open 은 안전측이 아니다 — 오염 write 는 다음 영업일 프리장까지 ≈24h
    존속하고 자기 강화 래치가 된다. 판정 불가면 아무것도 배우지 않는 것이 옳다.
    (`_strategy_exchange_async` 는 대문자 `"NXT"`/`"SOR"`/`"KRX"` 만 돌려준다.)
    """
    _exchange(monkeypatch, exchange)
    await _reject_sell(engine, mock_place_order)
    assert mock_stock_master.upsert_one.await_count == 0, (
        f"exchange={exchange!r} 인데 학습했다 — 미지 값은 증거가 아니다"
    )


@pytest.mark.asyncio
@freeze_time(_KST_0830)
async def test_c3_2_stock_master_get_failure_does_not_crash_or_write(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C4-3: DB 조회 실패는 흡수되고 write 도 없다(현행 보존) — 예외가 밖으로 안 나간다."""
    mock_stock_master.get.side_effect = RuntimeError("DB down")
    _exchange(monkeypatch, "NXT")
    await _reject_sell(engine, mock_place_order)   # 예외 전파하면 여기서 터진다
    assert mock_stock_master.upsert_one.await_count == 0


@pytest.mark.asyncio
@freeze_time(_KST_0830)
async def test_c3_3_upsert_failure_does_not_break_contract(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    registry: StrategyRegistry,
) -> None:
    """C4-3: write 실패도 `_selling` discard·positions 보존 계약을 깨지 않는다."""
    mock_stock_master.upsert_one.side_effect = RuntimeError("write failed")
    _exchange(monkeypatch, "NXT")
    await _reject_sell(engine, mock_place_order)
    assert _TICKER not in engine._selling
    assert _TICKER in registry.get("long_tail_volatility").state.positions


# ===========================================================================
# C4-4 — 마커 `[nxt_post_reinforce]` (wrote=1 / wrote=0 양쪽)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_KST_0830)
async def test_c4_1_marker_on_write(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    """C4-4 (RED): write 시 `wrote=1 reason=nxt_pre_window` 1행.

    현행 로그(`:798`)는 브래킷 마커가 없는 평문 `stock_master 사후 보강: …` 이라 기계
    판독이 불가능하다. ⚠️ 마커 신설이므로 **배포 전후 grep 합산 금지**.
    """
    _exchange(monkeypatch, "NXT")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await _reject_sell(engine, mock_place_order)
    lines = _marker_lines(caplog)
    assert len(lines) == 1, f"마커 1행이어야 한다: {lines}"
    line = lines[0]
    assert f"ticker={_TICKER}" in line
    assert "exchange=NXT" in line
    assert "wrote=1" in line
    assert "reason=nxt_pre_window" in line
    assert "div=" in line, "주문구분(`div=`)이 없으면 시장가 오탐(F-286-1)을 잴 수 없다"
    assert "now=" in line


@pytest.mark.asyncio
@freeze_time(_KST_0830)
async def test_c4_1b_marker_div_00_when_pre_nxt_preconverted(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    """적대 검증 LOW-5(test) — `div=` 필드가 `00`(지정가) 인 write 행을 실제로 관측한다.

    autouse `_isolate_session_and_prices` 가 프리장 사전 지정가 변환(`:677-697`)을
    결정적으로 꺼 두므로, 이 파일의 모든 write 는 `div=01`(시장가) 로만 관측돼 왔다.
    F-286-1(자문 §2-3)의 판독 근거는 `div=` 분포이므로, `div=00`(진짜 NXT 증거)
    행이 최소 1건은 실제로 만들어짐을 여기서 고정한다. `target_exchange`·
    `_nxt_evidence` 판정에는 영향이 없다(값 불변, 소스로 확인).
    """
    from src.engine import scanner
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.PRE_NXT}))
    monkeypatch.setattr(
        scanner, "ticker_prices", {_TICKER: {"current_price": 12_345}},
    )
    _exchange(monkeypatch, "NXT")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await _reject_sell(engine, mock_place_order)
    lines = _marker_lines(caplog)
    assert len(lines) == 1, f"마커 1행이어야 한다: {lines}"
    assert "div=00" in lines[0], f"프리장 사전 변환이 반영되지 않았다: {lines[0]!r}"
    assert "wrote=1" in lines[0]
    assert mock_stock_master.upsert_one.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, exchange, reason",
    [
        pytest.param(_KST_1605, "KRX", "exchange", id="1605-KRX"),
        pytest.param(_KST_1605, "SOR", "window", id="1605-SOR"),
        pytest.param(_KST_0830, "KRX", "exchange", id="0830-KRX"),
        pytest.param(_KST_0855, "NXT", "window", id="0855-NXT"),
    ],
)
async def test_c4_2_marker_on_skip_is_the_denominator(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
    frozen: str,
    exchange: str,
    reason: str,
) -> None:
    """C4-4 (RED): **미기록 분기에도 1행** — `wrote=0` 이 없으면 "안 썼다" 를 증명할 수 없다.

    D+1 판독의 분모다. `reason` 은 `exchange`(거래소 조건 불만족) / `window`(시각 조건
    불만족)로 갈린다 — 운영 `params.exchange` 가 예상과 다르면 `reason=exchange` 가
    대량으로 찍혀 즉시 드러난다(revert 불필요, 관측 사안).
    """
    _exchange(monkeypatch, exchange)
    caplog.clear()
    with freeze_time(frozen), caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await _reject_sell(engine, mock_place_order)
    lines = _marker_lines(caplog, wrote="0")
    assert len(lines) == 1, f"wrote=0 마커 1행이어야 한다: {_marker_lines(caplog)}"
    assert f"reason={reason}" in lines[0], (
        f"사유 분류가 틀렸다 (기대 {reason}): {lines[0]!r}"
    )
    assert f"exchange={exchange}" in lines[0]


@pytest.mark.asyncio
@freeze_time(_KST_1605)
async def test_c4_3_no_write_marker_when_skipped(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    """C4-4: skip 시 `wrote=1` 행은 없다(마커 두 종이 섞이지 않는다)."""
    _exchange(monkeypatch, "KRX")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await _reject_sell(engine, mock_place_order)
    assert _marker_lines(caplog, wrote="1") == []


# ===========================================================================
# C4-5 — 나머지 market_closed 계약은 byte 동일
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, exchange",
    [
        pytest.param(_KST_0830, "NXT", id="0830-NXT-write-path"),
        pytest.param(_KST_1605, "KRX", id="1605-KRX-skip-path"),
    ],
)
async def test_c5_1_selling_discarded_and_position_preserved(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    registry: StrategyRegistry,
    frozen: str,
    exchange: str,
) -> None:
    """C4-5: `_selling` **discard** + positions 보존 + 재시도 중단.

    루트 CLAUDE.md — `_selling` 을 보존하면 그게 곧 stale `_selling` 좀비 = 손절 마비다
    (09-08 필옵틱스 161580 이 6시간 45분 잠긴 실사례). 진입 차단은
    `SellRejectionTracker.is_blocked()` 가 담당한다.
    """
    _exchange(monkeypatch, exchange)
    with freeze_time(frozen):
        await _reject_sell(engine, mock_place_order)

    assert _TICKER not in engine._selling, "stale `_selling` 좀비 = 손절 마비"
    pos = registry.get("long_tail_volatility").state.positions.get(_TICKER)
    assert pos is not None and pos.quantity == 3, "positions 가 보존되지 않았다"
    assert mock_place_order.await_count == 1, "market_closed 는 재시도하지 않는다"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, exchange, in_krx_main",
    [
        pytest.param(_KST_0830, "NXT", False, id="0830-NXT"),
        pytest.param(_KST_1605, "KRX", False, id="1605-KRX"),
        pytest.param(_KST_1100, "KRX", True, id="1100-KRX"),
    ],
)
async def test_c5_2_tracker_registration_unchanged(
    engine: OrderEngine,
    mock_place_order: AsyncMock,
    mock_logs: AsyncMock,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
    frozen: str,
    exchange: str,
    in_krx_main: bool,
) -> None:
    """C4-5: TTL 축(`SellRejectionTracker`)은 **무접촉**.

    학습 축만 거래소 기준으로 바뀐다. TTL 은 "팔 수단이 없으니 길게 막는다" 가 안전측이라
    `is_nxt_session_hours`(15:30~20:00)를 그대로 쓴다 — 두 축이 이제 **의도적으로 다른
    창**이고, 다음 사이클이 둘을 같은 창으로 되돌리면 안 된다.
    """
    _exchange(monkeypatch, exchange)
    with freeze_time(frozen):
        await _reject_sell(engine, mock_place_order)

    assert _TICKER in engine._sell_rejection._blocked_until, (
        "tracker 등록이 사라졌다 — 진입 게이트가 무력화되고 거부 폭주가 부활한다"
    )
    assert engine._sell_rejection._blocked_reason.get(_TICKER) == "market_closed"


# ===========================================================================
# C4-6 — TTL 축 / 분류기 무접촉 + 08:50 드리프트 가드
# ===========================================================================
def test_c6_1_ttl_axis_window_definition_unchanged() -> None:
    """C4-6: `sell_rejection.is_nxt_session_hours` 는 15:30~20:00 을 **유지**한다.

    이 사이클은 학습 축만 좁힌다. TTL 을 함께 좁히면 09-14 이후 16:xx 거부가 5분 TTL 로
    풀려 팔 수단이 없는 구간에서 거부 폭주가 부활한다(안전측이 반대 방향이다).
    """
    from src.engine.sell_rejection import is_krx_main_hours, is_nxt_session_hours

    d = date(2026, 9, 14)
    assert is_nxt_session_hours(datetime.combine(d, time(8, 30), tzinfo=KST_TZ)) is True
    assert is_nxt_session_hours(datetime.combine(d, time(8, 55), tzinfo=KST_TZ)) is True
    assert is_nxt_session_hours(datetime.combine(d, time(16, 5), tzinfo=KST_TZ)) is True
    assert is_nxt_session_hours(datetime.combine(d, time(19, 59), tzinfo=KST_TZ)) is True
    assert is_krx_main_hours(datetime.combine(d, time(11, 0), tzinfo=KST_TZ)) is True
    assert is_krx_main_hours(datetime.combine(d, time(16, 5), tzinfo=KST_TZ)) is False


def _execute_sell_source() -> str:
    src = (_ROOT / _ORDER_ENGINE_REL).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute_sell":
            seg = ast.get_source_segment(src, node)
            assert seg, "`execute_sell` 소스 세그먼트 추출 실패"
            return seg
    raise AssertionError("`execute_sell` 를 찾지 못했다")


def test_c6_2_window_literals_match_market_state_n1() -> None:
    """C4-2 (RED, 드리프트 가드): `execute_sell` 의 `_dtime(H, M)` 리터럴 == N1 프리마켓.

    새 리터럴 `08:50` 의 근거는 `market_state.MARKET_TABLE` 의 N1(`start=08:00`,
    `end=08:50`)이다. 프로덕션 import 는 만들지 않고(순환·결합 회피) 테스트에서 대조한다 —
    cycle264 `test_c7_scheduler_line_cap_matches_cycle257_guard` 의 "두 수가 갈라지면
    조인 쪽" 패턴 답습.
    """
    from src.engine.market_state import MARKET_TABLE

    n1 = next(r for r in MARKET_TABLE if r.row_id == "N1")
    seg = _execute_sell_source()
    found = set()
    for node in ast.walk(ast.parse(seg)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_dtime"
        ):
            args = [a.value for a in node.args if isinstance(a, ast.Constant)]
            if len(args) == 2:
                found.add(time(*args))
    assert found == {n1.start, n1.end}, (
        f"`execute_sell` 의 시각 리터럴 {sorted(found)} 이 N1 프리마켓 "
        f"({n1.start}~{n1.end}) 과 갈라졌다 — 구 창 `09:00`/`15:30`/`20:00` 이 남아 있거나 "
        f"N1 이 바뀌었다"
    )


def test_c6_3_classification_order_preserved() -> None:
    """C4-5: `is_market_closed_rejection` 검사가 `is_market_order_disallowed` 보다 **먼저**.

    APBK0918 `[프리마켓] 시장가 매매 불가 시간` 은 두 분류에 **동시 매칭**한다. closed 가
    먼저라 "보류(포지션 보존 + 다음 09:00 TTL)" 로 떨어진다 — 프리장 왜곡 시세에 지정가
    폴백으로 즉시 파는 것보다 안전(2026-08-06 사용자 결정).
    """
    seg = _execute_sell_source()
    i_closed = seg.find("is_market_closed_rejection")
    i_disallow = seg.find("is_market_order_disallowed")
    assert i_closed != -1 and i_disallow != -1
    assert i_closed < i_disallow, "거부 분류 검사 순서가 뒤집혔다"


def test_c6_4_no_killswitch_param_introduced() -> None:
    """C4: 킬스위치 `DEFAULT_PARAMS` 키를 만들지 않는다(롤백 = 3줄 revert).

    매매 판정이 아니라 "DB 에 무엇을 쓰는가" 만 좁히고 방향이 축소 일변이다.
    """
    src = (_ROOT / _ORDER_ENGINE_REL).read_text(encoding="utf-8")
    for token in ("nxt_post_reinforce_mode", "nxt_reinforce_enabled",
                  "nxt_learn_mode", "nxt_attribution_mode"):
        assert token not in src, f"`{token}` 킬스위치 파라미터가 도입됐다"
