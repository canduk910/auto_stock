"""사이클 229 Red — VB 매수 컷 15:20 (명세 W1).

명세 정본 `_workspace/red/cycle229_buy_cutoff_spec.md` W1 /
자문 정본 `_workspace/domain_consult/cycle229_vb_1530_single_price.md` §3 · §9 /
행위 분해 `_workspace/red/cycle229_behaviors.md` §1.

**Red 단계 — 실패 테스트만. 프로덕션 미변경.** Green = backend-dev.

## 결함

15:20~15:30 은 연속매매가 아니라 KRX **장후 동시호가(종가 단일가)** 이고, 15:30:0x~2x 에
랜덤엔드 확정 종가 1틱이 체결 스트림에 실리며 15:19 마지막 연속체결가 대비 점프해
`prev < target <= current` edge-crossing 을 만든다. VB 는 당일 청산 전략인데 그 시각의
진입은 **남은 거래 시간이 0** 이고, 종가 단일가가 시장가 호가를 접수하므로 체결되면
그대로 **오버나잇** 이 된다(15:20 강제청산은 이미 지나갔다).

## Green 계약 (명세 W1)

- 모듈 상수 `BUY_CUTOFF_KST = time(15, 20)` — `DEFAULT_PARAMS`/`PARAM_RANGES` **미편입**
  (DB 토글 하나로 뚫려선 안 되는 규칙 = 전략 정체성 상수).
- `check_buy_signal` **최상단**, 모든 상태 변경 특히 `_prev_price` read/write **이전**:
  `datetime.now(KST).time() >= BUY_CUTOFF_KST` → `Signal.NONE`.
  ⚠️ naive `datetime.now().time()` 금지 — BFB `:929`/VCP `:1045` 의 naive 는 **P2-6 등재
  결함**이지 선례가 아니다. 선례는 kojiro `:796` `datetime.now(KST).time()`.
- 관측 `[vb_buy_cutoff]` INFO **1회/일**, 날짜 키 자기 리셋(`_reset_daily_state` 훅 미의존).
- 청산 경로 무간섭 — `check_exit_signal`·15:20 강제청산·보드 흡수 마진 byte 불변.

## 이 파일의 가드

(B1-1~4) 경계 3점 + TZ 양방향 / (B1-5) 컷 틱 `_prev_price` 미갱신 = 게이트 위치 뮤테이션
가드 / (B1-6) 청산 무간섭 / (B1-7·8) 로그 cap + 날짜 리셋 / (B1-9~12) 상수·미편입·보드 불변.

## freezegun 과 타임존 — 이 파일의 모든 시각 표기 규약

freezegun 은 naive 문자열을 **UTC** 로 동결한다. 따라서 이 파일의 `freeze_time` 인자는 전부
UTC 이며 KST = UTC + 9h 다.

    freeze_time("2026-08-28 06:19:59")  →  KST 15:19:59  /  naive now().time() = 06:19:59
    freeze_time("2026-08-28 06:20:00")  →  KST 15:20:00  /  naive now().time() = 06:20:00
    freeze_time("2026-08-28 15:20:00")  →  KST 08-29 00:20  /  naive now().time() = 15:20:00

B1-2 는 "naive 면 컷을 **놓친다**", B1-4 는 "naive 면 **엉뚱한 때 컷한다**" 를 잡는다.
둘 중 하나만으로는 naive 구현이 절반의 케이스를 우연히 통과할 수 있다.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_TICKER = "005930"
_CUTOFF_MARKER = "[vb_buy_cutoff]"
_VB_LOGGER = "src.engine.strategies.volatility_breakout"

# UTC 동결 시각 ↔ KST 대응 (위 docstring 규약)
_UTC_KST_151959 = "2026-08-28 06:19:59"
_UTC_KST_152000 = "2026-08-28 06:20:00"
_UTC_KST_152500 = "2026-08-28 06:25:00"
_UTC_KST_152900 = "2026-08-28 06:29:00"
_UTC_KST_153020 = "2026-08-28 06:30:20"   # 실측 발사 시각대(8/27 에코프로)
_UTC_WALL_1520_KST_0020 = "2026-08-28 15:20:00"  # KST 2026-08-29 00:20
_UTC_KST_152000_NEXT_DAY = "2026-08-31 06:20:00"  # 날짜 리셋 검증용(월)


# ---------------------------------------------------------------------------
# 헬퍼 — 기존 `test_cycle201_vb_reentry_cooldown.py` 픽스처 패턴 재사용 (새로 발명 금지)
# ---------------------------------------------------------------------------
def _make_vb(monkeypatch) -> VolatilityBreakoutStrategy:
    """scanner 격리 + session_tracker 초기화한 VB 인스턴스."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {_TICKER: "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="변동성 돌파", weight=0.3)
    )


def _activate(board: str) -> None:
    session_tracker._active = frozenset({MarketBoard(board)})


def _seed_target(strategy, ticker, *, prev_range=1000, k=0.5) -> None:
    """prepare() 결과 모사 — `_targets` dict 직접 시드 (base = prev_range × k)."""
    target_offset_base = int(prev_range * k)
    strategy._targets[ticker] = {
        "k": k,
        "prev_range": prev_range,
        "target_offset_base": target_offset_base,
        "target_offset": target_offset_base,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


def _armed_vb(monkeypatch) -> VolatilityBreakoutStrategy:
    """돌파 1틱이면 BUY 가 나오는 최소 rig — open 80,000 / target 80,500."""
    vb = _make_vb(monkeypatch)
    _seed_target(vb, _TICKER, prev_range=1000, k=0.5)   # base 500
    vb.on_open_price_confirmed(_TICKER, open_price=80000, board="main", source="rest")  # target 80,500
    _activate("main")
    return vb


def _prime(vb) -> None:
    """첫 틱 기록 — `_prev_price[t]["main"] = 80,200` (목표가 아래)."""
    assert vb.check_buy_signal(_TICKER, 80200, 80000) == Signal.NONE


def _breakout(vb) -> Signal:
    """돌파 틱 — prev 80,200 < target 80,500 <= current 80,500."""
    return vb.check_buy_signal(_TICKER, 80500, 80000)


def _cutoff_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if _CUTOFF_MARKER in r.getMessage()]


# ===========================================================================
# B1-1 — [대조군] KST 15:19:59 = 연속매매 마지막 순간 → BUY (게이트 도입 후에도 불변)
# ===========================================================================
@freeze_time(_UTC_KST_151959)
def test_b1_1_when_kst_151959_breakout_then_buy(monkeypatch) -> None:
    """B1-1 대조군: 컷 1초 전 돌파는 **여전히 매수한다**.

    게이트가 정상 매수창을 잠식하지 않는다는 것이 이 사이클의 안전 조건이다.
    이 케이스가 깨지면 컷 시각이 잘못 들어간 것(예: `>` 대신 `>=` 를 15:19 에 적용).
    """
    vb = _armed_vb(monkeypatch)
    _prime(vb)
    assert datetime.now(KST).time() == time(15, 19, 59)  # 규약 자기 검증
    assert _breakout(vb) == Signal.BUY, (
        "KST 15:19:59 는 연속매매 구간 — 컷 대상이 아니다"
    )


# ===========================================================================
# B1-2 — [RED] KST 15:20:00 정각 → NONE (경계 포함)
# ===========================================================================
@freeze_time(_UTC_KST_152000)
def test_b1_2_when_kst_152000_breakout_then_none(monkeypatch) -> None:
    """B1-2 (RED): 15:20:00 **정각부터** 컷. 경계는 닫힌 구간(`>=`).

    현재 FAIL = 게이트 부재 → 돌파 틱이 BUY.
    naive `datetime.now().time()` 구현도 FAIL = 06:20:00 < 15:20 이라 컷 미발화.
    """
    vb = _armed_vb(monkeypatch)
    _prime(vb)
    assert datetime.now(KST).time() == time(15, 20, 0)
    assert _breakout(vb) == Signal.NONE, (
        "KST 15:20:00 = 장후 동시호가 시작 = 연속매매 종료. 이후 진입은 "
        "당일 청산 전략의 '남은 시간 0' 자리이고 체결되면 오버나잇이 된다"
    )


# ===========================================================================
# B1-3 — [RED] KST 15:29:00 (동시호가 한복판) → NONE
# ===========================================================================
@freeze_time(_UTC_KST_152900)
def test_b1_3_when_kst_152900_breakout_then_none(monkeypatch) -> None:
    """B1-3 (RED): 동시호가 구간의 `current_price` 는 체결가가 아니라 예상체결가다.

    돌파 신호의 **입력 자체가 오염**된 구간이므로 신호를 만들지 않는다.
    """
    vb = _armed_vb(monkeypatch)
    _prime(vb)
    assert _breakout(vb) == Signal.NONE


# ===========================================================================
# B1-3b — [RED] KST 15:30:20 (실측 발사 시각) → NONE
# ===========================================================================
@freeze_time(_UTC_KST_153020)
def test_b1_3b_when_kst_153020_breakout_then_none(monkeypatch) -> None:
    """B1-3b (RED): 실측 9건이 몰린 시각대(8/27 15:30:20 에코프로) 직접 재현.

    이 틱이 곧 랜덤엔드 확정 종가이고, 여기서 발사된 시장가가 `[단일가매매]` 거부 →
    미분류 `raise` → `[callback_exception]` → **WS 재연결** 체인의 출발점이었다.
    게이트가 서면 `execute_buy` 가 호출되지 않으므로 체인 전체가 소멸한다.
    """
    vb = _armed_vb(monkeypatch)
    _prime(vb)
    assert _breakout(vb) == Signal.NONE


# ===========================================================================
# B1-4 — [TZ 역방향] UTC 벽시계 15:20 = KST 익일 00:20 → BUY
# ===========================================================================
@freeze_time(_UTC_WALL_1520_KST_0020)
def test_b1_4_when_utc_wallclock_1520_but_kst_0020_then_buy(monkeypatch) -> None:
    """B1-4: 게이트가 **어느 타임존을 읽는가** 만 검정한다.

    naive `datetime.now().time()` 구현이면 벽시계 15:20:00 >= 15:20 이라 컷이 서고
    이 테스트가 FAIL 한다. tz-aware(KST) 구현이면 실제 KST 는 익일 00:20 이라 통과한다.

    ⚠️ KST 00:20 매수가 현실적이라는 주장이 아니다 — 이 케이스는 시장 시각이 아니라
    타임존 축 하나만 고정한다(컨테이너 `TZ` 가 UTC 로 바뀌어도 게이트가 KST 를 본다).
    B1-2 와 짝: B1-2 = "naive 면 컷을 놓친다" / B1-4 = "naive 면 엉뚱한 때 컷한다".
    """
    vb = _armed_vb(monkeypatch)
    _prime(vb)
    assert datetime.now(KST).time() == time(0, 20, 0)
    assert datetime.now().time() == time(15, 20, 0)  # naive = UTC 벽시계
    assert _breakout(vb) == Signal.BUY, (
        "KST 00:20 은 컷 대상이 아니다. FAIL 이면 게이트가 naive 벽시계를 읽고 있다"
    )


# ===========================================================================
# B1-5 — [RED, 뮤테이션 가드] 컷 틱은 `_prev_price` 를 갱신하지 않는다
# ===========================================================================
def test_b1_5_cut_tick_does_not_update_prev_price(monkeypatch) -> None:
    """B1-5 (RED): 게이트가 `_prev_price` read/write **이전**에 있어야 한다.

    게이트를 아래로 내리면 종가/예상체결가가 baseline 으로 기록된다. VB `prepare()` 가
    `_prev_price.clear()`(`:164`) 를 하므로 익일 오염은 없지만, **당일 장중 재시작 시**
    그 값이 baseline 이 되어 09:00~15:20 재개 구간에서 거짓 미돌파를 만든다.

    현재 FAIL = 게이트 부재 → 컷 틱이 80,500 을 기록하고 BUY 까지 반환.
    """
    vb = _armed_vb(monkeypatch)

    with freeze_time(_UTC_KST_151959):
        _prime(vb)
        assert vb._prev_price[_TICKER]["main"] == 80200

    with freeze_time(_UTC_KST_152000):
        assert _breakout(vb) == Signal.NONE

    assert vb._prev_price[_TICKER]["main"] == 80200, (
        "컷 틱이 baseline 을 오염시켰다 — 게이트가 `_prev_price` 갱신보다 뒤에 있다"
    )


# ===========================================================================
# B1-6 — [보존] KST 15:25 청산 평가는 정상 발화 (매수 게이트가 청산을 건드리지 않는다)
# ===========================================================================
@freeze_time(_UTC_KST_152500)
def test_b1_6_exit_signal_still_fires_at_kst_1525(monkeypatch) -> None:
    """B1-6 (보존): 컷은 **매수 전용**이다.

    `tradable_boards` 독트린과 동일 계약 — 매도/손절/트레일링/익일청산/15:20 강제청산은
    시각·보드 무관 항상 작동한다. 매수 게이트가 청산까지 끄면 15:30 대 보유 종목이
    무방비가 된다(자문 §6 이 지적한 '보유 축 실비용' 이 오히려 커진다).
    """
    vb = _armed_vb(monkeypatch)
    vb.config.params["stop_loss_main"] = -3.0  # 임계 결정론 고정
    vb.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=80000, quantity=1,
        order_no="O-229", strategy_id="volatility_breakout",
    )

    assert vb.check_exit_signal(_TICKER, 70000, 80000) == Signal.STOP_LOSS, (
        "15:25 손절이 죽었다 — 매수 컷이 청산 경로를 오염시켰다"
    )


# ===========================================================================
# B1-7 — [RED] `[vb_buy_cutoff]` 는 하루 1행 (컷 2회 → 1행)
# ===========================================================================
@freeze_time(_UTC_KST_152000)
def test_b1_7_cutoff_log_emitted_once_per_day(monkeypatch, caplog) -> None:
    """B1-7 (RED): 관측은 있어야 하되 매 틱 폭주하면 안 된다.

    사이클 224 교훈 — "발화할 때만 보이는 관측은 관측이 아니다" 이므로 첫 차단 시
    반드시 1행. 반대로 cap 이 없으면 15:20~15:30 틱마다 찍혀 로그를 삼킨다.
    차단 누적 카운터는 불요(단순 시각 게이트).
    """
    caplog.set_level(logging.INFO, logger=_VB_LOGGER)
    vb = _armed_vb(monkeypatch)
    _prime(vb)

    assert _breakout(vb) == Signal.NONE
    assert vb.check_buy_signal(_TICKER, 80600, 80000) == Signal.NONE

    lines = _cutoff_lines(caplog)
    assert len(lines) == 1, (
        f"`{_CUTOFF_MARKER}` 는 첫 차단 시 1행 (관측 부재도 폭주도 아님). 실제 {len(lines)}행"
    )


# ===========================================================================
# B1-8 — [RED] 날짜가 바뀌면 다시 1행 — 훅 미의존 자기 리셋
# ===========================================================================
def test_b1_8_cutoff_log_resets_on_new_day(monkeypatch, caplog) -> None:
    """B1-8 (RED): cap 은 **날짜 키 자기 리셋**이어야 한다.

    `_reset_daily_state()` 훅에 의존하면 서브클래스/호출 누락 한 번으로 관측이 영구 침묵한다
    (`strategy_base._emit_budget_clamp` 가 같은 이유로 날짜 키 자기 리셋을 쓴다).
    같은 인스턴스가 이틀에 걸쳐 컷하면 총 2행이어야 한다.
    """
    caplog.set_level(logging.INFO, logger=_VB_LOGGER)
    vb = _armed_vb(monkeypatch)

    with freeze_time(_UTC_KST_151959):
        _prime(vb)
    with freeze_time(_UTC_KST_152000):
        assert _breakout(vb) == Signal.NONE
        assert len(_cutoff_lines(caplog)) == 1

    with freeze_time(_UTC_KST_152000_NEXT_DAY):
        assert _breakout(vb) == Signal.NONE

    lines = _cutoff_lines(caplog)
    assert len(lines) == 2, (
        f"날짜 경계에서 cap 이 리셋되지 않았다 (총 {len(lines)}행). "
        "훅 호출 없이도 스스로 풀려야 한다"
    )


# ===========================================================================
# B1-9 — [RED] 모듈 상수 `BUY_CUTOFF_KST == time(15, 20)`
# ===========================================================================
def test_b1_9_module_constant_is_1520() -> None:
    """B1-9 (RED): 컷 시각은 **모듈 상수**다 (자문 Q1 구현안 A).

    파라미터(`entry_end`)로 두면 운영자가 `strategy_config.params` 에 `15:35` 를 넣어
    구멍을 재개방할 수 있다. VB 의 OVERNIGHT 금지는 DB 토글 하나로 뚫려선 안 되는 규칙이고,
    진입 시각은 손익 튜닝값이 아니라 **전략 정체성 상수**다
    (`max_positions`·donchian 청산 상수(사이클 223)·`tradable_boards` 와 같은 부류).
    """
    from src.engine.strategies import volatility_breakout as vb_mod

    assert hasattr(vb_mod, "BUY_CUTOFF_KST"), (
        "모듈 상수 `BUY_CUTOFF_KST` 부재 — 컷 시각이 파라미터로 새면 DB 로 뚫린다"
    )
    assert vb_mod.BUY_CUTOFF_KST == time(15, 20)


# ===========================================================================
# B1-10 — [보존] `DEFAULT_PARAMS` 에 컷 키 미편입
# ===========================================================================
def test_b1_10_cutoff_not_in_default_params() -> None:
    """B1-10: DB override 경로(`strategy_config.params`)에 컷이 노출되면 안 된다."""
    params = VolatilityBreakoutStrategy.DEFAULT_PARAMS
    suspicious = [
        k for k in params
        if any(tok in k.lower() for tok in ("cutoff", "cut_off", "entry_end", "buy_end"))
    ]
    assert suspicious == [], (
        f"컷 관련 키가 DEFAULT_PARAMS 에 편입됨: {suspicious}. "
        "params 에 있으면 DB 가 덮어써 게이트가 무력화된다"
    )
    assert time(15, 20) not in params.values()


# ===========================================================================
# B1-11 — [보존] `PARAM_RANGES` / `INT_PARAMS` 미편입
# ===========================================================================
def test_b1_11_cutoff_not_ai_tunable() -> None:
    """B1-11: 진입 시각은 매일 밤 AI 가 흔들 값이 아니다.

    사이클 209(`max_breakout_extension_pct`)·212(`buy_threshold`/`donchian_period`)·
    223(donchian 청산 2키) 선례와 동일 — 정체성 상수는 자동 튜닝 화이트리스트 밖.
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    tokens = ("cutoff", "cut_off", "entry_end", "buy_end")
    hits = [
        k for k in set(PARAM_RANGES) | set(INT_PARAMS)
        if any(tok in k.lower() for tok in tokens)
    ]
    assert hits == [], f"컷 키가 AI 튜닝 화이트리스트에 편입됨: {hits}"


# ===========================================================================
# B1-12 — [보존] 보드 축 무접촉
# ===========================================================================
def test_b1_12_tradable_boards_unchanged() -> None:
    """B1-12: 컷은 **명시 시각 상수** 축이지 보드 축이 아니다.

    매수 컷을 보드에 결합하면 청산 마진(MAIN 15:39:59 종가 흡수)을 조정할 때 매수창이
    따라 움직인다 — `risk.py` 프리장 게이트가 "보드가 아니라 명시 상수로 판정" 을
    AST 가드까지 걸어 차단한 커플링과 같은 부류다.
    """
    assert VolatilityBreakoutStrategy.DEFAULT_TRADABLE_BOARDS == ("main",)
