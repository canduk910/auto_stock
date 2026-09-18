"""사이클 196 (2026-07-07) — VCP daily backfill 수렴 회귀 가드 (churn 종결).

배경 (사이클 192 D+1 실측): `_stock_master_daily_load_once` 의 VCP universe backfill 이
수렴 못 해 매 load 마다 348종목 전량 재backfill (churn). 근본 = backfill 조건
`existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=220)` 인데 retention 230cal일이 보유
영업일을 154 로 캡 → 220 절대 미도달 → use_vcp_backfill 영구 True.

시정 (P1): `_DAILY_LOAD_VCP_BACKFILL_DAYS = 220 → 120` (retained 154 대비 34일 마진 +
VCP prepare 100일 위 20일 버퍼). 수렴: existing 120 도달 → incremental 전환 → churn 종료.

⚠️ cycle299 (2026-09-17) 의미 전환 — 이 파일이 재는 **불변식은 그대로**이고 값만 옮겼다.
cycle299 는 retention 을 230 → 390 달력일로 함께 올려 target 을 실효 장기선 200 이 되는 225 영업일로
복원했다(200일 EMA). 사이클 196 이 세운 "retained − target = 34 영업일 마진" 은
390cal ≈ 261 영업일 − 225 = 36 으로 **오히려 늘어난다**. 커플링 부등식의 정본 가드는
`tests/unit/db/test_cycle299_retention_expansion.py::G-299-3a/3b/3c`.

Group B 회귀 가드 (scanner.py `_stock_master_daily_load_once`):
- B-1: 상수 == 225 (사이클 196 시점 120 → cycle299 의미 전환)
- B-2 (핵심 수렴): VCP + count=261(retained 최대치) → backfill 미호출 + days=7 증분
- B-3: VCP + count=224 (<225) → fetch_daily_candles_backfill(total_days=225) 호출
- B-4 (경계, 불변식): count == threshold → strict-< False → 재backfill 금지 (incremental)
- B-5 (cycle302 의미 전환): 비지수도 **같은 임계**를 쓴다 (154·30 모두 → 분할 backfill)

⚠️ cycle302 (2026-09-18) 의미 전환 — B-5 가 재던 "非VCP 불변" 은 backfill 대상이
지수 전용이던 시절의 계약이다. 이제 적재 대상(index ∪ 자격 ∪ 보호)이면 누구나 같은
임계를 쓴다. **수렴 불변식(B-2/B-4)은 그대로다** — 오히려 대상이 늘어난 만큼 churn
금지가 더 중요해졌다. 계약 정본 = `test_cycle302_backfill_scope_expansion.py`.

Group C:
- C-1 (SAFETY, AST, 불변식): scanner 변경 = 상수값만 — daily_load 본체 매매 hot path 참조 0
  + 구독/스캔 함수 심볼 존재 (사이클 172 SAFETY 패턴 답습)

Red 유효성 (cycle299 Red = production 미변경 = 상수 120 / retention 230):
- B-1/B-3 FAIL (120 기준 → 224 는 증분으로 새고 total_days=120)
- B-2/B-4/B-5/C-1 PASS (불변식 — 261 >= 120 도 증분 / threshold 동적 / 非VCP 무관 / AST)

mock 구성: 사이클 172 test_cycle172_vcp_universe_backfill.py 100% 답습
(list_all side_effect + max_bas_dd/count_by_ticker/fetch_*/upsert_batch + asyncio.sleep).
max_bas_dd=None = "fresh 아님 → 적재 진행" (사이클 176/180 교훈 — 날짜 하드코딩 회피).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


def _vcp_candle(bas_dd: str = "20260620") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


# ---------------------------------------------------------------------------
# B-1 — 상수 == 225 (사이클 196 시점 120 → cycle299 의미 전환)
# ---------------------------------------------------------------------------
def test_b1_backfill_days_constant():
    """_DAILY_LOAD_VCP_BACKFILL_DAYS == 225 (retention 390cal ≈ 261영업일 내 수렴).

    무엇을 재던 테스트인가: target 이 retention 의 실보유 영업일 **안**에 있다는 것.
    사이클 196 은 retention 230cal(=154영업일) 아래의 120 으로 그것을 만족시켰다.
    cycle299 는 retention 을 390cal(≈261영업일)로 함께 올려 target 225 를 같은 부등식
    안에 넣는다 — 마진은 34(사이클196) → 36(cycle299) 으로 오히려 늘어난다.

    cycle299 Red (120): FAIL. Green (225): PASS.
    """
    assert scanner._DAILY_LOAD_VCP_BACKFILL_DAYS == 225, (
        "cycle299 — retained ≈261 대비 36 영업일 마진 (실효 장기선 200 = 보유 225 영업일)"
    )


# ---------------------------------------------------------------------------
# B-2 (핵심 수렴) — VCP + count=261 (retained 최대치) → 재backfill 금지 + 증분 (days=7)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b2_vcp_retained_max_converges_to_incremental():
    """VCP universe + count_by_ticker=261 → backfill 미호출 + fetch_daily_candles(days=7).

    무엇을 재던 테스트인가: **"보유 가능 최대치에서 재backfill 하지 않는다"** = churn
    종결의 핵심 증명. 재는 것은 154 라는 숫자가 아니라 "그 시점 retention 이 물리적으로
    보유할 수 있는 최대 영업일" 이라는 **역할**이다.

    왜 261 로 옮기는가: 154 는 retention 230cal 의 실보유 영업일이었다(사이클 196 실측).
    cycle299 가 retention 을 390cal 로 올리면 실보유는 390 × 154/230 ≈ 261 영업일이 된다.
    154 를 그대로 두면 `154 < 225` 라 이 테스트가 재던 의도가 정반대(backfill 발화)로
    뒤집힌다 — 값을 옮기는 것이 곧 의도 보존이다.

    같은 불변식을 프로덕션 retention 상수에서 **동적으로** 산출하는 형태는
    `tests/unit/engine/test_cycle299_backfill_target_expansion.py::G-299-4` 가 맡는다
    (retention 만 뒤처진 반쪽 Green 을 잡는 커플링 가드). 여기서는 261 을 리터럴로
    못박아 그 동적 계산 자체가 틀어진 경우까지 덮는다.

    cycle299 Red (120): 261 >= 120 → 증분 → PASS (불변식).
    Green (225): 261 >= 225 → 증분 → PASS.
    반쪽 Green (retention 230 유지 + target 225): 여전히 PASS 하지만 G-299-4 가 잡는다.
    """
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),  # fresh 아님 → 적재 진행
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        # retention 390cal 의 실보유 영업일 (= 390 × 154/230, 사이클196 실측 앵커 환산)
        new=AsyncMock(return_value=261),
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

    assert backfill_mock.await_count == 0, (
        "VCP 261 (보유 최대치) >= 225 → 재backfill 금지 (수렴)"
    )
    assert 7 in captured_days, "VCP 261 → 증분 모드 (fetch_daily_candles days=7)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-3 — VCP + count=224 (<225) → fetch_daily_candles_backfill(total_days=225)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b3_vcp_below_target_triggers_backfill():
    """VCP + count_by_ticker=224 (target−1) → backfill 호출 + total_days=225.

    무엇을 재던 테스트인가: target 바로 아래 한 칸에서 backfill 분기가 켜지고, 끌어오는
    총량이 target 과 같다는 것. 재는 것은 "119" 가 아니라 **target−1** 이라는 역할이다.

    왜 224 / 225 로 옮기는가: cycle299 가 target 을 225 로 올리면 119 는 더 이상
    경계 아래 한 칸이 아니라 증분 구간 한복판이 되어 backfill 이 발화하지 않는다.

    `total_days` 하드코딩 규약 유지 — 상수를 참조하면 Red 에서도 통과해 Red 가 무효다.

    cycle299 Red (120): 224 >= 120 → 증분 → await_count==0 → FAIL.
    Green (225): 224 < 225 → backfill(total_days=225) → PASS.
    """
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=224),  # target−1 (< 225) → VCP backfill
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[_vcp_candle()]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 1, "VCP count 224 < 225 → backfill 호출"
    # 하드코딩 225 (상수 참조 시 Red 에서도 PASS 되어 Red 무효) — 목표값 명시 단언
    assert backfill_mock.call_args.kwargs.get("total_days") == 225, (
        "backfill total_days=225 의무. cycle299 Red(120): total_days=120 → FAIL"
    )
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-4 (경계, 불변식) — count == threshold → strict-< False → 재backfill 금지
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b4_boundary_count_equals_threshold_incremental():
    """count_by_ticker == _DAILY_LOAD_VCP_BACKFILL_DAYS → strict-< False → incremental.

    threshold 를 상수에서 동적 취득 → 상수값 무관 불변식 (cycle299 Red/Green 양쪽 PASS):
    - cycle299 Red: count=120, 120 < 120 = False → 증분 (days=7). backfill 0.
    - Green: count=225, 225 < 225 = False → 증분. backfill 0.
    strict-`<` 경계 (== 는 backfill 아님) 를 상수값 무관 영구 고정 —
    `<` 를 `<=` 로 바꾸면 수렴점이 사라져 영구 churn 이 된다.
    """
    threshold = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS  # 120(Red) / 225(Green) 동적
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=threshold),  # 정확히 경계값
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

    assert backfill_mock.await_count == 0, (
        "existing == threshold → strict-< False → 재backfill 금지 (경계 불변식)"
    )
    assert 7 in captured_days, "경계값(>=50) → 증분 (days=7)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-5a (cycle302 의미 전환) — 비지수 + existing=154 → 분할 backfill
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b5a_non_index_154_takes_backfill():
    """비지수(is_kospi200=False, is_kosdaq150=False) + existing=154 → 분할 backfill.

    ⚠️ cycle302 의미 전환. 154 는 오늘 실측 비지수 평균 깊이(125)보다도 깊은데,
    종전에는 `>= 50` 이라는 이유만으로 증분 7일에 갇혀 목표 깊이 225 에 **영영**
    닿지 못했다(증분은 새 봉만 얹지 과거를 파지 않는다). 그게 비지수 1,526 종목의
    225행 도달률이 0% 였던 이유다.
    """
    stock_master_rows = [
        {"ticker": "999999", "is_kospi200": False, "is_kosdaq150": False,
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=154),  # < 225 → 분할 backfill (cycle302)
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

    assert backfill_mock.await_count == 1, (
        "비지수도 DB < 225 면 같은 임계를 쓴다(cycle302). "
        f"실측 backfill={backfill_mock.await_count} fetch_days={captured_days}"
    )
    assert 7 not in captured_days, (
        "증분 7일로 빠지면 과거 깊이를 영영 못 판다. "
        f"실측 fetch_days={captured_days}"
    )
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-5b (cycle302 의미 전환) — 비지수 + existing=30 → 분할 backfill
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b5b_non_index_30_takes_backfill():
    """비지수 + existing=30 (<50) → 100일 단발이 아니라 분할 backfill.

    ⚠️ cycle302 의미 전환. 225 > 50 이라 `< 50 → 100일` 분기는 **도달 불가**가 됐다
    (구조적 폴백으로만 잔존). 신규 상장도 첫 밤에 목표 깊이를 탄다 —
    관계 핀 = `test_cycle302_backfill_scope_expansion.py::G-302-8b`.
    """
    stock_master_rows = [
        {"ticker": "999999", "is_kospi200": False, "is_kosdaq150": False,
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=30),  # < 225 → 분할 backfill (cycle302)
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

    assert backfill_mock.await_count == 1, (
        "얕은 비지수 종목도 첫 밤에 목표 깊이를 탄다(cycle302). "
        f"실측 backfill={backfill_mock.await_count} fetch_days={captured_days}"
    )
    assert 100 not in captured_days, (
        "100일 단발로 떨어지면 다음 밤에 또 파야 한다. "
        f"실측 fetch_days={captured_days}"
    )
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# C-1 (SAFETY, AST, 불변식) — scanner 변경 = 상수값만 (매매 hot path 불변)
# ---------------------------------------------------------------------------
def test_c1_safety_daily_load_no_trading_hot_path():
    """_stock_master_daily_load_once 본체 매매 hot path 참조 0 + 구독/스캔 함수 심볼 존재.

    사이클 172 SAFETY 패턴 답습 — 사이클 196 변경이 `_DAILY_LOAD_VCP_BACKFILL_DAYS`
    상수 값에 국한 (구독/스캔/우선순위/매수 경로 불변) 임을 정적 검증.
    불변식 — Red/Green 모두 PASS.
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

    # 상수 정의 존재 (사이클 196 변경 = 값만)
    assert hasattr(scanner, "_DAILY_LOAD_VCP_BACKFILL_DAYS"), \
        "_DAILY_LOAD_VCP_BACKFILL_DAYS 상수 정의 존재 의무"

    # 구독/스캔 경로 함수 심볼 불변 (accidental 삭제 방지)
    assert callable(getattr(scanner, "subscribe_filtered_stocks", None)), \
        "subscribe_filtered_stocks 심볼 불변"
    assert callable(getattr(scanner, "scan_stocks", None)), \
        "scan_stocks 심볼 불변"
