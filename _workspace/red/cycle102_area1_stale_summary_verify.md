# Cycle 102 Red 명세 — 영역 1: 사이클 78 silent 결함 영구 확인

**명세 출처**: `_workspace/cycle102_phase2_design.md` §영역 1 + `_workspace/cycle102_domain_consult.md` §A6
**위급도**: HIGH (부차) — 코드 변경 0 (영구 확인 의무만)
**행위**: 사이클 78 시정 영역 (`scheduler.py::_api_recovered_collector_loop` 본체 + `stop()` lifecycle hook) 영구 영속 확인 + `[stale_watcher_summary]` 5분 주기 emit 정상 발화 영속 + 영구 가드 5 신설 (회귀 방지)

## 사용자 결정 (영속)

- **Q71=A**: 사이클 78 + 외부 의견 가시화 + force_retry 임계 통합 (3 영역 단일 사이클)
- **영역 1 코드 변경 0 의무**: 사이클 78 영속 영역 영구 확인만 (G-78-VERIFY-1~5 신설)

## 결정적 발견 (운영 실측)

- `[stale_watcher_summary]` **0건/7일** (사이클 78 시정 commit `0017fe0`+`0d633a8` 배포 후 영구 0건)
- 가설 3 분리: (1) 코드 영역 결함 / (2) 배포 미반영 / (3) 운영 환경 분리 결함
- 영역 1 = 가설 (1) 영구 차단 확정 의무 (G-78-VERIFY-1~5)

## Production 영속 영역 (변경 0 의무)

### `src/engine/scheduler.py::_api_recovered_collector_loop` (L2529~L2567)

```python
async def _api_recovered_collector_loop(self) -> None:
    """사이클 76 (2026-06-08) — [api_retry_recovered] 5분 collector flush task."""
    from src.api.base import (
        _API_RECOVERED_COLLECTOR_WINDOW,
        _flush_api_recovered_collector,
        _flush_quote_recovered_collector,
    )
    from src.engine.stale_watcher_core import flush_stale_watcher_collector

    while self._running:
        await asyncio.sleep(_API_RECOVERED_COLLECTOR_WINDOW)
        # ...api flush 4 줄...
        # 사이클 78 hotfix: flush 호출 사이트 0건 (메모리 leak HIGH) 시정
        try:
            flush_swing_rest_poll_collector()
        except Exception:
            logger.exception("[swing_rest_poll_collector] flush 실패")
        try:
            flush_stale_watcher_collector()
        except Exception:
            logger.exception("[stale_watcher_collector] flush 실패")
        if not self._running:  # ← flush 4 줄 *이후* 위치 (사이클 78 의도 영속)
            break
```

### `src/engine/scheduler.py::stop()` (L920~L930 영역)

```python
# 사이클 78 hotfix: 잔존 collector 마지막 flush (Q5 사이클 74 G-SP4 답습)
try:
    flush_swing_rest_poll_collector()
except Exception:
    logger.exception("[swing_rest_poll_collector] shutdown flush 실패")
try:
    from src.engine.stale_watcher_core import flush_stale_watcher_collector
    flush_stale_watcher_collector()
except Exception:
    logger.exception("[stale_watcher_collector] shutdown flush 실패")
```

## Red 케이스 5 (HIGH 5)

| 가드 | 위급도 | 파일 | 영역 |
|------|------|------|------|
| **G-78-VERIFY-1** | HIGH | `tests/unit/engine/test_cycle102_stale_summary_emit.py` | `record_stale_watcher_check` *후* `flush_stale_watcher_collector` 호출 → `[stale_watcher_summary]` 1행 emit (mock + freezegun) |
| **G-78-VERIFY-2** | HIGH | `tests/unit/ast/test_cycle102_ast_flush_call_sites.py` | `_api_recovered_collector_loop` body AST = `flush_stale_watcher_collector` 호출 ≥1 + `flush_swing_rest_poll_collector` 호출 ≥1 |
| **G-78-VERIFY-3** | HIGH | `tests/unit/ast/test_cycle102_ast_flush_call_sites.py` | `stop()` lifecycle hook AST = 양쪽 flush 호출 ≥1 (사이클 78 G-AST1 영속 영구 확인) |
| **G-78-VERIFY-4** | MEDIUM | `tests/unit/ast/test_cycle102_ast_flush_call_sites.py` | `if not self._running: break` 위치 영속 (flush 4 줄 *이후*, 사이클 78 의도 마지막 1회 flush 보장) AST |
| **G-78-VERIFY-5** | MEDIUM | `tests/unit/engine/test_cycle102_stale_summary_emit.py` | empty collector 상태 `flush_stale_watcher_collector()` 호출 → emit 0 (no-op, 사이클 78 영역 영속) |

## Red 검증 명령

```bash
python -m pytest -x tests/unit/engine/test_cycle102_stale_summary_emit.py tests/unit/ast/test_cycle102_ast_flush_call_sites.py -v
# 영역 1 = 코드 변경 0 의무 → 사이클 78 영속이 정상이면 G-78-VERIFY 5/5 PASS
# (즉 사이클 78 영속 영역 검증 = Red 단계에서 즉시 PASS 영역 — 영구 가드 신설 목적)
```

## 영속 의무 매트릭스

- 사이클 17 OPSP0002 backoff 300s 영속 (변경 0)
- 사이클 29 R1/R2/R3 영속 (변경 0)
- 사이클 32 R4 universe guard 영속 (변경 0)
- 사이클 66 cap=10 priority 분리 영속 (변경 0)
- 사이클 67 stale_manager 4 sub-module 영속 (변경 0)
- **사이클 78 G-AST1 flush 호출 사이트 영속** (영역 1 영구 확인 핵심)
- 사이클 79 G-AST2 task cancel 영속 (변경 0)
- 4중 안전망 영속 (F1 + scan_loop + K + priority)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

## Green 인계 (backend-dev)

영역 1 = **코드 변경 0 의무** (사이클 78 영속 영역 영구 확인만). Green 단계 = 가드 5 추가만 + production 무변경.

## Refactor (영역 1)

- 영역 1 = refactor 영역 외 (영구 확인만)
- 영향 인덱스 갱신: `python tools/test_impact/build_index.py`
