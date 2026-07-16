"""사이클 166 — hts_avls 시가총액 단위 결함 시정 회귀 가드 (HIGH 매매 기회 손실).

근본 원인: stock_master.raw.hts_avls (KIS FHKST01010100 시가총액) 실제 단위 = 억원.
코드는 백만원으로 가정 → 100배 어긋남.

운영 DB 실측 (Supabase MCP READ-ONLY, 2026-06-19):
- 대형주 9종목 전수: 실제시총(원) / hts_avls = 96,931,403 ~ 103,473,124 ≈ 10^8 → 1단위 = 1억원
- hts_avls 분포: median=933 (=933억원), max=20,812,752 (삼성전자)
- min_market_cap=1,000억 케이스: 결함상태 hts_avls>=100,000(10조) = 80종목 / 정상 hts_avls>=1,000 = 1,734종목

domain-expert 자문 채택: 억원 기준 통일 / DB 재적재 불필요 / KRX 폴백도 억원 통일.

시정:
- list_by_filter (python-side): `hts_avls * 1_000_000 < min_market_cap` → `* 100_000_000`
- list_paged_by_filter (jsonb): `(min_market_cap + 999_999) // 1_000_000` → `// 100_000_000`

KIS 정본 (사이클 98 G-DOC1): FHKST01010100 inquire_price 응답 `hts_avls` = "HTS 시가총액" (억원 단위).

사이클 205 (2026-07-09, phase 1) 의미 전환: `list_by_filter` 의 시총 컷이 Python-side raw
파싱 → DB-side 생성 컬럼(hts_avls_eok) gte 로 전환. mock 은 실제 DB 필터를 수행하지 않으므로
`TestListByFilterEokUnit` 의 경계값 테스트 3건은 fixture 자체를 gte 통과 rows 만 남기고
주입(`_apply_eok_gte_filter`)하도록 갱신. `TestListPagedByFilterEokUnit`/`TestPathConsistency`
는 `list_paged_by_filter`(별개 함수, 무변경) 또는 pass-through 케이스라 무변경.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공통 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_row(
    ticker: str,
    hts_avls: str = "1000",   # 1,000억 (억원 단위 — 사이클 166 정정)
    acml_tr_pbmn: str = "50000000000",  # 500억 (원 단위)
    excg_dvsn_cd: str = "02",
    nxt_tradable: bool = True,
    name: str = "테스트종목",
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": excg_dvsn_cd,
        "nxt_tradable": nxt_tradable,
        "is_kospi200": False,
        "is_kosdaq150": False,
        "raw": {
            "hts_avls": hts_avls,
            "acml_tr_pbmn": acml_tr_pbmn,
        },
    }


def _run_list_by_filter(rows: list[dict], **kwargs):
    """사이클 M2b — list_by_filter 를 pg.fetch 경유 실행 (rows pass-through)."""
    import src.db.stock_master as sm

    with patch.object(sm, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        return asyncio.run(sm.list_by_filter(**kwargs))


def _run_list_paged_capture(min_market_cap: int) -> dict:
    """사이클 M2b — list_paged_by_filter 의 hts_avls_eok gte 임계를 캡처.

    production 은 pg.fetchval(count_sql, *count_args) + pg.fetch(data_sql, *data_args)
    를 발화하며, WHERE 에 `hts_avls_eok >= $N` 을 넣고 임계를 args 에 바인딩한다.
    임계는 SQL 텍스트("hts_avls_eok")와 args 를 대조해 추출.
    """
    import src.db.stock_master as sm

    captured: dict = {}

    def _record(sql: str, args: tuple):
        s = sql.lower()
        if "hts_avls_eok" in s:
            # WHERE 절 args 에서 hts_avls_eok 임계 추출 — 유일 int gte 대상.
            for a in args:
                if isinstance(a, int) and a not in (0,):
                    # count/data 쿼리 공통 = 첫 int 가 임계 (limit/offset 은 data 쿼리 끝)
                    captured["hts_avls_threshold"] = a
                    break

    async def _fetchval(sql, *args):
        _record(sql, args)
        return 1

    async def _fetch(sql, *args):
        _record(sql, args)
        return [_make_row("000001", hts_avls="1000")]

    with patch.object(sm, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(side_effect=_fetchval)
        pg_mod.fetch = AsyncMock(side_effect=_fetch)
        asyncio.run(sm.list_paged_by_filter(min_market_cap=min_market_cap))

    return captured


def _apply_eok_gte_filter(rows: list[dict], *, min_market_cap: int) -> list[dict]:
    """사이클 205 — DB-side hts_avls_eok gte 필터를 mock 레벨에서 시뮬레이션.

    fixture 의 raw.hts_avls(억원 문자열)로부터 hts_avls_eok 를 파생해 임계 비교 후,
    통과하는 rows 만 남긴다 (= "DB 가 이미 필터링해서 반환한 상태"를 흉내).
    """
    if min_market_cap <= 0:
        return rows
    threshold = (min_market_cap + 99_999_999) // 100_000_000
    out = []
    for row in rows:
        raw = row.get("raw") or {}
        try:
            eok = int(raw.get("hts_avls") or 0)
        except (ValueError, TypeError):
            eok = None
        if eok is None or eok < threshold:
            continue
        out.append(row)
    return out


# ===========================================================================
# G-166-EOK-1 (HIGH) — list_by_filter python-side 경로 억원 단위 정합
# ===========================================================================

class TestListByFilterEokUnit:
    """list_by_filter: hts_avls 억원 단위 비교 (×100_000_000 → 원)."""

    def test_eok_1_one_thousand_eok_passes(self):
        """hts_avls=1000 (1,000억) → min_market_cap=1,000억(=100_000_000_000원) 통과."""
        rows = [_make_row("000001", hts_avls="1000")]  # 1,000억
        result = _run_list_by_filter(rows, min_market_cap=100_000_000_000)

        assert any(r["ticker"] == "000001" for r in result), (
            "hts_avls=1000(억원=1,000억)이 1,000억 임계를 통과해야 함 (억원 단위 정합 — 사이클 166)"
        )

    def test_eok_1_boundary_999_eok_excluded(self):
        """hts_avls=999 (999억) → 1,000억 임계 미달 제외 (DB-side gte 시뮬레이션)."""
        rows = _apply_eok_gte_filter(
            [_make_row("000002", hts_avls="999")],  # 999억
            min_market_cap=100_000_000_000,
        )
        result = _run_list_by_filter(rows, min_market_cap=100_000_000_000)

        assert not any(r["ticker"] == "000002" for r in result), (
            "hts_avls=999(999억)는 1,000억 임계 미달로 제외돼야 함"
        )

    def test_eok_1_boundary_1000_eok_included(self):
        """hts_avls=1000 (정확히 1,000억) → 1,000억 임계 통과 (경계 포함)."""
        rows = [_make_row("000003", hts_avls="1000")]
        result = _run_list_by_filter(rows, min_market_cap=100_000_000_000)

        assert any(r["ticker"] == "000003" for r in result), (
            "hts_avls=1000(정확히 1,000억)은 경계 포함으로 통과해야 함"
        )

    def test_eok_1_ten_trillion_passes(self):
        """hts_avls=100000 (10조) → 1,000억 임계 통과 (결함상태 80종목 영역도 통과 유지)."""
        rows = [_make_row("000004", hts_avls="100000")]  # 10조
        result = _run_list_by_filter(rows, min_market_cap=100_000_000_000)

        assert any(r["ticker"] == "000004" for r in result)

    def test_eok_1_operational_pool_recovery(self):
        """운영 실측 재현: 1,000억~10조 구간 종목이 1,000억 임계에서 통과한다."""
        # 1,000억(=1000) / 3,000억(=3000) / 1조(=10000) — 결함상태 전부 탈락하던 구간
        rows = [
            _make_row("100001", hts_avls="1000"),   # 1,000억
            _make_row("100002", hts_avls="3000"),   # 3,000억
            _make_row("100003", hts_avls="10000"),  # 1조
            _make_row("100004", hts_avls="50000"),  # 5조
        ]
        result = _run_list_by_filter(rows, min_market_cap=100_000_000_000)

        tickers = {r["ticker"] for r in result}
        assert {"100001", "100002", "100003", "100004"} <= tickers, (
            "1,000억~5조 구간 4종목 모두 통과해야 함 (결함상태에서는 전부 탈락 = 후보 풀 95% 축소)"
        )

    def test_eok_1_donchian_500eok_threshold(self):
        """donchian 500억 임계: hts_avls=500(500억) 통과 / 499(499억) 탈락 (DB-side gte 시뮬레이션)."""
        rows = _apply_eok_gte_filter(
            [
                _make_row("200001", hts_avls="500"),  # 500억 — 통과
                _make_row("200002", hts_avls="499"),  # 499억 — 탈락
            ],
            min_market_cap=50_000_000_000,  # 500억
        )
        result = _run_list_by_filter(rows, min_market_cap=50_000_000_000)  # 500억

        tickers = {r["ticker"] for r in result}
        assert "200001" in tickers
        assert "200002" not in tickers

    def test_eok_1_hts_avls_missing_graceful(self):
        """hts_avls 키 미존재 → 생성 컬럼 NULL → DB gte 자동 제외 (시뮬레이션)."""
        rows = _apply_eok_gte_filter(
            [
                {"ticker": "000009", "name": "테스트", "excg_dvsn_cd": "02",
                 "nxt_tradable": True, "is_kospi200": False, "is_kosdaq150": False,
                 "raw": {}},
            ],
            min_market_cap=100_000_000,  # 1억
        )
        result = _run_list_by_filter(rows, min_market_cap=100_000_000)  # 1억

        assert not any(r["ticker"] == "000009" for r in result)


# ===========================================================================
# G-166-EOK-2 (HIGH) — list_paged_by_filter jsonb 경로 억원 단위 정합
# ===========================================================================

class TestListPagedByFilterEokUnit:
    """list_paged_by_filter (UI 페이징): jsonb hts_avls 억원 임계."""

    def _run_paged(self, min_market_cap: int):
        """생성 컬럼 hts_avls_eok gte 임계값을 캡처하기 위한 헬퍼 (사이클 M2b — pg 경유)."""
        return _run_list_paged_capture(min_market_cap)

    def test_eok_2_jsonb_threshold_is_eok(self):
        """min_market_cap=1,000억(원) → jsonb hts_avls 임계 = 1,000 (억원, ÷100_000_000)."""
        captured = self._run_paged(min_market_cap=100_000_000_000)  # 1,000억 원
        assert captured.get("hts_avls_threshold") == 1000, (
            f"jsonb hts_avls 임계가 1000(억원)이어야 함 — "
            f"실제 {captured.get('hts_avls_threshold')} "
            f"(결함상태=100000 백만원 환산)"
        )

    def test_eok_2_jsonb_threshold_500eok(self):
        """min_market_cap=500억(원) → jsonb hts_avls 임계 = 500 (억원)."""
        captured = self._run_paged(min_market_cap=50_000_000_000)  # 500억 원
        assert captured.get("hts_avls_threshold") == 500

    def test_eok_2_jsonb_threshold_ten_trillion(self):
        """min_market_cap=10조(원) → jsonb hts_avls 임계 = 100,000 (억원)."""
        captured = self._run_paged(min_market_cap=10_000_000_000_000)  # 10조 원
        assert captured.get("hts_avls_threshold") == 100_000

    def test_eok_2_zero_no_filter(self):
        """min_market_cap=0 → 시총 필터 미적용 (jsonb gte 미호출)."""
        captured = self._run_paged(min_market_cap=0)
        assert "hts_avls_threshold" not in captured


# ===========================================================================
# G-166-CONSISTENCY (HIGH) — jsonb 경로와 python 경로 단위 정합
# ===========================================================================

class TestPathConsistency:
    """list_by_filter(python) ↔ list_paged_by_filter(jsonb) 단위 일관성."""

    def test_consistency_same_eok_boundary(self):
        """동일 hts_avls=1000(1,000억) + min_market_cap=1,000억 → 양쪽 경로 단위 정합."""
        # list_by_filter 경로 (생성 컬럼 gte, DB-side)
        rows_py = [_make_row("000001", hts_avls="1000")]
        py_result = _run_list_by_filter(rows_py, min_market_cap=100_000_000_000)
        py_pass = any(r["ticker"] == "000001" for r in py_result)

        # list_paged_by_filter 경로 — hts_avls_eok gte 임계값 확인
        captured = _run_list_paged_capture(100_000_000_000)

        # 양쪽 경로 동일 억원 단위 체계 (사이클 166)
        assert py_pass, "list_by_filter 경로 1,000억 통과 실패"
        assert captured.get("hts_avls_threshold") == 1000, "list_paged 경로 임계 단위 불일치 (silent 분기)"
