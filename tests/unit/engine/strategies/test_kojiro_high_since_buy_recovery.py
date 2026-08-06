"""H-1 — 트레일링 기준점(`high_since_buy`) 재시작 소멸 결함 회귀 가드.

## 라이브 실증 (2026-08-06)

    positions 테이블 7행 전부 `high_since_buy == buy_price`

    ticker  종목            매수가    DB high   매수일 이후 일봉 high max
    236200  슈프리마         48,200   48,200    57,400   (+19.1%)
    111770  영원무역         86,800   86,800    92,400   (+6.5%)
    002790  아모레퍼시픽홀딩스  25,150   25,150    26,550   (+5.6%)
    079160  CJ CGV          5,230    5,230     5,540   (+5.9%)
    316140  우리금융지주      33,050   33,050    34,300   (+3.8%)

## 결함 메커니즘

`risk.py:114` 가 `pos.high_since_buy = max(pos.high_since_buy, current_price)` 로
**메모리만** 갱신한다. DB `positions.high_since_buy` 를 쓰는 경로는 둘뿐이다:

  - `save_position()` — 매수 체결 시 (`resolved_high = high or buy_price`)
  - `update_high()`   — 호출자가 donchian/VCP 의 `_apply_high_since_buy_from_candles` 뿐

kojiro 는 어느 쪽도 아니다. 그래서 `boot_manager.py:151-159` 가 매 영업일 07:55
`_boot()` 에서 DB row 로 Position 을 재생성하면(`high_since_buy=row.get(...)`)
**트레일링 기준점이 매일 아침 매수가로 리셋**된다. 2.5ATR 샹들리에가
`buy_price - 2.5×ATR` 로 주저앉아 사실상 하드손절과 구분되지 않고, 며칠에 걸쳐
쌓은 미실현이익은 보전 대상에서 통째로 빠진다.

실측 영향(슈프리마): 복구 시 샹들리에 51,203 = **매수가 +6.2% 확정 보전**.
복구 없으면 실효 손절선은 −8% backstop(44,344) — 같은 포지션에서 보호 수준이
6,859원/주 (12.2%p) 차이난다.

## 시정

1. **`StrategyBase._apply_high_since_buy_from_candles` 단일 진실원 추출** —
   donchian_swing.py 와 vcp_breakout.py 에 로그 접두사만 다른 byte-identical
   중복이 이미 존재했다. kojiro 에 3번째 복사본을 만들면 세 곳이 드리프트한다.
   ⚠️ `recompute_high_since_buy` **자체는 base 로 올리지 않는다** —
   `test_bfb_turtle_sizing.py::test_bfb_not_multiday_and_no_rederive_infra` 가
   `not hasattr(BullFlagBreakoutStrategy, "recompute_high_since_buy")` 를 강제한다.

2. **kojiro 는 `recompute_held_atr` 안에서 위임** — donchian 이 정확히 이 패턴
   (E3, `recompute_held_atr` 이 같은 일봉 응답으로 high 보정도 수행)이다.
   `recompute_held_atr` 는 scheduler.py 의 `_SWING_POLL_STRATEGIES` 루프가
   **이미 호출**하므로 KIS 추가 호출 0 + **scheduler.py diff 0**
   (VCP 전용 훅은 하드코딩 `_vcp` 라 kojiro 를 끼우면 8영역을 건드리게 된다).

3. **정규화 row 대응** — kojiro 의 일봉 소스는 `fetch_daily_candles`(KIS 원본 키)가
   아니라 `get_recent_daily_normalized` 다. 이 어댑터는 보통 raw JSONB(KIS 원본 키)를
   돌려주지만 **raw 키가 없는 row 는 row 자체**(정규화 컬럼 `bas_dd`/`high_price`)를
   돌려준다. 헬퍼가 한 형태만 읽으면 나머지는 조용히 전부 skip 된다.

## 안전 방향

보정은 **올리기 전용**이고 경계가 `buy_date < bas_dd < today` 로 엄격하다 —
보유 기간 중 실제로 도달한 일봉 고가만 채택하므로 과대복구가 구조적으로 불가능하다.
과소복구(매수 당일 고가 · 당일 장중 고가 제외)만 남으며 그 방향은 청산을 늦춘다.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def _today() -> date:
    """운영 코드가 `datetime.now(KST).date()` 를 쓰므로 테스트도 동일 기준."""
    return datetime.now(_KST).date()


def _kojiro(**extra) -> KojiroStrategy:
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.6, params=extra),
    )
    s.state.total_investment = 690_111
    return s


def _hold(s, ticker="236200", *, buy=48_200, qty=1, days_ago=15, high=0):
    pos = Position(
        ticker=ticker, buy_price=buy, quantity=qty, order_no=f"O-{ticker}",
        strategy_id="kojiro", buy_date=_today() - timedelta(days=days_ago),
        high_since_buy=high or buy,
    )
    s.state.positions[ticker] = pos
    return pos


def _kis_candle(d: date, high: int) -> dict:
    """KIS 원본 키 형태 (raw JSONB 경로 · fetch_daily_candles 폴백 경로)."""
    return {
        "stck_bsop_date": d.strftime("%Y%m%d"),
        "stck_hgpr": str(high),
        "stck_lwpr": str(int(high * 0.97)),
        "stck_clpr": str(int(high * 0.99)),
        "stck_oprc": str(int(high * 0.98)),
        "acml_vol": "100000",
    }


def _col_candle(d: date, high: int) -> dict:
    """정규화 컬럼 형태 (raw 키 부재 row → 어댑터가 row 자체를 반환)."""
    return {
        "bas_dd": d,
        "high_price": high,
        "low_price": int(high * 0.97),
        "close_price": int(high * 0.99),
        "open_price": int(high * 0.98),
        "volume": 100000,
    }


class _Recorder:
    """`recompute_held_atr` 의 외부 의존을 전부 잡아두는 컨텍스트."""

    def __init__(self, candles_by_ticker: dict[str, list[dict]] | Exception):
        self._candles = candles_by_ticker
        self.update_high = AsyncMock()
        self.fetch_calls: list[str] = []
        self._patches: list = []

    async def _fetch(self, ticker, days=0, min_required=None):
        self.fetch_calls.append(ticker)
        if isinstance(self._candles, Exception):
            raise self._candles
        val = self._candles.get(ticker, [])
        if isinstance(val, Exception):
            raise val
        return val

    def __enter__(self):
        self._patches = [
            patch("src.db.stock_master_daily.get_recent_daily_normalized", self._fetch),
            patch("src.db.positions.update_high", self.update_high),
            patch("src.db.system_logs.write_log", AsyncMock()),
            patch.object(KojiroStrategy, "_fetch_sector", AsyncMock(return_value="테스트섹터")),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


# ---------------------------------------------------------------------------
# H1-A — 단일 진실원: 헬퍼가 StrategyBase 에 있고 kojiro 가 상속한다
# ---------------------------------------------------------------------------

def test_helper_lives_on_strategy_base():
    """`_apply_high_since_buy_from_candles` 는 StrategyBase 의 단일 진실원이다."""
    assert hasattr(StrategyBase, "_apply_high_since_buy_from_candles"), (
        "H1-A: donchian/VCP 중복 2벌 → kojiro 3번째 복사본 대신 base 추출"
    )


def test_kojiro_inherits_helper():
    assert hasattr(KojiroStrategy, "_apply_high_since_buy_from_candles")


def test_no_duplicate_helper_definition_in_strategy_files():
    """전략 파일에 헬퍼 **정의**가 남아 있으면 드리프트 재발 — base 위임만 허용.

    호출(`self._apply_high_since_buy_from_candles(...)`)은 허용, `def` 는 금지.
    """
    root = Path(__file__).resolve().parents[4] / "src" / "engine" / "strategies"
    offenders = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node.name == "_apply_high_since_buy_from_candles"
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        f"H1-A: 헬퍼 정의는 StrategyBase 단독 — 잔존 정의 {offenders}"
    )


def test_recompute_hook_is_never_promoted_to_base():
    """[의미 전환 2026-08-06] `recompute_high_since_buy` 는 **base 승격 금지**.

    승격하면 momentum·VB 처럼 복구가 무의미한 전략까지 상속해 dead code 를 갖고,
    무엇보다 전략마다 일봉 소스·fetch 일수·재도출 대상이 다르다(donchian=KIS 직접
    +donchian_period / VCP=ema_long·base_max / BFB=pole·flag lookback). 공유해야 할
    것은 `_apply_high_since_buy_from_candles` **뿐**이고 그건 이미 base 에 있다.

    종전 이 테스트는 "BFB 는 이 메서드를 갖지 않는다"까지 강제했으나, 그 전제였던
    "BFB 는 익일 청산" 이 거짓으로 판명돼 P1.5 에서 **자체 정의**로 도입했다.
    """
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy

    assert not hasattr(StrategyBase, "recompute_high_since_buy")
    # 상속이 아니라 자체 정의여야 한다
    assert "recompute_high_since_buy" in BullFlagBreakoutStrategy.__dict__


# ---------------------------------------------------------------------------
# H1-B — kojiro 복구 본행위
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recovers_high_from_daily_candles_and_persists():
    """슈프리마 실측 재현 — 48,200 → 57,400 보정 + DB UPDATE."""
    s = _kojiro()
    pos = _hold(s)
    t = _today()
    candles = [
        _kis_candle(t - timedelta(days=n), h)
        for n, h in ((1, 55_000), (3, 57_400), (6, 52_000), (10, 49_000))
    ]
    with _Recorder({"236200": candles}) as rec:
        await s.recompute_held_atr()

    assert pos.high_since_buy == 57_400, "매수일 이후 일봉 high max 로 보정"
    rec.update_high.assert_awaited_once_with("236200", 57_400)


@pytest.mark.asyncio
async def test_recovers_from_normalized_column_rows():
    """어댑터가 raw 없는 row(정규화 컬럼)를 돌려줘도 보정된다.

    `bas_dd` 는 asyncpg 가 `date` 객체로 반환한다 — 문자열 길이 검사만 하면
    전 종목이 조용히 skip 된다.
    """
    s = _kojiro()
    pos = _hold(s)
    t = _today()
    candles = [_col_candle(t - timedelta(days=n), h) for n, h in ((2, 57_400), (5, 51_000))]
    with _Recorder({"236200": candles}) as rec:
        await s.recompute_held_atr()

    assert pos.high_since_buy == 57_400
    rec.update_high.assert_awaited_once_with("236200", 57_400)


@pytest.mark.asyncio
async def test_recovery_runs_even_when_atr_recompute_bails():
    """봉 수가 ATR 재계산 최소치(80)에 못 미쳐도 high 보정은 수행된다.

    kojiro 의 `recompute_held_atr` 는 `len(usable) < KOJIRO_MIN_REQUIRED` 에서
    `continue` 한다. 보정 코드를 그 뒤에 두면 워밍업 부족 종목이 영원히
    복구되지 않는다 — donchian 이 `pos_needs_high_recover` 를 ATR 필요 여부와
    **독립적으로** 계산하는 이유.
    """
    s = _kojiro()
    pos = _hold(s)
    t = _today()
    candles = [_kis_candle(t - timedelta(days=2), 57_400)]  # 1봉 — ATR 불가
    with _Recorder({"236200": candles}) as rec:
        await s.recompute_held_atr()

    assert pos.high_since_buy == 57_400
    rec.update_high.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_extra_kis_call_per_ticker():
    """이미 fetch 한 candles 재사용 — 종목당 일봉 조회 1회."""
    s = _kojiro()
    _hold(s)
    t = _today()
    with _Recorder({"236200": [_kis_candle(t - timedelta(days=2), 57_400)]}) as rec:
        await s.recompute_held_atr()

    assert rec.fetch_calls == ["236200"], f"종목당 1회여야 함: {rec.fetch_calls}"


# ---------------------------------------------------------------------------
# H1-C — 경계/단조성 (과대복구 구조적 차단)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_excludes_buy_date_and_today():
    """`buy_date < bas_dd < today` — 매수일 당일(매수 *전* 고가 오염)과 오늘 모두 제외."""
    s = _kojiro()
    pos = _hold(s, days_ago=3)
    t = _today()
    candles = [
        _kis_candle(t, 99_000),                              # 오늘 → 제외
        _kis_candle(t - timedelta(days=1), 51_000),          # 채택
        _kis_candle(t - timedelta(days=3), 88_000),          # 매수일 → 제외
    ]
    with _Recorder({"236200": candles}):
        await s.recompute_held_atr()

    assert pos.high_since_buy == 51_000


@pytest.mark.asyncio
async def test_never_lowers_existing_high():
    """보정은 올리기 전용 — 메모리 고점이 더 높으면 손대지 않고 DB 도 안 쓴다."""
    s = _kojiro()
    pos = _hold(s, high=61_300)
    t = _today()
    with _Recorder({"236200": [_kis_candle(t - timedelta(days=2), 57_400)]}) as rec:
        await s.recompute_held_atr()

    assert pos.high_since_buy == 61_300
    rec.update_high.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_day_purchase_is_untouched():
    """당일 매수는 buy_price 가 진실 — 보정 대상 아님."""
    s = _kojiro()
    pos = _hold(s, days_ago=0)
    t = _today()
    with _Recorder({"236200": [_kis_candle(t - timedelta(days=1), 99_000)]}) as rec:
        await s.recompute_held_atr()

    assert pos.high_since_buy == 48_200
    rec.update_high.assert_not_awaited()


# ---------------------------------------------------------------------------
# H1-D — fail-open (복구 실패가 매매를 마비시키지 않는다)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_update_failure_keeps_memory_correction():
    """DB UPDATE 가 실패해도 메모리 보정은 유지되고 예외는 전파되지 않는다."""
    s = _kojiro()
    pos = _hold(s)
    t = _today()
    with _Recorder({"236200": [_kis_candle(t - timedelta(days=2), 57_400)]}) as rec:
        rec.update_high.side_effect = RuntimeError("DB down")
        await s.recompute_held_atr()

    assert pos.high_since_buy == 57_400


@pytest.mark.asyncio
async def test_one_ticker_failure_does_not_block_others():
    """종목별 격리 — 한 종목 fetch 실패가 나머지 복구를 막지 않는다 (sequential)."""
    s = _kojiro()
    bad = _hold(s, "111770", buy=86_800)
    good = _hold(s, "236200", buy=48_200)
    t = _today()
    with _Recorder({
        "111770": RuntimeError("fetch 실패"),
        "236200": [_kis_candle(t - timedelta(days=2), 57_400)],
    }):
        await s.recompute_held_atr()

    assert bad.high_since_buy == 86_800      # 미보정
    assert good.high_since_buy == 57_400     # 정상 복구


@pytest.mark.asyncio
async def test_malformed_candles_are_skipped_gracefully():
    """키 결측/형식 불량 봉은 개별 skip — 전체가 죽지 않는다."""
    s = _kojiro()
    pos = _hold(s)
    t = _today()
    candles = [
        {"stck_bsop_date": "2026", "stck_hgpr": "99000"},     # 날짜 형식 불량
        {"stck_bsop_date": (t - timedelta(days=2)).strftime("%Y%m%d")},  # high 결측
        {"high_price": 88_000},                                # 날짜 결측
        _kis_candle(t - timedelta(days=4), 57_400),            # 유효
    ]
    with _Recorder({"236200": candles}):
        await s.recompute_held_atr()

    assert pos.high_since_buy == 57_400


# ---------------------------------------------------------------------------
# H1-E — 안전성: 8영역 미접촉 + 기존 배선 재사용
# ---------------------------------------------------------------------------

def test_kojiro_wired_through_existing_recompute_hook():
    """kojiro 복구는 `recompute_held_atr` 안에서 일어난다 (scheduler diff 0 근거).

    scheduler.py 의 VCP 전용 훅은 하드코딩 `_vcp` 라 kojiro 를 끼우면 8영역
    diff 가 발생한다. `_SWING_POLL_STRATEGIES` 루프가 이미 호출하는
    `recompute_held_atr` 에 얹는 것이 유일한 무접촉 경로다.
    """
    src = inspect.getsource(KojiroStrategy.recompute_held_atr)
    assert "_apply_high_since_buy_from_candles" in src


def test_scheduler_has_no_kojiro_high_recovery_wiring():
    """scheduler.py(8영역)는 이번 시정으로 변경되지 않는다."""
    from src.engine import scheduler as scheduler_mod

    src = inspect.getsource(scheduler_mod)
    idx = src.find("recompute_high_since_buy")
    assert idx != -1, "VCP 전용 훅은 영속"
    assert "kojiro" not in src[max(0, idx - 400): idx + 400], (
        "H1-E: kojiro 를 VCP 훅에 끼우면 8영역 diff 발생 — recompute_held_atr 경로 사용"
    )


# ---------------------------------------------------------------------------
# H1-F — 적대적 검증(2026-08-06)에서 확정된 결함 2건
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["inf", "-inf", "Infinity", "1e400", "  inf  ", "nan"])
def test_candle_high_never_raises_on_overflow_inputs(bad):
    """`int(float("inf"))` 은 OverflowError — `(TypeError, ValueError)` 로는 못 잡는다.

    새어 나가면 봉 하나가 `_apply_high_since_buy_from_candles` 를 통째로 중단시켜
    **같은 루프의 남은 보유 종목까지** 그날 복구를 잃는다(donchian 은 뒤따르는
    `_breakout_high`/`_channel_low` 재도출도 함께 유실). 추출 실패의 계약은
    "그 봉만 버린다" 이며, 추출 전 구현(`int(c.get("stck_hgpr","0"))` → ValueError
    → candle skip)도 그랬다.
    """
    assert StrategyBase._candle_high({"stck_hgpr": bad}) == 0


@pytest.mark.asyncio
async def test_one_bad_candle_does_not_abort_remaining_recovery():
    """불량 봉 1행이 나머지 봉/종목의 복구를 중단시키지 않는다."""
    s = _kojiro()
    a = _hold(s, "111770", buy=86_800)
    b = _hold(s, "236200", buy=48_200)
    t = _today()
    with _Recorder({
        "111770": [
            {"stck_bsop_date": (t - timedelta(days=1)).strftime("%Y%m%d"), "stck_hgpr": "inf"},
            _kis_candle(t - timedelta(days=2), 92_400),
        ],
        "236200": [_kis_candle(t - timedelta(days=2), 57_400)],
    }):
        await s.recompute_held_atr()

    assert a.high_since_buy == 92_400, "불량 봉은 그 봉만 버려야 한다"
    assert b.high_since_buy == 57_400, "앞 종목의 불량 봉이 뒤 종목을 막으면 안 된다"


def test_donchian_vcp_log_labels_preserved():
    """단일 진실원 추출이 운영자의 한글 로그 grep 경로를 끊지 않는다.

    추출 전 리터럴은 `"도치안 스윙 high_since_buy 보정: ..."` / `"VCP high_since_buy
    보정: ..."` 이었다. 접두사가 `strategy_id` 로 바뀌면 08-06 이후 복구 이력이
    과거 표기 grep 에서 0건으로 보인다.
    """
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    assert DonchianSwingStrategy._HIGH_RECOVER_LABEL == "도치안 스윙"
    assert VcpBreakoutStrategy._HIGH_RECOVER_LABEL == "VCP"
    # kojiro 는 신규라 보존할 과거 표기가 없다 → strategy_id 기본값
    assert KojiroStrategy._HIGH_RECOVER_LABEL is None


# ---------------------------------------------------------------------------
# H1-G — Σ오픈리스크 캡이 복구된 샹들리에를 반영한다 (사용자 결정 2026-08-06)
# ---------------------------------------------------------------------------

def _held_with_atr(s, ticker="236200", *, buy=48_200, qty=1, atr=2_479.0, high=None):
    pos = _hold(s, ticker, buy=buy, qty=qty, high=high or buy)
    s._position_atr[ticker] = atr
    return pos


def test_stop_price_includes_chandelier_when_it_binds():
    """고점이 복구되면 실효 손절선은 샹들리에다 (슈프리마 실측 재현).

    buy 48,200 · ATR 2,479 · 복구 고점 57,400
      pct(−8%)   = 44,344
      2ATR floor = 43,242
      샹들리에    = 57,400 − 2.5×2,479 = 51,202  ← 실효
    """
    s = _kojiro()
    pos = _held_with_atr(s, high=57_400)
    assert s._position_stop_price("236200", pos) == int(57_400 - 2.5 * 2_479.0)


@pytest.mark.parametrize("buy,atr", [(48_200, 2_479.0), (20_000, 800.0), (5_230, 231.0)])
def test_stop_price_unchanged_while_high_equals_buy(buy, atr):
    """고점 미복구(= H-1 이전 상태) 구간에서는 종전 값 그대로 — 회귀 0.

    `high == buy` 이면 샹들리에 `buy − 2.5×ATR` 가 2ATR 선 `buy − 2.0×ATR` 보다
    항상 낮으므로 `max()` 결과에 영향이 없다. 기존 캡/손절 테스트가 전부 이
    구간이라 샹들리에 편입이 그것들을 건드리지 않는다는 근거가 된다.

    실효선이 pct(−8%) 인지 2ATR 인지는 `atr_ratio` 에 따라 갈리므로
    (5.14% → pct 가 이김 / 4.0% → 2ATR 이 이김) 둘의 max 로 기대값을 세운다.
    """
    s = _kojiro()
    pos = _held_with_atr(s, buy=buy, atr=atr)
    expected = max(int(buy * 0.92), int(buy - 2.0 * atr))
    assert s._position_stop_price("236200", pos) == expected


def test_profit_locked_position_contributes_zero_risk():
    """샹들리에가 매수가를 넘으면 그 포지션의 오픈리스크는 0이다."""
    s = _kojiro()
    _held_with_atr(s, high=57_400)          # 샹들리에 51,202 > 매수가 48,200
    assert s._position_stop_price("236200", s.state.positions["236200"]) > 48_200
    assert s._open_risk_won() == 0


def test_profit_locked_position_never_offsets_other_risk():
    """이익 확정분이 **음수 리스크**로 다른 포지션의 노출을 상쇄하면 안 된다.

    상쇄를 허용하면 큰 승자 하나가 여러 패자의 실제 손실 노출을 가려 캡이
    조용히 무력화된다.
    """
    s = _kojiro()
    _held_with_atr(s, "236200", buy=48_200, atr=2_479.0, high=57_400)   # 리스크 0
    _held_with_atr(s, "002790", buy=25_150, atr=1_155.0, high=25_150)   # 실노출 있음

    solo = _kojiro()
    _held_with_atr(solo, "002790", buy=25_150, atr=1_155.0, high=25_150)

    assert s._open_risk_won() == solo._open_risk_won() > 0


def test_recovered_high_lowers_open_risk_monotonically():
    """고점 복구는 Σ오픈리스크를 늘리지 않는다 (매수 게이트가 조여지지 않음)."""
    s = _kojiro()
    pos = _held_with_atr(s)
    before = s._open_risk_won()
    pos.high_since_buy = 57_400
    assert s._open_risk_won() <= before


def test_stop_price_matches_exit_signal_line():
    """추정기와 실제 청산선이 일치한다 — 샹들리에 발화 경계에서 교차 검증."""
    s = _kojiro()
    pos = _held_with_atr(s, high=57_400)
    stop = s._position_stop_price("236200", pos)
    from src.engine.strategy_base import Signal

    assert s.check_exit_signal("236200", stop, 48_200) == Signal.TRAILING_STOP
    assert s.check_exit_signal("236200", stop + 1, 48_200) == Signal.NONE


def test_stop_price_does_not_mutate_stop_floor():
    """매수 게이트 경로가 청산 규약(`_stop_floor`)을 부작용으로 바꾸면 안 된다."""
    s = _kojiro()
    pos = _held_with_atr(s, high=57_400)
    assert "236200" not in s._stop_floor
    s._position_stop_price("236200", pos)
    assert "236200" not in s._stop_floor


def test_risk_on_tick_has_no_db_write():
    """`risk.on_tick` hot path 에 DB 쓰기가 들어가지 않았다 (틱당 write 금지)."""
    from src.engine import risk as risk_mod

    src = inspect.getsource(risk_mod)
    assert "update_high" not in src, (
        "H1-E: 고점 영속화를 on_tick 에 넣으면 틱당 DB write — 영속은 boot 훅 담당"
    )
