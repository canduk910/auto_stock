"""cycle239 Red — 계좌 SOFT Σ상한 게이트 **신선도**(stale → fail-open).

명세 = `_workspace/red/cycle239_gate_freshness_spec.md` (team-leader, 2026-09-02).

## 확증된 결함 (§1)

`account_risk_watcher.is_soft_gated()` 본문은 `return _gate_active` 한 줄이라
**마지막 평가가 언제였는지를 보지 않는다**. 감시 루프(`watch_loop`, 5분)가 죽거나
hang 하면 그 판정이 그대로 **동결**되고, 동결값이 block 이면 7전략 신규 매수가
영구 차단된다(현행은 `block_pct=None` 다크런치라 잠재 — DB `account_risk_block_pct=6.0`
을 켜는 순간 활성). `evaluated_at` 은 지금까지 어디서도 읽히지 않는 죽은 필드다.

## 처방 (§2, 사용자 09-02 승인)

- 판정 = **monotonic 단일 소스** `_evaluated_mono`(성공·실패 공통 스탬프).
  `_GATE_STALE_MAX_SECS = _WATCH_INTERVAL_SECS * 3`(=900) **초과**면 stale.
- stale·스탬프 None·판정 예외 → `is_soft_gated()` **False**(fail-open + LOUD).
- 관측 `[account_risk_gate] released reason=stale …` **WARNING 1회/일**
  (cap 키 `gate_stale`, 날짜 키 자기 리셋, **peek → 로그 → mark**).
- `get_gate_state()` 는 `stale`/`age_secs`/`stale_max_secs`/`effective_gated` 4키를
  더하되 `level` 은 **마지막 평가값 그대로 보존**(사실과 행위를 나란히) + **무발화**.
- `run_once` 는 양 분기에서 `was_active = _gate_active`(**cycle239-R1** — 원시값,
  아래 참조) + 스탬프 갱신.
- `ensure_watch_loop` 은 `add_done_callback` 으로 루프 사멸/종료를 LOUD 하게 남긴다.

## cycle239-R1 — 적대 검증 확증 시정 (2026-09-02, 착수 직후)

최초 구현은 `was_active = is_soft_gated()`(fresh-aware) 였다. 반박자 3렌즈+tester 가
독립 수렴한 결함: 이러면 **기록자가 소비자용 stale WARNING/cap 을 선소비**한다 —
정상 일일 라이프사이클(20:10 `_running=False` → 루프 정상 종료 → 밤새 `_gate_active`
잔존 → 익일 07:55 부팅 동기 평가)마다 `released reason=stale`(감시 정지/사멸 의심
WARNING)이 **거짓** 발화했고, 그 cap 소비가 그날 장중 진짜 hang 이 나도 소비자
경로의 stale WARNING 을 침묵시켰다(D2 LOUD 계약이 가장 필요한 순간에만 빠짐).
시정 = `was_active` 를 원시 `_gate_active` 로 환원 — 기록자는 `is_soft_gated()`/
`_emit_stale_release` 를 전혀 호출하지 않는다(F-8/F-8b 재설계 + F-8c/F-5b 신규,
아래 §4.1 표 갱신). 대가는 재개 전이 로그가 raw 값 기준(재개해도 `entered` 강제
불가)이라는 것뿐 — 실제 stale 탐지는 소비자 경로가 여전히 담당한다.

## 결정성 seam (§2.7)

시각 축은 **`_now_mono` monkeypatch 단일**(`_Clock`). freezegun 은 이 프로젝트에서
`time.monotonic` 까지 동결하므로(cycle187) 판정 시각은 seam 으로만 움직인다.
날짜 키(cap 리셋) 검증만 `freeze_time` 을 쓰되 **동기 함수만** 그 안에서 부른다.
모듈 전역 상태라 `_reset_watcher_state` autouse 픽스처를 이 파일에 재정의한다
(tests/unit/engine 에는 conftest 가 없다). 루트 autouse 2종
(`_neutralize_call_auction_gate`/`_pin_pre_market_clock`)은 watcher 무간섭.

## Red 상태 (착수 시점, R1 이전)

F-1/F-3/F-4/F-5/F-7/F-8/F-9(스탬프)/F-10/F-11/F-12/F-13 은 착수 시점 코드에서
FAIL 했다(신선도 개념 자체가 부재). F-2 는 경계 초과분에서, F-6/F-14 는 회귀
가드로 통과했다. **R1** 이 F-8/F-8b 를 raw 기준으로 재설계하고 F-8c(g3)/F-5b(g4)
를 신규 추가했다 — 상세는 위 "cycle239-R1" 절.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

from src.engine import account_risk_watcher as watcher

# 리그 재사용 — 복붙 금지(두 파일의 리그가 갈리면 게이트 계약이 조용히 쪼개진다).
from tests.unit.engine.test_cycle233_watcher_gate import (
    _fake_scheduler,
    _fake_strat,
    _patch_balance,
    _patch_thresholds,
)

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.scheduler"
_MISSING = object()
_STALE_MAX_EXPECTED = 900  # = _WATCH_INTERVAL_SECS(300) × 3


# ---------------------------------------------------------------------------
# 리그
# ---------------------------------------------------------------------------
class _Clock:
    """`_now_mono` seam 대역 — 임의 전진 + 호출 카운팅(fast path 실증용)."""

    def __init__(self, t: float = 10_000.0) -> None:
        self.t = float(t)
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return self.t

    def advance(self, secs: float) -> None:
        self.t += float(secs)


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    watcher.reset_state_for_test()
    watcher._watch_task = None
    yield
    watcher.reset_state_for_test()
    watcher._watch_task = None


def _pin_clock(monkeypatch, clock: _Clock) -> None:
    """판정 시각 seam 고정. Red 단계(`_now_mono` 부재)에서도 죽지 않게 raising=False."""
    monkeypatch.setattr(watcher, "_now_mono", clock, raising=False)


def _gated_scheduler():
    """실효 오픈리스크 10% — block_pct=6.0 에서 반드시 block."""
    pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
    return _fake_scheduler([_fake_strat("kojiro", pos, stop_of=lambda t: 40_000)])


def _ok_scheduler():
    """실효 오픈리스크 1% — 판정 ok."""
    pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
    return _fake_scheduler([_fake_strat("kojiro", pos, stop_of=lambda t: 49_000)])


async def _evaluate_block(monkeypatch, clock: _Clock) -> None:
    """block 판정 1회 — 게이트 활성 + 스탬프 기록."""
    _patch_balance(monkeypatch, net_asset=1_000_000)
    _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
    _pin_clock(monkeypatch, clock)
    await watcher.run_account_risk_watch_once(_gated_scheduler())


def _stale_records(caplog):
    return [r for r in caplog.records
            if "[account_risk_gate]" in r.message and "reason=stale" in r.message]


# ===========================================================================
# F-1 / F-2 — 판정식 (핵심 결함 + 경계)
# ===========================================================================
class TestF1F2StaleVerdict:

    @pytest.mark.asyncio
    async def test_f1_gate_when_evaluation_is_stale_then_fail_open(self, monkeypatch):
        """F-1 (현행 FAIL) — 감시 정지로 900s 초과 묵은 block 판정은 소비되지 않는다."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        assert watcher.is_soft_gated() is True, "block 판정 직후엔 게이트가 서야 한다"

        clock.advance(901)
        assert watcher.is_soft_gated() is False, (
            "stale(>900s) 판정은 fail-open 이어야 한다 — 현행은 _gate_active 만 "
            "돌려주므로 감시 루프 사멸 시 매수가 영구 차단된다"
        )

    @pytest.mark.asyncio
    async def test_f2_gate_when_age_at_threshold_then_boundary_is_strictly_greater(
        self, monkeypatch,
    ):
        """F-2 — 경계는 '초과'. 900.0 은 fresh, 900.001 부터 stale."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        base = clock.t

        clock.t = base + 899
        assert watcher.is_soft_gated() is True
        clock.t = base + 900.0
        assert watcher.is_soft_gated() is True, "임계 정각(900.0)은 fresh"
        clock.t = base + 900.001
        assert watcher.is_soft_gated() is False, "임계 초과는 stale = fail-open"


# ===========================================================================
# F-3 / F-4 / F-5 — 관측(WARNING 1회/일 cap · peek→로그→mark · None 스탬프)
# ===========================================================================
class TestF3F4F5StaleObservation:

    @pytest.mark.asyncio
    async def test_f3_stale_when_consumed_repeatedly_then_warns_once_with_fields(
        self, monkeypatch, caplog,
    ):
        """F-3 (현행 FAIL) — 폭주 금지 1회/일 + 판독에 필요한 필드 전수."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            results = [watcher.is_soft_gated() for _ in range(50)]

        assert results == [False] * 50, "stale 구간은 매 호출 fail-open"
        hits = _stale_records(caplog)
        assert len(hits) == 1, f"1회/일 cap 위반 — {len(hits)}행"
        rec = hits[0]
        assert rec.levelno == logging.WARNING, "감시자 정지는 WARNING(D2 LOUD)"
        assert "released" in rec.message, (
            "운영 grep 키 `[account_risk_gate] released` 를 벗어나면 "
            "'왜 풀렸나' 전수 검색에서 빠진다"
        )
        for field in ("age_secs=901", "max_secs=900", "evaluated_at=", "level=block"):
            assert field in rec.message, f"필드 누락: {field} / {rec.message}"

    @pytest.mark.asyncio
    async def test_f4a_stale_when_day_rolls_over_then_warns_again(
        self, monkeypatch, caplog,
    ):
        """F-4(a) — 날짜 키 자기 리셋(`_reset_daily_state` 훅 미의존)."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            with freeze_time("2026-09-02 10:00:00+09:00"):
                assert watcher.is_soft_gated() is False
                assert watcher.is_soft_gated() is False  # 같은 날 = cap
            assert len(_stale_records(caplog)) == 1
            with freeze_time("2026-09-03 10:00:00+09:00"):
                assert watcher.is_soft_gated() is False  # 익일 = 재발화

        assert len(_stale_records(caplog)) == 2

    @pytest.mark.asyncio
    async def test_f4b_stale_when_logging_raises_then_cap_unconsumed_and_still_open(
        self, monkeypatch, caplog,
    ):
        """F-4(b) — peek→로그→mark. 관측 자기실패가 관측을 지우지 않고 행위도 안 바꾼다."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)

        calls = {"n": 0}
        original = watcher.logger.warning

        def _boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("로그 싱크 장애")

        monkeypatch.setattr(watcher.logger, "warning", _boom)
        assert watcher.is_soft_gated() is False, "관측 실패 ≠ 행위 변화(여전히 fail-open)"
        assert calls["n"] == 1, "stale 경로가 WARNING 을 시도조차 안 했다"

        monkeypatch.setattr(watcher.logger, "warning", original)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            assert watcher.is_soft_gated() is False
        assert len(_stale_records(caplog)) == 1, (
            "mark-before-log 이면 cap 이 이미 소비돼 다음 호출이 침묵한다"
        )

    @pytest.mark.asyncio
    async def test_f4c_stale_when_state_reset_then_cap_is_cleared(
        self, monkeypatch, caplog,
    ):
        """F-4(c) — `reset_state_for_test()` 가 cap 도 리셋."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            watcher.is_soft_gated()
        assert len(_stale_records(caplog)) == 1

        watcher.reset_state_for_test()
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            assert watcher.is_soft_gated() is False
        assert len(_stale_records(caplog)) == 1

    def test_f5_gate_when_stamp_missing_then_fail_open_with_none_age(
        self, monkeypatch, caplog,
    ):
        """F-5 (현행 FAIL) — 스탬프 None(기록자 계약 위반 조합)도 stale 취급."""
        monkeypatch.setattr(watcher, "_gate_active", True)
        monkeypatch.setattr(watcher, "_evaluated_mono", None, raising=False)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            assert watcher.is_soft_gated() is False
            assert watcher.is_soft_gated() is False

        hits = _stale_records(caplog)
        assert len(hits) == 1
        assert "age_secs=None" in hits[0].message, hits[0].message

    def test_f5b_gate_when_age_computation_raises_then_fail_open_not_closed(
        self, monkeypatch, caplog,
    ):
        """F-5b (g4 — 뮤테이션 m6 검출) — 판정 예외는 반드시 fail-open(False).

        F-5 는 `_evaluated_mono=None` 직접 주입이라 `_gate_age_secs` 가 예외 없이
        None 을 반환하는 경로만 지난다 — `is_soft_gated` 의
        `except Exception: age = None` 을 `except Exception: return True`(fail-closed)
        로 바꿔도 F-5 는 못 잡는다. 여기서는 `_now_mono` 가 실제로 raise 하는
        경로를 별도로 실증한다.
        """
        def _boom():
            raise RuntimeError("monotonic clock 장애")

        watcher._gate_active = True
        watcher._evaluated_mono = 1.0  # None 아님 — _gate_age_secs 가 _now_mono 호출
        monkeypatch.setattr(watcher, "_now_mono", _boom)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            result = watcher.is_soft_gated()

        assert result is False, (
            "판정 예외는 fail-open(False) 이어야 한다 — fail-closed(True) 로 "
            "닫히면 도입 이전 무음과 구별 불가(D2 위반)"
        )
        hits = _stale_records(caplog)
        assert len(hits) == 1
        assert "age_secs=None" in hits[0].message, hits[0].message

    def test_f6_fast_path_when_gate_inactive_then_no_clock_read(
        self, monkeypatch, caplog,
    ):
        """F-6 — hot path 비용 상한: `_gate_active` False 면 시각 계산 0회, 로그 0행."""
        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            results = [watcher.is_soft_gated() for _ in range(100)]

        assert results == [False] * 100
        assert clock.calls == 0, (
            "fast path 소실 — `_gate_active` 검사보다 age 계산이 앞서면 "
            "7전략 per-tick 경로에 시각 비용이 얹힌다"
        )
        assert not [r for r in caplog.records if "[account_risk_gate]" in r.message]


# ===========================================================================
# F-7 — get_gate_state (사실과 행위를 나란히 · 무발화)
# ===========================================================================
class TestF7GateStateSnapshot:

    def test_f7a_state_when_never_evaluated_then_stale_and_not_gated(self):
        st = watcher.get_gate_state()
        assert st.get("age_secs", _MISSING) is None, "미평가 = age 없음"
        assert st.get("stale") is True, "미평가는 liveness 없음 = stale"
        assert st.get("effective_gated") is False
        assert st.get("stale_max_secs") == _STALE_MAX_EXPECTED
        assert st.get("level") == "ok"

    @pytest.mark.asyncio
    async def test_f7b_state_when_fresh_block_then_effective_gated(
        self, monkeypatch,
    ):
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        st = watcher.get_gate_state()
        assert st["level"] == "block"
        assert st.get("stale") is False
        assert st.get("effective_gated") is True
        age = st.get("age_secs", _MISSING)
        assert isinstance(age, (int, float)) and 0 <= age <= 1, age

    @pytest.mark.asyncio
    async def test_f7c_state_when_stale_then_level_preserved_but_not_gated(
        self, monkeypatch,
    ):
        """F-7(c) — `level` 재작성 금지. '동결됐다가 fail-open 으로 풀린 상태'의 서명."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)
        st = watcher.get_gate_state()
        assert st["level"] == "block", (
            "stale 시 level 을 ok 로 덮으면 '마지막 평가가 block 이었다'는 "
            "사실이 지워져 운영자가 동결을 식별할 수 없다"
        )
        assert st.get("stale") is True
        assert st.get("effective_gated") is False

    @pytest.mark.asyncio
    async def test_f7d_state_when_polled_repeatedly_then_never_emits(
        self, monkeypatch, caplog,
    ):
        """F-7(d) — 대시보드 폴링이 소비처 cap 을 선소비하면 안 된다(cycle233 F1 동형)."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            for _ in range(100):
                watcher.get_gate_state()
        assert _stale_records(caplog) == []

    @pytest.mark.asyncio
    async def test_f7e_state_when_extended_then_existing_keys_preserved(
        self, monkeypatch,
    ):
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        st = watcher.get_gate_state()
        for key in ("level", "reasons", "open_risk_pct", "open_risk_proxy_pct",
                    "net_asset", "coverage", "over_cap_count", "warn_pct",
                    "block_pct", "evaluated_at"):
            assert key in st, f"기존 키 유실: {key}"


# ===========================================================================
# F-8 / F-9 / F-10 / F-11 — 기록자(run_once) 연동
# ===========================================================================
class TestF8F9F10RecorderIntegration:

    @pytest.mark.asyncio
    async def test_f8_recorder_when_silent_gap_then_no_stale_warning_raw_transition(
        self, monkeypatch, caplog,
    ):
        """F-8 (cycle239-R1 재설계, g1 확증 시정) — 기록자는 stale 관측을 만들지 않는다.

        최초 설계(`was_active = is_soft_gated()`)는 이 시나리오(밤새 gap 후 익일
        부팅 재평가, 여전히 block)에서 `released reason=stale` WARNING 을 매 아침
        거짓 발화시켰다 — 감시 루프는 20:10 `_running=False` 로 **정상** 종료했을
        뿐인데 '감시 정지/사멸 의심' 으로 오독됐다(§리드 g1/g2 확증). 시정 =
        기록자 `was_active` 를 원시 `_gate_active` 로 되돌려 기록자 경로가
        `is_soft_gated()`/`_emit_stale_release` 를 아예 타지 않는다 — 소비자 경로
        (전략 on_tick·대시보드가 `is_soft_gated()` 를 직접 부를 때)만 stale 을
        관측/보고한다.
        """
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)  # entered(첫 평가)
        clock.advance(901)  # 20:10 종료 → 익일 07:55 부팅 gap 시뮬레이션

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await watcher.run_account_risk_watch_once(_gated_scheduler())

        msgs = [r.message for r in caplog.records if "[account_risk_gate]" in r.message]
        assert not any("reason=stale" in m for m in msgs), (
            f"기록자가 소비자용 stale WARNING 을 선소비했다(정상 일일 라이프사이클 "
            f"거짓 '사멸 의심'): {msgs}"
        )
        assert any("transition=reconfirm" in m for m in msgs), (
            f"raw _gate_active 기준 재확인(reconfirm)이 나와야 한다: {msgs}"
        )
        assert not any("transition=entered" in m for m in msgs), (
            f"같은 날 두 번째 평가라 entered 가 아니라 reconfirm 이어야 한다: {msgs}"
        )

    @pytest.mark.asyncio
    async def test_f8b_recorder_when_silent_gap_resolves_ok_then_single_release_log(
        self, monkeypatch, caplog,
    ):
        """F-8b (cycle239-R1 재설계) — raw 기준 release 는 유일한 신호, 중복 아님.

        기록자가 stale 를 관측하지 않으므로 '이미 stale WARNING 이 해제를
        알렸다' 전제가 사라진다 — `released —` INFO 1건이 그 자체로 정상 해제
        보고이고, 동반 stale WARNING 이 없어야 한다(있으면 기록자가 다시
        `is_soft_gated()` 를 부르는 회귀).
        """
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        clock.advance(901)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
            await watcher.run_account_risk_watch_once(_ok_scheduler())

        gate_msgs = [r.message for r in caplog.records
                     if "[account_risk_gate]" in r.message]
        released = [m for m in gate_msgs if "released" in m and "reason=" not in m]
        assert len(released) == 1, f"해제 로그는 정확히 1건이어야 한다: {gate_msgs}"
        assert not any("reason=stale" in m for m in gate_msgs), (
            f"기록자 경로에서 stale WARNING 이 동반되면 안 된다(회귀): {gate_msgs}"
        )

    @pytest.mark.asyncio
    async def test_f8c_stale_cap_when_recorder_reconfirms_same_day_then_independent(
        self, monkeypatch, caplog,
    ):
        """F-8c (g3 — 뮤테이션 x3 검출) — `gate_stale` cap 은 `gate_block` 과 별개.

        기록자가 같은 날 `transition=reconfirm`(cap 키 `gate_block`)을 이미
        소비했어도, 이후 소비자 경로의 `gate_stale` cap 은 별도로 1회 발화해야
        한다 — 두 cap 이 키를 공유하면 한쪽 소비가 다른 쪽을 침묵시킨다
        (D2 'fail-open+LOUD' 의 LOUD 절반이 하루 단위로 무음화되는 결함).
        """
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)  # entered
        # 같은 날 재평가 — reconfirm 이 `gate_block` cap 을 소비한다.
        await watcher.run_account_risk_watch_once(_gated_scheduler())

        clock.advance(901)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            results = [watcher.is_soft_gated() for _ in range(20)]

        assert results == [False] * 20
        hits = _stale_records(caplog)
        assert len(hits) == 1, (
            f"gate_stale cap 이 gate_block 과 키를 공유하면 이 WARNING 이 "
            f"무음화된다: {hits}"
        )

    @pytest.mark.asyncio
    async def test_f9_stamp_when_evaluation_succeeds_then_recorded(
        self, monkeypatch,
    ):
        """F-9 — 성공 경로 스탬프(`_gate_active` 대입과 같은 동기 블록)."""
        clock = _Clock(t=54_321.0)
        await _evaluate_block(monkeypatch, clock)
        stamp = getattr(watcher, "_evaluated_mono", _MISSING)
        assert stamp == clock.t, f"성공 평가가 스탬프를 남기지 않았다: {stamp!r}"
        st = watcher.get_gate_state()
        assert st.get("stale") is False
        assert st.get("age_secs", _MISSING) is not _MISSING
        assert st["age_secs"] <= 1

    @pytest.mark.asyncio
    async def test_f10_stamp_when_evaluation_fails_then_still_alive(
        self, monkeypatch,
    ):
        """F-10 (현행 FAIL) — 살아 있는 실패는 stale 이 아니다(루프 생존 중 연속 실패)."""
        from src.api import balance as balance_mod

        clock = _Clock()
        _pin_clock(monkeypatch, clock)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)

        async def _boom(afhr_flpr="N"):
            raise RuntimeError("KIS down")

        monkeypatch.setattr(balance_mod, "get_balance", _boom)
        await watcher.run_account_risk_watch_once(_gated_scheduler())

        st = watcher.get_gate_state()
        assert st["level"] == "error"
        assert st.get("stale") is False, (
            "실패 경로가 스탬프를 갱신하지 않으면 '루프 생존 중 연속 실패'가 "
            "'루프 사멸'로 오독된다"
        )
        assert st.get("age_secs", _MISSING) is not _MISSING
        assert st["age_secs"] <= 1
        assert watcher.is_soft_gated() is False  # fail-open 불변

    @pytest.mark.asyncio
    async def test_f11_reset_when_called_then_stamp_cleared(self, monkeypatch):
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        watcher.reset_state_for_test()

        assert getattr(watcher, "_evaluated_mono", _MISSING) is None
        st = watcher.get_gate_state()
        assert st.get("age_secs", _MISSING) is None
        assert st.get("stale") is True
        assert st.get("effective_gated") is False
        assert watcher.is_soft_gated() is False


# ===========================================================================
# F-12 — 루프 사멸 LOUD (0 행위)
# ===========================================================================
class TestF12WatchLoopDoneCallback:

    @staticmethod
    def _sched():
        return SimpleNamespace(_running=False,
                               registry=SimpleNamespace(all=lambda: []))

    @pytest.mark.asyncio
    async def test_f12a_loop_when_raises_then_warns_with_recovery_hint(
        self, monkeypatch, caplog,
    ):
        async def _boom(scheduler):
            raise RuntimeError("감시 루프 폭사")

        monkeypatch.setattr(watcher, "watch_loop", _boom)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            watcher.ensure_watch_loop(self._sched())
            task = watcher._watch_task
            with contextlib.suppress(Exception):
                await task
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        hits = [r for r in caplog.records
                if "[account_risk_watch_loop_died]" in r.message]
        assert hits, "루프 사멸이 완전 무음 — 동결을 알아챌 경로가 0"
        assert hits[0].levelno == logging.WARNING
        assert "RuntimeError" in hits[0].message
        assert "restart" in hits[0].message, "복구 안내 부재"

    @pytest.mark.asyncio
    async def test_f12b_loop_when_exits_normally_then_info(
        self, monkeypatch, caplog,
    ):
        async def _exit(scheduler):
            return None

        monkeypatch.setattr(watcher, "watch_loop", _exit)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            watcher.ensure_watch_loop(self._sched())
            await watcher._watch_task
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        hits = [r for r in caplog.records
                if "[account_risk_watch_loop_exit]" in r.message]
        assert hits, "정상 종료 = 매일 1건의 공짜 liveness 데이터포인트"
        assert "reason=running_false" in hits[0].message
        assert hits[0].levelno == logging.INFO

    @pytest.mark.asyncio
    async def test_f12c_loop_when_cancelled_then_info(self, monkeypatch, caplog):
        async def _sleeper(scheduler):
            await asyncio.sleep(30)

        monkeypatch.setattr(watcher, "watch_loop", _sleeper)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            watcher.ensure_watch_loop(self._sched())
            task = watcher._watch_task
            await asyncio.sleep(0)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await asyncio.sleep(0)

        hits = [r for r in caplog.records
                if "[account_risk_watch_loop_exit]" in r.message]
        assert hits and "reason=cancelled" in hits[0].message
        assert hits[0].levelno == logging.INFO


# ===========================================================================
# F-13 / F-14 — 소비처 전파 + fresh 행위 불변
# ===========================================================================
class TestF13F14ConsumerAndInvariance:

    @pytest.mark.asyncio
    async def test_f13_consumer_when_gate_stale_then_buy_gate_opens(
        self, monkeypatch,
    ):
        """F-13 (현행 FAIL) — strategy_base 무변경으로 전파됨을 실 전략으로 실증."""
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy
        from src.engine.strategy_base import StrategyConfig

        strat = DonchianSwingStrategy(StrategyConfig(
            strategy_id="donchian_swing", name="d", params={"exchange": "KRX"}))

        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        assert strat._account_soft_gate_blocked("005930") is True

        clock.advance(901)
        assert strat._account_soft_gate_blocked("005930") is False, (
            "소비처는 `is_soft_gated()` 만 보므로 신선도 시정이 자동 전파돼야 한다"
        )

    @pytest.mark.asyncio
    async def test_f14_fresh_when_evaluated_then_behaviour_identical(
        self, monkeypatch,
    ):
        """F-14 — fresh 구간 행위 불변(변경은 age>900 구간에만 존재)."""
        clock = _Clock()
        await _evaluate_block(monkeypatch, clock)
        for _ in range(300):
            clock.advance(2.0)  # 총 600s < 900s
            assert watcher.is_soft_gated() is watcher._gate_active

        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
        clock2 = _Clock()
        _pin_clock(monkeypatch, clock2)
        await watcher.run_account_risk_watch_once(_ok_scheduler())
        for _ in range(300):
            clock2.advance(2.0)
            assert watcher.is_soft_gated() is watcher._gate_active
