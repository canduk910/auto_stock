"""사이클 44 (2026-05-22) — refactor-review 카드 #7 종목명 lookup 단일 헬퍼.

배경:
- 18+ 곳에서 4 경로 혼재:
  1. `scanner.ticker_names.get(ticker, "")` — WS 시세 수신 시 갱신 dict
  2. `STATIC_TICKER_NAMES.get(ticker, "")` — scanner 자기 파일 정규식 파싱
  3. `_resolve_ticker_name(ticker)` — 사이클 41 신규 (`StrategyBase` 모듈 레벨)
  4. `t(ticker)` — `scanner.t` 헬퍼 ("종목명(코드)" 형식)
- 분산 위치: condition.py(5) + order_engine.py(53) + scheduler.py(21) + strategy_base.py(4)
- BFB/VCP/donchian prepare hook (사이클 41) 도 `_resolve_ticker_name` 사용 중

본 사이클 (44, LOW) 변경:
- `scanner.py::resolve_ticker_name(ticker)` 단일 헬퍼 추가
  - 폴백 순서: `ticker_names` (동적) → `STATIC_TICKER_NAMES` (정적) → `""`
- `strategy_base._resolve_ticker_name` 위임 (사이클 41 호환 layer 보존)
- 추가 호출처 마이그레이션은 별도 후속 카드 (회귀 위험 우려)

안전 가드:
- prepare()/on_tick()/execute_buy_sell 결과 동일성 보존 (lookup 변경만)
- 빈 ticker → 빈 문자열 (예외 X)
- WS 시세 수신 후 `ticker_names` 갱신 → resolve_ticker_name 반영
- 사이클 41 회귀 가드 (호환 layer 동작)

사양 (N-1 ~ N-6):
- N-1: `scanner.resolve_ticker_name` 헬퍼 존재 + 신호 (str -> str)
- N-2: ticker_names (동적) 1순위 → STATIC_TICKER_NAMES (정적) 2순위
- N-3: 양쪽 부재 시 빈 문자열
- N-4: 빈 ticker / None → 빈 문자열 (예외 X)
- N-5: `strategy_base._resolve_ticker_name` 위임 동작 (사이클 41 호환)
- N-6: WS 시세 수신 후 ticker_names 갱신 즉시 반영
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# N-1: scanner.resolve_ticker_name 헬퍼 존재 + 신호
# ===========================================================================
def test_scanner_has_resolve_ticker_name_helper():
    """`scanner.resolve_ticker_name(ticker: str) -> str` 신규 헬퍼."""
    from src.engine import scanner

    assert hasattr(scanner, "resolve_ticker_name"), (
        "scanner.resolve_ticker_name 헬퍼 누락 (사이클 44)"
    )
    assert callable(scanner.resolve_ticker_name)


# ===========================================================================
# N-2: ticker_names 1순위 → STATIC_TICKER_NAMES 2순위
# ===========================================================================
def test_resolve_ticker_name_dynamic_priority(monkeypatch):
    """`ticker_names` (WS 동적) 가 1순위. 정적 매핑보다 우선."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "동적 이름"})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {"005930": "정적 이름"})

    assert scanner.resolve_ticker_name("005930") == "동적 이름"


def test_resolve_ticker_name_static_fallback(monkeypatch):
    """`ticker_names` 부재 시 STATIC_TICKER_NAMES 폴백."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {"005930": "정적 이름"})

    assert scanner.resolve_ticker_name("005930") == "정적 이름"


# ===========================================================================
# N-3: 양쪽 부재 시 빈 문자열
# ===========================================================================
def test_resolve_ticker_name_returns_empty_for_unknown(monkeypatch):
    """양쪽 부재 → 빈 문자열 (예외 X)."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {})

    assert scanner.resolve_ticker_name("UNKNOWN") == ""


# ===========================================================================
# N-4: 빈 ticker / None → 빈 문자열 (예외 X)
# ===========================================================================
def test_resolve_ticker_name_empty_ticker_graceful():
    """빈 ticker → 빈 문자열 (예외 X)."""
    from src.engine import scanner

    assert scanner.resolve_ticker_name("") == ""


def test_resolve_ticker_name_none_safe(monkeypatch):
    """None 입력 시 예외 X (graceful 폴백)."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {})

    # None 안전 — TypeError 예외 전파 금지
    result = scanner.resolve_ticker_name(None)  # type: ignore
    assert result == ""


# ===========================================================================
# N-5: strategy_base._resolve_ticker_name 위임 (사이클 41 호환)
# ===========================================================================
def test_strategy_base_resolve_ticker_name_delegates_to_scanner(monkeypatch):
    """`_resolve_ticker_name` 가 `scanner.resolve_ticker_name` 위임 (동일 결과)."""
    from src.engine import scanner, strategy_base

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {})

    # 두 경로 동일 결과
    assert strategy_base._resolve_ticker_name("005930") == scanner.resolve_ticker_name("005930")
    assert strategy_base._resolve_ticker_name("005930") == "삼성전자"


def test_strategy_base_resolve_ticker_name_graceful(monkeypatch):
    """`_resolve_ticker_name` 도 graceful — 빈 문자열 폴백."""
    from src.engine import scanner, strategy_base

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {})

    assert strategy_base._resolve_ticker_name("UNKNOWN") == ""
    assert strategy_base._resolve_ticker_name("") == ""


# ===========================================================================
# N-6: WS 시세 수신 후 ticker_names 갱신 즉시 반영
# ===========================================================================
def test_resolve_ticker_name_reflects_dynamic_update(monkeypatch):
    """`ticker_names` 갱신 후 lookup 즉시 반영 (WS 시세 수신 시나리오)."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {})

    # 초기 — lookup miss
    assert scanner.resolve_ticker_name("005930") == ""

    # WS 시세 수신 시뮬 — ticker_names 갱신
    scanner.ticker_names["005930"] = "삼성전자"

    # 즉시 반영
    assert scanner.resolve_ticker_name("005930") == "삼성전자"


# ===========================================================================
# N-7: 사이클 41 funnel hook 호환 회귀 가드
# ===========================================================================
def test_funnel_hook_uses_resolved_name(monkeypatch):
    """사이클 41 `_record_funnel_step` 가 신규 헬퍼 통해 동일 결과 반환."""
    from src.engine import scanner
    from src.engine.strategy_base import StrategyBase, StrategyConfig

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "STATIC_TICKER_NAMES", {"000660": "SK하이닉스"})

    class _Stub(StrategyBase):
        async def prepare(self): pass
        def check_buy_signal(self, *a, **kw): return None
        def check_exit_signal(self, *a, **kw): return None
        def calc_buy_quantity(self, *a, **kw): return 0

    strat = _Stub(StrategyConfig(strategy_id="test", name="테스트", weight=0.1))
    strat._record_funnel_step(
        step_no=1, step_name="유니버스 후보",
        survived=["005930", "000660", "UNKNOWN"],
    )

    survived = strat._funnel_steps[0]["survived"]
    by_ticker = {s["ticker"]: s["name"] for s in survived}
    assert by_ticker["005930"] == "삼성전자"  # 동적
    assert by_ticker["000660"] == "SK하이닉스"  # 정적 폴백
    assert by_ticker["UNKNOWN"] == ""  # lookup miss
