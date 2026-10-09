"""시장 등락 통계 — 순수 leaf (cycle416).

명세: `_workspace/red/cycle416/breadth_spec.md` §2 · §3 · §4 · §5.1 · §7.1 · §7.2
계약: `_workspace/red/cycle416/breadth_contract.md` 「1. leaf」

이 모듈은 **순수 함수 모음**이다 — `await`·`async def`·입출력·`asyncio`·`logging`·`time`
(표준 라이브러리 `time` 모듈) import 가 없고, 벽시계(`.now()`/`.today()`/`.utcnow()`/
`.monotonic()`) 를 직접 읽지 않는다. 오늘·지금은 전부 호출자(라우트)가 인자로 건넨다.
`G-416-1`(`tests/unit/ast/test_cycle416_ast_market_breadth.py`)이 이 계약을 정적으로 잰다.

이 모듈은 매매 엔진·전략에서 import 하지 않는다 — 소비처는 `src/routes/market_breadth.py`
하나뿐이다(`G-416-5`). 관찰 전용(매크로 화면) 통계라 매매 행위에 영향을 주지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# 상수 (명세 §5.1)
# ─────────────────────────────────────────────────────────────────────────────

_KST = timezone(timedelta(hours=9))

#: 2023-01-25 시행 KRX 호가가격단위표(코스피·코스닥 공통) — (이 가격 미만, 호가단위) 오름차순.
#: 이 표를 넘는 가격은 호가단위 1,000 으로 본다(`tick_size` 의 fallback).
KRX_TICK_TABLE_20230125: tuple[tuple[int, int], ...] = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
)

#: 가격제한폭 — 기준가 대비 ±30%(코스피·코스닥 공통, 2015-06-15 시행).
PRICE_LIMIT_PCT = 30

#: 20일 ADR(등락비율) 업계 통상 기준선 — 판정 문구는 어디에도 쓰지 않는다(명세 §4.2·§1).
ADR_REFERENCE: dict[str, int] = {"oversold": 75, "overheated": 120}

DEFAULT_DAYS = 20
MIN_DAYS = 1
MAX_DAYS = 60

#: 날짜 창을 거슬러 보는 최소 달력일 한도(명세 §2.1 `L = max(40, 2 × days)`).
MIN_LOOKBACK_CALENDAR_DAYS = 40

#: KRX 가 「다음 날 08:00 게시」 를 안내하는 데 2시간 여유를 더한 미게시 판정 시각(명세 §2.2).
PUBLISH_PENDING_CUTOFF = time(10, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 숫자 읽기 (명세 §3.1)
# ─────────────────────────────────────────────────────────────────────────────

def parse_krx_int(v: object) -> int | None:
    """KRX 응답의 숫자 문자열을 정수로 읽는다.

    `None`·`""`·`"-"`·공백만 있는 값 → `None`. 그 밖에는 앞뒤 공백 제거 → 쉼표 제거 →
    `Decimal` 변환 → 정수가 아니면(`"12.5"`) `None`, 읽을 수 없으면(`"abc"`) `None`.
    """
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "-"):
        return None
    s = s.replace(",", "")
    try:
        dec = Decimal(s)
    except InvalidOperation:
        return None
    if dec != dec.to_integral_value():
        return None
    return int(dec)


def _read_decimal(v: object) -> Decimal | None:
    """`FLUC_RT` 같은 소수 문자열을 읽는다 — 정수 여부는 가리지 않는다(부호 교차확인용)."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _sign(x: Decimal | int) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 호가단위 · 가격제한폭 (명세 §3.3)
# ─────────────────────────────────────────────────────────────────────────────

def tick_size(price: int) -> int:
    """2023-01-25 호가가격단위 — `price` 가 속한 가격대의 호가단위."""
    for bound, tick in KRX_TICK_TABLE_20230125:
        if price < bound:
            return tick
    return 1_000


def price_limits(base: int) -> tuple[int, int]:
    """기준가 `base` 의 (상한가, 하한가) — 정의 (가′)(명세 §3.3).

    제한폭 `w` 는 기준가 30% 를 기준가 호가단위로 절사한다. 상한가는 `base + w` 를
    **그 가격대의 호가단위로 한 번 더 절사**한다(위쪽 호가대로 올라가면 단위가 커진다).
    하한가는 `base - w` 그대로 — 추가 절사가 없다(명세 §3.3 「왜 상한과 하한의 절사가
    다른가」, 보관소 실측 659일로 확정).
    """
    t = tick_size(base)
    w = ((base * PRICE_LIMIT_PCT) // 100) // t * t
    upper_raw = base + w
    tu = tick_size(upper_raw)
    upper = upper_raw // tu * tu
    lower = base - w
    return upper, lower


# ─────────────────────────────────────────────────────────────────────────────
# 행 분류 (명세 §3.2 · §3.3 · §3.4)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RowClass:
    """`classify_row` 의 반환값 — 종목 한 줄의 판정."""

    kind: str  # "unparsed" | "no_trade" | "up" | "down" | "flat"
    limit_up: bool = False
    limit_down: bool = False
    out_of_band: bool = False
    sign_mismatch: bool = False


def classify_row(row: dict) -> RowClass:
    """KRX 일별 매매정보 행 한 줄을 분류한다 — 순서는 명세 §3.2."""
    close = parse_krx_int(row.get("TDD_CLSPRC"))
    cmp = parse_krx_int(row.get("CMPPREVDD_PRC"))
    vol = parse_krx_int(row.get("ACC_TRDVOL"))

    if close is None or close <= 0 or cmp is None or vol is None or vol < 0:
        return RowClass(kind="unparsed")

    if vol == 0:
        return RowClass(kind="no_trade")

    if cmp > 0:
        kind = "up"
    elif cmp < 0:
        kind = "down"
    else:
        kind = "flat"

    limit_up = False
    limit_down = False
    out_of_band = False

    base = close - cmp
    high = parse_krx_int(row.get("TDD_HGPRC"))
    low = parse_krx_int(row.get("TDD_LWPRC"))

    if base > 0 and high is not None and high > 0 and low is not None and low > 0:
        upper, lower = price_limits(base)
        in_band = low >= lower and high <= upper
        if not in_band:
            out_of_band = True
        elif kind == "up" and close == upper:
            limit_up = True
        elif kind == "down" and close == lower:
            limit_down = True

    fluc = _read_decimal(row.get("FLUC_RT"))
    sign_mismatch = fluc is not None and _sign(cmp) != _sign(fluc)

    return RowClass(
        kind=kind, limit_up=limit_up, limit_down=limit_down,
        out_of_band=out_of_band, sign_mismatch=sign_mismatch,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 집계 (명세 §4)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DayStats:
    """하루·시장 하나의 집계(명세 §4.1). `sign_mismatch` 는 응답에 싣지 않는다(로그 전용)."""

    rows: int
    traded: int
    up: int
    down: int
    flat: int
    limit_up: int
    limit_down: int
    no_trade: int
    out_of_band: int
    unparsed: int
    up_ratio: float | None
    sign_mismatch: int = 0


@dataclass(frozen=True)
class SummaryStats:
    """여러 날의 요약(명세 §4.2)."""

    n_days: int
    up: int
    down: int
    flat: int
    limit_up: int
    limit_down: int
    no_trade: int
    up_ratio: float | None
    adr: float | None


def aggregate_rows(rows: list[dict]) -> DayStats:
    """하루치 KRX 원자료 행을 `DayStats` 로 집계한다(명세 §4.1)."""
    up = down = flat = limit_up = limit_down = no_trade = 0
    out_of_band = unparsed = sign_mismatch = 0

    for row in rows:
        rc = classify_row(row)
        if rc.kind == "unparsed":
            unparsed += 1
            continue
        if rc.kind == "no_trade":
            no_trade += 1
        elif rc.kind == "up":
            up += 1
        elif rc.kind == "down":
            down += 1
        elif rc.kind == "flat":
            flat += 1
        if rc.limit_up:
            limit_up += 1
        if rc.limit_down:
            limit_down += 1
        if rc.out_of_band:
            out_of_band += 1
        if rc.sign_mismatch:
            sign_mismatch += 1

    traded = up + down + flat
    rows_count = traded + no_trade
    up_ratio = round(up / traded, 4) if traded > 0 else None
    return DayStats(
        rows=rows_count, traded=traded, up=up, down=down, flat=flat,
        limit_up=limit_up, limit_down=limit_down, no_trade=no_trade,
        out_of_band=out_of_band, unparsed=unparsed, up_ratio=up_ratio,
        sign_mismatch=sign_mismatch,
    )


def merge_stats(a: DayStats, b: DayStats) -> DayStats:
    """두 `DayStats` 의 합계 — 정수 키는 더하고 `up_ratio` 는 합계 숫자로 재계산(평균 아님)."""
    up = a.up + b.up
    down = a.down + b.down
    flat = a.flat + b.flat
    limit_up = a.limit_up + b.limit_up
    limit_down = a.limit_down + b.limit_down
    no_trade = a.no_trade + b.no_trade
    out_of_band = a.out_of_band + b.out_of_band
    unparsed = a.unparsed + b.unparsed
    sign_mismatch = a.sign_mismatch + b.sign_mismatch
    traded = up + down + flat
    rows = traded + no_trade
    up_ratio = round(up / traded, 4) if traded > 0 else None
    return DayStats(
        rows=rows, traded=traded, up=up, down=down, flat=flat,
        limit_up=limit_up, limit_down=limit_down, no_trade=no_trade,
        out_of_band=out_of_band, unparsed=unparsed, up_ratio=up_ratio,
        sign_mismatch=sign_mismatch,
    )


def summarize(days: list[DayStats]) -> SummaryStats:
    """여러 날의 `DayStats` 를 요약한다(명세 §4.2). 빈 목록 → `n_days=0` · `up_ratio`/`adr` 둘 다 `None`."""
    n_days = len(days)
    up = sum(d.up for d in days)
    down = sum(d.down for d in days)
    flat = sum(d.flat for d in days)
    limit_up = sum(d.limit_up for d in days)
    limit_down = sum(d.limit_down for d in days)
    no_trade = sum(d.no_trade for d in days)
    traded = up + down + flat
    up_ratio = round(up / traded, 4) if traded > 0 else None
    adr = round(up / down * 100, 1) if down > 0 else None
    return SummaryStats(
        n_days=n_days, up=up, down=down, flat=flat, limit_up=limit_up,
        limit_down=limit_down, no_trade=no_trade, up_ratio=up_ratio, adr=adr,
    )


def stats_to_dict(stats: DayStats | SummaryStats) -> dict:
    """응답 직렬화 — `DayStats` 11키(`sign_mismatch` 제외) · `SummaryStats` 9키(명세 §5.4)."""
    if isinstance(stats, SummaryStats):
        return {
            "n_days": stats.n_days, "up": stats.up, "down": stats.down, "flat": stats.flat,
            "limit_up": stats.limit_up, "limit_down": stats.limit_down,
            "no_trade": stats.no_trade, "up_ratio": stats.up_ratio, "adr": stats.adr,
        }
    return {
        "rows": stats.rows, "traded": stats.traded, "up": stats.up, "down": stats.down,
        "flat": stats.flat, "limit_up": stats.limit_up, "limit_down": stats.limit_down,
        "no_trade": stats.no_trade, "out_of_band": stats.out_of_band,
        "unparsed": stats.unparsed, "up_ratio": stats.up_ratio,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 날짜 창 (명세 §2.1 · §2.2)
# ─────────────────────────────────────────────────────────────────────────────

def lookback_calendar_days(days: int) -> int:
    """거슬러 보는 한도(달력일) — `max(40, 2 × days)`."""
    return max(MIN_LOOKBACK_CALENDAR_DAYS, 2 * days)


def candidate_weekdays(today: date, days: int) -> list[date]:
    """`today` 를 뺀 평일 후보(최신 먼저), 한도일(`today - L`) 포함(명세 §2.1)."""
    limit = lookback_calendar_days(days)
    out: list[date] = []
    for k in range(1, limit + 1):
        d = today - timedelta(days=k)
        if d.weekday() < 5:
            out.append(d)
    return out


def next_weekday(d: date) -> date:
    """`d` 다음의 첫 평일(토·일 → 다음 월요일)."""
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:
        nd += timedelta(days=1)
    return nd


def is_publish_pending(d: date, d1: date, now: datetime) -> bool:
    """`d == d1` 이고 `now` 가 아직 다음 평일 10:00 KST 전이면 「아직 미게시」(명세 §2.2).

    `now` 가 KST 가 아닌 다른 시간대(예: UTC)로 와도 타임존이 있는 `datetime` 끼리의
    비교는 같은 시점을 가리키므로 결과가 바뀌지 않는다.
    """
    if d != d1:
        return False
    nw = next_weekday(d1)
    cutoff = datetime.combine(nw, PUBLISH_PENDING_CUTOFF, tzinfo=_KST)
    return now < cutoff


class DayStatus(str, Enum):
    """후보 날짜 하나의 판정(명세 §2.1 표)."""

    TRADING = "TRADING"
    EMPTY = "EMPTY"
    MISSING = "MISSING"


def classify_day(kospi: DayStats | None, kosdaq: DayStats | None) -> DayStatus:
    """두 시장의 그날 집계로 `TRADING`/`EMPTY`/`MISSING` 을 가른다(명세 §2.1 표).

    `None` = 그 시장 호출이 실패했다는 뜻이고(휴장이 아니다) 무조건 `MISSING`.
    """
    if kospi is None or kosdaq is None:
        return DayStatus.MISSING
    if kospi.rows > 0 and kosdaq.rows > 0:
        return DayStatus.TRADING
    if kospi.rows == 0 and kosdaq.rows == 0:
        return DayStatus.EMPTY
    return DayStatus.MISSING
