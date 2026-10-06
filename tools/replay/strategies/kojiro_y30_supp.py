#!/usr/bin/env python3
"""kojiro 30년 재검증 — 본 실행 뒤 보충 두 가지(결과 md 「사후 변경」 에 적는다).

1. 「시장 유닛 없이」 보고판 고침: 본 실행은 이미 m>0 으로 거른 신호에 m=1 을 넣어 현행과 같은 값이 나왔다(버그).
   여기서는 거르기 전 신호(m=0 날 포함) 전부에 m=1 을 넣는다(5년 점검 보고판과 같은 정의).
2. 5년 창 맞대기 분해: 5년 점검 모집단(스크래치 ``audit/kojiro/pop_w5y.csv``)과 (종목, 진입일)로 짝지어
   공통 거래 · 한쪽에만 있는 거래를 나눈다(5년 보관소는 2020-10-05 에 시작해 첫 80봉 동안 신호가 없다).

실행: python tools/replay/strategies/kojiro_y30_supp.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import config as C  # noqa: E402
from replay.strategies import kojiro as KJ  # noqa: E402
from replay.strategies import kojiro_opt as KO  # noqa: E402
from replay.strategies import kojiro_opt_run as KOR  # noqa: E402
from replay.strategies import kojiro_y30 as Y  # noqa: E402
from replay.strategies import kojiro_y30_run as R  # noqa: E402

POP5 = os.path.join(C.SCRATCH, "kojiro", "pop_w5y.csv")


def main():
    D = R.prepare()
    cal, st, p = D["cal"], D["st"], D["p"]
    Y.Y30Pos.LIM = Y.limit_table(cal)
    cost_era, cost_c = Y.era_cost(cal), Y.const_cost(cal)
    feats = D["feats_by"][5]
    cfg = KOR.exit_cfg(R.CURRENT)
    raw = D["sigs_by"][(5, 0.06)]
    out = {"no_market_unit": {}, "current_same_def": {}}
    for nm, w in (("T", Y.T_WIN), ("V", Y.V_WIN), ("H", Y.H_WIN)):
        g0, g1 = Y.gd_range(cal, w)
        allm1 = [KJ.Sig(**{**s.__dict__, "m": 1.0}) for s in raw]
        pn = Y.population(allm1, Y.PathMemo(st.bars, feats, p), cfg, g0, g1, 0.0)
        pc = Y.population(KO.select(raw, "cur", None), Y.PathMemo(st.bars, feats, p), cfg, g0, g1, 0.0)
        out["no_market_unit"][nm] = R.stats(pn, cal, cost_era, boot=False)
        out["current_same_def"][nm] = R.stats(pc, cal, cost_era, boot=False)
        m0 = [x for x in pn if (D["m_day"][x.s.gd] == 0)]
        out["no_market_unit"][nm]["m0_cell"] = R.stats(m0, cal, cost_era, boot=False)
        R.log("noMU", nm, out["no_market_unit"][nm]["n"], out["no_market_unit"][nm]["mean"],
              out["current_same_def"][nm]["mean"])
    # 5년 맞대기
    g0, g1 = Y.gd_range(cal, C.W5Y)
    mine = Y.population(KO.select(D["sigs_nom"], "cur", None), Y.PathMemo(st.bars, feats, p), cfg, g0, g1, 0.0)
    old = pd.read_csv(POP5, dtype={"ticker": str})
    ok = {(r.ticker, r.entry): r.net038 for r in old.itertuples()}
    mk = {(x.s.ticker, str(cal[x.s.gd].date())): Y.net(x, cost_c) for x in mine}
    common = sorted(set(ok) & set(mk))
    only_new = [k for k in mk if k not in ok]
    only_old = [k for k in ok if k not in mk]
    first_old = min(old.entry)
    out["w5y_reconcile"] = {
        "n_old": len(ok), "n_new": len(mk), "n_common": len(common),
        "common_mean_old": float(np.mean([ok[k] for k in common])),
        "common_mean_new": float(np.mean([mk[k] for k in common])),
        "common_absdiff_gt_1bp": int(sum(abs(ok[k] - mk[k]) > 1e-4 for k in common)),
        "first_entry_old": first_old,
        "only_new_n": len(only_new), "only_new_mean": float(np.mean([mk[k] for k in only_new])) if only_new else None,
        "only_new_before_first_old": sum(1 for k in only_new if k[1] < first_old),
        "only_new_before_first_old_mean": float(np.mean([mk[k] for k in only_new if k[1] < first_old]))
        if any(k[1] < first_old for k in only_new) else None,
        "only_old_n": len(only_old), "only_old_mean": float(np.mean([ok[k] for k in only_old])) if only_old else None,
        "new_mean_from_first_old": float(np.mean([v for k, v in mk.items() if k[1] >= first_old])),
        "new_n_from_first_old": sum(1 for k in mk if k[1] >= first_old),
    }
    R.log("w5y reconcile", out["w5y_reconcile"])
    path = os.path.join(R.OUT, "result_supp.json")
    with open(path, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=R._js)
    R.log("written", path)


if __name__ == "__main__":
    main()
