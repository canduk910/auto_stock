#!/usr/bin/env python3
"""(라) 규칙 미국 이식 + 무료 시장 폭 대용 (사전 등록 ``ra_us_breadth_20261006/prereg.frozen.md``).

앞 연구 ``ra_us`` 는 미국 폭 자료가 없어 조건2(폭 ≤ 0.3)를 「항상 거짓」 으로 두었다(= 폭 없는 판 A).
여기서는 조건2 자리에 무료 대용 폭 X 를 넣는다 — P0 진짜 폭(S5FI·NDFI, 50일선 위 비율) · P1 AR60(상승 비율
60일 평균) · P2 동일가중 ÷ 시가총액가중의 60일 평균 대비 위치. 문턱 = 한국 「폭 ≤ 0.3」 의 한국 학습 창
분위 ``p_K`` 를 미국 학습 창 X 분포에 옮긴 값(학습 구간만 쓴다).

판 = TR 이식판(칸 행동 원판 그대로, 주판) · RL 재학습판(칸 행동만 미국 학습) · S1/S2 분위 ±10%p ·
S3 누적 A/D 선 · SV 생존 편향 참고판. 엔진·판정·부트스트랩 = ``ra_us`` 그대로.

    python tools/replay/ra_us_breadth.py <out_dir>
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc_b as GB  # noqa: E402
from replay import ra_us as R  # noqa: E402
from replay import ra_us_breadth_data as D  # noqa: E402
from replay import regime_gate as RG  # noqa: E402
from replay import regime_gate_alloc as RA  # noqa: E402
from replay import regime_v2 as V  # noqa: E402

US_WINS = R.US_WINS
KR_T = RG.WINS["T"]
KR_TH = 0.3
Q_SHIFT = 0.10
N_BONF = 24
PROXIES = ("P0", "P1", "P2")
PROXY_NAMES = {"P0": "진짜 폭(50일선 위 비율)", "P1": "상승 종목 비율 60일 평균", "P2": "동일가중 ÷ 시가총액가중 60일 위치",
               "S3": "누적 A/D 선 − 60일 평균", "SV": "현 구성 종목 60일선 위 비율(생존 편향)"}
PAIR = {"P0": {"SPX": "S&P500 50일선 위 비율(S5FI)", "NDX": "나스닥100 50일선 위 비율(NDFI)"},
        "P1": {"SPX": "NYSE 상승·하락 종목 수", "NDX": "NASDAQ 상승·하락 종목 수"},
        "P2": {"SPX": "RSP ÷ SPY(수정 종가)", "NDX": "^NDXE ÷ ^NDX(가격)"}}
SB_RAUS = "_workspace/analysis/ra_us_20261006/scoreboard_entries.json"
REFS = ("hold", "fix075", "A")


# ═════════════════════════════════ 문턱 ═════════════════════════════════

def korea_quantile() -> float:
    """p_K = 한국 학습 창 KRX 거래일 중 원판 폭(R5) ≤ 0.3 인 날 비율."""
    m = V.load_mkt()
    br = V.load_breadth(m)
    sel = (m.dates >= pd.Timestamp(KR_T[0])) & (m.dates <= pd.Timestamp(KR_T[1]))
    x = br[sel].dropna()
    return float((x <= KR_TH).mean())


def train_threshold(xa: pd.Series, q: float, win=US_WINS["T"]) -> float:
    """미국 학습 창 KRX 거래일 중 X 가 있는 날의 q 분위수(학습 구간 밖 값은 쓰지 않는다)."""
    idx = xa.index
    sel = (idx >= pd.Timestamp(win[0])) & (idx <= pd.Timestamp(win[1]))
    vals = xa[sel].dropna().to_numpy(float)
    if len(vals) == 0:
        raise ValueError("학습 창에 대용 폭 값이 없다")
    return float(np.quantile(vals, q))


def proxy_series(px: str, asset: str) -> pd.Series:
    return {"P0": D.p0, "P1": D.p1, "P2": D.p2, "S3": D.p1_adl, "SV": D.sv}[px](asset)


def aligned(s: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    return R.align_before(s.to_frame("x"), dates)["x"]


def rule_of(thr: float):
    return (("T7", ">", 0.0), ("BX", "<=", float(thr)))


# ═════════════════════════════════ 판 실행 ═════════════════════════════════

def window_mask(dates, win):
    return (dates >= pd.Timestamp(win[0])) & (dates <= pd.Timestamp(win[1]))


def diag(dates, keys: np.ndarray, expo: np.ndarray, expoA: np.ndarray, wins: dict) -> dict:
    out = {}
    for wn, win in wins.items():
        s = window_mask(dates, win)
        k = keys[s]
        out[wn] = {"breadth_low": float(np.mean([x[1] == "1" for x in k])),
                   "cell01": float(np.mean(k == "01")), "cell11": float(np.mean(k == "11")),
                   "same_as_A": float(np.mean(expo[s] == expoA[s]))}
    return out


def sub_metrics(dates, value, d0) -> dict | None:
    """FULLD — FULL 곡선을 자료 시작일 d0 부터 잘라 잰 연복리·MDD·MAR."""
    s = pd.Series(np.asarray(value, float), index=pd.DatetimeIndex(dates))
    before = s.loc[:d0 - pd.Timedelta(days=1)]
    seg = s.loc[d0:]
    if len(seg) < 2:
        return None
    x0 = before.iloc[-1] if len(before) else seg.iloc[0]
    t0 = before.index[-1] if len(before) else seg.index[0]
    x = np.r_[x0, seg.to_numpy()]
    y = (seg.index[-1] - t0).days / 365.25
    cg = float((x[-1] / x[0]) ** (1 / y) - 1)
    mdd = float((x / np.maximum.accumulate(x) - 1).min())
    return {"start": str(seg.index[0].date()), "cagr": cg, "mdd": mdd, "mar": cg / abs(mdd) if mdd < 0 else None}


def reproduce_A(run: R.Runner, asset: str, ccy: str) -> float:
    path = os.path.join(os.path.dirname(os.path.dirname(_HERE)), SB_RAUS)
    ent = next(e for e in json.load(open(path))["entries"] if e["id"] == f"RAUS_{asset}_{ccy}_A")
    cum = np.asarray(ent["curve"]["cum"], float)
    v = np.asarray(run.res["A"]["windows"]["FULL"]["value"], float)
    if len(cum) != len(v):
        return float("inf")
    return float(np.max(np.abs(v / v[0] / cum - 1)))


def us_stage(pK: float, with_sv: bool = True) -> dict:
    df = pd.read_parquet(R.PARQUET)
    mk = {"U": GB.load(df, "U"), "H": GB.load(df, "H", hedged=True)}
    dates = mk["U"].dates
    out, meta = {}, {"thresholds": {}, "starts": {}, "repro": {}}
    for asset in R.ASSETS:
        f = R.us_features(asset, dates)
        keysA = V.rule_keys(f, R.RULE_RA)                       # 폭 결측 = 거짓 → ra_us 의 A
        expoA = R.expo_of(keysA, R.MAP_RA)
        prox = {}
        for px in PROXIES + ("S3",) + (("SV",) if with_sv else ()):
            try:
                prox[px] = aligned(proxy_series(px, asset), dates)
            except Exception as e:                               # SV 재료 없음 등
                print(f"[rausb] {asset} {px} 대용 폭 없음 — {e}", flush=True)
        plans = {}                                               # name -> (keys, thr, px, kind)
        for px, xa in prox.items():
            first = xa.dropna().index.min()
            meta["starts"][f"{px}_{asset}"] = str(first.date())
            fx = f.copy()
            if px == "S3":
                fx["BX"] = xa
                plans["S3"] = (V.rule_keys(fx, (("T7", ">", 0.0), ("BX", "<=", 0.0))), 0.0, px, "S3")
                continue
            qs = {"": pK} if px == "SV" else {"": pK, "_qm": pK - Q_SHIFT, "_qp": pK + Q_SHIFT}
            for sfx, q in qs.items():
                thr = train_threshold(xa, q)
                meta["thresholds"][f"{px}{sfx}_{asset}"] = {"q": q, "thr": thr}
                fx["BX"] = xa
                plans[f"TR_{px}{sfx}"] = (V.rule_keys(fx, rule_of(thr)), thr, px, "TR")
            if px == "SV":
                fx["BX"] = xa
                plans["TR_SV_lit"] = (V.rule_keys(fx, rule_of(KR_TH)), KR_TH, px, "TR")
                meta["thresholds"][f"SV_lit_{asset}"] = {"q": None, "thr": KR_TH}
        for ccy in R.CCYS:
            t0 = time.time()
            m = mk[ccy]
            run = R.Runner(m, asset, US_WINS, R.US_ERAS)
            run.baselines()
            run.run_expo("A", expoA, {"rule": "폭 없음(ra_us A)"})
            err = reproduce_A(run, asset, ccy)
            meta["repro"][f"{asset}_{ccy}"] = err
            print(f"[rausb] 재현 {asset}/{ccy} A 곡선 오차 {err:.2e}", flush=True)
            if not err < 1e-9:
                raise SystemExit(f"[rausb] RAUS_{asset}_{ccy}_A 재현 불일치 — 멈춘다")
            judged = []
            for nm, (keys, thr, px, kind) in plans.items():
                expo = R.expo_of(keys, R.MAP_RA)
                ext = {"proxy": px, "thr": thr, "map": dict(R.MAP_RA), "kind": kind,
                       "diag": diag(dates, keys, expo, expoA, US_WINS)}
                r = run.run_expo(nm, expo, ext)
                r["fulld"] = sub_metrics(r["windows"]["FULL"]["dates"], r["windows"]["FULL"]["value"],
                                         pd.Timestamp(meta["starts"][f"{px}_{asset}"]))
                judged.append(nm)
                if nm in tuple(f"TR_{p}" for p in PROXIES):
                    lr = R.learn(m, keys, US_WINS["T"], run.ix, run.il)
                    expo2 = R.expo_of(keys, lr["map"])
                    rn = "RL_" + px
                    r2 = run.run_expo(rn, expo2, {"proxy": px, "thr": thr, "map": lr["map"], "learn": lr["detail"],
                                                  "kind": "RL", "diag": diag(dates, keys, expo2, expoA, US_WINS)})
                    r2["fulld"] = sub_metrics(r2["windows"]["FULL"]["dates"], r2["windows"]["FULL"]["value"],
                                              pd.Timestamp(meta["starts"][f"{px}_{asset}"]))
                    judged.append(rn)
            for nm in judged:
                vs = {}
                for ref in REFS:
                    bt = {}
                    for wn in ("T", "V", "H"):
                        mo = run.res[nm]["windows"][wn]["monthly"]
                        mb = run.res[ref]["windows"][wn]["monthly"]
                        bt[wn] = R.boot(mo["r"].to_numpy(), mb["r"].to_numpy(), mb["cash"].to_numpy(),
                                        n_bonf=N_BONF)
                    vs[ref] = {"boot": bt, "judge": R.judge(bt["V"], bt["H"])}
                run.res[nm]["vs"] = vs
            out[(asset, ccy)] = run
            rr = run.res
            print(f"[rausb] {asset}/{ccy} " + " · ".join(
                f"{p} V {rr[p]['windows']['V']['metrics']['cagr']:+.3f} {rr[p]['vs']['hold']['judge']}/"
                f"{rr[p]['vs']['A']['judge']}" for p in ("TR_P0", "TR_P1", "TR_P2")) +
                f" · {time.time() - t0:.0f}s", flush=True)
    return {"runs": out, "meta": meta}


# ═════════════════════════════════ 산출 ═════════════════════════════════

MAIN_PLANS = tuple(f"{k}_{p}" for k in ("TR", "RL") for p in PROXIES)
SENS_PLANS = tuple(f"TR_{p}{s}" for p in PROXIES for s in ("_qm", "_qp")) + ("S3",)
SV_PLANS = ("TR_SV", "TR_SV_lit")


def plan_desc(nm: str, asset: str, r: dict) -> str:
    kind, px = nm.split("_")[0], nm.split("_")[1]
    head = (f"(라) 규칙 미국 이식 + 무료 시장 폭 대용 {px}({PAIR[px][asset]}) — 120일선 20일 기울기 > 0 × "
            f"대용 폭 ≤ {r['thr']:.4g}(한국 「폭 ≤ 0.3」 의 학습 분위를 미국 학습 창에 옮긴 문턱)")
    if kind == "TR":
        return head + " · 칸 행동 원판 그대로(오름·폭 건강 2배 · 내림·폭 무너짐 1배 · 나머지 현금)"
    return head + f" · 칸 행동 미국 1995~2012 재학습 {r['map']}"


def build_entries(SB, us: dict, rf, bench) -> list:
    entries = []
    gt = "(라) 장세 규칙 미국 이식 + 무료 시장 폭(ra_us_breadth) · 참고"
    ref = "_workspace/analysis/ra_us_breadth_20261006/result.md"
    for (asset, ccy), run in us.items():
        for nm in MAIN_PLANS:
            r = run.res[nm]
            w = r["windows"]["FULL"]
            d, v = w["dates"], w["value"]
            mt = SB.compute_metrics(d, v, rf, bench)
            r["full_sb"] = mt
            kind, px = nm.split("_")
            entries.append({
                "id": f"RAUSB_{px}_{asset}_{ccy}_{kind}",
                "name": f"{R.ASSET_NAMES[asset]}({R.CCY_NAMES[ccy]}) (라)+{'진짜 폭' if px == 'P0' else '대용 폭'} {px} "
                        f"{'이식' if kind == 'TR' else '재학습'}",
                "desc": plan_desc(nm, asset, r) + f" · 2배 = 일일 리셋 모형({'환 1배' if ccy == 'U' else '환헤지'}) · "
                        f"비용 왕복 0.38% · 대용 폭 자료 시작({run.res[nm]['fulld']['start'] if r.get('fulld') else '-'}) "
                        f"전은 폭 조건 거짓",
                "group": "ra_us_breadth", "group_title": gt, "status": "참고", "status_ref": ref,
                "source": "tools/replay/ra_us_breadth.py",
                "period": [str(d[0].date()), str(d[-1].date())],
                "curve": {"dates": [str(x.date()) for x in d], "cum": [float(x / v[0]) for x in v]},
                "yearly": {str(y): x["ret"] for y, x in mt["yearly"].items()},
                "turnover_yr": w["metrics"]["turnover_yr"], "cost_yr": w["metrics"]["cost_yr"],
                "after_tax_cagr": r["after_tax_cagr"],
                "tax_note": "해외 지수·2배 차익 15.4% · 현금 이자 15.4%"})
    return entries


def summarize(run: R.Runner, names) -> dict:
    out = {}
    for nm in names:
        if nm not in run.res:
            continue
        r = run.res[nm]
        row = {"windows": {wn: x["metrics"] for wn, x in r["windows"].items()}, "eras": r.get("eras"),
               "crises": r.get("crises"), "after_tax_cagr": r.get("after_tax_cagr")}
        for k in ("proxy", "thr", "map", "kind", "diag", "vs", "fulld", "full_sb", "learn"):
            if k in r:
                row[k] = r[k]
        out[nm] = row
    return out


def main(out_dir: str, with_sv: bool = True) -> None:
    from replay import scoreboard as SB
    t0 = time.time()
    pK = korea_quantile()
    print(f"[rausb] p_K = {pK:.4f}", flush=True)
    st = us_stage(pK, with_sv)
    us = st["runs"]
    mk = V.load_mkt()
    rf = pd.Series(np.cumprod(1 + mk.ret[:, GB.I_CASH]), index=mk.dates)
    ik = GB.COLS.index("K200")
    bench = pd.Series(np.cumprod(1 + (mk.ret[:, ik] - mk.fee[:, ik])), index=mk.dates)
    entries = build_entries(SB, us, rf, bench)
    allp = ("hold", "lev2", "fix050", "fix075", "b6040", "A") + MAIN_PLANS + SENS_PLANS + SV_PLANS
    for run in us.values():
        for nm in allp:
            if nm in run.res and "full_sb" not in run.res[nm]:
                w = run.res[nm]["windows"]["FULL"]
                run.res[nm]["full_sb"] = SB.compute_metrics(w["dates"], w["value"], rf, bench)
    res = {"meta": {"prereg_sha256": open(os.path.join(out_dir, "prereg.sha256")).read().split()[0],
                    "p_K": pK, "us_wins": US_WINS, **st["meta"], "sources": D.source_table(),
                    "sv_coverage": {a: D.sv_coverage(a) for a in R.ASSETS} if with_sv else None},
           "us": {f"{a}_{c}": summarize(run, allp) for (a, c), run in us.items()}}
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(R._clean(res), fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump({"source": "ra_us_breadth 2026-10-06 · tools/replay/ra_us_breadth.py "
                             "(_workspace/analysis/ra_us_breadth_20261006/result.md)",
                   "entries": [R._clean_entry(e) for e in entries]}, fh, ensure_ascii=False)
    scr = os.path.join(RG.SCRATCH_ROOT, "ra_us_breadth")
    os.makedirs(scr, exist_ok=True)
    with open(os.path.join(scr, "runs.pkl"), "wb") as fh:
        pickle.dump({k: v.res for k, v in us.items()}, fh)
    print(f"[rausb] 끝 · 성적표 항목 {len(entries)} · {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], with_sv="--no-sv" not in sys.argv)
