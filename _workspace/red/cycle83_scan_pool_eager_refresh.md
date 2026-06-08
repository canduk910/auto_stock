# 사이클 83 Red 명세 — `_scan_loop` 후보 풀 ticker `stock_master` eager refresh 영역 확장

**작성일**: 2026-06-09
**위급도**: MEDIUM
**카드**: #82-A (옵션 1)
**사용자 결정**: Q1=B (`subscribe_filtered_stocks` 진입점 hook) + Q2=C (백그라운드 task) + Q3=B (24h TTL + 50ms sleep) + Q6=B (사이클 84 push 분리)
**도메인 자문 결론**: 위급도 MEDIUM, 사용자 결정 전부 일치, 영구 가드 매트릭스 10 케이스 (HIGH 3 + MEDIUM 4 + LOW 3)

---

## 근본 원인

`stock_master` 운영 적재 = **14건 한정** (보유/익일청산 위주 — `_eager_refresh_stock_master_for_held_positions()` 의 좁은 영역). `_apply_price_filter` (`src/engine/scanner.py:166-176`) 가 `bfdy_clpr <= 0` 시 graceful 통과 → **후보 풀 ~90% 가 가격필터 우회**.

사이클 81 시정 (키 오타 `prdy_clpr` → `bfdy_clpr`) 의 실효성이 stock_master 적재 영역에 결정적 의존 — 적재 안 된 ticker = `stock_master.get()` None → `_apply_price_filter` graceful 통과 경로 진입. SK스퀘어 (402340) 미적재 케이스 = 동일 경로로 가격필터 우회 (사용자 보고 케이스).

**현황**:
- `_eager_refresh_stock_master_for_held_positions()` (사이클 13-D 도입) = 보유 + 익일청산 ticker 만 갱신 (~10건)
- `_scan_loop` (5분 주기) 후보 풀 ~150건 = 14건 - 10건 = 4건만 stock_master 적재 (~3%)
- `_apply_price_filter` 통과율 = (4건 통과 + 146건 graceful) / 150건 = 97% (실효 가격필터 무용)

## 시정 영역 매트릭스

### 영역 1 (시정 의무): `_scan_loop` 후보 풀 eager refresh

**위치**: `src/engine/scanner.py::subscribe_filtered_stocks` 진입점 직전 hook (Q1=B)
또는 `src/engine/scheduler.py::_scan_loop` 본체 hook (등가)

**행위**:
- 후보 풀 합집합 (`tickers ∪ extra ∪ priority_groups 값들`) 의 각 ticker 에 대해 `stock_master.is_stale(ticker, max_age_hours=24)` 검사
- stale = True → 백그라운드 task 큐 (Q2=C) 에 추가
- 백그라운드 task 가 sequential `inquire_stock_basics` + `upsert_one` 호출 (사이클 13-D `_eager_refresh_stock_master_for_held_positions` 패턴 답습)
- ticker 간 `asyncio.sleep(0.05)` 50ms (Q3=B, Rate Limit 보호)
- 5분 윈도우 누적 통계 collector → `[scan_pool_eager_refresh] window=300s candidates=N refreshed=M skipped=K failed=L elapsed_ms=E` 1행 emit (사이클 74 sampling 패턴 답습)

**lifecycle 통합**:
- `connect()` / `_boot` 시점 task 시작 (사이클 76 `_api_recovered_collector_task` 답습)
- `stop()` task_attrs 튜플 + `run_daily()` `finally` 양쪽 cancel (사이클 79 답습)
- 5분 윈도우 마지막 flush 1회 (사이클 78 답습)

### 영역 2 (영구 가드): 매매 안전성 영속

- 사이클 38 명문화 영속: `tradable_boards` 매수 진입 전용 영역에 신규 코드 위치 한정 — 매도/익일청산/손절 영향 0
- 사이클 32 R4 universe_guard 영속: 보유/익일청산 절대 보호 (eager refresh 가 unsubscribe 트리거 0)
- 사이클 17 KIS LMS chain 영속: eager refresh 가 unsubscribe 발화 0건

---

## 회귀 가드 10 케이스 (HIGH 3 + MEDIUM 4 + LOW 3)

| ID | 위급도 | 파일 | 검증 영역 |
|----|--------|------|-----------|
| **G-AST1** | HIGH | `tests/unit/ast/test_cycle83_ast_task_cancel_required.py` | 사이클 79 패턴 답습 — 신규 `_scan_pool_eager_refresh_task` (또는 결정 명명) 가 `stop()` + `run_daily.finally` 양쪽 task_attrs 튜플에 동행 추가 영구 가드. AST 정적 검증. |
| **G-AST2** | HIGH | `tests/unit/ast/test_cycle83_ast_tradable_boards_no_reference.py` | 사이클 38 명문화 영속 가드. eager refresh 신규 코드 영역에 `tradable_boards` keyword 참조 0건 정적 검증. |
| **G-LC1** | HIGH | `tests/unit/engine/test_cycle83_task_lifecycle.py` | asyncio mock lifecycle. `connect()` 시점 task 시작 + `stop()` cancel + setattr None 검증. |
| **G-TT1** | MEDIUM | `tests/unit/engine/test_cycle83_ttl_fresh_skip.py` | 24h TTL fresh skip freezegun. `stock_master.is_stale()` 사이클 68 KST 답습 + 24h 이내 fresh → eager refresh skip. |
| **G-TT2** | MEDIUM | `tests/unit/engine/test_cycle83_rate_limit_sleep.py` | 50ms sleep 가드. 30~50 ticker 호출 시 호출 간격 ≥50ms 검증. |
| **G-FL1** | MEDIUM | `tests/unit/engine/test_cycle83_stop_flush.py` | `stop()` 시점 마지막 flush 1회 보장 (사이클 78 답습). |
| **G-ML1** | MEDIUM | `tests/unit/engine/test_cycle83_memory_leak.py` | 5분 윈도우 종료 후 collector `len == 0` freezegun (메모리 leak 영구 차단). |
| **G-OP1** | LOW | `tests/unit/engine/test_cycle83_sk_square_fixture.py` | SK스퀘어 (402340) freezegun 실데이터 fixture. eager refresh 후 `bfdy_clpr` valid (>0) + `_apply_price_filter` skip 발화 검증. |
| **G-OP2** | LOW | `tests/unit/engine/test_cycle83_emit_visibility.py` | `[scan_pool_eager_refresh]` 1행 emit 가시화 검증 (A1 자문 권고). |
| **G-RT1** | LOW | `tests/unit/engine/test_cycle83_r6_frequency_regression.py` | 사이클 31 R6 silent_skip trigger 빈도 감소 회귀 (eager refresh 후 R6 trigger 빈도 ≤ 사전 빈도). |

## Red 상태 (사이클 83 작성 시점)

- production 코드 변경 0 (Red 단계 의무)
- 모든 10 케이스 fail 의무 (시정 코드 부재 시)
- 백엔드 현재 2110 PASS + 2 XFAIL + 2 skip → 사이클 83 Red 작성 시 +10 신규 fail 예상

## Green 단계 (사이클 84 backend-dev 인계)

production 시정:
1. `src/engine/scanner.py` 신규 함수 4: `_collect_scan_pool_tickers_for_eager_refresh()` + `_record_scan_pool_eager_refresh()` + `_flush_scan_pool_eager_refresh_collector()` + task body (`_scan_pool_eager_refresh_loop()`)
2. `src/engine/scheduler.py` lifecycle 통합: `_scan_pool_eager_refresh_task = asyncio.create_task(...)` (사이클 76 패턴) + `stop()` task_attrs 튜플 + `run_daily.finally` task_attrs 튜플 + `stop()` 마지막 flush try/except
3. `subscribe_filtered_stocks` 진입점 hook (Q1=B): `_record_scan_pool_candidates(tickers ∪ extra ∪ priority_groups)` 호출 (비동기 큐 등록만, 본체 차단 0)

## 영속 의무

- **사이클 79 패턴 답습**: AST G-AST1 (`_*_task` 도입 시 양쪽 task_attrs 튜플 동행)
- **사이클 78 패턴 답습**: G-FL1 (`stop()` 시점 마지막 flush) + G-ML1 (5분 윈도우 종료 후 collector 비워짐)
- **사이클 74 패턴 답습**: G-OP2 (5분 sampling 1행 emit)
- **사이클 38 명문화 영속**: G-AST2 (`tradable_boards` 신규 코드 영역 0 참조)
- **사이클 13-D 패턴 답습**: `_eager_refresh_stock_master_for_held_positions()` 구조 100% 답습 (sequential await + 24h TTL skip + graceful 예외)
- **사이클 17 KIS LMS chain 영속**: eager refresh 가 unsubscribe 발화 0건 (Q1 자연 만족 — `subscribe_filtered_stocks` 진입점 hook 은 풀 갱신만)
- **사이클 32 R4 영속**: 보유/익일청산 절대 보호 (`_eager_refresh_stock_master_for_held_positions` 단독 영역 영속)

## 운영 효과 예상 (사이클 84 push 후)

- stock_master 적재 14건 → 150+ 건 (후보 풀 전체 24h 갱신)
- `_apply_price_filter` 통과율 97% → 30~50% (정상 가격필터 발화)
- `[price_filter_scanner_skip]` 일일 0건 → 10~50건 (작전주/초고가 자동 차단)
- `[risk_silent_skip]` SK스퀘어 폭주 270건/일 → 0건 (R6 우회 시나리오 자연 차단, 사이클 81 시정 효과 영속 강화)
- dup_factor 추가 감소

## 사이클 84+ 후속

- Q6=B 사이클 84 push 분리 (안전 마진)
- 사이클 78 `[swing_rest_poll_summary]` 실증 측정 (다음 영업일 09:30~15:20)
- #16 (MEDIUM Q6-3 2026-06-13 이후) 영속
