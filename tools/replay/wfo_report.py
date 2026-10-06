#!/usr/bin/env python3
"""주기적 재조정 결과 → ``_workspace/analysis/wfo_20261006/result.md``.

전략별 ``<전략>/result.json`` 을 읽어 표를 만든다. 맨 위 = 진행 상황(시각) + ``head.md``(사람이 쓴 종합 · 한 문단 답).
"""
from __future__ import annotations

import json
import os
import time

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "_workspace/analysis/wfo_20261006"))
ORDER = (("vcp", "vcp_breakout"), ("bfb", "bull_flag_breakout"), ("kojiro", "kojiro"),
         ("donchian", "donchian_swing(개조)"), ("vb", "volatility_breakout"), ("ou", "평균회귀 OU z"),
         ("etf_trend", "etf_trend"))
NAMES = {"wfo": "재조정판", "current": "고정 현행", "fixed_b": "고정 B 판", "alt_mar": "(보고) 대안 MAR 규칙"}


def pct(x, d=2):
    return "—" if x is None or x != x else f"{100 * x:+.{d}f}%"


def pp(x, d=2):
    return "—" if x is None or x != x else f"{100 * x:+.{d}f}%p"


def section(key, title, R, ver="r", vlabel=""):
    L = []
    j = R["judge"][ver]
    L.append(f"### {title}{vlabel}\n")
    L.append(f"**판정 = {j['label']}** · 「조정을 안 해서 실패했나」 → **{j['answer']}**\n")
    L.append("| 판 | 거래 n | 거래당 평균 [90% 하한] | 계좌 연 복리 중앙 [최소, 최대] | 계좌 낙폭 중앙 | 연 체결 |")
    L.append("|---|---|---|---|---|---|")
    for k in ("wfo", "current", "fixed_b", "alt_mar"):
        if k not in R["trade"]:
            continue
        t, b = R["trade"][k][ver], R["books"][k][ver]
        L.append(f"| {NAMES[k]} | {t.get('n')} | {pct(t.get('mean'))} [{pct(t.get('lo90'))}] | "
                 f"{pct(b['cagr_median'])} [{pct(b['cagr_min'])}, {pct(b['cagr_max'])}] | {pct(b['mdd_median'], 1)} | "
                 f"{b.get('fills_per_year_median', float('nan')):.0f} |")
    ix = R["index"]["all"]
    L.append(f"| 지수 보유 | — | — | {pct(ix['cagr'])} | {pct(ix['mdd'], 1)} | — |\n")
    d = j["diff_vs_current"]
    L.append(f"- (1) 거래당 {'통과' if j['c1'] else '실패'} · (2) 계좌 {'통과' if j['c2'] else '실패'} · "
             f"(3) 현행 대비 차 {pp(d['est'])} [월 블록 5% 분위 {pp(d['lower']['0.05'])}] → "
             f"{'통과' if j['c3'] else '실패'}")
    if "diff_vs_fixed_b" in R:
        db = R["diff_vs_fixed_b"][ver]
        L.append(f"- (보고) 재조정판 − 고정 B 판 = {pp(db['est'])} [5% 분위 {pp(db['lower']['0.05'])}] · "
                 f"고정 B 판 자체 판정 = {R['judge_fixed_b'][ver]['label']}")
    if "judge_alt" in R:
        ja = R["judge_alt"][ver]
        L.append(f"- (보고) 대안 MAR 규칙판 판정 = {ja['label']} · 현행 대비 {pp(ja['diff_vs_current']['est'])} "
                 f"[{pp(ja['diff_vs_current']['lower']['0.05'])}]")
    L.append("")
    # 시대
    L.append("| 시대 | 재조정판 거래당 [하한] (n) | 고정 현행 | 고정 B 판 | 재조정 계좌 연·낙폭 | 현행 계좌 연·낙폭 | 지수 보유 연·낙폭 |")
    L.append("|---|---|---|---|---|---|---|")
    for era in R["eras_trade"]["wfo"][ver]:
        w = R["eras_trade"]["wfo"][ver][era]
        c = R["eras_trade"]["current"][ver][era]
        fb = R["eras_trade"].get("fixed_b", {}).get(ver, {}).get(era, {})
        bw = R["books"]["wfo"][ver]["eras"].get(era, {})
        bc = R["books"]["current"][ver]["eras"].get(era, {})
        ie = (R["index"]["eras"] or {}).get(era) or {}
        L.append(f"| {era} | {pct(w.get('mean'))} [{pct(w.get('lo90'))}] ({w.get('n')}) | {pct(c.get('mean'))} ({c.get('n')}) | "
                 f"{pct(fb.get('mean'))} | {pct(bw.get('cagr_median'))} · {pct(bw.get('mdd_median'), 1)} | "
                 f"{pct(bc.get('cagr_median'))} · {pct(bc.get('mdd_median'), 1)} | "
                 f"{pct(ie.get('cagr'))} · {pct(ie.get('mdd'), 1)} |")
    L.append("")
    s = R["stability"]
    L.append(f"**안정성** — {s['years']}년 중 서로 다른 조합 {s['distinct']}개 · 전년과 바뀐 해 {s['switches']} · "
             f"현행을 고른 해 {s['n_current']} · 고정 B 판을 고른 해 {s['n_fixed_b']} · 자격 없어 현행 {s['n_fallback']}. "
             f"축별 바뀐 해 = " + ", ".join(f"{k} {v}" for k, v in s["axis_switches"].items()) + ".  ")
    L.append(f"학습 순위 → 그해 순위 스피어만 평균 **{s['spearman_mean']:+.3f}**(양수 {s['spearman_pos_years']}/"
             f"{s['spearman_n_years']}년) · 고른 조합의 학습 평균 − 그해 평균 = **{pp(s['train_minus_oos_mean'])}**\n")
    L.append("<details><summary>해마다 고른 조합</summary>\n")
    L.append("| 해 | 고른 조합 | 학습 n · 평균 · 점수 | 그해 재조정 n · 평균 | 그해 현행 평균 | 그해 고정 B 평균 |")
    L.append("|---|---|---|---|---|---|")
    for y, row in R["by_year"].items():
        L.append(f"| {y} | `{row['chosen']}` | {row.get('train_n')} · {pct(row.get('train_mean'))} · "
                 f"{pct(row.get('train_score'))} | {row['wfo']['n']} · {pct(row['wfo']['mean'])} | "
                 f"{pct(row['current']['mean'])} | {pct((row.get('fixed_b') or {}).get('mean'))} |")
    L.append("\n</details>\n")
    return L


def main():
    L = []
    done = [k for k, _ in ORDER if os.path.exists(os.path.join(HERE, k, "result.json"))]
    L.append("# 주기적 재조정(직전 10년 → 다음 1년) 30년 백테스트 — 결과\n")
    L.append(f"- 진행: {time.strftime('%Y-%m-%d %H:%M')} KST 갱신 · 끝난 전략 {len(done)}/{len(ORDER)} "
             f"({', '.join(done) or '없음'})")
    L.append("- 사전 등록 = `prereg.md`(= `prereg.frozen.md`, sha256 `" +
             open(os.path.join(HERE, "prereg.sha256")).read().split()[0][:16] + "…`, 동결 " +
             open(os.path.join(HERE, "prereg.frozen_at")).read().strip() + ")")
    head = os.path.join(HERE, "head.md")
    if os.path.exists(head):
        L.append("\n" + open(head).read().rstrip() + "\n")
    L.append("\n## 전략별\n")
    for key, title in ORDER:
        p = os.path.join(HERE, key, "result.json")
        if not os.path.exists(p):
            L.append(f"### {title}\n\n(아직 실행 전)\n")
            continue
        R = json.load(open(p))
        if key == "vb":
            for v, lab in (("opt", " — 낙관판"), ("pes", " — 비관판")):
                L += section(key, title, R[v], "r", lab)
            L.append(f"**VB 종합 = {R['label']}**\n")
        else:
            L += section(key, title, R)
    open(os.path.join(HERE, "result.md"), "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
