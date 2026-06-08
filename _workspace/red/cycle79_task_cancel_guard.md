# 사이클 79 Red 명세 — `_api_recovered_collector_task` cancel 영구 가드

## 발주 근거
- 사이클 78 부차 발견 (commit `e03a13b` 보고서):
  > "stop() task cancel 목록 (L860~865) 에 _api_recovered_collector_task 가 여전히
  > 누락되어 있습니다. ... 운영 중 _running = False → loop 종료 → task 자연 종료가
  > 보장되므로 즉각 위험은 낮습니다."
- 사용자 결정: **사이클 79 발주** (영구 가드 추가 권고 수락)
- 위험 등급: LOW (즉각 위험 낮음 + 영구 silent 결함 차단)

## 근본 원인
- 사이클 76 commit (`0d633a8`) = `_api_recovered_collector_task = asyncio.create_task(
  self._api_recovered_collector_loop())` 도입 (`src/engine/scheduler.py:486~488`)
- `stop()` 의 `task_attrs` 튜플 (L860~865) 에 추가 누락
- `finally` 블록 (L737~742, `run_daily` 비정상 종료 경로) 도 동일 누락
- 사이클 13-E-2 명세 위반: "양쪽 동일 task 목록 통일"

## Red 테스트 매트릭스 (4 케이스 / 3 파일)

### `tests/unit/engine/test_cycle79_collector_task_cancel.py` (3 케이스 — 정적 grep)

| ID | 검증 | Red FAIL 사유 |
|----|------|--------------|
| G-CC1 | `stop()` 본문 AST unparse 결과에 `_api_recovered_collector_task` 참조 ≥ 1건 | 현재 등장 0건 |
| G-CC2 | `stop()` 의 `for task_attr in (...)` 튜플 내에 `"_api_recovered_collector_task"` 문자열 리터럴 ≥ 1건 (AST) | 현재 튜플 미포함 |
| G-CC3 | scheduler.py 전체에서 `"_api_recovered_collector_task"` 문자열 리터럴 등장 ≥ 2건 (stop + finally 양쪽) | 현재 0건 |

### `tests/unit/engine/test_cycle79_task_lifecycle.py` (1 케이스 — asyncio mock)

| ID | 검증 | Red FAIL 사유 |
|----|------|--------------|
| G-LC1 | `stop()` 호출 시 `_api_recovered_collector_task.cancel()` 1회 + setattr None | 현재 task_attrs 미포함 → cancel 0회 |

### `tests/unit/ast/test_cycle79_ast_task_cancel_required.py` (1 케이스 — 영구 가드)

| ID | 검증 | Red FAIL 사유 |
|----|------|--------------|
| G-AST1 | `self._*_task = asyncio.create_task(...)` AST 수집 = `stop()` task_attrs 튜플 (수집 - 튜플 = ∅) | 누락: `_api_recovered_collector_task` 1건 |

## Green 시정안 (backend-dev 인계)

`src/engine/scheduler.py::stop()` (L860~865) + `finally` 블록 (L737~742) 양쪽:

```python
for task_attr in (
    "_next_day_task", "_session_task", "_stale_watcher_task",
    "_session_health_task",
    "_swing_poll_task", "_swing_rest_poll_task",
    "_5xx_dedupe_summary_task",
    "_api_recovered_collector_task",  # 사이클 79 추가 (사이클 76 도입, cancel 누락 시정)
    "_ws_task", "_scan_task",
):
    task = getattr(self, task_attr, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    setattr(self, task_attr, None)
```

## 안전 가드 (CLAUDE.md 영속)

- WebSocket 4중 안전망 호출 시점/횟수 0
- 매도 안전성 / 사이클 38 명문화 / 사이클 17 KIS LMS chain 영향 0
- 사이클 55 R-1 / 66 / 67 / 72~78 모두 무영향
- 운영 영향 0 (lifecycle 영역 정리만, 매매 hot path 무관)
- 사이클 42 `_heartbeat_metrics_loop` 좀비 task 패턴 답습 (영구 가드)
- G-AST1 = 미래 신규 background task 추가 시 cancel 누락 silent 결함 영구 차단

## 검증 명령

```bash
python -m pytest tests/unit/engine/test_cycle79_*.py tests/unit/ast/test_cycle79_*.py -v --tb=short
```
