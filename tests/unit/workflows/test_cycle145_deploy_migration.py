"""사이클 145 — deploy.yml 영역 영구 영속 Supabase migration 자동 적용 회귀 가드.

결함 1 시정:
- 사이클 129 commit `df8cf82` (6/13 push) = production EC2 배포됐으나 migration 034 미적용
- Supabase 운영 로그 = 6/13~6/16 매일 16:30 KST PGRST204 master_raw 컬럼 부재 결함
- 메인 세션 hotfix 완료 (Supabase MCP apply_migration 영역)
- 사이클 145 = deploy.yml 자동 migration 적용 워크플로우 추가

영속 의무:
- silent 결함 영구 차단 (D+N 누적 결함 영역 영구 영속 방지)
- graceful (SUPABASE_DB_URL secret 부재 / psql 부재 시 skip)
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_DEPLOY_YML = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "deploy.yml"


class TestDeployMigration:
    """deploy.yml 영역 영구 영속 Supabase migration 자동 적용."""

    def test_g_145_migration_1_psql_command_present(self):
        """G-145-MIGRATION-1: deploy.yml 영역에 `psql` migration 적용 영역 영구 영속."""
        assert _DEPLOY_YML.exists()
        source = _DEPLOY_YML.read_text(encoding="utf-8")

        # psql 영역 영구 영속 명령어 영역
        assert "psql" in source, "deploy.yml 영역 영구 영속 psql migration 적용 부재"
        # supabase/migrations 영역 영구 영속 경로
        assert "supabase/migrations" in source, (
            "deploy.yml 영역 supabase/migrations 경로 부재"
        )

    def test_g_145_migration_2_supabase_db_url_secret(self):
        """G-145-MIGRATION-2: SUPABASE_DB_URL secret 영역 영구 영속 workflow env."""
        source = _DEPLOY_YML.read_text(encoding="utf-8")

        # secrets.SUPABASE_DB_URL 영역 영구 영속
        assert "SUPABASE_DB_URL" in source, (
            "deploy.yml 영역 SUPABASE_DB_URL secret 부재"
        )

    def test_g_145_migration_3_graceful_skip(self):
        """G-145-MIGRATION-3: SUPABASE_DB_URL 영역 부재 / psql 부재 시 graceful skip."""
        source = _DEPLOY_YML.read_text(encoding="utf-8")

        # graceful skip 영역 영구 영속 키워드
        assert "graceful" in source.lower() or "skip" in source.lower(), (
            "deploy.yml graceful skip 영역 부재"
        )

    def test_g_145_migration_4_docker_compose_preserved(self):
        """G-145-MIGRATION-4: docker compose 배포 영역 영구 영속 (사이클 114 영속)."""
        source = _DEPLOY_YML.read_text(encoding="utf-8")

        # docker compose 영역 영구 영속 보존
        assert "docker compose" in source
        assert "docker-compose.prod.yml" in source

    def test_g_145_migration_5_workflow_run_trigger(self):
        """G-145-MIGRATION-5: 사이클 114 workflow_run trigger 영역 영구 영속."""
        source = _DEPLOY_YML.read_text(encoding="utf-8")

        # 사이클 114 CI conclusion success 가드 영속
        assert "workflow_run" in source
        assert "conclusion" in source and "success" in source
