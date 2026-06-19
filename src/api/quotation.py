"""KIS 시세 조회 API — universe 가드 / 시세 진단 보조 함수.

사이클 32 (R4, 2026-05-21) — universe stale 가드 + KIS 최근체결시각 기록 신설 모듈.

배경:
- 사이클 28~29 누적 효과로 메인 편중 73% → 30% 해소됐으나 stale 종목 자체는 분산만 됨.
- 거래량 빈약한 중소형주가 영구 stale 로 41 슬롯 점유 + R1 force_retry 매 5분 KIS Rate Limit 부담.
- universe 제외 판단을 위해 KIS 당일 최근체결시각 + 누적 거래량 조회 필요.

본 모듈:
- `inquire_ccnl(ticker, market="J") -> dict | None`: 주식현재가 체결 (FHKST01010300)
  - 응답 output 배열 (최근순) 의 첫 row + today_volume 합산 dict 반환
  - 빈 응답 / KIS 오류 / 예외 → None (graceful, 호출자 보호)

참고: `src/api/condition.py` 는 스캐닝/조건검색 위주. 본 모듈은 운영 진단/가드 위주.
KIS 호출 패턴 (Rate Limit / 재시도 / 메트릭 / 보조 풀) 은 `base.py::kis_get_quote` 동일.
"""
from __future__ import annotations

import logging
import re

from src.api.base import kis_get_quote

logger = logging.getLogger(__name__)


# 사이클 32 (R4) — FHKST01010300 주식현재가 체결 (모의/실전 동일 TR_ID, FH 접두사)
_INQUIRE_CCNL_URL = "/uapi/domestic-stock/v1/quotations/inquire-ccnl"
_INQUIRE_CCNL_TR_ID = "FHKST01010300"

# 6자리 영숫자 ticker (KRX 단축코드)
_TICKER_PATTERN = re.compile(r"^[A-Za-z0-9]{6}$")


async def inquire_ccnl(ticker: str, market: str = "J") -> dict | None:
    """KIS 주식현재가 체결 조회 (FHKST01010300) — 당일 체결 내역 (최근순).

    TR_ID: FHKST01010300 (실전/모의 동일, FH 접두사).
    경로: `kis_get_quote` 시세성 풀 라우팅 (보조 라운드로빈 + 메인 fallback).
    응답 output 배열: [0] = 가장 최근 체결 (체결시간/체결단가/체결량/상대강도).
    today_volume = output 배열 cntg_vol 합산 (당일 누적 체결량).

    universe 가드 (사이클 32, R4): stale 종목이 실제로 KIS 측 거래가 빈약한지 확인 후
    universe 에서 자동 제외. 보유/익일청산은 호출자가 사전 차단 보장.

    Args:
        ticker: 6자리 영숫자 ticker (KRX 단축코드).
        market: 시장 코드. "J"(KRX, 기본) / "NX"(NXT) / "UN"(통합).

    Returns:
        - dict: 정상 응답 + output 비어있지 않음
          ```
          {
              "last_cntg_hour": "HHMMSS",
              "last_price": int,
              "last_volume": int,
              "last_relative_strength": float,
              "today_volume": int,    # output 배열 cntg_vol 합산
              "raw_count": int,       # output 배열 길이
          }
          ```
        - None: 빈 응답 (오프장 / 거래 없음) / KIS rt_cd 오류 / 예외 (graceful)

    Raises:
        ValueError: ticker 형식 오류 (6자리 영숫자 아님).
    """
    # 사전 가드 — ticker 형식 검증 (KIS 호출 전 차단)
    if not ticker or not _TICKER_PATTERN.match(ticker):
        raise ValueError(
            f"ticker 는 6자리 영숫자여야 합니다. 실제={ticker!r}"
        )

    params = {
        "fid_cond_mrkt_div_code": market,
        "fid_input_iscd": ticker,
    }

    try:
        data = await kis_get_quote(_INQUIRE_CCNL_URL, _INQUIRE_CCNL_TR_ID, params)
    except Exception as exc:
        # graceful — 외부 호출 실패 시 None 반환 (호출자가 제외 보류 판단)
        logger.debug(
            "[inquire_ccnl] KIS 호출 실패 ticker=%s err=%s",
            ticker, type(exc).__name__,
        )
        return None

    if data is None:
        return None

    # rt_cd 오류 응답은 kis_get_quote 가 KisApiError raise 또는 빈 dict 반환 가능
    # 방어 가드 — 어느 분기든 output 누락 / 빈 배열 → None
    output = data.get("output") or []
    if not output:
        return None

    # 첫 row (가장 최근 체결)
    first = output[0]

    # 합산 today_volume — output 배열 모든 row 의 cntg_vol
    today_volume = 0
    for row in output:
        try:
            today_volume += int(row.get("cntg_vol", "0") or "0")
        except (ValueError, TypeError):
            # 개별 row 파싱 실패 흡수 — 합산만 영향
            continue

    try:
        return {
            "last_cntg_hour": str(first.get("stck_cntg_hour", "")),
            "last_price": int(first.get("stck_prpr", "0") or "0"),
            "last_volume": int(first.get("cntg_vol", "0") or "0"),
            "last_relative_strength": float(first.get("tday_rltv", "0") or "0"),
            "today_volume": today_volume,
            "raw_count": len(output),
        }
    except (ValueError, TypeError) as exc:
        logger.debug(
            "[inquire_ccnl] 첫 row 파싱 실패 ticker=%s err=%s",
            ticker, exc,
        )
        return None
