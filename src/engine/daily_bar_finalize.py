"""cycle386 — 부팅 prepare 직전 「잠정 봉」을 KIS 정규장 확정값으로 덮는 leaf.

## 왜

KIS 일봉(FHKST03010100 `J`)은 D일 20:00 애프터마켓이 끝난 뒤에도 그날 봉의 종가 =
19:59 애프터 마지막 체결가, 고저 = 애프터 포함 범위를 돌려준다. 정규장 값으로
바뀌는 것은 D일 23:12 뒤 ~ D+1일 05:28 전이다. 우리 20:30 저녁 적재는 그 앞이라
가짜 값을 박고, D+1 아침 모든 전략의 prepare 가 그 값을 읽는다(09-23 봉 모집단
약 60% 가 틀렸다). 20:30 적재 자체는 그대로 둔다 — 이 leaf 가 다음 거래일 아침
부팅에서 prepare 직전에 「잠정 봉」만 골라 KIS 로 다시 받아 덮는다.

명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §8.

## 계약

- 공개 API = `spawn(*, phase)` · `wait_for_boot(task, *, budget_secs)` ·
  `finalize_once(*, now_kst=None, phase)` + 상수 8개.
- 잠정 판정(§8-3)은 `stock_master_daily.list_provisional_rows` 가 SQL 에서 한다.
  이 파일은 그 결과를 받아 KIS 로 재확인·재기록만 한다.
- **never-raise** — 어떤 실패도 부팅을 막지 않는다(fail-open + 마커).
- 8영역·`scheduler`·`scanner`·`boot_manager`·strategies import 0. `src.api.*` 는
  함수 안 지연 import 만.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta

import src.db.positions as positions
import src.db.stock_master_daily as stock_master_daily
import src.db.system_config as system_config
from src.db._kst import KST, to_date

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수 (§8-4 표 — 값 근거는 설계 문서가 정본)
# ---------------------------------------------------------------------------
FINAL_BOUNDARY_TIME = time(6, 0)
WINDOW_CAL_DAYS = 21
MAX_SPAN_CAL_DAYS = 130
RANGE_PAD_CAL_DAYS = 10
BOOT_WORKERS = 3
BOOT_BUDGET_SECS = 90
BG_SLEEP_SECS = 0.05
HARD_CAP_SECS = 600

_MODE_KEY = "daily_bar_finalize_mode"
_VALID_MODES = ("enforce", "observe", "off")
_PRIORITY_INDEX_TICKERS = ("069500", "229200")
_MAX_SAMPLE = 5
_PREFIX = "[daily_bar_finalize] "

#: spawn 한 태스크의 강한 참조(`funnel_capture._BG_TASKS` 관례) — asyncio 는 버린
#: Task 를 약한 참조로만 쥔다.
_BG_TASKS: set[asyncio.Task] = set()


def _now_kst() -> datetime:
    """벽시계 seam — 테스트가 시각을 고정한다."""
    return datetime.now(KST)


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _to_int_or_none(v: object) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 모드 (system_config.daily_bar_finalize_mode)
# ---------------------------------------------------------------------------
async def _resolve_mode() -> tuple[str, str]:
    """모드 원값을 읽는다. 키 없음=enforce · 모양이 틀림=observe · 조회 실패=enforce.

    `system_config` 의 제네릭 헬퍼(`_select_value`/`_string_from_raw` — cycle369
    `status_exit_mode` 와 같은 판정)를 그대로 재사용한다. 새 system_config 함수를
    만들지 않는다(§8-5 표에 없는 변경 최소화).
    """
    try:
        raw = await system_config._select_value(_MODE_KEY)  # noqa: SLF001
    except Exception:
        return "enforce", "(db_error)"
    s = system_config._string_from_raw(raw)  # noqa: SLF001
    if s is None:
        return "enforce", ""
    if s in _VALID_MODES:
        return s, ""
    return "observe", ""


# ---------------------------------------------------------------------------
# 대상 조회 후 그룹핑 · 우선순위
# ---------------------------------------------------------------------------
def _group_targets(rows: list[dict], head: date) -> dict[str, dict]:
    """잠정 행을 종목별로 묶는다. `bas_dd > head` 인 행은 방어적으로 버린다.

    (G5(d) 런타임 증명 — 대상 조회가 잘못 오늘 행을 돌려줘도 받는 구간의 끝이
    오늘에 닿지 않는다.)
    """
    grouped: dict[str, dict] = {}
    for r in rows:
        ticker = r.get("ticker")
        d = to_date(r.get("bas_dd"))
        if not ticker or d is None or d > head:
            continue
        g = grouped.get(ticker)
        if g is None:
            g = {"oldest": d, "newest": d, "old_by_date": {}}
            grouped[ticker] = g
        else:
            if d < g["oldest"]:
                g["oldest"] = d
            if d > g["newest"]:
                g["newest"] = d
        g["old_by_date"][d] = {
            "close_price": _to_int_or_none(r.get("close_price")),
            "high_price": _to_int_or_none(r.get("high_price")),
            "low_price": _to_int_or_none(r.get("low_price")),
        }
    return grouped


def _order_targets(grouped: dict[str, dict], position_tickers: set[str]) -> list[str]:
    """① 069500·229200 ② DB 보유 ③ newest 내림차순 → 티커 오름차순."""
    remaining = set(grouped.keys())
    ordered: list[str] = []
    for t in _PRIORITY_INDEX_TICKERS:
        if t in remaining:
            ordered.append(t)
            remaining.discard(t)
    for t in sorted(position_tickers & remaining):
        ordered.append(t)
        remaining.discard(t)
    rest = sorted(remaining, key=lambda t: (-grouped[t]["newest"].toordinal(), t))
    ordered.extend(rest)
    return ordered


async def _collect_position_tickers() -> set[str]:
    rows = await positions.load_all()
    out: set[str] = set()
    for r in rows:
        t = r.get("ticker") if isinstance(r, dict) else None
        if t:
            out.add(t)
    return out


# ---------------------------------------------------------------------------
# 요약 마커
# ---------------------------------------------------------------------------
def _emit(
    *, phase: str, mode: str, result: str, head: date | None, since: date | None,
    targets: int = 0, fetched: int = 0, upserted_rows: int = 0, close_changed: int = 0,
    hl_changed: int = 0, verified: int = 0, unrolled: int = 0, mismatch: int = 0,
    missing: int = 0, failed: int = 0, db_write_failures: int = 0, span_clipped: int = 0,
    pending: int = 0, elapsed_ms: int = 0, sample_failed: list[str] | None = None,
    sample_mismatch: list[str] | None = None, stage: str | None = None,
    exc_info: bool = False,
) -> None:
    clean = (
        result in ("ok", "noop")
        and failed == 0 and missing == 0 and mismatch == 0 and db_write_failures == 0
    )
    level = logging.INFO if clean else logging.WARNING
    parts = [f"phase={phase}", f"mode={mode}", f"result={result}"]
    if stage:
        parts.append(f"stage={stage}")
    parts.append(f"head={head.isoformat() if head is not None else ''}")
    parts.append(f"since={since.isoformat() if since is not None else ''}")
    parts.append(f"targets={targets}")
    parts.append(f"fetched={fetched}")
    parts.append(f"upserted_rows={upserted_rows}")
    parts.append(f"close_changed={close_changed}")
    parts.append(f"hl_changed={hl_changed}")
    parts.append(f"verified={verified}")
    parts.append(f"unrolled={unrolled}")
    parts.append(f"mismatch={mismatch}")
    parts.append(f"missing={missing}")
    parts.append(f"failed={failed}")
    parts.append(f"db_write_failures={db_write_failures}")
    parts.append(f"span_clipped={span_clipped}")
    parts.append(f"pending={pending}")
    parts.append(f"elapsed_ms={elapsed_ms}")
    if sample_failed:
        parts.append(f"sample_failed={','.join(sample_failed[:_MAX_SAMPLE])}")
    if sample_mismatch:
        parts.append(f"sample_mismatch={','.join(sample_mismatch[:_MAX_SAMPLE])}")
    try:
        logger.log(level, _PREFIX + " ".join(parts), exc_info=exc_info)
    except Exception:
        logger.debug("[daily_bar_finalize_emit_failed]", exc_info=True)


class _RunControl:
    """`spawn`↔`wait_for_boot` 공유 상태 — 예산 초과를 배경 페이싱으로 전환한다."""

    __slots__ = ("event",)

    def __init__(self) -> None:
        self.event = asyncio.Event()


class _RunCtx:
    """실행 1회의 누적 카운터 + 배경 전환 상태."""

    def __init__(
        self, *, phase: str, mode: str, mode_label: str, head: date, since: date,
        targets: int, t0: float, control: "_RunControl | None",
    ) -> None:
        self.phase = phase
        self.mode = mode
        self.mode_label = mode_label
        self.head = head
        self.since = since
        self.targets = targets
        self.t0 = t0
        self.control = control
        self.completed = 0
        self.fetched = 0
        self.downshifted = False
        self.hard_cap_hit = False
        self.downshift_emitted = False
        self.verified = 0
        self.unrolled = 0
        self.mismatch = 0
        self.missing = 0
        self.failed = 0
        self.db_write_failures = 0
        self.span_clipped = 0
        self.close_changed = 0
        self.hl_changed = 0
        self.upserted_rows = 0
        self.sample_failed: list[str] = []
        self.sample_mismatch: list[str] = []

    def _elapsed_ms(self) -> int:
        try:
            return int((asyncio.get_running_loop().time() - self.t0) * 1000)
        except Exception:
            return 0

    def hard_cap_exceeded(self) -> bool:
        try:
            if asyncio.get_running_loop().time() - self.t0 >= HARD_CAP_SECS:
                self.hard_cap_hit = True
                return True
        except Exception:
            return False
        return False

    def _pending(self) -> int:
        return max(0, self.targets - self.completed)

    def emit_downshift(self) -> None:
        _emit(
            phase=self.phase, mode=self.mode_label, result="budget_exceeded",
            head=self.head, since=self.since, targets=self.targets, fetched=self.fetched,
            upserted_rows=self.upserted_rows, close_changed=self.close_changed,
            hl_changed=self.hl_changed, verified=self.verified, unrolled=self.unrolled,
            mismatch=self.mismatch, missing=self.missing, failed=self.failed,
            db_write_failures=self.db_write_failures, span_clipped=self.span_clipped,
            pending=self._pending(), elapsed_ms=self._elapsed_ms(),
            sample_failed=self.sample_failed, sample_mismatch=self.sample_mismatch,
        )

    def emit_final(self, *, result: str, stage: str | None = None, exc_info: bool = False) -> None:
        phase = "background" if self.downshifted else self.phase
        _emit(
            phase=phase, mode=self.mode_label, result=result, stage=stage, exc_info=exc_info,
            head=self.head, since=self.since, targets=self.targets, fetched=self.fetched,
            upserted_rows=self.upserted_rows, close_changed=self.close_changed,
            hl_changed=self.hl_changed, verified=self.verified, unrolled=self.unrolled,
            mismatch=self.mismatch, missing=self.missing, failed=self.failed,
            db_write_failures=self.db_write_failures, span_clipped=self.span_clipped,
            pending=self._pending(), elapsed_ms=self._elapsed_ms(),
            sample_failed=self.sample_failed, sample_mismatch=self.sample_mismatch,
        )

    async def process_ticker(self, ticker: str, info: dict) -> None:
        """받기 → 거르기 → 교차검증 → 쓰기(§8-4 ④~⑦). 실패는 카운터만 남긴다."""
        from src.api import condition  # 지연 import — G5(b2)

        oldest: date = info["oldest"]
        newest: date = info["newest"]
        old_by_date: dict[date, dict] = info["old_by_date"]

        start = oldest - timedelta(days=RANGE_PAD_CAL_DAYS)
        if (newest - start).days > MAX_SPAN_CAL_DAYS:
            start = newest - timedelta(days=MAX_SPAN_CAL_DAYS)
            self.span_clipped += 1

        try:
            output1, output2 = await condition.fetch_daily_chart_ranged_with_summary(
                ticker, _ymd(start), _ymd(newest),
            )
        except Exception:
            self.failed += 1
            if len(self.sample_failed) < _MAX_SAMPLE:
                self.sample_failed.append(ticker)
            return

        self.fetched += 1

        bars_by_date: dict[date, dict] = {}
        for bar in output2 or []:
            if not isinstance(bar, dict):
                continue
            d = to_date(bar.get("stck_bsop_date"))
            if d is None or not (start <= d <= newest):
                continue
            bars_by_date[d] = bar

        if not bars_by_date:
            self.failed += 1
            if len(self.sample_failed) < _MAX_SAMPLE:
                self.sample_failed.append(ticker)
            return

        if newest == self.head:
            p_bar = bars_by_date.get(newest)
            if p_bar is None:
                self.missing += 1
                return
            prdy = _to_int_or_none((output1 or {}).get("stck_prdy_clpr")) if isinstance(output1, dict) else None
            p_close = _to_int_or_none(p_bar.get("stck_clpr"))
            if prdy is not None and p_close is not None and prdy == p_close:
                self.verified += 1
            else:
                prev_dates = [d for d in bars_by_date if d < newest]
                prev_close = (
                    _to_int_or_none(bars_by_date[max(prev_dates)].get("stck_clpr"))
                    if prev_dates else None
                )
                if prdy is not None and prev_close is not None and prdy == prev_close:
                    self.unrolled += 1
                else:
                    self.mismatch += 1
                    if len(self.sample_mismatch) < _MAX_SAMPLE:
                        self.sample_mismatch.append(ticker)
                    return

        close_changed = 0
        hl_changed = 0
        for d, bar in bars_by_date.items():
            old = old_by_date.get(d)
            if old is None:
                continue
            new_close = _to_int_or_none(bar.get("stck_clpr"))
            if new_close is not None and old.get("close_price") != new_close:
                close_changed += 1
            new_high = _to_int_or_none(bar.get("stck_hgpr"))
            new_low = _to_int_or_none(bar.get("stck_lwpr"))
            if (new_high is not None and old.get("high_price") != new_high) or (
                new_low is not None and old.get("low_price") != new_low
            ):
                hl_changed += 1

        if self.mode == "observe":
            self.close_changed += close_changed
            self.hl_changed += hl_changed
            return

        candles = [bar for _, bar in sorted(bars_by_date.items())]
        try:
            n = await stock_master_daily.upsert_batch(ticker, candles)
        except Exception:
            self.db_write_failures += 1
            return

        if n < len(candles):
            self.db_write_failures += 1

        self.close_changed += close_changed
        self.hl_changed += hl_changed
        self.upserted_rows += n


async def _run_workers(ordered: list[str], grouped: dict[str, dict], ctx: _RunCtx) -> None:
    """일꾼 풀을 돌린다. 한 일꾼이 못 잡는 예외로 죽으면 나머지도 취소하고 **기다린 뒤**
    전파한다(R3) — `asyncio.gather` 기본값은 한 태스크가 실패해도 형제를 취소하지 않아,
    호출자(`finalize_once`)가 `stage=processing` 요약을 낸 **뒤에도** 형제가 계속 써서
    "쓰기는 요약 이전에 멈춘다" 는 계약을 깬다. 취소 뒤 완료까지 기다려야 그 계약이 선다.
    """
    queue: asyncio.Queue[str] = asyncio.Queue()
    for t in ordered:
        queue.put_nowait(t)
    n_workers = max(1, int(BOOT_WORKERS))

    async def _worker(worker_id: int) -> None:
        while True:
            if ctx.control is not None and ctx.control.event.is_set() and not ctx.downshifted:
                ctx.downshifted = True
                ctx.emit_downshift()
            if ctx.downshifted and worker_id != 0:
                return
            if ctx.hard_cap_exceeded():
                return
            try:
                ticker = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if ctx.downshifted:
                await asyncio.sleep(BG_SLEEP_SECS)
                if ctx.hard_cap_exceeded():
                    return
            await ctx.process_ticker(ticker, grouped[ticker])
            ctx.completed += 1

    tasks = [asyncio.create_task(_worker(i)) for i in range(n_workers)]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for t in tasks:
            if not t.done():
                t.cancel()
        # 취소가 실제로 끝날 때까지 기다린다 — 여기서 돌아와야 호출자가 요약을 낸 시점에
        # 어떤 일꾼도 더 이상 쓰지 않는다는 것이 보장된다.
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
async def finalize_once(
    *, now_kst: datetime | None = None, phase: str, _control: "_RunControl | None" = None,
) -> None:
    """1회 실행 — 대상을 골라 KIS 확정값으로 덮는다. never-raise(`CancelledError` 는 예외).

    `_control` 은 `spawn`/`wait_for_boot` 전용 내부 seam 이다(직접 호출하는
    테스트·호출자는 넘기지 않는다 — 기본값 `None` 이면 예산 다운시프트가 없다).

    🔴 R1 — 단계별 `try` **사이**(정렬·그룹핑 등)의 예외는 그 어느 단계별 `except` 에도
    안 걸린다. 바깥 `try` 가 그것까지 받아 `result=error stage=unexpected` 로 요약한다.
    바깥 `try` 없이는 그 예외가 이 태스크를 조용히 끝내고(`spawn` 은 await 없이 띄우므로
    아무도 안 본다), `wait_for_boot` 가 부팅 쪽에서 그 실패를 받더라도 leaf 자신의
    `[daily_bar_finalize]` 요약 마커는 한 줄도 안 남는다.
    """
    try:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
    except Exception:
        t0 = 0.0
    now = now_kst if now_kst is not None else _now_kst()
    today = now.date()
    mode_label = "enforce"

    def _ms() -> int:
        try:
            return int((asyncio.get_running_loop().time() - t0) * 1000)
        except Exception:
            return 0

    try:
        mode, mode_note = await _resolve_mode()
        mode_label = f"{mode}{mode_note}"

        if mode == "off":
            _emit(phase=phase, mode=mode_label, result="noop", head=None, since=None,
                  targets=0, elapsed_ms=_ms())
            return

        # F1+F2 — §8-3 그대로: `P = max(bas_dd) WHERE bas_dd < 오늘`. 이 함수는 예외를
        # 삼키지 않는다(옛 `max_bas_dd(None)` 은 삼켜 `result=noop`(INFO) 으로 둔갑시켰다).
        try:
            head = await stock_master_daily.max_bas_dd_before(today)
        except Exception:
            _emit(phase=phase, mode=mode_label, result="error", stage="head",
                  head=None, since=None, targets=0, elapsed_ms=_ms())
            return

        if head is None:
            _emit(phase=phase, mode=mode_label, result="noop", head=None, since=None,
                  targets=0, elapsed_ms=_ms())
            return

        since = today - timedelta(days=WINDOW_CAL_DAYS)
        today_boundary = datetime.combine(today, FINAL_BOUNDARY_TIME, tzinfo=KST)

        try:
            rows = await stock_master_daily.list_provisional_rows(
                since=since, head=head, today_boundary=today_boundary,
            )
        except Exception:
            _emit(phase=phase, mode=mode_label, result="error", stage="select",
                  head=head, since=since, targets=0, elapsed_ms=_ms())
            return

        grouped = _group_targets(rows, head)
        if not grouped:
            _emit(phase=phase, mode=mode_label, result="noop", head=head, since=since,
                  targets=0, elapsed_ms=_ms())
            return

        try:
            position_tickers = await _collect_position_tickers()
        except Exception:
            position_tickers = set()

        ordered = _order_targets(grouped, position_tickers)
        ctx = _RunCtx(
            phase=phase, mode=mode, mode_label=mode_label, head=head, since=since,
            targets=len(ordered), t0=t0, control=_control,
        )

        try:
            await _run_workers(ordered, grouped, ctx)
        except Exception:
            ctx.emit_final(result="error", stage="processing", exc_info=True)
            return

        ctx.emit_final(result="hard_cap" if ctx.hard_cap_hit else "ok")
    except asyncio.CancelledError:
        raise
    except Exception:
        _emit(phase=phase, mode=mode_label, result="error", stage="unexpected",
              head=None, since=None, targets=0, elapsed_ms=_ms(), exc_info=True)


def spawn(*, phase: str) -> asyncio.Task:
    """태스크를 띄우기만 한다(await 없음 — 설정·잔고·레짐과 겹쳐 돈다).

    `finalize_once` 는 반드시 모듈 전역 이름으로 부른다 — `tests/conftest.py`
    의 autouse 중립화가 이 이름을 patch 한다.
    """
    control = _RunControl()

    async def _run_with_control() -> None:
        # `finalize_once` 를 모듈 전역 이름으로 부른다 — 바인딩이 아니라 매 호출
        # 조회라 `tests/conftest.py` 의 autouse 중립화 patch 가 그대로 걸린다.
        await finalize_once(now_kst=None, phase=phase, _control=control)

    task = asyncio.create_task(_run_with_control())
    task._dbf_control = control  # type: ignore[attr-defined]
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


async def wait_for_boot(task: "asyncio.Task | None", *, budget_secs: float) -> None:
    """예산 안에서 `task` 를 기다린다. never-raise — 태스크 부재·예외·타임아웃 전부 흡수.

    타임아웃이면 태스크를 취소하지 않는다 — 배경(1 일꾼 + `BG_SLEEP_SECS`)에서
    계속 돈다. 이 함수가 돌아올 때 그 전환은 이미 적용돼 있다.

    R4 — `asyncio.shield(task)` 는 **부팅(현재 태스크)이 취소될 때** `task` 를 보호할
    뿐이다. `task`(확정 태스크) 자신이 **다른 경로로** 직접 취소되면 `shield` 는 그
    취소를 그대로 이 코루틴에 전파한다. 그 `CancelledError` 를 무조건 다시 던지면 —
    부팅 자신은 취소 요청을 받은 적이 없는데도 — 확정 태스크 하나가 취소됐다는 이유로
    부팅 전체가 취소된다. 그래서 `asyncio.current_task().cancelling()` 으로 **부팅
    자신에게 걸린 취소 요청이 있는지**를 확인한다 — 있으면(`> 0`) 그 취소는 부팅
    자신의 것이니 그대로 전파하고, 없으면 확정 태스크만의 취소이니 흡수하고 WARNING 을
    남긴 뒤 부팅을 계속한다.
    """
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=budget_secs)
    except asyncio.TimeoutError:
        control = getattr(task, "_dbf_control", None)
        if control is not None:
            control.event.set()
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling() > 0:
            raise
        logger.warning(
            "[daily_bar_finalize] wait_for_boot 확정 태스크가 외부에서 취소됐다 — "
            "부팅(현재 태스크)은 취소 요청이 없으므로 계속한다",
            exc_info=True,
        )
    except Exception:
        logger.warning(
            "[daily_bar_finalize] wait_for_boot 예상 밖 예외 — 부팅은 계속한다",
            exc_info=True,
        )
