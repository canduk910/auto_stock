"""사이클 155 — _is_master_blocked_for_entry 1단계 차단 7건 → 13건 확장 회귀 가드.

사이클 129 master_raw 영역 영구 영속 7건 + 사이클 155 FHKST raw 영역 영구 영속 6건 = 13건.

**사이클 203 의미 전환**: FHKST raw 6건 중 iscd_stat_cls_code 차단은 완전 제거
(운영 DB 실측 = "55만 정상" 가정이 틀림, 57=정상 91%). 5건으로 축소.

**사이클 204 의미 전환**: FHKST raw 5건 중 투자주의(mrkt_warn_cls_code "01")
+ 투자유의(invt_caful_yn) 차단 해제. KIS 삼각검증 결과 차단 대상 index
9종목 전부 우량 대형주 실증 (급등 → 투자주의 지정 → 돌파전략 후보에서
제거되는 역설). 투자경고(02)/투자위험(03) 는 계속 차단. 최종 4건
(master_raw 7 + raw 4 = 11건). `tests/unit/engine/scanner/test_cycle204_investment_caution_unblock.py`
참조.

영속 의무:
- 사이클 32 R4 보유/익일청산 절대 보호 (호출 사이트 영역 영구 영속 의무 — 본 함수는 진입 차단만 판정)
- 사이클 38 명문화 (scanner 매수 진입 전 한정)
- 사이클 81 G-AST1 raw 영역 영구 영속 보호 (사이클 129 master_raw 우선 + raw 폴백 영속)
- 사이클 129 1단계 차단 7건 패턴 답습
"""

from __future__ import annotations

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


class TestCycle155Block13Keys:
    """G-155-BLOCK-1~3: master_raw 7건 + FHKST raw 4건 = 11건 차단 (사이클 204 투자주의 해제)."""

    def test_g_155_block_1_fhkst_raw_4_keys(self):
        """G-155-BLOCK-1 (HIGH): FHKST raw 영역 4 키 차단 영역 영구 영속.

        사이클 203 의미 전환 — iscd_stat_cls_code 차단은 완전 제거 (운영 DB
        실측 결과 "55만 정상" 가정이 틀림, 57=정상 91%). 6키→5키.
        사이클 204 의미 전환 — 투자주의(mrkt_warn "01") + 투자유의
        (invt_caful_yn) 차단 해제. 5키→4키.
        """
        # mrkt_warn_cls_code "01"(투자주의) = 사이클 204 un-block
        b, r = scanner._is_master_blocked_for_entry({}, {"mrkt_warn_cls_code": "01"})
        assert b is False
        assert r == ""

        # mrkt_warn_cls_code "02"(투자경고) = 차단 유지
        b, r = scanner._is_master_blocked_for_entry({}, {"mrkt_warn_cls_code": "02"})
        assert b is True
        assert "FHKST" in r

        # invt_caful_yn = 투자유의 (사이클 204 un-block)
        b, r = scanner._is_master_blocked_for_entry({}, {"invt_caful_yn": "Y"})
        assert b is False
        assert r == ""

        # short_over_yn = 단기과열
        b, r = scanner._is_master_blocked_for_entry({}, {"short_over_yn": "Y"})
        assert b is True
        assert "단기과열" in r

        # sltr_yn = 정리매매 (FHKST 영역)
        b, r = scanner._is_master_blocked_for_entry({}, {"sltr_yn": "Y"})
        assert b is True
        assert "정리매매" in r

        # temp_stop_yn = 임시 정지
        b, r = scanner._is_master_blocked_for_entry({}, {"temp_stop_yn": "Y"})
        assert b is True
        assert "임시" in r

    def test_g_155_block_2_or_logic(self):
        """G-155-BLOCK-2 (MEDIUM): master_raw + raw OR 영역 영구 영속.

        어느 한쪽이라도 차단 = 진입 차단.
        master_raw 단독 → 사이클 129 영역 차단.
        raw 단독 → 사이클 155 영역 차단.
        양쪽 모두 정상 → 통과.
        """
        # master_raw 단독 차단 (사이클 129)
        b, r = scanner._is_master_blocked_for_entry({"trht_yn": "Y"}, {})
        assert b is True
        assert "거래정지" in r

        # raw 단독 차단 (사이클 155)
        b, r = scanner._is_master_blocked_for_entry({}, {"temp_stop_yn": "Y"})
        assert b is True

        # 양쪽 정상 → 통과
        b, r = scanner._is_master_blocked_for_entry(
            {"trht_yn": "N"}, {"iscd_stat_cls_code": "55"}
        )
        assert b is False
        assert r == ""

        # raw 인자 미전달 (회귀 보존)
        b, r = scanner._is_master_blocked_for_entry({"trht_yn": "N"})
        assert b is False

    def test_g_155_block_3_graceful_on_invalid(self):
        """G-155-BLOCK-3 (HIGH): None/공백/빈 dict graceful + 보유 보호 의무는 호출 사이트."""
        # raw 빈 문자열 영역 영구 영속 (FHKST 응답 빈 영역) → graceful 통과
        b, r = scanner._is_master_blocked_for_entry(
            {}, {"iscd_stat_cls_code": "", "temp_stop_yn": "", "mrkt_warn_cls_code": ""}
        )
        assert b is False
        assert r == ""

        # raw None → graceful (회귀 보존)
        b, r = scanner._is_master_blocked_for_entry({"trht_yn": "N"}, None)
        assert b is False

        # 양쪽 모두 None/빈 → graceful 통과
        b, r = scanner._is_master_blocked_for_entry({}, {})
        assert b is False
        assert r == ""

    def test_g_155_block_4_cycle129_seven_keys_preserve(self):
        """G-155-BLOCK-4 (HIGH): 사이클 129 영역 7 키 영구 영속 차단 영속."""
        # 7 키 영역 영구 영속 = 모두 차단 동작
        for key in (
            "trht_yn",
            "sltr_yn",
            "mang_issu_yn",
            "ssts_hot_yn",
            "stange_runup_yn",
            "invt_alrm_yn",
        ):
            b, r = scanner._is_master_blocked_for_entry({key: "Y"}, None)
            assert b is True, f"키 {key} 차단 실패"
        # 시장경고 02 영역
        b, r = scanner._is_master_blocked_for_entry(
            {"mrkt_alrm_cls_code": "02"}, None
        )
        assert b is True
        assert "시장경고" in r
