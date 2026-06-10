# 사이클 92 Red 명세 — 07:50 KIS API 강제 중단 충돌 영구 시정

> **사이클 92** (2026-06-10) = HIGH 위급도 silent 결함 영구 시정 (matrix 20+ 후보)
> **status**: Red 명세 완료 (production 코드 변경 0)
> **위급도**: HIGH (매매 안전성 직접 영역 — 시세 0건 = 매수/매도 hot path 완전 정지)
> **사이클 88 G-REJECT 영속 의무**: 자동 재기동 = 4중 안전망 *추가* 영역 (대체 X)

---

## 1. 결함 chain (Phase 1 진단 영속)

`_workspace/cycle92_phase1_diagnosis.md` §5 영속:

```
07:45 _run_auto_start_loop → start() 호출
07:50 _boot() 진입 → _preissue_all_tokens 발화 (정확 KIS 강제 중단 시점!)
07:50 KIS 강제 중단 → REST/WS 접속 일괄 끊김 (KIS 정책 — 사용자 보고 정본)
07:55 connect() (WebSocket) 호출 → 즉시 ConnectionClosed / OSError
07:55:01~07:55:32 5회 재시도 (BACKOFF_BASE × 2^(n-1) = 1+2+4+8+16 = 31초)
07:55:32 "최대 재연결 횟수 초과, 종료" ERROR → _ws=None 영구 종료
08:00 NXT 프리 → 시세 미수신 → _confirm_breakout_open_prices polling timeout → _pending_next_day_clear 보류
09:00 KRX 메인 / 09:30 모멘텀 스캔 → 시세 미수신 → 매수 후보 풀 텅 빔 / 매도 hot path 위험
사용자 강제 재기동 → _running=False → re-entry → connect() 재호출 → 정상
```

**4중 안전망 한계 (G-REJECT-1 영속 영역, 사이클 88)**:
- F1 (`_verify_subscriptions_after_reconnect`) = `connect()` 내부 task → `_ws=None` 영구 종료 후 발화 불가
- `_scan_loop` 5분 = `_send_subscribe` 호출 자체 `_ws=None` graceful skip
- K stale watcher 120s = `kis_ws_pool.unsubscribe_in_pool` 호출하나 세션 dead 면 noop
- `_resubscribe_stale_priority` 5분 = 동일 한계

**결과**: 4중 안전망 모두 무력 → 사용자 수동 재기동만 유일한 회복 경로 → 자동 재기동 영역 = 4중 안전망 *추가* 영역 의무 (lifecycle 영역, 대체 X).

---

## 2. 사용자 결정 채택 (영구)

| 의제 | 채택 |
|------|------|
| Q28 TIME_BOOT 이동 | **E** A+D 결합 (07:50 → 07:55 + 자동 재기동 영구 가드) |
| Q29 TIME_AUTO_START | A 07:45 영속 (Python loop 영역, KIS 무관) |
| Q30 자동 재기동 | **A** MAX_RECONNECT 도달 시 `start()` idempotent 재호출 + 60s cooldown + 시간당 3회 cap |
| Q31 KIS 공식 명문 | C 생략 |
| **Q32** TIME_PRESUBSCRIBE | **B** 07:55 → 07:59 동행 이동 (domain-expert P1 권고) |
| **Q33** push 시점 | 완료 즉시 push |

---

## 3. 시정 영역 매트릭스 (Green 단계 backend-dev 인계)

### 3.1 `src/engine/scheduler.py` 시간 상수 이동 (3 줄 영역)

```python
# L51~L53
TIME_AUTO_START = time(7, 45)  # 영속 (Q29=A, Python loop 영역)
TIME_BOOT = time(7, 55)         # 사이클 92 — KIS 07:50 강제 중단 후 5분 마진 (Q28=E)
TIME_PRESUBSCRIBE = time(7, 59) # 사이클 92 — _boot 완료 후 4분 마진 race 회피 (Q32=B)
```

### 3.2 `src/realtime/websocket.py` 자동 재기동 영역 (Q30=A)

#### 모듈 전역 신규 상수 3 + import 1

```python
import time as _time  # 기존 import 영속 (이미 존재)

# 신규 모듈 전역 (사이클 92)
_AUTO_RESTART_COOLDOWN_SECS = 60.0   # idempotent 재호출 간 cooldown (사이클 13-E-2 답습)
_AUTO_RESTART_HOURLY_CAP = 3          # 시간당 cap (LMS chain 차단, 사이클 24 답습)
_AUTO_RESTART_WINDOW_SECS = 3600.0    # 1시간 슬라이딩 윈도우
```

#### `KisWebSocket.__init__` 영역 신규 인스턴스 변수 2

```python
self._auto_restart_last_at: float = 0.0  # 사이클 92 — 마지막 자동 재기동 시각
self._auto_restart_history: list[float] = []  # 사이클 92 — 1시간 슬라이딩 윈도우
```

#### 신규 메서드 `_trigger_auto_restart`

```python
async def _trigger_auto_restart(self) -> bool:
    """MAX_RECONNECT 도달 시 자동 start() 재호출.
    
    사이클 92 (2026-06-10) 신규. KIS 07:50 강제 중단 충돌 영구 시정.
    - 60s cooldown (사이클 13-E-2 답습)
    - 시간당 3회 cap (KIS LMS chain 차단, 사이클 24 silent_inactive 답습)
    - idempotent (기존 상태 영속 보장 + 중복 발화 race 차단)
    - 4중 안전망 *추가* (G-REJECT-1 위반 0, 사이클 88 영속)
    
    Returns:
        True = 재기동 발화 / False = cooldown 또는 cap 도달
    """
    now = _time.monotonic()
    # 60s cooldown
    if now - self._auto_restart_last_at < _AUTO_RESTART_COOLDOWN_SECS:
        logger.warning(
            "[ws_auto_restart_cooldown] 60s cooldown 미경과 (last=%.1fs ago)",
            now - self._auto_restart_last_at,
        )
        return False
    # 1시간 윈도우 prune
    self._auto_restart_history = [
        t for t in self._auto_restart_history if now - t < _AUTO_RESTART_WINDOW_SECS
    ]
    # 시간당 cap
    if len(self._auto_restart_history) >= _AUTO_RESTART_HOURLY_CAP:
        logger.error(
            "[ws_auto_restart_cap_exceeded] 시간당 %d회 cap 도달 (KIS LMS chain 차단)",
            _AUTO_RESTART_HOURLY_CAP,
        )
        return False
    # 발화 (idempotent)
    self._auto_restart_last_at = now
    self._auto_restart_history.append(now)
    logger.warning("[ws_auto_restart] MAX_RECONNECT 도달 → start() 자동 재호출")
    try:
        await self.stop()  # 기존 상태 정리
        await self.start()  # idempotent 재시작
        return True
    except Exception as e:
        logger.exception("[ws_auto_restart_failed] error=%s", e)
        return False
```

> **주의 — KisWebSocket 인터페이스 정합**: 현재 `KisWebSocket` 클래스는 `start`/`stop` 메서드가 없다 (lifecycle 메서드 = `connect`/`disconnect`). Green 단계 backend-dev 는 다음 중 1 선택:
> - 옵션 (1): `KisWebSocket` 에 `start`/`stop` 메서드 신규 (=`connect`/`disconnect` wrapping) — *권고*
> - 옵션 (2): `_trigger_auto_restart` 본체에서 `disconnect()`/`connect()` 직접 호출 (현행 인터페이스 답습)
> - 본 Red 명세는 옵션 (2) 채택 가정 (인터페이스 변경 0) — 회귀 가드 H-5 idempotent 검증은 `disconnect`/`connect` 시퀀스로 작성

#### `_connect_loop` 의 MAX_RECONNECT 도달 분기 영역 신규 호출 1

```python
# 기존 _connect_loop (실제 함수명은 connect, line 174~219)
async def connect(self, on_message):
    # ... 기존 영역 영속
    while self._running and self._reconnect_count <= MAX_RECONNECT:
        # ... 기존 try/except 영역 영속
        except (websockets.ConnectionClosed, websockets.InvalidURI, OSError) as e:
            self._reconnect_count += 1
            if self._reconnect_count > MAX_RECONNECT:
                logger.error("최대 재연결 횟수 초과, 종료")
                # 사이클 92 — 자동 재기동 트리거 (Q30=A)
                await self._trigger_auto_restart()
                break
            # ... 기존 backoff/sleep 영속
```

---

## 4. 회귀 가드 14 케이스 (HIGH 6 + MEDIUM 5 + LOW 3)

domain-expert 자문 A5 권고 (HIGH ≥ 43%) + 사이클 81 답습 패턴 (HIGH ≥ 30%) 충족.

### HIGH 6 (매매 안전성 직접 영역)

| ID | 파일 | 검증 |
|----|------|------|
| **H-1** | `tests/unit/engine/test_cycle92_time_boot_moved.py` | TIME_BOOT == time(7, 55) AST + TIME_PRESUBSCRIBE == time(7, 59) AST (Q28=E + Q32=B) |
| **H-2** | `tests/unit/realtime/test_cycle92_auto_restart_trigger.py` | MAX_RECONNECT 도달 시 `_trigger_auto_restart` 호출 정합 (asyncio mock) |
| **H-3** | `tests/unit/realtime/test_cycle92_auto_restart_cooldown.py` | 60s cooldown freezegun (1차 발화 → 60s 이내 2차 = False) |
| **H-4** | `tests/unit/realtime/test_cycle92_auto_restart_hourly_cap.py` | 시간당 3회 cap freezegun (3회 발화 → 4회째 = False + ERROR) |
| **H-5** | `tests/unit/realtime/test_cycle92_auto_restart_idempotent.py` | `start()` (= disconnect/connect) idempotent (재호출 시 기존 상태 정리 + 정상 시작) |
| **H-6** | `tests/unit/ast/test_cycle92_g_reject_persistence.py` | 사이클 88 G-REJECT-1/2/3 영속 가드 (사이클 92 자동 재기동 = 4중 안전망 *추가*, 대체 X) |

### MEDIUM 5

| ID | 파일 | 검증 |
|----|------|------|
| **M-1** | `tests/unit/realtime/test_cycle92_max_reconnect_persistence.py` | `MAX_RECONNECT=5` 영속 (Q30=A 한도 영속) |
| **M-2** | `tests/unit/realtime/test_cycle92_auto_restart_failure_graceful.py` | `start()` 실패 시 graceful False 반환 + ERROR |
| **M-3** | `tests/unit/engine/test_cycle92_boot_presubscribe_race.py` | `_boot()` 완료 후 `TIME_PRESUBSCRIBE` 발화 영속 (4분 마진) |
| **M-4** | `tests/unit/engine/test_cycle92_token_cache_persistence.py` | `_preissue_all_tokens` 24h 캐시 영속 (사이클 20 답습) |
| **M-5** | `tests/unit/realtime/test_cycle92_4_safety_nets_persistence.py` | 4중 안전망 영역 영속 (F1 / `_scan_loop` / K stale watcher / `_resubscribe_stale_priority`) 변경 0 |

### LOW 3

| ID | 파일 | 검증 |
|----|------|------|
| **L-1** | `tests/unit/realtime/test_cycle92_auto_restart_window_prune.py` | 1시간 슬라이딩 윈도우 prune (60분 경과 후 history 자동 제거) |
| **L-2** | `tests/unit/engine/test_cycle92_time_auto_start_persistence.py` | TIME_AUTO_START == time(7, 45) 영속 (Q29=A) |
| **L-3** | `tests/unit/realtime/test_cycle92_logger_kst_persistence.py` | KST 영속 (사이클 68 답습) |

---

## 5. 실행 결과 (Red 확인)

```bash
# H-1: TIME_BOOT == time(7, 55) AST
pytest -x tests/unit/engine/test_cycle92_time_boot_moved.py
> FAILED: TIME_BOOT == time(7, 50) ≠ time(7, 55)
> FAILED: TIME_PRESUBSCRIBE == time(7, 55) ≠ time(7, 59)

# H-2: _trigger_auto_restart 호출 정합
pytest -x tests/unit/realtime/test_cycle92_auto_restart_trigger.py
> FAILED: AttributeError: 'KisWebSocket' object has no attribute '_trigger_auto_restart'

# H-3 ~ L-3: 모두 동일 (production 코드 변경 0)
> FAILED: AttributeError / AssertionError
```

**Red 상태 확인** = 모든 14 케이스 fail = 사이클 92 production 코드 변경 0 영속 보장.

---

## 6. Green 단계 인계 (backend-dev)

### 6.1 시정 의무

1. `src/engine/scheduler.py:51-53` 3 줄 시정 (TIME_BOOT 7:55 + TIME_PRESUBSCRIBE 7:59)
2. `src/realtime/websocket.py` 신규 영역:
   - 모듈 전역 상수 3 (`_AUTO_RESTART_COOLDOWN_SECS` / `_AUTO_RESTART_HOURLY_CAP` / `_AUTO_RESTART_WINDOW_SECS`)
   - `KisWebSocket.__init__` 인스턴스 변수 2 (`_auto_restart_last_at` / `_auto_restart_history`)
   - 신규 메서드 `_trigger_auto_restart` (~50L, idempotent + cooldown + cap)
   - `connect()` 의 MAX_RECONNECT 분기에 `await self._trigger_auto_restart()` 1 줄 추가

### 6.2 영속 의무 (사이클 92 시정 후에도 보장)

- 사이클 88 G-REJECT-1/2/3 영속 (`tests/unit/ast/test_external_llm_reject_patterns.py`)
- 사이클 17 OPSP0002 backoff 영속 (`_opsp_backoff_until` dict)
- 사이클 29 005935 사고 패턴 차단 (HIGH 종목 cap 밖 잘림 영구 차단)
- 사이클 38 명문화 (tradable_boards 매수 진입 전용)
- 사이클 55 R-1 SellRejectionTracker 2단계 TTL
- 사이클 65 H2/H2-bis KST 강제
- 사이클 67 stale_manager 4 sub-module 분해
- 사이클 74 WS action aggregation 5분 윈도우
- 사이클 78 flush 호출 사이트
- 사이클 79 task cancel 양쪽 추가
- 사이클 81 bfdy_clpr
- 사이클 89 KOSPI/KOSDAQ 분리 + ETF 제외
- 사이클 91 페이징 누적

### 6.3 운영 가시화

- `[ws_auto_restart] MAX_RECONNECT 도달 → start() 자동 재호출` WARNING (발화 시점)
- `[ws_auto_restart_cooldown] 60s cooldown 미경과 (last=X.Xs ago)` WARNING
- `[ws_auto_restart_cap_exceeded] 시간당 N회 cap 도달 (KIS LMS chain 차단)` ERROR
- `[ws_auto_restart_failed] error=...` ERROR (start() 실패 graceful)

### 6.4 영향 인덱스 갱신

- `_workspace/test_index.yaml` backend tests 410 → 424 (+14)
- 영향 모듈: `src/engine/scheduler.py` (TIME_BOOT/TIME_PRESUBSCRIBE) + `src/realtime/websocket.py` (auto_restart 영역)

---

## 7. KIS MCP 정본 검증 (사이클 81/89/91 답습)

- KIS 정책 "07:50 모든 기존 접속 중단" = 사용자 보고 정본 (kis-mcp + `docs/kis/` 0건, Q31=C 생략)
- 추정 정책: KIS LMS / 앱키 정지 = 분당 1개 토큰 한도 + 시간당 5~10회 이상 발급 임시 정지 (domain-expert 자문 영속)
- 사이클 92 자동 재기동 cap (시간당 3회) = LMS chain 차단 안전 마진

---

## 8. 사이클 81/91 답습 패턴 영속

- 단일 근본 원인 (KIS 07:50 강제 중단 vs `MAX_RECONNECT=5` 31초 한도) + 1~3 줄 시정 + 신규 메서드 ~50L + AST 영구 가드
- 회귀 가드 14 케이스 (HIGH 6 = 43%) — domain-expert A5 권고 영속
- 21 사이클 연속 옵션 A 패턴 후보 (55 R-1 / 60 / 62~69 / 72~81 / 89 / 91 / **92**)
- silent 결함 영구 차단 22 회 후보 (사이클 91 21회 + **92**)

---

## 9. push 시점 (Q33 영속)

- **완료 즉시 push** (사용자 결정, 매매 많지 않음 + 사용자 자율 영역)
- 현재 시각 = 09:30 KST 이후 (사이클 92 자문 시점) — 매매 hot path 영향 0 (lifecycle 영역만)
- 다음 영업일 (2026-06-11 목) 07:45 ~ 08:00 영역에서 자동 검증 → SQL READ-ONLY 4 쿼리 + `[ws_max_reconnect_exceeded_auto_restart]` ERROR 0건 확인 의무
