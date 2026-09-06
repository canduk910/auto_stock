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

- `get_subscribed_tickers() -> set[str]` — TICK(H0STCNT0/H0NXCNT0/H0UNCNT0) 구독 합집합. 체결통보·장운영정보 제외. 현행 구독은 `H0UNCNT0`(통합) 단일 — H0STCNT0/H0NXCNT0 는 P1-7 B 리졸버 착지 전까지 예약 상수
- `get_acked_tickers() -> set[str]` — TICK 필터 ACK set. KIS REST/WS 슬롯 사용현황 조회 API 미존재 → 우리 측 ACK 추적이 "SEND 후 무응답" 가시화의 유일한 길

### 시세 채널 시간대별 전환 — 미배선·cycle257 삭제, 속성 기반 리졸버는 P1-7 B

사이클 26(2026-05-20, 커밋 f7f0766)이 도입한 시각 기반 채널 전환(활성 TR_ID 판정 함수 +
종목 단위 원자 전환 루프)은 **108일간 `src/` 호출자가 0**이었다 — 정의만 있고 어디서도
호출되지 않아 실제 구독은 처음부터 `TICK_TR_ID = H0UNCNT0`(통합) 단일 채널로만 동작했다.
cycle257(2026-09-05)이 이를 삭제(`scanner.py`/`scheduler.py`)했다. 채널을 시간대·종목
속성 기반으로 다시 분리할 필요가 생기면 이 문단이 아니라 **P1-7 B(속성 기반
`tick_tr_id_for(ticker)` 리졸버)** 로 간다 — `TICK_TR_ID_KRX`/`TICK_TR_ID_NXT` 두 상수는
그 리졸버의 반환값 자리로 `scanner.py` 에 보존돼 있다.

`on_tick` 중복 호출 안전: `scanner.ticker_prices[ticker]` 마지막 값 채택 + `_selling`/`is_ticker_blocked_for_buy` 중복 매수 차단.

## handler.py — 메시지 처리

- 파이프(`|`) 구분 메시지 파싱
- **실시간 체결가** (H0STCNT0/H0NXCNT0/H0UNCNT0): 현재가/시가/등락률 추출 → `RiskManager.on_tick` 콜백 (세 TR_ID 동일 포맷 → 단일 파서). 현행 구독은 H0UNCNT0(통합) 단일 — H0STCNT0/H0NXCNT0 는 P1-7 B 리졸버 예약 상수(cycle257)
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
| H0UNCNT0 | 실시간 체결가 (KRX+NXT 통합) | 종목코드 | 현재 사용 — `scanner.TICK_TR_ID`. NXT 거래 즉시 반영 |
| H0STCNT0 | 실시간 체결가 (KRX 단독) | 종목코드 | H0UNCNT0 동일 포맷. 호환성 유지 |
| H0NXCNT0 | 실시간 체결가 (NXT 단독) | 종목코드 | 동일 포맷 |
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
