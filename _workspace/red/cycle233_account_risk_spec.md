# cycle233 — G3′ 계좌 리스크 패키지 (척도 병기 + SOFT Σ상한 다크런치 + oversized 관측)

> 근거: `_workspace/domain_consult/cycle232_risk_control_review.md` (사용자 결정 2026-08-29 — 자문 권고 패키지 채택).
> **행위 변경 0 이 계약**: 척도 병기 = 관찰 전용 / SOFT 차단 임계 = DB 키 부재 시 비활성(다크런치) /
> oversized = 관측만(수량 불변). 드로다운 정지선·StrategyState.buy_block_reasons 는 다음 사이클(입출금 보정 선행).
> 8영역(risk.py·order_engine.py·realtime/·auth/·api/order.py·session.py·scanner.py·strategy_registry.py) diff 0.

## 설계 확정 (사실 조사 반영)

| # | 모듈 | 내용 |
|---|------|------|
| M1 | `portfolio_risk.py` | `compute_portfolio_risk_snapshot(..., stop_price_of=None)` — None 이면 **기존 반환 byte 동일**(기존 테스트 보존). 제공 시 per-position 실효 리스크 = `qty × max(0, buy − stop)`(stop ≥ buy → **0**, 자문 §정정2 — 확정 이익 상쇄 금지·음수 금지) + `effective` 키(`total_open_risk_effective_won`/`open_risk_effective_pct_of_net`/`effective_ratio`/`coverage`) + `by_strategy[sid]["risk_effective_won"]`. stop None/예외/≤0 → **프록시 폴백**(coverage 미계상). 신규 `compute_over_cap_positions(strategies)` — 별도 함수(스냅샷 계약 무접촉): cap=`int(budget×position_ratio)`, notional>cap 만 `{strategy_id, ticker, notional_won, cap_won, over_ratio}` |
| M2 | `db/system_config.py` | `get_account_risk_warn_pct()`(기본 **4.0** — 관측 경보 상시) + `get_account_risk_block_pct()`(기본 **None** — SOFT 차단 다크런치, DB `{"value": x}` 한 줄로 활성). graceful — 예외 시 기본값 |
| M3 | `account_risk_guard.py` 신규 leaf | 순수 판정 `evaluate_soft_gate(open_risk_pct, *, warn_pct, block_pct) -> {"level": ok\|warn\|block, "reasons"}`. block_pct None → block 불가. pct None/음수 → ok(fail-open). DB/HTTP/registry/scheduler import 0 (AST) |
| M4 | `account_risk_watcher.py` 신규 | scheduler 인자 패턴(boot_manager 선례). `run_account_risk_watch_once(scheduler)` = registry.all() + `get_balance()` net_asset + `extract_hard_stop_pct` + 전략 `get_effective_stop_price` 클로저 주입 → M1 스냅샷 → M2 임계 → M3 판정 → 모듈 게이트 상태 갱신. **Σ상한 = 순간 게이트(양방향 재계산)** — `buy_disabled` **절대 미접촉**(D1 이원화 — 일일손실 세팅을 지우는 회귀 원천 차단, AST `buy_disabled` 토큰 0). 실패 = **fail-open**: 게이트 False + `[account_risk_watch_failed]` WARNING(LOUD, 1회/일 cap). 로그 = block 전이 `[account_risk_gate]` WARNING / 해제 INFO / warn `[account_risk_watch] level=warn` WARNING 1회/일 / ok INFO summary 1회/일(over_cap count 동반). `is_soft_gated()` / `get_gate_state()` 노출 |
| M5 | `strategy_base.py` | ① `get_effective_stop_price(ticker) -> int\|None` 기본 None(프록시 폴백 신호) ② `_account_soft_gate_blocked(ticker)` — lazy import watcher, gated → `[account_gate_skip]` 1회/전략/일 후 True, **예외 → False**(fail-open) ③ `_apply_budget_limit` 최종 수량 반환 직전 `_emit_oversized_fallback` — `final_qty×price > int(budget×position_ratio)` 이면 `[oversized_fallback]` INFO 1회/(ticker)/일, **수량 불변·await 0(A-PURE/A-ATOMIC 보존)** |
| M6 | 7전략 `check_buy_signal` 최상단 | `if self._account_soft_gate_blocked(ticker): return Signal.NONE` 1줄(다크런치 상태 = 항상 False = byte 동일 경로). AST 가드가 7전략 전수 강제(신규 전략 누락 차단) |
| M7 | 전략 4종 실효 손절선 미러 | kojiro = `_position_stop_price` 위임 / donchian = §1·§2.6·§2 가격선 max(2ATR base+브레이크이븐 승격, backstop 선, 채널 저가, 샹들리에; 미스탬프 = stop_loss_rate 선) / VCP = max(고정%선, 래치 승격 buy, base_low, 샹들리에, ema50) / BFB = max(고정%선, 래치 buy, flag_low, 샹들리에). **read-only**(래치 set·`_stop_floor` 무변조·로그 무발화). 가격 무관 청산(시간·stage3·measured-move)은 모델 제외(kojiro docstring 선례) |
| M8 | 배선 | `boot_manager.boot()` 말미 — watch 동기 1회(부팅 창 봉합, 자문 §2.5-γ 반례2) + `ensure_watch_loop(scheduler)` 스폰(idempotent — boot 매일 재실행 대비 중복 가드). 주기 평가 = **watcher 자기 종료 루프**(`watch_loop`, 5분, `_running` False 시 ≤60s 자연 종료 = cancel 목록/task_attrs 불요). ⚠️ 1차안(collector loop piggyback)은 **scheduler.py 라인 상한 가드(<4,000L, 실측 3,999L)** 발화로 폐기 — 재비대 가드를 완화하는 대신 배선을 밖으로 옮겨 **scheduler diff 0** 달성 |
| M9 | 소비처 | `routes/portfolio.py` + `log_analysis_engine._build_portfolio_risk_snapshot` 에 stop_price_of·over_cap 배선(관찰 노출) |

## Red 결정적 입력 (자문 §6 + tester 관점)

- **R1 계약 보존**: stop_price_of 미전달 → 스냅샷 키 집합·값 기존과 동일(`effective` 키 부재).
- **R2 척도 병기**: 샹들리에가 매수가 위(stop ≥ buy) → `proxy > 0` ∧ `effective == 0`. stop < buy → `qty×(buy−stop)`. 콜러블 예외 → 프록시 폴백 + coverage 미계상.
- **R3 over_cap**: buy=405,500×1주, budget=789,130, ratio=0.166 → cap=130,995, over_ratio≈3.10 검출. ratio 결측/0 → skip. notional ≤ cap → 미검출.
- **R4 다크런치**: block_pct=None → 어떤 pct 도 block 아님. warn 4.0 경보만.
- **R5 이원/단방향**: 전략 state.buy_disabled=True 로 세팅 → watcher ok 판정 실행 → **buy_disabled 여전히 True**(무접촉). watcher 소스 `buy_disabled` 토큰 0 (AST).
- **R6 fail-open**: get_balance 예외 → `is_soft_gated() == False` + `[account_risk_watch_failed]` WARNING. 조용히 닫히는 구현은 FAIL.
- **R7 게이트 배선**: watcher 게이트 강제 True → 대표 전략 check_buy_signal == NONE. False → 기존 경로 진행. AST — 7전략 전수 호출 존재.
- **R8 oversized**: R3 수치로 `_apply_budget_limit` → **qty 1 유지** + `[oversized_fallback]` ratio=3.10 emit + 같은 날 2회째 무발화. 비초과(ratio 경로) 무발화. 수량이 0이 되는 구현(부속안 ② 오구현) FAIL.
- **R9 부팅 창**: boot() 가 watch 1회 호출(mock 검증) + 예외 graceful. 제거 뮤테이션 검출.
- **R10 미러 정합**: 전략별 대표 시나리오에서 `get_effective_stop_price` == check_exit 임계(허용 오차 int 절삭) + 호출 전후 `_breakeven_latched`/`_stop_floor`/`_partial_exit` 무변조.
- **R11 AST**: 8영역 `account_risk` 토큰 0 / guard leaf import 화이트리스트 / strategy_base 의 watcher import 함수-레벨 / `_api_recovered_collector_loop` 소스에 watch 호출 존재.
- **R12 system_config**: 키 부재 → (4.0, None). `{"value": 6.0}` → 6.0. 예외 → 기본.

## 적대 검증 (3렌즈 11 에이전트, 발견 21 → 확증 6) 시정 내역 — 2026-08-29

| ID | 심각도 | 결함 | 시정 |
|---|---|---|---|
| **C233-F1** | MEDIUM | edge-crossing 2전략(momentum/VB)의 최상단 게이트가 block 구간 동안 baseline(`_prev_price`/`_prev_prdy_rate`) 갱신을 동결 → 순간 게이트 장중 해제 후 첫 틱이 **거짓 돌파**(추격 상한 없는 매수). 잠복(다크런치 무영향) | 게이트를 **발사 직전**(edge-crossing 판정 성공 지점)으로 이동 — baseline 갱신 통과 후 신호만 차단. 게이트 위치 규약 이원화: 폴/래치형 5전략 = 첫 문장, edge-crossing 2전략 = pre-BUY (AST 가드가 양쪽 위치·최상단 금지까지 봉인) |
| **F1** | MEDIUM | VCP/BFB 미러가 `_effective_setup` 경유로 `[setup_structure_conflict]` 발화·cap 소비 — read-only 계약 위반 + cycle228-B 마커의 "청산 평가 문맥" D+1 귀인 훼손(watcher 가 cap 선소비) | `_effective_setup(ticker, *, observe=True)` 파라미터 — 미러는 `observe=False`(병합 동일·관측 부작용만 스킵). 회귀 = 미러 무발화 ∧ 직후 청산 경로 발화(cap 미소비 실증) |
| **F2** | HIGH | G-6 AST 가 `ast.dump` 문자열 검색이라 docstring 의 "_running" 으로 공허(while→if 뮤테이션 = 주기 반복 소멸이 전 스위트 생존) | G-6 를 구조 검사로 교체(최상위 `ast.While` 존재 + While.test 에 `_running` + sleep 조각 내 탈출 If) + **주기 반복 행위 테스트** 신설(run_once ≥2회). 뮤테이션 실증: while→if → 2 테스트 FAIL → 원복 |
| **F3** | HIGH | G-1 이 "호출 존재"만 검사 — bare call(결과 버림) 뮤테이션 통과 + 4전략 행위 테스트 부재 | `_is_gate_if`(Call 이 If.test 안 + body 가 `return Signal.NONE` 단독) + 위치 검사(5전략 첫 문장 / 2전략 pre-BUY) + R7 을 **7전략 전수 parametrize**. 뮤테이션 실증: donchian bare call → FAIL → 원복 |
| **F4** | MEDIUM | 신규 관측기 3곳 전부 mark-before-log — cycle226 D-3 동형(로그 자기실패가 그날 관측을 지움) | watcher `_peek_emit`/`_mark_emitted` 분리 + strategy_base 2곳 mark 를 로그 뒤로 이동. 규약 = peek → 로그 → mark |
| **F5** | MEDIUM | block 전이/재확인 동일 포맷 + docstring "전부 1회/일 cap" 거짓(전이는 무제한) + 실패-해제 무음 | `transition=entered`(cap 밖)/`reconfirm`(1회/일) 분리 + 실패 경로 `released reason=eval_failure` WARNING + docstring 정정. 레벨 단언(WARNING) 테스트 동반(F10) |

LOW 13건 중 반영 = 스테일 서술 정정(watcher docstring piggyback 잔재, F7/C233-F4) · 소비처 fail-open debug 흔적(F8). 잔여 LOW 수용 = C233-F3(donchian 시간청산 제외는 보수 방향) · F3-LOW(watcher 24/7 get_balance +288회/일 — 주말 무해, 필요 시 후속) · F9(watch_failed 에스컬레이션 — cycle231 선례, 후속 후보) · C233-F6(inf 변환) · F4-LOW(A-PURE 범위).
