"""cycle297 — 주간 회고 조인·집계 **순수 함수 leaf**.

정본 = `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` §3.5 · §5.1 G3.

"매수 시점 점수 ↔ 청산 손익" 의 정의는 하나여야 한다(자문 §7.3). 페어링은
`db.trade_history.get_trade_pairs()` 가 이미 Python 으로 하고 있으므로 SQL 뷰로
다시 쓰면 정의가 둘이 되고, 라우트 안에 조인·집계를 두면 응답 형식이 바뀔 때마다
분석 로직이 함께 흔들린다. 그래서 이 모듈은 **순수 함수**만 담는다 —
`src.*` import 0 · I/O 0 · `await` 0. 표만 넣어 골든 테스트로 잴 수 있고,
목요일 루틴이 읽는 숫자를 사람이 손으로 검산할 수 있다.

## 계약

```
join_pairs_with_evaluations(pairs, eval_rows, *, since_date, until_date) -> list[dict]
aggregate(rows, *, cost_pct) -> dict
```

- **매칭 축은 `(order_no, trade_date)`** — KIS ODNO 는 하루 단위로만 유일하다
  (`llm_buy_evaluations.py:6-8`). 주문번호 단독 매칭은 같은 번호의 다른 날짜 평가를
  잘못 붙인다.
- **`primary` = 첫 매수 주문(`buy_order_nos[0]`)의 평가** — 한 페어에 매수가 2건 이상인
  사례가 운영 DB 실측 9건이고, 사이클을 연 판단은 첫 매수다.
- **평가 없는 페어는 버리지 않는다** — 버리면 분모가 사라져 커버리지를 못 잰다.
- **손실 정의는 `profit_rate <= cost_pct`**(기본 0.25, 경계 포함) — `get_trade_pairs.profit_loss` 는
  수수료·세금 **전** 값인데 SYSTEM_PROMPT 의 점수 정의는 "차감 **후** 플러스 확률"이라
  0 을 기준으로 삼으면 두 정의가 어긋난다.
"""

from __future__ import annotations

_BUCKET_COUNT = 10


def _score_bucket_index(score) -> "int | None":
    """1~100 점을 10점 단위 1-based 버킷 인덱스(0~9)로. 범위 밖/비수치는 `None`."""
    try:
        s = int(score)
    except (TypeError, ValueError):
        return None
    if not (1 <= s <= 100):
        return None
    return min((s - 1) // 10, _BUCKET_COUNT - 1)


def _pick_primary(
    evaluations: list[dict], buy_order_nos: list[str], buy_date=None,
) -> "dict | None":
    """`buy_order_nos[0]` 에 대응하는 평가 행 — 없으면 `None`(§3.5-4).

    같은 주문번호가 보유 구간 안의 **여러 날짜**에 있으면(KIS ODNO 재사용) §3.5-3 대로
    `trade_date == buy_date` 인 행을 먼저 고른다. 입력 순서에 맡기면 호출자의
    `ORDER BY trade_date DESC` 때문에 **가장 늦은 날짜**가 primary 가 된다 — 사이클을 연
    판단은 첫 매수일의 평가다.
    """
    if not buy_order_nos:
        return None
    first_ono = str(buy_order_nos[0])
    candidates = [ev for ev in evaluations if str(ev.get("order_no") or "") == first_ono]
    if not candidates:
        return None
    bd = str(buy_date or "")
    if bd:
        for ev in candidates:
            if str(ev.get("trade_date") or "") == bd:
                return ev
    return candidates[0]


def _resolve_outcome(profit_rate, *, cost_pct: float) -> "str | None":
    """§3.5-4 — **손실 정의는 이 함수 하나뿐이다.** 경계 포함(`profit_rate == cost_pct`
    도 손실 — "비용과 같으면 남는 게 없다", G3-4a 골든 표).

    🔴 cycle297 검증 정정 — 종전에는 행 수준 `outcome` 을 `profit_rate < 0` 으로 따로
    매기는 `_row_outcome` 이 있었다. 그러면 `0 < profit_rate <= cost_pct` 구간의 페어가
    응답의 `pairs[i].outcome` 에서는 `"win"` 인데 같은 응답의 `aggregate` 에서는 손실로
    세어진다 — 목요일 루틴이 표와 집계를 나란히 읽으면 숫자가 맞지 않고, 사람이 손으로
    검산할 수 있어야 한다는 이 leaf 의 존재 이유가 무너진다. 정의는 하나다.
    """
    if profit_rate is None:
        return None
    try:
        return "loss" if float(profit_rate) <= float(cost_pct) else "win"
    except (TypeError, ValueError):
        return None


#: 손실 정의 기본 임계(%) — 왕복 수수료·세금 근사(명세 §8-2, [추론]).
DEFAULT_COST_PCT = 0.25


def _within_holding_window(trade_date, buy_date, sell_date) -> bool:
    """`buy_date <= trade_date <= sell_date`(문자열 사전식 비교, `YYYY-MM-DD` 계약)."""
    try:
        td = str(trade_date or "")
        bd = str(buy_date or "")
        sd = str(sell_date or "")
        if not td:
            return False
        if bd and td < bd:
            return False
        if sd and td > sd:
            return False
        return True
    except Exception:
        return False


_EVAL_WHITELIST = (
    "order_no", "trade_date", "score", "min_score", "would_block",
    "result", "reason", "prompt_version", "feature_version", "model",
)


def _project_eval(row: dict) -> dict:
    """평가 행을 화이트리스트로 사영 — `account_no` 등은 어디에도 싣지 않는다(§3.5-5)."""
    return {k: row.get(k) for k in _EVAL_WHITELIST}


def join_pairs_with_evaluations(
    pairs, eval_rows, *, since_date, until_date, cost_pct: float = DEFAULT_COST_PCT,
) -> list[dict]:
    """§3.5 — 청산 페어 × 매수 시점 평가 조인. 순수 함수, 입력을 변형하지 않는다.

    1. `status=="closed"` ∧ `sell_date ∈ [since_date, until_date]`(경계 포함) 페어만.
    2. 후보 평가 = 그 페어의 `buy_order_nos` 중 하나와 `order_no` 가 같고,
       `buy_date <= trade_date <= sell_date` 인 행 전부(`evaluations`).
    3. `primary` = `buy_order_nos[0]` 의 평가(그 주문번호의 여러 날짜 중 보유 구간 안의
       행 — 없으면 `None`).
    4. `outcome` = `_resolve_outcome(profit_rate, cost_pct=cost_pct)` — **집계와 같은
       정의**(§3.5-4). 라우트가 쿼리 `cost_pct` 를 그대로 넘기므로 응답의 행 표와
       `aggregate` 가 같은 임계로 판정된다.
    """
    try:
        rows_in = list(pairs or [])
    except Exception:
        rows_in = []
    try:
        evs_in = list(eval_rows or [])
    except Exception:
        evs_in = []

    since = str(since_date or "")
    until = str(until_date or "")
    try:
        cp = float(cost_pct)
    except (TypeError, ValueError):
        cp = DEFAULT_COST_PCT

    # order_no -> [평가 행...] (같은 주문번호가 여러 날짜에 있을 수 있다, §3.5-2).
    evs_by_ono: dict[str, list[dict]] = {}
    for ev in evs_in:
        try:
            ono = str(ev.get("order_no") or "")
        except Exception:
            continue
        if not ono:
            continue
        evs_by_ono.setdefault(ono, []).append(ev)

    # KIS ODNO 는 실거래에서 하루 한 번만 존재한다 — `(order_no, trade_date)` 조합
    # 하나는 정확히 한 페어에만 속한다. 같은 조합을 두 페어가 동시에 주장하는 것은
    # 픽스처 충돌(또는 데이터 오염)뿐이라, **입력 순서상 먼저 나온 페어가 갖는다**
    # (소비된 조합은 뒤 페어에서 재사용되지 않는다).
    consumed: set[tuple[str, str]] = set()

    out: list[dict] = []
    for pair in rows_in:
        try:
            if str(pair.get("status") or "") != "closed":
                continue
            sell_date = pair.get("sell_date")
            sd = str(sell_date or "")
            if not sd:
                continue
            if since and sd < since:
                continue
            if until and sd > until:
                continue

            buy_date = pair.get("buy_date")
            buy_order_nos = [str(x) for x in (pair.get("buy_order_nos") or [])]

            evaluations: list[dict] = []
            for ono in buy_order_nos:
                for ev in evs_by_ono.get(ono, ()):
                    trade_date = ev.get("trade_date")
                    key = (ono, str(trade_date or ""))
                    if key in consumed:
                        continue
                    if _within_holding_window(trade_date, buy_date, sell_date):
                        evaluations.append(_project_eval(ev))
                        consumed.add(key)

            primary = _pick_primary(evaluations, buy_order_nos, buy_date)

            profit_rate = pair.get("profit_rate")
            row = {
                "strategy": pair.get("strategy"),
                "ticker": pair.get("ticker"),
                "ticker_name": pair.get("ticker_name"),
                "pair_key": pair.get("pair_key"),
                "buy_date": buy_date,
                "sell_date": sell_date,
                "buy_price": pair.get("buy_price"),
                "sell_price": pair.get("sell_price"),
                "buy_qty": pair.get("buy_qty"),
                "profit_loss": pair.get("profit_loss"),
                "profit_rate": profit_rate,
                "buy_order_nos": buy_order_nos,
                "evaluations": evaluations,
                "primary": primary,
                "outcome": _resolve_outcome(profit_rate, cost_pct=cp),
            }
            out.append(row)
        except Exception:
            continue

    return out


def _empty_group() -> dict:
    buckets = [
        {"lo": i * 10 + 1, "hi": i * 10 + 10, "n": 0, "loss_rate": None}
        for i in range(_BUCKET_COUNT)
    ]
    return {
        "n_pairs": 0, "n_scored": 0, "n_unscored": 0,
        "n_block": 0, "n_block_loss": 0, "block_hit_rate": None,
        "n_pass": 0, "n_pass_loss": 0, "pass_loss_rate": None,
        "pnl_block_sum": 0.0, "pnl_pass_sum": 0.0,
        "avg_score_win": None, "avg_score_loss": None,
        "buckets": buckets,
        "coverage_pass_rate": None,
    }


def _accumulate(group: dict, *, row: dict, primary: dict, cost_pct: float,
                 score_win: list, score_loss: list) -> None:
    group["n_pairs"] += 1

    scored = bool(primary) and primary.get("result") == "ok" and primary.get("score") is not None
    if not scored:
        group["n_unscored"] += 1
        return
    group["n_scored"] += 1

    outcome = _resolve_outcome(row.get("profit_rate"), cost_pct=cost_pct)
    profit_loss = row.get("profit_loss")

    would_block = bool(primary.get("would_block"))
    if would_block:
        group["n_block"] += 1
        if outcome == "loss":
            group["n_block_loss"] += 1
        if isinstance(profit_loss, (int, float)):
            group["pnl_block_sum"] += float(profit_loss)
    else:
        group["n_pass"] += 1
        if outcome == "loss":
            group["n_pass_loss"] += 1
        if isinstance(profit_loss, (int, float)):
            group["pnl_pass_sum"] += float(profit_loss)

    score = primary.get("score")
    idx = _score_bucket_index(score)
    if idx is not None:
        bucket = group["buckets"][idx]
        bucket["n"] += 1
        if outcome == "loss":
            bucket.setdefault("_loss_n", 0)
            bucket["_loss_n"] += 1

    if outcome == "win" and isinstance(score, (int, float)):
        score_win.append(float(score))
    elif outcome == "loss" and isinstance(score, (int, float)):
        score_loss.append(float(score))


def _finalize_group(group: dict, *, score_win: list, score_loss: list) -> None:
    group["block_hit_rate"] = (
        group["n_block_loss"] / group["n_block"] if group["n_block"] else None
    )
    group["pass_loss_rate"] = (
        group["n_pass_loss"] / group["n_pass"] if group["n_pass"] else None
    )
    group["coverage_pass_rate"] = (
        group["n_pass"] / group["n_scored"] if group["n_scored"] else None
    )
    group["avg_score_win"] = (sum(score_win) / len(score_win)) if score_win else None
    group["avg_score_loss"] = (sum(score_loss) / len(score_loss)) if score_loss else None
    for bucket in group["buckets"]:
        loss_n = bucket.pop("_loss_n", 0)
        bucket["loss_rate"] = (loss_n / bucket["n"]) if bucket["n"] else None


def aggregate(rows, *, cost_pct: float) -> dict:
    """§3.5 — `overall` · `by_strategy[sid]` · `by_prompt_version["<sid>|<pv>"]` 집계.

    입력 행은 변형하지 않는다(순수 함수 계약 — 라우트가 같은 리스트를 응답 본문에도
    싣는다). 손실 정의 = `_resolve_outcome`(= `profit_rate <= cost_pct`, 0 고정 금지) —
    `join_pairs_with_evaluations` 의 행 `outcome` 과 **같은 함수**다.
    """
    try:
        cp = float(cost_pct)
    except (TypeError, ValueError):
        cp = DEFAULT_COST_PCT

    overall = _empty_group()
    overall_win: list = []
    overall_loss: list = []

    by_strategy: dict[str, dict] = {}
    by_strategy_win: dict[str, list] = {}
    by_strategy_loss: dict[str, list] = {}

    by_pv: dict[str, dict] = {}
    by_pv_win: dict[str, list] = {}
    by_pv_loss: dict[str, list] = {}

    try:
        rows_in = list(rows or [])
    except Exception:
        rows_in = []

    for row in rows_in:
        try:
            primary = row.get("primary") or {}
            sid = str(row.get("strategy") or "")

            _accumulate(overall, row=row, primary=primary, cost_pct=cp,
                        score_win=overall_win, score_loss=overall_loss)

            if sid:
                grp = by_strategy.setdefault(sid, _empty_group())
                gw = by_strategy_win.setdefault(sid, [])
                gl = by_strategy_loss.setdefault(sid, [])
                _accumulate(grp, row=row, primary=primary, cost_pct=cp,
                            score_win=gw, score_loss=gl)

            pv = primary.get("prompt_version") if primary else None
            if sid and pv:
                key = f"{sid}|{pv}"
                grp2 = by_pv.setdefault(key, _empty_group())
                gw2 = by_pv_win.setdefault(key, [])
                gl2 = by_pv_loss.setdefault(key, [])
                _accumulate(grp2, row=row, primary=primary, cost_pct=cp,
                            score_win=gw2, score_loss=gl2)
        except Exception:
            continue

    _finalize_group(overall, score_win=overall_win, score_loss=overall_loss)
    for sid, grp in by_strategy.items():
        _finalize_group(grp, score_win=by_strategy_win.get(sid, []),
                         score_loss=by_strategy_loss.get(sid, []))
    for key, grp in by_pv.items():
        _finalize_group(grp, score_win=by_pv_win.get(key, []),
                         score_loss=by_pv_loss.get(key, []))

    return {"overall": overall, "by_strategy": by_strategy, "by_prompt_version": by_pv}
