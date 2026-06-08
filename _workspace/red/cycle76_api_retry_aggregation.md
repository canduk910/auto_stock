# 사이클 76 Red — `_request` 5xx WARNING dedupe + recovered 5분 collector

**카드**: #23 (MEDIUM) api retry 5.80x dup 시정
**날짜**: 2026-06-08
**전략 결정**: E (사이클 18 dedupe + 사이클 74 collector 하이브리드 — **15 사이클 연속 옵션 A 패턴 영속**)
**Red 단계 산출**: tdd-engineer

---

## 1. 명세 분해 (4 의제 → 15 케이스)

### 의제 1 — `_request` 메인 60s WARNING dedupe (사이클 18 답습)

**결함 사이트**: `src/api/base.py::_request` L358 `logger.warning("HTTP %s (attempt %d/%d): %s", ...)` 직접 호출 — **사이클 18 dedupe 미적용** (사이클 18 은 `_request_via_quote_pool` 풀 영역만 시정).

**도입 사양**:
- 모듈 상수 `_REQUEST_5XX_DEDUPE_WINDOW = 60.0`
- 모듈 상태 `_request_5xx_dedupe: dict[(path, status), (window_start_loop_ts, count)]`
- 락 `_request_5xx_dedupe_lock = asyncio.Lock()`
- 헬퍼 `_record_request_5xx_for_dedupe(path: str, status: int) -> bool` (should_emit 반환)
- 호출자 `_request` L358 분기: `should_emit = await _record_request_5xx_for_dedupe(path, status); if should_emit: logger.warning(...)`

**Q4 (사용자 결정)**: 메인 + 풀 dedupe state **분리** — 사이클 18 `_quote_5xx_dedupe` 비침범.

**케이스 (4)** — `tests/unit/api/test_cycle76_request_5xx_dedupe.py`:
| ID | 시나리오 | 예상 (Red) | 예상 (Green) |
|----|---------|-----------|-------------|
| G-MD1 | 첫 호출 → should_emit=True + count=1 | FAIL (헬퍼 미존재) | PASS |
| G-MD2 | 동일 키 5회 → 첫 True + 4 False + count=5 | FAIL | PASS |
| G-MD3 | 60s 만료 후 → True + 카운트 1 리셋 (monkeypatch loop.time) | FAIL | PASS |
| G-MD4 | 다른 path/status → 독립 dedupe + 풀 state 비침범 (Q4) | FAIL | PASS |

### 의제 2 — `[api_retry_recovered]` 5분 collector (사이클 74 답습)

**결함 사이트**:
- `_request` L422~428 직접 write_log `[api_retry_recovered] path=... attempts=N` 1행/매 호출 emit
- `_request_via_quote_pool` L688~702 `_quote_request_metrics["retry_recovered"] += 1` (write_log 없음, 단 의제는 양쪽 collector 분리)

**도입 사양**:
- 모듈 상수 `_API_RECOVERED_COLLECTOR_WINDOW = 300.0`
- 메인 상태 `_api_recovered_collector: dict[str, int]` (path → count)
- 풀 상태 `_quote_recovered_collector: dict[str, int]` (path → count) — **Q4 분리**
- 헬퍼:
  - `_record_api_recovered(path: str) -> None` — 메인 _request 경유
  - `_record_quote_recovered(path: str) -> None` — 풀 _request_via_quote_pool 경유
  - `_flush_api_recovered_collector() -> None` — 메인 1행 summary + clear
  - `_flush_quote_recovered_collector() -> None` — 풀 1행 summary + clear
- 호출자 `_request` rt_cd=0 + attempt > 1 분기: 기존 write_log 제거 → `_record_api_recovered(path)` 호출
- 호출자 `_request_via_quote_pool` rt_cd=0 + attempt > 1 분기: `_record_quote_recovered(path)` 호출
- 5분 주기 task: scheduler `_api_recovered_collector_loop` (별개 사이클 inject, 본 사이클 헬퍼 자체 검증)

**summary 메시지 포맷**: `[api_retry_recovered_summary] window=300s total=N by_path={path:count, ...}`

**Q2 (사용자 결정)**: 빈 윈도우 (count=0) → flush emit 0 (no-op).

**케이스 (4)** — `tests/unit/api/test_cycle76_recovered_collector.py`:
| ID | 시나리오 | 예상 (Red) | 예상 (Green) |
|----|---------|-----------|-------------|
| G-RC1 | 메인 5회 record + flush → 1행 summary + total=5 + window=300s | FAIL | PASS |
| G-RC2 | by_path 통계 (path_a:3, path_b:2) + flush 후 state clear | FAIL | PASS |
| G-RC3 | 빈 윈도우 flush → emit 0 (Q2) | FAIL | PASS |
| G-RC4 | 메인 + 풀 state 분리 + 각각 별도 flush (총 2행) | FAIL | PASS |

### 의제 3 — ERROR 보존 매트릭스 영속 (결정 Y, 변경 0)

**핵심**: recovered 만 흡수, exhausted + kis_rejection 은 individual 영속 (사이클 29 005935 LMS chain 진단 의무 + CLAUDE.md "절대 깨지 말 것").

**케이스 (4)** — `tests/unit/api/test_cycle76_error_preservation_matrix.py`:
| ID | 사이트 | 영속 의무 | 예상 (Red+Green) |
|----|--------|---------|---------------|
| G-ERR1 | `_request` 5xx exhausted → `[api_retry_exhausted] last_status=503` | PR-B 영속 | **PASS** |
| G-ERR2 | `_request` 네트워크 exhausted → `[api_retry_exhausted] last_status=network` | PR-B 영속 | **PASS** |
| G-ERR3 | `_request` 토큰 만료 exhausted → `[api_retry_exhausted] last_status=token_expired` | PR-B (Codex) | **PASS** |
| G-ERR4 | `_request` rt_cd != "0" → `[kis_rejection]` + 민감 키 마스킹 | A1 / CLAUDE.md | **PASS** |

### 의제 4 — AST 영구 가드 (Q1, 사이클 74 G-7/G-8 답습)

**케이스 (3)** — `tests/unit/ast/test_cycle76_ast_api_retry_helper.py`:
| ID | 가드 | 예상 (Red) | 예상 (Green) |
|----|------|-----------|-------------|
| G-AST1 | `_request` 본문 `logger.warning("HTTP ...")` 직접 호출 0건 | FAIL (L358) | PASS |
| G-AST2 | `_request_via_quote_pool` 본문 `_record_5xx_for_dedupe` 호출 ≥ 1건 (사이클 18 영속) | **PASS** | PASS |
| G-AST3 | `_request` + `_request_via_quote_pool` 본문 `[api_retry_recovered]` 직접 write_log 0건 | FAIL (L422) | PASS |

`[api_retry_recovered_summary]` prefix 는 collector flush 단독 → 검출에서 제외 (allowed prefix).

---

## 2. Red 검증 결과 (3 회 반복)

```bash
python -m pytest tests/unit/api/test_cycle76_*.py tests/unit/ast/test_cycle76_*.py -v --tb=short
```

| Run | 결과 | 소요 |
|-----|------|------|
| 1 | **10 failed, 5 passed** | 0.12s |
| 2 | **10 failed, 5 passed** | 0.12s |
| 3 | **10 failed, 5 passed** | 0.12s |

**flakiness 0** (3 회 동일 결과 ±0.0s).

### Red 결과 세부 (명세 예측 100% 일치)

**FAIL (10)** — Green 발주 대상:
- `test_g_md1_first_5xx_emits_warning_and_count_one` — `_record_request_5xx_for_dedupe` 미존재
- `test_g_md2_repeated_5xx_within_window_suppresses_warning` — 헬퍼 미존재
- `test_g_md3_5xx_after_window_expiry_emits_again_and_resets_count` — 헬퍼 미존재
- `test_g_md4_different_keys_tracked_independently` — 헬퍼 미존재
- `test_g_rc1_5min_window_5_recovered_emits_one_summary_row` — `_record_api_recovered` 미존재
- `test_g_rc2_by_path_aggregation_accurate` — 헬퍼 미존재
- `test_g_rc3_empty_window_skips_emit` — `_flush_api_recovered_collector` 미존재
- `test_g_rc4_main_and_quote_collectors_separated` — `_record_quote_recovered` 미존재 (Q4)
- `test_g_ast1_request_no_direct_logger_warning_http` — L358 직접 `logger.warning("HTTP ")`
- `test_g_ast3_request_no_direct_api_retry_recovered_write_log` — L422 직접 `[api_retry_recovered]` write_log

**PASS (5)** — 영속 영역 (사이클 18/29 보존):
- `test_g_err1_api_retry_exhausted_5xx_individual_preserved`
- `test_g_err2_api_retry_exhausted_network_individual_preserved`
- `test_g_err3_api_retry_exhausted_token_expired_individual_preserved`
- `test_g_err4_kis_rejection_individual_preserved`
- `test_g_ast2_request_via_quote_pool_dedupe_helper_call_preserved`

---

## 3. Green 발주 사양 (backend-dev 인계)

### 영역 A — `_request` 5xx WARNING dedupe (메인)

**위치**: `src/api/base.py` L130 `_record_5xx_for_dedupe` 헬퍼 직전 또는 직후 모듈 영역.

```python
# 사이클 76 — 메인 _request 5xx WARNING dedupe (사이클 18 답습, Q4 별도 state)
_REQUEST_5XX_DEDUPE_WINDOW = 60.0  # seconds
_request_5xx_dedupe: dict[tuple[str, int], tuple[float, int]] = {}
_request_5xx_dedupe_lock = asyncio.Lock()


async def _record_request_5xx_for_dedupe(path: str, status: int) -> bool:
    """메인 _request 5xx 기록 후 should_emit 반환 (사이클 18 패턴 답습).

    Returns: True 면 호출자가 logger.warning 1회. False 면 억제.
    """
    now = asyncio.get_event_loop().time()
    async with _request_5xx_dedupe_lock:
        key = (path, status)
        entry = _request_5xx_dedupe.get(key)
        if entry is None or (now - entry[0]) > _REQUEST_5XX_DEDUPE_WINDOW:
            _request_5xx_dedupe[key] = (now, 1)
            return True
        _request_5xx_dedupe[key] = (entry[0], entry[1] + 1)
        return False
```

**호출자 변경** (L351~365 분기):
```python
except httpx.HTTPStatusError as e:
    status = e.response.status_code
    if 500 <= status < 600:
        _request_metrics["http_5xx"] += 1
        _request_metrics["by_path_5xx"][path] += 1
    elif 400 <= status < 500:
        _request_metrics["http_4xx"] += 1
    # 사이클 76 — 5xx 만 dedupe (4xx 영구 에러는 그대로 매 호출 WARNING)
    should_emit_warning = True
    if 500 <= status < 600:
        try:
            should_emit_warning = await _record_request_5xx_for_dedupe(path, status)
        except Exception:
            logger.debug(
                "[api_request] _record_request_5xx_for_dedupe 실패 — WARNING fallback",
                exc_info=True,
            )
    if should_emit_warning:
        logger.warning(
            "HTTP %s (attempt %d/%d): %s",
            status, attempt, MAX_RETRIES, path,
        )
    # ... 나머지 흐름 보존
```

### 영역 B — recovered 5분 collector (메인 + 풀)

```python
# 사이클 76 — [api_retry_recovered] 5분 collector (사이클 74 답습, Q4 분리)
_API_RECOVERED_COLLECTOR_WINDOW = 300.0  # 5분
_api_recovered_collector: dict[str, int] = {}
_quote_recovered_collector: dict[str, int] = {}


def _record_api_recovered(path: str) -> None:
    """메인 _request rt_cd=0 + attempt > 1 분기에서 호출 — 5분 누적."""
    _api_recovered_collector[path] = _api_recovered_collector.get(path, 0) + 1


def _record_quote_recovered(path: str) -> None:
    """풀 _request_via_quote_pool rt_cd=0 + attempt > 1 분기에서 호출 (Q4 분리)."""
    _quote_recovered_collector[path] = _quote_recovered_collector.get(path, 0) + 1


async def _flush_api_recovered_collector() -> None:
    """5분 주기 task 호출 — 메인 collector 1행 summary + clear (Q2: 빈 윈도우 skip)."""
    if not _api_recovered_collector:
        return  # Q2 — 빈 윈도우 emit 0
    total = sum(_api_recovered_collector.values())
    by_path_str = ", ".join(
        f"{p}:{c}" for p, c in sorted(_api_recovered_collector.items())
    )
    _log_msg = (
        f"[api_retry_recovered_summary] window={_API_RECOVERED_COLLECTOR_WINDOW:.0f}s "
        f"total={total} by_path={{{by_path_str}}}"
    )
    _api_recovered_collector.clear()
    try:
        await _system_logs.write_log("INFO", _log_msg)
    except Exception:
        pass


async def _flush_quote_recovered_collector() -> None:
    """5분 주기 task 호출 — 풀 collector 1행 summary + clear (Q2: 빈 윈도우 skip, Q4 분리)."""
    if not _quote_recovered_collector:
        return
    total = sum(_quote_recovered_collector.values())
    by_path_str = ", ".join(
        f"{p}:{c}" for p, c in sorted(_quote_recovered_collector.items())
    )
    _log_msg = (
        f"[api_retry_recovered_summary] window={_API_RECOVERED_COLLECTOR_WINDOW:.0f}s "
        f"total={total} by_path={{{by_path_str}}}"
    )
    _quote_recovered_collector.clear()
    try:
        await _system_logs.write_log("INFO", _log_msg)
    except Exception:
        pass
```

**호출자 변경**:
- `_request` L418~428 분기: 기존 try/write_log 제거 → `_record_api_recovered(path)` 단일 호출
- `_request_via_quote_pool` L688~702 분기: `_quote_request_metrics["retry_recovered"] += 1` 보존 + `_record_quote_recovered(path)` 추가

**5분 주기 task 인입** (별개 후속 사이클 또는 본 사이클 마지막에 scheduler 통합):
- `scheduler.py::_boot()` 가 `_api_recovered_collector_loop()` task 생성
- 5분 sleep loop → `_flush_api_recovered_collector()` + `_flush_quote_recovered_collector()` 순차 호출

---

## 4. 안전 규칙 + 영속 의무

**변경 0 영역**:
- `[api_retry_exhausted]` 3 영역 (5xx/네트워크/토큰) — individual ERROR write_log 영속
- `[kis_rejection]` (CLAUDE.md "절대 깨지 말 것") — individual ERROR + 민감 키 마스킹 영속
- `_record_5xx_for_dedupe` (사이클 18) + `_quote_5xx_dedupe` state — 풀 영역 영속
- 사이클 17 OPSP0002 backoff (`websocket.py`) — 본 사이클 범위 외
- 사이클 72 `_DbLogHandler` 500ms dedupe (`main.py`) — 본 사이클 범위 외

**자금 안전 영향 0**:
- 메인 `_request` 가 매매/잔고/체결조회 호출의 단일 진입점 — dedupe 추가는 *로그* 영역만 (호출 흐름 / 재시도 정책 / raise 동작 무변경)
- recovered collector 가 write_log를 *지연* (5분 누적) — chain 진단은 exhausted (individual) 가 영속
- 운영 14:50+ KST 메인 진입 중이지만 Red 단계는 test 작성만 (production code 변경 0)

---

## 5. 산출물 경로 (총 5 파일)

| 경로 | 케이스 |
|------|--------|
| `tests/unit/api/test_cycle76_request_5xx_dedupe.py` | G-MD1~MD4 (4) |
| `tests/unit/api/test_cycle76_recovered_collector.py` | G-RC1~RC4 (4) |
| `tests/unit/api/test_cycle76_error_preservation_matrix.py` | G-ERR1~ERR4 (4) |
| `tests/unit/ast/test_cycle76_ast_api_retry_helper.py` | G-AST1~AST3 (3) |
| `_workspace/red/cycle76_api_retry_aggregation.md` | 본 명세 |

**총 15 케이스** (의제 1+2+3+4 = 4+4+4+3).

---

## 6. Green 후 영구 가드 효과

- G-AST1: 미래 신규 `logger.warning("HTTP ...")` 사이트 추가 시 즉시 FAIL (silent 결함 영구 차단)
- G-AST2: 사이클 18 dedupe 헬퍼 호출 사이트 제거 시 즉시 FAIL (사이클 18 회귀 차단)
- G-AST3: 미래 신규 `[api_retry_recovered]` 직접 write_log 사이트 추가 시 즉시 FAIL

**예상 dup 감소율**: 5.80x → ≤2.0x (사이클 74 ws_action collector 6.68x→2.0x 효과 답습).
