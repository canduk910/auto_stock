#!/usr/bin/env python3
"""30년 전략 성적표 HTML 한 장을 만든다.

scoreboard.json 읽기 → 외부 항목 묶음 다시 매기기 → 곡선·지표 압축 → 항목 설명(explain.json) 풀기
→ template.html 의 두 자리(/*__DATA__*/null · /*__EXPLAIN__*/null) 치환 → 출력.

    python tools/replay/scoreboard_page/build_page.py            # 기본 경로로 만들기
    python tools/replay/scoreboard_page/build_page.py --check    # 설명 검사만(파일 안 씀)

설명 규약 = explain.json 의 "_about". 성적표의 모든 항목은 what·assets·rule·variant 네 칸이
explain.json 에서 와야 한다(원 설명 desc 폴백으로 채운 항목이 있으면 실패).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_SRC = REPO / "_workspace/analysis/scoreboard_20261006/scoreboard.json"
DEFAULT_OUT = REPO / "_workspace/reports/2026-10-06_scoreboard_30y.html"
DEFAULT_TEMPLATE = HERE / "template.html"
DEFAULT_EXPLAIN = HERE / "explain.json"

FIELDS = ("what", "assets", "rule", "variant")
UNDEFINED = "원자료에 정의 없음"
GOLD_PREFIXES = ("GOLD", "AU_", "NQG_")

# 외부 항목(group == "external") → 템플릿 묶음 key. 위에서부터 첫 일치.
EXTERNAL_GROUP_RULES = (
    ("SRS_", "srs"),
    ("QRX_", "qrx"),
    ("QR5_", "qr"),
    ("QR_", "qr"),
    ("DDP_", "ddp"),
    ("WF_", "rebal"),
    ("RG_V", "lev6040"),
    ("R2_", "regime_v2"),
    ("RAUSB_", "regime_v2"),
    ("RAUS_", "regime_v2"),
    ("RAG_", "regime_v2"),
)


def map_group(row_id: str, group: str) -> str:
    """금 접두는 어느 묶음에서 왔든 global(걷기 전진 _WF 는 global_wf). 그 밖의 external 은 id 접두로, 나머지 external 은 regime_pause."""
    if row_id.startswith(GOLD_PREFIXES):
        return "global_wf" if row_id.endswith("_WF") else "global"
    if group != "external":
        return group
    for prefix, key in EXTERNAL_GROUP_RULES:
        if row_id.startswith(prefix):
            return key
    return "regime_pause"


# ---------- 압축 (scratchpad build_v2.py 로직 그대로) ----------

def r6(x):
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, int):
        return x
    return float(f"{x:.6g}")


KEEP = ["start", "end", "years", "total_return", "cagr", "mdd", "mdd_peak", "mdd_trough", "mdd_recovery",
        "longest_underwater_days", "longest_underwater_ongoing", "longest_underwater_from", "vol", "sharpe",
        "sortino", "mar", "pos_year_ratio", "n_full_years", "worst_12m", "worst_12m_end", "ulcer",
        "final_value_10m", "n_months", "k200_cagr_same_window", "excess_vs_k200", "corr_k200",
        "turnover_yr", "cost_yr", "after_tax_cagr"]
EXTRA_KEEP = ["start_equity", "rep_seed", "n_seeds", "seed_cagr_median", "seed_cagr_min", "seed_cagr_max",
              "seed_mdd_median", "fills_per_year", "orders_per_year", "avg_stock_share", "cost_yr", "window"]


def compress(src: dict) -> dict:
    rows = []
    for r in src["rows"]:
        m = r["metrics"]
        mm = {k: (r6(m[k]) if not isinstance(m[k], str) else m[k]) for k in KEEP if k in m}
        mm["best_year"] = {"year": m["best_year"]["year"], "ret": r6(m["best_year"]["ret"])} if m.get("best_year") else None
        mm["worst_year"] = {"year": m["worst_year"]["year"], "ret": r6(m["worst_year"]["ret"])} if m.get("worst_year") else None
        mm["yearly"] = {y: [r6(v["ret"]), 1 if v["full"] else 0, v["days"]] for y, v in m["yearly"].items()}
        e = r["extra"]
        ex = {}
        for k in EXTRA_KEEP:
            if k in e:
                ex[k] = r6(e[k]) if not isinstance(e[k], (str, list)) else e[k]
        c = r["curves"]
        rows.append({
            "id": r["id"], "name": r["name"], "desc": r["desc"], "group": map_group(r["id"], r["group"]),
            "status": r["status"], "status_ref": r["status_ref"], "tax_note": r["tax_note"],
            "source": r["source"], "note": r["note"], "extra": ex, "metrics": mm,
            "curves": {"m": [s[:7] for s in c["month_end"]],
                       "c": [r6(float(f"{v:.5g}")) for v in c["cum"]],
                       "d": [round(v, 4) for v in c["dd_min"]]},
        })
    return {"generated_kst": src["generated_kst"], "rules": src["rules"],
            "reconcile": {"n": len(src["reconcile"]), "match": sum(1 for x in src["reconcile"] if x["match"])},
            "rows": rows}


# ---------- 설명 풀기 ----------

_PH = re.compile(r"\{([a-z_]+)\}")


def _parse_family(fam: dict, eid: str):
    """eid 가 이 계열(접두 + 기반 + 꼬리)이면 (기반 key, 꼬리) — 가장 긴 기반 key 우선. 아니면 None."""
    if not eid.startswith(fam["prefix"]):
        return None
    rest = eid[len(fam["prefix"]):]
    for key in sorted(fam["bases"], key=len, reverse=True):
        if rest.startswith(key) and rest[len(key):] in fam["suffixes"]:
            return key, rest[len(key):]
    return None


def _family_layers(ex: dict, eid: str) -> list[dict]:
    for fam in sorted(ex.get("families", []), key=lambda f: len(f["prefix"]), reverse=True):
        hit = _parse_family(fam, eid)
        if hit is None:
            continue
        key, suf = hit
        spec = fam["bases"][key]
        base_layer = {"base": spec} if isinstance(spec, str) else {
            **({"base": spec["base"]} if spec.get("base") else {}), **spec.get("fields", {})}
        return [fam.get("fields", {}), base_layer, fam["suffixes"][suf]]
    return []


def resolve(ex: dict, rows_by_id: dict, eid: str, _stack: tuple = ()) -> dict:
    """항목 하나의 설명 칸(what·assets·rule·variant·short·label)과 출처 표시(fallback)를 돌려준다."""
    if eid in _stack:
        raise ValueError(f"설명 기반(base) 순환: {' → '.join(_stack + (eid,))}")
    row = rows_by_id.get(eid)
    f: dict = {}
    if row is not None:
        f.update(ex.get("group_defaults", {}).get(row["group"], {}))
    for layer in _family_layers(ex, eid):
        f.update(layer)
    f.update(ex.get("ids", {}).get(eid, {}))
    fallback: list[str] = []
    if not any(f.get(k) for k in FIELDS):
        for prefix, pf in ex.get("prefix_fallback", {}).items():
            if eid.startswith(prefix):
                f = {**pf, **f}
                break
    base = None
    if f.get("base"):
        base = resolve(ex, rows_by_id, f["base"], _stack + (eid,))
    label = f.get("label") or (row["name"] if row else eid)
    values = {k: v for k, v in f.items() if isinstance(v, str)}
    values["label"] = label
    if base is not None:
        for k in ("label", "what", "assets", "rule", "short"):
            values[f"base_{k}"] = base[k]

    def fill(text: str) -> str:
        for _ in range(3):  # 자기 칸 안의 자기 참조({label} 등)까지 한두 번 더 편다
            new = _PH.sub(lambda m: values.get(m.group(1), m.group(0)), text)
            if new == text:
                break
            text = new
        return text

    out = {"label": label}
    desc = row["desc"] if row else ""
    for k in FIELDS + ("short",):
        v = fill(f[k]) if f.get(k) else ""
        if not v:
            fallback.append(k)
            if k == "rule" and desc:
                v = desc
            elif k == "short":
                v = ""
            else:
                v = UNDEFINED if k != "what" or not desc else desc
        out[k] = v
    out["fallback"] = fallback
    return out


def build_explain(ex: dict, rows: list[dict]) -> dict:
    rows_by_id = {r["id"]: r for r in rows}
    items = {r["id"]: resolve(ex, rows_by_id, r["id"]) for r in rows}
    return {"items": items, "groups": ex.get("groups", {}), "glossary": ex.get("glossary", [])}


def check_explain(explain: dict) -> list[str]:
    """문제 목록(빈 목록 = 통과). 네 칸이 explain.json 에서 오지 않았거나, 덜 풀린 자리 표시가 남은 항목."""
    problems = []
    for eid, it in explain["items"].items():
        missing = [k for k in FIELDS if k in it["fallback"]]
        if missing:
            problems.append(f"{eid}: 설명 없음 {missing}")
        for k in FIELDS + ("short", "label"):
            if _PH.search(it[k]):
                problems.append(f"{eid}.{k}: 풀리지 않은 자리 표시 {it[k]!r}")
            if not it[k].strip() and k != "short":
                problems.append(f"{eid}.{k}: 빈 칸")
    return problems


def undefined_ids(explain: dict) -> list[str]:
    return sorted(eid for eid, it in explain["items"].items() if any(UNDEFINED in it[k] for k in FIELDS))


def _js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build(src_path: Path, template_path: Path, explain_path: Path, out_path: Path | None) -> dict:
    src = json.loads(src_path.read_text(encoding="utf-8"))
    data = compress(src)
    ex = json.loads(explain_path.read_text(encoding="utf-8"))
    explain = build_explain(ex, data["rows"])
    problems = check_explain(explain)
    report = {"rows": len(data["rows"]), "problems": problems, "undefined": undefined_ids(explain)}
    if problems:
        return report
    if out_path is not None:
        tpl = template_path.read_text(encoding="utf-8")
        for mark in ("/*__DATA__*/null", "/*__EXPLAIN__*/null"):
            if tpl.count(mark) != 1:
                raise SystemExit(f"템플릿 자리 {mark} 가 정확히 한 번 있어야 한다(지금 {tpl.count(mark)}번)")
        html = tpl.replace("/*__DATA__*/null", _js(data)).replace("/*__EXPLAIN__*/null", _js(explain))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        report["bytes"] = len(html.encode("utf-8"))
        report["out"] = str(out_path)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    ap.add_argument("--explain", type=Path, default=DEFAULT_EXPLAIN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="설명 검사만 하고 파일을 쓰지 않는다")
    a = ap.parse_args(argv)
    rep = build(a.src, a.template, a.explain, None if a.check else a.out)
    print(f"항목 {rep['rows']}개 · 설명 문제 {len(rep['problems'])}건 · 「{UNDEFINED}」 항목 {len(rep['undefined'])}개")
    for p in rep["problems"]:
        print("  문제:", p)
    for u in rep["undefined"]:
        print(f"  {UNDEFINED}:", u)
    if rep.get("out"):
        print(f"출력 {rep['out']} ({rep['bytes']:,} 바이트)")
    return 1 if rep["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
