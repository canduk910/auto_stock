"""사이클 64 (2026-06-06) Red — F 카테고리: scanner 가격 필터 integration (4 케이스).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§F)
> **설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` §5.3
> **자문 응답 Q7-1 (HIGH)** + **Q7-4 (MEDIUM, funnel hook step_no=98)**

요구 행위 (Red 단계 모두 AttributeError / ImportError 정답):

- F-1: `subscribe_filtered_stocks` 내부 hook — `_apply_price_filter` 호출 후 WS 구독 (E2E)
- F-2: Settings PUT → `invalidate_price_filter_cache_scanner()` 즉시 호출 → 다음 scan 반영
- F-3: 보유/익일청산 보호 — Settings 변경 후에도 보호 종목 통과 (사이클 32 R4 답습)
- F-4 (Q7-4): `_apply_price_filter` 내부 funnel `step_no=98` snapshot hook 호출 (자문 옵션)

위험 등급 MEDIUM (통합 정합성).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


def _make_pf(min_price=0, max_price=0):
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


def _make_basics(ticker: str, prdy_clpr: int):
    from src.models.stock import StockBasics
    return StockBasics(
        ticker=ticker, name="", excg_dvsn_cd="",
        nxt_tradable=True, krx_halted=False, admin_item=False,
        raw={"prdy_clpr": str(prdy_clpr)},
    )


# ---------------------------------------------------------------------------
# F-1: E2E — subscribe_filtered_stocks 내부 hook → WS 구독 후보 축소
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F1_subscribe_filtered_stocks_internal_hook():
    """F-1 (E2E): `subscribe_filtered_stocks(tickers=[저가, 통과, 고가], ...)` 호출 시
    내부 `_apply_price_filter` hook 으로 1 종목만 구독.

    Q4 자문 옵션 A — 단일 진입점 `subscribe_filtered_stocks` 내부 hook.
    호출자 시그니처 변경 0 (4 호출처 자동 통과 — scheduler.py L481 / L522 / L542 / L1961).
    """
    from src.engine import scanner

    pf = _make_pf(min_price=5000, max_price=100_000)

    async def fake_sm_get(ticker):
        return {
            "AAAAAA": _make_basics("AAAAAA", prdy_clpr=2000),   # 저가 차단
            "BBBBBB": _make_basics("BBBBBB", prdy_clpr=50_000), # 통과
            "CCCCCC": _make_basics("CCCCCC", prdy_clpr=500_000),# 고가 차단
        }.get(ticker)

    # ws_pool mock — 실제 구독 호출 추적
    mock_pool = MagicMock()
    mock_pool.subscribe = AsyncMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value=set())

    # 캐시 사전 무효화 (테스트 격리)
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()

    # protected 비어있음 — 매수 후보만
    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.engine.scanner.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner._collect_protected_tickers_for_scanner",
               return_value=set()), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        # priority_groups=None 평탄 처리 분기 — kis_ws.subscribe 직접 호출 (legacy)
        # Q4 옵션 A: subscribe_filtered_stocks 내부 첫 줄에 filter hook 추가
        with patch("src.engine.scanner.kis_ws") as mock_ws:
            mock_ws.subscribe = AsyncMock()
            await scanner.subscribe_filtered_stocks(
                ["AAAAAA", "BBBBBB", "CCCCCC"],
                source_counts=None,
            )

            # subscribe 호출은 통과 종목 1개 (BBBBBB) 만
            subscribed_tickers = []
            for c in mock_ws.subscribe.call_args_list:
                # call args: (tr_id, ticker, ...)
                if len(c.args) >= 2:
                    subscribed_tickers.append(c.args[1])

            # AAAAAA / CCCCCC 차단 검증 (BBBBBB 만 구독)
            assert "AAAAAA" not in subscribed_tickers, "저가 차단 종목 구독됨 — hook 미적용"
            assert "CCCCCC" not in subscribed_tickers, "고가 차단 종목 구독됨 — hook 미적용"


# ---------------------------------------------------------------------------
# F-2: Settings PUT race — invalidate 즉시 반영
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F2_settings_put_invalidate_immediate_apply():
    """F-2: Settings PUT 시 `invalidate_price_filter_cache_scanner()` 호출 후
    다음 `_apply_price_filter` 호출 시 즉시 새 설정 반영.

    Q5 자문 — 즉시 반영 (5분 grace 금지). 다만 Q7-1: 즉시 unsubscribe 안 함.
    """
    from src.engine import scanner

    # 초기: 활성 (min=5000) → invalidate 후 비활성 (0/0)
    pf_active = _make_pf(min_price=5000, max_price=0)
    pf_off = _make_pf(min_price=0, max_price=0)
    db_get_mock = AsyncMock(side_effect=[pf_active, pf_off])

    # 캐시 사전 무효화
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()

    candidates = ["005930"]

    with patch("src.engine.scanner.get_price_filter", db_get_mock), \
         patch("src.db.stock_master.get",
               AsyncMock(return_value=_make_basics("005930", prdy_clpr=3000))), \
         patch("src.db.system_logs.write_log", AsyncMock()):

        # 1차 호출 — 활성 + 차단
        result1 = await scanner._apply_price_filter(candidates, protected_tickers=set())
        assert result1 == [], "1차 활성 시 차단 실패"

        # Settings PUT race — invalidate
        scanner.invalidate_price_filter_cache_scanner()

        # 2차 호출 — 비활성 (캐시 무효화 즉시 반영)
        result2 = await scanner._apply_price_filter(candidates, protected_tickers=set())
        assert result2 == candidates, (
            "Settings PUT 직후 즉시 반영 실패 — Q5 자문 위반 (5분 grace 금지)"
        )

    # DB 호출 2건 (1차 + 2차)
    assert db_get_mock.call_count == 2, (
        f"invalidate 후 DB 재호출 결함 (실제 {db_get_mock.call_count}건)"
    )


# ---------------------------------------------------------------------------
# F-3: 보유/익일청산 보호 — Settings 변경 후에도 보호 종목 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F3_protected_tickers_preserved_across_settings_change():
    """F-3: Settings 변경 (임계 강화) 후에도 보유/익일청산 종목 항상 통과.

    사이클 32 R4 universe guard 답습 통합 검증.
    """
    from src.engine import scanner

    # 1차: min=5000 / 2차: min=50_000 (강화 — 보유 005930 prdy=3000 더욱 명백히 차단 대상)
    pf1 = _make_pf(min_price=5000)
    pf2 = _make_pf(min_price=50_000)
    db_get_mock = AsyncMock(side_effect=[pf1, pf2])

    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()

    candidates = ["005930"]  # 보유 종목 가정
    protected = {"005930"}

    with patch("src.engine.scanner.get_price_filter", db_get_mock), \
         patch("src.db.stock_master.get",
               AsyncMock(return_value=_make_basics("005930", prdy_clpr=3000))), \
         patch("src.db.system_logs.write_log", AsyncMock()):

        # 1차 — 보호 (필터 통과)
        result1 = await scanner._apply_price_filter(candidates, protected_tickers=protected)
        assert result1 == ["005930"], "1차 보호 결함"

        # Settings 강화
        scanner.invalidate_price_filter_cache_scanner()

        # 2차 — 강화된 필터에도 보호
        result2 = await scanner._apply_price_filter(candidates, protected_tickers=protected)
        assert result2 == ["005930"], (
            "임계 강화 후에도 보유 종목 보호 의무 — 사이클 32 R4 답습 위반"
        )


# ---------------------------------------------------------------------------
# F-4 (Q7-4 MEDIUM): funnel step_no=98 snapshot hook
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F4_apply_price_filter_funnel_hook_step_no_98():
    """F-4 (Q7-4 자문, MEDIUM): `_apply_price_filter` 차단 발생 시
    `strategy_funnel.insert_snapshot(step_no=98)` 호출 (운영자 가시화).

    자문 §Q7-4 — funnel `step_no=98 = price_filter_scanner` 별도 단계 분리.
    survived_count + excluded_count + reason 분류 (below_min/above_max/no_prev_close).

    graceful — funnel hook 실패는 매수 흐름 영향 0 (try/except).
    """
    from src.engine import scanner

    candidates = ["AAAAAA", "BBBBBB", "CCCCCC"]
    pf = _make_pf(min_price=5000, max_price=100_000)

    async def fake_sm_get(ticker):
        return {
            "AAAAAA": _make_basics("AAAAAA", prdy_clpr=2000),
            "BBBBBB": _make_basics("BBBBBB", prdy_clpr=50_000),
            "CCCCCC": _make_basics("CCCCCC", prdy_clpr=500_000),
        }.get(ticker)

    funnel_insert_mock = AsyncMock()

    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()
    if hasattr(scanner, "reset_price_filter_daily_state"):
        scanner.reset_price_filter_daily_state()

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.db.strategy_funnel.insert_snapshot", funnel_insert_mock), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == ["BBBBBB"]

    # funnel insert_snapshot 호출 검증 (step_no=98)
    # Q7-4 자문: optional hook 이라 graceful — 실패해도 매수 흐름 영향 0
    # 호출 발생 시 step_no=98 명시 의무
    if funnel_insert_mock.call_count > 0:
        call_kwargs = funnel_insert_mock.call_args.kwargs
        assert call_kwargs.get("step_no") == 98, (
            f"funnel step_no=98 (Q7-4 자문) 위반: kwargs={call_kwargs}"
        )
        # step_name 검증 (자문 명시)
        step_name = call_kwargs.get("step_name", "")
        assert "price_filter" in step_name, (
            f"step_name 결함 — 'price_filter' 포함 의무: {step_name}"
        )
    else:
        # Red 단계 — hook 미구현 시 fail (Green 단계에서 구현 의무)
        pytest.fail(
            "Q7-4 funnel hook 누락 — `_apply_price_filter` 가 차단 발생 시 "
            "strategy_funnel.insert_snapshot(step_no=98) 호출 의무"
        )
