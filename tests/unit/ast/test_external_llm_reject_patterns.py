"""사이클 88 (2026-06-09) — 외부 LLM 추천 영구 차단 AST 가드.

외부 LLM 의견서 (`_workspace/external_llm_reviews/2026-06-09_realtime_review.md`)
의 단순 통합 추천 3 영역에 대해 미래 동일 추천 재현 시 즉시 검출.

양 agent (refactor-expert + domain-expert) 일치 결론:
    "구조 관찰 객관, 영속 시정 18 사이클 도메인 지식 부재"

영속 보장 매트릭스:
- WebSocket 4중 안전망 (F1 + _scan_loop + K stale watcher + _resubscribe_stale_priority)
- 종목 + 세션 2 계층 stale 하이브리드 (사이클 29 R1 + R2)
- 4 dict 분리 (_subscriptions / _subscriptions_acked / _ticker_to_session / ticker_last_tick)
- HIGH bypass_limit=True + 보유/익일청산 절대 보호 (사이클 32 R4)

영구 차단 이력:
- 사이클 17 OPSP0002 backoff
- 사이클 29 R1/R2/R3 (종목 + 세션 + priority)
- 사이클 32 R4 universe guard
- 사이클 38 명문화
- 사이클 66 cap=10 priority
- 사이클 67 stale_manager 4 sub-module 분할
- 사이클 74 sampling 5분 aggregation
- 사이클 78 flush 누락 영구 차단
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]


# ============================================================
# G-REJECT-1: 단일 restore 도입 영구 차단 (외부 추천 R4)
# ============================================================
def test_g_reject_1_quadruple_safety_net_persistence():
    """G-REJECT-1: WebSocket 4중 안전망 영속.

    외부 LLM R4 ("restore / reverify / stale_recovery → 하나로 통합") 반려.

    영속 의무 = 4중 안전망 시간 척도 분리:
    1. F1 재연결 후 verify (websocket._verify_subscriptions_after_reconnect)
    2. _scan_loop 5분 주기 (scheduler._scan_loop)
    3. K stale watcher 120s (stale_watcher_core.check_and_resubscribe_stale)
    4. priority 5분 우선 (stale_watcher_core.resubscribe_stale_priority)

    위반 시 사고 시나리오:
    - 단일 restore 통합 시 KIS 거부 코드 (OPSP0002/APBK0918/5xx/토큰 만료)
      분기별 복구 영역 마비 → KIS LMS chain 위험
    - 사이클 29 005935 사고 패턴 재현
    """
    websocket_py = (_REPO_ROOT / "src/realtime/websocket.py").read_text()
    stale_watcher_core_py = (_REPO_ROOT / "src/engine/stale_watcher_core.py").read_text()
    scheduler_py = (_REPO_ROOT / "src/engine/scheduler.py").read_text()

    # F1 재연결 verify (사이클 29 R3 영속)
    assert "_verify_subscriptions_after_reconnect" in websocket_py, (
        "외부 LLM R4 위반 — F1 재연결 후 verify 함수 영속 의무. "
        "_verify_subscriptions_after_reconnect 누락 = 4중 안전망 1번 마비."
    )

    # K stale watcher (사이클 29 R1 + 사이클 66 + 사이클 67 영속)
    assert "def check_and_resubscribe_stale" in stale_watcher_core_py, (
        "외부 LLM R4 위반 — K stale watcher 영속 의무. "
        "check_and_resubscribe_stale 누락 = 4중 안전망 3번 마비 + 사이클 29 005935 재현."
    )

    # priority resubscribe (사이클 66 cap=10 priority + 사이클 67 영속)
    assert "def resubscribe_stale_priority" in stale_watcher_core_py, (
        "외부 LLM R4 위반 — priority resubscribe 영속 의무. "
        "resubscribe_stale_priority 누락 = 4중 안전망 4번 마비."
    )

    # _scan_loop 5분 주기 (scheduler 영속)
    assert "_scan_loop" in scheduler_py, (
        "외부 LLM R4 위반 — _scan_loop 5분 주기 영속 의무. "
        "_scan_loop 누락 = 4중 안전망 2번 마비."
    )


# ============================================================
# G-REJECT-2: stale 전체 WS 단독 판정 영구 차단 (외부 추천 R5)
# ============================================================
def test_g_reject_2_per_ticker_stale_persistence():
    """G-REJECT-2: 종목별 stale 판정 영속.

    외부 LLM R5 ("종목 체결 없음 → 전체 WS 메시지 수신 없음으로 stale 판정 전환") 반려.

    영속 의무 = 종목 + 세션 2 계층 하이브리드:
    - 종목 단위: ticker_last_tick + STALE_FRESHNESS_SECS (사이클 29 R1)
    - 세션 단위: silent_inactive 3중 가드 (사이클 29 R2)

    위반 시 사고 시나리오:
    - 전체 WS 단독 채택 시 특정 종목 거래정지/품절 미감지
      ex. SK하이닉스 활성 + 삼성전자 정지 → 세션 fresh_ratio 정상 → 삼성전자 silent 미감지
    - HIGH 보유 종목 매도 hot path 마비
    - 사이클 29 005935 사고: 종목 단위 가시성으로 진단 가능 (전체 기준이면 발견 불가)
    """
    # ticker_last_tick 는 src/engine/scanner.py 에 정의 (모듈 전역 dict)
    # stale_tracker.py 는 StaleTrackerState 데이터클래스 (retry_count / force_retry_history 등)
    scanner_py = (_REPO_ROOT / "src/engine/scanner.py").read_text()
    stale_watcher_core_py = (_REPO_ROOT / "src/engine/stale_watcher_core.py").read_text()

    # ticker_last_tick 종목별 추적 영속 (scanner.py 모듈 전역)
    assert "ticker_last_tick" in scanner_py, (
        "외부 LLM R5 위반 — ticker_last_tick 종목별 추적 영속 의무. "
        "src/engine/scanner.py 의 모듈 전역 dict 누락 = 종목 단위 stale 판정 불가. "
        "전체 WS 단독 채택 시 사이클 29 005935 재현."
    )

    # STALE_FRESHNESS_SECS 종목 단위 임계 영속
    assert "STALE_FRESHNESS_SECS" in stale_watcher_core_py, (
        "외부 LLM R5 위반 — STALE_FRESHNESS_SECS 종목 단위 임계 영속 의무. "
        "누락 = 종목 단위 stale 판정 마비."
    )


# ============================================================
# G-REJECT-3: SubscriptionRegistry 단일 dict 통합 영구 차단 (외부 추천 R2)
# ============================================================
def test_g_reject_3_four_dict_separation_persistence():
    """G-REJECT-3: 4 dict 분리 영속.

    외부 LLM R2 ("_subscriptions / _subscriptions_acked / ticker_to_session 통합") 반려.

    영속 의무 = 4 dict 분리:
    - _subscriptions: 실제 구독 종목 set (SEND 기준)
    - _subscriptions_acked: ACK 정합성 가드 (orphan ACK race 차단)
    - _ticker_to_session: 멀티 세션 분산 (KIS 41 구독 한도 분배)
    - ticker_last_tick: 종목별 마지막 tick 시각 (G-REJECT-2 와 중복 보강)

    위반 시 사고 시나리오:
    - 단일 dict 통합 시 orphan ACK race 가드 마비
      → KIS SUBSCRIBE 송신 ↔ ACK 수신 race (수십 ms~수초) 동안 상태 불일치
    - KIS 41 한도 분산 영역 마비 → 세션 초과 에러
    - 종목별 tick 추적 영역 마비 → stale 판정 불가
    - 사이클 29 R3 priority 분리 회귀 위험
    """
    websocket_py = (_REPO_ROOT / "src/realtime/websocket.py").read_text()
    websocket_pool_py = (_REPO_ROOT / "src/realtime/websocket_pool.py").read_text()

    # 4 dict 전수 영속 검증
    required_dicts = [
        "_subscriptions",
        "_subscriptions_acked",
        "_ticker_to_session",
        "ticker_last_tick",
    ]

    combined = websocket_py + websocket_pool_py

    for d in required_dicts:
        assert d in combined, (
            f"외부 LLM R2 위반 — {d} 영속 의무. "
            f"단일 dict 통합 시 orphan ACK race / 41 한도 분산 / "
            f"종목별 tick 추적 영역 마비."
        )
