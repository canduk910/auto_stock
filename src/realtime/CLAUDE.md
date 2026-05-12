# CLAUDE.md — src/realtime/ (WebSocket 실시간)

KIS WebSocket 실시간 시세 수신 및 체결통보 처리.

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
- **구독 거절 감지(E2, 2026-05-12)**: `_handle_raw()` JSON 응답 분기에서 `body.rt_cd != "0"` 또는 `msg1` 키워드(영문 `ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/EXCEED/DUPLICATE` 대소문자 무시 + 한국어 `한도/초과/이미/중복/허용되지/권한`) 매칭 시 `_subscriptions.discard((tr_id, tr_key))` + ERROR 로그 + `write_log("ERROR", "[ws_subscribe_reject] tr_id=... tr_key=... rt_cd=... msg_cd=... msg1=...")` fire-and-forget. write_log 예외는 swallow — 정합성 회복 우선. 거절 분기 후 조기 return → 정상 SUBSCRIBE SUCCESS AES iv/key 저장 흐름 분리. 다음 5분 `_scan_loop` 사이클에서 E1 우선순위 큐로 자연 재시도 (재시도 큐 별도 미구현)
- **재연결 후 자동 검증 (F1, 2026-05-12)**: `connect()` 가 재연결 성공 + 기존 구독 복원 직후 `_reconnect_count > 0` 가드 통과 시 `asyncio.create_task(_verify_subscriptions_after_reconnect())` 발화. 검증 메서드는 `VERIFY_AFTER_SECS=60` 대기 → `scanner.ticker_last_tick` 비교 → `VERIFY_FRESHNESS_SECS=60` 내 tick 없는 TICK 구독에 대해 `_send_subscribe(TICK_TR_ID, ticker, subscribe=True)` 1회 재전송. KIS silent inactive(거절도 시세도 없음) 차단 — E2 거절 감지가 무력화되는 영역. 안전 가드: `_reverify_in_progress` 플래그로 동시 task 중첩 방지, `_reconnect_count == 0` (첫 연결) 발화 안 함, 검증 도중 `_ws is None`/`_running is False` 면 조용히 종료, 예외 발생 시 ERROR 로그 + 플래그 해제. stale 로그 preview 는 sorted 처음 10개만 표시 + 전체 카운트 명시. WARNING 시 `write_log("WARNING", "[ws_reverify] reconnect_count=... stale=N/M preview=[...]")` fire-and-forget. 재구독 1회로 부족하면 다음 5분 `_scan_loop` 자연 회복에 위임
- **우선순위 정책**: `scanner.subscribe_filtered_stocks(priority_groups=...)` 가 HIGH→LOW (positions → next_day_clear → swing → momentum → breakout) 순으로 처리. HIGH(보유/익일청산)는 bypass_limit=True 절대 보장, 후순위만 잔여 슬롯 초과 시 drop + `[priority_drop] swing=X momentum=Y breakout=Z` INFO 로그. HIGH 단독 41 초과 시 ERROR + `system_logs`
- `get_subscribed_tickers() -> set[str]`: 현재 TICK(H0UNCNT0) 구독 종목만 반환 (체결통보·장운영정보 제외). Phase D `scheduler._report_tick_coverage` 가 5분 주기 미수신 카운트 산출에 사용
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
