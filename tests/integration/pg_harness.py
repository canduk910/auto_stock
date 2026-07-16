"""실 Postgres 통합 하네스 (Supabase→RDS 이전, 단계 M1 증분 1).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md`.

목적 = mock 단위 테스트로 못 잡는 **실 SQL·JSONB codec** 검증 안전망 (계획 3대 리스크
1순위 = JSONB codec 누락 silent 결함). mock 이 주력, 통합은 codec·타입 왕복 실증.

동작:
- `DATABASE_URL_TEST` env 있으면 그 DSN 사용 (CI 의 postgres:15 service 컨테이너).
- 없으면 로컬 docker `postgres:15` 컨테이너를 subprocess 로 기동 (testcontainers 부재).
  랜덤 host 포트(`-p 0:5432`) → `docker port` 로 파싱 → healthcheck.
- 확보한 DSN 으로 asyncpg 연결 → **migration 001~041 순차 적용** (각 `.sql` 파일 내용을
  `conn.execute`) → `src.db.pg` 전역 풀을 그 DSN 으로 연결 → yield → teardown.

docker 도, `DATABASE_URL_TEST` 도 없으면 fixture 가 `pytest.skip` — 통합은 옵셔널.

⚠️ 이 파일은 Red 단계 하네스 정의. `conftest.py` 가 fixture 를 re-export 한다.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
_PG_IMAGE = "postgres:15"
_PG_PASSWORD = "testpg"
_PG_DB = "auto_stock_test"
_PG_USER = "postgres"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return True
    except Exception:
        return False


def _start_pg_container() -> tuple[str, str]:
    """postgres:15 컨테이너를 랜덤 포트로 기동. (container_id, dsn) 반환."""
    name = f"auto_stock_pg_test_{uuid.uuid4().hex[:8]}"
    cid = subprocess.check_output(
        [
            "docker", "run", "-d", "--rm",
            "--name", name,
            "-e", f"POSTGRES_PASSWORD={_PG_PASSWORD}",
            "-e", f"POSTGRES_DB={_PG_DB}",
            "-e", f"POSTGRES_USER={_PG_USER}",
            "-p", "0:5432",
            _PG_IMAGE,
        ],
        text=True,
    ).strip()

    # 호스트 포트 파싱: "0.0.0.0:54321" 또는 "[::]:54321"
    port_line = subprocess.check_output(
        ["docker", "port", cid, "5432/tcp"], text=True
    ).strip().splitlines()[0]
    host_port = port_line.rsplit(":", 1)[-1]

    dsn = (
        f"postgresql://{_PG_USER}:{_PG_PASSWORD}@127.0.0.1:{host_port}/{_PG_DB}"
    )
    return cid, dsn


def _stop_pg_container(cid: str) -> None:
    try:
        subprocess.run(
            ["docker", "stop", cid],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except Exception:
        pass


async def _wait_healthy(dsn: str, *, timeout: float = 30.0) -> None:
    import asyncpg

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = await asyncpg.connect(dsn)
            await conn.execute("SELECT 1")
            await conn.close()
            return
        except Exception as exc:  # noqa: BLE001 — 기동 대기 중 연결 거부 재시도
            last_exc = exc
            await asyncio.sleep(0.5)
    raise RuntimeError(f"postgres 컨테이너 healthcheck 타임아웃: {last_exc!r}")


async def _apply_migrations(dsn: str) -> None:
    """migration 001~041 순차 적용 (asyncpg 로 각 .sql 파일 실행)."""
    import asyncpg

    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise RuntimeError(f"마이그레이션 없음: {_MIGRATIONS_DIR}")
    conn = await asyncpg.connect(dsn)
    try:
        for sql_path in files:
            sql = sql_path.read_text(encoding="utf-8")
            await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """실 Postgres DSN 확보 (env 우선, 없으면 docker 기동). 세션 스코프."""
    env_dsn = os.environ.get("DATABASE_URL_TEST")
    if env_dsn:
        yield env_dsn
        return

    if not _docker_available():
        pytest.skip("docker/DATABASE_URL_TEST 없음 — 실 Postgres 통합 테스트 skip")

    cid, dsn = _start_pg_container()
    try:
        asyncio.run(_wait_healthy(dsn))
        yield dsn
    finally:
        _stop_pg_container(cid)


@pytest.fixture(scope="session")
def pg_migrated(pg_dsn: str) -> str:
    """migration 001~041 적용된 DSN. 세션 1회."""
    asyncio.run(_apply_migrations(pg_dsn))
    return pg_dsn


@pytest.fixture
async def pg_pool(pg_migrated: str):
    """src.db.pg 전역 풀을 통합 DSN 으로 연결 → yield → close.

    `pg.fetch`/`execute` 등이 이 풀을 통해 실 SQL 을 실행한다.
    JSONB codec 등록(`_init_conn`) 실증의 핵심 경로.
    """
    import src.db.pg as pg

    # settings.database_url 을 통합 DSN 으로 임시 교체 (init_pool 이 참조).
    from src.config import settings

    original = settings.database_url
    settings.database_url = pg_migrated
    await pg.init_pool()
    try:
        yield pg
    finally:
        await pg.close_pool()
        settings.database_url = original


@pytest.fixture
async def clean_positions(pg_pool):
    """positions 테이블 비운 상태로 시작 (테스트 격리)."""
    await pg_pool.execute("DELETE FROM positions")
    yield pg_pool
    await pg_pool.execute("DELETE FROM positions")


@pytest.fixture
async def clean_strategy_config(pg_pool):
    """strategy_config 테이블 비운 상태로 시작 (테스트 격리)."""
    await pg_pool.execute("DELETE FROM strategy_config")
    yield pg_pool
    await pg_pool.execute("DELETE FROM strategy_config")


# ---------------------------------------------------------------------------
# M1 증분 2 — 4 모듈 (log_reports/backtest_runs/market_regime_snapshots/
# pending_next_day_clear) 테이블 격리 fixture. seed 행이 있으면 DELETE 선행.
# ---------------------------------------------------------------------------
@pytest.fixture
async def clean_log_reports(pg_pool):
    """daily_log_reports 테이블 비운 상태로 시작 (테스트 격리)."""
    await pg_pool.execute("DELETE FROM daily_log_reports")
    yield pg_pool
    await pg_pool.execute("DELETE FROM daily_log_reports")


@pytest.fixture
async def clean_backtest_runs(pg_pool):
    """backtest_runs 테이블 비운 상태로 시작 (테스트 격리)."""
    await pg_pool.execute("DELETE FROM backtest_runs")
    yield pg_pool
    await pg_pool.execute("DELETE FROM backtest_runs")


@pytest.fixture
async def clean_market_regime(pg_pool):
    """market_regime_snapshots 테이블 비운 상태로 시작 (테스트 격리)."""
    await pg_pool.execute("DELETE FROM market_regime_snapshots")
    yield pg_pool
    await pg_pool.execute("DELETE FROM market_regime_snapshots")


@pytest.fixture
async def clean_pending_ndc(pg_pool):
    """pending_next_day_clear 테이블 비운 상태로 시작 (테스트 격리)."""
    await pg_pool.execute("DELETE FROM pending_next_day_clear")
    yield pg_pool
    await pg_pool.execute("DELETE FROM pending_next_day_clear")


# ---------------------------------------------------------------------------
# M1 증분 3 (M1 마무리) — daily_performance(RPC) / strategy_funnel 격리 fixture.
# ---------------------------------------------------------------------------
@pytest.fixture
async def clean_daily_performance(pg_pool):
    """daily_performance 테이블 비운 상태로 시작 (테스트 격리).

    ⚠️ RPC(`recompute_daily_performance()`)가 trade_history 를 읽어 daily_performance
    를 UPDATE 하므로 trade_history 도 동반 정리 (RPC seed 격리).
    """
    await pg_pool.execute("DELETE FROM daily_performance")
    await pg_pool.execute("DELETE FROM trade_history")
    yield pg_pool
    await pg_pool.execute("DELETE FROM daily_performance")
    await pg_pool.execute("DELETE FROM trade_history")


@pytest.fixture
async def clean_strategy_funnel(pg_pool):
    """strategy_funnel_snapshots 테이블 비운 상태로 시작 (테스트 격리)."""
    await pg_pool.execute("DELETE FROM strategy_funnel_snapshots")
    yield pg_pool
    await pg_pool.execute("DELETE FROM strategy_funnel_snapshots")
