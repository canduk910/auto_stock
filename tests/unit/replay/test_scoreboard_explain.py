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
