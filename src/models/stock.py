"""종목 마스터(기본정보) 데이터 모델 — KIS CTPF1002R 응답 파생.

NXT 거래가능 여부 사전 판별 (Phase G, 2026-05-11):
- `cptt_trad_tr_psbl_yn` (NXT 거래종목여부 Y/N)
- `nxt_tr_stop_yn`       (NXT 거래정지여부 Y/N)
- 파생값 `nxt_tradable = (cptt_trad_tr_psbl_yn == "Y") AND (nxt_tr_stop_yn == "N")`

KIS API 4질의 결과(KIS MCP 2026-05-11) `CTPF1002R` 이 이 정보를 제공하는
유일한 단건 조회 TR 임이 확정되었다. 마스터 일괄 다운로드 API 는 미제공
→ 종목별 단건 조회 + Supabase 캐시(24h TTL) 로 운영한다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StockBasics(BaseModel):
    """KIS CTPF1002R 응답에서 매매 안전성 판단에 필요한 6개 필드만 추려낸 모델."""

    ticker: str = Field(..., description="종목코드 (pdno)")
    name: str = Field("", description="종목약명 (prdt_abrv_name)")
    excg_dvsn_cd: str = Field("", description="거래소구분코드 — 02: KOSPI, 03: KOSDAQ 등")
    nxt_tradable: bool = Field(
        ...,
        description="NXT 거래 가능 여부 — (cptt_trad_tr_psbl_yn=='Y') AND (nxt_tr_stop_yn=='N')",
    )
    krx_halted: bool = Field(False, description="KRX 거래정지 여부 (tr_stop_yn=='Y')")
    admin_item: bool = Field(False, description="관리종목 여부 (admn_item_yn=='Y')")
    raw: dict[str, Any] = Field(default_factory=dict, description="CTPF1002R 원본 output (디버깅용)")
