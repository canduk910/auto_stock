"""사이클 192 (2026-07-04) — stock_master_daily purge 루프 배치 전환 회귀 가드.

결함 (운영 실증): `purge_old_rows` 가 단일 bulk DELETE (`delete().lt("bas_dd", cutoff)`)
→ supabase-py 기본 `returning="representation"` 로 47,924행 × raw JSONB 응답 반환 시도
→ PostgREST 응답 비대/timeout 예외 → 6/16 도입 이래 전 실행 실패 (515건 누적).

시정 설계 (사이클 175 루프 배치 답습 + 복합 PK 적응): 날짜 슬라이스 루프
  (1) SELECT oldest bas_dd 1건 (protected 제외) → 없으면 drained break
  (2) 그 날짜 전체 DELETE (returning="minimal" + count="exact", protected 제외)
  (3) deleted 누적 → PURGE_MAX_DATE_ITERATIONS cap.

핵심 불변식:
- SELECT / DELETE 양쪽 protected 제외 (SELECT 누락 = never-drain 회귀).
- DELETE returning="minimal" (응답 비대 근본 차단).
- 시그너처 `purge_old_rows(cutoff_date, *, protected_tickers=None)` 불변 (G-150-DAILY-1).
- graceful 보존 + 예외 타입 계측 (사이클 190) + 부분 누적 deleted 반환.

freezegun 미사용 (asyncio.sleep 없음, 사이클 187 교훈 준수 = 무관하나 명시).

Red 상태 (현재 단일 bulk DELETE 코드 기준):
- P-1/P-3/P-4/P-5/P-6 = FAIL (루프/SELECT/상수/부분누적 미구현).
- 시그너처 계약은 cycle150 G-150-DAILY-1 이 담당 (본 파일 미중복).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# mock 헬퍼 — SELECT chain / DELETE chain 분리 형상 (유연 stub)
# ---------------------------------------------------------------------------


def _select_result(data: list) -> MagicMock:
    """SELECT execute 결과 — .data 만 노출."""
    r = MagicMock(name="select_result")
    r.data = data
    return r


def _delete_result(count: int) -> MagicMock:
    """DELETE execute 결과 — .count (returning='minimal' 이라 data 빈 리스트)."""
    r = MagicMock(name="delete_result")
    r.data = []
    r.count = count
    return r


def _make_purge_mock(select_data_seq: list, delete_count_seq: list):
    """purge 루프 배치용 table mock 빌더.

    Args:
        select_data_seq: SELECT iteration 별 row 리스트 (마지막 [] = drained).
        delete_count_seq: DELETE 별 삭제 count (또는 Exception 인스턴스 = raise).

    Returns:
        (table_mock, select_chain, delete_chain) — SELECT/DELETE 체인 분리.
        각 메서드(lt/order/limit/not_.in_ · eq/not_.in_)는 자기 체인 반환 →
        Green 이 어떤 순서로 체이닝해도 흡수.
    """
    select_chain = MagicMock(name="select_chain")
    select_chain.lt.return_value = select_chain
    select_chain.order.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.not_.in_.return_value = select_chain
    select_chain.execute.side_effect = [_select_result(d) for d in select_data_seq]

    delete_chain = MagicMock(name="delete_chain")
    delete_chain.eq.return_value = delete_chain
    delete_chain.not_.in_.return_value = delete_chain
    delete_chain.lt.return_value = delete_chain  # 현재(bulk) 코드 호환 — Red 시 no-op
    delete_chain.execute.side_effect = [
        c if isinstance(c, BaseException) else _delete_result(c)
        for c in delete_count_seq
    ]

    table_mock = MagicMock(name="table_mock")
    table_mock.select.return_value = select_chain
    table_mock.delete.return_value = delete_chain
    return table_mock, select_chain, delete_chain


# =============================================================================
# P-1 (HIGH) — backlog N날짜 → 루프 N iteration + deleted 합산 + drained break
# =============================================================================


class TestP1LoopIteration:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p1_three_dates_loop_and_sum(self) -> None:
        """3날짜 backlog → SELECT 4회(3 데이터 + 1 빈) / DELETE 3회 / deleted=175."""
        from src.db import stock_master_daily as _smd

        table_mock, select_chain, delete_chain = _make_purge_mock(
            select_data_seq=[
                [{"bas_dd": "2025-01-01"}],
                [{"bas_dd": "2025-01-02"}],
                [{"bas_dd": "2025-01-03"}],
                [],  # drained
            ],
            delete_count_seq=[100, 50, 25],
        )

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(date(2025, 11, 15))

        # 날짜 슬라이스 루프 — SELECT 는 drained 확인까지 4회, DELETE 는 데이터 3회
        assert select_chain.execute.call_count == 4, \
            f"SELECT 4회(3 데이터 + drained 1) 의무 (실측 {select_chain.execute.call_count})"
        assert delete_chain.execute.call_count == 3, \
            f"DELETE 3회(날짜별 1회) 의무 (실측 {delete_chain.execute.call_count})"
        assert result["deleted"] == 175, "deleted 합산 정확 (100+50+25)"
        # 반환 계약 보존
        assert set(result.keys()) >= {"deleted", "protected_count", "elapsed_ms"}, \
            "반환 계약 {deleted, protected_count, elapsed_ms} 보존 의무"

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p1_delete_uses_eq_bas_dd(self) -> None:
        """DELETE 가 SELECT 로 얻은 oldest bas_dd 로 .eq 필터 (bulk .lt 폐기)."""
        from src.db import stock_master_daily as _smd

        table_mock, _sc, delete_chain = _make_purge_mock(
            select_data_seq=[[{"bas_dd": "2024-12-31"}], []],
            delete_count_seq=[42],
        )

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            await _smd.purge_old_rows(date(2025, 11, 15))

        # oldest 날짜로 .eq("bas_dd", "2024-12-31") 호출 의무
        delete_chain.eq.assert_called()
        eq_args = delete_chain.eq.call_args
        assert eq_args[0][0] == "bas_dd", "DELETE .eq 컬럼 = bas_dd"
        assert eq_args[0][1] == "2024-12-31", "DELETE 가 SELECT oldest 날짜 사용"


# =============================================================================
# P-2 companion (functional) — DELETE returning="minimal" + count="exact"
# =============================================================================


class TestP2ReturningMinimal:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p2_delete_returning_minimal(self) -> None:
        """DELETE 체인이 returning='minimal' (+count='exact') 로 생성 — 응답 비대 차단."""
        from src.db import stock_master_daily as _smd

        table_mock, _sc, _dc = _make_purge_mock(
            select_data_seq=[[{"bas_dd": "2024-12-01"}], []],
            delete_count_seq=[10],
        )

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            await _smd.purge_old_rows(date(2025, 11, 15))

        table_mock.delete.assert_called()
        call = table_mock.delete.call_args
        rendered = str(call)
        assert "minimal" in rendered, \
            f"DELETE returning='minimal' 의무 (응답 비대 근본 차단), 실측 call={rendered}"
        assert "exact" in rendered, \
            f"DELETE count='exact' 의무 (삭제 수 집계), 실측 call={rendered}"


# =============================================================================
# P-3 (HIGH, never-drain 가드) — SELECT + DELETE 양쪽 protected 제외
# =============================================================================


class TestP3ProtectedBothSides:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p3_protected_applied_on_select_and_delete(self) -> None:
        """protected_tickers 지정 시 SELECT 와 DELETE 양쪽 not_.in_ 적용.

        SELECT 쪽 누락 = protected 만 남은 날짜를 SELECT 가 계속 반환 → 무한 재선택
        (never-drain 회귀). 현재 bulk 코드는 SELECT 자체가 없어 FAIL (Red).
        """
        from src.db import stock_master_daily as _smd

        table_mock, select_chain, delete_chain = _make_purge_mock(
            select_data_seq=[[{"bas_dd": "2025-01-01"}], []],
            delete_count_seq=[100],
        )

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(
                date(2025, 11, 15),
                protected_tickers={"005930", "000660"},
            )

        # SELECT 쪽 protected 제외 (never-drain 가드 핵심)
        select_chain.not_.in_.assert_called()
        s_args = select_chain.not_.in_.call_args
        assert s_args[0][0] == "ticker", "SELECT not_.in_ 컬럼 = ticker"
        assert set(s_args[0][1]) == {"005930", "000660"}, \
            "SELECT 쪽 protected 제외 의무 (누락 = never-drain 회귀)"

        # DELETE 쪽 protected 제외 (사이클 32 R4 절대 보호)
        delete_chain.not_.in_.assert_called()
        d_args = delete_chain.not_.in_.call_args
        assert d_args[0][0] == "ticker", "DELETE not_.in_ 컬럼 = ticker"
        assert set(d_args[0][1]) == {"005930", "000660"}, \
            "DELETE 쪽 protected 제외 의무 (사이클 32 R4)"

        assert result["protected_count"] == 2, "protected_count 정합"

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p3_no_protected_skips_not_in(self) -> None:
        """protected 미지정 시 not_.in_ 미적용 (회귀 보존)."""
        from src.db import stock_master_daily as _smd

        table_mock, select_chain, delete_chain = _make_purge_mock(
            select_data_seq=[[{"bas_dd": "2024-11-01"}], []],
            delete_count_seq=[7],
        )

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(date(2025, 11, 15))

        assert not select_chain.not_.in_.called, "protected 미지정 시 SELECT not_.in_ 미적용"
        assert not delete_chain.not_.in_.called, "protected 미지정 시 DELETE not_.in_ 미적용"
        assert result["protected_count"] == 0
        assert result["deleted"] == 7


# =============================================================================
# P-4 — PURGE_MAX_DATE_ITERATIONS 상수 + 루프 cap
# =============================================================================


class TestP4MaxIterations:
    def test_p4a_constant_exists(self) -> None:
        """PURGE_MAX_DATE_ITERATIONS 모듈 상수 존재 + 양수."""
        import src.db.stock_master_daily as _smd

        const = getattr(_smd, "PURGE_MAX_DATE_ITERATIONS", None)
        assert const is not None, "PURGE_MAX_DATE_ITERATIONS 상수 존재 의무 (Red: 미구현)"
        assert isinstance(const, int) and const > 0, "PURGE_MAX_DATE_ITERATIONS 양수 int 의무"

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p4b_loop_capped_and_returns(self, monkeypatch) -> None:
        """초과 backlog(never-drain 데이터) → cap 만큼 삭제 후 정상 반환 (무한 루프 아님)."""
        import src.db.stock_master_daily as _smd

        const = getattr(_smd, "PURGE_MAX_DATE_ITERATIONS", None)
        assert const is not None, "PURGE_MAX_DATE_ITERATIONS 상수 존재 의무 (Red: 미구현)"

        monkeypatch.setattr(_smd, "PURGE_MAX_DATE_ITERATIONS", 3, raising=False)

        # SELECT 가 매번 데이터 반환(never-drain) — cap 이 루프 종료 유일 경로
        select_chain = MagicMock(name="select_chain")
        select_chain.lt.return_value = select_chain
        select_chain.order.return_value = select_chain
        select_chain.limit.return_value = select_chain
        select_chain.not_.in_.return_value = select_chain
        select_chain.execute.return_value = _select_result([{"bas_dd": "2025-01-01"}])

        delete_chain = MagicMock(name="delete_chain")
        delete_chain.eq.return_value = delete_chain
        delete_chain.not_.in_.return_value = delete_chain
        delete_chain.execute.return_value = _delete_result(10)

        table_mock = MagicMock(name="table_mock")
        table_mock.select.return_value = select_chain
        table_mock.delete.return_value = delete_chain

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(date(2025, 11, 15))

        assert select_chain.execute.call_count == 3, \
            f"cap=3 만큼만 SELECT (실측 {select_chain.execute.call_count})"
        assert delete_chain.execute.call_count == 3, \
            f"cap=3 만큼만 DELETE (실측 {delete_chain.execute.call_count})"
        assert result["deleted"] == 30, "cap 내 부분 삭제 합산 (3 × 10)"


# =============================================================================
# P-5 — 예외 시 graceful (부분 누적 + 예외 타입 계측)
# =============================================================================


class TestP5GracefulPartial:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p5_partial_accumulation_on_mid_exception(self) -> None:
        """2번째 DELETE 예외 → 1번째 삭제분 부분 누적 반환 + 예외 타입 로그."""
        from src.db import stock_master_daily as _smd

        table_mock, _sc, _dc = _make_purge_mock(
            select_data_seq=[
                [{"bas_dd": "2025-01-01"}],
                [{"bas_dd": "2025-01-02"}],
            ],
            delete_count_seq=[120, RuntimeError("boom-delete")],
        )

        with patch.object(_smd, "supabase") as mock_supa, \
                patch.object(_smd, "logger") as mock_logger:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(date(2025, 11, 15))

        assert result["deleted"] == 120, \
            "예외 전 삭제분(120) 부분 누적 반환 의무 (사이클 190 계측 + 부분 보존)"
        assert mock_logger.exception.called, "ERROR 로그(logger.exception) 발화 의무"
        logged = " ".join(str(c) for c in mock_logger.exception.call_args_list)
        assert "RuntimeError" in logged, \
            "예외 타입(RuntimeError) 문자열 계측 의무 (사이클 190 패턴)"

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p5_first_iteration_exception_returns_zero(self) -> None:
        """첫 DELETE 예외 → deleted=0 자연 보존 (기존 '0 반환' 계약)."""
        from src.db import stock_master_daily as _smd

        table_mock, _sc, _dc = _make_purge_mock(
            select_data_seq=[[{"bas_dd": "2025-01-01"}]],
            delete_count_seq=[RuntimeError("boom-first")],
        )

        with patch.object(_smd, "supabase") as mock_supa, \
                patch.object(_smd, "logger") as mock_logger:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(date(2025, 11, 15))

        assert result["deleted"] == 0, "첫 iteration 실패 = deleted 0 자연 보존"
        assert mock_logger.exception.called, "ERROR 로그 발화 의무"


# =============================================================================
# P-6 — 빈 테이블(삭제 대상 0) → SELECT 1회 + DELETE 0회 + deleted=0
# =============================================================================


class TestP6EmptyTable:
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 M2b (Supabase→RDS asyncpg 전환) — supabase 체인 특유 API "
            "(.not_.in_() / .delete(count=, returning=\"minimal\") / .lt / .eq call_args) 를 "
            "단언한다. asyncpg 전환으로 SELECT/DELETE 가 pg.fetchrow/pg.execute 단일 호출 + "
            "ticker <> ALL($::text[]) SQL 절로 대체되어 이 체인 패턴이 부재. 날짜 슬라이스 루프 "
            "+ deleted 누적 + never-drain(P-3) + graceful 부분누적 + cap 불변식은 M2b 신규 가드 "
            "test_cycleM2b_stock_master_daily_pg.py 가 pg 레벨에서 동등 커버."
        ),
    )
    async def test_p6_no_target_rows(self) -> None:
        """삭제 대상 0 → SELECT 1회(즉시 drained) / DELETE 0회 / deleted=0."""
        from src.db import stock_master_daily as _smd

        table_mock, select_chain, delete_chain = _make_purge_mock(
            select_data_seq=[[]],  # 첫 SELECT 부터 빈 결과
            delete_count_seq=[],
        )

        with patch.object(_smd, "supabase") as mock_supa:
            mock_supa.table.return_value = table_mock
            result = await _smd.purge_old_rows(date(2025, 11, 15))

        assert select_chain.execute.call_count == 1, \
            f"빈 테이블 = SELECT 1회 후 drained (실측 {select_chain.execute.call_count})"
        assert delete_chain.execute.call_count == 0, "삭제 대상 0 = DELETE 미호출"
        assert result["deleted"] == 0, "deleted=0"
