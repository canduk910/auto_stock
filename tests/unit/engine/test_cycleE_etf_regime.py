"""사이클 E-1 Red — 지수ETF 고지로 스테이지 레짐 신호 (관찰 전용 다크런치).

명세: `_workspace/red/_behaviors_cycleE_etf_regime_20260731.md`
자문: `_workspace/domain_consult/cycle_etf_kojiro_regime_20260731.md` (GO — 다크런치 우선)

E-1 = **관찰만** — 계산 + 로그 + API 노출까지. 매수 가드 행위(blocked/soft_multiplier/
reasons) 는 byte 동일 = 배제 0. block 통합·SOFT 상한·reasons 태깅은 E-2 인계.

이 스위트가 구동하는 인터페이스 (backend-dev Green 대상):
- `system_config.get_etf_regime_enabled() -> bool` / `set_etf_regime_enabled(bool)` (기본 False)
- `market_regime.DEFENSIVE_STAGES = frozenset({3, 4, 5})` (자문 방어집합 정본)
- `market_regime.is_two_day_defensive(stages: list[int|None]) -> bool` (최근 2 스테이지 판정)
- `market_regime.compute_etf_stage_signal(*, now=None) -> EtfStageSignal` (async)
    - 각 지수 `stock_master_daily.get_recent_daily(ticker, N)` 조회 → kojiro_indicators
      `ema`/`stage_of` 실호출로 스테이지 산출 + 2일 연속 방어 + 신선도 게이트
    - 반환 필드: kospi_stage / kosdaq_stage / kospi_defensive_2d / kosdaq_defensive_2d /
      etf_defensive(OR, 양쪽 stale 시 None) / stale_kospi / stale_kosdaq
    - ETF 티커: KODEX200 = 069500 / KODEX 코스닥150 = 229200
- `market_regime.get_current_etf_signal()` / `set_current_etf_signal(sig)` (boot 부착 관찰)
- `scheduler._refresh_market_regime_and_persist()` 가 dkstock 독립으로 compute 호출 +
  `[etf_regime]` 로그 (enabled=False 여도) + 결과 부착. get_buy_block_state 무변경.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

# 계약 상수 — compute 가 조회해야 하는 ETF 티커 (backend 반드시 동일 사용)
KOSPI_ETF = "069500"    # KODEX 200
KOSDAQ_ETF = "229200"   # KODEX 코스닥150


# ---------------------------------------------------------------------------
# 합성 일봉 헬퍼 — 명확한 스테이지 유도 (순수 함수 kojiro_indicators 실호출 검증)
# ---------------------------------------------------------------------------
def _rising_closes(n: int = 90, base: int = 10000, step: int = 30) -> list[int]:
    """단조 상승 close (oldest→newest) → EMA5>20>40 → 안정상승 stage 1."""
    return [base + step * i for i in range(n)]


def _falling_closes(n: int = 90, base: int = 13000, step: int = 30) -> list[int]:
    """단조 하락 close (oldest→newest) → EMA40>20>5 → 안정하락 stage 4."""
    return [base - step * i for i in range(n)]


def _daily_rows(closes_asc: list[int], *, last_date: date, ticker: str) -> list[dict]:
    """closes_asc(oldest→newest) → `get_recent_daily` 계약 형태 rows (bas_dd DESC).

    - bas_dd 는 last_date 로 끝나는 연속 달력일 (신선도 게이트 입력).
    - close_price 정규화 컬럼 (get_recent_daily SELECT * 계약).
    - 반환은 최신순(DESC) — 실제 `get_recent_daily` ORDER BY bas_dd DESC 정합.
    """
    n = len(closes_asc)
    rows = []
    for i, c in enumerate(closes_asc):
        d = last_date - timedelta(days=(n - 1 - i))
        rows.append({"ticker": ticker, "bas_dd": d, "close_price": c})
    return list(reversed(rows))  # newest-first


def _install_daily(monkeypatch, rows_by_ticker: dict[str, list[dict]]):
    """`stock_master_daily.get_recent_daily` monkeypatch (KIS/DB 격리)."""
    from src.db import stock_master_daily as smd

    async def _fake_get_recent_daily(ticker, days=20):
        return list(rows_by_ticker.get(ticker, []))

    monkeypatch.setattr(smd, "get_recent_daily", _fake_get_recent_daily)


def _now_kst(y=2026, mo=7, d=31, h=9) -> datetime:
    from src.db._kst import KST

    return datetime(y, mo, d, h, 0, tzinfo=KST)


def _patch_mode_thresholds(
    monkeypatch, *, mode, vix=25.0, fg_high=85.0, fg_low=15.0, defensive_enabled=True
):
    """get_buy_block_state() DB 위임 monkeypatch (test_cycleD 패턴 답습)."""
    from src.db.system_config import BuyBlockThresholds
    from src.engine import market_regime as mr

    async def _m():
        return mode

    async def _t():
        return BuyBlockThresholds(
            vix_threshold=vix,
            fg_high_threshold=fg_high,
            fg_low_threshold=fg_low,
            defensive_enabled=defensive_enabled,
        )

    monkeypatch.setattr(mr, "_db_get_buy_block_mode", _m, raising=False)
    monkeypatch.setattr(mr, "_db_get_buy_block_thresholds", _t, raising=False)


@pytest.fixture(autouse=True)
def _restore_singletons():
    """모듈 싱글톤 regime + etf signal 복원 (테스트 간 격리)."""
    from src.engine import market_regime as mr

    saved_regime = mr.get_current_regime()
    saved_etf = getattr(mr, "get_current_etf_signal", lambda: None)()
    yield
    mr.set_current_regime(saved_regime)
    setter = getattr(mr, "set_current_etf_signal", None)
    if setter is not None:
        setter(saved_etf)


# ===========================================================================
# E-1 — config 토글 (etf_regime_enabled, 기본 False, DB 우선)
# ===========================================================================
@pytest.mark.asyncio
async def test_get_etf_regime_enabled_defaults_false_when_key_missing(monkeypatch):
    """키 부재 → 기본 False (defensive_enabled/auto_apply 패턴, .env fallback 불필요)."""
    from src.db import system_config as sc

    async def _missing(_key):
        return sc._MISSING

    monkeypatch.setattr(sc, "_select_value", _missing)
    assert await sc.get_etf_regime_enabled() is False


@pytest.mark.asyncio
async def test_get_etf_regime_enabled_true_when_stored(monkeypatch):
    """저장값 {"value": True} → True."""
    from src.db import system_config as sc

    async def _stored(_key):
        return {"value": True}

    monkeypatch.setattr(sc, "_select_value", _stored)
    assert await sc.get_etf_regime_enabled() is True


@pytest.mark.asyncio
async def test_set_etf_regime_enabled_upserts_bool_value(monkeypatch):
    """set 은 JSONB {"value": bool} 표준 형태로 upsert (dkstock_regime_enabled 패턴)."""
    from src.db import system_config as sc

    captured: dict = {}

    async def _fake_upsert(key, value):
        captured["key"] = key
        captured["value"] = value

    monkeypatch.setattr(sc, "_upsert_value", _fake_upsert)
    await sc.set_etf_regime_enabled(True)

    assert captured["value"] == {"value": True}
    assert "etf_regime_enabled" in captured["key"]


# ===========================================================================
# E-2 (방어집합/2일 확인) — 순수 로직 `is_two_day_defensive` + DEFENSIVE_STAGES
# ===========================================================================
def test_defensive_stages_constant_is_345():
    """방어집합 정본 = {3,4,5} (하락 사분면 전체, 자문 §Q2)."""
    from src.engine.market_regime import DEFENSIVE_STAGES

    assert DEFENSIVE_STAGES == frozenset({3, 4, 5})


@pytest.mark.parametrize(
    "stage,expected",
    [(1, False), (2, False), (3, True), (4, True), (5, True), (6, False)],
)
def test_two_day_defensive_stage_membership(stage, expected):
    """스테이지 방어집합 판정 — {3,4,5} 방어 / {1,2,6} 미방어 (동일일 2회)."""
    from src.engine.market_regime import is_two_day_defensive

    assert is_two_day_defensive([stage, stage]) is expected


@pytest.mark.parametrize(
    "stages,expected",
    [
        ([2, 3], False),       # 어제2 오늘3 → 1일뿐 미방어
        ([3, 3], True),        # 2일 연속 방어
        ([3, 6], False),       # 상승전환 → 해제
        ([4, 4, 5], True),     # 최근 2 [4,5] 모두 방어집합 → 유지
        ([4, 4], True),
        ([2, 4], False),       # 단일일 방어 미확정
        ([4, 3], True),        # 둘 다 방어집합
        ([4], False),          # 1일뿐 → 미확정
        ([], False),           # 데이터 없음
        ([None, 4], False),    # None 포함 → 미확정
    ],
)
def test_two_day_defensive_sequences(stages, expected):
    """2일 연속 확인 히스테리시스 — 최근 2 스테이지 모두 방어집합이어야 True."""
    from src.engine.market_regime import is_two_day_defensive

    assert is_two_day_defensive(stages) is expected


# ===========================================================================
# E-2 (계산) — compute_etf_stage_signal 스테이지 산출 + OR 결합 (실호출 순수함수)
# ===========================================================================
@pytest.mark.asyncio
async def test_compute_both_falling_then_stage4_defensive_true(monkeypatch):
    """양 지수 단조 하락 → 각 stage4 + 2일 방어 True → etf_defensive True (OR)."""
    from src.engine.market_regime import compute_etf_stage_signal

    now = _now_kst()
    _install_daily(monkeypatch, {
        KOSPI_ETF: _daily_rows(_falling_closes(), last_date=now.date(), ticker=KOSPI_ETF),
        KOSDAQ_ETF: _daily_rows(_falling_closes(), last_date=now.date(), ticker=KOSDAQ_ETF),
    })

    sig = await compute_etf_stage_signal(now=now)

    assert sig.kospi_stage == 4
    assert sig.kosdaq_stage == 4
    assert sig.kospi_defensive_2d is True
    assert sig.kosdaq_defensive_2d is True
    assert sig.etf_defensive is True
    assert sig.stale_kospi is False
    assert sig.stale_kosdaq is False


@pytest.mark.asyncio
async def test_compute_both_rising_then_stage1_defensive_false(monkeypatch):
    """양 지수 단조 상승 → 각 stage1 + 방어 False → etf_defensive False."""
    from src.engine.market_regime import compute_etf_stage_signal

    now = _now_kst()
    _install_daily(monkeypatch, {
        KOSPI_ETF: _daily_rows(_rising_closes(), last_date=now.date(), ticker=KOSPI_ETF),
        KOSDAQ_ETF: _daily_rows(_rising_closes(), last_date=now.date(), ticker=KOSDAQ_ETF),
    })

    sig = await compute_etf_stage_signal(now=now)

    assert sig.kospi_stage == 1
    assert sig.kosdaq_stage == 1
    assert sig.etf_defensive is False


@pytest.mark.asyncio
async def test_compute_or_combine_one_index_defensive(monkeypatch):
    """코스피 하락(방어) + 코스닥 상승(미방어) → OR 결합 etf_defensive True."""
    from src.engine.market_regime import compute_etf_stage_signal

    now = _now_kst()
    _install_daily(monkeypatch, {
        KOSPI_ETF: _daily_rows(_falling_closes(), last_date=now.date(), ticker=KOSPI_ETF),
        KOSDAQ_ETF: _daily_rows(_rising_closes(), last_date=now.date(), ticker=KOSDAQ_ETF),
    })

    sig = await compute_etf_stage_signal(now=now)

    assert sig.kospi_stage == 4
    assert sig.kosdaq_stage == 1
    assert sig.etf_defensive is True  # 한쪽 방어 → OR


# ===========================================================================
# E-3 — 신선도 게이트 (stale bas_dd → 해당 지수 skip + stale=True, 양쪽 stale → None)
# ===========================================================================
@pytest.mark.asyncio
async def test_compute_one_index_stale_excluded_from_defensive(monkeypatch):
    """코스닥 최신 일봉 30일 전(stale) → 방어 판정 제외 + stale_kosdaq True.

    etf_defensive 는 신선한 코스피(하락 방어)만 반영 → True.
    """
    from src.engine.market_regime import compute_etf_stage_signal

    now = _now_kst()
    stale_date = now.date() - timedelta(days=30)
    _install_daily(monkeypatch, {
        KOSPI_ETF: _daily_rows(_falling_closes(), last_date=now.date(), ticker=KOSPI_ETF),
        KOSDAQ_ETF: _daily_rows(_falling_closes(), last_date=stale_date, ticker=KOSDAQ_ETF),
    })

    sig = await compute_etf_stage_signal(now=now)

    assert sig.stale_kospi is False
    assert sig.stale_kosdaq is True
    # stale 지수는 방어 판정 제외 (신호 skip)
    assert sig.kosdaq_defensive_2d is False
    assert sig.kosdaq_stage is None
    # etf_defensive 는 신선 지수만 반영
    assert sig.etf_defensive is True


@pytest.mark.asyncio
async def test_compute_both_stale_then_etf_defensive_none(monkeypatch):
    """양쪽 stale → etf_defensive = None (신호 없음)."""
    from src.engine.market_regime import compute_etf_stage_signal

    now = _now_kst()
    stale_date = now.date() - timedelta(days=30)
    _install_daily(monkeypatch, {
        KOSPI_ETF: _daily_rows(_falling_closes(), last_date=stale_date, ticker=KOSPI_ETF),
        KOSDAQ_ETF: _daily_rows(_falling_closes(), last_date=stale_date, ticker=KOSDAQ_ETF),
    })

    sig = await compute_etf_stage_signal(now=now)

    assert sig.stale_kospi is True
    assert sig.stale_kosdaq is True
    assert sig.etf_defensive is None


@pytest.mark.asyncio
async def test_compute_empty_rows_then_stale_and_none(monkeypatch):
    """일봉 부재(빈 조회) → 해당 지수 stale + etf_defensive None (양쪽 부재)."""
    from src.engine.market_regime import compute_etf_stage_signal

    now = _now_kst()
    _install_daily(monkeypatch, {KOSPI_ETF: [], KOSDAQ_ETF: []})

    sig = await compute_etf_stage_signal(now=now)

    assert sig.stale_kospi is True
    assert sig.stale_kosdaq is True
    assert sig.kospi_stage is None
    assert sig.etf_defensive is None


# ===========================================================================
# E-4 / E-5 — boot 관찰: dkstock 독립 compute 호출 + [etf_regime] 로그 + 결과 부착
# ===========================================================================
def _patch_refresh_and_persist(monkeypatch, regime):
    """refresh_from_dkstock → 주어진 regime, persist_snapshot → no-op (test_cycleD 답습)."""
    from src.engine import market_regime as mr

    async def _fake_refresh():
        return regime

    async def _fake_persist(_regime, _target_date):
        return None

    monkeypatch.setattr(mr, "refresh_from_dkstock", _fake_refresh)
    monkeypatch.setattr(mr, "persist_snapshot", _fake_persist)


def _patch_buy_block_mode(monkeypatch, mode: str):
    """boot 경로(cycle D inert) 가 조회하는 buy_block_mode 고정."""
    from src.db import system_config as sc

    async def _fake_mode():
        return mode

    monkeypatch.setattr(sc, "get_buy_block_mode", _fake_mode, raising=False)


def _patch_etf_enabled(monkeypatch, enabled: bool):
    from src.db import system_config as sc

    async def _fake_enabled():
        return enabled

    monkeypatch.setattr(sc, "get_etf_regime_enabled", _fake_enabled, raising=False)


def _patch_compute_etf(monkeypatch, signal, *, calls: list):
    """compute_etf_stage_signal 을 결정론적 signal 반환 fake 로 교체 + 호출 기록."""
    from src.engine import market_regime as mr

    async def _fake_compute(*, now=None):
        calls.append(now)
        return signal

    monkeypatch.setattr(mr, "compute_etf_stage_signal", _fake_compute, raising=False)


def _fake_signal(**kw) -> SimpleNamespace:
    base = dict(
        kospi_stage=4, kosdaq_stage=4,
        kospi_defensive_2d=True, kosdaq_defensive_2d=True,
        etf_defensive=True, stale_kospi=False, stale_kosdaq=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_boot_computes_etf_even_when_dkstock_empty(monkeypatch):
    """dkstock empty 여도 compute_etf_stage_signal 호출 (dkstock 독립 = 로버스트니스 본질)."""
    from src.engine.market_regime import MarketRegime
    from src.engine.scheduler import TradingScheduler

    _patch_refresh_and_persist(monkeypatch, MarketRegime.empty())
    _patch_buy_block_mode(monkeypatch, "SOFT")
    _patch_etf_enabled(monkeypatch, False)
    calls: list = []
    _patch_compute_etf(monkeypatch, _fake_signal(), calls=calls)

    sched = TradingScheduler()
    await sched._refresh_market_regime_and_persist()

    assert len(calls) == 1, "empty regime 인데 compute_etf_stage_signal 미호출 (dkstock 독립 위반)"


@pytest.mark.asyncio
async def test_boot_emits_etf_regime_log_even_when_disabled(monkeypatch, caplog):
    """enabled=False(다크런치) 여도 [etf_regime] 관찰 로그 1행 발화."""
    from src.engine.market_regime import MarketRegime
    from src.engine.scheduler import TradingScheduler

    _patch_refresh_and_persist(monkeypatch, MarketRegime.empty())
    _patch_buy_block_mode(monkeypatch, "SOFT")
    _patch_etf_enabled(monkeypatch, False)
    _patch_compute_etf(
        monkeypatch,
        _fake_signal(kospi_stage=4, kosdaq_stage=4, etf_defensive=True),
        calls=[],
    )

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = TradingScheduler()
    await sched._refresh_market_regime_and_persist()

    etf_logs = [r.getMessage() for r in caplog.records if "[etf_regime]" in r.getMessage()]
    assert len(etf_logs) == 1, "[etf_regime] 관찰 로그 미발화 (다크런치 관찰성 결손)"
    msg = etf_logs[0]
    assert "enabled=False" in msg
    assert "etf_defensive=True" in msg
    assert "kospi=stage4" in msg
    assert "kosdaq=stage4" in msg


@pytest.mark.asyncio
async def test_boot_attaches_etf_signal_for_observation(monkeypatch):
    """compute 결과가 get_current_etf_signal() 로 조회 가능하게 부착 (E-6 API 소스)."""
    from src.engine import market_regime as mr
    from src.engine.market_regime import MarketRegime
    from src.engine.scheduler import TradingScheduler

    _patch_refresh_and_persist(monkeypatch, MarketRegime.empty())
    _patch_buy_block_mode(monkeypatch, "SOFT")
    _patch_etf_enabled(monkeypatch, False)
    sentinel = _fake_signal(kospi_stage=4, kosdaq_stage=1, etf_defensive=True)
    _patch_compute_etf(monkeypatch, sentinel, calls=[])

    sched = TradingScheduler()
    await sched._refresh_market_regime_and_persist()

    assert mr.get_current_etf_signal() is sentinel


# ===========================================================================
# E-8 — 안전 (HIGH): get_buy_block_state 무변경 + etf 계산 예외 boot graceful
# ===========================================================================
@pytest.mark.asyncio
async def test_buy_block_state_unchanged_empty_soft(monkeypatch):
    """E-1 배제 0 회귀 — empty regime + SOFT → blocked/mult/reasons 기존 동일."""
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="SOFT")
    state = await MarketRegime.empty().get_buy_block_state()

    assert state.blocked is False
    assert state.soft_multiplier == 1.0
    assert state.reasons == []


@pytest.mark.asyncio
async def test_buy_block_state_unchanged_defensive_soft(monkeypatch):
    """E-1 배제 0 회귀 — defensive regime + SOFT → ×0.5 (etf 신호 무관 기존 동작)."""
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="SOFT")
    regime = MarketRegime(regime="defensive", regime_desc="방어")
    state = await regime.get_buy_block_state()

    assert state.blocked is False
    assert state.soft_multiplier == 0.5
    assert len(state.reasons) == 1


@pytest.mark.asyncio
async def test_boot_graceful_when_etf_compute_raises(monkeypatch):
    """etf 계산 예외 → boot 진행 + 메모리 regime 유효 (매크로 경로 보존)."""
    from src.engine import market_regime as mr
    from src.engine.market_regime import MarketRegime
    from src.engine.scheduler import TradingScheduler

    _patch_refresh_and_persist(monkeypatch, MarketRegime.empty())
    _patch_buy_block_mode(monkeypatch, "SOFT")
    _patch_etf_enabled(monkeypatch, False)

    async def _boom(*, now=None):
        raise RuntimeError("etf compute 실패")

    monkeypatch.setattr(mr, "compute_etf_stage_signal", _boom, raising=False)

    sched = TradingScheduler()
    # 예외 전파 없이 완료되어야 (graceful)
    await sched._refresh_market_regime_and_persist()

    # 매크로 경로 보존 — 메모리 regime 은 empty 로 세팅됨
    assert mr.get_current_regime().is_empty() is True
