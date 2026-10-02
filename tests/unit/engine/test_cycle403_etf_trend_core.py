"""cycle403 Red — ETF 추세 전략 순수 leaf `src/engine/etf_trend_core.py` 의 재현 동등성 · leaf 순도.

명세 정본 = `_workspace/cycle403_etf_trend_spec.md` §3 · §10-1 · §10-2
재현 정본 = `_workspace/domain_consult/cycle391_etf_s0_remeasure.py`
(`build_ticker` 지표 · `gen_trades` donchian 분기 · `sim_donchian(intraday_line=False)` · `Corr`)

재현 모듈은 `importlib` 로 파일에서 읽는다. 모듈 최상위는 상수·함수 정의와 `glob`(빈 목록이어도 무해)뿐이고
`main()` 은 `if __name__ == "__main__"` 아래라 부르지 않는다 — 읽기만으로 파일을 쓰거나 네트워크에 닿지 않는다.

## Green 이 맞출 계약 (명세 §3 이름 그대로 · 시그니처는 이 파일이 정한다)

봉 입력은 **날짜 오름차순** 리스트(`list[float]`). 인덱스 `j` = 신호봉 t. 반환 리스트 길이 = 입력 길이.

| 함수 | 시그니처 · 반환 |
|---|---|
| `ema` | `ema(values, span) -> list[float]` — `e[0]=v[0]`, `a=2/(span+1)` (pandas `ewm(adjust=False)`) |
| `true_ranges` | `true_ranges(highs, lows, closes) -> list[float]` — `tr[0]=h[0]-l[0]` |
| `atr_wilder` | `atr_wilder(tr, period=20) -> list[float]` — `ewm(alpha=1/period, adjust=False)`, tr[0] 부터 |
| `n14` | `n14(tr, i, period=14) -> float | None` — `mean(tr[i-13..i])`, tr[0] 제외 → `i < 14` 면 None |
| `breakout_line` | `breakout_line(highs, j, period=20) -> float | None` — `max(h[j-20..j-1])`, `j < 20` 면 None |
| `tv20` · `tv_prev20` | `tv20(tv, j, period=20)` = `mean(tv[j-19..j])` (j<19 None) · `tv_prev20(tv, j, period=20)` = `mean(tv[j-20..j-1])` (j<20 None) |
| `entry_signal` | `entry_signal(highs, lows, closes, trade_values, j, **params) -> EntrySignal` — 기본 인자 = DEFAULT_PARAMS 값(명세 L12). 반환 객체 속성 `ok: bool` · `stage: str | None`(떨어진 단계, `ok` 면 None) · `line` · `n` · `atr20` · `tv20` · `close` · `ema60` |
| `gap_skip_reason` | `gap_skip_reason(open_price, close_t, line, gap_pct=3.0, over_line_pct=4.0) -> "gap_up" | "gap_over_line" | None` (둘 다면 gap_up) |
| `hard_stop` | `hard_stop(E, N, backstop_pct=-9.0, stop_atr=2.0) -> float` |
| `stop_line` | `stop_line(E, N, hsb_closed, *, backstop_pct=-9.0, stop_atr=2.0, breakeven_atr=1.5, trail_atr=1.8) -> float` |
| `channel_low` | `channel_low(lows_prev, period=10) -> float | None` — 끝에서 최대 10개 최솟값, 빈 입력 None |
| `breakout_failed` | `breakout_failed(price, line, bars_since_buy, min_bars=2) -> bool` |
| `simulate_exit` | `simulate_exit(opens, highs, lows, closes, j) -> (k, px, why)` — `sim_donchian(d, j)` 와 같은 값 |
| `return_correlation` | `return_correlation(closes_a, closes_b, *, calendar, window=120, min_obs=60) -> float | None` — `closes_*` 는 `Mapping[날짜, 종가]`, `calendar` 는 기준 달력(069500 날짜 오름차순, 마지막 = 신호일). 수익률 = 같은 달력의 연속 두 날짜가 모두 있을 때만 |
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
REPRO = ROOT / "_workspace" / "domain_consult" / "cycle391_etf_s0_remeasure.py"
LEAF_REL = "src/engine/etf_trend_core.py"
REL = 1e-9


# ===========================================================================
# 공용 — 재현 모듈 · leaf · 합성 시계열
# ===========================================================================
def _rep():
    np = pytest.importorskip("numpy")  # noqa: F841 — 재현 모듈 의존성
    pytest.importorskip("pandas")
    if "rep391_cycle403" in sys.modules:
        return sys.modules["rep391_cycle403"]
    spec = importlib.util.spec_from_file_location("rep391_cycle403", REPRO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["rep391_cycle403"] = mod
    return mod


def _leaf():
    try:
        return importlib.import_module("src.engine.etf_trend_core")
    except ImportError as exc:  # pragma: no cover — Red 단계
        pytest.fail(f"[Red] {LEAF_REL} 미존재 — {exc}")


def _need(mod, *names):
    missing = [n for n in names if not hasattr(mod, n)]
    if missing:
        pytest.fail(f"[Red] etf_trend_core 에 {missing} 없음")


#: 씨앗 고정 합성 시계열 — 추세 · 톱니 · 급락 · 갭(시가 +3.5% 섞기) · 저유동(거래대금 하한 근처)
SCENARIOS = [
    (1, "trend"), (2, "saw"), (3, "crash"), (4, "gap"), (5, "trend"), (6, "saw"), (7, "thin"),
]


def _series(seed: int, kind: str, n: int = 320):
    rng = random.Random(seed)
    c = 10_000.0
    prev_r = 0.0
    o_, h_, l_, c_, tv_ = [], [], [], [], []
    for i in range(n):
        drift = {
            "trend": 0.0025,
            "saw": 0.004 if (i // 25) % 2 == 0 else -0.004,
            "crash": 0.003 if i < n - 60 else -0.01,
            "gap": 0.002,
            "thin": 0.0025,
        }[kind]
        r = drift + rng.gauss(0, 0.012)
        # 갭: 큰 양봉(신호 후보) 다음 날 절반 확률로 시가 +3.5% — 갭 스킵 경로 표본
        gap = 0.035 if kind == "gap" and prev_r > 0.004 and rng.random() < 0.5 else 0.0
        o = c * (1 + rng.gauss(0, 0.004) + gap)
        cl = c * (1 + r)
        h = max(o, cl) * (1 + abs(rng.gauss(0, 0.006)))
        lo = min(o, cl) * (1 - abs(rng.gauss(0, 0.006)))
        base = 2.1e9 if kind == "thin" else 3e9
        tv = base * (1 + abs(rng.gauss(0, 0.3))) * (2.6 if (r > 0.004 and rng.random() < 0.6) else 1.0)
        o_.append(o)
        h_.append(h)
        l_.append(lo)
        c_.append(cl)
        tv_.append(tv)
        c = cl
        prev_r = r
    return o_, h_, l_, c_, tv_


def _rep_data(o, h, lo, c, tv):
    import numpy as np
    import pandas as pd

    rep = _rep()
    df = pd.DataFrame({
        "open_adj": o, "high_adj": h, "low_adj": lo, "close_adj": c,
        "close": c, "trade_value": tv, "mktcap": [1e12] * len(c),
    })
    ci = np.arange(len(c))
    return rep.build_ticker(df, ci)


def _rep_entries(d, n):
    """재현이 산 신호봉 j 집합 — `gen_trades` donchian 분기 ∧ §2.3 전체판(`full_u`)."""
    import numpy as np
    import pandas as pd

    rep = _rep()
    cal = pd.date_range("2025-01-01", periods=n, freq="D").values
    trades = rep.gen_trades(
        "donchian", {"X": d}, {"X": True}, np.ones(n), cal, {"X": {"listed_at_end": True}}, n - 1,
    )
    return {t["j"] for t in trades if rep.full_u(t)}


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if math.isnan(b):
        return False
    return abs(a - b) <= REL * max(1.0, abs(b))


def _nan_to_none(x):
    return None if (x is None or (isinstance(x, float) and math.isnan(x))) else float(x)


# ===========================================================================
# §10-1 동등성 — 지표
# ===========================================================================
@pytest.mark.parametrize("seed,kind", SCENARIOS)
def test_indicators_match_reproduction(seed, kind):
    lf = _leaf()
    _need(lf, "ema", "true_ranges", "atr_wilder", "n14", "breakout_line", "tv20", "tv_prev20")
    o, h, lo, c, tv = _series(seed, kind)
    d = _rep_data(o, h, lo, c, tv)
    n = len(c)

    e60 = lf.ema(c, 60)
    assert len(e60) == n
    tr = lf.true_ranges(h, lo, c)
    assert len(tr) == n
    a20 = lf.atr_wilder(tr, 20)
    assert len(a20) == n

    bad: list[str] = []
    for i in range(n):
        if not _close(e60[i], float(d["e60"][i])):
            bad.append(f"e60[{i}] {e60[i]} != {d['e60'][i]}")
        if not _close(a20[i], float(d["atr20"][i])):
            bad.append(f"atr20[{i}] {a20[i]} != {d['atr20'][i]}")
        checks = (
            ("n14", lf.n14(tr, i), d["n14"][i]),
            ("hi_prev20", lf.breakout_line(h, i), d["hi_prev20"][i]),
            ("tv20", lf.tv20(tv, i), d["tv20"][i]),
            ("tvprev20", lf.tv_prev20(tv, i), d["tvprev20"][i]),
        )
        for name, got, want in checks:
            want = _nan_to_none(want)
            got = None if got is None else float(got)
            if not _close(got, want):
                bad.append(f"{name}[{i}] {got} != {want}")
    assert bad == [], f"{kind}/{seed}: 재현과 다른 지표 {len(bad)}개 — 앞 10개: {bad[:10]}"


def test_indicator_warmup_boundaries():
    """첫 값 위치 — n14 는 i=14, 돌파선·전일 20봉 거래대금은 j=20, 20봉 거래대금은 j=19."""
    lf = _leaf()
    o, h, lo, c, tv = _series(1, "trend", n=40)
    tr = lf.true_ranges(h, lo, c)
    assert tr[0] == pytest.approx(h[0] - lo[0], rel=REL)
    assert lf.n14(tr, 13) is None and lf.n14(tr, 14) is not None
    assert lf.breakout_line(h, 19) is None and lf.breakout_line(h, 20) == pytest.approx(max(h[0:20]), rel=REL)
    assert lf.tv20(tv, 18) is None and lf.tv20(tv, 19) == pytest.approx(sum(tv[0:20]) / 20, rel=REL)
    assert lf.tv_prev20(tv, 19) is None and lf.tv_prev20(tv, 20) == pytest.approx(sum(tv[0:20]) / 20, rel=REL)


# ===========================================================================
# §10-1 동등성 — 진입 판정(갭 포함)
# ===========================================================================
@pytest.mark.parametrize("seed,kind", SCENARIOS)
def test_entry_decision_matches_reproduction_at_every_bar(seed, kind):
    lf = _leaf()
    _need(lf, "entry_signal", "gap_skip_reason")
    o, h, lo, c, tv = _series(seed, kind)
    n = len(c)
    d = _rep_data(o, h, lo, c, tv)
    want = _rep_entries(d, n)

    got: set[int] = set()
    for j in range(0, n - 1):
        sig = lf.entry_signal(h, lo, c, tv, j)
        if not sig.ok:
            assert isinstance(sig.stage, str) and sig.stage, f"j={j}: 떨어진 단계 이름이 없다(깔때기용)"
            continue
        assert sig.stage is None
        assert _close(float(sig.line), float(d["hi_prev20"][j]))
        assert _close(float(sig.n), float(d["n14"][j]))
        assert _close(float(sig.atr20), float(d["atr20"][j]))
        assert _close(float(sig.tv20), float(d["tv20"][j]))
        assert _close(float(sig.close), float(c[j]))
        assert _close(float(sig.ema60), float(d["e60"][j]))
        if lf.gap_skip_reason(o[j + 1], c[j], sig.line) is None:
            got.add(j)
    assert got == want, (
        f"{kind}/{seed}: 진입 봉이 다르다 — leaf 만 {sorted(got - want)} · 재현만 {sorted(want - got)}"
    )


def test_entry_corpus_is_not_vacuous():
    """동등성 표본이 공허하지 않다 — 진입·갭 스킵·청산 사유가 여럿 나온다."""
    lf = _leaf()
    rep = _rep()
    entries = 0
    gap_skips = 0
    reasons: set[str] = set()
    for seed, kind in SCENARIOS:
        o, h, lo, c, tv = _series(seed, kind)
        d = _rep_data(o, h, lo, c, tv)
        for j in _rep_entries(d, len(c)):
            entries += 1
            reasons.add(rep.sim_donchian(d, j)[2])
        for j in range(0, len(c) - 1):
            sig = lf.entry_signal(h, lo, c, tv, j)
            if sig.ok and lf.gap_skip_reason(o[j + 1], c[j], sig.line) is not None:
                gap_skips += 1
    assert entries >= 50, f"진입 {entries}건 — 합성 시계열이 너무 얌전하다"
    assert gap_skips >= 1, "갭 스킵 경로가 한 번도 안 탔다"
    assert {"stop", "below_line"} <= reasons, f"청산 사유 표본이 좁다: {reasons}"


def test_min_bars_gate_is_100():
    """봉 수 < 100 이면 다른 조건이 다 맞아도 신호가 아니다(재현 `j0 = MIN_BARS - 1`)."""
    lf = _leaf()
    o, h, lo, c, tv = _series(5, "trend")
    for j in range(0, 99):
        assert lf.entry_signal(h, lo, c, tv, j).ok is False, f"j={j}(봉 {j + 1}개) 에서 신호"


@pytest.mark.parametrize("open_price,close_t,line,want", [
    pytest.param(10_300, 10_000, 9_800, "gap_up", id="gap_up_at_3pct"),
    pytest.param(10_299, 10_000, 9_950, None, id="below_3pct_and_line_ok"),
    pytest.param(10_000, 10_000, 9_600, "gap_over_line", id="over_line_4pct"),
    pytest.param(9_984, 10_000, 9_600, None, id="over_line_equal_not_skip"),
    pytest.param(10_500, 10_000, 9_000, "gap_up", id="both_reports_gap_up"),
    pytest.param(9_000, 10_000, 9_800, None, id="gap_down_not_skipped"),
])
def test_gap_skip_reason_boundaries(open_price, close_t, line, want):
    lf = _leaf()
    assert lf.gap_skip_reason(open_price, close_t, line) == want


# ===========================================================================
# §10-1 동등성 — 청산 재현
# ===========================================================================
@pytest.mark.parametrize("seed,kind", SCENARIOS)
def test_simulate_exit_matches_sim_donchian(seed, kind):
    lf = _leaf()
    _need(lf, "simulate_exit")
    rep = _rep()
    o, h, lo, c, tv = _series(seed, kind)
    d = _rep_data(o, h, lo, c, tv)
    bad = []
    for j in sorted(_rep_entries(d, len(c))):
        k0, px0, why0 = rep.sim_donchian(d, j)
        k1, px1, why1 = lf.simulate_exit(o, h, lo, c, j)
        if (int(k1), why1) != (int(k0), why0) or not _close(float(px1), float(px0)):
            bad.append(f"j={j}: leaf {(k1, px1, why1)} != 재현 {(k0, float(px0), why0)}")
    assert bad == [], f"{kind}/{seed}: " + "; ".join(bad[:10])


# ===========================================================================
# 가격선 단위 — 명세 §3
# ===========================================================================
def test_hard_stop():
    lf = _leaf()
    assert lf.hard_stop(10_000, 200) == pytest.approx(9_600)          # 2N 지배
    assert lf.hard_stop(10_000, 600) == pytest.approx(9_100)          # 받침 −9% 지배
    assert lf.hard_stop(10_000, None) == pytest.approx(9_100)
    assert lf.hard_stop(10_000, 0) == pytest.approx(9_100)


@pytest.mark.parametrize("hsb,want", [
    pytest.param(None, 9_600, id="buy_day_hard_only"),
    pytest.param(10_299, 10_299 - 1.8 * 200, id="trail_below_breakeven_trigger"),
    pytest.param(10_300, 10_000, id="breakeven_at_trigger"),
    pytest.param(11_000, 11_000 - 1.8 * 200, id="trail_over_breakeven"),
    pytest.param(9_700, 9_600, id="hard_dominates"),
])
def test_stop_line(hsb, want):
    lf = _leaf()
    assert lf.stop_line(10_000, 200, hsb) == pytest.approx(want)


def test_stop_line_without_n_is_backstop_only():
    lf = _leaf()
    assert lf.stop_line(10_000, None, 12_000) == pytest.approx(9_100)


def test_channel_low_and_breakout_failed():
    lf = _leaf()
    assert lf.channel_low([5, 4, 9, 8, 7, 6, 10, 11, 12, 13, 14, 15]) == 6   # 끝 10개
    assert lf.channel_low([3, 2]) == 2
    assert lf.channel_low([]) is None
    assert lf.breakout_failed(9_999, 10_000, 2) is True
    assert lf.breakout_failed(10_000, 10_000, 2) is False                   # 같으면 실패 아님(<)
    assert lf.breakout_failed(9_000, 10_000, 1) is False                    # D+1 은 판단 안 함


# ===========================================================================
# §3 묶음 상관 — `Corr` 와 같은 값
# ===========================================================================
def _calendar(n: int):
    out, d = [], date(2025, 1, 2)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _corr_case(kind: str):
    rng = random.Random({"pair": 11, "indep": 12, "short": 13, "flat": 14, "holes": 15}[kind])
    cal = _calendar(200)
    a, b = {}, {}
    pa = pb = 10_000.0
    for i, dt in enumerate(cal):
        ra = rng.gauss(0, 0.01)
        rb = (0.95 * ra + rng.gauss(0, 0.002)) if kind in ("pair", "short", "holes") else rng.gauss(0, 0.01)
        pa *= 1 + ra
        pb *= 1 + rb
        a[dt] = pa
        if kind == "flat":
            b[dt] = 10_000.0
        elif kind == "short" and i < 200 - 50:
            continue
        elif kind == "holes" and rng.random() < 0.15:
            continue
        else:
            b[dt] = pb
    return cal, a, b


def _rep_corr(cal, a, b):
    import numpy as np

    rep = _rep()
    ret = np.full((len(cal), 2), np.nan)
    for col, ser in enumerate((a, b)):
        cc = np.array([ser.get(dt, np.nan) for dt in cal], dtype=float)
        ret[1:, col] = cc[1:] / cc[:-1] - 1
    return rep.Corr(ret, {"A": 0, "B": 1})("A", "B", len(cal) - 1)


@pytest.mark.parametrize("kind", ["pair", "indep", "short", "flat", "holes"])
def test_return_correlation_matches_reproduction(kind):
    lf = _leaf()
    _need(lf, "return_correlation")
    cal, a, b = _corr_case(kind)
    want = _rep_corr(cal, a, b)
    got = lf.return_correlation(a, b, calendar=cal)
    if want is None:
        assert got is None, f"{kind}: 재현은 판정 불가(None)인데 leaf={got}"
    else:
        assert got is not None and _close(float(got), float(want)), f"{kind}: {got} != {want}"
    if kind == "pair":
        assert want is not None and want > 0.9, "표본 자기검사 — 같은 묶음 쌍이어야 한다"
    if kind in ("short", "flat"):
        assert want is None, "표본 자기검사 — 판정 불가 쌍이어야 한다"


# ===========================================================================
# §10-2 leaf 순도 — 표준 라이브러리만 · await/open/로깅 0
# ===========================================================================
def _leaf_tree() -> ast.Module:
    p = ROOT / LEAF_REL
    if not p.exists():
        pytest.fail(f"[Red] {LEAF_REL} 미존재")
    return ast.parse(p.read_text(encoding="utf-8"))


def test_leaf_imports_stdlib_only():
    tree = _leaf_tree()
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                bad.append(f"{node.lineno}: 상대 import")
                continue
            mods = [node.module or ""]
        else:
            continue
        for m in mods:
            top = m.split(".")[0]
            if top == "__future__":
                continue
            if top not in sys.stdlib_module_names or top == "logging":
                bad.append(f"{node.lineno}: {m}")
    assert bad == [], f"etf_trend_core 는 표준 라이브러리(로깅 제외)만 import 한다: {bad}"


def test_leaf_has_no_await_io_or_logging():
    tree = _leaf_tree()
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)):
            bad.append(f"{node.lineno}: async/await")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if name in ("open", "print"):
                bad.append(f"{node.lineno}: {name}(")
        elif isinstance(node, ast.Name) and node.id in ("logger", "logging"):
            bad.append(f"{node.lineno}: {node.id}")
    assert bad == [], f"etf_trend_core 는 순수 함수만: {bad}"
