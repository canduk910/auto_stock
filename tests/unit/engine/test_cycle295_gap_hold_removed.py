"""cycle295 Red — (A) 축 · **갭 홀드 제거** 행위 가드 (G-D1 · G-D2).

명세 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §2-1 · §5-1
AST 자매 = `tests/unit/ast/test_cycle295_ast_gap_hold_removed.py`
라우트 자매 = `tests/unit/routes/test_cycle295_gap_route_surface.py`

## 🔴 되돌리기 방지 — 이 파일이 붉어졌을 때 먼저 읽을 것

cycle294 적대 검증 CRITICAL-1 은 **틀리지 않았다.** 그 지적의 *사실*은 지금도 참이다:

  (가) **사실** — 15:40~16:00 은 KRX 에 연속 체결이 없고 NXT 애프터만 continuous 다
       (`market_state.MARKET_TABLE` 파생). `test_cycle294b::test_n1` 이 그 사실의
       유일한 감시자이고 **존치**한다.
  (나) **cycle294 의 판단** — 따라서 그 구간을 KRX 채널로 덮으면 `nxt_true` 보유의
       손절 커버리지가 매일 20분 사라진다. **이 문장도 여전히 참이다.**
  (다) **2026-09-15 사용자 결정** — "청산측으로도 참여를 하지 않고자 해.
       15:30~16:00 은 완전 휴식하도록 변경해야해." 그 커버리지 손실을 **비용으로
       수용**했다. 그리고 그 20분에 HIGH 만 NXT 로 왕복시키던 전환 창 2개는
       cycle294 가 사용자 결정 「전환 1회」를 **승인 없이** 뒤집어 넣은 것이었다.

⇒ 결함이 아니라 **결정**이다. 이 파일이 붉어졌다면 `_workspace/00_URGENT_WORKLIST.md`
의 2026-09-15 결정을 먼저 확인하고, **표가 바뀌어서인지 결정이 바뀌어서인지를 가르기
전에는 기대값을 고치지 마라.** 표가 바뀐 것이라면(= KRX 가 15:45 에 연속 체결을 갖게
되면) `test_cycle294b::test_n1` 이 함께 붉어진다 — 그것이 판별식이다.

## 🔵 양성 대조군이 왜 모든 단언에 붙어 있나

cycle292 교훈 = **본체가 떠나면 "0건" 부정 단언이 전부 참이 되어 조용히 공허해진다.**
`switch_windows` 가 `return []` 로 퇴화해도 "갭 창 없음" 은 참이다. 그래서 여기서는
- 창이 **정확히 1개**이고(0개도 실패),
- 그 창의 두 경계가 **표에서 파생된 실제 값**과 일치하며,
- 같은 스윕에서 프리 창 = NXT · 정규장 = KRX 가 **실제로 관측**되는지
를 함께 단언한다.
"""

from __future__ import annotations

import datetime as _dt

import pytest

pytestmark = pytest.mark.unit

KST = _dt.timezone(_dt.timedelta(hours=9))

KRX_ONLY = "H0STCNT0"
NXT_ONLY = "H0NXCNT0"

#: 🔴 09-14 제도 변경(K6 = KRX 애프터 16:00~20:00, `effective_from=2026-09-14`) **이후**.
#: 그 이전 날짜는 표의 구간이 다르므로 기본 pin 은 항상 09-14 이상이다.
DAY = _dt.date(2026, 9, 15)
#: K6 미유효일 — 갭이 15:40~**20:00** 로 벌어지던 날. 창은 그날도 하나뿐이어야 한다.
DAY_PRE_REFORM = _dt.date(2026, 9, 11)
#: 미래 임의 영업일 — 표가 날짜 범위만 보므로 09-15 와 같아야 한다.
DAY_FUTURE = _dt.date(2026, 11, 19)

ALL_DAYS = (DAY, DAY_PRE_REFORM, DAY_FUTURE)

OFFSET = 300


def _clock():
    from src.engine import tick_channel_clock

    return tick_channel_clock


def _mode():
    from src.engine import tick_channel_mode

    return tick_channel_mode


def _at(h: int, m: int, s: int = 0, *, day: _dt.date = DAY) -> _dt.datetime:
    return _dt.datetime.combine(day, _dt.time(h, m, s), tzinfo=KST)


def _at_time(t: _dt.time, *, day: _dt.date = DAY) -> _dt.datetime:
    return _dt.datetime.combine(day, t, tzinfo=KST)


def _krx_regular_open(day: _dt.date) -> _dt.time:
    """표에서 직접 읽은 KRX 정규장 개장 — 시각 리터럴을 쓰지 않는다."""
    from src.engine.market_state import MarketPhase, get_market_table

    rows = get_market_table(day)
    opens = [r.start for r in rows if r.market == "KRX" and r.phase is MarketPhase.REGULAR]
    assert opens, f"{day} 표에 KRX 정규장 행이 없다 — 전제 붕괴"
    return min(opens)


@pytest.fixture(autouse=True)
def _isolate():
    """시각축 leaf + 모드 모듈 전역(메모·래치·다이얼)을 테스트마다 비운다."""
    clock, mode = _clock(), _mode()
    for mod in (clock, mode):
        reset = getattr(mod, "reset_state_for_test", None)
        if callable(reset):
            reset()
    yield
    for mod in (clock, mode):
        reset = getattr(mod, "reset_state_for_test", None)
        if callable(reset):
            reset()


# ===========================================================================
# G-D1 — 전환 창은 **아침 하나**뿐
# ===========================================================================
@pytest.mark.parametrize("day", ALL_DAYS, ids=lambda d: d.isoformat())
def test_gd1_switch_windows_has_exactly_the_morning_window(day):
    """🔴 G-D1 — `switch_windows()` 라벨은 **정확히** `["pre_to_krx"]` 다.

    cycle294 가 넣은 `krx_to_nxt_gap`(15:40~16:00)·`nxt_gap_to_krx`(16:00~16:05)를
    되돌린다. 사용자 결정 「전환은 하루 1회」로 복귀한다.

    🔵 **양성 대조군 3중** — ① 라벨 목록이 1원소여야 하므로 `return []` 퇴화가 죽는다
    ② 창이 비어 있지 않다(`start < end`) ③ 두 경계가 표 파생 실제 값과 일치한다.
    """
    windows = _clock().switch_windows(day, offset_secs=OFFSET)
    labels = [label for _s, _e, label in windows]

    assert labels == ["pre_to_krx"], (
        f"{day} 전환 창 라벨이 {labels} 다. cycle295 는 갭 전환 창 2개"
        "(`krx_to_nxt_gap`·`nxt_gap_to_krx`)를 **제거**한다 — 사용자 결정 「전환 1회」. "
        "0개여도 실패다(그러면 아침 전환 자체가 사라져 프리장 구독이 종일 NXT 에 남는다)"
    )

    start, end, _label = windows[0]
    assert start < end, f"{day} 아침 전환 창이 빈 구간이다: {start}~{end}"
    assert start == _clock().switch_at(day, offset_secs=OFFSET), (
        "아침 창의 시작이 `switch_at` 과 갈렸다 — 전환 시각은 파라미터에서 파생된다"
    )
    assert end == _krx_regular_open(day), (
        f"아침 창의 끝이 표의 KRX 정규장 개장({_krx_regular_open(day)})과 갈렸다"
    )


def test_gd1b_no_switch_window_is_active_anywhere_after_the_morning():
    """🔴 G-D1b — 하루 1,440분 전수: 아침 창 **밖**에는 활성 전환 창이 없다.

    🔵 양성 대조군 — 같은 스윕에서 아침 창 안의 분들이 **실제로** `pre_to_krx` 를
    돌려주는지 함께 센다(전부 `None` 인 퇴화 사살).
    """
    c = _clock()
    morning_start, morning_end, _ = c.switch_windows(DAY, offset_secs=OFFSET)[0]

    inside_hits, offenders = 0, []
    for minute in range(24 * 60):
        now = _at(minute // 60, minute % 60)
        active = c.active_switch_window(now, offset_secs=OFFSET)
        in_morning = morning_start <= now.time() < morning_end
        if in_morning:
            if active is not None and active[2] == "pre_to_krx":
                inside_hits += 1
            else:
                offenders.append(f"{now:%H:%M} 아침 창인데 active={active!r}")
        elif active is not None:
            offenders.append(f"{now:%H:%M} → {active[2]}")

    assert not offenders, (
        f"아침 창 밖에서 전환 창이 살아 있거나 아침 창이 죽었다: {offenders[:8]}"
    )
    assert inside_hits > 0, (
        "🔵 양성 대조군 실패 — 아침 창 안에서도 활성 창이 한 번도 안 잡혔다. "
        "`active_switch_window` 가 항상 `None` 을 돌려주는 퇴화다"
    )


@pytest.mark.parametrize("hh_mm", [(15, 40), (15, 45), (15, 59), (16, 0), (16, 3), (16, 5)])
def test_gd1c_the_two_gap_boundaries_are_no_longer_switch_points(hh_mm):
    """G-D1c — 갭 경계 전후 어느 분에도 전환이 예약돼 있지 않다.

    09-15 15:41:56 에 실제로 일어난 전환 7건(`window=krx_to_nxt_gap`)의 재발 지점이다.
    """
    active = _clock().active_switch_window(_at(*hh_mm), offset_secs=OFFSET)
    assert active is None, (
        f"{hh_mm[0]:02d}:{hh_mm[1]:02d} 에 전환 창 {active!r} 가 남아 있다 — "
        "15:30~16:00 은 완전 휴식이고 그 구간에 채널을 옮길 이유가 없다"
    )


# ===========================================================================
# G-D2 — `priority` 는 채널 판정을 가르지 않는다
# ===========================================================================
@pytest.mark.parametrize("day", ALL_DAYS, ids=lambda d: d.isoformat())
def test_gd2_priority_does_not_change_the_channel_for_any_minute(day):
    """🔴 G-D2 — `clock_channel(priority="HIGH")` == `priority="LOW"` 를 1,440분 전부.

    `priority` 는 3단계 시각축에서 **판정에 쓰이지 않는다** — 코호트 축(`scanner`)만
    본다. 시그니처는 `scanner.py`(8영역) diff 0 을 위해 남기지만, 그 인자가 채널을
    가르는 순간 cycle294 의 갭 분기가 되살아난 것이다.

    🔵 **양성 대조군** — 같은 스윕이 두 채널을 **모두** 관측해야 한다. 표 조회가
    실패해 전부 KRX 로 떨어지는 퇴화(그러면 HIGH==LOW 가 공허하게 참이다)를 죽인다.
    """
    c = _clock()
    diffs, seen = [], set()
    for minute in range(24 * 60):
        now = _at(minute // 60, minute % 60, day=day)
        hi = c.clock_channel(now, offset_secs=OFFSET, priority="HIGH")
        lo = c.clock_channel(now, offset_secs=OFFSET, priority="LOW")
        seen.add(hi[0])
        seen.add(lo[0])
        if hi != lo:
            diffs.append(f"{now:%H:%M} HIGH={hi} LOW={lo}")

    assert seen == {KRX_ONLY, NXT_ONLY}, (
        f"🔵 양성 대조군 실패 — 하루 스윕이 관측한 채널이 {sorted(seen)} 다. "
        "프리 창 NXT · 정규장 KRX 두 채널이 모두 나와야 판정이 살아 있는 것이다"
    )
    assert not diffs, (
        f"{day} 에 `priority` 가 채널을 갈랐다({len(diffs)}분). 표본 {diffs[:5]} — "
        "cycle294 의 NXT 단독 구간 분기가 되살아났다. 사용자 결정(2026-09-15)은 "
        "15:30~16:00 **완전 휴식**이고 그 구간에 HIGH 만 NXT 로 보내는 예외는 없다"
    )


@pytest.mark.parametrize("hh_mm", [(15, 40), (15, 45), (15, 59)])
def test_gd2b_the_gap_reason_label_is_gone(hh_mm):
    """🔴 G-D2b — 그 20분의 판정 사유가 `krx_window` 로 되돌아온다.

    사유 문자열까지 잠그는 이유 = 채널만 맞추고 사유를 남겨 두면 D+1 로그 판독자가
    `nxt_gap_window` 를 보고 "갭 홀드가 아직 돈다" 고 읽는다.

    🔵 양성 대조군 — 같은 호출이 KRX 전용 채널을 돌려주는지도 함께 본다.
    """
    c = _clock()
    for priority in ("HIGH", "LOW"):
        tr_id, reason = c.clock_channel(_at(*hh_mm), offset_secs=OFFSET, priority=priority)
        assert tr_id == KRX_ONLY, f"{hh_mm} {priority} → {tr_id}"
        assert reason == c.REASON_KRX_WINDOW, (
            f"{hh_mm} {priority} 판정 사유가 {reason!r} 다 — `nxt_gap_window` 계열 사유는 "
            "cycle295 에서 어휘째 사라진다"
        )


def test_gd2c_pre_window_and_regular_window_still_work():
    """🔵 G-D2c 양성 대조군 — 제거가 **아침 전환까지** 지우지 않았다.

    갭 제거의 실패 모드 중 가장 나쁜 것은 `clock_channel` 을 통째로 단순화해 프리 창
    NXT 판정까지 없애는 것이다(그러면 08:00~08:55 프리장 체결을 못 받는다).
    """
    c = _clock()
    assert c.clock_channel(_at(8, 30), offset_secs=OFFSET)[0] == NXT_ONLY
    assert c.clock_channel(_at(8, 54, 59), offset_secs=OFFSET)[0] == NXT_ONLY
    assert c.clock_channel(_at(8, 55), offset_secs=OFFSET)[0] == KRX_ONLY
    assert c.clock_channel(_at(10, 0), offset_secs=OFFSET)[0] == KRX_ONLY
    assert c.clock_channel(_at(19, 0), offset_secs=OFFSET)[0] == KRX_ONLY


# ===========================================================================
# G-D2d — 다이얼로도 되살릴 수 없다
# ===========================================================================
def test_gd2d_no_dial_can_bring_the_gap_hold_back():
    """🔴 G-D2d — 갭 홀드를 켜는 **수단 자체가 없다**.

    사용자가 지목한 것은 "`tick_channel_gap_hold_enabled` 변수와 그 변수를 케어하는
    로직 … 시스템 복잡도" 다. 다이얼만 `false` 로 두고 코드를 남기면
    (a) 재기동 후 최대 120초 동안 프로세스 기본값 `True` 로 **재무장**되고
        (`refresh_switch_params` 가 DB 를 다시 읽기 전까지),
    (b) 그 사이 HIGH 로 발사된 구독은 창이 사라진 뒤에도 **되돌릴 창이 없어**
        20:00 `unsubscribe_all` 까지 NXT 에 남는다.
    그래서 제거는 "다이얼이 끌 수 없는 잔여 경로를 구조적으로 0 으로 만드는" 일이다.
    """
    mode = _mode()
    for name in ("gap_hold_enabled", "apply_gap_hold_enabled",
                 "GAP_HOLD_ENABLED_KEY", "DEFAULT_GAP_HOLD_ENABLED"):
        assert not hasattr(mode, name), (
            f"`tick_channel_mode.{name}` 이 남아 있다 — 갭 홀드를 켜는 경로가 살아 있다"
        )

    seam = getattr(mode, "set_switch_params_for_test", None)
    assert callable(seam), "🔵 양성 대조군 — 전환 파라미터 테스트 seam 자체가 사라졌다"
    seam(switch_enabled=True)          # 🔵 나머지 키는 그대로 받는다
    with pytest.raises(TypeError):
        seam(gap_hold_enabled=True)

    clock = _clock()
    for name in ("gap_hold_enabled", "in_nxt_gap", "nxt_only_continuous_window",
                 "REASON_NXT_GAP_WINDOW"):
        assert not hasattr(clock, name), (
            f"`tick_channel_clock.{name}` 이 남아 있다 — 소비처가 0 이어도 다음 사람이 "
            "다시 배선한다(사용자가 없애자고 한 '복잡도' 의 본체다)"
        )
