# CLAUDE.md — src/realtime/ (WebSocket 실시간)

KIS WebSocket 실시간 시세 수신 + 체결통보 처리. 메인 + 보조 N 세션 풀(`WebsocketPool`).

> 사이클별 변경 이력: `docs/HARNESS_CHANGELOG.md`

## 자금 안전 절대 원칙

- **체결통보 (H0STCNI0/H0STCNI9) → 메인 세션 단일 강제** — `_enforce_main_only_execution_notice` + `WebsocketPool.subscribe` 분기. 보조 시도 시 `QuoteSessionExecutionNoticeError`
- **매매/잔고/체결조회** → 메인 단일 (`src/auth/CLAUDE.md` 가드)
- **보조 세션** → 시세 only. `kis_quote_accounts` DB 등록 후 `scheduler._boot()` 재시작 시점 연결

## websocket_pool.py — WebsocketPool

`WebsocketPool` 클래스 + `kis_ws_pool` 싱글톤. 외부 호출자(scanner/risk/scheduler) 인터페이스 100% 보존 + 내부 분배 캡슐화.

### 분배 정책

- **HIGH 우선순위** (보유 / 익일청산) → 메인 세션 절대 보장 (`bypass_limit=True`)
- **LOW 우선순위** (스캐닝) → 보조 세션 라운드로빈. 가득/disconnect 세션 건너뜀. 모두 가용 없으면 메인 fallback
- **중복 ticker** → 메인 우선. 보조에 있는데 HIGH 로 들어오면 메인 승격 + 보조 unsubscribe + `[pool_promote]` 로그
- **모든 세션 가득** → drop + `[priority_drop_pool] tr_key=... priority=LOW reason=all_sessions_full main=N/41 quotes=M` INFO
- **총 슬롯 = 41 × (1 + N)** (메인 + 보조 N)

### 인터페이스

- `subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False) -> Optional[str]` — 세션 label 반환 ("main" / "quote-N"). drop → None
- `unsubscribe(tr_id, tr_key)` — 분배 추적된 세션에서 해제. 추적 없으면 noop. 체결통보 메인 강제
- `unsubscribe_all()` — 분배 추적 dict 순회 + 모든 세션 매칭 해제
- `unsubscribe_in_pool(tr_id, tr_key)` — K stale watcher 헬퍼. 추적 dict 제거 + 세션 unsubscribe. 강제 재등록 시 라운드로빈 재선택 의도
- `resend_subscribe_for_ticker(tr_id, tr_key)` — `_ticker_to_session` 추적으로 정확한 세션에 재SEND(추적 없으면 메인 fallback). ⚠️ **production 호출자 0건** — 사이클 17(2026-05-19)이 KIS 공식 답변("기등록한 사항을 재등록하지 않도록")을 반영해 K stale watcher 의 1~5회 재SEND 분기를 폐기했다. 함수 자체는 향후 운영 도구 후보로 보존하되 **재도입 금지** — AST 가드 `tests/unit/engine/test_stale_force_reregister_constant_removed.py`(G-DEAD-2)가 `src/engine/`·`src/realtime/` 전역에서 호출부 0건을 강제한다
- `get_subscribed_tickers() -> set[str]` — 메인 + 보조 TICK 합집합
- `get_acked_tickers() -> set[str]` — 합집합 ACK
- `get_subscriptions_by_session() -> dict[str, set[str]]` — **사이클 28 (2026-05-21)**: 세션 label → ticker set (역인덱싱, 영속 dict 미추가). scheduler 의 `[stale_watcher_detail]` / `[tick_coverage_session]` prefix + `/api/realtime/subscriptions` 의 `tickers_detail` 응답에 활용
- `get_session_status() -> list[dict]` — 세션별 label/subscribed/acked/limit/ws_connected/reconnect_count + tickers
- `start(dispatch_message=None)` — DB `kis_quote_accounts.list_accounts(active_only=True)` 조회 → 각 라벨별 `KisWebSocket` 생성 + `connect()` task 발화. 보조 0개 → noop + `[pool_start]` INFO. `_started` 멱등 가드
- `stop()` — 보조 connect task cancel + 각 보조 `disconnect()`. `_quotes` / `_ticker_to_session` / `_started` clear
- `disable_quote_session(label)` — health monitor 자동 비활성 헬퍼. label → 1-based index → 세션 disconnect + `_quotes` 제거 + `_ticker_to_session` 정리 + `_round_robin_idx=0` reset. 메인 라벨 noop (안전 가드)
- 호환 property: `_subscriptions` / `_subscriptions_acked` / `_ws` / `_reconnect_count` — 합집합 또는 메인 기준

### 라우트 응답 (`GET /api/realtime/subscriptions`)

```json
{
  "total": 123, "acked": 100, "fresh_60s": 95, "stale_60s": 5, "limit": 246,
  "sessions": [
    {"label": "main", "subscribed": 41, "acked": 41, "fresh": 40, "stale": 1, "limit": 41, "ws_connected": true, "reconnect_count": 0, "tickers": {"subscribed": [...], "acked": [...]}},
    {"label": "ISA", "subscribed": 12, ...}
  ]
}
```

- `total/acked` = 합집합 카운트, 세션별 분해는 `sessions[*]`
- `limit = MAX_SUBSCRIPTIONS × len(sessions)` (메인 + 보조 합산 용량)
- **사이클 43 (2026-05-22) — 세션 라벨 통일**: 보조 세션 라벨 `quote-1/quote-2/quote-3` 1-based index → DB `kis_quote_accounts.label` (ISA/sub/gold 등 사용자 등록 라벨) 직접 사용. `_session_label(ws)` / `get_session_status()` / `disable_quote_session(label)` / `[tick_coverage_session]` / `[stale_watcher_detail]` / `[priority_drop_pool]` / `[silent_inactive_force_reconnect]` / 사이클 42 `[ws_heartbeat]` / UI `KisAccountPoolCard` 모두 동일 라벨. 메인 라벨 `"main"` 절대 보존. `_quotes[idx]` 인덱스 자체는 변경 0. **사이클 194 (2026-07-06)**: `force_reconnect_session`(stale_session_recovery.py) 의 라벨→세션 *해석* 로직이 사이클 43에서 미이주되어 구식 `int(label.replace("quote-",""))` 파싱 잔존 → DB 라벨(gold/sub) 시 ValueError → `알 수 없는 label` → 보조 세션 강제 재연결 미발화 회귀였음. 사이클 194가 `disable_quote_session` 의 `getattr(q, "_label", None) == label` 매칭으로 교체 = 사이클 43 라벨 통일이 이 함수까지 완결 (로그 prefix 는 DB 라벨이었으나 내부 해석만 quote-N 잔존이던 문서-코드 불일치 해소). **사이클 195 (2026-07-06)**: `build_session_subscription_view`(stale_diagnostics.py, `[stale_watcher_detail]` capacity 로그 빌더)에도 동일 계열 quote-N 잔존 2곳 — phantom `label_order` 생성(`f"quote-{i}"`, 전부 skip되던 noise) + capacity 해석 `startswith("quote-")` 인덱스 파싱이 DB 라벨(gold/sub) 미매칭 → `cap_used=len(tickers)` degrade. 사이클 195가 phantom 제거(`label_order=["main"]`, groups 키가 채움) + capacity 해석 DB 라벨 매칭(동일 `disable_quote_session` 패턴)으로 시정 = 사이클 43 계열 quote-N 파서 전수(force_reconnect 194 + stale_diagnostics 195) 종결. 관찰성 전용(capacity_used 정확화), 매매 안전성 8영역 diff 0
- 보조 0개 → `sessions` 길이 1 (main only, 기존 호환)

## websocket.py — KisWebSocket 연결 관리

- WebSocket 접속키 발급 (`/oauth2/Approval`)
- 종목 시세 구독/해제 (**최대 41건, KIS 공식 한도**)
- 체결통보 구독 (실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호)
- Heartbeat 감시 (30s 미수신 → 재연결)
- 자동 재연결 (최대 5회, 지수 백오프)
- 연결 시 AES iv/key 수신 + 저장
- 구독 한도 초과 시 에러 대신 경고 + skip. **사이클 197 (2026-07-07)**: LOW(`bypass_limit=False`) 구독이 `MAX_SUBSCRIPTIONS(41)` 초과 시 `최대 구독 수(41) 도달, {tr_id}/{tr_key} 구독 건너뜀` WARNING 을 `_max_sub_warn_cap: DailyEmitCap[(tr_id,tr_key)]` 로 게이트 (1회/키/일, `_max_sub_warn_date` KST 자기리셋 = scheduler 배선 불요). 5분 scan 재시도가 동일 LOW 키(주로 H0UNMKO0 후보)를 반복 emit 하던 스팸(7/3 640건/일 실측) → 종목당 1회. **드롭 `return`·`bypass_limit` 분기 byte 불변** (HIGH 보유/익일청산 절대 보호 사이클 32 R4 영속, 관찰성 전용). scanner `[priority_drop]` 카운트 요약 + HIGH 초과 `[priority] HIGH 구독 한도 초과` ERROR 는 별도 → cap 이 매매/경보 신호 미차단. 회귀 가드 `tests/unit/realtime/test_cycle197_max_sub_warn_cap.py` (G-1 반복 1회 + G-4/G-5 SAFETY 드롭·bypass 불변 + G-6 AST should_emit/mark_emitted/return 동반)
- `__init__(*, token_manager=None, is_main=True, label=None)` — 보조 세션은 외부 매니저 주입 (사이클 7-A `get_token_manager(label)`). **사이클 42 (2026-05-22)**: `label` kwarg 신규 — 메인은 `"main"` / 보조는 DB `kis_quote_accounts.label` 직접 (예: ISA/sub/gold). 미지정 시 `is_main` 기반 자동 결정
- **PINGPONG 가시성** (사이클 42, 2026-05-22): KIS 가 메인 세션에 약 11~14s 간격 PINGPONG JSON 송신 → `_handle_raw` `tr_id=="PINGPONG"` 분기에서 즉시 echo-back + `_pingpong_recv_count` / `_pingpong_last_at` 갱신. **L1 DEBUG**: `[ws_pingpong_echo] label=...` (운영 INFO 미노출, LOG_LEVEL=DEBUG 일시만). **L2 INFO 5분 통계**: `_heartbeat_metrics_loop` 가 `HEARTBEAT_METRICS_INTERVAL_SECS=300` 주기로 `[ws_heartbeat] label=... window=300s pingpong_recv=N avg_interval=Xs last_age=Ys heartbeat_timeout=Z` emit + write_log 영구 보존 + 카운터 reset. `_receive_loop` `asyncio.TimeoutError` 분기에 `_heartbeat_timeout_count += 1`. Task lifecycle: `connect()` 진입 직후 1회 발화 + `disconnect()` cancel + await 정리 (좀비 task 방지, asyncio.CancelledError graceful). 메인+보조 인스턴스별 독립 카운터. **운영 관찰** (5/22): 메인 PINGPONG 22~27건/5분 (avg 11~14s 간격, last_age 3~7s — 정상). 보조 시세 세션은 PINGPONG 0건 — KIS 가 시세 전용 세션엔 PINGPONG 미송신 정책 추정 (heartbeat_timeout 0 = 시세 송수신 활발로 연결 유지)
- **WS action aggregation 옵션 E-1** (사이클 74, 2026-06-08): WebSocket 구독/ACK/해제/OPSP0002 ALREADY logger.info 직접 emit → 5분 윈도우 tr_id별 1행 aggregation 흡수. `_ws_action_collector: dict[str, dict[str, list[str]]]` 인스턴스 변수 (tr_id → {SUBSCRIBE/UNSUBSCRIBE/ACK: list[tr_key], OPSP_ALREADY: int}) + `_record_action(tr_id, tr_key, action)` (`_send_subscribe` 진입 + SUBSCRIBE SUCCESS + OPSP0002 ALREADY 분기 호출) + `_flush_ws_action_collector()` (`[ws_action_summary] label=... tr_id=... window=300s +N SUBSCRIBE [...] -M UNSUBSCRIBE [...] ack=K opsp_already=L` 1행 emit, 종목 cap 20 + overflow `...+N` 사이클 28 패턴 답습) + `_ws_action_metrics_loop` task (5분 주기, 사이클 42 `_heartbeat_metrics_loop` 패턴 답습) + `connect()` 진입 직후 task 시작 + `disconnect()` cancel *전* 마지막 flush 1회 (Q5 옵션 A). **ERROR 보존 매트릭스 7 prefix individual 영속** (사이클 29 005935 LMS chain 진단 의무): `[ws_subscribe_reject]` logger.error (사이클 73 R-2) + `[silent_inactive_force_reconnect]` (사이클 24/29-R2) + `[ws_heartbeat]` heartbeat timeout (사이클 42) + `[aes_key_skip]` (사이클 16) + `[ws_reverify]` WARNING (사이클 73 R-1) + `[stale_force_retry_cap]` / `[stale_priority_resubscribe_cap_exceeded]` (사이클 66 K-10). 운영 효과 예상: ~4,000/day INSERT → ~10/day 1행 (~95% 감소). AST 영구 가드 G-7 (`_send_subscribe` 직접 logger.info 0건) + G-8-A/G-8-B (`_run_swing_rest_poll_once` / `check_and_resubscribe_stale` 직접 logger.info 0건). 사이클 17 OPSP0002 backoff (`_opsp_backoff_until` dict + `subscribe()` 진입 검사) 행위 무변경 — collector 흡수만

### subscribe / 거절 감지 / ACK 추적

- **`subscribe(tr_id, tr_key, *, bypass_limit=False)`**: `bypass_limit=True` 면 `MAX_SUBSCRIPTIONS` 한도 skip + 무조건 add. 보유·익일청산 종목에 사용 — 손절·트레일링 감시 우선
- **구독 거절 감지 (E2)**: `_handle_raw()` 가 `body.rt_cd != "0"` 또는 `msg1` 키워드 (`ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/EXCEED/DUPLICATE` 대소문자 + 한국어 `한도/초과/중복/허용되지/권한`) 매칭 시 `_subscriptions.discard` + `_subscriptions_acked.discard` + `logger.error("[ws_subscribe_reject] tr_id=... ticker=... msg_cd=... msg1=...")` (사이클 73, 2026-06-08: write_log 직접 호출 제거 + logger.error 메시지에 prefix `[ws_subscribe_reject]` 신규 명시 → `_DbLogHandler` 위임 단일 INSERT, dup 2.40x → ≤2.0x). 거절 분기 후 조기 return → 정상 SUBSCRIBE SUCCESS AES iv/key 저장 분기 분리. 다음 `_scan_loop` 자연 재시도
- **OPSP0002 ALREADY IN SUBSCRIBE**: 거절 아닌 "KIS 측 이미 활성" 의미 — 거절 분기 *전* `_subscriptions/_subscriptions_acked.add` 로 정합성 회복 + INFO. msg_cd `OPSP0002` 또는 `ALREADY`/`이미 구독`/`이미 등록` 매칭
- **재연결 후 자동 검증 (F1)**: `connect()` 가 재연결 + 기존 구독 복원 직후 `_reconnect_count > 0` 가드 통과 시 `asyncio.create_task(_verify_subscriptions_after_reconnect())`. `VERIFY_AFTER_SECS=60` 대기 → `scanner.ticker_last_tick` 비교 → `VERIFY_FRESHNESS_SECS=60` 내 tick 없는 TICK 구독 1회 재전송. KIS silent inactive 차단. 안전 가드: `_reverify_in_progress` 중첩 방지 / 첫 연결 발화 안 함 / 검증 중 disconnect 시 종료 / 예외 ERROR + 플래그 해제. WARNING 시 `logger.warning("[ws_reverify] reconnect_count=N stale=M/T preview=[..]")` (사이클 73, 2026-06-08: write_log 직접 호출 제거 → `_DbLogHandler` 위임 단일 INSERT)
- **SUBSCRIBE ACK 추적 (G1)**: `_subscriptions_acked: set[tuple[str, str]]`. `_handle_raw` 가 `rt_cd=="0" AND "SUBSCRIBE SUCCESS"` 매칭 시 add + INFO. `subscribe`/`unsubscribe`/E2 거절 시 discard. `connect()` 재연결은 `_restore_subscriptions_after_reconnect()` 헬퍼가 ACK clear + send 재전송 동기 처리 — F1 task 발화 *전* 완료
- **`_subscriptions` 정합성 가드 (in-flight ACK race 차단)**: SUBSCRIBE SUCCESS 분기에서 `(tr_id, tr_key) in self._subscriptions` 가드. orphan ACK 는 `_subscriptions` 부재 → acked 에 add 안 함 + DEBUG `[ws_ack_orphan]`. `_scan_loop` 5분 주기 unsubscribe→ACK 도착 race 차단. AES iv/key 저장 분기는 정합성 가드와 무관 (단일 글로벌)
- **사이클 135 (2026-06-15) `_subscribed_at` 구독 ACK grace period (180s, Q3=A 영속)**: `KisWebSocket.__init__` 에 `_subscribed_at: dict[tuple[str, str], datetime] = {}` 인스턴스 변수 신규 (사이클 88 G-REJECT-3 4 dict → **5 dict 분리** 영속). **5 사이트 record/pop**: (1) SUBSCRIBE SUCCESS = `_subscribed_at[(tr_id, tr_key)] = now()` (2) OPSP0002 ALREADY = 동일 갱신 (자문 의제 4 KIS 측 활성 = 우리 측 grace 시점 갱신 정합) (3) `unsubscribe()` = pop (4) E2 거절 = pop 동행 (5) `_restore_subscriptions_after_reconnect()` = `clear()` 동행 (재연결 grace 시점 초기화). **websocket_pool 합산 property**: `WebsocketPool._subscribed_at` (메인+보조 모든 세션 dict.update 합집합). **grace 가드** `stale_watcher_core.check_and_resubscribe_stale` 영역 = `_is_within_grace(t)` = `if t in ticker_last_tick: return False` (G-GRACE-7 첫 시세 입수 후 grace 미적용 + 60s 영속 = 사이클 29 005935 보호 영구 확정) + `ack_at not datetime: return False` (G-GRACE-6 ACK 미확인 race 보호) + try/except 안전 폴백 (mock TypeError 차단 = 사이클 63 Phase 2-A3 mock 회귀 가드 보존). **상수**: `stale_diagnostics.SUBSCRIBE_GRACE_SECS = 180` (3.0 × STALE_FRESHNESS_SECS, P95 안전 마진 정합 = KOSPI 대형주 25s / 중형주 55s / KOSDAQ 중형주 75s / 소형주 150s / 10시 이후 480s). `stale_manager.__all__` re-export. **회귀 가드**: `tests/unit/realtime/test_cycle135_subscribe_grace_period.py` 14 케이스 (G-GRACE-1~10 + G-AST-GRACE 5 dict 분리 + G-AST-CONST 단일 정의처 + G-SAFETY-1/2 매매 안전성 직접 검증). domain-expert 자문 `_workspace/domain_consult/cycle135_websocket_grace_period.md` 영속
- **사이클 16 (2026-05-19) AES 키 격리 가드**: `KisWebSocket.__init__(*, is_main: bool = True)` 신규 인자 + `_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0", "H0STCNI9"})` 모듈 상수 + `_handle_raw` SUBSCRIBE SUCCESS 분기에 이중 가드: (1) `self.is_main=True` + (2) `tr_id in _EXECUTION_NOTICE_TR_IDS` 모두 만족 시에만 `set_aes_keys(iv, key)` 호출. 그 외 시세 SUBSCRIBE SUCCESS / 보조 세션 SUBSCRIBE SUCCESS 는 모듈 전역 키 저장 skip + DEBUG `[aes_key_skip] tr_id=... is_main=...` 로그. `WebsocketPool.start()` 가 보조 세션 생성 시 `KisWebSocket(token_manager=manager, is_main=False)` 명시. 사이클 7-C 풀 통합 (메인+보조 N 세션) 도입 시점부터 잠재 결함 — 보조 세션 ISA 의 시세 SUBSCRIBE SUCCESS 의 AES 키가 모듈 전역 `_aes_iv`/`_aes_key` 덮어씌워 메인 체결통보 (H0STCNI0/H0STCNI9) 복호화 실패하던 race 차단. 2026-05-19 11:20:23~11:22:31 운영 사고 11건 대응. 회귀 가드: `tests/unit/realtime/test_aes_keys_main_only.py` 6 케이스(is_main default True / is_main False 명시 / 메인+체결통보 저장 / 메인+시세 skip / 보조+시세 skip / 보조+체결통보 이중 안전망 skip). 자체 인스턴스 변수 `self.aes_iv`/`self.aes_key` 는 디버깅용 보존
- **사이클 17 (2026-05-19) OPSP0002 backoff 가드**: `KisWebSocket.__init__` 에 `_opsp_backoff_until: dict[tuple[str, str], float] = {}` 인스턴스 변수 신규. `_handle_raw` 의 `OPSP0002 ALREADY IN SUBSCRIBE` 분기에서 `self._opsp_backoff_until[(tr_id, tr_key)] = time.time() + 300.0` 기록 + INFO `[ws_opsp_backoff until=+300s]`. `subscribe(tr_id, tr_key, *, bypass_limit=False)` 진입 시 `time.time() < self._opsp_backoff_until.get(key, 0)` 면 send skip + DEBUG `[ws_subscribe_backoff] remain=...s` (한도 검사 *전*). `_subscriptions` 도 add 안 함 → 다음 자연 재시도 시 일관 동작. `bypass_limit=True` (HIGH 보유/익일청산) 는 검사 skip — 손절 우선 보장. **사이클 17 보강 (2026-05-19) — 60s → 300s 연장**: KIS 공식 답변 ("기등록한 사항을 재등록하지 않도록") 반영. `_scan_loop` 5분 주기 ≥ backoff 만료 보장 → 같은 사이클 내 재시도 차단. 2026-05-19 15:15 KST `tick_coverage ratio=0.0%` 운영 사고 (OPSP0002 후 즉시 재구독 → 또 OPSP0002 → 무한 루프 + KIS WS Rate Limit 위양성 폭증) 대응. 회귀 가드: `tests/unit/realtime/test_ws_subscribe_backoff.py` 5 케이스 (OPSP0002 후 backoff 300s 등록 / 유효 시간 내 send skip / 만료 후 정상 send / 다른 종목 격리 / 정상 SUBSCRIBE SUCCESS 후 미진입)
- **수동 재구독 endpoint**: `POST /api/realtime/resubscribe` — F1 자동 로직과 동일 규약 (`_send_subscribe(TICK_TR_ID, t, subscribe=True)` + 50ms sleep + `_subscriptions` 직접 수정 금지). 운영 시간대 ScanMonitor 끊김 배지 옆 인라인 버튼. 응답 `{resubscribed, tickers(sorted)}`. `_ws is None` 시 400. `[ws_manual_resubscribe]` write_log

### 우선순위 정책

- `scanner.subscribe_filtered_stocks(priority_groups=...)` 가 HIGH→LOW (positions → next_day_clear → swing → momentum → breakout) 순으로 처리
- HIGH (보유/익일청산) 는 `bypass_limit=True` 절대 보장
- 후순위는 잔여 슬롯 초과 시 drop + `[priority_drop] swing=X momentum=Y breakout=Z` INFO. HIGH 단독 41 초과 시 ERROR
- **사이클 25-B (2026-05-20) `_resubscribe_stale_priority` 분리**: positions/next_day_clear stale → HIGH+bypass_limit=True, 그 외 후보 stale → LOW+bypass_limit=False. 보유/익일청산 보장 절대 유지 + 후보 메인 과부하 방지

### get_subscribed_tickers / get_acked_tickers

- `get_subscribed_tickers() -> set[str]` — TICK(H0STCNT0/H0NXCNT0/H0UNCNT0) 구독 **합집합**. 체결통보·장운영정보 제외
- `get_acked_tickers() -> set[str]` — TICK 필터 ACK set. KIS REST/WS 슬롯 사용현황 조회 API 미존재 → 우리 측 ACK 추적이 "SEND 후 무응답" 가시화의 유일한 길
- 🔴 **cycle293(2026-09-14) — "합집합" 이 이제 참이다.** 종전 서술("현행 구독은
  `H0UNCNT0` 단일, 나머지 둘은 예약 상수")은 폐기한다. 판정은 `tr_id == TICK_TR_ID`
  등가 비교가 아니라 **단일 정본 집합 `scanner.TICK_TR_IDS` 의 멤버십**이다 —
  등가 비교가 하나라도 남으면 전용 채널로 옮긴 종목이 이 집합에서 **조용히
  사라져** K stale watcher 블라인드 · `delta_unsubscribe_dropped` 미해제(실제
  슬롯 누수) · 매 5분 재SEND · `[tick_coverage]` 분모 감소(= cycle252 「은폐
  금지」 계약 위반)가 한꺼번에 생긴다
- **진단 프로브 격리 기준이 「채널」→「프로브 정체성」으로 바뀌었다.** cycle253 은
  "TICK 집계는 `H0UNCNT0` 만 센다" 는 **채널 동일성**에 프로브 격리를 얹었는데,
  cycle293 이 그 전용 채널을 실 구독에 쓰기 시작하며 그 추론이 죽었다. 지금은
  `websocket.is_probe_excluded(tr_id, tr_key)` 가 판정하고 집합은
  `PROBE_EXCLUDED_TUPLES`(+ 수명 dict `_PROBE_EXCLUSION_DAY`)에 있다. 수명 =
  프로브 stop · 20:00 `unsubscribe_all`/`stop`(`reset_probe_exclusions()`) ·
  **KST 날짜 경과 시 판정 시점 자기 회수**. 비어 있는 것이 정상 상태다 —
  남으면 라이브 구독을 은폐한다(그 튜플이 실 구독과 **같은 식별자**다)

### 시세 채널 — **속성축 리졸버 2단계 착지(cycle293)**, 시간축 전환은 3단계

사이클 26(2026-05-20, 커밋 f7f0766)이 도입한 시각 기반 채널 전환(활성 TR_ID 판정 함수 +
종목 단위 원자 전환 루프)은 **108일간 `src/` 호출자가 0**이었다 — 정의만 있고 어디서도
호출되지 않아 실제 구독은 처음부터 `TICK_TR_ID = H0UNCNT0`(통합) 단일 채널로만 동작했다.
cycle257(2026-09-05)이 이를 삭제(`scanner.py`/`scheduler.py`)했다.

**cycle293(2026-09-14)이 그 자리에 속성축 리졸버를 놓았다 — 자문 §5 의 2단계다.**

| | |
|---|---|
| 종착지(재론 금지) | 통합 채널 `H0UNCNT0` **폐기**. KRX 전용 `H0STCNT0` + NXT 전용 `H0NXCNT0` 2채널 (2026-09-07 사용자 결정 + 09-14 재확인) |
| 이 단계가 한 것 | `scanner.tick_tr_id_for(ticker, *, priority)` 도입 + 9파일 25+ 사이트의 등가 비교를 **집합 멤버십**으로 전환(부채 상환) |
| 판정 시점 | **첫 구독 시점 1회.** ⚠️ **cycle294 가 뒤집었다** — 3단계는 전환 창 안에서 살아 있는 구독을 옮긴다. 이 줄은 2단계 기록이다 |
| 판정 규칙 | `no_feed_registry.is_no_feed(t)` ∧ 출처 확인(`raw ? 'cptt_trad_tr_psbl_yn'`) → `H0STCNT0` / 그 밖(미분류·출처 미확인·예외) → 현행 유지 |
| fail-open 방향 | `TICK_TR_ID`(통합) — ⚠️ **2단계 한정 과도기 장치**였다. cycle294 가 폴백을 시각 기반 전용 채널로 교체했다(아래 L1/L2/L3 표) |
| 킬스위치 | `system_config.tick_channel_resolver_mode` ∈ `off`/`observe`(기본)/`enforce_low`/`enforce`. **즉시 반영** = `PUT /api/realtime/tick-channel-mode` |
| 매수 축 | **열지 않았다**(B-1). `risk._tick_buy_eval_blocked_by_channel` 이 종목 축으로 막는다. ⚠️ **cycle294 가 그 술어를 「구독 사실(채널)」에서 「코호트」로 교체했다** — 아래 cycle294 절이 현행이고, 이 줄의 `applied_tick_channel` 서술은 **2단계 당시의 기록**이다(그 접근자는 지금 프로덕션 소비처가 0 이다) |

#### cycle294(2026-09-14) — **3단계 시간축 전환 · 통합 채널 소멸**

2단계의 두 규약(「첫 구독 시점 1회」·「fail-open = 통합」)은 그 문서가 스스로
**2단계 한정**이라 못박은 과도기 장치였다. 3단계가 둘 다 대체한다.

**구간표 — 전환은 하루 1회다.**

```
프리장(N1)              → H0NXCNT0   그 시각 NXT 만 연속 체결을 싣는다
전환 창                 → 주문 0건 · cycle241 시장 침묵 ⇒ 전환 비용 ≈ 0
정규장 + 애프터마켓     → H0STCNT0   연속
🔴 NXT 단독 연속 구간    → H0NXCNT0   **보유(HIGH)만** — 아래 CRITICAL-1
```

09-14 16:39~16:41 라이브 실측(`000815`·`005385` = `nxt_false` / `000660` =
`nxt_true`)에서 셋 다 `H0STCNT0` 로 KRX 애프터마켓 체결을 받았다 ⇒ 그 채널은
**종목 속성과 무관하게** 정규장 개장부터 연속 체결 종료까지를 덮는다.

🔴 **CRITICAL-1(착지 직후 적대 검증) — "KRX 창" 은 KRX 가 연속일 때만 참이다.**
`krx_continuous_end` 는 `max(end)` 라 09-15 기준 20:00 이고, 그 하나로
09:00~20:00 을 한 구간으로 묶으면 표와 어긋난다. 표 실측:

    KRX  REGULAR 09:00~15:20 continuous / CLOSE_AUCTION 15:20~15:30 single_auction
         AFTER_CLOSE_FIXED 15:30~16:00 fixed_price / AFTER_MARKET 16:00~20:00 continuous
    NXT  AFTER_MARKET 15:40~20:00 continuous   ← 🔴 15:40~16:00 은 NXT 뿐

⇒ **15:40~16:00(20분) 은 NXT 에만 연속 체결이 있다.** 그 20분을 KRX 채널로 덮으면
`nxt_true` **보유** 종목의 손절 트리거가 매일 20분씩 사라진다(오늘은 통합 채널이
그 체결을 싣는다 = INV-1 위반). 사용자 결정("전환 1회")의 근거였던 「cycle287 이
애프터 주문을 KRX 로 보내므로 KRX 가격이 정합」은 **16:00~20:00 에만 참**이다 —
`order_engine._route_exchange_by_clock("SOR", side="sell")` 을 실행하면 15:45·15:55
는 `("SOR","krx_unsupported_keep")`, 16:05·19:00 은 `("KRX","krx_by_clock")` 다.
즉 그 20분의 매도는 **NXT 로 나간다** ⇒ 같은 원칙이 그 구간의 평가 가격도 NXT 로
정한다. 시정은 사용자 결정과 충돌하지 않고 그 결정이 다루지 않은 구간에 그 원칙을
적용한 것이다.

범위는 **HIGH 로 한정**한다 — 그 구간에 필요한 것은 손절 커버리지 하나이고, LOW
~130종목을 하루 두 번 왕복시키면 KIS 공지 「비정상 케이스 2: 무한 등록/해제」다.
HIGH 는 실측 ~12종목 + make-before-break 이라 커버리지 공백이 0 이다. 그 구간에도
**속성축이 이긴다**(`nxt_false` 보유는 KRX 유지 — NXT 로 보내면 새 blind 다).
킬스위치 = `system_config.tick_channel_gap_hold_enabled`(기본 `true`).

🔴 **시각 리터럴 0건이 계약이다.** 경계 셋은 전부
`market_state.get_market_table(on_date)` **공개 API** 파생이다 —
`nxt_pre_end`(NXT·PRE_MARKET 의 end) · `krx_regular_open`(KRX·REGULAR 의 start) ·
`krx_continuous_end`(KRX 중 **`match_kind=="continuous"`** 의 end 최댓값).
`MARKET_TABLE` 을 직접 순회하지 않는 이유 = `effective_from`/`effective_to`
해석기(`_is_effective`)가 private 이고, 빠뜨리면 09-13 이전 날짜에서 20:00 이
나와 거짓이 된다. `krx_continuous_end` 를 `phase` 가 아니라 `match_kind` 로 고른
이유 = KRX 가 연속 구간을 또 신설해도 열거가 낡지 않는다.
전환 시각 = `clamp(nxt_pre_end + offset, nxt_pre_end, krx_regular_open)`,
`offset` 기본 300초.

**fail-open 이 층마다 다르다** (2단계의 단일 폴백을 대체한다):

| 층 | 실패 | 폴백 | 근거 |
|---|---|---|---|
| L1 시각축 | 표 조회 실패·행 부재·`now` 이상 | **`H0STCNT0`** | 09-14 실측이 확정한 채널 · 구독 수명의 92% 가 KRX 창 · 셋 중 **모의(VTS) 지원은 그것뿐** |
| L2 속성축 | 분류 미적재·예외·출처 미확인 | **프리 창에서 `H0NXCNT0`** | 비대칭 — 모르는 종목을 KRX 로 보내면 진짜 `nxt_true` 의 프리장 체결을 **새로 잃지만**, NXT 로 보내면 진짜 `nxt_false` 는 그 구간에 시장이 없어 **잃을 것이 0**. KRX 창에는 이 층이 없다 |
| L3 킬스위치 | `mode == "off"` | **`H0UNCNT0`** | 유일한 통합 반환 경로 |

⚠️ L2 의 방향 때문에 cycle293 이 출처 검사로 막던 **W2 도장 오염**(07:59 에 65.4%,
그중 420종목이 실제로는 `nxt_true`)의 **실패 비용이 3단계에서 0** 이 된다 — 오염된
420종목이 정답인 NXT 로 간다. 출처 검사는 없애지 않았다(프리 창에서 `nxt_false` 를
KRX 로 **내리는** 판단에는 여전히 권위가 필요하고, 전환 폭 40% 축소가 거기서 나온다).

**전환 — 창 안에서만, 창 밖은 금지.** 창은 `tick_channel_clock.switch_windows()`
가 표에서 파생한다 — `pre_to_krx`(아침) · `krx_to_nxt_gap`(NXT 단독 구간 진입) ·
`nxt_gap_to_krx`(복귀, 폭은 아침과 같은 `offset_secs`). 🔴 **창 안에서도 종목마다
경계를 다시 본다**(적대 검증 HIGH-3) — 120초 루프는 부팅 시각 기준 고정 위상이라
창 끝 직전에 진입할 수 있고, 종전 구현은 그 뒤 `MAX_PER_CYCLE`/`BUDGET_SECS` 가 찰
때까지 창을 넘겨 계속 옮겼다(개장 직후 LOW break-before-make = 실제 blind). 경과
시각은 벽시계 재조회가 아니라 **`now` + monotonic 경과**다(두 시계가 갈리지 않게).
트리거는 120초
`stale_watcher_core.check_and_resubscribe_stale` **하나뿐**이다(`_scan_loop` 는
`TIME_SCAN_START` 에 생성돼 아침 전환 창에 존재하지 않는다). HIGH(보유·익일청산)는
**make-before-break** — 신 채널 SEND → ACK 확인(`_subscriptions` ∧
`_subscriptions_acked` **두 집합**) → 구 채널 해제. ACK 실패는 신 채널만 즉시
회수하고 구 채널을 유지하며 **전환 예산을 소모하지 않는다**. LOW 는
break-before-make. 🔴 **세션 재추첨 금지** — 다른 세션에 떨어뜨리면
`_ticker_to_session` 이 덮여 구 세션 튜플이 **영구 고아**가 된다.

**전환 창 REST 백스톱에 대한 정직한 답** — 그 창엔 REST 도 새 체결가를 주지 않는다
(NXT 휴장 + KRX 시가 단일가). 백스톱은 REST 호출이 아니라 make-before-break +
창 밖 전환 금지 + `[tick_channel_switch_window_missed]` 미전환 관측으로 구현했고
KIS 호출 증가는 **0** 이다.

**자동 원복** = `krx_regular_open + revert_probe_secs`(기본 180초, =
`stale_diagnostics.SUBSCRIBE_GRACE_SECS` 재사용). 착지 직후 적대 검증이 이 장치의
**세 구멍**을 찾아 전부 닫았다:

* **표본**(CRITICAL-2 A·D / HIGH-2) — 종전 표본은 "그날 아침 전환에 **성공한** HIGH"
  뿐이었다. 그러면 프리 창부터 KRX 였던 `nxt_false` 보유 종목(이 사이클이 겨냥한
  바로 그 코호트)이 영영 표본에 못 들어오고, `nxt_true` 보유가 0인 날이나
  `enforce_low` 단계에서는 표본이 비어 **원복 자체가 존재하지 않았다**. 지금 표본은
  **「지금 KRX 전용 채널에 앉은 HIGH」** 로 전환 이력과 무관하다.
* **교차 확인**(CRITICAL-2 A) — 종전에는 비교 코호트가 전부 침묵이면 `market_wide`
  로 **결론지어** 그날 다시 재지 않았다. 그런데 3단계 `enforce` 의 정상 상태가
  "전 종목 같은 채널" 이라 그 채널이 진짜 죽은 날엔 비교 코호트도 함께 침묵한다 ⇒
  **진짜 고장에서만 발화하지 못하는** 교차 확인이었다. 지금은 ① 비교 코호트 ≥2 가
  fresh → 되돌린다 ② 비교 코호트는 있는데 전부 침묵 → **비결론**, 2×probe 까지
  기다렸다가 그래도 침묵이면 되돌린다(`all_silent_escalated`) ③ 비교 코호트 자체가
  없다 → 같은 시한 뒤 되돌린다(`all_silent_no_cross`).
* **1회성**(CRITICAL-2 C) — 종전에는 판정 **전에** `_revert_probe_done=True` 를 세워
  첫 측정이 비결론이면 그날 다시는 재지 않았다. 지금은 **결론적인 판정**
  (`frames_present` = 건강 / 되돌림)만 래치하고, 비결론은 다음 사이클이 다시 잰다
  (상한 `MAX_REVERT_PROBE_ATTEMPTS=10`).

🔴 **되돌림도 make-before-break 다**(CRITICAL-3). 종전에는 보유 종목에
`make_before_break=False`(선해제 + `bypass_limit=False`)를 09:03 **라이브 구간에**
걸고 반환값도 읽지 않았다 — 41-cap·OPSP 백오프에 걸리면 그 종목이 어느 채널에도
없는 채로 종일 남는다. "되돌림의 전제가 프레임 0" 이라는 근거는 **오발화 시 거짓**
이고, 절대 규칙 2 와도 모순이었다. 되돌린 상태는 `day_reverted` 래치로 그날 종일
**프리 창 규칙**이다(단순 「전원 NXT」면 `nxt_false` 가 새 blind 가 된다). 되돌린 뒤
**그날 재시도는 없다.** 래치는 벽시계 날짜로 스스로 풀리고, 시계를 못 읽는 경로
에서도 날짜 키가 비지 않는다(영구 좌초 차단).

🔴 **매수 축 술어가 「채널」에서 「코호트」로 바뀌었다.** 3단계는 `nxt_true` 까지
전 종목을 전용 채널로 보내므로, cycle293 의 채널 축 술어를 그대로 두면
momentum·VB·LTV·BFB·VCP **5전략의 틱 매수가 통째로 죽는다**(그 5전략은 틱이 유일
매수 경로다). 이제 `scanner._stamp_cohort` 가 **구독 발사 시점에 확신할 때만**
코호트를 심고(하루 단방향 닫힘 래치, 매일 리셋), `risk._tick_buy_eval_blocked_by_channel`
은 `scanner.tick_buy_cohort_blocked(ticker)` 하나만 읽으며 **모드를 보지 않는다**
(`off` 가 매수를 여는 cycle293 함정이 구조적으로 소멸). **스탬프 부재 = 열어 둔다** —
닫힘 오류는 레지스트리 한 번 실패로 전 종목에 동시에 일어나고(상관 실패) 열림
오류는 종목별 독립이라, 최대 위험은 전자다.

🔴 **스탬프는 재시도된다**(적대 검증 CRITICAL-1 부팅 / F-2 매수축). 종전에는 스탬프를
심는 유일한 자리가 `tick_tr_id_for` 였고 LOW 종목은 `already_in_pool` skip 이 그
호출보다 **앞**이라 그날 **07:59 한 번**만 기회를 가졌다. 그런데 07:59 는
`_full_universe_load_krx_primary` 의 도장이 마스터의 65.4% 를 덮은 시각이라, 그때
출처 검사가 실패한 종목은 08:08 에 진실이 복원돼도 **영영 미스탬프**로 남아 09:00
부터 KRX 프레임을 받으면서 매수 게이트가 열린 채였다 = 승인 없는 B-2 부분 발생.
지금은 `scanner.restamp_cohorts(tickers)` 를 5분 `subscribe_filtered_stocks` 와 **120초
`stale_watcher_core`** 둘 다에서 `ensure_fresh` 직후에 부른다(후자가 아침 창을 덮는다
— `_scan_loop` 은 `TIME_SCAN_START` 에야 생긴다). 닫힘 우세 단방향이라 재호출이 매수를
더 열 수 없다.

규모는 `[tick_buy_gate] stamped_no_feed= stamped_feed= unstamped=` 가 남긴다 —
⚠️ **하루 두 행**이다(cap 키가 시각 구간별). **판단은 정규장 창 행으로 한다** — 프리
창 행의 `unstamped` 는 도장 오염을 재는 값이라 크게 나오는 것이 정상이고, 그 값으로
배선을 판정하면 매일 거짓 경보다. 종전에는 하루 1행이 07:59 에만 나와 **항상 같은
값**을 찍었고, 그래서 그 계측기는 아무것도 잡지 못했다(적대 검증 CRITICAL-2 부팅).

출처 조회가 통째로 실패하는 날은 **상관된 열림**이다 — `[no_feed_provenance_unavailable]`
1회/일 **WARNING**(종전 `logger.debug` 라 리포트에 한 글자도 안 떴다).

**`scheduler.py` 무접촉의 잔여** — `scheduler.py` 의 두 줄(익일청산 시가 수신 ·
스윙 매수 직후)이 풀을 우회해 통합 채널로 직접 구독한다. `KisWebSocket.subscribe`
첫 문장의 `_reroute_legacy_unified(tr_id, tr_key)` 가 그것을 흡수한다 — 요청 tr_id 가
**시세 채널이면서 전용이 아닐 때**(= 통합)만 재라우팅하고, 체결통보(`H0STCNI0/9`)·
장운영정보(`H0UNMKO0`)·전용 2채널은 **byte 동일**로 통과한다. `off`/`observe`/**`enforce_low`** 도
통과다 — `enforce_low` 를 통과시키는 것은 적대 검증 HIGH-1 시정이다. 이 함수는
우선순위를 모르므로 S1(HIGH 를 스코프 밖에 두는 단계)에서 재라우팅하면 그 안전
장치가 통째로 무력화되고, 풀의 병행 dict 와 세션 실구독이 갈려 없는 튜플에
UNSUBSCRIBE 를 보내 KIS `OPSP0003` + 영구 고아를 만든다. 같은 이유로
**`WebsocketPool.subscribe` 진입에서도 한 번 적용**해 `_ticker_to_tr_id` 가 항상
세션이 실제로 구독한 채널과 같게 만들었다(재라우팅은 멱등이라 세션 안 호출은 no-op). 관측 = `[tick_channel_legacy_reroute]` 1회/(ticker)/일. ⚠️ 이것은 **증상
차단**이고 근본 시정(그 두 줄을 리졸버 경유로)은 별도 승인 대상이다.

🔴 **`off` 를 눌러도 이미 전용 채널에 올라간 구독은 되돌아가지 않는다.** 장중에
146종목을 대량 전환하는 것이 더 위험하고, 되돌림 대상인 통합은 `nxt_false` 에게
프레임 0 이라 **킬스위치가 손절을 악화시킨다**. `off` 가 막는 것은 새 판정·새 전환·
레거시 재라우팅이다. **완전 복귀는 다음 `_boot`(익일 07:45)** 다 — 장중 즉시 복귀는
재시작이 필요하고 D6 가 막는다.

**운영 다이얼** (전부 `system_config` 축 — 전략 `DEFAULT_PARAMS`·`param_catalog`
편입 금지):

| 키 | 기본 | 뜻 |
|---|---|---|
| `tick_channel_resolver_mode` | `observe` | `off`/`observe`/`enforce_low`/`enforce` |
| `tick_channel_switch_enabled` | `true` | **전환만** 끈다. 종목이 첫 구독 채널에 머문다 — `nxt_true` 는 NXT 종일이고 NXT 는 정규장·애프터에 체결을 실으므로 **blind 가 아니다**. 자동 원복의 수동 대응물 |
| `tick_channel_switch_offset_secs` | 300 | `nxt_pre_end` 에서 전환까지 |
| `tick_channel_switch_ack_timeout_secs` | — | HIGH make-before-break ACK 대기 |
| `tick_channel_revert_probe_secs` | 180 | 개장 후 원복 판정 시점 |
| `tick_channel_gap_hold_enabled` | `true` | 🔴 **NXT 단독 연속 구간**(09-15 = 15:40~16:00)에 보유(HIGH)가 NXT 를 따라가는가. `false` 면 그 20분의 손절 트리거가 사라지므로 **되돌릴 때만** |

즉시 반영(재시작 불요):

```bash
curl -X PUT .../api/realtime/tick-channel-mode -d '{"mode":"enforce"}'
curl -X PUT .../api/realtime/tick-channel-mode \
     -d '{"mode":"enforce","switch_enabled":false}'   # 채널은 유지, 전환만 정지
curl -X PUT .../api/realtime/tick-channel-mode \
     -d '{"mode":"enforce","gap_hold_enabled":false}' # 15:40~16:00 NXT 추종 해제
curl -X PUT .../api/realtime/tick-channel-mode -d '{"mode":"off"}'   # 배포 전과 동일
```

⚠️ **배포만으로는 아무 일도 일어나지 않는다** — `DEFAULT_MODE` 는 `observe` 이고
`system_config` 에 그 키를 넣는 마이그레이션도 초기화 코드도 없다. 3단계를 실제로
켜려면 **07:45 부팅 전에** `tick_channel_resolver_mode='enforce'` 가 DB 에 있어야
한다(부팅 뒤 올려도 코호트 스탬프는 재시도로 따라잡지만, 07:59 사전 구독이 이미
통합으로 나가 그날 「통합 구독 0」이 성립하지 않는다).

「채널이 문제」(`mode`)와 「전환이 문제」(`switch_enabled`)는 **다른 결정**이라 모드
enum 에 태우지 않았다 — 사고 중에 쓸 카드가 `off` 하나뿐이면 운영자가 장중 대량
전환을 실행하게 된다. `switch_enabled`·`gap_hold_enabled` 는 **선택 필드**라 생략하면 현행 값 무접촉이다.
`GET /api/realtime/tick-channel-mode` 는 그날 `nxt_gap_window` 와 `switch_windows`
(창 3개)를 함께 돌려준다 — 운영자가 화면 없이 "오늘 전환이 몇 시로 잡혔는가" 를
확인하는 유일한 채널이다.

🔴 **마커 의미 전환 — 배포 전후 grep 합산 금지**: `[tick_channel_config]` 는
`clock_krx=`/`clock_nxt=`/`cohort_no_feed=` 3라벨이 붙었고 `resolved_unified=` 는
**0 이 정상**이다 · `[tick_coverage] stale` 은 분모 불변 + `fresh` 증가가 성공 서명 ·
`[no_feed_held]` 와 `[stale_watcher_summary] no_feed_skipped=` 는 **0 에 수렴**해야
한다 · `[tick_channel_dual_detected]` 0 이 정상.

`TICK_TR_ID_KRX`/`TICK_TR_ID_NXT` 두 상수는 리졸버의 반환값 자리로 `scanner.py` 에
있고, 세 값을 담은 **단일 정본 집합**이 `scanner.TICK_TR_IDS` 다(두 번째 집합을
만들면 두 판정이 갈리고, 갈린 순간 "구독은 A 해제는 B" 가 된다 — AST 가드가 컬렉션
리터럴 개수를 1 로 잠근다).

`on_tick` 중복 호출 안전: `scanner.ticker_prices[ticker]` 마지막 값 채택 + `_selling`/`is_ticker_blocked_for_buy` 중복 매수 차단.

## handler.py — 메시지 처리

- 파이프(`|`) 구분 메시지 파싱
- **실시간 체결가** (H0STCNT0/H0NXCNT0/H0UNCNT0): 현재가/시가/등락률 추출 → `RiskManager.on_tick` 콜백 (세 TR_ID 동일 포맷 → 단일 파서). ⚠️ **구 서술("현행 구독은 H0UNCNT0 단일 — 나머지 둘은 예약 상수")은 거짓이다** — cycle293 이 무송출 종목을 `H0STCNT0` 로 보내기 시작했고 cycle294 는 정상 경로에서 통합을 **아예 반환하지 않는다**(프리장 `H0NXCNT0` / 정규장·애프터 `H0STCNT0`). `handler` 는 여전히 tr_id 를 `on_tick` 으로 넘기지 않으므로(P1-7 N-4, `handler.py` 는 미승인 8영역) `tick_volume` 의 채널 구분은 **이중 채널 금지 + 전환 창 프레임 0** 으로만 닫힌다
- **체결통보** (H0STCNI0/H0STCNI9): AES-256-CBC 복호화 → **계좌번호 필터** → `OrderEngine.handle_execution_notice` 콜백
- **NXT 장운영정보** (H0NXMKO0): 보드 전환 이벤트 → `register_board_handler` 등록 콜백(SessionTracker) 전달. KIS 명세 필드 미기재 → 운영 데이터 기반 확정
- 체결통보 필드 매핑 (`^` 구분, **cycle235 정본 정정** — KIS `ccnl_notice` 26컬럼): [0]CUST_ID(HTS ID), **[1]계좌번호(8)+상품코드(2)**, [2]주문번호, [3]원주문번호, [4]매도매수구분(02:매수/01:매도), [5]정정구분, [6]주문종류, [7]주문조건, **[8]종목코드**, **[9]CNTG_QTY 체결수량(통보 건별 증분)**, [10]CNTG_UNPR 체결단가, [11]체결시간, [12]거부여부, [13]CNTG_YN 체결구분(1:접수,2:체결), [14]ACPT_YN, [15]BRNC_NO, **[16]ODER_QTY 주문수량**, [17]고객명, [18]ORD_COND_PRC. ⚠️ 종전 표기([9]주문수량/[16]체결수량)는 정본과 **반대**였고 코드가 이를 따라 fields[16] 을 수량으로 오독 — 단일 전량 체결(두 값 동일)에선 잠복, 부분/분할 체결에서 positions 과대(08-28 257720 실사고: 실체결 2주가 3주 등록 → 익일 매도 전량 APBK0400). cycle235 가 fields[9] 로 시정 + AST 봉인(`test_cycle235_ast_execution_qty.py`) + 엔진 overrun 클램프(`[fill_qty_overrun]`) 이중 방어
- **계좌 필터**: `fields[1]` 이 `settings.kis_account_no` 로 시작하지 않으면 무시 (실전 H0STCNI0 은 동일 HTS ID 묶인 타 계좌 통보 함께 푸시)

### cycle264 (2026-09-06~07) — `[open_scope_observe]` 시가 스코프 shadow 관측 (**행위 변경 0**)

> 이 절은 **관측**의 계약이다. **시정이 아니다.** `_parse_tick_prices` 는 여전히 `[7] STCK_OPRC`
> 에 스코프 필터가 **없고**, 그것을 고치는 것은 **cycle265**(후속 F-2)다 — 아래 "아직 열려 있는 것".

#### 무엇을 재는가

통합 채널 `H0UNCNT0` 의 **일-스코프 필드는 09:00 에 리셋되지 않는다**. cycle222-a2 가 `[8] STCK_HGPR`
에서 실측하고 `[27] HGPR_HOUR` 로 KRX 정규장 창 필터를 붙였다(`_parse_day_high`). 같은 성질이
`[7] STCK_OPRC` 에도 적용되면, MAIN 구간 틱이 실어 오는 "시가" 가 **08:00~09:00 NXT 프리장 기준가**
이고 그 값이 `RiskManager.on_tick(open_price=…)` → `scanner.ticker_prices[t]["open_price"]` →
VB/LTV 의 보드 시가 → `target = open + offset` 으로 흘러간다(포렌식
`_workspace/analysis/entry_price_0900_20260906/`). 이 사이클은 그 가설의 **판별자를 하루치 재기만** 한다.

```
[open_scope_observe] ticker=%s oprc_hour=%s tick_open=%d cntg_hour=%s hgpr_hour=%s
                     mkop=%s hour_cls=%s in_main_window=%s
```

- 위치 = `_handle_tick` 안, `parsed` 성공 **뒤**. INFO, **1회/ticker/일**
  (`src/engine/daily_emit_cap.py::KstDailyEmitCap`, cycle258 표준 재사용).
- `oprc_hour` = `[24] OPRC_HOUR`, `hgpr_hour` = `[27]`, `mkop` = `[34] NEW_MKOP_CLS_CODE`,
  `hour_cls` = `[43] HOUR_CLS_CODE`. `[24]/[27]/[30]` 은 완전한 3-형제(시가/고가/저가가 찍힌 시각,
  HHMMSS 6자리)라 `_parse_day_high` 의 창 판정을 그대로 쓸 수 있다.
- `tick_open` = `_parse_tick_prices` 가 이미 만든 `[7]` 파싱값을 **그대로** 받는다.
- 리셋 훅 = `reset_open_scope_observe()`(`reset_day_high_scope_skip` 대칭).

#### 계약 (어기면 관측이 무의미해지거나 매매가 위험해진다)

1. **`_parse_tick_prices` 는 byte 동일이다.** 소스 세그먼트 sha 로 핀했다. 마커는 그 함수 **밖**에 둔다.
2. **게이트와 라벨은 다른 축이다.**
   - *게이트* = `[1] STCK_CNTG_HOUR`(틱 자신의 체결 시각)가 MAIN 창(`090000~153000`) 안일 때만
     cap 을 태운다(`_maybe_log_day_high_scope_skip` 과 동일 설계). **프리장 틱이 1회 cap 을 먹으면
     그 종목이 코호트 분모에서 사라진다.** `[1]` 파싱 실패도 cap 미소모(근거 없이 태우지 않는다).
   - *라벨* `in_main_window` = `[24]` 가 MAIN 창 안인가. **창 안/밖을 모두 남긴다** — 분모가 있어야
     오염 **비율**이 나온다. `[day_high_scope_skip]` 은 skip 만 남겨 분모가 없었고, 그래서 지금
     "93/287" 이 **추정**에 머문다.
3. **원문 보존 — 정규화 금지.** `[24]`·`[27]`·`[34]`·`[43]` 은 0 치환·zero-pad·trim 없이 그대로
   남긴다. 부재/접근 실패는 `"?"`, 빈 문자열 수신은 `""` — **둘은 서로 다른 사실**이다.
   ⚠️ **`[24]` 는 이 마커가 배포되기 전까지 이 프로젝트에서 한 번도 관측된 적이 없다**
   (`grep fields[24]` 전 소스 0건, KIS 로컬 캐시·MCP 정본 모두 컬럼 *이름*만 제공). "프리장 체결이
   없던 종목에 무엇을 주는가" 는 **추론**이며, 정규화는 바로 그 미지를 지운다.
4. **never-raise + 흡수기의 2차 예외까지 흡수.** 헬퍼 자체가 흡수하고, 호출부에서 **한 겹 더** 감싼다.
   이 경로에서 예외가 새면 `_on_tick` 콜백과 같은 자리로 전파돼 **틱마다 WebSocket 재연결**이
   일어난다(사이클 88 G-REJECT-1 의 `raise` 규약) = 손절 사각. 자기 실패 흔적은
   `src/engine/observer_trace.py::trace_observer_failure`(무흔적 `pass` 금지, cycle258 카드 #5).
5. **hot path 순수성** — `logger` 만 쓴다. `write_log`/DB/`await` 금지(AST A-1 동형).
   순서는 **창 게이트 → cap peek(비소모) → 필드 읽기 → emit**(cap 소진 시 인자 구성이 버려질 작업이다).
6. **볼륨 = 종목당 1행/일.** 종목당 다중 로그 금지. ⚠️ 자문의 "~290행/일" 은 구독 슬롯 **용량** 기반
   **추정**이고 운영 실측 `[tick_coverage] subscribed=` 는 09-03/09-04 기준 **107~148** 이다. 반대로
   `_scan_loop` 5분 delta 가 구독을 회전시키므로 하루 동안 관측된 서로 다른 ticker 수는 슬롯 수보다
   클 수도 있다 ⇒ D+1 에 **실제 행 수를 세고**(그 수가 오염 비율의 분모다) ~300행을 크게 넘으면 재평가.
   이 수를 다음 사이클이 "실측" 으로 인용하지 않는다.

#### 🔴 아직 열려 있는 것 — `[7]` 에는 여전히 스코프 필터가 없다 (cycle265 / 후속 F-2)

`_parse_tick_prices` 는 지금도 `int(fields[2]), int(fields[7])` 을 **필터 없이** 반환한다.
`[8] 고가` 는 스코프를 재고 `[7] 시가` 는 재지 않는 **비대칭이 그대로 남아 있다.**

- **시정 방향(자문 §0 권고)** = 소스에서 `[7]` 을 0 으로 강등하는 fail-closed 는 **쓰면 안 된다**.
  `[7]` 은 VB 목표가 말고도 08:00 익일청산 갭 판정 · LTV 프리장 보드 목표가 · kojiro 갭스킵/시가아래
  가드 · momentum 익일청산 갭률까지 **여섯 소비처**가 공유하고, 0 을 받으면 *가드가 조용히 꺼지거나*
  (kojiro) *강제 청산으로 뒤집히거나*(momentum) *프리장 매매가 통째로 죽는다*(LTV·익일청산).
  권고는 **`[7]` 을 그대로 두고 `board="main"` 목표가의 기준가만 KRX REST(`stck_oprc`, `J`)로
  갈아 끼우는** 방향이다.
- **선결 = 이 사이클의 3자 대조 판독**(`[open_scope_observe]` `[24]` 분포 + `[open_source_compare]`
  + `stock_master_daily` KRX 시가). 시정은 VB 진입이 추정 **−27.6%** 줄어드는 **매매 행위 변경**이라
  `src/realtime/**` = 8영역 승인 + `domain-consult` 선행이 필요하다.
- ⚠️ 자문이 조사 정본의 전제 하나를 뒤집었다 — `[breakout_open_confirm] confirmed=0` 은 **표시
  버그**였고(`get_targets_status()` 의 `active ∩ tradable_boards` 마스킹) 실제로는 09:00:05 REST
  경로가 VB **51/65**(09-03)·**46/55**(09-04)를 확정하고 있었다. **REST 폴백은 고장이 아니다 —
  오염된 WS 캐시가 먼저 이겨 차례가 오지 않을 뿐**이다. 즉 cycle265 는 새 배관을 까는 일이 아니라
  **우선순위를 뒤집는 일**이다.

### 사이클 102 (2026-06-11) — 시세 구독 영역 전면 재검토 (3 영역 통합 가시화)

사용자 신규 요구 "재구독 로직 자체가 실수가 아닌가 싶어. 시세구독 관련 부분을 전면 새로운 시각에서 재검토" + refactor-expert + domain-expert 병렬 자문 일치 결론 (사이클 88 G-REJECT 영구 영속 + 가시화 강화 + 임계 상향). 사용자 결정 Q72=F+가시화 (`last_ws_message_at` + dispatch + callback 3 영역 통합).

#### (a) `KisWebSocket._last_ws_message_at` 세션별 마지막 메시지 수신 시각

- **위치**: `KisWebSocket.__init__` (`websocket.py:162~165`) + `_handle_raw` (`websocket.py:607~609`)
- **타입**: `dict[str, datetime]` (세션 label → KST 시각)
- **갱신 시점**: `_handle_raw` 진입 시 즉시 `self._last_ws_message_at[self._label] = datetime.now(_KST_TZ)` (모든 메시지 — 시세/체결통보/PINGPONG/장운영정보)
- **책임 분리 영속** (사이클 88 G-REJECT-2 영구 영속): 종목별 `ticker_last_tick` (사이클 88 영속) ↔ 세션별 `_last_ws_message_at` (사이클 102 신규) — 별도 dict 분리, 통합 X
- **패턴 답습**: 사이클 16 `_aes_iv` 인스턴스 변수 패턴 (`__init__` + `_handle_raw` 양쪽 영역 분리) + 사이클 68 KST timezone 일관성 영속
- **운영 효과**: 메인 vs 보조 세션별 메시지 수신 빈도 비교 + KIS PINGPONG 미수신 정책 보조 세션 영역 정합 확인 + 추후 진단 영역 확장 가능 (5분 주기 emit 후속 카드 가능)

#### (b) `handler._silent_drop_count` + `flush_silent_drop_count()` dispatch silent drop 가시화

- **위치**: `handler.py:56~59` (모듈 전역) + `handler.py:101~113` (`_handle_tick` 2 분기) + `handler.py:223~238` (신규 함수)
- **타입**: `dict[str, int]` (ticker → 누적 drop 카운트)
- **누적 시점 2 영역** (graceful silent drop, 사이클 88 G-REJECT-2 종목별 영속 답습):
  - `_handle_tick` `len(fields) < 10` 분기 (L101~L105) — payload 영역 비정상 (`fields[0]` 없으면 `"_unknown"` 영역 영속)
  - `_handle_tick` `parsed is None` 분기 (L109~L113) — `_parse_tick_prices` 파싱 실패 (현재가/시가 int 변환 실패)
- **flush 함수**: `flush_silent_drop_count()` (L223~L238) — `[dispatch_drop_summary] window=300s drops_total=N by_ticker={...}` 1행 INFO emit + `_silent_drop_count.clear()`. empty collector 진입 시 emit 0 (Q2 빈 윈도우 skip 영속, 사이클 74 답습).
- **호출 사이트**: `scheduler.py::_api_recovered_collector_loop` (L2567~L2571) 5분 주기 + try/except graceful (사이클 78 G-AST1 영역 답습 — `flush_swing_rest_poll_collector` + `flush_stale_watcher_collector` 와 함께 호출).
- **운영 효과**: 미래 silent drop silent 결함 영구 차단 (KIS 응답 포맷 변경 / 종목코드 6자리 영문 우선 등 silent 분기 즉시 가시화).

#### (c) 3 콜백 일관 `try/except` + `[callback_exception]` + `raise` 영속 (사이클 88 G-REJECT-1 영구 영속)

- **위치 3 영역** (`handler.py` 동일 패턴):
  - `_handle_tick` (L121~L128) `await _on_tick(ticker, current_price, open_price, change_rate)` 외부
  - `_handle_execution` (L178~L186) `await _on_execution(ticker, order_no, side, price, quantity)` 외부
  - `_handle_market_op` (L212~L220) `await _on_board(tr_key, mkop_cls_code, payload)` 외부
- **패턴**: `try/except Exception: logger.exception("[callback_exception] handler=... ticker=... order_no=... tr_id=... tr_key=..."); raise` (1줄 컨텍스트 + ERROR + **`raise` 영속**)
- **`raise` 영속 의무 영구 영속 (사이클 88 G-REJECT-1 영구 영속, 외부 LLM 단순 `swallow` graceful 추천 영구 거부)**: callback 예외 → re-raise → KisWebSocket `_receive_loop` 외부로 전파 → WebSocket 재연결 자연 발화 영속. 단순 swallow 시 = 사이클 29 005935 LMS chain 사고 재현 위험 (callback 침묵 + 재연결 trigger 영역 영구 폐기 + KIS LMS / 앱키 정지 chain).
- **운영 효과**: 모든 callback 예외 가시화 (silent crash 영구 차단) + 재연결 trigger 영역 영구 보존.

#### 영속 의무 매트릭스 (사이클 102 영구 확인 영역)

- **사이클 88 G-REJECT-1 영구 영속**: 콜백 예외 단순 graceful (swallow) 영구 거부 → `raise` 의무 영속 (재연결 trigger 영역 영구 보존)
- **사이클 88 G-REJECT-2 영구 영속**: 종목별 `ticker_last_tick` ↔ 세션별 `_last_ws_message_at` 책임 분리 영속 (통합 X)
- **사이클 88 G-REJECT-3 영구 영속**: 4 dict 분리 (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`) + `_last_ws_message_at` 신규 추가 — 통합 X
- **사이클 17 OPSP0002 backoff 300s 영속**: `_opsp_backoff_until` dict 등록 행위 무변경
- **WebSocket 4중 안전망 영속**: F1 + `_scan_loop` + K stale watcher + `_resubscribe_stale_priority`
- **AST 영구 가드 5 + 회귀 가드 17 케이스**: G-78-VERIFY-1~5 (영역 1 영구 확인) + G-WS-MSG1/2 + G-DISPATCH1~3 + G-CALLBACK1/2 + G-THRESHOLD1/2/3 + G-LMS1 + G-PERSIST1

## WebSocket 메시지 포맷

```
수신: 0|H0STCNT0|001|005930^...^현재가^...
        │  │       │    └ 데이터 (캐럿 구분)
        │  │       └ 건수
        │  └ TR_ID
        └ 암호화 여부 (0: 평문, 1: 암호화)
```

## 구독 종류

| TR_ID | 용도 | 구독 키 | 비고 |
|-------|------|---------|------|
| H0UNCNT0 | 실시간 체결가 (KRX+NXT 통합) | 종목코드 | `scanner.TICK_TR_ID`. 🔴 **cycle294(2026-09-14)부터 정상 경로에서 반환하지 않는다** — 유일한 반환 자리는 킬스위치 `mode == "off"` 분기다. 🔴 **`stock_master.nxt_tradable=False`(KRX 단독) 종목의 체결 프레임을 보내지 않는다** — SUBSCRIBE 는 SUCCESS ACK 를 받으므로 구독은 살아 있는 것처럼 보이고 프레임만 영구 0 이다(포렌식 `_workspace/forensics/stale_candidates_0904.md`: 나흘 × ~200종목 예외 0, 유동주 포함, 최소 2026-07-24 부터 만성. 마스터 전체 **83.2%** 가 KRX 단독). **종착지는 폐기**(2026-09-07 사용자 결정) |
| H0STCNT0 | 실시간 체결가 (KRX 단독) | 종목코드 | H0UNCNT0 동일 포맷(47필드 인덱스 전부 동일). **cycle293 부터 실 구독**(무송출 종목) → **cycle294 부터 정규장+애프터마켓 전 종목**. 09-14 16:39~16:41 라이브 실측 — `000815`·`005385`(`nxt_false`)와 `000660`(**`nxt_true`**) 셋 다 구독 1~5초 뒤 첫 틱을 받았다 = **종목 속성과 무관하게** KRX 애프터마켓 체결을 싣는다. 판정 실패(L1)의 폴백도 이 채널이다. cycle253 프로브 실측으로 진짜 KRX 개장가 수신 확인. **모의(VTS) 지원 — 셋 중 유일** |
| H0NXCNT0 | 실시간 체결가 (NXT 단독) | 종목코드 | 동일 포맷. **cycle294 부터 실 구독** — 프리장 전 종목 + NXT 단독 연속 구간(09-15 = 15:40~16:00)의 **보유(HIGH)만**. 09-14 19:52~19:55 `000660` 지속 수신으로 라이브 확인(애프터 구간 대리 증거 — 프리장 08:00~08:50 프레임은 아직 실증 전이다). **모의(VTS) 미지원** |
| H0UNMKO0 | 통합 장운영정보 (KRX+NXT) | 종목코드 | 현재 사용 — MKOP_CLS_CODE 시장 전체 공통이라 대표 종목 1개(005930)만 구독. **모의(VTS) 미지원 — 실전 한정** |
| H0STMKO0 | KRX 단독 장운영정보 | 종목코드 | H0UNMKO0 동일 |
| H0NXMKO0 | NXT 단독 장운영정보 | 종목코드 | H0UNMKO0 동일. 통합 구독으로 충분 |
| H0STCNI0 | 체결통보 (실전) | HTS ID | KRX/NXT/SOR 모두 같은 TR, ODER_KIND 필드로 거래소 식별 |
| H0STCNI9 | 체결통보 (모의) | 계좌번호 | KRX 한정 (VTS NXT/SOR 미지원) |

## 운영 점진 활성화 (보조 세션)

1. **코드 배포 단계**: 풀 코드 + 보조 0개 (DB 미등록) → 메인 only 동작 (회귀 0)
2. **첫 보조 등록**: DB 1개 → 1 보조 활성 → 41+41 = 82 슬롯
3. **점진 추가**: DB 2~5 등록 → 풀 점진 확장
4. `scheduler._boot()` 재시작 시점에 보조 세션 연결

## 안전 규칙 (멀티 세션)

- **E1 (보유·익일청산 우선)** — `subscribe(priority="HIGH")` 메인 `bypass_limit=True` 절대 보장
- **E2 (거절 응답 감지)** — 각 세션 `_handle_raw()` 독립 작동
- **F1 (재연결 후 자동 검증)** — 각 세션 `_verify_subscriptions_after_reconnect()` 독립 발화
- **K (stale watcher)** — 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority='HIGH', bypass_limit=True)` **강제 재등록**(KIS 정상 "신규 등록" 패턴). 재SEND(`resend_subscribe_for_ticker`) 분기는 사이클 17 에서 폐기됐다 — `retry > MAX_STALE_RETRIES(=5)` 면 시간 기반 force_retry 로 넘어간다(`stale_watcher_core.py`)
- **세션 단위 silent inactive 자동 회복 (사이클 24, 2026-05-20)**: 메인/보조 세션의 fresh=0 + subscribed>=5 + 5분 지속 시 K stale watcher 가 `_ws.close()` 강제 발화 → connect() 의 ConnectionClosed catch → 재연결 자동 발화. 시간당 2회 cap.

## 주의사항

- **체결통보 구독은 매매의 핵심 전제조건** — 미구독 시 포지션 등록 불가 → 손절 불가
- 체결통보는 실전에서 암호화 — 반드시 `decrypt_aes_cbc` 필요
- scheduler 가 WebSocket 연결 직후 체결통보 자동 구독
- 구독 종목 변경 시 기존 해제 → 새 등록 순서
- WebSocket URL 은 REST 와 다름 (`ops.koreainvestment.com`)
- **실전 체결통보 (H0STCNI0)** 는 HTS ID 단위 푸시 — 동일 HTS ID 묶인 타 계좌 통보 함께 들어옴. handler `fields[1]` 계좌 필터링 필수

## §외부 LLM 검토 영구 기록 (사이클 88, 2026-06-09)

타 LLM 제출 "시세 수신 오류 + 구조 단순화" 의견서 검토 완료. 양 agent (refactor-expert + domain-expert) 일치 결론 = *구조 관찰 객관, 영속 시정 18 사이클 도메인 지식 부재*.

### 영속 보장 매트릭스 (단순 통합 추천 영구 거부)

- WebSocket 4중 안전망 시간 척도 (F1 + `_scan_loop` + K stale watcher + `_resubscribe_stale_priority`)
- 종목 + 세션 2 계층 stale 하이브리드 (사이클 29 R1 + R2)
- 4 dict 분리 (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`)
- HIGH `bypass_limit=True` + 보유/익일청산 절대 보호 (사이클 32 R4)
- 사이클 38 명문화 (`tradable_boards` 매수 진입 전용)

### 영구 차단 영역 3 (AST 가드)

`tests/unit/ast/test_external_llm_reject_patterns.py` 영구 차단:

1. **G-REJECT-1**: 단일 restore 도입 차단 (4중 안전망 영속) — 외부 추천 R4 반려. 4중 안전망 함수 4종 (`_verify_subscriptions_after_reconnect` / `_scan_loop` / `check_and_resubscribe_stale` / `resubscribe_stale_priority`) 영속 검증
2. **G-REJECT-2**: stale 전체 WS 단독 판정 차단 (사이클 29 005935 재현 방지) — 외부 추천 R5 반려. `ticker_last_tick` + `STALE_FRESHNESS_SECS` 종목 단위 영속 검증
3. **G-REJECT-3**: SubscriptionRegistry 단일 dict 통합 차단 (orphan ACK race / 41 한도 분산 영속) — 외부 추천 R2 반려. 4 dict 분리 (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`) 전수 영속 검증

### 채택 가능 후속 카드

| 카드 | 등급 | 내용 |
|-----|------|------|
| **#E1** | MEDIUM | `subscription_registry.py` read-only view 모듈 신설 (~80L) — 사이클 89+ |
| **#E2** | LOW | 4 계층 명명 매핑 docstring 보강 (코드 변경 0) |
| **#E3** | LOW | 운영 실증 측정 (사이클 74 `[stale_watcher_summary]` 인프라 재사용) |

### 참조

- `_workspace/external_llm_reviews/2026-06-09_realtime_review.md` (통합 영구 기록)
- 사이클 96 재평가 (2026-06-13 이후, 1주 운영 실증 후)
