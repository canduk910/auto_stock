# G 단계 작업 지시서 — WebSocket 구독 가시성 강화

> 팀장 작성. KIS WebSocket 구독 슬롯 사용현황을 운영자가 실시간으로 확인할 수 있도록
> 우리 측 도구를 강화한다. KIS REST/WS 어디에도 슬롯 조회 API가 없음(KIS MCP 확인 완료).

## 한 줄 요약
(1) SUBSCRIBE SUCCESS 응답 카운트 별도 추적(G1)
(2) `/api/realtime/subscriptions` 진단 endpoint 노출(G2)
(3) `/api/trading/status` scan 응답에 tick_coverage 4종 키 + ScanMonitor 색상 표시(G3)

## 사전 조사 결과 (팀장 확인)
- `_subscriptions: set[tuple[str, str]]` — websocket.py:77
- `_handle_raw` JSON 분기 — websocket.py:299~ (rt_cd != "0" 거절 분기 + AES 키 저장 분기 존재. **정상 응답 카운트 추적 미존재**)
- `get_subscribed_tickers()` — websocket.py:174 (TICK_TR_ID 필터)
- `ticker_last_tick: dict[str, datetime]` — scanner.py (Phase D)
- `scheduler._report_tick_coverage()` — scheduler.py:1442 (5분 주기 INFO 로그, 키 노출 안 함)
- `scheduler.get_status()` `scan` 필드 = `get_scan_status()` — scheduler.py:572
- `frontend/src/types/trading.ts::ScanStatus` — `subscribed_count` 존재
- `frontend/src/components/ScanMonitor.tsx:219` — `subscribed_count` 표시
- `MAX_SUBSCRIPTIONS = 41` — websocket.py:29

## G1 — SUBSCRIBE SUCCESS 응답 카운트 별도 추적

### 데이터 모델
- `KisWebSocket._subscriptions_acked: set[tuple[str, str]]` 신규 (`__init__`)
- 우리가 발송한 `_subscriptions` 와 분리. KIS가 정상 응답 보낸 구독만 add

### 응답 감지 (`_handle_raw` JSON 분기)
거절 분기(`_is_rejection_response`) **이후**, AES 키 저장 분기 **함께**:
```
정상 응답 판정: rt_cd == "0" AND ("SUBSCRIBE SUCCESS" in msg1.upper())
→ self._subscriptions_acked.add((tr_id, tr_key))
→ logger.info("WebSocket 구독 ACK: tr_id=%s, tr_key=%s", tr_id, tr_key)
```
- AES 키 저장 분기는 첫 응답에만 발생 → ACK 처리는 별도 조건으로 (둘 다 동일 응답에서 발화 가능, 충돌 없음)
- `rt_cd` 가 None/빈문자열인 경우 ACK 처리 안 함 (KIS 정상 응답은 항상 rt_cd="0" 포함)

### 라이프사이클
- `subscribe(tr_id, tr_key, bypass_limit=False)`: 호출 시 `_subscriptions_acked.discard((tr_id, tr_key))` — 응답 도착 전엔 ack 안 됨
- `unsubscribe(tr_id, tr_key)`: 호출 시 `_subscriptions_acked.discard((tr_id, tr_key))` — 동기
- E2 거절(`_is_rejection_response`): 기존 `_subscriptions.discard` 옆에 `_subscriptions_acked.discard` 추가 (이미 거절은 ack 아님)
- 재연결: `connect()` 의 기존 구독 복원 직전 `_subscriptions_acked.clear()` — 모든 구독이 다시 ack 받아야 함

### 헬퍼
- `get_acked_tickers() -> set[str]`: `get_subscribed_tickers()` 패턴 동일, TR_ID==TICK_TR_ID 필터링한 ack set 반환

## G2 — `/api/realtime/subscriptions` 진단 endpoint

### 파일
- 신규 `src/routes/realtime.py` 작성
- `src/main.py` 에 router include 추가 (다른 라우터와 동일 패턴)

### 라우터 정의
- prefix: `/api/realtime`, tags=["realtime"]
- GET `/subscriptions` → `ApiResponse[dict]`

### 응답 데이터 (KST 기준)
```
total            = len(kis_ws.get_subscribed_tickers())
acked            = len(kis_ws.get_acked_tickers())
limit            = websocket.MAX_SUBSCRIPTIONS
ws_connected     = kis_ws._ws is not None
reconnect_count  = kis_ws._reconnect_count

# fresh/stale: scanner.ticker_last_tick 기준, 최근 60s 내 갱신
subscribed_set = kis_ws.get_subscribed_tickers()
now = datetime.now(_KST_TZ)
threshold = timedelta(seconds=60)
fresh_tickers = {t for t in subscribed_set if (now - ticker_last_tick.get(t, min_dt)) <= threshold}
stale_tickers = subscribed_set - fresh_tickers
fresh_60s = len(fresh_tickers)
stale_60s = len(stale_tickers)

# tickers (모두 sorted)
tickers.subscribed = sorted(subscribed_set)
tickers.acked      = sorted(kis_ws.get_acked_tickers())
tickers.fresh      = sorted(fresh_tickers)
tickers.stale      = sorted(stale_tickers)
```

### 응답 스키마 (ApiResponse 래퍼)
```python
{
  "success": True,
  "data": {
    "total": 27,
    "acked": 25,
    "fresh_60s": 23,
    "stale_60s": 4,
    "limit": 41,
    "tickers": {
      "subscribed": [...],
      "acked":      [...],
      "fresh":      [...],
      "stale":      [...]
    },
    "reconnect_count": 3,
    "ws_connected": True
  },
  "message": ""
}
```

### 인증
- 다른 운영 endpoint 와 동일 정책 (인증 가드 없음 — 현재 코드 정책 그대로)

### ws_connected=False 처리
- `_ws is None` 인 경우에도 정상 응답 200 반환
- `total/acked/fresh_60s/stale_60s` 는 데이터 그대로 노출 (set 은 메모리에 유지될 수 있음)

## G3 — `/api/trading/status` 응답 + ScanMonitor 색상 표시

### 백엔드 — `scheduler.get_scan_status()` 가 아니라 `scanner.get_scan_status()` 임 (scheduler.py:518 import)
조사: `scheduler.get_status()` 내부에서 `from src.engine.scanner import get_scan_status` → `scanner.get_scan_status()` 호출.
즉 **수정 위치는 `src/engine/scanner.py::get_scan_status()`**.

추가할 4개 키:
- `tick_coverage_total: int` — `len(kis_ws.get_subscribed_tickers())` (TICK 구독 size)
- `tick_coverage_acked: int` — `len(kis_ws.get_acked_tickers())`
- `tick_coverage_fresh: int` — 최근 60s 내 tick 수신 카운트
- `tick_coverage_stale: int` — 60s 미수신 카운트

기존 `subscribed_count` / `subscribed_tickers` 보존 (호환성).

### 프론트엔드 타입 — `frontend/src/types/trading.ts::ScanStatus`
4개 키 optional 로 추가 (백엔드 미반영 시점 호환):
```ts
tick_coverage_total?: number
tick_coverage_acked?: number
tick_coverage_fresh?: number
tick_coverage_stale?: number
```

### ScanMonitor 표시 — `frontend/src/components/ScanMonitor.tsx:219` 부근
- 기존 `구독 중인 종목: N개` 표시는 보존
- 그 옆/하단에 보조 정보 추가: `fresh: 23 / stale: 4 / acked: 25 / limit: 41` 형식
- 색상:
  - `stale === 0` → 기본 (회색/검정)
  - `1 <= stale <= 5` → 노란색 배지 (Tailwind `bg-yellow-100 text-yellow-800` 등)
  - `stale > 5` → 빨간색 배지 (Tailwind `bg-red-100 text-red-800` 등)
- 진행바(`total / 41`)는 선택. team-leader 판단: **이번 차수에는 노출. 80% 이상이면 amber 톤**으로 한도 근접 가시화. 구현 부담 크면 생략 가능 — 색상 배지를 우선

## 테스트 (Red → Green)

### G1 — `tests/unit/realtime/test_websocket_ack.py` 신규
- **Case A**: `_handle_raw({rt_cd:"0", msg1:"SUBSCRIBE SUCCESS", tr_id:"H0UNCNT0", tr_key:"005930"})` → `_subscriptions_acked` 에 (H0UNCNT0, 005930) 포함 + INFO 로그
- **Case B**: `subscribe("H0UNCNT0","005930")` 직후 `_subscriptions_acked` 에 (H0UNCNT0, 005930) **없음** (응답 도착 전)
- **Case C**: 재연결(`connect` 재진입) 시 `_subscriptions_acked.clear()` 호출됨 — `connect()` 가 기존 구독 복원 직전 (별도 ack flow 가드 가능하면 메서드 단위로 분리)
- **Case D**: E2 거절(`rt_cd!="0"` 또는 `msg1="LIMIT EXCEED"`) → `_subscriptions_acked` 에 추가 안 됨, 기존 add 였으면 discard
- **Case E**: `unsubscribe("H0UNCNT0","005930")` 호출 → `_subscriptions_acked` 에서 discard
- **Case F**: `get_acked_tickers()` 가 TICK_TR_ID 필터링 (H0STCNI0/H0UNMKO0 등 제외) — `get_subscribed_tickers()` 와 동일 패턴

### G2 — `tests/unit/routes/test_realtime_endpoint.py` 신규
TestClient + FastAPI 사용 (다른 routes 테스트 패턴 따름)
- **Case G**: GET `/api/realtime/subscriptions` → 응답 스키마 매칭. `data` 에 `total/acked/fresh_60s/stale_60s/limit/tickers/reconnect_count/ws_connected` 8개 키 모두 존재. `tickers` 에 `subscribed/acked/fresh/stale` 4개 키 존재
- **Case H**: `_subscriptions` 에 `("H0UNCNT0","005930")`, `("H0UNCNT0","000660")` 주입 → `tickers.subscribed = ["000660","005930"]` (정렬됨)
- **Case I**: `kis_ws._ws = None` → 200 + `ws_connected=False` + `total/acked/fresh/stale` 모두 정상 카운트 반환

### G3 백엔드 — `tests/unit/engine/test_get_scan_status_tick_coverage.py` 신규
- **Case J**: `scanner.get_scan_status()` 반환 dict 에 4개 신규 키 모두 존재 (`tick_coverage_total/_acked/_fresh/_stale`)
- **Case K**: 기존 `subscribed_count` 키 보존 — 호환성 회귀 가드

### G3 프론트엔드 — `frontend/src/components/__tests__/ScanMonitor.test.tsx`
기존 파일 존재 여부 확인 후, 없으면 신규. vitest + RTL + MSW (TradingStatusContext 모킹)
- **Case L**: `tick_coverage_stale=0` → stale 배지 노란/빨강 클래스 없음 (기본 톤)
- **Case M**: `tick_coverage_stale=3` → 노란색 배지 (예: `class*=yellow`)
- **Case N**: `tick_coverage_stale=10` → 빨간색 배지 (예: `class*=red`)
- **Case O**: 진행바 구현 시 — `tick_coverage_total=33, limit=41` → 진행바 width 약 80%, amber 톤 (선택)

## 문서 동기화 (구현 완료 후)
- `src/realtime/CLAUDE.md` `websocket.py` 섹션 — `_subscriptions_acked` set + ACK 감지 + `get_acked_tickers()` 1줄
- `src/routes/CLAUDE.md` 표 — `/api/realtime/subscriptions` 1행 추가
- `src/engine/CLAUDE.md` scanner 섹션 — `get_scan_status()` tick_coverage 4개 키 1줄
- `frontend/CLAUDE.md` ScanMonitor 섹션 — tick_coverage 색상 정책 1줄
- 루트 `CLAUDE.md` 핵심 안전 규칙: 추가 불필요
- `README.md` API 엔드포인트 표 — `/api/realtime/subscriptions` 1줄

## 안전 불변식 (보존)
- E1 우선순위 큐 / `MAX_SUBSCRIPTIONS=41` / bypass_limit — 영향 없음
- E2 거절 감지 / `_subscriptions.discard` — G1 add 는 정상 응답에만, E2 와 상호 배타
- D `ticker_last_tick` + `_report_tick_coverage` — G2/G3 read-only 활용
- F1 재연결 후 60s 검증 — 변경 없음. G1 의 `_subscriptions_acked.clear()` 는 재연결 시점에 발화 → 60s 후 F1 이 stale 종목 재구독
- `/api/trading/status` 기존 응답 호환 — `subscribed_count` 보존

## 절대 금지
- git commit/add/push 금지 (사용자 명시까지)
- 인증 가드 추가 금지
- `_subscriptions` set 직접 수정 금지 (G1 은 별도 set)
- `MAX_SUBSCRIPTIONS=41` 변경 금지
- ScanMonitor 기존 `구독 중인 종목: N개` 표시 제거 금지

## TDD 사이클 분배
1. tdd-engineer → Red 테스트 4묶음 작성 (G1 6 / G2 3 / G3 백 2 / G3 프 3~4 = 약 14~15개)
2. backend-dev → G1 + G2 + G3 백엔드 Green 구현
3. frontend-dev → G3 프론트 타입 + ScanMonitor 색상 표시 Green 구현
4. tester → 전체 회귀(pytest + vitest) + 안전 불변식 검증 + 250단어 보고
