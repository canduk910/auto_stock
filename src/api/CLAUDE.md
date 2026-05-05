# CLAUDE.md — src/api/ (KIS REST API)

KIS OpenAPI REST 호출 모��. 모든 호출은 base.py의 공통 래퍼를 통한다.

## 모듈별 역할

### base.py — 공통 래퍼
- `kis_request(method, url, tr_id, ...)`: 모든 KIS API 호출의 단일 진입점
- 헤더 자동 구성: authorization, appkey, appsecret, tr_id, custtype("P")
- Rate Limit: `asyncio.Semaphore` 기반 초당 20건 제한
- 에러 처리: `rt_cd != "0"` 시 msg_cd + msg1 로깅
- 자동 ���시도: 네트워크 오류 최대 3회, 지수 백오프
- 토큰 만료 감지 시 자동 갱신 후 재시도

### order.py — 주문
- 현금 매수: TTTC0012U, 매도: TTTC0011U
- 정정/취소: TTTC0013U
- `settings.get_tr_id()`로 모의/실전 자동 변환

### balance.py — 잔고/조회
- 잔고조회: TTTC8434R
- 매수가능조회: TTTC8908R

### condition.py — 조건검색 + 영업일 체크
- 거래량순위 API로 종목 필터링 (FHPST01700000)
- 시총/거래대금 필터 적용
- `is_market_open(date)`: KIS chk-holiday API(CTCA0903R)로 개장일 여부 (`opnd_yn == "Y"`)
- `next_trading_day(after_date)`: 다음 개장일 조회 (휴일 다음날 자동 산정)

## 새 API 추가 절차
1. `docs/kis/{category}.md`에서 TR_ID, URL, 파라미터 확인
2. 이 디렉토리에 함수 추가 (반드시 `kis_request()` 사용)
3. TR_ID�� `settings.get_tr_id("실전TR_ID")` 사용
4. 응답 ��델은 `models/`에 pydantic으��� 정���
