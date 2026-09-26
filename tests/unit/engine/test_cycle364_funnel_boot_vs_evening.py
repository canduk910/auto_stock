"""cycle364 S1 Red — ④ `[funnel_boot_vs_evening] phase=boot` 저녁 목록 ↔ 부팅 목록 대조 마커.

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §4.3 · §6.2 ④ · M11.
S1 은 `phase=boot` 만(S2 가 reprepare·emergency 를 더한다). 이 마커가 S2(평시 아침 재준비
0회 — 기능 비활성화급)의 판단 근거(평시 `same=1`)를 먼저 실측으로 확인해 준다.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약
────────────────────────────────────────────────────────────────────────────
- leaf `funnel_capture.emit_funnel_boot_vs_evening(scheduler, *, phase="boot") -> None`
  never-raise(전체 10초 상한). 배선 = `boot_manager.boot` 의 익일청산 DB 복구(`load_pending_ndc`)
  **뒤** 1곳(보유 ∪ 익일청산이 확정된 시점).
- 저녁 목록 = `src.db.strategy_funnel.list_snapshots(target_date=오늘)` 중
  `step_no == 99 ∧ is_provisional is True` 행의 `survived_tickers`(str 또는 {"ticker": …}) ·
  `evening_at` = 그 행의 `snapshot_at`.
- 부팅 목록 = 활성 전략(`registry.enabled()`)의 `get_scanned_tickers()`.
- 비교 집합 = 양쪽에서 **보유 ∪ 익일청산 제외** — 보유 = `registry.all()` 전략들의
  `state.positions` 합집합, 익일청산 = `scheduler._pending_next_day_clear`(튜플이면 [0]).
  (저녁엔 보호 종목이라 마스터 차단·가격 필터를 통과하고, 부팅엔 복구 전이라 보유 0 이다
  — 빼지 않으면 kojiro 가 늘 same=0 이다: M11). leaf 는 8영역(scanner 포함) import 0 이라
  scanner 헬퍼가 아니라 scheduler 에서 직접 모은다.
- 원인 힌트 seam = `funnel_capture._boot_vs_evening_hints(evening_at) -> dict`
  (`params_changed`·`bars_changed_after`·`sm_refreshed_after`·`head_now`, DB 3쿼리 — 종목 단위
  조회 금지). 이 파일은 seam 을 갈아 끼운다.
- 형식(전략당 1행): `[funnel_boot_vs_evening] phase=boot strategy= as_of= evening_at= evening_n=
  boot_n= same= added= removed= sample_added=<≤5> sample_removed=<≤5> held_excluded=
  params_changed= bars_changed_after= sm_refreshed_after= head_now=` — `evening_n`·`boot_n` 은
  보유 제외 **뒤** 비교 집합 크기. 기본 INFO, `same=0 ∧ 힌트 3개 전부 0` 일 때만 WARNING.
  저녁 행이 하나도 없으면 `evening=absent` 1행(INFO).

Red 유효성: leaf 부재 → `_leaf()` assert, 배선 부재 → AST assert.

────────────────────────────────────────────────────────────────────────────
🔁 round 2 (R2 — 적대 검토: 부팅 지연 · 힌트 창 · 조용한 실패)
────────────────────────────────────────────────────────────────────────────
- **배선** — ④ 는 동기 부팅 경로에서 돌지 않는다(`_boot()` 는 WebSocket 연결 **전**에 await
  된다 — 보유 중 재기동의 틱 공백을 늘린다). `boot_manager.boot` 는 익일청산 복구 뒤
  `funnel_capture.spawn_funnel_boot_vs_evening(scheduler, phase="boot")` 를 **await 없이** 1회
  부르고, 이 함수(일반 def)는 백그라운드 task 를 만들어 돌려준다. task 는 WebSocket 연결 단계가
  시작된 뒤(`scheduler._ws_task` 가 생긴 뒤)에만 ④ 본체(`emit_funnel_boot_vs_evening`)를 돈다.
  대기 seam = leaf `_sleep`.
- **힌트는 부팅당 1회** — 전략 루프 **앞**에서 한 번 계산해 모든 행이 같은 값을 쓴다.
  seam = `_boot_vs_evening_hints(evening_at, until)` — `evening_at` = 저녁 행들의 `snapshot_at`
  최솟값, `until` = 부팅 준비 시작 = `phase == "boot"` 인 `_live_prepare_meta["started_at"]`
  최솟값. 모든 창은 [evening_at, until) 로 묶는다 — 부팅 자신의 보유 종목 eager refresh
  (준비 **뒤**에 돈다)가 `sm_refreshed_after` 로 새면 월요일·연휴 뒤마다 WARNING 이 막힌다.
- `stock_master_daily` 의 `updated_at` 집계는 인덱스 컬럼 `bas_dd` 로 범위를 묶는다(약 35.7만 행
  전 행 스캔 금지 — `updated_at` 인덱스 없음, migration 033).
- **조용한 실패 금지** — 실패·타임아웃(`BOOT_VS_EVENING_TIMEOUT_SECS`, 10초)은 WARNING
  **정확히 1행** `[funnel_boot_vs_evening] phase=boot error=…` 에 못 낸 전략 id 를 적는다. 전략
  행은 서로 격리된다(한 전략의 실패가 다른 전략 행을 지우지 않는다). 저녁 목록 조회 실패를
  `evening=absent`(정상 부재)로 적지 않는다.

────────────────────────────────────────────────────────────────────────────
🔁 round 3 (메인 세션 결정 F1·F2·F3 — round 2 검토의 「조용한 실패」 잔여)
────────────────────────────────────────────────────────────────────────────
- **F1** production `src.db.strategy_funnel.list_snapshots` 는 DB 예외를 삼키고 `[]` 를 돌려준다
  — round 2 의 `error=list_snapshots_failed` 분기는 도달 불가였고, DB 장애가 INFO
  `evening=absent` 로 적혔다. 계약: `list_snapshots(*, target_date, strategy_id=None,
  raise_on_error=False)` — 기본값은 현행(삼키고 `[]`), `raise_on_error=True` 면 예외를 그대로
  전파한다. ④ `_emit` 은 `raise_on_error=True` 로 읽는다. 이 파일의 가짜 `list_snapshots` 는 실
  헬퍼를 흉내 낸다(플래그 없이 부르면 삼키고 `[]`). BOOT4-16 은 가짜 없이 **`src.db.pg.fetch`**
  를 터뜨려 실 헬퍼 경로 그대로 잰다.
- **F2** 힌트 쿼리 실패를 맨 `pass` 로 삼키지 않는다 — 힌트 호출 1회(부팅 1회)에서 **첫 실패**가
  나면 WARNING **정확히 1행** `[funnel_boot_vs_evening] phase=boot hint_error=<축> …` 을 남긴다
  (never-raise, 그 축 값은 `None`). 축 이름 = 힌트 키: `strategy_config` →
  `params_changed` · `stock_master_daily` → `bars_changed_after`(같은 쿼리의 `head_now` 도 None)
  · `stock_master` → `sm_refreshed_after`. 시그니처 = `_boot_vs_evening_hints(evening_at, until, *,
  phase="boot")`(인자 없이 부르면 `phase=boot`). 이 WARNING 은 ④ 실패(`error=`)가 아니다 —
  전략 행은 그대로 나가고 `\\berror=` 오류 행은 0 이다. 실 PG 의미(정수 개수·창 경계·head_now)는
  `tests/integration/test_cycle364_boot_vs_evening_hints_pg.py`.
- **F3** 백그라운드 task 위생 — leaf 모듈 전역 `_BG_TASKS: set` 에 spawn 한 task 를 넣고
  `add_done_callback(_BG_TASKS.discard)` 로 뺀다(`llm_buy_gate` 관례 — 강한 참조). WebSocket
  대기 루프는 (a) `getattr(scheduler, "_running", True)` 가 거짓이면 DB 를 건드리지 않고 조용히
  끝나고(정지·기동 실패 뒤 다음 기동에서 ④ 가 두 번 찍히지 않게) (b) **120초**(대기 seam
  `_sleep` 으로 잰 누적 대기 또는 `_now_kst()` 경과 — `loop.time()` 금지: 이 파일은 시계를
  freezegun 으로 전진시킨다) 안에 `_ws_task` 가 안 생기면 WARNING **1행**
  `[funnel_boot_vs_evening] phase=boot error=ws_not_started strategies=<못 낸 활성 전략>` 을 남기고
  끝난다.
"""

from __future__ import annotations

import ast
import inspect
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_TODAY = date(2026, 9, 23)
_EVE_AT = datetime(2026, 9, 22, 21, 1, 7, tzinfo=KST)
_MARK = "[funnel_boot_vs_evening] "
_ZERO_HINTS = {"params_changed": 0, "bars_changed_after": 0, "sm_refreshed_after": 0,
               "head_now": date(2026, 9, 22)}


def _leaf():
    try:
        import src.engine.funnel_capture as fc
    except ImportError as exc:  # pragma: no cover - Red
        pytest.fail(f"src/engine/funnel_capture.py 미구현 (Red — cycle364 §4.3): {exc}")
    return fc


def _fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"\b(\w+)=(\S*)", line))


class _S:
    def __init__(self, sid, scanned, *, enabled=True, positions=(), meta_offset_s=0, boom=False):
        self.strategy_id = sid
        self.config = SimpleNamespace(enabled=enabled)
        self.state = SimpleNamespace(positions={t: object() for t in positions})
        self._scanned = list(scanned)
        self._boom = boom
        self._live_prepare_meta = {
            "as_of": _TODAY, "phase": "boot",
            "started_at": datetime(2026, 9, 23, 7, 45, 11, tzinfo=KST) + timedelta(seconds=meta_offset_s),
            "finished_at": datetime(2026, 9, 23, 7, 46, 0, tzinfo=KST), "ok": True,
        }

    def get_scanned_tickers(self):
        if self._boom:
            raise RuntimeError(f"{self.strategy_id} get_scanned_tickers 실패")
        return list(self._scanned)


class _Reg:
    def __init__(self, strategies):
        self._s = list(strategies)

    def all(self):
        return list(self._s)

    def enabled(self):
        return [s for s in self._s if s.config.enabled]


def _row(sid, tickers, *, provisional=True, step_no=99, as_dict=False):
    survived = [{"ticker": t, "name": ""} for t in tickers] if as_dict else list(tickers)
    return {
        "target_date": _TODAY, "strategy_id": sid, "step_no": step_no,
        "is_provisional": provisional, "survived_tickers": survived,
        "survived_count": len(tickers), "snapshot_at": _EVE_AT,
    }


_BOOT_START = datetime(2026, 9, 23, 7, 45, 11, tzinfo=KST)  # `_S` 기본 부팅 meta started_at


async def _emit(monkeypatch, caplog, *, strategies, rows, hints=None, ndc=(), list_exc=None,
                hints_exc=None, hint_calls=None):
    fc = _leaf()

    async def _list(*, target_date, strategy_id=None, raise_on_error=False):
        assert target_date == _TODAY, f"저녁 목록은 target_date=오늘 행이다 (실측 {target_date})"
        if list_exc is not None:
            # 🔁 round 3 (F1) — 실 헬퍼를 흉내 낸다: 기본값은 예외를 삼키고 [] 를 돌려준다
            # (production `list_snapshots` 가 그렇다). `raise_on_error=True` 일 때만 전파된다.
            if raise_on_error:
                raise list_exc
            logging.getLogger("src.db.strategy_funnel").warning(
                "strategy_funnel list 실패 — target=%s strategy=%s err=%s", target_date, strategy_id, list_exc,
            )
            return []
        return [r for r in rows if strategy_id in (None, r["strategy_id"])]

    async def _hints(*args, **kwargs):
        if hint_calls is not None:
            hint_calls.append((args, kwargs))
        if hints_exc is not None:
            raise hints_exc
        return dict(hints if hints is not None else _ZERO_HINTS)

    monkeypatch.setattr("src.db.strategy_funnel.list_snapshots", _list)
    monkeypatch.setattr(fc, "list_snapshots", _list, raising=False)
    monkeypatch.setattr(fc, "_boot_vs_evening_hints", _hints, raising=False)
    sched = SimpleNamespace(registry=_Reg(strategies), _pending_next_day_clear=set(ndc))
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00"):
        await fc.emit_funnel_boot_vs_evening(sched, phase="boot")
    return [r for r in caplog.records if r.getMessage().startswith(_MARK)]


def _by_strategy(records):
    out = {}
    for r in records:
        f = _fields(r.getMessage())
        if "strategy" in f:
            out[f["strategy"]] = (r.levelno, f, r.getMessage())
    return out


async def test_boot4_1_when_only_held_differs_then_same_1_info(monkeypatch, caplog):
    """M11 — 저녁 kojiro 목록엔 보유(990106)가 held_only 로 있고 부팅(복구 전)엔 없다 → same=1."""
    k = _S("kojiro", ["990101", "990102"], positions=("990106",))
    recs = await _emit(monkeypatch, caplog, strategies=[k],
                       rows=[_row("kojiro", ["990101", "990102", "990106"])])
    lvl, f, line = _by_strategy(recs)["kojiro"]
    assert f.get("same") == "1", f"보유 제외 없이 비교하면 kojiro 가 늘 same=0 이다 (M11): {line}"
    assert f.get("held_excluded") == "1" and f.get("evening_n") == "2" and f.get("boot_n") == "2", line
    assert (f.get("added"), f.get("removed")) == ("0", "0"), line
    assert f.get("phase") == "boot" and f.get("as_of") == "2026-09-23", line
    assert f.get("evening_at", "").startswith("2026-09-22T21:01:07"), line
    assert lvl == logging.INFO, "same=1 은 INFO"


async def test_boot4_2_when_unexplained_difference_then_warning_with_samples(monkeypatch, caplog):
    vb = _S("volatility_breakout", ["990101", "990102", "990104"])
    recs = await _emit(monkeypatch, caplog, strategies=[vb],
                       rows=[_row("volatility_breakout", ["990101", "990102", "990103"], as_dict=True)])
    lvl, f, line = _by_strategy(recs)["volatility_breakout"]
    assert f.get("same") == "0" and f.get("added") == "1" and f.get("removed") == "1", line
    assert "990104" in f.get("sample_added", "") and "990103" in f.get("sample_removed", ""), line
    for key in ("params_changed", "bars_changed_after", "sm_refreshed_after", "head_now"):
        assert key in f, f"원인 힌트 `{key}=` 누락: {line}"
    assert lvl == logging.WARNING, "same=0 ∧ 힌트 전부 0 = 설명 안 되는 차이 → WARNING"


async def test_boot4_3_when_difference_explained_by_hint_then_info(monkeypatch, caplog):
    vb = _S("volatility_breakout", ["990101", "990104"])
    recs = await _emit(monkeypatch, caplog, strategies=[vb],
                       rows=[_row("volatility_breakout", ["990101", "990103"])],
                       hints={**_ZERO_HINTS, "bars_changed_after": 12})
    lvl, f, line = _by_strategy(recs)["volatility_breakout"]
    assert f.get("same") == "0" and f.get("bars_changed_after") == "12", line
    assert lvl == logging.INFO, "힌트가 설명하는 차이는 INFO"


async def test_boot4_4_when_next_day_clear_ticker_differs_then_excluded(monkeypatch, caplog):
    vb = _S("volatility_breakout", ["990101"])
    recs = await _emit(monkeypatch, caplog, strategies=[vb],
                       rows=[_row("volatility_breakout", ["990101", "990107"])],
                       ndc={("990107", "volatility_breakout")})
    _, f, line = _by_strategy(recs)["volatility_breakout"]
    assert f.get("same") == "1" and f.get("held_excluded") == "1", f"익일청산도 제외 대상: {line}"


async def test_boot4_5_when_no_evening_rows_then_single_absent_line(monkeypatch, caplog):
    vb = _S("volatility_breakout", ["990101"])
    recs = await _emit(monkeypatch, caplog, strategies=[vb], rows=[])
    msgs = [r.getMessage() for r in recs]
    assert msgs and all("evening=absent" in m for m in msgs), msgs
    assert not any("same=" in m for m in msgs), msgs
    assert all(r.levelno < logging.WARNING for r in recs), "저녁 행 부재(배포 첫날·저녁 실패)는 INFO"


async def test_boot4_6_when_only_confirmed_or_step_rows_then_not_an_evening_list(monkeypatch, caplog):
    """확정(`is_provisional=False`) 99행·단계 행은 저녁 목록이 아니다."""
    vb = _S("volatility_breakout", ["990101"])
    recs = await _emit(monkeypatch, caplog, strategies=[vb], rows=[
        _row("volatility_breakout", ["990101", "990102"], provisional=False),
        _row("volatility_breakout", ["990101", "990102"], step_no=3),
    ])
    msgs = [r.getMessage() for r in recs]
    assert msgs and all("evening=absent" in m for m in msgs), msgs


async def test_boot4_7_when_inactive_strategy_has_evening_row_then_not_compared(monkeypatch, caplog):
    vb = _S("volatility_breakout", ["990101"])
    off = _S("vcp_breakout", ["990101"], enabled=False)
    recs = await _emit(monkeypatch, caplog, strategies=[vb, off], rows=[
        _row("volatility_breakout", ["990101"]), _row("vcp_breakout", ["990109"]),
    ])
    assert set(_by_strategy(recs)) == {"volatility_breakout"}, "부팅 목록은 활성 전략만"


async def test_boot4_8_when_many_differences_then_samples_capped_at_5(monkeypatch, caplog):
    vb = _S("volatility_breakout", [])
    evening = [f"9902{i:02d}" for i in range(8)]
    recs = await _emit(monkeypatch, caplog, strategies=[vb], rows=[_row("volatility_breakout", evening)])
    _, f, line = _by_strategy(recs)["volatility_breakout"]
    assert f.get("removed") == "8", line
    sample = [t for t in f.get("sample_removed", "").split(",") if t]
    assert 1 <= len(sample) <= 5, f"sample 은 ≤5 (실측 {sample})"


@pytest.mark.parametrize(
    "kw", [{"list_exc": RuntimeError("pg down")}, {"hints_exc": RuntimeError("pg down")}],
    ids=["list_snapshots_raises", "hints_raise"],
)
async def test_boot4_9_when_sources_raise_then_never_raises_and_no_silent_absence(monkeypatch, caplog, kw):
    """R2 — never-raise 에 더해 「조용한 부재」 금지: 활성 전략마다 `strategy=` 행이 있거나
    오류 WARNING 1행에 이름이 있어야 한다."""
    vb = _S("volatility_breakout", ["990101"])
    kj = _S("kojiro", ["990102"])
    recs = await _emit(monkeypatch, caplog, strategies=[vb, kj], rows=[
        _row("volatility_breakout", ["990101"]), _row("kojiro", ["990102"]),
    ], **kw)
    errs = [r.getMessage() for r in recs if r.levelno >= logging.WARNING and "error=" in r.getMessage()]
    assert len(errs) <= 1, errs
    emitted = set(_by_strategy(recs))
    for sid in ("volatility_breakout", "kojiro"):
        assert sid in emitted or (errs and sid in errs[0]), (
            f"{sid}: 행도 없고 오류 WARNING 에도 없다 — S2 판정 근거가 조용히 사라진다 (R2) {errs}"
        )
    if "list_exc" in kw:
        msgs = [r.getMessage() for r in recs]
        assert not any("evening=absent" in m for m in msgs), (
            f"저녁 목록 조회 실패를 정상 부재(`evening=absent`)로 적었다 (R2): {msgs}"
        )
        assert len(errs) == 1 and errs[0].startswith("[funnel_boot_vs_evening] phase=boot error="), errs


def _boot_fn():
    import src.engine.boot_manager as bm

    tree = ast.parse(Path(inspect.getfile(bm)).read_text(encoding="utf-8"))
    return next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "boot"
    )


def _calls(fn, name):
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            if (isinstance(f, ast.Name) and f.id == name) or (
                isinstance(f, ast.Attribute) and f.attr == name
            ):
                out.append(n)
    return out


def test_boot4_10_wiring_when_boot_runs_then_spawned_once_after_ndc_restore_not_awaited():
    """R2 — `_boot()` 은 WebSocket 연결 전에 await 된다. ④ 를 여기서 기다리면(최대 10초 + 전 행
    스캔) 보유 중 재기동의 틱 공백이 그만큼 길어진다."""
    boot_fn = _boot_fn()
    awaited = {
        id(n.value) for n in ast.walk(boot_fn)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
    }
    for name in ("emit_funnel_boot_vs_evening", "_emit", "_boot_vs_evening_hints"):
        hits = [c.lineno for c in _calls(boot_fn, name) if id(c) in awaited]
        assert hits == [], f"boot 이 ④(`{name}`)를 동기로 await 한다 (줄 {hits}) — 백그라운드로 (R2)"
    spawns = _calls(boot_fn, "spawn_funnel_boot_vs_evening")
    ndc = [c.lineno for c in _calls(boot_fn, "load_pending_ndc")]
    assert len(spawns) == 1, f"boot 안 `spawn_funnel_boot_vs_evening` 호출은 정확히 1곳 (실측 {[c.lineno for c in spawns]})"
    assert id(spawns[0]) not in awaited, "spawn 은 await 하지 않는다(task 를 만들어 돌려줄 뿐)"
    assert ndc and spawns[0].lineno > max(ndc), "대조는 익일청산 복구 **뒤** (보유 ∪ 익일청산 확정 시점, §4.3)"


def test_boot4_10b_spawner_when_inspected_then_plain_function():
    fc = _leaf()
    fn = getattr(fc, "spawn_funnel_boot_vs_evening", None)
    assert callable(fn), "leaf `spawn_funnel_boot_vs_evening(scheduler, *, phase)` 미구현 (R2)"
    assert not inspect.iscoroutinefunction(fn), "spawner 는 일반 def — task 를 만들어 곧바로 돌려준다"
    assert getattr(fc, "BOOT_VS_EVENING_TIMEOUT_SECS", None) == 10, "④ 전체 상한 10초(§4.3) 상수"


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 2 — R2 행위
# ══════════════════════════════════════════════════════════════════════
async def test_boot4_11_when_three_strategies_then_hints_once_with_min_evening_at_and_boot_start(monkeypatch, caplog):
    """힌트는 부팅당 1회 — 전략마다 3쿼리(6전략 18쿼리)가 아니다. 창 = [저녁 행 snapshot_at 최솟값,
    부팅 준비 시작(`phase=boot` meta started_at 최솟값))."""
    calls: list = []
    early = _EVE_AT
    rows = [
        _row("volatility_breakout", ["990101"]),
        {**_row("kojiro", ["990102"]), "snapshot_at": early + timedelta(seconds=40)},
        {**_row("vcp_breakout", ["990103"]), "snapshot_at": early + timedelta(seconds=75)},
    ]
    strategies = [
        _S("volatility_breakout", ["990101"], meta_offset_s=2),
        _S("kojiro", ["990102"], meta_offset_s=0),
        _S("vcp_breakout", ["990103"], meta_offset_s=30),
    ]
    recs = await _emit(monkeypatch, caplog, strategies=strategies, rows=rows, hint_calls=calls)
    assert len(_by_strategy(recs)) == 3
    assert len(calls) == 1, f"힌트를 전략마다 다시 계산했다 (호출 {len(calls)}회) — 부팅당 1회 (R2)"
    args, kwargs = calls[0]
    got = list(args) + list(kwargs.values())
    assert got and got[0] == early, f"창 하한 = 저녁 행 snapshot_at 최솟값 {early} (실측 {got})"
    assert _BOOT_START in got, (
        f"창 상한 = 부팅 준비 시작 {_BOOT_START} — 부팅 자신의 eager refresh 를 세지 않는다 (실측 {got})"
    )


class _AnyRow(dict):
    def __missing__(self, key):
        return date(2026, 9, 22) if ("head" in key or "bas_dd" in key) else 0

    def get(self, key, default=None):  # noqa: D401 — asyncpg Record 흉내
        return self[key]


class _PgSpy:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return date(2026, 9, 22) if "max(bas_dd)" in " ".join(sql.lower().split()) else 0

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return _AnyRow()

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return []


async def test_boot4_12_hints_sql_when_run_then_windows_bounded_and_daily_scan_indexed(monkeypatch):
    fc = _leaf()
    spy = _PgSpy()
    for name in ("fetchval", "fetchrow", "fetch"):
        monkeypatch.setattr(f"src.db.pg.{name}", getattr(spy, name))
    until = _BOOT_START
    with freeze_time("2026-09-23T07:46:30+09:00"):
        out = await fc._boot_vs_evening_hints(_EVE_AT, until)
    for key in ("params_changed", "bars_changed_after", "sm_refreshed_after", "head_now"):
        assert key in out, f"힌트 `{key}` 누락: {out}"
    assert 1 <= len(spy.calls) <= 4, f"힌트 DB 쿼리는 3개(+헤드 1) 이내 (실측 {len(spy.calls)})"
    windowed = [(q, a) for q, a in spy.calls if "updated_at" in q or "refreshed_at" in q]
    assert windowed, "시각 창 쿼리가 없다"
    for q, a in windowed:
        flat = " ".join(q.split())
        assert _EVE_AT in a and until in a, (
            f"창이 [evening_at, 부팅 준비 시작) 로 묶이지 않았다 — args={a} sql={flat}"
        )
        lo_ph = f"${list(a).index(_EVE_AT) + 1}"
        hi_ph = f"${list(a).index(until) + 1}"
        assert re.search(r">=?\s*" + re.escape(lo_ph) + r"(?!\d)", flat), (
            f"하한 `> {lo_ph}`(evening_at) 비교가 SQL 에 없다: {flat}"
        )
        assert re.search(r"<\s*" + re.escape(hi_ph) + r"(?!\d)", flat), (
            f"상한 `< {hi_ph}`(부팅 준비 시작) 비교가 SQL 에 없다 — 부팅 eager refresh 가 샌다: {flat}"
        )
    for q, a in spy.calls:
        low = " ".join(q.lower().split())
        if "stock_master_daily" in low and "updated_at" in low:
            where = low.split(" where ", 1)
            assert len(where) == 2 and "bas_dd" in where[1], (
                f"stock_master_daily updated_at 집계가 인덱스 컬럼 bas_dd 로 범위를 묶지 않는다 "
                f"(전 행 스캔): {low}"
            )


async def test_boot4_13_when_hints_hang_past_timeout_then_one_warning_listing_all(monkeypatch, caplog):
    """R2 — 10초 상한에 걸리면 DEBUG 로 삼키지 않는다: WARNING 1행에 못 낸 전략 전부."""
    import asyncio

    fc = _leaf()
    monkeypatch.setattr(fc, "BOOT_VS_EVENING_TIMEOUT_SECS", 0.05, raising=False)

    async def _hang(*a, **k):
        await asyncio.Event().wait()

    async def _list(*, target_date, strategy_id=None, raise_on_error=False):
        return [_row("volatility_breakout", ["990101"]), _row("kojiro", ["990102"])]

    monkeypatch.setattr("src.db.strategy_funnel.list_snapshots", _list)
    monkeypatch.setattr(fc, "list_snapshots", _list, raising=False)
    monkeypatch.setattr(fc, "_boot_vs_evening_hints", _hang)
    sched = SimpleNamespace(
        registry=_Reg([_S("volatility_breakout", ["990101"]), _S("kojiro", ["990102"])]),
        _pending_next_day_clear=set(),
    )
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00", real_asyncio=True):
        await asyncio.wait_for(fc.emit_funnel_boot_vs_evening(sched, phase="boot"), timeout=5)
    warns = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith("[funnel_boot_vs_evening] phase=boot error=")
    ]
    assert len(warns) == 1, f"타임아웃은 WARNING 정확히 1행 (실측 {warns})"
    for sid in ("volatility_breakout", "kojiro"):
        assert sid in warns[0], f"못 낸 전략 `{sid}` 가 오류 행에 없다: {warns[0]}"


async def test_boot4_14_when_one_strategy_line_fails_then_others_emitted_and_one_warning(monkeypatch, caplog):
    """R2 — 전략 행은 서로 격리된다. 한 전략의 실패가 남은 전략 행을 지우지 않는다."""
    recs = await _emit(monkeypatch, caplog, strategies=[
        _S("volatility_breakout", ["990101"]),
        _S("kojiro", ["990102"], boom=True),
        _S("vcp_breakout", ["990103"]),
    ], rows=[
        _row("volatility_breakout", ["990101"]), _row("kojiro", ["990102"]), _row("vcp_breakout", ["990103"]),
    ])
    assert set(_by_strategy(recs)) == {"volatility_breakout", "vcp_breakout"}, (
        f"kojiro 실패가 다른 전략 행까지 지웠다: {sorted(_by_strategy(recs))}"
    )
    errs = [r.getMessage() for r in recs if r.levelno >= logging.WARNING and "error=" in r.getMessage()]
    assert len(errs) == 1 and errs[0].startswith("[funnel_boot_vs_evening] phase=boot error="), errs
    assert "kojiro" in errs[0], errs[0]


async def test_boot4_15_spawned_task_when_ws_not_started_then_waits_and_runs_after(monkeypatch, caplog):
    """R2 — spawn 은 곧바로 task 를 돌려주고, task 는 WebSocket 연결 단계(`_ws_task`)가 생기기
    전에는 DB 를 건드리지 않는다. 연결 단계가 시작되면 ④ 를 낸다."""
    import asyncio

    fc = _leaf()
    orig_sleep = asyncio.sleep
    list_calls: list = []

    async def _fast_sleep(*a, **k):
        await orig_sleep(0)

    monkeypatch.setattr(fc, "_sleep", _fast_sleep, raising=False)
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    async def _list(*, target_date, strategy_id=None, raise_on_error=False):
        list_calls.append(target_date)
        return [_row("volatility_breakout", ["990101"])]

    async def _hints(*a, **k):
        return dict(_ZERO_HINTS)

    monkeypatch.setattr("src.db.strategy_funnel.list_snapshots", _list)
    monkeypatch.setattr(fc, "list_snapshots", _list, raising=False)
    monkeypatch.setattr(fc, "_boot_vs_evening_hints", _hints)
    sched = SimpleNamespace(
        registry=_Reg([_S("volatility_breakout", ["990101"])]),
        _pending_next_day_clear=set(), _ws_task=None, _phase="booting",
    )
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00", real_asyncio=True):
        task = fc.spawn_funnel_boot_vs_evening(sched, phase="boot")
        assert isinstance(task, asyncio.Task), f"spawn 은 asyncio.Task 를 돌려준다 (실측 {task!r})"
        for _ in range(50):
            await orig_sleep(0)
        assert list_calls == [] and not task.done(), (
            "WebSocket 연결 단계 전에 ④ 가 DB 를 읽었다 — 부팅 경로의 틱 공백을 늘린다 (R2)"
        )
        sched._ws_task = asyncio.get_running_loop().create_future()
        sched._phase = "presubscribe_wait"
        await asyncio.wait_for(task, timeout=5)
    assert list_calls, "연결 단계가 시작된 뒤에도 ④ 가 돌지 않았다"
    assert "volatility_breakout" in _by_strategy(
        [r for r in caplog.records if r.getMessage().startswith(_MARK)]
    )


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 3 — F1 저녁 목록 조회 실패가 `evening=absent` 로 둔갑하지 않는다
# ══════════════════════════════════════════════════════════════════════
def _sched(strategies, **extra):
    return SimpleNamespace(registry=_Reg(strategies), _pending_next_day_clear=set(), **extra)


async def _zero_hints(*a, **k):
    return dict(_ZERO_HINTS)


async def test_boot4_16_when_db_fetch_fails_through_real_helper_then_warning_not_absent(monkeypatch, caplog):
    """F1 — 가짜 `list_snapshots` 없이 실 헬퍼 경로 그대로: `src.db.pg.fetch` 가 터진다.

    production `list_snapshots` 는 예외를 삼키고 `[]` 를 돌려주므로, ④ 가 기본값으로 부르면 DB
    장애가 INFO `evening=absent`(= 「저녁 캡처가 없었다」)로 적힌다 — S1→S2 판정 근거를 읽는
    사람이 DB 장애를 저녁 캡처 부재로 오독한다(round 2 검토 finding 1)."""
    fc = _leaf()
    fetch_sql: list[str] = []

    async def _boom(sql, *args):
        fetch_sql.append(" ".join(str(sql).split()))
        raise RuntimeError("pg down")

    monkeypatch.setattr("src.db.pg.fetch", _boom)
    monkeypatch.setattr(fc, "_boot_vs_evening_hints", _zero_hints)
    caplog.set_level(logging.INFO)
    sched = _sched([_S("volatility_breakout", ["990101"]), _S("kojiro", ["990102"])])
    with freeze_time("2026-09-23T07:46:30+09:00"):
        await fc.emit_funnel_boot_vs_evening(sched, phase="boot")
    assert fetch_sql and "strategy_funnel_snapshots" in fetch_sql[0], (
        f"④ 가 저녁 목록을 `strategy_funnel_snapshots` 에서 읽지 않았다 (실측 {fetch_sql})"
    )
    mine = [r for r in caplog.records if r.getMessage().startswith(_MARK)]
    msgs = [r.getMessage() for r in mine]
    assert not any("evening=absent" in m for m in msgs), (
        f"DB 장애를 정상 부재(`evening=absent`)로 적었다 — list_snapshots 가 예외를 삼킨다 (F1): {msgs}"
    )
    errs = [r.getMessage() for r in mine if r.levelno >= logging.WARNING and re.search(r"\berror=", r.getMessage())]
    assert len(errs) == 1, f"조회 실패는 WARNING 정확히 1행 (실측 {msgs})"
    assert errs[0].startswith("[funnel_boot_vs_evening] phase=boot error=list_snapshots_failed"), errs[0]
    for sid in ("volatility_breakout", "kojiro"):
        assert sid in errs[0], f"못 낸 전략 `{sid}` 가 오류 행에 없다: {errs[0]}"


async def test_boot4_17_when_db_fetch_returns_rows_through_real_helper_then_normal_lines(monkeypatch, caplog):
    """F1 대조 — 전파형으로 바꿔도 정상 경로는 그대로(실 헬퍼 → `pg.fetch` 행 → 전략 행)."""
    fc = _leaf()
    binds: list[tuple] = []

    async def _fetch(sql, *args):
        binds.append(args)
        return [_row("volatility_breakout", ["990101"])]

    monkeypatch.setattr("src.db.pg.fetch", _fetch)
    monkeypatch.setattr(fc, "_boot_vs_evening_hints", _zero_hints)
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00"):
        await fc.emit_funnel_boot_vs_evening(_sched([_S("volatility_breakout", ["990101"])]), phase="boot")
    assert binds and _TODAY in binds[0], f"저녁 목록 target_date 바인딩 = 오늘 (실측 {binds})"
    lvl, f, line = _by_strategy([r for r in caplog.records if r.getMessage().startswith(_MARK)])[
        "volatility_breakout"
    ]
    assert f.get("same") == "1" and lvl == logging.INFO, line


async def test_boot4_18_list_snapshots_when_raise_on_error_then_propagates_default_still_swallows():
    """F1 계약 — `list_snapshots(*, target_date, strategy_id=None, raise_on_error=False)`.
    기본값은 현행(삼키고 `[]` — 라우트·일일 리포트 호출자 회귀 0), 플래그가 참이면 전파."""
    from unittest.mock import AsyncMock, patch

    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("pg down"))
        assert await strategy_funnel.list_snapshots(target_date=_TODAY) == [], "기본값은 현행 graceful []"
        with pytest.raises(RuntimeError, match="pg down"):
            await strategy_funnel.list_snapshots(target_date=_TODAY, raise_on_error=True)
        with pytest.raises(RuntimeError, match="pg down"):
            await strategy_funnel.list_snapshots(
                target_date=_TODAY, strategy_id="kojiro", raise_on_error=True,
            )
    p = inspect.signature(strategy_funnel.list_snapshots).parameters.get("raise_on_error")
    assert p is not None and p.kind is p.KEYWORD_ONLY and p.default is False, (
        "list_snapshots(*, target_date, strategy_id=None, raise_on_error=False) (F1)"
    )


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 3 — F2 힌트 쿼리 실패는 WARNING 1행(`hint_error=<축>`)
# ══════════════════════════════════════════════════════════════════════
_AXIS_BY_TABLE = {
    "strategy_config": "params_changed",
    "stock_master_daily": "bars_changed_after",
    "stock_master": "sm_refreshed_after",
}
_HINT_MARK = "[funnel_boot_vs_evening] phase=boot hint_error="


class _PgFailing(_PgSpy):
    """`FROM <table> ` 로 축을 가려 지정한 테이블 쿼리만 터뜨린다."""

    def __init__(self, fail_tables=()):
        super().__init__()
        self.fail_tables = set(fail_tables)

    def _maybe_fail(self, sql):
        low = " ".join(str(sql).lower().split()) + " "
        for t in self.fail_tables:
            if f"from {t} " in low:
                raise RuntimeError(f"{t} 쿼리 실패")

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        self._maybe_fail(sql)
        return 0

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        self._maybe_fail(sql)
        return _AnyRow()

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        self._maybe_fail(sql)
        return []


def _install_pg(monkeypatch, spy):
    for name in ("fetchval", "fetchrow", "fetch"):
        monkeypatch.setattr(f"src.db.pg.{name}", getattr(spy, name))


def _hint_warnings(caplog):
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(_HINT_MARK)
    ]


@pytest.mark.parametrize("table", ["strategy_config", "stock_master_daily", "stock_master"])
async def test_boot4_19_when_one_hint_query_fails_then_one_warning_naming_axis(monkeypatch, caplog, table):
    """F2 — 맨 `pass` 로 삼키면 그 축이 None 이 되어 「설명 안 되는 차이」 WARNING(= S2 판단
    근거)이 **영구히** 꺼지는데, 아무 흔적도 남지 않는다(round 2 검토: 힌트 SQL 은 실 PG 에서
    한 번도 돈 적이 없다)."""
    fc = _leaf()
    _install_pg(monkeypatch, _PgFailing({table}))
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00"):
        out = await fc._boot_vs_evening_hints(_EVE_AT, _BOOT_START)  # raise 금지
    axis = _AXIS_BY_TABLE[table]
    warns = _hint_warnings(caplog)
    assert len(warns) == 1, f"`{table}` 힌트 쿼리 실패 = WARNING 정확히 1행 (실측 {warns})"
    assert _fields(warns[0]).get("hint_error") == axis, f"실패 축 `{axis}` 를 적지 않았다: {warns[0]}"
    assert out.get(axis) is None, f"실패 축은 None(모름)이다 — 0 이 아니다: {out}"
    for other in set(_AXIS_BY_TABLE.values()) - {axis}:
        assert out.get(other) == 0, f"실패하지 않은 축 `{other}` 는 값이 있어야 한다: {out}"


async def test_boot4_20_when_all_hint_queries_fail_then_exactly_one_warning_first_axis(monkeypatch, caplog):
    """F2 — 「첫 실패」에 1행. 세 쿼리가 다 터져도 부팅당 WARNING 은 1행이다(축마다 3행 금지)."""
    fc = _leaf()
    _install_pg(monkeypatch, _PgFailing(set(_AXIS_BY_TABLE)))
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00"):
        out = await fc._boot_vs_evening_hints(_EVE_AT, _BOOT_START)
    warns = _hint_warnings(caplog)
    assert len(warns) == 1, f"힌트 실패 WARNING 은 호출당 정확히 1행 (실측 {warns})"
    first = (_fields(warns[0]).get("hint_error") or "").split(",")[0]
    assert first == "params_changed", f"첫 실패 축(= 첫 쿼리 strategy_config) 을 적는다: {warns[0]}"
    assert all(out.get(k) is None for k in ("params_changed", "bars_changed_after", "sm_refreshed_after", "head_now")), out


async def test_boot4_21_when_hint_queries_succeed_then_no_hint_warning(monkeypatch, caplog):
    fc = _leaf()
    _install_pg(monkeypatch, _PgFailing())
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00"):
        out = await fc._boot_vs_evening_hints(_EVE_AT, _BOOT_START)
    assert _hint_warnings(caplog) == [], "성공한 힌트는 WARNING 을 남기지 않는다"
    assert (out["params_changed"], out["bars_changed_after"], out["sm_refreshed_after"]) == (0, 0, 0), out


async def test_boot4_22_when_hint_fails_inside_emit_then_rows_emitted_and_no_error_line(monkeypatch, caplog):
    """F2 — 힌트 WARNING 은 ④ 실패(`error=`)가 아니다: 전략 행은 그대로 나가고(그 축은 None),
    오류 행은 0, 전략 행은 INFO(힌트가 0 이 아니므로 「설명 안 되는 차이」 판정 불가)."""
    fc = _leaf()
    _install_pg(monkeypatch, _PgFailing({"stock_master_daily"}))

    async def _list(*, target_date, strategy_id=None, raise_on_error=False):
        return [_row("volatility_breakout", ["990101", "990103"])]

    monkeypatch.setattr("src.db.strategy_funnel.list_snapshots", _list)
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00"):
        await fc.emit_funnel_boot_vs_evening(_sched([_S("volatility_breakout", ["990101", "990104"])]), phase="boot")
    mine = [r for r in caplog.records if r.getMessage().startswith(_MARK)]
    assert len(_hint_warnings(caplog)) == 1, [r.getMessage() for r in mine]
    errs = [r.getMessage() for r in mine if re.search(r"\berror=", r.getMessage())]
    assert errs == [], f"힌트 실패를 ④ 실패(`error=`)로 적었다: {errs}"
    lvl, f, line = _by_strategy(mine)["volatility_breakout"]
    assert f.get("bars_changed_after") == "None" and f.get("head_now") == "None", line
    assert f.get("same") == "0" and lvl == logging.INFO, line


# ══════════════════════════════════════════════════════════════════════
# 🔁 round 3 — F3 백그라운드 task 위생 (강한 참조 · 정지 · 120초 상한)
# ══════════════════════════════════════════════════════════════════════
class _Clock:
    """대기 seam 을 「freezegun 시계를 그만큼 전진시키는 가짜」로 바꾼다 — 실제 대기 0."""

    def __init__(self, frozen, orig_sleep, on_sleep=None):
        self.frozen = frozen
        self.orig_sleep = orig_sleep
        self.slept = 0.0
        self.on_sleep = on_sleep

    async def sleep(self, secs, *a, **k):
        self.slept += float(secs)
        self.frozen.tick(timedelta(seconds=float(secs)))
        if self.on_sleep is not None:
            self.on_sleep(self.slept)
        await self.orig_sleep(0)


def _ws_world(monkeypatch):
    fc = _leaf()
    list_calls: list = []
    hint_calls: list = []

    async def _list(*, target_date, strategy_id=None, raise_on_error=False):
        list_calls.append(target_date)
        return [_row("volatility_breakout", ["990101"]), _row("kojiro", ["990102"])]

    async def _hints(*a, **k):
        hint_calls.append((a, k))
        return dict(_ZERO_HINTS)

    monkeypatch.setattr("src.db.strategy_funnel.list_snapshots", _list)
    monkeypatch.setattr(fc, "list_snapshots", _list, raising=False)
    monkeypatch.setattr(fc, "_boot_vs_evening_hints", _hints)
    return fc, list_calls, hint_calls


async def test_boot4_23_spawned_task_when_created_then_held_in_bg_set_until_done(monkeypatch, caplog):
    """F3 — 버린 Task 는 약한 참조뿐이다(asyncio 문서). leaf 전역 `_BG_TASKS` 가 강한 참조를
    쥐고, 끝나면 `add_done_callback(discard)` 로 스스로 빠진다(`llm_buy_gate` 관례)."""
    import asyncio

    fc, list_calls, _ = _ws_world(monkeypatch)
    bg = getattr(fc, "_BG_TASKS", None)
    assert isinstance(bg, set), "leaf 전역 `_BG_TASKS: set` 이 없다 (F3)"
    caplog.set_level(logging.INFO)
    orig_sleep = asyncio.sleep
    with freeze_time("2026-09-23T07:46:30+09:00", real_asyncio=True):
        sched = _sched([_S("volatility_breakout", ["990101"])], _running=True,
                       _ws_task=asyncio.get_running_loop().create_future())
        task = fc.spawn_funnel_boot_vs_evening(sched, phase="boot")
        assert task in fc._BG_TASKS, "spawn 한 task 가 `_BG_TASKS` 에 없다 — 강한 참조 부재 (F3)"
        await asyncio.wait_for(task, timeout=5)
        for _ in range(3):
            await orig_sleep(0)
    assert task not in fc._BG_TASKS, "끝난 task 가 `_BG_TASKS` 에 남았다 — done 콜백 discard 부재 (F3)"
    assert list_calls, "WebSocket 단계가 이미 있으면 ④ 는 곧바로 돈다"


async def test_boot4_24_when_scheduler_stops_before_ws_then_runner_ends_without_db_or_late_emit(monkeypatch, caplog):
    """F3 — 기동 실패·부팅 중 정지(`_running=False`)면 대기 루프가 조용히 끝난다. 끝나지 않으면
    다음 기동이 `_ws_task` 를 만드는 순간 옛 runner 가 깨어나 새 runner 와 함께 ④ 를 **두 번**
    찍는다(round 2 tester 탐침 실측 2회)."""
    import asyncio

    fc, list_calls, hint_calls = _ws_world(monkeypatch)
    orig_sleep = asyncio.sleep
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00", real_asyncio=True) as fz:
        sched = _sched([_S("volatility_breakout", ["990101"])], _running=True, _ws_task=None)

        def _stop_after_1s(slept):
            if slept >= 1.0:
                sched._running = False

        clk = _Clock(fz, orig_sleep, on_sleep=_stop_after_1s)
        monkeypatch.setattr(fc, "_sleep", clk.sleep, raising=False)
        monkeypatch.setattr(asyncio, "sleep", clk.sleep)
        task = fc.spawn_funnel_boot_vs_evening(sched, phase="boot")
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
            pytest.fail(
                f"`_running=False` 뒤에도 WebSocket 대기 루프가 끝나지 않았다 (누적 {clk.slept:.1f}s, F3)"
            )
        assert clk.slept < 120.0, f"정지 뒤에도 대기가 이어졌다 (누적 {clk.slept}s)"
        # 다음 기동 — 새 `_ws_task`. 끝난 runner 가 깨어나 ④ 를 찍으면 안 된다.
        sched._running = True
        sched._ws_task = asyncio.get_running_loop().create_future()
        for _ in range(20):
            await orig_sleep(0)
    assert list_calls == [] and hint_calls == [], "정지한 기동의 runner 가 DB 를 읽었다 (F3)"
    assert not any("strategy=" in r.getMessage() for r in caplog.records if r.getMessage().startswith(_MARK)), (
        "정지한 기동의 runner 가 다음 기동에서 ④ 행을 찍었다 — 중복 `phase=boot` (F3)"
    )


async def test_boot4_25_when_ws_never_starts_then_gives_up_at_120s_with_one_warning(monkeypatch, caplog):
    """F3 — 120초 안에 `_ws_task` 가 안 생기면 WARNING 1행(`error=ws_not_started`, 못 낸 활성 전략
    전부)을 남기고 끝난다. 0.2초 폴링이 하루 종일 도는 일은 없다."""
    import asyncio

    fc, list_calls, hint_calls = _ws_world(monkeypatch)
    orig_sleep = asyncio.sleep
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00", real_asyncio=True) as fz:
        clk = _Clock(fz, orig_sleep)
        monkeypatch.setattr(fc, "_sleep", clk.sleep, raising=False)
        monkeypatch.setattr(asyncio, "sleep", clk.sleep)
        sched = _sched(
            [_S("volatility_breakout", ["990101"]), _S("kojiro", ["990102"]),
             _S("vcp_breakout", ["990103"], enabled=False)],
            _running=True, _ws_task=None,
        )
        task = fc.spawn_funnel_boot_vs_evening(sched, phase="boot")
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
            pytest.fail(f"WebSocket 대기에 상한이 없다 — 누적 {clk.slept:.1f}s 에도 끝나지 않았다 (F3)")
    assert 119.8 <= clk.slept <= 120.4, f"포기 시점은 120초 (누적 대기 {clk.slept:.1f}s)"
    assert list_calls == [] and hint_calls == [], "포기한 runner 가 DB 를 읽었다"
    warns = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(_MARK)
    ]
    assert len(warns) == 1, f"포기 = WARNING 정확히 1행 (실측 {warns})"
    assert warns[0].startswith("[funnel_boot_vs_evening] phase=boot error=ws_not_started"), warns[0]
    for sid in ("volatility_breakout", "kojiro"):
        assert sid in warns[0], f"못 낸 활성 전략 `{sid}` 가 포기 행에 없다: {warns[0]}"


async def test_boot4_26_when_ws_starts_just_before_120s_then_emits_without_give_up(monkeypatch, caplog):
    """F3 대조 — 상한 직전(119초)에 연결 단계가 시작되면 포기하지 않고 정상으로 낸다."""
    import asyncio

    fc, list_calls, _ = _ws_world(monkeypatch)
    orig_sleep = asyncio.sleep
    caplog.set_level(logging.INFO)
    with freeze_time("2026-09-23T07:46:30+09:00", real_asyncio=True) as fz:
        sched = _sched([_S("volatility_breakout", ["990101"]), _S("kojiro", ["990102"])],
                       _running=True, _ws_task=None)
        loop = asyncio.get_running_loop()

        def _ws_at_119(slept):
            if slept >= 119.0 and sched._ws_task is None:
                sched._ws_task = loop.create_future()

        clk = _Clock(fz, orig_sleep, on_sleep=_ws_at_119)
        monkeypatch.setattr(fc, "_sleep", clk.sleep, raising=False)
        monkeypatch.setattr(asyncio, "sleep", clk.sleep)
        task = fc.spawn_funnel_boot_vs_evening(sched, phase="boot")
        await asyncio.wait_for(task, timeout=5)
    mine = [r for r in caplog.records if r.getMessage().startswith(_MARK)]
    assert not any("ws_not_started" in r.getMessage() for r in mine), [r.getMessage() for r in mine]
    assert list_calls and set(_by_strategy(mine)) == {"volatility_breakout", "kojiro"}
