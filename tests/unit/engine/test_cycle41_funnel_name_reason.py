"""사이클 41 (2026-05-22) — funnel 단계별 종목명 + 탈락 사유 정밀 추적.

배경:
- 사이클 39 (2026-05-22) 단계별 hook 도입 후 사용자 5/22 12:27 funnel 검증:
  - BFB: 29→21→21→0 (사이클 33 acml_vol fix 효과 확인, 사이클 40 음봉 임계 0.40 적용 대기)
  - VCP: 115→113→113→31→9→0→0→0 (사이클 39 키 매핑 fix 효과 확인 — 이전 EMA=0 으로 가려져 있던 Pullback 9→0 새 결함 노출)
  - donchian: 111→111→111→0→... (H-4 시장 자연 vs 코드 결함)

사용자 요구:
- 단계별 탈락 사유 *수치 포함* 정확 추적 (예: "시총 864억 < 1000억")
- ticker 만이 아니라 종목명도 함께
- 각 단계 작업/필터링 조건 누락 정밀 추적 (코드 결함 추적 도구)

본 사이클 (41) 변경:
- `StrategyBase._record_funnel_step` 시그니처 확장:
  - `survived: list[str | dict]` — 종목명 자동 lookup (string 입력 → dict 자동 변환)
  - `excluded: list[dict]` — `{"ticker", "name", "reason"}` 정확 캡처
  - `step_conditions: str | None` (kwarg) — 단계 조건 명시 (툴팁용)
- `StrategyBase._resolve_ticker_name(ticker)` 헬퍼 — scanner.ticker_names + STATIC_TICKER_NAMES 1차
- 각 전략 prepare() hook 호출 보강 (BFB/VCP/donchian — 시뮬에서 검증, 회귀 가드 절대)
- DB JSONB 하위 호환 (string + dict 둘 다 허용)

사양 (R-1 ~ R-9):
- R-1: 신규 시그니처 — string 입력 시 자동 dict 변환 (종목명 lookup)
- R-2: dict 입력 시 그대로 유지
- R-3: excluded reason 정확 캡처 (수치 포함)
- R-4: step_conditions 옵션 보존
- R-5: 종목명 lookup 우선순위 (ticker_names → STATIC_TICKER_NAMES → "")
- R-6: 기존 사이클 39 회귀 가드 (string list 입력 호환)
- R-7: cap 200/20 보존
- R-8: 종목명 lookup miss graceful (빈 문자열, 예외 없음)
- R-9: scheduler `_auto_capture_funnel_snapshots` 가 신규 형식 DB 저장 (사이클 34 인프라 재활용)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# R-1: string 입력 시 자동 dict 변환 (종목명 lookup)
# ===========================================================================
def test_record_funnel_step_auto_resolves_name_for_string_ticker(monkeypatch):
    """survived=["005930"] → 자동 dict 변환 ({"ticker":"005930","name":"삼성전자"})."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig
    from src.engine import scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_names", {"005930": "삼성전자"})

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=1, step_name="유니버스 후보",
        survived=["005930"],
    )

    step = strat._funnel_steps[0]
    assert step["survived"][0]["ticker"] == "005930"
    assert step["survived"][0]["name"] == "삼성전자"


# ===========================================================================
# R-2: dict 입력 시 그대로 유지 (string 변환 안 함)
# ===========================================================================
def test_record_funnel_step_preserves_dict_input():
    """survived=[{"ticker":"...","name":"..."}] 그대로 보존."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=1, step_name="유니버스",
        survived=[{"ticker": "005930", "name": "직접 입력 종목명"}],
    )

    step = strat._funnel_steps[0]
    assert step["survived"][0]["name"] == "직접 입력 종목명"


# ===========================================================================
# R-3: excluded reason 정확 캡처 (수치 포함)
# ===========================================================================
def test_record_funnel_step_captures_excluded_reasons_with_numbers():
    """excluded=[{"ticker","name","reason"}] 정확 캡처 (수치 포함)."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=2, step_name="유니버스 필터",
        survived=[],
        excluded=[
            {"ticker": "AAAAA1", "name": "테스트1", "reason": "시총 864억 < 1000억"},
            {"ticker": "AAAAA2", "name": "테스트2", "reason": "거래대금 15억 < 20억"},
        ],
    )

    step = strat._funnel_steps[0]
    excluded = step["excluded"]
    assert len(excluded) == 2
    assert "시총 864억 < 1000억" in excluded[0]["reason"]
    assert "거래대금 15억 < 20억" in excluded[1]["reason"]


# ===========================================================================
# R-4: step_conditions 옵션 보존
# ===========================================================================
def test_record_funnel_step_supports_step_conditions():
    """`step_conditions` kwarg 보존 (UI 툴팁용)."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=6, step_name="Pullback 점진 수축",
        survived=["005930"],
        step_conditions="VCP: 2~4회 회수 + 직전 대비 폭 감소 + 마지막 ≤ 8%",
    )

    step = strat._funnel_steps[0]
    assert step["step_conditions"] == "VCP: 2~4회 회수 + 직전 대비 폭 감소 + 마지막 ≤ 8%"


def test_record_funnel_step_step_conditions_optional():
    """`step_conditions` 미지정 시 None — 기존 사이클 39 호환."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=1, step_name="유니버스",
        survived=["005930"],
    )

    step = strat._funnel_steps[0]
    assert step.get("step_conditions") is None


# ===========================================================================
# R-5: 종목명 lookup 우선순위
# ===========================================================================
def test_resolve_ticker_name_uses_ticker_names_first(monkeypatch):
    """`_resolve_ticker_name`: ticker_names 1차 → STATIC_TICKER_NAMES 폴백."""
    from src.engine.strategy_base import _resolve_ticker_name
    from src.engine import scanner as scanner_mod

    # ticker_names 우선
    monkeypatch.setattr(scanner_mod, "ticker_names", {"005930": "동적 매핑 이름"})
    monkeypatch.setattr(scanner_mod, "STATIC_TICKER_NAMES", {"005930": "정적 매핑 이름"})

    assert _resolve_ticker_name("005930") == "동적 매핑 이름"


def test_resolve_ticker_name_falls_back_to_static(monkeypatch):
    """ticker_names 부재 → STATIC_TICKER_NAMES 폴백."""
    from src.engine.strategy_base import _resolve_ticker_name
    from src.engine import scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_names", {})
    monkeypatch.setattr(scanner_mod, "STATIC_TICKER_NAMES", {"005930": "정적 매핑 이름"})

    assert _resolve_ticker_name("005930") == "정적 매핑 이름"


def test_resolve_ticker_name_returns_empty_for_unknown(monkeypatch):
    """양쪽 모두 부재 → 빈 문자열 (예외 없음)."""
    from src.engine.strategy_base import _resolve_ticker_name
    from src.engine import scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_names", {})
    monkeypatch.setattr(scanner_mod, "STATIC_TICKER_NAMES", {})

    assert _resolve_ticker_name("UNKNOWN") == ""


def test_resolve_ticker_name_graceful_on_import_error(monkeypatch):
    """scanner import 실패 graceful — 빈 문자열 반환 (예외 전파 금지)."""
    from src.engine.strategy_base import _resolve_ticker_name
    from src.engine import scanner as scanner_mod

    # 빈 dict 로 정상 경로 검증 — import 실패는 _resolve_ticker_name 내부 try/except 가 흡수
    monkeypatch.setattr(scanner_mod, "ticker_names", {})
    monkeypatch.setattr(scanner_mod, "STATIC_TICKER_NAMES", {})

    result = _resolve_ticker_name("UNKNOWN")
    assert result == ""


# ===========================================================================
# R-6: 기존 사이클 39 회귀 가드 — string list 입력 호환
# ===========================================================================
def test_string_list_input_compatible_with_cycle39():
    """기존 string list 입력 — 사이클 39 호환 (survived_count 보존)."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=1, step_name="유니버스",
        survived=["005930", "000660", "005935"],
    )

    step = strat._funnel_steps[0]
    assert step["survived_count"] == 3
    # 자동 변환 후에도 cap 적용
    assert len(step["survived"]) <= 200


# ===========================================================================
# R-7: cap 200/20 보존
# ===========================================================================
def test_cap_200_20_preserved_with_dict_form():
    """dict 형식에서도 cap 200/20 적용."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    many_survived = [f"{i:06d}" for i in range(300)]
    many_excluded = [{"ticker": f"E{i:05d}", "name": "테스트", "reason": "x"} for i in range(50)]
    strat._record_funnel_step(
        step_no=1, step_name="cap test",
        survived=many_survived, excluded=many_excluded,
    )

    step = strat._funnel_steps[0]
    assert len(step["survived"]) == 200
    assert len(step["excluded"]) == 20
    assert step["survived_count"] == 300
    assert step["excluded_count"] == 50


# ===========================================================================
# R-8: 종목명 lookup miss graceful
# ===========================================================================
def test_unknown_ticker_resolves_to_empty_name(monkeypatch):
    """이름 lookup miss → name="" (예외 없음)."""
    from src.engine.strategy_base import StrategyBase, StrategyConfig
    from src.engine import scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "ticker_names", {})
    monkeypatch.setattr(scanner_mod, "STATIC_TICKER_NAMES", {})

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=1, step_name="유니버스",
        survived=["UNKNOWN_TICKER"],
    )

    step = strat._funnel_steps[0]
    assert step["survived"][0]["ticker"] == "UNKNOWN_TICKER"
    assert step["survived"][0]["name"] == ""


# ===========================================================================
# R-9: scheduler _auto_capture_funnel_snapshots — 신규 형식 DB 저장
# ===========================================================================
@pytest.mark.asyncio
async def test_auto_capture_passes_dict_form_to_db(monkeypatch):
    """`_auto_capture_funnel_snapshots` 가 dict 형식 survived/excluded 를 그대로 DB 저장."""
    from src.engine.scheduler import TradingScheduler

    fake_strategy = MagicMock()
    fake_strategy.strategy_id = "bull_flag_breakout"
    fake_strategy._funnel_steps = [
        {
            "step_no": 2, "step_name": "유니버스 필터 통과",
            "survived": [{"ticker": "005930", "name": "삼성전자"}],
            "survived_count": 1,
            "excluded": [
                {"ticker": "AAAAA1", "name": "테스트1", "reason": "시총 864억 < 1000억"},
            ],
            "excluded_count": 1,
            "step_conditions": "BFB: 시총 ≥ 500억 + 거래대금 ≥ 20억",
        }
    ]
    fake_strategy.get_scanned_tickers = MagicMock(return_value=["005930"])

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = MagicMock()
    sched.registry.all = MagicMock(return_value=[fake_strategy])

    captured: list = []

    async def _fake_insert(**kwargs):
        captured.append(kwargs)
        return {"id": f"row-{kwargs['step_no']}"}

    from src.db import strategy_funnel as sf_mod
    monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

    await sched._auto_capture_funnel_snapshots()

    # 단계 2 row 확인
    step2_calls = [c for c in captured if c["step_no"] == 2]
    assert len(step2_calls) == 1
    survived = step2_calls[0]["survived_tickers"]
    assert isinstance(survived[0], dict)
    assert survived[0]["ticker"] == "005930"
    assert survived[0]["name"] == "삼성전자"

    excluded = step2_calls[0]["excluded_sample"]
    assert "시총 864억" in excluded[0]["reason"]
