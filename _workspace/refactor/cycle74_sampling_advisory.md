# 사이클 74 — WebSocket 로그 sampling/aggregation/rate cap 자문 (refactor-expert)

- 일자: 2026-06-08
- 의제: 옵션 E (tr_id별 aggregation + ERROR individual 보존) 구조 설계 + ERROR 보존 정의 + collector 헬퍼 재사용 평가 + AST 영구 가드 + 사이클 75+ 인계
- 사용자 결정 채택 컨텍스트: R3 / 2-A=C / 2-B=C 조건부 / **2-C=E** / X (5분 heartbeat 보존)
- 자문 위치: team-leader Phase 1 분석 후, tdd-engineer Red 발주 *전*
- 자문 기반 안전 규칙: CLAUDE.md "절대 깨지 말 것" 전부 (체결통보 / uvicorn 단일 / 매핑 / 익일청산 / NXT 좀비 / WebSocket 4중 안전망 / KIS LMS chain 차단 / 사이클 38/55 R-1/66/67/68/72/73) **불변 유지**

## 검토 범위

- 사이클 73 시정 후 잔존 INFO emit 사이트 (`src/realtime/websocket.py` + `src/realtime/websocket_pool.py`)
- 사이클 29 005935 사고 chain 진단 의무 영역 (`[ws_subscribe_reject]` / `[silent_inactive_force_reconnect]` / `[stale_force_retry_cap]` / `[stale_priority_resubscribe_cap_exceeded]`)
- 옵션 C 후보 재사용 영역 (`[swing_rest_poll]` / `[stale_watcher]`)
- 변경 대상 코드 0 — 권고만 (Red 발주는 tdd-engineer)

## 코드 사실 (현 상태)

### `src/realtime/websocket.py` 의 logger 사이트 (사이클 73 시정 후)

| 라인 | 사이트 | 레벨 | 메시지 prefix | 빈도 추정 (41 종목 × N) |
|------|--------|------|--------------|----------------------|
| L284 | `subscribe` 한도 초과 | warning | `최대 구독 수(...) 도달` | 결함 시만 (정상 0) |
| L373-376 | `_verify_subscriptions_after_reconnect` 미수신 0 | info | `[ws_reverify] 재연결 후 ...초 — 미수신 종목 없음` | 재연결 후 1회/사이클 |
| L380-384 | `_verify_subscriptions_after_reconnect` 미수신 N | warning | `[ws_reverify] 재연결 후 ...초 — 미수신 N종목 자동 재구독` | 결함 시만 |
| L417 | `_send_subscribe` 발사 (구독/해제) | **info** | `WebSocket {구독|해제}: {tr_id} / {tr_key}` | **종목별 1회 × 41 × N — 가장 큰 dup 원천** |
| L429-432 | `_receive_loop` heartbeat timeout | warning | `Heartbeat 타임아웃 (...초), 재연결 시도` | 결함 시만 |
| L435 | `_receive_loop` ConnectionClosed | warning | `WebSocket 연결 닫힘` | 결함 시만 |
| L490-493 | `_handle_raw` OPSP0002 ALREADY | info | `WebSocket 구독 이미 활성(KIS 측): ... [ws_opsp_backoff until=+300s]` | 사이클 17 OPSP0002 영역 — 결함 회피 가시화 영구 |
| L502-505 | `_handle_raw` 거절 | **error** | `[ws_subscribe_reject] tr_id=... rt_cd=... msg_cd=... msg=...` | **사이클 73 R-2 시정 영속 — LMS chain 진단 영역** |
| L524-526 | `_handle_raw` SUBSCRIBE SUCCESS | **info** | `WebSocket 구독 ACK: tr_id=... tr_key=...` | **종목별 1회 × 41 × N — 두 번째 dup 원천** |
| L528-531 | `_handle_raw` orphan ACK | debug | `[ws_ack_orphan] ...` | 운영 미노출 (DEBUG) |
| L544 | `_handle_raw` AES 키 수신 | info | `AES 키 수신: tr_id=...` | 메인 1~2회/세션 |
| L546-549 | `_handle_raw` AES 키 skip | debug | `[aes_key_skip] ...` | 운영 미노출 |

### `src/realtime/websocket_pool.py` 의 logger 사이트

| 라인 | 사이트 | 레벨 | 메시지 prefix | 빈도 |
|------|--------|------|--------------|------|
| L114 | `start` already started | debug | `[pool_start] already started` | noop |
| L122 | `start` 보조 조회 실패 | warning | `[pool_start] kis_quote_accounts 조회 실패` | 결함 시만 |
| L126 | `start` 보조 0개 | info | `[pool_start] 보조 시세 계좌 0개` | 1회/start |
| L138-141 | `start` 보조 매니저 실패 | warning | 결함 시만 |
| L155 | `start` 보조 등록 성공 | info | `[pool_start] 보조 세션 등록: label=...` | 1회/보조 |
| L183-186 | `start` ready timeout | warning | `[pool_start_ready_timeout] ...` | 결함 시만 |
| L193-195 | `start` ready 완료 | info | `[pool_start_ready] ...` | 1회/start |
| L200-202 | `start` 완료 | info | `[pool_start] 완료: main=1 quotes=...` | 1회/start |
| L316-319 | `subscribe` promote | **info** | `[pool_promote] ticker=... old=... new=main` | **HIGH 승격 사이트 — LMS chain 진단 영역** |
| L341-345 | `subscribe` drop all_sessions_full | **info** | `[priority_drop_pool] tr_key=... reason=all_sessions_full main=N/41 quotes=M` | **drop 가시화 — 사이클 73 시정 영역** |
| L354-357 | `subscribe` drop secondary | **info** | `[priority_drop_pool] tr_key=... reason=all_sessions_full` | 동상 |
| L380, L396, L409, L425, L462, L475 | 각종 unsubscribe/disable 실패 | debug | 운영 미노출 |
| L447, L482 | disable 메인 noop / 완료 | debug/info | 1회/disable |

### 사이클 73 시정 후 잔존 dup 핵심 4건 (운영 실증)

`src.realtime.websocket` 영역 dup 6.68x 의 root cause = L417 `_send_subscribe` + L524 `SUBSCRIBE SUCCESS` 두 사이트가 41 종목 × `_scan_loop` 5분 주기 × 1일 (KRX 09:30~15:20 = 5.83h / 5min ≈ 70 사이클) × 메인+보조 = ~4,000 INSERT/day. 정상 흐름 INFO 가 system_logs 폭주.

## 보고

### 1. 옵션 E-1/E-2/E-3 평가 매트릭스 + 권고

| 평가 축 | E-1 (단순 aggregation collector, 5분 윈도우) | E-2 (호출자 batch) | E-3 (per-loop aggregation) |
|---------|--------------------------------------------|----------------|----------------------------|
| **행위 보존** | 100% — KIS 측 메시지 송수신 0 변경, 단지 system_logs INSERT 시점만 지연. WebSocket 4중 안전망 (F1/scan_loop/K stale watcher/resubscribe_stale_priority) 호출 사이트 무영향 | 80% — `subscribe_filtered_stocks` 의 41 종목 일괄 호출이 *await chain* 변경 시 race 가능 (K stale watcher `pool.subscribe` 단발 호출과 분기 다름) | 70% — `_scan_loop` (5분 주기) 와 K stale watcher (120s 주기) 와 F1 (재연결 시) 의 호출 사이클이 *제각각* → 어디서 flush 할지 결정 어려움 |
| **사이클 29 사고 chain 진단** | ✅ ERROR/거절/promote/drop 은 individual 보존 (의제 2 매트릭스) — aggregation 은 정상 흐름만 흡수 | ⚠️ 호출자가 batch 단위로 emit → 호출자 사이트별로 동일 규약 강제 어려움 → 진단 누락 위험 | ⚠️ K stale watcher 강제 재등록 사이클 (120s) 과 `_scan_loop` (5분) 사이에 5분 lag → 사고 발생 시 5분 후에야 가시화 |
| **구조 개선 가치** | ★★★ — `[ws_heartbeat]` (사이클 42) 패턴 100% 답습 + 향후 `[swing_rest_poll]` / `[stale_watcher]` 재사용 헬퍼 추출 가능 | ★ — 호출자별 분기 → 표준화 불가 | ★★ — `_scan_loop` 사이클 정합성은 좋으나 다른 호출자 누락 시 silent 결함 |
| **테스트 가능성** | ★★★ — `freezegun` + `_ws_log_collector.flush()` 명시 trigger + collector 인스턴스 변수 → 단위 테스트 단순 | ★ — 호출자별 batch 시점이 다 다름 → 테스트 분산 + flakiness 위험 | ★★ — `_scan_loop` mock 필요, scheduler 의존 |
| **위험 등급** | **HIGH** (호출 사이트 변경 + collector 인스턴스 변수 추가) — 단 위험은 *명확하고 좁음* (collector 1 곳) | **HIGH** (광범위) | **HIGH** (multi-loop 분기) |
| **운영 가시화 (5분 lag)** | acceptable — `[ws_heartbeat]` 5분 패턴 사용자 수용 영속 | depend on batch 시점 | 5min ~ 120s lag 변동 → 분석 어려움 |
| **추상화 규칙 (3회 반복)** | ✅ `[ws_heartbeat]` + 옵션 C `[swing_rest_poll]` + 옵션 C 조건부 `[stale_watcher]` = **3 영역 적용 가능** → 헬퍼 추출 정당화 | N/A | N/A |

#### 권고: **옵션 E-1 (단순 aggregation collector, 5분 윈도우)** 채택

근거:
1. **행위 보존 100%** — KIS 송수신/구독 사이트 0 변경. WebSocket 4중 안전망 호출 시점/순서 보존.
2. **사이클 42 `[ws_heartbeat]` 패턴 답습** — 8 사이클 운영 검증 (5/22 ~ 6/8) + 사용자 수용 영속 + L2 INFO 5분 통계 정착.
3. **테스트 가능성** — `freezegun` + collector instance 변수 → flush trigger 명시 가능 + 사이클 60/64/65 패턴 답습.
4. **3회 반복 추상화 규칙** — `[ws_heartbeat]` + `[swing_rest_poll]` + (조건부) `[stale_watcher]` = 3 영역 적용 가능 → 의제 3 헬퍼 추출 정당화.

E-2 비채택 사유: 호출자별 분기 강제 어려움 + race 위험 (K stale watcher 단발 호출과 `subscribe_filtered_stocks` batch 호출 분기 다름).
E-3 비채택 사유: 5분 ~ 120s lag 변동 → 사고 진단 어려움 + `_scan_loop` 의존 silent 결함 위험.

#### 옵션 E-1 설계 권고 (의사 코드)

위치: `src/realtime/websocket.py::KisWebSocket` 인스턴스 변수 + `_send_subscribe` / `_handle_raw` SUBSCRIBE SUCCESS 사이트 흡수.

```python
# 인스턴스 변수 (사이클 42 _pingpong_recv_count 패턴 답습)
self._ws_action_collector: dict[str, dict[str, list[str]]] = {}
# 구조: tr_id → {"SUBSCRIBE": [tickers], "UNSUBSCRIBE": [tickers], "ACK": [tickers]}
self._ws_action_window_start_at: datetime = datetime.now(_KST_TZ)
WS_ACTION_FLUSH_INTERVAL_SECS = 300  # 5분 (사이클 42 HEARTBEAT_METRICS_INTERVAL_SECS 답습)

# 흡수 사이트 1: _send_subscribe (L417)
def _record_action(self, tr_id: str, tr_key: str, action: str) -> None:
    """action: SUBSCRIBE / UNSUBSCRIBE / ACK / OPSP_ALREADY"""
    bucket = self._ws_action_collector.setdefault(tr_id, {})
    bucket.setdefault(action, []).append(tr_key)

async def _send_subscribe(self, tr_id, tr_key, *, subscribe):
    ...
    await self._ws.send(json.dumps(msg))
    action = "SUBSCRIBE" if subscribe else "UNSUBSCRIBE"
    self._record_action(tr_id, tr_key, action)
    # logger.info("WebSocket %s: %s / %s", ...) 제거

# 흡수 사이트 2: _handle_raw SUBSCRIBE SUCCESS (L524)
self._record_action(tr_id, tr_key, "ACK")
# logger.info("WebSocket 구독 ACK: ...") 제거

# 흡수 사이트 3: _handle_raw OPSP0002 (L490)
self._record_action(tr_id, tr_key, "OPSP_ALREADY")
# logger.info("WebSocket 구독 이미 활성...") 제거 — backoff 정보는 별도 별개 ERROR 보존 (의제 2 참조)
# 단, [ws_opsp_backoff until=+300s] 정보는 별개 결정 영역 — 권고: aggregation 흡수 (운영 가시화 5분 lag 수용)

# Flush task (사이클 42 _heartbeat_metrics_loop 패턴 답습)
async def _ws_action_flush_loop(self) -> None:
    while self._running:
        await asyncio.sleep(WS_ACTION_FLUSH_INTERVAL_SECS)
        self._flush_ws_action_collector()

def _flush_ws_action_collector(self) -> None:
    if not self._ws_action_collector:
        return
    now = datetime.now(_KST_TZ)
    window_secs = (now - self._ws_action_window_start_at).total_seconds()
    for tr_id, actions in self._ws_action_collector.items():
        parts = []
        for action_name in ("SUBSCRIBE", "UNSUBSCRIBE", "ACK", "OPSP_ALREADY"):
            tickers = actions.get(action_name, [])
            if not tickers:
                continue
            # 종목 cap 20 (사이클 28 [stale_watcher_detail] 패턴 답습 — overflow ...+N)
            preview = sorted(tickers)[:20]
            overflow = max(0, len(tickers) - 20)
            tail = f"...+{overflow}" if overflow > 0 else ""
            parts.append(f"{action_name}={len(tickers)} {preview}{tail}")
        logger.info(
            "[ws_action_summary] label=%s tr_id=%s window=%.0fs %s",
            self._label, tr_id, window_secs, " ".join(parts),
        )
    self._ws_action_collector.clear()
    self._ws_action_window_start_at = now
```

연관 lifecycle:
- `connect()` 진입 직후 `_ws_action_flush_task = asyncio.create_task(self._ws_action_flush_loop())` (사이클 42 `_heartbeat_metrics_loop` task 패턴 답습)
- `disconnect()` 에서 cancel + await 정리 (좀비 task 방지) + 마지막 flush 1회 (잔여 카운터 손실 방지)

#### Q1 위험 사항 (HIGH 등급)

1. **OPSP0002 aggregation 흡수 시 backoff 추적 어려움** — `_opsp_backoff_until` dict 는 보존되지만 운영자가 "어느 종목이 언제 backoff 등록됐는지" 추적 어려움. → **권고**: `_opsp_backoff_until` dict 의 길이만 별도 1행 emit (`[ws_opsp_backoff_state] active=N peek=[ticker(remain_secs)]`) 5분 주기. 또는 의제 2 ERROR 보존 매트릭스에 등록.
2. **flush task lifecycle race** — `connect()` 재연결 시 기존 collector 잔여 카운터 flush 의무. → **권고**: `connect()` 재진입 시 `_flush_ws_action_collector()` 1회 명시 호출 (재연결 사이클 분리 가시화).
3. **`_record_action` 호출 누락 silent 결함** — 미래 신규 사이트 추가 시 호출 누락 가능. → 의제 4 AST 가드 (G-A) 영구 차단.

### 2. ERROR 보존 정의 매트릭스 (사이클 29 005935 LMS chain 진단)

| 사이트 | 파일:라인 | 레벨 | aggregation 흡수 | individual 보존 의무 | 사유 |
|--------|-----------|------|----------------|------------------|------|
| `_send_subscribe` SUBSCRIBE | websocket.py:L417 | INFO | ✅ 흡수 | — | 정상 흐름 emit (~2,000/day dup 핵심 원천) |
| `_send_subscribe` UNSUBSCRIBE | websocket.py:L417 | INFO | ✅ 흡수 | — | 동상 |
| `_handle_raw` SUBSCRIBE SUCCESS | websocket.py:L524 | INFO | ✅ 흡수 | — | 정상 흐름 emit (~2,000/day dup 두 번째 원천) |
| `_handle_raw` OPSP0002 ALREADY | websocket.py:L490 | INFO | ✅ 흡수 + 별도 `[ws_opsp_backoff_state]` 1행 | 결함 시만 (`_opsp_backoff_until` 폭주 감지 시) | 사이클 17 보강 영속 — 운영 가시화 5분 lag 수용 |
| `_handle_raw` 거절 (사이클 73 R-2) | websocket.py:L502 | **ERROR** | ❌ **반드시 individual** | ✅ **사이클 29 005935 LMS chain 진단 핵심** | 거절 = KIS 측 비정상 — `_DbLogHandler` 위임 단일 INSERT 영속 + dedupe 500ms 캐시 (사이클 72) 안전망 |
| `subscribe` 한도 초과 | websocket.py:L284 | WARNING | ❌ individual | ✅ 결함 시만 발생, 진단 의무 | HIGH 단독 41 초과 ERROR 가시화 영속 |
| `_verify_subscriptions_after_reconnect` 미수신 N | websocket.py:L380 | WARNING | ❌ individual | ✅ F1 재연결 후 silent inactive 진단 | preview cap 10 영속 (사이클 73 R-2 영속) |
| `_verify_subscriptions_after_reconnect` 예외 | websocket.py:L392 | EXCEPTION | ❌ individual | ✅ 진단 의무 | 사이클 73 영속 |
| `_receive_loop` heartbeat timeout | websocket.py:L429 | WARNING | ❌ individual | ✅ 재연결 chain 진단 | 사이클 42 영속 |
| `_receive_loop` ConnectionClosed | websocket.py:L435 | WARNING | ❌ individual | ✅ 재연결 chain 진단 | 영속 |
| `pool.subscribe` promote | websocket_pool.py:L316 | INFO | ❌ **반드시 individual** | ✅ HIGH 승격 = LMS chain 진단 영역 | 사이클 7-C 풀 영역 — 보조→메인 승격은 운영 영향 큼, aggregation 부적합 |
| `pool.subscribe` drop all_sessions_full | websocket_pool.py:L341 | INFO | ❌ **반드시 individual** | ✅ 사이클 73 영역 + drop 가시화 의무 | drop = 매매 영향 — aggregation 흡수 시 진단 어려움 |
| `pool.subscribe` drop secondary | websocket_pool.py:L354 | INFO | ❌ **반드시 individual** | ✅ 동상 | 동상 |
| `pool.start` 보조 등록 성공 | websocket_pool.py:L155 | INFO | ❌ individual | ✅ start lifecycle 진단 | 1회/보조 — aggregation 불필요 |
| `pool.start` 완료 | websocket_pool.py:L200 | INFO | ❌ individual | ✅ start lifecycle | 1회/start |
| `pool.start_ready_timeout` | websocket_pool.py:L183 | WARNING | ❌ individual | ✅ ready chain 진단 | 결함 시만 |
| `_handle_raw` AES 키 수신 | websocket.py:L544 | INFO | ❌ individual | ✅ 체결통보 chain 진단 | 메인 1~2회/세션 — aggregation 불필요 (절대 안전 규칙) |

#### Q2 매트릭스 보완 권고 (의제 발의)

1. **OPSP0002 결정 영역**: aggregation 흡수가 옳은지 사용자 결정 의뢰 의무. 사이클 17 보강 영역 — KIS LMS 위험 직접 영향. **권고**: aggregation 흡수 + `_opsp_backoff_until` dict 길이 별도 5분 주기 emit (`[ws_opsp_backoff_state] active=N peek=...`). 사용자 결정 의뢰.
2. **`[ws_ack_orphan]` 결정 영역**: 현재 DEBUG 레벨 — 운영 미노출. 사이클 14-C 보강 영역 — `_scan_loop` race 진단. **권고**: 현행 유지 (DEBUG = 운영 미노출 영속, 결함 발생 시 LOG_LEVEL=DEBUG 일시 활성 패턴).
3. **추가 식별 사이트 (자문 의무 수행)**:
   - `_restore_subscriptions_after_reconnect` (websocket.py:L320-328) — 재연결 직후 모든 구독 재SEND. **`_send_subscribe` 내부 호출 → 자동 aggregation 흡수** (별도 처리 불필요). 단 재연결 횟수가 폭주 시 (`_reconnect_count > 5`) aggregation 으로 흡수되면 cumulative SEND 카운트 가시화 어려움 → **권고**: `connect()` 재연결 분기에 `[ws_restore_after_reconnect] reconnect_count=N restored=K` 1행 emit (재연결 1회 1행 — 빈도 적음, aggregation 불필요).
   - `_send_subscribe` `_ws is None` 분기 (websocket.py:L399-400) — 현재 silent return. **권고**: 현행 유지 (정상 lifecycle disconnect 상태).
   - `pool.subscribe` 체결통보 메인 강제 분기 (websocket_pool.py:L303-306) — 로그 0. **권고**: 현행 유지 (1회/세션 lifecycle, 노출 가치 낮음).

### 3. collector 헬퍼 재사용 가치 평가

#### 옵션 비교

| 평가 축 | 옵션 C-shared (`src/db/_log_aggregator.py` 신규 모듈) | 옵션 C-individual (각 영역 별도 collector) |
|---------|------------------------------------------------|---------------------------------------|
| **DRY 가치** | ★★★ — `[ws_heartbeat]` (사이클 42) + `[ws_action_summary]` (사이클 74 신규) + `[swing_rest_poll]` (옵션 C) + `[stale_watcher]` (옵션 C 조건부) = 4 영역 공통 패턴 흡수 가능 | ★ — 영역별 중복 코드 |
| **영역별 격리 가치** | ★ — 신규 모듈 = 새 의존 추가 (engine → realtime → db 의존 그래프 갱신) | ★★★ — 영역별 독립 변경 가능 |
| **테스트 가능성** | ★★★ — 단위 모듈 단독 테스트 가능 + freezegun 패턴 표준화 | ★★ — 영역별 분산 테스트 |
| **추상화 시점 (3회 반복 규칙)** | ✅ 4 영역 적용 가능 → 추상화 정당화 | — |
| **위험 등급** | **MEDIUM** (신규 모듈 + 의존 그래프 갱신) | **LOW** (영역별 독립) |
| **사이클 67 답습** | ✅ `stale_manager.py` facade 패턴 (사이클 67) 답습 — 단일 진입점 + sub-module 분해 | — |

#### 권고: **사이클 74 시점 = 옵션 C-individual 채택, 사이클 76+ 시점 = 옵션 C-shared 후속 카드**

근거:
1. **사이클 74 = WebSocket 영역 first introduction** — 헬퍼 추출 *전* `[ws_action_summary]` 실증 운영 1주 의무 (사이클 60/61/67 패턴 답습 — 분해 *전* 운영 검증).
2. **3회 반복 규칙 엄격 준수** — 현재 `[ws_heartbeat]` (사이클 42 영속) + `[ws_action_summary]` (사이클 74 신규) = 2 영역 (3회 미만). 옵션 C (`[swing_rest_poll]`) 채택은 별개 사이클 결정 — 사이클 74 동시 도입 시 *섣부른 추상화*.
3. **위험 등급 MEDIUM 회피** — 사이클 74 단일 사이클 = 옵션 E 도입 (HIGH) + AST 가드 추가 만으로도 충분히 큰 변경. 신규 모듈 (`src/db/_log_aggregator.py`) 동시 도입 시 회귀 가드 폭주 + 사고 발생 시 root cause 분리 어려움.
4. **사이클 67 답습** — refactor #2 stale_manager 분해도 사이클 60/61/63 3 사이클에 걸쳐 단계적 진행. 사이클 74 도 단계적 권고.

#### 사이클 76+ 헬퍼 추출 청사진 (참고)

```python
# src/realtime/_log_aggregator.py (사이클 76+ 카드)
class TrIdLogAggregator:
    """tr_id 별 action collector + flush — [ws_action_summary] / [ws_heartbeat] 공통 패턴 추출."""
    def __init__(self, *, label: str, prefix: str, flush_interval_secs: float, ticker_cap: int = 20):
        ...
    def record(self, tr_id: str, action: str, ticker: str) -> None: ...
    def flush(self, logger: Logger) -> None: ...  # tr_id 별 1행 emit + cap overflow ...+N
```

`src/db/` 위치 비채택 사유: `db/` 는 Supabase CRUD 전용 (사이클 67 디렉토리 책임 영속) — log aggregator 는 realtime / engine 영역. `realtime/` 위치 채택 (메인 사용자).

### 4. AST 영구 가드 위치 + 정밀 검출 패턴

옵션 G-7 (aggregator helper 의무 사용) + G-8 (tr_id별 직접 logger.info 호출 시 grep 가드).

#### G-A (HIGH) `_send_subscribe` 의 logger.info 잔존 0건

**패턴** (사이클 67 G-16 / 사이클 73 G-6.R AST 답습):

```python
# tests/unit/ast/test_cycle74_no_logger_info_in_send_subscribe.py
import ast
import pathlib

def test_send_subscribe_no_direct_logger_info():
    """사이클 74 G-A — _send_subscribe 본문에 logger.info(...) 직접 호출 0건.

    aggregation 흡수 (_record_action) 만 호출. dup 6.68x → ≤2.0x 영속.
    """
    src = pathlib.Path("src/realtime/websocket.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_send_subscribe":
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "info"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "logger"
                ):
                    raise AssertionError(
                        f"_send_subscribe L{sub.lineno}: logger.info(...) 직접 호출 발견. "
                        f"_record_action 만 호출 의무 (사이클 74 옵션 E-1)."
                    )
```

#### G-B (HIGH) `_handle_raw` SUBSCRIBE SUCCESS 분기의 logger.info 잔존 0건

**패턴**: AST 로 SUBSCRIBE SUCCESS 분기를 식별하기 어려움 → grep 기반 대안.

```python
def test_subscribe_success_no_direct_logger_info():
    """사이클 74 G-B — SUBSCRIBE SUCCESS 분기에 logger.info(...) 0건.

    `WebSocket 구독 ACK:` 문자열 grep — 잔존 시 FAIL.
    """
    src = pathlib.Path("src/realtime/websocket.py").read_text()
    assert "WebSocket 구독 ACK:" not in src, (
        "SUBSCRIBE SUCCESS 분기 logger.info 잔존 — _record_action 흡수 의무 (사이클 74)"
    )
```

#### G-C (HIGH) `_handle_raw` 거절 분기의 logger.error individual 보존 영속

**패턴** (사이클 73 R-2 영속 보강):

```python
def test_subscribe_reject_logger_error_preserved():
    """사이클 74 G-C — _handle_raw 거절 분기에 logger.error("[ws_subscribe_reject] ...") 영속.

    사이클 73 R-2 시정 영속 + 사이클 29 005935 LMS chain 진단 의무.
    aggregation 흡수 금지 — individual 보존 필수.
    """
    src = pathlib.Path("src/realtime/websocket.py").read_text()
    assert "[ws_subscribe_reject]" in src
    assert 'logger.error(' in src  # 정확히는 거절 분기 내부 검증 필요 — AST 분석 권고
    # AST 단위: _handle_raw 함수 내 `[ws_subscribe_reject]` 문자열 + logger.error Call 동반
    ...
```

#### G-D (HIGH) `pool.subscribe` promote/drop 분기의 logger.info individual 보존

**패턴**:

```python
def test_pool_promote_drop_logger_info_preserved():
    """사이클 74 G-D — pool.subscribe promote/drop 분기 logger.info 영속.

    LMS chain 진단 영역 + drop 가시화 의무. aggregation 흡수 금지.
    """
    src = pathlib.Path("src/realtime/websocket_pool.py").read_text()
    assert "[pool_promote]" in src
    assert "[priority_drop_pool]" in src
    # AST: subscribe 함수 내 두 prefix 동반 logger.info Call 존재 검증
```

#### G-E (MEDIUM) `_ws_action_flush_loop` task lifecycle 가드

**패턴** (사이클 42 `_heartbeat_metrics_loop` task lifecycle 답습):

```python
def test_ws_action_flush_loop_lifecycle():
    """사이클 74 G-E — connect/disconnect 가 _ws_action_flush_task 관리 영속.

    좀비 task 방지 + 잔여 카운터 손실 방지 (마지막 flush 1회).
    """
    src = pathlib.Path("src/realtime/websocket.py").read_text()
    assert "_ws_action_flush_task" in src
    assert "_ws_action_flush_loop" in src
    # connect() 분기에 create_task / disconnect() 분기에 cancel + await
```

#### G-F (HIGH) `_ws_action_collector` flush 시 종목 cap 20 + overflow ...+N

**패턴** (사이클 28 `[stale_watcher_detail]` 영속 답습):

```python
def test_ws_action_collector_cap_20():
    """사이클 74 G-F — flush 시 종목 cap 20 + overflow ...+N 영속.

    사이클 28 [stale_watcher_detail] 패턴 답습. 메시지 길이 폭주 차단.
    """
    src = pathlib.Path("src/realtime/websocket.py").read_text()
    # _flush_ws_action_collector 함수 내 `[:20]` slice + `...+` 문자열 패턴
    assert "_flush_ws_action_collector" in src
    # 정확히는 함수 본체 AST 내 슬라이스 + f"...+{overflow}" 패턴 검증
```

#### G-검출 정밀 패턴 권고

사이클 67 G-16 / 사이클 73 G-6.R AST 패턴 100% 답습:
- `ast.AsyncFunctionDef` / `ast.FunctionDef` walk → 함수별 isolation
- `ast.Call.func.attr` + `ast.Call.func.value.id` 조합으로 `logger.info` 등 정확 매칭
- 문자열 prefix (`[ws_subscribe_reject]` / `[pool_promote]` 등) 잔존 여부는 단순 grep 보강

### 5. 사이클 75+ 인계 카드

#### 카드 #19 (HIGH 잔존, 사이클 73 인계) — `realtime_other` 16.13x dup 영역

- **현 상태**: 사이클 73 운영 실증 — `auth` 1.43x + `realtime_other` 16.13x + 기타 dup 잔존 (`src.realtime.websocket` 6.68x 외 영역)
- **권고 후행 시정**: 사이클 75+ 별개 카드 — 영역 식별 + 옵션 E-1 패턴 확장 적용 가능성 검토
- **회귀 가드**: 사이클 74 dup 측정 도구 (사이클 73 측정 절차) 재활용
- **위험 등급**: HIGH (실증 운영 dup 영역)
- **선행 의뢰**: 사이클 74 옵션 E-1 운영 1주 검증 후 카드 #19 발의

#### 카드 #20 (MEDIUM) — collector 헬퍼 추출 (`src/realtime/_log_aggregator.py`)

- **현 상태**: 사이클 74 = `[ws_action_summary]` introduction. 사이클 76+ 시점에 `[ws_heartbeat]` + `[ws_action_summary]` + (조건부) `[swing_rest_poll]` 통합 헬퍼 후보
- **권고**: 3 영역 확정 후 헬퍼 추출 (사이클 67 stale_manager 분해 패턴 답습)
- **회귀 가드**: 행위 보존 + 테스트 패턴 답습
- **위험 등급**: MEDIUM (refactor)
- **선행 의뢰**: 사이클 74 운영 1주 + 옵션 C (`[swing_rest_poll]` aggregation) 채택 결정 후

#### 카드 #21 (MEDIUM) — `[ws_opsp_backoff_state]` 5분 주기 emit

- **현 상태**: 사이클 74 옵션 E-1 도입 시 OPSP0002 ALREADY emit 이 aggregation 흡수 → `_opsp_backoff_until` dict 운영 가시화 약화 위험
- **권고**: `_ws_action_flush_loop` 내부에 `[ws_opsp_backoff_state] active=N peek=[ticker(remain_secs)]` 1행 추가 emit (5분 주기)
- **회귀 가드**: `_opsp_backoff_until` dict 길이 + 만료 시각 정확성
- **위험 등급**: MEDIUM
- **선행 의뢰**: 의제 2 매트릭스 사용자 결정 후

#### 카드 #22 (LOW) — `_restore_subscriptions_after_reconnect` cumulative emit

- **현 상태**: 재연결 후 모든 구독 재SEND → 자동 aggregation 흡수
- **권고**: `connect()` 재연결 분기에 `[ws_restore_after_reconnect] reconnect_count=N restored=K` 1행 emit (1회/재연결)
- **위험 등급**: LOW
- **선행 의뢰**: 사이클 74 push 후 운영 1주 발의

### 6. 사용자 결정 의제 (자문 결과로 발견된 추가 결정 영역)

#### 결정 Q2-D — OPSP0002 ALREADY emit 처리

옵션 A: aggregation 흡수 (사이클 74 권고) + 카드 #21 `[ws_opsp_backoff_state]` 별도 5분 주기 emit (운영 가시화 보강)
옵션 B: individual 보존 (사이클 17 보강 영역 — KIS LMS 위험 직접 영향 — 운영 가시화 우선)
옵션 C: DEBUG 강등 (운영 미노출, 결함 시만 LOG_LEVEL=DEBUG)

**권고**: 옵션 A — aggregation 흡수 + 카드 #21 별도 emit. 사이클 17 보강 의도 (`_opsp_backoff_until` 관리) 영속 + dup 흡수.

#### 결정 Q2-E — `[ws_ack_orphan]` 분기 처리

옵션 A: 현행 유지 (DEBUG, 운영 미노출)
옵션 B: aggregation 흡수 (`_record_action` 호출 + flush)

**권고**: 옵션 A — 현행 DEBUG 유지. 사이클 14-C race 진단 영역, 결함 발생 시만 LOG_LEVEL=DEBUG 일시 활성 패턴.

#### 결정 Q3 — collector 헬퍼 (의제 3 영역) 사이클 74 동시 도입 여부

옵션 A: **C-individual 채택** (사이클 74 단계적 + 사이클 76+ 카드 #20 후속) — refactor-expert 권고
옵션 B: C-shared 동시 도입 (`src/realtime/_log_aggregator.py`) — 위험 등급 MEDIUM 추가 + 사이클 74 변경 폭주

**권고**: 옵션 A. 사이클 60/61/67 단계적 분해 패턴 답습. 사이클 74 = WebSocket 영역 first introduction → 운영 검증 *전* 헬퍼 추출 시 sandbox 효과 (사이클 67 stale_manager 답습).

#### 결정 Q4 — flush 시점 (5분 주기) 변경 여부

옵션 A: **5분 주기 영속** (사이클 42 `[ws_heartbeat]` 영속) — refactor-expert 권고
옵션 B: 1분 주기 단축 (운영 가시화 빠름 — dup 흡수 효과 ↓)
옵션 C: 10분 주기 (dup 흡수 효과 ↑ — 운영 lag ↑)

**권고**: 옵션 A. 사이클 42 `[ws_heartbeat]` 사용자 수용 영속 + 사이클 75+ 운영 측정 후 조정 의제로 인계.

#### 결정 Q5 — `_ws_action_flush_loop` 마지막 flush 의무

옵션 A: **`disconnect()` cancel *전* 마지막 flush 1회 호출** — refactor-expert 권고 (잔여 카운터 손실 방지)
옵션 B: cancel 만 (잔여 카운터 손실 수용)

**권고**: 옵션 A. 사이클 42 `_heartbeat_metrics_loop` 답습 + 운영 환경 disconnect 가 매일 20:00 `unsubscribe_all()` 직후 발생 → 마지막 flush 가 정산 *직전* 운영 가시화 데이터 보존.

## 비권고 사항 (검토했으나 변경 권고하지 않는 항목)

1. **헬퍼 사이클 74 동시 도입** — 사이클 60/61/67 단계적 패턴 답습 (3회 반복 규칙 엄격).
2. **`[ws_ack_orphan]` 흡수** — 현행 DEBUG 유지 (사이클 14-C 영속).
3. **flush 주기 변경** — 사이클 42 영속 (사용자 수용 영속).
4. **`_send_subscribe` `_ws is None` 분기 emit 추가** — 정상 lifecycle disconnect 상태.
5. **`pool.subscribe` 체결통보 메인 강제 분기 emit 추가** — 1회/세션 lifecycle (절대 안전 규칙 영역 — 추가 노출 가치 낮음).

## 안전 규칙 영속 보장 확인

| 안전 규칙 | 사이클 74 옵션 E-1 영향 |
|----------|---------------------|
| 체결통보 (H0STCNI0/H0STCNI9) 구독 | **0** (logger.info 만 흡수, 구독 사이트 무변경) |
| uvicorn 단일 워커 | **0** |
| 주문번호 매핑 동기 | **0** |
| 체결통보 선행 race 가드 | **0** |
| 익일 청산 NEXT_DAY_STABILIZE_SECS=30 | **0** |
| NXT 매도 거부 좀비 차단 (사이클 55 R-1) | **0** |
| WebSocket 4중 안전망 (F1 / `_scan_loop` / K stale watcher / `_resubscribe_stale_priority`) | **0** (호출 시점/순서 무변경) |
| `_subscriptions` ACK 정합성 가드 (orphan ACK race) | **0** |
| KIS LMS chain 차단 (사이클 17 / 24 / 29-R1/R2/R3) | **0** (ERROR / 거절 / promote / drop individual 보존) |
| 사이클 38 명문화 (`tradable_boards` 매수 진입 전용) | **0** |
| 사이클 66 cap=10 priority 분리 | **0** |
| 사이클 67 stale_manager 분해 | **0** |
| 사이클 72 dedupe + 73 R-1/R-2/S-1 영속 | **유지** (dedupe 500ms 캐시 안전망 영속 — aggregation 흡수 후에도 안전망 보존) |
| KST 강제 (사이클 65 H2/H2-bis / 68) | **0** |
| 사이클 29 005935 사고 chain 진단 | **유지** (ERROR/거절/promote/drop individual 보존 = 매트릭스 영속) |

## 인계

- **team-leader**: 본 메모 + 결정 Q2-D/Q2-E/Q3/Q4/Q5 사용자 결정 의뢰
- **tdd-engineer**: Red 발주 시 회귀 가드 5종 (G-A / G-B / G-C / G-D / G-E / G-F) AST 영구 가드 + 단위 회귀 가드 (collector record/flush + 5분 freezegun + cap 20 overflow + lifecycle cancel/await + 마지막 flush)
- **domain-expert**: 카드 #19 (HIGH) 검토 시 행위 영향 평가 의뢰 (사이클 74 push 후 1주 운영 검증)
- **사용자 결정 후 사이클 74 push 의무** — 사이클 67 8 사이클 연속 패턴 영속

## refactor-expert 카드 요약

| 카드 # | 위험 | 의도 | 회귀 가드 | 영향 |
|--------|------|------|----------|------|
| **#A (HIGH)** | HIGH | 옵션 E-1 collector + flush_loop 도입 | G-A/B + 단위 collector record/flush + freezegun 5분 + lifecycle | dup 6.68x → ≤2.0x 추정 (운영 검증 의무) |
| **#B (HIGH)** | HIGH | ERROR 보존 매트릭스 영속 (사이클 73 R-2 영속) | G-C/D + grep 잔존 검증 | 사이클 29 005935 LMS chain 진단 의무 영속 |
| #C (MEDIUM, 카드 #21) | MEDIUM | `[ws_opsp_backoff_state]` 5분 주기 emit | 단위 + freezegun | OPSP0002 backoff 운영 가시화 보강 |
| #D (LOW, 카드 #22) | LOW | `[ws_restore_after_reconnect]` 1행 emit | 단위 | 재연결 chain 진단 보강 |
| #20 (MEDIUM, 사이클 76+) | MEDIUM | collector 헬퍼 추출 (`src/realtime/_log_aggregator.py`) | 행위 보존 + 사이클 67 답습 | DRY |
| #19 (HIGH, 사이클 75+) | HIGH | `realtime_other` 16.13x dup 영역 식별 + 시정 | 운영 dup 측정 도구 재활용 | dup 16x → ≤2.0x |

---

**자문 일자**: 2026-06-08
**자문자**: refactor-expert (행위 보존 + 구조 개선 + 사이클 29 LMS chain 진단 의무 영속)
**다음 단계**: team-leader 가 사용자 결정 의뢰 → tdd-engineer Red 발주 → backend-dev Green 구현 → tester 통합 검증 → push → 사이클 75+ #19 발의
