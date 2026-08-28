"""사이클 231 Red — kojiro `_held_stage3` **날짜 키 무효화** (P2-5).

명세: `_workspace/red/cycle231_stage3_stale_spec.md` (W1~W4)
자문: `_workspace/domain_consult/cycle231_kojiro_stage3_stale.md`
행위 분해: `_workspace/red/cycle231_behaviors.md`

## 왜 (결함)

`_held_stage3[ticker]` 는 `check_exit_signal:897` 에서 **가격 무관 즉시**
`Signal.TRAILING_STOP` 을 반환한다. 그런데 이 플래그엔 **타임스탬프가 없다** —
실제 의미는 "마지막으로 재판정에 성공한 시점의 값" 이고, 그게 어제인지 사흘 전인지
코드가 구분하지 못한다. `recompute_held_atr` 의 실패 4경로는 전부 `False` 를 써서
fail-open 을 `:649` docstring 으로 계약화했는데, `prepare()` 경로(`:400`)만
**성공 시에만** 기록하고 실패 시 직전 값을 방치한다 = 한 파일 안에 두 개의 답.

결정적 반례: `prepare()` 의 held 마킹(`:394-400`)은 **ATR 밴드 게이트(`:365`)보다 뒤**다.
밴드 **상한 이탈(>6%) = 변동성 급팽창 = 급등**한 종목이 정확히 마킹을 못 받고,
거기 stale True 가 남아 있으면 다음날 아침 첫 틱에 시장가로 던진다. kojiro 는
승률 11% / RR 3.19 라 기대값이 통째로 오른쪽 꼬리에 있다 — 그 꼬리를 데이터 열화로
자르는 것은 전략 자체를 부정한다.

## 계약 (backend-dev 구현 대상)

1. `_held_stage3: dict[str, tuple[date, bool]]` — 값 = `(판정 수행일, stage==3)`.
   **판정 수행일**이다(봉 날짜 아님 — 연휴에 무효화가 안 걸린다).
   기록 지점 전부(prepare 1 + recompute 5) 동일 형식.
2. 소비(`:897`)는 `엔트리 존재 ∧ 판정일 == today(KST) ∧ flag` 일 때만 §3 발화.
   억제해도 **값은 보존**한다(관측·사후 복기).
3. `[kojiro_stage3_stale_skip] ticker=%s judged_on=%s age_days=%d` —
   **age_days 1 = INFO / ≥2 = WARNING**(debug 단독은 `_DbLogHandler` INFO 컷을 못 넘는다).
   cap 1회/ticker/일, **날짜 키 자기 리셋**(`_reset_daily_state` 훅 미의존).
   `False`/부재는 로그 불요(정상 미발화).
4. `[kojiro_stage3_exit]` 에 `judged_on=%s` 필드 추가(문구 앞부분 byte 보존).
5. W3 부수 방어 — `kojiro.py:685` `pos.buy_date < today` 가 per-ticker try **밖**이라
   date 가 아니면 TypeError 가 루프를 뚫고 뒤 보유 종목 재계산을 통째 유실시킨다
   (cycle226 L-2 동형). 현재 잠복(`boot_manager:162` 가 date 보장)이므로 방어만.

**불변(FREEZE / 도메인 금기)**: §1 −8% 백스톱 · §2 2ATR floor · **§4 샹들리에
trail_atr=2.5(조임 금지 — 억제의 대가를 트레일링을 조여 메우지 말 것)** · 진입 로직 전체.

## freezegun 규약 (cycle229 선례)

freezegun 은 naive 문자열을 **UTC** 로 동결한다 → 이 파일의 freeze 인자는 전부 UTC,
KST = UTC + 9h. kojiro 는 `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 화이트리스트 밖
(= 08:00~09:00 프리장 청산 평가 보류)이라 **09:10 KST** 로 고정한다.

    freeze_time("2026-08-27 00:10:00")  →  KST 2026-08-27 09:10

## RED 상태 (production 미변경 시점)

- B1-1/2/3, B2-*, B3-2, B4-*, B5-*, B6-1, B7-2/3 = **FAIL**(현행은 bool 저장 + 날짜 무관 소비).
  B1-3 이 FAIL 하는 이유가 특히 이 결함의 성격을 드러낸다 — 현행 `if self._held_stage3.get(t):`
  는 **비어 있지 않은 튜플을 전부 참으로 읽으므로** `(오늘, False)` 조차 §3 를 발화시킨다.
- B1-4/5/6, B3-1, B7-1/4 = **PASS**(구현 후에도 계속 PASS 해야 하는 가드).
- B6-1 은 `kojiro.py:685` 에서 `TypeError: '<' not supported between 'str' and 'date'` 로
  터진다 = 루프 전체 중단 실증.
"""

from __future__ import annotations

import ast
import inspect
import logging
import textwrap
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

import src.engine.strategies.kojiro as kmod
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

# 기존 kojiro 테스트 rig 재사용 (새로 발명 금지)
from tests.unit.engine.strategies.test_kojiro import (
    _dummy_candles,
    _enriched,
    _pos,
    _run_prepare,
)

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
LOGGER_NAME = "src.engine.strategies.kojiro"

# UTC 동결 시각 ↔ KST 대응 (위 docstring 규약)
_UTC_D1_0910 = "2026-08-27 00:10:00"   # KST 2026-08-27(목) 09:10
_UTC_D2_0910 = "2026-08-28 00:10:00"   # KST 2026-08-28(금) 09:10

D_TODAY = date(2026, 8, 27)
D_YESTERDAY = date(2026, 8, 26)
D_TWO_AGO = date(2026, 8, 25)

# 08-18 영원무역 실측 상수 (cycle220 rig 공유)
TICKER = "111770"
BUY = 86_800
ATR = 4_736.0
PCT_BACKSTOP = int(BUY * 0.92)          # 79,856  (§1 −8%)
ATR_FLOOR = int(BUY - 2.0 * ATR)        # 77,328  (§2 2ATR)


def _kojiro(**extra) -> KojiroStrategy:
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.6, params=extra),
    )
    s.state.total_investment = 690_111
    return s


def _hold(
    s: KojiroStrategy,
    ticker: str = TICKER,
    *,
    buy: int = BUY,
    high: int | None = None,
    atr: float | None = ATR,
    buy_date: date | None = None,
) -> Position:
    """보유 포지션 + live ATR candidate. `high=None` → high_since_buy = buy."""
    pos = Position(
        ticker=ticker, buy_price=buy, quantity=1, order_no="O", strategy_id="kojiro",
    )
    pos.high_since_buy = buy if high is None else high
    if buy_date is not None:
        pos.buy_date = buy_date
    s.state.positions[ticker] = pos
    if atr is not None:
        s._candidates[ticker] = {"atr": atr, "stage": 1, "prev_close": buy}
    return pos


def _skip_logs(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if "[kojiro_stage3_stale_skip]" in r.getMessage()]


def _msgs(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records]


# ═══════════════════════════════════════════════════════════════════════════
# B1 — 소비 판정 (날짜 키)
# ═══════════════════════════════════════════════════════════════════════════


@freeze_time(_UTC_D1_0910)
def test_stage3_when_judged_today_true_then_trailing_stop_with_judged_on(caplog):
    """B1-1 [RED] `(오늘, True)` → §3 발화 + `[kojiro_stage3_exit]` 에 judged_on 필드.

    기존 계약(오늘 판정이면 던진다) 보존 + 사후 복기용 필드 추가.
    문구 **앞부분은 byte 보존** — 운영자 한글 grep 이력이 끊기면 안 된다.
    """
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_TODAY, True)

    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    assert s.check_exit_signal(TICKER, BUY, BUY) == Signal.TRAILING_STOP

    exits = [m for m in _msgs(caplog) if "[kojiro_stage3_exit]" in m]
    assert len(exits) == 1, "§3 발화 시 기존 로그 1행"
    assert exits[0].startswith(f"[kojiro_stage3_exit] {TICKER} 스테이지3 진입 (추세 종료)"), (
        "문구 앞부분 byte 보존 (운영자 grep 이력 연속성)"
    )
    assert "judged_on=2026-08-27" in exits[0], "판정일 노출 = '그 청산이 오늘 데이터였나' 즉답"


@freeze_time(_UTC_D1_0910)
def test_stage3_when_judged_yesterday_true_then_not_fired(caplog):
    """B1-2 [RED] `(어제, True)` → §3 **미발화**.

    억제는 "플래그를 False 로 덮어쓰기"가 아니라 "판정일이 오늘이 아니면 발화하지
    않는다" 다. 현행(날짜 무관 소비)에선 TRAILING_STOP → FAIL = 결함 실증.
    """
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)

    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    assert s.check_exit_signal(TICKER, BUY, BUY) == Signal.NONE
    assert not [m for m in _msgs(caplog) if "[kojiro_stage3_exit]" in m]


@freeze_time(_UTC_D1_0910)
def test_stage3_when_judged_today_false_then_no_fire_and_no_skip_log(caplog):
    """B1-3 [RED] `(오늘, False)` = 정상 미발화 → 억제 로그 **0**.

    현행은 `if self._held_stage3.get(ticker):` 라 **비어 있지 않은 튜플을 전부 참**으로
    읽는다 — 형태만 바꾸고 판정을 안 고치면 `False` 판정이 오히려 청산을 만든다.
    """
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_TODAY, False)

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    assert s.check_exit_signal(TICKER, BUY, BUY) == Signal.NONE
    assert _skip_logs(caplog) == [], "stage3 아님 = 정상 = 관측 대상 아님(신호 희석 차단)"


@freeze_time(_UTC_D1_0910)
def test_stage3_when_entry_absent_then_no_fire_and_no_skip_log(caplog):
    """B1-4 [가드] 엔트리 부재(미판정 종목) → 미발화 + 억제 로그 0."""
    s = _kojiro()
    _hold(s)

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    assert s.check_exit_signal(TICKER, BUY, BUY) == Signal.NONE
    assert _skip_logs(caplog) == []


@freeze_time(_UTC_D1_0910)
def test_stale_suppression_preserves_stored_entry():
    """B1-5 [RED] 억제가 값을 덮어쓰지 않는다 — 관측/사후 복기 가능해야 한다.

    hot path 부작용 금지 계약이기도 하다(청산 판정이 상태를 바꾸지 않는다).
    """
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)

    s.check_exit_signal(TICKER, BUY, BUY)
    assert s._held_stage3[TICKER] == (D_YESTERDAY, True), (
        "억제 = 발화 안 함이지 False 덮어쓰기가 아니다"
    )


@freeze_time(_UTC_D1_0910)
def test_on_position_closed_pops_tuple_entry():
    """B1-6 [가드] 형태 전환 후에도 `on_position_closed` pop 정상."""
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_TODAY, True)
    s._stop_floor[TICKER] = ATR_FLOOR

    s.on_position_closed(TICKER)
    assert TICKER not in s._held_stage3
    assert TICKER not in s._stop_floor


# ═══════════════════════════════════════════════════════════════════════════
# B2 — 억제 관측 (`[kojiro_stage3_stale_skip]`)
# ═══════════════════════════════════════════════════════════════════════════


@freeze_time(_UTC_D1_0910)
def test_stale_skip_age_one_day_is_info(caplog):
    """B2-1 [RED] age_days=1 → **INFO** 1행 (부팅 지연·일봉 결손 = 정상 범주)."""
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    s.check_exit_signal(TICKER, BUY, BUY)

    recs = _skip_logs(caplog)
    assert len(recs) == 1, "억제는 정의상 '아무 일도 안 일어남' — 로그가 없으면 판독 불가"
    msg = recs[0].getMessage()
    assert f"ticker={TICKER}" in msg
    assert "judged_on=2026-08-26" in msg
    assert "age_days=1" in msg
    assert recs[0].levelno == logging.INFO, "하루 미판정은 정상 범주 → INFO"


@freeze_time(_UTC_D1_0910)
def test_stale_skip_age_two_days_is_warning(caplog):
    """B2-2 [RED] age_days=2 → **WARNING** (데이터 파이프라인 고장 = 사람이 봐야 한다).

    `logger.debug` 단독은 `_DbLogHandler` INFO 컷을 못 넘어 `system_logs` 에 도달하지
    않는다(cycle225 교훈) — WARNING 은 DB 에 남는다.
    """
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_TWO_AGO, True)

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    s.check_exit_signal(TICKER, BUY, BUY)

    recs = _skip_logs(caplog)
    assert len(recs) == 1
    assert "age_days=2" in recs[0].getMessage()
    assert recs[0].levelno == logging.WARNING


@freeze_time(_UTC_D1_0910)
def test_stale_skip_capped_once_per_ticker_per_day(caplog):
    """B2-3 [RED] 같은 종목 같은 날 10회 평가 → 로그 **1행** (틱 폭주 차단)."""
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    for _ in range(10):
        assert s.check_exit_signal(TICKER, BUY, BUY) == Signal.NONE

    assert len(_skip_logs(caplog)) == 1


def test_stale_skip_cap_resets_on_new_day(caplog):
    """B2-4 [RED] 날짜 넘기면 다시 1행 — **날짜 키 자기 리셋**.

    `_reset_daily_state` 훅에 의존하지 않는다(kojiro 는 그 override 자체가 금지다 —
    `_stop_floor` 밤샘 보존). cycle224/227/228 날짜 키 관례.
    """
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    with freeze_time(_UTC_D1_0910):
        for _ in range(3):
            s.check_exit_signal(TICKER, BUY, BUY)
        assert len(_skip_logs(caplog)) == 1

    with freeze_time(_UTC_D2_0910):
        for _ in range(3):
            s.check_exit_signal(TICKER, BUY, BUY)
        assert len(_skip_logs(caplog)) == 2, "다음 날 첫 억제는 다시 1행"


@freeze_time(_UTC_D1_0910)
def test_stale_skip_cap_key_is_per_ticker(caplog):
    """B2-5 [RED] cap 키 = ticker — 두 종목이면 2행 (한 종목이 다른 종목을 삼키지 않는다)."""
    s = _kojiro()
    _hold(s, TICKER)
    _hold(s, "005930", buy=70_000)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)
    s._held_stage3["005930"] = (D_YESTERDAY, True)

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    s.check_exit_signal(TICKER, BUY, BUY)
    s.check_exit_signal("005930", 70_000, 70_000)

    tickers = {r.getMessage().split("ticker=")[1].split()[0] for r in _skip_logs(caplog)}
    assert tickers == {TICKER, "005930"}


# ═══════════════════════════════════════════════════════════════════════════
# B3 — 억제가 §1/§2/§4 를 막지 않는다 (자문 Q1 비대칭 비용의 전제)
# ═══════════════════════════════════════════════════════════════════════════


@freeze_time(_UTC_D1_0910)
def test_stale_suppression_keeps_hard_stop_backstop():
    """B3-1 [가드] stale 억제해도 §1 −8% 백스톱은 그대로 발화."""
    s = _kojiro()
    _hold(s)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)

    assert s.check_exit_signal(TICKER, PCT_BACKSTOP, BUY) == Signal.STOP_LOSS


@freeze_time(_UTC_D1_0910)
def test_stale_suppression_keeps_chandelier_trailing(caplog):
    """B3-2 [RED] stale 억제해도 §4 샹들리에는 살아 있다 — 같은 시그널이라도 **경로가 다르다**.

    고점 100,000 → 샹들리에 = 100,000 − 2.5×4,736 = 88,160.
    §3 가 억제되고 §4 가 잡는 것이 억제의 실제 비용 구조(체감 −1~3% × 1일)다.
    """
    s = _kojiro()
    _hold(s, high=100_000)
    s._held_stage3[TICKER] = (D_YESTERDAY, True)

    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    assert s.check_exit_signal(TICKER, 88_160, BUY) == Signal.TRAILING_STOP

    msgs = _msgs(caplog)
    assert any("[kojiro_trailing]" in m for m in msgs), "§4 가 잡아야 한다"
    assert not any("[kojiro_stage3_exit]" in m for m in msgs), "§3 는 억제된 상태"


# ═══════════════════════════════════════════════════════════════════════════
# B4 — 기록 형식 (prepare 1곳 + recompute 5곳)
# ═══════════════════════════════════════════════════════════════════════════


async def test_prepare_records_date_tuple_when_held_stage3(kojiro_fx, monkeypatch):
    """B4-1 [RED] `prepare()` 보유+stage3 → `(오늘, True)` 튜플 기록."""
    _pos(kojiro_fx, "005930", buy_price=10000)
    await _run_prepare(kojiro_fx, monkeypatch, "005930",
                       _enriched([2, 3], close=10000, atr=200.0))
    assert kojiro_fx._held_stage3["005930"] == (datetime.now(KST).date(), True)


async def test_prepare_records_date_tuple_false_when_not_stage3(kojiro_fx, monkeypatch):
    """B4-2 [RED] `prepare()` 보유+stage≠3 → `(오늘, False)`.

    "오늘 재판정했고 stage3 아니다" 와 "오늘 재판정을 못 했다" 는 다른 사실이다.
    """
    _pos(kojiro_fx, "005930", buy_price=10000)
    await _run_prepare(kojiro_fx, monkeypatch, "005930",
                       _enriched([2, 1], close=10000, atr=200.0))
    assert kojiro_fx._held_stage3["005930"] == (datetime.now(KST).date(), False)


@freeze_time(_UTC_D1_0910)
async def test_recompute_records_date_tuple_when_stage3(kojiro_fx, monkeypatch):
    """B4-3 [RED] `recompute_held_atr` 성공 경로 → `(오늘, True)`."""
    _hold(kojiro_fx, "005930", buy=10_000, atr=None, buy_date=D_TODAY)
    monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily_normalized",
                        AsyncMock(return_value=_dummy_candles()))
    monkeypatch.setattr(kmod, "enrich",
                        lambda df, cfg: _enriched([1, 3], close=10000, atr=200.0))
    monkeypatch.setattr(kojiro_fx, "_fetch_sector", AsyncMock(return_value=""))

    await kojiro_fx.recompute_held_atr()
    assert kojiro_fx._held_stage3["005930"] == (D_TODAY, True)


@freeze_time(_UTC_D1_0910)
@pytest.mark.parametrize("mode", ["fetch_raises", "empty_candles", "warmup_short", "enrich_raises"])
async def test_recompute_fail_open_paths_record_today_false(kojiro_fx, monkeypatch, mode):
    """B4-4 [RED] recompute 실패 4경로가 형태 전환 후에도 `(오늘, False)` fail-open 유지.

    `kojiro.py:649` docstring 이 명문 계약으로 적어 둔 것 — 이번 시정은 신설 정책이
    아니라 **그 계약을 prepare 경로에도 적용하는 일관화**다.
    """
    _hold(kojiro_fx, "005930", buy=10_000, atr=None, buy_date=D_TODAY)

    if mode == "fetch_raises":
        candles_mock = AsyncMock(side_effect=RuntimeError("boom"))
    elif mode == "empty_candles":
        candles_mock = AsyncMock(return_value=[])
    elif mode == "warmup_short":
        candles_mock = AsyncMock(return_value=_dummy_candles(n=10))
    else:
        candles_mock = AsyncMock(return_value=_dummy_candles())
    monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily_normalized", candles_mock)

    def _enrich(df, cfg):
        if mode == "enrich_raises":
            raise RuntimeError("boom")
        return _enriched([1, 3], close=10000, atr=200.0)

    monkeypatch.setattr(kmod, "enrich", _enrich)
    monkeypatch.setattr(kojiro_fx, "_fetch_sector", AsyncMock(return_value=""))

    await kojiro_fx.recompute_held_atr()
    assert kojiro_fx._held_stage3["005930"] == (D_TODAY, False)


# ═══════════════════════════════════════════════════════════════════════════
# B5 — 설계 의도 보존 ("익일 아침 발화" 는 죽지 않는다)
# ═══════════════════════════════════════════════════════════════════════════


async def test_evening_judgement_is_rearmed_by_next_morning_recompute(kojiro_fx, monkeypatch):
    """B5 [RED] D 저녁 판정 → D+1 아침엔 억제 → **D+1 recompute 후 발화**.

    자문에서 가장 중요한 검증. 16:20 evening prepare 가 D 날짜로 True 를 찍고
    D+1 09:00 에 소비되면 날짜 불일치로 억제된다 — 언뜻 "익일 아침 발화" 설계를
    죽이는 것처럼 보이지만 **죽지 않는다**. D+1 07:55 boot 의 `recompute_held_atr`
    이 같은 D 확정봉으로 다시 판정해 **D+1 날짜로** 기록하고, 그 뒤 09:00 부터
    소비된다. 즉 날짜 키는 "오늘 아침 재판정이 성공했는가" 의 정확한 프록시다.
    """
    monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily_normalized",
                        AsyncMock(return_value=_dummy_candles()))
    monkeypatch.setattr(kmod, "enrich",
                        lambda df, cfg: _enriched([1, 3], close=10000, atr=200.0))
    monkeypatch.setattr(kojiro_fx, "_fetch_sector", AsyncMock(return_value=""))

    with freeze_time(_UTC_D1_0910):
        _hold(kojiro_fx, TICKER, buy_date=D_TODAY)
        # D-1 저녁 prepare 가 남긴 판정 (D+1 아침 recompute 아직 안 돎)
        kojiro_fx._held_stage3[TICKER] = (D_YESTERDAY, True)
        assert kojiro_fx.check_exit_signal(TICKER, BUY, BUY) == Signal.NONE, (
            "오늘 재판정 전 = 억제"
        )

        await kojiro_fx.recompute_held_atr()
        assert kojiro_fx._held_stage3[TICKER] == (D_TODAY, True), "아침 재판정이 재무장"
        assert kojiro_fx.check_exit_signal(TICKER, BUY, BUY) == Signal.TRAILING_STOP, (
            "익일 아침 발화 설계 보존"
        )


# ═══════════════════════════════════════════════════════════════════════════
# B6 — W3 부수 방어 (매매 무변경, cycle226 L-2 동형)
# ═══════════════════════════════════════════════════════════════════════════


@freeze_time(_UTC_D1_0910)
async def test_recompute_bad_buy_date_does_not_kill_following_positions(
    kojiro_fx, monkeypatch, caplog,
):
    """B6-1 [RED] 첫 종목 `buy_date` 가 date 가 아니어도 **둘째 종목 재계산이 생존**.

    `kojiro.py:685` `if pos is not None and pos.buy_date < today:` 는 per-ticker try
    **밖**이다. `buy_date` 가 str 이면 TypeError 가 루프를 뚫고 나가 그 뒤 보유 종목의
    ATR/stage/stage3/floor 재계산이 통째 유실된다(donchian 은 `no_buy_date` 사유로
    명시 방어하는데 kojiro 는 안 한다). 현재 잠복이지만 방향이 **청산 약화**다.
    """
    bad = _hold(kojiro_fx, "000660", buy=10_000, atr=None)
    bad.buy_date = "2026-08-26"          # date 아님 (레거시/역직렬화 오염 재현)
    _hold(kojiro_fx, "005930", buy=10_000, atr=None, buy_date=D_TODAY)

    monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily_normalized",
                        AsyncMock(return_value=_dummy_candles()))
    monkeypatch.setattr(kmod, "enrich",
                        lambda df, cfg: _enriched([1, 3], close=10000, atr=200.0))
    monkeypatch.setattr(kojiro_fx, "_fetch_sector", AsyncMock(return_value=""))

    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    await kojiro_fx.recompute_held_atr()   # 현행: TypeError 전파 → FAIL

    assert kojiro_fx._held_stage3.get("005930") == (D_TODAY, True), (
        "뒤 종목 재판정이 앞 종목의 오염 데이터로 유실되면 안 된다"
    )
    assert "005930" in kojiro_fx._candidates
    assert kojiro_fx._position_atr.get("005930") == 200.0
    assert any(
        r.levelno >= logging.WARNING
        and "[kojiro_recompute]" in r.getMessage()
        and "000660" in r.getMessage()
        for r in caplog.records
    ), "무흔적 흡수 금지 — 어느 종목이 왜 빠졌는지 남긴다"


# ═══════════════════════════════════════════════════════════════════════════
# B7 — AST 가드 (⚠️ 자기 공허화 주의 — cycle224/226 교훈)
# ═══════════════════════════════════════════════════════════════════════════


def _names(nodes) -> set[str]:
    out: set[str] = set()
    for n in nodes:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Name):
                out.add(sub.id)
            elif isinstance(sub, ast.Attribute):
                out.add(sub.attr)
    return out


def _strings(nodes) -> list[str]:
    out: list[str] = []
    for n in nodes:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.append(sub.value)
    return out


def _target_names(target) -> set[str]:
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def _local_assigns(fn) -> dict[str, list]:
    """지역 대입 `name -> 값 노드들` — 튜플 언패킹 포함(전이 추적용)."""
    out: dict[str, list] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                for name in _target_names(t):
                    out.setdefault(name, []).append(node.value)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            for name in _target_names(node.target):
                out.setdefault(name, []).append(node.value)
    return out


def _expand(nodes, assigns: dict[str, list], limit: int = 8) -> set[str]:
    """표현식이 참조하는 이름을 **지역 대입을 전이적으로 되짚어** 확장.

    한 단계만 보면 `entry = self._held_stage3.get(t)` / `today = ...date()` 처럼
    조건식이 지역변수를 경유하는 순간 가드가 눈이 먼다(cycle226 L-2 교훈).
    """
    names = _names(nodes)
    frontier = set(names)
    seen: set[str] = set()
    while frontier and limit > 0:
        limit -= 1
        nxt: set[str] = set()
        for name in frontier:
            if name in seen:
                continue
            seen.add(name)
            for value in assigns.get(name, []):
                for m in _names([value]):
                    if m not in names:
                        names.add(m)
                        nxt.add(m)
        frontier = nxt
    return names


def _stage3_guard_token_sets(src: str) -> list[set[str]]:
    """`[kojiro_stage3_exit]` 발화 지점을 감싼 **모든 조건식**의 확장 토큰 집합.

    중첩 If 로 쪼개 써도 조상 조건을 전부 모으므로 구조에 덜 민감하다.
    반환이 빈 리스트면 발화 지점 자체를 못 찾은 것(= 가드 공허) → 호출부가 실패시킨다.
    """
    fn = ast.parse(textwrap.dedent(src)).body[0]
    assigns = _local_assigns(fn)
    found: list[set[str]] = []

    def rec(node, acc: list) -> None:
        if isinstance(node, ast.If):
            for stmt in list(node.body) + list(node.orelse):
                rec(stmt, acc + [node.test])
            return
        if any("kojiro_stage3_exit" in s for s in _strings([node])):
            found.append(_expand(acc, assigns) if acc else set())
            return
        for child in ast.iter_child_nodes(node):
            rec(child, acc)

    for stmt in fn.body:
        rec(stmt, [])
    return found


_MUTATED_SRC = '''
def check_exit_signal(self, ticker, current_price, open_price):
    if self._held_stage3.get(ticker):
        logger.info("[kojiro_stage3_exit] %s 스테이지3 진입 (추세 종료)", ticker)
        return Signal.TRAILING_STOP
    return Signal.NONE
'''

_FIXED_SRC = '''
def check_exit_signal(self, ticker, current_price, open_price):
    today = datetime.now(KST).date()
    entry = self._held_stage3.get(ticker)
    if entry is not None and entry[0] == today and entry[1]:
        logger.info("[kojiro_stage3_exit] %s 스테이지3 진입 (추세 종료) judged_on=%s",
                    ticker, entry[0])
        return Signal.TRAILING_STOP
    return Signal.NONE
'''

_DATE_TOKENS = {"date", "today"}


def _is_date_aware(src: str) -> bool:
    sets = _stage3_guard_token_sets(src)
    if not sets:
        return False
    return all(
        "_held_stage3" in tokens and bool(_DATE_TOKENS & tokens) for tokens in sets
    )


def test_ast_checker_is_not_vacuous():
    """B7-1 [비-공허성 실증] 판별기가 뮤테이션을 실제로 잡는지 먼저 증명한다.

    cycle224/226 의 교훈 — 가드가 "정의상 항상 참"인 명제를 묻고 있으면 뮤테이션
    전후 모두 통과해서 아무것도 못 막는다. 이 테스트는 시정 전후 항상 PASS 해야 하며,
    B7-2(실제 소스 검사)가 의미를 갖는 전제다.
    """
    assert _is_date_aware(_MUTATED_SRC) is False, (
        "날짜 비교 제거(현행 형태) → 반드시 FAIL 판정"
    )
    assert _is_date_aware(_FIXED_SRC) is True, "날짜 동반 판정 → PASS 판정"


def test_ast_stage3_branch_is_date_aware():
    """B7-2 [RED] 실제 `check_exit_signal` 의 §3 분기가 날짜 없이 값을 읽지 않는다."""
    src = inspect.getsource(KojiroStrategy.check_exit_signal)
    assert _stage3_guard_token_sets(src), "`[kojiro_stage3_exit]` 발화 지점 미발견 = 가드 공허"
    assert _is_date_aware(src), (
        "§3 는 `_held_stage3` 값과 **판정일**을 함께 봐야 한다 "
        "(타임스탬프 없는 플래그로 시장가 매도를 던지는 것이 이번 결함이다)"
    )


def test_ast_held_stage3_writes_are_date_tuples():
    """B7-3 [RED] `_held_stage3[...] = ...` 대입은 전부 튜플 — bare bool 재발 차단.

    기록 지점은 prepare 1 + recompute 5 = 6곳. 대입 형태(subscript) 유지가 계약이다.
    """
    tree = ast.parse(inspect.getsource(kmod))
    writes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute)
                    and t.value.attr == "_held_stage3"):
                writes.append(node)
    assert len(writes) >= 6, f"기록 지점 6곳(prepare 1 + recompute 5) 유지 — 실측 {len(writes)}"
    for node in writes:
        assert isinstance(node.value, ast.Tuple), (
            "값은 `(판정 수행일, stage==3)` 튜플이어야 한다 (bare bool 금지)"
        )
        assert len(node.value.elts) == 2


def test_exit_priority_constants_unchanged():
    """B7-4 [가드] FREEZE — 억제의 대가를 트레일링 조임으로 메우지 말 것(도메인 금기)."""
    d = KojiroStrategy.DEFAULT_PARAMS
    assert d["trail_atr"] == 2.5, "§4 샹들리에 2.5 불변 (fat-tail 절단 금지)"
    assert d["stop_atr"] == 2.0
    assert d["hard_stop_pct"] == -8.0


def test_check_buy_signal_untouched_by_stage3_date_key():
    """B7-4 [가드] 진입 로직 무접촉 (FREEZE — 이번 건은 청산 판정 유효성 한정)."""
    src = inspect.getsource(KojiroStrategy.check_buy_signal)
    assert "_held_stage3" not in src
    assert "stale" not in src.lower()


def test_no_reset_daily_state_override():
    """B7-4 [가드] cap 은 **날짜 키 자기 리셋** — `_reset_daily_state` 훅 신설 금지.

    override 를 추가하면 멀티데이 보유의 `_stop_floor`(브레이크이븐 승격선)가
    20:10 정산에 소멸한다(기존 AST 봉인).
    """
    assert "_reset_daily_state" not in KojiroStrategy.__dict__


@pytest.fixture
def kojiro_fx() -> KojiroStrategy:
    return KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로 대순환", weight=0.2),
    )
