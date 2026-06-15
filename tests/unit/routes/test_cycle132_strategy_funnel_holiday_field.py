"""사이클 132 (2026-06-15) — strategy_funnel 휴장일 UI 안내 응답 schema 격리 가드.

사용자 결정 영속:
- Q3=A 휴장일 UI 안내 추가
- Q4=A TDD 사이클 (Red → Green → verify)

배경:
- 휴장일 (주말/공휴일) 영역에서 운영자가 UI 접속 시 "오늘 데이터 미수신" 영구 영속 오인 차단 의무
- KIS `chk-holiday` API (CTCA0903R) `is_market_open(date)` 영구 영속 (사이클 17 영속) 재사용
- 응답 schema 확장 = `is_business_day: bool` + `holiday_note: str | None`

영속 의무:
- 사이클 17 chk-holiday 영속 (재사용 의무, 신규 KIS 호출 0건)
- 사이클 38 명문화 (라우트 영역 한정 + 매도/익일청산 hot path 무관)
- 사이클 84 L-2 GET 한정 (영향 0 = 화이트리스트 영향 0)
- 사이클 88 G-REJECT graceful (휴장일 조회 실패 graceful 통과)
- 사이클 89 한글 친숙 용어 (holiday_note 메시지 한글)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.routes import strategy_funnel as routes_sf


# =============================================================================
# G-132-D — 응답 schema 영구 영속 확장 (is_business_day + holiday_note)
# =============================================================================


class TestStrategyFunnelHolidayFieldPersistence:
    """GET /api/strategy-funnel 응답 schema 영구 영속 확장 영역."""

    @pytest.mark.asyncio
    async def test_g_132_d1_response_has_is_business_day_field(self):
        """G-132-D1 — 응답 data 영역에 is_business_day: bool 영구 영속.

        Q3=A 휴장일 UI 안내 추가 영속 의무.
        영업일 (True) 또는 휴장일 (False) 영구 영속 분기 의무.
        """
        # is_market_open mock = 영업일 분기
        with patch("src.routes.strategy_funnel.is_market_open", new=AsyncMock(return_value=True)):
            with patch(
                "src.routes.strategy_funnel.list_snapshots",
                new=AsyncMock(return_value=[]),
            ):
                resp = await routes_sf.get_funnel(target_date=None, strategy_id=None)

        # 응답 schema 영구 영속 확장 의무
        assert "is_business_day" in resp.data, (
            "GET /api/strategy-funnel 응답 data 영역 영구 영속 위반 — "
            "`is_business_day` 필드 부재. 사이클 132 Q3=A 영속 의무."
        )
        assert isinstance(resp.data["is_business_day"], bool), (
            f"is_business_day 영역 타입 영구 영속 위반 — "
            f"got type={type(resp.data['is_business_day']).__name__}, expected bool"
        )
        # 영업일 mock 시 True 영속 의무
        assert resp.data["is_business_day"] is True, (
            f"영업일 mock 시 is_business_day=True 영속 의무 — got {resp.data['is_business_day']}"
        )

    @pytest.mark.asyncio
    async def test_g_132_d2_response_has_holiday_note_field(self):
        """G-132-D2 — 응답 data 영역에 holiday_note: str | None 영구 영속.

        영업일 → None / 휴장일 → 한글 안내 메시지 영속.
        """
        # is_market_open mock = 영업일 분기 (holiday_note=None 의무)
        with patch("src.routes.strategy_funnel.is_market_open", new=AsyncMock(return_value=True)):
            with patch(
                "src.routes.strategy_funnel.list_snapshots",
                new=AsyncMock(return_value=[]),
            ):
                resp = await routes_sf.get_funnel(target_date=None, strategy_id=None)

        assert "holiday_note" in resp.data, (
            "GET /api/strategy-funnel 응답 data 영역 영구 영속 위반 — "
            "`holiday_note` 필드 부재. 사이클 132 Q3=A 영속 의무."
        )
        # 영업일 mock 시 None 영속 의무
        assert resp.data["holiday_note"] is None, (
            f"영업일 mock 시 holiday_note=None 영속 의무 — got {resp.data['holiday_note']!r}"
        )

    @pytest.mark.asyncio
    async def test_g_132_d3_holiday_note_korean_on_holiday(self):
        """G-132-D3 — 휴장일 분기 시 holiday_note 한글 안내 메시지 영속.

        사이클 89 한글 친숙 용어 영속.
        """
        with patch("src.routes.strategy_funnel.is_market_open", new=AsyncMock(return_value=False)):
            with patch(
                "src.routes.strategy_funnel.list_snapshots",
                new=AsyncMock(return_value=[]),
            ):
                resp = await routes_sf.get_funnel(target_date=None, strategy_id=None)

        assert resp.data["is_business_day"] is False, (
            f"휴장일 mock 시 is_business_day=False 영속 의무 — got {resp.data['is_business_day']}"
        )
        # 휴장일 시 holiday_note 한글 메시지 영속 의무
        assert resp.data["holiday_note"] is not None, (
            "휴장일 시 holiday_note 영역 영속 위반 — None 영구 영속 위반"
        )
        note = resp.data["holiday_note"]
        assert isinstance(note, str) and len(note) > 0, (
            f"holiday_note 영역 타입 + 비어있지 않음 영속 의무 — got {note!r}"
        )
        # 한글 키워드 영속 의무 (사이클 89 한글 친숙 용어 영속)
        assert "휴장" in note or "휴일" in note, (
            f"holiday_note 한글 키워드 영속 위반 — got {note!r}. "
            "사이클 89 한글 친숙 용어 영속 의무."
        )

    @pytest.mark.asyncio
    async def test_g_132_d4_graceful_when_is_market_open_fails(self):
        """G-132-D4 — is_market_open 호출 실패 시 graceful 통과 영속 (사이클 88 G-REJECT 답습).

        영업일 가정 (is_business_day=True) + holiday_note=None graceful 영속 의무.
        """
        with patch(
            "src.routes.strategy_funnel.is_market_open",
            new=AsyncMock(side_effect=Exception("KIS chk-holiday timeout")),
        ):
            with patch(
                "src.routes.strategy_funnel.list_snapshots",
                new=AsyncMock(return_value=[]),
            ):
                resp = await routes_sf.get_funnel(target_date=None, strategy_id=None)

        # graceful 통과 영속 의무 (영업일 가정)
        assert resp.success is True, (
            "is_market_open 실패 시 graceful 통과 영속 위반 — success=False"
        )
        assert resp.data["is_business_day"] is True, (
            f"graceful 영업일 가정 영속 위반 — got {resp.data['is_business_day']}"
        )
        assert resp.data["holiday_note"] is None, (
            f"graceful 영업일 가정 시 holiday_note=None 영속 의무 — got {resp.data['holiday_note']!r}"
        )

    @pytest.mark.asyncio
    async def test_g_132_d5_existing_response_keys_preserved(self):
        """G-132-D5 — 기존 응답 키 (target_date / strategy_id / snapshots) 영구 영속 보존.

        사이클 34 영속 영속 응답 schema 보존 의무 = 행위 보존.
        """
        with patch("src.routes.strategy_funnel.is_market_open", new=AsyncMock(return_value=True)):
            with patch(
                "src.routes.strategy_funnel.list_snapshots",
                new=AsyncMock(return_value=[]),
            ):
                resp = await routes_sf.get_funnel(target_date="2026-06-15", strategy_id="momentum")

        # 기존 응답 키 영속 의무 (사이클 34 영속)
        assert "target_date" in resp.data
        assert resp.data["target_date"] == "2026-06-15"
        assert "strategy_id" in resp.data
        assert resp.data["strategy_id"] == "momentum"
        assert "snapshots" in resp.data
        assert isinstance(resp.data["snapshots"], list)
