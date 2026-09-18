"""macro_lite/oas_history_store.py — load_seed() + CLI 엔트리 + 자동 적재 금지 검증 (REQ-PKG-04).

원본 stock/oas_history_store.py의 merge_and_persist/slice_history 시그니처와
반환 형식을 그대로 사용한다 (added/removed/total/first_date/last_date).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from macro_lite import oas_history_store as store


def _recent_dates(n: int, start_days_ago: int) -> list[str]:
    """10년 이내(slice_history 컷오프 통과)인 날짜 n개를 과거방향으로 생성."""
    base = date.today() - timedelta(days=start_days_ago)
    return [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def _write_seed(path: Path, series_rows: dict) -> Path:
    path.write_text(json.dumps(series_rows), encoding="utf-8")
    return path


# ── load_seed 기본 동작 ────────────────────────────────────────────

def test_load_seed_merges_each_series(tmp_path):
    dates_hy = _recent_dates(5, start_days_ago=100)
    dates_ig = _recent_dates(7, start_days_ago=200)
    seed = {
        "BAMLH0A0HYM2": [{"date": d, "value": 3.5} for d in dates_hy],
        "BAMLC0A0CM": [{"date": d, "value": 1.2} for d in dates_ig],
    }
    seed_path = _write_seed(tmp_path / "seed.json", seed)

    stats = store.load_seed(seed_path)
    assert set(stats.keys()) == {"BAMLH0A0HYM2", "BAMLC0A0CM"}
    # merge_and_persist 반환 형식 그대로 (added/removed/total/first_date/last_date)
    for series_id, n_expected in (("BAMLH0A0HYM2", 5), ("BAMLC0A0CM", 7)):
        s = stats[series_id]
        assert s["total"] == n_expected
        assert s["added"] == n_expected

    assert len(store.slice_history("BAMLH0A0HYM2", 10)) == 5
    assert len(store.slice_history("BAMLC0A0CM", 10)) == 7


def test_load_seed_accepts_str_path(tmp_path):
    dates = _recent_dates(3, start_days_ago=30)
    seed = {"BAMLH0A0HYM2": [{"date": d, "value": 2.0} for d in dates], "BAMLC0A0CM": []}
    seed_path = _write_seed(tmp_path / "seed.json", seed)

    stats = store.load_seed(str(seed_path))
    assert stats["BAMLH0A0HYM2"]["total"] == 3


def test_load_seed_idempotent_total_unchanged(tmp_path):
    dates = _recent_dates(4, start_days_ago=50)
    seed = {"BAMLH0A0HYM2": [{"date": d, "value": 4.0} for d in dates], "BAMLC0A0CM": []}
    seed_path = _write_seed(tmp_path / "seed.json", seed)

    store.load_seed(seed_path)
    total_first = len(store.get_history("BAMLH0A0HYM2"))

    store.load_seed(seed_path)
    total_second = len(store.get_history("BAMLH0A0HYM2"))

    assert total_first == total_second == 4


def test_load_seed_does_not_overwrite_existing_date(tmp_path):
    d = _recent_dates(1, start_days_ago=10)[0]

    # 1) merge_and_persist로 먼저 값 A 저장
    store.merge_and_persist("BAMLH0A0HYM2", [{"date": d, "value": 111.0}])

    # 2) seed에 같은 date, 다른 값 B → load_seed 후에도 A 유지 (기존 merge 규칙)
    seed = {"BAMLH0A0HYM2": [{"date": d, "value": 999.0}], "BAMLC0A0CM": []}
    seed_path = _write_seed(tmp_path / "seed.json", seed)
    store.load_seed(seed_path)

    hist = {r["date"]: r["value"] for r in store.get_history("BAMLH0A0HYM2")}
    assert hist[d] == 111.0


def test_load_seed_missing_file_raises_file_not_found(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        store.load_seed(missing)


def test_load_seed_empty_series_skipped_no_crash(tmp_path):
    seed = {"BAMLH0A0HYM2": [], "BAMLC0A0CM": []}
    seed_path = _write_seed(tmp_path / "seed.json", seed)
    stats = store.load_seed(seed_path)
    assert isinstance(stats, dict)
    for series_id in ("BAMLH0A0HYM2", "BAMLC0A0CM"):
        assert len(store.get_history(series_id)) == 0


# ── 동봉 실데이터 seed (data/oas_history_seed.json, SEED_PATH_DEFAULT) ──
# 부서장 지시: refactor-engineer가 운영 cache.db에서 추출한 실데이터로 교체 중.
# BAMLH0A0HYM2 881행 (2023-05-09 ~ 2026-09-16) / BAMLC0A0CM 880행.
# 자리표시(빈 리스트) 상태에서는 아래가 FAIL(RED)이 정상.

def test_load_default_bundled_seed_hy_oas_row_count_and_range():
    stats = store.load_seed()  # path 인자 없음 -> SEED_PATH_DEFAULT 사용
    assert "BAMLH0A0HYM2" in stats

    hy = store.slice_history("BAMLH0A0HYM2", 10)
    assert len(hy) == 881
    assert hy[0]["date"] == "2023-05-09"
    assert hy[-1]["date"] == "2026-09-16"


def test_load_default_bundled_seed_ig_oas_row_count():
    store.load_seed()
    ig = store.slice_history("BAMLC0A0CM", 10)
    assert len(ig) == 880


def test_load_default_bundled_seed_is_idempotent():
    stats_first = store.load_seed()
    total_first_hy = stats_first["BAMLH0A0HYM2"]["total"]
    slice_first_hy = len(store.slice_history("BAMLH0A0HYM2", 10))
    slice_first_ig = len(store.slice_history("BAMLC0A0CM", 10))

    stats_second = store.load_seed()
    total_second_hy = stats_second["BAMLH0A0HYM2"]["total"]
    slice_second_hy = len(store.slice_history("BAMLH0A0HYM2", 10))
    slice_second_ig = len(store.slice_history("BAMLC0A0CM", 10))

    assert total_first_hy == total_second_hy == 881
    assert slice_first_hy == slice_second_hy == 881
    assert slice_first_ig == slice_second_ig == 880


# ── CLI 엔트리: python -m macro_lite.seed --path <tmp> ─────────────

def test_seed_cli_entrypoint_exit_zero_and_reports_series(tmp_path):
    backend_dir = Path(__file__).resolve().parent.parent
    dates = _recent_dates(3, start_days_ago=60)
    seed = {"BAMLH0A0HYM2": [{"date": d, "value": 2.0} for d in dates], "BAMLC0A0CM": []}
    seed_path = _write_seed(tmp_path / "cli_seed.json", seed)

    cache_dir = tmp_path / "cli_cache"
    env = dict(os.environ)
    env["MACRO_LITE_CACHE_DIR"] = str(cache_dir)

    result = subprocess.run(
        [sys.executable, "-m", "macro_lite.seed", "--path", str(seed_path)],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "BAMLH0A0HYM2" in result.stdout


# ── 앱 기동/모듈 import 시 자동 적재 금지 ───────────────────────────

def test_importing_router_and_service_does_not_autoload_seed(tmp_path):
    """router/service 모듈 import만으로는 seed가 적재되지 않는다.

    별도 서브프로세스로 검증 (import는 프로세스당 1회만 실행되므로 신뢰성 확보).
    """
    backend_dir = Path(__file__).resolve().parent.parent
    cache_dir = tmp_path / "import_only_cache"
    env = dict(os.environ)
    env["MACRO_LITE_CACHE_DIR"] = str(cache_dir)

    code = (
        "import macro_lite.router\n"
        "import macro_lite.service\n"
        "from macro_lite import cache as cache_mod\n"
        "conn = cache_mod._conn()\n"
        "row = conn.execute(\n"
        "    \"SELECT COUNT(*) FROM cache WHERE key LIKE 'macro:oas_history_persist:%'\"\n"
        ").fetchone()\n"
        "conn.close()\n"
        "print('COUNT=%d' % row[0])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(backend_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "COUNT=0" in result.stdout
