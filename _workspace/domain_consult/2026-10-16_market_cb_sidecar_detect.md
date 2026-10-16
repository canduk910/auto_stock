# 자문: 서킷브레이커·사이드카 인지 — 메인 세션 장운영정보 구독 + CB 중 LOW 재구독 정지 (R3 C)
- 의뢰자: 메인 세션 (사용자 결정 2026-10-16 「인지 + R3 C」)
- 의뢰일: 2026-10-16
- 긴급도: HIGH (코스피·코스닥 모두 60일선 아래 하락 — 같은 사건이 다시 날 수 있는 장세)
- 근거: `_workspace/analysis/2026-10-15_silent_skip_1240.md` · `docs/kis/domestic-stock-realtime.md:1123~1192`(H0STMKO0) · `:191~236`(H0UNMKO0 + 실측 주의문) · `_workspace/domain_consult/cycle359_mkop_field_offset.md`
- 범위: (1) 발동·해제 기록 + 대시보드 표시 (2) CB 중 LOW 재구독(120초 K watcher · 5분 우선 재구독) 정지, HIGH 그대로. R3 A·B, 매매 신호·주문·청산은 범위 밖이다.

## 질문 요약

10-15 12:23(코스닥)·12:38(코스피)에 서킷브레이커 1단계로 보이는 전 종목 정지가 30분씩 있었다. 시스템은 이를 「CB」로 알아보지 못했다. `[market_op_cb_suspected]` 는 정지 종목 5개 이상이어야 켜지는데 관찰 대상이 2종목뿐이었다. 그 사이 LOW 약 120종목을 계속 해제→재등록했다. 질문은 일곱 가지다. 어느 채널·종목을 메인에 두는지, 슬롯은 어떻게 하는지, 상태를 어떻게 정의하는지, 게이트 조건, 마커·표시, tdd 시나리오다.

## 트레이더 시각

### 시장 가설
서킷브레이커는 **시장 단위 사건**이다. 종목 한두 개의 정지나 VI 와는 다르다. KRX 는 시장(코스피·코스닥)별로 따로 발동하고, 대체거래소(NXT)도 같이 멈춘다. 멈춘 30분 동안 「체결이 안 오는 것」은 정상이다. 그때 구독을 다시 거는 것은 회복 가치가 0 이고 LMS(등록·해제 반복) 압력만 쌓는다. 반대로 보유 종목은 재개 첫 체결(단일가 결과 = 갭)을 놓치면 안 되므로 HIGH 는 손대지 않는다. 사용자 결정과 같은 방향이다.

### 제도 사실(국내 CB·사이드카 — 거래소 규정, 2026 기준 일반 지식)
| 사건 | 발동 조건 | 효과 | 시장 체결 | 하루 횟수·시간 제한 |
|---|---|---|---|---|
| CB 1단계 | 지수 전일 대비 −8% 1분 지속 | 전 종목 20분 매매정지 → 10분 단일가 → 재개 | **멈춤 30분** | 1회 · 14:50 이후 발동 안 함 |
| CB 2단계 | −15% 이고 1단계보다 1%p 더 하락 | 1단계와 같음 | 멈춤 30분 | 1회 · 14:50 이후 발동 안 함 |
| CB 3단계 | −20% 이고 2단계보다 1%p 더 하락 | **그날 장 종료** | 끝 | 1회 · 시간 제한 없음 |
| 사이드카 | 코스피200 선물 ±5%(코스닥: 코스닥150 선물 ±6% 이고 현물 ±3%) 1분 지속 | **프로그램매매 호가 효력 5분 정지** | **계속됨** | 1회 · 14:50 이후 발동 안 함 |
| 시장임시정지(164) | 거래소 시스템 장애 등 | 전 종목 정지 | 멈춤(길이 불명) | — |

→ **사이드카는 LOW skip 대상이 아니다.** 일반 매매는 그대로 돌아서 LOW 종목 체결도 계속 온다. 그때 침묵하는 종목은 진짜 피드 결손일 수 있고, 그것을 고치는 것이 재구독의 원래 목적이다. 사이드카는 **기록·표시만** 한다.

### 실전 사례 / 통계 (10-15 실측, 분석 메모 1-2절)
- H0UNMKO0 대표 005930: 12:38 `AF8`(TRHT_YN=Y) → 12:58 `AF1` → 13:08 `AF1`/`BF9` → 코스피 재개.
- H0UNMKO0 보유 053450(코스닥): 12:23 `AF8`(**TRHT_YN=N**) → 12:43 `AF1` → 12:53 `BF9` → 같은 초에 체결 재개.
- 두 시장 모두 「AF8 → 20분 → AF1 → 10분 → BF9」였다. 1단계 시간표(20+10)와 정확히 맞는다. **표본은 시장마다 1건이다.**
- 053450 은 재개 체결이 **재등록 없이 기존 구독으로** 들어왔다. → 정지 중 재구독은 회복에 기여한 바가 없다(C 의 근거).
- 사이드카: 10-15 저가가 −9%대라 사이드카도 그날 났을 가능성이 높다. 그런데 분석 메모는 12:23 이전 H0UNMKO0 프레임을 다루지 않았다. **사이드카 때 통합 채널이 무엇을 보냈는지는 아직 모른다**(아래 후속 검증 V0).

### 위험 시나리오
1. **알파벳 코드의 뜻을 잘못 읽는다** — `AF8`·`AF1`·`BF9` 는 공식 문서가 없다. `AB1` 이 VI 2분 쌍에 붙어 온 선례(cycle359 §3.1)를 보면, 종목 단위 사건(VI·종목정지)에도 비슷한 알파벳 코드가 올 수 있다. 종목 하나의 정지를 시장 CB 로 읽으면 LOW skip 이 잘못 켜진다. 비용은 최대 TTL 동안 후보 피드를 고치지 않는 것(진입 기회 손실)이고 손절과는 무관하다.
2. **해제 코드가 안 온다** — 175/185/BF9 를 놓치면 LOW skip 이 하루 종일 남는다. cycle368 VI·정지 TTL 이 막은 것과 같은 모양의 결함이다. → TTL 이 필수다.
3. **H0STMKO0 가 대표 종목 구독으로 시장 코드를 안 보낸다** — 워크북 개요는 「연결종목의 VI 발동·해제 시 수신」이라고만 적었다. 코드 표에 174/175/387 등이 있다고 해서 종목 단위 구독으로 그 코드가 배달된다는 보장은 없다. → 통합 채널(이미 실측된 경로)을 버리지 않는다.

## 정량 권고

### Q1. 채널 — **둘 다 받는다. 기존 H0UNMKO0/005930 은 그대로 둔다**

| 안 | 구독(메인 추가분) | 장점 | 약점 |
|---|---|---|---|
| **안1 (권고)** | H0STMKO0 × 2(코스피·코스닥 대표) + H0UNMKO0 × 1(코스닥 대표) = **+3** | 공식 숫자 코드(174/175/182/184/185/387/388/397/398/164)와 실측된 알파벳 코드(AF8/AF1/BF9) 두 계열을 모두 받는다. 한 계열이 안 와도 다른 계열이 잡는다 | 슬롯 +3 |
| 안2 | H0STMKO0 × 2 = +2 | 공식 코드라 해석에 근거가 있다 | 배달 여부가 미확인이다. 안 오면 CB 인지가 0 이 된다 |
| 안3 | H0UNMKO0 × 1(코스닥 대표) = +1 | 실측으로 배달이 확인된 경로다 | 코드 뜻이 비공식(표본 1)이다. 사이드카 코드를 모른다 |

- 기존 `H0UNMKO0/005930`(`scheduler.py:618-626`)은 보드 기록용(`session.on_h0nxmko0`)이다. 동시에 코스피 알파벳 코드의 유일한 실측 경로라 **그대로 유지**한다.
- H0STMKO0 도 같은 `_handle_market_op` → `record_market_op_event` 로 이미 흘러간다(`handler.py:404-406`). **`src/realtime/**` 변경은 0 이다.**
- ⚠️ 부수 효과: H0STMKO0 는 08:30 `110`·15:20 `121` 같은 공식 동시호가 코드를 실제로 보낼 것이다. 그러면 `session._last_nxt_mkop_code` → `is_call_auction_now` 의 **코드 분기가 처음으로 켜진다**. 그 분기는 시간창(110: 08:25~09:05 · 121: 15:15~15:35)으로 묶여 있고, 같은 창의 시간 기반 폴백과 결과가 같다. 그래서 행위 차이는 없다고 판단한다. tdd 시나리오 T8 로 못 박는다.

### Q2. 대표 종목
- **코스피 = 005930 고정**(기존과 같다).
- **코스닥 = 고정 1종목**을 권고한다. 부팅 때 시총 1위를 고르는 방식은 DB·REST 의존을 부팅 경로에 하나 더 붙인다. 대표가 바뀌어도 시장 코드는 같으므로 「제일 큰 종목」일 필요가 없다. 요건은 셋이다. ① 거래정지·관리종목 가능성이 낮은 초대형주 ② NXT 거래 대상(보드 기록과 무관하지만 08:00 프레임 관찰용) ③ 상장폐지·이전상장 위험이 낮을 것. 후보는 **196170(알테오젠)**이고, 예비는 247540(에코프로비엠)이다. 확정은 backend-dev 가 `stock_master` 의 `excg_dvsn_cd=="03"` 과 거래정지 여부를 확인해서 한다. 이전상장 공시가 나면 사람이 바꾼다(상수 1줄).
- **시장당 2종목은 필요 없다.** CB 코드는 시장 코드라 대표 1종목이면 충분하다. 오판 위험은 「대표만 멈춘 경우」인데, 그것은 해석 규칙(Q4)으로 막는다. 대표의 `TRHT_YN=Y`·종목상태 58·VI(`AB1`, VI_CLS_CODE=Y)는 **CB 판정에 쓰지 않는다**. 10-15 에도 053450 은 TRHT_YN=N 이었다. 시장 코드 집합에 든 코드만 본다.

### Q3. 메인 슬롯 — 충돌하지 않는다. 단 `bypass_limit=False` 로
- 메인의 비-시세 구독은 지금 2개(체결통보 1 + H0UNMKO0/005930 1)다. 안1이면 5개가 된다. 한도 판정은 `len(self._subscriptions) >= 41`(`websocket.py:627`)이고 비-시세도 센다. 메인 HIGH 는 평소 10건 안팎이라 여유는 충분하다.
- **`bypass_limit=False` 로 건다.** cycle221 원칙(보호 대상은 tick 이다. 관찰 채널은 tick 을 밀어내지 않는다)과 같다. 부팅 순간은 슬롯이 비어 있어 항상 들어간다.
- **재연결 재구독은 공짜로 보장된다.** `_restore_subscriptions_after_reconnect`(`websocket.py:686-699`)가 `_subscriptions` 전체를 다시 보낸다(비-시세 포함). 정리 경로인 `scanner` 의 메인 잔여 해제(`scanner.py:1913-1918`)는 `TICK_TR_IDS` 만 지운다. 따라서 이 구독은 15:20·20:00 정리에서도 살아남는다.
- 🔴 이 구독 코드를 **`market_op_subscribe.py` 에 넣지 않는다.** `tests/unit/ast/test_cycle221_ast_market_op_no_main.py` 는 그 VI 훅의 메인 `kis_ws.subscribe` 를 0건으로 잠근다. 대표 구독은 VI 와 목적이 다른 새 leaf 에 둔다(아래 「최소 변경 자리」).
- 🔴 메인 VI 0건 규약(cycle221)의 **명시적 예외**로 문서화한다. 「시장 코드 대표 구독, 종목 수 상수 3, 늘리지 않는다」고 적고, AST 로 대표 상수의 원소 수 ≤ 3 을 건다.

### Q4. 상태 정의 (시장별 `KOSPI`/`KOSDAQ`)

| 상태 | 들어가는 코드(대표 종목 프레임의 MKOP_CLS_CODE) | 나가는 조건 | 수명(TTL) |
|---|---|---|---|
| `CB_ACTIVE` | H0STMKO0: **174**(발동) · **182**(장중동시마감) · **184**(개시) / H0UNMKO0: **AF8** · **AF1**(단일가 단계 — 이미 ACTIVE 면 유지, 아니면 진입) | 175 · 185 · **BF9** 수신 → `RELEASED`(유예) / TTL | 마지막 활성 프레임 뒤 **40분**(20+10분 + 여유 10분) |
| `CB_STAGE3` | 같은 날 그 시장 세 번째 `CB_ACTIVE` 진입(단계 = 그날 진입 횟수) | 21:30 정산 리셋 | 그날 끝까지 — 3단계는 장 종료라 재개가 없다 |
| `HALT_164` | **164**(시장임시정지) | 112(장개시)·175·185·BF9 수신 / TTL | **40분**, 만료 시 WARNING |
| `RELEASED`(유예) | 해제 코드 수신 | **180초** 뒤 `NORMAL` | — |
| `SIDECAR` | 387(매도)·397(매수) | 388·398 / TTL | **6분**(5분 + 1분) |
| 모르는 코드 | 위 표 밖의 코드(정상 장운영 110·112·121·129·F/P 계열은 「알려진 정상」) | 기록만 한다(INFO, 코드별 하루 1회) | — |

- **단계 구분**: KIS 코드에는 단계가 없다. 「그날 그 시장의 `CB_ACTIVE` 진입 횟수」로 단계를 센다(1·2·3). 3단계는 TTL 로 풀지 않는다. 하루 1회 제한이 있으니 횟수가 곧 단계다.
- **두 계열 중복 진입**: 같은 시장에 174(ST)와 AF8(UN)이 함께 오면 **같은 사건 하나**로 친다. 이미 ACTIVE 면 단계 카운트를 올리지 않고 TTL 만 갱신한다. 다만 해제(`RELEASED`) 뒤 15분 안에 오는 재발동 코드는 오차 프레임으로 볼 수 있다. 그래서 그 경우에만 같은 단계로 다시 들어간다. 1단계 재개 뒤 2단계까지는 수십 분이 걸리는 것이 보통이다. 이것을 단순화하려면 「직전 해제 뒤 5분 안이면 단계 증가 없음」 하나만 둔다.
- **시간창**: `CB_ACTIVE`·`HALT_164` 가 LOW skip 을 일으키는 것은 **09:00~15:30 안에서만**이다. 창 밖에서 들어온 코드는 기록·표시만 한다. 동시호가·장외는 기존 경로(`is_call_auction_now`)가 맡는다. 14:50 이후의 174 는 3단계일 때만 실재한다. 그래서 그 시각의 진입은 단계 카운트가 2 이상일 때만 정상이다. 아니면 WARNING `[market_cb_unexpected]` 로 남기되 상태 진입은 한다(안전 방향 = LOW skip, 비용은 진입 기회뿐).
- **알파벳 코드의 강등 조건**: 후속 검증 V0 에서 `AF8` 이 CB 가 아닌 날에도 나온 것이 확인되면 UN 계열은 「기록만」으로 내리고 ST 숫자 코드만 상태를 바꾼다. 상수 하나(`_UN_CODES_DRIVE_STATE`)로 전환한다.
- **사이드카는 LOW skip 을 일으키지 않는다.** 위 제도표가 근거다.
- **대표 종목의 VI·정지·종목상태는 상태 판정에 쓰지 않는다.** 기존 `record_market_op_event` 의 VI·정지 처리는 그대로 탄다.

### Q5. C 의 게이트 조건

| 안 | 규칙 | 트레이드오프 |
|---|---|---|
| **(a) 권고 — 어느 시장이든 CB 면 LOW 전부 skip** | `any(state in {CB_ACTIVE, CB_STAGE3, HALT_164, RELEASED}) and 09:00≤t<15:30` | 종목→시장 조회가 필요 없다(stale watcher 는 hot path 라 DB 조회를 넣으면 안 된다). 10-15 기준으로 skip 은 12:23~13:11(48분)이었다. 그 사이 15분씩 열려 있던 다른 시장의 LOW 피드 결손을 늦게 고친다. 손해는 폭락 구간의 진입 기회뿐이고, 그 구간 진입은 기대값이 낮다 |
| (b) 그 시장만 skip | 종목 시장(`excg_dvsn_cd`)이 CB 인 LOW 만 skip | 정밀하다. 하지만 동기 시장 맵이 stale watcher 에 없다(`market_unit.get_market_map` 은 async DB). 맵 결측이면 (a)로 떨어뜨리는 2단 규칙이 필요해 코드가 는다 |
| (c) 둘 다 CB 일 때만 | — | 10-15 처럼 시차가 있으면 코스닥 단독 15분을 놓친다. 권고하지 않는다 |

- **HIGH 는 어떤 안이든 무접촉이다.** 동시호가 선례(cycle371·216)와 같은 꼴이다. 120초 경로는 `low_stale` 만 비우고 `high_stale` 은 그대로 처리한다. 5분 경로는 `low_targets = []` 로 비운다.
- **해제 직후 몰림 방지 = `RELEASED` 유예 180초.** 재개 첫 체결이 같은 구독으로 들어와 `ticker_last_tick` 을 새로 찍을 시간을 준다(10-15 053450 실측). 180초 = `RESUBSCRIBE_THROTTLE_SECS`(=3×`STALE_FRESHNESS_SECS`)로 기존 상수를 재사용한다. 유예가 끝난 뒤에도 남는 stale 은 진짜 결손이다. 이것은 기존 장치가 이미 분산한다 — 시간당 cap(`STALE_FORCE_RETRY_HOURLY_CAP=6`)·`STALE_FORCE_RETRY_AFTER_SECS=600`·LOW 180초 throttle. **별도 순차 지연은 두지 않는다.** 새 장치를 늘리지 않는다.
- **동시호가 판정과 독립**이다. 두 게이트는 OR 로 묶고 마커는 따로 남긴다. 동시호가 상태와 CB 상태를 한 함수로 합치지 않는다. `is_call_auction_now` 는 8영역(`session.py`)이라 건드리지 않는다.
- 범위 메모: `_scan_loop` 5분 주기의 후보 구독 재편(scanner)은 C 범위 밖이다(사용자 범위 = 두 stale 경로).

### Q6. 마커·경보·표시·D+1 판독

| 마커 | 레벨 | 내용 |
|---|---|---|
| `[market_cb_active]` | **WARNING** | `market= stage= code= tr_id= tr_key= ts=` — 진입 1회 |
| `[market_cb_release]` | WARNING | `market= stage= code= elapsed_secs= reason=code|ttl` — TTL 해제면 `reason=ttl`(해제 코드 결손 신호) |
| `[market_halt_164]` | WARNING | 시장임시정지 진입·해제 |
| `[market_sidecar]` | WARNING | `market= side=sell|buy transition=on|off|ttl` |
| `[market_cb_unexpected]` | WARNING | 14:50 이후 1·2단계 의심 코드 · 시간창 밖 활성 코드 |
| `[market_status_unknown_code]` | INFO | 대표 종목의 모르는 코드, 코드별 하루 1회 cap |
| `[stale_skip_market_cb]` / `[stale_skip_market_cb_priority]` | WARNING(동시호가 마커와 같은 레벨) | `subscribed= low= high= markets=` — 120초·5분 경로 각자 |
| `[market_status_rep_subscribed]` | INFO / 실패 WARNING | 부팅 구독 3건 |

- **CRITICAL 은 쓰지 않는다.** CB 는 시장 사건이지 시스템 결함이 아니다. CRITICAL 은 인증·키 같은 무결성 경보용으로 남겨 둔다. 경고등(`alert_markers.py`) 명부에도 넣지 않는다. 그 명부는 「시스템 오류」 범주라서 시장 사건이 섞이면 의미가 흐려진다. **표시는 기존 장운영 화면으로 한다.**
- **대시보드**: `get_market_op_state_summary()["circuit_breaker"]` 에 필드를 **더한다**(기존 `suspected` 휴리스틱은 그대로 두고 `confirmed` 축을 따로 둔다). 더할 필드는 `markets: {KOSPI|KOSDAQ: {state, stage, since, last_code, source_tr_id, ttl_expires_at}}` · `sidecar: {KOSPI|KOSDAQ: {side, since}}` · `low_skip_active: bool` · `events_today: [≤10]`. 화면(`MarketStateNow.tsx`·`RealtimeHealth.tsx`)은 이미 `circuit_breaker` 를 읽는다. 「코스닥 서킷브레이커 1단계 발동 12:23 · 해제 예정 ~12:53」 띠 하나와 사이드카 배지 하나를 단다.
- **D+1 판독 기준(정상일)**:
  1. 부팅에 `[market_status_rep_subscribed]` 3건이 있고, ACK 오류·`최대 구독 수` WARNING·OPSP 가 0 이다.
  2. **H0STMKO0 대표 2종목에서 08:30 `110`, 09:00 `112`, 15:20 `121`, 15:30 `129` 가 수신된다.** 이 넷이 오면 「종목 단위 구독으로 시장 단위 코드가 배달된다」가 **CB 없이도** 실증된다. 그러면 Q1 의 위험 3 이 사실상 풀린다. 안 오면 ST 계열은 무효로 보고 안3으로 줄일지 재자문한다.
  3. `[market_cb_active]`·`[market_halt_164]` 0건. 1건이라도 나오면 거래소 공지와 대조한다. 오탐이면 V0 강등 규칙을 발동한다.
  4. `[stale_skip_market_cb*]` 0건(정상일).
  5. 재연결이 있던 날은 재연결 직후 대표 3건이 다시 ACK 되는지 확인한다.
- **사건일 판독**: 진입·해제 시각이 거래소 공지와 ±1분 안에 맞는지, `elapsed_secs≈1800`인지, `reason=code` 인지, skip 구간 LOW SEND=0 · HIGH 재등록이 그대로인지, 유예 180초 뒤 force_retry 가 몰리지 않는지(시간당 cap 차단 수) 본다.

## 현 코드와의 정합성

- **충돌 항목**
  - **`src/engine/market_op_subscribe.py` + `test_cycle221_ast_market_op_no_main.py`** — 메인 구독 금지 가드가 있다. 대표 구독을 이 파일에 넣으면 가드가 깨진다. → 새 leaf 에 둔다.
  - **cycle221 「메인 VI 0건」 규약** — 대표 3건은 VI 용도가 아니지만 같은 TR 계열이다. 명시적 예외로 문서화하고 상수 원소 수 AST 상한을 건다.
  - **`get_circuit_breaker_state()` 의 `representative_mkop_cls_code`**(005930 마지막 코드) — ST 프레임도 같은 ticker 로 들어와 이 값이 ST/UN 중 나중 것으로 덮인다. 표시만 쓰는 값이라 행위 영향은 0 이지만, 화면 문구가 섞인다. `confirmed` 축에서 `source_tr_id` 를 같이 보인다.
- **최소 변경 자리 (scheduler 3,867줄 → 순감소 권고)**
  1. 새 leaf `src/engine/market_cb_state.py`(8영역 아님): 상태 기계(시장별 dict, TTL 지연 평가 — cycle368 `_expire_stale_*` 패턴), 순수 판정 `is_low_resub_suppressed(now) -> bool`, 요약 `get_market_cb_summary()`, `reset_market_cb_state()`, 대표 상수 `MARKET_STATUS_REPS = (("H0STMKO0","005930","KOSPI"), ("H0STMKO0","<코스닥대표>","KOSDAQ"), ("H0UNMKO0","<코스닥대표>","KOSDAQ"))`, 구독 함수 `async subscribe_market_status_reps(ws)`(`bypass_limit=False`, 각 건 try/except).
  2. `market_operation_monitor.record_market_op_event`: 끝에 `market_cb_state.on_event(event)` 1회 호출(try/except 흡수). 대표 ticker 가 아니면 즉시 반환. `get_market_op_state_summary` 의 `circuit_breaker` 에 확인 축을 합친다. **8영역 아님.**
  3. `stale_watcher_core.py`(8영역 아님): 두 자리(120초 `:671` 직후 · 5분 `:1133` 직후)에 동시호가와 같은 꼴의 try-import 판정 + LOW-scoped skip 을 넣는다. 120초 경로는 `_is_call_auction or _is_market_cb` 로 묶되 마커는 따로 남기고, 5분 경로는 `low_targets = []`.
  4. `scheduler.py`: `:618-626` 9줄 블록을 leaf 호출 하나(H0UNMKO0/005930 포함 전체를 leaf 로 옮겨 **순감 4~5줄**)로 바꾼다. `_reset_daily_state` 에 `reset_market_cb_state()` 1줄(기존 `reset_market_op_state` 호출 옆, `:3802` 부근)을 둔다. 순증감은 −3 안팎이다. 🔴 H0UNMKO0/005930 을 leaf 로 옮길 때 기존 테스트(`test_cycle149_handler_market_op.py` 등)의 문자열 핀을 확인한다. 핀이 무거우면 그 블록은 두고 leaf 호출 2줄만 더한다(+2줄).
  5. `src/realtime/**`·`session.py`: **무접촉**(H0STMKO0 라우팅은 이미 있다).
- **선택지**: 안1 권고(+3 슬롯) / 안2·안3 은 Q1 표 참조. 게이트는 (a) 권고 / (b) 정밀안.

## 반례 / 한계
- 반례 1: 대표 종목이 그날 **개별 거래정지**(공시 대기 등) → 그 종목 구독으로 시장 코드가 계속 오는지 알 수 없다(정지 종목에도 장운영 프레임이 오는지 미확인). 코스피는 ST·UN 둘 다 005930 한 종목이라 단일 실패점이다. 005930 정지는 확률이 매우 낮아 받아들인다. 사고가 나면 대표 상수 1줄로 바꾼다.
- 반례 2: 해제 코드도 오지 않고 TTL 40분 안에 시장이 재개되면 최대 10분(+유예 3분) 동안 LOW 재구독이 쉰다. 비용은 진입 기회뿐이다.
- 반례 3: 3단계(장 종료)를 단계 카운트로만 판정한다. 시스템이 1·2단계 사이에 재기동해서 카운트를 잃으면, 3단계를 2단계로 보고 40분 TTL 뒤 풀린다. 그 뒤 LOW 재구독이 장 마감까지 헛돈다. 3단계는 역사적으로 한 번도 발동된 적이 없어 받아들인다.
- 반례 4: 사이드카를 skip 하지 않으므로 사이드카 5분 동안 프로그램 호가가 빠진 종목이 잠깐 침묵해도 재구독이 돈다. 일반 체결은 계속되므로 120초 침묵 종목은 적다고 본다.
- 한계: CB 실측 표본은 1회(시장별 1건)뿐이다. `AF8/AF1/BF9` 해석은 시각 패턴에 근거한 추정이다. H0STMKO0 의 시장 코드 배달 여부는 미실측이다(V1 이 정상일 하루로 해소). 제도 수치는 일반 지식이며 2026 개정 여부는 거래소 공지로 재확인이 필요하다.

## 후속 검증 권고

- **V0 (구현 전, tester — EC2 읽기 전용 grep)**: 최근 30거래일 `H0UNMKO0` 프레임에서 `MKOP_CLS_CODE` 값 분포를 날짜·종목별로 센다. `AF8`·`AF1`·`BF9` 가 10-15 말고도 나왔으면 UN 계열을 「기록만」으로 강등한다. 아울러 10-15 09:00~12:23 의 005930 프레임에서 사이드카 시각의 코드를 확인한다.
- **V1 (배포 다음 거래일)**: D+1 판독 2번(ST 110/112/121/129 수신).
- **tdd-engineer 에게 — 시나리오 8개**(가짜 프레임은 라이브 모양 `[0]=종목코드`, `0|H0STMKO0|001|005930^N^(null)^174^^^^55^N^N` 같은 원문 → `dispatch_message` 부터 탄다)
  - **T1 발동→skip**: 11:00 KOSDAQ 대표 H0STMKO0 `174` → `is_low_resub_suppressed=True`. 120초 경로에서 stale LOW 3 + HIGH 1 이면 LOW SEND 0, HIGH `unsubscribe_in_pool`→`subscribe(HIGH, bypass=True)` 1회, `[stale_skip_market_cb]` WARNING 1행. 5분 경로도 같은 입력에서 `low_targets==[]`, HIGH 그대로.
  - **T2 알파벳 계열**: 12:38 005930 H0UNMKO0 `AF8`(TRHT_YN=Y) → KOSPI `CB_ACTIVE` stage=1. 12:58 `AF1` → 같은 단계 유지, TTL 갱신. 13:08 `BF9` → `RELEASED` → 13:11:00 이전 True, 13:11:01 False(freezegun).
  - **T3 TTL**: `174` 뒤 해제 코드 없이 40분 1초 → False + `[market_cb_release] reason=ttl` WARNING 1회. 3단계(같은 날 세 번째 진입)는 TTL 뒤에도 True.
  - **T4 사이드카는 skip 아님**: `387` → `sidecar.KOSPI.side=="sell"`, `is_low_resub_suppressed=False`, LOW 재등록이 정상 발사된다. 6분 뒤 TTL 해제.
  - **T5 대표가 아닌 종목·종목 사건 무시**: 보유 종목 053450 `AF8`(대표 아님) → 상태 불변(V0 결과로 바꿀 수 있는 지점). 대표 005930 `TRHT_YN=Y`+종목상태 58+`AB1` → 상태 불변. 모르는 코드 `ZZ9` → INFO 1회, 두 번째는 cap.
  - **T6 시간창**: 08:40 `174` → 기록·표시는 하되 LOW skip False. 15:31 → False. 14:55 첫 진입 `174` → `[market_cb_unexpected]` + 진입.
  - **T7 재연결 재구독 + 슬롯**: 부팅 leaf 가 3건을 `bypass_limit=False` 로 `_subscriptions` 에 넣는다. `_restore_subscriptions_after_reconnect` 뒤 3건이 다시 SEND 된다. `scanner` 메인 잔여 정리 뒤에도 3건이 남는다(TICK 아님). 슬롯 40/41 이 찬 상태에서 부르면 조용히 skip + WARNING(대표 구독이 HIGH tick 을 밀지 않는다).
  - **T8 동시호가 회귀 0**: H0STMKO0 `110` 을 08:31 에, `121` 을 15:21 에 넣은 경우와 안 넣은 경우 `is_call_auction_now` 결과가 같다. 14:00 에 `110` 이 와서 고착돼도 False(cycle182 시간창).
  - (부가) 일일 리셋: `_reset_daily_state` 뒤 상태·단계 카운트·cap 이 0 이 된다.
- **AST**: `MARKET_STATUS_REPS` 원소 수 ≤ 3 · 그 leaf 에 `bypass_limit=True` 리터럴 0건 · `stale_watcher_core` 의 CB 판정이 HIGH 집합을 거르지 않는다(동시호가 가드 패턴 재사용) · `market_op_subscribe.py` 무변경.
- **backend-dev 에게**: 코스닥 대표 확정(`excg_dvsn_cd=="03"`·거래정지 아님). `record_market_op_event` 의 새 호출은 반드시 try/except 로 흡수한다(보드 콜백 보호 계약 — `handler.py:774` docstring). 상태 dict 는 기존 10 dict 와 분리한다(cycle149 분리 영속 원칙).
