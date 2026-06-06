# 사이클 67 Red — `stale_manager.py` sub-module 분해 회귀 가드 명세

> **작성**: tdd-engineer (Red 단계)
> **작성일**: 2026-06-06 (토)
> **선행**: 설계 카드 `_workspace/cycle67_stale_manager_decomposition_design_card.md`
>           자문 응답 `_workspace/cycle67_stale_manager_decomposition_domain_response.md`
> **위험 등급**: MEDIUM (행위 보존 refactor, 78 회귀 가드 영향 + K stale watcher HIGH hot path)

---

## 1. 사이클 의도

`src/engine/stale_manager.py` 1,099L → 4 sub-module + facade 분해:
- `stale_diagnostics.py` (~350L, 진단 5 함수 + 4 상수)
- `stale_session_recovery.py` (~280L, silent inactive 3 함수 + 5 상수)
- `stale_universe_guard.py` (~150L, universe 가드 1 함수 + 1 상수)
- `stale_watcher_core.py` (~320L, K stale watcher 본체 2 함수, HIGH hot path)
- `stale_manager.py` (~30L facade, 11 함수 + 10 상수 re-export only)

행위 보존 의무 — scheduler.py 11 wrapper 시그너처 변경 0 + 외부 인터페이스 변경 0 +
회귀 78 케이스 영향 0.

## 2. 자문 채택 결정 (사용자 확정)

| 의제 | 채택 옵션 | 비고 |
|------|---------|------|
| Q1 import 의존성 | A (facade 보존 단방향) | 8 사이클 답습 |
| Q2 Q4=B cross-module | P1 (모듈-레벨 정적 import) | 가독성 + AST G-7/G-8 검증 명시성 |
| Q3 logger binding | A (4 sub-module 동일 `src.engine.scheduler`) | 사이클 60 I1 영속 |
| Q4 patch 경로 | **B (facade patch 영속)** + G-16 신규 가드 | 실측 0건 근거 (자문 §5) |
| Q5 scheduler.py wrapper | A (facade 유지, 변경 0) | Q1 자연 귀결 |
| Q6-1 hot path import 캐시 | CONSIDER (측정 권고) | LOW |
| Q6-2 사이클 71+ 옵션 B 헬퍼 | MEDIUM (사전 설계 청사진) | 사이클 71+ 발의 |
| Q6-3 사이클 65 회고 시점 분리 | MEDIUM (1 주 운영 후 카드 #16) | 시점 분리 권고 |

## 3. 회귀 가드 매트릭스 (17 케이스, 6 파일)

| ID | 카테고리 | 위험 | Red 결과 | 위치 |
|----|---------|------|---------|------|
| G-1 | stale_diagnostics 신규 5 함수 | MEDIUM | **FAIL** | `test_cycle67_module_decomposition_g1_g5.py` |
| G-2 | stale_session_recovery 신규 3 함수 | MEDIUM | **FAIL** | 동상 |
| G-3 | stale_universe_guard 신규 1 함수 | MEDIUM | **FAIL** | 동상 |
| G-4 | stale_watcher_core 신규 2 함수 (HIGH) | HIGH | **FAIL** | 동상 |
| G-5 | facade 11 함수 + 10 상수 re-export 영속 | MEDIUM | PASS | 동상 |
| G-6 | logger binding `src.engine.scheduler` 4 모듈 (HIGH) | HIGH | **FAIL** | `test_cycle67_dependency_logger_g6_g9.py` |
| G-7 | import 의존성 단방향 (옵션 A) | MEDIUM | **FAIL** | 동상 |
| G-8 | watcher_core 가 diagnostics 정적 import (Q2 P1) | MEDIUM | **FAIL** | 동상 |
| G-9 | scheduler.py 11 wrapper facade lazy import 영속 (Q5 A) | MEDIUM | PASS | 동상 |
| G-10 | `emit_stale_session_detail` 시그너처 영속 (Q4=B) | MEDIUM | PASS | `test_cycle67_cycle63_cycle66_persistence_g10_g13.py` |
| G-11 | 사이클 66 시정 변수명 (`high_targets`/`low_targets`) 영속 | HIGH | PASS | 동상 |
| G-12 | try/except 4중 가드 (사이클 66 Q2) AST 영속 | HIGH | PASS | 동상 |
| G-13 | caplog `src.engine.scheduler` logger 발화 영속 | MEDIUM | PASS | 동상 |
| G-14 | 폐기 메서드 `_emit_price_filter_daily_summary` 0건 영속 | LOW | PASS | `test_cycle67_cycle60_persistence_g14_g15.py` |
| G-15 | WARNING `[stale_priority_resubscribe_cap_exceeded]` 영속 | HIGH | PASS | 동상 |
| G-16 | facade patch silent 결함 영구 차단 (Q4 옵션 B 안전선) | MEDIUM | PASS | `test_cycle67_facade_patch_persistence_g16.py` |
| G-17 | priority 분리 *후* cap AST (분해 후 위치 변경 대비) | HIGH | PASS | `test_cycle67_cycle66_priority_cap_persistence_g17.py` |

**HIGH 6 케이스 (35%)**: G-4 (K stale watcher 본체 신규), G-6 (logger silent 누락 위험),
G-11 (사이클 66 시정 영속), G-12 (try/except 4중), G-15 (사이클 29 사고 영역 WARNING),
G-17 (priority 분리 후 cap, 사이클 29 005935 사고 영구 차단).

## 4. Red 실행 결과

```
$ python -m pytest tests/unit/engine/stale_manager/test_cycle67_*.py -v --tb=short
7 failed, 10 passed in 0.39s
```

**FAIL (7)** — sub-module 4 파일 미존재 + 그에 의존하는 AST 가드 3 (G-6/G-7/G-8):
- G-1 `test_G1_stale_diagnostics_module_exports_5_functions`
- G-2 `test_G2_stale_session_recovery_module_exports_3_functions`
- G-3 `test_G3_stale_universe_guard_module_exports_1_function`
- G-4 `test_G4_stale_watcher_core_module_exports_2_functions`
- G-6 `test_G6_logger_binding_src_engine_scheduler_consistency`
- G-7 `test_G7_import_dependency_acyclic_unidirectional`
- G-8 `test_G8_stale_watcher_core_imports_emit_stale_session_detail_at_module_level`

**PASS (10)** — facade 영속 + 사이클 66 시정 본체 영속 + 영구 가드 (G-14/G-16):
- G-5 (facade re-export 영속, 분해 후에도 의무)
- G-9 (scheduler.py 11 wrapper 현재 facade 경유 영속)
- G-10/G-11/G-12/G-13 (사이클 60+61+63+66 본체가 stale_manager.py 잔존 → fallback PASS)
- G-14 (폐기 메서드 0건 영속)
- G-15 (사이클 29 사고 영역 WARNING 영속)
- G-16 (실측 facade patch 0건)
- G-17 (사이클 66 시정 영속)

## 5. flakiness 3 회 반복 검증

```
RUN 1: 7 failed, 10 passed in 0.29s
RUN 2: 7 failed, 10 passed in 0.20s
RUN 3: 7 failed, 10 passed in 0.20s
```

flakiness 0 (동일 결과 + ±0.09s 변동, order independence).

## 6. 카테고리 분리 측정

| sub-module 책임 영역 | 케이스 분포 |
|-------------------|----------|
| stale_diagnostics | G-1, G-10 (시그너처) |
| stale_session_recovery | G-2 |
| stale_universe_guard | G-3 |
| stale_watcher_core (HIGH hot path) | G-4, G-8, G-11, G-12, G-13, G-15, G-17 (7 케이스, 41%) |
| facade (stale_manager.py) | G-5, G-9, G-16 |
| 횡단 (4 sub-module 공통) | G-6 (logger), G-7 (의존성) |
| 영구 가드 (영역 무관) | G-14 (폐기 메서드 0) |

**HIGH hot path 영역 7 케이스 (41%)** = K stale watcher 본체 영역 보호 집중.

## 7. Green 단계 의무 (backend-dev 인계)

1. `src/engine/stale_diagnostics.py` 신규 — 5 함수 + 4 상수 이주
   (logger `src.engine.scheduler` 명시 binding 의무)
2. `src/engine/stale_session_recovery.py` 신규 — 3 함수 + 5 상수 이주
3. `src/engine/stale_universe_guard.py` 신규 — 1 함수 + 1 상수 이주
4. `src/engine/stale_watcher_core.py` 신규 — 2 함수 이주 +
   `from src.engine.stale_diagnostics import emit_stale_session_detail` 모듈-레벨
   정적 import (Q2 P1) + 사이클 66 시정 본체 영속
5. `src/engine/stale_manager.py` 재작성 — facade ~30L, 11 함수 + 10 상수 re-export only
   (`__all__` 21 항목 명시)
6. `src/engine/scheduler.py` 11 wrapper 변경 0 의무 — facade 경유 lazy import 영속

Green 검증 의무: 17 PASS + 사이클 60 (18) + 사이클 61 (20) + 사이클 63 (29) + 사이클 66 (11)
= **누적 95 케이스 PASS** (회귀 0 + flakiness 3 회 반복).

## 8. 산출물 경로

- Red 테스트 6 파일 (17 케이스):
  - `tests/unit/engine/stale_manager/test_cycle67_module_decomposition_g1_g5.py`
  - `tests/unit/engine/stale_manager/test_cycle67_dependency_logger_g6_g9.py`
  - `tests/unit/engine/stale_manager/test_cycle67_cycle63_cycle66_persistence_g10_g13.py`
  - `tests/unit/engine/stale_manager/test_cycle67_cycle60_persistence_g14_g15.py`
  - `tests/unit/engine/stale_manager/test_cycle67_facade_patch_persistence_g16.py`
  - `tests/unit/engine/stale_manager/test_cycle67_cycle66_priority_cap_persistence_g17.py`
- Red 명세 (본 문서): `_workspace/red/cycle67_stale_manager_decomposition.md`

## 9. backend-dev 발주 요청

SendMessage to backend-dev: "사이클 67 Red 17 케이스 작성 완료. 7 FAIL (sub-module 4 파일
미존재) + 10 PASS (facade/사이클 66 본체 영속). flakiness 0 (3 회 반복). Green 단계 = 4
sub-module 분해 + facade 30L 재작성 + scheduler.py wrapper 변경 0. 자문 채택: Q1=A / Q2=P1
모듈-레벨 정적 import / Q3=A 동일 logger / Q4=B facade patch 영속 + G-16 신규 / Q5=A wrapper
변경 0. 신규 가드 G-16/G-17 영속 의무. 누적 95 케이스 PASS 목표."
