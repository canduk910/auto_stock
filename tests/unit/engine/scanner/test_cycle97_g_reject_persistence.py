"""사이클 97 L-1 — 사이클 88 G-REJECT 외부 LLM 영구 차단 영속 (LOW).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 88 G-REJECT AST 가드 영속 (외부 LLM 영구 차단)
- 사이클 97 영역 신규 도입 후에도 영구 차단 영속

기대 동작 (영속, backend-dev 인계):
- `fetch_top_500_universe` 본체에 외부 LLM (openai / anthropic / requests + http://api.openai 등) 호출 영구 부재
- KIS API 영역만 영속 (KIS 정본 fluctuation.py)

Red 상태 (사이클 97): production 코드 영속 → PASS (사이클 88 영속 가드 영역).
                   `_fetch_fluctuation` 신규 함수 미존재 → 본 영역은 영속 (AST 정적 검사 = 부정 검증).

영속 의무:
- 사이클 88 G-REJECT 패턴 영속
- 사이클 89/91/94/96 영역 폐기 후에도 영속
- 매매 안전성 영향 0
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _scanner_module_source() -> str:
    return _scanner_module_path().read_text(encoding="utf-8")


def test_l1_no_external_llm_import_in_scanner():
    """L-1.a: scanner.py 에 외부 LLM 라이브러리 import 영구 부재.

    검증 영역 (사이클 88 G-REJECT AST):
    - `import openai` 영구 부재
    - `import anthropic` 영구 부재
    - `from openai import ...` 영구 부재
    - `from anthropic import ...` 영구 부재

    영속 의무: 사이클 88 G-REJECT 영역 영구 차단.
    """
    source = _scanner_module_source()
    tree = ast.parse(source)

    forbidden_modules = {"openai", "anthropic"}
    found_imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split(".")[0]
                if module_root in forbidden_modules:
                    found_imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in forbidden_modules:
                found_imports.append(f"from {node.module} import ...")

    assert not found_imports, (
        f"\n사이클 97 L-1.a 위반 — scanner.py 외부 LLM import 영속:\n"
        f"  발견: {found_imports}\n"
        f"  사이클 88 G-REJECT 영역 영구 차단 의무\n"
        f"  사이클 97 영역 = KIS API 정본만 영속"
    )


def test_l1_no_external_llm_url_literal_in_scanner():
    """L-1.b: scanner.py 에 외부 LLM URL literal 영구 부재.

    검증 영역:
    - `api.openai.com` 영구 부재
    - `api.anthropic.com` 영구 부재

    영속 의무: 사이클 88 G-REJECT 영역 영구 차단.
    """
    source = _scanner_module_source()

    forbidden_urls = ["api.openai.com", "api.anthropic.com"]
    found: list[str] = []

    for url in forbidden_urls:
        if url in source:
            found.append(url)

    assert not found, (
        f"\n사이클 97 L-1.b 위반 — scanner.py 외부 LLM URL 영속:\n"
        f"  발견: {found}\n"
        f"  사이클 88 G-REJECT 영역 영구 차단 의무"
    )


def test_l1_scanner_uses_kis_api_only():
    """L-1.c: scanner.py source 에 KIS API URL prefix 영속 (`/uapi/`).

    검증 영역:
    - `/uapi/` prefix 영속 (KIS API 영역 정합)
    - 사이클 97 시정 후 `/uapi/domestic-stock/v1/ranking/fluctuation` 영속

    영속 의무: KIS API 정본 영역 영구 영속.
    """
    source = _scanner_module_source()

    assert "/uapi/" in source, (
        "\n사이클 97 L-1.c 위반 — scanner.py KIS API URL 영역 부재:\n"
        "  사이클 97 시정 = `/uapi/domestic-stock/v1/ranking/fluctuation` 영속 의무\n"
        "  KIS API 정본 영역 영구 영속 의무"
    )
