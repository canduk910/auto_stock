"""cycle364 S1 — 저녁 A1 미리보기 · 라이브 prepare 단일 진실원 leaf.

역할 (설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md`):
- `prepare(as_of=)` 저녁 미리보기의 기준일 해석(`resolve_as_of`) + 라이브 prepare 잠금·meta
  기록 wrapper(`live_prepare_one`/`live_prepare_many`) + 캡처 라벨 가드(`capture_skip_reason`)
  + 저녁 21:00 A1 본체(`evening_capture_once`) + 부팅↔저녁 대조 ④(`emit_funnel_boot_vs_evening`
  / `spawn_funnel_boot_vs_evening`)를 한 곳에 모은다.
- **저녁 캡처 시각 = 21:00**(`TIME_EVENING_FUNNEL_CAPTURE`) — 20:30 일봉 적재 뒤, 20:45~20:51
  토큰 재발급 체인 뒤, 21:30 정산 전. `TIME_STOCK_MASTER_DAILY_LOAD`(20:30) 성공 마커를 30초
  간격으로 시작 마감(캡처+`EVENING_START_DEADLINE`=**21:15**)까지 기다린다 — 마커가 없으면 ①′
  KIS 폴백이 보조 풀로 수천 건 나가고 부실 목록이 남으므로 건너뛰는 편이 싸다.
- **never-raise** — 이 파일의 공개 함수는 어떤 것도 예외를 밖으로 던지지 않는다(호출자가
  스케줄러 task loop·부팅 경로라 하나가 죽으면 전체가 죽는다). `_live_prepare_meta` 는
  `{as_of, phase, started_at, finished_at, ok}` dict 로, prepare **시작 시점**에 `ok=None` 으로
  먼저 찍고 끝나면 `ok`(bool)·`finished_at` 을 채운다 — 진행 중에 캡처가 옛(끝난) meta 를 보고
  반쯤 만든 목록을 저장하지 않게 하려는 것이다.
- **잠금** — 라이브 prepare 는 한 번에 하나(`_lock()`). 부팅·07:59 재준비·5분 재준비·저녁 A1 이
  같은 전략 객체의 `_funnel_steps`/`_candidates` 를 동시에 건드리면 섞인다.
- **8영역 import 0** — `risk`·`order_engine`·`session`·`scanner`·`strategy_registry`·`api.order`·
  `realtime`·`auth` 어느 것도 이 파일에서 참조하지 않는다(AST 가드). 부팅↔저녁 대조(④)가
  보호 종목(보유·익일청산)을 모을 때도 scanner 헬퍼 대신 scheduler 가 넘겨준 상태를 쓴다.
- **PV-1(cycle364 R1) 은 4 전략 한정** — 「미리보기가 보유 종목의 청산 입력을 바꾸지 않는다」
  는 계약은 `strategy_base._preview_keep_tickers`/`_preview_skip_tickers` + **donchian·kojiro·
  bull_flag_breakout·vcp_breakout** 4전략 `prepare()` 안에 있다(round-1 이 BFB·VCP 도
  `_effective_setup` 이 live `_candidates` 를 우선한다는 사실을 발견해 2전략에서 4전략으로
  넓혔다). **VB·LTV 는 대상이 아니다** — VB `failed_breakout_exit` 는 재구성된 `_targets` 를,
  LTV 상한가 모드 전환은 `ticker_prev_close` 를 읽지만, 21:00~21:30 은 틱이 없고 21:30 정산이
  비우므로 받아들인 무해한 잔여다(설계 §1.2 VB·LTV 행 · §8). 이 leaf 를 21:00 이후로
  옮기는 것만으로는 안전하지 않다 — PV-1 이 없으면 미리보기 준비가 보유 종목(kojiro
  stage3·donchian ATR·BFB 샹들리에·VCP ema50 등)의 청산 입력을 바꿔 야간 틱 하나로 가격
  무관 청산이 발사될 수 있다.
- **호출자** — `capture_funnel_snapshots`(`scheduler.py`, 09:30 자동·수동 trigger·21:00 저녁
  A1 셋이 공유하는 캡처 헬퍼, 라벨 가드에 이 leaf 의 `capture_skip_reason` 을 쓴다) ·
  `boot_manager.boot`(부팅 prepare · ④ 스폰) · `scheduler.py`(07:59 사전 구독 재준비 2곳 ·
  `_reprepare_breakout_if_empty` · 저녁 task loop 위임).
- **S1/S2 경계** — 21:00 이전(부팅 +600초 즉시 1회)은 S1 임시 「레거시 재준비」다(`decision=
  legacy_reprepare`) — 미리보기가 아니라 오늘 라벨로 전 전략을 다시 준비한다. 오후 재기동
  (16:00~20:00)도 이 시각 창이면 이 분기를 탄다. **S2 는 이 분기를 없애고** 아침 ②③ 판정
  (입력이 실제로 바뀐 날만 재준비)으로 대체한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.db._kst import KST

logger = logging.getLogger(__name__)

_ORDER = (
    "volatility_breakout", "long_tail_volatility", "bull_flag_breakout", "vcp_breakout",
    "donchian_swing", "kojiro", "momentum",
)
EVENING_POLL_SECS = 30
EVENING_START_DEADLINE = timedelta(minutes=15)
BOOT_VS_EVENING_TIMEOUT_SECS = 10
_LOCK: dict = {}

_UNKNOWN_HINTS = {
    "params_changed": None, "bars_changed_after": None,
    "sm_refreshed_after": None, "head_now": None,
}


def _now_kst() -> datetime:
    return datetime.now(KST)


async def _sleep(secs: float) -> None:
    await asyncio.sleep(secs)


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lk = _LOCK.get(id(loop))
    if lk is None:
        lk = asyncio.Lock()
        _LOCK.clear()
        _LOCK[id(loop)] = lk
    return lk


@dataclass(frozen=True)
class AsOf:
    as_of: date
    expected_head: date
    mode: str
    preview: bool


async def resolve_as_of(now_kst: datetime, mode: str) -> AsOf | None:
    """cycle364 §2.2 — S1 은 `mode="evening"` 만 잰다. 모르면 라벨을 붙이지 않는다(None)."""
    try:
        from src.engine import trading_calendar as tc

        today = now_kst.date()
        if mode == "evening":
            if await tc.is_open_day(today) is not True:
                return None
            nxt = await tc.next_trading_day(today)
            if nxt is None:
                return None
            return AsOf(as_of=nxt, expected_head=today, mode="evening", preview=True)
        return None
    except Exception:
        return None


def _stamp_start(strategy, *, as_of, phase: str, started: datetime) -> None:
    """cycle364 R3 — prepare **시작 시점**에 `ok=None` 으로 먼저 찍는다."""
    try:
        strategy._live_prepare_meta = {
            "as_of": as_of if as_of is not None else started.date(),
            "phase": phase, "started_at": started, "finished_at": None, "ok": None,
        }
    except Exception:
        pass


def _stamp_finish(strategy, *, ok: bool, finished: datetime) -> None:
    try:
        meta = getattr(strategy, "_live_prepare_meta", None)
        if isinstance(meta, dict):
            meta["ok"] = ok
            meta["finished_at"] = finished
        else:
            strategy._live_prepare_meta = {"ok": ok, "finished_at": finished}
    except Exception:
        pass


async def _run_one(strategy, *, as_of, phase: str) -> bool:
    started = _now_kst()
    _stamp_start(strategy, as_of=as_of, phase=phase, started=started)
    ok = True
    try:
        if as_of is None:
            await strategy.prepare()
        else:
            await strategy.prepare(as_of=as_of)
    except Exception:
        ok = False
        # cycle364 R7 — grep 연속성: 옛 호출부 문구를 새 마커 안에 그대로 둔다
        # (boot_manager 「전략 prepare 실패」 / scheduler 「재 prepare 실패」).
        phrase = "전략 prepare 실패" if phase == "boot" else "재 prepare 실패"
        logger.exception(
            "[live_prepare] %s phase=%s %s", getattr(strategy, "strategy_id", "?"), phase, phrase,
        )
    _stamp_finish(strategy, ok=ok, finished=_now_kst())
    return ok


async def live_prepare_one(strategy, *, phase: str) -> bool:
    async with _lock():
        return await _run_one(strategy, as_of=None, phase=phase)


async def live_prepare_many(strategies, *, as_of, phase: str) -> dict:
    prepared, failed = 0, []
    for s in strategies:
        async with _lock():
            ok = await _run_one(s, as_of=as_of, phase=phase)
        if ok:
            prepared += 1
        else:
            failed.append(getattr(s, "strategy_id", "?"))
    return {"prepared": prepared, "failed": failed}


def capture_skip_reason(strategy, label: date, today: date, *, is_provisional: bool) -> str | None:
    """cycle364 §2.5 · R3 — 캡처가 이 전략 행을 저장해도 되는지 판정한다."""
    meta = getattr(strategy, "_live_prepare_meta", None)
    if not isinstance(meta, dict):
        return None if label == today else "no_meta"
    if meta.get("ok") is False:
        return "prepare_failed"
    if meta.get("ok") is not True:
        return "in_progress"
    if meta.get("as_of") != label:
        return "as_of_mismatch"
    if not is_provisional and meta.get("phase") == "evening":
        # R3 — 확정 캡처(09:30 자동·수동)는 저녁 미리보기(잠정 산출물)를 확정 행으로
        # 저장하지 않는다. 자정 뒤에는 저녁 meta 의 as_of 가 새 오늘과 같아져 라벨이
        # "일치"로 보이므로, phase 로 한 번 더 가른다.
        return "evening_preview_reject"
    return None


def _ordered(strategies):
    def key(s):
        sid = getattr(s, "strategy_id", "")
        enabled = bool(getattr(getattr(s, "config", None), "enabled", True))
        rank = _ORDER.index(sid) if sid in _ORDER else len(_ORDER)
        return (0 if enabled else 1, rank)

    return sorted(strategies, key=key)


def _marker_done(iso, today: date) -> bool:
    """R8 — 마커가 **오늘 20:30 이상**일 때만 완료다. 같은 날짜라도 그 이전(부팅 보충 적재가
    07:5x 에 쓴 마커)은 완료가 아니다 — 날짜만 비교하면 D-1 헤드로 미리보기가 돈다."""
    from src.engine.scheduler import TIME_STOCK_MASTER_DAILY_LOAD

    if not iso:
        return False
    try:
        dt = datetime.fromisoformat(iso)
        if dt.utcoffset() is None:
            return False
        return dt >= datetime.combine(today, TIME_STOCK_MASTER_DAILY_LOAD, tzinfo=KST)
    except Exception:
        return False


async def _daily_head_now() -> date | None:
    """R5 — 요약 행의 `daily_head=` 값. 인덱스 컬럼 `max(bas_dd)` 한 번 — `count_all()` 전 행
    스캔은 쓰지 않는다. 실패는 `None`(모름)이지 0 이 아니다."""
    try:
        from src.db.stock_master_daily import max_bas_dd

        return await max_bas_dd()
    except Exception:
        return None


async def evening_capture_once(scheduler) -> dict:
    """cycle364 §2.4/§4.6 저녁 A1 본체(task loop 의 once_callable, 21:00 이전은 S1 레거시).

    S1 = 부팅 +600초 즉시 1회(레거시, `decision=legacy_reprepare`) + 21:00 저녁 A1
    (`decision=run|skip`). **S2 에서 레거시 분기를 제거**하고 아침 ②③ 판정으로 대체한다 —
    이 분기는 오후 재기동(16:00~20:00)에서도 예전처럼 전 전략을 다시 준비하는 S1 한정
    임시 동작이다.
    """
    from src.engine.scheduler import TIME_EVENING_FUNNEL_CAPTURE, capture_funnel_snapshots

    now = _now_kst()
    registry = scheduler.registry

    if now.time() < TIME_EVENING_FUNNEL_CAPTURE:
        strategies = list(registry.all())
        res = await live_prepare_many(strategies, as_of=None, phase="reprepare_legacy")
        saved = await capture_funnel_snapshots(registry, is_provisional=True, target_date=now.date())
        head = await _daily_head_now()
        skipped = ",".join(f"{sid}:prepare_failed" for sid in res["failed"])
        logger.info(
            "[evening_funnel_capture] decision=legacy_reprepare reason=boot_immediate_run "
            "as_of=%s expected_head=None load_marker=None daily_head=%s prepared=%d saved=%d "
            "skipped=%s",
            now.date(), head, res["prepared"], saved, skipped,
        )
        return {"prepared": res["prepared"], "saved": saved}

    deadline = datetime.combine(now.date(), TIME_EVENING_FUNNEL_CAPTURE, tzinfo=KST) + EVENING_START_DEADLINE

    import src.engine.trading_calendar as tc
    from src.db import system_config as _sc

    asof: AsOf | None = None
    marker = None
    outcome: tuple[str, int] | None = None

    while True:
        now = _now_kst()
        today = now.date()
        try:
            opened = await tc.is_open_day(today)
        except Exception:
            opened = None

        if opened is False:
            outcome = ("today_closed", logging.INFO)
            break

        # R4 — 달력은 폴링 루프 안에서 시작 마감까지 다시 푼다. 오늘이 열린 날일 때만
        # `resolve_as_of` 를 부른다(닫힘·모름이면 다음 거래일을 물어봐야 소용이 없다).
        asof = await resolve_as_of(now, "evening") if opened is True else None
        if asof is not None:
            try:
                marker = await _sc.get_task_last_success("stock_master_daily_load")
            except Exception:
                marker = None
            if _marker_done(marker, today):
                outcome = None
                break

        if now >= deadline:
            outcome = ("calendar_unknown" if asof is None else "daily_load_not_done", logging.WARNING)
            break

        await _sleep(EVENING_POLL_SECS)

    # daily_head 조회는 while 밖(§g273f_4 — 대기 신호는 마커뿐, 헤드는 요약 행 전용).
    head = await _daily_head_now()

    if outcome is not None:
        reason, level = outcome
        if reason == "daily_load_not_done":
            logger.log(
                level,
                "[evening_funnel_capture] decision=skip reason=daily_load_not_done as_of=%s "
                "expected_head=%s load_marker=%s daily_head=%s prepared=0 saved=0 skipped=",
                asof.as_of, asof.expected_head, marker, head,
            )
        else:
            logger.log(
                level,
                "[evening_funnel_capture] decision=skip reason=%s as_of=None expected_head=None "
                "load_marker=None daily_head=%s prepared=0 saved=0 skipped=",
                reason, head,
            )
        return {"prepared": 0, "saved": 0}

    strategies = _ordered(registry.all())
    res = await live_prepare_many(strategies, as_of=asof.as_of, phase="evening")
    saved = await capture_funnel_snapshots(registry, is_provisional=True, target_date=asof.as_of)
    skipped = ",".join(f"{sid}:prepare_failed" for sid in res["failed"])
    logger.info(
        "[evening_funnel_capture] decision=run reason=load_marker_ok as_of=%s expected_head=%s "
        "load_marker=%s daily_head=%s prepared=%d saved=%d skipped=%s",
        asof.as_of, asof.expected_head, marker, head, res["prepared"], saved, skipped,
    )
    return {"prepared": res["prepared"], "saved": saved}


# ══════════════════════════════════════════════════════════════════════
# ④ 부팅↔저녁 대조 (§4.3, cycle364 R2)
# ══════════════════════════════════════════════════════════════════════
def _tickers(raw) -> set[str]:
    out = set()
    for x in raw or []:
        if isinstance(x, dict):
            t = x.get("ticker")
            if t:
                out.add(str(t))
        elif x:
            out.add(str(x))
    return out


def _collect_protected(scheduler) -> set[str]:
    """leaf 는 8영역(scanner 포함)을 import 하지 않는다 — scheduler 가 넘겨준 registry·
    `_pending_next_day_clear` 에서 직접 모은다."""
    held: set[str] = set()
    try:
        for s in scheduler.registry.all():
            held |= set(getattr(s.state, "positions", {}) or {})
    except Exception:
        pass
    try:
        for item in getattr(scheduler, "_pending_next_day_clear", None) or ():
            held.add(item[0] if isinstance(item, tuple) else item)
    except Exception:
        pass
    return held


async def _boot_vs_evening_hints(evening_at: datetime, until: datetime, *, phase: str = "boot") -> dict:
    """cycle364 §4.3 · R2/F2 — 저녁↔부팅 차이의 원인 힌트, **부팅당 1회**(DB 3쿼리 이내).

    창은 전부 `[evening_at, until)` 로 묶는다 — `until` = 부팅 준비 시작 시각(가장 이른
    `phase=boot` `_live_prepare_meta.started_at`). 부팅 자신의 보유 종목 eager refresh 는
    prepare **뒤**에 돌므로, 상한을 두지 않으면 그 refresh 가 `sm_refreshed_after` 로 새어
    월요일·연휴 뒤마다 "설명 안 되는 차이" WARNING 이 억제된다.

    never-raise. 값을 못 구한 축은 `None`(모름)이다. **F2** — 맨 `pass` 로 삼키지 않는다:
    이 호출 안에서 **첫 실패**가 나면 WARNING 정확히 1행 `hint_error=<축>` 을 남긴다(세 쿼리가
    다 터져도 1행 — 축마다 3행 금지). 그 WARNING 은 ④ 실패(`error=`)가 아니다.
    """
    out: dict = dict(_UNKNOWN_HINTS)
    if evening_at is None or until is None:
        return out
    try:
        from src.db import pg as _pg
    except Exception:
        return out

    failed_axis: str | None = None

    try:
        v = await _pg.fetchval(
            "SELECT count(*) FROM strategy_config WHERE updated_at > $1 AND updated_at < $2",
            evening_at, until,
        )
        out["params_changed"] = int(v or 0)
    except Exception:
        failed_axis = failed_axis or "params_changed"
    try:
        # bas_dd(인덱스 컬럼)로 범위를 묶어 `updated_at`(무인덱스) 전 행 스캔을 피한다.
        row = await _pg.fetchrow(
            "SELECT count(*) FILTER (WHERE updated_at > $1 AND updated_at < $2) "
            "AS bars_changed_after, max(bas_dd) AS head_now FROM stock_master_daily "
            "WHERE bas_dd >= $1::date - interval '2 days'",
            evening_at, until,
        )
        if row is not None:
            out["bars_changed_after"] = int(row.get("bars_changed_after") or 0)
            out["head_now"] = row.get("head_now")
    except Exception:
        failed_axis = failed_axis or "bars_changed_after"
    try:
        v = await _pg.fetchval(
            "SELECT count(*) FROM stock_master WHERE refreshed_at > $1 AND refreshed_at < $2",
            evening_at, until,
        )
        out["sm_refreshed_after"] = int(v or 0)
    except Exception:
        failed_axis = failed_axis or "sm_refreshed_after"

    if failed_axis is not None:
        logger.warning(
            "[funnel_boot_vs_evening] phase=%s hint_error=%s", phase, failed_axis,
        )
    return out


async def _emit(scheduler, phase: str, emitted: set[str]) -> None:
    from src.db import strategy_funnel as sf

    def _enabled():
        try:
            return list(scheduler.registry.enabled())
        except Exception:
            return []

    enabled = _enabled()
    today = _now_kst().date()
    try:
        # cycle364 F1 — 기본값은 예외를 삼키고 `[]`(운영 `list_snapshots`), 그러면 DB 장애가
        # 아래 `evening=absent`(정상 부재)로 오독된다. `raise_on_error=True` 로 전파시켜
        # 여기서 잡는다.
        rows = await sf.list_snapshots(target_date=today, raise_on_error=True)
    except Exception:
        ids = ",".join(getattr(s, "strategy_id", "?") for s in enabled)
        logger.warning(
            "[funnel_boot_vs_evening] phase=%s error=list_snapshots_failed strategies=%s",
            phase, ids,
        )
        return

    evening: dict = {}
    for r in rows or []:
        if r.get("step_no") == 99 and r.get("is_provisional") is True:
            evening[r["strategy_id"]] = (_tickers(r.get("survived_tickers")), r.get("snapshot_at"))
    if not evening:
        logger.info("[funnel_boot_vs_evening] phase=%s as_of=%s evening=absent", phase, today)
        return

    held = _collect_protected(scheduler)

    eats = [eat for (_e, eat) in evening.values() if eat is not None]
    evening_at = min(eats) if eats else None
    boot_starts = [
        meta["started_at"]
        for s in enabled
        if isinstance((meta := getattr(s, "_live_prepare_meta", None)), dict)
        and meta.get("phase") == "boot" and isinstance(meta.get("started_at"), datetime)
    ]
    until = min(boot_starts) if boot_starts else _now_kst()

    try:
        hints = (
            await _boot_vs_evening_hints(evening_at, until, phase=phase)
            if evening_at is not None else dict(_UNKNOWN_HINTS)
        )
    except Exception:
        hints = dict(_UNKNOWN_HINTS)

    failed: list[str] = []
    for s in enabled:
        sid = getattr(s, "strategy_id", "?")
        if sid not in evening:
            continue
        try:
            eset, eat = evening[sid]
            bset = set(s.get_scanned_tickers())
            excl = (eset | bset) & held
            e, b = eset - held, bset - held
            added, removed = sorted(b - e), sorted(e - b)
            same = int(e == b)
            level = logging.INFO
            if not same and all(
                hints.get(k) == 0 for k in ("params_changed", "bars_changed_after", "sm_refreshed_after")
            ):
                level = logging.WARNING
            logger.log(
                level,
                "[funnel_boot_vs_evening] phase=%s strategy=%s as_of=%s evening_at=%s evening_n=%d "
                "boot_n=%d same=%d added=%d removed=%d sample_added=%s sample_removed=%s "
                "held_excluded=%d params_changed=%s bars_changed_after=%s sm_refreshed_after=%s "
                "head_now=%s",
                phase, sid, today, eat.isoformat() if eat else None, len(e), len(b), same,
                len(added), len(removed), ",".join(added[:5]), ",".join(removed[:5]), len(excl),
                hints.get("params_changed"), hints.get("bars_changed_after"),
                hints.get("sm_refreshed_after"), hints.get("head_now"),
            )
            emitted.add(sid)
        except Exception:
            failed.append(sid)

    if failed:
        logger.warning(
            "[funnel_boot_vs_evening] phase=%s error=strategy_failed strategies=%s",
            phase, ",".join(failed),
        )


async def emit_funnel_boot_vs_evening(scheduler, *, phase: str = "boot") -> None:
    """cycle364 §4.3 · R2 — never-raise + 「조용한 부재」 금지.

    실패·타임아웃은 WARNING **정확히 1행**에 못 낸 전략 전부를 적는다(DEBUG 로 삼키지 않는다
    — 이 대조가 S2 착수 여부의 판단 근거라 조용히 사라지면 안 된다).
    """
    emitted: set[str] = set()
    try:
        await asyncio.wait_for(_emit(scheduler, phase, emitted), timeout=BOOT_VS_EVENING_TIMEOUT_SECS)
    except Exception:
        try:
            all_ids = [getattr(s, "strategy_id", "?") for s in scheduler.registry.enabled()]
        except Exception:
            all_ids = []
        missing = [sid for sid in all_ids if sid not in emitted] or all_ids
        logger.warning(
            "[funnel_boot_vs_evening] phase=%s error=timeout_or_exception strategies=%s",
            phase, ",".join(missing),
        )


#: cycle364 F3 — spawn 한 백그라운드 task 의 강한 참조(`llm_buy_gate` 관례). asyncio 는 버린
#: Task 를 약한 참조만 쥐므로, 이 집합이 없으면 GC 가 대기 중인 task 를 회수할 수 있다.
_BG_TASKS: set = set()

_WS_WAIT_POLL_SECS = 0.2
_WS_WAIT_TIMEOUT_SECS = 120.0


async def _wait_for_ws_then_emit(scheduler, phase: str) -> None:
    """cycle364 F3 — WebSocket 연결 단계 대기 루프 본체.

    (a) `getattr(scheduler, "_running", True)` 가 거짓이면 DB 를 건드리지 않고 조용히
    끝난다(정지·기동 실패 뒤 다음 기동에서 ④ 가 두 번 찍히지 않게). 기본값은 **True** 다
    (`_running` 속성이 없는 테스트 더블·구 호출부가 계속 돌게 하려는 것).
    (b) 대기 seam `_sleep` 으로 잰 누적 대기가 **120초**(`_WS_WAIT_TIMEOUT_SECS`)를 넘으면
    WARNING 1행 `error=ws_not_started` 을 남기고 끝난다(못 낸 활성 전략 전부를 적는다).
    """
    elapsed = 0.0
    while getattr(scheduler, "_ws_task", None) is None:
        if not getattr(scheduler, "_running", True):
            return
        if elapsed >= _WS_WAIT_TIMEOUT_SECS:
            try:
                all_ids = [getattr(s, "strategy_id", "?") for s in scheduler.registry.enabled()]
            except Exception:
                all_ids = []
            logger.warning(
                "[funnel_boot_vs_evening] phase=%s error=ws_not_started strategies=%s",
                phase, ",".join(all_ids),
            )
            return
        await _sleep(_WS_WAIT_POLL_SECS)
        elapsed += _WS_WAIT_POLL_SECS
    await emit_funnel_boot_vs_evening(scheduler, phase=phase)


def spawn_funnel_boot_vs_evening(scheduler, *, phase: str = "boot") -> "asyncio.Task":
    """cycle364 R2/F3 — 부팅은 이 함수를 **await 없이** 1회 부른다.

    `_boot()` 은 WebSocket 연결 *전*에 await 되므로, ④ 를 여기서 기다리면 보유 중 재기동의
    틱 공백이 그만큼 늘어난다. 반환된 task 는 WebSocket 연결 단계(`scheduler._ws_task`)가
    생길 때까지 DB 를 건드리지 않고 기다린다(대기 상한 = `_WS_WAIT_TIMEOUT_SECS`, 정지 시
    조기 종료). task 는 모듈 전역 `_BG_TASKS` 가 강한 참조로 붙들고, 끝나면 스스로 빠진다.
    """
    task = asyncio.create_task(_wait_for_ws_then_emit(scheduler, phase))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task
