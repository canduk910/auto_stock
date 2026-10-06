#!/usr/bin/env python3
"""donchian 효율화 — **사후 진단**(사전 등록 밖, 판정·채택 근거로 쓰지 않는다).

고른 판이 V 에서 무너진 뒤 「어느 요인이 깨졌나」 만 본다: 현행판에서 요인 하나씩만 바꾼 판의 T·V 모집단
거래당 순수익과 V 계좌 연 복리 중앙(현행 계좌 설정). 결과 = ``posthoc.json``(같은 폴더).
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import config as C  # noqa: E402
from replay.audit.sizing import OpSizer, load_strategy_class  # noqa: E402
from replay.strategies import donchian_kk as DK  # noqa: E402
from replay.strategies import donchian_kk_audit as DA  # noqa: E402
from replay.strategies import donchian_opt as DO  # noqa: E402

ONE_AT_A_TIME = [
    ("현행", {}, {}),
    ("A2 대금 2.5", {"vol_mult": 2.5}, {}),
    ("A3 상대강도", {"rs": True}, {}),
    ("A4 종가 위치 0.6", {"clv": 0.6}, {}),
    ("A5 m=1 만", {"mu": "m1"}, {}),
    ("A1 55봉", {"entry_n": 55}, {}),
    ("B4 채널 20", {}, {"chan": 20}),
    ("B3 시간 10봉", {}, {"time_bars": 10}),
    ("B2 무장 2R", {}, {"be_r": 2.0}),
    ("B1 R (6, 2.5)", {}, {"r": (6.0, 2.5)}),
]


def main():
    here = os.path.join(C.REPO, "_workspace/analysis/strategy_opt_20261005/donchian")
    st, m, kser, _, _ = DA.build_inputs()
    cal = st.cal
    kc = DO.market_close_on_cal(kser, cal)

    def gd_of(d, side="left"):
        return int(cal.searchsorted(pd.Timestamp(d), side=side)) - (1 if side == "right" else 0)

    win = {k: (gd_of(a), gd_of(b, "right")) for k, (a, b) in {"T": DO.T, "V": DO.V}.items()}
    cls = load_strategy_class(DA.BRANCH_DONCHIAN, "DonchianSwingStrategy", "opt_posthoc_donchian")
    fc: dict = {}
    out = []
    for name, de, dx in ONE_AT_A_TIME:
        en, ex = dict(DO.ENTRY0, **de), dict(DO.EXIT0, **dx)
        kk = DO.kk_of(ex)
        feats, sigs = DO.signals(st, m, kc, en, kk, fc)
        fv = {t: DO.feats_view(f, ex["chan"]) for t, f in feats.items()}
        row = {"name": name}
        for w in ("T", "V"):
            p = DO.pop_stats(DK.population(sigs, st.bars, fv, *win[w], kk=kk), cal)
            row[w] = {k: p[k] for k in ("n", "mean", "lo90", "R_mean")}
        op = OpSizer(cls, "donchian_swing", {"market_unit_mode": "enforce", "risk_pct": kk["risk_pct"],
                                             "position_ratio": 0.15, "max_positions": 6,
                                             "kk_r_floor_pct": ex["r"][0], "kk_r_atr_mult": ex["r"][1]})
        bv = DA.book_view(DA.run_books(sigs, st, fv, DO.V, kk, op, cost_rt=DO.COST))
        row["V_book"] = {k: bv[k] for k in ("cagr_median", "mdd_median", "fills_per_year_median")}
        out.append(row)
        print(name, f"T {row['T']['mean']*100:+.2f}({row['T']['n']}) V {row['V']['mean']*100:+.2f}"
              f"({row['V']['n']}) lo {row['V']['lo90']*100:+.2f} · V 계좌 {bv['cagr_median']*100:+.2f}%"
              f" 낙폭 {bv['mdd_median']*100:.1f}%", flush=True)
    with open(os.path.join(here, "posthoc.json"), "w") as fh:
        json.dump({"note": "사후 진단 — 판정·채택 근거 아님", "rows": out}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
