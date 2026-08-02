"""사이클 H Red — AST 격리 가드 + import sanity.

명세: `_workspace/cycleH_portfolio_risk_phase1_spec.md` §11 절대준수 + §TDD (e)(f).
Red 메모: `_workspace/red/cycleH_portfolio_risk.md`.

(e) AST 격리:
  - 매매 안전성 8영역 파일에 `portfolio_risk` import/참조 0건
    (risk.py / order_engine.py / strategy_registry.py / scanner.py / session.py /
     src/api/order.py / src/realtime/* / src/auth/*).
    ⚠️ strategy_registry.py 포함 — 관찰 훅을 registry 메서드로 추가하면 위반.
  - `src/engine/portfolio_risk.py` 소스에 registry/kojiro/db/httpx/requests import 0건
    (순수함수 = quant_score / te_metrics / ta_indicators 선례).

(f) import sanity:
  - `src/routes/portfolio.py` 와 `log_analysis_engine` 이
    `from src.engine.strategies.kojiro import _kojiro_sector_key` 재사용 시 순환 없이 로드.

RED 상태:
  - `src/engine/portfolio_risk.py` 부재 → portfolio_risk 소스 스캔 테스트 FAIL (파일 없음).
  - `src/routes/portfolio.py` 부재 → import sanity FAIL (ImportError).
  - 8영역 격리 테스트는 현재도 통과(참조 0). Green 이후에도 유지되는 영구 가드.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"

# 매매 안전성 8영역 (spec §11)
_EIGHT_AREA_FILES = [
    _SRC / "engine" / "risk.py",
    _SRC / "engine" / "order_engine.py",
    _SRC / "engine" / "strategy_registry.py",
    _SRC / "engine" / "scanner.py",
    _SRC / "engine" / "session.py",
    _SRC / "api" / "order.py",
]
_EIGHT_AREA_DIRS = [
    _SRC / "realtime",
    _SRC / "auth",
]

_PORTFOLIO_RISK_SRC = _SRC / "engine" / "portfolio_risk.py"


def _iter_area_files():
    for f in _EIGHT_AREA_FILES:
        if f.exists():
            yield f
    for d in _EIGHT_AREA_DIRS:
        if d.exists():
            for f in sorted(d.rglob("*.py")):
                yield f


def _imported_names(tree: ast.AST) -> set[str]:
    """모듈이 import 하는 모듈 경로 문자열 집합 (import X / from X import ...)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


# ===========================================================================
# (e) 8영역 — portfolio_risk import/참조 0건
# ===========================================================================
class TestEightAreaIsolation:
    def test_no_portfolio_risk_import_or_reference_in_eight_areas(self):
        offenders: list[str] = []
        for f in _iter_area_files():
            src = f.read_text(encoding="utf-8")
            # 토큰 참조 (문자열 포함 광의) — import 뿐 아니라 어떤 참조도 금지
            if "portfolio_risk" in src:
                offenders.append(str(f.relative_to(_REPO_ROOT)))
        assert not offenders, (
            "매매 안전성 8영역에 'portfolio_risk' 참조 발견 — 관찰 훅은 호출자 주입(pull)만 허용. "
            f"위반 파일: {offenders}"
        )

    def test_strategy_registry_no_portfolio_risk_method(self):
        """strategy_registry.py 는 8영역 — 관찰 훅을 registry 메서드로 추가 금지 (명세 경고)."""
        f = _SRC / "engine" / "strategy_registry.py"
        assert f.exists()
        src = f.read_text(encoding="utf-8")
        assert "portfolio_risk" not in src, (
            "strategy_registry.py 에 portfolio_risk 참조 — registry 메서드 추가 시 8영역 diff 위반."
        )


# ===========================================================================
# (e) portfolio_risk.py 소스 — registry/kojiro/db/http import 0건
# ===========================================================================
class TestPortfolioRiskPurity:
    def test_module_exists(self):
        assert _PORTFOLIO_RISK_SRC.exists(), (
            "src/engine/portfolio_risk.py 부재 — 신규 순수함수 모듈 (Green 대상)."
        )

    def test_no_forbidden_imports(self):
        assert _PORTFOLIO_RISK_SRC.exists(), "portfolio_risk.py 부재 (Red)."
        src = _PORTFOLIO_RISK_SRC.read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = _imported_names(tree)

        forbidden_substrings = (
            "strategy_registry",
            "strategies.kojiro",
            "src.db",
            "httpx",
            "requests",
        )
        offenders = [
            name
            for name in imported
            for bad in forbidden_substrings
            if bad in name
        ]
        assert not offenders, (
            "portfolio_risk.py 는 순수함수 — registry/kojiro/db/http import 금지 "
            f"(quant_score 선례). 위반 import: {offenders}"
        )

    def test_no_registry_or_kojiro_token(self):
        """import 외 직접 토큰 참조도 금지 (lazy import / 전역 접근 차단)."""
        assert _PORTFOLIO_RISK_SRC.exists(), "portfolio_risk.py 부재 (Red)."
        src = _PORTFOLIO_RISK_SRC.read_text(encoding="utf-8")
        for token in ("_kojiro_sector_key", "trading_scheduler", "import requests", "import httpx"):
            assert token not in src, (
                f"portfolio_risk.py 에 '{token}' — 순수성 위반 (호출자 주입 규약)."
            )


# ===========================================================================
# (f) import sanity — 순환 import 없이 로드 + _kojiro_sector_key 재사용
# ===========================================================================
class TestImportSanity:
    def test_kojiro_sector_key_importable(self):
        """섹터 분류 정본 — 이식 금지, import 재사용."""
        from src.engine.strategies.kojiro import _kojiro_sector_key

        # 순수함수 계약 — master_raw None → 미분류-{ticker} 독립
        assert _kojiro_sector_key(None, "005930") == "미분류-005930"

    def test_routes_portfolio_loads_without_circular_import(self):
        """routes/portfolio.py 가 _kojiro_sector_key 재사용해도 순환 없이 로드."""
        import importlib

        mod = importlib.import_module("src.routes.portfolio")
        assert hasattr(mod, "get_portfolio_risk"), "get_portfolio_risk 핸들러 미정의."
        assert hasattr(mod, "router"), "FastAPI router 미정의."

    def test_log_analysis_engine_loads_and_has_builder(self):
        """log_analysis_engine 가 스냅샷 헬퍼 재사용해도 순환 없이 로드."""
        import importlib

        mod = importlib.import_module("src.engine.log_analysis_engine")
        assert hasattr(mod, "_build_portfolio_risk_snapshot"), (
            "_build_portfolio_risk_snapshot 헬퍼 미정의 — 20:10 리포트 스냅샷 seam."
        )
