"""cycle364 S1 Red — CAP: 캡처 라벨 가드 (A1 과 같은 배포에 반드시 함께 — 설계 §0-5).

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.5 · §6.2 CAP · M6.
사용자 결정 카드3 (가) — 수동 캡처(파라미터 없음)는 오늘 라벨, 기준일이 다른 전략은 건너뛰고
응답 메시지로 알린다(응답 키 불변).

왜 필요한가: A1 뒤에는 저녁부터 다음 부팅까지 메모리 funnel 이 「다음 거래일 목록」이다. 지금
수동 캡처는 메모리를 **오늘 날짜의 확정 행**으로 저장하므로, 밤에 누르면 내일 목록이 오늘
09:35 확정 행을 덮는다(기록이 거짓이 된다). 09:30 자동 캡처도 같은 헬퍼를 쓴다.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약
────────────────────────────────────────────────────────────────────────────
- `scheduler.capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None)` —
  `label = target_date or 오늘(KST)`. 모든 INSERT 의 `target_date = label`.
- 전략마다 leaf `funnel_capture.capture_skip_reason(strategy, label, today) -> str | None`:
    meta(dict) 있고 ok=False            → "prepare_failed"
    meta(dict) 있고 as_of ≠ label       → "as_of_mismatch"
    meta(dict) 있고 as_of == label      → None(캡처)
    meta 없음(속성 부재 또는 **dict 아님** — MagicMock 자동 속성 포함) ∧ label == today → None
    meta 없음 ∧ label ≠ today           → "no_meta"
  (meta = wrapper 가 남기는 `strategy._live_prepare_meta`)
- 캡처 완료 로그(`[funnel_snapshot] 캡처 완료 …`)에 `skipped=<sid:사유,…>` 를 덧붙인다.
- 09:30 자동(`_auto_capture_funnel_snapshots`) = `target_date=오늘`, 확정.
- 수동 `POST /api/strategy-funnel/snapshot`(파라미터 없음) = 오늘 라벨 + 가드. 밤에(메모리 D+1)
  누르면 저장 0 + `message` 에 메모리 목록의 기준일(as_of)을 적어 「오늘 날짜로 저장하지
  않았다」고 알린다. 응답 `data` 키(`target_date`·`saved_count`·`count`) 불변.

Red 유효성: 현행 헬퍼는 `target_date` 를 받지 않고(TypeError) meta 를 보지 않는다(항상 저장).

────────────────────────────────────────────────────────────────────────────
🔁 round 2 (R3 — 라벨 가드의 진행 중 틈 · 자정 뒤 확정 캡처)
────────────────────────────────────────────────────────────────────────────
- `capture_skip_reason(strategy, label, today, *, is_provisional)` — 판정이 캡처 종류를 안다.
  `capture_funnel_snapshots` 는 자기 `is_provisional` 을 그대로 넘긴다.
    meta(dict) 있고 ok=False                          → "prepare_failed"
    meta(dict) 있고 ok 가 True 가 아님(None = 진행 중) → "in_progress"
    meta(dict) 있고 as_of ≠ label                      → "as_of_mismatch"
    **확정 캡처(is_provisional=False) ∧ meta.phase == "evening"** → 건너뜀(사유 문자열은 자유)
    그 밖(as_of == label)                              → None(캡처)
  (meta 없음 규칙은 그대로.) 왜: 00:00~부팅 사이 수동 캡처는 label = 새 오늘 = 저녁 meta 의
  as_of 라 「일치」로 통과해 **저녁 미리보기를 확정 행으로** 저장했다 — 다음 날 ④ 는
  `is_provisional is True` 만 보므로 `evening=absent` 가 되고 07:55 레거시 잠정 캡처는 ③-b 에
  조용히 거부된다. 09:30 자동 캡처도 같은 규칙(부팅이 다시 준비하지 않은 비활성 전략의 저녁 목록은
  확정으로 저장하지 않는다 — 그 전략은 전날 밤의 잠정 행이 남는다).

────────────────────────────────────────────────────────────────────────────
🔁 round 3 (F4 — 수동 캡처 응답이 건너뛴 전략과 사유를 말한다)
────────────────────────────────────────────────────────────────────────────
- 라우트 docstring 은 「건너뛰면 응답 message 가 알린다」고 하는데 실제 message 는 `as_of ≠ 오늘`
  만 다뤘다. 자정 뒤(`evening_preview_reject` 로 전 전략 건너뜀)에는 「0개 snapshot 저장」 한
  줄뿐이라 운영자가 이유를 모른다. `in_progress`·`prepare_failed` 도 이름이 안 나왔다.
- 계약: `capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None,
  skipped_out: dict | None = None) -> int` — `skipped_out` 이 dict 면 건너뛴 전략마다
  `skipped_out[sid] = 사유`(완료 로그 `skipped=` 와 같은 사유 문자열)를 채운다. 반환(int)·기존
  호출자(09:30 자동·저녁 A1)는 불변.
- 수동 라우트 message 는 건너뛴 전략을 `sid:사유` 토큰으로 적는다(사유 = `in_progress` ·
  `prepare_failed` · `as_of_mismatch` · `evening_preview_reject` · `no_meta`). 응답 `data` 키
  (`target_date`·`saved_count`·`count`) 불변, 기존 기준일 문구(카드3)도 유지.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_D = date(2026, 9, 22)
_D_NEXT = date(2026, 9, 23)


def _leaf():
    try:
        import src.engine.funnel_capture as fc
    except ImportError as exc:  # pragma: no cover - Red
        pytest.fail(f"src/engine/funnel_capture.py 미구현 (Red — cycle364 §2.5): {exc}")
    return fc


def _meta(as_of, ok=True, phase="evening"):
    now = datetime(2026, 9, 22, 21, 1, tzinfo=KST)
    return {"as_of": as_of, "phase": phase, "started_at": now, "finished_at": now, "ok": ok}


class _S:
    def __init__(self, sid, meta=None):
        self.strategy_id = sid
        self.config = SimpleNamespace(enabled=True)
        self._funnel_steps = [{
            "step_no": 1, "step_name": "s1", "step_conditions": None,
            "survived": [{"ticker": "990101", "name": ""}], "survived_count": 1,
            "excluded": [], "excluded_count": 0,
        }]
        if meta is not None:
            self._live_prepare_meta = meta

    def get_scanned_tickers(self):
        return ["990101"]


class _Reg:
    def __init__(self, strategies):
        self._s = list(strategies)

    def all(self):
        return list(self._s)


@pytest.fixture
def inserts(monkeypatch):
    rows: list[dict] = []

    async def _insert(**kw):
        rows.append(kw)
        return {"id": f"r{len(rows)}"}

    monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", _insert)
    return rows


# ══════════════════════════════════════════════════════════════════════
# capture_skip_reason — 4갈래 + dict 아님
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "meta,label,want",
    [
        (_meta(_D_NEXT, ok=False), _D_NEXT, "prepare_failed"),
        (_meta(_D_NEXT), _D, "as_of_mismatch"),
        (_meta(_D_NEXT), _D_NEXT, None),
        (None, _D, None),
        (None, _D_NEXT, "no_meta"),
    ],
    ids=["failed", "mismatch", "match", "no_meta_today", "no_meta_future"],
)
def test_cap_1_skip_reason_when_meta_and_label_then_table(meta, label, want):
    s = _S("vcp_breakout", meta=meta)
    assert _leaf().capture_skip_reason(s, label, _D, is_provisional=True) == want


def test_cap_1c_signature_when_inspected_then_is_provisional_keyword():
    import inspect

    p = inspect.signature(_leaf().capture_skip_reason).parameters.get("is_provisional")
    assert p is not None and p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD), (
        "capture_skip_reason 이 캡처 종류(`is_provisional`)를 받아야 한다 (R3)"
    )


@pytest.mark.parametrize("is_provisional", [True, False], ids=["provisional", "confirmed"])
@pytest.mark.parametrize("label", [_D, _D_NEXT], ids=["label_today", "label_next"])
def test_cap_1d_skip_reason_when_prepare_in_progress_then_in_progress(label, is_provisional):
    """R3 — `ok is None`(시작 스탬프만 있고 아직 안 끝남) → "in_progress". as_of 가 라벨과 같아도."""
    meta = {"as_of": label, "phase": "evening", "started_at": datetime(2026, 9, 22, 21, 0, tzinfo=KST),
            "ok": None}
    s = _S("vcp_breakout", meta=meta)
    assert _leaf().capture_skip_reason(s, label, _D, is_provisional=is_provisional) == "in_progress"


@pytest.mark.parametrize(
    "phase,is_provisional,skipped",
    [
        ("evening", False, True),          # 자정 뒤 수동·09:30 자동 확정 캡처 — 저녁 미리보기 금지
        ("evening", True, False),          # 저녁 A1 자기 캡처(잠정) — 허용
        ("boot", False, False),            # 부팅 목록의 09:30 확정 — 허용
        ("reprepare_legacy", False, False),  # +600초 레거시(오늘) 뒤 확정 — 허용
        ("intraday_empty", False, False),
    ],
)
def test_cap_1e_skip_reason_when_confirmed_capture_and_evening_meta_then_skipped(phase, is_provisional, skipped):
    today = _D_NEXT  # 자정이 지나 새 오늘 = 저녁 meta 의 as_of
    meta = _meta(_D_NEXT, phase=phase)
    got = _leaf().capture_skip_reason(_S("kojiro", meta=meta), today, today, is_provisional=is_provisional)
    if skipped:
        assert got, (
            f"확정 캡처가 저녁 미리보기(phase={phase})를 오늘 확정 행으로 저장하려 한다 (R3)"
        )
    else:
        assert got is None, f"phase={phase} is_provisional={is_provisional} 는 캡처 대상: {got!r}"


def test_cap_1b_skip_reason_when_meta_attr_is_not_dict_then_treated_as_absent():
    """MagicMock 전략은 `_live_prepare_meta` 를 자동 속성(MagicMock)으로 돌려준다 — 기존 캡처
    테스트 수십 건이 그런 가짜를 쓴다. dict 가 아니면 「meta 없음」이다."""
    fc = _leaf()
    m = MagicMock()
    m.strategy_id = "bull_flag_breakout"
    for prov in (True, False):
        assert fc.capture_skip_reason(m, _D, _D, is_provisional=prov) is None
        assert fc.capture_skip_reason(m, _D_NEXT, _D, is_provisional=prov) == "no_meta"


# ══════════════════════════════════════════════════════════════════════
# capture_funnel_snapshots(target_date=) — 라벨 가드 배선
# ══════════════════════════════════════════════════════════════════════
def test_cap_2_signature_when_inspected_then_target_date_keyword_default_none():
    import inspect

    from src.engine.scheduler import capture_funnel_snapshots

    p = inspect.signature(capture_funnel_snapshots).parameters.get("target_date")
    assert p is not None and p.kind is p.KEYWORD_ONLY and p.default is None, (
        "capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None) (Red — §2.5)"
    )


async def test_cap_3_when_label_future_then_only_matching_meta_saved_with_that_date(inserts, caplog):
    from src.engine.scheduler import capture_funnel_snapshots

    caplog.set_level(logging.INFO)
    good = _S("volatility_breakout", meta=_meta(_D_NEXT))
    stale = _S("kojiro", meta=_meta(_D, phase="boot"))
    failed = _S("donchian_swing", meta=_meta(_D_NEXT, ok=False))
    bare = _S("momentum")
    with freeze_time("2026-09-22T21:01:00+09:00"):
        saved = await capture_funnel_snapshots(
            _Reg([good, stale, failed, bare]), is_provisional=True, target_date=_D_NEXT,
        )
    assert {r["strategy_id"] for r in inserts} == {"volatility_breakout"}, (
        f"미래 라벨은 as_of 가 같은 전략만 (M6) — 실측 {sorted({r['strategy_id'] for r in inserts})}"
    )
    assert {r["target_date"] for r in inserts} == {_D_NEXT}
    assert saved == len(inserts)
    done = [
        r.getMessage() for r in caplog.records
        if r.getMessage().startswith("[funnel_snapshot] 캡처 완료")
    ]
    assert done, "캡처 완료 로그가 없다"
    for token in ("kojiro:as_of_mismatch", "donchian_swing:prepare_failed", "momentum:no_meta"):
        assert token in done[-1], f"완료 로그 `skipped=` 에 {token} 가 없다: {done[-1]}"


async def test_cap_4_when_label_today_and_meta_is_tomorrow_then_not_saved(inserts):
    """밤(21:40)에 오늘 라벨로 캡처 → 메모리 목록(D+1)이 오늘 행을 덮지 않는다."""
    from src.engine.scheduler import capture_funnel_snapshots

    s = _S("vcp_breakout", meta=_meta(_D_NEXT))
    with freeze_time("2026-09-22T21:40:00+09:00"):
        saved = await capture_funnel_snapshots(_Reg([s]), is_provisional=False)
    assert inserts == [] and saved == 0, "오늘 라벨에 내일 목록을 저장했다 (§0-5)"


async def test_cap_5_when_legacy_magicmock_strategy_and_label_today_then_saved(inserts):
    """레거시·테스트 가짜 호환 — meta 없음 + 오늘 라벨 = 현행대로 캡처."""
    from src.engine.scheduler import capture_funnel_snapshots

    m = MagicMock()
    m.strategy_id = "bull_flag_breakout"
    m._funnel_steps = []
    m.get_scanned_tickers = MagicMock(return_value=["990101"])
    with freeze_time("2026-09-22T09:30:00+09:00"):
        saved = await capture_funnel_snapshots(_Reg([m]), is_provisional=False)
    assert saved == 1 and inserts[0]["step_no"] == 99 and inserts[0]["target_date"] == _D


async def test_cap_6_auto_0930_when_called_then_target_date_today_confirmed(monkeypatch):
    from src.engine.scheduler import TradingScheduler

    mock = AsyncMock(return_value=0)
    monkeypatch.setattr("src.engine.scheduler.capture_funnel_snapshots", mock)
    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = _Reg([])
    with freeze_time("2026-09-22T09:30:05+09:00"):
        await sched._auto_capture_funnel_snapshots()
    kwargs = mock.await_args.kwargs
    assert kwargs.get("is_provisional") is False
    assert kwargs.get("target_date") == _D, f"09:30 자동 캡처는 target_date=오늘을 넘긴다 (실측 {kwargs})"


# ══════════════════════════════════════════════════════════════════════
# 수동 캡처 라우트 — 카드3 (가)
# ══════════════════════════════════════════════════════════════════════
async def test_cap_7_manual_route_at_night_when_memory_is_next_session_then_zero_saved_and_message(monkeypatch, inserts):
    import src.engine.scheduler as sched_mod
    from src.routes.strategy_funnel import trigger_snapshot

    monkeypatch.setattr(
        sched_mod.trading_scheduler, "registry",
        _Reg([_S("volatility_breakout", meta=_meta(_D_NEXT)), _S("kojiro", meta=_meta(_D_NEXT))]),
    )
    with freeze_time("2026-09-22T21:40:00+09:00"):
        resp = await trigger_snapshot()
    assert inserts == [], "밤 수동 캡처가 내일 목록을 오늘 확정 행으로 저장했다 (카드3)"
    assert set(resp.data) == {"target_date", "saved_count", "count"}, "응답 키 불변"
    assert resp.data["target_date"] == "2026-09-22"
    assert resp.data["saved_count"] == 0 and resp.data["count"] == 0
    assert "2026-09-23" in (resp.message or ""), (
        f"응답 메시지가 메모리 목록의 기준일을 알려야 한다 (카드3): {resp.message!r}"
    )


async def test_cap_8_manual_route_after_boot_when_memory_is_today_then_saved(monkeypatch, inserts):
    import src.engine.scheduler as sched_mod
    from src.routes.strategy_funnel import trigger_snapshot

    monkeypatch.setattr(
        sched_mod.trading_scheduler, "registry",
        _Reg([_S("volatility_breakout", meta=_meta(_D, phase="boot"))]),
    )
    with freeze_time("2026-09-22T10:00:00+09:00"):
        resp = await trigger_snapshot()
    assert resp.data["saved_count"] == 2 and {r["target_date"] for r in inserts} == {_D}
    assert all(r["is_provisional"] is False for r in inserts), "수동 캡처는 확정(현행 유지)"


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 2 — R3 배선: 진행 중 · 자정 뒤
# ══════════════════════════════════════════════════════════════════════
async def test_cap_9_manual_capture_during_evening_prepare_then_in_progress_strategy_not_saved(monkeypatch, inserts):
    """21:00 A1 준비 도중(전략 A 가 prepare 안에 있다) 수동 캡처(오늘 라벨·확정)를 누른다.
    meta 를 끝난 뒤에만 찍으면 A 는 아직 부팅 meta(as_of=D, ok=True)라 **반쯤 만든 D+1 목록이
    D 확정 행으로** 저장되고, ③-b 는 확정→확정을 허용해 D 의 09:35 행을 덮는다 (R3)."""
    import asyncio

    import src.engine.funnel_capture as fc
    from src.engine.scheduler import capture_funnel_snapshots

    gate, started = asyncio.Event(), asyncio.Event()

    class _Gated(_S):
        async def prepare(self, **kw):
            started.set()
            await gate.wait()

    a = _Gated("donchian_swing", meta=_meta(_D, phase="boot"))
    with freeze_time("2026-09-22T21:00:30+09:00", real_asyncio=True):
        task = asyncio.create_task(fc.live_prepare_many([a], as_of=_D_NEXT, phase="evening"))
        await asyncio.wait_for(started.wait(), timeout=5)
        saved = await capture_funnel_snapshots(_Reg([a]), is_provisional=False)
        gate.set()
        await task
    assert inserts == [] and saved == 0, (
        f"준비 도중의 전략을 확정 행으로 저장했다 (실측 {[(r['strategy_id'], r['step_no']) for r in inserts]})"
    )


async def test_cap_10_manual_route_after_midnight_when_memory_is_evening_preview_then_zero_saved(monkeypatch, inserts):
    """00:30(D+1) — 저녁 meta 의 as_of(D+1) = 새 오늘 = 라벨이라 「일치」다. 그래도 확정 캡처는
    저녁 미리보기를 저장하지 않는다(R3). 응답 키는 불변."""
    import src.engine.scheduler as sched_mod
    from src.routes.strategy_funnel import trigger_snapshot

    monkeypatch.setattr(
        sched_mod.trading_scheduler, "registry",
        _Reg([_S("volatility_breakout", meta=_meta(_D_NEXT)), _S("kojiro", meta=_meta(_D_NEXT))]),
    )
    with freeze_time("2026-09-23T00:30:00+09:00"):
        resp = await trigger_snapshot()
    assert inserts == [], "자정 뒤 수동 캡처가 저녁 미리보기를 오늘 확정 행으로 저장했다 (R3)"
    assert set(resp.data) == {"target_date", "saved_count", "count"}
    assert resp.data["target_date"] == "2026-09-23" and resp.data["saved_count"] == 0
    # 🔁 round 3 (F4) — 「0개 저장」 한 줄로 끝나면 운영자는 이유를 모른다.
    msg = resp.message or ""
    for sid in ("volatility_breakout", "kojiro"):
        assert f"{sid}:evening_preview_reject" in msg, (
            f"자정 뒤 수동 캡처 message 가 건너뛴 전략·사유(`{sid}:evening_preview_reject`)를 말하지 "
            f"않는다 (F4): {msg!r}"
        )


async def test_cap_11_auto_0930_when_strategy_still_has_evening_meta_then_not_saved_confirmed(inserts):
    """09:30 자동(확정) — 부팅이 다시 준비하지 않은(비활성) 전략의 저녁 meta 는 확정 저장 대상이
    아니다. 부팅 meta 전략은 그대로 저장된다."""
    from src.engine.scheduler import capture_funnel_snapshots

    booted = _S("volatility_breakout", meta=_meta(_D_NEXT, phase="boot"))
    evening_only = _S("vcp_breakout", meta=_meta(_D_NEXT, phase="evening"))
    with freeze_time("2026-09-23T09:30:05+09:00"):
        await capture_funnel_snapshots(_Reg([booted, evening_only]), is_provisional=False, target_date=_D_NEXT)
    assert {r["strategy_id"] for r in inserts} == {"volatility_breakout"}, (
        f"확정 캡처가 저녁 미리보기를 저장했다: {sorted({r['strategy_id'] for r in inserts})}"
    )


async def test_cap_12_evening_provisional_capture_when_evening_meta_then_saved(inserts):
    """대조 — 저녁 A1 자신의 잠정 캡처는 저녁 meta 를 저장한다(R3 가 막는 것은 확정뿐)."""
    from src.engine.scheduler import capture_funnel_snapshots

    s = _S("vcp_breakout", meta=_meta(_D_NEXT, phase="evening"))
    with freeze_time("2026-09-22T21:01:30+09:00"):
        saved = await capture_funnel_snapshots(_Reg([s]), is_provisional=True, target_date=_D_NEXT)
    assert saved == 2 and {r["target_date"] for r in inserts} == {_D_NEXT}


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 3 — F4 건너뛴 전략·사유 노출
# ══════════════════════════════════════════════════════════════════════
def test_cap_13a_signature_when_inspected_then_skipped_out_keyword_default_none():
    import inspect

    from src.engine.scheduler import capture_funnel_snapshots

    p = inspect.signature(capture_funnel_snapshots).parameters.get("skipped_out")
    assert p is not None and p.kind is p.KEYWORD_ONLY and p.default is None, (
        "capture_funnel_snapshots(registry, *, is_provisional=False, target_date=None, "
        "skipped_out=None) (F4)"
    )


async def test_cap_13_when_skipped_out_given_then_filled_with_sid_to_reason(inserts):
    """F4 — 헬퍼가 전략별 건너뜀 사유를 호출자에게 넘긴다(반환 int 는 그대로)."""
    from src.engine.scheduler import capture_funnel_snapshots

    good = _S("volatility_breakout", meta=_meta(_D_NEXT))
    stale = _S("kojiro", meta=_meta(_D, phase="boot"))
    failed = _S("donchian_swing", meta=_meta(_D_NEXT, ok=False))
    running = _S("vcp_breakout", meta={**_meta(_D_NEXT), "ok": None, "finished_at": None})
    bare = _S("momentum")
    out: dict = {}
    with freeze_time("2026-09-22T21:01:00+09:00"):
        saved = await capture_funnel_snapshots(
            _Reg([good, stale, failed, running, bare]), is_provisional=True, target_date=_D_NEXT,
            skipped_out=out,
        )
    assert isinstance(saved, int) and saved == len(inserts) == 2, (saved, len(inserts))
    assert out == {
        "kojiro": "as_of_mismatch",
        "donchian_swing": "prepare_failed",
        "vcp_breakout": "in_progress",
        "momentum": "no_meta",
    }, f"건너뛴 전략·사유가 호출자에게 안 넘어왔다 (F4): {out}"


async def test_cap_14_manual_route_when_strategies_skipped_for_each_reason_then_message_names_them(monkeypatch, inserts):
    """F4 — 낮(10:00) 수동 캡처: 저장된 전략 1 + 사유별 건너뜀 3(in_progress · prepare_failed ·
    as_of_mismatch). message 가 건너뛴 전략마다 `sid:사유` 를 적는다. 응답 키 불변."""
    import src.engine.scheduler as sched_mod
    from src.routes.strategy_funnel import trigger_snapshot

    monkeypatch.setattr(
        sched_mod.trading_scheduler, "registry",
        _Reg([
            _S("volatility_breakout", meta=_meta(_D, phase="boot")),
            _S("kojiro", meta={**_meta(_D, phase="intraday_empty"), "ok": None, "finished_at": None}),
            _S("donchian_swing", meta=_meta(_D, ok=False, phase="presubscribe")),
            _S("vcp_breakout", meta=_meta(_D_NEXT, phase="evening")),
        ]),
    )
    with freeze_time("2026-09-22T10:00:00+09:00"):
        resp = await trigger_snapshot()
    assert set(resp.data) == {"target_date", "saved_count", "count"}, "응답 키 불변"
    assert resp.data["saved_count"] == 2 and {r["strategy_id"] for r in inserts} == {"volatility_breakout"}
    msg = resp.message or ""
    for token in ("kojiro:in_progress", "donchian_swing:prepare_failed", "vcp_breakout:as_of_mismatch"):
        assert token in msg, f"수동 캡처 message 에 건너뜀 `{token}` 이 없다 (F4): {msg!r}"
    assert "volatility_breakout:" not in msg, f"저장된 전략을 건너뜀으로 적었다: {msg!r}"
    assert "2026-09-23" in msg, f"기준일 문구(카드3)는 유지한다: {msg!r}"
