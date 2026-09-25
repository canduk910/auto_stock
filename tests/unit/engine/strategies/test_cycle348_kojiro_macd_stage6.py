"""cycle348 — `[kojiro_macd_observe]` 를 국면6 크로스(role=stage6_gc)까지 확장 (Red).

명세 = `_workspace/red/cycle348_kojiro_macd_stage6_spec.md` (B1~B10).

## 무엇을 재나

cycle344 관측기는 보유(held)·strict entry 최종 후보(candidate)만 기록한다. 국면6 종목은
step7(국면1 ∧ 3선 우상향)에서 떨어지므로 한 줄도 안 남는다. cycle346 의 B6 규칙
(ATR 밴드 ∧ 국면6 ∧ gc3)을 실매매 유니버스에서 **앞으로** 재려면 그 사건을 기록해야 한다.
이 사이클은 step6 직후에 국면6 ∧ 마지막 봉 gc3 종목을 수집하고, 같은 마커로
`role=stage6_gc` 행을 남긴다(끝에 `bar= close= atr=`).

## 🔴 이 사이클이 바꾸지 않는 것

**매매 행위 0.** `_candidates`·`get_scanned_tickers()`·`stats`·funnel 기록·`_held_stage3`·
`_bought_today` 는 수집 헬퍼가 터져도, leaf 가 터져도 정상 실행과 **완전 동일**해야 한다
(`test_g348_b9_*`). 국면6 종목은 여전히 step7 에서 `stage1_up_ex` 로 탈락한다.

## caplog 규약 (CI 루트 로거 DEBUG 교훈 — cycle252 T2)

행 개수 단언은 전부 `levelno >= WARNING ∧ msg.startswith("[kojiro_macd_observe] ")` 로
한정한다(`_macd_lines`). 관측기 실패 흔적(`observer_failed`)만 DEBUG 까지 본다.

## 돌연변이 → 죽이는 테스트 매핑 (전부 KILL 이어야 한다)

| 돌연변이 | 죽이는 테스트 |
|---|---|
| M1 gc3 정의를 상태(`m3>s3`)로 | `test_g348_b2_stage6_without_cross_is_silent`(N6: 국면6·시그널 위 상태·교차 없음 → 행이 생김) · `test_g348_b3_helper_returns_none_without_cross` |
| M2 `stage == 6` → `!= 6` / `>= 5` | `test_g348_b2_other_stage_cross_is_silent`(F5 국면5 gc3 · C1 국면1 gc3) · `test_g348_b2_macd_row_not_called_for_other_stages`(`_macd_observe_row` 호출 stage 목록) · `test_g348_b3_helper_returns_none_for_other_stage` |
| M3 role 문자열 오기(stage6_gc→candidate 등) | `test_g348_b1_stage6_gc_row_emitted` · `test_g348_b6_leaf_row_values` · `test_g348_b7_summary_line_*` |
| M4 15원소 계약 파괴(끝 3필드 누락·12원소) | `test_g348_b3_helper_returns_fifteen_tuple` · `test_g348_b8_leaf_skips_non_fifteen_rows`(12원소 행을 받아 주면 KILL) · `test_g348_b1_stage6_gc_row_emitted`(bar/close/atr 값) |
| M5 수집 헬퍼 예외가 루프 try 로 샘(자기 try 제거) | `test_g348_b9_identical_when_collect_raises`(S6 보유 → held stamp·funnel stage1_up_ex 차분) · `test_g348_b4_collect_call_has_own_try`(AST) |
| M6 일일 상한 제거 | `test_g348_b7_daily_limit_60_and_one_summary` |
| M7 요약 줄 중복(하루 2회) | `test_g348_b7_summary_line_once_per_day` **하나뿐**이다 — `test_g348_b7_prepare_rerun_does_not_duplicate` 는 국면6 종목이 1개라 상한에 닿지 않아 요약 줄 자체가 없으므로 M7 을 못 잡는다 |
| M8 leaf 호출을 `observe_macd` 와 같은 try 에 합침 | `test_g348_b5_stage6_survives_observe_macd_failure`(observe_macd 가 터져도 stage6 행 존재) · `test_g348_b5_emit_call_has_own_try_after_observe_macd`(AST) |
| Xc4 step6 직후 국면6 이면 `stats["stage_valid_pass"] += 1` | `test_g348_b9_golden_matches_pre_extension`(stats 골든) — 차분 비교(`b9_identical_*`)는 정상·스텁 두 실행이 **같은 돌연변이**를 공유해 못 잡는다 |
| Xc6 step6 직후 국면6 이면 `stats["stage6_seen"] = …`(새 키) | `test_g348_b9_golden_matches_pre_extension`(키 집합 = `_empty_scan_stats()` + stats 골든) |
| Xk leaf `rule6/5/4` 식에서 `gc3` 제거 | `test_g348_b6_leaf_row_values`(gc3=False 행 → `gc3=0`·`rule6=0`) |
| W 잘못된 봉(`iloc[-2]`·당일 봉 미제외·`usable[1]`)으로 bar/close/atr 채움 | `test_g348_b3_row_tail_is_last_completed_bar`(봉마다 날짜·종가·ATR 이 다른 시나리오 — 당일 봉 미제외는 `partial_today` 케이스만 잡는다) |

골든(`_GOLDEN_*`)은 확장 **전** 코드(HEAD `2087ad3`)로 `_SCENARIO` 를 돌려 도출했다 — 이 사이클이
매매 산출을 바꾸지 않았다는 주장을 차분이 아니라 **고정 기준**으로 잰다.

## 인터페이스 (명세 예시 이름으로 고정)

- `KojiroStrategy._stage6_gc_observe_row(enriched, stage, bar_date, prev_close, atr_val) -> tuple | None`
- `src.engine.kojiro_band_observe.observe_macd_stage6(macd_s6_raw) -> None`
- `src.engine.kojiro_band_observe.STAGE6_GC_DAILY_LIMIT == 60`

Red 단계에서 import 에러로 전체가 죽지 않도록 신규 심볼은 전부 `getattr` 로 읽는다.
"""
from __future__ import annotations

import ast
import inspect
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from freezegun import freeze_time

import src.engine.kojiro_band_observe as leaf
from src.engine.kojiro_band_observe import MACD_MARKER, reset_kojiro_band_observe_cap
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[4]
_KOJIRO_PY = _REPO / "src" / "engine" / "strategies" / "kojiro.py"
_LEAF_PY = _REPO / "src" / "engine" / "kojiro_band_observe.py"

_LEAF_LOGGER = "src.engine.kojiro_band_observe"

# 기존 held/candidate 행의 필드 순서 — 파싱 계약. 확장 전과 byte 동일해야 한다.
_BASE_KEYS = [
    "ticker", "role", "stage", "gc3", "bars_since_gc3",
    "m1", "m2", "m3", "s1", "s2", "s3", "hist3",
    "m1_up", "m2_up", "m3_up", "all_macd_up",
    "rule6", "rule5", "rule4",
]
_S6_KEYS = _BASE_KEYS + ["bar", "close", "atr"]


@pytest.fixture(autouse=True)
def _fresh_cap():
    reset_kojiro_band_observe_cap()
    yield
    reset_kojiro_band_observe_cap()


# ── 공용 ────────────────────────────────────────────────────────────────


def _mk():
    from src.engine.strategies.kojiro import KojiroStrategy
    return KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))


def _need_leaf(name: str):
    fn = getattr(leaf, name, None)
    if fn is None:
        pytest.fail(f"미구현: src.engine.kojiro_band_observe.{name} 가 없다 (cycle348 B5/B7)")
    return fn


def _need_helper(strat):
    fn = getattr(strat, "_stage6_gc_observe_row", None)
    if fn is None:
        pytest.fail("미구현: KojiroStrategy._stage6_gc_observe_row 가 없다 (cycle348 B4)")
    return fn


def _macd_lines(caplog) -> list[str]:
    """WARNING 이상 ∧ 마커 prefix 로 한정한 MACD 관측 행(요약 포함)."""
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(MACD_MARKER + " ")
    ]


def _parse(line: str) -> dict[str, str]:
    body = line[len(MACD_MARKER):]
    return dict(tok.split("=", 1) for tok in body.split() if "=" in tok)


def _keys_in_order(line: str) -> list[str]:
    body = line[len(MACD_MARKER):]
    return [tok.split("=", 1)[0] for tok in body.split() if "=" in tok]


def _s6_rows(caplog) -> list[dict[str, str]]:
    return [
        _parse(m) for m in _macd_lines(caplog)
        if "role=stage6_gc" in m and "cap_reached=" not in m
    ]


def _summaries(caplog) -> list[str]:
    return [m for m in _macd_lines(caplog) if "role=stage6_gc" in m and "cap_reached=" in m]


def _row12(stage=6, *, gc3=True, m2_up=True):
    return (stage, 1.0, 2.0, 1.0, 0.5, 0.5, 0.5, gc3, 0, True, m2_up, True)


def _row15(stage=6, *, gc3=True, m2_up=True, bar="20250101", close=10000, atr=200.0):
    return _row12(stage, gc3=gc3, m2_up=m2_up) + (bar, close, atr)


# ── prepare 시나리오 ─────────────────────────────────────────────────────


def _full(stage_series, macd3):
    n = len(stage_series)
    return pd.DataFrame({
        "close": [10000.0] * n, "atr": [200.0] * n, "stage": list(stage_series),
        "ema_s": [9900.0] * n, "ema_m": [9800.0] * n, "ema_l": [9700.0] * n,
        "ema_s_up": [True] * n, "ema_m_up": [True] * n, "ema_l_up": [True] * n,
        "band_width": [10.0 + i for i in range(n)],
        "macd3": [float(x) for x in macd3],
        "macd1": [float(x) + 1 for x in macd3],
        "macd2": [float(x) + 2 for x in macd3],
        "macd1_sig": [0.5] * n, "macd2_sig": [0.5] * n, "macd3_sig": [0.5] * n,
    })


# 시그널 = 0.5 고정. [.., 0, 1] = 마지막 봉에서 교차(gc3). [.., 3, 4] = 이미 위(상태, 교차 아님).
_SCENARIO = [
    ("T1", [4, 4, 4, 6, 1], [0, 0, 2, 4, 6]),   # 국면1 후보, 교차는 과거
    ("S6", [1, 1, 1, 6, 6], [0, 0, 0, 0, 1]),   # 🎯 국면6 ∧ 마지막 봉 gc3
    ("N6", [1, 1, 1, 6, 6], [0, 1, 2, 3, 4]),   # 국면6, 시그널 위 **상태**지만 교차 없음
    ("F5", [4, 4, 4, 5, 5], [0, 0, 0, 0, 1]),   # 국면5 ∧ gc3
    ("C1", [4, 4, 4, 6, 1], [0, 0, 0, 0, 1]),   # 국면1 후보 ∧ gc3
]


async def _run_prepare(strat, monkeypatch, *, scenario=_SCENARIO, held=(),
                       collect_stub=None, leaf6_stub=None, macd_stub=None,
                       candles=None, frames=None):
    """`candles`(DESC 일봉 목록)·`frames`(종목별 enrich 결과)를 주면 기본 합성 대신 그것을 쓴다."""
    import src.engine.strategies.kojiro as kmod
    from src.db import stock_master_daily as smd
    from src.engine.strategy_base import Position

    for t in held:
        strat.state.positions[t] = Position(
            ticker=t, buy_price=10000, quantity=1, order_no="o",
            strategy_id="kojiro", buy_date=date(2026, 9, 1))

    tickers = [t for t, _, _ in scenario]
    monkeypatch.setattr(strat, "_scan_universe", AsyncMock(return_value=tickers))
    monkeypatch.setattr(strat, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=(tickers, [])))
    monkeypatch.setattr(strat, "_fetch_sector", AsyncMock(return_value="미분류"))
    if candles is None:
        candles = [{
            "stck_bsop_date": "20250101", "stck_oprc": "10000", "stck_hgpr": "10100",
            "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
        } for _ in range(85)]
    monkeypatch.setattr(smd, "get_recent_daily_normalized", AsyncMock(return_value=candles))
    if frames is None:
        frames = [_full(st, m3) for _, st, m3 in scenario]
    dfs = iter(frames)
    monkeypatch.setattr(kmod, "enrich", lambda df, cfg: next(dfs))

    funnel_calls: list[str] = []
    orig_funnel = strat._record_funnel_pipeline_step

    def _spy_funnel(*a, **k):
        funnel_calls.append(repr((a, sorted(k.items()))))
        return orig_funnel(*a, **k)

    monkeypatch.setattr(strat, "_record_funnel_pipeline_step", _spy_funnel)
    if collect_stub is not None:
        monkeypatch.setattr(strat, "_stage6_gc_observe_row", collect_stub, raising=False)
    if leaf6_stub is not None:
        monkeypatch.setattr(kmod, "observe_macd_stage6", leaf6_stub, raising=False)
    if macd_stub is not None:
        monkeypatch.setattr(kmod, "observe_macd", macd_stub, raising=False)

    await strat.prepare()
    stats = dict(strat.get_scan_stats())
    stats_keys = set(stats)
    stats.pop("last_run_at", None)   # 벽시계 — 두 실행 사이에 반드시 다르다
    return {
        "scanned": list(strat.get_scanned_tickers()),
        "candidates": {t: repr(v) for t, v in strat._candidates.items()},
        # 골든 비교용 — 종목명(전역 이름 캐시 의존)은 빼고, 점수는 부동소수 꼬리를 자른다.
        "cand_fields": {
            t: {k: (round(v, 9) if k == "score" else v)
                for k, v in d.items() if k != "name"}
            for t, d in strat._candidates.items()
        },
        "bought": set(strat._bought_today),
        "held_stage3": {t: repr(v) for t, v in strat._held_stage3.items()},
        "held_stage3_flag": {t: v[1] for t, v in strat._held_stage3.items()},
        "stats": stats,
        "stats_keys": stats_keys,
        "funnel": funnel_calls,
        "funnel_steps": [
            (s["step_no"], [x["ticker"] for x in s["survived"]],
             [(x.get("ticker"), x.get("reason")) for x in s["excluded"]])
            for s in strat._funnel_steps
        ],
    }


class _Counter:
    def __init__(self):
        self.n = 0

    def raiser(self, *a, **k):
        self.n += 1
        raise RuntimeError("cycle348 stub exploded")


# ── B1/B2/B6 — prepare 배선: 누가 행을 받나 ────────────────────────────────


async def test_g348_b1_stage6_gc_row_emitted(monkeypatch, caplog):
    """🎯 국면6 ∧ 마지막 봉 gc3 → role=stage6_gc WARNING 1줄, 끝에 bar/close/atr."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    await _run_prepare(_mk(), monkeypatch)
    rows = _s6_rows(caplog)
    assert [r["ticker"] for r in rows] == ["S6"], (
        f"stage6_gc 행은 S6 한 줄이어야 한다 — 실제 {[r.get('ticker') for r in rows]}")
    r = rows[0]
    assert r["role"] == "stage6_gc"
    assert r["stage"] == "6" and r["gc3"] == "1"
    assert (r["bar"], r["close"], r["atr"]) == ("20250101", "10000", "200.00")
    assert r["rule6"] == "1" and r["rule5"] == "0" and r["rule4"] == "0"


async def test_g348_b2_stage6_without_cross_is_silent(monkeypatch, caplog):
    """국면6 이지만 마지막 봉 교차가 아니면(시그널 위 **상태**) 0줄 — gc3 는 edge 다(M1)."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    await _run_prepare(_mk(), monkeypatch)
    _need_leaf("observe_macd_stage6")
    assert "N6" not in {r["ticker"] for r in _s6_rows(caplog)}, (
        "교차 없는 국면6 종목이 stage6_gc 로 기록됐다 — gc3 를 상태로 읽었다")


async def test_g348_b2_other_stage_cross_is_silent(monkeypatch, caplog):
    """국면≠6 이면 gc3 가 있어도 0줄(M2)."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    await _run_prepare(_mk(), monkeypatch)
    _need_leaf("observe_macd_stage6")
    got = {r["ticker"] for r in _s6_rows(caplog)}
    assert "F5" not in got, "국면5 교차가 stage6_gc 로 기록됐다"
    assert "C1" not in got, "국면1 교차가 stage6_gc 로 기록됐다"
    assert "T1" not in got


async def test_g348_b2_macd_row_not_called_for_other_stages(monkeypatch):
    """`stage != 6` 이면 `_macd_observe_row` 를 추가로 부르지 않는다 — gc3 는 그 결과를 재사용한다.

    후보(T1·C1, 국면1)는 기존 호출 2회, 국면6(S6·N6)만 추가 2회. 국면5(F5)는 0회.
    """
    strat = _mk()
    seen: list[int] = []
    orig = strat._macd_observe_row

    def _spy(enriched, stage):
        seen.append(int(stage))
        return orig(enriched, stage)

    monkeypatch.setattr(strat, "_macd_observe_row", _spy)
    await _run_prepare(strat, monkeypatch)
    assert sorted(seen) == [1, 1, 6, 6], (
        f"_macd_observe_row 호출 stage 목록이 {sorted(seen)} — 기대 [1, 1, 6, 6] "
        "(국면6 만 추가 호출, 그 외 국면은 추가 계산 0)")


async def test_g348_b6_base_rows_format_unchanged(monkeypatch, caplog):
    """기존 candidate 행 서식은 확장 전과 동일(필드·순서·bar/close/atr 없음)."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    await _run_prepare(_mk(), monkeypatch)
    cand = [m for m in _macd_lines(caplog) if " role=candidate " in m]
    assert cand, "candidate 행이 사라졌다"
    for m in cand:
        assert _keys_in_order(m) == _BASE_KEYS, f"candidate 행 서식이 바뀌었다: {m}"


async def test_g348_b6_stage6_fields_are_base_plus_tail(monkeypatch, caplog):
    """stage6_gc 행 = 기존 행과 **같은 필드·같은 순서** + 끝에 bar/close/atr."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    await _run_prepare(_mk(), monkeypatch)
    s6 = [m for m in _macd_lines(caplog) if " role=stage6_gc " in m and "cap_reached=" not in m]
    assert s6, "stage6_gc 행이 없다 — 미구현"
    assert _keys_in_order(s6[0]) == _S6_KEYS


async def test_g348_b9_stage6_still_rejected_at_step7(monkeypatch):
    """국면6 종목은 여전히 step7 에서 탈락한다 — 후보·스캔 목록에 없다."""
    out = await _run_prepare(_mk(), monkeypatch)
    assert "S6" not in out["candidates"] and "S6" not in out["scanned"]
    assert set(out["scanned"]) == {"T1", "C1"}


# ── B3/B4 — 수집 헬퍼 ────────────────────────────────────────────────────


def test_g348_b3_helper_returns_fifteen_tuple():
    """15원소 = `_macd_observe_row` 12원소 그대로 + (bar_date, prev_close, atr_val)."""
    strat = _mk()
    helper = _need_helper(strat)
    df = _full([1, 1, 1, 6, 6], [0, 0, 0, 0, 1])
    row = helper(df, 6, "20250101", 10000, 200.0)
    assert isinstance(row, tuple) and len(row) == 15, f"15원소가 아니다: {row!r}"
    assert row[:12] == strat._macd_observe_row(df, 6), "앞 12원소가 기존 행 계약과 다르다"
    assert row[12:] == ("20250101", 10000, 200.0)
    assert row[7] is True


def test_g348_b3_helper_returns_none_without_cross():
    strat = _mk()
    helper = _need_helper(strat)
    df = _full([1, 1, 1, 6, 6], [0, 1, 2, 3, 4])   # 시그널 위 상태, 교차 없음
    assert helper(df, 6, "20250101", 10000, 200.0) is None


@pytest.mark.parametrize("stage", [1, 2, 3, 4, 5])
def test_g348_b3_helper_returns_none_for_other_stage(stage):
    strat = _mk()
    helper = _need_helper(strat)
    df = _full([stage] * 5, [0, 0, 0, 0, 1])   # gc3 는 있다
    assert helper(df, stage, "20250101", 10000, 200.0) is None


@pytest.mark.parametrize("broken", [None, "x", pd.DataFrame({"close": [1.0]})])
def test_g348_b3_helper_never_raises(broken):
    strat = _mk()
    helper = _need_helper(strat)
    assert helper(broken, 6, "20250101", 10000, 200.0) is None


_FROZEN_KST = "2026-09-24 10:00:00+09:00"
_LAST_DONE_BAR = "20250331"   # 아래 합성 일봉의 가장 최근 **완성**봉


def _dated_candles(n: int = 85) -> list[dict]:
    """DESC(idx0=최신) 일봉 — 봉마다 날짜·종가가 다르다(잘못된 봉을 읽으면 값이 어긋난다)."""
    last = date(2025, 3, 31)
    return [{
        "stck_bsop_date": (last - timedelta(days=i)).strftime("%Y%m%d"),
        "stck_oprc": str(10000 + i), "stck_hgpr": str(10100 + i),
        "stck_lwpr": str(9900 + i), "stck_clpr": str(10000 + i), "acml_vol": "1000000",
    } for i in range(n)]


def _s6_frame_distinct() -> pd.DataFrame:
    """국면6 ∧ 마지막 봉 gc3, 봉마다 종가·ATR 이 다르다(ATR/종가는 전부 2% — 밴드 통과)."""
    df = _full([1, 1, 1, 6, 6], [0, 0, 0, 0, 1])
    df["close"] = [9000.0, 9500.0, 10000.0, 11000.0, 12345.0]
    df["atr"] = [180.0, 190.0, 200.0, 220.0, 246.9]
    return df


@pytest.mark.parametrize("with_today", [False, True], ids=["no_partial", "partial_today"])
async def test_g348_b3_row_tail_is_last_completed_bar(monkeypatch, caplog, with_today):
    """`bar=`/`close=`/`atr=` 는 prepare 가 쓴 **마지막 확정 봉**의 값이다.

    bar = 당일 부분봉을 뺀 뒤의 `usable[0]` 날짜, close/atr = `enriched.iloc[-1]` — 같은 봉을
    보유 stamp(`_candidates[ticker]` 의 `prev_close`/`atr`)도 쓴다. 봉마다 값이 다른 합성으로
    `iloc[-2]`·당일 봉 미제외·`usable[1]` 같은 잘못된 봉 돌연변이(W)를 죽인다.
    """
    from src.engine.strategies.kojiro import KST

    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    frame = _s6_frame_distinct()
    # 탐지기 자기검사 — 마지막 봉과 그 앞 봉이 같으면 이 테스트는 잘못된 봉을 가려내지 못한다.
    assert frame["close"].iloc[-1] != frame["close"].iloc[-2]
    assert frame["atr"].iloc[-1] != frame["atr"].iloc[-2]
    completed = _dated_candles()
    assert completed[0]["stck_bsop_date"] != completed[1]["stck_bsop_date"]

    strat = _mk()
    with freeze_time(_FROZEN_KST):
        today = datetime.now(KST).strftime("%Y%m%d")
        assert today != _LAST_DONE_BAR
        candles = ([{**completed[0], "stck_bsop_date": today}] + completed
                   if with_today else completed)
        await _run_prepare(strat, monkeypatch, scenario=[("S6", None, None)], held=("S6",),
                           candles=candles, frames=[frame])

    rows = _s6_rows(caplog)
    assert [r["ticker"] for r in rows] == ["S6"], rows
    r = rows[0]
    assert r["bar"] == _LAST_DONE_BAR, (
        f"bar={r['bar']} — 마지막 확정 봉({_LAST_DONE_BAR})이 아니다"
        + (" (당일 부분봉을 빼지 않았다)" if r["bar"] == today else ""))
    cand = strat._candidates["S6"]   # 보유 stamp 가 쓴 값 = prepare 가 판정에 쓴 그 봉
    assert (cand["prev_close"], cand["atr"]) == (12345, 246.9)
    assert r["close"] == str(cand["prev_close"]) == "12345", f"close={r['close']}"
    assert r["atr"] == f"{cand['atr']:.2f}" == "246.90", f"atr={r['atr']}"


def test_g348_b10_helper_is_sync_and_awaitless():
    """추가 I/O 0 — 수집 헬퍼는 동기 함수이고 await 0건.

    prepare 의 await 수는 cycle348 기준 7 이었고, cycle363 이 `expected_head =
    await self._resolve_expected_daily_head()` 1건을 gather 전에 더해 **8**이 됐다
    (①′ 일봉 신선도를 직전 영업일 기준으로 — `_workspace/red/cycle363_business_day_freshness_spec.md`
    §2.5). 관측 확장이 아니라 별도 승인 사이클의 신규 await 이다.
    """
    tree = ast.parse(_KOJIRO_PY.read_text(encoding="utf-8"))
    fns = {n.name: n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "_stage6_gc_observe_row" in fns, "미구현: _stage6_gc_observe_row 정의가 없다"
    h = fns["_stage6_gc_observe_row"]
    assert isinstance(h, ast.FunctionDef), "수집 헬퍼가 async 다"
    assert not any(isinstance(x, ast.Await) for x in ast.walk(h))
    prep = fns["prepare"]
    assert sum(isinstance(x, ast.Await) for x in ast.walk(prep)) == 8, (
        "prepare 의 await 수가 바뀌었다 — 관측 확장에 I/O 가 끼었다 "
        "(cycle363 의 `_resolve_expected_daily_head` 1건은 예외로 반영됨)")


def test_g348_b10_no_new_default_params():
    from src.engine.strategies.kojiro import KojiroStrategy
    keys = set(KojiroStrategy.DEFAULT_PARAMS)
    assert len(keys) == 43, f"DEFAULT_PARAMS 키 수가 {len(keys)} — 관측 확장은 키를 더하지 않는다"
    assert not any("stage6" in k or "observe" in k for k in keys)


def _enclosing_trys(tree, target_call_name):
    """target 호출을 감싼 Try 노드들(바깥→안) 과 호출 노드."""
    out = []

    def _walk(node, stack):
        for ch in ast.iter_child_nodes(node):
            st = stack + [ch] if isinstance(ch, ast.Try) else stack
            if isinstance(ch, ast.Call):
                f = ch.func
                nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if nm == target_call_name:
                    out.append((list(st), ch))
            _walk(ch, st)

    _walk(tree, [])
    return out


def _prepare_node():
    tree = ast.parse(_KOJIRO_PY.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "prepare":
            return n
    raise AssertionError("prepare 없음")


def _line_of(prep, pred) -> int:
    for n in ast.walk(prep):
        if pred(n):
            return n.lineno
    raise AssertionError("기준 노드를 못 찾았다")


def test_g348_b4_collect_call_has_own_try():
    """수집 호출은 **자기 try** 안에 있다 — 루프 try(`고지로 prepare 실패`)가 최내곽이면 M5."""
    prep = _prepare_node()
    hits = _enclosing_trys(prep, "_stage6_gc_observe_row")
    assert len(hits) == 1, f"미구현: prepare 안 _stage6_gc_observe_row 호출 {len(hits)}곳 (기대 1)"
    trys, call = hits[0]
    assert len(trys) >= 2, "수집 호출이 루프 try 에 직접 들어 있다 — 자기 try 가 없다"
    inner = trys[-1]
    inner_src = ast.dump(inner)
    assert "고지로 prepare 실패" not in "".join(
        ast.dump(h) for h in inner.handlers), "최내곽 try 가 루프 try 다"
    assert len(inner.body) <= 3 and "has_position" not in inner_src, (
        "수집 try 가 보유 stamp·후속 단계까지 감싼다")
    # 위치: step6(stage_valid_t.append) 직후, 보유 stamp(has_position) 앞.
    after = _line_of(prep, lambda n: isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == "append"
                     and isinstance(n.func.value, ast.Name) and n.func.value.id == "stage_valid_t")
    before = _line_of(prep, lambda n: isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute) and n.func.attr == "has_position")
    assert after < call.lineno < before, (
        f"수집 위치 {call.lineno} 가 step6({after}) 직후·보유 stamp({before}) 앞이 아니다")


# ── B5 — emit 배선 ───────────────────────────────────────────────────────


def test_g348_b5_emit_call_has_own_try_after_observe_macd():
    """leaf 호출은 `observe_macd` 다음·`_scanned_tickers` 대입 앞, **별도 try**, MACD 흡수기."""
    prep = _prepare_node()
    s6 = _enclosing_trys(prep, "observe_macd_stage6")
    assert len(s6) == 1, f"미구현: prepare 안 observe_macd_stage6 호출 {len(s6)}곳 (기대 1)"
    (s6_trys, s6_call), = s6
    (om_trys, om_call), = _enclosing_trys(prep, "observe_macd")
    assert s6_trys and om_trys
    assert s6_trys[-1] is not om_trys[-1], "stage6 leaf 가 observe_macd 와 같은 try 에 있다 (M8)"
    handlers = "".join(ast.dump(h) for h in s6_trys[-1].handlers)
    assert "absorb_macd_call_failure" in handlers
    assert "absorb_band_call_failure" not in handlers
    scanned_line = _line_of(prep, lambda n: isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Attribute) and t.attr == "_scanned_tickers" for t in n.targets)
        and n.lineno > om_call.lineno)
    assert om_call.lineno < s6_call.lineno < scanned_line


async def test_g348_b5_stage6_survives_observe_macd_failure(monkeypatch, caplog):
    """observe_macd 가 터져도 stage6_gc 행은 남는다 — 별도 try 의 행위 증거(M8)."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    boom = _Counter()
    await _run_prepare(_mk(), monkeypatch, macd_stub=boom.raiser)
    assert boom.n == 1
    assert [r["ticker"] for r in _s6_rows(caplog)] == ["S6"], (
        "observe_macd 실패가 stage6_gc 방출까지 삼켰다")


async def test_g348_b5_leaf_failure_traced_with_macd_marker(monkeypatch, caplog):
    """stage6 leaf 호출 실패 흔적은 MACD 마커(`absorb_macd_call_failure`)로 남는다."""
    from src.engine.kojiro_band_observe import MARKER as BAND_MARKER
    caplog.set_level(logging.DEBUG)
    boom = _Counter()
    await _run_prepare(_mk(), monkeypatch, leaf6_stub=boom.raiser)
    assert boom.n == 1, f"미구현: prepare 가 observe_macd_stage6 를 {boom.n}회 불렀다 (기대 1)"
    traces = [r.getMessage() for r in caplog.records if "observer_failed" in r.getMessage()]
    assert any(MACD_MARKER in m for m in traces), f"MACD 마커 흔적 없음 — {traces}"
    assert not any(BAND_MARKER in m for m in traces), "밴드 마커로 오귀인"


# ── B9 — 매매 무변경 ────────────────────────────────────────────────────


@pytest.mark.parametrize("held", [(), ("S6",)])
async def test_g348_b9_identical_when_collect_raises(monkeypatch, held):
    """🔴 수집 헬퍼가 터져도 매매 산출 완전 동일 — 루프 try 로 새면 S6 보유 stamp·
    step7 탈락 기록이 스킵돼 차분이 생긴다(M5)."""
    ok = await _run_prepare(_mk(), monkeypatch, held=held)
    boom = _Counter()
    broken = await _run_prepare(_mk(), monkeypatch, held=held, collect_stub=boom.raiser)
    assert boom.n >= 1, (
        f"미구현: prepare 가 _stage6_gc_observe_row 를 부르지 않는다 (호출 {boom.n}회)")
    assert ok == broken, "수집 헬퍼 예외가 prepare 매매 산출을 바꿨다"
    if held:
        assert "S6" in broken["candidates"] and "S6" in broken["held_stage3"]


async def test_g348_b9_identical_when_leaf_raises(monkeypatch):
    ok = await _run_prepare(_mk(), monkeypatch, held=("S6",))
    boom = _Counter()
    broken = await _run_prepare(_mk(), monkeypatch, held=("S6",), leaf6_stub=boom.raiser)
    assert boom.n == 1, f"미구현: prepare 가 observe_macd_stage6 를 {boom.n}회 불렀다"
    assert ok == broken, "stage6 leaf 예외가 prepare 매매 산출을 바꿨다"


async def test_g348_b9_step7_rejects_stage6(monkeypatch):
    """funnel step7 탈락 목록에 S6 가 `스테이지 6` 사유로 남는다(확장 전과 동일)."""
    out = await _run_prepare(_mk(), monkeypatch)
    step7 = [c for c in out["funnel"] if "스테이지 1 + EMA 5/20/40 모두 우상향" in c]
    assert step7 and "'S6'" in step7[0] and "스테이지 6" in step7[0]


# ── B9 골든 — 확장 전 코드(HEAD 2087ad3)로 `_SCENARIO` 를 돌려 도출한 고정값 ──────────
#
# 차분 비교(`b9_identical_*`)는 정상 실행과 스텁 실행이 **같은 코드**를 돌리므로, 수집 try
# 바깥(step6 직후)에 심은 돌연변이는 양쪽에 똑같이 들어가 차분이 0 이 된다(Xc4·Xc6 SURVIVE
# 실측). 아래 값은 `git show 2087ad3:src/engine/strategies/kojiro.py` 를 스크래치에 두고
# 같은 시나리오로 돌려 얻었고, 현재 트리와 byte 동일함을 확인했다. 값을 고칠 때는 반드시
# 확장 전 코드로 다시 도출한다 — 현재 코드의 출력을 복사해 넣으면 이 가드는 공허해진다.

_GOLDEN_STATS = {
    "universe_union": 0, "universe_candidates": 0, "universe_filtered": 0,
    "candle_fetch_ok": 5, "band_pass": 5, "stage_valid_pass": 5,
    "stage1_uptrend_pass": 2, "strict_entry_pass": 2, "final_prepared": 2,
}

_ALL5 = ["T1", "S6", "N6", "F5", "C1"]
_GOLDEN_FUNNEL = [
    (1, _ALL5, []), (2, _ALL5, []), (3, _ALL5, []), (4, _ALL5, []), (5, _ALL5, []),
    (6, _ALL5, []),
    (7, ["T1", "C1"], [("S6", "스테이지 6 / 3선우상향 True"),
                       ("N6", "스테이지 6 / 3선우상향 True"),
                       ("F5", "스테이지 5 / 3선우상향 True")]),
    (8, ["T1", "C1"], []),
    (9, ["T1", "C1"], []),
]

_EMA = {"ema_s": 9900.0, "ema_m": 9800.0, "ema_l": 9700.0}
_GOLDEN_CAND = {
    "T1": {"prev_close": 10000, "atr": 200.0, "stage": 1, **_EMA, "atr_ratio": 0.02,
           "sector": "미분류", "score": 0.7},
    "C1": {"prev_close": 10000, "atr": 200.0, "stage": 1, **_EMA, "atr_ratio": 0.02,
           "sector": "미분류", "score": 0.3},
    # 보유 stamp 만 받은 종목 — sector·score 가 없다(후보 등록 경로가 아니다).
    "S6": {"prev_close": 10000, "atr": 200.0, "stage": 6, **_EMA, "atr_ratio": 0.02},
}

_GOLDEN_BY_HELD = {
    (): {"scanned": ["T1", "C1"], "cand_keys": ["T1", "C1"], "held_stage3": {}},
    ("S6",): {"scanned": ["T1", "C1", "S6"], "cand_keys": ["T1", "S6", "C1"],
              "held_stage3": {"S6": False}},
}


@pytest.mark.parametrize("mode", ["normal", "collect_raises", "leaf_raises"])
@pytest.mark.parametrize("held", [(), ("S6",)])
async def test_g348_b9_golden_matches_pre_extension(monkeypatch, held, mode):
    """🔴 매매 산출이 확장 전 코드의 골든과 **완전 일치** — 정상·수집 헬퍼 raise·leaf raise 셋 다.

    stats 전체 dict(`last_run_at` 제외) · stats 키 집합(= `_empty_scan_stats()`) ·
    `get_scanned_tickers()` 순서 · `_candidates` 키 순서·거래 필드 · funnel 9단계 생존/탈락 ·
    `_held_stage3` 플래그 · `_bought_today`. Xc4(국면6 이면 `stage_valid_pass` 가산)·Xc6(새 stats
    키)를 죽인다 — 차분 비교로는 못 잡는 돌연변이다.
    """
    from src.engine.strategies.kojiro import _empty_scan_stats

    stubs = {}
    if mode == "collect_raises":
        stubs["collect_stub"] = _Counter().raiser
    elif mode == "leaf_raises":
        stubs["leaf6_stub"] = _Counter().raiser
    out = await _run_prepare(_mk(), monkeypatch, held=held, **stubs)
    want = _GOLDEN_BY_HELD[held]

    assert out["stats_keys"] == set(_empty_scan_stats()), (
        f"stats 키 집합이 바뀌었다: {sorted(out['stats_keys'] ^ set(_empty_scan_stats()))}")
    assert out["stats"] == _GOLDEN_STATS
    assert out["scanned"] == want["scanned"]
    assert list(out["candidates"]) == want["cand_keys"]
    assert out["cand_fields"] == {t: _GOLDEN_CAND[t] for t in want["cand_keys"]}
    assert out["funnel_steps"] == _GOLDEN_FUNNEL
    assert out["held_stage3_flag"] == want["held_stage3"]
    assert out["bought"] == set()


# ── B6/B7/B8 — leaf 단위 ────────────────────────────────────────────────


def test_g348_b7_limit_constant():
    assert getattr(leaf, "STAGE6_GC_DAILY_LIMIT", None) == 60


def test_g348_observe_macd_signature_unchanged():
    assert list(inspect.signature(leaf.observe_macd).parameters) == [
        "macd_raw", "ranked_final", "held_only"]


def test_g348_b6_leaf_row_values(caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn({"A": _row15(), "B": _row15(m2_up=False, close="x", atr=None),
        "C": _row15(gc3=False)})
    rows = {r["ticker"]: r for r in _s6_rows(caplog)}
    a, b, c = rows["A"], rows["B"], rows["C"]
    assert a["role"] == "stage6_gc"
    assert (a["m1"], a["m3"], a["s3"], a["hist3"]) == ("1.00", "1.00", "0.50", "0.50")
    assert (a["rule6"], a["rule5"], a["rule4"], a["all_macd_up"]) == ("1", "0", "0", "1")
    assert (a["bar"], a["close"], a["atr"]) == ("20250101", "10000", "200.00")
    assert b["rule6"] == "0" and b["all_macd_up"] == "0", "rule6 = gc3 ∧ all_up"
    assert (b["close"], b["atr"]) == ("-", "-"), "비수치는 `-`"
    # C = 국면6 ∧ 3 MACD 모두 우상향인데 교차가 없다 — gc3 항만 다르다(Xk: 식에서 gc3 를 빼면 1).
    assert c["all_macd_up"] == "1" and c["stage"] == "6"
    assert c["gc3"] == "0"
    assert (c["rule6"], c["rule5"], c["rule4"]) == ("0", "0", "0"), (
        "rule6 = gc3 ∧ all_up ∧ stage==6 — gc3 없이 발화했다")


def test_g348_b6_leaf_keys_match_base_plus_tail(caplog):
    """필드 순서의 정본은 observe_macd 의 실제 출력이다 — 그 뒤에 bar/close/atr 만 붙는다."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    leaf.observe_macd({"Z": _row12(stage=1)}, ["Z"], [])
    fn({"Y": _row15()})
    lines = _macd_lines(caplog)
    base = [m for m in lines if " role=candidate " in m][0]
    s6 = [m for m in lines if " role=stage6_gc " in m][0]
    assert _keys_in_order(base) == _BASE_KEYS
    assert _keys_in_order(s6) == _keys_in_order(base) + ["bar", "close", "atr"]


def test_g348_b7_emit_order_is_stash_order(caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn({"Z": _row15(), "A": _row15(), "M": _row15()})
    assert [r["ticker"] for r in _s6_rows(caplog)] == ["Z", "A", "M"]


def test_g348_b7_once_per_ticker_per_day(caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn({"A": _row15()})
    fn({"A": _row15()})
    assert [r["ticker"] for r in _s6_rows(caplog)] == ["A"]


def test_g348_b7_slot_does_not_compete_with_candidate(caplog):
    """키 `(ticker, "macd:stage6_gc")` — 같은 종목의 candidate 행과 슬롯을 다투지 않는다."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    leaf.observe_macd({"A": _row12(stage=1)}, ["A"], [])
    fn({"A": _row15()})
    roles = [_parse(m)["role"] for m in _macd_lines(caplog) if "ticker=A" in m]
    assert roles == ["candidate", "stage6_gc"]


def _batch(prefix: str, n: int) -> dict:
    return {f"{prefix}{i:03d}": _row15() for i in range(n)}


def test_g348_b7_daily_limit_60_and_one_summary(caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn(_batch("K", 65))
    rows = _s6_rows(caplog)
    assert len(rows) == 60, f"일일 상한 60 인데 {len(rows)}줄"
    assert [r["ticker"] for r in rows] == [f"K{i:03d}" for i in range(60)], "삽입 순서 앞 60"
    sums = _summaries(caplog)
    assert sums == [f"{MACD_MARKER} role=stage6_gc cap_reached=1 limit=60 suppressed=5"], sums


def test_g348_b7_summary_line_once_per_day(caplog):
    """요약은 하루 1회 — 재실행 prepare(두 번째 배치)에서 중복 금지(M7)."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn(_batch("K", 65))
    fn(_batch("L", 10))
    assert len(_s6_rows(caplog)) == 60
    assert len(_summaries(caplog)) == 1, f"요약이 {len(_summaries(caplog))}번"


def test_g348_b7_no_summary_under_limit(caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn(_batch("K", 60))
    assert len(_s6_rows(caplog)) == 60
    assert _summaries(caplog) == []


def test_g348_b7_limit_resets_on_kst_date_change(caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    with freeze_time("2026-09-24 00:00:00"):     # KST 09:00
        fn(_batch("K", 65))
    with freeze_time("2026-09-25 00:00:00"):     # 다음 KST 날
        fn(_batch("L", 65))
    assert len(_s6_rows(caplog)) == 120
    assert len(_summaries(caplog)) == 2


def test_g348_b7_reset_hook_clears_counter(caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn(_batch("K", 60))
    reset_kojiro_band_observe_cap()
    fn(_batch("L", 5))
    assert len(_s6_rows(caplog)) == 65, "reset 훅이 일일 상한 카운터를 초기화하지 않았다"


async def test_g348_b7_prepare_rerun_does_not_duplicate(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    await _run_prepare(_mk(), monkeypatch)
    await _run_prepare(_mk(), monkeypatch)
    assert [r["ticker"] for r in _s6_rows(caplog)] == ["S6"]


@pytest.mark.parametrize("bad", [None, "x", 123, [("A", _row15())]])
def test_g348_b8_leaf_never_raises_on_bad_input(bad):
    fn = _need_leaf("observe_macd_stage6")
    assert fn(bad) is None


def test_g348_b8_leaf_skips_non_fifteen_rows(caplog):
    """15원소가 아니면 skip — 12원소(기존 계약) 행도 받지 않는다(M4). 나머지는 계속."""
    caplog.set_level(logging.WARNING, logger=_LEAF_LOGGER)
    fn = _need_leaf("observe_macd_stage6")
    fn({"R12": _row12(), "BAD": (1, 2), "STR": "x", "OK": _row15()})
    assert [r["ticker"] for r in _s6_rows(caplog)] == ["OK"]


def test_g348_b10_leaf_is_awaitless():
    tree = ast.parse(_LEAF_PY.read_text(encoding="utf-8"))
    fns = {n.name: n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "observe_macd_stage6" in fns, "미구현: observe_macd_stage6 정의가 없다"
    f = fns["observe_macd_stage6"]
    assert isinstance(f, ast.FunctionDef)
    assert not any(isinstance(x, ast.Await) for x in ast.walk(f))
    assert isinstance(f.body[-1], ast.Try) or any(isinstance(s, ast.Try) for s in f.body), (
        "never-raise — 본체 전체 try")
