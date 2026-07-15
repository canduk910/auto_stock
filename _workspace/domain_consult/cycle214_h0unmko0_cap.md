# 사이클 214 domain-expert 자문 — H0UNMKO0(장운영정보) 41-cap 초과 드롭 시정

작성: 2026-07-15
요청자: team-leader (사이클 214 발주)
범위: H0UNMKO0 후보 구독 메인 세션 41-cap 초과 → 119건 드롭 시정 옵션 (a)/(b)/(c) 택1
자문 사전 문서: `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md` (재검증 대상)

---

## 질문 요약

유니버스 확대(사이클 203/204/208/211)로 H0UNMKO0 후보 구독이 메인 세션 41-cap 초과 → 119건 드롭
(`최대 구독 수(41) 도달, H0UNMKO0/<ticker> 구독 건너뜀`, 7/14 로그분석 medium finding).

- **(a)** 후보 H0UNMKO0 cap 20→축소 또는 0 (메인 슬롯 확보)
- **(b)** H0UNMKO0 풀 분산(kis_ws_pool) — 보조 세션 205 용량 활용, 후보 손실 0 (cycle 149 "보조 절대 금지" 상충 재검증)
- **(c)** 유지 + 관찰 (실제 영향 낮음, 로그 노이즈만)

---

## 결론 (한 줄)

**(b) 풀 분산 채택 — 단, HIGH(보유/익일청산)는 메인 세션 명시 고정, LOW 후보만 pool.subscribe 로 보조 분산.**
근거: cycle 149 "보조 세션 절대 금지"는 **KIS 정본·코드 정본 양쪽에서 반증**됨. H0UNMKO0 = KIS `실시간시세`
카테고리(체결통보와 별개) + 보조 세션은 코드상 이미 "시세 only" 허용 + `_EXECUTION_NOTICE_TR_IDS`
차단은 H0STCNI0/H0STCNI9 **체결통보만**. H0UNMKO0 는 시세성 read-only 데이터 → 보조 분산은 대칭성 위반 아님.
**(b)가 근본, (a)는 후보 VI 감시를 영구 희생하는 대증요법, (c)는 유니버스가 더 커지면 재발.**

---

## 트레이더 시각

### 시장 가설 — H0UNMKO0 후보 구독은 "손절 방어"가 아니라 "재구독 폭주 방어"

H0UNMKO0(장운영정보)는 종목별 VI 발동/해제·거래정지·종목상태를 실시간 push 한다. 이 신호의 매매적 의미는
**시세 미수신이 "구독 끊김(stale)"인지 "정상 거래중단(VI/halt)"인지 판별**하는 것 — cycle 149 가
047040/475150 ping-pong(정상 VI 종목을 stale 오판 → 강제 재구독 폭주 → KIS LMS chain 위험)을 막으려
도입했다.

- **보유 종목**: H0UNMKO0 상실 시 → VI 걸린 보유 종목을 stale 오판 → 강제 재구독 폭주 = **KIS LMS/앱키 정지 chain 위험** (진짜 위험). 그래서 HIGH bypass 절대 보장 의무 (사이클 32 R4 / 197).
- **후보 종목(미보유)**: H0UNMKO0 상실 시 → VI 후보를 stale 오판 → 재구독 시도. 그러나 이 재구독은
  **bounded**: cycle 197 로그 1회/키/일 cap + cycle 102 force_retry cap(시간당 6회 + 10분 cooldown)이
  이미 폭주를 봉쇄. 게다가 후보는 **미보유 = 손절 대상 아님** → VI 오판이 손익에 직결되지 않음.

즉 후보 H0UNMKO0의 실질 가치는 "재구독 노이즈 억제"이지 "손절 정확성"이 아니다. 이 사실이 (a) cap 축소가
"허용 가능한 축소"로 보이는 이유이자, 동시에 **(b)로 후보 손실 없이 노이즈까지 잡는 게 근본인 이유**다.

### cycle 149 "보조 세션 절대 금지" 근거 재검증 — 반증됨

cycle 149 자문 의제 2의 근거 2가지를 정본으로 재검증:

| cycle 149 근거 | 재검증 결과 | 정본 |
|---|---|---|
| (근거 A) "KIS LMS 한도는 TR 무관 세션당 41" → 보조도 동일 한도 | **부분 참** — 41 한도는 맞음. 그러나 이건 "보조 분산 금지"가 아니라 오히려 **분산해야 할 이유** (보조 세션마다 별도 41 슬롯 = 205 총용량) | websocket_pool.py:201 `total_slots = 41 × (1+N)` |
| (근거 B) "체결통보 메인 단일 패턴과 동일하게 H0UNMKO0도 메인 단일" (대칭성) | **반증** — 체결통보(H0STCNI0/9) 메인 단일은 **AES 키 격리 + 계좌 필터 + 자금 안전** 때문(사이클 16). H0UNMKO0 는 read-only 시세성 데이터로 이런 제약이 전무. 대칭 근거 없음 | 아래 3중 정본 |

**반증 정본 3중**:

1. **KIS 정본(kis-code-assistant MCP)**: `market_status_total`(H0UNMKO0, 국내주식 장운영정보 통합)은
   서브카테고리 **`실시간시세`**에 속함 — `index_exp_ccnl`(예상체결)·`asking_price_total`(호가)·
   `program_trade_total`(프로그램매매)와 **동일 그룹**. 체결통보(`ccnl_notice`)는 별개. → H0UNMKO0 =
   시세성 데이터, 계좌/자금 안전과 무관.

2. **코드 정본(websocket_pool.py:12, 53-72)**: 보조 세션은 명시적으로 **"시세 only (TICK + HOGA +
   예상체결)"** 허용. 차단은 `_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0", "H0STCNI9"})`
   **체결통보 2종뿐**. H0UNMKO0 는 이 frozenset에 **없음** → `WebsocketPool.subscribe`가 이미
   H0UNMKO0를 LOW로 받으면 보조 라운드로빈에 정상 분배(현재 코드 그대로, 신규 예외 불필요).

3. **dispatch 정본(handler.py:69-78, 232-235)**: `dispatch_message`는 **세션 무관 전역 콜백**. 어느
   세션(메인/보조)이 H0UNMKO0 메시지를 받든 `_handle_market_op → record_market_op_event`가 전역
   `market_operation_monitor`의 `_vi_active_tickers`/`_halt_active_tickers` 3 dict를 갱신. →
   **보조 세션으로 분산해도 VI/거래정지 이벤트 소비는 0 영향**(전역 dict, 세션 소속 무관).

**결론**: cycle 149 "보조 절대 금지"는 체결통보 대칭성을 잘못 확장 적용한 과보수(over-conservative)였음.
당시 "구현 시점에 확실히 안전한 쪽"으로 메인 단일을 택한 판단은 **그 시점엔 합리적**(후보 30종목 수준이라
41 cap 미도달 → 분산 불필요 + 검증 비용 회피)이었으나, 유니버스 3배 확대로 전제가 무너진 상태.

### cycle 149 자문이 스스로 남긴 위험 플래그 (의제 2 반례)

cycle 149 의제 2 반례가 이미 예견: *"메인 세션 슬롯 = TICK 41 + 체결통보 1 + H0UNMKO0 시장 1 + 종목별
H0UNMKO0 ≤ 20 = 최대 63 (KIS LMS 한도 41 초과 영역) — bypass_limit=True 가드만 의존"*. 즉 cycle 149는
"메인 단일 + bypass 의존"이 41 초과를 **구조적으로 내포**함을 인지하고도 후보를 `bypass_limit=False`(LOW)로
둬서 초과 시 드롭되게 설계 = **후보 드롭은 설계된 fallback**이었음. 지금 119건 드롭은 버그가 아니라
설계가 예견한 임계 도달. 근본 시정은 슬롯 총량을 늘리는 것(=(b) 보조 분산)이다.

### 위험 시나리오 (b 채택 시)

1. **보조 세션 편중 → 시세 TICK 슬롯 잠식**: H0UNMKO0 후보를 보조에 넣으면 보조 세션의 TICK 시세 슬롯을
   H0UNMKO0가 차지. 보조 세션이 후보 시세(TICK LOW)로도 이미 붐비면 H0UNMKO0가 시세 후보를 밀어낼 수 있음.
   → **완화**: 총 205 슬롯 vs 실측 소요(TICK 후보 ~150 + H0UNMKO0 후보 ~40 + 보유 HIGH)로 여유 큼. 단
   유니버스가 더 커지면 재평가.
2. **보조 세션 disconnect 시 H0UNMKO0 후보 상실**: 보조 세션 죽으면 그 세션의 H0UNMKO0 후보도 상실.
   그러나 후보 = 미보유 → 손익 무관 + cycle 24 세션 silent-inactive 자동 reconnect가 5분 내 회복.
3. **HIGH 보유 종목이 실수로 보조에 분산**: 절대 금지. HIGH는 반드시 메인 `bypass_limit=True`.
   → **완화**: (b) 구현 시 HIGH 루프는 `kis_ws.subscribe(bypass_limit=True)`(메인 직접) 유지, LOW
   루프만 `kis_ws_pool.subscribe(priority="LOW")`로 분리. 두 경로 분리 = HIGH 메인 고정 불변식.

---

## 정량 권고

### 채택: (b) 풀 분산 — HIGH 메인 고정 / LOW 보조 분산

**구체 스펙** (`scheduler.py::_subscribe_market_operation_tickers` L3398 시정):

```
# HIGH = 보유 + 익일청산 (메인 세션 절대 고정 — 변경 0)
for ticker in sorted(high_tickers):
    await kis_ws.subscribe(MARKET_OP_TR_ID, ticker, bypass_limit=True)   # 현행 유지
    ...

# LOW = 전략 후보 (풀 분산 — kis_ws → kis_ws_pool 로 변경)
for ticker in low_tickers:
    await kis_ws_pool.subscribe(MARKET_OP_TR_ID, ticker, priority="LOW", bypass_limit=False)
    ...
```

핵심 변경 = **LOW 루프 1줄** (`kis_ws.subscribe` → `kis_ws_pool.subscribe(priority="LOW")`). HIGH 루프
불변. `WebsocketPool.subscribe`가 H0UNMKO0(비 체결통보)를 LOW로 받으면 `_select_session`이 보조
라운드로빈에 자동 분배 — **websocket_pool.py 신규 코드 0** (기존 분배 로직이 이미 H0UNMKO0 허용).

**cap 조정**: LOW cap 20 → **상향 검토(예 40~60)**. 보조 분산으로 슬롯 여유가 생기므로 후보 전량 커버
가능. 단 도메인 권고 = **후보 H0UNMKO0 는 "재구독 노이즈 억제"용이므로 cap을 무한대로 열 필요는 없음**.
운영 실측 후보 수(203/204/208/211 확대 후) 기준 + 보조 세션 수 N 을 곱해 결정:
- 보조 세션 N=4 (gold/ISA/RIA/fire) 가정 → H0UNMKO0 후보 용량 여유 충분.
- **권고 cap = min(후보 전체, 60)**. 60 = 실전 유니버스 상한 근사 + 보조 편중 안전 마진. 후보가 60 넘으면
  거래대금/유동성 상위 60만(후보는 이미 유동성 필터 통과 셋) — VI 감시 우선순위는 유동성 높은 종목.
- (사용자 확정 필요: cap 40 보수 / 60 표준 / 후보전체 적극 — 3안 중 택. 도메인 default = **60**.)

**근거**:
- 총 슬롯 205 (41×5) vs 소요 = TICK 후보 ~150 + H0UNMKO0 후보 ~40~60 + 보유 HIGH 소수 → 여유 확보.
- 후보 손실 0 = cycle 149가 047040/475150 로 해결한 VI ping-pong 방어를 **후보 전체로 확대** (현재는
  드롭된 119건이 방어 사각).

### 대안 (a) 판정 — 채택 안 함, 그러나 (b) 실패 시 fallback

(a) cap 20→10 또는 0:
- **cap 0 (보유/익일청산만)**: 후보 VI ping-pong 방어 완전 포기. cycle 149 도입 취지(후보 VI stale
  오판 억제)를 되돌림. cycle 197 log cap + 102 force_retry cap이 폭주는 막으므로 "치명적"은 아니나,
  드롭 로그가 사라지는 대신 후보 재구독 시도 자체는 계속 발생(관측만 억제, 근본 미해결).
- **cap 10**: 20보다 더 많이 드롭 → 후보 방어 축소. 유니버스가 커진 상황에서 역행.
- 판정: **(a)는 대증요법** — 문제(슬롯 부족)를 후보 감시 희생으로 회피. (b)가 안전하다고 확인된 이상 (a)
  불필요. 단 (b) 구현/검증 리스크가 크다고 판단되면 **임시 지혈로 cap 10 하향은 허용**(드롭 로그 감소 +
  방어 우선순위 상위 10 종목 유지).

### 대안 (c) 판정 — 채택 안 함

(c) 유지 + 관찰:
- 현재 시세 TICK(풀 분산)·보유 H0UNMKO0(HIGH bypass)는 안전 → 즉각 손익 위험 0은 맞음.
- 그러나 (1) 드롭된 119 후보의 VI ping-pong 재구독 시도가 계속 발생(cycle 197 cap이 로그만 억제, 시도는
  잔존) (2) 유니버스가 더 커지면(향후 완화 사이클) 드롭 증가 → 재발.
- 판정: **미봉책**. (b)가 안전 확인된 근본 시정이므로 (c) 선택할 이유 없음.

---

## 현 코드와의 정합성

### 충돌 항목

**cycle 149 "보조 세션 절대 금지" (의제 2 채택) 와 (b) 정면 충돌** — 그러나 위 재검증으로 cycle 149 근거가
반증됨. 충돌 해소 방식 = **cycle 149 의제 2 의 "보조 금지"를 "체결통보만 메인 단일, H0UNMKO0 는 LOW 후보
보조 분산 허용"으로 갱신**. 이는 코드 정본(websocket_pool.py 의 "시세 only" 정책)과 오히려 정합.

### 변경 vs 유지 선택지

| 항목 | (b) 채택 시 | 유지 근거 |
|---|---|---|
| HIGH(보유/익일청산) 메인 고정 + bypass=True | **유지 (변경 0)** | 사이클 32 R4 / 149 / 197 절대 보호 |
| LOW 후보 `kis_ws.subscribe` → `kis_ws_pool.subscribe(priority="LOW")` | **변경 (1줄)** | 근본 시정 |
| `WebsocketPool.subscribe` H0UNMKO0 분배 로직 | **유지 (변경 0)** | 이미 비 체결통보 LOW 분배 지원 |
| `_EXECUTION_NOTICE_TR_IDS` frozenset | **유지 (변경 0)** | H0UNMKO0 미포함 = 이미 정합 |
| LOW cap 20 | **상향 (예 60)** | 보조 슬롯 여유 |
| `record_market_op_event` / `is_ticker_stale_excluded` 소비 | **유지 (변경 0)** | 전역 dict, 세션 무관 |

---

## 매매 안전성 8영역 영향 (realtime/ 영역 = 신중)

- **realtime/websocket_pool.py = 변경 0** — H0UNMKO0 LOW 분배는 기존 `subscribe`/`_select_session`
  경로가 이미 처리. `_EXECUTION_NOTICE_TR_IDS` 불변 → 체결통보 메인 단일 강제 절대 보존.
- **변경 지점 = `scheduler.py::_subscribe_market_operation_tickers` LOW 루프 1줄** (8영역 밖 —
  scheduler 는 lifecycle. 단 realtime/ pool API 호출이라 realtime 인접 → 신중 검증 의무).
- **HIGH bypass 보존 방식**: HIGH 루프는 `kis_ws.subscribe(bypass_limit=True)` 메인 직접 호출 유지 —
  보조로 절대 새어나가지 않음(코드 경로 분리 = 불변식). 사이클 32 R4 보유 절대 보호 영속.
- **사이클 197 41-cap DailyEmitCap 보존**: `kis_ws.subscribe`(메인) 경로의 41-cap WARNING cap 은 HIGH
  루프에서 여전히 유효(bypass=True 라 미진입). LOW 는 pool 경로라 pool 의 `[priority_drop_pool]` 로 전환
  — 드롭 시 pool 이 all_sessions_full 로그. cycle 197 cap 은 메인 단독 subscribe 잔존 경로에서 보존.
- **체결통보 구독(H0STCNI0/9) / risk.on_tick / order_engine / auth = diff 0** — H0UNMKO0 는 read-only
  시세성, 매매 hot path 무관.

---

## 회귀 가드 후보

- **G-214-1 (HIGH, SAFETY)**: HIGH(보유/익일청산) H0UNMKO0 구독은 반드시 `kis_ws.subscribe(bypass_limit=
  True)` 메인 경로 — 보조 세션에 절대 미분배 (AST + 행위: high_tickers 구독 후 `_ticker_to_session` 에서
  메인 소속 검증).
- **G-214-2 (HIGH)**: LOW 후보 H0UNMKO0 는 `kis_ws_pool.subscribe(priority="LOW")` 경로 — 보조 세션
  존재 시 보조 분배 검증 (mock 보조 N=2 → LOW H0UNMKO0 가 보조에 add).
- **G-214-3 (SAFETY)**: `_EXECUTION_NOTICE_TR_IDS` == frozenset({"H0STCNI0","H0STCNI9"}) 불변
  (H0UNMKO0 미포함 = 체결통보 메인 단일 강제 영속, AST).
- **G-214-4**: 보조 0개(N=1) 시 pool.subscribe(H0UNMKO0, LOW) → 메인 fallback = cycle 149 현행과 동일
  (회귀 0, 보조 미등록 환경 보존).
- **G-214-5**: H0UNMKO0 보조 분산 후에도 `record_market_op_event` → `is_ticker_stale_excluded` 소비
  불변 (전역 dict, 세션 무관 — 보조 세션 dispatch 도 동일 monitor 갱신).
- **G-214-6 (SAFETY)**: cap 상향해도 HIGH 는 cap 밖 무조건 구독 (사이클 149 의제 3 영속).

---

## 후속 검증 권고 (tdd-engineer / tester)

1. **tdd-engineer**: G-214-1/2/3 을 Red 우선 — 특히 G-214-1(HIGH 메인 고정)은 stash 시 FAIL 하도록
   HIGH ticker 가 보조에 분배되지 않음을 `_ticker_to_session[ticker] is _main` 으로 단언. mock 보조 세션
   N=2 구성 + LOW H0UNMKO0 분배 확인.
2. **tester**: 매매 안전성 8영역 diff 검증 — `git diff -- src/realtime/ src/engine/risk.py
   src/engine/order_engine.py src/auth/ src/api/order.py` = 0 (변경은 scheduler LOW 루프 1줄 한정).
   realtime/websocket_pool.py byte 불변 직접 확인.
3. **D+1 운영 실측**: (b) 배포 후 `H0UNMKO0/<ticker> 구독 건너뜀` 119건 → 0 확인 +
   `[priority_drop_pool] ... H0UNMKO0` 도 0 확인(전량 수용) + 보조 세션별 H0UNMKO0 분산 카운트
   (`get_session_status` 의 세션별 subscribed 에 H0UNMKO0 포함 여부) 실측.
4. **domain-expert 후속**: 보조 세션 TICK 시세 슬롯 잠식 여부 2주 관찰 — H0UNMKO0 후보가 보조에서 TICK
   후보를 밀어내는지 (`[priority_drop_pool] tr_key=... priority=LOW` TICK 드롭 증가 여부). 증가 시 cap
   재하향 또는 H0UNMKO0 전용 세션 분리 검토.

---

## 반례 / 한계

- **한계 1**: (b)는 보조 세션이 실제로 등록/연결돼 있을 때만 효과. 보조 0개(N=1) 환경(코드 배포 직후 또는
  DB 미등록)에서는 pool.subscribe 가 메인 fallback → 현행 (a)-cap20 과 동일한 드롭 잔존. 즉 **(b)의 전제 =
  보조 세션 운영 중**. 보조 세션이 죽어있으면 (a) 임시 cap 하향이 병행 안전망으로 유효.
- **한계 2**: H0UNMKO0 후보를 보조에 넣으면 보조 세션의 TICK 시세 총량이 줄어듦(같은 41 슬롯 공유). 후보
  유니버스가 205 슬롯을 다 채울 만큼 더 커지면(향후 완화 사이클) TICK vs H0UNMKO0 슬롯 경합 재발 →
  그때는 H0UNMKO0 전용 보조 세션 분리 또는 cap 하향이 필요. 현 시점 여유는 충분.
- **반례(가설이 깨지는 시나리오)**: 만약 KIS가 향후 H0UNMKO0를 "시세 계좌(quote-only 토큰)에서 구독 불가"로
  정책 변경하면 (b) 무효 → (a)로 회귀. 현 정본(2026-07)은 `실시간시세` 카테고리 = 구독 가능. 배포 후 D+1
  실측에서 보조 세션 H0UNMKO0 SUBSCRIBE SUCCESS 확인 = 이 반례 배제 검증.
- **한계 3**: cap 값(40/60/전체)은 도메인이 "60 표준"을 default 권고하나, 최종은 사용자 확정 사항 —
  후보 수 실측 + 보조 세션 N 확정 후 결정.
