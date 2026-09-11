"""AI 매수평가 조회 라우트: /api/llm-evaluations/* (cycle276).

정본 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §5 (C37~C40).

거래기록 UI 의 "AI 자문" 버튼이 쓰는 두 창구다 —
- `GET /api/llm-evaluations?order_nos=<CSV>` : 페이지 단위 **배치 요약**(버튼 활성/비활성 판정).
  응답 맵의 키는 `"<trade_date>|<order_no>"` 복합 키다(`summary_key()`) — 주문번호 단독
  키는 같은 번호의 다른 날짜 평가를 지운다(아래 네 번째 계약).
- `GET /api/llm-evaluations/{order_no}`      : 모달 **단건 상세**

## 네 가지 계약

1. **계좌번호는 저장은 원문, 응답은 마스킹**이다. `mask_account_no` 가 앞 4자리 + `****`
   를 만들고, 원문 `account_no` 키는 응답에 **존재하지 않는다**. 리포터 스코프 키가
   GET/HEAD 를 경로 무관 통과시키므로(cycle249) 이 표면에 원문이 실리면 외부 루틴이
   계좌번호를 읽는다. 기존 `mask_secret`(뒤 4자리)과 방향이 반대라 **재사용하지 않는다**.
2. **오류를 삼키지 않는다.** DB 예외 → 500(+`[llm_eval_route_error]`), 결과 없음 → 404
   (배치는 200 + 빈 맵). `except Exception: rows = []` 형태의 fail-silent 는 cycle266 이
   3개월짜리 은폐로 실증한 패턴이다 — 진짜 DB 장애가 "기록 없음" 으로 위장된다.
3. **날짜 축은 배치와 상세가 같아야 한다.** 배치가 주문번호당 1행으로 접으면, 접혀 사라진
   날짜의 거래 행은 버튼이 비활성인데 상세 조회로는 멀쩡히 읽힌다(반대 방향으로도 틀린다).
   그래서 배치는 `(trade_date, order_no)` 쌍 전부를 돌려주고 화면이 두 값으로 대조한다.
   `trade_date` 쿼리가 `YYYY-MM-DD` 가 아니면 **422** 다 — 조용히 무시하면 "가장 최근
   1행" 이 그 행의 평가처럼 응답된다.
4. **`Decimal` 은 여기서 `float` 로 사영한다.** asyncpg 가 NUMERIC 을 `Decimal` 로 주고
   pydantic v2 는 JSON 모드에서 그것을 **문자열**로 직렬화한다 — 프론트의 `toFixed` 가
   그대로 죽는다(cycle266 흰 화면).

인증은 최외곽 미들웨어 단일 지점이 책임진다. 이 파일은 그 계층을 한 줄도 건드리지 않는다.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from src.db import llm_buy_evaluations as llm_eval_db
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-evaluations", tags=["llm-evaluations"])

_MARKER_ERROR = "[llm_eval_route_error]"

# 손익 그리드 최대 페이지(200, `history.py::trade_pnl` 의 size 상한)와 정렬한다.
_MAX_ORDER_NOS = 200

_ACCOUNT_PREFIX_LEN = 4
_ACCOUNT_MIN_LEN = 8


def mask_account_no(raw) -> str:
    """계좌번호 마스킹 — **앞 4자리 + `****`**.

    빈 값·8자 미만은 전체 `****`(길이 누출 방지). `src/config.mask_secret`(뒤 4자리)과
    방향이 반대이므로 **재사용하지 않는다** — 두 관례를 섞으면 어느 쪽이 적용됐는지
    코드를 읽어야만 알 수 있다.
    """
    try:
        s = str(raw or "")
    except Exception:
        return "****"
    if len(s) < _ACCOUNT_MIN_LEN:
        return "****"
    return s[:_ACCOUNT_PREFIX_LEN] + "****"


def _num(value):
    """`Decimal` → `float` 사영(그 외 타입은 그대로)."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _iso_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value


def _ts(row: dict, key: str):
    """`to_char(..., '+09:00')` ISO 별칭 우선, 없으면 원본 값."""
    iso = row.get(f"{key}_iso")
    if iso:
        return iso
    value = row.get(key)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _ticker_name(ticker: str):
    """종목명 보완 — scanner read-only, 미로드 환경은 `None`(라우트 관례)."""
    try:
        from src.engine.scanner import ticker_names
        return ticker_names.get(ticker) or None
    except Exception:
        return None


def _summary(row: dict) -> dict:
    """배치 요약 — 버튼 활성 판정에 필요한 최소 필드만.

    계좌·입력 payload 는 싣지 않는다(C40 + 페이지당 200건이라 응답이 수 MB 로 부푼다).
    """
    return {
        "order_no": str(row.get("order_no") or ""),
        "trade_date": _iso_date(row.get("trade_date")),
        "ticker": row.get("ticker"),
        "strategy_id": row.get("strategy_id"),
        "result": row.get("result"),
        "reason": row.get("reason"),
        "score": row.get("score"),
        "min_score": row.get("min_score"),
        "would_block": row.get("would_block"),
        "evaluated_at": _ts(row, "evaluated_at"),
    }


def _detail(row: dict) -> dict:
    """단건 상세 — **화이트리스트 사영**.

    `SELECT *` 를 그대로 흘리면 미래에 새 열이 생길 때 계좌 같은 민감 값이 조용히
    응답 표면으로 새어 나간다. 원문 `account_no` 키는 여기서 사라진다.
    """
    ticker = str(row.get("ticker") or "")
    return {
        "trade_date": _iso_date(row.get("trade_date")),
        "account_no_masked": mask_account_no(row.get("account_no")),
        "account_product": row.get("account_product"),
        "ticker": ticker,
        "ticker_name": _ticker_name(ticker),
        "order_no": str(row.get("order_no") or ""),
        "eval_kind": row.get("eval_kind"),
        "strategy_id": row.get("strategy_id"),
        "mode": row.get("mode"),
        "result": row.get("result"),
        "reason": row.get("reason"),
        "score": row.get("score"),
        "min_score": row.get("min_score"),
        "would_block": row.get("would_block"),
        "rationale": row.get("rationale"),
        "key_risks": row.get("key_risks"),
        "invalidations": row.get("invalidations"),
        "model": row.get("model"),
        "tokens_in": row.get("tokens_in"),
        "tokens_out": row.get("tokens_out"),
        "cost_usd": _num(row.get("cost_usd")),
        "latency_ms": row.get("latency_ms"),
        "verdict_lag_ms": row.get("verdict_lag_ms"),
        "eval_to_order_lag_ms": row.get("eval_to_order_lag_ms"),
        "order_kst": _ts(row, "order_kst"),
        "evaluated_at": _ts(row, "evaluated_at"),
        "order_price_won": row.get("order_price_won"),
        "ordered_qty": row.get("ordered_qty"),
        "order_notional_won": row.get("order_notional_won"),
        "order_division": row.get("order_division"),
        "order_path": row.get("order_path"),
        "exchange": row.get("exchange"),
        "board": row.get("board"),
        "current_price_won": row.get("current_price_won"),
        "signal_matched": row.get("signal_matched"),
        "signal_price_won": row.get("signal_price_won"),
        "signal_time_local": row.get("signal_time_local"),
        "strategy_board": row.get("strategy_board"),
        "target_won": row.get("target_won"),
        "k": _num(row.get("k")),
        "breakout_excess_bp": _num(row.get("breakout_excess_bp")),
        "post_order_drift_bp": _num(row.get("post_order_drift_bp")),
        "drift_price_won": row.get("drift_price_won"),
        "tick_age_s": _num(row.get("tick_age_s")),
        "budget_total_won": row.get("budget_total_won"),
        "budget_remaining_after_won": row.get("budget_remaining_after_won"),
        "open_positions_n": row.get("open_positions_n"),
        "prompt_version": row.get("prompt_version"),
        "feature_version": row.get("feature_version"),
        "bars_count": row.get("bars_count"),
        "input_payload": row.get("input_payload"),
        "raw_response": row.get("raw_response"),
        "created_at": _ts(row, "created_at"),
    }


def _parse_trade_date(raw: str | None) -> str | None:
    """`trade_date` 쿼리 검증 — `YYYY-MM-DD` 가 아니면 **422**.

    없거나 빈 문자열이면 `None`(= 날짜 축 없이 조회). 파싱 불가를 그대로 DB 로
    넘기면 `_kst.to_date()` 가 경고만 남기고 `None` 을 돌려주므로 **200 + "가장 최근
    1행"** 이 응답된다 — 오타 하나가 "다른 날짜의 평가" 를 조용히 그 행의 평가로
    보여주는 것이고, 호출자는 자기 요청이 무시된 것을 알 길이 없다. 형식 위반은
    시끄럽게 거부한다(`src/routes/strategy_funnel.py::_parse_date` 관례).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"trade_date 형식 YYYY-MM-DD: {exc}")


def _parse_order_nos(raw: str) -> list[str]:
    """CSV 정규화 — 공백 제거 + 빈 항목 제거 + 중복 제거(순서 보존).

    0개 또는 200개 초과는 **422**. 빈 조회가 전체 스캔으로 번지지 않게 하고,
    페이지 상한을 넘는 요청이 조용히 잘리지 않게 한다.
    """
    seen: set[str] = set()
    out: list[str] = []
    for part in (raw or "").split(","):
        item = part.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    if not out:
        raise HTTPException(status_code=422, detail="order_nos 가 비었다 (1~200개 필요)")
    if len(out) > _MAX_ORDER_NOS:
        raise HTTPException(
            status_code=422,
            detail=f"order_nos {len(out)}개 — 최대 {_MAX_ORDER_NOS}개",
        )
    return out


def summary_key(trade_date, order_no) -> str:
    """배치 응답 맵의 키 = `"<trade_date>|<order_no>"`.

    주문번호 **단독**으로는 키를 만들 수 없다 — KIS ODNO 는 하루 단위로만 유일해서
    같은 번호가 여러 날짜에 존재하고, 단독 키로 접으면 한 날짜의 평가만 남아 나머지
    날짜의 거래 행이 "평가 기록 없음"(버튼 비활성)이 된다. 그런데 그 행의 상세
    조회는 날짜와 함께 묻기 때문에 멀쩡히 답을 받는다 — 배치와 상세의 날짜 축이
    어긋나면 화면이 거짓말을 한다(실 PG 재현).

    구분자 `|` 는 두 값 어디에도 나타나지 않는다(`trade_date` = ISO 날짜,
    `order_no` = KIS ODNO 숫자열)이므로 키 충돌이 없다.
    """
    return f"{trade_date or ''}|{order_no or ''}"


@router.get("", response_model=ApiResponse)
async def llm_evaluation_summaries(
    order_nos: str = Query(..., description="주문번호 CSV (1~200개)"),
    trade_date: str | None = Query(None, description="YYYY-MM-DD (선택)"),
):
    """배치 요약 — `"<trade_date>|<order_no>"` 를 키로 하는 맵.

    기록이 없는 조합은 **키 자체가 없다**(`null` 값 아님) — `null` 로 채우면
    프론트가 "기록 있음(값 null)" 과 "기록 없음" 을 구별하지 못한다.

    같은 주문번호가 여러 날짜에 있으면 **날짜마다 한 키**가 나간다(접지 않는다).
    """
    keys = _parse_order_nos(order_nos)
    bound_date = _parse_trade_date(trade_date)

    try:
        rows = await llm_eval_db.list_by_order_nos(keys, trade_date=bound_date)
    except Exception:
        logger.exception("%s batch order_nos=%d", _MARKER_ERROR, len(keys))
        raise HTTPException(status_code=500, detail="AI 매수평가 조회 실패")

    data = {}
    for row in rows or []:
        summary = _summary(row)
        if summary["order_no"] and summary["trade_date"]:
            data[summary_key(summary["trade_date"], summary["order_no"])] = summary
    return ApiResponse(success=True, data=data)


@router.get("/{order_no}", response_model=ApiResponse)
async def llm_evaluation_detail(
    order_no: str,
    trade_date: str | None = Query(None, description="YYYY-MM-DD (선택)"),
):
    """단건 상세 — 모달 본문.

    없으면 404, DB 예외는 500 이다. 두 경우를 섞으면 장애가 "기록 없음" 회색 안내로
    영구 은폐된다(cycle266).
    """
    bound_date = _parse_trade_date(trade_date)

    try:
        row = await llm_eval_db.get_by_order(order_no, trade_date=bound_date)
    except Exception:
        logger.exception("%s order_no=%s", _MARKER_ERROR, order_no)
        raise HTTPException(status_code=500, detail="AI 매수평가 조회 실패")

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"order_no={order_no} 평가 기록 없음 (trade_date={bound_date})",
        )
    return ApiResponse(success=True, data=_detail(row))
