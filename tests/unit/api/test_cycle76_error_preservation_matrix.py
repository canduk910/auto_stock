"""사이클 76 의제 #3 — ERROR 보존 매트릭스 영속 (사이클 29 005935 LMS chain 진단 의무).

본 파일은 *영속 영역 회귀 가드*. Red 단계 = 모든 케이스 PASS (사이클 18/29 영속).
Green 단계 = 사이클 76 옵션 E 도입 후에도 4 영역 individual ERROR 사이트 영속 보존.

영속 의무 ERROR/individual 사이트 매트릭스:
| 사이트 | 사이클 | 레벨 | prefix | aggregation 흡수 |
|--------|-------|------|--------|----------------|
| `_request` 5xx 최종 실패 | PR-B/16 | ERROR | `[api_retry_exhausted]` | individual 영속 |
| `_request` 네트워크 최종 실패 | PR-B/16 | ERROR | `[api_retry_exhausted]` | individual 영속 |
| `_request` 토큰 만료 최종 실패 | PR-B (Codex) | ERROR | `[api_retry_exhausted]` | individual 영속 |
| `_request` 거부 응답 | A1 | ERROR | `[kis_rejection]` | individual 영속 |

핵심 원칙:
- recovered 만 collector 흡수 (사이클 76 의제 #2) — exhausted 는 영속 (chain 진단 의무)
- `[kis_rejection]` 은 CLAUDE.md "절대 깨지 말 것" 영속 영역 (변경 0)

검증: source code 정적 검증 (3 개 `[api_retry_exhausted]` write_log + 1 개
`[kis_rejection]` write_log 사이트 영속).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_API_ROOT = Path(__file__).resolve().parents[3] / "src" / "api"


# ===========================================================================
# G-ERR1: `[api_retry_exhausted]` 5xx 최종 실패 individual write_log 영속
# ===========================================================================
def test_g_err1_api_retry_exhausted_5xx_individual_preserved():
    """G-ERR1: `_request` HTTPStatusError + 5xx + attempt == MAX_RETRIES 분기에
    `[api_retry_exhausted]` write_log 영속.

    사이클 29 005935 chain 진단 의무 — chain 의 *마지막 시도까지 실패* 사이트는 individual
    보존. recovered collector 흡수 금지.
    """
    base_py = _API_ROOT / "base.py"
    source = base_py.read_text(encoding="utf-8")

    # `[api_retry_exhausted]` prefix 영속
    assert "[api_retry_exhausted]" in source, (
        "G-ERR1: `[api_retry_exhausted]` prefix 누락 — PR-B 영속 위반"
    )

    # 5xx 분기 (last_status=503/5xx) 영속
    # `last_status=` 키워드 + `500 <=` 또는 `5xx` 패턴
    assert "last_status=" in source, (
        "G-ERR1: `last_status=` 필드 누락 — exhausted 메타데이터 영속 위반"
    )
    assert "500 <= status < 600" in source or "500 <= status" in source, (
        "G-ERR1: 5xx 가드 분기 누락 — 4xx 영구 에러 카운트 차단 정책 위반"
    )


# ===========================================================================
# G-ERR2: `[api_retry_exhausted]` 네트워크 최종 실패 individual write_log 영속
# ===========================================================================
def test_g_err2_api_retry_exhausted_network_individual_preserved():
    """G-ERR2: `_request` `httpx.RequestError` + attempt == MAX_RETRIES 분기에
    `[api_retry_exhausted]` `last_status=network` write_log 영속.

    PR-B 영속 — chain 진단 의무 (네트워크 차단 silent skip 가시화).
    """
    base_py = _API_ROOT / "base.py"
    source = base_py.read_text(encoding="utf-8")

    assert "last_status=network" in source, (
        "G-ERR2: `last_status=network` 필드 누락 — PR-B 네트워크 exhausted 영속 위반"
    )
    # `httpx.RequestError` 핸들러 영속
    assert "RequestError" in source, (
        "G-ERR2: `httpx.RequestError` 핸들러 누락"
    )


# ===========================================================================
# G-ERR3: `[api_retry_exhausted]` 토큰 만료 최종 실패 individual write_log 영속
# ===========================================================================
def test_g_err3_api_retry_exhausted_token_expired_individual_preserved():
    """G-ERR3: 토큰 만료 (`token` / `만료` 키워드) + attempt == MAX_RETRIES 분기에
    `[api_retry_exhausted]` `last_status=token_expired` write_log 영속.

    PR-B 보강 (Codex) 영속 — 토큰 발급 재시도 최종 실패 시 [kis_rejection] +
    raise KisApiError 흐름 보존 + exhausted 카운팅 누락 차단.
    """
    base_py = _API_ROOT / "base.py"
    source = base_py.read_text(encoding="utf-8")

    assert "last_status=token_expired" in source, (
        "G-ERR3: `last_status=token_expired` 필드 누락 — PR-B 보강 (Codex) 영속 위반"
    )
    # 토큰 만료 키워드 매칭 영속
    assert '"token" in msg1.lower()' in source or 'in msg1.lower()' in source, (
        "G-ERR3: 토큰 만료 키워드 매칭 누락"
    )


# ===========================================================================
# G-ERR4: `[kis_rejection]` (CLAUDE.md "절대 깨지 말 것") individual write_log 영속
# ===========================================================================
def test_g_err4_kis_rejection_individual_preserved():
    """G-ERR4: `_request` rt_cd != "0" 분기에 `[kis_rejection]` write_log 영속.

    CLAUDE.md "절대 깨지 말 것" 절: KIS 거부 응답 영구 저장 의무.
    민감 키 마스킹 (CANO/ACNT_PRDT_CD 제외) + body 주요 키 (PDNO/ORD_DVSN/ORD_UNPR/
    ORD_QTY/EXCG_ID_DVSN_CD/SLL_BUY_DVSN_CD) 포함 영속.

    사이클 76 변경 0 — recovered collector 영역과 무관.
    """
    base_py = _API_ROOT / "base.py"
    source = base_py.read_text(encoding="utf-8")

    assert "[kis_rejection]" in source, (
        "G-ERR4: `[kis_rejection]` prefix 누락 — CLAUDE.md '절대 깨지 말 것' 영속 위반"
    )

    # 민감 키 마스킹 (CANO/ACNT_PRDT_CD 제외) — 화이트리스트 명시 영속
    for key in ("PDNO", "ORD_DVSN", "ORD_UNPR", "ORD_QTY"):
        assert key in source, (
            f"G-ERR4: 민감 키 마스킹 화이트리스트 `{key}` 누락 — body 주요 키 영속 위반"
        )

    # fire-and-forget 패턴 (write_log 예외 swallow) 영속
    # `try: ... await _system_logs.write_log(...) ... except Exception: pass`
    assert "except Exception" in source, (
        "G-ERR4: fire-and-forget 예외 swallow 누락 — KIS rejection 흐름 차단 위험"
    )
