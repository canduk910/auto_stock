# 사이클 189 Red 작업 지시서 — db read retry 확장 (F4) + reprepare WARNING DailyEmitCap (F1)

출처: 7/1 `daily_log_reports` finding 검증 (2026-07-02) — F4(infra MEDIUM, kis_quote_accounts list 실패 11건/일 + price_filter/system_config get 실패) + F1(scan MEDIUM, BFB/VCP "후보 비어있음 재 prepare" WARNING 101건×4/일). 사이클 187 인계 (a) "전 db read 공통 retry 전환"의 1차 확장. 사용자 승인 = "F4+F1 묶음, 189 진행".

## 영역 A (F4) — `execute_with_retry` 확장: 2 모듈 read 전환 (쓰기 제외 영속)

사이클 187 `src/db/supabase.py::execute_with_retry(build, *, retries=1, op="")` 를 그대로 재사용 (헬퍼 변경 0). 대상 = **관측된 ERROR 발생원 2 모듈만** (blast radius 최소, 187 사용자 결정 패턴 답습):

### `src/db/kis_quote_accounts.py` read 4곳
`await asyncio.to_thread(_query)` → `await execute_with_retry(_query, op="<함수명>")`:
- `list_accounts` (L64) — 48h 실측 38건 최대 노이즈
- `get_account` (L86)
- `get_account_by_label` (L103)
- `get_credentials_for_token_manager` (L133)

### `src/db/system_config.py` read 9곳
- `get_cash_usage_ratio` (L70) / `get_auto_regime_adjust` (L137) / `_get_bool_or_none` (L198) / `get_buy_block_mode` (L311) / `_get_float_or_default` (L370) / `_get_bool_or_default` (L399) / `_get_int_or_default` (L616) / `_get_str_or_default_UNUSED` (L648) / `_get_string_or_none` (L781)

### 불변 계약 (187 답습)
- 기존 `try/except` graceful + 기본값 폴백 **전부 불변** — retry 소진 시 마지막 예외가 기존 except 로 떨어져 동일 폴백 (예: `_get_int_or_default` → default, `list_accounts` → 기존 폴백 동작 그대로 — Red 작성 전 각 함수 except 분기 실동작 확인 의무)
- **쓰기(`_upsert`/`_insert`/`_set_*` 계열) 미경유** — 직접 to_thread 유지 (187 멱등 제외 결정 영속)
- `list_accounts` 60s TTL 캐시 로직 불변 (retry 는 `_query` 호출부만 감쌈)
- 비-retry 예외 즉시 전파 (execute_with_retry 계약)

## 영역 B (F1) — `_reprepare_breakout_if_empty` WARNING DailyEmitCap

`src/engine/scheduler.py:2504~2506`:
```python
logger.warning("스캔 후보 비어있음 — 재 prepare 시도: %s", sid)
await write_log("WARNING", f"{sid} 후보 비어있음 — 재 prepare 시도")
```
현재 5분 scan_loop 마다 빈 전략별 무제한 발화 (logger + **DB INSERT**) → 하루 ~400행. 후보 0건은 정상 장세 가능 (VCP 0/65 일상).

### 시정
- `DailyEmitCap[str]` (`src/engine/daily_emit_cap.py`, API = `should_emit`/`mark_emitted`/`reset_daily`) 로 **로그 emit 만 1회/전략/일 cap** (사이클 31 R6 / 158 momentum 패턴 답습)
- **`strategy.prepare()` 재시도 행위 자체는 불변** — cap 은 logger.warning + write_log 두 줄만 감쌈 (사이클 48 회복 메커니즘 절대 보존)
- `_reset_daily_state()` 에 `reset_daily()` 동행 배선 (다음 영업일 재발화)
- 필드 위치 = TradingScheduler 인스턴스 필드 (사이클 56-D 패턴) 또는 기존 관례 답습 — tdd-engineer 판단

## Red 테스트 설계

### `tests/unit/db/test_cycle189_read_retry_expand.py` (~6)
- R-1: `list_accounts` 1회 RemoteProtocolError → retry → 정상 rows (execute_with_retry 경유 확인)
- R-2: `list_accounts` 2회 연속 실패 → 기존 graceful 폴백 불변
- R-3: `_get_int_or_default` retry → 값 / 소진 → default 폴백 불변
- R-4: `_get_bool_or_none` retry 경유 (대표 1)
- R-5: `get_buy_block_mode` retry 경유 + 소진 시 기존 폴백 (매수 가드 소비 경로 — 폴백 보수성 불변 확인)
- R-6: 쓰기 대표 1 (`_set_int` 또는 upsert) execute_with_retry 미경유 행위 확인

### `tests/unit/ast/test_cycle189_ast_read_retry.py` (~3)
- A-1: kis_quote_accounts read 4함수 = execute_with_retry 경유 + 직접 to_thread 0건
- A-2: system_config read 9함수 = 동일 (UNUSED 포함)
- A-3: 양 모듈 쓰기 계열 = to_thread 직접 유지 (execute_with_retry 호출 0건 불변식) — 187 A2 패턴

### `tests/unit/engine/test_cycle189_reprepare_emit_cap.py` (~5)
- C-1: 동일 sid 2회 연속 호출 → WARNING logger 1회만 (caplog)
- C-2: write_log 호출 1회만 (mock)
- C-3 (SAFETY): cap 발동 중에도 `strategy.prepare()` 는 매 호출 실행 (재시도 행위 불변)
- C-4: sid 별 독립 cap (bfb 발화 후 vcp 첫 발화는 emit)
- C-5: `_reset_daily_state()` 후 재발화 가능 (reset 배선)

## Red 유효성 기준
현재 코드에서 retry/AST/cap 케이스 FAIL, 폴백·쓰기 불변식 케이스는 PASS 허용 (187 기준 답습).

## Green 범위
`src/db/kis_quote_accounts.py` + `src/db/system_config.py` (read 호출부 1줄씩 교체 + execute_with_retry import) / `src/engine/scheduler.py` (reprepare cap 필드 + 2줄 가드 + reset 배선). 그 외 파일 변경 금지. 매매 안전성 8영역 diff 0 의무 (scheduler 는 8영역 외이나 reprepare 로그 cap 한정 확인).
