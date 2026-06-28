# 사이클 184 Red — stale-2: 2-pass 슬롯 계산 풀 총용량 정합 (MEDIUM)

작성: tdd-engineer (Red 단계). **production 미변경**. Green = backend-dev.
대상: `src/engine/scanner.py::subscribe_filtered_stocks` 단독. **realtime/ 변경 0** (기존 accessor 재사용).
매매 안전성: scanner 매수 진입 *전* 영역 (사이클 38 명문화) + HIGH bypass 절대 보호 불변 (사이클 32 R4).

## 테스트 파일

- 행위: `tests/unit/engine/scanner/test_cycle184_pool_union_slots.py` (7 케이스)
- AST: `tests/unit/ast/test_cycle184_pool_slots_ast.py` (4 케이스)
- 합계 **11 케이스** = 현재 **FAIL 5 (Red)** + **PASS 보존 6 (회귀 가드)**

---

## 결함 (stale-2, MEDIUM — 보조 세션 존재 시 슬롯 오산)

LOW 후보 2-pass 슬롯 계산 2곳이 **메인 세션 단독** 카운트만 사용:

| 위치 | 현재 코드 |
|------|----------|
| `scanner.py:1118` (1차 LOW 루프) | `remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)` |
| `scanner.py:1146` (2차 overflow 흡수 루프) | `remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)` |

`kis_ws._subscriptions` = 메인 세션 단독 set. 풀(`kis_ws_pool`)이 LOW 후보를 보조 세션에
라운드로빈 분배(`subscribe(bypass_limit=False)`)하면 메인 카운트는 안 늘어 →
**메인 full(41) + 보조 41×N 유휴 시 `remaining = 41-41 = 0` → LOW 후보 silent 과다 drop**
(보조 슬롯 전부 비었는데도). 풀 총용량 = `MAX_SUBSCRIPTIONS × (1+보조수)`
(websocket_pool.py:202 `[pool_start]` total_slots / route realtime.py:157 limit 계산과 동일).

> 참고: `scanner.py:1166` `total_subscribed = len(kis_ws._subscriptions)` 은 `[priority_drop]`
> 드롭 요약 **로그 라인** (target=`total_subscribed`, `remaining` 아님) = 시정 범위 외. AST 가드는
> `remaining` 할당만 대상 → 로그 라인 false-positive 없음 (Green 최소 변경 보존; 로그 정합은 LOW 인계).

## 확정 시정 설계 (Green 목표 — scanner.py 단독, realtime/ 미변경)

```python
# 2-pass 루프 진입 *전* 1회 계산 (세션 수 루프 중 불변):
_pool_session_count = len(kis_ws_pool.get_session_status())   # main + 보조 N = 1+N (read-only)
_pool_total_slots = MAX_SUBSCRIPTIONS * _pool_session_count
# 각 사이트(L1118/L1146):
remaining = _pool_total_slots - len(kis_ws_pool._subscriptions)   # 풀 union(전 tr_id property)
```

- `kis_ws_pool._subscriptions` = `WebsocketPool` 호환 property (websocket_pool.py:564, 메인+보조 전
  세션 `_subscriptions` 합집합, **모든 tr_id 포함**). `get_subscribed_tickers()`(TICK-only)는
  체결통보/장운영정보 제외 undercount → **`_subscriptions` 사용 의무** (gate #4).
- `kis_ws_pool.get_session_status()` = 메인+보조 전 세션 리스트(len=1+N), 라우트와 동일 계산.
- **보조 0개(n=1) → `_pool_total_slots=41` + `kis_ws_pool._subscriptions`==`kis_ws._subscriptions`
  (메인 단독) → 현 동작 완전 동일 (회귀 0)** = 핵심 회귀 가드.

---

## 가드 표

### 행위 (`test_cycle184_pool_union_slots.py`)

| 케이스 | 시나리오 | 현재 결과 | 근거 |
|--------|----------|----------|------|
| `test_REGRESS1_aux0_main_full_drops_all_identical` | 보조0 + 메인 full(41), breakout 5 | **PASS 보존** | 현재·Green 모두 `remaining=0` → 전량 drop. 회귀 0 핵심 |
| `test_REGRESS2_aux0_main_room_absorbs_all_identical` | 보조0 + 메인 10/41, breakout 5 | **PASS 보존** | 현재·Green `remaining=31` → 전량 흡수 |
| `test_REGRESS3_aux1_ample_room_absorbs_all_identical` | 보조1 + 메인 20/41, breakout 5 | **PASS 보존** | 여유 충분 시 보조 존재 무영향 (현재 21 / Green 62 둘 다 >0) |
| `test_ACCURACY1_aux1_main_full_absorbs_into_aux_slots` | 보조1 + 메인 full + 보조 유휴, breakout 10 | **FAIL (Red)** | 풀 총용량 82, union 41 → 잔여 41 슬롯에 10건 흡수 의무. 현재 메인 단독 41 → remaining 0 → 0건 구독 |
| `test_ACCURACY2_aux2_one_full_one_idle_uses_pool_union_total` | 보조2(1 full+1 유휴) + 메인 full, breakout 8 | **FAIL (Red)** | 총용량 123, union 82(>메인 41) → 잔여 41 → 8건 흡수 의무. union property 사용 입증. 현재 0건 |
| `test_SAFETY_HIGH1_positions_ndc_always_subscribed_bypass` | 메인 full, positions2+ndc1 | **PASS 보존** | HIGH `bypass_limit=True` 슬롯 계산 무관 절대 구독 (사이클 32 R4) |
| `test_SAFETY_HIGH2_high_independent_of_low_slot_calc` | 메인 full, positions2+breakout5 | **PASS 보존** | 슬롯 계산 변경이 HIGH 경로 영향 0 |

### AST (`test_cycle184_pool_slots_ast.py`) — 노드 검사 (사이클 167/179 교훈, source 텍스트 스캔 아님)

| 케이스 | 검사 | 현재 결과 |
|--------|------|----------|
| `test_AST1_no_main_solo_subscriptions_in_remaining` | `remaining` 할당에 `len(kis_ws._subscriptions)`(메인 단독) 잔존 0건 | **FAIL (Red)** (L1118/L1146 2건) |
| `test_AST2_remaining_uses_pool_union_subscriptions` | `remaining` 할당이 `len(kis_ws_pool._subscriptions)`(풀 union) 사용 (gate #4) | **FAIL (Red)** |
| `test_AST3_uses_pool_get_session_status_for_total_slots` | `subscribe_filtered_stocks` 가 `kis_ws_pool.get_session_status()` 호출 | **FAIL (Red)** |
| `test_AST4_detector_self_test` | `_len_subscriptions_objs`/`_remaining_assigns` 탐지기 self-test (false-negative 차단) | **PASS** (항상) |

- AST 범위 = `remaining` *할당* 노드 한정 (target name 'remaining') → 로그 라인 `total_subscribed` 제외.
- AST-2 가 `kis_ws_pool._subscriptions` 강제 = gate #4 (`get_subscribed_tickers` TICK-only 금지) 흡수.

---

## 현재 FAIL 근거 (실측)

```
5 failed, 6 passed (cycle184 단독, 0.27s)
FAILED ACCURACY1 — 메인 단독 remaining=0 → breakout 구독 0건 (Green 기대 10)
FAILED ACCURACY2 — 동일 (Green 기대 8)
FAILED AST1     — remaining 할당 2건이 len(kis_ws._subscriptions) 사용
FAILED AST2     — remaining 할당이 len(kis_ws_pool._subscriptions) 미사용
FAILED AST3     — kis_ws_pool.get_session_status() 미호출
```

## 기존 2-pass 테스트 영향 — **의미 전환 0건 (회귀 0)**

Green 전환 후에도 기존 테스트는 **모두 보조 0개(aux=0) 환경** → 풀 union == 메인 단독,
total_slots=41 → 동작 완전 동일. 실측 검증:
- `kis_ws_pool._main is scanner.kis_ws` = **True** (싱글톤 동일성, websocket_pool.py:92)
- `kis_ws_pool._quotes` 기본 `[]` (보조 미등록, pool.start() 미호출) → `get_session_status()` len 1
- aux=0 시 `len(kis_ws_pool._subscriptions)` == `len(scanner.kis_ws._subscriptions)` (직접 확인)

| 파일 | 슬롯 mock 방식 | Green 영향 |
|------|---------------|-----------|
| `test_scanner_priority_order.py` | `_fresh_ws_subscriptions` fixture 가 `scanner.kis_ws._subscriptions` 패치 + fake subscribe 가 같은 set 에 add (한도 시뮬) | **무영향** — Green 은 `kis_ws_pool._subscriptions`(=`_main._subscriptions`=같은 패치 set, aux=0) 읽음 → remaining 동일 |
| `test_scanner_priority_dispatch.py` / `..._priority_order.py` (C-*) | `kis_ws._subscriptions=set()` 빈 셋 + `get_subscribed_tickers=set()` | **무영향** — aux=0, union=∅ |
| `test_breakout_candidate_low_priority.py` (case 4/5) | `kis_ws._subscriptions=set()` 빈 셋 | **무영향** — aux=0 |
| `test_scan_loop_delta_only.py` 등 | 동일 aux=0 가정 | **무영향** |

baseline 실측: 위 4 파일 **29 passed** (production 미변경 상태).

> **★ Green 단계 backend-dev 유의**: Green 이 `kis_ws_pool.get_session_status()` /
> `kis_ws_pool._subscriptions` 를 **모듈 글로벌 `kis_ws_pool`(싱글톤)** 로 읽어야 기존 테스트의
> `scanner.kis_ws._subscriptions` 패치가 풀 union 에 반영됨 (`_main is kis_ws` 덕분). 다른 참조 경로
> 사용 시 기존 테스트 깨질 수 있음 — 명세대로 `kis_ws_pool` 직접 사용 의무. 보조 0개 환경에서
> `_quotes` 오염(이전 테스트 pool.start 잔재) 없는지 확인.

## HIGH bypass 불변 가드 (SAFETY)

- positions/next_day_clear 는 L1060~1074 에서 `bypass_limit=True` 로 **슬롯 계산 `remaining` *전***
  무조건 subscribe → 슬롯 계산 변경이 HIGH 경로 영향 0. SAFETY-HIGH-1/2 가 메인 full 에서도
  HIGH 전량 구독 + bypass_limit=True 단언 (현재·Green 모두 PASS). 사이클 32 R4 보유/익일청산 절대 보호.
- `git diff -- src/realtime/ src/engine/risk.py src/engine/order_engine.py src/auth/` = 0 기대
  (Green = scanner.py `subscribe_filtered_stocks` 슬롯 계산 3줄 영역 한정).

## AST 방식 요약

- **AST 노드 검사** (`ast.parse` + walk) — source 텍스트 grep 아님 (사이클 167/179 false-positive 교훈).
- 식별: `remaining` 할당(`ast.Assign` target Name 'remaining') 의 RHS 내 `len(X._subscriptions)`
  Call → X(Name id) 추출. `kis_ws` 잔존 0건(AST-1) + `kis_ws_pool` 사용(AST-2).
- **탐지기 self-test(AST-4)** = 합성 bad/good 스니펫으로 탐지기 정확성 검증 → silent 무력화
  (항상 빈 리스트 → 위양성 PASS) 영구 차단.

## Green 기대

production 3~5줄 (`_pool_session_count`/`_pool_total_slots` 사전 1회 + remaining 2곳 교체) →
cycle184 5 FAIL → PASS 전환. 기존 4 파일 29 PASS 유지 (회귀 0, 의미 전환 0).
