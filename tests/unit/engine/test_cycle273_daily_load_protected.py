# DEST: /Users/koscom/Projects/auto_stock/tests/unit/engine/test_cycle273_daily_load_protected.py
"""cycle273 D5 — 보유·익일청산 종목 일봉 적재 **강제 포함** (Red).

정본 = `_workspace/red/cycle273d_daily_load_held_inclusion_spec.md` ·
조사 `_workspace/analysis/2026-09-10_cycle273_UD_load_and_ui.md` §D5.

## 무엇이 문제였나 (실측)

같은 테이블에 대해 **지우는 쪽(16:15 purge)은 보유 종목을 보호**하는데
**채우는 쪽(16:00 load)은 보호하지 않는다.** `_is_daily_load_universe` 는
시총 500억 ∧ 거래대금 **10억**(주석의 20억은 문서 드리프트) 자격만 보고,
자격을 못 넘긴 날마다 그 종목의 **그날 봉**을 잃는다.

- `004690`(삼천리, **보유**) — `stock_master_daily` head 2026-09-04,
  09-07/08/09/10 **4거래일 결손**. 지금 시총 5,005억(✓)·거래대금 11.3억(✓)이지만
  일 거래대금이 3.2억~12.6억 사이를 오간다(임계 10억).
- 증분 창이 7영업일이라 **재진입하면 7영업일까지는 자동 복구**된다.
  004690 은 아직 그 창 안이다 — **09-16(화) 전에 배포하면 4일이 메워지고,
  미루면 영구 구멍이 된다.**

## 계약 (spec §3)

C1 ⚠️ **cycle302 에서 의미가 전환됐다.** 원문은 "`vcp_universe_tickers` 에 보호
   종목을 넣지 않는다(분할 backfill 금지)" 였다. 이제 분할 backfill 은 지수 전용이
   아니라 **적재 대상 전부**의 목표 깊이라, 보호 종목도 같은 깊이를 받는다.
   이 파일이 계속 지키는 것은 "보호 종목이 적재 대상에 든다" 이고, 깊이 축의
   계약은 `test_cycle302_backfill_scope_expansion.py` 가 정본이다.
C2 판정 실패 = **fail-open**(현행 집합 유지)
C3 `latest >= today` 신선도 skip 은 **우회하지 않는다**
C4 6자리 숫자 ticker 만 통과
C5 결과 집합은 현행의 **상위집합**(⊇)
C6 registry·scheduler 는 **읽기만**

⚠️ `src/engine/scanner.py` 는 **8영역**이다 — 커밋 시 sha 핀 4곳 절차가 따른다(spec §7).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit

_MCAP_EOK_MIN = 500              # 억원
_TRADE_WON_MIN = 1_000_000_000   # 10억원 (docstring 의 "20억" 은 드리프트 — spec §8 F-D5-a)
_MARKER = "[daily_load_protected_forced]"


def _candle(bas_dd: str = "20260710") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


def _row(ticker, *, is_kospi200=False, is_kosdaq150=False,
         hts_avls=None, acml_tr_pbmn=None, include_raw=True) -> dict:
    row: dict = {"ticker": ticker,
                 "is_kospi200": is_kospi200, "is_kosdaq150": is_kosdaq150}
    if include_raw:
        raw: dict = {}
        if hts_avls is not None:
            raw["hts_avls"] = hts_avls
        if acml_tr_pbmn is not None:
            raw["acml_tr_pbmn"] = acml_tr_pbmn
        row["raw"] = raw
    return row


def _qualifier(ticker: str) -> dict:
    return _row(ticker, hts_avls=str(_MCAP_EOK_MIN + 100),
                acml_tr_pbmn=str(_TRADE_WON_MIN + 5_000_000_000))


def _non_qualifier(ticker: str) -> dict:
    """시총은 넉넉한데 **거래대금이 임계 아래** — 004690 이 어떤 날 빠지는 그 모양."""
    return _row(ticker, hts_avls="5005", acml_tr_pbmn="900000000")   # 9억 < 10억


def _patched_load(rows, *, max_bas_dd=None, count_by_ticker=None,
                  list_all=None, backfill_mock=None, fetch_mock=None):
    max_bas_dd = max_bas_dd or AsyncMock(return_value=None)
    count_by_ticker = count_by_ticker or AsyncMock(return_value=100)
    backfill_mock = backfill_mock or AsyncMock(return_value=[_candle()])
    fetch_mock = fetch_mock or AsyncMock(return_value=[_candle()])
    list_all = list_all or AsyncMock(side_effect=[rows, []])
    return (
        patch.multiple("src.db.stock_master", list_all=list_all),
        patch.multiple("src.db.stock_master_daily",
                       max_bas_dd=max_bas_dd, count_by_ticker=count_by_ticker,
                       upsert_batch=AsyncMock(return_value=1)),
        patch.multiple("src.api.condition",
                       fetch_daily_candles_backfill=backfill_mock,
                       fetch_daily_candles=fetch_mock),
        patch("asyncio.sleep", new=AsyncMock()),
        backfill_mock, fetch_mock,
    )


def _fake_registry(*position_sets):
    strategies = [
        SimpleNamespace(state=SimpleNamespace(positions={t: {} for t in s}))
        for s in position_sets
    ]
    return SimpleNamespace(all=lambda: strategies)


@pytest.fixture
def held(monkeypatch):
    """보유/익일청산 주입 헬퍼 — `_collect_protected_tickers_for_scanner` seam."""
    def _apply(positions=(), pending=()):
        monkeypatch.setattr(scanner, "registry", _fake_registry(positions),
                            raising=False)
        import src.engine.scheduler as sched
        monkeypatch.setattr(sched, "trading_scheduler",
                            SimpleNamespace(_pending_next_day_clear=list(pending),
                                            registry=_fake_registry(positions)),
                            raising=False)
    return _apply


# ===========================================================================
# G-273D-1 (HIGH) — 004690 실사례: 자격 미달 + 보유 → 포함
# ===========================================================================

async def test_g273d_1_held_non_qualifier_is_loaded(held):
    """자격을 못 넘긴 보유 종목이 그날 봉을 잃지 않는다 (004690 회귀).

    현행 = `is_index or is_qualifier` 만 보므로 `total=1`(자격 종목만) → RED.
    """
    held(positions=["004690"])
    rows = [_qualifier("005930"), _non_qualifier("004690")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 2, (
        "보유 종목은 유니버스 자격과 무관하게 적재 후보에 든다. "
        f"실측 total={summary['total']} (현행 1 = RED)"
    )
    # cycle302 — 분기가 아니라 **종목 수**를 잰다(적재 대상이면 분할 backfill 을 탄다).
    assert backfill.await_count + fetch.await_count == 2


async def test_g273d_1b_pending_next_day_clear_is_loaded(held):
    """익일청산 대기 종목도 같은 보호를 받는다(튜플/문자열 두 형태 모두)."""
    held(positions=[], pending=[("003470", "momentum"), "000815"])
    rows = [_qualifier("005930"), _non_qualifier("003470"), _non_qualifier("000815")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()
    assert summary["total"] == 3, f"실측 total={summary['total']}"


# ===========================================================================
# C1 — VCP backfill 오염 금지
# ===========================================================================

async def test_c1_protected_takes_same_backfill_depth(held):
    """보호 종목도 적재 대상이므로 **같은 목표 깊이**를 받는다.

    ⚠️ cycle302 **의미 전환**. 종전 C1 은 "보호의 목적은 오늘 봉이지 이력이 아니다 —
    넣으면 KIS 3회가 샌다" 였고, 그건 분할 backfill 이 지수 전용이던 시절의 비용
    논증이었다. 이제 적재 대상 전부가 같은 깊이를 갖고, 보유 종목은 오히려 멀티데이
    손절·트레일링 복구(`_apply_high_since_buy_from_candles`)가 일봉을 읽는 쪽이라
    얕을 이유가 없다. 비용은 **1회성**이다 — 깊이에 닿으면 증분 1콜로 내려온다
    (가드 `test_cycle302_backfill_scope_expansion.py::G-302-3`).

    🔴 이 테스트가 계속 지키는 것 = **보호 종목이 적재 대상에 든다**(`total == 1`).
    """
    held(positions=["004690"])
    rows = [_non_qualifier("004690")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(
        rows, count_by_ticker=AsyncMock(return_value=10))
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 1
    assert backfill.await_count == 1, (
        f"보호 종목이 목표 깊이를 못 받았다 — backfill 호출 {backfill.await_count}회"
    )
    assert fetch.await_count == 0


# ===========================================================================
# C2 — fail-open
# ===========================================================================

async def test_c2_helper_failure_is_fail_open(monkeypatch):
    """보호 집합 판정이 터져도 **현행 후보 집합 그대로** 진행한다.

    fail-closed(적재 중단)는 P0-1 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이다.
    """
    def _boom():
        raise RuntimeError("registry down")
    monkeypatch.setattr(scanner, "_collect_protected_tickers_for_scanner", _boom,
                        raising=False)
    rows = [_qualifier("005930"), _non_qualifier("004690")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()
    assert summary["total"] == 1, (
        f"판정 실패가 적재를 바꿨다 — 실측 total={summary['total']} (기대: 현행 1)"
    )


# ===========================================================================
# C4 — 6자리 숫자 ticker 만
# ===========================================================================

async def test_c4_non_six_digit_protected_is_ignored(held):
    """ETF·신주인수권·오염 문자열은 강제 포함 대상이 아니다(진입 게이트 비대칭 규약)."""
    held(positions=["ABC123", "00469", "0046900", "", None])
    rows = [_qualifier("005930")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()
    assert summary["total"] == 1, f"실측 total={summary['total']}"


# ===========================================================================
# C3 — 신선도 skip 우회 금지
# ===========================================================================

async def test_c3_freshness_skip_is_not_bypassed(held):
    """이미 오늘 봉이 있으면 보호 종목도 `skipped_fresh` 로 간다.

    보호는 '후보에 넣는다' 까지다 — KIS 를 한 번 더 때리는 권한이 아니다.
    """
    from src.db._kst import today_kst

    held(positions=["004690"])
    rows = [_non_qualifier("004690")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(
        rows, max_bas_dd=AsyncMock(return_value=today_kst()))
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()
    assert summary["total"] == 1
    assert summary["skipped_fresh"] == 1
    assert fetch.await_count == 0 and backfill.await_count == 0


# ===========================================================================
# C5 — 상위집합 (어떤 종목도 새로 배제되지 않는다)
# ===========================================================================

async def test_c5_result_is_superset_of_current(held):
    """보호 집합이 비어 있으면 현행과 **완전히 동일**하다(회귀 방향 0)."""
    held(positions=[], pending=[])
    rows = [_qualifier("005930"), _row("247540", is_kosdaq150=True),
            _non_qualifier("004690"), _row("333333", hts_avls="100",
                                           acml_tr_pbmn="500000000")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()
    assert summary["total"] == 2, (
        f"보호 0건이면 현행 그대로여야 한다 — 실측 {summary['total']}"
    )


async def test_c5b_protected_already_in_universe_is_not_duplicated(held):
    """이미 유니버스 안인 보호 종목은 **한 번만** 적재된다(중복 KIS 호출 금지)."""
    held(positions=["005930"])
    rows = [_qualifier("005930")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()
    assert summary["total"] == 1, f"중복 append — 실측 {summary['total']}"
    # cycle302 — 분기 무관 종목 수 단언(중복 호출 금지가 이 테스트의 주제다).
    assert backfill.await_count + fetch.await_count == 1


# ===========================================================================
# G-273D-2 — `list_all` 조기 break 에도 보호 종목은 살아남는다
# ===========================================================================

async def test_g273d_2_protected_survives_list_all_failure(held):
    """페이징이 예외로 끊겨 보호 종목이 실린 페이지가 통째로 빠져도 적재한다.

    보호의 의미가 '자격 판정을 우회한다' 라면, 자격 판정을 **읽지 못한** 경우에도
    같은 결론이어야 한다.
    """
    held(positions=["004690"])
    p1, p2, p3, sl, backfill, fetch = _patched_load(
        [], list_all=AsyncMock(side_effect=RuntimeError("db down")))
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()
    assert summary["total"] == 1, (
        f"list_all 실패 시 보호 종목이 사라졌다 — 실측 {summary['total']}"
    )
    assert backfill.await_count + fetch.await_count == 1


# ===========================================================================
# G-273D-3 — 관측 마커: **실행당 1행** (종목당 emit 금지, 사이클 237 교훈)
# ===========================================================================

async def test_g273d_3_marker_is_one_line_per_run(held, caplog):
    held(positions=["004690", "003470"], pending=["000815"])
    rows = [_qualifier("005930"), _non_qualifier("004690"),
            _non_qualifier("003470"), _non_qualifier("000815")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with caplog.at_level(logging.INFO, logger="src.engine.scanner"):
        with p1, p2, p3, sl:
            await scanner._stock_master_daily_load_once()

    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith(_MARKER)]
    assert len(lines) == 1, (
        f"실행당 1행이어야 한다(종목당 emit 은 하루 1만 행 폭주 — cycle237). 실측 {lines}"
    )
    assert "protected=3" in lines[0]
    assert "forced_in_universe=3" in lines[0]
    assert "forced_extra=0" in lines[0]


# ===========================================================================
# C6 — 읽기만 한다
# ===========================================================================

async def test_c6_registry_state_is_untouched(held, monkeypatch):
    """보호 집합 수집이 registry/scheduler 상태를 바꾸지 않는다."""
    import src.engine.scheduler as sched

    held(positions=["004690"], pending=[("003470", "momentum")])
    before_positions = {
        id(s): dict(s.state.positions) for s in scanner.registry.all()
    }
    before_pending = list(sched.trading_scheduler._pending_next_day_clear)

    rows = [_non_qualifier("004690"), _non_qualifier("003470")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(rows)
    with p1, p2, p3, sl:
        await scanner._stock_master_daily_load_once()

    after_positions = {
        id(s): dict(s.state.positions) for s in scanner.registry.all()
    }
    assert after_positions == before_positions
    assert list(sched.trading_scheduler._pending_next_day_clear) == before_pending


# ===========================================================================
# G-273D-4 (AST) — 게이트가 세 갈래이고 VCP 는 여전히 index 단독
# ===========================================================================

def test_g273d_4_ast_gate_has_three_branches():
    import ast
    import inspect
    from pathlib import Path

    src = Path(inspect.getfile(scanner)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "_stock_master_daily_load_once")
    body = ast.get_source_segment(src, fn)

    for token in ("is_index", "is_qualifier", "_is_daily_load_universe"):
        assert token in body, f"기존 게이트 요소 소실: {token}"
    assert "_collect_protected_tickers_for_scanner" in body, (
        "보호 집합 헬퍼를 쓰지 않는다 — 새 판정을 발명하지 말고 사이클 32 R4 헬퍼를 재사용한다"
    )
    # cycle302 — 지수 전용 backfill 집합(`vcp_universe_tickers`)은 소멸했다.
    # 깊이 축의 소스 레벨 봉인은 `test_cycle302_backfill_scope_expansion.py::G-302-6`
    # 으로 옮겼다(그쪽이 "집합이 남아 있으면 붉어진다" 를 잰다). 여기서는 이 사이클의
    # 주제인 **적재 대상 게이트 3갈래**만 계속 지킨다.
    assert "vcp_universe_tickers" not in body, (
        "지수 전용 backfill 집합은 cycle302 에서 사라졌다 — 되살리면 "
        "'지수만 깊이를 받는다' 는 거짓이 소스로 돌아온다"
    )
