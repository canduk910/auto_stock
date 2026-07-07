# 사이클 196 — VCP daily backfill churn 시정 (target 220→120 + 윈도우 클램프)

## 배경 (사이클 192 D+1 실측 신규 발견)

7/6~7/7 D+1 실측 중 발견. `_stock_master_daily_load_once` (16:00 daily task + boot immediate) 의
VCP universe backfill 이 **수렴하지 못하고 매 load 마다 전량 재backfill**.

### 근본 원인 (실측 확정)

- VCP backfill 조건 (`scanner.py:2217-2218`): `is_vcp_universe AND existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=220)`
- retention (`stock_master_daily.py:587`): `DAILY_RETENTION_DAYS = 230` **달력일** → 매 purge 가 230 cal일
  이전 row 삭제 → **보유 영업일 = 154** (운영 DB 실측: rows_all 284 vs rows_within_retention 154,
  oldest 2025-05-09 = churn zone 포함).
- 154 영업일 < 220 → **VCP 348종목 `existing_count` 가 220 에 절대 도달 못 함** → `use_vcp_backfill`
  영구 True → 매 load 마다 `fetch_daily_candles_backfill(total_days=220)` 전량 재실행.
- 부수 결함: `fetch_daily_candles_backfill(total_days=220, window=100)` 은 `ceil(220/100)=3` 윈도우
  **전부 실행** → 실제 300영업일(≈430 cal일, oldest 2025-05-09 ≈ today-424) fetch = 목표 220 초과.

### 영향 (매매 무관, 순수 낭비 — scanner 매수 진입 *전* 데이터 plumbing, 사이클 38)

- **DB churn**: 매 backfill 이 cal 230~430 (영업일 154~300, ≈130 날짜 × 348종목 ≈ 45,159행) 재삽입
  → 다음 purge 드레인. 7/6 13:31 boot purge `deleted=45159` 가 그 증거.
- **잉여 KIS 호출**: 348종목 × 3윈도우 × (boot + 16:00) ≈ 2,088 호출/일 (수렴 시 348 incremental 로 감소).
- **daily load 지연**: 7/7 08:11 `elapsed_ms=1213766` (20분).
- **VCP prepare 는 실제로 100일만 사용** (`vcp_breakout.py:162-164` 소스 명시: "★ VCP days=100 cap
  절대 유지 (220 미사용)" — 어댑터 `get_recent_daily(days=100)` 최신 100 DESC 만 반환). 220 backfill =
  **적재-즉시-purge 되는 순수 낭비** (retention 도 안 되고 prepare 도 안 읽음).

## 시정 (사용자 결정 A + 실측 기반 값 강화)

**사용자 결정** (AskUserQuestion): Option A = backfill target 하향 (retention 용량 내 수렴, 저장 불변).
값은 실측(retained=154) 기반 강화 = **150 → 120** (retained 154 대비 34일 마진 + VCP read 100 위 20일
버퍼 — 150 은 마진 4일뿐이라 휴일 밀집 구간 간헐 재backfill 위험).

### P1 — `src/engine/scanner.py`
`_DAILY_LOAD_VCP_BACKFILL_DAYS = 220` → **`120`**. 주석 갱신 (retention 230cal=154영업일 실측 →
120 안전 수렴 + VCP prepare 100일 위 버퍼). VCP 분기 로직 (`use_vcp_backfill`) 구조 불변.

### P2 — `src/api/condition.py` `fetch_daily_candles_backfill` 윈도우 클램프
윈도우 루프 (L689-690):
```python
end_offset = i * window
start_offset = (i + 1) * window          # ← 목표 초과 (마지막 윈도우 overshoot)
```
→
```python
end_offset = i * window
start_offset = min((i + 1) * window, total_days)   # 사이클 196 — 목표 초과 fetch 차단
```
효과: total_days=120 → 윈도우 0 [0,100] + 윈도우 1 [100,120] (마지막 클램프) → 최고 도달 =
`int(120*7/5)+10 = 178` cal일 (retention 230 내 → **churn 0**). total_days=220 (regression) →
윈도우 2 start_offset=min(300,220)=220 → 도달 430→318 cal일. docstring "220일=100일 윈도우 ×3"
서술 갱신. **dedupe/sleep/graceful/`FID_ORG_ADJ_PRC="0"`/6자리 가드 불변.**

### 수렴 증명
target 120 + retained 154: 첫 backfill(2 클램프 윈도우, 120영업일, 178cal 도달, retention 내) →
`existing_count=120 ≥ 120` → `use_vcp_backfill=False` → incremental (fetch_daily_candles days=7) →
retention 까지 incremental 누적(→154) → 매 load VCP 는 348 incremental (1호출) → **재backfill·churn 종료.**
VCP prepare (days=100, min_required=100) 는 보유 ≥120 → 항상 100 확보 (행위 보존).

## 회귀 가드 (신규 `tests/unit/`)

### Group A — 윈도우 클램프 (`test_cycle196_backfill_window_clamp.py`, condition.py)
- **A-1 (핵심)**: `fetch_daily_candles_backfill(t, total_days=120, window=100)` — `fetch_daily_candles_ranged`
  mock + freeze today → 2 윈도우 호출, **마지막 윈도우 start_offset ≤ total_days** (win_start 이
  today-int(120*7/5)-10 ≈ today-178cal, today-290cal 아님). 모든 윈도우 start_offset ≤ 120 단언.
- **A-2 (regression)**: total_days=220 → 3 윈도우, 마지막 start_offset=220(300 아님) → 도달 318cal(430 아님).
- **A-3**: total_days=100 → 1 윈도우 start_offset=100 (min(100,100)) → 불변 (150cal 도달).
- **A-4 (AST/불변식)**: `fetch_daily_candles_backfill` 본체에 `min(` + `total_days` 클램프 존재
  (목표 초과 fetch 재도입 영구 차단, self-test).

### Group B — 수렴 (`test_cycle196_vcp_backfill_convergence.py`, scanner.py)
- **B-1**: `_DAILY_LOAD_VCP_BACKFILL_DAYS == 120` (상수 가드).
- **B-2 (핵심 수렴 증명)**: `_stock_master_daily_load_once` — VCP universe ticker, max_bas_dd<today,
  `count_by_ticker=154` → `fetch_daily_candles_backfill` **미호출** + `fetch_daily_candles(days=7)` 호출
  (incremental 수렴). mock = max_bas_dd/count_by_ticker/fetch_*/upsert_batch/list_all(vcp_universe seed).
- **B-3**: VCP ticker `count_by_ticker=119` (<120) → `fetch_daily_candles_backfill(total_days=120)` 호출.
- **B-4 (경계)**: `count_by_ticker=120` → 정확히 incremental (120<120 False).
- **B-5 (regression)**: 非VCP ticker 불변 — existing=154 → incremental / existing=30 → 100일 backfill
  (`fetch_daily_candles(days=100)`, VCP 분기 미진입).

### Group C — 매매 안전성
- **C-1 (SAFETY, AST)**: scanner.py 변경 = `_DAILY_LOAD_VCP_BACKFILL_DAYS` 상수 값만 (구독/스캔/우선순위/
  매수 경로 함수 미변경) — `subscribe_filtered_stocks`/`scan_stocks`/priority 관련 심볼 텍스트 불변 단언
  (사이클 172 `test_cycle172_safety_no_trading_diff.py` 패턴 답습).

## 의미 전환 (사이클 66 K-2) — tdd-engineer 식별·최소 갱신
- `test_cycle172_daily_ranged_backfill.py` — "220일=100일 윈도우 ×3" / 마지막 윈도우 날짜 범위 단언 시
  클램프 반영 (total_days=220 → 3윈도우 유지되나 3번째 start_offset 300→220). intent 보존.
- `test_cycle172_vcp_universe_backfill.py` — `_DAILY_LOAD_VCP_BACKFILL_DAYS == 220` / `total_days=220`
  호출 단언 → 120. intent(VCP universe backfill 분기 존재) 보존.
- `test_cycle172_retention_and_adapter.py` — retention **230 불변** (변경 0, 전환 없음 확인).
- `test_cycle172_safety_no_trading_diff.py` — AST safety, 클램프 후 PASS 확인.
- 사이클 173/187/192 daily 인접 테스트 = backfill total_days 하드코딩 단언 있으면 갱신, 없으면 회귀 0 확인.

## 검증 (Green 후 메인)
- Red 유효성: production stash 시 A-1/A-2/A-4 + B-1/B-2/B-3 FAIL (B-4/B-5/C-1 불변식 PASS).
- 격리 신규 ×2 flakiness 0 (freeze today = `fetch_daily_candles_backfill` datetime.now(KST) 동결,
  단 sleep asyncio 실호출 — 사이클 187 freezegun+asyncio.sleep hang 교훈: freezegun 금지, `today` 만
  고정하거나 `datetime` mock. Rate Limit sleep 은 `_DAILY_BACKFILL_WINDOW_SLEEP_SECS=0.05` 실호출 허용).
- 인접 회귀: cycle172/173/187/192 daily 계열 전수 PASS.
- **매매 안전성 8영역 diff**: scanner.py 는 8영역 中 1 → 변경이 `_DAILY_LOAD_VCP_BACKFILL_DAYS` 상수 값
  1줄 + 주석에 국한(구독/스캔/매수 hot path 불변) 직접 git diff 확인. condition.py 는 8영역 외.
  나머지 7영역(risk/order_engine/realtime/auth/api order.py/session/strategy_registry) diff 0 byte.

## 오케스트레이션
메인 스카우트·진단(완료, Supabase 실측 retained=154 확정) → tdd-engineer Red(A/B/C + 의미전환 식별)
→ backend-dev Green → 메인 검증. 커밋/푸시 보류 (사용자 승인). LOW~MEDIUM 운영 효율 (매매 무관).
