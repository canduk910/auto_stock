"""cycle299 (2026-09-17) — VCP 일봉 backfill target 120 → 225 영업일 확장.

목적
====
`src/engine/scanner.py::_DAILY_LOAD_VCP_BACKFILL_DAYS` 를 120 → 225 로 올려
실효 장기선이 정확히 200 이 되는 225 영업일을 DB 에 쌓는다. KIS `FHKST03010100` 의 100일은
**호출당** 한도라 `condition.fetch_daily_candles_backfill` 이 이미 윈도우
`ceil(225/100)=3` 개로 쪼개 순차 호출·병합한다 — 총량을 막던 것은 우리 상수뿐이다.

🔴 이 상수는 `src/db/stock_master_daily.py::DAILY_RETENTION_DAYS` (230 → 390) 와
**반드시 함께 간다.** 커플링 부등식은 자매 파일
`tests/unit/db/test_cycle299_retention_expansion.py` 의 G-299-3a/3b/3c 가 잰다.

⚠️ 이 사이클은 매매 행위를 바꾸지 않는다 — VCP `prepare()` 는 여전히 100일만 읽는다
(봉인 = 자매 파일 G-299-7a/7b).

가드 매트릭스 (이 파일)
======================
- G-299-2  _DAILY_LOAD_VCP_BACKFILL_DAYS == 225                          → Red FAIL
- G-299-5  VCP + count=224 (target−1) → backfill(total_days=225) 하드코딩  → Red FAIL
- G-299-4  VCP + count = retention 보유 최대치 → 재backfill 금지 + 증분     → 불변식(커플링)
- G-299-6  count == 상수 → strict-`<` False → 증분 (경계)                 → 불변식
- G-299-8  SAFETY — scanner 변경이 상수값에 국한 (매매/구독 hot path 무접촉) → 불변식
- G-299-9  1회 backfill 실도달 ≥ target (한 밤에 채운다)                  → 불변식

mock 구성은 사이클 172/196 을 100% 답습한다
(`list_all` side_effect + `max_bas_dd`/`count_by_ticker`/`fetch_*`/`upsert_batch`
+ `asyncio.sleep`). `max_bas_dd=None` = "fresh 아님 → 적재 진행"
(사이클 176/180 교훈 — 절대 날짜 하드코딩 회피).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner
from tests.unit.db.test_cycle299_retention_expansion import trading_days_in

pytestmark = pytest.mark.unit


def _vcp_candle(bas_dd: str = "20260620") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


_KOSPI200_ROW = {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False}


async def _run_load_with_count(existing_count: int):
    """`_stock_master_daily_load_once` 1종목 실행 → (backfill_mock, captured_days, summary).

    사이클 172/196 mock 구성 답습. VCP universe 종목(is_kospi200=True) 하나만 흘린다.
    """
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[[_KOSPI200_ROW], []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),  # fresh 아님 → 적재 진행
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=existing_count),
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_fetch),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    return backfill_mock, captured_days, summary


# ---------------------------------------------------------------------------
# G-299-2 — 상수 == 225
# ---------------------------------------------------------------------------
def test_g299_2_backfill_days_constant():
    """_DAILY_LOAD_VCP_BACKFILL_DAYS == 225 (실효 장기선이 정확히 200 이 되는 영업일 수).

    무엇을 재는 테스트인가: VCP universe 종목의 일봉 적재 목표 깊이.
    왜 225 인가: `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)` 라
    보유 225 에서 실효 장기선이 정확히 200 이 된다(220 이면 195 에 그친다). KIS 총량 제한은
    존재하지 않는다(`fetch_daily_candles_backfill` 이 100일 윈도우 3개로 쪼갠다).

    Red (120): FAIL.  Green (225): PASS.
    """
    assert scanner._DAILY_LOAD_VCP_BACKFILL_DAYS == 225, (
        "cycle299 — 실효 장기선 200(= 보유 225 영업일) 확보. "
        "🔴 db.stock_master_daily.DAILY_RETENTION_DAYS(=390) 와 반드시 함께 간다"
    )


# ---------------------------------------------------------------------------
# G-299-5 — VCP + count=224 (target−1) → backfill(total_days=225)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g299_5_vcp_target_minus_one_triggers_backfill():
    """VCP + count_by_ticker=224 (target−1) → backfill 호출 + total_days=225.

    무엇을 재는 테스트인가: 새 target 바로 아래 한 칸에서 backfill 분기가 실제로 켜지고,
    끌어오는 총량이 새 목표치라는 것.

    `total_days` 는 **하드코딩 225** 로 단언한다 — 상수를 참조하면 Red(120) 에서도
    `total_days == _DAILY_LOAD_VCP_BACKFILL_DAYS` 가 참이 되어 Red 가 무효가 된다
    (사이클 196 B-3 가 세운 규약).

    Red (120): 224 >= 120 → 증분 전환 → backfill await_count == 0 → FAIL.
    Green (225): 224 < 225 → backfill(total_days=225) → PASS.
    """
    backfill_mock, _days, summary = await _run_load_with_count(224)

    assert backfill_mock.await_count == 1, (
        "VCP count 224 < 225 → backfill 호출 의무. "
        "Red(120): 224 >= 120 → 증분 → await_count==0 = FAIL"
    )
    assert backfill_mock.call_args.kwargs.get("total_days") == 225, (
        "backfill total_days=225 의무 (하드코딩 — 상수 참조 시 Red 무효). "
        "Red(120): total_days=120 → FAIL"
    )
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# G-299-4 (수렴 / 커플링) — retention 보유 최대치에서 재backfill 하지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g299_4_converges_at_retained_maximum():
    """count = retention 이 보유 가능한 영업일(정상상태 최대치) → backfill 0 + 증분 7일.

    무엇을 재는 테스트인가: **churn 종결의 핵심 증명.** DB 가 물리적으로 가질 수 있는
    최대 행 수에 도달했을 때 backfill 분기가 꺼져야 한다. 꺼지지 않으면 `existing_count`
    가 target 에 영원히 못 닿아 매일 밤 전량 재backfill 이다 — 사이클 192 → 196 결함.

    count 를 **프로덕션 retention 상수에서 동적으로 산출**한다
    (`trading_days_in(DAILY_RETENTION_DAYS)`, 앵커 = 사이클196 실측 230cal ⇄ 154영업일):
      - Red   (retention 230 / target 120): count=154, 154 >= 120 → 증분 → PASS
      - Green (retention 390 / target 225): count=261, 261 >= 225 → 증분 → PASS
      - 반쪽 (retention 230 / target 225): count=154, 154 < 225 → backfill → FAIL ✅
      - 반쪽 (retention 390 / target 120): count=261 → 증분 → PASS (무해 방향)
    즉 이 테스트의 일은 **두 상수 중 retention 만 뒤처진 Green 을 붉게 만드는 것**이다.

    사이클 196 B-2 는 같은 의도를 count=154 리터럴로 고정했다. 그 리터럴은 Green 에서
    `154 < 225` 가 되어 의미가 뒤집히므로 별도로 261 로 옮긴다(의미 전환).
    """
    from src.db.stock_master_daily import DAILY_RETENTION_DAYS

    retained_max = trading_days_in(DAILY_RETENTION_DAYS)
    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    assert retained_max >= target, (
        f"전제 위반 — retention {DAILY_RETENTION_DAYS}cal 보유 최대치 {retained_max} 영업일이 "
        f"target {target} 보다 작다 (커플링 상세 진단은 G-299-3c)"
    )

    backfill_mock, captured_days, summary = await _run_load_with_count(retained_max)

    assert backfill_mock.await_count == 0, (
        f"보유 최대치 {retained_max} >= target {target} → 재backfill 금지 (수렴). "
        f"retention 만 뒤처지면 여기서 붉어진다"
    )
    assert 7 in captured_days, "보유 최대치 → 증분 모드 (fetch_daily_candles days=7)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# G-299-6 (경계 불변식) — count == 상수 → strict-`<` False → 증분
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g299_6_boundary_count_equals_target_incremental():
    """count_by_ticker == _DAILY_LOAD_VCP_BACKFILL_DAYS → 재backfill 금지 (경계).

    무엇을 재는 테스트인가: 분기 조건이 strict-`<` 라는 것 (== 는 backfill 아님).
    상수에서 동적 취득하므로 Red(count=120)/Green(count=225) 양쪽 PASS 하는 불변식이고,
    누군가 `<` 를 `<=` 로 바꾸면 target 값과 무관하게 붉어진다 — 그 변경 하나로
    수렴점이 사라져 영구 churn 이 된다.

    사이클 196 B-4 의 계승 (값만 상수를 따라 움직인다).
    """
    threshold = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS  # 120(Red) / 225(Green) 동적

    backfill_mock, captured_days, summary = await _run_load_with_count(threshold)

    assert backfill_mock.await_count == 0, (
        "existing == threshold → strict-< False → 재backfill 금지 (경계 불변식)"
    )
    assert 7 in captured_days, "경계값(>= 50) → 증분 (days=7)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# G-299-9 (1회 도달) — 한 번의 backfill 이 target 을 넘는다
# ---------------------------------------------------------------------------
# 1회 backfill 이 도달하는 달력일은 `condition.fetch_daily_candles_backfill` 의 깊이 환산이
# 정한다. 종래 `int(n*7/5)+10` 은 영업일당 달력일을 1.40(주말만)으로 가정해 target 이
# 커질수록 과소 도달했다 — target 225 에서 실도달 217 영업일(8 부족)이라 하루 1 영업일씩
# 8밤을 더 돌아야 채워졌다. cycle299 가 깊이에 휴일 보정을 비례로 얹어 **한 번에 넘긴다**:
#     사이클196 수식  target 225 → 325cal → 217 영업일 → 8 부족
#     cycle299 수식   target 225 → 347cal → 232 영업일 → 7 잉여
# 🔴 stride(윈도우 간격)는 7/5 그대로다 — 그것을 키우면 앞 윈도우가 KIS 100건 한도로
# 닿는 바닥보다 다음 윈도우 머리가 아래로 내려가 **사이에 구멍**이 생긴다.
#
# 이 가드의 계약은 **"모자라지 않는다"** 다(종래 "부족분 ≤ 10" 보다 강하다). 부족분 상한은
# 전이 기간을 유계로 묶는 약한 형태였고, 전이 자체가 없어진 지금은 그 단언이 음수에서도
# 통과해 공허해진다. 그래서 부등식을 뒤집어 잠근다.
MIN_ONE_PASS_SURPLUS_TRADING = 0


@pytest.mark.asyncio
async def test_g299_9_one_pass_reaches_target(monkeypatch):
    """1회 backfill 의 실도달 영업일 ≥ target — 전이 기간 없이 한 밤에 채운다.

    무엇을 재는 테스트인가: "한 번 긁으면 목표에 닿는가". 닿지 않으면 그만큼의 밤 동안
    VCP 유니버스 전량이 3윈도우 backfill 을 반복한다(영구 churn 은 아니지만 매일 밤
    KIS 호출이 3배로 든다). 도달값은 `_capture_backfill_reach_cal` **실측**이고 환산
    앵커는 사이클196 실측 230cal ⇄ 154영업일이다 — 수식을 테스트에 복제하지 않는다.

    이 단언이 붉어지는 방향은 둘이다: 깊이 환산이 과소로 되돌아가거나, target 이
    환산이 감당하는 것보다 커지거나. 어느 쪽이든 "한 밤에 채운다"가 깨졌다는 뜻이다.
    """
    from tests.unit.db.test_cycle299_retention_expansion import (
        _capture_backfill_reach_cal,
    )

    target = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS
    reach_cal = await _capture_backfill_reach_cal(monkeypatch, target)
    reach_trading = trading_days_in(reach_cal)
    surplus = reach_trading - target

    assert surplus >= MIN_ONE_PASS_SURPLUS_TRADING, (
        f"1회 backfill 이 target 에 못 닿는다 — 실도달 {reach_trading} 영업일 "
        f"(={reach_cal}cal) < target {target} (부족 {-surplus}). "
        f"그만큼의 밤 동안 VCP 유니버스 전량이 3윈도우 backfill 을 반복한다. "
        f"깊이 환산은 `condition._DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO` 가 정한다"
    )


# ---------------------------------------------------------------------------
# G-299-8 (SAFETY, 불변식) — scanner 변경이 상수값에 국한
# ---------------------------------------------------------------------------
def test_g299_8_safety_daily_load_no_trading_hot_path():
    """`_stock_master_daily_load_once` 본체 매매/구독 hot path 토큰 0 + 심볼 불변.

    무엇을 재는 테스트인가: cycle299 의 scanner 변경이 `_DAILY_LOAD_VCP_BACKFILL_DAYS`
    **값 하나**에 국한되고 구독/스캔/우선순위/매수 경로를 건드리지 않았다는 정적 증거.
    사이클 172/196 SAFETY 패턴(`test_c1_safety_daily_load_no_trading_hot_path`) 답습.

    불변식 — Red/Green 양쪽 PASS.
    """
    src = inspect.getsource(scanner._stock_master_daily_load_once)
    forbidden = (
        "risk.on_tick", "order_engine", "execute_buy", "execute_sell",
        "place_order", "check_exit_signal", "check_buy_signal",
        "subscribe_filtered_stocks", "scan_stocks",
    )
    for token in forbidden:
        assert token not in src, (
            f"_stock_master_daily_load_once 매매/구독 hot path 참조 0 의무: {token}"
        )

    assert hasattr(scanner, "_DAILY_LOAD_VCP_BACKFILL_DAYS"), \
        "_DAILY_LOAD_VCP_BACKFILL_DAYS 상수 정의 존재 의무"

    # 구독/스캔 경로 함수 심볼 불변 (accidental 삭제 방지)
    assert callable(getattr(scanner, "subscribe_filtered_stocks", None)), \
        "subscribe_filtered_stocks 심볼 불변"
    assert callable(getattr(scanner, "scan_stocks", None)), \
        "scan_stocks 심볼 불변"

    # 이웃 상수 불변 — cycle299 는 VCP target 만 움직인다
    assert scanner._DAILY_LOAD_FETCH_DAYS == 100, \
        "_DAILY_LOAD_FETCH_DAYS=100 (KIS 1회 호출 한도) 불변"
    assert scanner._DAILY_LOAD_INCREMENTAL_THRESHOLD == 50, \
        "_DAILY_LOAD_INCREMENTAL_THRESHOLD=50 (비 VCP 백필/증분 경계) 불변"
