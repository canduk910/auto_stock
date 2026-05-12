# E2 — WebSocket 구독 거절 감지 강화 (Red 의도 기록)

작성일: 2026-05-12
범위: E2만. E1 완료/E3 별도. 재시도 큐 미구현. `subscribe()` 시그니처 불변. git commit/push 금지.

## 결함
`src/realtime/websocket.py::_handle_raw()` JSON 응답 분기(line 196-203)가 `msg1` 의 `"ERROR"` 단일 키워드만 매칭. KIS 거절 응답 변형(예: "이미 등록", "한도 초과", `rt_cd != "0"`)을 감지 못 해 `_subscriptions` set 에 거절된 구독이 잔류 → silently drop 사실 자체를 운영 가시화 못 함.

## 거절 판정 (하나라도 매칭)
1. **rt_cd != "0"** — `body.get("rt_cd")` 가 `None` 이면 skip (Heartbeat/실시간 데이터)
2. **msg1 키워드 (대소문자 무시)**: ERROR / FAIL / REJECT / NOT ALLOWED / LIMIT / EXCEED / DUPLICATE / 한도 / 초과 / 이미 / 중복 / 허용되지 / 권한

## 거절 처리
- `self._subscriptions.discard((tr_id, tr_key))` (멱등)
- ERROR 로그: `"WebSocket 구독 거절: tr_id=%s, tr_key=%s, rt_cd=%s, msg_cd=%s, msg=%s"`
- `write_log("ERROR", "[ws_subscribe_reject] tr_id=... tr_key=... rt_cd=... msg_cd=... msg1=...")` — fire-and-forget, 실패 무시
- 거절 분기 후 조기 return — 정상 SUBSCRIBE SUCCESS AES 키 저장 흐름과 분리

## Red 케이스 (9개)
- A: rt_cd="1", msg_cd="OPSP0007", msg1="이미 등록된 종목입니다" → 거절 처리
- B: rt_cd="1", msg_cd="OPSP****", msg1="구독 한도 초과" → 거절 처리
- C: rt_cd="0", msg_cd="OPSP0000", msg1="SUBSCRIBE SUCCESS" + output iv/key → 정상, discard 없음, AES 저장
- D: msg1="ERROR..." 대문자 (회귀 보호) → 거절 처리
- E: msg1="FAIL TO SUBSCRIBE" → 거절 처리
- F: msg1="한도 초과" (한국어) → 거절 처리
- G: tr_id="PINGPONG" raw → 거절 처리 안 됨, _subscriptions 영향 없음
- H: 비-JSON `"0|H0UNCNT0|001|005930^..."` → JSON 분기 미진입, _subscriptions 영향 없음
- I: 같은 (tr_id, tr_key) 거절 응답 2회 → discard 멱등, 예외 없음

## 안전 불변식
- E1: `MAX_SUBSCRIPTIONS=41` / `bypass_limit` / 우선순위 큐 — 영향 없음
- 정상 응답 AES iv/key 저장 흐름 — 영향 없음
- Heartbeat(PINGPONG) echo / 비-JSON 캐럿 구분 데이터 분기 — 영향 없음
- A `_reprepare_breakout_if_empty` / B `source_counts` / C 매도 폴백 / D `ticker_last_tick` — 무관
- Phase G NXT 사전 판별 / 1주 폴백 — 무관

## 진실의 원천
`_workspace/00_leader_trading_rules.md` "WebSocket 구독 거절 감지" 절
