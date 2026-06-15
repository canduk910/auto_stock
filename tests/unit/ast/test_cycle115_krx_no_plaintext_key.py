"""사이클 115 (2026-06-12) — KRX API 키 평문 로그/노출 영구 차단 AST 가드.

Red 명세: `_workspace/red/cycle115_krx_endpoint_integration.md`

SEC-1: src/api/krx.py 영역에 config.key 가 logger.* 함수 인자로 직접 전달 0건.

영속 의무:
- 사이클 17 KIS 인증 보안 답습 (API 키 평문 로그 절대 0)
- 사이클 112 보안 영속 (key_masked 응답 + 평문 노출 0)
- AUTH_KEY query parameter URL 로그 시 endpoint_path 만 사용 (URL 전체 로그 금지)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source

pytestmark = pytest.mark.unit


_KRX_PY = Path(__file__).resolve().parents[3] / "src" / "api" / "krx.py"


def test_sec1_no_plaintext_key_in_logger_calls():
    """SEC-1: src/api/krx.py 영역에 logger.* 함수 인자로 config.key 직접 전달 0건.

    AST 정적 검증 — logger.warning("...", config.key) / logger.info("...", config.key)
    등 평문 key 노출 패턴 영구 차단.

    허용 영역:
    - merged_params = {"AUTH_KEY": config.key} (query parameter 영역, 외부 노출 0)
    - URL 구성 (`url = f"{base}{path}"` — base/path 만, AUTH_KEY 미포함)
    """
    source = read_module_source(_KRX_PY)
    tree = ast.parse(source)

    violations = []

    for node in ast.walk(tree):
        # logger.* 함수 호출 영역 검출
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "logger":
                # logger.warning / .info / .error / .debug 등 모든 호출 영역
                for arg in node.args:
                    # config.key 영역 직접 전달 검출
                    if isinstance(arg, ast.Attribute):
                        if (
                            isinstance(arg.value, ast.Name)
                            and arg.value.id == "config"
                            and arg.attr == "key"
                        ):
                            violations.append(
                                f"line {node.lineno}: logger.{node.func.attr}(... config.key ...) 검출"
                            )

                # keyword args (logger.warning("msg", extra={"key": config.key})) 영역
                for kw in node.keywords:
                    if isinstance(kw.value, ast.Attribute):
                        if (
                            isinstance(kw.value.value, ast.Name)
                            and kw.value.value.id == "config"
                            and kw.value.attr == "key"
                        ):
                            violations.append(
                                f"line {node.lineno}: logger.{node.func.attr}(..., {kw.arg}=config.key) 검출"
                            )

    assert not violations, (
        "SEC-1 위반: src/api/krx.py 영역에 logger.* 함수 인자로 config.key 평문 전달 검출.\n"
        + "\n".join(violations)
        + "\n사이클 17 KIS 인증 보안 패턴 답습 의무 영역 + 사이클 112 보안 영속 위반."
    )


def test_sec2_no_url_full_logging():
    """SEC-2: 완성된 URL (AUTH_KEY 포함 가능 영역) 영구 영속 로그 차단.

    f"{url}" / f"{base}{path}" / f"...{url}..." 등 URL 영역 통째 로그 영구 차단.
    허용 영역: endpoint_path 만 로그.
    """
    source = read_module_source(_KRX_PY)
    tree = ast.parse(source)

    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "logger":
                for arg in node.args:
                    # f-string 영역 — url 변수 사용 검출
                    if isinstance(arg, ast.JoinedStr):
                        for value in arg.values:
                            if isinstance(value, ast.FormattedValue):
                                if isinstance(value.value, ast.Name) and value.value.id == "url":
                                    violations.append(
                                        f"line {node.lineno}: logger.{node.func.attr}(f'... {{url}} ...') 검출"
                                    )

                    # %s 포맷 영역 — url 변수 직접 전달
                    if isinstance(arg, ast.Name) and arg.id == "url":
                        violations.append(
                            f"line {node.lineno}: logger.{node.func.attr}(... url ...) 검출"
                        )

    assert not violations, (
        "SEC-2 위반: src/api/krx.py 영역에 url 변수 logger 직접 전달 검출.\n"
        + "\n".join(violations)
        + "\nAUTH_KEY query parameter URL 노출 위험 — endpoint_path 만 로그 의무."
    )


def test_sec3_endpoint_path_only_in_logs():
    """SEC-3: logger.* 호출 영역에 endpoint=%s 패턴 영속 영구 확인.

    사이클 112 영속: 로그 시 endpoint_path 만 사용 (정본 패턴).
    """
    source = read_module_source(_KRX_PY)

    # 최소 1건 endpoint=%s 패턴 영속 영구 확인
    assert "endpoint=%s" in source, (
        "SEC-3 위반: src/api/krx.py 영역에 endpoint=%s 패턴 영구 영속 부재. "
        "사이클 112 보안 영속 위반 (endpoint_path 만 로그 영역 영구 영속)."
    )
