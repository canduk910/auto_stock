"""사이클 229 Red — momentum 매수 컷 15:20 (명세 W2).

명세 정본 `_workspace/red/cycle229_buy_cutoff_spec.md` W2 /
자문 정본 `_workspace/domain_consult/cycle229_vb_1530_single_price.md` §4 /
행위 분해 `_workspace/red/cycle229_behaviors.md` §2.

**Red 단계 — 실패 테스트만. 프로덕션 미변경.** Green = backend-dev.

## 왜 momentum 도 같은 15:20 인가

momentum 의 가설은 "장중 +29% 돌파 → 상한가(+30%) 직행 관성 → 잠김 확인 → 익일 갭업" 이다.
그런데 momentum 은 `change_rate >= 30.0` 종목을 **애초에 제외**하므로, 종가 확정 틱으로
잡히는 표본은 `+29% ≤ x < +30%` 로 **마감**한 종목뿐 — 즉 하루 종일 상한가를 두드렸으나
**못 잠근** 종목이다. 잠겼다가 마감 동시호가에 풀려서 +29% 로 마감한 경우는 더 나쁘다
(상한가 풀림 = 약세 전환). **원 가설의 정확한 반대 표본만 남는다.**

게다가 "돌파 순간" 이라는 신호 정의 자체가 그 시각엔 성립하지 않는다 — 뒤에 남은 거래
시간이 0 이라 상한가로 갈 여지가 구조적으로 없다.

⚠️ 이 판단은 표본 없이 내린 것이다(자문 §8-4 자기 고지 — 관측된 momentum 15:2x 매수 0건).
따라서 이 파일은 **행위 계약만** 고정하고 수익성 주장은 하지 않는다.

## Green 계약 (명세 W2 — W1 동형, 단 상수 공유 금지)

- 모듈 상수 `BUY_CUTOFF_KST = time(15, 20)` — **자기 파일에 자기 상수**
  (VB 에서 import 금지 = 파일 간 결합 회피). 값만 동일.
- `check_buy_signal` 최상단, `_prev_prdy_rate` read/write **이전**:
  `datetime.now(KST).time() >= BUY_CUTOFF_KST` → `Signal.NONE`. naive 금지.
- 관측 `[momentum_buy_cutoff]` INFO 1회/일, 날짜 키 자기 리셋.

## freezegun 타임존 규약

freezegun 은 naive 문자열을 **UTC** 로 동결한다. 이 파일의 `freeze_time` 인자는 전부 UTC,
KST = UTC + 9h. 상세는 `test_cycle229_vb_buy_cutoff.py` 모듈 docstring 참조.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_TICKER = "005930"
_PREV_CLOSE = 70000
_PRIME_PRICE = 89000     # +27.14% — 임계(29.0) 미만, 기록만
# +29.01% — 돌파 순간. 90,300(정확히 +29%)은 부동소수 오차로 28.999999999999996 이 되어
# `change_rate >= threshold` 를 통과하지 못한다. 임계 경계 자체는 이 사이클의 검정 대상이
# 아니므로(사이클 212 가 `buy_threshold` 를 정체성 상수로 봉인) 여유를 두고 잡는다.
_BREAKOUT_PRICE = 90310
_CUTOFF_MARKER = "[momentum_buy_cutoff]"
_MOMENTUM_LOGGER = "src.engine.strategies.momentum"

_UTC_KST_151959 = "2026-08-28 06:19:59"
_UTC_KST_152000 = "2026-08-28 06:20:00"
_UTC_KST_152500 = "2026-08-28 06:25:00"
_UTC_KST_152900 = "2026-08-28 06:29:00"
_UTC_KST_153020 = "2026-08-28 06:30:20"
_UTC_WALL_1520_KST_0020 = "2026-08-28 15:20:00"  # KST 2026-08-29 00:20
_UTC_KST_152000_NEXT_DAY = "2026-08-31 06:20:00"


# ---------------------------------------------------------------------------
# 헬퍼 — 기존 `test_momentum.py` 픽스처 패턴 재사용 (새로 발명 금지)
# ---------------------------------------------------------------------------
def _make_momentum(monkeypatch) -> MomentumStrategy:
    """scanner 전역 dict 를 격리한 모멘텀 인스턴스. momentum 은 prepare 없는 실시간 전략."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {_TICKER: _PREV_CLOSE})
    return MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="모멘텀", weight=0.5)
    )


def _prime(mo) -> None:
    """첫 틱 기록 — `_prev_prdy_rate[t] = +27.14%` (임계 29 미만)."""
    assert mo.check_buy_signal(_TICKER, _PRIME_PRICE, _PREV_CLOSE) == Signal.NONE


def _breakout(mo) -> Signal:
    """돌파 틱 — prev 27.14% < 29.0 <= current 29.01% (상한가 30% 미만)."""
    return mo.check_buy_signal(_TICKER, _BREAKOUT_PRICE, _PREV_CLOSE)


def _cutoff_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if _CUTOFF_MARKER in r.getMessage()]


# ===========================================================================
# B2-1 — [대조군] KST 15:19:59 돌파 → BUY (게이트가 정상 매수창을 잠식하지 않는다)
# ===========================================================================
@freeze_time(_UTC_KST_151959)
def test_b2_1_when_kst_151959_breakout_then_buy(monkeypatch) -> None:
    """B2-1 대조군: 컷 1초 전 +29% 돌파는 여전히 매수한다."""
    mo = _make_momentum(monkeypatch)
    _prime(mo)
    assert datetime.now(KST).time() == time(15, 19, 59)
    assert _breakout(mo) == Signal.BUY


# ===========================================================================
# B2-2 — [RED] KST 15:20:00 정각 → NONE
# ===========================================================================
@freeze_time(_UTC_KST_152000)
def test_b2_2_when_kst_152000_breakout_then_none(monkeypatch) -> None:
    """B2-2 (RED): 15:20:00 정각부터 컷 (VB 와 **같은 시각** — 정신 모델 단일화).

    "우리 시스템은 연속매매 시간에만 신규 진입한다" 한 문장이 두 전략을 동시에 설명한다.
    시각이 갈리면 나중에 "왜 momentum 만 15:30 이지" 를 매번 다시 설명해야 한다.

    현재 FAIL = 게이트 부재. naive 구현도 FAIL = 06:20:00 < 15:20.
    """
    mo = _make_momentum(monkeypatch)
    _prime(mo)
    assert datetime.now(KST).time() == time(15, 20, 0)
    assert _breakout(mo) == Signal.NONE


# ===========================================================================
# B2-3 — [RED] KST 15:29:00 / 15:30:20 → NONE
# ===========================================================================
@freeze_time(_UTC_KST_152900)
def test_b2_3_when_kst_152900_breakout_then_none(monkeypatch) -> None:
    """B2-3 (RED): 동시호가 예상체결가는 체결이 아니다 — 돌파 신호의 입력이 오염된 구간."""
    mo = _make_momentum(monkeypatch)
    _prime(mo)
    assert _breakout(mo) == Signal.NONE


@freeze_time(_UTC_KST_153020)
def test_b2_3b_when_kst_153020_breakout_then_none(monkeypatch) -> None:
    """B2-3b (RED): 랜덤엔드 확정 종가 틱. 이 표본의 +29% 는 '상한가 잠금 실패 마감' 이다."""
    mo = _make_momentum(monkeypatch)
    _prime(mo)
    assert _breakout(mo) == Signal.NONE


# ===========================================================================
# B2-4 — [TZ 역방향] UTC 벽시계 15:20 = KST 익일 00:20 → BUY
# ===========================================================================
@freeze_time(_UTC_WALL_1520_KST_0020)
def test_b2_4_when_utc_wallclock_1520_but_kst_0020_then_buy(monkeypatch) -> None:
    """B2-4: naive 구현이면 벽시계 15:20 >= 15:20 이라 컷이 서서 FAIL 한다.

    B2-2 와 짝 — 한쪽만으로는 naive 가 절반의 케이스를 우연히 통과한다.
    momentum 모듈에는 현재 `KST` 상수 자체가 없다(`from datetime import datetime` 뿐).
    Green 이 tz 를 새로 들여와야 하며, 이 케이스가 그것을 강제한다.
    """
    mo = _make_momentum(monkeypatch)
    _prime(mo)
    assert datetime.now(KST).time() == time(0, 20, 0)
    assert datetime.now().time() == time(15, 20, 0)
    assert _breakout(mo) == Signal.BUY, (
        "KST 00:20 은 컷 대상이 아니다. FAIL 이면 게이트가 naive 벽시계를 읽고 있다"
    )


# ===========================================================================
# B2-5 — [RED, 뮤테이션 가드] 컷 틱은 `_prev_prdy_rate` 를 갱신하지 않는다
# ===========================================================================
def test_b2_5_cut_tick_does_not_update_prev_prdy_rate(monkeypatch) -> None:
    """B2-5 (RED): 게이트가 `_prev_prdy_rate` read/write **이전**에 있어야 한다.

    momentum 은 첫 틱 기록(`if ticker not in self._prev_prdy_rate`)도 같은 dict 를 쓴다.
    게이트를 그 아래에 두면 종가 확정 틱의 등락률이 baseline 이 되어, 장중 재시작 후
    09:00~15:20 재개 구간에서 거짓 미돌파(또는 거짓 돌파)를 만든다.

    현재 FAIL = 게이트 부재 → 컷 틱이 29.0 을 기록하고 BUY 까지 반환.
    """
    mo = _make_momentum(monkeypatch)

    with freeze_time(_UTC_KST_151959):
        _prime(mo)
        primed = mo._prev_prdy_rate[_TICKER]
        assert primed == pytest.approx(27.142857, rel=1e-6)

    with freeze_time(_UTC_KST_152000):
        assert _breakout(mo) == Signal.NONE

    assert mo._prev_prdy_rate[_TICKER] == pytest.approx(primed, rel=1e-9), (
        "컷 틱이 baseline 을 오염시켰다 — 게이트가 `_prev_prdy_rate` 갱신보다 뒤에 있다"
    )


# ===========================================================================
# B2-6 — [보존] KST 15:25 청산 평가는 정상 발화
# ===========================================================================
@freeze_time(_UTC_KST_152500)
def test_b2_6_exit_signal_still_fires_at_kst_1525(monkeypatch) -> None:
    """B2-6 (보존): 컷은 매수 전용. momentum 은 익일청산 전략이라 15:30 대 보유가 상시 존재한다."""
    mo = _make_momentum(monkeypatch)
    mo.config.params["stop_loss_rate"] = -7.5  # 임계 결정론 고정
    mo.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=_PREV_CLOSE, quantity=1,
        order_no="O-229", strategy_id="momentum",
    )

    assert mo.check_exit_signal(_TICKER, 60000, _PREV_CLOSE) == Signal.STOP_LOSS, (
        "15:25 손절이 죽었다 — 매수 컷이 청산 경로를 오염시켰다"
    )


# ===========================================================================
# B2-7 — [RED] `[momentum_buy_cutoff]` 는 하루 1행
# ===========================================================================
@freeze_time(_UTC_KST_152000)
def test_b2_7_cutoff_log_emitted_once_per_day(monkeypatch, caplog) -> None:
    """B2-7 (RED): 첫 차단 시 1행. 관측 부재도, 매 틱 폭주도 아니다."""
    caplog.set_level(logging.INFO, logger=_MOMENTUM_LOGGER)
    mo = _make_momentum(monkeypatch)
    _prime(mo)

    assert _breakout(mo) == Signal.NONE
    assert mo.check_buy_signal(_TICKER, 90400, _PREV_CLOSE) == Signal.NONE  # +29.14%

    lines = _cutoff_lines(caplog)
    assert len(lines) == 1, (
        f"`{_CUTOFF_MARKER}` 는 첫 차단 시 1행. 실제 {len(lines)}행"
    )


# ===========================================================================
# B2-8 — [RED] 날짜가 바뀌면 다시 1행 — 훅 미의존 자기 리셋
# ===========================================================================
def test_b2_8_cutoff_log_resets_on_new_day(monkeypatch, caplog) -> None:
    """B2-8 (RED): cap 은 날짜 키 자기 리셋.

    momentum 은 `_reset_daily_state()` 를 override 하는데(`_prev_prdy_rate.clear()`),
    거기에 cap 리셋을 얹으면 훅 호출 누락 한 번으로 관측이 영구 침묵한다.
    """
    caplog.set_level(logging.INFO, logger=_MOMENTUM_LOGGER)
    mo = _make_momentum(monkeypatch)

    with freeze_time(_UTC_KST_151959):
        _prime(mo)
    with freeze_time(_UTC_KST_152000):
        assert _breakout(mo) == Signal.NONE
        assert len(_cutoff_lines(caplog)) == 1

    with freeze_time(_UTC_KST_152000_NEXT_DAY):
        assert _breakout(mo) == Signal.NONE

    lines = _cutoff_lines(caplog)
    assert len(lines) == 2, (
        f"날짜 경계에서 cap 이 리셋되지 않았다 (총 {len(lines)}행)"
    )


# ===========================================================================
# B2-9 — [RED] 모듈 상수 `BUY_CUTOFF_KST == time(15, 20)` (자기 파일에 자기 상수)
# ===========================================================================
def test_b2_9_module_constant_is_1520() -> None:
    """B2-9 (RED): momentum 자기 모듈에 자기 상수. VB 에서 import 하지 않는다.

    값이 같다고 상수를 공유하면 두 전략의 진입 정체성이 한 리터럴에 묶여, 한쪽만
    바꾸려는 미래의 변경이 다른 쪽을 조용히 끌고 간다(파일 간 결합 회피).
    """
    from src.engine.strategies import momentum as mo_mod

    assert hasattr(mo_mod, "BUY_CUTOFF_KST"), "모듈 상수 `BUY_CUTOFF_KST` 부재"
    assert mo_mod.BUY_CUTOFF_KST == time(15, 20)


# ===========================================================================
# B2-10 — [보존] `DEFAULT_PARAMS` 미편입
# ===========================================================================
def test_b2_10_cutoff_not_in_default_params() -> None:
    """B2-10: DB override 경로에 컷이 노출되면 안 된다."""
    params = MomentumStrategy.DEFAULT_PARAMS
    suspicious = [
        k for k in params
        if any(tok in k.lower() for tok in ("cutoff", "cut_off", "entry_end", "buy_end"))
    ]
    assert suspicious == [], f"컷 관련 키가 DEFAULT_PARAMS 에 편입됨: {suspicious}"
    assert time(15, 20) not in params.values()


# ===========================================================================
# B2-11 — [보존] AI 튜닝 화이트리스트 미편입
# ===========================================================================
def test_b2_11_cutoff_not_ai_tunable() -> None:
    """B2-11: 진입 시각 = 전략 정체성 상수. 사이클 209/212/223 선례."""
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    tokens = ("cutoff", "cut_off", "entry_end", "buy_end")
    hits = [
        k for k in set(PARAM_RANGES) | set(INT_PARAMS)
        if any(tok in k.lower() for tok in tokens)
    ]
    assert hits == [], f"컷 키가 AI 튜닝 화이트리스트에 편입됨: {hits}"
