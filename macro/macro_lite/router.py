"""매크로 API 라우터 (macro_lite 추출본).

원본: 이 프로젝트 `routers/macro.py` 중 5개 GET. 응답 shape 는 원본과 100% 동일.

인증 주입 지점 — `AUTH_DEPENDENCY` 한 곳:
    from app.auth import get_current_user      # 통합 대상 프로젝트의 인증 의존성
    AUTH_DEPENDENCY = get_current_user
None 이면 인증 없이 동작한다. 값이 있으면 라우터 전체(5개 엔드포인트)에 Depends 로 적용된다.

HTTPException 은 직접 raise 하지 않는다 — 부분 실패는 각 응답의 `errors` 배열로 반환.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from . import service

AUTH_DEPENDENCY = None  # 통합 시 교체: AUTH_DEPENDENCY = get_current_user

_deps = [Depends(AUTH_DEPENDENCY)] if AUTH_DEPENDENCY else []

router = APIRouter(prefix="/api/macro", tags=["macro"], dependencies=_deps)


@router.get("/yield-curve")
def get_yield_curve():
    """미국 국채 수익률곡선 (현재값 + 시계열 + 역전 여부)."""
    return service.get_yield_curve()


@router.get("/credit-spread")
def get_credit_spread():
    """FRED HY OAS + IG OAS 기반 하이일드 신용스프레드 (하워드 막스 시계추)."""
    return service.get_credit_spread()


@router.get("/currencies")
def get_currencies():
    """주요 환율 현재가 + 스파크라인."""
    return service.get_currencies()


@router.get("/commodities")
def get_commodities():
    """주요 원자재 현재가 + 스파크라인."""
    return service.get_commodities()


@router.get("/macro-cycle")
def get_macro_cycle():
    """경기 사이클 국면 판단 (5지표 가중합산 → 4국면) + 투자 체제."""
    return service.get_macro_cycle()
