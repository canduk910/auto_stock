#!/usr/bin/env python3
"""kojiro 실측 재검토 — 2026-07-20 진입조건 변경(밴드 4.5→6.0%, 창 3→5) 이후 라이브 결과 집계.

READ-ONLY. INSERT/UPDATE/DELETE 없음. 프로덕션 RDS 에서 안전 실행.

실행 (EC2, 앱 컨테이너 env 에 DATABASE_URL 존재):
    docker compose exec backend python tools/kojiro_live_review.py
  또는 (파일이 컨테이너에 없으면 stdin 파이프):
    docker compose exec -T backend python - < tools/kojiro_live_review.py
  또는 DSN 직접 지정:
    DATABASE_URL='postgresql://...:...@...:5432/db?sslmode=require' python tools/kojiro_live_review.py

출력 전체를 복사해 붙여넣어 주세요.
"""
from __future__ import annotations

import asyncio
import os
import ssl as ssl_mod
import sys
from datetime import date
from urllib.parse import urlsplit, urlunsplit, parse_qs

SINCE = os.environ.get("KOJIRO_REVIEW_SINCE", "2026-07-20")  # 진입조건 변경 배포일
SINCE_D = date.fromisoformat(SINCE)  # DATE 컬럼 파라미터용 (asyncpg 는 date 객체 요구)
STRATEGY = "kojiro"


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
    """섹션별 graceful — 테이블/컬럼 부재 시 에러만 출력하고 계속."""
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

    clean, ssl_ctx = _prep_dsn(dsn)
    conn = await asyncpg.connect(clean, ssl=ssl_ctx)
    try:
        _p("=" * 72)
        _p(f"kojiro 실측 재검토 — {SINCE} 이후 (전략={STRATEGY})")
        _p("=" * 72)

        # ── 1. 거래 요약 (trade_history) ──
        _p("\n### 1. 거래 요약 (COMPLETED/PARTIAL)")
        rows = await _safe(
            conn, "trade_summary",
            """
            SELECT trade_type,
                   count(*) AS n,
                   coalesce(sum(price * quantity), 0) AS gross,
                   coalesce(sum(profit_loss), 0) AS pnl
            FROM trade_history
            WHERE strategy = $1
              AND status IN ('COMPLETED', 'PARTIAL')
              AND timestamp >= ($2 || ' 00:00:00+09')::timestamptz
            GROUP BY trade_type ORDER BY trade_type
            """,
            STRATEGY, SINCE,
        )
        if not rows:
            _p("  (해당 기간 kojiro 체결 거래 없음)")
        for r in rows:
            _p(f"  {r['trade_type']}: {r['n']}건 / 거래대금 {_fmt_won(r['gross'])} / 실현손익 {_fmt_won(r['pnl'])}")

        # 승/패 + 평균 손익률 (SELL 기준)
        wl = await _safe(
            conn, "win_loss",
            """
            SELECT
              count(*) FILTER (WHERE profit_loss > 0) AS wins,
              count(*) FILTER (WHERE profit_loss < 0) AS losses,
              count(*) FILTER (WHERE profit_loss = 0) AS flats,
              coalesce(avg(profit_loss), 0) AS avg_pnl,
              coalesce(sum(profit_loss), 0) AS tot_pnl
            FROM trade_history
            WHERE strategy = $1 AND trade_type = 'SELL'
              AND status IN ('COMPLETED', 'PARTIAL')
              AND timestamp >= ($2 || ' 00:00:00+09')::timestamptz
            """,
            STRATEGY, SINCE,
        )
        if wl and (wl[0]["wins"] or wl[0]["losses"] or wl[0]["flats"]):
            w = wl[0]
            tot = (w["wins"] or 0) + (w["losses"] or 0) + (w["flats"] or 0)
            wr = (w["wins"] / tot * 100) if tot else 0
            _p(f"  매도 {tot}건 — 승 {w['wins']} / 패 {w['losses']} / 본전 {w['flats']} "
               f"(승률 {wr:.0f}%) · 평균 실현손익 {_fmt_won(w['avg_pnl'])} · 합계 {_fmt_won(w['tot_pnl'])}")

        # ── 2. 종목별 실현손익 (매도) ──
        _p("\n### 2. 종목별 실현손익 (매도 체결)")
        by_tkr = await _safe(
            conn, "by_ticker",
            """
            SELECT ticker,
                   count(*) AS sells,
                   coalesce(sum(profit_loss), 0) AS pnl
            FROM trade_history
            WHERE strategy = $1 AND trade_type = 'SELL'
              AND status IN ('COMPLETED', 'PARTIAL')
              AND timestamp >= ($2 || ' 00:00:00+09')::timestamptz
            GROUP BY ticker ORDER BY pnl ASC
            """,
            STRATEGY, SINCE,
        )
        if not by_tkr:
            _p("  (매도 체결 없음)")
        for r in by_tkr:
            _p(f"  {r['ticker']}: {r['sells']}건 실현손익 {_fmt_won(r['pnl'])}")

        # 매수 종목 (진입 실측 — 이름 미표시 버그 관측도 겸함)
        _p("\n### 2b. 매수 체결 종목 (진입)")
        buys = await _safe(
            conn, "buys",
            """
            SELECT ticker, count(*) AS n, coalesce(sum(quantity),0) AS qty,
                   min(timestamp) AS first_at
            FROM trade_history
            WHERE strategy = $1 AND trade_type = 'BUY'
              AND status IN ('COMPLETED', 'PARTIAL')
              AND timestamp >= ($2 || ' 00:00:00+09')::timestamptz
            GROUP BY ticker ORDER BY first_at
            """,
            STRATEGY, SINCE,
        )
        if not buys:
            _p("  (매수 체결 없음)")
        for r in buys:
            _p(f"  {r['ticker']}: {r['n']}회 {r['qty']}주 (최초 {r['first_at']})")

        # ── 3. 일자별 실적 (daily_performance) ──
        _p("\n### 3. 일자별 실적 (daily_performance)")
        perf = await _safe(
            conn, "daily_perf",
            """
            SELECT * FROM daily_performance
            WHERE strategy = $1 AND date >= $2
            ORDER BY date
            """,
            STRATEGY, SINCE_D,
        )
        if not perf:
            _p("  (kojiro 일자별 실적 행 없음)")
        for r in perf:
            d = dict(r)
            day = d.get("date") or d.get("target_date")
            _p(f"  {day}: 실현손익={_fmt_won(d.get('daily_realized_pnl', 0))} "
               f"일수익률={d.get('daily_return_rate', d.get('daily_rate', '?'))}% "
               f"누적={d.get('cumulative_return_rate', '?')}% "
               f"순자산={_fmt_won(d.get('total_asset', 0))}")

        # ── 4. Funnel 추이 (최종 후보 수 = 진입조건 완화 효과) ──
        _p("\n### 4. Funnel 추이 — 최종 후보 수 (step_no=9 우선, 없으면 max step)")
        funnel = await _safe(
            conn, "funnel",
            """
            SELECT target_date, step_no, step_name, survived_count
            FROM strategy_funnel_snapshots
            WHERE strategy_id = $1 AND target_date >= $2
            ORDER BY target_date, step_no
            """,
            STRATEGY, SINCE_D,
        )
        if not funnel:
            _p("  (kojiro funnel 스냅샷 없음)")
        else:
            by_day: dict = {}
            for r in funnel:
                by_day.setdefault(str(r["target_date"]), []).append(r)
            for day, steps in by_day.items():
                steps.sort(key=lambda x: x["step_no"])
                final = next((s for s in steps if s["step_no"] == 9), steps[-1])
                chain = " → ".join(f"{s['step_no']}:{s['survived_count']}" for s in steps)
                _p(f"  {day}: 최종후보={final['survived_count']}  [단계별 {chain}]")

        # ── 5. 현재 보유 (positions) ──
        _p("\n### 5. 현재 kojiro 보유 포지션")
        pos = await _safe(
            conn, "positions",
            """
            SELECT ticker, ticker_name, buy_price, quantity, buy_date, high_since_buy
            FROM positions WHERE strategy_id = $1 ORDER BY buy_date
            """,
            STRATEGY,
        )
        if not pos:
            _p("  (보유 없음)")
        for r in pos:
            _p(f"  {r['ticker']} {r.get('ticker_name') or '(이름없음)'}: "
               f"{r['quantity']}주 @ {_fmt_won(r['buy_price'])} (매수일 {r['buy_date']})")

        # ── 6. 최신 AI자문 backtest_summary (kojiro) ──
        _p("\n### 6. 최신 AI자문 backtest_summary (kojiro)")
        rec = await _safe(
            conn, "param_rec",
            """
            SELECT target_date, backtest_summary, recommended_params, weight_reasoning
            FROM parameter_recommendations
            WHERE strategy_id = $1 ORDER BY target_date DESC LIMIT 3
            """,
            STRATEGY,
        )
        if not rec:
            _p("  (kojiro 자문 행 없음)")
        for r in rec:
            _p(f"  [{r['target_date']}] backtest_summary={r.get('backtest_summary')}")
            if r.get("weight_reasoning"):
                _p(f"     weight_reasoning={r['weight_reasoning']}")

        _p("\n" + "=" * 72)
        _p("완료 — 위 전체를 복사해 주세요.")
        _p("=" * 72)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
