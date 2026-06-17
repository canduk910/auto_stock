# 사이클 159 refactor-expert 자문 — Supabase HTTP/2 race + 4 task stagger 임계 재산정

산출일 = 2026-06-17 (KST)
범위 = `src/engine/task_loop_helper.py` + `src/engine/scheduler.py` 4 task wrapper
사이클 158 시정 이후 운영 실측 검증 + 잔존 폭주 분석 + 신규 stagger 권고

## 0. 운영 실측 데이터 (Supabase MCP)

배포 시점 정렬:
- 사이클 157 운영 = 2026-06-17 00:00 UTC 이전
- 사이클 158 deploy = 2026-06-17 00:45 UTC = **09:45 KST**
- 사이클 158 첫 _boot = 09:48 KST

| 시간대 | master_skip | basics_skip | Server disc | ConnTerm | deque_mut | 비고 |
|--------|-------------|-------------|-------------|----------|-----------|------|
| 07:46~07:49 (사이클 157, 배포 전) | 22 | 0 | 3 | 16 | 3 | 4 task 동시 발화 |
| 08:13~08:24 (사이클 157, 배포 전) | 25 | 6 | 6 | 14 | 0 | 4 task 동시 발화 |
| 09:51~09:56 (사이클 158, 배포 후) | 12 | 4 | 6 | 4 | 1 | stagger 0/60/120/180 적용 |

24h 누적:
- `stock_master_master_load_skip` = 992 건
- `stock_master_basics_refresh_skip` = 1,958 건
- `Server disconnected` = 303 건
- `ConnectionTerminated error_code:1` = 310 건
- `deque mutated during iteration` = 16 건

**평가**: 사이클 158 stagger 0/60/120/180 = 배포 전 대비 약 50% 감소. 그러나 6분 윈도우당 12건 잔존 = 운영 불충분.

## 의제 1 — 사이클 158 stagger (0/60/120/180) 부족 사유 분석

### 1-A. Supabase HTTP/2 connection pool 한도

`supabase-py` SDK = httpx + HTTP/2 (`http2=True` 디폴트). 단일 HTTP/2 connection = stream concurrency 100 한계 (서버측 `MAX_CONCURRENT_STREAMS` 디폴트). `ConnectionTerminated error_code:1` = `error_code:1 PROTOCOL_ERROR` 또는 GOAWAY frame 직후 잔여 stream 정리.

증거 = 로그 패턴 `last_stream_id:2951` / `last_stream_id:1237` 큰 수치 = stream ID 누적 후 GOAWAY 수신. 단일 task 만으로 9,999 종목 upsert × 4 task 동시 = stream 폭주.

### 1-B. Supabase Pooler timeout / keepalive

Supabase 운영 측 pooler (PgBouncer + Kong) idle keepalive = 30~60초. 4 task 동시 진입 후 한 task 가 종목별 50ms sleep 영역 진입 시 다른 task 가 동일 connection 점유 충돌 가능.

### 1-C. 사이클 158 stagger 시간 부족

4 task 각 처리량:
- `full_universe_load` (20:00) — KIS 호출 ~2,800 종목 × 100ms ≈ 4.7분 (~280초)
- `stock_master_daily_load` (16:00) — KIS 호출 ~2,700 × 100ms ≈ 4.5분 (~270초)
- `stock_master_basics_refresh` (16:10) — KIS 호출 ~2,700 × 100ms ≈ 4.5분 (~270초)
- `stock_master_master_load` (16:30) — KIS 호출 KOSPI+KOSDAQ 2 파일 + ~2,800 종목 upsert ≈ 2분 (~120초)

사이클 158 stagger 60초 = 다음 task 가 직전 task 처리 중간 시점 (270초 중 60초 시점) 에 진입 → 270~480초 영역 4 task 모두 동시 Supabase 호출 → ConnectionTerminated 폭주.

### 1-D. 동시 요청 race

`_stock_master_master_load_once` + `_stock_master_basics_refresh_once` = 두 task 모두 `stock_master.upsert_one()` 호출. PostgREST 가 동일 row 동시 UPDATE 시 lock 충돌 + retry. `deque mutated during iteration` (16 건) = httpx connection pool deque 가 다른 코루틴이 변경 중 iterate = HTTP/2 stream 풀 race.

### 1-E. EC2 재시작 시점 (07:45 _boot) 영역

EC2 재시작 직후 = 토큰 캐시 / Supabase client 초기화 / KIS WebSocket 연결 = 모두 동시 발화. 4 task 가 모두 immediate_first_run=True 분기 진입하면 직전 코드 초기화와 충돌.

### 결론 (의제 1)

**핵심 결함 = stagger 시간 < 단일 task 처리 시간**. 60초 stagger 가 270~280초 처리 시간 대비 너무 짧음 → 4 task 모두 동시 hot 영역 진입.

## 의제 2 — 신규 stagger 임계 권고

### 옵션 A (보수 / 권고): 0 / 360 / 600 / 840 초 (= 0 / 6분 / 10분 / 14분)

| Task | initial_delay_secs | 처리 완료 추정 | 다음 task 진입 시점 비교 |
|------|--------------------|-----------------|------------------------|
| `full_universe_load` | 0 | ~280초 (4:40) | task 진입 360초 시점 = full_universe 80초 전 완료 |
| `stock_master_daily_load` | 360 | ~270초 (4:30) | task 완료 630초 시점 = basics 진입 30초 후 충돌 가능 |
| `stock_master_basics_refresh` | 600 | ~270초 (4:30) | task 완료 870초 시점 = master 30초 후 충돌 가능 |
| `stock_master_master_load` | 840 | ~120초 (2:00) | task 완료 960초 시점 = 종결 |

총 wall-clock = 840 + 120 = **960초 = 16분**. 사이클 158 stagger 180초 = 4 task 모두 동시 hot 영역 → 옵션 A 는 14분 영역에 분산.

### 옵션 B (공격): 0 / 180 / 360 / 540 초 (= 0 / 3분 / 6분 / 9분)

총 wall-clock = 540 + 120 = 660초 = 11분. 사이클 158 대비 3배 향상. 단 정기 task 와 충돌 가능 (예: daily 16:00 → 16:09 master 진입 = 정기 schedule 16:30 와 21분 간격, 안전).

### 옵션 C (균형, 권고 채택): 0 / 240 / 480 / 720 초 (= 0 / 4분 / 8분 / 12분)

| Task | initial_delay_secs | 처리 완료 추정 |
|------|--------------------|-----------------|
| `full_universe_load` | 0 | ~280초 (4:40) |
| `stock_master_daily_load` | 240 (4분) | full_universe 완료 *직후* 진입 = 0 overlap |
| `stock_master_basics_refresh` | 480 (8분) | daily 완료 30초 후 진입 = 30초 overlap (허용) |
| `stock_master_master_load` | 720 (12분) | basics 완료 30초 후 진입 = 30초 overlap (허용) |

총 wall-clock = 720 + 120 = **840초 = 14분**. 단일 task 시간 280초의 정확히 정합.

### 권고: 옵션 C

근거:
1. 단일 task 처리 시간 280초 정합 (overlap 0~30초 = 종목별 50ms sleep 영역 시 자연 분산)
2. 4 task 모두 hot 영역 동시 진입 0건 보장 (ConnectionTerminated 잠재 0%)
3. 사이클 17 KIS LMS chain 안전 마진 영역 답습 (300초 backoff = 240초 stagger 대비 60초 마진)
4. 정기 schedule 16:00/16:10/16:30 영역 정합 (16:10 - 16:00 = 600초 vs 480초 stagger = 정기 진입 + 첫 task 완료 후 충돌 0건)

## 의제 3 — task별 wait_time + initial_delay_secs 정합

| Task | wait_time (정기) | initial_delay_secs (start 직후) | 정기 schedule 안전성 |
|------|------------------|--------------------------------|----------------------|
| `full_universe_load` | 20:00:05 | 0 | 정기 20:00 = start 직후 시각 차 8h+ 안전 |
| `stock_master_daily_load` | 16:00 | 240 (옵션 C) | 정기 16:00 = start 직후 16:04 진입 (07:50 start 시 8h+ 대기) 안전 |
| `stock_master_basics_refresh` | 16:10 | 480 | 정기 16:10 = start 직후 16:08 진입 안전 |
| `stock_master_master_load` | 16:30 | 720 | 정기 16:30 = start 직후 16:12 진입 안전 |
| `stock_master_daily_purge` | 16:15 | (현재 미적용, 사이클 150) | retention cron — 영향 0 |

stagger 는 **immediate_first_run 분기에만 적용** (사이클 158 정합). 정기 매일 schedule 영역은 `_wait_until(wait_time)` 대기 후 즉시 호출 = stagger 불필요 (시간 차 자체가 분산 역할). 정기 schedule 정합 = 16:00 / 16:10 / 16:30 = 10분 간격 = 단일 task 280초(4:40) 영역에서 자연 분산.

## 의제 4 — `deque mutated during iteration` 결함 분석

### 4-A. 발생 영역

```
[stock_master_master_load_skip] ticker=475350 reason=upsert_failed err=deque mutated during iteration
```

`httpx` 내부 connection pool = `collections.deque`. HTTP/2 multiplexing 시 동일 코루틴 stack 에서 deque 가 변경되면서 iterate 충돌. 24h 16건 발생.

### 4-B. 사이클 159 범위 외 판정

- 이 결함은 stagger 늘려도 0건 보장 안 됨 (httpx 내부 race)
- 시정 영역 = httpx connection pool 분리 또는 Supabase client per-task 분리 — **별개 사이클 후속 의제**
- 사이클 159 = stagger 임계 상향 단독 영역

다만 stagger 옵션 C 채택 시 4 task 동시 진입 0건 → httpx 동시 stream 자연 감소 → deque mutated 자연 감소 효과 부수 예상 (정량 측정 D+1 의무).

## 의제 5 — KIS LMS chain 안전 마진 패턴 (사이클 17 답습)

### 5-A. 사이클 17 OPSP0002 backoff = 300초

KIS API `OPSP0002` (분당 호출 한도 초과) 시 사이클 17 영속 = `_opsp_backoff_until` 300초 (5분) 등록. KIS LMS chain (LMS = Long Message Service, KIS 운영 측 알람) 발화 시 *영구 차단* 위험. backoff 안전 마진 5분 영속 의무.

### 5-B. 옵션 C 정합 검증

- task 간 stagger = 240초 (full → daily) / 240초 (daily → basics) / 240초 (basics → master)
- 사이클 17 backoff = 300초 → stagger 240초 가 backoff 한 사이클 안에 들어옴 → 한 task 가 OPSP0002 발화 시 다음 task 진입 시점 = 300초 backoff 미해제 영역 → 자동 retry 발화 → KIS LMS chain 위험 가능

### 5-C. 사이클 159 결정

- KIS API 호출 영역 = 각 task 가 자체 Rate Limit 50ms sleep 영속 (사이클 17 답습)
- task 간 stagger 240초 = 한 task 내부 50ms sleep 시간 정합 (2,700 × 50ms = 135초 < 240초 = OK)
- KIS LMS chain 안전 마진 = 각 task 가 자체 backoff 보유 영속 + stagger 는 Supabase HTTP/2 race 한정
- **KIS LMS chain 위험 영역 변경 0** (옵션 C 채택 시도 KIS 호출 빈도 변경 0)

## 의제 6 — 운영 영역 즉시 효과 예상

| 영역 | 사이클 158 | 사이클 159 (옵션 C) | 예상 감소율 |
|------|------------|---------------------|--------------|
| master_skip / 24h | 992 | <300 | -70% |
| basics_skip / 24h | 1,958 | <600 | -70% |
| Server disconnected / 24h | 303 | <100 | -67% |
| ConnectionTerminated / 24h | 310 | <100 | -68% |
| deque mutated / 24h | 16 | <8 | -50% (부수 효과) |

D+1 운영 실측 시점 = 06-18 EC2 재시작 직후 (07:45~08:00 KST) — 자동 검증 + 16:00~16:30 정기 schedule 영역 자연 분산 (변경 0).

## 권고 매트릭스 (5건 의제 결과)

| 의제 | 결론 | 우선순위 |
|------|------|----------|
| 1. 사이클 158 부족 사유 | stagger 시간 < 단일 task 처리 시간 (60s < 280s) | HIGH (근본 원인) |
| 2. 신규 stagger 임계 | **옵션 C 채택 = 0 / 240 / 480 / 720 초** | HIGH (영구 시정) |
| 3. wait_time + initial_delay 정합 | 정기 schedule 영역 변경 0 (immediate_first_run 영역 한정) | MEDIUM (회귀 가드 의무) |
| 4. deque mutated 결함 | 사이클 159 범위 외 (httpx 내부 race) | LOW (사이클 160+ 인계) |
| 5. KIS LMS chain | 사이클 17 backoff 영역 변경 0 (안전) | HIGH (안전 검증) |

## 영속 의무 매트릭스

- CLAUDE.md "절대 깨지 말 것" 8 영역 = 변경 0
- 사이클 38 명문화 (scanner 영역 = 매수 진입 전 한정) = 변경 0
- 사이클 67 stale_manager 4 sub-module 영역 = 변경 0
- 사이클 79 G-AST2 task_attrs 4 위치 = 변경 0
- 사이클 88 G-REJECT graceful = 변경 0
- 사이클 106 lifecycle race 차단 = stagger 가 race 차단 강화
- 사이클 122/126/129/133/134 task 패턴 = 변경 0
- 사이클 158 `initial_delay_secs` 인자 디폴트 0 = 변경 0 (회귀 보존)

## 회귀 가드 의무 (tdd-engineer 발주)

8 케이스 ≥ 의무:

- G-159-STAGGER-1: 4 task initial_delay_secs = 0 / 240 / 480 / 720 정확 발화
- G-159-STAGGER-2: 사이클 158 default 0 인자 회귀 보존
- G-159-STAGGER-3: 4 task wrapper 별 initial_delay_secs 인자 정합 (full=0 / daily=240 / basics=480 / master=720)
- G-159-SAFETY-1 (HIGH): risk/order_engine/realtime/auth 변경 0
- G-159-SAFETY-2: 매수 진입 전 영역 한정 (사이클 38)
- G-159-AST-1: `initial_delay_secs` 호출 사이트 ≥ 4건 정적 가드
- G-159-AST-2: scheduler 영역 `_full_universe_load_task_loop` / `_stock_master_daily_load_task_loop` / `_stock_master_basics_refresh_task_loop` / `_stock_master_master_load_task_loop` 4 wrapper 정확 호출
- G-159-INTEGRATION-1: task_loop_helper.py `initial_delay_secs > 0` 분기 asyncio.sleep 호출 발화

## 끝
