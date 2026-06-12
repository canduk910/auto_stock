"""사이클 115 (2026-06-12) — KRX endpoint URL + OutBlock_1 키 AST 영구 가드.

Red 명세: `_workspace/red/cycle115_krx_endpoint_integration.md`

AST-1: KRX endpoint URL 정적 검증 (4 endpoint 경로 영구 영속)
AST-2: 응답 키 OutBlock_1 정적 검증 (사이클 112 영역 + 사이클 115 endpoint 영역)

영속 의무:
- 미래 endpoint 경로 변경 / OutBlock_1 키 변경 시 즉시 검출 영구 차단
- 사이클 109 G-AST 영역 패턴 답습 (KIS market-cap 화이트리스트 영역)
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_KRX_PY = Path(__file__).resolve().parents[3] / "src" / "api" / "krx.py"


def test_ast1_krx_endpoint_urls_present():
    """AST-1: src/api/krx.py 영역에 4 endpoint URL 문자열 존재 영구 영속.

    엔드포인트 변경 시 (예: KRX 측 URL 변경 또는 신규 endpoint 추가) 즉시 검출.
    """
    source = _KRX_PY.read_text(encoding="utf-8")

    required_endpoints = [
        "/sto/stk_bydd_trd",
        "/sto/ksq_bydd_trd",
        "/sto/stk_isu_base_info",
        "/sto/ksq_isu_base_info",
    ]

    for endpoint in required_endpoints:
        assert endpoint in source, (
            f"AST-1 위반: src/api/krx.py 영역에 endpoint '{endpoint}' 영구 영속 부재. "
            f"미래 KRX endpoint 영역 변경 영구 차단 가드 (사이클 115 정본 영구 영속)."
        )


def test_ast2_outblock1_key_present():
    """AST-2: src/api/krx.py 영역에 OutBlock_1 응답 키 문자열 존재 영구 영속.

    KRX 응답 형식 변경 시 (예: OutBlock_1 → OutBlock_2) 즉시 검출.
    """
    source = _KRX_PY.read_text(encoding="utf-8")

    assert "OutBlock_1" in source, (
        "AST-2 위반: src/api/krx.py 영역에 'OutBlock_1' 키 영구 영속 부재. "
        "KRX 응답 형식 정본 영구 영속 (사이클 112 + 사이클 115)."
    )


def test_ast3_get_method_persistence():
    """AST-3: src/api/krx.py 영역에 GET method 영속 (사이클 115 시정 영역 영구 차단).

    사이클 112 (POST 가정 결함) 시정 후 사이클 115 = GET 영속.
    미래 POST 회귀 영구 차단 (사이클 110 AST 영구 가드 패턴 답습).
    """
    source = _KRX_PY.read_text(encoding="utf-8")

    # GET method 영속 확인
    assert "client.get(" in source, (
        "AST-3 위반: src/api/krx.py 영역에 client.get( 영구 영속 부재. "
        "사이클 115 시정 (POST → GET) 영구 영속 위반 (외부 검증 정본: pykrx-openapi client.py)."
    )

    # POST method 회귀 영구 차단 검증 (정밀: client.post( 영역)
    # 주의: docstring 영역 "POST" 단어는 허용 (시정 이력 명시)
    # client.post( 영역 코드만 검출 (사이클 112 결함 영속 회귀 차단)
    assert "client.post(" not in source, (
        "AST-3 위반: src/api/krx.py 영역에 client.post( 회귀 영구 영속 검출. "
        "사이클 115 시정 영구 영속 위반 (GET method 정본)."
    )


def test_ast4_auth_key_in_query_params_not_headers():
    """AST-4: AUTH_KEY 가 query parameter 영역 영구 영속 (사이클 115 시정).

    사이클 112 (header 가정 결함) 시정 후 사이클 115 = query parameter 영속.
    """
    source = _KRX_PY.read_text(encoding="utf-8")

    # AUTH_KEY 가 params dict (merged_params 또는 params={"AUTH_KEY": ...}) 영역에 존재
    # 사이클 115 정본: merged_params = {"AUTH_KEY": config.key}
    assert "AUTH_KEY" in source, "AST-4 위반: AUTH_KEY 영역 영구 영속 부재"
    assert 'merged_params = {"AUTH_KEY"' in source or '"AUTH_KEY": config.key' in source, (
        "AST-4 위반: AUTH_KEY 가 query parameter dict 영역 영구 영속 부재. "
        "사이클 115 시정 (header → query parameter) 영구 영속 위반."
    )

    # header 영역에 AUTH_KEY 영구 차단 검증
    # headers = {"AUTH_KEY": ...} 영역 영구 차단 (사이클 112 회귀 차단)
    assert 'headers = {' not in source or '"AUTH_KEY"' not in source.split('headers = {')[-1].split('}')[0] if 'headers = {' in source else True, (
        "AST-4 위반: src/api/krx.py 영역에 headers dict 내 AUTH_KEY 회귀 검출. "
        "사이클 115 시정 영구 영속 위반."
    )
