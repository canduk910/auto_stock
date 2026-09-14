"""cycle294 §1 — 시세 채널 **시각축** 판정 leaf (8영역 밖 · 순수 · never-raise).

3단계의 종착지는 통합 채널의 **소멸**이다. 09-15 07:45 부팅부터 두 채널만 쓴다
— 프리장은 NXT 전용, 정규장+애프터는 KRX 전용. 그 배치는 아래와 같고 전환은
하루 **1회**뿐이다.

    프리장(N1 구간)        → NXT 전용   (그 시각 NXT 만 연속 체결을 싣는다)
    전환 창                → 주문 0건 · cycle241 시장 침묵 ⇒ 전환 비용 ≈ 0
    정규장 + 애프터마켓    → KRX 전용   (연속)
    🔴 NXT 단독 연속 구간  → **보유(HIGH)만** NXT 전용 (아래 §CRITICAL-1)

## 🔴 적대 검증 CRITICAL-1 시정 — "KRX 창" 은 KRX 가 연속일 때만 참이다

착지 직후 검증이 찾은 결함: `krx_continuous_end` 는 `max(end)` 라 **09-15 기준
20:00** 이고, 그 하나로 09:00~20:00 을 KRX 단일 구간으로 묶으면 표가 말하는 사실과
어긋난다. 실측 표(`get_market_table(2026-09-15)`):

    KRX  REGULAR            09:00~15:20  continuous
    KRX  CLOSE_AUCTION      15:20~15:30  single_auction     ← 연속 아님
    KRX  AFTER_CLOSE_FIXED  15:30~16:00  fixed_price        ← 연속 아님
    KRX  AFTER_MARKET       16:00~20:00  continuous
    NXT  AFTER_MARKET       15:40~20:00  continuous         ← 🔴 15:40~16:00 은 NXT 뿐

⇒ **15:40~16:00(20분) 은 NXT 에만 연속 체결이 있다.** 그 20분을 KRX 채널로 덮으면
`nxt_true` 보유 종목의 손절 트리거가 매일 20분씩 사라진다 — 오늘은 통합 채널이 그
체결을 싣고 있으므로(부록 A: 09-08 15:45 필옵틱스 실체결) **INV-1 위반**이다.

사용자 결정("전환은 하루 1회")의 근거는 「cycle287 이 애프터 주문을 KRX 로 보내므로
그 구간에 KRX 가격을 보는 것이 정합(평가 가격 = 체결 가격)」이었다. 그 근거는
**16:00~20:00 에만 참**이다 — `order_engine._route_exchange_by_clock("SOR", side="sell")`
을 실행해 보면 15:45·15:55 는 `("SOR", "krx_unsupported_keep")`, 16:05·19:00 은
`("KRX", "krx_by_clock")` 이다. 즉 15:40~16:00 의 매도는 **NXT 로 나간다** ⇒ 같은
원칙을 적용하면 그 구간의 평가 가격도 NXT 여야 한다. 이 시정은 사용자 결정과
충돌하지 않고 그 결정의 원칙을 결정이 다루지 않은 구간에 적용한 것이다.

범위는 **HIGH(보유·익일청산)로 한정**한다 — 그 구간에 필요한 것은 손절 커버리지
하나이고, LOW 후보 ~130종목을 하루 두 번 왕복시키면 KIS 공지 「비정상 케이스 2:
무한 등록/해제」에 정면으로 걸린다. HIGH 는 실측 ~12종목이고 make-before-break 라
커버리지 공백이 0 이다. 킬스위치 = `tick_channel_gap_hold_enabled=false`.

09-14 16:39~16:41 라이브 실측 — `000815`(nxt_false)·`005385`(nxt_false)·
`000660`(nxt_true) 전부 KRX 전용 채널에서 KRX 애프터마켓 체결을 받았다. 즉 그
채널은 **종목 속성과 무관하게** 정규장 개장부터 연속 체결 종료까지를 덮는다.

## 🔴 시각 리터럴 0건 (§1-C · G-294-1)

경계 셋은 전부 `market_state.get_market_table(on_date)` **공개 API** 파생이다.

    nxt_pre_end         = NXT · PRE_MARKET 행의 end        (N1)
    krx_regular_open    = KRX · REGULAR 행의 start          (K3)
    krx_continuous_end  = KRX · match_kind=="continuous" 의 end 최대값 (K3·K6)

전환 시각은 리터럴이 아니라 **파라미터**다 —
`switch_at = clamp(nxt_pre_end + offset, nxt_pre_end, krx_regular_open)`.

⚠️ `krx_continuous_end` 를 `phase` 로 고르지 않는 이유 — 그러면 REGULAR 와
AFTER_MARKET 을 **둘 다 열거**해야 하고, KRX 가 연속 구간을 하나 더 신설하는
날 그 열거가 조용히 낡는다. `match_kind` 는 "실시간 접속매매인가" 라는 성질
이라 신설 구간을 자동으로 흡수한다. 시간외 단일가(K7)는 `periodic_auction`
이라 이 질의에 애초에 걸리지 않는다 — `effective_to` 해석과 **이중으로** 막힌다.

## 🔴 통합 채널을 반환하지 않는다 (절대 규칙 1)

이 모듈은 전용 2채널만 다룬다. 판정 실패의 폴백도 **KRX 전용**이다(§3-B L1):
① 09-14 실측이 그 채널의 종목 속성 무관 수신을 확정했고 ② 하루 구독 수명의
92% 가 KRX 창이며 ③ 셋 중 **모의(VTS) 지원은 그것뿐**이다. 어떤 실패도
"구독을 안 한다" 로 가지 않는다(P0-1 재현 방향 · 금기 2).

킬스위치 `off` 의 통합 반환은 `scanner.tick_tr_id_for` 안에 있다 — 여기가 아니다.
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime as _datetime, timedelta

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure

logger = logging.getLogger(__name__)

#: 전환 offset 기본값 — 프리장 종료 뒤 이만큼 지나서 옮긴다(결정 카드 D-3 (가)).
#: 전환 창이 120초 루프 2~3사이클을 담고 정규장 개장 전에 반드시 끝나는 폭이다.
DEFAULT_SWITCH_OFFSET_SECS = 300

REASON_PRE_WINDOW = "pre_window"
REASON_KRX_WINDOW = "krx_window"
#: 🔴 CRITICAL-1 — KRX 가 연속이 아니고 NXT 만 연속인 구간(09-15 = 15:40~16:00).
REASON_NXT_GAP_WINDOW = "nxt_gap_window"
REASON_POST_CLOSE = "post_close"
REASON_DAY_REVERTED = "day_reverted"
REASON_TABLE_INCOMPLETE = "table_incomplete"
REASON_CLOCK_ERROR = "clock_error"

#: §5-B — 자동 원복 래치. 그날 나머지 시간 동안 **프리 창 규칙**을 쓴다
#: (단순 "전원 NXT" 가 아니다 — 속성축을 존중해야 원복이 새 blind 를 안 만든다).
_revert_for: _date | None = None
#: 래치를 심은 **벽시계** KST 날짜. 날짜가 넘어가면 스스로 비운다
#: (`scanner._sync_channel_day` 와 같은 자기 리셋 관례).
_revert_wall_day: str = ""

#: 전용 2채널 상수 캐시 — `scanner` 와의 순환 import 를 피해 지연 바인딩한다.
_CHANNELS: tuple[str, str] | None = None

#: 🔴 적대 검증 MEDIUM-4(부팅) / LOW-1(매수축) 시정 — 표 파생값 날짜 메모.
#: `risk.on_tick` 이 코호트 종목마다 `note_pre_window_frame` 을 부르고 그것이
#: `_windows` + `switch_at` 을 각각 돌려 `get_market_table`(13행 × 28 주문유형
#: 재구성, 실측 ≈24µs)을 **틱마다 두 번** 만들었다. 표는 날짜의 함수이므로
#: 날짜 키로 메모하면 그 비용이 하루 1회가 된다. 테스트 격리는
#: `reset_state_for_test()` 가 비운다(`MARKET_TABLE` 은 sha 핀된 모듈 상수다).
_WINDOW_MEMO: dict = {}
_SWITCH_AT_MEMO: dict = {}
_GAP_MEMO: dict = {}

#: 구간 길이 비교용 고정 기준일 — 날짜 의미 없음(시각 차만 쓴다).
_EPOCH_DAY = _date(2000, 1, 1)


def _channels() -> tuple[str, str]:
    """`(KRX 전용, NXT 전용)` — 값의 정본은 `scanner` 다(두 번째 정의 금지)."""
    global _CHANNELS
    if _CHANNELS is None:
        from src.engine.scanner import TICK_TR_ID_KRX, TICK_TR_ID_NXT

        _CHANNELS = (TICK_TR_ID_KRX, TICK_TR_ID_NXT)
    return _CHANNELS


def _kst_today() -> str:
    try:
        from src.engine.scanner import KST_TZ

        return _datetime.now(KST_TZ).date().isoformat()
    except Exception:  # pragma: no cover — never-raise
        return ""


def _windows(on_date: _date | None = None):
    """`(krx_regular_open, nxt_pre_end, krx_continuous_end)` — 없으면 `None`.

    🔴 `MARKET_TABLE` 을 **직접 순회하지 않는다.** 애프터마켓 행은
    `effective_from` 이, 시간외 단일가 행은 `effective_to` 가 붙어 있고 그
    해석기(`_is_effective`)는 private 이다. 공개 API 가 이미 그 일을 한다 —
    "날짜는 이 표의 계약이다"(`get_market_table` docstring).
    """
    memo_key = on_date
    cached = _WINDOW_MEMO.get(memo_key)
    if cached is not None:
        return cached
    try:
        from src.engine.market_state import MarketPhase, get_market_table

        rows = get_market_table(on_date)
    except Exception:
        return None, None, None
    try:
        krx_regular_open = min(
            (r.start for r in rows
             if r.market == "KRX" and r.phase is MarketPhase.REGULAR),
            default=None,
        )
        nxt_pre_end = max(
            (r.end for r in rows
             if r.market == "NXT" and r.phase is MarketPhase.PRE_MARKET),
            default=None,
        )
        krx_continuous_end = max(
            (r.end for r in rows
             if r.market == "KRX" and r.match_kind == "continuous"),
            default=None,
        )
    except Exception:
        return None, None, None
    result = (krx_regular_open, nxt_pre_end, krx_continuous_end)
    _WINDOW_MEMO[memo_key] = result
    return result


def _spans(rows, market: str) -> list[tuple]:
    """그 시장의 **연속 체결**(`match_kind=="continuous"`) 구간 목록."""
    return sorted(
        (r.start, r.end) for r in rows
        if r.market == market and r.match_kind == "continuous"
    )


def _subtract(span, cuts) -> list[tuple]:
    """`span` 에서 `cuts` 구간들을 뺀 나머지(열린 오른쪽 끝 기준)."""
    segments = [span]
    for c0, c1 in cuts:
        rest: list[tuple] = []
        for s0, s1 in segments:
            if c1 <= s0 or c0 >= s1:
                rest.append((s0, s1))
                continue
            if c0 > s0:
                rest.append((s0, c0))
            if c1 < s1:
                rest.append((c1, s1))
        segments = rest
    return [(a, b) for a, b in segments if a < b]


def nxt_only_continuous_window(on_date: _date | None = None):
    """🔴 CRITICAL-1 — 정규장 개장 **이후** KRX 는 연속이 아닌데 NXT 만 연속인 구간.

    `(start, end)` 또는 `(None, None)`. 09-15 기준 **15:40~16:00**(NXT N6 애프터가
    15:40 에 열리고 KRX K6 애프터는 16:00 에 열린다). 09-13 이전 날짜에서는
    `effective_from=2026-09-14` 인 K6 가 표에 없어 15:40~20:00 전체가 이 구간이다
    — 그 날짜에도 그것이 **사실**이므로 특례를 두지 않는다.

    ⚠️ 시각 리터럴 0건 — 두 시장의 연속 구간 집합을 빼기만 한다. KRX 가 연속
    구간을 하나 더 신설하거나 NXT 애프터 시각이 또 움직여도 이 질의는 낡지 않는다.
    여러 조각이 나오면 **가장 긴 조각** 하나를 고른다(현실적으로 1개다).
    """
    memo_key = on_date
    cached = _GAP_MEMO.get(memo_key)
    if cached is not None:
        return cached
    try:
        from src.engine.market_state import get_market_table

        rows = get_market_table(on_date)
    except Exception:
        return None, None
    try:
        krx_regular_open, _pre_end, _krx_end = _windows(on_date)
        if krx_regular_open is None:
            return None, None
        krx_spans = _spans(rows, "KRX")
        pieces: list[tuple] = []
        for span in _spans(rows, "NXT"):
            pieces.extend(_subtract(span, krx_spans))
        pieces = [(a, b) for a, b in pieces if a >= krx_regular_open]
        if not pieces:
            result = (None, None)
        else:
            best = max(
                pieces,
                key=lambda ab: (
                    _datetime.combine(_EPOCH_DAY, ab[1])
                    - _datetime.combine(_EPOCH_DAY, ab[0])
                ),
            )
            result = best
    except Exception:
        return None, None
    _GAP_MEMO[memo_key] = result
    return result


def gap_hold_enabled() -> bool:
    """NXT 단독 연속 구간을 HIGH 가 따라가는가 — 킬스위치(기본 켜짐).

    `tick_channel_mode` 를 **지연 참조**한다(그 모듈이 이 모듈을 import 하므로).
    조회 실패는 **켜짐**으로 흡수한다 — 꺼짐이 기본이면 INV-1 위반이 기본이 된다.
    """
    try:
        from src.engine import tick_channel_mode

        return bool(tick_channel_mode.gap_hold_enabled())
    except Exception:  # pragma: no cover — never-raise
        return True


def switch_at(on_date: _date | None = None, *, offset_secs: int | None = None):
    """전환 시각 = `clamp(nxt_pre_end + offset, nxt_pre_end, krx_regular_open)`.

    표가 바뀌어 프리장 종료가 정규장 개장 이후가 되면 전환 창이 **빈 구간**이
    되어 전환이 0건이다 — 예외를 던지지 않는다(fail-safe).
    """
    target = on_date if on_date is not None else _wall_date()
    if target is None:
        return None
    memo_key = (target, offset_secs)
    cached = _SWITCH_AT_MEMO.get(memo_key)
    if cached is not None:
        return cached
    krx_regular_open, nxt_pre_end, _end = _windows(target)
    if krx_regular_open is None:
        return None
    if nxt_pre_end is None or nxt_pre_end >= krx_regular_open:
        _SWITCH_AT_MEMO[memo_key] = krx_regular_open
        return krx_regular_open
    base = _datetime.combine(target, nxt_pre_end)
    span = (_datetime.combine(target, krx_regular_open) - base).total_seconds()
    try:
        wanted = int(offset_secs) if offset_secs is not None else DEFAULT_SWITCH_OFFSET_SECS
    except (TypeError, ValueError):
        wanted = DEFAULT_SWITCH_OFFSET_SECS
    clamped = max(0, min(wanted, int(span)))
    boundary = (base + timedelta(seconds=clamped)).time()
    _SWITCH_AT_MEMO[memo_key] = boundary
    return boundary


def _wall_date() -> _date | None:
    try:
        from src.engine.scanner import KST_TZ

        return _datetime.now(KST_TZ).date()
    except Exception:  # pragma: no cover — never-raise
        return None


def clock_channel(
    now, *, offset_secs: int | None = None, priority: str = "LOW",
) -> tuple[str, str]:
    """`(tr_id, reason)` — 🔴 통합 채널을 **절대 반환하지 않는다**(절대 규칙 1).

    tz-naive `now` 도 예외 없이 전용 채널로 떨어진다(§3-C) — 여기서 던지면
    `subscribe_filtered_stocks` 가 그 사이클의 구독을 통째로 잃는다.

    🔴 `priority` 는 **NXT 단독 연속 구간**(CRITICAL-1) 하나에만 쓰인다. 그
    구간에서 HIGH(보유·익일청산)만 NXT 를 따라가고 LOW 후보는 KRX 에 남는다 —
    그 20분에 필요한 것은 손절 커버리지뿐이고, LOW ~130종목을 하루 두 번
    왕복시키면 KIS 공지 「비정상 케이스 2: 무한 등록/해제」에 정면으로 걸린다.
    """
    krx_only, nxt_only = _channels()
    try:
        if day_reverted(now):
            return nxt_only, REASON_DAY_REVERTED
        on_date = now.date()
        krx_regular_open, _pre_end, krx_continuous_end = _windows(on_date)
        if krx_regular_open is None or krx_continuous_end is None:
            return krx_only, REASON_TABLE_INCOMPLETE
        boundary = switch_at(on_date, offset_secs=offset_secs) or krx_regular_open
        current = now.time()
        if current < boundary:
            return nxt_only, REASON_PRE_WINDOW
        if current < krx_continuous_end:
            if in_nxt_gap(current, on_date) and str(priority).upper() == "HIGH":
                return nxt_only, REASON_NXT_GAP_WINDOW
            return krx_only, REASON_KRX_WINDOW
        # 연속 체결 종료 이후 — 구독 자체가 없는 구간이다(20:00 `unsubscribe_all`).
        return krx_only, REASON_POST_CLOSE
    except Exception:
        return krx_only, REASON_CLOCK_ERROR


def in_nxt_gap(current_time, on_date: _date | None = None) -> bool:
    """그 시각이 **NXT 단독 연속 구간** 안인가 — 킬스위치까지 함께 본다."""
    try:
        if not gap_hold_enabled():
            return False
        gap_start, gap_end = nxt_only_continuous_window(on_date)
        if gap_start is None or gap_end is None:
            return False
        return gap_start <= current_time < gap_end
    except Exception:  # pragma: no cover — never-raise
        return False


def switch_windows(on_date: _date | None = None, *, offset_secs: int | None = None):
    """그날 **전환이 허용되는 창** 목록 `[(start, end, label), …]`.

    창 밖 전환 금지(§4-A)의 근거 셋은 아침 창에서 동시에 성립한다. NXT 단독
    구간의 두 경계는 그 셋 중 ①(프레임 0)이 성립하지 않지만, 대상이 HIGH 뿐이고
    make-before-break 이라 커버리지 공백이 0 이며 이중 채널 노출은 종목당 1~5초다.
    그 비용이 "매일 20분 손절 blind"(INV-1 위반)보다 작다.

      W1 `pre_to_krx`     [switch_at, krx_regular_open)      — 프리 창 → KRX
      W2 `krx_to_nxt_gap` [gap_start, gap_end)               — HIGH 만 NXT 로
      W3 `nxt_gap_to_krx` [gap_end, gap_end + offset)        — 되돌아오기

    W3 의 폭에 새 숫자를 짓지 않는다 — 아침 창과 같은 `offset_secs` 를 쓴다.
    """
    try:
        target = on_date if on_date is not None else _wall_date()
        if target is None:
            return []
        krx_regular_open, _pre_end, krx_continuous_end = _windows(target)
        if krx_regular_open is None:
            return []
        windows: list[tuple] = []
        boundary = switch_at(target, offset_secs=offset_secs)
        if boundary is not None and boundary < krx_regular_open:
            windows.append((boundary, krx_regular_open, "pre_to_krx"))
        if gap_hold_enabled():
            gap_start, gap_end = nxt_only_continuous_window(target)
            if gap_start is not None and gap_end is not None:
                windows.append((gap_start, gap_end, "krx_to_nxt_gap"))
                span = offset_secs if offset_secs is not None else DEFAULT_SWITCH_OFFSET_SECS
                try:
                    span = max(0, int(span))
                except (TypeError, ValueError):
                    span = DEFAULT_SWITCH_OFFSET_SECS
                back = (
                    _datetime.combine(target, gap_end) + timedelta(seconds=span)
                ).time()
                if krx_continuous_end is not None and back > krx_continuous_end:
                    back = krx_continuous_end
                if back > gap_end:
                    windows.append((gap_end, back, "nxt_gap_to_krx"))
        return windows
    except Exception:  # pragma: no cover — never-raise
        return []


def active_switch_window(now, *, offset_secs: int | None = None):
    """지금이 속한 전환 창 `(start, end, label)` — 없으면 `None`."""
    try:
        current = now.time()
        for start, end, label in switch_windows(now.date(), offset_secs=offset_secs):
            if start <= current < end:
                return start, end, label
    except Exception:  # pragma: no cover — never-raise
        return None
    return None


# ── §5-B 자동 원복 래치 ─────────────────────────────────────────────────────
def set_day_revert(on_date: _date | None = None) -> None:
    """그날 나머지 시간 동안 **프리 창 규칙**으로 되돌린다.

    `on_date` 를 주면 그 영업일 기준, 생략하면 벽시계 KST 오늘이다. 어느 쪽이든
    래치는 **벽시계 날짜가 넘어가면** 스스로 풀린다 — 다음 영업일 첫 구독부터
    자연 재시도한다(§5-C: 그날 재시도는 없다).
    """
    global _revert_for, _revert_wall_day
    target = on_date if on_date is not None else _wall_date()
    # 🔴 적대 검증 MEDIUM-3 — `_kst_today()` 가 `""` 를 돌려주는 경로(`scanner`
    # import 실패 등)에서 래치를 심으면 아래 날짜 자기 리셋 조건이 **영원히 거짓**
    # 이 되어 프로세스 수명 내내 전 종목이 프리 창 규칙에 고착된다. 시계를 못
    # 읽으면 래치가 겨누는 영업일 자체를 날짜 키로 쓴다(둘 다 없으면 심지 않는다).
    today = _kst_today()
    if not today and target is not None:
        today = target.isoformat()
    if not today:
        return
    _revert_wall_day = today
    _revert_for = target


def day_reverted(now=None) -> bool:
    """오늘 자동 원복이 걸려 있는가 — 읽기 전용(벽시계 날짜 자기 리셋 제외)."""
    global _revert_for, _revert_wall_day
    try:
        today = _kst_today()
        if not today:
            wall = _wall_date()
            today = wall.isoformat() if wall is not None else ""
        if _revert_wall_day and today and _revert_wall_day != today:
            _revert_for = None
            _revert_wall_day = ""
        if _revert_for is None:
            return False
        if now is not None:
            try:
                if now.date() < _revert_for:
                    # 래치보다 **앞선** 시각의 판정은 되돌림을 보지 않는다.
                    return False
            except Exception:
                return True
        return True
    except Exception:  # pragma: no cover — never-raise
        return False


# ── §11-A 관측 ─────────────────────────────────────────────────────────────
#: `[tick_channel_clock]` 배포 카나리아 cap — 하루 1행.
_clock_config_cap: "KstDailyEmitCap[str]" = KstDailyEmitCap()
#: `[tick_channel_pre_krx_frame]` cap — 1회/(ticker)/일.
_pre_frame_cap: "KstDailyEmitCap[str]" = KstDailyEmitCap()

#: §2-D 관측 상태 — 프리 창에 프레임을 받은 무송출 코호트 종목의 (건수, 첫 시각).
_pre_frame_counts: dict[str, int] = {}
_pre_frame_first: dict[str, str] = {}
_pre_frame_day: str = ""


def emit_clock_config(now=None, *, offset_secs: int | None = None) -> None:
    """`[tick_channel_clock]` — 표 파생값 **카나리아**, 하루 1행 WARNING.

    이 한 줄이 없으면 D+1 에 "오늘 전환이 몇 시로 잡혔는지" 를 사후에 알 방법이
    없다. 경계 셋이 전부 `get_market_table` 파생이므로 표가 또 바뀌는 날(09-14 가
    두 번째다) **값이 조용히 움직이고 그것을 아무도 모른다**. 카나리아가 그 변화를
    매일 아침 한 줄로 남긴다.

    🔴 레벨이 WARNING 인 이유 = `log_metrics_collector.pattern_by_level` 이
    `{WARNING, ERROR, CRITICAL}` 만 21:30 리포트 `top_patterns` 에 넣는다. INFO 로
    두면 배포 반영 여부가 리포트에 한 글자도 안 뜬다(cycle245 `[ratio_cap_config]`
    함정 — cycle293 이 `[tick_channel_config]` 를 WARNING 으로 올린 그 이유).

    never-raise — 카나리아 실패가 구독 사이클을 끊지 않는다.
    """
    try:
        on_date = now.date() if now is not None else _wall_date()
        krx_regular_open, nxt_pre_end, krx_continuous_end = _windows(on_date)
        boundary = switch_at(on_date, offset_secs=offset_secs)
        wanted = offset_secs if offset_secs is not None else DEFAULT_SWITCH_OFFSET_SECS
        gap_start, gap_end = nxt_only_continuous_window(on_date)
        _clock_config_cap.emit_once(
            f"clock|{on_date}",
            logger.warning,
            f"[tick_channel_clock] switch_at={boundary} krx_open={krx_regular_open} "
            f"krx_end={krx_continuous_end} nxt_pre_end={nxt_pre_end} "
            f"nxt_gap={gap_start}~{gap_end} gap_hold={int(gap_hold_enabled())} "
            f"offset_secs={wanted} source=market_table",
        )
    except Exception:  # pragma: no cover — never-raise
        trace_observer_failure("[tick_channel_clock]", "-", dest_logger=logger)


def _effective_offset() -> int | None:
    """지금 실제로 쓰이는 전환 offset — 관측 창이 채널 경계와 갈리지 않게 한다."""
    try:
        from src.engine import tick_channel_mode

        return tick_channel_mode.switch_offset_secs()
    except Exception:  # pragma: no cover — never-raise
        return None


def _sync_pre_frame_day() -> None:
    """KST 날짜가 넘어가면 §2-D 관측 상태를 스스로 비운다."""
    global _pre_frame_day
    today = _kst_today()
    if today and _pre_frame_day != today:
        _pre_frame_day = today
        _pre_frame_counts.clear()
        _pre_frame_first.clear()


def note_pre_window_frame(ticker: str, now=None) -> None:
    """§2-D — 프리 창에 **무송출 코호트** 종목의 틱이 들어왔음을 센다(관측 전용).

    `H0STCNT0` 이 KRX 시가 단일가 구간에 프레임을 보내는가? **[추론, 확신 ≈80%]
    보내지 않는다** — 체결가 채널이고 단일가 구간에는 체결이 없다. 이 함수는 그
    추론을 D+1 에 실측으로 바꾼다. 행위는 **바꾸지 않는다** — 게이트를 더하는
    것은 매매 행위 변경이라 별도 승인 대상이다(§2-D).

    호출자는 코호트 판정을 이미 끝낸 자리(`risk.on_tick` 의 틱당 1회 계산)이므로
    여기서는 시각만 본다.

    🔴 적대 검증 MEDIUM-4(부팅)/LOW-1(매수축) 시정 — 종전 구현은 창 밖 판정을
    하기 **전에** `_windows` + `switch_at` 을 각각 돌려 `get_market_table` 을 틱마다
    두 번 재구성했고(실측 ≈51µs/틱), docstring 의 "창 밖이면 즉시 반환" 은 사실이
    아니었다. 지금은 두 파생값이 **날짜 키로 메모**되므로 두 번째 호출부터는 dict
    조회뿐이고, 창 밖 판정도 그 메모 위에서 끝난다. 그리고 창 경계는 실제 채널
    경계와 같은 **`tick_channel_mode.switch_offset_secs()`** 를 쓴다 — 종전에는
    기본 offset 을 써서 운영자가 offset 을 바꾸면 관측 창과 실제 창이 갈렸다.
    """
    try:
        current = now if now is not None else None
        if current is None:
            return
        on_date = current.date()
        krx_regular_open, _pre_end, _krx_end = _windows(on_date)
        if krx_regular_open is None:
            return
        boundary = switch_at(on_date, offset_secs=_effective_offset()) or krx_regular_open
        if current.time() >= boundary:
            return                          # 전환 창 이후 = 이 관측의 대상이 아니다
        _sync_pre_frame_day()
        key = str(ticker)
        _pre_frame_counts[key] = _pre_frame_counts.get(key, 0) + 1
        _pre_frame_first.setdefault(key, current.time().isoformat())
    except Exception:  # pragma: no cover — never-raise
        return


def emit_pre_window_frame_summary(now=None) -> None:
    """`[tick_channel_pre_krx_frame] ticker= n= first_at=` — 1회/(ticker)/일 INFO.

    **프리 창이 끝난 뒤에만** 발화한다. 창 안에서 첫 프레임에 바로 찍으면 `n=1`
    밖에 못 적어 "얼마나" 를 영영 모른다 — 창이 닫힌 뒤에 찍으면 그날의 완전한
    건수가 들어간다. 호출자는 5분 `_scan_loop`(`TIME_SCAN_START`= 정규장 개장 뒤)
    이라 첫 호출이 이미 창 밖이다.

    기대값은 **0행**이다. 한 행이라도 뜨면 §0 의 추론이 틀린 것이고, 그때는
    게이트 추가 여부를 결정 카드로 올린다(매매 행위 변경 = 승인 대상).
    """
    try:
        current = now if now is not None else None
        if current is None:
            return
        on_date = current.date()
        krx_regular_open, _pre_end, _krx_end = _windows(on_date)
        if krx_regular_open is None:
            return
        boundary = switch_at(on_date, offset_secs=_effective_offset()) or krx_regular_open
        if current.time() < boundary:
            return                          # 아직 창 안 — 건수가 확정되지 않았다
        _sync_pre_frame_day()
        for ticker, n in sorted(_pre_frame_counts.items()):
            _pre_frame_cap.emit_once(
                f"pre_frame|{ticker}",
                logger.info,
                f"[tick_channel_pre_krx_frame] ticker={ticker} n={n} "
                f"first_at={_pre_frame_first.get(ticker, '-')}",
            )
    except Exception:  # pragma: no cover — never-raise
        trace_observer_failure("[tick_channel_pre_krx_frame]", "-", dest_logger=logger)


def reset_state_for_test() -> None:
    """모듈 전역 상태 초기화 (테스트 격리 seam)."""
    global _revert_for, _revert_wall_day, _CHANNELS, _pre_frame_day
    _revert_for = None
    _revert_wall_day = ""
    _CHANNELS = None
    _pre_frame_day = ""
    _WINDOW_MEMO.clear()
    _SWITCH_AT_MEMO.clear()
    _GAP_MEMO.clear()
    _pre_frame_counts.clear()
    _pre_frame_first.clear()
    _clock_config_cap.clear()
    _pre_frame_cap.clear()
