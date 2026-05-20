"""사이클 22 — Dockerfile .token_cache 디렉토리 권한 보강 회귀 가드.

배경:
    사이클 20 (35ebe3a) 토큰 캐시 영속화 도입 후 운영 결함 발생.
    docker-compose.prod.yml 볼륨 ./.token_cache:/app/.token_cache 마운트 시
    호스트 디렉토리가 root:root 로 생성되어 USER appuser (non-root) 가 쓰기 거부됨.

    PermissionError: [Errno 13] Permission denied: '.token_cache/quote_sub.json'

핵심 규약:
    A) Dockerfile 에 `mkdir -p /app/.token_cache` 라인 존재
    B) `mkdir -p /app/.token_cache` 가 `chown -R appuser:appuser /app` 보다 *앞*
    C) `USER appuser` 지시문이 `mkdir`/`chown` *뒤*

도구: 정적 텍스트 파싱 (pathlib + 정규식). docker build 자체는 회귀에서 실행 안 함 (CI 부담).
"""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile"


def _read_dockerfile_lines() -> list[str]:
    """Dockerfile 을 줄 단위로 읽어 list[str] 반환."""
    assert DOCKERFILE_PATH.exists(), f"Dockerfile not found at {DOCKERFILE_PATH}"
    return DOCKERFILE_PATH.read_text(encoding="utf-8").splitlines()


def _find_line_index(lines: list[str], pattern: str) -> int | None:
    """정규식 패턴에 매칭되는 첫 라인 인덱스 반환 (없으면 None)."""
    rx = re.compile(pattern)
    for idx, line in enumerate(lines):
        if rx.search(line):
            return idx
    return None


# === (A) mkdir -p /app/.token_cache 라인 존재 ===

def test_dockerfile_creates_token_cache_dir() -> None:
    """Dockerfile 에 `mkdir -p /app/.token_cache` 라인이 존재해야 한다.

    빌드 시점에 디렉토리를 명시 생성해야 Docker 볼륨 마운트 시 호스트 권한 매칭이
    보장된다 (컨테이너 측 권한 우선 매칭).
    """
    lines = _read_dockerfile_lines()
    idx = _find_line_index(lines, r"mkdir\s+-p\s+/app/\.token_cache")
    assert idx is not None, (
        "Dockerfile 에 `mkdir -p /app/.token_cache` 라인이 없습니다. "
        "사이클 20 핫픽스 영구화 위해 빌드 시점 디렉토리 생성 필수."
    )


# === (B) mkdir 가 chown 보다 앞 ===

def test_mkdir_before_chown_order() -> None:
    """`mkdir -p /app/.token_cache` 가 `chown -R appuser:appuser /app` 보다 앞에 있어야 한다.

    순서가 뒤바뀌면 chown 이 .token_cache 디렉토리를 못 잡고 root:root 잔존.
    """
    lines = _read_dockerfile_lines()
    mkdir_idx = _find_line_index(lines, r"mkdir\s+-p\s+/app/\.token_cache")
    chown_idx = _find_line_index(lines, r"chown\s+-R\s+appuser:appuser\s+/app")

    assert mkdir_idx is not None, "mkdir 라인이 없습니다."
    assert chown_idx is not None, "chown -R appuser:appuser /app 라인이 없습니다."
    assert mkdir_idx < chown_idx, (
        f"`mkdir -p /app/.token_cache` (line {mkdir_idx}) 가 "
        f"`chown -R appuser:appuser /app` (line {chown_idx}) 보다 *앞* 에 있어야 합니다. "
        f"chown 이 mkdir 보다 먼저 실행되면 .token_cache 가 root:root 잔존."
    )


# === (C) USER appuser 가 mkdir / chown 뒤 ===

def test_user_appuser_after_chown() -> None:
    """`USER appuser` 지시문이 `mkdir` / `chown` 라인 *뒤* 에 있어야 한다.

    USER appuser 가 앞에 있으면 non-root 가 /app 에 mkdir/chown 시도 → 거부.
    """
    lines = _read_dockerfile_lines()
    mkdir_idx = _find_line_index(lines, r"mkdir\s+-p\s+/app/\.token_cache")
    chown_idx = _find_line_index(lines, r"chown\s+-R\s+appuser:appuser\s+/app")
    user_idx = _find_line_index(lines, r"^\s*USER\s+appuser\s*$")

    assert mkdir_idx is not None, "mkdir 라인이 없습니다."
    assert chown_idx is not None, "chown 라인이 없습니다."
    assert user_idx is not None, "`USER appuser` 지시문이 없습니다."
    assert mkdir_idx < user_idx, (
        f"`mkdir -p /app/.token_cache` (line {mkdir_idx}) 가 "
        f"`USER appuser` (line {user_idx}) 보다 *앞* 에 있어야 합니다."
    )
    assert chown_idx < user_idx, (
        f"`chown -R appuser:appuser /app` (line {chown_idx}) 가 "
        f"`USER appuser` (line {user_idx}) 보다 *앞* 에 있어야 합니다."
    )
