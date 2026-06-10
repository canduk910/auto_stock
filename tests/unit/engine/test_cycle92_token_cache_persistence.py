"""사이클 92 M-4 — _preissue_all_tokens 24h 캐시 영속 (MEDIUM, 사이클 20 답습).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q3 영속:
- 사이클 20 토큰 캐시 (24h `.token_cache/` 볼륨 영속) 의무
- 자동 재기동 시 캐시 hit 우선 → 신규 발급 0건 → LMS chain 차단
- 시간당 3회 cap (Q30=A) × 토큰 발급 0건 = LMS 안전 영역

기대 동작 (Green, 사이클 92):
- `_preissue_all_tokens` 메서드 영속 (Scheduler)
- 캐시 hit 우선 정합 (사이클 20)
- `.token_cache/` 볼륨 마운트 영속 (Dockerfile + docker-compose)

Red 상태 (사이클 92, production 변경 0):
- 사이클 20 영속 → PASS (영속 가드)

영속 의무:
- 사이클 20 토큰 24h 캐시 영속 (자동 재기동 LMS chain 안전 마진)
- 사이클 92 자동 재기동 시 캐시 hit 우선 영역 영속
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_m4_preissue_all_tokens_method_persists():
    """M-4-1: Scheduler._preissue_all_tokens 메서드 영속 (사이클 20 답습).

    검증:
    - `Scheduler._preissue_all_tokens` async 메서드 존재
    - 사이클 92 자동 재기동 시 캐시 hit 우선 영역 영속

    영속 의무 (domain-expert A2-Q3):
    - 토큰 캐시 24h 영속 의무
    - 자동 재기동 시점 캐시 hit → 신규 발급 0건 → LMS chain 차단
    """
    from src.engine.scheduler import TradingScheduler

    method = getattr(TradingScheduler, "_preissue_all_tokens", None)
    assert method is not None, (
        "\n사이클 92 M-4-1 위반 — TradingScheduler._preissue_all_tokens 메서드 부재:\n"
        "  근거: 사이클 20 토큰 24h 캐시 영속 의무"
    )
    assert inspect.iscoroutinefunction(method), (
        "\n사이클 92 M-4-1 위반 — _preissue_all_tokens async 아님"
    )


def test_m4_token_cache_volume_in_dockerfile():
    """M-4-2: Dockerfile 에 `.token_cache/` 디렉토리 권한 보장 (사이클 20/22 답습).

    검증:
    - Dockerfile 에 `.token_cache` 영역 등장
    - 사이클 22 hotfix (chown 권한 보장) 영속

    영속 의무: 토큰 캐시 24h 영속 → 자동 재기동 시 신규 발급 0건.
    """
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    dockerfile = repo_root / "Dockerfile"

    assert dockerfile.exists(), (
        f"\n사이클 92 M-4-2 위반 — Dockerfile 파일 부재:\n  {dockerfile}"
    )

    source = dockerfile.read_text(encoding="utf-8")
    assert ".token_cache" in source, (
        "\n사이클 92 M-4-2 위반 — Dockerfile 에 .token_cache 영역 누락:\n"
        "  영속 의무: 사이클 20/22 토큰 캐시 24h 영속"
    )


def test_m4_token_cache_volume_in_docker_compose():
    """M-4-3: docker-compose.yml 에 `.token_cache:/app/.token_cache` bind mount 영속.

    검증:
    - docker-compose.yml 에 `.token_cache` 영역 등장 (bind mount)
    - 컨테이너 재기동 시점 토큰 영속

    영속 의무: 자동 재기동 시 캐시 hit 우선 → LMS chain 차단.
    """
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    compose = repo_root / "docker-compose.yml"

    assert compose.exists(), (
        f"\n사이클 92 M-4-3 위반 — docker-compose.yml 파일 부재:\n  {compose}"
    )

    source = compose.read_text(encoding="utf-8")
    assert ".token_cache" in source, (
        "\n사이클 92 M-4-3 위반 — docker-compose.yml 에 .token_cache 영역 누락:\n"
        "  영속 의무: 사이클 20 bind mount 영속"
    )
