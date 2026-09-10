# cycle273-F 명세 — 일봉 적재 **16:00 → 18:10** 이동 (D8)

- 작성 2026-09-10 · tdd-engineer(그룹 2) · **읽기 전용 사이클**
- 사용자 결정(2026-09-10 목 19:5x) = 보고서 §9 "나머지는 제안대로" 에 포함 — **D8 진행**,
  `scheduler.py` 변경 **승인 완료**(8영역은 아니지만 라인 상한 때문에 같은 승인 대상)
- 정본 = `_workspace/analysis/2026-09-10_cycle273_UD_load_and_ui.md` §D8 ·
  메모리 "일봉 적재 시각 3안 착지점"(23:00/05:00 = 루프 밖 불가 · 05:00 기동 보류 · **18:10 은 cycle263 D+1 뒤**)
- 기준 트리 = **HEAD `1df6d7d`**
- 보류 Red = `…/scratchpad/pending_tests/cycle273f/test_cycle273_daily_load_1810.py`
  → DEST `tests/unit/engine/test_cycle273_daily_load_1810.py`

---

## 1. U-D 는 "아직 이르다" 고 결론내지 않았다 — **조건 충족**

워크리스트가 걸어 둔 조건은 "**화 09-08 cycle263 D+1 확인 후**" 였다.
그 조건은 **4거래일 연속으로 충족**됐다(운영 DB `updated_at` 실측):

| bas_dd | 행 수 | `min(updated_at)` |
|---|---|---|
| 2026-09-07 | 1,197 | **09-07 16:00** |
| 2026-09-08 | 1,130 | **09-08 16:00** |
| 2026-09-09 | 1,088 | **09-09 16:00** |
| 2026-09-10 | 1,003 | **09-10 16:00** |

⚠️ docker 로그는 이미 못 쓴다 — cycle271 배포로 backend 컨테이너가 09-10 18:58 에 재생성돼 그 전 로그가
사라졌다. 그래서 DB `updated_at` 이 그 자리를 메운다. (문서에 남은 로그 실측은 09-07·09-10 두 날뿐이다.)

⇒ **판정: 지금 옮겨도 된다.** (그러나 §5 의 부수 효과와 §7 의 별건 HIGH 를 함께 읽어야 한다.)

---

## 2. 변경 규모

- **`src/engine/scheduler.py:66` 리터럴 1개**(라인 증감 **0**):
  `TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0)` → `time(18, 10)`
- `data_load_tasks.stock_master_daily_load_task_loop` 은 `wait_time` 을 **인자로만** 받고
  모듈 안에 시각 리터럴이 없다(모듈 docstring `:9-10` 이 그 규약을 적는다) — 배선은 `scheduler.py:3008` 한 줄.
- `scheduler.py` 현재 **3,898L / 상한 <3,900L** — 여유 2행 그대로 유지(리터럴 교체이므로 증감 0).
- 함께 고칠 서술 = `:66` 인라인 주석("KRX 메인 종료 30분 후 안전 마진") · `data_load_tasks.py:96` 의
  `# 16:00 KST` · `src/engine/CLAUDE.md:454` 시각 표 · 워크리스트 D-9 행 ·
  `stock_master_daily_load_task_loop` docstring("매일 16:00 KST").

---

## 3. 겹침 대조 — **0건** (전수)

| 시각 | 상수 | 18:10 과의 관계 |
|---|---|---|
| 15:20 / 15:30 / 15:40 | BUY_STOP / MAIN_CLOSE / POST_NXT_OPEN | 이전 |
| 16:10 / 16:15 / 16:20 / 16:30 / 16:40 | BASICS / DAILY_PURGE / EVENING_FUNNEL / MASTER / FINANCIAL | 이전 |
| **16:41 ~ 19:49** | — | **예정 작업 0건** |
| 19:50 | NXT_POST_BUY_STOP | 이후(1시간 40분 여유) |
| 20:00 / 20:00:05 / 20:10 | RECOMMENDATION·NXT_POST_CLOSE / FULL_UNIVERSE_LOAD / SETTLEMENT | 이후 |
| **21:30** | QUOTE_TOKEN_REFRESH (cycle270-B) | 창 `[21:20, 21:38]` — 18:10 과 무관. **단 §7 참조** |

- **16:40 재무 적재**는 주1회(`immediate_skip_if_fresh_hours=168`)이고 18:10 보다 앞이라 무관.
- **20:00:05 전체 유니버스 적재**는 1시간 50분 뒤라 무관.
- **적재 소요 실측** = 09-10 **16:00~16:02**, 1,003종목. 18:10~18:12 로 옮겨도 다음 예정 작업(19:50)까지 1시간 38분 여유.
- ⚠️ **역방향 제약이 새로 생긴다** — 토큰 강제 재발급 `T` 를 옮기는 후속 사이클은
  `test_cycle269…::test_c9` 가 `[T−10분, T+8분]` 창으로 `scheduler.TIME_*` 전수를 훑으므로
  **`T ∈ [18:02, 18:20]` 이 금지 구간**이 된다. 이 명세가 그 사실을 남긴다.

---

## 4. 소비자 확인 2건 (코드 판독 — 새로 깨지는 것 없음)

1. **16:20 저녁 funnel 캡처 — 영향 없음(두 겹).**
   (a) 전략 7종의 오늘봉 절단이 `prev_idx = 1 if candles[0]["stck_bsop_date"] == today_str else 0`
   = **날짜 비교**다(`volatility_breakout.py:293` · `long_tail_volatility.py:293` · `kojiro.py:352,743` ·
   `donchian_swing.py:445` · `bull_flag_breakout.py:330`). 오늘 행이 없으면 `prev_idx=0` 이 되어 **같은
   전일 봉**을 쓴다 — 결과 동일.
   (b) `_evening_funnel_capture_once` 의 "16:00 일봉 적재 완료 대기" 폴링은 `count_all()`(**테이블 전체
   행 수**)이 `> 0` 인지만 본다(`scheduler.py:3041-3056`). 수십만 행이 상시 존재하므로 **이 게이트는 지금도
   공허**하고, 18:10 이동으로 새로 깨지는 것이 없다.
   > **F-D8-a(INFO)** — 그 docstring 의 "일봉 미적재 시 빈 funnel 영속 방지" 는 **오늘 이미 사실이 아니다**
   > (빈 테이블만 막는다). 이 사이클에서 **주석을 정직화**한다(테스트가 강제).
2. **16:15 retention purge** — cutoff 가 T-230일이라 헤드 유무와 무관. 순서만 앞뒤가 바뀐다(무해).

---

## 5. 얻는 것 / 잃는 것 / ⚠️ 문서화되지 않은 부수 효과

| | 내용 |
|---|---|
| **얻는다** | 16:00~18:00 **시간외 단일가 물량이 그날 봉에 들어온다**(현재는 다음날 16:00 의 7영업일 창이 하루 늦게 보정). 워크리스트가 "16:00 유지의 유일한 잔여 비용" 으로 적어 둔 항목이 사라진다 |
| **잃는다** | 16:00~18:10 사이에 `stock_master_daily` 를 읽는 소비자는 헤드가 **어제 봉**이다 — §4 에서 두 소비자 확인 완료 |
| **미확인 1건** | **NXT 애프터(~20:00) 물량**이 이 일봉에 잡히는지는 **여전히 미확인**. 잡힌다면 18:10 도 그 부분은 다음날 보정에 맡긴다(이 워크플로는 KIS 를 호출하지 않았다) |

**⚠️ 부수 효과 (D5 와 직결)** — 18:10 은 **16:10 basics refresh 뒤**다. 유니버스 판정이
**어제치 `raw` → 오늘치 `raw`** 로 바뀐다.

- 좋은 쪽 — 오늘 거래대금이 임계를 넘긴 종목이 **그날 바로** 적재된다(오늘 실측 "유니버스인데 09-10 행 없음
  101종목" 중 상당수가 이 하루 지연으로 보인다).
- 나쁜 쪽 — 오늘 거래대금이 임계 **아래**로 떨어진 종목은 어제까지 받던 봉을 **그날부터 즉시** 잃는다.
  회전 자체는 사라지지 않고 **위상만 하루 당겨진다.**
- ⇒ **D8 은 D5 를 대체하지 못한다.** 004690 처럼 임계 근처 보유 종목은 그날 거래대금이 9억이면
  18:10 로 옮겨도 여전히 빠진다. **두 결정은 함께 가야 하고, D5 가 본질이다.**
- ⇒ 회귀 방향이 **양방향**이라 배포 D+1 에 `[stock_master_daily_load_begin] candidates=` 와
  `[..._summary] total/fetched` 를 **이동 전후로 나란히** 본다. **합산 금지.**

---

## 6. Red 계약 ↔ 테스트 (현재 **5 failed / 5 passed / 1 skipped**)

| 테스트 | 내용 | 현재 |
|---|---|---|
| `test_g273f_1_daily_load_time_moved_to_1810` | 상수 = `time(18,10)` | **RED** |
| `test_g273f_1b_wiring_still_passes_the_constant` | 배선 유지 + facade 에 시각 리터럴·`16:00` 주석 0 | **RED** |
| `test_g273f_2_no_scheduled_work_collides…` | 창 `[18:10, 18:20]` 겹침 0 | PASS |
| `test_g273f_2b_data_layer_order_is_preserved` | 16:10/16:15/16:20/16:30/16:40 불변 | PASS |
| `test_g273f_2c_side_effect_is_explicit…` | basics < daily_load (부수 효과 성립 조건) | **RED** |
| `test_g273f_2d_still_after_close_and_before_settlement` | 15:30 < T < 19:50 < 20:10 | PASS |
| `test_g273f_3_quote_token_refresh_window_still_clear` | cycle269 C9 불변식 유지 | PASS |
| `test_g273f_4_evening_funnel_does_not_depend…` | `count_all` 유지 + **F-D8-a 주석 정직화** | **RED** |
| `test_g273f_4b_strategies_cut_today_bar_by_date` | `prev_idx` 날짜 비교 5파일 | PASS |
| `test_g273f_5_engine_claude_md_states_the_new_time` | 문서 동기화 | **RED** |
| `test_g273f_6_periodic_wait_times_must_be_inside_the_loop_lifetime` | **§7 별건 — `@pytest.mark.skip`** | SKIP |

**갱신되는 기존 테스트 — 1개 함수**
`tests/unit/engine/test_cycle122_daily_load_task.py::test_sched1_*`(`:259`)이
`scheduler.TIME_STOCK_MASTER_DAILY_LOAD == time(16, 0)` 을 단언한다 → **같은 커밋에서 `time(18, 10)` 으로 갱신**.
같은 파일의 `TIME_STOCK_MASTER_DAILY_LOAD` **문자열** 존재 단언(`:295`)과
`tests/unit/ast/test_cycle122_kis_tr_id_persistence.py:87` 은 무영향.
`tests/unit/engine/test_cycle263_daily_load_stub_filter.py:1045` 는 상수 **이름**만 본다 — 무영향.
`tests/unit/engine/test_cycle269_quote_token_refresh.py:322`(`DAILY_LOAD < T`) 는 18:10 < 21:30 이라 **유지**.

**뮤테이션** — M1 `time(18,10)`→`time(18,0)`/`time(19,10)`(`test_g273f_1`) ·
M2 배선을 리터럴로 인라인(`test_g273f_1b`) · M3 basics 를 18:20 으로(`test_g273f_2c`) ·
M4 `count_all`→`max_bas_dd`(`test_g273f_4`).

---

## 7. 🔴 별건 HIGH — cycle270-B 의 **21:30 은 발화하지 않는다** (D8 Green 범위 밖)

**사실(실측 + 코드)**

1. `cda2dd3`(09-10 20:09 커밋, cycle270-B)가 `src/engine/quote_token_refresh.py:112` 를
   `TIME_QUOTE_TOKEN_REFRESH = time(21, 30)` 으로 바꿨다.
2. 그 task 는 `run_periodic_task_loop` 위임이고 `while scheduler._running:` 안에서
   `_wait_until(21:30, advance_if_passed=True)` 로 잠든다.
3. `scheduler.start()` 는 20:10 정산 → 로그 분석 → purge → `_reset_daily_state()` → ws disconnect 를
   마치면 본문이 끝나고, `finally` 가 백그라운드 task 를 전부 cancel 한다(목록에
   `_quote_token_refresh_task` 포함, `scheduler.py:1013`). 직후 `self._running = False`(`:1045`).
4. **오늘 실측** — `2026-09-10 20:10:15 [INFO] 매매 시스템 종료` / `금일 매매 종료, 익일 자동 시작 대기`.
   21:30 은 **80분 뒤**다.

**결론** — 배포되면 보조 시세계정 토큰 강제 재발급이 **매일 0회**가 되고, cycle269→270 이 고치려던 드리프트가
**조용히 원상 복귀**한다. 로그에는 부팅 시 `[quote_token_refresh] scheduled at=21:30` 한 줄만 남아
"배선은 살아 있다" 처럼 보인다(발화 요약 `accounts= issued=` 이 아예 안 나온다).

**왜 가드가 못 막았나** — `test_c9_schedule_time_invariants` 는 창 충돌 0 은 검사하지만 **loop 생존 시간**은
검사하지 않는다. 오히려 `threshold.time() > time(20, 15)`(⇒ **T > 20:25**)가 **T 를 loop 사망 시각 뒤로
밀어내도록 강제**한다 — **가드가 결함을 승인해 준 구조**다.

**이 명세의 처리** — 보류 Red 에 영속 가드 후보를 **`@pytest.mark.skip` 으로 넣어 두었다**
(`test_g273f_6_periodic_wait_times_must_be_inside_the_loop_lifetime`). 채택하면 그 별건이 즉시 RED 가 되고,
**D8 의 Green 으로는 고칠 수 없다.** ⇒ **결정 항목**(§8 OQ-D8-1).

---

## 8. 미해결 (결정 필요)

| # | 항목 | 권고 |
|---|---|---|
| **OQ-D8-1** | 별건 HIGH(21:30 무발화)를 **이 사이클에 묶는가, 별도 사이클인가.** 시정안 = A(T 를 loop 생존 창 안으로, 예 17:00/19:00 — **18:02~18:20 은 금지 구간**) / B(15:45 원복) / C(lifespan 구조 변경, 범위 밖) | **A 를 별도 사이클**로. 그리고 `wait_time < TIME_SETTLEMENT` **영속 가드**(F-D8-b)를 함께 — 이 계열("루프 밖 시각")은 23:00/05:00 안이 같은 이유로 기각된 적이 있어 **두 번째 재발**이다. 가드가 있으면 세 번째가 없다 |
| **OQ-D8-2** | NXT 애프터(~20:00) 물량이 18:10 일봉에 포함되는지 **미확인** | 배포 D+1 에 특정 종목의 `acml_vol` 을 KIS 원본과 대조(읽기 전용 1회). 포함되지 않으면 18:10 의 이득이 "시간외 단일가" 까지로 한정된다는 사실만 기록 |
| **OQ-D8-3** | D5 와의 **배포 순서** | **D5 먼저 또는 동시.** D8 단독 배포는 §5 의 양방향 회전을 만들면서 보호 결손은 그대로 둔다 |
| **OQ-D8-4** | 18:10 이동 후 `[stock_master_daily_load_summary] skipped_fresh` 의 의미 | cycle263 때처럼 **의미 전환은 없다**(신선도 게이트는 무접촉). 다만 `total/fetched` 는 유니버스 판정일이 바뀌므로 **이동 전후 합산 금지** |
