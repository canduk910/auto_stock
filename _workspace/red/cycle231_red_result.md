# 사이클 231 Red 결과 — kojiro `_held_stage3` 날짜 키 (P2-5)

실행 2026-08-29 / tdd-engineer
대상 = `tests/unit/engine/strategies/test_cycle231_stage3_date_key.py` (신규 28 케이스)
행위 분해 = `cycle231_behaviors.md` · 명세 = `cycle231_stage3_stale_spec.md`

## 집계

| 구분 | 수 | 비고 |
|---|---|---|
| 신규 파일 RED (구현 대상) | **20** | 결정적 — 3회 반복 동일(0.86s / 0.54s / 0.53s) |
| 신규 파일 보존 가드 (지금도 PASS, Green 후에도 PASS 의무) | **8** | |
| 의미 전환 RED | **1** | `test_kojiro.py::test_prepare_marks_held_stage3_even_if_not_buy_candidate` |
| 공허(vacuous) | **0** | B7-1 이 판별기 비-공허성을 직접 실증 |
| 백엔드 전체 | **21 failed / 5,734 passed / 9 skipped / 328 xfailed / 13 xpassed** (122s) | 실패 21 = 위 RED 20 + 의미 전환 1. **부수 회귀 0** |

## RED 20 (현행에서 실패 = 결함 실증)

| 케이스 | 실패 이유(실측) |
|---|---|
| `..._judged_today_true_then_trailing_stop_with_judged_on` | 로그가 `[kojiro_stage3_exit] 111770 스테이지3 진입 (추세 종료)` 뿐 — `judged_on=` 필드 부재 |
| `..._judged_yesterday_true_then_not_fired` | `TRAILING_STOP` 반환 (날짜 무관 소비) = **본 결함 실증** |
| `..._judged_today_false_then_no_fire_and_no_skip_log` | `TRAILING_STOP` — 현행 `if self._held_stage3.get(t):` 가 **비어 있지 않은 튜플을 전부 참**으로 읽는다 |
| `..._stale_skip_age_one_day_is_info` / `..._age_two_days_is_warning` | `[kojiro_stage3_stale_skip]` 0행 |
| `..._stale_skip_capped_once_per_ticker_per_day` / `..._cap_resets_on_new_day` / `..._cap_key_is_per_ticker` | 동상 (로그 자체가 없음) |
| `..._stale_suppression_keeps_chandelier_trailing` | §3 가 먼저 던져 `[kojiro_trailing]` 미발화 |
| `..._prepare_records_date_tuple_when_held_stage3` / `..._false_when_not_stage3` | `True` / `False` (bool 저장) |
| `..._recompute_records_date_tuple_when_stage3` | `True` |
| `..._recompute_fail_open_paths_record_today_false[4종]` | `False` — fail-open 계약은 살아 있으나 형태 미전환 |
| `..._evening_judgement_is_rearmed_by_next_morning_recompute` | 재판정 전에 이미 발화 (설계 의도 검증 불가 상태) |
| `..._recompute_bad_buy_date_does_not_kill_following_positions` | **`TypeError: '<' not supported between instances of 'str' and 'FakeDate'` @ `kojiro.py:685`** — 루프 전체 중단 = W3 실증 |
| `..._ast_stage3_branch_is_date_aware` | §3 조건식 토큰 = `{self, _held_stage3, get, ticker}` — 날짜 참조 0 |
| `..._ast_held_stage3_writes_are_date_tuples` | 기록 6곳 전부 `ast.Constant`/`ast.Compare` (bare bool) |

## 보존 가드 8 (지금 PASS — Green 후에도 PASS 해야 함)

`..._entry_absent_then_no_fire_and_no_skip_log` · `..._stale_suppression_preserves_stored_entry`
(억제가 값을 덮어쓰지 않음 = hot path 부작용 금지) · `..._on_position_closed_pops_tuple_entry` ·
`..._stale_suppression_keeps_hard_stop_backstop`(§1 생존) · `..._ast_checker_is_not_vacuous` ·
`..._exit_priority_constants_unchanged`(trail_atr 2.5 / stop_atr 2.0 / hard_stop −8.0) ·
`..._check_buy_signal_untouched_by_stage3_date_key`(FREEZE) · `..._no_reset_daily_state_override`.

## 자기 공허화 방지 (자문 후속 검증 7)

AST 판별기를 `_stage3_guard_token_sets` / `_is_date_aware` 순수 함수로 분리하고, **B7-1 이 그
판별기를 뮤테이션 소스와 시정 소스 양쪽에 직접 태워** 비-공허성을 실증한다.

- 뮤테이션(`if self._held_stage3.get(ticker):`) → `False` 판정
- 시정(`entry[0] == today and entry[1]`) → `True` 판정

판별기는 **지역 대입을 전이적으로** 되짚는다(cycle226 L-2 교훈 — `entry = ...get(t)` /
`today = datetime.now(KST).date()` 처럼 조건식이 지역변수를 경유하면 한 단계만 보는 가드는 눈이 먼다).
`[kojiro_stage3_exit]` 발화 지점의 **모든 조상 If 조건**을 모으므로 중첩 If 로 쪼개 써도 통과한다.
발화 지점을 못 찾으면 `False` → B7-2 가 "가드 공허" 로 실패한다.

## 의미 전환 4곳 (W4 — Red 단계 동반 수행 완료)

| 위치 | 전 | 후 | 현 상태 |
|---|---|---|---|
| `test_kojiro.py:167` | `_held_stage3["005930"] is True` | `== (datetime.now(KST).date(), True)` | **RED** (현행 `True`) |
| `test_kojiro.py:277` | `= True` | `= (datetime.now(KST).date(), True)` | PASS 유지 (튜플 truthy → Green 후에도 PASS) |
| `test_kojiro.py:303` | `= True` | `= (datetime.now(KST).date(), True)` | PASS 유지 (pop 은 값 형태 무관) |
| `test_cycle220_kojiro_breakeven_floor.py:371` | `= True` | `= (_today(), True)` | PASS 유지 |

각 지점에 `# cycle231 — 날짜 키 계약 …` 1줄 주석. 3곳이 지금도 PASS 하는 것은 **의도된 결과**다 —
이 주입들은 "오늘 판정이면 발화한다" 는 새 계약의 문서이고, Green 이후에도 같은 의미로 통과해야 한다.

## backend-dev 인계 메모

1. `_held_stage3` 기록 6곳(`:400` prepare + `:664/:668/:703/:738/:745` recompute) 을 `(today, flag)`
   튜플로. `today = datetime.now(KST).date()` — recompute 는 `:653` 에 이미 있다.
2. 소비 `:897` 은 **엔트리 존재 ∧ 판정일 == today ∧ flag**. 튜플 truthiness 에 기대지 말 것
   (B1-3 가 그것만으로 청산이 나는 것을 잡는다). 억제 시 **값 보존**(덮어쓰기 금지).
3. `[kojiro_stage3_stale_skip]` — cap `DailyEmitCap[str]` + **날짜 키 자기 리셋**
   (`_reset_daily_state` override 신설 금지, B7-4 봉인). age 1=INFO / ≥2=WARNING.
4. W3 = `:685` 를 per-ticker try 안으로 넣거나 `isinstance(pos.buy_date, date)` 사전 가드.
   흔적은 `[kojiro_recompute]` 계열 WARNING 1행에 해당 ticker 명시(B6-1 이 검사).
5. 파일 범위 = `kojiro.py` 단독. 8영역·타 전략 diff 0, PARAM_RANGES 신규 0.

## 잔여

- `tools/test_impact/build_index.py` 재생성은 **Green 이후 사이클 종료 시점**에 수행(현재 미실행).
