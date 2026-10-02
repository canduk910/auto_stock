# cycle399 — 공통 섀도 모드 `shadow_mode` (리팩토링 카드 #9)

> 사용자 승인 2026-10-02 R1 (`_workspace/design/2026-09-27_etf_trend_strategy.md` §10.2) — 8영역
> `src/engine/strategy_registry.py::update_weights` 한 줄 포함. 명세 근거 =
> `_workspace/domain_consult/cycle398_refactor_cards_2_3.md` §3(c) · `_workspace/refactor/2026-09-27_strategy_add_remove_structure.md` 카드 #9.

## 1. 행위 (검증 가능한 단위)

| # | 행위 | 테스트 |
|---|---|---|
| B1 | 7전략 `DEFAULT_PARAMS["shadow_mode"] is False` — 기본은 현행 그대로 | `test_cycle399_shadow_mode_gate.py::t01` |
| B2 | `shadow_mode is True` 면 실전이면 BUY 였을 평가가 `Signal.NONE` 을 돌려준다 | `t02` (양성 대조 `t02_positive`) |
| B3 | 그 순간 `[shadow_buy]` INFO 1줄 — 종목당 KST 하루 1회. 다음 날 다시 1회 | `t03` · `t04` |
| B4 | 섀도 BUY 는 전략 상태를 바꾸지 않는다 — `buy_signals`(화면) · `_bought_today` · 진입 스탬프(`_breakout_high`·`_position_setup`·`_position_atr`·`_position_sectors`) · 래치 · `pending_buys` · `signal_count_today` | `t05` |
| B5 | 막는 자리 = **신호 계산 뒤**. 앞 관문(종목상태 → `buy_paused` → 계좌 SOFT → 신호 → 시장 유닛)이 먼저 이기면 `[shadow_buy]` 도 없다 | `t06` |
| B6 | `is True` 만 켜짐. `"true"`·`1`·`None` 등은 꺼짐(실전 그대로 BUY) + `[shadow_mode_config] valid=0` WARNING. 키 부재는 꺼짐·무음 | `t07` |
| B7 | 매 호출 `config.params` 를 읽는다 — PUT 즉시 반영(재시작 없음) | `t08` |
| B8 | 청산 무접촉 — 섀도 켬/끔에서 보유분 청산 신호·청산 상태가 같다 | `t09` |
| B9 | `risk.on_tick` — 섀도 전략의 BUY 는 `execute_buy` 로 가지 않고, 보유분 손절은 나간다 | `t10` |
| B10 | 수량 경로 무접촉 — `calc_buy_quantity` 는 섀도 켬/끔에서 같다 | `t11` |
| W1 | `update_weights`: 섀도 켜짐 ∧ 지금 `enabled` 이면 비중 0 이어도 `enabled` 유지. 섀도 아닌 전략은 `weight > 0` 현행 그대로. 꺼져 있던 섀도 전략을 켜지는 않는다 | `test_cycle399_shadow_weights.py::w01~w05` |
| W2 | `allocate_funds`: 비중 0 섀도 전략 예산 0, 다른 전략 예산은 섀도 전략이 없을 때와 같다 | `w06` |
| W3 | `save_weights(weights, keep_enabled=…)` — `keep_enabled` 에 든 전략만 비중 0 이어도 DB `enabled=True` | `w07` |
| W4 | `PUT /api/strategies/weights` — 섀도 전략 비중 0 저장 뒤 메모리·DB 모두 `enabled=True`. 섀도가 없으면 `save_weights(weights)` 호출 모양 그대로 | `w08` · `w09` |
| W5 | 보유가 있는 섀도 전략의 비중 0 은 여전히 거부(`[weight_zero_guard]`) | `w10` |
| W6 | AI 자문 수동 적용의 비중 0 도 섀도 전략이면 DB `enabled` 를 지킨다 | `w11` |
| P1 | `PUT /params {"shadow_mode": true}` 즉시 반영 · bool 아니면 422 `type_mismatch` · AI 자문 두 경로가 못 바꾼다 | `tests/contract/test_cycle399_shadow_mode_route.py` |
| A* | 구조 봉인 — 모든 BUY 반환이 섀도 관문을 지난다(아래 §3) | `tests/unit/ast/test_cycle399_ast_shadow_mode.py` |

## 2. 결정 (명세와 다른 점 · 이유)

- **`[shadow_buy]` 에 설계 수량을 싣지 않는다.** 명세(cycle398 §3(c)·ETF 설계 §7.1)가 「가상 수량은 엔진에서
  계산하지 않는다 — 예산 0 이라 0 이 나온다. 가격·ATR·m·돌파선만 남기고 오프라인에서 가정 예산으로 계산」이다.
  `calc_buy_quantity` 를 신호 단계에서 부르면 사이징 관측 마커(`[budget_clamp]`·`[oversized_fallback]`·
  `[market_unit_calc]`)가 실전 매수처럼 찍혀 오귀인된다. 마커 칸 = `strategy= ticker= price= open= level= board=
  atr= m= mu_state=`.
- **`update_weights` 유지 조건에 「보유 0」 을 넣지 않는다.** 자문 원문은 「`shadow_mode is True` ∧ 보유 0」 이지만,
  보유가 있는 섀도 전략에서 그 조건이 거짓이면 `enabled=False` = 손절 정지(루트 금기)로 간다. 보유 중 비중 0 은
  라우트 두 곳(`[weight_zero_guard]`)이 이미 거부하므로, 유지 조건은 「섀도 켜짐 ∧ 지금 켜져 있음」 만으로 둔다 —
  어느 경우에도 `enabled` 를 끄는 방향으로 바뀌지 않는다.
- **꺼져 있던 섀도 전략을 비중 저장으로 켜지 않는다**(`was_enabled and …`). 켜는 것은 지금처럼 비중 > 0 또는
  운영 DB 조작이고, 섀도 S1 진입은 DB UPDATE 승인 절차를 따른다(ETF 설계 §7.1).
- **DB `save_weights` 는 호출자가 메모리 판정을 넘긴다(`keep_enabled`).** DB 행 `params` 만 보면 코드 기본값으로
  켜진 섀도(행에 키가 없다)를 놓친다. 섀도가 없을 때 라우트는 지금과 같은 `save_weights(weights)` 를 부른다.
- **AI 자동 적용(`auto_apply_recommendations`)은 손대지 않는다** — 그 경로는 감액만 하고 `max(rw, current × 0.5)`
  라 비중 0 을 쓰지 못한다(현재 비중 0 이면 「증액 차단」 으로 통째로 건너뛴다).

## 3. 막는 자리 — 7전략 전수표 (BUY 반환 직전 상태 변경)

모든 전략의 `return Signal.BUY` 는 파일마다 1곳이다. 섀도 관문
`if self._shadow_buy_intercepted(ticker, current_price, open_price, …): return Signal.NONE` 은 **마지막 거름 뒤 ·
상태 변경 앞**에 둔다.

| 전략 | 섀도 관문 직전의 마지막 거름 | 관문 뒤(섀도에서 일어나지 않는 것) |
|---|---|---|
| momentum | 계좌 SOFT(발사 직전) | 매수 로그 · `buy_signals` |
| volatility_breakout | 09:00 진입 보류(`_open_entry_hold_elapsed`) | 매수 로그 · `buy_signals` |
| long_tail_volatility | 15:20 main 컷(`_main_buy_cutoff_blocked`) | 매수 로그 · `buy_signals` |
| donchian_swing | 시장 유닛 거름 | `_bought_today` · `_breakout_high` · 로그 · `buy_signals` |
| bull_flag_breakout | 시장 유닛 거름 | `_vol_latch.pop` · `_bought_today` · `_position_setup` · `vol_gate_pass` · 로그 · `buy_signals` |
| vcp_breakout | 시장 유닛 거름 | `_vol_latch.pop` · `_bought_today` · `_position_setup` · `vol_gate_pass` · 로그 · `buy_signals` |
| kojiro | 시장 유닛 거름(갭 관측 `pass` 뒤) | `_bought_today` · `_position_atr` · `_position_sectors` · 로그 · `buy_signals` |

`_bought_today` 를 찍지 않으므로 같은 종목은 다음 평가에서 다시 BUY 판정에 닿는다 — 섀도 관문이 `Signal.NONE`
을 계속 돌려주고 `[shadow_buy]` 는 하루 1회 cap 이 막는다(실전의 「한 번 사면 그날 끝」 과 같은 횟수).

AST 봉인: 전략 명부 파일마다 (a) `Signal.BUY` 는 `return Signal.BUY` 로만 (b) 그 Return 의 같은 문장 목록 안
앞쪽 형제에 섀도 관문 `If` 가 있고 그 사이에 다른 `return`/`raise` 가 없다 (c) 시장 유닛 거름이 있는 파일은
그 `If` 가 섀도 관문보다 앞 (d) 섀도 관문 호출은 파일마다 1곳.

## 4. 실행 기록

- **Red**(구현 전) — 새 테스트 160 중 108 failed · 52 passed. 통과 52 는 현행을 못박는 양성 대조·불변식(t02 양성 대조 7 ·
  t06 앞 관문 우선 · t09 청산 무접촉 · w02~w05 현행 규칙 · S07·S08·S10 등)이다.
- **Green** — 새 테스트 162 passed(검토 반영 S01 별칭 검사 포함). Green 중 테스트 결함 2건 수정: (1) BFB·VCP 는 BUY 가
  `_evaluate_vol_gate` 안에서 나므로 S02·S03 을 「BUY 를 돌려주는 함수」 기준으로 고침 + 관문의 `open_price` 를 선택 인자로
  (그 헬퍼에 시가가 없다 — `open=-`) (2) t06 「신호 미충족」 을 donchian 돌파선 아래 가격으로 잡았는데 donchian 은 장중 가격으로
  돌파를 다시 보지 않는다(후보 = 전일 확정 돌파) — 진입창 밖 시각·edge 미교차로 바꿈.
- **재핀** — 파일 sha 핀(전략 7 · strategy_base · registry · param_catalog) · 세그먼트 sha 핀(`check_buy_signal` 5 ·
  `DEFAULT_PARAMS` 7) · 키 집합·개수(106 · identity 19 · `cycle399.1` · kojiro 46 · LTV 32) · 8영역 승인 핀 4곳 + 명시 승인
  목록(cycle276 c6_4c) · `_SRC_TREE_DIGEST`. 모두 「🔁 cycle399 재핀」 주석.
- **독립 검토**(읽기 전용 1회) — 주문이 나가는 경로 0 확인. 반영: 끄는 순서(비중 0 인 채 끄면 켜진 채 예산 0 → 900초 오귀인)
  문서화 · 기록 ≠ 실전 포트폴리오(max_positions·업종 상한·예산 미적용) 문서화 · BFB·VCP 래치 미소비로 늘어나는 관측 로그 문서화 ·
  S01 에 `Signal` 별칭 우회 차단 · 카탈로그 도움말 「켜져 있는 섀도 전략」 한정어. 반영하지 않음: 판정 읽기 예외 시 섀도로
  간주(fail-safe) — 명세 B6 「판정 실패 = 실전 그대로」 를 바꾸는 결정이라 남은 한계로 둔다(예산 0 섀도 전략은 수량 0).
- **돌연변이** 14/14 붉음(cp 백업 → 변형 → 4 파일 실행 → 복원, sha 대조).
