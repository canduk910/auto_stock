"""cycle227 W6 (RED) — universe stale 가드의 "거래량 빈약" 안전조건을 진짜 당일 누적으로.

## 결함 (P0-2)

가드는 `stale > 5` **그리고** `거래량 빈약` 두 조건으로 축출하는데, 두 번째 조건의
소스가 `inquire_ccnl(FHKST01010300)` 의 `today_volume` 이다. 그런데 그 값은
**최근 ~30 체결의 `cntg_vol` 합**이라 임계 `UNIVERSE_LOW_VOLUME_THRESHOLD=10_000` 을
사실상 항상 미달한다 ⇒ 안전조건이 실질 무력화되어 가드가
**"스테일 6회 = 무조건 축출"** 로 퇴화했다.

2026-08-25 실측: BFB 후보 48 중 **20건(41.7%)** 이 이 경로로 당일 영구 축출
(`reason=stale_6plus_low_volume`, `today_volume` 254~6,197).
BFB·VCP 는 `_SWING_POLL_STRATEGIES` 비멤버라 REST 폴 보강이 없어
**미구독 = 매수 평가 완전 상실**이다.

## KIS 정본 확인 결과 (W6 선행 필수 항목, 이 사이클에서 수행)

`mcp__kis-code-assistant__read_source_code` 로 확인한 FHKST01010300 응답 output row 는
**7 컬럼**이다 — `stck_cntg_hour` / `stck_prpr` / `prdy_vrss` / `prdy_vrss_sign` /
`cntg_vol` / `tday_rltv` / `prdy_ctrt`. **`acml_vol` 은 없다.**
(`cntg_vol` 이 "체결 **1건**의 거래량" 이라는 정본 정의가 위 진단을 산술적으로 확증한다.)

⇒ 명세 W6-2 의 "존재하면 첫 row 추출·추가 호출 0" 분기는 성립하지 않는다.
⇒ REST 폴백은 **FHKST01010100**(`inquire-price`, `output.acml_vol`) 확정.
   그 path 는 `base.py::_QUOTE_ALLOWED_PATHS` 화이트리스트에 **이미 있다**.

## 계약

1. **1순위** `tick_volume.get_observed_acml_vol(ticker)` → `vol_source=tick` (KIS 호출 0)
2. **2순위** `quotation.inquire_acml_vol(ticker)` (FHKST01010100) → `vol_source=rest`
3. **둘 다 부재 → 제외 보류.** 잘못된 축출(= 매수 평가 상실)이 잘못된 보류(= 슬롯 낭비)
   보다 훨씬 비싸다. 라이브 슬롯 사용률 34%(111/328) 실측이 그 근거다.
4. `today_volume` 은 **판정 소스에서 빠지고 로그 필드로만 남는다** (운영 grep 연속성).
5. `UNIVERSE_LOW_VOLUME_THRESHOLD=10_000` **값 불변** — 임계 재튜닝이 아니라 분자 정의 시정.
6. 보유·익일청산 절대 보호, 50ms sleep, `ccnl is None → 보류` 등 기존 계약 전부 불변.

## ⚠️ 이 파일은 `freeze_time` 을 쓰지 않는다

가드 본체에 `await asyncio.sleep(0.05)`(Rate Limit 보호)가 있는데, freezegun 은
`time.monotonic` 까지 얼려서 **이벤트 루프 시계가 전진하지 않는다** → `asyncio.sleep`
이 영원히 반환되지 않고 테스트가 행(hang) 한다. 기존 `test_universe_guard.py` 도
같은 이유로 freeze 를 쓰지 않는다.

가드 자체에는 날짜 의존 분기가 없고, `tick_volume` 의 KST 날짜 경계는
`test_cycle227_tick_volume.py` 가 전담 검증하므로 결정성 손실은 없다.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine import tick_volume

pytestmark = pytest.mark.unit

LOGGER_NAME = "src.engine.scheduler"
STALE = 9  # > MAX_STALE_RETRIES(=5)
TICKER = "001450"


@pytest.fixture(autouse=True)
def _isolate():
    tick_volume.reset_for_test()
    yield
    tick_volume.reset_for_test()


def _make_sched(
    *,
    held_tickers: list[str] | None = None,
    next_day_clear: set[tuple[str, str]] | None = None,
    stale_counts: dict[str, int] | None = None,
):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True
    sched._stale_retry_count = stale_counts if stale_counts is not None else {TICKER: STALE}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = next_day_clear or set()
    sched._universe_excluded_today = set()

    fake_registry = MagicMock()
    fake_registry.is_ticker_held_by_any = MagicMock(
        side_effect=lambda t: t in (held_tickers or [])
    )
    sched.registry = fake_registry
    return sched


@pytest.fixture
def rig(monkeypatch):
    """외부 경계만 대역 — KIS REST 2종 + WebSocket unsubscribe."""
    from src.api import quotation as quot_mod
    from src.engine import scheduler as sch_mod
    from src.realtime import websocket_pool as wp_mod

    state = {"today_volume": 254, "rest_acml_vol": None}

    async def _fake_ccnl(ticker, market="J"):
        return {
            "last_cntg_hour": "100112",
            "last_price": 50_600,
            "last_volume": 12,
            "last_relative_strength": 80.0,
            "today_volume": state["today_volume"],
            "raw_count": 30,
        }

    rest_spy = AsyncMock(side_effect=lambda ticker, *a, **kw: state["rest_acml_vol"])
    unsub_spy = AsyncMock()

    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)
    monkeypatch.setattr(quot_mod, "inquire_acml_vol", rest_spy, raising=False)
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)

    async def _wl(*a, **kw):
        return None

    monkeypatch.setattr(sch_mod, "write_log", _wl, raising=False)

    return {"state": state, "rest": rest_spy, "unsub": unsub_spy}


def _excluded_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "[universe_excluded]" in r.getMessage()]


# ===========================================================================
# W6-1 / W6-2 — tick 관측 우선 (KIS 추가 호출 0)
# ===========================================================================

@pytest.mark.asyncio
async def test_when_tick_observation_sufficient_then_not_excluded_and_no_rest_call(rig):
    """W6-2 — `today_volume` 이 미달이어도 **진짜 당일 누적**이 충분하면 축출하지 않는다.

    2026-08-25 에 이 경로로 BFB 후보 20건이 잘못 축출됐다.
    """
    sched = _make_sched()
    rig["state"]["today_volume"] = 254          # 최근 ~30 체결 합 (실측 범위)
    tick_volume.record_acml_vol(TICKER, 1_500_000)

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER not in sched._universe_excluded_today, (
        "실측 당일 누적 1,500,000 인 종목이 축출됐다 — 안전조건 소스가 여전히 "
        "`today_volume`(최근 체결 합) 이다"
    )
    rig["unsub"].assert_not_awaited()
    rig["rest"].assert_not_awaited()  # tick 관측이 있으면 REST 폴백은 부르지 않는다


@pytest.mark.asyncio
async def test_when_tick_observation_low_then_excluded_with_tick_source(rig, caplog):
    """W6-3 — 진짜 당일 누적이 임계 미달이면 축출 + `vol_source=tick`."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    sched = _make_sched()
    tick_volume.record_acml_vol(TICKER, 900)

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER in sched._universe_excluded_today
    rig["unsub"].assert_awaited_once()
    msg = _excluded_lines(caplog)[0]
    assert "acml_vol=900" in msg, f"판정에 쓴 값이 로그에 없다: {msg}"
    assert "vol_source=tick" in msg, f"판정 소스가 로그에 없다: {msg}"


# ===========================================================================
# W6-4 / W6-5 — REST 폴백 (FHKST01010100)
# ===========================================================================

@pytest.mark.asyncio
async def test_when_no_tick_observation_then_rest_fallback_called(rig):
    """W6-4 — tick 미관측 시에만 REST 폴백."""
    sched = _make_sched()
    rig["state"]["rest_acml_vol"] = 2_000_000

    await sched._evaluate_universe_guard([TICKER])

    rig["rest"].assert_awaited_once()
    assert TICKER not in sched._universe_excluded_today


@pytest.mark.asyncio
async def test_when_rest_value_low_then_excluded_with_rest_source(rig, caplog):
    """W6-5 — REST 값이 미달이면 축출 + `vol_source=rest`."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    sched = _make_sched()
    rig["state"]["rest_acml_vol"] = 1_200

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER in sched._universe_excluded_today
    msg = _excluded_lines(caplog)[0]
    assert "acml_vol=1200" in msg
    assert "vol_source=rest" in msg


# ===========================================================================
# W6-6 — 둘 다 부재 → 제외 보류 (이번 시정의 안전 방향)
# ===========================================================================

@pytest.mark.asyncio
async def test_when_both_sources_absent_then_exclusion_deferred(rig):
    """W6-6 — 판정 근거가 없으면 **축출하지 않는다.**

    잘못된 축출 = 매수 평가 완전 상실(BFB/VCP 는 REST 폴 보강이 없다).
    잘못된 보류 = 슬롯 낭비. 라이브 슬롯 사용률 34% 실측에서 후자가 훨씬 싸다.
    기존 `ccnl is None → 보류` 패턴과 같은 방향이다.
    """
    sched = _make_sched()
    rig["state"]["rest_acml_vol"] = None

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER not in sched._universe_excluded_today, (
        "당일 누적을 어느 소스로도 못 구했는데 축출했다 — 근거 없는 축출이다"
    )
    rig["unsub"].assert_not_awaited()


# ===========================================================================
# W6-7 / W6-8 — 로그 필드 연속성 · 판정 소스 전환
# ===========================================================================

@pytest.mark.asyncio
async def test_excluded_log_keeps_legacy_fields(rig, caplog):
    """W6-7 — 기존 필드(`reason`/`retries`/`last_cntg_hour`/`today_volume`) 유지.

    운영 grep 이력이 끊기면 이번 시정의 전후 비교가 불가능해진다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    sched = _make_sched()
    rig["state"]["today_volume"] = 254
    tick_volume.record_acml_vol(TICKER, 900)

    await sched._evaluate_universe_guard([TICKER])

    msg = _excluded_lines(caplog)[0]
    assert f"ticker={TICKER}" in msg
    assert "reason=stale_6plus_low_volume" in msg
    assert f"retries={STALE}" in msg
    assert "last_cntg_hour=100112" in msg
    assert "today_volume=254" in msg, f"기존 필드가 사라졌다 (grep 연속성 단절): {msg}"


@pytest.mark.asyncio
async def test_today_volume_is_no_longer_the_decision_source(rig):
    """W6-8 — `today_volume` 이 임계를 넘어도 **진짜 당일 누적**이 미달이면 축출한다.

    판정 소스가 실제로 교체됐는지 못박는 대칭 케이스. `today_volume` 이 여전히
    조기 `continue` 를 만들면 이 테스트가 실패한다.
    """
    sched = _make_sched()
    rig["state"]["today_volume"] = 50_000       # 임계 초과
    tick_volume.record_acml_vol(TICKER, 254)    # 진짜 당일 누적은 빈약

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER in sched._universe_excluded_today


# ===========================================================================
# W6-9 ~ W6-14 — 기존 계약 불변 (보존 검증)
# ===========================================================================

@pytest.mark.asyncio
async def test_held_ticker_never_excluded(rig):
    """W6-9 — 보유 종목 절대 보호 (손절·트레일링 우선)."""
    sched = _make_sched(held_tickers=[TICKER])
    tick_volume.record_acml_vol(TICKER, 1)

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER not in sched._universe_excluded_today
    rig["unsub"].assert_not_awaited()


@pytest.mark.asyncio
async def test_next_day_clear_ticker_never_excluded(rig):
    """W6-10 — 익일청산 종목 절대 보호 (시가 race 차단)."""
    sched = _make_sched(next_day_clear={(TICKER, "momentum")})
    tick_volume.record_acml_vol(TICKER, 1)

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER not in sched._universe_excluded_today


@pytest.mark.asyncio
async def test_stale_within_threshold_not_evaluated(rig):
    """W6-11 — `stale <= MAX_STALE_RETRIES` 는 평가 자체를 안 한다 (KIS 호출 절약)."""
    sched = _make_sched(stale_counts={TICKER: 3})
    tick_volume.record_acml_vol(TICKER, 1)

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER not in sched._universe_excluded_today
    rig["rest"].assert_not_awaited()


@pytest.mark.asyncio
async def test_ccnl_none_still_defers(monkeypatch, rig):
    """W6-12 — `inquire_ccnl` None 은 기존대로 제외 보류."""
    from src.api import quotation as quot_mod

    async def _none_ccnl(ticker, market="J"):
        return None

    monkeypatch.setattr(quot_mod, "inquire_ccnl", _none_ccnl, raising=False)
    sched = _make_sched()
    tick_volume.record_acml_vol(TICKER, 1)

    await sched._evaluate_universe_guard([TICKER])

    assert TICKER not in sched._universe_excluded_today


def test_threshold_constant_unchanged():
    """W6-13 — 임계 값 불변. 이번 시정은 분모(임계)가 아니라 **분자 정의**를 고친다."""
    from src.engine.stale_universe_guard import UNIVERSE_LOW_VOLUME_THRESHOLD

    assert UNIVERSE_LOW_VOLUME_THRESHOLD == 10_000


# ===========================================================================
# W6 부속 — REST 폴백 함수가 KIS 정본 TR 로 구현됐는가
# ===========================================================================

def test_quotation_exposes_inquire_acml_vol():
    """폴백 경로의 존재 계약.

    FHKST01010300 에 `acml_vol` 이 **없다**는 KIS 정본 확인 결과가 이 함수를 요구한다.
    """
    from src.api import quotation

    assert callable(getattr(quotation, "inquire_acml_vol", None)), (
        "`inquire_acml_vol` 부재 — FHKST01010300 응답에 acml_vol 이 없으므로 "
        "REST 폴백은 FHKST01010100 경유가 유일한 경로다"
    )


def test_quotation_fallback_uses_inquire_price_tr():
    """폴백은 FHKST01010100 / `inquire-price` 여야 한다 (화이트리스트 기존재 path)."""
    from pathlib import Path

    src = Path("src/api/quotation.py").read_text(encoding="utf-8")
    assert "FHKST01010100" in src, (
        "폴백 TR_ID 가 소스에 없다 — 임의 TR 로 구현되면 시세 풀 화이트리스트를 벗어난다"
    )
    assert "/uapi/domestic-stock/v1/quotations/inquire-price" in src
