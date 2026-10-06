"""30년 성적표 페이지 — 항목 설명(explain.json) 풀이와 묶음 매핑 검사."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_PAGE = Path(__file__).resolve().parents[3] / "tools" / "replay" / "scoreboard_page"
_spec = importlib.util.spec_from_file_location("scoreboard_build_page", _PAGE / "build_page.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)


def _explain():
    return json.loads(B.DEFAULT_EXPLAIN.read_text(encoding="utf-8"))


@pytest.mark.skipif(not B.DEFAULT_SRC.exists(), reason="scoreboard.json 없음")
def test_every_scoreboard_row_has_four_explained_fields():
    data = B.compress(json.loads(B.DEFAULT_SRC.read_text(encoding="utf-8")))
    explain = B.build_explain(_explain(), data["rows"])
    assert set(explain["items"]) == {r["id"] for r in data["rows"]}
    assert B.check_explain(explain) == []
    for eid, it in explain["items"].items():
        for k in B.FIELDS:
            assert it[k].strip(), (eid, k)
            assert k not in it["fallback"], (eid, k)


@pytest.mark.skipif(not B.DEFAULT_SRC.exists(), reason="scoreboard.json 없음")
def test_every_row_lands_in_a_template_group():
    data = B.compress(json.loads(B.DEFAULT_SRC.read_text(encoding="utf-8")))
    tpl = B.DEFAULT_TEMPLATE.read_text(encoding="utf-8")
    known = {"global", "global_wf", "base", "strategy", "regime_pause", "lev6040", "regime_v2",
             "rebal", "ddp", "qr", "qrx", "srs"}
    for k in known:
        assert f'key:"{k}"' in tpl
    assert {r["group"] for r in data["rows"]} <= known


@pytest.mark.parametrize("eid,group,expected", [
    ("SRS_KOJIRO", "external", "srs"),
    ("QRX_5_MAIN", "external", "qrx"),
    ("QR5_EQ", "external", "qr"),
    ("QR_TOP30", "external", "qr"),
    ("DDP_C_K200", "external", "ddp"),
    ("WF_OU", "external", "rebal"),
    ("RG_V1_90", "external", "lev6040"),
    ("RG_vb", "external", "regime_pause"),
    ("R2_IDX_ga", "external", "regime_v2"),
    ("GOLD_H", "external", "global"),
    ("AU_WF", "global_wf", "global_wf"),
    ("NQG_WF", "external", "global_wf"),
    ("AU_PERM", "external", "global"),
    ("NQG_EW", "external", "global"),
    ("kojiro", "strategy", "strategy"),
])
def test_group_mapping(eid, group, expected):
    assert B.map_group(eid, group) == expected


def test_family_resolution_fills_base_and_suffix():
    rows = [{"id": "kojiro", "name": "kojiro 현행", "desc": "d", "group": "strategy"},
            {"id": "SRS_KOJIRO_R20", "name": "x", "desc": "d", "group": "srs"}]
    it = B.build_explain(_explain(), rows)["items"]["SRS_KOJIRO_R20"]
    assert "kojiro(고지로 대순환 스윙)" in it["what"]
    assert it["assets"] == B.build_explain(_explain(), rows)["items"]["kojiro"]["assets"]
    assert "20영업일" in it["variant"]
    assert not it["fallback"]


def test_unregistered_id_falls_back_to_desc_and_is_reported():
    rows = [{"id": "ZZ_NEW", "name": "새 항목", "desc": "원 설명", "group": "global"}]
    ex = B.build_explain(_explain(), rows)
    it = ex["items"]["ZZ_NEW"]
    assert it["what"] == "원 설명" and it["rule"] == "원 설명"
    assert B.check_explain(ex)  # 설명 없는 항목은 검사에서 걸린다
    assert B.undefined_ids(ex) == ["ZZ_NEW"]


def test_gold_prefix_fallback_keeps_asset_line():
    rows = [{"id": "GOLD_NEW", "name": "금 새 판", "desc": "원 설명", "group": "external"}]
    it = B.build_explain(_explain(), rows)["items"]["GOLD_NEW"]
    assert "금" in it["assets"] and it["rule"] == "원 설명"


def test_template_has_both_placeholders_once():
    tpl = B.DEFAULT_TEMPLATE.read_text(encoding="utf-8")
    assert tpl.count("/*__DATA__*/null") == 1
    assert tpl.count("/*__EXPLAIN__*/null") == 1


GOLD_IDS = ("GOLD", "GOLD_H", "GOLD_LEV2", "AU_LEV2_H", "AU_K80G20", "AU_B1G10", "AU_PERM",
            "AU_WF", "NQG_EW", "NQG_IV", "NQG_WF")


def test_gold_ids_have_their_own_entries():
    ids = _explain()["ids"]
    for eid in GOLD_IDS:
        assert all(ids[eid].get(k) for k in B.FIELDS), eid


def test_r2_learned_variants_warn_about_inflated_30y_numbers():
    ids = _explain()["ids"]
    for eid in ("R2_IDX_da", "R2_IDX_ra", "R2_donchian_da", "R2_vcp_da", "R2_kojiro_da",
                "R2_donchian_ra", "R2_vcp_ra", "R2_kojiro_ra"):
        v = ids[eid]["variant"]
        assert "1997~2012" in v and ("부풀" in v or "판단 근거로 쓰지 않는다" in v), eid
    ra = ids["R2_IDX_ra"]
    assert "2010" in ra["assets"] and "145개" in ra["rule"] and "+1.1%" in ra["variant"]


# ───────────────────── 필터 태그 · 필터 규칙 ─────────────────────

def _rows():
    return B.compress(json.loads(B.DEFAULT_SRC.read_text(encoding="utf-8")))["rows"]


@pytest.mark.skipif(not B.DEFAULT_SRC.exists(), reason="scoreboard.json 없음")
def test_every_row_gets_complete_tags():
    rows = _rows()
    tags, problems = B.resolve_tags(_explain(), rows)
    assert problems == []
    vals = _explain()["tags"]["values"]
    assert set(tags) == {r["id"] for r in rows}
    for eid, t in tags.items():
        assert isinstance(t["regime"], bool), eid
        assert t["fx"] in vals["fx"], eid
        assert t["assets"] and set(t["assets"]) <= set(vals["assets"]), eid


@pytest.mark.skipif(not B.DEFAULT_SRC.exists(), reason="scoreboard.json 없음")
def test_hedge_tag_matches_nocarry_alt_exactly():
    rows = _rows()
    tags, _ = B.resolve_tags(_explain(), rows)
    hedged = {r["id"] for r in rows if tags[r["id"]]["fx"] == "H"}
    alts = {r["id"] for r in rows if r.get("alt")}
    assert hedged == alts and len(hedged) >= 29


@pytest.mark.skipif(not B.DEFAULT_SRC.exists(), reason="scoreboard.json 없음")
@pytest.mark.parametrize("eid,regime,fx,assets_has", [
    ("K200", False, "N", "kr_index"),
    ("SPX", False, "U", "os_index"),
    ("B-H", False, "H", "mix"),
    ("OL_NDX_H", False, "H", "lev"),
    ("OL_NDX_U50", False, "U", "cash"),
    ("GOLD_H", False, "H", "gold"),
    ("kojiro", True, "N", "kr_stock"),        # 원판에 시장 유닛
    ("vb", False, "N", "kr_stock"),
    ("etf_trend", True, "N", "kr_etf"),
    ("mr_fkeep", True, "N", "kr_stock"),      # 횡보장만
    ("F4", False, "U", "mix"),
    ("F5", True, "U", "mix"),
    ("BL_B0", False, "N", "kr_etf"),
    ("BL_A2", True, "N", "kr_etf"),
    ("RG_V1_SPX90", True, "U", "os_index"),
    ("R2_IDX_ra", True, "N", "lev"),
    ("RAUS_NDX_H_C", True, "H", "os_index"),
    ("RAUSB_P0_SPX_U_TR", True, "U", "os_index"),
    ("DDP_C_SPX", False, "U", "os_index"),
    ("DDP_VB", False, "N", "kr_stock"),
    ("SRS_ETF_TREND", True, "N", "kr_etf"),
    ("QR_TOP30", True, "N", "mix"),
    ("RAG_KOJIRO_G1", True, "N", "kr_stock"),
    ("RAG_KOJIRO_G0N", False, "N", "kr_stock"),  # 시장 유닛만 끈 판
    ("RAG_ETF_TREND_G1", True, "N", "kr_etf"),
    ("RAG_PORT_G0", True, "N", "mix"),
])
def test_tag_classification(eid, regime, fx, assets_has):
    rows = _rows()
    tags, _ = B.resolve_tags(_explain(), rows)
    if eid not in tags:
        pytest.skip(f"{eid} 행 없음")
    t = tags[eid]
    assert (t["regime"], t["fx"]) == (regime, fx), (eid, t)
    assert assets_has in t["assets"], (eid, t)


def test_missing_tags_fail_the_build():
    rows = [{"id": "ZZ_NEW", "group": "regime_v2", "status": "참고"}]
    ex = _explain()
    ex["tags"]["group_defaults"] = {}
    _, problems = B.resolve_tags(ex, rows)
    assert any("regime" in p for p in problems) and any("fx" in p for p in problems)
    assert any("assets" in p for p in problems)
    _, problems = B.resolve_tags({k: v for k, v in _explain().items() if k != "tags"}, rows)
    assert problems == ["explain.json 에 tags 없음"]


def test_hedge_tag_without_alt_fails():
    rows = [{"id": "OL_SPX_H", "group": "global", "status": "참고"}]          # alt 없음
    _, problems = B.resolve_tags(_explain(), rows)
    assert any("짝이 안 맞음" in p for p in problems)


# 필터 코어(template.html 의 /*__FILTER_CORE_BEGIN__*/ ~ END)를 node 로 돌린다
import shutil  # noqa: E402
import subprocess  # noqa: E402

_NODE = shutil.which("node")


def _run_core(js_body: str):
    tpl = B.DEFAULT_TEMPLATE.read_text(encoding="utf-8")
    a, b = "/*__FILTER_CORE_BEGIN__*/", "/*__FILTER_CORE_END__*/"
    assert tpl.count(a) == 1 and tpl.count(b) == 1
    core = tpl[tpl.index(a) + len(a):tpl.index(b)]
    out = subprocess.run([_NODE, "-e", core + "\nconsole.log(JSON.stringify((()=>{" + js_body + "})()));"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(_NODE is None, reason="node 없음")
def test_filter_core_bounds_units_and_drawdown_direction():
    r = _run_core(r'''
      const sp = k => RANGES.find(x=>x.k===k);
      const row = (m, t, st) => ({tags: t||{regime:true, fx:"H", assets:["os_index","lev"]}, status: st||"참고", m});
      const F = (o) => Object.assign({q:"", regime:"all", fx:"all", assets:[], status:[], ranges:{}}, o);
      const pass = (rw, f, txt) => passFilter(rw, {metrics: rw.m, extra:{}}, f, txt||"");
      const m = {cagr:0.10, mdd:-0.40, longest_underwater_days:365, final_value_10m:123456789, excess_vs_k200:0.012, sharpe:0.5};
      return {
        p_pct: parseBound("10%", sp("cagr")), p_minus: parseBound("−12.5", sp("cagr")), p_bad: parseBound("abc", sp("cagr")),
        p_mdd_pos: parseBound("40", sp("mdd")), p_mdd_neg: parseBound("−40", sp("mdd")), p_pp: parseBound("1.2%p", sp("ex")),
        p_day: parseBound("1,000일", sp("uw")), p_man: parseBound("12,345만 원", sp("final")),
        shown_cagr: shownValue(sp("cagr"), m), shown_final: shownValue(sp("final"), m), shown_uw: shownValue(sp("uw"), m),
        edge_min: pass(row(m), F({ranges:{cagr:{min:10, max:null}}})),
        edge_max: pass(row(m), F({ranges:{cagr:{min:null, max:10}}})),
        above: pass(row(m), F({ranges:{cagr:{min:10.01, max:null}}})),
        mdd_shallow_ok: pass(row(m), F({ranges:{mdd:{min:-40, max:null}}})),
        mdd_shallow_cut: pass(row({...m, mdd:-0.41}), F({ranges:{mdd:{min:-40, max:null}}})),
        mdd_deep_only: pass(row({...m, mdd:-0.2}), F({ranges:{mdd:{min:null, max:-30}}})),
        null_value_cut: pass(row({...m, sharpe:null}), F({ranges:{sharpe:{min:0, max:null}}})),
        final_man: pass(row(m), F({ranges:{final:{min:12345, max:12346}}})),
        regime_off: pass(row(m), F({regime:"off"})), fx_h: pass(row(m), F({fx:"H"})), fx_u: pass(row(m), F({fx:"U"})),
        assets_or: pass(row(m), F({assets:["gold","lev"]})), assets_none: pass(row(m), F({assets:["gold"]})),
        status: pass(row(m, null, "실패"), F({status:["통과","보류"]})),
        q_and: pass(row(m), F({q:"나스닥 2배"}), "나스닥100 2배 단순 보유"), q_miss: pass(row(m), F({q:"나스닥 금"}), "나스닥100 2배"),
        chip_mdd: rangeChipText(sp("mdd"), {min:-40, max:null}), chip_cagr: rangeChipText(sp("cagr"), {min:10, max:null}),
        chip_both: rangeChipText(sp("sharpe"), {min:0.5, max:1}),
      };''')
    assert r["p_pct"] == 10 and r["p_minus"] == -12.5 and r["p_bad"] is None
    assert r["p_mdd_pos"] == -40 and r["p_mdd_neg"] == -40          # 낙폭은 양수를 넣어도 음수 한도
    assert r["p_pp"] == 1.2 and r["p_day"] == 1000 and r["p_man"] == 12345
    assert abs(r["shown_cagr"] - 10) < 1e-9 and abs(r["shown_final"] - 12345.6789) < 1e-6 and r["shown_uw"] == 365
    assert r["edge_min"] and r["edge_max"] and not r["above"]           # 경계 포함
    assert r["mdd_shallow_ok"] and not r["mdd_shallow_cut"] and not r["mdd_deep_only"]
    assert not r["null_value_cut"] and r["final_man"]
    assert not r["regime_off"] and r["fx_h"] and not r["fx_u"]
    assert r["assets_or"] and not r["assets_none"] and not r["status"]
    assert r["q_and"] and not r["q_miss"]
    assert r["chip_mdd"] == "최대 낙폭 ≥ −40%(얕은 쪽)" and r["chip_cagr"] == "연평균(CAGR) ≥ 10%"
    assert r["chip_both"] == "0.5 ≤ 샤프 ≤ 1"


def test_template_has_filter_and_carry_controls():
    tpl = B.DEFAULT_TEMPLATE.read_text(encoding="utf-8")
    for s in ('id="carryTg"', "환헤지 금리차 반영", "끄면 금리차를 뺀 순수 환율 제거판을 봅니다", 'id="fbox"', 'id="fReset"',
              "개 중 ", "(금리차 제외 — 현지 통화 수익)", "금리차 뺀 판은 판정하지 않음(참고)", 'id="rgrid"'):
        assert s in tpl, s
