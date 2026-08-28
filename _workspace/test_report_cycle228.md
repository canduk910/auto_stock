# 사이클 228 Phase 4 적대적 검증 리포트 — BFB·VCP 매수 개방

> 작성: tester, 2026-08-28
> 대상: 커밋 A `4e7b302`(게이트 전환+래치+추격 상한) + 커밋 B `0056db7`(setup 리졸버)
> 방법: 읽기 중심 코드 감사 + 라이브 파라미터 시뮬레이션 14 시나리오(스크래치, 프로덕션 무수정) + 뮤테이션 실증 2건 + 테스트 스위트 재실행

## 판정: **조건부 GO** — 프로덕션 행위 결함 0건. 배포 차단 사유 없음. 단, D-1(회귀 가드 공허화)은 배포와 무관하게 즉시 tdd-engineer 시정 의뢰 대상.

---

## 결함 목록 (심각도순)

### D-1 [MEDIUM] cycle191 C-6 쿨다운 회귀 가드 공허화 — 은폐 주입 13번째 사이트 미전환

- 위치: `tests/unit/engine/strategies/test_cycle191_cooldown_wiring.py:199` — `_scanner.ticker_prices["005930"] = {"acml_vol": 5_000}  # 거래량 컷 통과`
- 커밋 A 는 "은폐 주입 12곳(3파일 11 + cycle191 **C-7**)" 을 전환했으나 같은 파일의 **C-6**(`test_C6_cooldown_via_hook_blocks_buy_signal`) 주입이 남았다. 게이트가 더 이상 `ticker_prices` 를 읽지 않으므로 이 주입은 불활성이고 주석("거래량 컷 통과")은 이제 거짓이다.
- **뮤테이션 실증**: 쿨다운 등록(`on_position_closed`)을 생략해도 게이트가 미관측 fail-closed 로 `NONE` 을 돌려 테스트가 통과 = **쿨다운 배선이 끊겨도 이 HIGH 가드가 잡지 못한다** (cycle224 자기 가드 공허성 클래스, red_result §3.5 가 경고한 "NONE 기대 공허 PASS" 의 정확한 사례).
- 대조 실증: `tick_volume.record_acml_vol("005930", 5_000)` 주입 시 쿨다운 부재에서 `BUY` 발화 → 구분력 회복 경로 확인.
- 시정 방향(1줄): 유령 키 주입을 `tick_volume.record_acml_vol` 로 교체. **tdd-engineer 회귀 테스트 의뢰.**

### D-2 [LOW] `_extension_cap_invariant_checked` 죽은 필드 + 명세 A4 편차 (잠복)

- `bull_flag_breakout.py:202` 에 "부팅 불변식 WARNING 1회만 … 인스턴스 수명 동안 1회로 고정" 주석과 함께 선언됐으나 **어디서도 읽거나 쓰지 않는다** (전 소스 grep 1건 = 선언부). VCP 는 필드 자체가 없다.
- 동적 실증: 위반 조합(stop_loss_rate=-3.0)에서 `_check_extension_cap_invariant()` 3회 호출 → WARNING **3행**. 명세 A4 "첫 prepare() 시 1회" 와 편차이고, prepare 안 주석은 반대로 "위반 시 prepare 마다 재경고되는 것이 오히려 옳다" 라고 적어 **코드·주석·명세 3자 불일치**.
- 라이브 조합(BFB 5.0/-5.0 → derived 5.26 / VCP 7.5/-7.0 → 7.53)은 무발화 확인 = 현재 잠복. 발화 조건이 되면(`stop_loss_rate` 는 PARAM_RANGES 멤버라 AI 야간 튜닝으로 조여질 수 있음) `_reprepare_breakout_if_empty`(후보 0 시 5분 주기 prepare) 경유로 일 ~100행+ WARNING 이 system_logs 에 쌓일 수 있다.
- 시정 방향: 필드 삭제+명세 문구 갱신, 또는 필드를 실제 1회 게이트로 배선 — 사람 결정 사안.

### D-3 [LOW] `_release_latch` cap 축에 reason 부재 — 같은 날 2번째 해제 사유 무흔적

- cap 키 = `(ticker, "latch_released")` (reason 미포함). 시뮬레이션 S10 실증: 같은 날 `level_moved` 해제 후 재래치 → `stop_line` 해제 시 **2번째 로그가 삼켜지고**, latch_released 카운터도 없어(명세 채택) 흔적이 0 이다. cycle225 가 `ticker|reason` 으로 닫은 함정과 같은 부류.
- 단, 명세 A2 문면("`[bfb_latch_released] reason=stop_line` 1회/(ticker)/일")과는 부합 — 구현 결함이 아니라 **명세 자체의 갭**. 행위 무영향, D+1 귀인 시 혼선 가능성만.

### D-4 [LOW] 게이트 read 예외의 reason 축 붕괴

- `[bfb|vcp_vol_gate_read_failed]` 가 `logger.debug` 단독이라 `_DbLogHandler` 를 못 넘는다. 뒤따르는 `no_data` WARNING 이 있어 **침묵은 아니지만**, system_logs 관점에선 "진짜 미관측" 과 "tick_volume 읽기 예외" 가 동일한 `no_data` 로 보인다(사유 축 붕괴). cycle225 독트린상 노트.

### D-5 [LOW] 대시보드 래치 상태 미노출

- `get_targets_status`(P3a "왜 안 사는가" 진단 그리드)가 `_vol_latch` 를 노출하지 않는다. 래치 중 종목은 `breakout_seen_at=None`(retention 완주 시 pop)으로 표시돼 화면상 "대기 없음" 으로 읽힌다 — 이번 사이클의 핵심 신규 상태가 로그(`[.*_latch_armed]`) 전용. 관찰 갭, 후속 사이클 후보.

### D-6 [INFO] DB 수동 오염 시 `float()` 예외 표면

- `max_breakout_extension_pct` 는 `_load_strategy_config` 의 per-key 병합(`if key in strategy.config.params`) 대상이라 운영자가 DB 에 비수치 값을 넣으면 `float()` 가 check_buy_signal 밖(=WS 콜백, risk.on_tick 은 전략 호출을 try 로 감싸지 않음 — `risk.py:558`)으로 샌다. PARAM_RANGES 미편입이라 AI 경로는 차단 — 운영자 실수 한정, 기존 direct-index 키들(`breakout_volume_mult` 등)과 동급의 pre-existing 노출.

---

## V1~V6 상세

**V1(a) 과잉 매수 — 통과.** 래치 재평가 블록은 `buy_disabled → has_position/is_buy_pending → is_sold_today → _bought_today → is_max_positions → is_daily_loss_exceeded → 후보 멤버십 → 시간 가드 → 쿨다운` **전부 뒤**에 위치(`bull_flag_breakout.py:907-953`, VCP 동형) — 어떤 가드도 우회하지 않는다. BUY 시 `_bought_today.add` + 래치 pop 으로 같은 날 재매수 불가(시뮬 S1b). `_arm_latch` 는 전 호출부가 `if latch is None` 게이트 — armed_at 리셋 없음. 0-나눗셈: `flag_high<=0` 진입 가드 + 판정식 자체 `if flag_high > 0 else 0.0` 이중.

**V1(b) 과소/오동작 — 통과.** 레벨 박제 비교는 **값 비교**라 재-prepare 로 dict 객체가 교체돼도 동일 값이면 래치 유지, 값 이동 시 `level_moved` 해제(시뮬 S6). 날짜 축: `_roll_gate_day_if_needed`(check_buy 최상단) cap 정리와 `_latch_entry` 의 `armed_date != today` 무효화가 둘 다 `datetime.now(KST).date()` 단일 축(시뮬 S7 — 어제 래치 읽는 순간 pop + `_breakout_first_seen` 진짜 날짜 전환에만 정리, 첫 초기화는 보존). stop_line 해제 후 재래치는 `_prev_price` 미갱신 덕에 **진짜 edge-crossing 을 요구**(시뮬 S5 — 001450 역선택 재발 차단 확인).

**V2 on_tick 생존성 — 통과.** 신규 예외 표면은 `tick_volume.get_observed_acml_vol` 하나이고 try 로 no_data 흡수(시뮬 S3b — RuntimeError 주입에도 NONE+래치). `_check_extension_cap_invariant` 는 전체 try. 래치 dict 직접 인덱싱(`latch["flag_high"]` 등)은 유일 작성자 `_arm_latch` 가 전 키를 항상 세팅. 잔여 예외 표면(`info["flag_avg_volume"]`·`params["breakout_volume_mult"]` direct index)은 228 이전과 동일한 pre-existing + D-6.

**V3 228-B 청산 안전성 — 통과.** `_effective_setup` 소비처는 **check_exit_signal 단독**(BFB `:1169` / VCP `:1226`, grep 전수 — `recompute_high_since_buy`·`_rederive_entry_atr`·boot 훅 `_refresh_position_setup_from_candles` 는 `_position_setup`/candles 직접 조작이라 리졸버 무경유). stamp 에 없는 live 키(`flag_avg_volume`·`avg_volume_20` 등)는 §1~§4 어디서도 소비되지 않아 merged 에 남아도 무해. §2 stamp-first ✓ / §3 measured-move 3키 전부 STRUCTURE_KEYS ✓ + `.get()` 결손 미발화 보존 ✓ / §4·§1.5 지표(atr14/ema50) live-first 의도 보존 ✓ / stamp `0` 결손 live 미보충 ✓. 시뮬 S8: 보유 중 flag_low 가 진입가 위(132,000)로 재검출돼도 +0.77% 포지션 §2 미발화 확인. conflict 로그는 `_roll_gate_day_if_needed` 선행 + cap 종류 축 분리(`setup_conflict`)로 매수 경로 cap 과 비충돌.

**V4 산출물 감사 — 통과.** 두 커밋 stat 합산 = BFB/VCP + 테스트 + 가드 핀(cycle223/223f/226/227) + 문서 한정. 8영역·scheduler.py·handler.py·risk.py·tick_volume.py **diff 0**. 워킹트리 BFB/VCP == HEAD(diff 0), cycle221 잔류(scheduler.py + market_op 테스트 4 + 신규 2)와 파일 비중첩 = 오염 없음. HEAD=`0056db7`, HEAD~1=`4e7b302` 연속.

**V5 운영성 — 조건부 통과 (D-3·D-4·D-5).** 신규 마커 9종(`[bfb|vcp_vol_gate_pass|reject|no_data]`·`[bfb|vcp_latch_armed|released]`·`[extension_cap_invariant]`·`[setup_structure_conflict]`) 상호 부분문자열 충돌 없음. `no_data` = WARNING 으로 `_DbLogHandler`(`src/main.py:161`) 통과 → system_logs 도달(시뮬 S3 레벨 실증). `_scan_stats` 6키 전환에 대한 은퇴 키(`vol_gate_observe_*`) 잔존 소비처 = src/·frontend/ 전수 grep **0건**(주석뿐).

**V6 라이브 파라미터 교차 — 통과.** 라이브 값(BFB mult **1.0**·retention **1분** / VCP mult **1.2**) 직접 주입 시뮬레이션 14 시나리오 중 13 PASS(유일 FAIL = D-3 관측 결함): 1분 retention 완주 → 아침 미달 래치 → 플래그 안 후퇴 생존 → 오후 임계 교차 BUY(S1, latch 설계 목적 그대로), 추격 상한 reject 후 상한 안 복귀 BUY(S2/S9b), mult 1.2 경계값(observed==threshold) BUY(S9), threshold 0 거울 유지(S9b), invariant 라이브 조합 무발화(S4b). `_load_strategy_config` 는 per-key 병합이라 DB 에 없는 신규 키 `max_breakout_extension_pct` 는 코드 리터럴(5.0/7.5)이 그대로 산다 — **DB 동반 UPDATE 불요** 확인.

---

## 테스트 재실행

- `tests/unit/engine/strategies/ + tests/unit/ast/` = **1,672 passed / 1 skipped / 50 xfailed / 3 xpassed** (재현).
- 백엔드 전체 = **5,677 passed / 9 skipped / 328 xfailed / 13 xpassed / 실패 0** (265s, 독립 재실행 — 개발팀 보고 수치와 일치).

## 후속 의뢰 (배포와 독립)

1. **tdd-engineer**: D-1 — C-6 주입 1줄 교체(`tick_volume.record_acml_vol`) + 뮤테이션(쿨다운 배선 제거) 검출 확인.
2. **team-leader 판단**: D-2 죽은 필드 처분(삭제+명세 갱신 vs 1회 게이트 배선) / D-3 cap 축 reason 편입 여부 / D-5 대시보드 래치 노출(후속 사이클).
