"""cycle302 (2026-09-18) — 일봉 backfill 대상을 **적재 대상 전부**로 확대 (Red).

## 왜

cycle299·300 이 일봉 깊이를 225 영업일까지 열었는데 backfill **대상**은 지수
(KOSPI200 ∪ KOSDAQ150) 뿐이었다. 2026-09-18 09:37 실측:

| 집합 | 종목 | 225행 이상 | 평균 행수 |
|---|---|---|---|
| 지수 | 348 | 348 (100%) | 232 |
| 비지수 | 1,526 | **0** | 125 |

VCP 는 628 종목을 평가하는데 깊은 일봉을 가진 건 348 뿐이라, 나머지 약 280(45%)은
`effective_ema_long = min(ema_long, 보유 − 20 − 5)` 가 **74·114·121** 로 잡혀
중기↔장기 간격이 10 안팎이 된다(정배열 판정이 동전던지기). 오늘 5단계 탈락 사유에
`50EMA / 150EMA / 121EMA` 가 그대로 찍혔다.

## 무엇을

`_stock_master_daily_load_once` 의 backfill 분기 조건에서 **지수 소속 판정을 뺀다**.
적재 대상(`all_tickers` = index ∪ 시총·거래대금 자격 ∪ 보호)이면 누구나
`existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS` 일 때 225일 분할 backfill 을 탄다.

🔴 **적재 대상 집합 자체(`all_tickers` 구성)는 바뀌지 않는다** — 그걸 바꾸면
유니버스 정책 변경이고 이 사이클의 범위 밖이다(G-302-9 가 봉인).

## 비용 — 무거운 값은 1회성이다

`existing_count >= 225` 가 되면 증분(7일·1콜) 분기로 넘어가고 retention
390 달력일(≈261 영업일)이 225 아래로 떨어뜨리지 않는다.

| | KIS 호출 | 소요 |
|---|---|---|
| 첫 채움(1회) | ≈2,886 | ≈345초 |
| **정상 운영(매일)** | **962** | **≈120초** |

**G-302-3 이 그 안전 근거를 봉인한다** — 전 종목이 target 이상이면 backfill 0건,
전량 증분 7일이다. 첫 채움은 20:30 스케줄이 아니라 수동 trigger 로 돌린다
(`TIME_QUOTE_TOKEN_REFRESH`(20:45) 불변식 창이 20:35 부터라 1분 침범한다).

## 의미가 전환되는 기존 가드 (값만 덮지 않았다 — 계약을 다시 재게 했다)

- `test_cycle172_vcp_universe_backfill.py::SCAN-3/SCAN-3b` — "비 VCP 는 100일"
- `test_cycle206_daily_load_universe.py::UNIVERSE-5` — "vcp_universe = index 만"
- `test_cycle273_daily_load_protected.py::C1` · `G-273D-4` — "보호 종목은 backfill 밖"

## 회귀 가드 매트릭스

전 16 케이스. Red 실측 = **8 failed / 8 passed**(초록 8 은 불변식이라 Red/Green 양쪽 통과).

- G-302-1  (HIGH) 비지수 자격 종목 `count=125` → 225일 분할 backfill      → Red FAIL
- G-302-1b (HIGH) 비지수 자격 종목 `count=10`  → 225일 분할 backfill      → Red FAIL
- G-302-2  (HIGH) 보호(비지수·비자격) 종목 `count=10` → backfill          → Red FAIL
- G-302-3  (HIGH) **수렴 후 무비용** — 전 종목 `count>=225` → backfill 0 · 전량 증분 7일 (불변식)
- G-302-4a 경계 — `target−1` → backfill (지수·비지수 2케이스)             → 비지수만 Red FAIL
- G-302-4b 경계 — `target` → 증분 (재 backfill 금지, 2케이스)             → 불변식
- G-302-5  지수 종목 분기 불변 (회귀 0)                                    → 불변식
- G-302-6  (AST) 분기에 지수 소속 판정 0 + 게이트 3갈래 보존              → Red FAIL
- G-302-6b (AST) 모듈 전체에 `vcp_universe_tickers` 잔존 0                → Red FAIL
- G-302-7  graceful — backfill 예외 → `failed++` 후 다음 ticker            → Red FAIL
- G-302-8  `_DAILY_LOAD_INCREMENTAL_THRESHOLD=50`·`_DAILY_LOAD_FETCH_DAYS=100` 불변
- G-302-8b **상수 관계 핀** — `target > 50` 인 한 100일 분기는 도달 불가
- G-302-9  적재 대상 집합 불변 — 비유니버스·비보호는 여전히 제외          → Red FAIL
- SAFETY-1 (HIGH) 매매 무관 — risk/order_engine/realtime/auth 참조 0

## 매매 안전성

scanner 20:30 일봉 적재 = **매수 진입 전** 데이터 계층이다(사이클 38 명문화).
risk / order_engine / realtime / auth 무접촉 — SAFETY-1 이 재확인한다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit

_MCAP_EOK_MIN = 500              # 억원
_TRADE_WON_MIN = 1_000_000_000   # 10억원


def _candle(bas_dd: str = "20260917") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


def _row(ticker, *, is_kospi200=False, is_kosdaq150=False,
         hts_avls=None, acml_tr_pbmn=None) -> dict:
    raw: dict = {}
    if hts_avls is not None:
        raw["hts_avls"] = hts_avls
    if acml_tr_pbmn is not None:
        raw["acml_tr_pbmn"] = acml_tr_pbmn
    return {"ticker": ticker, "is_kospi200": is_kospi200,
            "is_kosdaq150": is_kosdaq150, "raw": raw}


def _index(ticker: str) -> dict:
    """지수 편입 종목 — 종전에도 backfill 대상이었다."""
    return _row(ticker, is_kospi200=True)


def _qualifier(ticker: str) -> dict:
    """비지수 + 시총·거래대금 자격 통과 — 이 사이클이 새로 편입하는 다수 코호트."""
    return _row(ticker, hts_avls=str(_MCAP_EOK_MIN + 100),
                acml_tr_pbmn=str(_TRADE_WON_MIN + 5_000_000_000))


def _non_qualifier(ticker: str) -> dict:
    """자격 미달 — 보유/익일청산 보호로만 적재 대상에 든다(사이클 273 D5)."""
    return _row(ticker, hts_avls="5005", acml_tr_pbmn="900000000")   # 9억 < 10억


def _patched_load(rows, *, count_by_ticker=None, backfill_mock=None,
                  fetch_mock=None, max_bas_dd=None):
    max_bas_dd = max_bas_dd or AsyncMock(return_value=None)
    count_by_ticker = count_by_ticker or AsyncMock(return_value=100)
    backfill_mock = backfill_mock or AsyncMock(return_value=[_candle()])
    fetch_mock = fetch_mock or AsyncMock(return_value=[_candle()])
    return (
        patch.multiple("src.db.stock_master",
                       list_all=AsyncMock(side_effect=[rows, []])),
        patch.multiple("src.db.stock_master_daily",
                       max_bas_dd=max_bas_dd, count_by_ticker=count_by_ticker,
                       upsert_batch=AsyncMock(return_value=1)),
        patch.multiple("src.api.condition",
                       fetch_daily_candles_backfill=backfill_mock,
                       fetch_daily_candles=fetch_mock),
        patch("asyncio.sleep", new=AsyncMock()),
        backfill_mock, fetch_mock,
    )


def _fake_registry(positions):
    return SimpleNamespace(
        all=lambda: [SimpleNamespace(
            state=SimpleNamespace(positions={t: {} for t in positions}))],
    )


@pytest.fixture
def held(monkeypatch):
    """보유/익일청산 주입 seam — `_collect_protected_tickers_for_scanner` 경유."""
    def _apply(positions=(), pending=()):
        monkeypatch.setattr(scanner, "registry", _fake_registry(positions),
                            raising=False)
        import src.engine.scheduler as sched
        monkeypatch.setattr(
            sched, "trading_scheduler",
            SimpleNamespace(_pending_next_day_clear=list(pending),
                            registry=_fake_registry(positions)),
            raising=False,
        )
    return _apply


def _capture_fetch_days() -> tuple[AsyncMock, list[int]]:
    """`fetch_daily_candles(ticker, days=N)` 의 N 을 순서대로 모은다.

    ⚠️ 호출부가 `days=` **키워드**로 넘기므로 파라미터 이름이 계약이다.
    """
    captured: list[int] = []

    async def _fetch(ticker, days):
        captured.append(days)
        return [_candle()]

    return AsyncMock(side_effect=_fetch), captured


# ===========================================================================
# G-302-1 (HIGH) — 비지수 자격 종목 count=125 → 225일 분할 backfill
# ===========================================================================

async def test_g302_1_non_index_qualifier_mid_depth_takes_backfill():
    """오늘 실측 비지수 평균 깊이(125행)가 곧장 225일 backfill 을 탄다.

    현행(Red) = `is_vcp_universe` 가 False 라 `125 >= 50` 증분 7일로 빠진다 —
    그 종목의 `effective_ema_long` 은 영원히 100 에 머문다.
    """
    rows = [_qualifier("000660")]
    fetch_mock, days = _capture_fetch_days()
    p1, p2, p3, sl, backfill, _ = _patched_load(
        rows, count_by_ticker=AsyncMock(return_value=125), fetch_mock=fetch_mock)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()

    assert backfill.await_count == 1, (
        "비지수 자격 종목도 DB<225 면 분할 backfill 대상이다. "
        f"실측 backfill={backfill.await_count} fetch_days={days} (현행 0 = RED)"
    )
    assert backfill.await_args.kwargs.get("total_days") == \
        scanner._DAILY_LOAD_VCP_BACKFILL_DAYS, (
        "backfill 목표 깊이는 `_DAILY_LOAD_VCP_BACKFILL_DAYS` 단일 출처다. "
        f"실측 kwargs={backfill.await_args.kwargs}"
    )
    assert days == [], f"backfill 종목은 단발 fetch 를 겸하지 않는다 — 실측 {days}"
    assert summary["fetched"] == 1


# ===========================================================================
# G-302-1b (HIGH) — 비지수 자격 종목 count=10 → 225일 분할 backfill
# ===========================================================================

async def test_g302_1b_non_index_qualifier_shallow_takes_backfill():
    """얕은 비지수 종목도 100일이 아니라 225일을 받는다.

    현행(Red) = `count < 50` → `fetch_daily_candles(days=100)` 1콜.
    확대 후 = 첫 밤에 목표 깊이까지 한 번에 채운다(cycle299 G-299-9 의 1-pass 도달).
    """
    rows = [_qualifier("000660")]
    fetch_mock, days = _capture_fetch_days()
    p1, p2, p3, sl, backfill, _ = _patched_load(
        rows, count_by_ticker=AsyncMock(return_value=10), fetch_mock=fetch_mock)
    with p1, p2, p3, sl:
        await scanner._stock_master_daily_load_once()

    assert backfill.await_count == 1, (
        f"실측 backfill={backfill.await_count} fetch_days={days} (현행 0 = RED)"
    )
    assert 100 not in days, (
        "100일 단발 fetch 로 떨어지면 다음 밤에 또 backfill 을 해야 한다. "
        f"실측 fetch_days={days}"
    )


# ===========================================================================
# G-302-2 (HIGH) — 보호 종목도 backfill 대상 (cycle273 C1 의미 전환)
# ===========================================================================

async def test_g302_2_protected_ticker_now_takes_backfill(held):
    """보호(보유) 종목도 적재 대상이므로 깊이를 받는다.

    ⚠️ 이 단언은 `test_cycle273_daily_load_protected.py::C1` 을 **뒤집는다**.
    C1 의 근거("보호의 목적은 오늘 봉이지 이력이 아니다 — KIS 3회가 샌다")는
    backfill 이 지수 전용이던 시절의 비용 논증이었다. 이제는 적재 대상 전부가
    같은 목표 깊이를 갖고, 보유 종목은 오히려 멀티데이 손절·트레일링 복구
    (`_apply_high_since_buy_from_candles`)가 일봉을 읽는 쪽이라 얕을 이유가 없다.
    """
    held(positions=["004690"])
    rows = [_non_qualifier("004690")]
    p1, p2, p3, sl, backfill, fetch = _patched_load(
        rows, count_by_ticker=AsyncMock(return_value=10))
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 1, f"보호 종목 적재 대상 편입 불변 — 실측 {summary['total']}"
    assert backfill.await_count == 1, (
        "보호 종목도 DB<225 면 분할 backfill 을 탄다(C1 의미 전환). "
        f"실측 backfill={backfill.await_count} (현행 0 = RED)"
    )
    assert fetch.await_count == 0


# ===========================================================================
# G-302-3 (HIGH) — 수렴 후 무비용: 정상 운영 호출량이 늘지 않는다
# ===========================================================================

async def test_g302_3_converged_universe_costs_one_call_per_ticker():
    """🔴 이 설계의 안전 근거 — 전 종목이 target 이상이면 backfill 0건이다.

    첫 채움만 무겁고(≈2,886 콜) 그 뒤 매일 밤은 종목당 증분 1콜(7일)이다.
    retention 390 달력일(≈261 영업일)이 보유를 225 아래로 떨어뜨리지 않으므로
    수렴 상태는 유지된다. 이 단언이 붉어지면 "매일 밤 전량 재backfill(churn)"
    이라는 뜻이고 그건 cycle196 이 시정한 바로 그 결함이다.
    """
    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    rows = [
        _index("005930"), _index("247540"),
        _qualifier("000660"), _qualifier("035720"), _qualifier("068270"),
    ]
    fetch_mock, days = _capture_fetch_days()
    p1, p2, p3, sl, backfill, _ = _patched_load(
        rows, count_by_ticker=AsyncMock(return_value=target + 7),
        fetch_mock=fetch_mock)
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 5
    assert backfill.await_count == 0, (
        "수렴한 유니버스에서 분할 backfill 이 발생하면 정상 운영 비용이 3배가 된다. "
        f"실측 backfill={backfill.await_count}"
    )
    assert days == [7] * 5, (
        "종목당 증분 1콜(7일)이 정상 운영의 전부다. "
        f"실측 fetch_days={days}"
    )


# ===========================================================================
# G-302-4 — 경계: target−1 → backfill / target → 증분 (지수·비지수 동일)
# ===========================================================================

@pytest.mark.parametrize("row_factory", [_index, _qualifier],
                         ids=["index", "non_index_qualifier"])
async def test_g302_4a_one_below_target_takes_backfill(row_factory):
    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    p1, p2, p3, sl, backfill, fetch = _patched_load(
        [row_factory("005930")],
        count_by_ticker=AsyncMock(return_value=target - 1))
    with p1, p2, p3, sl:
        await scanner._stock_master_daily_load_once()
    assert backfill.await_count == 1, (
        f"count={target - 1} 은 목표 미달이라 backfill 이다 — 실측 {backfill.await_count}"
    )
    assert fetch.await_count == 0


@pytest.mark.parametrize("row_factory", [_index, _qualifier],
                         ids=["index", "non_index_qualifier"])
async def test_g302_4b_exactly_target_is_incremental(row_factory):
    """경계 포함 — `count == target` 이면 재 backfill 금지(cycle196 churn 차단)."""
    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    fetch_mock, days = _capture_fetch_days()
    p1, p2, p3, sl, backfill, _ = _patched_load(
        [row_factory("005930")], count_by_ticker=AsyncMock(return_value=target),
        fetch_mock=fetch_mock)
    with p1, p2, p3, sl:
        await scanner._stock_master_daily_load_once()
    assert backfill.await_count == 0, (
        f"count == target({target}) 에서 재 backfill 은 churn 이다 — "
        f"실측 {backfill.await_count}"
    )
    assert days == [7], f"실측 fetch_days={days}"


# ===========================================================================
# G-302-5 — 지수 종목 분기 불변 (회귀 0)
# ===========================================================================

async def test_g302_5_index_branch_unchanged():
    """지수 종목의 행위는 한 글자도 바뀌지 않는다(cycle172 SCAN-1/2 계보)."""
    p1, p2, p3, sl, backfill, fetch = _patched_load(
        [_index("005930")], count_by_ticker=AsyncMock(return_value=100))
    with p1, p2, p3, sl:
        await scanner._stock_master_daily_load_once()
    assert backfill.await_count == 1
    assert fetch.await_count == 0


# ===========================================================================
# G-302-6 (AST) — vcp_universe_tickers 소멸 + 분기 조건 `existing_count` 단독
# ===========================================================================

def _load_once_body() -> str:
    src = Path(inspect.getfile(scanner)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "_stock_master_daily_load_once")
    return ast.get_source_segment(src, fn) or ""


def test_g302_6_ast_backfill_gate_has_no_index_membership():
    """backfill 분기가 지수 소속을 묻지 않는다 — 소스 레벨 봉인.

    행위 테스트만 두면 "지수 집합에 전 종목을 넣는" 우회 구현도 초록이 된다.
    그 구현은 이름이 사실과 어긋난 채로 남아 다음 사람을 속인다.
    """
    body = _load_once_body()
    assert "vcp_universe_tickers" not in body, (
        "backfill 대상이 적재 대상 전부가 되면 지수 집합은 소비처 0 인 dead 다 — "
        "쓰지 않는 집합을 남기면 '지수만 깊이를 받는다' 는 거짓을 소스가 계속 말한다"
    )
    assert "is_vcp_universe" not in body, (
        "분기 지역변수도 함께 정리한다(이름이 사실과 어긋난다)"
    )
    # 적재 대상 게이트 3갈래는 그대로다 — 유니버스 정책은 이 사이클의 범위 밖이다.
    for token in ("is_index", "is_qualifier", "_is_daily_load_universe",
                  "_collect_protected_tickers_for_scanner"):
        assert token in body, f"적재 대상 게이트 요소 소실: {token}"


def test_g302_6b_ast_module_has_no_vcp_universe_symbol():
    """모듈 전체에서도 잔존 0 — 부분 삭제로 dead 조각이 남지 않는다."""
    src = Path(inspect.getfile(scanner)).read_text(encoding="utf-8")
    assert "vcp_universe_tickers" not in src, (
        "모듈 어딘가에 집합이 남아 있다 — 전수 삭제"
    )


# ===========================================================================
# G-302-7 — graceful: backfill 예외는 다음 ticker 를 막지 않는다
# ===========================================================================

async def test_g302_7_backfill_failure_is_graceful():
    """사이클 88 G-REJECT 영속 — 확대된 대상에서도 실패는 종목 단위로 격리된다."""
    rows = [_qualifier("000660"), _qualifier("035720")]
    calls: list[str] = []

    async def _boom(ticker, *, total_days):
        calls.append(ticker)
        if ticker == "000660":
            raise RuntimeError("KIS 거부")
        return [_candle()]

    p1, p2, p3, sl, _, fetch = _patched_load(
        rows, count_by_ticker=AsyncMock(return_value=10),
        backfill_mock=AsyncMock(side_effect=_boom))
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()

    assert calls == ["000660", "035720"], f"실측 호출 순서={calls}"
    assert summary["failed"] == 1, f"실측 failed={summary['failed']}"
    assert summary["fetched"] == 1, f"실측 fetched={summary['fetched']}"


# ===========================================================================
# G-302-8 — 상수 불변 + 두 임계의 관계 핀
# ===========================================================================

def test_g302_8_incremental_threshold_value_unchanged():
    assert scanner._DAILY_LOAD_INCREMENTAL_THRESHOLD == 50, (
        "증분 경계 50 은 이 사이클이 건드리지 않는다"
    )
    assert scanner._DAILY_LOAD_FETCH_DAYS == 100, (
        "KIS 1회 호출 한도 100 불변"
    )


def test_g302_8b_deep_target_dominates_incremental_threshold():
    """🔴 **알려진 귀결** — `target > 50` 인 한 100일 단발 분기는 도달 불가다.

    backfill 조건이 `existing_count < target(225)` 이고 그 뒤에 오는
    `elif existing_count < 50` 은 부분집합이라 절대 참이 되지 않는다. 100일 분기는
    **상수 관계에 종속된 구조적 폴백**으로만 남는다(target 을 50 아래로 되돌리면
    다시 살아난다).

    이 핀의 목적 = 그 사실을 소스가 아니라 **계약으로** 드러내는 것이다. 다음 사람이
    "100일 분기가 신규상장을 처리한다" 고 읽고 그 위에 무언가를 얹는 것을 막는다.
    신규상장도 이제 첫 밤에 225일 분할 backfill 을 탄다.
    """
    assert scanner._DAILY_LOAD_VCP_BACKFILL_DAYS > \
        scanner._DAILY_LOAD_INCREMENTAL_THRESHOLD, (
        f"target={scanner._DAILY_LOAD_VCP_BACKFILL_DAYS} 가 "
        f"증분 경계={scanner._DAILY_LOAD_INCREMENTAL_THRESHOLD} 이하로 내려가면 "
        "100일 분기가 되살아난다 — 그때는 이 핀의 설명문을 다시 써야 한다"
    )


# ===========================================================================
# G-302-9 — 적재 대상 집합 불변 (유니버스 정책은 범위 밖)
# ===========================================================================

async def test_g302_9_load_target_set_is_unchanged(held):
    """비유니버스·비보호 종목은 여전히 적재 대상이 아니다.

    이 사이클은 **깊이**만 넓힌다. 대상을 넓히면 그건 유니버스 정책 변경이고
    KIS 호출량·retention 산정이 통째로 달라진다.
    """
    held(positions=["004690"])
    rows = [
        _index("005930"),          # 지수
        _qualifier("000660"),      # 자격
        _non_qualifier("004690"),  # 보호
        _non_qualifier("900110"),  # 어디에도 안 드는 종목 — 제외
    ]
    p1, p2, p3, sl, backfill, _ = _patched_load(
        rows, count_by_ticker=AsyncMock(return_value=10))
    with p1, p2, p3, sl:
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 3, (
        "적재 대상 = index ∪ 자격 ∪ 보호 불변(900110 제외). "
        f"실측 total={summary['total']}"
    )
    assert backfill.await_count == 3, (
        f"적재 대상 전부가 backfill 을 탄다 — 실측 {backfill.await_count} (현행 1 = RED)"
    )


# ===========================================================================
# SAFETY-1 (HIGH) — 매매 무관: risk/order_engine/realtime/auth 무접촉
# ===========================================================================

def test_safety1_scanner_daily_load_touches_no_trading_module():
    body = _load_once_body()
    for forbidden in ("risk", "order_engine", "realtime", "auth",
                      "execute_buy", "execute_sell"):
        assert forbidden not in body, (
            f"일봉 적재는 매수 진입 **전** 데이터 계층이다 — `{forbidden}` 참조 금지"
        )
