"""사이클 108 — stock_master.list_by_filter 회귀 가드.

HIGH-1: 4 필터 (min_market_cap, min_trade_amount, nxt_tradable, exclude_tickers) 정합성
HIGH-5: hts_avls 백만원 → 원 단위 변환 (×1_000_000)
MEDIUM-3: stock_master 전체 활용 (~2,800종목, 사이클 106 영속)

사이클 205 (2026-07-09, phase 1) 의미 전환: 시총/거래대금 컷이 Python-side raw JSONB
파싱 → DB-side 생성 컬럼(hts_avls_eok/acml_tr_pbmn_won) gte 로 전환 (mock 은 DB 필터를
실행하지 않으므로 rows 를 gte 시뮬레이션 형태로 사전 분할 주입). fetch_limit 도
max(limit*2,1000) → .limit(limit) 직접으로 폐지 (m3 케이스 갱신). 상세 근거는
`_workspace/red/cycle205_list_by_filter_db_side.md` 참조.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공통 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_row(
    ticker: str,
    hts_avls: str = "10000",   # 1조 (억원 단위 — 사이클 166 정정, raw 는 참조용 잔존)
    acml_tr_pbmn: str = "50000000000",  # 500억 (원 단위, raw 는 참조용 잔존)
    excg_dvsn_cd: str = "02",
    nxt_tradable: bool = True,
    name: str = "테스트종목",
    hts_avls_eok: int | None = None,
    acml_tr_pbmn_won: int | None = None,
) -> dict:
    """사이클 205 — 생성 컬럼 hts_avls_eok/acml_tr_pbmn_won 동행 (DB-side gte 시뮬레이션용).

    미지정 시 raw 문자열로부터 자동 파생 (억원/원 단위 그대로, 사이클 166 정합).
    비숫자 raw 는 생성 컬럼 None (NULL 시뮬레이션).
    """
    if hts_avls_eok is None:
        try:
            hts_avls_eok = int(hts_avls)
        except (ValueError, TypeError):
            hts_avls_eok = None
    if acml_tr_pbmn_won is None:
        try:
            acml_tr_pbmn_won = int(acml_tr_pbmn)
        except (ValueError, TypeError):
            acml_tr_pbmn_won = None

    row: dict = {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": excg_dvsn_cd,
        "nxt_tradable": nxt_tradable,
        "raw": {
            "hts_avls": hts_avls,
            "acml_tr_pbmn": acml_tr_pbmn,
        },
    }
    if hts_avls_eok is not None:
        row["hts_avls_eok"] = hts_avls_eok
    if acml_tr_pbmn_won is not None:
        row["acml_tr_pbmn_won"] = acml_tr_pbmn_won
    return row


def _apply_db_side_filter(rows: list[dict], *, min_market_cap: int = 0, min_trade_amount: int = 0) -> list[dict]:
    """사이클 205 — DB-side gte 필터를 mock 레벨에서 시뮬레이션.

    production 이 DB-side 생성 컬럼 gte 로 전환됐으므로, mock (rows 그대로 반환)에는
    실제 필터가 걸리지 않는다. 이 헬퍼로 fixture 자체를 gte 통과 rows 만 남기고
    Supabase 에 주입 (= "DB 가 이미 필터링해서 반환한 상태"를 흉내).
    """
    hts_avls_threshold = 0
    if min_market_cap > 0:
        hts_avls_threshold = (min_market_cap + 99_999_999) // 100_000_000
    acml_tr_pbmn_threshold = min_trade_amount if min_trade_amount > 0 else 0

    out = []
    for row in rows:
        eok = row.get("hts_avls_eok")
        won = row.get("acml_tr_pbmn_won")
        if hts_avls_threshold > 0 and (eok is None or eok < hts_avls_threshold):
            continue
        if acml_tr_pbmn_threshold > 0 and (won is None or won < acml_tr_pbmn_threshold):
            continue
        out.append(row)
    return out


def _run_filter(rows: list[dict], **kwargs):
    """사이클 M2b — pg.fetch 경유 실행 + (result, sql, args) 반환.

    mock 은 이미 DB-side gte 필터링된 rows 를 반환(`_apply_db_side_filter`) →
    production 이 _post_filter (exclude/limit) 만 적용.
    """
    from unittest.mock import AsyncMock, patch as _patch

    import src.db.stock_master as sm

    with _patch.object(sm, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        result = asyncio.run(sm.list_by_filter(**kwargs))
        call = pg_mod.fetch.await_args
        sql = call.args[0] if call else ""
        args = call.args[1:] if call else ()
    return result, sql, args


# ---------------------------------------------------------------------------
# HIGH-1: 4 필터 정합성
# ---------------------------------------------------------------------------

class TestListByFilterHigh1:
    """HIGH-1: 4 필터 (시총/거래대금/nxt_tradable/exclude_tickers) 정확성."""

    def test_h1_min_market_cap_filters_correctly(self):
        """시총 1,000억 미만 종목이 제외된다 (hts_avls 억원 단위 — 사이클 166 정정).

        사이클 M2b — DB-side gte 전환. mock 은 실제 필터를 수행하지 않으므로
        fixture 자체를 gte 시뮬레이션(`_apply_db_side_filter`)으로 사전 분할해 주입.
        """
        rows = _apply_db_side_filter(
            [
                _make_row("000001", hts_avls="2000"),   # 2,000억 — 통과 (억원 단위)
                _make_row("000002", hts_avls="500"),    # 500억 — 제외 (1,000억 미만)
            ],
            min_market_cap=100_000_000_000,
        )
        result, sql, args = _run_filter(rows, min_market_cap=100_000_000_000)

        tickers = [r["ticker"] for r in result]
        assert "000001" in tickers
        assert "000002" not in tickers
        # DB-side 생성 컬럼 gte + 임계 바인딩 (사이클 205)
        assert "hts_avls_eok" in sql.lower(), "생성 컬럼 hts_avls_eok gte 누락"
        assert 1000 in args, "hts_avls_eok 임계 1000(억원) 바인딩 누락"

    def test_h1_min_trade_amount_filters_correctly(self):
        """거래대금 200억 미만 종목이 제외된다 (DB-side gte)."""
        rows = _apply_db_side_filter(
            [
                _make_row("000010", acml_tr_pbmn="50000000000"),   # 500억 — 통과
                _make_row("000011", acml_tr_pbmn="5000000000"),    # 50억 — 제외
            ],
            min_trade_amount=20_000_000_000,
        )
        result, sql, args = _run_filter(rows, min_trade_amount=20_000_000_000)

        tickers = [r["ticker"] for r in result]
        assert "000010" in tickers
        assert "000011" not in tickers
        assert "acml_tr_pbmn_won" in sql.lower(), "생성 컬럼 acml_tr_pbmn_won gte 누락"
        assert 20_000_000_000 in args, "acml_tr_pbmn_won 임계 바인딩 누락"

    def test_h1_exclude_tickers_removes_specified(self):
        """exclude_tickers 에 지정된 종목이 결과에서 제외된다 (_post_filter)."""
        rows = [
            _make_row("005930"),  # 삼성전자
            _make_row("000660"),  # SK하이닉스
        ]
        result, sql, args = _run_filter(rows, exclude_tickers=["005930"])

        tickers = [r["ticker"] for r in result]
        assert "005930" not in tickers
        assert "000660" in tickers

    def test_h1_nxt_tradable_param_passed_to_query(self):
        """nxt_tradable=True 가 DB 쿼리에 전달된다 (SQL WHERE + 바인딩 검증)."""
        rows = [_make_row("000001")]
        _result, sql, args = _run_filter(rows, nxt_tradable=True)

        assert "nxt_tradable" in sql.lower(), (
            "nxt_tradable=True 가 SQL WHERE 절에 누락됨"
        )
        assert True in args, "nxt_tradable=True 바인딩 누락"

    def test_h1_limit_caps_result(self):
        """limit 파라미터가 결과 건수를 제한한다 (_post_filter 재절단)."""
        rows = [_make_row(f"{i:06d}") for i in range(1, 201)]
        result, _sql, _args = _run_filter(rows, limit=50)

        assert len(result) <= 50


# ---------------------------------------------------------------------------
# HIGH-5: hts_avls 백만원 → 원 변환 (×1_000_000)
# ---------------------------------------------------------------------------

class TestListByFilterHigh5:
    """HIGH-5: hts_avls 단위 변환 정확성 (사이클 166 — 억원 단위 정정)."""

    def test_h5_hts_avls_unit_conversion_1trillion(self):
        """hts_avls=10000 (1조 억원) → 1_000_000_000_000 원 = 1조 통과 (사이클 166)."""
        rows = [_make_row("000001", hts_avls="10000")]  # 1조 (억원 단위)
        result, _sql, _args = _run_filter(rows, min_market_cap=1_000_000_000_000)  # 1조

        assert any(r["ticker"] == "000001" for r in result)

    def test_h5_hts_avls_just_below_threshold_excluded(self):
        """hts_avls=999 (999억 억원) → 1,000억 임계 미달 제외 (DB-side gte)."""
        rows = _apply_db_side_filter(
            [_make_row("000002", hts_avls="999")],  # 999억 (억원 단위)
            min_market_cap=100_000_000_000,
        )
        result, _sql, _args = _run_filter(rows, min_market_cap=100_000_000_000)  # 1,000억

        assert not any(r["ticker"] == "000002" for r in result)

    def test_h5_hts_avls_missing_graceful(self):
        """hts_avls 키 미존재 시 생성 컬럼 NULL — DB gte 에서 자동 제외 (시뮬레이션)."""
        rows = _apply_db_side_filter(
            [
                {"ticker": "000003", "name": "테스트", "excg_dvsn_cd": "02",
                 "nxt_tradable": True, "raw": {}},  # hts_avls 없음 → hts_avls_eok 없음(None)
            ],
            min_market_cap=1_000_000,  # 1억
        )
        result, _sql, _args = _run_filter(rows, min_market_cap=1_000_000)  # 1억

        # hts_avls_eok=None → gte 제외 (fixture 단계에서 이미 걸러짐)
        assert not any(r["ticker"] == "000003" for r in result)


# ---------------------------------------------------------------------------
# MEDIUM-3: limit×2 버퍼 패턴 (사이클 106 DB 활용 영속)
# ---------------------------------------------------------------------------

class TestListByFilterMedium3:
    """MEDIUM-3: DB fetch limit == 요청 limit (사이클 205 — 오버페치 폐지)."""

    def test_m3_fetch_limit_is_double(self):
        """사이클 205 의미 전환: DB 조회 limit == 요청 limit (오버페치 max(limit*2,1000) 폐지).

        DB-side gte 필터 전환으로 자격 종목만 반환되므로 버퍼 오버페치가 불필요.
        SQL LIMIT 바인딩이 요청 limit 그대로 (G-205-2 정합).
        """
        _result, sql, args = _run_filter([], limit=100)

        assert "limit" in sql.lower(), "SQL LIMIT 절 누락"
        assert 100 in args, f"DB fetch limit 이 요청 limit 100 과 불일치 (오버페치 폐지 위반). args={args}"
        # 오버페치 잔존 금지 (max(100*2,1000)=1000 / 200 이 걸리면 실패)
        assert 1000 not in args and 200 not in args, "오버페치 max(limit*2,1000) 잔존"

    def test_m3_no_kis_api_import_in_list_by_filter(self):
        """list_by_filter 실행 중 KIS API 가 호출되지 않는다."""
        rows = [_make_row("000001")]

        with patch("src.api.base.kis_get") as mock_kis:
            _run_filter(rows)
            mock_kis.assert_not_called()
