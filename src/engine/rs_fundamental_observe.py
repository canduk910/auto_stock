"""RS·재무·목표가 리비전 2단계 — 부팅 때 4전략 후보·보유 종목의 점수를 기록한다 (관찰 전용, 매매 행위 0).

명세 `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §B. 주문·수량·신호·후보 목록·전략 상태를 읽기만 하고
바꾸지 않는다(전략 객체에 대입 0). KIS 호출 0 — DB 만. never-raise.
킬스위치 `system_config.rs_fundamental_observe_mode` — 키 없음 = record · `off` = 안 돈다 · 그 밖 = record + WARNING.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import date, datetime, timedelta
from typing import Any

import src.db.candidate_scores as cs_db
import src.db.invest_opinion as io_db
import src.db.score_inputs as si_db
import src.db.system_config as sc_db
from src.db._kst import now_kst_iso, today_kst
from src.engine import fundamental_score as fs
from src.engine import rs_score

logger = logging.getLogger(__name__)

WAIT_PREPARE_SECS = 600
PREPARE_POLL_SECS = 10
RUN_TIMEOUT_SECS = 300
TARGET_STRATEGIES = ("donchian_swing", "vcp_breakout", "kojiro", "etf_trend")
_NO_FUNDAMENTAL = frozenset({"etf_trend"})
_MODE_KEY = "rs_fundamental_observe_mode"
_CLOSES_N = 200
_OPINION_LOOKBACK_DAYS = 400
_OPINION_CONCURRENCY = 8

_RS_COLS = ("rs_raw", "rs_pct", "sector_key", "vs_sector", "sector_pct", "in_sector_pct")
_TARGET_COLS = ("revision_breadth", "target_median_change", "opinion_brokers")
_FIN_COLS = (
    "fin_quarter", "op_income_q", "op_income_q_yoy", "op_turnaround", "op_yoy_growth",
    "revenue_yoy_growth", "net_turnaround", "roe", "debt_ratio_latest", "debt_ratio_down_years",
    "ttm_op_to_max_ratio",
)


# ---------------------------------------------------------------------------
# 순수 계산
# ---------------------------------------------------------------------------
def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _prev_year(stac_yymm: str) -> str:
    return f"{int(stac_yymm[:4]) - 1:04d}{stac_yymm[4:6]}"


def _fin_columns(rows: list[dict], master_raw: dict | None, as_of: date) -> dict[str, Any]:
    """분기·연간 재무 행(그때 알 수 있던 것만) → 재무 칸. 모름 = None."""
    out: dict[str, Any] = {c: None for c in _FIN_COLS}
    out["roe"] = _num((master_raw or {}).get("roe"))
    quarterly = fs.known_as_of([r for r in rows if r.get("div_cls") == "1"], as_of)
    annual = fs.known_as_of([r for r in rows if r.get("div_cls") == "0"], as_of)

    debt = [(r["stac_yymm"], _num(r.get("lblt_rate"))) for r in annual]
    debt_vals = [v for _ym, v in sorted(debt) if v is not None]
    if debt_vals:
        out["debt_ratio_latest"] = debt_vals[-1]
        last3 = debt_vals[-3:]
        if len(last3) >= 2:
            out["debt_ratio_down_years"] = sum(1 for a, b in zip(last3, last3[1:]) if b < a)

    if not quarterly:
        return out
    latest = max(r["stac_yymm"] for r in quarterly)
    out["fin_quarter"] = latest

    def series(col: str) -> dict[str, float | None]:
        return fs.quarterly_from_cumulative(
            [{"stac_yymm": r["stac_yymm"], "value": _num(r.get(col))} for r in quarterly]
        )

    op, sale, net = series("bsop_prti"), series("sale_account"), series("thtr_ntin")
    op_now, op_yoy = op.get(latest), op.get(_prev_year(latest))
    out["op_income_q"] = op_now
    out["op_income_q_yoy"] = op_yoy
    flags = fs.turnaround_flags(op_now, op_yoy)
    out["op_turnaround"] = flags["turnaround"]
    out["op_yoy_growth"] = flags["yoy_growth"]
    out["revenue_yoy_growth"] = fs.turnaround_flags(sale.get(latest), sale.get(_prev_year(latest)))["yoy_growth"]
    out["net_turnaround"] = fs.turnaround_flags(net.get(latest), net.get(_prev_year(latest)))["turnaround"]

    ttm: dict[str, float] = {}
    for ym in op:
        parts = [op.get(fs._shift_months(ym, -3 * k)) for k in range(4)]
        if all(p is not None for p in parts):
            ttm[ym] = float(sum(parts))  # type: ignore[arg-type]
    if latest in ttm:
        peak = max(ttm.values())
        if peak > 0:
            out["ttm_op_to_max_ratio"] = ttm[latest] / peak
    return out


def _target_columns(opinions: list[dict], as_of: date) -> dict[str, Any]:
    out: dict[str, Any] = {c: None for c in _TARGET_COLS}
    if not opinions:
        return out
    pairs = fs._latest_prev_by_broker(opinions, as_of, 60, 250)
    if not pairs:
        return out
    out["revision_breadth"] = fs.target_revision_breadth(opinions, as_of)
    out["target_median_change"] = fs.target_median_change(opinions, as_of)
    out["opinion_brokers"] = len(pairs)
    return out


# ---------------------------------------------------------------------------
# 입력 적재
# ---------------------------------------------------------------------------
def _failed(stage: str, exc: BaseException | None = None) -> None:
    logger.warning("[rs_observe_failed] stage=%s err=%r", stage, exc, exc_info=exc is not None)


async def _read_mode() -> str:
    try:
        raw = await sc_db._select_value(_MODE_KEY)
    except Exception as e:
        _failed("mode", e)
        return "record"
    if raw is sc_db._MISSING:
        return "record"
    val = str(raw.get("value") if isinstance(raw, dict) else raw).strip().lower()
    if val == "off":
        return "off"
    if val != "record":
        logger.warning("[rs_observe] %s=%r 인식 불가 — record 로 진행", _MODE_KEY, raw)
    return "record"


def _prepare_state(strategy: Any) -> str:
    """`done` | `pending`(진행 중·아직 없음) | `failed`."""
    meta = getattr(strategy, "_live_prepare_meta", None)
    if not isinstance(meta, dict):
        return "pending"
    if meta.get("ok") is True and meta.get("phase") == "boot":
        return "done"
    if meta.get("ok") is False:
        return "failed"
    return "pending"


async def _wait_prepared(registry: Any) -> list[Any]:
    """대상 전략(레지스트리에 있고 켜진 것)이 부팅 prepare 를 끝낼 때까지 기다린다. 못 기다린 전략은 skip 로그."""
    pending: dict[str, Any] = {}
    for sid in TARGET_STRATEGIES:
        s = registry.get(sid)
        if s is not None and bool(getattr(getattr(s, "config", None), "enabled", False)):
            pending[sid] = s
    ready: list[Any] = []
    deadline = time.monotonic() + WAIT_PREPARE_SECS
    while pending:
        for sid, s in list(pending.items()):
            state = _prepare_state(s)
            if state == "done":
                ready.append(s)
                del pending[sid]
            elif state == "failed":
                del pending[sid]
                logger.info("[rs_observe] strategy=%s skipped=prepare_not_done", sid)
        if not pending or time.monotonic() >= deadline:
            break
        await asyncio.sleep(PREPARE_POLL_SECS)
    for sid in pending:
        logger.info("[rs_observe] strategy=%s skipped=prepare_not_done", sid)
    order = {sid: i for i, sid in enumerate(TARGET_STRATEGIES)}
    return sorted(ready, key=lambda s: order[s.strategy_id])


def _targets(strategy: Any) -> tuple[list[str], set[str], list[str]]:
    """(후보 목록, 보유 집합, 행 대상 종목 — 후보 먼저, 보유만인 종목 뒤)."""
    scanned = [t for t in (strategy.get_scanned_tickers() or []) if isinstance(t, str)]
    held = {t for t in dict(getattr(strategy.state, "positions", {}) or {}) if isinstance(t, str)}
    ordered = list(dict.fromkeys(scanned)) + sorted(held - set(scanned))
    return scanned, held, ordered


async def _opinions_for(tickers: list[str], today: date) -> dict[str, list[dict]]:
    sem = asyncio.Semaphore(_OPINION_CONCURRENCY)
    frm, to = today - timedelta(days=_OPINION_LOOKBACK_DAYS), today - timedelta(days=1)

    async def one(t: str) -> tuple[str, list[dict]]:
        async with sem:
            return t, list(await io_db.get_opinions(t, frm, to) or [])

    return dict(await asyncio.gather(*(one(t) for t in tickers)))


async def _compute_and_write(ready: list[Any], today: date) -> None:
    from src.engine.strategies.kojiro import _kojiro_sector_key  # 읽기 전용 — 섹터 키 규약 공유

    started = time.monotonic()
    plan = [(s, *_targets(s)) for s in ready]
    row_tickers = list(dict.fromkeys(t for _s, _sc, _h, ordered in plan for t in ordered))
    fin_tickers = [t for t in row_tickers if any(t in o and s.strategy_id not in _NO_FUNDAMENTAL
                                                 for s, _sc, _h, o in plan)]
    if not row_tickers:
        return

    try:
        closes = await si_db.recent_closes_bulk(before=today, n=_CLOSES_N)
    except Exception as e:
        _failed("closes", e)
        return
    try:
        master = await si_db.master_raw_map(list({*closes, *row_tickers}))
    except Exception as e:
        _failed("master", e)
        master = {}
    try:
        fin_rows = await si_db.financial_rows_bulk(fin_tickers)
    except Exception as e:
        _failed("fin", e)
        fin_rows = {}
    try:
        opinions = await _opinions_for(fin_tickers, today)
    except Exception as e:
        _failed("opinions", e)
        opinions = {}

    scores = {t: rs_score.ibd_lite_return(c) for t, c in closes.items()}
    pct = rs_score.percentile_ranks(scores)
    sector_of = {t: _kojiro_sector_key(master.get(t), t) for t in closes}
    rel = rs_score.sector_relative(scores, sector_of)
    population = sum(v is not None for v in scores.values())
    computed_at = datetime.fromisoformat(now_kst_iso())
    yesterday = today - timedelta(days=1)

    rows: list[dict] = []
    markers: list[str] = []
    for strategy, scanned, held, ordered in plan:
        sid = strategy.strategy_id
        fundamental = sid not in _NO_FUNDAMENTAL
        counts = {"rs": 0, "fin": 0, "op": 0}
        for t in ordered:
            row: dict[str, Any] = {
                "target_date": today, "strategy_id": sid, "ticker": t,
                "role": "held" if t in held else "candidate",
                **{c: None for c in (*_RS_COLS, *_TARGET_COLS, *_FIN_COLS)},
                "rs_population": population, "computed_at": computed_at,
            }
            if t in closes:
                row.update(rs_raw=scores[t], rs_pct=pct[t], sector_key=sector_of[t], **rel[t])
            if fundamental:
                if t in fin_rows or master.get(t):
                    row.update(_fin_columns(fin_rows.get(t, []), master.get(t), today))
                row.update(_target_columns(opinions.get(t, []), yesterday))
            counts["rs"] += row["rs_raw"] is not None
            counts["fin"] += row["fin_quarter"] is not None
            counts["op"] += row["opinion_brokers"] is not None
            rows.append(row)
        markers.append(
            f"[rs_observe] strategy={sid} candidates={len(scanned)} held={len(held)} rs_known={counts['rs']} "
            f"fin_known={counts['fin']} opinion_known={counts['op']} rs_population={population} "
            f"elapsed_ms={int((time.monotonic() - started) * 1000)}"
        )

    try:
        await cs_db.upsert_scores(rows)
    except Exception as e:
        _failed("upsert", e)
        return
    for m in markers:
        logger.info(m)


async def _run(scheduler: Any) -> None:
    try:
        # prepare 대기가 먼저다 — 킬스위치(DB 조회)를 먼저 읽으면 prepare 가 끝나지 않는 단위 테스트의 boot() 마다
        # 풀 미초기화 연결 시도로 teardown 이 10초씩 늘어난다. off 여도 대기 비용은 폴링뿐이다.
        ready = await _wait_prepared(scheduler.registry)
        if not ready or await _read_mode() == "off":
            return
        await asyncio.wait_for(_compute_and_write(ready, today_kst()), RUN_TIMEOUT_SECS)
    except asyncio.TimeoutError:
        _failed("timeout")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _failed("run", e)


def spawn_boot_observe(scheduler: Any) -> asyncio.Task | None:
    """부팅 관찰 기록 태스크를 띄운다(await 없음). 실행 중 루프가 없으면 None. 예외 없음."""
    try:
        return asyncio.get_running_loop().create_task(_run(scheduler), name="rs_fundamental_observe")
    except RuntimeError:
        return None
    except Exception:
        logger.warning("[rs_observe_failed] stage=spawn", exc_info=True)
        return None
