"""cycle372 — 피라미딩 S0 과거 재현을 KRX 5년 보관소로 다시 돌린다 (읽기 전용, 프로덕션 코드 아님).

선행 = `cycle351_pyramid_s0_replay.py`(S0 정의·함수) · `cycle361_daily_retention_730.md` §6 C-3(두 유니버스)
· `cycle362_krx_archive_build.md`(보관소). 결과 = `cycle372_s0_archive_replay.md`.

운영 DB·KIS·KRX 호출 0. 로컬 파일만 읽는다.
  - 보관소: `data/archive/krx_daily/krx_daily_dump_2020-2025.json.gz`(수정본 OHLC · 거래량 · 거래대금)
            + `parquet/*.parquet`(그날 시총 `mktcap` 원 단위 · 누적 조정계수 `adj_factor`)
  - cycle351 덤프(오늘 시총 `hts_avls_eok` · kojiro 예산 · 2025-10-10~2026-09-23 DB 일봉)

재사용(재구현 0): `build_series` · `baseline` · `free_sim` · `grid` · `summarize` · `base_summary`
· `theo_peak` · `ci_cluster` · `ci_iid` · `budgets` · `window_n` 은 cycle351 모듈을 **파일 경로로 import** 해서
그대로 부른다. 사다리 = 저장소 leaf `src/engine/pyramid_shadow.py`(`overlay_ladder` 등)를 파일 경로로 import.

새로 쓴 것은 셋뿐이다.
  1. `proxy_raw` — cycle351 `proxy_entries` 의 조건 루프를 dedup **앞**에서 끊어 낸 것. 유니버스 ② 는
     그날 시총을 dedup 전에 걸어야 해서다. `dedup(proxy_raw(x)) == s0.proxy_entries(x)` 를 매 실행 단언한다.
  2. `indep_overlay_v2` — cycle351 `indep_overlay`(명세 §1-2 재구현)에 committed leaf 가 cycle351 S0
     실행 **뒤에** 더한 두 규칙(독립 검증 지적 #17: `_stop_floor` 래칫 · kojiro live ATR 「기존 2N 선」,
     설계 §4-1)을 덧댄 교차검산용 구현.
  3. 유니버스 필터 · 연도/분기/장세 분할 · 주·월·분기 묶음 구간 · 트랜치 분해 · 풀링 · 데이터 품질 민감도.

유니버스 (cycle361 §6 C-3)
  ① today — 오늘(cycle351 덤프, 2026-09-23) `hts_avls_eok >= 500` 인 6자리 종목만 (cycle351 과 같은 정의)
  ② asof   — 신호봉 날짜의 KRX `mktcap >= 500억 원` 인 6자리 종목 (상장폐지 포함 — 생존 편향 제거)

사용:
  python cycle372_s0_archive_replay.py run <cycle351 dump.jsonl.gz> <out_dir>
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)

_spec = importlib.util.spec_from_file_location("c351_s0", os.path.join(HERE, "cycle351_pyramid_s0_replay.py"))
s0 = importlib.util.module_from_spec(_spec)
sys.modules["c351_s0"] = s0
_spec.loader.exec_module(s0)

ARCH = os.path.join(REPO, "data", "archive", "krx_daily")
ARCH_DUMP = os.path.join(ARCH, "krx_daily_dump_2020-2025.json.gz")
LEAF = os.path.join(REPO, "src", "engine", "pyramid_shadow.py")
C_STAR = "s1N_t3_eq_f0.67"
MCAP_MIN_WON = 500 * 100_000_000  # 500억 원 (KRX mktcap 은 원 단위)
JUMP = 0.35                        # 가격제한폭 ±30% 를 넘는 하루 움직임 = 수정주가/거래정지 이음매 의심


def _is6(t):
    return len(t) == 6 and t.isdigit()


# ═══════════════════════════════════ 입력 ═══════════════════════════════════

def load_archive():
    import pandas as pd
    with gzip.open(ARCH_DUMP, "rt", encoding="utf-8") as fh:
        daily = json.load(fh)["daily"]
    fs = sorted(f for f in os.listdir(os.path.join(ARCH, "parquet")) if f.endswith(".parquet"))
    pq = pd.concat([pd.read_parquet(os.path.join(ARCH, "parquet", f),
                                    columns=["ticker", "bas_dd", "mktcap", "adj_factor", "close_adj"])
                    for f in fs], ignore_index=True)
    pq["d"] = pq["bas_dd"].dt.strftime("%Y-%m-%d")
    # json.gz 와 parquet 이 같은 원장인지 — 행 수 · 종가 전수 대조
    n_json = sum(len(v) for v in daily.values())
    chk = {(t, r[0]): r[4] for t, rows in daily.items() for r in rows}
    bad = sum(1 for t, d, c in zip(pq["ticker"], pq["d"], pq["close_adj"])
              if abs(float(chk.get((t, d), -1e18)) - float(c)) > 1e-6)
    meta = dict(json_rows=n_json, parquet_rows=len(pq), close_mismatch=bad,
                dates=int(pq["d"].nunique()), first=pq["d"].min(), last=pq["d"].max(),
                tickers=int(pq["ticker"].nunique()))
    side = {(t, d): (int(m), float(a)) for t, d, m, a in zip(pq["ticker"], pq["d"], pq["mktcap"], pq["adj_factor"])}
    return daily, side, meta


def series_from_daily(daily, tickers):
    """cycle351 `build_series` 를 그대로 부른다 — 유니버스 판정을 밖에서 하므로 master 는 전부 500 으로 둔다."""
    fake = {"master": {"rows": [[t, None, 500, None] for t in tickers]}, "daily": daily}
    series = s0.build_series(fake)
    return series


# ═══════════════════════════════════ 대리 진입 ═══════════════════════════════════

def proxy_raw(series):
    """cycle351 `proxy_entries` 의 조건 루프(dedup 전). 반환 = [(t, i0=i+1, N=atr[i])]."""
    import numpy as np
    out = []
    for t, s in series.items():
        st, up, atr, cl, tv, o = s["st"], s["up"], s["atr"], s["c"], s["tv"], s["o"]
        n = len(cl)
        for i in range(s0.WARM_I, n - 1):
            if st[i] != 1 or not up[i]:
                continue
            if not any(st[k] == 6 and st[k + 1] == 1 for k in range(max(0, i - 5), i)):
                continue
            ar = atr[i] / cl[i]
            if not (0.01 <= ar <= 0.06):
                continue
            if cl[i] <= s["ema_s"][i]:
                continue
            if np.median(tv[max(0, i - 20):i + 1]) < 1e9:
                continue
            gap = (o[i + 1] / cl[i] - 1) * 100
            if gap >= 5 or gap <= -4:
                continue
            out.append((t, i + 1, float(atr[i])))
    return out


def dedup(entries):
    ded, last = [], {}
    for t, i, N in entries:
        if t in last and i - last[t] < 10:
            continue
        last[t] = i
        ded.append((t, i, N))
    return ded


# ═══════════════════════════════════ 교차검산 (committed leaf 규칙 반영) ═══════════════════════════════════

_STOP_KINDS_V2 = {"gap", "set_line", "avg_backstop", "avg_breakeven", "stop_after_add", "existing_2n_live"}


def indep_overlay_v2(bars, E, N, step, sizes, stop_atr, hard_pct, be_mult, be_atr, no_add,
                     anchor_idx, anchor_price, anchor_add_allowed, gap_mult=s0.GAP_SKIP):
    """cycle351 `indep_overlay` + 설계 §4-1 두 항목 — ① 「기존 2N 선」 = 평단 − stop_atr × 그날 ATR(D-1)
    ② 사다리 선은 `_stop_floor` 처럼 조이기만 한다(그날 값이 이전 최댓값보다 클 때만 갱신, 종류도 함께)."""
    r_unit = stop_atr * N
    fills = [(0, E, sizes[0])]
    last, k = E, 1
    hsb = bars[0][2]
    floor = [None, None]

    def avg_now():
        q = sum(f[2] for f in fills)
        return sum(f[1] * f[2] for f in fills) / q

    def ladder_line(d):
        av = avg_now()
        A = be_atr[d - 1] if be_atr is not None else N
        terms = [("set_line", last - stop_atr * N), ("avg_backstop", av * (1 + hard_pct / 100.0))]
        if be_atr is not None:
            terms.append(("existing_2n_live", av - stop_atr * A))
        if be_mult > 0 and hsb >= av + be_mult * A:
            terms.append(("avg_breakeven", av))
        best = terms[0]
        for tm in terms[1:]:
            if tm[1] > best[1]:
                best = tm
        if floor[0] is None or best[1] > floor[0]:
            floor[0], floor[1] = best[1], best[0]
        return floor[0], floor[1]

    def risk_now():
        ln = (last - stop_atr * N) if k >= 2 else (E - stop_atr * N)
        return sum(f[2] * (f[1] - ln) for f in fills) / r_unit

    peak = risk_now()
    ex = None
    if anchor_idx == 0:
        ex = (0, float(anchor_price), "anchor")
    d = 1
    while ex is None and d < len(bars):
        _, o, h, lo, cl = bars[d]
        is_anchor = anchor_idx is not None and d == anchor_idx
        if k >= 2:
            ln, kind = ladder_line(d)
            px = None
            if o <= ln:
                px, kd = o, "gap"
            elif lo <= ln:
                px, kd = ln, kind
            if px is not None:
                if is_anchor and anchor_price > px:
                    px, kd = anchor_price, "anchor"
                ex = (d, px, kd)
        if ex is None and not no_add[d] and not (is_anchor and not anchor_add_allowed):
            while k < len(sizes):
                lvl = last + step * N
                if o >= lvl * gap_mult:
                    break
                if h < lvl:
                    break
                fp = max(lvl, o)
                fills.append((d, fp, sizes[k]))
                last = fp
                k += 1
                peak = max(peak, risk_now())
                ln2, _ = ladder_line(d)
                if lo <= ln2:
                    px, kd = ln2, "stop_after_add"
                    if is_anchor and anchor_price > px:
                        px, kd = anchor_price, "anchor"
                    ex = (d, px, kd)
                    break
        if ex is None and is_anchor:
            ex = (d, float(anchor_price), "anchor")
        hsb = max(hsb, h)
        d += 1
    if ex is None:
        ex = (len(bars) - 1, float(bars[-1][4]), "open")
    vR = sum(f[2] * (ex[1] - f[1]) for f in fills) / r_unit
    killed = int(k >= 2 and ex[2] in _STOP_KINDS_V2 and (anchor_idx is None or ex[0] < anchor_idx))
    return dict(tranches=k, fills=fills, exit_idx=ex[0], exit_price=ex[1], exit_kind=ex[2],
                virtual_R=vR, killed=killed, peak_risk_R=peak,
                set_stop=(last - stop_atr * N) if k >= 2 else None, avg=avg_now())


# ═══════════════════════════════════ 표본 A 한 벌 ═══════════════════════════════════

def run_sample_a(series, entries, leaf, rng, label, nominal_n=None, jump_flag=None):
    """cycle351 `analyze` 의 표본 A 부분(격자 24 × 앵커·자유 + 교차검산)을 그대로 따른다."""
    import numpy as np
    t_start = time.time()
    for s in series.values():
        if "flags" not in s:
            s["flags"] = leaf.no_add_flags(s["dates"])
    base_R, keys, cost_b, base_ex = [], [], [], []
    for t, i0, N in entries:
        s = series[t]
        j, px, why = s0.baseline(s, i0, N)
        E = float(s["o"][i0])
        base_R.append((px - E) / (s0.STOP_ATR * N))
        keys.append(s["dates"][i0].isoformat())
        cost_b.append(0.0025 * E / (s0.STOP_ATR * N))
        base_ex.append((j, px, why))
    res = dict(label=label, n=len(entries), tickers=len({e[0] for e in entries}), entry_days=len(set(keys)),
               first_entry=min(keys) if keys else None, last_entry=max(keys) if keys else None)
    res["base"] = s0.base_summary(base_R, keys, rng)
    res["base_exit_kinds"] = dict(Counter(b[2] for b in base_ex))
    anchor_res, free_res = {}, {}
    per = dict(key=keys, base_R=base_R, ticker=[e[0] for e in entries])
    xc_total, xc_bad = 0, []
    for name, step, sizes in s0.grid():
        cfg = leaf.LadderConfig(step_n=step, sizes=sizes, gap_skip_mult=s0.GAP_SKIP)
        a_recs, f_recs, cost_va, cost_vf = [], [], [], []
        for (t, i0, N), (j, px, why) in zip(entries, base_ex):
            s = series[t]
            E = float(s["o"][i0])
            bars = [(s["dates"][x], float(s["o"][x]), float(s["h"][x]), float(s["l"][x]), float(s["c"][x]))
                    for x in range(i0, j + 1)]
            flags = leaf.no_add_flags([b[0] for b in bars])
            be_atr = [float(s["atr"][x]) for x in range(i0, j + 1)]
            anchored = why != "open"
            a_idx = (j - i0) if anchored else None
            a_px = px if anchored else None
            allow = why in ("line", "time")
            out = leaf.overlay_ladder(bars, 0, E, N, cfg=cfg, stop_atr=s0.STOP_ATR, hard_stop_pct=s0.HARD,
                                      be_mult=s0.BE, be_atr=be_atr, no_add=flags, anchor_idx=a_idx,
                                      anchor_price=a_px, anchor_add_allowed=allow)
            a_recs.append(out)
            cost_va.append(0.0025 * sum(sz * p for _, p, sz in out["fills"]) / (s0.STOP_ATR * N))
            ind = indep_overlay_v2(bars, E, N, step, sizes, s0.STOP_ATR, s0.HARD, s0.BE, be_atr, flags,
                                   a_idx, a_px, allow)
            bad = s0._cmp(out, ind)
            xc_total += 1
            if bad:
                xc_bad.append(dict(config=name, ticker=t, entry=s["dates"][i0].isoformat(), fields=bad))
            fr = s0.free_sim(s, i0, N, N, step, sizes, s["flags"])
            fr["killed"] = int(fr["tranches"] >= 2 and fr["why"] in ("gap", "line", "stop_after_add")
                               and fr["exit_j"] < j)
            f_recs.append(fr)
            cost_vf.append(0.0025 * sum(sz * p for _, p, sz in fr["fills"]) / (s0.STOP_ATR * N))
        pk = s0.theo_peak(step, sizes)
        anchor_res[name] = s0.summarize(a_recs, base_R, keys, cost_va, cost_b, pk, rng)
        anchor_res[name]["exit_kinds"] = dict(Counter(r["exit_kind"] for r in a_recs))
        free_res[name] = s0.summarize(f_recs, base_R, keys, cost_vf, cost_b, pk, rng)
        free_res[name]["later_than_base"] = float(np.mean([fr["exit_j"] > b[0] for fr, b in zip(f_recs, base_ex)]))
        if name == C_STAR:
            per["anchor_vR"] = [r["virtual_R"] for r in a_recs]
            per["anchor_killed"] = [r["killed"] for r in a_recs]
            per["anchor_tranches"] = [r["tranches"] for r in a_recs]
            per["anchor_cost"] = cost_va
            per["free_vR"] = [r["virtual_R"] for r in f_recs]
            per["cost_b"] = cost_b
            res["cstar_killed_by_kind"] = dict(Counter(r["exit_kind"] for r in a_recs if r["killed"]))
    res["anchor"] = anchor_res
    res["free"] = free_res
    res["crosscheck_v2"] = dict(records=xc_total, mismatched=len(xc_bad), sample=xc_bad[:10])
    k1 = 0
    for (t, i0, N), (j, px, why) in zip(entries, base_ex):
        fr = s0.free_sim(series[t], i0, N, N, 1.0, (1.0,), series[t]["flags"])
        if (fr["exit_j"], round(fr["exit_px"], 6), fr["why"]) != (j, round(px, 6), why):
            k1 += 1
    res["free_k1_vs_base_mismatch"] = k1
    if nominal_n is not None:
        per["nominal_n"] = nominal_n
    if jump_flag is not None:
        per["jump"] = jump_flag
    res["elapsed_s"] = round(time.time() - t_start, 1)
    return res, per


# ═══════════════════════════════════ 분할 · 풀링 ═══════════════════════════════════

def delta_stats(d, keys, rng, killed=None, base=None):
    import numpy as np
    d = np.asarray(d, float)
    if len(d) == 0:
        return dict(n=0)
    ci, nd = s0.ci_cluster(d, keys, rng)
    out = dict(n=int(len(d)), days=nd, delta=float(d.mean()), ci_cluster=ci)
    if killed is not None:
        out["killed"] = float(np.mean(killed))
    if base is not None:
        out["base_mean"] = float(np.mean(base))
    return out


def splits(per, rng, breadth=None):
    import numpy as np
    keys = per["key"]
    B = np.array(per["base_R"])
    dA = np.array(per["anchor_vR"]) - B
    dF = np.array(per["free_vR"]) - B
    K = np.array(per["anchor_killed"])
    out = {}
    by = defaultdict(list)
    for ix, k in enumerate(keys):
        by[k[:4]].append(ix)
    out["by_year"] = {y: dict(anchor=delta_stats(dA[ix], [keys[i] for i in ix], rng, K[ix], B[ix]),
                              free_delta=float(dF[ix].mean()))
                      for y, ix in sorted(by.items())}
    if breadth is not None:
        g = defaultdict(list)
        for ix, k in enumerate(keys):
            b = breadth.get(k)
            g["unknown" if b is None else ("up" if b > 0 else "down")].append(ix)
        out["by_breadth60"] = {nm: dict(anchor=delta_stats(dA[ix], [keys[i] for i in ix], rng, K[ix], B[ix]),
                                        free_delta=float(dF[ix].mean()))
                               for nm, ix in sorted(g.items())}
    if "jump" in per:
        J = np.array(per["jump"], bool)
        ix = np.where(~J)[0]
        out["no_jump"] = dict(excluded=int(J.sum()),
                              anchor=delta_stats(dA[ix], [keys[i] for i in ix], rng, K[ix], B[ix]),
                              free=delta_stats(dF[ix], [keys[i] for i in ix], rng))
    if "nominal_n" in per:
        out["eligibility"] = per["_elig"]
    # 비용 차감 (앵커 C*)
    dc = (np.array(per["anchor_vR"]) - np.array(per["anchor_cost"])) - (B - np.array(per["cost_b"]))
    out["anchor_cost"] = delta_stats(dc, keys, rng)
    out.update(regime_extras(keys, B, dA, np.array(per["anchor_tranches"]), rng))
    return out


def _week(k):
    y, w, _ = date.fromisoformat(k).isocalendar()
    return f"{y}-W{w:02d}"


def _quarter(k):
    return f"{k[:4]}Q{(int(k[5:7]) - 1) // 3 + 1}"


def regime_extras(keys, B, dA, T, rng):
    """진입일보다 굵은 묶음(주·월·분기) 클러스터 · 트랜치 수별 분해 · 월 단위 기준선↔Δ 회귀."""
    import numpy as np
    out = {"wider_clusters": {}}
    for nm, fn in (("week", _week), ("month", lambda k: k[:7]), ("quarter", _quarter)):
        ci, n = s0.ci_cluster(dA, [fn(k) for k in keys], rng)
        out["wider_clusters"][nm] = dict(ci=ci, clusters=n)
    out["by_tranches"] = {int(t): dict(share=float((T == t).mean()), delta=float(dA[T == t].mean()),
                                       contrib=float(dA[T == t].sum() / len(dA)), base_mean=float(B[T == t].mean()))
                          for t in (1, 2, 3) if (T == t).any()}
    gq = defaultdict(list)
    for i, k in enumerate(keys):
        gq[_quarter(k)].append(i)
    out["by_quarter"] = {q: dict(n=len(v), delta=float(dA[v].mean()), base_mean=float(B[v].mean()))
                         for q, v in sorted(gq.items())}
    gm = defaultdict(list)
    for i, k in enumerate(keys):
        gm[k[:7]].append(i)
    x = np.array([B[v].mean() for v in gm.values()])
    y = np.array([dA[v].mean() for v in gm.values()])
    w = np.array([len(v) for v in gm.values()], float)
    if len(x) > 3:
        b1, b0 = np.polyfit(x, y, 1, w=np.sqrt(w))
        hi = x > 0.5
        out["monthly"] = dict(months=int(len(x)), months_delta_pos=int((y > 0).sum()), slope=float(b1),
                              intercept=float(b0), breakeven_base=float(-b0 / b1) if b1 else None,
                              months_base_gt_0_5=int(hi.sum()),
                              delta_in_those=float(np.average(y[hi], weights=w[hi])) if hi.any() else None)
    return out


def eligibility(per, rng, budget, risk_pct):
    import numpy as np
    keys = per["key"]
    B = np.array(per["base_R"])
    dA = np.array(per["anchor_vR"]) - B
    dF = np.array(per["free_vR"]) - B
    elig = np.array([math.floor((2 / 3) * budget * risk_pct / n) >= 2 for n in per["nominal_n"]])
    ek = [k for k, e in zip(keys, elig) if e]
    return dict(budget=round(budget), risk_pct=risk_pct, share=float(elig.mean()),
                anchor_eligible=delta_stats(dA[elig], ek, rng),
                anchor_blended=delta_stats(np.where(elig, dA, 0.0), keys, rng),
                free_blended=delta_stats(np.where(elig, dF, 0.0), keys, rng))


def pooled(pers, rng):
    import numpy as np
    keys, dA, dF, K, cA, cB, B = [], [], [], [], [], [], []
    for p in pers:
        keys += p["key"]
        b = np.array(p["base_R"])
        B += list(b)
        dA += list(np.array(p["anchor_vR"]) - b)
        dF += list(np.array(p["free_vR"]) - b)
        K += list(p["anchor_killed"])
        cA += list(p["anchor_cost"])
        cB += list(p["cost_b"])
    dA, dF, B = np.array(dA), np.array(dF), np.array(B)
    dc = (dA + B - np.array(cA)) - (B - np.array(cB))
    out = dict(anchor=delta_stats(dA, keys, rng, K, B), free=delta_stats(dF, keys, rng),
               anchor_cost=delta_stats(dc, keys, rng))
    T = np.concatenate([np.array(p["anchor_tranches"]) for p in pers])
    out.update(regime_extras(keys, B, dA, T, rng))
    return out


def breadth60(series):
    """장세 꼬리표 — 그날 거래된 전 종목 60거래일 수익률의 중앙값(동일가중 폭 지표)."""
    import numpy as np
    by = defaultdict(list)
    for s in series.values():
        c = s["c"]
        for x in range(60, len(c)):
            by[s["dates"][x].isoformat()].append(c[x] / c[x - 60] - 1)
    return {d: float(np.median(v)) for d, v in by.items() if len(v) >= 200}


def jump_flags(series, entries):
    out = []
    for t, i0, _N in entries:
        s = series[t]
        c, o = s["c"], s["o"]
        hi = min(i0 + s0.MAXH - 1, len(c) - 1)
        f = False
        for x in range(i0 + 1, hi + 1):
            if abs(c[x] / c[x - 1] - 1) > JUMP or abs(o[x] / c[x - 1] - 1) > JUMP:
                f = True
                break
        out.append(f)
    return out


def compact(res):
    """보고서 표에 쓰는 요약 — 격자 전부의 핵심 칸."""
    rows = {}
    for mode in ("anchor", "free"):
        for name, r in res[mode].items():
            rows[f"{mode}:{name}"] = {k: r[k] for k in ("peak_theory", "mean", "win", "p_le_m1", "cvar5", "min",
                                                     "reach2", "reach3", "delta", "ci_iid", "ci_cluster",
                                                     "conv_base_win_to_loss", "killed", "delta_cost",
                                                     "delta_norm", "ci_cluster_norm")}
    return rows


# ═══════════════════════════════════ 실행 ═══════════════════════════════════

def run(c351_dump, out_dir):
    import numpy as np
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    leaf, leaf_sha = s0.load_leaf(LEAF)
    dump = s0.load_dump(c351_dump)
    bud, _bm = s0.budgets(dump)
    rk = float({r["strategy_id"]: r for r in dump["strategy_config"]["rows"]}["kojiro"]["params"]["risk_pct"])
    today_uni = {r[0] for r in dump["master"]["rows"] if (r[2] or 0) >= 500 and _is6(r[0])}
    out = dict(leaf_sha256=leaf_sha, c351_dump=os.path.basename(c351_dump),
               today_universe_n=len(today_uni), kojiro_budget=round(bud["kojiro"]), risk_pct=rk)

    # ── (0) 연속성: cycle351 덤프를 이 스크립트 경로로 → cycle351 재실행과 같은 855 를 내야 한다
    rng = np.random.default_rng(351)
    db_series = s0.build_series(dump)
    db_raw = proxy_raw(db_series)
    db_entries = dedup(db_raw)
    ref, _ = s0.proxy_entries(db_series)
    assert db_entries == ref, "proxy_raw+dedup != cycle351 proxy_entries (DB)"
    db_res, db_per = run_sample_a(db_series, db_entries, leaf, rng, "db_2025-10_2026-09",
                                  nominal_n=[e[2] for e in db_entries], jump_flag=jump_flags(db_series, db_entries))
    db_per["_elig"] = eligibility(db_per, rng, bud["kojiro"], rk)
    db_res["splits"] = splits(db_per, rng, breadth60(db_series))
    out["db"] = {k: v for k, v in db_res.items() if k not in ("anchor", "free")}
    out["db"]["grid"] = compact(db_res)
    print(f"[db] n={db_res['n']} dA={db_res['anchor'][C_STAR]['delta']:.4f} "
          f"ci={db_res['anchor'][C_STAR]['ci_cluster']} xc_bad={db_res['crosscheck_v2']['mismatched']} "
          f"{time.time()-t0:.0f}s", flush=True)

    # ── (1) 보관소
    daily, side, meta = load_archive()
    out["archive_meta"] = meta
    print(f"[archive] {meta} {time.time()-t0:.0f}s", flush=True)
    six = sorted(t for t in daily if _is6(t))
    series = series_from_daily(daily, six)
    del daily
    raw = proxy_raw(series)
    all_ded = dedup(raw)
    ref, _ = s0.proxy_entries(series)
    assert all_ded == ref, "proxy_raw+dedup != cycle351 proxy_entries (archive)"
    br = breadth60(series)
    out["archive_series_tickers"] = len(series)
    out["archive_proxy_raw"] = len(raw)
    print(f"[archive] series={len(series)} raw={len(raw)} dedup_all={len(all_ded)} {time.time()-t0:.0f}s", flush=True)

    def sig_side(t, i0):
        return side.get((t, series[t]["dates"][i0 - 1].isoformat()))

    uni_defs = {
        "today": lambda t, i0: t in today_uni,
        "asof": lambda t, i0: (sig_side(t, i0) or (0, 1.0))[0] >= MCAP_MIN_WON,
    }
    pers = {}
    for uname, keep in uni_defs.items():
        rng = np.random.default_rng(372)
        ents = dedup([e for e in raw if keep(e[0], e[1])])
        nom = []
        miss = 0
        for t, i0, N in ents:
            sd = sig_side(t, i0)
            if sd is None or sd[1] <= 0:
                miss += 1
                nom.append(N)
            else:
                nom.append(N / sd[1])
        r, per = run_sample_a(series, ents, leaf, rng, f"archive_{uname}", nominal_n=nom,
                              jump_flag=jump_flags(series, ents))
        per["_elig"] = eligibility(per, rng, bud["kojiro"], rk)
        r["splits"] = splits(per, rng, br)
        r["nominal_lookup_miss"] = miss
        pers[uname] = per
        out[f"archive_{uname}"] = {k: v for k, v in r.items() if k not in ("anchor", "free")}
        out[f"archive_{uname}"]["grid"] = compact(r)
        c = r["anchor"][C_STAR]
        print(f"[{uname}] n={r['n']} days={r['entry_days']} dA={c['delta']:.4f} ci={c['ci_cluster']} "
              f"killed={c['killed']:.3f} xc_bad={r['crosscheck_v2']['mismatched']} "
              f"({r['elapsed_s']}s) {time.time()-t0:.0f}s", flush=True)
    # 두 유니버스의 겹침
    kt = {(t, k) for t, k in zip(pers["today"]["ticker"], pers["today"]["key"])}
    ka = {(t, k) for t, k in zip(pers["asof"]["ticker"], pers["asof"]["key"])}
    out["universe_overlap"] = dict(today=len(kt), asof=len(ka), both=len(kt & ka),
                                   today_only=len(kt - ka), asof_only=len(ka - kt))

    # ── (2) 풀링 — 보관소(2020-10~2025-10) + DB(2026-01~09) 대리 진입. 날짜가 겹치지 않는다
    rng = np.random.default_rng(3720)
    out["pooled_today_db"] = pooled([pers["today"], db_per], rng)
    out["pooled_asof_db"] = pooled([pers["asof"], db_per], rng)
    out["elapsed_s"] = round(time.time() - t0, 1)
    with open(os.path.join(out_dir, "cycle372_result.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    for nm, p in (("today", pers["today"]), ("asof", pers["asof"]), ("db", db_per)):
        with gzip.open(os.path.join(out_dir, f"cycle372_per_{nm}.json.gz"), "wt", encoding="utf-8") as fh:
            json.dump({k: v for k, v in p.items() if not k.startswith("_")}, fh, default=str)
    print(json.dumps({k: out[k] for k in ("pooled_today_db", "pooled_asof_db", "universe_overlap", "elapsed_s")},
                     default=str))


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown mode {sys.argv[1]}")
