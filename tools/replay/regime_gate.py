#!/usr/bin/env python3
"""장세별 매매 중단 연구 — 개별 전략 7개 (사전 등록 ``regime_gate_20261006/prereg.frozen.md`` §1).

「쉰다」 = 진입 세션의 6장세 라벨(D−1 종가까지, ``market_regime_label.session_labels``)이 쉬는 칸이면
그 신호를 계좌에 넣지 않는다. 이미 보유한 포지션은 원래 청산 규칙대로 나간다(손절 정지 금기).

전략 신호·계좌 집행은 30년 재검증과 성적표(``scoreboard_books``)가 쓴 함수를 그대로 부른다.
신호 목록에서 쉬는 날 진입분만 빼는 것이 이 모듈이 더하는 유일한 동작이다.

    python tools/replay/regime_gate.py select <out_dir> [전략 ...]   # 학습 63조합 → 고른 집합
    python tools/replay/regime_gate.py apply <out_dir> [전략 ...]    # 고른 집합으로 T·V·H·30년 + 쉬지 않는 판
"""
from __future__ import annotations

import itertools
import json
import multiprocessing as mp
import os
import pickle
import sys
import time

for _k in ("KIS_APP_KEY_REAL", "KIS_APP_SECRET_REAL", "KIS_ACCOUNT_NO_REAL", "KIS_APP_KEY_VTS", "KIS_APP_SECRET_VTS",
           "KIS_ACCOUNT_NO_VTS", "SUPABASE_URL", "SUPABASE_KEY", "DATABASE_URL"):
    os.environ.setdefault(_k, "audit-dummy")          # 운영 전략 클래스 import 용 더미(값은 쓰이지 않는다)

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay.audit import config as C  # noqa: E402
from src.engine.market_regime_label import session_labels  # noqa: E402

MAIN_REPO = "/Users/koscom/Projects/auto_stock"
SERIES_CSV = os.path.join(MAIN_REPO, "data/archive/krx_daily_long/index/market_unit_series.csv")
SCRATCH_ROOT = os.path.dirname(C.SCRATCH)

T_WIN = ("1997-01-02", "2012-12-28")
V_WIN = ("2013-01-02", "2020-12-30")
H_WIN = ("2021-01-04", "2026-10-02")
FULL = ("1997-01-02", "2026-10-02")
WINS = {"T": T_WIN, "V": V_WIN, "H": H_WIN, "FULL": FULL}

CELLS = ("UL", "UH", "SL", "SH", "DL", "DH")
CODE = {"stable_up": "UL", "volatile_up": "UH", "stable_flat": "SL", "volatile_flat": "SH",
        "stable_down": "DL", "volatile_down": "DH"}
NAMES = {"UL": "안정상승", "UH": "변동상승", "SL": "안정횡보", "SH": "변동횡보", "DL": "안정하락", "DH": "변동하락"}
REST_CAP = 0.70
SELECT_SEEDS = tuple(range(16))


def subsets() -> list[tuple[str, ...]]:
    """쉬는 칸 집합 후보 — 0~5칸(63개). 순서 = 칸 수 오름차순 → CELLS 순서 사전식(동점 깨기 규칙과 같다)."""
    out = []
    for k in range(0, 6):
        out.extend(itertools.combinations(CELLS, k))
    return out


def set_name(s) -> str:
    return "없음" if not s else "+".join(NAMES[x] for x in s)


# ═════════════════════════════════ 라벨 ═════════════════════════════════

def label_series() -> pd.Series:
    """세션 날짜 → 6칸 코드. 날짜 D 의 라벨 = D−1 종가까지(운영 ``session_labels`` 그대로)."""
    s = pd.read_csv(SERIES_CSV)
    s = s[s.close.notna()]
    from datetime import date
    ds = [date.fromisoformat(x) for x in s.date.astype(str)]
    lab = {pd.Timestamp(d): CODE[p.label] for d, p in session_labels(ds, list(s.close.to_numpy(float)))}
    return pd.Series(lab, dtype=object).sort_index()


def state_after_close() -> pd.Series:
    """종가 날짜 t → 그 종가로 확정된 상태(= 다음 세션의 라벨). 자산배분 결정용."""
    s = pd.read_csv(SERIES_CSV)
    s = s[s.close.notna()]
    from src.engine.market_regime_label import label_after_closes
    pts = label_after_closes(list(s.close.to_numpy(float)))
    idx = pd.DatetimeIndex(pd.to_datetime(s.date))
    return pd.Series([CODE[p.label] if p else None for p in pts], index=idx, dtype=object)


def labels_on(cal: pd.DatetimeIndex, lab: pd.Series) -> np.ndarray:
    """전략 달력 날짜별 라벨(없으면 None). 보관소 달력과 지수 달력이 다른 날은 None → 쉬지 않는다."""
    return np.array([lab.get(pd.Timestamp(d)) for d in cal], dtype=object)


def rest_mask(cal_lab: np.ndarray, rest) -> np.ndarray:
    rs = set(rest)
    return np.array([x in rs for x in cal_lab], dtype=bool)


# ═════════════════════════════════ 전략 어댑터 ═════════════════════════════════
# 각 어댑터 = (cal, sigs, gd_of(sig) 또는 마스크 함수, run(sigs_kept, win, seeds) → [(seed, equity)], 날짜)
# 신호·집행 설정은 ``scoreboard_books`` 의 같은 이름 함수와 같다(현행판).

class _Grab:
    def __init__(self, mod, name):
        self.mod, self.name, self.orig, self.runs = mod, name, getattr(mod, name), None

    def __enter__(self):
        def wrap(runs, *a, **k):
            self.runs = runs
            return self.orig(runs, *a, **k)
        setattr(self.mod, self.name, wrap)
        return self

    def __exit__(self, *exc):
        setattr(self.mod, self.name, self.orig)


class Bundle:
    sid: str
    cal: pd.DatetimeIndex
    sigs: object
    deterministic: bool = False

    def entry_gd(self) -> np.ndarray:
        raise NotImplementedError

    def keep(self, mask: np.ndarray):
        raise NotImplementedError

    def run(self, sigs, win, seeds) -> "tuple[list, pd.DatetimeIndex]":
        raise NotImplementedError


class ListBundle(Bundle):
    """신호가 ``.gd``(진입 세션 전역 인덱스)를 가진 객체 목록인 전략."""

    def entry_gd(self):
        return np.array([int(s.gd) for s in self.sigs], dtype=np.int64)

    def keep(self, mask):
        return [s for s, k in zip(self.sigs, mask) if k]


class Kojiro(ListBundle):
    sid = "kojiro"

    def __init__(self):
        from replay.audit import market_unit as MU
        from replay.audit import panel as PN
        from replay.strategies import kojiro as KJ
        from replay.strategies import kojiro_opt as KO
        from replay.strategies import kojiro_run as KR
        from replay.strategies import kojiro_y30 as Y
        from src.engine.etf_like import is_etf_like
        Y.patch_fast_ewm()
        if PN.sha256(C.DB_EXTRACT) != KR.EXTRACT_SHA:
            raise SystemExit("[gate kojiro] 추출본 sha 불일치")
        ext = PN.load_db_extract()
        row = dict(zip(ext["strategy_config"][0], {r[0]: r for r in ext["strategy_config"][1]}["kojiro"]))
        p = KJ.op_params(row)
        sectors = KJ.sectors_from_master(ext["master"][0], ext["master"][1])
        df, _ = Y.load_unified(drop_flags=False)
        etf_names = sorted(n for n in df.name.dropna().unique() if is_etf_like(None, n))
        if etf_names:
            df = df[~df.name.isin(etf_names)]
        cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
        st = Y.build(df[~df.flag], cal=cal)
        del df
        kd, kc = Y.mu_series()
        m_day = MU.m_for_days(cal, kd, kc)
        pf = {**p, "stage1_freshness": 5}
        feats = {t: KJ.features(b, pf) for t, b in st.bars.items()}
        univ = {t: Y.universe_era(b) for t, b in st.bars.items()}
        fb = {t: {**f, "tech": f["tech"] & (f["ratio"] <= 0.06)} for t, f in feats.items()}
        sigs, _ = KJ.build_signals(st.bars, fb, univ, m_day, {**pf, "atr_ratio_max": 0.06}, sectors)
        self.sigs = KO.select(sigs, "cur", None)
        Y.Y30Pos.LIM = Y.limit_table(cal)
        self.cal, self.bars, self.feats, self.p, self.cost = cal, st.bars, feats, p, Y.era_cost(cal)

    def run(self, sigs, win, seeds):
        from replay.strategies import kojiro_y30 as Y
        from replay.strategies import kojiro_y30_run as R
        with _Grab(Y, "summary30") as g:
            R.run_books(sigs, self.bars, self.feats, self.p, self.cal, win, self.cost, slip=0.0, seeds=seeds)
        return [(s, r["equity"]) for s, r in zip(seeds, g.runs)], pd.DatetimeIndex(g.runs[0]["dates"])


class Donchian(ListBundle):
    sid = "donchian"

    def __init__(self):
        from replay.audit.sizing import OpSizer, load_strategy_class
        from replay.strategies import donchian_kk as DK
        from replay.strategies import donchian_kk_audit as DA
        from replay.strategies import donchian_y30 as D
        from replay.strategies import donchian_y30_data as YD
        st, m, _, _ = YD.build(D.CACHE)
        cal = st.cal
        D._CAL["cal"] = cal
        if DA.PN.sha256(DA.BRANCH_DONCHIAN) != DA.BRANCH_SHA:
            raise SystemExit("[gate donchian] 브랜치 전략 파일 sha256 불일치")
        cls = load_strategy_class(DA.BRANCH_DONCHIAN, "DonchianSwingStrategy", "y30_branch_donchian_kk")
        entry, ex, acct = D.ENTRY0, D.EXIT0, D.ACCT0
        kk = D.kk_of(ex, acct)
        feats = {t: D.features_y30(b, entry_n=entry["entry_n"], vol_mult=entry["vol_mult"], clv=entry["clv"],
                                   tv_mode="pct") for t, b in st.bars.items()}
        raw = DK.build_signals(st.bars, feats, m)
        self.sigs = D.mu_apply([s for s in raw if not DA.r_half_blocked(s.E, s.N, kk)], entry["mu"])
        self.fv = {t: D.feats_view(f, ex["chan"]) for t, f in feats.items()}
        self.op = OpSizer(cls, "donchian_swing", {"market_unit_mode": "enforce", "risk_pct": kk["risk_pct"],
                                                  "position_ratio": acct["slots"][1],
                                                  "max_positions": acct["slots"][0],
                                                  "kk_r_floor_pct": ex["r"][0], "kk_r_atr_mult": ex["r"][1]})
        self.cal, self.bars, self.kk, self.era = cal, st.bars, kk, D.Costs(cal)

    def run(self, sigs, win, seeds):
        from replay.audit import book as BK
        from replay.strategies import donchian_y30 as D
        D._CAL["cal"] = self.cal
        with _Grab(BK, "book_summary") as g:
            D.books(sigs, self.bars, self.fv, win, self.kk, self.op, self.era, seeds=seeds)
        return [(s, r["equity"]) for s, r in zip(seeds, g.runs)], pd.DatetimeIndex(g.runs[0]["dates"])


class BfbVcp(ListBundle):
    def __init__(self, kind):
        from replay.strategies import bfb_vcp_opt as OP
        from replay.strategies import y30_bfbvcp as YB
        self.sid = kind
        Y = YB.Y
        cls, featf = YB._classes(kind)
        st, meta = Y.build()
        cal = st.cal
        m, _ = Y.market_unit(cal)
        s_, e_, x_, mu_ = YB.CURRENT_ID.split("|")
        p_s = OP.params_for(kind, s_, "X0")
        feats = {t: featf(b, p_s) for t, b in st.bars.items()}
        univ = Y.universe(st, meta["ratios"], kind, mode="pct")
        entries = {e[0]: e for e in OP.entries_for(kind)}
        _, meth, cap, k = entries[e_]
        self.sigs = YB.build_signals(st.bars, feats, m, p_s, univ, method=meth, cap=cap, k=k, slip=YB.LIVE_SLIP,
                                     close_slip=0.0)
        self.p_g = OP.params_for(kind, s_, x_)
        self.mu_thr = OP.MU_THR[mu_]
        self.cls, self.st, self.feats, self.cal, self.cost = cls, st, feats, cal, YB.EraCostY(cal)

    def run(self, sigs, win, seeds):
        from replay.strategies import y30_bfbvcp as YB
        with _Grab(YB, "book_summary") as g:
            YB.run_books(sigs, self.st, self.feats, self.sid, self.p_g, self.cls, win, self.cost, mu_thr=self.mu_thr,
                         seeds=seeds)
        g0 = int(self.cal.searchsorted(pd.Timestamp(win[0])))
        return [(s, r["equity"]) for s, r in zip(seeds, g.runs)], self.cal[g0:g0 + len(g.runs[0]["equity"])]


class VB(Bundle):
    sid = "vb"

    def __init__(self):
        from replay.strategies import vb_y30_run as R
        st, meta = R.load()
        self.ctx = R.Ctx(st, meta)
        self.sizer, _ = R.vb_sizer()
        km, hold, mode, stop, filt = R.CUR
        self.sigs = R.allsig(self.ctx, km, hold, mode, stop, filt, R.FILLS["base"], "opt")
        self.cal = self.ctx.cal

    def entry_gd(self):
        return np.asarray(self.sigs["gd"], dtype=np.int64)

    def keep(self, mask):
        return {k: np.asarray(v)[mask] for k, v in self.sigs.items()}

    def run(self, sigs, win, seeds):
        from collections import defaultdict
        from replay.strategies import vb as VBm
        from replay.strategies import vb_y30_run as R
        Y = R.Y
        ctx = self.ctx
        g = R.gwin(ctx.cal, win)
        sbg = defaultdict(list)
        cd = ctx.cd
        for j in range(len(sigs["row"])):          # ``vb_y30_run.book`` 와 같은 조립(씨앗만 인자)
            gd = int(sigs["gd"][j])
            if not (g[0] <= gd <= g[1]):
                continue
            r = int(sigs["row"][j])
            t = cd.names[int(cd.tk[r])]
            sbg[gd].append(Y.BSig(t, gd, float(sigs["E"][j]), float(sigs["E"][j] * cd.raw[r]), float(sigs["px"][j]),
                                  int(sigs["why"][j]), int(sigs["xg"][j]), float(cd.C[r])))
        runs = [Y.run_book_var(sbg, self.sizer, ctx.cal, g[0], g[1], seed, start_equity=float(C.BUDGET_C7),
                               cost_rt_gd=ctx.cost, max_pos=VBm.VB_OP["max_pos"]) for seed in seeds]
        return [(s, r["equity"]) for s, r in zip(seeds, runs)], ctx.cal[g[0]:g[1] + 1]


ETF_START = "2003-01-02"


class EtfTrend(Bundle):
    sid = "etf_trend"
    deterministic = True

    def __init__(self):
        from replay import y30_etfbase_run as YR
        self.V = YR.etf_load()
        thr = 2e9 * self.V["defl"]
        self.sigs, _ = YR.gen_signals30(self.V["data"], self.V["mu"], 20, thr, self.V["anom"], self.V["lock"])
        self.cal = self.V["cal"]

    def entry_gd(self):
        return np.array([int(t["entry_ci"]) for t in self.sigs], dtype=np.int64)

    def keep(self, mask):
        return [s for s, k in zip(self.sigs, mask) if k]

    def run(self, sigs, win, seeds):
        from replay import y30_etfbase_run as YR
        from replay.strategies import etf_trend_opt as EO
        w0 = max(pd.Timestamp(win[0]), pd.Timestamp(ETF_START))
        w = (str(w0.date()), win[1])
        bk = YR.etf_book30(self.V, sigs, EO.CURRENT, w, seeds=(0,))
        g0, g1 = YR.win_idx(self.V["cal"], w)
        return [(0, bk["equity_seed0"])], self.cal[g0:g1 + 1]


class OU(Bundle):
    sid = "mr_ou"
    deterministic = True

    def __init__(self):
        from replay import y30_mr_ou as OUm
        from replay import y30_mr_ou_judge as J
        d = os.path.join(SCRATCH_ROOT, "y30mr")
        with open(os.path.join(d, "ou_stage1.pkl"), "rb") as fh:
            payload = pickle.load(fh)
        with open(os.path.join(d, "panel.pkl"), "rb") as fh:
            panel = pickle.load(fh)
        self.ctx = J.Ctx(payload, panel)
        self.sigs = payload["trades"][OUm.CURRENT]
        self.cal = pd.DatetimeIndex(np.asarray(self.ctx.dates).astype("datetime64[ns]"))

    def entry_gd(self):
        return np.asarray(self.sigs["ei"], dtype=np.int64)

    def keep(self, mask):
        return self.sigs[mask]

    def run(self, sigs, win, seeds):
        from replay import y30_mr_ou_judge as J
        acc = J.account(self.ctx, sigs, win, mode="p3")
        g0 = acc["g0"]
        eq = np.cumprod(1 + acc["daily"]) * J.C7
        return [(0, eq)], self.cal[g0:g0 + len(eq)]


ADAPTERS = {"kojiro": Kojiro, "donchian": Donchian, "vcp": lambda: BfbVcp("vcp"), "bfb": lambda: BfbVcp("bfb"),
            "vb": VB, "etf_trend": EtfTrend, "mr_ou": OU}
ORDER = ("kojiro", "donchian", "vcp", "bfb", "vb", "etf_trend", "mr_ou")


# ═════════════════════════════════ 계좌 지표 ═════════════════════════════════

def eq_metrics(eq: np.ndarray, start: float, dates: pd.DatetimeIndex) -> dict:
    e = np.r_[start, np.asarray(eq, float)]
    d0 = pd.Timestamp(dates[0]) - pd.Timedelta(days=1)
    yrs = (pd.Timestamp(dates[-1]) - d0).days / 365.25
    cg = float((e[-1] / start) ** (1 / yrs) - 1) if e[-1] > 0 else -1.0
    mdd = float((e / np.maximum.accumulate(e) - 1).min())
    return {"cagr": cg, "mdd": mdd, "mar": (cg / abs(mdd)) if mdd < 0 else float("nan"), "final": float(e[-1])}


def seed_summary(runs, start, dates) -> dict:
    per = [eq_metrics(e, start, dates) for _, e in runs]
    mars = [x["mar"] for x in per if np.isfinite(x["mar"])]
    return {"cagr_median": float(np.median([x["cagr"] for x in per])),
            "mdd_median": float(np.median([x["mdd"] for x in per])),
            "mar_median": float(np.median(mars)) if mars else float("nan"),
            "n_seeds": len(per), "per_seed": per}


# ═════════════════════════════════ 실행 ═════════════════════════════════

_B: "Bundle | None" = None
_GD_LAB = None


def _start(win) -> float:
    return float(C.BUDGET_C7)


def _one(args):
    rest, win, seeds = args
    m = ~rest_mask(_GD_LAB[_B.entry_gd()], rest) if rest else np.ones(len(_B.entry_gd()), bool)
    runs, dates = _B.run(_B.keep(m), win, seeds)
    return rest, runs, dates, int(m.sum())


def load_bundle(sid: str) -> Bundle:
    t0 = time.time()
    b = ADAPTERS[sid]()
    print(f"[gate] {sid} 신호 준비 {time.time() - t0:.0f}s · 신호 {len(b.entry_gd())}", flush=True)
    return b


def rest_ratio(cal_lab, cal, win, rest) -> float:
    g0, g1 = int(cal.searchsorted(pd.Timestamp(win[0]))), int(cal.searchsorted(pd.Timestamp(win[1]), "right")) - 1
    lab = cal_lab[g0:g1 + 1]
    ok = np.array([x is not None for x in lab])
    return float(rest_mask(lab[ok], rest).mean()) if ok.any() else float("nan")


def _pool_map(jobs, nproc):
    if nproc <= 1:
        return [_one(j) for j in jobs]
    ctx = mp.get_context("fork")
    with ctx.Pool(nproc) as pool:
        return pool.map(_one, jobs, chunksize=1)


def select(sid: str, out_dir: str, nproc: int) -> dict:
    global _B, _GD_LAB
    _B = load_bundle(sid)
    lab = label_series()
    _GD_LAB = labels_on(_B.cal, lab)
    seeds = (0,) if _B.deterministic else SELECT_SEEDS
    cands = subsets()
    jobs, skipped = [], {}
    for s in cands:
        rr = rest_ratio(_GD_LAB, _B.cal, T_WIN, s)
        if rr > REST_CAP:
            skipped[set_name(s)] = rr
            continue
        jobs.append((s, T_WIN, seeds))
    t0 = time.time()
    res = _pool_map(jobs, nproc)
    rows = []
    for rest, runs, dates, n_kept in res:
        sm = seed_summary(runs, float(C.BUDGET_C7), dates)
        rows.append({"rest": list(rest), "name": set_name(rest), "n_cells": len(rest),
                     "rest_ratio_T": rest_ratio(_GD_LAB, _B.cal, T_WIN, rest), "signals_kept": n_kept,
                     "cagr": sm["cagr_median"], "mdd": sm["mdd_median"], "mar": sm["mar_median"]})
    order = {tuple(s): i for i, s in enumerate(cands)}
    ok = [r for r in rows if np.isfinite(r["mar"])]
    best = max(ok, key=lambda r: (r["mar"], -order[tuple(r["rest"])]))
    out = {"sid": sid, "seeds": list(seeds), "n_candidates": len(rows), "skipped_rest_cap": skipped,
           "chosen": best, "rows": sorted(rows, key=lambda r: -r["mar"] if np.isfinite(r["mar"]) else 9e9),
           "elapsed_s": time.time() - t0}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"select_{sid}.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=float)
    print(f"[gate] {sid} 선택 {best['name']} · T MAR {best['mar']:+.3f} (쉬지 않음 "
          f"{next(r['mar'] for r in rows if not r['rest']):+.3f}) · {time.time() - t0:.0f}s", flush=True)
    return out


def apply(sid: str, out_dir: str, nproc: int) -> dict:
    """고른 집합 · 쉬지 않는 판 × T·V·H·30년 — 씨앗별 일별 평가액을 피클로 남긴다(부트스트랩·성적표 입력)."""
    global _B, _GD_LAB
    with open(os.path.join(out_dir, f"select_{sid}.json")) as fh:
        sel = json.load(fh)
    chosen = tuple(sel["chosen"]["rest"])
    _B = load_bundle(sid)
    _GD_LAB = labels_on(_B.cal, label_series())
    seeds = (0,) if _B.deterministic else SELECT_SEEDS
    jobs = [(r, w, seeds) for w in (T_WIN, V_WIN, H_WIN, FULL) for r in ((), chosen)]
    if not chosen:
        jobs = [(r, w, s) for (r, w, s) in jobs if not r]
    res = _pool_map(jobs, nproc)
    out = {}
    for (rest, runs, dates, n_kept), (_, win, _) in zip(res, jobs):
        wn = next(k for k, v in WINS.items() if v == win)
        tag = "gate" if rest else "base"
        out[(wn, tag)] = {"dates": [str(d.date()) for d in dates], "runs": [(int(s), np.asarray(e, float))
                                                                             for s, e in runs],
                          "n_kept": n_kept, "rest": list(rest),
                          "rest_ratio": rest_ratio(_GD_LAB, _B.cal, win, rest)}
    if not chosen:
        for wn in WINS:
            out[(wn, "gate")] = out[(wn, "base")]
    with open(os.path.join(SCRATCH_ROOT, "regime_gate", f"apply_{sid}.pkl"), "wb") as fh:
        pickle.dump({"sid": sid, "chosen": list(chosen), "start": float(C.BUDGET_C7), "res": out}, fh)
    print(f"[gate] {sid} 적용 끝 · 고른 집합 {set_name(chosen)}", flush=True)
    return out


def main():
    cmd, out_dir = sys.argv[1], sys.argv[2]
    names = sys.argv[3:] or list(ORDER)
    nproc = int(os.environ.get("GATE_NPROC", 6))
    os.makedirs(os.path.join(SCRATCH_ROOT, "regime_gate"), exist_ok=True)
    for nm in names:
        if cmd == "select":
            select(nm, out_dir, nproc)
        elif cmd == "apply":
            apply(nm, out_dir, nproc)
        else:
            raise SystemExit(cmd)


if __name__ == "__main__":
    main()
