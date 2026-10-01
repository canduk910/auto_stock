# 리팩토링 리뷰 — 2026-09-27 · 전략을 더하고 빼는 구조

> 요청: 사용자 결정(09-27) 1번 「피라미딩은 다른 방향으로 재검토 — 필요하면 후지모토·깡토 전략을 새로 추가해 재검토. 지금 구조가 전략 추가·삭제에 쉬운지 재평가하고 리팩토링까지 검토」.
> 성격: **읽기 전용 분석 + 권고 카드.** `src/`·`tests/`·`frontend/`·설정·DB 무수정, git 쓰기 0. 기준 커밋 `6a2fea44`.
> 표기: **[실측]** = 이 메모를 쓰며 돌린 명령·테스트 결과 / **[코드]** = 파일:줄을 읽은 사실 / **[추정]** = 위 둘에서 끌어낸 판단.

---

## 0. 결론 (10줄)

1. **매매 본선은 이미 레지스트리 구동이라 쉽다.** 틱 평가·청산·사이징 관문·라우트·대시보드 탭은 `registry.all()/enabled()` 를 돌 뿐 전략 이름을 모른다[코드].
2. **어려운 곳은 「배선」이다.** 어느 전략이 틱으로 평가되는지, 폴로 평가되는지, 무엇을 구독하는지, 언제 청산하는지가 전략 id 목록으로 `scheduler.py`(승인 대상)와 8영역에 흩어져 있다[코드].
3. **새 전략이 조용히 틀리는 길이 있다.** 표마다 기본값이 서로 다른 원형을 가정한다. 목록에만 안 넣으면 틱 평가는 되는데 구독이 안 돼 사실상 무매매가 된다. cycle48(BFB·VCP 0건)이 이 경로였다[코드].
4. **가짜 전략을 넣어 테스트를 돌렸다[실측].** 예산 관문을 우회하고, 계좌·종목상태 게이트가 없고, `position_ratio × max_positions = 2.0` 인 전략이 **이름 붙은 안전 가드(A-GATE·C-DEFAULT·cycle233 게이트) 셋을 전부 통과했다.** 붉어진 것은 전략 파일을 glob 으로 도는 가드 셋뿐이다.
5. **거꾸로, 제대로 베껴 만든 전략이 더 많이 붉어진다[실측]** — 엉성한 쪽 37건, momentum 을 그대로 베낀 쪽 47건. 「정확히 7파일」 같은 닫힌 세계 단언 때문이다.
6. **전략 하나 등록만으로 `scheduler.py` 핀 23건이 깨진다[실측].** 등록이 `scheduler.py` 안에 있어서다.
7. **빼는 쪽은 더 무겁다[실측].** VCP 하나를 빼면 515건이 실패하고 16개 교차 모듈이 import 부터 깨진다. 그중 VCP 이름이 붙은 테스트 파일은 8개뿐이다.
8. **DB 에 함정 하나[코드]** — 시드 행 없는 새 전략에 화면에서 파라미터를 한 번 저장하면, `save_params` 가 `enabled=True, weight=0.5` 로 행을 만든다. 다음 재시작에 그 전략이 켜진다.
9. **권고 순서.** ① 테스트 쪽 명부부터 만들고 안전 가드를 거기로 돌린다(카드 #1, LOW). ② 새 전략용 오프라인 재현 틀을 `tools/replay/` 에 세운다(§7). ③ 후보가 재현 문턱을 넘은 뒤에만 등록·역할 분리(카드 #2·#3, `scheduler.py` 승인)를 한다.
10. **후지모토 1:2:6 은 새 전략 파일만으로는 못 돌린다[코드].** 같은 종목 추가 매수(`is_ticker_blocked_for_buy` 가 자기 보유도 막음), 부분 매도, 주문별 대기금액 키가 선결이다. 오프라인 재현은 지금도 된다.

---

## 1. 검토 범위·방법

- 범위: `src/` 전체에서 전략 id 문자열·목록·`hasattr/getattr` 훅, `supabase/migrations/`, `frontend/src/`, `tests/`(1,171 파일), 정본 문서.
- AST 스캔 [실측]: 7전략 id 중 5개 이상을 담은 리터럴 목록·dict 81곳(src 9 · tests 71 · tools 1). 스크립트 `scratchpad/find_lists.py`.
- **변이 실험 [실측]** — `git archive HEAD` 로 뜬 사본 4벌에서 `tests/unit + tests/contract`(12,688건)를 돌렸다.
  - **S0 기준**: 무수정. 실패 17건. 전부 git 이력을 읽는 가드라, 사본에 `.git` 이 없어서 생긴 것으로 본다[추정]. 네 시나리오 공통이라 차이 계산에서 뺐다.
  - **S1 엉성한 새 전략**: `probe_new.py` 를 추가했다. 규약을 일부러 어긴 전략이다.
    - `calc_buy_quantity` 가 관문 없이 수량을 바로 돌려준다.
    - `check_buy_signal` 에 게이트가 없고 늘 BUY 를 낸다.
    - `DEFAULT_PARAMS` 는 3키뿐이고, `position_ratio 0.5 × max_positions 4 = 2.0` 이다.
    - `scheduler.__init__` 에 등록만 했다(9줄).
  - **S2 베낀 새 전략**: `momentum.py` 를 클래스 이름만 바꿔 `probe_new.py` 로 복사했다. 등록은 S1 과 같다.
  - **S3 전략 제거**: `vcp_breakout.py` 를 지우고 import·등록 블록만 걷었다.
- 도메인 판단(후지모토·깡토의 매매 효과)은 이 메모의 범위가 아니다. 구조가 무엇을 막는지만 적는다.

---

## 2. 지금 전략 하나를 더하면 손대는 곳 — 전수표

「필수」 = 빠지면 매매가 틀리거나 조용히 멈춘다. 「부수」 = 빠져도 표시·관측만 나빠진다(기본값으로 굴러간다).

### 2.1 백엔드 `src/`

| # | 자리 | 무엇 | 필수/부수 | 빠지면 | 승인 |
|---|---|---|---|---|---|
| B1 | `src/engine/strategies/<new>.py` | `StrategyBase` 서브클래스. 추상 4개(`prepare`·`check_buy_signal`·`check_exit_signal`·`calc_buy_quantity`, `strategy_base.py:403-469`) + 문서 규약: 게이트 한 줄(`_account_soft_gate_blocked`, 폴·래치형은 첫 문장 / 엣지형은 발사 직전), 모든 return 이 `_apply_budget_limit` 경유, 보유형이면 `get_effective_stop_price` 미러, 멀티데이면 `_apply_high_since_buy_from_candles` | 필수 | — | 행위(새 매수 로직) |
| B2 | `scheduler.py:34-40` import · `:322-383` 등록 | 7개를 손으로 생성·등록. **등록 순서 = `risk.py:642` `for strategy in self.registry.enabled()` 평가 순서** = 같은 틱에 두 전략이 신호를 내면 먼저 사는 쪽 | 필수 | 전략이 존재하지 않음 | `scheduler.py` 승인 |
| B3 | `scheduler.py:1821-1826` `_collect_breakout_tickers` | 틱 평가 전략의 후보를 WebSocket 구독에 넣는 **유일한 경로**. 우선순위 = BFB→VCP→VB→LTV | 필수(틱형) | 틱 평가는 되는데 자기 후보가 구독되지 않아 사실상 무매매. cycle48 이 이 결함을 고쳤다(`:1803-1814` 독스트링) | 승인 |
| B4 | `scheduler.py:145` `_SWING_POLL_STRATEGIES` (사용처 `:788` `:1843` `:2309` `:2763` `:2887`) | 폴 매수 루프·REST 시세 폴·재시작 ATR 재계산·사전 prepare 재시도 | 필수(폴형) | 폴 매수 없음 | 승인 |
| B5 | `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES` | 폴형 전략의 틱 매수 평가 제외 | 필수(폴형) | 남이 구독한 종목의 틱에서 폴 대신 매수 평가가 돈다 | **8영역** |
| B6 | `scheduler.py:1389` 익일 청산 대상 · `:2038` 15:20 강제청산 대상 · `:782` `:1671` `:2624` 시가 목표가 확정 · `:2665` 빈 후보 재 prepare | 청산 일정·시가 기준 목표가 원형 | 원형에 따라 필수 | 그 원형 청산이 안 돈다 | 승인 |
| B7 | `strategy_base.py:75-77` `Position._MULTIDAY_STRATEGIES` | 멀티데이면 `is_next_day` 가 항상 False | 부수(배지 표시만 — `strategies/CLAUDE.md` BFB 절) | 주문 화면 「청산」 배지 오표시 | — |
| B8 | `strategy_base.py:45` `_ALWAYS_STATUS_GATE_CANDIDATE_SIDS` | 엣지형(발사 직전 게이트) 표지 | 부수(관측 카운트) | 차단 카운트가 전략 후보로 안 셈 | — |
| B9 | `status_exit_watch.py:75-80` `_GROUP` | 종목상태 매수 차단 선조회 우선순위 | 부수 | **기본값이 「스윙(3)」** 이라 틱형 새 전략도 P1 선조회에서 빠진다. P0 는 읽는다 | — |
| B10 | `session.py:75-84` `_DEFAULT_TRADABLE_BOARDS` | `tradable_boards` 키가 없을 때의 폴백. 4전략만 있다 | 부수(7전략 모두 키를 가짐) | 키도 없고 폴백도 없으면 `frozenset()` → `is_tradable` False → **조용한 무매매**(`session.py:112-121`, `risk.py:709`) | 8영역 |
| B11 | `boot_manager.py:494` BFB · `scheduler.py:2320` VCP `recompute_high_since_buy` | 재시작 뒤 트레일링 기준점 복구. 같은 훅이 두 파일에 있다 | 필수(보유형) | 재시작마다 기준점이 매수가로 리셋 | — / 승인 |
| B12 | `llm_buy_gate.py:481-493` `_BREAKOUT_LINE_KEYS` · `llm_features.py:493` `_STRATEGY_META` · `:610` `_NOT_APPLICABLE_NOTES` · `:662` `_SNAPSHOT_NA_KEYS` | AI 매수평가(기록 전용) 문맥 | 부수 | 빈 진입 규칙으로 채점. 점수가 잣대 오염 | — |
| B13 | `param_catalog.py:137-145` `STRATEGY_IDS` + 12 스펙의 `applies_to` + 새 키 스펙 + `CATALOG_VERSION` | 화면 편집 스키마 | 필수(편집 통로) | 새 키가 화면·PUT 에서 `unknown_key` | — |
| B14 | `funnel_capture.py:53-56` `_ORDER` | 저녁 캡처 순서 | 부수(미지 id 는 맨 뒤) | — | — |
| B15 | `open_price_rest.py:82` · `open_price_observe.py:101` · `position_exit_lines.py:58,75` · `pyramid_shadow.py:74` · `log_metrics_collector.py:719,796` · `backtest_orchestration.py:46,55` · `backtest_yaml.py:62-110` | 특정 전략 전용 관측·기능 | 해당 원형만 | — | — |
| B16 | `recommendation_engine.py:53` `PARAM_RANGES` · `:124` `INT_PARAMS` | AI 자동 튜닝 대상 키 | 부수(키 단위, 전략 무관) | 자동 튜닝 없음(안전 쪽) | — |

기본 전략을 가정하는 폴백도 있다. 전략을 **뺄 때** 이것이 문제가 된다(§4.6). 위치는 `boot_manager.py:293,335,416-444` · `scheduler.py:2362,2393,3442-3444` · `order_engine.py:2622,2854,2986,3084`(8영역) · `db/trade_history.py:92` · `models/trade.py:33` · `routes/trading.py:156`. 모두 `"momentum"` 으로 폴백한다[코드].

### 2.2 DB

| 자리 | 무엇 | 필수/부수 |
|---|---|---|
| `supabase/migrations/011_register_donchian_swing.sql`, `018_register_bull_flag_and_vcp.sql` 패턴 | `strategy_config` 시드 행(`enabled=false, weight=0, params='{}'`) | **필수** — 없으면 §4.5 함정. `kojiro` 는 시드 마이그레이션이 **없다**(grep 0). 운영 행이 어떻게 생겼는지는 이 메모에서 확인하지 않았다 |

### 2.3 프론트

| 자리 | 무엇 | 필수/부수 |
|---|---|---|
| `components/BalanceTable.tsx:12-17` `STRATEGY_NAMES` (**4개**) · `TradeHistoryGrid.tsx:112-119` (**6개**) · `TradePnLGrid.tsx:22-30` (7개) | 표시명 | 부수(없으면 id 원문) |
| `pages/StrategyFunnel.tsx:24-33` `STRATEGY_OPTIONS` | 깔때기 페이지 선택지 | 부수(없으면 선택 불가) |
| `types/strategy.ts:2-45` `STRATEGY_COLORS` · `utils/strategyInfo.ts:2-78` `STRATEGY_INFO` | 색·설명 | 부수(회색·없음) |
| `components/ScanMonitor.tsx:142-146` `FUNNEL_CONF` · `:272-283` `BREAKOUT_KEYS/LABELS` · `:313-316` 원형 분기 | 스캔 깔때기 패널 | 부수(패널 없음) |
| `tools/test_fixtures/gen_param_schema_fixture.py:34-42` → `frontend/src/test/fixtures/paramSchema.fixture.ts`, `e2e/fixtures/param-schema.fixture.ts` | 생성 픽스처 | 필수(생성기 재실행) |
| 대시보드 탭 `pages/Dashboard.tsx:23-24` | `Object.keys(strategies)` — **자동** | — |

### 2.4 테스트·가드

| 분류 | 개수 [실측] | 새 전략에 대한 태도 |
|---|---|---|
| 7전략 전부를 리터럴로 적은 테스트 파일 | 20 | **새 전략을 안 본다**(조용히 통과) |
| 5~6개 부분집합 리터럴 | 25 | 원형 범위 단언. 대부분 정당한 범위지만, 새 전략의 분류를 강제하지 않는다 |
| 전략 디렉터리 glob 순회 | 5곳(`test_cycle245_ast_ratio_notional_cap.py:90` G-245-6/7 · `test_cycle324_llm_gate_doc_truth.py:64` · `test_cycle274_ast_llm_gate.py:467` · `test_cycle297_ast_scope.py:130` · `test_cycle273e_ast_tick_buy_skip_constant.py:227`) | 새 전략을 **자동으로 본다** |
| 디렉터리 파일 명부 고정(`_ENGINE_PY_FILES`·`_PINNED_DIRS`·`_SRC_TREE_FILES`) | 5 테스트 | 새 파일이면 붉어짐(인지 강제) |
| `scheduler.py` sha·줄 수 핀 | 23 테스트 | 등록 한 줄에도 붉어짐 |

### 2.5 문서

- `src/engine/strategies/CLAUDE.md:238-243` 「새 전략 추가」 4단계. 시드 마이그레이션·구독 목록·폴 목록·카탈로그·프론트·가드가 **전부 빠져 있다**[코드].
- 루트 `CLAUDE.md` 「새 전략 추가」 4단계(같은 내용) · 전략 목록 1줄 · `_workspace/00_leader_trading_rules.md` 명세.
- 「7 전략」이라는 숫자가 정본 문서에 **64회** 나온다(루트 5 · README 9 · architecture 12 · engine 15 · strategies 9 · leader rules 10 · routes 2 · frontend 2)[실측 grep]. `src/` 주석에도 11파일 19회. 대부분 「7전략 전부 X 를 경유한다」 같은 불변식 문장이라, 여덟째 전략이 들어오면 **말없이 거짓**이 된다.

---

## 3. 실측 — 가짜 전략을 넣고 뺐을 때

### 3.1 S1(엉성) · S2(베낌) — 새로 붉어진 테스트 (S0 대비)

| 분류 | S1 | S2 | 내용 |
|---|---|---|---|
| `scheduler.py` sha·줄 수 핀 | 23 | 23 | 등록 9줄 때문. cycle274·276·278·282·286·287·290~298 의 「이번 사이클은 scheduler 무접촉」 증거 핀 |
| 디렉터리 명부 고정 | 5 | 5 | 새 파일 인지 강제 |
| **전략 내용을 본 가드(glob)** | **3** | 0 | G-245-6(`max_lot_ratio_mult` 없음) · G-245-7(return 이 관문 아님 — **예산 관문 우회는 이것이 우연히 잡았다**) · cycle324(`llm_gate_mode` 없음) |
| 닫힌 세계(「정확히 7」·「정확히 VB·LTV」·7전략 픽스처) | 5 | **18** | S2 에서 늘어난 13건 = 복사한 `llm_gate_*` 4키가 8번째 파일에 생겨서(cycle274 c10_3 · cycle276 c6_3a · cycle297 g2_1) + 복사한 `high_since_buy` 대입이 새 「소유자」로 잡혀서(cycle222a3 h1) |
| 영향 인덱스 신선도 | 1 | 1 | 재생성 필요 |
| **합계** | **37** | **47** | |

**S1 에서 붉어지지 않은 것(= 조용히 통과한 규약 위반)**:

- **A-GATE** — 모든 return 이 `_apply_budget_limit` 경유. `test_budget_limit_ast.py:33-41` `STRATEGY_FILES` 가 7개 고정 목록이다. 우회는 G-245-7 이 대신 잡았다(설계 의도 밖).
- **C-DEFAULT** — `position_ratio × max_positions ≤ 1.0`. 같은 파일 `:164-165`, 같은 고정 목록이다. **2.0 이 통과했다.** 부팅 때 `check_budget_invariant` 가 경고만 남기는 런타임 관찰은 있다.
- **cycle233 계좌·종목상태 게이트 위치** — `test_cycle233_ast_account_risk.py:28-33` `GATE_FIRST_FILES`/`GATE_PRE_BUY_FILES` 고정 목록이다. **게이트가 아예 없는 전략이 통과했다.**
- **예산 관문 행위 테스트** — `test_budget_limit_gate.py:39-47` `ALL_STRATEGIES` 고정 목록이다.
- **카탈로그 C1** — `test_cycle278_param_catalog.py:57-65` `_STRATEGY_META` 고정 목록이다. 새 전략이 새 키를 가져오면 카탈로그 누락이 보이지 않는다.

### 3.2 S3(VCP 제거)

- 새 실패 **515건 / 61파일** [실측]. 파일 이름에 `vcp` 가 들어간 것은 8개다. 나머지 53파일은 교차 테스트다. 가장 많은 곳은 `test_cycle278_param_catalog.py` 215건, `test_cycle290_killswitch_registration.py` 62건, `test_cycle300_daily_depth_switch.py` 22건이다.
- **import 부터 실패한 테스트 모듈 24개.** 그중 16개는 VCP 전용이 아니다. 예: `test_budget_limit_gate.py`, `test_kojiro_turtle_sizing.py`, `test_refactor_a5a6_atr_base.py`. 이 모듈들은 7전략 클래스를 전부 import 한다.
- 운영 코드는 멀쩡히 import 됐다. `registry.get("vcp_breakout")` 가 None 을 돌려주는 자리가 전부 방어돼 있다[실측·코드]. **제거 비용은 거의 전부 테스트와 DB 잔재(§4.6)에 있다.**

---

## 4. 구조 진단

### 4.1 쉬운 곳 (유지)

- `risk.on_tick`(`risk.py:642`) · `order_engine` · `StrategyBase._apply_budget_limit` 관문 · `routes/strategies.py`(`:74` `:153` `:211` `:262` `:371`) · 대시보드 탭. 전략 id 를 모르고 레지스트리만 돈다. `registry.all()/enabled()` 호출은 `src/` 21파일 61곳이다[실측 grep].
- `_load_strategy_config`(`scheduler.py:444-447`)는 등록 안 된 DB 행을 건너뛴다. 제거된 전략의 행이 남아도 부팅이 깨지지 않는다.

### 4.2 같은 사실이 여러 곳에 — 0계명 1순위

| 사실 | 적힌 곳 | 한쪽만 고치면 |
|---|---|---|
| 「donchian·kojiro 는 폴로 평가한다」 | `scheduler.py:145` · `risk.py:88`(8영역) · `status_exit_watch.py:75-80`(`_GROUP` 3 + 주석 「스윙 폴 훅이 덮는다」) | 폴에 넣고 `risk` 에 안 넣으면 틱에서도 매수 평가. `risk` 에만 넣으면 매수 경로 0 |
| 「BFB·VCP·VB·LTV 는 틱 구독으로 평가한다」 | `scheduler.py:1821-1826` · `:2665-2666` · `:1876-1918`(구독 출처 카운트 — `swing` 이 donchian 만 세고 kojiro 는 안 센다) · `status_exit_watch.py:76-77` · 프론트 `ScanMonitor.tsx:272-277` | 구독 목록에서 빠지면 무매매(cycle48) |
| 「VB·LTV 는 시가 기준 목표가」 | `scheduler.py:782` · `:1671` · `:2624` · `open_price_rest.py:82` · `open_price_observe.py:101` · `param_catalog.py:418` | 시가 확정·재시도·관측이 갈라진다 |
| 「보유 기준점 재계산 훅」 | `scheduler.py:2309-2315`(스윙) · `:2320-2325`(VCP) · `boot_manager.py:494-499`(BFB) | 같은 `recompute_high_since_buy` 가 두 파일에서 따로 불린다 |
| 전략 표시명 | `scheduler.py:327-381` `name=` · 프론트 3개 `STRATEGY_NAMES` · `StrategyFunnel.tsx:26-32` · `ScanMonitor.tsx:279-282` · `BreakoutCandidateMonitor.tsx:9-11` · 픽스처 생성기 `:34-42` | **donchian 이 세 이름이다** — 「20일 신고가 스윙」·「도치안 스윙」·「돈치안 스윙」. BFB 는 「눌림목 돌파」·「불플래그 돌파」, VCP 는 「변동성 수축 돌파」·「VCP 변동성 수축」·「VCP 돌파」[코드] |
| 공통 필수 키 12개 | 7파일 × 12 · 카탈로그 12 스펙의 `applies_to` · 키별 가드 4종 | [실측] 12키가 7전략 모두에 있다. 그중 8키는 **값까지 같다**(`after_market_exit_division`·`exchange`·`llm_gate_*` 4·`max_lot_ratio_mult`·`order_exchange_clock_mode`). 한 키 누락을 잡는 가드는 `max_lot_ratio_mult`·`llm_gate_mode` 둘뿐이다(glob) |

2회 이하인 사실은 그대로 둔다(3계명) — 「익일 청산 = momentum·LTV·VB」(`scheduler.py:1389` 한 곳), 「15:20 강제청산 = VB·LTV」(`:2038` 한 곳), 「엣지형 = momentum·VB」(`strategy_base.py:45` 한 곳 + 테스트).

### 4.3 기본값이 서로 다른 원형을 가정한다 — 조용한 실패의 뿌리

목록에 없는 전략을 각 표가 어떻게 다루는지를 모았다[코드].

| 표 | 목록에 없을 때 | 가정한 원형 |
|---|---|---|
| `risk.py:88` 틱 매수 평가 | 평가한다 | 틱형 |
| `scheduler.py:1821` 구독 | 구독 안 한다 | (어느 쪽도 아님) |
| `scheduler.py:145` 폴 | 폴 안 한다 | (어느 쪽도 아님) |
| `status_exit_watch.py:80` | 그룹 3 | 폴형 |
| `session.py:121` 보드 폴백 | 빈 집합 = 매수 불가 | (키가 있으면 무관) |
| `strategy_base.py:75` 멀티데이 | 아님 | 당일·익일형 |
| `scheduler.py:1389` 익일 청산 | 제외 | 멀티데이형 |

**등록만 한 새 틱형 전략**은 이렇게 된다. 틱에서 매수 평가는 받는다. 하지만 자기 후보는 구독되지 않아, 다른 전략이 우연히 구독한 종목에서만 산다. 가드는 이것을 못 잡는다. 표본이 0 이 아니라 「가끔」이라 발견이 늦다[추정]. cycle48 이 실제 사례다(`scheduler.py:1813` 「미포함 시 유니버스/임계 완화를 해도 BFB/VCP 0건 지속」).

### 4.4 가드가 새 전략을 못 보거나, 옳은 복사를 벌한다

- §3.1 대로, 이름 붙은 안전 가드 셋이 고정 목록이라 새 파일을 보지 않는다.
- 반대로 「정확히 7파일」·「정확히 VB·LTV」 단언은 규약을 지킨 복사를 벌한다. 이 단언들은 cycle297 이 LLM 게이트를 7전략으로 넓힌 뒤에도 이름에 「VB·LTV」가 남아 있다(`test_cycle274_ast_llm_gate.py` c10_3 · `test_cycle276_ast_order_hook.py` c6_3a).
- 결과적으로 **가드가 새 전략 작성자를 규약 위반 쪽으로 민다**(S1 37 < S2 47)[실측].

### 4.5 시드 행 없는 새 전략이 재시작에 켜진다

- `src/db/strategy_config.py:75-85` `save_params` 에서 행이 없으면 `await save(strategy_id, True, 0.5, params)` 를 호출한다[코드]. 이 줄은 첫 다중 전략 커밋 `c183f550`(2026-04-24)부터 있었다.
- 경로:
  1. 새 전략을 시드 없이 배포한다(코드 기본값 `enabled=False`).
  2. 화면에서 파라미터 하나를 저장한다(`routes/strategies.py:389`).
  3. DB 행이 `enabled=True, weight=0.5` 로 생긴다.
  4. 다음 재시작에 `_load_strategy_config`(`scheduler.py:448-449`)가 이 값을 적용한다.
  5. Σ 정규화 때문에 그 전략이 자금의 약 1/3 을 받는다(기존 Σ≈1.0 가정)[추정].
- 문서의 「새 전략 추가」 4단계에 시드 마이그레이션이 **없다**. 011·018 시드의 주석은 이 함정을 이유로 들지 않는다.
- 운영 DB 에 지금 7행이 모두 있으면 **오늘의 영향은 0** 이다. 이 메모는 DB 를 조회하지 않았다 → 확인 필요.

### 4.6 전략을 빼면 보유 포지션이 momentum 규약으로 넘어간다

- `boot_manager.py:293`: `target = registry.get(strategy_id) or registry.get("momentum")`. DB `positions.strategy_id` 가 등록되지 않은 전략이면 momentum 의 청산 규약을 탄다[코드]. momentum 의 규약은 익일 시가 갭 판정 뒤 청산, −7.5% 손절이다.
- 같은 폴백이 미체결 복구(`:416-444`), 잔고 동기화(`scheduler.py:3442-3444`), 체결통보 오귀속 방어(`order_engine.py:2622,2854,3084`, 8영역)에도 있다.
- 기존 금기(「보유 있는 전략을 끄지 않는다」)는 **끄기**만 다룬다. **코드에서 지우기**는 같은 위험을 재시작 뒤로 미룰 뿐, 문서 어디에도 없다.

### 4.7 부수 관찰 (카드 아님)

- `src/engine/strategy.py`(91줄)는 전략 이전의 단일 전략 모듈이다. `Signal`·`Position` 을 따로 갖는다. `src`·`tests`·`tools` 어디서도 import 하지 않는다[실측 grep]. AST 테스트 2개가 파일 경로로만 언급한다. 새 전략 작성자가 잘못된 `Signal` 을 import 할 여지가 있다. 삭제는 dead code 확정 절차(사이클 N회 관찰) 대상이라 여기서는 권고하지 않는다.

---

## 5. 추가 비용 추정 — 일봉 스윙형 전략 하나(후지모토·깡토류)

| 항목 | 지금 | 카드 #1~#5 이후 |
|---|---|---|
| 새 파일 | 1(전략) | 1(전략) |
| 기존 `src/` 수정 | 약 10파일: `scheduler.py`(등록·폴 목록·재계산 훅) · `risk.py:88`(8영역) · `strategy_base.py:76` · `status_exit_watch.py:75` · `param_catalog.py`(`STRATEGY_IDS` + 12 `applies_to` + 새 키) · `llm_features.py` 3표 · `llm_buy_gate.py` 1표 · (`boot_manager.py`) | 명부 1줄 + 카탈로그(새 키만) + `risk.py:88` 리터럴 1곳(카드 #3 선택지에 따라 0) |
| DB | 시드 마이그레이션 1(문서에 없음) | 1(체크리스트에 있음) |
| 프론트 | 약 7파일 + 픽스처 재생성 | 픽스처 재생성만(표시명은 API 에서) |
| 테스트 | S2 기준 47건 수선 + 고정 목록 20파일에 **손으로** 추가해야 안전 가드가 새 전략을 봄 | 명부가 분류를 요구하는 자리만 붉어짐(원형 분류 2~3건 예상[추정]) |
| 문서 | 표·명세 + 「7 전략」 64곳 중 불변식 문장 | 표·명세 |
| 승인 | `scheduler.py`(1) + `risk.py` 8영역(폴형이면 1) + 매수 로직 자체 | 매수 로직 자체(+ 폴형이면 `risk.py` 리터럴, §6 결정 3) |
| 규모 [추정] | 배선·가드만 TDD 사이클 1~1.5회. 전략 로직은 별도 | 배선 0.3회 수준 |

---

## 6. 권고 카드

순서는 권장 처리 순서다. **카드 #2·#3 은 실제로 붙일 후보가 §7 재현 문턱을 넘은 뒤에만** 권한다. 3계명(미래 가정으로 추상화하지 않는다)에 따른 것이다. 역할 목록은 이미 3회 이상 반복되지만, 그 비용은 전략을 더하거나 뺄 때만 실현된다.

### 카드 #1 — 테스트 쪽 전략 명부 하나 + 안전 가드를 그 명부로 돌린다

- **위험 등급**: LOW — `tests/` 만. `src/`·8영역 무접촉. 배포 모드 none.
- **현 상태**: 안전 가드 셋이 7개 고정 목록이다. `test_budget_limit_ast.py:33-41`(A-GATE `:122` · C-DEFAULT `:164`) · `test_cycle233_ast_account_risk.py:28-33` · `test_budget_limit_gate.py:39-47`. 카탈로그 대조는 `test_cycle278_param_catalog.py:57-65` · `tools/test_fixtures/gen_param_schema_fixture.py:34-42`. 닫힌 세계 단언은 cycle274 c10_3 · cycle276 c6_3a · cycle297 g2_1 · cycleF te 「all seven」 · contract `_INACTIVE_STRATEGY_IDS`.
- **권고**:
  ```
  tests/_strategy_census.py
    STRATEGY_FILES = sorted(p.name for p in strategies_dir.glob("*.py") if p.name != "__init__.py")
    STRATEGY_CLASSES = {sid: cls}   # 모듈 import → StrategyBase 서브클래스 탐색
    (자기 검사) len(STRATEGY_FILES) >= 7   # 탐지기 무효화 방지 — G-245-6 의 >= 7 관례
  A-GATE·C-DEFAULT·예산 관문 행위·카탈로그 C1 → parametrize(STRATEGY_FILES)
  cycle233 → 두 원형 목록은 그대로 두고 set(GATE_FIRST)|set(GATE_PRE_BUY) == set(STRATEGY_FILES) 단언 추가
            (새 파일은 「원형을 골라라」 메시지로 붉어진다)
  「정확히 7」 → 「명부 전부」
  ```
- **회귀 가드**: 바뀐 테스트 자신. **돌연변이 확인 필수** — §3.1 S1 전략을 다시 넣으면 A-GATE·C-DEFAULT·cycle233 이 붉어져야 한다. S2 의 닫힌 세계 13건은 초록이어야 한다.
- **예상 효과**: ① 새 전략이 안전 가드 3종을 조용히 빠져나가는 경로 3 → 0. ② 옳은 복사에 대한 거짓 붉음 18 → 0(S2 기준)[추정]. ③ 결합 상태 변화 없음(테스트만). ④ 7전략 고정 목록 20파일 중 안전 가드 5파일이 명부 하나로. (줄 수: 참고 생략)

### 카드 #2 — 등록 목록을 `scheduler.py` 밖 한 곳으로

- **위험 등급**: MEDIUM — `scheduler.py` 승인 대상(1회). 8영역 무접촉.
- **현 상태**: `scheduler.py:34-40` import 7줄 · `:322-383` 등록 62줄. 등록 순서가 `risk.py:642` 평가 순서다.
- **권고**:
  ```
  src/engine/strategies/manifest.py   # 순수 데이터 + 클래스 import 만
    STRATEGY_MANIFEST = (
      (MomentumStrategy, "momentum", "상한가 모멘텀", True, 1.0),
      (VolatilityBreakoutStrategy, "volatility_breakout", "변동성 돌파", False, 0.0),
      ... 현행 순서 그대로 7행
    )
  scheduler.__init__:
    for cls, sid, name, enabled, weight in STRATEGY_MANIFEST:
        self.registry.register(cls(StrategyConfig(strategy_id=sid, name=name, enabled=enabled, weight=weight)))
  ```
  카드 #1 명부와 `param_catalog.STRATEGY_IDS` 를 이 목록과 같다고 단언한다. 카탈로그는 「순수 데이터·src import 0」 설계라 리터럴을 유지하고 교차 검사만 건다.
- **회귀 가드**: Red 선작성 골든. `[(sid, name, enabled, weight, type(s).__name__) for s in TradingScheduler().registry.all()]` 이 현행 7행과 **순서까지** 같아야 한다. `scheduler.py` 핀 23건은 이 사이클이 한 번 갱신한다.
- **선행 의뢰**: 없음(행위 동일 증명이 골든 하나로 닫힌다).
- **예상 효과**: ① 전략 추가·삭제 시 `scheduler.py` 수정 1 → 0. S1·S2 의 핀 23건 원인이 사라진다. ② `scheduler.__init__` 의 관심사에서 「전략 목록」이 빠진다. ③ 없음. ④ 생성 블록 7회 반복 → 1. (참고: `scheduler.py` 약 −55줄 → 상한 3,900 여유 119 → 약 174)

### 카드 #3 — 원형(역할)을 전략이 선언하고, 배선 목록은 선언에서 뽑는다

- **위험 등급**: HIGH — 구독 우선순위·폴 순서·청산 일정 배선이 바뀐다. 행위를 같게 유지하는 것이 목표지만 영향면이 넓다.
- **현 상태**: §4.2 표의 첫 네 줄. §4.3 의 기본값 불일치.
- **권고**:
  ```
  StrategyBase (기본값 없음 — __init_subclass__ 에서 누락이면 TypeError: 새 전략이 원형을 고르게 강제)
    EVAL_DRIVER: ClassVar[str]              # "tick" | "swing_poll"
    TICK_SUBSCRIBE_RANK: ClassVar[int|None] # BFB 0 · VCP 1 · VB 2 · LTV 3 · 그 외 None
    OPEN_PRICE_TARGET: ClassVar[bool]       # VB·LTV
  scheduler: _SWING_POLL_STRATEGIES → _members("swing_poll") (등록 순서 보존)
             _collect_breakout_tickers / _reprepare_breakout_if_empty → rank 순
             :782 :1671 :2624 → OPEN_PRICE_TARGET
  8영역·리터럴 정책 목록은 건드리지 않고 교차 검사만:
    risk._TICK_BUY_EVAL_SKIP_STRATEGIES == {EVAL_DRIVER=="swing_poll"}
    Position._MULTIDAY_STRATEGIES (strategies/CLAUDE.md 「리터럴 정본」) ↔ 선언 대조
    status_exit_watch._GROUP ↔ 선언 대조
  ```
  구독 출처 카운트(`scheduler.py:1876-1918`)는 로그 서식(`vb=`·`ltv=`…)이 D+1 grep 계약이라 **이번 카드에서 빼고** 둔다.
- **회귀 가드**: Red 선작성. 파생 튜플이 현행 리터럴과 **순서까지** 같다는 골든 단언을 교체 전에 둔다. 기존 `test_cycle273e_ast_tick_buy_skip_constant.py` · cycle48 구독 테스트 · 스윙 폴 테스트를 유지한다.
- **선행 의뢰**: **domain-expert 행위 영향 평가**. 구독 우선순위(BFB·VCP head, 2026-08-08 사용자 결정)와 폴 순차성(같은 종목 이중 매수 차단)이 파생 뒤에도 같다는 것을 확인해야 한다.
- **예상 효과**: ① 「폴형」 사실 3파일 → 선언 1곳 + 교차 검사(한쪽만 고치면 붉어짐). 「틱 구독형」 `scheduler` 3자리 → 1곳. 「시가 목표가」 `scheduler` 3자리 → 1곳. ② 새 전략은 원형을 **고르지 않으면 로드되지 않는다**(§4.3 무매매 경로 차단). ③ 결합 상태 변화 없음. ④ 같은 id 목록 반복 3회 이상 × 3 사실 → 각 1.

### 카드 #4 — 공통 필수 키 12개를 명부 검사 하나로

- **위험 등급**: LOW — `tests/` + `param_catalog.py` 순수 데이터 별칭.
- **현 상태**: §4.2 마지막 줄. `tradable_boards` 누락은 조용한 무매매로 이어지는데(§2.1 B10) 이를 잡는 가드가 없다[코드 — S1 은 이 키를 넣었으므로 실측 대상이 아니었다].
- **권고**: `REQUIRED_COMMON_KEYS`(12키)를 카드 #1 명부로 glob 검사한다(각 파일 `DEFAULT_PARAMS` ⊇ 12키). 카탈로그의 12 스펙은 `applies_to=STRATEGY_IDS` 별칭으로 바꾼다. **값을 `StrategyBase` 로 끌어올리지는 않는다.** G-245-6 「각 파일이 선언」 정책, cycle290 킬스위치 「7 전략 전부의 `DEFAULT_PARAMS` 말미」 규약과 충돌한다.
- **회귀 가드**: `test_cycle278_param_catalog.py` 전부 + 돌연변이(키 하나 삭제 → 붉음).
- **예상 효과**: ① 새 전략 카탈로그 수정 13곳 → 1곳(`STRATEGY_IDS`). 키 누락 탐지 2/12 → 12/12. ② 없음. ③ 없음. ④ 키별 「정확히 7」 가드 4종 → 1.

### 카드 #5 — 프론트 표시명·색·설명을 한 곳에

- **위험 등급**: LOW — 프론트 표시만. 배포 모드 frontend(backend 무재시작).
- **현 상태**: §2.3 · §4.2 「표시명」 줄. BalanceTable 은 BFB·VCP·kojiro 를, TradeHistoryGrid 는 kojiro 를 id 원문으로 보여 준다[코드. 화면 실측은 안 함].
- **권고**: `frontend/src/utils/strategyMeta.ts` 하나(표시명·색·설명)를 둔다. 표시명은 `/api/strategies` 의 `name`(`strategy_registry.py:146`)을 우선하고 없으면 이 표를 쓴다. `StrategyFunnel` 선택지는 API 목록에서 만든다. 이름 하나를 정하는 것은 사용자 결정이다(§10 결정 5).
- **회귀 가드**: 기존 vitest(`TradePnLGrid.test.tsx`·`BalanceTable.sector.test.tsx`·`StrategyFunnel.*.test.tsx`) + 새 전략 id 가 들어오면 API 이름이 보이는지 한 건.
- **예상 효과**: ① 표시명 수정 자리 6곳 → 1곳. ② 없음. ③ 없음. ④ `STRATEGY_NAMES` 3벌 → 1.

### 카드 #6 — 추가·삭제 체크리스트를 코드에 맞춘다

- **위험 등급**: LOW — 문서. `/sync-docs` 경유.
- **권고**: `strategies/CLAUDE.md:238-243` 과 루트 「새 전략 추가」를 §2 필수 항목으로 다시 쓴다. 시드 마이그레이션, 원형 선택, 구독·폴, 카탈로그, 픽스처 재생성, 가드 분류가 들어간다. **「삭제」 절을 새로 둔다**: 보유 0 · 미체결 0 · `positions` 행 0 확인 뒤 제거하고, §4.6 폴백을 명시한다. 불변식 문장의 「7 전략 전부」는 「전 전략」으로 바꾸고, 숫자는 전략 표 한 곳에만 둔다(같은 사실을 두 문서에 적지 않는다).
- **예상 효과**: ① 체크리스트 누락 항목 6 → 0. 문서 숫자 64곳의 동기화 부담 → 전략 표 1곳.

### 행위 결함 — 리팩토링 밖(발의만, 별도 결정)

| # | 결함 | 등급 | 필요한 것 |
|---|---|---|---|
| D-1 | §4.5 `save_params` 가 행 없음을 `enabled=True, weight=0.5` 로 채운다 | HIGH(재시작 뒤 자금 배분이 바뀐다) | 운영 DB 7행 존재 확인 → 기본값을 `False, 0.0` 으로 바꾸는 건 행위 변경이라 승인 + domain-consult |
| D-2 | §4.6 미등록 전략의 보유가 momentum 규약으로 넘어간다 | HIGH(청산 규약 변경) | 규약을 먼저 정한다(momentum 유지 / 관찰 로그만 추가 / 부팅 거부). 관찰 로그 `[strategy_orphan_position]` 만이면 LOW. `order_engine` 자리는 8영역 |

---

## 7. 새 전략 오프라인 재현 틀 — 라이브 배선 전에 후보를 거르는 곳

### 7.1 지금 있는 것 [실측·코드]

| 조각 | 위치 | 재사용 |
|---|---|---|
| 5년 보관소 | `data/archive/krx_daily/` — json.gz(수정 OHLCV·거래대금) + parquet(그날 시총 `mktcap` 원 단위·`adj_factor`), 3,008종목, 상장폐지 포함. **ETF 없음**(KRX 주식 API) | 그대로 |
| 보관소 로더·유니버스 | `_workspace/domain_consult/cycle372_s0_archive_replay.py` `load_archive` · `series_from_daily` · 유니버스 ①today/②asof(시총 ≥ 500억) · `splits`·`regime_extras`·`pooled`·`breadth60`·`jump_flags` | 그대로 |
| 시계열·통계 | `cycle351_pyramid_s0_replay.py` `build_series`·`baseline`·`free_sim`·`summarize`·`ci_cluster`·`ci_iid`·`budgets`·`window_n` | 그대로 |
| 보관소+DB 이음·KOSPI 근사 지수 | 스크래치 `c375/c375_data*.py`(이음매 30% 초과 51종목 비율 보정, 시총 가중 지수 — 실제 KOSPI 와 3점 대조) | 이관 필요 |
| 4전략 대리 진입·1랏 기준선 | 스크래치 `c375/c375_entries.py`(542줄 — kojiro·donchian·BFB·VCP 를 numpy 로 **다시 구현**) | 이관 필요 |
| 종목 사이 크기 조절(연승·연패·시장 유닛) | 스크래치 `c375/c375_xbet.py` | 이관 필요 |
| 라이브·재현 공유 leaf 선례 | `src/engine/pyramid_shadow.py` — cycle372 가 파일 경로로 import | 패턴 |
| 전략 `prepare` 를 DB·KIS 없이 돌리는 선례 | `tests/unit/engine/strategies/_cycle364_harness.py` — `get_recent_daily_normalized`·`_scan_universe`·마스터 차단·`ticker_prev_close` 패치 | 패리티 단계에 사용 |

**지금 구조의 약점 [실측·추정]** — 재현은 매번 전략을 **다시 구현**한다. cycle375 의 ETF 157건 혼입은 이렇게 생겼다. 재현이 유니버스를 라이브(`scanner.ETF_KEYWORDS` 이름 필터, `kojiro.py:655-657`)와 따로 정의했다. 재구현이 늘수록 「재현이 잰 전략 ≠ 라이브 전략」 위험이 커진다.

### 7.2 새 전략용 틀의 요건

1. **자리**: `tools/replay/` 에 둔다. `src/` 밖이라 배포 모드가 none 이고 backend 가 재시작되지 않는다. `_workspace/` 는 문서 자리이고, 스크래치는 세션이 끝나면 사라진다.
2. **데이터 층** — `load_archive()`(5년) + DB 이음(최근 1년) + KOSPI 근사 지수. 입력 sha256 을 기록하고 난수 씨앗을 고정한다(cycle375 §9 관례).
3. **유니버스 층** — ①today/②asof 둘 다 돌린다(생존 편향 대조). **라이브 상수를 import 해서** 쓴다(`ETF_KEYWORDS`, 각 전략 `DEFAULT_PARAMS` 의 시총·거래대금 컷). 전략 모듈 import 에 필요한 환경변수는 `gen_param_schema_fixture.py` 처럼 더미로 준다.
4. **전략 층(순수 함수)** — 새 전략의 판정 핵심을 먼저 **순수 leaf** 로 쓴다(`pyramid_shadow` 패턴). 재현과 라이브가 같은 함수를 부르므로 동등성이 구성으로 보장된다.
   ```
   entries(series, ctx) -> [Entry(ticker, i_signal, i_fill, px_ref, N, meta)]
   manage(pos, bar, ctx) -> [Action("add"|"reduce"|"exit", qty_frac, px_rule, reason)]  # 분할 매수·부분 청산을 한 모델로
   size(entry, book, ctx) -> units                                                     # 연승·연패·시장 유닛 같은 종목 사이 크기 조절
   ```
   후지모토 1:2:6 은 `manage` 의 `add`·`reduce` 로, 깡토 점진적 베팅은 `size` 로 표현한다.
5. **집행 모델** — 신호 다음 봉 시가 체결, 갭 스킵·추격 상한(전략 파라미터), ±30% 가격제한, 비용(수수료·세금·슬리피지 인자).
6. **자금 층** — 시간순 포트폴리오 시뮬레이션. 예산·`max_positions`·`position_ratio` 를 쓰고, **정수 주 절삭(랏 기하)** 을 실제 순자산(약 500만) 기준으로 잰다. K축·ρ축 캡 산식은 새로 쓰지 않고 `turtle_sizing.compute_unit_qty` 를 재사용한다(루트 CLAUDE.md 「새 수식 금지」).
7. **판정 층** — R = 2N 기준. A/B/H 세 기간 전부 + 클러스터 부트스트랩 95% 하한 > 0. 상위 1% 제거 민감도. **문턱은 돌리기 전에 적는다**(cycle372·375 의 다중 비교 규율).
8. **패리티 단계(라이브 배선 직전에만)** — `StrategyBase` 서브클래스를 날짜별로 몬다(`_cycle364_harness` 패치 방식). 고정 표본(예: 50종목 × 250일)에서 순수 leaf 의 진입 집합과 같은지 단언한다. 이것을 통과해야 카드 #2·#3 에 올린다.

### 7.3 한계

- **일봉만 있다.** momentum·VB·LTV 의 장중 경로는 재현이 아니라 다른 전략이 된다(`backtest_orchestration.py:49-53` 주석, `strategies/CLAUDE.md`). 후지모토(RSI·MACD·일목)와 깡토(일봉 추세)는 일봉 재현이 성립한다[추정].
- **ETF 는 보관소에 없다.** ETF 전략을 재현하려면 KRX ETF 일별 수집을 따로 해야 한다. 운영 DB 에는 ETF 일봉이 약 1년 있다(cycle375 §2.6 — DB 덤프에 ETF 이름 381종목).
- DB 이음 구간 H 는 오늘 시총 ≥ 500억 ∪ 실체결 종목이라 대형 편향이 있다(cycle375 §6).

---

## 8. 사용자 결정 1·2·3 과 닿는 구조 사실

| 주제 | 구조가 막는 것 [코드] | 새 전략 파일만으로 되나 |
|---|---|---|
| **후지모토 1:2:6 분할 매수·매도** | ① `strategy_registry.py:86-98` `is_ticker_blocked_for_buy` 가 **자기 전략 보유 종목**의 추가 매수도 막는다(8영역) ② `pending_buy_amounts` 가 `ticker` 단일 키(루트 CLAUDE.md, 카드 E) ③ `execute_sell` 은 항상 전량(B7 진행 중) ④ `Position` 은 매수가·수량 하나. ⑤ 랏 기하 — 1:2:6 의 첫 조각이 1주 이상이려면 한 포지션이 9주 이상이어야 한다. 루트 CLAUDE.md 입금 후 q = VB 0.74 · LTV 1.11 · donchian 2.70 · momentum 4.34 · BFB 5.66 · kojiro 10.11 → kojiro 규모 랏만 선다[추정] | **아니다** — ①~④ 선결. 오프라인 재현(§7)은 지금 된다 |
| **깡토(추세 진입 + 느슨한 청산 + 종목 사이 크기 조절)** | 연승·연패 상태는 `StrategyState` 가 매일 리셋돼 재시작을 못 넘긴다 → `trade_history` 에서 부팅 때 다시 계산해야 한다. 시장 유닛에 쓸 라이브 KOSPI 60일선 출처는 확인하지 않았다. `market_regime.py:628` 이 KODEX200(`069500`) 일봉을 쓰는 경로가 있다(대용 후보) | 진입·청산은 된다. 크기 조절은 사이징 규약 변경이라 승인 |
| **시장 유닛(결정 2)** | 전략이 아니라 사이징 곱셈자다. 끼울 자리는 둘 다 승인 대상이다. (가) 전략별 `calc_buy_quantity` / `StrategyBase` 관문 — 「신규 진입 크기」라는 깡토 본뜻에 맞다. 관문 순서 계약·A-PURE 가드와 맞춰야 한다. (나) `allocate_funds`(`strategy_registry.py:36-45`, 8영역) — `cash_usage_ratio`·매크로 레짐과 같은 층이라 시너지가 자연스럽다. 다만 예산 자체가 줄면 캡 3종이 함께 줄어든다(자금비율 fail-open 자문 — 예산이 줄면 K축·ρ축·명목 캡이 함께 준다) | 새 전략이 아니다. 카드 #3 의 원형 선언에 「시장 유닛 적용 여부」를 한 칸 두면 전략별 켜기·끄기가 한곳에 모인다[추정] |
| **ETF 매매 대상(결정 3)** | 7전략 유니버스가 `scanner.ETF_KEYWORDS`(`scanner.py:494-497`) 이름 필터로 ETF 를 뺀다. 이 목록에는 `"BNK"` 가 있어 BNK금융지주 같은 주식도 걸린다(cycle375 §2.6). `volume_rank` 경로는 `_universe_filter_securities_only`(`scanner.py:2152`)가 `prdt_type_cd` 300(보통주)만 통과시킨다 | 기존 전략에 ETF 를 **섞는** 것보다, **ETF 전용 새 전략**(자기 유니버스)이 결합이 가장 작다[추정]. 그러면 이 메모의 추가 경로 그대로다. 재현에는 ETF 5년 일봉 수집이 선행이다 |

---

## 9. 비권고 사항 (검토했으나 권하지 않음)

- **플러그인식 자동 발견(디렉터리 import 로 자동 등록)** — 등록 순서가 매수 우선순위라 **순서가 명시돼야** 한다(`risk.py:642`). 자동 발견은 파일 이름순이 되어, 파일 하나 추가로 기존 전략의 우선순위가 바뀔 수 있다. 명시적 명부(카드 #2)로 충분하다.
- **공통 12키 값을 `StrategyBase` 로 끌어올리기** — 7파일·핀·킬스위치 규약을 다 흔든다. 누락 탐지는 카드 #4 검사로 충분하다.
- **`risk.py` 목록을 파생으로 바꾸기(8영역)** — 기본은 리터럴 유지 + 교차 검사다. 파생화는 폴형 전략이 자주 추가될 때만 이득이다(§10 결정 3).
- **`_PRE_MARKET_EXIT_EVAL_STRATEGIES`(`risk.py:79`)를 원형 선언으로** — 「`tradable_boards` 가 아닌 명시 상수」가 안전 규약이고 AST 가드가 있다. 2계명(안전 규칙 우선)으로 제외한다.
- **구독 출처 카운트 일반화(`scheduler.py:1876-1918`)** — 로그 서식이 D+1 grep 계약이다. kojiro 가 `swing` 카운트에서 빠진 것은 관측 결손이지만, 서식 변경은 별도 결정이다.
- **`scheduler.py` 핀 23건 통합** — 사이클별 무접촉 증거라는 하네스 정책이다. 카드 #2 로 전략 추가가 핀을 건드리지 않게 되면 이 메모의 문제는 풀린다.
- **ScanMonitor 깔때기 패널 일반화** — 패널이 없어도 매매는 무관하다. 전략별 단계 정의가 5개뿐이라 반복 기준(3회)은 넘지만 효과가 작다. 새 전략이 실제로 붙을 때 다시 본다.

---

## 10. 사용자에게 물을 것

1. **카드 #1(테스트 명부 + 안전 가드 3종 전환, LOW)을 먼저 할까요?** 새 전략을 붙이기 전에 막아야 할 구멍입니다. 지금은 예산 관문·예산 불변식·계좌 게이트가 없는 새 전략이 검사를 통과합니다.
2. **등록·원형 분리(카드 #2·#3, `scheduler.py` 승인 + 카드 #3 은 도메인 자문)를 언제 할까요?** 권고는 「후보가 오프라인 재현 문턱을 넘은 뒤」입니다. 지금 하면 쓰일지 모르는 구조를 먼저 만드는 셈입니다.
3. **폴형 새 전략을 붙일 때 `risk.py:88` 은?** (가) 리터럴 유지 + 교차 검사: 추가마다 8영역 한 줄 승인. (나) 한 번 승인해 원형 선언에서 파생: 이후 무접촉.
4. **D-1 `save_params` 기본값.** 운영 DB 에 7행이 다 있는지 확인한 뒤, 행이 없을 때 `enabled=False, weight=0` 으로 바꿀까요? 행위 변경이라 승인 대상입니다.
5. **전략 표시명을 하나로 정해 주세요.** donchian(「20일 신고가 스윙」/「도치안 스윙」/「돈치안 스윙」), BFB(「눌림목 돌파」/「불플래그 돌파」), VCP(「변동성 수축 돌파」/「VCP 변동성 수축」/「VCP 돌파」). 카드 #5 의 입력입니다.
6. **재현 틀을 `tools/replay/` 에 둘까요?** cycle351·372 스크립트와 스크래치의 c375 스크립트(데이터 이음·4전략 대리 진입·크기 조절)를 옮겨 일반화하는 일입니다. cycle375 §8 질문 3 과 같은 질문입니다.
7. **ETF 전략을 재현까지 가 보려면 ETF 5년 일봉 수집이 먼저입니다.** 보관소 확장, KRX 호출, 운영 DB 쓰기 0 입니다. 진행할까요? 콜 수·시간은 cycle362(주식 2,622콜·61분) 규모로 추정하며, 실측은 아닙니다.
8. **D-2 전략 제거 시 고아 포지션 규약.** momentum 폴백 유지 / 관찰 로그만 추가 / 부팅 거부 중 무엇으로 할까요? 결정 전까지 「보유·미체결·`positions` 행 0 뒤에만 코드 제거」를 문서 규약으로 둡니다(카드 #6).

---

## 부록 — 재현

- 사본 4벌·실행 로그: `/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/{base,s1,s2,s3}` · `run_{base,s1,s2,s3b}.txt` · 차이 `new_s1.txt` `new_s2.txt` `new_s3.txt`
- 사본 생성: `git archive HEAD | tar -x -C <dir>`. 실행: `python3 -m pytest tests/unit tests/contract -q -p no:cacheprovider --tb=line -rf`(S3 는 `--continue-on-collection-errors`). 각 약 4분.
- 결과: S0 17 실패 · S1 54 · S2 64 · S3 532 실패 + 115 오류 + 수집 오류 24 모듈.
- 리터럴 목록 스캔: `scratchpad/find_lists.py` → `lists.txt`(81곳).

---

## 11. 보충 (2026-10-01) — 평균회귀·ETF 전략이 요구하는 구조 조건

> 사용자 결정(2026-10-01) 「리팩토링 과제에 평균회귀 전략을 품을 수 있는 구조를 추가」 → **전용 재설계가 아니라 기존 카드의 입력으로 얹는다.** 근거: 평균회귀는 아직 연구(`_workspace/design/2026-10-01_mean_reversion_handoff.md` 트랙 R)를 통과하지 않았고, 이 메모 §6 의 3계명(미래 가정으로 추상화하지 않는다)이 그대로 적용된다. 아래 조건은 **모두 평균회귀만의 요구가 아니다** — ETF 전략·기존 전략이 이미 필요로 한다. 그래서 평균회귀가 연구에서 탈락해도 남는다.

### 11.1 평균회귀가 지금 구조에서 걸리는 곳 [코드]

| # | 필요한 것 | 지금 | 얹을 자리 | 다른 소비자 |
|---|---|---|---|---|
| 1 | 아침 일봉 판정 원형 | 카드 #3 `EVAL_DRIVER="swing_poll"` 로 이미 덮인다 | #3 (변경 없음) | donchian·kojiro |
| 2 | 시장 유닛 **적용 방식** 선언 | 터틀 4전략에 「설계 랏 축소」 로 고정(`src/engine/market_unit.py`, 루트 CLAUDE.md 「자금 관리」). 평균회귀는 「m=0 이면 신규 진입 차단, 그 외 무변경」 이라 방식이 다르다 | **카드 #3 확장** — 원형 선언에 `MARKET_UNIT_POLICY: ClassVar[str]` = `"scale"`(터틀 4) · `"block_zero"`(평균회귀) · `"none"`(그 외). §8 「시장 유닛」 줄의 「한 칸 두면」 을 bool 이 아니라 3값으로 정한다 | ETF 전략(설계서 「시장 유닛 적용」) |
| 3 | 청산 사유 구분(타임스톱·이익·회귀 깨짐) | `Signal` 에 시간 청산 값이 없어 손절로 섞인다(`strategy_base.py:54-62`) | **새 카드 아님** — cycle367 P2 카드 4-1 (나) `TIME_EXIT`+`TAKE_PROFIT`+`TREND_EXIT`(09-25 승인, 10-03~04 코드 사이클)가 둘을 덮는다. 「회귀 깨짐」 이름은 평균회귀가 연구를 통과할 때 **가산**한다(지금 추가 금지 — 쓰지 않는 enum 값). 4-1 구현 시 `Signal` 을 가산형으로 두라는 입력만 넘긴다 | donchian·BFB 시간 청산 오표기(N2) |
| 4 | **포지션별 진입 메타 보존** | `Position` 은 매수가·수량·매수일·고점뿐(`strategy_base.py:66-74`). `positions` 테이블(migration 006)에 확장 칸이 없다. 터틀 `_entry_atr` 은 재시작 때 **매수일 이전 봉으로 재도출**해 우회한다(`strategy_base.py:1733` `_rederive_entry_atr`) | **새 카드 #8** (아래) | 터틀 4전략 `_entry_atr` · 평균회귀(진입 반감기·μ·σ·z) · 피라미딩 사다리 |
| 5 | 매매 없이 신호·가상 청산만 남기는 **공통 섀도 모드** | 없다. `weight=0` 은 `enabled=False` 자동 토글 = 손절 정지(루트 CLAUDE.md 금기). `buy_paused` 는 매수를 멈추지만 「사려 했던 것」 을 남기지 않는다 | **새 카드 #9** (아래) | ETF 전략(설계서 「비중 0 shadow 4주·10건」 — 그 「비중 0」 이 금기와 충돌) |
| 6 | 오프라인 재현 틀 | §7 `tools/replay/` (결정 16) | §7 — 평균회귀 연구가 **첫 입주자**(필요한 층만) | 모든 새 전략 |

### 카드 #8 — 포지션별 진입 메타 보존 (재계산 vs 저장)

- **위험 등급**: MEDIUM — 청산 판단의 입력이 바뀐다. `positions` 스키마 가산(NULL 허용 JSONB) 은 사전 승인 범위지만, 읽는 쪽 `Position`·복구(`boot_manager.py`)·`_rederive_entry_atr` 은 청산 규약에 닿는다.
- **현 상태**: 진입 시점 값이 메모리에만 있고 재시작이 지운다. 터틀은 「매수일 이전 봉으로 재도출」 로 복원한다. 이 방식은 **입력이 결정적일 때만** 성립한다(같은 봉 → 같은 ATR).
- **판단 기준(먼저 정한다)**:
  - 재계산 가능 = 진입 시점 값이 「매수일 이전 확정 봉 + 고정 파라미터」 만의 함수 → 지금처럼 재도출(저장 불필요). 단 cycle386 이전처럼 **봉이 나중에 고쳐지면 재도출 값이 진입 때와 달라진다** — 그 위험을 받아들일지가 결정 사항이다.
  - 저장 필요 = 진입 때의 추정 창·파라미터 버전에 의존(평균회귀의 반감기·μ·σ 는 「5영업일마다 재추정」 이라 매수일 이전 봉만으로는 어느 재추정 창이었는지 다시 맞춰야 한다).
- **권고(후보가 생긴 뒤)**: `positions.entry_meta JSONB NULL` 가산 + `Position.entry_meta: dict` + 복구 시 저장값 우선, 없으면 기존 재도출. **기존 `_entry_atr` 경로는 바꾸지 않는다**(「ATR 손절 게이트는 `_entry_atr` 스탬프 존재」 금기 · 커플링 불변식). 평균회귀가 문턱을 넘기 전에는 착수하지 않는다.
- **입력 대기**: 트랙 R 보고서의 「진입 시점 보관 값 목록 + 재계산 복원 가능 여부」.
- **선행 의뢰**: domain-expert(보관 값이 청산을 어떻게 바꾸나) · 8영역 판정(`boot_manager.py` 복구 경로).

### 카드 #9 — 공통 섀도 모드

- **위험 등급**: MEDIUM — 매수 경로에 분기가 생긴다. 신호 단계에서 끝나야 하고, 주문·예산·`pending_buys` 에 닿으면 안 된다.
- **현 상태**: 섀도는 전략마다 따로 있다(시장 유닛 `market_unit_mode="shadow"`, LLM 게이트 shadow, `pyramid_shadow`). 「전략 전체를 섀도로」 는 없다. ETF 설계서의 「비중 0 shadow」 는 그대로 하면 `enabled=False` 가 된다.
- **권고**: 7전략 공통 `DEFAULT_PARAMS["shadow_mode"]=False`(`buy_paused` 와 같은 모양 — `is True` 일 때만, `PARAM_RANGES`/`INT_PARAMS` 편입 금지, 즉시 반영). 켜면 `check_buy_signal` 이 BUY 대신 `[shadow_buy]` 기록 + `Signal.NONE` 을 돌려주고, 가상 포지션의 청산을 일봉으로 사후 계산한다(실보유가 없으니 손절 정지 문제가 없다). 막는 자리 = 공통 매수 게이트(`_account_soft_gate_blocked`) 의 **`buy_paused` 다음 문장**.
- **결정 필요**: 섀도 전략에 비중을 줄지(0 이면 `enabled=False` 라 신호 평가 자체가 안 돈다 — 최소 비중 + `shadow_mode` 인지, `enabled` 와 비중을 떼는 #3 계열 수정인지).
- **선행 의뢰**: domain-expert(가상 체결 가정) · ETF 전략 설계와 함께 정한다 — **ETF 전략이 첫 소비자**이므로 착수 순서는 ETF 전략 shadow 직전.

### 11.2 순서

- 카드 #3 확장(#11.1-2)은 카드 #3 본체와 함께. #8·#9 는 **소비자가 실제로 생긴 뒤**(#9 = ETF 전략 shadow 직전, #8 = 평균회귀 연구 통과 뒤). 워크리스트 「진행 순서」 6·7 에 연결.
- 이 절은 행위 변경 0 인 계획 기록이다. 각 카드는 착수 때 승인·자문 절차를 따로 밟는다.
