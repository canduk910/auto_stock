"""사이클 205 (phase 1) — list_by_filter DB-side 필터 전환 회귀 가드.

배경 (자문 `_workspace/domain_consult/cycle205_universe_selection.md`):
- `list_by_filter` 가 `.order("refreshed_at", desc=True).limit(max(limit*2, 1000))` 로
  fetch → PostgREST 1000행 cap(사이클 175) + Python-side raw 파싱 필터.
- 자격 종목 821(BFB) 중 refreshed_at 최신 버퍼에 든 42~143만 필터 통과 = 나머지 누락.
- refreshed_at 은 종목 품질과 무관한 축 → 자의적 부분집합만 스캔 = selection bias.

phase 1 시정 (보수 — 사용자 결정: DB-side 필터만, 정렬·max_scan_stocks 유지):
1. Python-side 시총/거래대금 컷 → DB 쿼리 `.gte("hts_avls_eok", ceil(min_market_cap/1e8))`
   (min_market_cap>0 시) + `.gte("acml_tr_pbmn_won", min_trade_amount)` (min_trade_amount>0 시).
   list_paged_by_filter(사이클 168) 답습 — 생성 컬럼(migration 039)이 자격만 반환(≤821<1000).
2. sort_by: str | None = None 인자 신규. None = 현행 refreshed_at DESC 유지 (phase 1 정렬 무변경).
3. fetch_limit 폐지: DB 필터 후 .limit(limit) 직접 (오버페치 max(limit*2, 1000) 제거).
4. return_stage_counts=True = 3쿼리 (사이클 170 계약 보존):
   union(index/market/nxt 필터만) / mcap(+시총 gte) / trade(+거래대금 gte = filtered).
5. is_kospi200/is_kosdaq150 DB 필터 유지 + .gte AND 결합.

회귀 가드:
- G-205-1 (HIGH) DB필터 동치: hts_avls_eok/acml_tr_pbmn_won 컬럼 mock → 반환이 현행
  Python-side 결과와 동일 원소 (숫자/비숫자→NULL/null/음수 4케이스, 비숫자·null=양쪽 컷).
- G-205-2 fetch_limit 폐지: .limit(limit) 직접 (오버페치 미발생).
- G-205-3 (HIGH) return_stage_counts 3쿼리: union⊇mcap⊇trade + trade==filtered (G-A-1 답습).
- G-205-4 sort_by=None 정렬 유지: .order("refreshed_at", desc=True) 호출 (phase 1 회귀 0).
- G-205-5 index OR + 시총 gte 양립: is_kospi200/is_kosdaq150 조합에 .gte AND (donchian/VCP).
- G-205-6 (SAFETY) 반환 ticker 형식/필드 불변 + 시그너처 keyword.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fake Supabase 쿼리 체인 — .gte / .eq / .or_ / .order / .limit 호출 전수 캡처
#
# 사이클 168 FakeQuery 클래스 패턴 답습 (다중 .execute() 지원 = 3쿼리 필수).
# 각 쿼리 인스턴스가 자기 필터(gte/eq/or_)를 기록 → seen 에 per-execute 스냅샷 누적.
# 반환 rows 는 factory 에 주입된 고정 rows (DB-side 필터는 Supabase 가 수행하나
# mock 은 rows 를 그대로 반환 → 테스트는 "쿼리에 gte 가 걸렸는지"를 검증).
#
# ★ DB-side 필터 동치(G-205-1)는 rows 를 threshold 미만/이상으로 나눠 주입하고,
#   production 이 gte 임계로 반환 종목을 거르는지(= 어떤 gte col/val 로 쿼리했는지)
#   + rows 를 임계 기준으로 나눈 fixture 로 원소 동치를 검증한다.
# ---------------------------------------------------------------------------


def _make_row(
    ticker: str,
    *,
    hts_avls_eok: int | None = 20000,      # 2조 (억원) — 생성 컬럼
    acml_tr_pbmn_won: int | None = 50_000_000_000,  # 500억 (원) — 생성 컬럼
    hts_avls: str = "20000",               # raw (Python-side 폴백 검증용)
    acml_tr_pbmn: str = "50000000000",
    excg_dvsn_cd: str = "02",
    nxt_tradable: bool = True,
    is_kospi200: bool = True,
    is_kosdaq150: bool = False,
    name: str = "테스트종목",
) -> dict:
    """사이클 205 — 생성 컬럼 hts_avls_eok/acml_tr_pbmn_won 동행 (migration 039)."""
    row: dict = {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": excg_dvsn_cd,
        "nxt_tradable": nxt_tradable,
        "is_kospi200": is_kospi200,
        "is_kosdaq150": is_kosdaq150,
        "raw": {"hts_avls": hts_avls, "acml_tr_pbmn": acml_tr_pbmn},
    }
    # 생성 컬럼은 NULL 가능 (비숫자 raw → 정규식 가드 NULL). None 이면 키 자체 생략.
    if hts_avls_eok is not None:
        row["hts_avls_eok"] = hts_avls_eok
    if acml_tr_pbmn_won is not None:
        row["acml_tr_pbmn_won"] = acml_tr_pbmn_won
    return row


def _make_factory(rows_per_execute, seen: dict):
    """rows_per_execute: 각 .execute() 가 반환할 rows 의 list (3쿼리 시 3개).

    단일 list 를 주면 매 execute 동일 rows 반환.
    seen: {"gte": [(col,val),...], "eq":..., "or_":..., "order":..., "limit":...,
           "executes": N}
    """
    if rows_per_execute and isinstance(rows_per_execute[0], dict):
        # 단일 rows list → 매 execute 동일
        rows_seq = [rows_per_execute]
        single = True
    else:
        rows_seq = list(rows_per_execute)
        single = False

    state = {"idx": 0}

    class FakeQuery:
        def select(self, *a, **k):
            return self

        def gte(self, col, val):
            seen.setdefault("gte", []).append((col, val))
            return self

        def eq(self, col, val):
            seen.setdefault("eq", []).append((col, val))
            return self

        def or_(self, expr):
            seen.setdefault("or_", []).append(expr)
            return self

        def order(self, col, *, desc=False):
            seen.setdefault("order", []).append((col, desc))
            return self

        def limit(self, n):
            seen.setdefault("limit", []).append(n)
            return self

        def range(self, a, b):
            seen.setdefault("range", []).append((a, b))
            return self

        def execute(self):
            seen["executes"] = seen.get("executes", 0) + 1
            if single:
                data = rows_seq[0]
            else:
                i = min(state["idx"], len(rows_seq) - 1)
                data = rows_seq[i]
                state["idx"] += 1
            resp = MagicMock()
            resp.data = data
            resp.count = None
            return resp

    return FakeQuery


async def _fake_to_thread(fn, *args, **kwargs):
    return fn(*args, **kwargs)


def _run(rows_per_execute, seen: dict, **kwargs):
    from src.db import stock_master

    factory = _make_factory(rows_per_execute, seen)
    with patch.object(stock_master, "supabase") as mock_sb, \
         patch("asyncio.to_thread", side_effect=_fake_to_thread):
        mock_sb.table.side_effect = lambda _n: factory()
        return asyncio.run(stock_master.list_by_filter(**kwargs))


# ===========================================================================
# G-205-1 (HIGH) — DB-side 필터 동치: gte 임계 정확성 + Python-side 결과 동일 원소
# ===========================================================================


class TestG205DbSideFilterEquivalence:
    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_1a_market_cap_gte_hts_avls_eok_column(self):
        """min_market_cap>0 → DB 쿼리에 .gte("hts_avls_eok", ceil(min_market_cap/1e8)) 걸림.

        현행: Python-side `hts_avls * 1e8 < min_market_cap` 컷.
        시정: DB-side `.gte("hts_avls_eok", threshold)` — 생성 컬럼(억원) numeric 비교.
        동치: hts_avls(억원) >= ceil(min_market_cap/1e8) ⟺ hts_avls*1e8 >= min_market_cap.
        """
        seen: dict = {}
        rows = [_make_row("000001", hts_avls_eok=2000)]
        _run(rows, seen, min_market_cap=100_000_000_000)  # 1,000억

        gte_cols = [c for c, _ in seen.get("gte", [])]
        assert "hts_avls_eok" in gte_cols, (
            f"min_market_cap>0 → .gte('hts_avls_eok', ...) 의무 (DB-side). 실제 gte: {seen.get('gte')}"
        )
        # 임계 = ceil(100_000_000_000 / 100_000_000) = 1000 (억원)
        threshold = next(v for c, v in seen["gte"] if c == "hts_avls_eok")
        assert threshold == 1000, (
            f"hts_avls_eok 임계 = 1000 (억원) 의무 (사이클 108 Python-side 동치). 실제: {threshold}"
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_1b_trade_amount_gte_acml_tr_pbmn_won_column(self):
        """min_trade_amount>0 → .gte("acml_tr_pbmn_won", min_trade_amount) (원 직접)."""
        seen: dict = {}
        rows = [_make_row("000010", acml_tr_pbmn_won=50_000_000_000)]
        _run(rows, seen, min_trade_amount=20_000_000_000)  # 200억

        gte_cols = [c for c, _ in seen.get("gte", [])]
        assert "acml_tr_pbmn_won" in gte_cols, (
            f"min_trade_amount>0 → .gte('acml_tr_pbmn_won', ...) 의무. 실제 gte: {seen.get('gte')}"
        )
        threshold = next(v for c, v in seen["gte"] if c == "acml_tr_pbmn_won")
        assert threshold == 20_000_000_000, (
            f"acml_tr_pbmn_won 임계 = 원 직접 (환산 없음). 실제: {threshold}"
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_1c_no_gte_when_thresholds_zero(self):
        """min_market_cap=0, min_trade_amount=0 → 시총/거래대금 gte 미발생 (무필터 보존)."""
        seen: dict = {}
        rows = [_make_row("000001")]
        _run(rows, seen, min_market_cap=0, min_trade_amount=0)

        gte_cols = [c for c, _ in seen.get("gte", [])]
        assert "hts_avls_eok" not in gte_cols, "min_market_cap=0 시 hts_avls_eok gte 금지"
        assert "acml_tr_pbmn_won" not in gte_cols, "min_trade_amount=0 시 acml_tr_pbmn_won gte 금지"

    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_1d_python_side_result_unchanged_valid_rows(self):
        """숫자 생성 컬럼 정상 rows: gte 통과 종목 반환 (원소 동치).

        mock 은 rows 를 그대로 반환하나(DB 필터 실제 미실행), production 이 DB-side gte 로
        전환됐다면 Python-side 재필터를 하지 않으므로 gte 임계 이상 rows 는 모두 반환된다.
        fixture 를 전부 임계 이상으로 주입 → 반환 = 입력 전량 (Python-side 컷 잔존 시 실패).
        """
        seen: dict = {}
        rows = [
            _make_row("000001", hts_avls_eok=2000, acml_tr_pbmn_won=50_000_000_000),
            _make_row("000004", hts_avls_eok=3000, acml_tr_pbmn_won=80_000_000_000),
        ]
        result = _run(
            rows, seen,
            min_market_cap=100_000_000_000, min_trade_amount=10_000_000_000,
        )
        tickers = [r["ticker"] for r in result]
        assert tickers == ["000001", "000004"], (
            f"임계 이상 전량 반환 의무 (DB-side 필터 = Python 재컷 없음). 실제: {tickers}"
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_1e_nonnumeric_and_null_generated_col_excluded(self):
        """비숫자/null 생성 컬럼 (migration 039 정규식 가드 NULL): DB gte 에서 자동 제외.

        production 이 DB-side gte 로 전환됐다면, mock 이 NULL 생성 컬럼 rows 를 반환해도
        Supabase 는 실제로 이들을 걸러 반환하지 않는다. mock 은 필터를 흉내내지 못하므로
        본 케이스는 "production 이 hts_avls_eok/acml_tr_pbmn_won 을 gte 대상으로 쓰는지"
        (= raw.hts_avls / raw.acml_tr_pbmn Python-side int 파싱을 안 하는지) 를 검증한다.
        raw 는 비숫자("N/A")로 주입 → Python-side 파싱 잔존 시 hts_avls=0 컷으로 결과가
        달라지지만, DB-side 전환 후엔 raw 미참조라 mock rows 전량 반환.
        """
        seen: dict = {}
        rows = [
            _make_row(
                "000009",
                hts_avls_eok=None,          # 생성 컬럼 NULL (비숫자 raw)
                acml_tr_pbmn_won=None,
                hts_avls="N/A",             # raw 비숫자 → Python-side int 파싱 시 0
                acml_tr_pbmn="N/A",
            ),
        ]
        _run(rows, seen, min_market_cap=100_000_000_000, min_trade_amount=10_000_000_000)

        # DB-side 전환 확정 신호: 시총/거래대금 필터가 생성 컬럼 gte 로만 수행되고
        # raw JSONB Python-side int 파싱 컷 로직이 제거됨.
        gte_cols = [c for c, _ in seen.get("gte", [])]
        assert "hts_avls_eok" in gte_cols and "acml_tr_pbmn_won" in gte_cols, (
            "비숫자/null 컷은 DB-side 생성 컬럼 gte 가 담당 (Python-side raw 파싱 제거 의무). "
            f"실제 gte: {seen.get('gte')}"
        )


# ===========================================================================
# G-205-2 — fetch_limit 폐지: .limit(limit) 직접 (오버페치 max(limit*2,1000) 제거)
# ===========================================================================


class TestG205FetchLimitAbolished:
    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_2a_limit_is_exact_not_doubled(self):
        """DB fetch limit == 요청 limit (오버페치 미발생).

        현행: .limit(max(limit*2, 1000)) → limit=100 시 1000.
        시정: .limit(100) 직접 (DB 필터가 자격 ≤821<1000 반환하므로 오버페치 불요).
        """
        seen: dict = {}
        rows = [_make_row(f"{i:06d}") for i in range(50)]
        _run(rows, seen, limit=300)

        limits = seen.get("limit", [])
        assert limits, "Supabase .limit() 미호출"
        assert 300 in limits, (
            f"fetch limit == 요청 limit(300) 의무 (오버페치 폐지). 실제 limit 호출: {limits}"
        )
        # 오버페치 잔존 금지: max(300*2,1000)=1000 이 걸리면 실패
        assert 1000 not in limits and 600 not in limits, (
            f"오버페치 max(limit*2,1000) 잔존 = fetch_limit 미폐지. 실제: {limits}"
        )


# ===========================================================================
# G-205-3 (HIGH) — return_stage_counts=True 3쿼리 (사이클 170 G-A-1 답습)
# ===========================================================================


class TestG205StageCounts3Queries:
    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_3a_three_executes_and_monotonic(self):
        """return_stage_counts=True → 3쿼리(union/mcap/trade) + union⊇mcap⊇trade + trade==filtered.

        DB-side 전환으로 단일 루프 카운트(사이클 170) 불가 → 3쿼리 구조:
        - union: index/market/nxt 필터만 (mcap/trade gte 없이)
        - mcap: union + 시총 gte
        - trade: mcap + 거래대금 gte (= filtered)
        각 쿼리가 자기 단계 rows 를 반환하도록 mock 이 3회 execute 응답.
        """
        seen: dict = {}
        union_rows = [_make_row(f"{i:06d}") for i in range(10)]          # 10
        mcap_rows = [_make_row(f"{i:06d}") for i in range(10)]           # 10 (시총 전부 통과)
        trade_rows = [_make_row(f"{i:06d}") for i in range(8)]           # 8 (거래대금 2 탈락)

        result = _run(
            [union_rows, mcap_rows, trade_rows], seen,
            min_market_cap=100_000_000_000, min_trade_amount=10_000_000_000,
            return_stage_counts=True,
        )
        assert isinstance(result, tuple), "return_stage_counts=True → tuple 반환 의무"
        filtered, stage = result

        assert seen.get("executes", 0) == 3, (
            f"return_stage_counts=True → 3쿼리 의무 (union/mcap/trade). 실제 execute: {seen.get('executes')}"
        )

        union = stage["union_tickers"]
        mcap = stage["mcap_tickers"]
        trade = stage["trade_tickers"]
        assert set(mcap) <= set(union), "mcap ⊄ union"
        assert set(trade) <= set(mcap), "trade ⊄ mcap"
        assert len(union) >= len(mcap) >= len(trade)
        # trade == filtered (원소·순서 정합, G-A-1 답습)
        assert [r["ticker"] for r in filtered] == trade, "trade_tickers != filtered (순서·원소)"

    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_3b_default_returns_list_not_tuple(self):
        """return_stage_counts 미지정 → list (tuple 아님). 3쿼리 아닌 1쿼리 (회귀 0)."""
        seen: dict = {}
        rows = [_make_row("000001")]
        result = _run(rows, seen, min_market_cap=100_000_000_000)
        assert isinstance(result, list), "미지정 호출자 list 반환 위반"
        assert not isinstance(result, tuple)
        assert seen.get("executes", 0) == 1, (
            f"return_stage_counts=False → 단일 쿼리 의무. 실제 execute: {seen.get('executes')}"
        )


# ===========================================================================
# G-205-4 — sort_by=None 정렬 유지 (phase 1 회귀 0)
# ===========================================================================


class TestG205SortByHook:
    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_4a_sort_by_none_keeps_refreshed_at_desc(self):
        """sort_by=None (기본) → .order("refreshed_at", desc=True) 유지 (phase 1 무변경)."""
        seen: dict = {}
        rows = [_make_row("000001")]
        _run(rows, seen, min_market_cap=0)

        orders = seen.get("order", [])
        assert ("refreshed_at", True) in orders, (
            f"sort_by=None → refreshed_at DESC 유지 의무 (phase 1 정렬 무변경). 실제 order: {orders}"
        )

    def test_g205_4b_sort_by_param_exists_default_none(self):
        """sort_by 인자 존재 + 기본값 None (phase 2 훅 — phase 1 은 None 만 사용)."""
        from src.db import stock_master

        sig = inspect.signature(stock_master.list_by_filter)
        assert "sort_by" in sig.parameters, "sort_by 인자 부재 (phase 2 훅 의무)"
        assert sig.parameters["sort_by"].default is None, "sort_by 기본값 None 아님"


# ===========================================================================
# G-205-5 — index OR + 시총 gte 양립 (donchian/VCP)
# ===========================================================================


class TestG205IndexAndMcapCombine:
    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_5a_kospi200_kosdaq150_or_with_mcap_gte(self):
        """is_kospi200=True + is_kosdaq150=True (OR 합집합) + min_market_cap → or_ AND gte 양립."""
        seen: dict = {}
        rows = [_make_row("000001", is_kospi200=True, is_kosdaq150=True, hts_avls_eok=3000)]
        _run(
            rows, seen,
            is_kospi200=True, is_kosdaq150=True,
            min_market_cap=100_000_000_000,
        )
        # OR 합집합 = .or_ 호출 (사이클 153 영속)
        assert seen.get("or_"), (
            f"둘 다 True → .or_() 합집합 의무 (donchian). 실제 or_: {seen.get('or_')}"
        )
        # 시총 gte 동시 결합
        gte_cols = [c for c, _ in seen.get("gte", [])]
        assert "hts_avls_eok" in gte_cols, (
            f"OR + 시총 gte 양립 의무. 실제 gte: {seen.get('gte')}"
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_5b_kospi200_single_eq_with_mcap_gte(self):
        """is_kospi200=True 단독 + min_market_cap → .eq("is_kospi200", True) AND gte 양립."""
        seen: dict = {}
        rows = [_make_row("000001", is_kospi200=True, hts_avls_eok=3000)]
        _run(rows, seen, is_kospi200=True, min_market_cap=100_000_000_000)

        eq_cols = [c for c, _ in seen.get("eq", [])]
        assert "is_kospi200" in eq_cols, (
            f"is_kospi200 단독 → .eq('is_kospi200', ...) 의무. 실제 eq: {seen.get('eq')}"
        )
        gte_cols = [c for c, _ in seen.get("gte", [])]
        assert "hts_avls_eok" in gte_cols, "index eq + 시총 gte 양립 의무"


# ===========================================================================
# G-205-6 (SAFETY) — 반환 형식/필드 불변 + 시그너처
# ===========================================================================


class TestG205SafetyContract:
    @pytest.mark.xfail(
        strict=False,
        reason=(
        "사이클 M2b (Supabase→RDS asyncpg 전환) — 이 테스트는 supabase 체인 특유 API "
        "(FakeQuery `.gte()/.eq()/.or_()/.order()/.execute()` 호출 캡처 = seen[gte]/executes)를 "
        "단언한다. asyncpg 전환으로 이 체인이 pg.fetch(SQL, *args) 단일 호출 + 생성컬럼 gte "
        "WHERE 절 SQL 로 대체되어 체인 패턴이 부재(supabase 심볼 없음 → AttributeError). "
        "DB-side gte 임계/3쿼리(union/mcap/trade)/OR 합집합/오버페치 폐지 계약은 M2b 신규 가드 "
        "test_cycleM2b_stock_master_pg.py(list_by_filter_generated_column_gte_thresholds / "
        "return_stage_counts_three_queries / stage_counts_matches_plain_filtered / "
        "kospi200_kosdaq150_union_or / read_uses_fetch)가 pg 레벨에서 동등 커버."
        ),
    )
    def test_g205_6a_return_row_fields_unchanged(self):
        """반환 row 형식 불변: ticker/name/excg_dvsn_cd/nxt_tradable/is_kospi200/is_kosdaq150/raw."""
        seen: dict = {}
        rows = [_make_row("005930")]
        result = _run(rows, seen, min_market_cap=0)
        assert result, "결과 비어있음"
        row = result[0]
        for key in ("ticker", "name", "excg_dvsn_cd", "nxt_tradable",
                    "is_kospi200", "is_kosdaq150", "raw"):
            assert key in row, f"반환 row 필드 '{key}' 누락 (매수 후보 소비 계약)"

    def test_g205_6b_signature_preserves_existing_keywords(self):
        """시그너처 keyword 보존: 사이클 108/153/170 인자 전원 유지 + phase 1 신규 sort_by."""
        from src.db import stock_master

        sig = inspect.signature(stock_master.list_by_filter)
        params = sig.parameters
        for key in ("market", "min_market_cap", "min_trade_amount", "exclude_tickers",
                    "nxt_tradable", "is_kospi200", "is_kosdaq150", "limit",
                    "return_stage_counts", "sort_by"):
            assert key in params, f"list_by_filter 인자 '{key}' 부재 (계약 위반)"
