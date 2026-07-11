"""사이클 204 — 투자주의 차단 해제 (HIGH 매매 기회, 급등주 복원) Red 가드.

근거: `_workspace/domain_consult/cycle204_investment_caution_unblock.md`
(KIS 삼각검증: 00=정상 / 01=투자주의 / 02=투자경고 / 03=투자위험 +
차단 index 9종목 전부 우량 대형주 실증). 사용자 통찰: 급등 → 투자주의 지정
→ 돌파전략 후보 제거.

확정 변경 (`src/engine/scanner.py::_is_master_blocked_for_entry` raw 분기):
1. `mrkt_warn_cls_code >= "01"` → `>= "02"` (투자주의 01 해제, 경고 02/위험 03 유지)
2. `invt_caful_yn == "Y"` 차단 블록 완전 삭제 (투자유의 함께 해제)
3. merge/적재(`condition._FHKST_MERGE_KEYS`) 는 불변 — 차단만 완화

영속 의무:
- 사이클 32 R4 보유/익일청산 절대 보호 (본 함수는 진입 차단 판정만)
- 사이클 38 명문화 (scanner 매수 진입 전 한정)
- 사이클 81 G-AST1 raw read-only 영속
- 사이클 155 FHKST raw 분기 / 사이클 203 iscd 제거 영속
"""

from __future__ import annotations

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


class TestCycle204InvestmentCautionUnblock:
    """G-204-1~7: 투자주의/투자유의 un-block + SAFETY 급등·경고·위험 불변식."""

    def test_g_204_1_market_warn_01_unblock(self):
        """G-204-1 (핵심): mrkt_warn_cls_code "01" (투자주의) → un-block.

        현재 코드 `>= "01"` = (True, "FHKST 시장경고 (01)") → RED.
        Green (`>= "02"`) 후 (False, "") 통과.
        """
        b, r = scanner._is_master_blocked_for_entry(None, {"mrkt_warn_cls_code": "01"})
        assert b is False, "G-204-1 — 투자주의(01) 차단 해제 (급등주 복원)"
        assert r == ""

    def test_g_204_2_invt_caful_unblock(self):
        """G-204-2 (핵심): invt_caful_yn "Y" (투자유의) → un-block.

        현재 코드 = (True, "투자유의 (invt_caful_yn=Y, FHKST)") → RED.
        Green (블록 삭제) 후 (False, "") 통과.
        """
        b, r = scanner._is_master_blocked_for_entry(None, {"invt_caful_yn": "Y"})
        assert b is False, "G-204-2 — 투자유의 차단 완전 해제 (domain 확정)"
        assert r == ""

    def test_g_204_3_market_warn_02_still_blocked(self):
        """G-204-3 (SAFETY 유지): mrkt_warn_cls_code "02" (투자경고) → 차단 불변식."""
        b, r = scanner._is_master_blocked_for_entry(None, {"mrkt_warn_cls_code": "02"})
        assert b is True, "G-204-3 — 투자경고(02) 차단 불변"
        assert "FHKST" in r and "시장경고" in r

    def test_g_204_4_market_warn_03_still_blocked(self):
        """G-204-4 (SAFETY 유지): mrkt_warn_cls_code "03" (투자위험) → 차단 불변식."""
        b, r = scanner._is_master_blocked_for_entry(None, {"mrkt_warn_cls_code": "03"})
        assert b is True, "G-204-4 — 투자위험(03) 차단 불변"
        assert "FHKST" in r and "시장경고" in r

    def test_g_204_5_runup_flags_still_blocked(self):
        """G-204-5 (SAFETY 유지): 급등 3플래그 각 차단 불변식.

        단기과열(short_over_yn) / 공매도과열(ssts_hot_yn) / 이상급등(stange_runup_yn)
        = 급등 극단·작전 위험. 투자주의 완화와 무관하게 유지.
        """
        # 단기과열 (raw 분기)
        b, r = scanner._is_master_blocked_for_entry(None, {"short_over_yn": "Y"})
        assert b is True, "G-204-5 — 단기과열 차단 불변 (short_over_yn)"
        assert "단기과열" in r

        # 공매도과열 (master_raw 분기)
        b, r = scanner._is_master_blocked_for_entry({"ssts_hot_yn": "Y"}, None)
        assert b is True, "G-204-5 — 공매도과열 차단 불변 (ssts_hot_yn)"
        assert "공매도과열" in r

        # 이상급등 (master_raw 분기)
        b, r = scanner._is_master_blocked_for_entry({"stange_runup_yn": "Y"}, None)
        assert b is True, "G-204-5 — 이상급등 차단 불변 (stange_runup_yn)"
        assert "이상급등" in r

    def test_g_204_6_other_dedicated_flags_still_blocked(self):
        """G-204-6 (SAFETY 유지): 기타 전용 플래그 각 차단 불변식.

        거래정지/관리종목/정리매매/임시정지/시장경보(master)/투자주의환기(master).
        """
        # master_raw 분기
        for key, expect in (
            ("trht_yn", "거래정지"),
            ("mang_issu_yn", "관리종목"),
            ("sltr_yn", "정리매매"),
            ("invt_alrm_yn", "투자주의환기"),
        ):
            b, r = scanner._is_master_blocked_for_entry({key: "Y"}, None)
            assert b is True, f"G-204-6 — master_raw {key} 차단 불변"
            assert expect in r

        # master_raw 시장경보 >= "02"
        b, r = scanner._is_master_blocked_for_entry({"mrkt_alrm_cls_code": "02"}, None)
        assert b is True, "G-204-6 — 시장경보(master) 02 차단 불변"

        # raw(FHKST) 분기 정리매매/임시정지
        b, r = scanner._is_master_blocked_for_entry(None, {"sltr_yn": "Y"})
        assert b is True, "G-204-6 — FHKST 정리매매 차단 불변 (sltr_yn)"
        assert "정리매매" in r

        b, r = scanner._is_master_blocked_for_entry(None, {"temp_stop_yn": "Y"})
        assert b is True, "G-204-6 — FHKST 임시정지 차단 불변 (temp_stop_yn)"
        assert "임시" in r

    def test_g_204_7_warn01_with_runup_still_blocked(self):
        """G-204-7 (경계): mrkt_warn "01" + 급등 플래그 동반 → 여전히 차단.

        완화가 과열 종목을 통과시키지 않음을 보장. 투자주의만 있는 우량주는
        통과(G-204-1)하되, 단기과열이 동반되면 short_over_yn 로 차단.
        """
        b, r = scanner._is_master_blocked_for_entry(
            None, {"mrkt_warn_cls_code": "01", "short_over_yn": "Y"}
        )
        assert b is True, "G-204-7 — 투자주의 완화 후에도 단기과열 동반 시 차단"
        assert "단기과열" in r
