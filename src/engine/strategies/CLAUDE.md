# CLAUDE.md — src/engine/strategies/

`StrategyBase` 서브클래스 7개 (kojiro 2026-07 다크런치). 추상 메서드: `prepare` / `check_buy_signal` / `check_exit_signal` / `calc_buy_quantity`.

## 전략 카탈로그

> ✅ **BFB·VCP 매수 게이트 개방 (사이클 228, 2026-08-28 게이트 전환 완료 — P0-1 종결).**
> 이력: 유령 키 `ticker_prices["acml_vol"]`(대입부 0)로 두 전략이 전 기간 체결 0건이었다
> (2026-08-25 확정) → 사이클 227 이 배관(handler `fields[13]` → `on_tick(*, acml_vol=)` →
> `tick_volume.py`)과 would_pass 관측을 깔았고(Stage 0), 이틀 실측 **0/5**(관측/임계
> 8%→70% 시각순 상승)가 "돌파 순간 1회 심사 = 시계 읽기" 역선택을 확증 → 사이클 228 이
> 게이트를 전환했다.
>
> **현행 게이트 (사이클 228)**: 거래량 컷 소스 = `tick_volume` 실측 단일(미관측 None =
> fail-closed + `[bfb|vcp_vol_gate_no_data]` WARNING, 읽기 예외도 no_data 흡수). **충족
> 래치** — retention 완주(BFB)/edge-crossing(VCP) 후 거래량 미달·미관측 시 무장
> `[bfb|vcp_latch_armed]`, 후퇴에도 유지, 해제선 = **전략 자신의 §2 손절선**
> (flag_low/base_low, `reason=stop_line`) + 레벨 박제(`level_moved`), 재평가는 돌파선
> 이상 틱에서만, 통과 시 매수 `[bfb|vcp_vol_gate_pass] ... latch_age_sec=N`. **추격 상한**
> `max_breakout_extension_pct` = BFB **5.0** / VCP **7.5**(리터럴 — PARAM_RANGES 미편입,
> `current_price` 단독 판정·`daily_high` 금지) + 도출 관계 부팅 관찰
> `[extension_cap_invariant]`. 래치·cap 은 날짜 키 자기 리셋(scheduler 훅 미의존).
> `_scan_stats` 6키 = `vol_gate_pass/reject_ext/no_data`·`latch_armed_count`·
> `breakout_seen/retreat_count`(cap 무관 총량). ⚠️ **cycle227 관측 마커
> `[*_vol_gate_observe]` 는 은퇴** — 같은 would_pass 의 매매 귀결이 "안 샀다→샀다" 로
> 반전되므로 2026-08-28 이전 로그와 이후 로그를 같은 grep 으로 합산하지 마라.
> **228-B**: `_effective_setup` 이 구조 레벨(flag_low/pole_* / base_low)은 **stamp 우선**,
> 지표(atr14/ema50)는 live 우선으로 병합(P1 계약 복원) + `[setup_structure_conflict]` 관측.
> 자문 = `_workspace/domain_consult/cycle228_vol_gate_latch.md` · 명세 = `_workspace/red/cycle228_gate_latch_spec.md`.

> ⏸️ **VB·LTV 09:00 직후 진입 보류 `open_entry_hold_secs` (cycle262, 2026-09-06) — 지혈이며 근본 시정이 아니다.**
> KRX 개장 후 기본 **90초**(창 = KST `[09:00:00, 09:01:30)`, 하한 포함·상한 배타) 동안
> **신규 매수 신호만** 내지 않는다 — 청산·손절·트레일링·익일청산·15:20 강제청산은 무접촉.
> 근거 = 목표가의 기준 시가가 KRX 09:00 시가가 아니라 통합 채널 `H0UNCNT0` `fields[7]`
> (**세션 시가** — 프리장 체결이 있었으면 프리장 시가)이고, 09:00~09:01:30 코호트가
> "체결가 ≥ KRX시가+offset" 을 **20/20 전부 위반**(이후 53/93, Fisher p=6.4e-5).
> ⚠️ 오염된 `[7]` 은 **일-스코프 상수**라 90초 뒤에도 값이 그대로다 — **근본 시정**은
> `[7]` 에 `[24] OPRC_HOUR` 스코프 필터(`src/realtime/**` = **8영역**, 별도 승인 + 자문).
> **보드 무관 — 시간창 단독 판정**(`tradable_boards` 분기 금지: 09:00:00~09:00:30 은 세션
> 트래커 30초 주기 탓에 보드가 `pre_nxt` 로 잡힐 수 있는 stale 캐시 구간이다). LTV 의
> 08:00~09:00 진짜 프리장 매수는 **창 밖 = 무접촉**. **판정 자리 = 돌파 발사점**(계좌 SOFT
> 게이트 뒤) — 최상단 금지(보류 중 `_prev_price` baseline 동결 → 해제 후 거짓 돌파, cycle233
> C233-F1 + would_buy 증거 소실). **보류 중에도 baseline 갱신은 계속된다.**
> **fail-open 이 계약** — 키 부재·`None`·`""`·파싱 실패(`inf`/`nan` 포함)는 전부 0 = OFF =
> 현행 행위, 읽는 쪽 `[0, 600]` 클램프(읽기 `except` 는 **bare `Exception`**: `1e400` 은
> 유효 JSON 이라 `int(inf)` → `OverflowError` 가 `check_buy_signal` 을 뚫고
> `risk.on_tick` → `handler.py` re-raise → WS 재연결 폭주로 이어진다).
> 관측 = `[open_entry_hold_config]`(적용값 카나리아, 1회/**(전략, 값)**/일 — 값-민감 cap 이
> 장중 PUT 롤백 확인 채널이다. `source` 는 **출처가 아니라 값 동등성 추론**. ⚠️ 계좌 SOFT
> 게이트 활성일에는 **LTV 카나리아가 0행** — LTV 는 `GATE_FIRST_FILES` 라 게이트 If 가
> `check_buy_signal` 첫 문장이어야 하고(cycle233 M6, AST 봉인) 로그 emit 은 그 앞에 둘 수
> 없다. VB 는 게이트가 발사 직전이라 무영향. 후속 F-6) +
> `[open_entry_hold_blocked]`(**would_buy 정본**, 1회/(ticker,전략)/일). 두 emit 모두
> peek→로그→mark(cycle226 D-3) + bare `except Exception` 흡수 — **행위는 관측 밖**.
> `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(진입 정체성 상수, AST G-262-1).
> 롤백 = `PUT /api/strategies/{id}/params {"open_entry_hold_secs": 0}` **즉시** /
> `strategy_config` SQL UPDATE 는 **다음 재시작에서만**(cycle232 D6 → 장중 실효 수단은 PUT 뿐).
> 자문 §2.6 의 **세 번째(선택) 마커 `[open_entry_hold_release]`**("막고 나서 더 좋은 값에
> 샀나" 의 직접 측정)는 **이번 범위에서 미구현 = 후속 F-4** — 그때까지 그 판정은
> `trade_history` 조인으로만 복원되고 "못 샀다" vs "더 좋은 값에 샀다" 가 구분되지 않는다.
> 두 cap 은 **별개 인스턴스가 계약**(같은 슬롯을 다투면 config 1행이 그날의 blocked 표본을
> 통째로 침묵시킨다 — cycle236 '별개 cap 가드' / donchian OB-11 선례).
> 🕒 `[open_entry_hold_blocked]` 는 지금 **`system_logs` 에만** 남고 전략 INFO 는 실측상 최근
> 며칠분만 잔존한다 — **재검토 창(2주)이 닫히기 전에 purge 될 수 있다**(후속 F-1 = 일일 추출 적재).
> ⚠️ **DB 선반영 금지** — `_load_strategy_config`·`PUT /params` 둘 다 "코드에 이미 있는 키만
> 덮는" 오버레이라 **배포 전 PUT 은 무음 실패**하고 `params` JSONB 를 통째로 덮는다(cycle245 선례).
> 가드 = `tests/unit/engine/strategies/test_cycle262_open_entry_hold.py`(행위 104, C1~C12) ·
> `tests/unit/ast/test_cycle262_ast_open_entry_hold.py`(AST 28, G-262-1a~9).
> 명세 = `_workspace/00_leader_trading_rules.md` §5 · 자문 = `_workspace/consult/2026-09-06_open_entry_hold.md`.

> ✅ **VB·LTV `main` 목표가 기준가 = KRX REST 단일 출처 (cycle272, 2026-09-10 — 사용자 결정 D1).**
> `board=="main"` 목표가가 통합 채널 `H0UNCNT0` `fields[7]`(오염된 세션 시가)로 서던 것을
> 멈춘다 — 기준가는 이제 **KRX REST `stck_oprc`(`J`) 단일 출처**뿐이다. `on_open_price_confirmed(
> ticker, open_price, board="main", *, source="ws")` 가 좁은 목이고, `source` 기본값이
> 불신 `"ws"` 라 WS 3 호출부(스케줄러 1차 폴링·전략 인라인 확정)는 **한 글자도 안 바뀌고**
> 거부된다(`check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` byte 동일 = cycle264
> `_STRATEGY_PINS` 6개 불변). REST 확보는 신규 leaf `src/engine/open_price_rest.py` —
> 09:00:35 R1 부터 30초 간격 **19라운드**(마지막 **09:09:35**, cycle276 후속 A-2 — 종전 9회는
> 09:04:35 에 끝나고 첫 slow 가 09:09:35 여서 그 5분을 메우는 주체가 없었다) → 이후 5분 간격
> 15:20 까지(첫 slow 09:14:35). 09:05:00 이관 시각은 불변이다. 프린트
> 안 된 종목은 그 시점 매수 불가(유계 재시도가 회수, 못 하면 그날 안 산다). 09:05:00
> 이후는 `owns_board()` 가 False 로 떨어져 스케줄러의 기존 2차 REST 폴백이 백스톱.
> **킬스위치 `open_price_scope_mode`** — 각 전략의 `DEFAULT_PARAMS`(상호 import 금지) 키,
> 기본 `"enforce"`. `"off"` 만 롤백값(대소문자·공백 무시 정확 일치), 그 외 전부 enforce.
> `pre_nxt`/`post_nxt` 보드는 게이트 스코프 밖 — LTV 08:00~09:00 프리장·야간 매수 무접촉.
> `PARAM_RANGES`/`INT_PARAMS` 편입 금지. 롤백 = `PUT {"open_price_scope_mode":"off"}`
> **즉시**(그날 이미 REST 로 확정된 목표가는 안 되돌아온다 — 전진 방향으로만 듣는다).
> 8영역 접촉 0. 관측 마커 4종(`[main_rest_basis_config/round/confirmed/unresolved]`)은
> cycle264 마커와 별개. 가드 =
> `tests/unit/engine/strategies/test_cycle272_main_rest_basis.py` ·
> `tests/unit/engine/test_cycle272_open_price_rest_leaf.py` ·
> `tests/unit/ast/test_cycle272_ast_main_rest_basis.py`.
> 명세 = `_workspace/00_leader_trading_rules.md` §5 · 자문 =
> `_workspace/domain_consult/cycle272_rest_open_basis_20260910.md`.
> 🧪 **VB·LTV AI 매수평가 — 주문 접수 시점 shadow (cycle274 → cycle276, 2026-09-11)**. **전략 파일에는 훅이 없다.**
> cycle274 가 `return Signal.BUY` 직전에 두었던 신호 시점 훅은 cycle276 에서 **전부 제거**됐다(그 함수
> `observe_signal` 은 이름조차 소스에 없다 — 현재 계약은 `llm_buy_gate.observe_order(...)` 뿐이다)(`check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` 세그먼트 sha 가 cycle272 값으로 복귀 —
> `tests/unit/ast/test_cycle264_scope_and_pins.py::_STRATEGY_PINS` 6핀), 평가는 `order_engine.execute_buy` 가
> **매수 주문을 실제로 발화한 직후**(두 매수 `place_order` 경로 각각의 매핑 등록 블록 끝, PENDING INSERT 앞)에서
> `llm_buy_gate.observe_order(...)` 로 접수된다 — 신호 10건 중 절반만 주문이 되던 cycle274 의 표본 괴리를 없애고
> 주문번호가 확정된 시점이라야 PK `(trade_date, account_no, ticker, order_no)` 가 성립하기 때문이다(사용자 지시
> 09-11). 전략에 남는 것은 **`DEFAULT_PARAMS` 4키뿐**이며 그것이 설정 표면이자 킬스위치다(VB·LTV 각각):
> `llm_gate_mode="shadow"` · `llm_gate_min_score=70`(`would_block` 반사실용) · `llm_gate_daily_call_cap=20` ·
> `llm_gate_timeout_secs=20`. 훅 자체는 전략 무관이지만 `order_engine` 이 `strategy.config.params` 를 읽어
> 넘기므로 **4키가 없는 5전략(momentum·donchian·BFB·VCP·kojiro)은 `mode=off` 로 낙하** = `create_task` 0 · DB 0행
> (`[llm_gate_config]` 카나리아 1행만 남는다). **키 부재 의미가 셋으로 갈린다** — `mode` 부재 = **off**,
> `daily_call_cap` 부재 = **0**(호출 안 함), `min_score`/`timeout` 부재 = 70/20. 이유 = 돈을 쓰는 기능이라
> "설정 없으면 안 한다"(cycle245 `max_lot_ratio_mult` 부재=OFF 와 방향은 같되 이유가 다르고, cycle272
> `open_price_scope_mode` 부재=enforce 와는 **반대** — 그쪽은 오염 차단이 안전이라 fail-closed). 4키 전부
> `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST 이중 검사). 래치는 **주문번호/일**(cycle274 의 (전략,종목)/일 아님
> — 같은 종목을 하루 두 번 사면 두 번 평가한다) · 세마포어 2 · 재시도 0 · 일봉 캐시 `(ticker, KST date)` 상한 400 ·
> 당일 봉 폐기 · 출력 검증은 **클램프 금지**(범위 밖·NaN/inf·bool 은 `schema_error`). 마커 5종 =
> `[llm_gate_config]`(1회/(전략,값)/일, off 롤백 확인용 카나리아 — off-return **앞**) · `[llm_buy_score]`
> (주문당 1행, `order_no`·`score`·`would_block`·**`post_order_drift_bp`**(cycle274 `slip_bp` 개명 + 부호 의미 반대 =
> **합산 금지**)·`verdict_lag_ms`·`latency_ms`·`rationale` 60자 — `system_logs` 는 500자 컷이라 전문은 docker 로그) ·
> `[llm_buy_score_failed] reason=timeout|api_error|parse_error|schema_error|payload_error|no_bars|no_key|
> disabled_model|truncated` + `finish=`(OpenAI `finish_reason` 원문, 호출 전 실패는 `-`) — `truncated` 는
> cycle276 후속 A-1: 추론 모델의 추론 토큰이 `max_completion_tokens`(2000)를 함께 먹어 `content=""` 로
> 오는 경우이고, "모델이 스키마를 벗어났다"(`schema_error`)와 **다른 사실**이다 · `[llm_gate_daily_cap]`(1회/전략/일) · **`[llm_eval_persist] order_no= result=ok|error`**
> (DB 기록 유무를 남기는 유일 채널 — `reason=empty_order_no`/`cap_exceeded` 는 평가를 시작하지 않은 주문). 평가는
> 성공·실패 **모두** `llm_buy_evaluations` 에 1행 남는다(migration 043 · 조회 `GET /api/llm-evaluations/{order_no}`
> · UI 거래기록 두 그리드의 "AI 자문" 버튼). LTV `pre_nxt` 주문 포함(`board_note` + `vol_ratio_time_norm=null`).
> 모델 `settings.openai_buy_gate_model`(기본 `gpt-5.6-luna`, 20:00 자문 모델과 분리), 키 `openai_api_key` 재사용,
> temperature 미지정. **행위 변경 0**(점수는 기록만 — `enforce` 미구현, `shadow` 외 모든 값은 `off` 낙하).
> 킬스위치 = `PUT /api/strategies/{id}/params {"llm_gate_mode":"off"}` **즉시**(SQL 은 재시작 후). 자문 =
> `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`(Q1~Q10 = enforce 설계는 사용자 결정) +
> `_workspace/domain_consult/cycle276_order_time_llm_20260911.md`, 명세 =
> `_workspace/red/cycle276_order_time_llm_eval_spec.md`.


> ✅ **LTV `main` 보드 신규 매수 15:20 컷 (cycle286 C2-a, 2026-09-12 — 사용자 지적 "15:30~16:00 에
> LTV 시각컷이 없다" 시정)**. `session._BOARD_SCHEDULE` 의 MAIN 구간은 09:00~15:39:59(15:20~15:30
> 종가단일가 + 15:30~15:40 청산 마진 포함)라서, 컷이 없으면 KRX 연속체결이 끝난 뒤인
> 15:20~15:39:59 에도 `board="main"` 으로 신규 매수가 나갈 수 있었다. 15:20~15:30(K4)은 시장가가
> **접수되는** 구간이라 그 체결은 `_limit_up_reached` 미도달 상태로 오버나이트에 남고(익일청산·
> 갭가드·트레일링 전부 상한가 모드 전용), 15:30~15:40(K5/N5)의 "돌파"는 KRX 종가 고정 또는 타 시장
> 가격이라 정보량이 없다. 모듈 상수 `MAIN_BUY_CUTOFF_KST = time(15, 20)`(`DEFAULT_PARAMS`/
> `PARAM_RANGES`/`INT_PARAMS` **편입 금지** — 오버나이트 금지는 DB 토글로 뚫려선 안 되는 규칙,
> cycle229 G-2 동일 논거). 판정 자리 = **발사점**(`return Signal.BUY` 직전, cycle262 hold 블록
> 직후) — 계좌 SOFT 게이트가 첫 문장이라(cycle233 M6) 최상단 불가, board 스코프 컷이라 보드 해소
> 뒤여야 하고, baseline(`_prev_price`) 갱신 뒤라야 동결이 없다. **`board=="main"` 전용** —
> `pre_nxt`(보드 08:00~09:00, NXT 프리마켓 실질 종료는 08:50 — `market_state` N1.end 로
> 별개 축, `session._BOARD_SCHEDULE` 의 보드 경계와 혼동 금지)·`post_nxt`(15:40~19:50
> 연속 상한가 익일청산 모드 진입)는 무접촉. 청산·강제청산·수량은 이 사이클에서 한 글자도 안 바뀐다(`check_exit_signal`/
> `calc_buy_quantity` 세그먼트 sha 불변 — 루트 CLAUDE.md "tradable_boards 는 매수 진입 전용").
> 관측 `[ltv_main_buy_cutoff]`(would_buy 정본, `KstDailyEmitCap` 1회/ticker/일, never-raise).
> 킬스위치 파라미터 없음(모듈 상수 = DB override 불가) — 장중 긴급 롤백은
> `PUT {"tradable_boards": ["pre_nxt","post_nxt"]}`(컷보다 더 강한 안전측), 영구 롤백은 1커밋
> revert. 자문 = cycle286 도메인 자문 §1.

| ID | 핵심 동작 | 손절·청산 | tradable_boards / exchange |
|----|----------|----------|---------------------------|
| `momentum` | 전일종가 +29% 돌파 (상한가 30% 제외, 돌파 순간만) | -7.5% / 익일 청산: 갭+10%↑ → 트레일링 -2% / 그 외 즉시 매도 | KRX_OPEN+MAIN / KRX·NXT·SOR (실전 SOR 권장, 모의는 KRX 강제) |
| `volatility_breakout` | 보드별 시가 + (전일Range × 보드별 K) 돌파. `_targets[ticker].boards[board]` 보드 분리 저장. `_open_confirmed[ticker]` / `_prev_price[ticker]` 도 `{board: ...}` dict | **보드별 손절**: `stop_loss_main` 우선 → 부재 시 `stop_loss_rate` top-level fallback. (`stop_loss_pre_nxt` 키는 DB 호환 보존, PRE_NXT 제거로 적용 안 됨). `_get_stop_loss_for_board(params, board)` 헬퍼 + `_resolve_active_board()` 활성 보드 조회. **15:20 KRX 메인 일괄 청산** (OVERNIGHT 거부) | **MAIN 단독** (사이클 26: PRE_NXT + POST_NXT 제거, KRX ONLY) / `k_value_krx_main` / `k_value_nxt_pre` (`k_value_nxt_post` 키 호환 보존만). **cycle262 — 09:00 직후 `open_entry_hold_secs`(기본 90초) 진입 보류**(위 배너, 보드 무관 시간창 단독). **cycle274 — LLM 매수 평가 shadow**(`llm_gate_mode="shadow"`, 위 배너, 행위 0) |
| `long_tail_volatility` | VB 방식 + 전일대비 `min_prdy_rate%`↑. `_limit_up_reached` set으로 모드 관리. **`_cooldown_until` 2영업일 재진입 쿨다운** (사이클 213 — `on_position_closed` 훅에서 `was_limit_up`(discard 전 판정) 이면 면제, **당일 모드 손절 종목만** 등록 = 상한가 익일보유 정상 재진입 보존. 테스 whipsaw 차단. `reentry_cooldown_days=2` PARAM_RANGES 미등록, 일일 리셋 금지) | 당일 모드 -3% / 상한가 모드 -5% + 익일 갭/트레일링. **15:20 상한가 미도달 일괄 청산** / 상한가 모드는 익일 NXT 프리 청산 + POST_NXT 손절 모니터링. `_next_day_clear_pending` 가드 | **PRE_NXT + MAIN + POST_NXT 3보드** (사이클 38, 2026-05-22 사용자 의도 복원 — 연속 상한가 익일 청산 + 야간 매수. 사이클 26 KRX ONLY 정책 폐기). 매수 진입 전용 — 보유 손절/Trailing/익일청산은 보드 가드 무관 항상 작동. **cycle262 — 09:00 직후 `open_entry_hold_secs`(기본 90초) 진입 보류**(위 배너). 08:00~09:00 프리장 매수는 창 밖 = 무접촉. **cycle286 C2-a — `main` 보드 신규 매수 15:20 컷**(위 배너, `post_nxt`/`pre_nxt` 무접촉). **cycle274 — LLM 매수 평가 shadow**(프리장 신호 포함, 위 배너, 행위 0) |
| `donchian_swing` | 코스피200+코스닥150 고정 유니버스 → 시총 컷 → 60일 일봉 → 20일 신고가 + 60일 EMA 우상향 + 거래대금 1.5×. `prepare` 부분봉 가드(`candles[0]==오늘`이면 [1] 부터). 09:05~09:30 매수, 갭 +3%↑ 스킵, 1회만. **Phase 2A-2 터틀 sizing opt-in**(`sizing_mode="turtle"`, 기본 `position_ratio`=byte 동일) — `compute_unit_qty_guarded`(변동성 floor 1%+notional 클램프)로 유닛 sizing + `_entry_atr` 원자 스탬프 | ATR(14)×2 Chandelier 트레일링 + **하드손절**: 터틀(entry_atr 스탬프) → `buy − stop_atr(2.0)×entry_atr` + `-9%` backstop(ATR독립 최후 방어) / position_ratio(미스탬프) → **-7% byte 동일**. entry_atr = `recompute_held_atr` 가 재시작 시 buy_date 이전 봉으로 재도출(loosen 차단). **시간·15:20 청산 없음** — 멀티데이 보유 (DB positions 영속화) | MAIN |
| `bull_flag_breakout` | `stock_master.list_by_filter` (**전체 상장 확대 유니버스**, 시총 ≥ 100억 + 거래대금 ≥ 15억, ETF/ETN 제외; 사이클 108 KIS 순위 API 폐기. **2026-08-08 확대** — BFB 는 이미 지수 무제약이라 실질 변경 = 거래대금 20억→15억(도메인 B2, 장중 돌파 추격 슬리피지 방어로 kojiro 10억까지 안 내림) + `max_scan_stocks` 100→4000(`refreshed_at DESC` 임의 절단 소멸) + `return_stage_counts=True` 합집합 노출 배선) → 35일 일봉(DB 우선 어댑터, 사이클 173 `min_required=35`) → **폴 자동 검출**(3~10영업일 누적 +15%↑(사이클 48), 음봉 ≤ 45%) + **플래그 자동 검출**(2~10영업일, 조정 폭 ≤ 폴 폭의 **50%**(사이클 211, 0.382→0.5), 거래량 < 폴 평균 × 60%(안전장치 불변)). 09:05~13:00 **`flag_high` 돌파 순간** + 당일 거래량 ≥ `flag_avg_volume × 2`. `_bought_today` 1회 가드 + `_cooldown_until[ticker]=date` 3영업일 쿨다운 (**사이클 191 배선** — `on_position_closed` 훅에서 즉시 달력일 근사(+5) 등록 후 CTCA0903R `add_business_days` 로 정확 3영업일 정정. 청산 유형 무구분, 일일 리셋 금지 AST 가드) | -5% 손절 / **`flag_low` 이탈 → STOP_LOSS** / **측정된 이동 도달 → TRAILING_STOP**(타겟가 `flag_high + (pole_high - pole_start)`, 1차 구현 전량 청산) / 잔여 `high_since_buy - ATR×2` 트레일링 / 5영업일 시간 청산 (캘린더일 +2 보정) | MAIN / KRX |
| `vcp_breakout` | **미네르비니식 VCP**. **전체 상장 확대 유니버스**(2026-08-08 확대 — 지수 KOSPI200∪KOSDAQ150 제약 제거 `is_kospi200/is_kosdaq150=None`, 미네르비니 셋업은 중소형 성장주 서식지라 지수 제약이 그 종목군을 배제해 왔음) → 시총 ≥ 100억(사용자 결정 — kojiro 500억보다 낮게, 소형주 포함) + 거래대금 ≥ 10억(이전 `min_trade_amount=0` 하드코딩 미사용 → 실사용) + `max_scan_stocks` 200→4000 → 일봉 100일(prepare cap, `vcp_breakout.py:162` — 원설계 220 미실현 사이클 173, backfill 도 120 사이클 196. 확대 종목 일봉은 daily-load(지수∪500억/10억)가 이미 커버, 비지수 자격 641종목 중 95.8% ≥100일 실측 → scanner 무변경) → **추세 필터**(50/60/120 EMA 정렬 + 장기 EMA 1개월 우상향, 사이클 48 — KIS 100일 한도 내 effective ema_long ≈75) → **베이스 자동 검출**(25~75영업일, 깊이 ≤ 30%) → **pullback 점진 수축** (사이클 49 ATR threshold ZigZag, `min_swing_atr_mult=0.5` 노이즈 필터 + 마지막 swing 미완성 포함, 2~4회, 직전 대비 폭 감소, 마지막 ≤ 12%) → **거래량 수축**(마지막 5일 평균 < 베이스 직전 20일 평균 × 70%). 09:05~14:30 **`base_high` 돌파 순간** + 당일 거래량 ≥ 20일 평균 × 1.5. `_bought_today` + `_cooldown_until` 7영업일 (**사이클 191 배선** — `on_position_closed` 신설, BFB 동일 2단계 영업일 산정). **`Position._MULTIDAY_STRATEGIES` 멤버** → `is_next_day` 항상 False | -7% 손절 / **`base_low` 이탈 → STOP_LOSS** / `high_since_buy - ATR×2` 트레일링 / **50일 EMA 이탈 → TRAILING_STOP**. **시간·15:20 청산 없음** — donchian 컨벤션, 멀티데이 보유 | MAIN / KRX |
| `kojiro` | **고지로 대순환 스윙 (2026-07 라이브, `enabled=True`·비중 **30%** — 2026-08-25 운영 DB 실측. 코드 등록 기본값은 `enabled=False`·`weight=0.0` 다크런치)**. EMA 5/20/40 대순환. 전체 상장(`is_kospi200/is_kosdaq150=None`, `max_scan_stocks≥3577`) → 시총/거래대금 컷 → 일봉 100일(`min_required=80`, EMA40 seed <2%) → **ATR/종가 변동성 밴드 1.0~6.0%(비협상 판별 필터, 2026-07-20 상한 4.5→6.0 백테스트 PF 0.86→1.60)** → 스테이지 판별(EMA 동가 None 제외) → **strict entry: 스테이지1 + 최근 5영업일 6→1 전환 인접(`stage1_freshness=5`, 2026-07-20 백테스트 3→5 PF 1.60→1.75) + EMA 3선 우상향 + 전일종가>EMA5**. **후보 점수 랭킹(2026-07-20 도입, 원설계 §9④ — 2026-09-10 cycle273c 성분①② 원설계 복원)** = `0.4×(MACD3 3봉기울기/3/종가) + 0.3×(띠폭/직전5봉평균 − 1) + 0.3×6→1신선도`(후보풀 min-max 정규화, dormant 였던 enrich macd3/band_width 배선. cycle273c 이전은 성분①`/종가` 누락(주가 순위표화, ρ=+0.853)·성분②단일봉+`1e-9`분모(6→1 전환 직후 상시 폭발) — 원설계로 복원, shadow 관측 `[kojiro_band_observe]` 동반) → `get_scanned_tickers()` score DESC 정렬 → 매수 폴루프가 최적 셋업 먼저 처리(후보>슬롯/섹터캡 경합 시). **매수 후보 정렬만 — 자격/청산 무변경**(rank_w_* PARAM_RANGES 제외, fail-safe). 지표 = 순수모듈 `kojiro_indicators.py`(pandas Wilder ATR ewm(1/20), quant_score 선례). 09:05~09:30 매수(**갭업 ≥5% / 갭다운 ≤-4% / 장중 붕괴(현재가<시가) 스킵**), 1회만. **Σ 오픈리스크 캡**(`max_open_risk_pct=4.5`, 예산 대비 % — 개수 캡과 **병존**. 포지션 리스크 = `qty×(매수가−실효손절선)`, 실효손절선 = `max(buy×(1+hard_stop_pct/100), _stop_floor 또는 buy−stop_atr×ATR, high_since_buy−trail_atr×ATR)` = 청산 **세 가격선 전부**와 동일 산식·동일 ATR 리졸버. **샹들리에 편입은 H-1(2026-08-06) 동반 필수**(사용자 결정) — H-1 이전에는 `_boot()` 이 매일 고점을 매수가로 리셋해 매수창 시점 샹들리에가 항상 두 선보다 낮았기에 `max(pct, atr)` 만으로 정확했으나, 고점을 복구하면 샹들리에가 `buy_price` 를 넘을 수 있고(실측 슈프리마 51,202 > 48,200) 제외 시 **이미 이익 확정된 포지션을 만액 리스크로 계상**해 캡이 근거 없이 신규 매수를 잠근다. 실측 Σ리스크 27,162 → **20,797**(캡 31,055 대비 87.5%→67.0%, 여유 2.6배). ⚠️ 샹들리에는 앞 두 선과 달리 **tighten-only 가 아니다**(ATR 팽창 시 하락) — 이 값은 "최악 보장"이 아니라 **평가 시점의 실제 손절선**이며 매수 시도마다 재평가되므로 그게 맞다. `stop ≥ buy_price` 인 포지션은 **0 으로 계상**(음수 금지 — 한 종목의 확정 이익이 다른 종목 실노출을 상쇄하면 캡이 조용히 무력화). `_stop_floor` 는 **읽기만** — 매수 게이트가 청산 규약을 부작용으로 바꾸면 안 된다. `high == buy` 구간(고점 미복구)에서는 샹들리에가 항상 2ATR 선보다 낮아 **기존 값 그대로**(회귀 0). `_stop_floor` tighten-only 라 보유가 길수록 리스크 감소 반영. ATR 결측 → 고정% 추정, 예외/예산0/cap0 → fail-open. 매수 게이트 전용 — 청산 절대 미차단(AST 가드). 4.5% = `max_positions 6 × 유닛 1.0% = 6.0%` 보다 낮게 잡아 저리스크 포지션은 6개까지, full-size 유닛은 4~5개에서 정지) + **섹터/테마 동시보유 캡**(`max_positions_per_sector=2`, 매수 게이트 전용·fail-open·청산 미차단) — 동일섹터(`_kojiro_sector_key` KRX basket) 카운트에 **전일 보유 포함**(2026-08-03 사이클 J — `_position_sectors` 영속 맵이 `_candidates` 와이프·ATR 밴드/유니버스 이탈과 무관하게 held 집계, stamp=recompute/BUY 반환 직전/on_position_closed pop). ⚠️ `_reset_daily_state` override 금지(밤샘 보존). **조기진입(스테이지6)·피라미딩 = Phase 2 연기**. ⚠️ `max_units_per_stock=2`/`max_units_total=10` 은 **소비처 0건 = 미강제**(안전장치 아님) — 피라미딩 없이는 1포지션=1유닛 항등이라 `max_units_total`≡`max_positions` 이고 `max_units_per_stock=2` 는 도달 불가 상한. 피라미딩 검토 시 배선 예정, 그 전까지 리스크 한도로 오인 금지. `_candidates` = ATR/stage **live 소스**이나 `prepare()` 마다 와이프되므로 **손절이 여기 단독 의존하면 안 된다** — 2026-08-04 실증: 보유 6종목 중 삼영무역(002810)만 `_candidates` 부재 → `atr=0` → **2ATR 손절 분기 통째 skip** → 손절선 21,674 관통(현재가 21,550)에도 미발화, −8% backstop 만 잔존(`[kojiro_atr_stop]` 당일 0건). 부수결함 = 저장된 `_stop_floor` 조차 `atr>0` 블록 안에서만 읽혀 함께 무시됨. **시정** = `_effective_atr(ticker)` 리졸버(`_candidates` live 우선 → `_position_atr` 영속 폴백) + `_position_atr` 영속 맵(사이클 J `_position_sectors` 패턴, stamp 3지점 = recompute/BUY 직전/on_position_closed pop) + `_stop_floor` 를 ATR 전무 시에도 단독 손절선으로 승격. 손절·리스크캡 양쪽이 **동일 리졸버** 경유(불일치 차단). ⚠️ `_reset_daily_state` override 금지(밤샘 소멸) | **고정% backstop(-8%, ATR독립) → 2ATR 하드손절(tighten-only floor, cycle220 브레이크이븐 승격 포함) → 스테이지3 진입 TRAILING_STOP(익일 아침 발화, precompute `_held_stage3`) → 2.5ATR 샹들리에 트레일링**. **브레이크이븐 플로어(cycle220, 2026-08-18 다크런치)**: `breakeven_promote_atr`(기본 **0=비활성**, 활성 권장 1.5 — donchian P1 선례, PARAM_RANGES 미편입). 활성 시 `high_since_buy ≥ buy + mult×ATR`(live `_effective_atr`) 도달이면 §2 `eff = max(eff, buy)` 승격 → `_stop_floor` tighten-only 래칫 영속(ATR 팽창해도 유지). 재시작 = `recompute_held_atr` 이 H-1 복구 고점으로 재도출(H-1 이 먼저 실행). `_position_stop_price` 는 be_line 포함 **4선 max** read-only 미러(`_stop_floor` 무변조 독트린 유지 = 커플링 불변식). **플로어≠트레일** — 샹들리에 2.5 는 조임 금기(domain `kojiro_exit_loss_review.md`, RR 훼손 방지) — fat-tail 랠리는 §4 가 담당. 근거 = 08-18 실측 샹들리에 3청산(영원무역 +9.4%→-4.4% 등) 전부 +1.5N 도달 후 전량 반납. 활성화 = N=10 재튜닝 시 DB UPDATE + 재부팅. `recompute_held_atr`(boot/저녁 훅, enrich Wilder ATR, fail-open) — **H-1(2026-08-06) 이후 같은 일봉 응답으로 `high_since_buy` 재시작 복구도 수행**(`StrategyBase._apply_high_since_buy_from_candles` 위임, donchian E3 동형). 배치는 ATR/stage 블록보다 **앞** = 워밍업 봉 부족(`len(usable) < 80`)으로 그 블록이 `continue` 해도 고점 복구는 살아남는다. 이게 없으면 2.5ATR 샹들리에 기준점이 매일 아침 매수가로 리셋돼 트레일링이 하드손절과 구분되지 않는다(08-06 실측: 보유 7종목 전부 DB `high_since_buy == buy_price`). **시간·15:20 청산 없음** — donchian 컨벤션, 멀티데이. `_MULTIDAY_STRATEGIES` 멤버 + `check_force_clear()==[]`. 공유 순차 폴루프 `_SWING_POLL_STRATEGIES=("donchian_swing","kojiro")`(double-buy 차단) | MAIN / KRX |

## 자금관리 — 사이징 방식 × 손절 기준 매트릭스 (2026-08-03)

**핵심 명제**: `수량 = 예산 × risk_pct ÷ (진입가 − 손절가)`. 손절이 **고정 %** 면 명목 = `예산 × risk_pct/s` = 종목 무관 상수 = `position_ratio` 와 수학적으로 동일 → **고정% 손절 + 비율 사이징은 이미 리스크 균등**. ATR 유닛 사이징이 리스크를 균등화하는 것은 **손절도 ATR 기반일 때뿐**이고, 사이징만 전환하면 정규화가 오히려 깨진다(**함정 #1**). ⇒ **터틀 전환은 하드손절 ATR화와 반드시 한 커밋에 묶는다.**

| 전략 | sizing_mode 기본 | 하드손절 | 터틀 상태 |
|---|---|---|---|
| `momentum` | (키 없음) | 고정 % | **영구 제외** — `prepare` 빈 stub·일봉 0건 → ATR 산출 구조적 불가 |
| `volatility_breakout` | (키 없음) | 보드별 고정 % | **영구 제외** — 15:20 전량 강제청산, 보유기간 ≤1일이라 유닛 정규화 실익 낮음 |
| `long_tail_volatility` | (키 없음) | 일중 −3% / 오버나잇 −5% | **조건부 보류** — 상한가 2모드 손절 ATR화 재설계 선행 필요 |
| `donchian_swing` | `position_ratio` | entry_atr 스탬프 시 `buy − 2.0×entry_atr` + `−9%` backstop / 미스탬프 −7% | **라이브**(운영 DB `turtle`) · **K=2.0 랏 유닛 캡 라이브**(cycle242) |
| `kojiro` | `position_ratio` | `−8%` backstop → `2×ATR` tighten-only floor(`_stop_floor`) | **guarded 전환 완료** — `_entry_atr` 미도입(live ATR + `_stop_floor` 단일 메커니즘 유지) · **K=2.0 랏 유닛 캡 라이브**(cycle242) |
| `vcp_breakout` | `position_ratio` | entry_atr 스탬프 시 3단 밴드 / 미스탬프 −7% | **다크런치** — 활성화는 백테스트 게이트 |
| `bull_flag_breakout` | `position_ratio` | entry_atr 스탬프 시 3단 밴드 / 미스탬프 −5% | **다크런치** — 활성화는 백테스트 게이트 |

**규약 (신규 전략 추가 시에도 적용)**

- **제한 축은 셋이다** — ① 개수 `max_positions` ② 명목 `Σ매수금액 ≤ total_investment` ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정, 2026-08-04). 터틀의 유닛 캡이 실제로 통제하려던 값은 ③이고 유닛 **개수는 그 프록시**일 뿐이다 — 프록시는 "1유닛 = 상수 리스크"일 때만 정확한데 (a)소액 계좌 수량 절삭 (b)`hard_stop_pct` 가 `atr_ratio>4%` 에서 2ATR 을 자름 (c)사이징 혼재 로 헐거워진다. 08-04 실측 = "6포지션(=6유닛)"이 실제로는 **3.2유닛**(예산 3.2%), 포지션별 편차 8.3배. ⚠️ **개수 캡을 리스크 캡으로 대체하지 말 것** — 리스크 캡만 두면 저ATR 종목으로 포지션 수가 무한정 늘 수 있다(개별 리스크는 작아도 상관·운영 부담). 터틀도 유닛 캡과 시장군 캡을 병행했다.
- **개수 캡(`max_positions`)의 생애주기 — 걷어내는 게 아니라 역할이 진화한다 (2026-08-08 성장 경로 자문, `_workspace/domain_consult/kojiro_position_count_vs_unit_cap.md`)**. 사용자 원질문 "종목별 유닛 제한이 있으니 종목수 제한을 걷어낼 수 있나"에 대한 자본 단계별 답이다. 결론: 개수 캡은 **소액에서 중복(②가 이미 묶음)이지만 무해**, 계좌 성장 시 **유일한 상관·운영 통제축**이 되며, 걷어내는 것은 **로드맵의 마지막 단계**(T4)이지 첫 단계가 아니다. 사용자 직관("유닛 제한=리스크 관리")은 **이상적 터틀에서 옳으나** 우리 유닛은 (a)1주 양자화 (b)hard_stop backstop (c)사이징 혼재로 깨진 벽돌이라 개수≠리스크 — ③의 존재 자체가 그 자백이다.

  | 자본(net) | kojiro 예산 | `position_ratio` | 개수 캡 역할 | 피라미딩 | 상관군 캡 |
  |---|---|---|---|---|---|
  | **T0 현재(~117만)** | 706K | **0.166**(불변식 지혈) | ②와 중복(무해) | inert 봉인 | 섹터 캡 2 |
  | **T1 500만** | 300만 | 0.14~0.166 | 경계 | **배선+다크런치** | 섹터 캡 2 |
  | **T2 5000만** | 3000만 | 0.08~0.10 | **load-bearing** | **ON(4유닛)** | 유닛-섹터 캡 |
  | **T3 1억** | 6000만 | 0.06~0.08 | load-bearing | ON | 테마+섹터 |
  | **T4 2억** | 1.2억 | 0.04~0.05 | **흡수 가능(옵션)** | ON | 상관군 **주통제** |

  **정량 근거 3**: (1) 피라미딩 해상도 임계 = **net 500만**(1유닛≥10주가 중형주 기준 이 자본에서 교차 — 현재 117만은 대형주 1주라 피라미딩이 순수 노이즈). (2) ②명목 개수 천장 = `1/position_ratio`(자본 무관): ratio 0.20→5명, 0.05→20명 — 성장하며 ratio↓하면 저ATR 종목이 실제로 쌓여 **한국 중소형 폭락일 상관=1 수렴** 위험. (3) ③Σ리스크 캡은 **규모 불변**(항상 4.5 full유닛에서 물림, 100배 커져도 불변) — 더 담으려면 `max_open_risk_pct` 상향이 필요하고 그건 **상관군 캡이 전제**(터틀 12% heat 도 상관군 캡 6/10 동반). **궤적 본질 = 사이징 주도축 인계**(소액 notional-집중 → 대형 ATR유닛-계층). `position_ratio` 는 소액의 목발이지 종착점이 아니다.

  ⚠️ **VCP/BFB 는 kojiro 와 로드맵이 갈린다** — VCP=변동성 수축 진입(entry ATR 국소 최소, 2N 손절 과도 타이트)·BFB=measured-move 목표 확정이라 **둘 다 피라미딩 부적합**. 유닛 사이징(리스크 균등)까지만 태우고 피라미딩 제외 → `max_units_total`≡`max_positions` 영구 → **개수 캡이 T4 에서도 흡수 안 되고 load-bearing 영구**. 활성은 자본이 아니라 **체결+백테스트 게이트**(현재 체결 0건).

  **지금 당장(FREEZE 표본 N=1·0/4 보호 — 구조 재설계 금지)** = ① 불변식 지혈 `ratio 0.166`(DB 적용 완료) ② 본 생애주기 문서화(코드 diff 0) ③ `max_units_*` inert 봉인 유지(소비처 0건). **나머지 전부 자본/체결 게이트**, 기제 코드 착수 = **net 500만 도달 시**. 미결 결정 5(net 500만 도달 시 재개): weight 궤적 / 피라미딩 스타일(승자 추가 vs 고정 1유닛) / `max_open_risk_pct` 상한(보수 6~8 / 공격 10~12) / 상관 그룹핑 입도 / 기제 착수 자본.
- **매수 수량은 `StrategyBase._apply_budget_limit()` 관문을 반드시 경유**한다 (AST 가드 A-GATE 가 7전략 모든 `return` 을 검사). 이중제한 = ① 개수 `max_positions` + ② 명목 `Σ매수금액 ≤ total_investment`. 잔여 부족 시 **부분 매수**(잔여 < 1주 → 0). 비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — **분기 순서가 계약**. **cycle242** — 그 뒤(관측 `[oversized_fallback]` 앞)에 `sizing_mode="turtle"` 전략 한정 **랏당 최대 유닛 상한**이 붙는다: `min(final, floor(max_lot_units × 예산 × risk_pct ÷ ATR))`, 0 이면 매수하지 않는다. ATR 은 터틀 분기와 같은 `_candidates[ticker]` read-only(`atr`/`atr14` 상이 시 불채택 = fail-open + `[fallback_cap_skipped]` WARNING). **cycle245** — 그 K축 캡이 **이 랏을 실제로 심사하지 못한 모든 랏**(비터틀 5전략 전부 + 터틀이지만 `ticker`/`risk_pct`/예산/ATR 결손으로 fail-open 한 랏)에는 그다음, `[oversized_fallback]` 관측 **뒤**·`return` 앞에서 **ρ축 명목 상한**이 붙는다: `min(final, int(max_lot_ratio_mult × int(예산 × position_ratio)) // 현재가)`, 0 이면 매수하지 않는다. **cycle254(2026-09-05)부터 두 캡은 `min` 으로 후심사한다**(구 결정 ⑦ "상호배타 — `min` 합성 없음" 폐기 — K축이 심사한 랏도 이제 ρ축을 통과해야 한다. 사이즈드 터틀 랏·PR 낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한으로 이미 컷오프 이하라 무접촉이고, 실효는 1주 폴백 랏뿐. 판정기(`_lot_units_cap_governs`) 자체가 실패한 경우(`probe_error`)만 fail-open). `position_ratio` 결측·예산 0·초소액·판정 예외는 전부 fail-open + `[ratio_cap_skipped]` WARNING 이고, **키 부재는 캡 OFF**(cycle242 와 반대 관례 — 매수를 막는 통제라 fail-closed 는 P0-1 재현 경로).
- **불변식 `position_ratio × max_positions ≤ 1.0`** — DEFAULT_PARAMS 는 AST 가드(C-DEFAULT), AI 추천은 `_validate_recommendations` 교차검증이 강제. `max_positions` 는 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(리스크 정체성 상수).
- **ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 게이팅 **금지**. DB 토글 하나로 기보유 포지션의 손절 규약이 바뀌면 안 된다. 스탬프 값은 sizing 에 쓴 ATR 과 **반드시 동일**(커플링 불변식). 터틀이 0 을 반환하는 모든 경로(변동성 floor / 잔여 부족 / `ticker=None` / 예외)는 **미스탬프** → 기존 % 손절 byte 동일.
- **터틀 수량 ≤ 비중 수량**이 항상 성립 — `compute_unit_qty_guarded` 의 notional 상한이 `position_ratio × 예산` 이기 때문. 즉 전환은 **순수 축소 방향**이고 저ATR 수량 폭증은 구조적으로 불가능. 임계 = `atr_ratio = risk_pct ÷ position_ratio`(기본 2.5%).
- **3단 밴드 손절**(VCP/BFB) — `base_stop = min(buy − stop_atr×entry_atr, buy×(1+turtle_min_stop_pct/100))` 로 **과도한 타이트화 차단**, 상단은 `turtle_backstop_pct` 캡. ⚠️ VCP 는 정의상 변동성 수축 시점 진입이라 진입 ATR 이 국소 최소 → `atr_ratio 1.5%` 면 `2ATR = −3%` 로 현행 −7% 대비 절반 이하가 된다. `turtle_min_stop_pct`(VCP −5.0 / BFB −4.0)가 유일한 방어선이며 **실제 활성화 전 백테스트 스윕 필수**.
- 기존 live-ATR breakeven 래치(사이클 C)는 `entry_atr <= 0` 로 게이팅 — 두 tighten 메커니즘 공존 차단. 승격은 `max()` 로만 이동(tighten-only).
- 터틀 키 **7종**(`sizing_mode`/`risk_pct`/`stop_atr`/`turtle_backstop_pct`/`min_vol_floor_pct`/`turtle_min_stop_pct`/**`max_lot_units`**)은 전부 `PARAM_RANGES`/`INT_PARAMS` 미편입 = AI 자동튜닝 제외. 가드 = `tests/unit/ast/test_cycle242_ast_fallback_notional_cap.py` G-242-1(런타임 dict + 소스 리터럴 이중). ⚠️ 종전 6종은 **기계 가드 없이 문서 주장뿐**이었다(`grep min_vol_floor_pct tests/unit/ast/` 0건) — 후속에서 같은 가드에 편입 권장.
- **`max_lot_ratio_mult` 는 터틀 키가 아니라 전 전략 키**(cycle245) — 위 7종과 함께 세면 **8종**이 되지만 성격이 다르다. **7 전략 전부**의 `DEFAULT_PARAMS` 에 `2.5` 로 명시하며(터틀 2전략 포함 — `sizing_mode` 를 되돌리는 순간 ρ축이 자동으로 받는다), `PARAM_RANGES`/`INT_PARAMS` 미편입 = AI 자동튜닝 제외. 가드 = `tests/unit/ast/test_cycle245_ast_ratio_notional_cap.py` **G-245-1**(런타임 dict + 소스 리터럴 이중) + **G-245-6**(전략 파일 **glob 전수**로 키 존재 + 값이 `_MAX_LOT_RATIO_MULT_DEFAULT` 와 동치) + **G-245-7**(전략 `calc_buy_quantity`·터틀 사이징 함수에 `max_lot_ratio_mult` 토큰 0 = 캡 로직은 관문 안에만). 읽는 쪽 클램프 `[1.0, 20.0]` 이고 **하한 1.0 이 "정상 비중 랏 무접촉" 항등식의 전제**다.
- ⚠️ **BFB 는 익일 청산 전략이 아니다** (2026-08-06 정정 — 종전 서술 "BFB 는 `_MULTIDAY_STRATEGIES` 미포함(익일 청산)이라 재시작 재도출 불필요"는 **거짓**이었다). 코드 실측: `_execute_next_day_clear` 대상 = `("momentum","long_tail_volatility","volatility_breakout")` 뿐 · `_force_clear_main_only` 대상 = `("volatility_breakout","long_tail_volatility")` 뿐 · BFB `check_force_clear()==[]`. 즉 BFB 는 `max_hold_days`(5영업일) 시간 청산까지 **실질 멀티데이 보유**이며, `_MULTIDAY_STRATEGIES` 비멤버는 `is_next_day` 배지 표시에만 영향한다. 그래서 BFB 는 `_entry_atr`·`high_since_buy` **재시작 복구가 둘 다 없는 유일한 보유형 전략**이었고, **P1.5(2026-08-06)에서 도입**했다 — `_rederive_entry_atr`(매수일 *이전* 봉만, 부족 시 미스탬프) + `recompute_high_since_buy`(`StrategyBase._apply_high_since_buy_from_candles` 위임, 복사 금지). **배선은 `boot_manager`** — DB positions 복구가 끝난 뒤라야 보유가 확정되고, `scheduler.py` 는 8영역이라 diff 0 을 지켜야 한다. ⚠️ `_SWING_POLL_STRATEGIES` 에 BFB 편입 **금지**(그 상수는 매수 폴루프·구독 대상에도 쓰여 매수 행위가 바뀐다). ⚠️ **비활성이 아니다** — 운영 DB 실측(2026-08-06) `enabled=True`·`weight=0.10`(VCP 도 동일). 실현 손실이 0인 것은 **진입 조건이 엄격해 도입 이래 체결이 0건**이기 때문이지 꺼져 있어서가 아니다.
- **청산 파라미터는 `_position_setup` 영속 맵 + `_effective_setup` 리졸버 경유** (P1, 2026-08-06 · VCP·BFB 공통). `_candidates` 는 `prepare()` 마다 와이프되고 **보유 종목은 셋업이 무너져 후보 자격을 잃는 게 정상**이라, 청산이 거기 단독 의존하면 **T+1 아침부터 매일** 죽는다(재시작 사고가 아니다). 죽는 범위는 트레일링 하나가 아니라 — VCP = §1.5 래치·**§2 `base_low` 손절**·§3 트레일링·§4 `ema50` 이탈 / BFB = §1.5 래치·**§2 `flag_low` 손절**·**§3 measured-move 익절 전체**·§4 트레일링. 2026-08-04 kojiro 삼영무역과 동일 클래스. **필드별 갱신 규약이 다르다** — 구조 레벨(`base_low`/`flag_low`/`pole_*`/`flag_high`)은 BUY 직전 stamp 후 **불변**, 지표(`atr14`/`ema50`)는 boot 훅이 **이미 fetch 하는 일봉으로 매일 갱신**(`ema50` 을 박제하면 상승 추세에서 뒤처져 이탈 청산이 늦어진다). BFB §3 은 직접 인덱싱이었어서 `.get()` 방어 + **키 결손 시 미발화**(과잉 청산 금지)가 계약. ⚠️ `_reset_daily_state` 에서 clear **금지**(밤샘 소멸, AST 봉인). VCP 는 `recompute_high_since_buy` 의 **기존 일봉 fetch 응답을 재사용**해 `_rederive_entry_atr` 호출(추가 KIS 호출 0 + scheduler diff 0).
- **트레일링 기준점(`high_since_buy`) 영속은 전략 책임** (H-1, 2026-08-06) — `risk.on_tick` 은 메모리만 올린다(hot path 라 DB 쓰기 금지). DB 되쓰기 경로가 없으면 `_boot()`(매 영업일 07:55)이 DB row 로 Position 을 재생성할 때 **트레일링 기준점이 매수가로 리셋**된다. 보정 헬퍼 `StrategyBase._apply_high_since_buy_from_candles` 는 **단일 진실원**(donchian/VCP 에 로그 접두사만 다른 복사본 2벌이 있었고 kojiro 가 3번째가 될 참이었다). 신규 보유형 전략은 이 헬퍼를 **이미 fetch 한 일봉 응답으로** 호출할 것 — 추가 KIS 호출 0 + scheduler(8영역) diff 0.

## 공통 패턴

- `prepare()` 단계별 통과 카운트는 `_scan_stats` 누적 → `get_scan_stats()` → `strategies.<id>.scan_stats` 로 프론트 ScanMonitor 깔때기
- **사이클 21 (2026-05-20) — VB/LTV/momentum 도 깔때기 노출**:
  - VB: `_empty_scan_stats()` 9 키 (`universe_candidates / universe_filtered / price_filtered / mcap_pass / trade_amount_pass / candle_fetch_ok / k_value_computed / final_prepared / last_run_at`)
  - LTV: VB 9 키 + `consecutive_limit_pass` (10 키 — 연속상한가 N일 제외 통과)
  - momentum: prepare 없음 → `scanner.scan_filter_stats` 모듈 전역 dict 7 키 (`universe_candidates / rate_pass / mcap_pass / trade_amount_pass / limit_up_excluded / final_prepared / last_run_at`). `MomentumStrategy.get_scan_stats()` 는 모듈 dict 사본 반환
  - scan_stocks() 가 등락률 30%+ (상한가) 도 명시 분기 — `limit_up_excluded` 카운트 + 구독 후보 풀에서 제거 (`check_buy_signal` 의 30% 가드와 이중 안전망)
- VB/LTV/BFB `_scan_universe` (**현행, 사이클 108~**): `stock_master.list_by_filter(min_market_cap, min_trade_amount, ...)` **DB 단일 조회** — KIS 호출 0건. 시총(`raw.hts_avls`)·거래대금(`raw.acml_tr_pbmn`) JSONB 필터만 수행. **거래량순위 API(`FHPST01710000` volume-rank)는 사이클 108 에서 100% 폐기** (production 호출처 0건 = dead, AST 가드 `test_cycle108_ast_no_kis_volume_rank.py` + `test_cycle97_ast_no_volume_rank.py` 가 `_scan_universe` 재도입 영구 차단). 폐기 *전* (사이클 89~107) 방식 = 거래량순위 응답 1건으로 `prdy_vol × (stck_prpr - prdy_vrss)` 시총·전일거래대금 산출 (이제 미사용). ※ momentum 만 순위 API 사용 = **등락률순위**(`/ranking/fluctuation` `FHPST01700000`, `condition.py:299`) — *거래량순위와 다른 TR*. VB/LTV/BFB 와 무관.
- **사이클 108 (2026-06-11) — Plan Phase A 완료: VB/LTV/BFB `_scan_universe()` stock_master 베이스 전환 (KIS `volume-rank` API 100% 폐기, KIS API 호출 100% 절감)**: 사이클 104 인계 Q5=B (LOW 위험 자문 생략) + 사이클 107 raw 보강 의존성 해소 완료 → Plan Phase A 데이터 활용 가능. 사용자 결정 Q1=A (시총 = `hts_avls` 백만원 단위) + Q2=A (통합 단일 사이클 3 전략 동시 전환) + Q3=C (4 필터 = `min_market_cap` + `min_trade_amount` + `exclude_tickers` + `nxt_tradable`). **전환 패턴 (3 전략 동일)**: (1) DEFAULT_PARAMS 4 필터 추가 (`min_market_cap` + `min_trade_amount` + `exclude_tickers` + `nxt_tradable`, 사이클 32 R4 universe guard 답습 영속). (2) `_scan_universe()` = `stock_master.list_by_filter(min_market_cap=..., min_trade_amount=..., exclude_tickers=..., nxt_tradable=...)` 호출 (KIS `volume-rank` (FHPST01710000) 100% 폐기). (3) ETF 키워드 제외 (사이클 89 답습 + 6자리 ticker 영속). (4) funnel 카운터 영속 = `universe_candidates` + `universe_filtered` + `last_run_at` (사이클 21 답습). (5) graceful (`list_by_filter()` raise 시 빈 list 반환 + `_scan_stats["universe_candidates"]=0` 영속). **운영 효과**: KIS API 호출 100% 절감 (VB 3 + LTV 3 + BFB 3 = 9 호출/일 → 0 호출, 사이클 17 OPSP0002 backoff + KIS LMS chain 안전 효과) + 신호 빈도 ±5% 이내 영속 (사이클 89 답습 + 동일 필터 적용) + stock_master ~2,800 종목 활용 (사이클 106 lifecycle race 차단 + 사이클 107 raw 보강 + 사이클 108 list_by_filter 통합) + 운영자 통제 (Plan Phase C UI 운영자 필터링 호환 = `exclude_tickers` 인자 활용). **회귀 가드 52 PASS** (3 영역 통합 = 사이클 108 격리 실행 52 PASS / 0.20s / flakiness 0). xfail 의미 전환 23건 (사이클 97 K-2 패턴 답습 영속 = 사이클 89/95/96/97/99 폐기 계약 영구 보존). **사이클 38 명문화 영속**: scanner 단계 = 매수 진입 전 후보 풀 구성 한정 + 매도/손절/Trailing/익일청산/15:20 강제청산 hot path 무관. 매매 안전성 무영향 확정.
- **BFB `_scan_universe` 시간무관화** (사이클 48, 2026-05-27 — 0건 매매 결함 전면 시정): 사이클 33 의 `acml_vol`(당일 누적) 방식은 BFB `prepare()` 가 07:50 장 전 boot 에서만 호출 → `acml_vol=0` → **매일 "유니버스 0종목"** (운영 DB 확정). VB/LTV 와 동일하게 `volume-rank`(FHPST01710000, blng 0/1/3 합집합)로 소스 교체 — 응답 1건에 `prdy_vol`/`stck_prpr`/`prdy_vrss`/`lstn_stcn` 포함 → 개별 `fetch_stock_detail` 호출 없이 `trade_amt = prdy_vol × (stck_prpr - prdy_vrss)` 산출 + 시간 의존 제거. 전일 확정치 필수 (당일 acml 금지 — 오후 편중 왜곡). `min_trade_amount_failed` scan_stats 유지
- **BFB Pole 임계 완화** (사이클 48): `pole_min_return` 20.0→15.0 / `pole_max_red_ratio` 0.30→0.45. 한국 ±30% 환경에서 +20% + 음봉 30% 교집합 0 차단.
- **BFB flag_retracement 완화** (사이클 211, 2026-07-15): `flag_retracement_max` **0.382→0.5** (플래그 조정폭 폴폭의 38.2%→50%). Phase B funnel 실측 = 폴/플래그 병목(281→80→12), 오프라인 스윕 폴+플래그 통과 3→10(3.3배). `flag_volume_ratio 0.60`(거래량 수축 안전장치) 절대 불변 = 급락 되돌림 오판 봉쇄(사이클 198 논리). **DB 지혈 동반**(strategy_config.bull_flag_breakout: `pole_min_return` 20→15 코드 정합 + `flag_retracement_max` 0.382→0.5, DB값 우선). 사이클 48/198 BFB 완화 계열 후속. 매매 안전성 8영역 diff 0(flag 검출=prepare 매수 진입 전, 사이클 38).
- **VCP 추세필터 EMA 하향** (사이클 48): KIS 100일 한도로 `effective_ema_long` 이 200EMA 를 ~75 로 축소 + `ema_mid(150)>75` 재축소 → 50/65/75 정배열 항상 0 (추세필터 0건 결함). `ema_long` 200→**120** / `ema_mid` 150→**60** → 100일 내 50/60/120 안정 계산. `last_pullback_max` 0.08→**0.12** 완화. `effective_ema_long = min(ema_long, available_len - uptrend_days - 5)` 자동 축소 가드 + `_check_trend_filter(candles, effective_ema_long=)` 시그니처는 안전망으로 유지. 분할 fetch 인프라는 운영 1주 후 별도 검토
- **VCP Pullback "마지막 폭 0.0%" 결함 시정** (사이클 49, 2026-05-31): 사이클 48 시정 후에도 잔존한 VCP 단독 0건 매매 (운영 funnel 5/26~5/29 33/33 우량주 step 6 동일 사유 탈락). Root cause: (a) `_check_pullback_sequence` 가 chrono 끝부분 rising 중이면 마지막 swing 누락 → `base["last_pullback_pct"]` 미설정 → funnel reason 디폴트 "0.0%" 표시 (운영자 오인). (b) 등호 포함 swing 검출이 평탄 우량주 1원 단위 미세 변동도 swing 으로 인식 → 회수 범위 위반. 시정: ATR threshold ZigZag (신규 `min_swing_atr_mult=0.5`, 베이스 ATR 의 0.5배 미만 변동 무시) + state machine ('undefined'/'up'/'down') 으로 마지막 swing 미완성 포함 + False 반환 시에도 `last_pullback_pct` 항상 기록 (funnel reason 정확성). 회귀 가드 `test_cycle49_vcp_pullback_width_fix.py` 6 케이스. 매도/Trailing/익일청산 무변경 — 매수 진입 임계만 시정.
- **BFB/VCP 장중 재prepare 안전망** (사이클 48): `scheduler._reprepare_breakout_if_empty` 대상에 `bull_flag_breakout`/`vcp_breakout` 추가 (기존 VB/LTV 에 더해). boot 실패/일시 API 오류 회복용 — 주 메커니즘은 prdy 시간무관 유니버스. 후보 비었을 때만 호출 (전략당 5분 1회, rate limit 부담 미미)
- VB/LTV/donchian/bull_flag/vcp 모두 `prev_idx` 분기 동일: `candles[0].stck_bsop_date == 오늘`이면 candles[1] 을 전일로 사용
- 0종목 확정 시 `ERROR` 로그 + `system_logs` 기록
- 1주 폴백 (모든 전략): `StrategyBase._fallback_one_share(current_price)` 잔여 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`. **터틀 전략은 그 뒤에 `max_lot_units` 캡이 뒤따른다** — 폴백 1주가 K 유닛을 넘으면 잘리고, `floor(K×u*) == 0` 이면 **매수하지 않는다**(cycle242. 폴백 1주가 설계 유닛의 평균 4.94배·최대 15.61배가 되던 시정). **터틀이 아니거나 K축이 심사하지 못한 랏은 그 대신(또는 그 뒤에도) ρ축 캡(`max_lot_ratio_mult`, K_ρ=2.5)이 뒤따른다** — 명목이 `K_ρ × position_ratio × 예산` 을 넘으면 자르고 **1주도 못 사면 매수하지 않는다**(cycle245. 폴백 1주가 설계 랏의 4.23배가 되어 09-04 최대 손실 −11,000원을 내던 시정. 컷오프 = `int(K_ρ × int(예산 × position_ratio))` 원 — 09-04 예산 기준 LTV·VCP 130,100 / VB 341,515 / BFB 243,940 / momentum 81,312 / donchian·kojiro 195,150 / 323,952). **cycle254** — donchian·kojiro 는 더 이상 K축 판정기가 예외 처리(구 결정 ⑦)됐을 때만이 아니라 **1주 폴백 랏에 상시** 이 컷오프가 적용된다(구 결정 ⑦ "상호배타" 폐기 — 사이즈드 터틀 랏은 `compute_unit_qty_guarded` 의 notional 상한으로 항등적으로 무접촉이라 실효는 1주 폴백뿐). `[ratio_cap_config]` 라벨도 2종(off/on)으로 통일 — 터틀 전용 구 라벨은 폐기
- **사이클 39+41 (2026-05-22) — funnel 단계별 자동 hook**: BFB/VCP/donchian `prepare()` 가 `StrategyBase._record_funnel_step(step_no, step_name, survived, excluded=None, *, step_conditions=None)` 호출로 단계별 통과/탈락 종목 캡처 (BFB/VCP/donchian 각 9단계 — 사이클 157 +1단계 후). **사이클 41**: `survived: list[str \| dict]` (자동 dict 변환 — `_resolve_ticker_name` 종목명 lookup) + `excluded: list[{ticker, name, reason}]` (수치 포함 사유 — "음봉 비율 35% > 30%" / "마지막 폭 12% > 8%" / "신고가 미달 52000 < 55000" 등) + `step_conditions` (UI 단계 조건 툴팁용). cap 200/20 자동 적용. 9:30 `_scan_loop` 첫 진입 시 `scheduler._auto_capture_funnel_snapshots` 자동 발화 → DB `strategy_funnel_snapshots` 단계별 INSERT. `_reset_daily_state` 동행 reset
- **사이클 132 (2026-06-15) — funnel 전략별 정책 명시 + 휴장일 UI 안내 (Q2=C + Q3=A 사용자 결정 영속)**: (1) **momentum**: 실시간 본질 = funnel **영구 제외** 명시 (`prepare()` empty stub + docstring 명시 + `_record_funnel_step` 호출 0건 AST 영구 가드). UI 안내 "이 전략은 실시간 돌파 기반 — funnel 적재 미적용" 동행 영속. (2) **volatility_breakout / long_tail_volatility**: 사이클 140 자문 → 사이클 143 정상 활성화 (아래 사이클 143 행 참조). (3) **BFB / VCP / donchian**: 사이클 39+41 자동 hook 영속 (변경 0). (4) **휴장일 UI 안내**: `GET /api/strategy-funnel` 응답 `is_business_day: bool` + `holiday_note: str | None` 추가 (KIS `chk-holiday` 재사용 영속, 사이클 17 영속). 휴장일 운영자 UI 접속 시 amber 배너 + 한글 안내 ("오늘은 휴장일 — 영업일 데이터 미수신"). is_market_open 호출 실패 시 graceful 영업일 가정 (사이클 88 G-REJECT 답습). **매매 안전성 무영향 영속**: prepare() 메모리 + 라우트 응답 schema 만 확장 + scanner / risk / order / realtime / auth 변경 0 + 매수 진입 *전* 한정 영속.
- **사이클 143 (2026-06-16) — VB 5단계 + LTV 6단계 funnel hook 정상 활성화 (사이클 140 자문 영속, 사이클 132 인계 종결)**: **VB 5단계** (`volatility_breakout.py::VB_FUNNEL_STAGES`): (1) "거래량순위 + stock_master 기반 후보" (universe_candidates) + (2) "시총 + 거래대금 필터 통과" (universe_filtered) + (3) "일봉 fetch 통과" (candle_fetch_ok) + (4) "전일 Range > 0 + noise 계산 통과" (range_pass) + (5) "K값 계산 + target_offset > 0" (final_prepared). **LTV 6단계** (`long_tail_volatility.py::LTV_FUNNEL_STAGES`): VB 1~4 + (5) "연속 상한가 필터 통과" (consecutive_limit_pass, LTV 특화) + (6) "K값 계산 + target_offset > 0". `prepare()` 본체에 `_reset_funnel_steps()` + `_record_funnel_pipeline_step(STAGES[i-1], survived=tickers, step_conditions=..., excluded=excluded_list)` 5/6 호출 (사이클 47 FUNNEL_STAGES 위임 패턴 답습 + 사이클 39+41 BFB/VCP/donchian 답습). `excluded: list[dict]` 에 수치 포함 사유 ("fetch 실패" / "noise 0" / "prev_range=0 ≤ 0" / "연속 상한가 N일 이상" / "target_offset=0 ≤ 0 (k=X.XXXX)"). **UI**: `frontend/src/pages/StrategyFunnel.tsx` 사이클 132 안내 메시지 "단계별 funnel 후속 사이클 (사이클 133 인계)" 영구 제거 (G-FE-132-C 의미 전환, 사이클 66 K-2 패턴). 매매 안전성 영향 0 (사이클 38 명문화 영속, scanner 매수 진입 *전* + check_exit_signal hook 호출 0건 G-143-SAFETY-3 영속). `DEFAULT_TRADABLE_BOARDS` 변경 0 (VB MAIN 단독 사이클 26 + LTV 3보드 사이클 38 영속). **영속 의무**: `_scan_stats` 9/10 키 (변경 0) + `_record_funnel_pipeline_step` 호출 ≥ 5/6건 AST 가드 + `_reset_funnel_steps()` 호출 영속 + `check_exit_signal` 본체 funnel hook 호출 0건 영속. 회귀 가드 15 케이스 (G-143-VB 5 + LTV 5 + INT 2 + SAFETY 3).
- **사이클 156 Q0 (2026-06-17) — VB/LTV/BFB `nxt_tradable=True` 강제 필터 제거 (HIGH 사이클 108 silent 결함)**: 사용자 verbatim "nxt_tradable은 주문처리 시 NXT/거래소 분기용. 모든 거래 종목이 NXT 거래 가능한 건 의도와 다름". 운영 DB 실측 = total 3,573 / nxt_true 579 (16.2%) / nxt_false 2,994 (83.8%) → 후보 풀 5.2배 확장. 사이클 108 도입 시점 silent (사용자 의도 = 사이클 54 `_strategy_exchange_async` 주문 시점 NXT/KRX 분기). donchian = 사이클 121 이미 None (변경 0). 주문 시점 분기 영속.
- **사이클 157 (2026-06-17) — VCP hardcoded list 폐기 + 6 전략 `_is_master_blocked_for_entry` hook 통합 + FUNNEL_STAGES +1단계 (HIGH 사이클 153 인계 종결)**: Q1 = VCP `_scan_universe` `KOSPI_200_TICKERS + KOSDAQ_150_TICKERS` hardcoded import 폐기 + `list_by_filter(is_kospi200=True, is_kosdaq150=True)` 전환 (사이클 153 donchian 패턴) + `fetch_stock_detail` 124회/일 → 0. Q2 = 공통 헬퍼 `scanner.apply_master_block_filter(tickers, protected_tickers)` + 5 전략 (VB/LTV/donchian/BFB/VCP) wrapper `_apply_master_block_filter_in_prepare` + momentum `scan_stocks` 내부 hook (사이클 132 funnel 미적재 영속). 13건 차단 (사이클 129 master_raw 7 + 사이클 155 raw 6). 보유 종목 절대 보호 (사이클 32 R4). Q3 = FUNNEL_STAGES +1단계 (VB 5→6 / LTV 6→7 / donchian 8→9 / BFB 8→9 / VCP 8→9, momentum 미적재 영속). production +295L net / 회귀 가드 22 케이스 (HIGH 6) / 의미 전환 5건 (사이클 47/50/148/153) / 백엔드 2,639 PASS × 3회 flakiness 0 / 사이클 157 격리 22/22 PASS × 3회. 매매 안전성 8영역 + 사이클 32 R4/38/81/88/108/121/129/132/148/151/153/154/155 변경 0.
- **사이클 158 (2026-06-17) — 3 결함 통합 시정 (momentum 로그 cap + VB prepare 자동 재시도, MEDIUM)**: 운영 사례 = 2026-06-17 08:13~08:50 KST EC2 재시작 직후 (사이클 157 배포 08:08 KST). Q1 = 씨에스윈드(112610) momentum 익일 청산 KIS APBK0918 거부 후 `check_exit_signal` logger.info 매초 폭주 (26회/30초). 시정 = `momentum.py` 모듈 전역 `_next_day_clear_logged_today: DailyEmitCap[str]` + `check_exit_signal` 익일 청산 분기 cap (사이클 31 R6 / 57 V-1 패턴 답습) + `reset_next_day_clear_logged_today()` 헬퍼 + `_reset_daily_state` 동행 reset. Q2 = `_boot()` 후속 prepare() 가 `_full_universe_load_once` 완료 전 호출 → 5 전략 stock_master 0건 (VCP 제외, 사이클 157 list_by_filter 부재 영역). 시정 = VB `prepare()` 0건 시 자동 재시도 hook (cap 3회 + sleep 30초). production +45L net (momentum +26L + VB +19L). 사이클 158 격리 11/11 PASS (Q1 6 + Q2 5). 매매 안전성 8영역 + risk/order_engine/realtime/auth diff 0 + 사이클 19 `_selling` / 32 R4 / 38 / 54 / 132 영속. Q3 영역 (Supabase 연결 race) = `task_loop_helper.py` + `scheduler.py` 후속 사이클 인계.
- **사이클 148 (2026-06-16) — VB `prepare()` 가격 필터 후처리 추가 (사이클 64 scanner 정합)**: 사용자 보고 (verbatim) "전략별 시세 입수 비정상 현상 존재. 변동성 돌파 전략 시세를 애초에 시세수신 구독신청조차 안한 이유 확인 필요". 진단 = VB `prepare()` 31 종목 확정 vs scanner `_apply_price_filter` 6 종목 (298040/000660/009150/402340/011070/012450) `bfdy_clpr > max=500,000` 차단 → 시세 구독 신청 자체 안 함 → UI 영역 "현재가 -" 표시. 사용자 결정 Q1=B (VB 단독 우선) + Q2=C (PriceFilter 단일 source) + Q3=A (scanner 영속) + Q4=B (MEDIUM). `volatility_breakout.py::_scan_universe()` 영역 + `await self._apply_price_filter_in_prepare(filtered)` 호출 1줄 + `_apply_price_filter_in_prepare()` 신규 메서드 (+66L net). PriceFilter 비활성 (min=0, max=0) → 전체 통과 (회귀 보존) / 보유 종목 → 무조건 통과 (사이클 32 R4 + 사이클 30 005935 영속) / `raw.bfdy_clpr` miss → graceful 통과 (사이클 64 답습) / `min_price > 0 + bfdy_clpr < min_price` → 차단 / `max_price > 0 + bfdy_clpr > max_price` → 차단. `system_config.get_price_filter` 단일 source 영속 (scanner ↔ prepare 정합 보장 + PUT 즉시 무효화). scanner `_apply_price_filter` 영속 (이중 안전망, 사이클 32 R4 답습). 사이클 143 VB 5단계 FUNNEL_STAGES 변경 0. **회귀 가드 12 케이스 (HIGH 4 + MEDIUM 3 + LOW 5)**: G-148-PRICE-1 HIGH 운영 실증 6 종목 차단 + G-148-PRICE-2 가격 min 동행 + G-148-PRICE-3 비활성 회귀 보존 + G-148-PRICE-4 scanner protected_tickers keyword 영속 + G-148-PRICE-5 list_by_filter 시그너처 변경 0 + G-148-FUNNEL-1 VB_FUNNEL_STAGES 5단계 영속 + G-AST-148 get_price_filter import 영속 + DEFAULT_PARAMS 별도 키 금지 + **G-148-SAFETY-1 HIGH** check_exit_signal 호출 0건 + **G-148-SAFETY-2 HIGH** risk/order_engine import 0건 + **G-148-SAFETY-3 HIGH** 보유 종목 차단 0건. 백엔드 2,787 → 2,799 PASS × 3회 flakiness 0 / 사이클 148 격리 12/12 PASS / 매매 안전성 무영향 (매수 진입 *전* 영역 한정, 사이클 38 명문화 영속). 사이클 149+ 인계: LTV/donchian/BFB/VCP 4 전략 동일 패턴 적용 의무 + Settings UI 안내 메시지 ("VB prepare 가격 필터는 익일 반영", PUT 즉시 반영은 scanner 영역만).
- **사이클 C3 (2026-07-15) — VB `_apply_quant_filter_in_prepare` 퀀트 재무 게이트 관찰 훅 (Phase 1, 관찰 전용)**: `volatility_breakout.py` `prepare()` 말미에 `_apply_quant_filter_in_prepare(final_prepared_tickers)` 호출 1줄 + 신규 메서드 (사이클 148 `_apply_price_filter_in_prepare` 미러). DEFAULT_PARAMS `quant_filter_enabled=False` / `quant_min_f_score=0` / `quant_max_mf_rank=0` 3키 (**PARAM_RANGES 미편입**). `VB_FUNNEL_STAGES` 6→**7단계** (step 7 = "퀀트 재무 게이트(관찰) — F-Score/마법공식 스코어 기록, 배제 0"). `src/engine/quant_score.py` (F-Score-7 = Piotroski 9지표 中 현금흐름표 TR 부재로 CFO 2지표 제외 + 마법공식 EV/EBITDA·ROC) 를 `stock_master_financial.get_financial_series` + `stock_master.get`(시총) 로 계산 → funnel step 7 기록만. **기본 OFF = 관찰 전용, 배제 0** — `quant_filter_enabled=True` 여도 실배제 로직 미구현 (Phase 2 C4 인계). 결측·보유 fail-open (사이클 32 R4). graceful (전 단계 예외 격리). momentum 라이브 경로 무변경 (관찰은 오프라인). 매매 안전성 8영역 diff 0 (prepare = 매수 진입 전, 사이클 38). 상세 = `src/engine/CLAUDE.md` 사이클 C1~C3.
- **사이클 G (2026-08-02) — VB RR 개선 Phase 1 (Part A C2 조기청산 default-off + Part B RS/RSI 관찰)**: 사이클 F 실측 VB 유일 열위(승률 35%·RR 1.35<필요RR 1.83) 대응. **Part A** (`check_exit_signal`): DEFAULT_PARAMS `failed_breakout_exit_enabled=False`/`failed_breakout_buffer_pct=-0.5`/`failed_breakout_confirm_ticks=2`(PARAM_RANGES 미편입). 손절 분기 뒤 신규 분기 — 돌파선(`_targets` target_price) 아래 buffer% 로 confirm_ticks 연속 재이탈 시 `STOP_LOSS`(회복 시 카운터 리셋). `_failed_breakout_count` transient(prepare clear + on_position_closed pop). **enabled=False 기본 → byte-identical**. 롤아웃 = 외부 MCP 백테스트 게이트. **Part B** (`_apply_rs_rsi_observe_in_prepare`, C3 미러): DEFAULT_PARAMS `rs_filter_enabled=False`/`rsi_filter_enabled=False`/`rsi_extreme_max=85`(PARAM_RANGES 미편입). `VB_FUNNEL_STAGES` 7→9(step 8 RS/step 9 RSI 관찰). `ta_indicators.rsi/relative_strength` + `get_recent_daily`(DESC→ASC) + 지수 KODEX200(069500). **배제 0**(입력==출력, enabled=True 여도 Phase 1 실배제 미구현) + 보유 protected + 결측/예외 fail-open. RSI 관찰=극단(>85)만. 매매 안전성 8영역 diff 0(Part A default-off + Part B prepare 매수 진입 전). 회귀 43 케이스. 상세 = `src/engine/CLAUDE.md` 사이클 G.
- **사이클 170 (2026-06-20) — 전략 funnel 관찰성 결함 3건 시정 (행위 보존, MEDIUM+LOW)**: funnel = 순수 관찰성 (메모리 `_funnel_steps` + DB `strategy_funnel_snapshots` + UI). 매매 정상 (`list_by_filter` robust). 운영 DB 실측 (donchian 6/19 step1=0/step4=7 논리 불가능). **카드 B (MEDIUM, atomic 일관성)**: `StrategyBase._reset_funnel_steps(stages)` 0-시드 (`stages` 의 모든 `FunnelStage` 를 `survived=[]` count=0 pre-populate) + `_record_funnel_step` in-place upsert (같은 step_no 존재 시 교체, 없으면 append). 5 전략 prepare()+retry 의 `_reset_funnel_steps()` → `_reset_funnel_steps(<STAGES>)` (donchian/BFB/VCP=`FUNNEL_STAGES` / VB=`VB_FUNNEL_STAGES` / LTV=`LTV_FUNNEL_STAGES`, 전략별 2건). 조기반환/실패 run 도 전 단계 0 일관 → step4=7 stale 영구 소멸. scheduler `_auto_capture_funnel_snapshots` + `insert_snapshot` UPSERT 변경 0. **카드 A (MEDIUM, 단계 노출)**: `list_by_filter(return_stage_counts=True)` 신규 keyword (False=현행 list, True=`(filtered, {union_tickers, mcap_tickers, trade_tickers})`). 단일 필터 루프 내 단계별 ticker 누적 (cap 미적용 — 정확 count, 소비처 `_record_funnel_step` 가 survived 200 cap + survived_count 정확 기록). 기존 호출자 전원 미지정 → list (회귀 0). donchian `_scan_universe` `return_stage_counts=True` + `self._scan_stage_counts` 인스턴스 필드 보관 + prepare step1=union (필터 전) / step2=trade (거래대금컷 후, 라벨 "시총+거래대금 컷 통과") → collapse 차단. **카드 C (LOW, step1 표준화)**: VB/LTV step1 `survived=[]` placeholder → `_universe_candidate_tickers` 실제 후보 (`_scan_universe` filtered 보관, `__init__` `[]` 초기화). BFB/VCP step_conditions 구버전 문구 → 실제 소스 (list_by_filter) 정합. step1 의미 통일 = "원천 유니버스 후보 (필터 전)". **매매 안전성 무영향**: scanner/risk.on_tick/order_engine/realtime/auth/api/order.py diff 0. 매수 후보 반환 list 불변 (카드 A 카운트 관찰만, 필터 로직/임계 불변 — 사이클 166/168). check_exit_signal/check_buy_signal funnel hook 0건 (G-C-3 SAFETY). momentum funnel 영구 제외 (사이클 132). 사이클 32 R4/38/132/143/145/153/157 영속. **회귀 가드 36 케이스** (B 8 + A 6 + C 22, HIGH = G-B-3/G-A-1, SAFETY = G-C-3/G-C-4). G-A-1 = `return_stage_counts=True` filtered == False 결과 (원소·순서) 행위 보존 직접 검증. 백엔드 3,117 PASS × 3회 flakiness 0. mock 적응 (production 변경 동행, 의미 전환 아님): cycle119/cycle153 donchian `list_by_filter` mock tuple 반환. `_workspace/red/cycle170_funnel_observability.md` + `_workspace/refactor/2026-06-20_funnel_observability_review.md`.
- **사이클 173 (2026-06-22) — 5 전략 prepare 일봉 source KIS→DB 전환 (HIGH, 매수 target 행위 보존)**: 승인 설계 `/Users/koscom/.claude/plans/funnel-vast-wolf.md` 사이클 173 절 + domain-expert 동등성 자문 `_workspace/domain_consult/cycle173_prepare_db_equivalence.md`. 5 전략 (VB/LTV/donchian/BFB/VCP) `prepare()` 의 `_fetch_one` 일봉 source `fetch_daily_candles(ticker, days=N)` → `get_recent_daily_normalized(ticker, days=N, min_required=M)` (사이클 172 DB 우선 어댑터 + 사이클 173 락/신선도 게이트) 전환. **momentum 제외** (실시간). **전략별 days / min_required 명시 (None 의존 금지, 자문 §4)**: VB `k_period+2(~22)` / 22 · LTV `k_period+2(~22)` / 22 · donchian `~66` / **63 (필수 lookback 61 = long_ma 60+1, 절대 하향 금지 silent 왜곡 차단)** · BFB `~44` / 35 · **VCP `min(ema_long+base_max+10, 100)=100 cap 유지` / 100 (220 미사용, effective_ema_long ≈75 식 변경 0 = 행위 보존, G-VCP-1)**. **donchian 신고가 = 어댑터 candles 단일 source** (사이클 123 `get_donchian_high` 별도 DB 호출 + `db_high_hit`/`db_high_miss` 카운터 폐기, 자문 §249 락 종목 신고가/EMA 혼재 차단 — candles 가 이미 어댑터 DB 우선 + 락/신선도 KIS 폴백 경유 → 단일 source 일관). 정상 종목 = candles=DB → 사이클 123 신고가 동일 (행위 보존). **수정주가 divergence 방어 = 어댑터 락 게이트** (`src/db/CLAUDE.md` 어댑터 절 참조 — DB 윈도우 내 락 1 row 라도 발견 시 KIS 강제 폴백, KIS 추가 호출 0건 탐지). **보존 의무**: 사이클 158 VB/BFB/VCP prepare 0건 재시도 hook + 163 count_active + 32 R4 보유/익일청산 절대 보호 + prev_idx 분기 5 전략 + 170 funnel + 143/157 FUNNEL_STAGES/master_block hook 변경 0. **회귀 가드**: `tests/unit/engine/strategies/test_cycle173_prepare_db_equivalence.py` (AST 전환 5 전략 × 3 + min_required 값 정합 + G-VCP-1~3 + G-SAFETY-1/2 + G-EQ-1 VB 동등성 + donchian 신고가 단일 source = 27 케이스) + `tests/unit/db/test_cycle173_adapter_lock_stale_gate.py` (어댑터 락/신선도 게이트 13). 의미 전환 3건 = 사이클 172 SAFETY-2 (prepare 어댑터 호출 0 → xfail) + SAFETY-3 (raw 추출 헬퍼 위임 정합) + 사이클 123 `test_cycle123_donchian_db_high.py` 모듈 xfail (get_donchian_high 별도 DB 호출 폐기). **매매 안전성 무영향 (HIGH 경로지만 동등성 게이트 통과)**: `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = **0** + prepare 영역 check_exit/buy 호출 0건 (사이클 38 명문화). 변경 6 파일 (어댑터 1 + 5 전략 prepare). 사이클 174+ 인계: VCP 220일 EMA 원설계 복원 (backtest 동반 별도 사이클) + 락 종목 16:00 재backfill (완화책 2, 자문 §258) + `[prepare_db_fallback]` 폴백 빈도 일일 summary 가시화 (완화책 3).
- **사이클 50 (2026-06-01) — BFB 폴/플래그 단계별 사유 정밀화 (계측 전용)**: `bull_flag_breakout._detect_pole_and_flag` 가 실패 시 `None` 만 반환하던 결함(funnel step 5/6 survived=0 AND excluded=0 → 바인딩 조건 계측 불가) 시정. `_detect_pole_and_flag_detailed(candles) -> (result, fail_stage, detail)` 신규 — fail_stage(`pole_return`/`pole_red_ratio`/`flag_retracement`/`volume_contraction`) + 측정 수치. `_detect_pole_and_flag` 은 result 만 반환하는 thin wrapper (**기존 계약/행위 완전 보존**). `prepare()` funnel hook 이 fail_stage 별로 step 4(폴 상승률+음봉)/5(플래그 조정폭)/6(거래량 수축) 에 수치 사유 분배. 임계값/유니버스/DB params 무변경 (단계 2 보류). 회귀 가드 `test_cycle50_bfb_funnel_stage_detail.py` 6 케이스. 실측 스크립트 `tools/measure_bfb_pole_flag.py` (EC2 실행)

## 멀티데이 보유 전략

`Position._MULTIDAY_STRATEGIES` — `is_next_day` 항상 False, OrderMonitor "청산" 배지 미표시. 추가 시 frozenset 리터럴 멤버만, `Position` 시그니처 변경 금지. **코드 정본(2026-07) = `frozenset({"donchian_swing", "vcp_breakout", "kojiro"})`** (3 전략 모두 `strategy_base.py` 리터럴에 정적 선언 — vcp 가 과거 import 시점 동적 side-effect 로 추가하던 취약 패턴을 리터럴로 통합, import-order 독립). 추가 시 `check_force_clear()==[]` 결합 필수 (편입만 하고 force_clear 미구현 → 15:20 강제청산으로 멀티데이 소멸).

## 안전 규칙

- **계좌 SOFT Σ상한 게이트 (cycle233, 2026-08-29 — 다크런치)** — 7전략 `check_buy_signal` 이 `StrategyBase._account_soft_gate_blocked(ticker)` 를 경유한다(AST 가드가 전수 강제). **위치 이원화가 계약**: 폴/래치형 5전략(donchian/LTV/BFB/VCP/kojiro) = **첫 문장** / edge-crossing 2전략(momentum/VB) = **발사 직전**(`return Signal.BUY` 앞) — 최상단에 두면 block 구간 동안 `_prev_price`/`_prev_prdy_rate` baseline 갱신이 동결돼 순간 게이트(양방향) 해제 후 첫 틱이 **거짓 돌파**가 된다(적대 검증 C233-F1, AST 가 최상단 배치를 금지). 게이트는 신규 매수 신호만 차단 — 청산·손절·트레일링·익일청산은 구조적으로 무관. fail-open(판정 실패 → False). 다크런치 = DB `account_risk_block_pct` 부재 시 항상 False. 신규 전략 추가 시 이 게이트 1줄 + `get_effective_stop_price` read-only 미러(보유형이면) 배선 의무.
- **`get_effective_stop_price(ticker)` read-only 미러 (cycle233 척도 병기)** — 보유형 4전략(kojiro/donchian/VCP/BFB)이 자신의 check_exit 가격선들의 max 를 노출(가격 무관 청산 — 시간·stage3·measured-move — 은 모델 제외). **read-only 계약**: 래치 set·`_stop_floor`·로그 무변조. VCP/BFB 는 `_effective_setup(ticker, observe=False)` 경유 — observe=True 로 부르면 watcher(5분 주기)가 `[setup_structure_conflict]` cap 을 선소비해 cycle228-B 마커의 "청산 평가 문맥" D+1 귀인이 무너진다.
- **VB·momentum 매수 컷 15:20 (`BUY_CUTOFF_KST` 모듈 상수, cycle229 2026-08-28)** — 15:20~15:30 은 KRX 장후 동시호가로 **시장가 호가가 접수**되므로(15:20 강제청산 매도가 방증) VB 매수가 체결되면 오버나잇 확정이고, 15:30 랜덤엔드 확정 종가 틱은 허위 edge-crossing(+29% = 상한가 잠금 실패 마감 표본)을 만든다. 게이트는 `check_buy_signal` **최상단·상태 무갱신·KST 명시**(naive 금지). **DB override 불가 — DEFAULT_PARAMS/PARAM_RANGES 편입 금지**(OVERNIGHT 금지는 토글로 뚫리면 안 되는 규칙). 관측 `[vb_buy_cutoff]`/`[momentum_buy_cutoff]` 1회/일. `[단일가매매]` msg1 변형은 `balance.py` 분류기가 `is_market_order_disallowed` 로 흡수(매도 step_down 폴백 경로).

- **VB/LTV/BFB/VCP 후보 WebSocket 구독 우선순위** — `subscribe_filtered_stocks(priority_groups=...)` 의 `breakout` 그룹: LOW+bypass_limit=False (보조 세션 분산). **사이클 48 (2026-05-27)**: `scheduler._collect_breakout_tickers()` 가 4 돌파 전략(VB/LTV + bull_flag_breakout/vcp_breakout)을 순회 → BFB/VCP 후보도 동일 `breakout` LOW 그룹으로 편입. BFB/VCP 는 폴링 루프 없이 `risk.on_tick` 으로만 매수 평가하므로 이 구독 없이는 0건 지속(PR #15 P1). `_resubscribe_stale_priority` 의 stale 재구독도 positions/next_day_clear 소속이 아닌 후보는 LOW (사이클 25-B, 2026-05-20). 후보 HIGH 메인 집중 → 메인 과부하 → silent inactive 방지
- **VB `DEFAULT_TRADABLE_BOARDS` = ("main",) 유지 (사이클 26)** — KRX ONLY 정책. PRE_NXT 복구 금지 (NXT 갭상승 위험 + SK하이닉스 시가 결함). POST_NXT 추가 금지 (VB OVERNIGHT 보유 결함). DB `strategy_config.params.tradable_boards` 도 함께 갱신
- **LTV `DEFAULT_TRADABLE_BOARDS` = ("pre_nxt", "main", "post_nxt") 복원 (사이클 38, 2026-05-22)** — 사용자 운영 의도 복원. 연속 상한가 종목 익일 청산 모드 + 야간 매수. 사이클 26 KRX ONLY 정책 폐기. DB `strategy_config` 는 운영 중 보존된 3 보드 유지
- **`tradable_boards` 는 매수 진입 전용 (사이클 38 명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 보드 가드 *없이* 항상 작동. `risk.on_tick` 의 `check_exit_signal` 분기가 `session_tracker.is_tradable` 검사 *전* 진입 보장. 6 전략 공통 적용
- **VB 익일 청산 안전망** — `_execute_next_day_clear` 대상 포함. 비상 상황(시세 미수신, 시장가 거부, 재시작 race) 회복용
- **donchian_swing 일중 시세 REST 폴링 (`_swing_rest_poll_loop`) 제거 금지** — 09:30~15:20 KRX 메인 시간대 60s 주기로 보유+스캔 합집합 폴링 → ticker_prices 갱신 + 보유 손절 평가 재사용. WebSocket stale 보강
- 매수 신호는 반드시 "돌파 순간" 감지 (이전 틱 < 기준가 AND 현재 틱 ≥ 기준가)

## 사이클 23 파라미터 확장 (2026-05-20)

### BFB `breakout_retention_minutes` (P2-1)
- 기본 3분. 첫 돌파 감지 → `_breakout_first_seen[ticker]=now` 등록 + NONE. 경과 후 BUY 발사.
- 가격 후퇴 시 dict pop. `_reset_daily_state()` 에서 clear.
- `DEFAULT_PARAMS["breakout_retention_minutes"]=3`. `PARAM_RANGES["breakout_retention_minutes"]=(1,30)`. `INT_PARAMS` 등록.
- 기존 동작 회귀: `retention_minutes=0` 이면 즉시 BUY (기존 테스트 픽스처 활용).

### BFB `min_trade_amount_failed` scan_stats (P1-2)
- `_empty_scan_stats()` 키 추가. `_scan_universe`에서 시총 통과 + 거래대금 미달 시 증가.

### VCP `mcap_pass` scan_stats (P1-3)
- `_empty_scan_stats()` 키 추가. `_scan_universe`에서 시총 통과 시 증가.

### donchian `breakout_fail_n_days` (P2-2) — **사이클 223 (2026-08-21): 영업일 기준 + 재도출 off-by-one 시정 + PARAM_RANGES 제외**
- 기본 5일. `check_exit_signal` 에서 보유 N**영업일** + 현재가 < `_breakout_high[ticker]` → STOP_LOSS.
- **보유일 = 영업일** (사이클 223). 이전 `(today - buy_date).days` 달력일은 주말·연휴를 보유일로 세어 청산을 최대 2~3일 앞당겼다. `_business_days_held()` 가 `_trading_days` 캐시(일봉 union, **KIS 추가 호출 0**)로 계산하고, 캐시가 아직 오늘을 못 담은 구간만 하루 가산(주말 제외).
- `_breakout_high`: 매수 신호 발사 시 donchian_high 등록. graceful skip (0이면 분기 진입 안 함). 재시작 복구는 `_rederive_breakout_high` 담당
- **돌파선 0 방어 3중 (사이클 226)** — 상류에서 하류까지 같은 사고의 세 지점을 막는다.
  **(D-1)** `prepare()` 가 `prior_high <= 0` 이면 후보를 **거부**한다 + `[donchian_zero_breakout_line]` **WARNING**.
  이전엔 `prev_close <= prior_high` 만 봐서 `prior_high == 0` 이 **아무 양수 종가나 통과**했다 =
  20일 신고가 돌파를 **검증하지 않고** 후보가 만들어졌다. 돌파선 0 은 "돌파했다" 가 아니라 "계산하지 못했다" 다.
  탈락 사유는 정상 미달과 **문자열이 달라야** 한다(funnel step5 에서 구분).
  **(D-2)** 재도출 진입 게이트를 **값 기준**으로 — `_breakout_high[t] == 0` 이 멤버십 판정에서 "무장됨" 으로
  오판돼 **영구 미복구**였다. 시간청산 게이트(`breakout_high > 0`)·사이클 224/225 관측기와 **같은 축**이다.
  ⚠️ 이 변경으로 사이클 225 의 "행위 변경 0 — 재도출을 억지로 호출하지 않는다" 는 **값 0 경로에 한해 갱신**됐다:
  값 0 이면 이제 재도출을 **시도**한다(복구 전용 — 매수를 만들지 않는다). `reason=not_called` 는 다시 도달 불가.
  ⚠️ 게이트의 값 읽기는 `isinstance` 정규화다 — `int()` 를 조건식에서 부르면 **try 밖 예외 지점**이 생겨
  뒤 보유 종목의 `_channel_low`·`_entry_atr`·고점 보정이 통째로 유실된다(청산 약화 방향).
  **(D-3)** `src/db/stock_master_daily.py::_extract_raw` 가 `raw` 부재로 row 자체를 반환할 때
  `[daily_raw_missing]` 흔적. 그런 row 는 KIS 원본 키가 없어 `prepare` 의 `int(c.get("stck_hgpr","0"))` 가
  0 을 내고 그게 곧 D-1 사고의 **상류**다. ⚠️ 이 함수는 donchian 전용이 아니다(kojiro·VCP·BFB 공유) —
  호출당 1행 + 1회/ticker/일 cap. 반환값 불변(`is` 동일성 고정).
  **판독법**: 두 마커 동시 = 같은 사건(고가 결손 → 돌파선 0). D-3 단독 = 다른 전략 쪽 일봉 열화.
  ⚠️ **현재 잠복**이다 — 일봉 writer 가 `raw` 를 항상 저장하고 라이브 샘플도 전부 보유였다.
  D-1 의 실제 표면은 "종가는 살고 **고가만** 결손" 인 부분 결손 row 뿐이다(완전 정규화 row 는
  `stck_clpr` 부재로 기존 `prev_close <= 0` 가드가 먼저 잡는다). — **`prior[1:period+1]`** 로 `prepare()` 의 `prior_high = max(highs[1:period+1])` 과 **같은 창**을 본다(사이클 223 off-by-one 시정. 이전 `prior[:period]` 는 한 칸 어긋난 돌파선을 복구해 재시작 전후로 청산 임계가 달라졌다).
- **`PARAM_RANGES`/`INT_PARAMS` 제외** (사이클 223) — 청산 정체성 상수. 자동 자문뿐 아니라 **수동 적용 라우트**(`routes/recommendations.py`)도 같은 정본을 참조해 차단한다(한쪽만 막으면 제외가 아니다).
- 기존 ATR 트레일링/하드 손절 보존, 추가 분기만.
- **복구 경로 침묵 4층 관측화 (사이클 225)** — `_breakout_high` 가 재시작 후 무장되지 않는
  경로가 전부 무로그였다. 2026-08-24 장중 재배포 때 `192820` 이 `breakout_high=0` 으로
  남았는데(cycle224 `[days_held_observe]` 의 그 필드가 **유일한 흔적**이었다) 원인 규명에
  코드를 손으로 따라가야 했다. 신설 로그 = `[held_recompute_skip]`(1층: `recompute_held_atr`
  게이트 `continue`, fetch **앞**) · `[donchian_breakout_high_rederive_skip]`(2·3층:
  `insufficient_prior` / `zero_high`) · 4층 `reason=no_candles|no_buy_date|no_position`
  (게이트 `pos and buy_date and candles and ...` 가 falsy 라 재도출에 **진입조차** 못 한 경우).
  ⚠️ 4층이 특히 중요하다 — 그 경로는 상위 게이트를 통과한 뒤라 `buy_date < today` 이고,
  `days_held` 가 계속 자라는데 시간청산은 `breakout_high > 0` 에 막혀 **영구 미발화**한다
  (`fetch_daily_candles` 는 빈 `output2` 에 예외 없이 `[]` 를 돌려주고 5분 캐시에 박는다).
  발화 조건은 **미복구일 때만** — 무장된 정상 skip 을 매일 찍으면 신호가 희석된다.
  무장 판정은 **값(`> 0`)** 이다(멤버십 아님) — 시간청산 게이트·`[days_held_observe]` 와 같은 축.
  cap = A 는 `ticker`, B/4층은 `ticker|reason`(사유별 대응이 갈리므로 한 사유가 다른 사유를
  삼키면 안 된다), 실패 흔적은 `ticker|__observer_failed__`. 실패는 흡수하되
  `logger.debug(exc_info)` + **WARNING 1행**(debug 단독은 `_DbLogHandler` INFO 컷에 막혀
  `system_logs` 에 도달하지 않아 도입 이전 무음과 구별되지 않는다). 행위 변경 0 — 재도출을
  억지로 호출하지 않는다(게이트가 fetch 앞에 있는 이유가 KIS 호출 절약이다).
- **`[days_held_observe]` 상시 관측** (사이클 224) — 보유일을 **발화 여부와 무관하게** 하루 1회 남긴다.
  이전엔 `days_held` 가 (a) 폴백 플래그가 섰거나 (b) 시간청산이 **실제 발화**했을 때만 로그돼,
  *시간 기반 청산인데 발화할 때만 보유일이 보이는* 상태였다 — "얼마나 근접했나"를 영영 못 본다.
  실측 사각: 금 매수·`n_days=2`·캐시 최신일=매수일인 월요일은 `days_held=1`(달력 3)로 게이트 미충족이고
  `cache_max == _prev_weekday(today)` 라 폴백도 안 서서 **완전 무음**이었다.
  한 줄에 **영업일과 달력일을 나란히** 싣는 것이 목적 — `days_held=1 calendar_days=3` 이 곧
  사이클 223 S3(달력일→영업일)의 직접 확인이다. `days_ok`/`price_ok` 를 각각 실어 어느 조건이
  막는지 가린다. 호출은 `check_exit_signal` **최상단**(§1 하드손절보다 앞) — §2.5 안에 두면
  하드손절이 그날 첫 평가에 발화할 때 도달조차 못 하고, 매도 거부로 포지션이 생존하면 **영구 억제**된다.
  cap 키는 `ticker|armed`/`ticker|disarmed` (최대 2행/종목/일) — ticker 단독이면 장중 재시작 시
  재도출 전 `breakout_high=0` 스냅샷이 박제돼 종일 무장 해제로 오독된다. 실패는 흡수하되
  `[days_held_observe_failed]` debug 흔적을 남긴다(무흔적 흡수는 사이클 224 이전 무음과 구별 불가).
- **청산 계열 로그 폭주 cap** (사이클 237, 2026-09-02) — `[donchian_breakeven_promote]` 와
  `도치안 시간 기반 청산` 을 각각 **1회/ticker/일**(`_emit_breakeven_promote` / `_emit_time_exit`).
  실측 = 승격 로그가 08-31 **11,453건** · 09-01 **9,027건**(각각 그날 `system_logs` 의 36.9% / 51.0%,
  전부 **단일 종목 192820**). 근본은 **래칫 부재**다 — kojiro 는 승격 결과를 `_stop_floor` 에
  영속해 다음 틱 `promoted == eff` 로 자연 1회지만, donchian 은 `base_stop` 을 매 틱
  `buy − stop_atr×entry_atr` 로 재계산하므로 `promoted_stop != base_stop` 이 **영원히 참**이다.
  승격 자체는 매 틱 올바르게 일어난다(결과 동일) — 잘못된 건 로그뿐이다.
  시간청산은 신호와 짝이라 정상 흐름 1회지만, **매도가 거부되면**(034020 = 프리마켓 APBK0918)
  포지션이 잔존해 매 틱 재발화한다(09-02 68건). 매도 실패 사실은 `[market_closed_blocked]` 가
  따로 1회/일 기록하므로 관측 손실이 없다.
  ⚠️ **cap 은 로그에만 건다 — 행위는 cap 밖이 계약**: 승격 대입 `base_stop = promoted_stop` 과
  `return Signal.STOP_LOSS` 는 cap 성패와 무관하게 매 틱 수행된다. cap 이 신호까지 삼키면
  매도 거부 후 재시도가 끊겨 포지션이 청산되지 못한 채 잔존한다 = 관측 시정이 아니라 **결함 주입**
  (뮤테이션으로 실증 — 신호를 cap 에 종속시키면 TE-2 가 FAIL).
  두 cap 은 기존 5개와 **별개 인스턴스**(OB-11), 날짜 키 자기 리셋, peek→로그→mark(cycle226 D-3),
  예외 전량 흡수 + debug 흔적, 메시지 서식 **byte 동일**(운영 grep 연속성).
  **kojiro 무접촉** — 위 래칫으로 구조적으로 폭주하지 않는다(다크런치라 0건인 것과 별개 이유).
  관측기 자기 실패는 `logger.debug` 단독이 아니라 **`observer_trace.trace_observer_failure(…, dest_logger=logger)`**(cycle225 J-3 의 `_trace_observer_failure` 메서드를 cycle258 이 모듈 함수로 승격)로
  보낸다 — debug 단독은 `_DbLogHandler`(INFO 컷)를 못 넘어 `system_logs` 에 도달하지 않고,
  그러면 도입 이전 무음과 구별되지 않는다(적대 검증 C237-L2-1).
  ⚠️ **판독법 — 시간청산 로그의 첫 타임스탬프가 09:00 이전이면 프리장 게이트 이상 신호**다.
  donchian 은 `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES`(LTV 단독) **밖**이라 PRE_NXT 단독 구간엔
  청산 평가가 보류돼야 한다. 09-02 실측 = 시간청산 첫 발화 **08:00:00** vs
  `[pre_market_exit_deferred]` 첫 발화 **08:00:29** ⇒ `_session_loop` 30초 주기 탓에 08:00 정각엔
  `active` 에 PRE_NXT 가 없어 게이트가 **fail-open** 하는 **~30초 구멍**이 매일 존재한다.
  그 창에서 실제 매도 주문이 나갔고 APBK0918 로 거부됐다(NXT 거래가능 종목이면 체결됐을 수 있다).
  **별도 결함 — ✅ cycle238 (2026-09-02) 로 시정** (`risk._defers_pre_market_exit` 에 `boards_at(_now_kst())` 시각 폴백 OR 결합 — 상세 `src/engine/CLAUDE.md` 프리장 게이트 절). cap 은 그날 **첫** 발화를 남기므로 이 신호(09:00 이전 첫 발화 = 게이트 이상)는 cycle238 이후에도 D+1 판독 채널로 유효하다.
  잔여 후속 = 같은 구조지만 실측 0건인 `도치안 스윙 손절`·`[donchian_turtle_stop]`·
  `[donchian_turtle_backstop]`·`[donchian_channel_exit]`·`도치안 스윙 트레일링`
  (매도 거부가 길어지면 동일 폭주 — TE-4 픽스처 작업 중 손절 로그 5회 반복이 실증됐다).

### donchian `max_breakout_extension_pct` (P2-3) — **사이클 209 (2026-07-14): 기본 3.0→4.0, PARAM_RANGES 제외**
- 기본 **4.0%** (사이클 209 — 0.5%(AI 과튜닝, DB) 상시 스킵 병목 해소). `check_buy_signal` 갭 스킵 *후*, BUY 확정 *전* 삽입.
- `daily_high = max(stck_hgpr, high_price, current_price, open_price)`. `ext_pct = (daily_high - donchian_high)/donchian_high*100 > max_ext` 이면 NONE (추격 금지).
- **구조적 주의**: donchian 후보 = "전일 종가 > donchian_high(어제 제외 20일 신고가)" = 등록 순간 이미 돌파 → 오늘 기준가 위 시작 → extension 하한이 이미 양수. 따라서 `max_breakout_extension_pct ≥ gap_skip_threshold`(4.0≥3.0) 불변식 필수 (0.5%는 갭 통과 종목도 상시 차단 = 모순). AI 자동튜닝 제외(진입 임계=전략 정체성 상수, 사이클 198/208 선례). DB 값 우선 → 변경 시 strategy_config.params 동반 UPDATE 필수.
- 기존 `gap_skip_threshold`(3.0, 시가 갭) 와 별개 (당일 고가 추격 상한).

### donchian `box_contraction_period` + `max_box_volatility_pct` (P2-4) — **사이클 208 (2026-07-13) 완전 제거**
- ~~기본 10일, 5.0%. `prepare()` ATR 통과 후 박스 수축 필터.~~ **제거됨.**
- **제거 사유 (domain-expert 자문 `_workspace/domain_consult/cycle_donchian_box_contraction.md`)**: "20일 신고가 돌파"(추세 상승 → 최근 박스 넓음)와 "12일 박스 ≤임계 초압축 횡보 요구"는 앞단·뒷단이 반대 종목을 선호 → 교집합 거의 공집합 = donchian 최종 후보 상시 0 (2026-07-13 KB금융/금호타이어 step8=2→step9=0). VCP/BFB 와 역할 중복. 페이크 돌파 방어는 청산 규칙(ATR×2 트레일링/-7% 하드/`breakout_fail_n_days`/`max_breakout_extension_pct`)이 담당 → 제거 리스크 무손상.
- 삭제: 필터 블록(prepare) + DEFAULT_PARAMS 2키 + `_scan_stats["box_contraction_pass"]` + PARAM_RANGES/INT_PARAMS 2키(자동튜닝 제외 = 박스 폭은 손익 튜닝값 아닌 전략 정체성 상수, AI 5.0→3.2 과적합 조임 차단, 사이클 198 flag_lookback_min 선례). 매매 안전성 8영역 diff 0 (prepare 매수 진입 전, 사이클 38). check_exit_signal/ATR/신고가/EMA/거래대금 필터 불변.

### VCP PARAM_RANGES 화이트리스트 (P1-1)
- `base_depth_pct(0.10,0.50)` / `volume_contraction_ratio(0.30,1.00)` / `breakout_volume_mult(1.0,5.0)` / `last_pullback_max(0.03,0.15)` 추가.
- P2 신규 5 키 중 3키(`breakout_retention_minutes`/`breakout_fail_n_days`/`max_breakout_extension_pct`) PARAM_RANGES/INT_PARAMS 등록. box 2키는 사이클 208 제외.

## 새 전략 추가
1. 본 디렉토리에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `scheduler.py` `__init__` 에 `registry.register()` 추가
3. 필요 시 `scanner.py` 에 스캔 함수 추가
4. 본 표 + `_workspace/00_leader_trading_rules.md` 에 명세 추가

> **cycle258 (2026-09-05) — donchian 관측기 자기 실패 정본 경로**: `_trace_observer_failure` 메서드(cycle225 J-3)는 삭제되고 `src/engine/observer_trace.trace_observer_failure(marker, ticker, cap, dest_logger=logger)` 로 승격됐다(8/8 사이트 C 형태). cap 필드 7개는 `KstDailyEmitCap`(날짜 자기 리셋 내장)이라 `_x_day` 필드가 없다. 정상 마커 서식 byte 불변, 실패 흔적은 `observer_failed` 토큰(D+1 grep 축 신규).
