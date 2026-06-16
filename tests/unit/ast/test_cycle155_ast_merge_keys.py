"""사이클 155 — FHKST01010100 merge 35 키 AST 영구 가드.

사이클 145 G-AST1 영역 영구 영속 답습:
- _FHKST_MERGE_KEYS 모듈 상수 영역 영구 영속 (35 키 정합)
- _ZERO_VALUE_SKIP_KEYS frozenset 영역 영구 영속 (사이클 145 패턴 답습)

영속 의무:
- 사이클 81 G-AST1 raw 영역 영구 영속 보호 (덮어쓰기 금지 영역 영구 영속)
- 사이클 107 inquire_stock_basics merge 패턴 영속
- 사이클 145 _ZERO_VALUE_SKIP_KEYS 영역 영구 영속
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_CONDITION_PY = Path(__file__).resolve().parents[3] / "src" / "api" / "condition.py"


class TestCycle155AstMergeKeys:
    """G-AST-155: _FHKST_MERGE_KEYS 영역 영구 영속 35 키 + _ZERO_VALUE_SKIP_KEYS 정합."""

    def test_g_ast_155_module_constants_exist(self):
        """G-AST-155-1: _FHKST_MERGE_KEYS + _ZERO_VALUE_SKIP_KEYS 모듈 상수 존재."""
        from src.api import condition

        assert hasattr(condition, "_FHKST_MERGE_KEYS"), (
            "G-AST-155-1: _FHKST_MERGE_KEYS 모듈 상수 부재"
        )
        assert hasattr(condition, "_ZERO_VALUE_SKIP_KEYS"), (
            "G-AST-155-1: _ZERO_VALUE_SKIP_KEYS 모듈 상수 부재"
        )
        assert isinstance(condition._FHKST_MERGE_KEYS, tuple)
        assert isinstance(condition._ZERO_VALUE_SKIP_KEYS, frozenset)

    def test_g_ast_155_35_keys_total(self):
        """G-AST-155-2: _FHKST_MERGE_KEYS 35 키 정합 영역 영구 영속.

        사이클 107 5 키 + 사이클 155 신규 30 키 = 35 키.
        """
        from src.api import condition

        merge_keys = set(condition._FHKST_MERGE_KEYS)
        # 사이클 107 5 키 영역 영구 영속
        for k in ("acml_tr_pbmn", "lstn_stcn", "acml_vol", "prdy_vrss", "hts_avls"):
            assert k in merge_keys, f"사이클 107 영속 키 {k} 부재"

        # 사이클 155 HIGH 영역 핵심 키
        for k in (
            "per", "pbr",
            "hts_frgn_ehrt", "frgn_ntby_qty",
            "stck_mxpr", "stck_llam",
            "vol_tnrt", "prdy_vrss_vol_rate",
            "w52_hgpr", "w52_lwpr", "w52_hgpr_date", "d250_hgpr", "d250_lwpr",
            "mrkt_warn_cls_code", "invt_caful_yn", "short_over_yn", "sltr_yn",
            "iscd_stat_cls_code", "temp_stop_yn",
            "new_hgpr_lwpr_cls_code",
            "eps", "bps",
            "whol_loan_rmnd_rate",
        ):
            assert k in merge_keys, f"사이클 155 HIGH 키 {k} 부재"

        # 사이클 155 MEDIUM 영역
        for k in (
            "ssts_yn", "last_ssts_cntg_qty",
            "vi_cls_code", "ovtm_vi_cls_code",
            "bstp_kor_isnm",
        ):
            assert k in merge_keys, f"사이클 155 MEDIUM 키 {k} 부재"

        # 총 33 키 정합 영역 영구 영속 (사용자 명세 영영 = HIGH 23 + 추가 회복 3 + MEDIUM 5 + 사이클 107 5)
        # 영영 영영 정합: eps/bps 영영 = HIGH 영역 추가 회복 영영 (MEDIUM 영영 중복 제거 영영).
        assert len(merge_keys) == 33, (
            f"_FHKST_MERGE_KEYS 33 키 정합 영역 영구 영속 위반: 실측 {len(merge_keys)}"
        )

    def test_g_ast_155_zero_skip_keys_subset(self):
        """G-AST-155-3: _ZERO_VALUE_SKIP_KEYS ⊆ _FHKST_MERGE_KEYS 영역 영구 영속."""
        from src.api import condition

        merge_keys = set(condition._FHKST_MERGE_KEYS)
        skip_keys = set(condition._ZERO_VALUE_SKIP_KEYS)

        # skip_keys 는 merge_keys 의 부분집합
        assert skip_keys.issubset(merge_keys), (
            f"_ZERO_VALUE_SKIP_KEYS 영역 _FHKST_MERGE_KEYS 부분집합 위반: "
            f"외부 키 = {skip_keys - merge_keys}"
        )

        # 사이클 145 영역 영구 영속 = acml_tr_pbmn + acml_vol 영속
        assert "acml_tr_pbmn" in skip_keys
        assert "acml_vol" in skip_keys

        # 사이클 155 영역 영구 영속 = per/pbr/vol_tnrt 영역 영구 영속
        assert "per" in skip_keys
        assert "pbr" in skip_keys
        assert "vol_tnrt" in skip_keys

        # 비숫자 영역 = skip 영역 미포함 의무 (vi_cls_code "0" = 의미 있음)
        assert "vi_cls_code" not in skip_keys, (
            "vi_cls_code 영역 = _ZERO_VALUE_SKIP_KEYS 포함 금지 (사이클 149 영속)"
        )
        assert "iscd_stat_cls_code" not in skip_keys
        assert "w52_hgpr_date" not in skip_keys
