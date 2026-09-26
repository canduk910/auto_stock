# CLAUDE.md — src/realtime/ (WebSocket 실시간)

> 이력: [`docs/history/src-realtime-CLAUDE.history.md`](../../docs/history/src-realtime-CLAUDE.history.md)
>
> 이 문서는 **지금 동작하는 규칙만** 적는다. 바뀐 경위·실측 수치·결정 근거는 위 history 로,
> 사이클별 보고 원문은 [`docs/HARNESS_CHANGELOG.md`](../../docs/HARNESS_CHANGELOG.md) 로 간다.

KIS WebSocket 실시간 시세 수신 + 체결통보 처리. 메인 + 보조 N 세션 풀(`WebsocketPool`).

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

- `subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False) -> Optional[str]` — 세션 label 반환 ("main" / DB 라벨). drop → None
- `unsubscribe(tr_id, tr_key)` — 분배 추적된 세션에서 해제. 추적 없으면 noop. 체결통보 메인 강제
- `unsubscribe_all()` — 분배 추적 dict 순회 + 모든 세션 매칭 해제
- `unsubscribe_in_pool(tr_id, tr_key)` — K stale watcher 헬퍼. 추적 dict 제거 + 세션 unsubscribe. 강제 재등록 시 라운드로빈 재선택 의도
- `resend_subscribe_for_ticker(tr_id, tr_key)` — `_ticker_to_session` 추적 세션에 재SEND(추적 없으면 메인 fallback). ⚠️ **production 호출자 0건 · 재도입 금지** — KIS 공식 답변 「기등록한 사항을 재등록하지 않도록」(cycle17). AST 가드 `tests/unit/engine/test_stale_force_reregister_constant_removed.py`(G-DEAD-2)가 `src/engine/`·`src/realtime/` 전역에서 호출부 0건을 강제한다
- `get_subscribed_tickers() -> set[str]` — 메인 + 보조 TICK 합집합
- `get_acked_tickers() -> set[str]` — 합집합 ACK
- `get_subscriptions_by_session() -> dict[str, set[str]]` — 세션 label → ticker set(역인덱싱, 영속 dict 없음). 소비처 = `[stale_watcher_detail]` · `[tick_coverage_session]` · `/api/realtime/subscriptions` 의 `tickers_detail`
- `get_session_status() -> list[dict]` — 세션별 label/subscribed/acked/limit/ws_connected/reconnect_count + tickers
- `start(dispatch_message=None)` — DB `kis_quote_accounts.list_accounts(active_only=True)` 조회 → 각 라벨별 `KisWebSocket` 생성 + `connect()` task 발화. 보조 0개 → noop + `[pool_start]` INFO. `_started` 멱등 가드
- `stop()` — 보조 connect task cancel + 각 보조 `disconnect()`. `_quotes` / `_ticker_to_session` / `_started` clear
- `disable_quote_session(label)` — health monitor 자동 비활성 헬퍼. 라벨 매칭 세션 disconnect + `_quotes` 제거 + `_ticker_to_session` 정리 + `_round_robin_idx=0` reset. 메인 라벨 noop (안전 가드)
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
- 보조 0개 → `sessions` 길이 1 (main only)
- **세션 라벨** — 보조 세션 라벨은 DB `kis_quote_accounts.label`(ISA/sub/gold 등 사용자 등록 라벨) 그대로, 메인은 `"main"` 고정. `_session_label(ws)` · `get_session_status()` · `disable_quote_session(label)` · `force_reconnect_session`(`stale_session_recovery.py`) · `build_session_subscription_view`(`stale_diagnostics.py`) · 로그 prefix(`[tick_coverage_session]` · `[stale_watcher_detail]` · `[priority_drop_pool]` · `[silent_inactive_force_reconnect]` · `[ws_heartbeat]`) · UI `KisAccountPoolCard` 가 모두 같은 라벨을 쓴다. 🔴 **`quote-N` 파싱 금지** — 라벨→세션 해석은 `getattr(q, "_label", None) == label` 매칭이고, `_quotes[idx]` 인덱스는 내부 전용이다

## websocket.py — KisWebSocket 연결 관리

- WebSocket 접속키 발급 (`/oauth2/Approval`)
- 종목 시세 구독/해제 (**최대 41건, KIS 공식 한도** — `MAX_SUBSCRIPTIONS = 41`)
- 체결통보 구독 (실전 H0STCNI0+HTS ID / 모의 H0STCNI9+계좌번호)
- Heartbeat 감시 (30s 미수신 → 재연결)
- 자동 재연결 (최대 5회, 지수 백오프)
- 연결 시 AES iv/key 수신 + 저장
- 구독 한도 초과 시 에러 대신 경고 + skip. LOW(`bypass_limit=False`)의 `최대 구독 수(41) 도달, {tr_id}/{tr_key} 구독 건너뜀` WARNING 은 `_max_sub_warn_cap: DailyEmitCap[(tr_id,tr_key)]` 로 **1회/키/일**(`_max_sub_warn_date` KST 자기 리셋 = scheduler 배선 불요). **드롭 `return`·`bypass_limit` 분기는 cap 밖**(HIGH 보유/익일청산 절대 보호, 사이클 32 R4 영속 — 관찰성 전용)이고, scanner `[priority_drop]` 카운트 요약과 HIGH 초과 `[priority] HIGH 구독 한도 초과` ERROR 도 별도 경로라 cap 이 매매·경보 신호를 막지 않는다. 회귀 가드 `tests/unit/realtime/test_cycle197_max_sub_warn_cap.py`
- `__init__(*, token_manager=None, is_main=True, label=None)` — 보조 세션은 외부 매니저 주입(`get_token_manager(label)`). `label` 은 메인 `"main"` / 보조 DB `kis_quote_accounts.label`, 미지정 시 `is_main` 기반 자동 결정
- **PINGPONG** — KIS 가 메인 세션에 약 11~14s 간격 PINGPONG JSON 을 보낸다 → `_handle_raw` `tr_id=="PINGPONG"` 분기에서 즉시 echo-back + `_pingpong_recv_count` / `_pingpong_last_at` 갱신. **L1 DEBUG** `[ws_pingpong_echo] label=...`(운영 INFO 미노출). **L2 INFO 5분 통계** = `_heartbeat_metrics_loop` 가 `HEARTBEAT_METRICS_INTERVAL_SECS=300` 주기로 `[ws_heartbeat] label=... window=300s pingpong_recv=N avg_interval=Xs last_age=Ys heartbeat_timeout=Z` emit + write_log 영구 보존 + 카운터 reset. `_receive_loop` `asyncio.TimeoutError` 분기에서 `_heartbeat_timeout_count += 1`. Task lifecycle = `connect()` 진입 직후 1회 발화 + `disconnect()` cancel + await 정리(좀비 task 방지, `asyncio.CancelledError` graceful). 메인+보조 인스턴스별 독립 카운터. **보조 시세 세션엔 KIS 가 PINGPONG 을 보내지 않는다**(heartbeat_timeout 0 = 시세 송수신으로 연결 유지)
- **WS action 집계** — 구독/ACK/해제/OPSP0002 ALREADY 는 개별 `logger.info` 대신 `_ws_action_collector: dict[str, dict[str, list[str]]]`(tr_id → {SUBSCRIBE/UNSUBSCRIBE/ACK: list[tr_key], OPSP_ALREADY: int})에 쌓인다. `_record_action(tr_id, tr_key, action)` 호출부는 `_send_subscribe` 진입 · SUBSCRIBE SUCCESS · OPSP0002 ALREADY **3곳**, `_flush_ws_action_collector()` 가 `[ws_action_summary] label=... tr_id=... window=300s +N SUBSCRIBE [...] -M UNSUBSCRIBE [...] ack=K opsp_already=L` 1행을 emit 한다(종목 cap 20 + overflow `...+N`). `_ws_action_metrics_loop` task 는 5분 주기이며 `connect()` 진입 직후 시작 + `disconnect()` cancel **전** 마지막 flush 1회. **개별 ERROR 로 남기는 7 prefix**(집계 금지, 사이클 29 005935 LMS chain 진단 의무): `[ws_subscribe_reject]` · `[silent_inactive_force_reconnect]` · `[ws_heartbeat]` heartbeat timeout · `[aes_key_skip]` · `[ws_reverify]` · `[stale_force_retry_cap]` · `[stale_priority_resubscribe_cap_exceeded]`. AST 영구 가드 G-7(`_send_subscribe` 직접 `logger.info` 0건) + G-8-A/G-8-B(`_run_swing_rest_poll_once` / `check_and_resubscribe_stale` 직접 `logger.info` 0건)

### subscribe / 거절 감지 / ACK 추적

- **`subscribe(tr_id, tr_key, *, bypass_limit=False)`**: `bypass_limit=True` 면 `MAX_SUBSCRIPTIONS` 한도 skip + 무조건 add. 보유·익일청산 종목에 사용 — 손절·트레일링 감시 우선
- **구독 거절 감지 (E2)**: `_handle_raw()` 가 `body.rt_cd != "0"` 또는 `msg1` 키워드 (`ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/EXCEED/DUPLICATE` 대소문자 + 한국어 `한도/초과/중복/허용되지/권한`) 매칭 시 `_subscriptions.discard` + `_subscriptions_acked.discard` + `logger.error("[ws_subscribe_reject] tr_id=... ticker=... msg_cd=... msg1=...")` **1회**(직접 `write_log` 금지 — `_DbLogHandler` 위임 단일 INSERT). 거절 분기 후 조기 return → 정상 SUBSCRIBE SUCCESS AES iv/key 저장 분기와 분리. 다음 `_scan_loop` 자연 재시도
- **OPSP0002 ALREADY IN SUBSCRIBE**: 거절 아닌 "KIS 측 이미 활성" 의미 — 거절 분기 *전* `_subscriptions/_subscriptions_acked.add` 로 정합성 회복 + INFO. msg_cd `OPSP0002` 또는 `ALREADY`/`이미 구독`/`이미 등록` 매칭
- **재연결 후 자동 검증 (F1)**: `connect()` 가 재연결 + 기존 구독 복원 직후 `_reconnect_count > 0` 가드 통과 시 `asyncio.create_task(_verify_subscriptions_after_reconnect())`. `VERIFY_AFTER_SECS=60` 대기 → `scanner.ticker_last_tick` 비교 → `VERIFY_FRESHNESS_SECS=60` 내 tick 없는 TICK 구독 1회 재전송. KIS silent inactive 차단. 안전 가드: `_reverify_in_progress` 중첩 방지 / 첫 연결 발화 안 함 / 검증 중 disconnect 시 종료 / 예외 ERROR + 플래그 해제. WARNING 은 `logger.warning("[ws_reverify] reconnect_count=N stale=M/T preview=[..]")` 1회(`_DbLogHandler` 위임 단일 INSERT)
- **SUBSCRIBE ACK 추적 (G1)**: `_subscriptions_acked: set[tuple[str, str]]`. `_handle_raw` 가 `rt_cd=="0" AND "SUBSCRIBE SUCCESS"` 매칭 시 add + INFO. `subscribe`/`unsubscribe`/E2 거절 시 discard. `connect()` 재연결은 `_restore_subscriptions_after_reconnect()` 헬퍼가 ACK clear + send 재전송 동기 처리 — F1 task 발화 *전* 완료
- **`_subscriptions` 정합성 가드 (in-flight ACK race 차단)**: SUBSCRIBE SUCCESS 분기에서 `(tr_id, tr_key) in self._subscriptions` 가드. orphan ACK 는 `_subscriptions` 부재 → acked 에 add 안 함 + DEBUG `[ws_ack_orphan]`. `_scan_loop` 5분 주기 unsubscribe→ACK 도착 race 차단. AES iv/key 저장 분기는 정합성 가드와 무관 (단일 글로벌)
- **구독 ACK grace period** — `_subscribed_at: dict[tuple[str, str], datetime]` (사이클 88 G-REJECT-3 의 4 dict 에 더한 **5번째 분리 dict**, 통합 금지). **5 사이트 record/pop**: (1) SUBSCRIBE SUCCESS = `_subscribed_at[(tr_id, tr_key)] = now()` (2) OPSP0002 ALREADY = 동일 갱신(KIS 측 활성 = 우리 측 grace 시점 갱신) (3) `unsubscribe()` = pop (4) E2 거절 = pop 동행 (5) `_restore_subscriptions_after_reconnect()` = `clear()` 동행. **websocket_pool 합산 property** = `WebsocketPool._subscribed_at`(메인+보조 모든 세션 `dict.update` 합집합). **grace 가드**는 `stale_watcher_core.check_and_resubscribe_stale` 안의 `_is_within_grace(t)` = `if t in ticker_last_tick: return False`(첫 시세 입수 후 grace 미적용 — 사이클 29 005935 보호) + `ack_at not datetime: return False`(ACK 미확인 race 보호) + try/except 안전 폴백. **상수** `stale_diagnostics.SUBSCRIBE_GRACE_SECS = 180`(= 3.0 × `STALE_FRESHNESS_SECS`), `stale_manager.__all__` re-export. 회귀 가드 `tests/unit/realtime/test_cycle135_subscribe_grace_period.py`
- **AES 키 격리 가드** — `_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0", "H0STCNI9"})` 모듈 상수 + `_handle_raw` SUBSCRIBE SUCCESS 분기의 이중 가드: (1) `self.is_main=True` **∧** (2) `tr_id in _EXECUTION_NOTICE_TR_IDS` 를 모두 만족할 때만 `set_aes_keys(iv, key)` 를 호출한다. 그 밖의 시세 SUBSCRIBE SUCCESS·보조 세션 SUBSCRIBE SUCCESS 는 모듈 전역 키 저장 skip + DEBUG `[aes_key_skip] tr_id=... is_main=...`. `WebsocketPool.start()` 는 보조 세션을 `KisWebSocket(token_manager=manager, is_main=False)` 로 명시 생성한다. 이유 = 보조 세션 시세 ACK 의 AES 키가 모듈 전역 `_aes_iv`/`_aes_key` 를 덮어 메인 체결통보(H0STCNI0/H0STCNI9) 복호화가 깨진 2026-05-19 운영 사고의 재발 방지. 자체 인스턴스 변수 `self.aes_iv`/`self.aes_key` 는 디버깅용 보존. 회귀 가드 `tests/unit/realtime/test_aes_keys_main_only.py`
- **OPSP0002 backoff 가드** — `_opsp_backoff_until: dict[tuple[str, str], float]`. `_handle_raw` 의 `OPSP0002 ALREADY IN SUBSCRIBE` 분기에서 `self._opsp_backoff_until[(tr_id, tr_key)] = time.time() + 300.0` 기록 + INFO `[ws_opsp_backoff until=+300s]`. `subscribe(tr_id, tr_key, *, bypass_limit=False)` 진입 시 `time.time() < self._opsp_backoff_until.get(key, 0)` 이면 send skip + DEBUG `[ws_subscribe_backoff] remain=...s`(한도 검사 **전**, `_subscriptions` 미추가 → 다음 자연 재시도 시 일관 동작). `bypass_limit=True`(HIGH 보유/익일청산)는 검사 skip — 손절 우선 보장. **300s 인 이유** = `_scan_loop` 5분 주기 ≥ backoff 만료라 같은 사이클 안 재시도가 구조적으로 막힌다(KIS 「기등록한 사항을 재등록하지 않도록」). 회귀 가드 `tests/unit/realtime/test_ws_subscribe_backoff.py`
- **수동 재구독 endpoint**: `POST /api/realtime/resubscribe` — F1 자동 로직과 동일 규약 (`_send_subscribe(TICK_TR_ID, t, subscribe=True)` + 50ms sleep + `_subscriptions` 직접 수정 금지). 운영 시간대 ScanMonitor 끊김 배지 옆 인라인 버튼. 응답 `{resubscribed, tickers(sorted)}`. `_ws is None` 시 400. `[ws_manual_resubscribe]` write_log

### 우선순위 정책

- `scanner.subscribe_filtered_stocks(priority_groups=...)` 가 HIGH→LOW (positions → next_day_clear → swing → momentum → breakout) 순으로 처리
- HIGH (보유/익일청산) 는 `bypass_limit=True` 절대 보장
- 후순위는 잔여 슬롯 초과 시 drop + `[priority_drop] swing=X momentum=Y breakout=Z` INFO. HIGH 단독 41 초과 시 ERROR
- `_resubscribe_stale_priority`: positions/next_day_clear stale → HIGH + `bypass_limit=True`, 그 외 후보 stale → LOW + `bypass_limit=False` (보유/익일청산 보장 유지 + 후보의 메인 과부하 방지)

### get_subscribed_tickers / get_acked_tickers

- `get_subscribed_tickers() -> set[str]` — TICK(H0STCNT0/H0NXCNT0/H0UNCNT0) 구독 **합집합**. 체결통보·장운영정보 제외
- `get_acked_tickers() -> set[str]` — TICK 필터 ACK set. KIS REST/WS 슬롯 사용현황 조회 API 미존재 → 우리 측 ACK 추적이 "SEND 후 무응답" 가시화의 유일한 길
- 🔴 **TICK 판정은 `tr_id == TICK_TR_ID` 등가 비교가 아니라 단일 정본 집합 `scanner.TICK_TR_IDS` 의 멤버십이다.** 등가 비교가 하나라도 남으면 전용 채널로 옮긴 종목이 이 집합에서 **조용히 사라져** K stale watcher 블라인드 · `delta_unsubscribe_dropped` 미해제(실제 슬롯 누수) · 매 5분 재SEND · `[tick_coverage]` 분모 감소(= cycle252 「은폐 금지」 계약 위반)가 한꺼번에 생긴다
- **진단 프로브 격리 기준은 「프로브 정체성」이다** — 채널 동일성이 아니다(전용 채널이 실 구독에 쓰이므로 채널로는 가를 수 없다). 판정은 `websocket.is_probe_excluded(tr_id, tr_key)`, 집합은 `PROBE_EXCLUDED_TUPLES`(+ 수명 dict `_PROBE_EXCLUSION_DAY`). 수명 = 프로브 stop · 20:00 `unsubscribe_all`/`stop`(`reset_probe_exclusions()`) · **KST 날짜 경과 시 판정 시점 자기 회수**. **비어 있는 것이 정상 상태**다 — 남으면 같은 식별자의 라이브 구독을 은폐한다

### 시세 채널 — 시간축 전환 + 프리 창 속성축 보정

시각 기반 채널 전환의 옛 구현(사이클 26)은 `src/` 호출자가 0 이라 삭제됐다(cycle257).
현행 전환은 leaf 둘 — `tick_channel_clock.py`(시각축 파생) · `tick_channel_switch.py`(전환·자동 원복) 뿐이다.

| | |
|---|---|
| 종착지(재론 금지) | 통합 채널 `H0UNCNT0` **폐기**. KRX 전용 `H0STCNT0` + NXT 전용 `H0NXCNT0` 2채널 (2026-09-07 사용자 결정) |
| 리졸버 | `scanner.tick_tr_id_for(ticker, *, priority)` — 시각축(L1) 위에 프리 창 속성축(L2) 보정. 첫 구독뿐 아니라 **전환 창 안의 살아 있는 구독**에도 적용된다 |
| 속성축(L2) 규칙 | 프리 창에서 `no_feed_registry.is_no_feed(t)` ∧ 출처 확인(`raw ? 'cptt_trad_tr_psbl_yn'`) → `H0STCNT0` / 그 밖 → `H0NXCNT0` |
| 킬스위치 | `system_config.tick_channel_resolver_mode` ∈ `off`/`observe`(기본)/`enforce_low`/`enforce`. **즉시 반영** = `PUT /api/realtime/tick-channel-mode` |
| 매수 축 | 🔴 **게이트는 걷혔다(cycle336)** — 코호트도 매수 평가를 받는다. `risk._tick_buy_eval_blocked_by_channel` 은 남아 **계측기**로만 쓰인다(`[tick_buy_gate]` 분모 · `_note_pre_window_krx_frame` 게이팅). 채널 축 술어 금지는 그대로 |

**구간표 — 전환은 하루 1회(`pre_to_krx`)다.**

```
프리장(N1)            → H0NXCNT0   그 시각 NXT 만 연속 체결을 싣는다
전환 창               → 주문 0건 · cycle241 시장 침묵 ⇒ 전환 비용 ≈ 0
정규장 + 애프터마켓   → H0STCNT0   09:00~20:00 연속 (15:30~16:00 포함 — 아래 「완전 휴식」)
```

`H0STCNT0` 는 종목 속성(`nxt_true`/`nxt_false`)과 **무관하게** KRX 애프터마켓 체결을 싣는다
(09-14 라이브 실측 `000815`·`005385`·`000660`).

🔴 **15:30~16:00 은 완전 휴식이다 — 그 구간에도 HIGH·LOW 무관 KRX 채널을 유지한다**
(사용자 결정 2026-09-15 「청산측으로도 참여하지 않는다」, cycle295). 표 실측상 15:40~16:00 은
NXT 에만 연속 체결이 있어(KRX `AFTER_CLOSE_FIXED` 15:30~16:00 `fixed_price` / NXT `AFTER_MARKET`
15:40~20:00 `continuous`) `nxt_true` 보유의 손절 트리거가 매일 그 20분 사라진다 — 이 비용은
**수용된 것**이다. 그 구간의 매도는 `order_engine._route_exchange_by_clock` 이 NXT 로 보낸다
(`("SOR","krx_unsupported_keep")`). 되살리려면(보유 NXT 추종 갭 홀드) **새 승인 사이클이 필요**하고,
그 전에 ① 표가 바뀌었는지(KRX 가 그 시각에 연속 체결을 갖게 됐는지) ② 사용자 결정이 바뀌었는지를
먼저 가른다.

🔴 **시각 리터럴 0건이 계약이다.** 경계 셋은 전부
`market_state.get_market_table(on_date)` **공개 API** 파생이다 —
`nxt_pre_end`(NXT·PRE_MARKET 의 end) · `krx_regular_open`(KRX·REGULAR 의 start) ·
`krx_continuous_end`(KRX 중 **`match_kind=="continuous"`** 의 end 최댓값).
`MARKET_TABLE` 을 직접 순회하지 않는 이유 = `effective_from`/`effective_to`
해석기(`_is_effective`)가 private 이고, 빠뜨리면 09-13 이전 날짜에서 20:00 이
나와 거짓이 된다. `krx_continuous_end` 를 `phase` 가 아니라 `match_kind` 로 고른
이유 = KRX 가 연속 구간을 또 신설해도 열거가 낡지 않는다.
전환 시각 = `clamp(nxt_pre_end + offset, nxt_pre_end, krx_regular_open)`,
`offset` 기본 300초(`tick_channel_clock.DEFAULT_SWITCH_OFFSET_SECS`).

**fail-open 은 층마다 다르다:**

| 층 | 실패 | 폴백 | 근거 |
|---|---|---|---|
| L1 시각축 | 표 조회 실패·행 부재·`now` 이상 | **`H0STCNT0`** | 09-14 실측이 확정한 채널 · 구독 수명의 92% 가 KRX 창 · 셋 중 **모의(VTS) 지원은 그것뿐** |
| L2 속성축 | 분류 미적재·예외·출처 미확인 | **프리 창에서 `H0NXCNT0`** | 비대칭 — 모르는 종목을 KRX 로 보내면 진짜 `nxt_true` 의 프리장 체결을 **새로 잃지만**, NXT 로 보내면 진짜 `nxt_false` 는 그 구간에 시장이 없어 **잃을 것이 0**. KRX 창에는 이 층이 없다 |
| L3 킬스위치 | `mode == "off"` | **`H0UNCNT0`** | 유일한 통합 반환 경로 |

출처 검사(`raw ? 'cptt_trad_tr_psbl_yn'`)는 프리 창에서 `nxt_false` 를 KRX 로 **내리는** 판단에만
권위를 준다 — 전환 폭 40% 축소가 거기서 나온다. 출처 미확인 종목은 L2 폴백으로 NXT 로 가므로
07:59 도장 오염(마스터의 65.4% 가 도장 상태이고 그중 420종목은 실제 `nxt_true`)의 실패 비용은 0 이다.

**전환 — 창 안에서만, 창 밖은 금지.** 창은 `tick_channel_clock.switch_windows()` 가 표에서 파생하며
**`pre_to_krx`(아침) 하나**다(전환은 하루 1회 — 사용자 결정). 🔴 **창 안에서도 종목마다 경계를
다시 본다** — 120초 루프는 부팅 시각 기준 고정 위상이라 창 끝 직전에 진입할 수 있다. 경과 시각은
벽시계 재조회가 아니라 **`now` + monotonic 경과**다(두 시계가 갈리지 않게).
트리거는 120초 `stale_watcher_core.check_and_resubscribe_stale` **하나뿐**이다(`_scan_loop` 은
`TIME_SCAN_START` 에 생성돼 아침 전환 창에 존재하지 않는다). HIGH(보유·익일청산)는
**make-before-break** — 신 채널 SEND → ACK 확인(`_subscriptions` ∧ `_subscriptions_acked`
**두 집합**) → 구 채널 해제. ACK 실패는 신 채널만 즉시 회수하고 구 채널을 유지하며 **전환 예산을
소모하지 않는다**. LOW 는 break-before-make. 🔴 **세션 재추첨 금지** — 다른 세션에 떨어뜨리면
`_ticker_to_session` 이 덮여 구 세션 튜플이 **영구 고아**가 된다.

**전환 창 REST 백스톱에 대한 정직한 답** — 그 창엔 REST 도 새 체결가를 주지 않는다
(NXT 휴장 + KRX 시가 단일가). 백스톱은 REST 호출이 아니라 make-before-break +
창 밖 전환 금지 + `[tick_channel_switch_window_missed]` 미전환 관측으로 구현했고
KIS 호출 증가는 **0** 이다.

**자동 원복** = `krx_regular_open + revert_probe_secs`(기본 180초 = `stale_diagnostics.SUBSCRIBE_GRACE_SECS` 재사용).

- **표본** = **「지금 KRX 전용 채널에 앉은 HIGH」** — 전환 이력과 무관하다(프리 창부터 KRX 였던 `nxt_false` 보유가 표본에서 빠지면 원복 자체가 존재하지 않게 된다)
- **교차 확인** = ① 비교 코호트 ≥2 가 fresh → 되돌린다 ② 비교 코호트는 있는데 전부 침묵 → **비결론**, 2×probe 까지 기다렸다가 그래도 침묵이면 되돌린다(`all_silent_escalated`) ③ 비교 코호트 자체가 없다 → 같은 시한 뒤 되돌린다(`all_silent_no_cross`). 전원 침묵을 `market_wide` 로 **결론지어 기각하지 않는다** — `enforce` 의 정상 상태가 "전 종목 같은 채널" 이라 그 채널이 진짜 죽은 날엔 비교 코호트도 함께 침묵한다
- **래치는 결론적 판정에만** — `frames_present`(건강) 또는 되돌림만 래치하고 비결론은 다음 사이클이 다시 잰다(상한 `MAX_REVERT_PROBE_ATTEMPTS=10`)
- 🔴 **되돌림도 make-before-break 다** — HIGH `bypass_limit=True`, 반환값 집계. 선해제(`make_before_break=False`)를 라이브 구간에 걸면 41-cap·OPSP 백오프에 막힌 종목이 어느 채널에도 없는 채로 종일 남는다
- 되돌린 상태는 `day_reverted` 래치로 그날 종일 **프리 창 규칙**이다(단순 「전원 NXT」면 `nxt_false` 가 새 blind 가 된다). 되돌린 뒤 그날 재시도는 없다. 래치는 벽시계 날짜로 스스로 풀리고, 시계를 못 읽는 경로에서도 날짜 키가 비지 않는다(영구 좌초 차단)

🔴 **코호트는 매수를 막지 않는다 — 세는 일만 한다 (cycle336).** `risk.on_tick` 의 매수 분기에
코호트 게이트가 **없다**. 근거 = `nxt_tradable` 은 「어느 거래소로 보낼까」 축이지 「살까 말까」
축이 아니다(사이클 156 Q0 · 전략 3파일 주석, 5전략 전부 `list_by_filter(nxt_tradable=None)`).
품질 관문(거래정지·관리종목·정리매매·시장경고·ETF/리츠/SPAC·저유동)은 이 축과 **무관하게**
전부 살아 있다. 🔴 **매수 상한도 이 축과 무관하다** — `_apply_budget_limit` 관문과
`max_positions` 가 정한다. 이 축이 정하는 것은 **후보 밀도와 슬롯 회전 속도**뿐이다.

`scanner._stamp_cohort` 는 그대로다 — **구독 발사 시점에 확신할 때만** 심고(하루 단방향 닫힘
래치, 매일 리셋) **모드를 보지 않는다**. **채널 축 술어 금지**도 그대로다 — 전 종목이 전용
채널이라 술어를 채널로 되돌리면 momentum·VB·LTV·BFB·VCP **5전략의 틱 매수가 통째로 죽는다**
(그 5전략은 틱이 유일 매수 경로다). **스탬프 부재 = 열어 둔다** — 닫힘 오류는 레지스트리 한 번
실패로 전 종목에 동시에 일어나고(상관 실패) 열림 오류는 종목별 독립이라 최대 위험은 전자다.
⚠️ 스탬프가 틀려도 **매수는 안 막히고 계측만 흔들린다** — fail-open 의 대가가 그만큼 작다.

🔴 **스탬프는 재시도된다.** `scanner.restamp_cohorts(tickers)` 를 5분 `subscribe_filtered_stocks` 와
**120초 `stale_watcher_core`** 둘 다에서 `ensure_fresh` 직후에 부른다 — 후자가 아침 창을 덮는다
(`_scan_loop` 은 `TIME_SCAN_START` 에야 생기고, 07:59 는 `_full_universe_load_krx_primary` 의 도장이
마스터의 65.4% 를 덮은 시각이라 1회 스탬프로는 미스탬프가 남는다). 닫힘 우세 단방향이라 재호출이
계측을 더 열 수 없다(매수와는 무관하다).

규모는 `[tick_buy_gate] stamped_no_feed= stamped_feed= unstamped=` 가 남긴다 — cap 키가 시각
구간별이라 **하루 두 행**이고 **판단은 정규장 창 행으로 한다**(프리 창 행의 `unstamped` 는 도장
오염을 재는 값이라 크게 나오는 것이 정상이고, 그 값으로 배선을 판정하면 매일 거짓 경보다).
출처 조회가 통째로 실패하는 날은 **상관된 열림**이라 `[no_feed_provenance_unavailable]` **WARNING**
1회/일을 남긴다.

**레거시 통합 구독 재라우팅** — `scheduler.py` 의 두 줄(익일청산 시가 수신 · 스윙 매수 직후)이 풀을
우회해 통합 채널로 직접 구독한다. `KisWebSocket.subscribe` 첫 문장의 `_reroute_legacy_unified(tr_id,
tr_key)` 가 그것을 흡수한다 — 요청 tr_id 가 **시세 채널이면서 전용이 아닐 때**(= 통합)만, 그리고
`mode == "enforce"` 에서만 재라우팅하고, 체결통보(`H0STCNI0/9`)·장운영정보(`H0UNMKO0`)·전용 2채널·
`off`/`observe`/**`enforce_low`** 는 **byte 동일**로 통과한다. `enforce_low` 를 통과시키는 것이
계약이다 — 이 함수는 우선순위를 모르므로 HIGH 를 스코프 밖에 두는 단계에서 재라우팅하면 그 안전
장치가 통째로 무력화되고, 풀의 병행 dict 와 세션 실구독이 갈려 없는 튜플에 UNSUBSCRIBE 를 보내
KIS `OPSP0003` + 영구 고아를 만든다. 같은 이유로 **`WebsocketPool.subscribe` 진입에서도 한 번
적용**해 `_ticker_to_tr_id` 가 항상 세션이 실제로 구독한 채널과 같게 만든다(재라우팅은 멱등이라
세션 안 호출은 no-op). 관측 = `[tick_channel_legacy_reroute]` 1회/(ticker)/일. 근본 시정(그 두 줄을
리졸버 경유로)은 `scheduler.py` 승인 대상이다.

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
| `tick_channel_switch_ack_timeout_secs` | 5.0 | HIGH make-before-break ACK 대기 (읽는 쪽 클램프 `[1.0, 30.0]`) |
| `tick_channel_revert_probe_secs` | 180 | 개장 후 원복 판정 시점 (읽는 쪽 클램프 `[60.0, 900.0]`, 미설정 = `SUBSCRIBE_GRACE_SECS` 재사용) |

🔴 **폐기 키 `tick_channel_gap_hold_enabled`(cycle295 에서 코드·라우트·DB 헬퍼 전부 제거)의 이름을
재사용하지 마라** — DB 에 남은 `false` 행은 읽는 곳이 0 이라 노출되지 않지만, 같은 이름을 반대
의미로 되살리면 저장된 `false` 가 조용히 적용된다. 그 행은 **DELETE 하지 않는다**.

즉시 반영(재시작 불요):

```bash
curl -X PUT .../api/realtime/tick-channel-mode -d '{"mode":"enforce"}'
curl -X PUT .../api/realtime/tick-channel-mode \
     -d '{"mode":"enforce","switch_enabled":false}'   # 채널은 유지, 전환만 정지
curl -X PUT .../api/realtime/tick-channel-mode -d '{"mode":"off"}'
```

⚠️ **배포만으로는 아무 일도 일어나지 않는다** — `DEFAULT_MODE` 는 `observe` 이고
`system_config` 에 그 키를 넣는 마이그레이션도 초기화 코드도 없다. 실제로 켜려면
**07:45 부팅 전에** `tick_channel_resolver_mode='enforce'` 가 DB 에 있어야 한다(부팅 뒤 올려도
코호트 스탬프는 재시도로 따라잡지만, 07:59 사전 구독이 이미 통합으로 나가 그날 「통합 구독 0」이
성립하지 않는다).

「채널이 문제」(`mode`)와 「전환이 문제」(`switch_enabled`)는 **다른 결정**이라 모드
enum 에 태우지 않았다 — 사고 중에 쓸 카드가 `off` 하나뿐이면 운영자가 장중 대량
전환을 실행하게 된다. `switch_enabled` 는 **선택 필드**라 생략하면 현행 값 무접촉이다.
요청 바디의 미지 필드(폐기된 `gap_hold_enabled` 포함)는 `extra=ignore` 로 조용히 무시된다 —
422 로 막으면 같은 요청의 `mode` 킬스위치까지 막히기 때문이다(cycle295).
`GET /api/realtime/tick-channel-mode` 는 그날 `switch_windows`(창 하나, `pre_to_krx`)를 함께
돌려준다 — 운영자가 화면 없이 "오늘 전환이 몇 시로 잡혔는가" 를 확인하는 유일한 채널이다.

**판독 기준** — `[tick_channel_config]` 의 성공 서명은 **`clock_krx + clock_nxt == provenance_ok`**
(시각축이 전 종목을 전용 채널로 판정) 와 **`applied=H0UNCNT0` 0건**이다. ⚠️ `resolved_*` 는
**속성축(2단계) 집계**라 `resolved_unified` 는 `nxt_true` 코호트 크기이며 **0 이 되지 않는다**
(속성축은 `nxt_false` 만 확정하고 `nxt_true` 에는 현행 유지를 돌려준다). 실측 2026-09-17 07:59 =
`clock_krx=69 clock_nxt=77 resolved_unified=77 provenance_ok=146` · 09:30 = `clock_krx=149 clock_nxt=0
resolved_unified=80 provenance_ok=149`. `scanner.py::emit_tick_channel_config` 의 주석도 같은 오류를
갖고 있다(8영역이라 별건) · `[tick_coverage] stale` 은 분모 불변 + `fresh` 증가가 성공 서명 ·
`[no_feed_held]` 와 `[stale_watcher_summary] no_feed_skipped=` 는 **0 에 수렴** ·
`[tick_channel_dual_detected]` 0 이 정상.

`TICK_TR_ID_KRX`/`TICK_TR_ID_NXT` 두 상수는 리졸버의 반환값 자리로 `scanner.py` 에
있고, 세 값을 담은 **단일 정본 집합**이 `scanner.TICK_TR_IDS` 다(두 번째 집합을
만들면 두 판정이 갈리고, 갈린 순간 "구독은 A 해제는 B" 가 된다 — AST 가드가 컬렉션
리터럴 개수를 1 로 잠근다).

`on_tick` 중복 호출 안전: `scanner.ticker_prices[ticker]` 마지막 값 채택 + `_selling`/`is_ticker_blocked_for_buy` 중복 매수 차단.

## handler.py — 메시지 처리

- 파이프(`|`) 구분 메시지 파싱
- **실시간 체결가** (H0STCNT0/H0NXCNT0/H0UNCNT0): 현재가/시가/등락률 추출 → `RiskManager.on_tick` 콜백 (세 TR_ID 동일 포맷 → 단일 파서). 현행 구독은 프리장 `H0NXCNT0` / 정규장·애프터 `H0STCNT0` 이고 통합은 `mode=off` 에서만 나간다. `handler` 는 tr_id 를 `on_tick` 으로 넘기지 않으므로(P1-7 N-4, `handler.py` 는 미승인 8영역) `tick_volume` 의 채널 구분은 **이중 채널 금지 + 전환 창 프레임 0** 으로만 닫힌다
- **체결통보** (H0STCNI0/H0STCNI9): AES-256-CBC 복호화 → **계좌번호 필터** → `[13] CNTG_YN` 분기. `"2"`(체결)만 숫자 파싱을 거쳐 `OrderEngine.handle_execution_notice` 콜백으로 간다. 그 밖의 값은 아래 「접수 전문 기록」 뒤 return 한다
- **NXT 장운영정보** (H0NXMKO0): 보드 전환 이벤트 → `register_board_handler` 등록 콜백(SessionTracker) 전달. KIS 명세 필드 미기재 → 운영 데이터 기반 확정
- 체결통보 필드 매핑 (`^` 구분, KIS `ccnl_notice` 26컬럼): [0]CUST_ID(HTS ID), **[1]계좌번호(8)+상품코드(2)**, [2]주문번호, [3]원주문번호, [4]매도매수구분(02:매수/01:매도), [5]정정구분, [6]주문종류, [7]주문조건, **[8]종목코드**, **[9]CNTG_QTY 체결수량(통보 건별 증분)**, [10]CNTG_UNPR 체결단가, [11]체결시간, [12]거부여부, [13]CNTG_YN 체결구분(1:접수,2:체결), [14]ACPT_YN, [15]BRNC_NO, **[16]ODER_QTY 주문수량**, [17]고객명, [18]ORD_COND_PRC. 🔴 **수량은 반드시 `fields[9]`** — `[16]` 은 주문수량이라 부분/분할 체결에서 positions 과대가 된다(08-28 257720: 실체결 2주가 3주 등록 → 익일 매도 전량 APBK0400). AST 봉인 `test_cycle235_ast_execution_qty.py` + 엔진 overrun 클램프 `[fill_qty_overrun]` 이중 방어
- **계좌 필터**: `fields[1]` 이 `settings.kis_account_no` 로 시작하지 않으면 무시 (실전 H0STCNI0 은 동일 HTS ID 묶인 타 계좌 통보 함께 푸시)

### 접수 전문 기록 — `[order_notice]` · `[order_rejected_notice]` (**기록만, 상태 변경 0**)

체결통보 채널은 체결(`CNTG_YN=2`)만 보내지 않는다. 주문·정정·취소·거부의 **접수 전문**(`CNTG_YN=1`)도 같은
채널로 온다(KIS 명세 `CNTG_YN` `1` = 주문·정정·취소·거부). 거래소가 접수 뒤 거부한 주문은 REST 주문 응답이
성공이라 `[kis_rejection]` 에 남지 않는다. 장중에 그 거부를 알 수 있는 곳이 이 전문이다. 그래서
`_handle_execution` 이 접수 전문을 로그로 남긴다. ⚠️ 거부 전문의 실제 값(`rfus=`)은 라이브 표본 대기다.

- **자리** = 계좌 필터 **뒤**, 체결 경로의 숫자 파싱(`int(fields[10])`·`int(fields[9])`) **앞**. 다른 계좌의
  통보는 기록 전에 걸러진다. 접수 전문은 숫자 파싱에 닿지 않는다.
- `CNTG_YN == "1"` → INFO 1줄:
  `[order_notice] order_no=[2] orig_order_no=[3] side=BUY|SELL rctf=[5] kind=[6] cond=[7] ticker=[8] qty=[9] price=[10] hour=[11] rfus=[12] acpt=[14] ord_qty=[16]`.
  `side` 는 `[4]=="02"` 면 `BUY`, 그 밖은 `SELL` 이다. `[16]` 이 없으면 `ord_qty=` 는 빈 값이다.
  나머지 값은 원문 문자열 그대로 싣고 숫자로 바꾸지 않는다. ⚠️ 접수 전문의 `[9]`/`[10]` 이 무엇을 싣는지는
  실측 대기다(워크리스트).
- 그중 `rfus` 가 `"1"`(KIS 명세의 거부) 또는 `"Y"` 면 같은 칸으로 WARNING `[order_rejected_notice]` 1줄을
  더 남긴다. 거부 1건은 INFO·WARNING **두 행**이 된다. 거부 건수는 WARNING 만 센다.
- `CNTG_YN` 이 `"1"`·`"2"` 둘 다 아니면 기록 없이 DEBUG 한 줄 뒤 return 한다.
- KIS 코드값(`docs/kis/domestic-stock-realtime.md` H0STCNI0 절) = `RFUS_YN` `0` 승인·`1` 거부 ·
  `ACPT_YN` `1` 주문접수·`2` 확인·`3` 취소(FOK/IOC) · `RCTF_CLS` `0` 정상·`1` 정정·`2` 취소.
- 🔴 **개인정보를 싣지 않는다** — `[0]` CUST_ID(HTS ID) · `[1]` 계좌번호 · `[17]` 계좌명, 그리고 원문 payload
  (`fields[:N]` 통째 포함)는 어떤 레벨로도 로그에 넣지 않는다.
- 🔴 **`write_log` 를 따로 부르지 않는다** — 루트 `_DbLogHandler` 가 `src.*` 로거의 INFO 이상을 이미
  `system_logs` 로 나른다(cycle72 G-6 이중 INSERT 금지). 그 핸들러는 `"[<logger>] <msg>"[:500]` 로 자르므로
  한 줄이 500자 안에 들어가야 한다.
- 콜백(`_on_execution`)·주문번호 매핑·포지션은 건드리지 않는다. 취소·거부 전문으로 잔존 주문 상태를 정리하는
  경로는 없다(`src/engine/CLAUDE.md` `order_engine.py` 절 규칙 4 「알려진 비용」).
- 회귀 가드 = `tests/unit/realtime/test_cycle374_order_ack_notice.py`.

### `[open_scope_observe]` 시가 스코프 관측 (**행위 변경 0**)

통합 채널의 일-스코프 필드는 09:00 에 리셋되지 않는다 — `[7] STCK_OPRC` 가 실어 오는 "시가" 는
프리장 기준가일 수 있다. 그래서 **`board="main"` 목표가의 기준가는 WS `[7]` 이 아니라 KRX REST
`stck_oprc`(`J`) 다**(VB·LTV `on_open_price_confirmed(source="rest")`, 상세 =
`src/engine/strategies/CLAUDE.md`).

`_parse_tick_prices` 는 `[7]` 을 **필터 없이** 반환하고 그것이 의도다 — `[7]` 은 08:00 익일청산 갭
판정 · LTV 프리장 보드 목표가 · kojiro 갭스킵/시가아래 가드 · momentum 익일청산 갭률까지 **여섯
소비처**가 공유하므로 0 강등(fail-closed)은 금지다(0 을 받으면 가드가 조용히 꺼지거나 강제 청산으로
뒤집히거나 프리장 매매가 통째로 죽는다).

관측 마커:

```
[open_scope_observe] ticker=%s oprc_hour=%s tick_open=%d cntg_hour=%s hgpr_hour=%s
                     mkop=%s hour_cls=%s in_main_window=%s
```

- 위치 = `_handle_tick` 안, `parsed` 성공 **뒤**. INFO, **1회/ticker/일**(`src/engine/daily_emit_cap.py::KstDailyEmitCap`). 리셋 훅 = `reset_open_scope_observe()`(`reset_day_high_scope_skip` 대칭)
- `oprc_hour` = `[24] OPRC_HOUR`, `hgpr_hour` = `[27]`, `mkop` = `[34] NEW_MKOP_CLS_CODE`, `hour_cls` = `[43] HOUR_CLS_CODE`. `tick_open` 은 `_parse_tick_prices` 가 이미 만든 `[7]` 파싱값을 **그대로** 받는다(다시 파싱하면 두 수가 갈라져 "목표가가 실제로 쓴 값" 을 재는 것이 아니게 된다)

계약 (어기면 관측이 무의미해지거나 매매가 위험해진다):

1. **`_parse_tick_prices` 는 byte 동일이다.** 소스 세그먼트 sha 로 핀했다. 마커는 그 함수 **밖**에 둔다.
2. **게이트와 라벨은 다른 축이다.** *게이트* = `[1] STCK_CNTG_HOUR`(틱 자신의 체결 시각)가 MAIN 창(`090000~153000`) 안일 때만 cap 을 태운다(`_maybe_log_day_high_scope_skip` 과 동일 설계) — 프리장 틱이 1회 cap 을 먹으면 그 종목이 코호트 분모에서 사라지고, `[1]` 파싱 실패도 cap 미소모다. *라벨* `in_main_window` = `[24]` 가 MAIN 창 안인가 — **창 안/밖을 모두 남긴다**(분모가 있어야 오염 비율이 나온다).
3. **원문 보존 — 정규화 금지.** `[24]`·`[27]`·`[34]`·`[43]` 은 0 치환·zero-pad·trim 없이 그대로 남긴다. 부재/접근 실패는 `"?"`, 빈 문자열 수신은 `""` — **둘은 서로 다른 사실이다.**
4. **never-raise + 흡수기의 2차 예외까지 흡수.** 헬퍼 자체가 흡수하고 호출부에서 **한 겹 더** 감싼다. 이 경로에서 예외가 새면 `_on_tick` 콜백과 같은 자리로 전파돼 **틱마다 WebSocket 재연결**이 일어난다(G-REJECT-1 의 `raise` 규약) = 손절 사각. 자기 실패 흔적은 `src/engine/observer_trace.py::trace_observer_failure`(무흔적 `pass` 금지).
5. **hot path 순수성** — `logger` 만 쓴다. `write_log`/DB/`await` 금지(AST A-1 동형). 순서는 **창 게이트 → cap peek(비소모) → 필드 읽기 → emit**.
6. **볼륨 = 종목당 1행/일.** 종목당 다중 로그 금지.

### 수신 가시화 3종

- `KisWebSocket._last_ws_message_at: dict[label, datetime]` — `_handle_raw` 진입 시 모든 메시지(시세/체결통보/PINGPONG/장운영정보)에서 갱신. 종목별 `ticker_last_tick` 과 **분리 유지**(G-REJECT-2 — 통합 금지)
- `handler._silent_drop_count: dict[ticker,int]` + `flush_silent_drop_count()` — `_handle_tick` 의 `len(fields) < 10`(`fields[0]` 없으면 `"_unknown"`)·`parsed is None` 두 분기에서 누적하고, `scheduler._api_recovered_collector_loop` 가 5분마다 `[dispatch_drop_summary] window=300s drops_total=N by_ticker={...}` 1행 INFO + clear. 빈 윈도우는 emit 0
- 3 콜백(`_handle_tick`/`_handle_execution`/`_handle_market_op`) 일관 `try/except Exception: logger.exception("[callback_exception] handler=... ticker=... order_no=... tr_id=... tr_key=..."); raise` — 🔴 **`raise` 의무, swallow 금지**: 콜백 예외가 `_receive_loop` 로 전파돼 WebSocket 재연결을 유발하는 것이 설계다(침묵하면 사이클 29 005935 LMS chain 사고 재현)

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
| H0UNCNT0 | 실시간 체결가 (KRX+NXT 통합) | 종목코드 | `scanner.TICK_TR_ID`. 정상 경로에서 반환되지 않는다 — 유일한 반환 자리는 킬스위치 `mode == "off"` 분기다. 🔴 **`stock_master.nxt_tradable=False`(KRX 단독) 종목의 체결 프레임을 보내지 않는다** — SUBSCRIBE 는 SUCCESS ACK 를 받으므로 구독은 살아 있는 것처럼 보이고 프레임만 영구 0 이다(마스터 전체 **83.2%** 가 KRX 단독. 포렌식 `_workspace/forensics/stale_candidates_0904.md`). **종착지는 폐기**(2026-09-07 사용자 결정) |
| H0STCNT0 | 실시간 체결가 (KRX 단독) | 종목코드 | H0UNCNT0 동일 포맷(47필드 인덱스 전부 동일). 정규장+애프터마켓(09:00~20:00) 전 종목 + L1 폴백. **종목 속성과 무관하게** KRX 애프터마켓 체결을 싣는다(09-14 라이브 실측). **모의(VTS) 지원 — 셋 중 유일** |
| H0NXCNT0 | 실시간 체결가 (NXT 단독) | 종목코드 | 동일 포맷. 프리장(08:00~08:50) 전 종목 + L2 폴백(09-15 08:00 실측 fresh 61→79 로 프레임 확인). **모의(VTS) 미지원** |
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
- **K (stale watcher)** — 첫 stale 즉시 `pool.unsubscribe_in_pool` + `pool.subscribe(priority='HIGH', bypass_limit=True)` **강제 재등록**(KIS 정상 "신규 등록" 패턴, 재SEND 없음). `retry > MAX_STALE_RETRIES(=5)` 면 시간 기반 force_retry 로 넘어간다(`stale_watcher_core.py`)
- **세션 단위 silent inactive 자동 회복** — `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2)` + `subscribed >= SILENT_INACTIVE_MIN_SUBSCRIBED(=5)` + 5분 지속 시 `_ws.close()` 강제 → `connect()` 의 ConnectionClosed catch → 재연결 자동 발화. 시간당 세션당 2회 cap. 판정 가능 세션 ≥2 가 **전부** 침묵이면 세션 고장이 아니라 시장 침묵으로 보고 그 사이클을 기각한다(`[silent_inactive_market_wide_skip]`, cycle241) — 상세는 루트 `CLAUDE.md`
- 🔴 **구조 단순화 금기** (AST `tests/unit/ast/test_external_llm_reject_patterns.py` 영구 차단):
  1. **G-REJECT-1** — 단일 restore 로 **4중 안전망**(F1 · `_scan_loop` · K stale watcher · `_resubscribe_stale_priority`)을 대체하지 않는다. 함수 4종(`_verify_subscriptions_after_reconnect` / `_scan_loop` / `check_and_resubscribe_stale` / `resubscribe_stale_priority`) 존재를 가드가 검증한다. 콜백 예외 swallow 금지(`raise` 의무)도 같은 항목이다
  2. **G-REJECT-2** — stale 판정을 WS 세션 단독으로 하지 않는다. `ticker_last_tick` + `STALE_FRESHNESS_SECS` 종목 단위 판정을 유지한다(사이클 29 005935 재현 방지). 종목별 `ticker_last_tick` ↔ 세션별 `_last_ws_message_at` 책임 분리 유지
  3. **G-REJECT-3** — `_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick` (+ `_last_ws_message_at` · `_subscribed_at`) 을 단일 registry dict 로 통합하지 않는다(orphan ACK race · 41 한도 분산)

## 주의사항

- **체결통보 구독은 매매의 핵심 전제조건** — 미구독 시 포지션 등록 불가 → 손절 불가
- 체결통보는 실전에서 암호화 — 반드시 `decrypt_aes_cbc` 필요
- scheduler 가 WebSocket 연결 직후 체결통보 자동 구독
- 구독 종목 변경 시 기존 해제 → 새 등록 순서
- WebSocket URL 은 REST 와 다름 (`ops.koreainvestment.com`)
- **실전 체결통보 (H0STCNI0)** 는 HTS ID 단위 푸시 — 동일 HTS ID 묶인 타 계좌 통보 함께 들어옴. handler `fields[1]` 계좌 필터링 필수
