# 사이클 9 — KIS 차단 회피 안전망 (Red 명세)

직전 베이스라인: 1221 tests (commit edba27b, 2026-05-18 07:50).

## 배경
KIS Open API 담당자 공지 (2026-05-18) — 무한 연결/종료 반복, 검증 없는 무한 등록/해제 반복 시 IP/앱키 일시 차단 예정.

자체 점검 결과, K stale watcher(30s 주기) × 보조 세션 5개 × 40 종목 × 강제 재등록 임계 3 → 분당 800 요청 가능 → KIS 비정상 케이스 2 (무한 등록/해제) 직접 매핑.

## 행위 (4 항목)

### 행위 1 — stale watcher 발화 주기 완화
- `src/engine/scheduler.py::STALE_WATCHER_INTERVAL_SECS == 120` (이전 30)
- `src/engine/scheduler.py::STALE_FORCE_REREGISTER_AFTER == 10` (이전 3)
- `STALE_FRESHNESS_SECS == 60` 보존 (5/12 운영 사고 대응 의도)
- 분당 트래픽: 보조 5개 × 40 종목 × 강제 재등록 × (30s→120s) = 800 → 200 미만

### 행위 2 — `QuoteSessionHealthMonitor` 신규 (`src/services/quote_session_health.py`)
- 보조 세션별 토큰 발급 실패/5xx 누적 추적 (메인 라벨은 추적 제외)
- 임계 `MAX_CONSECUTIVE_FAILURES=5` 연속 실패 → 자동 비활성
- 5분 sliding window `MAX_FAILURE_RATE=0.5` (`MIN_CALLS_FOR_RATE=10`) → 자동 비활성
- 자동 비활성 시 (1) `kis_quote_accounts.update_account(active=False)` (2) `kis_ws_pool.disable_quote_session(label)` (3) `system_logs` `[quote_session_disabled]` 영구
- DB update 실패 graceful — 메모리만 비활성 + WARNING 로그
- 메인 라벨 호출은 noop (안전 가드)
- 두 번째 비활성 호출 idempotent (`_disabled_labels` set)

### 행위 3 — `base.py::_request_via_quote_pool` 통합
- 성공(`rt_cd=="0"`) 후 actual_label != "main" 일 때 `record_success(label)`
- 5xx 응답 → `record_failure(label, reason=f"http_{status}")`
- 보조 매니저 발급 실패 → `record_failure(label, reason="token_issue_fail")`
- KIS rt_cd!=0 (비즈니스 거부) → 기록 안 함

### 행위 4 — `WebsocketPool.disable_quote_session(label)` 신규
- `_quotes` 에서 해당 라벨 세션 찾아 disconnect + 제거
- `_ticker_to_session` 에서 해당 세션 담당 ticker 정리
- 라벨 없으면 noop (idempotent)
- 메인 라벨은 noop (안전 가드)

## 회귀 테스트 매핑

| 행위 | 파일 | 케이스 |
|------|------|--------|
| 1 | `tests/unit/engine/test_stale_watcher_thresholds.py` (신규) | 6 |
| 2 | `tests/unit/services/test_quote_session_health.py` (신규) | 10 |
| 2+3 | `tests/contract/test_quote_session_auto_disable.py` (신규) | 4 |
| 4 | `tests/unit/realtime/test_websocket_pool.py` 확장 | 5 |

기대 합계: 1221 → ~1246.

## 안전 원칙
- 운영 매매 흐름 무관 (WebSocket/시세 호출 안전망만)
- 5/12 운영 사고 대응 의도 보존 (FRESHNESS=60s 그대로)
- 자동 비활성 graceful, 운영자 수동 재활성 가능 (Settings UI → 다음 _boot)
- 메인 라벨 자동 비활성 절대 금지
