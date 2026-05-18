# 사이클 13-E-3 — `stop()` 좀비 task 차단 + session-start hook idempotency

> 선행 사이클: 13-E (pool 정리) → 13-E-1 (stop 5종) → 13-E-2 (finally 7종) → **13-E-3 (stop 7종 + hook idempotency)**
> PR #12 (https://github.com/canduk910/auto_stock/pull/12) 신규 Copilot 리뷰 2건 대응.
> 작성: team-leader · 모델: opus · 작업 분배: tdd-engineer → backend-dev → tester.

---

## §1 현상

### ① Copilot 리뷰 — `src/engine/scheduler.py:636` (자금 안전 관련)

> `stop()`에서 `_ws_task`/`_scan_task`를 취소/await하지 않아, 수동 중지 후 빠르게 재시작할 경우
> 이전 task가 살아남아 중복 connect/scan 루프가 재개될 수 있습니다. 특히 `_scan_loop()`는
> `SCAN_INTERVAL` 동안 sleep 후 `_running`이 다시 True면 계속 동작하므로, `stop()`의 task cancel
> 목록에 `_ws_task`, `_scan_task`도 포함해 cancel→await→None 재대입까지 finally와 동일하게
> 정리하는 편이 안전합니다.

(URL: https://github.com/canduk910/auto_stock/pull/12#discussion_r3262475485)

#### 직접 grep 사실관계 — `src/engine/scheduler.py:619~647`

```python
async def stop(self) -> None:
    """매매 프로세스를 중지한다."""
    self._running = False
    # 사이클 13-E-1 리뷰 ② — finally 와 동일한 5종 task cancel.
    # _swing_rest_poll_task 누락 시 disconnect/pool.stop 이후 REST 폴링이 한 사이클 더
    # 돌거나 예외 로그가 발생할 수 있어 finally 와 동일 목록·동일 처리로 통일.
    for task_attr in (
        "_next_day_task", "_session_task", "_stale_watcher_task",
        "_swing_poll_task", "_swing_rest_poll_task",
    ):
        task = getattr(self, task_attr, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        setattr(self, task_attr, None)
    await unsubscribe_all()
    await kis_ws.disconnect()
    # 추가: 수동 중지 시에도 동일 보장
    try:
        from src.realtime.websocket_pool import kis_ws_pool as _wsp
        await _wsp.stop()
    except Exception:
        logger.warning("[scheduler_stop] pool.stop 실패", exc_info=True)
    await write_log("INFO", "매매 시스템 수동 중지")
```

#### finally 블록 (line 500~518) — 이미 7종 (13-E-2 갱신본):

```python
for task_attr in (
    "_next_day_task", "_session_task", "_stale_watcher_task",
    "_swing_poll_task", "_swing_rest_poll_task",
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

**비대칭 사실**: finally 7종 vs stop() 5종 — `_ws_task`/`_scan_task` 누락.

---

### ② Copilot 리뷰 — `.claude/hooks/session-start.sh:27` (환경 위생, 자금 안전 무관)

> 세션 시작마다 `PYTHONPATH` export 라인을 무조건 append(`>>`)해서 같은 세션/프로젝트에서 hook이
> 여러 번 실행되면 `${CLAUDE_ENV_FILE}`이 중복 라인으로 계속 커질 수 있습니다. 기존에 동일 라인이
> 있는지 확인하고 없을 때만 추가하거나, 파일을 재생성/덮어쓰는 방식으로 idempotent하게 만드는
> 것이 좋습니다.

(URL: https://github.com/canduk910/auto_stock/pull/12#discussion_r3262475497)

#### 직접 grep 사실관계 — `.claude/hooks/session-start.sh:27`

```bash
# pytest 가 src/ 를 import 할 때 PYTHONPATH 가 cwd 인지 확인
echo 'export PYTHONPATH="${PYTHONPATH:-}:."' >> "${CLAUDE_ENV_FILE:-/dev/null}"
```

**문제**: `>>` 무조건 append. 동일 세션에서 hook 이 N 회 실행되면 동일 라인 N 개 누적.

---

## §2 근본 원인

### ① 13-E-2 검증 사각지대

13-E-2 작성 시 backend-dev + tester 는 다음과 같이 판단:

> "stop() 단독 호출 경로는 부재 (CLI/Settings UI 모두 미연결) → 5종 유지로 충분"

그러나 이 분석은 **stop→start 빠른 재시작 race 시나리오를 다루지 않음**.

- `_scan_loop()` 는 `SCAN_INTERVAL` (5분) sleep 도중 `_running=False` 시점이 와도 sleep 자체는 깨지지 않음 → cancel 명시 필요
- `_ws_task` 도 `kis_ws.disconnect()` 직후 `await self._ws_task` 가 stop() 에 부재 → 좀비
- `start()` 내부 try 블록 line 493 `await self._ws_task` 는 정상 종료 경로에서만 동작 — 수동 stop 경로는 별개

**Operational risk**: 향후 stop() 가 `/api/system/stop` 또는 `Settings.toggle_auto_start` 로 노출될 가능성 + 테스트 코드에서 `await scheduler.stop()` 직접 호출 시 좀비 task 가 다음 테스트로 전파.

### ② shell hook append 무조건

`echo ... >>` 패턴은 idempotent 하지 않음. Claude Code remote 환경에서 동일 세션 내 hook 재실행이 발생 가능 (re-attach, retry, multi-tab 등).

`${CLAUDE_ENV_FILE}` 가 영구 파일이면 누적분이 다음 세션까지 전파 → PYTHONPATH 가 `:.:.:.:.:.` 로 비대해짐 (실행은 가능하나 위생 불량 + diff 노이즈).

---

## §3 안전성 평가

| 항목 | ① stop() 7종 누락 | ② hook append 무조건 |
|------|------------------|--------------------|
| **자금 안전** | 잠재적 — stop→start race 시 중복 connect 가능, 시세 race | 무관 |
| **운영 영향** | 좀비 task 가 disconnect 후 예외 로그 발생 → system_logs 노이즈 | env 파일 라인 누적 + 진단 어려움 |
| **회귀 위험** | finally 와 stop 의 비대칭 — 13-E-1 통일 원칙 위반 | shell hook 단독 — 코드 영향 없음 |
| **우선순위** | High (TDD 사이클 필수) | Medium (idempotent 가드 작은 fix) |

**결론**: ① 은 자금 안전 잠재 위험 + 13-E-1 원칙 위반 → 7종 통합 필수. ② 는 단순 위생 fix.

---

## §4 Fix 명세

### Patch A — `src/engine/scheduler.py:619~647` stop() 5종 → 7종

**채택 근거** (3 문장 이내):
1. 13-E-2 finally 블록 7종과 **완전히 동일한 tuple** 순서·멤버로 통일 — 비대칭 제거.
2. 좀비 task lifecycle 차단 — `_ws_task`/`_scan_task` 의 `cancel→await→None` 까지 명시.
3. stop() 본문 disconnect/pool.stop 순서는 유지 — task cancel 만 확장 (cancel 후 disconnect 라야 race-free).

**Before (line 622~638)**:
```python
self._running = False
# 사이클 13-E-1 리뷰 ② — finally 와 동일한 5종 task cancel.
for task_attr in (
    "_next_day_task", "_session_task", "_stale_watcher_task",
    "_swing_poll_task", "_swing_rest_poll_task",
):
    task = getattr(self, task_attr, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    setattr(self, task_attr, None)
await unsubscribe_all()
await kis_ws.disconnect()
```

**After**:
```python
self._running = False
# 사이클 13-E-3 — finally 블록 (line 500~518) 과 동일한 7종 task cancel.
# `_ws_task`/`_scan_task` 누락 시 stop→start 빠른 재시작 race 에서
# 좀비 connect 루프 + scan_loop 가 중복 동작 가능 (Copilot 리뷰 #1).
for task_attr in (
    "_next_day_task", "_session_task", "_stale_watcher_task",
    "_swing_poll_task", "_swing_rest_poll_task",
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
await unsubscribe_all()
await kis_ws.disconnect()
```

**불변 보존**: `unsubscribe_all` → `kis_ws.disconnect` → `pool.stop` 순서 동일. 추가 task 2종만 cancel 루프 tuple 에 편입.

---

### Patch B — `.claude/hooks/session-start.sh:27` idempotent guard

**채택 근거** (3 문장 이내):
1. 가장 단순한 (a) 패턴 — `grep -qxF "$LINE" "$FILE" || echo "$LINE" >> "$FILE"` 1줄.
2. `${CLAUDE_ENV_FILE}` 가 `/dev/null` 인 경우 grep -qxF 가 빈 매치로 false → 무조건 append 가 되지만 `/dev/null` 은 write-only 라 누적 위험 없음 (현행 동작 보존).
3. 라인 비교는 `-x` (whole line) + `-F` (fixed string) + `-q` (quiet) 로 partial match/escape 이슈 차단.

**Before (line 26~27)**:
```bash
# pytest 가 src/ 를 import 할 때 PYTHONPATH 가 cwd 인지 확인
echo 'export PYTHONPATH="${PYTHONPATH:-}:."' >> "${CLAUDE_ENV_FILE:-/dev/null}"
```

**After**:
```bash
# pytest 가 src/ 를 import 할 때 PYTHONPATH 가 cwd 인지 확인
# 13-E-3 — hook 다회 실행 시 동일 라인 중복 누적 방지 (Copilot 리뷰 #2).
_PYTHONPATH_LINE='export PYTHONPATH="${PYTHONPATH:-}:."'
_ENV_FILE="${CLAUDE_ENV_FILE:-/dev/null}"
if [ "${_ENV_FILE}" = "/dev/null" ] || ! grep -qxF "${_PYTHONPATH_LINE}" "${_ENV_FILE}" 2>/dev/null; then
  echo "${_PYTHONPATH_LINE}" >> "${_ENV_FILE}"
fi
```

**불변 보존**: `set -euo pipefail` 친화 — `grep -qxF` 가 no-match (rc=1) 일 때 `||` 로 echo 가 실행되며 short-circuit. `2>/dev/null` 는 파일 없을 때 stderr 억제.

---

## §5 회귀 시나리오 (Red Test)

### Test L — stop() 7종 task cancel (NEW, Patch A 핵심)

#### L-1: `_ws_task` cancel/await/None 호출 verify
- Given: `scheduler._ws_task = MagicMock(asyncio.Task)` (done()=False)
- When: `await scheduler.stop()`
- Then: `_ws_task.cancel()` 1회 호출 + `await _ws_task` 발생 + `scheduler._ws_task is None`

#### L-2: `_scan_task` cancel/await/None 호출 verify
- 동일 패턴 (`_scan_task` 대상)

#### L-3 (선택): stop→start 빠른 재시작 시 좀비 task 부재 verify
- 13-E-2 finally cover 와 중복 가능 → tdd-engineer 판단으로 생략 가능

### Test M — 13-E-1 Test F 회귀 가드

- 기존 5종 회귀 가드를 7종으로 갱신:
  - `_next_day_task` + `_session_task` + `_stale_watcher_task` + `_swing_poll_task` + `_swing_rest_poll_task` + `_ws_task` + `_scan_task` 모두 cancel 호출 verify
- tuple 순서가 finally 블록과 동일한지 코드 정합성 확인

### Test N — session-start.sh idempotent (NEW shell test)

- Given: tmp `CLAUDE_ENV_FILE=$(mktemp)`, `CLAUDE_CODE_REMOTE=true`
- When: `bash .claude/hooks/session-start.sh` × 3 회 실행
- Then: `grep -cxF 'export PYTHONPATH="${PYTHONPATH:-}:."' "$CLAUDE_ENV_FILE"` == 1
- 위치 제안: `tests/shell/test_session_start_hook.py` (subprocess + tmp_path fixture) 또는 `tests/test_session_start_hook.sh` (bats/순수 bash). **Python subprocess.run 권장** — pytest 통합 인프라 활용.

---

## §6 안전 가드

- 체결통보 (H0STCNI0/H0STCNI9) 분기 손대지 않음
- `_subscriptions` 직접 수정 없음
- 메인 `kis_ws.disconnect()` 호출 순서 (line 488) 보존
- 13-E + 13-E-1 + 13-E-2 finally 7종 처리 코드 **참조만, 변경 금지**
- stop() 함수 외부 시그니처 변화 없음 (`async def stop(self) -> None`)
- shell hook 의 `set -euo pipefail` 호환성 — `grep` rc=1 가 `||` 로 흡수되어 `pipefail` 트리거 안 함

---

## §7 영향 인덱스

| 변경 파일 | 라인 범위 | 영향 테스트 |
|----------|---------|-----------|
| `src/engine/scheduler.py` | 619~647 (stop) | `tests/test_scheduler_shutdown.py` (Test F 회귀), `tests/test_scheduler_stop_zombie_tasks.py` (NEW Test L) |
| `.claude/hooks/session-start.sh` | 26~27 | `tests/test_session_start_hook.py` (NEW Test N) |

- `tools/test_impact/build_index.py` 재실행 후 affected 갱신 필요
- 프론트엔드 영향 없음

---

## §8 작업 분배

### tdd-engineer (Red 단계)

**파일**: `tests/test_scheduler_stop_zombie_tasks.py` (NEW)
- Test L-1: `_ws_task` cancel/await/None
- Test L-2: `_scan_task` cancel/await/None
- Test M: 7종 tuple 멤버·순서 회귀 가드

**파일**: `tests/test_session_start_hook.py` (NEW)
- Test N: 3회 실행 후 라인 카운트 ≤ 1

**확인**: 두 신규 테스트 모두 Red 상태 (현재 코드에서 FAIL) 확인 → backend-dev 인계.

### backend-dev (Green 단계)

1. `src/engine/scheduler.py` line 627~630 tuple 멤버에 `"_ws_task", "_scan_task"` 추가
2. `.claude/hooks/session-start.sh` line 26~27 idempotent guard 적용
3. `python -m pytest -q tests/test_scheduler_stop_zombie_tasks.py tests/test_session_start_hook.py` 통과 확인

### tester (검증 단계)

1. 영향 인덱스 재빌드 후 affected 테스트 전체 Green 확인
2. PR #12 Copilot 리뷰 2건 resolve 가능 상태 확인 (스레드 reply 또는 resolve action)
3. 13-E-1 Test F + 13-E-2 finally 7종 회귀 모두 Green 확인 (regression coverage)
4. `_workspace/test_report.md` 업데이트 — 13-E-3 항목 추가

---

## §9 검수 체크리스트

1. **stop() tuple = finally tuple** — `("_next_day_task", "_session_task", "_stale_watcher_task", "_swing_poll_task", "_swing_rest_poll_task", "_ws_task", "_scan_task")` 동일 (멤버·순서)
2. **disconnect 순서 보존** — `unsubscribe_all()` → `kis_ws.disconnect()` → `pool.stop()` 순서 유지
3. **hook idempotent verify** — tmp env file 에서 hook 3회 실행 후 라인 == 1
4. **회귀 가드 통과** — 13-E-1 Test F + 13-E-2 finally 7종 + 신규 L/M/N 전부 Green
5. **PR #12 Copilot 2건 resolve** — discussion_r3262475485 + discussion_r3262475497 closed

---

## 부록 A — 다음 단계 tdd-engineer 분배 메시지 초안

> **From**: team-leader · **To**: tdd-engineer · **Cycle**: 13-E-3 Red
>
> PR #12 Copilot 리뷰 2건 (https://github.com/canduk910/auto_stock/pull/12) 대응 — Red 테스트 작성.
>
> **명세**: `/home/user/auto_stock/_workspace/cycle13e3_stop_zombie_and_hook_idempotency_spec.md`
>
> **신규 테스트 2개**:
> 1. `tests/test_scheduler_stop_zombie_tasks.py` — Test L-1/L-2 (`_ws_task`/`_scan_task` cancel·await·None), Test M (7종 tuple 회귀 가드)
> 2. `tests/test_session_start_hook.py` — Test N (subprocess 3회 실행 후 `grep -cxF` 카운트 == 1)
>
> **기준점**:
> - `src/engine/scheduler.py:619~647` stop() 현재 5종 → 7종 확장 대상
> - finally 블록 (line 500~518) 은 이미 7종 — **읽기 전용** 참조
> - `.claude/hooks/session-start.sh:27` 무조건 append → idempotent guard 대상
>
> **확인**: 두 테스트 모두 현재 코드에서 FAIL(Red) → backend-dev 인계 시 명시.
>
> **금지**: 체결통보 분기, `_subscriptions`, 메인 disconnect 순서, 13-E 계열 finally 코드 수정.
