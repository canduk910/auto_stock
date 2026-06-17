# 사이클 158 Red 명세 — 3 결함 통합 시정

운영 사례: 2026-06-17 08:13~08:50 KST. EC2 재시작 직후 (사이클 157 배포 시점 08:08 KST 직후) 발생.

## Q1 — momentum 익일 청산 로그 폭주 (MEDIUM, 신규 silent)

### 운영 사례
- 08:13:36 [momentum] 익일 즉시 청산: 씨에스윈드(112610) 갭률 8.1% (시가: 61400, 매수가: 56800)
- 08:13:37 KIS 거부 APBK0918 (프리마켓 시장가 매매 불가)
- 08:14:06 [next_day_clear_deferred] ticker=112610 (사이클 54 정상)
- 08:14:06 ~ 08:14:31+ 매초 동일 INFO 발화 (~26회/30초)

### 근본 원인
- `SellRejectionTracker.is_blocked()` 가 KIS 호출은 차단 (정상)
- 그러나 `momentum.check_exit_signal` line 161 `logger.info("익일 즉시 청산: ...")` 영역에 DailyEmitCap 없음
- 사이클 19 `_selling` 가드 = `execute_sell` 호출 차단만. 신호 평가 미차단
- 매 tick 마다 `check_exit_signal` → `Signal.NEXT_DAY_CLEAR` 반환 → logger 발화

### 시정
- `momentum.py` 모듈 전역 `_next_day_clear_logged_today: DailyEmitCap[str]` (ticker 단위)
- `check_exit_signal` 익일 청산 분기 (line 159-164, gap_rate < gap_threshold)에서 `should_emit(ticker)` 검사 후 logger.info
- `_reset_daily_state` 동행 reset (사이클 31 R6 답습)

### 회귀 가드 (7 케이스)
- G-158-Q1-1: 모듈 전역 `_next_day_clear_logged_today: DailyEmitCap[str]` 정의
- G-158-Q1-2: `check_exit_signal` 익일 청산 분기 진입 시 should_emit 검사
- G-158-Q1-3: 동일 ticker 동일 일자 logger.info 1회 cap (10 tick × 동일 ticker → 1 log)
- G-158-Q1-4: 다른 ticker 는 cap 영향 없음 (격리 검증)
- G-158-Q1-5: `_reset_daily_state` (또는 모듈 reset 헬퍼) 동행 reset
- G-158-Q1-6: cap이 있어도 Signal.NEXT_DAY_CLEAR 반환은 영속 (KIS 호출 trigger 보존 — execute_sell 차단은 SellRejectionTracker 책임)
- G-158-Q1-7: 트레일링 분기는 cap 영향 영역 외 (변경 0)

## Q2 — stock_master 0건 prepare 자동 재시도 hook (MEDIUM)

### 운영 사례
- 08:13:14 VB 유니버스 0/0종목 (stock_master 0건)
- 08:13:14 LTV/donchian/BFB 동일 0건
- 08:13:15 VCP만 77/77종목 정상
- 08:13:31 "돌파 유니버스 비어있어 prepare 재실행" → 재시도도 0건
- 08:16:39 [full_universe_load_summary] total=2768 elapsed_ms=188243 (3분 8초)

### 근본 원인
- `_full_universe_load_task_loop` start() 직후 즉시 1회 + while 루프 (사이클 106)
- 1회 실행 ~3분 소요
- `_boot()` line 71-75 prepare() 호출이 `_full_universe_load_once` 완료 *전* 발생 race
- 결과 = stock_master 비어있는 상태로 prepare → 0건

### 시정 (옵션 B)
- 5 전략 (momentum 제외) prepare 영역: stock_master 0건 시 자동 재시도 hook
- 재시도 횟수 cap 3회 + sleep 30초 (총 90초)
- `_full_universe_load_once` 완료 대기 또는 retry 시점 list_by_filter 재호출

### 회귀 가드 (5 케이스)
- G-158-Q2-1: VB prepare 영역 0건 시 자동 재시도 hook (사이클 156 nxt_tradable 제거 영속, list_by_filter 호출 재실행)
- G-158-Q2-2: 재시도 횟수 cap = 3회
- G-158-Q2-3: 재시도 간격 sleep 30초 (asyncio.sleep mock 검증)
- G-158-Q2-4: 정상 (stock_master ≥1건) 케이스 재시도 0회 (회귀 보존)
- G-158-Q2-5: momentum 영역 변경 0 (실시간 본질, prepare empty stub 영속)

## Q3 — task 발화 stagger (LOW)

### 운영 사례
- 08:13:14 ~ 08:16:39 다수 ConnectionTerminated/Broken pipe/Connection reset
- 4 task (full_universe / basics / daily / master) 동시 발화 → Supabase HTTP/2 풀 race

### 시정 (옵션 C — stagger)
- start() 후 task별 stagger 적용:
  - full_universe = 0초 (즉시)
  - basics = 60초 후 (asyncio.sleep before once 실행)
  - daily = 120초 후
  - master = 180초 후
- task_loop_helper의 `immediate_first_run` 영역 + 신규 `initial_delay_secs` 인자 옵션

### 회귀 가드 (3 케이스)
- G-158-Q3-1: task_loop_helper에 `initial_delay_secs` 인자 신규 (default 0 = 회귀 보존)
- G-158-Q3-2: scheduler 4 task 발화 stagger 인자 명시 (0/60/120/180)
- G-158-Q3-3: 사이클 152 `_wait_until` hotfix 영속 (변경 0)

## 안전성 가드 (HIGH 4)

- G-158-SAFETY-1 (HIGH): risk.on_tick / order_engine / realtime / auth 변경 0
- G-158-SAFETY-2 (HIGH): 매수 진입 전 영역 한정 (Q2/Q3, 사이클 38 명문화)
- G-158-SAFETY-3 (HIGH): Q1 시정은 logger 영역만 — Signal.NEXT_DAY_CLEAR 반환 영속 (사이클 32 R4 보유 절대 보호)
- G-158-SAFETY-4 (HIGH): 사이클 54 `_strategy_exchange_async` 변경 0

## 영속 의무

- 사이클 19 `_selling` 가드 (Q1 logger 영역만)
- 사이클 31 R6 / 57 V-1 DailyEmitCap 패턴
- 사이클 32 R4 보유/익일청산 절대 보호
- 사이클 38 명문화 (매수 진입 전 한정)
- 사이클 106 lifecycle race 차단 패턴
- 사이클 134 task_loop_helper 영속
- 사이클 152 `_wait_until` hotfix
- 사이클 157 hook 통합 영속
