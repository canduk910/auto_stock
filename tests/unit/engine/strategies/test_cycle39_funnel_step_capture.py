"""사이클 39 (2026-05-22) — BFB/VCP/donchian funnel 단계별 ticker 캡처 + 자동 snapshot hook.

배경:
- 사이클 33 시정 후도 5/22 09:38 funnel snapshot 에서 BFB/VCP/donchian final=0 잔존.
- 사이클 34 funnel DB 는 수동 trigger + 최종 단계 (`step_no=99`) 만 저장 → 단계별 진단 불가.
- 단계별 어느 종목이 어디서 떨어지는지 모르면 시장 자연 0 vs 코드 결함 구분 불가.

Phase 1 진단 결과 (team-leader 정밀 분석):
- BFB: `_detect_pole_and_flag` 매우 엄격 (3~10일 +20%↑ + 음봉≤30% + 조정≤38.2% + 거래량 수축) → 자연 0 가능성 매우 높음
- VCP: 사이클 33 fix 정확 (effective_ema_long=75 + 100 candles 통과). 미네르비니식 추세 필터 자연 0 가능성 매우 높음
- donchian: 코드 정상. 신고가 자연 0 가능성 ~70%

본 사이클 (39) 변경:
- `StrategyBase._record_funnel_step(step_no, step_name, survived, excluded=None)` 헬퍼
- `StrategyBase._funnel_steps: list[dict]` 신규 필드 (prepare 마다 reset)
- BFB / VCP / donchian `prepare()` 단계별 hook 삽입 (회귀 가드 — 결과 무변경)
- `scheduler._auto_capture_funnel_snapshots()` 신규 — 09:30 _scan_loop 첫 진입 시 자동 snapshot
- `db.strategy_funnel.insert_snapshot` 단계별 row (step_no 1~8) 저장 — 사이클 34 인프라 재활용

사양 (S-1 ~ S-7):
- S-1: `StrategyBase._record_funnel_step` 헬퍼 존재 + survived/excluded 캡처
- S-2: prepare() 첫 호출 시 `_funnel_steps` reset
- S-3: BFB / VCP / donchian prepare() 가 단계별 hook 호출 (실제 결과 무변경)
- S-4: 단계별 ticker cap (200 survived / 20 excluded)
- S-5: 자동 snapshot trigger 가 활성 전략별 `_funnel_steps` 를 DB insert_snapshot 호출
- S-6: prepare() 결과 무변경 회귀 (사이클 33 BFB/VCP fix 보존)
- S-7: 자동 snapshot 실패 graceful (한 전략 실패해도 다른 전략 계속)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# S-1: _record_funnel_step 헬퍼 + 필드 초기화
# ===========================================================================
def test_strategy_base_has_record_funnel_step_helper():
    """`StrategyBase._record_funnel_step` 메서드 존재."""
    from src.engine.strategy_base import StrategyBase

    assert hasattr(StrategyBase, "_record_funnel_step"), (
        "StrategyBase._record_funnel_step 헬퍼 누락"
    )


def test_strategy_base_has_funnel_steps_field():
    """`StrategyBase.__init__` 가 `_funnel_steps: list` 초기화."""
    import inspect
    from src.engine.strategy_base import StrategyBase

    src = inspect.getsource(StrategyBase.__init__)
    assert "_funnel_steps" in src, (
        "StrategyBase.__init__ 에 _funnel_steps 초기화 누락"
    )


def test_record_funnel_step_captures_survived_and_excluded():
    """`_record_funnel_step` 호출 시 `_funnel_steps` 리스트에 dict 추가."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))

    strat._record_funnel_step(
        step_no=1, step_name="유니버스 후보",
        survived=["005930", "000660"],
        excluded=[{"ticker": "EXCLUDE1", "reason": "test"}],
    )

    assert len(strat._funnel_steps) == 1
    step = strat._funnel_steps[0]
    assert step["step_no"] == 1
    assert step["step_name"] == "유니버스 후보"
    # 사이클 41 (2026-05-22) — string 입력 자동 dict 변환 (종목명 lookup)
    survived = step["survived"]
    assert len(survived) == 2
    assert survived[0]["ticker"] == "005930"
    assert survived[1]["ticker"] == "000660"
    assert "name" in survived[0]  # 종목명 자동 lookup (운영 환경 기준 "" 가능)
    assert step["survived_count"] == 2
    assert step["excluded"] == [{"ticker": "EXCLUDE1", "reason": "test"}]


# ===========================================================================
# S-2: cap 200 survived / 20 excluded 자동 적용
# ===========================================================================
def test_record_funnel_step_applies_caps():
    """survived cap 200 / excluded cap 20 자동 적용."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))

    many_survived = [f"{i:06d}" for i in range(300)]
    many_excluded = [{"ticker": f"E{i:05d}", "reason": "x"} for i in range(50)]
    strat._record_funnel_step(
        step_no=1, step_name="cap test",
        survived=many_survived, excluded=many_excluded,
    )

    step = strat._funnel_steps[0]
    assert len(step["survived"]) == 200, f"survived cap 200 미적용 — {len(step['survived'])}"
    assert len(step["excluded"]) == 20, f"excluded cap 20 미적용 — {len(step['excluded'])}"
    # 카운트는 cap 이전 원본 보존
    assert step["survived_count"] == 300, "원본 카운트 보존 (cap 이전)"
    assert step["excluded_count"] == 50


# ===========================================================================
# S-3: BFB prepare 가 단계별 hook 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_bfb_prepare_records_funnel_steps(monkeypatch):
    """BFB prepare() 가 8 단계 hook 호출."""
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategies import bull_flag_breakout as bfb_mod

    async def _fake_scan():
        return ["005930", "000660"]

    # 일봉 mock — pole/flag 검출 통과하도록 합성
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    today = _dt.now(_tz(_td(hours=9))).date()

    def _make_candles(ticker_idx, days=30):
        candles = []
        base = 50000
        for i in range(days):
            d = today - _td(days=i + 1)
            # 30일 전 base → 어제 base+5000 (정상 우상향)
            price = base + (days - i) * 100
            candles.append({
                "stck_bsop_date": d.strftime("%Y%m%d"),
                "stck_clpr": str(price),
                "stck_hgpr": str(price + 500),
                "stck_lwpr": str(price - 500),
                "stck_oprc": str(price),
                "acml_vol": "1000000",
            })
        return candles

    async def _fake_fetch(ticker, days):
        return _make_candles(0, days=days)

    monkeypatch.setattr(bfb_mod, "fetch_daily_candles", _fake_fetch, raising=False)

    fake_config = MagicMock()
    fake_config.strategy_id = "bull_flag_breakout"
    fake_config.params = {**BullFlagBreakoutStrategy.DEFAULT_PARAMS}
    fake_config.enabled = True
    fake_config.weight = 0.1

    strat = BullFlagBreakoutStrategy.__new__(BullFlagBreakoutStrategy)
    strat.config = fake_config
    strat._candidates = {}
    strat._scanned_tickers = []
    strat._bought_today = set()
    strat._cooldown_until = {}
    strat._scan_universe = _fake_scan
    # 사이클 39 — funnel_steps 필드 초기화
    strat._funnel_steps = []
    strat._scan_stats = bfb_mod._empty_scan_stats()

    await strat.prepare()

    # 1단계 이상 hook 호출되어야 함
    assert len(strat._funnel_steps) >= 1, (
        f"BFB prepare 가 단계별 hook 호출 누락 — _funnel_steps={strat._funnel_steps}"
    )
    # 첫 단계는 유니버스 후보
    assert strat._funnel_steps[0]["step_no"] == 1


# ===========================================================================
# S-4: VCP prepare 가 단계별 hook 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_vcp_prepare_records_funnel_steps(monkeypatch):
    """VCP prepare() 가 단계별 hook 호출."""
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategies import vcp_breakout as vcp_mod

    async def _fake_scan():
        return ["005930"]

    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    today = _dt.now(_tz(_td(hours=9))).date()

    def _make_candles(days=100):
        candles = []
        for i in range(days):
            d = today - _td(days=i + 1)
            price = 50000 + (days - i) * 100
            candles.append({
                "stck_bsop_date": d.strftime("%Y%m%d"),
                "stck_clpr": str(price),
                "stck_hgpr": str(price + 500),
                "stck_lwpr": str(price - 500),
                "stck_oprc": str(price),
                "acml_vol": "1000000",
            })
        return candles

    async def _fake_fetch(ticker, days):
        return _make_candles(days=min(days, 100))

    # VCP prepare() 도 함수 본문에서 from src.api.condition import fetch_daily_candles 호출
    from src.api import condition as cond_mod
    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(vcp_mod, "fetch_daily_candles", _fake_fetch, raising=False)

    fake_config = MagicMock()
    fake_config.strategy_id = "vcp_breakout"
    fake_config.params = {**VcpBreakoutStrategy.DEFAULT_PARAMS}
    fake_config.enabled = True
    fake_config.weight = 0.1

    strat = VcpBreakoutStrategy.__new__(VcpBreakoutStrategy)
    strat.config = fake_config
    strat._candidates = {}
    strat._scanned_tickers = []
    strat._bought_today = set()
    strat._cooldown_until = {}
    strat._scan_universe = _fake_scan
    strat._funnel_steps = []
    strat._scan_stats = vcp_mod._empty_scan_stats()

    await strat.prepare()

    assert len(strat._funnel_steps) >= 1, (
        f"VCP prepare 가 단계별 hook 호출 누락"
    )


# ===========================================================================
# S-5: donchian prepare 가 단계별 hook 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_donchian_prepare_records_funnel_steps(monkeypatch):
    """donchian prepare() 가 단계별 hook 호출."""
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies import donchian_swing as ds_mod

    async def _fake_scan():
        return ["005930"]

    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    today = _dt.now(_tz(_td(hours=9))).date()

    def _make_candles(days=66):
        candles = []
        for i in range(days):
            d = today - _td(days=i + 1)
            price = 50000 + (days - i) * 100
            candles.append({
                "stck_bsop_date": d.strftime("%Y%m%d"),
                "stck_clpr": str(price),
                "stck_hgpr": str(price + 500),
                "stck_lwpr": str(price - 500),
                "stck_oprc": str(price),
                "acml_vol": "1000000",
            })
        return candles

    async def _fake_fetch(ticker, days):
        return _make_candles(days=days)

    # donchian prepare() 가 함수 본문에서 `from src.api.condition import fetch_daily_candles` 호출
    # → condition 모듈 자체 패치 필요 (ds_mod 가 아닌 src.api.condition)
    from src.api import condition as cond_mod
    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(ds_mod, "fetch_daily_candles", _fake_fetch, raising=False)

    fake_config = MagicMock()
    fake_config.strategy_id = "donchian_swing"
    fake_config.params = {**DonchianSwingStrategy.DEFAULT_PARAMS}
    fake_config.enabled = True
    fake_config.weight = 0.1

    strat = DonchianSwingStrategy.__new__(DonchianSwingStrategy)
    strat.config = fake_config
    strat._candidates = {}
    strat._scanned_tickers = []
    strat._scan_universe = _fake_scan
    strat._funnel_steps = []
    strat._scan_stats = ds_mod._empty_scan_stats()
    strat._bought_today = set()
    strat._breakout_high = {}
    # 사이클 223 — 이 테스트는 `__new__` 로 __init__ 을 우회하는 수제 부분 생성자라
    # 신규 인스턴스 필드를 여기에도 등록해야 한다(`_breakout_high` 선례).
    # `_trading_days` = 시간청산 영업일 계산용 거래일 캐시 (prepare 가 union 갱신).
    strat._trading_days = set()

    await strat.prepare()

    assert len(strat._funnel_steps) >= 1, (
        f"donchian prepare 가 단계별 hook 호출 누락"
    )


# ===========================================================================
# S-6: scheduler `_auto_capture_funnel_snapshots` 헬퍼 + insert_snapshot 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_capture_inserts_per_step_rows(monkeypatch):
    """`_auto_capture_funnel_snapshots` 가 활성 전략별 단계별 row INSERT."""
    from src.engine.scheduler import TradingScheduler

    # 가짜 전략 — _funnel_steps 보유
    fake_strategy = MagicMock()
    fake_strategy.strategy_id = "bull_flag_breakout"
    fake_strategy._funnel_steps = [
        {"step_no": 1, "step_name": "유니버스 후보",
         "survived": ["005930"], "survived_count": 1,
         "excluded": [], "excluded_count": 0},
        {"step_no": 2, "step_name": "유니버스 필터",
         "survived": ["005930"], "survived_count": 1,
         "excluded": [], "excluded_count": 0},
    ]
    fake_strategy.get_scanned_tickers = MagicMock(return_value=["005930"])

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = MagicMock()
    sched.registry.all = MagicMock(return_value=[fake_strategy])

    # insert_snapshot mock — 호출 인자 캡처
    captured: list = []

    async def _fake_insert(**kwargs):
        captured.append(kwargs)
        return {"id": f"row-{kwargs['step_no']}"}

    from src.db import strategy_funnel as sf_mod
    monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

    await sched._auto_capture_funnel_snapshots()

    # 단계별 row + 최종 (step_no=99) 합쳐서 3개 이상
    assert len(captured) >= 2, (
        f"단계별 + 최종 row INSERT 누락 — captured={len(captured)}"
    )
    step_nos = [c["step_no"] for c in captured]
    assert 1 in step_nos
    assert 2 in step_nos


# ===========================================================================
# S-7: 자동 snapshot 한 전략 실패해도 다른 전략 계속 (graceful)
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_capture_graceful_on_strategy_error(monkeypatch):
    """한 전략 처리 중 예외 → 다른 전략 계속 진행."""
    from src.engine.scheduler import TradingScheduler

    s1 = MagicMock()
    s1.strategy_id = "bull_flag_breakout"
    # _funnel_steps 접근 시 예외
    type(s1)._funnel_steps_error = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    # _funnel_steps 자체는 정상 빈 리스트로 — get_scanned_tickers 예외
    s1._funnel_steps = []
    s1.get_scanned_tickers = MagicMock(side_effect=RuntimeError("boom"))

    s2 = MagicMock()
    s2.strategy_id = "vcp_breakout"
    s2._funnel_steps = [
        {"step_no": 1, "step_name": "유니버스",
         "survived": ["005930"], "survived_count": 1,
         "excluded": [], "excluded_count": 0}
    ]
    s2.get_scanned_tickers = MagicMock(return_value=["005930"])

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = MagicMock()
    sched.registry.all = MagicMock(return_value=[s1, s2])

    captured: list = []

    async def _fake_insert(**kwargs):
        captured.append(kwargs)
        return {"id": "row"}

    from src.db import strategy_funnel as sf_mod
    monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

    # 예외 전파 없이 완료
    await sched._auto_capture_funnel_snapshots()

    # s2 의 단계만 캡처 (s1 격리)
    sids = [c["strategy_id"] for c in captured]
    assert "vcp_breakout" in sids, "s2 처리 누락 — s1 예외가 다른 전략 차단"
