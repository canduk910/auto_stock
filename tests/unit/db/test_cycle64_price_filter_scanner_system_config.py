"""사이클 64 (2026-06-06) Red — A 카테고리: `src/db/system_config.py` 가격 필터 단순화 (4 케이스).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§A)
> **설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` §1.1~1.3
> **자문 응답**: `_workspace/cycle64_price_filter_scanner_domain_response.md` (Q4 옵션 A — mode 폐기)
> **선례**: 사이클 62 A 5 케이스 → mode 제거 후 4 케이스로 단순화

요구 행위 (Red 단계 모두 AssertionError / TypeError 정답):

- A-1: `get_price_filter()` 가 PriceFilter(min=0, max=0) 만 반환 (mode 필드 없음)
- A-2: `set_price_filter(min_price=, max_price=)` 부분 갱신 — mode 인자 자체 제거
- A-3: 범위 외 입력 ValueError (음수 / max<min) — mode 검증 분기 폐기
- A-4: `set_price_filter(mode=...)` 호출 시 TypeError (mode 인자 자체 제거 — 호환성 차단)

회귀 가드:
- A-1/A-2 = PriceFilter 모델 단순화 (사이클 62 mode 필드 폐기)
- A-3 = 양수 검증 보존
- A-4 = mode 인자 호환성 차단 (오용 방지)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# A-1: get_price_filter() 디폴트 — mode 필드 부재
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A1_get_price_filter_default_no_mode_field(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-1: 키 부재 시 PriceFilter(min=0, max=0) — mode 필드 자체가 없어야 함.

    사이클 64 — mode 폐기 (Q4 옵션 A 자문 확정).
    `PriceFilter` Pydantic 모델 에 mode 필드 존재 시 결함 (사이클 62 잔재).
    """
    from src.db import system_config
    from src.db.system_config import PriceFilter, get_price_filter

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    pf = await get_price_filter()
    assert isinstance(pf, PriceFilter)
    assert pf.min_price == 0
    assert pf.max_price == 0
    # mode 필드 자체 폐기 (사이클 64 핵심) — model_fields 에서 키 부재 확인
    assert "mode" not in PriceFilter.model_fields, (
        "사이클 64 mode 필드 폐기 위반 — PriceFilter.model_fields 에 'mode' 잔존"
    )
    # is_active 분기 — 0/0 이면 비활성
    assert pf.is_active is False


# ---------------------------------------------------------------------------
# A-2: 부분 갱신 — mode 인자 없이 min/max 만
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A2_set_price_filter_partial_update_no_mode(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-2: `set_price_filter(min_price=)` / `set_price_filter(max_price=)` 부분 갱신.

    사이클 62 의 mode 인자 폐기. min/max 만 입력 + 보존 검증.
    """
    from src.db import system_config
    from src.db.system_config import get_price_filter, set_price_filter

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    # 1단계: min/max 둘 다 세팅 (mode 인자 없음)
    await set_price_filter(min_price=5000, max_price=1_000_000)
    pf = await get_price_filter()
    assert pf.min_price == 5000
    assert pf.max_price == 1_000_000

    # 2단계: min 만 갱신 → max 보존
    await set_price_filter(min_price=10_000)
    pf2 = await get_price_filter()
    assert pf2.min_price == 10_000
    assert pf2.max_price == 1_000_000, "max_price 보존 실패 — 부분 갱신 결함"

    # 3단계: max 만 갱신 → min 보존
    await set_price_filter(max_price=500_000)
    pf3 = await get_price_filter()
    assert pf3.min_price == 10_000
    assert pf3.max_price == 500_000


# ---------------------------------------------------------------------------
# A-3: 범위 외 입력 ValueError (음수 / max<min)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A3_set_price_filter_invalid_raises(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-3: 음수 / max<min → ValueError.

    mode 검증 분기 폐기 (사이클 64). 양수 검증 + max<min 검증만 보존.
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

    # max < min (둘 다 명시 + 둘 다 > 0)
    with pytest.raises(ValueError):
        await set_price_filter(min_price=10_000, max_price=5_000)


# ---------------------------------------------------------------------------
# A-4: mode 인자 자체 제거 — 호환성 차단 (오용 방지)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A4_set_price_filter_mode_argument_rejected(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-4: `set_price_filter(mode=...)` 호출 시 TypeError.

    사이클 64 단순화 — mode 인자 자체 폐기. 사이클 62 코드 잔재 시 결함.
    `import inspect` 로 시그니처 검증 + 실제 호출 시 TypeError 양쪽 검증.
    """
    import inspect

    from src.db import system_config
    from src.db.system_config import set_price_filter

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    # 1) 시그니처 정적 검증 — `mode` 매개변수 부재
    sig = inspect.signature(set_price_filter)
    params = list(sig.parameters.keys())
    assert "mode" not in params, (
        f"사이클 64 mode 인자 폐기 위반 — set_price_filter 시그니처에 'mode' 잔존: {params}"
    )

    # 2) 실제 호출 — TypeError (unexpected keyword argument 'mode')
    with pytest.raises(TypeError):
        await set_price_filter(mode="HARD")  # type: ignore[call-arg]
