"""refactor-review A3 (Red) — `_refine_cooldown_business_days` 4벌 byte-identical → StrategyBase 단일 정의 승격.

작업 지시서 = `_workspace/red/refactor_a3_cooldown_base.md`.

**Red 단계 — 실패 테스트만. production 미변경.** Green = backend-dev.

배경: `_refine_cooldown_business_days` 가 bfb/ltv/vcp/vb 4 전략에 로그 접두사(1토큰)만 다른
byte-identical 4벌로 존재한다. H-1 `_apply_high_since_buy_from_candles` / A5·A6
`_rederive_entry_atr`·`_atr` 와 동일 클래스의 드리프트 위험 → base 단일 정의 + 전략별
`_COOLDOWN_LOG_LABEL: ClassVar[str]` override 로 승격 (H-1 `_HIGH_RECOVER_LABEL` 선례 동형).

현재 4벌 위치 (backend-dev 정확 인계):
  - bull_flag_breakout.py:1094  → 접두사 `[bfb]`
  - long_tail_volatility.py:134 → 접두사 `[ltv]`
  - vcp_breakout.py:1179        → 접두사 `[vcp]`
  - volatility_breakout.py:1035 → 접두사 `[vb]`
(ltv/vb 접두사 = tdd-engineer 소스 실측 확인 완료 — `[ltv]`/`[vb]`, "추정" 아님.)

Green 계약:
  - `StrategyBase._refine_cooldown_business_days(self, ticker)` async 단일 정의.
    본문 = `days = self.config.params["reentry_cooldown_days"]` → `today = datetime.now(KST).date()`
    → `try: accurate = await add_business_days(today, days); self._cooldown_until[ticker] = accurate`
    → `except Exception: logger.warning("%s 영업일 정정 실패 (ticker=%s) — 근사값 유지",
       self._COOLDOWN_LOG_LABEL, ticker)`.
  - `StrategyBase._COOLDOWN_LOG_LABEL: ClassVar[str | None] = None` (base 기본, `_HIGH_RECOVER_LABEL` 동형).
  - 4 전략 override: bfb=`[bfb]` / vcp=`[vcp]` / ltv=`[ltv]` / vb=`[vb]` (byte-identical 로그 보존).
  - 4 전략 소스에서 `def _refine_cooldown_business_days` **제거** (base 위임만).
  - `register_cooldown_after_exit` 는 **승격 대상 아님** (bfb 변형 = `_breakout_first_seen.pop` 동반이라
    byte-identical 아님) → 4 전략 소스 정의 잔존.

⚠️ 패치 seam 계약 (backend-dev 필독): base 승격 후에도 `add_business_days` 를 **concrete
전략 모듈 네임스페이스로 resolve** 해야 한다 (stale_manager `sys.modules[type(self).__module__]`
패턴). 기존 cycle191/201/213 테스트 + 본 파일 행위 테스트 모두 전략 모듈 바인딩
(`monkeypatch.setattr(<strategy_mod>, "add_business_days", ...)`)을 패치하기 때문 — base 가
`strategy_base.add_business_days` 나 `src.api.condition` 를 직접 참조하면 이 seam 이 깨져
cycle191/201/213 회귀(요구 6 위반) + 본 파일 행위 테스트가 동반 FAIL 한다.

가드 매트릭스:
  - A3-1 (Red): 4 전략 소스 `def _refine_cooldown_business_days` 부재 (현재 4벌 → FAIL).
  - A3-2 (Red): StrategyBase 단일 정의 존재 + async.
  - A3-3 (행위 보존): 4 전략 refine 성공 → `_cooldown_until` 정확 영업일 갱신.
  - A3-4 (행위 보존 + Red ClassVar): 4 전략 refine 실패 graceful + `[bfb]/[vcp]/[ltv]/[vb]`
    접두사 로그 (caplog) / `_COOLDOWN_LOG_LABEL` ClassVar 값 (현재 부재 → FAIL).
  - A3-5 (Red): kojiro/donchian/momentum base 메서드 상속 + 소스 cooldown 배선 부재.
  - A3-6 (scope): `register_cooldown_after_exit` 승격 금지 — 4 전략 소스 잔존.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.strategy_base import StrategyBase, StrategyConfig
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.momentum import MomentumStrategy

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_STRAT_DIR = Path(__file__).resolve().parents[4] / "src" / "engine" / "strategies"
_TICKER = "005930"


# ---------------------------------------------------------------------------
# 전략 팩토리 — cycle191/201/213 픽스처 패턴 답습 (refine-only = scanner 무관)
# ---------------------------------------------------------------------------
def _make_bfb() -> BullFlagBreakoutStrategy:
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="bfb", params={"exchange": "KRX"})
    )


def _make_vcp() -> VcpBreakoutStrategy:
    return VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="vcp", params={"exchange": "KRX"})
    )


def _make_ltv() -> LongTailVolatilityStrategy:
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="ltv", weight=0.15)
    )


def _make_vb() -> VolatilityBreakoutStrategy:
    return VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="vb", weight=0.3)
    )


# (id, factory, module_path, log_label, reentry_cooldown_days)
_COOLDOWN_CASES = [
    ("bfb", _make_bfb, "src.engine.strategies.bull_flag_breakout", "[bfb]", 3),
    ("vcp", _make_vcp, "src.engine.strategies.vcp_breakout", "[vcp]", 7),
    ("ltv", _make_ltv, "src.engine.strategies.long_tail_volatility", "[ltv]", 2),
    ("vb", _make_vb, "src.engine.strategies.volatility_breakout", "[vb]", 2),
]
_CASE_IDS = [c[0] for c in _COOLDOWN_CASES]


def _defs_in_strategy_files(name: str) -> list[str]:
    """전략 디렉토리 전 .py 파일에서 `def <name>` 위치 목록 (H-1/A5·A6 미러)."""
    offenders: list[str] = []
    for path in sorted(_STRAT_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                offenders.append(f"{path.name}:{node.lineno}")
    return offenders


# ===========================================================================
# A3-1 [Red] 4 전략 소스 중복 정의 0건
# ===========================================================================
def test_a3_1_no_duplicate_refine_definition_in_strategy_files() -> None:
    """A3-1 (Red): `_refine_cooldown_business_days` 정의는 StrategyBase 단독 — 전략 파일 잔존 0.

    현재 FAIL = bfb/ltv/vcp/vb 4벌 존재. Green = base 승격 후 잔존 0.
    호출은 없고(base 상속) `def` 만 금지 — H-1 `test_no_duplicate_helper_definition_in_strategy_files` 미러.
    """
    offenders = _defs_in_strategy_files("_refine_cooldown_business_days")
    assert not offenders, (
        f"A3-1: _refine_cooldown_business_days 정의는 base 단독 — 잔존 {offenders}"
    )


# ===========================================================================
# A3-2 [Red] StrategyBase 단일 정의 존재 + async
# ===========================================================================
def test_a3_2_base_has_refine_and_is_async() -> None:
    """A3-2 (Red): StrategyBase 에 `_refine_cooldown_business_days` (async) 존재.

    현재 FAIL = base 미정의 (각 전략 자체 def). Green = base 단일 정의.
    """
    assert hasattr(StrategyBase, "_refine_cooldown_business_days"), (
        "A3-2: base 단일 정의 부재 (H-1 `_apply_high_since_buy_from_candles` 선례 동형 승격)"
    )
    assert inspect.iscoroutinefunction(StrategyBase._refine_cooldown_business_days), (
        "A3-2: `_refine_cooldown_business_days` 는 async (await add_business_days)"
    )


def test_a3_2_four_strategies_inherit_base_refine() -> None:
    """A3-2b (Red): 4 전략이 base 메서드 상속 (자체 정의 없이 hasattr True)."""
    for _sid, factory, _mod, _label, _days in _COOLDOWN_CASES:
        strat = factory()
        assert hasattr(strat, "_refine_cooldown_business_days")


# ===========================================================================
# A3-3 [행위 보존] refine 성공 → 정확 영업일 date 로 갱신 (4 전략)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-07-14 10:00:00")
@pytest.mark.parametrize("sid,factory,modpath,label,days", _COOLDOWN_CASES, ids=_CASE_IDS)
async def test_a3_3_refine_success_updates_cooldown(
    monkeypatch: pytest.MonkeyPatch, sid, factory, modpath, label, days,
) -> None:
    """A3-3 (행위 보존): refine 성공 → `_cooldown_until[t]` 정확 영업일 date 로 교체.

    현재 PASS (전략 자체 def) + 승격 후 PASS (base 위임) = byte-identical 행위 보존 가드.
    add_business_days 는 전략 모듈 바인딩 패치 (seam 계약 — 파일 상단 ⚠️ 참조).
    """
    strat = factory()
    today = datetime.now(KST).date()
    strat.register_cooldown_after_exit(_TICKER)  # 근사 선등록

    accurate = today + timedelta(days=days)  # 임의 영업일 정정 결과
    fake_add = AsyncMock(return_value=accurate)
    mod = importlib.import_module(modpath)
    monkeypatch.setattr(mod, "add_business_days", fake_add, raising=False)

    await strat._refine_cooldown_business_days(_TICKER)

    fake_add.assert_awaited_once()
    assert strat._cooldown_until[_TICKER] == accurate, (
        f"{sid}: refine 성공 → 정확 영업일 date 교체 (행위 보존)"
    )


# ===========================================================================
# A3-4 [행위 보존 + Red ClassVar] refine 실패 graceful + 전략별 로그 접두사
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-07-14 10:00:00")
@pytest.mark.parametrize("sid,factory,modpath,label,days", _COOLDOWN_CASES, ids=_CASE_IDS)
async def test_a3_4_refine_failure_keeps_approx_and_logs_prefix(
    monkeypatch: pytest.MonkeyPatch, caplog, sid, factory, modpath, label, days,
) -> None:
    """A3-4 (행위 보존): refine 예외 → 근사값 유지 (전파 0) + `%s 영업일 정정 실패` WARNING.

    로그 접두사 = 전략별 (`[bfb]/[vcp]/[ltv]/[vb]`) — `_COOLDOWN_LOG_LABEL` ClassVar 로 보존.
    caplog 은 logger 미지정(root) = 승격 후 logger namespace 이동(전략 모듈 → strategy_base)에 견고.
    현재 PASS (하드코딩 접두사) + 승격 후 PASS (ClassVar) = byte-identical 로그 보존 가드.
    """
    strat = factory()
    today = datetime.now(KST).date()
    strat.register_cooldown_after_exit(_TICKER)
    approx = strat._cooldown_until[_TICKER]
    assert approx == today + timedelta(days=days + 2), "근사값 = today + days + 2 선결"

    fake_add = AsyncMock(side_effect=RuntimeError("boom"))
    mod = importlib.import_module(modpath)
    monkeypatch.setattr(mod, "add_business_days", fake_add, raising=False)

    with caplog.at_level(logging.WARNING):
        await strat._refine_cooldown_business_days(_TICKER)  # 예외 전파 없이 완료

    assert strat._cooldown_until[_TICKER] == approx, (
        f"{sid}: refine 예외 → 근사값 유지 (graceful)"
    )
    warn_text = "\n".join(
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
    )
    assert "영업일 정정 실패" in warn_text, f"{sid}: 실패 시 WARNING 미발화"
    assert label in warn_text, (
        f"{sid}: 로그 접두사 {label} 보존 실패 (운영자 grep 이력 단절) — got: {warn_text!r}"
    )


def test_a3_4_cooldown_log_label_classvar_per_strategy() -> None:
    """A3-4b (Red): 전략별 `_COOLDOWN_LOG_LABEL` ClassVar override 값.

    현재 FAIL = ClassVar 부재 (AttributeError). Green = 전략별 override.
    label 값에 대괄호 포함 (`[bfb]`) — `logger.warning("%s 영업일 정정 실패...", label, ticker)`
    형태로 현행 `[bfb] 영업일 정정 실패...` 와 byte-identical.
    """
    assert BullFlagBreakoutStrategy._COOLDOWN_LOG_LABEL == "[bfb]"
    assert VcpBreakoutStrategy._COOLDOWN_LOG_LABEL == "[vcp]"
    assert LongTailVolatilityStrategy._COOLDOWN_LOG_LABEL == "[ltv]"
    assert VolatilityBreakoutStrategy._COOLDOWN_LOG_LABEL == "[vb]"


def test_a3_4_base_cooldown_log_label_default_none() -> None:
    """A3-4c (Red): base `_COOLDOWN_LOG_LABEL` 기본값 None (`_HIGH_RECOVER_LABEL` 선례 동형).

    현재 FAIL = ClassVar 부재. kojiro/donchian/momentum 은 상속하되 refine 미호출이라 미사용.
    """
    assert hasattr(StrategyBase, "_COOLDOWN_LOG_LABEL")
    assert StrategyBase._COOLDOWN_LOG_LABEL is None


# ===========================================================================
# A3-5 [Red] kojiro/donchian/momentum 미영향 — 상속하되 소스 배선 0
# ===========================================================================
def test_a3_5_non_cooldown_strategies_inherit_base_refine() -> None:
    """A3-5 (Red): cooldown 미보유 전략(kojiro/donchian/momentum)도 base 메서드 상속.

    현재 FAIL = base 미정의 → 상속할 것이 없음(hasattr False). Green = base 승격 후 상속.
    상속돼도 호출 0 (cooldown 배선 부재) — 아래 소스 가드가 배선 부재 확인.
    """
    for cls in (KojiroStrategy, DonchianSwingStrategy, MomentumStrategy):
        assert hasattr(cls, "_refine_cooldown_business_days"), (
            f"{cls.__name__}: base 승격 후 상속 (정의는 base, 호출은 0)"
        )


def test_a3_5_non_cooldown_strategy_sources_have_no_cooldown_wiring() -> None:
    """A3-5b: kojiro/donchian/momentum 소스에 cooldown 배선 정의 부재 (재진입 쿨다운 없음).

    현재/승격 후 PASS = 이 전략들은 cooldown 자체가 없다 (상속받아도 미호출).
    """
    for fname in ("kojiro.py", "donchian_swing.py", "momentum.py"):
        tree = ast.parse((_STRAT_DIR / fname).read_text(encoding="utf-8"))
        defs = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "_refine_cooldown_business_days" not in defs, f"{fname}: 승격 대상 정의 부재 의무"
        assert "register_cooldown_after_exit" not in defs, f"{fname}: cooldown 배선 없음"


def test_a3_5_non_cooldown_strategies_have_no_cooldown_label_override() -> None:
    """A3-5c: kojiro/donchian/momentum 은 `_COOLDOWN_LOG_LABEL` override 없이 base 상속(None).

    현재/승격 후 PASS = 미호출 전략은 override 불필요 (base None 상속).
    """
    for cls in (KojiroStrategy, DonchianSwingStrategy, MomentumStrategy):
        assert "_COOLDOWN_LOG_LABEL" not in cls.__dict__, (
            f"{cls.__name__}: cooldown 미보유 → 라벨 override 금지 (base None 상속)"
        )


# ===========================================================================
# A3-6 [scope] register_cooldown_after_exit 는 승격 금지 — 4 전략 소스 잔존
# ===========================================================================
def test_a3_6_register_cooldown_after_exit_remains_per_strategy() -> None:
    """A3-6 (scope 가드): `register_cooldown_after_exit` 는 A3 승격 대상 아님 — 4 전략 소스 잔존.

    BFB 변형은 `_breakout_first_seen.pop(ticker, None)` 를 동반해 다른 3벌과 byte-identical 아니다
    → 승격하면 BFB 행위가 바뀐다. A3 는 `_refine_cooldown_business_days` **만** 승격.
    현재/승격 후 PASS — 과잉 승격(register 까지 base 로 끌어올림) 회귀 영구 차단.
    """
    files_with_def = {
        path.name
        for path in sorted(_STRAT_DIR.glob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "register_cooldown_after_exit"
    }
    for fname in (
        "bull_flag_breakout.py",
        "vcp_breakout.py",
        "long_tail_volatility.py",
        "volatility_breakout.py",
    ):
        assert fname in files_with_def, (
            f"{fname}: register_cooldown_after_exit 정의 잔존 의무 (A3 승격 대상 아님)"
        )
