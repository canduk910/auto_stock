#!/usr/bin/env python3
"""섹터 RS 배제 — 전략 계좌를 관문을 끼워 다시 돈다(사전 등록 §3).

성적표 어댑터(``scoreboard_books``)를 그대로 부르되, 각 30년 계좌 함수의 「그날 신호 목록 꺼내기 + 섞기」 두 줄 뒤에
``sector_rs_core.SectorGate.filter`` 한 줄을 끼운 사본으로 바꿔 둔다(원 파일 무수정 · 섞기 뒤라 난수 흐름이 원판과 같다).

    python tools/replay/sector_rs_run.py <data.pkl> <out_dir> <sid> [<variant> ...]

variant = BASE(관문 끔) · R60 · R20 · R120 · IBD · BF · ETF. 판(낙관/비관)은 sb_addons_ddp 와 같다(kojiro·vb 만 비관).
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import sb_addons_ddp as DDP  # noqa: E402  (어댑터 · 판 전환 재사용 — 그쪽 관문은 설치하지 않는다)
from replay import sector_rs_core as R  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

UNIVERSE_ETF = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long/meta/universe_etf.csv"
MR = {"mr_band", "mr_fkeep"}
_PATCHED: set = set()
GATE: "R.SectorGate | None" = None


def etf_names() -> dict:
    u = pd.read_csv(UNIVERSE_ETF, dtype=str)
    return dict(zip(u["ticker"], u["name"]))


class _MRCapture:
    """``y30_mr_band.load`` 를 감싸 날짜·종목 목록을 관문에 건네준다."""

    def __init__(self, gate):
        from replay import y30_mr_band as MB
        self.MB, self.gate, self.orig = MB, gate, MB.load

    def __enter__(self):
        def wrap(*a, **k):
            out = self.orig(*a, **k)
            dates, names = out[0], out[3]
            self.gate.date_override = np.asarray(dates)
            self.gate.key = lambda cd, _n=names: _n[cd.tid]
            self.gate.mr_names = names
            return out
        self.MB.load = wrap
        return self

    def __exit__(self, *exc):
        self.MB.load = self.orig


def install(sid: str):
    import importlib
    mod_name, fn = DDP.LOOPS[sid]
    if (mod_name, fn) in _PATCHED:
        return
    mod = importlib.import_module(mod_name)
    R.gate_function(mod, fn, GATE, mr=sid in MR)
    _PATCHED.add((mod_name, fn))


def make_gate(D: dict):
    global GATE
    GATE = R.SectorGate(D["cal"], None, lambda t, d: None, enabled=False)
    return GATE


def configure(D: dict, sid: str, variant: str, enames: dict):
    g = GATE
    g.reset()
    g.enabled = variant != "BASE"
    g.excl = D["excl"]["R60" if variant == "BASE" else variant]
    g.date_override = None
    g.key = lambda o: o.ticker
    g.mr_names = None
    if sid == "etf_trend":
        g.classify = lambda t, d, _n=enames: R.etf_bucket(_n.get(str(t), ""))
    else:
        clf = R.Classifier(D["snaps"], backfill=(variant == "BF"))
        g.classify = clf.bucket


def run_one(D, sid, version, variant, enames) -> dict:
    configure(D, sid, variant, enames)
    install(sid)
    t0 = time.time()
    if sid in MR:
        with _MRCapture(GATE):
            p = DDP.run_adapter(sid, version)
    else:
        p = DDP.run_adapter(sid, version)
    meta = p["meta"]
    n_days = len(p["equity"]) - 1
    full = []
    for r in GATE.runs:
        if r["days"] != n_days:
            break
        full.append(r)
    if not full:
        raise SystemExit(f"[srs] {sid}: 관문 호출 날 수가 계좌 날 수 {n_days} 와 맞는 실행이 없다")
    rep = int(meta["rep_seed"]) if sid != "etf_trend" else 0
    if sid == "etf_trend" and len(full) != 16:
        raise SystemExit(f"[srs] etf_trend 전체 창 실행 {len(full)} ≠ 16")
    if sid != "etf_trend" and len(full) != int(meta["n_seeds"]):
        raise SystemExit(f"[srs] {sid}: 전체 창 실행 {len(full)} ≠ 씨앗 {meta['n_seeds']}")

    def dog(run):
        if GATE.date_override is not None:
            return lambda gd: GATE.date_override[gd]
        return lambda gd: run["cal"][gd]
    seeds = []
    for i, r in enumerate(full):
        tr = R.trade_rows(r, dog(r), GATE.mr_names)
        seeds.append({"seed": i, "trades": tr, "dropped": r["dropped"], "seen": r["seen"],
                      "unclassified": r["unclassified"], "classified": r["classified"],
                      "by_year": r["by_year"]})
    meta.update({"version": version, "variant": variant, "elapsed_s": time.time() - t0})
    return {"p": p, "seeds": seeds, "rep": rep}


def check_books(sid, p) -> float:
    return DDP.check_scoreboard(sid, p)


def main():
    data, out_dir, sid = sys.argv[1], sys.argv[2], sys.argv[3]
    variants = sys.argv[4:] or ["BASE", "R60", "R20", "R120", "IBD", "BF", "ETF"]
    D = pickle.load(open(data, "rb"))
    make_gate(D)
    enames = etf_names()
    os.makedirs(out_dir, exist_ok=True)
    for version in (("opt", "pes") if sid in DDP.PES else ("opt",)):
        for variant in variants:
            if version == "pes" and variant not in ("BASE", "R60"):
                continue
            path = os.path.join(out_dir, f"{sid}__{version}__{variant}.pkl")
            if os.path.exists(path):
                print(f"[srs] {sid} {version} {variant} 이미 있음 — 건너뜀", flush=True)
                continue
            res = run_one(D, sid, version, variant, enames)
            if version == "opt" and variant == "BASE":
                d = check_books(sid, res["p"])
                res["p"]["meta"]["check_scoreboard_max_abs"] = d
                if d > 0.5:
                    raise SystemExit(f"[srs] {sid}: 관문 끈 곡선이 성적표와 다르다(최대 차 {d:.2f}원)")
            p = res["p"]
            out = {"dates": [str(x) for x in p["dates"]], "equity": np.asarray(p["equity"], float),
                   "meta": json.loads(json.dumps(p["meta"], default=str)), "seeds": res["seeds"], "rep": res["rep"]}
            with open(path, "wb") as fh:
                pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
            s = res["seeds"][res["rep"]]
            m = p["meta"]
            print(f"[srs] {sid} {version} {variant} {m['elapsed_s']:.0f}s · 씨앗 CAGR 중앙 {m['seed_cagr_median']:+.4f} · "
                  f"대표 거래 {len(s['trades'])} · 빠진 신호 {len(s['dropped'])} · 미분류 {s['unclassified']}/{s['seen']}"
                  + (f" · 성적표 대조 {m.get('check_scoreboard_max_abs'):.4f}" if 'check_scoreboard_max_abs' in m else ""),
                  flush=True)


if __name__ == "__main__":
    main()
