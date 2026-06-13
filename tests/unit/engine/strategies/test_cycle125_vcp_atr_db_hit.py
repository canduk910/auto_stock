"""사이클 125 (2026-06-13) — VCP prepare() ATR 산정 DB 헬퍼 전환 회귀 가드.

[변경 내용]
- `prepare()` 내 ATR 산정 영역을 `stock_master_daily.get_atr()` DB 우선으로 전환
- DB ATR (Wilder smoothing) vs KIS 캔들 ATR (SMA) ±10% 임계 일치 검증
- DB hit 시 db_atr_hit 카운터, DB miss 시 db_atr_miss, ±10% 초과 시 db_atr_mismatch + KIS fallback

[회귀 가드 5 케이스]
G-ATR-MATCH    : DB ATR 반환 → ±10% 이내 → db_atr_hit 증가
G-ATR-FALLBACK : DB ATR None (miss) → db_atr_miss 증가, KIS 캔들 fallback 사용
G-ATR-WILDER   : DB ATR 반환 but KIS ATR 과 ±10% 초과 → db_atr_mismatch + KIS fallback + WARNING
G-CYCLE49-PRESERVE: 사이클 49 _check_pullback_sequence 영역 무변경 (ATR 산정 변경 무영향)
G-VOLATILITY-SPIKE : db_atr > 0 but kis_atr == 0 → db_atr 직접 사용 (DB hit 카운터)

절대 경로 하드코딩 금지 (CI 환경 정합) — Path(__file__).resolve().parents[N] 상대 경로 의무.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

# 절대 경로 하드코딩 금지 (사이클 123 hotfix 답습)
_VCP_SRC = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "engine"
    / "strategies"
    / "vcp_breakout.py"
)


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _make_candles(n: int = 95) -> list[dict]:
    """fetch_daily_candles 반환 형식을 모방한 캔들 리스트.

    - n >= 95: VCP prepare() 내 effective_ema_long 충족
    - candles[0] = 어제 (prev_idx=0)
    - 단조 상승 추세 (최신 종가가 가장 높음)
    - 거래량 충분 (acml_vol > 0)
    """
    today = datetime.now(KST).date()
    rows = []
    base_close = 50_000
    for i in range(n):
        d = today - timedelta(days=i + 1)  # candles[0] = 어제
        close = base_close + i * 200       # 역순 → 오래될수록 낮음 (최신이 높음=상승추세)
        high = close + 1_000
        low = close - 800
        rows.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "acml_vol": str(3_000_000 + i * 1_000),
        })
    return rows


def _make_strategy(monkeypatch):
    """VcpBreakoutStrategy 인스턴스를 최소 mock 상태로 준비."""
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    config = StrategyConfig(
        strategy_id="vcp_breakout",
        name="VCP 돌파",
        params={},
    )
    strat = VcpBreakoutStrategy(config)

    # _scan_universe → 단일 종목 반환
    async def _fake_scan():
        return ["005930"]

    strat._scan_universe = _fake_scan
    return strat


def _bypass_filters(strat):
    """trend_filter / base_detect / pullback_sequence / volume_contraction 를 bypass.

    ATR 산정 영역에만 집중하기 위해 중간 필터 메서드를 mock.
    사이클 123 donchian 패턴과 달리 VCP는 다단계 필터 구조이므로
    각 단계를 pass로 mock해야 ATR 코드에 도달 가능.
    """
    _FAKE_TREND = {"ema50": 48_000, "ema150": 46_000, "ema200": 44_000}
    _FAKE_BASE = {
        "high": 55_000,
        "low": 50_000,
        "length": 40,
        "avg_volume_20": 3_000_000,
        "last_pullback_pct": 0.05,
        "last_pullback_count": 2,
    }

    strat._check_trend_filter = lambda *args, **kwargs: _FAKE_TREND
    strat._detect_base = lambda *args, **kwargs: _FAKE_BASE
    strat._check_pullback_sequence = lambda *args, **kwargs: True
    strat._check_volume_contraction = lambda *args, **kwargs: True


# ---------------------------------------------------------------------------
# G-ATR-MATCH: DB ATR 반환 → ±10% 이내 → db_atr_hit 증가
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_atr_match_db_hit_counter(monkeypatch):
    """get_atr 유효값 반환 + KIS ATR 과 ±10% 이내 → db_atr_hit 카운터 증가.

    KIS 캔들 ATR: 캔들 구조상 high-low=1800 → SMA 기반 ≈ 1800
    DB ATR = 1_900 → diff_pct ≈ 5.6% ≤ 10% → hit
    """
    from src.api import condition as cond_mod
    from src.db import stock_master_daily as smd_mod
    from src.engine import strategy_base as sb_mod

    candles = _make_candles()

    async def _fake_fetch(ticker, days):
        return candles

    async def _fake_db_atr(ticker, days=14):
        return 1_900.0  # diff_pct ≈ 5.6% ≤ 10% → hit

    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(smd_mod, "get_atr", _fake_db_atr, raising=False)
    monkeypatch.setattr(sb_mod, "_resolve_ticker_name", lambda t: "삼성전자", raising=False)

    strat = _make_strategy(monkeypatch)
    _bypass_filters(strat)
    await strat.prepare()

    stats = strat._scan_stats
    assert stats.get("db_atr_hit", 0) >= 1, (
        f"db_atr_hit 카운터 미증가: stats={stats}"
    )
    assert stats.get("db_atr_miss", 0) == 0, (
        f"db_atr_miss 가 증가됨 (DB hit 케이스): stats={stats}"
    )
    assert stats.get("db_atr_mismatch", 0) == 0, (
        f"db_atr_mismatch 가 증가됨 (±10% 이내 케이스): stats={stats}"
    )


# ---------------------------------------------------------------------------
# G-ATR-FALLBACK: DB miss (None) → db_atr_miss 증가, KIS 캔들 fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_atr_fallback_db_miss_counter(monkeypatch):
    """get_atr None 반환 → db_atr_miss 카운터 증가, KIS 캔들 ATR 사용."""
    from src.api import condition as cond_mod
    from src.db import stock_master_daily as smd_mod
    from src.engine import strategy_base as sb_mod

    candles = _make_candles()

    async def _fake_fetch(ticker, days):
        return candles

    async def _fake_db_atr_none(ticker, days=14):
        return None  # DB miss

    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(smd_mod, "get_atr", _fake_db_atr_none, raising=False)
    monkeypatch.setattr(sb_mod, "_resolve_ticker_name", lambda t: "삼성전자", raising=False)

    strat = _make_strategy(monkeypatch)
    _bypass_filters(strat)
    await strat.prepare()

    stats = strat._scan_stats
    assert stats.get("db_atr_miss", 0) >= 1, (
        f"db_atr_miss 카운터 미증가: stats={stats}"
    )
    assert stats.get("db_atr_hit", 0) == 0, (
        f"db_atr_hit 가 증가됨 (DB miss 케이스): stats={stats}"
    )


# ---------------------------------------------------------------------------
# G-ATR-WILDER: DB ATR ±10% 초과 → db_atr_mismatch + KIS fallback + WARNING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_atr_wilder_mismatch_uses_kis_fallback(monkeypatch, caplog):
    """DB ATR 과 KIS ATR 이 ±10% 초과 시 db_atr_mismatch + KIS fallback + WARNING 로그.

    KIS 캔들 ATR ≈ 1_800 (SMA 기반, high-low=1800)
    DB ATR = 3_000 → diff_pct ≈ 66.7% > 10% → mismatch + WARNING
    """
    import logging
    from src.api import condition as cond_mod
    from src.db import stock_master_daily as smd_mod
    from src.engine import strategy_base as sb_mod

    candles = _make_candles()

    async def _fake_fetch(ticker, days):
        return candles

    async def _fake_db_atr_far(ticker, days=14):
        return 3_000.0  # diff_pct >> 10%

    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(smd_mod, "get_atr", _fake_db_atr_far, raising=False)
    monkeypatch.setattr(sb_mod, "_resolve_ticker_name", lambda t: "삼성전자", raising=False)

    strat = _make_strategy(monkeypatch)
    _bypass_filters(strat)

    with caplog.at_level(logging.WARNING):
        await strat.prepare()

    stats = strat._scan_stats
    assert stats.get("db_atr_mismatch", 0) >= 1, (
        f"db_atr_mismatch 카운터 미증가 (±10% 초과 케이스): stats={stats}"
    )
    assert stats.get("db_atr_hit", 0) == 0, (
        f"db_atr_hit 가 증가됨 (mismatch 케이스): stats={stats}"
    )
    # WARNING 로그 확인
    warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    atr_warning = any("vcp_atr_mismatch" in m for m in warning_msgs)
    assert atr_warning, (
        f"[vcp_atr_mismatch] WARNING 로그 미발화: caplog={warning_msgs}"
    )


# ---------------------------------------------------------------------------
# G-CYCLE49-PRESERVE: 사이클 49 _check_pullback_sequence 영역 무변경
# ---------------------------------------------------------------------------

def test_g_cycle49_pullback_sequence_unaffected():
    """ATR 산정 영역 변경이 _check_pullback_sequence 로직에 영향을 주지 않는다.

    사이클 49 핵심 파라미터 min_swing_atr_mult=0.5 가 DEFAULT_PARAMS 에 여전히 존재.
    _check_pullback_sequence, _atr 메서드 존재 확인 (KIS fallback 경로 영속).
    """
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    # 사이클 49 필수 파라미터 영속 (클래스 속성)
    default_params = VcpBreakoutStrategy.DEFAULT_PARAMS
    assert "min_swing_atr_mult" in default_params, (
        "DEFAULT_PARAMS 에 min_swing_atr_mult 누락 (사이클 49 영속 위반)"
    )
    assert default_params["min_swing_atr_mult"] == 0.5, (
        f"min_swing_atr_mult 기본값 변경됨: {default_params['min_swing_atr_mult']} (사이클 49: 0.5)"
    )

    # _check_pullback_sequence 메서드 존재 확인
    assert hasattr(VcpBreakoutStrategy, "_check_pullback_sequence"), (
        "_check_pullback_sequence 메서드 누락 (사이클 49 영속 위반)"
    )

    # _atr 정적 메서드 여전히 존재 (KIS fallback 경로 유지)
    assert hasattr(VcpBreakoutStrategy, "_atr"), (
        "_atr 정적 메서드 누락 (KIS fallback 경로 필수)"
    )

    # vcp_breakout.py 소스에 get_atr import + await 호출 정적 검증
    source = _VCP_SRC.read_text(encoding="utf-8")
    assert "from src.db.stock_master_daily import get_atr" in source, (
        "vcp_breakout.py 에 get_atr lazy import 누락 (사이클 125 영속 위반)"
    )
    assert "await _get_db_atr(" in source, (
        "vcp_breakout.py 에 await _get_db_atr(...) 호출 누락 (사이클 125 영속 위반)"
    )
    assert "db_atr_miss" in source, (
        "vcp_breakout.py 에 db_atr_miss 카운터 분기 누락"
    )
    assert "db_atr_hit" in source, (
        "vcp_breakout.py 에 db_atr_hit 카운터 분기 누락"
    )
    assert "vcp_atr_mismatch" in source, (
        "vcp_breakout.py 에 [vcp_atr_mismatch] WARNING 분기 누락"
    )


# ---------------------------------------------------------------------------
# G-VOLATILITY-SPIKE: db_atr > 0 but kis_atr == 0 → DB ATR 직접 사용
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_volatility_spike_db_atr_when_kis_zero(monkeypatch):
    """KIS ATR 계산값 = 0 (캔들 부족 등) 이고 DB ATR 유효 시 DB ATR 사용 + db_atr_hit.

    - kis_atr == 0 이면 diff_pct 계산 불가 (ZeroDivisionError 회피)
    - DB ATR > 0 이면 DB 값 직접 사용 (KIS ATR > 0 분기 skip)
    - db_atr_hit 카운터 증가
    """
    from src.api import condition as cond_mod
    from src.db import stock_master_daily as smd_mod
    from src.engine import strategy_base as sb_mod
    from src.engine.strategies import vcp_breakout as vcp_mod

    candles = _make_candles()

    async def _fake_fetch(ticker, days):
        return candles

    async def _fake_db_atr(ticker, days=14):
        return 2_500.0  # DB ATR 유효

    def _zero_atr(*args, **kwargs):
        return 0.0

    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(smd_mod, "get_atr", _fake_db_atr, raising=False)
    monkeypatch.setattr(sb_mod, "_resolve_ticker_name", lambda t: "삼성전자", raising=False)
    monkeypatch.setattr(vcp_mod.VcpBreakoutStrategy, "_atr", staticmethod(_zero_atr), raising=False)

    strat = _make_strategy(monkeypatch)
    _bypass_filters(strat)
    await strat.prepare()

    stats = strat._scan_stats
    # KIS ATR=0, DB ATR=2500 → DB 직접 사용 → db_atr_hit
    assert stats.get("db_atr_hit", 0) >= 1, (
        f"db_atr_hit 미증가 (DB ATR 유효 + KIS ATR=0 케이스): stats={stats}"
    )
    assert stats.get("db_atr_mismatch", 0) == 0, (
        f"db_atr_mismatch 가 증가됨 (KIS ATR=0 이면 diff 계산 불가): stats={stats}"
    )
