"""(라) 장세 문 — 칸 판정 · 허용 칸 · D−1 사용 · 시장 유닛 배수 적용 위치 · 관문 끈 판 = 성적표 books 일치."""
from __future__ import annotations

import inspect
import json
import linecache
import os
import sys
import types
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import ra_gate_core as G  # noqa: E402

RESULT_JSON = os.path.join(_ROOT, "_workspace/analysis/ra_gate_20261006/result.json")


@dataclass(frozen=True)
class _S:
    ticker: str
    m: float = 1.0


# ── 칸 판정 · 허용 칸 ──────────────────────────────────────────────────────

def test_allow_cells_are_user_fixed_10_and_01():
    assert G.ALLOW == {"10", "01"} and G.BLOCK == {"00", "11"}
    assert G.allowed("10") and G.allowed("01")
    assert not G.allowed("00") and not G.allowed("11")
    assert G.allowed(None)                                      # 칸 없음(판단 계열 이전) = 허용


def test_rule_keys_bits_match_slope_and_breadth():
    from replay import regime_v2 as RV
    f = pd.DataFrame({"T7": [0.01, -0.01, -0.02, 0.03, np.nan], "R5": [0.5, 0.2, 0.6, 0.3, 0.1]})
    keys = RV.rule_keys(f, [("T7", ">", 0.0), ("R5", "<=", 0.3)])
    # 오름·넓음 = 10(허용) · 내림·좁음 = 01(허용) · 내림·넓음 = 00(중단) · 오름·좁음(경계 0.3 포함) = 11(중단) · 결측 = 거짓
    assert list(keys) == ["10", "01", "00", "11", "01"]
    assert [G.allowed(k) for k in keys[:4]] == [True, True, False, False]


# ── D−1 사용 ───────────────────────────────────────────────────────────────

def test_asof_uses_strictly_earlier_day():
    d = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"])
    a = G.AsOf(d, ["10", "00", "01"])
    assert a("2020-01-02") is None                              # 그날 종가는 아직 못 쓴다
    assert a("2020-01-03") == "10"
    assert a("2020-01-04") == "00"                              # 휴장일 사이 = 앞선 마지막 날
    assert a("2020-01-06") == "00"
    assert a("2020-01-07") == "01"


def test_asof_stale_rule():
    d = pd.DatetimeIndex(["2020-01-02"])
    a = G.AsOf(d, [0.5], default=float("nan"), stale_days=10)
    assert a("2020-01-12") == 0.5
    assert np.isnan(a("2020-01-13"))                            # 11일 묵음 → 판정 불가(fail-open 은 호출자)


def test_mu_asof_equals_audit_m_for_days():
    from replay.audit import market_unit as MU
    rng = np.random.default_rng(3)
    bd = pd.bdate_range("2019-01-01", periods=200)
    closes = 10000 * np.cumprod(1 + rng.normal(0, 0.01, len(bd)))
    cal = pd.DatetimeIndex(list(bd[50:]) + [bd[-1] + pd.Timedelta(days=20)])
    ref = MU.m_for_days(cal, bd, closes)
    f = G.mu_asof(bd, closes)
    got = np.array([f(d) for d in cal])
    assert np.array_equal(np.isnan(ref), np.isnan(got))
    assert np.allclose(ref[~np.isnan(ref)], got[~np.isnan(got)])
    assert set(np.unique(ref[~np.isnan(ref)])) <= {0.0, 0.5, 0.75, 1.0}


# ── 관문 ───────────────────────────────────────────────────────────────────

def _gate(cells, ms, **kw):
    cal = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"])
    cell_of = G.AsOf(cal, cells)
    m_of = G.AsOf(cal, ms, default=float("nan"))
    return G.RaGate(cell_of=cell_of, m_of=m_of, **kw), cal


def test_gate_blocks_whole_day_on_block_cell_and_records():
    g, cal = _gate(["10", "00", "01", "11"], [1, 1, 1, 1], block=True)
    loc = {"cal": cal}
    sigs = [_S("A"), _S("B")]
    assert g.filter(0, sigs, loc) == sigs                       # 칸 없음 → 허용
    assert g.filter(1, sigs, loc) == sigs                       # 01-03 의 칸 = 01-02 종가 10 → 허용
    assert g.filter(2, sigs, loc) == []                         # 01-06 의 칸 = 01-03 종가 00 → 중단
    assert g.filter(3, sigs, loc) == sigs                       # 01-07 의 칸 = 01-06 종가 01 → 허용
    r = g.runs[-1]
    assert r["dropped"] == [("2020-01-06", "A", "00"), ("2020-01-06", "B", "00")]
    assert r["cell_days"] == {None: 1, "10": 1, "00": 1, "01": 1}


def test_gate_off_returns_same_list_object():
    g, cal = _gate(["00"] * 4, [0, 0, 0, 0], block=False, mu="native")
    lst = [_S("A", 0.0)]
    assert g.filter(1, lst, {"cal": cal}) is lst
    assert g.runs[-1]["dropped"] == []


def test_mu_off_replaces_m_on_copies_only():
    g, cal = _gate(["10"] * 4, [0.5] * 4, block=True, mu="off")
    a = _S("A", 0.0)
    out = g.filter(1, [a], {"cal": cal})
    assert out[0].m == 1.0 and a.m == 0.0                       # 사본만 m = 1


def test_mu_native_keeps_signal_m_and_counts_mismatch():
    g, cal = _gate(["10"] * 4, [0.75, 0.5, 1, 1], block=True, mu="native", check_m=True)
    loc = {"cal": cal}
    out = g.filter(1, [_S("A", 0.75), _S("B", 0.5)], loc)       # 01-03 의 m = 01-02 값 0.75
    assert [s.m for s in out] == [0.75, 0.5]
    assert g.runs[-1]["m_checked"] == 2 and g.runs[-1]["m_mismatch"] == 1


def test_mu_apply_sets_multiplier_after_block_and_drops_zero():
    g, cal = _gate(["10", "00", "01", "10"], [0.5, 0.75, 0.0, float("nan")], block=True, mu="apply")
    loc = {"cal": cal}
    s = [_S("A")]
    assert g.filter(1, s, loc) == s and g.mult == 0.5           # 허용 칸 · m 0.5 → 랏 배수
    assert g.scale(7) == 3 and g.scale(0) == 0                  # floor(7 × 0.5)
    assert g.filter(2, s, loc) == []                            # 중단 칸(00) → 칸으로 버림
    assert g.runs[-1]["dropped"] == [("2020-01-06", "A", "00")] and g.runs[-1]["dropped_mu"] == []
    assert g.filter(3, s, loc) == []                            # 허용 칸(01)인데 m = 0 → 신호 단계에서 버림
    assert g.runs[-1]["dropped_mu"] == [("2020-01-07", "A", "01")]


def test_mu_apply_nan_is_fail_open():
    g, cal = _gate(["10"] * 4, [float("nan")] * 4, block=False, mu="apply")
    assert g.filter(1, [_S("A")], {"cal": cal}) and g.mult == 1.0 and g.scale(5) == 5


def test_mult_resets_each_day_and_native_leaves_scale_identity():
    g, cal = _gate(["10"] * 4, [0.5] * 4, block=False, mu="native")
    g.filter(1, [_S("A")], {"cal": cal})
    assert g.mult == 1.0 and g.scale(9) == 9


# ── 소스 끼우기 · 끈 판 = 원판 ────────────────────────────────────────────────

_TOY = '''
def run_book(signals_by_gd, cal, seed, B=1000.0, pos_ratio=0.2):
    import math
    import numpy as np
    rng = np.random.default_rng(seed)
    out = []
    for gd in range(len(cal)):
        todays = list(signals_by_gd.get(gd, []))
        rng.shuffle(todays)
        for cd in todays:
            q = int(math.floor(B * pos_ratio / cd.E_raw))
            pos = {}
            pos[cd.tid] = (cd, q)
            out.append((gd, cd.tid, q, float(rng.random())))
    return out
'''


@dataclass(frozen=True)
class _C:
    tid: int
    E_raw: float
    m: float = 1.0


def _toy_module():
    mod = types.ModuleType("toy_rag")
    exec(_TOY, mod.__dict__)
    fn = "<toy_rag>"
    linecache.cache[fn] = (len(_TOY), None, _TOY.splitlines(True), fn)
    mod.run_book.__code__ = mod.run_book.__code__.replace(co_filename=fn)
    assert inspect.getsource(mod.run_book)
    return mod


def test_gate_function_off_equals_original_and_mult_hits_lot():
    mod = _toy_module()
    cal = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"])
    sig = {1: [_C(0, 30.0), _C(1, 40.0)], 2: [_C(0, 30.0), _C(1, 40.0), _C(2, 7.0)]}
    orig = mod.run_book(sig, cal, 7)
    g = G.RaGate(cell_of=G.AsOf(cal, ["10", "00", "01"]), m_of=G.AsOf(cal, [0.5, 0.5, 0.5]), block=False)
    g.key = lambda cd: cd.tid
    G.gate_function(mod, "run_book", g, mr=True)
    assert mod.run_book(sig, cal, 7) == orig                     # 끈 판 = 원판(난수 흐름 · 랏까지)
    g.block = g.enabled = True
    on = mod.run_book(sig, cal, 7)
    assert [x for x in on if x[0] == 2] == []                    # 01-06 의 칸 = 01-03 종가 00 → 중단
    assert [x for x in on if x[0] == 1] == [x for x in orig if x[0] == 1]
    g.block = g.enabled = False
    g.mu = "apply"
    half = mod.run_book(sig, cal, 7)
    assert [x[2] for x in half if x[0] == 1] == [int(np.floor(1000 * 0.2 * 0.5 / (30.0 if x[1] == 0 else 40.0)))
                                                  for x in half if x[0] == 1]


def test_gate_source_mr_lot_must_be_unique():
    src = ("def f(x, gd, rng, B, pos_ratio):\n    todays = list(x.get(gd, []))\n    rng.shuffle(todays)\n"
           "    for cd in todays:\n        pos = {}\n        pos[cd.tid] = (cd, q)\n")
    _, n = G.gate_source(src, mr=True)
    assert n == -1                                               # 랏 자리 없음 → 거부


@pytest.mark.parametrize("modname,fn,mr", [
    ("replay.strategies.kojiro_y30", "run_book30", False),
    ("replay.strategies.donchian_y30", "run_book", False),
    ("replay.strategies.y30_bfbvcp", "run_book", False),
    ("replay.strategies.vb_y30", "run_book_var", False),
    ("replay.y30_etfbase_run", "etf_book30", False),
    ("replay.y30_mr_band", "run_book", True),
])
def test_real_loops_have_exactly_one_gate_site(modname, fn, mr):
    import importlib
    try:
        mod = importlib.import_module(modname)
    except Exception as e:  # noqa: BLE001 — 실행 환경에 자료 의존 import 가 없으면 건너뜀
        pytest.skip(f"import 실패: {e}")
    import textwrap
    src = textwrap.dedent(inspect.getsource(getattr(mod, fn)))
    new, n = G.gate_source(src, mr=mr)
    assert n == 1
    assert new.count("_SRS_GATE.filter(gd, todays, locals())") == 1
    # 관문 줄은 섞기 바로 뒤
    lines = new.splitlines()
    i = next(k for k, ln in enumerate(lines) if "_SRS_GATE.filter" in ln)
    assert "rng.shuffle(todays)" in lines[i - 1]
    if mr:
        assert new.count("B * pos_ratio * _SRS_GATE.mult / cd.E_raw") == 1


def test_spec_table_matches_prereg():
    from replay import ra_gate_run as RR
    assert RR.spec("kojiro", "G0") == {"block": False, "mu": "native", "check_m": True, "etf_enforce": False}
    assert RR.spec("kojiro", "G0N")["mu"] == "off" and not RR.spec("kojiro", "G0N")["block"]
    assert RR.spec("donchian", "G1") == {"block": True, "mu": "off", "check_m": False, "etf_enforce": False}
    assert RR.spec("vcp", "G2") == {"block": True, "mu": "native", "check_m": False, "etf_enforce": False}
    assert RR.spec("vb", "G1") == {"block": True, "mu": "native", "check_m": False, "etf_enforce": False}
    assert RR.spec("mr_band", "G3S") == {"block": False, "mu": "apply", "check_m": False, "etf_enforce": False}
    assert RR.spec("etf_trend", "G2S") == {"block": True, "mu": "native", "check_m": False, "etf_enforce": True}
    with pytest.raises(ValueError):
        RR.spec("bfb", "G3S")
    with pytest.raises(ValueError):
        RR.spec("vb", "G0N")


# ── 산출 대조 — 관문 끈 판 = 성적표 books ────────────────────────────────────

def test_base_books_match_scoreboard():
    if not os.path.exists(RESULT_JSON):
        pytest.skip("결과 파일 없음")
    res = json.load(open(RESULT_JSON))
    chk = res["check_scoreboard"]
    assert set(chk) == {"kojiro", "donchian", "vcp", "bfb", "vb", "etf_trend", "mr_band", "mr_fkeep"}
    assert all(v is not None and v <= 0.5 for v in chk.values()), chk
    assert res["cells"]["regv2_key_diff"] == 0
