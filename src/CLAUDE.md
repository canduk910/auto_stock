# CLAUDE.md — src/ (백엔드)

FastAPI 기��� 백엔드. KIS OpenAPI 연동, 매매 엔진, Supabase DB 연동.

## 실행
```bash
uvicorn src.main:app --reload          # ��발
python -m src.main                      # 직접 실행
```

## 모듈 의존 관계
```
config.py ← (모든 모듈에서 settings import)
auth/ ← api/base.py, realtime/websocket.py
api/base.py ← api/order.py, api/balance.py, api/condition.py
api/ ← engine/, routes/
realtime/handler.py ← engine/risk.py(on_tick) + engine/order_engine.py(체결통보) + engine/session.py(보드 전환)
engine/session.py ← engine/risk.py, engine/scheduler.py, engine/strategies/* (현재 보드 query)
engine/ ← routes/trading.py (시작/정지)
db/ ← engine/, routes/
models/ ← (모든 모듈에서 사용)
```

## 주요 패턴

### KIS API 호출
모��� KIS REST API 호출은 `api/base.py`의 `kis_request()`를 통한다:
- 헤더 자동 구성 (authorization, appkey, appsecret, tr_id)
- `asyncio.Semaphore`로 초당 20건 Rate Limit
- `rt_cd != "0"` 시 에러 로��
- 네트워크 오류 시 3회 재시도 (지수 백오프 + 0~0.25s jitter)
- 토큰 만료 시 자동 갱신 후 재시도
- 호출 메트릭(`_request_metrics`): http_5xx/4xx/network_err/kis_error/retries + path별 5xx 카운트. `get_request_metrics()` / `reset_request_metrics()` 노출, 일일 로그 분석에서 사용

### TR_ID 관리
```python
# 올바른 사��� — 환경에 따라 자동 변환
tr_id = settings.get_tr_id("TTTC0012U")  # 실전: TTTC0012U, 모의: VTTC0012U
```
새 API 연동 시 TR_ID를 하드코딩하지 않고 반드시 `settings.get_tr_id()` 사용.

### 주문 안전 장치 (engine/order_engine.py)
- 중복 매수 차단: 동일 종목 미체결/보유 시 주문 거부
- 부��� 체��� 관리: PARTIAL 상태 추적, 30초 후 잔여 취소
- 매도 실패 재시도: 최대 3회, 지수 백오프(1s, 2s, 4s), 실패 시 CRITICAL 로그
- 매수가능 캐시(60초 TTL): `get_buyable()` 결과를 `StrategyState.cached_buyable_qty`에 캐싱 — 매 틱 KIS 호출 → 분당 1회로 축소 (`BUYABLE_CACHE_TTL = 60.0`)
- 잔고부족 매수 락(900초): `is_insufficient_cash()` 응답 또는 `max_buy_quantity<=0` 시 `state.block_buy(now+BUY_BLOCK_DURATION)` — 다음 잔고 sync까지 KIS 호출 자체 차단 (`BUY_BLOCK_DURATION = 900.0`)
- 매도 잔고부족 즉시 break: `is_insufficient_quantity()` 응답 시 3회 재시도 생략 + 메모리 포지션 + DB positions 정리(다음 sync에서 보정)
- 주문번호 매핑 등록 위치: `place_order` 응답 직후 동기 영역(`await insert_trade` 전). 시장가 즉시체결 race 시에도 `_handle_*_fill`이 올바른 strategy_id를 찾도록 보장
- 체결통보 선행 race 가드: `_completed_orders` set으로 응답보다 빨리 도착한 체결통보를 COMPLETED 직접 INSERT 처리, 뒤늦은 응답에서 PENDING INSERT 생략

### 실시간 데이터 (realtime/)
- WebSocket 접속키: `/oauth2/Approval`로 발급
- 체결통보(H0STCNI0): 실전 환경에서 AES-256-CBC 복호화 필요
- 메시지 포맷: 파이프(|) 구분, 첫 필드가 암호화 여부
- Heartbeat 30초 미수신 시 자동 재연결 (최대 5회)
- **시세 채널**: `H0UNCNT0`(KRX+NXT 통합) — `scanner.TICK_TR_ID`. 메시지 포맷은 `H0STCNT0`(KRX 단독)/`H0NXCNT0`(NXT 단독)와 동일 → `handler.dispatch_message`가 셋 다 동일 파서로 처리
- **NXT 장운영정보**: `H0NXMKO0` 실전 한정 구독 → `register_board_handler`로 `SessionTracker.on_h0nxmko0` 콜백 등록 (보드 전환 코드 수신, 명세 미확정으로 현재는 코드 기록만)

### NXT/SOR 통합 (engine/session.py)
- `MarketBoard` enum: `pre_nxt`(NXT 프리 08:00~09:00) / `krx_open`(08:30~09:00) / `main`(09:00~15:20) / `krx_after`(15:30~18:00) / `post_nxt`(NXT 애프터 15:30~20:00)
- `SessionTracker`: 시각 기반 + H0NXMKO0 입력으로 활성 보드 추적. `_session_loop`(scheduler.py 30초 주기)에서 `tick()` 호출
- `is_tradable(strategy_id, params)`: 활성 보드 ∩ 전략 `tradable_boards` ≠ ∅ 인지 — `RiskManager.on_tick`에서 매수 신호 평가 전 가드
- 주문 라우팅: `place_order(..., exchange="KRX"|"NXT"|"SOR")` body에 `EXCG_ID_DVSN_CD`. 모의(VTS)는 KRX만

## 새 KIS API 추가 시 절차
1. `docs/kis/README.md`에서 해당 API의 스펙 파일 확인
2. 스펙 파일에서 TR_ID, URL, Request/Response 확인
3. `api/` 하위에 함수 추가 (반드시 `kis_request()` 사용)
4. `models/` 하위에 응답 모델 추가 (pydantic)
5. 필요 시 `routes/` 하위에 엔드포인트 추가
