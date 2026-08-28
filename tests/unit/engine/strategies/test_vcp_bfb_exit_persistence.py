"""P1 — VCP/BFB 청산 파라미터의 `_candidates` 단독 의존 결함 회귀 가드.

## 결함

`prepare()` 는 매 실행마다 `_candidates` 를 와이프한다(VCP `:199`/`:216`, BFB
`:171`/`:188`). 쓰기 지점은 스캔 루프 단 하나(VCP `:437`, BFB `:368`)이고
**후보 자격 필터를 통과한 종목만** 등록한다. 그런데 보유 종목은 정의상 이미
돌파해 셋업이 무너진 상태라 **다음 prepare 에서 탈락하는 것이 정상 동작**이다.

⇒ T+1 아침 prepare 직후부터 청산 분기가 조용히 죽는다. 재시작 사고가 아니라
**매일** 발생한다. 2026-08-04 kojiro 삼영무역(002810) 사고와 동일 클래스이며,
kojiro 는 `_position_atr` + `_effective_atr` 로 이미 시정됐다.

죽는 범위가 ATR 트레일링 하나가 아니다:

| | 죽는 분기 | 남는 것 |
|---|---|---|
| VCP | §1.5 래치 · **§2 `base_low` 손절** · §3 ATR 트레일링 · §4 `ema50` 이탈 | §1 하드손절 |
| BFB | §1.5 래치 · **§2 `flag_low` 손절** · **§3 measured-move 익절 전체** · §4 트레일링 | §1 하드손절 + §5 시간청산 |

두 전략 모두 `enabled=True`·`weight=0.10` 으로 **무장**돼 있다(운영 DB 실측
2026-08-06). 체결이 0건인 것은 꺼져 있어서가 아니라 진입 조건이 통과되지
않아서이므로, 첫 체결이 나는 순간 위 결함이 그대로 발동한다.

## 시정 — `_position_setup` 영속 맵 + `_effective_setup` 리졸버

kojiro `_position_atr` 패턴이되 **스칼라가 아니라 dict** 다(청산이 여러 키를 씀).

필드별 성격이 다르므로 갱신 규약도 다르다:

- **구조적 레벨** (`base_low` / `flag_low` / `pole_high` / `pole_start` /
  `flag_high`) — 진입 시점 셋업에서 확정된 값. BUY 직전 stamp 후 **불변**.
- **지표값** (`atr14`, `ema50`) — 매일 변한다. boot 훅
  (`recompute_high_since_buy`)이 **이미 fetch 하는 일봉으로 매일 갱신**한다.
  스냅샷을 박제하면 `ema50` 이 상승 추세에서 뒤처져 이탈 청산이 늦어진다.

⚠️ BFB §3 은 `info["pole_high"]` 처럼 **직접 인덱싱**이라 부분 재채움 시
`KeyError` → `check_exit_signal` 전체 예외. `.get()` 방어 + 키 결손 시 미발화
(과잉 청산 금지)가 계약이다.

⚠️ `_reset_daily_state` 에서 영속 맵을 clear 하면 밤새 소멸한다(kojiro 와 동일
이유). AST 로 봉인한다.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timedelta, timezone

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def _today() -> date:
    return datetime.now(_KST).date()


def _vcp(**params) -> VcpBreakoutStrategy:
    s = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.1, params=params),
    )
    s.state.total_investment = 115_000
    return s


def _bfb(**params) -> BullFlagBreakoutStrategy:
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목", weight=0.1, params=params),
    )
    s.state.total_investment = 115_000
    return s


def _hold(s, ticker="005930", *, buy=70_000, qty=1, high=None, days_ago=3):
    pos = Position(
        ticker=ticker, buy_price=buy, quantity=qty, order_no=f"O-{ticker}",
        strategy_id=s.strategy_id, buy_date=_today() - timedelta(days=days_ago),
        high_since_buy=high or buy,
    )
    s.state.positions[ticker] = pos
    return pos


# VCP `_candidates` 스키마 (vcp_breakout.py:437-446)
def _vcp_info(*, base_low=66_000, atr14=1_500, ema50=68_000):
    return {
        "base_high": 72_000, "base_low": base_low, "last_pullback_pct": 0.05,
        "atr14": atr14, "ema50": ema50, "ema150": 65_000, "ema200": 60_000,
        "prev_close": 70_000, "avg_volume_20": 100_000,
    }


# BFB `_candidates` 스키마 (bull_flag_breakout.py:368-372)
def _bfb_info(*, flag_low=66_000, atr14=1_500, pole_start=60_000, pole_high=72_000, flag_high=70_500):
    return {
        "pole_start": pole_start, "pole_high": pole_high, "flag_high": flag_high,
        "flag_low": flag_low, "flag_avg_volume": 80_000, "pole_len": 5,
        "atr14": atr14, "prev_close": 70_000,
    }


# ---------------------------------------------------------------------------
# P1-A — 영속 맵 + 리졸버 존재
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_persistent_setup_map_and_resolver_exist(factory):
    s = factory()
    assert isinstance(s._position_setup, dict), "청산 파라미터 영속 맵"
    assert callable(s._effective_setup), "_candidates live → _position_setup 폴백 리졸버"


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_live_candidates_take_precedence(factory):
    """설계 의도 보존 — live 값이 있으면 그쪽을 쓴다(변동성/지표 변화 반영)."""
    s = factory()
    info = _vcp_info(atr14=2_000) if s.strategy_id == "vcp_breakout" else _bfb_info(atr14=2_000)
    s._candidates["005930"] = info
    s._position_setup["005930"] = {"atr14": 111}
    assert s._effective_setup("005930").get("atr14") == 2_000


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_resolver_falls_back_to_persistent_map(factory):
    s = factory()
    s._position_setup["005930"] = {"atr14": 1_500}
    assert not s._candidates
    assert s._effective_setup("005930").get("atr14") == 1_500


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_resolver_returns_empty_dict_when_nothing_known(factory):
    """미지 종목은 빈 dict — 호출부가 `.get()` 만으로 안전해야 한다."""
    s = factory()
    assert s._effective_setup("999999") == {}


# ---------------------------------------------------------------------------
# P1-B — VCP: `_candidates` 와이프 후에도 §2/§3/§4 가 살아 있다
# ---------------------------------------------------------------------------

def test_vcp_base_low_stop_survives_candidates_wipe():
    """§2 베이스 하단 이탈 손절 — 결함 시 분기 통째 skip 되던 곳."""
    s = _vcp()
    _hold(s, buy=70_000)
    s._position_setup["005930"] = {"base_low": 66_000, "atr14": 1_500, "ema50": 60_000}
    assert not s._candidates
    assert s.check_exit_signal("005930", 65_900, 70_000) == Signal.STOP_LOSS


def test_vcp_atr_trailing_survives_candidates_wipe():
    """§3 ATR 트레일링 — 고점 80,000 − 1,500×2 = 77,000."""
    s = _vcp()
    _hold(s, buy=70_000, high=80_000)
    s._position_setup["005930"] = {"base_low": 1, "atr14": 1_500, "ema50": 1}
    assert s.check_exit_signal("005930", 77_000, 70_000) == Signal.TRAILING_STOP
    assert s.check_exit_signal("005930", 77_100, 70_000) == Signal.NONE


def test_vcp_ema50_exit_survives_candidates_wipe():
    """§4 50일 EMA 이탈."""
    s = _vcp()
    _hold(s, buy=70_000)
    s._position_setup["005930"] = {"base_low": 1, "atr14": 0, "ema50": 68_000}
    assert s.check_exit_signal("005930", 67_900, 70_000) == Signal.TRAILING_STOP


# ---------------------------------------------------------------------------
# P1-C — BFB: 와이프 후에도 §2/§3/§4 가 살아 있다
# ---------------------------------------------------------------------------

def test_bfb_flag_low_stop_survives_candidates_wipe():
    s = _bfb()
    _hold(s, buy=70_000)
    s._position_setup["005930"] = {"flag_low": 66_000, "atr14": 1_500}
    assert not s._candidates
    assert s.check_exit_signal("005930", 65_900, 70_000) == Signal.STOP_LOSS


def test_bfb_measured_move_target_survives_candidates_wipe():
    """§3 measured-move 익절 — BFB 의 **유일한 익절 경로**.

    타겟 = flag_high + (pole_high − pole_start) = 70,500 + 12,000 = 82,500
    """
    s = _bfb()
    _hold(s, buy=70_000)
    s._position_setup["005930"] = {
        "flag_low": 1, "atr14": 0,
        "pole_start": 60_000, "pole_high": 72_000, "flag_high": 70_500,
    }
    assert s.check_exit_signal("005930", 82_500, 70_000) == Signal.TRAILING_STOP


def test_bfb_atr_trailing_survives_candidates_wipe():
    s = _bfb()
    _hold(s, buy=70_000, high=80_000)
    s._position_setup["005930"] = {"flag_low": 1, "atr14": 1_500}
    assert s.check_exit_signal("005930", 77_000, 70_000) == Signal.TRAILING_STOP


def test_bfb_measured_move_silent_on_missing_keys():
    """키 결손 시 **미발화** — 직접 인덱싱이면 KeyError 로 청산 전체가 죽는다.

    과잉 청산(임의 기본값으로 익절 발화)도 금지 — 조용히 넘어가야 한다.
    """
    s = _bfb()
    _hold(s, buy=70_000)
    s._position_setup["005930"] = {"flag_low": 1, "atr14": 0}   # pole_* / flag_high 결손
    assert s.check_exit_signal("005930", 999_999, 70_000) == Signal.NONE


# ---------------------------------------------------------------------------
# P1-D — stamp 3지점
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_buy_signal_stamps_setup(factory):
    """BUY 반환 직전 stamp — 당일 매수분이 다음날 prepare 와이프를 견딘다.

    cycle228 적응(불변식 동일·검사 표면만 이동) — 게이트 전환이 BUY 확정 블록을
    `_evaluate_vol_gate` 로 추출해 stamp 도 함께 이동했다. BUY 경로 =
    `check_buy_signal` → `_evaluate_vol_gate` 두 함수의 합집합 소스로 검사한다
    (호출 배선은 cycle228 AST G-3 이 별도 강제).
    """
    s = factory()
    src = inspect.getsource(type(s).check_buy_signal)
    gate = getattr(type(s), "_evaluate_vol_gate", None)
    if gate is not None:
        src += inspect.getsource(gate)
    assert "_position_setup" in src, "BUY 경로에서 청산 파라미터를 영속화해야 한다"


@pytest.mark.parametrize("factory", [_vcp, _bfb], ids=["vcp", "bfb"])
def test_on_position_closed_pops_setup(factory):
    """청산 시 정리 — 재진입 시 stale 셋업으로 손절하면 안 된다."""
    s = factory()
    _hold(s)
    s._position_setup["005930"] = {"atr14": 1}
    s.on_position_closed("005930")
    assert "005930" not in s._position_setup


@pytest.mark.parametrize(
    "mod",
    ["src.engine.strategies.vcp_breakout", "src.engine.strategies.bull_flag_breakout"],
    ids=["vcp", "bfb"],
)
def test_reset_daily_state_never_clears_persistent_setup(mod):
    """`_reset_daily_state` 가 영속 맵을 건드리면 멀티데이 보유가 밤새 소멸한다.

    kojiro `_position_sectors`/`_position_atr` 와 동일한 봉인(AST).
    """
    import importlib

    src = inspect.getsource(importlib.import_module(mod))
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_reset_daily_state":
            continue
        # docstring 은 허용(경고문에 이름이 등장한다) — **코드만** 검사한다.
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        code = "\n".join((ast.get_source_segment(src, n) or "") for n in body)
        assert "_position_setup" not in code, (
            f"{mod}._reset_daily_state 가 _position_setup 을 clear — 밤샘 소멸"
        )


# ---------------------------------------------------------------------------
# P1-E — 지표값은 boot 훅에서 매일 갱신, 구조 레벨은 불변
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory,structural,indicators",
    [
        (_vcp, {"base_low": 66_000}, ("atr14", "ema50")),
        (_bfb, {"flag_low": 66_000, "flag_high": 70_500, "pole_high": 72_000,
                "pole_start": 60_000}, ("atr14",)),
    ],
    ids=["vcp", "bfb"],
)
async def test_boot_hook_refreshes_indicators_and_keeps_structure(
    factory, structural, indicators, monkeypatch,
):
    """`recompute_high_since_buy` 가 **이미 fetch 한 일봉**으로 지표를 갱신한다.

    지표(`atr14`/`ema50`)를 진입 시점 스냅샷으로 박제하면 상승 추세에서 `ema50` 이
    뒤처져 §4 이탈 청산이 늦어진다. 반대로 구조 레벨(`base_low`/`flag_low`/`pole_*`)
    은 진입 시점 셋업에서 확정된 값이라 **불변**이어야 한다.
    """
    from unittest.mock import AsyncMock

    s = factory()
    _hold(s, buy=70_000, days_ago=3)
    stale = {**structural, **{k: 1 for k in indicators}}
    s._position_setup["005930"] = dict(stale)

    monkeypatch.setattr(
        "src.api.condition.fetch_daily_candles", AsyncMock(return_value=_vcp_candles()),
    )
    monkeypatch.setattr("src.db.positions.update_high", AsyncMock())
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())

    await s.recompute_high_since_buy()

    setup = s._position_setup["005930"]
    for k, v in structural.items():
        assert setup[k] == v, f"{k} 는 구조 레벨 — 불변이어야 한다"
    for k in indicators:
        assert setup[k] > 1, f"{k} 는 매일 재계산 대상 (stale 1 유지되면 안 됨)"


def _vcp_candles(n: int = 80) -> list[dict]:
    """KIS 일봉 형태 (최신순) — `_atr` 는 최신순, `_ema` 는 시간순을 기대한다."""
    out = []
    for i in range(n):
        base = 70_000 - i * 50
        out.append({
            "stck_bsop_date": (_today() - timedelta(days=i)).strftime("%Y%m%d"),
            "stck_hgpr": str(base + 800), "stck_lwpr": str(base - 800),
            "stck_clpr": str(base), "stck_oprc": str(base - 100), "acml_vol": "100000",
        })
    return out


def test_vcp_base_low_rederived_when_lost_on_restart():
    """프로세스 재시작으로 `base_low` 가 소실되면 매수일 이전 봉으로 재검출한다.

    `_position_setup` 은 in-memory 다 — `_entry_atr` 만 살려서는 §2 손절이 침묵한다.
    재검출 실패 시엔 미복구(0)로 남긴다: 잘못된 레벨로 손절선을 긋느니 §1
    하드손절에 맡기는 편이 낫다(fail-safe).
    """
    s = _vcp()
    pos = _hold(s, buy=70_000, days_ago=3)
    assert not s._position_setup and not s._candidates
    s._refresh_position_setup_from_candles("005930", pos, _vcp_candles())
    setup = s._position_setup["005930"]
    assert setup["atr14"] > 0 and setup["ema50"] > 0, "지표는 항상 재계산"
    assert setup.get("base_low", 0) >= 0, "재검출 실패는 미복구 — 예외는 금지"


def test_vcp_rederive_never_overwrites_existing_base_low():
    """이미 있는 구조 레벨은 덮어쓰지 않는다 — 진입 시점 값이 정본."""
    s = _vcp()
    pos = _hold(s, buy=70_000, days_ago=3)
    s._position_setup["005930"] = {"base_low": 66_000, "atr14": 1, "ema50": 1}
    s._refresh_position_setup_from_candles("005930", pos, _vcp_candles())
    assert s._position_setup["005930"]["base_low"] == 66_000


def test_vcp_rederive_excludes_buy_date_and_after():
    """매수일 당일/이후 봉이 섞이면 돌파 이후 구간이 박스에 포함돼 베이스가 왜곡된다."""
    s = _vcp()
    pos = _hold(s, buy=70_000, days_ago=3)
    captured: list[list[dict]] = []
    s._detect_base = lambda cs: (captured.append(cs), None)[1]
    s._rederive_base_low("005930", pos, _vcp_candles())
    if captured:
        buy_dd = pos.buy_date.strftime("%Y%m%d")
        assert all(c["stck_bsop_date"] < buy_dd for c in captured[0])


# ---------------------------------------------------------------------------
# P1-F — 안전성: 8영역 미접촉 + 매수 행위 불변
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mod",
    ["src.engine.strategies.vcp_breakout", "src.engine.strategies.bull_flag_breakout"],
    ids=["vcp", "bfb"],
)
def test_no_trading_hot_path_import(mod):
    """전략 파일이 매매 hot path 를 import 하면 안 된다 (사이클 172 SAFETY-4)."""
    import importlib

    src = inspect.getsource(importlib.import_module(mod))
    for banned in ("from src.engine.risk", "from src.engine.order_engine", "from src.realtime"):
        assert banned not in src, f"{mod} 에 {banned} 금지"


def test_swing_poll_strategies_unchanged():
    """`_SWING_POLL_STRATEGIES` 에 BFB/VCP 를 넣으면 **매수 폴링 대상**이 된다.

    이 상수는 재prepare·구독·매수 폴루프·청산 폴루프에 모두 쓰인다 — 복구 배선
    목적으로 건드리면 매수 행위가 바뀐다.
    """
    from src.engine.scheduler import _SWING_POLL_STRATEGIES

    assert _SWING_POLL_STRATEGIES == ("donchian_swing", "kojiro")
