"""사이클 166 — scanner KRX MKTCAP 폴백 억원 단위 정합 + AST 단위 가드.

사이클116 KRX 폴백은 `mktcap_won // 1_000_000` (원→백만원) 으로 저장했으나,
KIS 경로 hts_avls 가 억원 단위로 확정됨 (사이클 166) → 같은 hts_avls 컬럼에
단위 혼재 발생. KRX 폴백도 `// 100_000_000` (원→억원) 으로 통일.

domain-expert 자문: 단위 혼재는 사일런트 결함 온상 → 발화 빈도와 무관하게 통일.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCANNER_PATH = _REPO_ROOT / "src" / "engine" / "scanner.py"
_STOCK_MASTER_PATH = _REPO_ROOT / "src" / "db" / "stock_master.py"


# ===========================================================================
# G-166-KRX-1 (MEDIUM) — KRX MKTCAP 폴백 억원 환산 (원 → 억원)
# ===========================================================================

class TestKrxFallbackEokConversion:
    """KRX MKTCAP(원) → hts_avls(억원) 환산 정합."""

    def test_krx_1_source_uses_100_million_divisor(self):
        """scanner KRX 폴백 영역이 // 100_000_000 (억원) 으로 환산한다."""
        src = _SCANNER_PATH.read_text(encoding="utf-8")
        # KRX MKTCAP → hts_avls 환산 영역 찾기
        m = re.search(
            r'krx_raw\["hts_avls"\]\s*=\s*mktcap_won\s*//\s*([\d_]+)', src
        )
        assert m is not None, "KRX MKTCAP → hts_avls 환산 코드를 찾지 못함"
        divisor = m.group(1).replace("_", "")
        assert divisor == "100000000", (
            f"KRX 폴백 환산 divisor 가 {divisor} — "
            f"억원 단위(100_000_000)여야 함 (사이클 166, 원→억원)"
        )

    def test_krx_1_no_million_divisor_in_hts_avls_fallback(self):
        """KRX hts_avls 환산 영역에 // 1_000_000 (백만원) 잔존 0건."""
        src = _SCANNER_PATH.read_text(encoding="utf-8")
        # mktcap_won // 1_000_000 패턴 잔존 차단 (백만원 결함)
        bad = re.search(r'mktcap_won\s*//\s*1_000_000\b', src)
        assert bad is None, (
            "KRX MKTCAP 환산에 // 1_000_000 (백만원) 잔존 — "
            "사이클 166 억원 단위 통일 위반"
        )


# ===========================================================================
# G-166-AST-1 (HIGH) — list_by_filter / list_paged_by_filter 단위 정합 AST
# ===========================================================================

class TestStockMasterUnitAst:
    """stock_master.py 시총 비교 영역 억원 단위 정적 검증."""

    def test_ast_1_list_by_filter_python_path_eok(self):
        """list_by_filter python-side hts_avls 비교가 × 100_000_000 (억원→원)."""
        src = _STOCK_MASTER_PATH.read_text(encoding="utf-8")
        # hts_avls * N < min_market_cap 패턴
        m = re.search(
            r'hts_avls\s*\*\s*([\d_]+)\s*<\s*min_market_cap', src
        )
        assert m is not None, (
            "list_by_filter python-side hts_avls * N < min_market_cap 패턴 미발견"
        )
        multiplier = m.group(1).replace("_", "")
        assert multiplier == "100000000", (
            f"list_by_filter hts_avls 곱셈 단위가 {multiplier} — "
            f"억원→원 환산(100_000_000)이어야 함 (사이클 166)"
        )

    def test_ast_1_list_paged_jsonb_threshold_eok(self):
        """list_paged_by_filter jsonb hts_avls 임계가 // 100_000_000 (억원)."""
        src = _STOCK_MASTER_PATH.read_text(encoding="utf-8")
        # (min_market_cap + ...) // N 또는 min_market_cap // N 패턴
        m = re.search(
            r'min_market_cap[^/\n]*//\s*([\d_]+)', src
        )
        assert m is not None, (
            "list_paged_by_filter jsonb 임계 환산 패턴 미발견"
        )
        divisor = m.group(1).replace("_", "")
        assert divisor == "100000000", (
            f"list_paged_by_filter jsonb 임계 divisor 가 {divisor} — "
            f"억원 단위(100_000_000)여야 함 (사이클 166)"
        )

    def test_ast_1_no_million_unit_in_hts_avls_compare(self):
        """stock_master.py 에 hts_avls × 1_000_000 / // 1_000_000 (백만원) 잔존 0건."""
        src = _STOCK_MASTER_PATH.read_text(encoding="utf-8")
        # hts_avls * 1_000_000 (백만원 환산) 잔존 차단
        bad_mul = re.search(r'hts_avls\s*\*\s*1_000_000\b', src)
        assert bad_mul is None, (
            "stock_master.py 에 hts_avls * 1_000_000 (백만원) 잔존 — 사이클 166 위반"
        )
        # min_market_cap // 1_000_000 (백만원 환산) 잔존 차단
        bad_div = re.search(r'min_market_cap[^/\n]*//\s*1_000_000\b', src)
        assert bad_div is None, (
            "stock_master.py 에 min_market_cap // 1_000_000 (백만원) 잔존 — 사이클 166 위반"
        )


# ===========================================================================
# G-166-DOC 영역 — 사이클 167 폐기 (헬퍼 3개 dead code 제거).
# 사이클 166 시점 헬퍼 존재 + docstring 억원 명문화 가드 (TestHelperUnitDocumentation)
# 는 사이클 167 dead code 폐기로 의도 무효화 → 제거. 폐기 영구 가드는
# tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py 로 이관.
# ===========================================================================
