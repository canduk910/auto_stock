# QA 테스트 체크리스트

## Task #15: 인증/API 래퍼 테스트 (blocked by #2, #3)

### 15-1. OAuth 토큰 발급
- [ ] POST `/oauth2/tokenP` 요청 파라미터: grant_type, appkey, appsecret
- [ ] 응답 파싱: access_token, access_token_token_expired, token_type, expires_in
- [ ] 토큰 만료 시 자동 갱신 로직 존재
- [ ] 모의투자(VTS) 도메인: `openapivts.koreainvestment.com:29443`
- [ ] 실전 도메인: `openapi.koreainvestment.com:9443`
- [ ] .env의 KIS_ENV에 따라 도메인 전환

### 15-2. WebSocket 접속키 발급
- [ ] POST `/oauth2/Approval` 요청: grant_type, appkey, secretkey
- [ ] 응답 파싱: approval_key

### 15-3. 토큰 폐기
- [ ] POST `/oauth2/revokeP` 요청: appkey, appsecret, token
- [ ] 응답: code 200, message 확인

### 15-4. REST API 공통 래퍼
- [ ] 공통 헤더: authorization(Bearer 토큰), appkey, appsecret, tr_id, custtype
- [ ] Rate Limit: 초당 20건 제한 Semaphore 구현
- [ ] 에러 응답 처리: rt_cd != "0" 시 예외 발생
- [ ] Hashkey 생성: POST `/uapi/hashkey` (POST 요청 시 필요)

### 15-5. 모의/실전 TR_ID 전환
- [ ] 매수: TTTC0012U (실전) / VTTC0012U (모의)
- [ ] 매도: TTTC0011U (실전) / VTTC0011U (모의)
- [ ] 정정취소: TTTC0013U (실전) / VTTC0013U (모의)
- [ ] 잔고조회: TTTC8434R (실전) / VTTC8434R (모의)
- [ ] 매수가능: TTTC8908R (실전) / VTTC8908R (모의)
- [ ] 체결통보 WS: H0STCNI0 (실전) / H0STCNI9 (모의)

---

## Task #16: 주문 흐름 E2E 테스트 (blocked by #7)

### 16-1. 매수 주문 흐름
- [ ] POST `/uapi/domestic-stock/v1/trading/order-cash` 호출
- [ ] Request: CANO, ACNT_PRDT_CD, PDNO(종목코드), ORD_DVSN("01" 시장가), ORD_QTY, ORD_UNPR("0" 시장가)
- [ ] TR_ID: TTTC0012U (매수)
- [ ] Response 파싱: KRX_FWDG_ORD_ORGNO, ODNO(주문번호), ORD_TMD(주문시각)
- [ ] rt_cd "0" 확인

### 16-2. 체결 통보 수신 (WebSocket)
- [ ] H0STCNI0 구독: tr_key = HTS ID
- [ ] 체결 통보 파싱: ^ 구분자로 분리
- [ ] 접수 통보 vs 체결 통보 구분 (output 필드 차이)
- [ ] 체결 시 trade_history INSERT (COMPLETED 상태)

### 16-3. 잔고 조회
- [ ] GET `/uapi/domestic-stock/v1/trading/inquire-balance`
- [ ] TR_ID: TTTC8434R
- [ ] Request: CANO, ACNT_PRDT_CD, AFHR_FLPR_YN, INQR_DVSN, UNPR_DVSN 등
- [ ] output1 파싱: pdno, hldg_qty, pchs_avg_pric, evlu_pfls_amt, evlu_pfls_rt
- [ ] output2 파싱: dnca_tot_amt(예수금), tot_evlu_amt, nass_amt

### 16-4. 매수가능금액 조회
- [ ] GET `/uapi/domestic-stock/v1/trading/inquire-psbl-order`
- [ ] TR_ID: TTTC8908R
- [ ] Response: ord_psbl_cash, max_buy_amt, max_buy_qty
- [ ] 25% 비중 계산: ord_psbl_cash의 25%를 매수금으로 사용

### 16-5. 매도 주문 (손절)
- [ ] POST `/uapi/domestic-stock/v1/trading/order-cash`
- [ ] TR_ID: TTTC0011U (매도)
- [ ] 시장가 전량 매도: ORD_DVSN="01", ORD_UNPR="0"
- [ ] 매수 체결가 대비 -7.5% 조건 정확성

### 16-6. 주문 정정/취소
- [ ] POST `/uapi/domestic-stock/v1/trading/order-rvsecncl`
- [ ] TR_ID: TTTC0013U
- [ ] Request: ORGN_ODNO(원주문번호), RVSE_CNCL_DVSN_CD("01" 정정, "02" 취소)
- [ ] 부분 체결 잔량 취소 (30초 대기 후)

### 16-7. 중복 매수 차단
- [ ] 보유 종목에 대한 매수 시도 차단
- [ ] 미체결 매수 주문 있는 종목 매수 차단
- [ ] 동시 보유 최대 4종목 제한

### 16-8. 부분 체결 처리
- [ ] PARTIAL 상태 trade_history 기록
- [ ] 체결 수량만 잔고 반영
- [ ] 30초 후 잔여 취소 로직
- [ ] 손절 시 부분 체결: 체결분 완료 처리, 잔여 재주문

---

## Task #17: FastAPI <-> React 경계면 검증 (blocked by #11, #12, #13, #14)

### 17-1. 엔드포인트 URL 매칭
- [ ] `/api/trading/start` — POST, 요청/응답 모델 일치
- [ ] `/api/trading/stop` — POST, 요청/응답 모델 일치
- [ ] `/api/balance` — GET, 응답 필드와 React 컴포넌트 바인딩
- [ ] `/api/history` — GET, page/size 쿼리 파라미터
- [ ] `/api/performance/daily` — GET, 차트 데이터 포맷

### 17-2. 응답 모델 <-> TypeScript 타입 교차 비교
- [ ] pydantic 모델 필드명 = TypeScript interface 필드명
- [ ] 타입 호환: str->string, int->number, float->number, bool->boolean
- [ ] Optional 필드 처리 일치
- [ ] 날짜/시간 포맷 일치

### 17-3. 페이징 응답 구조
- [ ] FastAPI 응답: { items: [], total: N, page: N, size: N }
- [ ] React TanStack Table 기대 구조와 매칭
- [ ] page 0-based vs 1-based 일치 확인

### 17-4. 에러 응답
- [ ] HTTPException detail 구조
- [ ] React 에러 핸들링 코드가 detail 구조를 올바르게 파싱

### 17-5. 상태값 ENUM 일치
- [ ] trade_history.status: PENDING, COMPLETED, PARTIAL, CANCELLED
- [ ] FastAPI 응답과 React 렌더링에서 동일 값 사용

---

## Task #18: 매매 안전성 테스트 (blocked by #7, #8)

### 18-1. 매수 조건 정확성
- [ ] 시가 대비 +29.5% 계산: `현재가 >= 시가 * 1.295`
- [ ] 비중 계산: `매수금 = 예수금 * 0.25`
- [ ] 매수 수량: `매수금 / 현재가` (정수 내림)

### 18-2. 손절 트리거
- [ ] 조건: `현재가 <= 매수체결가 * 0.925` (즉, -7.5%)
- [ ] 기준이 "매수 체결가"인지 확인 (시가가 아님!)
- [ ] 즉시 시장가 전량 매도
- [ ] 매도 실패 시 재시도 최대 3회
- [ ] 재시도 실패 시 system_logs 기록

### 18-3. 익일 청산 (09:00)
- [ ] 09:00 정확히 트리거
- [ ] 갭상승 판단: `당일시가 >= 매수체결가 * 1.10` (+10%)
- [ ] 갭상승 Yes: 트레일링 스탑 가동
- [ ] 갭상승 No: 즉시 시장가 전량 매도

### 18-4. 트레일링 스탑
- [ ] 고점 실시간 추적 (당일 시가 이후)
- [ ] 매도 조건: `(고점 - 현재가) / 고점 * 100 >= 2.0`
- [ ] 시장가 매도 트리거

### 18-5. 리스크 관리
- [ ] 종목당 최대 25% 비중 제한
- [ ] 동시 보유 최대 4종목
- [ ] 일일 최대 손실 5% 도달 시 당일 매매 중단
- [ ] 최대 40개 종목 구독 제한

### 18-6. 스케줄러 동작 순서
- [ ] 08:25: 기동 -> 토큰 갱신 -> DB 잔고 동기화
- [ ] 08:30: WebSocket 연결
- [ ] 09:00: 익일 청산
- [ ] 09:30: 종목 필터링 시작
- [ ] 15:20: 신규 매수 중단
- [ ] 15:30: WebSocket 해제
- [ ] 16:10: 정산 -> daily_performance 기록 -> Sleep

### 18-7. Rate Limit 시나리오
- [ ] 초당 20건 Semaphore 제한 구현
- [ ] 여러 종목 동시 손절 시 큐잉 동작
- [ ] 지연된 주문도 순차 실행

### 18-8. 종목 필터링
- [ ] 09:30 이후 5분 주기 필터링
- [ ] 시가총액 >= 1,000억 원
- [ ] 당일 거래대금 >= 200억 원
- [ ] 40개 초과 시 거래대금 상위 우선
