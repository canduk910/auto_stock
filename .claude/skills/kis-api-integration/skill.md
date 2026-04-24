---
name: kis-api-integration
description: "한국투자증권(KIS) OpenAPI 연동 코드를 구현하는 스킬. OAuth 인증, REST API 주문/조회, WebSocket 실시간 시세/체결통보, 조건검색, Rate Limit 관리를 포함한다. FastAPI 서버에서 KIS API를 호출하는 모든 백엔드 코드에 이 스킬을 사용할 것. KIS API, 한국투자증권, 주식 주문, 잔고 조회, 실시간 시세, WebSocket, 토큰 발급, TR_ID 등을 언급하면 반드시 이 스킬을 참조한다."
---

# KIS OpenAPI 연동 스킬

한국투자증권 OpenAPI를 Python(FastAPI + Asyncio)으로 연동하는 백엔드 코드를 구현한다.

## API 스펙 참조 방법

KIS API 상세 스펙은 `docs/kis/` 디렉토리에 카테고리별로 정리되어 있다:
- 전체 목록 및 프로젝트 사용 API: `docs/kis/README.md`
- 카테고리별 상세 스펙: `docs/kis/{category}.md`

구현 전 반드시 해당 API의 상세 스펙을 Read로 확인한다. 스펙에 있는 TR_ID, URL, Request/Response Example을 기준으로 구현한다.

## 환경 설정

```python
# .env 파일로 관리 (절대 코드에 하드코딩하지 않음)
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...        # 계좌번호 (8자리)
KIS_ACCOUNT_PRODUCT=01    # 계좌상품코드
KIS_ENV=vts               # vts(모의) 또는 real(실전)

# 도메인 자동 결정
REAL_DOMAIN = "https://openapi.koreainvestment.com:9443"
VTS_DOMAIN = "https://openapivts.koreainvestment.com:29443"
```

## 핵심 구현 패턴

### 1. 토큰 관리
- `/oauth2/tokenP`로 접근토큰 발급
- 만료 시각 저장, API 호출 전 만료 여부 확인
- 만료 10분 전 자동 갱신, 실패 시 재발급
- 토큰은 메모리 + 파일 캐시 (재시작 시 복구)

### 2. REST API 공통 래퍼
모든 KIS REST API 호출은 공통 래퍼를 통해 수행한다:
- 헤더 자동 구성: `authorization`, `appkey`, `appsecret`, `tr_id`, `custtype("P")`
- Rate Limit 준수: `asyncio.Semaphore` 기반 초당 20건 제한
- 응답 공통 처리: `rt_cd == "0"` 성공, 그 외 에러 (`msg_cd`, `msg1` 로깅)
- 자동 재시도: 네트워크 오류 시 최대 3회, 지수 백오프
- 토큰 만료(rt_cd 에러) 시 자동 갱신 후 재시도

### 3. WebSocket 실시간 처리
```
연결 → 접속키 발급(/oauth2/Approval) → 구독 등록(tr_id + tr_key)
→ 메시지 수신 → 파이프(|) 구분 파싱 → 핸들러 디스패치
→ Heartbeat 모니터링 → 끊김 시 자동 재연결
```

- 실시간 체결통보(H0STCNI0)는 AES-256-CBC 복호화 필요 (접속 시 받는 iv, key 사용)
- 최대 40개 종목 동시 구독
- Heartbeat 미수신 시 30초 후 재연결 시도 (최대 5회, 지수 백오프)

### 4. 주문 안전 장치
- 주문 전 매수가능금액(`TTTC8908R`) 사전 조회
- 전략별 비중에 따른 수량 계산 (strategy.calc_buy_quantity)
- 전략 간 동일 종목 중복 주문 차단 (registry.is_ticker_held_by_any)
- 부분 체결 감지 → PARTIAL 상태 기록 → 잔여 물량 추적/취소
- 모든 주문에 strategy_id 태깅 → 체결통보에서 올바른 전략에 라우팅

### 5. 다중 전략 매매 엔진

매매 전략은 `src/engine/strategy_base.py`의 StrategyBase를 상속하여 구현한다.
각 전략의 매수/청산 로직은 `_workspace/00_leader_trading_rules.md` 명세를 따른다.

```python
# RiskManager.on_tick() — 전략 레지스트리 순회
for strategy in registry.enabled():
    # 청산 신호 확인
    signal = strategy.check_exit_signal(ticker, current_price, open_price)
    if signal != Signal.NONE:
        await order_engine.execute_sell(ticker, signal, strategy.strategy_id)
    # 매수 신호 확인
    signal = strategy.check_buy_signal(ticker, current_price, open_price)
    if signal == Signal.BUY:
        await order_engine.execute_buy(ticker, current_price, strategy)
```

## 프로젝트 사용 API 빠른 참조

| 기능 | TR_ID | 스펙 파일 |
|------|-------|----------|
| 토큰 발급 | - | `docs/kis/oauth.md` |
| WebSocket 접속키 | - | `docs/kis/oauth.md` |
| 국내 현금 주문 | TTTC0011U(매도)/0012U(매수) | `docs/kis/domestic-stock-order.md` |
| 국내 주문 정정취소 | TTTC0013U | `docs/kis/domestic-stock-order.md` |
| 국내 잔고 조회 | TTTC8434R | `docs/kis/domestic-stock-order.md` |
| 국내 매수가능 조회 | TTTC8908R | `docs/kis/domestic-stock-order.md` |
| 실시간 체결통보 | H0STCNI0 | `docs/kis/domestic-stock-realtime.md` |

> 각 API의 Request/Response 상세는 반드시 해당 스펙 파일을 Read하여 확인한다.

## Supabase 연동

- `supabase-py` SDK 사용
- 거래 실행 시 `trade_history`에 즉시 INSERT
- 체결 확인 시 status 업데이트 (PENDING → COMPLETED 또는 PARTIAL)
- 16:10 정산 시 `daily_performance`에 당일 실적 INSERT
- 에러/이벤트 발생 시 `system_logs`에 기록
