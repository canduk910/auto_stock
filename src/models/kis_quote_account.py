"""사이클 7-A (2026-05-17): 보조 KIS 시세 수신 계좌 모델.

`kis_quote_accounts` 테이블 row 매핑 + 응답 노출 정책.

자금 안전 원칙:
- 매매/잔고/체결통보는 메인 계좌 단일 — 본 모델은 시세 수신 한정.
- `app_secret` 평문은 응답에 절대 노출 금지. `mask_secret()` 헬퍼로 항상 마스킹 변환 후 반환.
- 후속 사이클(7-B WebSocketPool / 7-C REST 라운드로빈)에서 실제 사용. 본 사이클은 등록/조회 인프라만.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def mask_secret(secret: str) -> str:
    """app_secret 마스킹 — 마지막 4자리만 노출.

    예: "abcdef1234567890" → "****7890"
    8자리 미만이거나 빈 문자열이면 전체를 ``****`` 로 마스킹 (길이 정보 누출 방지).
    """
    if not secret:
        return "****"
    if len(secret) < 8:
        return "****"
    return f"****{secret[-4:]}"


class KisQuoteAccount(BaseModel):
    """`kis_quote_accounts` row 응답 모델.

    Fields:
        id: UUID PK.
        label: 운영자 식별 라벨 (UNIQUE).
        app_key: KIS Developers 발급 APP KEY (평문 유지 — 비밀번호 등급 아님).
        app_secret_masked: APP SECRET 마스킹 ("****1234" 형식). 평문은 절대 노출 안 함.
        kis_env: "real" / "vts".
        active: false 면 시세 풀 제외.
        created_at / updated_at: ISO 8601.
    """

    id: UUID
    label: str
    app_key: str
    app_secret_masked: str
    kis_env: Literal["real", "vts"]
    active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "KisQuoteAccount":
        """Supabase row → 응답 모델. app_secret 평문은 마스킹 변환."""
        return cls(
            id=UUID(str(row["id"])) if not isinstance(row["id"], UUID) else row["id"],
            label=row["label"],
            app_key=row["app_key"],
            app_secret_masked=mask_secret(row.get("app_secret", "")),
            kis_env=row["kis_env"],
            active=bool(row.get("active", True)),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row.get("updated_at")) if row.get("updated_at") else None,
        )


class KisQuoteAccountCreate(BaseModel):
    """POST /api/integrations/quote-accounts 요청 본문."""

    label: str = Field(..., min_length=1, max_length=64)
    app_key: str = Field(..., min_length=1)
    app_secret: str = Field(..., min_length=1)
    kis_env: Literal["real", "vts"]

    @field_validator("label", "app_key", "app_secret")
    @classmethod
    def _strip_not_empty(cls, v: str) -> str:
        stripped = (v or "").strip()
        if not stripped:
            raise ValueError("값이 비어 있습니다.")
        return stripped


class KisQuoteAccountUpdate(BaseModel):
    """PUT /api/integrations/quote-accounts/{id} 요청 본문.

    active / label 만 갱신 가능. app_key / app_secret 수정은 본 사이클에서 지원 안 함
    (삭제 후 재등록 패턴). 보안 감사 추적성 보장.
    """

    active: Optional[bool] = None
    label: Optional[str] = Field(None, min_length=1, max_length=64)

    @field_validator("label")
    @classmethod
    def _strip_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("label 이 비어 있습니다.")
        return stripped


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _parse_dt(value: Any) -> datetime:
    """ISO 8601 문자열 또는 datetime → datetime 변환. 'Z' 접미사 호환."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        iso = value.replace("Z", "+00:00")
        return datetime.fromisoformat(iso)
    raise TypeError(f"datetime 파싱 실패: {value!r}")
