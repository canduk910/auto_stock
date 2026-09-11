"""cycle283 Red — 가상 시계로 본 컷오프 20:00 (C14 ⑤ + 자문 요구 ①).

## 재현하려는 사고 (2026-09-11 금)
16:05 배포 재기동 → 16:14 즉시 적재(immediate)가 1,005종목의 **오늘 봉**을 저장 →
18:10 정기가 908종목을 `skipped_fresh` 로 건너뜀. 그 1,005종목의 금요일 거래량이
부분값이다(40종목 대조: 중앙값 +0.51%, 평균 +1.61%, **최대 +13.97%**(현대차)).

## 시장 모델 (자문 요구 ①)
`test_cycle263_daily_load_stub_filter.py` 의 종전 `_sim_kis_response` 는
"15:40 이후면 KIS 가 오늘 **확정봉**을 준다" 고 모델링했다 — 이 사이클이 반증하는
바로 그 명제다. 그런 대역 위에서는 09-11 결함이 **구조적으로 재현 불가능**하다.
여기서는 하루를 세 구간으로 모델링한다:

| 구간 | KIS 가 주는 오늘 봉 | 근거 |
|---|---|---|
| ~09:00 | **껍데기** (O=H=L=C=전일종가, vol=0) | cycle263 실측 |
| 09:00~20:00 | **부분** (OHLC 는 15:30 확정, **거래량만 모자람**) | 09-11 실측 |
| 20:00~ | **최종** | 09-14 애프터마켓 종료 |

⚠️ 마지막 행(20:00 확정)은 아직 **미실측 가설**이다 —
`docs/market-changes-2026-09-14.md` §2 마지막 행이 "KIS 일봉(FHKST03010100)이
애프터마켓 물량을 언제 반영하는가 → 문서에 근거 없음 → **실측 필요**" 라고 적고 있고,
§4-1 이 그 절차(20:05/20:20/20:40/21:00 재조회)를 이미 적어 뒀다. 09-11 실측
(18:10 저장분 vs 18:45 재조회 15/15 일치)은 **변경 전 제도**의 값이라 이관되지 않는다.
어긋나면 `_DAILY_LOAD_TODAY_BAR_CUTOFF` 와 `TIME_STOCK_MASTER_DAILY_LOAD` 를 함께
뒤로 민다 — 부등식 `cutoff ≤ 적재 < 정산` 만 지키면 상수 2개 조정이다.

## 성공 서명
1. 16:14 재기동 immediate 가 **오늘 봉을 저장하지 않는다** (DB 최신 = D-1).
2. 그래서 20:30 정기가 `skipped_fresh` 로 건너뛰지 않는다 (멱등 규칙 `latest >= today`).
3. 20:30 정기가 저장한 오늘 봉의 거래량이 **최종값**이다.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import date, datetime, time as dtime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

import src.engine.scanner as scanner
from src.engine.scanner import KST_TZ as KST

pytestmark = pytest.mark.unit

_TICKER = "005380"          # 현대차 — 09-11 최대 오염(+13.97%) 표본
_SESSIONS = [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10),
             date(2026, 9, 11), date(2026, 9, 14)]
_TODAY = date(2026, 9, 14)  # 09-14(월) = 제도 변경 첫날

#: 09-11 실측 최대 오염을 뒤집은 비율(부분/최종). 중앙값 +0.51% 가 아니라 **최대치**를
#: 쓴다 — 시뮬이 재려는 것은 "평균적으로 얼마나 틀리나" 가 아니라 "부분값이 확정값과
#: **다른 값**임을 필터가 알아보나" 이고, 근소한 차이는 정수 절삭에 묻혀 공허해진다.
_PARTIAL_RATIO = 0.87


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _seq(d: date) -> int:
    """세션 인덱스 대역 — `_SESSIONS` 밖 날짜(과거 패딩)도 받아야 하므로 ordinal 기반."""
    return d.toordinal() - date(2026, 9, 1).toordinal()


def _final_vol(d: date) -> int:
    return 1_000_000 + 1_000 * _seq(d)


def _bar(d: date, *, vol: int, flat: bool = False) -> dict:
    close = 250_000 + 500 * _seq(d)
    o = h = low = close
    if not flat:
        o, h, low = close - 1_000, close + 2_500, close - 2_000
    return {
        "stck_bsop_date": _ymd(d),
        "stck_oprc": str(o), "stck_hgpr": str(h),
        "stck_lwpr": str(low), "stck_clpr": str(close),
        "acml_vol": str(vol), "acml_tr_pbmn": str(close * max(vol, 1)),
    }


def _final_bar(d: date) -> dict:
    return _bar(d, vol=_final_vol(d))


def _partial_bar(d: date) -> dict:
    """OHLC 는 확정값과 **동일**하고 거래량만 모자란 봉 (09-11 실측 형상).

    ⚠️ 여기서 OHLC 를 같게 둔 것은 **현행 제도의 실측**이다(09-11 6종목 전수).
    09-14 부터 애프터마켓이 실시간 연속체결이면 일중 고가/저가가 16:00~20:00 에
    갱신될 수 있고, 그러면 이 모델의 OHLC 도 구간마다 달라져야 한다 — 그 판정은
    09-15(화) 아침에 09-14 봉의 `stck_hgpr`/`stck_lwpr` 를 09-14 15:30 시점 KRX
    정규장 고가/저가와 대조하는 **별도 실측**이다(자문 R3). 참이면 이 사이클의
    영향 범위가 거래량 3전략에서 **가격 축 5전략**으로 넓어진다.
    """
    return _bar(d, vol=int(_final_vol(d) * _PARTIAL_RATIO))


def _stub_bar(d: date) -> dict:
    return _bar(d, vol=0, flat=True)


def _kis_response(days: int) -> list[dict]:
    now = datetime.now(KST)
    today = now.date()
    out: list[dict] = []
    prior = [d for d in _SESSIONS if d < today]
    if today in _SESSIONS:
        if now.time() < dtime(9, 0):
            out.append(_stub_bar(today))
        elif now.time() < dtime(20, 0):
            out.append(_partial_bar(today))
        else:
            out.append(_final_bar(today))
    for d in reversed(prior):
        out.append(_final_bar(d))
    return out[:days]


class _Store:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, dict]] = {}
        self.log: list[tuple[str, tuple[str, ...]]] = []

    def seed(self, ticker: str, candles: list[dict]) -> None:
        for c in candles:
            self.rows.setdefault(ticker, {})[c["stck_bsop_date"]] = c

    async def max_bas_dd(self, ticker: str):
        keys = self.rows.get(ticker) or {}
        if not keys:
            return None
        n = max(keys)
        return date(int(n[:4]), int(n[4:6]), int(n[6:8]))

    async def count_by_ticker(self, ticker: str) -> int:
        return len(self.rows.get(ticker) or {})

    async def upsert_batch(self, ticker: str, candles: list[dict]) -> int:
        self.log.append((
            datetime.now(KST).strftime("%H:%M"),
            tuple(str(c["stck_bsop_date"]) for c in candles),
        ))
        for c in candles:
            self.rows.setdefault(ticker, {})[str(c["stck_bsop_date"])] = c
        return len(candles)

    def head(self, ticker: str) -> dict | None:
        keys = self.rows.get(ticker) or {}
        return keys[max(keys)] if keys else None


def _universe_rows():
    return [{
        "ticker": _TICKER,
        "raw": {"hts_avls": "500000", "acml_tr_pbmn": "500000000000"},
        "is_kospi200": False, "is_kosdaq150": False,
    }]


def _patch(stack: ExitStack, store: _Store, fetch_log: list[str]):
    async def _fetch(_t, days):
        fetch_log.append(datetime.now(KST).strftime("%H:%M"))
        return _kis_response(days)

    stack.enter_context(patch("src.db.stock_master.list_all",
                              new=AsyncMock(return_value=_universe_rows())))
    stack.enter_context(patch("src.db.stock_master_daily.max_bas_dd",
                              new=AsyncMock(side_effect=store.max_bas_dd)))
    stack.enter_context(patch("src.db.stock_master_daily.count_by_ticker",
                              new=AsyncMock(side_effect=store.count_by_ticker)))
    stack.enter_context(patch("src.api.condition.fetch_daily_candles",
                              new=AsyncMock(side_effect=_fetch)))
    stack.enter_context(patch("src.db.stock_master_daily.upsert_batch",
                              new=AsyncMock(side_effect=store.upsert_batch)))
    stack.enter_context(patch("asyncio.sleep", new=AsyncMock()))


def _seeded_store() -> _Store:
    store = _Store()
    store.seed(_TICKER, [_final_bar(d) for d in _SESSIONS if d < _TODAY])
    # 증분 분기(`fetch_days=7`)로 돌게 과거 55행 확보 — 평시 프로덕션 상태
    store.seed(_TICKER, [
        _bar(_SESSIONS[0] - timedelta(days=i + 1), vol=900_000 + i)
        for i in range(55)
    ])
    return store


# ===========================================================================
# 1) 20:00 이전 재기동 immediate 는 오늘 봉을 버린다
# ===========================================================================

@pytest.mark.asyncio
async def test_c283_sim_1_reboot_before_cutoff_drops_todays_partial_bar():
    """09-11 사고 재현 — 16:14 재기동 immediate 가 **부분봉을 박지 않는다**.

    종전 컷오프 15:40 이면 16:14 는 `mode=keep` 이라 부분봉이 그대로 저장되고
    (`latest >= today`) 그날 정기 적재가 전 종목 `skipped_fresh` 로 죽는다.
    """
    store = _seeded_store()
    fetch_log: list[str] = []
    with freeze_time("2026-09-14T16:14:00+09:00"), ExitStack() as stack:
        _patch(stack, store, fetch_log)
        await scanner._stock_master_daily_load_once()

    assert _ymd(_TODAY) not in (store.rows.get(_TICKER) or {}), (
        "16:14 재기동이 오늘 봉을 저장했다 — 그 봉은 **부분 거래량**이고, 그날 정기 "
        "적재는 `latest >= today` 로 skip 되어 영원히 보정되지 않는다 (09-11 사고 재현)"
    )
    assert await store.max_bas_dd(_TICKER) == date(2026, 9, 11), (
        "DB 최신이 D-1 로 남아야 20:30 정기가 skip 되지 않는다"
    )


@pytest.mark.asyncio
async def test_c283_sim_2_regular_load_at_2030_writes_the_final_volume():
    """20:30 정기 적재는 **최종** 거래량을 쓴다."""
    store = _seeded_store()
    fetch_log: list[str] = []
    with freeze_time("2026-09-14T20:30:00+09:00"), ExitStack() as stack:
        _patch(stack, store, fetch_log)
        summary = await scanner._stock_master_daily_load_once()

    assert summary["skipped_fresh"] == 0
    head = store.head(_TICKER)
    assert head is not None and head["stck_bsop_date"] == _ymd(_TODAY)
    assert int(head["acml_vol"]) == _final_vol(_TODAY), (
        f"20:30 이 부분 거래량을 박았다 (실측 {head['acml_vol']}, "
        f"최종 {_final_vol(_TODAY)}, 부분 {int(_final_vol(_TODAY) * _PARTIAL_RATIO)})"
    )


@pytest.mark.asyncio
async def test_c283_sim_3_reboot_then_regular_load_sequence_is_healed():
    """09-11 사고 경로 전체 — 16:14 재기동 **뒤에도** 20:30 이 일을 한다."""
    store = _seeded_store()
    fetch_log: list[str] = []

    with freeze_time("2026-09-14T16:14:00+09:00"), ExitStack() as stack:
        _patch(stack, store, fetch_log)
        await scanner._stock_master_daily_load_once()

    with freeze_time("2026-09-14T20:30:00+09:00"), ExitStack() as stack:
        _patch(stack, store, fetch_log)
        summary = await scanner._stock_master_daily_load_once()

    assert summary["skipped_fresh"] == 0, (
        "재기동이 남긴 오늘 봉 때문에 정기 적재가 skip 됐다 — 09-11 사고의 기전 그대로"
    )
    assert fetch_log == ["16:14", "20:30"], f"두 실행 모두 fetch 의무 (실측 {fetch_log})"
    head = store.head(_TICKER)
    assert int(head["acml_vol"]) == _final_vol(_TODAY)


@pytest.mark.asyncio
async def test_c283_sim_4_force_true_does_not_bypass_the_filter():
    """`force=True` 는 멱등 skip **만** 우회한다 — 필터는 통과하지 못한다.

    수동 `POST /api/stock-master/daily/refresh` 한 번이 그날 정기 적재를 죽이는
    경로를 되살리면 안 된다.
    """
    store = _seeded_store()
    store.seed(_TICKER, [_partial_bar(_TODAY)])  # 이미 오늘 행이 있는 상태
    fetch_log: list[str] = []
    with freeze_time("2026-09-14T16:14:00+09:00"), ExitStack() as stack:
        _patch(stack, store, fetch_log)
        summary = await scanner._stock_master_daily_load_once(True)

    assert summary["skipped_fresh"] == 0, "force 는 멱등 skip 을 우회한다"
    assert fetch_log == ["16:14"]
    # 시드된 부분봉은 DB 에 남아 있다(필터는 **쓰기**만 막는다). 중요한 것은 이 실행이
    # 오늘 봉을 **새로 upsert 하지 않았다**는 것 — `force` 가 필터까지 우회하면
    # 09-11 사고의 수동 판본이 된다(수동 실행 한 번이 그날 정기 적재를 죽인다).
    assert all(_ymd(_TODAY) not in dates for _ts, dates in store.log), (
        f"장중 `force` 실행이 오늘 봉을 upsert 했다 (실측 {store.log})"
    )
    assert any(_ymd(date(2026, 9, 11)) in dates for _ts, dates in store.log), (
        f"전일 봉까지 안 썼다면 필터가 과하게 잘랐다 (실측 {store.log})"
    )


@pytest.mark.parametrize(
    "clock,expect_today_written",
    [
        ("2026-09-14T15:41:00+09:00", False),  # 구 컷오프 직후 — 이제는 폐기
        ("2026-09-14T18:10:00+09:00", False),  # 구 적재 시각 — 이제는 폐기
        ("2026-09-14T19:59:00+09:00", False),  # 애프터마켓 종료 1분 전
        ("2026-09-14T20:00:00+09:00", True),   # 경계 = 보존
        ("2026-09-14T20:30:00+09:00", True),   # 정기 적재
    ],
)
@pytest.mark.asyncio
async def test_c283_sim_5_cutoff_boundary_end_to_end(clock, expect_today_written):
    """경계 전수 — `15:41`·`18:10` 이 **폐기 쪽**이라는 사실이 이 사이클의 핵심이다.

    그 두 항이 없으면 누가 컷오프를 15:40 이나 18:10 으로 되돌려도 나머지 항만으로는
    아무것도 붉어지지 않는다.
    """
    store = _seeded_store()
    fetch_log: list[str] = []
    with freeze_time(clock), ExitStack() as stack:
        _patch(stack, store, fetch_log)
        await scanner._stock_master_daily_load_once()

    written = _ymd(_TODAY) in (store.rows.get(_TICKER) or {})
    assert written is expect_today_written, (
        f"{clock} 실행의 오늘 봉 기록 여부 계약 위반 (기대 {expect_today_written})"
    )
