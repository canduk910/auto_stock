# DEST: /Users/koscom/Projects/auto_stock/tests/unit/engine/strategies/test_cycle273_kojiro_rank_restore.py
"""cycle273 D3 — 고지로 후보 순위 성분 **원설계 복원** (Red).

정본 = `_workspace/red/cycle273c_kojiro_rank_restore_spec.md` ·
자문 `_workspace/domain_consult/cycle273_kojiro_rank_restore_20260910.md` §3·§10 ·
조사 `_workspace/analysis/2026-09-10_cycle273_UC_kojiro_rank.md` §2·§3 ·
원설계 정본 `_workspace/kojiro_ma/kojiro/screener.py:113-120,134-141`.

복원 대상은 `KojiroStrategy._rank_candidate_components` 의 성분 ①② **두 개뿐**이다.

    ① macd3_slope_pct = (macd3[-1] - macd3[-4]) / _RANK_LOOKBACK / close[-1]
       (현행은 `/3` 도 `/close` 도 없는 **원(₩)** 값 → 사실상 주가 순위표)
    ② band_expansion  = bw[-1] / mean(bw[-6:-1]) - 1,  분모 <= 0 이면 0.0
       (현행은 분모가 **단일봉 bw[-4] + 1e-9** → 6→1 직후 bw≈0 에서 폭발)
    ③ 신선도는 **복원 대상이 아니다** — `within - dist61` 은 원설계 `-fresh_days` 의
       양의 아핀 변환이고 min-max 는 아핀 불변이라 정규화값이 이미 동일하다.

가중치(0.4/0.3/0.3) · `_score_candidates` · 자격 게이트 · 청산은 **무접촉**이다.

## 이 파일이 '현행 식' 을 사본으로 들고 있는 이유

C1·C3 은 "무엇을 고쳤는가" 를 **두 값을 나란히 놓아** 기록하라는 계약이다(자문 §10.1).
복원 뒤 현행 식은 프로덕션에서 사라지므로, 그 식의 **동결 사본**(`_legacy_components`)을
테스트 안에 둔다. 사본은 프로덕션을 부르지 않으므로 Green 이후에도 영원히 초록이고,
값이 나란히 남는 것이 이 사본의 유일한 목적이다.

RED 예상: C1·C3·C4·C6·C7·C8 = FAIL (현행 식). C2·C5·C9 = PASS(현행에서도 성립하는
안전 계약 — 복원 뒤에도 성립해야 하므로 함께 둔다).
"""
from __future__ import annotations

import random

import pandas as pd
import pytest

from src.engine.strategies.kojiro import KojiroStrategy, _RANK_LOOKBACK
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


def _mk(**params):
    return KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.1, params=params)
    )


def _df(macd3, band_width, close=10000.0):
    n = len(macd3)
    closes = close if isinstance(close, list) else [float(close)] * n
    return pd.DataFrame({
        "macd3": [float(x) for x in macd3],
        "band_width": [float(x) for x in band_width],
        "close": closes,
    })


# ---------------------------------------------------------------------------
# 현행(HEAD 1df6d7d) 식의 **동결 사본** — 반증 케이스 전용. 프로덕션 미호출.
# ---------------------------------------------------------------------------
def _legacy_components(enriched) -> tuple[float, float]:
    """`kojiro.py:1207-1211`(HEAD) 성분 ①② 그대로. 복원 후엔 존재하지 않는 식이다."""
    m3 = enriched["macd3"]
    bw = enriched["band_width"]
    li = len(m3) - 1
    pi = max(0, li - _RANK_LOOKBACK)
    slope = float(m3.iloc[li] - m3.iloc[pi])
    prev_bw = float(bw.iloc[pi])
    expansion = (float(bw.iloc[li]) - prev_bw) / (abs(prev_bw) + 1e-9)
    return slope, expansion


def _mm(vals: list[float]) -> list[float]:
    """`_score_candidates._mm` 와 동일한 min-max (중립 임계 1e-12 포함)."""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return [0.5] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


# ===========================================================================
# C1 (G-273-1) — 가격 스케일 불변 + 현행 반증 케이스
# ===========================================================================

def test_c1_g273_1_price_scale_invariance_with_legacy_counterexample():
    """%-동학이 **완전히 같고** 주가만 다른 3종목 → 복원 성분① 정규화 = [0.5,0.5,0.5].

    반증(현행 식) = [0.0, 0.1727…, 1.0] = **종가 순서 그대로**.
    실측 근거: 자문 §2.2 Spearman(성분①, 종가) = **+0.853** (2026-09-10 후보 17종목).
    """
    s = _mk()
    closes = [4720.0, 47950.0, 255000.0]           # 유안타증권 / 중가주 / HD현대
    unit_m3 = [0.0, 0.0, 0.2, 0.4, 0.6]            # 종가 1만원 기준 macd3
    unit_bw = [1.0, 1.0, 1.2, 1.4, 1.6]
    stages = [4, 4, 4, 6, 1]

    restored, legacy = [], []
    for c in closes:
        df = _df([x * c / 10000 for x in unit_m3],
                 [x * c / 10000 for x in unit_bw], close=c)
        slope, _exp, _fr = s._rank_candidate_components(df, stages, within=5)
        restored.append(slope)
        legacy.append(_legacy_components(df)[0])

    # (a) 복원 — 세 종목의 성분① 원값이 같다(부동소수 잔차 ~1e-21)
    assert restored[0] == pytest.approx(restored[2], rel=1e-9), (
        "복원 성분①은 무차원(하루당 가격비율)이라 주가 스케일에 불변이어야 한다. "
        f"실측 {restored}"
    )
    # 잔차가 `_mm` 중립 임계(1e-12)보다 9자릿수 작아 '전부 동값 → 0.5' 로 떨어진다
    assert max(restored) - min(restored) < 1e-12
    assert _mm(restored) == [0.5, 0.5, 0.5], (
        f"복원 정규화가 중립이 아니다 — 실측 {_mm(restored)}"
    )

    # (b) 반증 — 현행 식은 종가 순서를 그대로 재생산한다
    legacy_norm = _mm(legacy)
    assert legacy_norm[0] == pytest.approx(0.0)
    assert legacy_norm[1] == pytest.approx(0.17272654626817963, abs=1e-9)
    assert legacy_norm[2] == pytest.approx(1.0)
    expected_mid = (closes[1] - closes[0]) / (closes[2] - closes[0])
    assert legacy_norm[1] == pytest.approx(expected_mid, abs=1e-12), (
        "현행 정규화값이 정확히 '종가의 min-max' 라는 것이 이 반증의 핵심이다"
    )


# ===========================================================================
# C2 (G-273-8) — `/_RANK_LOOKBACK` 무해성
# ===========================================================================

def test_c2_g273_8_rank_lookback_division_is_order_preserving():
    """`/3` 은 후보 공통 양의 상수 → min-max 뒤 **순위 불변**.

    ⚠️ 자문 C2 원문은 "비트 단위(`==`)" 를 요구하나 **실측이 반증**한다:
    무작위 500 풀 × 2~20 후보에서 `_score_candidates` 산출 681개 값이
    비트 단위로 달랐다(최대 절대차 **2.220446049250313e-16** = 1 ULP,
    순위가 달라진 풀 **0/500**). 부동소수에서 `mm(v/c) == mm(v)` 는 수학적
    항등이지만 IEEE-754 항등은 아니다. 그래서 이 테스트는
      (a) 값이 정확히 표현되는 **고정 풀**에서는 `==` 를,
      (b) 무작위 스윕에서는 **1 ULP 상한 + 순위 완전 동일**을 단언한다.
    (spec §5 open question OQ-1 — 계약 문언 정정 요청)
    """
    s = _mk()
    p = s.config.params

    # (a) 고정 풀 — 2진수로 정확히 표현되는 값만 써서 bitwise 동일을 강제
    div = {"A": ((6.0 / 3) / 10000, 0.5, 4.0),
           "B": ((3.0 / 3) / 10000, 0.25, 2.0),
           "C": (0.0, 0.0, 0.0)}
    nodiv = {"A": (6.0 / 10000, 0.5, 4.0),
             "B": (3.0 / 10000, 0.25, 2.0),
             "C": (0.0, 0.0, 0.0)}
    a, b = s._score_candidates(div, p), s._score_candidates(nodiv, p)
    assert a == b, f"고정 풀에서는 비트 단위로 같아야 한다 — {a} vs {b}"

    # (b) 무작위 스윕 — 순위 완전 동일 + 1 ULP 상한
    worst = 0.0
    for seed in range(200):
        random.seed(seed)
        n = random.randint(2, 20)
        raw_div, raw_nodiv = {}, {}
        for i in range(n):
            close = random.choice([4720.0, 47950.0, 255000.0, 12000.0])
            dm3 = random.uniform(-500.0, 2000.0)
            exp = random.uniform(-1.0, 5.0)
            fresh = float(random.randint(0, 4))
            raw_div[f"T{i}"] = ((dm3 / _RANK_LOOKBACK) / close, exp, fresh)
            raw_nodiv[f"T{i}"] = (dm3 / close, exp, fresh)
        sa = s._score_candidates(raw_div, p)
        sb = s._score_candidates(raw_nodiv, p)
        worst = max(worst, max(abs(sa[k] - sb[k]) for k in sa))
        assert (sorted(sa, key=lambda t: sa[t], reverse=True)
                == sorted(sb, key=lambda t: sb[t], reverse=True)), (
            f"seed={seed} — `/3` 이 순위를 바꿨다. 이건 계약 위반이다"
        )
    assert worst <= 4e-16, f"점수차가 1 ULP 를 넘었다 — 실측 {worst}"


# ===========================================================================
# C3 (G-273-2) — 분모 폭발 대조 (현행 계약 고정 + 복원 유한)
# ===========================================================================

def test_c3_g273_2_denominator_explosion_pair():
    """`bw[-4] ≈ 0` 시리즈 — 현행은 1e3 이상으로 튀고, 복원은 유한하다.

    6→1 전환은 정의상 EMA20 이 EMA40 을 뚫는 사건이라 `bw[-4] ≈ 0` 은
    **예외가 아니라 상시**다(자문 §3.2). 그 자리에서 현행 식은 좁은 밴드에
    만점을 주고 나머지 후보를 전부 0 근처로 눌러 버렸다.
    """
    s = _mk()
    bw = [100.0, 80.0, 60.0, 0.0, 40.0, 60.0, 90.0]     # bw[-4] = 0.0
    df = _df([0.0] * 7, bw)

    legacy_exp = _legacy_components(df)[1]
    assert legacy_exp >= 1e3, (
        f"현행 계약(회귀 고정): 분모 0 → 폭발. 실측 {legacy_exp}"
    )
    assert legacy_exp == pytest.approx(9.0e10, rel=1e-6)

    _slope, restored_exp, _fr = s._rank_candidate_components(df, [6, 1, 1], within=5)
    assert restored_exp == pytest.approx(0.875, abs=1e-9), (
        "복원 분모 = mean(bw[-6:-1]) = mean(60,0,40,60,... ) 계열 → 유한. "
        f"실측 {restored_exp}"
    )
    assert abs(restored_exp) < 10.0


# ===========================================================================
# C4 (G-273-3) — band_prev 가 정확히 0
# ===========================================================================

def test_c4_g273_3_band_prev_exactly_zero_returns_zero():
    """`bw` 전부 0 → 복원은 **0.0**(가드 발동). inf·nan 아님."""
    import math

    s = _mk()
    df = _df([0.0] * 7, [0.0] * 7)
    _slope, exp, _fr = s._rank_candidate_components(df, [6, 1, 1], within=5)
    assert exp == 0.0, f"분모 <= 0 이면 정직하게 0.0 — 실측 {exp}"
    assert math.isfinite(exp)


# ===========================================================================
# C5 (G-273-4) — 짧은 시리즈
# ===========================================================================

@pytest.mark.parametrize("n", [1, 2, 3, 5, 6])
def test_c5_g273_4_short_series_no_exception(n):
    """`len(bw) ∈ {1,2,3,5,6}` → IndexError·ZeroDivisionError 0건.

    `len==1` 은 `iloc[-6:-1]` 이 **빈 슬라이스** → `mean()=nan` → `nan > 0` 이
    False → `0.0`. pandas 의 이 거동이 원설계 표현을 그대로 옮겨도 되는 근거다.
    """
    import math

    s = _mk()
    df = _df([float(i) for i in range(n)], [float(i + 1) for i in range(n)])
    slope, exp, fresh = s._rank_candidate_components(df, [6, 1], within=5)
    assert math.isfinite(slope) and math.isfinite(exp) and math.isfinite(fresh)
    if n == 1:
        assert exp == 0.0, "빈 분모(nan) 는 0.0 으로 떨어져야 한다"


# ===========================================================================
# C6 (G-273-5) — close 가드 (ZeroDivisionError 로 종목이 사라지지 않는다)
# ===========================================================================

@pytest.mark.parametrize("close_col", [
    [0.0] * 5,                 # close == 0  → ZeroDivisionError 후보
    [-100.0] * 5,              # close < 0
    ["x"] * 5,                 # 비수치
])
def test_c6_g273_5_close_guard_component_one_zero(close_col):
    """close 가 못 쓰는 값이면 **성분①만 0.0**, 성분②③ 은 살린다. 예외 전파 0건.

    이 계약의 본체는 "예외가 안 난다" 가 아니라 **"예외가 나면 그 종목이
    후보에서 통째로 사라진다"** 는 것이다 — `ZeroDivisionError` 는
    `except (KeyError, TypeError)` 를 통과해 `prepare` 바깥
    `except Exception: continue`(kojiro.py:456) 로 올라간다 = 자격 변경.
    """
    s = _mk()
    df = _df([0.0, 1.0, 2.0, 3.0, 5.0], [10.0, 10.0, 12.0, 14.0, 15.0], close=close_col)
    slope, exp, fresh = s._rank_candidate_components(df, [4, 5, 6, 1, 1], within=5)
    assert slope == 0.0, f"성분① fail-safe 0.0 — 실측 {slope}"
    assert exp == pytest.approx(0.30434782608695654, abs=1e-12), (
        "성분②는 close 와 무관하므로 살아 있어야 한다(성분 전멸 금지)"
    )
    assert fresh == pytest.approx(4.0)


def test_c6b_g273_5_close_column_missing_uses_existing_failsafe():
    """`close` 열 자체가 없으면 기존 fail-safe `(0.0, 0.0, fresh)` 와 같은 형태.

    `test_rank_components_failsafe_missing_columns`(기존)가 고정한 계약과 같은
    자리다 — `close` 를 그 `try` 에 넣는다는 자문 §3.5 의 선택이 여기서 굳는다.
    """
    s = _mk()
    df = pd.DataFrame({
        "macd3": [0.0, 1.0, 2.0, 3.0, 5.0],
        "band_width": [10.0, 10.0, 12.0, 14.0, 15.0],
    })
    slope, exp, fresh = s._rank_candidate_components(df, [4, 5, 6, 1, 1], within=5)
    assert (slope, exp) == (0.0, 0.0)
    assert fresh == pytest.approx(4.0)


def test_c6c_g273_5_no_exception_matrix():
    """계약 범위 안의 적대 입력에서 **어떤 예외도 밖으로 나가지 않는다**.

    ⚠️ 범위 밖(의도적 제외) = **길이 0 시리즈**(`macd3`/`band_width` 열은 있는데
    행이 0). `m3.iloc[-1]` 이 `IndexError` 를 낸다 — 현행도 동일하며 회귀가 아니다.
    프로덕션은 `KOJIRO_MIN_REQUIRED = 80` 봉을 통과한 뒤에만 이 함수에 도달하므로
    도달 불가다. 여기서 가드를 넓히면 원설계에 없는 방어를 발명하는 것이라
    spec §범위 밖에 기록만 하고 테스트로 강제하지 않는다.
    """
    s = _mk()
    hostile = [
        _df([1.0], [0.0], close=[0.0]),
        _df([1.0, 2.0], [0.0, 0.0], close=[None, None]),
        pd.DataFrame({"macd3": [1.0], "close": [100.0]}),        # band_width 없음
        pd.DataFrame({"band_width": [1.0], "close": [100.0]}),   # macd3 없음
        pd.DataFrame(),                                          # 전 열 부재
    ]
    for df in hostile:
        out = s._rank_candidate_components(df, [6, 1], within=5)
        assert isinstance(out, tuple) and len(out) == 3


def test_c6d_oq5_nonfinite_components_are_neutralized():
    """OQ-5 — `nan`/`inf` 성분은 그 성분만 `0.0` 으로 중립화한다.

    ⚠️ **이 테스트는 사용자/팀장 승인(OQ-5)에 걸려 있다.** 원설계
    `screener.py` 에 없는 **추가 방어**이기 때문이다(자문 §3.5 마지막 행 ·
    §13 미해결 ⑤). 근거 = `nan` 하나가 `_score_candidates` 의 `min`/`max` 를
    오염시켜 **전 후보 점수를 `nan`** 으로 만들고 정렬을 무의미하게 한다.

    **미승인으로 결정되면 이 테스트를 삭제하고 spec §OQ-5 에 그 결정을 남긴다.**
    Green 이 이 가드를 넣지 않은 채 테스트만 남기면 영구 RED 가 된다.
    """
    import math

    s = _mk()
    df = _df([float("nan")] * 5, [float("nan")] * 5)
    slope, exp, fresh = s._rank_candidate_components(df, [6, 1, 1], within=5)
    assert math.isfinite(slope) and math.isfinite(exp), (
        f"비유한 성분이 그대로 새어 나갔다 — slope={slope} exp={exp}. "
        "이 값이 하나라도 nan 이면 그날 후보 전원의 score 가 nan 이 된다"
    )
    assert slope == 0.0 and exp == 0.0

    df2 = _df([0.0, 0.0, 0.0, 0.0, float("inf")], [10.0, 10.0, 12.0, 14.0, 15.0])
    slope2, _exp2, _fr2 = s._rank_candidate_components(df2, [6, 1, 1], within=5)
    assert math.isfinite(slope2) and slope2 == 0.0

    # 검증 라운드2 [HIGH] — `band_prev > 0` 가드를 **통과한 뒤** 분자(bw[-1])만
    # nan 인 경우. 위 df(전부 nan)는 `band_prev=mean(nan)=nan` 이라 `nan > 0` 이
    # False 로 떨어져 애초에 이 isfinite 분기를 밟지 않는다(뮤테이션 ESCAPED
    # 원인 — 가드 2줄을 통째로 지워도 30종 뮤테이션 중 이 케이스만 무증상).
    # band_prev=mean(10,10,12,14)=11.5>0 이면서 bw[-1]=nan 인 입력이 실제로
    # `math.isfinite(band_expansion)` 분기를 밟는 유일한 경로다.
    df3 = _df([0.0, 1.0, 2.0, 3.0, 5.0], [10.0, 10.0, 12.0, 14.0, float("nan")])
    _slope3, exp3, _fr3 = s._rank_candidate_components(df3, [6, 1, 1], within=5)
    assert exp3 == 0.0 and math.isfinite(exp3), (
        f"band_prev>0 가드를 통과한 뒤의 nan 분자가 새어 나갔다 — 실측 {exp3}"
    )


# ===========================================================================
# C7 — 기존 테스트 갱신본의 정확값 (독립 재계산)
# ===========================================================================

def test_c7_rank_components_from_enriched_restored_values():
    """`test_rank_components_from_enriched` 의 복원 후 정확값.

    li=4, pi=1 →  m3s = (5-1)/3/10000 = 1.3333333333333333e-4
    bw.iloc[-6:-1] = [10,10,12,14] → mean 11.5 → be = 15/11.5 - 1 = 0.30434782608695654
    stages [4,5,6,1,1] → dist 1 → fr = 5-1 = 4.0
    """
    s = _mk()
    df = _df([0.0, 1.0, 2.0, 3.0, 5.0], [10.0, 10.0, 12.0, 14.0, 15.0], close=10000.0)
    m3s, be, fr = s._rank_candidate_components(df, [4, 5, 6, 1, 1], within=5)
    assert m3s == pytest.approx(1.3333333333333333e-4, abs=1e-18)
    assert be == pytest.approx(0.30434782608695654, abs=1e-15)
    assert fr == pytest.approx(4.0)
    assert _RANK_LOOKBACK == 3

    # 뮤테이션 M3 방어 — 분모 창을 한 칸이라도 옮기면 값이 달라진다
    assert be != pytest.approx(15 / ((10 + 12 + 14) / 3) - 1, abs=1e-9)   # [-5:-1]
    assert be != pytest.approx(15 / ((10 + 10 + 12 + 14 + 15) / 5) - 1, abs=1e-9)  # [-6:]


# ===========================================================================
# C8 — 통합 순위 불변 (기존 test_get_scanned_tickers_ranked_desc 가 그대로 초록)
# ===========================================================================

def test_c8_ranked_desc_components_still_monotone():
    """T1>T2>T3 이 **세 성분 전부**에서 유지된다 — 기존 통합 테스트 무갱신 근거."""
    s = _mk()
    cases = {
        "T1": ([0, 0, 2, 4, 6], [10, 10, 12, 14, 16], [4, 4, 4, 6, 1]),
        "T2": ([0, 0, 1, 2, 3], [10, 10, 11, 12, 13], [4, 4, 6, 1, 1]),
        "T3": ([0, 0, 0, 0, 0], [10, 10, 10, 10, 10], [4, 6, 1, 1, 1]),
    }
    got = {}
    for t, (m3, bw, stages) in cases.items():
        got[t] = s._rank_candidate_components(_df(m3, bw), stages, within=5)

    assert got["T1"][0] == pytest.approx(2e-4, abs=1e-18)
    assert got["T2"][0] == pytest.approx(1e-4, abs=1e-18)
    assert got["T3"][0] == 0.0
    assert got["T1"][1] == pytest.approx(0.391304347826087, abs=1e-12)
    assert got["T2"][1] == pytest.approx(0.20930232558139528, abs=1e-12)
    assert got["T3"][1] == 0.0
    for i in range(3):
        assert got["T1"][i] >= got["T2"][i] >= got["T3"][i]
    scores = s._score_candidates(
        {t: got[t] for t in ("T1", "T2", "T3")}, s.config.params)
    assert scores["T1"] > scores["T2"] > scores["T3"]


# ===========================================================================
# C9 (G-273-6) — 최상위 안전 계약: 후보 **집합** 불변
# ===========================================================================

async def test_c9_g273_6_candidate_set_independent_of_rank_components(monkeypatch):
    """랭킹 성분이 무엇이든 `rank_raw`·`_candidates` 의 **집합**은 같다.

    성분 함수를 상수 `(0,0,0)` 으로 갈아끼운 실행과 실제 실행의 집합을 비교한다.
    순서만 달라야 하고, 집합이 바뀌면 랭킹이 **자격 게이트를 건드린 것**이다.
    """
    from unittest.mock import AsyncMock
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
        ("T3", _full([4, 6, 1, 1, 1], [0, 0, 0, 0, 0], [10, 10, 10, 10, 10])),
    ]

    async def _run(strat, flat: bool):
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
        if flat:
            monkeypatch.setattr(type(strat), "_rank_candidate_components",
                                lambda self, e, s_, w: (0.0, 0.0, 0.0))
        await strat.prepare()
        return set(strat.get_scanned_tickers()), set(strat._candidates.keys())

    real = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    scanned_a, cand_a = await _run(real, flat=False)
    flat_s = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2))
    scanned_b, cand_b = await _run(flat_s, flat=True)

    assert scanned_a == scanned_b, (
        "랭킹 성분이 후보 **집합**을 바꿨다 — 자격 게이트 침범. 즉시 원복 대상"
    )
    assert cand_a == cand_b
    assert scanned_a == {"T1", "T2", "T3"}


# ===========================================================================
# 검증 라운드2 [MEDIUM] — `_band_observe_row` 산술 직접 커버
#
# `_band_observe_row` 는 `_rank_candidate_components` 와 **독립 재계산**하는
# 관측 stash 헬퍼다(leaf 사정권 밖 — `grep -rn '_band_observe_row' tests/` 가
# 사전 검증 0건이었다). 이 두 테스트가 없으면 `bw_prev5` 를 단일봉으로 바꾸거나
# (MB2) `exp1` 을 상수로 바꿔도(MB3) 전 스위트가 초록이다.
# ===========================================================================

def test_c14_band_observe_row_exp1_matches_advisory_table():
    """자문 §4.3(나) 실측표(`kojiro_band_width_floor_filter_20260910.md:340-344`)
    5행을 직접 호출로 재현 — `row[7]`(exp1) 이 독립 재계산과 일치한다(MB3 KILL).

    표 열 = 종목 / bw(현재) / bw(직전 3봉, denom) / exp1. `_RANK_LOOKBACK=3` 이므로
    길이 4(`li=3, pi=0`) 시리즈로 `bw.iloc[0]=denom`·`bw.iloc[3]=현재` 를 배치하면
    `_band_observe_row` 의 `bw_prev1`/`exp1` 계산 경로만 단독으로 노출된다.
    """
    s = _mk()
    cases = [
        ("롯데지주", 10.4, 95.0, 8.1346),
        ("에스엠", 91.0, 708.0, 6.7802),
        ("HD현대", 483.0, 3150.0, 5.5217),
        ("SK케미칼", 2705.0, 2860.0, 0.0573),
        ("삼천리", 2681.0, 3496.0, 0.3040),
    ]
    for name, bw_prev1, bw_now, expected_exp1 in cases:
        enriched = {
            "macd3": pd.Series([0.0, 0.0, 0.0, 0.0]),
            "band_width": pd.Series([bw_prev1, bw_prev1, bw_prev1, bw_now]),
        }
        row = s._band_observe_row(
            name, "20260910", 10000.0, 200.0, enriched, [4, 4, 4, 6], within=5)
        assert row[7] == pytest.approx(expected_exp1, abs=0.05), (
            f"{name} exp1(row[7]) 불일치 — 실측 {row[7]} 기대 {expected_exp1}"
        )


def test_c15_band_observe_row_exp5_and_slope_pct_match_rank_components():
    """같은 `enriched` 에서 `row[8]`(exp5) == `_rank_candidate_components()[1]`
    (band_expansion), `row[10]`(slope_pct) == `[0]`(macd3_slope) — **비트 일치**.

    이 등식이 이 사이클의 유일한 '관측이 거짓말하지 않는다' 보증이다
    (MB2 — `bw_prev5` 를 단일봉으로 바꾸면 관측만 조용히 어긋난다).
    """
    s = _mk()
    df = _df([0.0, 1.0, 2.0, 3.0, 5.0], [10.0, 10.0, 12.0, 14.0, 15.0], close=10000.0)
    macd3_slope, band_expansion, _fresh = s._rank_candidate_components(
        df, [4, 5, 6, 1, 1], within=5)
    row = s._band_observe_row("T", "20260910", 10000.0, 200.0, df, [4, 5, 6, 1, 1], within=5)
    assert row[8] == band_expansion, (
        f"exp5(row[8]) 가 본체 band_expansion 과 어긋난다 — {row[8]} vs {band_expansion}"
    )
    assert row[10] == macd3_slope, (
        f"slope_pct(row[10]) 가 본체 macd3_slope 와 어긋난다 — {row[10]} vs {macd3_slope}"
    )


# ===========================================================================
# 검증 라운드3 [HIGH] — `_band_observe_row` 의 `except Exception:` 폴백 무검정
# (뮤테이션 `except Exception:` → `except KeyError:` ESCAPED)
# ===========================================================================

def test_c16_band_observe_row_except_fallback_on_nonnumeric_band_width():
    """`band_width` 가 비수치(object dtype)면 **raise 하지 않고** 정확한 12원소
    폴백 튜플 `(name, bar, close, atr, 0.0×7, None)` 을 반환한다.

    `bw.iloc[li]` 에서 `float("bad")` 가 `ValueError` 를 낸다 — `KeyError` 가
    아니다. 뮤테이션 방어 — `except Exception:` → `except KeyError:` 로 좁히면
    이 `ValueError` 가 새어 나가 `_band_observe_row` 자체가 raise 하고,
    이는 호출부(`prepare`)의 같은 try 스코프에서 **그 ticker 의 매수 후보
    처리 전체**를 끊는다(§검증 라운드3 행위 테스트 `test_c17_…` 참조).
    """
    s = _mk()
    enriched = {
        "macd3": pd.Series([0.0, 1.0, 2.0, 3.0, 5.0]),
        "band_width": pd.Series(["bad"] * 5),   # object dtype, 비수치
    }
    row = s._band_observe_row(
        "종목", "20260909", 10000.0, 200.0, enriched, [4, 5, 6, 1, 1], within=5)
    assert row == ("종목", "20260909", 10000.0, 200.0,
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None), (
        f"폴백 튜플이 계약(`kojiro.py` `except Exception:` 분기 리터럴)과 다르다 — 실측 {row}"
    )
