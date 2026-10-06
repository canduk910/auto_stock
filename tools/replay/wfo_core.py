"""주기적 재조정(걷기 전진) 공통 층 — 사전 등록 ``_workspace/analysis/wfo_20261006/prereg.md`` §1·§3·§4.

전략 어댑터(``wfo_<전략>.py``)가 조합마다 **전체 기간 모집단 거래**를 ``Trades`` 로 넘기면, 이 파일이
해마다 학습 창에서 조합을 고르고(§1-4) · 표본 밖 거래를 이어 붙이고(§1-6) · 판정(§3)과 안정성(§4)을 낸다.
계좌는 전략마다 다르므로 어댑터가 돌리고, 여기서는 씨앗별 일별 자산을 받아 요약만 한다.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from replay.audit import config as C

BOOT_SEED = C.BOOT_SEED          # 20261005
N_BOOT = C.N_BOOT                # 2000
DIFF_BOOT = 20000
P1_LO = C.P1_LO                  # −0.2%
P3_MDD = C.P3_MDD                # −35%
TRAIN_YEARS = 10
OOS_YEARS = tuple(range(2007, 2027))
ERAS = (("2007-01-01", "2011-12-31"), ("2012-01-01", "2016-12-31"), ("2017-01-01", "2021-12-31"),
        ("2022-01-01", "2026-12-31"))
OPEN_GD = 10 ** 9                # 청산 안 된 거래(데이터 끝까지 보유)의 청산 gd
INDEX_CSV = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long/index/market_unit_series.csv"


# ── 거래 묶음 ───────────────────────────────────────────────────────────────

@dataclass
class Trades:
    """한 조합의 전체 기간 모집단. 진입 gd 오름차순일 필요는 없다."""
    gin: np.ndarray                  # 진입 gd(공통 달력 색인)
    gout: np.ndarray                 # 청산 gd(열린 채 끝나면 OPEN_GD)
    r: np.ndarray                    # 거래당 순수익(주 비용)
    ck: np.ndarray                   # 군집 키 문자열 "종목|ISO연-W주"(``audit.judge.iso_week_key``)
    extra: dict = field(default_factory=dict)   # 판(VB 비관판 등) 이름 → 순수익 배열

    def __post_init__(self):
        self.gin = np.asarray(self.gin, dtype=np.int64)
        self.gout = np.asarray(self.gout, dtype=np.int64)
        self.r = np.asarray(self.r, dtype=float)
        self.ck = np.asarray(self.ck, dtype=object)
        assert len(self.gin) == len(self.gout) == len(self.r) == len(self.ck)

    def __len__(self):
        return len(self.r)

    def take(self, mask) -> "Trades":
        return Trades(self.gin[mask], self.gout[mask], self.r[mask], self.ck[mask],
                      {k: v[mask] for k, v in self.extra.items()})

    def values(self, version: str = "r") -> np.ndarray:
        return self.r if version == "r" else self.extra[version]


def concat(parts: "list[Trades]") -> Trades:
    if not parts:
        return Trades(np.zeros(0, int), np.zeros(0, int), np.zeros(0), np.zeros(0, object))
    keys = set(parts[0].extra)
    return Trades(np.concatenate([p.gin for p in parts]), np.concatenate([p.gout for p in parts]),
                  np.concatenate([p.r for p in parts]), np.concatenate([p.ck for p in parts]),
                  {k: np.concatenate([p.extra[k] for p in parts]) for k in keys})


def week_keys(tickers, gds, cal: pd.DatetimeIndex) -> np.ndarray:
    iso = {}
    out = np.empty(len(gds), dtype=object)
    for i, (t, g) in enumerate(zip(tickers, gds)):
        g = int(g)
        if g not in iso:
            y, w, _ = cal[g].date().isocalendar()
            iso[g] = f"{y}-W{w:02d}"
        out[i] = f"{t}|{iso[g]}"
    return out


# ── 통계 ────────────────────────────────────────────────────────────────────

def cluster_boot(values, keys, *, n_boot: int = N_BOOT, seed: int = BOOT_SEED, q: float = C.BOOT_Q):
    """``audit.judge.cluster_bootstrap(order="sorted")`` 와 같은 값(같은 난수 소비) — 키 정렬을 np.unique 로."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    est = float(v.mean())
    uk, idx = np.unique(np.asarray(keys, dtype=object).astype(str), return_inverse=True)
    K = len(uk)
    if K < 2:
        return est, float("nan"), float("nan")
    s1 = np.bincount(idx, weights=v, minlength=K)
    s0 = np.bincount(idx, minlength=K).astype(float)
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    stat = np.einsum("ij,j->i", cnt, s1) / np.einsum("ij,j->i", cnt, s0)
    return est, float(np.percentile(stat, 100 * q)), float(np.percentile(stat, 100 * (1 - q)))


def month_block_diff(a_r, a_months, b_r, b_months, *, n_boot: int = DIFF_BOOT, seed: int = BOOT_SEED,
                     qs=(0.05,)) -> dict:
    """``bfb_vcp_opt.month_block_diff`` 와 같은 식(달력 월 블록 · 같은 월 집합 · A 평균 − B 평균)."""
    months = sorted(set(a_months) | set(b_months))
    ix = {m: i for i, m in enumerate(months)}
    K = len(months)

    def sums(r, ms):
        idx = np.fromiter((ix[m] for m in ms), dtype=np.int64, count=len(ms))
        return (np.bincount(idx, weights=np.asarray(r, float), minlength=K),
                np.bincount(idx, minlength=K).astype(float))
    a1, a0 = sums(a_r, a_months)
    b1, b0 = sums(b_r, b_months)
    est = a1.sum() / a0.sum() - b1.sum() / b0.sum()
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        st = (np.einsum("ij,j->i", cnt, a1) / np.einsum("ij,j->i", cnt, a0)
              - np.einsum("ij,j->i", cnt, b1) / np.einsum("ij,j->i", cnt, b0))
    st = st[np.isfinite(st)]
    return {"est": float(est), "months": K, "n_boot_valid": int(len(st)),
            "lower": {f"{q:.6g}": float(np.quantile(st, q)) for q in qs}}


def months_of(tr: Trades, cal: pd.DatetimeIndex) -> list:
    ym = cal.strftime("%Y-%m")
    return [ym[g] for g in tr.gin]


def stat(tr: Trades, cal, version: str = "r", boot: bool = True) -> dict:
    v = tr.values(version)
    out = {"n": int(len(v))}
    if len(v) == 0:
        return out
    out.update(mean=float(v.mean()), median=float(np.median(v)), win=float((v > 0).mean()))
    if boot and len(v) >= 2:
        _, lo, hi = cluster_boot(v, tr.ck)
        out.update(lo90=lo, hi90=hi)
    return out


# ── 해 경계 ─────────────────────────────────────────────────────────────────

class YearIndex:
    def __init__(self, cal: pd.DatetimeIndex, end: str = "2026-10-02"):
        self.cal = cal
        self.end_gd = int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1

    def first(self, y: int) -> int:
        return int(self.cal.searchsorted(pd.Timestamp(f"{y}-01-01")))

    def last(self, y: int) -> int:
        return min(int(self.cal.searchsorted(pd.Timestamp(f"{y}-12-31"), side="right")) - 1, self.end_gd)

    def train_mask(self, tr: Trades, y: int, years: int = TRAIN_YEARS) -> np.ndarray:
        a, b, d = self.first(y - years), self.last(y - 1), self.first(y)
        return (tr.gin >= a) & (tr.gin <= b) & (tr.gout < d)

    def oos_mask(self, tr: Trades, y: int) -> np.ndarray:
        return (tr.gin >= self.first(y)) & (tr.gin <= self.last(y))

    def win_mask(self, tr: Trades, a: str, b: str) -> np.ndarray:
        g0 = int(self.cal.searchsorted(pd.Timestamp(a)))
        g1 = min(int(self.cal.searchsorted(pd.Timestamp(b), side="right")) - 1, self.end_gd)
        return (tr.gin >= g0) & (tr.gin <= g1)


# ── 선택 ────────────────────────────────────────────────────────────────────

def n_changed(cfg: dict, base: dict) -> int:
    return sum(1 for k in base if cfg.get(k) != base.get(k))


def score_lo90(tr: Trades) -> "tuple[float, float]":
    if len(tr) < 2:
        return float("nan"), float(tr.r.mean()) if len(tr) else float("nan")
    est, lo, _ = cluster_boot(tr.r, tr.ck)
    return lo, est


def score_min_lo90(versions=("r", "pes")):
    """VB — min(낙관판 하한, 비관판 하한), 평균은 낙관판."""
    def f(tr: Trades):
        if len(tr) < 2:
            return float("nan"), float("nan")
        los = [cluster_boot(tr.values(v), tr.ck)[1] for v in versions]
        return float(min(los)), float(tr.values(versions[0]).mean())
    return f


def select_year(yi: YearIndex, y: int, combos: "list[str]", trades: "dict[str, Trades]", cfgs: "dict[str, dict]",
                base_cfg: dict, min_tpy: float, current_id: str, score_fn=score_lo90) -> dict:
    """§1-3·4 — 자격 조합 중 학습 점수 최대. 반환 = 고른 id · 표(조합별 학습 n · 점수 · 평균)."""
    rows = []
    for ci, cid in enumerate(combos):
        tr = trades[cid].take(yi.train_mask(trades[cid], y))
        n = len(tr)
        elig = n >= min_tpy * TRAIN_YEARS
        sc, mn = score_fn(tr) if elig else (float("nan"), float(tr.r.mean()) if n else float("nan"))
        rows.append({"id": cid, "order": ci, "n": n, "eligible": bool(elig), "score": sc, "mean": mn,
                     "changed": n_changed(cfgs[cid], base_cfg)})
    el = [r for r in rows if r["eligible"] and np.isfinite(r["score"])]
    if not el:
        return {"year": y, "chosen": current_id, "fallback": True, "n_eligible": 0, "rows": rows}
    best = min(el, key=lambda r: (-r["score"], -r["mean"], r["changed"], r["order"]))
    return {"year": y, "chosen": best["id"], "fallback": False, "n_eligible": len(el), "rows": rows,
            "chosen_score": best["score"], "chosen_train_mean": best["mean"], "chosen_train_n": best["n"]}


def select_year_by_metric(y: int, combos, metric: "dict[str, float]", elig: "dict[str, bool]", cfgs, base_cfg,
                          current_id: str) -> dict:
    """대안 규칙(§1-5) — 미리 계산한 학습 MAR 로 고른다."""
    el = [(cid, i) for i, cid in enumerate(combos) if elig[cid] and np.isfinite(metric[cid])]
    if not el:
        return {"year": y, "chosen": current_id, "fallback": True}
    cid, _ = min(el, key=lambda x: (-metric[x[0]], n_changed(cfgs[x[0]], base_cfg), x[1]))
    return {"year": y, "chosen": cid, "fallback": False, "metric": float(metric[cid])}


def stitch(yi: YearIndex, path: "dict[int, str]", trades: "dict[str, Trades]") -> Trades:
    return concat([trades[path[y]].take(yi.oos_mask(trades[path[y]], y)) for y in sorted(path)])


def fixed(yi: YearIndex, cid: str, trades: "dict[str, Trades]", years=OOS_YEARS) -> Trades:
    return stitch(yi, {y: cid for y in years}, trades)


# ── 계좌 요약 ───────────────────────────────────────────────────────────────

def cal_years(cal, g0: int, g1: int) -> float:
    return max((cal[g1] - cal[g0]).days, 1) / 365.25


def curve_stats(eq: np.ndarray, start_equity: float, years: float) -> dict:
    e = np.concatenate([[start_equity], np.asarray(eq, float)])
    cagr = float((e[-1] / start_equity) ** (1 / years) - 1) if e[-1] > 0 else -1.0
    mdd = float((e / np.maximum.accumulate(e) - 1).min())
    return {"cagr": cagr, "mdd": mdd, "total": float(e[-1] / start_equity - 1)}


def book_summary(equities: "list[np.ndarray]", dates: pd.DatetimeIndex, start_equity: float,
                 fills: "list[int] | None" = None, eras=ERAS) -> dict:
    """씨앗별 일별 자산(같은 날짜 축) → 연 복리·낙폭 씨앗 중앙 + 시대 구간(구간 시작 평가액 기준)."""
    yrs = max((dates[-1] - dates[0]).days, 1) / 365.25
    per = [curve_stats(eq, start_equity, yrs) for eq in equities]
    out = {"cagr_median": float(np.median([p["cagr"] for p in per])),
           "cagr_min": float(np.min([p["cagr"] for p in per])), "cagr_max": float(np.max([p["cagr"] for p in per])),
           "mdd_median": float(np.median([p["mdd"] for p in per])), "per_seed_cagr": [p["cagr"] for p in per],
           "years": yrs}
    if fills is not None:
        out["fills_per_year_median"] = float(np.median(fills) / yrs)
    er = {}
    for a, b in eras:
        m = (dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(b))
        if not m.any():
            continue
        i0, i1 = int(np.argmax(m)), int(len(m) - 1 - np.argmax(m[::-1]))
        cg, md = [], []
        for eq in equities:
            s = float(eq[i0 - 1]) if i0 > 0 else start_equity
            seg = eq[i0:i1 + 1]
            y = max((dates[i1] - (dates[i0 - 1] if i0 > 0 else dates[i0])).days, 1) / 365.25
            st_ = curve_stats(seg, s, y) if s > 0 else {"cagr": -1.0, "mdd": -1.0}
            cg.append(st_["cagr"])
            md.append(st_["mdd"])
        er[f"{a[:4]}–{b[:4]}"] = {"cagr_median": float(np.median(cg)), "mdd_median": float(np.median(md))}
    out["eras"] = er
    out["P2_pass"] = bool(out["cagr_median"] > 0 and out["mdd_median"] >= P3_MDD)
    return out


def index_stats(a: str = "2007-01-02", b: str = "2026-10-02", eras=ERAS) -> dict:
    s = pd.read_csv(INDEX_CSV, parse_dates=["date"]).set_index("date")["close"].dropna()
    s = s[~s.index.duplicated()]

    def one(a_, b_):
        prev = s[s.index < pd.Timestamp(a_)]
        seg = s[(s.index >= pd.Timestamp(a_)) & (s.index <= pd.Timestamp(b_))]
        if len(seg) < 2:
            return None
        base = float(prev.iloc[-1]) if len(prev) else float(seg.iloc[0])
        yrs = max((seg.index[-1] - (prev.index[-1] if len(prev) else seg.index[0])).days, 1) / 365.25
        return curve_stats(seg.to_numpy(float) / base, 1.0, yrs)
    return {"all": one(a, b), "eras": {f"{x[:4]}–{y[:4]}": one(x, min(y, b)) for x, y in eras}}


# ── 학습 MAR(대안 규칙) ─────────────────────────────────────────────────────

def chained_mar(yearly_curves: "dict[int, np.ndarray]", years: "list[int]", start_equity: float) -> float:
    """해마다 C7 로 새로 시작한 1년 계좌 일별 자산 → 시작 자산으로 정규화해 이어 붙인 곡선의 연 복리 ÷ |낙폭|."""
    curve, level = [], 1.0
    for y in years:
        e = yearly_curves.get(y)
        if e is None or len(e) == 0:
            continue
        curve.append(level * np.asarray(e, float) / start_equity)
        level = float(curve[-1][-1])
    if not curve:
        return float("nan")
    c = np.concatenate([[1.0], np.concatenate(curve)])
    yrs = len(years)
    cagr = float(c[-1] ** (1 / yrs) - 1) if c[-1] > 0 else -1.0
    mdd = float((c / np.maximum.accumulate(c) - 1).min())
    return cagr / max(abs(mdd), 1e-4)


# ── 판정 · 안정성 ───────────────────────────────────────────────────────────

def judge(wfo: Trades, cur: Trades, cal, book: dict, version: str = "r") -> dict:
    s = stat(wfo, cal, version)
    p1 = bool(s.get("mean", -1) > 0 and s.get("lo90", -1) > P1_LO)
    d = month_block_diff(wfo.values(version), months_of(wfo, cal), cur.values(version), months_of(cur, cal))
    p3 = bool(d["lower"]["0.05"] > 0)
    p2 = bool(book["P2_pass"])
    fails = [nm for nm, ok in (("(1)", p1), ("(2)", p2), ("(3)", p3)) if not ok]
    label = "통과" if not fails else "실패" + "".join(fails)
    if p3 and p1 and p2:
        answer = "그렇다 — 재조정이 전략을 살린다"
    elif p3:
        answer = "일부 — 재조정이 현행보다 낫지만 전략을 살리지는 못한다"
    else:
        answer = "아니다 — 재조정은 현행보다 낫다는 근거가 없다"
    return {"trade": s, "c1": p1, "c2": p2, "c3": p3, "diff_vs_current": d, "label": label, "answer": answer}


def stability(path: "dict[int, str]", sel: "dict[int, dict]", cfgs: "dict[str, dict]", trades: "dict[str, Trades]",
              yi: YearIndex, current_id: str, fixed_b_id: "str | None", min_oos_n: int = 10) -> dict:
    from scipy.stats import spearmanr
    ys = sorted(path)
    ch = [path[y] for y in ys]
    switches = sum(1 for a, b in zip(ch, ch[1:]) if a != b)
    axes = list(cfgs[ch[0]].keys())
    ax_sw = {a: sum(1 for p, q in zip(ch, ch[1:]) if cfgs[p].get(a) != cfgs[q].get(a)) for a in axes}
    rho, gap = {}, []
    for y in ys:
        rows = [r for r in sel[y]["rows"] if r["eligible"] and np.isfinite(r["score"])]
        sc, oo = [], []
        for r in rows:
            t = trades[r["id"]]
            v = t.r[yi.oos_mask(t, y)]
            if len(v) >= min_oos_n:
                sc.append(r["score"])
                oo.append(float(v.mean()))
        if len(sc) >= 5 and np.std(sc) > 0 and np.std(oo) > 0:
            rho[y] = float(spearmanr(sc, oo).correlation)
        c = path[y]
        t = trades[c]
        vo = t.r[yi.oos_mask(t, y)]
        if not sel[y].get("fallback") and len(vo):
            gap.append(sel[y]["chosen_train_mean"] - float(vo.mean()))
    rv = list(rho.values())
    return {"distinct": len(set(ch)), "switches": switches, "years": len(ys), "axis_switches": ax_sw,
            "n_current": sum(1 for c in ch if c == current_id),
            "n_fixed_b": sum(1 for c in ch if c == fixed_b_id) if fixed_b_id else None,
            "n_fallback": sum(1 for y in ys if sel[y].get("fallback")),
            "spearman_by_year": rho, "spearman_mean": float(np.mean(rv)) if rv else float("nan"),
            "spearman_pos_years": int(sum(1 for x in rv if x > 0)), "spearman_n_years": len(rv),
            "train_minus_oos_mean": float(np.mean(gap)) if gap else float("nan")}


def era_trades(tr: Trades, yi: YearIndex, cal, version: str = "r", eras=ERAS) -> dict:
    out = {}
    for a, b in eras:
        s = stat(tr.take(yi.win_mask(tr, a, b)), cal, version)
        out[f"{a[:4]}–{b[:4]}"] = {k: s.get(k) for k in ("n", "mean", "lo90")}
    return out


def js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (date, pd.Timestamp)):
        return str(o)
    return str(o)


def product_cfgs(grid: dict) -> "list[dict]":
    ks = list(grid)
    return [dict(zip(ks, v)) for v in itertools.product(*(grid[k] for k in ks))]


# ── 공통 진행기 ─────────────────────────────────────────────────────────────

def run_wfo(*, cal, combos, cfgs, trades, current_id, fixed_b_id, base_cfg, min_tpy, book_fn,
            score_fn=score_lo90, versions=("r",), years=OOS_YEARS, select_fn=None, alt_curves=None,
            alt_select_fn=None, start_equity=float(C.BUDGET_C7), log=print) -> dict:
    """§1 ~ §4 를 한 전략에 대해 돈다. ``book_fn(path, version) -> book_summary`` 는 어댑터가 준다."""
    yi = YearIndex(cal)
    sel = {}
    for y in years:
        sel[y] = select_fn(y) if select_fn else select_year(yi, y, combos, trades, cfgs, base_cfg, min_tpy,
                                                               current_id, score_fn)
        log(f"[wfo] {y} → {sel[y]['chosen']} (자격 {sel[y].get('n_eligible')}, 점수 {sel[y].get('chosen_score')})")
    path = {y: sel[y]["chosen"] for y in years}
    paths = {"wfo": path, "current": {y: current_id for y in years}}
    if fixed_b_id is not None:
        paths["fixed_b"] = {y: fixed_b_id for y in years}
    alt = None
    if alt_select_fn is not None:
        alt = {y: alt_select_fn(y) for y in years}
        paths["alt_mar"] = {y: alt[y]["chosen"] for y in years}
    elif alt_curves is not None:
        alt = {}
        for y in years:
            elig = {r["id"]: r["eligible"] for r in sel[y]["rows"]} if "rows" in sel[y] else {c: True for c in combos}
            metric = {c: chained_mar(alt_curves[c], list(range(y - TRAIN_YEARS, y)), start_equity)
                      if c in alt_curves else float("nan") for c in combos}
            alt[y] = select_year_by_metric(y, combos, metric, elig, cfgs, base_cfg, current_id)
        paths["alt_mar"] = {y: alt[y]["chosen"] for y in years}
    T = {k: stitch(yi, p, trades) for k, p in paths.items()}
    res = {"years": list(years), "path": path, "selection": {y: {k: v for k, v in s.items() if k != "rows"}
                                                            for y, s in sel.items()},
           "alt_path": paths.get("alt_mar"), "alt_selection": alt, "versions": list(versions)}
    res["trade"] = {k: {v: stat(t, cal, v) for v in versions} for k, t in T.items()}
    res["eras_trade"] = {k: {v: era_trades(t, yi, cal, v) for v in versions} for k, t in T.items()}
    res["books"] = {}
    for k, p in paths.items():
        res["books"][k] = {}
        for v in versions:
            res["books"][k][v] = book_fn(p, v)
            b = res["books"][k][v]
            log(f"[wfo] book {k}/{v} 연 {b['cagr_median']:+.4f} 낙폭 {b['mdd_median']:+.3f}")
    res["judge"] = {v: judge(T["wfo"], T["current"], cal, res["books"]["wfo"][v], v) for v in versions}
    if "alt_mar" in T:
        res["judge_alt"] = {v: judge(T["alt_mar"], T["current"], cal, res["books"]["alt_mar"][v], v) for v in versions}
    if "fixed_b" in T:
        res["diff_vs_fixed_b"] = {v: month_block_diff(T["wfo"].values(v), months_of(T["wfo"], cal),
                                                      T["fixed_b"].values(v), months_of(T["fixed_b"], cal))
                                  for v in versions}
        res["judge_fixed_b"] = {v: judge(T["fixed_b"], T["current"], cal, res["books"]["fixed_b"][v], v)
                                for v in versions}
    res["stability"] = stability(path, sel, cfgs, trades, yi, current_id, fixed_b_id)
    res["index"] = index_stats(str(cal[yi.first(years[0])].date()), str(cal[yi.end_gd].date()))
    res["by_year"] = {}
    for y in years:
        row = {}
        for k, p in paths.items():
            t = trades[p[y]]
            v = t.r[yi.oos_mask(t, y)]
            row[k] = {"n": int(len(v)), "mean": float(v.mean()) if len(v) else None}
        row["chosen"] = path[y]
        row["train_n"] = sel[y].get("chosen_train_n")
        row["train_mean"] = sel[y].get("chosen_train_mean")
        row["train_score"] = sel[y].get("chosen_score")
        res["by_year"][y] = row
    return res
