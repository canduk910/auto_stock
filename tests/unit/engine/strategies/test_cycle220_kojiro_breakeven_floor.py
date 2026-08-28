"""cycle220 Red — kojiro 브레이크이븐 플로어 이식 (다크런치) 회귀 가드.

명세: 사용자 지시 (team-leader → tdd-engineer). 구현 = backend-dev (kojiro.py 단독).
자문: `_workspace/domain_consult/kojiro_exit_loss_review.md`
      (Q2 1순위 = 청산 브레이크이븐 플로어 이식, 최고 EV / 샹들리에 조임 금기 /
       "플로어이지 트레일이 아니다 — max(플로어, 샹들리에, 백스톱)").
선례: donchian P1 (`breakeven_promote_atr=1.5` 라이브) / BFB·VCP 사이클 C
      (`breakeven_promote_atr=0.0` 다크런치, `test_cycleC_bfb_breakeven.py`).

## 실측 동기부여 (08-18 영원무역 111770)

    매수 86,800 · 고점 95,000(+9.4%) · ATR 4,736
      1.5N 승격선 = 86,800 + 1.5×4,736 = 93,904  ← 고점 95,000 이 넘김
      샹들리에선 = 95,000 − 2.5×4,736 = 83,160    ← 완전 왕복 시 여기까지 반납
      실제 청산 83,000 (−4.4%)                    ← +9.4% → −4.4% 전량 반납

    브레이크이븐 플로어가 있었다면: 고점이 1.5N 을 넘긴 순간 손절선을 매수가로
    승격 → 완전 왕복 시 86,800(±0%) 부근 청산 → 이익 반납 차단.

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

kojiro.py 단독. 3 삽입 지점 + 1 미러:

1. `DEFAULT_PARAMS["breakeven_promote_atr"] = 0.0` (다크 = 분기 미진입 = byte-identical).
   PARAM_RANGES/INT_PARAMS **미편입** (청산 정체성 상수).

2. `check_exit_signal` §2 — 현 `eff` 계산 직후(`self._stop_floor[ticker] = eff` 뒤),
   `if eff > 0 and current_price <= eff` 판정 **전** 삽입:
       be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
       if be_mult > 0 and atr > 0 and pos.buy_price > 0 and \
          pos.high_since_buy >= pos.buy_price + be_mult * atr:
           promoted = max(eff, pos.buy_price)
           if promoted != eff:
               logger.info("[kojiro_breakeven_promote] ...")
           eff = promoted
           self._stop_floor[ticker] = eff   # 기존 tighten-only 래칫에 영속
   ATR 소스 = live `_effective_atr` (kojiro 는 `_entry_atr` 미도입 = 단일 메커니즘).

3. `recompute_held_atr` 재시작 재도출 — 현 floor 래칫 블록(`_stop_floor[ticker] = max(...)`)
   에 동일 승격. H-1 `_apply_high_since_buy_from_candles` 가 **먼저** 고점을 복구하므로
   승격 재도출 가능. `be_mult > 0` 게이트 동일.

4. `_position_stop_price` read-only 미러 (Σ리스크캡 커플링 불변식 — "청산 세 가격선
   전부와 동일 산식"). breakeven 라인을 `max()` 에 포함하되 `_stop_floor` **무변조**:
       be_line = int(pos.buy_price) if (be_mult > 0 and atr > 0 and
                 pos.high_since_buy >= pos.buy_price + be_mult * atr) else 0
       return max(pct_line, atr_line, trail_line, be_line)

불변 (FREEZE / 도메인 금기): §1 백스톱(−8%) · §3 스테이지3 · **§4 샹들리에
trail_atr=2.5(조임 금기)** · 진입 로직 전체 · `_reset_daily_state` 미접촉.

## RED 상태

- 승격 발화 / floor 재도출 / 리스크캡 미러 = 현 코드 부재 → FAIL.
- 다크(mult=0) / 미도달 / §1·§3·§4 불변 / 파라미터 제외 = 현 코드 통과(guard).
"""

from __future__ import annotations

import inspect
import logging
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))

# 08-18 영원무역 실측 상수 — 전 테스트 공유.
BUY = 86_800
ATR = 4_736.0
N15 = BUY + 1.5 * ATR                 # 93,904  (1.5N 승격 임계, 정확히 정수)
ATR_FLOOR = int(BUY - 2.0 * ATR)      # 77,328  (2ATR 하드손절 선)
PCT_BACKSTOP = int(BUY * 0.92)        # 79,856  (−8% 백스톱, 정확히 −8.0%)


def _today() -> date:
    """운영 코드가 `datetime.now(KST).date()` 를 쓰므로 테스트도 동일 기준."""
    return datetime.now(_KST).date()


def _kojiro(**extra) -> KojiroStrategy:
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.6, params=extra),
    )
    s.state.total_investment = 690_111
    return s


def _hold(
    s: KojiroStrategy,
    ticker: str = "111770",
    *,
    buy: int = BUY,
    qty: int = 1,
    high: int | None = None,
    atr: float | None = ATR,
    stage: int = 1,
) -> Position:
    """보유 포지션 + (옵션) live ATR candidate 세팅.

    `atr=None` → `_candidates` 미등록(재시작/ATR 결측 상태 재현).
    `high=None` → high_since_buy = buy (고점 미복구 상태).
    """
    pos = Position(
        ticker=ticker, buy_price=buy, quantity=qty, order_no="O", strategy_id="kojiro",
    )
    pos.high_since_buy = buy if high is None else high
    s.state.positions[ticker] = pos
    if atr is not None:
        s._candidates[ticker] = {"atr": atr, "stage": stage, "prev_close": buy}
    return pos


# ── 재시작 재도출(recompute) 용 일봉 합성 ──────────────────────────────────
# TR 이 매일 4,736 로 일정 → Wilder ewm(1/20) 이 정확히 4,736 수렴 (결정론).
def _flat_kis_candle(d: date, *, high: int = 91_000, low: int = 86_264, close: int = 88_000) -> dict:
    return {
        "stck_bsop_date": d.strftime("%Y%m%d"),
        "stck_hgpr": str(high),
        "stck_lwpr": str(low),
        "stck_clpr": str(close),
        "stck_oprc": str(close),
        "acml_vol": "100000",
    }


def _flat_series(today: date, n: int = 85) -> list[dict]:
    """DESC(idx0=최신=today-1). 85봉 ≥ KOJIRO_MIN_REQUIRED(80) 로 ATR/floor 블록 진입."""
    return [_flat_kis_candle(today - timedelta(days=k)) for k in range(1, n + 1)]


class _RecomputeDeps:
    """`recompute_held_atr` 외부 의존 격리 (DB 일봉/UPDATE/log/섹터)."""

    def __init__(self, candles_by_ticker: dict[str, list[dict]]):
        self._candles = candles_by_ticker
        self.update_high = AsyncMock()
        self._patches: list = []

    async def _fetch(self, ticker, days=0, min_required=None):
        return self._candles.get(ticker, [])

    def __enter__(self):
        self._patches = [
            patch("src.db.stock_master_daily.get_recent_daily_normalized", self._fetch),
            patch("src.db.positions.update_high", self.update_high),
            patch("src.db.system_logs.write_log", AsyncMock()),
            patch.object(KojiroStrategy, "_fetch_sector", AsyncMock(return_value="섹터")),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Red 1 — 다크 기본값 + PARAM_RANGES/INT_PARAMS 미편입
# ═══════════════════════════════════════════════════════════════════════════
def test_default_param_is_dark():
    """DEFAULT_PARAMS breakeven_promote_atr 기본값 = 0.0 (다크런치, BFB 사이클 C 선례)."""
    assert KojiroStrategy.DEFAULT_PARAMS.get("breakeven_promote_atr") == 0.0


def test_breakeven_key_excluded_from_param_ranges():
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert "breakeven_promote_atr" not in PARAM_RANGES, "청산 정체성 상수 — AI 튜닝 금지"
    assert "breakeven_promote_atr" not in INT_PARAMS


# ═══════════════════════════════════════════════════════════════════════════
# Red 2 — 다크(mult=0) = byte-identical (승격 없음 · _stop_floor 2ATR 래칫만)
# ═══════════════════════════════════════════════════════════════════════════
def test_dark_default_is_byte_identical():
    """기본(off) 이면 고점이 아무리 높아도 승격 없음 — 기존 이익반납 그대로.

    고점 95,000 넘겼어도 buy 부근 반납 시 미청산(승격 부재), 샹들리에선에서만 반납 청산.
    """
    s = _kojiro()  # breakeven off (기본)
    _hold(s, high=95_000)
    # buy 부근으로 반납해도 승격 없어 미청산
    assert s.check_exit_signal("111770", BUY, BUY) == Signal.NONE
    assert s._stop_floor["111770"] == ATR_FLOOR, "2ATR 래칫만 — buy 로 승격 금지"
    # 완전 왕복 → 샹들리에선(83,160)에서만 TRAILING_STOP (이익 반납 실현)
    assert s.check_exit_signal("111770", int(95_000 - 2.5 * ATR), BUY) == Signal.TRAILING_STOP


def test_dark_does_not_mutate_stop_floor_to_buy():
    """다크 상태에서 _stop_floor 가 buy 로 오르지 않는다 (승격 부작용 부재)."""
    s = _kojiro(breakeven_promote_atr=0.0)
    _hold(s, high=95_000)
    s.check_exit_signal("111770", 90_000, BUY)
    assert s._stop_floor["111770"] == ATR_FLOOR


# ═══════════════════════════════════════════════════════════════════════════
# Red 3 — 승격 발화 (08-18 영원무역 시나리오) + tighten-only + 로그 1회
# ═══════════════════════════════════════════════════════════════════════════
def test_promotion_fires_and_locks_at_buy(caplog):
    """mult=1.5 + high ≥ 1.5N → eff 가 buy 로 승격 + _stop_floor==buy + 이후 buy 이하 STOP_LOSS.

    실측: buy 86,800 · high 95,000 · ATR 4,736 → 1.5N=93,904 도달 → 플로어 86,800.
    """
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, high=95_000)
    with caplog.at_level(logging.INFO, logger="src.engine.strategies.kojiro"):
        # 승격 관측 — 아직 미청산 (플로어 = buy, 현재가 그 위)
        assert s.check_exit_signal("111770", 90_000, BUY) == Signal.NONE
        assert s._stop_floor["111770"] == BUY, "래칫 영속: 승격선 = 매수가"
        # 완전 왕복 → buy 이하 → STOP_LOSS (이익 반납 차단)
        assert s.check_exit_signal("111770", BUY, BUY) == Signal.STOP_LOSS
        # 갭다운으로 플로어 하회여도 발화 (익일 아침 갭 시나리오)
        assert s.check_exit_signal("111770", 84_000, BUY) == Signal.STOP_LOSS
    assert caplog.text.count("[kojiro_breakeven_promote]") == 1, "승격 로그 1회 (재발화 없음)"


def test_promotion_tighten_only_no_fire_above_buy():
    """tighten-only — 승격돼도 현재가 buy 위면 미발화 (손절선 buy 위 확대 케이스 0)."""
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, high=95_000)
    assert s.check_exit_signal("111770", 90_000, BUY) == Signal.NONE
    assert s._stop_floor["111770"] == BUY
    assert s.check_exit_signal("111770", BUY + 1, BUY) == Signal.NONE


# ═══════════════════════════════════════════════════════════════════════════
# Red 4 — 임계 미도달 시 미승격 (2ATR 선 유지)
# ═══════════════════════════════════════════════════════════════════════════
def test_no_promotion_below_threshold():
    """high < buy + 1.5×ATR → 승격 없음, 기존 2ATR 선 유지."""
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, high=90_000)  # 90,000 < 1.5N 93,904
    assert s.check_exit_signal("111770", BUY, BUY) == Signal.NONE
    assert s._stop_floor["111770"] == ATR_FLOOR, "미도달 → 2ATR 래칫만, buy 승격 금지"


# ═══════════════════════════════════════════════════════════════════════════
# Red 5 — 래칫 tighten-only: 승격 후 ATR 팽창해도 floor 가 buy 아래로 안 내려감
# ═══════════════════════════════════════════════════════════════════════════
def test_ratchet_tighten_only_survives_atr_expansion():
    """승격 후 ATR 2배 팽창 → 재-승격 조건은 거짓이나 래칫이 floor 를 buy 로 유지."""
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, high=95_000)
    assert s.check_exit_signal("111770", 90_000, BUY) == Signal.NONE  # 승격 → floor buy
    assert s._stop_floor["111770"] == BUY

    s._candidates["111770"]["atr"] = 2 * ATR  # ATR 팽창 (2ATR base 가 buy 훨씬 아래로)
    assert s.check_exit_signal("111770", 90_000, BUY) == Signal.NONE
    assert s._stop_floor["111770"] == BUY, "ATR 팽창해도 floor 가 buy 아래로 loosen 금지"
    assert s.check_exit_signal("111770", BUY, BUY) == Signal.STOP_LOSS


# ═══════════════════════════════════════════════════════════════════════════
# Red 6 — fat-tail 보존: 플로어는 buy 고정(트레일 아님), 샹들리에가 더 높은 선 별도 작동
# ═══════════════════════════════════════════════════════════════════════════
def test_fat_tail_floor_fixed_at_buy_chandelier_separate():
    """대랠리(high = buy + 10×ATR) — 플로어는 buy 에 고정, 샹들리에(§4)는 훨씬 위.

    도메인 반례 1 완화: breakeven 이 fat-tail 을 절단하면 안 된다.
    """
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, high=int(BUY + 10 * ATR))  # 134,160
    # 승격 관측 — 플로어 buy 고정 (트레일 아님)
    assert s.check_exit_signal("111770", 125_000, BUY) == Signal.NONE
    assert s._stop_floor["111770"] == BUY, "플로어는 buy 에 고정 — high 따라 트레일 금지"
    # 샹들리에(§4) 는 무변경 byte = high − 2.5×ATR (플로어보다 훨씬 위에서 별도 작동)
    pos = s.state.positions["111770"]
    assert s._position_stop_price("111770", pos) == int(BUY + 10 * ATR - 2.5 * ATR)


def test_chandelier_trails_above_floor_no_fat_tail_cut():
    """+1.5N 후 계속 상승 시 샹들리에가 플로어 위에서 트레일 (breakeven 절단 안 됨).

    자문 후속 검증 (b): high=100,000 → 샹들리에 88,160 > 플로어 86,800.
    """
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, high=100_000)
    assert s.check_exit_signal("111770", 95_000, BUY) == Signal.NONE
    assert s._stop_floor["111770"] == BUY
    chandelier = int(100_000 - 2.5 * ATR)  # 88,160 (> 플로어 86,800)
    assert s.check_exit_signal("111770", chandelier, BUY) == Signal.TRAILING_STOP
    assert s.check_exit_signal("111770", chandelier + 1, BUY) == Signal.NONE


# ═══════════════════════════════════════════════════════════════════════════
# Red 7 — 재시작 재도출: _stop_floor 빈 상태 + recompute_held_atr → floor 재승격
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_restart_rederivation_promotes_floor_when_enabled():
    """재시작(_stop_floor 빈) + high 복구 상태 + mult=1.5 → floor 가 buy 로 재도출.

    H-1 `_apply_high_since_buy_from_candles` 가 먼저 고점을 복구 → 승격 재도출.
    """
    s = _kojiro(breakeven_promote_atr=1.5)
    pos = _hold(s, high=97_000, atr=None)  # candidates 없이(재시작), high 이미 복구 상태
    pos.buy_date = _today() - timedelta(days=15)
    s._stop_floor.clear()
    with _RecomputeDeps({"111770": _flat_series(_today())}):
        await s.recompute_held_atr()
    assert s._stop_floor["111770"] == BUY, "재시작 재도출: floor 가 buy 로 승격"


@pytest.mark.asyncio
async def test_restart_no_promotion_when_disabled():
    """mult=0(기본) 이면 재시작 재도출도 기존 2ATR floor 만 (승격 없음)."""
    s = _kojiro()  # off
    pos = _hold(s, high=97_000, atr=None)
    pos.buy_date = _today() - timedelta(days=15)
    s._stop_floor.clear()
    with _RecomputeDeps({"111770": _flat_series(_today())}):
        await s.recompute_held_atr()
    assert s._stop_floor["111770"] == ATR_FLOOR, "다크: 2ATR floor 만 재도출"


# ═══════════════════════════════════════════════════════════════════════════
# Red 8 — 리스크캡 미러: _position_stop_price 에 breakeven 포함, _stop_floor 무변조
# ═══════════════════════════════════════════════════════════════════════════
def test_risk_cap_mirror_promotes_when_condition_met():
    """mult=1.5 + 승격 조건 충족 → _position_stop_price ≥ buy → _open_risk_won 0."""
    s = _kojiro(breakeven_promote_atr=1.5)
    pos = _hold(s, high=int(N15))  # high = 93,904 (정확히 1.5N)
    assert "111770" not in s._stop_floor
    stop = s._position_stop_price("111770", pos)
    assert stop == BUY, "be_line = buy 가 세 선(pct/2ATR/샹들리에) 전부를 이긴다"
    assert "111770" not in s._stop_floor, "읽기 전용 — _stop_floor 무변조"
    assert s._open_risk_won() == 0, "실효손절선 ≥ buy → 오픈리스크 0 계상"


def test_risk_cap_mirror_unchanged_when_disabled():
    """mult=0 → 기존 3선(pct/2ATR/샹들리에) max 그대로 (breakeven 라인 부재)."""
    s = _kojiro()  # off
    pos = _hold(s, high=int(N15))
    stop = s._position_stop_price("111770", pos)
    assert stop == int(N15 - 2.5 * ATR), "다크: 샹들리에선(82,064) = 3선 max"
    assert s._open_risk_won() == 1 * (BUY - stop)  # 4,736


def test_position_stop_price_read_only_on_stop_floor():
    """AST — `_position_stop_price` 는 `_stop_floor` 를 쓰지 않는다 (매수 게이트 부작용 차단)."""
    src = inspect.getsource(KojiroStrategy._position_stop_price)
    assert "self._stop_floor[" not in src, (
        "매수 게이트 추정기가 청산 규약(_stop_floor)을 부작용으로 갱신하면 안 된다"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Red 9 — 우선순위/불변: §1 백스톱 · §3 스테이지3 · §4 샹들리에(2.5) · 진입 FREEZE
# ═══════════════════════════════════════════════════════════════════════════
def test_hard_stop_backstop_unchanged():
    """§1 −8% 백스톱 무변경 (ATR 결측 시 breakeven 조건 거짓 → 미개입)."""
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, atr=None, high=BUY)  # ATR 결측 → §2/§4/breakeven 전부 inert, §1 만
    assert s.check_exit_signal("111770", PCT_BACKSTOP, BUY) == Signal.STOP_LOSS  # −8.0%
    assert s.check_exit_signal("111770", PCT_BACKSTOP + 50, BUY) == Signal.NONE  # −7.9%


def test_stage3_exit_unchanged():
    """§3 스테이지3 청산 무변경 (high=buy → 승격 미발화, stage3 정상 발화)."""
    s = _kojiro(breakeven_promote_atr=1.5)
    _hold(s, high=BUY)  # high < 임계 → 승격 없음
    # cycle231 — 날짜 키 계약: 오늘 판정이어야 §3 발화 (stale True 는 억제)
    s._held_stage3["111770"] = (_today(), True)
    assert s.check_exit_signal("111770", BUY, BUY) == Signal.TRAILING_STOP


def test_chandelier_trail_atr_constant_unchanged():
    """§4 샹들리에 trail_atr=2.5 값 불변 (도메인 금기 = 조임 금지) + hard_stop/stop_atr 불변."""
    d = KojiroStrategy.DEFAULT_PARAMS
    assert d["trail_atr"] == 2.5, "샹들리에 조임 금기 — 2.5 불변"
    assert d["stop_atr"] == 2.0
    assert d["hard_stop_pct"] == -8.0


def test_check_buy_signal_untouched_by_breakeven():
    """진입 로직(check_buy_signal) 에 breakeven 토큰 인젝션 0 (FREEZE, AST)."""
    src = inspect.getsource(KojiroStrategy.check_buy_signal)
    assert "breakeven" not in src.lower(), "진입 파라미터/로직 불변 (FREEZE)"


def test_no_reset_daily_state_override():
    """`_reset_daily_state` override 추가 금지 — _stop_floor 밤샘 보존 (기존 AST 봉인)."""
    assert "_reset_daily_state" not in KojiroStrategy.__dict__, (
        "override 추가 시 멀티데이 보유의 _stop_floor(브레이크이븐 승격선)가 20:10 정산에 소멸"
    )


def test_check_exit_signal_has_no_open_risk_reference():
    """청산이 리스크 캡을 참조하지 않는다 (기존 계약 보존 — 캡 도달 시 손절 마비 차단)."""
    src = inspect.getsource(KojiroStrategy.check_exit_signal)
    assert "_open_risk_won" not in src and "max_open_risk_pct" not in src
