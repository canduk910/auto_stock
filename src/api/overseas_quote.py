"""해외주식 종목/지수/환율 기간별시세 (FHKST03030100) — 나스닥100 지수 종가.

`ndx2x_riskoff` 전략(cycle443)의 유일한 신호 원천. 정본 =
`_workspace/domain_consult/2026-10-06_ndx2x_risk_off.md` §3 「신호 원천」 +
2026-10-11 메인 세션 운영 키 실측(조회 전용, 작업 지시서 cycle443 「운영 실측 사실」).

실측 사실(운영 키, 실전):
- `FID_INPUT_ISCD="NDX"` (나스닥100, `output1.hts_kor_isnm`="나스닥 100"). `.NDX`·
  `NAS@NDX`·`IXIC` 는 `rt_cd=0` 인데 0행이 온다 — 그래서 **0행은 오류로 다룬다**
  (정상 응답(`rt_cd=="0"`)이어도).
- `output2` 는 **최신순**(날짜 내림차순). 종가=`ovrs_nmix_prpr`, 날짜=`stck_bsop_date`
  (YYYYMMDD). `mod_yn` 필드 존재(과거 값 변경 여부) — 이 래퍼는 소비하지 않는다.
- 한 호출 **최대 100행**(`tr_cont` 로 다음 쪽 조회 불가 — KIS 문서 "tr_cont를 이용한
  다음조회 불가 API"). 더 과거를 받으려면 `FID_INPUT_DATE_2`(종료일) 커서를 과거로
  당겨 **겹치게** 여러 번 호출한다(요청 시작일 근처 며칠이 빠지는 실측 quirk를
  겹침으로 상쇄 — `src.engine.ndx2x_core.merge_batches` 가 병합을 맡는다, 이 모듈은
  I/O 래퍼일 뿐이다).
- **당일 조회는 지연 또는 종가시세**(KIS 공식 문구) — 호출자가 미국 종가 확정 이후
  (KST 07:00 이후, 서머타임 전환 양쪽 덮는다)에만 불러야 한다. 이 모듈은 시각을
  판단하지 않는다(호출자 책임, `ndx2x_ingest.py`).
"""

from __future__ import annotations

from datetime import date

from src.api.base import kis_get_quote

#: KIS FHKST03030100 경로.
PATH = "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"
#: 실전·모의 동일(KIS 문서 — "[실전투자/모의투자] FHKST03030100").
TR_ID = "FHKST03030100"
#: 나스닥100 지수 코드(실측) — `.NDX`·`NAS@NDX`·`IXIC` 는 0행으로 떨어진다.
NDX_ISCD = "NDX"
#: 한 호출 KIS 응답 행 상한(실측) — 이 상수 자체가 행위를 바꾸지 않는다(참고용 문서화).
MAX_ROWS_PER_CALL = 100


class OverseasIndexEmptyResponseError(RuntimeError):
    """`output2` 가 0행 — `rt_cd=="0"`(정상 응답)이어도 오류로 취급한다.

    실측상 잘못된 종목코드(`.NDX`·`NAS@NDX`·`IXIC`)의 특징 — 재시도가 아니라
    `FID_INPUT_ISCD` 값을 재확인한다.
    """


async def fetch_daily_chartprice(
    start: date, end: date, *, iscd: str = NDX_ISCD,
) -> list[dict]:
    """KIS 호출 1회 — `output2`(최신순 원본 dict list, 최대 100행)를 그대로 돌린다.

    파싱·검증(날짜·종가 형식, 최신순 여부)은 순수 함수
    `src.engine.ndx2x_core.parse_kis_rows`/`assert_latest_first` 가 맡는다 — 이
    함수는 I/O 래퍼일 뿐 파싱하지 않는다(leaf·wrapper 책임 분리).
    """
    resp = await kis_get_quote(
        PATH, TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "N",  # N = 해외지수
            "FID_INPUT_ISCD": iscd,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",  # D = 일
        },
    )
    rows = resp.get("output2") or []
    if not rows:
        raise OverseasIndexEmptyResponseError(
            f"FHKST03030100 output2 0행 (iscd={iscd!r}, {start.isoformat()}~{end.isoformat()})"
            " — rt_cd 정상이어도 오류로 취급한다. FID_INPUT_ISCD 를 재확인하라."
        )
    return rows
