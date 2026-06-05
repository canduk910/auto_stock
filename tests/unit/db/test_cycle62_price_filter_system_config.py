"""사이클 62 (2026-06-05) Red — A 카테고리: `src/db/system_config.py` 가격 필터 헬퍼 (5 케이스).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§A)
> **설계 카드**: `_workspace/cycle62_price_filter_design_card.md` §1.1/§1.2 (자문 옵션 A 채택)
> **선례**: `tests/unit/db/test_system_config_buy_block.py` (사이클 8 4 모드) 답습

요구 행위 (Red 단계 모두 ImportError / AttributeError 정답):

A-1: `get_price_filter()` 키 부재 시 기본 PriceFilter(min=0, max=0, mode="OFF") 반환
A-2: `set_price_filter(min_price=, max_price=, mode=)` 부분 갱신 (None 인 키는 보존)
A-3: 범위 외 입력 ValueError (음수 / max<min / 잘못된 mode)
A-4: 60s TTL 캐시 (cash_usage_ratio 패턴 답습) — *system_config 헬퍼 자체에는 캐시 없음*,
     이 케이스는 round-trip 동작 검증 (값 저장 후 재조회 일치)
A-5: invalidate 후 즉시 반영 — 부분 갱신 직후 재조회 시 새 값 반영

Q1 자문 확정: 디폴트 0/0 (비활성) + 권장값은 UI 툴팁만 (백엔드 DB 디폴트 아님)
Q4 자문 확정: 3 모드 (HARD/WARN/OFF) + 디폴트 OFF
Q5 자문 확정: invalidate 즉시 반영 (60s TTL 캐시는 RiskManager 영역, system_config 는 단순 round-trip)

회귀 가드: cash_usage_ratio (0.0~1.0) / buy_block_mode (4 모드) 패턴 답습 — DB 헬퍼 추가에
기존 5 키 영향 0.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# A-1: 기본값 — mode=OFF / min=0 / max=0 (비활성)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A1_get_price_filter_default_off(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-1: 키 부재 시 기본 PriceFilter(min=0, max=0, mode='OFF') 반환.

    Q1 + Q4 자문 확정 — 디폴트 비활성 (운영 시작 안전성 우선).
    """
    from src.db import system_config  # Red: 정상 import
    from src.db.system_config import PriceFilter, get_price_filter  # Red: AttributeError

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    pf = await get_price_filter()
    assert isinstance(pf, PriceFilter)
    assert pf.min_price == 0
    assert pf.max_price == 0
    assert pf.mode == "OFF"
    assert pf.is_active is False  # OFF + 0/0 → 비활성


# ---------------------------------------------------------------------------
# A-2: 부분 갱신 — None 인 키는 보존
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A2_set_price_filter_partial_update(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-2: `set_price_filter(min_price=)` 만 호출 시 max/mode 는 보존.

    `set_buy_block_thresholds` 부분 갱신 패턴 답습.
    """
    from src.db import system_config
    from src.db.system_config import get_price_filter, set_price_filter

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    # 1단계: 모두 세팅 (HARD + 5000 + 1_000_000)
    await set_price_filter(min_price=5000, max_price=1_000_000, mode="HARD")
    pf = await get_price_filter()
    assert pf.min_price == 5000
    assert pf.max_price == 1_000_000
    assert pf.mode == "HARD"

    # 2단계: min_price 만 갱신 → max/mode 보존
    await set_price_filter(min_price=10_000)
    pf2 = await get_price_filter()
    assert pf2.min_price == 10_000
    assert pf2.max_price == 1_000_000, "max_price 보존 실패 — 부분 갱신 결함"
    assert pf2.mode == "HARD", "mode 보존 실패 — 부분 갱신 결함"

    # 3단계: mode 만 갱신
    await set_price_filter(mode="WARN")
    pf3 = await get_price_filter()
    assert pf3.min_price == 10_000
    assert pf3.max_price == 1_000_000
    assert pf3.mode == "WARN"


# ---------------------------------------------------------------------------
# A-3: 범위 외 입력 ValueError (음수 / max<min / 잘못된 mode)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A3_set_price_filter_invalid_raises(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-3: 음수 / max<min / 잘못된 mode → ValueError.

    Q1 슬라이더 bound 검증 + Q4 3 모드 검증.
    """
    from src.db import system_config
    from src.db.system_config import set_price_filter

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    # 음수 min
    with pytest.raises(ValueError):
        await set_price_filter(min_price=-1)

    # 음수 max
    with pytest.raises(ValueError):
        await set_price_filter(max_price=-100)

    # max < min (둘 다 명시)
    with pytest.raises(ValueError):
        await set_price_filter(min_price=10_000, max_price=5_000)

    # 잘못된 mode (소문자 / 알 수 없는 / 빈 문자열)
    for bad_mode in ["hard", "SOFT", "INVALID", "", None]:
        with pytest.raises((ValueError, TypeError)):
            await set_price_filter(mode=bad_mode)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# A-4: 저장 후 즉시 재조회 일치 (round-trip)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A4_set_price_filter_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-4: 3 모드 + 다양한 min/max 조합 round-trip 일치.

    JSONB 직렬화/역직렬화 + int 보존 검증.
    """
    from src.db import system_config
    from src.db.system_config import get_price_filter, set_price_filter

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    for mode in ["HARD", "WARN", "OFF"]:
        for min_price, max_price in [(0, 0), (5000, 1_000_000), (10_000, 500_000)]:
            await set_price_filter(min_price=min_price, max_price=max_price, mode=mode)
            pf = await get_price_filter()
            assert pf.min_price == min_price, f"round-trip 결함: mode={mode}, min={min_price}"
            assert pf.max_price == max_price
            assert pf.mode == mode


# ---------------------------------------------------------------------------
# A-5: PriceFilter.is_active 분기 (OFF / HARD 0/0 / HARD 활성 / WARN 활성)
# ---------------------------------------------------------------------------
def test_A5_price_filter_is_active_property():
    """A-5: `is_active` property — OFF 또는 0/0 이면 False, HARD/WARN + 값 > 0 면 True.

    risk.on_tick 의 분기 진입 결정에 사용 — 비활성이면 가드 평가 자체 skip (성능 보호).
    """
    from src.db.system_config import PriceFilter

    # OFF 모드 — 임계값 무관 비활성
    assert PriceFilter(min_price=0, max_price=0, mode="OFF").is_active is False
    assert PriceFilter(min_price=5000, max_price=1_000_000, mode="OFF").is_active is False

    # HARD + 0/0 — 비활성 (둘 다 0 = 임계 부재)
    assert PriceFilter(min_price=0, max_price=0, mode="HARD").is_active is False

    # HARD + min 만 활성
    assert PriceFilter(min_price=5000, max_price=0, mode="HARD").is_active is True

    # HARD + max 만 활성
    assert PriceFilter(min_price=0, max_price=1_000_000, mode="HARD").is_active is True

    # WARN + 둘 다 활성
    assert PriceFilter(min_price=5000, max_price=1_000_000, mode="WARN").is_active is True
