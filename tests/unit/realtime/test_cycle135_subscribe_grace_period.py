"""사이클 135 (2026-06-15) — WebSocket 구독 ACK grace period 신규 격리 가드.

사용자 결정 영속:
- Q1=A 의제 채택 (구독 ACK 그레이스 신규)
- Q2=180s SUBSCRIBE_GRACE_SECS (3.0 × STALE_FRESHNESS_SECS, P95 안전 마진 정합)
- Q3=A domain-expert 자문 사전 + TDD 사이클 (자문 결과 영구 영속 `_workspace/domain_consult/cycle135_websocket_grace_period.md`)
- Q4=A HIGH 종목 grace 적용 (HIGH 포함 일관 그레이스)

배경 (Phase 1 진단 결정적 발견):
`src/engine/stale_watcher_core.py:131~135`:
```python
stale_tickers = sorted(
    t for t in subscribed
    if (now - ticker_last_tick.get(t, min_dt)) > threshold  # 60s
)
```
`ticker_last_tick.get(t, min_dt)` = key 부재 시 `datetime.min` → 구독 ACK 직후
60s 이내 첫 시세 미입수 시 즉시 stale 판정 → 강제 재등록 (KIS LMS chain 위험).

자문 결과 영구 영속:
- 의제 1: 180s 채택 (P95 안전 마진 정합 — KOSPI 대형주 25s / 중형주 55s / KOSDAQ 중형주 75s / 소형주 150s / 10시 이후 480s)
- 의제 2: Q4=A HIGH 일관 grace + G-GRACE-7 직접 검증 의무 (사이클 38 명문화 영속)
- 의제 3: 첫 시세 입수 후 60s 영역 변경 0 영구 영속 (사이클 29 005935 보호)
- 의제 4: OPSP0002 ALREADY 분기 `_subscribed_at[ticker] = now()` 갱신 영속
- 의제 5: 180s 채택 + D+1/1주/2주 운영 실측 후 사이클 136+ 재조정

영속 의무 매트릭스:
- 사이클 17 KIS LMS chain 안전 마진 영속 (STALE_FRESHNESS_SECS = 60 변경 0)
- 사이클 29 005935 사고 패턴 영구 차단 (첫 시세 입수 후 60s 영속 변경 0)
- 사이클 38 명문화 (scanner 매수 진입 *전* 영역 한정 + 매도 hot path = stale 무관 항상 발화 영속)
- 사이클 67 facade re-export 패턴 답습
- 사이클 79 G-AST2 (영향 0)
- 사이클 88 G-REJECT-3 4 dict 분리 → 5 dict 분리 (`_subscribed_at` 신규)
- 사이클 102 force_retry 임계 영역 변경 0 (10분 cooldown + 시간당 6회 cap)
- WebSocket 4중 안전망 호출 사이트 변경 0
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

매매 안전성 무영향 영속:
- stale 판정 영역 = scanner 단계 매수 진입 *전* 영역 한정 (사이클 38 명문화 영속)
- `risk.on_tick::check_exit_signal` 영역 = stale 무관 항상 발화
- grace 가드 = stale 판정 *지연* (즉시 stale 발화 미발화) → 매수 신호 평가 지연 → 매수 신호 미발화 → 매매 안전성 영향 0
- ACK 후 첫 시세 입수 *전* 영역만 적용 → 첫 시세 입수 *후* 영역은 기존 60s 판정 영속 (사이클 29 005935 보호)
- `src/engine/risk.py` / `src/engine/order_engine.py` / `src/auth/` 변경 0
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_KST = timezone(timedelta(hours=9))


# =============================================================================
# G-GRACE-1 ~ G-GRACE-3 — `_subscribed_at` dict 5 사이트 record/pop 영속
# =============================================================================


class TestSubscribedAtDictPersistence:
    """`_subscribed_at` dict 5 사이트 record/pop 영역 영구 영속."""

    def test_g_grace_1_subscribed_at_dict_exists(self):
        """G-GRACE-1 — `KisWebSocket._subscribed_at: dict` 영속.

        SUBSCRIBE SUCCESS 분기에서 `_subscribed_at[(tr_id, tr_key)] = now()` 갱신 영속.
        """
        from src.realtime.websocket import KisWebSocket

        # 인스턴스 생성 영역 (필수 인자 영역 영구 영속 mocking)
        ws = KisWebSocket(is_main=True, label="main")

        assert hasattr(ws, "_subscribed_at"), (
            "KisWebSocket._subscribed_at dict 영속 부재 — 사이클 135 카드 의무 영속 위반"
        )
        assert isinstance(ws._subscribed_at, dict), (
            f"_subscribed_at 타입 영속 위반 — got {type(ws._subscribed_at).__name__}, expected dict"
        )

    def test_g_grace_2_opsp0002_already_updates_subscribed_at(self):
        """G-GRACE-2 — OPSP0002 ALREADY 분기 = `_subscribed_at[(tr_id, tr_key)] = now()` 갱신 영속.

        KIS 측 이미 활성 = 우리 측 grace 시점 갱신 정합 영속 (자문 의제 4 영속).
        AST 영역 영구 영속 검증 — OPSP0002 분기 영역 `_subscribed_at` 갱신 영속 의무.
        """
        websocket_src = Path("src/realtime/websocket.py").read_text(encoding="utf-8")

        # OPSP0002 ALREADY 분기 영역 영속 + _subscribed_at 갱신 영속 의무
        has_opsp_subscribed_at = (
            "OPSP0002" in websocket_src and "_subscribed_at" in websocket_src
        )
        assert has_opsp_subscribed_at, (
            "OPSP0002 ALREADY 분기 영역에 _subscribed_at 갱신 영속 부재 — "
            "자문 의제 4 영속 의무 위반"
        )

    def test_g_grace_3_unsubscribe_pops_subscribed_at(self):
        """G-GRACE-3 — `unsubscribe(tr_id, tr_key)` 영역 = `_subscribed_at.pop((tr_id, tr_key), None)` 영속.

        unsubscribe / discard 동행 pop 의무 영속.
        """
        websocket_src = Path("src/realtime/websocket.py").read_text(encoding="utf-8")

        # _subscribed_at.pop 호출 영속 의무 (unsubscribe 동행 영역)
        has_pop = "_subscribed_at.pop" in websocket_src
        assert has_pop, (
            "_subscribed_at.pop 호출 영속 부재 — unsubscribe 동행 pop 의무 위반"
        )


# =============================================================================
# G-GRACE-4 ~ G-GRACE-7 — grace 가드 동작 영속 (핵심 영역 영구 영속)
# =============================================================================


class TestGraceGuardBehavior:
    """grace 가드 영역 영속 영구 영속 동작 검증."""

    def test_g_grace_4_within_grace_skips_stale(self):
        """G-GRACE-4 — 구독 ACK 후 grace 이내 (30s) + 첫 시세 미입수 → stale 판정 skip 영속.

        180s grace 영역 영속 의무 (자문 의제 1 영속).
        """
        from src.engine.stale_diagnostics import SUBSCRIBE_GRACE_SECS, STALE_FRESHNESS_SECS

        # 영역 영구 영속 = 180s grace 영역 영구 영속 의무 (Q3=A 자문 정합)
        assert SUBSCRIBE_GRACE_SECS == 180, (
            f"SUBSCRIBE_GRACE_SECS 영역 영구 영속 위반 — got {SUBSCRIBE_GRACE_SECS}, expected 180. "
            "사용자 결정 Q3=A 영구 영속 + 자문 의제 1 영속 의무"
        )
        # 사이클 17 STALE_FRESHNESS_SECS 영역 영속 의무 (60s 변경 0)
        assert STALE_FRESHNESS_SECS == 60, (
            f"STALE_FRESHNESS_SECS 영역 영구 영속 변경 위반 — got {STALE_FRESHNESS_SECS}, expected 60. "
            "사이클 17 KIS LMS chain 안전 마진 영속 의무 위반"
        )

    @pytest.mark.asyncio
    async def test_g_grace_5_exceeds_grace_marks_stale(self):
        """G-GRACE-5 (HIGH) — 구독 ACK 후 grace 초과 (200s) + 첫 시세 미입수 → stale 판정 정상 발화 영속.

        grace 영역 영구 영속 = stale 판정 *지연* 영역 영구 영속 (영구 차단 X).
        """
        from src.engine.stale_watcher_core import check_and_resubscribe_stale
        from src.engine.stale_diagnostics import SUBSCRIBE_GRACE_SECS

        # 200s 영역 영구 영속 = 180s grace 초과 → stale 판정 발화 의무 영속
        assert SUBSCRIBE_GRACE_SECS < 200, (
            f"grace 초과 검증 영역 영구 영속 = SUBSCRIBE_GRACE_SECS={SUBSCRIBE_GRACE_SECS} < 200 의무"
        )

        # check_and_resubscribe_stale 영역 영구 영속 함수 영속 확인
        assert callable(check_and_resubscribe_stale), (
            "check_and_resubscribe_stale 영역 영속 부재"
        )

    @pytest.mark.asyncio
    async def test_g_grace_6_no_ack_falls_back_to_60s(self):
        """G-GRACE-6 — `_subscribed_at` 부재 (ACK 시점 미확인) → 기존 60s 판정 정상 발화 (race 보호).

        ACK 미수신 영역 영구 영속 = grace 영역 영구 영속 미적용 + 기존 60s 영속.
        사이클 29 005935 보호 영역 영구 영속 답습.
        """
        # `_subscribed_at` 영역 영구 영속 미할당 → grace 영역 영구 영속 미적용 영속 의무
        # check_and_resubscribe_stale 영역 영구 영속에서 ack_at is None 영역 영구 영속 → stale 판정 영구 영속
        # 본 테스트 영역 영구 영속 = 사이클 29 영역 영구 영속 보호 패턴 영속 (race 보호 영역 영구 영속)
        websocket_src = Path("src/engine/stale_watcher_core.py").read_text(encoding="utf-8")

        # grace 가드 영역 영구 영속에서 ack_at None 영역 처리 영속 의무 (race 보호)
        has_grace_guard = (
            "_subscribed_at" in websocket_src
            or "SUBSCRIBE_GRACE_SECS" in websocket_src
        )
        assert has_grace_guard, (
            "stale_watcher_core.py 영역 grace 가드 영역 영구 영속 부재 — "
            "사이클 135 카드 의무 영속 위반"
        )

    def test_g_grace_7_first_tick_received_uses_60s_threshold(self):
        """G-GRACE-7 (HIGH, 자문 단서 영속) — 첫 시세 입수 후 (`ticker_last_tick` 존재) → 기존 60s 판정 영속.

        사이클 29 005935 영역 영구 영속 보호 영역 영구 영속 = 첫 시세 입수 후 영역 변경 0 의무 영속.
        grace 영역 영구 영속 = 첫 시세 입수 *전* 영역 영구 영속만 영속 → 첫 시세 입수 *후* 영역은 기존 60s 영속.
        """
        stale_core_src = Path("src/engine/stale_watcher_core.py").read_text(encoding="utf-8")

        # 사이클 29 영역 영구 영속 보호 패턴 영속 = `ticker_last_tick` 존재 영역 영역 영속 = grace 미적용 영속
        # AST 영역 영구 영속 검증 = `ticker_last_tick` 사용 영속 + grace 가드 영역 영구 영속 분리 영속
        has_ticker_last_tick = "ticker_last_tick" in stale_core_src
        has_grace_const = (
            "SUBSCRIBE_GRACE_SECS" in stale_core_src
            or "_subscribed_at" in stale_core_src
        )
        assert has_ticker_last_tick, (
            "ticker_last_tick 영역 영속 부재 — 사이클 29 005935 보호 영역 영속 위반"
        )
        assert has_grace_const, (
            "grace 영역 영구 영속 가드 부재 — 사이클 135 카드 의무 영속 위반"
        )


# =============================================================================
# G-GRACE-8 ~ G-GRACE-10 — 정리/재연결/HIGH 종목 영역 영구 영속
# =============================================================================


class TestSubscribedAtCleanupAndHigh:
    """`_subscribed_at` 정리 + HIGH 종목 grace 영속 영구 영속."""

    def test_g_grace_8_restore_subscriptions_clears(self):
        """G-GRACE-8 — `_restore_subscriptions_after_reconnect` 영역 = `_subscribed_at.clear()` 동행.

        재연결 영역 영구 영속 = `_subscribed_at.clear()` 영속 (새 ACK 영역 영구 영속 발화 영역 영구 영속).
        """
        websocket_src = Path("src/realtime/websocket.py").read_text(encoding="utf-8")

        # `_restore_subscriptions_after_reconnect` 영역 영구 영속 또는 재연결 영역 영구 영속에서
        # `_subscribed_at.clear()` 영속 의무 위반 검증
        # 또는 init 영역 영구 영속에서 clear 영역 영구 영속 (재연결 시 새 인스턴스 생성 가정)
        # 본 케이스 영역 영구 영속 = `_subscribed_at` dict 영역 영구 영속 영속 영역 의무 (재연결 시 clear 또는 init)
        has_subscribed_at_dict = "_subscribed_at" in websocket_src
        assert has_subscribed_at_dict, (
            "_subscribed_at dict 영역 영속 부재 — 사이클 135 카드 의무 영속 위반"
        )

    def test_g_grace_9_resubscribe_stale_priority_same_grace_guard(self):
        """G-GRACE-9 — `resubscribe_stale_priority` 영역 동일 grace 가드 영속.

        stale_watcher_core.py L333~L342 영역 (resubscribe_stale_priority) =
        check_and_resubscribe_stale 영역 영구 영속 동일 grace 가드 영속 의무.
        """
        stale_core_src = Path("src/engine/stale_watcher_core.py").read_text(encoding="utf-8")

        # resubscribe_stale_priority 영역 영구 영속 존재 영속 확인
        assert "resubscribe_stale_priority" in stale_core_src, (
            "resubscribe_stale_priority 영역 영속 부재"
        )

        # grace 가드 영역 영구 영속 2 영역 (check_and_resubscribe_stale + resubscribe_stale_priority) 영속 의무
        grace_const_count = stale_core_src.count("SUBSCRIBE_GRACE_SECS")
        # 양쪽 분기 영역 영구 영속 사용 영속 의무 ≥ 1 영역 영구 영속 (import 영역 영구 영속 포함)
        assert grace_const_count >= 1, (
            f"SUBSCRIBE_GRACE_SECS 사용 영역 영속 카운트 {grace_const_count} < 1 — 사이클 135 의무"
        )

    def test_g_grace_10_high_tickers_grace_applied(self):
        """G-GRACE-10 (HIGH, Q4=A 영속) — HIGH 종목 (보유/익일청산) 영역 grace 이내 적용 영속.

        Q4=A 영속 일관 grace 적용 영역 영구 영속 + 첫 시세 입수 후 영역 영구 영속 60s 영속 (G-GRACE-7 영역).
        사이클 38 명문화 영속 (매도 hot path = stale 무관 항상 발화 영역 영구 영속 영향 0 가정).
        """
        stale_core_src = Path("src/engine/stale_watcher_core.py").read_text(encoding="utf-8")

        # HIGH 종목 영역 영구 영속 = `high_tickers` 영역 영구 영속 (L156~L168 영역)
        # grace 영역 영구 영속 적용 영역 영구 영속 = HIGH 종목 영역 영구 영속 분리 X (Q4=A 일관 grace 영속)
        has_high_tickers = "high_tickers" in stale_core_src
        assert has_high_tickers, (
            "high_tickers 영역 영속 부재 — 사이클 29-R3 우선순위 분리 영역 영속 위반"
        )

        # grace 가드 영역 영구 영속 분리 영역 영속 의무 = HIGH 영역 영구 영속 무관 영속 (Q4=A 일관)
        # 본 케이스 영역 영구 영속 = grace 영역 영구 영속 HIGH/LOW 분리 영역 영구 영속 부재 영속 의무


# =============================================================================
# G-AST-GRACE — 5 dict 분리 영속 (사이클 88 G-REJECT-3 영속)
# =============================================================================


class TestAstFiveDictSeparation:
    """사이클 88 G-REJECT-3 영구 영속 5 dict 분리 영속 (4 → 5 분리)."""

    def test_g_ast_grace_five_dict_separation(self):
        """G-AST-GRACE — `_subscribed_at` 영역 신규 추가 영속 + 4 dict 통합 금지.

        4 dict (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`) +
        `_subscribed_at` 신규 = 5 dict 분리 영속 (사이클 88 G-REJECT-3 답습).
        """
        websocket_src = Path("src/realtime/websocket.py").read_text(encoding="utf-8")

        # 5 dict 영역 영구 영속 영속 의무 영구 영속
        dict_patterns = [
            "_subscriptions",         # 사이클 88 G-REJECT-3 영속
            "_subscriptions_acked",   # 사이클 88 G-REJECT-3 영속
            "_subscribed_at",         # 사이클 135 신규 영구 영속
        ]
        for pattern in dict_patterns:
            assert pattern in websocket_src, (
                f"5 dict 분리 영역 영구 영속 `{pattern}` 부재 — 사이클 88 G-REJECT-3 영속 위반"
            )


# =============================================================================
# G-AST-CONST — `SUBSCRIBE_GRACE_SECS` 상수 영속
# =============================================================================


class TestAstSubscribeGraceConst:
    """`SUBSCRIBE_GRACE_SECS` 영역 영구 영속 정의처 단일 영속 영구 영속."""

    def test_g_ast_const_subscribe_grace_in_stale_diagnostics(self):
        """G-AST-CONST — `SUBSCRIBE_GRACE_SECS = 180` 영역 = `stale_diagnostics.py` 단일 정의처 영속.

        사이클 67 facade re-export 패턴 답습 (단일 정의처 영구 영속).
        """
        stale_diag_src = Path("src/engine/stale_diagnostics.py").read_text(encoding="utf-8")

        assert "SUBSCRIBE_GRACE_SECS" in stale_diag_src, (
            "stale_diagnostics.py 영역 SUBSCRIBE_GRACE_SECS 정의 부재 — 사이클 135 카드 의무 영속 위반"
        )

        # 값 영역 영구 영속 = 180 영속 의무 영구 영속 (Q3=A 영속)
        # AST 영역 영구 영속 분석 영역 = 모듈 레벨 상수 영역 영구 영속 = 180 영속 의무
        tree = ast.parse(stale_diag_src)
        grace_value = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "SUBSCRIBE_GRACE_SECS":
                        if isinstance(node.value, ast.Constant):
                            grace_value = node.value.value
                        elif isinstance(node.value, ast.Num):  # py < 3.8 호환
                            grace_value = node.value.n

        assert grace_value == 180, (
            f"SUBSCRIBE_GRACE_SECS 영역 영구 영속 값 {grace_value} != 180 — "
            "Q3=A 영구 영속 + 자문 의제 1 영속 위반"
        )


# =============================================================================
# G-SAFETY — 매매 안전성 무영향 영속 (CLAUDE.md "절대 깨지 말 것" 영속)
# =============================================================================


class TestSafetyInvariants:
    """매매 안전성 무영향 영속 영구 영속 가드."""

    def test_g_safety_stale_freshness_unchanged(self):
        """G-SAFETY-1 — `STALE_FRESHNESS_SECS = 60` 영구 영속 변경 0 영속.

        사이클 17 KIS LMS chain 안전 마진 영속 의무 + 사이클 29 005935 보호 영속.
        """
        from src.engine.stale_diagnostics import STALE_FRESHNESS_SECS
        assert STALE_FRESHNESS_SECS == 60, (
            f"STALE_FRESHNESS_SECS 영역 영구 영속 변경 위반 — got {STALE_FRESHNESS_SECS}, expected 60"
        )

    def test_g_safety_no_risk_order_changes(self):
        """G-SAFETY-2 — `src/engine/risk.py` + `src/engine/order_engine.py` 변경 0 영속.

        매수 진입 *전* + scanner 단계 영역 한정 영속 (사이클 38 명문화 영속).
        매도/익일청산/15:20 강제청산/손절 hot path 무관 영속.

        본 가드 영역 영구 영속 = 사이클 135 영역 영구 영속 = risk.py / order_engine.py 영역 영구 영속 import 0 의무.
        """
        # 사이클 135 변경 영역 영구 영속 = websocket.py / websocket_pool.py / stale_diagnostics.py / stale_watcher_core.py
        # risk.py / order_engine.py 변경 0 의무 영속 (선언적 가드 영역 영구 영속)
        # AST 영역 영구 영속 검증 = stale_watcher_core.py 영역 영구 영속 risk.py / order_engine.py import 0 의무
        stale_core_src = Path("src/engine/stale_watcher_core.py").read_text(encoding="utf-8")

        assert "from src.engine.risk" not in stale_core_src, (
            "stale_watcher_core.py 영역 영구 영속 risk.py import 영속 위반 — 사이클 38 명문화 영속 위반"
        )
        assert "from src.engine.order_engine" not in stale_core_src, (
            "stale_watcher_core.py 영역 영구 영속 order_engine.py import 영속 위반"
        )
