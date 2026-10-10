"""예탁원정보(액면교체·자본감소·합병분할) + 계좌 기간별 권리현황(CTRGA011R) — cycle431.

액면병합·분할 등 "주문 밖 수량 변경"을 KIS 잔고 대사로 장부에 반영하기 위한
근거 조회 모듈이다(사용자 결정 2026-10-10, 안1). 소비처 = `src/engine/boot_manager.py`
(07:45 부팅 반영) · `src/engine/scheduler.py`(21:30 CTRGA011R 사후 대사, 감지만).

판정 자체(비율 계산·분류)는 이 파일에 없다 — 순수 leaf
`src/engine/corporate_action_reconcile.py` 가 맡는다. 여기는 KIS REST 호출만.

TR 4종:
- `HHKDB669105C0` 예탁원정보(액면교체일정) — `/uapi/domestic-stock/v1/ksdinfo/rev-split`
- `HHKDB669106C0` 예탁원정보(자본감소일정) — `/uapi/domestic-stock/v1/ksdinfo/cap-dcrs`
- `HHKDB669104C0` 예탁원정보(합병_분할일정) — `/uapi/domestic-stock/v1/ksdinfo/merger-split`
- `CTRGA011R` 기간별계좌권리현황조회 — `/uapi/domestic-stock/v1/trading/period-rights`
  (실전 전용 — 모의투자 미지원, `docs/kis/domestic-stock-order.md`)

연속조회 — 예탁원 3종은 `docs/kis/domestic-stock-info.md` 가 "tr_cont 를 이용한
다음조회 불가 API" 라고 적어 두었지만, 사용자 결정(2026-10-10)은 KIS 공식 예제를
따라 **응답 헤더 `tr_cont` 가 M 이면 `tr_cont="N"` 으로 같은 조건을 다시 부르고,
`CTS` 쿼리 파라미터는 항상 빈칸으로 둔다**(요청 본문의 CTS 로는 다음 쪽을 못
연다 — 문서 속 "불가" 는 CTS 축 얘기다). CTRGA011R 은 `CTX_AREA_FK100`/
`CTX_AREA_NK100` 되돌림(= `balance.get_daily_orders` 와 같은 모양)이다. 쪽수
상한은 두지 않는다 — 응답이 "더 있다"(M/F)고 하는데 **새 행이 0개**면 다음
요청도 같은 쪽을 받을 뿐이므로 `CorporateActionPaginationStuckError` 를 올린다
(cycle430 `DailyOrdersPaginationStuckError` 와 같은 규약).
"""
from __future__ import annotations

from datetime import date, timedelta

from src.api.base import kis_get
from src.config import settings

REV_SPLIT_URL = "/uapi/domestic-stock/v1/ksdinfo/rev-split"
REV_SPLIT_TR_ID = "HHKDB669105C0"
CAP_DCRS_URL = "/uapi/domestic-stock/v1/ksdinfo/cap-dcrs"
CAP_DCRS_TR_ID = "HHKDB669106C0"
MERGER_SPLIT_URL = "/uapi/domestic-stock/v1/ksdinfo/merger-split"
MERGER_SPLIT_TR_ID = "HHKDB669104C0"
PERIOD_RIGHTS_URL = "/uapi/domestic-stock/v1/trading/period-rights"
PERIOD_RIGHTS_TR_ID = "CTRGA011R"

#: 예탁원 조회 창 — 오늘(기준일) 이전 며칠까지 본다. 매매거래정지 기간이 길어도
#: 아우르도록 넉넉히 둔다. 운영 관찰로 조정 가능한 상수 — 사용자 결정 없음.
DEPOSITORY_LOOKBACK_DAYS = 30

#: CTRGA011R 사후 대사 창(21:30) — 당일 하루만 본다(그날 생긴 권리 행 감지).
PERIOD_RIGHTS_LOOKBACK_DAYS = 1

#: 연속조회에서 "다음 데이터 있음" 을 뜻하는 응답 헤더 `tr_cont` 값(KIS 공지).
_NEXT_PAGE_FLAGS = ("M", "F")


class CorporateActionPaginationStuckError(RuntimeError):
    """예탁원/계좌권리 연속조회가 진행하지 않는다(같은 쪽 반복)."""


def _date_window(today: date | None, lookback_days: int) -> tuple[str, str]:
    # 사이클 68 G12 — naive `date.today()` 금지(서버 timezone 의존 → KST 영업일
    # 어긋남). `today` 가 비면 `_kst.today_kst()` 로 구한다.
    if today is None:
        from src.db._kst import today_kst
        _today = today_kst()
    else:
        _today = today
    f_dt = (_today - timedelta(days=lookback_days)).strftime("%Y%m%d")
    t_dt = _today.strftime("%Y%m%d")
    return f_dt, t_dt


async def _fetch_ksd_info(
    url: str,
    tr_id: str,
    ticker: str,
    *,
    market_gb: str | None = None,
    lookback_days: int = DEPOSITORY_LOOKBACK_DAYS,
    today: date | None = None,
) -> list[dict]:
    """예탁원 정보 3종 공용 호출 — 연속조회(tr_cont M/F → N, CTS 항상 공백)."""
    f_dt, t_dt = _date_window(today, lookback_days)
    params: dict[str, str] = {"SHT_CD": ticker, "CTS": "", "F_DT": f_dt, "T_DT": t_dt}
    if market_gb is not None:
        params["MARKET_GB"] = market_gb

    rows: list[dict] = []
    tr_cont = ""
    while True:
        data = await kis_get(url, settings.get_tr_id(tr_id), params, tr_cont=tr_cont)
        page_rows = data.get("output1") or []
        before = len(rows)
        rows.extend(page_rows)

        flag = (data.get("_response_headers") or {}).get("tr_cont", "")
        if flag not in _NEXT_PAGE_FLAGS:
            return rows
        if len(rows) == before:
            raise CorporateActionPaginationStuckError(
                f"{tr_id} 연속조회가 진행하지 않는다 (tr_cont={flag!r}, rows={len(rows)})"
            )
        tr_cont = "N"


async def fetch_face_value_change(ticker: str, *, today: date | None = None) -> list[dict]:
    """예탁원정보(액면교체일정, HHKDB669105C0) — `inter_bf_face_amt`/`inter_af_face_amt`."""
    return await _fetch_ksd_info(
        REV_SPLIT_URL, REV_SPLIT_TR_ID, ticker, market_gb="0", today=today,
    )


async def fetch_capital_decrease(ticker: str, *, today: date | None = None) -> list[dict]:
    """예탁원정보(자본감소일정, HHKDB669106C0) — `reduce_cap_rate`/`comp_way`."""
    return await _fetch_ksd_info(CAP_DCRS_URL, CAP_DCRS_TR_ID, ticker, today=today)


async def fetch_merger_split(ticker: str, *, today: date | None = None) -> list[dict]:
    """예탁원정보(합병_분할일정, HHKDB669104C0) — 감지만, 자동 반영 대상이 아니다."""
    return await _fetch_ksd_info(MERGER_SPLIT_URL, MERGER_SPLIT_TR_ID, ticker, today=today)


async def fetch_period_rights(
    ticker: str = "",
    *,
    start_date: str,
    end_date: str,
    right_type_cd: str = "",
) -> list[dict]:
    """기간별계좌권리현황조회(CTRGA011R) — **실전 전용**(모의투자 미지원 → 빈 목록).

    응답 목록 키는 실제 `output` 이다(스펙 표의 `output1` 과 다르다 — 2026-10-10
    운영 탐침 실측). 연속조회는 `get_daily_orders` 와 같은 모양
    (`CTX_AREA_FK100`/`CTX_AREA_NK100` 되돌림).
    """
    if not settings.is_production:
        return []

    rows: list[dict] = []
    cur_fk = cur_nk = ""
    tr_cont = ""
    while True:
        params = {
            "INQR_DVSN": "03",
            "CUST_RNCNO25": "",
            "HMID": "",
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product,
            "INQR_STRT_DT": start_date,
            "INQR_END_DT": end_date,
            "RGHT_TYPE_CD": right_type_cd,
            "PDNO": ticker,
            "PRDT_TYPE_CD": "",
            "CTX_AREA_NK100": cur_nk,
            "CTX_AREA_FK100": cur_fk,
        }
        data = await kis_get(
            PERIOD_RIGHTS_URL, settings.get_tr_id(PERIOD_RIGHTS_TR_ID), params, tr_cont=tr_cont,
        )
        page_rows = data.get("output") or []
        before = len(rows)
        rows.extend(page_rows)

        flag = (data.get("_response_headers") or {}).get("tr_cont", "")
        if flag not in _NEXT_PAGE_FLAGS:
            return rows

        next_fk = str(data.get("ctx_area_fk100") or "")
        next_nk = str(data.get("ctx_area_nk100") or "")
        no_progress = len(rows) == before and (
            (not next_fk.strip() and not next_nk.strip())
            or (next_fk == cur_fk and next_nk == cur_nk)
        )
        if no_progress:
            raise CorporateActionPaginationStuckError(
                f"{PERIOD_RIGHTS_TR_ID} 연속조회가 진행하지 않는다 (tr_cont={flag!r}, rows={len(rows)})"
            )
        cur_fk, cur_nk = next_fk, next_nk
        tr_cont = "N"
