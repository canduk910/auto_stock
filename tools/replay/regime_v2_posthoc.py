#!/usr/bin/env python3
"""regime_v2 사후 대조(동결 뒤 · 판정 근거 아님) — 고정 노출 0.5 · 보조 (나-경험) 와의 비교.

MAR 은 노출을 낮추면 현금 이자 몫 때문에 올라가는 경향이 있다. 노출이 낮은 판이 「판단이 좋아서」 인지
「덜 실어서」 인지 가르려고 고정 0.5 배 판을 같은 창에서 잰다.

    python tools/replay/regime_v2_posthoc.py <out_dir>
"""
from __future__ import annotations

import json
import os
import pickle
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from replay import global_alloc_b as GB  # noqa: E402
from replay import regime_gate as RG  # noqa: E402
from replay import regime_gate_alloc as RA  # noqa: E402
from replay import regime_v2 as V  # noqa: E402


def main():
    out_dir = sys.argv[1]
    ix = pickle.load(open(os.path.join(V.SCR, "index.pkl"), "rb"))
    m = V.load_mkt()
    out = {}
    for e in (0.5, 0.75):
        expo = np.full(len(m.dates), e)
        r = {}
        for wn in ("T", "V", "H", "FULL"):
            win = RG.WINS[wn]
            a, b = RA.win_ab(m, win)
            sim = V.run_index(m, expo, win)
            mt = V.index_metrics(m, sim, win)
            mo = GB.monthly(m, sim.value, a, b)
            r[wn] = {"metrics": mt}
            for p in ("ga", "na", "na_emp", "da", "ra"):
                po = ix["res"][p]["windows"][wn]["monthly"] if wn != "FULL" else None
                if po is not None:
                    r[wn][f"boot_{p}_vs_const"] = V.boot(po["r"].to_numpy(), mo["r"].to_numpy(), mo["cash"].to_numpy())
        out[str(e)] = r
        print(f"[posthoc] 고정 {e}: " + " · ".join(
            f"{wn} {r[wn]['metrics']['cagr']:+.3f}/{r[wn]['metrics']['mdd']:+.3f}/MAR {r[wn]['metrics']['mar']:+.3f}"
            for wn in ("T", "V", "H", "FULL")), flush=True)
    # 판별 노출 평균(설명용)
    avg = {}
    for p, d in ix["res"].items():
        avg[p] = {wn: float(sum(float(k) * v for k, v in w["metrics"]["expo_share"].items()))
                  for wn, w in d["windows"].items()}
    out["avg_exposure"] = avg
    with open(os.path.join(out_dir, "posthoc.json"), "w") as fh:
        json.dump(V._clean(out), fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
