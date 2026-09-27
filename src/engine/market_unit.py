"""cycle382 — 시장 유닛(단계형) 판정 leaf.

KODEX 200(``069500``) 일봉 60일선으로 그날 장세를 4단계로 나눈다. 위·상승 = 1.0
(설계 랏 그대로) · 위·하락 = 0.75 · 아래·상승 = 0.5 · 아래·하락 = 0.0(신규 진입
없음). 결측·stale·예외는 전부 ``m=1.0``(fail-open) — 결측이 매수를 조용히
줄이면 안 된다.

명세 정본 = ``_workspace/red/cycle382_market_unit_spec.md`` §1~§3.
설계 정본 = ``_workspace/domain_consult/cycle376_market_unit.md`` §6.3·§7.3·§10.

순수 판정(``classify``·``normalize_mode``)은 표준 라이브러리만 쓴다.
``compute_snapshot`` 만 DB(``stock_master_daily.get_recent_daily``)와 휴장일
판정(``trading_calendar.previous_trading_day``)을 함수 안 지연 import 로 부른다
— 테스트가 그 두 이름을 모듈 속성으로 monkeypatch 하는 seam 이다.

모든 시장 유닛 마커는 이 모듈의 ``logger``(``"src.engine.market_unit"``) 하나로
나간다 — 호출자(``StrategyBase`` 의 헬퍼들)가 이 로거 객체를 직접 써서 로그를
남기고, cap(1회/일 등) 판정은 호출자(전략 인스턴스별)가 한다.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# ── 상수 (leaf 한 곳에만 — AST A02) ─────────────────────────────────────────
SOURCE_TICKER = "069500"          # KODEX 200
MA_WINDOW = 60
SLOPE_LOOKBACK = 20
MIN_ROWS = MA_WINDOW + SLOPE_LOOKBACK          # 80
FETCH_ROWS = 120
# market_regime.ETF_STALE_MAX_CALENDAR_DAYS 와 같은 값 — 휴장일 모를 때 폴백.
STALE_FALLBACK_MAX_CALENDAR_DAYS = 10

MULTIPLIERS: "MappingProxyType[str, float]" = MappingProxyType({
    "up_rising": 1.0,
    "up_falling": 0.75,
    "down_rising": 0.5,
    "down_falling": 0.0,
})

MODE_KEY = "market_unit_mode"
MODES = ("off", "shadow", "enforce")


def normalize_mode(raw: Any) -> "tuple[str, bool]":
    """모드 값 정규화. 부재(``None``) = ``("off", True)``. 오타·비문자열 = ``("off", False)``."""
    if raw is None:
        return "off", True
    if not isinstance(raw, str):
        return "off", False
    val = raw.strip().lower()
    if val in MODES:
        return val, True
    return "off", False


@dataclass(frozen=True)
class Classification:
    """§1.2 판정 결과 한 칸."""

    state: str
    m: float
    above: bool
    rising: bool
    close: float
    sma60: float
    sma60_prev: float


def _to_number(v: Any) -> "Decimal | None":
    """종가 값을 양의 유한 ``Decimal`` 로. 결측·0·음수·비유한·비수치는 ``None``."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, Decimal):
        d = v
    elif isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError):
            return None
    else:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(f):
            return None
        try:
            d = Decimal(str(f))
        except InvalidOperation:
            return None
    if not d.is_finite() or d <= 0:
        return None
    return d


def classify(closes: "Sequence[Any]") -> "tuple[Classification | None, str]":
    """§1.2 판정 — 마지막 80개 종가(오름차순 입력)만 본다.

    reason ∈ ``ok`` · ``rows_short``(< 80행) · ``bad_close``(창 안 결측/비수치/
    비유한/0 이하). 동률은 약한 쪽(엄격 부등호) — ``above``/``rising`` 둘 다
    ``==`` 이면 False.
    """
    if len(closes) < MIN_ROWS:
        return None, "rows_short"
    window = list(closes[-MIN_ROWS:])
    values: "list[Decimal]" = []
    for raw in window:
        num = _to_number(raw)
        if num is None:
            return None, "bad_close"
        values.append(num)

    sum60 = sum(values[SLOPE_LOOKBACK:])          # values[20:80] — SMA60(D-1) × 60
    sum60_prev = sum(values[:MA_WINDOW])          # values[0:60] — SMA60(D-21) × 60
    last = values[-1]

    above = (last * MA_WINDOW) > sum60
    rising = sum60 > sum60_prev

    if above and rising:
        state = "up_rising"
    elif above and not rising:
        state = "up_falling"
    elif not above and rising:
        state = "down_rising"
    else:
        state = "down_falling"
    m = MULTIPLIERS[state]

    classification = Classification(
        state=state, m=m, above=bool(above), rising=bool(rising),
        close=float(last), sma60=float(sum60) / MA_WINDOW,
        sma60_prev=float(sum60_prev) / MA_WINDOW,
    )
    return classification, "ok"


@dataclass(frozen=True)
class Snapshot:
    """전략 객체가 거래일별로 들고 있는 그날의 시장 유닛 판정 결과."""

    as_of: date
    preview: bool
    ok: bool
    state: str
    m: float
    reason: str
    bar_date: "date | None"
    expected_head: "date | None"
    rows: int
    close: "float | None"
    sma60: "float | None"
    sma60_prev: "float | None"
    above: "bool | None"
    rising: "bool | None"


def _unavailable(
    as_of_date: date, preview: bool, *, reason: str, rows: int,
    bar_date: "date | None", expected_head: "date | None",
) -> Snapshot:
    return Snapshot(
        as_of=as_of_date, preview=preview, ok=False, state="unavailable", m=1.0,
        reason=reason, bar_date=bar_date, expected_head=expected_head, rows=rows,
        close=None, sma60=None, sma60_prev=None, above=None, rising=None,
    )


def _parse_bas_dd(raw: Any) -> "date | None":
    """``bas_dd`` 파싱 — ``date``/``datetime``/ISO 문자열 수용. 실패는 ``None``(버린다)."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _is_stale(head: date, expected_head: "date | None", as_of_date: date) -> bool:
    if expected_head is not None:
        return head < expected_head
    return (as_of_date - head).days > STALE_FALLBACK_MAX_CALENDAR_DAYS


async def compute_snapshot(as_of_date: date, *, preview: bool) -> Snapshot:
    """§1·§2 — 그 거래일의 시장 유닛 스냅샷. never-raise(실패 → m=1.0).

    seam(함수 안 지연 import, 호출 시점 모듈 속성) = ``src.db.stock_master_daily
    .get_recent_daily`` · ``src.engine.trading_calendar.previous_trading_day``.
    판정 순서 = ① 행 수 → ② 신선도 → ③ 종가 품질(첫 실패에서 멈춘다).
    """
    try:
        import src.db.stock_master_daily as _smd

        rows = await _smd.get_recent_daily(SOURCE_TICKER, FETCH_ROWS)
    except Exception:
        return _unavailable(
            as_of_date, preview, reason="exception", rows=0,
            bar_date=None, expected_head=None,
        )

    try:
        filtered: "list[tuple[date, Any]]" = []
        for row in rows or []:
            bd = _parse_bas_dd(row.get("bas_dd"))
            if bd is None or bd >= as_of_date:
                continue
            filtered.append((bd, row.get("close_price")))
        filtered.sort(key=lambda item: item[0])
        rows_count = len(filtered)

        if rows_count < MIN_ROWS:
            return _unavailable(
                as_of_date, preview, reason="rows_short", rows=rows_count,
                bar_date=None, expected_head=None,
            )

        head = filtered[-1][0]

        import src.engine.trading_calendar as _tc

        expected_head = await _tc.previous_trading_day(as_of_date)

        if _is_stale(head, expected_head, as_of_date):
            return _unavailable(
                as_of_date, preview, reason="stale_head", rows=rows_count,
                bar_date=head, expected_head=expected_head,
            )

        window = filtered[-MIN_ROWS:]
        classification, reason = classify([c for _, c in window])
        if classification is None or reason != "ok":
            return _unavailable(
                as_of_date, preview, reason=reason, rows=rows_count,
                bar_date=head, expected_head=expected_head,
            )

        return Snapshot(
            as_of=as_of_date, preview=preview, ok=True, state=classification.state,
            m=classification.m, reason="ok", bar_date=head, expected_head=expected_head,
            rows=rows_count, close=classification.close, sma60=classification.sma60,
            sma60_prev=classification.sma60_prev, above=classification.above,
            rising=classification.rising,
        )
    except Exception:
        return _unavailable(
            as_of_date, preview, reason="exception", rows=0,
            bar_date=None, expected_head=None,
        )
