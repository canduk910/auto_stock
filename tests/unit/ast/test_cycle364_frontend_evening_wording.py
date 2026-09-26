"""cycle364 S1 Red — 프론트 문구·MSW 가 저녁 캡처 시각(21:00)과 같은 말을 한다.

⚠️ **이 백엔드 테스트는 프론트 파일을 읽는다** (`frontend/src/components/KojiroMonitor.tsx` ·
`frontend/src/pages/StrategyFunnel.tsx` · `frontend/src/test/handlers.ts`). 프론트 전용 사이클의
검증 목록(`grep -rl 'frontend/' tests/unit`)에 이 파일이 걸린다 — 가드 설계 금기(2026-09-05) 준수.

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §1.4 · §2.6 「프론트」 · §6.1 S1.
- KojiroMonitor 「매일 저녁 16:20 스캔」 은 A1 뒤 거짓이다(16:20 재준비가 사라지고 21:00 에
  다음 거래일 미리보기가 돈다).
- StrategyFunnel 잠정 배지 툴팁 「16:20 저녁 잠정 캡처」 도 같다(잠정 배지는 이제 미래 날짜 행에만).
- MSW `market-ops` 목의 `evening_funnel_capture.scheduled_at` 은 백엔드
  `_hms(TIME_EVENING_FUNNEL_CAPTURE)` 와 같아야 한다(목이 백엔드 계약을 흉내 낸다).

새 문구 자체는 frontend-dev 몫이다 — 이 파일은 「옛 시각이 남지 않았다 · 새 시각을 말한다」만 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_UI_FILES = (
    _ROOT / "frontend" / "src" / "components" / "KojiroMonitor.tsx",
    _ROOT / "frontend" / "src" / "pages" / "StrategyFunnel.tsx",
)


@pytest.mark.parametrize("path", _UI_FILES, ids=lambda p: p.name)
def test_fe364_1_ui_copy_when_read_then_no_stale_1620_and_mentions_2100(path):
    text = path.read_text(encoding="utf-8")
    assert "16:20" not in text, f"{path.name}: 옛 저녁 캡처 시각 16:20 이 남았다 (A1 뒤 거짓)"
    assert "21:00" in text, f"{path.name}: 새 저녁 캡처 시각 21:00 을 말하지 않는다"


def test_fe364_2_msw_market_ops_when_mocked_then_evening_row_scheduled_at_matches_backend():
    from src.routes.market_ops import TIME_EVENING_FUNNEL_CAPTURE, _hms

    text = (_ROOT / "frontend" / "src" / "test" / "handlers.ts").read_text(encoding="utf-8")
    m = re.search(r'id:\s*"evening_funnel_capture",[\s\S]*?scheduled_at:\s*"([^"]+)"', text)
    assert m, "MSW 목에서 evening_funnel_capture 행을 못 찾았다"
    assert m.group(1) == _hms(TIME_EVENING_FUNNEL_CAPTURE), (
        f"MSW scheduled_at={m.group(1)!r} ≠ 백엔드 {_hms(TIME_EVENING_FUNNEL_CAPTURE)!r}"
    )
