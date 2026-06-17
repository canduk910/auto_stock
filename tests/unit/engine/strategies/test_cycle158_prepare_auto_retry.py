"""사이클 158 Q2 — 5 전략 prepare 0건 시 자동 재시도 hook 회귀 가드.

운영 사례 (2026-06-17 08:13:14 ~ 08:16:39 KST):
- VB/LTV/donchian/BFB 유니버스 0/0종목 (stock_master 0건 race)
- _full_universe_load_task_loop start() 직후 즉시 1회 실행 ~3분 소요
- _boot() prepare() 호출이 적재 *전* 발생 → 0건 silent

근본 원인:
- _boot() line 71-75 = registry.enabled() 순회 prepare
- _full_universe_load_task = create_task 비동기 발화
- prepare가 적재 미완료 상태 진입

시정 (옵션 B):
- 5 전략 (VB/LTV/donchian/BFB/VCP) prepare 영역 stock_master 0건 시 자동 재시도
- 재시도 cap 3회 + sleep 30초
- _scan_universe() 0건 반환 시 retry hook

회귀 가드 5 케이스 (VB 단독 — 동일 패턴 4 전략 D+1 인계):
- G-158-Q2-1: VB prepare 0건 시 자동 재시도 hook
- G-158-Q2-2: 재시도 횟수 cap = 3회
- G-158-Q2-3: 재시도 간격 sleep 30초
- G-158-Q2-4: 정상 케이스 재시도 0회 (회귀 보존)
- G-158-Q2-5: momentum 영역 변경 0 (실시간 본질)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import StrategyConfig


# ──────────────────────────────────────────────────────────────────────
# G-158-Q2-1 — VB prepare 0건 시 자동 재시도 hook 발화
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G_158_Q2_1_vb_prepare_zero_triggers_retry() -> None:
    """VB _scan_universe() 첫 호출 0건 → 자동 재시도 → 두번째 호출 1건 반환.

    재시도 hook 발화 시 _scan_universe 가 최소 2회 호출되어야 한다.
    """
    config = StrategyConfig(strategy_id="volatility_breakout", name="변동성돌파", params={}, enabled=True, weight=1.0)
    s = VolatilityBreakoutStrategy(config)

    call_count = {"n": 0}

    async def _mock_scan_universe() -> list[str]:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return []  # 첫 호출 0건 (stock_master race)
        return ["005930"]  # 두번째 정상

    with patch.object(s, "_scan_universe", side_effect=_mock_scan_universe), \
         patch.object(s, "_apply_master_block_filter_in_prepare", new=AsyncMock(return_value=(["005930"], []))), \
         patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=None)), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        await s.prepare()

    assert call_count["n"] >= 2, (
        f"0건 시 재시도 의무 (실측 _scan_universe 호출 {call_count['n']}회, 운영 race 영역)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-158-Q2-2 — 재시도 횟수 cap = 3회
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G_158_Q2_2_retry_cap_max_3() -> None:
    """전부 0건이어도 최대 4회 (초기 1 + 재시도 3) 호출 후 종료."""
    config = StrategyConfig(strategy_id="volatility_breakout", name="변동성돌파", params={}, enabled=True, weight=1.0)
    s = VolatilityBreakoutStrategy(config)

    call_count = {"n": 0}

    async def _mock_scan_universe() -> list[str]:
        call_count["n"] += 1
        return []  # 영구 0건

    with patch.object(s, "_scan_universe", side_effect=_mock_scan_universe), \
         patch.object(s, "_apply_master_block_filter_in_prepare", new=AsyncMock(return_value=([], []))), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        await s.prepare()

    # 초기 1회 + 재시도 cap 3회 = 최대 4회
    assert call_count["n"] <= 4, (
        f"재시도 cap=3 초과 (실측 {call_count['n']}회, 무한 루프 위험 영역)"
    )
    assert call_count["n"] >= 4, (
        f"재시도 cap 미달 (실측 {call_count['n']}회, cap=3 의무)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-158-Q2-3 — 재시도 간격 sleep 30초 (asyncio.sleep mock)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G_158_Q2_3_retry_sleep_30_seconds() -> None:
    """재시도 간격 = asyncio.sleep(30) 호출 검증.

    운영 race ~3분 소요 영역 = 30초 × 3회 = 90초 안전 마진.
    """
    config = StrategyConfig(strategy_id="volatility_breakout", name="변동성돌파", params={}, enabled=True, weight=1.0)
    s = VolatilityBreakoutStrategy(config)

    async def _empty_scan() -> list[str]:
        return []

    sleep_mock = AsyncMock(return_value=None)
    with patch.object(s, "_scan_universe", side_effect=_empty_scan), \
         patch.object(s, "_apply_master_block_filter_in_prepare", new=AsyncMock(return_value=([], []))), \
         patch("asyncio.sleep", new=sleep_mock):
        await s.prepare()

    # 30초 sleep 호출 ≥1건 (3회 재시도 = 3 sleep)
    sleep_30_calls = [c for c in sleep_mock.call_args_list if c.args and c.args[0] == 30]
    assert len(sleep_30_calls) >= 1, (
        f"재시도 sleep(30) 호출 부재 (전체 sleep 호출 {sleep_mock.call_args_list})"
    )


# ──────────────────────────────────────────────────────────────────────
# G-158-Q2-4 — 정상 케이스 재시도 0회 (회귀 보존)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G_158_Q2_4_normal_case_no_retry() -> None:
    """첫 호출 1건 ≥ 반환 시 재시도 0회 (회귀 보존)."""
    config = StrategyConfig(strategy_id="volatility_breakout", name="변동성돌파", params={}, enabled=True, weight=1.0)
    s = VolatilityBreakoutStrategy(config)

    call_count = {"n": 0}

    async def _mock_scan_universe() -> list[str]:
        call_count["n"] += 1
        return ["005930"]

    sleep_mock = AsyncMock(return_value=None)
    with patch.object(s, "_scan_universe", side_effect=_mock_scan_universe), \
         patch.object(s, "_apply_master_block_filter_in_prepare", new=AsyncMock(return_value=(["005930"], []))), \
         patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=None)), \
         patch("asyncio.sleep", new=sleep_mock):
        await s.prepare()

    assert call_count["n"] == 1, (
        f"정상 케이스 재시도 의무 0 (실측 {call_count['n']}회)"
    )
    # 정상 케이스 sleep(30) 호출 0건 (회귀 보존)
    sleep_30_calls = [c for c in sleep_mock.call_args_list if c.args and c.args[0] == 30]
    assert len(sleep_30_calls) == 0, "정상 케이스 재시도 sleep 0회 의무"


# ──────────────────────────────────────────────────────────────────────
# G-158-Q2-5 — momentum 영역 변경 0 (실시간 본질)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G_158_Q2_5_momentum_prepare_unchanged() -> None:
    """momentum prepare empty stub 영속 (사이클 132 funnel 미적재 영역)."""
    config = StrategyConfig(strategy_id="momentum", name="모멘텀", params={}, enabled=True, weight=1.0)
    s = MomentumStrategy(config)

    # prepare 호출이 어떤 sleep도 발화하지 않아야 함 (재시도 hook 영역 외)
    sleep_mock = AsyncMock(return_value=None)
    with patch("asyncio.sleep", new=sleep_mock):
        await s.prepare()

    # momentum은 empty stub = sleep 0건
    sleep_30_calls = [c for c in sleep_mock.call_args_list if c.args and c.args[0] == 30]
    assert len(sleep_30_calls) == 0, "momentum 영역 sleep(30) 호출 0 (실시간 본질 영역 영속)"
