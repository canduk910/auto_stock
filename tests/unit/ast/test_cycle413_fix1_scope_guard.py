"""cycle413 보완 1차 Red — 범위 가드: #1(거래일지 세후 = 세전) 은 **라우트 순서만** 고친다.

판정 원문 = scratchpad `c413/fix/verdict1.md` #1 「문자열화를 `overlay_pairs` 호출 **뒤**로 옮긴다. `/pnl` 과 같은 순서이고,
`cost_overlay` 는 고치지 않는다」. `cost_overlay.py` 는 `/api/history/pnl`·`/api/costs/*`·`/api/performance/*` 가 함께 쓰는
비용 계산 정본이라, 일지 결함을 거기서 고치면(예: 키를 문자열로 바꾸기) 다른 화면의 숫자가 함께 움직인다.

| # | 계약 |
|---|---|
| X1 | `src/engine/cost_overlay.py` 내용 sha = 기준 `cf06540d`(cycle413 1차 HEAD) 그대로 |

왜 내용 sha 인가 — `ast.dump` 는 3.12(CI)/3.13(로컬) 출력이 달라 핀하지 않는다(cycle256·259).

⚠️ **사이클 한정 — cycle413 병합 후 삭제.** 이 sha 는 보완 1차의 무접촉 증거로만 유효하다. 다음 사이클이 정당하게
`cost_overlay.py` 를 바꾸면 지운다(고아 가드 방지). 상수 이름을 `*_CONTENT_SHA` 로 짓지 않는다(`test_cycle223g3`
`_PIN_GUARD_FILES` 관례).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_BASE_SHA_FIX1 = {
    "src/engine/cost_overlay.py": "413e116f03229e78a0781499800821518f8b29abf4976c818db644fe6a0f20b9",
}


@pytest.mark.parametrize("rel", sorted(_BASE_SHA_FIX1))
def test_x1_cost_overlay_untouched(rel):
    got = hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()
    assert got == _BASE_SHA_FIX1[rel], (
        f"{rel} 가 바뀌었다 — #1 은 `src/routes/history.py` 의 문자열화 순서만 고친다(판정 #1)")
