"""사이클 180 — VB/LTV `prepare()` 시작부 3-dict 리셋 (strat-1 HIGH/CONFIRMED) Red.

배경 (확정 결함 — domain-expert 자문 `_workspace/domain_consult/cycle180_vb_ltv_prepare_reset.md`):
- VB(`volatility_breakout.py`) / LTV(`long_tail_volatility.py`) `prepare()` 가
  `self._targets` / `self._open_confirmed` / `self._prev_price` 를 시작부에서 비우지 않음.
- 3-dict 는 prepare 의 종목별 *재할당* (VB L267/279, LTV L293/304) 외에는 프로세스 생애 동안
  절대 비워지지 않음 (`_reset_daily_state` 도 strategy.state.* 만 비우고 인스턴스 3-dict 미참조,
  직접 확인 `scheduler.py:3804~3818`). → 전일 universe 에서 빠진 종목이 영원히 잔존.
- 잔존 `_targets` → `_scanned_tickers = list(self._targets.keys())` (VB L293/LTV L318) → 구독 →
  틱 → `check_buy_signal` 이 stale `_targets[전일종목]` 의 전일 open_price/target_offset 으로
  매수 판정 → 절대규칙 "돌파 = 이전틱 < 기준가 AND 현재틱 >= 기준가" 의 *기준가 오염*.

시정 명세 (Green 이 구현 — 본 Red 는 이것을 강제):
- VB + LTV `prepare()` 시작부 (첫 `_scan_universe()` 호출 *전*) 에 정확히 3줄씩:
    self._targets.clear()
    self._open_confirmed.clear()
    self._prev_price.clear()
- 절대 clear 금지 (제외): `_limit_up_reached` (LTV), `_next_day_clear_pending` (both).

본 파일 = A(핵심 결함 재현, 현재 FAIL=Red) + B(SAFETY, 현재 PASS=불변 가드). AST 정적 가드는
`tests/unit/ast/test_cycle180_prepare_reset_ast.py` 분리 (사이클 167 source 텍스트 스캔 false-positive
교훈 → AST 토큰 기반).

가드 ID taxonomy (domain-expert §7 정합):
- G-180-EMPTY-GATE / G-180-SCANNED / G-180-STALE-BUY  (A, Red — 현재 FAIL)
- G-180-LIMITUP-EXCLUDE / G-180-NDC-EXCLUDE / G-180-EXIT-PATH  (B SAFETY, 현재 PASS)
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


# ===========================================================================
# 헬퍼 — 정상 일봉 시리즈 (KIS 키 raw, 날짜 의존 제거)
# ===========================================================================
def _valid_candles(n: int = 24, *, base_close: int = 50_000, spread: int = 600) -> list[dict]:
    """KIS `get_recent_daily_normalized` 형식 candles (DESC, 락 없음).

    사이클 176 hotfix 교훈 — 날짜 의존 제거: 모든 stck_bsop_date 를 *과거 고정 연도*(2024)로
    생성 → 어떤 CI 실행 시각에도 today_str 과 절대 불일치 → prepare 의 prev_idx=0 안정.
    prev_range > 0 + noise > 0 + target_offset > 0 보장 (VB/LTV 모두 _targets 생성).
    """
    base = date(2024, 6, 1)
    rows: list[dict] = []
    for i in range(n):
        dd = base - timedelta(days=i)
        close = base_close - i * 200
        high = close + spread + (i % 3) * 100
        low = close - (spread - 200) - (i % 2) * 100
        open_p = close - 100  # |close-open| = 100 → noise = 1 - 100/range > 0
        rows.append({
            "stck_bsop_date": dd.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_oprc": str(open_p),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "acml_vol": str(1_000_000 + i * 1000),
            "acml_tr_pbmn": str(50_000_000_000),
            "prdy_ctrt": "1.5",
        })
    return rows


def _make_vb(**overrides) -> VolatilityBreakoutStrategy:
    params = {
        "k_period": 20,
        "max_positions": 10,
        "daily_loss_limit": -5.0,
        "min_market_cap": 100_000_000_000,
        "min_trade_amount": 20_000_000_000,
        "max_scan_stocks": 100,
        "exchange": "KRX",
    }
    params.update(overrides)
    config = StrategyConfig(
        strategy_id="volatility_breakout", name="변동성돌파", params=params, enabled=True,
    )
    return VolatilityBreakoutStrategy(config)


def _make_ltv(**overrides) -> LongTailVolatilityStrategy:
    params = {
        "k_period": 20,
        "min_prdy_rate": 5.0,
        "min_market_cap": 100_000_000_000,
        "min_trade_amount": 20_000_000_000,
        "max_scan_stocks": 100,
        "exclude_consecutive_limit": 2,
        "intraday_stop_loss": -3.0,
        "limit_up_threshold": 29.0,
        "overnight_stop_loss": -5.0,
        "gap_up_threshold": 10.0,
        "trailing_stop_rate": -2.0,
        "position_ratio": 0.15,
        "max_positions": 6,
        "daily_loss_limit": -5.0,
        "exchange": "KRX",
    }
    params.update(overrides)
    config = StrategyConfig(
        strategy_id="long_tail_volatility", name="롱테일VB", params=params, enabled=True,
    )
    return LongTailVolatilityStrategy(config)


async def _run_prepare(strategy, universe: list[str], candles: list[dict]) -> None:
    """prepare 1회 실행 — _scan_universe / master_block / 어댑터 / asyncio.sleep mock.

    cycle158/cycle173 mock 패턴 답습:
    - `_scan_universe` → universe 그대로 반환 (DB 의존 제거)
    - `_apply_master_block_filter_in_prepare` → (universe, []) (차단 0)
    - `src.db.stock_master_daily.get_recent_daily_normalized` → 동일 candles (일봉 의존 제거)
    - `asyncio.sleep` → no-op (0건 재시도 hook 30초 발화 차단)
    """
    with patch.object(strategy, "_scan_universe", new=AsyncMock(return_value=list(universe))), \
            patch.object(
                strategy, "_apply_master_block_filter_in_prepare",
                new=AsyncMock(return_value=(list(universe), [])),
            ), \
            patch(
                "src.db.stock_master_daily.get_recent_daily_normalized",
                new=AsyncMock(return_value=candles),
            ), \
            patch("asyncio.sleep", new=AsyncMock(return_value=None)):
        await strategy.prepare()


# ===========================================================================
# A. 핵심 결함 재현 — 현재 코드 대비 FAIL (Red), 시정 후 PASS
# ===========================================================================


class TestStaleTickerRemoval:
    """A.1 — 전일 stale 종목 소멸 (G-180-EMPTY-GATE)."""

    @pytest.mark.asyncio
    async def test_g_180_empty_gate_vb_targets_drop_stale(self):
        """G-180-EMPTY-GATE-VB: VB 2차 prepare 후 `_targets` 가 전일 종목 A 미포함 + B 만 포함.

        현재 코드(미시정) = A 누적 잔존 → FAIL (Red).
        시정 후 = `_targets.clear()` 로 A 소멸 → PASS.
        """
        vb = _make_vb()
        universe_a = ["100001", "100002"]
        universe_b = ["200001", "200002"]  # A 와 disjoint

        await _run_prepare(vb, universe_a, _valid_candles())
        # 1차 prepare 로 A 등록 확인 (sanity — 결함 무관 전제)
        assert set(vb._targets.keys()) == set(universe_a), "1차 prepare A 등록 전제 위반"

        await _run_prepare(vb, universe_b, _valid_candles())

        keys = set(vb._targets.keys())
        assert set(universe_a).isdisjoint(keys), (
            f"VB 2차 prepare 후 전일 종목 {universe_a} 가 _targets 에 잔존: {keys} "
            f"(prepare 시작부 _targets.clear() 누락 = stale 누적 결함)"
        )
        assert keys == set(universe_b), f"VB _targets 가 당일 B 만 포함해야 함: {keys}"

    @pytest.mark.asyncio
    async def test_g_180_empty_gate_vb_open_confirmed_prev_price_drop_stale(self):
        """G-180-EMPTY-GATE-VB-AUX: VB `_open_confirmed`/`_prev_price` 도 전일 A 잔존 0.

        `_prev_price` 는 prepare 가 채우지 않으므로(틱에서만 기록) 1차 prepare 후 수동 시드 —
        '전일 틱 누적 상태'를 모사. 시정의 `_prev_price.clear()` 가 이를 비워야 함.
        """
        vb = _make_vb()
        await _run_prepare(vb, ["100001", "100002"], _valid_candles())
        # 1차 prepare 후 _open_confirmed 에 A 존재 (prepare 가 `_open_confirmed[t]={}` 설정)
        assert "100001" in vb._open_confirmed
        # 전일 틱 누적 상태 모사 (prepare 는 _prev_price 미설정 → 수동 시드)
        vb._prev_price["100001"] = {"main": 49_900}

        await _run_prepare(vb, ["200001"], _valid_candles())

        assert "100001" not in vb._open_confirmed, (
            "VB 2차 prepare 후 전일 종목 _open_confirmed 잔존 (_open_confirmed.clear() 누락)"
        )
        assert "100002" not in vb._open_confirmed
        assert "100001" not in vb._prev_price, (
            "VB 2차 prepare 후 전일 종목 _prev_price 잔존 (_prev_price.clear() 누락)"
        )

    @pytest.mark.asyncio
    async def test_g_180_empty_gate_ltv_targets_drop_stale(self):
        """G-180-EMPTY-GATE-LTV: LTV 2차 prepare 후 `_targets` 가 전일 A 미포함 + B 만 포함."""
        ltv = _make_ltv()
        universe_a = ["100001", "100002"]
        universe_b = ["200001", "200002"]

        await _run_prepare(ltv, universe_a, _valid_candles())
        assert set(ltv._targets.keys()) == set(universe_a), "1차 prepare A 등록 전제 위반"

        await _run_prepare(ltv, universe_b, _valid_candles())

        keys = set(ltv._targets.keys())
        assert set(universe_a).isdisjoint(keys), (
            f"LTV 2차 prepare 후 전일 종목 {universe_a} 가 _targets 에 잔존: {keys}"
        )
        assert keys == set(universe_b), f"LTV _targets 가 당일 B 만 포함해야 함: {keys}"

    @pytest.mark.asyncio
    async def test_g_180_empty_gate_ltv_open_confirmed_prev_price_drop_stale(self):
        """G-180-EMPTY-GATE-LTV-AUX: LTV `_open_confirmed`/`_prev_price` 전일 A 잔존 0."""
        ltv = _make_ltv()
        await _run_prepare(ltv, ["100001", "100002"], _valid_candles())
        assert "100001" in ltv._open_confirmed
        ltv._prev_price["100001"] = {"main": 49_900}

        await _run_prepare(ltv, ["200001"], _valid_candles())

        assert "100001" not in ltv._open_confirmed, (
            "LTV 2차 prepare 후 전일 종목 _open_confirmed 잔존 (_open_confirmed.clear() 누락)"
        )
        assert "100001" not in ltv._prev_price, (
            "LTV 2차 prepare 후 전일 종목 _prev_price 잔존 (_prev_price.clear() 누락)"
        )


class TestScannedTickersNoStale:
    """A.2 — `_scanned_tickers` 전일 미포함 (G-180-SCANNED)."""

    @pytest.mark.asyncio
    async def test_g_180_scanned_vb_excludes_stale(self):
        """G-180-SCANNED-VB: 2차 prepare 후 `get_scanned_tickers()` 가 전일 A 부재.

        `_scanned_tickers = list(self._targets.keys())` 이므로 stale `_targets` 가
        그대로 구독 풀로 전파됨 (결함의 1차 전파 경로). 현재 코드 = A 포함 → FAIL.
        """
        vb = _make_vb()
        await _run_prepare(vb, ["100001", "100002"], _valid_candles())
        await _run_prepare(vb, ["200001", "200002"], _valid_candles())

        scanned = vb.get_scanned_tickers()
        assert "100001" not in scanned and "100002" not in scanned, (
            f"VB get_scanned_tickers() 가 전일 종목 포함: {scanned} "
            f"(stale _targets → _scanned_tickers 전파 → 구독)"
        )
        assert set(scanned) == {"200001", "200002"}, f"당일 B 만 구독 의무: {scanned}"

    @pytest.mark.asyncio
    async def test_g_180_scanned_ltv_excludes_stale(self):
        """G-180-SCANNED-LTV: LTV 2차 prepare 후 get_scanned_tickers() 전일 A 부재."""
        ltv = _make_ltv()
        await _run_prepare(ltv, ["100001", "100002"], _valid_candles())
        await _run_prepare(ltv, ["200001", "200002"], _valid_candles())

        scanned = ltv.get_scanned_tickers()
        assert "100001" not in scanned and "100002" not in scanned, (
            f"LTV get_scanned_tickers() 가 전일 종목 포함: {scanned}"
        )
        assert set(scanned) == {"200001", "200002"}


class TestStaleTargetNoBuy:
    """A.3 — stale 타겟 매수 차단 (행위 직결, G-180-STALE-BUY)."""

    @pytest.mark.asyncio
    async def test_g_180_stale_buy_vb_blocked(self):
        """G-180-STALE-BUY-VB: 전일 종목 X 가 당일 universe 에서 빠지면 stale target 매수 0건.

        현재 코드 = `_targets[X]` 잔존 → 전일 target_offset 으로 BUY 발생 → FAIL (Red).
        시정 후 = `_targets.get(X)` None → 조기 return NONE → PASS.

        활성 보드는 session 미동작이라 `_resolve_active_board` 를 "main" 으로 고정 (보드 가드 격리,
        결함 = `_targets` 잔존 한정으로 분리).
        """
        vb = _make_vb()
        # 1차 prepare — 전일 종목 X(100001) 타겟 등록
        await _run_prepare(vb, ["100001"], _valid_candles())
        assert "100001" in vb._targets, "1차 prepare X 타겟 등록 전제 위반"
        stale_offset = vb._targets["100001"]["target_offset_base"]
        assert stale_offset > 0, "전제 — 전일 target_offset > 0"

        # 2차 prepare — 당일 universe 에서 X 제거 (Y 만)
        await _run_prepare(vb, ["200001"], _valid_candles())

        open_price = 50_000
        # stale target = open + 전일 offset (시정 후엔 _targets[X] 부재로 도달 불가)
        cross_price = open_price + stale_offset + 1_000
        with patch.object(vb, "_resolve_active_board", return_value="main"):
            s1 = vb.check_buy_signal("100001", current_price=open_price, open_price=open_price)
            s2 = vb.check_buy_signal("100001", current_price=cross_price, open_price=open_price)

        assert s1 == Signal.NONE
        assert s2 == Signal.NONE, (
            "VB 가 전일 종목 X 의 stale target 으로 BUY 발생 — "
            "전일 시가/Range 기준 진입 = 돌파 기준가 오염 (prepare 시작부 _targets.clear() 누락)"
        )

    @pytest.mark.asyncio
    async def test_g_180_stale_buy_ltv_blocked(self):
        """G-180-STALE-BUY-LTV: LTV 전일 종목 stale target 매수 0건.

        prdy_rate 필터는 본 결함과 직교 → `min_prdy_rate=0.0` 으로 격리 (stale `_targets`
        잔존 단일 변수로 결함 분리).
        """
        ltv = _make_ltv(min_prdy_rate=0.0)
        await _run_prepare(ltv, ["100001"], _valid_candles())
        assert "100001" in ltv._targets, "1차 prepare X 타겟 등록 전제 위반"
        stale_offset = ltv._targets["100001"]["target_offset_base"]
        assert stale_offset > 0

        await _run_prepare(ltv, ["200001"], _valid_candles())

        open_price = 50_000
        cross_price = open_price + stale_offset + 1_000
        with patch.object(ltv, "_resolve_active_board", return_value="main"):
            s1 = ltv.check_buy_signal("100001", current_price=open_price, open_price=open_price)
            s2 = ltv.check_buy_signal("100001", current_price=cross_price, open_price=open_price)

        assert s1 == Signal.NONE
        assert s2 == Signal.NONE, (
            "LTV 가 전일 종목 X 의 stale target 으로 BUY 발생 (prepare 시작부 _targets.clear() 누락)"
        )


# ===========================================================================
# B. SAFETY 가드 — 시정이 매도/청산 경로/제외 dict 를 건드리지 않음.
#    현재 코드에서도 PASS, 시정 후에도 PASS 의무 (Green 이 `_limit_up_reached.clear()`
#    또는 `_next_day_clear_pending=False` 를 prepare 에 잘못 추가하면 즉시 FAIL = 영구 가드).
# ===========================================================================


class TestLimitUpExcluded:
    """B.4 — `_limit_up_reached` 무변경 (LTV, G-180-LIMITUP-EXCLUDE)."""

    @pytest.mark.asyncio
    async def test_g_180_limitup_exclude_ltv_preserved(self):
        """G-180-LIMITUP-EXCLUDE: prepare 시작부 clear 가 `_limit_up_reached` 를 비우지 않음.

        상한가 익일청산 종목 보호 — clear 시 15:20 강제청산 오편입 + -3% 손절 모드 격하
        (롱테일 핵심 수익 구조 파괴, domain-expert §의제2 절대 제외).
        """
        ltv = _make_ltv()
        ltv._limit_up_reached.add("999999")

        await _run_prepare(ltv, ["200001"], _valid_candles())

        assert "999999" in ltv._limit_up_reached, (
            "prepare 가 `_limit_up_reached` 를 비움 — 상한가 익일청산 안전성 파괴 "
            "(Green 이 _limit_up_reached.clear() 를 잘못 추가하면 안 됨)"
        )


class TestNextDayClearPendingExcluded:
    """B.5 — `_next_day_clear_pending` 무변경 (VB+LTV, G-180-NDC-EXCLUDE)."""

    @pytest.mark.asyncio
    async def test_g_180_ndc_exclude_vb_preserved(self):
        """G-180-NDC-EXCLUDE-VB: prepare 후 VB `_next_day_clear_pending` 여전히 True."""
        vb = _make_vb()
        vb._next_day_clear_pending = True

        await _run_prepare(vb, ["200001"], _valid_candles())

        assert vb._next_day_clear_pending is True, (
            "prepare 가 VB `_next_day_clear_pending` 를 리셋 — 익일청산 race 가드 파괴"
        )

    @pytest.mark.asyncio
    async def test_g_180_ndc_exclude_ltv_preserved(self):
        """G-180-NDC-EXCLUDE-LTV: prepare 후 LTV `_next_day_clear_pending` 여전히 True."""
        ltv = _make_ltv()
        ltv._next_day_clear_pending = True

        await _run_prepare(ltv, ["200001"], _valid_candles())

        assert ltv._next_day_clear_pending is True, (
            "prepare 가 LTV `_next_day_clear_pending` 를 리셋 — 익일청산 race 가드 파괴"
        )


class TestExitPathUnaffected:
    """B.6 — 보유 종목 청산 경로 무영향 (G-180-EXIT-PATH).

    `check_exit_signal`/`check_force_clear` 가 3-dict 미참조이므로, prepare 가 `_targets`
    를 비워도 보유 포지션(state.positions)/`_limit_up_reached`/`_next_day_clear_pending`
    기반 청산은 정상 동작 (사이클 38 명문화 — 청산은 보드/타겟 무관 항상 작동).
    """

    @pytest.mark.asyncio
    async def test_g_180_exit_path_vb_stop_loss_after_prepare(self):
        """G-180-EXIT-PATH-VB: prepare 가 _targets 비워도 보유 종목 손절 정상 발화."""
        vb = _make_vb()
        vb.state.positions["300001"] = Position(
            ticker="300001", buy_price=10_000, quantity=10, order_no="O1",
            strategy_id="volatility_breakout",
        )

        await _run_prepare(vb, ["200001"], _valid_candles())  # _targets clear (시정 후)

        # -10% → stop_loss_rate(-3%) 이하 → STOP_LOSS (3-dict 무참조)
        sig = vb.check_exit_signal("300001", current_price=9_000, open_price=9_000)
        assert sig == Signal.STOP_LOSS, (
            "보유 종목 손절이 prepare 의 _targets clear 에 영향받음 — 청산 경로 3-dict 참조 위반"
        )
        # 15:20 강제청산 대상에 보유 종목 포함 (positions 기반, _targets 무관)
        assert "300001" in vb.check_force_clear()

    @pytest.mark.asyncio
    async def test_g_180_exit_path_ltv_stop_loss_after_prepare(self):
        """G-180-EXIT-PATH-LTV: prepare 가 _targets 비워도 LTV 보유 종목 청산 정상."""
        ltv = _make_ltv()
        ltv.state.positions["300001"] = Position(
            ticker="300001", buy_price=10_000, quantity=10, order_no="O1",
            strategy_id="long_tail_volatility",
        )

        await _run_prepare(ltv, ["200001"], _valid_candles())

        # 당일 모드 (상한가 미도달) -10% → intraday_stop_loss(-3%) 이하 → STOP_LOSS
        sig = ltv.check_exit_signal("300001", current_price=9_000, open_price=9_000)
        assert sig == Signal.STOP_LOSS, (
            "LTV 보유 종목 손절이 prepare 의 _targets clear 에 영향받음 — 청산 경로 3-dict 참조 위반"
        )
        # 상한가 모드 아님 → 15:20 강제청산 대상 포함 (_limit_up_reached 기반)
        assert "300001" in ltv.check_force_clear()
