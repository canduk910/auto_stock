#!/usr/bin/env python3
"""실거래(K4) 판정 실행 — VB(L1·L2) · momentum(L1·L2·갭 칸) · LTV(L1 사후 기록).

입력 = 스크래치 ``audit/live_trips.json``(단계 1, sha 대조) + DB 추출본 일봉(momentum 다음 날 시가).
출력 = 스크래치 ``audit/vb/live_result.json`` + 표준출력(집계값만 — 종목별 원장은 스크래치에만).
D-8 시작일 = 사용자 결정(10-05) rules 판: VB 09-14 · momentum 06-12 · LTV 전 기간.
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import config as C  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.strategies import vb_live as VL  # noqa: E402

LIVE_SHA = "ae62143a"           # 단계 1 결과 §3.1 (앞 8자)
START = {"volatility_breakout": {"rules": "2026-09-14", "strict": "2026-09-28", "all_D4": C.LIVE_START},
         "momentum": {"rules": "2026-06-12", "strict": "2026-09-08", "all_D4": C.LIVE_START},
         "long_tail_volatility": {"all": C.LIVE_START}}


def main():
    path = os.path.join(C.SCRATCH, "live_trips.json")
    sha = PN.sha256(path)
    assert sha.startswith(LIVE_SHA), sha
    live = json.load(open(path))
    trips = live["trips"]
    ext = PN.load_db_extract()
    dcols, drows = ext["daily"]
    ix = {c: i for i, c in enumerate(dcols)}
    opens = {(r[ix["ticker"]], r[ix["bas_dd"]][:10]): r[ix["open_price"]] for r in drows}
    days = sorted({r[ix["bas_dd"]][:10] for r in drows if r[ix["ticker"]] == "069500"})
    out = {"live_trips_sha256": sha, "extract_sha256": PN.sha256(C.DB_EXTRACT), "starts": START}

    for s, wins in START.items():
        res = {}
        for name, st in wins.items():
            tl = VL.select(trips, s, st)
            blk = {"start": st, **VL.l1_block(tl), "l2": VL.l2_block(tl)}
            if s == "volatility_breakout":
                blk["exit_reason"] = VL.bucket_table(tl, VL.vb_exit_reason)
                blk["price_bucket"] = VL.bucket_table(tl, lambda t: "le_86794" if t["buy_px"] <= 86_794
                                                      else "gt_86794")
                blk["lot_bucket"] = VL.bucket_table(tl, lambda t: "one_share" if t["one_share"] else "multi")
            if s == "momentum":
                blk["gap_bucket"] = VL.bucket_table(tl, lambda t: VL.momentum_bucket(t, opens, days))
            if s == "long_tail_volatility":
                blk["mode"] = VL.bucket_table(tl, VL.ltv_mode)
                blk["by_month"] = VL.bucket_table(tl, VL.month_key)
                sep = [t for t in tl if t["buy_date"].startswith("2026-09")]
                intr = [t for t in tl if VL.ltv_mode(t) == "intraday"]
                blk["sep_only"] = {**VL.l1_block(sep), "l2": VL.l2_block(sep)}
                blk["ex_limit_up_mode"] = {**VL.l1_block(intr), "l2": VL.l2_block(intr)}
                blk["cost_0p23_for_cycle381"] = {"all": VL.l1_block(tl, 0.0023)["mean_net"],
                                                 "sep": VL.l1_block(sep, 0.0023)["mean_net"]}
            if s in ("volatility_breakout", "momentum"):
                blk["by_month"] = VL.bucket_table(tl, VL.month_key)
            res[name] = blk
        res["excluded_D7"] = live["summary"][s]["excl_D7_status"]
        res["orphan_sells"] = live["summary"][s]["orphan_sells"]
        res["open_unclosed"] = live["summary"][s]["open_unclosed"]
        res["excl_D4"] = live["summary"][s]["excl_D4_before_0429"]
        out[s] = res
    os.makedirs(os.path.join(C.SCRATCH, "vb"), exist_ok=True)
    with open(os.path.join(C.SCRATCH, "vb", "live_result.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
