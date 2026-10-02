#!/usr/bin/env python3
"""전략별 예산 사용률·칸 수 측정 + 업종 쏠림·계좌 오픈리스크 (2026-10-02).

READ-ONLY. INSERT/UPDATE/DELETE 없음. KIS 호출 없음. 프로덕션 RDS 에서 안전 실행.
지시서 = `_workspace/analysis/slot_utilization_20261002/` 작업의 입력 — 사용자
질문 「전략당 종목 수 제한(max_positions)이 너무 작게 투자하는 효과가 있지
않나」를 측정으로 확인한다. 판정 규칙은 지시서 §4 에 측정 전 고정돼 있고, 이
스크립트는 숫자만 낸다 — 판정·파라미터 변경 제안은 보고서(report.md)에서 한다.

실행 (EC2, 앱 컨테이너 env 에 DATABASE_URL 존재):
    docker compose exec -T backend python - < tools/slot_utilization_review.py > slot_util.txt
  또는 DSN 직접 지정:
    DATABASE_URL='postgresql://...:...@...:5432/db?sslmode=require' python tools/slot_utilization_review.py

출력 전체를 복사해 주세요.

── 순수 함수 (DB 무관, 단위 테스트 대상 — tests/unit/tools/test_slot_utilization_review.py) ──
- filter_trade_events: PENDING/CANCELLED 제외
- build_daily_timeline: 전략·종목별 보유를 시간순 재구성 → 일자별 장마감 스냅샷(이월 포함)
  + 장중 최대 동시보유 + 랏(매수 1건=1행) + 보유 초과 매도 경고
- reconcile_with_live_positions: 오늘자 재구성 결과 ↔ `positions` 테이블 대조
"""
from __future__ import annotations

import os
import ssl as ssl_mod
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit, parse_qs

STATUSES_INCLUDED = {"COMPLETED", "PARTIAL"}

# 주 기간 = 09-20 입금(250만→500만) 이후. 비교 기간 = 그 이전 60영업일.
PRIMARY_SINCE = os.environ.get("SLOT_REVIEW_SINCE", "2026-09-21")
COMPARE_SINCE = os.environ.get("SLOT_REVIEW_COMPARE_SINCE", "2026-07-01")  # 넉넉히 잡고 스크립트가 60영업일로 자른다


# ───────────────────────── 순수 함수 (DB 무관) ─────────────────────────

@dataclass(frozen=True)
class TradeEvent:
    strategy: str
    ticker: str
    trade_type: str  # "BUY" | "SELL"
    price: float
    quantity: int
    timestamp: datetime  # tz-aware, 호출자가 이미 KST 로 변환해 준다는 계약
    status: str


def filter_trade_events(rows: Iterable[dict]) -> list[TradeEvent]:
    """PENDING/CANCELLED 제외 — COMPLETED/PARTIAL 만 보유 재구성에 들어간다."""
    out: list[TradeEvent] = []
    for r in rows:
        status = str(r.get("status") or "").upper()
        if status not in STATUSES_INCLUDED:
            continue
        out.append(
            TradeEvent(
                strategy=str(r["strategy"]),
                ticker=str(r["ticker"]),
                trade_type=str(r["trade_type"]).upper(),
                price=float(r["price"]),
                quantity=int(r["quantity"]),
                timestamp=r["timestamp"],
                status=status,
            )
        )
    return out


@dataclass
class _OpenLot:
    quantity: int = 0
    cost: float = 0.0  # 누적 매입원가(평단 × 잔여수량)


def _kst_date_iso(ts: datetime) -> str:
    return ts.date().isoformat()


def build_daily_timeline(
    events: Iterable[TradeEvent],
    *,
    strategies: list[str],
    trading_days: list[str],
) -> dict[str, Any]:
    """전략·종목별 보유를 시간순으로 재구성한다.

    `trading_days` 는 오름차순 ISO 날짜 문자열 목록이어야 한다(조밀한 타임라인
    생성 — 거래 없는 날도 직전 장마감 보유를 이월한다).

    반환:
      eod: {(strategy, date): [{"ticker","quantity","cost_basis"}, ...]}
      eod_count / eod_cost_total: {(strategy, date): 값}
      intraday_max_count: {(strategy, date): 그날 장중 동시보유 종목 수 최댓값}
      lots: 매수 1건 = 1행 [{"strategy","ticker","date","quantity","price","trade_type"}]
      oversell_warnings: 보유보다 많은 매도 시도(0 으로 클램프하고 기록)
    """
    events_by_day: dict[str, list[TradeEvent]] = {}
    for e in events:
        events_by_day.setdefault(_kst_date_iso(e.timestamp), []).append(e)
    for day_events in events_by_day.values():
        day_events.sort(key=lambda e: e.timestamp)

    open_lots: dict[tuple[str, str], _OpenLot] = {}
    eod: dict[tuple[str, str], dict[str, _OpenLot]] = {}
    intraday_max_count: dict[tuple[str, str], int] = {}
    lots: list[dict] = []
    oversell_warnings: list[dict] = []

    for day in trading_days:
        day_events = events_by_day.get(day, [])
        day_running_max: dict[str, int] = {s: 0 for s in strategies}

        for ev in day_events:
            lot_key = (ev.strategy, ev.ticker)
            lot = open_lots.setdefault(lot_key, _OpenLot())

            if ev.trade_type == "BUY":
                lot.quantity += ev.quantity
                lot.cost += ev.price * ev.quantity
                lots.append(
                    {
                        "strategy": ev.strategy,
                        "ticker": ev.ticker,
                        "date": day,
                        "quantity": ev.quantity,
                        "price": ev.price,
                        "trade_type": "BUY",
                    }
                )
            elif ev.trade_type == "SELL":
                sell_qty = ev.quantity
                if sell_qty > lot.quantity:
                    oversell_warnings.append(
                        {
                            "strategy": ev.strategy,
                            "ticker": ev.ticker,
                            "date": day,
                            "held": lot.quantity,
                            "sell_qty": sell_qty,
                        }
                    )
                    sell_qty = lot.quantity
                avg_cost = (lot.cost / lot.quantity) if lot.quantity > 0 else 0.0
                lot.cost -= avg_cost * sell_qty
                lot.quantity -= sell_qty
                if lot.quantity <= 0:
                    lot.quantity = 0
                    lot.cost = 0.0

            # 이 전략이 그 시점에 동시에 들고 있는 종목 수(장중 추이)
            open_count = sum(
                1 for (s, _t), l in open_lots.items() if s == ev.strategy and l.quantity > 0
            )
            if ev.strategy not in day_running_max or open_count > day_running_max[ev.strategy]:
                day_running_max[ev.strategy] = max(day_running_max.get(ev.strategy, 0), open_count)

        # 장마감 스냅샷 — strategies 전체에 대해 조밀하게(거래 없는 전략/날도 포함)
        for s in strategies:
            # `_OpenLot` 는 가변 객체라 참조를 그대로 스냅샷에 넣으면 이후 날짜의
            # 매도가 과거 스냅샷까지 소급해 바꿔버린다(실측 09-22~25 전기·전자 3종목
            # cost=0 로 재현됐던 결함) — 반드시 값 복사본을 저장한다.
            snap = {
                t: _OpenLot(l.quantity, l.cost)
                for (ss, t), l in open_lots.items()
                if ss == s and l.quantity > 0
            }
            eod[(s, day)] = snap
            base_count = len(snap)
            prior = day_running_max.get(s, 0)
            intraday_max_count[(s, day)] = max(prior, base_count)

    eod_out = {
        k: [{"ticker": t, "quantity": l.quantity, "cost_basis": l.cost} for t, l in v.items()]
        for k, v in eod.items()
    }
    eod_count = {k: len(v) for k, v in eod_out.items()}
    eod_cost_total = {k: sum(x["cost_basis"] for x in v) for k, v in eod_out.items()}

    return {
        "eod": eod_out,
        "eod_count": eod_count,
        "eod_cost_total": eod_cost_total,
        "intraday_max_count": intraday_max_count,
        "lots": lots,
        "oversell_warnings": oversell_warnings,
    }


def reconcile_with_live_positions(
    reconstructed_today: dict[str, int], live_positions: dict[str, int]
) -> list[dict]:
    """오늘자 재구성 보유수량 ↔ `positions` 테이블 실측을 종목 단위로 대조한다.

    불일치만 반환한다(원인은 추측하지 않는다 — 지시서 §3.2).
    """
    tickers = set(reconstructed_today) | set(live_positions)
    diffs = []
    for t in sorted(tickers):
        r = reconstructed_today.get(t, 0)
        l = live_positions.get(t, 0)
        if r != l:
            diffs.append({"ticker": t, "reconstructed_qty": r, "live_qty": l})
    return diffs


def business_days(start: date, end: date) -> list[str]:
    """start~end(포함) 사이 평일(월~금) ISO 날짜 목록. 공휴일 캘린더는 없음(근사)."""
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ───────────────────────── DB I/O (async main, READ-ONLY) ─────────────────────────

def _prep_dsn(dsn: str):
    """asyncpg 는 DSN 쿼리의 sslmode 를 직접 못 먹으므로 분리해 ssl context 로 전달."""
    parts = urlsplit(dsn)
    q = parse_qs(parts.query)
    sslmode = q.pop("sslmode", ["require"])[0]
    new_query = "&".join(f"{k}={v[0]}" for k, v in q.items())
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    ssl_ctx = None
    if sslmode in ("require", "prefer", "allow", "verify-ca", "verify-full"):
        ssl_ctx = ssl_mod.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl_mod.CERT_NONE
    return clean, ssl_ctx


def _p(s: str = "") -> None:
    print(s, flush=True)


def _fmt_won(v) -> str:
    try:
        return f"{int(v):,}원"
    except Exception:
        return str(v)


async def _safe(conn, label: str, sql: str, *args):
    try:
        return await conn.fetch(sql, *args)
    except Exception as e:  # noqa: BLE001
        _p(f"  ⚠️ [{label}] 쿼리 실패: {type(e).__name__}: {e}")
        return []


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST") or ""
    if len(sys.argv) > 1 and sys.argv[1].startswith("postgres"):
        dsn = sys.argv[1]
    if not dsn:
        _p("❌ DATABASE_URL 환경변수가 없습니다. 컨테이너 안에서 실행하거나 DSN 을 인자로 주세요.")
        sys.exit(1)

    import asyncpg  # 컨테이너 내 존재

    import json as _json

    clean, ssl_ctx = _prep_dsn(dsn)
    conn = await asyncpg.connect(clean, ssl=ssl_ctx)
    try:
        # JSONB=raw dict 바인딩 (src/db/pg.py 와 동일 codec — CLAUDE.md 「코딩 컨벤션」)
        await conn.set_type_codec("jsonb", encoder=_json.dumps, decoder=_json.loads, schema="pg_catalog")
        await conn.set_type_codec("json", encoder=_json.dumps, decoder=_json.loads, schema="pg_catalog")
        # 세이프티 — 이 세션에서는 읽기만 한다 (지시서 §8)
        await conn.execute("SET default_transaction_read_only = on")

        _p("=" * 72)
        _p(f"전략별 예산 사용률·칸 수 측정 — 주 기간 {PRIMARY_SINCE}~ / 비교 기간 {COMPARE_SINCE}~")
        _p("=" * 72)

        # ── 0. 등록 전략 + 현재 파라미터 ──
        _p("\n### 0. strategy_config (현재 파라미터 — 코드 기본값이 아니라 이 값이 정본)")
        cfg_rows = await _safe(
            conn, "strategy_config",
            "SELECT strategy_id, enabled, weight, params FROM strategy_config ORDER BY strategy_id",
        )
        strategies: list[str] = []
        for r in cfg_rows:
            strategies.append(r["strategy_id"])
            params = r["params"] or {}
            _p(
                f"  {r['strategy_id']}: enabled={r['enabled']} weight={r['weight']} "
                f"max_positions={params.get('max_positions')} position_ratio={params.get('position_ratio')} "
                f"sizing_mode={params.get('sizing_mode')} buy_paused={params.get('buy_paused')} "
                f"stop_loss_rate={params.get('stop_loss_rate')} hard_stop_pct={params.get('hard_stop_pct')} "
                f"entry_end={params.get('entry_end')}"
            )
        if not strategies:
            _p("  (strategy_config 행 없음 — 이후 쿼리가 빈 결과를 낼 수 있음)")

        # ── 1. 거래 원자료 (trade_history, 주 기간 + 비교 기간 합쳐 한 번에) ──
        _p("\n### 1. trade_history 원자료 조회 (COMPLETED/PARTIAL, 비교 기간 시작부터)")
        trade_rows = await _safe(
            conn, "trade_history",
            """
            SELECT strategy, ticker, trade_type, price, quantity, status,
                   to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD"T"HH24:MI:SS') AS ts_kst
            FROM trade_history
            WHERE status IN ('COMPLETED', 'PARTIAL')
              AND timestamp >= ($1 || ' 00:00:00+09')::timestamptz
            ORDER BY timestamp
            """,
            COMPARE_SINCE,
        )
        _p(f"  거래 행 수: {len(trade_rows)}")

        # dict + tz-aware KST datetime 으로 정규화 → 순수 함수 입력
        from datetime import timezone as _tz

        kst = _tz(timedelta(hours=9))
        norm_rows = []
        for r in trade_rows:
            d = dict(r)
            d["timestamp"] = datetime.fromisoformat(d.pop("ts_kst")).replace(tzinfo=kst)
            norm_rows.append(d)
        events = filter_trade_events(norm_rows)
        _p(f"  필터 통과(COMPLETED/PARTIAL) 이벤트 수: {len(events)}")

        if not strategies:
            strategies = sorted({e.strategy for e in events})

        if not events:
            _p("\n(거래 이벤트 없음 — 이후 분석 섹션 생략)")
        else:
            min_day = min(_kst_date_iso(e.timestamp) for e in events)
            today_iso = date.today().isoformat()
            days = business_days(date.fromisoformat(min_day), date.fromisoformat(today_iso))
            _p(f"  타임라인 범위: {min_day} ~ {today_iso} ({len(days)}영업일 근사 — 휴장일 미반영)")

            timeline = build_daily_timeline(events, strategies=strategies, trading_days=days)

            if timeline["oversell_warnings"]:
                _p(f"\n⚠️ 보유 초과 매도(추적-실거래 어긋남) {len(timeline['oversell_warnings'])}건:")
                for w in timeline["oversell_warnings"][:20]:
                    _p(f"    {w}")

            primary_days = [d for d in days if d >= PRIMARY_SINCE]

            # ── 2. 전략별 칸 사용률 / 예산 사용률 (주 기간) ──
            _p(f"\n### 2. 전략별 칸·예산 사용률 — 주 기간 {PRIMARY_SINCE}~ (장마감 기준)")
            for s in strategies:
                counts = [timeline["eod_count"].get((s, d), 0) for d in primary_days]
                intraday = [timeline["intraday_max_count"].get((s, d), 0) for d in primary_days]
                if not counts:
                    continue
                max_pos_row = next((r for r in cfg_rows if r["strategy_id"] == s), None)
                max_positions = (max_pos_row["params"] or {}).get("max_positions") if max_pos_row else None
                full_days_eod = sum(1 for c in counts if max_positions and c >= max_positions)
                full_days_intraday = sum(1 for c in intraday if max_positions and c >= max_positions)
                zero_days = sum(1 for c in counts if c == 0)
                _p(
                    f"  {s} (max_positions={max_positions}): "
                    f"장마감 칸찬날 {full_days_eod}/{len(counts)} "
                    f"({full_days_eod/len(counts)*100:.0f}%) · "
                    f"장중최대 칸찬날 {full_days_intraday}/{len(counts)} "
                    f"({full_days_intraday/len(counts)*100:.0f}%) · "
                    f"보유0 날 {zero_days}/{len(counts)} · "
                    f"평균 보유종목수 {sum(counts)/len(counts):.2f}"
                )

            # ── 3. 랏 모양(1주 비율, q 분포) ──
            _p(f"\n### 3. 랏 모양 — 매수 1건당 수량 (주 기간 {PRIMARY_SINCE}~)")
            for s in strategies:
                qtys = [
                    l["quantity"] for l in timeline["lots"]
                    if l["strategy"] == s and l["date"] >= PRIMARY_SINCE
                ]
                if not qtys:
                    _p(f"  {s}: 매수 체결 없음")
                    continue
                one_share = sum(1 for q in qtys if q == 1)
                qtys_sorted = sorted(qtys)
                median = qtys_sorted[len(qtys_sorted) // 2]
                _p(
                    f"  {s}: 매수 {len(qtys)}건 · 1주 비율 {one_share/len(qtys)*100:.0f}% "
                    f"· 중앙 수량 {median}주"
                )

            # ── 4. 계좌 전체 현금 비중 (오늘자) ──
            _p("\n### 4. 계좌 전체 — 오늘자 재구성 보유 vs positions 테이블 대조")
            today_recon: dict[str, int] = {}
            for s in strategies:
                for row in timeline["eod"].get((s, today_iso), []):
                    today_recon[row["ticker"]] = today_recon.get(row["ticker"], 0) + row["quantity"]
            live_rows = await _safe(
                conn, "positions", "SELECT ticker, quantity FROM positions",
            )
            live_pos = {r["ticker"]: r["quantity"] for r in live_rows}
            diffs = reconcile_with_live_positions(today_recon, live_pos)
            if diffs:
                _p(f"  불일치 {len(diffs)}건(원인 미추정 — 목록만):")
                for d in diffs:
                    _p(f"    {d}")
            else:
                _p("  일치 (재구성 == positions 테이블)")

        # ── 5. daily_performance — 전략별 예산(≈total_asset − 당일 실현손익) + 계좌 순자산 ──
        _p(f"\n### 5. daily_performance — 일별 total_asset (주 기간 {PRIMARY_SINCE}~)")
        perf_rows = await _safe(
            conn, "daily_performance",
            """
            SELECT date, strategy, total_asset, daily_realized_pnl
            FROM daily_performance
            WHERE date >= $1
            ORDER BY strategy, date
            """,
            date.fromisoformat(PRIMARY_SINCE),
        )
        _p(f"  행 수: {len(perf_rows)} (strategy='total' = 계좌 전체 — 다른 전략과 합산 금지)")
        # (strategy, date) -> total_asset  /  date -> 계좌 순자산('total' 행)
        budget_by_sd: dict[tuple[str, str], float] = {}
        net_asset_by_day: dict[str, float] = {}
        for r in perf_rows:
            d_iso = r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"])
            if r["strategy"] == "total":
                net_asset_by_day[d_iso] = float(r["total_asset"] or 0)
            else:
                budget_by_sd[(r["strategy"], d_iso)] = float(r["total_asset"] or 0)

        # ── 6. strategy_funnel_snapshots — 칸 찬 날 vs 아닌 날의 미매수 후보 수 근사 ──
        _p(f"\n### 6. strategy_funnel_snapshots — 최종 단계 생존 종목 수 (주 기간 {PRIMARY_SINCE}~)")
        funnel_rows = await _safe(
            conn, "funnel",
            """
            SELECT target_date, strategy_id, step_no, survived_count, survived_tickers
            FROM strategy_funnel_snapshots
            WHERE target_date >= $1 AND is_provisional IS NOT TRUE
            ORDER BY strategy_id, target_date, step_no
            """,
            date.fromisoformat(PRIMARY_SINCE),
        )
        _p(f"  행 수: {len(funnel_rows)}")
        # 전략별 날짜별 "최종 단계(최대 step_no) 생존 종목 집합" — 칸 찬 날 미매수 근사(§3.4-5)에 사용
        funnel_final_by_sd: dict[tuple[str, str], set] = {}
        max_step_by_sd: dict[tuple[str, str], int] = {}
        for r in funnel_rows:
            key = (r["strategy_id"], r["target_date"].isoformat())
            if r["step_no"] >= max_step_by_sd.get(key, -1):
                max_step_by_sd[key] = r["step_no"]
                tickers = r["survived_tickers"] or []
                if isinstance(tickers, list):
                    # 원칙은 문자열 배열이지만(migration 030 주석), 실측 데이터가 다를 수
                    # 있어 dict 원소(예: {"ticker":...})도 방어적으로 흡수한다.
                    norm = []
                    for el in tickers:
                        if isinstance(el, dict):
                            norm.append(str(el.get("ticker", el)))
                        else:
                            norm.append(str(el))
                    funnel_final_by_sd[key] = set(norm)
                else:
                    funnel_final_by_sd[key] = set()

        if events:
            _p(f"\n### 6b. 칸 찬 날 vs 아닌 날 — funnel 최종 생존 중 미매수 종목 수 (일봉 스윙 4전략 근사)")
            swing_strategies = [s for s in strategies if s in (
                "kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout"
            )]
            for s in swing_strategies:
                max_pos_row = next((r for r in cfg_rows if r["strategy_id"] == s), None)
                max_positions = (max_pos_row["params"] or {}).get("max_positions") if max_pos_row else None
                full_misses, other_misses, full_n, other_n = [], [], 0, 0
                for d in primary_days:
                    key = (s, d)
                    survived = funnel_final_by_sd.get(key)
                    if survived is None:
                        continue
                    held_today = {row["ticker"] for row in timeline["eod"].get((s, d), [])}
                    missed = len(survived - held_today)
                    count = timeline["eod_count"].get((s, d), 0)
                    is_full = bool(max_positions) and count >= max_positions
                    if is_full:
                        full_misses.append(missed)
                        full_n += 1
                    else:
                        other_misses.append(missed)
                        other_n += 1
                avg_full = (sum(full_misses) / full_n) if full_n else None
                avg_other = (sum(other_misses) / other_n) if other_n else None
                _p(
                    f"  {s}: 칸찬날(n={full_n}) 평균 미매수 생존종목 "
                    f"{avg_full if avg_full is not None else '표본없음'} · "
                    f"칸안찬날(n={other_n}) 평균 {avg_other if avg_other is not None else '표본없음'} "
                    f"(※ funnel 생존 ≠ 매수신호 — 가격·시간 조건 미반영 근사치)"
                )

            # ── 7. 업종 쏠림 (X1) — 주 기간 전 영업일, 전략 무관 합산 ──
            _p(f"\n### 7. X1 업종 쏠림 — 주 기간 {PRIMARY_SINCE}~ 매일 장마감 기준 (전략 무관 합산)")
            all_held_tickers = set()
            for (s, d), count in timeline["eod_count"].items():
                if d < PRIMARY_SINCE or count == 0:
                    continue
                for row in timeline["eod"][(s, d)]:
                    all_held_tickers.add(row["ticker"])
            sector_rows = await _safe(
                conn, "stock_master_sector",
                """
                SELECT ticker, raw, master_raw
                FROM stock_master
                WHERE ticker = ANY($1::text[])
                """,
                sorted(all_held_tickers),
            )
            _p(f"  보유한 적 있는 종목 {len(all_held_tickers)}개 중 stock_master 매칭 {len(sector_rows)}개")

            # `src/engine/sector_naming.py::resolve_sector_name` 과 같은 우선순위를 그대로
            # 미러링한다(bstp_kor_isnm → kojiro 섹터 키 폴백 → 미분류-{ticker}).
            # 이 분석 스크립트는 src/ 를 수정하지 않고 읽기만 한다 — 함수 재사용(복제 아님).
            try:
                from src.engine.strategies.kojiro import _kojiro_sector_key
            except Exception:

                def _kojiro_sector_key(master_raw, ticker):  # type: ignore[no-redef]
                    return f"미분류-{ticker}"

            ticker_sector: dict[str, str] = {}
            for r in sector_rows:
                raw = r["raw"] if isinstance(r["raw"], dict) else {}
                isnm = str(raw.get("bstp_kor_isnm", "") or "").strip()
                if isnm:
                    ticker_sector[r["ticker"]] = isnm
                else:
                    mraw = r["master_raw"] if isinstance(r["master_raw"], dict) else None
                    ticker_sector[r["ticker"]] = _kojiro_sector_key(mraw, r["ticker"])
            for t in all_held_tickers:
                ticker_sector.setdefault(t, f"미분류-{t}")

            # strategy별 손절 근사치(§ 전제 — 복원 불가 시 「전략 손절% × 매입원가」 근사)
            stop_pct_by_strategy: dict[str, float] = {}
            for r in cfg_rows:
                p = r["params"] or {}
                raw_stop = p.get("hard_stop_pct", p.get("stop_loss_rate"))
                try:
                    stop_pct_by_strategy[r["strategy_id"]] = abs(float(raw_stop)) / 100.0
                except (TypeError, ValueError):
                    stop_pct_by_strategy[r["strategy_id"]] = 0.0

            # 일자별 섹터 집계: {date: {sector: {"tickers": set, "cost": float, "risk": float}}}
            day_sector_agg: dict[str, dict[str, dict]] = {}
            day_total_risk: dict[str, float] = {}
            for (s, d), rows in timeline["eod"].items():
                if d < PRIMARY_SINCE or not rows:
                    continue
                stop_pct = stop_pct_by_strategy.get(s, 0.0)
                for row in rows:
                    sector = ticker_sector.get(row["ticker"], f"미분류-{row['ticker']}")
                    bucket = day_sector_agg.setdefault(d, {}).setdefault(
                        sector, {"tickers": set(), "cost": 0.0, "risk": 0.0}
                    )
                    bucket["tickers"].add(row["ticker"])
                    bucket["cost"] += row["cost_basis"]
                    risk = row["cost_basis"] * stop_pct
                    bucket["risk"] += risk
                    day_total_risk[d] = day_total_risk.get(d, 0.0) + risk

            days_with_concentration = 0
            days_checked = 0
            ranking: list[tuple[str, str, int, float]] = []  # (day, sector, n_tickers, cost)
            for d in primary_days:
                sectors = day_sector_agg.get(d)
                if not sectors:
                    continue
                days_checked += 1
                max_n = max(len(b["tickers"]) for b in sectors.values())
                if max_n >= 3:
                    days_with_concentration += 1
                for sector, b in sectors.items():
                    ranking.append((d, sector, len(b["tickers"]), b["cost"]))

            ranking.sort(key=lambda x: (-x[2], -x[3]))
            _p(f"  같은 업종 3종목 이상 동시 보유한 날: {days_with_concentration}/{days_checked} "
               f"({days_with_concentration/days_checked*100:.0f}%)" if days_checked else "  (표본 없음)")
            _p("  판정 규칙(측정 전 고정) — 이 비율 ≥ 20% 면 「쏠림 있음」, 그 미만이면 「쏠림 낮음」")
            _p("  최대 쏠림 날 상위 10 (날짜, 업종, 동시보유종목수, 매입원가합):")
            for d, sector, n, cost in ranking[:10]:
                _p(f"    {d} | {sector} | {n}종목 | {_fmt_won(cost)}")

            # ── 8. X2 계좌 전체 오픈리스크 ──
            _p(f"\n### 8. X2 계좌 전체 오픈리스크 = Σ오픈리스크(근사) ÷ 순자산(strategy='total')")
            x2_ratios: list[tuple[str, float]] = []
            for d in primary_days:
                risk = day_total_risk.get(d)
                net_asset = net_asset_by_day.get(d)
                if risk is None or not net_asset:
                    continue
                x2_ratios.append((d, risk / net_asset))
            if x2_ratios:
                vals = sorted(v for _, v in x2_ratios)
                n = len(vals)
                _p(
                    f"  표본 {n}일 · 평균 {sum(vals)/n*100:.1f}% · 중앙 {vals[n//2]*100:.1f}% · "
                    f"최대 {vals[-1]*100:.1f}%"
                )
                # 「여러 전략 칸이 동시에 찬 날」 과의 교차표
                max_positions_by_s = {
                    r["strategy_id"]: (r["params"] or {}).get("max_positions") for r in cfg_rows
                }
                multi_full_days = 0
                for d, _ratio in x2_ratios:
                    full_strats = sum(
                        1
                        for s in strategies
                        if max_positions_by_s.get(s)
                        and timeline["eod_count"].get((s, d), 0) >= max_positions_by_s[s]
                    )
                    if full_strats >= 2:
                        multi_full_days += 1
                _p(f"  여러 전략(≥2) 칸이 동시에 찬 날: {multi_full_days}/{n}")
            else:
                _p("  (표본 없음 — daily_performance strategy='total' 또는 오픈리스크 데이터 부족)")

        _p("\n" + "=" * 72)
        _p("완료 — 위 전체를 복사해 주세요.")
        _p("=" * 72)
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
