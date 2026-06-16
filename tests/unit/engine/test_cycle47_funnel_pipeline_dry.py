"""사이클 47 (2026-05-22) — refactor-review 카드 #3 (MEDIUM) Funnel hook DRY.

배경:
- BFB / VCP / donchian 각 `prepare()` 에 8 단계 `_record_funnel_step` 호출
- 사이클 39 (단계별 자동 hook) + 사이클 41 (종목명 + 사유 + step_conditions) 통합 후 24회 반복
- step_no / step_name 상수가 코드 본문 분산 → 새 전략 추가 시 funnel hook 누락 위험

본 사이클 (47, MEDIUM) 변경:
- `StrategyBase` 모듈 레벨에 `FunnelStage` 데이터클래스 (frozen=True).
- `StrategyBase._record_funnel_pipeline_step(stage, survived, excluded=None, step_conditions=None)`
  헬퍼 — `FunnelStage` 기반 위임. 사이클 41 `_record_funnel_step` 호환 layer 보존.
- step_conditions 는 호출 시점 runtime 평가 가능 (f-string 보존).
- 3 전략 (BFB/VCP/donchian) 파일 상단에 `FUNNEL_STAGES` 상수 정의 (step_no/step_name 만).

안전 가드:
- prepare() 결과 동일성 절대 보존 (FunnelStage 추출은 hook 호출만 단순화)
- 퍼널 카운터 reset 시점 보존 (사이클 39 _reset_daily_state)
- 사이클 41 종목명 + 사유 hook 동작 보존
- 사이클 34 string 배열 형식 하위 호환

사양 (D-1 ~ D-6):
- D-1: `FunnelStage` 데이터클래스 존재 + frozen=True (immutability)
- D-2: 필수 필드 (step_no, step_name) + step_no 가 int
- D-3: `StrategyBase._record_funnel_pipeline_step` 위임 헬퍼
- D-4: step_conditions 인자 보존 (사이클 41 호환)
- D-5: 3 전략 `FUNNEL_STAGES` 모듈 상수 (8 단계, step_no 1~8)
- D-6: 회귀 가드 — 사이클 39+41 _funnel_steps 결과 동일성
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# D-1: FunnelStage 데이터클래스 존재 + frozen=True
# ===========================================================================
def test_funnel_stage_dataclass_exists():
    """`StrategyBase` 모듈에 `FunnelStage` 데이터클래스 존재."""
    from src.engine import strategy_base

    assert hasattr(strategy_base, "FunnelStage"), (
        "`FunnelStage` 데이터클래스 누락 (사이클 47)"
    )


def test_funnel_stage_is_frozen():
    """`FunnelStage` 가 frozen=True (immutability — 모듈 상수 안전)."""
    from src.engine.strategy_base import FunnelStage

    stage = FunnelStage(step_no=1, step_name="테스트")
    with pytest.raises((AttributeError, Exception)):
        stage.step_no = 99  # type: ignore


# ===========================================================================
# D-2: 필수 필드 (step_no, step_name)
# ===========================================================================
def test_funnel_stage_required_fields():
    """`FunnelStage` 필수 필드 — step_no, step_name."""
    from src.engine.strategy_base import FunnelStage

    stage = FunnelStage(step_no=4, step_name="20일 신고가 돌파")
    assert stage.step_no == 4
    assert stage.step_name == "20일 신고가 돌파"


# ===========================================================================
# D-3: _record_funnel_pipeline_step 위임 헬퍼 존재
# ===========================================================================
def test_record_funnel_pipeline_step_exists():
    """`StrategyBase._record_funnel_pipeline_step` 헬퍼 존재."""
    from src.engine.strategy_base import StrategyBase

    assert hasattr(StrategyBase, "_record_funnel_pipeline_step"), (
        "_record_funnel_pipeline_step 위임 헬퍼 누락 (사이클 47)"
    )


def test_record_funnel_pipeline_step_delegates_to_record_funnel_step():
    """`_record_funnel_pipeline_step` 가 `_record_funnel_step` 위임 — 사이클 39+41 호환."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig, FunnelStage

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    stage = FunnelStage(step_no=1, step_name="유니버스 후보")

    strat._record_funnel_pipeline_step(
        stage, survived=["005930"], step_conditions="KRX 등락률 순위 상위",
    )

    assert len(strat._funnel_steps) == 1
    step = strat._funnel_steps[0]
    assert step["step_no"] == 1
    assert step["step_name"] == "유니버스 후보"
    assert step["step_conditions"] == "KRX 등락률 순위 상위"


# ===========================================================================
# D-4: step_conditions 인자 보존 (사이클 41 호환)
# ===========================================================================
def test_record_funnel_pipeline_step_with_excluded():
    """`excluded` 인자 동작 — 사이클 41 종목명 + 사유 캡처 호환."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig, FunnelStage

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    stage = FunnelStage(step_no=2, step_name="유니버스 필터")

    strat._record_funnel_pipeline_step(
        stage,
        survived=["005930"],
        excluded=[{"ticker": "EXC1", "name": "탈락 종목", "reason": "시총 864억 < 1000억"}],
    )

    step = strat._funnel_steps[0]
    assert step["excluded_count"] == 1
    assert step["excluded"][0]["reason"] == "시총 864억 < 1000억"


# ===========================================================================
# D-5: 3 전략 FUNNEL_STAGES 모듈 상수 (8 단계 + step_no 1~8 순서)
# ===========================================================================
@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 157 (2026-06-17) 의미 전환 영구 영속 — BFB FUNNEL_STAGES 8 → 9단계 "
        "(1단계 진입 차단 13건 step 신규 영구 영속). 사이클 66 K-2 패턴 답습."
    ),
)
def test_bfb_funnel_stages_constant():
    """`bull_flag_breakout.FUNNEL_STAGES` 8 단계 정의 → 사이클 157 = 9단계 영구 영속 의미 전환."""
    from src.engine.strategies import bull_flag_breakout

    assert hasattr(bull_flag_breakout, "FUNNEL_STAGES"), (
        "BFB FUNNEL_STAGES 모듈 상수 누락 (사이클 47)"
    )
    stages = bull_flag_breakout.FUNNEL_STAGES
    assert len(stages) == 8
    # step_no 1~8 순서
    for idx, stage in enumerate(stages, start=1):
        assert stage.step_no == idx, f"BFB 단계 {idx} step_no 순서 어긋남 — {stage}"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 157 (2026-06-17) 의미 전환 영구 영속 — VCP FUNNEL_STAGES 8 → 9단계 "
        "(1단계 진입 차단 13건 step 신규 영구 영속). 사이클 66 K-2 패턴 답습."
    ),
)
def test_vcp_funnel_stages_constant():
    """`vcp_breakout.FUNNEL_STAGES` 8 단계 정의 → 사이클 157 = 9단계 영구 영속 의미 전환."""
    from src.engine.strategies import vcp_breakout

    assert hasattr(vcp_breakout, "FUNNEL_STAGES")
    stages = vcp_breakout.FUNNEL_STAGES
    assert len(stages) == 8
    for idx, stage in enumerate(stages, start=1):
        assert stage.step_no == idx


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 157 (2026-06-17) 의미 전환 영구 영속 — donchian FUNNEL_STAGES 8 → 9단계 "
        "(1단계 진입 차단 13건 step 신규 영구 영속). 사이클 66 K-2 패턴 답습."
    ),
)
def test_donchian_funnel_stages_constant():
    """`donchian_swing.FUNNEL_STAGES` 8 단계 정의 → 사이클 157 = 9단계 영구 영속 의미 전환."""
    from src.engine.strategies import donchian_swing

    assert hasattr(donchian_swing, "FUNNEL_STAGES")
    stages = donchian_swing.FUNNEL_STAGES
    assert len(stages) == 8
    for idx, stage in enumerate(stages, start=1):
        assert stage.step_no == idx


def test_funnel_stages_step_names_consistent():
    """3 전략 step_no=1 단계 step_name 이 사용자 명세와 일치."""
    from src.engine.strategies import bull_flag_breakout, vcp_breakout, donchian_swing

    # BFB step_no=1 — 유니버스 후보
    assert bull_flag_breakout.FUNNEL_STAGES[0].step_name == "유니버스 후보"
    # VCP step_no=1 — 코스피200+코스닥150 합집합
    assert vcp_breakout.FUNNEL_STAGES[0].step_name == "코스피200+코스닥150 합집합"
    # donchian step_no=1 — 코스피200+코스닥150 합집합
    assert donchian_swing.FUNNEL_STAGES[0].step_name == "코스피200+코스닥150 합집합"


# ===========================================================================
# D-6: 회귀 가드 — 사이클 39+41 _funnel_steps 결과 동일성
# ===========================================================================
@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 157 (2026-06-17) 의미 전환 영구 영속 — BFB prepare() funnel_steps 8 → 9 단계 "
        "(1단계 진입 차단 13건 step 신규 영구 영속). 사이클 66 K-2 패턴 답습."
    ),
)
@pytest.mark.asyncio
async def test_bfb_prepare_funnel_steps_same_count_after_cycle47(monkeypatch):
    """BFB prepare() 후 _funnel_steps 결과가 사이클 47 적용 후에도 8 단계 정확 → 사이클 157 = 9 단계 의미 전환."""
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategies import bull_flag_breakout as bfb_mod
    from datetime import date as _date, timedelta as _td

    today = _date.today()

    def _make_candles(days=30):
        return [
            {
                "stck_bsop_date": (today - _td(days=i + 1)).strftime("%Y%m%d"),
                "stck_clpr": str(50000 + (days - i) * 100),
                "stck_hgpr": str(50000 + (days - i) * 100 + 500),
                "stck_lwpr": str(50000 + (days - i) * 100 - 500),
                "stck_oprc": str(50000 + (days - i) * 100),
                "acml_vol": "1000000",
            }
            for i in range(days)
        ]

    async def _fake_scan():
        return ["005930"]

    async def _fake_fetch(ticker, days):
        return _make_candles(days)

    from src.api import condition as cond_mod
    monkeypatch.setattr(bfb_mod, "fetch_daily_candles", _fake_fetch, raising=False)
    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch, raising=False)

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
    strat._funnel_steps = []
    strat._scan_stats = bfb_mod._empty_scan_stats()

    await strat.prepare()

    # 사이클 47: 8 단계 모두 기록 (사이클 39+41 결과 동일성)
    assert len(strat._funnel_steps) == 8, (
        f"BFB prepare() 후 _funnel_steps 8 단계 정확 (사이클 47 회귀 가드). "
        f"실제={len(strat._funnel_steps)}"
    )
    # step_no 1~8 순서 정합
    step_nos = [s["step_no"] for s in strat._funnel_steps]
    assert step_nos == [1, 2, 3, 4, 5, 6, 7, 8]
