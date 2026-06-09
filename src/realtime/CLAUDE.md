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
- `resend_subscribe_for_ticker(tr_id, tr_key)` — K stale watcher 헬퍼. 추적 없으면 메인 fallback
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
- **사이클 43 (2026-05-22) — 세션 라벨 통일**: 보조 세션 라벨 `quote-1/quote-2/quote-3` 1-based index → DB `kis_quote_accounts.label` (ISA/sub/gold 등 사용자 등록 라벨) 직접 사용. `_session_label(ws)` / `get_session_status()` / `disable_quote_session(label)` / `[tick_coverage_session]` / `[stale_watcher_detail]` / `[priority_drop_pool]` / `[silent_inactive_force_reconnect]` / 사이클 42 `[ws_heartbeat]` / UI `KisAccountPoolCard` 모두 동일 라벨. 메인 라벨 `"main"` 절대 보존. `_quotes[idx]` 인덱스 자체는 변경 0
- 보조 0개 → `sessions` 길이 1 (main only, 기존 호환)

## websocket.py — KisWebSocket 연결 관리

- WebSocket 접속키 발급 (`/oauth2/Approval`)
- 종목 시세 구독/해제 (**최대 41건, KIS 공식 한도**)
- 체결통보 구독 (실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호)
- Heartbeat 감시 (30s 미수신 → 재연결)
- 자동 재연결 (최대 5회, 지수 백오프)
- 연결 시 AES iv/key 수신 + 저장
- 구독 한도 초과 시 에러 대신 경고 + skip
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
- **사이클 16 (2026-05-19) AES 키 격리 가드**: `KisWebSocket.__init__(*, is_main: bool = True)` 신규 인자 + `_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0", "H0STCNI9"})` 모듈 상수 + `_handle_raw` SUBSCRIBE SUCCESS 분기에 이중 가드: (1) `self.is_main=True` + (2) `tr_id in _EXECUTION_NOTICE_TR_IDS` 모두 만족 시에만 `set_aes_keys(iv, key)` 호출. 그 외 시세 SUBSCRIBE SUCCESS / 보조 세션 SUBSCRIBE SUCCESS 는 모듈 전역 키 저장 skip + DEBUG `[aes_key_skip] tr_id=... is_main=...` 로그. `WebsocketPool.start()` 가 보조 세션 생성 시 `KisWebSocket(token_manager=manager, is_main=False)` 명시. 사이클 7-C 풀 통합 (메인+보조 N 세션) 도입 시점부터 잠재 결함 — 보조 세션 ISA 의 시세 SUBSCRIBE SUCCESS 의 AES 키가 모듈 전역 `_aes_iv`/`_aes_key` 덮어씌워 메인 체결통보 (H0STCNI0/H0STCNI9) 복호화 실패하던 race 차단. 2026-05-19 11:20:23~11:22:31 운영 사고 11건 대응. 회귀 가드: `tests/unit/realtime/test_aes_keys_main_only.py` 6 케이스(is_main default True / is_main False 명시 / 메인+체결통보 저장 / 메인+시세 skip / 보조+시세 skip / 보조+체결통보 이중 안전망 skip). 자체 인스턴스 변수 `self.aes_iv`/`self.aes_key` 는 디버깅용 보존
- **사이클 17 (2026-05-19) OPSP0002 backoff 가드**: `KisWebSocket.__init__` 에 `_opsp_backoff_until: dict[tuple[str, str], float] = {}` 인스턴스 변수 신규. `_handle_raw` 의 `OPSP0002 ALREADY IN SUBSCRIBE` 분기에서 `self._opsp_backoff_until[(tr_id, tr_key)] = time.time() + 300.0` 기록 + INFO `[ws_opsp_backoff until=+300s]`. `subscribe(tr_id, tr_key, *, bypass_limit=False)` 진입 시 `time.time() < self._opsp_backoff_until.get(key, 0)` 면 send skip + DEBUG `[ws_subscribe_backoff] remain=...s` (한도 검사 *전*). `_subscriptions` 도 add 안 함 → 다음 자연 재시도 시 일관 동작. `bypass_limit=True` (HIGH 보유/익일청산) 는 검사 skip — 손절 우선 보장. **사이클 17 보강 (2026-05-19) — 60s → 300s 연장**: KIS 공식 답변 ("기등록한 사항을 재등록하지 않도록") 반영. `_scan_loop` 5분 주기 ≥ backoff 만료 보장 → 같은 사이클 내 재시도 차단. 2026-05-19 15:15 KST `tick_coverage ratio=0.0%` 운영 사고 (OPSP0002 후 즉시 재구독 → 또 OPSP0002 → 무한 루프 + KIS WS Rate Limit 위양성 폭증) 대응. 회귀 가드: `tests/unit/realtime/test_ws_subscribe_backoff.py` 5 케이스 (OPSP0002 후 backoff 300s 등록 / 유효 시간 내 send skip / 만료 후 정상 send / 다른 종목 격리 / 정상 SUBSCRIBE SUCCESS 후 미진입)
- **수동 재구독 endpoint**: `POST /api/realtime/resubscribe` — F1 자동 로직과 동일 규약 (`_send_subscribe(TICK_TR_ID, t, subscribe=True)` + 50ms sleep + `_subscriptions` 직접 수정 금지). 운영 시간대 ScanMonitor 끊김 배지 옆 인라인 버튼. 응답 `{resubscribed, tickers(sorted)}`. `_ws is None` 시 400. `[ws_manual_resubscribe]` write_log

### 우선순위 정책

- `scanner.subscribe_filtered_stocks(priority_groups=...)` 가 HIGH→LOW (positions → next_day_clear → swing → momentum → breakout) 순으로 처리
- HIGH (보유/익일청산) 는 `bypass_limit=True` 절대 보장
- 후순위는 잔여 슬롯 초과 시 drop + `[priority_drop] swing=X momentum=Y breakout=Z` INFO. HIGH 단독 41 초과 시 ERROR
- **사이클 25-B (2026-05-20) `_resubscribe_stale_priority` 분리**: positions/next_day_clear stale → HIGH+bypass_limit=True, 그 외 후보 stale → LOW+bypass_limit=False. 보유/익일청산 보장 절대 유지 + 후보 메인 과부하 방지

### get_subscribed_tickers / get_acked_tickers

- `get_subscribed_tickers() -> set[str]` — TICK(H0STCNT0/H0NXCNT0/H0UNCNT0) 구독 합집합. 체결통보·장운영정보 제외. 사이클 26: H0UNCNT0(통합) 하위 호환 보존 + H0STCNT0/H0NXCNT0 시간대별 분리
- `get_acked_tickers() -> set[str]` — TICK 필터 ACK set. KIS REST/WS 슬롯 사용현황 조회 API 미존재 → 우리 측 ACK 추적이 "SEND 후 무응답" 가시화의 유일한 길

### 시세 채널 시간대별 전환 (사이클 26, 2026-05-20)

`scanner.get_active_tick_tr_ids(now_t=None) -> set[str]` 로 현재 활성 TR_ID set 결정:

| 구간 | TR_ID | 메서드 |
|------|-------|--------|
| 08:00~08:59:09 | {H0NXCNT0} | PRE_NXT 단독 |
| **08:59:10~08:59:59** | {H0NXCNT0, H0STCNT0} | KRX 사전 마진 (50초) |
| 09:00~15:30 | {H0STCNT0} | KRX MAIN |
| 15:30~15:39:09 | {H0STCNT0} | 종가 흡수 마진 (10분) |
| **15:39:10~15:39:59** | {H0STCNT0, H0NXCNT0} | NXT 사전 마진 (50초) |
| 15:40~19:59 | {H0NXCNT0} | POST_NXT 단독 |

사전 마진 구간에서 두 채널 동시 활성 — `_board_transition_loop` 가 종목별 원자 전환 진행.
`on_tick` 중복 호출 안전: `scanner.ticker_prices[ticker]` 마지막 값 채택 + `_selling`/`is_ticker_blocked_for_buy` 중복 매수 차단.

**종목 단위 원자 전환 (`_atomic_board_transition`)**:
1. `kis_ws_pool.unsubscribe(stale_tr_id, ticker)` 호출
2. `_subscriptions_acked` 에서 `(stale_tr_id, ticker)` 제거 확인 polling (timeout 2s)
   - timeout → WARNING `[atomic_transition_ack_timeout]` + 강행
3. new_tr_id 가 None 아니면 `subscribe(new_tr_id, ticker, priority=HIGH|LOW)` 호출
4. 50ms sleep (KIS 부담 회피)

`_board_transition_loop`: HIGH (positions/next_day_clear) 우선 처리 → `[board_transition_complete]` INFO

## handler.py — 메시지 처리

- 파이프(`|`) 구분 메시지 파싱
- **실시간 체결가** (H0STCNT0/H0NXCNT0/H0UNCNT0): 현재가/시가/등락률 추출 → `RiskManager.on_tick` 콜백 (세 TR_ID 동일 포맷 → 단일 파서). 사이클 26: H0STCNT0(KRX) + H0NXCNT0(NXT) 시간대별 분리
- **체결통보** (H0STCNI0/H0STCNI9): AES-256-CBC 복호화 → **계좌번호 필터** → `OrderEngine.handle_execution_notice` 콜백
- **NXT 장운영정보** (H0NXMKO0): 보드 전환 이벤트 → `register_board_handler` 등록 콜백(SessionTracker) 전달. KIS 명세 필드 미기재 → 운영 데이터 기반 확정
- 체결통보 필드 매핑 (`^` 구분): [0]HTS ID, **[1]계좌번호(8)+상품코드(2)**, [2]주문번호, [3]원주문번호, [4]매도매수구분, [5]정정구분, [6]주문종류, [7]주문조건, **[8]종목코드**, [9]주문수량, [10]체결단가, [11]체결시간, [12]거부여부, [13]체결구분(1:접수,2:체결), [14]?, [15]?, [16]체결수량, [17]고객명, [18]종목명
- **계좌 필터**: `fields[1]` 이 `settings.kis_account_no` 로 시작하지 않으면 무시 (실전 H0STCNI0 은 동일 HTS ID 묶인 타 계좌 통보 함께 푸시)

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
- **K (stale watcher)** — `pool.resend_subscribe_for_ticker` 가 `_ticker_to_session` 활용해 정확한 세션 재전송
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
