"""사이클 149 (2026-06-16) — 장운영정보 (H0UNMKO0) 정본 + REST 보조 폴백.

KIS 공식 H0UNMKO0 응답 10 컬럼 정본 + 종목별 구독 정합 영속.
사이클 26 (2026-05-20) 메인 단일 005930 대표 구독 영역 보존 +
사이클 149 (2026-06-16) 보유/익일청산/전략 후보 합집합 종목별 구독 확장.

domain-expert 자문 산출물:
    `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`

영속 의무:
- 의제 1: VI_CLS_CODE "0"/""/None = 비활성 블랙리스트 (truthy 매핑, KIS 향후 확장 호환)
- 의제 2: 메인 세션 단일 + bypass_limit=True (사이클 17 KIS LMS chain 안전)
- 의제 4: 부팅 REST 1회 폴백 (graceful — 결함 시 매매 안전성 영향 0)
- 의제 5: stale 회피 = VI 활성 + 거래정지 + 종목상태 이상 (MRKT_TRTM 제외)

매매 안전성 무영향 (사이클 38 명문화 영속):
- stale 판정 *지연*만 = 재구독 발화 차단 (매수 신호 평가 영향 0)
- `risk.on_tick` / `order_engine` / `auth` 변경 0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.api.base import kis_get_quote

logger = logging.getLogger(__name__)

KST_TZ = timezone(timedelta(hours=9))

# 사이클 26 영속 + 사이클 149 종목별 구독 확장
MARKET_OP_TR_ID = "H0UNMKO0"

# 사이클 149 의제 4 (자문 채택) — REST 보조 폴백 TR_ID
VI_STATUS_TR_ID = "FHPST01390000"
VI_STATUS_URL = "/uapi/domestic-stock/v1/quotations/inquire-vi-status"


@dataclass(frozen=True)
class MarketOpEvent:
    """H0UNMKO0 단일 메시지 이벤트 (사이클 149 신규, cycle368 필드 배치 재확정).

    🔴 **라이브 프레임은 첫 칸이 종목코드다(실측 2026-09-21~23, EC2 17건 전수).**
    KIS 문서(`docs/kis/domestic-stock-realtime.md` 통합 절)와 KIS MCP 공식 샘플은
    종목코드 칸이 빠진 10컬럼(`[0]=TRHT_YN`)으로 적혀 있으나, 라이브 프레임은
    KRX/NXT 단독 표(`[0]=MKSC_SHRN_ISCD`)와 같은 ticker-first 배치다. 그래서
    `parse_market_op_payload` 는 `fields[0]` 이 정확히 `"Y"`/`"N"` 일 때만 문서 모양으로
    보고, 그 밖은 전부 라이브(ticker-first) 모양으로 읽는다(§ 조사 메모
    `_workspace/domain_consult/cycle359_mkop_field_offset.md`).

    KIS 공식 응답 10 컬럼(**문서 모양 기준** — 종목코드 칸 없음, cycle368 재확정). 라이브
    프레임은 이보다 **+1 칸 밀린다**(종목코드가 맨 앞에 온다) — 실제 offset 판별은
    `parse_market_op_payload` 가 한다:
        [0] TRHT_YN — 거래정지 여부 ("Y"/"N")
        [1] TR_SUSP_REAS_CNTT — 거래 정지 사유 내용
        [2] MKOP_CLS_CODE — 장운영 구분 코드 (110/112/121/129...)
        [3] ANTC_MKOP_CLS_CODE — 예상 장운영 구분 코드
        [4] MRKT_TRTM_CLS_CODE — 임의연장구분코드 (의제 5 제외, 시장 단위 신호)
        [5] DIVI_APP_CLS_CODE — 동시호가배분처리구분코드
        [6] ISCD_STAT_CLS_CODE — 종목상태구분코드 (거래정지 판정은 `ISCD_STAT_BLOCKING` 참조)
        [7] VI_CLS_CODE — VI적용구분코드 (의제 5 stale 회피 대상)
        [8] OVTM_VI_CLS_CODE — 시간외단일가VI적용구분코드 (의제 5 stale 회피 대상)
        [9] EXCH_CLS_CODE — 거래소 구분코드 (KRX/NXT)

    위 인덱스는 이 dataclass 필드 순서와 이름이 지정하는 "논리 칸" 이다 — 실제 페이로드에서
    몇 번째 `^` 구분 칸을 읽을지는 `parse_market_op_payload` 의 offset 판별이 정한다.
    """
    ticker: str
    trht_yn: str
    tr_susp_reas_cntt: str
    mkop_cls_code: str
    antc_mkop_cls_code: str
    mrkt_trtm_cls_code: str
    divi_app_cls_code: str
    iscd_stat_cls_code: str
    vi_cls_code: str
    ovtm_vi_cls_code: str
    exch_cls_code: str
    received_at: datetime


def parse_market_op_payload(tr_key: str, payload: str) -> MarketOpEvent:
    """H0UNMKO0 `^` 구분 10 컬럼 파싱 + MarketOpEvent 반환.

    🔴 **칸 기준점 (cycle368, M-1)** — `off = 0 if fields[0] in ("Y","N") else 1`.
    `fields[0]` 이 정확히(`==`, `startswith` 아님) `"Y"` 또는 `"N"` 이면 **문서 모양**
    (종목코드 칸 없음, KIS 문서 표 그대로) — 그 밖은 전부 **라이브 모양**
    (`fields[0]` = 종목코드, 이후 칸이 한 칸씩 밀림). `tr_key == fields[0]` 으로 판별하지
    않는다 — `KisWebSocket._handle_raw` 가 `tr_key = payload.split("^")[0]` 로 뽑으므로
    운영 경로에서는 그 등식이 항상 참이라 판별력이 없다(cycle359 메모 §6 M-1).

    컬럼 정의는 `MarketOpEvent` 클래스 docstring 이 정본이다.
    누락 컬럼 = 빈 문자열 폴백 (사이클 95 unknown 영역 답습 + KIS 향후 확장 호환).
    """
    fields = payload.split("^")
    off = 0 if fields and fields[0] in ("Y", "N") else 1

    def _f(i: int) -> str:
        idx = i + off
        return fields[idx] if len(fields) > idx else ""

    # cycle368 F4 — 정지 사유 칸의 KIS null 토큰 정규화(정확일치만, N4).
    _reason = _f(1)
    if _reason == _NULL_TOKEN:
        _reason = ""

    return MarketOpEvent(
        ticker=tr_key,
        trht_yn=_f(0),
        tr_susp_reas_cntt=_reason,
        mkop_cls_code=_f(2),
        antc_mkop_cls_code=_f(3),
        mrkt_trtm_cls_code=_f(4),
        divi_app_cls_code=_f(5),
        iscd_stat_cls_code=_f(6),
        vi_cls_code=_f(7),
        ovtm_vi_cls_code=_f(8),
        exch_cls_code=_f(9),
        received_at=datetime.now(KST_TZ),
    )


# 의제 1 (자문 채택) — 비활성 블랙리스트 truthy 매핑.
# KIS API 코드값 향후 확장 호환 = enum 처리 금지. "0"/""/None = 비활성, 그 외 = 활성.
# cycle368 F4(적대적 검토 뒤 메인 세션 결정, 사용자 승인 범위 안) — KIS null 토큰 `"(null)"`
# 도 비활성으로 본다. 라이브 프레임 실측(EC2, 09-21~23)에서 미기록 칸이 빈 문자열이 아니라
# 문자열 그대로 `(null)` 로 온다 — VI/시간외VI 칸이 이 값이면 활성으로 오판해서는 안 된다.
_INACTIVE_VALUES: frozenset[str] = frozenset({"", "0", "N", "n", "(null)"})

#: cycle368 F4 — KIS null 토큰. 텍스트 칸(TR_SUSP_REAS_CNTT) 정규화는 **정확히 이 값과
#: 같을 때만** `""` 로 바꾼다 — 부분 문자열 치환이면 "매매거래정지 (null) 표기 포함" 같은
#: 실제 사유 문장이 깎인다(N4).
_NULL_TOKEN = "(null)"


def _is_code_active(code: Optional[str]) -> bool:
    """truthy 매핑 = `code not in {"", "0", "N", None}` 시 활성."""
    if code is None:
        return False
    return code not in _INACTIVE_VALUES


# 🔴 종목상태(ISCD_STAT_CLS_CODE) 거래정지 판정 — 2026-09-25 사용자 결정(cycle368).
# 값 표(51~59, 00) 중 **58(거래정지 지정 종목) 하나만** 정지로 본다. 51(관리)·
# 59(단기과열) 포함 그 외 값은 정지가 아니다 — 그 값들을 「종목상태 이상」으로
# 넓게 읽으면(구 `_is_code_active` 재사용) 55(신용가능)·57(증거금100%) 같은
# 정상 상태까지 거래정지로 오분류해 보유 종목이 재구독 안전망에서 빠진다
# (cycle359 메모 §7-1 "두 번째 덫"). 51/59 보유 종목 청산·신규매수 차단은
# 범위 밖(cycle369, `domain-consult` 선행) — 여기서는 만들지 않는다.
ISCD_STAT_BLOCKING: frozenset[str] = frozenset({"58"})


def is_iscd_stat_blocking(code: Optional[str]) -> bool:
    """종목상태구분코드가 거래정지(58)인가 — `ISCD_STAT_BLOCKING` 멤버십 단독 판정."""
    return code in ISCD_STAT_BLOCKING


def is_event_blocking(event: MarketOpEvent) -> bool:
    """의제 5 (자문 채택) — VI 활성 + 거래정지 + 종목상태 이상 3 영역 통합 판정.

    True = stale 회피 대상 (시세 미수신 정상 영역).
    MRKT_TRTM_CLS_CODE 는 시장 단위 신호 = 무관 (자문 의제 5).
    """
    # 거래정지 (TRHT_YN == "Y")
    if event.trht_yn and event.trht_yn.upper() == "Y":
        return True
    # VI 활성 (정적 + 동적 + 시간외)
    if _is_code_active(event.vi_cls_code):
        return True
    if _is_code_active(event.ovtm_vi_cls_code):
        return True
    # 종목상태 거래정지(58) 단독 — cycle368, `_is_code_active` 광범위 판정 폐기
    if is_iscd_stat_blocking(event.iscd_stat_cls_code):
        return True
    return False


async def inquire_vi_status_today() -> set[str]:
    """의제 4 (자문 채택) — 부팅 시점 REST 폴백 (FHPST01390000).

    KIS 공식 inquire_vi_status (변동성완화장치 VI 현황) 응답 영역에서
    `vi_cls_code != "0"` 활성 ticker set 반환.

    graceful 영속 (KIS 거부 / 네트워크 / 응답 형식 변경 → 빈 set):
    - 부팅 시점 = 07:50 KST = 장 시작 *전* = VI 활성 거의 없음
    - 결함 시 영향 0 = WebSocket 수신만으로 충분 (사이클 88 G-REJECT 답습)
    """
    today_yyyymmdd = datetime.now(KST_TZ).strftime("%Y%m%d")
    params = {
        "FID_DIV_CLS_CODE": "0",            # 0:전체 1:상승 2:하락
        "FID_COND_SCR_DIV_CODE": "20139",   # 화면 분류 코드 (KIS 정본 고정)
        "FID_MRKT_CLS_CODE": "0",           # 0:전체 K:거래소 Q:코스닥
        "FID_INPUT_ISCD": "",
        "FID_RANK_SORT_CLS_CODE": "0",      # 0:전체 1:정적 2:동적 3:정적&동적
        "FID_INPUT_DATE_1": today_yyyymmdd,
        "FID_TRGT_CLS_CODE": "0",
        "FID_TRGT_EXLS_CLS_CODE": "",
    }
    try:
        # 2026-08-04 — `_QUOTE_ALLOWED_PATHS` 등재 완료 (사이클 109 market-cap /
        # C1 finance 선례). 등재 전에는 매 호출 QuotePoolPathError 로 시드가 100%
        # 실패하면서 부팅마다 ERROR + traceback 만 남겼다. 화이트리스트에서 이 path 를
        # 빼면 그 silent 결함이 즉시 재발한다 (회귀 가드:
        # tests/unit/api/test_vi_status_quote_allowlist.py).
        response = await kis_get_quote(VI_STATUS_URL, VI_STATUS_TR_ID, params)
        if not response or response.get("rt_cd") != "0":
            return set()
        output = response.get("output", []) or []
        if not isinstance(output, list):
            return set()
        active_tickers: set[str] = set()
        for row in output:
            if not isinstance(row, dict):
                continue
            ticker = (row.get("mksc_shrn_iscd") or "").strip()
            vi_code = (row.get("vi_cls_code") or "").strip()
            if ticker and _is_code_active(vi_code):
                active_tickers.add(ticker)
        return active_tickers
    except Exception:
        # graceful 영속 (사이클 88 G-REJECT 답습) — 부팅 폴백 실패 = 영향 0
        logger.exception("[inquire_vi_status_today] REST 보조 폴백 실패 graceful")
        return set()
