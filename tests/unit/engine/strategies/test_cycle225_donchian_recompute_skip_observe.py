"""사이클 225 Red — donchian 복구 경로의 **침묵 3층** 관측화.

## 발단 (라이브 실측 2026-08-24)

15:58 장중 재배포 → 컨테이너 재시작. 직후 사이클 224 관측 로그가 이걸 찍었다:

    16:03:52 [days_held_observe] ticker=192820 ... breakout_high=0 current_price=285000

같은 날 09:06 에는 `breakout_high=263000` 이었다. 재시작으로 `_breakout_high` 가 소실됐고
**재도출이 복구하지 못했다** = 그 종목의 시간청산이 무장 해제 상태다.

규명 결과 **재도출이 실패한 게 아니라 호출조차 되지 않았다.** `recompute_held_atr` 루프에
재도출(`_rederive_breakout_high`)보다 **앞선** 게이트가 있다:

    pos_needs_high_recover = bool(pos and pos.buy_date < today)
    need_atr = ticker not in self._candidates
    if not need_atr and not pos_needs_high_recover:
        continue          # ← fetch **앞**. 재도출까지 못 간다.

    403870 : buy_date 08-21 < today ✅ · `_candidates` 이탈 ✅ → 통과, 재도출 성공(46,900)
    192820 : buy_date == today ❌ · `_candidates` **잔류** ❌ → continue → 재도출 미호출
             (실측 `scanned_tickers: ['192820']` · `targets: ['192820']`)

## 라이브 리스크는 없다 — 그래서 **행위를 바꾸지 않는다**

`_breakout_high` 소비처는 전수 2곳 — 매수 시 등록(`check_buy_signal`), 시간청산 게이트
읽기(`check_exit_signal` §2.5). 게이트는
`breakout_high > 0 **and** days_held >= n_days and 현재가 < breakout_high` 다.
이 구멍의 발생 조건이 `buy_date == today` 인데, 그러면 `_business_days_held` 가 **항상 0**
이고 `n_days` 는 라이브 2 · 기본 5(사이클 223 S1 이 `PARAM_RANGES` 에서 제외해 AI 가 못
낮춘다) ⇒ `days_held(0) >= n_days(≥2)` 가 어차피 거짓이라 게이트가 닫혀 있다.
게다가 **자가 치유**된다 — 내일 부팅이면 `buy_date < today` 로 통과하고, 후보 이탈 시엔
`need_atr=True` 로 통과한다. `days_held` 가 임계에 닿기 전에 반드시 재무장된다.

⚠️ 따라서 **행위 수정 금지**. `continue` 앞에서 재도출을 억지로 호출하면 매수 당일 종목마다
   KIS 일봉 fetch 가 새로 생기는데(게이트가 fetch **앞**에 있는 이유가 그것이다) 이득은 0이다.

## 진짜 문제 = 침묵 3층 (이 사이클이 없애는 것)

규명에 시간이 걸린 이유는 이 경로에 흔적이 하나도 없기 때문이다.

    1층  `recompute_held_atr` 의 `continue`                        — 무로그
    2층  `_rederive_breakout_high` 의 `len(prior) < period + 1`    — 조용한 return
    3층  같은 함수의 `if breakout_high > 0:` (값 0이면 set 도 로그도 없음)

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

### A. `[held_recompute_skip]` — 침묵 1층

1. 신규 메서드 **`_emit_held_recompute_skip(ticker, pos, need_atr, needs_high_recover)`**
   — `logger.info`. 호출 위치 = `recompute_held_atr` 의 게이트 `continue` **직전**
   (⇒ `fetch_daily_candles` **앞**. 이 로그 때문에 fetch 가 생기면 취지 정반대다).
2. **발화 조건 = `continue` 로 빠지면서 `ticker not in self._breakout_high` 인 경우만.**
   이미 무장돼 있으면 그 skip 은 무해하다 — 정상 경로를 매일 찍으면 신호가 희석된다.
   ⚠️ 이 조건 판정은 **emitter 내부**(try 안)에서 한다. 호출부에서 `_breakout_high` 를
   읽으면 그 읽기가 try 밖이라 관측이 `recompute_held_atr` 를 죽일 수 있다(C-12a).
3. 로그 필드(같은 한 줄): `ticker` `strategy` `buy_date` `today` `need_atr`
   `in_candidates` `needs_high_recover` `breakout_high_armed`.
   `in_candidates` / `breakout_high_armed` 는 emitter 내부에서 구한다.
4. 문구는 **과잉 주장 금지** — 이 상태가 곧 위험이라고 쓰지 않는다. 위 "라이브 리스크
   없음" 근거(매수 당일 ⇒ `days_held=0` ⇒ 게이트 닫힘, 자가 치유 2경로)를 docstring 에
   명시하고, 본문은 "무장 미복구 상태이며 다음 영업일 부팅 또는 후보 이탈 시 재무장된다"
   수준으로 적는다.

### B. `[donchian_breakout_high_rederive_skip]` — 침묵 2·3층

5. 신규 메서드 **`_emit_breakout_high_rederive_skip(ticker, pos, reason, prior_len, need)`**
   — `logger.info`. `_rederive_breakout_high` 의 두 조용한 실패 경로에 사유를 남긴다.
     - `len(prior) < donchian_period + 1` → `reason=insufficient_prior prior=N need=M`
       (`need` = **`donchian_period + 1`** = 가드가 실제로 요구하는 봉 수)
     - 계산 결과 `breakout_high <= 0`     → `reason=zero_high prior=N`
   두 경우 모두 `ticker` / `strategy` / `buy_date` 동반.
6. 기존 성공 로그 `[donchian_breakout_high_rederive]` **무변경** ·
   기존 `except Exception: logger.exception("도치안 breakout_high 재도출 실패")` **무변경**.

### 공통

7. 둘 다 **DailyEmitCap 1회/ticker/일**, 서로 **별개 인스턴스 필드**이며 사이클 223/224 의
   `_days_held_fallback_logged` · `_days_held_observe_logged` 와도 별개.
   날짜 키 자기리셋(`_days_held_fallback_day` 선례 — `_reset_daily_state` 훅 비의존).
8. 어떤 예외도 흡수하되 **흔적을 남긴다** — `logger.debug("[..._failed] ...", exc_info=True)`.
   마커는 `[held_recompute_skip_failed]` / `[donchian_breakout_high_rederive_skip_failed]`.
   ⚠️ 무흔적 흡수 금지 — 사이클 224 F3 계약. 조용히 삼키면 이 관측이 영구 침묵해도
   도입 이전 무음과 구별되지 않는다.
9. hot path 는 아니지만(부팅·폴 주기) **cap 조회를 먼저** 한다.
10. **행위 변경 0** — `recompute_held_atr` 의 제어 흐름·**fetch 호출 횟수**·
    `check_exit_signal` 반환이 어떤 입력에서도 달라지지 않는다.

## Red 유효성 (production 미변경 시점)

- A-0/A-1/A-4/A-5/A-6 · B-0/B-5/B-6/B-8 · IND-1 · C-12a/C-12b · STRUCT-1 = **FAIL**
  (두 emitter 미구현 → 신규 마커 0건)
- A-2/A-3 · B-7 · C-9/C-10/C-11 = **PASS** — 구현 후에도 계속 PASS 해야 하는 가드다
  (특히 C-9 fetch 횟수 · C-10 시그널 표가 "관측 전용" 계약의 본체).
"""

from __future__ import annotations

import ast
import datetime as _dt
import inspect
import logging
import textwrap
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

import src.engine.strategies.donchian_swing as _mod
from src.engine.observer_trace import trace_observer_failure
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.strategies.donchian_swing"

_SKIP = "[held_recompute_skip]"
_SKIP_FAILED = "[held_recompute_skip_failed]"
_RSKIP = "[donchian_breakout_high_rederive_skip]"
_RSKIP_FAILED = "[donchian_breakout_high_rederive_skip_failed]"
_REDERIVE_OK = "[donchian_breakout_high_rederive]"     # 기존 성공 로그 (무변경)
_REDERIVE_ERR = "도치안 breakout_high 재도출 실패"       # 기존 except 로그 (무변경)
_OBS = "[days_held_observe]"                           # 사이클 224
_EXIT = "도치안 시간 기반 청산"

D = _dt.date


# ===========================================================================
# rig — 사이클 223/224 (`test_cycle223_donchian_business_days_held.py`,
#       `test_cycle_p2a2_donchian_turtle.py`, `test_cycle224_...`) 패턴 재사용
# ===========================================================================
def _mk(**params) -> DonchianSwingStrategy:
    cfg = StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"sizing_mode": "position_ratio", **params},
    )
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _hold(s, ticker: str, buy_date: D, *, in_candidates: bool = True,
          breakout_high: int = 0, buy_price: int = 10_000) -> Position:
    """보유 포지션 등록. `in_candidates`/`breakout_high` 가 게이트 축이다."""
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                   strategy_id="donchian_swing", buy_date=buy_date)
    pos.high_since_buy = buy_price
    s.state.positions[ticker] = pos
    if in_candidates:
        s._candidates[ticker] = {"prev_close": buy_price, "atr": 0, "ema60": 0,
                                 "donchian_high": 0}
    if breakout_high:
        s._breakout_high[ticker] = breakout_high
    return pos


def _candle(d: D, high: int | str = 11_000, low: int = 9_000, close: int = 10_000) -> dict:
    return {
        "stck_bsop_date": d.strftime("%Y%m%d"),
        "stck_hgpr": str(high),
        "stck_lwpr": str(low),
        "stck_clpr": str(close),
        "acml_vol": "1000000",
    }


def _bdays_desc(end: D, n: int) -> list[D]:
    """`end`(포함)부터 과거로 주말 제외 n 영업일 — 내림차순(idx0=최신)."""
    out: list[D] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= _dt.timedelta(days=1)
    return out


def _prior_candles(buy_date: D, n: int, *, highs: dict[int, int | str] | None = None,
                   default_high: int | str = 11_000) -> list[dict]:
    """매수일 **이전** 봉 n 개 (DESC). `highs` 로 인덱스별 고가 지정."""
    days = _bdays_desc(buy_date - _dt.timedelta(days=1), n)
    return [_candle(d, (highs or {}).get(i, default_high)) for i, d in enumerate(days)]


@contextmanager
def _recompute_rig(s, candles: list | None = None, by_ticker: dict | None = None):
    """`recompute_held_atr` 외부 의존 격리 + **fetch 호출 카운터**.

    카운터가 이 사이클의 핵심 가드다 — 관측 로그가 fetch 를 새로 만들면(게이트를
    fetch 뒤로 옮기면) 이 사이클의 전제 "행위 변경 0" 이 깨진다(C-9).
    """
    calls: list[str] = []

    async def _fetch(ticker, days=0, **kw):
        calls.append(ticker)
        src = by_ticker.get(ticker, []) if by_ticker is not None else (candles or [])
        return list(src)

    with patch("src.api.condition.fetch_daily_candles", new=_fetch):
        s._apply_high_since_buy_from_candles = AsyncMock()
        yield calls


def _lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


def _one(caplog, marker: str) -> str:
    got = _lines(caplog, marker)
    assert len(got) == 1, f"{marker} 로그 1행 기대 — got {len(got)}: {got}"
    return got[0]


def _assert_tokens(line: str, *tokens: str) -> None:
    missing = [t for t in tokens if t not in line]
    assert not missing, f"로그 필드 누락 {missing} — got {line!r}"


# 2026-08 달력: 17(월) 18(화) 19(수) 20(목) 21(금) / 22(토) 23(일) / 24(월) 25(화)
_W_1721 = [D(2026, 8, 17), D(2026, 8, 18), D(2026, 8, 19), D(2026, 8, 20), D(2026, 8, 21)]


# ###########################################################################
# A. `[held_recompute_skip]` — 침묵 1층
# ###########################################################################

def test_a0_skip_emitter_exists():
    """계약 §1 — 관측 emitter 자체가 있어야 한다."""
    assert callable(getattr(_mk(), "_emit_held_recompute_skip", None)), (
        "계약 §1: `_emit_held_recompute_skip` 부재"
    )


async def test_a1_live_192820_skip_is_logged_with_full_gate_axes(caplog):
    """**192820 실측 재현** — 매수 당일 + 후보 잔류 + 무장 미복구 = 현행 완전 무음.

    2026-08-24 15:58 재배포 직후 그대로. 게이트 두 축(`need_atr` / `needs_high_recover`)이
    **둘 다 False** 라 `continue` 로 빠지고, 그 결과 `_breakout_high` 가 종일 미복구다.
    이 한 줄이 있었으면 규명이 로그 한 줄로 끝났다.
    """
    s = _mk(breakout_fail_n_days=2)
    _hold(s, "192820", D(2026, 8, 24))          # buy_date == today · 후보 잔류
    assert "192820" not in s._breakout_high, "탐지기 self-test — 무장 미복구 전제"

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s) as calls:
        await s.recompute_held_atr()

    assert calls == [], "skip 종목은 fetch 0 — 게이트가 fetch **앞**에 있는 이유"
    line = _one(caplog, _SKIP)
    _assert_tokens(
        line,
        "ticker=192820", "strategy=donchian_swing",
        "buy_date=2026-08-24", "today=2026-08-24",
        "need_atr=False", "in_candidates=True",
        "needs_high_recover=False", "breakout_high_armed=False",
    )
    assert "192820" not in s._breakout_high, "관측 전용 — 재도출을 억지로 부르지 않는다"


async def test_a2_no_emit_when_breakout_high_already_armed(caplog):
    """**이미 무장돼 있으면 미발화** — 같은 skip 조건이어도 그 skip 은 무해하다.

    정상 경로를 매일 찍으면 신호가 희석된다(계약 §2).
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24), breakout_high=263_000)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s) as calls:
        await s.recompute_held_atr()

    assert calls == []
    assert not _lines(caplog, _SKIP), (
        "무장된 종목의 skip 은 정상 — 로그하면 진짜 신호가 묻힌다"
    )


async def test_a3_control_403870_passes_gate_so_no_skip_log(caplog):
    """**403870 대조군** — `buy_date < today` 면 skip 자체가 없다 → 로그 없음 + 재도출 성공.

    실측 그대로: 08-21 매수 · 재도출선 46,900 복구.
    """
    s = _mk()
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)
    candles = _prior_candles(D(2026, 8, 21), 25, highs={5: 46_900, 0: 48_000, 22: 99_999})

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles) as calls:
        await s.recompute_held_atr()

    assert calls == ["403870"], "게이트 통과 종목은 fetch 1회 (기존 행위)"
    assert not _lines(caplog, _SKIP), "skip 하지 않았으므로 skip 로그도 없다"
    assert s._breakout_high.get("403870") == 46_900, (
        "사이클 223 S2 창(prior[1:period+1]) — 신호일 봉(48,000)·창 밖(99,999) 제외"
    )
    assert _lines(caplog, _REDERIVE_OK), "기존 성공 로그는 무변경으로 남는다"


async def test_a3b_control_candidate_dropout_passes_gate(caplog):
    """대조군 2 — 매수 당일이어도 **후보 이탈**(`need_atr=True`)이면 게이트를 통과한다.

    이게 '자가 치유 2경로' 중 하나다. 통과했으므로 skip 로그는 없다.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24), in_candidates=False)
    candles = _prior_candles(D(2026, 8, 24), 25, highs={5: 263_000}, default_high=250_000)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles) as calls:
        await s.recompute_held_atr()

    assert calls == ["192820"]
    assert not _lines(caplog, _SKIP)
    assert s._breakout_high.get("192820") == 263_000, "후보 이탈 경로로 재무장"


async def test_a4_capped_once_per_ticker_per_day(caplog):
    """DailyEmitCap — 같은 날 recompute 가 여러 번 돌아도 1행(계약 §7).

    `recompute_held_atr` 는 부팅뿐 아니라 스윙 폴 주기에도 돈다.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24))

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s):
        for _ in range(6):
            await s.recompute_held_atr()

    got = _lines(caplog, _SKIP)
    assert len(got) == 1, f"cap 위반 — {len(got)}건: {got}"


async def test_a5_reemits_on_day_change(caplog):
    """날짜가 바뀌면 재발화 — 날짜 키 자기리셋(`_reset_daily_state` 훅 비의존).

    익일에도 같은 종목이 '매수 당일' 상태가 되는 경우(재진입)를 재현한다.
    """
    s = _mk()
    pos = _hold(s, "192820", D(2026, 8, 24))

    with caplog.at_level(logging.INFO, logger=_LOGGER), _recompute_rig(s):
        with freeze_time("2026-08-24 16:03:52+09:00"):
            for _ in range(3):
                await s.recompute_held_atr()
            assert len(_lines(caplog, _SKIP)) == 1

        pos.buy_date = D(2026, 8, 25)               # 익일 재진입 (당일 매수)
        with freeze_time("2026-08-25 09:30:00+09:00"):
            for _ in range(3):
                await s.recompute_held_atr()

    got = _lines(caplog, _SKIP)
    assert len(got) == 2, f"날짜 전환 후 재발화 실패 — {len(got)}건: {got}"
    assert "today=2026-08-24" in got[0] and "today=2026-08-25" in got[1]


async def test_a6_cap_is_per_ticker(caplog):
    """cap 은 종목별 — 무장 미복구 2종목이면 각각 1행, 무장된 1종목은 0행."""
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24))
    _hold(s, "005930", D(2026, 8, 24))
    _hold(s, "000660", D(2026, 8, 24), breakout_high=70_000)   # 무장 → 미발화

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s):
        for _ in range(4):
            await s.recompute_held_atr()

    got = _lines(caplog, _SKIP)
    assert len(got) == 2, f"종목별 1회/일 cap 위반 — {len(got)}건: {got}"
    assert any("ticker=192820" in m for m in got)
    assert any("ticker=005930" in m for m in got)
    assert not any("ticker=000660" in m for m in got), "무장 종목은 제외"


def test_struct_1_skip_emit_precedes_fetch_and_continue():
    """소스 구조 계약 — 관측 호출이 **첫 await(fetch) 보다 앞** · **첫 `continue` 보다 앞**.

    행위 테스트(C-9)만으로는 '어쩌다 앞에 있는' 상태와 구분되지 않는다. 리팩터가 호출을
    fetch 뒤로 옮기면 매수 당일 종목마다 KIS 일봉 호출이 새로 생긴다 — 이 사이클이
    명시적으로 금지한 변화다.
    """
    src = inspect.getsource(DonchianSwingStrategy.recompute_held_atr)
    tree = ast.parse(textwrap.dedent(src))
    calls = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_emit_held_recompute_skip"
    ]
    awaits = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Await)]
    continues = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Continue)]

    assert calls, "관측 호출이 `recompute_held_atr` 안에 없다"
    assert awaits and continues, "탐지기 self-test — fetch await 와 게이트 continue 전제"
    assert min(calls) < min(awaits), (
        f"관측 호출(line {min(calls)})이 fetch await(line {min(awaits)}) 뒤에 있다 "
        "— 관측이 KIS 호출을 새로 만들면 취지 정반대다"
    )
    assert min(calls) < min(continues), (
        f"관측 호출(line {min(calls)})이 게이트 continue(line {min(continues)}) 뒤에 있다 "
        "— 도달하지 못한다"
    )


# ###########################################################################
# B. `[donchian_breakout_high_rederive_skip]` — 침묵 2·3층
# ###########################################################################

def test_b0_rederive_skip_emitter_exists():
    """계약 §5 — 재도출 실패 사유 emitter 자체가 있어야 한다."""
    assert callable(getattr(_mk(), "_emit_breakout_high_rederive_skip", None)), (
        "계약 §5: `_emit_breakout_high_rederive_skip` 부재"
    )


async def test_b5_insufficient_prior_logs_reason_and_leaves_unarmed(caplog):
    """침묵 2층 — `len(prior) < donchian_period + 1` 의 조용한 return 에 사유를 남긴다.

    사이클 223 S2 가 길이 가드를 `period` → `period+1` 로 올려 **미복구 확률이 올라간**
    경로다. 값(`need=21`)이 로그에 있어야 "봉이 몇 개 모자랐나"를 즉시 안다.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), buy_price=280_000)      # buy_date < today → 게이트 통과
    candles = [_candle(D(2026, 8, 24), 290_000)] + _prior_candles(D(2026, 8, 21), 5)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        await s.recompute_held_atr()

    line = _one(caplog, _RSKIP)
    _assert_tokens(line, "ticker=192820", "strategy=donchian_swing",
                   "buy_date=2026-08-21", "reason=insufficient_prior",
                   "prior=5", "need=21")
    assert "192820" not in s._breakout_high, "행위 무변경 — 미복구는 그대로 미복구"
    assert not _lines(caplog, _REDERIVE_OK), "성공 로그가 나오면 안 된다"


async def test_b6_zero_high_logs_reason_and_leaves_unarmed(caplog):
    """침묵 3층 — 봉은 충분한데 계산 결과가 0 (`if breakout_high > 0:` 조용한 미설정).

    KIS 고가 필드 결손(`""`) 같은 경우다. 2층과 **사유가 달라야** 대응이 갈린다
    (봉 부족 = 백필 / 값 0 = 데이터 품질).
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), buy_price=280_000)
    candles = _prior_candles(D(2026, 8, 21), 25, default_high="")   # 전부 고가 결손

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        await s.recompute_held_atr()

    line = _one(caplog, _RSKIP)
    _assert_tokens(line, "ticker=192820", "reason=zero_high", "prior=25")
    # 사이클 225 J-4 — `need=` 는 `insufficient_prior` 전용이다. 단일 포맷으로 전 사유에
    # 실으면 `reason=zero_high prior=25 need=21` 이 나오고, 운영자는 "25 ≥ 21 인데 왜
    # 실패?" 로 읽어 길이 가드 회귀(사이클 223 S2)를 의심하며 엉뚱한 곳을 판다.
    assert "need=" not in line, f"zero_high 행에 `need=` 유입 — 오독 유발: {line!r}"
    assert "192820" not in s._breakout_high
    assert not _lines(caplog, _REDERIVE_OK)


async def test_b7_successful_rederive_emits_only_the_existing_log(caplog):
    """정상 재도출 시 기존 `[donchian_breakout_high_rederive]` 만 — skip 로그 **없음**(계약 §6)."""
    s = _mk()
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)
    candles = _prior_candles(D(2026, 8, 21), 25, highs={5: 46_900})

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        await s.recompute_held_atr()

    assert s._breakout_high.get("403870") == 46_900
    assert _lines(caplog, _REDERIVE_OK), "기존 성공 로그 무변경"
    assert not _lines(caplog, _RSKIP), "성공했는데 skip 로그가 남으면 신호가 오염된다"


async def test_b8_rederive_skip_capped_once_per_ticker_per_day(caplog):
    """DailyEmitCap — 미복구 상태가 지속되면 recompute 마다 재진입한다. 그래도 1행."""
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), buy_price=280_000)
    candles = [_candle(D(2026, 8, 24), 290_000)] + _prior_candles(D(2026, 8, 21), 5)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        for _ in range(5):
            await s.recompute_held_atr()

    got = _lines(caplog, _RSKIP)
    assert len(got) == 1, f"cap 위반 — {len(got)}건"


# ###########################################################################
# IND — cap 필드 독립성 (계약 §7)
# ###########################################################################

async def test_ind_1_three_caps_do_not_silence_each_other(caplog):
    """A · B · 사이클 224 관측 cap 이 **서로 다른 필드**여야 한다.

    같은 필드를 공유하면 한 사실이 다른 사실을 침묵시킨다(사이클 224 OB-11 원칙).
    같은 날 · 같은 종목으로 셋을 연달아 발화시킨다.
    """
    s = _mk(breakout_fail_n_days=2)
    _hold(s, "192820", D(2026, 8, 24), buy_price=280_000)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        with _recompute_rig(s):                       # ① A: 매수 당일 + 후보 잔류
            await s.recompute_held_atr()
        assert len(_lines(caplog, _SKIP)) == 1

        del s._candidates["192820"]                   # ② B: 후보 이탈 → 재도출 진입, 봉 부족
        short = _prior_candles(D(2026, 8, 24), 5)
        with _recompute_rig(s, short):
            await s.recompute_held_atr()
        assert len(_lines(caplog, _RSKIP)) == 1, "A cap 이 B 를 침묵시켰다"

        s.check_exit_signal("192820", 285_000, 284_000)   # ③ 사이클 224 관측
        assert _lines(caplog, _OBS), "신규 cap 이 사이클 224 관측을 침묵시켰다"

    assert len(_lines(caplog, _SKIP)) == 1, "B/224 발화가 A 를 재발화시키면 안 된다"


# ###########################################################################
# C. 행위 무변경 (관측 전용 계약의 본체)
# ###########################################################################

async def test_c9_fetch_call_count_unchanged(caplog):
    """**fetch 호출 횟수 불변** — skip 된 종목은 fetch 0, 통과 종목은 각 1.

    관측 로그가 게이트를 fetch 뒤로 밀면 매수 당일 종목마다 KIS 일봉 호출이 새로 생긴다.
    이 사이클이 "행위 수정 금지"라고 못박은 바로 그 변화다.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24))                       # skip
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)     # 통과 (needs_high_recover)
    _hold(s, "005930", D(2026, 8, 24), in_candidates=False)  # 통과 (need_atr)
    before_candidate = s._candidates["192820"]

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, _prior_candles(D(2026, 8, 21), 25)) as calls:
        await s.recompute_held_atr()

    assert sorted(calls) == ["005930", "403870"], f"fetch 대상 변화 — got {calls}"
    assert calls.count("403870") == 1 and calls.count("005930") == 1, "중복 fetch 금지"
    assert "192820" not in calls, "skip 종목 fetch 0 (게이트 = fetch 앞)"
    # skip 종목의 상태는 어느 것도 건드리지 않는다 (순수 관찰)
    assert s._candidates["192820"] is before_candidate
    assert "192820" not in s._breakout_high
    assert "192820" not in s._channel_low
    assert "192820" not in s._entry_atr


def _case_hard_stop():
    s = _mk(breakout_fail_n_days=5)
    s._trading_days = set(_W_1721[:-1])
    _hold(s, "005930", D(2026, 8, 20), breakout_high=11_000)
    return s, 9_200, 9_900, Signal.STOP_LOSS          # -8% ≤ stop_loss_rate -7%


def _case_turtle_stop():
    s = _mk(breakout_fail_n_days=5)
    s._trading_days = set(_W_1721[:-1])
    _hold(s, "005930", D(2026, 8, 20), breakout_high=11_000)
    s._entry_atr["005930"] = 500.0                    # 10,000 - 2×500 = 9,000
    return s, 9_000, 9_900, Signal.STOP_LOSS


def _case_time_exit():
    s = _mk(breakout_fail_n_days=2)
    s._trading_days = set(_W_1721[:-1])
    _hold(s, "005930", D(2026, 8, 19), breakout_high=11_000)
    return s, 9_800, 9_900, Signal.STOP_LOSS          # 08-20 + today = 2 영업일


def _case_channel_exit():
    s = _mk(breakout_fail_n_days=5)
    s._trading_days = set(_W_1721[:-1])
    _hold(s, "005930", D(2026, 8, 20), breakout_high=11_000)
    s._channel_low["005930"] = 9_500
    return s, 9_400, 9_900, Signal.TRAILING_STOP


def _case_trailing():
    s = _mk(breakout_fail_n_days=5)
    s._trading_days = set(_W_1721[:-1])
    _hold(s, "005930", D(2026, 8, 20), breakout_high=11_000)
    s._candidates["005930"]["atr"] = 300              # 10,000 - 2.0×300 = 9,400
    return s, 9_400, 9_900, Signal.TRAILING_STOP


def _case_none():
    s = _mk(breakout_fail_n_days=5)
    s._trading_days = set(_W_1721[:-1])
    _hold(s, "005930", D(2026, 8, 20), breakout_high=11_000)
    return s, 9_800, 9_900, Signal.NONE


def _case_unarmed_same_day():
    """이 사이클의 실측 상태 그대로 — 매수 당일 · 무장 미복구. 시간청산은 닫혀 있다."""
    s = _mk(breakout_fail_n_days=2)
    s._trading_days = set(_W_1721)
    _hold(s, "005930", D(2026, 8, 21))
    return s, 9_800, 9_900, Signal.NONE


def _case_no_position():
    s = _mk(breakout_fail_n_days=5)
    s._trading_days = set(_W_1721[:-1])
    return s, 9_800, 9_900, Signal.NONE


@freeze_time("2026-08-21 10:00:00+09:00")
@pytest.mark.parametrize("builder", [
    _case_hard_stop, _case_turtle_stop, _case_time_exit, _case_channel_exit,
    _case_trailing, _case_none, _case_unarmed_same_day, _case_no_position,
], ids=["hard_stop", "turtle_stop", "time_exit", "channel_exit",
        "trailing", "none", "unarmed_same_day", "no_position"])
def test_c10_exit_signal_behavior_unchanged(builder):
    """`check_exit_signal` 반환은 대표 입력 전부에서 불변 — 이 사이클은 청산을 안 만진다."""
    s, price, open_price, expected = builder()
    assert s.check_exit_signal("005930", price, open_price) == expected


class _PoisonLogger:
    """지정 마커가 든 로그만 폭발시키는 로거 래퍼 (사이클 224 OB-10 패턴)."""

    def __init__(self, real, marker: str):
        self._real = real
        self._marker = marker

    def __getattr__(self, name):
        return getattr(self._real, name)

    def _maybe_boom(self, msg):
        if self._marker in str(msg):
            raise RuntimeError(f"관측 로그 폭발 (인위적): {self._marker}")

    def info(self, msg, *args, **kwargs):
        self._maybe_boom(msg)
        return self._real.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._maybe_boom(msg)
        return self._real.warning(msg, *args, **kwargs)


async def test_c11a_skip_emitter_failure_does_not_break_recompute(caplog, monkeypatch):
    """A emitter 가 폭발해도 `recompute_held_atr` 는 정상 완료 — 뒤 종목도 계속 처리된다."""
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24))                        # skip → emitter 폭발
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)      # 그 다음 종목
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger, _SKIP))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, _prior_candles(D(2026, 8, 21), 25, highs={5: 46_900})) as calls:
        await s.recompute_held_atr()

    assert calls == ["403870"], "관측 실패가 루프를 죽여 뒤 종목 복구가 유실됐다"
    assert s._breakout_high.get("403870") == 46_900, "뒤 종목 재도출은 그대로 성공"


async def test_c11b_rederive_skip_emitter_failure_does_not_break_recompute(caplog, monkeypatch):
    """B emitter 가 폭발해도 `recompute_held_atr` 는 정상 완료 · 재도출 결과 불변."""
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), buy_price=280_000)
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger, _RSKIP))
    short = _prior_candles(D(2026, 8, 21), 5)
    full = _prior_candles(D(2026, 8, 21), 25, highs={5: 46_900})

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, by_ticker={"192820": short, "403870": full}) as calls:
        await s.recompute_held_atr()

    assert sorted(calls) == ["192820", "403870"]
    assert "192820" not in s._breakout_high, "행위 무변경"
    assert s._breakout_high.get("403870") == 46_900


async def test_c12a_skip_emitter_failure_leaves_a_trace(caplog, monkeypatch):
    """**무흔적 흡수 금지**(계약 §8) — A emitter 내부 폭발 시 debug 흔적이 남는다.

    조용히 삼키면 이 관측이 영구 침묵해도 도입 이전 무음과 구별되지 않는다
    (사이클 224 F3 에서 같은 이유로 못박은 계약).
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24))
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger, _SKIP))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s):
        await s.recompute_held_atr()

    assert _lines(caplog, _SKIP_FAILED), (
        "실패를 흡수했지만 흔적이 없다 — 영구 침묵이 도입 이전과 구별되지 않는다"
    )
    assert not _lines(caplog, _SKIP), "실패했는데 관측 로그가 남으면 안 된다"


async def test_c12b_rederive_skip_emitter_failure_leaves_its_own_trace(caplog, monkeypatch):
    """B emitter 내부 폭발 → 전용 흔적. **재도출 실패로 오독되면 안 된다**.

    기존 `except Exception: logger.exception("도치안 breakout_high 재도출 실패")` 로
    새어 나가면 운영자는 데이터 문제(재도출 실패)로 읽는다 — 실제로는 관측기 결함이다.
    ⇒ emitter 는 **자기 try 안에서** 흡수해야 한다(계약 §8).
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), buy_price=280_000)
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger, _RSKIP))
    short = [_candle(D(2026, 8, 24), 290_000)] + _prior_candles(D(2026, 8, 21), 5)

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, short):
        await s.recompute_held_atr()

    assert _lines(caplog, _RSKIP_FAILED), "실패 흔적 부재 — 영구 침묵과 구별 불가"
    assert not _lines(caplog, _RSKIP)
    assert not _lines(caplog, _REDERIVE_ERR), (
        "관측기 결함이 기존 '재도출 실패' 로그로 새면 원인이 오독된다"
    )


# ###########################################################################
# J. 적대적 검증 후속 (사이클 225 J-1 ~ J-4)
# ###########################################################################
# J-1  침묵이 3층이 아니라 **4층**이었다 — 재도출 게이트(`if pos and pos.buy_date and
#      candles and ticker not in self._breakout_high`)가 falsy 면 B 로그도 A 로그도 없다.
# J-2  B cap 키가 ticker 단독이라 같은 날 한 사유가 다른 사유를 삼켰다.
# J-3  실패 흔적이 debug 단독이라 `system_logs`(INFO 이상만 적재)에 도달하지 않았다.
# J-4  `reason=zero_high` 행에 붙은 `need=21` 이 오독을 부른다.
# ###########################################################################


def _warn_lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING and marker in r.getMessage()]


class _BoomContains(dict):
    """무장 판정에서만 폭발하는 dict — A emitter 의 `armed` 판정 지점을 정확히 노린다.

    `mark_emitted` **이전**에 터지므로 호출할 때마다 실패가 재현된다 = 실패 흔적 cap 을
    실제로 시험할 수 있다(정상 cap 이 먼저 걸리면 두 번째 호출부터 조용히 return 한다).

    ⚠️ 시정 K-1 로 seam 이 옮겨졌다 — 무장 판정이 `ticker in self._breakout_high`
       (멤버십)에서 `self._breakout_high.get(ticker, 0) > 0`(값)으로 바뀌었다.
       시간청산 게이트가 값으로 보기 때문이고, 멤버십이면 `_breakout_high[t] == 0`
       포지션이 "무장됨" 으로 오판돼 흔적 없이 침묵한다. 그래서 poison 도 `.get`
       으로 옮긴다. `__contains__` 는 혹시 남은 멤버십 판정이 있어도 잡히도록 둔다.
    """

    def get(self, *a, **k):
        raise RuntimeError("인위적 폭발 — armed 판정(값)")

    def __contains__(self, key):
        raise RuntimeError("인위적 폭발 — armed 판정(멤버십)")


# ---------------------------------------------------------------------------
# J-1 — 침묵 4층
# ---------------------------------------------------------------------------
async def test_j1_no_candles_leaves_time_exit_permanently_blocked(caplog):
    """**빈 일봉 응답** — 게이트 falsy 로 재도출 미호출. 여기엔 자가 치유가 없다.

    `fetch_daily_candles` 는 KIS `rt_cd=0` + 빈 `output2` 시 예외 없이 `[]` 를 돌려주고
    그 `[]` 를 5분 TTL 캐시에 저장한다(`src/api/condition.py`). 그런데 이 지점은 상위
    게이트를 이미 통과한 뒤 = `buy_date < today`(또는 후보 이탈) ⇒ `days_held` 는 계속
    자라는데 시간청산은 `breakout_high > 0` 에 막혀 **영구 미발화**한다. A(1층) 로그가
    "다음 영업일 부팅에 재무장된다" 고 약속한 바로 그 경로가 이것이다.
    """
    s = _mk(breakout_fail_n_days=2)
    _hold(s, "192820", D(2026, 8, 18), in_candidates=False, buy_price=280_000)
    s._trading_days = set(_W_1721) | {D(2026, 8, 24)}

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, []) as calls:
        await s.recompute_held_atr()

    assert calls == ["192820"], "게이트는 통과했다 — fetch 는 그대로 1회(행위 무변경)"
    line = _one(caplog, _RSKIP)
    _assert_tokens(line, "ticker=192820", "strategy=donchian_swing",
                   "buy_date=2026-08-18", "reason=no_candles", "candles=0")
    assert "prior=" not in line and "need=" not in line, (
        f"4층엔 `prior` 개념 자체가 없다 — 의미 없는 필드 유입: {line!r}"
    )
    assert not _lines(caplog, _SKIP), "1층 로그는 나오면 안 된다(상위 게이트는 통과했다)"
    assert "192820" not in s._breakout_high, "관측 전용 — 재도출을 억지로 부르지 않는다"
    # 무음이 왜 위험한지의 근거: days_held 는 임계를 넘겼는데 시간청산은 닫혀 있다.
    days_held, _ = s._business_days_held(D(2026, 8, 18), D(2026, 8, 24))
    assert days_held >= 2, "탐지기 self-test — 시간청산 임계 초과 전제"
    assert s.check_exit_signal("192820", 270_000, 275_000) == Signal.NONE, (
        "행위 변경 0 — 관측은 청산을 만들지 않는다(그래서 로그가 유일한 단서다)"
    )


async def test_j1_armed_ticker_does_not_emit(caplog):
    """게이트가 falsy 인 **정상** 사유 = 이미 무장 → 발화 금지 (A 의 §2 원칙 동형)."""
    s = _mk()
    _hold(s, "192820", D(2026, 8, 18), in_candidates=False, breakout_high=263_000)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, []) as calls:
        await s.recompute_held_atr()

    assert calls == ["192820"]
    assert not _lines(caplog, _RSKIP), "무장된 종목의 게이트 falsy 는 정상 경로다"
    assert s._breakout_high["192820"] == 263_000, "무장값 무접촉"


@pytest.mark.parametrize("pos_kind,reason", [("none", "no_position"),
                                             ("no_buy_date", "no_buy_date")])
def test_j1_gate_axis_reasons_are_distinguished(caplog, pos_kind, reason):
    """게이트 실패 **사유**가 구분돼 실린다.

    두 사유 모두 `recompute_held_atr` 루프에서는 상위(:629 `pos.buy_date < today`)가
    먼저 터지므로 실질 방어용이다 — 그래도 사유가 뭉뚱그려지면 안 된다.
    """
    s = _mk()
    if pos_kind == "none":
        pos = None
    else:
        pos = _hold(s, "005930", D(2026, 8, 18))
        pos.buy_date = None

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        s._emit_breakout_high_rederive_not_called("005930", pos, [_candle(D(2026, 8, 20))])

    line = _one(caplog, _RSKIP)
    _assert_tokens(line, "ticker=005930", f"reason={reason}")
    assert "prior=" not in line and "need=" not in line and "candles=" not in line


def test_j1_not_called_emit_is_in_the_gate_else_and_adds_no_rederive():
    """소스 구조 — 관측은 게이트의 **`else`** 에만 얹힌다(재도출 강제 호출 금지)."""
    src = inspect.getsource(DonchianSwingStrategy.recompute_held_atr)
    tree = ast.parse(textwrap.dedent(src))

    def _names(nodes):
        return [n.func.attr for n in ast.walk(ast.Module(body=list(nodes), type_ignores=[]))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]

    gates = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.If) and "_rederive_breakout_high" in _names(n.body)
    ]
    assert len(gates) == 1, "재도출 게이트가 1개가 아니다 — 구조 변경 감지"
    gate = gates[0]
    assert "_emit_breakout_high_rederive_not_called" in _names(gate.orelse), (
        "4층 관측이 게이트 `else` 에 없다 — 게이트 falsy 경로는 다시 무음이 된다"
    )
    assert "_rederive_breakout_high" not in _names(gate.orelse), (
        "`else` 에서 재도출을 부르면 행위 변경(추가 복구·추가 KIS 호출)이다"
    )
    whole = _names(tree.body)
    assert whole.count("_rederive_breakout_high") == 1, "재도출 호출부 증가 감지"


# ---------------------------------------------------------------------------
# J-2 — cap 키가 사유를 삼키면 안 된다
# ---------------------------------------------------------------------------
def test_j2_two_reasons_same_ticker_same_day_both_survive(caplog):
    """같은 날 같은 종목의 `insufficient_prior` 와 `zero_high` 가 **둘 다** 남는다.

    키가 ticker 단독이면 1행만 남고(실증), 그 순간 "봉 부족 = 백필 / 값 0 = 데이터 품질"
    이라는 분리의 존재 이유가 사라진다.
    """
    s = _mk()
    pos = _hold(s, "192820", D(2026, 8, 21))

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        s._emit_breakout_high_rederive_skip("192820", pos, "insufficient_prior", 5, 21)
        s._emit_breakout_high_rederive_skip("192820", pos, "zero_high", 25, 21)

    got = _lines(caplog, _RSKIP)
    assert len(got) == 2, f"사유가 서로를 침묵시켰다 — {len(got)}행: {got}"
    assert any("reason=insufficient_prior" in m for m in got)
    assert any("reason=zero_high" in m for m in got)


def test_j2_cap_is_still_once_per_reason_per_day(caplog):
    """사유별 cap 은 여전히 1회/일 — 사유를 늘려도 폭주하지 않는다."""
    s = _mk()
    pos = _hold(s, "192820", D(2026, 8, 21))

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        for _ in range(4):
            s._emit_breakout_high_rederive_skip("192820", pos, "insufficient_prior", 5, 21)
            s._emit_breakout_high_rederive_skip("192820", pos, "zero_high", 25, 21)
            s._emit_breakout_high_rederive_skip("192820", pos, "no_candles")

    got = _lines(caplog, _RSKIP)
    assert len(got) == 3, f"사유별 1회/일 cap 위반 — {len(got)}행: {got}"


def test_j2_cap_is_still_per_ticker_and_resets_on_day_change(caplog):
    """cap 키 확장이 종목 분리·날짜 자기리셋을 깨뜨리지 않는다."""
    s = _mk()
    pos_a = _hold(s, "192820", D(2026, 8, 21))
    pos_b = _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        with freeze_time("2026-08-24 16:03:52+09:00"):
            for _ in range(3):
                s._emit_breakout_high_rederive_skip("192820", pos_a, "zero_high", 25, 21)
                s._emit_breakout_high_rederive_skip("403870", pos_b, "zero_high", 25, 21)
            assert len(_lines(caplog, _RSKIP)) == 2
        with freeze_time("2026-08-25 09:30:00+09:00"):
            s._emit_breakout_high_rederive_skip("192820", pos_a, "zero_high", 25, 21)

    assert len(_lines(caplog, _RSKIP)) == 3, "날짜 전환 후 재발화 실패"


# ---------------------------------------------------------------------------
# J-3 — 실패 흔적이 `system_logs` 에 도달해야 한다
# ---------------------------------------------------------------------------
async def test_j3_failure_trace_is_warning_not_only_debug(caplog, monkeypatch):
    """`_DbLogHandler` 는 **INFO 이상만** 적재한다 — debug 단독이면 DB 에 안 남는다.

    20:10 일일 로그 리포트와 대시보드는 `system_logs` 를 읽으므로, emitter 가 항구적으로
    깨져도 DB 기반 도구에서는 도입 이전 무음과 **구별되지 않는다**(계약 §8 금지 상태).
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24))
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger, _SKIP))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s):
        await s.recompute_held_atr()

    assert _lines(caplog, _SKIP_FAILED), "debug 스택 흔적은 유지"
    assert _warn_lines(caplog, _SKIP_FAILED), (
        "WARNING 부재 — `_DbLogHandler`(INFO 이상) 를 통과하지 못해 `system_logs` 미도달"
    )
    assert not _lines(caplog, _SKIP)


async def test_j3_rederive_failure_trace_is_warning_too(caplog, monkeypatch):
    """B emitter 흔적도 동일 — 기존 '재도출 실패' 로그로는 여전히 새지 않는다."""
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), buy_price=280_000)
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger, _RSKIP))
    short = [_candle(D(2026, 8, 24), 290_000)] + _prior_candles(D(2026, 8, 21), 5)

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, short):
        await s.recompute_held_atr()

    assert _warn_lines(caplog, _RSKIP_FAILED), "WARNING 부재 — `system_logs` 미도달"
    assert not _lines(caplog, _REDERIVE_ERR), "관측기 결함이 데이터 문제로 오독되면 안 된다"


def test_j3_failure_warning_is_capped_once_per_ticker_per_day(caplog):
    """WARNING 폭주 차단 — `recompute_held_atr` 는 스윙 폴(60s)에서도 돈다.

    `_BoomContains` 는 `mark_emitted` **이전**(armed 판정)에 터지므로 호출마다 실패가
    재현된다 = 정상 cap 이 아니라 **실패 흔적 cap** 이 시험된다.
    """
    s = _mk()
    pos = _hold(s, "192820", D(2026, 8, 24))
    s._breakout_high = _BoomContains()

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        for _ in range(6):
            s._emit_held_recompute_skip("192820", pos, False, False)

    warns = _warn_lines(caplog, _SKIP_FAILED)
    assert len(warns) == 1, f"실패 WARNING cap 위반 — {len(warns)}행"
    assert len(_lines(caplog, _SKIP_FAILED)) == 7, (
        "debug 스택은 매 실패마다 유지(6 debug + 1 warning)"
    )


def test_j3_failed_cap_key_does_not_collide_with_normal_keys(caplog):
    """실패 흔적 키(`ticker|__observer_failed__`)가 정상 관측 키를 삼키면 안 된다.

    J-2 와 같은 클래스의 결함이다 — 실패 1건이 그 날의 정상 관측을 통째로 침묵시킨다.
    """
    s = _mk()
    pos = _hold(s, "192820", D(2026, 8, 21))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        try:
            raise RuntimeError("인위적")
        except RuntimeError:
            # 사이클 258 카드 #5 — 메서드 `s._trace_observer_failure`(4인자, day_attr
            # 포함)가 모듈 함수 `trace_observer_failure`(3인자, day 는 KstDailyEmitCap
            # 내부로 흡수)로 승격됐다. donchian 자신의 로거를 명시해 캡슐화 스코프
            # (`caplog.at_level(..., logger=_LOGGER)`)와의 호환을 보존한다.
            trace_observer_failure(
                _RSKIP_FAILED, "192820", s._breakout_high_rederive_skip_logged,
                dest_logger=_mod.logger,
            )
        s._emit_breakout_high_rederive_skip("192820", pos, "insufficient_prior", 5, 21)
        s._emit_breakout_high_rederive_skip("192820", pos, "zero_high", 25, 21)

    assert _warn_lines(caplog, _RSKIP_FAILED), "탐지기 self-test — 실패 흔적 전제"
    assert len(_lines(caplog, _RSKIP)) == 2, "실패 흔적 키가 정상 관측 키를 삼켰다"


class _DoubleFaultLogger:
    """사이클 258 카드 #5 — `info`(1차 폭발) 와 `warning`(흔적의 2차 폭발) 을 각각
    독립적으로 터뜨리는 대역.

    옛 `_trace_observer_failure` 메서드의 WARNING 서식(`"...ticker=%s..."`)은
    `"ticker="` 리터럴을 포맷 문자열 자체에 담고 있어 `_PoisonLogger` 하나로
    1차·2차가 동시에 터졌다. 모듈 함수 `trace_observer_failure` 의 WARNING 은
    `"%s observer_failed key=%s"` — marker/key 는 **인자**로 전달되므로
    `_PoisonLogger._maybe_boom` 이 보는 raw 포맷 문자열에는 안 실린다(구조가
    달라졌을 뿐, 계약은 동일 — 이 테스트는 그 계약을 검증한다). 그래서 `warning`
    은 내용 무관 무조건 폭발시켜 "흔적 자신도 실패할 수 있다" 시나리오를 재현한다.
    """

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def info(self, msg, *a, **k):
        if "ticker=" in str(msg):
            raise RuntimeError("관측 로그 폭발 (인위적): ticker=")
        return self._real.info(msg, *a, **k)

    def warning(self, msg, *a, **k):
        raise RuntimeError("관측 로그 폭발 (인위적): warning")


async def test_j3_nested_guard_swallows_failure_of_the_trace_itself(caplog, monkeypatch):
    """**가장 안쪽은 어떤 경우에도 조용히 통과** — 흔적 로그가 또 터져도 전파 금지.

    흔적 로그는 이미 `except` 안이다. 여기서 2차 예외가 새면 관측이 매매 경로
    (`recompute_held_atr` 루프)를 죽여 뒤 종목의 복구까지 유실된다.
    `info`(1차, `[held_recompute_skip]` 발화 시도) 와 `warning`(2차, 흔적 자신의
    WARNING 발화 시도) 을 각각 폭발시켜 **둘 다** 조용히 흡수되는지 본다.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 24))                        # A 경로 → info 폭발
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)      # 뒤 종목
    monkeypatch.setattr(_mod, "logger", _DoubleFaultLogger(_mod.logger))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, _prior_candles(D(2026, 8, 21), 25, highs={5: 46_900})) as calls:
        await s.recompute_held_atr()      # 예외 전파 없이 완주해야 한다

    assert calls == ["403870"], "2차 예외가 루프를 죽여 뒤 종목 복구가 유실됐다"
    assert s._breakout_high.get("403870") == 46_900
    assert _lines(caplog, _SKIP_FAILED), "debug 흔적은 남는다(폭발 대상 아님)"
    assert not _warn_lines(caplog, _SKIP_FAILED), (
        "탐지기 self-test — WARNING 자체가 터지는 상황을 재현하지 못했다"
    )


# ---------------------------------------------------------------------------
# J-4 — 사유에 의미 없는 필드를 싣지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reason,args,must,must_not", [
    ("insufficient_prior", (5, 21), ("prior=5", "need=21"), ("candles=",)),
    ("zero_high",          (25, 21), ("prior=25",),          ("need=",)),
    ("no_candles",         (),       ("candles=0",),         ("need=", "prior=")),
    ("no_buy_date",        (),       (),                     ("need=", "prior=", "candles=")),
    ("no_position",        (),       (),                     ("need=", "prior=", "candles=")),
], ids=["insufficient_prior", "zero_high", "no_candles", "no_buy_date", "no_position"])
def test_j4_fields_are_reason_scoped(caplog, reason, args, must, must_not):
    """`need=` 는 `insufficient_prior` 전용 · `prior=` 는 재도출이 실제로 돈 2·3층 전용.

    `reason=zero_high prior=25 need=21` 은 "25 ≥ 21 인데 왜 실패?" 라는 오독을 부르고
    운영자를 길이 가드 회귀(사이클 223 S2) 쪽으로 오도한다 — 실제 원인은 KIS 고가
    필드 결손이다.
    """
    s = _mk()
    pos = _hold(s, "192820", D(2026, 8, 21))

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        s._emit_breakout_high_rederive_skip("192820", pos, reason, *args)

    line = _one(caplog, _RSKIP)
    _assert_tokens(line, "ticker=192820", f"reason={reason}", *must)
    leaked = [t for t in must_not if t in line]
    assert not leaked, f"사유 `{reason}` 에 의미 없는 필드 {leaked} 유입 — got {line!r}"


# ===========================================================================
# 사이클 225-K — 적대적 재검증 후속
#
# K-1 이 이 사이클에서 가장 중요한 시정이다. 관측기가 "무장" 을
# `ticker in self._breakout_high`(멤버십)로 판정했는데, 정작 시간청산 게이트와
# 사이클 224 관측기는 `breakout_high > 0`(값)으로 본다. 같은 파일 안에서 축이
# 갈렸고, 그 틈에 `_breakout_high[t] == 0` 인 포지션이 **무장됨으로 오판돼
# 흔적 없이** 빠져나갔다 — 이 사이클이 없애려던 상태 그 자체다.
#
# 도달 경로: `check_buy_signal` 이 `info["donchian_high"]` 를 **무조건** 대입하고,
# `prepare()` 는 고가 필드가 결손된 일봉에서 `prior_high=0` 후보를 만들 수 있다.
# ===========================================================================

@pytest.mark.asyncio
async def test_k1_zero_valued_breakout_high_is_not_treated_as_armed(caplog):
    """`_breakout_high[t] == 0` 은 **무장이 아니다** — A 층이 발화해야 한다.

    멤버십 판정이면 이 케이스가 조용히 return 한다(시정 전 동작).
    """
    s = _mk(breakout_fail_n_days=2)
    _hold(s, "192820", D(2026, 8, 24))
    s._breakout_high["192820"] = 0          # 키는 있으나 값이 0 = 실질 무장 해제

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s) as calls:
        await s.recompute_held_atr()

    assert calls == [], "skip 종목은 fetch 0 (행위 무변경)"
    line = _one(caplog, _SKIP)
    _assert_tokens(line, "ticker=192820", "breakout_high_armed=False")


@pytest.mark.asyncio
async def test_k1_positive_breakout_high_still_suppresses_the_log(caplog):
    """대조군 — 값이 있으면 skip 은 무해한 정상 경로라 찍지 않는다."""
    s = _mk(breakout_fail_n_days=2)
    _hold(s, "192820", D(2026, 8, 24))
    s._breakout_high["192820"] = 263_000

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s):
        await s.recompute_held_atr()

    assert _lines(caplog, _SKIP) == [], "무장 상태의 skip 을 찍으면 신호가 희석된다"


def test_k1_rederive_not_called_emitter_uses_value_not_membership(caplog):
    """4층 emitter 도 값 기준이어야 한다 — 멤버십이면 값 0 케이스를 삼킨다."""
    s = _mk(breakout_fail_n_days=2)
    pos = _hold(s, "192820", D(2026, 8, 18), in_candidates=False)
    s._breakout_high["192820"] = 0

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"):
        s._emit_breakout_high_rederive_not_called("192820", pos, [])

    _assert_tokens(_one(caplog, _RSKIP), "ticker=192820", "reason=no_candles")


def test_k1_armed_judgment_axis_matches_the_exit_gate():
    """소스 계약 — 관측기의 무장 판정과 시간청산 게이트가 **같은 축**을 쓴다.

    행위 테스트만으로는 "어쩌다 맞는" 상태와 구분되지 않는다. 두 관측기 본문에
    `in self._breakout_high` 형태의 **멤버십** 판정이 남아 있으면 축이 다시 갈린다.
    (재도출 진입 게이트 `ticker not in self._breakout_high` 는 **행위**라 제외 —
     이번 사이클은 관측 전용이므로 그건 의도적으로 멤버십을 유지한다.)
    """
    import inspect
    import re
    import textwrap

    for fn in (DonchianSwingStrategy._emit_held_recompute_skip,
               DonchianSwingStrategy._emit_breakout_high_rederive_not_called):
        body = textwrap.dedent(inspect.getsource(fn))
        code = "\n".join(
            ln for ln in body.splitlines()
            if not ln.lstrip().startswith("#")
        )
        # docstring 제거 — 설명문의 인용까지 잡으면 가드가 공허해진다
        code = re.sub(r'"""(?:.|\n)*?"""', "", code)
        assert "in self._breakout_high" not in code, (
            f"{fn.__name__} 에 멤버십 무장 판정이 남았다 — 시간청산 게이트는 "
            "`breakout_high > 0`(값)으로 본다. 축이 갈리면 값 0 포지션이 "
            "'무장됨'으로 오판돼 흔적 없이 침묵한다."
        )
        assert "_breakout_high.get(" in code, (
            f"{fn.__name__} 이 값 기준 판정을 하지 않는다"
        )
