# 사이클 197 — 41-cap 구독 WARNING DailyEmitCap (백로그 A, log-only 관찰성)

## 배경 (사이클 196 효과 실측 중 A 스코프 확정)

`src/realtime/websocket.py::subscribe` L463-464:
```python
if not bypass_limit and len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
    logger.warning("최대 구독 수(%d) 도달, %s/%s 구독 건너뜀", MAX_SUBSCRIPTIONS, tr_id, tr_key)
    return
```
LOW 우선순위(`bypass_limit=False`) 구독이 메인 WS 41슬롯 초과 시 드롭 + WARNING. 5분 scan loop 이
실패한 동일 키(주로 H0UNMKO0 장운영정보 후보)를 **매 사이클 재시도** → 종목당 반복 emit.

### 운영 실측 (Supabase)
- `최대 구독 수(41) 도달, H0UNMKO0/{ticker} 구독 건너뜀` — **7/3 저녁 단일 버스트**(16:41~19:59 NXT
  애프터) ~22 종목 × 각 ~32회 = **~640건/일**. 7/6~7/7 = 0건(candidate 셋 41 미초과, episodic).
- 원 관측 "641 WARNING"의 정체 확정.

### 안전성 (matting 무관 확정)
- **보유/익일청산은 `bypass_limit=True`라 이 분기 미진입** → 절대 드롭 안 됨(사이클 32 R4/149 영속).
  드롭 대상 = LOW 후보의 H0UNMKO0/TICK 구독뿐.
- scanner `[priority_drop]` INFO(scanner.py:972 = 드롭 카운트 요약) + **HIGH 초과 별도 ERROR**
  (`[priority] HIGH 구독 한도 초과`, scanner.py:1045) → 이 L464 WARNING cap 이 매매/경보 신호 **미차단**.
- L464 는 순수 per-subscribe 반복 detail → DailyEmitCap 안전.

## 시정 (log-only, 드롭 행위 byte 불변)

`src/realtime/websocket.py` 단일 함수 + 필드 2 + import 1 + 모듈 상수 1:

1. **import** (top-level, 순환 없음 — `src/engine/__init__.py` 빈 파일 + `daily_emit_cap` 의존성 0):
   `from src.engine.daily_emit_cap import DailyEmitCap`
2. **모듈 상수** (MAX_SUBSCRIPTIONS 인근): `_KST_TZ = timezone(timedelta(hours=9))` (기존 부재 시 추가).
3. **`__init__` 필드** (L130 `_opsp_backoff_until` 인근):
   ```python
   # 사이클 197 — 41-cap WARNING DailyEmitCap (1회/(tr_id,tr_key)/일, 5분 재시도 스팸 억제)
   self._max_sub_warn_cap: DailyEmitCap[tuple[str, str]] = DailyEmitCap()
   self._max_sub_warn_date: str = ""
   ```
4. **L463-465 WARNING 게이트** (드롭 `return` 불변):
   ```python
   if not bypass_limit and len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
       # 사이클 197 — WARNING DailyEmitCap (1회/키/일, KST 자기리셋). 드롭 행위 불변.
       _today = datetime.now(_KST_TZ).date().isoformat()
       if _today != self._max_sub_warn_date:
           self._max_sub_warn_date = _today
           self._max_sub_warn_cap.reset_daily()
       _key = (tr_id, tr_key)
       if self._max_sub_warn_cap.should_emit(_key):
           logger.warning("최대 구독 수(%d) 도달, %s/%s 구독 건너뜀", MAX_SUBSCRIPTIONS, tr_id, tr_key)
           self._max_sub_warn_cap.mark_emitted(_key)
       return
   ```
   - 날짜 계산/cap 조회는 **41-cap 도달 시(rare)에만** 실행 = 정상 subscribe hot path 오버헤드 0.
   - `return`(구독 skip) + `bypass_limit` 분기 + OPSP backoff(L454-461) + add/ack(L466-470) **불변**.

### 불변식 / 함정
- `bypass_limit=True` 는 L463 조건 자체 미진입 → HIGH 보유/익일청산 구독 add 정상 (WARNING·cap 무관).
- WARNING 게이트는 **logger.warning 만** 억제. `_subscriptions.add` 안 함 + `return` = 드롭 행위 동일.
- KST 자기리셋 = scheduler `_reset_daily_state` 배선 불요 (matting-safety 영역 surface 최소).
- `datetime`/`timezone`/`timedelta` 는 websocket.py 기존 import(L16) 재사용.

## 회귀 가드 (신규 `tests/unit/realtime/test_cycle197_max_sub_warn_cap.py`)

- **G-1 (핵심 cap)**: 41 구독 채운 뒤 동일 (H0UNMKO0, "005930") LOW subscribe **5회 반복**(같은 날)
  → `logger.warning` **정확히 1회**(caplog) + 5회 모두 `_subscriptions` 미증가(드롭 유지).
- **G-2 (per-key)**: 41 채운 뒤 서로 다른 키 3개 LOW subscribe → WARNING **3회**(키당 1회).
- **G-3 (KST 자기리셋)**: 동일 키 subscribe → 1회 warning, `_max_sub_warn_date` 를 전일로 강제
  (또는 `datetime` monkeypatch 로 날짜 전진) → 재 subscribe 시 warning 재발(리셋 확인). freezegun
  금지(asyncio.sleep hang 교훈) — `_max_sub_warn_date` 직접 세팅 또는 `websocket.datetime` mock.
- **G-4 (SAFETY, HIGH 보존)**: 41 채운 뒤 `bypass_limit=True` subscribe → WARNING **0회** +
  `_subscriptions` **증가**(드롭 안 함, 보유 절대 보호 사이클 32 R4).
- **G-5 (SAFETY, 드롭 행위 불변)**: LOW subscribe at 41-cap → `_subscriptions` 미증가 + `_send_subscribe`
  미호출(반복 호출해도) = WARNING 게이트와 무관하게 드롭 byte 동일.
- **G-6 (AST)**: L463 분기 본체에 `should_emit`/`mark_emitted` + `return` 동반 존재
  (미래 무한 emit 재도입 영구 차단, `_ast_helpers.py` self-test).

## 의미 전환 (사이클 66 K-2) — tdd-engineer 식별
`grep`으로 기존 realtime 테스트에서 "최대 구독 수" WARNING 을 **매 호출 발생**으로 단언하는 케이스
탐색(주로 subscribe 1회 호출 → 첫 warning 은 cap 통과라 PASS 유지 예상). 동일 키 반복 호출에
warning 반복을 단언하는 테스트가 있으면 의미 전환(1회로). 없으면 회귀 0 명시.

## 검증
- Red 유효성: production 미변경 시 G-1(반복 warning=5) / G-3 FAIL, G-2/G-4/G-5 PASS(불변식).
- 격리 신규 ×2 flakiness 0. 인접 realtime(websocket subscribe/priority/stale) 전수 PASS.
- **매매 안전성 8영역**: realtime/(8영역 中 1) 변경 = WARNING 게이트 + 필드/import 한정 —
  구독 add/skip/return/bypass 로직 byte 불변 직접 diff 검증. 나머지 7영역 diff 0.

## 오케스트레이션
메인 스카우트·실측(완료) → tdd-engineer Red → 메인 세션 Green(matting-safety 정밀) → 메인 검증.
LOW log-only. 커밋/푸시 보류.
