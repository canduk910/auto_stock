"""cycle227 W3 (RED) — 신규 leaf 모듈 `src/engine/tick_volume.py`.

## 왜 별도 모듈인가

관측 누적거래량을 `scanner.ticker_prices` 에 넣으면 **donchian 매수 행위가 바뀐다** —
`donchian_swing` 이 같은 dict 에서 `daily_high = max(stck_hgpr, high_price, ...)` 를 읽어
`ext_pct` 과열 가드를 계산하기 때문이다(`risk.py` 주석 + 기존 AST 가드가 이미 경고).
그래서 값은 **전용 leaf 모듈**에만 산다.

## 설계 제약 (`_workspace/red/cycle227_acml_vol_stage0_spec.md` W3)

- **날짜 키 자기 리셋** — `_reset_daily_state` 훅에 의존하지 않는다.
  `scheduler.py` diff 0 이 이번 사이클의 설계 목표다(미커밋 cycle221 잔류와 커밋 분리).
  선례: `DailyEmitCap` 계열의 KST 날짜 자기리셋(`_max_sub_warn_date`).
- 외부 의존 최소 — DB/HTTP 없음, KST date 만. `portfolio_risk.py` 순수 모듈 선례.
- **미관측 sentinel 은 `None`. `0` 금지** — `0` 은 P0 결함의 그 값이다(자문 §5).
"""

from __future__ import annotations

import pytest
from freezegun import freeze_time

from src.engine import tick_volume

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolate():
    tick_volume.reset_for_test()
    yield
    tick_volume.reset_for_test()


# ===========================================================================
# W3-1 — 공개 API
# ===========================================================================

def test_module_exposes_three_public_functions():
    for name in ("record_acml_vol", "get_observed_acml_vol", "reset_for_test"):
        assert callable(getattr(tick_volume, name, None)), (
            f"`tick_volume.{name}` 부재 — W3 공개 API 계약 위반"
        )


# ===========================================================================
# W3-2 / W3-3 / W3-5 — 미관측 None · 왕복 항등 · 0 은 유효 관측
# ===========================================================================

def test_get_when_never_recorded_then_none():
    """W3-2 — 미관측은 `None`. **`0` 을 돌려주면 P0 결함을 그대로 이식하는 것이다.**"""
    got = tick_volume.get_observed_acml_vol("005930")
    assert got is None, (
        f"미관측 반환이 {got!r} 이다. `None` 이어야 한다 — `0` 을 돌려주면 "
        "'미수신'과 '거래량 0'이 다시 구별 불가가 되어 유령 키 결함이 부활한다"
    )


@freeze_time("2026-08-25 09:30:00")
def test_record_then_get_when_same_day_then_roundtrip():
    """W3-3 — record → get 왕복 항등."""
    tick_volume.record_acml_vol("005930", 1_234_567)
    assert tick_volume.get_observed_acml_vol("005930") == 1_234_567


@freeze_time("2026-08-25 09:30:00")
def test_record_zero_when_real_observation_then_returns_zero_not_none():
    """W3-5 — `0` 은 **유효한 관측**(거래가 아직 없는 종목)이다.

    미수신(`None`)과 타입 수준에서 갈라야 소비처가 두 사유를 다른 로그로 남길 수 있다.
    """
    tick_volume.record_acml_vol("005930", 0)
    assert tick_volume.get_observed_acml_vol("005930") == 0
    assert tick_volume.get_observed_acml_vol("005930") is not None


@freeze_time("2026-08-25 09:30:00")
def test_get_when_other_ticker_recorded_then_none():
    tick_volume.record_acml_vol("005930", 1_000)
    assert tick_volume.get_observed_acml_vol("000660") is None


# ===========================================================================
# W3-4 — 음수 무시 (기존 값 보존)
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
@pytest.mark.parametrize("neg", [-1, -999], ids=["sentinel", "large"])
def test_record_when_negative_then_ignored(neg):
    """W3-4 — 음수는 handler sentinel(`-1`) 이므로 기록하지 않는다."""
    tick_volume.record_acml_vol("005930", neg)
    assert tick_volume.get_observed_acml_vol("005930") is None


@freeze_time("2026-08-25 09:30:00")
def test_record_when_negative_after_valid_then_keeps_previous():
    """W3-4 — 음수가 **정상 관측을 덮어써서 지우면 안 된다**.

    WS 재연결 직후 짧은 payload 가 한 번 오면 그 종목 관측이 통째로 사라진다.
    """
    tick_volume.record_acml_vol("005930", 500_000)
    tick_volume.record_acml_vol("005930", -1)
    assert tick_volume.get_observed_acml_vol("005930") == 500_000


# ===========================================================================
# W3-6 — 마지막 기록 우선
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
def test_record_twice_when_same_day_then_last_write_wins():
    """W3-6 — 마지막 관측이 현재 상태다.

    ⚠️ `max()` 로 바꾸면 값의 의미가 "마지막 관측" → "당일 최대 관측" 으로 바뀐다.
    그건 Stage 0(행위 변경 0) 범위 밖 결정이라 명세 문구대로 last-write-wins 로 고정한다.
    """
    tick_volume.record_acml_vol("005930", 1_000)
    tick_volume.record_acml_vol("005930", 2_000)
    assert tick_volume.get_observed_acml_vol("005930") == 2_000


# ===========================================================================
# W3-7 / W3-8 / W3-9 — 날짜 키 자기 리셋 (KST)
# ===========================================================================

def test_get_when_date_rolled_then_none():
    """W3-7 — 저장 날짜 != 오늘이면 `None` (크로스데이 오염 차단).

    어제 관측이 오늘의 게이트/가드 판정에 쓰이면 조용히 틀린 결론을 낸다.
    """
    with freeze_time("2026-08-25 09:30:00"):
        tick_volume.record_acml_vol("005930", 1_234_567)
        assert tick_volume.get_observed_acml_vol("005930") == 1_234_567
    with freeze_time("2026-08-26 09:30:00"):
        assert tick_volume.get_observed_acml_vol("005930") is None


def test_record_when_date_rolled_then_clears_previous_day():
    """W3-8 — 날짜 전환 후 첫 record 가 이전 날짜 전체를 clear 한다 (무한 성장 차단)."""
    with freeze_time("2026-08-25 09:30:00"):
        tick_volume.record_acml_vol("005930", 111)
        tick_volume.record_acml_vol("000660", 222)
    with freeze_time("2026-08-26 09:30:00"):
        tick_volume.record_acml_vol("005930", 999)
        assert tick_volume.get_observed_acml_vol("005930") == 999
        assert tick_volume.get_observed_acml_vol("000660") is None, (
            "날짜 전환 시 이전 날짜 데이터가 전체 clear 되지 않았다"
        )


def test_date_boundary_is_kst_not_utc():
    """W3-9 — 날짜 판정은 **KST**.

    UTC 2026-08-25 15:30 = KST 2026-08-26 00:30 → 이미 다음 날이다.
    UTC 기준으로 판정하면 KST 자정 이후 9시간 동안 어제 관측이 살아남는다.
    """
    with freeze_time("2026-08-25 14:30:00"):   # KST 2026-08-25 23:30
        tick_volume.record_acml_vol("005930", 1_000)
    with freeze_time("2026-08-25 15:30:00"):   # KST 2026-08-26 00:30
        assert tick_volume.get_observed_acml_vol("005930") is None, (
            "KST 자정을 넘겼는데 어제 관측이 살아 있다 — 날짜 판정이 UTC 기준이다"
        )


def test_same_kst_day_across_utc_midnight_survives():
    """W3-9 (반대 방향) — UTC 자정을 넘어도 **같은 KST 날**이면 유지된다."""
    with freeze_time("2026-08-24 16:00:00"):   # KST 2026-08-25 01:00
        tick_volume.record_acml_vol("005930", 4_242)
    with freeze_time("2026-08-25 05:00:00"):   # KST 2026-08-25 14:00
        assert tick_volume.get_observed_acml_vol("005930") == 4_242


# ===========================================================================
# W3-10 — 테스트 격리
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
def test_reset_for_test_clears_all():
    tick_volume.record_acml_vol("005930", 1)
    tick_volume.record_acml_vol("000660", 2)
    tick_volume.reset_for_test()
    assert tick_volume.get_observed_acml_vol("005930") is None
    assert tick_volume.get_observed_acml_vol("000660") is None
