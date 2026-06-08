"""사이클 84 Red — L-5 (LOW): 사이클 32 R4 universe guard 무영향 검증.

사이클 32 R4 `_evaluate_universe_guard` (`src/engine/stale_universe_guard.py` 사이클 67 분해
영속) = stale + 보유/익일청산 절대 보호 영속.

사이클 84 = READ-ONLY GET 5 라우트 + DB trigger = `_evaluate_universe_guard` 호출 사이트 변경 0
+ `_universe_excluded_today` set 영향 0 검증.

본 가드 = `src/routes/stock_master.py` (신규) + `src/db/stock_master.py` (헬퍼 4종 추가) 가
`_universe_excluded_today` / `_evaluate_universe_guard` 참조 0건 정적 검증.

위험 등급 LOW (영구 정적 가드 — 사이클 32 R4 영속 보장).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
TARGETS = [
    ROOT / "src" / "db" / "stock_master.py",
    ROOT / "src" / "routes" / "stock_master.py",
]

FORBIDDEN_REFS = [
    "_universe_excluded_today",
    "_evaluate_universe_guard",
    "stale_universe_guard",
]


def test_L5_no_universe_guard_reference_in_stock_master_modules():
    """L-5: 사이클 84 신규 모듈에 사이클 32 R4 universe guard 참조 0건.

    READ-ONLY GET 영역 한정 = universe guard hot path 영향 0 보장.
    """
    hits = []
    for target in TARGETS:
        if not target.exists():
            # 라우트 파일 Green 단계 신규 — 미존재 skip
            continue
        text = target.read_text(encoding="utf-8")
        for ref in FORBIDDEN_REFS:
            if ref in text:
                hits.append(f"{target.relative_to(ROOT)}: `{ref}` 참조 검출")

    assert not hits, (
        "사이클 32 R4 universe guard 무영향 결함 — 참조 검출:\n"
        + "\n".join(hits)
        + "\n→ 사이클 84 = READ-ONLY GET + trigger 영역 = universe guard hot path 무관 의무."
    )
