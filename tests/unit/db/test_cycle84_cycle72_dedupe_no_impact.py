"""사이클 84 Red — L-4 (LOW): 사이클 72 dedupe 영역 무영향 가드.

사이클 72 `_DbLogHandler` 500ms TTL dedupe 캐시 (`src/main.py`) 영속 — `system_logs` 이중
INSERT 영구 차단.

사이클 84 trigger (`stock_master_history_trigger`) = DB 레벨 PostgreSQL trigger
(application 코드 무관 + `_DbLogHandler` 경로 무관) = 영속 영향 0 검증.

본 가드 = `src/db/stock_master.py` 와 `src/routes/stock_master.py` 가 `write_log` 또는
`_insert_log_to_db` 직접 호출 0건 정적 검증 (사이클 72 옵션 A' 패턴 영속).

위험 등급 LOW (영구 정적 가드 — 사이클 72 silent 결함 차단 패턴 영속).
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


def test_L4_no_direct_write_log_call_in_stock_master_modules():
    """L-4: 사이클 84 신규 모듈 (db/stock_master.py + routes/stock_master.py) 에 `write_log` /
    `_insert_log_to_db` 직접 호출 0건 — 사이클 72 dedupe 영속 영향 무관 보장.
    """
    hits = []
    for target in TARGETS:
        if not target.exists():
            # 라우트 파일은 Green 단계 신규 작성 영역 — 미존재 시 skip
            continue
        text = target.read_text(encoding="utf-8")
        if "write_log(" in text:
            hits.append(f"{target.relative_to(ROOT)}: `write_log(` 호출 (사이클 72 영속 위반)")
        if "_insert_log_to_db(" in text:
            hits.append(f"{target.relative_to(ROOT)}: `_insert_log_to_db(` 직접 호출")

    assert not hits, (
        "사이클 72 dedupe 영속 영향 결함 — `write_log` / `_insert_log_to_db` 직접 호출 검출:\n"
        + "\n".join(hits)
        + "\n→ 사이클 84 변경기록 = trigger 단일 진입점 (Q8=A) 의무. logger.info() 위임만 허용."
    )
