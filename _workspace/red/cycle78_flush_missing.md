# 사이클 78 Red 명세 — 사이클 74 도입 누락 silent 결함 시정 (flush 호출 사이트)

**날짜**: 2026-06-08
**위급도**: **HIGH (메모리 leak 영구 영역)**
**카드**: 사이클 74 hotfix (사용자 결정 = A + B + C, 17 사이클 연속 옵션 A 패턴 영속)
**선행 진단**: team-leader Phase 1 + C 진단 (Supabase READ-ONLY 측정)

---

## C 진단 결과 (필수 정독)

**Supabase 측정 (2026-06-07 22:56 ~ 2026-06-08 현재)**:

| prefix | last_emit (KST) | 상태 |
|--------|----------------|------|
| `[stale_watcher]` 개별 | 14:08:57 (사이클 74 배포 *이전* 마지막) | OK 배포 후 emit 0건 |
| `[swing_rest_poll]` 개별 | 14:09:27 (사이클 74 배포 *이전* 마지막) | OK 배포 후 emit 0건 |
| `[ws_action_summary]` | 16:50:29 (74건) | OK 사이클 74 정상 작동 |
| `[swing_rest_poll_summary]` | **0건 영구** | **결함 확정** |
| `[stale_watcher_summary]` | **0건 영구** | **결함 확정** |

### 근본 원인

- **사이클 74 commit `0017fe0`**: `record_swing_rest_poll` + `flush_swing_rest_poll_collector`
  + `record_stale_watcher_check` + `flush_stale_watcher_collector` 함수 + `_ws_action_metrics_loop` task 도입
- **누락**: `flush_swing_rest_poll_collector` + `flush_stale_watcher_collector` 호출 사이트 (5분 주기 task 또는 lifecycle hook)
- **사이클 76 commit `0d633a8`**: `_api_recovered_collector_loop` task 도입 시 swing/stale flush 추가 누락

### 메모리 leak 위험 (정량)

- `_swing_rest_poll_collector: list[dict]` 60s 주기 → 720 dict/day 무한 누적
- `_stale_watcher_collector: list[dict]` 120s 주기 → 360 dict/day 무한 누적
- **영업일 12 시간 운영 = 1,080 dict / day 영구 점유** (컨테이너 재시작까지)
- 현재 5 시간 운영 = ~450 dict 잔존

---

## A 명세 시정 (HIGH) — backend-dev Green 단계 발주 대상

**옵션 권고 = 옵션 1**: `_api_recovered_collector_loop` 본체 재사용 (단순 + 추가 task 미도입).

```python
# src/engine/scheduler.py::_api_recovered_collector_loop (사이클 76 도입 본체)
async def _api_recovered_collector_loop(self) -> None:
    from src.api.base import (
        _API_RECOVERED_COLLECTOR_WINDOW,
        _flush_api_recovered_collector,
        _flush_quote_recovered_collector,
    )
    # 사이클 78 hotfix import (모듈 레벨 권고, 함수 레벨도 가능)
    from src.engine.stale_watcher_core import flush_stale_watcher_collector

    while self._running:
        await asyncio.sleep(_API_RECOVERED_COLLECTOR_WINDOW)
        if not self._running:
            break
        try:
            await _flush_api_recovered_collector()
        except Exception:
            logger.exception("[api_recovered_collector] 메인 flush 실패")
        try:
            await _flush_quote_recovered_collector()
        except Exception:
            logger.exception("[api_recovered_collector] 풀 flush 실패")
        # 사이클 78 hotfix: 사이클 74 도입 누락 silent 결함 영구 시정
        try:
            flush_swing_rest_poll_collector()
        except Exception:
            logger.exception("[swing_rest_poll_collector] flush 실패")
        try:
            flush_stale_watcher_collector()
        except Exception:
            logger.exception("[stale_watcher_collector] flush 실패")
```

**lifecycle hook (`stop()`) 마지막 flush (Q5 사이클 74 G-SP4 답습)**:

```python
# src/engine/scheduler.py::stop() — unsubscribe_all() 호출 직전 추가
# 사이클 78 hotfix: 잔존 collector 마지막 flush (잔여 카운터 손실 방지)
try:
    flush_swing_rest_poll_collector()
except Exception:
    logger.exception("[swing_rest_poll_collector] shutdown flush 실패")
try:
    flush_stale_watcher_collector()
except Exception:
    logger.exception("[stale_watcher_collector] shutdown flush 실패")

await unsubscribe_all()
```

**부차 우려 발견**: `stop()` 의 task cancel 목록 (line 860~865) 에 `_api_recovered_collector_task` 누락 — 별도 카드 후보. 본 사이클 범위 외.

---

## B 명세 시정 (MEDIUM) — 무대상 확정

`[stale_watcher]` 직접 emit 사이트:
- `stale_watcher_core.py::check_and_resubscribe_stale` 본체 (line 237 영역) = 사이클 74 commit 에서 `record_stale_watcher_check` 위임으로 흡수 완료
- C 진단 = 사이클 74 배포 후 `[stale_watcher]` 개별 emit 0건 (14:08:57 마지막)
- **B 명세 = 무대상 확정** (사이클 74 commit `0017fe0` 에 이미 흡수)

---

## Red 테스트 매트릭스 (총 6 케이스, 3 파일)

### 의제 1 — flush 호출 사이트 존재 검증 (4 케이스)

파일: `tests/unit/engine/test_cycle78_flush_call_sites.py`

| ID | 검증 | Red | Green |
|----|------|-----|-------|
| G-FL1 | `flush_swing_rest_poll_collector` 호출 사이트 (scheduler.py) ≥ 1건 | 0건 FAIL | ≥1건 PASS |
| G-FL2 | `flush_stale_watcher_collector` 호출 사이트 (scheduler.py) ≥ 1건 | 0건 FAIL | ≥1건 PASS |
| G-FL3 | `stop()` lifecycle 본체에 양쪽 flush 호출 (Q5 잔여 손실 방지) | 0건 FAIL | 2건 PASS |
| G-FL4 | 5분 주기 task 함수 (stop 제외) 본체에 양쪽 flush co-located | 0건 FAIL | ≥1 함수 PASS |

### 의제 2 — collector 메모리 leak 차단 검증 (1 케이스)

파일: `tests/unit/engine/test_cycle78_memory_leak_prevention.py`

| ID | 검증 | Red | Green |
|----|------|-----|-------|
| G-ML1 | `_api_recovered_collector_loop` 1회 실행 후 양쪽 collector `len == 0` | 5 + 3 잔존 FAIL | 0 + 0 PASS |

### 의제 3 — AST 영구 가드 (1 케이스)

파일: `tests/unit/ast/test_cycle78_ast_flush_required.py`

| ID | 검증 | Red | Green |
|----|------|-----|-------|
| G-AST1 | `record_*` 정의 모듈의 대응 `flush_*` 호출 사이트 ≥ 1건 (scheduler.py) | 0건 FAIL | ≥1건 PASS |

**G-AST1 영구 가드 효과**: 미래 신규 `record_*` collector 추가 시 대응 `flush_*` 호출 사이트 누락 silent 결함 즉시 FAIL → silent 메모리 leak 영구 차단.

---

## Red 검증 결과 (2026-06-08)

### 단일 실행 결과

```
FAILED tests/unit/engine/test_cycle78_flush_call_sites.py::test_g_fl1_flush_swing_rest_poll_collector_call_site_exists
FAILED tests/unit/engine/test_cycle78_flush_call_sites.py::test_g_fl2_flush_stale_watcher_collector_call_site_exists
FAILED tests/unit/engine/test_cycle78_flush_call_sites.py::test_g_fl3_lifecycle_shutdown_flush_call_site_exists
FAILED tests/unit/engine/test_cycle78_flush_call_sites.py::test_g_fl4_periodic_task_flushes_both_collectors
FAILED tests/unit/engine/test_cycle78_memory_leak_prevention.py::test_g_ml1_periodic_task_clears_both_collectors
FAILED tests/unit/ast/test_cycle78_ast_flush_required.py::test_g_ast1_record_collector_requires_flush_call_site
============================== 6 failed in 0.31s ===============================
```

**FAIL 6 / PASS 0** — 전부 Red (의도된 실패).

### Flakiness 3 회 반복

| Run | 결과 | 시간 |
|-----|------|------|
| 1   | 6 failed | 0.21s |
| 2   | 6 failed | 0.21s |
| 3   | 6 failed | 0.21s |

**Flakiness 0** — 결정론적 (동일 결과 + 동일 ±0s 시간).

---

## 영속 의무 매트릭스 (Green 단계 backend-dev 의무)

| 영역 | 영속 의무 | 영향 |
|------|----------|------|
| 사이클 17 KIS LMS chain 차단 | `_opsp_backoff_until` 등록 행위 변경 0 | 로깅 영역 시정만 |
| 사이클 38 명문화 | `tradable_boards` 매수 진입 전용 영속 | 매도 영역 영향 0 |
| 사이클 55 R-1 / 66 / 67 매매 안전성 | SellRejectionTracker 2단계 TTL / cap=10 priority 분리 / stale facade 영속 | 0 |
| 사이클 74 record/flush 함수 시그너처 | 변경 0 (호출 사이트만 신규 추가) | 0 |
| 사이클 76 `_api_recovered_collector_loop` 패턴 | 본체 try/except 흡수 패턴 답습 | 0 |
| WebSocket 4중 안전망 (F1 / `_scan_loop` / K stale watcher / `_resubscribe_stale_priority`) | 호출 시점/횟수 변경 0 | 0 |
| 매도 / 손절 / Trailing / 익일청산 / 15:20 강제청산 | 본 사이클 시정 = 로깅 영역 (시세 영역) | 영향 0 |

---

## 산출물

| 파일 | 라인 | 케이스 | 종류 |
|------|------|--------|------|
| `tests/unit/engine/test_cycle78_flush_call_sites.py` | 230 | 4 (G-FL1~FL4) | AST 정적 + 함수 단위 |
| `tests/unit/engine/test_cycle78_memory_leak_prevention.py` | 110 | 1 (G-ML1) | asyncio integration (monkeypatch) |
| `tests/unit/ast/test_cycle78_ast_flush_required.py` | 120 | 1 (G-AST1) | AST 영구 가드 |
| `_workspace/red/cycle78_flush_missing.md` | 본 파일 | - | Red 명세 영구 기록 |

**총 6 케이스 / 3 파일 / Red 6 FAIL / Green 6 PASS 전환 예상**

---

## Green 단계 인계 (backend-dev)

1. **옵션 1 권고 채택 시** (1 곳 수정):
   - `src/engine/scheduler.py::_api_recovered_collector_loop` 본체 (L2469~L2480 영역) 에 swing/stale flush 호출 4 줄 (try/except 포함) 추가
   - import 추가: `from src.engine.stale_watcher_core import flush_stale_watcher_collector`

2. **lifecycle hook (G-FL3 요구)**:
   - `src/engine/scheduler.py::stop()` 의 `await unsubscribe_all()` 호출 직전에 양쪽 flush 호출 4 줄 (try/except 포함) 추가

3. **검증 명령**:
   ```bash
   python -m pytest tests/unit/engine/test_cycle78_*.py tests/unit/ast/test_cycle78_*.py -v
   # 기대: 6 passed
   ```

4. **회귀 검증**:
   ```bash
   python -m pytest tests/unit/engine/ tests/unit/ast/ -q
   # 회귀 0건 의무 (사이클 74 / 76 / 67 등 영역 무영향)
   ```

5. **운영 효과 (다음 _boot 후 5분 시점)**:
   - `[swing_rest_poll_summary]` 5분 주기 1행 emit 시작
   - `[stale_watcher_summary]` 5분 주기 1행 emit 시작
   - collector 메모리 안정 (자동 비움)

---

## 후속 카드 (사이클 79+ 발의 후보)

- **카드 #20** (LOW, 별도 우려): `stop()` 의 task cancel 목록에 `_api_recovered_collector_task` 누락 — line 860~865. 사이클 76 도입 시 누락. 좀비 task 위험은 낮으나 영구 가드 추가 권고.
- **카드 #21** (LOW): 미래 신규 `record_*` 헬퍼 도입 시 자동 회귀 가드 — 사이클 78 G-AST1 패턴이 일반화 흡수 (모듈 단위 자동 매칭). 별도 카드 불필요.
