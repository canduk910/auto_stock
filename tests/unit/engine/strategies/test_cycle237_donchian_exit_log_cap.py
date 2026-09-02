"""사이클 237 Red — donchian 청산 계열 관측 로그 폭주 cap.

## 왜 (실측)

2026-08-31 · 09-01 운영 로그 실측:

    2026-08-31  [donchian_breakeven_promote] 192820  : 11,453건 (전체 31,064행의 36.9%)
    2026-09-01  [donchian_breakeven_promote] 192820  :  9,027건 (전체 17,698행의 51.0%)
    2026-09-02  도치안 시간 기반 청산 034020            :     68건 (08:00~09:00 프리마켓)

**단일 종목 하나가 하루 1만 건**을 찍었고, 그게 그날 `system_logs` 의 절반이다.

## 근본 원인 — 래칫 부재

kojiro 의 같은 승격(`[kojiro_breakeven_promote]`)은 **자연히 1회**다. 승격 결과를
`self._stop_floor[ticker] = eff` 로 **영속**하므로 다음 틱엔 `promoted == eff` 가 되어
`if promoted != eff:` 가 거짓이 된다.

donchian 은 그 래칫이 없다 — `base_stop` 을 매 틱 `buy_price - stop_atr × entry_atr` 로
**재계산**하므로 `base_stop < buy_price` 인 한 `promoted_stop != base_stop` 이 **영원히 참**이다.
승격 자체는 매 틱 올바르게 일어나고(결과 동일), 로그만 무한 반복된다.

시간청산(`도치안 시간 기반 청산`)은 성격이 다르다 — `Signal.STOP_LOSS` 를 반환하므로
정상 흐름에선 1회지만, **매도가 거부되면**(034020 = 프리마켓 APBK0918) 포지션이 살아남아
매 틱 재발화한다. 매도 실패 사실 자체는 `[market_closed_blocked]` 가 이미 1회/일 cap 으로
기록하므로, 이 로그를 cap 해도 관측 손실이 없다.

## 인터페이스 계약

1. **cap 은 로그에만 건다. 행위는 절대 cap 밖.**
   - breakeven 승격 계산(`base_stop = promoted_stop`)은 매 틱 그대로 수행된다.
   - 시간청산 `return Signal.STOP_LOSS` 는 매 틱 그대로 반환된다.
   이게 이 사이클의 **핵심 계약**이다. cap 이 청산을 한 번만 시도하게 만들면
   그건 관측 시정이 아니라 **매매 결함 주입**이다.

2. `DailyEmitCap[str]` 1회/ticker/일, 두 마커 **각각 별개 인스턴스**.
   날짜 키 자기 리셋(`_days_held_observe_day` 선례) — `_reset_daily_state` 훅 미의존.

3. 관측 순서 = **peek → 로그 → mark** (cycle226 D-3). 로그가 던져도 cap 이 소비되지
   않아야 그 종목이 종일 봉인되지 않는다.

4. 어떤 예외도 흡수 — 관측 실패가 청산 판정을 막지 않는다.

## Red 유효성 (production 미변경 시점)

- BE-1/BE-3/BE-4, TE-1/TE-3/TE-4 = FAIL (cap 부재 → N틱 = N행)
- BE-2, TE-2 = PASS (행위 가드 — 구현 후에도 계속 PASS 해야 한다)
- BE-5, TE-5 = 구현 후에야 유효(cap 헬퍼가 생겨야 poison 이 발화)
"""

from __future__ import annotations

import datetime as _dt
import logging

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.strategies.donchian_swing"
_BE = "[donchian_breakeven_promote]"
_EXIT = "도치안 시간 기반 청산"

D = _dt.date


# ===========================================================================
# rig
# ===========================================================================
def _mk(**params) -> DonchianSwingStrategy:
    cfg = StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={
            "sizing_mode": "position_ratio",
            "breakout_fail_n_days": 2,
            "stop_atr": 2.0,
            "breakeven_promote_atr": 1.5,
            "turtle_backstop_pct": -9.0,
            "channel_exit_period": 0,
            **params,
        },
    )
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _arm_breakeven(s, ticker="192820", buy_price=273_500, atr=11_185.0):
    """브레이크이븐 승격이 성립하는 최소 상태.

    high_since_buy >= buy + 1.5×atr  ⇒ 승격 발화.
    base_stop = buy - 2.0×atr < buy  ⇒ promoted != base ⇒ (cap 없으면) 매 틱 로그.
    """
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=1, order_no="O",
                   strategy_id="donchian_swing", buy_date=D(2026, 8, 24))
    pos.high_since_buy = int(buy_price + 2.0 * atr)  # 1.5×ATR 초과
    s.state.positions[ticker] = pos
    s._entry_atr[ticker] = atr          # 터틀 손절 분기 활성(스탬프 존재)
    s._breakout_high[ticker] = 0        # 시간청산 미무장(격리)
    return pos


def _arm_time_exit(s, ticker="034020", buy_price=83_600, breakout_high=87_700):
    """시간청산이 매 틱 발화하는 상태(매도 거부로 포지션 잔존 가정)."""
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=1, order_no="O",
                   strategy_id="donchian_swing", buy_date=D(2026, 8, 31))
    pos.high_since_buy = buy_price
    s.state.positions[ticker] = pos
    s._breakout_high[ticker] = breakout_high
    s._trading_days = {D(2026, 8, 31), D(2026, 9, 1), D(2026, 9, 2)}
    return pos


def _lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


# ===========================================================================
# BE — 브레이크이븐 승격 로그 cap
# ===========================================================================
@freeze_time("2026-09-01 10:00:00")
def test_be_1_promote_log_capped_once_per_day(caplog):
    """BE-1 (핵심) — 100틱 평가에도 승격 로그는 하루 1행."""
    s = _mk()
    pos = _arm_breakeven(s)
    above = pos.buy_price + 2_000  # 승격 손절선 위 → STOP_LOSS 아님

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for _ in range(100):
            s.check_exit_signal(pos.ticker, above, 0)

    got = _lines(caplog, _BE)
    assert len(got) == 1, f"승격 로그 1행 기대 — got {len(got)}행 (실측 폭주 재현)"


@freeze_time("2026-09-01 10:00:00")
def test_be_2_promotion_behavior_unchanged_by_cap(caplog):
    """BE-2 (행위 가드) — cap 이 걸려도 승격 자체는 매 틱 유효하다.

    cap 이 승격 **계산**까지 건너뛰면 손절선이 `buy - 2ATR` 로 되돌아가
    `buy - 1` 에서 STOP_LOSS 가 안 나온다. 그건 관측 시정이 아니라 손절 약화다.
    """
    s = _mk()
    pos = _arm_breakeven(s)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for _ in range(50):
            assert s.check_exit_signal(pos.ticker, pos.buy_price + 2_000, 0) == Signal.NONE
        # 51번째 틱 — 승격 손절선(=매수가) 바로 아래
        sig = s.check_exit_signal(pos.ticker, pos.buy_price - 1, 0)

    assert sig == Signal.STOP_LOSS, (
        "cap 이후에도 승격된 손절선(=매수가)이 유지돼야 한다 — "
        "NONE 이면 cap 이 승격 계산을 건너뛴 것(손절 약화)"
    )


def test_be_3_promote_log_resets_next_day(caplog):
    """BE-3 — 날짜가 바뀌면 다시 1행(cap 자기 리셋)."""
    s = _mk()
    pos = _arm_breakeven(s)
    above = pos.buy_price + 2_000

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        with freeze_time("2026-09-01 10:00:00"):
            for _ in range(5):
                s.check_exit_signal(pos.ticker, above, 0)
        with freeze_time("2026-09-02 10:00:00"):
            for _ in range(5):
                s.check_exit_signal(pos.ticker, above, 0)

    got = _lines(caplog, _BE)
    assert len(got) == 2, f"이틀 = 2행 기대 — got {len(got)}: {got}"


@freeze_time("2026-09-01 10:00:00")
def test_be_4_promote_cap_is_per_ticker(caplog):
    """BE-4 — cap 키는 ticker 단위(한 종목이 다른 종목을 삼키지 않는다)."""
    s = _mk()
    a = _arm_breakeven(s, ticker="192820", buy_price=273_500, atr=11_185.0)
    b = _arm_breakeven(s, ticker="005930", buy_price=70_000, atr=1_500.0)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for _ in range(10):
            s.check_exit_signal(a.ticker, a.buy_price + 2_000, 0)
            s.check_exit_signal(b.ticker, b.buy_price + 2_000, 0)

    got = _lines(caplog, _BE)
    assert len(got) == 2, f"2종목 = 2행 기대 — got {len(got)}: {got}"
    assert any("192820" in ln for ln in got)
    assert any("005930" in ln for ln in got)


@freeze_time("2026-09-01 10:00:00")
def test_be_5_promote_log_failure_does_not_break_exit(monkeypatch, caplog):
    """BE-5 — 관측기가 던져도 청산 판정은 정상 수행된다(예외 흡수)."""
    s = _mk()
    pos = _arm_breakeven(s)

    import src.engine.strategies.donchian_swing as _mod

    real_info = _mod.logger.info

    def _poison(msg, *args, **kwargs):
        if isinstance(msg, str) and "breakeven_promote" in msg:
            raise RuntimeError("관측기 폭발")
        return real_info(msg, *args, **kwargs)

    monkeypatch.setattr(_mod.logger, "info", _poison)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        sig = s.check_exit_signal(pos.ticker, pos.buy_price - 1, 0)

    assert sig == Signal.STOP_LOSS, "관측 실패가 승격·손절을 무력화하면 안 된다"


# ===========================================================================
# TE — 시간청산 로그 cap (신호 반환은 cap 밖)
# ===========================================================================
@freeze_time("2026-09-02 08:30:00")
def test_te_1_time_exit_log_capped_once_per_day(caplog):
    """TE-1 (핵심) — 매도 거부로 20틱 재평가돼도 로그는 하루 1행."""
    s = _mk()
    pos = _arm_time_exit(s)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for _ in range(20):
            s.check_exit_signal(pos.ticker, 79_600, 0)

    got = _lines(caplog, _EXIT)
    assert len(got) == 1, f"시간청산 로그 1행 기대 — got {len(got)}행"


@freeze_time("2026-09-02 08:30:00")
def test_te_2_signal_returned_every_tick_despite_cap(caplog):
    """TE-2 (핵심 행위 가드) — 로그는 1행이어도 **신호는 매 틱** 반환된다.

    cap 이 `return Signal.STOP_LOSS` 까지 막으면 매도 거부 후 재시도가 끊겨
    포지션이 청산되지 못한 채 잔존한다 = 매매 결함 주입.
    """
    s = _mk()
    pos = _arm_time_exit(s)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        sigs = [s.check_exit_signal(pos.ticker, 79_600, 0) for _ in range(20)]

    assert all(x == Signal.STOP_LOSS for x in sigs), (
        f"20틱 모두 STOP_LOSS 여야 한다 — got {sigs.count(Signal.STOP_LOSS)}/20"
    )
    assert len(_lines(caplog, _EXIT)) == 1


def test_te_3_time_exit_log_resets_next_day(caplog):
    """TE-3 — 날짜 자기 리셋."""
    s = _mk()
    pos = _arm_time_exit(s)
    s._trading_days |= {D(2026, 9, 3)}

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        with freeze_time("2026-09-02 08:30:00"):
            for _ in range(3):
                s.check_exit_signal(pos.ticker, 79_600, 0)
        with freeze_time("2026-09-03 08:30:00"):
            for _ in range(3):
                s.check_exit_signal(pos.ticker, 79_600, 0)

    got = _lines(caplog, _EXIT)
    assert len(got) == 2, f"이틀 = 2행 기대 — got {len(got)}: {got}"


@freeze_time("2026-09-02 08:30:00")
def test_te_4_time_exit_cap_is_per_ticker(caplog):
    """TE-4 — ticker 단위 cap."""
    s = _mk()
    a = _arm_time_exit(s, ticker="034020", buy_price=83_600, breakout_high=87_700)
    b = _arm_time_exit(s, ticker="088350", buy_price=5_790, breakout_high=5_730)

    # ⚠️ 가격은 §1 하드손절(-7%)보다 **위**, 돌파선보다 **아래**여야 시간청산 분기에
    #    도달한다. 손절이 먼저 발화하면 시간청산 로그가 아예 안 나온다.
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for _ in range(5):
            s.check_exit_signal(a.ticker, 79_600, 0)   # -4.8%, 돌파선 87,700 아래
            s.check_exit_signal(b.ticker, 5_700, 0)    # -1.6%, 돌파선 5,730 아래

    got = _lines(caplog, _EXIT)
    assert len(got) == 2, f"2종목 = 2행 기대 — got {len(got)}: {got}"


@freeze_time("2026-09-02 08:30:00")
def test_te_5_time_exit_log_failure_does_not_break_signal(monkeypatch):
    """TE-5 — 관측기가 던져도 STOP_LOSS 는 반환된다."""
    s = _mk()
    pos = _arm_time_exit(s)

    import src.engine.strategies.donchian_swing as _mod

    real_info = _mod.logger.info

    def _poison(msg, *args, **kwargs):
        if isinstance(msg, str) and "시간 기반 청산" in msg:
            raise RuntimeError("관측기 폭발")
        return real_info(msg, *args, **kwargs)

    monkeypatch.setattr(_mod.logger, "info", _poison)

    assert s.check_exit_signal(pos.ticker, 79_600, 0) == Signal.STOP_LOSS, (
        "관측 실패가 시간청산 신호를 삼키면 안 된다"
    )


# ===========================================================================
# 적대 검증 후속 (C237-F2 / L3-2 / L3-3 / L3-4) — 계약 §2·§3·§5 회귀 가드
# ===========================================================================
def _poison_once(monkeypatch, needle: str):
    """`logger.info` 가 `needle` 포함 메시지에서 **1회만** 던지게 만든다."""
    import src.engine.strategies.donchian_swing as _mod

    real = _mod.logger.info
    state = {"fired": False}

    def _p(msg, *a, **kw):
        if not state["fired"] and isinstance(msg, str) and needle in msg:
            state["fired"] = True
            raise RuntimeError("emit 실패")
        return real(msg, *a, **kw)

    monkeypatch.setattr(_mod.logger, "info", _p)
    return state


@freeze_time("2026-09-01 10:00:00")
def test_be_6_failed_emit_does_not_consume_cap(monkeypatch, caplog):
    """BE-6 (C237-F2/L3-2) — 계약 §3: peek → 로그 → **mark**.

    로그가 던진 시도는 cap 을 소비하면 안 된다. mark-before-log 로 표류하면
    그날 첫 승격 틱의 일시적 emit 실패가 그 종목을 **종일 봉인**한다.
    """
    s = _mk()
    pos = _arm_breakeven(s)
    above = pos.buy_price + 2_000

    st = _poison_once(monkeypatch, "breakeven_promote")
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        s.check_exit_signal(pos.ticker, above, 0)      # 1회차 — emit 실패
        assert st["fired"], "poison 이 발화하지 않았다(테스트 무효)"
        assert not _lines(caplog, _BE), "실패한 시도가 로그를 남기면 안 된다"
        s.check_exit_signal(pos.ticker, above, 0)      # 2회차 — 정상 emit

    got = _lines(caplog, _BE)
    assert len(got) == 1, (
        f"실패 시도가 cap 을 소비하면 안 된다(mark-before-log 회귀) — got {len(got)}행"
    )


@freeze_time("2026-09-02 08:30:00")
def test_te_6_failed_emit_does_not_consume_cap(monkeypatch, caplog):
    """TE-6 (C237-F2/L3-2) — 시간청산 쪽 동형 가드."""
    s = _mk()
    pos = _arm_time_exit(s)

    st = _poison_once(monkeypatch, "시간 기반 청산")
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        assert s.check_exit_signal(pos.ticker, 79_600, 0) == Signal.STOP_LOSS
        assert st["fired"]
        assert not _lines(caplog, _EXIT)
        assert s.check_exit_signal(pos.ticker, 79_600, 0) == Signal.STOP_LOSS

    assert len(_lines(caplog, _EXIT)) == 1, "실패 시도가 cap 을 소비했다"


@freeze_time("2026-09-02 10:00:00")
def test_cap_instances_are_separate_per_marker(caplog):
    """C237-L3-3 — 계약 §2: 두 마커는 **별개 cap 인스턴스**(OB-11).

    한 종목이 같은 날 승격과 시간청산에 **모두** 무장될 수 있다. cap 을 공유하면
    먼저 찍힌 쪽이 다른 쪽을 삼켜 "왜 청산했는가"의 유일한 기록이 사라진다.
    """
    s = _mk()
    atr = 1_000.0
    buy = 100_000
    pos = Position(ticker="192820", buy_price=buy, quantity=1, order_no="O",
                   strategy_id="donchian_swing", buy_date=D(2026, 8, 31))
    pos.high_since_buy = int(buy + 2.0 * atr)      # 승격 성립
    s.state.positions[pos.ticker] = pos
    s._entry_atr[pos.ticker] = atr
    s._breakout_high[pos.ticker] = 120_000          # 시간청산도 무장
    s._trading_days = {D(2026, 8, 31), D(2026, 9, 1), D(2026, 9, 2)}

    # 가격은 승격 손절선(=매수가) **위**, 돌파선 **아래** → 두 로그가 같은 틱에 성립
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for _ in range(10):
            s.check_exit_signal(pos.ticker, buy + 500, 0)

    assert len(_lines(caplog, _BE)) == 1, "승격 로그가 시간청산 cap 에 먹혔다"
    assert len(_lines(caplog, _EXIT)) == 1, "시간청산 로그가 승격 cap 에 먹혔다"


@freeze_time("2026-09-01 10:00:00")
def test_be_7_message_format_byte_identical(caplog):
    """BE-7 (C237-L3-4) — 계약 §5: 서식 byte 동일 + 인자 순서 고정.

    행 개수만 세면 인자 전치(before↔after 등)를 못 잡는다. 승격 로그는
    `monday_activation_guide.md` §8 이 VCP/BFB 활성화를 판정하는 근거 문장이라
    값이 뒤바뀐 채 나오면 GO/NO-GO 판단이 오염된다.
    """
    s = _mk()
    atr = 11_185.0
    buy = 273_500
    pos = _arm_breakeven(s, buy_price=buy, atr=atr)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        s.check_exit_signal(pos.ticker, buy + 2_000, 0)

    line = _lines(caplog, _BE)[0]
    expected_base = int(buy - 2.0 * atr)     # 승격 전 = buy - stop_atr×ATR
    assert line.endswith(f"→ 손절선 {expected_base}→{buy}"), (
        f"인자 전치/서식 표류 — got {line!r}"
    )
    assert f"고점({pos.high_since_buy}) ≥ 매수가({buy})+1.5×ATR({int(atr)})" in line


@freeze_time("2026-09-02 08:30:00")
def test_te_7_message_format_byte_identical(caplog):
    """TE-7 (C237-L3-4) — 시간청산 서식 동형 가드."""
    s = _mk()
    pos = _arm_time_exit(s)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        s.check_exit_signal(pos.ticker, 79_600, 0)

    line = _lines(caplog, _EXIT)[0]
    assert line.endswith(
        "도치안 시간 기반 청산: 034020 보유 2영업일 ≥ 2, 현재가(79600) < 돌파선(87700)"
    ), f"서식 표류 — got {line!r}"
