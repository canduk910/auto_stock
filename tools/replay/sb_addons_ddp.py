#!/usr/bin/env python3
"""낙폭 정지 DDP — 성적표 개별 매매 전략 계좌를 관문을 끼워 다시 돈다(사전 등록 §1).

성적표 어댑터(``scoreboard_books``)를 그대로 부르되, 각 30년 계좌 함수의 「그날 신호 목록」 한 줄에
``sb_addons_core.GateHub`` 관문을 끼운 사본으로 바꿔 둔다(원 파일 무수정). 판(낙관/비관) × 관문(끔/켬) 넷.

    python tools/replay/sb_addons_ddp.py <out_dir> [kojiro donchian vcp bfb vb etf_trend mr_band mr_fkeep]
"""
from __future__ import annotations

import json
import os
import sys
import time

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import scoreboard_books as SB  # noqa: E402  (운영 클래스 import 용 더미 환경변수도 여기서)
from replay import sb_addons_core as S  # noqa: E402

import numpy as np  # noqa: E402

HUB = S.GateHub(enabled=False)
_PATCHED: set = set()

# 전략 → (계좌 함수가 있는 모듈 import 경로, 함수 이름)
LOOPS = {
    "kojiro": ("replay.strategies.kojiro_y30", "run_book30"),
    "donchian": ("replay.strategies.donchian_y30", "run_book"),
    "vcp": ("replay.strategies.y30_bfbvcp", "run_book"),
    "bfb": ("replay.strategies.y30_bfbvcp", "run_book"),
    "vb": ("replay.strategies.vb_y30", "run_book_var"),
    "etf_trend": ("replay.y30_etfbase_run", "etf_book30"),
    "mr_band": ("replay.y30_mr_band", "run_book"),
    "mr_fkeep": ("replay.y30_mr_band", "run_book"),
}
# 비관판이 따로 있는 전략(사전 등록 §0)
PES = {"kojiro", "vb"}


def install(sid: str):
    import importlib
    mod_name, fn = LOOPS[sid]
    if (mod_name, fn) in _PATCHED:
        return
    mod = importlib.import_module(mod_name)
    S.gate_function(mod, fn, HUB)
    _PATCHED.add((mod_name, fn))


class _Swap:
    """``모듈.이름`` 을 잠시 바꾼다."""

    def __init__(self, mod, name, new):
        self.mod, self.name, self.new = mod, name, new
        self.orig = getattr(mod, name)

    def __enter__(self):
        setattr(self.mod, self.name, self.new(self.orig))
        return self

    def __exit__(self, *exc):
        setattr(self.mod, self.name, self.orig)


def run_adapter(sid: str, version: str):
    """성적표 어댑터 1회. version = opt | pes(kojiro: 시가 + 0.76% · vb: pes 순서)."""
    ad = SB.ADAPTERS[sid]
    if version == "opt" or sid not in PES:
        return ad(None)
    if sid == "kojiro":
        from replay.strategies import kojiro_y30_run as R

        def wrap(orig):
            def f(*a, **k):
                k["slip"] = R.SLIP
                return orig(*a, **k)
            return f
        with _Swap(R, "run_books", wrap):
            return ad(None)
    if sid == "vb":
        from replay.strategies import vb_y30_run as R

        def wrap(orig):
            def f(*a, **k):
                a = list(a)
                assert a[-1] == "opt", a[-1]
                a[-1] = "pes"
                return orig(*a, **k)
            return f
        with _Swap(R, "allsig", wrap):
            return ad(None)
    raise ValueError(sid)


def one(sid: str, version: str, gate: bool) -> dict:
    install(sid)
    HUB.reset()
    HUB.enabled = gate
    p = run_adapter(sid, version)
    meta = p["meta"]
    n_seed = meta["n_seeds"]
    runs = HUB.runs[:n_seed] if sid != "etf_trend" else HUB.runs[:1]
    dropped = HUB.dropped[:len(runs)]
    rep = meta["rep_seed"] if sid != "etf_trend" else 0
    g = runs[rep]
    n_days = len(p["equity"]) - 1
    if g.n_days != n_days:
        raise SystemExit(f"[ddp] {sid}: 관문 호출 {g.n_days} ≠ 계좌 날 수 {n_days} — 신호 줄이 매일 불리지 않는다")
    dates = [str(x) for x in p["dates"]]
    ev = [{"seen_day": dates[1 + i], "eq": e, "peak": pk} for i, e, pk in g.events]
    meta.update({"version": version, "gate": gate,
                 "ddp_rep": {"events": ev, "n_events": len(ev), "paused_days": g.paused_days,
                             "dropped_signals": dropped[rep]},
                 "ddp_median": {"n_events": float(np.median([len(r.events) for r in runs])),
                                "paused_days": float(np.median([r.paused_days for r in runs])),
                                "dropped_signals": float(np.median(dropped))}})
    return p


def save(out_dir, sid, version, gate, p):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{sid}__{version}__{'ddp' if gate else 'base'}.npz")
    np.savez_compressed(path, dates=p["dates"], equity=p["equity"], meta=json.dumps(p["meta"], ensure_ascii=False,
                                                                                         default=str))
    return path


def check_scoreboard(sid, p) -> float:
    """관문 끈 낙관판 = 성적표 books 와 원 단위로 같아야 한다(사전 등록 §1-2)."""
    ref = os.path.join(_ROOT, "_workspace/analysis/scoreboard_20261006/books", f"{sid}.npz")
    z = np.load(ref, allow_pickle=False)
    a, b = np.asarray(z["equity"], float), np.asarray(p["equity"], float)
    if len(a) != len(b) or list(z["dates"].astype(str)) != [str(x) for x in p["dates"]]:
        return float("inf")
    return float(np.max(np.abs(a - b)))


def main():
    out_dir = sys.argv[1]
    names = sys.argv[2:] or list(LOOPS)
    for sid in names:
        for version in (("opt", "pes") if sid in PES else ("opt",)):
            for gate in (False, True):
                t0 = time.time()
                p = one(sid, version, gate)
                if version == "opt" and not gate:
                    d = check_scoreboard(sid, p)
                    p["meta"]["check_scoreboard_max_abs"] = d
                    if d > 0.5:
                        raise SystemExit(f"[ddp] {sid}: 관문 끈 곡선이 성적표와 다르다(최대 차 {d:.2f}원)")
                path = save(out_dir, sid, version, gate, p)
                m = p["meta"]
                print(f"[ddp] {sid} {version} {'DDP' if gate else 'base'} {time.time() - t0:.0f}s → {path} · "
                      f"씨앗 CAGR 중앙 {m['seed_cagr_median']:+.4f} · 낙폭 중앙 {m['seed_mdd_median']:+.3f} · "
                      f"발동(대표) {m['ddp_rep']['n_events']} · 정지일 {m['ddp_rep']['paused_days']}"
                      + (f" · 성적표 대조 {m.get('check_scoreboard_max_abs'):.4f}" if version == "opt" and not gate else ""),
                      flush=True)


if __name__ == "__main__":
    main()
