# Phase 2 — 터틀 유닛 자금관리 전면 전환 구현계획

> 산출: ultracode 워크플로우(15 에이전트: 자금관리 표면 매핑 + domain-expert 자문 + 4차원 설계 + 5렌즈 적대검증 18 findings + 종합).
> 상태: **구현 전 설계 확정본**. 각 단계 = 사용자 승인 게이트 + domain-consult 선행(하네스: 자금관리 필수) + TDD.

## 1. Context — 무엇을 왜

- **문제**: Phase 1 에서 kojiro 는 청산(2ATR 손절)은 터틀식이나 sizing 은 `position_ratio` = **반쪽 상태**. "1유닛 = 예산 고정 리스크" 불변식이 sizing 쪽에서 미복원.
- **목표**: `position_ratio`(순자산×weight×ratio) → **터틀 유닛 sizing**(`unit = floor(budget×risk_pct / ATR)`)으로 전환해 **리스크 정규화**(변동성 무관 유닛당 동일 리스크). 손절 = 진입가 − stop_atr×ATR 을 전제로 "sizing↔stop ATR 커플링" 불변식 확립.
- **전환 방식**: 공통 turtle 인프라(순수 sizing 헬퍼 + 계좌 유닛 카운트) + **전략별 `sizing_mode` 플래그**('turtle' | 'position_ratio') opt-in. 기본 `position_ratio` → 미전환 전략 회귀 0, fallback 영구 보존.

### ⚠️ 핵심 재구성 (사용자 확정 방향 정정 — "전면 전환"의 현실적 범위)
도메인 자문이 "Phase A = kojiro + donchian/VCP/BFB 즉시 opt-in"을 절반 정정:
1. **즉시 sizing-only opt-in 가능 = kojiro 하나** (손절이 이미 2ATR). donchian/VCP/BFB 하드손절은 **여전히 고정%(-7/-5/-7)**, ATR은 트레일링 전용 → sizing만 바꾸면 불변식 붕괴 + 함정#1(저ATR 대량매수+깊은%손절=리스크 집중) 발동 → **sizing+하드손절ATR화 묶음(2A-2)**.
2. **momentum/VB 는 turtle 영구 제외** — momentum 은 실시간·당일 %무브 정체성 + ATR 무의미/부재, VB 는 15:20 당일청산이라 vol정규화 실익 낮음.
3. **Phase B 실질 turtle 후보 = LTV 하나** (상한가 2모드 stop 재설계 선행, 조건부).
4. **피라미딩·entry_atr 영속 = 2C 완전 이연** → 2A/2B 스키마 변경 0.

즉 현실적 "전면 전환" 종착점 = **kojiro + donchian + VCP + BFB (+ LTV 조건부)** 가 turtle, **momentum/VB 는 position_ratio 영구**.

## 2. 도메인 확정 (a~i)

| 항목 | 결론 |
|---|---|
| (a) risk_pct | **0.5%** 우선 (3안: 0.5/0.75/1.0). KR 갭리스크가 2ATR 손절 관통(하한가 −30%) → 레퍼런스 1% 공격적. ⚠️ "10유닛=계좌 20%" 산술은 per-strategy-budget 에서 무효 = 실제 총리스크 Σ(weightᵢ×risk_pct×stop_atr) 분포 의존. 라이브 후 ratchet-up |
| (b) 유닛 한도 | registry **additive read-only on-demand 카운트** (2C 전 1포지션=1유닛 → 영속 카운터·migration 불필요). 캡 게이트 = 매수입구 **await-free 동기 블록** |
| (c) 섹터 소스 | `master_raw.bstp_larg_div_code`(대분류). 결측=섹터캡 skip + 계좌캡 백스톱. coarse 시 중분류 튜닝 |
| (d) weight 재해석 | **per-strategy-budget**: unit_size total_capital = `state.total_investment`. `allocate_funds` 무변경, weight 의미 보존, turtle↔position_ratio 현금 경합 제거. 계좌 10유닛 캡이 계좌레벨 통제 대행 |
| (e) 피라미딩 | 2C 분리, **영구보류 가능**(터틀 필수 아님, KR 상한가 캡으로 runway 짧음) |
| (f) momentum ATR | **영구 position_ratio 제외**. VB 도 제외 권고 |
| (g) entry_atr 영속 | 2A/2B 불필요(fresh-ATR + tighten-only floor). **단 재시작 loosen 위험 → stop_floor 영속/재구성 필수화**. 유닛별 entry_atr 는 2C migration |
| (h) 조기진입 | 2A 배선만(`compute_unit_qty(fraction=0.5)`), `allow_early_entry=False` 다크런치 유지 |
| (i) 단계 순서 | 2A-1 → 2A-2 → 2B → 2C(보류) → 2D(조건부) |

## 3. 단계 로드맵

### 공통 인프라 (2A-1 선결)
**신규 `src/engine/turtle_sizing.py`** (순수모듈, 8영역·DB/HTTP/시계 미접촉 — `quant_score.py`/`kojiro_indicators.py` 선례):
- `compute_unit_qty(strategy_budget, atr_value, risk_pct, *, fraction=1.0) -> int` = `floor(budget×risk_pct/atr×fraction)`, `atr<=0 or risk_pct<=0 → 0` (레퍼런스 `money.py:12-22` 이식). total_capital = **`state.total_investment`**(전략예산).
- `affordable_qty(...)` (money.py:35-40, 2C 유닛별 현금검증용 — 2A 는 execute_buy `max_buy_qty` 재사용).

**DEFAULT_PARAMS 신규 4키** (전략별, `{**DEFAULT_PARAMS, **config.params}` 병합 = DB 미저장 안전, kojiro 선례): `sizing_mode="position_ratio"` / `risk_pct=0.005` / `max_units_per_stock=2` / `max_units_total=10`.
**PARAM_RANGES/INT_PARAMS 미등록** (사이클 208/209/212 기전 자동 폐기 + 210 auto_apply 미접촉).

### Phase 2A-1 — kojiro 단독 opt-in (GO, stop 무변경)
- `strategies/kojiro.py::calc_buy_quantity` — turtle 분기 삽입: `sizing_mode=='turtle'` 시 `compute_unit_qty(total_investment, _candidates[ticker]['atr'], risk_pct)` + 예산잔여 클램프, **try/except fail-open → position_ratio 낙하**.
- **`order_engine.py::execute_buy`(:265) — 안 A 확정**: `calc_buy_quantity(current_price, ticker)` ticker 전달. **안 B(check_buy_signal stash) 폐기**(멀티세션 recv + swing poll + kojiro 이중 매수경로 stash race = 금전 오류).
- **7전략 전부 시그니처 원자 갱신**: `calc_buy_quantity(self, current_price, ticker=None)` (본체 불변, additive). 미갱신 시 위치인자 3개 → hot path TypeError 크래시. **order_engine 호출부 + 7 시그니처 = 동일 커밋 원자화**.
- stop 무변경 (kojiro check_exit 이미 2ATR + tighten-only + −8% backstop). backstop 비대칭(고변동 종목 실효손절 −8% 캡 → 유닛 실리스크 < 명목, 보수적).
- **회귀 가드**: INV(qty×ATR≈budget×risk_pct) / FALLBACK(risk_pct 결측·atr 0·_candidates 부재 4조합 → position_ratio) / SIG(7전략 2-arg 호출 + AST) / REGRESS(미전환 6전략 turtle 주입해도 byte 동일) / BACKSTOP.
- **8영역**: order_engine diff(호출 1줄 + ticker, 순수 additive). GO 즉시(kojiro 다크런치, 라이브 영향 0) + domain-consult(risk_pct 최종값).

### Phase 2A-2 — donchian/VCP/BFB opt-in (조건부, sizing+하드손절 ATR화 묶음)
- 각 `calc_buy_quantity` turtle 분기(2A-1 동일) **AND** 각 `check_exit_signal` 하드손절 `stop_loss_rate -7/-5/-7% → 진입가 − stop_atr×ATR` + **tighten-only floor 이식**(kojiro `_stop_floor` 패턴, 재시작 loosen 차단).
- **ATR 정의 통일**: sizing ATR = 손절 ATR 동일 소스(donchian `_atr` SMA14 / BFB·VCP atr14 각자). `get_atr` 재사용 금지.
- **risk_model 결합 가드**: 단일 sizing_mode 플래그가 sizing+stop 미결합 → turtle 분기가 ATR-stop 활성 assert, 또는 `risk_model='turtle'` 통합 스위치. AST 로 "sizing=turtle인데 고정% 손절" 조합 영구 차단.
- **갭데이 가드**: kojiro 갭 skip(갭업≥5%/갭다운≤−4%) 패리티 + intraday ATR floor (저ATR qty 팽창 + KR ±30% 갭 → 2ATR 관통 방어).
- **회귀 가드**: TRAP1(하드손절 고정% 아님 AST+행위) / COUPLE(risk_model assert) / TIGHTEN(재시작 non-loosen).
- **8영역**: check_exit 변경 = 매매 행위 직접 변경(strategies 파일=8영역 밖이나 청산=HIGH). GO 조건: 2A-1 라이브 안정 + **전략별 domain-consult**(하드손절 %→ATR 이 정체성·청산 통계 영향, stop_atr 값) + 사용자 승인.

### Phase 2B — 계좌 10유닛 / 섹터 3유닛 캡 (GO, 2A 라이브 후)
- `strategy_registry.py`(**8영역**) additive read-only: `count_open_units()`(turtle 전략 `len(positions)+len(pending_buys)`, **pending 포함 이중매수 방지**, **ticker set 중복제거**) / `count_units_by_sector(ticker, sector_map)`(**내부 await 금지**, 60s TTL 동기 섹터맵) / `can_add_turtle_unit(...)`(캡 값 호출자 주입).
- **캡 게이트 = execute_buy `calc_buy_quantity(:265) 후 ~ pending_buys.add(:306) 전` await-free 동기 블록**. **불변식(하드): count-read↔pending.add 사이 await 0건**(섹터 조회는 gate 진입 전 1회 await → 스칼라 주입). turtle 종목만, `is_ticker_blocked_for_buy` 본체 불변. 초과 시 `[turtle_unit_cap_block]` DailyEmitCap.
- **pending 재조정**: 미체결 LIMIT pending 무기한 잔존 = 슬롯 starvation → sync(15분)에서 회수 or 접수시각 TTL.
- **max_positions**: 전략별 로컬 서브캡 + 글로벌 10유닛 AND. Σmax_positions(turtle) > 10 → 글로벌 캡 실질 바인딩 = **현행 대비 노출 축소(개선)**. daily_loss_limit 독립 병존.
- **회귀 가드**: REG-1/2/3(allocate_funds·is_ticker_blocked·update_weights 불변) / GATE-1/2/3(10유닛·섹터·position_ratio 무영향) / **ATOMIC(await 0건 AST)** / **RACE(2 task 인터리브 9+1pending=10 → 11번째 차단)** / DEDUP / STARVE / SAFETY(7영역 diff 0).
- **8영역**: strategy_registry + order_engine diff(순수 additive 증명). GO: 2A 라이브 + 섹터 대분류 실측 + domain-consult.

### Phase 2C — 피라미딩 (보류/조건부, 영구보류 가능)
- **판정**: 터틀 정체성상 선택. 2A/2B 가 가치 80%를 회귀 20%로 전달. **롤아웃을 피라미딩에 볼모잡지 않음.**
- **재평가 트리거**: 2B 라이브 후 (+1ATR 수익+추세유지 종목 ≥30% AND 증축 이득 > 트레일링 손실) 입증 시에만 발의. 관찰은 코드 변경 최소(로그만).
- **IF 발의 청사진**(이중 opt-in `sizing_mode='turtle' AND allow_pyramiding=True`): `positions.units JSONB` additive migration(유닛별 entry_price/qty/entry_atr) + execute_buy `pyramid_add` keyword + `is_ticker_blocked_for_pyramid`(self-strategy has_position 예외). **적대검증 F-2C1~7 필수 흡수**: 부분체결 staging 분리 / boot_manager units 복구 / 부활 차단 / entry_atr stash / max_units in-flight 포함 / 매도 Σqty broker 재확인 / 관찰 로그 DailyEmitCap.
- **8영역**: order_engine + strategy_registry 2파일 행위 변경 = 최대 회귀면. domain-consult 재확인.

### Phase 2D — momentum/VB 영구 제외 + LTV 조건부
- **momentum 영구 position_ratio**: prepare 빈stub·일봉 0건·당일 ATR stale·신규상장 부재. calc_buy_quantity 무변경(시그니처 ticker만). DB sizing_mode='turtle' **명시 무시** + `getattr(self,'_candidates',{})` 안전접근 + turtle 분기 0건 AST.
- **VB 제외 권고**: 15:20 당일청산 → vol정규화 실익 낮음.
- **LTV 조건부**: prepare 22봉 ATR 저렴이나 **상한가 2모드 stop(−3%/−5%) ATR화 재설계 선행**. domain-consult 후 결정.

## 4. 적대검증 18 findings — 흡수 (요약)
**HIGH**: 안A 확정(kojiro 이중경로 stash race 폐기) / 7전략 시그니처 원자 커밋 / 캡 게이트 await-free(:224후 폐기, :265후~:306전) / "on-demand=race부재" 논거 폐기(원자성 불변식+RACE 가드) / per-strategy "20%계좌" 산술 정정 / 재시작 stop_floor 영속(tighten-only) / 2C 부분체결·재시작·부활 6종.
**MEDIUM**: turtle 분기 try/except fail-open / fallback 4조합 / 섹터 await gate 전 1회 / ticker 중복제거 / pending starvation 회수 / total_investment boot drift 명문화 / risk_model 결합 assert / 갭데이 오버사이징 skip.

## 5. 리스크 & 배포 전략
- **8영역 불가피 변경분**(order_engine 2A-1 ticker·2B 게이트·2C pyramid / strategy_registry 2B 카운트): 전부 sizing_mode='turtle' opt-in 분기 격리 → position_ratio 경로 byte 동일 AST + `git diff` 순수 additive.
- **독립 배포 순서**: 2A-1(kojiro 다크런치 sizing) → 2A-2(donchian/VCP/BFB 전략별 순차, domain+승인) → 2B(캡, 섹터 실측 선행) → 2C(관찰 후 발의/영구보류) → 2D(momentum/VB 확정 제외, LTV 조건부).
- **미결(라이브 계측)**: risk_pct 0.5% 실효성 / 섹터 대분류 coarse 여부 / total_investment boot 스냅샷 drift / 혼재 현금초과 빈도.

## 6. 검증
- **불변식**: turtle 진입 시 `qty × stop_atr × ATR ≈ total_investment × risk_pct × stop_atr`(클램프 미발동, ±1주). 클램프 binding `qty=min(unit_size, budget_qty, max_buy_qty)` 재현.
- **8영역 diff 관리**: 각 단계 `git diff -- <8영역>` 순수 additive(opt-in 분기 + 신규 메서드), 미전환 전략 byte 동일.
- **오케스트레이션**: 메인(설계) → domain-consult → tdd-engineer(Red) → backend-dev(Green) → tester(8영역 diff + 불변식). 2A-2/2C/2D HIGH = 사용자 승인 게이트.

## 부록 — 정독 앵커
`_workspace/kojiro_ma/kojiro/money.py`(unit_size:12/affordable:35) · `strategy_registry.py`(allocate_funds:42/is_ticker_blocked_for_buy:86-98) · `kojiro.py`(DEFAULT_PARAMS:100/check_exit:636/calc:691/_candidates:126) · `order_engine.py`(execute_buy:204/calc호출:265/max_buy_qty:299/pending.add:306/_handle_buy_fill:982) · `donchian_swing.py`(exit:899/calc:948) · `vcp_breakout.py`(exit:1002/calc:1059) · `bull_flag_breakout.py`(exit:883/calc:956) · `momentum.py`(calc:205) · `volatility_breakout.py`(calc:938) · `long_tail_volatility.py`(calc:876) · `strategy_config.py`(save_params:75) · `stock_master.py`(get_master_raw:196) · `recommendation_engine.py`(PARAM_RANGES:67/검증:187) · **신규 `turtle_sizing.py`**. **2A/2B 스키마 변경 0, 2C만 positions.units migration.**
