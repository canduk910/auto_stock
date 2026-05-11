# CLAUDE.md — src/api/ (KIS REST API)

KIS OpenAPI REST 호출 모��. 모든 호출은 base.py의 공통 래퍼를 통한다.

## 모듈별 역할

### base.py — 공통 래퍼
- `kis_request(method, url, tr_id, ...)`: 모든 KIS API 호출의 단일 진입점
- 헤더 자동 구성: authorization, appkey, appsecret, tr_id, custtype("P")
- Rate Limit: `asyncio.Semaphore` 기반 초당 20건 제한
- 에러 처리: `rt_cd != "0"` 시 msg_cd + msg1 로깅
- 자동 재시도: 네트워크 오류 최대 3회, 지수 백오프(`BACKOFF_BASE=0.5s × 2^(attempt-1)`) + jitter(`0~BACKOFF_JITTER=0.25s` random) — thundering herd 완화
- 토큰 만료 감지 시 자동 갱신 후 재시도
- 호출 메트릭: `_request_metrics`(전역 dict)에 total/http_5xx/http_4xx/network_err/kis_error/retries + path별 5xx 카운트 누적. `get_request_metrics()` 스냅샷 / `reset_request_metrics()` 리셋. 일일 로그 분석(`log_analysis_engine.py`)이 20:10 INSERT 후 reset 호출
- **거부 응답 영구 저장(Phase A1)**: `rt_cd != "0"` 시 `KisApiError` raise 직전에 `system_logs.write_log("ERROR", "[kis_rejection] path=... tr_id=... msg_cd=... msg1=... body={PDNO/ORD_DVSN/ORD_UNPR/ORD_QTY/EXCG_ID_DVSN_CD/SLL_BUY_DVSN_CD}")` fire-and-forget 호출. 민감 키(CANO/ACNT_PRDT_CD) 마스킹. `write_log` 예외는 swallow — raise 흐름 보존. 운영 trace를 영구 보존해 새 거부 사례(예: "시장가매매불가") 진단 자료 누적. `docs/kis/error-codes.md` 4절 참조.

### order.py — 주문
- 현금 매수: TTTC0012U, 매도: TTTC0011U
- 정정/취소: TTTC0013U
- `settings.get_tr_id()`로 모의/실전 자동 변환
- `place_order(..., exchange="KRX")` / `cancel_order(..., exchange="KRX")`: 거래소ID 구분(`EXCG_ID_DVSN_CD`) body 필드. `KRX`(기본) / `NXT` / `SOR`. 모의투자(VTS)는 KRX만 허용 — SOR/NXT는 실전 한정. 호출자 미지정 시 KRX로 동작(후방 호환)
- **매수 지정가 분기**: 그동안 매수는 항상 시장가(`price=0`)로 호출됐으나, `order_engine.execute_buy`가 "시장가매매불가" 거부 폴백 시 `place_order(side=BUY, price=fallback_price>0, order_division=LIMIT, exchange=...)` 조합으로 호출. body는 `ORD_DVSN=order_division.value`, `ORD_UNPR=str(price)`로 그대로 직렬화 — 매도 지정가와 동일 경로, 추가 보정 불필요.

### balance.py — 잔고/조회
- 잔고조회: TTTC8434R
- 매수가능조회: TTTC8908R
- `get_balance(afhr_flpr="N")`: `AFHR_FLPR_YN` query param. `N`(기본, 정규장) / `Y`(시간외 단일가) / `X`(NXT 정규장) — required
- `get_daily_orders(target_date="", exchange="ALL")`: TTTC0081R 주식일별주문체결조회. `EXCG_ID_DVSN_CD` query param required — `ALL`(기본, KRX+NXT+SOR 합산) / `KRX` / `NXT` / `SOR`. KIS 명세 갱신(2026-05-08)에서 required로 강제 — NXT 체결 누락 방지 위해 기본값 ALL
- `is_market_closed_rejection(KisApiError) -> bool`: KIS 응답이 '장운영시간 외' / '매매 불가 시간' / '거래시간 외' 류의 시간 거부인지 판단. KIS 가 동일 `msg_cd=APBK0918` 로 보유부족·자금부족·시간외 거부를 모두 내보내므로 msg1 키워드(`_MARKET_CLOSED_KEYWORDS`)로 분리. NXT 프리/애프터에서 시장가 매도가 거부될 때 이 함수가 True 면 `is_insufficient_*` 는 False 로 떨어져 positions 보존 결정에 사용된다.
- `is_insufficient_cash(KisApiError) -> bool`: 매수 실패 응답이 '주문가능금액 부족'(예수금 부족) 사유인지 식별. msg_cd 화이트리스트(APBK0919/EGW00120) + msg1 키워드("부족" + "주문가능금액/예수금/현금") 동시 검사. `APBK0918` 은 시간외 거부와 공용이라 msg1 현금 키워드가 동반될 때만 True. OrderEngine 매수 락 결정용.
- `is_insufficient_quantity(KisApiError) -> bool`: 매도 실패 응답이 '매도가능수량 부족'(보유 부족) 사유인지 식별. msg1 키워드("부족" + "매도가능/보유수량/잔고") 가드 + `APBK0918` 은 보유부족 키워드가 동반될 때만 True. 시간외 거부에서는 False 로 떨어져 메모리/DB positions 보존. 매도 즉시 break 결정용.
- `is_market_order_disallowed(KisApiError) -> bool`: KIS 응답이 '시장가매매불가' 류의 거부인지 판단. msg1 키워드(`_MARKET_ORDER_DISALLOWED_KEYWORDS`: "시장가매매불가" / "시장가 매매 불가" / "시장가 주문 불가" / "시장가 호가 불가")로 매칭. 기존 3종 분류와 **상호 배타** — 이 함수가 True 이면 다른 3종은 모두 False. `execute_buy`가 이 거부에 대해 `step_up(current_price, 5)` 가격으로 지정가 1회 폴백을 시도한다. msg_cd 는 운영 trace 누적 후 화이트리스트화 예정. 2026-05-11 계양전기 사례 대응 (`docs/kis/error-codes.md` 4-2절).

### condition.py — 조건검색 + 영업일 체크
- 거래량순위 API로 종목 필터링 (FHPST01700000)
- 시총/거래대금 필터 적용
- `is_market_open(date)`: KIS chk-holiday API(CTCA0903R)로 개장일 여부 (`opnd_yn == "Y"`)
- `next_trading_day(after_date)`: 다음 개장일 조회 (휴일 다음날 자동 산정)
- `fetch_daily_candles(ticker, days)`: 일봉 N영업일치 조회. **`FHKST03010100`(`/quotations/inquire-daily-itemchartprice`, 모의/실전 동일 TR_ID) 사용 — 단일 호출당 최대 100일 응답**. 이전 `FHKST01010400`(`inquire-daily-price`)은 약 30일로만 응답이 제한되어 60일 EMA 사용처(donchian_swing)에서 모든 종목이 길이 컷에 탈락하던 결함을 차단. 응답은 `output2` 배열(최신순), `stck_bsop_date`가 비어있는 placeholder 행은 제거하여 반환. 달력일 윈도우는 영업일/달력일 비율(5/7) + 마진 = `days + days//2 + 10`

## 새 API 추가 절차
1. `docs/kis/{category}.md`에서 TR_ID, URL, 파라미터 확인
2. 이 디렉토리에 함수 추가 (반드시 `kis_request()` 사용)
3. TR_ID�� `settings.get_tr_id("실전TR_ID")` 사용
4. 응답 ��델은 `models/`에 pydantic으��� 정���
