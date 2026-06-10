# 사이클 92 Phase 1 진단 — 07:45 우리 기동 vs 07:50 KIS API 강제 접속 중단 충돌

> **상태**: Phase 1 READ-ONLY 진단 완료. Phase 2 (Red 명세 작성) 사용자 결정 대기.
> **위급도**: **HIGH** (매매 안전성 직접 영역 — 시세 0건 = 매수/매도 hot path 완전 정지).
> **domain-expert 자문 의무**: **권고** (KIS 정책 영역 + WebSocket 4중 안전망 영역 + `TIME_BOOT` 영구 시점 변경).

---

## 1. 사용자 보고 (verbatim)

> "장 초반에 시세도 잘 들어오지 않고 전략별 감시종목 리스트도 제대로 갱신되지 않아서 강제 재기동하니까 감시종목 리스트가 제대로 생성되었어. 비정상이라는 의미지.
> 우리 매일 오전 기동이 07:45 인데 한투 open api 재기동이 07:50 이라고 하는데 관련이 있을듯해. 07:50 에 모든 기존 접속을 중단시킨다고 함."

---

## 2. 시간 상수 영속 확인 (현행)

`src/engine/scheduler.py:51-54` (코드 변경 0 확인):

| 상수 | 시각 | 동작 |
|------|------|------|
| `TIME_AUTO_START` | **07:45** | `_run_auto_start_loop` → `start()` 호출 |
| `TIME_BOOT` | **07:50** ← KIS 강제 중단 정확 일치 | `_boot()` (`boot_manager.boot()`) — `_preissue_all_tokens` + 토큰 + 잔고 + 매크로 + DB positions 복구 |
| `TIME_PRESUBSCRIBE` | 07:55 | WebSocket connect + 체결통보 구독 + presubscribe 시세 |
| `TIME_PRE_NXT_OPEN` | 08:00 | NXT 프리 진입 + 익일 청산 |

**결정적 영역**: `TIME_BOOT = 07:50` 정확히 KIS 강제 중단 시점과 일치. 우리 `_preissue_all_tokens` (`scheduler.py:1766`) 가 메인 + 보조 N 토큰을 분당 1개 한도 직렬화로 발급하며, 사용자 보고된 KIS 정책 "07:50 에 모든 기존 접속 중단" 시점에 정확히 충돌.

---

## 3. KIS 정본 검증 결과

- `docs/kis/oauth.md` — `/oauth2/tokenP` 응답 `expires_in=86400` (24h) 외 일일 강제 중단 명세 **없음**
- `docs/kis/rate-limits.md` — REST 18/s, WebSocket 41/세션, 토큰 1/min 외 일일 점검 명세 **없음**
- `docs/kis/` 25 파일 전수 검색 결과 = "07:50" / "일일 정기" / "일일 재기동" / "강제 접속 중단" / "maintenance" 키워드 **0건**
- KIS MCP 시도 = 별도 정본 검증 필요 (Phase 2 권고)
- **사용자 보고가 현재 유일한 정본 자료** — 한국투자증권 운영팀 채널 (전화/이메일/Slack KIS Developers) 으로 공식 명문 확보 의무

---

## 4. 운영 로그 점검 결과

- Supabase MCP `execute_sql` READ-ONLY = **권한 거부 (`McpError -32600`)** 6 쿼리 전수 실패
- **사용자/EC2 직접 조회 위임 의무**: 운영 EC2 SSH `~/auto_stock/` 에서 아래 SQL 직접 실행 권고 (Supabase 콘솔 SQL Editor 또는 `psql`)

```sql
-- 1. 오늘 07:45~09:30 ERROR/WARNING 전수
SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul','HH24:MI:SS') AS t_kst, log_level, LEFT(message,200) AS msg
FROM system_logs
WHERE timestamp >= '2026-06-10T07:45:00+09:00' AND timestamp <= '2026-06-10T09:30:00+09:00'
  AND log_level IN ('ERROR','WARNING','CRITICAL')
ORDER BY timestamp ASC LIMIT 100;

-- 2. WebSocket 끊김/재연결 영역
SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul','HH24:MI:SS') AS t_kst, log_level, LEFT(message,300) AS msg
FROM system_logs
WHERE timestamp >= '2026-06-10T07:45:00+09:00' AND timestamp <= '2026-06-10T09:30:00+09:00'
  AND (message ILIKE '%websocket%' OR message ILIKE '%[ws_%' OR message ILIKE '%OPSP%'
       OR message ILIKE '%subscribe%' OR message ILIKE '%reconnect%' OR message ILIKE '%재연결%' OR message ILIKE '%끊김%')
ORDER BY timestamp ASC LIMIT 150;

-- 3. _boot + 토큰 발급 영역
SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul','HH24:MI:SS') AS t_kst, log_level, LEFT(message,300) AS msg
FROM system_logs
WHERE timestamp >= '2026-06-10T07:45:00+09:00' AND timestamp <= '2026-06-10T09:30:00+09:00'
  AND (message ILIKE '%_boot%' OR message ILIKE '%token%' OR message ILIKE '%preissue%'
       OR message ILIKE '%[oauth%' OR message ILIKE '%인증%' OR message ILIKE '%발급%')
ORDER BY timestamp ASC LIMIT 100;

-- 4. 사용자 강제 재기동 시점 추정
SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul','HH24:MI:SS') AS t_kst, log_level, LEFT(message,300) AS msg
FROM system_logs
WHERE timestamp >= '2026-06-10T07:00:00+09:00' AND timestamp <= '2026-06-10T10:30:00+09:00'
  AND (message ILIKE '%start%' OR message ILIKE '%boot%' OR message ILIKE '%shutdown%'
       OR message ILIKE '%lifespan%' OR message ILIKE '%스케줄러%' OR message ILIKE '%자동매매%' OR message ILIKE '%기동%')
ORDER BY timestamp ASC LIMIT 200;
```

**확인 의무 패턴 (운영자 수동 점검)**:
- `최대 재연결 횟수 초과, 종료` ERROR 1건 + 시각 (`websocket.py:209`)
- `WebSocket 끊김 (...), N/5 재연결 대기 X.Xs` WARNING 시퀀스 5건
- `[silent_inactive_force_reconnect]` ERROR — 사이클 24 / 29-R2 세션 silent inactive 자동 reconnect 발화 여부
- `[boot_preissue]` 토큰 발급 실패 ERROR (`scheduler.py:1780/1786/1796`)

---

## 5. 결함 chain 가설 (HIGH 위급도)

### 5.1 결정적 발견 — WebSocket `MAX_RECONNECT=5` 영구 종료 위험

**`src/realtime/websocket.py:30,174,207-210`** 검증:

```python
MAX_RECONNECT = 5
BACKOFF_BASE = 1.0
# ...
while self._running and self._reconnect_count <= MAX_RECONNECT:
    # ...
    except (websockets.ConnectionClosed, ...) as e:
        self._reconnect_count += 1
        if self._reconnect_count > MAX_RECONNECT:
            logger.error("최대 재연결 횟수 초과, 종료")
            break
        wait = BACKOFF_BASE * (2 ** (self._reconnect_count - 1))  # 1 + 2 + 4 + 8 + 16 = 31s
```

**총 재연결 누적 = 1 + 2 + 4 + 8 + 16 = 31초** → `MAX_RECONNECT=5` 초과 시 **WebSocket loop 영구 종료** (`break` → `self._ws = None`).

### 5.2 chain 추정

1. **07:45** `_run_auto_start_loop` → `start()` 호출
2. **07:50** `_boot()` 진입 → `_preissue_all_tokens` 발화 (메인 + 보조 N 토큰 분당 1개 직렬화 발급)
3. **07:50 KIS 강제 중단** → KIS 측 REST/WS 접속 일괄 끊김
4. **07:50:01~07:55** 우리 토큰 발급 + DB positions 복구 + 매크로 fetch = 정상 진행 가능 (KIS REST 일시 503 → `_request` graceful 흡수)
5. **07:55** `connect()` (WebSocket) 호출 — **KIS 재기동 중이면 즉시 `ConnectionClosed` 또는 `OSError`**
6. **07:55:01~07:55:32** 5회 재시도 (1+2+4+8+16=31초) — KIS 재기동 30초 이상 지속이면 모두 실패
7. **07:55:32** `최대 재연결 횟수 초과, 종료` ERROR → **WS 영구 종료** → 시세 0건 + 사용자 보고 시나리오 정확히 일치
8. **8:00 NXT 프리** 진입했지만 시세 미수신 → `_confirm_breakout_open_prices` 폴링 timeout → `_pending_next_day_clear` 보류
9. **9:00 KRX 메인** 진입 / **9:30 모멘텀 스캔** → 시세 미수신 → 매수 후보 풀 텅 빔 / 매도 hot path 위험
10. **사용자 강제 재기동** = `_running=False` → re-entry → `connect()` 재호출 → KIS 정상 상태 → 정상 작동

### 5.3 4중 안전망 영역 한계

WebSocket 4중 안전망 (F1 + `_scan_loop` + K stale watcher + `_resubscribe_stale_priority`) 은 **`self._ws is not None`** 전제 작동. `_ws=None` 영구 종료 후엔:
- F1 (`_verify_subscriptions_after_reconnect`) = `connect()` 내부 task → 발화 불가
- `_scan_loop` (5분, `scheduler._scan_loop`) = `subscribe_filtered_stocks` 호출하나 `_ws=None` 이면 `_send_subscribe` 호출 자체 graceful skip
- K stale watcher (120s, `stale_watcher_core.check_and_resubscribe_stale`) = `kis_ws_pool.unsubscribe_in_pool` 호출하나 세션 dead 면 noop
- `_resubscribe_stale_priority` (5분, sub-loop of `_scan_loop`) = 동일 한계

**결과**: 4중 안전망 모두 무력. 사용자 수동 재기동만 유일한 회복 경로.

---

## 6. 사용자 결정 의제 (Q28~Q31)

### Q28 (HIGH 핵심) — `TIME_BOOT` 시점 영구 이동

| 옵션 | 시점 | 장점 | 단점 |
|------|------|------|------|
| **A 권고** | `TIME_BOOT = time(7, 55)` (5분 이동) | KIS 강제 중단 *후* 안전 마진 / `TIME_PRESUBSCRIBE` 와 동일 시각 통합 가능 | 다른 시간 상수 (presubscribe / pre_nxt_open) 영향 검토 의무 |
| B | `TIME_BOOT = time(7, 51)` (1분 이동) | 최소 침습 / 영업 시작 시간 영향 최소 | KIS 강제 중단 진행 중일 가능성 (1분 마진 부족) |
| C | `TIME_BOOT = time(8, 0)` (10분 이동, NXT 시작과 동행) | NXT 프리 진입 직전 안전 보장 | `_preissue_all_tokens` (메인+보조 N × 60s 직렬화) 가 NXT 매매 시작 시점까지 미완 위험 |
| D | `TIME_BOOT` 영속 + 자동 재기동 영구 가드 (Q30 답) | 시점 변경 0 + 영구 가드 | 자동 재기동 영역 추가 복잡도 + 도입 회귀 위험 |
| E | **A + D 결합 (강력 권고)** | 시점 이동 + 자동 재기동 영구 가드 (silent 결함 영구 차단) | 도입 회귀 위험 (단, 회귀 가드 충분히 작성 가능) |

### Q29 (MEDIUM) — `TIME_AUTO_START` 영향

| 옵션 | 채택 | 비고 |
|------|------|------|
| **A 권고** | `TIME_AUTO_START = time(7, 45)` 영속 + `TIME_BOOT` 만 이동 | `run_daily()` 기상은 KIS 영향 0 (Python loop) — 변경 불요 |
| B | `TIME_AUTO_START` 도 동행 이동 (`time(7, 50)` 또는 `time(7, 55)`) | scheduler entrypoint 영역 변경 — 회귀 가드 영역 추가 |

### Q30 (HIGH) — Q28 옵션 D/E 채택 시 자동 재기동 영역

| 옵션 | 트리거 | 비고 |
|------|--------|------|
| **A 권고** | `MAX_RECONNECT=5` 도달 → `최대 재연결 횟수 초과, 종료` 발화 시 자동 `start()` 재호출 (idempotent 보장 의무) | 최소 침습 + 사이클 79/80 task lifecycle 패턴 답습 |
| B | `MAX_RECONNECT` 영역 영구 확장 (예: 5 → 60 + 지수 backoff cap 60s) | 31s → 약 1h 영구 재시도 — KIS 강제 중단 1h 시나리오 흡수 |
| C | 시간 기반 (07:50:00~07:55:00 영역 한정 재시도 무한) | 영역 제한적 + 정확한 KIS 재기동 시점 시나리오 한정 |
| D | A + B 결합 (안전 마진) | 최대 영구 회복력 + 자동 재기동 영역 |

### Q31 (LOW) — KIS 공식 명문 확보 의무

| 옵션 | 채택 | 비고 |
|------|------|------|
| **A 권고** | 한국투자증권 운영팀 (KIS Developers 채널 / 이메일 / 전화) 공식 문의 의무 | KIS 정책 = "07:50 강제 접속 중단" 정본 명문 확보 → `docs/kis/` 영구 기록 |
| B | 시정 영역 적용 + KIS 명문 확보는 별도 카드 인계 | 시정 우선 + 명문 후행 |

---

## 7. 회귀 가드 매트릭스 추정 (Phase 2 — tdd-engineer 발주 후)

### Q28 옵션 A (TIME_BOOT 5분 이동) 채택 시:

- **G-TIME-1** `TIME_BOOT == time(7, 55)` (상수 영속 AST 정적)
- **G-TIME-2** `TIME_BOOT >= TIME_AUTO_START + 10분` (KIS 강제 중단 안전 마진 AST 정적)
- **G-TIME-3** `TIME_BOOT == TIME_PRESUBSCRIBE` 또는 `TIME_BOOT < TIME_PRE_NXT_OPEN` 검증
- **G-TIME-4** `architecture.md` 시퀀스 다이어그램 동행 갱신 (07:50 → 07:55)
- **G-TIME-5** `docs/kis/rate-limits.md:196` "다음 영업일 `_boot()` (07:50)" → "07:55" 동행 갱신
- **G-TIME-6** `_workspace/00_leader_trading_rules.md` 사이클 6 / 7-D / 23 답습 영역 영향 검토 (12 위치)

### Q30 옵션 A (자동 재기동 영역) 채택 시:

- **G-REC-1** `MAX_RECONNECT` 도달 시 `start()` idempotent 재호출 (사이클 13-E-2 task lifecycle 답습)
- **G-REC-2** 재시도 cooldown 가드 (`asyncio.sleep(N)` — 권고 60s 영구 마진, KIS 재기동 완료 보장)
- **G-REC-3** 시간당 자동 재기동 cap (권고 3회 — LMS / 앱키 정지 위험 차단, 사이클 24 답습)
- **G-REC-4** `_reset_daily_state()` 동행 가드 (중복 reset 차단)
- **G-REC-5** 자동 재기동 발화 시 ERROR `[ws_max_reconnect_exceeded_auto_restart] count=N/3` 운영 가시화

### Q30 옵션 B (MAX_RECONNECT 영구 확장) 채택 시:

- **G-MAX-1** `MAX_RECONNECT = 60` 또는 `INF` 영역 영속
- **G-MAX-2** `BACKOFF_BASE` cap 60s (`min(BACKOFF_BASE * 2**(n-1), 60.0)`)
- **G-MAX-3** 누적 재시도 시간 안전 마진 AST 정적 (예: ≥1h)

---

## 8. 진행 가이드

1. **사용자 결정 의제 (Q28~Q31) 회신 대기** — 영구 시점 변경 + 자동 재기동 영역은 정책적 결정 영역
2. **운영자 의무 (병렬)**: §4 SQL 6 쿼리 직접 실행 → 결과 회신 (구체 시각 + 패턴 확정 + 5.2 chain 가설 검증)
3. **KIS 공식 명문 확보 (Q31 A 권고)**: 한국투자증권 운영팀 공식 문의 — "07:50 강제 접속 중단" 정확한 명세 + 지속 시간 + 영향 범위
4. **결정 후 Phase 2 발주**:
   - team-leader 명세 분해 → tdd-engineer Red 명세 → backend-dev Green 구현 → tester 회귀 검증
   - domain-expert 자문 권고 (HIGH + 매매 안전성 직접 영역 + 영구 시점 변경 = `domain-consult` 스킬 의무)
5. **운영 시간 가드**: 현재 09:00+ KRX 메인 진입 영역 → 시정 push 는 **NXT 애프터 (15:30+)** 또는 **익일 07:45 *전*** 의무 (CLAUDE.md "운영 가이드" 영속)

---

## 9. 사이클 81/91 답습 패턴

- **사이클 81** (silent 결함 영구 차단 19 회 누적 + 옵션 A 패턴 20 연속) = 단일 근본 원인 + 1 줄 시정 + AST 영구 가드 + 회귀 가드 ~17 케이스
- **사이클 91** (가정 채택) = 본 사이클 직전 운영 진단 영역
- **사이클 92** = silent 결함 영구 차단 20 회 후보 + 옵션 A 패턴 21 연속 후보

**도메인 자문 권고**: domain-expert 자문 의무 (KIS 정책 영역 + WebSocket 4중 안전망 영역 + `TIME_BOOT` 영구 시점 변경 + 자동 재기동 영역).
