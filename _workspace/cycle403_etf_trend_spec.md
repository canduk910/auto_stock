# cycle403 — ETF 추세 전략(`etf_trend`) 구현 명세 (team-leader 분해본)

- 정본 설계 = `_workspace/design/2026-09-27_etf_trend_strategy.md`(10-02 확정판). 이 문서는 그 설계를 **구현 단위로 쪼갠 것**이고, 설계가 「확인 필요」로 남긴 자리를 팀장이 정한 값(**L-결정**)을 담는다. 충돌하면 이 문서의 L-결정이 이긴다(설계가 구현 사이클에 맡긴 자리라서).
- 작업 디렉터리 = `/Users/koscom/Projects/auto_stock_c403` (브랜치 `feat/cycle403-etf-trend`). 이 밖 쓰기 금지.
- 🔴 **이번 사이클에 하지 않는 것**: main 병합 · push · 배포 · 운영 DB 쓰기 · 마이그레이션 적용 · **8영역 수정**(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**`) · `scheduler.py` 수정 · `Signal` enum 수정(cycle402 소관) · git checkout --/stash/reset · 커밋.
- 🔴 `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES` 에 `"etf_trend"` 를 **넣지 않는다**(R3 승인 대기). 그래서 교차 검사 `_TICK_BUY_EVAL_SKIP_STRATEGIES == frozenset(SWING_POLL_IDS)` **1건은 붉은 채로 둔다**(xfail·skip 로 덮지 않는다). 이 밖의 붉은 테스트는 0 이어야 한다. 다른 8영역 상수(예: `session._DEFAULT_TRADABLE_BOARDS`)를 요구하는 검사가 붉어지면 고치지 말고 팀장에게 보고한다.

## 1. 파일 지도

| 자리 | 할 일 |
|---|---|
| 새 `src/engine/etf_trend_core.py` | **순수 leaf** — 표준 라이브러리(`math`)만. `src.*` import 0 · I/O 0 · `await` 0 · 로깅 0. 지표·신호·청산선·사이징 판정 함수(§3). 재현 스크립트와 같은 식 |
| 새 `src/engine/strategies/etf_trend.py` | `EtfTrendStrategy(StrategyBase)` (§4~§8) |
| `src/db/stock_master.py` | `list_etf_trend_universe(min_market_cap_eok: int = 500) -> list[dict]` 추가(§4.1). 기존 함수 무접촉 |
| `src/engine/strategy_manifest.py` | import 블록 **끝**에 `from src.engine.strategies.etf_trend import EtfTrendStrategy` + 명부 **끝**에 1행(L2) |
| `src/engine/strategy_base.py` | `Position._MULTIDAY_STRATEGIES` 리터럴에 `"etf_trend"` 추가. 그 밖 무접촉 |
| `src/engine/status_exit_watch.py` | `_GROUP` 에 `"etf_trend": 3` |
| `src/engine/param_catalog.py` | `STRATEGY_IDS` 끝에 `"etf_trend"` · 새 키 등재 · `_TURTLE4` → 5전략(이름을 `_TURTLE_SIZED` 로 바꾸고 참조 전부 갱신, 별칭 남기지 않음) · `market_unit_mode` `applies_to` 에 포함 |
| `funnel_capture._ORDER` 등 명부 id 교차 검사 대상 | 필요 시 `etf_trend` 추가 |
| `supabase/migrations/044_etf_trend_seed.sql` | 시드 행(§9). **파일만**, 적용 금지 |
| 프론트 | `frontend/src/utils/strategyMeta.ts` 표시명 「ETF 추세」+색 · `StockMaster.tsx` `FIELD_LABELS`(+`CATEGORY_KEYS`) 에 `scty_grp_id_cd`(증권그룹코드)·`etf_txtn_type_cd`(ETF 과세유형코드)·`etf_chas_erng_rt_dbnb`(ETF 추적배수)·`etf_etn_ivst_heed_item_yn`(ETF/ETN 투자유의) · 전략 선택지 목록이 하드코딩된 곳 |
| 문서 | `src/engine/strategies/CLAUDE.md`(카탈로그 행·사이징 매트릭스 행·「멀티데이 보유 전략」 절의 `check_force_clear()==[]` 문장을 「`close_at_1520=False` 이거나, `True` 면 그날 끝낼 종목만(전량 반환 금지)」 로) · `_workspace/00_leader_trading_rules.md`(팀장이 쓴다) |
| 테스트 열거 목록 | `test_cycle233_ast_account_risk.py` `GATE_FIRST_FILES`/`GATE_PRE_BUY_FILES` · `test_budget_limit_ast.py` `STRATEGY_FILES` · cycle382 `TURTLE_FILES` · cycle399 섀도 AST(S01/S08) · cycle384 `buy_paused` AST · G-245 · ETF G4 허용 목록 · `test_cycle278_ast_catalog_guards.py` `_DEFAULT_PARAMS_SHA` 재핀 · 명부/골든 G1(「등록 7행」→ 8행, **생성기로 재생성**, 의도된 변경) |

## 2. L-결정 (팀장)

- **L1 표시명** = `"ETF 추세"`(R7).
- **L2 명부 행** = `StrategyEntry(EtfTrendStrategy, "etf_trend", "ETF 추세", False, 0.0, eval_driver="swing_poll", breakout_rank=None, open_price_target=False, close_at_1520=True, market_unit_policy="scale")` — 끝에.
- **L3 섀도 기본값** = 이 전략만 `DEFAULT_PARAMS["shadow_mode"] = True`(S1 = 섀도 시작, 비중 0 과 이중 안전). 공통 키 AST(S08 등)가 「7전략 같은 값 False」를 단언하면 **`etf_trend: True` 명시 예외**로 고친다(예외 목록은 리터럴, 이유 한 줄). `market_unit_mode = "shadow"`.
- **L4 시장 유닛** — `market_unit_mode != "off"` 이면(= shadow·enforce 둘 다) `_market_unit_view()` 의 `state == "unavailable"` → `NONE` + `reason=market_unit_unavailable`, `m <= 0` → `NONE` + `reason=zero_state`. 이것은 이 전략 **신호 정의**(재현이 m>0 만 산다)라 shadow 에서도 거른다. 랏 축소(`m<1`)는 enforce 일 때만(터틀 4전략과 같은 `_market_unit_sizing`/`_market_unit_blocks_entry` 경로). `off` 이면 m=1 취급(거르지 않음).
- **L5 1주 폴백 금지** — `calc_buy_quantity` 는 터틀 유닛이 0 이면 **관문 앞에서 리터럴 `0`** 을 돌려준다(position_ratio 낙하·1주 폴백 없음). 유닛 > 0 이면 `_apply_budget_limit(qty, price, ticker)` 를 거친다(관문 본문·순서 무접촉, 관문은 qty>0 에서 폴백하지 않는다). 신호 단계에서 같은 순수 계산으로 0 이면 `NONE` + `reason=rounds_to_zero`. 단 **전략 예산(`state.total_investment`) ≤ 0** 이면 랏 판정을 건너뛰고: 섀도 켜짐 → 섀도 관문으로 간다(S1 은 비중 0 이라 이것이 기록의 유일한 길) / 섀도 꺼짐 → `NONE` + `reason=no_budget`.
- **L6 `min_vol_floor_pct` = 0.0** — 재현에는 N 기준 floor 가 없다(N>0 만). ATR20 밴드(1~6%)가 변동성 하한을 맡는다. floor 를 1.0 으로 두면 재현이 산 거래를 라이브가 0주로 거른다.
- **L7 장중 붕괴 스킵** = `current_price < open_price` 이면 `NONE` + `reason=collapse`, **래치 없음**(다음 폴에서 다시 본다). 갭 스킵 두 규칙은 `_bought_today` 래치(그날 끝).
- **L8 묶음 캡** = 이 전략의 `state.positions` ∪ `state.pending_buys` 중 후보와 같은 묶음이 있으면 `NONE` + `reason=cluster_held`, 래치 없음. 묶음 = prepare 가 계산한 쌍 집합(§4.3). 판정 불가(상관 None)는 같은 묶음이 아니다(재현 `same_cluster` 와 같게 — 구현 전 재현 `same_cluster` 를 읽고 그대로).
- **L9 청산 신호 종류** — 하드·본전 = `Signal.STOP_LOSS`, 트레일링·10일 채널 = `Signal.TRAILING_STOP`, 15:20 돌파 실패 = `check_force_clear()` 반환(스케줄러가 `Signal.FORCE_CLEAR` 로 판다). 소스에 `# TODO(cycle402 병합 뒤): R4=(b) — 15:20 돌파 실패 사유를 Signal.TREND_EXIT 로` 를 남긴다. 사유 구분은 `[etf_trend_exit] reason=breakout_fail_1520` 마커.
- **L10 15:20 판단 가격** = `scanner.ticker_prices[t]["current_price"]`, 나이는 `scanner.ticker_last_tick[t]`(KST datetime). 값이 없거나 0, 또는 나이 > `breakout_fail_price_max_age_secs`(180) 이면 **팔지 않는다** + `[etf_trend_1520_stale]` WARNING(1회/종목/일). 돌파선 결측도 팔지 않는다 + WARNING. 함수 지역 import(`from src.engine.scanner import ...`)로 읽는다 — scanner 는 읽기만(8영역 무접촉).
- **L11 시각 게이트** — 매수 창 09:05~09:30(`datetime.now().time()`, donchian 과 같은 모양). `check_force_clear` 에는 벽시계 게이트를 두지 않는다(스케줄러가 15:20 에만 부르고 15:30 이후는 스케줄러가 건너뛴다). 테스트는 freezegun 으로 창 안·밖 두 시각.
- **L12 키 이름** — donchian 과 같은 뜻은 같은 이름을 쓴다: `donchian_period`20 · `long_ma_period`60 · `volume_period`20 · `volume_multiplier`1.5 · `atr_period`14 · `atr_trail_mult`1.8 · `gap_skip_threshold`3.0 · `stop_atr`2.0 · `turtle_backstop_pct`−9.0 · `breakeven_promote_atr`1.5 · `channel_exit_period`10 · `sizing_mode`"turtle" · `risk_pct`0.01 · `position_ratio`0.25 · `max_positions`4 · `min_vol_floor_pct`0.0 · `min_market_cap`50_000_000_000 · `exchange`"KRX" · `tradable_boards`["main"]. 새 키: `gap_over_line_pct`4.0 · `min_trade_amount_20d`2_000_000_000 · `min_price`1_000 · `max_price`500_000 · `atr_band_period`20 · `atr_ratio_min`0.01 · `atr_ratio_max`0.06 · `min_bars`100 · `quality_window`60 · `daily_fetch_rows`225 · `cluster_corr_window`120 · `cluster_corr_min_obs`60 · `cluster_corr_threshold`0.9 · `breakout_fail_min_bars`2 · `breakout_fail_price_max_age_secs`180. 공통 키: `max_lot_units`2.0 · `max_lot_ratio_mult`2.5 · `market_unit_mode`"shadow" · `buy_paused`False · `shadow_mode`**True** · `order_exchange_clock_mode`"enforce" · `after_market_exit_division`"44" · LLM 4키(donchian 과 같은 값) · `daily_loss_limit` 등 base 가 요구하는 키는 donchian 값. 🔴 **이 전략의 키는 하나도 `PARAM_RANGES`/`INT_PARAMS`(AI 자동 튜닝)에 넣지 않는다**(S1 동안 AI 자문 적용 제외, 설계 §7.1). param_catalog 등재는 PUT 통로용.
- **L13 마이그레이션 번호** = `044`. 내용 = `INSERT INTO strategy_config (strategy_id, enabled, weight, params) VALUES ('etf_trend', false, 0, '{}'::jsonb) ON CONFLICT (strategy_id) DO NOTHING;`(컬럼은 실제 스키마를 보고 맞춘다). CI 하네스가 마이그레이션을 glob 하면 테스트 DB 에는 적용돼도 된다.

## 3. 순수 leaf `etf_trend_core.py` — 재현과 같은 식

재현 정본 = `_workspace/domain_consult/cycle391_etf_s0_remeasure.py` 의 `build_ticker`(지표) · `gen_trades` donchian 분기(신호·갭) · `sim_donchian`(청산, `intraday_line=False`) · `same_cluster`/`Corr`(묶음). 같은 입력에서 같은 결과를 내야 한다(동등성 테스트 §10).

봉 입력 = 날짜 오름차순 리스트(o,h,l,c,trade_value). 인덱스 j = 신호봉 t.

- `ema(values, span)` — `e[0]=v[0]`, `e[i]=a·v[i]+(1−a)·e[i−1]`, `a=2/(span+1)` (= pandas `ewm(span, adjust=False)`).
- `true_ranges(h,l,c)` — `tr[0]=h[0]−l[0]`, `tr[i]=max(h−l, |h−c[i−1]|, |l−c[i−1]|)`.
- `atr_wilder(tr, period=20)` — `ewm(alpha=1/period, adjust=False)` 를 tr[0] 부터(재현 `atr20`).
- `n14(tr, i)` — `tr[i−13..i]` 단순평균, tr[0] 은 제외(재현은 tr[0]=NaN 로 둔 뒤 rolling 14) → 첫 값은 i=14.
- `breakout_line(h, j, period=20)` — `max(h[j−20..j−1])`, j≥20 일 때만.
- `tv20(tv, j)` = `mean(tv[j−19..j])` · `tv_prev20(tv, j)` = `mean(tv[j−20..j−1])`.
- `entry_signal(...)` — 재현 조건 그대로: `tv20 ≥ min_trade_amount_20d` ∧ `close ≥ min_price` ∧ `atr20/close ≥ atr_ratio_min` ∧ `close ≤ max_price` ∧ `atr20/close ≤ atr_ratio_max` ∧ `line>0 ∧ close>line` ∧ `ema60[j]>ema60[j−1] ∧ close>ema60[j]` ∧ `tv_prev20>0 ∧ tv[j] ≥ 1.5·tv_prev20` ∧ `N>0` ∧ 봉 수 ≥ `min_bars`. 반환 = 판정 + 어느 단계에서 떨어졌는지(깔때기용) + `line`·`N`·`atr20`·`tv20`·`close`.
- `gap_skip_reason(open, close_t, line, gap_pct=3.0, over_line_pct=4.0)` → `"gap_up"`(open ≥ close_t×1.03) · `"gap_over_line"`(open > line×1.04) · `None`.
- `hard_stop(E, N, backstop_pct=−9.0, stop_atr=2.0)` = `max(E − 2N, E×0.91)`; N 결측/0 이면 `E×0.91`.
- `stop_line(E, N, hsb_closed, ...)` = `max(hard, E if hsb_closed ≥ E+1.5N else −inf, hsb_closed − 1.8N)`; hsb_closed 없음(매수일) = hard.
- `channel_low(lows_prev, period=10)` = 직전 10봉 저가 최솟값(매수일 다음 봉부터 적용).
- `breakout_failed(price, line, bars_since_buy, min_bars=2)` = `bars_since_buy ≥ 2 ∧ price < line`.
- `unit_qty(budget, N, price, risk_pct, position_ratio, remaining)` — `turtle_sizing.compute_unit_qty_guarded` 를 쓰지 말고 leaf 는 **같은 식의 순수 판정 보조**만 두거나, 사이징은 전략 파일에서 `compute_unit_qty_guarded(min_vol_pct=0.0)` 를 부른다(새 수식 금지 — 전략 파일 쪽 권장).
- `simulate_exit(o,h,l,c,j)` — `sim_donchian(d, j)` 와 **같은 (k, px, why)** 를 내는 재현 함수. 위 함수들로 조립(재현 틀 `tools/replay/` 용).
- `return_correlation(closes_a, closes_b, window=120, min_obs=60)` — 일간수익률 상관, 관측 < 60 또는 표준편차 0 이면 `None`. 날짜 정렬(같은 날짜끼리)로 맞춘다.

## 4. `prepare(self, *, as_of=None)` — 07:45

1. **유니버스(SQL)** `list_etf_trend_universe()` — `stock_master` 에서 `master_raw->>'scty_grp_id_cd' = 'EF'`(그룹 코드 상수는 `etf_like.ETF_GROUP_CODES` 의 `"EF"` 를 공유) ∧ `etf_txtn_type_cd='01'` ∧ `etf_chas_erng_rt_dbnb='1'` ∧ `coalesce(etf_etn_ivst_heed_item_yn,'N') <> 'Y'` ∧ `hts_avls_eok ≥ 500` ∧ ticker 6자리 숫자. 실제 raw 칼럼 이름은 스키마로 확인. 반환 = ticker·name·hts_avls_eok.
2. 종목별 `stock_master_daily.get_recent_daily(t, daily_fetch_rows)` (DB 만, KIS 폴백 없음, 결손 = 후보 아님 `reason=data_gap`). KODEX 200 `069500` 일봉도 읽어 기준 날짜로 쓴다.
3. 일봉 품질: 봉 수 ≥ 100 · 최신 봉 날짜 = 069500 최신 봉 날짜 · 069500 최근 60봉 날짜가 모두 그 종목에 있다.
4. 신호봉 t = 최신 봉. `entry_signal`. 통과 → `_candidates[t] = {prev_close, line, n (=N), atr (=N — 사이징 ATR 키, 시장 유닛 `_MARKET_UNIT_ATR_KEY="atr"` 와 같게), atr20, tv20, ema60, cluster_key}`.
5. 묶음: 후보 ∪ 이 전략 보유 종목 사이 모든 쌍의 상관을 계산해 `> 0.9` 인 쌍을 `_cluster_pairs`(frozenset 쌍 집합)로. 상태는 매일 새로 만든다(영속 맵 금지).
6. `_scanned_tickers` = 후보를 `tv20` 내림차순. `get_scanned_tickers()` 가 이 순서를 돌려준다(스윙 폴 순서).
7. 시장 유닛 스냅샷 갱신 — donchian 과 같은 자리에서 `_refresh_market_unit(...)`.
8. 깔때기 단계(설계 §7.4) `_record_funnel_step`. 마커 `[etf_trend_universe]`(단계별 수·묶음 수·m) · `[etf_trend_signal]`(후보·line·N·tv20 순서) INFO 1회.
9. 미리보기(`_resolve_prepare_as_of` preview) 경로는 donchian 의 모양을 따른다.

## 5. `check_buy_signal(ticker, current_price, open_price)` — 순서가 계약

1. `if self._account_soft_gate_blocked(ticker): return Signal.NONE` — **첫 문장**.
2. `buy_disabled` · 보유/주문중 · 당일매도 · `_bought_today` · `is_max_positions()` · `is_daily_loss_exceeded()` → NONE.
3. `info = _candidates.get(ticker)` 없으면 NONE.
4. 시각 09:05~09:30 밖 NONE.
5. 갭 스킵(L7) → `_bought_today` 래치 + `[etf_trend_skip] reason=gap_up|gap_over_line`.
6. 붕괴(L7) → NONE 래치 없음.
7. 묶음(L8).
8. 시장 유닛(L4) → `zero_state`/`market_unit_unavailable`; 이어서 `_market_unit_blocks_entry(ticker, current_price)`.
9. 랏(L5) → `rounds_to_zero`/`no_budget`.
10. `if self._shadow_buy_intercepted(ticker, current_price, open_price, level=info["line"]): return Signal.NONE`.
11. 상태 변경: `_bought_today.add` · `_breakout_line[ticker] = info["line"]` · `buy_signals` append(20개 상한) · `return Signal.BUY`.

- `[etf_trend_skip]` INFO 1회/(종목, 사유)/일(`DailyEmitCap` 류 기존 도구). 관측 예외는 판정을 바꾸지 않는다.
- `await` 0 · I/O 0.

## 6. `calc_buy_quantity(current_price, ticker=None)`

- `current_price <= 0` → `0`.
- `lots = self._market_unit_sizing(current_price, ticker)`; 값이 있으면 donchian 과 같게(`lot_after<=0 → 0`, turtle 경로면 `_entry_atr[ticker]=lots.atr`, `_apply_budget_limit(lots.design_after, ...)`).
- 아니면 `compute_unit_qty_guarded(budget, N, price, risk_pct, remaining_budget=…, min_vol_pct=params["min_vol_floor_pct"], position_ratio=…)`. `>0` → `_entry_atr[ticker] = N`(사이징 N 과 같은 값 — 커플링 불변식) 후 `_apply_budget_limit(qty, price, ticker)`. `0` → `return 0`(L5).
- `ticker is None` 또는 N 결측 → `0`.

## 7. 청산

### 7.1 `check_exit_signal(ticker, current_price, open_price)` — 선 1~4

상태: `_entry_atr[t]`(N) · `_hsb_closed[t]`(매수일~전일 완성봉 고가 최대, 매수 당일은 없음) · `_channel_low[t]` · `_bars_since_buy[t]`(매수일 포함 완성봉 수).

- 실효 손절선 = `stop_line(E=pos.buy_price, N, hsb_closed)`. `current_price <= 선` → 하드/본전이 지배하면 `STOP_LOSS`, 트레일링이 지배하면 `TRAILING_STOP`.
- `bars_since_buy ≥ 1 ∧ channel_low > 0 ∧ current_price < channel_low` → `TRAILING_STOP`.
- 장중 고가로 선을 올리지 않는다(`pos.high_since_buy` 는 선 계산에 쓰지 않는다 — 설계 §4.1 「선 갱신 시점」).
- `[etf_trend_exit] reason=hard|breakeven|trail|channel entry_n= hold_bars=` INFO(1회/종목/일, 신호 반환은 cap 밖).
- 15:30 종가 틱 신호는 그대로 `STOP_LOSS`/`TRAILING_STOP` 을 돌려준다(시각 게이트 금지 — 「`tradable_boards` 는 매수 진입 전용」). 관측만 `[etf_trend_close_print_exit]` WARNING(15:30 이후 시각에서 발생 시).

### 7.2 `check_force_clear() -> list[str]` — 선 5, never-raise

- 보유 각 종목: 돌파선 결측 → 건너뜀 + WARNING · `_bars_since_buy < breakout_fail_min_bars` → 건너뜀 · 가격(L10) 결측/낡음 → 건너뜀 + WARNING · `price < line` → 목록에 넣고 `[etf_trend_exit] reason=breakout_fail_1520 price= line= age_s=`.
- 돌파선 위 보유는 **절대** 반환하지 않는다. 전량 반환 금지.
- 요약 `[etf_trend_1520_check] held= checked= below= missing_line= stale=` INFO 1회/일.
- 함수 전체 try/except → 예외 시 `[]` + `[etf_trend_1520_error]` WARNING.

### 7.3 `get_effective_stop_price(ticker)` — read-only 미러

선 1~4 의 max(정수). 로그·상태 변경 0, 예외 → None.

### 7.4 `recompute_held_atr()` — 부팅 복구 한 곳

보유 각 종목: 일봉(`daily_fetch_rows`) DB 읽기 →
- N 결측 & `_entry_atr_rederive_allowed(t)` → `_rederive_entry_atr(t, pos, candles, 14)`.
- 돌파선 결측 → 매수일 이전 봉만으로 `breakout_line`(신호봉 = 매수일 직전 봉).
- `_hsb_closed` = 매수일 이후(포함) 봉 고가 최대 · `_bars_since_buy` = 그 봉 수 · `_channel_low` = 최근 10봉 저가 최소.
- `StrategyBase._apply_high_since_buy_from_candles` 위임(이미 읽은 봉 재사용).
- 봉이 모자라면 그 칸은 비우고 `[etf_trend_recover_skip]` WARNING.
- 같은 프로세스에서 매수 때 찍은 `_breakout_line`·`_entry_atr` 가 있으면 덮지 않는다.
- 매일 아침 prepare 와 함께 보유 상태가 갱신돼야 한다 — 이 메서드가 매 부팅(매일 `_boot`) 에 불리는지 확인하고, 아니면 prepare 끝에서 보유분 갱신을 같은 헬퍼로 부른다(복구 훅을 둘로 나누지 말고 헬퍼 하나를 두 자리가 부른다).

### 7.5 `on_position_closed(ticker)` — `_entry_atr`·`_breakout_line`·`_hsb_closed`·`_channel_low`·`_bars_since_buy` pop.

## 8. 기타 배선

- `_reset_daily_state` 는 멀티데이 상태를 지우지 않는다(`_bought_today` 등 일일 상태만, base 규약).
- `list_by_filter(exclude_etf_like=True)` 는 이 전략이 쓰지 않는다(ETF 를 산다) — ETF 허용 목록(G4) 에 `etf_trend` 등재.
- `get_scan_stats()`·`get_targets_status()` 등 다른 스윙 전략이 가진 공개 메서드 중 라우트·스케줄러가 부르는 것은 같은 모양으로 둔다.

## 9. 마이그레이션 — L13.

## 10. 테스트 (Red 먼저)

1. **동등성(핵심)**: 재현 모듈을 `importlib` 로 읽어(`_workspace/domain_consult/cycle391_etf_s0_remeasure.py`, 모듈 로드 부작용이 없는지 확인 — `main()` 은 부르지 않는다) 결정적 합성 시계열 여러 개(씨앗 고정, 추세·톱니·갭·급락 포함)에서
   - `build_ticker` 의 `e60`·`atr20`·`n14`·`hi_prev20`·`tv20`·`tvprev20` 와 leaf 값이 상대오차 1e-9 이내,
   - 모든 j 에서 donchian 분기 진입 판정(갭 포함)이 같고,
   - 진입한 모든 j 에서 `simulate_exit` 가 `sim_donchian(d, j)` 와 같은 `(k, why)` 와 `px`(1e-9).
2. leaf AST: import 는 표준 라이브러리만, `await`/`open(`/로깅 0.
3. 전략 단위: §5 순서 각 분기(창 안·밖 freezegun) · 섀도 켜짐 + 예산 0 → `[shadow_buy]` 기록 + NONE · 섀도 꺼짐 + 예산 0 → `no_budget` · 시장 유닛 unavailable/zero → NONE(shadow 모드에서도) · off 면 거르지 않음 · 묶음 보유 시 NONE · 갭 래치 · 붕괴 무래치 · 0주 → NONE.
4. `calc_buy_quantity`: 유닛 0 → 0(1주 폴백 없음, `_fallback_one_share` 미호출) · 유닛>0 → 관문 경유 + `_entry_atr` = N.
5. 청산: 선 1~4 경계(≤ / <) · 매수 당일 hard 만 · 본전 승격 다음 봉부터 · 장중 고가 무시.
6. `check_force_clear`: 돌파선 아래 1종목만 반환 · 위는 0 · D+1 은 0 · 가격 낡음/결측 → 0 + WARNING · 예외 → `[]`.
7. 복구: `recompute_held_atr` 가 돌파선·N·hsb·bars·채널을 봉에서 되살린다 · 매수 때 값은 덮지 않는다.
8. 명부: 8행 · 끝 행 값 · 파생 집합(`SWING_POLL_IDS`·`CLOSE_AT_1520_IDS`·`MARKET_UNIT_SCALE_IDS`) 에 etf_trend.
9. 통합(가능하면): `_force_clear_main_only` 를 etf_trend 보유 2종목(아래/위)로 돌려 `execute_sell` 1회.
10. 기존 열거 테스트 갱신(§1 표 마지막 행). 골든 G1 은 생성기로 재생성.

## 11. domain-expert 자문 반영 (`_workspace/domain_consult/cycle403_etf_trend_impl_review.md`) — 아래가 §2·§5·§7 을 덮는다

- **L7 보강** — §5 순서 5(갭) **앞**에 `open_price <= 0` → `NONE` 무래치 + `[etf_trend_skip] reason=open_unknown`. 시가 결측이면 갭·붕괴를 판정하지 않는다(안 그러면 갭 검사 없이 BUY).
- **L8 수정** — 묶음 캡 풀 = 이 전략의 `positions` ∪ `pending_buys` ∪ **이 전략의 당일 매도 종목**(`state.sold_today` 류). 재현 판정판 `dedup(exit_day_holds=True)` 와 맞춘다(그날 09:00 시가 손절된 종목도 그날 묶음 보유로 친다). 막는 방향.
- **복구 N(§7.4)** — 재도출은 게이트 `_entry_atr_rederive_allowed(t)` 는 그대로 쓰되, 값은 공통 `_rederive_entry_atr`(정수 절삭) 대신 **leaf `n14` 를 매수일 이전 봉(오름차순)으로 계산한 float** 로 넣는다(재시작 뒤에도 매수 때 N 과 1e-9 이내).
- **멀티데이 상태 매일 덮어쓰기** — `_hsb_closed`·`_bars_since_buy`·`_channel_low` 는 매 부팅(그리고 prepare 보유 갱신) **무조건 다시 계산해 덮는다**. 「덮지 않는다」 는 `_breakout_line`·`_entry_atr` 두 칸에만.
- **`_bars_since_buy` 는 KODEX 200(`069500`) 달력 기준** — 069500 일봉 중 날짜 ≥ 매수일인 봉 수. 그 종목 최신 봉 날짜 ≠ 069500 최신 봉 날짜면 `[etf_trend_recover_skip] reason=head_stale` WARNING(값은 069500 달력으로 센 것을 쓰고, `_hsb_closed`·`_channel_low` 는 종목이 가진 봉으로).
- **관측** — `[shadow_buy]`(level=돌파선) 와 함께 `[etf_trend_buy_eval]` INFO 에 `open_price`·`current_price`·`prev_close`·`line`·`N`·`m`·`cluster` 를 남긴다(1회/종목/일). 섀도 집계에서 S2 예산 기준 0주 판정은 오프라인 몫(코드 변경 없음).

## 12. cycle402 병합 반영 (브랜치를 main `e581d5d` 로 빨리감기함) — L9 를 덮는다

- cycle402 가 `Signal.TREND_EXIT` 와 훅 `StrategyBase.force_clear_signal(ticker)`(기본 `FORCE_CLEAR`) + `strategy_base.resolve_force_clear_signal` 을 들였고 `scheduler._force_clear_main_only` 가 그것을 쓴다.
- **L9 개정**: `EtfTrendStrategy.force_clear_signal(ticker) -> Signal.TREND_EXIT`(never-raise). TODO 주석은 두지 않는다. 체결 기록 사유가 「추세 이탈」 로 남는다. 나머지(하드·본전 STOP_LOSS, 트레일링·채널 TRAILING_STOP)는 그대로.
- 테스트: `resolve_force_clear_signal(etf_strategy, t) is Signal.TREND_EXIT` · 통합(가능하면) `_force_clear_main_only` 가 돌파선 아래 종목을 `TREND_EXIT` 로 `execute_sell`.
