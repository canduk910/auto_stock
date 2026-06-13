"""사이클 117 — KRX basDd 전일 영업일 + 빈 응답 시 최대 7일 재시도 + KIS 폴백.

근본 원인 (사이클 115 도입 후 발견):
- KRX 일별 매매정보 = 영업일 종료 후 (~16:00 KST) 가용
- today_kst() 영역 = 금일 → KRX 응답 빈 list → universe=0 응답
- 사용자 보고 (2026-06-12 15:40 KST): "지금 새로고침" → universe 0 ticker

시정 (사용자 결정 C: A + B + source 통합):
A. basDd = today - 1 day 시작 + 빈 응답 시 -1 day 재시도 (max 7일, 공휴일/주말 회피)
B. 7일 모두 0건 → KrxApiError raise → 호출자 KIS 자동 폴백
+ 라우트 응답 source 키 추가 (사이클 110 영역 누락 보강)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCANNER_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "scanner.py"
_ROUTE_PY = Path(__file__).resolve().parents[4] / "src" / "routes" / "stock_master.py"


def _read_scanner_source() -> str:
    return _SCANNER_PY.read_text(encoding="utf-8")


def _read_route_source() -> str:
    return _ROUTE_PY.read_text(encoding="utf-8")


def _find_function(tree: ast.AST, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_h1_basdd_uses_yesterday_not_today():
    """HIGH-1: _full_universe_load_krx_primary 가 today - 1 day 시작 (today_kst() 직접 사용 0)."""
    source = _read_scanner_source()
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_krx_primary")
    assert fn is not None
    fn_source = ast.unparse(fn)
    assert "timedelta" in fn_source
    assert "today_kst() - timedelta(days=1)" in fn_source


def test_h2_empty_response_retry_loop():
    """HIGH-2: 빈 응답 시 -1 day 재시도 + max_attempts=7 영역."""
    source = _read_scanner_source()
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_krx_primary")
    fn_source = ast.unparse(fn)
    assert "max_attempts = 7" in fn_source
    assert "range(max_attempts)" in fn_source
    assert "if kospi_trd or kosdaq_trd:" in fn_source
    assert "base_date -= timedelta(days=1)" in fn_source


def test_h3_krx_error_raised_after_max_attempts():
    """HIGH-3: 7일 모두 0건 시 KrxApiError raise (KIS 폴백 trigger 의무)."""
    source = _read_scanner_source()
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_krx_primary")
    fn_source = ast.unparse(fn)
    assert "_KrxApiError" in fn_source or "KrxApiError" in fn_source
    assert re.search(r"raise\s+_?KrxApiError", fn_source) is not None


def test_h4_empty_response_emit_visibility():
    """HIGH-4: 빈 응답 시 [krx_empty_response] INFO emit (운영 가시화)."""
    source = _read_scanner_source()
    assert "[krx_empty_response]" in source
    assert "basDd=" in source


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 라우트 응답 동기 summary 폐기 → {status, task_key} 의미 전환. source 키 노출은 GET /refresh-progress 응답으로 이전 (사이클 66 K-2 패턴)",
)
def test_h5_route_response_source_key_present():
    """HIGH-5: 라우트 응답 영역 source 키 추가 (사이클 110 영역 누락 보강)."""
    source = _read_route_source()
    tree = ast.parse(source)
    fn = _find_function(tree, "refresh_universe_now")
    assert fn is not None
    fn_source = ast.unparse(fn)
    assert '"source"' in fn_source or "'source'" in fn_source
    assert 'summary.get("source"' in fn_source or "summary.get('source'" in fn_source


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget 전환 — 동기 message 폐기 → 시작 안내 의미 전환 (사이클 66 K-2 패턴)",
)
def test_m1_message_includes_source():
    """MEDIUM-1: 응답 message 영역에 source= 영역 포함 (운영자 즉시 확인)."""
    source = _read_route_source()
    tree = ast.parse(source)
    fn = _find_function(tree, "refresh_universe_now")
    fn_source = ast.unparse(fn)
    assert "source=" in fn_source


def test_m2_rate_limit_sleep_in_retry_loop():
    """MEDIUM-2: 재시도 영역 50ms sleep 영구 영속 (KIS LMS chain 안전 마진 답습)."""
    source = _read_scanner_source()
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_krx_primary")
    fn_source = ast.unparse(fn)
    assert "_asyncio.sleep(0.05)" in fn_source


def test_g_ast1_no_direct_today_kst_strftime_in_krx():
    """AST 영구 가드: _full_universe_load_krx_primary 영역에 today_kst().strftime("%Y%m%d") 직접 사용 0건."""
    source = _read_scanner_source()
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_krx_primary")
    fn_source = ast.unparse(fn)
    assert "today_kst().strftime" not in fn_source
