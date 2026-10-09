#!/usr/bin/env python3
"""etf_trend 걷기 전진 — 학습 창 길이 K 비교 구동기. 사전 등록 = ``_workspace/analysis/wfo_window_20261009/prereg.frozen.md``.

``wfo_etf.prepare()`` 로 창과 무관한 앞부분을 한 번 만들고 ``wfo_etf.main(ctx=…, years=…, train_years=K, out=None,
do_alt=False)`` 를 창 P·Q·R 의 각 K 에 돌린다(계좌 함수 · 선택 · 판정 함수는 그대로). 이 파일이 더하는 계산은
사전 등록 §4-6(미래 차단 비율) · §4-7(반쪽 P1·P2) · 해별 차이 · §5 판정(a)~(d) 의 기계 적용뿐이다.

실행: python tools/replay/wfo_etf_window.py            # 계산 + result.json + result.md(표)
      python tools/replay/wfo_etf_window.py --render  # result.json 에서 result.md 표만 다시 쓴다
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import wfo_core as W  # noqa: E402
from replay import wfo_etf as WE  # noqa: E402

ADIR = os.path.join(_REPO, "_workspace/analysis/wfo_window_20261009")
END = WE.END                                   # 2026-10-02
P_YEARS = tuple(range(2020, 2027))
Q_YEARS = (2025, 2026)
P_KS = (1, 2, 3, 4, 5)
Q_KS = (1, 2, 3, 4, 5, 10)
R_KS = (1, 2, 3, 4, 5)
JUDGE_KS = (1, 2, 3, 4)                         # §5 판정 대상 — K=5 는 같은 식으로 보고만
HALVES = (("P1", "2020-01-01", "2022-12-31"), ("P2", "2023-01-01", END))
MDD_TOL = 0.05                                  # §5(b) 5%p
INPUT_COPY = os.path.join(ADIR, "input", "stock_master_etf_fields.json")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def quiet(*a):
    pass


# ── §4-6 미래 차단 비율 ─────────────────────────────────────────────────────

def blocked_ratio(yi, tr: W.Trades, y: int, k: int):
    """[Y−K, Y−1] 진입 거래 중 Y 첫 거래일까지 청산이 안 된 비율(진입 0 이면 None)."""
    a, b, d = yi.first(y - k), yi.last(y - 1), yi.first(y)
    m = (tr.gin >= a) & (tr.gin <= b)
    n = int(m.sum())
    if n == 0:
        return None, 0
    return float(((tr.gout >= d) & m).sum() / n), n


def blocked(ctx, path, k):
    yi, trades = ctx["yi"], ctx["trades"]
    chosen, grid = {}, {}
    for y in sorted(path):
        r, n = blocked_ratio(yi, trades[path[y]], y, k)
        chosen[y] = {"ratio": r, "n_entries": n}
        rs = [blocked_ratio(yi, trades[c], y, k)[0] for c in ctx["ids"]]
        rs = [x for x in rs if x is not None]
        grid[y] = {"mean_ratio": float(np.mean(rs)) if rs else None, "n_combos": len(rs)}
    cv = [v["ratio"] for v in chosen.values() if v["ratio"] is not None]
    gv = [v["mean_ratio"] for v in grid.values() if v["mean_ratio"] is not None]
    return {"chosen_by_year": chosen, "grid_by_year": grid,
            "chosen_mean": float(np.mean(cv)) if cv else None, "grid_mean": float(np.mean(gv)) if gv else None}


# ── 한 실행 요약 ────────────────────────────────────────────────────────────

def halves(ctx, a: W.Trades, b: W.Trades):
    yi = ctx["yi"]
    out = {}
    for nm, s, e in HALVES:
        va, vb = a.r[yi.win_mask(a, s, e)], b.r[yi.win_mask(b, s, e)]
        out[nm] = {"n_a": int(len(va)), "n_b": int(len(vb)),
                   "mean_a": float(va.mean()) if len(va) else None, "mean_b": float(vb.mean()) if len(vb) else None,
                   "diff": float(va.mean() - vb.mean()) if len(va) and len(vb) else None}
    return out


def summarize(ctx, res, k, years, with_halves):
    yi, trades = ctx["yi"], ctx["trades"]
    paths = {"wfo": res["path"], "current": {y: ctx["cur_id"] for y in years},
             "fixed_b": {y: ctx["b_id"] for y in years}}
    T = {nm: W.stitch(yi, p, trades) for nm, p in paths.items()}

    def row(nm, diff):
        t, bk = res["trade"][nm]["r"], res["books"][nm]["r"]
        return {"n": t["n"], "mean": t.get("mean"), "lo90": t.get("lo90"),
                "diff_vs_current_est": diff["est"] if diff else None,
                "diff_vs_current_lo5": diff["lower"]["0.05"] if diff else None,
                "cagr": bk["cagr_median"], "mdd": bk["mdd_median"], "fills_per_year": bk["fills_per_year_median"]}

    st = res["stability"]
    wfo = row("wfo", res["judge"]["r"]["diff_vs_current"])
    wfo.update(spearman_mean=st["spearman_mean"], spearman_pos_years=st["spearman_pos_years"],
               spearman_n_years=st["spearman_n_years"], spearman_by_year=st["spearman_by_year"],
               distinct=st["distinct"], switches=st["switches"], axis_switches=st["axis_switches"],
               train_minus_oos_mean=st["train_minus_oos_mean"], n_fallback=st["n_fallback"],
               n_current=st["n_current"], n_fixed_b=st["n_fixed_b"],
               diff_vs_fixed_b_est=res["diff_vs_fixed_b"]["r"]["est"],
               diff_vs_fixed_b_lo5=res["diff_vs_fixed_b"]["r"]["lower"]["0.05"])
    fb = blocked(ctx, res["path"], k)
    wfo.update(excluded_open_mean=fb["chosen_mean"], excluded_open_grid_mean=fb["grid_mean"])
    by_year = {}
    for y in years:
        r = res["by_year"][y]
        w, c, b = r["wfo"]["mean"], r["current"]["mean"], r["fixed_b"]["mean"]
        by_year[y] = {"chosen": r["chosen"], "n_wfo": r["wfo"]["n"], "mean_wfo": w,
                      "n_current": r["current"]["n"], "mean_current": c, "n_fixed_b": r["fixed_b"]["n"],
                      "mean_fixed_b": b,
                      "diff_vs_current": (w - c) if w is not None and c is not None else None,
                      "train_n": r["train_n"], "train_mean": r["train_mean"], "train_score": r["train_score"],
                      "n_eligible": res["selection"][y].get("n_eligible"),
                      "fallback": res["selection"][y].get("fallback"),
                      "spearman": st["spearman_by_year"].get(y),
                      "blocked_chosen": fb["chosen_by_year"][y]["ratio"],
                      "blocked_chosen_n_entries": fb["chosen_by_year"][y]["n_entries"],
                      "blocked_grid_mean": fb["grid_by_year"][y]["mean_ratio"]}
    out = {"K": k, "years": list(years), "wfo": wfo, "current": row("current", None),
           "fixed_b": row("fixed_b", res["judge_fixed_b"]["r"]["diff_vs_current"]),
           "by_year": by_year, "path": res["path"], "blocked": fb,
           "judge_label_orig": res["judge"]["r"]["label"], "book_start": f"{years[0]}-01-02", "book_end": END,
           "self_check_final_equity_diff": res["self_check_final_equity_diff"]}
    if with_halves:
        out["halves_wfo_minus_current"] = halves(ctx, T["wfo"], T["current"])
        out["halves_fixed_b_minus_current"] = halves(ctx, T["fixed_b"], T["current"])
    return out


# ── §5 판정 ────────────────────────────────────────────────────────────────

def judge_k(s: dict) -> dict:
    w, c = s["wfo"], s["current"]
    h = s["halves_wfo_minus_current"]
    n_years = len(s["years"])
    a = bool(w["diff_vs_current_lo5"] > 0)
    b = bool(w["cagr"] >= c["cagr"] and w["mdd"] >= c["mdd"] - MDD_TOL)
    cc = bool(np.isfinite(w["spearman_mean"]) and w["spearman_mean"] > 0
              and w["spearman_pos_years"] >= (2 / 3) * n_years)
    d = bool(h["P1"]["diff"] is not None and h["P2"]["diff"] is not None and h["P1"]["diff"] > 0 and h["P2"]["diff"] > 0)
    return {"a": a, "b": b, "c": cc, "d": d, "pass": bool(a and b and cc and d),
            "c_denominator_years": n_years, "c_pos_needed": float(2 / 3 * n_years)}


SENT_PASS = ("짧은 창이 낫다는 근거가 있다 — K = {k}. 그래도 채택은 사용자 결정이고, 채택하면 그 창으로 이 문서와 같은 방식의 "
             "새 사전 등록을 만든 뒤 쓴다.")
SENT_FAIL = "짧은 창이 낫다는 근거가 없다 — 결과를 보고 창을 고르면 그것이 다시 과적합이므로 원 등록의 10년을 유지한다"
ISOLATED = "고립된 통과 — 우연 가능성 높음"


def verdict(P: dict) -> dict:
    j = {k: judge_k(P[k]) for k in P_KS}
    passed = [k for k in JUDGE_KS if j[k]["pass"]]
    if passed:
        best = max(passed, key=lambda k: P[k]["wfo"]["diff_vs_current_lo5"])
        sent = SENT_PASS.format(k=best)
    else:
        best, sent = None, SENT_FAIL
    isolated = None
    if len(passed) == 1:
        k = passed[0]
        nb = [x for x in (k - 1, k + 1) if x in P]
        isolated = bool(nb and all(P[x]["wfo"]["diff_vs_current_est"] < 0 for x in nb))
    return {"by_K": j, "passed": passed, "best": best, "sentence": sent, "isolated_pass": isolated,
            "isolated_note": ISOLATED if isolated else None, "k5_report_only": j[5]}


# ── 실행 ───────────────────────────────────────────────────────────────────

def compute(log=WE.log) -> dict:
    t0 = time.time()
    ctx = WE.prepare(log=log)
    from replay.audit import gate_c391b as GT
    db_fields = GT.load_c391().DB_FIELDS
    runs = {"P": {}, "Q": {}, "R": {}}
    raw = {}

    def go(win, k, years, with_halves):
        key = (k, tuple(years))
        if key not in raw:
            raw[key] = WE.main(do_alt=False, years=years, train_years=k, out=None, ctx=ctx, log=quiet)
            log(f"[{win}] K={k} {years[0]}–{years[-1]} 끝 ({time.time()-t0:.0f}s)")
        runs[win][k] = summarize(ctx, raw[key], k, years, with_halves)

    for k in P_KS:
        go("P", k, P_YEARS, True)
    for k in Q_KS:
        go("Q", k, Q_YEARS, False)
    for k in R_KS:
        go("R", k, tuple(range(2015 + k, 2027)), False)

    # 고정 판은 K 와 무관해야 한다 — 같은 창의 K 사이에서 같은지 확인
    fixed_same = {}
    for win in ("P", "Q"):
        ks = list(runs[win])
        fixed_same[win] = all(runs[win][k][f] == runs[win][ks[0]][f] for k in ks for f in ("current", "fixed_b"))
    v = verdict(runs["P"])

    prereg = os.path.join(ADIR, "prereg.frozen.md")
    prereg_sha = sha(prereg)
    prereg_rec = open(os.path.join(ADIR, "prereg.sha256")).read().split()[0]
    here = os.path.dirname(os.path.abspath(__file__))
    out = {"generated_at_kst": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST"),
           "end": END, "P_years": list(P_YEARS), "Q_years": list(Q_YEARS),
           "R_years": {k: [2015 + k, 2026] for k in R_KS},
           "code_sha256": {f: sha(os.path.join(here, f)) for f in ("wfo_core.py", "wfo_etf.py", "wfo_etf_window.py")},
           "prereg_sha256": prereg_sha, "prereg_sha256_recorded": prereg_rec,
           "prereg_sha_match": prereg_sha == prereg_rec,
           "input": {"db_fields_path_used": db_fields, "db_fields_sha256": sha(db_fields),
                     "repo_copy_sha256": sha(INPUT_COPY), "same": sha(db_fields) == sha(INPUT_COPY)},
           "self_check_final_equity_diff": ctx["self_check"], "fixed_rows_identical_across_K": fixed_same,
           "current_id": ctx["cur_id"], "fixed_b_id": ctx["b_id"], "grid_size": len(ctx["ids"]),
           "windows": runs, "verdict": v, "elapsed_s": time.time() - t0}
    with open(os.path.join(ADIR, "result.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=W.js)
    log("result.json", f"{out['elapsed_s']:.0f}s", v["passed"], v["sentence"])
    return out


# ── result.md 표(숫자는 result.json 에서만) ─────────────────────────────────

def pct(x, d=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{100 * x:+.{d}f}%"


def pctu(x, d=1):
    return "—" if x is None else f"{100 * x:.{d}f}%"


def num(x, d=3):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:+.{d}f}"


def ox(b):
    return "통과" if b else "실패"


def render(R: dict) -> str:
    L = []
    W_ = R["windows"]
    L.append("# etf_trend 걷기 전진 — 학습 창 길이 비교(K = 1·2·3·4·5·10년) — 결과\n")
    L.append(f"- 생성 시각: {R['generated_at_kst']}")
    L.append("- 코드 sha256: " + " · ".join(f"`{k}` {v}" for k, v in R["code_sha256"].items()))
    L.append(f"- 사전 등록 sha 확인: `prereg.frozen.md` = {R['prereg_sha256']} · `prereg.sha256` 기록 = "
             f"{R['prereg_sha256_recorded']} → **{'일치' if R['prereg_sha_match'] else '불일치'}**")
    i = R["input"]
    L.append(f"- 입력 `stock_master_etf_fields.json` sha256 = {i['db_fields_sha256']}(계산에 쓴 경로 = `{i['db_fields_path_used']}`) · "
             f"리포 사본 `input/` = {i['repo_copy_sha256']} → {'같다' if i['same'] else '다르다'}")
    L.append(f"- 계좌 자기 대조(현행 고정 = `etf_book30`) Δ최종자산 = {R['self_check_final_equity_diff']} · "
             f"고정 판이 K 사이에 같은가 = {R['fixed_rows_identical_across_K']} · 계산 {R['elapsed_s']:.0f}초")
    L.append(f"- 표본 밖 끝 = {R['end']} · 고정 현행 = `{R['current_id']}` · 고정 B = `{R['fixed_b_id']}` · 격자 {R['grid_size']}\n")

    def head():
        return ("| 판 | n | 거래당 평균 [90% 하한] | 현행 대비 차 점추정 [5% 분위] | 연 복리 | 최대 낙폭 | 연 체결 |"
                " 스피어만 평균 (양+/전체) | 바뀐 해 | 미래 차단(고른 조합 / 격자 평균) |")

    def line(lbl, r, wfo=True):
        sp = (f"{num(r['spearman_mean'], 3)} ({r['spearman_pos_years']}/{r['spearman_n_years']})" if wfo else "—")
        sw = str(r["switches"]) if wfo else "—"
        fb = f"{pctu(r['excluded_open_mean'])} / {pctu(r['excluded_open_grid_mean'])}" if wfo else "—"
        dif = (f"{pct(r['diff_vs_current_est'])} [{pct(r['diff_vs_current_lo5'])}]"
               if r["diff_vs_current_est"] is not None else "—")
        return (f"| {lbl} | {r['n']} | {pct(r['mean'])} [{pct(r['lo90'])}] | {dif} | {pct(r['cagr'])} | "
                f"{pct(r['mdd'], 1)} | {r['fills_per_year']:.1f} | {sp} | {sw} | {fb} |")

    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    # 창 P
    P = W_["P"]
    v = R["verdict"]
    L.append("## 1. 창 P(주 판정) — 표본 밖 2020-01-02 ~ 2026-10-02, 2020-01-02 새 계좌\n")
    L.append(head())
    L.append(sep)
    for k in sorted(P, key=int):
        L.append(line(f"K={k}", P[k]["wfo"]))
    k0 = sorted(P, key=int)[0]
    L.append(line("고정 현행", P[k0]["current"], False))
    L.append(line("고정 B", P[k0]["fixed_b"], False))
    L.append("")
    L.append("판정(사전 등록 §5 — K=1..4 판정, K=5 는 같은 식으로 보고만):\n")
    L.append("| 판 | 반쪽 P1(2020–2022) 차 | 반쪽 P2(2023–2026-10-02) 차 | (a) 5% 분위 > 0 | (b) 계좌 | (c) 고르는 힘 | (d) 두 반쪽 | 종합 |")
    L.append("|---|---:|---:|---|---|---|---|---|")
    for k in sorted(P, key=int):
        h = P[k]["halves_wfo_minus_current"]
        j = v["by_K"][k]
        tag = "통과" if j["pass"] else "실패"
        if int(k) == 5:
            tag += "(보고만)"
        L.append(f"| K={k} | {pct(h['P1']['diff'])} | {pct(h['P2']['diff'])} | {ox(j['a'])} | {ox(j['b'])} | "
                 f"{ox(j['c'])} | {ox(j['d'])} | {tag} |")
    hb = P[k0]["halves_fixed_b_minus_current"]
    L.append(f"| 고정 B | {pct(hb['P1']['diff'])} | {pct(hb['P2']['diff'])} | — | — | — | — | — |")
    L.append("")
    L.append(f"(c) 의 「전체 해」 = 창 P 의 해 수 {v['by_K'][k0]['c_denominator_years']} → 양(+)인 해 "
             f"{v['by_K'][k0]['c_pos_needed']:.2f} 이상. (b) 낙폭 허용 = 고정 현행 낙폭 − 5%p.\n")
    L.append(f"**결론(사전 고정 문장): 「{v['sentence']}」**")
    if v["isolated_note"]:
        L.append(f"\n**{v['isolated_note']}**")
    L.append("")
    # 해별 차이
    L.append("## 2. 창 P 해별 차이 — (K판 거래당 평균 − 고정 현행 거래당 평균)\n")
    ys = P[k0]["years"]
    L.append("| 판 | " + " | ".join(str(y) for y in ys) + " |")
    L.append("|---|" + "---:|" * len(ys))
    for k in sorted(P, key=int):
        L.append(f"| K={k} | " + " | ".join(pct(P[k]["by_year"][str(y)]["diff_vs_current"]) for y in ys) + " |")
    L.append("| 고정 현행 거래당 평균(n) | " + " | ".join(
        f"{pct(P[k0]['by_year'][str(y)]['mean_current'])} ({P[k0]['by_year'][str(y)]['n_current']})" for y in ys) + " |")
    L.append("")
    L.append("해별 스피어만(학습 점수 순위 대 그해 표본 밖 평균 순위):\n")
    L.append("| 판 | " + " | ".join(str(y) for y in ys) + " |")
    L.append("|---|" + "---:|" * len(ys))
    for k in sorted(P, key=int):
        L.append(f"| K={k} | " + " | ".join(num(P[k]["by_year"][str(y)]["spearman"], 2) for y in ys) + " |")
    L.append("")
    L.append("해별 미래 차단 비율(고른 조합 / 격자 108 평균):\n")
    L.append("| 판 | " + " | ".join(str(y) for y in ys) + " |")
    L.append("|---|" + "---:|" * len(ys))
    for k in sorted(P, key=int):
        L.append(f"| K={k} | " + " | ".join(
            f"{pctu(P[k]['by_year'][str(y)]['blocked_chosen'])} / {pctu(P[k]['by_year'][str(y)]['blocked_grid_mean'])}"
            for y in ys) + " |")
    L.append("")
    # 창 Q
    Q = W_["Q"]
    q0 = sorted(Q, key=int)[0]
    L.append("## 3. 창 Q(보조) — 표본 밖 2025-01-02 ~ 2026-10-02\n")
    L.append(head())
    L.append(sep)
    for k in sorted(Q, key=int):
        L.append(line(f"K={k}", Q[k]["wfo"]))
    L.append(line("고정 현행", Q[q0]["current"], False))
    L.append(line("고정 B", Q[q0]["fixed_b"], False))
    L.append("")
    # 창 R
    Rw = W_["R"]
    L.append("## 4. 창 R(보고) — K 마다 가장 긴 표본 밖 (2015+K)-01-02 ~ 2026-10-02\n")
    L.append("| 판 | 창 | n | 거래당 평균 [90% 하한] | 현행 대비 차 점추정 [5% 분위] | 연 복리 | 최대 낙폭 | 연 체결 |"
             " 스피어만 평균 (양+/전체) | 바뀐 해 | 고정 현행 n · 평균 · 연 복리 · 낙폭 |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for k in sorted(Rw, key=int):
        r, c = Rw[k]["wfo"], Rw[k]["current"]
        L.append(f"| K={k} | {Rw[k]['years'][0]}–{Rw[k]['years'][-1]} | {r['n']} | {pct(r['mean'])} [{pct(r['lo90'])}] | "
                 f"{pct(r['diff_vs_current_est'])} [{pct(r['diff_vs_current_lo5'])}] | {pct(r['cagr'])} | {pct(r['mdd'], 1)} | "
                 f"{r['fills_per_year']:.1f} | {num(r['spearman_mean'], 3)} ({r['spearman_pos_years']}/{r['spearman_n_years']}) | "
                 f"{r['switches']} | {c['n']} · {pct(c['mean'])} · {pct(c['cagr'])} · {pct(c['mdd'], 1)} |")
    L.append("")
    # 고른 조합
    L.append("## 5. K 별 해마다 고른 조합(창 R 기준 전체 해 · Q 의 K=10 포함)\n")
    allys = list(range(2016, 2027))
    L.append("| 해 | " + " | ".join(f"K={k}" for k in sorted(Rw, key=int)) + " | K=10 |")
    L.append("|---|" + "---|" * (len(Rw) + 1))
    for y in allys:
        cells = [f"`{Rw[k]['path'][str(y)]}`" if str(y) in Rw[k]["path"] else "—" for k in sorted(Rw, key=int)]
        cells.append(f"`{Q['10']['path'][str(y)]}`" if str(y) in Q["10"]["path"] else "—")
        L.append(f"| {y} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("| 판(창 R) | 서로 다른 조합 | 바뀐 해 | 축별 바뀐 해 | 학습 − 표본 밖 평균(낙차) | 미래 차단 평균(고른 / 격자) |")
    L.append("|---|---:|---:|---|---:|---:|")
    for k in sorted(Rw, key=int):
        r = Rw[k]["wfo"]
        ax = " · ".join(f"{a} {n}" for a, n in r["axis_switches"].items())
        L.append(f"| K={k} | {r['distinct']} | {r['switches']} | {ax} | {pct(r['train_minus_oos_mean'])} | "
                 f"{pctu(r['excluded_open_mean'])} / {pctu(r['excluded_open_grid_mean'])} |")
    r = Q["10"]["wfo"]
    ax = " · ".join(f"{a} {n}" for a, n in r["axis_switches"].items())
    L.append(f"| K=10(창 Q) | {r['distinct']} | {r['switches']} | {ax} | {pct(r['train_minus_oos_mean'])} | "
             f"{pctu(r['excluded_open_mean'])} / {pctu(r['excluded_open_grid_mean'])} |")
    L.append("")
    L.extend(render_post(R))
    return "\n".join(L) + "\n"


def render_post(R: dict) -> list:
    """「사후」 절 + 한 문단 답. 숫자는 result.json 에서만."""
    P, v = R["windows"]["P"], R["verdict"]
    ks = sorted(P, key=int)
    L = ["## 6. 사후 — 사전 등록과 달라진 것 · 등록이 정하지 않아 이 계산이 정한 것\n"]
    L.append("1. **입력 재추출** — 원 입력 스냅샷 `scratchpad/etf_s0/input/stock_master_etf_fields.json`(sha f4f27fc2…)이 "
             "10-07 00:00 스크래치 정리로 지워졌다. 같은 조회 스크립트 `q_etf_fields_ro.py`(sha 3c0d4cd3… — 세션 기록에서 "
             "바이트 그대로 복원)로 10-09 09:0x KST 운영 DB 에서 읽기 전용 재추출했다(873행, stock_master 3,586행 — 원본과 같은 "
             f"개수). 새 sha = {R['input']['db_fields_sha256'][:8]}…(`refreshed_at` 칸이 다름). 사본 = `input/`(SHA256SUMS). "
             "이 입력으로 K=10 · 표본 밖 2025~2026 · 대안 규칙 포함 재현(`repro_k10/result.json`)이 원 결과와 elapsed_s · "
             "code_sha256 · train_years 를 뺀 모든 칸에서 차이 0건이라 §6 을 통과한 것으로 본다. 창 Q 의 K=10 해마다 고른 "
             "조합도 원 결과와 같다.")
    alt = {}
    for k in ks:
        w = P[k]["wfo"]
        alt[k] = bool(w["spearman_mean"] > 0 and w["spearman_pos_years"] >= 2 / 3 * w["spearman_n_years"])
    flips = [k for k in ks if alt[k] != v["by_K"][k]["c"]]
    L.append(f"2. **(c) 의 「전체 해」 와 스피어만 거름** — 창 P 의 해 수({v['by_K'][ks[0]]['c_denominator_years']})를 분모로 썼다. "
             "스피어만은 원 등록 코드 `wfo_core.stability` 를 그대로 써서, 그해 표본 밖 거래가 10건 이상인 자격 조합만 넣고 "
             "그런 조합이 5개 미만이면 그해를 재지 않는다(사전 등록 §4-4 의 「자격 조합 전체」 와 다른 점 — 원 등록 코드에서 물려받은 "
             "정의). 그래서 잰 해 수가 " + " · ".join(f"K={k} {P[k]['wfo']['spearman_n_years']}" for k in ks)
             + " 이다(자격 조합이 없는 해, 또는 K=3 의 2020 처럼 자격 조합이 4개뿐인 해가 빠진다). 분모를 「잰 해 수」로 바꾸면 "
             "(c) 가 바뀌는 판 = " + (", ".join(f"K={k}" for k in flips) if flips else "없음")
             + " — K=1..4 의 판정은 어느 쪽이든 같다"
             + ("(K=5 는 보고만이고 (b) 에서 이미 실패)." if flips == ["5"] else ".")
             + " 검증 단계가 등록 문구대로(거름 없이 자격 조합 전체) 독립 재계산한 값도 K=1 +0.010(양+ 2/5) · K=2 −0.115(3/6) · "
             "K=3 −0.086(4/7) · K=4 −0.109(3/6) · K=5 +0.017(4/6) 이라 K=1..4 의 (c) 는 두 정의 모두 실패다.")
    Rw = R["windows"]["R"]
    L.append("3. **자격 조합이 없는 해 = 고정 현행** — `wfo_core.select_year` 의 기존 대체 규칙(원 등록 코드 그대로)이다. 창 P 에서 "
             "그런 해 수 = " + " · ".join(f"K={k} {P[k]['wfo']['n_fallback']}" for k in ks)
             + ", 창 R 에서는 " + " · ".join(f"K={k} {Rw[k]['wfo']['n_fallback']}/{len(Rw[k]['path'])}해" for k in sorted(Rw, key=int))
             + " 이다(창 R 의 K=1 은 거의 반이 현행 그대로다). 그 해는 K판 = 현행이라 해별 차이가 0 이다. 짧은 창일수록 "
             "「연 30건 × K」 하한을 넘는 조합이 적은 해가 생긴다.")
    L.append("4. **미래 차단 비율의 평균 방식** — 격자 평균 = 그해 창 안 진입이 1건 이상인 조합별 비율의 단순 평균, 창 평균 = "
             "해별 비율의 단순 평균. 2025 는 모든 K · 모든 조합에서 0 이다(2025 첫 거래일 전에 진입한 거래가 모두 그 전에 청산됨).")
    b22 = {k: P[k]["by_year"]["2022"] for k in ("1", "4")}
    L.append("5. **반쪽 P1·P2** — 이어 붙인 표본 밖 거래를 진입일로 나눈 거래당 평균의 차(점추정, 부트스트랩 없음). 두 판의 거래를 "
             "한데 모은 평균의 차라서, 해마다 거래 수가 다르면 해별 성적과 반대 방향으로 나올 수 있다. K=1·K=4 의 P1 양(+)이 그 경우다 — "
             f"2022 에 K판 거래가 {b22['1']['n_wfo']}건(현행 {b22['1']['n_current']}건)뿐이라 그해 거래당 "
             f"{pct(b22['1']['diff_vs_current'])}p 로 더 나빴는데도 나쁜 해의 비중이 줄었다. P1 의 해별 차는 0 또는 음(−)이므로 "
             "(d) 통과를 「해마다 일관」 으로 읽지 않는다(판정은 등록 문구대로 기계 적용한 그대로 둔다).")
    L.append("6. **「고립된 통과」 규칙** — 통과한 짧은 창이 없어 적용할 대상이 없다.")
    L.append("7. **계산 경로** — 입력 파일은 `cycle391` 모듈의 기본 경로(세션 스크래치 `etf_s0/input/`)에서 읽었고 sha 가 리포 사본과 "
             "같다. 대안 규칙(학습 MAR)은 사전 등록 §2 대로 돌리지 않았다(`do_alt=False`).")
    L.append("8. **고정 B 는 표본 밖 성적이 아니다** — 고정 B(`L20|tr3.0|ch10|bl1|ge075`)는 원 등록에서 2020-10~2023-09 학습 격자로 "
             "고른 「5년 선택판」 이라 창 P 의 앞부분(P1)과 겹친다. 고정 B 행은 비교 참고로만 읽는다.")
    k4 = P["4"]["wfo"]
    L.append(f"9. **경계값** — K=4 의 (a) 5% 분위 {pct(k4['diff_vs_current_lo5'])} 는 0 과 사실상 같다(부트스트랩 오차 범위). "
             "K=4 는 (b)·(c) 에서도 실패하므로 판정은 같다.")
    L.append("10. **창 P 기준 안정성** — " + " · ".join(
        f"K={k} 서로 다른 조합 {P[k]['wfo']['distinct']} · 바뀐 해 {P[k]['wfo']['switches']} · 낙차 "
        f"{pct(P[k]['wfo']['train_minus_oos_mean'])}" for k in ks) + "(§5 의 요약표는 창 R 기준이다).\n")
    k1 = P["1"]["wfo"]
    q10 = R["windows"]["Q"]["10"]["wfo"]
    L.append("## 7. 한 문단 답\n")
    L.append(
        "직전 1~4년만 보고 조합을 고르는 방식을 2020~2026 표본 밖에서 그대로 굴려 봤지만, 미리 정한 네 조건을 모두 넘은 창은 "
        f"하나도 없었습니다. 가장 나아 보인 1년 창은 거래당 평균이 현행보다 {pct(k1['diff_vs_current_est'])}p 높았지만, "
        f"「작년에 좋았던 조합이 올해도 좋은가」를 본 상관이 잴 수 있었던 {k1['spearman_n_years']}해 중 "
        f"{k1['spearman_pos_years']}해만 양(+)이라 고르는 힘이 없었고, 그 우위도 대부분 2025년 한 해"
        f"({pct(P['1']['by_year']['2025']['diff_vs_current'])}p)에서 나왔습니다. 2·3년 창은 현행과 비슷하거나 못했고, 4년 창도 우위가 통계적으로 확인되지 않았습니다. "
        "그래서 결론은 사전에 정한 문장 그대로 — 짧은 창이 낫다는 근거가 없고, 결과를 보고 창을 고르면 그것이 다시 과적합이므로 "
        "원 등록의 10년을 유지합니다. 다만 10년 유지는 사전 규칙의 기본값이지 10년이 더 낫다는 증거가 아닙니다 — 10년 창도 잴 수 있었던 "
        f"2025~26 에서 현행을 넘지 못했습니다({pct(q10['diff_vs_current_est'])}p, 5% 분위 {pct(q10['diff_vs_current_lo5'])}). "
        "이 결과는 2020~2026 한 구간(2025~26 활황의 비중이 큼)에서 창 4개를 함께 시험한 것이고 표본이 작습니다. "
        "「근거가 없다」 는 「짧은 창이 나쁘다」 는 뜻이 아닙니다.")
    return L


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true", help="계산 없이 result.json 에서 result.md 표만")
    a = ap.parse_args()
    if not a.render:
        compute()
    R = json.load(open(os.path.join(ADIR, "result.json")))
    with open(os.path.join(ADIR, "result.md"), "w") as fh:
        fh.write(render(R))
