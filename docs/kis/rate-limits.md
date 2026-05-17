# KIS API 호출 유량 정책 (Rate Limits)

> **공식 안내 기준일**: 2026-04-20 (KIS Developers 공지)
> **본 문서 작성일**: 2026-05-17

KIS OpenAPI 의 초당 호출 제한과 본 시스템(`auto_stock`) 의 적용 현황을 정리한다.

---

## 1. KIS 공식 정책 (2026-04-20 기준)

### REST API

| 환경 | 한도 | 비고 |
|------|------|------|
| **실전투자** | 1초당 **18건** (기존 20건에서 하향) | 계좌(앱키) 단위 적용 |
| **모의투자** | 1초당 **1건** (기존 2건에서 하향) | 계좌(앱키) 단위 적용 |
| 접근토큰발급 (`/oauth2/tokenP`) | 1초당 **1건** | 2023-10-27 시행, 환경 무관 |

- **변경 사유**: 호출 트래픽 급증에 따른 트래픽 관리 강화
- **분산 정책**: 서버 내 분산으로 일부 유량이 통과되지 않을 수 있음 → **즉시 재호출** 권장
- **동시 호출 권장 간격**: 100ms ~ 150ms 텀

### WebSocket

| 항목 | 한도 |
|------|------|
| 실시간 데이터 동시 등록 (체결가 + 호가 + 예상체결 + 체결통보 합산) | **1세션당 41건** |
| 적용 범위 | 국내주식 / 해외주식 / 국내파생 / 해외파생 **모든 상품 합산** |
| 체결통보 | HTS ID 단위 등록, ID 연결 모든 계좌의 체결 통보 수신 |
| 세션 수 | 1개의 계좌(앱키) 당 **1세션** |
| 다중 세션 | 1 PC 에서 여러 계좌(앱키)로 세션 연결 가능 |
| 접속키 발급 | 초당 1건 |

### 추가 유량 확보 방법

- 과금 정책 / 유량 확대 **계획 없음**
- 추가 유량 필요 시: 다른 계좌의 API 등록 → 발급된 앱정보(appkey, appsecret)로 분산 호출

---

## 2. 본 시스템 적용 현황

### REST — `src/api/base.py::_rate_limit()`

```python
_semaphore = asyncio.Semaphore(20)  # 초당 20건
```

| 항목 | 현재 값 | KIS 공식 | 상태 |
|------|--------|---------|------|
| 실전 REST 한도 | **20건/초** | 18건/초 | ⚠️ **2건 초과 — 보정 필요** |
| 모의 REST 한도 | 20건/초 | 1건/초 | ⚠️ 모의 환경 분리 미적용 |
| 재시도 백오프 | `BACKOFF_BASE=0.5s × 2^(attempt-1)` + jitter | — | 분산 정책 대응 |
| 동시 호출 간격 | 일부 경로 50ms (`asyncio.sleep(0.05)`) | 100~150ms 권장 | ⚠️ 권장 미만 |

**관련 안전 규칙** (CLAUDE.md):
- 모든 KIS REST 호출은 `src/api/base.py::kis_request()` 경유 (Rate Limit·재시도·메트릭)
- 호출 메트릭 누적 — `_request_metrics` (total/http_5xx/http_4xx/network_err/kis_error/retries)
- 일일 로그 분석 (20:10) 이 메트릭 INSERT 후 reset

### 토큰 발급 — `src/auth/token.py`

- 24시간 캐시 → 일일 1~2회 호출. 초당 1건 한도 영향 거의 없음
- 토큰 만료 감지 시 자동 갱신 (`kis_request` 내부)

### WebSocket — `src/realtime/websocket.py`

```python
MAX_SUBSCRIPTIONS = 41  # KIS 공식 한도
```

| 항목 | 적용 |
|------|------|
| 동시 구독 한도 | **41건** (KIS 공식과 일치) ✅ |
| 보유 종목 / 익일청산 우선 보장 | `bypass_limit=True` 로 한도 무시 — 손절·트레일링 감시 절대 보장 (E1, 2026-05-12) |
| 후순위 drop 가시화 | `[priority_drop] swing=X momentum=Y breakout=Z` INFO 로그 + `system_logs` |
| 거절 응답 감지 | `_handle_raw()` 가 `rt_cd != "0"` 또는 키워드(LIMIT/EXCEED 등) 매칭 시 `_subscriptions.discard` + ERROR 로그 (E2) |
| 재연결 후 자동 검증 | `_verify_subscriptions_after_reconnect()` — 60s 내 tick 없는 구독 재전송 (F1) |
| 동시 호출 간격 | `asyncio.sleep(0.05)` (50ms) — 권장 100~150ms 미만 |

체결통보 구독 (`H0STCNI0` / `H0STCNI9`): 41건 한도에 포함됨. **제거 금지** (포지션 등록·손절 불가).

---

## 3. 잠재 결함 / 후속 작업

본 문서 작성 시점에 KIS 공식 정책과 본 시스템 구현 간 다음 불일치가 확인됨:

### 🔴 결함 1 — REST 실전 한도 미반영

- **현재**: `Semaphore(20)` 초당 20건
- **KIS 공식**: 실전 18건/초
- **영향**: 운영 트래픽 피크 시 분산 정책 거부 가능성 → 재호출로 자연 흡수되지만 `[priority_drop]` 또는 5xx 발생 가능
- **fix**: `src/api/base.py:27` `_semaphore = asyncio.Semaphore(18)` + `_rate_limit()` 의 `>= 20` 도 `>= 18` 로 변경

### 🟡 결함 2 — 모의 환경 분리 미적용

- **현재**: 모의/실전 동일 20건
- **KIS 공식**: 모의 1건/초 (실전 1/18 수준)
- **영향**: 모의 환경 테스트에서 burst 호출 시 분산 거부 → 회귀 테스트 false positive 가능성
- **fix**: `_semaphore` 를 `settings.kis_env` 분기로 동적 결정 (`vts=1` / `real=18`)

### 🟢 결함 3 — 동시 호출 간격 50ms

- **현재**: 일부 경로 `asyncio.sleep(0.05)` (스캐너 종목 폴링, donchian REST poll 등)
- **KIS 공식**: 100~150ms 권장
- **영향**: 권장값보다 짧음 — 트래픽 피크 시 분산 거부 + 재호출 노이즈 증가
- **fix**: 권장 100ms 또는 150ms 로 상향 (전체 grep 후 일괄 보정)

**우선순위**: 결함 1 > 2 > 3. 모두 별도 사이클로 분리 검토 권장.

---

## 4. 운영 진단 명령

```sql
-- 최근 24시간 KIS REST 호출 메트릭 (일일 로그 분석 기준)
SELECT
  target_date,
  metrics->'api_metrics'->>'total' AS total,
  metrics->'api_metrics'->>'http_5xx' AS http_5xx,
  metrics->'api_metrics'->>'retries' AS retries,
  metrics->'api_metrics'->>'retry_recovered' AS retry_recovered,
  metrics->'api_metrics'->>'retry_exhausted' AS retry_exhausted
FROM daily_log_reports
ORDER BY target_date DESC
LIMIT 7;

-- KIS 거부 응답 영구 로그 (Phase A1)
SELECT timestamp, message
FROM system_logs
WHERE message LIKE '[kis_rejection]%'
  AND timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC
LIMIT 50;

-- WebSocket 시세 구독 슬롯 현황 (G2)
-- curl http://localhost:8000/api/realtime/subscriptions | jq
```

---

## 5. 참조

- 본 시스템 Rate Limit 구현: `src/api/base.py::_rate_limit()`
- 재시도 + 메트릭: `src/api/CLAUDE.md` (PR-B `api_retry_recovered/exhausted`)
- WebSocket 구독 우선순위: `src/realtime/CLAUDE.md` (E1 / E2 / F1 / K)
- KIS 거부 응답 영구 저장: 메인 `CLAUDE.md` "핵심 안전 규칙" 의 Phase A1
- 에러 코드 분류: [docs/kis/error-codes.md](error-codes.md) (APBK0918 / APBK1943 / APBK3013 등)

---

## 6. KIS 차단 회피 안전망 (사이클 9, 2026-05-18)

### KIS Open API 담당자 공지 (2026-05-18)

> 무한으로 연결 접속, 종료 반복 / 데이터 구독 후 검증 없이 무한 등록/해제 반복 → IP/앱키 일시 차단 예정

본 시스템 다층 점검 결과:

| 메커니즘 | 상태 | 근거 |
|---------|------|------|
| Reconnect 백오프 | ✅ 안전 | `MAX_RECONNECT=5` + 지수 백오프 |
| F1 재연결 검증 | ✅ 안전 | 60s 1회 + `_reverify_in_progress` 중첩 방지 |
| E2 거절 응답 처리 | ✅ 안전 | `_subscriptions.discard` + 5분 `_scan_loop` 위임 |
| K stale watcher × 보조 5개 | 🔴 **위험** | 30s 주기 × 강제 임계 3 → 분당 800 unsubscribe/subscribe |

### 사이클 9 안전망 4 항목

1. **stale watcher 트래픽 완화** (`src/engine/scheduler.py`)
   - `STALE_WATCHER_INTERVAL_SECS`: 30 → **120** (분당 발화 1/4)
   - `STALE_FORCE_REREGISTER_AFTER`: 3 → **10** (20분 stale 누적 후에만 강제 재등록)
   - `STALE_FRESHNESS_SECS`: 60 보존 (5/12 사고 대응 의도)
   - 최악 시나리오 분당 트래픽 800 → 200 미만 (강제 임계 분기로 실제 1/10 이하)

2. **`QuoteSessionHealthMonitor`** (`src/services/quote_session_health.py`)
   - 보조 세션별 토큰 발급 실패 / 5xx 응답 누적 추적
   - 5회 연속 실패 또는 5분 50% 실패율 (min_calls 10) → 자동 비활성
   - DB `kis_quote_accounts.active=false` + 풀 제거 + `[quote_session_disabled]` 영구 로그
   - 메인 라벨 "main" 은 자동 비활성 절대 금지

3. **`base.py::_request_via_quote_pool` 통합**
   - 성공 → `record_success(label)` / 5xx → `record_failure(label, "http_503")` / 토큰 발급 실패 → `record_failure(label, "token_issue_fail")`

4. **`WebsocketPool.disable_quote_session(label)`**
   - 보조 세션 1개 disconnect + 풀 제거 + ticker 추적 정리
   - 메인 / 없는 라벨 / 두 번째 호출 모두 noop (idempotent)

### 운영자 가이드

자동 비활성 발생 시:
1. `system_logs` 에서 `[quote_session_disabled]` 사유 확인
2. 외부 원인 (KIS 측 장애, 토큰 만료, 계정 issue) 진단
3. Settings UI 에서 해당 보조 계좌 `active=true` 토글
4. **다음 영업일** `_boot()` (07:50) 부터 풀 재참여 (당일 즉시 재참여 미지원)

### 회귀 가드 (24 신규)
- `tests/unit/engine/test_stale_watcher_thresholds.py` 7 케이스
- `tests/unit/services/test_quote_session_health.py` 10 케이스
- `tests/unit/realtime/test_websocket_pool_disable.py` 5 케이스
- `tests/contract/test_quote_session_auto_disable.py` 4 케이스
