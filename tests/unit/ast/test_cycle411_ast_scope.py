"""cycle411 Red — 범위 가드: 실비용 합치기는 **8영역·`scheduler.py` 무접촉** 이다 (내용 sha).

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` 「🔴 8영역 … 무접촉」.

| # | 계약 |
|---|---|
| G1 | 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`·`src/api/order.py`·`src/realtime/**`·`src/auth/**`) + `src/engine/scheduler.py` 의 `.py` 내용 sha = base `669170d5` 그대로 |
| G2 | 8영역 디렉터리에 새 `.py` 가 생기거나 사라지지 않는다(파일 집합 동일) |
| G3 | `allocate_rows` 일반화 뒤에도 기존 귀속 테스트 `test_trackc_trade_cost_calc.py` · TE 테스트 `test_cycleF_te_rr_metrics.py` 는 **무수정**이다(행위 보존을 테스트를 고쳐 맞추지 않는다) |

왜 내용 sha 인가 — `ast.dump` 는 3.12(CI)/3.13(로컬) 출력이 달라 핀하지 않는다(cycle256·259).
스캔은 `Path.rglob("*.py")` — `git ls-files` 는 미추적 새 파일을 못 본다(cycle259 S4b).

⚠️ **사이클 한정 — cycle411 머지 후 삭제.** 이 dict 는 base `669170d5` blob 이라 cycle411 의
무접촉 증거로만 유효하다. 다음 사이클이 이 파일들을 정당하게 바꾸면 이 테스트를 지운다(고아
가드 방지). dict 이름을 `*_CONTENT_SHA` 로 짓지 않는다(`test_cycle223g3` `_PIN_GUARD_FILES` 관례).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_BASE_SHA = {
    "src/engine/risk.py": "a2187b8270446379988d24dfbe39b902d6ab37b112d4b6ce7330ee171434e222",
    "src/engine/order_engine.py": "08c479841352fb579f767c109de3e8f901d1c27bdce705b39b5ba6556fc0b3e1",
    "src/engine/session.py": "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    "src/engine/scanner.py": "611568c078c6f3779344e05b3dfa308c792c64e1c5e02480de6313200282f54f",
    "src/engine/strategy_registry.py": "3b6366c3cdb6e83907428435b95611880f1b8223e572c361a1cad2d00b13a067",
    "src/api/order.py": "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    "src/engine/scheduler.py": "f53d41a11fe162f80e113c6ff48cf6d235581769be7979499c5782ff11d49646",
    "src/realtime/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py": "e1a484e9ac82d43f0fa85cba693ea5a206ecfbae1076dfee0f4e6bf6d4f2a2d4",
    "src/realtime/websocket.py": "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py": "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    "src/auth/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py": "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/auth/token.py": "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
}

_UNTOUCHED_TESTS = {
    "tests/unit/engine/test_trackc_trade_cost_calc.py":
        "f09d39a6c5381eecf9efc725e11818b142d7382eceaa45af53eec022911ee5b9",
    "tests/unit/engine/test_cycleF_te_rr_metrics.py":
        "4576f3efb702e00dc118e6fac4a89cfafbd7232707a48d255df85e73ef078799",
}


def _sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_g1_eight_areas_and_scheduler_unchanged(rel):
    assert _sha(rel) == _BASE_SHA[rel], f"{rel} 가 바뀌었다 — cycle411 은 8영역·scheduler.py 무접촉"


def test_g2_eight_area_dirs_have_no_new_py():
    found = {
        p.relative_to(_ROOT).as_posix()
        for d in ("src/realtime", "src/auth")
        for p in (_ROOT / d).rglob("*.py")
        if "__pycache__" not in p.parts
    }
    expected = {k for k in _BASE_SHA if k.startswith(("src/realtime/", "src/auth/"))}
    assert found == expected


@pytest.mark.parametrize("rel", sorted(_UNTOUCHED_TESTS))
def test_g3_behavior_preservation_tests_unmodified(rel):
    assert _sha(rel) == _UNTOUCHED_TESTS[rel], f"{rel} 를 고치지 말 것 — 행위 보존은 구현이 맞춘다"
