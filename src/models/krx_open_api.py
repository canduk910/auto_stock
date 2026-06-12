"""사이클 112 (2026-06-12): KRX 정식 OPEN API 키 관리 모델.

`system_config` 의 3 키 (`krx_open_api_key` + `krx_open_api_base_url` + `krx_open_api_enabled`)
관리 + 라우트 응답/요청 모델.

자금 안전 원칙:
- API key 평문은 응답에 절대 노출 금지 — `mask_secret()` 헬퍼로 항상 마스킹 변환 후 반환.
- 평문 키는 Supabase 저장 + 내부 호출 (`fetch_krx_open_api`) 전용.
- 사이클 7-A `kis_quote_accounts` 마스킹 패턴 답습.

본 사이클 (112) = 인프라 사전 구성만. 호출 사이트는 사이클 113+ 별도 사이클에서 추가.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


DEFAULT_BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"


def mask_secret(secret: str) -> str:
    """KRX OPEN API 키 마스킹 — 마지막 4자리만 노출.

    예: "secret_key_1234" → "****1234"
    8자리 미만이거나 빈 문자열이면 전체 ``****`` 로 마스킹 (길이 정보 누출 방지).
    사이클 7-A `kis_quote_account.mask_secret` 패턴 답습.
    """
    if not secret:
        return "****"
    if len(secret) < 8:
        return "****"
    return f"****{secret[-4:]}"


class KrxOpenApiConfig(BaseModel):
    """내부 사용 — Supabase 조회 결과 (평문 key 포함).

    **API 응답/로그에 절대 노출 금지** — 본 모델은 `src/db/system_config.py` 내부
    + `src/api/krx.py::fetch_krx_open_api` 호출 영역 전용. 라우트 응답은 항상
    `KrxOpenApiStatus` (마스킹) 로 변환.
    """

    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    key: str = ""


class KrxOpenApiStatus(BaseModel):
    """`GET /api/integrations/krx-open-api` 응답.

    Fields:
        enabled: 활성 여부 (DB 저장값).
        base_url: 호출 base URL (DB 저장값 또는 디폴트).
        key_masked: API key 마스킹 ("****1234" 형식). **평문은 절대 노출 안 함**.
    """

    enabled: bool
    base_url: str
    key_masked: str


class KrxOpenApiUpdateRequest(BaseModel):
    """`PUT /api/integrations/krx-open-api` 부분 갱신 요청.

    모든 필드 optional — 명시된 필드만 갱신. 빈 body 는 변경 없이 현재 상태 응답.
    key 는 평문 입력 + DB 평문 저장 + 응답 마스킹.
    """

    key: Optional[str] = Field(default=None, min_length=1)
    base_url: Optional[str] = Field(default=None, min_length=1)
    enabled: Optional[bool] = None

    @field_validator("key", "base_url")
    @classmethod
    def _strip_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("값이 비어 있습니다.")
        return stripped
