# cycle449 — BFB·VCP 「슬롯이 찬 동안에도 직전 가격 추적」 (Red 명세)

- 사용자 결정: 2026-10-12 — ① 고치는 방식 = 만석 중에도 가격 추적 ② BFB·VCP 함께
- 근거: `_workspace/domain_consult/2026-10-12_bfb_breakout_volume_mult.md`
- 테스트: `tests/unit/engine/strategies/test_cycle449_slot_full_baseline.py`
- 선례: VB·LTV 09:00 진입 보류 — 「보류 중에도 `_prev_price` baseline 을 갱신한다. 얼리면 해제 뒤 첫 틱이 거짓 돌파」(`src/engine/strategies/CLAUDE.md` 각주 ②)

## 1. 결함

`bull_flag_breakout.py::check_buy_signal` 과 `vcp_breakout.py::check_buy_signal` 은
`if self.is_max_positions(): return Signal.NONE` 이 `_prev_price` read-then-write 보다 앞이다.
슬롯(`max_positions`)이 찬 동안 `_prev_price` 가 갱신되지 않아, 슬롯이 비는 첫 틱에 이미
돌파선(BFB `flag_high` / VCP `base_high`) 위에 있던 종목이 `prev < 돌파선 <= current` 로
「방금 돌파」로 읽혀 바로 매수된다.

실사례 3건 전부 손실 — 10-06 14:06 엑스게이트(다른 종목 매도 1초 뒤) · 10-07 13:39 빛과전자(매도 2초 뒤) ·
09-23 에이치브이엠(매도 15초 뒤 래치 무장).

## 2. 계약 (Green 이 따른다)

두 전략의 `check_buy_signal` 에서 `is_max_positions()` 가 참이라 `Signal.NONE` 을 돌려주기 **직전**에
「만석 추적」을 한 번 수행한다. 그 밖의 반환 순서·판정은 바꾸지 않는다. 만석이 아닐 때의 경로는 그대로다.

만석 추적 — 동기 · 순수 메모리 · never-raise(예외 흡수, 반환은 NONE) · `await`/DB/HTTP 0:

1. `self._candidates.get(ticker)` 가 없거나 `current_price <= 0` → 아무것도 하지 않는다.
2. **오늘자** 래치(`ticker in self._vol_latch and self._latch_entry(ticker) is not None`) → 아무것도 하지 않는다
   (래치 자체도 무접촉). 기존 규약 「`_prev_price` 는 fresh 경로에서만 read-then-write」(001450 회귀) 유지.
   날짜 지난 래치는 `_latch_entry` 가 읽으면서 지우고, 그 종목은 아래 단계로 계속 추적한다.
3. `_roll_gate_day_if_needed()` 를 부른 뒤, BFB 만: `_breakout_first_seen` 에 그 종목이 있으면 pop(만석이라 그 돌파 대기는
   끝 — 다시 사려면 새 교차).
4. 돌파선이 양수이고 `0 < prev < 돌파선 <= current_price`(`prev = self._prev_price.get(ticker, 0)`)이면 INFO 1줄,
   1회/종목/일(`_gate_should_emit(ticker, "full_cross")`). 로그 실패는 행위에 영향 없음.
   - BFB `[bfb_full_cross_skipped] ticker=… flag_high=… price=… prev=…`
   - VCP `[vcp_full_cross_skipped] ticker=… base_high=… price=… prev=…`
5. `self._prev_price[ticker] = current_price` (4 뒤에).

시간 창·쿨다운·일일 손실과 무관하게 「만석이라 NONE 을 돌려주는 그 지점」에서만 수행한다.

건드리지 않는 것: `_vol_latch` · `_bought_today` · `_cooldown_until` · `_position_setup` · `_entry_atr` ·
`_scan_stats`(새 카운터 없음) · `DEFAULT_PARAMS`(새 키 없음) · 8영역 · `scheduler.py` · 다른 전략.

## 3. 테스트 목록

`kit` 픽스처가 BFB·VCP 를 parametrize 한다(T5 는 BFB 전용). 모든 호출은 `freeze_time` 안(기본 2026-10-12 10:00).

| 항목 | 테스트 | 현 코드 |
|---|---|---|
| T1 | `test_slot_freed_when_price_already_above_line_then_no_buy` (미관측 / 만석 전 선 아래 관측 2변형) | 실패 — BUY |
| T1 | `test_slot_full_ticks_update_prev_price` | 실패 |
| T1 | `test_slot_freed_when_already_above_and_volume_short_then_latch_not_armed` | 실패 — 래치 무장 |
| T1 | `test_slot_full_tracking_ignores_entry_window` (08:00, 창 밖) | 실패 |
| T1 | `test_slot_full_tracking_touches_nothing_else` | 통과(가드) |
| T2 | `test_slot_freed_then_real_recross_buys` | 실패(앞 단계에서 이미 BUY) |
| T2 | `test_price_drops_below_line_while_full_then_cross_after_free_buys` | 통과 — 픽스처가 BUY 까지 닿는다는 양성 대조군 |
| T4 | `test_latched_ticker_untouched_while_full` | 통과(가드) |
| T4 | `test_stale_yesterday_latch_does_not_freeze_tracking_while_full` | 구현 뒤 추가 |
| T5 | `test_bfb_pending_retention_dropped_when_slots_fill` | 실패 |
| T5 | `test_bfb_slot_freed_when_already_above_then_no_retention_wait_registered` | 실패 |
| T5 | `test_bfb_pending_retention_dropped_while_full_does_not_count_retreat` | 실패 |
| T6 | `test_full_cross_logged_once_per_ticker_per_day` | 실패 |
| T6 | `test_full_cross_log_cap_resets_next_day` | 실패 |
| T6 | `test_first_seen_above_line_while_full_logs_nothing_but_tracks_price` | 구현 뒤 추가 |
| T6 | `test_first_seen_above_line_while_full_then_later_cross_still_logs` | 구현 뒤 추가 |
| T6 | `test_full_cross_log_failure_does_not_change_behavior` | 실패 |
| T7 | `test_slot_full_tracking_never_raises_on_broken_candidate` (4변형) | 통과(가드) |
| T8 | `test_slot_full_non_candidate_creates_no_prev_price` | 통과(가드) |
| T8 | `test_slot_full_non_positive_price_leaves_prev_price` (0 / -1) | 실패(뒷부분 — 정상 틱 추적 전제) |

Red 실행(2026-10-12): `25 failed, 16 passed`(41건). 실패는 전부 단언 실패(임포트·픽스처 오류 0), `--log-level=DEBUG` 에서도 같은 수.
Green 뒤(2026-10-12): 위 「구현 뒤 추가」 3개 테스트(BFB·VCP 각 1건 = 6건)를 더해 **47건**, 전부 통과.

### T3 (만석이 아닐 때 무변경) — 기존 테스트가 덮는다

- BFB: `tests/unit/engine/strategies/test_cycle228_bfb_gate_transition.py::test_gate_when_tick_volume_sufficient_then_buy`,
  `tests/unit/engine/strategies/test_bull_flag_breakout_retention.py::test_buy_signal_after_retention_period`
- VCP: `tests/unit/engine/strategies/test_cycle228_vcp_gate_transition.py::test_gate_when_tick_volume_sufficient_then_buy`
- VCP 틱 시퀀스 골든: `tests/unit/engine/strategies/test_cycle349_vcp_breakout_observe.py::test_g2_golden_*`

## 4. 명세에서 테스트가 정한 것

- **cap 은 날짜 단위로 풀린다** — `test_full_cross_log_cap_resets_next_day`. 두 전략의 `_roll_gate_day_if_needed()` 는
  지금 만석 반환보다 **뒤**에서 불린다. 만석 추적이 `_gate_should_emit` 을 쓰려면 그 앞에서 날짜 롤을 먼저 해야 한다
  (BFB 의 롤은 진짜 날짜 전환에서 `_breakout_first_seen` 도 비운다 — 기존 동작 그대로).
- **만석이 지운 BFB 돌파 대기는 「후퇴」로 세지 않는다** — `breakout_retreat_count` 무변경, `"BFB 돌파 후퇴"` 로그 없음.
- **미관측 종목(`prev=0`)이 만석 중 처음부터 선 위일 때는 로그를 찍지 않는다** — 로그 조건은 `prev > 0` 을 요구한다
  (계약 4). 「교차」가 아니라 「처음 본 틱」이기 때문이다. 직전 가격은 그 틱에도 갱신하므로, 그 뒤 선 아래로 내려갔다
  다시 넘는 진짜 교차는 찍힌다. 단언 = `test_first_seen_above_line_while_full_logs_nothing_but_tracks_price` ·
  `test_first_seen_above_line_while_full_then_later_cross_still_logs`.
- **날짜 지난 래치는 추적을 막지 않는다** — `test_stale_yesterday_latch_does_not_freeze_tracking_while_full`. 어제 무장된
  래치가 dict 에 남아 있어도 `_latch_entry` 가 무효로 읽어 지우고, 만석 추적은 그대로 돈다.
- 로그 필드는 공백 구분 토큰으로 단언한다(`ticker=280360` `flag_high=136200` `price=136300` `prev=136100`) — 정수 서식.

## 5. Green 이 손대야 할 기존 가드·핀

- `tests/unit/ast/test_cycle290_ast_scope.py::_SEGMENT_SHA` — `("bull_flag_breakout","check_buy_signal")` ·
  `("vcp_breakout","check_buy_signal")` 소스 세그먼트 sha 2핀 재핀(`test_g290_2_strategy_entry_exit_segments_are_byte_identical`).
  만석 추적을 헬퍼 메서드로 빼도 호출 1줄이 세그먼트를 바꾼다.
- `tests/unit/ast/test_cycle431_ast_price_dim_stamps.py` — 새 ticker 키 dict 속성을 만들면 분류 등재 필요(계약대로면 새 속성 없음).
- 확인만(깨지지 않을 것으로 보이나 Green 뒤 실행): `test_cycle233_ast_account_risk.py`(SOFT 게이트 첫 문장) ·
  `test_cycle399_ast_shadow_mode.py`(S01 — BUY 반환 앞 섀도 관문) · `test_cycle384_ast_buy_paused.py` ·
  `test_cycle228_ast_gate_guards.py`(g3 래치 경로 · g8 한글 문구) · `test_cycle349_vcp_breakout_observe.py`(G2 골든 —
  시나리오에 만석 구간 없음) · `test_cycle369_r2_edge_baseline.py` · `test_cycle398_strategy_wiring_golden.py`.
- 문서: `src/engine/strategies/CLAUDE.md` 각주 ① · `_workspace/00_leader_trading_rules.md`(커밋 전 `/sync-docs`).
