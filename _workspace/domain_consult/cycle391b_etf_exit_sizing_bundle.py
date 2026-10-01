#!/usr/bin/env python3
"""cycle391b — ETF 추세 전략 청산·수량 묶음 비교 (진입 = 2안 donchian형 고정).

사용자 결정 3(10-02): 「청산·수량절은 1안과 2안을 모두 백테스트돌려보고 유효한 쪽으로 최종결정하자」.
  묶음 A = 설계서 §3.3 갭(+5%/−4%) · §4 청산(손절 max(E−2·ATR20, 0.92E) · 본전 1.5ATR · 샹들리에 2.5ATR · 스테이지3) ·
           §5 사이징(ATR20 · stop_atr 2.0)
  묶음 B = cycle378 donchian 대리 묶음(cycle391 이 측정한 것): N=TR14 평균 · 손절 max(E−2N, 0.91E) · 트레일링 1.8N ·
           10일 저가 채널 · 2봉 뒤 돌파선 아래 종가 · 갭 +3%/돌파선 +4%
판정 규칙 = prereg.md (첫 실행 전에 sha256 고정 — prereg.sha256). 문턱 = 설계서 §8.3 T1~T6 그대로.

재사용: _workspace/domain_consult/cycle391_etf_s0_remeasure.py 를 수정 없이 모듈로 불러 쓴다(sha256 확인).
연구 전용: 운영 DB/KIS/KRX 호출 0. src/ 무접촉. 출력 = 이 폴더(환경변수 C391B_DIR)의 results.json · results.md · runs.log.

v2(적대 감사 반영, 판정 경로 무변경): 판정판 묶음 A·B·D1·D2 와 판정 함수는 v1 과 한 줄도 다르지 않다.
  감사 뒤 보고판(사후 — 판정에 쓰지 않는다)만 덧붙인다:
  - M1: B 의 「D+2 부터 돌파선 아래 종가 청산」 을 (a) 다음 봉 시가 청산(설계서 §4.3 종가 신호 경로)
        (b) 장중 이탈(c391.sim_donchian intraday_line=True — M12 만 바꾼 판, EMA60 은 판정판 그대로)으로 읽은 판
  - 갭 규칙을 두 묶음에 똑같이 둔 판(갭 없음)
  - I1 상장폐지 종목 거래 수 · I2 ATR20/N 비 · L2 슬리브 정의별 체결 수
  v1 판정 수치와 같은지는 judged_payload_sha256 으로 results_v1.json 과 대조한다.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

T0 = time.time()
HERE = os.environ.get("C391B_DIR", "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
                      "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/c391b")
ETF_S0_DIR = os.environ.get("ETF_S0_DIR", "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
                            "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/etf_s0")
os.environ["ETF_S0_DIR"] = ETF_S0_DIR
BASE_PY = "/Users/koscom/Projects/auto_stock/_workspace/domain_consult/cycle391_etf_s0_remeasure.py"
BASE_SHA = "c05d4d5ab0d252e181ab37b03c356fc7ae8655416954337c820a8f9cca27aea0"
C391_RESULTS = os.path.join(ETF_S0_DIR, "results.json")
PREREG = os.path.join(HERE, "prereg.md")
PREREG_SHA_FILE = os.path.join(HERE, "prereg.sha256")
RUNS_LOG = os.path.join(HERE, "runs.log")
SCRIPT_VERSION = "c391b-v2"

SLEEVE_SEED = 20263002          # prereg §2 — 두 묶음 공통(cycle391 donchian 판정판 씨앗)
GAP_A_UP, GAP_A_DN = 0.05, -0.04  # 설계서 §3.3
REPRO_TOL = 1e-12


def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ── 사전 등록 무결성 ──
_prereg_sha = sha256_file(PREREG)
_prereg_rec = open(PREREG_SHA_FILE).read().split()[0]
if _prereg_sha != _prereg_rec:
    sys.exit(f"[c391b] prereg.md sha256 {_prereg_sha} != 기록값 {_prereg_rec} — 사전 등록이 바뀌었다. 멈춘다.")
_base_sha = sha256_file(BASE_PY)
if _base_sha != BASE_SHA:
    sys.exit(f"[c391b] cycle391 모듈 sha256 {_base_sha} != {BASE_SHA} — 재사용 대상이 바뀌었다. 멈춘다.")

_spec = importlib.util.spec_from_file_location("c391", BASE_PY)
c391 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c391)


def sim_donchian_line_next_open(d, j):
    """감사 M1 보고판 — c391.sim_donchian(intraday_line=False) 과 같되, D+2 부터 종가 < 돌파선이면
    그 종가가 아니라 다음 봉 시가에 판다(ETF 는 15:30 종가를 본 뒤 그날 팔 수 없다 — 설계서 §4.3)."""
    E = d["o"][j + 1]
    N = d["n14"][j]
    line = d["hi_prev20"][j]
    hard = max(E - 2.0 * N, E * 0.91)
    stop, hsb = hard, -np.inf
    n = len(d["c"])
    D = j + 1
    pending = False
    for k in range(D, n):
        if pending:
            return k, d["o"][k], "below_line_next_open"
        ch = np.min(d["l"][max(0, k - 10):k]) if k >= D + 1 else -np.inf
        if d["o"][k] <= stop or d["o"][k] < ch:
            return k, d["o"][k], ("stop_gap" if d["o"][k] <= stop else "chan10_gap")
        trig = []
        if d["l"][k] <= stop:
            trig.append((stop, "stop"))
        if d["l"][k] < ch:
            trig.append((ch, "chan10"))
        if trig:
            px, why = max(trig)
            return k, px, why
        if k >= D + 2 and d["c"][k] < line:
            pending = True
            continue
        hsb = max(hsb, d["h"][k])
        be = E if hsb >= E + 1.5 * N else -np.inf
        stop = max(hard, be, hsb - 1.8 * N)
    return n - 1, d["c"][n - 1], "end"


# ════════════════════════════════════════════════════════════════════
# 거래 생성 — 진입은 2안 donchian 신호(cycle391 gen_trades donchian 분기와 한 줄씩 같다),
# 갭 규칙·청산·사이징 ATR 만 묶음에 따라 바꾼다.
# ════════════════════════════════════════════════════════════════════
def gen_trades_bundle(gap_mode, exit_mode, data, cls, mu, cal, meta, last_ci):
    """gap_mode ∈ {"A","B","none"} · exit_mode ∈ {"A","B","B_next_open","B_intraday"}.
    ("B","B") = cycle391 gen_trades("donchian") 와 같아야 한다(재현 관문). "none"·"B_*" 는 감사 뒤 보고판 전용."""
    trades = []
    for t, d in data.items():
        if not cls.get(t):
            continue
        n = len(d["c"])
        j0 = c391.MIN_BARS - 1
        e60 = d["e60"]
        for j in range(j0, n - 1):
            ci = d["ci"][j]
            if d["ci"][j + 1] != ci + 1:
                continue
            c = d["c"][j]
            craw = d["craw"][j]
            a20 = d["atr20"][j]
            atr_pct = a20 / c
            if not (d["tv20"][j] >= c391.TV20_MIN and craw >= c391.PX_MIN and atr_pct >= c391.ATR_LO):
                continue
            # ── 2안 진입 신호 (공통) ──
            hp = d["hi_prev20"][j]
            if not (hp > 0 and c > hp):
                continue
            if not (e60[j] > e60[j - 1] and c > e60[j]):
                continue
            tvp = d["tvprev20"][j]
            if not (tvp > 0 and d["tv"][j] >= 1.5 * tvp):
                continue
            N = d["n14"][j]
            if not (N > 0):
                continue
            # ── 갭 규칙 ──
            o1 = d["o"][j + 1]
            if gap_mode == "B":
                if o1 >= c * 1.03 or o1 > hp * 1.04:
                    continue
            elif gap_mode == "A":  # 설계서 §3.3: 시가 갭 ≥ +5% · ≤ −4% 스킵 (A1)
                gap = o1 / c - 1
                if gap >= GAP_A_UP or gap <= GAP_A_DN:
                    continue
            elif gap_mode != "none":
                raise ValueError(gap_mode)
            # ── 청산·사이징 ──
            if exit_mode == "B":
                k, px, why = c391.sim_donchian(d, j)
                size_atr = N
            elif exit_mode == "B_next_open":   # 감사 M1(a)
                k, px, why = sim_donchian_line_next_open(d, j)
                size_atr = N
            elif exit_mode == "B_intraday":    # 감사 M1(b) — M12 만 장중으로
                k, px, why = c391.sim_donchian(d, j, intraday_line=True)
                size_atr = N
            elif exit_mode != "A":
                raise ValueError(exit_mode)
            else:  # 설계서 §4.1·§5.1: entry_atr = ATR20, sim_kojiro(손절 max(E−2A,0.92E) · 본전 1.5A · 샹들리에 2.5A · 스테이지3)
                k, px, why = c391.sim_kojiro(d, j)
                size_atr = a20
            m = mu[ci]
            E = d["o"][j + 1]
            rw = 2.0 * size_atr
            cost = c391.COST_LIQ if d["tv20"][j] >= c391.COST_LIQ_TV else c391.COST_ILLIQ
            if why == "end":
                why = "open_end" if d["ci"][k] == last_ci else "delist"
            R = (px - E) / rw
            Rnet = (px - E - cost * E) / rw
            f = min(1.0, c391.POS_RATIO * (size_atr / c) / c391.RISK_PCT)
            scale = craw / c
            lot = 0
            if m == m and m > 0:
                b = c391.REP_BUDGET * m
                lot = int(math.floor(min(b * c391.RISK_PCT / (size_atr * scale), c391.POS_RATIO * b / craw)))
            trades.append({
                "ticker": t, "sig_ci": int(ci), "entry_ci": int(ci + 1), "exit_ci": int(d["ci"][k]),
                "entry_date": str(pd.Timestamp(cal[ci + 1]).date()), "exit_date": str(pd.Timestamp(cal[d["ci"][k]]).date()),
                "E": float(E), "exit_px": float(px), "reason": why, "R": float(R), "Rnet": float(Rnet),
                "m": float(m) if m == m else None, "f": float(f), "tv20": float(d["tv20"][j]),
                "atr_pct": float(atr_pct), "size_atr_pct": float(size_atr / c), "hold": int(k - j - 1),
                "lot75": lot, "listed_at_end": bool(meta[t]["listed_at_end"]),
                "f_mcap": bool(d["mc"][j] >= c391.MCAP_MIN), "f_pxhi": bool(craw <= c391.PX_MAX),
                "f_atrhi": bool(atr_pct <= c391.ATR_HI), "f_qual": bool(d["qual60"][j]),
                "f_nav": bool(np.isfinite(d["nav"][j]) and d["nav"][j] >= c391.MCAP_MIN) if "nav" in d else None,
                "j": int(j), "k": int(k), "rw": float(rw), "cost": float(cost),
            })
    return trades


def decide(a, b):
    """prereg §1: 하나만 통과 → 그것 · 둘 다 통과 → 연 수익÷|근사 MDD| 큰 쪽(동률 → B) · 둘 다 탈락 → 없음."""
    pa, pb = a["judge"]["pass_T1_T5"], b["judge"]["pass_T1_T5"]
    ra, rb = a["sleeve"]["ret_over_mdd"], b["sleeve"]["ret_over_mdd"]
    if pa and pb:
        w = "A" if round(ra, 9) > round(rb, 9) else "B"
        return w, f"둘 다 통과 → 연 수익÷|근사 MDD| 가 큰 묶음 {w} ({ra:.3f} 대 {rb:.3f})", pa, pb
    if pa:
        return "A", "묶음 A 만 통과 → A", pa, pb
    if pb:
        return "B", "묶음 B 만 통과 → B", pa, pb
    return None, "둘 다 탈락 → 없음", pa, pb


def main():
    print("[c391b] hashing inputs ...", flush=True)
    hashes = {os.path.relpath(p, "/Users/koscom/Projects/auto_stock"): sha256_file(p) for p in c391.PARQUETS}
    hashes["data/archive/krx_etf_daily/raw_2020_2026.jsonl"] = sha256_file(c391.RAW_JSONL)
    hashes["scratchpad/etf_s0/input/stock_master_etf_fields.json"] = sha256_file(c391.DB_FIELDS)
    hashes["scratchpad/etf_s0/q_etf_fields_ro.py"] = sha256_file(c391.DB_QUERY)
    ref = json.load(open(C391_RESULTS))
    if hashes != ref["input_sha256"]:
        sys.exit("[c391b] 입력 sha256 이 cycle391 results.json 과 다르다 — 멈춘다.")
    script_sha = sha256_file(os.path.abspath(__file__))

    print("[c391b] meta / classification ...", flush=True)
    meta, last_date, n_last = c391.load_meta()
    dbj = json.load(open(c391.DB_FIELDS))
    db = {r["ticker"]: r for r in dbj["rows"]}
    agr_v1 = c391.agreement(meta, db, c391.rule_v1)
    v1_ok = agr_v1["precision"] >= 0.9 and agr_v1["recall"] >= 0.9
    rule_fn = c391.rule_v1 if v1_ok else c391.rule_v3
    cls = {}
    for t, mm in meta.items():
        if t in db:
            r = db[t]
            v = (r["grp"] == "EF" and r["txtn"] == "01" and r["mult"] == "1" and (r["heed"] or "N") != "Y")
        else:
            v = rule_fn(mm)
        cls[t] = bool(v and c391.live_code(t))
    if sum(cls.values()) != ref["classification"]["summary"]["U1_class_total"]:
        sys.exit("[c391b] U1 부류 수가 cycle391 과 다르다 — 멈춘다.")

    print("[c391b] load parquet / indicators ...", flush=True)
    df = pd.concat([pd.read_parquet(p) for p in c391.PARQUETS], ignore_index=True)
    cal = np.array(sorted(df["bas_dd"].unique()))
    cal_map = pd.Series(np.arange(len(cal)), index=pd.DatetimeIndex(cal))

    def cmap(vals):
        return cal_map.loc[pd.DatetimeIndex(vals)].to_numpy()

    need = {t for t, v in cls.items() if v} | {"069500"}
    data = {}
    for t, g in df[df["ticker"].isin(need)].groupby("ticker"):
        d = c391.build_ticker_cal(g, cmap, None)
        if d is not None:
            data[t] = d
    mu = c391.market_unit_series(data["069500"], len(cal))
    last_ci, ncal = len(cal) - 1, len(cal)
    tick_list = sorted(data)
    col = {t: i for i, t in enumerate(tick_list)}
    ret = np.full((len(cal), len(tick_list)), np.nan)
    for t, d in data.items():
        cc = np.full(len(cal), np.nan)
        cc[d["ci"]] = d["c"]
        ret[1:, col[t]] = cc[1:] / cc[:-1] - 1
    corr = c391.Corr(ret, col)
    dcls = {t: d for t, d in data.items() if cls.get(t)}

    def all_trades(gap_mode, exit_mode):
        allt = gen_trades_bundle(gap_mode, exit_mode, dcls, cls, mu, cal, meta, last_ci)
        return [t for t in allt if t["entry_date"] >= c391.FULL_START and t["m"] is not None]

    # ── 재현 관문 1: 일반화 함수(B,B) == cycle391 gen_trades("donchian") ──
    ref_trades = c391.gen_trades("donchian", dcls, cls, mu, cal, meta, last_ci)
    mine_trades = gen_trades_bundle("B", "B", dcls, cls, mu, cal, meta, last_ci)
    gate1 = (len(ref_trades) == len(mine_trades)) and all(
        all((a[k] == b[k]) or (a[k] != a[k] and b[k] != b[k]) for k in a) and a.keys() == b.keys()
        for a, b in zip(ref_trades, mine_trades))
    if not gate1:
        sys.exit("[c391b] 재현 관문 1 실패 — 일반화 함수가 cycle391 donchian 거래와 다르다.")
    print(f"[c391b] gate1 ok: {len(mine_trades)} raw donchian trades identical", flush=True)

    rng = np.random.default_rng(c391.SEED)

    DED = {}

    def evaluate(gap_mode, exit_mode, seed_base, with_extras=False):
        allt = all_trades(gap_mode, exit_mode)
        base = [t for t in allt if c391.full_u(t)]
        buy = [t for t in base if t["m"] > 0]
        ded, _ = c391.dedup(buy, corr, rep_select=False)
        DED[(gap_mode, exit_mode)] = ded
        st = c391.r_stats(ded, rng)
        sl = c391.sleeve(ded, seed_base, data, ncal)
        jd = c391.judge(st, sl)
        out = {"signals_full_universe": len(base), "signals_m_pos": len(buy), "dedup_m_pos": len(ded),
               "stats": st, "sleeve": sl, "judge": jd}
        if with_extras:
            ded_live, _ = c391.dedup([t for t in buy if t["listed_at_end"]], corr, rep_select=False)
            st_live = c391.r_stats(ded_live, rng)
            ratio = st["wR"] / st_live["wR"] if st_live["wR"] > 0 else float("nan")
            out["T6"] = {"wR_all": st["wR"], "wR_listed_only": st_live["wR"], "n_all": st["n"],
                         "n_listed_only": st_live["n"], "ratio": ratio,
                         "ok": bool(ratio == ratio and ratio >= c391.T6_MIN_RATIO)}
            out["judge"]["T6_warning_ok"] = out["T6"]["ok"]
            out["block_ci"] = c391.block_cis(ded)
            out["integrated_sleeve"] = {"rand": c391.sleeve_integrated(buy, corr, "rand", seed_base + 20000),
                                        "tv": c391.sleeve_integrated(buy, corr, "tv", c391.SEED)}
            v = {}
            ded_rep, n_sub = c391.dedup(buy, corr, rep_select=True)
            stv, slv = c391.r_stats(ded_rep, rng), c391.sleeve(ded_rep, seed_base, data, ncal)
            v["S1_rep_select_on"] = {"stats": stv, "sleeve": slv, "judge": c391.judge(stv, slv), "n_substituted": n_sub}
            ded9, _ = c391.dedup(buy, corr, rep_select=False, exit_day_holds=False)
            stv, slv = c391.r_stats(ded9, rng), c391.sleeve(ded9, seed_base, data, ncal)
            v["S9_exit_day_not_held"] = {"stats": stv, "sleeve": slv, "judge": c391.judge(stv, slv)}
            out["variants"] = v
            # 청산 사유별 건수·건당 R (판정판)
            out["exit_reason_R"] = {r_: [c391.wmean([t for t in ded if t["reason"] == r_]),
                                         sum(1 for t in ded if t["reason"] == r_)]
                                    for r_ in sorted({t["reason"] for t in ded})}
            out["trades"] = [{k: t[k] for k in ("ticker", "entry_date", "exit_date", "E", "exit_px", "reason",
                                                "Rnet", "m", "f", "size_atr_pct", "hold", "lot75")} for t in ded]
        return out

    print("[c391b] bundle B (cycle378 donchian) ...", flush=True)
    resB = evaluate("B", "B", SLEEVE_SEED, with_extras=True)
    # ── 재현 관문 2: B 판정판 == cycle391 donchian 판정판 ──
    rs, rl = ref["rules"]["donchian"]["stats"], ref["rules"]["donchian"]["sleeve"]
    chk = {
        "n": (resB["stats"]["n"], rs["n"]), "wR": (resB["stats"]["wR"], rs["wR"]),
        "ci95_lo": (resB["stats"]["ci95"][0], rs["ci95"][0]), "ci95_hi": (resB["stats"]["ci95"][1], rs["ci95"][1]),
        "wR_A": (resB["stats"]["wR_A"], rs["wR_A"]), "wR_ex2025": (resB["stats"]["wR_ex2025"], rs["wR_ex2025"]),
        "wR_ex_top1pct": (resB["stats"]["wR_ex_top1pct"], rs["wR_ex_top1pct"]),
        "ann_mean": (resB["sleeve"]["ann_mean"], rl["ann_mean"]), "mdd_median": (resB["sleeve"]["mdd_median"], rl["mdd_median"]),
        "T6_ratio": (resB["T6"]["ratio"], ref["rules"]["donchian"]["T6"]["ratio"]),
    }
    gate2 = all(abs(a - b) <= REPRO_TOL for a, b in chk.values())
    if not gate2:
        sys.exit(f"[c391b] 재현 관문 2 실패 — B 판정판이 cycle391 과 다르다: {chk}")
    print(f"[c391b] gate2 ok: B == cycle391 donchian judged (n={resB['stats']['n']}, wR={resB['stats']['wR']:+.4f})", flush=True)

    print("[c391b] bundle A (design §3.3/§4/§5) ...", flush=True)
    resA = evaluate("A", "A", SLEEVE_SEED, with_extras=True)

    print("[c391b] decomposition D1 / D2 ...", flush=True)
    resD1 = evaluate("B", "A", SLEEVE_SEED)   # A 청산·사이징 + B 갭
    resD2 = evaluate("A", "B", SLEEVE_SEED)   # B 청산·사이징 + A 갭

    # ── 감사 뒤 보고판(사후 — 판정에 쓰지 않는다). 판정판 계산이 끝난 뒤에만 돈다 ──
    print("[c391b] post-audit report variants ...", flush=True)
    resM1a = evaluate("B", "B_next_open", SLEEVE_SEED)
    resM1b = evaluate("B", "B_intraday", SLEEVE_SEED)
    resG0A = evaluate("none", "A", SLEEVE_SEED)
    resG0B = evaluate("none", "B", SLEEVE_SEED)

    adopted, text, pa, pb = decide(resA, resB)
    sens = {}
    for vn in ("S1_rep_select_on", "S9_exit_day_not_held"):
        a2, t2, p2a, p2b = decide(resA["variants"][vn], resB["variants"][vn])
        sens[vn] = {"adopted": a2, "text": t2, "A_pass": p2a, "B_pass": p2b}

    def atr_ratio(ded):
        r = np.array([data[t["ticker"]]["atr20"][t["j"]] / data[t["ticker"]]["n14"][t["j"]] for t in ded])
        a_pct = [data[t["ticker"]]["atr20"][t["j"]] / data[t["ticker"]]["c"][t["j"]] for t in ded]
        n_pct = [data[t["ticker"]]["n14"][t["j"]] / data[t["ticker"]]["c"][t["j"]] for t in ded]
        return {"n": len(ded), "median_atr20_over_n14": float(np.median(r)),
                "corr_pct": float(np.corrcoef(a_pct, n_pct)[0, 1])}

    def m1_row(res):
        a2, t2, p2a, p2b = decide(resA, res)
        return {"stats_core": {k: res["stats"][k] for k in ("n", "wR", "ci95", "wR_A", "ci95_A", "n_A", "wR_ex2025",
                                                           "wR_ex_top1pct", "exit_reasons", "hold_median")},
                "sleeve_core": {k: res["sleeve"][k] for k in ("ann_mean", "mdd_median", "ret_over_mdd",
                                                             "mtm_mdd_median", "ret_over_mtm_mdd")},
                "judge": res["judge"], "verdict_if_this_were_B": {"adopted": a2, "text": t2},
                "ratio_A_needs_to_rise_pct": (res["sleeve"]["ret_over_mdd"] / resA["sleeve"]["ret_over_mdd"] - 1) * 100}

    post_audit = {
        "_note": "감사 뒤 추가(사후). 판정에 쓰지 않는다. prereg §4 의 보고판 목록 밖이다.",
        "M1_B_line_next_open": m1_row(resM1a),
        "M1_B_line_intraday_m12_only": m1_row(resM1b),
        "M1_B_line_close_judged": m1_row(resB),
        "gap_none": {"A": m1_row(resG0A), "B": m1_row(resG0B)},
        "I1_delisted_ticker_trades": {"A": resA["stats"]["n_delisted_ticker_trades"],
                                      "B": resB["stats"]["n_delisted_ticker_trades"]},
        "I2_atr20_over_n14": {"A_judged": atr_ratio(DED[("A", "A")]), "B_judged": atr_ratio(DED[("B", "B")])},
        "L2_sleeve_trades_per_run": {b: {"judged": r_["sleeve"]["trades_per_run_mean"],
                                         "integrated_rand": r_["integrated_sleeve"]["rand"]["trades_per_run_mean"],
                                         "integrated_tv": r_["integrated_sleeve"]["tv"]["trades_per_run_mean"],
                                         "ann": [r_["sleeve"]["ann_mean"], r_["integrated_sleeve"]["rand"]["ann_mean"],
                                                 r_["integrated_sleeve"]["tv"]["ann_mean"]],
                                         "ratio": [r_["sleeve"]["ret_over_mdd"],
                                                   r_["integrated_sleeve"]["rand"]["ret_over_mdd"],
                                                   r_["integrated_sleeve"]["tv"]["ret_over_mdd"]]}
                                     for b, r_ in (("A", resA), ("B", resB))},
    }

    out = {
        "script_version": SCRIPT_VERSION,
        "generated_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "runtime_sec": round(time.time() - T0, 1),
        "prereg_sha256": _prereg_sha, "script_sha256": script_sha, "base_module_sha256": _base_sha,
        "input_sha256": hashes, "seed_boot": c391.SEED, "seed_sleeve": SLEEVE_SEED,
        "repro_gate1_raw_trades_identical": gate1, "repro_gate2_B_equals_cycle391": gate2,
        "repro_gate2_detail": {k: [a, b] for k, (a, b) in chk.items()},
        "verdict": {"adopted": adopted, "text": text, "A_pass": pa, "B_pass": pb},
        "sensitivity_verdicts": sens,
        "bundles": {"A": resA, "B": resB, "D1_Aexit_Bgap": resD1, "D2_Bexit_Agap": resD2},
        "post_audit_report_only": post_audit,
    }
    core = {k: v for k, v in c391.clean(out).items() if k not in ("generated_at_kst", "runtime_sec")}
    out["result_core_sha256"] = hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    # 판정 수치(스크립트 정체와 무관한 부분)가 v1 과 같은가
    jkeys = ("verdict", "sensitivity_verdicts", "bundles", "repro_gate1_raw_trades_identical",
             "repro_gate2_B_equals_cycle391", "repro_gate2_detail", "prereg_sha256", "input_sha256")

    def judged_sha(o):
        return hashlib.sha256(json.dumps({k: o[k] for k in jkeys}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    out["judged_payload_sha256"] = judged_sha(c391.clean(out))
    v1p = os.path.join(HERE, "results_v1.json")
    if os.path.exists(v1p):
        v1 = json.load(open(v1p))
        out["judged_payload_sha256_v1"] = judged_sha(v1)
        out["judged_payload_equal_v1"] = out["judged_payload_sha256"] == out["judged_payload_sha256_v1"]
    else:
        out["judged_payload_sha256_v1"], out["judged_payload_equal_v1"] = None, None
    with open(os.path.join(HERE, "results.json"), "w") as fh:
        json.dump(c391.clean(out), fh, ensure_ascii=False, indent=1, allow_nan=False)
    write_md(c391.clean(out))
    with open(RUNS_LOG, "a") as fh:
        fh.write("\t".join([out["generated_at_kst"], SCRIPT_VERSION, f"prereg={_prereg_sha}", f"script={script_sha}",
                            f"result_core={out['result_core_sha256']}", f"verdict={adopted}",
                            f"judged_payload={out['judged_payload_sha256']}",
                            f"equal_v1={out['judged_payload_equal_v1']}"]) + "\n")
    print(f"[c391b] verdict: {text} · core {out['result_core_sha256'][:16]} · {out['runtime_sec']}s", flush=True)


# ════════════════════════════════════════════════════════════════════
# results.md
# ════════════════════════════════════════════════════════════════════
def fmt(v, p=3, sign=True):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "—"
    return f"{v:+.{p}f}" if sign else f"{v:.{p}f}"


def write_md(o):
    L = []
    a = L.append
    ox = lambda b: "O" if b else "X"
    A, B = o["bundles"]["A"], o["bundles"]["B"]
    a("# cycle391b 결과 — ETF 추세 전략 청산·수량 묶음 비교 (진입 2안 donchian형 고정)")
    a("")
    a(f"- 생성 {o['generated_at_kst']} · {o['runtime_sec']}초 · 스크립트 {o['script_version']} `{o['script_sha256']}`")
    a(f"- 사전 등록 `prereg.md` sha256 `{o['prereg_sha256']}` · 재사용 모듈 `{o['base_module_sha256']}`")
    a(f"- 결과 핵심 sha256 `{o['result_core_sha256']}` · 재현 관문: 원거래 동일 {o['repro_gate1_raw_trades_identical']} · B = cycle391 판정판 {o['repro_gate2_B_equals_cycle391']}")
    a(f"- 판정 수치 sha256 `{o['judged_payload_sha256']}` · v1(`results_v1.json`)과 같음: {o['judged_payload_equal_v1']}")
    a("")
    a(f"## 판정: **{o['verdict']['text']}**")
    a("")
    a("| 문턱 | 기준 | 묶음 A (설계서 §3.3·§4·§5) | | 묶음 B (cycle378 donchian 대리) | |")
    a("|---|---|---|---|---|---|")
    sa, sb, la, lb, ja, jb = A["stats"], B["stats"], A["sleeve"], B["sleeve"], A["judge"], B["judge"]
    a(f"| T1 | 건당 R ≥ +0.15 ∧ 95% 하한 > 0 | {fmt(sa['wR'])} [{fmt(sa['ci95'][0])}, {fmt(sa['ci95'][1])}] (n={sa['n']}) | {ox(ja['T1'])} | "
      f"{fmt(sb['wR'])} [{fmt(sb['ci95'][0])}, {fmt(sb['ci95'][1])}] (n={sb['n']}) | {ox(jb['T1'])} |")
    a(f"| T2 | A(2021~22) ≥ −0.20 | {fmt(sa['wR_A'])} (n={sa['n_A']}) | {ox(ja['T2'])} | {fmt(sb['wR_A'])} (n={sb['n_A']}) | {ox(jb['T2'])} |")
    a(f"| T3 | 2025 제외 > 0 | {fmt(sa['wR_ex2025'])} (n={sa['n_ex2025']}) | {ox(ja['T3'])} | {fmt(sb['wR_ex2025'])} (n={sb['n_ex2025']}) | {ox(jb['T3'])} |")
    a(f"| T4 | 상위 1% 제외 > 0 | {fmt(sa['wR_ex_top1pct'])} ({sa['top1pct_k']}건 제외) | {ox(ja['T4'])} | {fmt(sb['wR_ex_top1pct'])} ({sb['top1pct_k']}건 제외) | {ox(jb['T4'])} |")
    a(f"| T5 | 연 수익 > 0 ∧ 근사 MDD ≥ −20%p | {fmt(la['ann_mean'],1)}%/년 · {fmt(la['mdd_median'],1)}%p | {ox(ja['T5'])} | "
      f"{fmt(lb['ann_mean'],1)}%/년 · {fmt(lb['mdd_median'],1)}%p | {ox(jb['T5'])} |")
    a(f"| T6 (경고) | 폐지 포함 ÷ 현재 상장분 ≥ 0.5 | {fmt(A['T6']['wR_all'])} ÷ {fmt(A['T6']['wR_listed_only'])} = {fmt(A['T6']['ratio'],2,False)} | {ox(A['T6']['ok'])} | "
      f"{fmt(B['T6']['wR_all'])} ÷ {fmt(B['T6']['wR_listed_only'])} = {fmt(B['T6']['ratio'],2,False)} | {ox(B['T6']['ok'])} |")
    a(f"| **T1~T5** | | | **{'통과' if ja['pass_T1_T5'] else '탈락'}** | | **{'통과' if jb['pass_T1_T5'] else '탈락'}** |")
    a(f"| 비 | 연 수익 ÷ \\|근사 MDD\\| | {fmt(la['ret_over_mdd'],2,False)} | | {fmt(lb['ret_over_mdd'],2,False)} | |")
    a("")
    a("## 상세 (판정판)")
    a("")
    a("| 항목 | 묶음 A | 묶음 B |")
    a("|---|---|---|")
    for p in ("A", "B", "H"):
        a(f"| 기간 {p} 건당 R [95%] (n) | {fmt(sa['wR_'+p])} [{fmt(sa['ci95_'+p][0])}, {fmt(sa['ci95_'+p][1])}] ({sa['n_'+p]}) | "
          f"{fmt(sb['wR_'+p])} [{fmt(sb['ci95_'+p][0])}, {fmt(sb['ci95_'+p][1])}] ({sb['n_'+p]}) |")
    yk = " · ".join(f"{y} {fmt(v[0],2)}({v[1]})" for y, v in sa["wR_by_year"].items())
    yb = " · ".join(f"{y} {fmt(v[0],2)}({v[1]})" for y, v in sb["wR_by_year"].items())
    a(f"| 연도별 R(건수) | {yk} | {yb} |")
    a(f"| m 상태별 R(건수) | {' · '.join(f'm={m} {fmt(v[0],2)}({v[1]})' for m, v in sa['by_m'].items())} | "
      f"{' · '.join(f'm={m} {fmt(v[0],2)}({v[1]})' for m, v in sb['by_m'].items())} |")
    a(f"| 승률 · 평균 이익/손실 · 손익비 | {sa['win_rate']*100:.0f}% · {fmt(sa['avg_win'],2)}/{fmt(sa['avg_loss'],2)} · {fmt(sa['payoff'],2,False)} | "
      f"{sb['win_rate']*100:.0f}% · {fmt(sb['avg_win'],2)}/{fmt(sb['avg_loss'],2)} · {fmt(sb['payoff'],2,False)} |")
    a(f"| 최대 R · 보유 중앙 | {fmt(sa['max_R'],2)} · {sa['hold_median']:.0f}봉 | {fmt(sb['max_R'],2)} · {sb['hold_median']:.0f}봉 |")
    a(f"| 청산 사유 비율 | {sa['exit_reasons']} | {sb['exit_reasons']} |")
    a(f"| 청산 사유별 건당 R(건수) | {' · '.join(f'{k} {fmt(v[0],2)}({v[1]})' for k, v in A['exit_reason_R'].items())} | "
      f"{' · '.join(f'{k} {fmt(v[0],2)}({v[1]})' for k, v in B['exit_reason_R'].items())} |")
    a(f"| 사이징 ATR/종가 중앙 · f 중앙 | {sa['size_atr_pct_median']*100:.2f}% · {sa['f_median']:.2f} | {sb['size_atr_pct_median']*100:.2f}% · {sb['f_median']:.2f} |")
    a(f"| 슬리브 A / B / H (%/년) | {fmt(la['ann_A'],1)} / {fmt(la['ann_B'],1)} / {fmt(la['ann_H'],1)} | {fmt(lb['ann_A'],1)} / {fmt(lb['ann_B'],1)} / {fmt(lb['ann_H'],1)} |")
    a(f"| 슬리브 연 체결 A / B / H | {la['tpy_A']:.0f} / {la['tpy_B']:.0f} / {la['tpy_H']:.0f} | {lb['tpy_A']:.0f} / {lb['tpy_B']:.0f} / {lb['tpy_H']:.0f} |")
    a(f"| 슬리브 40회 연 수익 범위 · 근사 MDD 최악/최선 | {fmt(la['ann_min'],1)}~{fmt(la['ann_max'],1)}% · {fmt(la['mdd_worst'],1)}/{fmt(la['mdd_best'],1)} | "
      f"{fmt(lb['ann_min'],1)}~{fmt(lb['ann_max'],1)}% · {fmt(lb['mdd_worst'],1)}/{fmt(lb['mdd_best'],1)} |")
    a(f"| 일별 평가 MDD 중앙(최악) · 비 | {fmt(la['mtm_mdd_median'],1)}({fmt(la['mtm_mdd_worst'],1)}) · {fmt(la['ret_over_mtm_mdd'],2,False)} | "
      f"{fmt(lb['mtm_mdd_median'],1)}({fmt(lb['mtm_mdd_worst'],1)}) · {fmt(lb['ret_over_mtm_mdd'],2,False)} |")
    ba, bb = A["block_ci"], B["block_ci"]
    for lab, k in (("T1 95% 월 묶음", "full_month"), ("T1 95% 겹침 구간 묶음", "full_overlap"), ("A 95% 진입일 묶음", "A_day"),
                   ("A 95% 월 묶음", "A_month"), ("A 95% 겹침 구간 묶음", "A_overlap")):
        a(f"| {lab} | [{fmt(ba[k][0])}, {fmt(ba[k][1])}] | [{fmt(bb[k][0])}, {fmt(bb[k][1])}] |")
    ia, ib = A["integrated_sleeve"], B["integrated_sleeve"]
    for lab, k in (("통합 슬리브 무작위 40회", "rand"), ("통합 슬리브 거래대금 순서", "tv")):
        a(f"| {lab}: 연 수익 · MDD · 비 | {fmt(ia[k]['ann_mean'],1)}% · {fmt(ia[k]['mdd_median'],1)} · {fmt(ia[k]['ret_over_mdd'],2,False)} | "
          f"{fmt(ib[k]['ann_mean'],1)}% · {fmt(ib[k]['mdd_median'],1)} · {fmt(ib[k]['ret_over_mdd'],2,False)} |")
    a(f"| 정수 랏 0주(예산 75만) · 뺀 건당 R | {sa['lot75_zero']} · {fmt(sa['wR_excl_lot75_zero'])} | {sb['lot75_zero']} · {fmt(sb['wR_excl_lot75_zero'])} |")
    a(f"| 신호 §2 전체 / m>0 / 중복 제거 | {A['signals_full_universe']} / {A['signals_m_pos']} / {A['dedup_m_pos']} | {B['signals_full_universe']} / {B['signals_m_pos']} / {B['dedup_m_pos']} |")
    a("")
    a("## 보고용 판 (판정에 쓰지 않는다 — prereg §4)")
    a("")
    a("| 판 | 묶음 | T1 R [하한] (n) | T2 A | T3 | T4 | T5 연수익 · MDD (비) | T1~T5 |")
    a("|---|---|---|---|---|---|---|---|")

    def vrow(lab, name, v):
        s, l_, j = v["stats"], v["sleeve"], v["judge"]
        a(f"| {lab} | {name} | {fmt(s['wR'])} [{fmt(s['ci95'][0])}] ({s['n']}) {ox(j['T1'])} | {fmt(s['wR_A'])} {ox(j['T2'])} | "
          f"{fmt(s['wR_ex2025'])} {ox(j['T3'])} | {fmt(s['wR_ex_top1pct'])} {ox(j['T4'])} | "
          f"{fmt(l_['ann_mean'],1)}% · {fmt(l_['mdd_median'],1)} ({fmt(l_['ret_over_mdd'],2,False)}) {ox(j['T5'])} | {'통과' if j['pass_T1_T5'] else '탈락'} |")

    vrow("D1", "A 청산·사이징 + B 갭", o["bundles"]["D1_Aexit_Bgap"])
    vrow("D2", "B 청산·사이징 + A 갭", o["bundles"]["D2_Bexit_Agap"])
    for vn, lab in (("S1_rep_select_on", "S1 대표 선택 켬"), ("S9_exit_day_not_held", "S9 M8 반대")):
        vrow(lab, "A", A["variants"][vn])
        vrow("", "B", B["variants"][vn])
        a(f"| | → 이 판의 판정 | {o['sensitivity_verdicts'][vn]['text']} | | | | | |")
    a("")
    pa_ = o["post_audit_report_only"]
    a("## 감사 뒤 추가 판 (사후 — 판정에 쓰지 않는다, prereg §4 목록 밖)")
    a("")
    a("### M1 — B 의 「돌파선 아래」 청산을 어떻게 집행하나 (A 는 판정판 그대로)")
    a("")
    a("| B 의 읽기 | T1 R [하한] (n) | T2 A [95%] | T3 | T4 | T5 연수익 · MDD (비) | 일별 평가 MDD (비) | T1~T5 | 이 읽기로 판정했다면 | B 비 ÷ A 비 − 1 |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for lab, k in (("종가 청산(판정판, M12)", "M1_B_line_close_judged"), ("다음 날 시가 청산(§4.3 경로)", "M1_B_line_next_open"),
                   ("장중 이탈(M12 만 장중)", "M1_B_line_intraday_m12_only")):
        r_ = pa_[k]
        s, l_, j = r_["stats_core"], r_["sleeve_core"], r_["judge"]
        a(f"| {lab} | {fmt(s['wR'])} [{fmt(s['ci95'][0])}] ({s['n']}) | {fmt(s['wR_A'])} [{fmt(s['ci95_A'][0])}, {fmt(s['ci95_A'][1])}] | "
          f"{fmt(s['wR_ex2025'])} | {fmt(s['wR_ex_top1pct'])} | {fmt(l_['ann_mean'],1)}% · {fmt(l_['mdd_median'],1)} ({fmt(l_['ret_over_mdd'],2,False)}) | "
          f"{fmt(l_['mtm_mdd_median'],1)} ({fmt(l_['ret_over_mtm_mdd'],2,False)}) | {'통과' if j['pass_T1_T5'] else '탈락'} | "
          f"{r_['verdict_if_this_were_B']['text']} | {r_['ratio_A_needs_to_rise_pct']:+.0f}% |")
    a("")
    a("### 갭 규칙을 두 묶음에 똑같이 — 갭 규칙 없음")
    a("")
    a("| 묶음 | T1 R (n) | T2 A | T5 연수익 · MDD (비) | T1~T5 |")
    a("|---|---|---|---|---|")
    for b in ("A", "B"):
        r_ = pa_["gap_none"][b]
        s, l_, j = r_["stats_core"], r_["sleeve_core"], r_["judge"]
        a(f"| {b} 청산·사이징 | {fmt(s['wR'])} ({s['n']}) | {fmt(s['wR_A'])} | {fmt(l_['ann_mean'],1)}% · {fmt(l_['mdd_median'],1)} ({fmt(l_['ret_over_mdd'],2,False)}) | "
          f"{'통과' if j['pass_T1_T5'] else '탈락'} |")
    a("")
    a("### 참고 수치")
    a("")
    i2 = pa_["I2_atr20_over_n14"]
    a(f"- I1 상장폐지 종목 거래(판정판): A {pa_['I1_delisted_ticker_trades']['A']}건 · B {pa_['I1_delisted_ticker_trades']['B']}건 — T6 = 1.00 은 검증 없이 나온 값")
    a(f"- I2 ATR20/N 비 중앙 · %끼리 상관: A 판정판 {i2['A_judged']['median_atr20_over_n14']:.3f} · {i2['A_judged']['corr_pct']:.3f} / "
      f"B 판정판 {i2['B_judged']['median_atr20_over_n14']:.3f} · {i2['B_judged']['corr_pct']:.3f}")
    for b in ("A", "B"):
        x = pa_["L2_sleeve_trades_per_run"][b]
        a(f"- L2 {b}: 회당 체결 판정판 {x['judged']:.1f} · 통합 무작위 {x['integrated_rand']:.1f} · 통합 거래대금 순 {x['integrated_tv']:.1f} / "
          f"연 수익 {x['ann'][0]:+.1f} · {x['ann'][1]:+.1f} · {x['ann'][2]:+.1f}% / 비 {x['ratio'][0]:.2f} · {x['ratio'][1]:.2f} · {x['ratio'][2]:.2f}")
    a("")
    with open(os.path.join(HERE, "results.md"), "w") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    main()
