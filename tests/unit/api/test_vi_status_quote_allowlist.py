"""VI 현황(inquire-vi-status) 시세 풀 화이트리스트 — 회귀 가드.

결함 (사이클 149 도입 시점 silent, 2026-08-04 발견):
`market_operation.inquire_vi_status_today()` 가 `kis_get_quote(VI_STATUS_URL, ...)` 를
호출하는데 해당 path 가 `_QUOTE_ALLOWED_PATHS` 에 없어 **매 호출 QuotePoolPathError**.
부팅/재시작마다 `logger.exception` 으로 ERROR + traceback 을 남기고(08-03 ERROR 15건
중 8건) VI 부팅 시드는 100% 실패했다. 코드 주석이 스스로 "사이클 109+ 화이트리스트
추가 의무" 라 적어뒀으나 이행되지 않은 채 남아 있었다.

동일 클래스 선례 2건: 사이클 109 `ranking/market-cap`, 사이클 C1 finance 5 path.

정책 부합 근거 (KIS 정본): `inquire_vi_status` = "변동성완화장치(VI) 현황",
subcategory "업종/기타" = 시세성 조회. 요청 파라미터가 `FID_*` 뿐이라 계좌·주문 등
민감 식별자 없음 → 보조 풀 라우팅 자금 안전 정책 부합.

실사용: `stale_watcher_core.py` 의 `is_ticker_stale_excluded` — VI 발동 종목을 stale
판정에서 제외한다. 시드가 죽어 있으면 VI 로 체결이 멈춘 종목이 stale 로 오인돼 강제
재구독 → KIS LMS chain 위험(사이클 17/29). 장중 재배포 시점에 실효.
"""

from __future__ import annotations

import pytest

from src.api.base import _QUOTE_ALLOWED_PATHS
from src.api.market_operation import VI_STATUS_TR_ID, VI_STATUS_URL

pytestmark = pytest.mark.unit


def test_vi_status_path_in_quote_allowlist():
    assert VI_STATUS_URL in _QUOTE_ALLOWED_PATHS, (
        "inquire-vi-status 는 시세 풀 화이트리스트 필수 — 누락 시 부팅마다 "
        "QuotePoolPathError + VI 시드 100% 실패 (사이클 109/C1 선례와 동일 결함)"
    )


def test_vi_status_tr_id_is_kis_canonical():
    """KIS 정본 TR_ID 고정 (하드코딩 드리프트 차단)."""
    assert VI_STATUS_TR_ID == "FHPST01390000"


def test_quote_allowlist_has_no_trading_paths():
    """화이트리스트 확장이 매매/잔고/체결 경로를 끌어들이지 않았는지 (자금 안전 정책).

    판정은 **path 세그먼트**로 한다 — 키워드 부분일치는 `finance/balance-sheet`
    (재무 대차대조표 = 시세성)를 `inquire-balance`(계좌 잔고)로 오탐한다.
    """
    allowed_segments = ("/quotations/", "/ranking/", "/finance/")
    for path in _QUOTE_ALLOWED_PATHS:
        assert "/trading/" not in path, f"매매성 path 혼입: {path}"
        assert any(seg in path for seg in allowed_segments), (
            f"시세성 세그먼트(quotations/ranking/finance) 밖의 path: {path}"
        )
