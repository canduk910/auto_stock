"""macro_lite 패키지 단독 pytest 공용 fixture.

캐시 격리: 테스트마다 `MACRO_LITE_CACHE_DIR`을 tmp_path로 monkeypatch해
실제 `~/macro-lite/cache.db`를 절대 건드리지 않는다. `macro_lite/cache.py`가
환경변수를 호출 시점에 읽으므로(_cache_dir()) 이 fixture만으로 격리가 성립한다.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_macro_lite_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MACRO_LITE_CACHE_DIR", str(tmp_path))
    yield
