"""cycle228-B (RED) — `_effective_setup` 구조 레벨 계약 복원.

## 결함 (착수 전 코드로 직접 확인 완료)

두 축이 동시에 성립해야 하는데 **둘 다 성립한다**:

1. `_effective_setup` 이 `_candidates`(live)를 **통째로 우선**한다 — 키별 병합이 아니다:

       live = self._candidates.get(ticker)
       if live:
           return live                      # ← 구조 레벨까지 전부 live
       return self._position_setup.get(ticker) or {}

2. `prepare()` 는 **보유 종목을 후보에서 제외하지 않는다** — AST 실측으로
   BFB/VCP 양쪽 `prepare` 본체에 `has_position` / `is_ticker_held_by_any` /
   `positions` / `_position_setup` 참조가 **0건**이다.

⇒ 돌파 후 급등한 보유 종목이 익일 **새 폴/플래그(베이스)로 재검출**되면
§2 손절선이 **새 `flag_low`/`base_low`(진입가보다 높을 수 있다)로 갈아탄다**
→ 상승 중인 포지션이 즉시 손절된다.

## 이것이 문서화된 계약과 정면 충돌한다

`_refresh_position_setup_from_candles` 의 docstring 이 직접 이렇게 적어 두었다:

> **구조 레벨**(`flag_low`/`flag_high`/`pole_high`/`pole_start`) → 진입 시점
> 셋업에서 확정된 값이라 **이미 있으면 건드리지 않는다**.

그 함수는 `_position_setup` 을 지킨다. 그런데 `_effective_setup` 의 live-우선이
**그 보호를 우회한다** — 보호받는 값이 실제로 읽히지 않는다.
`strategies/CLAUDE.md` P1 계약("구조 레벨은 BUY 직전 stamp 후 불변, 지표만 매일 갱신")도
같은 문장이다.

## 왜 지금 고치는가

BFB/VCP 청산 코드는 **전 기간 프로덕션 미실행**이다. 228-A 가 매수를 여는 순간
첫 체결이 곧 이 경로의 첫 가동이고, **D+1 아침이 바로 이 결함을 처음 밟는 시점**이다.

## 커밋 분리 (명세 구속)

228-A 와 228-B 는 같은 두 파일을 건드리므로 **A Green → A 커밋 → B Green** 순서다.
이 파일이 `test_cycle228b_*` 로 분리된 이유가 그것이고, **A Green 시점에도 여전히
RED 여야 한다** — A 구현이 우연히 B 를 만족시키면 커밋 분리의 의미가 사라진다.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from freezegun import freeze_time

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

BFB_LOGGER = "src.engine.strategies.bull_flag_breakout"
VCP_LOGGER = "src.engine.strategies.vcp_breakout"
CONFLICT = "[setup_structure_conflict]"

TICKER = "005930"
BUY_PRICE = 10_000
CURRENT = 10_200          # 매수가 대비 +2% — 상승 중인 포지션


def _lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


# ---------------------------------------------------------------------------
# BFB rig
# ---------------------------------------------------------------------------

def _bfb(
    *,
    stamp: dict | None,
    live: dict | None,
    high_since_buy: int = 10_300,
) -> BullFlagBreakoutStrategy:
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.15)
    )
    pos = Position(
        ticker=TICKER, buy_price=BUY_PRICE, quantity=10, order_no="O1",
        strategy_id="bull_flag_breakout",
    )
    pos.high_since_buy = high_since_buy
    pos.buy_date = date(2026, 8, 27)
    s.state.positions[TICKER] = pos
    if stamp is not None:
        s._position_setup[TICKER] = stamp
    if live is not None:
        s._candidates[TICKER] = live
    return s


_BFB_STAMP = {
    "flag_low": 9_000, "flag_high": 11_000,
    "pole_high": 12_000, "pole_start": 10_000, "atr14": 300,
}
# 익일 재검출 — 급등해서 새 폴/플래그가 잡혔다. flag_low 가 **매수가보다 높다.**
_BFB_LIVE_REDETECTED = {
    "flag_low": 10_500, "flag_high": 12_500,
    "pole_high": 14_000, "pole_start": 11_000, "atr14": 300,
}


# ---------------------------------------------------------------------------
# VCP rig
# ---------------------------------------------------------------------------

def _vcp(
    *, stamp: dict | None, live: dict | None, high_since_buy: int = 10_300,
) -> VcpBreakoutStrategy:
    s = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.10)
    )
    pos = Position(
        ticker=TICKER, buy_price=BUY_PRICE, quantity=10, order_no="O1",
        strategy_id="vcp_breakout",
    )
    pos.high_since_buy = high_since_buy
    pos.buy_date = date(2026, 8, 27)
    s.state.positions[TICKER] = pos
    if stamp is not None:
        s._position_setup[TICKER] = stamp
    if live is not None:
        s._candidates[TICKER] = live
    return s


_VCP_STAMP = {"base_low": 9_000, "atr14": 300, "ema50": 9_500}
_VCP_LIVE_REDETECTED = {"base_low": 10_500, "atr14": 300, "ema50": 9_500}


# ###########################################################################
# B1 — 결함 재현 (시정 후 기대를 단언 → 현행에서 RED)
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_b1_bfb_held_position_uses_stamped_flag_low_not_redetected():
    """B1 — 보유 중 재검출돼도 §2 손절선은 **진입 시점 stamp** 를 쓴다.

    현행: live `flag_low=10,500` > 현재가 10,200 → **STOP_LOSS**
          (상승 중인 포지션이 새 셋업의 하단에 걸려 조기 손절)
    시정: stamp `flag_low=9,000` → 발화 없음
    """
    strat = _bfb(stamp=_BFB_STAMP, live=_BFB_LIVE_REDETECTED)

    sig = strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    assert sig == Signal.NONE, (
        f"매수가 대비 +2% 인 포지션이 {sig} 로 청산됐다 — §2 손절선이 익일 "
        "재검출된 새 flag_low(10,500)로 갈아탔다. 구조 레벨은 BUY 직전 stamp 후 "
        "불변이라는 P1 계약 위반이다"
    )


@freeze_time("2026-08-27 10:00:00")
def test_b1_vcp_held_position_uses_stamped_base_low_not_redetected():
    strat = _vcp(stamp=_VCP_STAMP, live=_VCP_LIVE_REDETECTED)

    sig = strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    assert sig == Signal.NONE, (
        f"+2% 포지션이 {sig} — §2 가 재검출된 base_low(10,500)를 썼다"
    )


@freeze_time("2026-08-27 10:00:00")
def test_b1_bfb_measured_move_uses_stamped_pole_and_flag():
    """B1 — §3 측정된 이동도 구조 레벨이다 (stamp 기준).

    stamp 타겟 = flag_high 11,000 + (12,000−10,000) = **13,000**
    live 타겟  = flag_high 12,500 + (14,000−11,000) = 15,500
    현재가 13,100 → stamp 기준이면 익절 도달, live 기준이면 미도달.
    """
    strat = _bfb(stamp=_BFB_STAMP, live=_BFB_LIVE_REDETECTED, high_since_buy=13_100)

    sig = strat.check_exit_signal(TICKER, 13_100, BUY_PRICE)

    assert sig == Signal.TRAILING_STOP, (
        f"{sig} — §3 익절 타겟이 재검출된 폴/플래그로 밀려 진입 근거와 무관한 "
        "목표가 됐다 (측정된 이동은 진입 시점 폴 폭이 정의다)"
    )


# ###########################################################################
# B2 — 지표는 live 우선 유지 (현행 보존 검증)
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_b2_bfb_indicator_atr_still_comes_from_live():
    """B2 — `atr14` 는 **지표**라 매일 갱신이 설계 의도다.

    stamp atr14=1,000 → 샹들리에 11,000−2,000 = 9,000 → 미발화
    live  atr14=100   → 샹들리에 11,000−200  = 10,800 → **발화**
    """
    strat = _bfb(
        stamp={**_BFB_STAMP, "atr14": 1_000},
        live={**_BFB_STAMP, "flag_low": 9_500, "atr14": 100},
        high_since_buy=11_000,
    )

    sig = strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    assert sig == Signal.TRAILING_STOP, (
        "지표(atr14)까지 stamp 로 굳으면 상승 추세에서 트레일링이 뒤처진다 — "
        "구조 레벨만 고정하는 것이 계약이다"
    )


@freeze_time("2026-08-27 10:00:00")
def test_b2_vcp_indicator_ema50_still_comes_from_live():
    """B2 — VCP `ema50` 도 지표. live 10,500 이탈 → 발화."""
    strat = _vcp(
        stamp={**_VCP_STAMP, "ema50": 9_000},
        live={"base_low": 8_500, "atr14": 300, "ema50": 10_500},
    )

    assert strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE) == Signal.TRAILING_STOP


# ###########################################################################
# B2 — 폴백·결손 계약 보존
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_b2_bfb_unstamped_position_still_uses_live_fallback():
    """B2 — `_position_setup` 부재(재시작 직후 등)면 기존 폴백 그대로.

    stamp 가 없으면 보호할 값이 없다 — live 를 쓰는 것이 현행이자 최선이다.
    """
    strat = _bfb(stamp=None, live=_BFB_LIVE_REDETECTED)
    assert strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE) == Signal.STOP_LOSS


@freeze_time("2026-08-27 10:00:00")
def test_b2_bfb_zero_stamped_structure_does_not_fire():
    """B2 — stamp 구조 값이 `0`(결손)이면 **미발화**가 계약이다.

    ⚠️ 여기서 live 로 폴백하면 결손이 조용히 재검출 값으로 메워져 B1 결함이
    부분 부활한다. 잘못된 레벨로 손절선을 긋느니 §1 하드손절에 맡긴다
    (`_refresh_position_setup_from_candles` 의 fail-safe 원칙과 동일).
    """
    strat = _bfb(
        stamp={**_BFB_STAMP, "flag_low": 0},
        live=_BFB_LIVE_REDETECTED,
    )
    assert strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE) == Signal.NONE


@freeze_time("2026-08-27 10:00:00")
def test_b2_vcp_zero_stamped_structure_does_not_fire():
    strat = _vcp(stamp={**_VCP_STAMP, "base_low": 0}, live=_VCP_LIVE_REDETECTED)
    assert strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE) == Signal.NONE


@freeze_time("2026-08-27 10:00:00")
def test_b2_bfb_no_position_setup_and_no_live_is_still_empty_dict():
    """B2 — 미지 종목은 계속 **빈 dict**(None 아님). 호출부가 `.get()` 만으로 안전."""
    strat = _bfb(stamp=None, live=None)
    assert strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE) == Signal.NONE


# ###########################################################################
# B2 — `[setup_structure_conflict]` 관측 로그
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_b2_conflict_logged_once_per_ticker_per_day(caplog):
    """B2 — 발화 빈도 자체가 이 결함의 **실측 규모**다 (D+1 귀인 분리 목적).

    A(래치)와 B(리졸버)를 같은 날 배포하면 D+1 관찰에서 원인이 섞인다.
    전용 마커가 그 분리를 만든다.
    """
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(stamp=_BFB_STAMP, live=_BFB_LIVE_REDETECTED)

    for _ in range(5):
        strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    lines = _lines(caplog, CONFLICT)
    assert len(lines) == 1, f"1회/(ticker)/일 cap 미작동 — {len(lines)}행"
    assert TICKER in lines[0]


@freeze_time("2026-08-27 10:00:00")
def test_b2_no_conflict_log_when_live_matches_stamp(caplog):
    """구조 레벨이 같으면 충돌이 아니다 — 로그 0행."""
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(stamp=_BFB_STAMP, live=dict(_BFB_STAMP))

    strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    assert _lines(caplog, CONFLICT) == []


@freeze_time("2026-08-27 10:00:00")
def test_b2_no_conflict_log_when_unstamped(caplog):
    """stamp 가 없으면 비교 대상이 없다 — 폴백 경로는 정상이지 충돌이 아니다."""
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(stamp=None, live=_BFB_LIVE_REDETECTED)

    strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    assert _lines(caplog, CONFLICT) == []


def test_b2_conflict_log_cap_resets_on_date_change(caplog):
    caplog.set_level(logging.INFO, logger=BFB_LOGGER)
    strat = _bfb(stamp=_BFB_STAMP, live=_BFB_LIVE_REDETECTED)

    with freeze_time("2026-08-27 10:00:00"):
        strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)
    with freeze_time("2026-08-28 10:00:00"):
        strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    assert len(_lines(caplog, CONFLICT)) == 2


@freeze_time("2026-08-27 10:00:00")
def test_b2_vcp_conflict_logged_once(caplog):
    caplog.set_level(logging.INFO, logger=VCP_LOGGER)
    strat = _vcp(stamp=_VCP_STAMP, live=_VCP_LIVE_REDETECTED)

    for _ in range(3):
        strat.check_exit_signal(TICKER, CURRENT, BUY_PRICE)

    assert len(_lines(caplog, CONFLICT)) == 1


# ###########################################################################
# B3 — 결함 전제 자체를 가드로 못박는다
# ###########################################################################

@pytest.mark.parametrize(
    "rel",
    ["src/engine/strategies/bull_flag_breakout.py", "src/engine/strategies/vcp_breakout.py"],
    ids=["bfb", "vcp"],
)
def test_b3_effective_setup_is_not_wholesale_live(rel):
    """B3 — 리졸버가 live 를 **통째로 반환하지 않는다**.

    현행은 `if live: return live` 한 줄이라 키별 병합이 아예 없다. 시정 후에는
    구조/지표를 나눠 합성해야 하므로 이 형태가 남아 있으면 안 된다.
    """
    import ast
    from pathlib import Path

    src = Path(rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "_effective_setup"),
        None,
    )
    assert fn is not None, f"{rel} 에 `_effective_setup` 미발견"
    body = ast.unparse(fn)
    assert "return live" not in body, (
        f"{rel}::_effective_setup 이 여전히 live 를 통째로 반환한다 — "
        "구조 레벨 stamp 우선 병합이 없다"
    )
