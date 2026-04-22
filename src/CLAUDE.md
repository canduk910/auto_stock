# CLAUDE.md — src/ (백엔드)

FastAPI 기��� 백엔드. KIS OpenAPI 연동, 매매 엔진, Supabase DB 연동.

## 실행
```bash
uvicorn src.main:app --reload          # ��발
python -m src.main                      # 직접 실행
```

## 모듈 의존 관계
```
config.py ← (모든 모듈���� settings import)
auth/ ← api/base.py, realtime/websocket.py
api/base.py ← api/order.py, api/balance.py, api/condition.py
api/ ← engine/, routes/
realtime/ ← engine/strategy.py (시세 콜백)
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
- 네트워크 오류 시 3회 재시도 (지수 백오프)
- 토큰 만료 시 자동 갱신 후 재시도

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

### 실시간 데이터 (realtime/)
- WebSocket 접속키: `/oauth2/Approval`로 발급
- 체결통보(H0STCNI0): 실전 환경에서 AES-256-CBC 복호화 필요
- 메시지 포맷: 파이프(|) 구분, 첫 필드가 암호화 여부
- Heartbeat 30초 미수신 시 자동 재연결 (최대 5회)

## 새 KIS API 추가 시 절차
1. `docs/kis/README.md`에서 해당 API의 스펙 파일 확인
2. 스펙 파일에서 TR_ID, URL, Request/Response 확인
3. `api/` 하위에 함수 추가 (반드시 `kis_request()` 사용)
4. `models/` 하위에 응답 모델 추가 (pydantic)
5. 필요 시 `routes/` 하위에 엔드포인트 추가
