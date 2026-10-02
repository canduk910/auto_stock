# cycle398 자문 — 리팩터링 카드 #2(등록 명부)·#3(원형 선언) 행위 영향 + 결정 대기 3건

- 작성 2026-10-02 KST · domain-expert · 읽기 전용(`src/`·`tests/`·정본 문서 무수정, git 쓰기 0)
- 입력: `_workspace/refactor/2026-09-27_strategy_add_remove_structure.md` §0·§2.1·§4.2~4.6·카드 #2·#3·§10·§11(카드 #8·#9) · ETF 설계 `_workspace/design/2026-09-27_etf_trend_strategy.md` · `_workspace/domain_consult/cycle391b_etf_exit_sizing_bundle.md` · 평균회귀 `_workspace/design/2026-10-01_mean_reversion_handoff.md`
- 표기: **[코드]** 파일:줄을 읽은 사실 · **[실측]** 이번에 돌린 조회 · **[추정]** 판단
- 운영 DB 조회 [실측, 2026-10-02 15:53 KST, `BEGIN READ ONLY`]:

| strategy_id | enabled | weight | tradable_boards | market_unit_mode | sizing_mode | buy_paused | 보유 |
|---|---|---|---|---|---|---|---|
| momentum | True | 0.0316 | ["main"] | (없음) | (없음) | (없음) | 1 |
| volatility_breakout | True | 0.0316 | ["main"] | (없음) | (없음) | (없음) | 0 |
| long_tail_volatility | False | 0 | ["main"] | (없음) | (없음) | (없음) | 0 |
| donchian_swing | True | 0.1579 | ["main"] | enforce | turtle | **true** | 0 |
| bull_flag_breakout | True | 0.1579 | ["main"] | enforce | turtle | false | 4 |
| vcp_breakout | True | 0.2000 | ["main"] | enforce | turtle | false | 2 |
| kojiro | True | 0.4210 | ["main"] | enforce | turtle | false | 6 |

→ **7행 모두 있다.** 보유 13건(BFB 4 · kojiro 6 · VCP 2 · momentum 1).

---

## 질문 요약

1. 카드 #3 원형 선언으로 묶일 배선 축마다 「원형이 같으면 배선이 같다」 가 깨지는 실제 차이 + 원형 목록 제안 + 예외 처리
2. 결정 대기 3건 — (a) `risk.py:88` 리터럴 (b) D-1 `save_params` 기본값 (c) 카드 #9 공통 섀도의 막는 자리와 비중 0 문제
3. 「바이트 동일 행위」 증명 수단과 배포 시점 제약

---

## 1. 트레이더 시각 — 원형은 축 하나가 아니다

### 1.1 시장 가설로 본 전략의 「몸」

트레이더 말로 하면 이 시스템의 전략은 세 가지 몸을 갖고 있다.

- **틱을 보고 순간에 사는 몸** — 호가창이 터지는 순간이 진입이다. 구독 슬롯(41개)이 곧 기회다. momentum·VB·LTV·BFB·VCP.
- **아침에 일봉을 보고 한 바퀴 돌며 사는 몸** — 신호는 전날 봉에서 이미 났고, 아침 09:05~09:30 에 REST 로 한 종목씩 확인하고 산다. 순차라서 두 전략이 같은 종목을 동시에 사지 못한다. donchian·kojiro(+ETF·평균회귀).
- **얼마나 들고 가는가** — 그날 15:20 에 비우는 몸(VB·LTV), 다음 날 아침에 정리하는 몸(momentum·VB·LTV 안전망), 며칠~몇 주 들고 가는 몸(나머지).

문제는 **진입 방식(틱/폴)과 보유 기간이 독립**이라는 점이다. BFB·VCP 는 틱으로 사고 며칠 들고 간다. 그래서 원형 이름 하나로 모든 배선을 정하면 반드시 깨진다.

### 1.2 축별 점검 — 7전략 + ETF + 평균회귀 [코드]

| 축 | 지금 자리 | momentum | VB | LTV | donchian | BFB | VCP | kojiro | ETF(설계) | 평균회귀(설계) |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 매수 평가 구동 | `risk.py:88` · `scheduler.py:145` | tick | tick | tick | poll | tick | tick | poll | poll | poll |
| A2 후보 WS 구독 | `scheduler.py:1821-1826` | **자체 `scan_stocks`** | 순위 2 | 순위 3 | 없음 | 순위 0 | 순위 1 | 없음 | 없음 | 없음 |
| A3 빈 후보 재 prepare | `scheduler.py:2665` | — | 1번째 | 2번째 | — | 3번째 | 4번째 | — | — | — |
| A4 시가 기준 목표가 | `:782` `:1671` `:2624` · `open_price_rest.py:82` | — | ✓ | ✓ | — | — | — | — | — | — |
| A5 15:20 `check_force_clear` 호출 | `:2038` | — | ✓(전량) | ✓(조건부) | — | — | — | — | **✓ 후보(조건부)** | — |
| A6 익일 청산 | `:1389` | ✓ | ✓(안전망) | ✓ | — | — | — | — | — | — |
| A7 멀티데이 배지 | `strategy_base.py:81` | — | — | — | ✓ | **✗(예외)** | ✓ | ✓ | ✓ | ✓ |
| A8 재시작 복구 훅 | `scheduler.py:2309`·`:2320` · `boot_manager.py:507` | — | — | — | `recompute_held_atr` | `recompute_high_since_buy`(boot_manager) | `recompute_high_since_buy`(scheduler) | `recompute_held_atr` | 미정 | 미정 |
| A9 보유 REST 폴(09:30~15:20) | `scheduler.py:2887` | — | — | — | ✓ | — | — | ✓ | ✓ | ✓ |
| A10 시장 유닛 정책 | 각 전략 `calc_buy_quantity`·`check_buy_signal` 호출 + `_MARKET_UNIT_ATR_KEY` | none | none | none | scale | scale | scale | scale | scale + **결손 시 막음** | block_zero + 결손 시 막음(Q2 권고안) |
| A11 매수 게이트 위치 | `strategy_base.py:45` · cycle233 가드 | 발사 직전 | 발사 직전 | 첫 문장 | 첫 문장 | 첫 문장 | 첫 문장 | 첫 문장 | 첫 문장 | 첫 문장 |
| A12 종목상태 선조회 그룹 | `status_exit_watch.py:75-80` | 3(기본값) | 1 | 1 | 3 | 2 | 2 | 3 | 3 | 3 |
| A13 `tradable_boards` | `DEFAULT_PARAMS` + DB | 운영 DB 값 | 〃 | 〃(DB `main`, 코드 3보드) | 〃 | 〃 | 〃 | 〃 | main | main |
| A14 프리장 청산 평가 보류 | `risk.py:79` | — | — | ✓ | — | — | — | — | — | — |

### 1.3 「원형이 같으면 배선이 같다」 가 깨지는 곳

| # | 깨지는 곳 | 원인 | 바이트 동일을 지키려면 |
|---|---|---|---|
| X1 | **momentum 은 틱형인데 후보 구독 경로가 다르다** | 자기 후보가 `get_scanned_tickers()` 가 아니라 `scan_stocks()` 결과(`scheduler.py:856`)다 | 구독 순위 `None` + `scan_stocks` 경로는 손대지 않는다 |
| X2 | **구독 순서 ≠ 재 prepare 순서** | 구독은 BFB→VCP→VB→LTV(2026-08-08 사용자 결정, `:1821`), 재 prepare 는 VB→LTV→BFB→VCP(`:2665`) | 명세 카드 #3 의 「`_reprepare_breakout_if_empty` → rank 순」 은 **순서가 바뀐다.** 재 prepare 는 **등록 순서 필터**(= 지금 순서와 같다), 구독만 명시 순위로 뽑는다 |
| X3 | **익일 청산 순서 ≠ 등록 순서** | `:1389` 는 momentum→LTV→VB, 등록 순서는 momentum→VB→LTV | 익일 청산은 매도 발사 순서가 바뀐다. 3계명대로 **리터럴 유지**(한 곳뿐, 다음 소비자 없음) |
| X4 | **BFB 는 멀티데이인데 `_MULTIDAY_STRATEGIES` 밖** | 역사적 누락. 소비처는 `is_next_day` → 화면 배지·API 필드뿐이고 BFB 코드는 이 값을 읽지 않는다 | 「멀티데이」 선언에서 파생하면 BFB 배지가 바뀐다(표시 변경). **리터럴 유지 + 교차 검사, BFB 를 문서화된 예외로** |
| X5 | **복구 훅 이름이 둘이고 donchian 은 둘 다 가졌다** | donchian 은 `recompute_held_atr` 와 `recompute_high_since_buy`(`donchian_swing.py:1551`)를 모두 정의하지만 지금은 앞의 것만 불린다 | 「멀티데이면 `recompute_high_since_buy` 호출」 로 파생하면 **donchian 이 두 번 복구**된다. 훅은 **전략이 이름을 선언**(`RESTORE_HOOK = "held_atr" \| "high_since_buy" \| None`)하고 한 번만 부른다 |
| X6 | **축마다 `enabled` 게이트가 다르다** | 매수·구독·폴·시가·15:20·익일청산 루프는 `config.enabled` 를 본다. **복구 훅 3곳은 보지 않는다**(`hasattr` 만) | 파생 루프가 복구 축에 `enabled` 필터를 새로 넣으면 꺼진 전략 보유분의 기준점 복구가 사라진다. 축마다 지금의 게이트를 그대로 옮긴다 |
| X7 | **복구 시점이 두 곳** | VCP 는 `_eager_refresh_stock_master_for_held_positions` 끝(`:2320`), BFB 는 그 직후 `boot_manager.py:507`. 호출자는 `boot_manager.py:490` 하나 [코드 grep] | 한 루프로 합치면 VCP·BFB 사이에 다른 일이 끼지 않으므로 같은 시점이다. 단 「DB positions 복구 **뒤**」 는 반드시 지킨다 |
| X8 | **시장 유닛 정책은 진입 방식과 무관** | 터틀 4전략은 틱 둘(BFB·VCP) + 폴 둘(donchian·kojiro). 평균회귀는 같은 폴인데 block_zero | 원형에 묶지 않고 **독립 선언**으로 둔다 |
| X9 | **게이트 위치가 같은 틱형 안에서 갈린다** | VB 는 발사 직전, LTV 는 첫 문장 | 원형에 묶지 않는다. 지금처럼 리터럴 + cycle233 교차 검사 |
| X10 | **09:30 구독의 스윙 후보** | `:857` 은 `extra` 에 스윙 후보를 넣고 `_scan_loop`(`:2465`)는 뺀다. 다만 `priority_groups` 가 있으면 구독은 그룹으로만 하고 `swing=[]` 이라, 스윙 후보는 **구독되지 않고** 가격·거래대금 필터 호출과 `_record_scan_pool_candidates` 큐에만 들어간다 [코드 `scanner.py:1615-1650`·`:1712`] | 지금 동작 그대로 둔다(고치지 않는다). ETF 가 폴형에 들어가면 ETF 후보 약 80종이 이 큐에 들어간다는 것을 ETF 사이클 입력으로 넘긴다 |
| X11 | **`tradable_boards` 는 런타임 값** | 운영 DB 가 덮는다(LTV DB `["main"]` ↔ 코드 3보드 [실측]) | 원형 선언 대상 아님. 카드 #4(키 존재 검사) 영역 |
| X12 | **프리장 청산 평가 보류(LTV)** | 안전 규약 「명시 상수로 판정」 + AST 가드 | 원형 밖. 명세 §9 비권고와 같다 |

### 1.4 위험 시나리오 — 원형을 잘못 고르면 시장에서 무엇이 일어나나

- **폴형을 틱형으로 잘못 선언** — 아침 순차 폴과 틱 평가가 겹친다. 같은 종목을 폴이 확인하는 동안 틱이 먼저 사면 순차 폴이 막아 주던 이중 매수 경합이 다시 열린다. kojiro 는 통합 채널 시가 오염(09-07 갭업 탐지 0/8)을 다시 먹는다.
- **틱형을 폴형으로 잘못 선언** — 그 전략은 09:05~09:30 에만 산다. 장중 돌파(BFB·VCP 의 본업)가 사라진다. 에러가 아니라 「체결이 줄었다」 로만 보여 cycle48 처럼 늦게 발견된다.
- **구독 순위 누락** — 틱형 새 전략이 등록만 되고 순위가 없으면 남이 구독한 종목에서만 산다(§4.3 cycle48 경로).
- **15:20 훅 누락** — 당일 청산형이 밤을 넘긴다. VB 는 다음 날 아침 익일 청산 안전망이 잡지만 손실은 갭만큼 커진다.

---

## 2. 정량 권고 — 원형 목록과 축별 선언

### 2.1 권고 구조: 「축별 선언(필수) + 원형은 이름표」

원형 하나가 축 전부를 정하는 설계는 X1·X4·X5·X8·X9 에서 바로 깨진다. 그래서 **축마다 따로 선언하고, 원형은 조합에 붙이는 이름표와 테스트 프리셋**으로만 쓴다. 기본값을 두지 않고 `__init_subclass__` 에서 누락이면 `TypeError` 로 막는 것은 명세 카드 #3 그대로 좋다(조용한 무매매 대신 기동 실패 = 시끄러운 실패).

| 선언(ClassVar, 기본값 없음) | 값 | 파생시키는 배선 | 파생 순서 |
|---|---|---|---|
| `EVAL_DRIVER` | `"tick"` \| `"swing_poll"` | 스윙 폴 루프·보유 REST 폴·스윙 prepare 재시도·`_collect_swing_tickers` · (결정 (a) 에 따라) 틱 매수 평가 제외 | **등록 순서**(donchian→kojiro, 지금과 같다) |
| `TICK_SUBSCRIBE_RANK` | `int` \| `None` | `_collect_breakout_tickers` | **순위 오름차순**(BFB 0 · VCP 1 · VB 2 · LTV 3) |
| `TICK_REPREPARE` | `bool` | `_reprepare_breakout_if_empty` | **등록 순서**(VB→LTV→BFB→VCP — X2) |
| `OPEN_PRICE_TARGET` | `bool` | `:782` `:1671` `:2624` | 등록 순서(VB→LTV) |
| `CLOSE_AT_1520` | `bool` | `_force_clear_main_only` 대상 | 등록 순서(VB→LTV) |
| `RESTORE_HOOK` | `"held_atr"` \| `"high_since_buy"` \| `None` | 재시작 복구(한 전략 한 번, `enabled` 무관 — X6) | 등록 순서(donchian→VCP→BFB→kojiro 가 되는데 아래 주의) |
| `MARKET_UNIT_POLICY` | `"scale"` \| `"block_zero"` \| `"none"` | 이번 카드에서는 **교차 검사만**(`scale` ⇔ `_MARKET_UNIT_ATR_KEY is not None` ∧ 두 진입점 호출 AST) | — |

- `TICK_REPREPARE` 를 따로 두는 이유: 지금 집합은 구독 순위 보유 집합과 같지만(VB·LTV·BFB·VCP) **순서가 다르다**. 같은 집합을 두 선언으로 적기 싫다면 `TICK_SUBSCRIBE_RANK is not None` 에서 집합을 뽑고 **순서만 등록 순서로** 뽑는 것도 된다. 선언 하나가 낫다(0계명) — 권고는 후자다.
- `RESTORE_HOOK` 순서 주의: 지금 실제 순서는 「donchian·kojiro(`recompute_held_atr`) → VCP → (eager 반환) → BFB」 다. 등록 순서로 한 루프를 돌면 donchian → BFB → VCP → kojiro 가 된다. 각 훅이 자기 전략 보유만 만지므로 서로 독립이라 결과 상태는 같다[추정] — **그래도 골든 테스트는 호출 순서를 지금 그대로 고정**하고, 순서를 바꾸려면 테스트를 바꾸는 별도 결정으로 한다. 가장 안전한 형태는 「`held_atr` 묶음 → `high_since_buy` 묶음」 2단 루프(각 묶음 안은 등록 순서) = donchian·kojiro → VCP·BFB 순서다. BFB·VCP 사이 순서만 바뀐다(VCP→BFB 가 등록 순서로는 BFB→VCP). 그 하나는 독립 훅이라 허용 가능하나, **바이트 동일을 고집하면 `high_since_buy` 묶음만 VCP→BFB 명시 순서를 둔다**.
- `MARKET_UNIT_POLICY` 를 지금 **행위 파생에 쓰지 않는다** — 시장 유닛은 각 전략의 `calc_buy_quantity`·`check_buy_signal` 안에서 명시 호출로 걸려 있고(관문 순서 계약·A-PURE), 이걸 베이스 클래스 분기로 옮기면 사이징 경로가 바뀐다. 이번에는 선언 + 교차 검사(선언 `scale` 인데 두 호출이 없으면 붉음)만 하고, `block_zero` 의 실제 동작은 평균회귀가 연구 문턱을 넘을 때 가산한다.
- **결손 시 동작(fail-open/closed) 은 3값 정책에 넣지 않는다.** ETF(설계 §5.2)와 평균회귀(Q2 권고안)는 결손 날 신규 진입을 막고, 터틀 4전략은 m=1 로 연다. 이것은 「정책」 과 직교하는 두 번째 축이다. 지금 소비자가 없으므로(3계명) ETF 사이클에서 `MARKET_UNIT_ON_UNAVAILABLE: "open" | "closed"` 같은 ClassVar 로 가산한다. **리스크 정체성 값이라 `DEFAULT_PARAMS` 가 아니라 ClassVar** 가 맞다(AI 자문·PUT 으로 열리면 안 된다).

### 2.2 원형 이름표 (4종)

| 원형 | 멤버 | A1 | A2 | A4 | A5 | A8 | A10 | 원형 안의 예외 |
|---|---|---|---|---|---|---|---|---|
| `tick_scan` | momentum | tick | None(자체 `scan_stocks`) | ✗ | ✗ | None | none | 단독 원형. 익일 청산 리터럴 멤버 |
| `tick_intraday` | VB · LTV | tick | 2 · 3 | ✓ | ✓ | None | none | 게이트 위치(VB 발사 직전/LTV 첫 문장), LTV 프리장 청산 보류, 15:20 VB 전량/LTV 조건부(전략 본체 몫) |
| `tick_multiday` | BFB · VCP | tick | 0 · 1 | ✗ | ✗ | high_since_buy | scale | BFB 멀티데이 배지 누락(X4), 복구 위치(X7) |
| `poll_daily` | donchian · kojiro · (ETF) · (평균회귀) | swing_poll | None | ✗ | ✗(ETF ✓ 후보) | held_atr(ETF·평균회귀 미정) | scale(평균회귀 block_zero) | kojiro 틱 제외 근거가 donchian 과 다름(결과는 같다) |

- **원형으로 묶을 수 없어 리터럴로 남길 예외(교차 검사만)**: 익일 청산 `:1389`(X3) · `_MULTIDAY_STRATEGIES`(X4) · `_ALWAYS_STATUS_GATE_CANDIDATE_SIDS`(X9) · `status_exit_watch._GROUP`(우선순위 1/2/3 은 원형과 거의 겹치지만 momentum 이 「기본값 3」 으로 들어가 있어 파생하면 의미가 바뀐다 — 교차 검사는 「`swing_poll` ⊆ 그룹 3」 와 「틱 구독형 ∉ 그룹 3」 둘) · `_PRE_MARKET_EXIT_EVAL_STRATEGIES`(안전 규약) · 구독 출처 카운트 `:1876-1918`(D+1 grep 계약) · `open_price_rest._BASIS_STRATEGIES`(8영역 아님, `OPEN_PRICE_TARGET` 과 교차 검사).
- **ETF 의 「돌파선 아래 종가 청산」 은 `CLOSE_AT_1520=True` 로 들어오는 것이 트레이더 본능에 맞다.** 15:20 에 판단해 시장가를 내면 주문은 15:20~15:30 장 마감 동시호가로 들어가 **그날 종가로 체결**된다. cycle391b 가 「종가를 본 뒤에는 그날 못 판다」 고 한 제약(M1)을 가장 가깝게 메우는 집행이다. 차이는 「15:20 가격으로 판단·15:30 종가로 체결」 이라 판단과 체결 사이 10분 동시호가 변동만 남는다. LTV 가 이미 같은 훅을 조건부로 쓰므로 새 메커니즘이 아니다. 단 `_force_clear_main_only` 는 `Signal.FORCE_CLEAR` 를 하드코딩해 사유가 「강제청산」 으로 찍힌다 → ETF 사이클이 사유 표기(cycle367 카드 4-1 `TREND_EXIT`)와 함께 정한다. **이번 리팩터링에서 이 선언 칸을 열어 두면 ETF 사이클은 `scheduler.py` 를 다시 열 필요가 없다.**
- 평균회귀의 타임스톱 「다음 날 시가 청산」 은 momentum 익일 청산 기계(갭 판정 → 트레일링 모드)와 의미가 다르다. 익일 청산 리터럴에 넣지 않고 자기 `check_exit_signal` 안에서 처리하는 것이 맞다(kojiro 스테이지3 익일 청산과 같은 방식) → A6 은 소비자가 늘지 않으므로 리터럴 유지가 맞다.

### 2.3 카드 #2(등록 명부) — 트레이더 관점 확인

- **명부 순서 = 틱 평가 순서**(`risk.py:642`) = 같은 틱에 두 전략이 신호를 내면 먼저 사는 쪽. 지금 순서(momentum→VB→LTV→donchian→BFB→VCP→kojiro)를 그대로 옮긴다. 새 전략(ETF·평균회귀)은 **끝에 붙인다** — 새 전략이 기존 실전 전략의 종목을 선점하지 않게 하는 것이 맞다. ETF 는 유니버스가 겹치지 않아(`is_etf_like` 로 주식 전략에서 빠짐) 실제 경합은 없다.
- **명부의 `enabled`·`weight` 기본값은 장식이 아니다.** `_load_strategy_config` 가 DB 조회에 실패하면 이 값으로 굴러간다(`scheduler.py:486-487` `기본값 사용`). 지금은 「momentum 만 켜짐·weight 1.0」 이다. 정리한다고 momentum 을 `False` 로 바꾸면 DB 장애일에 **켜진 전략 0개 = 전 보유 손절 정지**가 된다. 명부는 지금 값 그대로(momentum True 1.0, 나머지 False 0.0) 옮기고 골든에 넣는다.
- 행위 영향: 골든(`(sid, name, enabled, weight, 클래스명)` 7행 순서까지)이 통과하면 **매매 행위 변경 0**. 동의한다.

---

## 3. 결정 대기 3건 권고

### (a) `risk.py:88` 리터럴 — **권고 (나) 한 번 승인해 선언에서 파생**

- **트레이더 근거**: 「아침 폴로 사는 전략은 틱으로 사면 안 된다」 는 독립된 선택이 아니라 **폴 구동의 정의에서 나오는 불변식**이다. 틱 평가가 함께 돌면 순차 폴이 막는 같은 종목 이중 매수 경합이 열리고, kojiro 는 오염된 시가로 산다. 같은 사실을 두 곳에 적어 두고 사람이 맞추는 (가) 는 0계명 위반이고, 추가 때마다 받는 8영역 승인은 이미 그 전략의 설계 승인 + domain-consult 에서 판단한 것을 한 번 더 도장 찍는 일이라 안전을 더하지 않는다.
- **형태**: `risk.on_tick` 이 목록 대신 `strategy.EVAL_DRIVER == "swing_poll"` 를 읽는다(전략 인스턴스의 ClassVar — risk 가 전략 모듈을 import 하지 않아 순환 import 0, 런타임·DB·AI 로 바뀌지 않음). 상수 이름은 남겨 `frozenset(파생)` 으로 두는 방식은 risk.py 가 명부를 import 해야 해서 덜 좋다.
- **같이 남길 방어**: 「지금 파생 집합 == {donchian_swing, kojiro}」 골든 1건(값 고정 — 다음 전략 추가 때 이 골든을 바꾸는 diff 가 곧 리뷰 지점) + 변이 확인(kojiro 를 `tick` 으로 바꾸면 붉음).
- **(가) 를 고를 이유가 있는 유일한 경우**: 「폴로 사면서 틱으로도 사는」 혼합형을 허용할 계획이 있을 때. 그 혼합형은 순차 폴의 경합 차단을 깨므로 **허용하지 않는 것이 맞다**[추정]. 그래서 이분법 선언으로 충분하다.
- 승인 범위: 8영역 `risk.py` 한 줄(판정식) + sha 핀 갱신. 카드 #3 과 같은 커밋·같은 배포에 넣어도 바이트 동일(파생 집합이 같다)이라 귀인 문제가 없다.

### (b) D-1 `save_params` — **권고: 행이 없으면 「켜지 않는다」. 단 「메모리 현재값 보존」 이 더 정확하다**

- 운영 DB 7행이 모두 있다 [실측] → **오늘 영향 0**. 위험은 다음 새 전략(ETF·평균회귀)부터 실현된다.
- 트레이더 원칙: **「파라미터 저장이 켜고 끄기와 비중을 바꾸면 안 된다.」** 지금 코드는 행이 없으면 `enabled=True, weight=0.5` 를 적어, 화면에서 손잡이 하나 저장한 새 전략이 다음 재시작에 Σ 정규화로 자금의 약 1/3 을 받고 실매매에 들어간다. 매매를 **여는** 방향의 기본값은 닫힌 쪽이어야 한다.
- 선택지 두 개:
  - **2-1 (최소)** `enabled=False, weight=0` — 새 전략 기준으로는 안전. 다만 코드 기본값이 `enabled=True` 인 전략(지금은 momentum 하나)의 행이 어떤 이유로 사라진 뒤 파라미터를 저장하면, 다음 재시작에 그 전략이 꺼지고 **보유 손절이 멈춘다**(루트 금기). 지금은 momentum 행이 있어 가상의 경로다.
  - **2-2 (권고)** 행이 없으면 **라우트가 들고 있는 메모리의 현재 `enabled`·`weight` 를 그대로 적는다**(없으면 `False`·0). 저장이 상태를 바꾸지 않으므로 두 방향 모두 막힌다. 라우트(`routes/strategies.py:389`)는 레지스트리를 갖고 있어 값을 넘길 수 있다(8영역 아님, `src/db/strategy_config.py` 시그니처 가산).
- 어느 쪽이든 **매매 행위를 바꾸는 코드라 승인 대상**이고, 바이트 동일 리팩터링(카드 #2·#3)과 **같은 커밋·배포에 섞지 않는다**(귀인 분리).
- 함께 기록할 것: 새 전략 사이클은 시드 마이그레이션(`enabled=False, weight=0` 행 INSERT, `ON CONFLICT DO NOTHING`)을 필수 단계로 둔다(명세 카드 #6). D-1 수정은 그 시드를 빠뜨렸을 때의 2차 방어다.

### (c) 카드 #9 공통 섀도 — **권고: 막는 자리를 바꾼다. 비중은 0 + `enabled`·비중 분리**

**막는 자리 — 「`buy_paused` 다음 문장」 은 섀도의 목적과 맞지 않는다.**

- `_account_soft_gate_blocked` 는 폴·래치형 5전략에서 `check_buy_signal` 의 **첫 문장**이다(`donchian_swing.py:1632` 등) [코드]. 거기서 섀도로 돌려보내면 신호를 **계산하기 전에** 끝나서 「사려 했던 것」 이 남지 않는다. momentum·VB 만 발사 직전이라 두 부류에서 섀도가 다른 뜻이 된다.
- 섀도는 **실전과 똑같이 판단한 뒤 방아쇠만 빼는 것**이어야 한다. 순서 = 종목상태 차단 → `buy_paused`(멈춤이 이기면 기록도 없다) → 계좌 SOFT → **신호 계산** → 시장 유닛 거름(`_market_unit_blocks_entry`) → **여기서 BUY 를 `[shadow_buy]` 기록 + `Signal.NONE` 으로 바꾼다**.
- 권고 형태: 7전략의 **모든 BUY 반환**이 공통 관문 하나(예: `self._finalize_buy(ticker, …)`)를 거치게 하고 AST 로 강제한다 — `_apply_budget_limit`(A-GATE)와 같은 관례다. `execute_buy`(order_engine)·`risk.on_tick`·스윙 폴 루프(scheduler)에 두는 길은 8영역·승인 대상이고 경로가 둘로 갈리므로 피한다.
- 확인 필요: BUY 반환 직전에 전략이 상태를 바꾸는 곳(래치·`buy_signals` 화면 목록·`_bought_today`)이 있으면 섀도에서도 바뀐다. `_bought_today` 가 찍히면 같은 종목 섀도 신호가 하루 1회로 줄어 실전과 같아지므로 오히려 맞다. 화면 `buy_signals` 에 섀도 신호가 실전처럼 보이는 것은 막아야 한다 — tdd-engineer 가 전략별로 전수 확인.

**비중 0 문제 — 최소 비중은 쓰지 않는다.**

- 최소 비중(예 0.05)은 `allocate_funds` 의 Σ 정규화 때문에 **실전 6전략의 예산을 그만큼 깎는다**(쓰지 않는 현금이 섀도 전략에 묶인다). 랏이 1주 언저리인 지금(루트 「랏 미세화」) 5% 축소는 일부 종목을 0주로 떨어뜨린다. 섀도가 실전 행위를 바꾸면 섀도가 아니다.
- 그래서 **비중 0(예산 0 = 주문이 구조적으로 불가능, 이중 안전) + `enabled=True` 유지**가 맞다. 지금도 부팅은 DB `enabled=True, weight=0` 을 그대로 싣는다(`_load_strategy_config` 가 둘을 따로 적용 [코드]) — ETF 설계 S1 이 이 경로다. 깨지는 곳은 **`update_weights` 가 `enabled = weight > 0` 으로 덮는 것**(`strategy_registry.py:54`, 8영역)과 DB `save_weights`(`strategy_config.py:64`)다. 비중 화면에서 아무 전략이나 저장하면 섀도 전략이 꺼진다.
- 권고: 두 자리에서 「`shadow_mode is True` ∧ 보유 0 이면 비중 0 이어도 `enabled` 를 유지」 한 줄. `strategy_registry.py` 는 **8영역 한 줄 승인**이 든다. 가상 수량은 엔진에서 계산하지 않고(예산 0 이라 0 이 나온다) `[shadow_buy]` 에 가격·ATR·m·묶음만 남기고 오프라인에서 가정 예산으로 계산한다 — 예산 배선을 새로 만들지 않는다.

**손절 정지 금기와의 관계**

- 섀도 전략은 보유가 없으므로(예산 0 + BUY→NONE) `enabled` 를 켜고 꺼도 멈출 손절이 없다 — 금기와 충돌하지 않는다.
- 보유 중인 전략을 섀도로 돌리는 경우(실전 → 섀도 강등)는 **`enabled=True` 가 유지되므로 기보유분의 손절·트레일링이 계속 돈다** — 이것이 `buy_paused` 와 같은 성질이고, 비중 0 강등과 달리 금기를 밟지 않는다. 다만 보유 중 비중 0 저장은 라우트의 「매수금액 하한선 검증」 이 이미 거부한다. 섀도 강등은 비중을 건드리지 말고 `shadow_mode` 만 켠다.
- 🔴 「섀도라서 비중 0 → `enabled=False` 로 둔다」 는 길은 쓰지 않는다 — 평가 자체가 안 돌아 섀도 기록이 0 이 되고(ETF S1 함정), 보유가 남아 있으면 손절이 멈춘다.
- 섀도 + 틱형이면 WS 구독 슬롯(41)을 실전 전략과 나눠 쓴다(`config.enabled` 가 구독 게이트). ETF·평균회귀는 폴형이라 해당 없다. 틱형 섀도가 생기면 그때 구독 순위 최하위를 정한다.
- 시점: 명세 §11.2 그대로 **ETF 섀도 직전**. 카드 #2·#3 과 **다른 사이클**(행위 변경 · 8영역 한 줄).

---

## 4. 현 코드와의 정합성 — 충돌 항목

| 충돌 | 명세 위치 | 권고 |
|---|---|---|
| **재 prepare 를 구독 순위로 정렬** | 카드 #3 「`_collect_breakout_tickers` / `_reprepare_breakout_if_empty` → rank 순」 | 재 prepare 는 **등록 순서**로(X2). 순위 정렬은 구독만 |
| **`MARKET_UNIT_POLICY` 를 행위 분기로 쓰는 것** | §11.1-2 「원형 선언에 3값」 | 이번 카드는 **선언 + 교차 검사만**. `block_zero` 동작은 평균회귀 통과 뒤, 결손 시 동작 축은 ETF 사이클에서 가산 |
| **섀도 막는 자리** | 카드 #9 「`buy_paused` 다음 문장」 | **BUY 반환 공통 관문**(신호 계산 뒤) |
| **`_MULTIDAY_STRATEGIES` 대조** | 카드 #3 「선언 대조」 | 대조는 하되 **BFB 를 명시 예외**로. 파생 전환 금지(배지 변경) |
| **복구 훅 파생** | 명세 §4.2 「보유 기준점 재계산 훅」 | `RESTORE_HOOK` 이름 선언, 한 전략 한 번, `enabled` 무관(X5·X6) |

변경 vs 유지 선택지: 위 다섯 줄은 모두 「명세를 이렇게 고쳐 구현」 이다. 명세대로 그대로 구현하면 X2(재 prepare 순서)와 X5(donchian 이중 복구)가 **바이트 동일을 깨고**, 섀도는 기록 0 이 된다.

---

## 5. 행위 불변 증명 — 무엇으로 「바이트 동일」 을 보이나

### 5.1 교체 전에 쓰는 특성 테스트(골든) — 지금 코드에서 초록, 교체 뒤에도 초록

| # | 대상 | 단언 |
|---|---|---|
| G1 | 등록 | `[(sid, name, enabled, weight, cls) for s in registry.all()]` 7행 순서까지(카드 #2) |
| G2 | 파생 집합·순서 | 스윙 폴 `("donchian_swing","kojiro")` · 구독 `(BFB,VCP,VB,LTV)` · 재 prepare `(VB,LTV,BFB,VCP)` · 시가 `(VB,LTV)` · 15:20 `(VB,LTV)` · 틱 제외 `{donchian,kojiro}` |
| G3 | 리터럴 예외 교차 | `_MULTIDAY_STRATEGIES == 멀티데이 선언 − {BFB}` · `_GROUP` 그룹 3 ⊇ `swing_poll` · 틱 구독형 ∉ 그룹 3 · `_BASIS_STRATEGIES == OPEN_PRICE_TARGET` · `scale` ⇔ `_MARKET_UNIT_ATR_KEY` 존재 ⇔ 두 진입점 호출 |
| G4 | 구독 인자 스냅샷 | 가짜 후보를 심은 7전략으로 07:55 사전 구독·09:30 구독·`_scan_loop` 1회의 `subscribe_filtered_stocks` 인자(`tickers`·`extra` 순서·`source_counts`·`priority_groups` 5키)를 바꾸기 전 커밋 기준 스냅샷과 비교. **X10(09:30 `extra` 의 스윙 후보) 포함** |
| G5 | 스윙 폴 1주기 | 가짜 후보로 `fetch_stock_detail`·`execute_buy` 호출 순서 |
| G6 | 15:20·익일 청산 | `execute_sell` 호출 순서·신호(VB·LTV FORCE_CLEAR / momentum·LTV·VB 순 NEXT_DAY_CLEAR) |
| G7 | 틱 평가 행렬 | 같은 틱에 7전략 각각 `check_buy_signal`·`check_exit_signal` 호출 여부(스파이) — 틱 제외 2전략은 청산만 |
| G8 | 복구 훅 | 꺼진 전략 포함 보유를 심고 부팅: 호출 횟수 donchian `held_atr` 1·`high_since_buy` **0** / kojiro `held_atr` 1 / VCP·BFB `high_since_buy` 1 / 나머지 0, 호출 순서, 「DB positions 복구 뒤」 |
| G9 | `enabled` 게이트 | 축별로 꺼진 전략을 하나씩 넣어 매수·구독·폴·시가·15:20·익일청산은 빠지고 복구는 남는지 |

- **돌연변이 확인 필수**: kojiro `EVAL_DRIVER="tick"` · BFB 순위 제거 · VB `CLOSE_AT_1520=False` · donchian `RESTORE_HOOK="high_since_buy"` · 복구 루프에 `enabled` 필터 추가 — 각각 위 골든 중 하나 이상이 붉어야 한다.
- 기존 가드 유지: `test_cycle273e_ast_tick_buy_skip_constant.py`(결정 (a)(나)면 「판정식이 선언을 읽는다」 로 갱신) · cycle48 구독 테스트 · 스윙 폴 테스트 · `scheduler.py` 핀 23건(이 사이클이 한 번 갱신) · 8영역 sha 핀(결정 (a)(나) 일 때 `risk.py` 1건).
- 전체 스위트 재실행(고친 뒤 마지막에 한 번 더 — 메모리 규약) + `--log-level=DEBUG` 재실행.

### 5.2 운영 실측(D+1) — 배포 전 3영업일과 숫자 모양 비교

- 07:45 부팅: 복구 마커 — `recompute_held_atr`(kojiro 6 보유)·VCP 2·BFB 4 의 복구 로그가 이전과 같은 건수, `recompute_*_실패` 0. 시장 유닛 `[market_unit_state]` 4전략 동일.
- 07:55 `사전 구독: N종목` · 09:30 구독 `source_counts`(`vb= ltv= bfb= vcp= swing= momentum= positions=`) 모양과 크기가 전날과 같은 범위 · `[priority_drop]` 건수 같은 범위.
- 09:05~09:30 `[swing_poll]` 주기 요약(후보·필터·매수 수) — donchian 은 `buy_paused` 라 매수 0 이 정상, kojiro 후보 수 전날 범위.
- `[tick_buy_gate]` 분모 · `[stale_watcher_summary]` · 09:30 funnel 스냅샷 단계 수 동일.
- 15:20 `15:20 KRX 메인 매수 중단 + 강제 청산` 1행, VB 보유가 있으면 `강제 청산 대상` 행.
- 판정: 위 마커가 0 이 되거나 2배·절반으로 튀면 **롤백**(되돌리기 커밋을 미리 만들어 둔다).

### 5.3 배포 시점 제약 — 루트 운영 가이드 외 추가 조건

1. **full 모드(백엔드 재시작) 확정 배포다.** 장외 창 15:30~16:00 · 21:35~익일 07:45 · 주말만, 20:00~21:35 금지는 그대로다. 보유 13건이 있으므로 장중 금지도 그대로다.
2. **권고 창 = 평일(월~목) 15:30~16:00.** 재시작 직후 복구 훅·보유 구독이 **그 자리에서** 돌아 보유 13건 기준으로 바로 확인된다. 그리고 다음 날 아침 07:45 부팅·사전 구독·09:05 폴·09:30 구독·15:20 을 사람이 깨어 있는 하루에 모두 본다. 금요일 배포는 첫 실전 검증이 월요일로 밀린다. 밤 배포(21:35~)는 재시작이 세션 시작 컷오프(20:00)에 걸려 첫 부팅이 다음 날 07:45 이고, 문제가 보여도 08:00 NXT 프리장·익일 청산(momentum 1건) 전 15분 안에 되돌려야 해서 여유가 없다.
3. **같은 배포에 행위 변경을 섞지 않는다** — 카드 #2·#3(+ 결정 (a)(나)의 `risk.py` 한 줄)은 바이트 동일이라 한 배포가 된다. D-1(결정 (b))·카드 #9(결정 (c))는 **다른 배포**로 분리한다. 섞으면 D+1 숫자가 달라졌을 때 원인을 가를 수 없다.
4. **시장 유닛 상태가 바뀌는 날은 피한다.** 10-02 06:47 부터 터틀 4전략이 `enforce` 다. 장세 판정(KODEX200 60일선)이 넘어가는 날이면 축소 랏 때문에 매수 건수가 바뀌어 G 비교가 흐려진다. 배포 전날 `[market_unit_state]` 의 m 이 이틀 연속 같은지 본다.
5. **`buy_paused`·비중을 배포 창 앞뒤로 만지지 않는다.** donchian `buy_paused=true` 상태 그대로 두고 비교한다.
6. **배포 모드 확인** — `git diff --name-only <EC2 .deployed_sha> HEAD` 에 `src/` 가 있으면 full. 확신이 없으면 full 로 간주.

---

## 6. 반례 / 한계

- **「바이트 동일」 이 G1~G9 로 닫히지 않는 곳**: 로그 문구·마커 순서가 바뀌면 D+1 grep 계약이 깨질 수 있다. 파생 루프가 로그에 넣는 전략 이름 순서가 바뀌는지 G4·G6 이 문자열까지 잡도록 한다.
- **복구 순서(X7)** 는 각 훅이 독립이라는 [추정]에 기대고 있다. 두 훅이 같은 공유 자원(일봉 조회 rate limit·`_candidates`)을 쓰면 순서가 결과를 바꿀 수 있다. G8 이 호출 순서를 지금 그대로 고정하는 이유다.
- **원형 이름표는 미래 전략에서 또 깨질 수 있다.** 그래서 행위는 축별 선언에서만 파생하고, 이름표는 문서·테스트 프리셋으로만 쓴다.
- **ETF 를 폴형에 넣으면 공유 순차 폴(09:05~09:30)이 길어진다.** ETF 후보 약 80종의 REST 확인이 donchian·kojiro 뒤에 붙는다. 등록 순서상 ETF 가 마지막이라 기존 두 전략의 집행 시각은 그대로지만, 창 안에 ETF 를 다 못 도는 날이 생길 수 있다 — ETF 사이클 측정 항목.
- 운영 로그 대조는 하지 않았다(DB 는 `strategy_config`·`positions` 만 조회). D+1 비교 범위는 tester 가 배포 전 3영업일 실측으로 정한다.

---

## 7. 후속 검증 권고

- **tdd-engineer**: §5.1 G1~G9 를 교체 **전** 커밋에서 초록으로 먼저 세우고, 돌연변이 5종으로 붉어지는 것을 확인. 카드 #9 착수 때 7전략의 BUY 반환 직전 상태 변경(래치·`buy_signals`·`_bought_today`) 전수표.
- **backend-dev**: 명세 카드 #3 의사코드의 재 prepare 정렬을 등록 순서로 고쳐 구현. `RESTORE_HOOK` 2단 루프. 복구 축에 `enabled` 필터를 넣지 않는다.
- **tester**: 배포 전 3영업일 마커 기준선(§5.2) 확보 → D+1 비교 → 롤백 판정.
- **team-leader 결정 요청**: (a)(나) · (b) 2-2 · (c) 공통 BUY 관문 + 비중 0·`enabled` 유지 — 셋 다 승인 대상이고, (b)·(c) 는 카드 #2·#3 과 다른 배포.
