# CLAUDE.md — src/engine/strategies/

> 이력: [`docs/history/src-engine-strategies-CLAUDE.history.md`](../../../docs/history/src-engine-strategies-CLAUDE.history.md)

`StrategyBase` 서브클래스 7개. 추상 메서드: `prepare` / `check_buy_signal` / `check_exit_signal` / `calc_buy_quantity`.

**이 문서는 코드 기본값만 적는다.** 활성 여부·비중·파라미터의 운영값은 DB `strategy_config` 가 정본이다 — 부팅 `_load_strategy_config` 가 DB 값으로 코드 값을 키별로 덮는다(`if key in strategy.config.params` — 코드에 없는 키는 버린다). 운영값 = `GET /api/strategies`, 운영 결정(멈춤·퇴출·터틀 전환) = `_workspace/00_URGENT_WORKLIST.md`.
- 코드 등록 기본값(`scheduler.py` `__init__`)은 momentum 만 `enabled=True`·`weight=1.0`, 나머지 6전략은 `enabled=False`·`weight=0.0` 이다.
- 코드 기본값을 바꿀 때 운영 DB 값도 함께 바꾼다 — 그대로 두면 DB 값이 계속 이긴다.
- ⚠️ 새 키를 코드 배포 **전**에 SQL 로 넣었다면(승인된 선반영 포함 — 루트 `CLAUDE.md` 「자율 진행과 승인 빈도」) 배포 전까지 그 전략의 `params` 를 저장하지 않는다(`PUT /api/strategies/{id}/params` · AI 자문 적용). 메모리에는 그 키가 없어서 `save_params` 가 메모리 dict 전체로 `params` JSONB 를 덮으면 선반영 값이 사라진다. 배포 전 PUT 으로 새 키를 넣으면 `unknown_key` 422 다.

## 전략 카탈로그

각주 ①~⑦ 은 표의 해당 행이 가리키는 게이트다. ⑧·⑨ 는 **7 전략 전부**에 걸리는 공통 청산·매수 차단이라 행마다 적지 않는다.

| ID | 파일 | 핵심 동작 | 손절·청산 | tradable_boards |
|----|------|----------|----------|-----------------|
| `momentum` | `momentum.py` | 전일종가 대비 +29%(`buy_threshold`) 돌파 순간만(상한가 30% 제외). 각주 ④ | −7.5% / 익일: 시가 갭 ≥ +10%(`gap_up_threshold`) 면 트레일링 −2%, 미만이면 09:00 KRX 시장가 익일청산(`scheduler._execute_next_day_clear`) | `("krx_open","main")` — `krx_open` 은 보드 표에 없어 실효 MAIN |
| `volatility_breakout` | `volatility_breakout.py` | 보드별 시가 + 전일 Range × 보드별 K 돌파. `_targets[ticker].boards[board]`·`_open_confirmed[ticker]`·`_prev_price[ticker]` 가 `{board: ...}` dict. 각주 ②③④ | 보드별 손절 `stop_loss_{board}` → 없으면 `stop_loss_rate`(−3%) (`_get_stop_loss_for_board(params, board)` + `_resolve_active_board()`). **15:20 KRX 메인 일괄 청산**(OVERNIGHT 거부) | **MAIN 단독** / `k_value_krx_main`. `k_value_nxt_pre`·`k_value_nxt_post`·`stop_loss_pre_nxt` 는 DB 호환 보존만(미적용) |
| `long_tail_volatility` | `long_tail_volatility.py` | VB 방식 + 전일대비 `min_prdy_rate`(5%)↑. `_limit_up_reached` set 으로 모드 관리. **`_cooldown_until` 2영업일 재진입 쿨다운** — `on_position_closed` 가 **당일 모드 손절 종목만** 등록한다(`was_limit_up` 은 discard 전 판정 — 상한가 익일보유의 재진입 보존). `reentry_cooldown_days=2` 는 `PARAM_RANGES` 미등록·일일 리셋 금지. 각주 ②③④⑤⑦ | 당일 모드 `intraday_stop_loss`(−3%) / 상한가 모드 `overnight_stop_loss`(−5%) + 익일 갭 ≥ `gap_up_threshold` 면 트레일링, **미달·시가 미수신·`nxt_tradable=False` 는 09:00 KRX 시장가 청산**(NXT 프리 즉시 체결 아님). **15:20 상한가 미도달 일괄 청산** — 상한가 모드는 15:20 가격 확인(각주 ⑦) 뒤 보존 + POST_NXT 손절 모니터링. `_next_day_clear_pending` 가드 | **PRE_NXT + MAIN + POST_NXT** — 연속 상한가 익일 청산 + 야간 매수 |
| `donchian_swing` | `donchian_swing.py` | 코스피200∪코스닥150(`list_by_filter(is_kospi200=True, is_kosdaq150=True)`) → 시총·거래대금 컷 → 일봉(`min_required=63`) → 20일 신고가 + 60일 EMA 우상향 + 거래대금 20일 평균 1.5×. 부분봉 가드(`candles[0]==기준일` 이면 [1] 부터). 09:05~09:30 매수, 갭 +3%↑ 스킵, 1회만. 터틀 opt-in(`sizing_mode="turtle"`, 기본 `position_ratio`) = `compute_unit_qty_guarded` + `_entry_atr` 원자 스탬프. 각주 ④ | ① 하드손절 — 스탬프 랏 `buy − stop_atr(2.0)×entry_atr`(고점이 `buy + breakeven_promote_atr(1.5)×entry_atr` 에 닿으면 매수가로 승격, tighten-only) + `−9%` backstop / 미스탬프 −7% → ② 시간청산(`breakout_fail_n_days`, 아래 절) → ③ 10일 저가 채널 이탈(`channel_exit_period=10`, `TRAILING_STOP`) → ④ ATR(14)×2 샹들리에. 재시작 재도출 = 「자금관리」 ATR 손절 게이트. 15:20 강제청산 없음 — 멀티데이(DB positions 영속) | MAIN |
| `bull_flag_breakout` | `bull_flag_breakout.py` | `list_by_filter`(전체 상장, 시총 ≥ 100억 + 거래대금 ≥ 15억, ETF/ETN 제외, `max_scan_stocks=4000`) → 일봉(`min_required=35`) → **폴**(3~10영업일 누적 +15%↑, 음봉 ≤ 45%) + **플래그**(2~10영업일, 조정 ≤ 폴 폭 50%, 거래량 < 폴 평균 × 60%). 09:05~13:00 **`flag_high` 돌파 순간** + 당일 거래량 ≥ `flag_avg_volume × 2`. `_bought_today` 1회 + `_cooldown_until` 3영업일(`on_position_closed` 가 달력일 근사(+5)로 등록 → CTCA0903R `add_business_days` 로 정확 3영업일, 청산 유형 무구분, 일일 리셋 금지 AST). 각주 ①④ | −5% / **`flag_low` 이탈 → STOP_LOSS** / **측정된 이동 도달 → TRAILING_STOP**(타겟 `flag_high + (pole_high − pole_start)`, 전량) / `high_since_buy − ATR×2` 트레일링 / 시간 청산 = 매수 뒤 달력일 > `max_hold_days`(5) + 2 | MAIN |
| `vcp_breakout` | `vcp_breakout.py` | **미네르비니식 VCP**. 전체 상장(`is_kospi200/is_kosdaq150=None`) → 시총 ≥ 100억 + 거래대금 ≥ 10억 + `max_scan_stocks=4000` → 일봉(깊이 = 「임계」 VCP) → **추세 필터**(50/150/200 EMA 정렬 + 장기 EMA 1개월 우상향 — 실효 장기선은 읽은 봉 수가 정한다) → **베이스**(25~75영업일, 깊이 ≤ 30%) → **pullback 점진 수축**(ATR ZigZag `min_swing_atr_mult=1.0`, 2~4회, 폭 감소, 마지막 ≤ 12%) → **거래량 수축**(마지막 5일 평균 < 베이스 직전 20일 평균 × 70%). 09:05~14:30 **`base_high` 돌파 순간** + 거래량 ≥ 20일 평균 × 1.5. `_bought_today` + `_cooldown_until` 7영업일(BFB 와 같은 2단계 산정). 각주 ①④⑥ | −7% / **`base_low` 이탈 → STOP_LOSS** / `high_since_buy − ATR×2` 트레일링 / **50일 EMA 이탈 → TRAILING_STOP**. 시간·15:20 청산 없음 — 멀티데이 | MAIN |
| `kojiro` | `kojiro.py` | **고지로 대순환 스윙**(EMA 5/20/40). 전체 상장(`max_scan_stocks=4000`) → 시총/거래대금 컷 → 일봉 100봉(`min_required=80`, EMA40 seed 잔여 < 2%) → **ATR/종가 밴드 1.0~6.0%**(비협상) → 스테이지 판별(EMA 동가 None 제외) → **strict entry** = 스테이지1 + 최근 5영업일 6→1 전환(`stage1_freshness=5`) + EMA 3선 우상향 + 전일종가 > EMA5. **점수 랭킹** `0.4×(MACD3 3봉기울기/3/종가) + 0.3×(띠폭/직전5봉평균 − 1) + 0.3×6→1신선도`(후보풀 min-max, 지표 = `kojiro_indicators.py` Wilder ATR `ewm(1/20)`) → `get_scanned_tickers()` score DESC — **정렬만, 자격·청산 무변경**(`rank_w_*` 는 `PARAM_RANGES` 제외). 관측(행위 0) = `src/engine/CLAUDE.md` `kojiro_band_observe.py` 절. 09:05~09:30 매수(**갭업 ≥5% / 갭다운 ≤−4% / 현재가<시가 스킵**), 1회만. 각주 ④ | **−8% backstop(ATR 독립) → 2ATR tighten-only floor(`_stop_floor`) → 스테이지3 진입 TRAILING_STOP(익일 아침, precompute `_held_stage3`) → 2.5ATR 샹들리에**. 브레이크이븐 `breakeven_promote_atr`(기본 0 = 비활성, `PARAM_RANGES` 미편입) — `high_since_buy ≥ buy + mult×ATR`(live `_effective_atr`)이면 `eff = max(eff, buy)` → `_stop_floor` 래칫 영속. `_position_stop_price` = be_line 포함 **4선 max** read-only 미러(`_stop_floor` 무변조 = 커플링 불변식). 🔴 **샹들리에 2.5 를 조이지 않는다** — RR 이 훼손된다(fat-tail 은 트레일링 몫, 자문 `kojiro_exit_loss_review.md`). 시간·15:20 청산 없음 — `_MULTIDAY_STRATEGIES` + `check_force_clear()==[]`. 공유 순차 폴루프 `_SWING_POLL_STRATEGIES=("donchian_swing","kojiro")`(double-buy 차단) | MAIN |

- `exchange` 는 7전략 모두 코드 기본 `KRX`(선택지 `KRX`·`NXT` — `SOR` 은 폐기, 모의는 KRX 만). 시각별 거래소 결정 = `src/engine/CLAUDE.md` `order_engine.py` 절.

**kojiro 리스크 통제**

- **Σ 오픈리스크 캡** `max_open_risk_pct=4.5`(예산 대비 %, 개수 캡과 **병존**). 포지션 리스크 = `qty×(매수가−실효손절선)`, 실효손절선 = `max(buy×(1+hard_stop_pct/100), _stop_floor 또는 buy−stop_atr×ATR, high_since_buy−trail_atr×ATR)` — 청산 세 가격선과 같은 산식·같은 ATR 리졸버로 매수 시도마다 다시 잰다(샹들리에가 ATR 팽창 시 내려가므로 최악 보장이 아니다). `stop ≥ buy_price` 는 **0 으로 계상**한다 — 음수면 확정 이익이 다른 종목 노출을 상쇄해 캡이 무력화된다. `_stop_floor` 는 읽기만 한다. ATR 결측 → 고정% 추정, 예외·예산 0·cap 0 → fail-open. 매수 게이트 전용 — 청산 미차단(AST).
- **섹터 캡** `max_positions_per_sector=2`(매수 게이트 전용·fail-open·청산 미차단). 동일섹터(`_kojiro_sector_key` KRX basket) 카운트에 **전일 보유 포함** — `_position_sectors` 영속 맵(stamp = recompute / BUY 반환 직전 / `on_position_closed` pop).
- **ATR 리졸버 `_effective_atr(ticker)`** = `_candidates` live 우선 → `_position_atr` 영속 폴백(stamp 3지점 = recompute / BUY 직전 / `on_position_closed` pop). 손절·리스크캡이 **같은 리졸버**를 쓴다 — `_candidates` 단독이면 후보에서 빠진 보유 종목이 `atr=0` 으로 2ATR 손절을 건너뛴다.
- ⚠️ `_position_sectors`·`_position_atr` 는 밤을 넘겨야 하므로 kojiro 는 `_reset_daily_state` 를 override 하지 않는다.
- **`max_units_per_stock=2`/`max_units_total=10` 은 소비처 0건 = 미강제**(`param_catalog` 「미사용」) — 리스크 한도로 오인하지 않는다(피라미딩·조기진입(스테이지6) 코드가 없어 1포지션=1유닛).
- `recompute_held_atr`(boot/저녁 훅, enrich Wilder ATR, fail-open)는 같은 일봉으로 `high_since_buy` 도 복구한다(`StrategyBase._apply_high_since_buy_from_candles`). 자리는 ATR/stage 블록 **앞**이다 — 봉 부족(`len(usable) < 80`)으로 그 블록이 `continue` 해도 고점 복구는 살아야 한다(없으면 샹들리에 기준점이 매일 아침 매수가로 리셋).

**각주 ① BFB·VCP 매수 게이트** — 거래량 컷 소스 = `tick_volume` 실측 단일(미관측 `None`·읽기 예외 = **fail-closed** + `[bfb|vcp_vol_gate_no_data]` WARNING). **충족 래치** — retention 완주(BFB)/edge-crossing(VCP) 뒤 거래량 미달·미관측이면 `[bfb|vcp_latch_armed]` 로 무장하고 후퇴에도 유지한다. 해제선 = **자기 §2 손절선**(`flag_low`/`base_low`, `reason=stop_line`) + 레벨 박제(`level_moved`). 재평가는 돌파선 이상 틱에서만, 통과 시 매수 `[bfb|vcp_vol_gate_pass] ... latch_age_sec=N`. **추격 상한** `max_breakout_extension_pct` = BFB **5.0** / VCP **7.5**(리터럴 — `PARAM_RANGES` 미편입, `current_price` 단독 판정·`daily_high` 금지) + 부팅 관찰 `[extension_cap_invariant]`. 래치·cap 은 날짜 키 자기 리셋. `_scan_stats` 6키 = `vol_gate_pass/reject_ext/no_data`·`latch_armed_count`·`breakout_seen/retreat_count`. 셋업 병합 = 「자금관리」 `_effective_setup` 항목. 자문 `_workspace/domain_consult/cycle228_vol_gate_latch.md` · 명세 `_workspace/red/cycle228_gate_latch_spec.md`.

**각주 ② VB·LTV 09:00 직후 진입 보류 `open_entry_hold_secs`(기본 90)** — KST `[09:00:00, 09:01:30)` 동안 **신규 매수 신호만** 내지 않는다(청산류 무접촉).
- 판정은 **시간창 단독**이다 — `tradable_boards` 는 09:00:00~09:00:30 에 세션 트래커 30초 주기 탓에 `pre_nxt` 로 남는다. LTV 08:00~09:00 프리장 매수는 창 밖.
- 자리 = **돌파 발사점**(계좌 SOFT 게이트 뒤). 보류 중에도 `_prev_price` baseline 을 갱신한다(얼리면 해제 뒤 첫 틱이 거짓 돌파).
- **fail-open** — 키 부재·`None`·`""`·파싱 실패(`inf`/`nan` 포함) = 0 = OFF. `[0, 600]` 클램프의 `except` 는 **bare `Exception`** 이다 — 좁히면 `1e400` 의 `OverflowError` 가 WS 재연결 폭주를 부른다.
- 관측 = `[open_entry_hold_config]`(1회/(전략, 값)/일 — 장중 PUT 롤백 확인 채널, `source` = 값 동등성 추론) + `[open_entry_hold_blocked]`(**would_buy 정본**, 1회/(ticker, 전략)/일). 두 cap 은 **별개 인스턴스**다(공유하면 config 1행이 그날 blocked 표본을 지운다). 관측은 peek→로그→mark · 예외 흡수이고 행위는 관측 밖이다. release 마커 없음 — 사후 평가는 `trade_history` 조인. ⚠️ 계좌 SOFT 게이트 활성일엔 LTV 카나리아 0행(LTV 는 게이트가 첫 문장).
- `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-262-1). 롤백 = `PUT {"open_entry_hold_secs": 0}` **즉시**(SQL 은 재시작에서만).
- 가드 `test_cycle262_open_entry_hold.py` · `test_cycle262_ast_open_entry_hold.py`. 명세 `_workspace/00_leader_trading_rules.md` §5 · 자문 `_workspace/consult/2026-09-06_open_entry_hold.md`.

**각주 ③ VB·LTV `main` 목표가 기준가 = KRX REST 단일 출처** — `board=="main"` 기준가는 **KRX REST `stck_oprc`(`J`)** 뿐이다.
- 좁은 목 `on_open_price_confirmed(ticker, open_price, board="main", *, source="ws")` — 신뢰 목록 `("rest",)`, 기본값 `"ws"` 라 WS 확정 경로(스케줄러 1차 폴링·전략 인라인)는 조용히 거부된다.
- REST 확보 = leaf `src/engine/open_price_rest.py`(일정 = `src/engine/CLAUDE.md` 모듈 맵). 프린트 안 된 종목은 그 시점 매수 불가(유계 재시도가 못 회수하면 그날 안 산다). 09:05:00 뒤엔 `owns_board()` False → 스케줄러 2차 REST 폴백이 백스톱.
- **킬스위치 `open_price_scope_mode`**(각 전략 `DEFAULT_PARAMS`, 상호 import 금지) — 기본 `"enforce"`, `"off"` 만 롤백(대소문자·공백 무시 정확 일치, 그 외 전부 enforce). `PARAM_RANGES`/`INT_PARAMS` 편입 금지. 롤백 PUT **즉시** — 이미 REST 로 확정된 목표가는 되돌아오지 않는다.
- `pre_nxt`/`post_nxt` 보드는 스코프 밖(LTV 프리장·야간 매수 무접촉). 마커 `[main_rest_basis_config/round/confirmed/unresolved]`. 가드 `test_cycle272_main_rest_basis.py` · `test_cycle272_open_price_rest_leaf.py` · `test_cycle272_ast_main_rest_basis.py`. 명세 `_workspace/00_leader_trading_rules.md` §5 · 자문 `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`.

**각주 ④ AI 매수평가(LLM) — 주문 접수 시점 shadow** — **전략 파일에는 훅이 없다.** `order_engine.execute_buy` 가 `place_order` 성공 직후(매핑 등록 끝, PENDING INSERT 앞) `llm_buy_gate.observe_order(...)` 로 접수한다. 래치·cap·마커·영속(`llm_buy_evaluations`)·모델 = `src/engine/CLAUDE.md` 모듈 맵 `llm_buy_gate.py`.
- 설정 = **`DEFAULT_PARAMS` 4키**(7전략 전부): `llm_gate_mode="shadow"` · `llm_gate_min_score=70`(`would_block` 반사실용) · `llm_gate_daily_call_cap=20` · `llm_gate_timeout_secs=20`. 4키 전부 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST 런타임 + 소스 이중).
- **키 부재** = `mode` **off** · `daily_call_cap` **0**(호출 안 함) · `min_score`/`timeout` 70/20 — 돈을 쓰는 기능이라 설정이 없으면 하지 않는다(각주 ③ 의 부재 = enforce 와 반대).
- **기록만 한다**(행위 변경 없음). `enforce` 는 미구현, `shadow` 외 값은 `off`. 킬스위치 = `PUT {"llm_gate_mode":"off"}` **즉시**(SQL 은 재시작 뒤).
- 채점 문맥 = `llm_features._STRATEGY_META`(7전략) + `snapshot_keys_for`. LTV `pre_nxt` 주문도 평가한다(`board_note` + `vol_ratio_time_norm=null`). `[llm_buy_score]` 의 `rationale` 은 60자 절단(`system_logs` 500자 컷 — 전문은 docker 로그), `latency_ms`(LLM 호출만) ≠ `verdict_lag_ms`(접수→판정 전체).
- 호출 = 재시도 0(`AsyncOpenAI(max_retries=0)`) · `score` 가 bool 이어도 `schema_error` · 모델 기본 `gpt-5.6-luna`(`openai_buy_gate_model` — 20:00 자문 `openai_recommend_model` 과 별도) · 키 `openai_api_key` 재사용 · temperature 미지정. 조회 `GET /api/llm-evaluations/{order_no}` · 회고 `.../retrospective`.
- 자문 `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`(enforce 설계는 사용자 결정) · `cycle276_order_time_llm_20260911.md` · 명세 `_workspace/red/cycle276_order_time_llm_eval_spec.md`.

**각주 ⑤ LTV `main` 보드 신규 매수 15:20 컷** — `board=="main"` 신규 매수는 `MAIN_BUY_CUTOFF_KST = time(15, 20)` 이후 내지 않는다. **모듈 상수**다 — `DEFAULT_PARAMS`/`PARAM_RANGES`/`INT_PARAMS` **편입 금지**(오버나이트 금지가 DB 토글로 뚫리면 안 된다).
- 이유 — `session._BOARD_SCHEDULE` MAIN 이 15:39:59 까지라, 컷이 없으면 15:20~15:30 시장가가 **접수되어** `_limit_up_reached` 미도달 오버나이트로 남는다(익일청산·갭가드·트레일링은 상한가 모드 전용). 15:30~15:40 은 종가 고정·다른 시장 가격이라 돌파 정보가 없다.
- 자리 = **발사점**(`return Signal.BUY` 직전, 각주 ② 블록 직후) — SOFT 게이트 첫 문장 · 보드 해소·`_prev_price` 갱신 뒤.
- **`board=="main"` 전용** — `pre_nxt`·`post_nxt`(15:40~19:50) 무접촉.
- 관측 `[ltv_main_buy_cutoff]`(would_buy 정본, `KstDailyEmitCap` 1회/ticker/일, never-raise). 킬스위치 없음 — 장중 롤백 = `PUT {"tradable_boards": ["pre_nxt","post_nxt"]}`(더 강한 안전측), 영구 = 1커밋 revert.

**각주 ⑥ VCP 돌파 관측 (cycle349, 관측 전용 — 매매 행위 0)** — 「그날 돌파 사건이 있었나」를 사후에 판정한다. 후보 집합·순서·매수 판정·`DEFAULT_PARAMS` 무변경.
- **오전 prepare 만** — `_observe_breakout_distance(refs)` 는 실행 시각 ≤ `entry_end`(14:30)일 때만 기록한다(naive `datetime.now().time()` vs `_parse_time_hhmm(params["entry_end"])` — 창 게이트와 같은 시계). 창 밖 prepare 는 줄 0 · watch 무접촉. 미리보기(`as_of` > 오늘)는 시각과 무관하게 부르지 않는다(P3). 호출 2곳(정상 끝 · 유니버스 0종목 조기 반환)은 각자 `try`.
- **① `[vcp_breakout_distance]`** WARNING 후보당 1줄 `run= ticker= base_high= prev_close= dist_pct= box_high_date= box_high_ago= base_low= base_len=`. `dist_pct = (base_high − prev_close)/prev_close×100`(`prev_close ≤ 0` → `na`). `box_high_*` = `candles[:base_len]` 에서 고가가 `base_high` 인 최근 봉(⚠️ `box_high_ago` 는 1부터, cycle347 `high_age` 는 0부터). cap 키 `(ticker, base_high, prev_close)` 하루 1회(인스턴스 `KstDailyEmitCap`).
- **run 요약 `[vcp_breakout_distance_summary]`** WARNING `run= n= median_pct= within5= over10= tickers=`(후보 0 → `tickers=-`, `within5` = `dist_pct ≤ 5.0`, `over10` = `> 10.0`) = **run 별 후보 목록의 정본**(퍼널 스냅샷은 ≈09:35 한 장뿐). 같은 KST 날짜 **직전** 요약과 같으면 생략한다(직전 1개만 비교 — A→B→A 는 세 줄). 비교 키 `_breakout_summary_last = (kst_date, content_key)` 는 로그 **뒤**에 기록.
- **③ 틱 관측** — 오전 prepare 끝(조기 반환 포함)이 watch `_breakout_watch = {date, run_at, tickers: {t: {base_high, max, ticks, first_cross_at, first_tick_at, last_tick_at}}}` 를 그 시점 `_candidates` 로 **통째로 교체**한다. `check_buy_signal` **두 번째 문장**(첫 = 계좌 SOFT 게이트) `_observe_breakout_tick(ticker, current_price)` 가 09:05~14:30(양 끝 포함) 틱의 최고가·틱 수·최초 돌파 시각(`current_price >= base_high`)·첫/마지막 틱 시각만 적는다. watch 밖 상태는 무접촉이고 반환값이 없다. 매수 게이트들 앞이라 쿨다운·당일 매수 종목·돌파선 위 틱도 관측한다.
- **하루 요약** — 순수 읽기 `breakout_event_summary(target_date)` → metrics `"vcp_breakout_events"` + `[vcp_breakout_events]` WARNING(수집·`final` = `src/engine/CLAUDE.md` `log_metrics_collector.py` 항목).
  - `status` = `ok` · `no_watch`(오늘인데 watch 없음 = 「모른다」이지 「돌파 0」이 아니다) · `not_retained`(지난 날짜 — 정본은 그날 `daily_log_reports.metrics`) · `error`.
  - `crossed` = `max >= base_high` 인 수(동률도 돌파). `observed` = 창 안 틱 ≥ 1 인 종목 수이지 창 전체가 아니다(덮은 구간 = `per_ticker[t]` 의 `first_tick_at`/`last_tick_at`).
  - `partial` = `run_at > entry_start`(원인 불문). 후보 0 인 날(`candidates=0`)은 `partial` 을 읽지 않는다(5분 재준비가 watch 를 계속 교체한 흔적). 창 중간 재준비에서 후보가 처음 생긴 날과 창 안 재기동은 진짜 `partial` 이다.
- ⚠️ **한계** — (a) 틱은 `risk.on_tick` 이 VCP `check_buy_signal` 을 부를 때만 보인다 — 보유·주문중·당일매도(`is_ticker_blocked_for_buy`)·자금 가드·SOFT 게이트·구독 해제로 막힌 틱은 없다(창 시작부터 막히면 `unobserved_tickers`, 장중에 막히기 시작하면 `observed` 에 포함된 채 그 뒤 고가가 빠진 거짓 음성 — `last_tick_at` 으로 읽는다) (b) 14:30 뒤 재기동이면 그날 요약은 `no_watch`(① 줄은 남는다) (c) 창 안 재기동은 이전 관측을 버린다(`partial=1`, `run_at` = 마지막 교체) (d) prepare 도중 예외면 watch 는 직전 값 유지.
- 예외 경계 — 틱 훅·요약은 본체 전체 `try`, ① 헬퍼는 종목 계산·요약 줄만 자기 `try`(나머지는 호출부) — prepare 는 관측이 없을 때와 같은 상태로 끝난다. `_candidates` 엔트리에 키를 더하지 않는다(UI `get_targets_status` 누출 방지) · KIS·DB·`await` 추가 0. 명세 `_workspace/red/cycle349_vcp_observe_spec.md` · 회귀 `test_cycle349_vcp_breakout_observe.py`(골든 `fixtures/cycle349_golden.json`) · `test_cycle349_vcp_breakout_events_metrics.py`.

**각주 ⑦ LTV 15:20 상한가 유지 확인 (`limit_up_close_hold_mode`, cycle352)** — 상한가 모드 당일 종목이 15:20 가격 기준 `limit_up_threshold` 미달이면 그날 청산한다(B안, 자문 `_workspace/domain_consult/cycle352_ltv_limit_up_trailing.md`).
- **행위** — `check_force_clear()`(15:20)가 상한가 모드 ∧ 당일 매수(`not pos.is_next_day`) ∧ `limit_up_close_hold_mode="enforce"`(기본) 종목 중 **15:20 전일대비 등락률 < `limit_up_threshold`** 를 그날 강제청산 목록에 넣는다. 이상이면 보존한다(그 뒤 = 카탈로그 LTV 행).
- **가격** = `scanner.ticker_prices[t]["current_price"]` / `scanner.ticker_prev_close[t]`(모드 전환 판정과 같은 출처). `>=` 면 보유. 판정 불가(가격 없음·0 이하·전일종가 없음·예외)는 **보유**(hold_unknown, fail-open — 잠긴 상한가는 체결이 드물어 마지막 가격이 상한가다).
- **킬스위치** `enforce`/`off`(`open_price_scope_mode` 와 같은 규약), `PARAM_RANGES`/`INT_PARAMS` 편입 금지. 롤백 `PUT /api/strategies/long_tail_volatility/params {"limit_up_close_hold_mode":"off"}` 즉시.
- **never-raise** — `scheduler._force_clear_main_only` 가 try 없이 부르므로 실패해도 현행 목록만 반환(당일 모드 15:20 청산 보존). `check_exit_signal`·`scheduler.py`·`risk.py` 무접촉.
- 마커 `[ltv_limit_up_close_config]`(1행/일, 보유 0 에도) · `[ltv_limit_up_close_decision]`(종목마다). 회귀 `test_cycle352_ltv_limit_up_close_hold.py`(T14 는 `test_long_tail_volatility.py` 소관) · `test_cycle352_ast_ltv_close_hold.py`(G1~G6, G3b) · `tests/integration/test_force_clear_1520.py`(I1·I2).

**각주 ⑧ 7 전략 공통 — 관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단 (cycle369)** — 전략 파일에는 코드가 없다. 창·판정·킬스위치(`status_exit_mode`·`status_buy_block_mode`)·마커 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절.
- **청산** — leaf `status_exit_watch.py` 가 보유(꺼진 전략 포함)를 REST `FHKST01010100` 으로 읽고, **09:00:30~15:28** 에 전용 플래그(`mang_issu_cls_code`·`short_over_yn`)가 `Y` 면 `execute_sell(t, Signal.STATUS_EXIT, sid)` 시장가. 종목상태 코드 51·59 폴백만이면 팔지 않고 경고만. **전략 예외 없음**(LTV 상한가 모드·kojiro 멀티데이도 판다). 같은 틱 다른 청산 신호와는 `_selling` 이 하나로 합치고 표기는 먼저 쏜 쪽.
- **당일 매수 차단** — 공통 게이트 `_account_soft_gate_blocked` **첫 문장**(AST J25)이 그날 장중 조회 해당 종목의 신규 매수를 막는다(지정 첫날 포함). 막는 순간 edge 기준가를 비운다 — VB·LTV 중첩 `_prev_price[t]` · momentum `_prev_prdy_rate[t]`(첫 문장 게이트인 LTV 는 차단 동안 기준가가 얼어, 안 비우면 해제 뒤 거짓 돌파). 🔴 BFB·VCP 평평한 `_prev_price` 는 건드리지 않는다(비우면 0 으로 읽혀 새 거짓 돌파).

**각주 ⑨ 7 전략 공통 — 신규 매수 멈춤 `buy_paused` (cycle384)** — 전략 파일에는 `DEFAULT_PARAMS["buy_paused"]=False` 한 줄뿐이고, AST 가 `DEFAULT_PARAMS` 를 가진 모든 전략 파일에 요구한다(`test_cycle384_ast_buy_paused.py` A12). 게이트·마커(`[buy_paused_config]`·`[buy_paused_skip]`) = `src/engine/CLAUDE.md` `strategy_base.py` 절.
- **행위** — `true` 면 **신규 매수 신호만** `Signal.NONE`. 청산·손절·트레일링·익일청산·15:20 강제청산·종목상태 청산·시간 청산은 그대로.
- 🔴 **신호 단계에서 막는다** — 전략 끄기·`weight=0`(보유 손절까지 멈춘다 — 루트 금기) · 수량 0 반환(900초 「투자금 부족」 오귀인) · `buy_disabled`(일일 손실 래치)로 대신하지 않는다.
- **자리** = 공통 게이트 **둘째 문장**(첫 문장 = 각주 ⑧). 첫 문장 게이트 전략(LTV·donchian·BFB·VCP·kojiro)은 멈춘 동안 신호 본문이 안 돌고, momentum·VB 는 돌파 순간에만 닿는다.
- **해제 첫 틱** — 막는 순간 각주 ⑧ 과 같은 edge 기준가와 진입 래치(BFB `_breakout_first_seen[t]` · BFB/VCP `_vol_latch[t]`)를 비운다(해제 뒤 거짓 돌파·낡은 래치 매수 방지). 🔴 BFB·VCP 평평한 `_prev_price` 와 donchian·kojiro `_bought_today` 는 건드리지 않는다.
- **값** — `is True` 일 때만 멈춘다. 부재·`False`·`"true"`·`1` 등은 멈추지 않는다(모양이 틀리면 WARNING), PUT 은 bool 이 아니면 422. `PUT {"params":{"buy_paused":true|false}}` **즉시**. `PARAM_RANGES`/`INT_PARAMS` 편입 금지 — AI 자문 적용 경로(수동·자동)가 거른다(AST A11).
- 🔴 **멈춰 둔 동안 이 키를 코드에서 지우지 않는다** — 키 없는 코드가 배포되면 `_load_strategy_config` 가 DB 의 `true` 를 버려 조용히 풀린다.
- 절차 = `_workspace/red/cycle384_buy_paused_spec.md` §11(켜기·확인) · §12(해제·롤백). 어느 전략이 멈췄는지는 운영 상태다(`GET /api/strategies`·워크리스트).

## 자금관리 — 사이징 방식 × 손절 기준 매트릭스

**핵심 명제**: `수량 = 예산 × risk_pct ÷ (진입가 − 손절가)`. 손절이 **고정 %** 면 명목 = `예산 × risk_pct/s` = 종목 무관 상수 = `position_ratio` 이므로 **고정% 손절 + 비율 사이징은 이미 리스크 균등**이다. ATR 유닛 사이징은 **손절도 ATR 기반일 때만** 리스크를 균등화한다 — 사이징만 바꾸면 정규화가 깨진다(**함정 #1**). ⇒ **터틀 전환은 하드손절 ATR화와 반드시 한 커밋에 묶는다.**

| 전략 | `sizing_mode` 코드 기본 | 하드손절 | 터틀 배선(코드) |
|---|---|---|---|
| `momentum` | (키 없음) | 고정 % | **제외** — `prepare` 빈 stub·일봉 0건이라 ATR 이 없다 |
| `volatility_breakout` | (키 없음) | 보드별 고정 % | **제외** — 15:20 전량 청산(보유 ≤1일)이라 유닛 정규화 실익이 낮다 |
| `long_tail_volatility` | (키 없음) | 당일 −3% / 상한가 모드 −5% | **보류** — 상한가 2모드 손절 ATR화 재설계 선행 |
| `donchian_swing` | `position_ratio` | 스탬프 시 `buy − 2.0×entry_atr`(+ 브레이크이븐) + `−9%` backstop / 미스탬프 −7% | 배선됨 · K=2.0(cycle242) |
| `kojiro` | `position_ratio` | `−8%` backstop → `2×ATR` tighten-only floor(`_stop_floor`) | 배선됨 — `_entry_atr` 미도입(live ATR + `_stop_floor` 단일 메커니즘) · K=2.0 |
| `vcp_breakout` | `position_ratio` | 스탬프 시 3단 밴드 / 미스탬프 −7% | 배선됨(하드손절 ATR화 동반) · K=2.0 |
| `bull_flag_breakout` | `position_ratio` | 스탬프 시 3단 밴드 / 미스탬프 −5% | 배선됨(하드손절 ATR화 동반) · K=2.0 |

- VB·LTV 제외 근거는 함정 #1 이지 데이터 부재가 아니다(`prepare` 가 이미 일봉을 읽어 ATR 은 추가 I/O 0 으로 나온다).
- 운영 DB `sizing_mode` 는 이 표와 다르다(`GET /api/strategies`).

**규약 (신규 전략 추가 시에도 적용)**

- **제한 축은 셋** — ① 개수 `max_positions` ② 명목 `Σ매수금액 ≤ total_investment` ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). 유닛 **개수는 ③의 프록시**일 뿐이다. ⚠️ **개수 캡을 리스크 캡으로 대체하지 않는다** — 저ATR 종목으로 포지션 수가 무한정 는다.
- **`max_positions` 는 걷어내지 않는다** — 계좌가 커지면 유일한 상관·운영 통제축이다(자문 `_workspace/domain_consult/kojiro_position_count_vs_unit_cap.md`). `position_ratio` 를 낮추면 개수 천장(`1/position_ratio`, 자본 무관)이 올라 저ATR 종목이 쌓인다(중소형 폭락일 상관=1 수렴). ③은 규모 불변(full 유닛 4.5개에서 물린다)이라, 더 담으려고 `max_open_risk_pct` 를 올리는 것은 **상관군 캡이 전제**다.
- **피라미딩(사다리 증량)은 코드가 없다**(설계 `_workspace/design/2026-09-24_three_stage_sizing_pyramiding.md`). 정해진 제약 = K 2.0 유지 · **1주 폴백 랏에는 사다리를 걸지 않는다**(설계안 D-2) · 사다리 위험 합계는 kojiro `max_open_risk_pct` 가 지킨다. ⚠️ **VCP/BFB 는 피라미딩 부적합**(VCP 수축 진입은 2N 손절이 과도하게 타이트, BFB 는 measured-move 목표 확정) — 그래서 `max_units_total`≡`max_positions` 가 영구히 성립하고 **개수 캡이 영구 load-bearing** 이다.
- **유닛화는 랏 미세화를 풀지 못한다** — 정수 절삭은 유닛식에도 있다. 랏이 1주 언저리인 원인은 `q` = 설계 랏 ÷ 그 전략이 사는 종목의 중앙 주가(중앙 명목 아님)이고 `q` 는 순자산에 정비례한다. 비중·자금을 둔 채 유닛만 도입하면 `floor(예산 × risk_pct ÷ ATR) = 0` 으로 **전면 무매매**다. 고칠 대상은 사이징이 아니라 전략 간 배분이다.
- **매수 수량은 `StrategyBase._apply_budget_limit()` 관문을 반드시 지난다**(AST A-GATE — 7전략 모든 `return`). 순서 **잔여 클램프 → K축 → `[oversized_fallback]` 관측 → ρ축 → `return`** 이 계약이다. 순서의 이유·헬퍼·마커·순수성(A-PURE·A-ATOMIC) = `src/engine/CLAUDE.md` `strategy_base.py` 절.
  - **잔여** = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`. 부족하면 **부분 매수**(잔여 < 1주 → 0). 비중 기준 0주면 `_fallback_one_share` 로 위임 — **이 분기 순서가 계약**.
  - **K축 `max_lot_units`(K=2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든 랏**(터틀 유닛·`position_ratio` 낙하·1주 폴백)을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고 0 이면 **매수하지 않는다**(`min` — 늘리지 않는다). 산출 = `turtle_sizing.compute_unit_qty(..., fraction=K)` 재사용(새 수식 금지), ATR = 터틀 분기와 같은 `_candidates[ticker]` read-only. ATR 결측·모호(`atr`/`atr14` 상이)·`risk_pct ≤ 0`·예외 = **fail-open**(현행 수량 + `[fallback_cap_skipped]`) — fail-closed 는 유령 키가 두 전략을 전 기간 체결 0건으로 만든 방향이다. 클램프 `[1.0, 20.0]`(하한 = 정상 터틀 랏이 캡에 안 걸리는 전제, 상한 = 롤백 다이얼).
    - ⚠️ 「K유닛 = 예산 2.0% 노출」은 `_entry_atr` 스탬프 랏(2×ATR 손절) 한정 — 폴백·낙하 랏은 미스탬프라 고정% 손절이고 실효 상한은 `cap_qty × price × |stop_loss_rate|` 다. `sizing_mode="turtle"` 이 아닌 전략은 범위 밖(함정 #1).
    - 롤백 = `max_lot_units = 20.0` — `PUT /api/strategies/{id}/params` **즉시**, SQL UPDATE 는 **다음 재시작에서만**(`_config_loaded` 프로세스당 1회, `_boot` 재호출 no-op). 보유 중 장중 재시작 금지(cycle232 D6)라 **장중은 PUT 뿐**. 당일 캡→0 으로 `_bought_today` 가 소진된 종목은 어느 수단으로도 **다음 세션부터만** 되살아난다(`cap_qty` 는 D-1 ATR 기반 일중 상수).
  - **ρ축 `max_lot_ratio_mult`(K_ρ=2.5, cycle245 — 관문을 지나는 모든 랏)** — `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // 현재가`, 1주도 못 사면 **매수하지 않는다**(줄이는 방향뿐). 사이즈드 터틀 랏·낙하 랏은 notional 상한 덕에 항등적으로 무접촉이라 **실효는 1주 폴백 랏뿐**이다. K축이 심사한 랏도 `min` 으로 후심사한다(cycle254 — 조기탈출은 `_lot_units_cap_governs` 판정 예외 `probe_error` 뿐).
    - `position_ratio` 결측·예산 0·초소액·판정 예외 = fail-open + `[ratio_cap_skipped]`. **키 부재 = 캡 OFF**(K축과 반대 — 매수를 막는 통제라 fail-closed 는 유령 키 재현 경로).
    - 키는 **7 전략 전부** `DEFAULT_PARAMS` 에 `2.5`(터틀 포함 — `sizing_mode` 를 되돌리면 ρ축이 받는다). 클램프 `[1.0, 20.0]` — **하한 1.0 이 「정상 비중 랏 무접촉」 전제**(미만이면 주 분기까지 잘려 전면 무매매). 롤백 K_ρ=20.0(반영 시점은 K축과 같다).
    - `PARAM_RANGES`/`INT_PARAMS`·AI 자문 자동 적용 경로 편입 금지. 가드 `tests/unit/ast/test_cycle245_ast_ratio_notional_cap.py` G-245-1(런타임 dict + 소스 리터럴) · G-245-6(전략 파일 glob 전수 — 키 존재 + 값 = `_MAX_LOT_RATIO_MULT_DEFAULT`) · G-245-7(전략 `calc_buy_quantity`·터틀 사이징에 `max_lot_ratio_mult` 토큰 0 — 캡 로직은 관문 안에만).
- **불변식 `position_ratio × max_positions ≤ 1.0`** — DEFAULT_PARAMS 는 AST(C-DEFAULT), AI 추천은 `_validate_recommendations` 가 강제. `max_positions` 는 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(리스크 정체성 상수).
- **ATR 손절 게이트 = `_entry_atr` 스탬프 존재** — `sizing_mode` 로 게이팅하지 않는다(DB 토글 하나로 기보유 손절 규약이 바뀌면 안 된다). 스탬프 값 = sizing 에 쓴 ATR(**커플링 불변식**). 터틀이 0 을 반환하는 모든 경로(변동성 floor / 잔여 부족 / `ticker=None` / 예외)는 **미스탬프** → % 손절.
  - **재시작 재도출은 지금 `sizing_mode="turtle"` 일 때만** — BFB·VCP `StrategyBase._entry_atr_rederive_allowed`, donchian `recompute_held_atr`(buy_date 이전 봉)의 같은 조건(구조 가드 `tests/unit/engine/strategies/test_cycle355_entry_atr_rederive_gate.py` G6). position_ratio 랏을 되살리면 고정% 손절이 ATR 손절 + % 받침선으로 넓어진다.
  - ⚠️ 랏별 사이징 기록이 없어 **보유 중 `sizing_mode` 를 바꾸면 기보유분도 새 설정의 손절을 탄다**(position_ratio→turtle 은 다음 아침 부팅부터, turtle→position_ratio 는 다음 재시작부터). 전환은 그 전략 보유 0 에서.
- **터틀 수량 ≤ 비중 수량** — `compute_unit_qty_guarded` notional 상한이 `position_ratio × 예산` 이라 전환은 **순수 축소**, 저ATR 수량 폭증은 구조적으로 불가. 임계 `atr_ratio = risk_pct ÷ position_ratio`(기본 2.5%).
- **3단 밴드 손절**(VCP/BFB) — `base_stop = min(buy − stop_atr×entry_atr, buy×(1+turtle_min_stop_pct/100))` 로 과도한 타이트화를 막고 상단은 `turtle_backstop_pct` 캡. ⚠️ VCP 진입 ATR 은 국소 최소다(`atr_ratio 1.5%` 면 `2ATR = −3%`) — `turtle_min_stop_pct`(VCP −5.0 / BFB −4.0)가 유일한 방어선이다.
- live-ATR breakeven 래치는 `entry_atr <= 0` 로 게이팅(두 tighten 메커니즘 공존 차단), 승격은 `max()` 로만.
- 터틀 키 **7종**(`sizing_mode`/`risk_pct`/`stop_atr`/`turtle_backstop_pct`/`min_vol_floor_pct`/`turtle_min_stop_pct`/**`max_lot_units`**)은 `PARAM_RANGES`/`INT_PARAMS` 미편입. 기계 가드는 `max_lot_units` 뿐(`tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py` G-242-1 = 런타임 dict + 소스 리터럴), 나머지 6종은 문서 규약.
- ⚠️ **BFB 는 익일 청산 전략이 아니다** — `_execute_next_day_clear` 대상 = `("momentum","long_tail_volatility","volatility_breakout")` · `_force_clear_main_only` 대상 = `("volatility_breakout","long_tail_volatility")` · BFB `check_force_clear()==[]`. 시간 청산까지 **실질 멀티데이**이고 `_MULTIDAY_STRATEGIES` 비멤버는 `is_next_day` **배지에만** 영향한다. 재시작 복구 = `_rederive_entry_atr`(매수일 *이전* 봉만, 부족 시 미스탬프, turtle 일 때만) + `recompute_high_since_buy`(`_apply_high_since_buy_from_candles` 위임, 복사 금지). **배선은 `boot_manager`**(DB positions 복구 뒤, `scheduler.py` 무접촉). 🔴 `_SWING_POLL_STRATEGIES` 에 BFB 를 넣지 않는다 — 매수 폴루프·구독 대상에도 쓰여 매수 행위가 바뀐다.
- **청산 파라미터는 `_position_setup` 영속 맵 + `_effective_setup` 리졸버 경유**(VCP·BFB) — `_candidates` 는 `prepare()` 마다 와이프되고 보유 종목은 후보 자격을 잃는 게 정상이라, 거기만 보면 **T+1 아침부터 매일** 청산이 죽는다(VCP §1.5 래치·**§2 `base_low`**·§3 트레일링·§4 `ema50` / BFB §1.5 래치·**§2 `flag_low`**·**§3 measured-move 전체**·§4 트레일링). 구조 레벨(`base_low`/`flag_low`/`pole_*`/`flag_high`)은 BUY 직전 stamp 후 **불변**·stamp 우선, 지표(`atr14`/`ema50`)는 boot 훅의 일봉으로 **매일 갱신**·live 우선(`ema50` 을 박제하면 이탈 청산이 늦어진다). 충돌 관측 `[setup_structure_conflict]`. BFB §3 은 `.get()` 방어 + **키 결손 시 미발화**(과잉 청산 금지). ⚠️ `_reset_daily_state` 에서 clear **금지**(AST 봉인). VCP 는 `recompute_high_since_buy` 의 기존 fetch 응답으로 `_rederive_entry_atr` 를 부른다(KIS 추가 0, 같은 turtle 게이트).
- **트레일링 기준점(`high_since_buy`) 영속은 전략 책임** — `risk.on_tick` 은 메모리만 올린다(hot path DB 쓰기 금지). 단일 진실원 `StrategyBase._apply_high_since_buy_from_candles`(계약 = `src/engine/CLAUDE.md` `strategy_base.py` 절, 복사본 금지). 신규 보유형 전략은 이미 fetch 한 일봉으로 부른다(KIS 추가 0). 없으면 `_boot()` 가 DB row 로 Position 을 만들 때 기준점이 매수가로 리셋된다.

### 시장 유닛 — 터틀 4전략 (cycle382)

장세에 따라 터틀 4전략(`kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout`)의 **신규 진입 설계 랏만** 줄인다. 🔴 **매크로 레짐과 다른 축이다** — 레짐 게이트가 아니라 전략 사이징이다. 헬퍼·마커 = [`src/engine/CLAUDE.md`](../CLAUDE.md) `strategy_base.py` 절 · 판정 leaf = 같은 문서 모듈 맵 `market_unit.py`.

- **장세** = KODEX 200(`069500`) 일봉 종가의 **직전 영업일 봉** — 60일선 위·상승 **1** · 위·하락 **0.75** · 아래·상승 **0.5** · 아래·하락 **0**(그날 신규 진입 없음). 상승 = 60일선 > 20봉 전 60일선. 동률은 약한 쪽. 배수·창 길이는 leaf `src/engine/market_unit.py` 한 곳의 상수이고 파라미터로 열지 않는다.
- **무접촉** = `total_investment`·잔여 클램프·K축·ρ축·kojiro 오픈리스크 캡·`cash_usage_ratio`·보유분·청산 규약. 🔴 예산 경로(`cash_usage_ratio`·`total_investment` 축소)로 대신하지 않는다 — 7전략 전부와 일일 손실 분모·정산 기준선·비중 하한선 검증이 함께 흔들리고, 매크로 자동 조정과 같은 손잡이라 두 효과를 가를 수 없다(자문 `_workspace/domain_consult/cycle376_market_unit.md` §7.4).
- **모드** `market_unit_mode ∈ off|shadow|enforce` — 네 전략 `DEFAULT_PARAMS` 에만 있다(기본 `"shadow"` = 계산·기록만, 수량 불변. 부재·오타 = `off`). VB·LTV·momentum 에는 키·헬퍼 호출이 없다(설계 랏이 1주 언저리 — 같은 자문 §4.4). 전략마다 `PUT {"params":{"market_unit_mode":"off"|"shadow"|"enforce"}}` 로 **즉시** 바뀐다(매 호출 읽는다). `PARAM_RANGES`/`INT_PARAMS`·AI 자문 자동 적용 경로 **편입 금지**(AST `test_cycle382_ast_market_unit.py` A03).
- **결측·stale·예외 = m=1**(현행) + WARNING(`[market_unit_unavailable]`·`[market_unit_error]`) — 장세 데이터 결손이 매수를 조용히 줄이면 안 된다.

| 전략 | `_MARKET_UNIT_ATR_KEY` | 신호 필터 자리 (`_market_unit_blocks_entry`) | 축소 매수의 스탬프 |
|---|---|---|---|
| `kojiro` | `"atr"` | `check_buy_signal` — `observe_gap(…, "pass", …)` 블록 뒤, `_bought_today.add` 앞 | 없음(`_position_atr` 을 신호 시점에 찍는다) |
| `donchian_swing` | `"atr"` | `check_buy_signal` — 추격 상한 `[donchian_extension_skip]` 블록 뒤, `_bought_today.add`·`_breakout_high` 스탬프 앞 | `_entry_atr`(터틀 경로) |
| `bull_flag_breakout` | `"atr14"` | `_evaluate_vol_gate` — 추격 상한 거부 블록 뒤, `latch_age_sec = 0` 앞 | `_entry_atr`(터틀 경로) |
| `vcp_breakout` | `"atr14"` | `_evaluate_vol_gate` — BFB 와 같은 자리 | `_entry_atr`(터틀 경로) |

- **자리가 계약이다** — 다른 매수 게이트를 전부 지난 뒤라 거르는 사유가 시장 유닛뿐이다. 필터는 `_bought_today`·`buy_signals`·래치·스탬프를 건드리지 않는다(PUT `off` 가 다음 평가부터 먹는다). BFB·VCP 는 필터가 `_prev_price` 갱신 뒤라 PUT `off` 뒤 첫 틱이 거짓 교차가 아니다. SOFT 게이트는 그대로 첫 문장.
- **축소일(`enforce` ∧ m<1)** — `calc_buy_quantity` 첫머리가 줄인 설계 랏만 관문에 넘긴다. 1주 폴백도, 터틀→`position_ratio` 낙하도 없다(원인 불문 — 낙하 랏은 미스탬프라 고정% 손절이고 명목이 줄인 유닛보다 커질 수 있다). m=1 인 날의 결손 낙하는 현행 그대로.
- **줄인 랏으로 못 사는 종목은 신호 단계에서 `Signal.NONE`** — 수량 0 을 흘리면 `order_engine` 의 「매수 수량 0 → 900s cooldown (투자금: …)」 으로 오귀인된다. 잔여 부족(`funds`)은 거르지 않는다(기존 자금 경로가 맞는 귀인).
- ⚠️ `enforce` ∧ m=0 인 날에도 donchian·kojiro 스윙 폴은 후보마다 `fetch_stock_detail` 을 부른 뒤 신호에서 거른다(`_bought_today` 를 안 써 09:05~09:30 매분 다시 평가).

## 공통 패턴

### funnel (깔때기)

- `prepare()` 단계별 통과 수 = `_scan_stats` → `get_scan_stats()` → `strategies.<id>.scan_stats` → 프론트 ScanMonitor.
- `_scan_stats` 키(모듈 함수 `_empty_scan_stats()` 시드) = **VB 9키**(`universe_candidates / universe_filtered / price_filtered / mcap_pass / trade_amount_pass / candle_fetch_ok / k_value_computed / final_prepared / last_run_at`) · **LTV** = VB 9키 + `consecutive_limit_pass` · **momentum** 은 `scanner.scan_filter_stats` 모듈 전역 7키(`universe_candidates / rate_pass / mcap_pass / trade_amount_pass / limit_up_excluded / final_prepared / last_run_at`)의 사본 · BFB 는 `min_trade_amount_failed`, VCP 는 `mcap_pass` 를 더 센다.
- `scan_stocks()` 는 등락률 30%+(상한가)를 명시 분기한다 — `limit_up_excluded` + 구독 후보 제거(`check_buy_signal` 30% 가드와 이중 안전망).
- 단계 수 = BFB·VCP·donchian·kojiro 각 **9**(`FUNNEL_STAGES`) · VB **9**(`VB_FUNNEL_STAGES`) · LTV **7**(`LTV_FUNNEL_STAGES`). **momentum 은 영구 제외**(`prepare()` 빈 stub — `_record_funnel_step` 호출 0건을 AST 가 강제, UI 「실시간 돌파 기반 — funnel 적재 미적용」).
- 기록 헬퍼(`_record_funnel_step`·`_record_funnel_pipeline_step`·`_reset_funnel_steps`) = `src/engine/CLAUDE.md` `strategy_base.py` 절. 전략은 `prepare()`·재시도마다 자기 STAGES 를 넘긴다. `survived` 의 문자열 원소는 `_resolve_ticker_name` 으로 `{ticker, name}` 이 된다(dict 원소는 그대로). `excluded` = `[{ticker, name, reason}]`(reason 은 수치 포함 — 「음봉 비율 35% > 30%」), `step_conditions` = UI 툴팁. DB 캡처 = 같은 문서 「funnel 스냅샷 캡처」 절.
- step1 = **「원천 유니버스 후보(필터 전)」**. `list_by_filter(return_stage_counts=True)` 가 `(filtered, {union_tickers, mcap_tickers, trade_tickers})` 를 돌려주고(미지정이면 list), donchian·BFB·VCP·kojiro 가 그것으로 단계 collapse 를 막는다.
- BFB `_detect_pole_and_flag_detailed(candles) -> (result, fail_stage, detail)` 이 `fail_stage`(`pole_return`/`pole_red_ratio`/`flag_retracement`/`volume_contraction`)와 수치를 낸다. `_detect_pole_and_flag` 은 result 만 돌려주는 thin wrapper.
- 휴장일 응답 필드 = `src/routes/CLAUDE.md` `/api/strategy-funnel` 행. funnel 은 **순수 관찰성** — `check_buy_signal`/`check_exit_signal` funnel hook 0건(AST).

### prepare 공통

- **기준일 인자 `prepare(self, *, as_of: date | None = None)`**(7전략 공통, 해석 = `StrategyBase._resolve_prepare_as_of`) — `None`/오늘 = 현행 그대로(부팅·07:59·5분 재준비 — 골든 `tests/unit/engine/strategies/fixtures/cycle364_prepare_golden.json`) · `> 오늘` = **미리보기**(`today_str = as_of` 라 오늘 봉이 「전일」, 기대 헤드 = `previous_trading_day(as_of)`, 21:00 저녁 캡처만) · `< 오늘` = `ValueError`. momentum 은 인자만 받는다. VB·LTV 는 PV-1 밖이다(VB 보유는 15:20 에 비고, LTV 상한가 보유가 읽는 `ticker_prev_close` 는 21:30 정산이 비운 뒤 다음 부팅이 채운다).
- 🔴 **PV-1 — 미리보기 준비는 보유 종목의 청산 입력을 바꾸지 않는다** (donchian·kojiro·BFB·VCP — 청산이 `_candidates` 보유 엔트리를 읽는 네 전략)
  - 와이프 = `self._candidates = {t: v for t, v in self._candidates.items() if t in keep}`(`keep = _preview_keep_tickers()` = 자기 보유 ∪ 자기 익일청산, 남긴 엔트리는 **같은 객체**). 종목 루프는 `skip = _preview_skip_tickers()`(자기 보유 ∪ 전 전략 보유·익일청산) 종목의 fetch 결과를 버린다 — `_candidates`·`ticker_prev_close`·kojiro `_held_stage3`·관측 원자료 어느 것도 쓰지 않는다.
  - 이유 — 바뀌면 야간 틱 하나로 청산이 나갈 수 있다(kojiro `_held_stage3` 는 가격 무관 `TRAILING_STOP`). 20:00 뒤에도 stale watcher 가 보유를 HIGH 로 재구독하므로 틱 부재는 보장이 아니다.
  - `_scanned_tickers` — donchian·BFB·VCP 는 이번 실행 후보만, kojiro 는 `ranked_final + held_only`(`held_only` = **자기** 보존 엔트리만).
  - 🔴 미리보기에서 `_held_stage3` 를 `as_of` 날짜로 찍지 않는다 — 스테이지3은 가격을 보지 않는 유일한 청산이다. 다음 날 판정은 부팅 `recompute_held_atr` 가 정본.
  - ⚠️ 비미리보기 준비(레거시 +600초·07:59·5분)는 PV-1 밖 — 전량 와이프한다(donchian 보유 트레일링이 매수 시점 ATR 로 떨어지는 경로가 남는다).
- **P3 — 미리보기는 관측 부수 로그를 내지 않는다** — kojiro `observe_band`·`observe_macd`·`observe_macd_stage6`(`bar` = 「D-1 완성봉」 계약, 일일 cap 소비) · VCP `_observe_breakout_distance`. funnel 기록과 VB 퀀트·RS/RSI 관찰은 미리보기의 산출물이라 남긴다. 가드 `test_cycle364_{prepare_as_of,preview_held_guard,preview_keep_own_skip_all}.py`.
- 6전략 일봉 = `get_recent_daily_normalized(ticker, days=N, min_required=M, expected_head=E)`(DB 우선 어댑터). **`min_required`**: VB 22 · LTV 22 · donchian **63**(lookback 61 = `long_ma` 60+1 — **절대 하향 금지**, silent 왜곡) · BFB 35 · VCP 100(깊이 모드 무관 — 「임계」 VCP) · kojiro 80(`KOJIRO_MIN_REQUIRED`). `None` 의존 금지.
- `expected_head` = 직전 영업일 — gather 전 `self._resolve_expected_daily_head()` 로 **1회** 구해 전 종목에 넘긴다(헤드가 더 오래된 종목은 KIS 폴백, `None` = 달력 판정 `DAILY_STALENESS_DAYS`). 넘기지 않는 호출부 = kojiro `recompute_held_atr` · `llm_buy_gate` — 그래서 헤드가 하루 밀린 날 kojiro 보유 종목의 부팅 재계산과 재준비는 다른 봉을 볼 수 있다(결함 아님). 계약 = `src/db/CLAUDE.md` `stock_master_daily.py` 절.
- donchian 신고가는 **어댑터 candles 단일 소스**(별도 DB 조회 금지 — 락 종목 신고가/EMA 혼재 차단). 수정주가 divergence 방어 = 어댑터 락 게이트(`src/db/CLAUDE.md`).
- **1단계 진입 차단** `scanner._is_master_blocked_for_entry` **11건** = master_raw 7(`trht_yn` 거래정지 · `sltr_yn` 정리매매 · `mang_issu_yn` 관리 · `ssts_hot_yn` 공매도과열 · `stange_runup_yn` 이상급등 · `mrkt_alrm_cls_code` 시장경고 02↑ · `invt_alrm_yn` 투자주의환기(KOSDAQ)) + FHKST raw 4(`mrkt_warn_cls_code` 02↑ · `short_over_yn` · `sltr_yn` · `temp_stop_yn`). 헬퍼 `scanner.apply_master_block_filter(tickers, *, protected_tickers)` + 6전략 wrapper `_apply_master_block_filter_in_prepare` + momentum `scan_stocks` 내부 hook. **보유 종목 절대 보호.**
- **`nxt_tradable=None`** — 유니버스 단계에서 NXT 필터를 걸지 않는다(NXT/KRX 분기는 주문 시점 `_strategy_exchange_async`).
- `stock_master` 0건이면 자동 재시도(cap 3회 + 30초, `[<전략>_prepare_retry]`) — VB·LTV·donchian·BFB·VCP·kojiro. 후보가 빈 경우의 5분 재준비 = `scheduler._reprepare_breakout_if_empty`(VB·LTV·BFB·VCP).
- **가격 필터는 6전략 공통** `StrategyBase._apply_price_filter_in_prepare`(kojiro 는 자체 override) — `system_config.get_price_filter` **단일 소스**, 비활성(min=0, max=0)이면 전체 통과, 보유 무조건 통과, `raw.bfdy_clpr` 결측 graceful. scanner `_apply_price_filter` 는 이중 안전망.
- VB 전용 관찰 2종(**배제 0**, 키 전부 `PARAM_RANGES` 미편입, 결측·보유 fail-open) — **퀀트 재무**(`_apply_quant_filter_in_prepare`, `quant_filter_enabled=False`/`quant_min_f_score=0`/`quant_max_mf_rank=0`, `quant_score.py` F-Score-7 + 마법공식) · **RS/RSI**(`_apply_rs_rsi_observe_in_prepare`, `rs_filter_enabled=False`/`rsi_filter_enabled=False`/`rsi_extreme_max=85`, `ta_indicators.rsi/relative_strength` + `get_recent_daily`(DESC→ASC), 지수 069500).
- VB 실패 돌파 조기청산 = `failed_breakout_exit_enabled=False`/`failed_breakout_buffer_pct=-0.5`/`failed_breakout_confirm_ticks=2`(`PARAM_RANGES` 미편입) — 손절 분기 뒤, 돌파선(`_targets` target_price) 아래 buffer% 로 confirm_ticks 연속 재이탈 시 `STOP_LOSS`(회복 시 리셋). `_failed_breakout_count` 는 transient(prepare clear + `on_position_closed` pop). **기본 off**, 롤아웃은 외부 MCP 백테스트 게이트.
- momentum 익일 청산 로그 **1회/ticker/일**(`_next_day_clear_logged_today` + `reset_next_day_clear_logged_today()` + `_reset_daily_state` 동행) — 시장가 거부 뒤 매초 폭주 차단.
- VB/LTV/donchian/BFB/VCP `prev_idx` — `candles[0].stck_bsop_date == today_str`(= 기준일)이면 `candles[1]` 이 전일.
- 0종목 확정 시 `ERROR` 로그 + `system_logs`. prepare 는 **매수 진입 전** 단계라 청산 hot path 와 무관하다.

### 유니버스

- VB/LTV/BFB `_scan_universe` = `stock_master.list_by_filter(min_market_cap, min_trade_amount, exclude_tickers, nxt_tradable)` **DB 단일 조회**(KIS 0건). 시총(`raw.hts_avls`)·거래대금(`raw.acml_tr_pbmn`) **전일 확정치** 기준 — 당일 `acml_vol` 금지(boot 시점 0 + 오후 편중). 6자리 ticker 검증은 호출자 책임, `list_by_filter()` 예외 → 빈 list + `_scan_stats["universe_candidates"]=0`.
- **ETF/ETN 제외 = 증권그룹코드 판정, LIMIT 전** — 6전략의 모든 `list_by_filter(...)` 가 `exclude_etf_like=True`(AST G4)라 ETF 가 `max_scan_stocks` 칸을 차지하지 않는다. 루프는 `is_etf_like(row.get("raw"), name)` 로 한 번 더 본다(G3). 판정 = `src/engine/CLAUDE.md` 모듈 맵 `etf_like.py`. momentum 은 `list_by_filter` 를 안 써 이름 폴백만 탄다. ⚠️ ETF 를 사는 새 전략은 G4(`tests/unit/ast/test_cycle380_ast_etf_like.py`) 허용 목록에 이유와 함께 올린다.
- **거래량순위 API(`FHPST01710000`) 금지** — AST `test_cycle108_ast_no_kis_volume_rank.py` + `test_cycle97_ast_no_volume_rank.py`. momentum 만 **등락률순위**(`FHPST01700000`, `src/api/condition.py::_fetch_fluctuation_rank`)를 쓴다 — 다른 TR 이다.
- VCP `list_by_filter(is_kospi200=None, is_kosdaq150=None)`(지수 무제약), donchian `is_kospi200=True, is_kosdaq150=True`. hardcoded ticker list 금지.

### 임계

- BFB 폴·플래그 = `pole_min_return=15.0` · `pole_max_red_ratio=0.45` · `flag_retracement_max=0.5` · `flag_volume_ratio=0.60`(거래량 수축 안전장치 — **절대 불변**, 급락 되돌림 오판 봉쇄).
- VCP pullback(`_check_pullback_sequence`) = **ATR threshold ZigZag**(`min_swing_atr_mult=1.0` 미만 변동 무시) + state machine(`undefined`/`up`/`down`, 마지막 미완성 swing 포함). `False` 일 때도 `last_pullback_pct` 를 **항상 기록**한다(미설정이면 화면에 「0.0%」 로 오인).

#### VCP — 추세 필터와 일봉 읽기 깊이

- 추세 필터 `ema_short=50` · `ema_mid=150` · `ema_long=200`(미너비니 원설계) · `last_pullback_max=0.12`. `effective_ema_long = min(ema_long, available_len - uptrend_days - 5)` 가드 + `_check_trend_filter(candles, effective_ema_long=)` 가 **읽은 봉 수만큼만** 장기선을 세우고, `ema_mid >= ema_long` 이면 중기선을 `max(ema_short+1, ema_long-10)` 으로 줄인다.
- **읽기 깊이 `daily_fetch_depth_mode`(cycle300)** — `"cap100"`(코드 기본) = 100봉 · `"full"` = `ema_long + base_max_days + 10`(기본 설정이면 285봉). 원설계 정렬을 쓰려면 `"full"` 이어야 한다(운영값 = `GET /api/strategies`). 실효 정렬:

    | 보유 영업일 | `effective_ema_long` | 실효 정렬 | 중기↔장기 간격 |
    |---|---|---|---|
    | 100 | 75 | 50/65/75 | **10 — 정배열이 동전던지기** |
    | 225 | 200 | 50/150/200 | 50 |

  - 전환·롤백 = `PUT /api/strategies/vcp_breakout/params {"daily_fetch_depth_mode":"full"|"cap100"}` **즉시**(SQL 은 재시작에서만 — 장중은 PUT 뿐). `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AI 야간 튜닝이 실효 EMA 를 뒤집으면 안 된다). 미지·결측·비문자열 = `"cap100"`.
  - `min_required` 는 두 모드 다 **100** — KIS 폴백이 호출당 100봉이라 올리면 DB 100~224봉 구간이 더 얕은 KIS 응답으로 바뀐다.
  - ⚠️ `cap100` 의 100봉은 KIS 한도가 아니라 `vcp_breakout.py` `KIS_DAILY_CANDLES_MAX = 100` 이다(KIS 100일은 **호출당** 한도 — `src/api/CLAUDE.md`). `get_recent_daily` 상한 `_MAX_DAILY_ROWS`=400 · 적재 깊이 225영업일.
  - 가드 `test_cycle300_daily_depth_switch.py`(G-300-1~9).

### 1주 폴백

- 비중 기준 0주면 관문이 `StrategyBase._fallback_one_share(current_price)` 로 위임한다. K축·ρ축 캡(0 이면 매수하지 않는다)의 실효 대상이 사실상 이 랏이고, 시장 유닛 축소일에는 터틀 4전략이 여기 닿지 않는다(「자금관리」).

## 멀티데이 보유 전략

`Position._MULTIDAY_STRATEGIES` — `is_next_day` 항상 False, OrderMonitor 「청산」 배지 미표시. **정본 = `strategy_base.py` 의 `frozenset({"donchian_swing", "vcp_breakout", "kojiro"})` 리터럴** — import 시점 동적 추가 **금지**(import-order 독립), `Position` 시그니처 변경 금지. 추가 시 `check_force_clear()==[]` 결합 **필수**(없으면 15:20 강제청산으로 멀티데이가 소멸).

## 안전 규칙

- **계좌 SOFT Σ상한 게이트 (cycle233 — 다크런치)** — 7전략 `check_buy_signal` 이 `StrategyBase._account_soft_gate_blocked(ticker)` 를 지난다(AST 전수 강제). **위치 이원화가 계약** — 폴/래치형 5전략(donchian/LTV/BFB/VCP/kojiro) = **첫 문장** / edge-crossing 2전략(momentum/VB) = **발사 직전**(`return Signal.BUY` 앞). 🔴 edge-crossing 전략은 최상단에 두지 않는다 — 차단 동안 `_prev_price`/`_prev_prdy_rate` baseline 이 얼어 해제 뒤 첫 틱이 거짓 돌파다(AST). 신규 매수만 막는다(청산류 무관 · fail-open = 판정 실패 → False · DB `account_risk_block_pct` 가 없으면 항상 False). 게이트 본문 순서 = ① 종목상태 당일 매수 차단(각주 ⑧, AST J25 — 다크런치 아님, 킬스위치 키가 없으면 `enforce`) ② `buy_paused`(각주 ⑨) ③ 계좌 SOFT 판정.
- **read-only 청산선 미러** — 소비 = `engine/position_exit_lines` → `GET /api/balance`. 래치 set·`_stop_floor`·로그 무변조. VCP/BFB 는 `_effective_setup(ticker, observe=False)` 경유 — 🔴 `observe=False` 필수(10초 폴링이 5분 watcher 의 `[setup_structure_conflict]` cap 을 선소비하면 D+1 귀인이 무너진다).
  - **`get_effective_stop_price(ticker)`**(cycle233 척도 병기) — 보유형 4전략(kojiro/donchian/VCP/BFB)이 check_exit 가격선들의 max 를 낸다(가격 무관 청산 — 시간·stage3·measured-move — 은 제외).
  - **`get_effective_target_price(ticker) -> (target, already_hit)`**(cycle342 — BFB 단독) — 측정 목표가 `flag_high + (pole_high − pole_start)` 를 stamp 폴백으로 낸다(손절 미러와 같은 경로). 🔴 `get_targets_status()` 로 읽지 않는다 — `_candidates` 순회라 후보 자격을 잃은 보유 종목이 빠져 잔고 화면이 간헐적으로 빈 칸이 되고, 남아 있어도 live 재검출 값이라 엔진 §3 과 갈린다. 키 결손·폭 ≤ 0 = **미발화(`None`)**(임의 기본값 익절 = 과잉 청산). 둘째 원소는 `_partial_exit` 래치 **읽기만**(이미 발화한 목표를 「안 닿았다」로 읽지 않게). 회귀 `test_cycle342_bfb_target_mirror.py`.
- **VB·momentum 매수 컷 15:20 (`BUY_CUTOFF_KST` 모듈 상수)** — 15:20~15:30 장후 동시호가는 시장가가 접수돼 VB 매수가 체결되면 오버나잇이 확정된다. 15:30 랜덤엔드 종가 틱은 허위 edge-crossing(+29% = 잠금 실패 마감 표본)을 만든다 — momentum 컷의 근거다. `check_buy_signal` **최상단·상태 무갱신·KST 명시**(naive 금지). **DB override 불가 — `DEFAULT_PARAMS`/`PARAM_RANGES` 편입 금지**. 관측 `[vb_buy_cutoff]`/`[momentum_buy_cutoff]` 1회/일. `[단일가매매]` msg1 변형은 `balance.py` 분류기가 `is_market_order_disallowed` 로 흡수한다(매도 step_down 폴백).
- **돌파 후보 구독 우선순위** — `scheduler._collect_breakout_tickers()` 가 VB/LTV/BFB/VCP 후보를 `subscribe_filtered_stocks(priority_groups=...)` 의 `breakout` 그룹(LOW + `bypass_limit=False`)에 넣는다. **BFB/VCP 는 `risk.on_tick` 이 유일한 매수 평가 경로**(폴링 루프 없음)라 구독이 없으면 매수 0건이다. 🔴 후보를 HIGH 로 메인에 몰지 않는다 — 과부하 → silent inactive.
- **VB `DEFAULT_TRADABLE_BOARDS` = ("main",) 유지** — PRE_NXT 복구 금지(NXT 갭상승 위험 + SK하이닉스 시가 결함), POST_NXT 추가 금지(OVERNIGHT 보유 결함). 바꿀 때는 DB `strategy_config.params.tradable_boards` 도 함께.
- **LTV `DEFAULT_TRADABLE_BOARDS` = ("pre_nxt", "main", "post_nxt")** — 사용자 운영 의도(연속 상한가 익일 청산 + 야간 매수).
- **`tradable_boards` 는 매수 진입 전용**(7전략 공통 — 청산류는 보드 가드 없이 항상 작동, 유일한 예외 = NXT 프리장 청산 평가 보류). 상세 = `src/engine/CLAUDE.md` 「risk.py」 절.
- **VB 익일 청산 안전망** — `_execute_next_day_clear` 대상(시세 미수신·시장가 거부·재시작 race 회복).
- **donchian `_swing_rest_poll_loop` 제거 금지** — 09:30~15:20 60s 주기로 보유+스캔 합집합을 폴링해 `ticker_prices` 를 갱신하고 보유 손절 평가에 쓴다(WS stale 보강).
- 매수 신호는 반드시 **「돌파 순간」** 감지다(이전 틱 < 기준가 AND 현재 틱 ≥ 기준가).

## donchian·BFB·VCP 개별 파라미터 규약

### BFB `breakout_retention_minutes`

- 기본 3분. 첫 돌파 감지 → `_breakout_first_seen[ticker]=now` + NONE, 경과 후 BUY. 가격 후퇴 시 pop, `_reset_daily_state()` 에서 clear. `retention_minutes=0` 이면 즉시 BUY.
- `DEFAULT_PARAMS["breakout_retention_minutes"]=3` · `PARAM_RANGES` `(1,30)` · `INT_PARAMS` 등록.

### donchian `breakout_fail_n_days`

- 기본 5. `check_exit_signal` 에서 보유 N**영업일** ∧ 현재가 < `_breakout_high[ticker]` → STOP_LOSS(ATR 트레일링·하드 손절에 더한 분기).
- 보유일 = **영업일** — `_business_days_held()` 가 `_trading_days` 캐시(일봉 union, KIS 추가 0)로 세고, 캐시가 오늘을 못 담은 구간만 하루 더한다(주말 제외). 달력일로 세면 청산이 최대 2~3일 당겨진다.
- `_breakout_high` = 매수 신호 때 등록하는 donchian_high(0 이면 분기 미진입). 재시작 복구 `_rederive_breakout_high` 의 창 **`prior[1:period+1]`** 은 `prepare()` 의 `prior_high = max(highs[1:period+1])` 과 **같은 창**이어야 한다.
- **`PARAM_RANGES`/`INT_PARAMS` 제외**(청산 정체성 상수) — **수동 적용 라우트**(`routes/recommendations.py`)도 같은 정본으로 막는다.
- **돌파선 0 방어 3중**
  - (D-1) `prepare()` 가 `prior_high <= 0` 후보를 **거부**하고 `[donchian_zero_breakout_line]` WARNING. 탈락 사유 문자열은 정상 미달과 달라야 한다(funnel step5). 실제 표면은 「종가는 살고 고가만 결손」 row 뿐이다(완전 정규화 row 는 `prev_close <= 0` 가드가 먼저 잡는다).
  - (D-2) 재도출 진입 게이트는 **값 기준**(`_breakout_high[t] == 0` 이면 시도, 복구 전용 — 시간청산 게이트 `breakout_high > 0`·관측기와 같은 축) — 멤버십이면 0 이 「무장됨」으로 읽혀 **영구 미복구**다. ⚠️ 값 읽기는 `isinstance` 정규화 — 조건식의 `int()` 는 try 밖 예외가 되어 뒤 보유 종목의 `_channel_low`·`_entry_atr`·고점 보정을 통째로 잃는다.
  - (D-3) `src/db/stock_master_daily.py::_extract_raw` 가 `raw` 부재 row 를 그대로 돌려줄 때 `[daily_raw_missing]`(D-1 의 상류 — KIS 원본 키가 없어 `stck_hgpr` 가 0). kojiro·VCP·BFB 공유라 호출당 1행 + 1회/ticker/일 cap, 반환값 불변(`is` 동일성). 두 마커 동시 = 같은 사건(고가 결손), D-3 단독 = 다른 전략 쪽 일봉 열화.
- **관측**(무장 판정은 값 `> 0`)
  - `[held_recompute_skip]` — `recompute_held_atr` 게이트 `continue`(fetch 앞), cap `ticker`.
  - `[donchian_breakout_high_rederive_skip] reason=insufficient_prior|zero_high|no_candles|no_buy_date|no_position` — 미복구일 때만, cap `ticker|reason`. `no_candles|no_buy_date|no_position` 은 `days_held` 가 자라도 시간청산이 `breakout_high > 0` 에 막혀 **영구 미발화**하는 경로다. `no_candles` 는 5분 이어질 수 있다(`fetch_daily_candles` 는 빈 `output2` 에 `[]` 를 돌려주고 그 빈 결과도 5분 캐시에 박는다).
  - `[days_held_observe]` — **하루 1회** `days_held`·`calendar_days`·`days_ok`·`price_ok`. 자리 = `check_exit_signal` **최상단**(§1 하드손절 앞 — 안쪽이면 하드손절이 발화하는 날 못 닿고, 매도 거부로 포지션이 살면 영구 억제). cap 키 `ticker|armed`/`ticker|disarmed`(장중 재시작 직후 `breakout_high=0` 스냅샷이 종일 박제되지 않게). 실패 = `[days_held_observe_failed]` debug.
- **청산 로그 cap** — `[donchian_breakeven_promote]`·`도치안 시간 기반 청산` 각 **1회/ticker/일**(`_emit_breakeven_promote`/`_emit_time_exit` — `promoted_stop != base_stop` 이 매 틱 참이다). 🔴 **cap 은 로그에만 — 행위는 cap 밖**: `base_stop = promoted_stop` 과 `return Signal.STOP_LOSS` 는 매 틱 수행한다(신호까지 삼키면 매도 거부 뒤 재시도가 끊겨 포지션이 남는다).
  - donchian cap 7개 = 각자 별개 `KstDailyEmitCap`(날짜 자기 리셋), peek→로그→mark, 예외 흡수 + debug, 서식 byte 동일. cap 없는 동류 = `도치안 스윙 손절`·`[donchian_turtle_stop]`·`[donchian_turtle_backstop]`·`[donchian_channel_exit]`·`도치안 스윙 트레일링`.
  - ⚠️ 시간청산 로그 첫 타임스탬프가 09:00 이전이면 프리장 게이트 이상이다(donchian 은 `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 밖).
- **관측기 자기 실패** = `src/engine/observer_trace.trace_observer_failure(marker, ticker, cap, dest_logger=logger)` 로만(`observer_failed` = D+1 grep 축). `logger.debug` 단독 금지 — `_DbLogHandler`(INFO 컷)를 못 넘어 무음과 구별되지 않는다.

### donchian `max_breakout_extension_pct`

- 기본 **4.0%**. `check_buy_signal` 갭 스킵 *후*, BUY 확정 *전*. `daily_high = max(stck_hgpr, high_price, current_price, open_price)`, `ext_pct = (daily_high - donchian_high)/donchian_high*100 > max_ext` 이면 NONE(추격 금지).
- 불변식 **`max_breakout_extension_pct ≥ gap_skip_threshold`**(4.0≥3.0) 필수 — 후보 = 「전일 종가 > donchian_high(어제 제외 20일 신고가)」라 extension 하한이 이미 양수다(0.5% 같은 값은 상시 차단). `PARAM_RANGES` 편입 금지. 바꿀 때 `strategy_config.params` 동반 UPDATE. `gap_skip_threshold`(3.0, 시가 갭)와 별개(당일 고가 추격 상한).

### donchian 박스 수축 필터 재도입 금지

- `box_contraction_period`·`max_box_volatility_pct` 를 **다시 넣지 않는다** — 「20일 신고가 돌파」와 「초압축 횡보 요구」는 교집합이 공집합이라 후보가 상시 0 이 된다(자문 `_workspace/domain_consult/cycle_donchian_box_contraction.md`). 페이크 돌파 방어는 **청산 규칙**(ATR×2 트레일링 / −7% / `breakout_fail_n_days` / `max_breakout_extension_pct`)이 맡는다.

### PARAM_RANGES 편입 목록

- 진입 품질 키 = VCP `base_depth_pct(0.10,0.50)` / `volume_contraction_ratio(0.30,1.00)` / `breakout_volume_mult(1.0,5.0)`(BFB 공용) / `last_pullback_max(0.03,0.15)` + BFB `breakout_retention_minutes(1,30)`(`INT_PARAMS` 동행).
- **편입 금지** = `breakout_fail_n_days` · `max_breakout_extension_pct` · `box_contraction_period` · `max_box_volatility_pct` · `atr_trail_mult`(donchian·VCP·BFB 공유) · `max_positions` · `market_unit_mode`(AST A03). 나머지는 각 자리에 있다 — 터틀 7종·`max_lot_ratio_mult`(「자금관리」) · 각주 ②③④⑦⑨ 의 키 · `daily_fetch_depth_mode`(「임계」 VCP) · 장중 킬스위치 2키(아래).
- 정본 = `recommendation_engine.PARAM_RANGES`/`INT_PARAMS`, **`INT_PARAMS` ⊆ `PARAM_RANGES`** 유지.

## 새 전략 추가

1. 이 디렉토리에 `StrategyBase` 서브클래스(`prepare(self, *, as_of=None)`/`check_buy_signal`/`check_exit_signal`/`calc_buy_quantity`).
2. `scheduler.py` `__init__` 에 `registry.register()` — `scheduler.py` 는 라인 상한 때문에 승인 대상(루트 `CLAUDE.md` 「자율 진행과 승인 빈도」).
3. 필요하면 `scanner.py` 에 스캔 함수(8영역 — 승인 대상).
4. 이 문서 표(파일명 열 포함) + `_workspace/00_leader_trading_rules.md` 명세.
5. 배선 의무:
   - `check_buy_signal` 에 계좌 SOFT 게이트 1줄(「안전 규칙」 위치 계약) + `tests/unit/ast/test_cycle233_ast_account_risk.py` `GATE_FIRST_FILES`/`GATE_PRE_BUY_FILES` 에 파일 추가.
   - `calc_buy_quantity` 의 모든 `return` 이 `_apply_budget_limit` 경유 + `tests/unit/ast/test_budget_limit_ast.py` `STRATEGY_FILES` 에 파일 추가.
   - 보유형이면 `get_effective_stop_price` read-only 미러 + boot 훅에서 `StrategyBase._apply_high_since_buy_from_candles` 호출(없으면 다음 날 아침마다 트레일링 기준점이 매수가로 돌아간다 — 「자금관리」 트레일링 기준점 항목).
   - 7전략 공통 키(`buy_paused` · `max_lot_ratio_mult` · 장중 킬스위치 2키 · LLM 4키)를 같은 값으로 둔다 — `buy_paused`(A12)·`max_lot_ratio_mult`(G-245-6)는 AST glob 전수. 새 `DEFAULT_PARAMS` 키는 `param_catalog.py` 에도 등재(없으면 PUT `unknown_key` 422). 배포 전 DB 선반영 시 PUT 금지 = 문서 머리. `DEFAULT_PARAMS` 를 바꾸면 `tests/unit/ast/test_cycle278_ast_catalog_guards.py` `_DEFAULT_PARAMS_SHA` 재핀이 따른다.
   - `list_by_filter(...)` 에 `exclude_etf_like=True`(ETF 를 사면 G4 허용 목록).
   - 멀티데이면 `_MULTIDAY_STRATEGIES` 리터럴 + `check_force_clear()==[]`.

> **장중 킬스위치 두 키** — `order_exchange_clock_mode`(기본 `"enforce"`)·`after_market_exit_division`(기본 `"44"`)는 **7 전략 전부** `DEFAULT_PARAMS` 말미 + `param_catalog` 에 코드 상수(`order_engine._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT`·`_AFTER_EXIT_DIVISION_DEFAULT`)와 같은 값으로 있다(`params.get(key, DEFAULT)` 와 항등). 등재가 여는 것은 `PUT /api/strategies/{id}/params` **통로**뿐이다(없으면 `unknown_key` 422 라 장중에 끌 수단이 없다). `PARAM_RANGES`/`INT_PARAMS` 편입 금지 — AI 자문이 청산 수단을 끄는 스위치를 뒤집으면 안 된다. 사고 중 조작 순서·허용값·롤백 = `_workspace/00_leader_trading_rules.md` 「거래소 라우팅」 절 + `src/engine/CLAUDE.md` `order_engine.py` 절.
