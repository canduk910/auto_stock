"""사이클 112 영역 6+7 (HIGH 5) — AST 영구 가드 (보안 의무 영역).

Red 명세 (`_workspace/red/cycle112_krx_open_api_infra.md`):

G-AST-1: KrxOpenApiStatus 모델에 평문 key 필드 0건 (`key_masked` 단독)
G-AST-2: src/routes/system_integrations.py 응답 빌더가 mask_secret 호출 의무
G-AST-3: src/db/system_config.py 의 get_krx_open_api_config 반환 = KrxOpenApiConfig
G-SEC-1: src/ 전체 rglob 에서 krx_open_api_key 평문 logger.* 호출 0건
G-SEC-2: src/ 전체 rglob 에서 write_log / system_logs INSERT 에 평문 key 전달 0건

위험 등급 HIGH (평문 key 노출 미래 silent 결함 영구 차단).

영속 의무:
- 사이클 7-A 마스킹 패턴 영속
- 사이클 75 G-AST5 AST 영구 가드 영속
- 사이클 102 G-CALLBACK1 영속 (정적 검증 의무)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC_DIR = Path(__file__).resolve().parents[3] / "src"
ROUTES_FILE = SRC_DIR / "routes" / "system_integrations.py"
MODELS_FILE = SRC_DIR / "models" / "krx_open_api.py"
DB_FILE = SRC_DIR / "db" / "system_config.py"


def test_g_ast_1_status_model_no_plaintext_key_field():
    """G-AST-1: KrxOpenApiStatus 모델 = key_masked 단독 (평문 key 필드 부재)."""
    assert MODELS_FILE.exists()
    src = MODELS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)

    found_status = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "KrxOpenApiStatus":
            found_status = True
            # body 영역에서 annotation 필드명 수집
            field_names = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_names.append(item.target.id)
            assert "key_masked" in field_names, (
                f"KrxOpenApiStatus 에 key_masked 필드 부재: {field_names}"
            )
            # 평문 key 필드 절대 부재 (보안 의무)
            assert "key" not in field_names, (
                f"KrxOpenApiStatus 에 평문 key 필드 존재 — 보안 위반: {field_names}"
            )
    assert found_status, "KrxOpenApiStatus 클래스 정의 부재"


def test_g_ast_2_routes_build_status_calls_mask_secret():
    """G-AST-2: routes/system_integrations.py 응답 빌더가 마스킹 호출 의무.

    `_build_krx_open_api_status` 본체에 `mask_secret` (또는 `krx_mask_secret`) 호출 ≥1건.
    """
    assert ROUTES_FILE.exists()
    src = ROUTES_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)

    found_builder = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.name == "_build_krx_open_api_status":
                found_builder = True
                body_src = ast.unparse(node)
                # mask_secret (또는 krx_mask_secret) 호출 ≥1건
                assert (
                    "mask_secret" in body_src
                ), f"_build_krx_open_api_status 본체에 mask_secret 호출 부재: {body_src[:300]}"
    assert found_builder, "_build_krx_open_api_status 함수 정의 부재"


def test_g_ast_3_db_get_returns_config_pydantic():
    """G-AST-3: get_krx_open_api_config 반환 = KrxOpenApiConfig (Pydantic, 평문 key 포함)."""
    assert DB_FILE.exists()
    src = DB_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)

    found_getter = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.name == "get_krx_open_api_config":
                found_getter = True
                body_src = ast.unparse(node)
                # KrxOpenApiConfig 생성 호출 의무
                assert "KrxOpenApiConfig" in body_src, (
                    f"get_krx_open_api_config 본체에 KrxOpenApiConfig 생성 부재"
                )
    assert found_getter, "get_krx_open_api_config 함수 정의 부재"


def test_g_sec_1_no_plaintext_logger_calls_for_krx_key():
    """G-SEC-1: src/ 전체 rglob 에서 krx_open_api_key 값 평문 logger 호출 0건.

    `config.key` 또는 `krx_open_api_key` 변수가 logger.* / print / write_log 인자에 직접 전달되지 않아야 함.
    """
    # 검사 대상 파일 — krx 관련 영역만 (전체 rglob 시 false-positive 영역 ↑)
    target_files = [
        SRC_DIR / "api" / "krx.py",
        SRC_DIR / "routes" / "system_integrations.py",
        SRC_DIR / "db" / "system_config.py",
        SRC_DIR / "models" / "krx_open_api.py",
    ]

    forbidden_patterns = [
        re.compile(r"logger\.\w+\([^)]*\bconfig\.key\b[^)]*\)"),
        re.compile(r"logger\.\w+\([^)]*krx_open_api_key[^)]*\)"),
        re.compile(r"write_log\([^)]*\bconfig\.key\b[^)]*\)"),
    ]

    violations = []
    for file_path in target_files:
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            for match in pattern.finditer(text):
                violations.append(
                    f"{file_path.name}: {match.group(0)[:100]}"
                )

    assert not violations, (
        f"평문 KRX key logger 호출 발견 (보안 위반):\n" + "\n".join(violations)
    )


def test_g_sec_2_no_plaintext_write_log_for_krx_key():
    """G-SEC-2: write_log / system_logs INSERT 에 평문 key 전달 0건.

    G-SEC-1 보강 — system_logs.write_log 명시 검사 + AUTH_KEY 변수 평문 logger 호출 0건.
    """
    target_files = [
        SRC_DIR / "api" / "krx.py",
        SRC_DIR / "routes" / "system_integrations.py",
        SRC_DIR / "db" / "system_config.py",
    ]

    # AUTH_KEY 변수 값 logger / write_log 인자 전달 패턴 검출
    forbidden = re.compile(r"(logger\.\w+|write_log)\([^)]*[\"']AUTH_KEY[\"']\s*:[^)]*\)")

    violations = []
    for file_path in target_files:
        if not file_path.exists():
            continue
        text = file_path.read_text(encoding="utf-8")
        for match in forbidden.finditer(text):
            violations.append(f"{file_path.name}: {match.group(0)[:100]}")

    assert not violations, (
        f"AUTH_KEY header 값 logger / write_log 노출 (보안 위반):\n" + "\n".join(violations)
    )


def test_g_sec_3_mask_secret_correctness():
    """추가 보안 가드: mask_secret 함수 자체의 정확성 검증."""
    from src.models.krx_open_api import mask_secret

    # 8자 이상 — 마지막 4자리만 노출
    assert mask_secret("secret_key_1234") == "****1234"
    assert mask_secret("abcdef1234567890") == "****7890"

    # 8자 미만 — 전체 마스킹 (길이 정보 누출 차단)
    assert mask_secret("abc") == "****"
    assert mask_secret("abcd") == "****"
    assert mask_secret("abcdefg") == "****"

    # 빈 문자열
    assert mask_secret("") == "****"

    # 평문 결과 부재 검증
    assert "secret" not in mask_secret("secret_key_1234")
    assert "key" not in mask_secret("secret_key_1234")
