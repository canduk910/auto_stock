# 사이클 159 Red — Supabase HTTP/2 race stagger 임계 상향 (사이클 158 → 옵션 C)

## 사유

운영 실측 (2026-06-17, Supabase MCP):
- 사이클 158 stagger (0/60/120/180) 배포 후 잔존 결함
- master_skip 992 / basics_skip 1,958 / Server disc 303 / ConnTerm 310 / deque_mut 16 (24h 누적)
- 사이클 158 대비 약 50% 감소했으나 운영 불충분

근본 원인 = stagger 시간 < 단일 task 처리 시간 (60s stagger << 280s task 처리)

## 시정 (옵션 C — refactor-expert 자문)

| Task | 사이클 158 | 사이클 159 (옵션 C) |
|------|------------|--------------------|
| `_full_universe_load_task_loop` | 0 | 0 |
| `_stock_master_daily_load_task_loop` | 60 | 240 |
| `_stock_master_basics_refresh_task_loop` | 120 | 480 |
| `_stock_master_master_load_task_loop` | 180 | 720 |

총 wall-clock = 720 + 120 = 14분 (사이클 158 = 180 + 120 = 5분 → 2.8배 확장)

## 회귀 가드 8 케이스

| 케이스 | 영역 | 위험 등급 |
|--------|------|-----------|
| G-159-STAGGER-1 | 4 task initial_delay_secs = 0 / 240 / 480 / 720 정확 발화 (AST 정적) | MEDIUM |
| G-159-STAGGER-2 | 사이클 158 회귀 가드 (default 0 인자 보존) | LOW |
| G-159-STAGGER-3 | 4 task wrapper 별 initial_delay_secs 인자 정합 정확 (4 wrapper × 4 값 매칭) | MEDIUM |
| G-159-SAFETY-1 | risk/order_engine/realtime/auth import 영역 0건 (HIGH) | HIGH |
| G-159-SAFETY-2 | 매수 진입 전 영역 한정 (사이클 38 명문화) — scanner / scheduler 영역만 | HIGH |
| G-159-AST-1 | scheduler.py `initial_delay_secs=` 호출 사이트 ≥ 4건 (정적) | MEDIUM |
| G-159-AST-2 | 4 wrapper 정확 호출 (sub-method 명) AST 가드 | LOW |
| G-159-INT-1 | task_loop_helper `initial_delay_secs > 0` 분기 asyncio.sleep 호출 (mock 검증) | MEDIUM |

## 영속 의무 매트릭스

- CLAUDE.md "절대 깨지 말 것" 8 영역 = 변경 0
- 사이클 38 명문화 (scanner 영역 매수 진입 전 한정)
- 사이클 67 stale_manager 4 sub-module 영역 = 변경 0
- 사이클 134 task_loop_helper 영역 `initial_delay_secs` 인자 영속
- 사이클 152 `_wait_until` hotfix 영속
- 사이클 158 회귀 보존 (G-158-Q3-1/2/3 PASS 유지)

## 매매 안전성 영역

영향 0 (사이클 38 명문화 영역). scanner 단계 매수 진입 전 task lifecycle 영역만 변경. risk.on_tick / order_engine / realtime / auth 변경 0.

