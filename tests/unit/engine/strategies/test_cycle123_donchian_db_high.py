"""사이클 123 — donchian_swing prepare() DB 우선 신고가 계산 회귀 가드.

G-DB1: DB hit → stats["db_high_hit"] 증가 (get_donchian_high 반환값 사용)
G-DB2: DB miss (None) → stats["db_high_miss"] 증가 (KIS fallback)
G-DB3: DB hit 시에도 fetch_daily_candles 호출 영속 (사이클 14 EMA/ATR/거래량)
G-AST1: from src.db.stock_master_daily import get_donchian_high + await 호출 정적 검증

★ 사이클 173 (2026-06-22) 의미 전환 (사이클 66 K-2 패턴):
donchian prepare 일봉 source 가 어댑터 (get_recent_daily_normalized, DB 우선 + 락/신선도
KIS 폴백) 단일 source 로 통일. 신고가도 어댑터 candles 단일 source (max(highs[...])) 사용
→ get_donchian_high 별도 DB 호출 + db_high_hit/db_high_miss 카운터 폐기 (자문 §249 혼재 차단).
사이클 123 의 "DB 신고가 우선 + 별도 카운터" 설계는 어댑터 (DB 우선) 가 흡수 → 본 모듈 xfail.
173 신고가 단일 source 검증 = test_cycle173_prepare_db_equivalence.py
::test_g_eq3_donchian_high_single_source_from_candles 가 영속.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# 사이클 173 의미 전환 — get_donchian_high 별도 DB 호출 폐기 (candles 단일 source 통일)
pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=False,
        reason="사이클 173 — donchian 신고가 어댑터 candles 단일 source 통일 "
               "(get_donchian_high 별도 DB 호출 + db_high_hit/miss 카운터 폐기, 자문 §249 혼재 차단)",
    ),
]

KST = timezone(timedelta(hours=9))

# 사이클 120 ttl_bypass 답습 — 절대 경로 하드코딩 금지 (CI 환경 정합).
_DONCHIAN_SRC = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "engine"
    / "strategies"
    / "donchian_swing.py"
)

# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _make_candles(n: int = 70) -> list[dict]:
    """fetch_daily_candles 반환 형식을 모방한 캔들 리스트 (index 0 = 가장 최근).

    long_ma_period=60 → 61개 이상 필요 (len >= 61).
    fetch_days = max(65, 25)+1 = 66 → 66개 이상을 기본으로 생성.
    prev_close = 50_000 (closes[0])
    highs[1:21] 최대값 = 48_000 (i=1 기준, KIS fallback 신고가)
    """
    today = datetime.now(KST).date()
    rows = []
    for i in range(n):
        d = today - timedelta(days=i + 1)   # candles[0] = 어제
        rows.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(50_000 - i * 50),   # closes[0]=50_000
            "stck_hgpr": str(48_000 - i * 30),   # highs[1]=47_970, max≈47_970
            "stck_lwpr": str(45_000 - i * 40),
            "acml_vol": str(3_000_000 + i * 5_000),   # 거래량 충분
        })
    return rows


def _make_strategy(monkeypatch):
    """DonchianSwingStrategy 인스턴스를 mock으로 준비."""
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies import donchian_swing as ds_mod
    from src.engine.strategy_base import StrategyConfig

    config = StrategyConfig(
        strategy_id="donchian_swing",
        name="도치안 스윙",
        params={},
    )
    strat = DonchianSwingStrategy(config)

    # _scan_universe → 005930 단일 종목 반환 (DB/KIS 호출 불필요)
    async def _fake_scan():
        return ["005930"]

    strat._scan_universe = _fake_scan
    return strat, ds_mod


# ---------------------------------------------------------------------------
# G-DB1: DB hit → db_high_hit 카운터 증가
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_db1_db_hit_increments_counter(monkeypatch):
    """get_donchian_high 가 유효값(>0) 반환 시 db_high_hit 카운터가 증가한다."""
    from src.api import condition as cond_mod
    from src.db import stock_master_daily as smd_mod
    from src.engine import strategy_base as sb_mod

    candles = _make_candles()

    async def _fake_fetch(ticker, days):
        return candles

    async def _fake_db_high(ticker, days=20):
        return 47_000  # 유효한 DB 신고가

    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(smd_mod, "get_donchian_high", _fake_db_high, raising=False)
    monkeypatch.setattr(sb_mod, "_resolve_ticker_name", lambda t: "삼성전자", raising=False)

    strat, _ = _make_strategy(monkeypatch)
    await strat.prepare()

    stats = strat._scan_stats
    assert stats.get("db_high_hit", 0) >= 1, (
        f"db_high_hit 카운터 미증가: stats={stats}"
    )
    assert stats.get("db_high_miss", 0) == 0, (
        f"db_high_miss 가 증가됨 (DB hit 케이스): stats={stats}"
    )


# ---------------------------------------------------------------------------
# G-DB2: DB miss (None) → db_high_miss 카운터 증가
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_db2_db_miss_increments_counter(monkeypatch):
    """get_donchian_high 가 None 반환 시 db_high_miss 카운터가 증가하고 KIS fallback 사용."""
    from src.api import condition as cond_mod
    from src.db import stock_master_daily as smd_mod
    from src.engine import strategy_base as sb_mod

    candles = _make_candles()

    async def _fake_fetch(ticker, days):
        return candles

    async def _fake_db_high_none(ticker, days=20):
        return None  # DB miss

    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(smd_mod, "get_donchian_high", _fake_db_high_none, raising=False)
    monkeypatch.setattr(sb_mod, "_resolve_ticker_name", lambda t: "삼성전자", raising=False)

    strat, _ = _make_strategy(monkeypatch)
    await strat.prepare()

    stats = strat._scan_stats
    assert stats.get("db_high_miss", 0) >= 1, (
        f"db_high_miss 카운터 미증가: stats={stats}"
    )
    assert stats.get("db_high_hit", 0) == 0, (
        f"db_high_hit 가 증가됨 (DB miss 케이스): stats={stats}"
    )


# ---------------------------------------------------------------------------
# G-DB3: DB hit 시에도 fetch_daily_candles 호출 영속 (사이클 14)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_db3_fetch_daily_candles_always_called(monkeypatch):
    """get_donchian_high 성공 시에도 fetch_daily_candles 는 반드시 호출된다.

    사이클 14 영속: EMA/ATR/거래량 계산은 KIS 일봉 데이터가 필수.
    DB 신고가 도입으로 candle fetch 자체가 생략되어선 안 된다.
    """
    from src.api import condition as cond_mod
    from src.db import stock_master_daily as smd_mod
    from src.engine import strategy_base as sb_mod

    candles = _make_candles()
    fetch_call_count = {"n": 0}

    async def _counting_fetch(ticker, days):
        fetch_call_count["n"] += 1
        return candles

    async def _fake_db_high(ticker, days=20):
        return 47_000  # DB hit

    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _counting_fetch, raising=False)
    monkeypatch.setattr(smd_mod, "get_donchian_high", _fake_db_high, raising=False)
    monkeypatch.setattr(sb_mod, "_resolve_ticker_name", lambda t: "삼성전자", raising=False)

    strat, _ = _make_strategy(monkeypatch)
    await strat.prepare()

    assert fetch_call_count["n"] >= 1, (
        f"fetch_daily_candles 미호출: count={fetch_call_count['n']} (사이클 14 영속 위반)"
    )


# ---------------------------------------------------------------------------
# G-AST1: import + await 호출 정적 검증
# ---------------------------------------------------------------------------

def test_g_ast1_import_and_call_site_present():
    """donchian_swing.py prepare() 내부에 lazy import + await 호출이 존재한다.

    - from src.db.stock_master_daily import get_donchian_high
    - await get_donchian_high(...) 호출
    - db_high_hit / db_high_miss 카운터 분기

    미래 리팩토링으로 해당 영역이 제거되는 경우 즉시 검출.
    """
    source = _DONCHIAN_SRC.read_text(encoding="utf-8")

    assert "from src.db.stock_master_daily import get_donchian_high" in source, (
        "donchian_swing.py 에 get_donchian_high lazy import 누락"
    )
    assert "await get_donchian_high(" in source, (
        "donchian_swing.py 에 await get_donchian_high(...) 호출 누락"
    )
    assert "db_high_miss" in source, (
        "donchian_swing.py 에 db_high_miss 카운터 분기 누락"
    )
    assert "db_high_hit" in source, (
        "donchian_swing.py 에 db_high_hit 카운터 분기 누락"
    )

    # AST 파싱으로 문법 오류 없음 확인
    try:
        ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"donchian_swing.py AST 파싱 실패: {e}")
