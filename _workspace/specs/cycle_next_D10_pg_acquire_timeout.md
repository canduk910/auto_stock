# D10 작업 구성 — asyncpg 풀 `acquire()` 타임아웃 (cycle239 후속 E, 주중 별도 사이클)

> 사용자 결정 2026-09-05: "나머지 D 제안은 권고안대로" → 권고 = 주중 별도 사이클(호출자 전수 + 뮤테이션), 8영역 승인 동반. 이 문서는 착수용 명세 초안이다.

## 1. 사실
- `src/db/pg.py` 풀 생성은 `command_timeout=30.0`(문장 실행 타임아웃)과 `max_inactive_connection_lifetime=300.0` 만 두고, **커넥션 획득 대기(`_pool.acquire()`)에는 타임아웃이 없다**(`fetch/fetchrow/fetchval/execute/executemany` 5곳, `pg.py:128~162`). 풀이 고갈되면 모든 DB 호출이 무한 대기한다 — cycle250 이 계좌 위험 감시에 300s 타임아웃을 씌워 막은 hang 의 공통 뿌리.
- `_with_retry` 는 읽기 3함수만 연결 계열 예외에 1회 재시도한다(`_RETRY_EXCEPTIONS`). 쓰기 2함수는 멱등 우려로 재시도 없음.

## 2. 목표
- `acquire(timeout=T)` 로 무한 대기를 예외(`asyncio.TimeoutError`)로 바꾼다. T 후보 = 30s(문장 타임아웃과 동일) — 정상 부하에서 acquire 는 ms 단위라 오탐 0 에 가깝다.
- 예외는 각 호출자의 기존 `except Exception` 경로(fire-and-forget 로깅·graceful)로 흡수된다. **무한 대기보다 나쁜 경우는 없는지** 호출자 전수로 확인하는 것이 이 사이클의 본체다.

## 3. 호출자 전수 (착수 시 갱신)
- `grep -rn "pg\.\(fetch\|fetchrow\|fetchval\|execute\|executemany\)(" src | wc -l` 로 목록화. 8영역 호출자(order_engine `insert_trade`·positions 저장, risk.py 손절 기록 등)는 **동작 변경 없음**(예외 타입만 추가)이지만 실패 모드가 "무한 대기 → 예외" 로 바뀌므로 승인 대상으로 분류한다.
- 각 호출자를 3분류: (a) 이미 `except Exception` 흡수 — 변경 0 (b) 예외가 상위 태스크로 전파 — 태스크 생존 여부 확인(`[callback_exception]`·done_callback 유무) (c) 트랜잭션/순서 의존 — 부분 실패 시 정합성 검토.

## 4. 설계
- `pg.py` 에 `_ACQUIRE_TIMEOUT_SECS = 30.0` 상수 + 5곳 `acquire(timeout=_ACQUIRE_TIMEOUT_SECS)`. `_RETRY_EXCEPTIONS` 에 `asyncio.TimeoutError` 를 넣을지 결정(넣으면 읽기 3함수는 1회 재시도 → 최악 60s; 넣지 않으면 즉시 실패). 권고 = 넣지 않음(풀 고갈은 재시도로 풀리지 않는다) + `[pg_acquire_timeout] op= waited=` WARNING 1회/일.
- 관측: `get_stats()` 류에 풀 사용량(`_pool.get_size()/get_idle_size()`)을 노출해 20:10 리포트 metrics 에 병기 → 고갈 징후를 사전에 본다.
- fail-open 원칙: 타임아웃 예외는 호출자 규약대로 흡수되며, 매매 엔진의 in-memory 상태(positions 등)는 DB 실패와 독립이다(기존 계약).

## 5. 검증
- 단위: acquire 가 T 초과 시 TimeoutError, 정상 시 무영향(차분 1,000 호출), 상수 리터럴 1곳(AST), 재시도 예외 집합 불변.
- 통합(pg_harness): 풀 size=1 에서 커넥션을 점유한 채 두 번째 호출이 T 뒤 예외로 끝나고 풀이 누수 없이 회수됨.
- 호출자 (b)(c) 분류 각각에 대해 "예외 시 태스크 생존" 테스트 1개 이상.

## 6. 착수 조건
- 8영역 호출자 목록 승인 → 주중 장외 배포 → D+1 `[pg_acquire_timeout]` 0건이 정상.

## 3-a. 호출자 사전 목록 (09-05 15:2x 자동 집계 — 화요일 착수 시 재실행해 갱신)
- 총 `pg.*` 호출 **116** 건 / 함수별 {'fetch': 52, 'fetchrow': 21, 'execute': 28, 'fetchval': 13, 'executemany': 2} / 파일 18개. 8영역 파일은 굵게. 직접 `.acquire(` 호출 6건: src/db/pg.py:128; src/db/pg.py:138; src/db/pg.py:148; src/db/pg.py:156; src/db/pg.py:162; src/engine/account_risk_watcher.py:61.

| 파일 | 호출 수 | 비고 |
|---|---|---|
| `src/db/stock_master.py` | 19 |  |
| `src/db/trade_history.py` | 17 |  |
| `src/db/stock_master_daily.py` | 11 |  |
| `src/db/kis_quote_accounts.py` | 8 |  |
| `src/db/parameter_recommendations.py` | 8 |  |
| `src/db/system_logs.py` | 7 |  |
| `src/db/backtest_runs.py` | 5 |  |
| `src/db/daily_performance.py` | 5 |  |
| `src/db/market_regime_snapshots.py` | 5 |  |
| `src/db/positions.py` | 5 |  |
| `src/db/log_reports.py` | 4 |  |
| `src/db/pending_next_day_clear.py` | 4 |  |
| `src/db/stock_master_financial.py` | 4 |  |
| `src/db/strategy_config.py` | 4 |  |
| `src/db/strategy_funnel.py` | 4 |  |
| `src/engine/log_metrics_collector.py` | 3 |  |
| `src/db/system_config.py` | 2 |  |
| `src/main.py` | 1 |  |

- 화요일 아침 절차: ① 위 표 재집계 ② 8영역 파일의 각 호출 지점을 (a)/(b)/(c) 로 분류해 표에 열 추가 ③ 사용자 승인(8영역 = 예외 타입 추가만, 코드 diff 는 `src/db/pg.py` 단독) ④ Red→Green→Verify ⑤ 장외 배포.
