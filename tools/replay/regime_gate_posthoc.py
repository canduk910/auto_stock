#!/usr/bin/env python3
"""장세 문 연구 — 사후 대조(동결 뒤 추가 · 판정 근거 아님, 해석 보조).

(a) 개별 전략: 「쉬는 날을 같은 비율·같은 덩어리 길이로, 시기만 무작위로」 — 창 안 쉼 마스크를 원형으로 밀어
    (밀기 폭 = 20 세션 이상) 같은 계좌를 돈다. 실제 장세 쉼이 「그냥 덜 매매함」 보다 나은지를 본다.
(b) 60/40 변형: 레버리지 상태 마스크를 30년 창 안에서 원형으로 밀어 V1·V2(90%)를 다시 돈다 —
    「안정상승이라는 시기」 가 「아무 때나 같은 일수만큼 2배」 보다 나은지를 본다.

    python tools/replay/regime_gate_posthoc.py <out_dir> [전략 ...]
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc_b as GB  # noqa: E402
from replay import regime_gate as RG  # noqa: E402
from replay import regime_gate_alloc as RA  # noqa: E402

N_SHIFT_STRAT = 100
N_SHIFT_ALLOC = 500
MIN_SHIFT = 20
SEED = 20261006

_B = None
_SIG_GD = None


def _one(args):
    win, rest_sessions, seeds = args                 # rest_sessions = 쉬는 세션 전역 인덱스 집합(배열)
    rs = np.zeros(len(_B.cal), bool)
    rs[rest_sessions] = True
    m = ~rs[_SIG_GD]
    runs, dates = _B.run(_B.keep(m), win, seeds)
    sm = RG.seed_summary(runs, 4_707_820.0, dates)
    return sm["cagr_median"], sm["mdd_median"], sm["mar_median"]


def strategy(sid, out_dir, nproc):
    global _B, _SIG_GD
    sel = json.load(open(os.path.join(out_dir, f"select_{sid}.json")))
    chosen = tuple(sel["chosen"]["rest"])
    if not chosen:
        return None
    _B = RG.load_bundle(sid)
    _SIG_GD = _B.entry_gd()
    lab = RG.labels_on(_B.cal, RG.label_series())
    seeds = (0,) if _B.deterministic else RG.SELECT_SEEDS
    rng = np.random.default_rng(SEED)
    out = {}
    for wn in ("V", "H"):
        win = RG.WINS[wn]
        g0 = int(_B.cal.searchsorted(pd.Timestamp(max(win[0], RG.ETF_START if sid == "etf_trend" else win[0]))))
        g1 = int(_B.cal.searchsorted(pd.Timestamp(win[1]), "right")) - 1
        base = RG.rest_mask(lab[g0:g1 + 1], chosen)
        n = len(base)
        jobs = [(win, g0 + np.nonzero(base)[0], seeds)]
        shifts = rng.integers(MIN_SHIFT, n - MIN_SHIFT, N_SHIFT_STRAT)
        for k in shifts:
            jobs.append((win, g0 + np.nonzero(np.roll(base, int(k)))[0], seeds))
        ctx = mp.get_context("fork")
        with ctx.Pool(nproc) as pool:
            res = pool.map(_one, jobs, chunksize=2)
        act, sh = res[0], np.array(res[1:])
        out[wn] = {"actual": {"cagr": act[0], "mdd": act[1], "mar": act[2]},
                   "shift_median": {"cagr": float(np.median(sh[:, 0])), "mdd": float(np.median(sh[:, 1])),
                                    "mar": float(np.nanmedian(sh[:, 2]))},
                   "pct_actual_cagr": float(np.mean(sh[:, 0] < act[0])),
                   "pct_actual_mar": float(np.nanmean(sh[:, 2] < act[2])), "rest_ratio": float(base.mean()),
                   "n_shift": int(len(sh))}
        print(f"[posthoc] {sid} {wn} 실제 CAGR {act[0]:+.4f} MAR {act[2]:+.3f} · 무작위 시기 중앙 "
              f"{out[wn]['shift_median']['cagr']:+.4f} / {out[wn]['shift_median']['mar']:+.3f} · 실제 백분위 "
              f"CAGR {out[wn]['pct_actual_cagr']:.2f} MAR {out[wn]['pct_actual_mar']:.2f}", flush=True)
    return out


def alloc():
    m = RA.load_market()
    st = RA.states(m)
    a, b = RA.win_ab(m, RG.FULL)
    on = np.array([x == "UL" for x in st])
    seg = on[a:b + 1].copy()
    rng = np.random.default_rng(SEED)
    shifts = rng.integers(MIN_SHIFT, len(seg) - MIN_SHIFT, N_SHIFT_ALLOC)
    fake = np.array(["UL" if x else "SL" for x in st], dtype=object)
    out = {}
    for kind in ("V1", "V2"):
        def run(s_on):
            sst = fake.copy()
            sst[a:b + 1] = np.where(s_on, "UL", "SL")
            sc, _ = RA.variant_schedule(m, kind, 0.9, "LK200", a, b, sst)
            v = GB.simulate(m, sc, a, b).value
            mt = GB.metrics(m, v, a, b)
            return mt["cagr"], mt["mar"], mt["sharpe"]
        act = run(seg)
        sh = np.array([run(np.roll(seg, int(k))) for k in shifts])
        out[kind] = {"actual": dict(zip(("cagr", "mar", "sharpe"), act)),
                     "shift_median": dict(zip(("cagr", "mar", "sharpe"), np.median(sh, axis=0).tolist())),
                     "shift_p05": dict(zip(("cagr", "mar", "sharpe"), np.percentile(sh, 5, axis=0).tolist())),
                     "shift_p95": dict(zip(("cagr", "mar", "sharpe"), np.percentile(sh, 95, axis=0).tolist())),
                     "pct_actual": dict(zip(("cagr", "mar", "sharpe"), np.mean(sh < np.array(act), axis=0).tolist())),
                     "n_shift": int(len(sh))}
        print(f"[posthoc] {kind}_90 실제 CAGR {act[0]:+.4f} MAR {act[1]:+.3f} 샤프 {act[2]:.2f} · 무작위 시기 중앙 "
              f"{out[kind]['shift_median']} · 백분위 {out[kind]['pct_actual']}", flush=True)
    # 레버리지 상태 세션의 KOSPI200(보수 뒤) 연율 수익 · 그 밖 세션
    r = m.ret[a + 1:b + 1, 0] - m.fee[a + 1:b + 1, 0]
    held = on[a - 1:b - 1]                             # 세션 t 수익 = 결정 t−2 가 t−1 종가에 집행한 보유
    out["k200_ann_on_held"] = float(np.exp(np.log1p(r[held]).mean() * 252) - 1)
    out["k200_ann_off_held"] = float(np.exp(np.log1p(r[~held]).mean() * 252) - 1)
    out["k200_vol_on_held"] = float(r[held].std() * np.sqrt(252))
    out["k200_vol_off_held"] = float(r[~held].std() * np.sqrt(252))
    print(f"[posthoc] K200 연율 — 레버리지 보유 세션 {out['k200_ann_on_held']:+.3f} (변동 {out['k200_vol_on_held']:.3f})"
          f" · 그 밖 {out['k200_ann_off_held']:+.3f} (변동 {out['k200_vol_off_held']:.3f})", flush=True)
    return out


def main():
    out_dir = sys.argv[1]
    names = sys.argv[2:] or list(RG.ORDER)
    nproc = int(os.environ.get("GATE_NPROC", 4))
    t0 = time.time()
    res = {"alloc": alloc(), "strategies": {}}
    for sid in names:
        res["strategies"][sid] = strategy(sid, out_dir, nproc)
    with open(os.path.join(out_dir, "posthoc.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=float)
    print(f"[posthoc] done {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
