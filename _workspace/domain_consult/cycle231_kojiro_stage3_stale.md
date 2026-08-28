# kojiro `_held_stage3` stale True — 재판정 실패 시 방향 (P2-5, cycle231)

작성 2026-08-29 / domain-expert / 요청자 team-leader

---

## 질문 요약

`_held_stage3[ticker]` 는 `check_exit_signal:897` 에서 **가격 무관 즉시** `Signal.TRAILING_STOP` 을 반환하는
플래그다. `recompute_held_atr` 의 실패 경로 4곳은 전부 `False` 를 기록해 fail-open 을 계약화(`:649` docstring)
했는데, `prepare()` 경로(`:400`)만 성공 시에만 기록하고 실패 시 직전 값을 방치한다.

- **Q1** 재판정 불가 시 (a) §3 발화 억제 vs (b) 직전 True 신뢰
- **Q2** 무효화 기제 (a) `(판정일, bool)` 날짜 키 vs (b) prepare 시작 시 pop 후 성공 시 재기록
- **Q3** 억제 관측 로그의 필요 여부·문구·레벨

---

## 트레이더 시각

### 스테이지3 가 무엇을 말하는가

`kojiro_indicators._STAGE_MAP` 실측: stage 3 = `("m","l","s")` = **中 > 長 > 短**. 단기선이 세 선 중
맨 아래로 내려앉은 배열이다. 대순환 분석에서 이건 "추세가 꺾였다"의 **확인 신호**이지 예고가 아니다
(예고는 stage 2 = 中 > 短 > 長). 그래서 §3 가 가격을 안 보고 즉시 던지는 설계는 그 자체로는 정당하다 —
**단, 그 판정이 오늘 데이터일 때만** 그렇다.

핵심은 이 플래그가 **이벤트가 아니라 상태**라는 점이다. "어제 stage3 였다" 는 오늘도 stage3 일 확률이
높다(EMA 배열은 하루 만에 잘 안 뒤집힌다). 그래서 (b) 를 지지하는 직관이 생긴다. 그러나 우리가 마주한
상황은 "어제의 판정" 이 아니다 — 플래그에 **타임스탬프가 없다**. 실제 의미는 "**마지막으로 재판정에
성공한 시점의 값**" 이고, 그게 어제인지 사흘 전인지 코드가 구분하지 못한다. 상태의 지속성 논거는
"어제 것" 에는 성립하지만 "언제인지 모르는 과거" 에는 성립하지 않는다.

### 재판정 실패의 원인이 stage3 와 어떻게 상관하는가 — 결정적 반례

`prepare()` 의 held 마킹(`:394-400`)은 **ATR/종가 변동성 밴드 게이트(`:365`)보다 뒤**에 있다.
보유 종목이 밴드 밖으로 나가면 `continue` 로 빠져 마킹을 못 받는다. 밴드는 `[1.0%, 6.0%]` 양쪽이 다 컷이다.

- **하한 이탈**(atr_ratio < 1%) = 변동성 소멸, 횡보. stage3 와 약한 양의 상관.
- **상한 이탈**(atr_ratio > 6%) = **변동성 급팽창**. 급락일 수도, **급등일 수도** 있다.

이게 (b) 의 가장 위험한 반례다. **급등해서 ATR 이 터진 종목이 정확히 마킹을 못 받는 종목**이고,
그 종목에 stale True 가 남아 있으면 다음날 아침 첫 틱에 시장가로 던진다. kojiro 는 승률 11% / RR 3.19
(cycle220 실측 N=9) 짜리 전략이다. 기대값이 통째로 오른쪽 꼬리에 있고, 그 꼬리를 데이터 열화로
잘라내는 것은 전략 자체를 부정한다. 손실 종목을 하루 늦게 정리하는 비용과는 종류가 다르다.

### 비대칭 비용 — 무엇이 무엇을 방어하는가

**(a) 억제했는데 진짜 stage3 였을 때**: §3 만 침묵하고 §1(고정% −8% backstop, ATR 독립) · §2(2ATR
tighten-only floor, `_stop_floor` 는 메모리에 래칫돼 있음) · §4(2.5ATR 샹들리에) 는 전부 살아 있다.
`_effective_atr` 이 `_candidates` live → `_position_atr` 영속 폴백을 타므로 ATR 도 웬만해선 0 이 아니다.
비용 = "stage3 아침 시장가" 와 "샹들리에가 잡는 지점" 의 차이 × 1일. stage3 는 정의상 이미 고점에서
꺾인 뒤라 샹들리에가 대개 근접해 있다. 체감 −1~3%, 꼬리는 §1 이 −8% 에서 자른다.

**그리고 이 지연은 새로운 종류가 아니다.** §3 는 원래 "당일 종가로 판정 → 익일 아침 발화" 설계다.
이미 하루 지연이 내장돼 있고, 억제는 같은 크기의 지연을 한 번 더 먹는 것이다.

**(b) 신뢰했는데 stale 이었을 때**: 데이터 배관 실패가 **시장가 매도 주문**으로 전환된다. 손실 상한이
없다 — 잔여 추세 전체다. 그리고 사후에 "왜 팔았나" 를 물으면 답이 "며칠 전 판정을 오늘 썼다" 다.
그건 매매 판단이 아니라 사고다.

### 이미 코드가 답을 갖고 있다

`:649` docstring 이 "실패/stale/lock → fail-open (`_held_stage3=False`, 고정%+2ATR 손절 유지)" 를
**명문 계약**으로 적어 뒀고, `recompute_held_atr` 의 4개 실패 경로가 전부 그렇게 동작한다.
즉 (a) 는 신설 정책이 아니라 **기존 계약을 prepare 경로에도 적용하는 일관화**다. 지금 상태는 같은
질문("재판정 못 했을 때 어떻게 하나")에 대해 한 파일 안에 **두 개의 답**이 있는 것이고, 그 자체가 결함이다.

---

## 정량 권고

### Q1 → **(a) 미판정 = §3 발화 억제** (권고 강도: 강)

- 억제는 "플래그를 False 로 덮어쓰기" 가 아니라 "**판정일이 오늘이 아니면 §3 를 발화하지 않는다**" 로
  구현한다. 값 자체는 보존해야 관측(Q3)과 사후 복기가 가능하다.
- §1/§2/§4 는 무변경. **§4 샹들리에 2.5 는 절대 불변**(도메인 금기 — `kojiro_exit_loss_review.md`,
  fat-tail 절단 금지). 억제의 대가를 트레일링을 조여서 메우려 하지 말 것. 그 방향이 바로 cycle220 이
  반증한 실수다.
- 진입·파라미터 무변경(FREEZE 표본 보호 준수). 이번 건은 **청산 결함 시정 한정**이다.

### Q2 → **(a) `(판정일, bool)` 날짜 키** (권고 강도: 강)

`self._held_stage3: dict[str, tuple[date, bool]]` 로 형태 전환. 소비는
`judged_on, flag = self._held_stage3.get(ticker, (None, False))` → `flag and judged_on == today` 일 때만 발화.

**(b) pop 방식을 배제하는 이유**: (b) 는 "매일 prepare 가 최소 1회 돈다" 는 불변식에 의존하는데
그 불변식이 코드로 강제되지 않는다. kojiro `prepare()` 호출자는 조건부 4곳이다 —
boot_manager(`:124`, 무조건) / run_daily 07:59 재-prepare(`scheduler:743`, `get_scanned_tickers()` 가
비었을 때만) / 16:20 evening funnel(`scheduler:3168`, 전 전략) / prepare 내부 재시도 루프.
pop 이 도는 날은 안전하지만 **prepare 자체가 안 도는 날**은 stale 을 그대로 남긴다.
날짜 키는 **기록자가 몇 명이든 소비 시점에 판정**하므로 미래에 세 번째 기록자가 생겨도 계약이 유지된다.
cycle224/227/228 의 날짜 키 자기 리셋 관례 + `_reset_daily_state` 훅 미의존 독트린과도 일치한다.

**날짜 정의 = `datetime.now(KST).date()`(판정을 수행한 날), 봉 날짜 아님.** 봉 날짜를 키로 쓰면
연휴·휴장에 D-1 봉이 그대로라 무효화가 안 걸린다. 우리가 통제하려는 것은 "오늘 재판정이 실제로
수행됐는가" 이지 봉의 신선도가 아니다.

**⚠️ 설계 의도 보존 확인 (이 자문에서 가장 중요한 검증)**: 16:20 evening prepare 가 D 날짜로 True 를
찍고 D+1 09:00 에 소비되면 날짜 불일치로 억제된다 — 언뜻 "익일 아침 발화" 설계를 죽이는 것처럼 보인다.
**죽지 않는다.** D+1 07:55 boot 의 `recompute_held_atr` 이 같은 D 확정봉으로 다시 판정해 **D+1 날짜로**
기록하고, 그 뒤 09:00 에 소비된다. 즉 날짜 키는 "오늘 아침 재판정이 성공했는가" 의 정확한 프록시로
동작하고, recompute 가 실패한 날에만 억제된다 — 그게 정확히 의도한 바다.
타이밍 마진도 충분하다: recompute 07:55, 소비는 09:00 부터(kojiro 는 `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES`
화이트리스트 밖이라 08:00~09:00 프리장 청산 평가 자체가 보류된다).

### Q3 → **필요하다** (권고 강도: 강)

억제는 정의상 "아무 일도 안 일어남" 이고, §3 발화 0건은 (i) stage3 아님 (ii) 재판정 실패로 억제
(iii) §1/§2 선발화 를 구분하지 못한다. cycle224 가 donchian 에서 정확히 같은 사각을 겪었다.

- **문구**:
  `[kojiro_stage3_stale_skip] ticker=%s judged_on=%s today=%s age_days=%d — 오늘 재판정 없음, 스테이지3 청산 보류(§1/§2/§4 유지)`
- **레벨**: `age_days == 1` → **INFO** / `age_days >= 2` → **WARNING**.
  하루 미판정은 부팅 지연·일봉 결손으로 발생 가능한 정상 범주지만, 이틀 연속은 데이터 파이프라인
  고장이고 그 상태로 §3 가 계속 침묵하면 사람이 봐야 한다. `logger.debug` 단독은 `_DbLogHandler`
  INFO 컷을 못 넘어 `system_logs` 에 도달하지 않는다(cycle225 교훈) — WARNING 은 DB 에 남는다.
- **cap**: `DailyEmitCap[str]`, 키 `ticker` 단독, 1회/ticker/일. 날짜 자기 리셋.
  (사유가 하나뿐이라 cycle225 의 `ticker|reason` 분리는 불필요. age 는 하루 안에서 고정.)
- **동반 권고(비용 0)**: §3 가 **발화할 때**도 기존 `[kojiro_stage3_exit]` 로그에 `judged_on=%s` 한
  필드를 추가한다. 사후 복기에서 "그 청산이 오늘 데이터였나" 를 즉답한다.
- 관측기 자기실패는 흡수하되 흔적을 남긴다(`[kojiro_stage3_observe_failed]` debug + 3중 try).
  무흔적 흡수는 도입 이전 무음과 구별되지 않는다(cycle224 F3 / cycle225 동형).

---

## 현 코드와의 정합성

### 팩트 정정 2건 (요청서 전제 수정)

**정정 1 — cycle225 게이트는 kojiro 에 없다.** 요청서의 "부팅 recompute 는 cycle225 게이트
(`need_atr`/`pos_needs_high_recover` 둘 다 거짓이면 skip)로 멀쩡한 보유 종목을 건너뛴다" 는
**donchian_swing.py:667-668** 의 이야기다. `kojiro.recompute_held_atr:656` 은
`for ticker in list(self.state.positions.keys())` **전수 순회**이고 skip 게이트가 0개다.
따라서 kojiro 에서 cross-day stale 이 살아남는 경로는 "게이트 스킵" 이 아니라 다음 둘이다:

1. **recompute 루프가 미실행/중도 중단** — `_eager_refresh_stock_master_for_held_positions`
   (`scheduler:2325`) 는 `boot_manager:341` 의 단일 try/except 안에서 호출되고, 그 함수 앞부분에
   eager refresh 루프가 있다. 이 함수가 recompute 루프 도달 **전에** 예외로 빠지면 그날 재판정이
   통째로 없다.
2. **recompute *이후*에 도는 prepare 의 조기 continue** — 07:59 재-prepare(`get_scanned_tickers()`
   가 빈 날. kojiro strict entry 특성상 흔하다) 와 16:20 evening prepare 는 **positions 가 복구된
   상태**에서 돌아 held 마킹 분기가 살아 있다. 여기서 ATR 밴드/stage None/일봉 fetch 실패로 빠지면
   직전 값이 그대로 남는다. boot prepare(`boot_manager:124`)는 positions 복구 **전**이라 무관.

**정정 2 — 마킹은 밴드 게이트보다 뒤다.** 위 "결정적 반례" 절 참조. 이건 (b) 채택 시 실제로
도달 가능한 최악 경로다.

### 충돌 항목

**충돌 없음.** (a)+날짜 키는 `:649` fail-open 계약의 확장이고, `hard_stop_pct`/`stop_atr`/`trail_atr`/
`breakeven_promote_atr` 어느 것도 건드리지 않는다. `PARAM_RANGES` 편입 신규 0. `on_position_closed`
의 `pop`(`:1040`)은 형태 전환과 무관하게 그대로 동작한다. 8영역 무접촉 — `kojiro.py` 단독으로 닫힌다.

### 의미 전환 (dev/tdd 인계 필수)

`_held_stage3` 를 직접 조작하는 테스트 4곳이 형태 전환에 걸린다:
- `tests/unit/engine/strategies/test_kojiro.py:167` (`is True` 단언)
- `tests/unit/engine/strategies/test_kojiro.py:277, 303` (직접 `= True` 주입)
- `tests/unit/engine/strategies/test_cycle220_kojiro_breakeven_floor.py:371` (직접 `= True` 주입)

주입형 3곳은 `(today, True)` 로 바꾸면 기존 의도(§3 발화)가 보존된다. 이 전환 자체가
**"오늘 판정이면 발화한다"** 를 명시하는 계약 문서가 되므로 xfail 이 아니라 갱신이 맞다.
그리고 **어제 날짜로 주입하면 발화하지 않는다** 는 신규 RED 를 반드시 짝으로 추가할 것.

### 부수 발견 (범위 밖, 잠복 — 정보 공유)

`kojiro.recompute_held_atr:685` 의 `if pos is not None and pos.buy_date < today:` 는 **try 밖**이다.
`buy_date` 가 date 가 아니면 TypeError 가 per-ticker 본체를 뚫고 나가 **그 뒤 보유 종목의 ATR/stage/
stage3/floor 재계산이 통째로 유실**된다(cycle226 L-2 가 donchian 게이트의 `int()` 에서 닫은 것과 동형).
donchian 은 `no_buy_date` 사유로 명시 방어하는데 kojiro 는 안 한다.
**현재 잠복이다** — `boot_manager:162` 가 `to_date(row) or yesterday` 로 항상 date 를 보장한다.
매매를 바꾸는 변경이 아니고(방어 추가), 이번 사이클에 끼울지는 team-leader 판단.

---

## 반례 / 한계

1. **억제가 길어지는 시나리오**: 데이터가 며칠 안 들어오면 §3 가 계속 침묵하고 그동안 §1 −8% 까지
   흘러내릴 수 있다. → Q3 의 `age_days >= 2` WARNING 이 그 상태를 사람에게 올린다. 억제 자체를
   자동 해제(예: "3일 지나면 그냥 믿는다")로 만들지 **말 것** — 그건 (b) 를 시간 지연으로 되살리는 것이고,
   더 오래된 데이터를 더 신뢰하는 역설이 된다.
2. **stage3 지속성 논거는 진짜로 유효하다**: EMA 배열은 하루에 잘 안 뒤집힌다. 그래서 "어제 판정 =
   오늘 판정" 인 경우가 다수이고, (a) 는 그 다수 케이스에서 **하루씩 늦게 나가는 비용**을 지불한다.
   이 비용은 실재하며 0 이 아니다. 우리가 사는 것은 "소수의 급등 종목을 배관 실패로 던지지 않을 보험" 이고,
   보험료는 저 지연이다. kojiro 의 손익 구조(승률 11% / RR 3.19)에서 이 교환은 유리하다고 본다 —
   **다만 승률이 높고 RR 이 낮은 전략이었다면 반대 결론이 나온다.** 이 권고를 다른 전략에 그대로
   복사하지 말 것.
3. **표본**: 이 판단은 §3 실측 발화 표본이 아니라 구조 논증 + cycle220 의 N=9 청산 실측에 기댄다.
   `[kojiro_stage3_exit]` 발화가 20건쯤 쌓이면 "stage3 청산 vs 샹들리에 청산" 의 실현 손익을 갈라
   §3 의 존재 가치 자체를 재검정할 것을 권고한다. 지금은 그 표본이 없다.
4. **날짜 키가 못 잡는 것**: 오늘 재판정에 **성공했지만 그 데이터가 스테일한** 경우(일봉이 D-3 에서
   멈춰 있는데 fetch 는 성공). 이건 별개 축이고 `stock_master_daily` 신선도 문제다. 이번 시정 범위 밖.

---

## 후속 검증 권고 (tdd-engineer / tester)

**tdd-engineer — 결정적 RED 4**

1. `(어제, True)` 주입 + 현재가 무관 → §3 **미발화**, `[kojiro_stage3_stale_skip]` 1행.
   (현행에서 FAIL = 결함 실증)
2. `(오늘, True)` 주입 → §3 발화(기존 계약 보존), 로그에 `judged_on` 포함.
3. **밴드 이탈 시나리오 통합**: 보유 종목의 `atr_ratio` 를 6% 초과로 만들어 `prepare()` 를 태우고
   → 마킹이 안 되는 것 + 날짜가 갱신되지 않는 것 + 다음날 소비에서 억제되는 것을 한 흐름으로.
   이게 (b) 반례의 회귀 가드다.
4. `recompute_held_atr` 의 4개 실패 경로가 전부 `(today, False)` 를 쓰는지 — fail-open 계약이
   형태 전환 후에도 유지되는지.

**cap/관측 가드 2**

5. 같은 종목 같은 날 10회 평가 → 억제 로그 1행. 날짜 넘기면 다시 1행.
6. `age_days=1` INFO / `age_days=2` WARNING 레벨 분기.

**AST 가드 1 (자기 공허화 주의)**

7. `check_exit_signal` 의 §3 분기가 `_held_stage3` 값을 **날짜 동반 판정 없이** 읽지 않는지.
   ⚠️ cycle224/226 의 교훈 — 가드가 "호출보다 뒤" 같은 **정의상 항상 참**인 명제를 묻지 않도록,
   뮤테이션(날짜 비교 제거 → FAIL / 원복 → PASS)으로 비-공허성을 반드시 실증할 것.

**tester — 배포 후 실측 2**

8. D+1 07:55 로그에서 `[kojiro_recompute] ... stage3=` 가 보유 전 종목에 대해 찍히는지
   (전수 순회 확인 = 정정 1 의 라이브 검증).
9. `[kojiro_stage3_stale_skip]` 이 배포 후 발화하는지. **발화 0건이 곧 정상이 아니다** —
   0건이면 "재판정이 매일 성공하고 있다" 는 뜻이므로 8번과 짝지어 읽어야 판독된다.
