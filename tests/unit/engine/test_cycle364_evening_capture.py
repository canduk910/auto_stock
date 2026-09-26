"""cycle364 S1 Red — 새 leaf `src/engine/funnel_capture.py`: RES · 라이브 준비 wrapper · EVE(21:00 저녁 A1).

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.2 · §2.4 · §2.5 · §4.4 · §6.2
(RES · EVE · LOCK). 사용자 결정 카드2 (가) = 21:00 + 20:30 일봉 적재 성공 마커 대기(30초 폴링,
21:15 까지 없으면 WARNING 과 함께 건너뜀). S1 만 — 아침 ②③ 판정·비상 캡처·전략 단위
마감은 S2(이 파일 밖).

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약 (이 파일이 고정한다)
────────────────────────────────────────────────────────────────────────────
leaf `src.engine.funnel_capture` (8영역 import 0 · never-raise):
- `@dataclass(frozen=True) class AsOf: as_of, expected_head, mode, preview`
- `async def resolve_as_of(now_kst, mode) -> AsOf | None` — S1 은 `mode="evening"` 행만 잰다:
  오늘 개장 필수 → `as_of = next_trading_day(오늘)`, `expected_head = 오늘`, `preview=True`.
  오늘 휴장·모름, 다음 거래일 모름, 예외 → None(라벨을 추측하지 않는다).
- `async def live_prepare_one(strategy, *, phase) -> bool` — `strategy.prepare()` 를 **인자 없이**
  부른다(부팅·장중 경로 호출 형태 보존 — `async def prepare(self)` 가짜 전략이 깨지지 않는다).
  반환 = 성공 여부. 호출부(scheduler 07:59 사전 구독 2곳 · 5분 `_reprepare_breakout_if_empty`)는
  False 일 때 기존 실패 로그(`logger.exception` + `write_log("ERROR", …)`)를 그대로 남긴다.
- `async def live_prepare_many(strategies, *, as_of, phase, ...)` — `as_of` 가 있으면
  `prepare(as_of=as_of)`.
- 두 wrapper 모두: 예외 격리(raise 안 함) · 전략 객체에
  `_live_prepare_meta = {"as_of": date, "phase": str, "started_at": aware, "finished_at": aware,
  "ok": bool}` 기록(인자 없는 호출의 as_of = KST 오늘) · **라이브 prepare 는 한 번에 하나**
  (잠금 — 두 prepare 본문이 동시에 돌지 않는다).
- 시각 seam = `_now_kst()`(KST aware) · 대기 seam = `_sleep(secs)`. 이 파일은 freezegun
  (`real_asyncio=True`) 으로 시계를 얼리고 `asyncio.sleep`·`_sleep` 을 「시계를 그만큼
  전진시키는 가짜」로 바꾼다 — 벽시계 0, 실제 대기 0.

scheduler `TradingScheduler._evening_funnel_capture_once(self) -> dict` (task loop 의 once_callable,
본체는 leaf `evening_capture_once(scheduler)` 위임):
- **21:00(=`TIME_EVENING_FUNNEL_CAPTURE`) 이후 = 저녁 A1 경로**
  1. `resolve_as_of(now, "evening")` None → `[evening_funnel_capture] decision=skip
     reason=calendar_unknown`(오늘 휴장도 skip) — 준비·캡처 0.
  2. 적재 완료 신호 = `system_config.get_task_last_success("stock_master_daily_load")` 가
     **오늘 `TIME_STOCK_MASTER_DAILY_LOAD`(KST aware) 이상**. 참이면 즉시, 거짓이면 30초 간격
     재확인, 시작 마감 = 캡처 시각 + 15분(21:15)을 넘기면 WARNING `decision=skip
     reason=daily_load_not_done`. 🔴 `count_all() > 0` 은 신호가 아니다(M5).
  3. `live_prepare_many(registry.all() 우선순위, as_of=as_of, phase=…)` — 순서 VB → LTV →
     BFB → VCP → donchian → kojiro → momentum → 비활성(같은 순서).
  4. `capture_funnel_snapshots(registry, is_provisional=True, target_date=as_of)` — 준비 실패
     전략은 라벨 가드가 건너뛴다(`prepare_failed`).
  5. 요약 1행 `[evening_funnel_capture] decision=run|skip reason= as_of= expected_head=
     load_marker= daily_head= prepared= saved= skipped=<sid:사유,…>`. 반환 dict 는 어느
     경로든 `prepared`·`saved`(int) 키를 가진다(`[evening_funnel_capture_summary]` 형식 유지).
- **21:00 이전 = S1 에서 유지되는 부팅 +600초 즉시 1회(아침 재준비)** — 🔶 설계 문서가 S1 의
  이 경로를 명시하지 않아 tdd-engineer 가 보수적으로 고정했다(§6.4 「S2 첫 월요일: 07:5x 준비
  로그 0줄」 = S1 에서는 아직 돈다는 뜻): 미리보기 아님(as_of 없음/오늘) · 캡처 라벨 = 오늘 ·
  잠정 · 20:30 마커를 기다리지 않는다.

Red 유효성: leaf 부재 → `_leaf()` assert. scheduler once 는 현행(`count_all` 폴링·오늘 라벨)
으로 돌아 as_of·target_date·로그 단언에서 붉다.

────────────────────────────────────────────────────────────────────────────
🔁 round 2 (적대 검토 반영 — 메인 세션 결정 R3~R8, 사용자 승인 D3 범위)
────────────────────────────────────────────────────────────────────────────
- R3 `_live_prepare_meta` 는 prepare **시작 시점**에 `{as_of, phase, started_at, ok: None}` 로
  먼저 찍고, 끝나면 `ok`(bool)·`finished_at` 을 채운다(`started_at` 은 그대로). 끝난 뒤에만
  찍으면 21:00 준비 도중의 수동 캡처가 옛(부팅) meta 를 보고 반쯤 만든 D+1 목록을 D 확정 행으로
  저장한다.
- R4 달력(`resolve_as_of`)은 마커 대기 루프 **안에서** 시작 마감(21:15)까지 30초마다 다시 푼다.
  진짜 모름이 마감까지 이어지면 WARNING `decision=skip reason=calendar_unknown`, 오늘이 휴장이면
  대기 없이 INFO `decision=skip reason=today_closed`.
- R5 `[evening_funnel_capture]` 의 `daily_head=` 는 인덱스 컬럼 `max(bas_dd)`
  (`stock_master_daily.max_bas_dd()`)로 채운다 — 리터럴 `None` 금지. `count_all()` 은 부르지 않는다.
- R6 21:00 이전(부팅 +600초) 레거시 경로는 `[evening_funnel_capture] decision=legacy_reprepare`
  1행을 남긴다(§6.4 실측에서 A1 과 구별). docstring 에 「S1 임시 · S2 에서 제거 · 오후 재기동도
  예전처럼 재준비」를 적는다.
- R7 `live_prepare_one` 실패 로그는 새 마커 `[live_prepare]` 안에 옛 문구를 그대로 둔다(grep
  연속성): `phase=boot` → 「전략 prepare 실패」, 그 밖 → 「재 prepare 실패」.
- R8 마커 하한 — 같은 날짜라도 20:30 이전(부팅 보충 적재가 07:5x 에 쓴 마커)은 「오늘 적재
  완료」가 아니다(round-1 생존 돌연변이 Y6). 경계 20:29:59 도 미완료.

────────────────────────────────────────────────────────────────────────────
🔁 round 3 (메인 세션 결정 F5 · F8)
────────────────────────────────────────────────────────────────────────────
- F5 5분 재준비(`_reprepare_breakout_if_empty`, `phase=intraday_empty`) 실패 1건 = wrapper 의
  `[live_prepare] … 재 prepare 실패` ERROR **1행** + `write_log("ERROR", f"{sid} 재 prepare 실패")`
  **1건**. 호출부의 `logger.error("재 prepare 실패: …")` 는 걷는다 — 남기면 한 번의 실패가 ERROR
  3행(HEAD 는 2행)이 되고 문구가 두 번 찍혀 21:30 `top_patterns` 같은 grep 집계가 두 배로 센다.
- F8 R5 레거시 경로(21:00 이전 = 부팅 +600초 즉시 1회) 요약 행의 `daily_head=` 도 DB
  `max(bas_dd)` 값이다(round 2 생존 돌연변이 R5-legacy-head-None — 그 행만 단언이 없었다).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_HOLIDAYS = frozenset({date(2026, 9, 24), date(2026, 9, 25)})
_EVE_MARK = "[evening_funnel_capture] "
_ORIG_SLEEP = asyncio.sleep


def _leaf():
    try:
        import src.engine.funnel_capture as fc
    except ImportError as exc:  # pragma: no cover - Red
        pytest.fail(f"src/engine/funnel_capture.py 미구현 (Red — cycle364 §2.2): {exc}")
    return fc


def _set_leaf_attr(monkeypatch, name, value):
    """leaf 가 있으면 seam 을 바꾸고, 없으면(Red) 조용히 넘어간다 — 단언이 붉힌다."""
    try:
        import src.engine.funnel_capture as fc
    except ImportError:
        return
    monkeypatch.setattr(fc, name, value, raising=False)


def _fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"\b(\w+)=(\S*)", line))


def _eve_lines(caplog, level=logging.INFO):
    return [
        r for r in caplog.records
        if r.levelno >= level and r.getMessage().startswith(_EVE_MARK)
    ]


# ──────────────────────────── 가짜 세계 ────────────────────────────

class _Calendar:
    def __init__(self, *, unknown=frozenset(), holidays=_HOLIDAYS):
        self.unknown = set(unknown)
        self.holidays = set(holidays)

    async def __call__(self, d):
        if d in self.unknown:
            return None
        return d.weekday() < 5 and d not in self.holidays


class _Probe:
    """라이브 prepare 동시 실행 계측."""

    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.order: list[str] = []


class _FakeStrategy:
    def __init__(self, sid, *, enabled=True, fail=False, probe=None, gate=None, started=None):
        self.strategy_id = sid
        self.config = SimpleNamespace(strategy_id=sid, enabled=enabled, params={})
        self.state = SimpleNamespace(positions={})
        self._funnel_steps = [{
            "step_no": 1, "step_name": "s1", "step_conditions": None,
            "survived": [{"ticker": "990101", "name": ""}], "survived_count": 1,
            "excluded": [], "excluded_count": 0,
        }]
        self.calls: list[dict] = []
        self.fail = fail
        self.probe = probe or _Probe()
        self.gate = gate
        self.started = started

    async def prepare(self, **kwargs):
        self.calls.append(dict(kwargs))
        self.probe.order.append(self.strategy_id)
        self.probe.active += 1
        self.probe.max_active = max(self.probe.max_active, self.probe.active)
        try:
            if self.started is not None:
                self.started.set()
            if self.gate is not None:
                await self.gate.wait()
            for _ in range(3):
                await _ORIG_SLEEP(0)
            if self.fail:
                raise RuntimeError(f"{self.strategy_id} prepare 실패")
        finally:
            self.probe.active -= 1

    def get_scanned_tickers(self):
        return ["990101"]


class _NoArgStrategy(_FakeStrategy):
    """부팅 경로 테스트의 옛 가짜 — `prepare(self)` 에 인자가 없다."""

    async def prepare(self):  # noqa: D401 — 시그니처가 핵심
        self.calls.append({})


class _Registry:
    def __init__(self, strategies):
        self._s = list(strategies)

    def all(self):
        return list(self._s)

    def enabled(self):
        return [s for s in self._s if s.config.enabled]

    def get(self, sid):
        return next((s for s in self._s if s.strategy_id == sid), None)


def _scheduler(strategies):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = _Registry(strategies)
    sched._pending_next_day_clear = set()
    sched._phase = "idle"
    return sched


class _World:
    """시계(freezegun) · 가짜 대기 · 마커 · INSERT 기록을 한 번에 깐다."""

    def __init__(self, monkeypatch, frozen, *, marker=None, calendar=None, head=date(2026, 9, 22)):
        self.frozen = frozen
        self.sleeps: list[float] = []
        self.inserts: list[dict] = []
        self.marker_reads = 0
        self._marker = marker
        monkeypatch.setattr(
            "src.engine.trading_calendar._lookup_open", calendar or _Calendar(),
        )

        async def _fake_sleep(secs, *a, **k):
            self.sleeps.append(float(secs))
            frozen.tick(timedelta(seconds=float(secs)))
            await _ORIG_SLEEP(0)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        _set_leaf_attr(monkeypatch, "_sleep", _fake_sleep)

        async def _get_marker(label):
            if label != "stock_master_daily_load":
                return None
            self.marker_reads += 1
            m = self._marker
            return m(datetime.now(KST)) if callable(m) else m

        monkeypatch.setattr("src.db.system_config.get_task_last_success", _get_marker)
        _set_leaf_attr(monkeypatch, "get_task_last_success", _get_marker)

        async def _insert(**kw):
            self.inserts.append(kw)
            return {"id": f"row-{len(self.inserts)}"}

        monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", _insert)
        # 현행(Red) 경로의 count_all 폴링이 실 DB 로 나가지 않게 — 비어 있지 않다고 답한다.
        # 🔴 이 값이 참이어도 저녁 경로는 마커만 본다(M5).
        self.count_all = AsyncMock(return_value=1_000)
        monkeypatch.setattr("src.db.stock_master_daily.count_all", self.count_all)
        # R5 — `daily_head=` 는 인덱스 컬럼 `max(bas_dd)` 한 번. 실 DB 로 나가지 않게 대역.
        self.head = head
        self.max_bas_dd = AsyncMock(return_value=head)
        monkeypatch.setattr("src.db.stock_master_daily.max_bas_dd", self.max_bas_dd)
        _set_leaf_attr(monkeypatch, "max_bas_dd", self.max_bas_dd)

        async def _pg_fetchval(sql, *args):
            if "max(bas_dd)" in " ".join(str(sql).lower().split()):
                return head
            return None

        monkeypatch.setattr("src.db.pg.fetchval", _pg_fetchval)


# ══════════════════════════════════════════════════════════════════════
# RES — resolve_as_of(now, "evening")  (S1 행)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "now,want_as_of,want_head",
    [
        (datetime(2026, 9, 22, 21, 0, tzinfo=KST), date(2026, 9, 23), date(2026, 9, 22)),
        (datetime(2026, 9, 23, 21, 0, tzinfo=KST), date(2026, 9, 28), date(2026, 9, 23)),
        (datetime(2026, 9, 18, 21, 0, tzinfo=KST), date(2026, 9, 21), date(2026, 9, 18)),
    ],
    ids=["tue_to_wed", "wed_over_chuseok_to_mon", "fri_to_mon"],
)
async def test_res_1_evening_when_trading_day_then_next_session_preview(monkeypatch, now, want_as_of, want_head):
    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _Calendar())
    got = await _leaf().resolve_as_of(now, "evening")
    assert got is not None, f"{now:%m-%d} 저녁 = 거래일인데 None"
    assert (got.as_of, got.expected_head, got.mode, got.preview) == (
        want_as_of, want_head, "evening", True,
    ), got


@pytest.mark.parametrize(
    "now,unknown",
    [
        (datetime(2026, 9, 24, 21, 0, tzinfo=KST), frozenset()),                   # 오늘 휴장
        (datetime(2026, 9, 22, 21, 0, tzinfo=KST), frozenset({date(2026, 9, 22)})),  # 오늘 모름
        (datetime(2026, 9, 23, 21, 0, tzinfo=KST), frozenset({date(2026, 9, 24)})),  # 다음 거래일 모름
    ],
    ids=["today_holiday", "today_unknown", "next_unknown"],
)
async def test_res_2_evening_when_calendar_closed_or_unknown_then_none(monkeypatch, now, unknown):
    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _Calendar(unknown=unknown))
    assert await _leaf().resolve_as_of(now, "evening") is None, "모르면 라벨을 붙이지 않는다 (§2.2)"


async def test_res_3_evening_when_lookup_raises_then_none_never_raise(monkeypatch):
    async def _boom(_d):
        raise RuntimeError("CTCA0903R 장애")

    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", _boom)
    assert await _leaf().resolve_as_of(datetime(2026, 9, 22, 21, 0, tzinfo=KST), "evening") is None


# ══════════════════════════════════════════════════════════════════════
# LP — 라이브 준비 wrapper (호출 형태 · meta · 예외 격리 · 잠금)
# ══════════════════════════════════════════════════════════════════════
async def test_lp_1_live_prepare_one_when_called_then_prepare_without_args_and_meta_today():
    fc = _leaf()
    s = _NoArgStrategy("volatility_breakout")
    with freeze_time("2026-09-22T07:50:00+09:00", real_asyncio=True):
        ok = await fc.live_prepare_one(s, phase="boot")
    assert ok is True, "wrapper 는 성공 여부(bool)를 돌려준다 — 호출부의 기존 실패 로그를 보존하려면 필요하다"
    assert s.calls == [{}], "부팅·장중 경로는 `prepare()` 를 인자 없이 부른다 (§2.1 호출 형태 보존)"
    meta = getattr(s, "_live_prepare_meta", None)
    assert isinstance(meta, dict), "wrapper 가 `_live_prepare_meta` dict 를 남겨야 한다 (§2.5)"
    assert meta.get("as_of") == date(2026, 9, 22), f"인자 없는 준비의 기준일 = KST 오늘: {meta!r}"
    assert meta.get("phase") == "boot" and meta.get("ok") is True, meta
    for key in ("started_at", "finished_at"):
        ts = meta.get(key)
        assert isinstance(ts, datetime) and ts.utcoffset() is not None, f"{key} 는 aware datetime: {ts!r}"
    assert meta["started_at"] <= meta["finished_at"]


async def test_lp_2_live_prepare_one_when_prepare_raises_then_isolated_and_ok_false():
    fc = _leaf()
    s = _FakeStrategy("kojiro", fail=True)
    with freeze_time("2026-09-22T07:50:00+09:00", real_asyncio=True):
        ok = await fc.live_prepare_one(s, phase="boot")  # raise 금지
    assert ok is False, (
        "실패는 False 로 알린다 — 5분 재준비 호출부가 이 값으로 기존 ERROR system_logs "
        "(`test_scan_loop_reprepare::test_vb_prepare_raises_is_swallowed_with_error_log`)를 계속 남긴다"
    )
    assert s._live_prepare_meta.get("ok") is False


async def test_lp_3_live_prepare_many_when_as_of_given_then_passed_and_recorded():
    fc = _leaf()
    a, b = _FakeStrategy("volatility_breakout"), _FakeStrategy("donchian_swing", fail=True)
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True):
        await fc.live_prepare_many([a, b], as_of=date(2026, 9, 23), phase="evening")
    assert a.calls == [{"as_of": date(2026, 9, 23)}] and b.calls == [{"as_of": date(2026, 9, 23)}]
    assert a._live_prepare_meta["as_of"] == date(2026, 9, 23) and a._live_prepare_meta["ok"] is True
    assert b._live_prepare_meta["ok"] is False, "한 전략 실패가 다른 전략을 끊지 않고 meta 로 남는다"


async def test_lp_4_two_live_prepares_when_concurrent_then_never_overlap():
    """§4.4 — 라이브 준비는 한 번에 하나. 부팅·장중 재준비·저녁이 같은 전략 객체를 동시에 쓰면
    `_funnel_steps`·`_candidates` 가 섞인다."""
    fc = _leaf()
    probe = _Probe()
    gate, started = asyncio.Event(), asyncio.Event()
    a = _FakeStrategy("volatility_breakout", probe=probe, gate=gate, started=started)
    b = _FakeStrategy("long_tail_volatility", probe=probe)
    with freeze_time("2026-09-22T10:00:00+09:00", real_asyncio=True):
        ta = asyncio.create_task(fc.live_prepare_one(a, phase="intraday_empty"))
        await started.wait()
        tb = asyncio.create_task(fc.live_prepare_one(b, phase="presubscribe"))
        for _ in range(10):
            await _ORIG_SLEEP(0)
        assert b.calls == [], "앞선 라이브 준비가 끝나기 전에 두 번째 준비가 시작됐다 (잠금 부재)"
        gate.set()
        await asyncio.gather(ta, tb)
    assert probe.max_active == 1 and b.calls == [{}]


# ══════════════════════════════════════════════════════════════════════
# EVE — 21:00 저녁 A1 1회 (scheduler once → leaf)
# ══════════════════════════════════════════════════════════════════════
_TODAY_MARK = "2026-09-22T20:32:10.634156+09:00"


def _strategies(probe=None):
    probe = probe or _Probe()
    return [
        _FakeStrategy("volatility_breakout", probe=probe),
        _FakeStrategy("kojiro", probe=probe),
    ]


async def test_eve_1_when_load_marker_present_at_2100_then_preview_and_capture_next_session(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=_TODAY_MARK)
        result = await sched._evening_funnel_capture_once()

    for s in strategies:
        assert s.calls == [{"as_of": date(2026, 9, 23)}], (
            f"{s.strategy_id}: 저녁 준비는 prepare(as_of=다음 거래일) 1회 (실측 {s.calls})"
        )
    assert w.inserts, "저녁 캡처가 한 행도 쓰지 않았다"
    assert {kw["target_date"] for kw in w.inserts} == {date(2026, 9, 23)}, (
        "스냅샷 날짜 = as_of(다음 거래일) (§2.5)"
    )
    assert all(kw["is_provisional"] is True for kw in w.inserts), "저녁 캡처는 잠정"
    assert w.sleeps == [], "21:00 에 이미 마커가 있으면 곧바로 진행한다(대기 0)"
    assert isinstance(result, dict) and result.get("prepared") == 2
    assert result.get("saved") == len(w.inserts)
    lines = [r.getMessage() for r in _eve_lines(caplog)]
    assert len(lines) == 1, f"요약 1행 계약 (실측 {lines})"
    f = _fields(lines[0])
    assert f.get("decision") == "run", lines[0]
    assert f.get("as_of") == "2026-09-23" and f.get("expected_head") == "2026-09-22", lines[0]
    assert f.get("prepared") == "2" and f.get("saved") == str(len(w.inserts)), lines[0]
    for key in ("reason", "load_marker", "daily_head", "skipped"):
        assert key in f, f"요약 행에 `{key}=` 가 없다: {lines[0]}"


async def test_eve_1b_when_wednesday_before_chuseok_then_as_of_monday(monkeypatch):
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-23T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker="2026-09-23T20:32:10+09:00")
        await sched._evening_funnel_capture_once()
    assert strategies[0].calls == [{"as_of": date(2026, 9, 28)}]
    assert {kw["target_date"] for kw in w.inserts} == {date(2026, 9, 28)}


async def test_eve_2_when_marker_exactly_at_load_slot_then_run(monkeypatch):
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker="2026-09-22T20:30:00+09:00")
        await sched._evening_funnel_capture_once()
    assert strategies[0].calls == [{"as_of": date(2026, 9, 23)}], "마커 = 오늘 20:30:00 정각도 완료다(≥)"
    assert w.sleeps == []


async def test_eve_3_when_marker_arrives_during_wait_then_polls_every_30s_and_runs(monkeypatch):
    """전날 마커 → 30초 간격 재확인 → 21:03 에 오늘 마커가 생기면 그때 진행."""
    strategies = _strategies()
    sched = _scheduler(strategies)

    def _marker(now):
        if now >= datetime(2026, 9, 22, 21, 3, tzinfo=KST):
            return "2026-09-22T21:02:40+09:00"
        return "2026-09-19T20:32:10+09:00"

    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=_marker)
        await sched._evening_funnel_capture_once()
        finished_at = datetime.now(KST)
    assert w.sleeps and set(w.sleeps) == {30.0}, f"폴링 간격은 30초 (실측 {w.sleeps})"
    assert datetime(2026, 9, 22, 21, 3, tzinfo=KST) <= finished_at < datetime(2026, 9, 22, 21, 4, tzinfo=KST)
    assert strategies[0].calls == [{"as_of": date(2026, 9, 23)}]


async def test_eve_4_when_no_marker_by_2115_then_skip_warning_without_prepare(monkeypatch, caplog):
    """카드2 (가) — 21:15 까지 마커가 없으면 건너뛴다. `count_all()` 이 1,000 이어도(M5)."""
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=None)
        result = await sched._evening_funnel_capture_once()
        gave_up_at = datetime.now(KST)
    assert all(s.calls == [] for s in strategies), "적재 없이 준비하면 ①′ 폴백이 수천 건 KIS 호출이 된다"
    assert w.inserts == [], "건너뛴 날 내일 라벨 부실 목록을 남기면 안 된다"
    assert w.sleeps and set(w.sleeps) == {30.0}, w.sleeps
    assert datetime(2026, 9, 22, 21, 15, tzinfo=KST) <= gave_up_at <= datetime(
        2026, 9, 22, 21, 15, 30, tzinfo=KST,
    ), f"시작 마감 21:15 를 넘기자마자 멈춰야 한다 (실측 {gave_up_at.time()})"
    warns = [r.getMessage() for r in _eve_lines(caplog, logging.WARNING)]
    assert len(warns) == 1, warns
    f = _fields(warns[0])
    assert (f.get("decision"), f.get("reason")) == ("skip", "daily_load_not_done"), warns[0]
    assert result == {**result, "prepared": 0, "saved": 0}, result


async def test_eve_5_when_today_closed_then_skip_info_today_closed_without_wait(monkeypatch, caplog):
    """R4 — 오늘이 휴장(추석 09-24)이면 기다릴 이유가 없다: 대기 0 · INFO `reason=today_closed`
    (`calendar_unknown` 과 섞지 않는다 — 휴장일 수동 기동 뒤에도 WARNING 이 쌓이지 않는다)."""
    caplog.set_level(logging.INFO)
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-24T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker="2026-09-23T20:32:10+09:00")
        result = await sched._evening_funnel_capture_once()
    assert all(s.calls == [] for s in strategies) and w.inserts == []
    assert w.sleeps == [], "휴장일은 달력을 다시 풀 이유도, 마커를 기다릴 이유도 없다"
    lines = _eve_lines(caplog)
    assert len(lines) == 1, [r.getMessage() for r in lines]
    f = _fields(lines[0].getMessage())
    assert (f.get("decision"), f.get("reason")) == ("skip", "today_closed"), lines[0].getMessage()
    assert lines[0].levelno == logging.INFO, "오늘 휴장은 정상 경로 — INFO"
    assert result.get("prepared") == 0 and result.get("saved") == 0, result


@pytest.mark.parametrize(
    "unknown",
    [frozenset({date(2026, 9, 22)}), frozenset({date(2026, 9, 23)})],
    ids=["today_unknown", "next_unknown"],
)
async def test_eve_5b_when_calendar_unknown_until_deadline_then_retry_every_30s_and_warning(monkeypatch, caplog, unknown):
    """R4 — 21:00 한 번의 CTCA0903R 장애(5초 타임아웃·None — 90초 음성 캐시)로 그날 저녁 미리보기를
    통째로 버리지 않는다. 마감 21:15 까지 30초마다 다시 풀고, 끝내 모르면 WARNING 1행."""
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=_TODAY_MARK, calendar=_Calendar(unknown=unknown))
        result = await sched._evening_funnel_capture_once()
        gave_up_at = datetime.now(KST)
    assert all(s.calls == [] for s in strategies) and w.inserts == [], "모르면 라벨을 붙이지 않는다"
    assert len(w.sleeps) >= 10 and set(w.sleeps) == {30.0}, (
        f"달력을 한 번만 풀고 포기했다 — 30초 간격으로 마감까지 다시 풀어야 한다 (실측 {w.sleeps})"
    )
    assert datetime(2026, 9, 22, 21, 15, tzinfo=KST) <= gave_up_at <= datetime(
        2026, 9, 22, 21, 15, 30, tzinfo=KST,
    ), gave_up_at.time()
    warns = [r.getMessage() for r in _eve_lines(caplog, logging.WARNING)]
    assert len(warns) == 1, warns
    assert (_fields(warns[0]).get("decision"), _fields(warns[0]).get("reason")) == (
        "skip", "calendar_unknown",
    ), warns[0]
    assert result.get("prepared") == 0 and result.get("saved") == 0, result


async def test_eve_5c_when_calendar_recovers_before_deadline_then_runs(monkeypatch, caplog):
    """R4 — 21:02 에 휴장일 조회가 살아나면(음성 캐시 90초 뒤 재조회) 그날 미리보기를 한다."""
    caplog.set_level(logging.INFO)
    strategies = _strategies()
    sched = _scheduler(strategies)
    recovered = datetime(2026, 9, 22, 21, 2, tzinfo=KST)

    class _Flaky(_Calendar):
        async def __call__(self, d):
            if datetime.now(KST) < recovered:
                return None
            return await super().__call__(d)

    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=_TODAY_MARK, calendar=_Flaky())
        await sched._evening_funnel_capture_once()
        ended = datetime.now(KST)
    for s in strategies:
        assert s.calls == [{"as_of": date(2026, 9, 23)}], (
            f"{s.strategy_id}: 달력이 21:02 에 돌아왔는데 미리보기를 안 했다 (실측 {s.calls}) — 달력을 "
            "루프 밖에서 한 번만 풀었다"
        )
    assert {kw["target_date"] for kw in w.inserts} == {date(2026, 9, 23)}
    assert ended < datetime(2026, 9, 22, 21, 5, tzinfo=KST), ended.time()
    assert not _eve_lines(caplog, logging.WARNING), "회복한 날은 WARNING 이 없다"


async def test_eve_6_when_one_strategy_prepare_fails_then_capture_skips_it(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    ok = _FakeStrategy("volatility_breakout")
    bad = _FakeStrategy("donchian_swing", fail=True)
    sched = _scheduler([ok, bad])
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=_TODAY_MARK)
        result = await sched._evening_funnel_capture_once()
    assert {kw["strategy_id"] for kw in w.inserts} == {"volatility_breakout"}, (
        "준비 실패 전략의 (이전 상태) funnel 을 내일 라벨로 저장하면 안 된다 (§2.5 prepare_failed)"
    )
    assert bad._live_prepare_meta["ok"] is False and ok._live_prepare_meta["ok"] is True
    assert result.get("prepared") == 1
    line = [r.getMessage() for r in _eve_lines(caplog)][-1]
    assert "donchian_swing:prepare_failed" in _fields(line).get("skipped", ""), line


async def test_eve_7_when_run_then_priority_order_active_first(monkeypatch):
    probe = _Probe()
    ids = ["kojiro", "momentum", "volatility_breakout", "donchian_swing",
           "long_tail_volatility", "bull_flag_breakout", "vcp_breakout"]
    strategies = [
        _FakeStrategy(sid, probe=probe, enabled=(sid != "donchian_swing")) for sid in ids
    ]
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        _World(monkeypatch, fz, marker=_TODAY_MARK)
        await sched._evening_funnel_capture_once()
    assert probe.order == [
        "volatility_breakout", "long_tail_volatility", "bull_flag_breakout", "vcp_breakout",
        "kojiro", "momentum", "donchian_swing",
    ], f"준비 순서 (§2.4 — 활성 우선순 → 비활성): {probe.order}"


async def test_eve_8_when_evening_runs_then_concurrent_live_prepare_never_overlaps(monkeypatch):
    """저녁 준비 도중 5분 `_reprepare_breakout_if_empty` 같은 다른 라이브 준비가 끼어도 겹치지 않는다."""
    fc = _leaf()
    probe = _Probe()
    gate, started = asyncio.Event(), asyncio.Event()
    vb = _FakeStrategy("volatility_breakout", probe=probe, gate=gate, started=started)
    other = _FakeStrategy("long_tail_volatility", probe=probe)
    sched = _scheduler([vb])
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        _World(monkeypatch, fz, marker=_TODAY_MARK)
        t_eve = asyncio.create_task(sched._evening_funnel_capture_once())
        await asyncio.wait_for(started.wait(), timeout=5)
        t_other = asyncio.create_task(fc.live_prepare_one(other, phase="intraday_empty"))
        for _ in range(10):
            await _ORIG_SLEEP(0)
        assert other.calls == [], "저녁 준비 중에 다른 라이브 준비가 시작됐다 (잠금 부재)"
        gate.set()
        await asyncio.gather(t_eve, t_other)
    assert probe.max_active == 1


async def test_eve_9_morning_immediate_run_when_before_capture_time_then_legacy_today_reprepare(monkeypatch):
    """S1 에서 유지되는 부팅 +600초 즉시 1회(07:57) — 미리보기 아님 · 오늘 라벨 · 20:30 마커 대기 없음."""
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T07:57:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker="2026-09-19T20:32:10+09:00")
        await sched._evening_funnel_capture_once()
        ended = datetime.now(KST)
    for s in strategies:
        assert len(s.calls) == 1 and s.calls[0].get("as_of") in (None, date(2026, 9, 22)), (
            f"{s.strategy_id}: 아침 즉시 1회는 미리보기가 아니다 (실측 {s.calls})"
        )
    assert w.inserts and {kw["target_date"] for kw in w.inserts} == {date(2026, 9, 22)}
    assert all(kw["is_provisional"] is True for kw in w.inserts)
    assert 30.0 not in w.sleeps and ended < datetime(2026, 9, 22, 8, 5, tzinfo=KST), (
        f"아침 즉시 1회가 저녁 적재 마커를 기다렸다 (sleeps={w.sleeps[:5]}…, 종료 {ended.time()})"
    )


def test_eve_10_task_loop_summary_format_kept():
    """grep 연속성 — `[evening_funnel_capture_summary] prepared=%d saved=%d` 형식은 그대로."""
    import inspect

    import src.engine.data_load_tasks as dlt

    src = inspect.getsource(dlt.evening_funnel_capture_task_loop)
    assert '"[evening_funnel_capture_summary] prepared=%d saved=%d"' in src
    assert 'summary_keys=("prepared", "saved")' in src


def test_eve_11_capture_time_constant_is_2100():
    from src.engine.scheduler import TIME_EVENING_FUNNEL_CAPTURE

    assert TIME_EVENING_FUNNEL_CAPTURE == time(21, 0), (
        f"카드2 (가) — 저녁 캡처 21:00 (실측 {TIME_EVENING_FUNNEL_CAPTURE})"
    )


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 2 — R8 마커 하한 · R5 daily_head · R6 레거시 마커 · R3 시작 스탬프 · R7 실패 문구
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "marker",
    ["2026-09-22T07:52:30+09:00", "2026-09-22T20:29:59+09:00"],
    ids=["same_day_morning_catchup", "boundary_202959"],
)
async def test_eve_12_when_marker_is_today_but_before_2030_then_waits_and_skips(monkeypatch, caplog, marker):
    """R8 — 전날 적재가 실패해 부팅 보충 적재가 07:5x 에 **오늘 날짜** 마커를 쓴 뒤, 오늘 20:30
    적재가 또 실패한 날. 날짜만 비교하면(Y6) D-1 헤드로 미리보기를 돌려 ①′ KIS 폴백이 보조 풀로
    수천 건 나가고 내일 라벨 부실 목록이 남는다. 경계 20:29:59 도 미완료다(20:30:00 = 완료, EVE-2)."""
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=marker)
        await sched._evening_funnel_capture_once()
        gave_up_at = datetime.now(KST)
    assert all(s.calls == [] for s in strategies), (
        f"오늘 20:30 이전 마커({marker})를 적재 완료로 봤다 — 날짜만 비교했다 (Y6)"
    )
    assert w.inserts == []
    assert w.sleeps and set(w.sleeps) == {30.0}, w.sleeps
    assert datetime(2026, 9, 22, 21, 15, tzinfo=KST) <= gave_up_at <= datetime(
        2026, 9, 22, 21, 15, 30, tzinfo=KST,
    ), gave_up_at.time()
    warns = [_fields(r.getMessage()) for r in _eve_lines(caplog, logging.WARNING)]
    assert [(f.get("decision"), f.get("reason")) for f in warns] == [("skip", "daily_load_not_done")], warns


@pytest.mark.parametrize(
    "scenario",
    ["run", "daily_load_not_done", "calendar_unknown"],
)
async def test_eve_13_summary_line_when_logged_then_daily_head_is_db_max_bas_dd(monkeypatch, caplog, scenario):
    """R5 — `daily_head=` 는 인덱스 컬럼 `max(bas_dd)` 값이다(리터럴 None 금지 — 「새 칸은 값이
    찍히는지까지」). 첫 거래일 실측에서 D 봉이 적재됐는지 이 한 칸으로 확인한다."""
    caplog.set_level(logging.INFO)
    strategies = _strategies()
    sched = _scheduler(strategies)
    marker = None if scenario == "daily_load_not_done" else _TODAY_MARK
    calendar = _Calendar(unknown={date(2026, 9, 22)}) if scenario == "calendar_unknown" else None
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker=marker, calendar=calendar, head=date(2026, 9, 22))
        await sched._evening_funnel_capture_once()
    lines = [r.getMessage() for r in _eve_lines(caplog)]
    assert len(lines) == 1, lines
    assert _fields(lines[0]).get("daily_head") == "2026-09-22", (
        f"`daily_head=` 가 DB 헤드가 아니다: {lines[0]}"
    )
    assert w.count_all.await_count == 0, "헤드는 인덱스 `max(bas_dd)` 한 번 — 전 행 count_all 금지"


async def test_eve_14_legacy_immediate_run_when_before_2100_then_distinct_decision_line(monkeypatch, caplog):
    """R6 — 부팅 +600초 레거시 재준비(S1 임시)는 `decision=legacy_reprepare` 1행으로 A1 과 구별된다
    (§6.4 「16:20 에 준비 로그 0줄」 실측이 재기동 날 헷갈리지 않게)."""
    caplog.set_level(logging.INFO)
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T07:57:00+09:00", real_asyncio=True) as fz:
        _World(monkeypatch, fz, marker="2026-09-19T20:32:10+09:00")
        await sched._evening_funnel_capture_once()
    lines = [r.getMessage() for r in _eve_lines(caplog)]
    assert len(lines) == 1, f"레거시 경로 요약 1행 (실측 {lines})"
    assert _fields(lines[0]).get("decision") == "legacy_reprepare", lines[0]


def test_eve_15_legacy_branch_docstring_states_s1_interim():
    """R6 — `evening_capture_once` docstring 이 레거시 분기의 정체(S1 임시 = 부팅 +600초 즉시 1회,
    S2 에서 제거, 오후 재기동도 예전처럼 재준비)를 적는다 — 다음 사람이 지워도 되는지 판단한다."""
    doc = _leaf().evening_capture_once.__doc__ or ""
    for token in ("S1", "S2", "600", "재기동"):
        assert token in doc, f"`evening_capture_once` docstring 에 `{token}` 가 없다:\n{doc}"


async def test_lp_5_when_prepare_in_progress_then_meta_already_stamped_ok_none():
    """R3 — meta 는 prepare 시작 시점에 먼저 찍힌다. 옛 meta(부팅 as_of=D, ok=True)가 준비 도중에
    남아 있으면 그 사이의 캡처가 반쯤 만든 D+1 목록을 D 확정 행으로 저장한다."""
    fc = _leaf()
    gate, started = asyncio.Event(), asyncio.Event()
    s = _FakeStrategy("donchian_swing", gate=gate, started=started)
    s._live_prepare_meta = {
        "as_of": date(2026, 9, 22), "phase": "boot", "ok": True,
        "started_at": datetime(2026, 9, 22, 7, 45, 5, tzinfo=KST),
        "finished_at": datetime(2026, 9, 22, 7, 45, 20, tzinfo=KST),
    }
    with freeze_time("2026-09-22T21:00:00+09:00", real_asyncio=True):
        task = asyncio.create_task(fc.live_prepare_many([s], as_of=date(2026, 9, 23), phase="evening"))
        await asyncio.wait_for(started.wait(), timeout=5)
        mid = dict(s._live_prepare_meta)
        gate.set()
        await task
    assert mid.get("ok") is None, f"준비 도중 meta 의 ok 는 None(진행 중)이어야 한다: {mid!r}"
    assert (mid.get("as_of"), mid.get("phase")) == (date(2026, 9, 23), "evening"), mid
    st = mid.get("started_at")
    assert isinstance(st, datetime) and st.utcoffset() is not None and st.hour == 21, mid
    end = s._live_prepare_meta
    assert end["ok"] is True and end["started_at"] == st and end["finished_at"] >= st, end


@pytest.mark.parametrize(
    "phase,phrase",
    [
        ("boot", "전략 prepare 실패"),
        ("presubscribe", "재 prepare 실패"),
        ("intraday_empty", "재 prepare 실패"),
        ("evening", "재 prepare 실패"),
    ],
)
async def test_lp_6_when_prepare_fails_then_marker_line_keeps_old_phrase(caplog, phase, phrase):
    """R7 — grep 연속성: 옛 호출부 문구(boot_manager 「전략 prepare 실패」 · scheduler 「재 prepare
    실패」)를 새 마커 `[live_prepare]` 행 안에 그대로 둔다(호출부 except 는 죽은 코드라 걷는다)."""
    fc = _leaf()
    s = _FakeStrategy("kojiro", fail=True)
    with freeze_time("2026-09-22T07:50:00+09:00", real_asyncio=True):
        if phase == "evening":
            await fc.live_prepare_many([s], as_of=date(2026, 9, 23), phase=phase)
        else:
            await fc.live_prepare_one(s, phase=phase)
    errs = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.ERROR and r.getMessage().startswith("[live_prepare] ")
    ]
    assert len(errs) == 1, f"실패 1건 = `[live_prepare]` ERROR 1행 (실측 {errs})"
    assert phrase in errs[0] and "kojiro" in errs[0] and f"phase={phase}" in errs[0], errs[0]


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 3 — F8 레거시 요약 행 daily_head · F5 5분 재준비 실패 로그 1회
# ══════════════════════════════════════════════════════════════════════
async def test_eve_13b_legacy_summary_line_when_logged_then_daily_head_is_db_max_bas_dd(monkeypatch, caplog):
    """F8 — 부팅 +600초 레거시 행(`decision=legacy_reprepare`)의 `daily_head=` 도 DB 헤드다.
    화요일 07:57 = 전날(월) 봉까지 적재된 상태 → `daily_head=2026-09-21`. 리터럴 None 이면
    「재기동 날 아침 헤드가 어디까지 왔나」를 이 행으로 볼 수 없다(round 2 생존 돌연변이)."""
    caplog.set_level(logging.INFO)
    strategies = _strategies()
    sched = _scheduler(strategies)
    with freeze_time("2026-09-22T07:57:00+09:00", real_asyncio=True) as fz:
        w = _World(monkeypatch, fz, marker="2026-09-21T20:32:10+09:00", head=date(2026, 9, 21))
        await sched._evening_funnel_capture_once()
    lines = [r.getMessage() for r in _eve_lines(caplog)]
    assert len(lines) == 1, lines
    f = _fields(lines[0])
    assert f.get("decision") == "legacy_reprepare", lines[0]
    assert f.get("daily_head") == "2026-09-21", f"레거시 행 `daily_head=` 가 DB 헤드가 아니다 (F8): {lines[0]}"
    assert w.count_all.await_count == 0, "헤드는 인덱스 `max(bas_dd)` 한 번 — 전 행 count_all 금지"


class _EmptyFailing(_FakeStrategy):
    """후보가 비어 5분 재준비 대상이 되고, 그 prepare 가 터지는 전략."""

    def get_scanned_tickers(self):
        return []


async def test_lp_7_intraday_empty_when_prepare_fails_then_one_error_log_and_one_write_log(monkeypatch, caplog):
    """F5 — 실패 1건 = wrapper ERROR 1행 + write_log ERROR 1건(HEAD 와 같은 system_logs 1행).
    호출부가 `logger.error("재 prepare 실패: …")` 를 또 찍으면 같은 문구 ERROR 가 2행이다."""
    import src.engine.scheduler as sched_mod

    s = _EmptyFailing("volatility_breakout", fail=True)
    sched = _scheduler([s])
    written: list[tuple[str, str]] = []

    async def _write_log(level, message, *a, **k):
        written.append((level, message))

    monkeypatch.setattr(sched_mod, "write_log", _write_log)
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-22T10:05:00+09:00", real_asyncio=True):
        await sched._reprepare_breakout_if_empty()  # raise 금지
    assert len(s.calls) == 1, f"빈 후보 전략은 재준비 1회 (실측 {s.calls})"
    errs = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.ERROR and "재 prepare 실패" in r.getMessage()
    ]
    assert len(errs) == 1, (
        f"실패 1건에 「재 prepare 실패」 ERROR 가 {len(errs)}행 — 호출부 logger.error 중복 (F5): {errs}"
    )
    assert errs[0].startswith("[live_prepare] ") and "phase=intraday_empty" in errs[0], errs[0]
    err_rows = [(lv, m) for lv, m in written if lv == "ERROR"]
    assert err_rows == [("ERROR", "volatility_breakout 재 prepare 실패")], (
        f"system_logs ERROR 는 HEAD 와 같이 1행 (실측 {written})"
    )
