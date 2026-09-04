"""cycle250 Red — 계좌 리스크 평가 **타임아웃**(`wait_for`) + 후처리 wrapper.

명세 = team-leader 지시 (2026-09-05, cycle239 후속 A — HARNESS_CHANGELOG
2026-09-02 cycle239 행 "후속 = A 평가 타임아웃(wait_for 300s — hang 근본,
우선순위 1)").

## 확증된 결함

`watch_loop` 은 5분마다 `run_account_risk_watch_once(scheduler)` 를 **무기한**
await 한다. 그 안의 `balance_mod.get_balance()`(KIS 세마포어)·
`system_config.get_*`(asyncpg `pool.acquire()` — 타임아웃 인자 없음)는 어느
쪽도 시간 상한이 없어, 한 번 hang 하면 **루프가 영원히 그 자리에 선다**.

- cycle239 는 *소비자* 쪽(`is_soft_gated()`)에 신선도 fail-open(900s)을 넣어
  "block 로 얼어붙은 게이트가 매수를 영구 차단"하는 피해만 막았다. 루프 자체는
  되살아나지 않으므로 **그날 남은 평가가 전부 사라진다**.
- 더 나쁜 것은 침묵이다 — hang 은 예외가 아니라서 `_watch_task` 가 done 이
  되지 않고, cycle239 가 붙인 `[account_risk_watch_loop_died]` 도 **찍히지
  않는다**(죽은 게 아니라 멈춘 것). 관측 채널은 소비자 경로의 stale WARNING
  하나뿐이고, 그건 게이트가 **활성일 때만** 발화한다(다크런치 현행에선 0).
- 부팅 동기 1회(`boot_manager.py:399`)도 같은 hang 에 **부팅이 막힌다**.

## 처방 (명세 1~4)

- 모듈 상수 `_EVAL_TIMEOUT_SECS = 300` — 리터럴은 이 한 곳.
  계약 = `0 < _EVAL_TIMEOUT_SECS <= _WATCH_INTERVAL_SECS < _GATE_STALE_MAX_SECS`
  (타임아웃 후 **다음 평가가 stale 이전에 온다**).
- 신규 `run_account_risk_watch_once_guarded(scheduler)` =
  `asyncio.wait_for(run_account_risk_watch_once(scheduler), _EVAL_TIMEOUT_SECS)`.
  `asyncio.TimeoutError` 시 **기존 실패 분기와 동일한 후처리**(원시 `was_active`
  → `_gate_active=False` fail-open → `_evaluated_mono` 스탬프(같은 동기 블록,
  await 0 = cycle239 G-239-5 동형) → `_gate_state` level=error/reasons=["timeout"]
  → 활성이었으면 `released reason=eval_timeout` WARNING(cap 밖) →
  `[account_risk_eval_timeout]` WARNING 1회/일 cap) 후 **None** 반환.
- **다른 예외는 잡지 않는다** — 내부 `run_account_risk_watch_once` 의 기존
  except 가 이미 fail-open + `[account_risk_watch_failed]` 를 담당한다.
  wrapper 가 한 번 더 잡으면 같은 사건이 두 번 기록되고, 두 후처리가 서로 다른
  답을 쓸 수 있다.
- 호출부 2곳(`watch_loop` / `boot_manager`)만 guarded 로 교체.
  `run_account_risk_watch_once` **본체는 무변경**(AST ⑤ 가 HEAD 대비 봉인).

## 왜 타임아웃이 루프 안이 아니라 wrapper 인가

`wait_for` 의 타임아웃은 내부 코루틴을 **취소**로 끝낸다 — 취소는
`run_account_risk_watch_once` 의 `except Exception` 을 **지나가지 않는다**
(`CancelledError` 는 `BaseException`). 즉 내부 함수는 자기 취소를 후처리할
수 없고, 후처리(fail-open + 스탬프 + 관측)의 소유자는 wrapper 여야 한다.

## 결정성 seam

시각 축은 cycle239 와 동일하게 `_now_mono` monkeypatch 단일(`_Clock` 재사용 —
복붙 금지). **freeze_time 은 이 파일에서 쓰지 않는다** — freezegun 은 이
프로젝트에서 `time.monotonic` 까지 동결하고(cycle187), 이벤트 루프의 타이머가
그 시계를 쓰므로 `wait_for` 가 영영 만료되지 않아 60s 스위트 타임아웃으로
끌려간다. 그래서 cap 의 **날짜 롤오버**는 이 파일이 검증하지 않는다(같은 날
cap + `reset_state_for_test` 리셋까지만 — 날짜 키 자기 리셋 기전 자체는
`_peek_emit` 공용 경로라 cycle239 F-4a 가 이미 봉인).

일 카운터 접근자는 **`_eval_timeout_count()`** 로 고정한다(명세 5-T2 의 "택1,
명시"). `get_gate_state()` 에 키를 더하지 않는 쪽을 고른 이유 = cycle239 F-7e
가 그 dict 의 키 집합을 계약으로 못박았고, 진단용 카운터가 대시보드 폴링
응답에 섞이면 그 계약이 사이클마다 흔들린다.

## Red 상태 (착수 시점)

T1~T5·T7 은 `run_account_risk_watch_once_guarded` 부재로 FAIL,
T6 은 `watch_loop` 이 raw 를 부르므로 FAIL.
T6b(monkeypatch 호환 핀)만 현행에서도 통과한다 — 명세 6 의 "기존 테스트
무수정 통과"(cycle233 F2)를 이 파일 안에 명시적 계약으로 못박은 것이다.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from src.engine import account_risk_watcher as watcher

# 리그 재사용 — 복붙 금지(리그가 갈리면 게이트 계약이 조용히 쪼개진다, cycle239 선례).
from tests.unit.engine.test_cycle233_watcher_gate import (
    _fake_scheduler,
    _fake_strat,
    _patch_balance,
    _patch_thresholds,
)
from tests.unit.engine.test_cycle239_gate_freshness import _Clock

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.scheduler"
_MISSING = object()

# 진짜 구현 참조 — hang 더블로 갈아끼운 뒤 다시 되돌리기 위한 원본 핀.
_REAL_ONCE = watcher.run_account_risk_watch_once


# ---------------------------------------------------------------------------
# 리그
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_watcher_state():
    watcher.reset_state_for_test()
    watcher._watch_task = None
    yield
    watcher.reset_state_for_test()
    watcher._watch_task = None


def _guarded():
    """Red 단계에서 AttributeError 대신 '왜 없는지'가 보이게."""
    fn = getattr(watcher, "run_account_risk_watch_once_guarded", None)
    assert fn is not None, (
        "run_account_risk_watch_once_guarded 부재 (cycle250 미구현) — hang 하면 "
        "루프가 영원히 멈추고 그날 남은 평가가 전부 사라진다"
    )
    return fn


def _pin_clock(monkeypatch, clock: _Clock) -> None:
    monkeypatch.setattr(watcher, "_now_mono", clock, raising=False)


def _gated_scheduler():
    """실효 오픈리스크 10% — block_pct=6.0 에서 반드시 block."""
    pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
    return _fake_scheduler([_fake_strat("kojiro", pos, stop_of=lambda t: 40_000)])


def _patch_hang(monkeypatch, *, secs: float = 0.05) -> dict:
    """평가가 영원히 안 끝나는 상태(= 실제 hang) 재현 + 타임아웃 축소."""
    entered = {"n": 0}

    async def _hang(scheduler):
        entered["n"] += 1
        await asyncio.Event().wait()  # 취소로만 끝난다

    monkeypatch.setattr(watcher, "run_account_risk_watch_once", _hang)
    monkeypatch.setattr(watcher, "_EVAL_TIMEOUT_SECS", secs, raising=False)
    return entered


async def _evaluate_block(monkeypatch, clock: _Clock) -> None:
    """진짜 평가 1회로 게이트 활성(block) — 타임아웃 전 상태를 만든다."""
    _patch_balance(monkeypatch, net_asset=1_000_000)
    _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
    _pin_clock(monkeypatch, clock)
    monkeypatch.setattr(watcher, "run_account_risk_watch_once", _REAL_ONCE)
    await watcher.run_account_risk_watch_once(_gated_scheduler())


def _timeout_records(caplog):
    return [r for r in caplog.records
            if "[account_risk_eval_timeout]" in r.message]


def _release_timeout_records(caplog):
    return [r for r in caplog.records
            if "[account_risk_gate]" in r.message
            and "reason=eval_timeout" in r.message]


def _counter() -> int:
    fn = getattr(watcher, "_eval_timeout_count", None)
    assert callable(fn), (
        "_eval_timeout_count() 접근자 부재 — 일 카운터가 어디에도 노출되지 "
        "않으면 cap 이 삼킨 2회차 이후 타임아웃이 관측 불가다"
    )
    return fn()


def _failed_records(caplog):
    """cycle250 적대 검증 M23 — `[account_risk_watch_failed]` 행 필터."""
    return [r for r in caplog.records if "[account_risk_watch_failed]" in r.message]


def _patch_inner_failure(monkeypatch) -> None:
    """cycle250 적대 검증 M23 — 내부 평가가 일반 예외로 실패하는 상태 재현.

    `run_account_risk_watch_once` 를 진짜 구현으로 되돌리고(hang 더블이 앞서
    설치돼 있을 수 있음) `get_balance` 가 던지게 해 기존 `watch_failed` cap
    을 소비시킨다 — `eval_timeout` cap 과 키가 공유되면 이 소비가 타임아웃
    관측까지 침묵시킨다(M23).
    """
    from src.api import balance as balance_mod

    async def _boom(afhr_flpr="N"):
        raise ValueError("KIS 응답 파싱 실패")

    _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
    monkeypatch.setattr(balance_mod, "get_balance", _boom)
    monkeypatch.setattr(watcher, "run_account_risk_watch_once", _REAL_ONCE)


# ===========================================================================
# T1 — 타임아웃 후처리 (핵심 결함)
# ===========================================================================
class TestT1TimeoutPostProcessing:

    async def test_t1_eval_when_hangs_then_timeout_fail_open_stamped_and_warned(
        self, monkeypatch, caplog,
    ):
        """T1 (현행 FAIL) — hang 은 타임아웃으로 끝나고 실패 분기와 같은 후처리를 받는다."""
        clock = _Clock(t=70_000.0)
        _pin_clock(monkeypatch, clock)
        entered = _patch_hang(monkeypatch)
        assert getattr(watcher, "_evaluated_mono", _MISSING) is None, (
            "사전 조건 — 미평가 상태에서 시작"
        )

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            result = await _guarded()(_gated_scheduler())

        assert entered["n"] == 1, "내부 평가가 호출조차 안 됐다(더블 배선 오류)"
        assert result is None, "타임아웃은 None 반환(실패 분기와 동일 계약)"
        assert watcher._gate_active is False, (
            "타임아웃이 fail-open 이 아니면 hang 이 곧 '영구 매수 차단'이다(D2 위반)"
        )
        stamp = getattr(watcher, "_evaluated_mono", _MISSING)
        assert isinstance(stamp, float) and stamp == clock.t, (
            f"타임아웃도 '살아 있음' 스탬프를 남겨야 한다 — 미갱신이면 소비자 "
            f"경로가 stale 로 오독하고 두 채널이 같은 사건을 두 번 센다: {stamp!r}"
        )

        st = watcher._gate_state
        assert st.get("level") == "error", st
        assert st.get("reasons") == ["timeout"], (
            f"사유가 'timeout' 으로 특정되지 않으면 hang 과 KIS 장애가 "
            f"같은 서명으로 섞인다: {st}"
        )
        assert st.get("open_risk_pct") is None, st
        evaluated_at = st.get("evaluated_at")
        assert isinstance(evaluated_at, str) and "+09:00" in evaluated_at, (
            f"KST 명시 ISO 여야 한다: {evaluated_at!r}"
        )

        hits = _timeout_records(caplog)
        assert len(hits) == 1, f"타임아웃 관측 1행이어야 한다 — {len(hits)}행"
        rec = hits[0]
        assert rec.levelno == logging.WARNING, "hang 은 WARNING(D2 LOUD)"
        assert "timeout_secs=" in rec.message, rec.message
        assert "timeout_secs=300" not in rec.message, (
            f"임계가 하드코딩됐다 — 실제 사용 값(monkeypatch 0.05)이 아니라 "
            f"상수 리터럴을 찍고 있다: {rec.message}"
        )
        assert "count=1" in rec.message, (
            f"카운터가 로그보다 늦게 증가하면 첫 행이 count=0 으로 나온다: "
            f"{rec.message}"
        )

    async def test_t1b_eval_when_hangs_then_gate_state_snapshot_is_stale_free(
        self, monkeypatch,
    ):
        """T1(b) — 타임아웃 직후 스냅샷은 '살아 있는 실패'(stale=False)로 읽혀야 한다."""
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_hang(monkeypatch)
        await _guarded()(_gated_scheduler())

        st = watcher.get_gate_state()
        assert st.get("stale") is False, (
            "타임아웃이 스탬프를 안 남기면 '루프 생존 중 타임아웃'이 '루프 사멸'로 "
            "오독된다(cycle239 F-10 동형)"
        )
        assert st.get("effective_gated") is False
        assert st.get("level") == "error"
        assert watcher.is_soft_gated() is False

    async def test_e26_timeout_when_gate_inactive_then_no_release_log(
        self, monkeypatch, caplog,
    ):
        """cycle250 적대 검증 M26 — 비활성 게이트 타임아웃은 해제 전이 로그 0.

        `if was_active:` 가 `if True:` 로 뒤집혀도(다크런치 상시 `_gate_active`
        =False) 기존 테스트가 전부 통과하던 escape — 풀린 적 없는 게이트에
        `released reason=eval_timeout` 이 찍히면 '왜 풀렸나' grep 이 매 hang
        마다 오염된다.
        """
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_hang(monkeypatch)
        assert watcher._gate_active is False, "사전 조건 — 다크런치 상시 비활성"

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await _guarded()(_gated_scheduler())

        assert len(_timeout_records(caplog)) == 1
        assert _release_timeout_records(caplog) == [], (
            "풀린 적 없는 게이트에 `released reason=eval_timeout` 이 찍혔다"
        )


# ===========================================================================
# T2 — 관측 cap (1회/일) + 일 카운터
# ===========================================================================
class TestT2DailyCap:

    async def test_t2_timeout_when_repeats_same_day_then_warns_once_counter_grows(
        self, monkeypatch, caplog,
    ):
        """T2 (현행 FAIL) — 폭주 금지 1회/일, 그러나 사실(횟수)은 지워지지 않는다."""
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_hang(monkeypatch)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await _guarded()(_gated_scheduler())
            assert _counter() == 1
            clock.advance(300)
            await _guarded()(_gated_scheduler())

        assert len(_timeout_records(caplog)) == 1, (
            f"같은 날 2회차가 또 찍혔다 — 5분 주기 hang 이면 하루 144행 폭주: "
            f"{[r.message for r in _timeout_records(caplog)]}"
        )
        assert _counter() == 2, (
            "cap 이 로그만이 아니라 카운터까지 삼키면 '몇 번 멈췄나'가 사라진다"
        )
        assert watcher._evaluated_mono == clock.t, "2회차도 스탬프 갱신"

    async def test_t2b_counter_when_state_reset_then_zero(self, monkeypatch):
        """T2(b) — `reset_state_for_test()` 가 카운터도 리셋(테스트 격리 계약)."""
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_hang(monkeypatch)
        await _guarded()(_gated_scheduler())
        assert _counter() == 1

        watcher.reset_state_for_test()
        assert _counter() == 0, (
            "카운터가 모듈 전역인데 리셋에 동행하지 않으면 테스트 간 누설된다"
        )

    async def test_t2c_cap_when_logging_raises_then_cap_unconsumed(
        self, monkeypatch, caplog,
    ):
        """T2(c) — peek→로그→mark. 관측 자기실패가 그날 관측을 지우지 않는다."""
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_hang(monkeypatch)

        original = watcher.logger.warning
        calls = {"n": 0}

        def _boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("로그 싱크 장애")

        monkeypatch.setattr(watcher.logger, "warning", _boom)
        await _guarded()(_gated_scheduler())
        assert calls["n"] >= 1, "타임아웃 경로가 WARNING 을 시도조차 안 했다"

        monkeypatch.setattr(watcher.logger, "warning", original)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await _guarded()(_gated_scheduler())
        assert len(_timeout_records(caplog)) == 1, (
            "mark-before-log 이면 cap 이 이미 소비돼 그날 내내 무음이 된다"
            "(cycle226 D-3 동형)"
        )

    async def test_e23a_failure_then_timeout_same_day_both_logged(
        self, monkeypatch, caplog,
    ):
        """cycle250 적대 검증 M23 — [실패 → 타임아웃] 순서, 두 마커 모두 발화.

        `_peek_emit("eval_timeout")`/`_mark_emitted("eval_timeout")` 을
        `"watch_failed"` 로 바꿔치기해도(cap 키 공유) 기존 스위트는 전부
        통과하던 escape — 같은 날 KIS 실패 1건이 그 뒤 hang 마커를 침묵시키면
        안 된다(cycle239 x3 동형 공백).
        """
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            _patch_inner_failure(monkeypatch)
            await _guarded()(_gated_scheduler())  # watch_failed cap 소비
            clock.advance(300)
            _patch_hang(monkeypatch)
            await _guarded()(_gated_scheduler())  # 타임아웃

        assert len(_failed_records(caplog)) == 1
        assert len(_timeout_records(caplog)) == 1, (
            "같은 날 KIS 실패 1건 뒤의 hang 이 무음이 됐다 — cap 키가 "
            "`watch_failed` 와 공유되고 있다"
        )

    async def test_e23b_timeout_then_failure_same_day_both_logged(
        self, monkeypatch, caplog,
    ):
        """cycle250 적대 검증 M23(역순) — [타임아웃 → 실패] 도 서로 침묵시키지 않는다."""
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            _patch_hang(monkeypatch)
            await _guarded()(_gated_scheduler())  # 타임아웃 cap 소비
            clock.advance(300)
            _patch_inner_failure(monkeypatch)
            await _guarded()(_gated_scheduler())  # 내부 실패

        assert len(_timeout_records(caplog)) == 1
        assert len(_failed_records(caplog)) == 1, (
            "hang 1건 뒤의 KIS 실패가 무음이 됐다 — cap 키 공유"
        )

    async def test_e25_counter_when_day_changes_then_restarts_at_one(
        self, monkeypatch, caplog,
    ):
        """cycle250 적대 검증 M25 — `_bump_eval_timeout_count` 날짜 롤오버.

        `if _eval_timeout_count_day != today:` 를 `if False:` 로 바꿔도 기존
        스위트는 전부 통과하던 escape — 전일 잔존 카운터가 오늘로 이월되면
        1회/일 WARNING 의 `count=` 가 '오늘 몇 번'이 아니라 '프로세스 수명
        동안 몇 번'이 된다(며칠 상주 프로세스에서 치명).
        """
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_hang(monkeypatch)
        monkeypatch.setattr(watcher, "_eval_timeout_count_day", "2000-01-01")
        monkeypatch.setattr(watcher, "_eval_timeout_count_today", 7)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await _guarded()(_gated_scheduler())

        assert _counter() == 1, (
            f"어제 7회가 오늘로 이월됐다(실측 {_counter()}) — '오늘 몇 번' 이 아니라 "
            "'프로세스 수명 동안 몇 번' 이 된다"
        )
        assert "count=1" in _timeout_records(caplog)[0].message


# ===========================================================================
# T3 — 활성 게이트 해제 전이 (cap 밖)
# ===========================================================================
class TestT3ActiveGateRelease:

    async def test_t3_timeout_when_gate_active_then_release_logged(
        self, monkeypatch, caplog,
    ):
        """T3 (현행 FAIL) — 무음 해제 금지. 'block 이 왜 풀렸나'가 남아야 한다."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        assert watcher.is_soft_gated() is True

        clock.advance(300)
        _patch_hang(monkeypatch)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await _guarded()(_gated_scheduler())

        rel = _release_timeout_records(caplog)
        assert len(rel) == 1, (
            f"활성 게이트가 타임아웃으로 풀렸는데 전이 로그가 없다: "
            f"{[r.message for r in caplog.records]}"
        )
        assert rel[0].levelno == logging.WARNING, (
            "평가 불능으로 인한 해제는 WARNING(`released reason=eval_failure` 동형)"
        )
        assert "released" in rel[0].message, (
            "운영 grep 키 `[account_risk_gate] released` 를 벗어나면 "
            "'왜 풀렸나' 전수 검색에서 빠진다"
        )
        assert watcher.is_soft_gated() is False

    async def test_t3b_release_when_reoccurs_then_not_capped_but_marker_is(
        self, monkeypatch, caplog,
    ):
        """T3(b) — 전이 로그는 cap **밖**, 타임아웃 마커는 cap **안**(두 채널 분리).

        전이는 희소 사건이고 flapping 자체가 신호다(cycle233 F5). 반대로 마커는
        5분마다 재발할 수 있어 반드시 cap 이 필요하다 — 둘을 같은 cap 에 묶으면
        한쪽이 다른 쪽을 침묵시킨다(cycle239 F-8c 동형).
        """
        clock = _Clock()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            # 1회차 — 활성 → 타임아웃
            await _evaluate_block(monkeypatch, clock)
            clock.advance(300)
            _patch_hang(monkeypatch)
            await _guarded()(_gated_scheduler())
            # 재활성 (진짜 평가 1회) → 2회차 타임아웃
            clock.advance(300)
            await _evaluate_block(monkeypatch, clock)
            assert watcher.is_soft_gated() is True
            clock.advance(300)
            _patch_hang(monkeypatch)
            await _guarded()(_gated_scheduler())

        assert len(_release_timeout_records(caplog)) == 2, (
            "해제 전이가 cap 에 걸렸다 — 두 번째 '왜 풀렸나'가 통째로 사라진다"
        )
        assert len(_timeout_records(caplog)) == 1, (
            "타임아웃 마커가 cap 밖이면 5분 주기 hang 이 하루 144행을 찍는다"
        )


# ===========================================================================
# T4 — 정상 평가 투명성 (wrapper 는 성공 경로를 건드리지 않는다)
# ===========================================================================
class TestT4TransparentOnSuccess:

    async def test_t4a_guarded_when_inner_returns_then_passthrough_untouched(
        self, monkeypatch, caplog,
    ):
        """T4(a) — 반환값은 그대로, 상태는 무접촉, 관측 0행."""
        sentinel = {"level": "ok", "reasons": [], "sentinel": object()}

        async def _fast(scheduler):
            return sentinel

        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        monkeypatch.setattr(watcher, "run_account_risk_watch_once", _fast)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            result = await _guarded()(_gated_scheduler())

        assert result is sentinel, "wrapper 가 반환값을 갈아치웠다"
        assert watcher._gate_active is False
        assert getattr(watcher, "_evaluated_mono", _MISSING) is None, (
            "wrapper 가 성공 경로에서 스탬프를 덧쓰면 기록자가 둘이 된다"
            "(cycle239 단일 기록자 계약)"
        )
        assert _timeout_records(caplog) == []
        assert _release_timeout_records(caplog) == []

    async def test_t4b_guarded_when_real_evaluation_then_state_matches_raw(
        self, monkeypatch,
    ):
        """T4(b) — 실제 평가를 guarded 로 통과시켜도 raw 호출과 상태가 같다."""
        _patch_balance(monkeypatch, net_asset=1_000_000)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
        clock = _Clock()
        _pin_clock(monkeypatch, clock)

        via_guarded = await _guarded()(_gated_scheduler())
        guarded_state = dict(watcher._gate_state)
        guarded_active = watcher._gate_active
        guarded_stamp = watcher._evaluated_mono

        watcher.reset_state_for_test()
        via_raw = await watcher.run_account_risk_watch_once(_gated_scheduler())
        raw_state = dict(watcher._gate_state)

        assert via_guarded is not None and via_raw is not None
        assert guarded_active is True and watcher._gate_active is True
        assert guarded_stamp == clock.t
        compared = ("level", "reasons", "open_risk_pct", "open_risk_proxy_pct",
                    "net_asset", "over_cap_count", "warn_pct", "block_pct")
        for key in compared:
            assert guarded_state.get(key, _MISSING) == raw_state.get(key, _MISSING), (
                f"guarded 경유가 raw 와 다른 판정을 만들었다: {key} "
                f"{guarded_state.get(key)!r} != {raw_state.get(key)!r}"
            )


# ===========================================================================
# T5 — 타임아웃 아닌 예외는 wrapper 소관이 아니다
# ===========================================================================
class TestT5NonTimeoutErrors:

    async def test_t5_inner_failure_when_general_exception_then_only_watch_failed(
        self, monkeypatch, caplog,
    ):
        """T5 (핵심) — 내부 일반 예외는 기존 경로만 1건, 타임아웃 마커 0건."""
        from src.api import balance as balance_mod

        async def _boom(afhr_flpr="N"):
            raise ValueError("KIS 응답 파싱 실패")

        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
        monkeypatch.setattr(balance_mod, "get_balance", _boom)
        monkeypatch.setattr(watcher, "run_account_risk_watch_once", _REAL_ONCE)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            result = await _guarded()(_gated_scheduler())

        assert result is None
        failed = [r for r in caplog.records
                  if "[account_risk_watch_failed]" in r.message]
        assert len(failed) == 1, (
            f"기존 실패 관측이 1건이어야 한다(중복 로깅 금지): "
            f"{[r.message for r in failed]}"
        )
        assert _timeout_records(caplog) == [], (
            "일반 예외를 타임아웃으로 오분류하면 hang 통계가 오염된다"
        )
        st = watcher._gate_state
        assert st.get("level") == "error"
        assert st.get("reasons") != ["timeout"], st
        assert "ValueError" in str(st.get("reasons")) or "파싱" in str(st.get("reasons")), st
        assert watcher._gate_active is False
        assert watcher._evaluated_mono == clock.t

    async def test_t5b_guarded_when_inner_raises_directly_then_propagates(
        self, monkeypatch, caplog,
    ):
        """T5(b) — wrapper 는 `TimeoutError` **만** 잡는다(광범위 except 금지).

        내부 함수는 자기 예외를 이미 흡수한다. wrapper 가 한 겹 더 잡으면
        (a) 같은 사건이 두 번 기록되고 (b) 내부가 못 잡은 진짜 이상(배선
        오류·프로그래밍 오류)이 `[account_risk_watch_loop_died]` 로도 보이지
        않게 조용히 삼켜진다.
        """
        async def _explode(scheduler):
            raise ValueError("배선 오류")

        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        monkeypatch.setattr(watcher, "run_account_risk_watch_once", _explode)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            with pytest.raises(ValueError):
                await _guarded()(_gated_scheduler())

        assert _timeout_records(caplog) == []
        assert watcher._gate_active is False
        assert getattr(watcher, "_evaluated_mono", _MISSING) is None, (
            "타임아웃이 아닌 예외에 wrapper 가 후처리를 실행했다"
        )
        assert watcher._gate_state.get("level") == "ok", watcher._gate_state


# ===========================================================================
# T6 — 호출부 교체 (루프는 타임아웃 뒤에도 계속 돈다)
# ===========================================================================
class TestT6CallSites:

    @staticmethod
    def _fast_sleep(monkeypatch):
        async def _sleep(_secs):
            return None

        monkeypatch.setattr(watcher.asyncio, "sleep", _sleep)

    async def test_t6_watch_loop_when_timeout_then_next_iteration_still_runs(
        self, monkeypatch,
    ):
        """T6 (현행 FAIL) — 루프가 guarded 를 부르고, 타임아웃 뒤에도 다음 주기가 온다.

        타임아웃이 루프를 끊으면 시정의 목적(그날 남은 평가 보존)이 사라진다.
        """
        calls = {"n": 0}
        sched = SimpleNamespace(_running=True,
                                registry=SimpleNamespace(all=lambda: []))

        async def _fake_guarded(s):
            calls["n"] += 1
            if calls["n"] >= 3:
                sched._running = False
            return None  # 타임아웃 반환값과 동일

        monkeypatch.setattr(watcher, "run_account_risk_watch_once_guarded",
                            _fake_guarded, raising=False)
        self._fast_sleep(monkeypatch)
        await asyncio.wait_for(watcher.watch_loop(sched), timeout=5.0)

        assert calls["n"] == 3, (
            f"`watch_loop` 이 guarded 를 경유하지 않거나 반복이 끊겼다 "
            f"(실측 {calls['n']}회) — raw 직접 호출이면 hang 상한이 없다"
        )

    async def test_t6b_watch_loop_when_raw_patched_then_still_reached(
        self, monkeypatch,
    ):
        """T6(b) — 명세 6 계약: guarded 는 raw 를 **런타임 모듈 속성**으로 찾는다.

        `from ... import` 로 이름을 박아두면 기존 회귀(cycle233 F2 등)가 raw 를
        monkeypatch 해도 guarded 가 진짜 구현을 부른다 — 그 테스트들이 조용히
        실제 KIS/DB 경로로 새는 것이 아니라, 애초에 의도한 더블이 무시된다.
        현행에서도 통과하는 **호환 핀**이다.
        """
        calls = {"n": 0}
        sched = SimpleNamespace(_running=True,
                                registry=SimpleNamespace(all=lambda: []))

        async def _fake_once(s):
            calls["n"] += 1
            if calls["n"] >= 2:
                sched._running = False

        monkeypatch.setattr(watcher, "run_account_risk_watch_once", _fake_once)
        self._fast_sleep(monkeypatch)
        await asyncio.wait_for(watcher.watch_loop(sched), timeout=5.0)

        assert calls["n"] >= 2, (
            "raw monkeypatch 가 guarded 를 통과하지 못했다 — 이름 조회가 "
            "import 시점에 고정됐다(기존 회귀 테스트 무력화)"
        )


# ===========================================================================
# T7 — 관측 실패는 행위를 바꾸지 않는다
# ===========================================================================
class TestT7ObservationIsolation:

    async def test_t7_timeout_when_logger_raises_then_state_identical(
        self, monkeypatch,
    ):
        """T7 (현행 FAIL) — 로거가 죽어도 fail-open + 스탬프 결과는 동일하다."""
        clock = _Clock()

        # (a) 로거 정상 — 기준 상태 채집
        await _evaluate_block(monkeypatch, clock)
        clock.advance(300)
        _patch_hang(monkeypatch)
        await _guarded()(_gated_scheduler())
        expected = (watcher._gate_active, watcher._evaluated_mono,
                    watcher._gate_state.get("level"),
                    watcher._gate_state.get("reasons"))

        # (b) 로거 폭사 — 같은 시나리오 재현 (활성 게이트 → 타임아웃)
        watcher.reset_state_for_test()
        clock2 = _Clock()
        await _evaluate_block(monkeypatch, clock2)
        clock2.advance(300)
        _patch_hang(monkeypatch)

        def _boom(*args, **kwargs):
            raise RuntimeError("로그 싱크 장애")

        monkeypatch.setattr(watcher.logger, "warning", _boom)
        monkeypatch.setattr(watcher.logger, "info", _boom)
        result = await _guarded()(_gated_scheduler())

        assert result is None
        actual = (watcher._gate_active, watcher._evaluated_mono,
                  watcher._gate_state.get("level"),
                  watcher._gate_state.get("reasons"))
        assert actual == expected, (
            f"관측 실패가 행위를 바꿨다(관측기 자기실패 ≠ 게이트 상태 변화): "
            f"{actual} != {expected}"
        )
        assert watcher.is_soft_gated() is False


# ===========================================================================
# T8(E28) — 외부 취소는 타임아웃 후처리를 가로채지 않는다
# ===========================================================================
class TestE28CancelPropagates:
    """cycle250 적대 검증 M28 — `except (TimeoutError, CancelledError)` escape.

    G-250-4b 는 종전 `names & {"TimeoutError"}` ∧ `Exception/BaseException`
    부재만 검사해 `CancelledError` 동반 포착을 통과시켰다(docstring 의
    "취소까지 삼켜 stop 이 안 먹는다" 주장이 행위 테스트로 뒷받침되지
    않던 공백). 뮤턴트 하에서 첫 프로브 실행이 280s+ hang 했다 — teardown 의
    cancel 까지 삼켜 루프가 종료 불능이 된 것으로, 운영 shutdown 취소가
    삼켜지면 `_running` False 확인까지 최대 `_EVAL_TIMEOUT_SECS` 지연되는
    바로 그 위험의 재현이다. e28b 는 `_patch_hang(secs=0.3)` + `finally`
    `sched._running=False` 로 teardown 을 유계한다.
    """

    async def test_e28a_guarded_when_cancelled_then_raises_without_postprocessing(
        self, monkeypatch, caplog,
    ):
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_hang(monkeypatch, secs=30.0)  # 타임아웃이 먼저 오지 않게

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            task = asyncio.ensure_future(_guarded()(_gated_scheduler()))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert watcher._evaluated_mono is None, "취소를 타임아웃으로 후처리했다"
        assert watcher._gate_state.get("level") == "ok"
        assert _timeout_records(caplog) == []
        assert _counter() == 0

    async def test_e28b_watch_loop_when_cancelled_mid_eval_then_stops(
        self, monkeypatch,
    ):
        _patch_hang(monkeypatch, secs=0.3)  # 뮤턴트가 취소를 삼켜도 teardown 이 유계

        async def _fast_sleep(_secs):
            return None

        monkeypatch.setattr(watcher.asyncio, "sleep", _fast_sleep)
        sched = SimpleNamespace(_running=True,
                                registry=SimpleNamespace(all=lambda: []))
        task = asyncio.ensure_future(watcher.watch_loop(sched))
        try:
            for _ in range(3):
                await asyncio.wait({task}, timeout=0)  # 첫 guarded 진입까지 양보
            task.cancel()
            done, _pending = await asyncio.wait({task}, timeout=1.0)
            assert task in done and task.cancelled(), (
                "취소된 감시 루프가 1초 안에 끝나지 않았다 — guarded 가 "
                "CancelledError 를 삼켜 다음 주기로 계속 돈다"
            )
        finally:
            sched._running = False  # 삼킨 경우에도 다음 타임아웃 뒤 자연 종료
            await asyncio.wait({task}, timeout=3.0)
