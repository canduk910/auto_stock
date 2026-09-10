# DEST: /Users/koscom/Projects/auto_stock/tests/unit/engine/test_cycle273_kojiro_band_observe.py
"""cycle273 D3 shadow — `[kojiro_band_observe]` 관측 leaf (Red). **행위 변경 0.**

정본 = `_workspace/red/cycle273c_kojiro_rank_restore_spec.md` §4 ·
자문 §5 · 조사 U-C §6. 구조는 `src/engine/kojiro_gap_observe.py`(cycle268) 그대로,
**이름만 band 계열**이다(이름 충돌 실측 — spec §4.2).

RED 예상: 이 파일 전체가 `ModuleNotFoundError`(수집 에러) — leaf 미존재.
Green 이 `src/engine/kojiro_band_observe.py` 를 만들면 수집이 되고 개별 단언이 산다.

## 한 행의 서식 (필드 순서 고정 — 사후 grep 파싱의 계약)

    [kojiro_band_observe] ticker= name= role= rank= bar= close= atr= atr_pct=
                          bw= bw_close_pct= bw_atr= bw_prev1= bw_prev5=
                          exp1= exp5= slope_raw= slope_pct= dist61= score=

## stash 튜플 (12원소, 순서 고정)

    (name, bar, close, atr, bw, bw_prev1, bw_prev5, exp1, exp5, slope_raw, slope_pct, dist61)
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit

from src.engine.kojiro_band_observe import (          # noqa: E402  (RED: 모듈 미존재)
    MARKER,
    absorb_band_call_failure,
    observe_band,
    reset_kojiro_band_observe_cap,
)

_LOGGER_NAME = "src.engine.kojiro_band_observe"

# (name, bar, close, atr, bw, bw_prev1, bw_prev5, exp1, exp5, slope_raw, slope_pct, dist61)
_ROW_A = ("삼천리", "20260910", 100000.0, 2500.0, 300.0, 10.0, 200.0,
          29.0, 0.5, 932.64, 3.1088e-3, 1)
_ROW_B = ("유안타증권", "20260910", 4720.0, 120.0, 8.0, 0.5, 6.0,
          15.0, 0.3333, 17.26, 1.2189e-3, 0)


@pytest.fixture(autouse=True)
def _fresh_cap():
    reset_kojiro_band_observe_cap()
    yield
    reset_kojiro_band_observe_cap()


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(MARKER)]


# ===========================================================================
# G-273-10 — 한 행의 필드 순서·이름 (파싱 계약)
# ===========================================================================

def test_g273_10_field_order_is_fixed(caplog):
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        observe_band({"004690": _ROW_A}, ["004690"], [], scores={"004690": 0.8123})
    lines = _lines(caplog)
    assert len(lines) == 1, f"1행이어야 한다 — 실측 {lines}"
    keys = [tok.split("=", 1)[0] for tok in lines[0][len(MARKER):].split() if "=" in tok]
    assert keys == [
        "ticker", "name", "role", "rank", "bar", "close", "atr", "atr_pct",
        "bw", "bw_close_pct", "bw_atr", "bw_prev1", "bw_prev5",
        "exp1", "exp5", "slope_raw", "slope_pct", "dist61", "score",
    ], f"필드 순서가 계약과 다르다 — 실측 {keys}"
    assert "ticker=004690" in lines[0] and "role=candidate" in lines[0]
    assert "rank=0" in lines[0]
    assert "bar=20260910" in lines[0]


def test_g273_10b_derived_fields_math(caplog):
    """`atr_pct`·`bw_close_pct`·`bw_atr` 는 leaf 가 파생한다(본체 무접촉)."""
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        observe_band({"004690": _ROW_A}, ["004690"], [], scores={"004690": 0.5})
    line = _lines(caplog)[0]
    # atr_pct = 2500/100000 = 2.50%  ·  bw_close_pct = 300/100000*100 = 0.30%
    # bw_atr   = 300/2500 = 0.12
    assert "atr_pct=2.50" in line
    assert "bw_close_pct=0.30" in line
    assert "bw_atr=0.12" in line


def test_g273_10c_zero_denominator_renders_dash(caplog):
    """close·atr 이 0 이면 파생 필드는 `-` — 관측이 산술로 죽지 않는다."""
    row = ("X", "20260910", 0.0, 0.0, 5.0, 1.0, 2.0, 4.0, 1.5, 1.0, 0.0, 2)
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        observe_band({"000000": row}, ["000000"], [], scores={})
    line = _lines(caplog)[0]
    assert "atr_pct=-" in line and "bw_close_pct=-" in line and "bw_atr=-" in line
    assert "score=-" in line, "점수 미상은 `-` (0.0 으로 위장 금지)"


# ===========================================================================
# G-273-11 — role / rank / 방출 순서
# ===========================================================================

def test_g273_11_role_rank_and_emit_order(caplog):
    """emit 순서 = `ranked_final + held_only` = **그날 매수 처리 순서**."""
    band_raw = {"AAA": _ROW_A, "BBB": _ROW_B, "HHH": _ROW_A}
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        observe_band(band_raw, ["BBB", "AAA"], ["HHH"],
                     scores={"BBB": 0.9, "AAA": 0.4})
    lines = _lines(caplog)
    assert len(lines) == 3
    assert "ticker=BBB" in lines[0] and "rank=0" in lines[0] and "role=candidate" in lines[0]
    assert "ticker=AAA" in lines[1] and "rank=1" in lines[1]
    assert "ticker=HHH" in lines[2] and "role=held" in lines[2] and "rank=-" in lines[2], (
        "보유 전용 행은 순위가 없다 — `-` 로 남기고 0 으로 위장하지 않는다"
    )


# ===========================================================================
# C13 / G-273-12 — cap 키 = (ticker, role), 1행/(ticker,role)/일
# ===========================================================================

def test_c13_g273_12_cap_key_is_ticker_and_role(caplog):
    band_raw = {"AAA": _ROW_A}
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        observe_band(band_raw, ["AAA"], [], scores={"AAA": 0.1})
        observe_band(band_raw, ["AAA"], [], scores={"AAA": 0.1})   # 같은 날 재호출
    assert len(_lines(caplog)) == 1, "같은 (ticker, role) 은 하루 1행"

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        observe_band(band_raw, [], ["AAA"], scores={})              # 같은 종목, role 다름
    assert len(_lines(caplog)) == 1, (
        "role 이 다르면 별도 행 — '같은 종목이 후보이면서 보유' 라는 사실이 "
        "ticker 단독 키로는 지워진다"
    )


def test_g273_12b_reset_hook_clears_cap(caplog):
    band_raw = {"AAA": _ROW_A}
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        observe_band(band_raw, ["AAA"], [], scores={})
        reset_kojiro_band_observe_cap()
        observe_band(band_raw, ["AAA"], [], scores={})
    assert len(_lines(caplog)) == 2


# ===========================================================================
# G-273-13 — never-raise + 실패 흔적(observer_trace)
# ===========================================================================

@pytest.mark.parametrize("bad", [
    {"AAA": None},
    {"AAA": ("too", "short")},
    {"AAA": ("n", "b", "close-not-a-number", 1, 2, 3, 4, 5, 6, 7, 8, 9)},
    None,
])
def test_g273_13_never_raises(bad, caplog):
    """망가진 입력에도 예외가 밖으로 나가지 않는다 — 관측은 prepare 를 끊지 않는다."""
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        assert observe_band(bad, ["AAA"], [], scores={}) is None


def test_g273_13b_failure_leaves_a_trace(caplog):
    """실패는 **침묵하지 않는다** — `observer_trace` WARNING 1회/(marker,key)/일.

    무흔적 `pass` 는 cycle258 카드 #5 가 금지한 형태다. 결측이 '오염 없음' 으로
    오독되는 것을 막는 유일한 채널이 이 WARNING 이다.
    """
    with caplog.at_level(logging.WARNING):
        absorb_band_call_failure("prepare")
    warns = [r.getMessage() for r in caplog.records
             if r.levelno >= logging.WARNING and MARKER in r.getMessage()]
    assert len(warns) >= 1, "흡수기가 아무 흔적도 남기지 않았다"


def test_g273_13c_absorber_never_raises():
    """흡수기는 호출 지점 `except` 절에서 불린다 — 여기서 던지면 매수가 끊긴다."""
    assert absorb_band_call_failure(object()) is None
    assert absorb_band_call_failure(None) is None


# ===========================================================================
# 검증 라운드2 [MEDIUM] — 배치 레벨 실패도 흔적을 남긴다 (cycle258 카드 #5)
# ===========================================================================

def test_g273_14_batch_level_failure_leaves_a_trace(caplog):
    """`ranked_final` 이 순회 불가(`enumerate(object())` → `TypeError`)면
    **배치 레벨** `except Exception: trace_observer_failure(...)` 가 발동한다.

    이 줄을 `pass` 로 바꿔도(뮤테이션) 전 스위트가 초록이던 결함 — `observe_band`
    가 여전히 `None` 을 반환(never-raise 유지)하면서도 WARNING 흔적이 **있어야**
    관측기 자기 실패가 '변화 없음'으로 오독되지 않는다.
    """
    with caplog.at_level(logging.WARNING):
        assert observe_band({}, object(), [], scores={}) is None
    warns = [r.getMessage() for r in caplog.records
             if r.levelno >= logging.WARNING and MARKER in r.getMessage()]
    assert len(warns) >= 1, "배치 레벨 실패가 흔적을 남기지 않았다"


def test_g273_15_per_ticker_failure_does_not_abort_the_batch(caplog):
    """한 ticker 의 stash 조회가 터져도(예: unhashable ticker → `dict.get` 이
    `TypeError`) **그 ticker 만** 건너뛰고 나머지는 정상 방출된다.

    docstring 의 '개별 ticker 실패는 그 ticker 만 스킵, 나머지는 계속 처리한다'
    계약 — per-ticker `except Exception: continue` 를 `raise` 로 바꾸면(뮤테이션)
    이 예외가 배치 전체를 끊어 `GOOD` 행까지 사라진다.
    """
    band_raw = {"GOOD": _ROW_A}
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        assert observe_band(band_raw, [["unhashable"], "GOOD"], [], scores={}) is None
    lines = _lines(caplog)
    assert len(lines) == 1 and "ticker=GOOD" in lines[0], (
        f"불량 ticker(unhashable) 하나가 전체 배치를 막았다 — 실측 {lines}"
    )


# ===========================================================================
# C11 (G-273-9) — 관측 차분: leaf 가 터져도 prepare 산출이 완전히 동일
# ===========================================================================

async def _run_prepare(strat, monkeypatch, *, break_leaf: bool):
    from unittest.mock import AsyncMock

    import pandas as pd
    import src.engine.strategies.kojiro as kmod
    from src.db import stock_master_daily as smd

    def _full(stage_series, macd3, band_width, *, close=10000.0, atr=200.0):
        n = len(stage_series)
        return pd.DataFrame({
            "close": [close] * n, "atr": [atr] * n, "stage": list(stage_series),
            "ema_s": [9900.0] * n, "ema_m": [9800.0] * n, "ema_l": [9700.0] * n,
            "ema_s_up": [True] * n, "ema_m_up": [True] * n, "ema_l_up": [True] * n,
            "macd3": [float(x) for x in macd3],
            "band_width": [float(x) for x in band_width],
        })

    ordered = [
        ("T1", _full([4, 4, 4, 6, 1], [0, 0, 2, 4, 6], [10, 10, 12, 14, 16])),
        ("T2", _full([4, 4, 6, 1, 1], [0, 0, 1, 2, 3], [10, 10, 11, 12, 13])),
    ]
    tickers = [t for t, _ in ordered]
    monkeypatch.setattr(strat, "_scan_universe", AsyncMock(return_value=tickers))
    monkeypatch.setattr(strat, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=(tickers, [])))
    monkeypatch.setattr(strat, "_fetch_sector", AsyncMock(return_value="미분류"))
    monkeypatch.setattr(smd, "get_recent_daily_normalized", AsyncMock(return_value=[{
        "stck_bsop_date": "20250101", "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    } for _ in range(85)]))
    dfs = iter([df for _, df in ordered])
    monkeypatch.setattr(kmod, "enrich", lambda df, cfg: next(dfs))
    if break_leaf:
        def _boom(*a, **k):
            raise RuntimeError("leaf exploded")
        monkeypatch.setattr(kmod, "observe_band", _boom, raising=False)
    await strat.prepare()
    return (
        list(strat.get_scanned_tickers()),
        {t: repr(v) for t, v in strat._candidates.items()},
        set(strat._bought_today),
    )


async def test_c11_g273_9_prepare_identical_when_leaf_raises(monkeypatch):
    """leaf 를 raise 스텁으로 갈아끼워도 `get_scanned_tickers()` · `_candidates`
    (`score` 를 `repr(float)` 수준까지) · `_bought_today` 가 **완전 동일**하다.

    이것이 '행위 무영향' 증명 5중 중 가장 강한 B(차분)다.
    """
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategy_base import StrategyConfig

    def _mk():
        return KojiroStrategy(
            StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))

    ok = await _run_prepare(_mk(), monkeypatch, break_leaf=False)
    broken = await _run_prepare(_mk(), monkeypatch, break_leaf=True)
    assert ok == broken, (
        "관측기 예외가 prepare 산출을 바꿨다 — 이 사이클의 제1 계약 위반"
    )


def _parse_row(line: str) -> dict[str, str]:
    """`[kojiro_band_observe] k=v k=v ...` 한 행을 `{key: value}` 로 분해."""
    return dict(tok.split("=", 1) for tok in line[len(MARKER):].split() if "=" in tok)


async def test_c11b_prepare_emits_the_marker(monkeypatch, caplog):
    """배선 확인 — `prepare` 가 실제로 한 행 이상 남긴다(RED: 미배선).

    ⚠️ 위 차분 테스트만으로는 '아예 안 부른다' 도 통과한다. 이 테스트가 그 구멍을 막는다.

    검증 라운드3 [MEDIUM] 추가 — `observe_band(..., scores=scores)` 배선 무검정
    (뮤테이션 `scores=scores` → `scores=None` ESCAPED). `score=` 가 `-` 로 위장되지
    않고 `_candidates[ticker]["score"]` 와 **문자열 비트 일치**하며, `rank` 오름차순을
    따라 `score` 가 비증가임을 단언한다 — `scores=None` 이면 전 행이 `score=-` 로
    떨어져 이 세 단언이 즉시 KILL 한다.
    """
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategy_base import StrategyConfig

    strat = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await _run_prepare(strat, monkeypatch, break_leaf=False)
    lines = _lines(caplog)
    assert len(lines) >= 2, f"후보 2종목의 관측 행이 없다 — 실측 {lines}"
    assert all("bar=" in ln and "exp1=" in ln and "exp5=" in ln for ln in lines), (
        "exp1(현행식)·exp5(복원식)를 **한 행에 함께** 남겨야 전후 대조가 성립한다"
    )

    parsed = [_parse_row(ln) for ln in lines]
    assert all(p["score"] != "-" for p in parsed), (
        f"score= 가 `-` 로 나왔다 — `observe_band(..., scores=scores)` 배선이 끊겼다는 "
        f"뜻이다. 실측 {parsed}"
    )
    for p in parsed:
        expected_score = strat._candidates[p["ticker"]]["score"]
        assert p["score"] == str(expected_score), (
            f"{p['ticker']} 행의 score={p['score']} 가 _candidates 의 "
            f"score={expected_score} 와 어긋난다 — leaf 에 넘어간 scores 딕셔너리가 "
            "prepare 가 실제로 확정한 것과 다르다는 뜻이다"
        )
    ranked = sorted(
        ((int(p["rank"]), float(p["score"])) for p in parsed if p["rank"] != "-"),
        key=lambda pair: pair[0],
    )
    for i in range(1, len(ranked)):
        assert ranked[i - 1][1] >= ranked[i][1], (
            f"rank 오름차순인데 score 가 비증가가 아니다 — emit 순서와 정렬 기준이 "
            f"어긋났다. 실측 {ranked}"
        )


# ===========================================================================
# 검증 라운드3 [MEDIUM] — `bar_date = usable[0].get("stck_bsop_date")` 무검정
# (뮤테이션 `usable[0]` → `candles[0]` ESCAPED)
# ===========================================================================

async def test_g273_x_bar_date_uses_usable_not_candles_head(monkeypatch, caplog):
    """오늘 부분봉이 낀 날(`prev_idx=1`) — `bar=` 는 `candles[0]`(오늘) 이 아니라
    **`usable[0]`**(= `candles[1]`, 드롭 이후 첫 완성봉) 이어야 한다.

    기존 모든 픽스처는 스텁 `stck_bsop_date="20250101"` 이 실제 오늘과 결코 같지
    않아 `prev_idx` 가 항상 0 이었다 — `usable[0] is candles[0]` 이 우연히 성립해
    `usable[0]` → `candles[0]` 뮤테이션이 무증상이었다(ESCAPED 실측). 이 테스트는
    `candles[0]` 을 실제 "오늘"(`datetime.now(KST)`) 로 만들어 두 식을 분리한다.
    """
    from datetime import datetime as _dt

    from src.engine.strategies.kojiro import KST as _KOJIRO_KST
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategy_base import StrategyConfig

    from unittest.mock import AsyncMock
    import pandas as pd
    import src.engine.strategies.kojiro as kmod

    today_str = _dt.now(_KOJIRO_KST).strftime("%Y%m%d")
    strat = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    df = pd.DataFrame({
        "close": [10000.0] * 5, "atr": [200.0] * 5, "stage": [4, 4, 4, 6, 1],
        "ema_s": [9900.0] * 5, "ema_m": [9800.0] * 5, "ema_l": [9700.0] * 5,
        "ema_s_up": [True] * 5, "ema_m_up": [True] * 5, "ema_l_up": [True] * 5,
        "macd3": [0.0, 0.0, 2.0, 4.0, 6.0], "band_width": [10.0, 10.0, 12.0, 14.0, 16.0],
    })
    monkeypatch.setattr(strat, "_scan_universe", AsyncMock(return_value=["T1"]))
    monkeypatch.setattr(strat, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=(["T1"], [])))
    monkeypatch.setattr(strat, "_fetch_sector", AsyncMock(return_value="미분류"))
    candles = [{
        "stck_bsop_date": today_str, "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    }] + [{
        "stck_bsop_date": "19991231" if i == 0 else "19990101",
        "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    } for i in range(84)]
    from src.db import stock_master_daily as smd
    monkeypatch.setattr(smd, "get_recent_daily_normalized", AsyncMock(return_value=candles))
    monkeypatch.setattr(kmod, "enrich", lambda d, cfg: df)
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await strat.prepare()
    lines = _lines(caplog)
    assert len(lines) == 1, f"T1 후보 관측 행이 정확히 1개여야 한다 — 실측 {lines}"
    assert "bar=19991231" in lines[0], (
        f"usable[0](드롭 이후 첫 완성봉) 이 아니라 candles[0](오늘 부분봉) 을 썼다 — "
        f"실측 {lines[0]}"
    )
    assert f"bar={today_str}" not in lines[0]


async def test_g273_xb_bar_date_no_partial_bar_today(monkeypatch, caplog):
    """오늘 부분봉이 없는 날(`prev_idx=0`) — `bar=` 는 여전히 `candles[0]`
    (= `usable[0]`, 이 경우 둘이 같다) 이어야 한다. 위 테스트의 대조 케이스.
    """
    from unittest.mock import AsyncMock

    import pandas as pd
    import src.engine.strategies.kojiro as kmod
    from src.db import stock_master_daily as smd
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategy_base import StrategyConfig

    strat = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    df = pd.DataFrame({
        "close": [10000.0] * 5, "atr": [200.0] * 5, "stage": [4, 4, 4, 6, 1],
        "ema_s": [9900.0] * 5, "ema_m": [9800.0] * 5, "ema_l": [9700.0] * 5,
        "ema_s_up": [True] * 5, "ema_m_up": [True] * 5, "ema_l_up": [True] * 5,
        "macd3": [0.0, 0.0, 2.0, 4.0, 6.0], "band_width": [10.0, 10.0, 12.0, 14.0, 16.0],
    })
    monkeypatch.setattr(strat, "_scan_universe", AsyncMock(return_value=["T1"]))
    monkeypatch.setattr(strat, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=(["T1"], [])))
    monkeypatch.setattr(strat, "_fetch_sector", AsyncMock(return_value="미분류"))
    candles = [{
        "stck_bsop_date": "19991230", "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    } for _ in range(85)]
    monkeypatch.setattr(smd, "get_recent_daily_normalized", AsyncMock(return_value=candles))
    monkeypatch.setattr(kmod, "enrich", lambda d, cfg: df)
    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        await strat.prepare()
    lines = _lines(caplog)
    assert len(lines) == 1
    assert "bar=19991230" in lines[0]


# ===========================================================================
# 검증 라운드3 [HIGH] — `_band_observe_row` 의 `except Exception:` 이 실제
# `prepare()` 실행 안에서도 후보 처리를 침범하지 않는다 (행위 반쪽)
#
# `_rank_candidate_components` 는 held-only 티커(strict entry 자격 미달)에서는
# **아예 호출되지 않는다** — 실측: `bw.iloc[-6:-1].mean()`(그쪽 분모)이 `pi` 를
# 항상 포함해, candidate 역할에서는 band_width 를 자연 오염시키면 `_rank_
# candidate_components` 가 먼저 터져 `_band_observe_row` 를 격리 검증할 수 없다
# (그 자리는 `_run_prepare(break_leaf=True)`(C11)가 이미 leaf 전체 폭발로
# 덮는다). held 역할은 이 공유 계산을 거치지 않으므로 `_band_observe_row` 단독
# 예외 흡수를 오염 없이 분리하는 유일한 경로다.
# ===========================================================================

async def _run_prepare_with_held(strat, monkeypatch, *, corrupt_held_band: bool):
    from unittest.mock import AsyncMock

    import pandas as pd
    import src.engine.strategies.kojiro as kmod
    from src.db import stock_master_daily as smd
    from src.engine.strategy_base import Position

    def _cand(stage_series, macd3, band_width, *, close=10000.0, atr=200.0):
        n = len(stage_series)
        return pd.DataFrame({
            "close": [close] * n, "atr": [atr] * n, "stage": list(stage_series),
            "ema_s": [9900.0] * n, "ema_m": [9800.0] * n, "ema_l": [9700.0] * n,
            "ema_s_up": [True] * n, "ema_m_up": [True] * n, "ema_l_up": [True] * n,
            "macd3": [float(x) for x in macd3],
            "band_width": [float(x) for x in band_width],
        })

    def _held(*, corrupt: bool):
        n = 5
        bw = pd.Series(["bad"] * n) if corrupt else pd.Series([10.0] * n)
        return pd.DataFrame({
            "close": [10000.0] * n, "atr": [200.0] * n, "stage": [3] * n,  # 스테이지3 → step7 자연 탈락
            "ema_s": [9900.0] * n, "ema_m": [9800.0] * n, "ema_l": [9700.0] * n,
            "ema_s_up": [True] * n, "ema_m_up": [True] * n, "ema_l_up": [True] * n,
            "macd3": [0.0] * n, "band_width": bw,
        })

    ordered = [
        ("T1", _cand([4, 4, 4, 6, 1], [0, 0, 2, 4, 6], [10, 10, 12, 14, 16])),
        ("T2", _cand([4, 4, 6, 1, 1], [0, 0, 1, 2, 3], [10, 10, 11, 12, 13])),
        ("HELD", _held(corrupt=corrupt_held_band)),
    ]
    tickers = [t for t, _ in ordered]
    strat.state.positions["HELD"] = Position(
        ticker="HELD", buy_price=10000, quantity=10, order_no="X1", strategy_id="kojiro")
    monkeypatch.setattr(strat, "_scan_universe", AsyncMock(return_value=tickers))
    monkeypatch.setattr(strat, "_apply_master_block_filter_in_prepare",
                        AsyncMock(return_value=(tickers, [])))
    monkeypatch.setattr(strat, "_fetch_sector", AsyncMock(return_value="미분류"))
    monkeypatch.setattr(smd, "get_recent_daily_normalized", AsyncMock(return_value=[{
        "stck_bsop_date": "20250101", "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    } for _ in range(85)]))
    dfs = iter([df for _, df in ordered])
    monkeypatch.setattr(kmod, "enrich", lambda d, cfg: next(dfs))
    await strat.prepare()
    return strat


async def test_c17_band_observe_row_except_isolated_to_held_role(monkeypatch, caplog):
    """held-only 티커(`_rank_candidate_components` 미도달)에서 `band_width` 가
    비수치여도 `_band_observe_row` 의 `except Exception:` 이 흡수해 **후보 처리에
    전혀 침범하지 않는다**.

    단언 3중: (a) "고지로 prepare 실패" WARNING **0건**(예외가 밖으로 새면 이
    로그가 남는다 — 이것이 뮤테이션(`except KeyError:`)을 직접 KILL 하는 신호),
    (b) `get_scanned_tickers()` 오염 없이 동일, (c) `stats["final_prepared"]`
    (candidate 2종 카운트) 동일.
    """
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategy_base import StrategyConfig

    def _mk():
        return KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))

    with caplog.at_level(logging.WARNING):
        clean = await _run_prepare_with_held(_mk(), monkeypatch, corrupt_held_band=False)
    assert not any("고지로 prepare 실패" in r.getMessage() for r in caplog.records)
    clean_scanned = list(clean.get_scanned_tickers())
    clean_final = clean.get_scan_stats()["final_prepared"]

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        dirty = await _run_prepare_with_held(_mk(), monkeypatch, corrupt_held_band=True)
    dirty_scanned = list(dirty.get_scanned_tickers())
    dirty_final = dirty.get_scan_stats()["final_prepared"]

    assert not any("고지로 prepare 실패" in r.getMessage() for r in caplog.records), (
        "band_width 비수치가 `_band_observe_row` 밖으로 새어 `prepare` 의 outer "
        "except 를 건드렸다 — `except Exception:` 폴백이 무력화됐다는 뜻이다"
    )
    assert dirty_scanned == clean_scanned, (
        f"후보 집합/순서가 오염됐다 — {dirty_scanned} vs {clean_scanned}"
    )
    assert dirty_final == clean_final == 2, (
        f"final_prepared 가 오염됐다 — {dirty_final} vs {clean_final}"
    )
    assert "HELD" in dirty_scanned
