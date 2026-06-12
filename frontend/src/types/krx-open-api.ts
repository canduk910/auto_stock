/**
 * 사이클 112 (2026-06-12): KRX 정식 OPEN API 키 관리 타입.
 *
 * 백엔드 `src/models/krx_open_api.py::KrxOpenApiStatus / KrxOpenApiUpdateRequest` 1:1 매핑.
 *
 * 보안: `key` 평문 필드 부재 — `key_masked` 단독 노출 (`****1234`).
 */

export interface KrxOpenApiStatus {
  enabled: boolean
  base_url: string
  key_masked: string
}

export interface KrxOpenApiUpdateRequest {
  // 모든 필드 optional — 명시된 필드만 갱신. 빈 문자열 차단 (Pydantic field_validator)
  key?: string
  base_url?: string
  enabled?: boolean
}
