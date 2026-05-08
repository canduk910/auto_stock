# 테스트 리포트 — 2026-04-21 (Rev.2: 경계면 검증 추가)

## 요약
- ��체: 49건 | 통과: 32건 | 실패: 15건 | 미검증: 2건

---

## Task #15: 인증/API 래퍼 테스트

### 통과 항목 (12건)
- [x] 15-1. POST /oauth2/tokenP 요청 파라미터: grant_type, appkey, appsecret ✓
- [x] 15-1. 응답 파싱: access_token, access_token_token_expired, token_type, expires_in ✓
- [x] 15-1. 토큰 만료 10분 전 자동 갱신 ✓ (token.py:108)
- [x] 15-1. 모의/실전 도메인 전환 ✓ (config.py:29-32)
- [x] 15-2. WebSocket 접속키 발급 (approval_key) ✓ (token.py:73-87)
- [x] 15-3. 토큰 폐기 ✓ (token.py:54-71)
- [x] 15-4. 공통 헤더 구성 (authorization, appkey, appsecret, tr_id, custtype) ✓ (token.py:89-101)
- [x] 15-4. Rate Limit 초당 20건 제한 ✓ (base.py:22-55)
- [x] 15-4. 에러 응답 처리 rt_cd != "0" ✓ (base.py:135-150)
- [x] 15-4. Hashkey 생성 ✓ (hashkey.py)
- [x] 15-5. 모의 TR_ID 전환 T→V ✓ (config.py:46-54)
- [x] 15-4. 네트워크 오류 시 최대 3회 재시도 ✓ (base.py:92-132)

### 실패 항목 (2건)

#### [F1] Rate Limit 이중 제한 구조
- **파일**: src/api/base.py:92-94
- **현상**: `_rate_limit()` 함수와 `asyncio.Semaphore(20)` 동시 사용. 역할 중복으로 혼란.
- **기대**: 하나의 메커니즘으로 통일
- **수정 제안**: Semaphore 기반으로 통일하거나, _rate_limit()만 사용
- **심각도**: 낮음
- **담당**: backend-dev

#### [F2] config.py get_tr_id() WebSocket TR_ID 안전장치 부재
- **파일**: src/config.py:46-54
- **현상**: H0으로 시작하는 WebSocket TR_ID가 이 함수를 통과하면 잘못된 변환 발생
- **기대**: WebSocket TR_ID는 변환 제외 또는 별도 매핑
- **수정 제안**: `if base_tr_id.startswith("H0"): return base_tr_id` 추가
- **심각도**: 낮음 (현재 실제 경로에서 호출되지 않으나 방어적 코딩)
- **담당**: backend-dev

---

## Task #16: 주문 흐름 E2E 테스트

### 통과 항목 (7건)
- [x] 16-1. 매수 주문 URL/TR_ID 정확 ✓ (order.py:21,33)
- [x] 16-1. Request body 필드 일치 ✓ (order.py:35-42)
- [x] 16-1. Response 파싱 ODNO, ORD_TMD ✓ (order.py:48-51)
- [x] 16-3. 잔고조회 URL/TR_ID/파라미터 정확 ✓ (balance.py:15,21-33,35)
- [x] 16-3. output1 파싱 (pdno, hldg_qty, pchs_avg_pric 등) ✓ (balance.py:37-50)
- [x] 16-3. output2 파싱 (dnca_tot_amt, tot_evlu_amt, nass_amt) ✓ (balance.py:53-63)
- [x] 16-4. 매수가능조회 URL/TR_ID/파싱 정확 ✓ (balance.py:68-87)

### 실패 항목 (7건)

#### [F3] TradeStatus CANCELLED 상태 누락
- **파일**: src/models/trade.py:14-18
- **현상**: TradeStatus enum에 PENDING, COMPLETED, PARTIAL만 존재
- **기대**: CANCELLED 추가 (잔량 취소 시 상태)
- **수정 제안**: `CANCELLED = "CANCELLED"` 추가
- **심각도**: 높음
- **담당**: backend-dev

#### [F4] 체결통보 AES 복호화 미적용
- **파일**: src/realtime/handler.py:70-93
- **현상**: 실전 체결통보는 AES-256-CBC 암호화. 복호화 없이 파싱 시도.
- **기대**: encrypt 플래그 "1"이면 decrypt_aes_cbc() 호출 후 파싱
- **수정 제안**: websocket.py:185의 _encrypt_flag를 handler에 전달, 분기 처리
- **심각도**: 높음 (실전 전환 시 전면 장애)
- **담당**: backend-dev

#### [F5] 부분 체결 판별 로직 부재
- **파일**: src/engine/order_engine.py:121-150
- **현상**: handle_execution_notice()가 항상 COMPLETED로 업데이트
- **기대**: 주문수량 vs 체결수량 비교, 불일치 시 PARTIAL 기록
- **수정 제안**: Position에 ordered_qty 필드 추가, 누적 체결수량과 비교
- **심각도**: 중간
- **담당**: backend-dev

#### [F6] 매도 실패 시 재시도 미구현
- **파일**: src/engine/order_engine.py:117-119
- **현상**: execute_sell() except에서 로그만 남김
- **기대**: 최대 3회 재시도, 전패 시 system_logs ERROR 기록
- **수정 제안**: for attempt in range(3) 루프, write_log("ERROR", ...) 추가
- **심각도**: 높음 (손절 실패 = 추가 손실)
- **담당**: backend-dev

#### [F7] 중복 매수 차단: 동시 보유 4종목 제한 미구현
- **파일**: src/engine/order_engine.py:33-82
- **현상**: 동일종목 중복만 차단, 포지션 수 제한 없음
- **기대**: len(state.positions) >= 4 이면 매수 차단
- **수정 제안**: execute_buy() 상단에 조건 추가
- **심각도**: 중간
- **담당**: backend-dev

#### [F8] 체결통보 필드 인덱스 오류 가능성
- **파일**: src/realtime/handler.py:86-90
- **현상**: fields[17]을 ticker로 사용. KIS 스펙에서 인덱스 17은 "종목명"일 수 있음.
- **기대**: 종목코드(ticker) 추출 정확성 확인
- **수정 제안**: KIS 체결통보 필드 매핑 재확인. 종목코드 필드 인덱스로 수정.
- **심각도**: 중간
- **담당**: backend-dev

#### [F9] 페이징 응답에 total 미포함
- **파일**: src/routes/history.py:12-23
- **현상**: 응답에 total(전체 건수) 없음
- **기대**: `{"trades": [...], "page": 1, "size": 20, "total": 150}`
- **수정 제안**: Supabase count 쿼리 추가, 응답에 total 포함
- **심각도**: 중간
- **담당**: backend-dev

---

## Task #18: 매매 안전성 테스트

### 통과 항목 (3건)
- [x] 18-1. 매수 조건 시가 대비 +29.5% 계산 정확 ✓ (strategy.py:70-71, BUY_THRESHOLD=29.5)
- [x] 18-2. 손절 기준 "매수 체결가" 대비 -7.5% 정확 ✓ (strategy.py:91, STOP_LOSS_RATE=-7.5, pos.buy_price 사용)
- [x] 18-1. 비중 계산 25% 정확 ✓ (strategy.py:140, POSITION_RATIO=0.25)

### 실패 항목 (4건)

#### [F10] 09:00 익일 청산 트리거 누락
- **파일**: src/engine/scheduler.py:45-89
- **현상**: start()에서 _boot() 후 바로 스캔. 09:00 청산 실행 없음.
- **기대**: 09:00에 is_next_day=True 포지션 시가 확인 → 갭상승 판단 → 즉시매도/트레일링스탑
- **수정 제안**: `await self._wait_until(time(9,0))` + `_execute_next_day_clear()` 추가
- **심각도**: 높음 (익일 청산 전체 미작동)
- **담당**: backend-dev

#### [F11] 일일 최대 손실 5% 제한 미구현
- **파일**: src/engine/risk.py
- **현상**: 규칙 명세 8항 일일 손실 한도 미구현
- **기대**: 전체 포지션 평가손실이 총 투자대금의 5% 초과 시 당일 매매 중단
- **수정 제안**: on_tick()에서 전체 손실률 계산, 5% 초과 시 buy_disabled 플래그
- **심각도**: 중간
- **담당**: backend-dev

#### [F12] 15:20 신규 매수 중단 미구현
- **파일**: src/engine/scheduler.py
- **현상**: 규칙 명세 15:20 이후 매수 중단 미구현
- **수정 제안**: TIME_BUY_CUTOFF = time(15, 20) 정의, buy_disabled 플래그
- **심각도**: 중간
- **담당**: backend-dev

#### [F13] 트레일링 스탑 고점 이중 갱신
- **파일**: src/engine/strategy.py:123 + src/engine/risk.py:39
- **현상**: 두 곳에서 high_since_buy 갱신
- **기대**: 한 곳에서만 갱신
- **수정 제안**: strategy.py:123 제거 (risk.py:39에서만 갱신)
- **심각도**: 낮음 (동작에 영향 없으나 코드 명확성 저하)
- **담당**: backend-dev

---

## 미검증 (2건)
- [ ] 체결통보 필드 인덱스 정확성 (실제 WS 데이터로 확인 필요)
- [ ] Supabase 스키마와 pydantic 모델 필드 일치 (DB 마이그레이션 파일 미확인)

---

## Task #17: FastAPI↔React 경계면 검증

### 통과 항목 (10건)
- [x] 17-1. POST /api/trading/start URL 매칭 ✓
- [x] 17-1. POST /api/trading/stop URL 매칭 ✓
- [x] 17-1. GET /api/trading/status URL 매칭 ✓
- [x] 17-1. GET /api/balance URL 매칭 ✓
- [x] 17-1. GET /api/history?page=&size= URL+파라미터 매칭 ✓
- [x] 17-1. GET /api/performance/summary URL 매칭 ✓
- [x] 17-1. GET /api/performance/daily?days= URL+파라미터 매칭 ✓
- [x] 17-1. GET /api/performance/monthly URL 매칭 ✓
- [x] 17-2. BalanceData: Holding 필드 10개 + BalanceSummary 필드 7개 완전 일치 ✓
- [x] 17-2. TradingStatusData (running, positions, pending_buys, position_tickers) 일치 ✓

### 실패 항목 (2건)

#### [F14] trading start/stop 응답 타입 불일치
- **파일**: frontend/src/api/trading.ts:11,15 + src/routes/trading.py:13,22
- **현상**: FastAPI는 `ApiResponse` (success+data+message) 반환, React는 `ActionResult` (success+message만) 타입으로 수신
- **기대**: 양쪽 타입 일치
- **수정 제안**: React의 startTrading/stopTrading을 `ApiResponse<null>` 타입으로 변경하거나, ActionResult에 data 필드 추가
- **심각도**: 낮음 (JS에서 추가 필드는 무시되므로 런타임 오류 없음, 타입 안전성만 저하)
- **담당**: frontend-dev

#### [F15] PerformanceCard 일평균 수익률 색상 기준 오류
- **파일**: frontend/src/components/PerformanceCard.tsx:38
- **현상**: 일평균 수익률 카드의 색상이 `profitColor(data.total_profit_rate)` 기준 — 누적 수익률 기준으로 색상 결정
- **기대**: 각 카드의 색상은 해당 값 기준 (일평균은 `data.avg_daily_profit_rate` 기준)
- **수정 제안**: `card.colored` 분기에서 각 카드의 실제 값으로 profitColor 호출
- **심각도**: 중간 (시각적 오류 — 누적 음수+일평균 양수 시 일평균도 파란색)
- **담당**: frontend-dev

### 참고 (기존 이슈 연동)
- 페이징 total 미포함 [F9]: 양쪽 모두 total 없음. 프론트는 `trades.length < size`로 다음 페이지 판단(TradeHistoryGrid.tsx:102). 마지막 페이지가 정확히 size개이면 빈 페이지로 이동 가능.
- TradeRecord 타입 `{ [key: string]: unknown }`: 동적 컬럼 처리로 의도적 설계이나 타입 안전성 낮음.

## KIS API 스펙 교차 비교 결과
| API | URL | TR_ID | 코드 일치 |
|-----|-----|-------|----------|
| 주식주문(현금) | /uapi/domestic-stock/v1/trading/order-cash | TTTC0012U/TTTC0011U | ✓ |
| 주식주문(정정취소) | /uapi/domestic-stock/v1/trading/order-rvsecncl | TTTC0013U | ✓ |
| 주식잔고조회 | /uapi/domestic-stock/v1/trading/inquire-balance | TTTC8434R | ✓ |
| 매수가능조회 | /uapi/domestic-stock/v1/trading/inquire-psbl-order | TTTC8908R | ✓ |
| 체결통보(WS) | H0STCNI0 / H0STCNI9(모의) | ✓ (handler.py:41) | ✓ |
| 실시간체결가(WS) | H0STCNT0 | ✓ (handler.py:39, scanner.py:20) | ✓ |
