"""cycle294b — 3단계 착지 직후 **적대 검증 지적 시정**의 회귀 가드.

검증 3렌즈(전환 사각 · 매수 축 · 부팅/운영)가 찾은 CRITICAL 4 · HIGH 4 · MEDIUM
다수를 닫은 코드를 잠근다. 자매 = `tests/unit/engine/test_cycle294_stage3.py`
(3단계 본체) · `tests/unit/ast/test_cycle294_ast_stage3.py`.

| ID | 등급 | 닫은 것 |
|----|------|---------|
| N1~N6 | 🔴 CRITICAL-1 | **15:40~16:00 NXT 단독 연속 구간** — KRX 채널로 덮으면 `nxt_true` 보유 종목의 손절 트리거가 매일 20분 사라진다(INV-1 위반) |
| R1~R6 | 🔴 CRITICAL-2 | 자동 원복이 진짜 고장에서 발화하고, 비결론 판정은 래치하지 않는다 |
| M1~M3 | 🔴 CRITICAL-3 | 원복도 **make-before-break** — 보유 종목에 break-before-make 금지 |
| Z1~Z3 | 🟠 HIGH-1 | LOW 전환 실패가 **구독 좀비**를 만들지 않는다 + 고아 튜플 회수 |
| W1~W3 | 🟠 HIGH-3 | 창 **안에서도** 종목마다 경계를 다시 본다 |
| S1~S4 | 🔴 CRITICAL-1(부팅) | 코호트 스탬프 **재시도** — 07:59 도장 창 1회 기회 결함 |
| G1~G2 | 🔴 CRITICAL-2(부팅) | `[tick_buy_gate]` 가 스탬프 **뒤** 값을 남긴다(구간별 1행) |
| E1~E2 | 🟠 HIGH-1(부팅) | `enforce_low` 의 HIGH 제외가 재라우팅에 무력화되지 않는다 |
| T1~T2 | 🟡 MEDIUM-2 | 전환 대상에서 프로브·비-TICK 라우팅 제외 |
| P1~P2 | 🟡 MEDIUM-3 | `off`/`disabled` 로 빠져나가도 미전환 잔여를 남긴다 |
| L1 | 🟡 MEDIUM-3(clock) | `day_reverted` 래치가 영구화되지 않는다 |
| F1 | 🟠 F-1(매수축) | 출처 조회 실패가 **WARNING** 으로 리포트에 뜬다 |
"""

from __future__ import annotations

import datetime as _dt
import logging

import pytest

from tests.unit.engine.test_cycle294_stage3 import (  # noqa: F401 — 픽스처 재사용
    DAY,
    KRX_ONLY,
    NO_FEED,
    NO_FEED_2,
    NXT_ONLY,
    NXT_TRUE,
    NXT_TRUE_2,
    UNIFIED,
    _at,
    _clock,
    _cohort_blocked,
    _fake_scheduler,
    _isolate,
    _patch_classification,
    _pool_env,
    _run_switch,
    _scanner,
    _seed_subscription,
    _set_mode,
    _set_switch_params,
    _switch_mod,
)

pytestmark = pytest.mark.unit


# ===========================================================================
# N1~N6 (🔴 CRITICAL-1) — NXT 단독 연속 구간
# ===========================================================================
def test_n1_table_says_krx_has_no_continuous_matching_between_1540_and_1600():
    """🔴 사실 확인 — 이 시정의 전제는 추론이 아니라 **표가 말하는 것**이다.

    09-15 `get_market_table` 실측: KRX 는 15:20 종가단일가 → 15:30 시간외 종가
    (fixed_price) → 16:00 애프터마켓(continuous). NXT 는 15:40 애프터가
    continuous. 그래서 15:40~16:00 은 **NXT 에만 연속 체결이 있다**.
    """
    from src.engine.market_state import get_market_table

    rows = get_market_table(DAY)
    krx = [(r.start, r.end) for r in rows if r.market == "KRX" and r.match_kind == "continuous"]
    nxt = [(r.start, r.end) for r in rows if r.market == "NXT" and r.match_kind == "continuous"]
    gap_t = _dt.time(15, 45)
    assert not any(a <= gap_t < b for a, b in krx), (
        "표가 바뀌어 KRX 가 15:45 에 연속 체결을 갖게 됐다 — 이 시정의 전제가 "
        "사라졌으므로 `nxt_only_continuous_window` 를 다시 검토하라"
    )
    assert any(a <= gap_t < b for a, b in nxt), "NXT 애프터(15:40~20:00)가 표에서 사라졌다"


def test_n2_gap_window_is_derived_from_the_table_not_from_literals():
    """N2 — 구간은 두 시장의 연속 집합 **빼기**로 나온다(시각 리터럴 0건)."""
    start, end = _clock().nxt_only_continuous_window(DAY)
    assert (start, end) == (_dt.time(15, 40), _dt.time(16, 0)), (
        f"09-15 NXT 단독 연속 구간이 15:40~16:00 이 아니다: {start}~{end}"
    )


def test_n3_high_follows_nxt_in_the_gap_but_low_stays_on_krx():
    """🔴 N3 — 그 20분에 **보유(HIGH)만** NXT 를 따라간다.

    LOW 후보 ~130종목을 하루 두 번 왕복시키면 KIS 공지 「비정상 케이스 2:
    무한 등록/해제」에 정면으로 걸린다. 그 구간에 필요한 것은 손절 커버리지뿐이다.
    """
    c = _clock()
    for hh, mm in ((15, 41), (15, 59)):
        now = _at(hh, mm)
        assert c.clock_channel(now, offset_secs=300, priority="HIGH")[0] == NXT_ONLY, (
            f"{hh}:{mm} 에 보유 종목이 KRX 채널에 남는다 — 그 시각 KRX 에는 연속 "
            "체결이 없어 손절 트리거가 통째로 사라진다(INV-1 위반)"
        )
        assert c.clock_channel(now, offset_secs=300, priority="LOW")[0] == KRX_ONLY, (
            "LOW 후보까지 NXT 로 옮기면 하루 두 번 ~130종목 왕복이다"
        )


@pytest.mark.parametrize("hh_mm", [(15, 25), (15, 39), (16, 0), (16, 5), (19, 0)])
def test_n4_gap_is_closed_on_both_edges(hh_mm):
    """N4 — 경계 양쪽. 15:39 은 아직 KRX, 16:00 정각은 이미 KRX 로 돌아온다."""
    now = _at(*hh_mm)
    assert _clock().clock_channel(now, offset_secs=300, priority="HIGH")[0] == KRX_ONLY


def test_n5_gap_dial_off_restores_the_single_morning_switch():
    """N5 — 킬스위치. `gap_hold_enabled=false` 면 배포 직후 설계와 동일하다."""
    _set_switch_params(gap_hold_enabled=False)
    assert _clock().clock_channel(_at(15, 45), offset_secs=300, priority="HIGH")[0] == KRX_ONLY
    assert len(_clock().switch_windows(DAY, offset_secs=300)) == 1, (
        "다이얼을 내렸는데 NXT 구간 전환 창이 남아 있다"
    )


def test_n6_no_feed_high_stays_on_krx_inside_the_gap(monkeypatch):
    """🔴 N6 — 그 구간에도 **속성축이 이긴다**.

    `nxt_false` 보유 종목을 NXT 로 보내면 그 채널은 그 종목의 프레임을 애초에
    보내지 않으므로 **새 blind** 를 만든다. 원복(`day_reverted`)이 "전원 NXT" 가
    아니라 프리 창 규칙인 것과 같은 이유다.
    """
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,),
                          classified=(NO_FEED,))
    _set_mode("enforce")
    assert _scanner().desired_tick_tr_id(NO_FEED, priority="HIGH", now=_at(15, 45)) == KRX_ONLY


def test_n7_three_switch_windows_exist_and_do_not_overlap():
    """N7 — 창 목록은 아침 1 + 구간 경계 2 이고 서로 겹치지 않는다."""
    windows = _clock().switch_windows(DAY, offset_secs=300)
    labels = [label for _s, _e, label in windows]
    assert labels == ["pre_to_krx", "krx_to_nxt_gap", "nxt_gap_to_krx"], labels
    for (s1, e1, _l1), (s2, _e2, _l2) in zip(windows, windows[1:]):
        assert s1 < e1 <= s2, f"창이 겹치거나 역전됐다: {windows}"


# ===========================================================================
# W1~W3 (🟠 HIGH-3) — 창 안에서도 경계를 다시 본다
# ===========================================================================
async def test_w1_loop_stops_when_it_crosses_the_window_edge(monkeypatch, _pool_env):
    """🔴 W1 — 사이클이 창 끝을 넘기면 **남은 종목을 옮기지 않는다.**

    120초 stale watcher 는 부팅 시각 기준 고정 위상이라 08:59:4x 에 창 안으로
    들어올 수 있다. 종전 구현은 그 뒤 `MAX_PER_CYCLE`/`BUDGET_SECS` 가 찰 때까지
    창을 넘겨 계속 옮겼고, 그 경우 LOW 의 break-before-make 가 **개장 직후 실제
    blind** 를 만든다.
    """
    pool, session = _pool_env
    sw = _switch_mod()
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE, NXT_TRUE_2),
                          classified=(NXT_TRUE, NXT_TRUE_2))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    for t in (NXT_TRUE, NXT_TRUE_2):
        _seed_subscription(pool, session, t, NXT_ONLY)
    scheduler = _fake_scheduler({NXT_TRUE, NXT_TRUE_2})

    # 첫 종목을 처리한 직후 시각이 창 끝을 넘어간 것으로 만든다.
    calls = {"n": 0}
    real = sw._advanced

    def _fake_advanced(now, started):
        calls["n"] += 1
        return now if calls["n"] <= 1 else _at(9, 1)

    monkeypatch.setattr(sw, "_advanced", _fake_advanced)
    result = await _run_switch(scheduler, pool, _at(8, 59, 45))
    monkeypatch.setattr(sw, "_advanced", real)

    assert result.get("left_window") is True, "창을 넘겼는데 루프가 멈추지 않았다"
    assert result.get("switched") == 1, (
        f"창을 넘긴 뒤에도 계속 옮겼다: {result}"
    )


async def test_w2_advanced_uses_the_cycle_now_not_the_wall_clock():
    """W2 — 경과 시각은 호출자가 넘긴 `now` 기준이다(벽시계 재조회 금지).

    벽시계를 다시 읽으면 창 판정이 두 시계 사이에서 갈리고, 합성 `now` 로 창
    안/밖을 만드는 테스트가 **실행 시각에 따라** 결과를 바꾼다(메모리 교훈:
    「시각 창 게이트 테스트는 시각 고정」).
    """
    import time as _time

    sw = _switch_mod()
    now = _at(8, 56)
    out = sw._advanced(now, _time.monotonic())
    assert abs((out - now).total_seconds()) < 5, (
        f"`_advanced` 가 벽시계를 읽는다: {out} (기대 ≈ {now})"
    )


async def test_w3_switch_summary_names_the_window(monkeypatch, _pool_env, caplog):
    """W3 — 요약 마커가 **어느 창**이었는지 남긴다(창이 셋이 됐다)."""
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    caplog.set_level(logging.WARNING)
    await _run_switch(_fake_scheduler({NXT_TRUE}), pool, _at(8, 56))
    assert any("window=pre_to_krx" in r.message for r in caplog.records), (
        "`[tick_channel_switch_summary]` 에 창 라벨이 없다 — 창이 셋이라 어느 창의 "
        "전환인지 모르면 D+1 판독이 성립하지 않는다"
    )


# ===========================================================================
# M1~M3 (🔴 CRITICAL-3) + R1~R6 (🔴 CRITICAL-2) — 자동 원복
# ===========================================================================
async def _probe(monkeypatch, pool, session, *, held, on_krx, fresh, at):
    """전환을 거치지 않고 **원복 판정만** 돌린다(표본이 전환 성공에 묶이지 않는다)."""
    import src.engine.scanner as scanner_mod

    _set_mode("enforce")
    _set_switch_params(switch_enabled=True, offset_secs=300, revert_probe_secs=180)
    for t in on_krx:
        _seed_subscription(pool, session, t, KRX_ONLY)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {t: _at(9, 2, 30) for t in fresh})
    return await _run_switch(_fake_scheduler(set(held)), pool, at)


async def test_r1_sample_includes_high_that_was_never_switched(monkeypatch, _pool_env):
    """🔴 R1 (CRITICAL-2 A·D / HIGH-2) — 표본은 **지금 KRX 에 앉은 HIGH** 다.

    종전 표본은 "그날 아침 NXT→KRX 전환에 성공한 HIGH" 뿐이었다. 그러면 프리
    창부터 KRX 였던 `nxt_false` 보유 종목 — 이 사이클이 겨냥한 바로 그 코호트 —
    이 표본에 영영 못 들어오고, `nxt_true` 보유가 0인 날이나 `enforce_low`
    단계에서는 표본이 비어 **원복 자체가 존재하지 않았다**.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(NO_FEED, NO_FEED_2),
                          provenance_ok=(NO_FEED, NO_FEED_2, NXT_TRUE, NXT_TRUE_2),
                          classified=(NO_FEED, NO_FEED_2, NXT_TRUE, NXT_TRUE_2))
    sw = _switch_mod()
    for t in (NO_FEED, NO_FEED_2):
        _seed_subscription(pool, session, t, KRX_ONLY)
    sample = sw._revert_sample(_fake_scheduler({NO_FEED, NO_FEED_2}), pool)
    assert sample == sorted([NO_FEED, NO_FEED_2]), (
        f"전환한 적 없는 보유 종목이 원복 표본에서 빠진다: {sample}"
    )


async def test_r2_revert_fires_when_there_is_no_cross_cohort(monkeypatch, _pool_env, caplog):
    """🔴 R2 (CRITICAL-2 A) — 전 종목이 같은 채널일 때도 되돌릴 수 있다.

    3단계 `enforce` 의 **정상 상태**가 "전 종목 같은 채널" 이다. 종전 교차 확인은
    그때 `cross_fresh=0` → `market_wide` 로 기각했으므로, 그 채널이 진짜 죽은 날
    자동 원복이 **구조적으로 발화하지 못했다**. 2×probe(=09:06) 뒤에는 비교
    대상 부재 자체를 근거로 되돌린다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE, NXT_TRUE_2),
                          classified=(NXT_TRUE, NXT_TRUE_2))
    caplog.set_level(logging.INFO)
    await _probe(monkeypatch, pool, session, held=(NXT_TRUE, NXT_TRUE_2),
                 on_krx=(NXT_TRUE, NXT_TRUE_2), fresh=(), at=_at(9, 3))
    assert _clock().day_reverted(_at(9, 3)) is False, "09:03 에 성급히 되돌렸다"
    await _probe(monkeypatch, pool, session, held=(NXT_TRUE, NXT_TRUE_2),
                 on_krx=(NXT_TRUE, NXT_TRUE_2), fresh=(), at=_at(9, 7))
    assert _clock().day_reverted(_at(9, 7)) is True, (
        "🔴 비교 코호트가 없다는 이유로 되돌리지 않았다 — 3단계 정상 상태가 바로 "
        "그 상태라 이 경로가 막히면 자동 원복은 죽은 장치다(절대 규칙 4)"
    )
    assert any("all_silent_no_cross" in r.message for r in caplog.records)


async def test_r3_non_decisive_verdict_does_not_latch(monkeypatch, _pool_env):
    """🔴 R3 (CRITICAL-2 C) — 비결론 판정은 **하루 한 번**을 소비하지 않는다.

    종전에는 판정 **전에** `_revert_probe_done=True` 를 세워, 첫 측정이
    `sample_too_small`/`market_wide` 로 끝나면 그날 다시는 재지 않았다.
    """
    pool, session = _pool_env
    sw = _switch_mod()
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    await _probe(monkeypatch, pool, session, held=(NXT_TRUE,), on_krx=(NXT_TRUE,),
                 fresh=(), at=_at(9, 3))
    assert sw._revert_probe_done is False, (
        "표본 부족(비결론)인데 그날 측정을 종료했다 — 나중에 보유가 생겨도 다시 "
        "재지 않는다"
    )


async def test_r4_frames_present_is_decisive_and_ends_the_probe(monkeypatch, _pool_env):
    """R4 — 프레임이 오면 그날 종결이다(건강 판정은 결론적)."""
    pool, session = _pool_env
    sw = _switch_mod()
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE, NXT_TRUE_2),
                          classified=(NXT_TRUE, NXT_TRUE_2))
    await _probe(monkeypatch, pool, session, held=(NXT_TRUE, NXT_TRUE_2),
                 on_krx=(NXT_TRUE, NXT_TRUE_2), fresh=(NXT_TRUE,), at=_at(9, 3))
    assert sw._revert_probe_done is True
    assert _clock().day_reverted(_at(9, 3)) is False


async def test_r5_probe_attempts_are_capped(monkeypatch, _pool_env):
    """R5 — 비결론이 반복돼도 무한히 재지 않는다(폭주 방지)."""
    pool, session = _pool_env
    sw = _switch_mod()
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    for _ in range(sw.MAX_REVERT_PROBE_ATTEMPTS + 3):
        await _probe(monkeypatch, pool, session, held=(NXT_TRUE,), on_krx=(NXT_TRUE,),
                     fresh=(), at=_at(9, 3))
    assert sw._revert_attempts <= sw.MAX_REVERT_PROBE_ATTEMPTS


async def test_m1_revert_uses_make_before_break_on_held_tickers(monkeypatch, _pool_env):
    """🔴 M1 (CRITICAL-3) — 원복도 **신 채널 확인 뒤 구 채널 해제**다.

    종전에는 보유 종목에 `make_before_break=False`(= 선해제 + `bypass_limit=False`)
    를 09:03 **라이브 구간에** 걸고 반환값도 읽지 않았다. 41-cap·OPSP 백오프에
    걸리면 그 종목이 어느 채널에도 없는 채로 종일 남는다. 근거로 적혀 있던
    "되돌림의 전제가 프레임 0" 은 오발화 시 거짓이고, 모듈 docstring 의 절대 규칙
    2(HIGH make-before-break)와도 모순이었다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE, NXT_TRUE_2),
                          classified=(NXT_TRUE, NXT_TRUE_2))
    seen = {}

    async def _spy(tr_key, new_tr_id, *, make_before_break=True, **kw):
        seen[tr_key] = make_before_break
        return "switched"

    monkeypatch.setattr(pool, "switch_channel_same_session", _spy)
    await _probe(monkeypatch, pool, session, held=(NXT_TRUE, NXT_TRUE_2),
                 on_krx=(NXT_TRUE, NXT_TRUE_2), fresh=(NO_FEED, NO_FEED_2), at=_at(9, 3))
    assert seen, "원복이 아무 종목도 옮기지 않았다"
    assert all(v is True for v in seen.values()), (
        f"🔴 보유 종목 원복에 break-before-make 를 썼다: {seen}"
    )


async def test_m2_revert_respects_the_attribute_axis(monkeypatch, _pool_env):
    """M2 (§5-B / G-294-10) — 되돌림은 "전원 NXT" 가 아니라 **프리 창 규칙**이다.

    단순 전원 NXT 면 `nxt_false` 종목이 NXT 에서 프레임 0 이 되어 **원복이 새
    blind 를 만든다**. 되돌린 뒤에도 그 코호트는 KRX 를 유지해야 한다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(NO_FEED,),
                          provenance_ok=(NO_FEED, NXT_TRUE, NXT_TRUE_2),
                          classified=(NO_FEED, NXT_TRUE, NXT_TRUE_2))
    targets = {}

    async def _spy(tr_key, new_tr_id, **kw):
        targets[tr_key] = new_tr_id
        return "switched"

    monkeypatch.setattr(pool, "switch_channel_same_session", _spy)
    await _probe(monkeypatch, pool, session, held=(NXT_TRUE, NO_FEED),
                 on_krx=(NXT_TRUE, NO_FEED), fresh=(), at=_at(9, 7))
    assert _clock().day_reverted(_at(9, 7)) is True
    assert targets.get(NXT_TRUE) == NXT_ONLY
    assert targets.get(NO_FEED) in (None, KRX_ONLY), (
        f"🔴 `nxt_false` 를 NXT 로 되돌렸다 — 그 채널은 그 종목의 프레임을 애초에 "
        f"보내지 않는다(원복이 새 blind 를 만든다): {targets}"
    )


async def test_m3_revert_failure_is_counted_and_logged(monkeypatch, _pool_env, caplog):
    """M3 — 원복 실패는 세어서 ERROR 행에 싣는다(반환값을 버리지 않는다)."""
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE, NXT_TRUE_2),
                          classified=(NXT_TRUE, NXT_TRUE_2))

    async def _fail(tr_key, new_tr_id, **kw):
        return "low_drop"

    monkeypatch.setattr(pool, "switch_channel_same_session", _fail)
    caplog.set_level(logging.WARNING)
    await _probe(monkeypatch, pool, session, held=(NXT_TRUE, NXT_TRUE_2),
                 on_krx=(NXT_TRUE, NXT_TRUE_2), fresh=(NO_FEED, NO_FEED_2), at=_at(9, 3))
    errors = [r.message for r in caplog.records if "[tick_channel_auto_revert]" in r.message]
    assert errors and "failed=2" in errors[0], (
        f"원복 실패가 ERROR 행에 안 실렸다: {errors}"
    )


# ===========================================================================
# Z1~Z3 (🟠 HIGH-1) — 전환 실패가 좀비를 만들지 않는다
# ===========================================================================
async def test_z1_low_drop_releases_the_routing(monkeypatch, _pool_env, caplog):
    """🔴 Z1 — LOW 전환이 실패하면 **라우팅을 비운다**.

    종전에는 세션에 튜플이 0개인데 풀은 "구독돼 있다" 고 믿었다. 그러면 그 종목이
    `get_subscribed_tickers()` 에서 빠져 K stale watcher 가 영원히 못 보고,
    `delta_unsubscribe_dropped` 의 정리 대상도 아니며, 다음 `subscribe` 는 중복
    분기에서 SEND 없이 조기 반환한다 ⇒ 20:00 까지 자가 치유 경로가 없다.
    """
    pool, session = _pool_env
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    session._subscriptions.discard((NXT_ONLY, NXT_TRUE))

    async def _no_sub(tr_id, tr_key, **kw):
        return None

    monkeypatch.setattr(session, "subscribe", _no_sub)
    caplog.set_level(logging.WARNING)
    result = await pool.switch_channel_same_session(
        NXT_TRUE, KRX_ONLY, make_before_break=False, ack_timeout_secs=0.01,
    )
    assert result == "low_drop"
    assert NXT_TRUE not in pool._ticker_to_session, "세션 라우팅이 남았다(좀비)"
    assert NXT_TRUE not in pool._ticker_to_tr_id, "채널 라우팅이 남았다(좀비)"
    assert any("routing=released" in r.message for r in caplog.records)


async def test_z2_orphan_puts_the_old_tuple_back_for_the_2000_sweep(monkeypatch, _pool_env):
    """🔴 Z2 — 구 채널 해제가 SEND 에서 실패하면 튜플을 **되돌려 놓는다**.

    `KisWebSocket.unsubscribe` 는 `_subscriptions.discard` 를 먼저 하고 SEND 한다.
    실패하면 KIS 쪽 구독은 살아 있는데 로컬에서는 사라져 20:00 `unsubscribe_all()`
    (로컬 튜플 전수 순회)이 회수하지 못한다 — 영구 고아 + 41 슬롯 잠식 +
    `detect_dual_tick_channels` 도 못 본다.
    """
    pool, session = _pool_env
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)

    real_unsub = session.unsubscribe

    async def _flaky(tr_id, tr_key, **kw):
        if tr_id == NXT_ONLY:
            session._subscriptions.discard((tr_id, tr_key))
            raise RuntimeError("send failed")
        return await real_unsub(tr_id, tr_key, **kw)

    async def _ok_sub(tr_id, tr_key, **kw):
        session._subscriptions.add((tr_id, tr_key))
        session._subscriptions_acked.add((tr_id, tr_key))

    monkeypatch.setattr(session, "unsubscribe", _flaky)
    monkeypatch.setattr(session, "subscribe", _ok_sub)
    result = await pool.switch_channel_same_session(
        NXT_TRUE, KRX_ONLY, make_before_break=True, ack_timeout_secs=1.0,
    )
    assert result == "switched_orphan"
    assert (NXT_ONLY, NXT_TRUE) in session._subscriptions, (
        "🔴 고아 튜플이 로컬 집합에서 사라졌다 — 20:00 일괄 해제가 회수하지 못한다"
    )
    assert pool._ticker_to_tr_id[NXT_TRUE] == KRX_ONLY


async def test_z3_ack_timeout_still_keeps_the_routing(_pool_env, monkeypatch):
    """Z3 — ACK 타임아웃은 라우팅을 **건드리지 않는다**(구 채널이 살아 있다)."""
    pool, session = _pool_env
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)

    async def _silent_sub(tr_id, tr_key, **kw):
        return None

    monkeypatch.setattr(session, "subscribe", _silent_sub)
    result = await pool.switch_channel_same_session(
        NXT_TRUE, KRX_ONLY, make_before_break=True, ack_timeout_secs=0.01,
        poll_interval=0.001,
    )
    assert result == "ack_timeout"
    assert pool._ticker_to_tr_id[NXT_TRUE] == NXT_ONLY
    assert pool._ticker_to_session.get(NXT_TRUE) is session


# ===========================================================================
# S1~S4 (🔴 CRITICAL-1 부팅) — 코호트 스탬프 재시도
# ===========================================================================
def test_s1_restamp_closes_the_w2_stamping_window(monkeypatch):
    """🔴 S1 — 07:59 도장 오염으로 놓친 스탬프를 **나중에 심는다**.

    `tick_tr_id_for` 안의 스탬프는 LOW 종목에 대해 그날 07:59 한 번뿐이었다
    (`already_in_pool` skip 이 리졸버 호출보다 앞). 그런데 07:59 는
    `_full_universe_load_krx_primary` 의 `nxt_tradable=False` 도장이 마스터의
    65.4% 를 덮고 있는 시각이라, 그때 출처 검사가 실패한 종목이 **영영
    미스탬프**로 남아 매수 축 게이트가 열린 채 방치됐다 = 승인 없는 B-2 부분 발생.
    """
    scanner = _scanner()
    scanner.reset_tick_channel_state_for_test()
    _set_mode("enforce")
    # 07:59 — 도장 상태(진짜 nxt_false 인데 출처 미확인)
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(),
                          classified=(NO_FEED,))
    scanner.tick_tr_id_for(NO_FEED, priority="LOW", now=_at(7, 59))
    assert _cohort_blocked(NO_FEED) is False, "출처 미확인인데 스탬프가 심겼다"

    # 08:08 — basics_refresh 가 진실을 복원한다
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,),
                          classified=(NO_FEED,))
    scanner.restamp_cohorts([NO_FEED])
    assert _cohort_blocked(NO_FEED) is True, (
        "🔴 출처가 복원됐는데 코호트가 안 닫힌다 — 그 종목은 09:00 부터 KRX "
        "프레임을 받으면서 5전략의 매수 평가를 통과한다(미승인 매수 개방)"
    )


def test_s2_restamp_never_opens_a_closed_cohort(monkeypatch):
    """S2 — 재스탬프는 **닫힘 우세 단방향**이다(매수를 더 열 수 없다)."""
    scanner = _scanner()
    scanner.reset_tick_channel_state_for_test()
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,),
                          classified=(NO_FEED,))
    scanner.restamp_cohorts([NO_FEED])
    assert _cohort_blocked(NO_FEED) is True
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NO_FEED,),
                          classified=(NO_FEED,))
    scanner.restamp_cohorts([NO_FEED])
    assert _cohort_blocked(NO_FEED) is True, "재스탬프가 그날 안에 매수를 열었다"


def test_s3_restamp_leaves_nxt_true_open(monkeypatch):
    """🔴 S3 (절대 규칙 5) — 재스탬프가 `nxt_true` 매수를 닫지 않는다."""
    scanner = _scanner()
    scanner.reset_tick_channel_state_for_test()
    _patch_classification(monkeypatch, no_feed=(NO_FEED,),
                          provenance_ok=(NO_FEED, NXT_TRUE), classified=(NO_FEED, NXT_TRUE))
    scanner.restamp_cohorts([NO_FEED, NXT_TRUE])
    assert _cohort_blocked(NXT_TRUE) is False, (
        "🔴 `nxt_true` 매수가 닫혔다 — 5전략은 틱이 유일 매수 경로다"
    )


def test_s4_restamp_is_wired_into_both_polling_paths():
    """S4 — 5분 `subscribe_filtered_stocks` 와 120초 stale watcher **둘 다**.

    5분 경로만 있으면 `_scan_loop` 이 09:30 에야 생기므로 아침 창을 못 덮는다.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    scanner_src = (root / "src/engine/scanner.py").read_text(encoding="utf-8")
    watcher_src = (root / "src/engine/stale_watcher_core.py").read_text(encoding="utf-8")
    assert "restamp_cohorts(_channel_probe)" in scanner_src, (
        "`subscribe_filtered_stocks` 가 코호트를 재스탬프하지 않는다"
    )
    assert "restamp_cohorts(_classify_targets)" in watcher_src, (
        "120초 stale watcher 가 코호트를 재스탬프하지 않는다 — `_scan_loop`(09:30 "
        "생성)만으로는 08:08 진실 복원 뒤 아침 창을 덮지 못한다"
    )


# ===========================================================================
# G1~G2 (🔴 CRITICAL-2 부팅) — 계측기가 스탬프 뒤 값을 본다
# ===========================================================================
def test_g1_buy_gate_emits_once_per_clock_phase(monkeypatch, caplog):
    """🔴 G1 — `[tick_buy_gate]` 는 프리 창 1행 + 정규장 창 1행이다.

    종전에는 cap 키가 `"buy_gate"` 라 하루 1행이었고 그 1행은 07:59 사전 구독에서
    나왔다. 그 시각은 W2 도장 오염이 최악이라 매일 `unstamped=거의 전부` 를
    찍었다 — fail-open 을 재는 **유일한 계측기**가 결함과 무관하게 항상 같은 값을
    내니 아무것도 못 잡는다.
    """
    scanner = _scanner()
    scanner.reset_tick_channel_state_for_test()
    _set_mode("enforce")
    _patch_classification(monkeypatch, no_feed=(NO_FEED,), provenance_ok=(NO_FEED,),
                          classified=(NO_FEED,))
    caplog.set_level(logging.WARNING)

    import src.engine.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "datetime", _FrozenDatetime(_at(7, 59)))
    scanner.restamp_cohorts([NO_FEED])
    scanner.emit_tick_channel_config([NO_FEED])
    monkeypatch.setattr(scanner_mod, "datetime", _FrozenDatetime(_at(10, 0)))
    scanner.emit_tick_channel_config([NO_FEED])

    gate_rows = [r.message for r in caplog.records if "[tick_buy_gate]" in r.message]
    assert len(gate_rows) == 2, f"구간별 1행이 아니다: {gate_rows}"


def test_g2_buy_gate_counts_the_stamped_cohort(monkeypatch, caplog):
    """G2 — 카나리아가 **실제 스탬프 상태**를 센다(재스탬프가 emit 앞이다)."""
    scanner = _scanner()
    scanner.reset_tick_channel_state_for_test()
    _set_mode("enforce")
    _patch_classification(monkeypatch, no_feed=(NO_FEED,),
                          provenance_ok=(NO_FEED, NXT_TRUE), classified=(NO_FEED, NXT_TRUE))
    caplog.set_level(logging.WARNING)
    scanner.restamp_cohorts([NO_FEED, NXT_TRUE])
    scanner.emit_tick_channel_config([NO_FEED, NXT_TRUE])
    rows = [r.message for r in caplog.records if "[tick_buy_gate]" in r.message]
    assert rows and "stamped_no_feed=1" in rows[0] and "unstamped=0" in rows[0], rows


class _FrozenDatetime:
    """`scanner.datetime` 대체 — `now(tz)` 만 고정한다."""

    def __init__(self, moment):
        self._moment = moment

    def now(self, tz=None):
        return self._moment

    def __getattr__(self, name):
        return getattr(_dt.datetime, name)


# ===========================================================================
# E1~E2 (🟠 HIGH-1 부팅) — enforce_low 의 HIGH 제외
# ===========================================================================
def test_e1_enforce_low_keeps_legacy_unified_requests_unified(monkeypatch):
    """🔴 E1 — `enforce_low` 에서 레거시 통합 요청은 **재라우팅되지 않는다**.

    S1(단계적 롤아웃)은 HIGH(보유·익일청산)를 스코프 밖에 둔다. 그런데 세션의
    `subscribe` 첫 문장은 우선순위를 모르므로, 그 단계에서 통합 요청을 전용
    채널로 되돌리면 안전장치가 통째로 무력화된다 — 실측: `tick_tr_id_for(HIGH)`
    는 통합을 돌려주는데 세션은 전용 채널을 구독해 병행 dict 가 갈리고, 이어지는
    해제가 없는 튜플을 겨눠 KIS `OPSP0003` + 영구 고아를 만든다.
    """
    from src.realtime.websocket import _reroute_legacy_unified

    _set_mode("enforce_low")
    assert _reroute_legacy_unified(UNIFIED, NXT_TRUE) == UNIFIED


async def test_e2_pool_records_the_channel_it_actually_subscribes(monkeypatch, _pool_env):
    """🔴 E2 — 풀의 병행 dict 가 **세션이 실제로 구독한 채널**과 같다.

    재라우팅은 세션 안에서 일어나 호출자의 지역 변수를 못 바꾼다. 종전에는 풀이
    재라우팅 **전** 값을 기록해 `unsubscribe` 자기 교정 · 전환의 `old_tr_id` ·
    `stale_watcher_core._actual_or_desired_tick_tr_id` 가 전부 틀린 채널을 봤다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("enforce")
    # 레거시 호출자(`scheduler.py` 두 줄)가 하듯 **통합 채널**을 요청한다.
    await pool.subscribe(UNIFIED, NXT_TRUE, priority="HIGH", bypass_limit=True)
    tracked = pool._ticker_to_tr_id.get(NXT_TRUE)
    live = {tr for tr, tk in session._subscriptions if tk == NXT_TRUE}
    assert live and {tracked} == live, (
        f"🔴 풀 추적({tracked})과 세션 실제 구독({live})이 갈렸다 — 이 상태에서 "
        "해제하면 없는 튜플에 UNSUBSCRIBE 를 보내 KIS `OPSP0003` 을 받고 진짜 "
        "튜플은 영구 고아가 된다"
    )
    assert tracked != UNIFIED, (
        "`enforce` 인데 통합 채널이 그대로 구독됐다 — 「통합 구독 0」이 깨진다"
    )


# ===========================================================================
# T1~T2 (🟡 MEDIUM-2) — 전환 대상 필터
# ===========================================================================
def test_t1_probe_tuples_are_never_switched(monkeypatch, _pool_env):
    """T1 — cycle253 진단 프로브는 전환 대상이 아니다.

    전환하면 제외 등록이 **구 튜플 키**로 남아 새 튜플이 TICK 집계·stale
    watcher·delta 해제에 라이브처럼 섞인다(프로브 격리 계약 파손).
    """
    from src.realtime.websocket import register_probe_exclusion, reset_probe_exclusions

    pool, session = _pool_env
    reset_probe_exclusions()
    register_probe_exclusion(NXT_ONLY, NXT_TRUE)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    sw = _switch_mod()
    assert sw._is_switchable(NXT_ONLY, NXT_TRUE) is False, (
        "진단 프로브 튜플이 전환 대상이다 — 옮기면 제외 등록이 구 튜플 키로 남아 "
        "새 튜플이 TICK 집계·stale watcher·delta 해제에 라이브처럼 섞인다"
    )
    reset_probe_exclusions()


def test_t2_non_tick_routing_is_never_switched(_pool_env):
    """🔴 T2 — 체결통보(`H0STCNI0`) 라우팅이 전환 대상이 되면 안 된다.

    `wanted` 는 항상 전용 TICK 채널이라, 필터가 없으면 체결통보 구독이 전환
    대상으로 잡혀 루트 CLAUDE.md 의 「체결통보 구독 제거 금지」를 정면으로 깬다.
    """
    sw = _switch_mod()
    assert sw._is_switchable("H0STCNI0", "12345678-01") is False
    assert sw._is_switchable("H0UNMKO0", "005930") is False
    assert sw._is_switchable(NXT_ONLY, NXT_TRUE) is True


# ===========================================================================
# P1~P2 (🟡 MEDIUM-3) — 킬스위치로 빠져나가도 잔여를 남긴다
# ===========================================================================
@pytest.mark.parametrize("mode,dial,reason", [
    ("off", True, "mode"),
    ("observe", True, "mode"),
    ("enforce", False, "disabled"),
])
async def test_p1_window_missed_fires_even_when_the_switch_is_gated(
    monkeypatch, _pool_env, caplog, mode, dial, reason,
):
    """🔴 P1 — `off`/`observe`/전환 다이얼 off 로 빠져나가도 잔여를 센다.

    종전에는 그 셋이 `_maybe_emit_window_missed` 보다 먼저 return 해서, 창 안에
    `off` 를 누르면 일부는 KRX·일부는 NXT 인 채로 종일 남는데 로그에 한 줄도
    없었다. 운영자가 "몇 개가 안 옮겨졌는지" 를 알 수 없다.
    """
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode(mode)
    _set_switch_params(switch_enabled=dial, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    caplog.set_level(logging.WARNING)
    await _run_switch(_fake_scheduler({NXT_TRUE}), pool, _at(9, 30))
    rows = [r.message for r in caplog.records if "[tick_channel_switch_window_missed]" in r.message]
    assert rows and f"reason={reason}" in rows[0], (
        f"게이트({reason})로 빠져나가면서 미전환 잔여를 안 남겼다: {rows}"
    )


async def test_p2_window_missed_is_silent_while_still_inside_the_window(
    monkeypatch, _pool_env, caplog,
):
    """P2 — 창 안에서는 잔여가 정상이므로 침묵한다(거짓 경보 금지)."""
    pool, session = _pool_env
    _patch_classification(monkeypatch, no_feed=(), provenance_ok=(NXT_TRUE,),
                          classified=(NXT_TRUE,))
    _set_mode("off")
    _set_switch_params(switch_enabled=True, offset_secs=300)
    _seed_subscription(pool, session, NXT_TRUE, NXT_ONLY)
    caplog.set_level(logging.WARNING)
    await _run_switch(_fake_scheduler({NXT_TRUE}), pool, _at(8, 57))
    assert not [r for r in caplog.records if "window_missed" in r.message]


# ===========================================================================
# L1 (🟡 MEDIUM-3 clock) — 래치 영구화 차단
# ===========================================================================
def test_l1_day_revert_latch_is_not_permanent_when_the_clock_is_unreadable(monkeypatch):
    """🔴 L1 — `_kst_today()` 가 빈 문자열을 줘도 래치가 영구화되지 않는다.

    종전에는 그 경로에서 래치를 심으면 날짜 자기 리셋 조건(`_revert_wall_day and
    today and ...`)이 **영원히 거짓**이 되어, 프로세스 수명 내내 전 종목이 프리
    창 규칙에 고착됐다(§6-D 가 금지한 '영구 좌초 래치' 의 채널 축 부활).
    """
    clock = _clock()
    clock.reset_state_for_test()
    monkeypatch.setattr(clock, "_kst_today", lambda: "")
    clock.set_day_revert(DAY)
    assert clock._revert_wall_day == DAY.isoformat(), (
        "🔴 래치 날짜 키가 비어 있다 — 그러면 아래 자기 리셋 조건이 영원히 거짓이라 "
        "프로세스 수명 내내 전 종목이 프리 창 규칙에 고착된다"
    )
    monkeypatch.setattr(clock, "_kst_today", lambda: DAY.isoformat())
    assert clock.day_reverted(_at(10, 0)) is True
    monkeypatch.setattr(clock, "_kst_today", lambda: "2026-09-16")
    assert clock.day_reverted(
        _dt.datetime(2026, 9, 16, 10, 0, tzinfo=_at(9, 0).tzinfo)
    ) is False, "🔴 날짜가 넘어갔는데 원복 래치가 풀리지 않았다 — 영구 좌초다"


# ===========================================================================
# F1 (🟠 매수축 F-1) — 출처 조회 실패가 시끄럽다
# ===========================================================================
async def test_f1_provenance_failure_emits_a_warning(monkeypatch, caplog):
    """🔴 F1 — 출처 조회 실패는 **상관된 fail-open** 이라 WARNING 이어야 한다.

    `_provenance_ok` 가 비면 `_stamp_cohort` 가 무송출 코호트 **전체**를 미스탬프로
    남기고, 미스탬프는 매수 허용이라 5전략의 틱 매수가 그 코호트에 통째로 열린다
    (§6-D 의 "열림 오류는 종목별로 독립" 전제가 이 경로에서만 깨진다). 종전에는
    `logger.debug` 뿐이라 21:30 리포트(`pattern_by_level` 이 WARNING 이상만 집계)에
    한 글자도 안 떴다 — 되돌릴 수 없는 방향의 사고가 **무음**이었다.
    """
    import src.db.stock_master as stock_master
    from src.engine import no_feed_registry

    no_feed_registry.reset_state_for_test()

    async def _ok_map(tickers):
        return {t: False for t in tickers}

    async def _boom(tickers):
        raise RuntimeError("db down")

    monkeypatch.setattr(stock_master, "get_nxt_tradable_map", _ok_map, raising=False)
    monkeypatch.setattr(stock_master, "get_nxt_provenance_map", _boom, raising=False)
    caplog.set_level(logging.WARNING)
    await no_feed_registry.ensure_fresh([NO_FEED])
    rows = [r.message for r in caplog.records
            if "[no_feed_provenance_unavailable]" in r.message]
    assert rows, (
        "출처 조회 실패가 WARNING 으로 안 뜬다 — 매수 축이 코호트 전체에 열린 "
        "사실이 리포트에 한 글자도 안 남는다"
    )
