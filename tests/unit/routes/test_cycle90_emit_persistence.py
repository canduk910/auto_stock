"""사이클 90 L-3 (LOW) — Q27=A [stock_master_bulk_refresh] 영속 활용.

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

사용자 결정 Q27=A: 사이클 89 영속 prefix `[stock_master_bulk_refresh]` 활용
(자동/수동 구분 0). 신규 prefix 도입 0건 (사이클 78 silent 결함 영역 추가 위험 차단).

기대 동작 (Green, 사이클 90):
- POST refresh-universe 호출 시 사이클 89 fetch_top_500_universe 의 emit 영역 그대로 발화
- 사이클 90 신규 prefix (`[refresh_universe_manual]` 등) 도입 0건
- `src/routes/stock_master.py` 본문에 logger.* 발화 0건 (fetch 함수 내부 emit 만 활용)

Red 상태: production 코드 0 → 404.

위험 등급 LOW (사이클 78 silent 결함 영역 추가 위험 차단).

영속 의무:
- 사이클 89 [stock_master_bulk_refresh] 영속 영역 변경 0
- 사이클 78 silent 결함 차단 영속 (신규 prefix 도입 dup 위험 영구 차단)
- 사이클 72/73/74 dup_factor 1.0 영속 (양쪽 emit 차단)
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_ROUTE_PY = _SRC_ROOT / "routes" / "stock_master.py"


def test_l3_no_new_prefix_introduced_in_route():
    """L-3: stock_master 라우트 본문에 신규 emit prefix 도입 0건.

    사이클 90 시정 영역에서 새 prefix (`[refresh_universe_manual]` 등) 도입 차단.
    사이클 89 영속 prefix 만 활용 (Q27=A 자동/수동 구분 0).
    """
    assert _ROUTE_PY.exists(), f"라우트 파일 부재: {_ROUTE_PY}"
    source = _ROUTE_PY.read_text(encoding="utf-8")

    # 사이클 90 신규 prefix 차단 매트릭스
    forbidden_prefixes = [
        "[refresh_universe_manual]",
        "[refresh_universe_now]",
        "[stock_master_manual_refresh]",
        "[manual_refresh_universe]",
    ]
    for prefix in forbidden_prefixes:
        assert prefix not in source, (
            f"라우트 본문에 신규 emit prefix `{prefix}` 도입 검출 — "
            f"Q27=A 영속 위반 (사이클 89 [stock_master_bulk_refresh] 영속 활용 의무). "
            f"사이클 72/73/74 dup_factor 1.0 영속 영역 영향 가능."
        )


def test_l3_route_does_not_emit_logger_directly():
    """L-3-bis: 라우트 본문에서 logger.* 직접 emit 0건.

    fetch_top_500_universe 내부 emit 만 활용 (사이클 89 영속). 라우트 본문에
    logger.info/warning/error 호출 0건 의무. 사이클 78 답습 (collector 영역 분리).
    """
    assert _ROUTE_PY.exists()
    source = _ROUTE_PY.read_text(encoding="utf-8")

    # logger.* 직접 호출 패턴 검출 — refresh-universe 영역 한정
    # 라우트 함수 본문 안에 `logger.info(` / `logger.warning(` / `logger.error(` 검출 0건
    import re

    # `refresh_universe_now` 함수 영역만 추출 (사이클 90 신규 영역)
    func_pattern = re.compile(
        r"async\s+def\s+refresh_universe_now\s*\(.*?\)(.*?)(?=\nasync\s+def|\Z)",
        re.DOTALL,
    )
    match = func_pattern.search(source)

    if match is not None:
        func_body = match.group(1)
        logger_calls = re.findall(r"logger\.(info|warning|error|debug)\s*\(", func_body)
        assert len(logger_calls) == 0, (
            f"refresh_universe_now 함수 본문에 logger.* 직접 호출 {len(logger_calls)}건 검출 "
            f"({logger_calls}) — Q27=A 영속 위반 (사이클 89 fetch 함수 내부 emit 만 활용 의무)"
        )
    # Red 단계: 함수 미존재 시 본 검증은 vacuous PASS (production 코드 0 상태)
    # Green 단계: 함수 존재 시 logger 호출 0건 의무
