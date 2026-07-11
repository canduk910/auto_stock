"""사이클 203 — VCP funnel step3 과차단 시정: iscd_stat_cls_code 차단 체크 완전 제거.

명세: _workspace/red/cycle203_iscd_stat_overblock.md
자문: _workspace/domain_consult/cycle203_iscd_stat_overblock.md (KIS MCP + 운영 DB 3,576종목 실측)

배경 (확정 진단):
- scanner.py `_is_master_blocked_for_entry` L2565-2568 이 raw.iscd_stat_cls_code != "55"
  이면 매수 진입 전부 차단. "55만 정상" 가정이 틀림 — 실측: 코드 57=정상/그외(91%,
  3,270종목 전부 거래) / 58=현재가0 잔재(정상주 혼입) / 51=정상(ETF·스팩) / 52=투자위험
  (유니버스 0건) / 53/54/59=시장경고 계열(전용 플래그가 100% 커버).
- 현 체크가 KOSPI200∪KOSDAQ150 정상 대형주 60~75% 오차단 (VCP 182→63).

확정 시정 = L2565-2568 완전 삭제.
- iscd 로 차단하려던 위험(53/54/59/정리매매/관리/거래정지)은 전부 전용 플래그
  (mrkt_warn_cls_code / short_over_yn / sltr_yn / mang_issu_yn / trht_yn / temp_stop_yn 등)가
  실측 100% 커버 = 완전 중복. iscd 가 고유하게 잡는 위험 0건.
- 전용 플래그 12건 전부 유지 (SAFETY 불변).

Red 유효성 (현재 코드):
- (1)/(2)/(8)/(9) FAIL — iscd=57/58/51 정상주 차단 + iscd=52 단독 차단 + AST 참조 잔존.
- (3~7) PASS(불변식) — 전용 플래그 차단은 iscd 제거와 무관하게 유지.

영속 의무:
- 사이클 32 R4 보유/익일청산 절대 보호 (apply_master_block_filter 의 protected_tickers,
  이 함수 밖 — 불변).
- 사이클 38 명문화 (scanner 매수 진입 전 한정).
- 사이클 81 G-AST1 raw 영역 read-only 영속.
- 사이클 155 raw 6건 → 5건 (iscd 제거) / 사이클 129 master_raw 7건 불변.
"""

from __future__ import annotations

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


class TestCycle203IscdNoOverblock:
    """iscd_stat_cls_code 차단 제거 — 정상주 un-block + 전용 플래그 보호 유지."""

    def test_g_203_1_iscd_57_normal_unblock(self):
        """G-203-1 (HIGH): iscd=57 정상주 (다른 위험 플래그 전부 부재) → 통과.

        실측 57 = 3,270종목 (91%) 전부 거래 정상. 현재 코드는 "종목상태 비정상" 차단.
        """
        b, r = scanner._is_master_blocked_for_entry(None, {"iscd_stat_cls_code": "57"})
        assert b is False, (
            "G-203-1 — iscd=57 정상주는 통과 의무 (현재 코드는 '55만 정상' 오가정 → 차단)"
        )
        assert r == ""

    def test_g_203_2_iscd_58_51_normal_unblock(self):
        """G-203-2 (HIGH): iscd=58 / 51 정상주 → 통과.

        58 = 현재가0 데이터 신선도 잔재(정상 대형주 혼입, 거래정지 아님).
        51 = 정상 (ETF·스팩·우선주, "관리종목" 가설 실측 반증).
        """
        b, r = scanner._is_master_blocked_for_entry(None, {"iscd_stat_cls_code": "58"})
        assert b is False, "G-203-2 — iscd=58 (현재가0 잔재, 정상주 혼입) 통과 의무"
        assert r == ""

        b, r = scanner._is_master_blocked_for_entry(None, {"iscd_stat_cls_code": "51"})
        assert b is False, "G-203-2 — iscd=51 (ETF·스팩·정상소형주) 통과 의무"
        assert r == ""

    # -------------------------------------------------------------------------
    # SAFETY 불변식 — iscd 제거 후에도 위험 종목은 전용 플래그로 여전히 차단.
    # (현재 코드에서도 PASS — Red 유효성상 불변식)
    # -------------------------------------------------------------------------

    def test_g_203_3_trading_halt_still_blocked(self):
        """G-203-3 (SAFETY 유지): 거래정지 (master_raw.trht_yn=Y) → 차단 (불변)."""
        b, r = scanner._is_master_blocked_for_entry({"trht_yn": "Y"}, None)
        assert b is True, "G-203-3 — 거래정지 차단 불변 (trht_yn 전용 플래그)"
        assert "거래정지" in r

    def test_g_203_4_admin_issue_still_blocked(self):
        """G-203-4 (SAFETY 유지): 관리종목 (master_raw.mang_issu_yn=Y) → 차단 (불변)."""
        b, r = scanner._is_master_blocked_for_entry({"mang_issu_yn": "Y"}, None)
        assert b is True, "G-203-4 — 관리종목 차단 불변 (mang_issu_yn 전용 플래그)"
        assert "관리종목" in r

    def test_g_203_5_market_warn_covers_52_53(self):
        """G-203-5 (SAFETY 유지·52/53 커버): 시장경고 (raw.mrkt_warn_cls_code>="01") → 차단.

        투자위험(52)/투자경고(53)는 실측 mrkt_warn_cls_code 로 100% 커버.
        iscd 제거해도 시장경고 계열 보호 유지 (불변).
        """
        b, r = scanner._is_master_blocked_for_entry(None, {"mrkt_warn_cls_code": "02"})
        assert b is True, "G-203-5 — 시장경고(52/53 커버) 차단 불변 (mrkt_warn_cls_code)"
        assert "FHKST" in r and "시장경고" in r

    def test_g_203_6_short_over_covers_59(self):
        """G-203-6 (SAFETY 유지·59 커버): 단기과열 (raw.short_over_yn=Y) → 차단.

        단기과열(59)은 실측 short_over_yn=Y 로 100% 커버. iscd=59 없이도 차단 (불변).
        """
        b, r = scanner._is_master_blocked_for_entry(None, {"short_over_yn": "Y"})
        assert b is True, "G-203-6 — 단기과열(59 커버) 차단 불변 (short_over_yn)"
        assert "단기과열" in r

    def test_g_203_7_invt_caful_sltr_temp_stop_still_blocked(self):
        """G-203-7 (SAFETY 유지): 투자유의/정리매매/임시정지 raw 플래그 각 차단 (불변)."""
        b, r = scanner._is_master_blocked_for_entry(None, {"invt_caful_yn": "Y"})
        assert b is True, "G-203-7 — 투자유의 차단 불변 (invt_caful_yn)"
        assert "투자유의" in r

        b, r = scanner._is_master_blocked_for_entry(None, {"sltr_yn": "Y"})
        assert b is True, "G-203-7 — 정리매매 차단 불변 (sltr_yn, FHKST)"
        assert "정리매매" in r

        b, r = scanner._is_master_blocked_for_entry(None, {"temp_stop_yn": "Y"})
        assert b is True, "G-203-7 — 임시정지 차단 불변 (temp_stop_yn)"
        assert "임시" in r

    def test_g_203_8_iscd_52_alone_unblock_documented_limit(self):
        """G-203-8 (경계·domain 한계 문서화): iscd=52 단독 (mrkt_warn 부재) → 제거 후 통과.

        실측 52 = 유니버스 0건 + 실제 투자위험은 mrkt_warn 동반이라 무해.
        본 케이스는 "iscd 제거로 이 이론적 케이스가 mrkt_warn 의존이 됨"을 명시하는
        문서화 가드 (자문 §반례 참조). 현재 코드는 iscd!="55" 로 차단 → RED.
        """
        # mrkt_warn 등 전용 플래그를 일절 동반하지 않은 순수 iscd=52 단독.
        b, r = scanner._is_master_blocked_for_entry(None, {"iscd_stat_cls_code": "52"})
        assert b is False, (
            "G-203-8 — iscd=52 단독 (mrkt_warn 부재) 제거 후 통과. "
            "실측 52=유니버스 0건이며 실제 투자위험은 mrkt_warn 동반이라 무해 "
            "(domain 자문 §반례: iscd 제거 시 이 이론 케이스는 mrkt_warn 의존)"
        )
        assert r == ""
