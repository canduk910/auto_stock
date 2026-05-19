# 사이클 13-H — `pool.start()` 보조 connect race 결함 명세

> PR #12 (사이클 13-G) 직후 발견된 라이브 결함. KST 2026-05-19 09:00~ KRX 메인 시간 실측.
> **자금 안전 영향: HIGH (보유 종목 외 23개 메인 stale → 매수 신호 누락 + 손절 평가 지연).**
> 본 사이클: `pool.start()` first-ready await + 운영 회복 보강. 13-E~13-G race 가드/시각 mock/매핑 동기 영역 무변경.

---

## §1 현상 — 운영 환경 실측 (2026-05-19)

### 1-1. `/api/realtime/subscriptions` 라이브 스냅샷

```
KST 09:15:42
{
  "total": 27, "acked": 27, "fresh_60s": 4, "stale_60s": 23, "limit": 82,
  "sessions": [
    {"label": "main",    "subscribed": 25, "acked": 25, "fresh": 2, "stale": 23, "limit": 41, "ws_connected": true},
    {"label": "quote-1", "subscribed": 2,  "acked": 2,  "fresh": 2, "stale": 0,  "limit": 41, "ws_connected": true}
  ]
}
```

- 메인: **25 구독 중 stale 23** (fresh 2 = 보유 1종목 017670 + 005930 H0UNMKO0 대표)
- 보조 quote-1: 2 구독 모두 fresh
- 전체 27 / 82 슬롯 (33% 사용) — 분산 여유 충분한데 메인 편중

### 1-2. 시간대별 로그 인용

```
07:50:12 [pool_start] 보조 세션 등록: label=quote-1
07:50:12 [pool_start] 완료: main=1 quotes=1 total_slots=82
07:50:14 사전 구독: 25종목 (돌파 + 스윙 + 보유)            ← ★ 메인 25 전부 부착
07:50:15 [scanner] 실시간 시세 구독 완료: total=27 (vb=12, ltv=8, swing=3, momentum=0, positions=1, dummy=2)
07:50:16 SUBSCRIBE SUCCESS main x25                          ← 메인 ACK 도달
07:50:31 [quote-1] connected (AES iv/key 수신)               ← ★ 보조 connect 완료 시각이 19초 늦음
09:14:02 [stale_watcher] stale=23/27 tickers=[...]
09:14:02 [pool_resend_subscribe] 23종목 재발송 (메인 그대로)
09:16:05 [stale_watcher] stale=23/27 (회복 0)
09:16:05 [stale_force_register] 강제 재등록: 23 (메인 → 메인)
09:18:08 [stale_watcher] stale=23/27 skip_count_exceeded     ← 11회 누적 → skip 전환
```

### 1-3. 자금 영향

- 보유 1종목 (017670 SK텔레콤) 만 메인 fresh — `bypass_limit=True` HIGH 분기로 메인 부착 정상
- 23 stale 종목 (VB+LTV+swing 돌파 유니버스) = **0.5초 단위 가격 추적 불가**
  - VB/LTV 돌파 매수 신호 (이전 틱 < target AND 현재 틱 ≥ target) → 실시간성 손상
  - donchian_swing 멀티데이 보유 시 `_swing_rest_poll_loop` 60s REST 폴링으로 보강은 되지만 매수 평가는 09:30~ pull 폴링 09:05~09:30 분리 — KRX 메인 시간대 매수 0건 위험
  - 트레일링 손절 (`atr_trail_mult`) 가격 갱신 stale → 손절 지연

---

## §2 근본 원인

### 2-1. fire-and-forget connect task race

`src/realtime/websocket_pool.py:138-143`:

```python
ws = KisWebSocket(token_manager=manager)
self._quotes.append(ws)                                     # ① 즉시 list 추가 (ACK 미수신)
if dispatch_message is not None:
    import asyncio as _asyncio
    task = _asyncio.create_task(ws.connect(dispatch_message))  # ② fire-and-forget
    self._quote_connect_tasks.append(task)
```

`pool.start()` 가 보조 connect 완료를 **await 하지 않고** return.

### 2-2. `_available_quotes()` 가드와 `_ticker_to_session` 고착

`src/realtime/websocket_pool.py:199-210`:

```python
def _available_quotes(self) -> list[KisWebSocket]:
    return [
        q for q in self._quotes
        if getattr(q, "_ws", None) is not None     # ← ★ 첫 연결 전 None
        and len(q._subscriptions) < MAX_SUBSCRIPTIONS
    ]
```

`scheduler._boot()` 의 `pool.start()` 직후 (07:50:12) ~ 보조 connect 완료 (07:50:31) 사이 ~19초 동안:
- `_available_quotes()` 가 `[]` 반환
- `_select_session(priority="LOW")` 가 메인 fallback (line 192 `return self._main`)
- `subscribe()` 가 `self._ticker_to_session[tr_key] = self._main` 고착

### 2-3. 사후 회복 부재

보조 connect 가 19초 후 완료되어도:
- 이미 메인에 부착된 25 종목은 `_ticker_to_session` 에 메인 고정
- K stale watcher (`pool.resend_subscribe_for_ticker`) 는 동일 세션 (메인) 으로 재전송 → 회복 0
- 강제 재등록 (`pool.unsubscribe_in_pool` + `pool.subscribe(priority='HIGH')`) 도 HIGH 분기로 메인 우선 → 분산 안 됨

### 2-4. KIS 메인 단일 채널 throttle

KIS WebSocket 은 세션당 41 구독 한도 — 메인에 25 부착은 한도 내. 그러나 KIS 측 송신 throttle 또는 우리 측 메시지 수신 손실로 stale 발생. **분배가 적정 동작이면 회피 가능한 범위.**

---

## §3 트레이딩 안전성 평가 — HIGH

### 3-1. 매수 신호 누락 (HIGH)

VB/LTV 돌파 매수는 **돌파 순간** (이전 < target AND 현재 ≥ target) 감지가 필수. 메인 stale = 0.5초 tick 누락 → 돌파 순간 놓침. KRX 메인 시간대 (09:00~15:20, 6시간 20분) 동안 누적 매수 기회 손실.

### 3-2. 손절 평가 지연 (HIGH)

VB/LTV 보유 시 stop_loss_main / stop_loss_pre_nxt 평가는 on_tick 갱신가에 의존. stale 종목 보유 발생 시 손절 지연 → 추가 손실 가능.

donchian_swing 은 `_swing_rest_poll_loop` 60s REST 폴링 보강이 있지만 VB/LTV 는 없음.

### 3-3. 보유 종목은 안전

보유 종목 (017670) 은 `priority='HIGH'` + `bypass_limit=True` 로 메인 부착 + fresh — 본 결함의 직접 피해 없음. 단, **추가 진입 (호가 변동 추적)** 시점에는 영향 가능.

### 3-4. 익일 청산 안전

`_pending_next_day_clear` 종목도 HIGH 메인 부착 → 본 결함 무관.

---

## §4 Fix 명세

### Patch 1 — `pool.start()` first-ready await (필수 적용)

`src/realtime/websocket_pool.py:96-154`.

**timeout 값 결정: 7초.**

근거:
- KIS WebSocket 핸드쉐이크 + AES key 수신 정상 소요 2~3s (실측 07:50:12 → 07:50:31 = 19s 는 동시 메인 연결 + token issue 경합 가능)
- 보수 마진 2x = ~5s, 그러나 토큰 발급 race 흡수 위해 7s. `pool.start()` 가 `_boot()` 전체 흐름 (07:50~07:55 5분) 안에서 충분히 흡수
- 단일 보조 무한 대기 차단 — timeout 시 WARNING + 그대로 return → 직후 subscribe 는 메인 fallback (기존 동작 보존)

**Before (line 135~149):**

```python
try:
    ws = KisWebSocket(token_manager=manager)
    self._quotes.append(ws)
    if dispatch_message is not None:
        import asyncio as _asyncio
        task = _asyncio.create_task(ws.connect(dispatch_message))
        self._quote_connect_tasks.append(task)
    logger.info("[pool_start] 보조 세션 등록: label=%s", label)
except Exception:
    logger.warning(
        "[pool_start] 보조 세션 생성 실패: label=%s — skip",
        label, exc_info=True,
    )

logger.info(
    "[pool_start] 완료: main=1 quotes=%d total_slots=%d",
    len(self._quotes), MAX_SUBSCRIPTIONS * (1 + len(self._quotes)),
)
```

**After (line 135~178, +29 lines):**

```python
try:
    ws = KisWebSocket(token_manager=manager)
    self._quotes.append(ws)
    if dispatch_message is not None:
        import asyncio as _asyncio
        task = _asyncio.create_task(ws.connect(dispatch_message))
        self._quote_connect_tasks.append(task)
    logger.info("[pool_start] 보조 세션 등록: label=%s", label)
except Exception:
    logger.warning(
        "[pool_start] 보조 세션 생성 실패: label=%s — skip",
        label, exc_info=True,
    )

# 사이클 13-H — 보조 connect first-ready await
# 적어도 1개 보조 세션이 _ws 준비될 때까지 timeout 까지 대기.
# 직후 subscribe 가 _available_quotes() 에 보조 후보 발견 → 보조 라운드로빈 분배.
# Timeout 초과 시 WARNING + 그대로 return — 직후 subscribe 는 메인 fallback (기존 동작 보존).
if self._quotes and dispatch_message is not None:
    import asyncio as _asyncio
    POOL_START_READY_TIMEOUT_SECS = 7.0
    POOL_START_READY_POLL_INTERVAL_SECS = 0.1
    start_t = _asyncio.get_event_loop().time()
    while _asyncio.get_event_loop().time() - start_t < POOL_START_READY_TIMEOUT_SECS:
        ready = sum(
            1 for q in self._quotes
            if getattr(q, "_ws", None) is not None
        )
        if ready >= 1:
            elapsed = _asyncio.get_event_loop().time() - start_t
            logger.info(
                "[pool_start_ready] 보조 first-ready: ready=%d/%d elapsed=%.2fs",
                ready, len(self._quotes), elapsed,
            )
            break
        await _asyncio.sleep(POOL_START_READY_POLL_INTERVAL_SECS)
    else:
        # while/else — break 없이 timeout
        logger.warning(
            "[pool_start_ready_timeout] 보조 세션 first-ready 미달성: "
            "timeout=%.1fs quotes=%d — 메인 fallback 동작 (직후 subscribe 가 메인 부착)",
            POOL_START_READY_TIMEOUT_SECS, len(self._quotes),
        )

logger.info(
    "[pool_start] 완료: main=1 quotes=%d total_slots=%d",
    len(self._quotes), MAX_SUBSCRIPTIONS * (1 + len(self._quotes)),
)
```

설계 메모:
- `asyncio.wait(connect_tasks, return_when=FIRST_COMPLETED)` 대신 **`_ws` 폴링** 채택 — KisWebSocket.connect() 가 무한 루프 (재연결 + heartbeat) 라 task 자체는 never-complete. `_ws` 속성 갱신 시점이 "ready" 의 정확한 시그널
- `asyncio.get_event_loop().time()` 사용 (monotonic) — 13-F freezegun mock 영향 없음
- 폴링 간격 100ms — 7s timeout 안에서 70회 평가 충분
- 메인 fallback 흐름 보존 — `_quotes` 가 0 이거나 timeout 시 그대로 return → `_available_quotes()` 가 빈 list → 메인 fallback

### Patch 2 — `_select_session` 보강: **미적용**

근거:
- Patch 1 만으로 race window 가 7s 이내로 좁아짐
- `_select_session` 에 보조 reconnect 대기 로직 추가 시 매 subscribe 호출마다 yield → 다른 race 발생 가능
- 메인 fallback 은 **안전망**으로 유지 — 보조 0개 또는 모두 disconnect 시 정상 동작 요구
- 7s timeout 초과 시점에도 보조 connect 가 진행 중이면 K stale watcher (120s) 가 사후 보강 — Patch 3 미적용 시 stale → 강제 재등록 사이클에서 자연 회복은 안 됨 (메인→메인 재부착이라 분산 0). 운영자 수동 풀 재시작 필요. **이 trade-off 는 수용** — 대부분 케이스는 7s 안에 connect 완료

### Patch 3 — 자동 rebalance 헬퍼: **미적용 (보수)**

근거 (자동 rebalance 의 race 위험):
- KIS WS unsubscribe → subscribe race: 메인에서 unsubscribe 직후 보조 subscribe 시점에 KIS 측 ACK 비대칭 발생 가능
- 이미 13-E~13-G 에서 `_subscriptions` 정합성 가드 / orphan ACK race 차단 / stale watcher 4중 안전망을 정교하게 구축 — 추가 rebalance 로직은 그 정교함을 깨트릴 위험
- HIGH 종목 (보유/익일청산) 은 메인 보존 의무 — rebalance 로직이 잘못 이전하면 자금 안전 직접 영향
- 자동 회복보다 **결함 발생률 자체를 낮추는 Patch 1** 이 우선
- 운영자 수동 회복 경로: `POST /api/realtime/resubscribe` (기존) — 운영 매뉴얼에 명시 권장

**향후 후속 사이클 검토 사항:**
- 메인 80% 초과 + 보조 30% 미만 5분 지속 시 운영자 알림 (Slack/SMS) 만 — 자동 이전 아님
- Patch 3 의 자동 rebalance 는 별도 사이클 13-I 에서 신중 검토 (회귀 테스트 분리 필요)

---

## §5 회귀 시나리오 (Q/R)

### Q-1 (Patch 1 정상 케이스)

`pool.start()` 호출 시 보조 connect 가 7s 내 완료 → 직후 subscribe 가 보조 라운드로빈 분배 (메인 1 + 보조 1, 25 종목 → 메인 13 / 보조 12 또는 라운드로빈 적정 분산).

**기대 시그널:**
- `[pool_start_ready] 보조 first-ready: ready=1/1 elapsed=2.34s` INFO 1행
- `[pool_start] 완료: main=1 quotes=1 total_slots=82` INFO 1행
- 직후 subscribe 25회 → 메인 / 보조 분산 (`get_session_status()` 에서 확인)

### Q-2 (Patch 1 timeout 케이스 — 보조 토큰 발급 지연)

보조 connect 가 7s 초과 → `pool.start()` 가 WARNING + return → 직후 subscribe 는 메인 fallback (기존 동작 보존, 회귀 0).

**기대 시그널:**
- `[pool_start_ready_timeout] 보조 세션 first-ready 미달성: timeout=7.0s quotes=1 — 메인 fallback 동작` WARNING 1행
- 직후 subscribe 25회 → 메인 부착 (기존 결함 재현이지만 결정적 동작)
- 보조 connect 가 그 후 완료되면 다음 `_scan_loop` 5분 주기에서 새 ticker 만 보조 분산 (기존 25 메인 부착은 그대로)

### Q-3 (보조 0개 — DB 미등록)

`kis_quote_accounts.list_accounts(active_only=True)` 가 빈 list → `pool.start()` 즉시 return (회귀 0, 사이클 7-B 기존 동작).

**기대 시그널:**
- `[pool_start] 보조 시세 계좌 0개 — 메인 only 동작` INFO 1행
- `pool_start_ready` 분기 진입 안 함 (`self._quotes` 가 빈 list)

### Q-4 (start() 멱등 — 두 번째 호출)

`_started=True` 가드로 즉시 return (13-G 기존 동작 보존).

### Q-5 (보조 N개 중 일부만 ready)

보조 3개 등록, 1개만 7s 내 ready, 나머지 2개 지연. **`ready >= 1` 조건 충족 → 즉시 break + INFO.**

남은 2개는 백그라운드 task 에서 connect 진행 → 다음 subscribe 에서 자연 추가 후보. 기존 `_available_quotes()` 동적 평가가 이를 보강.

---

## §6 안전 가드 (변경 금지)

- **체결통보 (H0STCNI0/H0STCNI9) 메인 강제 분기** — `subscribe()` line 246~249, `unsubscribe()` line 312~315, `_enforce_main_only_execution_notice` — 무변경
- **`_subscriptions` 직접 수정 금지** — 모든 변경은 `subscribe`/`unsubscribe` API 경유 (사이클 7-B / 13-E)
- **메인 fallback 자체** — timeout 후 또는 보조 0개 시 메인 fallback 는 안전망 유지
- **HIGH 우선순위 메인 보장** — `priority='HIGH'` + `bypass_limit=True` 메인 부착 분기 무변경
- **start/stop race 가드 (13-G)** — `_started` 멱등 + finally 7종 cancel + `stop()` 정리 — 무변경
- **시각 mock (13-F)** — `freezegun` 호환. `_asyncio.get_event_loop().time()` 은 monotonic 이라 mock 영향 없음 (필요 시 테스트에서 `time.monotonic` patch 분리)
- **task lifecycle (13-E)** — `_quote_connect_tasks` append + `stop()` cancel 패턴 무변경
- **KIS 메인 단일 채널 throttle 자체** — KIS 측 문제, 우리 코드로 우회 가능한 범위 (분배) 만 수정

---

## §7 영향 인덱스

### 수정 파일
- `src/realtime/websocket_pool.py` (Patch 1 — line 96~154 범위)

### 테스트 파일
- `tests/realtime/test_websocket_pool.py` — Q-1/Q-2/Q-3/Q-4/Q-5 테스트 추가 (Red)
- `tools/test_impact/index.json` — `src.realtime.websocket_pool` ↔ `tests/realtime/test_websocket_pool.py` 매핑 보강

### 비파괴 검증
- `tests/realtime/test_websocket.py` — KisWebSocket subscribe/unsubscribe 회귀
- `tests/engine/test_scheduler.py` — `_boot()` → `pool.start()` 호출 회귀 (13-E~13-G)
- `tests/realtime/test_websocket_pool_lifecycle.py` (13-E2/E3) — stop() 멱등 무변경 확인

### 문서
- `src/realtime/CLAUDE.md` — `start()` 동작에 first-ready await 추가 명시
- `docs/HARNESS_CHANGELOG.md` — 사이클 13-H 라인 추가

---

## §8 작업 분배

### 8-1. tdd-engineer (Red 작성)

분배 메시지 초안:

> **사이클 13-H Red 테스트 작성 의뢰 — `pool.start()` 보조 first-ready await**
>
> **목표:** Q-1/Q-2/Q-3/Q-4/Q-5 시나리오를 `tests/realtime/test_websocket_pool.py` 에 Red 로 추가. 현재 코드 (fire-and-forget) 에서는 Q-1/Q-5 fail, Q-2/Q-3/Q-4 pass.
>
> **테스트 설계:**
> 1. **Q-1 정상 first-ready**: `KisWebSocket` connect 가 `_ws` 를 즉시 (~50ms) 세팅하도록 mock. `pool.start(dispatch_message=mock)` 호출 후 `await pool.start()` 종료 시점에 `pool._quotes[0]._ws is not None` 검증 + `[pool_start_ready]` log capture 1회.
> 2. **Q-2 timeout**: KisWebSocket connect 가 8초 이상 sleep 하도록 mock (또는 `asyncio.Event` 미발화). `monotonic` patch 로 가속 가능. `pool.start()` 종료 시점에 `[pool_start_ready_timeout]` WARNING capture + `pool._quotes[0]._ws is None` 검증.
> 3. **Q-3 보조 0개**: `kqa.list_accounts` mock → `[]`. `pool.start()` 즉시 return + `[pool_start] 보조 시세 계좌 0개` INFO. `pool_start_ready` 분기 진입 안 함 (no `pool_start_ready*` log).
> 4. **Q-4 멱등**: `pool._started = True` 사전 세팅 → `pool.start()` 호출 → 즉시 return + `[pool_start] already started — noop` DEBUG.
> 5. **Q-5 N개 중 일부 ready**: 보조 3개 등록. 1개만 즉시 ready, 나머지 2개는 `asyncio.Event` 미발화. `pool.start()` 종료 시점 `ready=1/3` INFO + 전체 timeout 안 도달.
>
> **mock 전략:**
> - `kis_quote_accounts.list_accounts` patch — Q-1/Q-2/Q-3/Q-5 별로 list 길이 조정
> - `get_token_manager` patch — AsyncMock
> - `KisWebSocket.connect` patch — `async def` 가 `self._ws = MagicMock()` 직후 무한 sleep (실제 코드 흐름 시뮬)
> - `asyncio.get_event_loop().time()` 또는 `time.monotonic` patch — Q-2 timeout 가속 (7s → ~0.01s 시뮬)
>
> **기대 결과:** 현재 코드 기준 Q-1/Q-5 fail (first-ready await 부재), Q-2/Q-3/Q-4 pass. Patch 1 적용 후 5건 모두 pass.
>
> **금지:**
> - 실제 KIS WebSocket 연결 시도 금지 (전부 mock)
> - `_subscriptions` 직접 manipulate 금지
> - 체결통보 분기 테스트는 본 사이클 범위 밖

### 8-2. backend-dev (Green 구현)

분배 메시지 초안:

> **사이클 13-H Green 구현 의뢰 — Patch 1 적용**
>
> **선행:** tdd-engineer Red 테스트 (Q-1/Q-5 fail) 확인 후 진입.
>
> **변경 1건만:** `src/realtime/websocket_pool.py:135~154` — §4 Patch 1 스니펫 적용. for-accounts 루프 *후*, `[pool_start] 완료` log *전* 에 first-ready await 블록 삽입.
>
> **상수 선언 위치:** `POOL_START_READY_TIMEOUT_SECS=7.0` / `POOL_START_READY_POLL_INTERVAL_SECS=0.1` — 모듈 상단 import 영역 *아래* `MAX_SUBSCRIPTIONS` 인근에 module-level 상수로 선언 권장 (테스트에서 patch 가능).
>
> **금지:**
> - `_available_quotes()` 시그니처 변경
> - `_select_session` 분기 추가 (Patch 2 미적용)
> - 자동 rebalance 로직 추가 (Patch 3 미적용)
> - 체결통보 분기 / `_subscriptions` 직접 수정
> - `stop()` / `disable_quote_session` / `subscribe` / `unsubscribe` 무변경
>
> **검증:**
> 1. `python -m pytest tests/realtime/test_websocket_pool.py -v` → 5건 pass
> 2. 회귀: `python -m pytest tests/realtime/ tests/engine/test_scheduler.py -q`
> 3. `src/realtime/CLAUDE.md` 의 `start()` 동작 설명에 first-ready await 1줄 추가

### 8-3. tester (검수)

분배 메시지 초안:

> **사이클 13-H 검수 의뢰**
>
> **현업 검수 포인트:**
> 1. **timeout 7s 적정성** — KIS WebSocket 핸드쉐이크 실측 통계가 있다면 95% percentile < 5s 인지. 운영 로그 grep: `[quote-N] connected` 시각과 `[pool_start]` 시각 차이 평균/95p 산출
> 2. **메인 fallback 흐름 보존** — Q-2 timeout 케이스에서 매수/매도 흐름 정상 동작 (메인 25 부착 + KIS throttle 영향은 운영 회복 매뉴얼 가이드)
> 3. **HIGH 우선순위 영향 0건** — 보유/익일청산 종목 메인 부착 분기 회귀 없음
> 4. **시각 mock 호환** — 13-F freezegun 흐름과 `asyncio.get_event_loop().time()` 분리 동작 확인
> 5. **운영 회복 매뉴얼 보강** — `POST /api/realtime/resubscribe` 수동 호출 시 정상 분배 회복 시나리오 검증 (별도 운영 가이드 PR 권장)

---

## §9 검수 체크리스트 (핵심 5개)

1. **Patch 1 first-ready await** — `[pool_start_ready]` INFO 1행 또는 `[pool_start_ready_timeout]` WARNING 1행이 `[pool_start] 완료` 직전에 정확히 1회 출력
2. **Q-1 정상 분배** — `pool.start()` 종료 후 25 ticker subscribe 시 메인:보조 분산 비율 12:13 (또는 13:12) — `get_session_status()` 응답으로 확인
3. **Q-2 timeout fallback** — 7s 초과 시 WARNING + 메인 fallback. 회귀 0 (기존 결함 재현이지만 결정적). 운영자 알림 가능 형태
4. **체결통보 메인 강제 무변경** — `tests/realtime/test_websocket_pool.py::test_execution_notice_main_only` 회귀 pass
5. **stop/finally 7종 cancel 무변경** — 13-E~13-G race 가드 회귀 pass (`_quote_connect_tasks` cancel 동작 확인)

---

## §10 운영 회복 가이드 (참고 — 별도 docs PR 권장)

본 사이클로 결함 발생률은 낮아지지만 timeout 케이스 (Q-2) 에서는 여전히 메인 편중 가능. 운영자 회복 경로:

1. `/api/realtime/subscriptions` 모니터링 — 메인 stale 비율 80% 초과 + 보조 사용률 30% 미만 5분 지속 시 알림
2. `POST /api/realtime/resubscribe` 호출 — F1 자동 로직 동일 규약. 단, 메인 → 메인 재부착이라 본 결함 케이스에는 분산 효과 없음 → 이 경우 풀 재시작 권장
3. 풀 재시작: `POST /api/trading/stop` → `POST /api/trading/start` — `_boot()` 재진입 시 Patch 1 first-ready await 가 적용된 새 분배 라운드

---

## 부록 — Patch 2/3 미적용 trade-off 명세

| Patch | 적용 | 근거 | 미적용 시 위험 |
|-------|------|------|----------------|
| 1 | **YES** | first-ready await 로 race window 7s → 결함 발생률 직접 차단 | (적용함) |
| 2 | NO | `_select_session` 보강이 매 subscribe yield → 다른 race 위험. Patch 1 만으로 정상 케이스 회복 충분 | timeout 후 보조 connect 완료 시 신규 ticker 만 분산 (기존 메인 부착은 그대로) |
| 3 | NO | 자동 rebalance 가 unsubscribe→subscribe race + HIGH 종목 잘못 이전 위험 | timeout 케이스에서 자동 회복 안 됨 → 운영자 수동 풀 재시작 필요 |

후속 사이클 13-I 검토 사항:
- Patch 3 자동 rebalance 의 회귀 테스트 설계 + 안전 가드 (HIGH 보존 / 일괄 이전 금지 / batched unsubscribe-subscribe sequence)
- 운영자 알림 (Slack/SMS) 통합 — 메인 80% 초과 + 5분 지속 트리거
