"""퀀트 재무필터 순수 함수 — 마법공식(Magic Formula) + F-Score-7.

사이클 C2. DB/HTTP/시계 절대 미접촉 순수 함수 모듈. 매매 무관 (계산 계층,
C3/C4 에서 통합·활성). 8영역(risk/order_engine/realtime/auth/api/order.py/
session.py/scanner.py/strategy_registry.py) 미접촉.

- compute_f_score_7: 당기 vs 전기 2기 비교 7지표 Piotroski F-Score 근사.
- compute_magic_formula: 유니버스 상대 순위 (Earnings Yield + ROC, Greenblatt).

`_safe_float` 는 이 모듈 전용 자체 정의 — `src/db/stock_master_financial.py`
와 결합 회피를 위해 import 하지 않는다 (Red 메모 인계 명시).
"""

from __future__ import annotations


def _safe_float(value) -> float | None:
    """value 를 float 로 안전 변환. None/빈문자열/비숫자 → None (graceful)."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool 은 int 서브클래스라 의도치 않은 True/False→1.0/0.0 혼입 차단.
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_f_score_7(curr: dict | None, prev: dict | None) -> int | None:
    """당기(curr) vs 전기(prev) 비교 7지표 F-Score (최대 7점).

    개별 지표 결측/0분모 → 그 지표만 미가점(+0), 전체는 계속 평가.
    2기 부족(curr=None/prev=None/prev 필수 필드 전부 결측) → None (fail-open).
    """
    if curr is None or prev is None:
        return None

    # 2기 부족 판정: prev 의 7지표 핵심 필드가 전부 결측이면 유효 비교 불가.
    prev_keys = (
        "cptl_ntin_rate",
        "lblt_rate",
        "crnt_rate",
        "sale_totl_rate",
        "sale_account",
        "total_aset",
        "cpfn",
    )
    if all(prev.get(k) is None for k in prev_keys):
        return None

    score = 0

    # 지표1: ROA 양수 (cptl_ntin_rate > 0)
    curr_roa = _safe_float(curr.get("cptl_ntin_rate"))
    prev_roa = _safe_float(prev.get("cptl_ntin_rate"))
    if curr_roa is not None and curr_roa > 0:
        score += 1

    # 지표2: ΔROA > 0
    if curr_roa is not None and prev_roa is not None and curr_roa > prev_roa:
        score += 1

    # 지표3: 부채비율 감소 (lblt_rate 감소)
    curr_lblt = _safe_float(curr.get("lblt_rate"))
    prev_lblt = _safe_float(prev.get("lblt_rate"))
    if curr_lblt is not None and prev_lblt is not None and curr_lblt < prev_lblt:
        score += 1

    # 지표4: 유동비율 증가 (crnt_rate 증가)
    curr_crnt = _safe_float(curr.get("crnt_rate"))
    prev_crnt = _safe_float(prev.get("crnt_rate"))
    if curr_crnt is not None and prev_crnt is not None and curr_crnt > prev_crnt:
        score += 1

    # 지표5: 매출총이익율 증가 (sale_totl_rate 증가)
    curr_gm = _safe_float(curr.get("sale_totl_rate"))
    prev_gm = _safe_float(prev.get("sale_totl_rate"))
    if curr_gm is not None and prev_gm is not None and curr_gm > prev_gm:
        score += 1

    # 지표6: 총자산회전율 증가 (sale_account/total_aset, 분모>0 가드)
    curr_sale = _safe_float(curr.get("sale_account"))
    curr_asset = _safe_float(curr.get("total_aset"))
    prev_sale = _safe_float(prev.get("sale_account"))
    prev_asset = _safe_float(prev.get("total_aset"))
    if (
        curr_sale is not None
        and curr_asset is not None
        and curr_asset > 0
        and prev_sale is not None
        and prev_asset is not None
        and prev_asset > 0
    ):
        curr_turnover = curr_sale / curr_asset
        prev_turnover = prev_sale / prev_asset
        if curr_turnover > prev_turnover:
            score += 1

    # 지표7: 자본금 불변/감소 (cpfn <= prev.cpfn)
    curr_cpfn = _safe_float(curr.get("cpfn"))
    prev_cpfn = _safe_float(prev.get("cpfn"))
    if curr_cpfn is not None and prev_cpfn is not None and curr_cpfn <= prev_cpfn:
        score += 1

    return int(score)


def _compute_ey(fin: dict, mktcap: float | None) -> float | None:
    """Earnings Yield: ev_ebitda>0 직접 우선, 아니면 폴백 bsop_prti/EV."""
    ev_ebitda = _safe_float(fin.get("ev_ebitda"))
    if ev_ebitda is not None and ev_ebitda > 0:
        return 1.0 / ev_ebitda

    bsop_prti = _safe_float(fin.get("bsop_prti"))
    total_lblt = _safe_float(fin.get("total_lblt")) or 0.0
    mktcap_val = _safe_float(mktcap) or 0.0
    ev = mktcap_val + total_lblt
    if bsop_prti is not None and ev > 0:
        return bsop_prti / ev

    return None


def _compute_roc(fin: dict) -> float | None:
    """ROC = bsop_prti / ((cras - flow_lblt) + fxas), 분모>0 가드."""
    bsop_prti = _safe_float(fin.get("bsop_prti"))
    cras = _safe_float(fin.get("cras"))
    flow_lblt = _safe_float(fin.get("flow_lblt"))
    fxas = _safe_float(fin.get("fxas"))
    if bsop_prti is None or cras is None or flow_lblt is None or fxas is None:
        return None
    denom = (cras - flow_lblt) + fxas
    if denom <= 0:
        return None
    return bsop_prti / denom


def _rank_descending(values: dict[str, float | None]) -> dict[str, int]:
    """values(ticker -> 값) 를 내림차순 랭킹 (높을수록 rank=1). None 은 최하위.

    결정성 보장: 동점/None 은 ticker 문자열 오름차순으로 안정적 tie-break.
    """
    tickers = sorted(values.keys())  # 결정적 기저 순서
    ranked = sorted(
        tickers,
        key=lambda t: (
            values[t] is None,  # False(0) < True(1) → 값 있는 종목 먼저
            -(values[t]) if values[t] is not None else 0.0,
            t,  # tie-break: ticker 오름차순 (결정적)
        ),
    )
    return {ticker: idx + 1 for idx, ticker in enumerate(ranked)}


def compute_magic_formula(
    series_by_ticker: dict[str, dict],
    mktcap_by_ticker: dict[str, float],
) -> dict[str, dict]:
    """유니버스 상대 순위 (마법공식: Earnings Yield + Return on Capital).

    입력 전 종목이 출력에 존재 (결측도 None 표기, 제외 아님).
    ey_rank/roc_rank 내림차순(높을수록 우량=1위, None 최하위).
    mf_rank = ey_rank + roc_rank (낮을수록 우량).
    """
    if not series_by_ticker:
        return {}

    ey_by_ticker: dict[str, float | None] = {}
    roc_by_ticker: dict[str, float | None] = {}

    for ticker, fin in series_by_ticker.items():
        fin = fin or {}
        mktcap = mktcap_by_ticker.get(ticker)
        ey_by_ticker[ticker] = _compute_ey(fin, mktcap)
        roc_by_ticker[ticker] = _compute_roc(fin)

    ey_ranks = _rank_descending(ey_by_ticker)
    roc_ranks = _rank_descending(roc_by_ticker)

    result: dict[str, dict] = {}
    for ticker in series_by_ticker:
        ey_rank = ey_ranks[ticker]
        roc_rank = roc_ranks[ticker]
        result[ticker] = {
            "ey": ey_by_ticker[ticker],
            "roc": roc_by_ticker[ticker],
            "ey_rank": ey_rank,
            "roc_rank": roc_rank,
            "mf_rank": ey_rank + roc_rank,
        }

    return result
