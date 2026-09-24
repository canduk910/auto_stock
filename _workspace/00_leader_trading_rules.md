# 매매 규칙 명세 — 팀장 작성

> 이력: [`docs/history/workspace-00_leader_trading_rules.history.md`](../docs/history/workspace-00_leader_trading_rules.history.md)
>
> 이 문서는 **지금 동작하는 매매 규칙만** 적는다. 바뀐 경위·실측 수치·결정 근거는 위 history 로,
> 사이클별 보고 원문은 [`docs/HARNESS_CHANGELOG.md`](../docs/HARNESS_CHANGELOG.md) 로 간다.

## 1. 시스템 개요
KIS OpenAPI 기반 국내주식 자동매매시스템. 다중 전략 아키텍처로 전략별 독립 자금 운용.
모의투자(VTS) 환경에서 1차 검증 후 실전 전환. **2026-05-08판 KIS API 명세에서 NXT(넥스트레이드 ATS) 주문/시세 정식 지원** → 매매 시간대를 KRX 단독에서 KRX+NXT 통합(08:00~20:00)으로 확장.

## 2. 전략 구성

### 전략 A: 상한가 모멘텀 (strategy_id: momentum)
전일종가 대비 급등 종목을 추적하여 +29% 돌파 시 매수, 다음 영업일 NXT 프리 시가에서 청산. **KRX 보드 한정**(상한가 +29%는 KRX 기준).

### 전략 B: 변동성 돌파 (strategy_id: volatility_breakout)
노이즈 비율 기반 동적 K값으로 보드별 시가 + 전일Range × K로 매수 목표가 설정, 돌파 시 매수. **KRX 메인 단독 활성**(`DEFAULT_TRADABLE_BOARDS=("main",)`, 사이클 26 — PRE_NXT/POST_NXT 매수 제거). 보드별 K값 파라미터(`k_value_nxt_pre/post`)는 잔존하나 매수 보드가 main 뿐이라 실효는 `k_value_krx_main` 만.

### 전략 C: 롱테일 변동성 돌파 (strategy_id: long_tail_volatility)
변동성 돌파 방식으로 조기 진입 + 당일 +29% 도달 시 익일 청산 모드 전환(롱테일 추구). **매수는 PRE_NXT / MAIN / POST_NXT 3보드** (사이클 38, 2026-05-22 사용자 의도 복원 — 야간 NXT 프리 진입 + 연속 상한가 종목 애프터 진입). 상한가 미도달 종목은 15:20 일괄 청산, 상한가 도달 종목은 익일 NXT 프리 청산 + POST_NXT 시간대 손절 모니터링. **`main` 보드 신규 매수는 15:20 컷**(cycle286 C2-a, 2026-09-12 — KRX 연속체결 종료 이후 신규 매수를 막는다. `pre_nxt`/`post_nxt` 무접촉, 청산 무접촉).

### 전략 D: 20일 신고가 스윙 (strategy_id: donchian_swing)
일봉 종가가 20일 신고가 돌파 + 60일 EMA 우상향 + 거래대금 1.5배 → 다음 영업일 09:05 시장가 매수. ATR(14)×2 트레일링 청산 / 하드 -7% / 15:20 강제 청산 없음(단 `breakout_fail_n_days`=5 시간 기반 청산은 있음) / 평균 5~15 영업일 보유. **KRX 메인만 활성**(추세추종은 일중 변동성 필요).

### 전략 E: 눌림목 돌파 (strategy_id: bull_flag_breakout)
강한 상승(폴) 후 짧은 횡보·완만한 조정(플래그) 종목을 추적, 플래그 상단 재돌파 시 매수. **KRX 메인 09:05~13:00 한정**(`tradable_boards=("main",)`). "측정된 이동(measured move)" 익절 — 폴 폭만큼 가면 절반 청산, 잔여 ATR×2 트레일링. 손절 -5% 또는 플래그 하단 이탈. 모멘텀(+29% 폭발) 후속 진입로.

### 전략 F: 변동성 수축 돌파 (strategy_id: vcp_breakout)
미네르비니식 VCP(Volatility Contraction Pattern) — 추세 + Stage 2 확인 + 2~4회 pullback 점진 수축 + 거래량 수축 후 베이스 상단 돌파 시 매수. **KRX 메인 09:05~14:30 한정**. ATR(14)×2 트레일링 + 50일 EMA 이탈 청산. 손절 -7% 또는 베이스 하단 이탈. 시간 청산 없음(멀티데이). donchian_swing 정공법 보강(신고가 직진 추격 → VCP 는 베이스 + 변동성 수축 확인).

### 전략 G: 고지로 대순환 스윙 (strategy_id: kojiro)
이동평균선 대순환(EMA 5/20/40 배열 스테이지) 추세추종. donchian 정공법 보강 — "질서정연한 추세"를 EMA 정배열 상태로 포착. **운영 DB `strategy_config.enabled=True` 로 실매매 중**이고 코드 등록 기본값만 `enabled=False, weight=0.0` 다크런치다 — 운영 비중의 진실 원천은 DB.
- **유니버스**: 전체 상장 종목(지수 고정 해제, 시총 500억↑·거래대금 10억↑ 컷) + **ATR/종가 변동성 밴드 1.0~6.0%** — 비협상 판별 필터다(<1% 노이즈·>6.0% 급등작전주 배제).
- **동시보유 리스크 캡**: `max_positions=5` + **동일섹터 동시보유 ≤ `max_positions_per_sector=2`** (매수 게이트 전용·fail-open·청산 미차단). 섹터 프록시 = KRX 산업지수 플래그 + 업종 대분류 폴백. **동일섹터 카운트는 전일 보유를 포함한다** — `_position_sectors` 영속 맵이 `_candidates` 와이프·ATR 밴드(<1%)·유니버스 이탈과 무관하게 held 섹터를 집계하므로 이 캡은 "포트폴리오 누적 섹터 노출 상한"이다(stamp = recompute / BUY 반환 직전, pop = `on_position_closed`). ⚠️ **kojiro `_reset_daily_state` override 추가 금지** — 멀티데이 held 섹터가 밤에 소멸한다.
- **후보 점수 랭킹**: 후보가 슬롯/섹터캡에서 경합하면 `0.4×(MACD3 3봉기울기/3/종가) + 0.3×(띠폭/직전5봉평균 − 1) + 0.3×6→1신선도`(후보풀 min-max 정규화 가중합)로 최적 셋업을 먼저 산다. **매수 후보 정렬만** — strict entry 자격·청산 임계 무변경이고 `rank_w_*` 가중치는 정체성 상수라 `PARAM_RANGES` 제외다. 성분①은 `/3/종가` 로 나눠야 주가 순위표가 되지 않고(누락 시 ρ=+0.853), 성분②의 분모는 **직전 5봉 평균**이어야 6→1 전환 직후 폭발하지 않는다. shadow 관측 `[kojiro_band_observe]` (leaf `src/engine/kojiro_band_observe.py`)가 두 식을 한 행에 남겨 대조한다.
- **매수(strict entry, 4조건 AND)**: ① 현재 스테이지 1(단기>중기>장기) ② 최근 5영업일 내 6→1 전환 인접(신선도, `stage1_freshness=5`) ③ EMA 3선 우상향 ④ 전일 종가 > EMA5. **KRX 메인 09:05~09:30 시장가**, 갭업 ≥5% / 갭다운 ≤-4% / 장중 붕괴(현재가<시가) 스킵, 1회만.
- **청산(우선순위)**: 고정% 하드손절 -8%(ATR 독립 backstop) → 2ATR 하드손절(tighten-only) → 스테이지3 진입(추세 종료, 익일 아침 발화) → 2.5ATR 샹들리에 트레일링. **시간·15:20 청산 없음(멀티데이)**.
- **브레이크이븐 플로어**: `breakeven_promote_atr`(기본 **0=비활성**, 활성 권장 1.5 — donchian P1 선례). 활성 시 `high_since_buy ≥ 매수가 + mult×ATR` 도달 이력이 있으면 2ATR 손절선을 `max(현행선, 매수가)` 로 승격해 기존 `_stop_floor` tighten-only 래칫에 영속한다(ATR 팽창해도 유지, 재시작 시 `recompute_held_atr` 이 H-1 복구 고점으로 재도출). **플로어일 뿐 트레일이 아니다** — 샹들리에 2.5ATR(조임 금기, `_workspace/domain_consult/kojiro_exit_loss_review.md`)가 위쪽 추세 청산을 계속 담당해 fat-tail 랠리를 자르지 않는다. Σ리스크캡 `_position_stop_price` 도 같은 산식을 미러한다(4선 max). **활성화 = DB `strategy_config.kojiro.params.breakeven_promote_atr=1.5` UPDATE + 재부팅**(`PARAM_RANGES` 미편입 = AI 튜닝 제외).
- **Phase 1 = position_ratio 자금관리**. 조기진입(스테이지6)·터틀 유닛 sizing·피라미딩 = **Phase 2 연기**.
- **⚠️ "돌파 순간 절대규칙" 명시적 승인 예외**: kojiro 진입은 전일 종가에 확정되는 *완성 일봉 상태조건*이라 장중 목표가 교차(돌파 순간)가 아니다 — VB/LTV 같은 intraday breakout 클래스 전용 규칙(이전틱<기준가 AND 현재틱≥기준가)은 적용하지 않는다. donchian 과 같은 "일봉 확정 → 익일 시가 집행" 클래스다. **단 kojiro 는 donchian 보다 장중 확증이 약하다**(donchian 은 장중 신고가 재돌파 확인을 유지하고 kojiro 는 장중 검증이 0이다) → 이 약화를 **방어선 4중**으로 보상한다: 09:05~09:30 창 + 갭업 스킵 + 갭다운 스킵 + 비붕괴(현재가≥시가) 확인.

### 전략별 자금 비중
- 프론트엔드 Settings 페이지에서 비중 조절. **단위 = 비율 0.0~1.0** (`PUT /api/strategies/weights` — 퍼센트 0~100 을 보내면 422). Σ > 1.0 이면 저장 전 거부(`success=false`). **진실 원천은 DB `strategy_config`**(7 전략) — 코드 기본값도 이 문서의 예시도 아니다. 마지막 실측(2026-08-18 `GET /api/strategies`) = momentum 0.05 / VB 0.15 / LTV 0.10 / donchian 0.15 / bull_flag 0.15 / vcp 0.10 / kojiro 0.30 (합 1.00, 7 전략 전부 enabled=True).
- ⚠️ **보유 중인 전략의 weight 를 0 으로 내리지 않는다** — weight 0 은 `registry.enabled()` 에서 이탈해 그 전략 보유 종목의 손절 평가가 멈춘다(`risk.py` `on_tick` 이 `enabled()` 를 단일 순회한다). 비활성화가 목적이면 `enabled` 축을 쓴다.
- 총 자산을 비중에 따라 분배, 각 전략은 할당된 자금 내에서만 매매
- 전략 간 동일 종목 중복 매수 방지 (보유 OR 주문중 OR 당일매도 통합 가드)
- **매수 수량 1주 fallback (전략 잔여 자금 기준)**: `position_ratio × total_investment // current_price = 0`이라도 **전략 잔여 자금**이 1주 살 수 있으면 1주 매수. **7개 전략 동일 규칙**.
  - **잔여 자금 = `state.total_investment` − (해당 전략 보유 포지션 `buy_price×qty` 합계 + 해당 전략 `pending_buys` 매수 예정 금액 합계)**
  - 보유/주문중은 `strategy_id`로 격리 — 다른 전략 포지션은 자기 전략 사용액에 포함하지 않음
  - 고정 총액(`state.total_investment >= current_price`)과 비교하면 같은 전략이 이미 자금 90%를 점유해도 1주가 더 나가 **전략 한도를 넘는다**(2026-05-11 운영 사고).
  - 구현: 7 전략(`momentum`/`volatility_breakout`/`long_tail_volatility`/`donchian_swing`/`bull_flag_breakout`/`vcp_breakout`/`kojiro`)의 `calc_buy_quantity` 가 `StrategyBase._apply_budget_limit` 관문을 경유하고, 관문이 `qty <= 0` 일 때 `_fallback_one_share(current_price)` 로 위임
- **전략별 투자한도 이중제한**: **① 개수 `max_positions` + ② 명목 `Σ매수금액 ≤ total_investment`.** ②는 `StrategyBase._apply_budget_limit(qty, price, ticker)` 공통 관문이 **7 전략 `calc_buy_quantity` 의 모든 return** 을 통과시켜 강제한다(AST 가드 A-GATE). 관문이 없던 시절 `position_ratio × max_positions` 가 kojiro 0.20×10 / LTV 0.50×4 = 각 **2.00** 이 되어 계좌 전체 122.5% 초과 청약이 났다.
  - `qty <= 0` → `_fallback_one_share` 위임 (**분기 순서가 계약**) / `qty > 0` → `min(qty, 잔여//price)`. **부분 매수 허용** — 부분 유닛의 리스크는 1유닛 *미만*(under-risk)이라 안전 방향이고, 소액 계좌에서 "유닛 미만 스킵"은 사실상 무매매를 만든다.
  - **불변식 `position_ratio × max_positions ≤ 1.0`** — 코드 기본값은 AST 가드(C-DEFAULT), AI 추천은 `_validate_recommendations` 교차검증. `max_positions` 는 리스크 정체성 상수라 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**.
  - **원자성**: `order_engine.execute_buy` 의 `calc_buy_quantity` ~ `pending_buys.add` 사이 `await` **0건**이라 관문 read 가 pending 등록까지 원자적이다. 관문 안에서 `await`/DB/HTTP **절대 금지** (AST 가드 A-ATOMIC/A-PURE).
  - 관측: `[budget_clamp] ticker=… strategy=… requested=… clamped=… remaining=…` DailyEmitCap 1회/(ticker,전략)/일.
- **1회 투자금액 ATR 유닛화 (`sizing_mode="turtle"`)**: `unit = floor(전략예산 × risk_pct ÷ ATR)`. **손절이 ATR 기반인 전략에만 적용**한다 — `수량 = 예산 × risk_pct ÷ (진입가 − 손절가)` 에서 손절이 고정%면 명목이 종목 무관 상수라 `position_ratio` 가 이미 리스크 균등이고, 사이징만 바꾸면 정규화가 깨진다(함정 #1). 상세 매트릭스는 `src/engine/strategies/CLAUDE.md` 「자금관리 — 사이징 방식 × 손절 기준」 절.
  - **ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 게이팅 금지 (DB 토글이 기보유 포지션의 손절 규약을 바꾸면 안 된다). 스탬프 값 = sizing 에 쓴 ATR 과 동일(커플링 불변식).
  - **랏당 최대 유닛 상한 `max_lot_units` (K = 2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든 매수 랏**(터틀 유닛 · `position_ratio` 낙하 · 1주 폴백)에 `min(수량, floor(K × 예산 × risk_pct ÷ ATR))` 을 적용하고, 그 상한이 0 이면 **매수하지 않는다**. 근거 = 터틀 유닛이 1주에 못 미치면 관문이 1주를 사는데 고가 종목에선 그 1주가 설계 유닛의 여러 배(donchian 실측 평균 4.94배·최대 15.61배)라 `risk_pct` 통제가 진입 시점에 이미 무력했다. **매수를 줄이는 방향뿐**이고 정상 터틀 랏(≤1유닛)은 K≥1 이라 한 건도 안 건드린다. K 는 리스크 정체성 상수 — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AI 자문·자동 적용 대상 아님), 읽는 쪽 `[1.0, 20.0]` 클램프. ATR 결측·모호·`risk_pct ≤ 0`·예외는 **fail-open**(현행 수량 유지 + `[fallback_cap_skipped]` WARNING). 고정%손절 5전략은 범위 밖. 피라미딩(사다리 증량)에서도 **K 는 2.0 을 유지하고, 1주 폴백으로 산 랏에는 사다리를 걸지 않는다**(설계안 `_workspace/design/2026-09-24_three_stage_sizing_pyramiding.md` D-2 — K→1.0 은 사다리와 무관하게 kojiro 진입 8%·donchian 진입 20% 를 없앤다). 위험 합계는 kojiro `max_open_risk_pct` 가 지킨다. 롤백은 해당 전략 `max_lot_units = 20.0` — **`PUT /api/strategies/{id}/params` 는 즉시, DB SQL UPDATE 는 다음 백엔드 재시작에서만** 반영되고, 당일 `_bought_today` 가 소진된 종목은 어느 쪽이든 다음 세션부터다.
- **랏 명목 ρ축 상한 `max_lot_ratio_mult` (K_ρ = 2.5, cycle245)** — 관문을 지나는 **모든 랏**의 명목을 `K_ρ × position_ratio × 예산` 이하로 자르고, 1주도 못 사면 **매수하지 않는다**. 산식 = `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // 현재가`. **두 캡은 `min` 으로 합성한다(cycle254)** — K축(`max_lot_units`)이 심사한 랏도 ρ축이 후심사하며, 판정기(`_lot_units_cap_governs` = `sizing_mode=="turtle"` ∧ `ticker` ∧ `risk_pct>0` ∧ 예산>0 ∧ ATR 해석 성공) 자체가 실패한 경우(`probe_error`)만 fail-open 으로 남는다.
  - **실효는 1주 폴백 랏뿐이다** — 사이즈드 터틀 랏·`position_ratio` 낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한(`min(qty, int(예산×position_ratio)//price)`)으로 이미 컷오프 이하라 항등적으로 무접촉이다.
  - **왜 ρ축인가**: LTV·VB·momentum 은 `risk_pct`·`_entry_atr`·`_candidates` 가 **소스에 0건**이라 ATR 축이 원리적으로 불가하다. 컷오프는 `[oversized_fallback]`·`portfolio_risk.compute_over_cap_positions` 가 이미 재고 있는 축이라 자기검증이 성립한다. 근거 = 09-04 실측 LTV 000500 220,000원이 설계 랏 52,041원의 **4.23배**로 들어가 그날 최대 단일 손실(−11,000원, 순자산 0.42%)을 냈다.
  - **차단(0주)이 유일 선택지** — K_ρ≥1 이면 캡은 1주 폴백 경로에서만 바인딩되고 그 수량은 항상 1이다(1주는 쪼갤 수 없다).
  - **전략별 차등 없음** — 진짜 차등은 이미 `weight × position_ratio`(순자산 대비 VB 5.25% / BFB 3.75% / LTV·VCP 2.00% / MOM 1.25%)에 있다.
  - **키 부재 = 캡 OFF** (cycle242 `max_lot_units` 와 **반대 관례** — 매수를 막는 통제라 fail-closed 는 P0-1 유령 키 재현 경로다). 키는 **7 전략 전부**의 `DEFAULT_PARAMS` 에 2.5 로 명시하고 AST 가 glob 전수로 강제한다. `PARAM_RANGES`/`INT_PARAMS` **편입 금지**, 읽는 쪽 `[1.0, 20.0]` 클램프(**하한 1.0 = 정상 비중 랏 무접촉의 수학적 전제**). `position_ratio` 결측·예산 0·초소액·판정 예외는 **fail-open**(현행 수량 + `[ratio_cap_skipped]` WARNING).
  - **컷오프는 예산에 선형 비례한다** — `weight`·`cash_usage_ratio`·순자산이 바뀌면 함께 움직인다.
  - **관측 4마커** `[ratio_notional_blocked]`(INFO 행위) · `[ratio_cap_skipped]`(WARNING fail-open) · `[ratio_cap_config]`(INFO 카나리아 `off|on`, `cutoff_price` 필수) · `[ratio_cap_clamped]`(WARNING). ⚠️ `[oversized_fallback]` 은 **"사려 했던 랏"** 이고 `order_engine` 수량-0 WARNING 은 **"ρ캡 차단 포함"** 이라 1:1 이 아니라 1:N 이다 — 도입 전후 같은 grep 합산 금지.
  - **롤백** = 해당 전략 `max_lot_ratio_mult = 20.0`. **PUT 은 즉시 / SQL UPDATE 는 다음 재시작에서만** 반영되고, 보유 중 장중 재시작은 금지(cycle232 D6)이므로 **장중 실효 수단은 PUT 뿐**이다. ⚠️ 키가 배포되기 **전**에는 PUT 이 무음 실패(미지 키 탈락) + `params` 통째 덮어쓰기로 SQL 값까지 지운다.
  - `compute_unit_qty_guarded` 의 notional 상한이 `position_ratio × 예산` 이라 **터틀 수량 ≤ 비중 수량**이 항상 성립 = 전환은 **순수 축소 방향**.
  - race 가드: `pending_buys`는 `place_order` 응답 직후 동기 영역에서 즉시 등록 — 기존 매핑 등록 규약과 동일하게 합산 일관성 보장

### WebSocket 시세 구독 — 한도·우선순위·거절 감지

**`MAX_SUBSCRIPTIONS = 41`(KIS 공식 한도)** · 총 슬롯 = `41 × (1 + 보조 세션 수)`.

- **우선순위(HIGH → LOW)**:
  1. **보유 포지션** — `registry.all()` 순회 `state.positions.keys()` 합집합. **한도 무시 절대 보장**(`bypass_limit=True`). 손절·트레일링 감시는 KIS 한도보다 우선한다.
  2. **익일청산 보류 대상** — `scheduler._pending_next_day_clear` 의 ticker. **한도 무시 절대 보장**. 09:00 KRX 시장가 청산을 놓치면 위험하다.
  3. **돌파 후보(BFB → VCP → VB → LTV)** — `_collect_breakout_tickers()`. LOW 처리 1순위 — BFB/VCP 는 폴링 없이 tick 으로만 매수를 평가하므로 구독이 곧 매수 기회다.
  4. **모멘텀 스캔** — `scan_stocks()` 결과. breakout 다음 순번.
  - **donchian_swing 은 WS 구독 대상에서 제외** — Pull 폴링(`_swing_buy_poll_loop`)이 매분 1회 `fetch_stock_detail`(REST)로 매수를 평가한다. 매수 *성공* 시(`pending_buys` 또는 `positions` 등록 확인) `bypass_limit=True` 로 즉시 TICK 구독을 추가한다.
- **drop 정책**: 잔여 슬롯(풀 전체 용량 기준) 부족 시 후순위(**breakout → momentum → swing**)만 잘린다. drop 개수는 **WARNING** 1행으로 노출한다 — `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H low_remaining=R pool_sessions=S pool_slots=T pool_subscribed=U pool_remaining=V`(`low_remaining` = 후순위 처리 후 남은 슬롯, 0 으로 clamp / swing=0 고정).
- **중복 제거**: 같은 종목이 여러 그룹에 있으면 HIGH 순위로 1회만 subscribe 한다.
- **HIGH 단독 41 초과(이상 케이스)**: ERROR 로그 + `system_logs` 기록. 보유는 무조건 add(`bypass_limit=True`), 후순위는 0개 — 운영자가 전략 비중을 줄여야 한다.
- **불변식**: HIGH(보유 + 익일청산)는 어떤 경우에도 drop 금지. 후순위 drop 은 ERROR 가 아니라 WARNING 이다(정상 운영 흐름이지만 가시화 대상).
- **통합 지점**: `src/realtime/websocket.py::subscribe(tr_id, tr_key, *, bypass_limit=False)` · `src/engine/scanner.py::subscribe_filtered_stocks(..., *, priority_groups=None)`(키: `positions` / `next_day_clear` / `swing` / `momentum` / `breakout`, `None` 이면 평탄 처리) · `src/engine/scheduler.py::_build_priority_groups()`.

**구독 ACK 추적과 진단**

- `KisWebSocket._subscriptions_acked` — 정상 응답(`rt_cd=="0"` + `msg1` 에 "SUBSCRIBE SUCCESS")에 add, `subscribe`/`unsubscribe`/거절 판정/재연결에 discard·clear. `get_acked_tickers()` 는 TICK TR_ID 로 거른 set 을 돌려준다.
- `GET /api/realtime/subscriptions` — `{ total, acked, fresh_60s, stale_60s, limit(=41 × (1 + 보조 세션 수)), tickers:{subscribed/acked/fresh/stale}, reconnect_count, ws_connected, last_tick_map, sessions:[{label, subscribed, acked, fresh, stale, limit, ws_connected, reconnect_count, tickers_detail}] }`. KST 기준이고 `ws_connected=False` 여도 200 이다.
- `scanner.get_scan_status()` 는 `tick_coverage_total/acked/fresh/stale` 4키를 함께 낸다(소스 = 풀 합집합 `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()`).

**구독 거절 감지** — 위치 = `src/realtime/websocket.py::_handle_raw()` 의 `_is_rejection_response`.

- 판정(하나라도 매칭): ① `rt_cd != "0"`(`body.get("rt_cd")` 가 None 이면 skip — Heartbeat 등) ② `msg1` 키워드(대소문자 무시) `ERROR / FAIL / REJECT / NOT ALLOWED / LIMIT / EXCEED / DUPLICATE / 한도 / 초과 / 이미 / 중복 / 허용되지 / 권한`.
- 처리: `self._subscriptions.discard((tr_id, tr_key))`(멱등) + ERROR 로그 + `write_log("ERROR", "[ws_subscribe_reject] tr_id=… tr_key=… rt_cd=… msg_cd=… msg1=…")` fire-and-forget.
- **호출자에게 시그널을 전달하지 않는다** — `subscribe()` 는 동기 시그니처를 유지하고, 거절은 다음 5분 `_scan_loop` 사이클에서 우선순위 큐로 자연 재시도된다. **재시도 큐 구현 금지.**
- 불변식: rt_cd 누락 응답(PINGPONG·캐럿 구분 실시간 데이터)은 거절 처리하지 않는다 · 같은 `(tr_id, tr_key)` 2회 거절은 discard 멱등 · 정상 응답 흐름(`SUBSCRIBE SUCCESS` AES iv/key 저장)은 불변(거절 분기에서 조기 return 만 한다).

### 외부 백테스트 서버 통합

20:00 AI 자문 직후 OpenAI 제안값을 외부 백테스트 서버로 검증한다. 운영 모니터링·진단 절차의 정본은 [`docs/backtest-monitoring.md`](../docs/backtest-monitoring.md).

- **외부 서버** `http://43.202.187.5:3846/mcp` (JSON-RPC 2.0 over Streamable HTTP/SSE). 인증 없음 — IP 화이트리스트만.
- **토글** `KIS_MCP_ENABLED`(DB `system_config.kis_mcp_enabled` 우선). 꺼져 있으면 `MCPClient.call_tool()` 이 `ConfigError` 를 내고 자문은 OpenAI 결과만 INSERT 하며 `backtest_summary=null` 로 자연 처리된다.
- **흐름**: 자문 INSERT → `_enqueue_backtest_jobs` 가 활성 전략마다 2 row(`params_kind` = current|recommended) INSERT → 60초 주기 `_backtest_poll_loop` 가 완료분을 `parameter_recommendations.backtest_summary` JSONB 에 동봉. 24h 미완료는 `failed` 로 마킹하고 종료한다.
- **YAML DSL 표현 가능 3종** = `momentum` / `volatility_breakout` / `donchian_swing`. **표현 불가 4종** = `long_tail_volatility` / `bull_flag_breakout` / `vcp_breakout` / `kojiro` → `BacktestNotSupportedError` → `skipped`.
- **기본 universe** = 코스피200 대표 5종목(`005930`/`000660`/`035420`/`005380`/`051910`), **기간 90일**.
- **자금 안전**: 백테스트 결과를 자동매매 파라미터에 **자동 반영하지 않는다**. 운영자가 Settings 에서 명시 적용할 때만 반영된다.
- **graceful**: `health_check()` 은 어떤 경우에도 raise 하지 않고 `False` 를 돌려준다. `GET /api/backtest/mcp/health` 는 항상 HTTP 200 으로 `{enabled, reachable, tools_count, error}` 를 낸다. 자문 INSERT 와 enqueue 는 `try/except` 로 분리돼 enqueue 가 실패해도 자문 row 는 남는다.
- **응답 키 규약**: `max_drawdown` 은 **양수 절대값**(`signInverted: true`) · `profit_loss_ratio → profit_factor` · `total_orders → total_trades` · `annual_return → cagr`. 외부 응답이 `data.result.metrics.{basic,risk,trading}` 3단 중첩이라 `_extract_metrics` → `_normalize_metrics` 가 8키로 평탄화한다.
- **타임아웃** connect 5s / read `BACKTEST_TIMEOUT_SECS`(기본 300s) / write 10s / pool 10s. 세션 만료(421)는 1회 자동 재초기화 후 재시도.
- 실측 검증 도구 = `scripts/verify_mcp_response_schema.py` — 외부 서버가 바뀌면 재실행한다.

### 거래소 라우팅 — 시각이 거래소와 호가유형을 정한다

전략 `exchange` 파라미터는 **DB 에 저장된 값**이고, 실제로 나가는 거래소는 **시각**이 정한다.

| 값 | 의미 | 비고 |
|---|---|---|
| `KRX` | 한국거래소 단일 | 모의(VTS) 지원 |
| `NXT` | 넥스트레이드 ATS 단일 | 실전 한정 |
| `SOR` | Smart Order Routing (KIS 가 KRX/NXT 자동 분배) | 실전 한정. **주문에 쓰지 않는다**(폐기 표시) |

`place_order`/`cancel_order` body 에 `EXCG_ID_DVSN_CD` 로 전송한다. 모의는 SOR/NXT 를 KIS 가 거절하므로 KRX 만 쓴다.

**시각 기반 라우팅** — `order_engine._route_exchange_by_clock` 이 `market_state.MARKET_TABLE` 만 읽어 판정한다(`order_engine.py` 안에 시각 리터럴 0건).

| 구간 | 거래소 | 1차 호가유형 | 폴백 |
|---|---|---|---|
| 프리장 08:00~08:50 | DB 값(NXT) | **`27` GTP지정가**(`ORD_UNPR` = `step_up(현재가,5)`) | `00` |
| 정규장 09:00~15:30 | **KRX 강제** | `01` | `00` |
| 15:30~16:00 | DB 값 유지 | 현행 유지 | — |
| KRX 애프터 16:00~20:00 | **KRX 강제** | **`44` 최유리지정가(`ORD_UNPR=0`)** | `41` 지정가 + `step_down(5)` |

- **정규장에 NXT/SOR 을 쓰지 않는다는 것이 사용자의 명시 확정 규약이다**("SOR이 최적호가라는 보장도 없다" — 재론 대상 아님). 우리가 보낼 수 있는 호가유형이 그 시각 그 거래소에 아예 없는 창(프리장·15:30~16:00)만 DB 값을 그대로 쓴다.
- 운영 DB 7 전략의 `exchange` 는 **전부 `NXT`** 이고 라우팅은 그 값을 바꾸지 않는다(읽기 전용으로 가로챈다).
- **`44` 는 시장가가 아니다** — 반대편 최우선호가 지정가라 실질 최악이 1틱(20~21bp)으로 기존 폴백 5틱(101~106bp)보다 작다. `ORD_UNPR=0` 을 쓰는 근거는 비대칭이다: 0 이 틀리면 즉시 거부가 알려 주고 41 폴백이 받지만, 가격이 틀리면 미체결 잔존 = 손절 **무음** 실패다.
- **폴백은 거부 사유 분류에 의존하지 않는다** — 44 거부 사유 어느 것도 현재 msg1 키워드에 걸릴 근거가 없고, 원문을 모르는 채 키워드를 추측하면 다음 사람이 "이미 처리했다"고 오독한다. 폭주 봉인 3종 = TTL 항상 등록 · 종목당 5회 포기 래치 + `[after_exit_giveup]` CRITICAL · 익일청산 전환.
- **프리장 `27` 의 정체성** = 미체결 잔량을 거래소가 프리마켓 종료(08:50)에 **일괄 취소**한다. `00` 은 그 자동취소를 받지 못해 미체결이 NXT 정규장(09:00:30~)으로 새고, 그 누출은 역선택 방향으로만 치우친다(프리장 목표가는 `main` 시가로 09:00:05 에 다시 계산되므로 넘어간 주문은 이미 폐기된 목표가의 잔상이다). 게이트 4중(실전·NXT·`market_state` 표에서 그 시각 유효·프리장) 중 하나라도 실패하면 `00` 이 그대로 나간다(fail-safe, 파라미터 없음 — 롤백은 1커밋 revert).
- **매도는 `27` 로 바꾸지 않는다** — GTP 매도는 08:50 자동취소가 `_selling` 을 ≈09:45 까지 잠가 손절 재평가를 억제한다. 현행 `00` 은 09:00:30 NXT 정규장에서 시세 아래 지정가라 거의 확실히 체결돼 안전망으로 기능한다(청산 경로를 좁히지 않는다).
- 상세 = `src/engine/CLAUDE.md` §order_engine.py · 자문 = `_workspace/domain_consult/cycle291_pre_nxt_gtp_20260913.md`.

**장중 킬스위치 2키** — 7 전략 전부의 `DEFAULT_PARAMS` + `param_catalog` 에 코드 상수와 같은 값으로 등재돼 있다.

| 키 | 기본값 | 허용값 | 부재/오타 시 해석 |
|---|---|---|---|
| `order_exchange_clock_mode` | `enforce` | `enforce` · `sell_only` · `off` | `enforce`(라우터에 mode 화이트리스트가 없어 미지 값은 조용히 `enforce` 로 읽힌다) |
| `after_market_exit_division` | `"44"` | `"44"` · `"41"`(문자열) | `"44"`(허용 밖·정수·부재는 전부 이 값으로 폴백) |

롤백은 **`PUT` 뿐**이다 — `strategy_config` SQL 직접 UPDATE 는 다음 백엔드 재시작에서만 반영되고(cycle232 D6 가 보유 중 장중 재시작을 금지), 1커밋 revert + 재배포는 그 자체가 그 창의 재시작이다.

⚠️ **전제 — 두 스위치는 `exchange ∈ {"NXT","SOR"}` 일 때만 효력이 있다.** `_route_exchange_by_clock` 의 clause 1(`base ∉ {"NXT","SOR"}` → 그대로 반환)이 mode 검사보다 **앞**에서 발화하므로, 어떤 전략의 `exchange` 가 `"KRX"` 로 바뀌면(코드 기본값이 이미 그렇다) `enforce`·`sell_only`·`off` 세 값이 그 전략에서 **완전히 동일한 무동작**이 된다. 운영 DB 가 전부 `NXT` 라서 아래 절차가 실제로 작동한다. `[order_channel] … base=NXT exchange=KRX reason=krx_by_clock` 에서 `base=NXT` 가 찍혔다는 것이 곧 그 전략이 clause 1 을 지나 mode 검사까지 도달했다는 뜻이다(같은 날 `nxt_tradable=false` 종목은 `[nxt_downgrade]` 로 base 가 먼저 KRX 가 되어 마커가 침묵한다 — 그 종목에 대해서는 스위치가 무동작이다). `exchange` 를 KRX 로 마이그레이션하는 날부터는 이 전제가 깨지고 `[order_channel] reason=base_krx` 가 그 증거다 — 그날은 아래 절차 대신 곧바로 코드 재배포(`order_engine.py`)가 필요하다.

⚠️ **두 스위치는 전략별이다 — 전역 킬스위치가 없다.** 보유가 여러 전략에 걸쳐 있으면 사고 중 그 전략 **각각**에 PUT 해야 한다. 하나만 누르고 "껐다"고 믿지 않는다.

⚠️ **첫 PUT 이 그 전략의 두 값을 DB 에 영구 고정한다.** `PUT /api/strategies/{id}/params` 는 병합된 **전체** `params` dict 를 저장하므로, 어떤 키든 그 전략에 처음 PUT 하는 순간부터 이 두 값도 DB 에 박혀 그 뒤로는 **코드 상수를 바꿔도 그 전략에는 반영되지 않는다**(재시작해도 DB 값이 이긴다). 사고 중 한 값을 되돌렸으면(예: `off`→`enforce`) 그것으로 끝이 아니라 **그 전략은 이제부터 계속 DB 값을 산다**는 뜻이다 — 익일 `SELECT strategy_id, params->>'order_exchange_clock_mode', params->>'after_market_exit_division' FROM strategy_config` 로 어느 전략이 DB 지배로 넘어갔는지 확인한다.

**사고 중 조작 순서 (스위치를 만지기 전에 반드시 이 순서로)** —

0. 스위치를 만지기 전에 세 마커로 증상부터 가른다. 거부 / 미체결 / 악체결은 처방이 반대다. 보유 중인 **전략마다** 아래를 확인한다.
   - `[order_channel_config] strategy= mode= division=` → 지금 살아 있는 값. **이 마커는 그 전략이 주문을 낼 때만 찍힌다** — 부재는 실패의 증거가 아니라 "아직 그 전략이 주문을 내지 않았다"는 뜻이다. PUT 직후의 즉시 증거는 이 마커가 아니라 **PUT 200 응답의 `data.applied`** 다.
   - `[after_exit_division] ticker= div= unpr= cur= dial=` → 변환이 일어났는가, **`cur=` 이 0 인가**
   - `[after_exit_rejected]` / `[after_exit_giveup]` → 거부인가 아닌가
1. **매도 거부**(`[after_exit_rejected]` 있음) — `order_exchange_clock_mode` 는 만지지 않는다. `[after_exit_division]` 의 `cur>0` 을 **먼저 확인**하고 그때만 `after_market_exit_division="41"`. `cur=0` 이면 **41 금지** — 44 로 두고 포기 래치가 다음 09:00 청산으로 착지시키게 둔다.
2. **매도가 접수됐는데 미체결/악체결**(`[after_exit_rejected]` 없음) — `41` 의 본래 용도. 같은 `cur>0` 조건.
3. **매수만 거부**(LTV 야간) — `order_exchange_clock_mode="sell_only"`. 매도·취소는 계속 KRX 라 44/41 청산이 살아 있다. 애프터 창에서 mode 를 만지는 유일한 정당 용도다. ⚠️ 이 값은 16:00~19:50 LTV 야간 매수도 함께 되살린다(방어 다이얼이 아니다).
4. **그래도 안 되면** `off` 가 아니라 `PUT {"exchange":"KRX"}` — clause 1 이 mode 검사보다 앞서 발화해 KRX 로 고정되면서 44/41 전환이 보존된다(부작용은 프리장 주문도 KRX 로 가는 것 하나).
5. **`off` 는 라우터 자체 고장 증거**(`reason=probe_error` 반복)가 있을 때만 — 애프터 44/41 청산까지 함께 죽는다. 안전한 후퇴가 아니다.

### 보드(매매 시간대) 화이트리스트
각 전략 `tradable_boards` 파라미터로 매매 가능 보드를 결정:

| Board | 시간 | 전략 매핑 (기본값) |
|---|---|---|
| `pre_nxt` | NXT 프리 08:00~09:00 | LTV |
| `krx_open` | (사이클 26 비활성 — enum 호환만 유지) | momentum (`DEFAULT_TRADABLE_BOARDS=("krx_open","main")` + `session._DEFAULT_TRADABLE_BOARDS` 양쪽에 잔존). 단 `_BOARD_SCHEDULE` 이 이 보드를 활성화하지 않아 **실효 0** — momentum 매수는 `main` 에서만 평가된다 |
| `main` | KRX 메인 09:00~15:39:59 (매수 중단 15:20) | momentum / VB / LTV / donchian_swing / bull_flag_breakout / vcp_breakout / kojiro |
| `krx_after` | (사이클 26 비활성 — enum 호환만 유지) | 미사용 |
| `post_nxt` | NXT 애프터 15:40~20:00 | LTV |

**RiskManager 보드 가드**: `on_tick` 매수 신호 평가 전 `session_tracker.is_tradable(strategy_id, params)`로 활성 보드 ∩ tradable_boards 체크 — 비활성 보드에서는 신호 평가 자체 skip.

---

## 3. 전략 A: 상한가 모멘텀 상세

### 종목 선정
- 09:30 이후 등락률 순위 API로 5분 주기 필터링
- 1차 필터: 전일종가 대비 등락률 +15% 이상 상승 종목
- 2차 필터: 시가총액 1,000억 원 이상 AND 당일 거래대금 200억 원 이상
- ETF/ETN 제외 (KODEX, TIGER, 인버스, 레버리지 등 + RISE/KoAct/PLUS/TIMEFOLIO/WOORI/FOCUS 키워드)
- 최대 40개 종목으로 제한

### 매수 규칙
- **진입 조건**: 전일종가 대비 현재가가 +29.0% 이상 도달 (29% 미만 → 29% 이상 돌파 순간만)
- **제외**: 이미 상한가(+30%)에 도달한 종목은 매수 대상에서 제외
- **주문 방식**: 시장가 매수
- **투자 비중**: 할당 자금의 25% (1종목당) — 자금 부족 시 1주 fallback 동작
- **중복 방지**: 동일 종목이 이미 보유 중이거나 미체결 매수 주문이 있으면 매수 금지
- **매매 보드**: KRX_OPEN + MAIN만 (NXT 보드 비활성 — 상한가 기준이 KRX이므로 NXT 단독 +29% 의미 약함)
- **거래소 라우팅**: 기본 KRX — 실제로 나가는 거래소는 시각이 정한다(§거래소 라우팅)

### 당일 손절
- **조건**: 매수 체결가 대비 현재가가 `stop_loss_rate` 이하 도달 시 즉시 시장가 전량 매도
- **주의**: 기준은 반드시 "매수 체결가"이지 시가가 아님
- **코드 기본값**: `stop_loss_rate = -7.5%` (`src/engine/strategies/momentum.py::DEFAULT_PARAMS`)
- **운영값 = DB `strategy_config.momentum.params.stop_loss_rate` 가 진실 원천이다** — 코드 기본값도 이 문서의 숫자도 아니다. 마지막 실측 = **`-2.4%`**(사용자 수동 apply).
- **운영값이 코드 기본값과 다르면 화면과 로그가 함께 알려야 한다** — `frontend/src/pages/Strategies.tsx` 가 전략별 임계를 표시하고, `momentum.py` 손절 로그가 임계를 같은 줄에 emit 한다(`"손절 신호: … 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"`). 코드 기본값만 보고 판단하면 오인한다.
- **운영값을 바꾸면 이 문서도 함께 고친다.**

### 익일 청산 (다음 영업일 NXT 프리 08:00 → NXT 거래가능 여부로 분기)
다음 영업일 보유 종목에 대해 **NXT 거래가능 여부**로 청산 시점을 분기한다.

#### 분기 기준 — KIS CTPF1002R 사전 조회 (Primary) + 시가 수신 (Fallback)
KIS MCP 4질의 결과(2026-05-11) **CTPF1002R(주식기본조회) 응답의 두 필드로 종목별 NXT 등록 여부를 사전 조회 가능**함이 확정됨:
- `cptt_trad_tr_psbl_yn` — NXT 거래종목여부 (Y/N)
- `nxt_tr_stop_yn` — NXT 거래정지여부 (Y/N)
- **파생값**: `nxt_tradable = (cptt_trad_tr_psbl_yn == "Y") AND (nxt_tr_stop_yn == "N")`

**Primary 판별**: `stock_master` 테이블(24h TTL 캐시) → `inquire_stock_basics(ticker)` (CTPF1002R)
- Lazy: 매수 진입/익일 청산 직전 조회 → miss/stale 시 KIS 호출 후 upsert
- Eager(향후): `_boot()`(기동 직후)에서 후보 일괄 갱신 (1차에서는 Lazy만)

**Fallback**: stock_master 조회 실패 또는 미보강 종목 → 기존 WebSocket 시가 수신 휴리스틱 유지
- `ticker_prices[ticker]["open_price"] > 0` (또는 `_resolve_open_price` 폴링) → NXT 거래 가능 추정
- 시가 미수신 → NXT 거래 불가 추정

#### (a) NXT 거래 가능 (`nxt_tradable=True` + 시가 수신) — 갭상승 여부로 분기
- 매수 체결가 대비 +10% 이상 갭상승 → 고점 -2% 트레일링 스탑 모드로 전이. **단 트레일링 판정은 09:00 부터** — `risk._defers_pre_market_exit`(2026-08-06)가 PRE_NXT 단독 구간에서 `_PRE_MARKET_EXIT_EVAL_STRATEGIES`(=LTV) 외 전략의 청산 평가를 보류하므로, momentum 은 08:00~09:00 동안 트레일링·손절이 평가되지 않고 09:00 KRX 시세로 재개된다. **cycle238 (2026-09-02)** — 게이트가 `session_tracker.active`(30초 stale) 단독이라 08:00:00~29 에 매일 열리던 구멍을 `boards_at(_now_kst())` 시각 폴백 OR 로 닫았다(08:00 정각부터 보류). 09:00 정각은 stale `active` 잔존 ≤30초 보류 유지(현행 동일)
- 갭상승 미달 → **(b) 와 동일하게 `_pending_next_day_clear` 보류(reason=`nxt_underthreshold`) → 09:00 KRX 시장가 단일 청산**(`_drain_pending_next_day_clear`, Tier 1 2026-07-23, 자문 `nxt_prelimit_stale_selling_orderflow`). **08:00 NXT 프리 지정가 조기청산은 내지 않는다** — 얇은 NXT 프리 유동성에서 지정가 미체결 만료가 어느 `_selling` discard 경로에도 걸리지 않아 `_selling` 영구 잔존 → `risk.on_tick` 손절/트레일링 종일 억제를 만든다.

#### (b) NXT 거래 불가 (`nxt_tradable=False` OR 시가 미수신) — 09:00 KRX 메인 시가 확정 후 시장가 청산
- 08:00 시점에는 **청산 보류** (`_pending_next_day_clear` set 에 등록)
- **NXT 등록 사전 판별이 False면 30s 안정화도 거치지 않고 즉시 보류** (불필요한 NXT 주문 시도 0)
- 09:00 KRX 메인 시가 확정(`_confirm_breakout_open_prices(board="main")`) 직후
  `_drain_pending_next_day_clear()` 가 시장가로 일괄 정리
- 정규장 시간대이므로 시장가 OK

#### 거래소 라우팅 사전 다운그레이드
- `OrderEngine._strategy_exchange(strategy_id, ticker=...)` — ticker 인자 추가
- 전략 `exchange`가 NXT/SOR 이지만 `stock_master.get(ticker).nxt_tradable=False`이면 **KRX 강제 다운그레이드**
- `system_logs`에 `[nxt_downgrade]` prefix 1행 (strategy/ticker/원래 exchange/적용 exchange)

#### 사후 보강
- 매도 거부 시(KIS `APBK0918` + "장운영시간이 아닙니다" 등) `is_market_closed_rejection()` 가드로
  **메모리 `state.positions` 및 DB `positions` 보존** (재시도하지 않고 다음 거래 가능 시각에 자연 재트리거)
- 거부 발생 직후 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강 → 같은 종목 재 NXT 호출 방지
- **시가 미수신 시 `high_since_buy` 폴백 + 갭률 0% 즉시 청산 경로는 제거** (전일 고가 혼입으로 좀비 포지션 위험)
- **시장가 호가 불가 거부(`is_market_order_disallowed`, APBK1943 "시장가호가불가" 등) Phase C, 2026-05-11**: 시장가 매도 경로(`limit_price=0`)에서 `step_down(현재가, 5)` 지정가 1회 폴백. 폴백 실패 시 메모리/DB positions 보존, cooldown 등록 안 함(청산 의무) → 다음 사이클 재트리거. 2026-05-11 계양전기(012200) 09:00:21 매도 ×3 + 수동 매도 ×2 실패 사고 대응

#### 매도 거부 정책 — `SellRejectionTracker`

`src/engine/sell_rejection.py::SellRejectionTracker` 단일 정책 객체가 4 분류 (market_closed / market_order_disallowed / insufficient_quantity / insufficient_cash) 를 통합 관리한다. `OrderEngine.execute_sell` 진입 직후 `is_blocked(ticker)` 게이트가 KIS 호출 전에 차단한다.

**`market_closed_rejection` 2단계 TTL**
- KRX 메인 시간대(09:00~15:30 KST) 거부 = **5분 TTL** (일시 장애 가정 — KIS 일시 거부 후 자연 복구 시나리오 빠른 재진입 보장)
- NXT 시간대(08:00~09:00 / 15:30~20:00 KST) 거부 = **다음 KST 09:00 TTL** (장운영시간 외 명확 — KRX 메인 개장까지 차단 유지)
- TTL 미경과 시 INFO `[market_closed_blocked] ticker=... reason=...` 1줄/ticker/일 cap → 동일 종목 재시도 폭주 차단

**`market_order_disallowed` 30초 TTL + NXT 폴백 실패 익일 청산 전환**
- 시장가 매도 폴백(`step_down(현재가, 5)` 지정가 1회) 결과(성공/실패) 무관 **30초 TTL** 등록 (동일 tick 폭주 차단)
- NXT 시간대 폴백 실패 시(`is_nxt_session=True AND fallback_succeeded=False`) → `_pending_next_day_clear.add((ticker, strategy_id))` 자동 등록 + `[next_day_clear_deferred]` WARNING → 다음 영업일 09:00 KRX 시장가 일괄 청산 자연 전환
- 지정가 매도(`limit_price>0`)는 폴백/TTL 등록 모두 안 함 (운영자 명시 지정가 의도 보존)

**`insufficient_quantity` reconciliation**
- 거부 발생 시 tracker history 적재(차단 X — positions 메모리/DB 제거가 자연 차단)
- 즉시 `[positions_reconciliation] ticker=... strategy=... reason=insufficient_quantity` INFO 1행
- 1회 `get_balance()` 호출 → 실제 잔량 > 0 인 경우 (수동 부분매도 보호 시나리오) INFO `실제 잔량 확인: ... qty=N — positions 재등록 권고` (자동 재등록 미구현 — 운영자 수동 확인 권고)
- `get_balance()` 실패 graceful (DEBUG 로그만, positions 제거는 이미 완료)

**호환 layer + reset 정책**
- `OrderEngine._market_closed_blocked` / `_market_closed_blocked_logged_today` 2 property 보존 (사이클 52 테스트 코드 무수정, dict/set 인스턴스 동일성 보장)
- `OrderEngine.reset_daily_state()` → `self._sell_rejection.reset_daily()` 4 필드 (`_blocked_until` / `_blocked_reason` / `_logged_today` / `_history`) 일괄 위임 + `_nxt_downgrade_logged_today.clear()` 보존
- ticker별 history `deque(maxlen=20)` — 시간당 과다 거부 알람 hook 용 버퍼.

### 트레일링 스탑 상세
- NXT 프리 시가 이후 고점을 실시간 추적
- 현재가가 고점 대비 -2% 이하로 떨어지면 시장가 매도 트리거
- 수식: `(고점 - 현재가) / 고점 * 100 >= 2.0` 이면 매도

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 25%
- 일일 최대 손실 한도: 할당 자금의 5% → 도달 시 당일 매매 중단
- 동시 보유 종목 수: 최대 4종목

---

## 4. 전략 B: 변동성 돌파 상세

### 핵심 개념
- **노이즈 비율** = 1 - |Close - Open| / (High - Low)
- **동적 K값** = 최근 20일 평균 노이즈 비율
- **보드별 매수 목표가** = 보드 시가 + (전일 Range × K값 × 보드별 K 곱)

### 보드별 시가/타겟 분리
보드마다 시가가 다르므로 별도로 추적:
- `_targets[ticker]["boards"]["main"]` ← KRX 09:00 시가 + (전일Range × K × `k_value_krx_main`)
- `_targets[ticker]["boards"]["pre_nxt"]` ← NXT 프리 첫 거래 시가 + (전일Range × K × `k_value_nxt_pre`)
- `_targets[ticker]["boards"]["post_nxt"]` ← NXT 애프터 첫 거래 시가 + (전일Range × K × `k_value_nxt_post`)
- 보드별 K 곱 기본값 1.0. NXT는 거래대금이 KRX의 ~10%로 변동성 큼 → 1.2~1.5로 보수 운용 권장

### 종목군
- 코스피 + 코스닥 전체에서 거래대금/시총 조건 필터
- 조건: 시가총액 1,000억 원 이상 AND **전일** 거래대금 200억 원 이상 (Settings에서 변경 가능)
  - 거래대금은 거래량순위 API 응답의 `prdy_vol × (stck_prpr - prdy_vrss)`로 산출 → 시간 의존 제거
- ETF/ETN 제외
- 최대 100종목

### 데이터 준비 (`_boot()` 시점 = 기동 직후)
- 각 종목의 최근 22일 일봉 데이터(시/고/저/종) 조회 (KIS FHKST03010100, 100일 응답)
- candles[0]이 오늘이면 candles[1]을 "전일"로 사용 (장 시작 전 빈/부분봉 방어)
- 종목별 K값 계산 + 전일 Range로 `target_offset_base` 산출
- `prev_range == 0` 또는 `target_offset_base == 0` 종목은 skip
- 전일 종가를 `scanner.ticker_prev_close`에 사전 등록

### 시가 확정 + 매수 규칙
- 보드 진입 시점에 `_confirm_breakout_open_prices(board=...)` 호출 → 보드별 시가 확정 + Target 계산
- **진입 조건**: 현재가 >= 활성 보드의 Target_Price 돌파 순간 (이전 틱 < target AND 현재 틱 >= target). 보드별 `_prev_price[ticker][board]` 분리
- **주문 방식**: 시장가 매수
- **투자 비중**: 할당 자금의 10% (1종목당) — 자금 부족 시 1주 fallback
- **동시 보유**: 최대 10종목
- **매매 보드**: MAIN 단독 (09:00~15:20). **PRE_NXT·POST_NXT 매수 모두 비활성** (사이클 26, 2026-05-20 — PRE_NXT 는 OVERNIGHT 위험 차단, POST_NXT 는 당일 15:20 일괄매도 정책 보존)
- **거래소 라우팅**: 기본 KRX — 실제로 나가는 거래소는 시각이 정한다(§거래소 라우팅)

### 보드별 시가 확정 호출 — `board` 인자 명시 의무
- `_confirm_breakout_open_prices()` 의 자동 결정 분기는 `SessionTracker.active` 를 main → post_nxt → pre_nxt 우선순위로 검색해 보드를 추론한다. `SessionTracker._session_loop` 가 **30초 주기**라 보드 경계(08:00 / 09:00 / 15:30) 정각 호출과 race 가 난다.
- **불변식**: 보드 경계 정각 호출은 반드시 `board="..."` 를 **명시 인자로** 전달한다. 자동 결정에 의존하지 않는다.
  - `TIME_PRE_NXT_OPEN` (08:00) → `board="pre_nxt"` 명시
  - `TIME_KRX_OPEN_CONFIRM` (09:00:05) → `board="main"` 명시
  - `TIME_KRX_MAIN_CLOSE` (15:30) → `board="post_nxt"` 명시
- 근거 = 09:00:05 호출이 stale 캐시 탓에 `board="pre_nxt"` 로 폴백해 `_targets[ticker]["boards"]["main"]` 키가 끝내 안 채워지면 그날 KRX 메인 매수 신호가 통째로 0건이 된다(2026-05-14~15 실측).
- **자동 결정 허용 호출**(시점이 가변이라 명시가 부적절): 중간 부팅 호출 · `now > TIME_KRX_OPEN_CONFIRM` 조건의 스캔 시작 직전 재확정.

### 손절
- **조건**: 매수 체결가 대비 -3%
- **주문**: 즉시 시장가 전량 매도

### 강제 청산 — 보드별 분리
- **15:20 KRX 메인 매수 중단 + 강제 청산**: POST_NXT 활성 여부와 **무관하게** 각 전략의 `check_force_clear()` 를 호출해 반환 종목을 청산한다. 보유 유지 여부는 `check_force_clear()` 본체가 결정한다(`keeps_post_nxt` 는 로그로만 남는다).
- **VB·LTV는 15:20 일괄 청산**: VB `DEFAULT_TRADABLE_BOARDS = ("main",)` / LTV `("pre_nxt", "main", "post_nxt")`. VB는 모든 보유 청산, LTV 는 `_limit_up_reached` 제외(상한가 모드만 익일 보유). LTV 상한가 모드의 POST_NXT 손절 모니터링은 `risk.on_tick` 청산 평가가 보드 가드와 무관하게 작동한다.
- **VB 익일 청산 안전망**: VB 도 `_execute_next_day_clear` 대상이다. 당일 15:20 청산이 비상 상황으로 누락되면 다음 영업일 NXT 프리 시가에서 자동 청산한다. `check_exit_signal` 익일 청산 분기 순서 = STOP_LOSS 우선 → pending 가드 → NEXT_DAY_CLEAR.
- **19:50 NXT 애프터 매수 중단**: 모든 활성 전략 `buy_disabled = True`. POST_NXT 매수가 VB/LTV 에서 비활성이라 19:50 강제 청산 코드 부재는 실질 영향이 없다(LTV 상한가 모드 종목은 정책상 익일 청산 의도).
- **20:00 NXT 애프터 종료**: VB 는 정상 경로상 OVERNIGHT 보유 없음 (15:20 청산). LTV 상한가 모드 종목 + 안전망 발동 VB 종목만 다음 영업일 NXT 프리 청산 대기.

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 10%
- 일일 최대 손실 한도: 할당 자금의 5%

### 재진입 쿨다운
- **쿨다운**: 청산 후 **2영업일** (`reentry_cooldown_days=2`, BFB 3영업일 / VCP 7영업일과 구분 — VB 당일청산 특성상 짧게 설정).
- **배선**: `OrderEngine.on_position_closed(ticker)` 훅에서 `register_cooldown_after_exit(ticker)` 즉시 호출(달력일 근사 = today + days + 2) → `_refine_cooldown_business_days(ticker)` 비동기 정정(CTCA0903R `add_business_days`로 정확한 N영업일 교체, 실패 시 근사값 유지 graceful).
- **매수 게이트**: `check_buy_signal`의 `is_sold_today` 가드 직후 `_cooldown_until[ticker] >= today` 면 즉시 NONE (돌파 조건 완비 여부 무관).
- **영속 금지**: `_cooldown_until`는 크로스데이 상태 — `_reset_daily_state`/`prepare()` 리셋 대상에서 절대 제외 (일일 초기화 시 매일 소멸하면 재진입 방어가 무력화됨).

### 09:00 직후 진입 보류 `open_entry_hold_secs` — **VB 에도 적용된다**
VB·LTV 공통 계약이라 정본은 아래 §5 끝의 전용 절에 한 번만 둔다. 요약 = KRX 개장 후 기본 **90초**
동안 **신규 매수 신호만** 보류(청산 계열 전부 무접촉), **지혈이며 근본 시정이 아니다**.
→ §5 「09:00 직후 진입 보류 `open_entry_hold_secs`」

---

## 5. 전략 C: 롱테일 변동성 돌파 상세

VB와 진입 로직 동일 + 상한가 도달 시 익일 청산 모드로 전환해 긴 꼬리(롱테일) 추구.

### VB 대비 차이
- 추가 진입 필터: 전일대비 ≥ `min_prdy_rate`(기본 5%)
- 연속상한가 종목 제외 (`exclude_consecutive_limit`, 기본 2일 — 전일 기준 N일 연속 +25%↑면 후보 제외)
- 상한가 도달(+29%) 시 → 익일 청산 모드 전환(`_limit_up_reached` set)
- **2단계 청산**:
  - 당일 모드(상한가 미도달): 손절 -3%, 15:20 강제 청산 보류 가능(POST_NXT 활성 시 19:50까지)
  - 상한가 모드: 손절 -5%, 다음 영업일 NXT 프리 시가에서 갭상승 +10% → 트레일링 -2% / 그 외 즉시 매도
- 보드별 K값 분리는 VB와 동일

### 매매 보드 / 거래소 라우팅
VB와 동일.

---

### 09:00 직후 진입 보류 `open_entry_hold_secs` — **지혈이며 근본 시정이 아니다**

**VB·LTV 공통.** KRX 개장 후 `open_entry_hold_secs` 초 동안(기본 **90**, 창 = KST
`[09:00:00, 09:01:30)` — 하한 포함·상한 배타) **신규 매수 신호만** 내지 않는다.
청산·손절·트레일링·익일청산·15:20 강제청산은 **전부 무접촉**이다.

- **왜**: 목표가의 기준 시가가 KRX 09:00 시가가 아니라 통합 채널 `fields[7]`(= 세션 시가, 프리장 체결이 있었으면 프리장 시가)이었다. 그 창의 체결은 "체결가 ≥ KRX시가+offset" 을 20/20 전부 위반했고(이후 구간 57%) Fisher p=6.4e-5 다 — **행동의 근거는 손익이 아니라 이 메커니즘**이다.
- **⚠️ 지혈이다**: 오염된 `[7]` 은 **일-스코프 상수**라 90초 뒤에도 값이 그대로다. 이 보류는 통계적으로 최악인 구간만 피할 뿐 오염 자체를 고치지 않는다(09:01:30 이후에도 57%가 위반한다). 보류 후 성적이 기대만큼 안 좋아져도 그건 이 조치의 실패가 아니라 **근본이 안 고쳐졌다는 증거**이고, 좋아져도 근본 시정을 미룰 근거가 되지 않는다.
- **보드 무관 — 시간창 단독 판정**. `tradable_boards` 로 분기하지 않는다(09:00:00~09:00:30 은 세션 트래커 30초 주기 탓에 보드가 아직 `pre_nxt` 로 잡힐 수 있는데 그건 stale 캐시 산물이라, 보드로 나누면 그 30초가 통째로 구멍이 된다). **LTV 의 08:00~09:00 진짜 프리장 매수는 창 밖이라 무접촉**이다(그 구간의 `[7]` 은 그 보드의 올바른 기준가다).
- **판정 자리 = 돌파 발사점**(계좌 SOFT 게이트 뒤). 최상단 금지 — 보류 구간에 `_prev_price` baseline 이 동결돼 해제 후 첫 틱이 거짓 돌파가 되고(cycle233 C233-F1), 무엇을 살 뻔했는지도 기록할 수 없다. **보류 중에도 baseline 갱신은 계속된다.**
- **fail-open 이 계약**: 키 부재·`None`·빈 문자열·파싱 실패(`inf`/`nan` 포함)는 전부 **0 = OFF = 현행 행위**. 읽는 쪽 `[0, 600]` 클램프(오타 `10000` 이 오전을 통째로 막는 것을 차단). fail-closed 는 P0-1 유령 키가 BFB/VCP 를 전 기간 체결 0건으로 만든 그 방향이다.
- **관측 2종** (둘 다 INFO, 관측 실패는 매수 판정을 **절대** 바꾸지 않는다):
  - `[open_entry_hold_config] strategy= hold_secs= until= source=` — 그날 적용값 카나리아. cap 은 **1회/(전략, 값)/일**이라 값을 바꾼 날에만 2행이 된다. ⚠️ `source` 는 출처가 아니라 **값 동등성 추론**이다(`DEFAULT_PARAMS` 와 같으면 `default`, 다르면 `db`). ⚠️ 계좌 SOFT 게이트가 활성인 날에는 **LTV 의 이 카나리아가 0행**이다 — LTV 는 `GATE_FIRST_FILES` 멤버라 게이트 If 가 `check_buy_signal` 의 첫 문장이어야 하고(AST 봉인) 로그 emit 은 부작용이라 그 앞에 둘 수 없다. 그날 LTV 적용값은 `PUT` 응답이나 `strategy_config` 로 확인한다.
  - `[open_entry_hold_blocked] ticker= board= current_price= target= board_open= prev= k= offset= elapsed_secs= prdy_close=` — **would_buy 정본**, 1회/(ticker, 전략)/일. ⚠️ `system_logs` 의 전략 INFO 는 실측상 최근 며칠만 잔존하므로 재검토 창이 닫히기 전에 일일 추출 적재가 필요하다.
- **롤백**: `PUT /api/strategies/{id}/params {"open_entry_hold_secs": 0}` — **즉시** 반영(라우트가 in-memory `config.params` 를 덮는다). `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만** 반영되고, cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **장중 실효 수단은 PUT 뿐**이다. 키가 전략별이라 VB 90 을 유지한 채 LTV 만 끌 수 있다.
- **`PARAM_RANGES`/`INT_PARAMS` 편입 금지** — 진입 정체성 상수. AI 자문 자동 적용 경로에도 넣지 않는다(최근 손실을 목적함수로 삼는 튜너는 n≤20 에 과적합해 "최근 손실 거래를 지우는 값" 으로 수렴한다). AST 가드 G-262-1 이 런타임 dict + 소스 리터럴 이중으로 강제한다.
- **⚠️ DB 선반영 금지** — `_load_strategy_config`(scheduler)도 `PUT /api/strategies/{id}/params`(routes)도 **"코드에 이미 있는 키만 덮는" 오버레이**라, 배포 전 PUT 은 미지 키를 조용히 버리는 **무음 실패**이고 `params` JSONB 를 통째로 덮어 먼저 넣은 SQL 값까지 지운다. **배포 후에 PUT 한다.**
- **해제 조건(조건부 만료)** — (i) 근본 시정(기준가 출처 교체) 배포 **그리고** (ii) 시정 후 20 거래일 동안 `[open_entry_hold_blocked]` 가 그 창에서 발화 0~희소. **둘 다 충족 전에는 유지**한다. **자동 재검토 트리거** = 블록된 거래의 **추정** 손익이 2주 연속 양(+)이면 창 축소·해제를 재논의한다(레짐이 갭업→갭앤고로 바뀌면 막은 거래가 승자가 된다). 그 추정은 진입 다리만 로그로 남고 청산 다리는 시뮬레이션이라 보고할 때 "실측"이 아니라 **"추정(상관 0.79)"** 으로 표기한다.
- **벽시계 임계의 구멍**: 세션 트래커가 30초 지터로 늦게 뒤집히면 같은 거래가 09:01:31 에 그대로 난다(실측 경계 = 09:01:34 1건, 창 밖 4초).

### `main` 기준가 출처 `open_price_scope_mode` — 사용자 결정 D1

**VB·LTV 공통.** `board=="main"` 목표가의 기준가는 **KRX REST `stck_oprc`(`J`) 단일 출처**다.
사용자 결정 원문 = *"체크할 필요가 없이 KRX시가를 쓰는게 원칙"*. 위 `open_entry_hold_secs`
가 최악 구간을 피하는 **지혈**이라면, 이건 오염된 기준가 자체를 REST 값으로 **교체**하는
시정이다 — 둘은 독립이고 90초 보류가 0 으로 롤백돼도 이 시정은 그대로 유효하다.

- **좁은 목** = `on_open_price_confirmed(ticker, open_price, board="main", *, source="ws")`. `source` 기본값이 불신 `"ws"` 라 WS 호출부(스케줄러 1차 폴링·전략 인라인 확정)는 **한 글자도 안 바뀌고** 거부된다 — `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` byte 동일.
- **REST 확보** = leaf `src/engine/open_price_rest.py`. 09:00:35 R1 부터 30초 간격 **19라운드**(마지막 09:09:35 — 첫 slow 라운드 전까지 30초 격자를 연속 커버한다) → 이후 5분 간격 15:20 까지. 프린트 안 된 종목은 그 시점 **매수 불가**다(틀린 목표선으로 들어간 포지션은 손절선까지 틀리지만, 안 들어간 종목은 기회비용만 남는다). 09:05:00 이후는 스케줄러의 2차 REST 폴백이 백스톱이다.
- **킬스위치** `open_price_scope_mode` — **각 전략의** `DEFAULT_PARAMS`(상호 import 금지) 키. 기본 **`"enforce"`**(= REST 단일 출처). `"off"` 만 롤백값(대소문자·공백 무시 정확 일치)으로 WS 캐시·인라인 확정을 다시 허용한다. 그 외 모든 값·부재·예외는 **enforce**(D1 "체크할 필요가 없이" 의 직역). `pre_nxt`/`post_nxt` 보드는 게이트 스코프 밖 — LTV 08:00~09:00 프리장 매수·야간 매수는 전면 무접촉이다.
- **`PARAM_RANGES`/`INT_PARAMS` 편입 금지** — 진입 정체성 상수(AST G-272-28a/b).
- **롤백** = `PUT /api/strategies/{id}/params {"open_price_scope_mode":"off"}` — **즉시** 반영(그날 이미 REST 로 확정된 목표가는 되돌아오지 않는다 — 전진 방향으로만 듣는다). `strategy_config` SQL UPDATE 는 **다음 재시작에서만**(cycle232 D6).
- 상세 = `src/engine/strategies/CLAUDE.md` · 자문 = `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`.

---

### VB·LTV AI 매수평가 `llm_gate_*` — **shadow, 매매 행위 변경 0**

매수 주문이 나간 **직후** 그 주문을 1~100점으로 평가해 기록만 한다. `enforce` 는 미구현이며
어떤 값이든 `off` 로 낙하한다 — 점수는 매수를 막지 않는다.

- **`DEFAULT_PARAMS` 4키(VB·LTV 각각, `PARAM_RANGES`/`INT_PARAMS` 편입 금지)**: `llm_gate_mode="shadow"` · `llm_gate_min_score=70` · `llm_gate_daily_call_cap=20` · `llm_gate_timeout_secs=20`
- **키 부재** = `mode` off · `daily_call_cap` 0(호출 안 함) · `min_score` 70 · `timeout` 20 — 돈을 쓰는 기능이라 "설정 없으면 안 한다"(`open_price_scope_mode` 부재=enforce 와 반대 방향).
- **자리** = **전략 파일에는 훅이 없다.** `order_engine.execute_buy` 가 매수 `place_order` 에 성공한 **직후**(매핑 등록 블록 끝 · PENDING INSERT 앞) 두 경로(주 경로 · 시장가 거부 지정가 5호가 폴백) 각각에서 `llm_buy_gate.observe_order(...)` 를 부른다. 신호 시점이 아니라 주문 시점인 이유는 ① 신호의 절반만 주문이 되어 점수가 실현손익에 붙지 않았고 ② PK 의 `order_no` 는 `place_order` 응답 뒤에야 확정되기 때문이다. **매도·취소 `place_order` 는 훅 금지.** 훅 자체는 전략 무관이고 평가 여부는 `strategy.config.params["llm_gate_mode"]` 가 정한다 → 4키가 없는 전략은 `mode=off` 낙하(평가 0·비용 0, `[llm_gate_config]` 카나리아만 1행).
- **평가 1회/주문** — 래치 키가 **주문번호**다(같은 종목을 하루 두 번 사면 두 번 평가한다). 일일 cap 은 전략별이고 cap 초과 주문은 `[llm_eval_persist] reason=cap_exceeded` 1행으로 남는다(DB 행 0).
- **기록** = `llm_buy_evaluations`(migration 043, PK `(trade_date, account_no, ticker, order_no)`, 53열). **성공·실패 모두 1행** — 실패도 `reason` 과 **입력 payload** 를 담고 `score=NULL` 이다(침묵하면 "평가 안 함" 과 "평가 실패" 가 구별되지 않는다). 계좌는 저장은 원문, **API 응답은 마스킹**(앞 4자리 + `****`).
- **회고분석 규약** = `prompt_version`/`feature_version` 이 다른 행을 **섞어서 회귀하지 않는다** · 주문 시점 제약 3열(`budget_total_won`/`budget_remaining_after_won`/`open_positions_n`)로 차단의 반사실을 판단한다(예산·`max_positions` 가 묶여 있으면 차단은 다른 종목 매수로 **대체**된다) · `input_payload` 는 요약·절단 없이 저장해 훗날 다른 모델로 **오프라인 재채점**한다 · 조인은 `order_no`→`trade_history`(3축), `buy_order_nos`→`get_trade_pairs` 실현손익이고 **체결/부분체결/미체결/취소 4분류를 반드시 분리**한다(미체결을 손익 0 으로 섞으면 오염된다) · 페어 손익을 주문 단위로 배분할 때는 **매수 금액(수량×매수가) 가중**으로 나눈다.
- **UI** = 거래기록 두 그리드(체결 = BUY 행 `order_no`, 손익 = `buy_order_nos`) 각 행에 "AI 자문" 버튼, 기록이 없으면 비활성(회색)·툴팁 "평가 기록 없음". 팝업 = 점수/임계/차단여부·사유·핵심 위험·무효화 조건·지표 요약·주문 스냅샷·모델/토큰/비용/지연·원문 payload(접기).
- **비용·지연** = 주문 시점 트리거라 호출 수가 신호 시점보다 적다. 타임아웃 20초(같은 모델 실측 6.1~11.3초). pre-warm(목표가 확정 시 전량 선평가)은 호출 17배·표본 불변이라 하지 않는다 — `post_order_drift_bp` 실측이 필요 여부를 답한다.
- **롤백** = `PUT /api/strategies/{id}/params {"llm_gate_mode":"off"}` 즉시. `.env` `OPENAI_API_KEY` 제거는 재시작 후(`no_key`).
- **D+1 서명** = `[llm_gate_config]` 전략당 1행 · `[llm_buy_score]` **매수 주문당 1행**(score 1~100, `order_no=` 포함) · `[llm_eval_persist] result=ok` 가 같은 수 · `_failed` <10% · `[llm_gate_daily_cap]` 0행 · 매수 건수·시각·수량 패턴 불변 · DB 행 수 = 그날 매수 주문 수.
- ⚠️ **표류 필드 `post_order_drift_bp` 는 구 `slip_bp` 와 부호 의미가 반대다**(+ 는 주문 뒤 상승 = 이득) — 두 마커의 로그를 합산하지 않는다.

## 6. 전략 D: 20일 신고가 스윙 (donchian_swing) 상세

### 개념
멀티데이 추세추종(터틀 스타일). 한 번 추세 잡힌 종목은 끝까지 따라간다는 클래식 추세 전략.

### 종목군
- **코스피200 + 코스닥150 유니버스** — `stock_master.list_by_filter(is_kospi200=True, is_kosdaq150=True, …)` DB 필터로 산출(사이클 119/153, 하드코딩 리스트 미사용). 거래량순위 API 미사용(추세추종 부적합)
- 시가총액 컷 `min_market_cap` 기본 **500억**(Q2=D 임시 완화, 원본 3,000억), 스캔 상한 `max_scan_stocks=400`
- 스캔 단계 거래대금 컷 `min_trade_amount` 기본 **10억**(원본 50억)이 별도로 적용되며, prepare() 의 `volume_multiplier`(기본 1.5×)는 그와 별개의 20일 평균 대비 조건

### 진입 조건 (`_boot()` prepare)
1. 어제 종가가 최근 20일 신고가 돌파 (`donchian_period`)
2. 어제 종가가 60일 EMA 위 + EMA 우상향 (`long_ma_period`)
3. 어제 거래대금 ≥ 20일 평균 × `volume_multiplier`(1.5)
4. ATR(14) 산출

### 매수 규칙
- **시점**: 다음 영업일 09:05 ~ 09:30 사이 시장가 (1종목당 1회만)
- **갭 스킵**: 시가 갭상승 +3% 이상이면 진입 스킵 (`gap_skip_threshold`, 추격 매수 회피)
- **투자 비중**: 할당 자금의 20% (1종목당)
- **동시 보유**: 최대 5종목
- **매매 보드**: MAIN만 (KRX 메인 한정)
- **거래소 라우팅**: 기본 KRX
- **매수 평가 채널 (G안)**: `scheduler._swing_buy_poll_loop()` 가 09:05~09:30 KST **1분 주기**로 `fetch_stock_detail`(KIS REST) 폴링하여 매수 평가한다. WebSocket on_tick 에서는 매수 평가하지 않는다 — 일봉 전략이라 tick 평가는 낭비이고, 후보 50~150개의 WebSocket 슬롯을 변동성 돌파(VB/LTV) 후보에 양보한다.
  - **보유 종목은 그대로 WebSocket(positions HIGH 그룹) 구독** → 청산(ATR 트레일링/-7% 하드)은 `risk.on_tick` 의 `check_exit_signal` 그대로 평가
  - `risk.on_tick` 매수 평가 직전에 `if strategy_id == "donchian_swing": continue` 가드 (이중 안전망)
  - `donchian_swing.check_buy_signal` 의 09:05~09:30 시간 가드 + `_bought_today` set 그대로 유지 (Pull 폴링도 중복 진입 방지)
  - `[swing_poll] candidates=N filtered=M bought=K elapsed=T.Ts` INFO 로그 1행 / 사이클

### 청산
- **하드 손절**: 매수가 대비 **-6%** (운영 DB, 사이클 210 복원). 코드 DEFAULT -7. **⚠️ 사이클 210 (2026-07-14)**: AI 자문 수동 apply 누적으로 `stop_loss_rate -3.2` / `daily_loss_limit -0.8`(배정자금 -0.8% 손실=당일 매수 중단)까지 과조임 방치돼 208/209로 신호가 나와도 진입 직후 죽던 상태 → **stop -6.0 / daily_loss -6.0 복원**. 재조임 방지 = auto_apply `_CONSERVATIVE_KEYS` 제거(engine/CLAUDE.md 참조).
- **일일 손실 한도** (`daily_loss_limit`): 배정자금 대비 **-6%** (사이클 210 복원, 코드 DEFAULT -8). 초과 시 당일 매수 중단.
- **브레이크이븐 승격** (`breakeven_promote_atr`=1.5, **기본 활성**): 고점이 매수가 + 1.5 × `_entry_atr` 도달 이력이 있으면 2ATR 하드손절선을 매수가로 승격(tighten-only, P1-A 2026-07-29)
- **10일 채널 이탈 청산** (`channel_exit_period`=10, **기본 활성**): 현재가 < 최근 10영업일 저가 채널이면 TRAILING_STOP. ATR 트레일링 **앞**에서 평가 (P1-A 2026-07-29)
- **ATR×2 Chandelier 트레일링**: `high_since_buy − ATR(14) × 2` 이하로 떨어지면 매도
- **15:20 강제 청산 없음** (`check_force_clear()` 빈 리스트). 단 **시간 기반 청산은 있다** — `breakout_fail_n_days`(기본 5): 보유 5영업일 경과 + 현재가 < 돌파선이면 STOP_LOSS (사이클 23 P2-2)
- 평균 5~15 영업일 보유 → DB `positions` 영속화로 일자 넘어 유지

#### high_since_buy 일봉 폴백
- **`recompute_held_atr()` 직후 또는 함께 `high_since_buy` 일봉 보정** — 매수일 다음 영업일~전영업일까지의 KIS 일봉 high max로 복구. 시세 미수신 누적으로 chandelier 트레일링 손절선이 매수가 부근에 동결되는 결함 차단 (2026-05-12 이마트 사례)
- 대상: **donchian_swing · vcp_breakout · kojiro**. 헬퍼 `_apply_high_since_buy_from_candles` 는 `StrategyBase` **단일 진실원**(전략별 복사본 금지 — AST 재발 가드). kojiro 는 `recompute_held_atr` 이 **이미 fetch 한 일봉 응답을 재사용**해 호출하므로 KIS 추가 호출이 0이다
- ⚠️ **영속이 없으면 트레일링은 매일 아침 죽는다** — `risk.on_tick` 은 메모리만 올리고 `_boot()`(매 영업일 기동 직후)은 DB row 로 Position 을 재생성한다. 복구가 없으면 보유 종목의 DB `high_since_buy` 가 `buy_price` 에 머물러 2.5ATR 샹들리에가 `buy − 2.5×ATR` 로 주저앉고 하드손절과 구분되지 않는다(2026-08-06 보유 7종목 전부 실측). **신규 보유형 전략은 이 복구를 반드시 배선한다.**
- 보정 조건: `pos.buy_date < today_kst` 인 보유 포지션만. 매수일 당일/미래일은 skip (당일은 `buy_price`가 진실, 미래일은 비정상 → WARNING)
- 보정값: `max(pos.high_since_buy, max(eligible_daily_highs))` — 일봉 응답 후 매수일 < bsop_date < today 범위 필터 → 일별 `stck_hgpr` max
- DB 영속화: 보정값이 기존 high_since_buy 초과 시 `update_high(ticker, new_high)` (또는 `save_position`)로 UPDATE + `system_logs` `[high_since_buy_recover]` prefix 1행
- 안전 가드: 종목별 sequential await (Rate Limit), 일봉 fetch 예외/빈 응답 → 해당 종목 skip + 다른 종목 영향 없음
- `risk.py:72` 실시간 시세 기반 `high_since_buy` 갱신은 그대로 유지 — 이건 boot 시점 1회 복구만

#### 일중 시세 REST 폴링 보강 `_swing_rest_poll_loop`
donchian_swing 은 멀티데이 보유 + ATR×2 Chandelier + 하드 손절 전략이라 일중 시세에 100% 의존한다. WebSocket 이 stale 이면 손절 평가 자체가 멈추므로 REST 폴링 레이어가 그 구멍을 메운다(WS 가 정상이면 무해한 멱등 중복이다).

- **위치** `src/engine/scheduler.py::_swing_rest_poll_loop()` — 매수 평가 전용인 `_swing_buy_poll_loop`(09:05~09:30)와 **별개**다.
- **운영 시간** 09:30 ~ 15:20 (매수 진입 종료 후에도 보유 평가는 계속). **주기 60초.**
- **대상 = `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")` 합집합** — 각 전략의 `_scanned_tickers`(최종 후보) + `state.positions`(보유) + `state.pending_buys`(주문 진행 중)를 6자리 영숫자 필터 + dedupe 로 합친다.
- **동작(종목별 sequential await)**: KIS 단건 시세 호출 → 종목 사이 `await asyncio.sleep(0.05)` → `scanner.ticker_prices[ticker]` 갱신(`current_price`/`open_price`/`change_rate`/`prdy_ctrt`) → `scanner.ticker_last_tick[ticker]` touch(stale watcher 가 fresh 로 인식) → `ticker_names` 보강 → **보유 종목 한정** `RiskManager.on_tick(ticker, price)` 직접 호출.
- **별도 청산 경로를 신설하지 않는다** — 기존 트레일링/하드 손절 코드를 그대로 재사용한다.
- **예외 격리**: KIS 5xx/timeout/`KisApiError` 는 종목 단위 try/except 로 흡수하고 다음 종목으로 간다. loop 본체 예외는 ERROR 로그 + 다음 사이클 자연 회복.
- **구조화 로그**: 사이클당 1행이 아니라 **5분 윈도우 집계 1행**이다 — `[swing_rest_poll_summary] polls=N candidates_avg=X max=Y total_held=Z elapsed_ms_avg=W`(`record_swing_rest_poll(stats)` 위임, 개별 사이클 행은 fetch 실패 시 DEBUG 뿐). 수집 필드 = `candidates`/`held`/`pending`/`updated`/`failed`/`elapsed_ms`, 전부 두 전략 합산치.
- **불변식**:
  - 매수 평가는 이 폴링이 **트리거하지 않는다** — donchian 매수는 `_swing_buy_poll_loop`(09:05~09:30 1분 주기) 전용이고, 이 loop 는 **시세 갱신 + 보유 평가만** 책임진다.
  - `risk.py` 의 donchian_swing 매수 스킵 가드(`if strategy_id == "donchian_swing": continue`)를 보존한다.
  - WS 우선순위 큐와 무관 — 이 폴링은 WS 슬롯을 쓰지 않는다.

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 20%
- 일일 최대 손실 한도: 할당 자금의 8%

---

## 6-E. 전략 E: 눌림목 돌파 (bull_flag_breakout) 상세

### 개념
강한 상승(폴, flag pole) 직후 짧은 횡보·완만한 조정(플래그) 후 플래그 상단을 재돌파하는 클래식 셋업.
모멘텀 전략이 +29% 폭발 순간을 잡는다면, 본 전략은 그 후속 정리(소형 조정) 후 2차 상승 진입로를 담당한다.

### 종목군
- KOSPI + KOSDAQ 전체에서 사후 필터.
- **유니버스 소스 = `stock_master.list_by_filter`(사전 적재 DB)** — 스캔 시점에 KIS 를 직접 호출하지 않는다. 거래대금 컷은 **전일 확정치**여야 한다(당일 누적 거래량으로 재면 `_boot()` prepare 에서 항상 0이 되어 유니버스가 매일 0종목이 된다).
- **시가총액 ≥ 100억** (`min_market_cap`, 기본 10_000_000_000 — 사용자 결정: kojiro 500억보다 낮게 유지해 소형주 포함, 라이브 DB 값 정합)
- **거래대금 ≥ 15억** (`min_trade_amount`, 기본 1_500_000_000 — 2026-08-08 확대 20억→15억. 도메인 B2: BFB 는 장중 돌파 추격이라 전 전략 중 슬리피지 최대 노출 → kojiro 10억까지 내리지 않고 완만한 15억으로 유동성 바닥 보존. 추격도 BFB>VCP>kojiro 에 비례한 차등)
- ETF/ETN 제외 (기존 키워드 컨벤션 재사용 — KODEX/TIGER/RISE/KoAct/PLUS/TIMEFOLIO/WOORI/FOCUS/인버스/레버리지)
- 최대 4000종목 (`max_scan_stocks`, 100→확대 — 전체 filtered 커버, `refreshed_at DESC` 임의 절단 소멸. BFB 는 이미 지수 무제약이라 실질 확대의 핵심 레버)

### 데이터 준비 (`_boot()` prepare)
- 종목별 일봉 **44일치**(폴 10 + 플래그 10 + ATR 14 + 여유 10) — `get_recent_daily_normalized(ticker, days=44, min_required=35)` (DB 우선 어댑터, 사이클 173). `fetch_daily_candles` 는 재시작 복구 경로 전용
- `candles[0]==오늘`이면 `candles[1]`을 전일로 사용 (부분봉 가드, VB/LTV/donchian 컨벤션 재사용)

### 셋업 검증 (단계별 필터, prepare 시 통과 종목만 `_candidates`에 등록)
**폴(Pole) 조건 — `pole_lookback_days=3~10`**:
1. 직전 N영업일(3~10) 사이에 **누적 상승률 ≥ +15%** (`pole_min_return`, 기본 **15.0** — 사이클 48 완화, 기존 20.0 은 음봉 30% 와 교집합이 0 을 만듦. 한국 일일 ±30% 환경에서 3~10일 +15% 도 충분히 강한 깃대 모멘텀)
2. 같은 구간 **음봉 비율 ≤ 45%** (`pole_max_red_ratio`, 기본 **0.45**(cycle48) — 강한 폴 구간도 1~2일 쉬어가는 음봉이 정상이라 30% 면 5일 중 음봉 2개(40%)에 현실 깃대상승이 다수 탈락한다. 가짜 돌파는 돌파 순간 + 거래량 2배 컷이 거른다) — `close < open`인 일수 / 구간 길이
3. 폴 구간 내 최고가 = `pole_high`, 폴 시작가 = `pole_start`, **폴 폭 = `pole_high - pole_start`**

**플래그(Flag) 조건 — `flag_lookback_days=2~10`** (폴 종료 직후 N영업일. **사이클 198 (2026-07-09) — 3→2 완화**: domain-expert 자문 + 298종목×4일 DB 실측(`_workspace/domain_consult/cycle198_pattern_strictness_korea.md`) — 한국 급등주는 눌림(플래그)이 얕고 빠르다(상한가 익일 눌림 → 3일차 재돌파 리듬), `flag_lookback_min=3`이면 2일 눌림을 플래그로 검출 못해 후보 소실. `flag_volume_ratio`(거래량 수축 60%) 안전장치가 저품질(급락 되돌림) 후보를 여전히 전량 흡수 실증 — 완화해도 오탐 0):
1. 플래그 구간 최고가 = `flag_high`, 최저가 = `flag_low`
2. **조정 폭 ≤ 폴 폭의 50%** (`flag_retracement_max=0.5`, 사이클 211 — 0.382→0.5 완화, funnel 폴/플래그 병목 실측 3.3배) — `(pole_high - flag_low) <= (pole_high - pole_start) × 0.5`. 거래량 수축(`flag_volume_ratio 0.6`)이 급락 되돌림 오판 봉쇄(안전장치 불변)
3. **플래그 평균 거래량 < 폴 평균 거래량 × 60%** (`flag_volume_ratio=0.60`) — 거래량 수축 확인
4. 플래그 종가 추세는 강한 우하향이 아니어야 함 (마지막 종가가 flag_low 보다 0.5×ATR 이상 멀지 않을 것 — 일종의 sanity check, 정밀한 회귀선 검사는 1차에서 생략)

검증 통과 시 `_candidates[ticker] = {pole_start, pole_high, flag_high, flag_low, flag_avg_volume, pole_len, flag_len, atr14, prev_close}` 등록 (`pole_low` 키는 존재하지 않는다). 이 중 구조 레벨 4키 `_SETUP_LEVEL_KEYS = (flag_low, flag_high, pole_high, pole_start)` 는 `_position_setup` 에 영속된다.

### funnel 단계별 탈락 사유
`_detect_pole_and_flag_detailed(candles) -> (result, fail_stage, detail)` 이 실패 시 "가장 멀리 도달한 sub-condition"(`pole_return`/`pole_red_ratio`/`flag_retracement`/`volume_contraction`)과 측정 수치(`best_return`/`red_ratio`/`retracement`/`vol_ratio`)를 보고한다. `_detect_pole_and_flag(candles) -> dict | None` 은 그 result 만 돌려주는 thin wrapper 라 검출 결과는 불변이다. `prepare()` 의 funnel hook 이 `fail_stage` 에 따라 step 4(폴 상승률+음봉) / step 5(플래그 조정폭) / step 6(거래량 수축)에 탈락 종목을 수치 사유로 분배한다 — 한 줄로 뭉뚱그리면 어느 조건이 바인딩인지 운영자가 알 수 없다.

### 매수 규칙
- **진입 조건**: 현재가가 `flag_high`(플래그 상단) 돌파 순간 + **실측 거래량 게이트 통과**
  - 돌파 순간: `이전 틱 < flag_high AND 현재 틱 ≥ flag_high` (VB 컨벤션 — `_prev_price[ticker]` 추적)
  - **거래량 컷**: `tick_volume.get_observed_acml_vol(ticker)` 실측 누적거래량 ≥ `flag_avg_volume × breakout_volume_mult`. **소스는 `tick_volume` 뿐이고 미관측(`None`)은 fail-closed** 다 — `0` sentinel 금지 계약은 `tick_volume` 자체가 보장한다. 읽기 실패도 미관측과 같이 다뤄 예외가 `check_buy_signal` 밖으로 새지 않게 한다(on_tick 이 죽으면 그 종목의 청산 평가까지 멈춘다).
  - **충족 래치**: 돌파 후 거래량이 아직 모자라면 `_vol_latch` 에 무장해 두고 같은 날 재평가한다(entry 별 `armed_date` 로 자기 무효화).
  - **추격 상한**: 거래량을 채워도 `(현재가 − flag_high) / flag_high × 100 > max_breakout_extension_pct`(기본 **5.0**)면 진입하지 않는다. 판정은 `current_price` 단독이다 — `daily_high`/`ticker_prices` 를 쓰지 않는다(donchian 이식 시 그 커플링이 딸려온다).
  - 마커 = `[bfb_vol_gate_pass]`(INFO) · `[bfb_vol_gate_no_data]`(WARNING) · `[bfb_vol_gate_reject] reason=extension`(INFO), 카운터 = `vol_gate_pass` / `vol_gate_reject_ext` / `vol_gate_no_data`.
  - ⚠️ **구 관측 마커 `[bfb_vol_gate_observe]` 는 은퇴했고 `would_pass` 의 의미가 반대라 그 시절 로그와 합산하지 않는다.**
- **진입 시간대**: **09:05 ~ 13:00 KRX 메인** (`entry_start=09:05` / `entry_end=13:00`, 시간 가드)
  - `tradable_boards=("main",)` — KRX 메인만, NXT 비활성(눌림목 패턴이 NXT 거래대금 부족으로 신뢰성 낮음)
- **거래소 라우팅**: 기본 `KRX` (모의 호환)
- **주문 방식**: 시장가
- **투자 비중**: 할당 자금의 25% (`position_ratio=0.25`) — 1주 폴백 `_fallback_one_share()` 호출
- **동시 보유**: 최대 4종목 (`max_positions=4`)
- **종목당 1회만**: `_bought_today` set (donchian 컨벤션 재사용) — 진입 시도 즉시 add (체결 여부 무관)
- **쿨다운**: 청산 후 **3영업일** (`reentry_cooldown_days=3`). DB `positions` 또는 `trade_history` 마지막 매도일 + 3 < today 면 재진입 허용

### 청산 (3단계 — `check_exit_signal`)
1. **하드 손절**: 매수가 -5% (`stop_loss_rate=-5.0`) → 즉시 시장가 매도 (Signal.STOP_LOSS)
2. **플래그 하단 이탈 손절**: `current_price < flag_low` → Signal.STOP_LOSS
3. **측정된 이동(measured move) — 절반 익절**:
   - **타겟가** = `flag_high + (pole_high - pole_start)` (플래그 상단에서 폴 폭만큼 상승)
   - 현재가 ≥ 타겟가 도달 순간 → **보유 수량의 50% 시장가 매도** (Signal.TRAILING_STOP 으로 보고 + 별도 부분 매도 라우팅)
   - 절반 익절 처리 시 `_partial_exit[ticker]=True` 로 마킹 → 잔여 ATR 트레일링
4. **잔여 ATR×2 트레일링**: `_partial_exit[ticker]==True` 분기에서 `current_price <= high_since_buy - ATR×2` → Signal.TRAILING_STOP (donchian 컨벤션 재사용)
5. **시간 청산**: 진입 후 **5영업일 경과** 시 잔량 시장가 (`max_hold_days=5`) — `pos.buy_date + 5영업일 ≤ today` 판정

> ⚠️ **BFB 는 익일 청산 전략이 아니다.** `_execute_next_day_clear`·`_force_clear_main_only` 어느 목록에도 없고 `check_force_clear()==[]` 이라 위 5번까지 **실질 멀티데이 보유**다(`_MULTIDAY_STRATEGIES` 비멤버라는 사실은 `is_next_day` 배지 표시에만 영향한다). 그래서 재시작 복구가 필요하다 — `_rederive_entry_atr`(**`sizing_mode="turtle"` 일 때만** — position_ratio 랏은 −5% 고정 손절 유지, cycle355) + `recompute_high_since_buy` 를 `boot_manager` 에 배선한다(`scheduler.py` 는 8영역이라 무접촉, `_SWING_POLL_STRATEGIES` 편입은 매수 폴루프·구독까지 바꾸므로 금지).
>
> ⚠️ **청산 2~4번은 `_candidates` 단독 의존 금지** (P1, 2026-08-06 · VCP 와 동일 규약). 특히 3번 measured-move 는 BFB 의 **유일한 익절 경로**인데 `info["pole_high"]` 직접 인덱싱이라 부분 재채움 시 `KeyError` 로 `check_exit_signal` 전체가 죽었다 → `.get()` 방어 + **키 결손 시 미발화**(임의 기본값으로 익절을 쏘면 과잉 청산)가 계약.

### 매수 회전
- 종목당 진입 1회 (`_bought_today` set)
- 청산 후 **3영업일 쿨다운**
- 신규 매수 차단 조건: `is_max_positions()` / `is_daily_loss_exceeded()` / `state.buy_disabled` / `registry.is_ticker_blocked_for_buy()`

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 25%
- 일일 최대 손실 한도: 할당 자금의 6% (`daily_loss_limit=-6.0`)
- 동시 보유 종목 수: 최대 4종목

### 기본 파라미터 (`DEFAULT_PARAMS`)
```python
DEFAULT_PARAMS = {
    "tradable_boards": ["main"],
    "exchange": "KRX",
    # 폴
    "pole_lookback_min": 3,
    "pole_lookback_max": 10,
    "pole_min_return": 15.0,
    "pole_max_red_ratio": 0.45,
    # 플래그
    "flag_lookback_min": 2,
    "flag_lookback_max": 10,
    "flag_retracement_max": 0.5,
    "flag_volume_ratio": 0.60,
    # 매수
    "breakout_volume_mult": 2.0,
    "entry_start": "09:05",
    "entry_end": "13:00",
    "breakout_retention_minutes": 3,   # 첫 돌파 감지 후 N분 유지해야 발사 (가짜 돌파 차단)
    "max_breakout_extension_pct": 5.0, # 추격 상한 — 정체성 상수, PARAM_RANGES 미편입
    "position_ratio": 0.25,
    "max_positions": 4,
    # 청산
    "stop_loss_rate": -5.0,
    "atr_period": 14,
    "atr_trail_mult": 2.0,
    "breakeven_promote_atr": 0.0,  # 브레이크이븐 승격, 0=비활성(다크런치). PARAM_RANGES/INT_PARAMS 미편입
    "max_hold_days": 5,
    "reentry_cooldown_days": 3,
    # ── 터틀 유닛 sizing + 하드손절 ATR화 (다크런치) ──
    # 게이트는 sizing_mode 가 아니라 `_entry_atr` 스탬프 존재. 전 키 PARAM_RANGES/INT_PARAMS 미편입
    "sizing_mode": "position_ratio",
    "risk_pct": 0.005,
    "stop_atr": 2.0,
    "turtle_backstop_pct": -7.0,
    "min_vol_floor_pct": 1.0,
    "max_lot_units": 2.0,      # cycle242 — 랏당 최대 유닛(K). PARAM_RANGES/INT_PARAMS 미편입
    "max_lot_ratio_mult": 2.5, # cycle245 — 랏 명목 ρ축 상한(K_ρ). 명목 ≤ K_ρ×position_ratio×예산, 1주도 못 사면 미매수.
                               # K축과 `min` 합성(cycle254). PARAM_RANGES 미편입. 롤백 = 20.0
    "turtle_min_stop_pct": -4.0,
    # 유니버스 — 전체 상장 ∩ 시총≥100억 ∩ 거래대금≥15억
    "min_market_cap": 10_000_000_000,
    "min_trade_amount": 1_500_000_000,
    "max_scan_stocks": 4000,
    # 일반
    "daily_loss_limit": -6.0,
    # 장중 킬스위치 — 값은 order_engine 코드 상수와 동일(행위 변경 0).
    "order_exchange_clock_mode": "enforce",
    "after_market_exit_division": "44",
}
```

### 운영 노트
- VTS(모의) 검증 가능 — KRX 메인 한정이므로 SOR/NXT 의존성 없음
- 셋업이 빈번하지 않은 패턴 — prepare 결과 0종목이 정상일 수도 있음. 0종목 ERROR 로그는 조건 완화 검토 신호로 사용
- `_workspace/00_leader_trading_rules.md` 변경 시 `src/engine/CLAUDE.md`·`CLAUDE.md` 다중 전략 표 동기화

---

## 6-F. 전략 F: 변동성 수축 돌파 (vcp_breakout) 상세

### 개념
미네르비니식 VCP(Volatility Contraction Pattern). 상승 후 변동성이 단계적으로 축소되는 베이스(2~4회 pullback, 점진 수축) → 거래량 폭증 베이스 상단 돌파 시 매수.
donchian_swing 의 정공법(신고가 직진 추격)을 보강하는 추세추종 보조 전략. VCP 는 베이스 + 변동성 수축 확인으로 후핵폐기를 줄인다.

### 종목군
- **전체 상장 확대 유니버스** (2026-08-08 — kojiro 동일 필터. 지수 KOSPI200∪KOSDAQ150 제약 제거 → `list_by_filter(is_kospi200=None, is_kosdaq150=None)`. 미네르비니 VCP 셋업은 대형 지수주가 아니라 중소형 성장주에서 나오므로 지수 제약이 서식지를 배제해 왔음. 일봉 데이터는 이미 존재 — daily-load 유니버스 = 지수∪500억/10억 = 확대 상위집합, 비지수 자격 641종목 중 95.8%가 ≥100일 적재 실측)
- **시가총액 ≥ 100억** (`min_market_cap`, 기본 10_000_000_000 — 사용자 결정: kojiro 500억보다 낮게 유지해 미네르비니 중소형 성장주 더 넓게 포착, 라이브 DB 값 정합)
- **거래대금 ≥ 10억** (`min_trade_amount`, 기본 1_000_000_000 — 이전 `_scan_universe` 하드코딩 0(미사용)을 실사용으로 전환, 소형주 유동성 바닥 방어)
- ETF/ETN 제외
- 최대 4000종목 (`max_scan_stocks`, 200→확대 — 전체 filtered 커버, `refreshed_at DESC` 임의 절단 소멸)

### 데이터 준비 (`_boot()` prepare)
- 종목별 일봉 — `get_recent_daily_normalized(ticker, days=fetch_days, min_required=100)` (DB 우선 어댑터, 사이클 173). **읽기 깊이는 전략 파라미터 `daily_fetch_depth_mode` 가 정한다**(cycle300):
  - `"cap100"`(기본) → `fetch_days = min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX=100)` = **100봉**. 배포 시점 행위는 이 값에서 byte 동일하다.
  - `"full"` → `fetch_days = ema_long + base_max + 10`(기본값이면 200+75+10 = 285). DB 에 있는 만큼만 오므로 얕은 종목은 자동으로 줄어들고 `effective_ema_long` 가드가 그대로 받아 낸다.
  - 켜고 끄는 수단 = `PUT /api/strategies/vcp_breakout/params {"daily_fetch_depth_mode":"full"}` — **즉시 반영 + 영속**. 롤백은 같은 PUT 에 `"cap100"`. `strategy_config` SQL UPDATE 는 다음 백엔드 재시작에서만 반영되므로 장중 실효 수단은 PUT 뿐이다(cycle232 D6).
  - `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(진입 정체성 축). 미지 값·결측·비문자열은 전부 `"cap100"` 으로 낙하한다.
  - `min_required` 는 두 모드 다 **100** 이다 — KIS 폴백은 한 호출 100봉이 상한이라 문턱을 올리면 DB 가 100~224봉인 구간에서 더 얕은 KIS 응답으로 바뀐다.
  - 읽기 관문 `db/stock_master_daily.get_recent_daily` 의 상한은 `_MAX_DAILY_ROWS = 400` 이다(cycle300 이 100 에서 올렸다). 100 은 애초에 KIS 한도가 아니었다 — KIS 의 100일은 **호출당** 한도다. 적재 깊이 target 은 225영업일이고, **그 깊이를 받는 대상은 일봉 적재 대상 전부**다(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호 — cycle302 가 지수 전용에서 넓혔다). 즉 `"full"` 을 켠 전략이 얕은 봉을 만나는 구간은 상장 이력 자체가 짧은 종목뿐이다.
  - `fetch_daily_candles` 는 재시작 복구 경로 전용
- `candles[0]==오늘`이면 `candles[1]`을 전일로 사용 (부분봉 가드)

### 추세 필터 (Stage 2 confirmation, prepare 시 단계별 검사)
1. **종가 > 단기 EMA > 중기 EMA > 장기 EMA** (`ema_short=50`, `ema_mid=150`, `ema_long=200` — 미너비니 Trend Template 원설계)
2. **장기 EMA 우상향 1개월 이상** — 현재 장기 EMA > 1개월 전(20영업일 전) 장기 EMA (`long_ema_uptrend_days=20`)
3. 통과 종목만 다음 단계 검사
4. **EMA 값과 읽기 깊이는 짝이다.** `effective_ema_long = min(ema_long, available_len - long_ema_uptrend_days - 5)` 이고, 그 뒤 `ema_mid >= ema_long` 이면 `ema_mid = max(ema_short+1, ema_long-10)` 로 중기선이 한 번 더 줄어든다. 설정 50/150/200 의 실효 정렬은 이렇게 갈린다 — **보유 100봉 → 50/65/75**(중기↔장기 간격 10 = 정배열이 동전던지기) · **보유 225봉 → 50/150/200**(간격 50). 즉 기본 모드 `"cap100"` 에서는 설정이 50/150/200 이어도 실제로 계산되는 정렬은 50/65/75 다. 원설계 정렬을 실제로 쓰려면 위 `daily_fetch_depth_mode="full"` 을 켠다. 자동 축소 가드는 fetch 부족 시 안전망으로 유지한다.

### 베이스 정의 (`base_lookback_weeks=5~15` → 일봉 25~75영업일)
1. 베이스 시작·종료 자동 검출: `base_max_days`(75)부터 `base_min_days`(25)까지 길이를 줄여 가며 첫 매칭(=가장 긴) 구간을 베이스로 인식. 판정식은 2번과 동일한 **고가/저가 기준** `(max(high) - min(low)) / max(high) ≤ base_depth_pct(0.30)` 하나뿐이다 — `base_depth_max=0.25` 같은 별도 상수·종가 기준 산식은 존재하지 않는다
2. **베이스 깊이** = `(base_high - base_low) / base_high ≤ 30%` (`base_depth_pct=0.30`)
3. 베이스 길이 = 25~75영업일 (`base_min_days=25`, `base_max_days=75`)

### 조정 시퀀스 (Pullback Sequence, 점진 수축)
1. 베이스 구간 내 pullback 자동 검출: 직전 swing high → swing low 까지의 하락 폭 → 다음 swing high 까지의 상승. `pullback_count_min=2`, `pullback_count_max=4`
2. 각 pullback 폭 = `(swing_high - swing_low) / swing_high` (%)
3. **각 pullback 폭이 직전 pullback 보다 작아야 함** (점진 수축, 변동성 contraction. strict — 동일 폭 거부)
4. **마지막 pullback ≤ 12%** (`last_pullback_max=0.12` — 사이클 48 완화, 기존 0.08. 한국 중소형주 변동성에 8% 는 빡셈. 점진 수축 조건은 유지)
5. **노이즈 swing 필터 `min_swing_atr_mult=1.0`** — 베이스 구간 평균 일중 변동폭(`sum(high-low) / N`, ATR 근사) × 1.0 미만 변동은 swing 으로 인정하지 않는다(ATR 산출 실패 시 종가 평균의 0.3% 폴백). 🔴 **이 임계를 낮추지 않는다** — 낮추면 ZigZag 반전 회수가 2~4배로 불어난다. 그러면 상한 `pullback_count_max=4` 를 넘기고 점진 수축 strict 단조(통과율 1/n!)가 무너져 Pullback 단계가 사실상 막힌다. 등호 포함 swing 검출은 평탄 우량주의 1원 단위 변동까지 swing 으로 세어 회수 2~4회 범위를 상시 위반시킨다. running_max / running_min 추적 + threshold 이상 반전에서만 swing 을 확정한다(ZigZag 표준).
6. **마지막 swing 이 미완성이어도 포함한다** — state machine('undefined'/'up'/'down')으로 끝까지 진행해 `state=='down'` 중 데이터가 끝나면 마지막 pivot_high → running_min 의 진행 중 pullback 을 "마지막 pullback" 으로 센다. 누락하면 `base["last_pullback_pct"]` 가 비어 funnel 이 "마지막 폭 0.0%" 로 오표시된다 — **False 반환 경로에서도 실제 마지막 swing 폭(또는 swing 0개면 명시적 0.0)을 기록한다.**

### 거래량 수축
- 베이스 형성 중 **마지막 5일 평균 거래량 < 베이스 직전 20일 평균 거래량 × 70%** (`volume_contraction_ratio=0.70`)
- 베이스 직전 20일 = 베이스 시작 직전 영업일들

검증 통과 시 `_candidates[ticker] = {base_high, base_low, last_pullback_pct, atr14, ema50, ema150, ema200, prev_close, avg_volume_20}` 등록 (`avg_volume_20` = 매수 거래량 컷 기준선 — 20일 평균 × `breakout_volume_mult`).

### 매수 규칙
- **진입 조건**: 현재가가 `base_high`(베이스 상단, `pivot_high`) 돌파 순간 + **실측 거래량 게이트 통과**
  - **거래량 컷**: `tick_volume.get_observed_acml_vol(ticker)` 실측 누적거래량 ≥ `avg_volume_20 × breakout_volume_mult`. BFB 와 **동형**이다 — 소스는 `tick_volume` 뿐, 미관측은 fail-closed, 충족 래치, 추격 상한(`max_breakout_extension_pct` 기본 **7.5**), 마커 `[vcp_vol_gate_*]`.
  - 돌파 순간: `이전 틱 < base_high AND 현재 틱 ≥ base_high` (VB 컨벤션)
- **진입 시간대**: **09:05 ~ 14:30 KRX 메인** (`entry_start=09:05` / `entry_end=14:30`)
  - `tradable_boards=("main",)`
- **거래소 라우팅**: 기본 `KRX`
- **주문 방식**: 시장가
- **투자 비중**: 할당 자금의 20% (`position_ratio=0.20`) — 1주 폴백 `_fallback_one_share()`
- **동시 보유**: 최대 5종목 (`max_positions=5`) — donchian 과 동일 수준
- **종목당 1회만**: `_bought_today` set
- **쿨다운**: 청산 후 **7영업일** (`reentry_cooldown_days=7`)

### 청산 (멀티데이, 시간 청산 없음)
1. **하드 손절**: 매수가 -7% (`stop_loss_rate=-7.0`) → Signal.STOP_LOSS
2. **베이스 하단 이탈**: `current_price < base_low` → Signal.STOP_LOSS
3. **ATR×2 트레일링 (Chandelier)**: `current_price <= high_since_buy - ATR×2` → Signal.TRAILING_STOP (donchian 컨벤션 재사용 — `_atr()` 헬퍼)
4. **50일 EMA 이탈**: `current_price < ema50` → Signal.TRAILING_STOP. `ema50` 은 **매일 갱신**한다(boot 훅이 이미 fetch 하는 일봉으로 재계산) — 진입 시점 스냅샷을 박제하면 상승 추세에서 `ema50` 이 뒤처져 이탈 청산이 늦어진다.
5. **시간 청산 없음 + 15:20 강제 청산 없음** — `check_force_clear() = []` (donchian 컨벤션, 멀티데이 보유)

> ⚠️ **청산 2~4번은 `_candidates` 단독 의존 금지** (P1, 2026-08-06). `prepare()` 는 매 실행마다 `_candidates` 를 와이프하고 **보유 종목은 돌파 후 셋업이 무너져 후보 자격을 잃는 게 정상**이라, 거기 단독 의존하면 **T+1 아침부터 매일** 2~4번이 통째로 침묵하고 1번 하드손절만 남는다(재시작 사고가 아니다 — 2026-08-04 kojiro 삼영무역과 동일 클래스). 전부 `_effective_setup(ticker)` 리졸버 경유(`_candidates` live → `_position_setup` 영속 폴백). **구조 레벨**(`base_low`)은 BUY 직전 stamp 후 불변이고 재시작 소실 시 매수일 *이전* 봉으로 재검출(실패 시 미복구 = fail-safe), **지표**(`atr14`/`ema50`)는 boot 훅이 매일 갱신. `_reset_daily_state` 에서 clear 금지(AST 봉인).

### 멀티데이 보유 영속화
- `Position._MULTIDAY_STRATEGIES` frozenset 에 `vcp_breakout` 추가 — `is_next_day` 항상 False 반환 (OrderMonitor "청산" 배지 미표시, donchian I2 컨벤션)
- DB `positions` 영속화로 일자 넘어 유지
- `recompute_held_atr()` + `recompute_high_since_buy()` 동등 메커니즘 적용 (boot 시 일봉 fetch 로 ATR 재계산 + high_since_buy 폴백) — backend-dev 가 donchian 헬퍼 재사용 또는 vcp 별도 메서드 판단

### 매수 회전
- 종목당 진입 1회 (`_bought_today` set)
- 청산 후 **7영업일 쿨다운**
- 신규 매수 차단 조건: `is_max_positions()` / `is_daily_loss_exceeded()` / `state.buy_disabled` / `registry.is_ticker_blocked_for_buy()`

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 20%
- 일일 최대 손실 한도: 할당 자금의 8% (`daily_loss_limit=-8.0`)
- 동시 보유 종목 수: 최대 5종목

### 기본 파라미터 (`DEFAULT_PARAMS`)
```python
DEFAULT_PARAMS = {
    "tradable_boards": ["main"],
    "exchange": "KRX",
    # 추세 필터 — 미너비니 원설계 50/150/200(실효 장기선은 daily_fetch_depth_mode 가 정한다)
    "ema_short": 50,
    "ema_mid": 150,
    "ema_long": 200,
    "long_ema_uptrend_days": 20,
    # 베이스
    "base_min_days": 25,
    "base_max_days": 75,
    "base_depth_pct": 0.30,
    # 조정 시퀀스
    "pullback_count_min": 2,
    "pullback_count_max": 4,
    "last_pullback_max": 0.12,
    "min_swing_atr_mult": 1.0,  # 노이즈 swing 필터 (베이스 ATR × 1.0)
    # 거래량 수축
    "volume_contraction_ratio": 0.70,
    # 매수
    "breakout_volume_mult": 1.5,
    "entry_start": "09:05",
    "entry_end": "14:30",
    "max_breakout_extension_pct": 7.5,  # 추격 상한 — 정체성 상수, PARAM_RANGES 미편입
    "position_ratio": 0.20,
    "max_positions": 5,
    # 청산
    "stop_loss_rate": -7.0,
    "atr_period": 14,
    "atr_trail_mult": 2.0,
    "breakeven_promote_atr": 0.0,  # 브레이크이븐 승격, 0=비활성(다크런치). PARAM_RANGES/INT_PARAMS 미편입
    "reentry_cooldown_days": 7,
    # ── 터틀 유닛 sizing + 하드손절 ATR화 (다크런치) ──
    # 게이트는 sizing_mode 가 아니라 `_entry_atr` 스탬프 존재. 전 키 PARAM_RANGES/INT_PARAMS 미편입
    "sizing_mode": "position_ratio",
    "risk_pct": 0.005,
    "stop_atr": 2.0,
    "turtle_backstop_pct": -9.0,
    "min_vol_floor_pct": 1.0,
    "max_lot_units": 2.0,      # cycle242 — 랏당 최대 유닛(K). PARAM_RANGES/INT_PARAMS 미편입
    "max_lot_ratio_mult": 2.5, # cycle245 — 랏 명목 ρ축 상한(K_ρ). 명목 ≤ K_ρ×position_ratio×예산, 1주도 못 사면 미매수.
                               # K축과 `min` 합성(cycle254). PARAM_RANGES 미편입. 롤백 = 20.0
    "turtle_min_stop_pct": -5.0,
    # 유니버스 — 전체 상장 ∩ 시총≥100억 ∩ 거래대금≥10억 (지수 제약 없음)
    "min_market_cap": 10_000_000_000,
    "min_trade_amount": 1_000_000_000,
    "max_scan_stocks": 4000,
    # 일반
    "daily_loss_limit": -8.0,
    # 장중 킬스위치 — 값은 order_engine 코드 상수와 동일(행위 변경 0).
    "order_exchange_clock_mode": "enforce",
    "after_market_exit_division": "44",
}
```

### 운영 노트
- 미네르비니식 셋업은 빈번하지 않음 — 정상 운영에서도 일일 후보 0~5 종목이 정상
- 멀티데이 보유 — donchian_swing 과 동일 부류, `_MULTIDAY_STRATEGIES` 멤버 등록 필수
- VTS(모의) 검증 가능 — KRX 메인 한정

### BFB/VCP 구독 배선
BFB/VCP 매수 신호는 (donchian 의 폴링 루프와 달리) `risk.on_tick`(WebSocket tick) 으로만 평가된다. 그래서 두 전략의 후보는 반드시 `scheduler._collect_breakout_tickers()` 순회 대상(VB/LTV/BFB/VCP 4 전략)에 들어 있어야 한다 — 이 함수 하나가 (a) `_scan_loop` extra, (b) `_collect_presubscribe_tickers`(07:59 사전구독), (c) `_build_priority_groups()["breakout"]` 세 구독 경로의 소스다. 빠지면 후보가 tick 을 못 받아 매수 평가가 영영 일어나지 않는다.
- **우선순위**: BFB/VCP 후보도 VB/LTV 와 동일하게 `breakout` 그룹 = **LOW + `bypass_limit=False`** 로 유입돼 `[priority_drop]` 대상이다(설계대로). HIGH(positions/next_day_clear) `bypass_limit=True` 41슬롯 절대 보장은 무접촉이다.
- **가시성**: `_build_subscription_source_counts()` 가 `bfb`/`vcp` 카운트를 낸다.
- `_universe_excluded_today` 필터는 BFB/VCP 후보에도 동일 적용된다.

---

## 7. 공통 규칙

### 부분 체결 처리
- 시장가 주문도 호가 잔량 부족 시 부분 체결 가능
- 부분 체결 시: trade_history에 PARTIAL 상태로 기록, 체결된 수량만 반영
- 미체결 잔량: 30초 대기 후 미체결이면 잔여 주문 취소
- 손절 시 부분 체결: 체결된 부분은 손절 완료로 처리, 잔여는 재주문

### 체결 기반 포지션 관리
- **체결통보 WebSocket 구독 필수**: 시세 외에 체결통보(실전: H0STCNI0, 모의: H0STCNI9)를 반드시 구독해야 함
- **시세 채널은 KRX 전용 `H0STCNT0` + NXT 전용 `H0NXCNT0` 2채널이다** (cycle293·294, 2026-09-14).
  통합 `H0UNCNT0` 은 `stock_master.nxt_tradable=False` 종목의 체결을 보내지 않아 폐기했다 —
  정상 경로에서 반환하지 않는다. 세 TR_ID 는 **47필드 포맷이 같아 파서가 하나**이고, `handler` 가
  `on_tick` 에 tr_id 를 넘기지 않으므로 **매매 로직은 어느 채널에서 온 틱인지 모른다**.
  🔴 그래서 **한 종목을 두 채널에 동시 구독하는 것이 금지**다(같은 키에 두 누적값이 번갈아 쓰인다).
  거래소 식별은 시세가 아니라 체결통보 `ODER_KIND` 필드에서 한다
- **장운영정보 H0UNMKO0 구독** (실전 한정): 대표 종목(`005930`) 1개로 보드 전환 코드(`MKOP_CLS_CODE`) 실시간 수신
- 주문 접수 시 pending_buys에 등록 (중복 주문 차단)
- **체결통보 수신 시** 포지션 등록/제거 (주문 직후가 아님 — 체결 확인 전 포지션 등록하면 안 됨)
- 주문번호 매핑(`_order_qty`/`_order_strategy`/`_order_ticker`) 등록은 `place_order` 응답 직후 동기 영역에서. `await insert_trade` 진입 전 (시장가 즉시체결 race 방지)
- 체결통보 선행 race 가드: `_completed_orders` set + UPDATE 0건 보정 INSERT
- 기동 시: KIS 주문체결내역 API + DB trade_history.strategy로 포지션/미체결 복구
- 매수일자(buy_date) 기반 익일 청산 판정 (시간 기준이 아님)

### 매수 안전장치
- **종목코드 형식 비대칭**: 진입은 6자리 숫자만(`isdigit`) — ETF·신주인수권 차단. 사후처리(체결통보·잔고 sync)는 6자리 영숫자(`isalnum`) 허용
- **매수가능 캐시**: 60초 TTL — KIS `get_buyable()` 호출을 매 틱 → 분당 1회로 축소
- **잔고부족 매수 락**: 900초 — `is_insufficient_cash` 응답 또는 `max_buy_quantity≤0` 시 다음 잔고 sync까지 매수 차단
- **per-ticker low_funds cooldown**: 900초 — `calc_buy_quantity()<=0`인 종목 매 틱 반복 호출 차단
- **매도 잔고부족 즉시 break**: `is_insufficient_quantity` 응답 시 3회 재시도 생략 + 메모리·DB positions 정리

### 스케줄 — KRX/NXT 통합 운영 (08:00~20:00)

| 시각 | 동작 |
|------|------|
| 07:45 | 자동 매매 시작 (`AUTO_START` + DB 재확인. 주말+공휴일 KIS chk-holiday로 자동 건너뜀) |
| 07:45 직후 | `_boot()` — 프로세스 기동, OAuth 토큰 갱신, DB 포지션/설정 복구, 전략별 자금 분배, 전략 prepare(일봉/K값/전일종가/도치안 단계별 통계). `start()` 안에서 **즉시** 돌기 때문에 자동 기동이면 07:45 직후이고, 수동 재기동이면 그 시각이다 |
| 07:59 | WebSocket 연결, **체결통보(H0STCNI0/9) 구독** + **통합 장운영정보(H0UNMKO0/005930) 구독** + 사전 구독(돌파+스윙+보유 합집합). `_boot()` 완료 뒤로 띄워 race 를 피한다 |
| 08:00 | NXT 프리 진입 — 익일 청산 백그라운드(30초 안정화 후 NXT 시가 청산) + 돌파 시가 확정(`board="pre_nxt"`) + LTV PRE_NXT 매수 시작(VB 는 MAIN 전용 — 프리장은 보유 매도만) |
| 09:00:05 | KRX 메인 시가 확정 — VB/LTV `board="main"` 별도 시가 + KRX 09:00 시가 + (전일Range × `k_value_krx_main`) Target_Price 계산 → MAIN 매매 진입 |
| 09:05~09:30 | donchian_swing 진입창 — 시장가 1주문/종목, 갭 +3%↑ 스킵 |
| 09:30 | 모멘텀 종목 스캔 시작. 5분 주기 `_scan_loop` 시작(돌파+스윙+보유 합집합 재구독) |
| 15:20 | KRX 메인 신규 매수 중단 + KRX 메인 강제 청산(`_force_clear_main_only`) — 청산 목록은 각 전략 `check_force_clear()` 가 정한다(VB 전량 · LTV 는 `_limit_up_reached` 상한가 모드만 제외) |
| 15:30 | KRX 메인 마감 (종가 흡수 마진 시작, `_force_clear_main_only` 가드 기준). 스케줄러는 여기서 `post_nxt_trading` 으로 넘어가고 `_confirm_breakout_open_prices(board="post_nxt")` 를 부른다 — `post_nxt` **보드**가 열리는 15:40 보다 10분 앞선다 |
| 15:40 | NXT 애프터 진입 — LTV 는 POST_NXT 신규 매수, VB 는 보유 매도만 |
| 16:10 | KIS CTPF1002R 종목 basics 매스 보강 |
| 16:15 | 일봉 retention purge (`DAILY_RETENTION_DAYS`) |
| 16:20 | 저녁 잠정 funnel 캡처 (운영자 밤 후보 확인) |
| 16:30 | KIS 종목 마스터 파일 적재 (`master_raw`) |
| 16:40 | 재무 5 TR 주1회 적재 (`stock_master_financial`) |
| 19:50 | NXT 애프터 신규 매수 중단 (`buy_disabled = True`) |
| 20:00 | NXT 애프터 종료(WebSocket 구독 해제) + 전략수정 AI자문 생성(OpenAI → `parameter_recommendations`, 동기 순차 ~3분). 같은 20:00 이 **기동 거부 경계**(`TIME_SESSION_START_CUTOFF`)다 |
| 20:00:05 | 전체 유니버스 적재 (`_full_universe_load`, AI자문 직후 5초 마진) |
| 20:05 | metrics 1차 스냅샷(`daily_metrics_snapshot`, OpenAI 미호출) — `api_metrics`·`strategy_funnel` 은 프로세스 메모리 전용이라 정산까지 기다리면 유실 노출이 90분이다 |
| 20:30 | KIS 일봉 일괄 적재 (`stock_master_daily`) — KRX 애프터마켓(16:00~20:00) 종료 후 = 그날 거래량이 확정된 뒤. 전략 진입 판정이 읽는 전일봉 거래량의 품질을 결정한다 |
| 21:30 | 전략별 + 합산 일일 정산, daily_performance 기록, 일일 로그 분석 리포트 생성(OpenAI → `daily_log_reports`, 완전판이 20:05 1차 행을 덮어쓴다), 로그 retention purge, 프로세스 Sleep |

### 야간 매매(POST_NXT 15:40~20:00) 운용 원칙
- 사용자 부재 시간대 사고 위험 인지 — Settings 상단 amber 경고 배너 노출
- 손절·트레일링은 실시간 작동
- NXT 거래대금 KRX 대비 ~10%로 변동성 큼 → 보드별 K 곱(`k_value_nxt_post`) 1.2~1.5 보수 운용 권장
- 비활성화 원하면 Settings 페이지에서 해당 전략의 `tradable_boards`에서 POST_NXT 해제

### API Rate Limit 대응
- 초당 20건 제한 준수
- 일괄 매도(손절 동시 발생) 시 asyncio.Semaphore로 큐잉
- 주문이 지연되더라도 순차 실행 보장

### 환경 설정
- .env의 `KIS_ENV`로 실전/모의 전환 (인증 정보 자동 매핑)
- 모든 TR_ID는 `settings.get_tr_id()`로 환경별 자동 변환
- **모의(VTS)는 KRX만 지원** — SOR/NXT는 실전 한정. 모의에서 NXT/SOR 시도 시 KIS가 거절
- 실전 전환 시 반드시 팀장 승인 필요

### 전략별 잔고/실적 관리
- trade_history: strategy 컬럼으로 전략별 거래내역 분리
- daily_performance: (date, strategy) 복합PK로 전략별 + 합산 실적 기록
- 정산은 **21:30** — `total_asset` 계산 시점이 그때라 종가는 애프터마켓 20:00 마지막 체결가다.

### 시간 상수 (`src/engine/scheduler.py`)
| 상수 | 값 | 의미 |
|---|---|---|
| `TIME_AUTO_START` | 07:45 | 자동 매매 시작 |
| `TIME_BOOT` | 07:55 | **런타임 미사용** — `_boot()` 는 `start()` 안에서 즉시 돈다(07:45 자동 기동이면 그 직후). 값만 테스트가 핀한다 |
| `TIME_PRESUBSCRIBE` | 07:59 | 사전 구독 (_boot 완료 후 4분 마진, race 회피) |
| `TIME_PRE_NXT_OPEN` | 08:00 | NXT 프리 진입 (익일 청산 + LTV PRE_NXT) |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | KRX 메인 시가 확정 |
| `TIME_SCAN_START` | 09:30 | 모멘텀 스캔 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | KRX 메인 매수 중단 + 강제 청산 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감 (종가 흡수 마진 시작, `_force_clear_main_only` 가드 기준) |
| `TIME_POST_NXT_OPEN` | 15:40 | **런타임 미사용** — 스케줄러의 POST_NXT 전환과 `post_nxt` 시가 확정은 `TIME_KRX_MAIN_CLOSE`(15:30) 직후다. 보드 경계 15:40 의 정본은 `session._BOARD_SCHEDULE` 이다 |
| `TIME_STOCK_MASTER_BASICS_REFRESH` | 16:10 | KIS CTPF1002R 매스 보강 |
| `TIME_STOCK_MASTER_DAILY_PURGE` | 16:15 | `stock_master_daily` retention purge |
| `TIME_EVENING_FUNNEL_CAPTURE` | 16:20 | 저녁 잠정 funnel 캡처 |
| `TIME_STOCK_MASTER_MASTER_LOAD` | 16:30 | KIS 종목 마스터 파일 적재 |
| `TIME_STOCK_MASTER_FINANCIAL_LOAD` | 16:40 | 재무 5 TR 주1회 적재 |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | NXT 애프터 매수 중단 (안전 마감, 변경 금지) |
| `TIME_NXT_POST_CLOSE` | 20:00 | NXT 애프터 종료, unsubscribe |
| `TIME_RECOMMENDATION` | 20:00 | AI자문 생성 |
| `TIME_FULL_UNIVERSE_LOAD` | 20:00:05 | 전체 유니버스 적재 (AI자문 직후 5초 마진) |
| `TIME_SESSION_START_CUTOFF` | 20:00 | `scheduler.start()` 기동 거부 경계. `run_daily` 의 일자 전환 판정도 같은 상수를 쓴다(갈리면 그 창에서 헛 재시도가 돈다). ⚠️ 그 창의 재기동은 그날 20:30 일봉 적재를 잃는다 |
| `TIME_METRICS_SNAPSHOT` | 20:05 | metrics 1차 스냅샷 (OpenAI 미호출, `reset_request_metrics()` 미호출) |
| `TIME_STOCK_MASTER_DAILY_LOAD` | 20:30 | KIS 일봉 일괄 적재 — 애프터마켓 종료 후 |
| `TIME_SETTLEMENT` | 21:30 | 정산 + 일일 로그 분석. 일봉 적재(20:30) 뒤여야 한다. 주기 task 수명 상한이기도 하다 |
| `NEXT_DAY_STABILIZE_SECS` | 30 | 익일 청산 NXT 프리 시가 안정화 |
| `SESSION_TICK_INTERVAL` | 30 | SessionTracker 보드 전환 감시 주기 |

### 위험 요약 (실전 전환 전 검토)
1. **VTS 검증 불가** — SOR/NXT는 실전 한정. 카나리 운영 어려움
2. **NXT 거래대금 ~10%** — 시가 흔들림이 매매 신호 노이즈로 작용 가능
3. **야간 매매 모니터링 부재** — 사용자 부재 시간대 사고 위험. POST_NXT는 명시 토글로만 활성
4. **정산 시각(21:30) 의존** — daily_performance 의 'date' 의미, EC2 자동 재시작 정책, 익일 부팅 시각이 모두 여기에 묶여 있다
5. **종목 적격성** — NXT 거래 가능 종목이 KRX 전 종목인지 일부인지 명세 미기재. 운영 데이터로 검증 필요

## 8. 운영 규칙 (전략 공통 인프라)

전략 매매 규칙(§2~§7) 밖에서 매매에 영향을 주는 규칙을 모은다. 도입 경위·실측·회귀 가드 목록은
[history](../docs/history/workspace-00_leader_trading_rules.history.md) 에 있다.

### 8-1. AI 자문 (20:00) — 생성 · 검증 · 적용

`src/engine/recommendation_engine.py::generate_recommendations` 가 전략별 1행씩
`parameter_recommendations` 에 INSERT 한다. **자동 적용은 weight 감액 한 가지뿐**이고 나머지는
전부 운영자 수동 검토 후 명시 적용이다.

- **DB 컬럼**: `recommended_params`(화이트리스트 키만) · `recommended_weight NUMERIC`(0.0~1.0, null=권고 없음) · `weight_reasoning TEXT`(≤1000자) · `code_review_notes TEXT`(≤2000자, 자유 텍스트) · `applied_weight NUMERIC` · `backtest_summary JSONB`.
- **user_payload**: 자기 전략 통계 + `current_weight` + `peer_weights`(다른 enabled 전략) + `peer_metrics` + (매크로 레짐 활성 시) `MarketRegime.to_advisor_dict()` 12키.
- **검증 `_validate_recommendations`** (5-tuple `(validated_params, reasoning, weight, notes, weight_reasoning)`):
  - `recommended_weight` = float 캐스트 + `0.0 <= x <= 1.0`. 범위 밖이면 None 으로 무시 + WARNING.
  - `weight is None` → `weight_reasoning` 도 None 으로 자동 정리. weight 는 있는데 사유가 비었으면 `WEIGHT_REASONING_FALLBACK="(사유 미제공)"` + WARNING.
  - `code_review_notes` 2000자 초과는 잘라내고, 비-str 이면 None.
  - **`code_review_notes` 텍스트로 코드를 자동 변경하지 않는다 — 정보 표시 전용이다.**
- **수동 apply** `POST /api/recommendations/{id}/apply` (body `apply_keys` / `apply_weight: bool=False`):
  - 이 라우트는 `ApiResponse` 래퍼라 **4xx 를 내지 않는다** — 클라이언트는 status code 가 아니라 `success` 플래그로 분기한다. `apply_weight=true` 인데 `recommended_weight` 가 null 이면 200 + `success=false`.
  - **증액 Σ 가드**: `apply_weight=true` 이고 **증액**일 때만, 나머지 전략 현재 비중 합 + 신규값 > `1.0 + 1e-3` 이면 `success=false` + `[weight_sum_violation]` WARNING. 위치는 params/weight/DB 어떤 변경도 일어나기 **전** early return 이다. **감액은 Σ 검사 없이 항상 통과** — Σ>1 로 오염된 상태의 유일한 복구 수단이기 때문이다.
  - 적용은 `save_weights({strategy_id: w})` + `strategy.config.weight` **직접 대입**이다. `registry.update_weights()` 는 부르지 않는다(`config.enabled = weight > 0` 자동 토글 부작용 차단).
  - **`allocate_funds()` 즉시 재호출 금지** — 다음 `_boot()`(다음 영업일 기동 직후)에서 자연 반영된다.
- **자동 적용 `auto_apply_recommendations(target_date)`** — 20:00 자문 INSERT 직후 스케줄러가 부른다.
  - `system_config.auto_apply_enabled` 가 False/None 이면 즉시 `{applied:0, skipped:0, reason:"disabled"}`. **기본 False.**
  - `recommended_weight` 가 None 이거나 **현재 weight 이상(증액)**이면 SKIP + `[auto_apply_skip_increase]`.
  - 적용값 = `max(recommended_weight, current_weight × 0.5)` — **50% cap**. 상태는 수동 `applied` 와 구분되는 `applied_auto` 로 마킹하고 `[auto_weight_apply]` 1행을 남긴다.
  - **파라미터 자동 적용은 없다** — `_CONSERVATIVE_KEYS = frozenset()`(빈 집합)이라 손절·일일한도·비중 키가 전량 제외돼 `[auto_params_apply]` 는 발화하지 않는다. 진입/청산 임계는 전략 정체성 상수이고, 단조 조임 ratchet 이 donchian 을 교살한 선례가 있다. ⚠️ 프론트 토글 문구(`IntegrationToggleCard.tsx::AUTO_APPLY_META`)는 아직 "보수적 파라미터 자동 적용" 이라 코드와 어긋나 있다.
  - 라우트 = `GET/PUT /api/integrations/auto-apply` (`{enabled: bool}`), UI 토글은 ConfirmModal 이중 확인.
- **metrics 손절 정규화** `recommendation_metrics._normalize_stop_loss_rate(params)` — 후보 **5키**(`stop_loss_rate` / `intraday_stop_loss` / `overnight_stop_loss` / `stop_loss_main` / `stop_loss_pre_nxt`)를 모아 **음수만** 인정하고 `min`(절대값 최대 = 가장 보수적)을 돌려준다. 후보가 없으면 `0.0` 이고 `compute_metrics` 의 손절 분기가 skip 된다. ⚠️ **kojiro 는 이 헬퍼의 대상이 아니다** — 하드손절 키가 `hard_stop_pct` 라 5키 어디에도 없어 `stop_loss_hits` 가 항상 0 이다.

### 8-2. `PARAM_RANGES` / `INT_PARAMS`

`recommendation_engine.PARAM_RANGES` 에 있는 키만 AI 자문이 추천할 수 있고, `INT_PARAMS ⊆ PARAM_RANGES` 가 규약이다(정수 캐스트 대상).

- **편입 금지 = 정체성 상수.** 진입 임계(`max_positions` · `buy_threshold` · `donchian_period` · `max_breakout_extension_pct` · `open_entry_hold_secs` · `open_price_scope_mode`)와 청산 임계(`atr_trail_mult` · `breakout_fail_n_days` · `breakeven_promote_atr` · `channel_exit_period`), 리스크 정체성 상수(`max_lot_units` K · `max_lot_ratio_mult` K_ρ · `rank_w_*`), 킬스위치·LLM 키가 여기 해당한다.
- **왜**: 최근 손실을 목적함수로 삼는 튜너는 표본이 적을 때 "최근 손실 거래를 지우는 값" 으로 수렴한다 — 청산 임계를 조이면 추세추종이 데이트레이딩으로 변태하고, 진입 임계를 조이면 신호가 말라붙는다. 라이브 값이 허용 범위의 **하한에 정확히 붙어 있으면** 그건 과튜닝 서명이다.
- **`atr_trail_mult` 는 3전략 공유 키**(`donchian_swing`·`vcp_breakout`·`bull_flag_breakout`, 전부 DEFAULT 2.0)라 제외가 세 전략에 함께 걸린다. 근거 표본은 donchian 뿐이므로 **VCP 또는 BFB 의 청산 왕복이 ≥20 쌓이면 그 전략에 한해 재편입 여부를 독립 판정**한다. 키를 전략별로 나눠야 하면 kojiro 의 `stop_atr`/`trail_atr` 고유명 선례를 따른다.

### 8-3. 시장 레짐 — **관찰 전용**

`dkstock.cloud` 매크로를 `_boot()` 에서 1회 fetch 해 `market_regime_snapshots` 에 1행 남긴다.

- **레짐은 매수를 차단하거나 축소하지 않는다.** `risk.on_tick`/`_swing_buy_poll_loop` 의 게이트는 존재하지 않는다. 레짐 대응은 **`cash_usage_ratio` 하나로만** 한다.
- **`cash_usage_ratio` 자동 조정**: `clamp((100 − regime.params.cash_min) / 100, 0.0, 1.0)` — defensive(75)→0.25 / neutral(50)→0.5 / aggressive(20)→0.8. `auto_regime_adjust=true`(기본)일 때만 갱신하고 `false` 면 운영자 수동값을 보존한다.
- **외부 실패 graceful**: fetch 실패·timeout·토큰 만료·토글 OFF → `MarketRegime.empty()` → `cash_usage_ratio` 자동 갱신 안 함(수동값 유지), 자동매매 본 흐름 영향 0.
- `get_current_regime()` 는 `_boot()` 1회 호출을 가정한 모듈 싱글톤이다(동시성 lock 없음 — 단일 워커 전제). 소비처는 대시보드 `/current` 와 AI 자문 payload **표시 전용**이다.

### 8-4. 매수 가드 `buy_block_mode` — 표시 전용

`buy_block_mode`(`OFF`/`WARN`/`SOFT`/`HARD`, 기본 `HARD`)와 4 임계(`buy_block_vix_threshold` 25.0 / `buy_block_fg_high_threshold` 85.0 / `buy_block_fg_low_threshold` 15.0 / `buy_block_regime_defensive_enabled` true)는 `system_config` 에 남아 있으나 **어느 값이든 매매 행위를 바꾸지 않는다**.

- HARD 로 둬도 매수는 차단되지 않고 SOFT 로 둬도 수량은 축소되지 않는다. `order_engine.execute_buy(soft_multiplier=)` 는 시그니처만 남고 호출자가 0건이다.
- 모드/임계 변경은 대시보드·자문 payload 표기에만 반영된다. **실제 위험 축소가 필요하면 `cash_usage_ratio` 또는 전략 weight 를 조정한다.**
- 라우트 = `GET/PUT /api/integrations/buy-block`. `get_buy_block_state()` 는 60초 TTL 캐시(`BUY_BLOCK_CACHE_TTL=60.0`)를 쓰고 **DB 폴백 결과(`db_ok=False`)는 캐시에 저장하지 않는다**(운영자가 임계를 바꿔도 폴백 값이 영구 캐시되는 결함 차단). PUT 응답 끝에서 `invalidate_buy_block_cache()` 를 graceful 호출해 다음 평가부터 즉시 반영한다.

### 8-5. VB 보드별 손절 `_get_stop_loss_for_board`

우선순위 = ① 활성 보드 키 `params.get(f"stop_loss_{board}")` 가 **음수**면 채택 → ② top-level `stop_loss_rate` → ③ 둘 다 없으면 `0.0` 반환(손절 분기 skip).

- 활성 보드는 VB 내부 `_resolve_active_board()` 가 `SessionTracker.active` ∩ `tradable_boards` 에서 고른다. 예외는 흡수하고 None 을 돌려주며, None 이면 top-level 로 폴백한다(테스트 환경·부팅 직후 race 안전).
- `check_exit_signal(ticker, current_price, open_price)` 시그니처는 **7 전략 공통**이라 보드 인자를 추가하지 않는다 — 보드는 전략이 스스로 조회한다(`risk.py` 변경 0).
- `stop_loss_main` / `stop_loss_pre_nxt` 는 VB `DEFAULT_PARAMS` 에 **없다**. `supabase/migrations/024_vb_board_stop_loss_defaults.sql` 이 `stop_loss_rate` 값을 복사해 DB `strategy_config.params` 에만 주입하고, 소스 참조는 `recommendation_engine.PARAM_RANGES` / `recommendation_metrics._normalize_stop_loss_rate` / `portfolio_risk` 뿐이다. 코드 fallback 기본값은 **-3.0** 이다.
- ⚠️ **`stop_loss_pre_nxt` 는 적용 경로가 없다** — VB 가 `DEFAULT_TRADABLE_BOARDS=("main",)` 라 `_resolve_active_board()` 가 `pre_nxt` 를 반환하지 않는다. 값을 넣어도 손절은 `stop_loss_main` → `stop_loss_rate` 로만 결정된다(DB 호환 보존 키).
- **STOP_LOSS 우선순위 보존** — 보드별 손절 > 익일 청산(NEXT_DAY_CLEAR). 손절은 `_next_day_clear_pending` 가드의 영향을 받지 않는다.

### 8-6. 외부 통합 토글 — DB 우선 / `.env` fallback

`dkstock_regime_enabled` · `kis_mcp_enabled` · `auto_regime_adjust` · `auto_apply_enabled` 는 `system_config` 키이고, 헬퍼는 키 부재 시 `None` 을 돌려줘 호출자가 `.env` 로 폴백한다(하위 호환).

- 클라이언트는 **매 호출 DB 조회**(캐시 없음)라 토글이 즉시 반영된다.
- `dkstock-regime` 을 켜면 `asyncio.create_task` 로 백그라운드 fetch 를 발화하고 API 는 즉시 응답한다(fetch 실패해도 토글 자체는 성공). 끄면 메모리 regime 을 empty 로 reset 한다 — 표시·자문 payload·`cash_usage_ratio` 자동 조정만 멈춘다(매수 차단 효과는 애초에 없다).
- `kis_mcp_enabled` 토글은 즉시 fetch 하지 않는다 — 백테스트는 20:00 자문 시점에 발화한다.
- 모드 변경은 ConfirmModal 이중 확인, 임계값 변경은 즉시 저장이다.

### 8-7. 시스템 로그 — 검색과 retention

- **검색** `GET /api/logs/search` — `message ILIKE %q%`(파라미터 바인딩, SQL 인젝션 안전) + level/start/end 동시 조건. 빈 `q` 는 422. `SEARCH_DEFAULT_LIMIT=200` / `SEARCH_MAX_LIMIT=1000` clamp, 응답 `{logs, total, has_more}`. 검색 모드에서는 페이징·자동 새로고침을 끈다.
- **retention** `purge_old_logs()` — `INFO_RETENTION_DAYS=2` / `HIGH_RETENTION_DAYS=30`(`HIGH_LEVELS=("WARNING","ERROR","CRITICAL")`) 등급별 분리 DELETE, 1회 cap `MAX_PURGE_BATCH=100_000`, `[log_retention]` INFO 1행.
- **실행 시점** = 정산 흐름 안 — `generate_daily_log_report()` **뒤**, `_reset_daily_state()` **앞**. 로그 분석이 `system_logs` 를 읽은 다음에 지운다. 예외는 graceful(`[log_retention_skip]` + 다음 사이클 재시도).
- **WHERE cutoff 가 None 이면 `RuntimeError`** 를 즉시 raise 한다 — 전체 DELETE 사고를 막는 방어 코드다. 조용히 넘어가지 않는다.

### 8-8. 보조 KIS 계좌와 시세 풀

**자금 안전 절대 원칙 (불변)** — 매매 주문(`src/api/order.py`) · 잔고(`src/api/balance.py`) · 체결조회 · 체결통보(`H0STCNI0`/`H0STCNI9`) 구독은 **영원히 메인 계좌 단일**이다. 보조 계좌(`kis_quote_accounts`)는 **시세 수신 전용**이고 자금과 무관하다.

- 코드 가드 3중: `WebsocketPool.subscribe()` 가 체결통보 tr_id 면 priority 를 무시하고 메인으로 우회(`_enforce_main_only_execution_notice` 위반 시 `QuoteSessionExecutionNoticeError`) · REST 는 `_QUOTE_ALLOWED_PATHS` 화이트리스트(**현재 13 path**) 밖이면 `QuotePoolPathError` · `order`/`balance` 모듈이 시세 풀을 import 하지 않음을 테스트가 단언.
- ⚠️ **신규 시세성 TR 을 도입하면 화이트리스트에 등록한다** — 누락하면 매 부팅 `QuotePoolPathError` 가 난다(실제로 3회 반복된 사고 클래스다).
- **REST 분배**: `kis_get_quote`/`kis_post_quote` → `_select_quote_label()` 라운드로빈(`(idx+1) % len(active_labels)` + `asyncio.Lock`), per-label `Semaphore(18)`(메인 20 보다 보수적), 메트릭은 `get_quote_request_metrics().by_label` 로 분리된다. 보조 토큰 매니저 발급 실패(`ValueError`)는 메인 fallback.
- **WebSocket 분배**: HIGH(보유/익일청산) → 메인 세션 + `bypass_limit=True` 절대 보장 / LOW(스캐닝) → 보조 세션 라운드로빈(가득·disconnect 세션은 건너뛰고, 모두 불가면 메인 fallback). 총 슬롯 = `MAX_SUBSCRIPTIONS × (1 + N)`.
- **중복 ticker 는 메인 우선**: 메인에 있는 ticker 가 LOW 로 다시 오면 메인 유지 / 보조에 있는 ticker 가 HIGH 로 오면 보조 `unsubscribe` + 메인 `subscribe(bypass_limit=True)` 승격 + `[pool_promote] ticker=… old=<DB 라벨> new=main`. 양쪽 동시 등록은 같은 tick 중복 처리 + 슬롯 낭비라 금지한다.
- **모든 세션 가득** → drop + `[priority_drop_pool] tr_key=… priority=LOW reason=all_sessions_full main=N/41 quotes=M`, `subscribe()` 는 `None` 반환.
- **세션 라벨은 DB `kis_quote_accounts.label`** 이다(`"main"` + 라벨들, 미설정 시 `"unknown"`).
- 보조 계좌 자격은 응답 모델에 평문 필드 자체가 없고(`app_secret_masked` = `****` + 마지막 4자리, 8자리 미만은 `****` 통일) 평문은 토큰 매니저 전용 함수 `get_credentials_for_token_manager(label)` 만 본다. PUT 은 `active`/`label` 만 수정 가능하다 — 키 교체는 삭제 후 재등록이다.
- **보조 0개면 메인 단독 동작**과 완전히 같다(회귀 0). 운영자가 등록하면 다음 `_boot` 사이클부터 분배가 시작된다.

### 8-9. 보조 세션 헬스 · 5xx 다이제스트

`src/services/quote_session_health.py::QuoteSessionHealthMonitor` 가 보조 세션만 추적한다(**메인 라벨 `"main"` 은 제외** — 안전 가드).

- **자동 비활성 트리거**: (a) `MAX_CONSECUTIVE_FAILURES=5` 연속 실패 (b) `WINDOW_SECS=300` sliding window 에서 `MIN_CALLS_FOR_RATE=10` 이상 호출 중 실패율 ≥ `MAX_FAILURE_RATE=0.5`.
- 트리거 시 ① `kis_quote_accounts.update_account(active=False)` ② `kis_ws_pool.disable_quote_session(label)` ③ `[quote_session_disabled]` 영구 1행. DB update 실패는 graceful(메모리는 비활성 유지 + `[quote_session_health_db_fail]` WARNING). 두 번째 호출은 idempotent.
- **fast window**: `FAST_WINDOW_SECS=60` / `FAST_MIN_CALLS=10` / `FAST_MAX_FAILURE_RATE=0.8` — 라벨 선택 직후 이 비율을 넘으면 재시도 backoff 없이 **즉시 메인 fallback** 한다(`get_recent_5xx_ratio(label)`).
- **기록 대상**: 성공(`rt_cd=="0"`, 보조 라벨) → `record_success` / 5xx → `record_failure(reason=f"http_{status}")` / 보조 토큰 발급 실패 → `record_failure(reason="token_issue_fail")`. **KIS 비즈니스 거부(`rt_cd!=0`)와 네트워크 에러는 기록하지 않는다**(세션 건강과 무관하다).
- **5xx 로그 dedupe**: 동일 `(path, label, status)` 를 `_QUOTE_5XX_DEDUPE_WINDOW=60.0`초 창으로 묶어 WARNING 1행 + 60초 주기 summary 1행(`count >= 2` 인 키만). 메인 요청 dedupe state 와 분리돼 있다.
- **복귀 절차**: Settings UI 에서 `active=true` 토글 → **다음 영업일 `_boot()`(기동 직후)부터** 풀에 재참여한다. 당일 즉시 재참여는 미지원이다(동일 토큰 패턴 차단 + 운영자 진단 시간 확보). 긴급하면 컨테이너 재기동 시점에 반영된다.

### 8-10. WebSocket stale watcher 임계

- 발화 주기 `STALE_WATCHER_INTERVAL_SECS=120`(scheduler) · 신선도 판정 `STALE_FRESHNESS_SECS=60`(stale_diagnostics).
- 1~5회(`MAX_STALE_RETRIES=5`) stale 은 즉시 `unsubscribe_in_pool` + `subscribe` **강제 재등록**(KIS "기등록 재등록 금지" 반영). 우선순위는 분리한다 — 보유·익일청산은 HIGH + `bypass_limit=True`, 그 외 후보는 LOW + `bypass_limit=False`(메인 편중 차단).
- 5회 초과는 시간 기반 force_retry — `STALE_FORCE_RETRY_AFTER_SECS=600`, 시간당 `STALE_FORCE_RETRY_HOURLY_CAP=6` cap(LMS·앱키 정지 위험 차단).
- **stale universe 가드**: stale>5 + 당일 누적 체결량 < `UNIVERSE_LOW_VOLUME_THRESHOLD=10_000` 이면 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO. **보유·익일청산은 절대 보호**하고 `_reset_daily_state` 에서 동행 clear 한다(영구 블랙리스트 금지).

### 8-11. 포트폴리오 리스크·섹터 노출 — **관찰 전용**

- **오픈 리스크 프록시** = `buy_price × quantity × |하드손절%| / 100`.
- **전략별 하드손절%** = 손절 후보 **7키**(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt`/`turtle_backstop_pct`/`hard_stop_pct`) 중 음수만 모아 `min`(최대 계획 손실). **결측은 −7.0 fail-open**(0.0 금지 — 0 은 "리스크 없음" 으로 읽힌다).
- **섹터 분류 정본** = `src/engine/sector_naming.py::resolve_sector_name` **단일 진실원**(portfolio 라우트·일일리포트·잔고 3 소비처 공유, 이식 금지). 우선순위 ① basics raw `bstp_kor_isnm`(업종 한글명) → ② `kojiro._kojiro_sector_key(master_raw)`(KRX 산업지수 플래그, 소스 = `stock_master.get_master_raw`) → ③ `미분류-{ticker}` 독립 취급(fail-open). 따라서 `by_sector` 키는 대개 업종 한글명이고 KRX 플래그 키는 ①이 빈 종목에만 나타난다.
- **집계** = 총 명목 / 총 오픈리스크 / 순자산 대비% / 동시보유 수 / 전략별·섹터별 분해 / top 섹터. 노출 = `GET /api/portfolio/risk`(pull) + 21:30 일일 리포트 metrics `portfolio_risk_snapshot` + `[portfolio_risk]` 구조화 로그 1행(정산 경로 한정).
- **금기**: 이 지표로 **매수 차단·수량 축소·포지션 배제를 하지 않는다**(SOFT 상한은 별도 사이클) · 8영역 무접촉 의무 · 신규 임계 `PARAM_RANGES` 편입 금지(정체성 상수).

### 8-12. 컨테이너 토큰 캐시 권한

`Dockerfile` prod 스테이지의 **순서가 계약**이다 — ① `mkdir -p /app/.token_cache` ② `chown -R appuser:appuser /app` ③ `chmod 755 /app/.token_cache` ④ `USER appuser`. 호스트 bind mount 가 디렉터리를 root:root 로 새로 만들면 non-root 프로세스가 토큰 캐시를 쓰지 못해 `PermissionError` 가 난다(2026-05-20 운영 사고). 회귀 가드 = `tests/integration/test_dockerfile_token_cache_perms.py`.
