"""KRX 정식 OPEN API (openapi.krx.co.kr) 클라이언트.

사이클 112 (2026-06-12) — 인프라 사전 구성 (POST/JSON body/AUTH_KEY header 가정).
사이클 115 (2026-06-12) — 외부 검증 결과 추상 정정 + 4 endpoint 함수 추가.

사이클 115 정본 영구 확정 (외부 검증 2건 독립 일치):
- 출처 1: seobaeksol/krx-rs/docs/krx-api-reference/KRX_API_Spec.md
- 출처 2: raccoonyy/pykrx-openapi/src/pykrx_openapi/client.py (정본 코드 인용)
  `response = self.session.get(url, params=params, timeout=self.timeout)`
  `params = {"AUTH_KEY": self.api_key, "basDd": bas_dd}`
- HTTP method = **GET** (사이클 112 POST 가정 결함 시정)
- 인증 위치 = **query parameter `AUTH_KEY=`** (사이클 112 header 가정 결함 시정)
- 파라미터 위치 = **query string** (사이클 112 JSON body 가정 결함 시정)
- base URL = `https://data-dbg.krx.co.kr/svc/apis/{category}` (사이클 112 영속)
- 응답 = `{"OutBlock_1": [...]}` JSON 배열 (사이클 112 영속)
- Rate Limit = 키당 일일 10,000 호출 (4 호출/일 = 0.04% 영역)

자금 안전 절대 원칙:
- 본 모듈은 KIS OpenAPI 와 완전 분리 (별개 시스템). KIS `kis_request` / `kis_get_quote` 0건.
- API key 평문은 응답/로그/커밋 절대 노출 금지 — endpoint_path 만 로그.
- AUTH_KEY query parameter URL 도 로그 시 endpoint_path 만 사용 (URL 전체 로그 금지).

graceful 정책 (사이클 88 G-REJECT 영속):
- enabled=False 또는 key 부재 → `KrxApiError` raise.
- 401 (서비스 승인 대기) / 4xx / 5xx → `KrxApiError` raise.
- httpx 네트워크/timeout 예외 → `KrxApiError` 변환 raise.
- 호출자 (사이클 115 `_full_universe_load_once`) Q3=C KIS 폴백 의무.

사이클 111 stash 영구 보존 영역 (data.krx.co.kr 비공식 endpoint, 폐기됨) 과 완전 무관.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class KrxApiError(Exception):
    """KRX OPEN API 호출 실패. 호출자는 graceful 폴백 의무 (사이클 88 G-REJECT 영속)."""


# 호출 timeout (KIS 와 동일 수준 — 일자별 집계 API 라 더 길어도 무방)
_DEFAULT_TIMEOUT_SECS = 30.0


# 사이클 115 (2026-06-12) — 4 endpoint 경로 상수 (AST 영구 가드 영역)
# 출처: raccoonyy/pykrx-openapi constants.py + seobaeksol/krx-rs KRX_API_Spec.md
_ENDPOINT_STK_BYDD_TRD = "/sto/stk_bydd_trd"
_ENDPOINT_KSQ_BYDD_TRD = "/sto/ksq_bydd_trd"
_ENDPOINT_STK_ISU_BASE_INFO = "/sto/stk_isu_base_info"
_ENDPOINT_KSQ_ISU_BASE_INFO = "/sto/ksq_isu_base_info"

# 응답 영역 키 (AST 영구 가드 영역)
_OUTBLOCK_KEY = "OutBlock_1"


async def fetch_krx_open_api(
    endpoint_path: str,
    params: Optional[dict[str, Any]] = None,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SECS,
) -> dict[str, Any]:
    """KRX 정식 OPEN API 호출 (GET + AUTH_KEY query parameter).

    사이클 115 (2026-06-12) — 사이클 112 추상 결함 3건 시정:
    - POST → GET
    - JSON body → query string (`params=`)
    - AUTH_KEY header → AUTH_KEY query parameter

    출처: raccoonyy/pykrx-openapi 정본 코드
    `response = self.session.get(url, params=params, timeout=self.timeout)`
    `params = {"AUTH_KEY": self.api_key, "basDd": bas_dd}`

    Args:
        endpoint_path: base URL 이후 경로 (예: `/sto/stk_bydd_trd`). 슬래시 자동 정규화.
        params: query string 에 직렬화될 dict (예: `{"basDd": "20260612"}`).
                AUTH_KEY 는 본 함수가 자동 추가 (호출자 명시 불필요).
        timeout: httpx timeout (초). 기본 30s.

    Returns:
        KRX 응답 dict (`OutBlock_1` 배열 포함 — 호출자가 파싱).

    Raises:
        KrxApiError:
            - enabled=False 또는 key 부재 (활성화 안 됨)
            - 401 (서비스 승인 대기) / 4xx / 5xx
            - httpx 네트워크/timeout 예외
            - JSON decode 실패 / 응답 형식 부적합

    보안: 평문 key 는 query parameter 에만 사용. URL 전체 로그 금지 (endpoint_path 만 로그).
    """
    # 순환 import 회피 — 함수 내부 import
    from src.db.system_config import get_krx_open_api_config

    config = await get_krx_open_api_config()

    if not config.enabled:
        raise KrxApiError("KRX OPEN API 비활성 (설정 페이지에서 활성화 필요)")
    if not config.key:
        raise KrxApiError("KRX OPEN API key 부재 (설정 페이지에서 등록 필요)")

    # URL 정규화
    base = config.base_url.rstrip("/")
    path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
    url = f"{base}{path}"

    # AUTH_KEY + 호출자 params 병합 (사이클 115 정본 — pykrx-openapi client.py 패턴)
    merged_params = {"AUTH_KEY": config.key}
    if params:
        merged_params.update(params)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=merged_params)
    except httpx.TimeoutException as e:
        # 평문 key 노출 차단 — endpoint_path 만 로그 (URL 전체 금지)
        logger.warning("[krx_open_api] timeout endpoint=%s", endpoint_path)
        raise KrxApiError(f"KRX OPEN API timeout: {endpoint_path}") from e
    except httpx.HTTPError as e:
        logger.warning("[krx_open_api] http error endpoint=%s err=%s", endpoint_path, type(e).__name__)
        raise KrxApiError(f"KRX OPEN API http error: {endpoint_path}") from e

    if response.status_code == 401:
        # 서비스별 승인 대기 (Phase 1 진단 — Rate Limit 미초과여도 승인대기 시 401)
        logger.warning("[krx_open_api] 401 unauthorized endpoint=%s (서비스 승인 대기 또는 키 무효)", endpoint_path)
        raise KrxApiError(
            f"KRX OPEN API 401 (서비스 승인 대기 또는 키 무효): {endpoint_path}"
        )
    if response.status_code >= 400:
        logger.warning(
            "[krx_open_api] http %s endpoint=%s",
            response.status_code,
            endpoint_path,
        )
        raise KrxApiError(
            f"KRX OPEN API http {response.status_code}: {endpoint_path}"
        )

    try:
        data = response.json()
    except ValueError as e:
        logger.warning("[krx_open_api] json decode 실패 endpoint=%s", endpoint_path)
        raise KrxApiError(f"KRX OPEN API json decode 실패: {endpoint_path}") from e

    if not isinstance(data, dict):
        raise KrxApiError(
            f"KRX OPEN API 응답 형식 부적합 (dict 아님): {endpoint_path}"
        )
    return data


# ==============================================================================
# 사이클 115 (2026-06-12) — 4 endpoint 함수 신규
# ==============================================================================
#
# 사용자 결정 (확정): Q1=양쪽 통합 (bydd_trd + isu_base_info), Q3=C 폴백 영속.
# 호출자: src/engine/scanner.py::_full_universe_load_once (Q3=C KRX 1차 + KIS 폴백)
# 응답 schema 정본: seobaeksol/krx-rs KRX_API_Spec.md
#
# bydd_trd 15 필드: BAS_DD, ISU_CD(6자리), ISU_NM, MKT_NM, SECT_TP_NM,
#   TDD_CLSPRC, CMPPREVDD_PRC, FLUC_RT, TDD_OPNPRC, TDD_HGPRC, TDD_LWPRC,
#   ACC_TRDVOL, ACC_TRDVAL(원 단위, 사이클 108 min_trade_amount 직접 정합),
#   MKTCAP(원 단위, 사이클 108 min_market_cap 직접 정합), LIST_SHRS
# isu_base_info 12 필드: ISU_CD(12자리 표준), ISU_SRT_CD(6자리 단축, KRX 종목코드 정합),
#   ISU_NM, ISU_ABBRV, ISU_ENG_NM, LIST_DD, MKT_TP_NM, SECUGRP_NM,
#   SECT_TP_NM, KIND_STKCERT_TP_NM, PARVAL, LIST_SHRS


async def fetch_stk_bydd_trd(date: str) -> list[dict]:
    """KOSPI 일별 매매정보 (사이클 109 KIS market-cap 영역 KRX 대안).

    Args:
        date: 기준일자 YYYYMMDD (예: "20260612").

    Returns:
        OutBlock_1 배열 (15 필드 dict 리스트). 응답 누락 시 빈 리스트.

    Raises:
        KrxApiError: enabled=False / 401 / 4xx / 5xx / 네트워크 예외 / JSON decode 실패.
                     호출자는 Q3=C KIS 폴백 의무 (사이클 88 G-REJECT 영속).
    """
    data = await fetch_krx_open_api(_ENDPOINT_STK_BYDD_TRD, {"basDd": date})
    return data.get(_OUTBLOCK_KEY, [])


async def fetch_ksq_bydd_trd(date: str) -> list[dict]:
    """KOSDAQ 일별 매매정보.

    Args:
        date: 기준일자 YYYYMMDD.

    Returns:
        OutBlock_1 배열 (15 필드 dict 리스트). 응답 누락 시 빈 리스트.

    Raises:
        KrxApiError: graceful 폴백 의무.
    """
    data = await fetch_krx_open_api(_ENDPOINT_KSQ_BYDD_TRD, {"basDd": date})
    return data.get(_OUTBLOCK_KEY, [])


async def fetch_stk_isu_base_info(date: str) -> list[dict]:
    """KOSPI 종목 기본정보 (CTPF1002R 영역 KRX 대안).

    ticker 정합 주의: `ISU_SRT_CD` (단축코드 6자리) = KRX 종목코드 표준.
    `ISU_CD` (표준코드 12자리) 는 사용 금지 (stock_master PK 영역 비정합).

    Args:
        date: 기준일자 YYYYMMDD.

    Returns:
        OutBlock_1 배열 (12 필드 dict 리스트). 응답 누락 시 빈 리스트.

    Raises:
        KrxApiError: graceful 폴백 의무.
    """
    data = await fetch_krx_open_api(_ENDPOINT_STK_ISU_BASE_INFO, {"basDd": date})
    return data.get(_OUTBLOCK_KEY, [])


async def fetch_ksq_isu_base_info(date: str) -> list[dict]:
    """KOSDAQ 종목 기본정보.

    Args:
        date: 기준일자 YYYYMMDD.

    Returns:
        OutBlock_1 배열 (12 필드 dict 리스트). 응답 누락 시 빈 리스트.

    Raises:
        KrxApiError: graceful 폴백 의무.
    """
    data = await fetch_krx_open_api(_ENDPOINT_KSQ_ISU_BASE_INFO, {"basDd": date})
    return data.get(_OUTBLOCK_KEY, [])
