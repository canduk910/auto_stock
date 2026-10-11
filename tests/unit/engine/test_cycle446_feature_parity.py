"""cycle446 — `llm_worker/lw/features.py` 는 `src/engine/llm_features.py` 에서 **복사**한
지표 함수다(설계 §4.1 — 공용 패키지로 빼면 backend Dockerfile COPY 가 바뀌어 full 배포가
된다). 이 테스트가 드리프트 덫이다 — 같은 고정 입력에 두 구현을 넣어 값이 같은지 대조한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LLM_WORKER = _REPO_ROOT / "llm_worker"


def _import_worker_features():
    if str(_LLM_WORKER) not in sys.path:
        sys.path.insert(0, str(_LLM_WORKER))
    import importlib

    # lw 패키지가 이미 다른 경로로 import 돼 있으면(병렬 테스트) 캐시를 지운다.
    sys.modules.pop("lw", None)
    sys.modules.pop("lw.features", None)
    return importlib.import_module("lw.features")


_BARS_DESC = [
    {"stck_oprc": 1000 + i, "stck_hgpr": 1020 + i, "stck_lwpr": 990 + i,
     "stck_clpr": 1010 + i, "acml_vol": 10000 + i * 10}
    for i in range(60, 0, -1)  # desc: 최근(1) → 오래됨(60)
]


@pytest.mark.parametrize("fn_name,args,kwargs", [
    ("ema", ([1.0, 2.0, 3.0, 4.0, 5.0], 3), {}),
    ("rsi_wilder", ([float(x) for x in range(10, 40)],), {"period": 14}),
    ("atr_wilder", (list(range(10, 40)), list(range(5, 35)), list(range(8, 38))), {"period": 14}),
    ("hv_annualized", ([100.0 + (i % 5) for i in range(30)],), {"period": 20}),
    ("channel", (list(range(1, 30)), list(range(0, 29))), {"period": 20}),
])
def test_indicator_functions_match_backend(fn_name, args, kwargs):
    from src.engine import llm_features as backend

    worker = _import_worker_features()
    backend_fn = getattr(backend, fn_name)
    worker_fn = getattr(worker, fn_name)
    assert worker_fn(*args, **kwargs) == backend_fn(*args, **kwargs)


def test_macd_matches_backend():
    from src.engine import llm_features as backend

    worker = _import_worker_features()
    closes = [100.0 + (i * 0.7) + (i % 3) for i in range(40)]
    assert worker.macd(closes) == backend.macd(closes)


def test_compute_technicals_matches_backend_for_fixed_bars():
    from src.engine import llm_features as backend

    worker = _import_worker_features()
    got_backend = backend.compute_technicals(_BARS_DESC, current_price=1005)
    got_worker = worker.compute_technicals(_BARS_DESC, current_price=1005)
    assert got_worker == got_backend


def test_compute_technicals_key_set_matches_backend_for_feature_version():
    """`lw/exit_shadow._feature_version()` 와 backend `llm_buy_gate._feature_version()` 가
    같은 입력에서 같은 키 집합을 내는지 — 둘이 다르면 버전 축이 의미를 잃는다."""
    from src.engine import llm_features as backend

    worker = _import_worker_features()
    keys_backend = sorted(backend.compute_technicals([], current_price=0).keys())
    keys_worker = sorted(worker.compute_technicals([], current_price=0).keys())
    assert keys_worker == keys_backend
