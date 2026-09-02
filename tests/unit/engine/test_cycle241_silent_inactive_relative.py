"""cycle241 Red — silent_inactive 세션 상대 판정 (08-31 포렌식 결함 ⓐ · 워크리스트 P1-4).

> 선행 명세: `_workspace/red/cycle241_silent_inactive_relative_spec.md`

## 결함 (현행)

`detect_silent_inactive_sessions`(`src/engine/stale_session_recovery.py:43`)는 세션마다
**독립적으로** `fresh_ratio < 0.2 ∧ subscribed >= 5 ∧ 5분 지속` 을 판정한다. 세션 간 비교도,
시장 상태 참조도 없어서 "8세션이 같은 초에 전부 침묵" 을 "8개 세션이 동시에 고장" 과 구분할
방법이 코드에 없다. 30일 522건 중 491건(94.1%)이 풀 전체 동시 발화이고 정규장 09:00~15:20
발화는 0건 — 즉 발화의 실체는 시장 침묵(NXT 프리 마감 08:50~09:00 · 15:20 이후 장후
동시호가 + 15:30~15:40 마감 흡수)이며 재연결이 회복시킨 사례는 0건이다.

## 시정 (L1 — 세션 상대 판정)

판정 가능 세션(`subscribed >= SILENT_INACTIVE_MIN_SUBSCRIBED`)이 `_MARKET_WIDE_MIN_ELIGIBLE(=2)`
이상이고 **그 전부**가 침묵이면 시장 침묵으로 보고 그 사이클을 **기각 + 전 라벨 first_seen pop**
후 `[]` 반환. 다른 세션이 하나라도 fresh 면 현행대로 발화(진짜 세션 결함 보존), 판정 가능
세션 < 2 면 현행 byte 동일(fail-open).

## 이 파일의 계약

- `(현행 FAIL)` 표기 케이스 = Red 실증 대상. 나머지는 회귀 가드(현행에서도 PASS 유지 의무).
- **결과 집합 ⊆ 현행** — 시정이 새 발화 경로를 만들지 않는다.
- 관측 마커 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` 는
  에피소드 전이 cap(진입 1회 / 지속 30분마다 / 이탈 1회) — 폭주 금지, peek→로그→mark.
- 행위(pop + `[]`)는 cap **밖** — 관측 헬퍼가 던져도 수행된다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 8세션 픽스처 원본 — 사이클 29-R2 회귀 파일과 같은 세션 dict 형상을 공유한다.
from tests.unit.engine.test_session_silent_inactive_ratio import _make_session as _base_session

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

# 15:21 KST — 연속매매 종료(15:20) 직후, STALE_FRESHNESS_SECS=60 경과로 전 세션이
# 구조적으로 침묵하는 실측 슬롯. 마커 `entered` 가 찍혀야 하는 시각대.
NOW = datetime(2026, 9, 3, 15, 22, 0, tzinfo=KST)

# 운영 실측 8세션 라벨 (main = 메인 세션, 나머지는 보조 계좌 DB 라벨)
LABELS = ("main", "ISA", "RIA", "fire", "gold", "44606571", "71513056", "1004")

# 세션별 구독 종목 수 (전부 SILENT_INACTIVE_MIN_SUBSCRIBED=5 이상 = 판정 가능)
DEFAULT_SUBS = {
    "main": 8, "ISA": 12, "RIA": 16, "fire": 10,
    "gold": 9, "44606571": 17, "71513056": 11, "1004": 13,
}

_MARKER = "[silent_inactive_market_wide_skip]"
_MISSING = object()  # ws_connected 키 자체가 없는 세션 표현


# ===========================================================================
# 헬퍼
# ===========================================================================
def _mod():
    from src.engine import stale_session_recovery
    return stale_session_recovery


def _reset_mw_state() -> None:
    """에피소드 관측 상태 초기화 — Green 전에는 no-op (회귀 가드가 Red 에서도 PASS 하도록)."""
    fn = getattr(_mod(), "reset_market_wide_episode_state", None)
    if callable(fn):
        fn()


@pytest.fixture(autouse=True)
def _isolate_market_wide_episode():
    """모듈 전역 에피소드 상태 누수 차단 (전/후 초기화)."""
    _reset_mw_state()
    yield
    _reset_mw_state()


def _mw_state() -> dict:
    """`_MW_EPISODE` 직접 접근 — 미구현이면 Red 사유를 명시하고 실패."""
    state = getattr(_mod(), "_MW_EPISODE", None)
    if state is None:
        pytest.fail(
            "cycle241 미구현 — `stale_session_recovery._MW_EPISODE` 부재. "
            "에피소드 관측 상태는 StaleTrackerState(7필드 정확 일치 가드)·scheduler(3,999L) "
            "어느 쪽에도 못 두므로 모듈 전역 + 날짜 키 자기 리셋이 유일한 무충돌 위치다."
        )
    return state


def _make_scheduler():
    """`TradingScheduler.__new__` + `_stale_state` 만 init (사이클 60 A1 패턴 답습)."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    return sched


def _tickers_for(label: str, n: int) -> list[str]:
    """세션 간 겹치지 않는 6자리 종목코드 — fresh 계산이 세션별로 독립하도록."""
    idx = LABELS.index(label) if label in LABELS else 9
    return [f"{idx}{i:05d}" for i in range(n)]


def _build_pool(
    fresh_counts: dict[str, int],
    *,
    labels: tuple[str, ...] = LABELS,
    subs: dict[str, int] | None = None,
    connected: dict[str, object] | None = None,
    reconnects: dict[str, int] | None = None,
    now: datetime = NOW,
) -> tuple[list[dict], dict[str, datetime]]:
    """세션 상태 리스트 + `ticker_last_tick` 맵 생성.

    Args:
        fresh_counts: 라벨 → fresh 종목 수 (미지정 = 0 = 완전 침묵).
        subs: 라벨 → 구독 수 (미지정 시 DEFAULT_SUBS, 그래도 없으면 8).
        connected: 라벨 → `ws_connected` 값. `_MISSING` 이면 키 자체를 제거.
        reconnects: 라벨 → `reconnect_count` 값 (미지정 = 기존 픽스처 기본값, 보통 0).
    """
    sub_map = DEFAULT_SUBS if subs is None else subs
    sessions: list[dict] = []
    last_tick: dict[str, datetime] = {}
    for label in labels:
        n = sub_map.get(label, 8)
        tickers = _tickers_for(label, n)
        sess = _base_session(label, n, tickers)
        if connected is not None and label in connected:
            value = connected[label]
            if value is _MISSING:
                sess.pop("ws_connected", None)
            else:
                sess["ws_connected"] = value
        if reconnects is not None and label in reconnects:
            sess["reconnect_count"] = reconnects[label]
        sessions.append(sess)
        for t in tickers[: fresh_counts.get(label, 0)]:
            last_tick[t] = now - timedelta(seconds=10)
    return sessions, last_tick


def _run_detect(sched, sessions, last_tick, now: datetime) -> list[str]:
    """ratio 파일 관용구 — pool/ticker_last_tick/datetime 3중 patch 후 감지 1사이클."""
    from src.engine import scheduler as sch_mod

    with patch.object(sch_mod, "kis_ws_pool") as mock_pool:
        mock_pool.get_session_status = MagicMock(return_value=sessions)
        with patch("src.engine.scanner.ticker_last_tick", last_tick):
            with patch("src.engine.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = now
                mock_dt.min = datetime.min
                return sched._detect_silent_inactive_sessions()


def _marker_lines(caplog, transition: str | None = None, level: int | None = None) -> list[str]:
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if _MARKER not in msg:
            continue
        if "_failed" in msg:
            continue
        if transition is not None and f"transition={transition}" not in msg:
            continue
        if level is not None and rec.levelno != level:
            continue
        out.append(msg)
    return out


def _failed_lines(caplog) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if "[silent_inactive_market_wide_skip_failed]" in r.getMessage()
        and r.levelno == logging.WARNING
    ]


def _arm(sched, labels, now: datetime = NOW, seconds: float = 301.0) -> None:
    """`first_seen` 사전 무장 — 5분 지속 임계를 이미 넘긴 상태."""
    for label in labels:
        sched._silent_inactive_first_seen[label] = now - timedelta(seconds=seconds)


# ===========================================================================
# F-1 (현행 FAIL — 핵심): 8세션 전원 침묵 = 시장 침묵 → 기각
# ===========================================================================
def test_f241_1_all_eight_sessions_silent_when_market_wide_then_rejected(caplog):
    """8세션 전부 fresh=0 + 5분 지속 → 발화 0 + 전 라벨 first_seen pop + entered 마커 1행.

    현행은 세션 간 비교가 없어 8 label 을 전부 반환하고, K 루프가 8세션 × `_ws.close()` 를
    발화한다(하루 ~24회 재연결 = 접속키 낭비 + 보유 종목 tick blind). 시정 후에는 이 입력이
    '시장 침묵' 으로 기각돼야 한다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    sessions, last_tick = _build_pool({})           # 전 세션 fresh=0
    _arm(sched, LABELS)
    first_seen_obj = sched._silent_inactive_first_seen

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == [], (
        f"전 세션 동시 침묵은 '세션 8개 동시 고장' 이 아니라 시장 침묵이다 — got {result}. "
        f"발화 시 8 × _ws.close() → 접속키 8건 + 재구독 폭주 + tick blind."
    )
    assert sched._silent_inactive_first_seen == {}, (
        "기각은 pop 이어야 한다 — 값을 유지(hold)하면 시장 재개 순간 지각 세션이 즉발한다."
    )
    assert sched._silent_inactive_first_seen is first_seen_obj, "first_seen dict 동일성 보존"

    entered = _marker_lines(caplog, "entered")
    assert len(entered) == 1, f"entered 마커 정확히 1행 — got {entered}"
    line = entered[0]
    for field in ("sessions=8", "eligible=8", "silent=8/8", "connected=8", "reset=8"):
        assert field in line, f"마커 필드 `{field}` 누락 — got {line!r}"
    assert not any(
        "[silent_inactive_force_reconnect]" in r.getMessage() for r in caplog.records
    ), "기각 사이클에서 강제 reconnect 로그가 나오면 안 된다"


# ===========================================================================
# F-2 (현행 FAIL): 기각 사이클은 first_seen 을 등록조차 하지 않는다
# ===========================================================================
def test_f241_2_market_wide_when_unarmed_then_no_first_seen_accumulation():
    """무장 전 전 세션 침묵 → `[]` ∧ first_seen 비어 있음(누적 금지).

    누적 후 반환 직전 필터(m7 변형)는 침묵 구간 동안 first_seen 이 계속 자라므로 시장이
    재개돼 한 세션만 늦게 깨어나는 순간 elapsed >= 300 이 이미 성립해 즉발한다 —
    오판이 재개 경계로 이동할 뿐이다.
    """
    sched = _make_scheduler()
    sessions, last_tick = _build_pool({})

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == []
    assert sched._silent_inactive_first_seen == {}, (
        f"기각 사이클은 누적 금지 — got {dict(sched._silent_inactive_first_seen)}"
    )


# ===========================================================================
# F-3 (회귀 가드): 진짜 단독 세션 결함은 현행대로 발화
# ===========================================================================
def test_f241_3_single_broken_session_when_others_fresh_then_still_fires(caplog):
    """main 만 fresh 1/8(12.5%) + 5분 지속, 타 7세션 fresh 50~78% → `["main"]` 발화.

    09-02 16:05 실측 재현. 비교 대상이 fresh 하므로 '그 세션만 죽었다' 가 성립한다 —
    상대 판정이 이 경로를 죽이면 결함 탐지 자체가 사라진다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    sessions, last_tick = _build_pool(
        {"main": 1, "ISA": 6, "RIA": 10, "fire": 7, "gold": 7,
         "44606571": 12, "71513056": 8, "1004": 9}
    )
    _arm(sched, ["main"])

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == ["main"], f"단독 세션 결함 보존 실패 — got {result}"
    assert _marker_lines(caplog) == [], "하나라도 fresh 면 시장 침묵이 아니다 — 마커 금지"
    for label in LABELS[1:]:
        assert label not in sched._silent_inactive_first_seen


# ===========================================================================
# F-4 (경계 회귀): 하나라도 fresh 면 상대 판정 불성립
# ===========================================================================
def test_f241_4_one_fresh_session_when_seven_silent_then_seven_fire(caplog):
    """7세션 침묵(5분 지속) + RIA fresh 11/16(68.75%) → 7 label 발화, 마커 0.

    `silent == eligible` 이 아니면 게이트는 off. 시장이 조용한 게 아니라 7개가 실제로
    죽었을 가능성이 살아 있으므로 현행 행위를 유지한다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    sessions, last_tick = _build_pool({"RIA": 11})
    silent_labels = [lb for lb in LABELS if lb != "RIA"]
    _arm(sched, silent_labels)

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert sorted(result) == sorted(silent_labels), f"got {result}"
    assert "RIA" not in sched._silent_inactive_first_seen, "회복 세션 first_seen pop"
    assert _marker_lines(caplog) == [], "게이트 off 사이클에 마커 금지"


# ===========================================================================
# F-5 (회귀 가드): 비교 불가 = fail-open (현행 byte 동일)
# ===========================================================================
def test_f241_5a_single_session_pool_when_silent_then_fires_as_today(caplog):
    """단일 세션 풀(VTS/개발) → 비교 대상이 없으므로 현행 판정 유지."""
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    sessions, last_tick = _build_pool({}, labels=("main",))
    _arm(sched, ["main"])

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == ["main"], (
        f"eligible < 2 는 fail-open(현행 유지)여야 한다 — got {result}. "
        f"단일 세션까지 기각하면 silent inactive 감지 자체가 사라진다."
    )
    assert _marker_lines(caplog) == []


def test_f241_5b_second_session_below_min_subscribed_then_eligible_is_one(caplog):
    """main(sub=8) 침묵 + 두 번째 세션 sub=4(비판정) 침묵 → eligible=1 → 현행 발화.

    `subscribed < SILENT_INACTIVE_MIN_SUBSCRIBED` 세션은 원래도 suspect 가 될 수 없어
    분모에서 빠진다 — 분모를 `len(sessions)` 로 세는 변형(m4)을 잡는다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    labels = ("main", "ISA")
    sessions, last_tick = _build_pool({}, labels=labels, subs={"main": 8, "ISA": 4})
    _arm(sched, labels)

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == ["main"], f"eligible=1 이면 현행 유지 — got {result}"
    assert "ISA" not in sched._silent_inactive_first_seen, "sub<5 세션은 first_seen pop"
    assert _marker_lines(caplog) == []


# ===========================================================================
# F-6 (현행 FAIL): eligible 하한 정확히 2
# ===========================================================================
def test_f241_6_exactly_two_eligible_sessions_all_silent_then_rejected(caplog):
    """정확히 2세션 모두 eligible·침묵 → 기각 + `sessions=2 eligible=2 silent=2/2`."""
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    labels = ("main", "ISA")
    sessions, last_tick = _build_pool({}, labels=labels)
    _arm(sched, labels)

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == [], f"_MARKET_WIDE_MIN_ELIGIBLE=2 하한 — got {result}"
    entered = _marker_lines(caplog, "entered")
    assert len(entered) == 1, f"got {entered}"
    for field in ("sessions=2", "eligible=2", "silent=2/2"):
        assert field in entered[0], f"`{field}` 누락 — got {entered[0]!r}"


# ===========================================================================
# F-7 (현행 FAIL — hold 변형 봉인): 침묵 해제 후 다시 5분
# ===========================================================================
def test_f241_7_after_market_wide_then_real_defect_needs_fresh_five_minutes():
    """전원 침묵(pop) → 재개 후 main 만 침묵 → **재개 시점부터** 5분 뒤에야 발화.

    - 사이클1 (NOW, 전원 침묵): main first_seen(NOW-200) pop, `[]`
    - 사이클2 (NOW+120, 7 fresh + main 침묵): first_seen 재등록 = NOW+120, `[]`
    - 사이클3 (NOW+420, 동일): elapsed 300 도달 → `["main"]`

    현행은 사이클2 에서 elapsed 320 으로 **즉발**한다. 기각 시 값을 유지하는 hold 변형(m2)도
    같은 자리에서 잡힌다.
    """
    sched = _make_scheduler()
    t1 = NOW
    t2 = NOW + timedelta(seconds=120)
    t3 = t2 + timedelta(seconds=300)

    sched._silent_inactive_first_seen["main"] = t1 - timedelta(seconds=200)

    sessions1, tick1 = _build_pool({}, now=t1)
    assert _run_detect(sched, sessions1, tick1, t1) == [], "사이클1 전원 침묵 = 기각"
    assert "main" not in sched._silent_inactive_first_seen, (
        "기각은 pop — hold 하면 재개 직후 첫 사이클에 즉발한다"
    )

    fresh_map = {lb: DEFAULT_SUBS[lb] for lb in LABELS if lb != "main"}
    sessions2, tick2 = _build_pool(fresh_map, now=t2)
    assert _run_detect(sched, sessions2, tick2, t2) == [], (
        "재개 직후 사이클은 5분 카운트를 새로 시작해야 한다"
    )
    assert sched._silent_inactive_first_seen.get("main") == t2, (
        f"first_seen 재등록 시각 불일치 — got {sched._silent_inactive_first_seen.get('main')}"
    )

    sessions3, tick3 = _build_pool(fresh_map, now=t3)
    assert _run_detect(sched, sessions3, tick3, t3) == ["main"], (
        "재개 후 5분 지속한 진짜 결함은 반드시 발화"
    )


# ===========================================================================
# F-8 (현행 FAIL): 마커 전이 cap — 5사이클 = 1행
# ===========================================================================
def test_f241_8_episode_transition_cap_entered_exited_reentered(caplog):
    """5사이클 연속 전원 침묵 → entered 1행 · 혼합 사이클 → exited 1행 · 재침묵 → entered 재발화.

    에피소드당 1회만 캡하면 08-31 형 4시간 두절이 몇 줄로 축약된다. 매 사이클 로그(m8)는
    K 루프 120s × 4시간 = 120행 폭주가 된다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()

    for step in range(5):                                  # t = 0, 120, 240, 360, 480
        now = NOW + timedelta(seconds=120 * step)
        sessions, tick = _build_pool({}, now=now)
        assert _run_detect(sched, sessions, tick, now) == []

    assert len(_marker_lines(caplog, "entered")) == 1, (
        f"5사이클 동안 entered 1행 — got {_marker_lines(caplog, 'entered')}"
    )
    assert _marker_lines(caplog, "exited") == []

    mixed_now = NOW + timedelta(seconds=600)
    sessions, tick = _build_pool({"RIA": 11}, now=mixed_now)
    assert _run_detect(sched, sessions, tick, mixed_now) == []

    exited = _marker_lines(caplog, "exited")
    assert len(exited) == 1, f"이탈 1행 — got {exited}"
    assert "elapsed_secs=600" in exited[0], f"got {exited[0]!r}"
    assert "cycles=5" in exited[0], f"got {exited[0]!r}"

    re_now = NOW + timedelta(seconds=720)
    sessions, tick = _build_pool({}, now=re_now)
    assert _run_detect(sched, sessions, tick, re_now) == []
    assert len(_marker_lines(caplog, "entered")) == 2, "재진입 시 entered 재발화"


# ===========================================================================
# F-9 (현행 FAIL): persisting WARNING 30분 주기
# ===========================================================================
def test_f241_9_persisting_warning_every_thirty_minutes(caplog):
    """전원 침묵 62분(120s × 32사이클) → entered 1 + persisting WARNING 2 (t=1800, t=3600).

    정상 최장 에피소드는 15:20→15:40 의 1,200s 라 1,800s 는 1.5배 마진이다. persisting 이
    찍히면 08-31 형 장기 두절 — `[tick_coverage] ratio=0.0%` 와 함께 읽는다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()

    for step in range(32):                                 # t = 0 .. 3720
        now = NOW + timedelta(seconds=120 * step)
        sessions, tick = _build_pool({}, now=now)
        assert _run_detect(sched, sessions, tick, now) == [], f"step={step}"

    assert len(_marker_lines(caplog, "entered")) == 1
    warns = _marker_lines(caplog, "persisting", level=logging.WARNING)
    assert len(warns) == 2, (
        f"1,800s 임계 첫 발화 + 1,800s 뒤 재발화 = 2행 — got {warns}"
    )
    assert "elapsed_secs=1800" in warns[0], f"got {warns[0]!r}"
    assert "elapsed_secs=3600" in warns[1], f"got {warns[1]!r}"


# ===========================================================================
# F-10 (현행 FAIL): 관측 실패 격리 + peek→로그→mark
# ===========================================================================
def test_f241_10_observer_failure_when_logger_raises_then_behavior_intact(caplog, monkeypatch):
    """마커 로깅이 던져도 pop·`[]` 은 수행되고, `since` 는 기록되지 않는다.

    mark-before-log(m9)면 실패한 사이클이 에피소드를 열어버려 복구 후 entered 가 영영
    안 찍힌다 — 관측기 자기실패가 관측 대상을 지우는 cycle226 D-3 동형 함정.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    mod = _mod()
    real_info = mod.logger.info

    def _raiser(msg, *args, **kwargs):
        if isinstance(msg, str) and _MARKER in msg:
            raise RuntimeError("관측기 자기 실패 주입")
        return real_info(msg, *args, **kwargs)

    monkeypatch.setattr(mod.logger, "info", _raiser)

    _arm(sched, LABELS)
    sessions, tick = _build_pool({})
    result = _run_detect(sched, sessions, tick, NOW)      # 예외 전파 0 의무

    assert result == [], "관측 실패는 행위(기각)를 바꾸지 않는다"
    assert sched._silent_inactive_first_seen == {}, "pop 은 cap 밖에서 수행"
    assert len(_failed_lines(caplog)) == 1, (
        f"자기 실패 흔적 WARNING 1행 — got {_failed_lines(caplog)}"
    )

    monkeypatch.undo()
    later = NOW + timedelta(seconds=120)
    sessions, tick = _build_pool({}, now=later)
    assert _run_detect(sched, sessions, tick, later) == []
    assert len(_marker_lines(caplog, "entered")) == 1, (
        "peek→로그→mark — 실패 사이클이 `since` 를 기록했으면 entered 가 영영 안 찍힌다"
    )


# ===========================================================================
# F-11 (현행 FAIL): `unknown` 라벨 충돌 — 개수는 리스트 길이로 센다
# ===========================================================================
def test_f241_11a_duplicate_unknown_labels_then_rejected_without_error(caplog):
    """`unknown` ×2 + main, 전부 침묵 → eligible=3(길이 기준) → 기각, pop 예외 0."""
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    labels = ("unknown", "unknown", "main")
    sessions, last_tick = _build_pool({}, labels=labels, subs={"unknown": 7, "main": 8})
    _arm(sched, ["unknown", "main"])

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == [], f"got {result}"
    entered = _marker_lines(caplog, "entered")
    assert len(entered) == 1 and "sessions=3" in entered[0] and "eligible=3" in entered[0], (
        f"세션 수는 리스트 길이 — got {entered}"
    )


def test_f241_11b_two_duplicate_labels_only_then_length_based_count_rejects(caplog):
    """`unknown` ×2 만(총 2세션) 전부 침묵 → 길이 기준 eligible=2 → 기각.

    라벨 set 으로 세는 변형(m5)이면 eligible=1 이라 fail-open 으로 떨어져 발화한다 — 대조군.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    labels = ("unknown", "unknown")
    sessions, last_tick = _build_pool({}, labels=labels, subs={"unknown": 7})
    _arm(sched, ["unknown"])

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == [], (
        f"판정 가능 세션 개수는 **리스트 길이**로 센다(라벨 set 아님) — got {result}"
    )
    assert len(_marker_lines(caplog, "entered")) == 1


# ===========================================================================
# F-12 (현행 FAIL): 날짜 키 자기 리셋
# ===========================================================================
def test_f241_12_stale_episode_from_previous_day_then_reset_not_persisting(caplog):
    """전일 19:58 에 열린 에피소드가 남아 있어도 익일 08:52 는 새 에피소드로 시작한다.

    날짜 키가 없으면 elapsed 가 13시간으로 계산돼 첫 사이클부터 persisting WARNING 이
    터진다(m11). `_reset_daily_state` 훅은 scheduler 편집이라 쓸 수 없으므로 자기 리셋이 계약.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    state = _mw_state()

    prev_day = datetime(2026, 9, 2, 19, 58, 0, tzinfo=KST)
    state.update(day=prev_day.date().isoformat(), since=prev_day, cycles=60, last_warn_at=None)

    next_morning = datetime(2026, 9, 3, 8, 52, 0, tzinfo=KST)
    sessions, tick = _build_pool({}, now=next_morning)
    assert _run_detect(sched, sessions, tick, next_morning) == []

    assert len(_marker_lines(caplog, "entered")) == 1, "익일 첫 침묵은 새 에피소드 진입"
    assert _marker_lines(caplog, "persisting") == [], (
        "전일 `since` 로 elapsed 를 재면 13시간 → 즉시 persisting = 날짜 키 부재"
    )
    assert state["cycles"] == 1, f"새 에피소드 cycles=1 — got {state['cycles']}"


# ===========================================================================
# F-13 (현행 FAIL): connected= 진단 필드
# ===========================================================================
def test_f241_13_connected_field_counts_only_true_and_tolerates_missing_key(caplog):
    """`ws_connected` True 5 · False 2 · 키 부재 1 → `connected=5`, 예외 0.

    08-31 형에서 `connected=0/8` 이 소켓 사망을 즉시 말해 준다. 게이트에는 쓰지 않는다 —
    `_ws is None` 이면 `force_reconnect_session` 이 어차피 skip 하므로 결과가 안 바뀐다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    connected = {
        "main": True, "ISA": True, "RIA": True, "fire": True, "gold": True,
        "44606571": False, "71513056": False, "1004": _MISSING,
    }
    sessions, tick = _build_pool({}, connected=connected)

    assert _run_detect(sched, sessions, tick, NOW) == []

    entered = _marker_lines(caplog, "entered")
    assert len(entered) == 1, f"got {entered}"
    assert "connected=5" in entered[0], f"got {entered[0]!r}"


# ===========================================================================
# F-13b (신규 — 적대 검증 확증 #2 봉인): reconnects= 진단 필드
# ===========================================================================
def test_f241_13b_reconnects_field_sums_reconnect_count_across_sessions(caplog):
    """`reconnect_count` 합이 `reconnects=` 로 병기된다(마커 진단 필드 — 게이트에는 미사용).

    ⚠️ **cycle241 라운드 2 정정** — `reconnects=` 는 `KisWebSocket._reconnect_count`(핸드셰이크
    단계 재시도 인덱스, 세션당 상한 `MAX_RECONNECT=5`) 합이며, **08-31 형 소켓 생존 판별에는
    쓸 수 없다**: 이 함수가 부르는 `force_reconnect_session` 의 강제 `_ws.close()` 는 이
    카운터를 올리지 않는다(`_receive_loop` 가 `ConnectionClosed` 를 흡수해 정상 반환하므로
    `connect()` 의 except 분기에 도달 못 하고, `MIN_STABLE_SECONDS` 리셋만 매 루프 작동).
    소켓 생존 판별은 `[ws_heartbeat]`(세션별 PINGPONG 기반) 로 읽는다 — 이 테스트는 필드가
    `get_session_status()` 소스에서 정확히 합산돼 병기되는지만 봉인한다(진단 필드 정확성).
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    reconnects = {"main": 3, "ISA": 2, "gold": 1}          # 나머지는 기본값 0
    sessions, tick = _build_pool({}, reconnects=reconnects)

    assert _run_detect(sched, sessions, tick, NOW) == []

    entered = _marker_lines(caplog, "entered")
    assert len(entered) == 1, f"got {entered}"
    assert "connected=8" in entered[0], f"got {entered[0]!r}"
    assert "reconnects=6" in entered[0], f"got {entered[0]!r}"


# ===========================================================================
# F-14 (현행 FAIL): cap dict 동일성·내용 무접촉
# ===========================================================================
def test_f241_14_reject_path_when_running_then_cap_dict_untouched():
    """기각 경로는 `_silent_inactive_recovery_count` 를 읽지도 쓰지도 않는다.

    시간당 세션당 2회 cap(KIS LMS/앱키 정지 위험 차단)은 이 사이클의 무접촉 계약이다.
    """
    sched = _make_scheduler()
    cap_dict = sched._silent_inactive_recovery_count
    assert cap_dict is sched._stale_state.silent_inactive_recovery_count
    cap_dict["main"] = [1234.5]
    first_seen_obj = sched._silent_inactive_first_seen
    _arm(sched, LABELS)

    sessions, tick = _build_pool({})
    assert _run_detect(sched, sessions, tick, NOW) == []

    assert sched._silent_inactive_recovery_count is cap_dict, "cap dict `is` 동일성"
    assert cap_dict == {"main": [1234.5]}, f"cap 내용 불변 — got {cap_dict}"
    assert sched._silent_inactive_first_seen is first_seen_obj, "first_seen dict 동일성"
    assert sched._silent_inactive_first_seen == {}, "값만 pop"


# ===========================================================================
# F-15 (현행 FAIL): K 루프 통합 — 기각 사이클엔 reconnect 0회
# ===========================================================================
@pytest.mark.asyncio
async def test_f241_15_k_loop_body_when_market_wide_then_no_force_reconnect():
    """`_stale_watcher_loop` 본체와 동일한 순서로 돌려 `_ws.close()` 발화가 0인지 본다.

    현행은 8 label 을 돌려주므로 같은 루프가 8회 재연결한다 = 접속키 8건 + 보유 종목 tick 공백.
    """
    from src.engine import stale_manager

    sched = _make_scheduler()
    _arm(sched, LABELS)
    sessions, tick = _build_pool({})

    with patch.object(
        stale_manager, "force_reconnect_session", new=AsyncMock(return_value=True)
    ) as mock_reconnect:
        silent_labels = _run_detect(sched, sessions, tick, NOW)
        for label in silent_labels:                        # `_stale_watcher_loop` 본체 동형
            await sched._force_reconnect_session(label)

    assert silent_labels == [], f"got {silent_labels}"
    assert mock_reconnect.await_count == 0, (
        f"기각 사이클 강제 reconnect 0회 의무 — got {mock_reconnect.await_count}회"
    )


# ===========================================================================
# F-16 (현행 FAIL): sub=0 혼합 (20:00 unsubscribe_all race)
# ===========================================================================
def test_f241_16a_zero_sub_sessions_excluded_from_eligible_then_two_reject(caplog):
    """6세션 sub=0 + 2세션 eligible·침묵 → eligible=2 → 기각."""
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    subs = {lb: 0 for lb in LABELS}
    subs["main"] = 8
    subs["ISA"] = 12
    sessions, tick = _build_pool({}, subs=subs)
    _arm(sched, ["main", "ISA"])

    assert _run_detect(sched, sessions, tick, NOW) == []
    entered = _marker_lines(caplog, "entered")
    assert len(entered) == 1 and "eligible=2" in entered[0], f"got {entered}"


def test_f241_16b_only_one_eligible_among_zero_sub_sessions_then_fires(caplog):
    """7세션 sub=0 + 1세션만 eligible·침묵 → eligible=1 → 현행 발화(fail-open)."""
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    subs = {lb: 0 for lb in LABELS}
    subs["main"] = 8
    sessions, tick = _build_pool({}, subs=subs)
    _arm(sched, ["main"])

    assert _run_detect(sched, sessions, tick, NOW) == ["main"]
    assert _marker_lines(caplog) == []


# ===========================================================================
# F-18 (신규 — 적대 검증 escape M06a/M06b 봉인): pass 1 예외는 전파된다
# ===========================================================================
@pytest.mark.parametrize("bad_index", [0, 4, 7], ids=["first", "middle", "last"])
def test_f241_18_malformed_session_when_missing_label_then_exception_propagates(bad_index, caplog):
    """pass 1(판정 재료 수집) 도중 예외가 나면 삼키지 않고 그대로 전파한다.

    현행 계약 = `scheduler.py:3024-3029` 의 K 루프가
    `except Exception: logger.exception("... 다음 사이클 자연 재시도")` 로 흡수한다. 이 함수
    **안에서** 삼키면(전체 try/except → `[]` 반환, 또는 세션별 try/continue → eligible 분모
    왜곡) malformed 세션 하나가 감지 자체를 조용히 무력화하거나 게이트를 뒤집는다 — 어느 쪽도
    이 사이클의 계약이 아니다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    sessions, last_tick = _build_pool({})            # 전 세션 fresh=0 (시장 침묵 모양)
    del sessions[bad_index]["label"]                 # 필수 키 결손 — pass 1 에서 즉시 KeyError

    with pytest.raises(KeyError):
        _run_detect(sched, sessions, last_tick, NOW)

    assert sched._silent_inactive_first_seen == {}, (
        "pass 1 은 상태 무변경 — 예외 전 first_seen 변경 0"
    )
    assert _marker_lines(caplog) == [], (
        "예외 시 마커 emit 0 — 게이트 도달 전에 중단돼야 한다(전파돼 `[]` 로 위장 금지)"
    )


def test_f241_18b_malformed_session_when_market_wide_shape_then_still_raises(caplog):
    """전원 침묵 모양의 입력이라도 malformed 세션이 섞이면 기각(`[]`)이 아니라 예외.

    변조(전체 try/except → 기각)는 이 케이스를 "시장 침묵 → 정상 기각" 으로 위장시킨다 —
    실제로는 판정 재료 자체를 못 만든 것이므로 반드시 예외가 드러나야 한다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    sessions, last_tick = _build_pool({})
    del sessions[3]["tickers"]                        # 필수 서브키 결손

    with pytest.raises(KeyError):
        _run_detect(sched, sessions, last_tick, NOW)

    assert _marker_lines(caplog, "entered") == [], (
        "예외를 삼켜 `[]` 로 기각하면 시장 침묵 오판이 아니라 진짜 결함 은폐다"
    )


# ===========================================================================
# F-19 (신규 — 적대 검증 escape M19 봉인): 기각은 non-eligible 세션도 pop, ghost 는 보존
# ===========================================================================
def test_f241_19_market_wide_reject_pops_non_eligible_stale_labels_but_not_ghost_keys(caplog):
    """기각(reset) 은 현재 세션 목록(`judged`)의 전 라벨을 pop 한다 — suspect(=eligible ∧
    침묵) 만이 아니다. 목록 밖의 ghost 키는 손대지 않는다.

    변조(`if _s and ...pop(label, None)`) 는 suspect 만 pop 해서, sub<5/sub=0 처럼 원래도
    suspect 가 될 수 없는 세션의 stale first_seen 이 기각 사이클을 몇 번 통과해도 살아남는다 —
    그 세션이 나중에 구독을 회복해 진짜 eligible·침묵이 되는 순간 옛 시각으로 즉발한다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    sched = _make_scheduler()
    subs = dict(DEFAULT_SUBS)
    subs["fire"] = 3                                  # 판정 불가(sub<5) — silent_suspect 항상 False
    subs["1004"] = 0                                   # 판정 불가(sub=0)
    sessions, last_tick = _build_pool({}, subs=subs)   # 나머지 6세션 eligible·전부 침묵

    # 원래도 suspect 가 될 수 없는 두 라벨 + 현재 세션 목록 밖(ghost)에 stale first_seen 사전 오염.
    sched._silent_inactive_first_seen.update({
        "fire": NOW - timedelta(seconds=500),
        "1004": NOW - timedelta(seconds=500),
        "ghost": NOW - timedelta(seconds=500),
    })

    result = _run_detect(sched, sessions, last_tick, NOW)

    assert result == [], f"6/8 eligible 전부 침묵 → 시장 침묵 기각 — got {result}"
    remaining = dict(sched._silent_inactive_first_seen)
    assert remaining == {"ghost": NOW - timedelta(seconds=500)}, (
        f"judged 안의 fire/1004 는 non-eligible 이어도 pop, judged 밖 ghost 는 무접촉 — "
        f"got {remaining}"
    )
    entered = _marker_lines(caplog, "entered")
    assert len(entered) == 1 and "reset=2" in entered[0], (
        f"reset 은 실제로 pop 된 라벨 수(fire+1004=2) — got {entered}"
    )
