#!/usr/bin/env python3
"""(라) 장세 문 — 전략 계좌를 관문을 끼워 다시 돈다(사전 등록 §3).

성적표 어댑터(``scoreboard_books``)를 그대로 부르되, 각 30년 계좌 함수의 「그날 신호 목록 꺼내기 + 섞기」 두 줄 뒤에
``ra_gate_core.RaGate.filter`` 한 줄을 끼운 사본으로 바꿔 둔다(원 파일 무수정 · 섞기 뒤라 난수 흐름이 원판과 같다).

    python tools/replay/ra_gate_run.py prep <data.pkl>                       # 칸 키 · 시장 유닛 날짜표(대조 포함)
    python tools/replay/ra_gate_run.py run <data.pkl> <out_dir> <sid> [판 ...]

판 = G0 · G0N · G1 · G2(터틀) / G0 · G1 · G3S · G2S(비터틀). 비관판은 kojiro · vb 만(같은 판 전부).
"""
from __future__ import annotations

import functools
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
from replay import scoreboard_books as SB  # noqa: E402
from replay import ra_gate_core as G  # noqa: E402
from replay import sector_rs_core as R  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

MR = {"mr_band", "mr_fkeep"}
TURTLE_VARIANTS = ("G0", "G0N", "G1", "G2")
OTHER_VARIANTS = ("G0", "G1", "G3S", "G2S")
REGV2_INDEX = os.path.join(os.path.dirname(SB.C.SCRATCH), "regime_v2", "index.pkl")
_PATCHED: set = set()
GATE: "G.RaGate | None" = None


def variants_of(sid: str) -> tuple:
    return TURTLE_VARIANTS if sid in G.TURTLE else OTHER_VARIANTS


def spec(sid: str, variant: str) -> dict:
    """판 → 관문 설정(사전 등록 §3 표)."""
    block = variant in ("G1", "G2", "G2S")
    if sid in G.TURTLE:
        if variant not in TURTLE_VARIANTS:
            raise ValueError((sid, variant))
        return {"block": block, "mu": "off" if variant in ("G0N", "G1") else "native", "check_m": variant == "G0",
                "etf_enforce": False}
    if variant not in OTHER_VARIANTS:
        raise ValueError((sid, variant))
    apply_ = variant in ("G3S", "G2S")
    if sid == "etf_trend":
        return {"block": block, "mu": "native", "check_m": False, "etf_enforce": apply_}
    return {"block": block, "mu": "apply" if apply_ else "native", "check_m": False, "etf_enforce": False}


# ═════════════════════════════════ 자료 ═════════════════════════════════

def prep(out_path: str) -> dict:
    """(라) 칸 키(판단 계열 달력) 재계산 + regime_v2 저장 키 대조 · 시장 유닛 069500 계열."""
    from replay import regime_v2 as RV
    from replay.strategies import kojiro_y30 as KY
    m = RV.load_mkt()
    f = RV.features(m)
    rule = [tuple(c) for c in json.load(open(os.path.join(
        _ROOT, "_workspace/analysis/regime_v2_20261006/ra_rule.json")))["rule"]]
    keys = RV.rule_keys(f, rule)
    chk = {"rule": rule}
    if os.path.exists(REGV2_INDEX):
        ix = pickle.load(open(REGV2_INDEX, "rb"))
        same_dates = bool(pd.DatetimeIndex(ix["dates"]).equals(pd.DatetimeIndex(m.dates)))
        diff = int(np.sum(np.asarray(ix["keys"]["ra"], dtype=object) != keys)) if same_dates else -1
        chk.update({"regv2_same_dates": same_dates, "regv2_key_diff": diff})
        if diff != 0:
            raise SystemExit(f"[ra_gate prep] regime_v2 저장 키와 다르다(달력 같음 {same_dates} · 다른 날 {diff})")
    else:
        chk["regv2_index"] = "없음 — 대조 생략"
    valid = np.isfinite(f["T7"].to_numpy(float)) & np.isfinite(f["R5"].to_numpy(float))
    first_valid = str(pd.DatetimeIndex(m.dates)[int(np.argmax(valid))].date())
    kd, kc = KY.mu_series()
    out = {"dates": pd.DatetimeIndex(m.dates), "keys": keys, "t7": f["T7"].to_numpy(float),
           "r5": f["R5"].to_numpy(float), "first_valid": first_valid, "check": chk,
           "mu_dates": pd.DatetimeIndex(kd), "mu_close": np.asarray(kc, float)}
    with open(out_path, "wb") as fh:
        pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"[ra_gate prep] 칸 키 {len(keys)}일({out['dates'][0].date()} ~ {out['dates'][-1].date()}) · 두 조건 다 있는 첫날 "
          f"{first_valid} · 대조 {chk} → {out_path}", flush=True)
    return out


def lookups(D: dict):
    cell_of = G.AsOf(D["dates"], list(D["keys"]), default=None)
    m_of = G.mu_asof(D["mu_dates"], D["mu_close"])
    return cell_of, m_of


# ═════════════════════════════════ 설치 · 실행 ═════════════════════════════════

def install(sid: str):
    import importlib
    mod_name, fn = DDP.LOOPS[sid]
    if (mod_name, fn) in _PATCHED:
        return
    mod = importlib.import_module(mod_name)
    G.gate_function(mod, fn, GATE, mr=sid in MR)
    _PATCHED.add((mod_name, fn))


class _Swap:
    def __init__(self, mod, name, new):
        self.mod, self.name, self.new = mod, name, new
        self.orig = getattr(mod, name)

    def __enter__(self):
        setattr(self.mod, self.name, self.new(self.orig))
        return self

    def __exit__(self, *exc):
        setattr(self.mod, self.name, self.orig)


class _Capture:
    """``scoreboard_books.pack`` 을 감싸 씨앗 전부의 곡선(전체 창)을 붙잡는다."""

    def __init__(self):
        self.runs = self.dates = None

    def __call__(self, orig):
        def f(sid, dates, runs, start_equity, **k):
            self.runs = [(int(s), np.asarray(e, float)) for s, e in runs]
            self.dates = pd.DatetimeIndex(dates)
            return orig(sid, dates, runs, start_equity, **k)
        return f


def _vb_wrap(orig):
    def f(*a, **k):
        sz, params = orig(*a, **k)
        return (lambda P, B, used, _s=sz: GATE.scale(_s(P, B, used))), params
    return f


def run_one(D, sid, version, variant) -> dict:
    sp = spec(sid, variant)
    cell_of, m_of = lookups(D)
    g = GATE
    g.reset()
    g.cell_of, g.m_of = cell_of, m_of
    g.block, g.enabled, g.mu, g.check_m = sp["block"], sp["block"], sp["mu"], sp["check_m"]
    g.date_override, g.key, g.mr_names, g.mult = None, (lambda o: o.ticker), None, 1.0
    install(sid)
    cap = _Capture()
    t0 = time.time()
    swaps = [_Swap(SB, "pack", cap)]
    if sid == "vb":
        from replay.strategies import vb_y30_run as VR
        swaps.append(_Swap(VR, "vb_sizer", _vb_wrap))
    if sid == "etf_trend" and sp["etf_enforce"]:
        from replay import y30_etfbase_run as YR
        swaps.append(_Swap(YR, "etf_book30", lambda o: functools.partial(o, mu_mode="enforce")))
    for s in swaps:
        s.__enter__()
    try:
        if sid in MR:
            from replay.sector_rs_run import _MRCapture
            with _MRCapture(g):
                p = DDP.run_adapter(sid, version)
        else:
            p = DDP.run_adapter(sid, version)
    finally:
        for s in reversed(swaps):
            s.__exit__()
    meta = p["meta"]
    n_days = len(p["equity"]) - 1
    full = [r for r in g.runs if r["days"] == n_days]
    if sid == "etf_trend":
        full = full[:16]
    n_need = 16 if sid == "etf_trend" else int(meta["n_seeds"])
    if len(full) != n_need:
        raise SystemExit(f"[ra_gate] {sid} {variant}: 전체 창 실행 {len(full)} ≠ {n_need}")
    rep = int(meta["rep_seed"]) if sid != "etf_trend" else 0

    def dog(run):
        if g.date_override is not None:
            return lambda gd: g.date_override[gd]
        return lambda gd: run["cal"][gd]
    seeds = []
    for i, r in enumerate(full):
        seeds.append({"seed": i, "trades": R.trade_rows(r, dog(r), g.mr_names), "dropped": r["dropped"],
                      "dropped_mu": r["dropped_mu"], "seen": r["seen"], "cell_days": dict(r["cell_days"]),
                      "cell_sigs": dict(r["cell_sigs"]), "m_checked": r["m_checked"], "m_mismatch": r["m_mismatch"],
                      "m_mismatch_ex": r["m_mismatch_ex"], "mult_days": dict(r["mult_days"])})
    meta.update({"version": version, "variant": variant, "spec": sp, "elapsed_s": time.time() - t0})
    return {"p": p, "seeds": seeds, "rep": rep, "all_runs": cap.runs, "all_dates": cap.dates}


def main():
    cmd = sys.argv[1]
    if cmd == "prep":
        prep(sys.argv[2])
        return
    data, out_dir, sid = sys.argv[2], sys.argv[3], sys.argv[4]
    want = sys.argv[5:] or list(variants_of(sid))
    D = pickle.load(open(data, "rb"))
    global GATE
    GATE = G.RaGate()
    os.makedirs(out_dir, exist_ok=True)
    for version in (("opt", "pes") if sid in DDP.PES else ("opt",)):
        for variant in want:
            path = os.path.join(out_dir, f"{sid}__{version}__{variant}.pkl")
            if os.path.exists(path):
                print(f"[ra_gate] {sid} {version} {variant} 이미 있음 — 건너뜀", flush=True)
                continue
            res = run_one(D, sid, version, variant)
            p = res["p"]
            if version == "opt" and variant == "G0":
                d = DDP.check_scoreboard(sid, p)
                p["meta"]["check_scoreboard_max_abs"] = d
                if d > 0.5:
                    raise SystemExit(f"[ra_gate] {sid}: 관문 끈 곡선이 성적표와 다르다(최대 차 {d:.2f}원)")
            out = {"dates": [str(x) for x in p["dates"]], "equity": np.asarray(p["equity"], float),
                   "meta": json.loads(json.dumps(p["meta"], default=str)), "seeds": res["seeds"], "rep": res["rep"],
                   "all_runs": res["all_runs"], "all_dates": [str(x.date()) for x in res["all_dates"]]}
            with open(path, "wb") as fh:
                pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
            s = res["seeds"][res["rep"]]
            m = p["meta"]
            print(f"[ra_gate] {sid} {version} {variant} {m['elapsed_s']:.0f}s · 씨앗 CAGR 중앙 {m['seed_cagr_median']:+.4f} · "
                  f"대표 거래 {len(s['trades'])} · 버린 신호(칸) {len(s['dropped'])} · 버린 신호(m=0) {len(s['dropped_mu'])}"
                  + (f" · m 대조 {s['m_mismatch']}/{s['m_checked']}" if s["m_checked"] else "")
                  + (f" · 성적표 대조 {m.get('check_scoreboard_max_abs'):.4f}" if 'check_scoreboard_max_abs' in m else ""),
                  flush=True)


if __name__ == "__main__":
    main()
