"""계좌 묶음 배정 기록 (cycle404 — 단계 0, 자문 cycle400 R1~R5).

명세 = `_workspace/red/cycle404_account_cluster_assign_spec.md`.
요인 목록 확정 근거 = `_workspace/domain_consult/cycle404_factor_etf_list.md` +
운영 DB 실측(`_workspace/domain_consult/cycle404_factor_survey.json`,
`_workspace/domain_consult/cycle404_factor_check.py` 재현).

**이번 사이클은 기록만 한다 — 매수 차단·수량 변경·신호 변경 0.** 매일 아침 부팅에서
포지션 복구가 끝난 뒤 한 번, 보유·후보 종목을 업종 ETF 요인(또는 시장·독립·결측)으로
배정하고 묶음별 유닛·명목을 `system_logs` 에 WARNING 으로 남긴다. 소비처는 아직 없다
(`tests/unit/ast/test_cycle404_ast_account_cluster.py` G2 가 봉인) — 단계 1(섀도 게이트)
에서 `strategy_base.py` 가 이 모듈을 부르게 된다.

leaf 규약(§7): import 는 표준 라이브러리 + `src.db.stock_master_daily.get_recent_daily`
(KIS 폴백 없는 DB 전용 조회) + `src.db.system_config`(읽기) 만. `src.api.*`·scheduler·
risk·order_engine·strategy_registry·session·scanner·realtime·auth 금지. 레지스트리는
duck typing 으로 인자로 받는다(`.all()` · `.enabled()`).

공개 인터페이스:
- `assign_one(stock_rets, market_rets, factors)` — 순수. 종목 하나의 배정 판정(§2).
- `assign_all(series, targets)` — 순수. 여러 종목 일괄 배정 + 요인 결측 보고.
- `summarize(detail, held, cands, net_asset)` — 순수. 묶음·그룹 요약(§4).
- `run_boot_assign(registry, net_asset)` — I/O. 모드 읽기 → 일봉 읽기 → 배정 → 마커(§5~§7).
- `spawn_boot_assign(scheduler_or_registry, net_asset)` — `INITIAL_DELAY_SECS` 뒤 위 함수를
  부르는 백그라운드 task 생성(await 없음).
- `get_assignment_map()` — 당일 배정표(ticker → 라벨) 사본.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, timezone

import src.db.system_config as system_config
from src.db.stock_master_daily import get_recent_daily

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# §2 · §4 상수 (사전 등록 — 섀도 판정 전 변경 금지)
# ══════════════════════════════════════════════════════════════════════
WINDOW_RETURNS = 120
MIN_OVERLAP = 100
CORR_MIN = 0.60
MARKET_MARGIN = 0.03
MARKET_TICKER = "069500"

CLUSTER_CAP_U = 4
CLUSTER_CAP_PCT = 20.0
ACCOUNT_CAP_U = 18

#: 부팅 직후 WS 연결·첫 틱 처리와 DB 풀 경합을 피하기 위한 지연(초, 테스트 seam).
INITIAL_DELAY_SECS = 30
#: 전체 실행 상한(초) — 넘으면 `[account_cluster_unavailable] reason=timeout`.
RUN_TIMEOUT_SECS = 120
#: 일봉 동시 읽기 상한(세마포어).
READ_CONCURRENCY = 4
#: 묶음 후보 목록 마커 상한(넘으면 `...+N`).
CAND_LIST_CAP = 40

#: 업종 ETF 요인 목록 — 순서 = 동률 판정 순서(§3). 10-03 실측
#: (`cycle404_factor_survey.json`)으로 chem(117460)·steel(117680) 0봉 제외,
#: it(266370)은 semi 와 상관 0.96(> 0.90 중복 기준)이라 제외 — 13개 후보안에서
#: 10개로 확정.
FACTORS: tuple[tuple[str, str], ...] = (
    ("091160", "semi"),
    ("305720", "battery"),
    ("244580", "bio"),
    ("091180", "auto"),
    ("139230", "heavy"),
    ("449450", "defense"),
    ("117700", "constr"),
    ("091170", "bank"),
    ("102970", "broker"),
    ("228810", "media"),
)

#: system_config 킬스위치 키 이름(§6). `system_config.get_account_cluster_mode_raw()`
#: 가 실제로 이 키를 읽는다 — 여기 두는 이유는 leaf 가 자신이 쓰는 계좌 키를
#: 스스로 밝혀 두기 위함(§9-8 G3c).
_MODE_KEY = "account_cluster_mode"

_NOT_CLUSTER = ("market", "independent", "missing")
_KST = timezone(timedelta(hours=9))

#: spawn 한 백그라운드 task 를 붙드는 모듈 전역 강한 참조(funnel_capture._BG_TASKS 선례).
_BG_TASKS: set = set()

#: 당일 배정표(ticker → 라벨) — 모듈 메모리, 부팅마다 덮어쓴다.
_ASSIGNMENT_MAP: dict[str, str] = {}


# ══════════════════════════════════════════════════════════════════════
# 순수 함수 — 상관·배정(§2)
# ══════════════════════════════════════════════════════════════════════
def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:  # 표준편차 0 → 상관 없음
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def _corr(dates: list, a: dict, b: dict) -> float | None:
    return _pearson([a[d] for d in dates], [b[d] for d in dates])


def assign_one(
    stock_rets: dict, market_rets: dict, factors: list[tuple[str, dict]]
) -> tuple[str, float | None, str | None, float | None]:
    """종목 하나의 배정 판정(§2 결정적 순서). 순수 — I/O 0.

    Returns:
        (label, m, best_factor_name, b) — `label` 은 요인 이름 또는
        `market`/`independent`/`missing`. `m` = 시장 상관, `b` = 최대 요인 상관.
    """
    base = sorted(set(stock_rets) & set(market_rets))[-WINDOW_RETURNS:]
    if len(base) < MIN_OVERLAP:
        return "missing", None, None, None
    m = _corr(base, stock_rets, market_rets)
    if m is None:
        return "missing", None, None, None

    best_name: str | None = None
    best_corr: float | None = None
    for name, f_rets in factors:
        dates = [d for d in base if d in f_rets]
        if len(dates) < MIN_OVERLAP:
            continue
        c = _corr(dates, stock_rets, f_rets)
        if c is None:
            continue
        if best_corr is None or c > best_corr:  # 동률은 목록 앞 요인 유지
            best_name, best_corr = name, c

    if m >= CORR_MIN and (best_corr is None or m >= best_corr):
        return "market", m, best_name, best_corr
    if best_corr is not None and best_corr >= CORR_MIN and best_corr - m >= MARKET_MARGIN:
        return best_name, m, best_name, best_corr
    return "independent", m, best_name, best_corr


def _returns_by_date(rows: list[tuple], prev_day: dict[str, str]) -> dict[str, float]:
    """[(bas_dd, close), ...](정렬 무관) → {bas_dd: 전일 대비 수익률}.

    `prev_day` = 시장(069500) 달력 기준 {영업일: 직전 영업일}. 종목 쪽 두 행의
    날짜가 그 달력상 연속이 아니면(거래정지 등으로 하루가 빠짐) 그 쌍의 수익률을
    만들지 않는다(§2 — 2일치 수익률이 요인의 1일 수익률과 짝지어져 상관이
    오염되는 것을 막는다).
    """
    sorted_rows = sorted(((str(d), float(c)) for d, c in rows), key=lambda x: x[0])
    out: dict[str, float] = {}
    for (d0, c0), (d1, c1) in zip(sorted_rows, sorted_rows[1:]):
        if prev_day.get(d1) != d0:
            continue
        if c0 > 0 and c1 > 0:
            out[d1] = c1 / c0 - 1.0
    return out


def assign_all(
    series: dict[str, list[tuple]], targets: list[str]
) -> tuple[dict[str, tuple], list[str]] | None:
    """여러 종목 일괄 배정. 순수 — I/O 0.

    `series` = {ticker: [(bas_dd, close), ...]}(정렬 무관, `MARKET_TICKER`·`FACTORS`
    종목의 시계열도 포함). 시장 봉이 부족하면 그날 배정 전체를 건너뛴다(`None`).

    Returns:
        (detail, factor_missing) — `detail[ticker]` = `assign_one` 결과,
        `factor_missing` = 봉 부족으로 제외된 요인 이름 목록.
    """
    market_dates = sorted(str(d) for d, _ in series.get(MARKET_TICKER, []))
    prev_day = dict(zip(market_dates[1:], market_dates))
    market_rets = _returns_by_date(series.get(MARKET_TICKER, []), prev_day)
    if len(market_rets) < MIN_OVERLAP:
        return None

    factor_missing: list[str] = []
    factors: list[tuple[str, dict]] = []
    for ticker, name in FACTORS:
        rets = _returns_by_date(series.get(ticker, []), prev_day)
        if len(rets) < MIN_OVERLAP:
            factor_missing.append(name)
            continue
        factors.append((name, rets))

    detail: dict[str, tuple] = {}
    for t in targets:
        stock_rets = _returns_by_date(series.get(t, []), prev_day)
        detail[t] = assign_one(stock_rets, market_rets, factors)
    return detail, factor_missing


# ══════════════════════════════════════════════════════════════════════
# 순수 함수 — 요약(§4)
# ══════════════════════════════════════════════════════════════════════
def summarize(
    detail: dict[str, tuple],
    held: list[tuple],
    cands: dict[str, list[str]],
    net_asset: float,
) -> dict:
    """묶음·그룹 요약. 순수 — I/O 0.

    `held` = [(ticker, strategy_id, buy_price, quantity), ...] (꺼진 전략 포함 전부).
    `cands` = {strategy_id: [ticker, ...]} (켜진 전략만 — 호출자가 이미 필터).
    보유 종목은 후보에서 제외한다(보유가 우선).
    """
    held_tickers = {t for t, *_ in held}
    clusters: dict[str, dict] = {}
    groups: dict[str, dict] = {g: {"held": [], "cand_n": 0} for g in _NOT_CLUSTER}

    for t, sid, buy_price, qty in held:
        label = detail.get(t, ("missing", None, None, None))
        if label[0] in _NOT_CLUSTER:
            groups[label[0]]["held"].append((t, sid))
            continue
        c = clusters.setdefault(label[0], {"held_u": 0, "notional": 0, "held": [], "cand": []})
        c["held_u"] += 1
        c["notional"] += int(buy_price) * int(qty)
        c["held"].append((t, sid, label[3]))

    seen_cand: set[str] = set()
    for sid, tickers in cands.items():
        for t in tickers:
            if t in held_tickers or t in seen_cand:
                continue
            seen_cand.add(t)
            label = detail.get(t, ("missing", None, None, None))[0]
            if label in _NOT_CLUSTER:
                groups[label]["cand_n"] += 1
                continue
            c = clusters.setdefault(label, {"held_u": 0, "notional": 0, "held": [], "cand": []})
            c["cand"].append((t, sid))

    for c in clusters.values():
        if net_asset and net_asset > 0:
            c["notional_pct"] = c["notional"] / net_asset * 100
        else:
            c["notional_pct"] = None
        over_unit = c["held_u"] >= CLUSTER_CAP_U
        over_pct = c["notional_pct"] is not None and c["notional_pct"] >= CLUSTER_CAP_PCT
        c["would_block_next"] = int(over_unit or over_pct)

    held_u = len(held_tickers)
    return {
        "held_u": held_u,
        "account_over": int(held_u >= ACCOUNT_CAP_U),
        "clusters": clusters,
        "groups": groups,
    }


def get_assignment_map() -> dict[str, str]:
    """당일 배정표(ticker → 라벨) 사본."""
    return dict(_ASSIGNMENT_MAP)


# ══════════════════════════════════════════════════════════════════════
# I/O — 모드 읽기(§6)
# ══════════════════════════════════════════════════════════════════════
async def _resolve_mode() -> tuple[str, object, str | None]:
    """계좌 킬스위치 해석. 반환 (effective, raw_value, reason).

    `reason` 은 `off`/`record` 가 아닐 때만(= WARNING 을 내야 할 때만) 채워진다.
    DB 조회 예외는 여기서 흡수해 `reason="read_error"` 로 바꾼다 — 그 밖의
    모든 해석은 순수 분기다.
    """
    try:
        raw = await system_config.get_account_cluster_mode_raw()
    except Exception:
        return "record", None, "read_error"
    if raw is None:
        return "record", None, None
    if raw == "off":
        return "off", raw, None
    if raw == "record":
        return "record", raw, None
    if raw in ("shadow", "enforce"):
        return "record", raw, "not_implemented"
    return "record", raw, "invalid"


# ══════════════════════════════════════════════════════════════════════
# I/O — 부팅 실행(§5 · §7)
# ══════════════════════════════════════════════════════════════════════
def _snapshot(registry) -> tuple[list[tuple], dict[str, list[str]], list[str]]:
    """보유·후보 스냅샷(메모리, I/O 0). `registry` 가 None 이면 ValueError."""
    if registry is None:
        raise ValueError("registry is None")
    held: list[tuple] = []
    for s in registry.all():
        for t, p in dict(s.state.positions).items():
            held.append((t, s.strategy_id, p.buy_price, p.quantity))
    cands: dict[str, list[str]] = {}
    cand_sources: list[str] = []
    for s in registry.enabled():
        c = getattr(s, "_candidates", None)
        if isinstance(c, dict):
            cands[s.strategy_id] = list(c)
            cand_sources.append(f"{s.strategy_id}:{len(c)}")
        else:
            cand_sources.append(f"{s.strategy_id}:none")
    return held, cands, cand_sources


async def _read_series(allt: list[str]) -> dict[str, list[tuple]]:
    """종목마다 `get_recent_daily` 1회(세마포어로 동시성 제한). 실패 종목은 빈 시계열 —
    단, `MARKET_TICKER` 읽기 실패는 그대로 전파한다(그 종목만 missing 으로 두지 않고
    그날 배정 전체를 포기하기 위해 — `run_boot_assign` 의 바깥 try 가 받는다)."""
    sem = asyncio.Semaphore(READ_CONCURRENCY)

    async def _one(t: str) -> tuple[str, list[tuple]]:
        async with sem:
            try:
                rows = await get_recent_daily(t, WINDOW_RETURNS + 1)
                return t, [(r["bas_dd"], r["close_price"]) for r in rows]
            except Exception:
                if t == MARKET_TICKER:
                    raise
                return t, []

    pairs = await asyncio.gather(*[_one(t) for t in allt])
    return dict(pairs)


def _format_cand_list(cand: list[tuple[str, str]]) -> str:
    items = [f"{t}:{sid}" for t, sid in cand]
    if len(items) > CAND_LIST_CAP:
        return ",".join(items[:CAND_LIST_CAP]) + f"+{len(items) - CAND_LIST_CAP}"
    return ",".join(items)


async def _run(registry, net_asset: float) -> None:
    t0 = time.monotonic()
    effective, raw, reason = await _resolve_mode()
    if reason:
        logger.warning(
            "[account_cluster_mode] value=%s effective=%s reason=%s", raw, effective, reason
        )
    if effective == "off":
        logger.info("[account_cluster_assign] mode=off skip")
        return

    held, cands, cand_sources = _snapshot(registry)
    targets = list(dict.fromkeys([h[0] for h in held] + [t for ts in cands.values() for t in ts]))

    all_tickers = list(dict.fromkeys([MARKET_TICKER] + [t for t, _ in FACTORS] + targets))
    series = await _read_series(all_tickers)

    out = assign_all(series, targets)
    if out is None:
        _ASSIGNMENT_MAP.clear()
        logger.warning("[account_cluster_unavailable] reason=market_short")
        return
    detail, factor_missing = out

    _ASSIGNMENT_MAP.clear()
    _ASSIGNMENT_MAP.update({t: v[0] for t, v in detail.items()})

    summary = summarize(detail, held, cands, net_asset)
    counts = {"clustered": 0, "market": 0, "independent": 0, "missing": 0}
    for t in targets:
        label = detail[t][0]
        counts[label if label in _NOT_CLUSTER else "clustered"] += 1

    today = datetime.now(_KST).date().isoformat()
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.warning(
        "[account_cluster_assign] summary 기록 전용 mode=%s date=%s phase=boot net_asset=%d "
        "held_u=%d account_cap_u=%d account_over=%d targets=%d clustered=%d market=%d "
        "independent=%d missing=%d factor_missing=%s cand_sources=%s elapsed_ms=%d",
        effective, today, int(net_asset), summary["held_u"], ACCOUNT_CAP_U,
        summary["account_over"], len(targets), counts["clustered"], counts["market"],
        counts["independent"], counts["missing"], ",".join(factor_missing),
        ",".join(cand_sources), elapsed_ms,
    )

    for name, c in summary["clusters"].items():
        pct = "none" if c["notional_pct"] is None else f"{c['notional_pct']:.1f}"
        held_str = ",".join(f"{t}:{sid}:{corr:.2f}" for t, sid, corr in c["held"])
        logger.warning(
            "[account_cluster_assign] cluster=%s 기록 전용 held_u=%d cap_u=%d notional=%d "
            "notional_pct=%s cap_pct=20 would_block_next=%d held=%s cand=%s",
            name, c["held_u"], CLUSTER_CAP_U, c["notional"], pct, c["would_block_next"],
            held_str, _format_cand_list(c["cand"]),
        )

    for group_name, v in summary["groups"].items():
        held_str = ",".join(f"{t}:{sid}" for t, sid in v["held"])
        logger.warning(
            "[account_cluster_assign] group=%s 기록 전용 held=%s cand_n=%d",
            group_name, held_str, v["cand_n"],
        )


async def run_boot_assign(registry, net_asset: float) -> None:
    """부팅 묶음 배정 1회(§5~§7). never-raise — 어떤 예외도 밖으로 내지 않는다.

    `RUN_TIMEOUT_SECS` 상한을 여기서 건다. 결손·예외·타임아웃이면 배정표를
    비우고(`[account_cluster_unavailable]`) 끝낸다(이전 값 잔존 금지).
    """
    try:
        await asyncio.wait_for(_run(registry, net_asset), timeout=RUN_TIMEOUT_SECS)
    except asyncio.TimeoutError:
        _ASSIGNMENT_MAP.clear()
        logger.warning("[account_cluster_unavailable] reason=timeout")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # never-raise(§7 §9-5) — 결손은 기록, 매매엔 닿지 않는다
        _ASSIGNMENT_MAP.clear()
        logger.warning(
            "[account_cluster_unavailable] reason=error:%s", type(exc).__name__
        )


def spawn_boot_assign(scheduler_or_registry, net_asset: float):
    """`INITIAL_DELAY_SECS` 뒤 `run_boot_assign` 을 부르는 백그라운드 task 생성.

    일반 def — await 하지 않는다(부팅을 막지 않는다). 실행 중인 이벤트 루프가 없으면
    (예: 테스트에서 동기 호출) `None` 을 돌려주고 예외를 내지 않는다.
    """
    registry = getattr(scheduler_or_registry, "registry", scheduler_or_registry)

    async def _body() -> None:
        await asyncio.sleep(INITIAL_DELAY_SECS)
        await run_boot_assign(registry, net_asset)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_body())
    except Exception:
        return None
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task
