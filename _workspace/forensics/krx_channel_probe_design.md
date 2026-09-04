# KRX 단독 채널 프로브·채널 리졸버 설계 메모 (P1-7 B, 2026-09-05 야간 초안)

> 근거 = `stale_candidates_0904.md`. 결정 요청 = 아침 리포트 §4 D8. 이 문서는 코드가 아니라 결정을 돕는 설계다.

## 1. 왜 프로브가 먼저인가
- 확정된 사실은 "통합 채널 `H0UNCNT0` 은 `nxt_tradable=False` 종목을 송출하지 않는다"(나흘 예외 0)까지다. "KRX 단독 채널 `H0STCNT0` 은 송출한다"는 기대이지 실측이 아니다(05-08 b77a764 통합 채널 전환 이전 로그가 없고, KIS 문서·MCP 샘플 어디에도 대상 범위가 없다).
- B 본 시정은 8영역 4파일(`scanner.py`·`websocket.py`·`websocket_pool.py`·`order_engine.py:1104`) + 비8영역 4파일을 건드린다. 프로브 없이 착수하면 8영역 승인·sha 재핀·뮤테이션 비용을 가설 위에 얹는 것이다.

## 2. 프로브를 8영역 무접촉으로 만들 수 있다 (cycle253 후보)
- `kis_ws_pool.subscribe(tr_id, tr_key, ...)` 가 tr_id 를 이미 받고, `handler.dispatch_message` 가 `H0STCNT0` 를 통합 채널과 같은 `_handle_tick` 으로 처리해 `ticker_last_tick` 을 갱신한다 → 라우트에서 `H0STCNT0` 로 구독을 걸고 `ticker_last_tick` 신선도를 보면 수신 여부가 판정된다.
- 격리: TICK 집합 함수·120s K stale watcher·universe guard·delta unsubscribe·F1 재검증은 `tr_id == H0UNCNT0` 필터 → 프로브는 그 경로들에 안 보인다(재등록 대상 아님, 삭제 대상 아님, stale 집계 밖). ⚠️ 예외(cycle253 적대 검증 F4) = 5분 `resubscribe_stale_priority` 는 `ticker_last_tick` 전수가 소스라 프로브 종목이 프레임을 받은 뒤 stale 이 되면 후보에 들 수 있고, cycle240 desired 필터가 꺼진 상태(breakout desired ∅ ∨ HIGH 수집 예외)면 TICK 으로 재구독돼 이중 채널이 된다 — 평일 정상 상태에선 필터가 활성이라 프로브 종목(desired 밖)은 걸러진다. 재연결 복원은 `_subscriptions` 전체라 유지되고, 20:00 `unsubscribe_all` 이 함께 지운다. 슬롯은 정직하게 41 cap 에 셈된다.
- 위험과 가드: `_ticker_to_session` 이 tr_key 단일 키라 **이미 H0UNCNT0 로 구독된 종목·보유·익일청산·desired 후보는 프로브 금지**(라우트가 409 로 거부). 프레임이 오면 `risk.on_tick` 이 실제로 돌기 때문에 후보 종목이면 실매수 신호가 날 수 있다 — 위 배제가 그 경로를 막는다. `bypass_limit=True` 금지(HIGH 슬롯을 밀면 안 된다).
- 엔드포인트 = `POST/GET/DELETE /api/realtime/channel-probe` (명세 `spec_cycle253_channel_probe.md`, 라우트 파일 1개 + 테스트 2개). 기본 OFF — 호출하지 않으면 아무 일도 없다.
- 운영: 월 09:30 후보 2종목 POST → 5분 간격 GET → `received=true` 면 가설 확정, 15분간 `subscribed∧acked∧!received` 면 반증(KIS 문의).

## 3. 프로브 성공 시 B 본 시정 윤곽
- 리졸버 1개 `tick_tr_id_for(ticker) -> "H0STCNT0"|"H0UNCNT0"`(소스 = `no_feed_registry`/`stock_master.nxt_tradable` 메모리 캐시, cycle252 leaf 재사용). `TICK_TR_ID` 직접 사용처 전부(scanner 6·websocket 4·websocket_pool 4·stale_watcher_core·stale_universe_guard·stale_session_recovery·order_engine:1104·scheduler:1347) 를 경유.
- 풀/세션 TICK 필터를 `{H0UNCNT0, H0STCNT0}` 집합으로. `_ticker_to_session` 단일 키 ⇒ **동일 종목 이중 채널 금지 불변식**(AST + 런타임 가드). `_scan_loop` 델타는 `(tr_id, ticker)` 쌍으로 desired 비교(편출/편입 시 채널 재결정 + 재구독).
- 플리커 debounce: `stock_master` 16:15 일괄값 우선, 07:5x eager 갱신의 False 플리커(08-31 064550)는 다음 16:15 까지 채널 변경 보류.
- 예상 부하: nxt_false 71~78 종목이 틱을 내기 시작하면 프레임/일 1.25M → +30~40%. `dispatch_drop_summary`·이벤트루프 지연 관측 동반. tick 전략 유니버스가 1/3 커지는 효과의 체결률·슬롯 예산 재산정(메인 41 헤드룸 후속과 연동).
- 사이클 26 시간대별 전환(`get_active_tick_tr_ids`·`_board_transition_loop`)은 호출자 0 의 죽은 코드 — 속성 기반이 우월(하루 2회 전 종목 재구독 churn 없음, nxt_true 의 NXT 체결 보존). refactor-review 로 삭제 + `src/realtime/CLAUDE.md` 정정.
- 검증 = 포렌식 ②-1 분할 검사 재실행: ACK 종목 100% 프레임>0 이면 종결.

## 4. 프로브 실패(H0STCNT0 도 무송출) 시
- KIS 문의("NXT 비대상 종목 SUBSCRIBE 가 SUCCESS ACK 를 주면서 데이터가 없다") + 보유 사각은 C(`SWING_REST_POLL_EARLY_START` 09:00:30) + tick 전략 nxt_false 보유 시 `[no_feed_held]` 경보로 임시 대응. 장기적으로는 KRX 단독 종목을 REST 폴 기반 보조 피드로 덮는 설계(별도 자문).
