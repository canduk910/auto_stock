"""사이클 112 (2026-06-12): KRX 정식 OPEN API (openapi.krx.co.kr) 클라이언트 추상.

Phase 1 진단 결정적 발견:
- 인증 방식 = `AUTH_KEY` HTTP header (KIS Bearer token 영역과 별개)
- base URL = `https://data-dbg.krx.co.kr/svc/apis/{category}` (디폴트)
- 호출 방식 = POST + JSON payload (`Content-Type: application/json`)
- Rate Limit = 키당 일일 10,000 호출 (서비스별 승인 의무, 승인대기 시 401)
- 응답 = `OutBlock_1` 배열 + 필드 (`BAS_DD / ISU_CD / ISU_NM / TDD_CLSPRC` 등)

자금 안전 절대 원칙:
- 본 모듈은 *KIS OpenAPI 와 완전 분리* (별개 시스템). KIS `kis_request` / `kis_get_quote` 0건.
- API key 평문은 응답/로그/커밋 절대 노출 금지 — `KrxApiError` 메시지에도 마스킹.
- 호출 0건 보장 (본 사이클 112 = 인프라 사전 구성만, 사이클 113+ 통합 영역에서 첫 호출).

graceful 정책:
- enabled=False 또는 key 부재 → `KrxApiError("KRX OPEN API 비활성 또는 키 부재")` raise.
- httpx 네트워크/timeout 예외 → `KrxApiError` 변환 raise.
- 호출자 (사이클 113+) 는 KIS 폴백 또는 stock_master 캐시 폴백 의무 (사이클 88 G-REJECT 영속).

사이클 111 stash 영구 보존 영역 (data.krx.co.kr 비공식 endpoint, 폐기됨) 과 완전 무관 신규 추상.
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


async def fetch_krx_open_api(
    endpoint_path: str,
    params: Optional[dict[str, Any]] = None,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SECS,
) -> dict[str, Any]:
    """KRX 정식 OPEN API 호출 (POST + AUTH_KEY header + JSON body).

    Args:
        endpoint_path: base URL 이후 경로 (예: `/sto/stk_bydd_trd`). 슬래시 자동 정규화.
        params: JSON body 에 직렬화될 dict (예: `{"basDd": "20260612"}`).
        timeout: httpx timeout (초). 기본 30s.

    Returns:
        KRX 응답 dict (`OutBlock_1` 배열 포함 — 호출자가 파싱).

    Raises:
        KrxApiError:
            - enabled=False 또는 key 부재 (활성화 안 됨)
            - 401 (서비스 승인 대기) / 4xx / 5xx
            - httpx 네트워크/timeout 예외

    **보안**: 평문 key 는 header 에만 사용. 로그/예외 메시지 절대 노출 금지.
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

    headers = {
        "AUTH_KEY": config.key,  # Phase 1 진단 확정 형식 (Bearer token 아님)
        "Content-Type": "application/json",
    }
    body = params or {}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as e:
        # 평문 key 노출 차단 — endpoint_path 만 로그
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
