# CLAUDE.md — src/realtime/ (WebSocket 실시간)

KIS WebSocket 실시간 시세 수신 및 체결통보 처리.

## 사이클 7-B (2026-05-17) — WebsocketPool 시세 분배

단일 ``KisWebSocket`` 인스턴스 → 메인 + 보조 N 세션 풀. 외부 호출자(scanner/risk/scheduler)
인터페이스 100% 보존, 내부 분배 로직 캡슐화.

### 자금 안전 절대 원칙

- **체결통보(H0STCNI0/H0STCNI9) → 메인 세션 단일 강제** — ``_enforce_main_only_execution_notice``
  + ``WebsocketPool.subscribe`` 분기가 무조건 메인 우회. 보조 세션 시도 시 ``QuoteSessionExecutionNoticeError``
- **매매/잔고/체결조회** → 본 사이클 변경 0 (사이클 7-A 가드 ``src/auth/CLAUDE.md``)
- **보조 세션** → 시세 only. ``kis_quote_accounts`` DB 등록 후 ``scheduler._boot()`` 재시작 시점에 연결

### 분배 정책

- **HIGH 우선순위**(보유 / 익일청산) → 메인 세션 절대 보장 (``bypass_limit=True``). E1 규칙 유지
- **LOW 우선순위**(스캐닝) → 보조 세션 라운드로빈. 가득 / disconnect 세션 건너뜀. 모두 가용 없으면 메인 fallback
- **중복 ticker** → 메인 우선. 보조에 있는데 HIGH 로 들어오면 메인 승격 + 보조 unsubscribe + ``[pool_promote]`` 로그
- **모든 세션 가득** → drop + ``[priority_drop_pool] tr_key=... priority=LOW reason=all_sessions_full main=N/41 quotes=M`` INFO 로그
- **총 슬롯 = 41 × (1 + N)** (메인 + 보조 N). 보조 0 → 41, 보조 5 → 246

### 운영 점진 활성화

1. **코드 배포 단계**: 풀 코드 + 보조 세션 0개 (DB 미등록) → 메인 only 동작 (회귀 0)
2. **첫 보조 등록**: DB 1개 → 1 보조 활성 → 41 + 41 = 82 슬롯
3. **점진 추가**: DB 2~5 등록 → 풀 점진 확장
4. ``scheduler._boot()`` 재시작 시점에 보조 세션 연결 (기존 메인 흐름 유지)

### 모듈

- ``src/realtime/websocket_pool.py::WebsocketPool`` — 메인(``kis_ws`` 재사용) + ``_quotes: list[KisWebSocket]`` + ``_ticker_to_session: dict[str, KisWebSocket]`` + ``_round_robin_idx: int``
- ``WebsocketPool.subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False) -> Optional[str]`` — 세션 label 반환 ("main" / "quote-N"). drop → None
- ``WebsocketPool.unsubscribe(tr_id, tr_key)`` — 분배 추적된 세션에서 해제. 추적 없으면 noop. 체결통보는 메인 강제
- ``WebsocketPool.unsubscribe_all()`` — 분배 추적 dict 순회 + 모든 세션 매칭 해제
- ``WebsocketPool.resend_subscribe_for_ticker(tr_id, tr_key)`` — K stale watcher 헬퍼. 추적 없는 ticker 는 메인 fallback
- ``WebsocketPool.get_subscribed_tickers() -> set[str]`` — 메인 + 보조 TICK 합집합 (Phase D 호환)
- ``WebsocketPool.get_acked_tickers() -> set[str]`` — 합집합 ACK
- ``WebsocketPool.get_session_status() -> list[dict]`` — 세션별 label/subscribed/acked/limit/ws_connected/reconnect_count + tickers.subscribed/acked
- 호환 property: ``_subscriptions`` / ``_subscriptions_acked`` / ``_ws`` / ``_reconnect_count`` — 메인 단독이 아닌 합집합 또는 메인 기준 반환 (기존 호출자 의미 보존)
- 모듈 싱글톤: ``kis_ws_pool``. 기존 ``kis_ws`` 도 메인 단일로 보존 (풀이 그를 재사용)

### 안전 규칙 멀티 세션 지원

- **E1 (보유·익일청산 우선)** — ``subscribe(priority="HIGH")`` 가 메인 세션 bypass_limit=True 절대 보장
- **E2 (거절 응답 감지)** — 각 세션의 ``_handle_raw()`` 독립 작동. 풀이 거절 처리 재구현 안 함
- **F1 (재연결 후 자동 검증)** — 각 세션의 ``_verify_subscriptions_after_reconnect()`` 가 ``connect()`` 안에서 독립 발화
- **K (stale watcher)** — ``pool.resend_subscribe_for_ticker(tr_id, tr_key)`` 가 ``_ticker_to_session`` 추적 dict 활용해 정확한 세션에 재전송. 추적 없으면 메인 fallback

### 라우트 응답 확장

``/api/realtime/subscriptions`` 응답에 ``sessions`` 배열 추가:

```json
{
  "total": 123, "acked": 100, "fresh_60s": 95, "stale_60s": 5, "limit": 246,
  "sessions": [
    {"label": "main", "subscribed": 41, "acked": 41, "fresh": 40, "stale": 1, "limit": 41, "ws_connected": true, "reconnect_count": 0, "tickers": {"subscribed": [...], "acked": [...]}},
    {"label": "quote-1", "subscribed": 41, ...},
    ...
  ],
  ...
}
```

- ``total/acked`` 는 합집합 카운트, 세션별 분해는 ``sessions[*].subscribed/acked``
- ``limit`` 은 ``MAX_SUBSCRIPTIONS × len(sessions)`` (메인 + 보조 합산 용량)
- 보조 0개 시 ``sessions`` 길이 1 (main only) — 기존 호환

### 회귀 가드 (46 신규)

- ``tests/unit/realtime/test_websocket_pool.py`` (25) — 분배 알고리즘 / 중복 / 체결통보 강제 / drop / get_subscribed_tickers / get_session_status / unsubscribe / 보조 0개 회귀
- ``tests/unit/realtime/test_pool_safety_rules.py`` (8) — E1 / E2 / F1 / K 멀티 세션 지원 + 메인 단일 체결통보 가드
- ``tests/integration/test_pool_distribution.py`` (6) — 5 세션 분배 / 총 슬롯 / disconnect graceful / HIGH bypass / 보조 0개 회귀 / 100 종목 통합 조회
- ``tests/contract/test_routes_subscriptions_pool.py`` (7) — sessions 배열 / 필수 키 / 집계 정합 / limit 확장

## 모듈별 역할

### websocket.py — 연결 관리
- WebSocket 접속키 발급 (`/oauth2/Approval`)
- 종목 시세 구독/해제 (**최대 41건, KIS 공식 한도** — E1, 2026-05-12. 이전 200은 과대 설정으로 silently 거절 차단 못 함)
- 체결통보 구독 (실전: H0STCNI0 키=HTS ID, 모의: H0STCNI9 키=계좌번호)
- Heartbeat 감시 (30초 미수신 시 재연결)
- 자동 재연결 (최대 5회, 지수 백오프)
- 연결 시 AES 복호화용 iv/key 수신 및 저장
- 구독 한도 초과 시 에러 대신 경고 + 건너뜀
- **`subscribe(tr_id, tr_key, *, bypass_limit: bool = False)`**: `bypass_limit=True` 면 `MAX_SUBSCRIPTIONS` 한도 검사를 skip 하고 무조건 add. `subscribe_filtered_stocks(priority_groups=...)` 가 보유·익일청산 종목에 사용 — 보유 시세 누락 시 손절·트레일링 감시 불가하므로 한도보다 우선
- **구독 거절 감지(E2, 2026-05-12)**: `_handle_raw()` JSON 응답 분기에서 `body.rt_cd != "0"` 또는 `msg1` 키워드(영문 `ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/EXCEED/DUPLICATE` 대소문자 무시 + 한국어 `한도/초과/중복/허용되지/권한`) 매칭 시 `_subscriptions.discard((tr_id, tr_key))` + ERROR 로그 + `write_log("ERROR", "[ws_subscribe_reject] tr_id=... tr_key=... rt_cd=... msg_cd=... msg1=...")` fire-and-forget. write_log 예외는 swallow — 정합성 회복 우선. 거절 분기 후 조기 return → 정상 SUBSCRIBE SUCCESS AES iv/key 저장 흐름 분리. 다음 5분 `_scan_loop` 사이클에서 E1 우선순위 큐로 자연 재시도 (재시도 큐 별도 미구현). **N(2026-05-12)**: `OPSP0002 ALREADY IN SUBSCRIBE` 응답은 거절이 아닌 "KIS 측 이미 활성" 의미로 분류 — 거절 분기 진입 *전* `_subscriptions/_subscriptions_acked.add` 로 정합성 회복 + INFO 로그. msg_cd `OPSP0002` 또는 `ALREADY`/`이미 구독`/`이미 등록` 매칭. `_scan_loop` 재구독 → 또 ALREADY → 무한 루프 + tick_coverage stale 위양성 차단(2026-05-12 운영 사고). `_REJECT_KEYWORDS_KO` 에서 광범위 위양성 키워드 `이미` 제거
- **재연결 후 자동 검증 (F1, 2026-05-12)**: `connect()` 가 재연결 성공 + 기존 구독 복원 직후 `_reconnect_count > 0` 가드 통과 시 `asyncio.create_task(_verify_subscriptions_after_reconnect())` 발화. 검증 메서드는 `VERIFY_AFTER_SECS=60` 대기 → `scanner.ticker_last_tick` 비교 → `VERIFY_FRESHNESS_SECS=60` 내 tick 없는 TICK 구독에 대해 `_send_subscribe(TICK_TR_ID, ticker, subscribe=True)` 1회 재전송. KIS silent inactive(거절도 시세도 없음) 차단 — E2 거절 감지가 무력화되는 영역. 안전 가드: `_reverify_in_progress` 플래그로 동시 task 중첩 방지, `_reconnect_count == 0` (첫 연결) 발화 안 함, 검증 도중 `_ws is None`/`_running is False` 면 조용히 종료, 예외 발생 시 ERROR 로그 + 플래그 해제. stale 로그 preview 는 sorted 처음 10개만 표시 + 전체 카운트 명시. WARNING 시 `write_log("WARNING", "[ws_reverify] reconnect_count=... stale=N/M preview=[...]")` fire-and-forget. 재구독 1회로 부족하면 다음 5분 `_scan_loop` 자연 회복에 위임
- **우선순위 정책**: `scanner.subscribe_filtered_stocks(priority_groups=...)` 가 HIGH→LOW (positions → next_day_clear → swing → momentum → breakout) 순으로 처리. HIGH(보유/익일청산)는 bypass_limit=True 절대 보장, 후순위만 잔여 슬롯 초과 시 drop + `[priority_drop] swing=X momentum=Y breakout=Z` INFO 로그. HIGH 단독 41 초과 시 ERROR + `system_logs`
- `get_subscribed_tickers() -> set[str]`: 현재 TICK(H0UNCNT0) 구독 종목만 반환 (체결통보·장운영정보 제외). Phase D `scheduler._report_tick_coverage` 가 5분 주기 미수신 카운트 산출에 사용
- **수동 재구독 endpoint (J2, 2026-05-12)**: `src/routes/realtime.py::POST /api/realtime/resubscribe` 가 F1 자동 재구독 로직과 *동일 규약*(`_send_subscribe(TICK_TR_ID, t, subscribe=True)` + 50ms sleep + `_subscriptions` 직접 수정 금지)으로 수동 트리거 노출. F1=재연결 후 60s 1회 자동 / J2=운영 시간대 ScanMonitor 끊김 배지 옆 인라인 버튼 클릭 → 즉시 stale 일괄 재전송. 응답 `{resubscribed, tickers(sorted)}`. WebSocket `_ws is None` 시 400. 영구 로그 `[ws_manual_resubscribe] count=N tickers=[...]` fire-and-forget
- **SUBSCRIBE ACK 추적 (G1, 2026-05-12)**: `_subscriptions_acked: set[tuple[str, str]]` 신규. `_handle_raw` JSON 분기에서 `rt_cd=="0" AND "SUBSCRIBE SUCCESS" in msg1.upper()` 매칭 시 add + INFO 로그(`WebSocket 구독 ACK`). `subscribe`/`unsubscribe`/E2 거절(`_is_rejection_response`) 시 discard. `connect()` 재연결은 `_restore_subscriptions_after_reconnect()` 헬퍼가 ACK clear + 기존 구독 send 재전송을 동기 처리 — F1 task 발화 *전* 완료해 60s 후 ACK 미수신 종목이 stale 로 정확히 잡힌다. `get_acked_tickers() -> set[str]`: TICK 필터 ACK set (`get_subscribed_tickers` 와 동일 패턴). KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 ACK 추적이 "SEND 후 무응답" 케이스 가시화의 유일한 길

### handler.py — 메시지 처리
- 파이프(|) 구분 메시지 파싱
- 실시간 체결가(H0STCNT0/H0UNCNT0/H0NXCNT0): 현재가, 시가, 등락률 추출 → RiskManager.on_tick 콜백 (세 TR_ID 모두 동일 메시지 포맷이라 단일 파서로 처리)
- 체결통보(H0STCNI0/H0STCNI9): AES-256-CBC 복호화 → **계좌번호 필터** → OrderEngine.handle_execution_notice 콜백
- NXT 장운영정보(H0NXMKO0): 보드 전환 이벤트 → `register_board_handler`로 등록한 콜백(Phase 3 SessionTracker) 전달. KIS 명세 필드 미기재로 운영 데이터 기반 확정
- 체결통보 필드 매핑 (^ 구분): [0]HTS ID, **[1]계좌번호(8자리)+상품코드(2자리)**, [2]주문번호, [3]원주문번호, [4]매도매수구분, [5]정정구분, [6]주문종류, [7]주문조건, **[8]종목코드**, [9]주문수량, [10]체결단가, [11]체결시간, [12]거부여부, [13]체결구분(1:접수,2:체결), [14]?, [15]?, [16]체결수량, [17]고객명, [18]종목명
- 계좌 필터: `fields[1]`이 `settings.kis_account_no`로 시작하지 않으면 무시 (실전 H0STCNI0은 동일 HTS ID에 묶인 타 계좌 통보가 함께 푸시되므로 필수)

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
| H0UNCNT0 | 실시간 체결가 (KRX+NXT 통합) | 종목코드 | 현재 사용 — `scanner.TICK_TR_ID`. NXT 거래도 즉시 반영 |
| H0STCNT0 | 실시간 체결가 (KRX 단독) | 종목코드 | 메시지 포맷 H0UNCNT0과 동일. 호환성 유지 |
| H0NXCNT0 | 실시간 체결가 (NXT 단독) | 종목코드 | 메시지 포맷 동일 |
| H0UNMKO0 | 통합 장운영정보 (KRX+NXT) | 종목코드 | 현재 사용 — 종목 단위 구독이지만 MKOP_CLS_CODE는 시장 전체 공통이라 대표 종목 1개(005930)만 구독해 보드 전환 수신. **모의(VTS) 미지원 — 실전 한정** |
| H0STMKO0 | KRX 단독 장운영정보 | 종목코드 | H0UNMKO0과 동일 메시지 포맷 |
| H0NXMKO0 | NXT 단독 장운영정보 | 종목코드 | H0UNMKO0과 동일 메시지 포맷. 통합 구독으로 충분해 별도 미구독 |
| H0STCNI0 | 체결통보 (실전) | HTS ID | KRX/NXT/SOR 모두 같은 TR로 수신, ODER_KIND 필드로 거래소 식별 |
| H0STCNI9 | 체결통보 (모의) | 계좌번호 | KRX 한정 (VTS는 NXT/SOR 미지원) |

## 주의사항
- **체결통보 구독은 매매의 핵심 전제조건** — 미구독 시 포지션 등록 불가 → 손절 불가
- 체결통보는 실전에서 암호화됨 — 반드시 decrypt_aes_cbc 필요
- scheduler.py에서 WebSocket 연결 직후 체결통보 자동 구독
- 구독 종목 변경 시 기존 구독 해제 → 새 구독 등록 순서
- WebSocket URL은 REST와 다름 (ops.koreainvestment.com)
- **실전 체결통보(H0STCNI0)는 HTS ID 단위 푸시** — 동일 HTS ID에 묶인 타 계좌 체결 통보가 같이 들어옴. KIS API 스펙상 구독 단계에서 차단 불가하므로 handler.py에서 `fields[1]` 계좌번호 필터링 필수
