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
        """G-145-MIGRATION-4: migration 적용 뒤 compose 배포가 보존된다.

        cycle248(2026-09-04) 재스코프 — compose 호출이 deploy.yml 에서
        `tools/deploy/compose_up_changed.sh`(선택적 배포)로 이동했다. 계약은 "migration
        루프 **뒤에** compose 배포가 따라온다" 이므로, deploy.yml 은 그 스크립트를 migration
        뒤에 호출하고 스크립트가 `docker compose` + `docker-compose.prod.yml` 을 품는지 본다.
        (스크립트 자체의 모드 계약은 tests/unit/deploy/test_cycle248_compose_up_changed.py.)
        """
        source = _DEPLOY_YML.read_text(encoding="utf-8")
        script_path = _DEPLOY_YML.parents[2] / "tools" / "deploy" / "compose_up_changed.sh"
        assert script_path.exists(), "선택적 배포 스크립트가 없다"
        script = script_path.read_text(encoding="utf-8")
        call = "bash tools/deploy/compose_up_changed.sh"
        assert call in source, "deploy.yml 이 compose 배포 스크립트를 호출하지 않는다"
        assert source.index("supabase/migrations") < source.index(call), (
            "compose 배포가 migration 적용보다 앞이다 — 새 코드가 옛 스키마 위에서 뜬다"
        )
        assert "docker compose" in script
        assert "docker-compose.prod.yml" in script

    def test_g_145_migration_5_workflow_run_trigger(self):
        """G-145-MIGRATION-5: 사이클 114 workflow_run trigger 영역 영구 영속."""
        source = _DEPLOY_YML.read_text(encoding="utf-8")

        # 사이클 114 CI conclusion success 가드 영속
        assert "workflow_run" in source
        assert "conclusion" in source and "success" in source
