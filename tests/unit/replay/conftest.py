"""replay(오프라인 연구) 테스트 공통 설정.

- 30년 보관소(`data/archive/krx_daily_long/`)는 git 밖이라 CI 에 없다 — 그 파일을 직접 읽는 테스트는 파일이 없으면 건너뛴다.
- CI 의 numpy 가 pandas 내부(timedeltas.pyx)에서 내는 「generic timedelta 단위」 사용 중단 경고는 연구 코드 결함이 아니므로
  이 폴더에서만 무시한다(`filterwarnings = error` 전역 설정은 그대로).
"""
from __future__ import annotations

import os

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ARCHIVE_META = os.path.join(_REPO, "data", "archive", "krx_daily_long", "meta")

# 보관소 meta 파일을 직접 읽는 테스트(파일 없으면 건너뜀)
_NEEDS_ARCHIVE = {
    "test_y30_bfb.py::test_rows_use_era_cost_by_entry_and_exit_day",
    "test_y30_vb.py::test_cost_and_limit_tables",
    "test_y30_vcp.py::test_limit_table_dates",
    "test_y30_vcp.py::test_era_cost_main_and_const",
}

_NUMPY_GENERIC_TD = (
    "ignore:The 'generic' unit for NumPy timedelta is deprecated:DeprecationWarning"
)


def pytest_collection_modifyitems(config, items):
    here = os.path.dirname(os.path.abspath(__file__))
    archive_missing = not os.path.isdir(_ARCHIVE_META)
    for item in items:
        if not str(item.fspath).startswith(here):
            continue
        item.add_marker(pytest.mark.filterwarnings(_NUMPY_GENERIC_TD))
        key = f"{os.path.basename(str(item.fspath))}::{item.name}"
        if archive_missing and key in _NEEDS_ARCHIVE:
            item.add_marker(pytest.mark.skip(reason="30년 보관소(git 밖) 없음 — CI 에서는 건너뜀"))
