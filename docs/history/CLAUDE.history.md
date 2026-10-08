> 원본: `CLAUDE.md` · 이관: 2026-09-17

루트 정본에서 걷어낸 경위·실측 수치·결정 근거. 규약 = [`README.md`](README.md).
원문 그대로 옮긴다(append-only). 사이클별 보고 원문은 [`../HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 에 있다.

---

## 🔴 최우선 과제 — 먼저 읽을 것

### 2026-08-25~08-28 — P0 / P0-1 (BFB·VCP 유령 키 `acml_vol`) 경위

**P0 요약 (2026-08-25 확정, 실측 검증 완료)** — `bull_flag_breakout` 과 `vcp_breakout` 의
매수 최종 관문이 `scanner.ticker_prices["acml_vol"]` 을 읽는데 그 키의 대입부가 전체 소스에
없었다(`risk.py` 는 4키만 기록). `acml_vol ≡ 0 < vol_threshold` 항상 참 ⇒ `check_buy_signal`
이 **구조적으로 `Signal.BUY` 반환 불가** ⇒ 두 전략만 전 기간 체결 0건(비중 합 25%).
기존 귀인 "진입 조건 미통과 탓"은 반증됐다(2026-08-25 하루만 21회 이상 충족).

**✅ P0-1 종결 (사이클 227 배관 → 사이클 228 게이트 전환, 2026-08-28)**: 사이클 227 이
배관(handler `fields[13]` → `on_tick(*, acml_vol=)` → `tick_volume`)+관측을 배포했고, 이틀
실측 would_pass **0/5**(관측/임계 8%→70% 시각순 상승 = 게이트가 잰 것은 거래량이 아니라
시계)로 래치 선행이 확정돼 사이클 228 이 게이트를 **tick_volume 실측 + 충족 래치 + 추격
상한(BFB 5.0/VCP 7.5)** 으로 전환했다 — **매수 개방**(비중 현행 BFB 0.15/VCP 0.10, 자문
실측 체결률 ≈0.5건/일·만기 위험 순자산 1.45%). 관측 마커 `[*_vol_gate_observe]` 은퇴
(would_pass 의미 반전 — 08-28 전후 로그 합산 금지). 228-B = `_effective_setup` 구조 레벨
stamp 우선 복원(첫 체결이 밟을 청산 경로의 P1 계약 위반 선제 시정). 상세 =
`src/engine/strategies/CLAUDE.md` 배너 + `_workspace/00_URGENT_WORKLIST.md`.

→ CHANGELOG: 사이클 227 · 228 행. 현행 게이트 규칙 = `src/engine/strategies/CLAUDE.md` 배너.

## 하네스 변경 이력 (요약)

2026-09-17 사용자 결정으로 정본에서 이 표를 통째로 걷어냈다 — 이력의 유일한 정본은
[`../HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 다. 15행 각각에 대응하는 CHANGELOG 행이
같은 날짜·같은 사이클로 존재하지만 **문구가 글자까지 같지는 않아**(측정: 15행 중 10행이 부분
일치), 규약 3의 "글자까지 같은 문단" 예외에 해당하지 않으므로 원문을 그대로 옮겨 둔다.
표를 유지하라고 지시하던 머리말도 같이 들어 있다.

→ CHANGELOG: 각 행의 `cycleN`

```
이 표는 **최근 ~15개 사이클의 한 줄 요약만** 유지한다. 각 행은 반드시 한 줄 — verbatim 금지. 신규 사이클 완료 시: (1) 이 표 상단에 한 줄 요약 1행 추가 + 가장 오래된 1행 제거(15행 유지), (2) 사용자 보고 verbatim·회귀 가드·영속 의무·검증 수치 등 상세는 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 에만 append.

| 날짜 | 사이클 | 한 줄 요약 |
|------|--------|-----------|
| 2026-09-16 | **15:30~16:00 완전 휴식** + 갭 홀드 제거 + bool 킬스위치 왕복 시정 + 손절 재주문 매핑 (cycle295 — 사용자 결정 09-15 "청산측으로도 참여하지 않는다. 15:30~16:00 은 완전 휴식" · 8영역 `order_engine.py` **단독** 승인 · `scheduler.py` 무접촉 3,726L · 명세 `_workspace/red/cycle295_gap_hold_removal_spec.md`) | 네 축. **(A)** cycle294 가 사용자 결정 「전환 1회」(명세 §0 재론 금지)를 착지 직후 적대 검증 CRITICAL 로 받아 **승인 없이** 3창으로 바꾼 갭 홀드(`krx_to_nxt_gap` 15:40~16:00 · `nxt_gap_to_krx`)를 철회 — `nxt_only_continuous_window` 46행 + `_spans`/`_subtract` 22행 + 다이얼 `tick_channel_gap_hold_enabled` 제거, `switch_windows()` 는 `pre_to_krx` **1개**. 킬스위치를 달았다는 것이 승인을 대신하지 않는다. **(B)** 라우터 **밖** 순수 술어 `_market_rest_now`(`market_state` 공개 API 파생, 시각 리터럴 0건)로 `execute_sell`·`execute_buy`·`_cancel_and_reorder`(**쌍** — 취소만 통과시키면 손절을 호가창에서 빼고 대체를 안 넣는다) 발사점 게이트. 라우터 clause 에 넣으면 `_strategy_exchange_async` 가 `_probe_nxt_downgrade_base` 를 먼저 불러 `nxt_tradable=False` 코호트(마스터 83.2%)를 `base="KRX"` 로 만들고 clause 1 `base_krx` 에서 즉시 반환 → 컷이 가장 필요한 다수를 통째로 비껴간다(15:35·15:45·16:05 실행값 전부 `('KRX','base_krx')`). 1분×1,440분×7날짜 스윕으로 발화 구간 정확히 15:30~16:00, 프리장·정규장·KRX 애프터 발화 0. 15:30~15:40 은 **순이득**(현행은 거부를 받고 그 거부가 다음-09:00 TTL 로 16:00~20:00 청산 4시간을 잠갔다). **(C)** 🔴 09-15 실증 — 10:0x `PUT {"gap_hold_enabled":false}` 가 `gap_persisted:true` 를 돌려주고도 15:41:56 갭 전환 7건이 그대로 일어났다. `set_…(False)` → `_set_string(key,"false")` → DB `{"value":"false"}` → `_get_bool_or_none` dict 분기 `return bool(v)` = `bool("false")` = **True**. 아래 문자열 정규화 분기는 dict 로 감싸인 값에 도달 못 함. PUT 직후 메모리는 False 지만 5분·120초 refresh 가 True 로 되돌린다 = **끄면 켜지는 킬스위치**. 영향 = cycle294 의 bool 다이얼 2개뿐(`set_auto_start` docstring 이 "왕복 불변식 = split-brain 해소 핵심" 을 이미 경고했는데 답습 안 됨). 시정 = dict 분기 정규화(`"maybe"`/`""` → None, bool 아닌 문자열을 True 로 읽는 것이 결함의 본질) + 두 setter `_set_bool` + 왕복 불변식 테스트(모든 bool 다이얼 동적 스캔). 즉시 조치 = 09-15 16:2x DB 를 JSON boolean 으로 직접 교체 → 09-16 15:30~16:00 전환 0·주문 0 실측. **(D)** `order_engine.py:2505` 손절 잔여 재주문(`_cancel_and_reorder`, `PARTIAL_FILL_WAIT=30` 뒤)이 프로덕션 `place_order` 5곳 중 **유일하게** 반환값을 버려 매핑 0종 → 체결통보가 `_order_strategy` miss → `trade_history` miss → `:2233` `"momentum"` 오귀속 + `_order_qty` 부재로 `ordered_qty` 가 통보 수량으로 대체돼 **부분체결이 전량으로 읽힘**(`:1877`) → `result=` 로 받아 5종 + `_completed_orders.discard`(필요한 값 전부 스코프에 있었다). **적대 검증 CRITICAL 1·HIGH 5 전부 시정** — ① 🔴 명세 §9 Q2 권고(특별 개장일 fail-open = 실제 틱이 오면 컷 해제)가 **틀렸다**: `risk.py:585` 가 `ticker_last_tick[t]=now` 를 쓰고 같은 콜스택에서 `:688 execute_sell` 을 부르므로 나이가 **항상 0.0s** = 컷이 항상 해제 · 게다가 KRX K5(15:30~16:00 `AFTER_CLOSE_FIXED`)가 정규장과 **같은 채널** `H0STCNT0` 로 실제 체결 프레임을 보내(09-16 실측 fresh 41~102) 신선도는 해제 키가 될 수 없다 → **fail-open 전면 철회**. 특별 개장일(지연 개장) 15:30~16:00 이 연속체결 중인데 컷이 30분 무음 차단하는 위험은 **알려진 한계로 잔존**(§4-6, 연 1회 규모) ② `POST /api/trading/manual-sell` 이 컷을 비껴가는데 미문서화 → 명시 면제 + 응답 경고 + AST 봉인(운영자 비상 매도를 30분 막는 것은 사용자 결정 사항) ③ 런북이 폐기 키를 지시하고 PUT 은 `success:true` 로 조용히 삼킴 → 런북 삭제 + 무음 no-op 경고 ④ (D) 행위 가드 **0건**(뮤테이션 11종 전부 ESCAPED — "고침 자체를 꺼도" 초록) → 신규 5건 ⑤ 트리 digest 미갱신 ⑥ `test_f4` 선재 시각 드리프트(`setter()` → `setter(DAY)`). 뮤테이션 55종 38 KILLED / 14 ESCAPED → 시정 후 봉인. 검증 = **10,550 passed / 0 failed** · cycle295 9파일 207 · `TZ=UTC` 동일 · sha 핀 `order_engine` 9 + `realtime/CLAUDE.md` 4 + 트리 digest. `tick_channel_switch.py` 는 docstring 1곳(창 3→1 사실 정정)만. **장중 킬스위치 없음**(cycle287 과 같은 방향의 결정 — 컷은 16:00 에 스스로 끝나고 잘못돼도 주문이 안 나가는 쪽) |
| 2026-09-15 | 프로세스 분리 **4단계 방향 기록 — 메시지 기반 5프로세스** (사이클 번호 없음 · **코드 0줄** · 사용자 원안 2026-09-15 · 정본 [`docs/architecture.md`](docs/architecture.md) **15.5** 신설 380행 · 구 15.5→15.6 · 구 15.6→15.7) | 승인·착수 **전**이다 — "할 것이다" 가 아니라 **"이렇게 하려면 무엇이 필요하다"** 로 읽는다(1·2·3단계와 같은 지위). 구조 = 전송 전담 2프로세스(**W** KIS WS 수신·파싱·라우팅 / **R** KIS REST 송수신 — 주문 전용이 아니라 **모든 프로세스가 공유하는 단일 게이트웨이**) + 업무 3프로세스(**1** 시세·전략평가 · **2** 주문 · **3** 체결). 3단계(15.4)가 업무 축으로 갈랐다면 4단계는 **전송 수단 축으로 먼저 가르고 업무를 그 위에 얹는다** — 그 분할선 차이가 15.4 보류 근거 ①②③ 을 없앤다: ① 공유 리미터를 **만들지 않고** `_semaphore(20)`(`src/api/base.py:28`)·라벨 `Semaphore(18)`(`:346`)를 R 안으로 되돌린다(조건 = R 이 **정확히 1개**) ② 토큰 발급·`.token_cache` 는 R 단독이고 **W 는 access_token 없이 산다**(`get_approval_key()` 가 `/oauth2/Approval` 을 직접 POST 해 `_GLOBAL_ISSUE_LOCK` 을 타지 않고 `src/realtime/**` 의 `get_token()` 호출 0건 — 실측) ③ W 가 1개면 체결통보 메인 세션 단일은 형식상 자동 성립하나 **체결→포지션 반영이 두 홉**이 되어 ③이 지키려던 것은 오히려 나빠진다. 🔴 **④ A-ATOMIC 의 귀속이 통념과 다르다** — "주문 프로세스가 1개라서" 가 아니라 **"전략평가가 1개이고 그 안에 전 전략 state(`total_investment`·`positions`·`pending_buy_amounts` + `registry.is_ticker_blocked_for_buy()`)가 모여 있어서"** 유지된다 ⇒ 파생 규약 = **전략평가는 전략별로 쪼갤 수 없다**. **4단계는 3단계를 대체가 아니라 흡수(상위집합)하므로 3단계 선행은 불필요** — 먼저 하면 공유 레이트리미터·분산 발급 잠금을 만들었다가 4단계에서 버린다. 메시지 토픽 7종(T1 `md.tick` 은 **`tr_id` 를 반드시 싣는다** — cycle294 매수 축 술어가 "구독 사실" 을 읽어 채널 정보가 빠지면 재현 불가 / T7 `sub.control` 은 사용자 도식에 없던 화살표). T3 가 수량을 담는가 = **B안 권고**(전략평가가 사이징까지 하고 완성 수량을 보낸다 — 원자 구간이 깨지는 게 아니라 전략평가 **안으로 이동**, `_apply_budget_limit` 이 이미 순수 동기라 이동 비용 0), **C안(주문이 사이징) 기각** = 터틀 분기가 `self._entry_atr[ticker]` 를 스탬프하고 그 유무가 ATR 손절이냐 고정% 손절이냐를 가르므로 사본에 스탬프가 남으면 **로그에도 안 보이는 매매 행위 변경**이다. FEP 도식(`docs/order_exec_architecture.png`)의 "모주문번호를 주문라인수로 나머지 연산" 은 **문자 그대로 적용 불가**(`CancelType.REVISE` 참조 0건 · 신규 주문 시점에 `order_no` 부재) ⇒ **우리 파티션 키는 `ticker`**(같은 ticker 의 주문·취소는 같은 큐 FIFO · 취소→재주문 쌍은 fire-and-forget 금지), 동형 위험은 **"취소가 원주문을 앞지른다"**(쌍 3개, 오늘은 `await` 한 줄이 순서를 지킨다). 지연 = 늘어나는 항 **one-way ~0.023ms**(UDS+JSON n=20,000 실측 RT 중앙값 0.046ms·p99 0.120·max 2.59) vs 줄어드는 항 **수신 루프 최악 blocking ≈3.7초**(매도 3회 재시도 sleep 이 `risk.on_tick` 인라인) ⇒ 판정은 "홉이 싸다" 가 아니라 **"오늘의 인라인 구조가 이미 더 비싸다"** 쪽이다. 버스는 축마다 갈린다 — 틱(하루 1.25M~1.75M 프레임 **추정**)에 DB 테이블 큐+폴링은 이식 불가, 애프터 폴백 가격은 **의사 메시지가 싣고 가야** `_AFTER_EXIT_GIVEUP_THRESHOLD=5` 예산을 헛되이 깎지 않는다. 🔴 **15.4 표에 없던 다섯 번째 제약** = 주문번호 매핑 6종과 `_completed_orders` 가 주문↔체결 **양방향**으로 경계를 가로지른다(그 창은 사고가 아니라 루트 `CLAUDE.md` 금기가 설계한 창이고 4단계는 그것을 **정상 경로**로 만든다) ⇒ **B안(매핑 DB 영속) 권고**, C안은 `_order_strategy` miss 폴백이 `"momentum"` 하드코딩(`order_engine.py:2233`)이라 오귀속이 조용히 흐른다. 새 계약 둘 = **멱등키**(`trade_history` 부분 UNIQUE 는 중복 주문을 **못 막는다** — 축에 `order_no` 가 있어 중복 배달 두 건은 서로 다른 ODNO 로 둘 다 INSERT 된다 ⇒ 생산자 `intent_id` 필요, `signal_seq` 는 오늘 없는 신규 개념) · **청산 큐 제거는 체결 확정 이벤트로만**. `scheduler.py`(3,726L)는 여섯 번째 프로세스가 아니라 **공통 라이브러리 + 얇은 시계**로 분해하고 작업은 소유 프로세스가 갖는다(21:30 `_reset_daily_state` 가 **분산 barrier** 가 되는데 실패 규약이 지금 없다). 제약 A~I = A 역할당 정확히 1개(늘릴 수 있는 축이 사실상 없다 — 목적이 확장성이 아니라 **배포·크래시 격리**다) · B `healthcheck:` 가 4 compose 파일 **전부 0건**(실측) · C 토큰 캐시 R 전용 · D 즉시 반영 킬스위치가 RPC 가 되며 **폴링 5분 강등 금지** · E 라우트 21개 중 **7개**가 `trading_scheduler` 직접 참조 ⇒ FastAPI 는 전략평가에 붙이고 **그 프로세스는 4단계 뒤에도 가장 재시작하기 어렵다** · F 공용 부트스트랩 분리가 **사실상 첫 커밋** · G 공유 로그 파일 자정 rollover 경합 = **확정 결함** + 밀리초 없음 + `system_logs` 출처 컬럼 없음 · H 단일 이미지 + 서비스별 CMD · I 부분 고장 규약 신설. 🔴 **지금 착수를 권고하지 않는다** — cycle248 이 장중 고통의 **86%** 를 이미 없앴고(최근 90일 커밋 363건 중 장중 125건이 만진 고유 파일 510개에서 390개가 `none`·49개가 `frontend`), 4단계가 실제로 자유롭게 하는 몫은 **장중 파일 터치의 약 1.6%**, 크래시 격리 상금에 대응하는 **사고 기록 0건**이다(단 `restart: unless-stopped` 가 조용히 되살린 재기동은 문서에 안 남으므로 기록 부재가 사건 부재의 증명은 아니다). 더 싼 대안 넷(① 관측 축 선행 ② 휘발 상태 복구 실증 ③ scheduler 분해 ④ 1단계 `llm_worker`)은 전부 **프로세스 0개 추가**다. 착수 전 **미확인 숫자 5건**·**사용자 결정 5건**은 `_workspace/00_URGENT_WORKLIST.md` 에 등재했다. 부수 = 15.4 stale 앵커 정정(`websocket_pool.py` `_EXECUTION_NOTICE_TR_IDS` :59→**:64** · `_enforce_main_only_execution_notice` :62→**:109** · `order_engine.py` A-ATOMIC :314~:355→**:741~:782~:784**) + 그 실측 중 발견한 **오늘 라이브에 도달 가능한 결함 2건**(`order_engine.py:2505` · `scheduler.py:1583`)을 워크리스트 별도 절로 등재. **코드·테스트 diff 0**(`src/realtime/CLAUDE.md` 는 8영역 sha 핀 대상이라 무접촉) |
| 2026-09-14 | 🔴 시세 채널 **3단계 시간축 전환 — 통합 채널 소멸** + 착지 직후 적대 검증 CRITICAL 4·HIGH 4 시정 (cycle294 — 사용자 결정 "H0UNCNT0 는 아예 쓸 생각이 없어"(09-07 결정의 완성, 재론 대상 아님) · 명세 `_workspace/red/cycle294_stage3_time_axis_spec.md` · 8영역 5파일 승인 중 **4파일 접촉**(`scanner`·`risk`·`websocket`·`websocket_pool`, `order_engine.py` 는 diff 0) · `scheduler.py` 무접촉 3,726L) | 정상 경로에서 통합 채널을 **반환하지 않는다** — 프리장 `H0NXCNT0` / 정규장+애프터 `H0STCNT0`. 신규 leaf 2 = `tick_channel_clock.py`(시각축, 순수·never-raise·**시각 리터럴 0건** — 경계 셋이 전부 `market_state.get_market_table(on_date)` 공개 API 파생) + `tick_channel_switch.py`(전환·자동 원복, 120초 stale watcher 안에서 never-raise). fail-open 이 층마다 다르다 — L1 표 실패→KRX(09-14 16:39 라이브 실측이 확정한 채널 · 구독 수명의 92% 가 KRX 창 · 셋 중 **모의(VTS) 지원은 그것뿐**) / L2 속성 실패→**프리 창 NXT**(비대칭: 모르는 종목을 KRX 로 보내면 진짜 `nxt_true` 의 프리장 체결을 새로 잃지만, NXT 로 보내면 진짜 `nxt_false` 는 그 구간에 시장이 없어 잃을 것이 0) / L3 `off` 만 통합. 🔴 **매수 축 술어를 「채널」에서 「코호트」로 바꿨다** — 3단계는 `nxt_true` 까지 전 종목을 전용 채널로 보내므로 cycle293 술어를 그대로 두면 momentum·VB·LTV·BFB·VCP **5전략의 틱 매수가 통째로 죽는다**(그 5전략은 틱이 유일 매수 경로다). **착지 직후 적대 검증 3렌즈가 CRITICAL 4 + HIGH 4 를 찾아 전부 닫았다** — ① 🔴 **15:40~16:00 은 KRX 에 연속 체결이 없고 NXT 애프터만 열려 있다**(표 실측: K4 종가단일가·K5 시간외 종가 → 16:00 K6 애프터 / N6 는 15:40 부터 continuous). 그 20분을 KRX 로 덮으면 `nxt_true` 보유의 손절 트리거가 **매일 20분** 사라진다(INV-1 위반). 사용자 결정 「전환 1회」의 근거였던 「cycle287 이 애프터 주문을 KRX 로 보내므로 KRX 가격이 정합」은 **16:00~20:00 에만 참**이다 — `_route_exchange_by_clock("SOR", side="sell")` 실행값이 15:45·15:55 는 `("SOR","krx_unsupported_keep")`, 16:05·19:00 은 `("KRX","krx_by_clock")` 다. 그 원칙을 그 구간에 적용하면 평가 가격도 NXT 여야 한다 → **보유(HIGH)만** NXT 추종(LOW ~130종목 왕복은 KIS 「비정상 케이스 2」), 속성축은 그 구간에도 이겨 `nxt_false` 보유는 KRX 유지, 킬스위치 `tick_channel_gap_hold_enabled` ② 자동 원복이 **진짜 고장에서 구조적으로 발화 못 함**(표본이 「전환 성공한 HIGH」뿐 → 「지금 KRX 에 앉은 HIGH」로 / 교차 확인이 전원 침묵을 **결론**지어 기각 → 비결론 + 2×probe escalation / 판정 **전에** 래치 → 결론적 판정에만) ③ 원복이 보유 종목에 **break-before-make + `bypass_limit=False`** 를 09:03 라이브 구간에 걸고 반환값도 안 읽음 → make-before-break + 결과 집계 ④ LOW 전환 실패가 세션 튜플 0 + 라우팅 잔존 = **20:00 까지 자가 치유 없는 구독 좀비** → 라우팅 동행 pop / 고아 튜플은 로컬 집합에 되돌려 20:00 회수 가능하게 ⑤ 🔴 코호트 스탬프가 **07:59 도장 창에 1회 기회**뿐이라(LOW 는 `already_in_pool` skip 이 리졸버보다 앞) 08:08 진실 복원 뒤에도 미스탬프로 남아 매수 축이 ≈38종목에서 샘 = 미승인 B-2 부분 발생 → `restamp_cohorts` 를 5분·**120초** 두 배선에 ⑥ `[tick_buy_gate]` 가 스탬프 **전**에 하루 1행이라 ⑤를 영구 은폐(항상 `unstamped=전체`) → 시각 구간별 1행(**판단은 정규장 창 행으로**) ⑦ `enforce_low` 의 HIGH 제외가 레거시 재라우팅에 무력화 + 풀 병행 dict 발산(OPSP0003 + 영구 고아) → `enforce_low` 통과 + 풀 진입에서 재라우팅 1회 적용 ⑧ 창 끝을 넘겨 계속 전환 → **종목마다 경계 재확인**(경과는 벽시계가 아니라 `now`+monotonic). 그 밖 = 출처 조회 실패가 `logger.debug` 라 **상관된 매수 개방이 무음**이던 것 → `[no_feed_provenance_unavailable]` WARNING 1회/일 · `day_reverted` 래치 영구화 차단 · 전환 대상에서 cycle253 프로브·비-TICK(체결통보) 라우팅 제외 · `off`/`disabled` 로 빠져나가도 미전환 잔여를 남김 · hot path 의 표 재구성을 날짜 메모로. 다이얼 5키 전부 `system_config` 축(`param_catalog` 편입 금지), 즉시 반영 `PUT /api/realtime/tick-channel-mode`. ⚠️ **배포만으로는 아무 일도 일어나지 않는다** — 기본 모드가 `observe` 라 07:45 부팅 전에 DB 에 `enforce` 를 넣어야 한다. 🔴 **남은 미해결 = N-1**(프리장 08:00~08:50 `H0NXCNT0` 라이브 프레임은 내일 08:00 전에 실증 불가 — 09-14 프로브는 같은 채널의 **애프터 구간** 대리 증거다. 자동 원복은 09:03 에야 돌아 그 창을 못 잡는다). 검증 = ast **1,614** · engine **5,963** · 나머지 **2,762** / 0 failed. `scheduler.py`(3,726L)·`order_engine`·`session`·`strategy_registry`·`api/order`·`auth/**`·`handler.py`·`market_state.py`·`tick_volume.py`·전략 7파일 + `strategy_base` diff 0 |
| 2026-09-14 | 시세 채널 **속성축 리졸버 2단계** — 등가 비교 25+곳을 집합 멤버십으로, 매수 축은 닫은 채 (cycle293 — 명세 `_workspace/red/cycle293_tick_channel_resolver_spec.md` · 8영역 5파일 승인(`scanner`·`websocket`·`websocket_pool`·`order_engine` + **`risk.py` 2차 승인**) · `scheduler.py` 무접촉 3,726L) | 통합 채널 `H0UNCNT0` 은 `nxt_tradable=False`(마스터 **83.2%**) 종목의 체결 프레임을 **보내지 않는다** — SUBSCRIBE 는 SUCCESS ACK 를 받으므로 구독은 살아 있는 것처럼 보이고 프레임만 영구 0 이다(09-14 실측 `[tick_coverage] stale=64/146`, stale 표본 15/15 전부 `nxt_false`). **종착지는 통합 채널 폐기**(2026-09-07 사용자 결정 + 09-14 재확인)이고 이 사이클은 그 **2단계 = 배관 부채 상환**이다 — `scanner.tick_tr_id_for(ticker, *, priority)` 도입 + 9파일의 `tr_id == TICK_TR_ID` 등가 비교를 단일 정본 집합 `TICK_TR_IDS` 멤버십으로 전환(하나라도 남으면 옮긴 종목이 `get_subscribed_tickers()` 에서 **조용히 사라져** K stale watcher 블라인드·슬롯 누수·5분 재SEND·분모 감소가 한꺼번에 생긴다). 판정은 **첫 구독 시점 1회**(⚠️ **cycle294 3단계가 이 규약을 뒤집었다** — 전환 창 안에서 살아 있는 구독을 옮기고 fail-open 도 통합이 아니라 시각 기반 전용 채널이다. 이 문장은 2단계 당시 기록으로 읽는다). 출처 검사 (`raw ? 'cptt_trad_tr_psbl_yn'`)가 07:45~08:08 KRX 도장 창을 막는다 — 그 창에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있고 실측 **2,344/3,583(65.4%)** 이 도장 상태, 그중 **420종목은 실제 `True`** 였다(그대로 믿으면 진짜 NXT 종목을 NXT 체결 못 받는 채널로 보낸다). 🔴 **매수 축은 열지 않았다(B-1)** — 채널을 열면 시총 1,000억↑ 유니버스의 **64%** 가 momentum·VB·LTV·BFB·VCP 5전략 매수 평가에 새로 노출되고(BFB/VCP 는 `acml_vol` 실측이 들어오며 `vol_gate_no_data` fail-closed 까지 풀린다) 그건 미승인 매매 행위 변경이다. **적대 검증 4렌즈가 CRITICAL 2 + HIGH 6 을 잡았다** — ① 매수 게이트 술어가 리졸버 **재호출**이라 킬스위치 `off`·모드 하강·`nxt_tradable` 복귀·출처 후퇴 **네 경로**에서 프레임은 계속 전용 채널로 오는데 게이트만 풀렸다(사고 중 누르는 안전 조치가 매수를 연다) → **구독 사실**(`_ticker_to_tr_id` → `applied_tick_channel`)로 교체 ② `[tick_channel_dual_detected]` 가 `pool.subscribe` 중복 분기 안에 있어 §4-C 가 맡긴 **풀 우회 2곳**(`scheduler.py:1382`·`:2728` = `kis_ws.subscribe` 직접)에 구조적으로 도달 못 함 → **전 세션 `_subscriptions` 전수 대조**(`detect_dual_tick_channels`)로 이동 + 정상 경로의 요청 거부는 마커 분리(`[tick_channel_request_denied]`) ③ `ensure_fresh` 유일 호출자가 stale watcher 라 **07:59 사전 구독 코호트가 통째로 미분류** → 구독 전 warm-up ④ `[tick_channel_flip]` 무cap(틱당 1행 = cycle237 계열) → cap ⑤ `PROBE_EXCLUDED_TUPLES` 가 라이브 구독과 **같은 식별자**인데 회수 경로가 하나뿐 → 날짜 자기 회수 + `unsubscribe_all`/`stop` clear ⑥ 킬스위치 라우트 테스트 **0건**(cycle287 실패 재현 뮤테이션 2건 ESCAPED) → 3종 신설 ⑦ 공허 가드 3건(A4 `issubset` 이 집합 확대를 못 막음 · A5 이름 존재 검사가 주석에 통과 · A12 부분문자열이 5곳 중 1곳 삭제를 통과) 조임. 킬스위치 `system_config.tick_channel_resolver_mode`(기본 `observe` = **행위 0**) + `PUT /api/realtime/tick-channel-mode` **즉시 반영**. ⚠️ `off` 는 이미 옮겨진 구독을 되돌리지 않지만 매수 게이트는 구독 사실을 보므로 계속 닫혀 있다. 검증 = ast **1,531** · engine **5,858** · 나머지 **2,7xx** / 0 failed · `scheduler.py`·`session`·`strategy_registry`·`api/order`·`auth/**`·`handler.py`·전략 7파일 diff 0 · sha 핀 13곳 + 트리 digest 갱신 |
| 2026-09-14 | `scheduler.py` 라인 예산 확보 — VI(H0UNMKO0) 구독 176줄을 leaf 로 추출 (cycle292 — 사용자 승인 "스케쥴러 리팩터 오늘 수행하자" · 명세 `_workspace/red/cycle292_scheduler_market_op_leaf_spec.md` · **순수 리팩터, 행위 변경 0**) | 상한 3,900 에 여유가 **3줄**뿐이라 다음 사이클이 손댈 자리가 없었다. `_subscribe_market_operation_tickers` 본체를 신규 leaf `src/engine/market_op_subscribe.py::subscribe_market_operation_tickers` 로 옮기고 scheduler 에는 **5줄 위임 wrapper** 만 남겼다 — 3,897 → **3,726L**(여유 174). 본체는 `self.` → `scheduler.` **6곳** + 4칸 dedent 뿐이고, 변환 후 `ast.get_source_segment` sha 가 명세가 미리 산출해 둔 값과 일치해 **라인 단위 동일이 기계 증명**됐다(1회용 핀, 영속 가드 미편입). 🔴 이 사이클의 진짜 위험은 추출이 아니라 **가드가 조용히 공허해지는 것**이었다 — cycle214/221 의 봉인이 전부 "…가 0건" 부정 단언이라 본체가 떠나면 남은 wrapper 노드를 재며 **전부 참**이 된다(08-19 OPSP0008 사고 = 메인 45/41 → 보유 4종목 ~58분 tick blind 재발 방지가 소리 없이 사라진다). 그래서 AST 가드 4파일을 leaf 로 **재조준**하면서 각각 **양성 대조군**을 심었다(`ws.subscribe ≥ 1` · `bypass_limit` 키워드 ≥ 1 · `kis_ws_pool` 참조 존재 · `State.OPEN` 리터럴 + 판정식 + 함수-로컬 import 3중). 그 양성 대조군이 **HEAD 에서 새던 구멍을 실제로 닫았다** — `bypass_limit` 키워드를 통째로 지우는 뮤테이션이 HEAD 가드에서는 19 passed 로 ESCAPE 했다. ⚠️ **함수-로컬 import 5줄을 모듈 최상단으로 올리면 안 된다**(최대 위험) — 회귀 4파일이 정의 모듈 속성을 monkeypatch 하므로 승격 시 patch 가 무력화되고 `_ws is None → return 0` 조기 반환이 부정 단언을 조용히 초록으로 만든다(승격 뮤테이션에 행위 22건 red = seam 이 load-bearing 임을 실증). logger 는 `getLogger("src.engine.scheduler")` 고정(마커 5종이 전부 기존 — `__name__` 이면 `system_logs` 접두가 갈려 판독 사슬 파괴). 뮤테이션 **37종 전수 KILLED**(3렌즈 합산, ESCAPED 0). 적대 검증이 문서 축에서 잡은 것 = `/sync-docs` 모듈 누락 자가 점검이 **부분 문자열 매치라 거짓 통과**(로그 마커 `[market_op_subscribe_skip]` 가 모듈명을 포함해 통과시켰다 → `.py` + 단어 경계로 조이자 누락 9건이 드러났다 — 1건은 cycle292 자신의 신규 leaf, **선재 8건**(engine 1·db 4·api 1·routes 2)은 별건 카드) · `architecture.md` 의 3중 거짓("후보 합집합"=cycle221 F2 로 삭제 / "HIGH bypass"=cycle230 폐기 / "LOW cap=20"=cycle214 가 60) · `market_operation_monitor.get_market_op_active_tickers` docstring 의 소비처 2개가 **둘 다 거짓**(프로덕션 호출자 0건). 검증 = 백엔드 **10,03x PASS / 0 FAIL** · `TZ=UTC` · `--log-level=DEBUG` 동일 · 8영역·전략 7파일 diff 0. 후속 = `test_cycle287_ast_scope.py::test_s1d` 가 비교 양변을 모두 라이브 FS 에서 만들어 **구조적으로 공허**하다(신규 파일 탐지는 `test_s1b` 의 하드코딩 목록이 한다) · 선재 누락 9건 · `get_market_op_active_tickers` dead code 처분 |
| 2026-09-13 | 장운영상태 화면에 **야간작업 타임라인 + 실시간 VI·서킷브레이커** (cycle285 — 사용자 발의 "매매 외 작업들 완료현황도 함께 있었으면, 실시간 장운영상태까지 가져올 수 있으면 더 좋고" · 명세 `_workspace/red/cycle285_market_state_ops_panel_spec.md` · 8영역 무접촉 = 사전 승인 범위 · 9 에이전트) | 목적 = **월요일 저녁을 SSH grep 없이 화면으로 보기**(이번 세션에서만 EC2 에 붙어 `system_logs` 를 grep 한 일이 여러 번 있었다). 섹션 A(지금 시장은) = 백엔드 신규 0, 기존 `GET /api/realtime/market-operation` 재사용(cycle186 쿼리 키 공유로 RealtimeHealth 와 캐시를 나눈다). 섹션 B(오늘 야간작업) = 신규 `GET /api/market-ops`(`src/routes/market_ops.py`), 14행 시각순, 상태 10종. `/api/market-state` 를 확장하지 않고 **별도 라우트로 분리**한 이유 = 그쪽에 AST 가드 2개(시계 호출 1회·시각 리터럴 0건)와 픽스처 byte 동일 강제 사슬이 걸려 있다. 🔴 **시각 리터럴 0건** — 예정 시각은 전부 `scheduler.TIME_*` 에서 읽고 주석의 `16:10` 류도 상수명 인용으로 교체했다. 명세 §4 를 코드로 강제 = "이벤트 수신 N종목 기준" **항상** 표시(`H0UNMKO0` 은 005930+보유·익일청산뿐이라 "VI 0건" 이 "VI 없음" 으로 읽히면 운영자가 없는 안전을 믿는다) · 서킷브레이커 **"추정"** 표기 + 근거(halted/observed·사유 표본)를 의심하지 않을 때도 노출 · 세션 4분기(관측 중/장 종료/세션 종료/조회 실패)로 21:30 `_reset_daily_state` 뒤의 0 을 "이상 없음" 으로 읽히게 하지 않음 · 읽기 전용(재실행 버튼 0). **적대 검증 3렌즈가 "완료로 보이는데 사실 확인 안 됨" 4건을 잡았다** — `full_universe_load` 가 아침 부팅 증거로 20:00:05 실행을 하루 종일 완료로 오분류 / `stock_master_daily_load` 가 전날 실패→다음날 catch-up 마커로 오분류 / 수동 새로고침이 예정 전 증거를 완료로 위조(셋 다 같은 근본 원인, 신규 `_evidence_after_schedule` 이 한 번에 닫음) / `metrics_snapshot` 이 21:30 실행 여부와 무관하게 항상 "완료(최종반영)"(→ `_is_complete_report` 4축 판정기로 완전판 실재 시에만). 그 밖 = 휴장 확정이 이미 증명된 `done` 행까지 뒤집던 것(→`not_fired`/`scheduled` 에만) · 조회 실패를 "미발화" 로 확정(→`_degrade_on_error`) · CB·VI 배지가 정상과 sRGB 거리 ≈10.5 로 구별 불가(cycle261 결함 계열, →red-200/900·beige-200) · 신선도 미표시(→`refetchOnWindowFocus` + "N초 전 수신"). 구현자 자체 검증도 1건 — `snapshot_pass` 를 `is True` 로 비교했는데 실제로는 정수 `1` 이 심긴다(`1 is True` 는 거짓, 영원히 오분류될 뻔했다). 쿼리 왕복 3회 전량 Index(-Only) Scan ~3ms. 검증 = 백엔드 **9,595** PASS · TZ=UTC 63 · 프론트 **787** PASS(90파일) · tsc 0 · 실 postgres:15 왕복 4케이스. 8영역·`scheduler.py`(3,897L)·`market_state.py`·전략 7파일 diff 0. 운영 실측(일요일) = `is_trading_day False/kis` · 상태 분포 `holiday 12 · skipped_weekly 1 · unknown 1`(휴장일에 안 돈 작업이 `failed` 가 아니라 `holiday` = §4-4 의도대로). ⚠️ 운영 참고 = 컨테이너 재시작 직후 **60초 안**에는 개장 여부가 `확인 불가` 로 뜬다(토큰 준비 전 조회 실패가 음수 TTL 60초로 캐시된다) — 결함이 아니라 "모른다를 개장으로 보여주지 않는" 설계다. 후속 = **VI 구독 확대**(`src/realtime/**` = 별도 승인, 사용자 결정 ⑥ 여전히 열림) · `data_load_tasks` 168h 상수 통합 · MarketState 배지 대비 자동 가드 |
| 2026-09-13 | 장운영상태 표 주문유형코드 27~47 명칭 확정 + SOR 폐기 표시 (cycle289 · 287b — 사용자 지적 "27~47이 전부 확인필요 상태" · "SOR 내용들 UI에서 일단 걷어내자") | 공지 2026-09-09 원문 표기를 그대로 옮겨 `confidence` `name_unconfirmed`→`confirmed` 10개(27~29 NXT GTP · 41~47 KRX 애프터), 확인필요 잔여 0. `note` 에 코드값만으로는 알 수 없는 규약(GTP 08:50 일괄취소 · 애프터 시장가/ETP 불가)을 남겼다. **SOR** = `param_catalog` `Choice(deprecated=True)` + 라벨 "SOR (폐기 — 주문에 쓰이지 않음)" — **어휘에서 지우지 않았다**(당시 운영 DB 7전략이 전부 SOR 이었고 어휘를 먼저 좁히면 그 값 명시 저장이 422 다. ⚠️ **그 뒤 2026-09-13 결정 D3 로 7전략 전부 `NXT` 로 PUT 됐다** — SOR 잔여 0, 2026-09-15 실측 재확인. `test_n3b` 가 배포 순서 `코드 → D+1 → 카탈로그/프론트 → DB` 를 강제한다). `<option>` 은 브라우저가 스타일을 제한해 `choice.deprecated` 회색 처리가 안 닿으므로 **라벨 자체가 유일한 폐기 신호**다. `market_state` `FINDINGS` 2번("현재 전 주문이 SOR 이므로")이 cycle287 배포로 **거짓**이 되어 시정 + 폐기 각주 1행(총 3행, 프론트 변경 0으로 화면에 뜬다). 🔴 `EXCHANGE_ORDER` 의 SOR 열은 **삭제하지 않는다** — 그 표는 "KIS 가 받는가" 의 사실 표이고, 지우면 41~47 의 SOR 지원이 **확인 필요**라는 사실까지 사라져 cycle282 의 "미확인을 미지원으로 접지 않는다" 를 깬다(`test_n4`/`n4b` 봉인). 픽스처 4개 재생성 · sha·트리 digest·findings 개수 핀 갱신. 백엔드 9,523 · 프론트 775 PASS |
| 2026-09-13 | 시각이 거래소와 호가코드를 정한다 — KRX 애프터마켓 청산 개통 (cycle287 — 사용자 확정 "프리장은 NXT, 나머지는 전부 KRX로" · "애프터시장에서는 41-47만 쓰면 되잖아, 호가코드만 교체" · 호가유형 44 선택 · 8영역 `order_engine.py`·`api/order.py` 승인 · 14 에이전트 오케스트레이션) | 구간별 (거래소, 1차, 폴백) = 프리장 08:00~09:00 base(NXT) 유지·`00`+step_down(5) / 정규장 09:00~15:30 **KRX**·`01`→`00` / **휴식 15:30~16:00 현행 유지** / 애프터 16:00~20:00 **KRX**·**`44` 최유리(unpr=0)→`41`+step_down(5)**. 판정은 `market_state.MARKET_TABLE` 만 읽어 `order_engine.py` 안 시각 리터럴 **0건**이고, K6 의 `effective_from=2026-09-14` 덕분에 **배포해도 09-14 09:00 까지 행위 변화 0**. **44 는 시장가가 아니다** — 반대편 최우선호가 지정가라 실질 최악이 1틱(20~21bp)으로 기존 폴백 5틱(101~106bp)보다 **작다**(±30% 는 시장가 한정). `ORD_UNPR=0` 근거 = 비대칭(0 이 틀리면 즉시 거부가 알려 주고 41 폴백이 받는다 / 가격이 틀리면 미체결 잔존 = 손절 **무음** 실패). **폴백은 분류에 의존하지 않는다** — 44 거부 사유 5가지 중 어느 것도 현재 msg1 키워드에 걸릴 근거가 없고, 원문을 모르는 채 키워드를 추측하면 틀렸을 때 다음 사람이 "이미 처리했다" 고 오독한다. 폭주 봉인 3종(TTL 항상 등록 · 종목당 5회 포기 래치 + `[after_exit_giveup]` CRITICAL · 익일청산 전환). 킬스위치 `order_exchange_clock_mode`(기본 `enforce`) · `after_market_exit_division`(기본 `"44"`). 🔴 **둘 다 `param_catalog` 미등재라 `PUT /api/strategies/{id}/params` 가 `unknown_key` 로 422 다 — 장중에 끌 수 없다.** 전략 `DEFAULT_PARAMS` 에 키를 넣어야 PUT 이 통하고 그건 매매 행위 변경이라 별도 승인 + `domain-consult` 대상이다(전략 7파일 diff 0 제약으로 이 사이클엔 못 넣었다). 급성 시 되돌리는 수단은 1커밋 revert + 재배포뿐이고, **그 재배포 자체가 16:00~20:00 에는 금지하려는 재시작이다**(D8). 코드 서술 정본 = `src/engine/CLAUDE.md` 의 "장중 킬스위치 없음" 절. 적대 검증 4렌즈 CRITICAL 1(현재가 결측 시 봉인 무발화)·HIGH 5(취소가 원주문과 다른 거래소로 새는 경계 교차 → `_order_exchange[order_no]` 매핑 신설 / `[after_cancel_result]` 미구현 / CI 시각 폭탄 4건) 시정. 프로덕션 3파일 · `scheduler.py` 3,897L·8영역 나머지·전략 7파일·`market_state`·`session`·`sell_rejection` diff 0 · sha 핀 16곳. 백엔드 9,523 PASS |
| 2026-09-12 | 메뉴바 2단 카테고리화 + 폭 슬라이더 깜박임 시정 (cycle288 — 사용자 지적 "헤더메뉴바도 같이 넓어지려고 해서인듯" · "메뉴바가 너무 난잡" + 묶음 직접 지정 · 프론트 전용) | 깜박임 원인 = `App.tsx` 가 같은 동적 `maxWidth` 를 나브 안쪽 div 와 `main` 두 곳에 걸었고 **슬라이더가 그 나브 컨테이너 안에 있었다** — 드래그 중 컨테이너가 리사이즈되며 슬라이더가 포인터와 어긋났다. 시정 = 나브 `NAV_INNER_MAX_WIDTH` 고정, `main` 만 반응. 구 주석("나브도 동일 폭")은 **의도적 설계**였으므로 지우지 않고 왜 뒤집었는지를 덧붙였다(되돌림 방지). 메뉴 10개 → 상위 7개(대시보드/거래내역/로그 단독 · **종목**{조건검색 추적·종목마스터} · **전략**{전략 현황·전략수정 AI자문} · 설정 · **운영상태**{장운영상태·실시간 상태}). 단독 항목엔 드롭다운을 만들지 않는다(클릭 한 번을 더 요구해 더 난잡해진다). `NavEntry = leaf|group` 로 **드롭다운 유무가 데이터로 결정**되고, 나브 전체가 `components/NavBar.tsx` 로 분리됐다. URL·페이지 무변경, 경로 10/10 도달 가능(가드가 href 집합 불변을 단언). 적대 검증이 **구현자가 안 돌린 e2e 4건 실제 파괴**를 잡았다 — 접힌 그룹 때문에 `getByText().first()` 가 모바일 헤더의 숨은 span 을 집었다(→ `getByRole("heading")`). 접근성 3건(포커스 `<body>` 이탈 · `aria-haspopup` 거짓 약속 → disclosure · Tab 이탈 시 열린 채 잔존) 시정. 프론트 769 PASS · e2e 42/42 |
| 2026-09-12 | LTV `main` 보드 매수 15:20 컷 + NXT 거부 귀속 시정 (cycle286 C2-a·C4-a — 사용자 승인, 8영역 `order_engine.py` 단독 · 11 에이전트 오케스트레이션) | **C2-a** `_BOARD_SCHEDULE` 의 MAIN 이 09:00~15:39:59 라 KRX 연속체결이 끝난 15:20 이후에도 `board="main"` 매수가 나갈 수 있었다. 15:20~15:30 종가단일가는 `00`/`01` 을 **접수**하므로 거부라는 우연한 안전판이 없고, 15:20 `_force_clear_main_only` 는 이미 지나가 그 체결이 익일청산·갭가드·트레일링이 전부 없는 당일 모드로 **오버나이트에 남는다**. 모듈 상수 `MAIN_BUY_CUTOFF_KST=15:20`(DB override 불가 — 오버나이트 금지는 토글로 뚫려선 안 된다), 자리는 **발사점**(계좌 게이트가 첫 문장이라 최상단 불가 + baseline 동결 방지 + would_buy 관측). **C4-a** `nxt_tradable=False` 사후 보강을 시계 단독 → `target_exchange ∈ (NXT,SOR) ∧ 08:00~08:50` 로. 09-14 부터 KRX 애프터가 구 `15:30~20:00` 창에 통째로 들어와 KRX 주문의 거부가 그 종목을 NXT 불가로 낙인찍고 그 오염이 ≈24h 존속하는 자기 강화 래치가 된다. **운영 실측이 위험 판독을 바꿨다** — LTV `tradable_boards` DB 실제 `["main","pre_nxt"]`(post_nxt 없음 ⇒ 야간 매수 이미 꺼짐)라 C2-a 는 노출을 **옮기는 게 아니라 없앤다**. 7전략 `exchange` 는 당시 전부 SOR 이라 C4-a 실효는 창 단독이었다(**그 뒤 D3 로 전부 `NXT`** — 같은 집합 안이라 판정은 불변, 실효도 창 단독 그대로). LTV 15:20 이후 매수 **전 기간 0건** = 예방적 시정. 백엔드 9,286 PASS |
| 2026-09-11 | 저녁 창 재설계 — 봉 확정 커트오프 20:00 · 일봉 적재 20:30 · 정산 21:30 · 기동 거부 경계 분리 (cycle283 — 사용자 확정 D1~D8, 8영역 `scanner.py` 단독 승인 · `scheduler.py` **3,897L** < 실효 상한 3,900 · sha 핀 7곳) | 09-11(금) 16:05 재기동 → 16:14 immediate 가 **1,005종목 부분 거래량 봉**을 저장 → 18:10 정기가 908종목 `skipped_fresh` 로 건너뜀(40종목 대조 중앙값 +0.51%, 최대 **+13.97%** 현대차). 일봉 OHLC 는 15:30 확정이지만 **거래량은 시간외 동안 계속 는다**. 09-14 부터 KRX 애프터마켓(16:00~20:00 실시간 체결) 신설 + 시간외 단일가 폐지 ⇒ 18:10 적재는 **매일** 부분값을 담는다. 시정 = **커트오프 `time(20,0)`**(판정식 byte 동일) + **적재 20:30** + **정산 21:30** + 신규 `TIME_SESSION_START_CUTOFF=20:00`(`start()` 거부와 `run_daily` 일자 전환이 **둘 다** 사용 — 갈리면 그 창에서 60초 주기 헛 재시도 ~90회가 KIS 휴장일 API 와 WARNING 90행으로 그날 리포트 `level_counts` 를 오염) + **`TIME_METRICS_SNAPSHOT=20:05`** metrics 1차 스냅샷(신규 leaf `daily_metrics_snapshot.py` — OpenAI 미호출, `reset_request_metrics()` 미호출, never-raise, 마커 1행; 메모리 전용 `api_metrics`·`strategy_funnel` 유실 노출 90분→5분) + **`insert_log_report` upsert**(`ON CONFLICT (target_date) DO UPDATE`, SET 절 base 9컬럼만 — `ext_*` 6·`created_at` 0건. 20:20 루틴 POST 실측 20:34~20:54 가 이제 정산보다 **먼저**라 순수 INSERT 면 그날 `metrics` JSONB 통째 유실) + **C9-b 수동 재실행 비파괴**(`POST /api/log-reports/run` 은 완성본이 있으면 `generate_daily_log_report` 를 호출조차 않고 `success=false`, `?force=1` 만 덮어쓴다 — 21:30 정산 뒤 재실행이 `api_metrics` 0 으로 덮던 신규 파괴 경로 차단) + **`[daily_head_stale]` 부팅 관측 1행**(자문 R1 — 20:00~21:30 재기동은 그날 적재를 통째로 잃고 다음 아침 prepare 가 하루 밀린 헤드로 종일 돈다. 보정은 이미 있고 없는 건 **순서**라, 여기서는 관측만 넣고 완전 자동화는 별도 승인). 매매 행위 영향 = **일봉 거래량을 읽는 3전략**(donchian ×1.0 후보 증가 / BFB ×1/2 감소 / VCP ×1/5 감소) — kojiro 는 `enrich` 가 `volume` 을 읽지 않아 **무영향**(브리프 서술 정정). 전략 7파일·`strategy_base` diff 0. 검증 후속 5건 시정 = 재실행 가드 **4축**(OpenAI 실패일 수동 복구가 막히던 오분류 해소) · `[daily_head_stale]` 휴장일 역산(연휴 오탐 차단) · 스냅샷 마커 `saved=1|0` · 가드 3건을 주석·OR 만족에서 AST/런타임으로 조임 · 라인 상한 표기 4,000→**3,900** 정정. **미실측 전제 2** = ① KIS 일봉이 20:00 직후 확정되는가(§4-1 재조회 필수) ② 애프터마켓 체결이 일봉 H/L 에 반영되는가(참이면 영향이 가격 축 VB/LTV 까지 확대). **3세대 합산 금지** = `[daily_load_today_bar_filter] mode=`(15:40~20:00 이 keep→drop) · `skipped_fresh` · 20:20 루틴 리포트의 `api_metrics`/`strategy_funnel`(리셋 뒤 값 → 전일 전체) |
| 2026-09-11 | AI 매수평가 **주문 발화 시점** 이동 + 전용 테이블 영속화 + 거래기록 UI 팝업 (cycle276 — 사용자 지시 "매수평가 시점을 실제로 매수주문을 발화하는 시점으로, 입력·결과를 로그와 DB(일자-계좌-종목-주문번호 PK)에 남겨 주문체결내역과 연결, UI 거래기록 각 행에 AI매매자문 버튼·팝업" · 8영역 중 `order_engine.py` 만 사용자 승인 접촉) | cycle274 의 신호 시점 훅(`observe_signal`, 전략 2파일)을 **전부 제거**하고 `execute_buy` 의 두 매수 `place_order` 성공 직후(매핑 등록 끝 · PENDING INSERT 앞)에서 `observe_order` 로 접수한다 — 신호 10건 중 절반만 주문이 되던 표본 괴리 해소 + `order_no` 확정 시점이라야 PK 가 성립. 래치 키 `(전략,종목)/일` → **주문번호**(같은 종목 두 번 사면 두 번 평가) · 신규 `llm_buy_evaluations`(migration 043, 53열, 성공·실패 모두 1행) · 신규 라우트 `GET /api/llm-evaluations[/{order_no}]`(계좌 **마스킹**, 화이트리스트 사영, 404/500 분리) · `get_trade_pairs` 에 `buy_order_nos`/`sell_order_nos`/`pair_key` 3키(한 페어 매수 2건 이상 실측 9건 = 단수 불가) · 프론트 두 그리드 "AI 자문" 버튼 + `LlmEvaluationModal`(배치 1요청으로 활성 판정, 의존성 0) · 마커 5종(`[llm_eval_persist]` 신규, `slip_bp`→`post_order_drift_bp` 개명 = 부호 의미 반대라 **합산 금지**) · 전략 파일은 `DEFAULT_PARAMS` 4키만 남고 세그먼트 sha 는 cycle272 값 복귀 · **매매 행위 변경 0**(주문이 나간 뒤 평가가 붙는다, `enforce` 미구현) · A-ATOMIC 구간 byte 동일 · `scheduler.py`·타 8영역·전략 5파일 diff 0 · 검증 후속 7건 시정 — **A-1** 09-11 실전 2건이 전건 실패한 원인(추론 모델의 추론 토큰이 `max_completion_tokens` 를 함께 소비 → `content=""`)을 한도 400→**2000** + 신규 사유 **`truncated`**(마커 `finish=` 병기)로 분리, 비용은 상한이라 불변 · **A-2** 시가 REST 빠른 라운드 9→**19**(09:00:35~09:09:35 연속 — 종전 09:04:35~09:09:35 5분을 메우는 주체가 없었다, 스케줄러 재시도는 09:30 `_scan_loop` 안) · **B-1** `buy_signals[-3:]` 꼬리 절단 제거(전략이 이미 20건 cap, 잘리면 신호 매칭이 실패해 목표가·k 가 통째로 null) · **B-2** 배치 요약 응답 키를 `날짜|주문번호` 복합 키로(주문번호 단독 키가 같은 번호의 다른 날짜 평가를 지워 버튼 비활성↔상세 200 비대칭, 실 PG 재현) · **B-3** `trade_date` 형식 위반 200→**422** · **B-4** `signal_time_kst`→`signal_time_local`(tz-naive 로컬 시각, 043 미적용이라 개명 비용 0) · **B-5** 자매 핀 주석 정직화 |
| 2026-09-11 | VB·LTV 매수 신호 LLM 평가 게이트 **shadow** 배선 — 점수 기록만, 행위 변경 0 (cycle274 — 사용자 지시 "큐 끝나면 자문부터 시작하고 shadow 로 배선", 자문 `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md` 결정 10 + 열린 질문 Q1~Q10(enforce 규약은 사용자 결정 카드) · 신규 leaf `src/engine/llm_buy_gate.py`(observe_signal 동기 never-raise → create_task, 래치 1회/(전략,종목)/일, cap 20, 세마포어 2, 타임아웃 20s, 클램프 금지, 마커 4종 + `slip_bp`) + `llm_features.py`(지표 순수 함수·화이트리스트 스냅샷·프롬프트 위생) · VB·LTV `return Signal.BUY` 직전 호출부 try/except(양 분기 동일 반환) + `DEFAULT_PARAMS` 4키(`llm_gate_mode="shadow"`·`min_score=70`·`daily_call_cap=20`·`timeout_secs=20`, 부재 = off/0/70/20, PARAM_RANGES 편입 금지) · `config.openai_buy_gate_model` · **8영역·scheduler(3,872L)·strategy_base·타 전략 5파일 diff 0** · `_STRATEGY_PINS` 2핀 갱신·4핀 불변 · cycle233 C233-F1 가드 try 양 분기 BUY 귀결 최소 확장(승인 카드) · 적대 검증 2라운드(CRITICAL datetime payload → 빈 페이로드 무음 · HIGH 거래량 5필드 누락·설정값 노출 시정, 뮤테이션 ESCAPED 0) · 신규 322 · 전체 8,1xx PASS) | D+1(09-11) = `[llm_gate_config]` VB·LTV 각 1행 · `[llm_buy_score]` 4~6행 · `_failed` <10% · `[llm_gate_daily_cap]` 0 · VB·LTV 매수 패턴 불변 · `verdict_lag_ms` p50/p95. 킬스위치 `PUT {"llm_gate_mode":"off"}` 즉시 |
| 2026-09-11 | D2(나) F-3 — kojiro WS 틱(`risk.on_tick`) 매수 평가 skip, 명시 상수 `_TICK_BUY_EVAL_SKIP_STRATEGIES` (cycle273e I4 — D2(나) 사용자 결정 09-10, 8영역 `risk.py` 단독 · scheduler 3,873L diff 0) | 09-07 실측 N=103(WS 시가≠KRX 확정 시가 95.1%·갭업 탐지율 0/8) 오염 시정 — 경로 B(`on_tick`) kojiro 매수 평가 skip, 매수는 경로 A(`_swing_buy_poll_loop`, REST `stck_oprc`)에서만. 후보 집합 무손실(코드 레벨 증명 `_scanned_tickers ⊇ _candidates`). cycle268 real_call_paths R11 계약 반전(원 docstring "삭제하지 마라" → 0행 계약). sha 핀 4곳 갱신. 뮤테이션 12종 KILLED/ESCAPED 0 · 표적 26 + AST 931 + 회귀 2,403 PASS. 킬스위치 없음(1행 revert). 커밋 완료·push 금지(워크트리 규약) |
| 2026-09-11 | 필옵틱스 F-1/F-2/F-3 — `update_trade_status` WHERE 에 `order_no` 추가(호출 6곳) + `[trade_status_multi_update]` 다중갱신 관측 + AST1/AST2 unskip (cycle273b I3 — D2(다) 사용자 결정 09-10, `src/db/trade_history.py`+`src/engine/order_engine.py` 2파일, 8영역 `order_engine.py` 단독 · scheduler 3,873L diff 0) | 같은 (ticker, trade_type, strategy) 의 **다른 order_no** 행까지 함께 덮던 WHERE 결손(필옵틱스 161580 사건 원인)을 시정 — C1~C6 호출부 전부 지역변수 `order_no` 를 그대로 전달, 미전달 시 SQL **byte 동일**(좁히기만 하는 opt-in). `affected>1` 시 `trade_history.py` 한 곳에서 WARNING 1행(부분 UNIQUE 인덱스 때문에 order_no 있는 호출은 구조적으로 발화 불가 — 과거를 재는 측정기가 아니라 WHERE·인덱스 후퇴 감시자). AST1 매처를 "키워드 이름"→"지역변수 바인딩까지" 강화(직전 검증 뮤테이션 M12 ESCAPED 시정). 뮤테이션 프로덕션 14종 KILLED/ESCAPED 0 · 신규 46 + 실PG 32 PASS · AST 926 PASS · sha 핀 4곳 갱신 |
> 사이클 200 이하 및 초기 하네스 구성 전체 이력(verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)
```

## 모델 라우팅

### 2026-09-06 — `model: fable` 고정이 네 에이전트를 막은 경위

```
| 구현 계획·검수·리팩토링 검토·마무리 보고서 | **opus** | `team-leader`, `tester`, `refactor-expert`, `report-writer` — 2026-09-06 정정: 종전 `model: fable` 고정이 크레딧 소진으로 그 넷을 전부 막았다(리포트 파이프라인 11회 시도 전멸). ⚠️ **모델 지정을 지워도 상속이 Fable 로 해석된다**(실측: 지정 없는 내장 `general-purpose` 도 같은 오류) — 명시 지정만 통한다. 그래서 메인 세션과 같은 `opus` 로 명시했다. 세션 모델이 또 바뀌면 이 네 줄도 같이 바꾼다 |
```

## 자율 진행과 승인 빈도

### `scheduler.py` 라인 상한 표기 변천 (7곳/15곳 · `<4,000L`)

```
- **8영역** = `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**` (정본 목록 = `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS`, 승인 시 그 파일의 sha 핀 절차를 따른다). `scheduler.py` 는 8영역은 아니지만 라인 상한(**<3,900L** — cycle257 이 세운 영구 상한이 정본이고 자매 가드 **15곳**(cycle257/264/268/269/272/273/273b/274/276/283/286/287/290/291/292)이 복창한다 — 종전 표기 '7곳' 은 cycle273b 시점에 멈춘 값이었다. 새 사이클이 이 상한을 복창하면 이 수도 함께 올린다. 종전 표기 `<4,000L` 은 느슨한 쪽이라 폐기: 두 수가 갈라지면 항상 **더 조인 쪽**이 정본이다) 때문에 같은 승인 대상이다.
```

### 2026-09-15~16 — 15:30~16:00 이 온전한 공백이 되기 전의 단서 (cycle295 착지 전)

정본 「사전 승인 범위」와 「운영 가이드」 두 곳에 같은 ⚠️ 가 있었다. cycle295(2026-09-16)
착지로 15:30~16:00 은 완전 휴식이 되어 단서가 사라졌다.

> ⚠️ 15:30~16:00 이 온전한 공백이 되는 것은 cycle295(15:30~16:00 완전 휴식) 착지 **뒤**다. 그 전에는 15:40~16:00 에 NXT 청산 경로가 구조적으로 열려 있다 — 다이얼 `tick_channel_gap_hold_enabled=false`(2026-09-15 적용)가 시세를 끊어 실질 무주문이지만, 확실히 하려면 **15:30~15:40** 을 쓴다.

→ CHANGELOG: cycle295 행

## 핵심 안전 규칙 (절대 깨지 말 것)

### 2026-08-08 — KRX OpenAPI 오판으로 full_universe_load 3,577→60 종목 degrade (전문)

```
- **기능·설정 비활성화(disable / toggle off / dead 판정) 시 심층 검증 의무** — 무언가를 "미사용/dead/낭비"라고 단정하기 **전에 소비처(consumers)를 전수 확인**하고, 비활성화 **후에는 그 소비처가 여전히 정상 동작하는지 라이브 실측**으로 검증한다. **비활성화는 "제거"가 아니라 "경로 변경"일 수 있다** — 주 경로를 끄면 폴백 경로가 조용히 degrade될 수 있으므로, 배포 후 반드시 실측 점검한다(설정 토글은 CI/Deploy 를 안 타므로 자동 검증도 없다). 실측 없는 비활성화 금지. ⚠️ **재발 방지 사례 (2026-08-08 KRX OpenAPI)**: `krx_open_api_enabled` 를 "무효 키·낭비"로 오판해 비활성화 → 소비처 `scanner._full_universe_load_krx_primary`(20:00/07:48 전체 유니버스 적재 주 소스)가 KIS market-cap 폴백으로 밀려 **full_universe_load 가 3,577→60종목으로 degrade**(D+1 실측 발견). 원인 = (a) 소비처 미확인(주 소스인데 "미사용" 오판) + (b) 비활성화 후 점검 절차 부재. 키는 실제 유효(40자)했고 재활성화로 복원. **끄기 전에 `grep` 으로 소비처를 찾고, 끈 뒤엔 그 소비처의 산출물(예: 적재 종목수)을 라이브로 확인하라.**
```

### 2026-09-10 cycle271 — 체결통보 선행 race 의 두 번째 창 (전문)

```
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존. **cycle271(2026-09-10)** — 그 가드가 못 덮는 두 번째 창(PENDING `insert_trade` 의 `await` 도중 체결통보가 먼저 완주 → 보정 INSERT 가 같은 `(ticker, order_no, trade_type)` 를 선점 → migration 029 부분 UNIQUE 위반으로 `execute_buy` 가 ERROR 종료·`buy_succeeded` 후처리 누락)은 `_insert_pending_buy_or_absorb_race` 가 **`_completed_orders` 에 그 주문번호가 있을 때만** `UniqueViolationError` 를 흡수·discard 한다. 증거 없는 위반은 그대로 전파(다른 원인 은폐 금지) — 무조건 삼키기·`sizing`·재시도 INSERT 로 바꾸지 않는다
```

### 2026-09-02 cycle241 — silent inactive 세션 상대 판정의 근거 통계 (전문)

```
- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드: `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단). **세션 상대 판정 (cycle241, 2026-09-02)** — 판정 가능 세션(`subscribed >= 5`)이 **2개 이상이고 그 전부**가 `fresh_ratio < 0.2` 이면 '세션 고장'이 아니라 **시장 침묵**(NXT 프리 마감 08:50~09:00 · 15:20 이후 장후 동시호가 + 15:30~15:40 마감 흡수)으로 보고 그 사이클을 **기각 + 판정 가능 전 라벨 `first_seen` pop**(누적 후 필터 금지 — 시장 재개 순간 지각 세션이 즉발한다); 다른 세션이 하나라도 fresh 면 현행대로 발화(진짜 세션 결함 보존), 판정 가능 세션 < 2 면 현행 유지(fail-open) = 결과 집합 ⊆ 현행. 기각은 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` 로만 관측(30분 이상 지속 시 WARNING). 근거 = 30일 522건 중 491건(94%)이 풀 전원 동시 발화 · 09:00~15:20 정규장 0건 · 재연결이 회복시킨 사례 0(08-31/08-12 전 세션 두절도 익일 부팅으로만 회복). **시장 침묵 기각에 시간창 리터럴(08:30/15:20)·`tradable_boards`·`session` import 를 쓰지 않는다** — 세션 간 비교만이 15:30~15:40 갭까지 닫는다(AST G-241-5)
```

### 2026-09-05 cycle252 → 09-14 cycle293/294 — no_feed 마커 3세대 반전 (전문)

```
- **무송출(no_feed) 종목은 K stale watcher 가 재등록하지 않는다 (cycle252, 2026-09-05)** — 통합 채널 `H0UNCNT0` 은 `stock_master.nxt_tradable=False`(KRX 단독, NXT 비대상) 종목의 체결 프레임을 보내지 않는다(포렌식 `_workspace/forensics/stale_candidates_0904.md`: 나흘 × ~200종목 예외 0, 유동주 포함, 최소 07-24 부터 만성). SUBSCRIBE 는 SUCCESS ACK 를 받으므로 재등록은 회복 가치 0 이고 SEND 만 하루 ≈14,600 을 만든다. `stale_watcher_core.check_and_resubscribe_stale` 은 `no_feed_registry`(`stock_master` 조회, 600s TTL, **fail-open** = 집합 ∅·조회 예외·미지 ticker 면 현행 byte 동일)로 **LOW no_feed 종목의 SEND·`_stale_last_resubscribe_at` 스탬프·force_retry history 만** 건너뛴다. **HIGH(보유·익일청산) 경로는 byte 동일**(가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 손절 커버리지다 — 대신 `[no_feed_held]` WARNING 1회/일이 "보유 종목이 WS blind, 손절은 REST 폴만" 을 매일 남긴다). `_stale_retry_count` 는 계속 증가(r>5 홀드)해 `stale_universe_guard` 의 저유동 축출 경로를 보존한다. 🔴 **cycle293(2026-09-14)이 이 절의 세 마커 의미를 뒤집었다 — 배포 전후 grep 합산 금지.** ① `[tick_coverage] stale` 은 cycle252 계약에서 **불변이 정상**(현상 은폐 금지)이었으나, 속성축 리졸버가 착지한 지금은 **줄어드는 것이 성공 서명**이다(단 **채널 이동만으로 분모가 줄어서는 안 된다** — 집계가 세 채널 합집합이라 분모는 유지되고, 성공은 `stale` 감소보다 **`fresh` 증가**로 먼저 나타나야 한다). ② `[stale_watcher_summary] no_feed_skipped=` 는 높은 것이 정상에서 **감소가 성공 서명**으로(전용 채널로 옮긴 종목은 프레임이 실제로 오므로 회복 가치가 생겨 skip 대상에서 빠진다). ③ `[no_feed_held]` 는 매일 알리는 것에서 **S2(`enforce`) 뒤 0 이 정상**으로(0 이 아니면 판정 실패 또는 전환 실패. ⚠️ 배포 **직후**에는 계속 비영인 것이 정상 — 기본 모드가 `observe`(행위 0)이고 `enforce_low` 는 HIGH 를 스코프 밖에 둔다). 근본 시정이던 속성 기반 채널 리졸버(`nxt_false → H0STCNT0`, P1-7 B)는 **cycle293 2단계 → cycle294 3단계(시간축 전환 · 통합 채널 소멸)로 착지**했다 — 3단계에서는 `[no_feed_held]` 가 **0 이 정상**이고(전 종목이 전용 채널) `no_feed_skipped=` 도 0 에 수렴한다 — 상세 = `src/realtime/CLAUDE.md` 「시세 채널」 절, 킬스위치 = `PUT /api/realtime/tick-channel-mode`. 5분 `resubscribe_stale_priority` 는 무접촉(후보 소스 `ticker_last_tick` 에 no_feed 종목은 프레임 0 이라 애초에 없다). 금기 = no_feed 를 stale 집계에서 **빼서** 숫자를 좋게 만드는 것, HIGH 를 skip 에 넣는 것, 관측 헬퍼가 예외를 전파해 HIGH 재등록 사이클을 끊는 것(F-1)
```

### cycle242 · cycle245 — 매수 수량 관문 안 두 캡의 자리 논거 (전문)

```
- **매수 수량은 전략 잔여 자금 기준** — 7 전략 `calc_buy_quantity()` 의 **모든 return** 이 `StrategyBase._apply_budget_limit()` 관문을 경유한다 (AST 가드 A-GATE). 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`. 비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — **이 분기 순서가 계약**이다. 관문 안에서 `await`/DB/HTTP **절대 금지** — `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(AST 가드 A-ATOMIC)이 원자성의 전제이고, 이게 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다. **cycle242** — 관문은 폴백/잔여 클램프 **뒤** · `[oversized_fallback]` 관측 **앞**에서 `sizing_mode="turtle"` 전략의 랏을 `max_lot_units`(K) 유닛으로 자른다(`_apply_lot_units_cap`). 캡 ATR 은 사이징과 **같은** `_candidates[ticker]` 를 read-only 로 읽고 `("atr","atr14")` 두 키가 서로 다른 값이면 **불채택**(fail-open) — `_candidates` 를 생성·변경하지 않는다(AST G-242-8). 관문 안 `await`/DB/HTTP 금지(A-PURE)는 신규 헬퍼 8 개 전부에 확장 적용된다(AST G-242-2/G-242-10) — 관측 실패가 매수 수량을 바꾸면 안 되므로 세 emit 은 전부 예외를 흡수하고 **행위는 cap 밖**이다. **cycle245** — 관문은 그다음, `[oversized_fallback]` 관측 **뒤**·`return` 앞에서 ρ축 명목 상한(`_apply_ratio_notional_cap`)을 적용한다. 관측 **앞**에 두면 차단된 랏의 ρ 관측이 `final_qty < 1` 로 통째로 사라지고, `_apply_lot_units_cap` **앞**에 두면 조기탈출로 cycle242 마커 3종이 사라진다 — **이 자리가 유일하게 안전한 위치다**. 관문 안 `await`/DB/HTTP 금지(A-PURE)는 cycle245 신규 헬퍼 6 에도 확장 적용된다(AST G-245-2), 캡 스코프는 폴백 랏이 아니라 **관문을 지나는 모든 랏**이고, 관문 반환 타입은 **`int`** 여야 한다(float 이면 `api/order.py` 가 `ORD_QTY="2.0"` 을 KIS 로 보낸다 — G-245 회귀가 봉인)
```

### cycle243 · cycle249 — API 인증·리포터 스코프 (전문)

```
- **API 인증은 조용히 꺼지지 않는다 (cycle243)** — `ApiAuthMiddleware` 는 **최외곽**(`MetricsMiddleware` 보다 바깥, starlette 는 마지막 `add_middleware` 가 가장 바깥)에서 `/health` 를 뺀 **전 경로**를 `X-API-Key` 로 지킨다. `API_AUTH_KEY` 미설정·빈 문자열·비교 예외는 전부 **401(fail-closed)** — fail-open 은 "키가 없으면 인증이 사라진다" = 이 사이클이 고친 결함의 재현이다(매매 엔진은 in-process 라 API 가 잠겨도 매매 영향 0, 대시보드만 멈춘다). 금기 = (a) `/api` 접두사 스코프로 좁히기(`/docs`·`/openapi.json` 이 열린다) (b) 프로덕션 코드에 테스트 우회 플래그 두기 — 테스트는 모듈 전역 `authorize` 를 monkeypatch 하는 seam **하나**만 쓴다(`tests/conftest.py::_neutralize_api_auth` + 옵트아웃 마커 `real_api_auth`) (c) `API_ALLOWED_ORIGINS=*` — 와일드카드는 코드가 **버리고 경고**한다(CORS credentialed preflight 전면 개방 + CSRF Origin 검사 무력화가 한 값에 동시에 딸려온다) (d) 개발 예외·개발용 기본키(커밋된 기본키는 공격자가 프로덕션에 가장 먼저 시도할 값) — dev 는 vite proxy 가 서버 측에서 `X-API-Key`·`Origin` 을 넣어 산다. 상태변경(POST/PUT/PATCH/DELETE)은 Origin 검사 추가(부재는 허용 = curl 비상 매도 경로 보존). **알려진 한계 = TLS 부재**(자격이 평문으로 오간다, 후속 F1) · 단일 공유 키(감사 추적 없음). **리포터 스코프(cycle249)** — `authorize()` 가 운영 키 판정 **뒤**에 리포터 키(`API_REPORTER_KEY`)를 본다: GET/HEAD 는 경로 무관 통과, `POST /api/log-reports/{date}/external` 정확 경로만 통과, 그 외는 유일하게 **403**(`reporter_scope`, 다른 사유는 전부 401). 스코프는 요청 헤더가 아니라 nginx `map $remote_user` 가 고르는 **Basic 사용자**에서 나온다(`location /api/` 가 클라이언트 헤더를 무조건 치환하므로 "루틴이 스코프 키를 보낸다"는 설계는 성립하지 않는다)
```

### cycle242 K축 · cycle245 ρ축 — 랏 캡 실측과 경위 (전문)

```
- **랏당 최대 유닛 상한 `max_lot_units` (K=2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든** 매수 랏(터틀 유닛·`position_ratio` 낙하·1주 폴백)을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고, 그 값이 0 이면 **매수하지 않는다**. 1주 폴백이 설계 유닛의 평균 4.94배·최대 15.61배가 되어 `risk_pct` 통제를 진입 시점에 무력화하던 과잉 피라미딩 시정 — **매수를 줄이는 방향**뿐이다(캡은 `min()` 이라 수량을 늘리지 않는다). 캡 산출은 `turtle_sizing.compute_unit_qty(budget, atr, risk_pct, fraction=K)` **재사용**(새 수식 금지), ATR 은 터틀 분기와 **같은 소스** `_candidates[ticker]` 를 read-only 로 읽는다. K 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-242-1: 런타임 dict + 소스 리터럴 이중), 읽는 쪽 `[1.0, 20.0]` 클램프(**하한 1.0 = 정상 터틀 랏이 캡에 안 걸리는 수학적 전제**, 상한 20.0 = 롤백 다이얼). ATR 결측·모호(`atr`↔`atr14` 상이)·`risk_pct ≤ 0`·예외는 **fail-open**(현행 수량 유지 + `[fallback_cap_skipped]` WARNING) — fail-closed 는 P0-1 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이라 금지. ⚠️ **"K유닛 = 예산 2.0% 노출" 은 `_entry_atr` 스탬프 랏(2×ATR 손절) 한정** — 폴백·PR 낙하 랏은 미스탬프라 고정% 손절을 타므로 실효 상한은 `cap_qty × price × |stop_loss_rate|`(donchian 실측 최대 2.09%·이론 6.99%)다. **고정%손절 5전략**(momentum/VB/LTV + `position_ratio` 모드 VCP/BFB)은 **범위 밖**(position_ratio 가 이미 리스크 균등 — 유닛 캡을 씌우면 정규화 역전, 함정 #1). 피라미딩(사다리 증량) 착수 시 **K→1.0** 으로 조인다(K=2 랏 + 4유닛 사다리 = 8유닛 = R15 재위반). 롤백 = 해당 전략 `max_lot_units = 20.0` — 어느 수단도 코드 재배포는 불필요하지만 **반영 시점이 다르다**(cycle245 라운드 2 실측): `PUT /api/strategies/{id}/params` 는 **즉시**(라우트가 in-memory `config.params` 를 덮는다), `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만**(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회이고 07:55 `_boot` 재호출은 no-op) — cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **장중 실효 수단은 PUT 뿐**이다. **그리고 당일 캡→0 으로 `_bought_today` 가 소진된 종목은 어느 수단으로도 다음 세션부터만 되살아난다**(`cap_qty` 는 D-1 ATR 기반 일중 상수)

- **랏 명목 ρ축 상한 `max_lot_ratio_mult` (K_ρ=2.5, cycle245)** — K축(`max_lot_units`)이 **심사하지 못하는 모든 랏**(비터틀 5전략 전부 + 터틀이지만 ATR 배관이 끊긴 랏)의 명목을 `K_ρ × position_ratio × 예산` 이하로 자르고, **1주도 못 사면 매수하지 않는다**. 1주 폴백 랏의 크기가 설계가 아니라 **그 종목 주가**로 결정되던 결함 시정 — 09-04 실측 LTV 000500 이 설계 랏의 4.23배(220,000원)로 들어가 그날 최대 손실 −11,000원(순자산 0.42%)을 냈다. **매수를 줄이는 방향뿐**이다(`min` 이라 수량을 늘리지 않는다). 산식 = `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // 현재가`, 판정 기준은 `_lot_units_cap_governs`(= turtle ∧ ticker ∧ `risk_pct>0` ∧ 예산>0 ∧ ATR 해석 성공)이다. **cycle254(2026-09-05)부터 K축이 심사한 랏도 ρ축이 `min` 으로 후심사한다**(구 결정 ⑦ "두 캡은 상호배타 — `min` 합성 없음" 폐기) — `_apply_ratio_notional_cap` 의 조기탈출은 `_lot_units_cap_governs` 판정 자체가 실패한 경우(`probe_error`)만 fail-open 으로 남기고, 그 외엔 K축 심사 여부와 무관하게 컷오프를 적용한다. 사이즈드 터틀 랏·`position_ratio` 낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한(`min(qty, int(예산×position_ratio)//price)`)이 명목을 이미 컷오프 이하로 묶어 두므로 `final <= cap_qty` 로 **항등적으로 무접촉**이고, **실효는 1주 폴백 랏뿐**이다 — 구 잔여 노출 kojiro 3.86배·donchian 5.00배(후속 F-9)는 cycle254 로 닫혔다. `[ratio_cap_config]` 라벨도 터틀 전용 `backstop` 을 폐기하고 `off|on` 2종으로 통일했다. **키 부재 = OFF**(cycle242 `max_lot_units` 관례와 **반대** — 매수를 막는 통제라 "설정이 없으면 막는다"는 P0-1 유령 키 재현 경로다). 키는 **7 전략 전부**의 `DEFAULT_PARAMS` 에 명시하고 AST 가 glob 전수로 강제한다. K_ρ 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-245-1) + AI 자문 자동 적용 경로 편입 금지, 읽는 쪽 `[1.0, 20.0]` 클램프(**하한 1.0 = 정상 비중 랏이 캡에 안 걸리는 수학적 전제** — 1.0 미만은 주 분기까지 잘라 전면 무매매, 상한 20.0 = 롤백 다이얼). `position_ratio` 결측·예산 0·초소액·판정 예외는 전부 **fail-open**(현행 수량 + `[ratio_cap_skipped]` WARNING). 롤백 = 해당 전략 K_ρ=20.0 — **`PUT /api/strategies/{id}/params` 는 즉시, `strategy_config` SQL UPDATE 는 다음 백엔드 재시작에서만** 반영되므로 보유 중 장중 롤백은 PUT 이 유일 경로다(cycle232 D6). ⚠️ **배포 전에는 PUT 이 무음 실패한다** — 라우트가 미지 키를 조용히 버리고 `params` JSONB 를 통째로 덮어 먼저 넣은 SQL 값까지 지운다.
```

### cycle272 — VB·LTV `main` 목표가 기준가 (전문, 통합 채널 소멸 전 서술)

```
- **VB·LTV `main` 목표가 기준가 = KRX REST 단일 출처 (cycle272, 2026-09-10 — 사용자 결정 D1)** — `board=="main"` 목표가는 통합 채널 `H0UNCNT0` `fields[7]`(오염된 세션 시가) 대신 **KRX REST `stck_oprc`(`J`) 만** 기준가로 삼는다. 좁은 목 `on_open_price_confirmed(..., board="main", *, source="ws")` — `source` 신뢰 목록은 `("rest",)` 뿐이고 기본값이 불신 `"ws"` 라 WS 확정 경로는 조용히 거부된다. 킬스위치 `open_price_scope_mode`(전략별 `DEFAULT_PARAMS`, 기본 `"enforce"`, `"off"` 만 롤백 — `PARAM_RANGES`/`INT_PARAMS` 편입 금지). REST 확보는 leaf `src/engine/open_price_rest.py`(09:00:35 R1 부터 30초 간격 9라운드 → 5분 간격 15:20 까지, 프린트 안 된 종목은 그 시점 매수 불가). `pre_nxt`/`post_nxt` 보드는 게이트 스코프 밖 — LTV 08:00~09:00 프리장·야간 매수 무접촉. 상세 = `src/engine/strategies/CLAUDE.md`
```

## Docker / 배포

### 2026-09-04 cycle248 — 선택적 배포 도입 경위 (전문)

```
- **cycle248 선택적 배포 (2026-09-04) — 모든 push 가 backend 를 재시작하던 문제 시정.** 종전 `docker compose up --build -d` 는 Compose v5.1 에서 **이미지 ID 가 같아도** `build:` 서비스를 전부 재생성했다(빌드가 이미지를 재태그해 LastTagTime 이 컨테이너보다 새로워진다 — EC2 v5.1.3·로컬 v5.1.1 재현). 그래서 ~~cycle243 의 "Phase 1(nginx 만)은 backend 이미지 입력 무접촉 → 무재시작 → D6 미적용"~~ 은 **거짓이었다**(13db0d9 프론트 전용 push · 09-02 b985938 문서 1파일 push 모두 backend ~100초 tick blind 실측). 이제 `tools/deploy/compose_up_changed.sh` 가 **마지막 성공 배포 SHA 마커**(`.deployed_sha`, git 밖)와 HEAD 의 누적 diff 로 모드를 고른다 — **full**(`src/`·`requirements.txt`·`Dockerfile`·`docker-compose.prod.yml`·`.dockerignore`·`deploy.yml`·`tools/deploy/` 중 하나라도 변경 → 현행 동일 `up --build`) / **frontend**(`frontend/` 만 → `up --build --no-deps frontend`, backend 무접촉 실측) / **none**(그 외 tests·`tools/test_impact`·`pyproject.toml` 등 또는 마커==HEAD 재실행 → 빌드 없는 `up -d` = Running). ⚠️ `**.md`·`docs/**`·`_workspace/**` 만 바꾼 push 는 CI `paths-ignore` 로 **CI/Deploy 자체가 뜨지 않는다**(마커는 다음 배포의 누적 diff 가 따라잡음 — 09-05 실측 d9561f1). 판정 불가(마커 없음·미지 SHA·diff 실패)는 전부 **full**(fail-safe = 현행). 마커는 compose 성공 뒤에만 쓴다. 분류의 근거는 루트 Dockerfile COPY 소스가 `requirements.txt`·`src/` 뿐이라는 구성적 사실(가드 D-8)이고, `test_cycle248_deploy_pipeline.py::G-248-2` 가 COPY 소스 ↔ 정규식 정합을 강제한다(COPY 를 늘리면 붉어진다). ⚠️ `.env` 는 git 밖이라 스크립트가 못 본다 — `.env` 를 손댄 뒤에는 운영자가 `docker compose up -d` 로 직접 재생성하고(**마커는 건드리지 않는다** — 마커는 git SHA 의 배포 상태만 뜻한다), backend `ports`·compose 변경은 full 로 자동 분류된다. 배포 로직 자체(`deploy.yml`·`tools/deploy/`)를 바꾼 push 는 의도적으로 full 이다(검증 안 된 판정으로 재시작을 건너뛰지 않는다). 운영자 사전 확인 = push **전** 로컬에서 `git diff --name-only <EC2 .deployed_sha 값> HEAD` 의 경로를 위 규칙에 대보는 것(EC2 dry-run 은 이미 pull 된 HEAD 만 본다) / EC2 에서는 `DEPLOY_DRY_RUN=1 bash tools/deploy/compose_up_changed.sh`(docker 미호출·마커 미기록, `true` 동치·미지 값 exit 2). ⚠️ `src/**` 는 확장자 무관 이미지 입력이다(`src/CLAUDE.md` 수정도 full). none 모드의 `up -d` 도 `.env` 등 구성이 어긋나 있으면 재생성한다(none ≠ 무조건 무재시작). **EC2 에서 git 을 손으로 움직였거나(reset/checkout/revert/stash) 수동 `docker compose build|up --build` 를 했으면 `rm ~/auto_stock/.deployed_sha`** — 마커는 git SHA 의 배포 상태만 뜻하고 실행 중 이미지와 대조하지 않는다(수동 배포는 스크립트로). 직전 배포가 중간에 죽으면 `.deployed_sha.attempt` 가 남아 다음 배포가 자동으로 full 이다
```

### 2026-09-05 cycle255 — TLS(443) 1단계 준비 절차 (전문)

```
- **cycle255 TLS(443) 1단계 준비 (2026-09-05) — `auto.dkstock.cloud`, cycle243 L1(TLS 부재) 후속.** 지금까지 Basic Auth 자격·`X-API-Key` 가 평문 HTTP 로 오갔다(20:20 리포터 루틴 포함). 이번 사이클은 **코드·절차만 준비**하고 아직 443 을 열지 않는다 — 활성화는 호스트 파일 `.tls_enabled`(git 밖) 존재 여부 하나로 스위치된다. 사용자가 도메인 관리 화면에서 **A 레코드(`auto.dkstock.cloud` → `3.38.228.74`) 를 직접 등록**한 뒤 EC2 에서 `LE_EMAIL=<메일> bash tools/ops/tls_enable.sh` 를 1회 실행하면: DNS·챌린지 경로 사전 점검 → `certbot certonly --webroot`(80 은 nginx 가 계속 쓴다, `--standalone` 금지) → 발급 산출물 확인 **뒤에만** `.tls_enabled` 생성 → `docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml up -d --no-deps frontend`(backend 무접촉, cycle232 D6 — 장중에도 전환 가능) → **사후 검증**(80 → 401 ∧ 443 → 401 ∧ frontend `State=running`, ≤10초 폴링 — `docker compose up -d` 는 크래시 루프여도 exit 0 이라 종료 코드로는 못 잰다, compose v5.1 실측) → 갱신 경로 검증(reload 훅 1회 실행 + `certbot renew --dry-run`, 실패는 WARNING 만) 순으로 진행하고, 오버레이 up 실패·사후 검증 실패는 마커 삭제 + base 단독 `up -d --no-deps frontend` 원복을 **스크립트가 실행**한다(80 은 그 원복 up 이 성공한 뒤에 다시 살아 있다 — 오버레이 up 이 non-zero 인 컨테이너는 created 로 멈춰 80 도 000 이다). 갱신 reload 훅은 `certonly --deploy-hook`(절대경로 docker + `--project-directory` + `exec -T`) 으로 renewal conf 에 영속돼 snap/apt timer 가 돌린다 — crontab 을 두지 않는다(ubuntu crontab 은 `/etc/letsencrypt` 쓰기 불가, 상대경로 compose 는 cron cwd 에서 실패). ⚠️ **이 커밋 배포 전 EC2 에서 `mkdir -p ~/auto_stock/certbot-www`**(`secrets/` 와 같은 사전 생성 규약) — 없으면 prod compose 의 bind mount 가 root:root 755 로 만들어 ubuntu 의 스크립트가 probe 를 못 쓴다(`.token_cache` root 소유 사고와 동일 계열, ubuntu:24.04 실측). 스크립트도 `sudo install -d -o $(id -u)` 로 방어하지만 사전 생성이 정본이다. `tools/deploy/compose_up_changed.sh` 는 이 마커가 있을 때만 모든 compose 호출에 `-f docker-compose.tls.yml` 를 덧붙인다(**모드 판정에는 개입하지 않는다** — 개입하면 TLS 를 켠 날부터 모든 배포가 backend 재시작이 되어 cycle248 이 없앤 비용이 부활한다). 신규 `frontend/nginx.tls.conf.template`(443, 인증서는 `/etc/letsencrypt/live/auto.dkstock.cloud/`, `TLSv1.2`/`TLSv1.3`, Basic Auth·아이콘 단락·`/api/` 프록시는 HTTP 템플릿과 동일 — `map` 은 두지 않고 HTTP 템플릿의 `map $remote_user $api_key_for_user`를 공유한다 — 중복 정의해도 nginx 는 **정상 기동**하고 뒤에 include 되는 `tls.conf` 의 map 이 조용히 이겨 모든 사용자의 `X-API-Key` 가 빈 값이 된다(무증상 backend 전면 401, nginx:alpine 실측) — 그래서 텍스트 가드 G-255-2f 가 유일한 방어다)은 인증서가 없으면 기동에 실패하므로 **기본 이미지에 굽지 않고** `docker-compose.tls.yml` 오버레이가 볼륨으로만 마운트한다. HTTP 템플릿엔 ACME HTTP-01 챌린지 location(`^~ /.well-known/acme-challenge/`, `satisfy any; allow all; root /var/www/certbot;`) 한 블록만 추가했다 — `auth_basic off;` 는 여전히 쓰지 않는다(D-1-b 불변). **1단계 범위**: 443 은 80 과 **병행**(리다이렉트 없음), HSTS 없음(브라우저에 되돌릴 수 없는 상태를 심으므로 안정화 후 2단계). 활성화 뒤 사용자 절차 = ① 20:20/**목** 20:30 루틴(주간 자문은 2026-09-09 사용자 지시로 화→목 이설, 종전 표기 "화" 는 09-05 시점 값)의 `BASE` 를 `https://auto.dkstock.cloud` 로 ② 클라우드 환경의 허용 도메인에 추가(`API_ALLOWED_ORIGINS` 는 same-origin 이라 변경 불필요) ③ 안정 1주 후 2단계(80→443 리다이렉트 + HSTS + Basic 자격 회전) 검토.
```

### 2026-09-05 cycle260 — TLS 2단계 준비 절차 (전문)

```
- **cycle260 TLS 2단계 준비 (2026-09-05) — http→https 301·HSTS·Basic 자격 회전, cycle255 L1 후속.** 사용자 결정(09-05 보고서 2부 카드④ "제안대로") — 가동 시점은 **월 09-07 20:20 자동 리포트가 https 로 성공한 것을 사람이 확인한 뒤**다. 이 사이클은 스위치를 켜지 않고 절차·코드만 준비한다(cycle255 와 같은 마커 게이트 패턴). 두 nginx 템플릿의 `server{}` 안에 스니펫 include 게이트 한 줄씩(HTTP `stage2/http-*.conf`, TLS server 레벨 `stage2/tls-srv-*.conf` + location 2곳 `stage2/tls-loc-*.conf`) — **서버 글롭과 location 글롭을 분리**했다(명세 원안 `tls-*.conf`+`tls-loc-*.conf` 조합대로면 `tls-*` 가 `tls-loc-hsts.conf` 까지 매치해 HSTS 가 서버·location 양쪽에서 중복 적용된다 — 실 nginx 로 반증 확인). `docker-compose.tls2.yml` 오버레이(frontend `volumes` 에 `tools/ops/tls_stage2:/etc/nginx/conf.d/stage2:ro` 하나뿐)가 스니펫 디렉터리를 마운트하며, 마커가 없으면 그 디렉터리가 없어 glob 이 아무것도 못 찾고 렌더 결과가 1단계와 **byte 동일**함을 실 nginx:alpine(1.31.5) 3구성(BASE/OFF/ON) 실측으로 확인했다. `tools/ops/tls_stage2_enable.sh` 는 `.tls_enabled`·인증서·로컬 https 401·**`ROUTINE_HTTPS_CONFIRMED=1`**(사람이 월요일 루틴 결과를 보고 넣는 게이트, 없으면 아무것도 안 함)를 선결 확인한 뒤 `.tls_stage2` 를 만들고 오버레이를 올리고, **검증 4경로**(80 `/`→301+도메인 고정 Location, ACME 챌린지→404 유지, 443 무자격 401+HSTS 헤더, 443 정적자산 HSTS 헤더)를 폴링해 실패하면 마커 삭제 + 1단계 원복까지 스스로 실행한다. `tools/ops/rotate_basic_auth.sh` 는 2단계 가동의 **필수 후속**이다 — 301 은 서버가 자격을 요구하지 않게 할 뿐 브라우저가 선제로 보내는 옛 자격까지 막지 못하므로(`curl -u` 실측: 301 을 받기 전에 `Authorization` 헤더를 평문으로 먼저 보낸다), `secrets/.htpasswd` 사용자 목록을 파일에서 읽어(하드코딩 금지) `openssl rand -base64 18` 새 비밀번호 + `openssl passwd -apr1 -stdin` 해시로 교체하고, **새 비밀번호는 화면에 출력하지 않고 `secrets/.rotated-<ts>`(권한 600) 파일로만** 전달한다 — 운영자가 그 값을 읽어 클라우드 루틴의 `REPORTER_BASIC_PASSWORD` 갱신 + 브라우저 재로그인까지 마쳐야 회전이 끝난다. HSTS 는 **1일**(`max-age=86400`)로 시작(includeSubDomains·preload 없음), 상향은 1주 안정 후 별도 결정. 원복(disable)은 `.tls_enabled` 존재 여부로 1단계까지만 되돌리거나 완전히 끈다. 적대 검토가 HIGH 2건을 찾아 배포 전 시정·테스트로 봉인했다 — rotate 검증이 백엔드에 없는 `/api/health` 를 찔러 항상 실패로 오판하던 결함(→ nginx 가 직접 서빙하는 `/` 로 정정) · HSTS 헤더 검사가 접두 매치라 `max-age=0` 도 통과시키던 뮤테이션 ESCAPED(→ 정확 값 매치로 조임). src·8영역·`scheduler.py`·`.env` diff 0, 신규 가드 168 PASS(cycle255 3파일 재검증 포함), 백엔드 전체 7,005 PASS. **사용자 할 일 = 월요일 20:20 루틴 https 성공 확인 → EC2 에서 `ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh` 실행 → 완료 뒤 `rotate_basic_auth.sh` 로 비밀번호 회전.**
```

### 2026-09-11 cycle279 — 프로세스 분리 1단계 준비 기록 (전문)

```
- **cycle279 프로세스 분리 1단계 준비 (2026-09-11) — 배포 모드 3종 → 4종(예정).** 1단계(AI 매수평가(LLM)를 `llm_worker` 컨테이너로 분리, 큐로 재사용할 대상은 신규 브로커가 아니라 `llm_buy_evaluations` 테이블 = migration 043)가 **진행 중**이다 — 근거는 사용자 결정(2026-09-11 "1단계만 진행")이고 `cycle279` 는 **예약한 번호**라 명세·코드는 아직 없다. 워커 모드(**미구현 · 예정**)는 `frontend` 모드와 같은 원리(`--no-deps`)로 backend 무접촉이 될 **전망**이다 — 현재 스크립트의 `case "$MODE"` 는 full/frontend/none **3갈래뿐**이고 미지 모드는 `exit 2` 다(`tools/deploy/compose_up_changed.sh:188-203`). ⚠️ **`llm_worker` 는 `docker-compose.prod.yml` 본체에 정의한다** — TLS 처럼 오버레이에만 두면 그 오버레이를 안 붙이는 `full`·`none` 배포의 `--remove-orphans`(`:190`/`:198`)가 돌던 워커를 orphan 으로 삭제한다. ⚠️ **지금의 `BACKEND_RE` 는 첫 대안이 `src/` 다**(`:85`) — 워커 코드를 `src/` 아래 그대로 두면 워커 전용 변경도 `full` 로 분류돼 backend 가 재시작된다(D6 발동). 워커 축 경로와 `BACKEND_RE` 제외 방식은 cycle279 명세에서 확정한다. 2단계(20:00 자문·21:30 로그 분석·외부 백테스트 분리)는 **계획**이며 **위험이 균일하지 않다** — 20:00 자문의 `auto_apply` 는 `recommendation_engine.py:626`/`:657` 에서 **살아 있는 전략 객체**를 직접 변이하는 파라미터 즉시 반영의 유일한 경로라, 워커로 옮기면 반영이 다음 재시작으로 밀린다(매매 행위 변경). 퍼널 스냅샷은 원천이 엔진 메모리(`scheduler.py:186` 이 `_funnel_steps` 순회)라 **가를 수 없다**. 3단계(시세 감시 ↔ 전략 판정 ↔ 주문 완전 분리)는 **보류** — REST 20/s·토큰 분당 1건·체결통보 메인 세션 단일·매수 원자성이 전부 프로세스 안 자원이라 착수 전 별도 설계 + 사용자 승인이 필요하다. 단계별 도식 5개와 보류 근거의 파일:행 인용 = [`docs/architecture.md`](docs/architecture.md) 15장
```

### cycle232 D6 · cycle283 D8 — 배포 창 규약 경위 (전문)

```
- 운영 가이드: **보유 포지션이 있으면 KRX 메인 시간(09:00~15:30) push(=EC2 자동 배포) 금지** (cycle232 D6 승격, 2026-08-29 — 재시작 1~5분 tick blind 동안 손절 사각 + `_scan_loop` 5분 race. 08-24 장중 재배포가 donchian `_breakout_high` 소실을 실측시킨 선례). 보유 0이면 종전 권고(빈번한 push 자제) 수준. push 는 NXT 애프터(15:30~) 또는 익일 07:55 _boot 전. **20:00~21:35 도 피한다**(cycle283 D8 — 20:00 AI 자문 · 20:05 metrics 1차 스냅샷 · 20:30 일봉 적재 · 21:30 정산/`_reset_daily_state`. 그 창의 재기동은 기동 거부 경계 `TIME_SESSION_START_CUTOFF`(20:00) 에 막혀 그날 저녁 블록 전체 — 20:30 일봉 적재 · `_settle()`(daily_performance) · 일일 로그 분석 · 로그 retention — 이 통째로 결손된다(넷 다 `TIME_SETTLEMENT` 뒤라 한 번에 사라진다). `[daily_head_stale]` WARNING 이 다음 아침 07:55 에 일봉 결손을 알리고, 복구 절차 3종은 `src/routes/CLAUDE.md` 의 `/api/trading/restart` 행에 있다). 즉 장외 배포 창은 **15:30~16:00 · 21:35~익일 07:45**. 16:00~20:00 은 2026-09-14 신설된 **KRX 애프터마켓 실시간 연속체결** 구간이라 재시작이 D6 이 막으려던 것과 같은 tick blind 를 만든다(종전 표기 `15:30~19:55` 는 시간외 단일가 시절 값이라 폐기). 08:00~08:50 NXT 프리장도 실매매 구간이다(2026-09-15 실증 — LTV 매수 3건·손절 2건 체결). ⚠️ 15:30~16:00 이 온전한 공백이 되는 것은 cycle295(15:30~16:00 완전 휴식) 착지 **뒤**다. 그 전에는 15:40~16:00 에 NXT 청산 경로가 구조적으로 열려 있다 — 다이얼 `tick_channel_gap_hold_enabled=false`(2026-09-15 적용)가 시세를 끊어 실질 무주문이지만, 확실히 하려면 **15:30~15:40** 을 쓴다. **cycle248 이후** — 이 금지는 backend 가 재생성되는 push(full 모드)에만 실질 적용된다. frontend 전용·docs 전용 push 는 backend 를 건드리지 않지만, **push 전에 어느 모드인지 확신이 없으면 full 로 간주**한다(`tools/deploy/` 나 `deploy.yml` 이 섞인 커밋은 항상 full)
```

### 2026-09-05 cycle243 — nginx Basic Auth 결손 증상 3갈래 (전문)

```
- `frontend/nginx.conf.template`: 정적파일 + `/api` → backend:8000 프록시 + **사이트 전체 Basic Auth**(cycle243). `nginx:alpine` 엔트리포인트가 `/etc/nginx/templates/*.template` → `/etc/nginx/conf.d/` 로 envsubst 렌더(`NGINX_ENVSUBST_FILTER=^API_(AUTH|REPORTER)_KEY$` 로 치환 변수 2개 제한, cycle249 리포터 키 추가). `map $remote_user $api_key_for_user { default "${API_AUTH_KEY}"; reporter "${API_REPORTER_KEY}"; }` 가 http 컨텍스트(server 블록 밖·앞)에서 Basic 사용자별 키를 고르고, `location /api/` 는 `proxy_set_header X-API-Key $api_key_for_user;` 로 그 결과를 주입한다(치환 구문은 이제 `map` 블록 안에만 존재 — cycle246 "주석 금지" 관례가 여기도 적용). 자격 파일은 호스트 `./secrets/.htpasswd` bind mount(**git 커밋 금지**). 결손 증상 3갈래(실측) — **무자격은 어떤 상태에서도 401**(정상과 동일 = 무자격 curl 로는 결손을 판별할 수 없다) / 자격 + 파일 부재 → **403** / 자격 + 권한 거부 → **500**. ⚠️ 권한: nginx worker 는 컨테이너 안 **uid 101(nginx)** 이고 호스트 파일은 `ubuntu`(uid 1000) 소유라 `chmod 600`·디렉터리 `chmod 700` 이면 전면 500 이다(`.token_cache` root 소유 사고와 동일 계열) → `chmod 755 secrets` + `chmod 644 secrets/.htpasswd`. 구 `frontend/nginx.conf` 는 삭제됐다(되살리면 인증 없는 구버전이 조용히 서빙되는 fail-open). `auth_basic off;` 는 이 템플릿에 **절대 쓰지 않는다** — 한 줄로 Basic Auth 와 백엔드 X-API-Key 주입이 동시에 뚫린다(AST 가드 D-1-b)
```

## 디렉토리 역할

### `src/workers/` — 4단계(메시지 기반 5프로세스) 방향 기록 (전문)

```
- `src/workers/` — 프로세스 분리 1단계(cycle279 — `llm_worker` 컨테이너, 진행 중)에서 워커 진입점이 들어올 자리. **아직 없다.** 4단계(메시지 기반 5프로세스)는 **승인 전 방향 기록**이지만, 그것이 승인되면 이 자리에 들어올 축은 워커 1개가 아니라 **5개**(W 웹소켓 · R REST · 1 시세·전략평가 · 2 주문 · 3 체결)가 된다. 그때 필요한 것은 진입점 파일만이 아니다 — 로깅·DB풀 부트스트랩이 `src/main.py` 모듈 로드와 lifespan 에 묶여 있어 uvicorn 없는 프로세스가 그것을 import 하면 메모리 바닥이 5배가 되므로, **공용 부트스트랩 모듈 분리가 4단계의 사실상 첫 커밋**이다(제약 F). 상세 = [`docs/architecture.md`](docs/architecture.md) 15.2 · 15.5
```

## DB 스키마

### `stock_master` · `stock_master_daily` — 컬럼 추가 사이클 경위 (전문)

```
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + **사이클 129 `master_raw` JSONB + `master_raw_updated_at TIMESTAMPTZ` 신규** (KIS 공식 일일 마스터 파일 영역 — 시총/거래정지/관리종목/지수편입/재무 ~30 키, raw 영역 분리 보호). NXT 거래가능 사전 판별. **사이클 168 생성 컬럼 `hts_avls_eok bigint`(억원) + `acml_tr_pbmn_won bigint`(원) GENERATED ALWAYS STORED** (migration 039 — raw.hts_avls/acml_tr_pbmn 가 jsonb *문자열* 로 저장되어 UI `list_paged_by_filter` jsonb numeric gte 가 0건 silent 결함 → 생성 컬럼 numeric 비교 + 인덱스로 시정. 비숫자는 `~ '^[0-9]+$'` 가드로 NULL. raw 읽기만 = 사이클 81 G-AST1 영속) |

| `stock_master_daily` | KIS FHKST03010100 일봉 정규화 (migration 033). PK `(ticker, bas_dd)` + OHLCV + change_rate + raw JSONB. 매일 16:00 KST 적재 (백필 시 T-100일, 이후 D-1 영업일 증분). **사이클 172 — VCP universe (KOSPI200∪KOSDAQ150) backfill** (분할 fetch) + retention `DAILY_RETENTION_DAYS=230`. **사이클 196 (2026-07-07) — VCP backfill target 220→120 수렴** (retention 230cal=154영업일 실측 < 220 → 무한 재backfill churn → target 120 하향 + `fetch_daily_candles_backfill` 윈도우 클램프, VCP prepare 실사용 100일 << 154 보유 무영향). donchian (20일 신고가) / VCP (베이스+Pullback, prepare 100일 cap) / VB (ATR) 전략 활용 |
```

---

## 2026-09-17 정리 2차(검증 렌즈) — 정본에서 추가로 걷어낸 원문
> 원본: `CLAUDE.md` · 이관: 2026-09-17 · 아래 각 항목은 정리 1차 뒤 남아 있던 시점 주석·폐기 값을 걷어낸 원문 그대로다.

### ## 환경 변수 — `DKSTOCK_REGIME_ENABLED`

```
(매수 가드는 사이클 I 제거 — 레짐은 관찰 전용)
```

### ## 환경 변수 — `KIS_MCP_ENABLED`

```
자문 직후 6 전략 × 2 kind = 12 job fire-and-forget
```

### ## 다중 전략 (요약) — 7 전략 행

```
`kojiro`(고지로 대순환 스윙, 2026-07 Phase 1 다크런치 `enabled=False`)
```

### ### 자금 관리 — 전략별 투자한도 행 머리

```
- **전략별 투자한도 (2026-08-03 이중 → 2026-08-04 kojiro 삼중)** — ① 개수 `max_positions` + ② 명목 `Σ매수금액 ≤ total_investment` + ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). 터틀의 유닛 캡이 통제하려던 값은 ③이고 유닛 **개수는 프록시**일 뿐 — 수량 절삭·`hard_stop_pct` 캡·사이징 혼재로 프록시가 헐거워진다(08-04 실측 6포지션=3.2유닛). **개수 캡을 리스크 캡으로 대체 금지**(저ATR 종목 포지션 수 폭증). ②는 ②는 `StrategyBase._apply_budget_limit`
```

### ### 외부 통합 (백테스트 + 매크로 레짐) — 백테스트 행

```
- 20:00 AI 자문 INSERT 직후 외부 MCP 백테스트 (`http://43.202.187.5:3846/mcp`) — 6 전략 × 2 kind = 12 job fire-and-forget →
```

### ### 외부 통합 (백테스트 + 매크로 레짐) — 매크로 레짐 행

```
**매수 가드는 사이클 I(2026-08-03) 제거** — 레짐은 매수를 차단/축소하지 않는 관찰 지표(`buy_block_mode` 는 표시 전용 잔존, `get_buy_block_state` 는 대시보드/자문 payload 만 소비). ETF 레짐(E-1)·포트폴리오 리스크(사이클 H) 관찰 활성
```

### ## 핵심 안전 규칙 (절대 깨지 말 것) — WebSocket 다중 안전망 — K stale watcher 괄호

```
 + 시간당 6회 cap, 사이클 102 임계 상향)
```

### ## DB 스키마 — `backtest_runs` 행

```
6 전략 × 2 kind = 12 row/사이클)
```

### ## DB 스키마 — `strategy_funnel_snapshots` 행

```
수동 trigger `POST /api/strategy-funnel/snapshot` (현재 최종 단계 `step_no=99` 만, 자동 hook 은 후속 사이클)
```

### ## Docker / 배포 — TLS 행 — 자격 회전 상태 표기

```
**남은 절차 = `tools/ops/rotate_basic_auth.sh` 로 Basic 자격 회전**(미실행) — 301 은
```


### 2026-09-17 cycle298 이관 — `07:55` 시각 꼬리표 2곳

`TIME_BOOT`(07:55) 은 런타임 참조가 0건이고 `_boot()` 는 `scheduler.start()` 안에서 즉시 돈다
(`scheduler.py:600`, 2026-09-17 grep 전수). 아래가 그 전까지 정본에 있던 구절이다.

```
(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회이고 07:55 `_boot` 재호출은 no-op)

`[daily_head_stale]` WARNING 이 다음 아침 07:55 에 일봉 결손을 알리고,
```

같은 꼬리표를 `src/db/CLAUDE.md:92` · `src/routes/CLAUDE.md:38` · `src/engine/strategies/CLAUDE.md:73` ·
`README.md` 에서도 걷어냈다(구절 교체뿐이라 옮길 내용이 따로 없다). 경위 정본 =
[`src-engine-CLAUDE.history.md`](src-engine-CLAUDE.history.md) 의 같은 날짜 항목.

→ CHANGELOG: cycle298 행

## DB 스키마 — `stock_master_daily` 행

### 2026-09-17 cycle299 — backfill target·retention 값 교체

경위·수치의 정본은 [`src-db-CLAUDE.history.md`](src-db-CLAUDE.history.md) 의 같은 날짜 항목이다.
루트 정본에서는 표의 한 행만 새 값으로 덮었다.

원문(`CLAUDE.md:212` 중 바뀐 부분, 2026-09-17 이관):

---

VCP universe(KOSPI200∪KOSDAQ150) backfill target **120일** · retention `DAILY_RETENTION_DAYS=230`(230 캘린더일 = 154 영업일 실측이라 target 을 그보다 크게 잡으면 무한 재backfill churn)

---

→ CHANGELOG: cycle299 행

### cycle299 (2026-09-18) — 목표를 220 → 225, 보존을 380 → 390 으로 다시 올린 경위

사이클 안에서 값이 한 번 더 움직였다. 앞 항목에 380/220 으로 적힌 서술은 그 시점의 기록이고,
확정값은 **retention 390 달력일 · VCP backfill target 225 영업일** 이다.

- **왜 225 인가** — VCP 추세 필터의 `effective_ema_long = min(ema_long, 보유 − uptrend_days(20) − 5)`
  에 운영 DB 값(`ema_short=50` / `ema_mid=150` / `ema_long=200`)을 넣고 보유 영업일을 움직이면,
  보유 220 에서는 실효 장기선이 **195** 에 그치고 **225 에서 정확히 200** 이 된다. 미네르비니 원전의
  200EMA 를 형식이 아니라 값으로 성립시키는 최소 깊이가 225 다. 같은 계산에서 mid↔long 간격도
  220 의 45 에서 225 의 50 으로 벌어진다(보유 100 이면 간격 10 = 사실상 동전던지기였다).
- **왜 retention 도 함께 올렸나** — 가드 `G-299-3c`(`retained_trading(retention) >= target + 30`)
  때문이다. 환산 앵커 230cal ⇄ 154영업일로 `retained(380) = 254` 인데 `225 + 30 = 255` 라 **1 모자라
  FAIL** 한다. 3c 를 만족하는 retention 최소값은 **381** 이고, 여유를 두어 390 을 택했다
  (`retained(390) = 261` → 마진 **36 영업일**, 사이클196 의 34 보다 크다).
- **실측(가드 헬퍼 `_capture_backfill_reach_cal` 로 확인)** — `total_days=225` 의 윈도우는 3개
  (100/100/25), 최고 도달 **325 달력일** < retention 390(여유 65cal). 1회 backfill 실도달은
  `trading_days_in(325) = 217` 영업일이라 target 에 **8 영업일** 모자라고, 이 부족분은 220 일 때와
  같다(둘 다 8). 전이 기간과 비용 추정은 앞 항목과 동일하다.
- **재핀** — `scanner.py` 가 다시 바뀌어 8영역 sha 핀 13곳(`_PIN_GUARD_FILES` 4 + 기준선 9)과
  `test_cycle287::_SRC_TREE_DIGEST` 를 같은 값으로 한 번 더 옮겼다. 단언은 약화되지 않았다.

### cycle299 (2026-09-18, 이어서) — 달력 환산을 고쳐 1회 backfill 이 목표를 넘게 했다

사용자 요청("데이터 지금 바로 채울 수는 없어?")으로, 별건으로 미뤄 두었던 환산식을 이 사이클에서 고쳤다.

- **고친 것** — `fetch_daily_candles_backfill` 의 **깊이**(마지막 윈도우 시작점) 환산에만 휴일 보정을
  비례로 얹었다: `int(n*7/5) + int(n*0.10) + 10`. 상수 3개를 이름으로 뽑고 근거를 주석에 남겼다
  (`_WEEKEND_CAL_PER_TRADING_DAY` / `_DAILY_BACKFILL_HOLIDAY_MARGIN_RATIO` / `_DAILY_BACKFILL_BASE_MARGIN_CAL`).
- **왜 계수를 통째로 올리지 않았나** — `3/2`(=1.50) 제안은 **stride 까지 함께 키운다**. KIS 가 한 호출에
  100건까지만 주므로 앞 윈도우는 공휴일이 하나도 없는 구간에서 정확히 100영업일 = **140 달력일**까지만
  덮는다. stride 가 140 을 넘는 순간 다음 윈도우의 머리가 그 바닥보다 아래로 내려가 **사이 구간이 통째로
  비고**, 빈 날짜는 어느 윈도우도 다시 집지 않는다(`3/2` 면 stride 150 > 140). 그래서 stride 는 7/5 로
  두고 깊이에만 보정을 얹는 형태를 택했다. 구멍 검사는 공휴일 0 이라는 최악 가정으로 확인했다.
- **실측** — `total_days=225` → 윈도우 3개 `[(0,160), (140,310), (280,347)]`, 최고 도달 **347 달력일**.
  실측 비율(앵커 230cal ⇄ 154영업일 = 1.479)로 **232 영업일**이라 목표 225 를 **7 넘는다**. 공휴일이
  없는 해(1.40)에는 247, 밀집한 해(1.52)에도 228 로 어느 쪽도 목표 위다. 전이 기간이 사라졌다.
- **가드** — `retention 390` 기준 3a(347 < 390, 여유 43) · 3b(347+30 = 377 ≤ 390) · 3c(261 ≥ 255) 전부
  통과라 retention 은 옮기지 않았다. `G-299-9` 는 "부족분 ≤ 10"(음수에서 공허해진다)에서
  **"실도달 ≥ target"** 으로 부등식을 뒤집어 강화했다.
- **`scanner.py` 무접촉** — 변경을 `condition.py` 에 가둬 8영역 sha 핀 13곳을 다시 옮기지 않았다.
  움직인 것은 `test_cycle287::_SRC_TREE_DIGEST` 하나다.
- **호출자** — `fetch_daily_candles_backfill` 의 프로덕션 호출자는 `scanner._stock_master_daily_load_once`
  **하나뿐**임을 `grep` 으로 재확인했다. 별도 함수 `fetch_daily_candles` 는 무접촉이다.

## DB 스키마 — `stock_master_daily` 행 (cycle302, 2026-09-18)

`backfill target 225일` 의 **대상** 표기를 덮어썼다. 종전 정본은
`VCP universe(KOSPI200∪KOSDAQ150) backfill target 225일` 이었다.

바뀐 사실 = backfill 분기 조건에서 지수 소속 판정이 빠져, 일봉 적재 대상
(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호 = 2026-09-18 실측 962종목) 전부가
`existing_count < 225` 일 때 같은 분할 backfill 을 탄다.

근거 실측(2026-09-18 09:37) = 지수 348종목은 225행 이상 100%(평균 232)인데 **비지수 1,526종목은
0%**(평균 125)였다. VCP 평가 대상 628 중 약 280(45%)이 `effective_ema_long` 74~121 에 묶여
중기↔장기 간격 10 안팎, 곧 정배열 판정이 동전던지기였다.

정상 운영 비용은 불변이다 — 깊이에 닿으면 증분 1콜로 내려오고 retention 390cal(≈261 영업일)이
225 아래로 떨어뜨리지 않는다. 첫 채움(962종목 × 3콜 ≈ 2,886 호출 ≈ 345초)만 20:30 스케줄이 아니라
장 종료 후 수동 trigger 로 돌린다(`TIME_QUOTE_TOKEN_REFRESH`(20:45) 불변식 창 20:35~ 를 1분 침범).

상세 = `docs/history/src-engine-CLAUDE.history.md` 「분할 backfill 분기 — 대상 확대」.

## DB 스키마 — `strategy_funnel_snapshots` 행

### 2026-09-25 cycle350 — UNIQUE 키 서술 교체 (migration 035 뒤에도 남아 있던 옛 키)

정본 표 행 원문. UNIQUE 는 migration 035(cycle145)부터 `(target_date, strategy_id, step_no)` 였다:

| `strategy_funnel_snapshots` | 전략별 조건검색 단계별 후보/탈락 종목 영구 추적. `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE. `survived_tickers` JSONB cap 200 / `excluded_sample` JSONB cap 20. 09:30 자동 캡처(`scheduler._auto_capture_funnel_snapshots`, 단계별 + `step_no=99`) + 수동 trigger `POST /api/strategy-funnel/snapshot`(`capture_funnel_snapshots(registry, is_provisional=False)`) |

→ CHANGELOG: cycle350 행

## 자금 관리 — `max_lot_units` 항목

### 2026-09-25 — 「피라미딩 착수 시 K→1.0」 교체 (설계안 D-2, 사용자 결정 2026-09-24)

정본 문장 원문:

피라미딩(사다리 증량) 착수 시 **K→1.0** 으로 조인다(K=2 랏 + 4유닛 사다리 = 8유닛 = R15 재위반).

바뀐 사실 = 사용자가 설계안 `_workspace/design/2026-09-24_three_stage_sizing_pyramiding.md` D-2 ⓐ 를
택했다 — K 는 2.0 을 유지하고, 1주 폴백으로 산 랏에는 사다리를 걸지 않는다.

근거(설계안 §5 · 자문 `_workspace/domain_consult/cycle345_three_stage_pyramiding.md` Q4) = 사다리 트랜치는
전부 정상 분기(≥2주)라 K 캡에 닿지 않는다. 8유닛 문제는 「K=2 폴백 랏 위에 사다리」 조합에서만 생기므로
그 조합을 막으면 닫힌다. 반대로 K→1.0 은 사다리와 무관하게 kojiro 신규 진입 8%·donchian 20% 를 없앤다
(u<1 종목의 1주 폴백 랏 차단, 09-24 예산 기준).

같은 서술을 함께 고친 곳 = `_workspace/00_leader_trading_rules.md` · `docs/trading_base/{피라미딩,자금관리,리스크관리,README}.md`
· `_workspace/00_URGENT_WORKLIST.md`(결정 완료 3번 · R6 행 폐기 표시).

## 핵심 안전 규칙 (절대 깨지 말 것)

### 2026-09-27 cycle380 — 「종목코드 형식 비대칭」 의 차단 대상

정본 원문(목록 행):

- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지

경위: cycle380(사용자 결정 2026-09-27 「운영db 조회 허용 및 판정 변경 채택」)이 ETF/ETN 판정을 이름 키워드에서 증권그룹코드 `scty_grp_id_cd ∈ {EF,EN,FE}` 로 바꿨다. 판정은 leaf `src/engine/etf_like.py::is_etf_like` 하나로 모였고, 코드가 없을 때만 이름 키워드로 떨어진다. 「ETF… 자동매매 차단」 은 사실이 아니었다 — ETF 코드도 6자리 숫자라 `isdigit()` 를 통과한다(`stock_master` 3,583행 전부 6자리 숫자, EF 873행 포함, 2026-09-27 읽기 전용 조회). 이 규칙이 실제로 막는 것은 영숫자 코드와 7자리 ETN 코드다(`docs/kis/domestic-stock-order.md` `PDNO` 「ETN의 경우 7자리」).

→ CHANGELOG: cycle380 행

## 외부 통합 (백테스트 + 매크로 레짐) · 디렉토리 역할

### 2026-09-27 cycle382 — 「레짐은 매수를 차단·축소하지 않는다」 를 매크로 레짐 한정으로

정본 원문(「외부 통합」 목록 행):

- 매크로 레짐 (**우리 `macro` 컨테이너**, cycle315) — `regime/vix/fear_greed` 관찰 + `cash_usage_ratio` 자동 조정 (`auto_regime_adjust`, `clamp((100-cash_min)/100)`). **레짐은 관찰 지표다 — 매수를 차단·축소하지 않는다**(`buy_block_mode` 는 표시 전용, `get_buy_block_state` 는 대시보드/자문 payload 만 소비). ETF 레짐·포트폴리오 리스크 관찰 활성

정본 원문(「디렉토리 역할」 `macro/` 행):

- `macro/` — **매크로 API 별도 컨테이너** (경기사이클·투자체제·금리차·하이일드·환율·원자재 5섹션 = `GET /api/macro/*`). 자체 `Dockerfile`·`requirements.txt`(pandas/numpy/yfinance)·`main.py` 를 갖고 매매 이미지와 완전 분리된다 — **`src/` 아래로 옮기지 않는다**(옮기면 macro 변경마다 매매 backend 가 재시작된다). `macro/macro_lite/` 는 stock-manager 추출 패키지의 **무수정 vendor** 라 재이식 시 통째로 덮어쓴다. 캐시는 `MACRO_LITE_CACHE_DIR` 영속 bind mount 필수(FRED 가 OAS 를 3년치만 주므로 누적 store 가 유실되면 하이일드 **차트**의 10년·5년 구간이 3년으로 영구 퇴행). **매매 레짐의 출처이기도 하다**(cycle315) — `src/engine/market_regime.py` 가 `src/services/macro_client.py` 로 이 컨테이너를 부른다. 다만 레짐은 여전히 **관찰 지표**라 매수를 차단·축소하지 않는다. 운영 가이드 = [`docs/macro-lite.md`](docs/macro-lite.md)

경위: cycle382(사용자 결정 2026-09-27 「시장유닛 단계형 권고대로 채택」)가 터틀 4전략(kojiro·donchian_swing·bull_flag_breakout·vcp_breakout)의 신규 진입 설계 랏을 KODEX 200(`069500`) 60일선 계단(1 / 0.75 / 0.5 / 0)으로 줄이는 **시장 유닛**을 넣었다(4전략 기본 `market_unit_mode="shadow"` = 계산·기록만). 시장 유닛은 매수를 줄이므로 「레짐은 … 축소하지 않는다」 가 전체 문장으로는 더 이상 참이 아니다. 자문 `_workspace/domain_consult/cycle376_market_unit.md` §8 충돌 1 의 선택지 (a) — 매크로 레짐 교리는 그대로 두고 시장 유닛을 별개 사이징 규칙으로 적는다 — 를 따랐다. 시장 유닛 규칙은 「자금 관리」 절 새 항목에 적었다. 같은 결정으로 E-2 계획(ETF 스테이지를 `block_reason`·매수 가드로 통합)을 닫았다(자문 §8 · §12 질문 5).

→ CHANGELOG: cycle382 행

## 핵심 안전 규칙 (절대 깨지 말 것)

### 2026-09-27 cycle384 — 「보유한 채로 멈추는 수단은 없다」 교체

정본 원문(「보유 포지션이 있는 전략을 끄지 않는다」 항목 중 바뀐 세 문장):

- 🔴 **한 전략을 「보유한 채로」 멈추는 수단은 없다. `weight=0` 은 더 나쁘다**
- 지금 할 수 있는 것은 **그 전략 보유를 먼저 비우고** 끄는 것뿐이다.
- 보유한 채로 신규 유입만 줄이려면 **`position_ratio`·`max_positions`(PUT params — `enabled` 를 건드리지 않고 하한선 검증도 없다)** 를 쓴다.

경위: 사용자 결정 2026-09-27 「돈키언 신규매수 중지」 — 돈키언 보유분은 원래 청산 규약대로 나가게 두고, 개조 전까지 새 매수만 멈춘다. 설정으로는 할 수 없었다(돈키언 매수 창 09:05~09:30 이 코드 고정). 전략 끄기·`weight=0` 은 보유분 손절을 멈추고, 수량 0 반환은 900초 「투자금 부족」 으로 오귀인되고, `buy_disabled` 는 일일 손실 래치라 밤에 풀린다. 그래서 cycle384 가 7 전략 공통 `DEFAULT_PARAMS["buy_paused"]=False` 를 두고 공통 매수 게이트 `_account_soft_gate_blocked` 둘째 문장에서 신호를 막게 했다. 「보유한 채로 멈추는 수단은 없다」 는 사실이 아니게 됐다. `weight=0` 경고와 「끄려면 보유를 먼저 비운다」 는 그대로다. 명세 = `_workspace/red/cycle384_buy_paused_spec.md`.

→ CHANGELOG: cycle384 행

## 핵심 안전 규칙 (절대 깨지 말 것)

### 2026-09-27 cycle385 — 「체결통보 주문수량은 3단 출처」 항목의 매도 피해 · 재주문 타이머 사유

정본 원문(두 구절):

- 매도는 미체결 잔량이 **손절 감시 밖으로 사라지고**, 매수는 잔여 통보가 조용히 버려진 채 **영원히 적은 수량으로 믿는다**(15분 sync 도 기보유는 안 고친다).
- 🔴 **재주문 타이머는 `qty_src=="map"` 일 때만**(`_cancel_and_reorder` 에 포지션 재조회가 0건이라, 없으면 **사람이 낸 주문을 30초 뒤 취소하고 다시 낸다**)

경위: cycle385(사용자 결정 2026-09-26·27 분할 매도 허용 · 「b7 분할매도 진행」)가 매도 체결을 주문 축과 보유 축으로 나눴다. 매도는 주문 축이 틀려도 보유 축이 잔량을 지킨다. J-2 가 `_cancel_and_reorder` 에 발사 직전 보유 재조회를 넣어 「재조회 0건」 은 사실이 아니게 됐지만, 취소는 조건 없이 나가므로 게이트의 이유(사람이 낸 주문을 취소·재발사)는 그대로다. 새 항목 「매도 체결은 두 축으로 판정한다」 를 바로 아래에 두었다.

→ CHANGELOG: cycle385 행

---

## 2026-10-01 sync-docs 압축 — 정본에서 이관

출처 = 루트 `CLAUDE.md`(이관 직전 HEAD `979c30b2`). 절 제목은 이관 시점의 정본 절 제목이다. 원문은 정본에서 바뀌거나 빠진 줄 전체를 그대로 옮겼다(일부만 바뀐 줄도 줄 전체).

### 기본 진입점 — `team-leader` 우선 — ⚠️ KIS 스펙의 시간 경계

```
- **⚠️ KIS 스펙의 시간 경계 — `docs/kis/*.md` 는 2026-09-11 03:00 워크북 스냅샷이라 「변경 전」 세계를 기술한다.** 거기엔 시간외 단일가(16:00~18:00)가 살아 있고 `H0STOUP0` 가 현역으로 적혀 있다. **2026-09-14 시행 제도 변경(KRX 애프터마켓 16:00~20:00 신설·시간외 단일가 폐지·시가단일가 08:20 확대·KRX 정규장 미체결 자동취소)은 세 곳에 나눠 적혀 있다** — 제도·시간표·보드 영향 = [`src/engine/CLAUDE.md`](src/engine/CLAUDE.md) `session.py` 절 · TR·필드 변경 = [`docs/kis/README.md`](docs/kis/README.md) 「제도 변경 공지 반영」 절(+ 각 필드 자리에 직접 반영, `docs/kis` 재생성 시 그 절을 보고 다시 넣는다) · 우리 할 일·실측 목록 = [`_workspace/00_URGENT_WORKLIST.md`](_workspace/00_URGENT_WORKLIST.md). 09-14 이후의 사실을 `docs/kis/` 에서만 찾으면 틀린 답이 나온다(실증: cycle280 자문이 이 함정에 빠져 존재하지 않는 「저녁 시세 공백」 CRITICAL 을 냈다). 순서 = 위 세 곳 → `kis-mcp-query` → `docs/kis/*.md` 본문
```

사유: 「실증: cycle280 …」 괄호는 사건 기록이라 정본에서 뺐다. 경계 규칙과 세 곳의 순서는 정본에 남는다.

### 환경 변수 — API_AUTH_KEY (cycle243)

```
- `API_AUTH_KEY` (cycle243): 백엔드 `X-API-Key` 인증 키. **미설정이면 fail-closed** — `/health` 를 뺀 전 경로 401 + 기동 시 `[api_auth_key_missing]` CRITICAL. 조용히 끄지 않는다(fail-open 은 "키가 없으면 인증이 사라진다" = 이 결함의 재현). 생성 `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`. 운영에서는 nginx 가 프록시 요청에 주입해 브라우저에 노출되지 않는다. 키 회전은 frontend·backend **동시 재시작**이 필요하므로 장 종료 후에만
```

사유: 「fail-open 은 … 이 결함의 재현」 은 같은 절의 API 인증 항목과 같은 이유 문장이라 그 항목 링크로 줄였다.

### 다중 전략 (요약) — 7 전략

```
7 전략: `momentum` / `volatility_breakout` / `long_tail_volatility` / `donchian_swing` / `bull_flag_breakout` / `vcp_breakout` / `kojiro`(고지로 대순환 스윙 — 운영 DB `strategy_config.enabled=True` 로 실매매 중, 코드 등록 기본값만 `enabled=False`).
```

사유: kojiro 의 운영 DB 상태(`enabled=True` 실매매 중)는 운영값이라 정본에서 뺐다. 활성 여부·비중의 운영값 정본 = DB `strategy_config`(`GET /api/strategies`), 코드 기본값 = `src/engine/strategies/CLAUDE.md` 머리말.

### 새 전략 추가

```
### 새 전략 추가
1. `src/engine/strategies/` 에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `src/engine/scheduler.py` `__init__` 에서 `registry.register()`
3. 필요 시 `scanner.py` 에 스캔 함수 추가
4. `strategies/CLAUDE.md` 표 + `_workspace/00_leader_trading_rules.md` 명세 추가
```

사유: 「새 전략 추가」 4단계는 `src/engine/strategies/CLAUDE.md` 「새 전략 추가」 절이 정본이다(AST 목록 등재 · `_DEFAULT_PARAMS_SHA` 재핀 · `param_catalog` 등재까지 보강돼 있다). 루트는 링크 한 줄로 줄였다.

### 자금 관리 — 전략 비중 단위 = 비율 0.0~1.0 (2026-08-18 확정)

```
- **전략 비중 단위 = 비율 `0.0~1.0` (2026-08-18 확정)** — `PUT /api/strategies/weights` 요청 바디 · `GET /api/strategies` 응답 `weight` · `strategy_config.weight` 컬럼 · AI 자문 `save_weights` 경로가 **모두 같은 단위**라 GET↔PUT 왕복이 항등이다. 라우트가 범위 위반은 422, Σ>1.0 payload 는 `success=false`(저장 미수행)로 거부하고, 부팅 시 `_load_strategy_config` 가 **레지스트리 등록 전략 행**의 개별 `weight > 1.0` 또는 Σ `> 1.001` 을 `[weight_config_anomaly]` WARNING 으로 관찰만 한다 — **자동 클램프·정규화 금지**(오염 값을 조용히 그럴듯하게 만들면 운영자가 실측할 근거가 사라진다), fail-open
```

사유: 「(2026-08-18 확정)」 시점 꼬리를 뺐다. 단위 계약 문장은 그대로다.

### 자금 관리 — 전략별 투자한도

```
- **전략별 투자한도 — 삼중** — ① 개수 `max_positions` + ② 명목 `Σ매수금액 ≤ total_investment` + ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). 터틀의 유닛 캡이 통제하려던 값은 ③이고 유닛 **개수는 프록시**일 뿐 — 수량 절삭·`hard_stop_pct` 캡·사이징 혼재로 프록시가 헐거워진다. **개수 캡을 리스크 캡으로 대체 금지**(저ATR 종목 포지션 수 폭증). ②는 `StrategyBase._apply_budget_limit` 공통 관문이 7 전략 `calc_buy_quantity` 의 모든 return 을 통과시켜 강제하며, 잔여가 부족하면 **부분 매수**(잔여 < 1주 → 0). 불변식 **`position_ratio × max_positions ≤ 1.0`** — DEFAULT_PARAMS 는 AST 가드(C-DEFAULT)가, AI 추천은 `_validate_recommendations` 교차검증이 강제. `max_positions` 는 리스크 정체성 상수라 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**
```

사유: 삼중 한도의 상세(유닛 개수가 프록시인 이유 (a)(b)(c))는 `src/engine/strategies/CLAUDE.md` 「자금관리」 규약 첫 항목이 정본이다. 금기·불변식·편입 금지는 정본에 남는다.

### 자금 관리 — 1회 투자금액 ATR 유닛화 (sizing_mode="turtle")

```
- **1회 투자금액 ATR 유닛화 (`sizing_mode="turtle"`)** — `unit = floor(전략예산 × risk_pct ÷ ATR)`. **손절이 ATR 기반인 전략에만 적용**한다: 손절이 고정%면 명목이 종목 무관 상수라 `position_ratio` 가 이미 리스크 균등이고, 사이징만 ATR 로 바꾸면 정규화가 깨진다(함정 #1). 현재 배선 = donchian(라이브) · kojiro · VCP/BFB(다크런치, 하드손절 ATR화 동반). momentum/VB/LTV 는 제외 — 제외 사유는 전략마다 다르다: **momentum** = ATR 부재 · **VB** = 당일 15:20 청산 · **LTV** = 상한가 2모드 재설계 선행. ⚠️ VB·LTV 는 prepare 가 이미 일봉을 읽으므로 **ATR 산출 자체는 추가 I/O 0 으로 가능**하다(제외 근거가 데이터 부재가 아니라 함정 #1 이다). `compute_unit_qty_guarded` 의 notional 상한이 `position_ratio × 예산` 이라 **터틀 수량 ≤ 비중 수량**이 항상 성립 = 전환은 순수 축소 방향.
```

사유: 「donchian(라이브) · VCP/BFB(다크런치)」 는 운영 DB 상태라 정본에서 뺐다. 전략별 제외 사유와 「VB·LTV 는 ATR 산출이 추가 I/O 0 으로 가능」 은 strategies 「자금관리」 매트릭스 아래에 있다.

### 자금 관리 — 유닛화가 랏 미세화를 풀지 못한다(2026-09-20 실측)

```
  🔴 **유닛화가 랏 미세화를 풀지 못한다**(2026-09-20 실측) — 정수 절삭은 유닛식에도 똑같이 있어, 유닛을 쓰는 donchian·kojiro 도 매수의 **76%·52%가 1주**다. 랏이 1주 언저리인 원인은 사이징 방식이 아니라 **설계 랏 ÷ 그 전략이 사는 종목의 주가**(= `q`)다. `q` 는 **순자산에 정비례**한다 — 2026-09-20 입금(250만→500만) **전** 실측 = VB **0.37** · LTV **0.55** · donchian 1.35 · momentum 2.17 · BFB 2.83 · kojiro 5.06, **후**(순자산 약 500만) = 각각 **2배**(VB 0.74 · LTV 1.11 · donchian 2.70 · momentum 4.34 · BFB 5.66 · kojiro 10.11). ⚠️ **과거 체결 데이터는 전부 「전」 구간**이다 — 그때 VB 설계 랏은 44,031원인데 중앙 주가가 118,750원이라 **반 주도 못 샀다**. 비중·자금을 손대지 않은 채 유닛만 도입하면 `floor(예산 × risk_pct ÷ ATR) = 0` 이 되어 그 전략이 **전면 무매매**가 된다.
```

사유: 랏 미세화 실측 `q` 값(2026-09-20 입금 전·후)은 시점 고정 수치라 정본에서 뺐다. 규칙(정수 절삭은 유닛식에도 있다 · 유닛만 도입하면 전면 무매매 · 고칠 대상은 배분)은 정본과 strategies 「자금관리」 에 남는다.

### 자금 관리 — 그리고 이것은 자본 부족이 아니라 배분 문제다

```
  🔴 **그리고 이것은 자본 부족이 아니라 배분 문제다** — `q ≥ N` 을 요구하면 필요 비중 `w_i = N × P_i × m_i / A` 이고, N=5 에서 **Σ 필요 비중 = 0.97**(체결 있는 6전략, **입금 후 순자산 약 500만 기준**)이라 **입금 후 자본으로는 충분하다**(입금 전 250만 기준이면 Σ 1.94 로 불가능했다). 어긋난 것은 배분이다 — kojiro 는 0.40 을 쥐고 0.197 만 필요한데(랏이 10주라 정밀도가 남는다) VB 는 0.236 이 필요한데 0.05 뿐이다. ⚠️ `q` 계산의 분모는 **중앙 주가**이지 중앙 명목이 아니다(다주 랏이 섞이면 갈라진다 — VB 실측 주가 118,750 vs 명목 150,600)
```

사유: 필요 비중 `w_i = N × P_i × m_i / A` 와 Σ 0.97 / 1.94, VB 주가 118,750 vs 명목 150,600 은 입금 시점에 묶인 실측이라 정본에서 뺐다(메모리 `project_lot_geometry.md` 와도 같은 수치).

### 자금 관리 — 랏당 최대 유닛 상한 max_lot_units (K=2.0, cycle242)

```
- **랏당 최대 유닛 상한 `max_lot_units` (K=2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든** 매수 랏(터틀 유닛·`position_ratio` 낙하·1주 폴백)을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고, 그 값이 0 이면 **매수하지 않는다**. **매수를 줄이는 방향뿐**이다(캡은 `min()` 이라 수량을 늘리지 않는다) — 1주 폴백이 `risk_pct` 통제를 진입 시점에 무력화하던 과잉 피라미딩 시정이다. 캡 산출은 `turtle_sizing.compute_unit_qty(budget, atr, risk_pct, fraction=K)` **재사용**(새 수식 금지), ATR 은 터틀 분기와 **같은 소스** `_candidates[ticker]` 를 read-only 로 읽는다. K 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-242-1: 런타임 dict + 소스 리터럴 이중), 읽는 쪽 `[1.0, 20.0]` 클램프(**하한 1.0 = 정상 터틀 랏이 캡에 안 걸리는 수학적 전제**, 상한 20.0 = 롤백 다이얼). ATR 결측·모호(`atr`↔`atr14` 상이)·`risk_pct ≤ 0`·예외는 **fail-open**(현행 수량 유지 + `[fallback_cap_skipped]` WARNING) — fail-closed 는 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이라 금지. ⚠️ **"K유닛 = 예산 2.0% 노출" 은 `_entry_atr` 스탬프 랏(2×ATR 손절) 한정** — 폴백·PR 낙하 랏은 미스탬프라 고정% 손절을 타므로 실효 상한은 `cap_qty × price × |stop_loss_rate|` 다. **고정%손절 5전략**(momentum/VB/LTV + `position_ratio` 모드 VCP/BFB)은 **범위 밖**(position_ratio 가 이미 리스크 균등 — 유닛 캡을 씌우면 정규화 역전, 함정 #1). 피라미딩(사다리 증량)에서도 **K 는 2.0 을 유지하고, 1주 폴백으로 산 랏에는 사다리를 걸지 않는다**(설계안 `_workspace/design/2026-09-24_three_stage_sizing_pyramiding.md` D-2 — R15 재위반(8유닛)은 K=2 폴백 랏 위에 사다리를 얹을 때만 생기고, K→1.0 은 사다리와 무관하게 kojiro 진입 8%·donchian 진입 20% 를 없앤다). 사다리 전체의 위험 합계는 kojiro `max_open_risk_pct` 가 지킨다. 롤백 = 해당 전략 `max_lot_units = 20.0` — 코드 재배포는 불필요하지만 **반영 시점이 다르다**: `PUT /api/strategies/{id}/params` 는 **즉시**(라우트가 in-memory `config.params` 를 덮는다), `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만**(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회이고 `_boot` 재호출은 no-op) — cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **장중 실효 수단은 PUT 뿐**이다. **그리고 당일 캡→0 으로 `_bought_today` 가 소진된 종목은 어느 수단으로도 다음 세션부터만 되살아난다**(`cap_qty` 는 D-1 ATR 기반 일중 상수)
```

사유: K축의 시정 경위(「1주 폴백이 `risk_pct` 통제를 무력화하던 과잉 피라미딩 시정」)와 피라미딩 설계안 D-2 의 수치(R15 재위반 8유닛 · kojiro 진입 8% · donchian 진입 20%)는 경위·실측이라 정본에서 뺐다. 산출식 재사용(`turtle_sizing.compute_unit_qty(..., fraction=K)`) · ATR 소스 · 2.0% 노출 범위 · 피라미딩 제약 · `_config_loaded` · `_bought_today` 소진은 strategies 「자금관리」 K축이 정본이다.

### 자금 관리 — 랏 명목 ρ축 상한 max_lot_ratio_mult (K_ρ=2.5, cycle245)

```
- **랏 명목 ρ축 상한 `max_lot_ratio_mult` (K_ρ=2.5, cycle245)** — 관문을 지나는 **모든** 랏의 명목을 `K_ρ × position_ratio × 예산` 이하로 자르고, **1주도 못 사면 매수하지 않는다**. 1주 폴백 랏의 크기가 설계가 아니라 **그 종목 주가**로 결정되던 결함 시정이고, **매수를 줄이는 방향뿐**이다(`min` 이라 수량을 늘리지 않는다). 산식 = `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // 현재가`. **K축이 심사한 랏도 ρ축이 `min` 으로 후심사한다(cycle254)** — `_apply_ratio_notional_cap` 의 조기탈출은 판정 기준 `_lot_units_cap_governs`(= turtle ∧ ticker ∧ `risk_pct>0` ∧ 예산>0 ∧ ATR 해석 성공) **자체가 실패한 경우**(`probe_error`)만 fail-open 으로 남기고, 그 외엔 K축 심사 여부와 무관하게 컷오프를 적용한다. 사이즈드 터틀 랏·`position_ratio` 낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한(`min(qty, int(예산×position_ratio)//price)`)이 명목을 이미 컷오프 이하로 묶어 두므로 `final <= cap_qty` 로 **항등적으로 무접촉**이고, **실효는 1주 폴백 랏뿐**이다. `[ratio_cap_config]` 라벨은 `off|on` 2종이다. **키 부재 = OFF**(`max_lot_units` 관례와 **반대** — 매수를 막는 통제라 "설정이 없으면 막는다"는 유령 키 재현 경로다). 키는 **7 전략 전부**의 `DEFAULT_PARAMS` 에 명시하고 AST 가 glob 전수로 강제한다. K_ρ 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-245-1) + AI 자문 자동 적용 경로 편입 금지, 읽는 쪽 `[1.0, 20.0]` 클램프(**하한 1.0 = 정상 비중 랏이 캡에 안 걸리는 수학적 전제** — 1.0 미만은 주 분기까지 잘라 전면 무매매, 상한 20.0 = 롤백 다이얼). `position_ratio` 결측·예산 0·초소액·판정 예외는 전부 **fail-open**(현행 수량 + `[ratio_cap_skipped]` WARNING). 롤백 = 해당 전략 K_ρ=20.0 — **`PUT /api/strategies/{id}/params` 는 즉시, `strategy_config` SQL UPDATE 는 다음 백엔드 재시작에서만** 반영되므로 보유 중 장중 롤백은 PUT 이 유일 경로다(cycle232 D6)
```

사유: ρ축 산식(`cutoff`·`cap_qty`) · 조기탈출 판정기 `_lot_units_cap_governs`(`probe_error`) · 항등적 무접촉 이유 · `[ratio_cap_config]` 라벨은 strategies 「자금관리」 ρ축과 `src/engine/CLAUDE.md` `strategy_base.py` 절이 정본이다.

### 자금 관리 — 시장 유닛 market_unit_mode (cycle382, 사용자 결정 2026-09-27)

```
- **시장 유닛 `market_unit_mode` (cycle382, 사용자 결정 2026-09-27)** — 장세에 따라 터틀 4전략(`kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout`)의 **신규 진입 설계 랏만** 줄인다. 장세는 KODEX 200(`069500`) 일봉 종가의 **직전 영업일 봉**으로 정한다 — 60일선 위·60일선 상승 = **1** · 위·하락 = **0.75** · 아래·상승 = **0.5** · 아래·하락 = **0**(그날 신규 진입 없음). 상승 = 60일선이 20봉 전 60일선보다 높다. 동률은 약한 쪽으로 판정한다. 배수·창 길이는 leaf `src/engine/market_unit.py` 한 곳의 상수이고 파라미터로 열지 않는다. **무접촉** = `total_investment`·잔여 클램프·K축·ρ축·kojiro 오픈리스크 캡·`cash_usage_ratio`·보유분·청산 규약. 예산 경로(`cash_usage_ratio`·`total_investment` 축소)를 쓰지 않는 이유 = 7전략 전부와 일일 손실 분모·정산 기준선·비중 하한선 검증이 함께 흔들리고, 매크로 자동 조정과 같은 손잡이라 두 효과를 로그로 가를 수 없다(자문 `_workspace/domain_consult/cycle376_market_unit.md` §7.4). **축소일(`enforce` ∧ m<1)에는 1주 폴백도, 터틀→`position_ratio` 낙하도 없다**(원인 불문 — 낙하 랏은 `_entry_atr` 미스탬프라 고정% 손절을 탄다). 줄인 랏으로 못 사는 종목은 **신호 단계에서 `Signal.NONE`** 으로 거른다 — 수량 0 을 흘리면 `order_engine` 의 「매수 수량 0 → 900s cooldown (투자금: …)」 으로 오귀인된다. 잔여 부족(`funds`)은 거르지 않는다(기존 자금 경로가 맞는 귀인이다). 결측·stale·예외 = **m=1**(현행 그대로) + WARNING(`[market_unit_unavailable]`·`[market_unit_error]`) — 장세 데이터 결손이 매수를 조용히 줄이면 안 된다. 모드 `off|shadow|enforce` — 부재·오타 = `off`, 4전략 기본 = `shadow`(계산·기록만, 수량 불변). `PARAM_RANGES`/`INT_PARAMS`·AI 자문 자동 적용 경로 **편입 금지**(리스크 정체성 상수). 켜고 끄기 = 전략마다 `PUT /api/strategies/{id}/params {"params":{"market_unit_mode":"off"|"shadow"|"enforce"}}` — 모드를 매 호출 읽으므로 **즉시** 반영된다. 🔴 **매크로 레짐과 다른 축이다** — 레짐 게이트가 아니라 전략 사이징이다. 계산 자리·마커 = `src/engine/CLAUDE.md` `strategy_base.py` 절
```

사유: 장세 4단계 배수의 판정표(위·상승 1 / 위·하락 0.75 / 아래·상승 0.5 / 아래·하락 0) · 상승 정의 · 동률 처리 · leaf 상수 · 예산 경로를 쓰지 않는 이유 전체 · 자문 경로는 strategies 「시장 유닛」 절이 정본이다.

### 자금 관리 — cash_usage_ratio

```
- **`cash_usage_ratio`**: `system_config.cash_usage_ratio` 키 — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 `[0.0, 1.0]`, 5% 단위, 기본 1.0. Settings 슬라이더로 조정 → **다음 영업일부터 반영**. `auto_regime_adjust=true` (기본) + `DKSTOCK_REGIME_ENABLED=true` 시 매크로 레짐 `cash_min` 기반 자동 갱신 (`clamp((100-cash_min)/100, 0.0, 1.0)`)
```

사유: 코드 사실 정정: `auto_regime_adjust` 는 「기본 true」 가 아니다 — `src/db/system_config.py::get_auto_regime_adjust` 가 판독 불가(키 없음·value null·형식 오류·예외)를 전부 `_AUTO_REGIME_ADJUST_DEFAULT`(False, 수동 모드)로 돌려준다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 상세 메커니즘은 src/engine/CLAUDE.md · src/realtime/CLAUDE.md 참조

```
상세 메커니즘은 `src/engine/CLAUDE.md` · `src/realtime/CLAUDE.md` 참조. 여기서는 **금기**만:
```

사유: 머리말을 「항목마다 링크한 하위 절이 정본」 으로 바꿨다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 보유 포지션이 있는 전략을 끄지 않는다

```
- 🔴 **보유 포지션이 있는 전략을 끄지 않는다 — 끄는 순간 그 포지션의 손절이 멈춘다.** `risk.on_tick` 이 `registry.enabled()`(= `config.enabled` 참인 것만) **단일 순회**라, 끈 전략의 보유분은 손절·트레일링·익일청산·15:20 강제청산이 **전부 정지**하고 아무도 보지 않는 채 남는다(`src/engine/risk.py` 의 전략 순회 · `strategy_registry.enabled()`). 끄기 전에 **그 전략 보유 0 을 확인**하거나 먼저 청산한다. `enabled` 축 시정은 미착수이고 `src/engine/CLAUDE.md` 가 「의도적 미시정」으로 적어 둔 상태다. ⚠️ 「전략 수를 줄여 전략당 예산을 키운다」는 처방이 이 함정을 정면으로 밟는다. 두 용도를 구분한다 — **랏을 키우려면** `max_positions`(슬롯)를 줄이고 `position_ratio`(종목당 비율)를 올린다(`position_ratio × max_positions ≤ 1.0` 불변식 유지, **`weight` 는 무접촉**). 🔴 **보유한 채로 신규 매수만 멈추려면 `buy_paused` 를 쓴다(바로 아래 항목). `weight=0` 은 더 나쁘다** — `registry.update_weights` 가 **`config.enabled = weight > 0` 을 자동 토글**하므로 비중 0 = **즉시 비활성화 = 손절 정지**다(이 금기를 우회하는 길이 아니라 **금기 그 자체를 밟는 길**이다). 게다가 **`PUT /api/strategies/weights` 는 보유 매수금액 비율 미만의 비중을 거부한다**(`routes/strategies.py` 「매수금액 하한선 검증」 — "보유 종목 매도 후 비중을 줄여주세요"). 즉 금기가 겨냥한 바로 그 상황에서 도달 불가다. 끄는 길은 **그 전략 보유를 먼저 비우고** 끄는 것 하나뿐이다. **그 하한선 검증은 두 경로에 모두 있다**(cycle333) — `PUT /api/strategies/weights` 와 `POST /api/recommendations/{id}/apply`(AI 자문 적용). 자문 경로는 비중만 거부하고 파라미터 적용은 진행하며, 거부 사실을 응답 message 와 `[weight_zero_guard]` 에 남긴다. 둘 다 보유 조회 실패는 **fail-open**(판정 불가를 차단으로 바꾸면 적용 경로가 DB 가용성에 묶인다). ⚠️ 자문 경로가 특히 위험했던 이유 = 그 경로는 메모리 `config.weight` 만 바꾸고 `enabled` 는 안 건드려 **당일은 화면·로그가 정상**이고 다음 재시작에서야 발현한다 — 사고와 증상 사이에 재시작이 끼어 원인 추적이 끊긴다. 보유한 채로 신규 유입을 **줄이려면** **`position_ratio`·`max_positions`(PUT params — `enabled` 를 건드리지 않고 하한선 검증도 없다)** 를, **멈추려면** `buy_paused` 를 쓴다. `enabled` 축 시정과 함께 후속 대상
```

사유: 「자문 경로가 특히 위험했던 이유」 문단은 경위라 정본에서 뺐다(같은 내용 = `src/routes/CLAUDE.md` 「POST /api/recommendations/{id}/apply」 절). 코드 사실 정정: 「그 하한선 검증은 두 경로에 모두 있다(cycle333)」 는 틀렸다 — 두 경로에 다 있는 것은 **비중 0 가드**이고, 매수금액 하한선 검증은 `PUT /api/strategies/weights` 에만 있다(`src/routes/recommendations.py::_reject_zero_weight_if_held` · `src/routes/strategies.py::update_weights`).

### 핵심 안전 규칙 (절대 깨지 말 것) — 신규 매수만 멈추기 = buy_paused (cycle384

```
- 🔴 **신규 매수만 멈추기 = `buy_paused` (cycle384 — 사용자 결정 2026-09-27 「돈키언 신규매수 중지」)** — 7 전략 공통 `DEFAULT_PARAMS["buy_paused"]=False`. `PUT /api/strategies/{id}/params {"params":{"buy_paused":true}}` 로 켜면 그 전략의 **신규 매수 신호만** 멈춘다. 보유분의 손절·트레일링·익일청산·15:20 강제청산·종목상태 청산·시간 청산은 그대로 돈다 — 이 키를 읽는 곳이 `check_buy_signal` 안의 게이트뿐이다. 반영은 **즉시**다(게이트가 매 호출 `self.config.params` 를 읽는다). DB 에도 저장돼 재시작 뒤에도 유지된다. 막는 자리 = 공통 매수 게이트 `StrategyBase._account_soft_gate_blocked` 의 **둘째 문장**(첫 문장 = 종목상태 차단 AST J25 · 셋째 = 계좌 SOFT). 🔴 **신호 단계에서 막는다** — 수량 0 반환(900초 「투자금 부족」 오귀인) · `buy_disabled`(일일 손실 래치) · `enabled`·`weight`(손절 정지)로 대신하지 않는다. 🔴 **`is True` 일 때만 멈춘다** — 키 부재·`False`·문자열 `"true"`·`1` 같은 다른 모양은 **멈추지 않음** + WARNING. PUT 은 bool 이 아니면 422 다. 🔴 `PARAM_RANGES`/`INT_PARAMS` **편입 금지** — AI 자문(수동·자동 적용)이 켜고 끄면 안 된다(AST `test_cycle384_ast_buy_paused.py` A11). 🔴 **멈춰 둔 동안 코드에서 키를 지우지 않는다** — 키가 없는 코드가 배포되면 `_load_strategy_config` 가 DB 의 `true` 를 버려(`if key in strategy.config.params`) 조용히 풀린다. 상세 = `src/engine/CLAUDE.md` `strategy_base.py` 절
```

사유: `buy_paused` 의 막는 자리(첫 문장 = 종목상태 차단 AST J25 · 셋째 = 계좌 SOFT) 서술은 `src/engine/CLAUDE.md` `strategy_base.py` 절과 strategies 각주 ⑨ 가 정본이다. 금기 문장은 정본에 남는다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 체결통보 선행 race 가드 (_completed_orders set + UPDATE 0건 보정 INSERT

```
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존. 그 가드가 못 덮는 두 번째 창(PENDING `insert_trade` 의 `await` 도중 체결통보가 먼저 완주 → 보정 INSERT 가 같은 `(ticker, order_no, trade_type)` 를 선점 → migration 029 부분 UNIQUE 위반으로 `execute_buy` 가 ERROR 종료·`buy_succeeded` 후처리 누락)은 `_insert_pending_or_absorb_race(side=…)`(cycle271 매수 · cycle327 매도 확대)가 **`_completed_orders` 에 그 주문번호가 있을 때만** `UniqueViolationError` 를 흡수·discard 해서 막는다. 증거 없는 위반은 그대로 전파(다른 원인 은폐 금지) — 무조건 삼키기·`sizing`·재시도 INSERT 로 바꾸지 않는다
```

사유: 두 번째 창의 기전(보정 INSERT 가 키를 선점 → `execute_buy` ERROR 종료·`buy_succeeded` 후처리 누락)과 사이클 표기(cycle271 매수 · cycle327 매도 확대)는 `src/engine/CLAUDE.md` `order_engine.py` 절 체결통보 race 가드 ② 가 정본이다. 원문 열거의 `sizing` 은 정본(engine)에 없는 항목이라 옮기지 않았다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 주문이 나간 뒤의 실패로 재발사 금지 (cycle327·335)

```
- **주문이 나간 뒤의 실패로 재발사 금지 (cycle327·335)** — `place_order` 가 성공하면 그 주문은 이미 거래소에 있다. 그 뒤의 어떤 예외(UNIQUE 위반·DB 타임아웃·페일오버)도 **「발사 실패」가 아니므로** 재시도 루프로 되돌리지도, 발사 실패 정리 코드를 돌리지도 않는다. **매수·매도 4 경로가 전부 축별 경계 래퍼**(`_persist_buy_pending_after_send` · `_persist_sell_pending_after_send`)를 거치고, 각 래퍼가 자체 `try/except Exception` 으로 닫은 뒤 `[buy_post_send_error]`/`[sell_post_send_error]` 를 남기고 정상 종료한다. 매도는 재시도 직전에 `strategy.state.positions.get(ticker)` 를 **재조회**해 포지션이 사라졌으면 `[sell_position_gone]` 후 중단한다 — 루프 밖 지역 참조 `pos` 는 체결 뒤에도 옛 수량을 들고 있어 **이미 판 것을 다시 판다**(돌연변이 재현 3회 발사 — 경계를 `UniqueViolationError` 로 좁히자 `test_sell_does_not_refire_on_generic_insert_error` 가 시도 1/2/3 을 그대로 재현했다. 🔴 **운영 로그의 사고 기록이 아니다** — 매도 부분체결은 5개월간 0건이라 이 결함은 아직 실현되지 않았고, 그 사실이 시정을 미룰 근거는 아니다. 부분체결은 유동성이 얇아지는 순간에 몰린다). 매수는 **`pending_buys`/`pending_buy_amounts` 를 풀지 않는다** — 접수된 매수는 KIS 가 주문가능금액에서 이미 뺀 「묶인 자금」이고, 푸는 것은 **같은 종목 재매수 + 전략 예산 이중 사용 + 그 틱 청산 평가 소멸 + 900초 매수 락**을 동시에 연다(계좌 방어 `get_buyable` 은 전략 예산보다 훨씬 커서 이것을 못 막는다). 조용한 흡수 금지 — 두 마커가 유일한 관측 채널이고 **무cap ERROR** 다. 🔴 두 래퍼의 `except Exception` 을 **좁히지 않는다** — 좁히면 행위 회귀가 **거의 전부 초록인 채로** 샌다(매도 13/13 통과, 매수는 `UniqueViolationError` 케이스가 통과). 표본을 늘려도 같은 누락에 노출되므로 구조 가드 `test_cycle328_sell_pending_helper.py::test_g328_3b`(두 축)가 유일한 방어다. 피라미딩 착수 시 매도의 재조회가 수량의 유일한 진실원이 되고, 매수는 `pending_buy_amounts` 키를 `(ticker, order_no)` 로 바꾸는 것이 선결이다(지금은 `ticker` 단일 키라 같은 종목 두 번째 주문이 첫 번째를 덮는다)
```

사유: 「돌연변이 재현 3회 발사 … 운영 로그의 사고 기록이 아니다 … 5개월간 0건」 은 경위·실측이라 정본에서 뺐다. 묶인 자금을 풀었을 때의 나머지 비용(그 틱 청산 평가 소멸 · 900초 매수 락 · `get_buyable` 이 못 막는 이유)과 「매도 13/13 통과」 실측은 `src/engine/CLAUDE.md` 「접수 후 PENDING 영속화」 절이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 체결통보 주문수량은 3단 출처 (cycle329)

```
- **체결통보 주문수량은 3단 출처 (cycle329)** — `order_no` 는 KIS 응답이 와야 알 수 있어 `await place_order` 가 걸린 동안 주문번호 매핑 5종이 **전부 비어 있다**. 그 창에 착지한 통보는 `ordered_qty` 가 **증분 체결량으로 폴백**돼 `total_filled >= ordered_qty` 가 항상 참이 되고 **부분 체결이 전량으로 오판**된다 — 매수는 잔여 통보가 조용히 버려진 채 **영원히 적은 수량으로 믿는다**(15분 sync 도 기보유는 안 고친다). 매도는 주문 축만 틀리고 잔량은 보유 축이 지킨다(바로 아래 항목). 그래서 `map`(`_order_qty`) → `payload`(체결통보 `fields[16] ODER_QTY`) → `increment`(현행 폴백) 순으로 읽는다. 🔴 **전량 판정에 출처 게이트를 걸지 않는다**(걸면 수동 전량 매도가 유보돼 `_selling` 좀비 = 손절 마비) · 🔴 **재주문 타이머는 `qty_src=="map"` 일 때만**(`_cancel_and_reorder` 는 취소를 조건 없이 낸다 — 게이트가 없으면 **사람이 낸 주문을 30초 뒤 취소하고 다시 낸다**) · 🔴 **체결수량 소스 `fields[9]` 는 무접촉**(그 오독이 257720 사고, `test_cycle235_ast_execution_qty.py` 봉인). 매핑이 선 정상 통보마다 `[ordered_qty_mismatch]` 로 payload 를 교차검증한다. 상세 = `src/engine/CLAUDE.md` 「체결통보 주문수량」 절
```

사유: 매수·매도의 피해 양상과 `[ordered_qty_mismatch]` 교차검증은 `src/engine/CLAUDE.md` 「체결통보 주문수량 — 출처 3단」 절이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 매도 체결은 두 축으로 판정한다 (cycle385

```
- **매도 체결은 두 축으로 판정한다 (cycle385 — 사용자 결정 2026-09-26·27, 분할 매도 허용)** — `_handle_sell_fill` 의 **주문 축**(`total_filled >= ordered_qty`)은 장부·매핑·타이머·`_selling` 을 정하고, **보유 축**(`pos.quantity` 에서 체결량을 빼고 0 이 됐나)은 포지션 삭제·`delete_position`·`on_position_closed`·`sold_today`·구독 해제를 정한다. 보유보다 적은 매도(`manual-sell`·MTS·재주문 잔여)가 다 체결돼도 남은 보유는 추적에 남고 차감 수량이 `save_position` 으로 저장된다. 지키는 불변식 셋 = **추적 밖 실보유 0**(과소 추적 금지, 과대는 다음 APBK0400 이 회수) · **우리 주문 합 ≤ 추적 수량**(운영자가 따로 산 몫은 팔지 않는다) · **안 잠긴 추적 잔여는 팔 수 있어야 한다**. 🔴 **보유 축에도 출처 게이트를 걸지 않는다** · 🔴 **주문이 끝나면 `_selling` 을 푼다 — 어느 주문의 종료든, 보유가 남아도 푼다**(남기면 잔여 보유의 손절이 멈춘다). 해제에 조건을 달지 않는다 — 통보 앞쪽 `await` 전에 잡은 값(`qty_src`·보유자)으로 가르면 REST 응답이 통보 도중 착지할 때 표식이 남는다(AST AR2-1). 원주문을 취소했는데 우리 재주문이 확정적으로 안 걸렸을 때(발사 전 종료 · 「안 걸렸다」가 확정된 거부)와 동결이 지키던 보유가 닫혔을 때도 푼다. 🔴 **「안 걸렸다」는 `order_engine._sell_not_placed_reason(exc)` 한 곳이 가른다** — APBK0400 수량 초과(`is_sell_qty_exceeded`) · 장운영시간 외(`is_market_closed_rejection`) · 시장가 불가(`is_market_order_disallowed`)만이다. 뒤 둘은 같은 요청의 앞 전송도 똑같이 거부됐을 주문 자체의 거부라, 남기면 걸린 주문 없는 `_selling` 좀비가 된다(「NXT 매도 거부 좀비 차단」 과 같은 원리). 그 밖의 `KisApiError`(EGW00201 · 모르는 코드 · 보유 부족 문구)와 전송 예외는 「안 걸렸다」의 증거가 아니다 — `src/api/base.py::_request` 가 주문 POST 도 전송 오류·5xx 에 다시 보내므로 앞 전송이 접수됐을 수 있다(풀면 다음 틱이 그 위에 또 낸다). 분류는 msg1 문구 기반이라 문구가 키워드에 없으면 풀지 않는다. `manual-sell` 이 발사 실패에서 표식을 되돌리는 판정도 같은 함수다. `manual-sell` 이 `_selling` 을 발사 **앞**에서 세우는 것도 잔여 손절을 지키기 위해서다 · 🔴 **#1.5 재대조와 늦은 체결통보는 같은 체결을 두 번 빼지 않는다** — 재대조는 잔고(`get_balance`) **뒤에** 주문 목록(TTTC0081R, `exchange="ALL", pdno=ticker`, 2.0초 상한)을 읽어 「스냅샷에 이미 반영된 체결」을 주문별 크레딧으로 적고, 늦은 통보는 크레딧을 먼저 쓴 뒤 남은 만큼만 뺀다. 목록을 못 믿으면 종목 크레딧에 **더하고**(덮어쓰지 않는다) 재대조는 한다. 원장(`_sell_notice_seen`)은 메모리라 재시작하면 빈다 — 원장 시작 시각(`_sell_ledger_since`)보다 먼저 접수된 주문(TTTC0081R `ord_dt`+`ord_tmd`)은 「아직 안 온 통보」에 세지 않고, 그 크레딧에는 상한을 둔다. 기록된 두 시각의 비교라 벽시계 게이트가 아니고, 시각을 못 읽으면 뒤로 읽어 덜 쏜다 · 🔴 **외부 매도가 일부를 잠가도 안 잠긴 추적 잔여는 판다** — 아직 안 온 외부 체결 통보를 먼저 뺀 `eff` 로 `fire = sellable − (held − eff)` 를 잰다. 1 이상이면 그 수량만 내고(`pos.quantity` 무변경), 0 이하이거나 주문 목록을 못 믿으면 동결한다(운영자 몫을 팔지 않는다). 🔴 **걸린 매도가 없어도 보류한다**(명세 부록 R4 D1) — 원장 시작 뒤 주문의 미통보 체결이 추적 전부를 덮으면(`[sell_qty_unnoticed_fills]`) 계좌에 남은 것을 운영자 몫으로 보고 통보를 기다린다. 그 순간 주문 목록을 못 믿었으면 `[sell_qty_hold_orders_unavailable]` 로 보류한다. 푸는 주체는 그 주문의 종료 통보 · 보유 닫힘 · `selling_reconcile` 이다 · 🔴 **`execute_sell` 의 발사·매핑·PENDING 수량은 루프 상단에서 잡은 `send_qty` 하나다**(발사 뒤 `pos.quantity` 를 다시 읽으면 창 안 통보가 깎은 값이 적혀 유령 보유가 남는다. 부분 잠김 상한은 `min` 으로 줄이기만 한다) · 🔴 **소유 전략은 registry 전수 보유자로 찾는다**(`registry.get(sid)` 로 좁히면 `"momentum"` 기본값 함정). 장부 전략이 그 종목을 들고 있지 않은데 보유자가 2개 이상이면 보유 축은 어느 수량도 바꾸지 않는다 · 🔴 **손절 잔여 재주문은 발사 직전 보유를 다시 보고 `min(remaining, 보유)` 만 낸다** — 보유 0 이면 내지 않고 `_selling` 을 푼다. 재조회가 모호하거나 실패하면 `remaining` 그대로 낸다(손절 잔여를 버리는 쪽이 더 비싸다). 수동 매도 라우트 주문(`_manual_sell_orders` 표식)은 보유와 무관하게 `remaining` 을 낸다 — 운영자가 누른 수량이고, `strategy_id` 로 추론하지 않는다. ⚠️ 알려진 한계 — 무관한 주문(MTS·손님 수동 매도)의 종료도 `_selling` 을 풀어, 우리 손절 주문이 걸린 채 다음 틱이 한 번 더 낸다. 손님 수동 매도가 걸린 동안 교체된 재주문 타이머가 표식을 풀 때도 같다. 운영자 초과분 ≥ 추적 잔여이면 운영자 몫이 팔린다. 과대 추적도 운영자 초과분이 있으면 같은 결과로 번진다. `manual-sell` 이 발사 여부를 모르는 이유(EGW00201 · 전송 예외 등)로 실패하면 표식이 남아 그 종목 손절이 `selling_reconcile` 까지 멈춘다. 상세 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」 절
```

사유: 두 축 판정의 세부 조건·예외(`_sell_not_placed_reason` 분류 셋 · #1.5 재대조 크레딧 · 원장 시작 시각 · 부분 잠김 `fire` · 걸린 매도 없을 때 보류 · `send_qty` · 보유자 2개 이상 · `_manual_sell_orders` · 알려진 한계 목록)는 `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」 절이 정본이다(그 절에 전부 있음을 토큰 대조로 확인).

### 핵심 안전 규칙 (절대 깨지 말 것) — 관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단 (cycle369

```
- **관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단 (cycle369 — 사용자 결정 2026-09-25·26)** — leaf `src/engine/status_exit_watch.py` 가 보유 종목(꺼진 전략 포함)을 REST `FHKST01010100` 전용 플래그 `mang_issu_cls_code`·`short_over_yn` 으로 읽는다. KRX 정규장 **09:00:30~15:28** 안에서 전용 플래그가 `Y` 면 `execute_sell(t, Signal.STATUS_EXIT, sid)` 를 `asyncio.shield` 안에서 시장가로 낸다(종목당 하루 3회 — 재시작해도 `system_logs` 로 이어 센다). 🔴 창 밖 발사 금지 — 창은 발사 직전에 한 번 더 본다. 16:00~20:00 KRX 애프터마켓은 단기과열종목을 거래 대상에서 빼 거부·포기 래치가 난다. 🔴 **매도는 종목상태 코드 51·59 폴백만으로 쏘지 않는다** — 그 코드는 정상 ETF·스팩·우선주에도 붙는다(cycle203 실측). 폴백만 맞으면 `[status_exit_fallback_only]` 경고만 남긴다(매수 차단은 폴백도 쓴다). 🔴 판정에 `ssts_hot_yn`(공매도과열)·`short_over_cls_code`(예고)·`stock_master` DB 값을 쓰지 않는다. 휴장일로 확정된 날(수동 기동)은 조회·청산을 하지 않는다. 신규 매수는 공통 게이트 `StrategyBase._account_soft_gate_blocked` **첫 문장**이 그날 장중 조회 기준으로 막는다(지정 첫날 포함 · 순수 메모리 조회 · 못 읽으면 막지 않는다 · 수량 0 반환으로 막지 않는다). 🔴 **보유 종목 구독은 끊지 않는다** — 「재구독 중지」 를 글자대로 구현하면 청산 거부 시 손절이 눈을 감는다. 킬스위치 `system_config.status_exit_mode`·`status_buy_block_mode`(키 없음 = `enforce` · 모양이 틀린 행 = `observe` · DB 조회 실패 = 직전 값), 즉시 반영 = `PUT /api/integrations/status-exit` — 메모리를 DB 쓰기보다 **먼저** 바꾸고, 청산 패스는 발사 직전마다 모드를 다시 읽어 패스 도중의 `off` 도 뒤 종목부터 듣는다. DB 저장이 실패하면 그 축을 메모리에 고정해 refresh 가 되돌리지 못한다. ⚠️ 발사 창은 고정 시계라 특별 개장일(지연 개장)을 모른다 — 그날은 개장 전에 `sell_mode` 를 `off`/`observe` 로 내린다. 상세 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절
```

사유: 조회 TR(`FHKST01010100`) · `asyncio.shield` · 재시작 시드 · 휴장일 · 지정 첫날 · 킬스위치 3상태와 메모리 선반영·pin 세부는 `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — NXT 매도 거부 좀비 차단

```
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + `_selling` **discard** (진입 게이트 `SellRejectionTracker.is_blocked()` 가 이후 차단 담당 — `_selling` 을 보존하면 그게 곧 stale `_selling` 좀비=손절 마비이므로 반드시 해제) + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. `SellRejectionTracker.is_blocked()` 진입 게이트는 **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 4 필드 일괄 위임, `OrderEngine.reset_daily_state()` 캡슐화 보존). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 직접 노출 (is 동일성 보장)
```

사유: 코드 사실 정정: `_sell_rejection.reset_daily()` 는 4 필드가 아니라 5 필드를 비운다(`src/engine/sell_rejection.py::reset_daily` — `_alarm_last_emitted` 포함). 호환 layer property(`_market_closed_blocked` · `_market_closed_blocked_logged_today`, `is` 동일성)는 `src/engine/CLAUDE.md` `order_engine.py` 절이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 매수/매도 시장가 거부 → 지정가 5호가 폴백 1회

```
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
```

사유: msg1 키워드 나열(4개)은 코드의 키워드 목록과 개수가 다르다. 목록 정본 = `src/api/CLAUDE.md` 「KIS 거부 응답 분류 헬퍼」 절. 루트는 금기와 규약만 둔다.

### 핵심 안전 규칙 (절대 깨지 말 것) — WebSocket 다중 안전망

```
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s 주기, 1~5회 즉시 강제 재등록 + 6회 초과 시 10분 cooldown 기반 시간 기반 force_retry + 시간당 6회 cap) + `_resubscribe_stale_priority` (5분 우선) 4중. K stale watcher 양쪽 분기에 우선순위 분리 (positions/`_pending_next_day_clear` HIGH+bypass=True, 그 외 후보 LOW+bypass=False — 메인 편중 차단). `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
```

사유: K stale watcher 의 횟수·cooldown·cap 세부와 `_subscriptions` ACK 정합성 가드는 `src/engine/CLAUDE.md` `scheduler.py` 절과 `src/realtime/CLAUDE.md` 「안전 규칙 (멀티 세션)」 이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 세션 단위 silent inactive 자동 reconnect

```
- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드: `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단). **세션 상대 판정 (cycle241)** — 판정 가능 세션(`subscribed >= 5`)이 **2개 이상이고 그 전부**가 `fresh_ratio < 0.2` 이면 '세션 고장'이 아니라 **시장 침묵**(NXT 프리 마감·장후 동시호가·마감 흡수)으로 보고 그 사이클을 **기각 + 판정 가능 전 라벨 `first_seen` pop**(누적 후 필터 금지 — 시장 재개 순간 지각 세션이 즉발한다); 다른 세션이 하나라도 fresh 면 현행대로 발화(진짜 세션 결함 보존), 판정 가능 세션 < 2 면 현행 유지(fail-open) = 결과 집합 ⊆ 현행. 기각은 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` 로만 관측(30분 이상 지속 시 WARNING). **시장 침묵 기각에 시간창 리터럴(08:30/15:20)·`tradable_boards`·`session` import 를 쓰지 않는다** — 세션 간 비교만이 마감 흡수 구간의 갭까지 닫는다(AST G-241-5)
```

사유: 시장 침묵 기각의 fail-open 조건(판정 가능 세션 < 2 · 하나라도 fresh)과 관측 `transition=entered|persisting|exited`(30분 이상 지속 WARNING)는 `src/engine/CLAUDE.md` 모듈 맵 `stale_session_recovery.py` · `scheduler.py` 절이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 무송출(no_feed) 종목은 K stale watcher 가 재등록하지 않는다 (cycle252)

```
- **무송출(no_feed) 종목은 K stale watcher 가 재등록하지 않는다 (cycle252)** — SUBSCRIBE 가 SUCCESS ACK 를 받아도 체결 프레임이 영구 0 인 종목이 있어, 재등록은 회복 가치 0 이고 SEND 만 하루 ≈14,600 을 만든다. `stale_watcher_core.check_and_resubscribe_stale` 은 `no_feed_registry`(`stock_master` 조회, 600s TTL, **fail-open** = 집합 ∅·조회 예외·미지 ticker 면 현행 byte 동일)로 **LOW no_feed 종목의 SEND·`_stale_last_resubscribe_at` 스탬프·force_retry history 만** 건너뛴다. **HIGH(보유·익일청산) 경로는 byte 동일** — 가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 손절 커버리지이기 때문이다. 대신 `[no_feed_held]` WARNING 1회/일이 "보유 종목이 WS blind, 손절은 REST 폴만" 을 남긴다. `_stale_retry_count` 는 계속 증가(r>5 홀드)해 `stale_universe_guard` 의 저유동 축출 경로를 보존한다. 근본 시정인 채널 리졸버(cycle293 속성축 → cycle294 시간축 = 통합 채널 소멸)가 착지한 지금은 `[no_feed_held]` 와 `[stale_watcher_summary] no_feed_skipped=` 가 **0 에 수렴하는 것이 정상**이다 — 상세 = `src/realtime/CLAUDE.md` 「시세 채널」 절, 킬스위치 = `PUT /api/realtime/tick-channel-mode`. ⚠️ 이 두 마커와 `[tick_coverage] stale` 의 의미는 2026-09-14 배포로 뒤집혔다 — **그 전후 로그를 합산하지 않는다**. 5분 `resubscribe_stale_priority` 는 무접촉(후보 소스 `ticker_last_tick` 에 no_feed 종목은 프레임 0 이라 애초에 없다). 금기 = no_feed 를 stale 집계에서 **빼서** 숫자를 좋게 만드는 것, HIGH 를 skip 에 넣는 것, 관측 헬퍼가 예외를 전파해 HIGH 재등록 사이클을 끊는 것
```

사유: 하루 SEND ≈14,600 은 실측이라 정본에서 뺐다. 600s TTL · `_stale_retry_count` r>5 홀드 이유 · 5분 `resubscribe_stale_priority` 무접촉 이유 · 채널 리졸버 착지 후 0 수렴은 `src/engine/CLAUDE.md` 모듈 맵 `stale_watcher_core.py`·`no_feed_registry.py` 와 `src/realtime/CLAUDE.md` 「시세 채널」 이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 전제

```
- 🔴 **전제 — 넥스트트레이드(NXT)에서 거래되는 종목은 전부 KRX 상장 종목이다.** NXT 는 대체거래소(ATS)라 **자체 상장이 없다**. 그래서 `nxt_tradable` 은 「이 종목이 어디에 상장돼 있나」가 **아니라** 「KRX **에 더해** NXT 에서도 거래되나」다(정의 = `cptt_trad_tr_psbl_yn=="Y" ∧ nxt_tr_stop_yn=="N"`, `api/condition.py:451`). 따라서 `nxt_tradable=False` 는 **「KRX 전용」**이지 「어디서도 못 산다」가 아니고, 그 종목도 09:00~20:00 KRX 정규장·애프터에서 정상 매매된다(마스터의 **83.2%** 가 이 코호트다). 「NXT 미상장」·「NXT 에만 있는 종목」 같은 말은 쓰지 않는다 — 실재하지 않는 상태다.
```

사유: 마스터의 83.2% 가 `nxt_false` 코호트라는 수치는 실측이라 정본에서 뺐다. 코드 사실 정정: 파생 위치 `api/condition.py:451` 은 줄번호가 표류했다(실제 파생 = `inquire_stock_basics` 안 458행) — 함수명으로 바꿨다.

### 핵심 안전 규칙 (절대 깨지 말 것) — NXT 시세 채널은 프리장(08:00~09:00) 전용이다

```
- **NXT 시세 채널은 프리장(08:00~09:00) 전용이다** — `scanner._resolve_channel` 은 **시각축 × 속성축** 합성인데, 시각축(`tick_channel_clock.clock_channel`)이 KRX 창을 돌려주면 **속성축을 아예 호출하지 않는다**(`scanner.py:690` 조기 반환). 즉 **09:00~20:00 은 `nxt_tradable` 과 무관하게 전 종목이 `H0STCNT0`** 이고, `nxt_tradable` 이 채널을 가르는 구간은 프리 창 하나뿐이다. 전환은 하루 **1회**(`pre_to_krx`). 프리 창에서 `nxt_false` 를 KRX 채널에 두는 근거는 커버리지가 아니라 **전환 횟수**다 — 그 종목은 그 시간 NXT 미거래 + KRX 시가 단일가라 어느 채널이든 연속체결 프레임이 없고, KRX 에 두면 09:00 첫 체결을 **전환 없이** 받는다(전환 폭 ~40% 감소). 걷으면 프리 창 KRX 프레임(K2 08:30~08:40 장전 시간외 **종가**, 전일 종가 고정)과 그 감소분을 잃고 **그뿐이다** — 정규장 시세·매수 평가에는 닿지 않는다.
```

사유: 코드 사실 정정: `scanner.py:690` 조기 반환 인용은 줄번호가 표류했다(`_resolve_channel` 정의 653행, KRX 분기 688행) — 함수명으로 바꿨다. 프리 창 `nxt_false` 를 KRX 채널에 두는 근거(전환 횟수)와 K2 08:30~08:40 종가 프레임은 `src/engine/CLAUDE.md` 「시세 채널 (통합 채널 소멸 후)」 이 정본이다. 「전환 폭 ~40% 감소」 는 실측이라 옮기지 않았다.

### 핵심 안전 규칙 (절대 깨지 말 것) — nxt_tradable 은 「어느 거래소로 보낼까」 에만 쓴다

```
- **`nxt_tradable` 은 「어느 거래소로 보낼까」 에만 쓴다 — 「살까 말까」 에는 쓰지 않는다 (사이클 156 Q0 · cycle336 원복)** — 5 전략이 전부 `list_by_filter(nxt_tradable=None)` 로 후보를 뽑고(`strategies/volatility_breakout.py:450` · `long_tail_volatility.py:501` · `bull_flag_breakout.py:709` 주석이 근거), `risk.on_tick` 의 매수 평가에도 코호트 게이트가 **없다**. cycle293 이 `if chan_buy_blocked: continue` 로 그 기준을 다른 계층에서 되살렸던 것을 cycle336 이 걷었다 — 실측 구독 158 중 **77(49%)** 이 매수 평가에서 빠져 있었다. **되살리지 마라.** 🔴 반대로 **남겨야 하는 세 배선**은 전부 주문·청산 쪽이고, 걷었을 때의 대가가 서로 다르다: ① `order_engine._probe_nxt_downgrade_base`(NXT **거래대상이 아닌** 종목에 NXT 주문 = 거부, 게다가 **KRX 애프터 44/41 청산 변환의 전제**다) ② `scheduler` 익일청산 KRX 예약(걷으면 08:00 프리장 NXT 시장가가 `APBK0918` 거부 → 다음 09:00 TTL 로 그날 청산이 잠긴다) ③ 프리장 시세 채널 선택(걷으면 **프리 창 한 시간의 KRX 프레임만** 잃는다 — 위 절. ①②와 달리 청산이 깨지지 않고, 그 창의 유일한 청산 소비자는 LTV 다). 판정 함수 `_tick_buy_eval_blocked_by_channel` 는 계측기로 남아 `[tick_buy_gate]` 분모와 `_note_pre_window_krx_frame` 게이팅에 쓰인다
```

사유: 「실측 구독 158 중 77(49%)」 는 실측이라 정본에서 뺐다. 전략 파일 줄번호 인용(`volatility_breakout.py:450` 등)은 표류 위험이 있어 strategies 「prepare 공통」 링크로 바꿨다.

### 핵심 안전 규칙 (절대 깨지 말 것) — stale universe 가드

```
- **stale universe 가드** — `_evaluate_universe_guard`: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO + `inquire_ccnl` 으로 마지막 체결시각 로그. 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)
```

사유: `inquire_ccnl` 마지막 체결시각 로그는 `src/engine/CLAUDE.md` `scheduler.py` 절 `_evaluate_universe_guard` 가 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — trade_history 중복 INSERT 차단

```
- **`trade_history` 중복 INSERT 차단** — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()` 사용 (dedupe 없음 + CANCELLED 제외). DB 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)` 이중 안전망. 기존 `get_today_buy_trades()` 의 ticker dedupe 는 포지션 복구용 — 절대 sync 중복 판정에 사용 금지
```

사유: 이유 한 구절(핑퐁 INSERT)을 `src/db/CLAUDE.md` 「trade_history.py」 절에서 가져와 덧붙였다. 원문 조건은 그대로다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 종목코드 형식 비대칭

```
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — 영숫자 코드(신주인수권 등)·7자리 ETN 코드 자동매매 차단 + 좀비 포지션 방지. 🔴 **이 규칙은 ETF 를 막지 못한다** — ETF 코드도 6자리 숫자다(`stock_master` 3,583행 전부 6자리 숫자, 2026-09-27 조회). ETF/ETN 매수 제외는 `src/engine/etf_like.py::is_etf_like` 가 맡는다 — 증권그룹코드 `scty_grp_id_cd ∈ {EF,EN,FE}` 우선, 코드가 없을 때만 이름 키워드 폴백(cycle380). 규약 = `src/engine/CLAUDE.md` 모듈 맵 `etf_like.py`
```

사유: 「stock_master 3,583행 전부 6자리 숫자, 2026-09-27 조회」 는 실측이라 정본에서 뺐다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 매수 수량은 전략 잔여 자금 기준

```
- **매수 수량은 전략 잔여 자금 기준** — 7 전략 `calc_buy_quantity()` 의 **모든 return** 이 `StrategyBase._apply_budget_limit()` 관문을 경유한다 (AST 가드 A-GATE). 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`. 비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — **이 분기 순서가 계약이다**. 터틀 4전략 `calc_buy_quantity` 첫머리의 시장 유닛 분기(cycle382)는 관문 **앞**에서 `0` 을 돌려주거나 줄인 설계 랏(`> 0`)을 관문에 넘길 뿐이라 관문 본문·순서는 그대로다 — 축소일에 관문의 폴백 분기는 도달 불가다. 관문 **안의 순서도 계약이다**: 폴백·잔여 클램프 → `_apply_lot_units_cap`(K축, cycle242) → `[oversized_fallback]` 관측 → `_apply_ratio_notional_cap`(ρ축, cycle245) → `return`. ρ축을 관측 **앞**에 두면 차단된 랏의 ρ 관측이 `final_qty < 1` 로 통째로 사라지고, K축 **앞**에 두면 조기탈출로 cycle242 마커 3종이 사라진다. 관문 안에서 `await`/DB/HTTP **절대 금지**(AST A-PURE — 두 사이클의 신규 헬퍼 14개 전부에 적용: G-242-2/G-242-10 · G-245-2) — `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(AST 가드 A-ATOMIC)이 원자성의 전제이고, 이게 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다. 관측 emit 3종은 전부 예외를 흡수하고 **행위는 cap 밖**이다(관측 실패가 매수 수량을 바꾸면 안 된다). K축 캡 ATR 은 사이징과 **같은** `_candidates[ticker]` 를 read-only 로 읽고 `("atr","atr14")` 두 키가 서로 다른 값이면 **불채택**(fail-open) — `_candidates` 를 생성·변경하지 않는다(AST G-242-8). 캡 스코프는 폴백 랏이 아니라 **관문을 지나는 모든 랏**이고, 관문 반환 타입은 **`int`** 여야 한다(float 이면 `api/order.py` 가 `ORD_QTY="2.0"` 을 KIS 로 보낸다 — G-245 회귀가 봉인)
```

사유: 신규 헬퍼 A-PURE 가드 이름(G-242-2 · G-242-10 · G-245-2) · K축 ATR read-only(G-242-8, `("atr","atr14")` 불채택) · 관측 emit 3종 · `int` 반환 회귀(G-245)의 세부는 `src/engine/CLAUDE.md` `strategy_base.py` 절이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 터틀 ATR 손절 게이트는 _entry_atr 스탬프 존재

```
- **터틀 ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 로 게이팅 금지. DB 토글 하나로 **기보유 포지션의 손절 규약**이 바뀌면 안 된다. position_ratio 매수는 미스탬프라 기존 % 손절 경로를 byte 동일하게 탄다. 스탬프 값은 반드시 sizing 에 쓴 ATR 과 동일(커플링 불변식). 이 금기는 **청산** 규약이다 — 진입 사이징(`calc_buy_quantity`·`max_lot_units` 캡)이 `sizing_mode` 로 분기하는 것은 충돌이 아니다. **재시작 복구의 재도출(`_rederive_entry_atr`)은 그 전략이 지금 `sizing_mode="turtle"` 일 때만 한다**(`StrategyBase._entry_atr_rederive_allowed`, cycle355 — donchian·BFB·VCP 세 호출부 전부, AST 가드 G6) — position_ratio 랏은 처음부터 스탬프가 없어 되살릴 것이 없고, 되살리면 다음 날 아침부터 고정% 손절이 ATR 손절+% 받침선으로 넓어진다(2026-09-23 BFB 100840 −5% 규약인데 −7.1% 매도). ⚠️ 랏별 사이징 기록이 없어 **보유 중 `sizing_mode` 를 바꾸면 기보유분이 새 설정의 손절을 탄다**(position_ratio→turtle 은 다음 아침 부팅부터, turtle→position_ratio 는 다음 재시작부터) — 전환은 그 전략 보유 0 에서 한다
```

사유: 「cycle355 — donchian·BFB·VCP 세 호출부 전부」 와 「2026-09-23 BFB 100840 −5% 규약인데 −7.1% 매도」 는 경위·실측이라 정본에서 뺐다. 전환 시점(position_ratio→turtle 은 다음 아침 부팅부터 · turtle→position_ratio 는 다음 재시작부터)은 strategies 「자금관리」 ATR 손절 게이트가 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — tradable_boards 는 매수 진입 전용 (명문화)

```
- **`tradable_boards` 는 매수 진입 전용 (명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동. **유일한 예외 = NXT 프리장(08:00~09:00) 청산 평가 보류 게이트**(2026-08-06 사용자 결정, `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 화이트리스트 = LTV 만) — 프리장 왜곡 틱(전일 상한가 종목 시초가 하한가 형성 등)의 허깨비 손절·트레일링 고점 오염을 차단하고 09:00 KRX 시세로 재평가한다. **평가 보류이지 주문 보류가 아니다**(주문만 보류하면 허깨비 신호가 09:00 실매도로 전환). 게이트는 `tradable_boards` 가 아니라 **명시 상수**로 판정(AST 가드) — 매수 목적 보드 변경이 청산 규약을 바꾸는 커플링 차단. 매도 시장가는 `execute_sell` 이 프리장 단독 구간에서 `step_down(현재가,5)` 지정가로 사전 변환(매수 PR-F 대칭, 실효 대상 LTV). `risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입. LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")` (사용자 의도 — 연속 상한가 익일 청산 + 야간 매수)
```

사유: 「전일 상한가 종목 시초가 하한가 형성 등」 예시와 프리장 매도 시장가의 `step_down(현재가,5)` 사전 변환(매수 PR-F 대칭, 실효 대상 LTV)은 `src/engine/CLAUDE.md` 「risk.py」·「order_engine.py」 절이 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — VB·LTV main 목표가 기준가 = KRX REST 단일 출처 (cycle272

```
- **VB·LTV `main` 목표가 기준가 = KRX REST 단일 출처 (cycle272 — 사용자 결정 D1)** — `board=="main"` 목표가는 WS 세션 시가(KRX 확정 시가와 어긋난다) 대신 **KRX REST `stck_oprc`(`J`) 만** 기준가로 삼는다. 좁은 목 `on_open_price_confirmed(..., board="main", *, source="ws")` — `source` 신뢰 목록은 `("rest",)` 뿐이고 기본값이 불신 `"ws"` 라 WS 확정 경로는 조용히 거부된다. 킬스위치 `open_price_scope_mode`(전략별 `DEFAULT_PARAMS`, 기본 `"enforce"`, `"off"` 만 롤백 — `PARAM_RANGES`/`INT_PARAMS` 편입 금지). REST 확보는 leaf `src/engine/open_price_rest.py`(09:00:35 부터 30초 간격 **19라운드**(마지막 09:09:35) → 5분 간격 15:20 까지, 프린트 안 된 종목은 그 시점 매수 불가). `pre_nxt`/`post_nxt` 보드는 게이트 스코프 밖 — LTV 08:00~09:00 프리장·야간 매수 무접촉. 상세 = `src/engine/strategies/CLAUDE.md`
```

사유: REST 확보 일정(09:00:35 부터 30초 간격 19라운드 → 5분 간격 15:20 까지)은 `src/engine/CLAUDE.md` 모듈 맵 `open_price_rest.py` 가 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 모든 시각 데이터 KST 강제

```
- **모든 시각 데이터 KST 강제** — 백엔드 `_to_kst(iso)` 헬퍼 + `_today_kst_iso()` timezone 명시 (`+09:00`). 프론트 `Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시. `new Date(iso).getHours()` 브라우저 로컬타임 추출 금지
```

사유: 코드 사실 정정: 프론트 규칙은 「`Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시」 가 아니라 「`src/utils/kst.ts` 위임, 새 `Intl.DateTimeFormat` 생성 금지」 다(`frontend/CLAUDE.md` 「시각적 컨벤션」 · K4 가드).

### 코딩 컨벤션 — KIS 호출은 반드시 src/api/base.py::kis_request() 또는 kis_get_quote(

```
- KIS 호출은 반드시 `src/api/base.py::kis_request()` 또는 `kis_get_quote()` 경유 (Rate Limit·재시도·메트릭)
```

사유: 코드 사실 정정: `src/api/base.py::kis_request()` 라는 함수는 없다 — 메인 진입점은 `kis_get()`·`kis_post()`, 시세 풀은 `kis_get_quote()`·`kis_post_quote()` 다.

### 코딩 컨벤션 — TR_ID 는 settings.get_tr_id() 사용

```
- TR_ID 는 `settings.get_tr_id()` 사용 — 하드코딩 금지
```

사유: 코드 사실 정정: TR_ID 는 실전 값을 넘기고, 모의 변환은 `TokenManager.build_headers` 가 `settings.get_tr_id()` 를 모든 요청 헤더에 적용한다(`src/api/CLAUDE.md` 「새 API 추가 절차」 3번).

### DB 스키마 (AWS RDS PostgreSQL) — 마이그레이션

```
마이그레이션: `supabase/migrations/`. CRUD 모듈 상세: `src/db/CLAUDE.md`. (마이그레이션 디렉토리명은 supabase/ 유지 — 스키마 SQL 정본, RDS 에 순차 적용)
| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적, 실현손익 기준) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 (auto_start, cash_usage_ratio, buy_block_mode + 4 임계값, dkstock_regime_enabled, kis_mcp_enabled 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 20:00 AI자문 (target_date+strategy_id UNIQUE). `recommended_weight`/`code_review_notes`/`applied_weight`/`weight_reasoning`/`backtest_summary` JSONB |
| `daily_log_reports` | **21:30** 일일 로그 분석(cycle283 D3) + **20:05 metrics 1차 스냅샷**(같은 행을 upsert) (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함). 토큰/지연/비용 5 컬럼 — input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd (migration 031, 모두 NULL 허용) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + `master_raw` JSONB + `master_raw_updated_at TIMESTAMPTZ` (KIS 공식 일일 마스터 파일 영역 — 시총/거래정지/관리종목/지수편입/재무 ~30 키, raw 영역 분리 보호). NXT 거래가능 사전 판별. 생성 컬럼 `hts_avls_eok bigint`(억원) + `acml_tr_pbmn_won bigint`(원) GENERATED ALWAYS STORED (migration 039 — raw 의 `hts_avls`/`acml_tr_pbmn` 이 jsonb **문자열**이라 UI 의 jsonb numeric 비교가 0건으로 조용히 실패했다. 비숫자는 `~ '^[0-9]+$'` 가드로 NULL). **raw 는 읽기만 한다**(AST G-AST1 영속) |
| `stock_master_daily` | KIS FHKST03010100 일봉 정규화 (migration 033). PK `(ticker, bas_dd)` + OHLCV + change_rate + raw JSONB. **매일 20:30 KST 적재**(`TIME_STOCK_MASTER_DAILY_LOAD`) — 백필 시 T-100일, 이후 D-1 영업일 증분. 🔴 **20:30 에 쓴 그날 봉의 종가·고가·저가는 잠정이다** — KIS 가 그 시각엔 애프터마켓 마지막 체결가·애프터 포함 고저를 주고, D+1 새벽에 정규장 값으로 바꾼다. 다음 거래일 아침 부팅이 prepare 직전에 `daily_bar_finalize` 로 확정한다(cycle386 — 잠정 판정은 `updated_at` 하나, 규약 = `src/db/CLAUDE.md` · 흐름 = `src/engine/CLAUDE.md` 「저녁 데이터 적재」). **일봉 적재 대상 전부**(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호) backfill target **225일**(cycle302 가 대상을 지수에서 전체로 넓혔다 — 비지수 1,526 종목의 225행 도달률이 0% 였다. 첫 채움만 종목당 3콜이고 수렴 후에는 증분 1콜이다. cycle299 — `effective_ema_long = min(ema_long, 보유 − 20 − 5)` 라 보유 225 에서 실효 장기선이 정확히 **200** 이 된다) · retention `DAILY_RETENTION_DAYS=390`(390 캘린더일 ≈ 261 영업일이라 target 위로 36 영업일 마진. 두 값은 함께 움직인다 — target 이 보유 영업일을 넘으면 무한 재backfill churn). donchian(20일 신고가) / VCP(베이스+Pullback, 읽기 깊이는 전략 파라미터 `daily_fetch_depth_mode` — 기본 `"cap100"`=100봉 / `"full"`=`ema_long+base_max+10`, cycle300) / VB(노이즈비율 K·전일 Range — **ATR 아님**) 전략 활용. 읽기 관문 상한 = `get_recent_daily` 의 `_MAX_DAILY_ROWS=400` |
| `stock_master_financial` | KIS 재무 5 TR 정규화 (migration 041, 사이클 C1). PK `(ticker, stac_yymm, div_cls)` (div_cls 0=년/1=분기) + 18 NUMERIC 컬럼(손익 5/대차 7/수익성 2/안정성 2/기타 2) + raw JSONB + refreshed_at. 마법공식(EV/EBITDA·ROC) + F-Score-7 원천 데이터. 주1회 16:40 적재. 매매 hot path 무관 |
| `llm_buy_evaluations` | **cycle276** AI 매수평가(LLM shadow)를 주문 발화 시점에 기록 (migration 043). PK `(trade_date, account_no, ticker, order_no)` + 53열 — 점수/임계/`would_block`·사유·핵심위험·무효화조건 · 주문 스냅샷(주문가·수량·구분·경로·거래소·보드) · 모델/토큰/비용/지연 3종 · 회고 층화 `prompt_version`/`feature_version` · 주문 시점 제약 `budget_total_won`/`budget_remaining_after_won`/`open_positions_n` · `input_payload` JSONB(`build_messages` 3인자 전체 = 오프라인 재채점의 다리) · `raw_response` JSONB(파싱 전 원문). **주문 1건 = 1행(성공·실패 모두)**, 실패 행도 payload 를 담고 `score=NULL`. 조인 = `order_no`→`trade_history` 체결(`(trade_date, ticker, order_no)` 3축) · `buy_order_nos`→`get_trade_pairs` 실현손익. 인덱스 4 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE. 활성 전략마다 2 row/자문(`params_kind` = current|recommended)) |
| `market_regime_snapshots` | 매크로 레짐 일일 스냅샷(출처 = 우리 `macro` 컨테이너). `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). `list_accounts()` 60s TTL 메모리 캐시 |
| `strategy_funnel_snapshots` | 전략별 조건검색 단계별 후보/탈락 종목 영구 추적. `(target_date, strategy_id, step_no)` UNIQUE(migration 035) — 같은 키는 UPSERT 로 1행만 남는다(`snapshot_at` 의 뜻 = `src/db/CLAUDE.md` `strategy_funnel.py` 절). `survived_tickers` JSONB cap 200 / `excluded_sample` JSONB cap 20. 09:30 자동 캡처(`scheduler._auto_capture_funnel_snapshots`, 단계별 + `step_no=99`) + 수동 trigger `POST /api/strategy-funnel/snapshot`(`capture_funnel_snapshots(registry, is_provisional=False)`) + 21:00 저녁 미리보기(`is_provisional=TRUE`, `target_date` = 다음 거래일). 잠정 쓰기는 확정 행을 덮지 못한다(`src/db/CLAUDE.md` `strategy_funnel.py` 절) |
```

사유: DB 표는 「테이블명 + 용도 한 줄」 로 줄였다. 원문 행의 상세(컬럼·인덱스·적재 시각·cap·53열 서술·잠정 종가 판정 규약)는 `src/db/CLAUDE.md` 모듈 절과 `src/engine/CLAUDE.md` 「저녁 데이터 적재」 가 정본이다. 「20:30 에 쓴 그날 봉 종가는 잠정」 한 문장은 매매 판단 함정이라 정본에 남겼다. 누락 보강: `pending_next_day_clear`(migration 038) · `stock_master_history`(migration 032·036) 두 테이블이 표에 없었다(`supabase/migrations` `CREATE TABLE` 18종 대조).

### DB 스키마 (AWS RDS PostgreSQL) — trade_history 부분 UNIQUE 인덱스 (migration 029)

```
> **`trade_history` 부분 UNIQUE 인덱스 (migration 029)**: `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. `_sync_orders_to_db` 핑퐁 INSERT 영구 차단 + NULL/빈 order_no (수동 매매 사전 등) 호환.
```

사유: `trade_history` 부분 UNIQUE 인덱스(migration 029) 인용 블록은 `src/db/CLAUDE.md` 「trade_history.py」 절이 정본이다.

### DB 스키마 (AWS RDS PostgreSQL) — stock_master / stock_master_daily UI 동기화 의무

```
> **`stock_master` / `stock_master_daily` UI 동기화 의무**: stock_master 컬럼 / raw JSONB 키 / stock_master_daily 컬럼 추가 시 UI 동기화 의무 영속. 전략에서 종목마스터 데이터 참고 시점 영역부터 신규 수집 데이터는 UI 노출 의무. 절차 = (1) `frontend/src/types/stock-master.ts` interface 갱신 (2) `frontend/src/api/stock-master.ts` 호출 영역 갱신 (3) `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 한글 라벨 + `CATEGORY_KEYS` 배치 + `HIGHLIGHT_KEYS` 핵심 키 추가 (4) `GET /api/stock-master/stats` 응답에 진단 카운트 추가 + 카드 1개 추가 (5) `frontend/src/test/handlers.ts` MSW + `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합 갱신 (6) 회귀 가드 추가. 상세는 `frontend/CLAUDE.md` 참조.
```

사유: UI 동기화 6단계는 `frontend/CLAUDE.md` 「(6) 신규 데이터 추가 시 UI 동기화 절차 (영구 가드)」 가 정본이다(8단계로 더 세분돼 있다).

### Docker / 배포 — 타임존 TZ=Asia/Seoul, vite 프록시 타겟은 VITE_API_URL 분기

```
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
```

사유: vite 프록시 타겟 분기의 정본 = `frontend/CLAUDE.md` 「실행」 절.

### Docker / 배포 — 배포 모드 함정 넷

```
- ⚠️ 배포 모드 함정 넷: (a) `**.md`·`docs/**`·`_workspace/**` 만 바꾼 push 는 CI `paths-ignore` 로 **CI/Deploy 자체가 뜨지 않는다**(마커는 다음 배포의 누적 diff 가 따라잡는다) (b) `src/**` 는 이미지 입력이지만 **`src/` 안 `.md` 는 예외다** — `IMAGE_EXCLUDED_RE='^src/.*\.md$'`(`tools/deploy/compose_up_changed.sh:140`)가 backend 히트에서 2단으로 덜어내므로(`:217` `grep -vE`) **`src/engine/CLAUDE.md` 만 바꾼 push 는 full 이 아니다**. 두 파일이 갈라지지 않게 `tests/unit/ast/test_cycle322_image_excluded_paths.py` 가 묶는다. 🔴 `.*\.md$` 로 넓히지 않는다 — `tools/deploy/` 축이 흔들린다 (c) `.env` 는 git 밖이라 스크립트가 못 본다 — 손댄 뒤에는 운영자가 `docker compose up -d` 로 직접 재생성하고 **마커는 건드리지 않는다**(마커는 git SHA 의 배포 상태만 뜻한다) (d) none 모드의 `up -d` 도 `.env` 등 구성이 어긋나 있으면 재생성한다(none ≠ 무조건 무재시작)
```

사유: `compose_up_changed.sh:140` · `:217` 줄번호 인용을 심볼(`IMAGE_EXCLUDED_RE` · `grep -vE`) 인용으로 바꿨다(줄번호는 표류한다).

### Docker / 배포 — TLS

```
- **TLS — `auto.dkstock.cloud` 2단계 가동 중**(1단계 2026-09-05 · 2단계 09-08). 80 은 **301** 로 https 로 보내고, 443 은 Basic Auth + HSTS `max-age=86400`(includeSubDomains·preload 없음). ACME HTTP-01 챌린지 location(`^~ /.well-known/acme-challenge/`, `satisfy any; allow all; root /var/www/certbot;`)만 301 밖이다. 스위치는 호스트 마커 파일 2개(git 밖) — `.tls_enabled`(1단계 = `docker-compose.tls.yml` + `frontend/nginx.tls.conf.template`) · `.tls_stage2`(2단계 = `docker-compose.tls2.yml` 이 `tools/ops/tls_stage2/` 스니펫을 마운트). 켜고 끄는 것은 `tools/ops/tls_enable.sh` · `tools/ops/tls_stage2_enable.sh` 이고, 사후 검증에 실패하면 두 스크립트가 **마커 삭제 + 이전 단계 원복까지 스스로 실행**한다. `compose_up_changed.sh` 는 마커가 있을 때만 `-f` 오버레이를 덧붙이고 **모드 판정에는 개입하지 않는다**(개입하면 TLS 를 켠 날부터 모든 배포가 backend 재시작이 되어 cycle248 이 없앤 비용이 부활한다). 인증서 갱신은 `certonly --deploy-hook` 으로 renewal conf 에 영속돼 snap/apt timer 가 돌린다 — **crontab 을 두지 않는다**(ubuntu crontab 은 `/etc/letsencrypt` 쓰기 불가, 상대경로 compose 는 cron cwd 에서 실패). 🔴 **TLS 템플릿에 `map` 을 중복 정의하지 않는다** — nginx 는 **정상 기동**하고 뒤에 include 되는 map 이 조용히 이겨 모든 사용자의 `X-API-Key` 가 빈 값이 된다(무증상 backend 전면 401). 텍스트 가드 G-255-2f 가 유일한 방어다. `auth_basic off;` 금지는 여기서도 불변(D-1-b). **Basic 자격 회전은 `tools/ops/rotate_basic_auth.sh` 로 한다**(실행 이력은 워크리스트) — 301 은 서버가 자격을 요구하지 않게 할 뿐 브라우저가 선제로 보내는 옛 자격까지 막지 못한다. 새 비밀번호는 화면에 찍지 않고 `secrets/.rotated-<ts>`(권한 600) 로만 전달되므로, 운영자가 그 값을 클라우드 루틴의 `REPORTER_BASIC_PASSWORD` 에 넣고 브라우저를 재로그인해야 회전이 끝난다
```

사유: TLS 단계별 가동 날짜(1단계 2026-09-05 · 2단계 09-08)는 시점 꼬리라 정본에서 뺐다.

### 디렉토리 역할 — src/api/

```
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). `quotation.py::inquire_ccnl(ticker, market='J')` — FHKST01010100 주식현재가 시세, output[0] + today_volume 합산 + graceful None (stale universe 가드용)
```

사유: 코드 사실 정정: `inquire_ccnl` 의 TR 은 `FHKST01010100`(주식현재가 시세)이 아니라 `FHKST01010300`(주식현재가 체결)이다(`src/api/quotation.py::inquire_ccnl` docstring).

### 디렉토리 역할 — src/services/

```
- `src/services/` — 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `macro_client.py` 매크로 레짐 — 우리 `macro` 컨테이너를 평문 GET 으로 부른다, 인증 없음 / `quote_session_health.py` 보조 세션 health monitor)
```

사유: 누락 보강: `src/services/exceptions.py` 가 어느 정본에도 없었다. 목록 정본 = `src/CLAUDE.md` 「진입점」 절.

### 디렉토리 역할 — src/middleware/

```
- `src/middleware/` — API 인증(`X-API-Key`)·리포터 스코프 최외곽 미들웨어 (전용 CLAUDE.md 없음)
```

사유: `src/CLAUDE.md` 「진입점」 절 링크만 덧붙였다.


### 검증 지적 반영 — 핵심 안전 규칙 (절대 깨지 말 것) · DB 스키마

이 절의 앞 사유 문장 중 셋이 정본 위치를 잘못 가리켰다. 이번 반영에서 정본에 되살리거나 고친 것:

- 체결통보 race 가드 — 앞 사유는 「`execute_buy` ERROR 종료·`buy_succeeded` 후처리 누락」 의 정본이 engine race 가드 ② 라고 적었지만 그 자리에 없다. 결과 한 구절을 루트에 되살렸다(코드 = `src/engine/scheduler.py` 의 `_swing_buy_poll_loop` 안 `buy_succeeded` — 예외면 `False` 가 되어 매수 직후 HIGH 구독이 빠진다).
- WebSocket 다중 안전망 — 앞 사유는 `_subscriptions` ACK 정합성 가드의 정본을 `src/realtime/CLAUDE.md` 「안전 규칙 (멀티 세션)」 이라 적었지만, 가드 본문은 같은 파일 「subscribe / 거절 감지 / ACK 추적」 절에 있다. 루트 링크를 그 절로 바꾸고 가드 이름을 남겼다.
- 보유 전략 끄기 금지 — 원문 「둘 다 보유 조회 실패는 **fail-open**」 은 코드와 다르다. 순수 fail-open 은 자문 적용 경로(`src/routes/recommendations.py::_reject_zero_weight_if_held` → `[weight_zero_guard_degraded]`)뿐이고, 비중 PUT 경로(`src/routes/strategies.py::_held_tickers_from_db`)는 DB 예외 때 `[weight_zero_probe_degraded]` 를 남기고 메모리 `state.positions` 로 판정한다.
- `nxt_tradable` 용도 — 원문 「5 전략」 과 압축본 「전략은 전부」 둘 다 부정확했다. `list_by_filter` 호출은 6전략(kojiro·BFB·donchian·VB·LTV·VCP)이고 `momentum.py` 에는 없다. donchian·kojiro 는 파라미터 `nxt_tradable`(코드 기본값 `None`)로 넘긴다.
- silent inactive — `src/realtime/CLAUDE.md` 의 같은 항목이 「상세는 루트 `CLAUDE.md`」 로 위임하므로 루트에 마커 이름 `[silent_inactive_market_wide_skip]` 을 남겼다.
- DB 스키마 `llm_buy_evaluations` 행 — `docs/architecture.md` 가 이 행을 열 정의 정본으로 가리킨다. 루트 행에 `src/db/CLAUDE.md` 「llm_buy_evaluations.py — AI 매수평가 기록」 절 링크를 달았다.

---

## 2026-10-02 sync-docs 압축 2차 — 정본에서 이관

출처 = 루트 `CLAUDE.md`(1차 압축 반영본, 미커밋 · 기준 HEAD `979c30b2`). 사용자 요청 「유지해야할 내용도 전반적으로 압축하자」.
절 제목은 이관 시점의 정본 절 제목이다. 바뀌거나 빠진 줄 전체를 원문 그대로 옮겼다(일부만 바뀐 줄도 줄 전체).
「핵심 안전 규칙」 항목은 줄인 조건이 링크한 하위 정본에 같은 조건으로 있는 것을 grep 으로 확인한 뒤에만 줄였다.

### 기본 진입점 — `team-leader` 우선 — 문서 동기화 → /sync-docs

```
- **문서 동기화 → `/sync-docs` 명령 (Phase 4.8, 코드 변경 사이클은 커밋 전 필수)** — 코드 위치 → 갱신 후보 문서
  매핑 표 + **대상 문서 정본 목록** + 모듈 누락 자가 점검을 담은 유일한 체크리스트다.
  ⚠️ 전용 `CLAUDE.md` 가 없는 `src/services/` · `src/middleware/` · `tools/` · `e2e/` 가 누락 반복 지점
  **실행 주체 = `report-writer` 에이전트**(2026-09-11 사용자 결정) — 메인 세션은 꾸러미만 만들어 위임하고
  커밋 여부만 정한다. 쉬운 말로 유지하되 식별자·상수·불변식·금기 조건은 인용 대상이라 흐리지 않는다.
```

사유: 5줄을 한 줄로 합쳤다.

### 기본 진입점 — `team-leader` 우선 — ⚠️ KIS 스펙의 시간 경계

```
- **⚠️ KIS 스펙의 시간 경계 — `docs/kis/*.md` 는 2026-09-11 03:00 워크북 스냅샷이라 「변경 전」 세계를 기술한다.** 거기엔 시간외 단일가(16:00~18:00)가 살아 있고 `H0STOUP0` 가 현역으로 적혀 있다. **2026-09-14 시행 제도 변경(KRX 애프터마켓 16:00~20:00 신설·시간외 단일가 폐지·시가단일가 08:20 확대·KRX 정규장 미체결 자동취소)은 세 곳에 나눠 적혀 있다** — 제도·시간표·보드 영향 = [`src/engine/CLAUDE.md`](src/engine/CLAUDE.md) `session.py` 절 · TR·필드 변경 = [`docs/kis/README.md`](docs/kis/README.md) 「제도 변경 공지 반영」 절(+ 각 필드 자리에 직접 반영, `docs/kis` 재생성 시 그 절을 보고 다시 넣는다) · 우리 할 일·실측 목록 = [`_workspace/00_URGENT_WORKLIST.md`](_workspace/00_URGENT_WORKLIST.md). 09-14 이후의 사실을 `docs/kis/` 에서만 찾으면 틀린 답이 나온다. 순서 = 위 세 곳 → `kis-mcp-query` → `docs/kis/*.md` 본문
```

사유: 문장만 줄였다. 경계 규칙·세 곳·순서는 그대로다.

### 기본 진입점 — `team-leader` 우선 — 외부 검색 → insane-search

```
- **외부 검색 → `insane-search` 스킬 (2026-09-11 사용자 지시)** — 리포 밖 정보를 찾을 때 `WebFetch` 로
  시작하지 않는다. 402·403·차단 응답, 스크립트로 그려져 껍데기만 오는 페이지, X·레딧·유튜브·깃헙
  검색·네이버 등 봇 차단이 있는 곳이 대상이다. 단순 검색은 `WebSearch`, KIS 스펙은 `docs/kis/*.md`
  와 `kis-mcp-query` 가 먼저다. **모든 에이전트에 같은 규칙이 적힌다**
```

사유: 4줄을 한 줄로 합쳤다.

### 모델 라우팅 — 모델 라우팅 — opus 행

```
| 구현 계획·검수·리팩토링 검토·마무리 보고서 | **opus** | `team-leader`, `tester`, `refactor-expert`, `report-writer` — ⚠️ **모델은 에이전트 정의에 명시한다.** 지정을 지우면 상속이 Fable 로 해석돼 그 모델의 크레딧이 마르면 넷이 한꺼번에 막힌다. 세션 모델이 바뀌면 이 네 줄도 같이 바꾼다 |
```

사유: 문장만 줄였다.

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정) — 자율 진행 구간 머리 문단

```
**승인은 결정 지점에서만 묻는다.** **자율 진행 구간**은 사용자가 (a) 구간의 끝(시각 또는 할 일 목록)과 (b) 커밋·배포 허용 여부를 **명시**했을 때만 성립한다(예: "06:30까지 승인 없이 진행, 커밋은 작업 단위로"). "진행해" 한마디는 그 작업의 구현·검증까지의 승인이며, 커밋·push 는 별도로 묻는다(메모리 "커밋은 명시 지시 시에만" 정책의 유일한 예외가 명시된 자율 구간이다). 구간 안에서는 사전 승인 범위(아래) 에 한해 구현 → 검증 → 커밋(작업 단위) → 배포 → 실측 확인까지 사이클마다 다시 묻지 않고 이어서 진행하고, 구간의 끝에 `cycle-report` 스킬로 **한 번** 보고한다(쉬운 말 아티팩트 + 원문 md + 결정 카드). 보고서의 "결정해 주세요" 카드가 그동안 미룬 승인 요청을 **모아** 전달한다 — 보고서가 승인을 대신하지는 않는다.
```

사유: 문장만 줄였다(보고서 구성 괄호는 report-writer 정의가 정본). 예시 괄호(「06:30까지 승인 없이 진행, 커밋은 작업 단위로」)를 뺐다.

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정) — 8영역

```
- **8영역** = `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**` (정본 목록 = `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS`, 승인 시 그 파일의 sha 핀 절차를 따른다). `scheduler.py` 는 8영역은 아니지만 **라인 상한 `<3,900L`**(cycle257 이 세운 영구 상한) 때문에 같은 승인 대상이다 — 여러 AST 가드가 이 상한을 복창하며, **두 수가 갈라지면 항상 더 조인 쪽이 정본이다**.
```

사유: 문장만 줄였다.

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정) — 사전 승인 범위 (b) 항

```
- **사전 승인 범위** (아래 셋을 **모두** 만족할 때만): (a) 8영역·`scheduler.py` 무접촉 — 8영역 안이면 관측 로그 한 줄도 승인 (b) 배포는 운영 가이드의 장외 창 안 — **15:30~16:00 · 21:35~익일 07:45**(backend 재생성 1~5분 여유) · 주말·공휴일 종일. **20:00~21:35 는 자율 구간 중에도 push 금지**(cycle283 D8 — 20:00 자문·20:05 metrics 1차 스냅샷·20:30 일봉 적재·21:30 정산/`_reset_daily_state` 가 재시작에 끊긴다. 게다가 그 창의 재기동은 `TIME_SESSION_START_CUTOFF`(20:00) 때문에 **거부**되므로 그날 20:30 일봉 적재를 통째로 잃는다). 모드 판정이 불확실하면 full(재시작)로 간주(cycle248) (c) 다음 커밋으로 원복 가능. 테스트·문서·관측 전용 변경도 (a) 를 만족할 때만 포함. DB 스키마는 가산형 마이그레이션(NULL 허용 ADD COLUMN·INDEX·신규 테이블)만 포함.
```

사유: 20:00~21:35 금지의 이유(저녁 블록·기동 거부)는 같은 파일 「Docker / 배포」 운영 가이드와 같은 문장이라 링크로 줄였다. 두 창 문자열(`21:35~익일 07:45`·`20:00~21:35`)은 남긴다.

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정) — 여전히 승인이 필요한 것

```
- **여전히 승인이 필요한 것(구간 중에도 멈추고 묻는다 — 위 범위와 충돌하면 이 목록이 항상 우선)** = 8영역·`scheduler.py` 변경 · 보유 중 장중 push(D6) · 기능·설정 비활성화(심층 검증 의무) · 되돌리기 어려운 운영 조치(DB UPDATE/DELETE·DROP·타입 변경·NOT NULL 백필, 수동 매매, 키 회전, 구독·세션 강제 조작) · 사용자 결정 항목(비중·파라미터 값·전략 on/off·자금 **+ 매매 행위를 바꾸는 코드 변경 — 진입·청산·수량·사이징·손절 규약·`DEFAULT_PARAMS` 신규 키 — 는 파일 위치와 무관하게 승인 + `domain-consult` 선행**) · 외부로 나가는 조치(메일·PR 머지·루틴(schedule) 생성/변경·Notion 쓰기·외부 서비스 설정). 단, **이미 승인된 사이클 명세에 포함된** 외부 설정·배포 전 DB 선반영(예: cycle245 §7.1 K=20 선반영)은 그 승인에 포함된 것으로 보되, 실행 전후 값을 보고서 "서버에 올린 것" 표에 남긴다.
```

사유: 예시 괄호(cycle245 §7.1 K=20 선반영)를 뺐다.

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정) — 보고 시점

```
- **보고 시점** = `cycle-report` 스킬 정본의 트리거 4 (① 사이클 3회 이상 연속 완료 ② 자율 진행 구간(주·야간 무관) 종료 ③ 사용자의 "리포트/보고서/정리해 줘" 요청 ④ 세션 종료 전 사용자가 못 본 배포·결정 누적). 사이클 1~2회라도 결정 항목 3개 이상이면 호출. 그 밖에는 터미널 요약으로 충분하다.
```

사유: 트리거 4 목록은 같은 파일 「기본 진입점」 의 마무리 보고 줄과 같다.

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정) — 보고서 기준

```
- **보고서 기준** = `.claude/agents/report-writer.md` 의 구조·쓰기 규칙(용어 풀이 → 한눈에 → 시간순 → 발견 → 결정 카드 → 확인 목록 → 승인 시 할 일 → 함께 만든 것·배운 점 → 바닥글). 사실은 정본(git·changelog·워크리스트·호출자 검증 결과·포렌식/자문 문서)에서만, 예상과 실측 구분, 커밋 해시는 바닥글에만. report-writer 는 커밋·push 를 하지 않는다(메인 세션이 커밋 정책에 따라 결정). 기준 예시 = `.claude/skills/cycle-report/example_2026-09-05.html` + 원문 `_workspace/reports/2026-09-05_night_autonomous_work.md`.
```

사유: 보고서 구조 순서·사실 출처·예상과 실측 구분·커밋 해시 위치, 「report-writer 는 커밋·push 를 하지 않는다(메인 세션이 커밋 정책에 따라 결정)」 는 report-writer 정의 「하지 않는 것」 절에 같은 규칙이 있다.

### 병렬 작업 — 같은 작업 디렉터리는 git 이 지켜 주지 않는다 — 병렬 작업 머리 문단

```
동시에 여러 에이전트를 띄울 때, **파일을 쓰는 에이전트**는 서로의 편집을 덮어쓸 수 있다. git 이 지키는 것은 **커밋된 것**이고 커밋 전 편집본끼리는 나중에 쓴 쪽이 이긴다. 2026-09-19 실측 사고 = 동시 작업이 `src/routes/market_regime.py` 의 내용을 `src/engine/market_regime.py` 에 써서 750줄 매매 모듈이 123줄 라우트 사본이 됐다.
```

사유: 사고 서사(750줄 → 123줄)를 이관하고 사고 이름 한 구절만 남겼다.

### 병렬 작업 — 같은 작업 디렉터리는 git 이 지켜 주지 않는다 — 병렬 작업 — worktree 격리

```
- **쓰는 에이전트를 동시에 띄우면 `isolation: "worktree"`** — 읽기만 하는 에이전트(조사·검토·렌즈)는 그대로 둔다. 격리는 에이전트당 디스크와 준비 시간을 쓰므로 쓰기가 실제로 겹칠 때만이다.
```

사유: 문장만 줄였다.

### 병렬 작업 — 같은 작업 디렉터리는 git 이 지켜 주지 않는다 — 병렬 작업 — git add -A

```
- **띄우기 전에 `git add -A`** — 그러면 덮어써도 `git checkout -- <path>` 한 줄로 돌아온다(그 사고의 실제 복구 경로다). 커밋이 아니라 인덱스 스냅샷이라 커밋 정책과 무관하다.
```

사유: 「그 사고의 실제 복구 경로다」 꼬리를 뺐다.

### 병렬 작업 — 같은 작업 디렉터리는 git 이 지켜 주지 않는다 — 병렬 작업 — 자동 덫

```
- 자동 덫 = `tests/unit/deploy/test_cycle319_no_clobbered_module.py` (`src/` 안에 내용이 같은 파일 쌍 = 0). 덮어쓰기는 거의 항상 **다른 파일의 사본**이라 이것으로 잡힌다. 부분 덮어쓰기는 못 잡으므로 위 두 습관이 본체다.
```

사유: 문장만 줄였다.

### 하네스 변경 이력 — 하네스 변경 이력

```
사이클별 변경 이력은 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 가 **유일한 정본**이다(상단이 최신).
이 문서에는 이력표를 두지 않는다 — 규약은 위 「문서 규약」 절.
```

사유: 두 줄을 한 줄로 합쳤다.

### 환경 변수 — SUPABASE_URL / SUPABASE_KEY

```
- `SUPABASE_URL`, `SUPABASE_KEY`: **런타임 미사용이지만 설정은 필수다.** 어느 db 모듈도 참조하지 않고
  (`src/db/supabase.py` 는 롤백용 병존) 값이 무엇이든 동작에 영향이 없지만, `src/config.py:36-37` 의
  `supabase_url: str` / `supabase_key: str` 가 **기본값 없는 필수 필드**라 비우거나 빼면 pydantic 검증에
  걸려 **기동 자체가 실패한다**. 새 환경을 만들 때 "미사용이니 비워도 된다" 로 읽으면 안 된다
```

사유: 4줄을 한 줄로 합쳤다. 조건(필수 필드·기동 실패)은 그대로다.

### 환경 변수 — API_AUTH_KEY

```
- `API_AUTH_KEY` (cycle243): 백엔드 `X-API-Key` 인증 키. **미설정이면 fail-closed** — `/health` 를 뺀 전 경로 401 + 기동 시 `[api_auth_key_missing]` CRITICAL. 조용히 끄지 않는다(금기 = 「핵심 안전 규칙」 API 인증 항목). 생성 `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`. 운영에서는 nginx 가 프록시 요청에 주입해 브라우저에 노출되지 않는다. 키 회전은 frontend·backend **동시 재시작**이 필요하므로 장 종료 후에만
```

사유: 문장만 줄였다.

### 환경 변수 — API_REPORTER_KEY

```
- `API_REPORTER_KEY` (cycle249, 기본 빈 값 = 리포터 역할 비활성): 리포터 스코프 키 — 허용 범위는 **GET/HEAD 전체 + `POST /api/log-reports/{date}/external` 단 한 경로**뿐이다(20:20 KST 클라우드 루틴이 로그 번들을 읽고 분석 결과를 쓰는 유일한 창구). nginx `map $remote_user` 가 Basic 사용자 `reporter` 에게만 이 값을 주입한다(운영 키를 보내는 `default` 사용자와 다른 값이어야 판정이 성립). 미설정이면 어떤 요청도 리포터로 통과하지 못한다(fail-closed)
```

사유: 문장만 줄였다.

### 환경 변수 — DKSTOCK_REGIME_ENABLED

```
- `DKSTOCK_REGIME_ENABLED` (기본 false): 매크로 레짐 수신 + cash_usage_ratio 자동 조정 활성화 (레짐은 관찰 전용 — 매수를 차단하지 않는다). 출처는 **우리 `macro` 컨테이너**(`MACRO_API_URL`, 기본 `http://macro:8000`)다. 🔴 **변수명은 유지한다** — 운영 DB `system_config.dkstock_regime_enabled` 행과 짝이고, 개명하면 그 행이 고아가 된다. 판정은 **DB 우선 / `.env` fallback** 이다(`services/macro_client.py`). 상한 = `MACRO_API_READ_TIMEOUT_SECS`(90초) · 부팅 전용 `MACRO_API_BOOT_TIMEOUT_SECS`(25초)
```

사유: 「레짐은 관찰 전용 — 매수를 차단하지 않는다」 는 같은 파일 「외부 통합」 절과 같은 문장이다.

### 자금 관리 — 자금 관리 — 전략 비중 단위

```
- **전략 비중 단위 = 비율 `0.0~1.0`** — `PUT /api/strategies/weights` 요청 바디 · `GET /api/strategies` 응답 `weight` · `strategy_config.weight` 컬럼 · AI 자문 `save_weights` 경로가 **모두 같은 단위**라 GET↔PUT 왕복이 항등이다. 라우트가 범위 위반은 422, Σ>1.0 payload 는 `success=false`(저장 미수행)로 거부하고, 부팅 시 `_load_strategy_config` 가 **레지스트리 등록 전략 행**의 개별 `weight > 1.0` 또는 Σ `> 1.001` 을 `[weight_config_anomaly]` WARNING 으로 관찰만 한다 — **자동 클램프·정규화 금지**(오염 값을 조용히 그럴듯하게 만들면 운영자가 실측할 근거가 사라진다), fail-open
```

사유: 422·`success=false` 거부 규칙은 같은 파일 「비중 단위 추론 변환 금지」 항목과 routes 「전략 설정 쓰기 경로」 절에, 부팅 감지 조건(등록 전략 행·개별 `weight > 1.0`·Σ `> 1.001`·fail-open)과 클램프 금지 이유는 engine `scheduler.py` 절 `_load_strategy_config()` 항목에 있다.

### 자금 관리 — 자금 관리 — 전략별 투자한도 — 삼중

```
- **전략별 투자한도 — 삼중** — ① 개수 `max_positions` ② 명목 `Σ매수금액 ≤ total_investment`(관문 `StrategyBase._apply_budget_limit` 이 강제 — 잔여가 부족하면 **부분 매수**, 잔여 < 1주 → 0) ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). 유닛 **개수는 리스크의 프록시**일 뿐이지만 **개수 캡을 리스크 캡으로 대체 금지**(저ATR 종목 포지션 수 폭증). 불변식 **`position_ratio × max_positions ≤ 1.0`** — DEFAULT_PARAMS 는 AST 가드(C-DEFAULT)가, AI 추천은 `_validate_recommendations` 교차검증이 강제. `max_positions` 는 리스크 정체성 상수라 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**. 상세 = `src/engine/strategies/CLAUDE.md` 「자금관리 — 사이징 방식 × 손절 기준 매트릭스」 절
```

사유: 「유닛 개수는 리스크의 프록시」 설명은 strategies 「자금관리」 절 「제한 축은 셋」 항목에 있다.

### 자금 관리 — 자금 관리 — 1회 투자금액 ATR 유닛화

```
- **1회 투자금액 ATR 유닛화 (`sizing_mode="turtle"`)** — `unit = floor(전략예산 × risk_pct ÷ ATR)`. **손절이 ATR 기반인 전략에만 적용**한다 — 손절이 고정%면 명목이 종목 무관 상수라 `position_ratio` 가 이미 리스크 균등이고, 사이징만 ATR 로 바꾸면 정규화가 깨진다(함정 #1). 배선 = donchian · kojiro · VCP/BFB(하드손절 ATR화 동반). momentum/VB/LTV 는 제외한다(전략별 사유 = 위 매트릭스 절). `compute_unit_qty_guarded` 의 notional 상한이 `position_ratio × 예산` 이라 **터틀 수량 ≤ 비중 수량**이 항상 성립 = 전환은 순수 축소 방향.
  🔴 **유닛화가 랏 미세화를 풀지 못한다** — 정수 절삭은 유닛식에도 똑같이 있다. 랏이 1주 언저리인 원인은 사이징 방식이 아니라 **설계 랏 ÷ 그 전략이 사는 종목의 중앙 주가**(= `q`, 순자산에 정비례)다. 비중·자금을 손대지 않은 채 유닛만 도입하면 `floor(예산 × risk_pct ÷ ATR) = 0` 이 되어 그 전략이 **전면 무매매**가 된다. 고칠 대상은 사이징이 아니라 전략 간 배분이다.
```

사유: 배선 목록·`compute_unit_qty_guarded` 상한·`q` 정의는 strategies 「자금관리」 절(표·「터틀 수량 ≤ 비중 수량」·「유닛화는 랏 미세화를 풀지 못한다」)에 있다. 두 줄을 하나로 합쳤다.

### 자금 관리 — 자금 관리 — 랏당 최대 유닛 상한 `max_lot_units`

```
- **랏당 최대 유닛 상한 `max_lot_units` (K=2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든** 매수 랏(터틀 유닛·`position_ratio` 낙하·1주 폴백)을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고, 그 값이 0 이면 **매수하지 않는다**(`min` — 매수를 줄이는 방향뿐). ATR 결측·모호(`atr`↔`atr14` 상이)·`risk_pct ≤ 0`·예외는 **fail-open**(현행 수량 유지 + `[fallback_cap_skipped]` WARNING) — fail-closed 는 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이라 금지. K 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-242-1), 읽는 쪽 `[1.0, 20.0]` 클램프(하한 1.0 = 정상 터틀 랏이 캡에 안 걸리는 전제, 상한 20.0 = 롤백 다이얼). 롤백 = 해당 전략 `max_lot_units = 20.0` — `PUT /api/strategies/{id}/params` 는 **즉시**, `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만** 반영되므로 보유 중 장중 롤백은 PUT 뿐이다(cycle232 D6). 산출식 재사용 · ATR 소스 · 「K유닛 = 예산 2.0% 노출」의 범위 · 피라미딩 제약 · 당일 `_bought_today` 소진 = strategies 「자금관리」 절
```

사유: 산출식 재사용·ATR 소스(`_candidates[ticker]` read-only)·「K유닛 = 예산 2.0% 노출」 범위·피라미딩 제약·당일 `_bought_today` 소진은 다음 세션부터만 회복·클램프 하한·상한의 뜻은 strategies 「자금관리」 절 K축 항목에 있다.

### 자금 관리 — 자금 관리 — 랏 명목 ρ축 상한 `max_lot_ratio_mult`

```
- **랏 명목 ρ축 상한 `max_lot_ratio_mult` (K_ρ=2.5, cycle245)** — 관문을 지나는 **모든** 랏의 명목을 `K_ρ × position_ratio × 예산` 이하로 자르고, **1주도 못 사면 매수하지 않는다**(`min` — 줄이는 방향뿐). 1주 폴백 랏의 크기가 설계가 아니라 그 종목 주가로 정해지는 것을 막는 캡이라 실효는 1주 폴백 랏뿐이다. K축이 심사한 랏도 ρ축이 `min` 으로 후심사한다(cycle254). **키 부재 = OFF**(`max_lot_units` 관례와 **반대** — 매수를 막는 통제라 "설정이 없으면 막는다"는 유령 키 재현 경로다). 키는 **7 전략 전부**의 `DEFAULT_PARAMS` 에 명시한다(AST glob 전수). `position_ratio` 결측·예산 0·초소액·판정 예외는 **fail-open**(`[ratio_cap_skipped]` WARNING). K_ρ 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS`·AI 자문 자동 적용 경로 **편입 금지**(AST G-245-1), 읽는 쪽 `[1.0, 20.0]` 클램프(하한 1.0 미만은 주 분기까지 잘라 전면 무매매). 롤백 = 해당 전략 K_ρ=20.0(반영 시점은 K축과 같다). 산식 · 조기탈출 조건 · 마커 = strategies 「자금관리」 절
```

사유: fail-open 사유 열거(`position_ratio` 결측·예산 0·초소액)와 클램프 하한 1.0 의 뜻(미만이면 전면 무매매), 시정 경위(1주 폴백 랏 크기가 주가로 정해지던 결함)는 strategies 「자금관리」 절 ρ축 항목에 있다.

### 자금 관리 — 자금 관리 — 시장 유닛 `market_unit_mode`

```
- **시장 유닛 `market_unit_mode` (cycle382, 사용자 결정 2026-09-27)** — 장세(KODEX 200 `069500` 직전 영업일 봉의 60일선 위·아래 × 60일선 상승·하락)에 따라 터틀 4전략(`kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout`)의 **신규 진입 설계 랏만** 1 / 0.75 / 0.5 / 0 배로 줄인다(0 = 그날 신규 진입 없음). **무접촉** = `total_investment`·잔여 클램프·K축·ρ축·kojiro 오픈리스크 캡·`cash_usage_ratio`·보유분·청산 규약 — 예산 경로로 줄이면 7전략 전부와 일일 손실 분모·정산 기준선이 함께 흔들린다. 축소일(`enforce` ∧ m<1)에는 1주 폴백도 터틀→`position_ratio` 낙하도 없고, 줄인 랏으로 못 사는 종목은 수량 0 이 아니라 **신호 단계 `Signal.NONE`** 으로 거른다(수량 0 은 「매수 수량 0 → 900s cooldown」 으로 오귀인된다). 결측·stale·예외 = **m=1**(현행 그대로) + WARNING — 장세 데이터 결손이 매수를 조용히 줄이면 안 된다. 모드 `off|shadow|enforce` — 부재·오타 = `off`, 4전략 기본 = `shadow`(계산·기록만). 켜고 끄기 = 전략마다 `PUT /api/strategies/{id}/params {"params":{"market_unit_mode":"off"|"shadow"|"enforce"}}`(**즉시**). `PARAM_RANGES`/`INT_PARAMS`·AI 자문 자동 적용 경로 **편입 금지**. 🔴 **매크로 레짐과 다른 축이다** — 레짐 게이트가 아니라 전략 사이징이다. 규칙 = `src/engine/strategies/CLAUDE.md` 「시장 유닛 — 터틀 4전략 (cycle382)」 절 · 계산 자리·마커 = `src/engine/CLAUDE.md` `strategy_base.py` 절
```

사유: 무접촉 목록 전체·예산 경로를 쓰지 않는 이유·축소일(`enforce` ∧ m<1)에 1주 폴백·`position_ratio` 낙하가 없다는 조건·PUT 바디·WARNING 마커 이름은 strategies 「시장 유닛」 절에 같은 조건으로 있다.

### 자금 관리 — 자금 관리 — cash_usage_ratio

```
- **`cash_usage_ratio`**: `system_config.cash_usage_ratio` 키 — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 `[0.0, 1.0]`, 5% 단위, 기본 1.0. Settings 슬라이더로 조정 → **다음 영업일부터 반영**. `auto_regime_adjust` 가 켜져 있고 `DKSTOCK_REGIME_ENABLED=true` 면 매크로 레짐 `cash_min` 기반 자동 갱신 (`clamp((100-cash_min)/100, 0.0, 1.0)`). `auto_regime_adjust` 의 판독 불가(키 없음·형식 오류·예외)는 전부 **false(수동 모드)** 다(`src/db/CLAUDE.md` 「system_config.py — 시스템 설정 키-값 헬퍼」 절)
```

사유: 문장만 줄였다.

### 외부 통합 (백테스트 + 매크로 레짐) — 외부 통합 — 매크로 레짐

```
- 매크로 레짐 (**우리 `macro` 컨테이너**, cycle315) — `regime/vix/fear_greed` 관찰 + `cash_usage_ratio` 자동 조정 (`auto_regime_adjust`, `clamp((100-cash_min)/100)`). **매크로 레짐은 관찰 지표다 — 매수를 차단·축소하지 않는다**(`buy_block_mode` 는 표시 전용, `get_buy_block_state` 는 대시보드/자문 payload 만 소비). 장세에 따른 신규 진입 축소는 매크로 레짐이 아니라 **시장 유닛**(「자금 관리」 절 `market_unit_mode`)이 전략 사이징에서 한다. ETF 레짐·포트폴리오 리스크 관찰 활성
```

사유: 자동 조정 식은 같은 파일 「자금 관리」 `cash_usage_ratio` 항목과 같다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 기능·설정 비활성화 시 심층 검증 의무

```
- **기능·설정 비활성화(disable / toggle off / dead 판정) 시 심층 검증 의무** — 무언가를 "미사용/dead/낭비"라고 단정하기 **전에 소비처(consumers)를 `grep` 으로 전수 확인**하고, 비활성화 **후에는 그 소비처의 산출물(예: 적재 종목수)을 라이브 실측**으로 확인한다. **비활성화는 "제거"가 아니라 "경로 변경"일 수 있다** — 주 경로를 끄면 폴백 경로가 조용히 degrade 된다. 설정 토글은 CI/Deploy 를 안 타므로 자동 검증도 없다. 실측 없는 비활성화 금지 — 2026-08-08 `krx_open_api_enabled` 를 "무효 키·낭비"로 오판해 끈 결과 주 소스 `scanner._full_universe_load_krx_primary` 가 폴백으로 밀려 `full_universe_load` 가 3,577→60종목으로 degrade 됐고 D+1 에야 발견됐다
```

사유: 사고 경위(주 소스 `scanner._full_universe_load_krx_primary` 가 폴백으로 밀림·D+1 발견)를 이관하고 사고 이름 한 구절만 남겼다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 보유 전략 끄기 금지

```
- 🔴 **보유 포지션이 있는 전략을 끄지 않는다 — 끄는 순간 그 포지션의 손절이 멈춘다.** `risk.on_tick` 이 `registry.enabled()`(= `config.enabled` 참인 것만) **단일 순회**라, 끈 전략의 보유분은 손절·트레일링·익일청산·15:20 강제청산이 **전부 정지**하고 아무도 보지 않는 채 남는다. 끄기 전에 **그 전략 보유 0 을 확인**하거나 먼저 청산한다. `enabled` 축 시정은 미착수이고 `src/engine/CLAUDE.md` 가 「의도적 미시정」으로 적어 둔 상태다. 🔴 **`weight=0` 도 끄기다** — `registry.update_weights` 가 **`config.enabled = weight > 0` 을 자동 토글**하므로 비중 0 = **즉시 비활성화 = 손절 정지**다. 그래서 보유가 있는 전략의 비중 0 은 두 경로가 모두 거부한다 — `PUT /api/strategies/weights` 와 `POST /api/recommendations/{id}/apply`(AI 자문 적용 — 비중만 거부하고 파라미터 적용은 진행, `[weight_zero_guard]`). `PUT /api/strategies/weights` 는 보유 매수금액 비율 미만의 비중도 거부한다(「매수금액 하한선 검증」 — "보유 종목 매도 후 비중을 줄여주세요"). 보유 조회가 실패하면 자문 경로는 막지 않고(**fail-open** `[weight_zero_guard_degraded]` — 판정 불가를 차단으로 바꾸면 적용 경로가 DB 가용성에 묶인다), 비중 PUT 경로는 메모리 보유로 판정한다(`[weight_zero_probe_degraded]`). 끄는 길은 **그 전략 보유를 먼저 비우고** 끄는 것 하나뿐이다. ⚠️ 「전략 수를 줄여 전략당 예산을 키운다」는 처방이 이 금기를 정면으로 밟는다. 용도별 수단 — **랏을 키우려면** `max_positions`(슬롯)를 줄이고 `position_ratio`(종목당 비율)를 올린다(`position_ratio × max_positions ≤ 1.0` 불변식 유지, **`weight` 는 무접촉**) · 보유한 채로 신규 유입을 **줄이려면** `position_ratio`·`max_positions`(PUT params — `enabled` 를 건드리지 않고 하한선 검증도 없다) · **멈추려면** `buy_paused`(바로 아래). 경로별 가드 = `src/routes/CLAUDE.md` 「전략 설정 쓰기 경로 — 비중 · 파라미터 · AI 자문 적용」 절
```

사유: 경로별 가드(자문 경로는 비중만 거부·파라미터는 진행, `[weight_zero_guard]`, 매수금액 하한선 검증 문구, 조회 실패 시 `[weight_zero_guard_degraded]` fail-open / `[weight_zero_probe_degraded]` 메모리 판정)는 `src/routes/CLAUDE.md` 「전략 설정 쓰기 경로」 절에 있다. 「끄는 길은 보유를 먼저 비우는 것 하나뿐」 은 첫 문장 「끄기 전에 보유 0 확인 또는 먼저 청산」 과 같은 규칙이다. `enabled` 축 시정이 미착수라는 사실은 `src/engine/CLAUDE.md` 「의도적 미시정」 문단에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 신규 매수만 멈추기 = buy_paused

```
- 🔴 **신규 매수만 멈추기 = `buy_paused` (cycle384 — 사용자 결정 2026-09-27 「돈키언 신규매수 중지」)** — 7 전략 공통 `DEFAULT_PARAMS["buy_paused"]=False`. `PUT /api/strategies/{id}/params {"params":{"buy_paused":true}}` 로 켜면 그 전략의 **신규 매수 신호만** 멈추고, 보유분의 손절·트레일링·익일청산·15:20 강제청산·종목상태 청산·시간 청산은 그대로 돈다. 반영은 **즉시**이고 DB 에 저장돼 재시작 뒤에도 유지된다. 🔴 **신호 단계에서 막는다**(공통 매수 게이트 `StrategyBase._account_soft_gate_blocked` 의 둘째 문장) — 수량 0 반환(900초 「투자금 부족」 오귀인) · `buy_disabled`(일일 손실 래치) · `enabled`·`weight`(손절 정지)로 대신하지 않는다. 🔴 **`is True` 일 때만 멈춘다** — 키 부재·`False`·문자열 `"true"`·`1` 같은 다른 모양은 멈추지 않음 + WARNING, PUT 은 bool 이 아니면 422 다. 🔴 `PARAM_RANGES`/`INT_PARAMS` **편입 금지** — AI 자문(수동·자동 적용)이 켜고 끄면 안 된다(AST `test_cycle384_ast_buy_paused.py` A11). 🔴 **멈춰 둔 동안 코드에서 키를 지우지 않는다** — 키가 없는 코드가 배포되면 `_load_strategy_config` 가 DB 의 `true` 를 버려(`if key in strategy.config.params`) 조용히 풀린다. 상세 = `src/engine/CLAUDE.md` `strategy_base.py` 절 · `src/engine/strategies/CLAUDE.md` 각주 ⑨
```

사유: 청산 종류 열거, 대체 수단마다의 부작용(900초 「투자금 부족」 오귀인·일일 손실 래치·손절 정지), 「다른 모양」 예시(`"true"`·`1`)와 WARNING, `if key in strategy.config.params` 는 strategies 각주 ⑨ 와 engine `strategy_base.py` 절에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 체결통보 선행 race 가드

```
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존. 그 가드가 못 덮는 두 번째 창(PENDING `insert_trade` 의 `await` 도중 체결통보가 먼저 완주해 migration 029 부분 UNIQUE 를 위반 — 흡수하지 않으면 `execute_buy` 가 ERROR 로 끝나 스윙 폴의 `buy_succeeded` 후처리(매수 직후 HIGH 구독)가 빠진다)은 `_insert_pending_or_absorb_race(side=…)` 가 **`_completed_orders` 에 그 주문번호가 있을 때만** `UniqueViolationError` 를 흡수·discard 해서 막는다. 증거 없는 위반은 그대로 전파한다(다른 원인 은폐 금지) — 무조건 삼키기·재시도 INSERT 로 바꾸지 않는다. 상세 = `src/engine/CLAUDE.md` `order_engine.py` 절 「체결통보 race 가드」
```

사유: 문장만 줄였다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 주문이 나간 뒤의 실패로 재발사 금지

```
- **주문이 나간 뒤의 실패로 재발사 금지 (cycle327·335)** — `place_order` 가 성공하면 그 주문은 이미 거래소에 있다. 그 뒤의 어떤 예외(UNIQUE 위반·DB 타임아웃·페일오버)도 **「발사 실패」가 아니므로** 재시도 루프로 되돌리지도, 발사 실패 정리 코드를 돌리지도 않는다. 매수·매도 4 경로는 축별 경계 래퍼(`_persist_buy_pending_after_send` · `_persist_sell_pending_after_send`)가 자체 `try/except Exception` 으로 닫고 `[buy_post_send_error]`/`[sell_post_send_error]`(유일한 관측 채널, **무cap ERROR**)를 남긴 뒤 정상 종료한다. 🔴 두 래퍼의 `except Exception` 을 **좁히지 않는다** — 좁히면 행위 회귀가 거의 전부 초록인 채로 새므로 구조 가드 `test_cycle328_sell_pending_helper.py::test_g328_3b`(두 축)가 유일한 방어다. 🔴 매도는 재시도 직전에 `strategy.state.positions.get(ticker)` 를 **재조회**해 포지션이 사라졌으면 `[sell_position_gone]` 후 중단한다(루프 밖 지역 참조 `pos` 는 체결 뒤에도 옛 수량이라 **이미 판 것을 다시 판다**). 🔴 매수는 `pending_buys`/`pending_buy_amounts` 를 **풀지 않는다** — 접수된 매수는 KIS 가 이미 묶은 자금이고, 풀면 같은 종목 재매수와 전략 예산 이중 사용이 열린다. 피라미딩 착수 시 선결 = `pending_buy_amounts` 키를 `(ticker, order_no)` 로 바꾸는 것이다(지금은 `ticker` 단일 키라 같은 종목 두 번째 주문이 첫 번째를 덮는다). 상세 = `src/engine/CLAUDE.md` 「접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2」 절
```

사유: 예외 예시(UNIQUE 위반·DB 타임아웃·페일오버), 재조회 대상(`strategy.state.positions.get(ticker)`)과 지역 참조 `pos` 가 이미 판 것을 다시 판다는 이유, 묶인 자금을 풀 때의 부작용 전체는 engine 「접수 후 PENDING 영속화」 절과 `order_engine.py` 절에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 체결통보 주문수량은 3단 출처

```
- **체결통보 주문수량은 3단 출처 (cycle329)** — `await place_order` 가 걸린 동안 주문번호 매핑이 비어 있어, 그 창에 착지한 통보는 `ordered_qty` 가 증분 체결량으로 폴백돼 **부분 체결이 전량으로 오판**된다. 그래서 `map`(`_order_qty`) → `payload`(체결통보 `fields[16] ODER_QTY`) → `increment`(현행 폴백) 순으로 읽는다. 🔴 **전량 판정에 출처 게이트를 걸지 않는다**(걸면 수동 전량 매도가 유보돼 `_selling` 좀비 = 손절 마비) · 🔴 **재주문 타이머는 `qty_src=="map"` 일 때만**(`_cancel_and_reorder` 는 취소를 조건 없이 낸다 — 게이트가 없으면 **사람이 낸 주문을 30초 뒤 취소하고 다시 낸다**) · 🔴 **체결수량 소스 `fields[9]` 는 무접촉**(그 오독이 257720 사고, `test_cycle235_ast_execution_qty.py` 봉인). 상세 = `src/engine/CLAUDE.md` 「체결통보 주문수량 — 출처 3단 (cycle329)」 절
```

사유: 오판 경로 설명(`ordered_qty` 가 증분 체결량으로 폴백)은 engine 「체결통보 주문수량」 절에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 매도 체결은 두 축으로 판정한다

```
- **매도 체결은 두 축으로 판정한다 (cycle385 — 사용자 결정 2026-09-26·27, 분할 매도 허용)** — `_handle_sell_fill` 의 **주문 축**(`total_filled >= ordered_qty`)은 장부·매핑·타이머·`_selling` 을 정하고, **보유 축**(`pos.quantity` 에서 체결량을 빼고 0 이 됐나)은 포지션 삭제·`delete_position`·`on_position_closed`·`sold_today`·구독 해제를 정한다. 지키는 불변식 셋 = **추적 밖 실보유 0** · **우리 주문 합 ≤ 추적 수량**(운영자가 따로 산 몫은 팔지 않는다) · **안 잠긴 추적 잔여는 팔 수 있어야 한다**. 🔴 **보유 축에도 출처 게이트를 걸지 않는다** · 🔴 **주문이 끝나면 `_selling` 을 푼다 — 보유가 남아도 조건 없이 푼다**(남기면 잔여 보유의 손절이 멈춘다) · 🔴 표식을 되돌려도 되는 「안 걸렸다」는 `order_engine._sell_not_placed_reason(exc)` 한 곳이 가른다 — APBK0400 수량 초과 · 장운영시간 외 · 시장가 불가만이다. 그 밖의 `KisApiError`(EGW00201 · 모르는 코드)와 전송 예외는 그 증거가 아니다(`src/api/base.py::_request` 가 주문 POST 도 재전송해 앞 전송이 접수됐을 수 있다) · 🔴 #1.5 재대조와 늦은 체결통보는 같은 체결을 두 번 빼지 않는다 · 🔴 외부 매도가 일부를 잠가도 안 잠긴 추적 잔여는 판다(`fire = sellable − (held − eff)` 가 1 이상이면 그 수량만, 0 이하이거나 주문 목록을 못 믿으면 동결) · 🔴 걸린 매도가 없어도 미통보 체결이 추적 전부를 덮으면 보류한다(`[sell_qty_unnoticed_fills]`) · 🔴 `execute_sell` 의 발사·매핑·PENDING 수량은 루프 상단에서 잡은 `send_qty` 하나다 · 🔴 소유 전략은 registry 전수 보유자로 찾는다(`registry.get(sid)` 로 좁히면 `"momentum"` 기본값 함정) · 🔴 손절 잔여 재주문은 발사 직전 보유를 다시 보고 `min(remaining, 보유)` 만 낸다(보유 0 이면 내지 않고 `_selling` 을 푼다 · 재조회가 모호하거나 실패하면 `remaining` 그대로 · 수동 매도 라우트 주문(`_manual_sell_orders`)은 보유와 무관하게 `remaining`). 조건·예외·알려진 한계의 정본 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축 (cycle385)」 절
```

사유: 「안 걸렸다」 세 분류(APBK0400·장운영시간 외·시장가 불가)와 그 밖 예외(EGW00201·재전송 가능성), #1.5 재대조 크레딧, `fire = sellable − (held − eff)` 부분 잠김, `[sell_qty_unnoticed_fills]` 보류, `send_qty`, 잔여 재주문 `min(remaining, 보유)`·`_manual_sell_orders` 는 engine 「매도 체결」 절에 같은 조건으로 있다(grep 확인). 소유 전략을 registry 전수 보유자로 찾는 금기(`registry.get(sid)` = `"momentum"` 기본값 함정)도 같은 절 「소유 전략」 항목에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 관리종목(51)·단기과열(59) 보유 청산

```
- **관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단 (cycle369 — 사용자 결정 2026-09-25·26)** — 보유 종목(꺼진 전략 포함)을 REST 전용 플래그 `mang_issu_cls_code`·`short_over_yn` 으로 읽어, KRX 정규장 **09:00:30~15:28** 안에서 `Y` 면 시장가로 판다(종목당 하루 3회). 🔴 창 밖 발사 금지 — 창은 발사 직전에 한 번 더 본다(16:00~20:00 애프터는 단기과열종목을 거래 대상에서 빼 거부·포기 래치가 난다). 🔴 **매도는 종목상태 코드 51·59 폴백만으로 쏘지 않는다** — 그 코드는 정상 ETF·스팩·우선주에도 붙는다(매수 차단은 폴백도 쓴다). 🔴 판정에 `ssts_hot_yn`(공매도과열)·`short_over_cls_code`(예고)·`stock_master` DB 값을 쓰지 않는다. 🔴 **보유 종목 구독은 끊지 않는다** — 「재구독 중지」 를 글자대로 구현하면 청산 거부 시 손절이 눈을 감는다. 신규 매수는 공통 게이트 `StrategyBase._account_soft_gate_blocked` **첫 문장**이 막는다(못 읽으면 막지 않는다 · 수량 0 반환으로 막지 않는다). 킬스위치 `system_config.status_exit_mode`·`status_buy_block_mode`(키 없음 = `enforce` · 모양이 틀린 행 = `observe` · DB 조회 실패 = 직전 값), 즉시 반영 = `PUT /api/integrations/status-exit`. ⚠️ 발사 창은 고정 시계라 특별 개장일(지연 개장)을 모른다 — 그날은 개장 전에 `sell_mode` 를 `off`/`observe` 로 내린다. 상세 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절
```

사유: 발사 직전 창 재확인, 매수 차단 게이트 자리(`_account_soft_gate_blocked` 첫 문장)·폴백 사용·못 읽으면 막지 않음, 킬스위치의 모양 오류 = `observe`·조회 실패 = 직전 값, 판정 금지 필드의 뜻(공매도과열·예고)은 engine 「종목상태 청산·당일 매수 차단」 절에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — NXT 매도 거부 좀비 차단

```
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection`(APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB)를 보존하고 `_selling` 을 **discard** 하고 재시도를 멈춘다(`_selling` 을 보존하면 그게 곧 stale `_selling` 좀비 = 손절 마비다 — 이후 차단은 진입 게이트 `SellRejectionTracker.is_blocked()` 가 맡는다). `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. 진입 게이트는 **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL(일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL(동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 가 `OrderEngine.reset_daily_state()` → `_sell_rejection.reset_daily()` 로 함께 비운다. 구현(호환 property·분류 헬퍼) = `src/engine/CLAUDE.md` `order_engine.py` 절 · `src/api/CLAUDE.md` 「KIS 거부 응답 분류 헬퍼」 절
```

사유: 문장만 줄였다. TTL 값은 그대로다.

### 핵심 안전 규칙 (절대 깨지 말 것) — KIS 거부 응답 영구 저장

```
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget. 접수 **뒤** 거래소가 거부한 주문은 REST 응답이 아니라 체결통보 채널의 접수 전문으로 오고, `[order_rejected_notice]` WARNING 으로 남는다(기록만 · 개인정보 칸 제외 — 상세 `src/realtime/CLAUDE.md` 「접수 전문 기록」)
```

사유: 기록 필드(path/tr_id/msg_cd/msg1 + body 주요 키)와 접수 전문 기록 규칙(기록만 · 개인정보 칸 제외)은 `src/api/CLAUDE.md` 와 `src/realtime/CLAUDE.md` 「접수 전문 기록」 에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — WebSocket 시세 보유·익일청산 우선 보장

```
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
```

사유: 문장만 줄였다.

### 핵심 안전 규칙 (절대 깨지 말 것) — WebSocket 다중 안전망

```
- **WebSocket 다중 안전망** — F1(재연결 후 검증) + `_scan_loop`(5분) + K stale watcher(120s) + `_resubscribe_stale_priority`(5분 우선) **4중**을 단일 복구로 대체하지 않는다. K stale watcher 의 재등록은 보유·`_pending_next_day_clear` = HIGH + `bypass=True`, 그 외 후보 = LOW + `bypass=False`(메인 편중 차단). 재시도 횟수·cooldown·시간당 cap = `src/engine/CLAUDE.md` `scheduler.py` 절 `_stale_watcher_loop()` · 구조 단순화 금기 = `src/realtime/CLAUDE.md` 「안전 규칙 (멀티 세션)」 절 · `_subscriptions` 정합성 가드(orphan ACK race 차단) = `src/realtime/CLAUDE.md` 「subscribe / 거절 감지 / ACK 추적」 절
```

사유: 문장만 줄였다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 세션 단위 silent inactive 자동 reconnect

```
- **세션 단위 silent inactive 자동 reconnect** — `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2)` + `subscribed_count >= 5` + 5분 지속이면 `_ws.close()` 로 강제 재연결한다. 시간당 세션당 2회 cap(LMS/앱키 정지 위험 차단). 판정 가능 세션(`subscribed >= 5`)이 2개 이상이고 **그 전부**가 침묵이면 세션 고장이 아니라 **시장 침묵**으로 보고 그 사이클을 기각하고 판정 가능 전 라벨의 `first_seen` 을 pop 한다(누적 후 필터 금지 — 시장 재개 순간 지각 세션이 즉발한다). 다른 세션이 하나라도 fresh 거나 판정 가능 세션이 2 미만이면 현행대로 발화한다(fail-open — 결과 집합 ⊆ 현행). 🔴 **시장 침묵 기각에 시간창 리터럴(08:30/15:20)·`tradable_boards`·`session` import 를 쓰지 않는다** — 세션 간 비교만이 마감 흡수 구간의 갭까지 닫는다(AST G-241-5). 기각 관측 = `[silent_inactive_market_wide_skip]`. 상세 = `src/engine/CLAUDE.md` 모듈 맵 `stale_session_recovery.py` · `scheduler.py` 절
```

사유: fail-open 조건(다른 세션 하나라도 fresh·판정 가능 세션 < 2 → 현행, 결과 집합 ⊆ 현행)은 engine 모듈 맵 `stale_session_recovery.py` 와 `scheduler.py` 절에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 무송출(no_feed) 종목

```
- **무송출(no_feed) 종목은 K stale watcher 가 재등록하지 않는다 (cycle252)** — SUBSCRIBE 가 SUCCESS ACK 를 받아도 체결 프레임이 영구 0 인 종목은 재등록 가치가 0 이라, `stale_watcher_core.check_and_resubscribe_stale` 이 `no_feed_registry`(**fail-open** — 조회 예외·미지 종목이면 현행 그대로)로 **LOW no_feed 종목의 SEND·스탬프·force_retry history 만** 건너뛴다. `_stale_retry_count` 는 계속 올린다(r>5 홀드 — `stale_universe_guard` 의 저유동 축출 경로 보존). **HIGH(보유·익일청산) 경로는 byte 동일**하다 — 가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 손절 커버리지이기 때문이다. 대신 `[no_feed_held]` WARNING 1회/일이 "보유 종목이 WS blind" 를 남긴다. 금기 = no_feed 를 stale 집계에서 **빼서** 숫자를 좋게 만드는 것, HIGH 를 skip 에 넣는 것, 관측 헬퍼가 예외를 전파해 HIGH 재등록 사이클을 끊는 것. ⚠️ 이 마커들과 `[tick_coverage] stale` 의 의미는 2026-09-14 배포 전후로 다르다 — **그 전후 로그를 합산하지 않는다**. 상세 = `src/engine/CLAUDE.md` 모듈 맵 `stale_watcher_core.py` · 채널 리졸버·킬스위치 = `src/realtime/CLAUDE.md` 「시세 채널 — 시간축 전환 + 프리 창 속성축 보정」 절
```

사유: 무송출 정의 문장과 `_stale_retry_count` 를 계속 올리는 이유(`stale_universe_guard` 저유동 축출 보존)는 engine 모듈 맵 `stale_watcher_core.py` ③ 항목에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 전제 — NXT 종목은 전부 KRX 상장

```
- 🔴 **전제 — 넥스트트레이드(NXT)에서 거래되는 종목은 전부 KRX 상장 종목이다.** NXT 는 대체거래소(ATS)라 **자체 상장이 없다**. 그래서 `nxt_tradable` 은 「이 종목이 어디에 상장돼 있나」가 **아니라** 「KRX **에 더해** NXT 에서도 거래되나」다(정의 = `cptt_trad_tr_psbl_yn=="Y" ∧ nxt_tr_stop_yn=="N"`, `api/condition.py::inquire_stock_basics`). 따라서 `nxt_tradable=False` 는 **「KRX 전용」**이지 「어디서도 못 산다」가 아니고, 그 종목도 09:00~20:00 KRX 정규장·애프터에서 정상 매매된다. 「NXT 미상장」·「NXT 에만 있는 종목」 같은 말은 쓰지 않는다 — 실재하지 않는 상태다.
```

사유: 문장만 줄였다.

### 핵심 안전 규칙 (절대 깨지 말 것) — NXT 시세 채널은 프리장 전용

```
- **NXT 시세 채널은 프리장(08:00~09:00) 전용이다** — 리졸버 `scanner._resolve_channel` 은 시각축이 KRX 창을 주면 속성축을 **호출하지 않는다**. 그래서 **09:00~20:00 은 `nxt_tradable` 과 무관하게 전 종목이 `H0STCNT0`** 이고, `nxt_tradable` 이 채널을 가르는 구간은 프리 창 하나뿐이다(자동 원복 래치가 선 날은 예외). 전환은 하루 **1회**(`pre_to_krx`). 프리 창의 채널 선택을 걷으면 그 한 시간의 KRX 프레임만 잃고 정규장 시세·매수 평가에는 닿지 않는다. 리졸버 구조 = `src/engine/CLAUDE.md` 「모듈 맵」 「시세 채널 (통합 채널 소멸 후)」 · 채널 규칙 = `src/realtime/CLAUDE.md` 「시세 채널 — 시간축 전환 + 프리 창 속성축 보정」 절
```

사유: 「프리 창 채널 선택을 걷으면 그 한 시간의 KRX 프레임만 잃는다」 는 바로 아래 `nxt_tradable` 항목 ③ 과 같은 문장이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — nxt_tradable 용도

```
- **`nxt_tradable` 은 「어느 거래소로 보낼까」 에만 쓴다 — 「살까 말까」 에는 쓰지 않는다 (사이클 156 Q0 · cycle336 원복)** — 후보를 `list_by_filter` 로 뽑는 6전략은 전부 `nxt_tradable=None`(코드 기본값)이고(momentum 은 `list_by_filter` 를 쓰지 않는다 · `src/engine/strategies/CLAUDE.md` 「prepare 공통」), `risk.on_tick` 의 매수 평가에도 코호트 게이트가 **없다**. cycle293 이 `if chan_buy_blocked: continue` 로 그 기준을 다른 계층에서 되살렸던 것을 cycle336 이 걷었다. **되살리지 마라.** 🔴 반대로 **남겨야 하는 세 배선**은 전부 주문·청산 쪽이고, 걷었을 때의 대가가 서로 다르다: ① `order_engine._probe_nxt_downgrade_base`(NXT **거래대상이 아닌** 종목에 NXT 주문 = 거부, 게다가 **KRX 애프터 44/41 청산 변환의 전제**다) ② `scheduler` 익일청산 KRX 예약(걷으면 08:00 프리장 NXT 시장가가 `APBK0918` 거부 → 다음 09:00 TTL 로 그날 청산이 잠긴다) ③ 프리장 시세 채널 선택(걷으면 **프리 창 한 시간의 KRX 프레임만** 잃는다 — ①②와 달리 청산이 깨지지 않고, 그 창의 유일한 청산 소비자는 LTV 다). 판정 함수 `_tick_buy_eval_blocked_by_channel` 는 계측기로 남아 `[tick_buy_gate]` 분모와 `_note_pre_window_krx_frame` 게이팅에 쓰인다
```

사유: cycle293 게이트 재도입·cycle336 철거 경위를 이관했다. 계측기 용도(`[tick_buy_gate]` 분모·`_note_pre_window_krx_frame`)는 `src/realtime/CLAUDE.md` 「시세 채널」 절 매수 축 행에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — stale universe 가드

```
- **stale universe 가드** — `_evaluate_universe_guard`: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목을 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO. 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지). 상세 = `src/engine/CLAUDE.md` `scheduler.py` 절
```

사유: `_universe_excluded_today` 등록과 마커 레벨은 engine `scheduler.py` 절에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — trade_history 중복 INSERT 차단

```
- **`trade_history` 중복 INSERT 차단** — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()` 사용 (dedupe 없음 + CANCELLED 제외). DB 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)`(migration 029) 이중 안전망. 기존 `get_today_buy_trades()` 의 ticker dedupe 는 포지션 복구용 — 절대 sync 중복 판정에 사용 금지(같은 ticker 의 다른 `order_no` 가 가려져 핑퐁 INSERT 가 난다). 상세 = `src/db/CLAUDE.md` 「trade_history.py — 거래 내역」 절
```

사유: 문장만 줄였다.

### 핵심 안전 규칙 (절대 깨지 말 것) — NXT 거래가능 사전 판별

```
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]`. `_boot()` eager 사전 갱신 (보유 + `_pending_next_day_clear` 합집합). 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)`
```

사유: 문장만 줄였다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 종목코드 형식 비대칭

```
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — 영숫자 코드(신주인수권 등)·7자리 ETN 코드 자동매매 차단 + 좀비 포지션 방지. 🔴 **이 규칙은 ETF 를 막지 못한다** — ETF 코드도 6자리 숫자다. ETF/ETN 매수 제외는 `src/engine/etf_like.py::is_etf_like` 가 맡는다 — 증권그룹코드 `scty_grp_id_cd ∈ {EF,EN,FE}` 우선, 코드가 없을 때만 이름 키워드 폴백(cycle380). 규약 = `src/engine/CLAUDE.md` 모듈 맵 `etf_like.py`
```

사유: 판정 순서(증권그룹코드 `scty_grp_id_cd ∈ {EF,EN,FE}` 우선, 코드가 없을 때만 이름 키워드 폴백)는 engine 모듈 맵 `etf_like.py` 항목에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 매수 수량은 전략 잔여 자금 기준

```
- **매수 수량은 전략 잔여 자금 기준** — 7 전략 `calc_buy_quantity()` 의 **모든 return** 이 `StrategyBase._apply_budget_limit()` 관문을 경유한다 (AST 가드 A-GATE). 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`. **관문 안의 순서가 계약이다**: 폴백(`_fallback_one_share`)·잔여 클램프 → `_apply_lot_units_cap`(K축, cycle242) → `[oversized_fallback]` 관측 → `_apply_ratio_notional_cap`(ρ축, cycle245) → `return`. ρ축을 관측 **앞**에 두면 차단된 랏의 ρ 관측이 `final_qty < 1` 로 통째로 사라지고, K축 **앞**에 두면 조기탈출로 cycle242 마커 3종이 사라진다. 관문 안에서 `await`/DB/HTTP **절대 금지**(AST A-PURE) — `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(AST 가드 A-ATOMIC)이 원자성의 전제이고, 이게 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다. 관측 emit 은 예외를 흡수하고 **행위는 cap 밖**이다(관측 실패가 매수 수량을 바꾸면 안 된다). 관문 반환 타입은 **`int`** 여야 한다(float 이면 `api/order.py` 가 `ORD_QTY="2.0"` 을 KIS 로 보낸다). 터틀 4전략의 시장 유닛 분기는 관문 **앞**이라 관문 본문·순서는 그대로다. 헬퍼·마커·가드 = `src/engine/CLAUDE.md` `strategy_base.py` 절
```

사유: 순서를 바꿨을 때 무엇이 사라지는지(ρ축 관측 `final_qty < 1`·K축 마커 3종)와 시장 유닛 분기가 관문 앞이라는 사실은 engine `strategy_base.py` 절과 strategies 「자금관리」 절에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — API 인증은 조용히 꺼지지 않는다

```
- **API 인증은 조용히 꺼지지 않는다 (cycle243)** — `ApiAuthMiddleware` 는 **최외곽**(`MetricsMiddleware` 보다 바깥, starlette 는 마지막 `add_middleware` 가 가장 바깥)에서 `/health` 를 뺀 **전 경로**를 `X-API-Key` 로 지킨다. `API_AUTH_KEY` 미설정·빈 문자열·비교 예외는 전부 **401(fail-closed)** — fail-open 은 "키가 없으면 인증이 사라진다" 는 뜻이라 금지다(매매 엔진은 in-process 라 API 가 잠겨도 매매 영향 0, 대시보드만 멈춘다). 금기 = (a) `/api` 접두사 스코프로 좁히기(`/docs`·`/openapi.json` 이 열린다) (b) 프로덕션 코드에 테스트 우회 플래그 두기 — 테스트는 모듈 전역 `authorize` 를 monkeypatch 하는 seam **하나**만 쓴다(`tests/conftest.py::_neutralize_api_auth` + 옵트아웃 마커 `real_api_auth`) (c) `API_ALLOWED_ORIGINS=*` — 와일드카드는 코드가 **버리고 경고**한다(CORS credentialed preflight 전면 개방 + CSRF Origin 검사 무력화가 한 값에 동시에 딸려온다) (d) 개발 예외·개발용 기본키(커밋된 기본키는 공격자가 프로덕션에 가장 먼저 시도할 값) — dev 는 vite proxy 가 서버 측에서 `X-API-Key`·`Origin` 을 넣어 산다. 상태변경(POST/PUT/PATCH/DELETE)은 Origin 검사 추가(부재는 허용 = curl 비상 매도 경로 보존). **알려진 한계 = 단일 공유 키**(감사 추적 없음). **리포터 스코프(cycle249)** — `authorize()` 가 운영 키 판정 **뒤**에 리포터 키(`API_REPORTER_KEY`)를 본다: GET/HEAD 는 경로 무관 통과, `POST /api/log-reports/{date}/external` 정확 경로만 통과, 그 외는 유일하게 **403**(`reporter_scope`, 다른 사유는 전부 401). 스코프는 요청 헤더가 아니라 nginx `map $remote_user` 가 고르는 **Basic 사용자**에서 나온다(`location /api/` 가 클라이언트 헤더를 무조건 치환하므로 "루틴이 스코프 키를 보낸다"는 설계는 성립하지 않는다)
```

사유: 상태변경 Origin 검사(부재 허용 = curl 비상 경로)와 「알려진 한계 = 단일 공유 키」 는 `src/routes/CLAUDE.md` 「인증 — deny-by-default」 절에 있다. 기본키 금지 이유(커밋된 기본키는 공격자의 첫 시도 값)를 이관했다. 금기 (a)~(d)·리포터 스코프의 정본은 여전히 이 항목이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 비중 단위 추론 변환 금지

```
- **비중 단위 추론 변환 금지** — 전략 비중은 **어느 계층에서도 값 크기로 단위를 추측하지 않는다**. 폐기된 `v / 100 if v > 1 else v`(라우트)와 `totalW <= 1.01 ? round(w*100) : round(w)`(프론트 로드)는 1%(정수 `1`)를 100%로 저장하고 그 오염을 "균등분배" 화면으로 **위장**했다 — 추론 분기는 오염 시에만 깨어나므로 결함이 아니라 결함 은폐 장치다. 단위는 계약으로 고정(비율 0.0~1.0)하고 위반은 조용히 흡수하지 말고 422 / `success=false` 로 **시끄럽게 거부**한다. AST 가드 = `tests/unit/ast/test_ast_weight_no_magnitude_heuristic.py`(`update_weights` 내 `IfExp` · `/ 100` 0건, Σ 가드가 저장보다 선행 + 사이에 early return) + `frontend/src/components/__tests__/_ast_weight_unit_guard.test.ts`(`Settings.tsx` 내 `1.01` 리터럴 · `Math.round(s.weight)` 0건)
```

사유: 폐기된 두 분기의 원문(라우트·프론트 `totalW <= 1.01 ? …`)과 가드가 세는 것(`IfExp`·`/ 100`·`1.01`·`Math.round(s.weight)`, Σ 가드 선행)을 이관했다. 가드 조건은 가드 파일 자체가 정본이다.

### 핵심 안전 규칙 (절대 깨지 말 것) — 터틀 ATR 손절 게이트

```
- **터틀 ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 로 게이팅 금지. DB 토글 하나로 **기보유 포지션의 손절 규약**이 바뀌면 안 된다. position_ratio 매수는 미스탬프라 기존 % 손절 경로를 byte 동일하게 탄다. 스탬프 값은 반드시 sizing 에 쓴 ATR 과 동일(커플링 불변식). 이 금기는 **청산** 규약이다 — 진입 사이징(`calc_buy_quantity`·`max_lot_units` 캡)이 `sizing_mode` 로 분기하는 것은 충돌이 아니다. **재시작 복구의 재도출은 그 전략이 지금 `sizing_mode="turtle"` 일 때만 한다**(`StrategyBase._entry_atr_rederive_allowed`, AST 가드 G6) — 되살리면 고정% 손절이 ATR 손절+% 받침선으로 넓어진다. ⚠️ 랏별 사이징 기록이 없어 **보유 중 `sizing_mode` 를 바꾸면 기보유분이 새 설정의 손절을 탄다** — 전환은 그 전략 보유 0 에서 한다. 상세 = `src/engine/strategies/CLAUDE.md` 「자금관리 — 사이징 방식 × 손절 기준 매트릭스」 절
```

사유: 「position_ratio 매수는 미스탬프라 % 손절」 과 재도출을 막는 이유(고정% 손절이 넓어짐)는 strategies 「자금관리」 절 「ATR 손절 게이트」 항목에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — tradable_boards 는 매수 진입 전용

```
- **`tradable_boards` 는 매수 진입 전용 (명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동(`risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입). **유일한 예외 = NXT 프리장(08:00~09:00) 청산 평가 보류 게이트**(2026-08-06 사용자 결정, `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 화이트리스트 = LTV 만) — 프리장 왜곡 틱의 허깨비 손절·트레일링 고점 오염을 차단하고 09:00 KRX 시세로 재평가한다. **평가 보류이지 주문 보류가 아니다**(주문만 보류하면 허깨비 신호가 09:00 실매도로 전환). 게이트는 `tradable_boards` 가 아니라 **명시 상수**로 판정(AST 가드) — 매수 목적 보드 변경이 청산 규약을 바꾸는 커플링 차단. LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")` (사용자 의도 — 연속 상한가 익일 청산 + 야간 매수). 프리장 매도의 지정가 사전 변환 = `src/engine/CLAUDE.md` 「risk.py」·「order_engine.py」 절
```

사유: 트레일링 고점 오염 언급, 명시 상수의 이유(매수 보드 변경이 청산 규약을 바꾸는 커플링 차단), LTV 보드 사용자 의도(연속 상한가 익일 청산 + 야간 매수), 프리장 매도 지정가 사전 변환은 engine 「risk.py」·「order_engine.py」 절과 strategies 문서에 있다.

### 핵심 안전 규칙 (절대 깨지 말 것) — VB·LTV main 목표가 기준가

```
- **VB·LTV `main` 목표가 기준가 = KRX REST 단일 출처 (cycle272 — 사용자 결정 D1)** — `board=="main"` 목표가는 WS 세션 시가(KRX 확정 시가와 어긋난다) 대신 **KRX REST `stck_oprc`(`J`) 만** 기준가로 삼는다. 좁은 목 `on_open_price_confirmed(..., board="main", *, source="ws")` 의 `source` 신뢰 목록은 `("rest",)` 뿐이고 기본값이 불신 `"ws"` 라 WS 확정 경로는 조용히 거부된다. 프린트 안 된 종목은 그 시점 매수 불가. 킬스위치 `open_price_scope_mode`(전략별 `DEFAULT_PARAMS`, 기본 `"enforce"`, `"off"` 만 롤백 — `PARAM_RANGES`/`INT_PARAMS` 편입 금지). `pre_nxt`/`post_nxt` 보드는 게이트 스코프 밖 — LTV 08:00~09:00 프리장·야간 매수 무접촉. REST 확보 일정 = `src/engine/CLAUDE.md` 모듈 맵 `open_price_rest.py` · 상세 = `src/engine/strategies/CLAUDE.md` 각주 ③
```

사유: 문장만 줄였다.

### DB 스키마 (AWS RDS PostgreSQL) — DB 스키마 — llm_buy_evaluations 행

```
| `llm_buy_evaluations` | AI 매수평가(LLM shadow)를 주문 발화 시점에 기록 (migration 043) — 주문 1건 = 1행(성공·실패 모두). 열 정의 정본 = `src/db/CLAUDE.md` 「llm_buy_evaluations.py — AI 매수평가 기록」 절 |
```

사유: 문장만 줄였다.

### DB 스키마 (AWS RDS PostgreSQL) — DB 스키마 — UI 동기화 의무

```
> **`stock_master` / `stock_master_daily` UI 동기화 의무**: `stock_master` 컬럼 / `raw` JSONB 키 / `stock_master_daily` 컬럼을 추가하면 UI 에 노출한다 — 전략이 종목마스터 데이터를 참고하는 시점부터 새로 수집한 데이터는 UI 노출 의무다. 절차 = `frontend/CLAUDE.md` 「(6) 신규 데이터 추가 시 UI 동기화 절차 (영구 가드)」 절.
```

사유: 「전략이 종목마스터 데이터를 참고하는 시점부터 …」 는 frontend 「(6) 신규 데이터 추가 시 UI 동기화 절차」 첫 문단에 같은 문장이 있다.

### Docker / 배포 — 토큰 캐시 영속화

```
- **토큰 캐시 영속화**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨 양쪽 compose 동일 마운트. KIS `/oauth2/tokenP` 분당 1개 한도 + 컨테이너 재기동 시 토큰 24h 유효 보존. `.gitignore` 등록 (`.token_cache/` + 구 `.token_cache_quote_*.json` 호환). 구 경로 `.token_cache.json` 존재 시 자동 마이그레이션
```

사유: 문장만 줄였다.

### Docker / 배포 — `.token_cache` 빌드 시점 권한 보장

```
- **`.token_cache` 빌드 시점 권한 보장**: `Dockerfile` prod 스테이지가 `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `USER appuser` 순서. 호스트 bind mount 가 root:root 로 생성되어 `appuser` 가 쓰기 거부되던 결함 영구 차단 (회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py`)
```

사유: 문장만 줄였다.

### Docker / 배포 — frontend/nginx.conf.template

```
- `frontend/nginx.conf.template`: 정적파일 + `/api` → backend:8000 프록시 + **사이트 전체 Basic Auth**(cycle243). `nginx:alpine` 엔트리포인트가 `/etc/nginx/templates/*.template` → `/etc/nginx/conf.d/` 로 envsubst 렌더(`NGINX_ENVSUBST_FILTER=^API_(AUTH|REPORTER)_KEY$` 로 치환 변수 2개 제한). `map $remote_user $api_key_for_user { default "${API_AUTH_KEY}"; reporter "${API_REPORTER_KEY}"; }` 가 http 컨텍스트(server 블록 밖·앞)에서 Basic 사용자별 키를 고르고, `location /api/` 는 `proxy_set_header X-API-Key $api_key_for_user;` 로 그 결과를 주입한다(치환 구문은 `map` 블록 안에만 둔다). 자격 파일은 호스트 `./secrets/.htpasswd` bind mount(**git 커밋 금지**). ⚠️ 권한: nginx worker 는 컨테이너 안 **uid 101(nginx)** 이고 호스트 파일은 `ubuntu`(uid 1000) 소유라 `chmod 600`·디렉터리 `chmod 700` 이면 전면 500 이다 → `chmod 755 secrets` + `chmod 644 secrets/.htpasswd`. 결손 진단 3갈래 — **무자격은 어떤 상태에서도 401**(정상과 동일 = 무자격 curl 로는 결손을 판별할 수 없다) / 자격 + 파일 부재 → **403** / 자격 + 권한 거부 → **500**. `auth_basic off;` 는 이 템플릿에 **절대 쓰지 않는다** — 한 줄로 Basic Auth 와 백엔드 X-API-Key 주입이 동시에 뚫린다(AST 가드 D-1-b). 구 `frontend/nginx.conf` 를 되살리지 않는다(인증 없는 구버전이 조용히 서빙되는 fail-open)
```

사유: 권한의 이유(worker uid 101 vs 호스트 uid 1000)와 결손 진단 3갈래(무자격 401 / 파일 부재 403 / 권한 거부 500)는 `README.md` 「배포 전 호스트 준비 (하드 게이트)」 절에 같은 내용이 있다. 금기·map 계약은 그대로다.

### Docker / 배포 — 자동 배포

```
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + **선택적 재빌드**(`.github/workflows/deploy.yml` → `tools/deploy/compose_up_changed.sh`, cycle248). push 시각 → pool_start 지연 1~5분(backend 가 재생성될 때만). deploy.yml 은 push 후 `supabase/migrations/*.sql` 을 EC2 psql 로 순차 적용 (`SUPABASE_DB_URL` secret — **이름은 유지하되 값이 RDS DSN**, graceful skip)
```

사유: 다음 줄 「GitHub Secrets」 를 합쳤다.

### Docker / 배포 — GitHub Secrets

```
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `SUPABASE_DB_URL` (값=RDS DSN)
```

사유: 위 「자동 배포」 줄에 합쳤다.

### Docker / 배포 — 선택적 배포 (cycle248)

```
- **선택적 배포 (cycle248)** — `tools/deploy/compose_up_changed.sh` 가 **마지막 성공 배포 SHA 마커**(`.deployed_sha`, git 밖)와 HEAD 의 누적 diff 로 모드를 고른다. **full**(`src/`·`requirements.txt`·`Dockerfile`·`docker-compose.prod.yml`·`.dockerignore`·`deploy.yml`·`tools/deploy/` 중 하나라도 변경 → `up --build` = **backend 재시작**) / **선택 배포**(backend 축 무변경 + `frontend/`·`tools/ops/tls_stage2/`·`macro/` 중 변경된 축만 → `up --build --no-deps <서비스…>`, backend 무접촉. 모드 이름이 곧 서비스 목록이다 — `frontend` · `macro` · `frontend+macro`) / **none**(그 외 tests·`tools/test_impact`·`pyproject.toml` 등 또는 마커==HEAD 재실행 → 빌드 없는 `up -d`). 판정 불가(마커 없음·미지 SHA·diff 실패)는 전부 **full**(fail-safe). backend 히트가 하나라도 있으면 그 즉시 full 로 확정되므로 **backend 가 선택 목록에 들어갈 길은 구조적으로 없다**. 마커는 compose 성공 뒤에만 쓴다. 분류의 근거는 루트 Dockerfile COPY 소스가 `requirements.txt`·`src/` 뿐이라는 구성적 사실(가드 D-8)이고, `test_cycle248_deploy_pipeline.py::G-248-2` 가 COPY 소스 ↔ 정규식 정합을 강제한다(COPY 를 늘리면 붉어진다)
```

사유: 모드별 변경 경로 목록(full 축 `src/`·`requirements.txt`·`Dockerfile`·`docker-compose.prod.yml`·`.dockerignore`·`deploy.yml`·`tools/deploy/` / 선택 축 `frontend/`·`tools/ops/tls_stage2/`·`macro/` / none = tests·`tools/test_impact`·`pyproject.toml` 등)은 `README.md` 「선택적 배포 (cycle248)」 표에 있다.

### Docker / 배포 — 배포 모드 함정 넷

```
- ⚠️ 배포 모드 함정 넷: (a) `**.md`·`docs/**`·`_workspace/**` 만 바꾼 push 는 CI `paths-ignore` 로 **CI/Deploy 자체가 뜨지 않는다**(마커는 다음 배포의 누적 diff 가 따라잡는다) (b) `src/**` 는 이미지 입력이지만 **`src/` 안 `.md` 는 예외다** — `IMAGE_EXCLUDED_RE='^src/.*\.md$'`(`tools/deploy/compose_up_changed.sh`)가 backend 히트에서 `grep -vE` 로 2단 덜어내므로 **`src/engine/CLAUDE.md` 만 바꾼 push 는 full 이 아니다**. 두 파일이 갈라지지 않게 `tests/unit/ast/test_cycle322_image_excluded_paths.py` 가 묶는다. 🔴 `.*\.md$` 로 넓히지 않는다 — `tools/deploy/` 축이 흔들린다 (c) `.env` 는 git 밖이라 스크립트가 못 본다 — 손댄 뒤에는 운영자가 `docker compose up -d` 로 직접 재생성하고 **마커는 건드리지 않는다**(마커는 git SHA 의 배포 상태만 뜻한다) (d) none 모드의 `up -d` 도 `.env` 등 구성이 어긋나 있으면 재생성한다(none ≠ 무조건 무재시작)
```

사유: 문장만 줄였다.

### Docker / 배포 — 배포 모드 사전 확인

```
- 배포 모드 사전 확인 = push **전** 로컬에서 `git diff --name-only <EC2 .deployed_sha 값> HEAD` 의 경로를 위 규칙에 대보는 것(EC2 dry-run 은 이미 pull 된 HEAD 만 본다). EC2 에서는 `DEPLOY_DRY_RUN=1 bash tools/deploy/compose_up_changed.sh`(docker 미호출·마커 미기록, `true` 동치·미지 값 exit 2). **EC2 에서 git 을 손으로 움직였거나(reset/checkout/revert/stash) 수동 `docker compose build|up --build` 를 했으면 `rm ~/auto_stock/.deployed_sha`** — 마커는 git SHA 의 배포 상태만 뜻하고 실행 중 이미지와 대조하지 않는다. 직전 배포가 중간에 죽으면 `.deployed_sha.attempt` 가 남아 다음 배포가 자동으로 full 이다
```

사유: 사전 확인 절차(EC2 dry-run 은 이미 pull 된 HEAD 만 본다 · docker 미호출·마커 미기록 · `true` 동치·미지 값 exit 2)와 `.deployed_sha.attempt` 가 남으면 다음 배포가 full 이라는 사실은 `README.md` 「선택적 배포」·「수동 배포」 절에 있다(exit 2·`true` 동치는 스크립트 자체가 정본).

### Docker / 배포 — TLS

```
- **TLS — `auto.dkstock.cloud` 2단계 가동 중**. 80 은 **301** 로 https 로 보내고, 443 은 Basic Auth + HSTS `max-age=86400`(includeSubDomains·preload 없음). ACME HTTP-01 챌린지 location(`^~ /.well-known/acme-challenge/`, `satisfy any; allow all; root /var/www/certbot;`)만 301 밖이다. 스위치는 호스트 마커 파일 2개(git 밖) — `.tls_enabled`(1단계 = `docker-compose.tls.yml` + `frontend/nginx.tls.conf.template`) · `.tls_stage2`(2단계 = `docker-compose.tls2.yml` 이 `tools/ops/tls_stage2/` 스니펫을 마운트). 켜고 끄는 것은 `tools/ops/tls_enable.sh` · `tools/ops/tls_stage2_enable.sh` 이고, 사후 검증에 실패하면 두 스크립트가 **마커 삭제 + 이전 단계 원복까지 스스로 실행**한다. `compose_up_changed.sh` 는 마커가 있을 때만 `-f` 오버레이를 덧붙이고 **모드 판정에는 개입하지 않는다**(개입하면 TLS 를 켠 날부터 모든 배포가 backend 재시작이 되어 cycle248 이 없앤 비용이 부활한다). 인증서 갱신은 `certonly --deploy-hook` 으로 renewal conf 에 영속돼 snap/apt timer 가 돌린다 — **crontab 을 두지 않는다**(ubuntu crontab 은 `/etc/letsencrypt` 쓰기 불가, 상대경로 compose 는 cron cwd 에서 실패). 🔴 **TLS 템플릿에 `map` 을 중복 정의하지 않는다** — nginx 는 **정상 기동**하고 뒤에 include 되는 map 이 조용히 이겨 모든 사용자의 `X-API-Key` 가 빈 값이 된다(무증상 backend 전면 401). 텍스트 가드 G-255-2f 가 유일한 방어다. `auth_basic off;` 금지는 여기서도 불변(D-1-b). **Basic 자격 회전은 `tools/ops/rotate_basic_auth.sh` 로 한다**(실행 이력은 워크리스트) — 301 은 서버가 자격을 요구하지 않게 할 뿐 브라우저가 선제로 보내는 옛 자격까지 막지 못한다. 새 비밀번호는 화면에 찍지 않고 `secrets/.rotated-<ts>`(권한 600) 로만 전달되므로, 운영자가 그 값을 클라우드 루틴의 `REPORTER_BASIC_PASSWORD` 에 넣고 브라우저를 재로그인해야 회전이 끝난다
```

사유: 켜고 끄는 스크립트 동작(사후 검증 실패 시 마커 삭제 + 이전 단계 원복)·회전 산출물(`secrets/.rotated-<ts>`, 권한 600, 화면 출력 없음)은 `README.md` 「TLS (HTTPS)」 절에 있다. 301 이 옛 자격을 막지 못한다는 회전 동기, 「실행 이력은 워크리스트」, crontab 금지의 둘째 이유(상대경로 compose 의 cron cwd 실패)를 이관했다. `auth_basic off;` 금지(D-1-b)는 바로 위 `frontend/nginx.conf.template` 항목과 같은 금기다.

### Docker / 배포 — EC2 사전 생성 규약

```
- ⚠️ EC2 사전 생성 규약: `~/auto_stock/secrets/` 와 `~/auto_stock/certbot-www/` 는 **사람이 먼저 만든다**. compose 의 bind mount 가 먼저 만들면 root:root 가 되어 `ubuntu` 가 쓸 수 없다(`.token_cache` root 소유 사고와 같은 계열)
```

사유: 「`.token_cache` root 소유 사고와 같은 계열」 꼬리를 뺐다.

### Docker / 배포 — 프로세스 분리 1단계 = llm_worker

```
- **프로세스 분리 1단계 = `llm_worker` 컨테이너**(AI 매수평가를 분리, 큐로 쓸 대상은 신규 브로커가 아니라 `llm_buy_evaluations` 테이블 = migration 043). **아직 코드가 없다** — 배포 모드는 full / 선택 배포(`frontend`·`macro`·`frontend+macro`) / none 이고 미지 모드는 `exit 2` 다. 착수 시 제약 둘 — (a) `llm_worker` 는 `docker-compose.prod.yml` **본체**에 정의한다(오버레이에만 두면 그 오버레이를 안 붙이는 `full`·`none` 배포의 `--remove-orphans` 가 돌던 워커를 orphan 으로 삭제한다) (b) 워커 코드를 `src/` 아래 그대로 두면 워커 전용 변경도 `full` 로 분류돼 backend 가 재시작된다(`BACKEND_RE` 첫 대안이 `src/`). 2~4단계 도식과 보류 근거의 파일:행 인용 = [`docs/architecture.md`](docs/architecture.md) 15장
```

사유: 현재 배포 모드 목록·미지 모드 `exit 2`·「신규 브로커가 아니다」·migration 043 은 같은 파일 「선택적 배포」 항목·DB 스키마 표와 `docs/architecture.md` 15장에 있다.

### Docker / 배포 — 운영 가이드

```
- 운영 가이드 — **보유 포지션이 있으면 KRX 메인 시간(09:00~15:30) push(=EC2 자동 배포) 금지**(cycle232 D6): 재시작 1~5분 tick blind 동안 손절 사각 + `_scan_loop` 5분 race. 보유 0이면 빈번한 push 자제 수준. **20:00~21:35 도 피한다**(cycle283 D8 — 20:00 AI 자문 · 20:05 metrics 1차 스냅샷 · 20:30 일봉 적재 · 21:30 정산/`_reset_daily_state`. 그 창의 재기동은 `TIME_SESSION_START_CUTOFF`(20:00)에 막혀 그날 저녁 블록 전체(20:30 일봉 적재 · `_settle()` · 일일 로그 분석 · 로그 retention)가 통째로 결손된다. `[daily_head_stale]` WARNING 이 다음 아침 `_boot()` 에서 일봉 결손을 알리고, 복구 절차 3종은 `src/routes/CLAUDE.md` 의 `/api/trading/restart` 행에 있다). **16:00~20:00 은 KRX 애프터마켓 실시간 연속체결**, **08:00~08:50 은 NXT 프리장** — 둘 다 실매매 구간이라 재시작이 같은 tick blind 를 만든다. 즉 장외 배포 창은 **15:30~16:00 · 21:35~익일 07:45** 와 주말·공휴일이다. 이 금지는 backend 가 재생성되는 push(full 모드)에만 실질 적용되지만, **어느 모드인지 확신이 없으면 full 로 간주**한다(`tools/deploy/` 나 `deploy.yml` 이 섞인 커밋은 항상 full)
```

사유: 문장만 줄였다. 두 창 문자열과 「20:00~21:35 도 피한다」 머리말은 그대로다.

### 디렉토리 역할 — 디렉토리 역할 — src/api/

```
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). `quotation.py::inquire_ccnl(ticker, market='J')` — FHKST01010300 주식현재가 체결, output[0] + today_volume 합산 + graceful None (stale universe 가드용)
```

사유: `inquire_ccnl` 시그니처·TR(`FHKST01010300`)·반환 규약은 `src/api/CLAUDE.md` 「quotation.py — 주식현재가 체결」 절에 있다.

### 디렉토리 역할 — 디렉토리 역할 — src/engine/

```
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 21:30 일일 분석(cycle283 D3) / `daily_metrics_snapshot.py` 20:05 metrics 1차 스냅샷 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
```

사유: 「(cycle283 D3)」 꼬리를 뺐다.

### 디렉토리 역할 — 디렉토리 역할 — src/services/

```
- `src/services/` — 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `macro_client.py` 매크로 레짐 — 우리 `macro` 컨테이너를 평문 GET 으로 부른다, 인증 없음 / `quote_session_health.py` 보조 세션 health monitor / `exceptions.py`). 전용 CLAUDE.md 없음 — 목록 정본 = `src/CLAUDE.md` 「진입점」 절
```

사유: 문장만 줄였다.

### 디렉토리 역할 — 디렉토리 역할 — macro/

```
- `macro/` — **매크로 API 별도 컨테이너** (경기사이클·투자체제·금리차·하이일드·환율·원자재 5섹션 = `GET /api/macro/*`). 자체 `Dockerfile`·`requirements.txt`(pandas/numpy/yfinance)·`main.py` 를 갖고 매매 이미지와 완전 분리된다 — **`src/` 아래로 옮기지 않는다**(옮기면 macro 변경마다 매매 backend 가 재시작된다). `macro/macro_lite/` 는 stock-manager 추출 패키지의 **무수정 vendor** 라 재이식 시 통째로 덮어쓴다. 캐시는 `MACRO_LITE_CACHE_DIR` 영속 bind mount 필수(FRED 가 OAS 를 3년치만 주므로 누적 store 가 유실되면 하이일드 **차트**의 10년·5년 구간이 3년으로 영구 퇴행). **매매 레짐의 출처이기도 하다**(cycle315) — `src/engine/market_regime.py` 가 `src/services/macro_client.py` 로 이 컨테이너를 부른다. 다만 매크로 레짐은 **관찰 지표**라 매수를 차단·축소하지 않는다. 운영 가이드 = [`docs/macro-lite.md`](docs/macro-lite.md)
```

사유: 섹션 이름 목록·의존성(pandas/numpy/yfinance)·stock-manager 출처·FRED 3년 사정은 `docs/macro-lite.md` 에 있다.

### 2026-10-02 압축 2차 — 검증 지적으로 정본에 되살린 것

위 이관 기록의 사유 중 아래 항목은 사실과 달라, 해당 규칙·조건을 정본에 되살렸다(이관 원문은 위에 그대로 둔다).

- TLS 항목의 `auth_basic off;` 금지 — 남은 nginx 항목이 「이 템플릿」 으로 한정돼 TLS 템플릿이 빠졌다. nginx 항목을 두 템플릿(`nginx.conf.template`·`nginx.tls.conf.template`)으로 넓혔다.
- 배포 모드 사전 확인 — 「push 전에 아는 길은 로컬 diff 하나, EC2 dry-run 은 pull 된 HEAD 만 본다」 는 한정이 README 에 없었다. 정본에 되살렸다.
- API 인증 — 「fail-open … 뜻이라 **금지**다」 의 금지어를 되살렸다.
- 보유 전략 끄기 금지 — apply 경로는 비중만 거부하고 파라미터는 진행한다는 한정, PUT params 가 `enabled`·하한선과 무관하다는 근거를 되살렸다. 「하한선 검증은 두 경로에 모두 있다」 는 되살리지 않았다 — `src/routes/recommendations.py` 에는 비중 0 가드만 있고 하한선 검증이 없다(`src/routes/CLAUDE.md` apply 절과 일치).
- 운영 가이드(20:00~21:35) — 「20:00 AI 자문」·「`_reset_daily_state`」 와 「재기동 시점 이후의」 한정을 되살렸다.
- NXT 사후 보강 `upsert_one` — NXT/SOR 주문의 프리장(08:00~08:50) 거부일 때만 · KRX 거부엔 쓰지 않는다는 조건을 붙였다.
- 배포 함정 (a) — 「마커는 다음 배포의 누적 diff 가 따라잡는다」 를 되살렸다.
- nginx 렌더 경로(`/etc/nginx/templates/*.template` → `/etc/nginx/conf.d/`)와 map 자리 한정(server 블록 밖·앞)을 되살렸다.
- `[priority_drop]` — 「INFO + WARNING `system_logs`」 를 되살리고 링크를 `src/engine/CLAUDE.md` `scanner.py` 절로 고쳤다.
- 매도 재조회 — `strategy.state.positions.get(ticker)` 와 이유(옛 `pos` 로 이미 판 것을 다시 판다)를 되살리고 `order_engine.py` 절 링크를 더했다.
- 코호트 게이트 — 금지 패턴 식별자 `if chan_buy_blocked: continue` 를 되살렸다.
- ρ축 — 「K_ρ 도 리스크 정체성 상수」 분류를 되살렸다.

### 2026-10-02 cycle393 — `[no_feed_held]` 거짓 경보 판정 시정 (사용자 결정 7)

종전(cycle252~357) 판정식은 `no_feed_high = {t ∈ high_tickers : is_no_feed(t)}` 하나였다.
`is_no_feed` 는 `stock_master.nxt_tradable == False`(KRX 전용) **정적 집합**뿐이라 프레임
수신 여부를 보지 않았고, KRX 전용 보유 종목을 하나라도 들고 있으면 09:00 뒤 첫 사이클에
**반드시** 떴다 — 운영 `system_logs` 30일 실측 5회(09-28 09:01:24 · 09-29 09:00:18 ·
09-29 16:02:30(재기동 후 cap 초기화, 애프터마켓) · 09-30 09:01:53 · 10-01 09:01:50).

10-01 운영 재조회로 반증 — 대상 4종목(003490·232140·417200·425040) 전부가 마커(09:01:50)
보다 먼저 MAIN 체결 틱을 받았다(417200 09:00:06 · 003490 09:00:18 · 425040 09:00:22 ·
232140 09:00:29, 425040 `[day_high_adopted]` 09:00:31) — 거짓 경보였다. 메시지 문구
「KRX 채널인데 WS 프레임 0(연속체결 미수신)」·「REST 폴(… 09:05~15:20)」도 당시 이미
낡아 있었다(실제 보유 폴 시작 = `SWING_REST_POLL_EARLY_START` 09:00:30).

시정 = 판정을 "측정했을 때만 말한다"로 바꿨다 — W(오늘 WS 체결 기록 부재,
`tick_volume.get_observed_acml_vol`) + R(구독 중 KRX 누적거래량 증가, `inquire_acml_vol`
을 600초 간격 두 번 읽어 확인 + 60초 더 대기) 두 증거 다리가 모두 서야 확정한다.
상세 규약 = `src/engine/CLAUDE.md` `stale_watcher_core.py` 절(현재형).

---

## Docker / 배포

### 2026-10-08 cycle412 문서 동기화 — 선택 배포 모드 일반화 · CI migration 범위

정본 원문(바뀐 부분):

```
/ **선택 배포**(`frontend` · `macro` · `frontend+macro` — `--no-deps`, backend 무접촉) / **none**
```

```
(`tests/integration/pg_harness.py` 가 migration 001~045 적용)
```

경위: cycle412(거래일지 1a)가 `journal` 축(`JOURNAL_RE='^journal_worker/'` → 서비스
`journal_worker`)을 더하면서 `tools/deploy/compose_up_changed.sh` 가 걸린 축을 `frontend`·
`macro`·`journal` 순서로 `+` 로 잇는 일반 조합으로 바뀌었다. 고정 3모드 나열은 그것을 담지
못한다. CI 의 migration 범위는 047(거래일지 4표)까지다 — 046(cycle409)이 들어올 때 이 줄이
고쳐지지 않아 두 번호가 함께 밀려 있었다.

같은 동기화에서 덧붙인 것(걷어낸 원문 없음) = 「Docker / 배포」 의 `journal_worker` 항목 ·
EC2 사전 생성 규약의 `secrets/journal_worker.env` 문장(`env_file` 결손이 compose 명령 전체를
실패시킨다 — 로컬 compose v5.1.1 실측) · `llm_worker` 항목의 선례 문장 · DB 스키마 표
`trade_journal_*` 행 · 디렉토리 역할 `journal_worker/` 행 · `API_REPORTER_KEY` 의 워커 직결
문장 · 테스트 실행 주석 둘(워커 테스트 포함 · 영향 인덱스 범위).

→ CHANGELOG: cycle412 행

### 2026-10-09 cycle412 마무리 문서 동기화 — `journal_worker` 한 회전에 대사 · 과거분 적재 · `TZ`

정본 원문(「Docker / 배포」 `journal_worker` 항목의 바뀐 부분):

```
15초 한 회전 = G0 `GET /api/trading/status?include=system,holdings,strategies` → G1 `GET /api/balance/exit-lines` → `./logs:/app/logs:ro` 꼬리 읽기 → 주문 행·손절선 사건 쓰기 → 커서 저장(엔진 정지·`phase=="idle"` 이면 300초 주기에 쓰기 0). 환경변수는 `JOURNAL_DATABASE_URL`(`env_file: ./secrets/journal_worker.env`)·`API_REPORTER_KEY` 둘뿐이고 자원 상한은 `mem_limit: 160m`·`cpus: 0.25` 다.
```

경위: cycle412 보완(`17dbd16c`)이 대사(`jw/reconcile.py`)를 한 회전 끝에 60초 간격으로 연결하고
`python -m jw backfill <경로…>` 를 실제 적재로 만들었다. 원문은 그 전 코드라 대사 단계가 없었다.
`docker-compose.prod.yml` 의 `journal_worker` `environment` 에는 `TZ=Asia/Seoul` 도 있어 「둘뿐」 을
「`TZ` 말고는 둘뿐」 으로 고쳤다(워커 코드가 `os.environ` 에서 읽는 것은 여전히 둘이다).

→ CHANGELOG: cycle412 마무리 행
