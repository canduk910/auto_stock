"""P3a — VCP/BFB 후보 진단 payload 확장 회귀 가드.

## 왜

두 전략은 `enabled=True`·`weight=0.10` 인데 도입 이래 **체결 0건**이다. 실측으로
원인이 갈렸다:

    VCP  후보 0      — 깔때기 `추세필터 329 → 7 (97.9% 탈락)` → `pullback 7 → 0`
    BFB  후보 18     — 그중 **6종목(33%)이 WebSocket 미구독** → on_tick 미발화 →
                       `check_buy_signal` 자체가 호출되지 않음

그런데 지금 화면은 VB 용 타겟표를 재사용해 `K값 0.000` · `시가 "-"` 만 보여주고,
장 외 시간엔 행 자체가 렌더되지 않는다. **"왜 안 사는가"에 답할 정보가 0** 이다.

## 계약

- **VB 호환 5키(`k`/`target_price`/`open_price`/`target_offset`/`open_confirmed`)는
  유지**한다 — `scheduler._confirm_breakout_open_prices` 가 소비하고, 그건 매매
  안전성 8영역이라 건드릴 수 없다. 키 **추가만** 한다.
- `strategy_registry.get_strategies_status()` 는 `hasattr` 덕타이핑 제네릭이라
  키를 얹으면 registry·route 수정 **0** 으로 프론트까지 전달된다(kojiro 선례).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))

# `scheduler._confirm_breakout_open_prices` 가 소비하는 계약 (8영역 — 제거 금지)
_VB_COMPAT = ("k", "target_price", "open_price", "target_offset", "open_confirmed")


def _vcp() -> VcpBreakoutStrategy:
    s = VcpBreakoutStrategy(StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.1))
    s._candidates["005930"] = {
        "base_high": 72_000, "base_low": 66_000, "last_pullback_pct": 0.05,
        "atr14": 1_500, "ema50": 68_000, "ema150": 65_000, "ema200": 60_000,
        "prev_close": 70_000, "avg_volume_20": 100_000,
    }
    return s


def _bfb() -> BullFlagBreakoutStrategy:
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목", weight=0.1),
    )
    s._candidates["005930"] = {
        "pole_start": 60_000, "pole_high": 72_000, "flag_high": 70_500,
        "flag_low": 66_000, "flag_avg_volume": 80_000, "pole_len": 5,
        "atr14": 1_500, "prev_close": 70_000,
    }
    return s


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_vb_compat_keys_preserved(factory):
    """8영역(`scheduler._confirm_breakout_open_prices`) 소비 계약 — 제거 금지."""
    row = factory().get_targets_status()["005930"]
    for k in _VB_COMPAT:
        assert k in row, f"VB 호환 키 {k} 가 사라지면 scheduler 가 깨진다"


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_diagnostic_keys_present(factory):
    """후보 그리드가 "왜 안 사는가"에 답하는 데 필요한 최소 필드."""
    row = factory().get_targets_status()["005930"]
    for k in ("name", "prev_close", "stop_line", "volume_threshold",
              "in_cooldown", "bought_today"):
        assert k in row, f"진단 필드 {k} 누락"


def test_vcp_stop_line_is_base_low():
    assert _vcp().get_targets_status()["005930"]["stop_line"] == 66_000


def test_bfb_stop_line_is_flag_low():
    assert _bfb().get_targets_status()["005930"]["stop_line"] == 66_000


def test_bfb_exposes_measured_target():
    """BFB 의 유일한 익절 경로 — `flag_high + (pole_high − pole_start)` = 82,500."""
    assert _bfb().get_targets_status()["005930"]["measured_target"] == 82_500


@pytest.mark.parametrize(
    "factory,mult_key,avg", [(_vcp, "breakout_volume_mult", 100_000),
                             (_bfb, "breakout_volume_mult", 80_000)],
    ids=["vcp", "bfb"],
)
def test_volume_threshold_matches_buy_gate(factory, mult_key, avg):
    """화면의 거래량 컷 임계가 `check_buy_signal` 이 실제로 쓰는 값과 같아야 한다."""
    s = factory()
    row = s.get_targets_status()["005930"]
    assert row["volume_threshold"] == int(avg * s.config.params[mult_key])


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_bought_today_and_cooldown_reflected(factory):
    """"오늘 이미 매수 시도" / "쿨다운 중" 은 0건 진단의 직접 답이다."""
    s = factory()
    s._bought_today.add("005930")
    s._cooldown_until["005930"] = datetime.now(_KST).date() + timedelta(days=3)
    row = s.get_targets_status()["005930"]
    assert row["bought_today"] is True
    assert row["in_cooldown"] is True
    assert row["cooldown_until"] == (datetime.now(_KST).date() + timedelta(days=3)).isoformat()


def test_expired_cooldown_is_not_active():
    s = _vcp()
    s._cooldown_until["005930"] = date(2020, 1, 1)
    assert s.get_targets_status()["005930"]["in_cooldown"] is False


def test_bfb_exposes_breakout_retention_state():
    """BFB 는 첫 돌파 후 `breakout_retention_minutes` 대기한다.

    이 대기가 화면에 없으면 "돌파했는데 왜 안 샀나"에 답할 수 없다 —
    지금은 로그에만 남는다.
    """
    s = _bfb()
    seen = datetime.now(_KST) - timedelta(seconds=107)
    s._breakout_first_seen["005930"] = seen
    row = s.get_targets_status()["005930"]
    assert row["breakout_seen_at"] == seen.isoformat()
    assert row["retention_minutes"] == s.config.params["breakout_retention_minutes"]


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_payload_survives_missing_keys(factory):
    """부분 채움 후보에서도 예외 없이 렌더 가능한 dict 를 돌려준다."""
    s = factory()
    s._candidates["999999"] = {}
    row = s.get_targets_status()["999999"]
    for k in _VB_COMPAT:
        assert k in row
