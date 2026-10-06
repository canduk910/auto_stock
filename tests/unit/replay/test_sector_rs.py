"""섹터 RS 배제 — RS 계산 · D-1 사용(미래 정보 없음) · 하위 30% 개수 규칙 · 미분류 통과 · 관문 끈 판 = 성적표 일치."""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import sector_rs_core as R  # noqa: E402

RESULT_JSON = os.path.join(_ROOT, "_workspace/analysis/sector_rs_20261006/result.json")


# ── 하위 개수 규칙 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("n,k", [(19, 6), (17, 5), (10, 3), (5, 2), (6, 2), (7, 2), (8, 2), (9, 3), (4, 0), (0, 0)])
def test_n_bottom_round_half_up_and_minimum(n, k):
    # 0.3·n 반올림(.5 올림) · 순위에 든 섹터 5 미만이면 배제 없음
    assert R.n_bottom(n) == k


def test_bottom_set_lowest_rs_and_nan_excluded():
    rs = {"반도체": 0.10, "은행": -0.20, "증권": -0.05, "보험": float("nan"), "건설": -0.30, "운송": 0.0,
          "자동차": 0.02}
    # NaN 1개 빼고 6개 → 하위 round(1.8)=2 → 건설(−0.30) · 은행(−0.20)
    assert R.bottom_set(rs) == frozenset({"건설", "은행"})


def test_bottom_set_tie_uses_bucket_order():
    rs = {b: 0.0 for b in R.BUCKETS[:10]}         # 전부 같은 RS → 10개 → 하위 3 = BUCKETS 앞 3개
    assert R.bottom_set(rs) == frozenset(R.BUCKETS[:3])


# ── RS 계산 ────────────────────────────────────────────────────────────────

def test_rs_value_n_day_minus_bench():
    lv = np.array([100.0, 110.0, 121.0, 133.1])
    bn = np.array([100.0, 100.0, 105.0, 110.0])
    # p=3, N=2: 섹터 133.1/110 − 1 = 0.21 · 지수 110/100 − 1 = 0.10
    assert R.rs_value(lv, bn, 3, 2) == pytest.approx(0.11)
    assert math.isnan(R.rs_value(lv, bn, 1, 2))          # 되돌아볼 날이 없으면 NaN


def test_rs_value_uses_only_up_to_p():
    lv = np.linspace(100, 200, 300)
    bn = np.full(300, 100.0)
    a = R.rs_value(lv, bn, 260, "ibd")
    lv2 = lv.copy()
    lv2[261:] = 1.0                                       # p 뒤를 망가뜨려도 값이 같다
    assert R.rs_value(lv2, bn, 260, "ibd") == a


def test_ibd_weights():
    n = 300
    lv = np.full(n, 100.0)
    bn = np.full(n, 100.0)
    p = 299
    lv[p] = 110.0                                         # 모든 되돌아볼 날 대비 +10% · 지수 0
    assert R.rs_value(lv, bn, p, "ibd") == pytest.approx(0.10)
    lv[p - 63] = 110.0                                    # 63일 수익만 0 → 가중 0.4 빠짐
    assert R.rs_value(lv, bn, p, "ibd") == pytest.approx(0.06)


def test_excl_table_respects_members_and_start():
    n = 30
    bench = np.full(n, 100.0)
    lv = {b: np.full(n, 100.0) for b in R.BUCKETS[:6]}
    for i, b in enumerate(R.BUCKETS[:6]):
        lv[b][-1] = 100.0 + i                             # 마지막 날 RS 0,1,…,5 %
    mem = {b: np.full(n, 10) for b in lv}
    ex = R.excl_table(lv, mem, bench, 5, start={b: 0 for b in lv})
    assert ex[-1] == frozenset(R.BUCKETS[:2])             # 6개 → 하위 2
    mem[R.BUCKETS[0]][-1] = 2                             # 구성 종목 3 미만 → 순위 밖 → 5개 → 하위 2
    ex = R.excl_table(lv, mem, bench, 5, start={b: 0 for b in lv})
    assert ex[-1] == frozenset(R.BUCKETS[1:3])
    st = {b: 0 for b in lv}
    st[R.BUCKETS[1]] = n - 3                              # 지수 시작이 되돌아볼 날보다 늦으면 순위 밖 → 4개 → 없음
    mem[R.BUCKETS[0]][-1] = 10
    st[R.BUCKETS[0]] = n - 3
    assert R.excl_table(lv, mem, bench, 5, start=st)[-1] == frozenset()


# ── 분류 스냅숏 ────────────────────────────────────────────────────────────

def _snaps():
    return [(pd.Timestamp("2001-01-02"), {"005930": "IT하드웨어", "055550": "은행"}),
            (pd.Timestamp("2001-02-01"), {"005930": "반도체"})]


def test_classifier_uses_strictly_earlier_snapshot():
    c = R.Classifier(_snaps())
    assert c.bucket("005930", "2001-01-02") is None              # 스냅숏 그날은 아직 못 쓴다
    assert c.bucket("005930", "2001-01-03") == "IT하드웨어"
    assert c.bucket("005930", "2001-02-01") == "IT하드웨어"
    assert c.bucket("005930", "2001-02-02") == "반도체"
    assert c.bucket("055550", "2001-02-02") is None              # 새 스냅숏에 없으면 미분류


def test_classifier_backfill_and_preferred():
    c = R.Classifier(_snaps(), backfill=True)
    assert c.bucket("005930", "1997-05-01") == "IT하드웨어"
    assert R.Classifier(_snaps()).bucket("005930", "1997-05-01") is None
    assert c.bucket("005935", "2001-01-10") == "IT하드웨어"       # 우선주 → 보통주


def test_label_and_etf_buckets():
    assert R.label_bucket("농업, 임업 및 어업") == "필수소비재"
    assert R.label_bucket("IT 서비스") == "소프트웨어·인터넷"
    assert R.label_bucket("전기·전자") == "IT하드웨어"
    assert R.label_bucket("없는업종") is None
    assert R.etf_bucket("KODEX 반도체") == "반도체"
    assert R.etf_bucket("TIGER 200 IT") == "IT하드웨어"
    assert R.etf_bucket("KODEX 200") is None
    assert R.etf_bucket("TIGER 미국S&P500") is None
    assert R.etf_bucket("KODEX 미국반도체") is None
    assert R.etf_bucket("KODEX 은행") == "은행"


# ── 관문 ───────────────────────────────────────────────────────────────────

class _S:
    def __init__(self, t):
        self.ticker = t


def _gate(enabled=True):
    cal = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"])
    excl = [frozenset(), frozenset({"은행"}), frozenset()]
    cls = {"A": "은행", "B": "반도체"}
    return R.SectorGate(cal, excl, lambda t, d: cls.get(t), enabled=enabled), cal


def test_gate_uses_previous_day_table():
    g, cal = _gate()
    loc = {"cal": cal}
    # 0 일: p = −1 → 표 없음 · 1 일(01-03): p = 0 → 빈 집합 · 2 일(01-06): p = 1 → 은행 배제
    assert [s.ticker for s in g.filter(0, [_S("A")], loc)] == ["A"]
    assert [s.ticker for s in g.filter(1, [_S("A")], loc)] == ["A"]
    assert [s.ticker for s in g.filter(2, [_S("A"), _S("B"), _S("C")], loc)] == ["B", "C"]
    assert g.runs[-1]["dropped"] == [("2020-01-06", "A", "은행")]
    assert g.runs[-1]["unclassified"] == 1                     # C = 미분류 → 통과


def test_gate_between_calendar_days_uses_last_earlier_close():
    g, _ = _gate()
    loc = {"cal": pd.DatetimeIndex(["2020-01-04", "2020-01-07"])}   # 루프 달력이 KRX 달력과 다를 때
    assert [s.ticker for s in g.filter(0, [_S("A")], loc)] == []    # 01-04 → p = 01-03 → 은행 배제
    assert [s.ticker for s in g.filter(1, [_S("A")], loc)] == ["A"]  # 01-07 → p = 01-06 → 빈 집합


def test_gate_disabled_returns_same_list_and_counts():
    g, cal = _gate(enabled=False)
    lst = [_S("A"), _S("B")]
    assert g.filter(2, lst, {"cal": cal}) is lst
    assert g.runs[-1]["dropped"] == [] and g.runs[-1]["seen"] == 2


def test_gate_new_run_on_gd_reset():
    g, cal = _gate()
    g.filter(0, [], {"cal": cal})
    g.filter(1, [], {"cal": cal})
    g.filter(0, [], {"cal": cal})
    assert len(g.runs) == 2 and g.runs[0]["days"] == 2


_TOY = '''
def run_book(signals_by_gd, cal, seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    out = []
    for gd in range(len(cal)):
        todays = list(signals_by_gd.get(gd, []))
        rng.shuffle(todays)
        for s in todays:
            out.append((gd, s.ticker, float(rng.random())))
    return out
'''


def test_gate_function_off_equals_original_and_on_drops():
    import types
    mod = types.ModuleType("toy_srs")
    exec(_TOY, mod.__dict__)
    import inspect
    import linecache
    fn = "<toy_srs>"
    linecache.cache[fn] = (len(_TOY), None, _TOY.splitlines(True), fn)
    mod.run_book.__code__ = mod.run_book.__code__.replace(co_filename=fn)
    assert inspect.getsource(mod.run_book)
    cal = pd.DatetimeIndex(["2020-01-02", "2020-01-03", "2020-01-06"])
    sig = {1: [_S("A"), _S("B")], 2: [_S("A"), _S("B"), _S("C")]}
    orig = mod.run_book(sig, cal, 7)
    g, _ = _gate(enabled=False)
    R.gate_function(mod, "run_book", g)
    assert mod.run_book(sig, cal, 7) == orig                     # 끈 판 = 원판(난수 흐름까지)
    g.enabled = True
    on = mod.run_book(sig, cal, 7)
    assert [x for x in on if x[0] == 2 and x[1] == "A"] == []    # 2 일 은행(A) 빠짐
    assert [x[:2] for x in on if x[0] == 1] == [x[:2] for x in orig if x[0] == 1]


def test_gate_source_requires_shuffle_line():
    src = "def f(x, gd):\n    todays = list(x.get(gd, []))\n    return todays\n"
    _, n = R.gate_source(src)
    assert n == 0


def test_match_dropped():
    base = [("2020-01-06", "A", 0.05), ("2020-01-06", "B", -0.02), ("2020-01-07", "A", 0.01)]
    assert R.match_dropped(base, [("2020-01-06", "A", "은행")]) == [0.05]


# ── 산출 대조 — 관문 끈 판 = 성적표 books ────────────────────────────────────

def test_base_books_match_scoreboard():
    if not os.path.exists(RESULT_JSON):
        pytest.skip("결과 파일 없음")
    res = json.load(open(RESULT_JSON))
    chk = res["check_scoreboard"]
    assert set(chk) == {"kojiro", "donchian", "vcp", "bfb", "vb", "etf_trend", "mr_band", "mr_fkeep"}
    assert all(v is not None and v <= 0.5 for v in chk.values()), chk
