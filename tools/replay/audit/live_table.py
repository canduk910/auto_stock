#!/usr/bin/env python3
"""단계 3 — 실거래 정리(K4 공통): 전략별 현 설정 시작일(D-8) + 왕복 거래 표(D-1·D-2·D-4·D-7).

현 설정 시작일 근거 = ``parameter_recommendations.current_params``(매일 20:00 자문이 그 순간의 **실행 중 설정**을
적어 둔 것 — 기본값 병합 뒤의 런타임 값). 최신 스냅샷(10-02)과 매매 행위 키가 하나라도 다른 마지막 날 T 를 찾고,
바뀐 시점은 (T 20:00, 다음 스냅샷 20:00] 안이다. 시작일 = 「최신과 같아진 첫 스냅샷 날의 다음 거래일」(보수).
변경 시각이 장 전으로 기록된 것(시장 유닛 enforce PUT 10-02 06:47 — 워크리스트)은 그날을 시작일로 쓴다.
키가 스냅샷에 없던 날(``<absent>``) = 그 기능이 아직 없던 날(코드 도입 전)로 본다.

판(둘 다 보고):
- strict = 행위 키 전부(시장 유닛 모드 포함)
- ex_mu  = ``market_unit_mode`` 만 뺀 것 — 터틀 4전략은 10-02 enforce 전환 하나 때문에 strict 표본이 하루뿐이다
- rules  = 랏 캡(K축 ``max_lot_units``·ρ축 ``max_lot_ratio_mult``)·시장 유닛을 뺀 것 — 진입·청산·손절 규칙 기준.
  거래당 수익률(L1)은 랏 크기와 무관하므로 이 판이 L1 표본의 후보다(채택은 팀장 결정)

출력: 스크래치 audit/live_trips.json(왕복 전체 · 손익 포함) + 표준출력 요약(개수만)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import config as C  # noqa: E402
from replay.audit import live as LV  # noqa: E402
from replay.audit import panel as PN  # noqa: E402

NON_BEHAVIOR = {"llm_gate_daily_call_cap", "llm_gate_min_score", "llm_gate_mode", "llm_gate_timeout_secs",
                "buy_paused", "order_exchange_clock_mode", "after_market_exit_division", "exchange",
                "nxt_tradable", "exclude_tickers"}
# 변경 시각이 기록으로 확인된 것 — (전략, 키) → 그 변경이 처음 적용된 거래일
#  · 시장 유닛 enforce PUT 2026-10-02 06:47(장 전) — 워크리스트 「10-02 새벽」 2
#  · VB·LTV max_lot_ratio_mult 2.5→1.0 PUT 2026-09-25 07:3x(추석 휴장) → 첫 거래일 09-28 — 보고서 2026-09-25 §4-3
#  · VCP sizing_mode=turtle·risk_pct 0.01 PUT 2026-09-26 10:22(휴장) → 첫 거래일 09-28 — 워크리스트 「VCP 터틀 전환」
PREMARKET_CHANGES = {("kojiro", "market_unit_mode"): "2026-10-02",
                     ("donchian_swing", "market_unit_mode"): "2026-10-02",
                     ("bull_flag_breakout", "market_unit_mode"): "2026-10-02",
                     ("vcp_breakout", "market_unit_mode"): "2026-10-02",
                     ("volatility_breakout", "max_lot_ratio_mult"): "2026-09-28",
                     ("long_tail_volatility", "max_lot_ratio_mult"): "2026-09-28",
                     ("vcp_breakout", "sizing_mode"): "2026-09-28",
                     ("vcp_breakout", "risk_pct"): "2026-09-28"}
VARIANTS = (("strict", set()),
            ("ex_mu", {"market_unit_mode"}),
            ("rules", {"market_unit_mode", "max_lot_units", "max_lot_ratio_mult"}))


def _j(v):
    return v if isinstance(v, (dict, list)) or v is None else json.loads(v)


def settings_start(recs: list, trading_days: "list[str]", exclude: "set[str]") -> dict:
    """recs = [(target_date, current_params)] 오름차순. 반환 = 시작일·근거."""
    latest = recs[-1][1]
    keys = [k for k in latest if k not in NON_BEHAVIOR and k not in exclude]
    last_diff_day, last_diff_keys = None, []
    for d, cp in recs:
        dk = [k for k in keys if cp.get(k, "<absent>") != latest[k]]
        if dk:
            last_diff_day, last_diff_keys = d, dk
    if last_diff_day is None:
        return {"start": recs[0][0], "basis": "스냅샷 전 구간 같음", "last_diff": None, "keys": []}
    later = [d for d, _ in recs if d > last_diff_day]
    first_equal = later[0] if later else None
    pm = [PREMARKET_CHANGES.get((None, k)) for k in last_diff_keys]
    return {"last_diff": last_diff_day, "first_equal_snapshot": first_equal, "keys": last_diff_keys,
            "start_conservative": next((t for t in trading_days if first_equal and t > first_equal), None)}


def main():
    ext = PN.load_db_extract()
    sha = PN.sha256(C.DB_EXTRACT)
    cols, rows = ext["param_recs"]
    ix = {c: i for i, c in enumerate(cols)}
    by = defaultdict(list)
    for r in rows:
        by[r[ix["strategy_id"]]].append((r[ix["target_date"]], _j(r[ix["current_params"]])))
    dcols, drows = ext["daily"]
    dix = {c: i for i, c in enumerate(dcols)}
    trading_days = sorted({r[dix["bas_dd"]][:10] for r in drows if r[dix["ticker"]] == "069500"})
    starts = {}
    for s, lst in sorted(by.items()):
        lst.sort(key=lambda x: x[0])
        res = {}
        for name, exc in VARIANTS:
            r = settings_start(lst, trading_days, exc)
            # 장 전 변경 보정: 마지막 차이 키가 전부 장 전 변경으로 기록된 것이면 그날부터
            pm = {PREMARKET_CHANGES.get((s, k)) for k in r.get("keys", [])}
            if r.get("keys") and None not in pm and len(pm) == 1:
                r["start"] = pm.pop()
                r["basis"] = "변경 시각 기록 — 처음 적용된 거래일부터"
            else:
                r["start"] = r.get("start_conservative") or r.get("start")
                r["basis"] = r.get("basis", "최신과 같아진 첫 스냅샷의 다음 거래일(보수)")
            res[name] = r
        starts[s] = res
    # donchian 개조 = 미배포(새 규칙 실거래 0) — 구 규칙 거래는 전부 참고
    starts["donchian_swing"]["note"] = "새 규칙(깡토 개조) 미배포 — 표의 시작일은 구 규칙 기준이며 판정에 쓰지 않는다"

    tcols, trows = ext["trades_all"]
    trs = [dict(zip(tcols, r)) for r in trows]
    ca = LV.ca_days_from_db(dcols, drows)
    out = LV.round_trips(trs, cost_rt=C.COST_RT_JUDGE, ca_days=ca, live_start=C.LIVE_START)
    pcols, prows = ext["positions"]
    pos = Counter(r[pcols.index("strategy_id")] for r in prows)
    open_by = Counter(o["strategy"] for o in out["open"])
    summary = {}
    for s in sorted({t["strategy"] for t in out["trips"]} | set(by)):
        tl = [t for t in out["trips"] if t["strategy"] == s]
        st = starts.get(s, {})
        row = {"trips_all": len(tl),
               "first_buy": min((t["buy_date"] for t in tl), default=None),
               "last_sell": max((t["sell_date"] for t in tl), default=None),
               "excl_D4_before_0429": sum(1 for t in tl if not t["in_window"]),
               "excl_D1_corporate_action": sum(1 for t in tl if t["ca_flag"] and t["in_window"]),
               "open_unclosed": open_by.get(s, 0), "positions_table": pos.get(s, 0),
               "orphan_sells": sum(1 for o in out["orphan_sells"] if o["strategy"] == s),
               "excl_D7_status": {f"{k[1]}:{k[2]}": v for k, v in out["excluded"].items() if k[0] == s}}
        for name, _exc in VARIANTS:
            if name in st:
                start = st[name]["start"]
                row[f"start_{name}"] = start
                row[f"trips_{name}"] = sum(1 for t in tl if t["in_window"] and not t["ca_flag"] and start
                                           and t["buy_date"] >= start)
                row[f"buys_{name}"] = sum(1 for t in tl for (d, _q, _p) in t["buy_orders"]
                                          if start and d >= start) + \
                    sum(1 for o in out["open"] if o["strategy"] == s and start
                        and LV.kst_date(o["buy_ts"]).isoformat() >= start)
        row["judged_window_trips_all_D4_D1"] = sum(1 for t in tl if t["in_window"] and not t["ca_flag"])
        row["one_share_share"] = (sum(1 for t in tl if t["one_share"]) / len(tl)) if tl else None
        summary[s] = row
    res = {"extract_sha256": sha, "starts": starts, "summary": summary,
           "orphan_sells": out["orphan_sells"], "open": out["open"],
           "excluded": {f"{k[0]}:{k[1]}:{k[2]}": v for k, v in out["excluded"].items()},
           "trips": out["trips"]}
    with open(os.path.join(C.SCRATCH, "live_trips.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({"starts": starts, "summary": summary, "orphan_sells": out["orphan_sells"]},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
