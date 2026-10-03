"""KIS 기간별매매손익현황조회 `TTTC8715R` — 실비용(수수료·제세금) 사후 대사용 조회 (트랙 C).

정본 스펙 = `docs/kis/domestic-stock-order.md` 「기간별매매손익현황조회」 + KIS MCP
`inquire_period_trade_profit` 공식 샘플. HTS [0856] 기간별 매매손익 「종목별」 화면과 같다.

- **실전 전용**(모의투자 미지원) — 모의 환경에서는 KIS 를 부르지 않고 `RealEnvRequired`.
- 계좌 TR 이라 **메인 단일 경로 `kis_get`** 을 쓴다(시세 풀은 다른 계좌라 쓸 수 없다).
- 연속조회 = 응답 헤더 `tr_cont` 가 `M`/`F` 면 다음 쪽. 다음 요청은 헤더 `tr_cont="N"` +
  본문 `ctx_area_fk100`/`ctx_area_nk100` 을 그대로 되돌린다. `_MAX_PAGES` 에서 멈추면
  `truncated=True` 로 알린다(조용히 자르지 않는다).
- 비주문 조회라 8영역 `src/api/order.py` 와 분리한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.api.base import kis_get
from src.config import settings

PERIOD_TRADE_PROFIT_URL = "/uapi/domestic-stock/v1/trading/inquire-period-trade-profit"
PERIOD_TRADE_PROFIT_TR_ID = "TTTC8715R"

# 한 쪽 행 수는 KIS 가 정한다. 50쪽이면 수년치 종목별 행도 충분하다 — 넘으면 truncated.
_MAX_PAGES = 50
_NEXT_PAGE_FLAGS = ("M", "F")


class RealEnvRequired(Exception):
    """`TTTC8715R` 은 실전 전용이다 — 모의(vts) 환경에서 호출하면 올린다."""


@dataclass
class PeriodTradeProfit:
    rows: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    pages: int = 0
    truncated: bool = False


def _as_summary(output2) -> dict:
    if isinstance(output2, dict):
        return output2
    if isinstance(output2, list) and output2 and isinstance(output2[0], dict):
        return output2[0]
    return {}


async def fetch_period_trade_profit(
    start_yyyymmdd: str, end_yyyymmdd: str, *, pdno: str = ""
) -> PeriodTradeProfit:
    """기간(`YYYYMMDD` 양끝 포함)의 일자·종목별 매매손익·수수료·제세금을 전부 읽는다.

    KIS 거부(`rt_cd != "0"`)는 `KisApiError` 로 그대로 올라온다 — 어느 쪽에서 나든 부분
    결과를 돌려주지 않는다(대사 값이 일부만 저장되면 합계 대조가 무의미해진다).
    """
    if not settings.is_production:
        raise RealEnvRequired("TTTC8715R 은 실전 전용이다(KIS_ENV=real 에서만 조회)")

    out = PeriodTradeProfit()
    nk = fk = ""
    tr_cont = ""
    while out.pages < _MAX_PAGES:
        params = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product,
            "SORT_DVSN": "01",  # 과거 순
            "PDNO": pdno,
            "INQR_STRT_DT": start_yyyymmdd,
            "INQR_END_DT": end_yyyymmdd,
            "CTX_AREA_NK100": nk,
            "CBLC_DVSN": "00",
            "CTX_AREA_FK100": fk,
        }
        data = await kis_get(
            PERIOD_TRADE_PROFIT_URL, PERIOD_TRADE_PROFIT_TR_ID, params, tr_cont=tr_cont
        )
        out.pages += 1
        out.rows.extend(r for r in (data.get("output1") or []) if isinstance(r, dict))
        summary = _as_summary(data.get("output2"))
        if summary or not out.summary:
            out.summary = summary

        flag = (data.get("_response_headers") or {}).get("tr_cont", "")
        if flag not in _NEXT_PAGE_FLAGS:
            return out
        nk = str(data.get("ctx_area_nk100") or "")
        fk = str(data.get("ctx_area_fk100") or "")
        tr_cont = "N"

    out.truncated = True
    return out
