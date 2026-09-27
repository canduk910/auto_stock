"""cycle380 Red (통합) — `list_by_filter(exclude_etf_like=True)` 가 LIMIT **전에** ETF 를 거른다.

명세 = `_workspace/red/cycle380_etf_group_code.md` §4.

왜 실 Postgres 인가: 판정이 SQL(`raw->>'scty_grp_id_cd'` · TRIM/UPPER · 이름 폴백 · COALESCE 이름)로
내려가야 LIMIT 앞에 걸린다. mock 은 SQL 을 실행하지 않으므로 "LIMIT 전" 을 증명하지 못한다.

실측 근거(2026-09-27 운영 DB 읽기 전용): VB·LTV 는 `max_scan_stocks=100` 로 먼저 자르고
(`ORDER BY refreshed_at DESC`) 이름 필터를 뒤에 건다. 09-23 스냅샷에서 VB 통과 주식 82 + ETF 28,
LTV 주식 169 + ETF 50 — 100칸 일부를 ETF 가 차지한 뒤 버려진다.

계약:
- `exclude_etf_like: bool = False` keyword-only. **기본값은 현행과 같다**(ETF 포함) — 전략 밖
  호출자(재무 적재 `scanner._stock_master_financial_load_once`, `tools/validate_turtle_sizing.py`)는
  이번 사이클 무변경.
- True 면 반환 집합 = 「`is_etf_like(row.raw, row.name)` 이 거짓인 행」 을 **정렬 순서대로 LIMIT**
  한 것 — 여기서 `row.name` 은 SELECT 가 돌려주는 COALESCE 이름(`name` → `master_raw.hts_kor_isnm`).
- `return_stage_counts=True` 의 union/mcap/trade 세 쿼리 모두 같은 제외를 건다(최종 == trade 유지).

## HEAD 기준

전부 RED — `exclude_etf_like` 인자 부재(TypeError). 단, `test_default_keeps_legacy_behaviour` 는
현행 보존 가드라 HEAD 에서 이미 초록이다(의도된 비-Red).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_BASE = datetime.fromisoformat("2026-09-23T16:00:00+09:00")

# (ticker, name 컬럼, raw 의 scty_grp_id_cd(None=키 없음), master_raw 이름, 분 오프셋)
# 오프셋이 클수록 최신(refreshed_at DESC 로 먼저 나온다) — ETF 류를 전부 최신에 둔다.
_ETF_LIKE = [
    ("426030", "TIME 미국나스닥100액티브", "EF", None, 100),
    ("153270", "KIWOOM 코스피100", "EF", None, 99),
    ("069500", "KODEX 200", "EF", None, 98),
    ("530001", "QV 샘플 상장지수증권", "EN", None, 97),
    ("530002", "글로벌 샘플 인덱스", " fe ", None, 96),      # 소문자·공백 변형
    ("102110", "TIGER 200", None, None, 95),                  # 코드 없음 → 이름 폴백
    ("114800", "", None, "KODEX 인버스", 94),                 # 코드·name 없음 → master_raw 이름 폴백
    ("122630", "KODEX 레버리지", "", None, 93),               # 빈 코드 → 이름 폴백
]
_STOCK_LIKE = [
    ("037270", "YG PLUS", "ST", None, 50),                   # 이름엔 키워드, 코드는 주식
    ("138930", "BNK금융지주", "ST", None, 49),
    ("005930", "삼성전자", None, None, 48),                   # 코드 없음·키워드 없음
    ("395400", "SK리츠", "RT", None, 47),                     # 범위 밖 그룹 — 현행대로 포함
    ("088980", "맥쿼리인프라", "IF", None, 46),
    ("950160", "코오롱티슈진", "DR", None, 45),
    ("000660", "SK하이닉스", "st", None, 44),                 # 소문자 주식 코드
]
_STOCK_ORDER = [t for t, *_ in _STOCK_LIKE]
_ETF_TICKERS = {t for t, *_ in _ETF_LIKE}


async def _seed(pg, rows, *, hts_avls="10000", acml_tr_pbmn="50000000000", trade_overrides=None):
    trade_overrides = trade_overrides or {}
    for ticker, name, grp, master_name, offset in rows:
        raw = {"hts_avls": hts_avls, "acml_tr_pbmn": trade_overrides.get(ticker, acml_tr_pbmn)}
        if grp is not None:
            raw["scty_grp_id_cd"] = grp
        master_raw = {"hts_kor_isnm": master_name} if master_name else {}
        await pg.execute(
            """
            INSERT INTO stock_master (ticker, name, excg_dvsn_cd, nxt_tradable,
                                      is_kospi200, is_kosdaq150, raw, master_raw, refreshed_at)
            VALUES ($1, $2, '02', false, false, false, $3::jsonb, $4::jsonb, $5)
            """,
            ticker, name, raw, master_raw, _BASE + timedelta(minutes=offset),
        )


@pytest.mark.asyncio
async def test_etf_like_excluded_before_limit(clean_stock_master):
    """LIMIT 7 — ETF 류 8행이 모두 더 최신이어도 주식 7행이 전부 돌아온다."""
    from src.db import stock_master

    await _seed(clean_stock_master, _ETF_LIKE + _STOCK_LIKE)

    out = await stock_master.list_by_filter(limit=len(_STOCK_LIKE), exclude_etf_like=True)

    assert [r["ticker"] for r in out] == _STOCK_ORDER, (
        "SQL 에서 LIMIT 전에 걸러야 한다 — 뒤에서 거르면 최신 ETF 가 칸을 먹고 주식이 밀려난다"
    )


@pytest.mark.asyncio
async def test_small_limit_is_filled_with_stocks_not_etfs(clean_stock_master):
    """VB·LTV 축소판 — LIMIT 3 이 ETF 가 아니라 가장 최신 주식 3개로 찬다."""
    from src.db import stock_master

    await _seed(clean_stock_master, _ETF_LIKE + _STOCK_LIKE)

    out = await stock_master.list_by_filter(
        min_market_cap=50_000_000_000, min_trade_amount=50_000_000_000,
        limit=3, exclude_etf_like=True,
    )

    assert [r["ticker"] for r in out] == _STOCK_ORDER[:3]


@pytest.mark.asyncio
async def test_sql_exclusion_matches_helper_row_by_row(clean_stock_master):
    """차등 검증 — SQL 제외 집합 == 파이썬 헬퍼 판정(같은 raw·같은 COALESCE 이름)."""
    from src.db import stock_master
    from src.engine.etf_like import is_etf_like

    await _seed(clean_stock_master, _ETF_LIKE + _STOCK_LIKE)

    everything = await stock_master.list_by_filter(limit=1000)            # 현행(무제외)
    kept = await stock_master.list_by_filter(limit=1000, exclude_etf_like=True)

    expected = [r["ticker"] for r in everything if not is_etf_like(r["raw"], r["name"])]
    assert [r["ticker"] for r in kept] == expected
    assert set(expected) == set(_STOCK_ORDER), "픽스처 전제: 헬퍼 판정이 표와 같다"


@pytest.mark.asyncio
async def test_stage_counts_all_three_queries_exclude(clean_stock_master):
    """union/mcap/trade 세 단계 모두 ETF 0 · 최종 == trade (G-A-1 유지)."""
    from src.db import stock_master

    # 000660 만 거래대금 미달 → trade 단계에서 빠진다(attrition 이 살아 있는지 확인).
    await _seed(
        clean_stock_master, _ETF_LIKE + _STOCK_LIKE,
        trade_overrides={"000660": "1000000000"},
    )

    filtered, stage = await stock_master.list_by_filter(
        min_market_cap=100_000_000_000, min_trade_amount=20_000_000_000,
        limit=1000, return_stage_counts=True, exclude_etf_like=True,
    )

    for key in ("union_tickers", "mcap_tickers", "trade_tickers"):
        leaked = _ETF_TICKERS & set(stage[key])
        assert not leaked, f"{key} 에 ETF 류가 남았다: {sorted(leaked)}"
    assert set(stage["union_tickers"]) == set(_STOCK_ORDER)
    assert "000660" in stage["mcap_tickers"] and "000660" not in stage["trade_tickers"]
    assert [r["ticker"] for r in filtered] == stage["trade_tickers"]


@pytest.mark.asyncio
async def test_default_keeps_legacy_behaviour(clean_stock_master):
    """기본값(인자 없음)은 현행 그대로 — ETF 도 돌아온다(전략 밖 호출자 무변경).

    현행 보존 가드라 HEAD 에서도 초록이다.
    """
    from src.db import stock_master

    await _seed(clean_stock_master, _ETF_LIKE + _STOCK_LIKE)

    out = await stock_master.list_by_filter(limit=3)

    assert [r["ticker"] for r in out] == ["426030", "153270", "069500"]


# cycle380 검증 보강 — SQL 이름 폴백·코드 공백 처리가 파이썬 헬퍼와 어긋나는 변형(
# BTRIM 이 공백만 지움 / LIKE→ILIKE / '%kw%'→'kw%')을 잡는 탐침 행. 기존 픽스처는
# 코드 없는 ETF 가 전부 키워드로 시작하고 소문자·탭 변형이 없어 세 변형이 살아남았다.
_PROBE = [
    ("252670", "삼성 인버스 2X 상장지수", None, None, 90),   # 키워드가 이름 중간 → ETF(이름 폴백)
    ("900001", "kodex 200", None, None, 89),                  # 소문자 — 헬퍼는 대소문자 구분 → 주식
    ("900002", "Sol라이프", None, None, 88),                  # 'SOL' 소문자 변형 → 주식
    ("900003", "탭코드 샘플", "\tEF\n", None, 87),            # 탭·개행 감싼 EF → ETF
    ("900004", "KODEX 개행 샘플", "\nST\t", None, 86),        # 탭·개행 감싼 ST → 주식(이름 무시)
    ("900005", "레버리지 공백코드", "\t \n", None, 85),       # 공백뿐인 코드 → 이름 폴백 → ETF
    ("900006", "평범한주식", "ST", None, 84),
]


@pytest.mark.asyncio
async def test_sql_name_fallback_and_whitespace_match_helper(clean_stock_master):
    """SQL 판정 == 파이썬 헬퍼(탭·개행 코드, 이름 중간 키워드, 소문자 변형 포함)."""
    from src.db import stock_master
    from src.engine.etf_like import is_etf_like

    await _seed(clean_stock_master, _PROBE)

    everything = await stock_master.list_by_filter(limit=1000)
    kept = await stock_master.list_by_filter(limit=1000, exclude_etf_like=True)

    expected = [r["ticker"] for r in everything if not is_etf_like(r["raw"], r["name"])]
    assert [r["ticker"] for r in kept] == expected
    assert set(expected) == {"900001", "900002", "900004", "900006"}
