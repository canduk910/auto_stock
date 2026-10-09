"""거래일지 카드 조립 — 순수 leaf (cycle413, 거래일지 화면 1b).

명세 = `_workspace/red/cycle413/journal_view_spec.md`(domain-expert) · 계약 =
`_workspace/red/cycle413/journal_view_contract.md` 1절. 이 파일과 테스트
(`tests/unit/engine/test_cycle413_journal_view.py`)가 갈리면 테스트가 정본이다.

🔴 **순수 함수만** — `async def`·`await` 0, DB·API·KIS·8영역 import 0(AST 가드
`tests/unit/ast/test_cycle413_scope_guard.py::test_s4_leaf_is_pure`). 모든 입력은
DB 함수가 돌려주는 모양 그대로 받는다(시각 = KST ISO 문자열, 날짜 = `date`, 금액 =
`Decimal`/`int`).

「모름 ≠ 0」 원칙 — 값이 `None` 이면 짝 `*_na` 가 반드시 있고, 값이 있으면 `*_na` 는
`None` 이다. 숫자 칸에 0 을 채워 「모름」을 위장하지 않는다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

KST = timezone(timedelta(hours=9))

NA_UNKNOWN = "unknown"
NA_BEFORE_RECORD = "before_record"
NA_NOT_APPLICABLE = "not_applicable"
NA_PENDING = "pending"
NA_LOOKUP_FAILED = "lookup_failed"

#: cycle413 이전(09-28 전)에는 접수 전문(`[order_notice]`)이 없어 `order_division` 이
#: 구조적으로 비어 있다 — 고정 사실이라 상수로 둔다(명세 5절).
_DIVISION_RECORD_START = date(2026, 9, 28)

_EXCURSION_CUTOFF = time(15, 30)
_PROVISIONAL_CUTOFF = time(6, 0)


# ════════════════════════════════════════════════════════════════════════════
# 공통 숫자·시각 헬퍼
# ════════════════════════════════════════════════════════════════════════════
def _f(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _won(v) -> str:
    """천 단위 쉼표, 소수 없음."""
    n = _f(v)
    return f"{round(n):,}" if n is not None else ""


def _dateof(ts: str | None) -> date | None:
    if not ts:
        return None
    try:
        return date.fromisoformat(str(ts)[:10])
    except ValueError:
        return None


def _parse_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except ValueError:
        return None


def _parse_record_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _before(d: date | None, threshold: date | None) -> bool:
    return d is not None and threshold is not None and d < threshold


def _orders_threshold(record_start: dict) -> date | None:
    return _parse_record_date(record_start.get("orders_restored")) or _parse_record_date(
        record_start.get("orders_live"))


def _stops_threshold(record_start: dict) -> date | None:
    return _parse_record_date(record_start.get("stops"))


def _order_price_threshold(record_start: dict) -> date | None:
    return _parse_record_date(record_start.get("order_price"))


def _record_na(d: date | None, threshold: date | None) -> str:
    return NA_BEFORE_RECORD if _before(d, threshold) else NA_UNKNOWN


# ════════════════════════════════════════════════════════════════════════════
# 체결 행 → 주문 라인 묶기 (명세 1-2 OrderLine)
# ════════════════════════════════════════════════════════════════════════════
def _won_floor(x) -> int:
    from decimal import ROUND_FLOOR
    return int(Decimal(str(x)).to_integral_value(rounding=ROUND_FLOOR))


def _group_order_lines(fills: list[dict], side: str) -> list[dict]:
    """같은 `order_no` 체결을 1줄로 묶는다(가중평균 체결가 원 단위 내림, 시간순)."""
    side_fills = [f for f in fills if str(f.get("trade_type") or "").upper() == side]
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for f in sorted(side_fills, key=lambda x: str(x.get("timestamp") or "")):
        ono = str(f.get("order_no") or "").strip()
        key = ono if ono else f"__none__{f.get('id')}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(f)

    lines: list[dict] = []
    for key in order:
        gf = groups[key]
        qty = sum(int(f.get("quantity") or 0) for f in gf)
        amt = sum(_f(f.get("price")) * int(f.get("quantity") or 0) for f in gf)
        price = _won_floor(amt / qty) if qty else 0
        at = min(str(f.get("timestamp") or "") for f in gf)
        ono = str(gf[0].get("order_no") or "").strip() or None
        lines.append({
            "order_no": ono, "fills": gf, "trade_ids": [f.get("id") for f in gf],
            "at": at, "price": price, "qty": qty,
            "date": _dateof(at),
        })
    return lines


# ════════════════════════════════════════════════════════════════════════════
# 체결오차(Slip) — 주문가/판단가 기준 (명세 1-2 Slip, T2)
# ════════════════════════════════════════════════════════════════════════════
def _slip(ref_price: float, ref_src: str, *, side: str, line_fills: list[dict],
          per_fill_ref: dict | None = None, bound: str = "exact") -> dict:
    total = 0.0
    for f in line_fills:
        r = per_fill_ref.get(f.get("id"), ref_price) if per_fill_ref else ref_price
        price = _f(f.get("price")) or 0.0
        qty = int(f.get("quantity") or 0)
        per_share = (price - r) if side == "BUY" else (r - price)
        total += per_share * qty
    qty_total = sum(int(f.get("quantity") or 0) for f in line_fills) or 1
    per_share_avg = total / qty_total
    bp = round(per_share_avg / ref_price * 1e4, 1) if ref_price else 0.0
    return {
        "ref_price": round(ref_price) if isinstance(ref_price, float) and ref_price == round(ref_price)
        else ref_price,
        "ref_src": ref_src,
        "per_share_won": round(per_share_avg),
        "bp": bp,
        "total_won": round(total),
        "bound": bound,
    }


def _slip_order(line: dict, *, side: str, record_start: dict) -> tuple[dict | None, str | None]:
    per_fill_ref: dict = {}
    covered = False
    for f in line["fills"]:
        op = f.get("order_price")
        if op is not None:
            per_fill_ref[f.get("id")] = _f(op)
            covered = True
    if covered:
        ref_price = next(v for v in per_fill_ref.values())
        return _slip(ref_price, "trade", side=side, line_fills=line["fills"], per_fill_ref=per_fill_ref), None
    return None, None  # 호출자가 journal row 폴백을 시도한다


def _slip_judge_ref_src(judge_src: str | None, source: str | None) -> str:
    if judge_src in ("signal", "log_price"):
        return "restored" if source == "log_restore" else "live"
    if judge_src == "restored_ai":
        return "restored_ai"
    return "derived"


# ════════════════════════════════════════════════════════════════════════════
# 손절선/변화 표 (4절, T5·T6)
# ════════════════════════════════════════════════════════════════════════════
_STOP_FIELDS = ("stop_price", "stop_kind", "target_price", "target_hit", "arm_price")


def _filter_stop_rows(stops: list[dict] | None, *, strategy: str, ticker: str,
                       opened_at: datetime, closed_at: datetime | None, now: datetime,
                       buy_order_nos: list[str]) -> list[dict]:
    if not stops:
        return []
    lo = opened_at - timedelta(seconds=60)
    hi = (closed_at + timedelta(seconds=120)) if closed_at else now
    out = []
    for r in stops:
        if r.get("strategy") != strategy or r.get("ticker") != ticker:
            continue
        at = _parse_dt(r.get("observed_at"))
        if at is None or at < lo or at > hi:
            continue
        pos = r.get("pos_order_no")
        if pos and buy_order_nos and pos not in buy_order_nos:
            continue
        out.append(r)
    out.sort(key=lambda r: str(r.get("observed_at") or ""))
    return out


def _cause(row: dict, prev: dict | None, *, avg_price: float) -> str:
    causes: list[str] = []
    event = row.get("event")
    inputs = row.get("inputs") or {}
    prev_inputs = (prev.get("inputs") or {}) if prev else {}

    def add(label: str) -> bool:
        if label not in causes:
            causes.append(label)
        return len(causes) >= 2

    if event == "paused":
        if add("전략 꺼짐 — 손절 평가 정지"):
            return " · ".join(causes)
    if event == "exit":
        age = inputs.get("snapshot_age_s")
        label = f"청산 직전 스냅샷 ({age}초 전)" if age is not None else "청산 직전 스냅샷"
        if add(label):
            return " · ".join(causes)
    if event == "boot":
        label = "재시작 재계산"
        if row.get("strategy") == "long_tail_volatility":
            label += " · 상한가 모드 소실 가능"
        if add(label):
            return " · ".join(causes)

    if prev is not None:
        if "quantity" in inputs and "quantity" in prev_inputs and inputs["quantity"] != prev_inputs["quantity"]:
            if add("수량 변화(추가 체결·분할 매도)"):
                return " · ".join(causes)
        if "buy_price" in inputs and "buy_price" in prev_inputs and inputs["buy_price"] != prev_inputs["buy_price"]:
            if add("매수가 변화(추가 체결)"):
                return " · ".join(causes)
        if inputs.get("kk_armed") and not prev_inputs.get("kk_armed"):
            if add("3R 도달 — 본전 무장"):
                return " · ".join(causes)
        if row.get("stop_kind") != prev.get("stop_kind"):
            if add("손절선 출처 바뀜"):
                return " · ".join(causes)
        cur_price = row.get("stop_price")
        prev_price = prev.get("stop_price")
        if cur_price is not None and prev_price is not None and prev_price < avg_price <= cur_price:
            if add("본전 승격"):
                return " · ".join(causes)
        if ("high_since_buy" in inputs and "high_since_buy" in prev_inputs
                and inputs["high_since_buy"] is not None and prev_inputs["high_since_buy"] is not None
                and inputs["high_since_buy"] > prev_inputs["high_since_buy"]):
            if add("고점 갱신"):
                return " · ".join(causes)
        if ("entry_atr" in inputs and "entry_atr" in prev_inputs and inputs["entry_atr"] != prev_inputs["entry_atr"]):
            if add("ATR 변화"):
                return " · ".join(causes)
        if row.get("target_price") != prev.get("target_price"):
            if add("목표 갱신"):
                return " · ".join(causes)
        elif row.get("target_hit") != prev.get("target_hit"):
            if add("목표 도달"):
                return " · ".join(causes)

    if event == "first":
        if add("첫 관측"):
            return " · ".join(causes)

    if not causes:
        causes.append("입력 그대로 — 파라미터 변경·일봉 재계산 추정")
    return " · ".join(causes)


def _build_stop_track(rows: list[dict], *, avg_price: float) -> dict:
    out_rows: list[dict] = []
    last_shown: dict | None = None
    # cycle413 보완 1차 F9 — 방향은 「직전에 보인 행 중 값이 있는 것」과 비교한다
    # (명세 4-3). 바로 앞 행이 값 없음(예: engine_idle eod)이어도 그 앞의 값 있는
    # 행으로 건너뛴다 — `last_shown` 하나로는 「값 없는 직전 행」 때문에 방향을
    # 잃는다(400원 내린 재시작 재계산이 「모름」 으로 보였다).
    last_priced_price = None
    hidden_eod = 0
    for row in rows:
        event = row.get("event")
        forced = event in ("first", "boot", "paused", "exit")
        cur_tuple = tuple(row.get(k) for k in _STOP_FIELDS)
        prev_tuple = tuple(last_shown.get(k) for k in _STOP_FIELDS) if last_shown else None
        visible = forced or last_shown is None or cur_tuple != prev_tuple
        if not visible:
            if event == "eod":
                hidden_eod += 1
            continue

        price = row.get("stop_price")
        if last_priced_price is None or price is None:
            direction = None
            delta = None
        elif price > last_priced_price:
            direction, delta = "up", price - last_priced_price
        elif price < last_priced_price:
            direction, delta = "down", price - last_priced_price
        else:
            direction, delta = "flat", 0

        out_rows.append({
            "at": row.get("observed_at"), "event": event, "price": price,
            "kind": row.get("stop_kind"), "delta_won": delta, "direction": direction,
            "cause": _cause(row, last_shown, avg_price=avg_price),
            "target_price": row.get("target_price"), "target_hit": row.get("target_hit"),
            "arm_price": row.get("arm_price"),
            "snapshot_age_s": (row.get("inputs") or {}).get("snapshot_age_s") if event == "exit" else None,
        })
        last_shown = row
        if price is not None:
            last_priced_price = price

    ups = sum(1 for r in out_rows if r["direction"] == "up")
    downs = sum(1 for r in out_rows if r["direction"] == "down")
    paused = any(r["event"] == "paused" for r in out_rows)
    first_val = out_rows[0]["price"] if out_rows else None
    last_val = out_rows[-1]["price"] if out_rows else None
    return {
        "na": None, "first": first_val, "last": last_val, "ups": ups, "downs": downs,
        "paused": paused, "rows": out_rows, "hidden_eod": hidden_eod,
    }


# ════════════════════════════════════════════════════════════════════════════
# 진입 이유 — 3-1(ring 실시간) + 3-2(복원/AI 보강)
# ════════════════════════════════════════════════════════════════════════════
_AI_BREAKOUT_NAME = {
    "volatility_breakout": "돌파선", "long_tail_volatility": "돌파선",
    "donchian_swing": "신고가", "bull_flag_breakout": "깃발 상단",
    "vcp_breakout": "베이스 고점", "etf_trend": "돌파선",
}
_AI_K_STRATEGIES = ("volatility_breakout", "long_tail_volatility")
_AI_CUTOFF = date(2026, 9, 17)

#: cycle413 보완 1차 F11 — VB·LTV 진입 문장에 보드를 밝힌다(ring `signal.board` ·
#: AI 평가 `strategy_board`). 보드를 모르면(키 없음) 문장은 그대로 「돌파선 …」.
_BOARD_LABEL = {"main": "본장", "pre_nxt": "NXT 프리", "post_nxt": "NXT 애프터"}

_STRATEGY_LABEL = {
    "momentum": "모멘텀", "volatility_breakout": "변동성 돌파", "long_tail_volatility": "롱테일 변동성",
    "donchian_swing": "돈키언 스윙", "bull_flag_breakout": "추세 눌림목 돌파", "vcp_breakout": "VCP 돌파",
    "kojiro": "고지로", "etf_trend": "ETF 추세",
}

_TARGET_NONE_TEXT = {
    "momentum": "없음 — 익일 갭 판정·트레일 청산",
    "volatility_breakout": "없음 — 15:20 당일 청산",
    "long_tail_volatility": "없음 — 15:20·익일 청산",
    "kojiro": "없음 — 샹들리에 트레일·스테이지3 청산",
    "vcp_breakout": "없음 — 트레일·추세 이탈 청산",
    "etf_trend": "없음 — 트레일·채널 이탈·돌파 실패 정리",
}


def _ai_eligible(strategy: str, trade_date: date | None) -> bool:
    if strategy not in _AI_BREAKOUT_NAME or trade_date is None:
        return False
    if trade_date < _AI_CUTOFF:
        return strategy in _AI_K_STRATEGIES
    return True


def _find_ai_eval(llm_evals: list[dict] | None, *, trade_date, ticker, order_no) -> dict | None:
    if not llm_evals:
        return None
    for row in llm_evals:
        if row.get("trade_date") == trade_date and row.get("ticker") == ticker and row.get("order_no") == order_no:
            return row
    return None


def _ai_sentence(strategy: str, ai: dict) -> str:
    target = ai.get("target_won")
    name = _AI_BREAKOUT_NAME.get(strategy, "돌파선")
    if strategy in _AI_K_STRATEGIES:
        board_label = _BOARD_LABEL.get(ai.get("strategy_board"))
        if board_label:
            name = f"{board_label} {name}"
    parts = [f"{name} {_won(target)} 돌파"]
    k = ai.get("k")
    if strategy in _AI_K_STRATEGIES and k is not None:
        parts.append(f"K {float(k):.2f}")
    return " · ".join(parts)


def _ring_entry_sentence(strategy: str, signal: dict, params: dict | None) -> str:
    params = params or {}
    if strategy == "momentum":
        parts = [f"전일 종가 {_won(signal.get('prev_close'))} 대비 {_f(signal.get('change_rate')):.1f}% 급등"]
        if params.get("buy_threshold") is not None:
            parts.append(f"기준 {_f(params['buy_threshold']):.1f}%")
        return " · ".join(parts)
    if strategy in ("volatility_breakout", "long_tail_volatility"):
        board_label = _BOARD_LABEL.get(signal.get("board"))
        head = f"{board_label} 돌파선" if board_label else "돌파선"
        parts = [f"{head} {_won(signal.get('target_price'))} 돌파"]
        if signal.get("k") is not None:
            parts.append(f"K {_f(signal['k']):.2f}")
        if signal.get("change_rate") is not None:
            parts.append(f"시가 대비 {_f(signal['change_rate']):.1f}%")
        return " · ".join(parts)
    if strategy == "donchian_swing":
        period = params.get("donchian_period")
        head = f"{int(period)}일 신고가" if period is not None else "신고가"
        parts = [f"{head} {_won(signal.get('donchian_high'))} 돌파"]
        if signal.get("atr") is not None:
            parts.append(f"ATR {_won(signal['atr'])}")
        return " · ".join(parts)
    if strategy == "bull_flag_breakout":
        parts = [f"깃발 상단 {_won(signal.get('flag_high'))} 돌파"]
        if signal.get("target_price") is not None:
            parts.append(f"측정 목표 {_won(signal['target_price'])}")
        if signal.get("atr") is not None:
            parts.append(f"ATR {_won(signal['atr'])}")
        return " · ".join(parts)
    if strategy == "vcp_breakout":
        parts = [f"베이스 고점 {_won(signal.get('base_high'))} 돌파"]
        if signal.get("atr") is not None:
            parts.append(f"ATR {_won(signal['atr'])}")
        return " · ".join(parts)
    if strategy == "kojiro":
        stage = signal.get("stage")
        parts = [f"스테이지{stage} 신규 진입", "이평 정배열"]
        if signal.get("atr") is not None:
            parts.append(f"ATR {_won(signal['atr'])}")
        return " · ".join(parts)
    if strategy == "etf_trend":
        parts = [f"돌파선 {_won(signal.get('line'))} 종가 돌파(전일)"]
        if signal.get("open_price") is not None:
            parts.append(f"시가 {_won(signal['open_price'])} 진입")
        if signal.get("atr") is not None:
            parts.append(f"N {_won(signal['atr'])}")
        return " · ".join(parts)
    return f"{_STRATEGY_LABEL.get(strategy, strategy)} 매수 신호"


def _entry_reason(anchor_row: dict | None, *, strategy: str, orders_failed: bool,
                   buy_date: date | None, record_start: dict, llm_evals: list[dict] | None,
                   order_no: str | None, ticker: str, fills_failed: bool = False) -> dict:
    if orders_failed:
        return {"code": None, "sub": None, "phrase": None, "renamed_from": None, "text": None,
                "src": None, "signal_src": None, "na": NA_LOOKUP_FAILED}

    signal_src = None
    if anchor_row is not None:
        signal_src = (anchor_row.get("signal") or {}).get("signal_src")

    ai = None
    if signal_src != "ring" and _ai_eligible(strategy, buy_date):
        ai = _find_ai_eval(llm_evals, trade_date=buy_date, ticker=ticker, order_no=order_no)
        if ai is not None and ai.get("target_won") is None:
            ai = None

    if anchor_row is None:
        if ai is not None:
            return {"code": None, "sub": None, "phrase": None, "renamed_from": None,
                    "text": _ai_sentence(strategy, ai), "src": "restored_ai", "signal_src": None, "na": None}
        if fills_failed:
            # cycle413 보완 2차 N2(screens 재검증) — 체결 조회 실패로 `order_no` 자체를 몰라
            # 일지 행을 찾아보지도 못했다. 기록이 없어서(`_record_na`="unknown")가 아니라
            # 우리가 조회에 실패해서다 — lookup_failed 로 낸다(「모름」의 이유를 흐리지 않는다).
            return {"code": None, "sub": None, "phrase": None, "renamed_from": None, "text": None,
                    "src": None, "signal_src": None, "na": NA_LOOKUP_FAILED}
        return {"code": None, "sub": None, "phrase": None, "renamed_from": None, "text": None,
                "src": None, "signal_src": None, "na": _record_na(buy_date, _orders_threshold(record_start))}

    code = anchor_row.get("reason_code")
    sub = anchor_row.get("reason_sub")
    source = anchor_row.get("source")
    src_live_or_restored = "restored" if source == "log_restore" else "live"

    if signal_src == "ring":
        signal = anchor_row.get("signal") or {}
        text = _ring_entry_sentence(strategy, signal, anchor_row.get("params"))
        return {"code": code, "sub": sub, "phrase": None, "renamed_from": None, "text": text,
                "src": "live", "signal_src": "ring", "na": None}

    if ai is not None:
        return {"code": code, "sub": sub, "phrase": None, "renamed_from": None,
                "text": _ai_sentence(strategy, ai), "src": "restored_ai", "signal_src": signal_src, "na": None}

    judge = anchor_row.get("judge_price")
    if judge is not None:
        text = f"매수 신호 · 신호가 {_won(judge)} — 구조값 기록 없음"
    elif signal_src == "log_only":
        text = "거래량 관문 통과 매수 — 구조값 기록 없음"
    elif signal_src == "none":
        text = "매수 신호 기록 없음"
    else:
        return {"code": code, "sub": sub, "phrase": None, "renamed_from": None, "text": None, "src": None,
                "signal_src": signal_src, "na": _record_na(buy_date, _orders_threshold(record_start))}
    return {"code": code, "sub": sub, "phrase": None, "renamed_from": None, "text": text,
            "src": src_live_or_restored, "signal_src": signal_src, "na": None}


# ════════════════════════════════════════════════════════════════════════════
# 청산 이유 — 3-3
# ════════════════════════════════════════════════════════════════════════════
import re as _re

_PATH_TAIL = {"fallback": " · 5호가 폴백"}


def _path_tail(signal: dict, *, parent_order_no: str | None = None) -> str:
    path = signal.get("path")
    if path == "reorder":
        return f" · 잔여 재주문(원주문 {parent_order_no})" if parent_order_no else " · 잔여 재주문"
    return _PATH_TAIL.get(path, "")


def _reason_sub_label(sub: str | None) -> str:
    return {
        "gap_below": "갭 미달", "krx_only": "KRX 전용", "nxt_open_missing": "NXT 시가 미수신",
        "managed": "관리종목", "overheat": "단기과열", "managed+overheat": "관리·과열",
    }.get(sub, sub or "")


_STOP_LOSS_PCT_THRESHOLD = {"kojiro_hard_stop", "bfb_turtle_backstop", "momentum_stop"}
_STOP_LOSS_LINE_ONLY = {"kojiro_atr_stop", "bfb_turtle_stop"}
_STOP_LOSS_PCT_LINE = {"bfb_pullback_stop", "vb_stop"}
_STOP_LOSS_PCT_NO_PREFIX = {"ltv_intraday_stop", "ltv_limit_up_stop"}
_PHRASE_LABEL = {
    "kojiro_hard_stop": "하드 손절", "kojiro_atr_stop": "ATR 손절", "kojiro_trailing": "샹들리에 트레일",
    "kojiro_stage3_exit": "스테이지3 진입", "bfb_turtle_stop": "터틀 손절(E−2N)",
    "bfb_turtle_backstop": "받침선 손절", "bfb_pullback_stop": "눌림목 손절",
    "bfb_measured_target": "측정 목표 도달", "bfb_time_exit": "보유 기한 초과",
    "ltv_intraday_stop": "당일 모드 손절", "ltv_limit_up_stop": "상한가 모드 손절",
    "vb_stop": "고정 손절", "momentum_stop": "고정 손절",
    "donchian_time_exit": "시간 청산", "donchian_time_exit_legacy": "돌파선 아래",
    "donchian_trailing_legacy": "트레일(옛 규칙)",
}


def _line_val(fired, eff) -> int | None:
    return fired if fired is not None else eff


def _exit_sentence(*, code: str | None, sub: str | None, source: str | None,
                    signal: dict, fired, eff, parent_order_no: str | None = None) -> str | None:
    phrase = signal.get("phrase")
    if code == "STOP_LOSS":
        if phrase in _STOP_LOSS_PCT_THRESHOLD:
            pct = abs(_f(signal.get("pct")) or 0.0)
            thr = abs(_f(signal.get("threshold")) or 0.0)
            text = f"{_PHRASE_LABEL[phrase]} — 매수가 대비 {pct:.1f}% (기준 {thr:.1f}%)"
        elif phrase in _STOP_LOSS_LINE_ONLY:
            text = f"{_PHRASE_LABEL[phrase]} — 손절선 {_won(signal.get('line'))} 이탈"
        elif phrase in _STOP_LOSS_PCT_LINE:
            pct = abs(_f(signal.get("pct")) or 0.0)
            text = f"{_PHRASE_LABEL[phrase]} — 매수가 대비 {pct:.1f}%"
            line = _line_val(fired, eff)
            if line is not None:
                text += f" · 선 {_won(line)}"
        elif phrase in _STOP_LOSS_PCT_NO_PREFIX:
            pct = abs(_f(signal.get("pct")) or 0.0)
            text = f"{_PHRASE_LABEL[phrase]} — {pct:.1f}%"
            line = _line_val(fired, eff)
            if line is not None:
                text += f" · 선 {_won(line)}"
        else:
            line = _line_val(fired, eff)
            text = f"손절선 {_won(line)} 이탈" if line is not None else "손절선 이탈"
    elif code == "TRAILING_STOP":
        if phrase in ("kojiro_trailing", "donchian_trailing_legacy"):
            line = _line_val(fired, eff)
            cur = signal.get("current_price")
            text = f"{_PHRASE_LABEL[phrase]} — 선 {_won(line)} 이탈"
            if cur is not None:
                text += f" (현재가 {_won(cur)})"
        else:
            # cycle413 보완 1차 F5 — 워커 문법에 TRAILING_STOP 패턴이 없는 전략
            # (momentum·etf_trend) 은 fired 가 없다. 그럴 때 스냅샷 손절선이
            # `hard_pct`(고정% 근사)면 숫자를 쓰지 않는다 — 근사값을 발동선처럼
            # 보이면 안 된다(값 자체는 `effective_line` 칸에 그대로 남는다).
            if fired is None and signal.get("stop_kind") == "hard_pct":
                line = None
            else:
                line = _line_val(fired, eff)
            text = f"트레일선 {_won(line)} 이탈" if line is not None else "트레일선 이탈"
    elif code == "TAKE_PROFIT":
        target = signal.get("target")
        text = f"측정 목표 {_won(target)} 도달 — 전량 익절"
        if signal.get("current_price") is not None:
            text += f" (현재가 {_won(signal['current_price'])})"
    elif code == "TIME_EXIT":
        if phrase == "donchian_time_exit":
            m = _re.search(r"reason=(\w+)", signal.get("reason_line") or "")
            token = m.group(1) if m else None
            if token == "no_1r":
                text = "+1R 미도달 — 시간 청산"
            elif token == "max_hold":
                text = "최대 보유 기간 도달 — 시간 청산"
            else:
                text = "시간 청산"
        elif phrase == "bfb_time_exit":
            text = "보유 기한 초과 — 시간 청산"
        elif phrase == "donchian_time_exit_legacy":
            text = "돌파선 아래 — 시간 청산(옛 규칙)"
            if signal.get("current_price") is not None:
                text += f" (현재가 {_won(signal['current_price'])})"
        else:
            text = "시간 청산"
    elif code == "TREND_EXIT":
        if phrase == "kojiro_stage3_exit":
            text = "스테이지3 진입 — 추세 종료"
        elif signal.get("_strategy") == "etf_trend":
            text = "15:20 돌파선 아래 — 돌파 실패 정리"
        else:
            text = "추세 이탈 청산"
    elif code == "FORCE_CLEAR":
        text = "15:20 강제청산"
    elif code == "NEXT_DAY_CLEAR":
        if sub == "gap_below":
            gap = _f(signal.get("gap")) or 0.0
            thr = _f(signal.get("gap_threshold")) or 0.0
            text = f"익일 청산 — 갭 {gap:.1f}% < 기준 {thr:.1f}%"
        elif sub == "krx_only":
            text = "익일 청산 — KRX 전용 종목, 09:00 시장가"
        elif sub == "nxt_open_missing":
            text = "익일 청산 — NXT 시가 미수신, KRX 시가 뒤"
        else:
            text = "익일 청산"
    elif code == "STATUS_EXIT":
        text = f"{_reason_sub_label(sub)} 지정 — 보유 청산"
    elif code == "MANUAL":
        text = "수동 매도(화면)"
    elif code is None:
        if source == "external":
            text = "엔진 밖 주문(HTS·MTS) — 사유 기록 없음"
        elif source == "unmatched":
            text = "사유 매핑 없음"
        else:
            return None
    else:
        text = f"{code} 청산"
    text += _path_tail(signal, parent_order_no=parent_order_no)
    return text


def _line_role(code: str | None) -> str | None:
    # cycle413 보완 1차 F4 — 사유 코드를 모르면(기록 전 청산·external·unmatched·일지
    # 조회 실패) 역할을 정하지 않는다. 엔진이 판 것이 아니면 손절 발동 여부도 모른다
    # — 예전엔 여기서 전부 「reference(손절 미발동)」 로 단정했다.
    if code is None:
        return None
    if code in ("STOP_LOSS", "TRAILING_STOP"):
        return "fired"
    if code == "TAKE_PROFIT":
        return "target"
    return "reference"


_FIRED_SRC_DERIVED_PHRASES = {"ltv_intraday_stop", "ltv_limit_up_stop"}


def _fired_src(signal: dict, *, source: str | None) -> str | None:
    phrase = signal.get("phrase")
    if signal.get("line") is not None:
        return "restored" if source == "log_restore" else "live"
    if signal.get("threshold") is not None and signal.get("buy_price") is not None:
        return "derived"
    if phrase in _FIRED_SRC_DERIVED_PHRASES:
        return "derived"
    return "snapshot"


def _exit_reason(row: dict | None, *, orders_failed: bool, exit_date: date | None,
                  record_start: dict, strategy: str) -> dict:
    if orders_failed:
        return {"code": None, "sub": None, "phrase": None, "renamed_from": None, "text": None,
                "src": None, "signal_src": None, "na": NA_LOOKUP_FAILED}
    if row is None:
        return {"code": None, "sub": None, "phrase": None, "renamed_from": None, "text": None,
                "src": None, "signal_src": None, "na": _record_na(exit_date, _orders_threshold(record_start))}

    code = row.get("reason_code")
    sub = row.get("reason_sub")
    source = row.get("source")
    signal = dict(row.get("signal") or {})
    signal["_strategy"] = strategy
    src = "restored" if source == "log_restore" else "live"
    renamed_from = None
    sig_name = signal.get("signal_name")
    if sig_name is not None and code is not None and sig_name != code:
        renamed_from = sig_name

    text = _exit_sentence(code=code, sub=sub, source=source, signal=signal,
                          fired=row.get("fired_line"), eff=row.get("effective_line"),
                          parent_order_no=row.get("parent_order_no"))
    if text is None:
        return {"code": code, "sub": sub, "phrase": signal.get("phrase"), "renamed_from": renamed_from,
                "text": None, "src": None, "signal_src": None,
                "na": _record_na(exit_date, _orders_threshold(record_start))}
    return {"code": code, "sub": sub, "phrase": signal.get("phrase"), "renamed_from": renamed_from,
            "text": text, "src": src, "signal_src": None, "na": None}


# ════════════════════════════════════════════════════════════════════════════
# 익절 목표 (3-4)
# ════════════════════════════════════════════════════════════════════════════
def _target(strategy: str, *, rows: list[dict], anchor_row: dict | None, avg_price: float,
            closed: bool, exit_code: str | None, buy_date: date | None, record_start: dict,
            stops_failed: bool) -> dict:
    if strategy == "bull_flag_breakout":
        target_rows = [r for r in rows if r.get("target_price") is not None]
        anchor_signal_target = (anchor_row.get("signal") or {}).get("target_price") if anchor_row else None
        if target_rows:
            price = target_rows[-1]["target_price"]
            hit = any(r.get("target_hit") for r in rows) or (closed and exit_code == "TAKE_PROFIT")
        elif anchor_signal_target is not None:
            price = anchor_signal_target
            hit = closed and exit_code == "TAKE_PROFIT"
        else:
            price = None
            hit = None
        if price is None:
            na = NA_LOOKUP_FAILED if stops_failed else _record_na(buy_date, _stops_threshold(record_start))
            return {"kind": "measured_move", "price": None, "hit": None,
                    "signal_price": anchor_signal_target, "arm_price": None, "one_r_price": None,
                    "armed_at": None, "text": "측정 목표 기록 없음", "na": na}
        pct = round((price - avg_price) / avg_price * 100, 2) if avg_price else 0.0
        text = f"측정 목표 {_won(price)} ({pct:+.2f}%) — {'도달' if hit else '미도달'}"
        if anchor_signal_target is not None and anchor_signal_target != price:
            text += f" · 재시작 뒤 다시 찾은 목표 — 진입 때 {_won(anchor_signal_target)}"
        return {"kind": "measured_move", "price": price, "hit": bool(hit),
                "signal_price": anchor_signal_target, "arm_price": None, "one_r_price": None,
                "armed_at": None, "text": text, "na": None}

    if strategy == "donchian_swing":
        arm_rows = [r for r in rows if r.get("arm_price") is not None]
        arm_price = arm_rows[-1]["arm_price"] if arm_rows else None
        one_r_price = None
        armed_at = None
        if arm_rows:
            pre_arm_stop = arm_rows[0].get("stop_price")
            if pre_arm_stop is not None:
                one_r_price = round(2 * avg_price - pre_arm_stop)
        prev_armed = False
        for r in rows:
            armed_now = bool((r.get("inputs") or {}).get("kk_armed"))
            if armed_now and not prev_armed:
                armed_at = r.get("observed_at")
                break
            prev_armed = armed_now
        if arm_price is None:
            text = "없음 — 3R 무장가 기록 없음"
        else:
            text = f"3R 무장가 {_won(arm_price)}"
            if one_r_price is not None:
                text += f" · 1R 면제선 {_won(one_r_price)}"
            if armed_at:
                text += f" · {str(armed_at)[5:10]} 무장 — 손절선 본전"
        return {"kind": "none", "price": None, "hit": None, "signal_price": None,
                "arm_price": arm_price, "one_r_price": one_r_price, "armed_at": armed_at,
                "text": text, "na": NA_NOT_APPLICABLE}

    text = _TARGET_NONE_TEXT.get(strategy, "없음")
    return {"kind": "none", "price": None, "hit": None, "signal_price": None, "arm_price": None,
            "one_r_price": None, "armed_at": None, "text": text, "na": NA_NOT_APPLICABLE}


# ════════════════════════════════════════════════════════════════════════════
# 비용 (Costs)
# ════════════════════════════════════════════════════════════════════════════
def _fold_status(statuses: list[str | None]) -> str | None:
    uniq = {s for s in statuses if s is not None}
    if not uniq:
        return None
    return uniq.pop() if len(uniq) == 1 else "mixed"


def _build_costs(pair: dict, *, buy_ids: list, exit_lines: list[dict], costs: dict | None,
                  status: str) -> dict:
    if costs is None:
        exits = [{"order_no": ln["order_no"], "at": ln["at"], "fee": None, "tax": None,
                  "status": None, "allocated": False} for ln in exit_lines]
        return {
            "na": NA_LOOKUP_FAILED, "entry_fee": None, "entry_status": None, "entry_allocated": False,
            "exits": exits, "fee_total": None, "tax_total": None, "paid_total": None,
            "expected_exit": None, "expected_exit_na": (NA_NOT_APPLICABLE if status == "closed"
                                                         else NA_LOOKUP_FAILED),
            "status": None, "allocated": False,
        }

    # cycle413 보완 1차 F10 — 비용 맵에 없는 체결 id 는 0원이 아니라 None(「모름 ≠ 0」).
    # 일부라도 맵에 없으면 그 몫(entry_fee·그 청산 줄의 fee/tax)을 통째로 None 으로
    # 낸다(부분합을 전체인 척 내지 않는다).
    buy_found_ids = [i for i in buy_ids if i in costs]
    buy_entries = [costs[i] for i in buy_found_ids]
    if buy_ids and len(buy_found_ids) < len(buy_ids):
        entry_fee = None
    else:
        entry_fee = sum(c["fee"] for c in buy_entries) if buy_entries else 0.0
    entry_status = _fold_status([c.get("cost_status") for c in buy_entries])
    entry_allocated = any(c.get("allocated") for c in buy_entries)

    exits = []
    for ln in exit_lines:
        want_ids = ln["trade_ids"]
        found_ids = [i for i in want_ids if i in costs]
        entries = [costs[i] for i in found_ids]
        if want_ids and len(found_ids) < len(want_ids):
            fee = None
            tax = None
        else:
            fee = sum(c["fee"] for c in entries) if entries else 0.0
            tax = sum(c["tax"] for c in entries) if entries else 0.0
        exits.append({
            "order_no": ln["order_no"], "at": ln["at"],
            "fee": fee, "tax": tax,
            "status": _fold_status([c.get("cost_status") for c in entries]),
            "allocated": any(c.get("allocated") for c in entries),
        })

    if entry_fee is None or any(x["fee"] is None or x["tax"] is None for x in exits):
        paid_total = None
    else:
        paid_total = entry_fee + sum((x["fee"] or 0.0) + (x["tax"] or 0.0) for x in exits)

    fee_total = pair.get("fee")
    tax_total = pair.get("tax")

    if status == "closed":
        expected_exit = None
        expected_exit_na = NA_NOT_APPLICABLE
    else:
        # 실값은 수량 맥락이 필요해 `build_card` 가 뒤에서 채운다(fee_total/tax_total
        # 둘 다 있을 때만) — 여기서는 안전한 기본값(대기)만 둔다.
        expected_exit = None
        expected_exit_na = NA_PENDING

    return {
        "na": None, "entry_fee": entry_fee, "entry_status": entry_status,
        "entry_allocated": entry_allocated, "exits": exits,
        "fee_total": fee_total, "tax_total": tax_total, "paid_total": paid_total,
        "expected_exit": expected_exit, "expected_exit_na": expected_exit_na,
        "status": pair.get("cost_status"), "allocated": bool(pair.get("allocated")),
    }


# ════════════════════════════════════════════════════════════════════════════
# 보유 중 MFE/MAE (6절)
# ════════════════════════════════════════════════════════════════════════════
def _row_has_lock(row: dict) -> bool:
    flng = row.get("flng_cls_code")
    if flng is not None and str(flng).strip() not in ("", "00"):
        return True
    prtt = row.get("prtt_rate")
    if prtt is not None:
        try:
            if abs(_f(prtt) or 0.0) > 1e-9:
                return True
        except (TypeError, ValueError):
            return True
    return False


def _is_provisional(row: dict) -> bool:
    bas_dd = row.get("bas_dd")
    updated = _parse_dt(row.get("updated_at"))
    if not isinstance(bas_dd, date) or updated is None:
        return False
    threshold = datetime.combine(bas_dd + timedelta(days=1), _PROVISIONAL_CUTOFF, tzinfo=KST)
    return updated < threshold


def _held_qty_at_1530(buy_fills: list[dict], sell_fills: list[dict], day: date) -> float:
    cutoff = datetime.combine(day, _EXCURSION_CUTOFF, tzinfo=KST)
    bought = sum(int(f.get("quantity") or 0) for f in buy_fills
                 if (_parse_dt(f.get("timestamp")) or cutoff) < cutoff)
    sold = sum(int(f.get("quantity") or 0) for f in sell_fills
               if (_parse_dt(f.get("timestamp")) or cutoff) < cutoff)
    return bought - sold


def _build_excursion(*, ticker: str, avg_price: float, buy_fills: list[dict], sell_fills: list[dict],
                      closes: list[dict] | None, business_days: list[date] | None) -> dict:
    if closes is None or business_days is None:
        return {"basis_price": avg_price, "mfe": None, "mae": None, "closes_k": 0, "closes_n": 0,
                "provisional_dates": [], "lock_dates": [], "na": NA_LOOKUP_FAILED}

    own_closes = {r["bas_dd"]: r for r in closes if r.get("ticker") == ticker}

    qualifying: list[tuple[date, float]] = []
    for day in sorted(set(business_days)):
        qty = _held_qty_at_1530(buy_fills, sell_fills, day)
        if qty > 0:
            qualifying.append((day, qty))

    closes_n = len(qualifying)
    candidates: list[dict] = []
    provisional_dates: list[str] = []
    lock_dates: list[str] = []
    for day, qty in qualifying:
        row = own_closes.get(day)
        if row is None:
            continue
        close = row.get("close_price")
        pct = round((close - avg_price) / avg_price * 100, 2) if avg_price else 0.0
        krw = round((close - avg_price) * qty)
        provisional = _is_provisional(row)
        lock = _row_has_lock(row)
        if provisional:
            provisional_dates.append(day.isoformat())
        if lock:
            lock_dates.append(day.isoformat())
        candidates.append({"pct": pct, "krw": krw, "date": day.isoformat(), "close": close,
                           "qty": int(qty), "provisional": provisional})

    closes_k = len(candidates)
    if closes_n == 0:
        return {"basis_price": avg_price, "mfe": None, "mae": None, "closes_k": 0, "closes_n": 0,
                "provisional_dates": [], "lock_dates": [], "na": NA_NOT_APPLICABLE}
    if closes_k == 0:
        return {"basis_price": avg_price, "mfe": None, "mae": None, "closes_k": 0, "closes_n": closes_n,
                "provisional_dates": [], "lock_dates": [], "na": NA_UNKNOWN}

    mfe = candidates[0]
    mae = candidates[0]
    for c in candidates[1:]:
        if c["pct"] > mfe["pct"]:
            mfe = c
        if c["pct"] < mae["pct"]:
            mae = c

    return {"basis_price": avg_price, "mfe": mfe, "mae": mae, "closes_k": closes_k, "closes_n": closes_n,
            "provisional_dates": provisional_dates, "lock_dates": lock_dates, "na": None}


# ════════════════════════════════════════════════════════════════════════════
# build_card — 조립 본체
# ════════════════════════════════════════════════════════════════════════════
def _pair_kst_iso(d, t) -> str | None:
    """페어의 `buy_date`/`buy_time`(또는 `sell_date`/`sell_time`) → KST ISO 문자열.

    체결 행 조회 실패(F8)로 fills 가 없을 때 opened_at/closed_at 을 이걸로 채운다.
    """
    if d is None or t is None:
        return None
    d_str = d.isoformat() if isinstance(d, date) else str(d)
    return f"{d_str}T{t}+09:00"


def build_card(
    pair: dict, *,
    fills: list[dict] | None,
    orders: list[dict] | None,
    stops: list[dict] | None,
    note: dict | None,
    closes: list[dict] | None,
    business_days: list[date] | None,
    llm_evals: list[dict] | None,
    costs: dict | None,
    record_start: dict,
    now: datetime,
) -> dict:
    strategy = pair.get("strategy")
    ticker = pair.get("ticker")
    status = pair.get("status")
    buy_ids = list(pair.get("buy_trade_ids") or [])
    partial_ids = list(pair.get("partial_sell_trade_ids") or [])
    buy_order_nos = list(pair.get("buy_order_nos") or [])

    # cycle413 보완 1차 F8 — 체결 행 조회 실패(fills=None). 화면 칸은 그 칸에만
    # 번지게 하고(TS non-null 유지) MFE/MAE 만 lookup_failed 로 낸다.
    fills_failed = fills is None

    buy_fills_all = [] if fills_failed else [f for f in fills if str(f.get("trade_type") or "").upper() == "BUY"]
    sell_fills_all = [] if fills_failed else [f for f in fills if str(f.get("trade_type") or "").upper() == "SELL"]

    entry_lines = [] if fills_failed else _group_order_lines(fills, "BUY")
    exit_lines_raw = [] if fills_failed else _group_order_lines(fills, "SELL")

    anchor_trade_id = buy_ids[0] if buy_ids else None
    if fills_failed:
        opened_at = _pair_kst_iso(pair.get("buy_date"), pair.get("buy_time"))
    else:
        opened_at = entry_lines[0]["at"] if entry_lines else None
    opened_dt = _parse_dt(opened_at)
    opened_date = _dateof(opened_at)

    closed_at = None
    if status == "closed":
        if fills_failed:
            closed_at = _pair_kst_iso(pair.get("sell_date"), pair.get("sell_time"))
        elif exit_lines_raw:
            closed_at = exit_lines_raw[-1]["at"]
    closed_dt = _parse_dt(closed_at)

    held_days = None
    if opened_date is not None:
        end_date = _dateof(closed_at) if closed_at else now.date()
        held_days = (end_date - opened_date).days

    orders_failed = orders is None
    orders_map: dict = {}
    if orders is not None:
        for row in orders:
            key = (row.get("order_date"), str(row.get("order_no") or ""), row.get("side"))
            orders_map[key] = row

    # ── record_notice ────────────────────────────────────────────────────────
    order_thr = _orders_threshold(record_start)
    stops_thr = _stops_threshold(record_start)
    record_notice = None
    if _before(opened_date, order_thr):
        record_notice = "before_orders"
    elif _before(opened_date, stops_thr):
        record_notice = "before_stops"

    # ── 주문 라인(entry/exit) 공통 조립 ───────────────────────────────────────
    def _row_for(line: dict, side: str) -> dict | None:
        if orders_failed or not line.get("date") or not line.get("order_no"):
            return None
        return orders_map.get((line["date"], line["order_no"], side))

    def _build_line(line: dict, side: str, *, record_start=record_start) -> tuple[dict, dict | None]:
        row = _row_for(line, side)
        d = line.get("date")
        if orders_failed:
            source = source_na = None
            division = division_na = None
            judge_price = judge_upper = judge_src = judge_na = None
            path = parent = None
            source_na = division_na = judge_na = NA_LOOKUP_FAILED
        elif row is None:
            na = _record_na(d, order_thr)
            source = division = None
            source_na = division_na = na
            judge_price = judge_upper = judge_src = None
            judge_na = na
            path = parent = None
        else:
            source = row.get("source")
            source_na = None
            division = row.get("order_division")
            if division is not None:
                division_na = None
            else:
                division_na = NA_BEFORE_RECORD if d and d < _DIVISION_RECORD_START else NA_UNKNOWN
            path = (row.get("signal") or {}).get("path")
            parent = row.get("parent_order_no")
            if side == "BUY":
                judge_price = row.get("judge_price")
                judge_upper = None
                if judge_price is not None:
                    judge_src = "signal"
                    judge_na = None
                else:
                    ai = None
                    signal_src = (row.get("signal") or {}).get("signal_src")
                    if signal_src != "ring" and _ai_eligible(strategy, d):
                        ai = _find_ai_eval(llm_evals, trade_date=d, ticker=ticker, order_no=line.get("order_no"))
                        if ai is not None and ai.get("signal_price_won") is None:
                            ai = None
                    if ai is not None:
                        judge_price = ai.get("signal_price_won")
                        judge_src = "restored_ai"
                        judge_na = None
                    else:
                        judge_src = None
                        judge_na = _record_na(d, order_thr)
            else:
                sig = row.get("signal") or {}
                judge_price = row.get("judge_price")
                judge_upper = sig.get("judge_upper")
                judge_src = sig.get("judge_src")
                judge_na = None if (judge_price is not None or judge_upper is not None) else _record_na(d, order_thr)

        slip_order, _ = _slip_order(line, side=side, record_start=record_start)
        slip_order_na = None
        if slip_order is None:
            jrow_price = row.get("order_price") if row is not None else None
            if jrow_price is not None:
                jsrc = "restored" if (row.get("source") == "log_restore") else "live"
                slip_order = _slip(_f(jrow_price), jsrc, side=side, line_fills=line["fills"])
            elif orders_failed:
                slip_order_na = NA_LOOKUP_FAILED
            else:
                slip_order_na = _record_na(d, _order_price_threshold(record_start))

        slip_judge = None
        if not orders_failed and row is not None:
            jp = judge_price if judge_price is not None else judge_upper
            if jp is not None:
                jsrc2 = _slip_judge_ref_src(judge_src, row.get("source"))
                order_ref = slip_order["ref_price"] if slip_order else None
                if order_ref is None or round(_f(jp), 6) != round(_f(order_ref), 6):
                    bound = "upper" if (judge_price is None and judge_upper is not None) else "exact"
                    slip_judge = _slip(_f(jp), jsrc2, side=side, line_fills=line["fills"], bound=bound)

        ln_out = {
            "side": side, "order_no": line.get("order_no"), "trade_ids": line["trade_ids"],
            "at": line["at"], "price": line["price"], "qty": line["qty"],
            "division": division, "division_na": division_na,
            "source": source, "source_na": source_na, "path": path, "parent_order_no": parent,
            "judge": {"price": judge_price, "upper": judge_upper, "src": judge_src, "na": judge_na},
            "slip_order": slip_order, "slip_order_na": slip_order_na, "slip_judge": slip_judge,
        }
        return ln_out, row

    entry_order_lines = []
    anchor_row = None
    for i, line in enumerate(entry_lines):
        ln, row = _build_line(line, "BUY")
        entry_order_lines.append(ln)
        if i == 0:
            anchor_row = row

    exit_order_lines = []
    for line in exit_lines_raw:
        ln, row = _build_line(line, "SELL")
        d = line.get("date")
        if orders_failed:
            reason = {"code": None, "sub": None, "phrase": None, "renamed_from": None, "text": None,
                      "src": None, "signal_src": None, "na": NA_LOOKUP_FAILED}
        else:
            reason = _exit_reason(row, orders_failed=False, exit_date=d, record_start=record_start,
                                  strategy=strategy)
        realized = None
        if all(f.get("profit_loss") is not None for f in line["fills"]):
            realized = int(sum(Decimal(str(f.get("profit_loss"))) for f in line["fills"]))
        role = _line_role(reason.get("code"))
        fired = row.get("fired_line") if row else None
        # cycle413 보완 1차 F12 — 익절(TAKE_PROFIT) 청산의 발동선은 워커가 줄에
        # 못 남겼어도(`fired_line=None`, 복원분 등) 신호의 목표가(`signal.target`)로
        # 세운다 — 화면이 「—」 를 그리지 않게.
        target_derived = False
        if fired is None and role == "target" and row is not None:
            sig_target = (row.get("signal") or {}).get("target")
            if sig_target is not None:
                fired = sig_target
                target_derived = True
        eff = row.get("effective_line") if row else None
        fired_src = None
        if fired is not None and row is not None:
            if target_derived:
                fired_src = "restored" if row.get("source") == "log_restore" else "live"
            else:
                fired_src = _fired_src(row.get("signal") or {}, source=row.get("source"))
        snapshot_age = (row.get("signal") or {}).get("snapshot_age_s") if row else None
        if fired is None and eff is None:
            line_na = NA_LOOKUP_FAILED if orders_failed else _record_na(d, order_thr)
        else:
            line_na = None
        ln.update({
            "reason": reason, "realized_gross_krw": realized, "fired_line": fired, "fired_src": fired_src,
            "effective_line": eff, "snapshot_age_s": snapshot_age, "line_role": role, "line_na": line_na,
        })
        exit_order_lines.append(ln)

    entry_qty = sum(ln["qty"] for ln in entry_order_lines)
    avg_price = _f(pair.get("buy_price")) or 0.0

    # ── entry.reason / initial_stop / target ─────────────────────────────────
    anchor_order_no = entry_order_lines[0]["order_no"] if entry_order_lines else None
    reason = _entry_reason(
        anchor_row, strategy=strategy, orders_failed=orders_failed, buy_date=opened_date,
        record_start=record_start, llm_evals=llm_evals, order_no=anchor_order_no, ticker=ticker,
        fills_failed=fills_failed,
    )

    stops_failed = stops is None
    filtered_stops = _filter_stop_rows(
        stops, strategy=strategy, ticker=ticker, opened_at=opened_dt or now,
        closed_at=closed_dt, now=now, buy_order_nos=buy_order_nos,
    ) if not stops_failed else []

    if stops_failed:
        initial_stop = {"price": None, "kind": None, "pct_from_entry": None, "observed_at": None,
                        "delay_s": None, "na": NA_LOOKUP_FAILED, "first_seen": None}
        stop_track = {"na": NA_LOOKUP_FAILED, "first": None, "last": None, "ups": 0, "downs": 0,
                     "paused": False, "rows": [], "hidden_eod": 0}
    elif not filtered_stops:
        na = _record_na(opened_date, stops_thr)
        initial_stop = {"price": None, "kind": None, "pct_from_entry": None, "observed_at": None,
                        "delay_s": None, "na": na, "first_seen": None}
        stop_track = {"na": na, "first": None, "last": None, "ups": 0, "downs": 0,
                     "paused": False, "rows": [], "hidden_eod": 0}
    else:
        earliest = filtered_stops[0]
        earliest_date = _dateof(earliest.get("observed_at"))
        earliest_dt = _parse_dt(earliest.get("observed_at"))
        if earliest_date == opened_date and earliest.get("stop_kind") != "mode_dependent":
            price = earliest.get("stop_price")
            delay = int((earliest_dt - opened_dt).total_seconds()) if (earliest_dt and opened_dt) else None
            pct = round((price - avg_price) / avg_price * 100, 2) if (price is not None and avg_price) else None
            initial_stop = {"price": price, "kind": earliest.get("stop_kind"), "pct_from_entry": pct,
                            "observed_at": earliest.get("observed_at"), "delay_s": delay, "na": None,
                            "first_seen": None}
        elif earliest_date == opened_date and earliest.get("stop_kind") == "mode_dependent":
            initial_stop = {"price": None, "kind": earliest.get("stop_kind"), "pct_from_entry": None,
                            "observed_at": None, "delay_s": None, "na": NA_UNKNOWN, "first_seen": None}
        else:
            na = _record_na(opened_date, stops_thr)
            initial_stop = {"price": None, "kind": None, "pct_from_entry": None, "observed_at": None,
                            "delay_s": None, "na": na,
                            "first_seen": {"price": earliest.get("stop_price"), "kind": earliest.get("stop_kind"),
                                          "observed_at": earliest.get("observed_at")}}
        stop_track = _build_stop_track(filtered_stops, avg_price=avg_price)

    exit_code = exit_order_lines[-1]["reason"].get("code") if (status == "closed" and exit_order_lines) else None
    target = _target(strategy, rows=filtered_stops, anchor_row=anchor_row, avg_price=avg_price,
                     closed=(status == "closed"), exit_code=exit_code, buy_date=opened_date,
                     record_start=record_start, stops_failed=stops_failed)

    # ── pnl ───────────────────────────────────────────────────────────────────
    unrealized = status == "open"
    gross = pair.get("profit_loss")
    gross_rate = pair.get("profit_rate")
    net = pair.get("net_profit_loss")
    net_rate = pair.get("net_profit_rate")
    costs_failed = costs is None
    gross_na = None if gross is not None else (NA_PENDING if unrealized else NA_UNKNOWN)
    net_na = None if net is not None else (NA_LOOKUP_FAILED if costs_failed else
                                           (NA_PENDING if unrealized else NA_UNKNOWN))

    partial_fills = [] if fills_failed else [f for f in fills if f.get("id") in partial_ids]
    if partial_fills and all(f.get("profit_loss") is not None for f in partial_fills):
        partial_gross = int(sum(Decimal(str(f.get("profit_loss"))) for f in partial_fills))
    else:
        partial_gross = None
    partial_fee = pair.get("partial_fee")
    partial_tax = pair.get("partial_tax")
    if partial_gross is not None and partial_fee is not None and partial_tax is not None:
        partial_net = partial_gross - _f(partial_fee) - _f(partial_tax)
    else:
        partial_net = None

    pnl = {
        "gross_krw": gross, "gross_rate_pct": gross_rate, "net_krw": net, "net_rate_pct": net_rate,
        "unrealized": unrealized, "partial_gross_krw": partial_gross, "partial_net_krw": partial_net,
        "gross_na": gross_na, "net_na": net_na,
    }

    # ── costs ─────────────────────────────────────────────────────────────────
    costs_block = _build_costs(pair, buy_ids=buy_ids, exit_lines=exit_order_lines, costs=costs, status=status)
    if fills_failed:
        # cycle413 보완 2차 N1 — 체결 조회 실패면 청산분(수량·비용)을 전혀 모른다.
        # `exit_lines=[]` 로 들어가 `paid_total` 이 진입 수수료만으로 「합계」인 척 나오고
        # (부분합을 전체처럼 내는 「모름 ≠ 0」 위반), `entry_qty=0` 폴백(`or 1`)이
        # `ratio_remaining` 을 비율이 아닌 보유수량 그 자체로 왜곡시켜 `expected_exit` 가
        # 음수로 나온다(screens·trader 재현: ≈ −17,877). 둘 다 lookup_failed 로 낸다.
        costs_block["paid_total"] = None
        if status != "closed":
            costs_block["expected_exit"] = None
            costs_block["expected_exit_na"] = NA_LOOKUP_FAILED
    elif (status != "closed" and costs_block["na"] is None and costs_block["fee_total"] is not None
          and costs_block["entry_fee"] is not None):
        total_buy_qty = entry_qty or 1
        remaining_qty = _f(pair.get("buy_qty")) or 0.0
        ratio_remaining = remaining_qty / total_buy_qty if total_buy_qty else 1.0
        entry_fee_portion = (costs_block["entry_fee"] or 0.0) * ratio_remaining
        fee_est = _f(costs_block["fee_total"]) - entry_fee_portion
        tax_est = _f(costs_block["tax_total"]) or 0.0
        costs_block["expected_exit"] = fee_est + tax_est
        costs_block["expected_exit_na"] = None

    # ── excursion ────────────────────────────────────────────────────────────
    # F8 — 체결 행 조회 실패면 종가·영업일이 있어도 보유 수량(fills 기반)을 모르므로
    # 「해당 없음」 으로 위장하지 않고 조회 실패로 낸다.
    excursion = _build_excursion(
        ticker=ticker, avg_price=avg_price, buy_fills=buy_fills_all, sell_fills=sell_fills_all,
        closes=None if fills_failed else closes, business_days=None if fills_failed else business_days,
    )

    note_out = None
    if note is not None:
        note_out = {"body": note.get("body"), "updated_at": note.get("updated_at")}

    return {
        "pair_key": pair.get("pair_key"), "anchor_trade_id": anchor_trade_id,
        "strategy": strategy, "ticker": ticker, "ticker_name": pair.get("ticker_name"),
        "status": status, "opened_at": opened_at, "closed_at": closed_at, "held_days": held_days,
        "record_notice": record_notice, "pnl": pnl,
        "entry": {"avg_price": int(round(avg_price)), "qty": entry_qty, "orders": entry_order_lines,
                 "reason": reason, "initial_stop": initial_stop, "target": target},
        "exits": exit_order_lines, "stop_track": stop_track, "costs": costs_block,
        "excursion": excursion, "note": note_out,
    }
