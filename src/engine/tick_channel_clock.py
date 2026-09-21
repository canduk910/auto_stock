"""cycle294 §1 — 시세 채널 **시각축** 판정 leaf (8영역 밖 · 순수 · never-raise).

3단계의 종착지는 통합 채널의 **소멸**이다. 09-15 07:45 부팅부터 두 채널만 쓴다
— 프리장은 NXT 전용, 정규장+애프터는 KRX 전용. 그 배치는 아래와 같고 전환은
하루 **1회**뿐이다.

    프리장(N1 구간)        → NXT 전용   (그 시각 NXT 만 연속 체결을 싣는다)
    전환 창                → 주문 0건 · cycle241 시장 침묵 ⇒ 전환 비용 ≈ 0
    정규장 + 애프터마켓    → KRX 전용   (연속, 15:30~16:00 포함)

## 🔴 cycle295 — CRITICAL-1 *시정* 은 철회됐다. *사실* 은 그대로다

cycle294 착지 직후 적대 검증이 찾은 사실은 지금도 참이다 — `krx_continuous_end`
는 **연속** 구간 end 최댓값인데, 09-15 표에는 그 사이에 연속이 아닌 구간이 끼어
있다(`get_market_table(2026-09-15)` 실측):

    KRX  REGULAR            09:00~15:20  continuous
    KRX  CLOSE_AUCTION      15:20~15:30  single_auction     ← 연속 아님
    KRX  AFTER_CLOSE_FIXED  15:30~16:00  fixed_price        ← 연속 아님
    KRX  AFTER_MARKET       16:00~20:00  continuous
    NXT  AFTER_MARKET       15:40~20:00  continuous         ← 15:40~16:00 은 NXT 뿐

⇒ **15:40~16:00(20분) 은 NXT 에만 연속 체결이 있다** — 이 문장은 여전히 참이다.

cycle294 는 그 20분 동안 **보유(HIGH)만** NXT 를 따라가는 전환 창 2개
(`krx_to_nxt_gap`·`nxt_gap_to_krx`)와 킬스위치 `tick_channel_gap_hold_enabled`
를 사용자 결정 「전환은 하루 1회」에 **승인 없이** 추가했다. 2026-09-15 사용자가
"청산측으로도 참여를 하지 않고자 해. 15:30~16:00 은 완전 휴식하도록 변경해야해"
로 그 시정을 **철회**했다 — 그 20분의 손절 커버리지 손실을 비용으로 수용한
것이다. cycle295(`_workspace/red/cycle295_gap_hold_removal_spec.md`)가 이 배선을
**구조적으로 0** 으로 만들었다 — 갭 함수·킬스위치·전환 창 2개·DB 헬퍼 2개·라우트
필드 4개가 전부 제거됐다. **되돌리기 전에 그 명세의 §1·§6-4 를 먼저 읽어라** —
표가 바뀌어서(KRX 가 그 시각에 연속체결을 갖게 됐다)인지 사용자 결정이 바뀌어서
인지를 가르기 전에는 이 절을 되살리지 마라. 판별식은
`tests/unit/engine/test_cycle294b_adversarial_fixes.py::test_n1` 이다.

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

    🔴 cycle295 — `priority` 는 **판정에 쓰이지 않는다.** cycle294 가 NXT 단독
    연속 구간(모듈 docstring §CRITICAL-1)에서 HIGH 만 NXT 를 따라가게 했던 분기는
    2026-09-15 사용자 결정("15:30~16:00 완전 휴식")으로 **철회**됐다 — 그 결정의
    *근거*였던 사실(15:40~16:00 은 NXT 만 연속)은 여전히 참이지만, *시정*은
    되돌렸다. 시그니처는 `scanner.py`(8영역) diff 0 을 위해 유지한다(§2-3) —
    판정은 코호트 축(`scanner.tick_buy_cohort_blocked`)만 본다.
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
            return krx_only, REASON_KRX_WINDOW
        # 연속 체결 종료 이후 — 구독 자체가 없는 구간이다(20:00 `unsubscribe_all`).
        return krx_only, REASON_POST_CLOSE
    except Exception:
        return krx_only, REASON_CLOCK_ERROR


def switch_windows(on_date: _date | None = None, *, offset_secs: int | None = None):
    """그날 **전환이 허용되는 창** 목록 `[(start, end, label), …]`.

    cycle295 — 사용자 결정 「전환은 하루 1회」로 되돌아온다. cycle294 가 NXT
    단독 연속 구간(모듈 docstring §CRITICAL-1) 커버리지를 위해 추가했던
    `krx_to_nxt_gap`·`nxt_gap_to_krx` 두 창은 **철회**됐다 — 그 시정의 *근거*는
    여전히 참이지만, 사용자가 그 손절 커버리지 손실을 비용으로 수용했다.

      W1 `pre_to_krx`     [switch_at, krx_regular_open)      — 프리 창 → KRX
    """
    try:
        target = on_date if on_date is not None else _wall_date()
        if target is None:
            return []
        krx_regular_open, _pre_end, _krx_end = _windows(target)
        if krx_regular_open is None:
            return []
        windows: list[tuple] = []
        boundary = switch_at(target, offset_secs=offset_secs)
        if boundary is not None and boundary < krx_regular_open:
            windows.append((boundary, krx_regular_open, "pre_to_krx"))
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

    🔴 cycle295 — `nxt_gap=`·`gap_hold=` 두 필드가 빠졌다(§6-6, 그 배선 자체가
    사라졌다). 나머지 4필드는 byte 동일하게 남는다.
    """
    try:
        on_date = now.date() if now is not None else _wall_date()
        krx_regular_open, nxt_pre_end, krx_continuous_end = _windows(on_date)
        boundary = switch_at(on_date, offset_secs=offset_secs)
        wanted = offset_secs if offset_secs is not None else DEFAULT_SWITCH_OFFSET_SECS
        _clock_config_cap.emit_once(
            f"clock|{on_date}",
            logger.warning,
            f"[tick_channel_clock] switch_at={boundary} krx_open={krx_regular_open} "
            f"krx_end={krx_continuous_end} nxt_pre_end={nxt_pre_end} "
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

    `H0STCNT0` 이 KRX 시가 단일가 구간에 프레임을 보내는가? **실측 완료(2026-09-21,
    5영업일 180행)** — K1(시가 단일가)에는 **0건이 맞다**. 빠뜨린 것은 그 안에
    **의도적으로 중첩**된 **K2(장전 시간외 종가 08:30~08:40)** 한 행이고,
    거기는 `match_kind="fixed_price"`(전일 종가 고정)라 **실제 체결이 난다**
    (`market_state.py` K2 행이 `confidence=_CONFIRMED` 로 이미 적어 두었다).
    즉 원래 추론은 **사실이 틀린 것이 아니라 범위가 좁았다**.

    이 함수는 이제 일회성 검증이 아니라 **K2 프레임 규모의 상시 계측기**다.
    행위는 **바꾸지 않는다** — 게이트를 더하는 것은 매매 행위 변경이라 별도 승인
    대상이고, 🔴 **K2 노출에 새 게이트를 만들지 않는다**(막을 것이 없는 게이트는
    다음 사람에게 없는 위험을 있다고 가르친다 — 아래 잠금 셋 참조).

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

    기대값은 **K2 한정 일 30~55행**이다(2026-09-15~09-21 실측 51·33·55·38·3).

    🔴 **판별식은 행 수가 아니라 `first_at` 최솟값이다.**
      * `first_at >= 08:30` — 정상. K2 구간이고 원래 추론은 살아 있다
      * `08:20 <= first_at < 08:30` — 🟠 K1 에 체결이 났다. 추론이 흔들린다
      * `first_at < 08:20` — 🔴 **§0 추론 붕괴.** 결정 카드로 올린다

    ⚠️ **행 수가 많다고 사고가 아니다** — 2026-09-21 에 180행을 보고 한 번
    CRITICAL 로 오판했다. 그때 실측 최솟값은 정확히 `08:30:00` 이었다.

    K2 구간이 매수로 새지 않는 이유(잠금 셋, `cycle336` 실측) — 그 10분에 보드
    가드를 통과하는 전략은 **LTV 하나**이고 K2 는 전일 종가 고정이라
    ① `min_prdy_rate`(운영 5.0) vs 등락률 **0.0%** 로 돌파 검사 **앞**에서 컷
    ② `prev == current` 라 돌파 술어가 논리적 모순
    ③ `target = board_open + target_offset > current`.
    🔴 **`min_prdy_rate` 를 0 이하로 내리면 그 첫 잠금이 사라진다.**
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
    _pre_frame_counts.clear()
    _pre_frame_first.clear()
    _clock_config_cap.clear()
    _pre_frame_cap.clear()
