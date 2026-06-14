"""사이클 129 — KIS 종목 마스터 파일 다운로드 Red 회귀 가드.

배경:
- 사용자 결정 Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼
- KIS 정본 URL (kis-mcp-query 검증):
  - KOSPI: https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip
  - KOSDAQ: https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip
- 인코딩 = cp949 (KIS 정본)
- SSL 영역 = 옵션 C (httpx + verify=True 우선 + 실패 시 verify=False 폴백)
- domain-consult 5 의제 + SSL 옵션 C 전수 채택 (cycle129_domain_consult.md)

회귀 가드 5 케이스 (모두 Red 단계 = 처음에 fail):
- G-DL1: KOSPI URL 정본 확정
- G-DL2: KOSDAQ URL 정본 확정
- G-DL3: cp949 인코딩 영역 정합
- G-DL4: SSL 검증 우선 (verify=True) 성공 경로
- G-DL5: SSL 검증 실패 → SSL 우회 폴백 (verify=False) + WARNING 로그
"""
from __future__ import annotations

import pytest


def test_g_dl1_kospi_url_constant():
    """G-DL1: KOSPI URL 정본 상수 영구 영속 (kis-mcp-query 검증).

    KIS 공식 저장소 (koreainvestment/open-trading-api) stocks_info/kis_kospi_code_mst.py
    정본 URL = https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip
    """
    from src.api import kis_master

    assert hasattr(kis_master, "KOSPI_MASTER_URL"), (
        "G-DL1: src.api.kis_master.KOSPI_MASTER_URL 상수 부재"
    )
    assert kis_master.KOSPI_MASTER_URL == (
        "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip"
    ), "G-DL1: KOSPI URL 정본 불일치"


def test_g_dl2_kosdaq_url_constant():
    """G-DL2: KOSDAQ URL 정본 상수 영구 영속 (kis-mcp-query 검증).

    KIS 공식 저장소 stocks_info/kis_kosdaq_code_mst.py 정본 URL =
    https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip
    """
    from src.api import kis_master

    assert hasattr(kis_master, "KOSDAQ_MASTER_URL"), (
        "G-DL2: src.api.kis_master.KOSDAQ_MASTER_URL 상수 부재"
    )
    assert kis_master.KOSDAQ_MASTER_URL == (
        "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip"
    ), "G-DL2: KOSDAQ URL 정본 불일치"


def test_g_dl3_cp949_encoding_constant():
    """G-DL3: cp949 인코딩 영역 정합 (KIS 정본).

    마스터 파일은 cp949 인코딩 — utf-8 디코드 시 silent 결함 (한글 깨짐).
    """
    from src.api import kis_master

    assert hasattr(kis_master, "MASTER_FILE_ENCODING"), (
        "G-DL3: MASTER_FILE_ENCODING 상수 부재"
    )
    assert kis_master.MASTER_FILE_ENCODING == "cp949", (
        "G-DL3: 인코딩 cp949 불일치 — KIS 정본 (한글 cp949 의무)"
    )


@pytest.mark.asyncio
async def test_g_dl4_ssl_verify_true_primary(monkeypatch):
    """G-DL4: SSL 검증 우선 (verify=True) 성공 경로.

    domain-consult 자문 옵션 C 채택 — httpx.AsyncClient(verify=True) 우선.
    KIS 공식 저장소 샘플의 `ssl._create_unverified_context` 패턴은 폴백 영역.
    """
    from src.api import kis_master

    # 성공 경로 시뮬레이션 = verify=True 호출 시 빈 ZIP bytes 반환
    captured_verify_values: list[bool] = []

    class _StubClient:
        def __init__(self, *, verify: bool = True, **_kwargs):
            captured_verify_values.append(verify)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def get(self, _url: str):
            class _Resp:
                status_code = 200
                content = b""

                def raise_for_status(self):
                    return None
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", _StubClient)

    # 다운로드 호출 (성공 경로) — verify=True 가 첫 시도여야 함
    await kis_master.download_master_zip(kis_master.KOSPI_MASTER_URL)

    assert len(captured_verify_values) >= 1, (
        "G-DL4: httpx.AsyncClient 호출 0건 — 다운로드 영역 미구현"
    )
    assert captured_verify_values[0] is True, (
        "G-DL4: verify=True 우선 호출 영역 위반 — domain-consult 옵션 C 위반"
    )


@pytest.mark.asyncio
async def test_g_dl5_ssl_fallback_unverified(monkeypatch, caplog):
    """G-DL5: SSL 검증 실패 → verify=False 폴백 + WARNING 로그.

    domain-consult 자문 옵션 C 옵션 영역 — SSL 검증 실패 시 폴백 1회.
    KIS 공식 샘플 답습 (ssl._create_unverified_context 패턴).
    """
    import httpx as _httpx

    from src.api import kis_master

    captured_verify_values: list[bool] = []
    call_count = {"n": 0}

    class _StubClient:
        def __init__(self, *, verify: bool = True, **_kwargs):
            captured_verify_values.append(verify)
            self._verify = verify

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def get(self, _url: str):
            call_count["n"] += 1
            if self._verify:
                # 첫 호출 verify=True → SSL 에러 시뮬레이션
                raise _httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED")

            class _Resp:
                status_code = 200
                content = b""

                def raise_for_status(self):
                    return None

            return _Resp()

    monkeypatch.setattr(_httpx, "AsyncClient", _StubClient)
    caplog.set_level("WARNING", logger="src.api.kis_master")

    await kis_master.download_master_zip(kis_master.KOSPI_MASTER_URL)

    assert captured_verify_values == [True, False], (
        "G-DL5: 폴백 영역 = [True, False] 호출 순서 위반"
    )
    # WARNING 로그 출력 영구 영속 (운영 보안 가시화 의무)
    warning_msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("SSL" in m or "verify" in m or "폴백" in m for m in warning_msgs), (
        "G-DL5: SSL 폴백 WARNING 로그 부재 — 운영 보안 가시화 의무 위반"
    )
