"""사이클 226 Red — donchian 돌파선 0 **잠복 경로** 방어 (D-1 / D-2 / D-3).

> Red 작성 = tdd-engineer · Green 구현 = backend-dev.
> 수정 허용 = `src/engine/strategies/donchian_swing.py` · `src/db/stock_master_daily.py`
>              (+ 각 테스트). **8영역 diff 0** — 예외 핀은 빈 집합이다(재산출 금지).

## 발단 — 사이클 225 K-1 이 가리킨 곳보다 **위쪽**에 원인이 있었다

`prepare()` 의 일봉 source 는 `get_recent_daily_normalized` 다. 그 함수의
`_extract_raw`(`src/db/stock_master_daily.py:500`)는 **`raw` JSONB 가 없는 row 를
row 자체로 graceful 반환**한다. 그런 row 는 KIS 원본 키가 아니라 DB 정규화 컬럼
(`high_price`/`bas_dd`/…)을 들고 있으므로 `int(c.get("stck_hgpr", "0"))` 가 **0** 이다.

    highs      = [0, 0, 0, ...]
    prior_high = max(highs[1: donchian_period + 1]) == 0
    if prev_close <= prior_high:  continue      # ← 0 이면 **아무 양수 종가나 통과**

= "20일 신고가를 돌파했다" 를 **검증하지 않은 채** 후보가 만들어진다. 이어서
`check_buy_signal` 이 `self._breakout_high[ticker] = info["donchian_high"]` 를 **무조건**
대입하므로 `_breakout_high[t] = 0` 이 박히고, 그 값은

  - 시간청산 게이트 `breakout_high > 0` 에 막혀 **영구 미발화**
  - 재도출 진입 게이트 `ticker not in self._breakout_high` 는 **멤버십**이라 "무장됨" 으로
    판정해 복구를 **시도조차 않는다** (사이클 225 K-1 은 *관측기*만 값 기준으로 고쳤고,
    게이트는 행위라 의도적으로 남겼다)

## ⚠️ 현재 발화 중이 아니다 (잠복)

일봉 writer(`stock_master_daily.py:133`)가 `"raw": dict(candle)` 을 **항상** 저장하고
`ON CONFLICT ... raw = EXCLUDED.raw` 로 갱신한다. 라이브 샘플(403870·192820·005930 각
30행)도 전부 raw 보유였다. `_extract_raw` 의 폴백은 마이그레이션 033 이전 잔존 row 나
다른 경로로 들어온 row 를 위한 방어이고 **지금은 안 탄다**.

⇒ 그래서 이 사이클은 **매수를 넓히는 방향의 변경을 하지 않는다**. 안전 방향 3건만 닫는다.
   특히 `stck_hgpr`/`high_price` 양쪽 수용(= 넓히는 변경)은 **이번 범위 밖**이다 —
   사람이 깨어 있을 때 결정할 사안이다.

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

### D-1. `prepare()` 돌파선 0 후보 **거부** (매수 안전 ↑)

1. `prior_high` 산출 직후, **기존 `prev_close <= prior_high` 비교보다 앞에서**
   `prior_high <= 0` 이면 그 종목을 후보에서 제외한다(`continue`).
   순서 계약: **기존 `prev_close <= 0` 가드보다는 뒤** — 종가가 0 인 종목은 지금도
   `candle_fetch_ok` 에 계상되지 않은 채 빠지고, 그 사실을 새 마커로 덮으면
   "고가 결손" 과 "종가 결손" 이 한 신호로 뭉개진다.
2. 탈락 사유는 사이클 41 규약대로 **`donchian_excluded`** 에 append 한다
   (dict 키 `ticker` / `name` / `reason`) ⇒ funnel step 5("신고가 돌파") `excluded` 노출.
   사유 문자열은 **정상 미달(`전일 종가 … ≤ 직전 20일 신고가 …`)과 달라야** 한다 —
   같으면 운영자가 데이터 품질 사고를 평범한 시장 미달로 읽는다.
3. `stats["donchian_pass"]` 미증가. `_empty_scan_stats()` **키 집합은 불변**
   (신규 키는 ScanMonitor/DB funnel 동기화 의무를 유발한다 — 이번 범위 밖).
4. 신규 emitter **`_emit_zero_breakout_line(ticker, prior_high, prev_close, period)`**
   가 마커 `[donchian_zero_breakout_line]` 을 **WARNING 이상**으로 1회/ticker/일 남긴다.
   WARNING 인 이유 = 이 조건이 실제로 발생하면 **데이터 품질 사고**이고,
   `_DbLogHandler` 가 INFO 이상만 `system_logs` 로 올리므로 debug 는 도달하지 않는다.
   필드: `ticker` `strategy` `period` `prior_high` `prev_close`.
5. cap 은 사이클 223/224/225 의 4 cap 과 **별개 인스턴스 필드** + 날짜 키 자기리셋.
6. emitter 내부 예외는 흡수하되 **흔적**(`[donchian_zero_breakout_line_failed]`)을 남기고,
   ⚠️ 기존 `except Exception: logger.warning("도치안 스윙 prepare 실패 …")` 로 **새면 안 된다**
   (관측기 결함이 일봉 파싱 결함으로 오독된다). 흡수해도 **탈락 캡처는 이미 끝나 있어야**
   한다 ⇒ `donchian_excluded.append` 를 emit **보다 먼저** 한다.

### D-2. 재도출 진입 게이트를 **값 기준**으로 (복구 자가치유)

7. `recompute_held_atr` 의
       if pos and pos.buy_date and candles and ticker not in self._breakout_high:
   를 **값 기준**으로 바꾼다 — `not int(self._breakout_high.get(ticker, 0) or 0)`.
   근거: 시간청산 게이트(`breakout_high > 0`)·사이클 224 관측기·사이클 225 관측기가
   전부 **값**으로 본다. 이 게이트만 멤버십이라 값 0 포지션이 "무장됨" 으로 판정돼
   **영구 미복구**다.
8. **복구 전용 변경**이다 — 매수를 만들지 않고, 0(무효)을 실제 값으로 되돌릴 뿐이다.
   fetch 호출 횟수 불변(게이트는 fetch **뒤**에 있으므로 원래 fetch 는 이미 일어난다).
9. 값 0 이면 이제 재도출을 **시도**하므로 사이클 225 4층(`_emit_breakout_high_rederive_
   not_called`)은 그 경로에서 더 이상 발화하지 않고, 실패 시 2·3층 사유 로그
   (`insufficient_prior` / `zero_high`)가 뜬다.
10. 사이클 225 가 남긴 "값이 0 이면 재도출은 여전히 막힌다" 서술을 **정정**한다.

### D-3. `_extract_raw` 폴백 **가시화** (관측, 행위 변경 0)

11. `raw` 부재로 row 자체를 반환할 때 마커 `[daily_raw_missing]` 1행 —
    필드 = `ticker`(가능하면) / 부재 row 수 / 전체 row 수.
12. ⚠️ 이 함수는 **donchian 전용이 아니다**(kojiro·VCP·BFB 공유) ⇒ **호출당 최대 1행**
    + **같은 날 같은 ticker 1회**.
13. 시그니처 확장은 **기본값 있는 키워드**(`*, ticker: str | None = None`)로 —
    기존 호출부 `_extract_raw(db_rows)` 호환을 깨지 않는다.
14. **반환값은 기존과 동일**(raw 보유 row → raw dict 그 자체, 부재 row → row 그 자체).
    폴백 자체는 그대로 둔다(graceful 이 옳다). 흔적만 남긴다.
15. 관측 실패는 흡수하되 흔적(`[daily_raw_missing_failed]`) — 반환값은 여전히 정상.

## Red 유효성 (production 미변경 시점, 기대)

실행 실측 (production 미변경) = **24 FAIL / 11 PASS**. 전부 사유가 '미구현' 이다.

- FAIL = D1-0/1(×2)/2/4/5/9/10 · D2-0/1/2/5/6/8/10 · D3-0(×2)/2/3/5/6/7/8/9
- PASS(구현 후에도 계속 PASS 해야 하는 비회귀·행위불변 가드) =
  D1-3/6/7/8 · D2-3/4/7/9 · D3-1/4 · COMMON-1

특히 두 실패가 발단을 그대로 재현한다:
  D1-1  `{'005930': {'atr': 10625, 'donchian_high': 0, …}}`
        = 돌파를 검증하지 않고 만들어진 후보.
  D2-5  `reason=not_called` 발화 — 사이클 225 가 '이론상 도달 불가, 방어' 라고 적어둔
        4층 사유가 **값 0 경로로 실제 도달한다**. 게이트가 멤버십이라는 증거다.
"""

from __future__ import annotations

import ast
import datetime as _dt
import hashlib
import inspect
import logging
import subprocess
import textwrap
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

import src.db.stock_master_daily as _smd
import src.engine.strategies.donchian_swing as _mod
from src.engine.strategies.donchian_swing import (
    DonchianSwingStrategy,
    _empty_scan_stats,
)
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.strategies.donchian_swing"
_DB_LOGGER = "src.db.stock_master_daily"

# D-1
_ZERO = "[donchian_zero_breakout_line]"
_ZERO_FAILED = "[donchian_zero_breakout_line_failed]"
_PREPARE_ERR = "도치안 스윙 prepare 실패"
# D-2 (사이클 225 자산 재사용)
_REDERIVE_OK = "[donchian_breakout_high_rederive]"
_RSKIP = "[donchian_breakout_high_rederive_skip]"
_SKIP = "[held_recompute_skip]"
# D-3
_RAW_MISSING = "[daily_raw_missing]"
_RAW_MISSING_FAILED = "[daily_raw_missing_failed]"

D = _dt.date
_REPO_ROOT = Path(__file__).resolve().parents[4]


# ===========================================================================
# 공통 rig — 사이클 208(prepare) · 225(recompute) · 173(어댑터) 패턴 재사용
# ===========================================================================
def _mk(**params) -> DonchianSwingStrategy:
    cfg = StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"sizing_mode": "position_ratio", **params},
    )
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _lines(caplog, marker: str, *, min_level: int = logging.NOTSET) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if marker in r.getMessage() and r.levelno >= min_level]


def _one(caplog, marker: str, *, min_level: int = logging.NOTSET) -> str:
    got = _lines(caplog, marker, min_level=min_level)
    assert len(got) == 1, f"{marker} 로그 1행 기대 — got {len(got)}: {got}"
    return got[0]


def _assert_tokens(line: str, *tokens: str) -> None:
    missing = [t for t in tokens if t not in line]
    assert not missing, f"로그 필드 누락 {missing} — got {line!r}"


class _PoisonLogger:
    """지정 마커가 든 로그만 폭발시키는 로거 래퍼 (사이클 224 OB-10 / 225 패턴).

    ⚠️ 마커에 닫는 대괄호가 포함되므로 `[X]` 는 `[X_failed]` 의 부분문자열이 **아니다**
       — 실패 흔적 자체는 폭발하지 않는다(그게 이 래퍼가 성립하는 이유다).
    """

    def __init__(self, real, marker: str):
        self._real = real
        self._marker = marker

    def __getattr__(self, name):
        return getattr(self._real, name)

    def _boom(self, msg):
        if self._marker in str(msg):
            raise RuntimeError(f"관측 로그 폭발 (인위적): {self._marker}")

    def info(self, msg, *a, **kw):
        self._boom(msg)
        return self._real.info(msg, *a, **kw)

    def warning(self, msg, *a, **kw):
        self._boom(msg)
        return self._real.warning(msg, *a, **kw)

    def error(self, msg, *a, **kw):
        self._boom(msg)
        return self._real.error(msg, *a, **kw)


# ---------------------------------------------------------------------------
# prepare rig (사이클 208 `_run_prepare_with_candles` 확장 — 종목별 candles)
# ---------------------------------------------------------------------------
def _prep_candles(
    n: int = 70,
    base: int = 10_000,
    *,
    high_mode: str = "normal",   # "normal" | "zero" | "missing"
    breakout: bool = True,
    zero_close: bool = False,
    anchor: D = D(2026, 8, 24),
) -> list[dict]:
    """donchian prepare 의 1~4 필터를 통과하는 일봉 (최신순, idx0 = 전일).

    `high_mode`:
      normal  — `stck_hgpr` 정상 ⇒ `prior_high > 0` (대조군)
      zero    — `stck_hgpr = "0"` ⇒ `prior_high == 0` (이번 사이클의 표적)
      missing — `stck_hgpr` 키 자체 부재 ⇒ `.get(..., "0")` 폴백으로 동일하게 0
                (= `_extract_raw` 폴백 row 의 실제 모습)

    `breakout=False` 면 전일 종가를 낮춰 **정상 신고가 미달**(기존 사유)을 만든다.
    `zero_close=True` 면 종가까지 0 ⇒ 기존 `prev_close <= 0` 가드 경로.
    """
    out: list[dict] = []
    for i in range(n):
        d = anchor - _dt.timedelta(days=i + 1)
        if i == 0:
            close = int(base * (1.25 if breakout else 0.90))
            vol = "3000000"
        else:
            close = int(base * (1 + 0.001 * (n - i)))
            vol = "1000000"
        row = {
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": "0" if zero_close else str(close),
            "stck_lwpr": str(int(close * 0.98)),
            "stck_oprc": str(close),
            "acml_vol": vol,
        }
        if high_mode == "normal":
            row["stck_hgpr"] = str(int(close * 1.01))
        elif high_mode == "zero":
            row["stck_hgpr"] = "0"
        # "missing" — 키 자체를 넣지 않는다
        out.append(row)
    return out


def _bare_db_rows(n: int = 70, base: int = 10_000,
                  anchor: D = D(2026, 8, 24)) -> list[dict]:
    """`_extract_raw` 폴백이 돌려주는 **DB 정규화 row** 그대로 (KIS 키 0개)."""
    out = []
    for i in range(n):
        d = anchor - _dt.timedelta(days=i + 1)
        out.append({
            "ticker": "005930",
            "bas_dd": d,
            "open_price": base,
            "high_price": int(base * 1.01),
            "low_price": int(base * 0.98),
            "close_price": base,
            "volume": 1_000_000,
        })
    return out


@contextmanager
def _prepare_rig(strat: DonchianSwingStrategy, by_ticker: dict[str, list[dict]]):
    """`prepare()` 외부 의존 격리 — 유니버스/마스터블록/DB 어댑터/scanner 전역."""
    tickers = list(by_ticker.keys())

    async def _fake_scan():
        strat._scan_stats["universe_candidates"] = len(tickers)
        strat._scan_stats["universe_filtered"] = len(tickers)
        strat._scan_stage_counts = {
            "union_tickers": list(tickers),
            "mcap_tickers": list(tickers),
            "trade_tickers": list(tickers),
        }
        return list(tickers)

    async def _fake_daily(ticker, days=0, **kw):
        return list(by_ticker.get(ticker, []))

    import src.engine.scanner as _scanner

    with patch.object(strat, "_scan_universe", new=_fake_scan), \
            patch.object(strat, "_apply_master_block_filter_in_prepare",
                         new=AsyncMock(return_value=(list(tickers), []))), \
            patch.object(_smd, "get_recent_daily_normalized", new=_fake_daily), \
            patch("src.db.system_logs.write_log", new=AsyncMock()), \
            patch.object(_scanner, "ticker_prev_close", {}):
        yield


def _funnel_step(strat: DonchianSwingStrategy, step_no: int) -> dict:
    for entry in strat._funnel_steps:
        if entry.get("step_no") == step_no:
            return entry
    raise AssertionError(f"funnel step {step_no} 부재 — {strat._funnel_steps}")


# ---------------------------------------------------------------------------
# recompute rig (사이클 225 `_recompute_rig` 재사용)
# ---------------------------------------------------------------------------
def _hold(s, ticker: str, buy_date: D, *, in_candidates: bool = True,
          breakout_high: int | None = None, buy_price: int = 10_000) -> Position:
    """보유 포지션 등록.

    `breakout_high=None` → 키 **부재**(사이클 225 기본) / `0` → **값 0**(이번 표적).
    """
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                   strategy_id="donchian_swing", buy_date=buy_date)
    pos.high_since_buy = buy_price
    s.state.positions[ticker] = pos
    if in_candidates:
        s._candidates[ticker] = {"prev_close": buy_price, "atr": 0, "ema60": 0,
                                 "donchian_high": 0}
    if breakout_high is not None:
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
    out: list[D] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= _dt.timedelta(days=1)
    return out


def _prior_candles(buy_date: D, n: int, *, highs: dict[int, int | str] | None = None,
                   default_high: int | str = 10_500) -> list[dict]:
    days = _bdays_desc(buy_date - _dt.timedelta(days=1), n)
    return [_candle(d, (highs or {}).get(i, default_high)) for i, d in enumerate(days)]


@contextmanager
def _recompute_rig(s, candles: list | None = None, by_ticker: dict | None = None):
    calls: list[str] = []

    async def _fetch(ticker, days=0, **kw):
        calls.append(ticker)
        src = by_ticker.get(ticker, []) if by_ticker is not None else (candles or [])
        return list(src)

    with patch("src.api.condition.fetch_daily_candles", new=_fetch):
        s._apply_high_since_buy_from_candles = AsyncMock()
        yield calls


# 2026-08 달력: 17(월) 18(화) 19(수) 20(목) 21(금) / 22(토) 23(일) / 24(월) 25(화)
_W_1724 = {D(2026, 8, 17), D(2026, 8, 18), D(2026, 8, 19), D(2026, 8, 20),
           D(2026, 8, 21), D(2026, 8, 24)}


# ---------------------------------------------------------------------------
# D-3 격리 — 모듈 전역 cap 이 테스트 간 누수되지 않도록 best-effort 리셋.
# (주 격리 수단은 **테스트별 고유 ticker** 다. 이 fixture 는 belt-and-braces.)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_module_caps():
    from src.engine.daily_emit_cap import DailyEmitCap

    def _sweep():
        for name, val in list(vars(_smd).items()):
            if isinstance(val, DailyEmitCap):
                val.reset_daily()
            elif name.isupper() and name.endswith("_DAY") and isinstance(val, str):
                setattr(_smd, name, "")

    _sweep()
    yield
    _sweep()


# ###########################################################################
# D-1 — `prior_high <= 0` 후보 거부 (매수 안전 ↑)
# ###########################################################################

def test_d1_0_zero_breakout_line_emitter_exists():
    """계약 §4 — 데이터 품질 사고 emitter 자체가 있어야 한다."""
    assert callable(getattr(_mk(), "_emit_zero_breakout_line", None)), (
        "계약 §4: `_emit_zero_breakout_line` 부재 — 조용히 거르면 사고가 안 보인다"
    )


@pytest.mark.parametrize("high_mode", ["missing", "zero"], ids=["raw부재폴백", "고가0"])
async def test_d1_1_zero_prior_high_is_rejected_not_a_candidate(caplog, high_mode):
    """**핵심** — 돌파선이 0 이면 후보가 만들어지지 않는다.

    현행은 `prev_close <= prior_high` 만 보므로 `prior_high == 0` 이 **무조건 통과**한다.
    돌파선 0 은 "20일 신고가를 계산하지 못했다" 는 뜻이지 "돌파했다" 가 아니다.
    방향은 **매수를 줄이는 쪽**이다(거짓 신호 차단).
    """
    s = _mk()
    candles = _prep_candles(high_mode=high_mode)
    # 탐지기 self-test — 이 fixture 가 실제로 prior_high 0 을 만드는지
    highs = [int(c.get("stck_hgpr", "0")) for c in candles]
    assert max(highs[1: s.config.params["donchian_period"] + 1]) == 0
    assert int(candles[0]["stck_clpr"]) > 0, "종가는 양수 — prev_close 가드로 새면 안 된다"

    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), \
            _prepare_rig(s, {"005930": candles}):
        await s.prepare()

    assert "005930" not in s._candidates, (
        "돌파선 0 종목이 후보가 됐다 — 20일 신고가 검증 없이 매수 대상이 된다"
    )
    assert s._scanned_tickers == [], "scanned_tickers 로도 새면 안 된다"
    assert s._scan_stats["final_prepared"] == 0
    assert s._scan_stats["donchian_pass"] == 0, "신고가 단계 통과로 계상되면 안 된다"
    assert s._scan_stats["candle_fetch_ok"] == 1, (
        "종가는 정상이므로 fetch 단계는 통과한 것이 맞다 (순서 계약 §1)"
    )
    line = _one(caplog, _ZERO, min_level=logging.WARNING)
    _assert_tokens(line, "ticker=005930", "strategy=donchian_swing",
                   "period=20", "prior_high=0")
    assert "prev_close=" in line, f"전일 종가 미노출 — 사고 규명 단서 부족: {line!r}"


async def test_d1_2_exclusion_is_captured_with_a_distinct_reason(caplog):
    """탈락 사유 캡처 규약(사이클 41) — funnel step 5 `excluded` 에 **구분되는 사유**.

    사유가 정상 미달(`전일 종가 … ≤ 직전 20일 신고가 …`)과 같으면 운영자는 데이터 품질
    사고를 평범한 시장 미달로 읽는다. 같은 run 에 정상 미달 종목을 함께 태워 대조한다.
    """
    s = _mk()
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), \
            _prepare_rig(s, {
                "005930": _prep_candles(high_mode="missing"),          # 돌파선 0
                "000660": _prep_candles(breakout=False),               # 정상 미달
            }):
        await s.prepare()

    step5 = _funnel_step(s, 5)
    excluded = {e["ticker"]: e for e in step5["excluded"]}
    assert "005930" in excluded, (
        "돌파선 0 탈락이 funnel step5 excluded 에 없다 — 사이클 41 캡처 규약 위반"
    )
    assert "000660" in excluded, "탐지기 self-test — 정상 미달 대조군 전제"
    zero_reason = excluded["005930"]["reason"]
    miss_reason = excluded["000660"]["reason"]
    assert isinstance(zero_reason, str) and zero_reason.strip()
    assert "name" in excluded["005930"], "사이클 41 dict 키(ticker/name/reason) 규약"
    assert zero_reason != miss_reason, (
        "데이터 품질 사고와 정상 신고가 미달이 같은 사유 문자열 — 대응이 갈리지 않는다"
    )
    assert "신고가" in zero_reason and "0" in zero_reason, (
        f"사유가 '돌파선 0' 을 지시하지 않는다: {zero_reason!r}"
    )
    survived = {e["ticker"] for e in step5["survived"]}
    assert "005930" not in survived and "000660" not in survived


def test_d1_3_scan_stats_key_set_unchanged():
    """`_empty_scan_stats()` **키 집합 불변** — 신규 키는 UI/DB funnel 동기화 의무를 부른다.

    이번 사이클은 사유 캡처(`excluded`)만 쓰고 새 카운터를 만들지 않는다(계약 §3).
    """
    assert set(_empty_scan_stats()) == {
        "universe_union", "universe_candidates", "universe_filtered",
        "candle_fetch_ok", "donchian_pass", "ema_uptrend_pass",
        "volume_pass", "atr_pass", "final_prepared", "last_run_at",
    }


async def test_d1_4_marker_capped_once_per_ticker_per_day(caplog):
    """cap — 같은 날 prepare 가 여러 번 돌아도 1행(계약 §5)."""
    s = _mk()
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), \
            _prepare_rig(s, {"005930": _prep_candles(high_mode="missing")}):
        for _ in range(4):
            await s.prepare()

    got = _lines(caplog, _ZERO)
    assert len(got) == 1, f"cap 위반 — {len(got)}건: {got}"


async def test_d1_5_marker_is_per_ticker_and_reemits_next_day(caplog):
    """cap 은 종목별 · 날짜 키 자기리셋(계약 §5)."""
    s = _mk()
    by_ticker = {
        "005930": _prep_candles(high_mode="missing"),
        "000660": _prep_candles(high_mode="zero"),
        "035720": _prep_candles(),                       # 정상 — 미발화
    }
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), _prepare_rig(s, by_ticker):
        with freeze_time("2026-08-24 08:10:00+09:00"):
            await s.prepare()
            await s.prepare()
        day1 = _lines(caplog, _ZERO)
        assert len(day1) == 2, f"종목별 1회/일 위반 — {day1}"
        assert any("ticker=005930" in m for m in day1)
        assert any("ticker=000660" in m for m in day1)
        assert not any("ticker=035720" in m for m in day1), "정상 종목은 제외"

        with freeze_time("2026-08-25 08:10:00+09:00"):
            await s.prepare()

    assert len(_lines(caplog, _ZERO)) == 4, "날짜 전환 후 재발화 실패(자기리셋 부재)"


async def test_d1_6_control_positive_prior_high_unaffected(caplog):
    """**대조군** — `prior_high > 0` 정상 돌파는 행위 무영향(후보 생성 + 마커 0)."""
    s = _mk()
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), \
            _prepare_rig(s, {"005930": _prep_candles()}):
        await s.prepare()

    assert "005930" in s._candidates, "정상 돌파 종목이 탈락하면 이번 시정이 과했다"
    assert s._candidates["005930"]["donchian_high"] > 0
    assert s._scan_stats["donchian_pass"] == 1
    assert s._scan_stats["final_prepared"] == 1
    assert not _lines(caplog, _ZERO), "정상 경로에서 사고 마커가 뜨면 신호가 오염된다"


async def test_d1_7_prev_close_guard_still_first(caplog):
    """기존 `prev_close <= 0` 가드 **비회귀 + 순서 계약**(§1).

    종가 0 종목은 지금도 `candle_fetch_ok` 에 계상되지 않은 채 빠진다. 새 마커가
    이 경로까지 덮으면 "고가 결손" 과 "종가 결손" 이 한 신호로 뭉개진다.
    """
    s = _mk()
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), \
            _prepare_rig(s, {"005930": _prep_candles(zero_close=True,
                                                     high_mode="missing")}):
        await s.prepare()

    assert "005930" not in s._candidates
    assert s._scan_stats["candle_fetch_ok"] == 0, "prev_close 가드가 먼저여야 한다"
    assert not _lines(caplog, _ZERO), (
        "종가 결손을 '돌파선 0' 으로 라벨링하면 두 사고가 구별되지 않는다"
    )


async def test_d1_8_fully_normalized_rows_hit_the_prev_close_guard(caplog):
    """현실 경로 — `_extract_raw` 폴백 row(정규화 컬럼만)는 종가도 0 이라 기존 가드가 잡는다.

    이 사이클의 발단 서사가 "완전 정규화 row" 로만 성립한다고 오해되면 안 된다:
    완전 정규화 row 는 `stck_clpr` 도 없어 **기존 가드**가 먼저 잡는다. D-1 이 필요한
    범위는 종가는 살아 있고 **고가만** 결손인 부분 결손 row 다(그래서 D-3 가시화가 짝이다).
    """
    s = _mk()
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), \
            _prepare_rig(s, {"005930": _bare_db_rows()}):
        await s.prepare()

    assert "005930" not in s._candidates
    assert s._scan_stats["candle_fetch_ok"] == 0
    assert not _lines(caplog, _ZERO)


async def test_d1_9_emitter_failure_absorbed_with_trace_and_exclusion_intact(caplog):
    """emitter 폭발 → 흡수 + 전용 흔적. **탈락은 그대로** · prepare 실패로 오독 금지(§6).

    캡처(`donchian_excluded.append`)가 emit **보다 먼저** 라야 이 성질이 성립한다.
    """
    s = _mk()
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), \
            patch.object(_mod, "logger", _PoisonLogger(_mod.logger, _ZERO)), \
            _prepare_rig(s, {"005930": _prep_candles(high_mode="missing"),
                             "000660": _prep_candles()}):
        await s.prepare()

    assert "005930" not in s._candidates, "관측 실패가 안전 가드를 무력화했다"
    assert "000660" in s._candidates, "관측 실패가 뒤 종목 처리를 죽였다"
    assert _lines(caplog, _ZERO_FAILED), (
        "실패를 흡수했지만 흔적이 없다 — 영구 침묵이 도입 이전과 구별되지 않는다"
    )
    assert not _lines(caplog, _ZERO)
    assert not _lines(caplog, _PREPARE_ERR), (
        "관측기 결함이 기존 'prepare 실패' 로그로 새면 일봉 파싱 결함으로 오독된다"
    )
    excluded = {e["ticker"] for e in _funnel_step(s, 5)["excluded"]}
    assert "005930" in excluded, "emit 실패로 탈락 캡처까지 유실됐다 — append 가 먼저여야 한다"


async def test_d1_10_guard_only_narrows_never_widens(caplog):
    """방향 계약 — D-1 은 **줄이는** 변경뿐이다.

    같은 유니버스에서 후보 집합은 '정상 돌파 종목' 부분집합이어야 하고, 어떤 입력에서도
    시정 전보다 후보가 늘 수 없다. (`stck_hgpr`/`high_price` 양쪽 수용 같은 **넓히는**
    변경은 이번 범위 밖이다 — 사람이 깨어 있을 때 결정할 사안.)
    """
    s = _mk()
    by_ticker = {
        "005930": _prep_candles(high_mode="missing"),   # 돌파선 0 → 제외
        "000660": _prep_candles(high_mode="zero"),      # 돌파선 0 → 제외
        "035720": _prep_candles(),                      # 정상 돌파 → 포함
        "051910": _prep_candles(breakout=False),        # 정상 미달 → 제외
        "207940": _bare_db_rows(),                      # 종가 0 → 제외
    }
    with caplog.at_level(logging.DEBUG, logger=_LOGGER), \
            freeze_time("2026-08-24 08:10:00+09:00"), _prepare_rig(s, by_ticker):
        await s.prepare()

    assert set(s._candidates) == {"035720"}, (
        f"후보 집합이 '정상 돌파' 단일 종목이 아니다 — {sorted(s._candidates)}"
    )
    assert s._scan_stats["final_prepared"] == 1


# ###########################################################################
# D-2 — 재도출 진입 게이트를 **값 기준**으로 (복구 자가치유)
# ###########################################################################

async def test_d2_0_zero_value_triggers_rederive_and_arms(caplog):
    """**핵심** — `_breakout_high[t] == 0` 이면 재도출을 **시도**하고 실제 값으로 갱신한다.

    현행 게이트 `ticker not in self._breakout_high` 는 **멤버십**이라 값 0 을 "무장됨"
    으로 판정해 복구를 시도조차 않는다 = 영구 미복구.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), breakout_high=0, buy_price=45_000)
    candles = _prior_candles(D(2026, 8, 21), 25, highs={5: 46_900, 0: 48_000})

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, candles) as calls:
        await s.recompute_held_atr()

    assert calls == ["192820"], "fetch 는 원래대로 1회 (게이트는 fetch **뒤**)"
    assert s._breakout_high.get("192820") == 46_900, (
        "값 0 이 실제 돌파선으로 복구되지 않았다 — 멤버십 게이트가 복구를 막고 있다"
    )
    assert _lines(caplog, _REDERIVE_OK), "기존 성공 로그가 남아야 한다"
    assert not _lines(caplog, _RSKIP), "성공했는데 skip 사유 로그가 남으면 신호 오염"


async def test_d2_1_zero_value_failure_emits_layer2_reason(caplog):
    """값 0 + 봉 부족 → 사이클 225 **2층** 사유(`insufficient_prior`)가 뜬다.

    시도했으므로 이제 사유가 보인다. 결과는 여전히 미복구(행위상 손해 0).
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), breakout_high=0, buy_price=280_000)
    candles = [_candle(D(2026, 8, 24), 290_000)] + _prior_candles(D(2026, 8, 21), 5)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        await s.recompute_held_atr()

    line = _one(caplog, _RSKIP)
    _assert_tokens(line, "ticker=192820", "reason=insufficient_prior",
                   "prior=5", "need=21")
    assert int(s._breakout_high.get("192820", 0) or 0) == 0, "미복구는 미복구 그대로"


async def test_d2_2_zero_value_failure_emits_layer3_reason(caplog):
    """값 0 + 고가 전부 결손 → 사이클 225 **3층** 사유(`zero_high`).

    이 조합이야말로 이번 사이클의 발단(고가 결손 일봉)과 정확히 같은 데이터 상태다.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), breakout_high=0, buy_price=280_000)
    candles = _prior_candles(D(2026, 8, 21), 25, default_high="")

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        await s.recompute_held_atr()

    line = _one(caplog, _RSKIP)
    _assert_tokens(line, "ticker=192820", "reason=zero_high", "prior=25")
    assert "need=" not in line, "사이클 225 J-4 — need= 는 insufficient_prior 전용"


async def test_d2_3_control_armed_positive_value_still_skips_rederive(caplog):
    """**대조군** — 값 > 0 이면 여전히 재도출을 시도하지 않고 값도 건드리지 않는다."""
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), breakout_high=263_000, buy_price=280_000)
    candles = _prior_candles(D(2026, 8, 21), 25, highs={5: 999_999})

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, candles) as calls:
        await s.recompute_held_atr()

    assert calls == ["192820"], "fetch 는 기존대로 1회"
    assert s._breakout_high["192820"] == 263_000, "무장값 무접촉 (loosen/변경 금지)"
    assert not _lines(caplog, _REDERIVE_OK), "이미 무장된 종목을 재도출하면 행위 변경이다"
    assert not _lines(caplog, _RSKIP), "무장된 종목의 게이트 falsy 는 정상 경로다"


async def test_d2_4_missing_key_still_triggers_rederive(caplog):
    """기존 동작 보존 — **키 부재**(사이클 225 이전부터의 정상 복구 경로)도 그대로 시도."""
    s = _mk()
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)     # breakout_high 키 부재
    assert "403870" not in s._breakout_high, "탐지기 self-test"
    candles = _prior_candles(D(2026, 8, 21), 25, highs={5: 46_900, 0: 48_000})

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        await s.recompute_held_atr()

    assert s._breakout_high.get("403870") == 46_900
    assert _lines(caplog, _REDERIVE_OK)


async def test_d2_5_zero_value_no_longer_reported_as_layer4(caplog):
    """값 0 은 이제 4층(`재도출 미호출`)이 아니다 — 시도했으므로 2·3층 사유로 갈린다.

    사이클 225 J-1 의 `no_candles`/`not_called` 계열이 이 경로에서 뜨면, 시정이 게이트가
    아니라 관측기만 건드렸다는 뜻이다.

    ⚠️ 부수 소득 — 현행(멤버십 게이트)에서 이 입력은 실제로 `reason=not_called` 를 찍는다.
       사이클 225 는 그 사유를 "이론상 도달 불가, 방어" 라고 적어뒀는데, **값 0 경로로
       도달한다**. 즉 그 주석 자체가 멤버십 게이트의 부작용을 증언하고 있었다.
    """
    s = _mk()
    _hold(s, "192820", D(2026, 8, 21), breakout_high=0, buy_price=280_000)
    candles = _prior_candles(D(2026, 8, 21), 25, default_high="")

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        await s.recompute_held_atr()

    got = _lines(caplog, _RSKIP)
    assert got, "사유 로그 자체가 없다"
    for bad in ("reason=not_called", "reason=no_candles", "reason=no_position",
                "reason=no_buy_date"):
        assert not any(bad in m for m in got), (
            f"값 0 인데 4층 사유({bad})가 떴다 — 게이트가 여전히 멤버십이다: {got}"
        )


def test_d2_6_rederive_gate_is_value_based_in_source():
    """소스 구조 — 재도출 게이트 조건식에 **멤버십 판정이 남아 있으면 안 된다**.

    행위 테스트만으로는 "어쩌다 통과하는" 상태와 구별되지 않는다. 주석/docstring 은
    허용하되(AST 는 문자열을 보지 않는다) **게이트 `If` 의 test 노드**만 검사한다 —
    같은 함수의 `ticker not in self._entry_atr`(터틀 재도출)은 무관하므로 건드리지 않는다.
    """
    src = inspect.getsource(DonchianSwingStrategy.recompute_held_atr)
    tree = ast.parse(textwrap.dedent(src))

    def _names(nodes):
        return [n.func.attr for n in ast.walk(ast.Module(body=list(nodes), type_ignores=[]))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]

    gates = [n for n in ast.walk(tree)
             if isinstance(n, ast.If) and "_rederive_breakout_high" in _names(n.body)]
    assert len(gates) == 1, "재도출 게이트가 1개가 아니다 — 구조 변경 감지"
    # ⚠️ 게이트가 지역변수를 경유할 수 있다(시정 L-2 — `int()` 를 조건식 안에서 부르면
    #    try 밖 예외 지점이 새로 생겨 루프가 죽는다). 그래서 `If.test` 만 보면
    #    "`_breakout_high` 를 안 본다" 는 **거짓 경보**가 난다. 조건식이 참조하는
    #    지역 이름을 **같은 함수의 단일 대입**으로 되짚어 그 값까지 포함해 검사한다.
    #    되짚지 않고 함수 전체를 훑으면 무관한 `_breakout_high` 접근(예: 4층 emitter
    #    호출)까지 잡혀 가드가 공허해진다.
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef))
    assigns: dict[str, ast.AST] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            assigns.setdefault(n.targets[0].id, n.value)
    #    ⚠️ 되짚기는 **전이적**이어야 한다. 한 단계만 보면
    #       `_armed = _bh_raw if ... else 0` 에서 멈춰 `_bh_raw` 가 가리키는
    #       `self._breakout_high.get(...)` 에 닿지 못하고 거짓 경보가 난다.
    test = gates[0].test
    reachable, seen, stack = [test], set(), [test]
    while stack:
        node = stack.pop()
        for nm in ast.walk(node):
            if isinstance(nm, ast.Name) and nm.id in assigns and nm.id not in seen:
                seen.add(nm.id)
                reachable.append(assigns[nm.id])
                stack.append(assigns[nm.id])
    dumped = "".join(ast.dump(x) for x in reachable)
    assert "_breakout_high" in dumped, (
        "게이트(및 그 조건이 참조하는 지역 대입)가 `_breakout_high` 를 더 이상 안 본다"
    )
    assert "NotIn()" not in dumped, (
        "재도출 게이트가 여전히 멤버십(`not in`) 판정 — 값 0 포지션이 영구 미복구다"
    )
    # 사이클 225 J-1 구조 계약 유지 (else 에 4층 관측, 재도출 강제 호출 금지)
    assert "_emit_breakout_high_rederive_not_called" in _names(gates[0].orelse)
    assert "_rederive_breakout_high" not in _names(gates[0].orelse)
    assert _names(tree.body).count("_rederive_breakout_high") == 1


async def test_d2_7_upper_gate_skip_behavior_unchanged(caplog):
    """비회귀(사이클 225 A) — 상위 게이트 skip 경로는 **그대로**다.

    매수 당일 + 후보 잔류 + 값 0 이면 여전히 `continue` 이고 fetch 0 이다. D-2 는
    상위 게이트를 건드리지 않는다(그걸 건드리면 매수 당일 종목마다 KIS 호출이 생긴다).
    """
    s = _mk(breakout_fail_n_days=2)
    _hold(s, "192820", D(2026, 8, 24), breakout_high=0)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s) as calls:
        await s.recompute_held_atr()

    assert calls == [], "상위 게이트가 fetch 앞이라는 계약이 깨졌다"
    _assert_tokens(_one(caplog, _SKIP), "ticker=192820", "breakout_high_armed=False")
    assert int(s._breakout_high.get("192820", 0) or 0) == 0


async def test_d2_8_stale_cycle225_claim_is_corrected():
    """사이클 225 가 남긴 "값 0 은 여전히 막힌다" 서술 정정(계약 §10).

    코드가 자가 복구하도록 바뀌었는데 주석이 "여전히 막힌다" 로 남아 있으면, 다음 사람이
    그 문장을 근거로 D-2 를 되돌린다.
    """
    text = Path(_mod.__file__).read_text(encoding="utf-8")
    # ⚠️ 소스에서 이 문장은 줄바꿈으로 쪼개져 있으므로 **줄 단위 조각**으로 찾는다.
    for stale in ("값이 0 이면 재도출은 여전히",
                  "`ticker not in self._breakout_high`)는 **무변경**"):
        assert stale not in text, (
            f"사이클 225 의 스테일 서술이 남아 있다: {stale!r}"
        )


async def test_d2_9_fetch_count_and_exit_signals_unchanged(caplog):
    """행위 불변 — fetch 횟수 · 다른 청산 분기는 그대로."""
    s = _mk(breakout_fail_n_days=5)
    _hold(s, "192820", D(2026, 8, 24), breakout_high=0)         # skip → fetch 0
    _hold(s, "403870", D(2026, 8, 21), buy_price=45_000)        # 통과 → fetch 1
    _hold(s, "005930", D(2026, 8, 24), in_candidates=False,
          breakout_high=0)                                      # 통과 → fetch 1

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), \
            _recompute_rig(s, _prior_candles(D(2026, 8, 21), 25,
                                             highs={5: 46_900})) as calls:
        await s.recompute_held_atr()

    assert sorted(calls) == ["005930", "403870"], f"fetch 대상 변화 — {calls}"
    # 하드손절은 무장 여부와 무관하게 그대로 동작 (청산 절대 미차단)
    s._trading_days = set(_W_1724)
    assert s.check_exit_signal("403870", 41_000, 44_000) == Signal.STOP_LOSS


async def test_d2_10_recovery_unblocks_permanently_dead_time_exit(caplog):
    """**복구의 값어치** — 값 0 이던 포지션의 시간청산이 되살아난다.

    시간청산 게이트는 `breakout_high > 0 and days_held >= n_days and 현재가 < breakout_high`
    다. 값 0 이면 첫 조건에서 영구 미발화이고, 멤버십 게이트가 그 상태를 고칠 기회를
    영원히 지운다. 재도출이 실제 값을 복구하면 게이트가 정상 판정으로 돌아온다.
    ⚠️ 이건 **복구**이지 매수 확대가 아니다.
    """
    s = _mk(breakout_fail_n_days=2)
    _hold(s, "192820", D(2026, 8, 18), breakout_high=0, buy_price=10_000)
    s._trading_days = set(_W_1724)
    candles = _prior_candles(D(2026, 8, 18), 25, highs={5: 11_000},
                             default_high=10_500)

    with caplog.at_level(logging.INFO, logger=_LOGGER), \
            freeze_time("2026-08-24 16:03:52+09:00"), _recompute_rig(s, candles):
        # 복구 전 = 시간청산 영구 미발화 (탐지기 self-test)
        assert s.check_exit_signal("192820", 9_800, 9_900) == Signal.NONE
        days_held, _ = s._business_days_held(D(2026, 8, 18), D(2026, 8, 24))
        assert days_held >= 2, "탐지기 self-test — 시간청산 임계 초과 전제"
        await s.recompute_held_atr()

    assert s._breakout_high.get("192820") == 11_000
    assert s.check_exit_signal("192820", 9_800, 9_900) == Signal.STOP_LOSS, (
        "복구 후에도 시간청산이 죽어 있다 — 게이트가 값 0 을 못 고쳤다"
    )


# ###########################################################################
# D-3 — `_extract_raw` 폴백 가시화 (관측, 행위 변경 0)
# ###########################################################################

def _raw_row(dd: D, close: int = 10_000, ticker: str = "005930") -> dict:
    return {
        "ticker": ticker, "bas_dd": dd, "close_price": close,
        "high_price": int(close * 1.01), "flng_cls_code": "00", "prtt_rate": 0.0,
        "raw": {"stck_bsop_date": dd.strftime("%Y%m%d"), "stck_clpr": str(close),
                "stck_hgpr": str(int(close * 1.01))},
    }


def _bare_row(dd: D, close: int = 10_000, ticker: str = "005930", *,
              empty_raw: bool = False) -> dict:
    row = {
        "ticker": ticker, "bas_dd": dd, "close_price": close,
        "high_price": int(close * 1.01), "flng_cls_code": "00", "prtt_rate": 0.0,
    }
    if empty_raw:
        row["raw"] = {}          # 빈 dict 도 현행 계약상 '부재'(falsy) 취급
    return row


def _mixed(n_raw: int, n_bare: int, *, ticker: str = "005930",
           empty_raw: bool = False) -> list[dict]:
    base = D(2026, 8, 24)
    rows = [_raw_row(base - _dt.timedelta(days=i), ticker=ticker)
            for i in range(n_raw)]
    rows += [_bare_row(base - _dt.timedelta(days=n_raw + i), ticker=ticker,
                       empty_raw=empty_raw)
             for i in range(n_bare)]
    return rows


@pytest.mark.parametrize("empty_raw", [False, True], ids=["raw키부재", "raw빈dict"])
def test_d3_0_missing_raw_rows_leave_a_trace(caplog, empty_raw):
    """**핵심** — `raw` 부재 row 가 섞이면 `[daily_raw_missing]` 1행.

    지금은 완전 무음이라, 이 경로가 살아나도(마이그레이션 033 이전 잔존 row 등)
    아무도 모른다. `prepare()` 는 그 row 에서 고가 0 을 읽고 **돌파선 0** 을 만든다.
    """
    rows = _mixed(18, 4, ticker="900001", empty_raw=empty_raw)

    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"):
        _smd._extract_raw(rows, ticker="900001")

    line = _one(caplog, _RAW_MISSING, min_level=logging.INFO)
    _assert_tokens(line, "900001", "4", "22")


def test_d3_1_no_trace_when_every_row_has_raw(caplog):
    """전부 raw 보유(=라이브 실측 상태)면 **무발화** — 정상 경로를 매일 찍으면 신호가 희석된다."""
    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"):
        _smd._extract_raw(_mixed(22, 0, ticker="900002"))

    assert not _lines(caplog, _RAW_MISSING)


def test_d3_2_one_line_per_call_even_with_many_missing_rows(caplog):
    """**호출당 최대 1행** — 이 함수는 donchian 전용이 아니다(kojiro·VCP·BFB 공유).

    row 당 1행이면 100일 창 × 전 전략 × 전 종목으로 로그가 폭주한다.
    """
    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"):
        _smd._extract_raw(_mixed(0, 60, ticker="900003"), ticker="900003")

    assert len(_lines(caplog, _RAW_MISSING)) == 1


def test_d3_3_capped_per_ticker_per_day(caplog):
    """같은 날 같은 ticker 반복 → 1회 · 다른 ticker 는 각각 · 날짜 바뀌면 재발화."""
    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER):
        with freeze_time("2026-08-24 16:00:00+09:00"):
            for _ in range(5):
                _smd._extract_raw(_mixed(10, 2, ticker="900004"), ticker="900004")
            assert len(_lines(caplog, _RAW_MISSING)) == 1, "동일 ticker cap 위반"
            _smd._extract_raw(_mixed(10, 2, ticker="900005"), ticker="900005")
            assert len(_lines(caplog, _RAW_MISSING)) == 2, "cap 이 ticker 별이 아니다"

        with freeze_time("2026-08-25 16:00:00+09:00"):
            _smd._extract_raw(_mixed(10, 2, ticker="900004"), ticker="900004")

    assert len(_lines(caplog, _RAW_MISSING)) == 3, "날짜 전환 후 재발화 실패"


def test_d3_4_return_value_is_byte_identical_to_current_contract(caplog):
    """**행위 변경 0** — 반환값은 지금과 동일(raw 보유 → raw dict / 부재 → row 그 자체).

    폴백 자체는 옳다(graceful). 이 사이클은 흔적만 남긴다.
    """
    rows = _mixed(3, 2, ticker="900006")

    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"):
        out = _smd._extract_raw(rows)

    assert len(out) == len(rows)
    for i in range(3):
        assert out[i] is rows[i]["raw"], "raw 보유 row 는 raw dict 그대로 반환"
    for j in (3, 4):
        assert out[j] is rows[j], "raw 부재 row 는 row 자체 graceful 반환"


def test_d3_5_signature_stays_backward_compatible():
    """기존 호출부 호환 — 위치인자 1개 호출이 그대로 동작하고, 추가 파라미터는 전부 기본값."""
    sig = inspect.signature(_smd._extract_raw)
    params = list(sig.parameters.values())
    assert params[0].name == "db_rows"
    for p in params[1:]:
        assert p.default is not inspect.Parameter.empty, (
            f"신규 파라미터 {p.name} 에 기본값이 없다 — 기존 호출부가 깨진다"
        )
    assert "ticker" in sig.parameters, "계약 §13: ticker 키워드 파라미터"
    assert sig.parameters["ticker"].kind is inspect.Parameter.KEYWORD_ONLY, (
        "ticker 는 **키워드 전용**이어야 한다(위치인자 오삽입 차단)"
    )
    # 위치인자 1개 호출 = 기존 호출부 형태
    rows = _mixed(2, 1, ticker="900007")
    out = _smd._extract_raw(rows)
    assert out[0] is rows[0]["raw"] and out[2] is rows[2]


async def test_d3_6_adapter_path_reports_the_ticker(caplog):
    """어댑터 정상 경로(`get_recent_daily_normalized` → DB 사용)에서도 ticker 가 실린다.

    ticker 없이 "부재 4/22" 만 남으면 어느 종목의 일봉이 썩었는지 알 수 없어 대응이 안 된다.
    """
    rows = _mixed(20, 4, ticker="900008")

    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"), \
            patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=rows)), \
            patch.object(_smd, "max_bas_dd",
                         new=AsyncMock(return_value=D(2026, 8, 24))), \
            patch("src.api.condition.fetch_daily_candles",
                  new=AsyncMock(return_value=[])) as kis:
        out = await _smd.get_recent_daily_normalized("900008", 22, min_required=22)

    assert kis.await_count == 0, "정상 DB 경로 전제 (락/신선도/부족 폴백 아님)"
    assert len(out) == 24
    _assert_tokens(_one(caplog, _RAW_MISSING, min_level=logging.INFO), "900008", "4")


async def test_d3_7_kis_fallback_path_reports_the_ticker(caplog):
    """KIS 폴백이 **실패**해 DB raw graceful 로 떨어지는 경로에서도 ticker 가 실린다.

    이 경로(`_kis_fallback` 의 `except`)가 부분 결손 row 를 그대로 prepare 로 내보내는
    두 번째 입구다.
    """
    rows = _mixed(5, 3, ticker="900009")

    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"), \
            patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=rows)), \
            patch.object(_smd, "max_bas_dd",
                         new=AsyncMock(return_value=D(2026, 8, 24))), \
            patch("src.api.condition.fetch_daily_candles",
                  new=AsyncMock(side_effect=RuntimeError("KIS down"))):
        out = await _smd.get_recent_daily_normalized("900009", 22, min_required=22)

    assert len(out) == 8, "graceful 반환 계약 불변"
    _assert_tokens(_one(caplog, _RAW_MISSING, min_level=logging.INFO), "900009", "3")


def test_d3_8_observer_failure_absorbed_with_trace_and_value_intact(caplog, monkeypatch):
    """관측 실패는 흡수 + 흔적 · **반환값은 그대로**(계약 §15).

    폴백은 매매 hot path 는 아니지만 5 전략 prepare 의 일봉 입구다 — 관측이 여기서
    예외를 뿜으면 그날의 스캔이 통째로 죽는다.
    """
    rows = _mixed(4, 2, ticker="900010")
    monkeypatch.setattr(_smd, "logger", _PoisonLogger(_smd.logger, _RAW_MISSING))

    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"):
        out = _smd._extract_raw(rows, ticker="900010")

    assert out[0] is rows[0]["raw"] and out[4] is rows[4], "반환값이 관측 실패에 오염됐다"
    assert _lines(caplog, _RAW_MISSING_FAILED), (
        "실패를 흡수했지만 흔적이 없다 — 영구 침묵이 도입 이전 무음과 구별되지 않는다"
    )
    assert not _lines(caplog, _RAW_MISSING)


def test_d3_9_ticker_unknown_still_traces(caplog):
    """ticker 미전달(기존 호출부 형태)이어도 **흔적은 남는다** — 침묵보다 낫다."""
    with caplog.at_level(logging.DEBUG, logger=_DB_LOGGER), \
            freeze_time("2026-08-24 16:00:00+09:00"):
        _smd._extract_raw(_mixed(3, 3, ticker="900011"))

    assert _lines(caplog, _RAW_MISSING, min_level=logging.INFO), (
        "ticker 를 모른다고 통째로 침묵하면 이 경로는 영원히 안 보인다"
    )


# ###########################################################################
# COMMON — 8영역 diff 0 (예외 핀 = **빈 집합**, 재산출 금지)
# ###########################################################################

_EIGHT_AREAS = [
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/scanner.py",
    "src/engine/session.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
    "src/realtime",
    "src/auth",
]
# 🔁 2026-08-25 (cycle227) — 면제 기전을 **파일명 집합 → 내용 sha 핀**으로 교체.
#
#    사이클 226 은 `_ALLOWED: set[str] = set()` 로 두었다. 빈 집합인 동안은 문제가
#    없지만, 거기에 파일명을 넣는 순간 면제가 **영구**가 된다 — cycle222-a3 이
#    "제외 결정이 한쪽 경로에만 걸리면 제외가 아니다" 를 근거로 파일명 면제를 버리고
#    자기소멸형 내용 핀으로 옮겨간 바로 그 이유다. cycle227 이 처음으로 이 가드에
#    면제를 요구하게 되었으므로, 이름을 등록하는 대신 **자매 가드
#    (`tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py`)의 기전을 그대로 이식**한다.
#    ⇒ 검사 강도는 낮아지지 않는다: 핀에 없는 8영역 파일은 여전히 즉시 FAIL 이고,
#      핀에 있는 파일도 내용이 한 바이트라도 달라지면 FAIL 한다. 커밋되면 그 경로가
#      `git diff HEAD` 에 안 나타나 면제가 조회조차 되지 않는다(자기소멸).
#
#    cycle227 승인 근거 = P0-1(BFB·VCP 가 유령 키 `ticker_prices["acml_vol"]` 을
#    읽어 전 기간 매수 0건) 시정 Stage 0 의 **사용자 명시 8영역 승인**
#    (`handler.py` + `risk.py` 두 파일 한정). 둘 다 순수 추가이며
#    `ticker_prices` 4키는 불변이다.
# TODO(cycle227 커밋 후): 아래 두 항목을 **삭제**하고 dict 를 비운다.
# ✅ 2026-08-27 — cycle227 항목은 커밋 `a7245af` 로 **자기소멸**(죽은 값 삭제).
#    cycle228 의 BFB·VCP 변경은 이 가드의 8영역 목록 밖이라 신규 핀이 불요하다.
# 🔁 2026-08-29 (cycle235) — 257720 실사고(부분 체결 positions 수량 오염) 시정의
#    **사용자 명시 8영역 승인**("N1부터 작업 시작", 범위 = handler·order_engine 한정):
#    handler 는 체결수량 소스 fields[16](ODER_QTY 오독)→fields[9](CNTG_QTY 정본) 1줄
#    + 주석 정정, order_engine 은 overrun 클램프(누적>주문수량 시 캡 + WARNING) 순수
#    추가. 명세 `_workspace/red/cycle235_fill_qty_spec.md`.
#    + cycle236(N2, "n2 시작" 승인): APBK0400 분류(is_sell_qty_exceeded, balance.py
#    비8영역) 소비 분기 — 잔고 재대조 수량 보정/잠김 보존/실보유0 기존 경로
#    (`_workspace/red/cycle236_sell_qty_exceeded_spec.md`).
# ✅ 2026-09-02 — cycle235 항목(handler.py·order_engine.py·realtime/CLAUDE.md)은
#    커밋 f2b831f 로 자기소멸, 삭제 (더 이상 `git diff HEAD` 에 나타나지 않는다).
#
# 🔁 2026-09-02 (cycle238) — 프리장 청산 보류 게이트 08:00 정각 ~30초 구멍 시정의
#    사용자 명시 8영역 승인("P1-6 은 A 로 진행", 범위 = `risk.py` 단독). 자매 가드
#    (`test_cycle223_ast_donchian_exit_fix.py`)와 **같은 값**으로 핀한다.
#    명세 = `_workspace/red/cycle238_pre_market_clock_gate_spec.md`.
# TODO(cycle238 커밋 후): 아래 항목을 **삭제**하고 dict 를 비운다.
_ALLOWED_CONTENT_SHA: dict[str, str] = {
    # 2026-09-05 비움(리팩토링 리뷰 카드 #3) — 종전 항목은 전부 커밋돼 자기소멸한 죽은 값이었다.
    # 다음 8영역 승인 사이클이 in-flight 변경의 내용 sha 를 여기 한시 등록하고, 커밋 후 다시 비운다.
}


def _git(*args: str) -> str:
    res = subprocess.run(["git", *args], cwd=_REPO_ROOT,
                         capture_output=True, text=True)
    if getattr(res, "returncode", 0) != 0:
        raise AssertionError(
            f"git {' '.join(args)} 실패 (rc={res.returncode}) — fail-closed. "
            f"stderr: {(res.stderr or '').strip()}"
        )
    return res.stdout


def _content_sha(path: str) -> str:
    """면제 대상 파일 **내용**의 sha256 (`shasum -a 256 <파일>` 과 동일).

    diff 텍스트가 아니라 파일 바이트를 해시한다 — diff 텍스트는 git config
    (`diff.noprefix` / `diff.mnemonicPrefix` / `diff.context` / `core.abbrev` …)
    에 따라 **코드 변경 0인데도** 달라져서, 그때마다 "핀 재산출" 을 유도하고
    그 과정에서 진짜 8영역 변경까지 함께 봉인된다(cycle222-a3 G-2 실측).
    """
    return hashlib.sha256((_REPO_ROOT / path).read_bytes()).hexdigest()


def test_common_1_eight_areas_untouched():
    """8영역 diff **0** — staged/unstaged/untracked 전부.

    ⚠️ 실패 시 "핀을 재산출" 하지 마라. 먼저 8영역 실제 변경을 확인하고 되돌린다
    (사이클 222-a3 의 자기소멸 가드 교훈).
    ⚠️ 워킹트리의 미커밋 cycle221(`scheduler.py` + 테스트 6파일)은 8영역이 아니므로
    이 가드에 걸리지 않는다 — `git checkout`/`stash`/`restore` 로 건드리지 마라.
    """
    tracked = _git("diff", "HEAD", "--name-only", "--", *_EIGHT_AREAS).split()
    untracked = _git("ls-files", "--others", "--exclude-standard",
                     "--", *_EIGHT_AREAS).split()
    changed = set(tracked) | set(untracked)
    unexpected = sorted(changed - set(_ALLOWED_CONTENT_SHA))
    assert unexpected == [], (
        f"8영역 변경 감지: {unexpected} — 사이클 226 허용치는 **0**이다. "
        "핀을 늘리기 전에 실제 변경을 되돌려라."
    )
    for path in sorted(changed & set(_ALLOWED_CONTENT_SHA)):
        assert _content_sha(path) == _ALLOWED_CONTENT_SHA[path], (
            f"{path} 의 내용이 면제 스냅샷과 다르다.\n"
            "⚠️ **핀을 먼저 재산출하지 마라** — 그 순간 8영역 실제 변경이 그대로 "
            "새 스냅샷으로 봉인된다.\n"
            f"  1) `git diff HEAD -- {path}` 를 눈으로 읽어라.\n"
            "  2) 승인 범위 밖 변경이면 되돌려라 (8영역 diff 0 이 기본 계약이다).\n"
            "  3) 승인된 작업(cycle227 Stage 0) 자체가 갱신된 것이 확실할 때만 "
            f"재산출한다 (`shasum -a 256 {path}`)."
        )
