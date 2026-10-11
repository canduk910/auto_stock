"""`exit_ai_evaluations`/`exit_ai_runs` 읽기(cycle446 D-6). 청산 AI 섀도 기록은 `llm_worker`
컨테이너가 쓴다(관찰자 방식) — 이 모듈은 **읽기만** 한다. backend 쪽 어디에서도 이 모듈을
import 해 매매 판단에 쓰지 않는다(가드 = `tests/unit/ast/test_cycle446_ast_exit_ai_scope.py` —
`src/engine/`·8영역에 `exit_ai_*` 언급 0).

설계 = `_workspace/design/2026-10-11_exit_ai_shadow.md`. 스키마 = `supabase/migrations/050_exit_ai_evaluations.sql`.

asyncpg 바인딩 규약(`src/db/CLAUDE.md`) — TIMESTAMPTZ 읽기는 `to_char(...,'+09:00')` 로 KST
ISO 문자열, DATE 는 `_kst.to_date()`. JSONB 는 codec 이 왕복.
"""
from __future__ import annotations

from datetime import date

import src.db.pg as pg
from src.db._kst import to_date

_ISO_SELECT = "YYYY-MM-DD\"T\"HH24:MI:SS.US+09:00"

#: `llm_worker/lw/config.py::EXIT_AI_STRATEGIES` 와 같은 값의 **읽기 쪽 사본**(설계 §2.1).
#: 두 패키지는 별도 배포 단위라 공용 import 가 없다 — 바꾸면 양쪽을 함께 고친다.
EXIT_AI_STRATEGIES = frozenset({
    "donchian_swing", "kojiro", "vcp_breakout", "bull_flag_breakout", "etf_trend",
})


async def get_latest_verdicts(pairs: list[tuple[str, str]]) -> dict:
    """`{(strategy_id, ticker): row}` — 그 (전략, 종목) 쌍의 가장 최근(`bar_date` DESC)
    `result='ok'` 평가 1행(`action`·`exit_score`·`bar_date`·`evaluated_at`·`rationale`).

    잔고 화면 「현재 AI 판단」 칸 용도 — 보유 수만큼(보통 10~20건) 이라 한 쿼리로 OR 조건을
    엮는다. 빈 입력 = 쿼리 없이 `{}`. 조회 실패는 **삼키지 않는다**(호출부가 「평가 없음」
    과 「조회 실패」 를 가른다, 루트 CLAUDE.md 「새 화면 칸은 값이 찍히는지까지 실측」).
    """
    uniq = sorted(set(pairs))
    if not uniq:
        return {}
    conditions = []
    args: list = []
    for sid, ticker in uniq:
        conditions.append(f"(strategy_id = ${len(args) + 1} AND ticker = ${len(args) + 2})")
        args.extend([sid, ticker])
    sql = (
        "SELECT strategy_id, ticker, buy_date, buy_order_no, bar_date, action, exit_score,"
        f" rationale, to_char(evaluated_at, '{_ISO_SELECT}') AS evaluated_at_iso"
        " FROM exit_ai_evaluations WHERE result = 'ok' AND (" + " OR ".join(conditions) + ")"
        " ORDER BY bar_date DESC"
    )
    rows = await pg.fetch(sql, *args)
    out: dict = {}
    for r in rows:
        key = (r["strategy_id"], r["ticker"])
        if key not in out:  # ORDER BY bar_date DESC 라 첫 행이 최신
            out[key] = dict(r)
    return out


async def get_evaluations_for_position(
    *, strategy_id: str, ticker: str, buy_date: date, buy_order_no: str,
) -> list[dict]:
    """그 포지션(전략×종목×매수일×매수주문번호)의 평가 전부(`bar_date` ASC) — 거래일지 카드
    「AI 청산 의견」 요지 용도. 기록 없으면 `[]`(「대상 아님」 과 「평가 없음」 은 호출부가
    `exit_ai_runs` 대상 전략 목록으로 가른다)."""
    sql = (
        "SELECT bar_date, act_date, action, exit_score, rationale, result, reason,"
        " exit_is_manual, outcome_status, exit_date, next_open_won, exit_vwap_after_won,"
        f" to_char(evaluated_at, '{_ISO_SELECT}') AS evaluated_at_iso"
        " FROM exit_ai_evaluations"
        " WHERE strategy_id = $1 AND ticker = $2 AND buy_date = $3 AND buy_order_no = $4"
        " ORDER BY bar_date ASC"
    )
    rows = await pg.fetch(sql, strategy_id, ticker, to_date(buy_date), buy_order_no or "")
    return [dict(r) for r in rows]


async def get_today_run_status(target_date: date) -> dict | None:
    """`exit_ai_runs` 그날 1행(없으면 `None`) — 대시보드 경고등의 「오늘 워커가 안 돌았다」
    최소 판정용(cycle446 D-6)."""
    sql = ("SELECT run_date, bar_date, status, n_targets, n_ok, n_failed, n_skipped,"
           f" to_char(finished_at, '{_ISO_SELECT}') AS finished_at_iso"
           " FROM exit_ai_runs WHERE run_date = $1")
    row = await pg.fetchrow(sql, to_date(target_date))
    return dict(row) if row else None
