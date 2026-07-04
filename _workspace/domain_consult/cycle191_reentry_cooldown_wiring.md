# 사이클 191 — BFB/VCP 재진입 쿨다운 고아 배선 (매매 행위 변경 자문)

> 대상: `register_cooldown_after_exit(ticker)` (BFB L965 / VCP L1070, **production 호출처 0건 = 고아**) 를 활성화하는 배선. 사이클 185 인계 A-4, MEDIUM 매매 행위 변경.
> 참고: `_workspace/domain_consult/cycle185_position_closed_cleanup.md` (on_position_closed 훅 구축 + 2 site 배선 검증)

## 질문 요약

두 전략의 재진입 쿨다운(`_cooldown_until`)은 도입 이래 한 번도 걸린 적이 없다. 청산 종목을 당일/익일 재돌파 시 즉시 재매수 가능한 상태. 6개 의제로 (1) 배선 지점 (2) 청산 유형 무구분 (3) 달력일 vs 영업일 (4) 부분 익절 정합 (5) 재시작 휘발 (6) 리셋 상호작용을 평가.

---

## 결정적 코드 사실 (자문 전제 — 직접 검증)

1. **BFB `_cooldown_until: dict[str, date]`, `reentry_cooldown_days=3`(달력일)**. `register_cooldown_after_exit`(L965~973) = `_cooldown_until[ticker] = datetime.now(KST).date() + timedelta(days=3)` + `_breakout_first_seen.pop(ticker)`. 게이트 L812~814 `if cd_until and cd_until >= today: return NONE`. `on_position_closed`(L982) = `_partial_exit.pop` 만. `_reset_daily_state`(L978) = `_breakout_first_seen.clear()` 만.
2. **VCP 동형, `reentry_cooldown_days=7`(달력일)**. `register_cooldown_after_exit`(L1070~1073). 게이트 L962~965. **`on_position_closed` override 없음**(base no-op) + **`_reset_daily_state` override 없음** + `_partial_exit` 개념 없음(청산 = base_low 이탈 / 50EMA 이탈 / ATR 트레일링, measured-move 부분익절 방식 아님).
3. **영업일 산술 헬퍼 codebase 부재**. `is_market_open(date)`(condition.py:207, chk-holiday CTCA0903R, 30일 캐시)은 단건 개장 판별만. N영업일 전진 함수 없음. BFB 시간청산(L938~941)도 `max_hold_days`를 "단순 캘린더일 + 2일 보정 — 영업일 정확도 미흡하지만 1차 구현"으로 처리 → **달력일 근사가 이미 이 파일의 확립된 컨벤션**.
4. **`is_ticker_blocked_for_buy`(registry)가 보유↔재매수를 결합**: 포지션이 메모리에 살아있거나(`is_ticker_held_by_any`) 당일 매도(`sold_today`)면 재매수 차단. → 쿨다운이 등록되는 시점(전량 청산)과 재매수가 가능해지는 시점(포지션 제거 후) 사이에 race 없음.

---

## 의제 1 — 배선 지점 (on_position_closed 훅) — GO

### 트레이더 시각 + 구조

`on_position_closed(ticker)` 훅에 `register_cooldown_after_exit(ticker)` 추가(BFB 기존 override에 1줄 + VCP override 신설)가 **정답**. 사이클 185가 이미 검증한 2 site(전량 체결 `_handle_sell_fill` + insufficient_qty reconciliation `execute_sell`)에 1:1 대응하며, order_engine try/except 격리도 그대로 상속된다. "포지션이 닫혔다 = 쿨다운 시작" 은 자연스러운 시맨틱이고, 코드 사실 4에 의해 등록 시점과 재매수 가능 시점 사이 race 가 없다.

### 대안 비교

- **대안 A (check_exit_signal 반환 시점 등록)**: **NO**. check_exit_signal 이 STOP_LOSS/TRAILING 을 반환해도 *실제 매도 체결이 보장되지 않는다* — NXT 거부, 시장가 거부→지정가 폴백 실패, 부분 체결 등. 신호 ≠ 체결. 신호 시점에 쿨다운을 걸면 "청산은 실패했는데 쿨다운은 걸린" 상태 = 원 포지션도 못 팔고 재진입도 막힌 이중 손실. 체결 시점(on_position_closed)에 거는 것이 유일하게 옳다.
- **대안 B (order_engine 직접 호출)**: **NO**. order_engine 이 전략별 `register_cooldown_after_exit` 를 직접 부르려면 전략 내부 메서드를 알아야 함 = 레이어 침범. `on_position_closed` base no-op + override 패턴이 정확히 이 결합을 캡슐화하려고 사이클 185에서 구축됨. 재사용이 맞다.

### 트레이드오프 (명시) — 전량 청산 시만 발화

훅은 full-fill(전량 체결) 시에만 발화 → **부분 체결로 잔량 보유 중엔 쿨다운 미등록**. 이는 정확하다. 잔량 보유 중엔 코드 사실 4에 의해 재매수가 이미 차단되므로 쿨다운이 불필요하고, 전량 청산돼 재매수가 열리는 그 순간 쿨다운이 등록된다. 의제 4 참조.

---

## 의제 2 — 청산 유형 무구분 일괄 등록 — GO (사용자 결정 갈림길 ①)

### 트레이더 시각 — 유형별 판단

`on_position_closed(ticker)` 는 ticker 만 받아 청산 유형(손절/익절)을 알 수 없다. 유형별로 보면:

- **손절 후 재진입**: BFB flag_low / VCP base_low 이탈로 손절 = **패턴이 깨진 것**. 깨진 직후 같은 종목이 다시 flag_high/base_high 를 재돌파하면 이는 whipsaw(속임수 돌파)일 공산이 크다. **쿨다운으로 막는 것이 강하게 정당** — 눌림목/수축 돌파 셋업의 핵심 리스크가 바로 이 재돌파 whipsaw 반복 진입이다.
- **익절(measured-move / 트레일링) 후 재진입**: 셋업이 성공한 것. 하지만 익절 직후 종목은 이미 폴 폭/베이스 폭만큼 상승한 **확장(extended) 상태**. BFB/VCP 는 "저점 축적 후 돌파"를 노리지 이미 뛴 종목을 추격하지 않는다 → 익절 직후 재진입 = 고점 추격. 게다가 새 셋업이 형성되려면 시간이 걸린다(BFB 플래그 3~10영업일, VCP 베이스 25~75영업일). **쿨다운(3/7일)보다 새 셋업 형성 시간이 더 길므로, 익절 후 쿨다운을 걸어도 실질 기회손실이 거의 0.**
- **강제청산(15:20)**: BFB/VCP 는 15:20 강제청산 대상이 아니다(멀티데이, 시간청산 없음 — VCP 는 `_MULTIDAY_STRATEGIES`, BFB 는 flag_low/5영업일 시간청산). 실질 미발생.
- **수동 HTS 매도(insufficient_qty reconciliation)**: 사용자 개입. 알고리즘은 "포지션 증발"만 안다. 쿨다운을 걸어도 무방 — 사용자가 손댄 종목을 즉시 재매수하는 것보다 며칠 쉬는 게 보수적. 빈도 극히 낮음.

### 판정: **무구분 일괄 등록 GO**

근거 = (a) 손절 후 쿨다운은 whipsaw 차단으로 강하게 정당 (b) 익절 후 쿨다운도 새 셋업 형성 시간 > 쿨다운이라 기회손실 ~0 + 고점 추격 회피 (c) 유형 구분하려면 훅 시그니처를 `on_position_closed(ticker, exit_reason)` 로 확장해야 하고 이는 사이클 185 훅 계약 + order_engine 2 site 변경 = blast radius 확대. 이득(익절 후 즉시 재진입 허용) 대비 비용(계약 변경 + 고점 추격 유발)이 맞지 않는다.

### 사용자 결정 갈림길 ①

만약 사용자가 "익절 성공 종목은 재진입을 허용하고 싶다"면 **옵션 B**(훅 시그니처에 exit_reason 전달, 손절/시간청산 계열만 쿨다운)를 제시할 수 있다. 단 그 경우에도 *익절 직후 즉시 재돌파 진입은 고점 추격*이므로 권장하지 않으며, 훅 계약 변경 blast radius 를 감수해야 한다. **domain 권고는 무구분(옵션 A).**

---

## 의제 3 — 달력일 vs 영업일 — 옵션 A (달력일 유지 + BFB 값 상향 + docstring 정정) (사용자 결정 갈림길 ②)

### 결함 정밀 추적

게이트 `cd_until >= today` + `cd_until = today + timedelta(days=N)`:

- **BFB 3달력일 — 실질 미달 심각**: 목요일 청산 → cd_until = 일요일. 금요일(today) < 일요일 → 차단(단 주말 흡수분 제외 시 **실질 차단 = 금요일 1영업일**). 월요일 today(날짜) > 일요일 cd_until → `>= ` False → **월요일 재진입 허용**. 원설계 "3영업일"(금/월/화)이 목/금 청산 시 **1영업일로 붕괴**. 작은 N + 주말 흡수의 왜곡.
- **VCP 7달력일 — 덜 심각**: 목 청산 → cd_until = 다음주 목. 금/월/화/수 재진입 차단(주말 2일 자연 흡수) ≈ 4영업일. 원설계 "7영업일"보다 미달하나 VCP 베이스 형성 자체가 25~75영업일이라 실질 영향 미미.

docstring("3영업일"/"7영업일")과 코드(달력일)가 불일치.

### 옵션 비교

- **옵션 A (달력일 유지 + 파라미터 상향 + docstring "달력일"로 정정)**: 최소 diff. 게이트/등록 로직 불변, DEFAULT_PARAMS 값만. codebase 컨벤션(코드 사실 3, BFB 시간청산이 이미 "달력일+2 보정" 근사)과 일관.
- **옵션 B (영업일 환산)**: `register_cooldown_after_exit` 에서 today 부터 N영업일 전진. **비권장** — 영업일 산술 헬퍼 부재(코드 사실 3) → `is_market_open` 반복 호출(공휴일 캐시 의존 + 등록 hot-adjacent 경로에 외부 호출) 또는 로컬 주말/공휴일 근사 신규 인프라. 쿨다운은 정밀도가 크게 중요하지 않은 리스크 완충장치인데 blast radius 만 커진다.

### 판정: **옵션 A**

- **BFB `reentry_cooldown_days` 3 → 5** 상향 권고. 5달력일이면 목/금 청산도 주말 흡수 후 대부분 커버(목→화, 금→수). 트레이더 실질 = BFB 는 인트라데이 돌파라 whipsaw 가 빠르게 발생 → 며칠 쿨다운이면 충분, 과도할 필요 없음.
- **VCP `reentry_cooldown_days` 7 유지** 권고. 새 베이스가 7~10일 안에 형성될 수 없어 값 조정의 실익이 미미. 현 7 유지가 최소 diff.
- **docstring 정정**: 두 파일 모듈 docstring "N영업일 쿨다운" → "N**달력일** 쿨다운(주말 흡수로 실질 영업일은 그보다 짧음)" 으로 코드와 일치시켜 미래 오인 차단.

### 사용자 결정 갈림길 ②

"영업일 정밀도를 반드시 지켜야 한다"면 옵션 B 를 검토하되 공휴일 캐시 의존 인프라 도입이 전제. **domain 권고 = 옵션 A(달력일 + BFB 5 + docstring 정정).**

---

## 의제 4 — 부분 익절 잔량 보유 중 미발화 — 정합 확인 (GO)

BFB `_partial_exit` 50% 익절(현 1차 구현은 measured-move 도달 시 **전량 청산 TRAILING_STOP**, `_partial_exit` 는 once-only 마킹) 후 잔량 보유 케이스 = 실제로는 *부분 체결*(주문 전량인데 체결 잔량)뿐. 이때 재매수는 `is_ticker_blocked_for_buy`(보유 중 차단, 코드 사실 4)가 막는다 → 쿨다운 미등록이 정확. 전량 청산돼 포지션이 제거되면 그때 on_position_closed 발화 → 쿨다운 등록 → 재매수 열림과 동시에 쿨다운 활성. **완벽 정합.** VCP 는 `_partial_exit` 자체가 없어 무관.

---

## 의제 5 — 재시작 휘발 — 허용(GO) + 영속화 별건 인계

`_cooldown_until` 메모리 전용 → EC2 재시작 시 소실. 그러나:

- **빈도**: EC2 재시작은 배포(장외 위주) 또는 장애 시. 장중 재시작 드묾.
- **소실 window 실질 위험**: 재시작 직후 쿨다운 소실 종목이 재매수되려면 (a) prepare 유니버스 재통과 (b) flag_high/base_high 재돌파 *순간* (이전틱<기준가 AND 현재틱>=기준가) (c) entry 시간창 — 조건 다중 동시 충족 확률 낮음.
- **일관성**: 사이클 185 도 `_limit_up_reached`/`_partial_exit` 메모리 휘발을 "허용 + 영속화 별건 인계"로 처리. 동일 계열 결정.

### 판정: **허용 + 영속화 별건 인계**

관찰 후 재시작 직후 whipsaw 재매수가 실측되면 DB 영속화(positions 테이블 유사 `(ticker, strategy_id, cd_until)`)를 별도 사이클로. 현 단계 즉시 영속화는 과잉.

---

## 의제 6 — `_reset_daily_state` / prepare 리셋 상호작용 — 확인 (GO)

- **일일 리셋 금지 확인**: `_cooldown_until` 은 multi-day 상태(사이클 185 보유결합 필드 원칙과 동일 계열). BFB `_reset_daily_state` 는 `_breakout_first_seen.clear()` 만(transient) → `_cooldown_until` 미접촉 = 정확. VCP 는 override 없음 → 자동 미접촉 = 정확. **일일 리셋하면 3/7일 쿨다운이 매일 소멸해 무의미**해지므로 절대 리셋 금지.
- **prepare 리셋 확인**: BFB/VCP prepare 는 시작부 `_candidates={}` 만 리셋(strategies/CLAUDE.md). `_cooldown_until` 미접촉이어야 함 — 배선 후 register 만 쓰고 prepare 가 안 건드리는지 회귀 가드로 고정 권고.
- **만료 항목 자연 방치**: `cd_until >= today` 비교라 만료 date 는 자동 무해(통과). dict 는 종목 수 유한 + 재청산 시 덮어씀이라 무한 성장 아님. **정리 불요 확인.**

### 배선 세부 (구조 주의)

- **BFB**: 기존 `on_position_closed`(L982~984)에 `self.register_cooldown_after_exit(ticker)` 1줄 추가. `_partial_exit.pop` 유지. register 내부의 `_breakout_first_seen.pop` 은 무해 중복(이미 `_reset_daily_state` 가 일일 clear).
- **VCP**: `on_position_closed(self, ticker)` 신설 → `self.register_cooldown_after_exit(ticker)` 호출. VCP register 는 breakout_first_seen 미접촉이라 단순.

---

## 현 코드와의 정합성 (충돌 점검)

충돌 **없음**. 변경 = (a) BFB on_position_closed +1줄 (b) VCP on_position_closed 신설 (c) BFB `reentry_cooldown_days` 3→5 (d) 두 docstring 정정. 매매 의사결정 로직(check_buy/check_exit 본체) 0 변경. 사이클 185 훅 계약(ticker 단일 인자) 불변 → order_engine 2 site 변경 0.

**충돌 항목** (값 변경 1건 명시): **BFB `reentry_cooldown_days` 3 → 5** 는 DEFAULT_PARAMS 변경 → `_workspace/00_leader_trading_rules.md` 동기화 의무(CLAUDE.md 규칙). `PARAM_RANGES` 에 이 키가 자동튜닝 대상이면 범위 재확인. **변경 vs 유지 선택지**: (변경) 목/금 청산 실질 미달 시정 / (유지) 최소 diff 지만 목/금 청산 시 1영업일 붕괴 잔존. domain 권고 = 변경(5).

---

## 반례 / 한계

1. **익절 후 새 셋업 조기 형성(이론)**: 드물게 익절 종목이 쿨다운 내 새 폴/베이스를 완성해 재돌파하면 옵션 A 는 이를 막는다. 그러나 BFB 플래그(3~10영업일)/VCP 베이스(25~75영업일) 형성 시간 > 쿨다운이라 실질 빈도 극저 + 고점 추격 회피 이득이 더 큼.
2. **재시작 직후 소실 window(의제 5)**: 재매수 조건 다중이라 실질 위험 작으나 0 은 아님. 영속화 별건 인계로 관찰.
3. **달력일 근사 잔존(의제 3)**: BFB 5달력일도 특정 요일 청산 시 영업일 환산 약간 미달 가능. codebase 컨벤션(달력일 근사) 수용 범위 — 쿨다운은 완충장치라 허용.
4. **BFB register 내 `_breakout_first_seen.pop` 중복**: on_position_closed 경로에서 호출 시 `_reset_daily_state` 일일 clear 와 중복이나 멱등·무해.

---

## 후속 검증 권고 (tdd-engineer 가 추가할 가드)

### 배선 정확성
- **G-191-BFB-WIRE**: BFB positions[X] 전량 청산(`_handle_sell_fill` full) → `on_position_closed(X)` → `X in _cooldown_until` AND `_cooldown_until[X] == today + 5일`.
- **G-191-VCP-WIRE**: VCP 동형, `on_position_closed` 신설 발화 → `_cooldown_until[X] == today + 7일`.
- **G-191-SECONDARY**: insufficient_qty reconciliation(`execute_sell` 수동 HTS 매도) → on_position_closed → 쿨다운 등록(외부 증발 종목도 catch-all).

### 쿨다운 게이트 행위
- **G-191-BFB-GATE (HIGH)**: 쿨다운 등록 종목 재돌파 → check_buy_signal `return NONE`(재매수 차단). 만료 후(cd_until < today) → 정상 매수 재개.
- **G-191-VCP-GATE (HIGH)**: VCP 동형.
- **G-191-CALENDAR**: 목요일 청산(freezegun) + BFB 5일 → 다음주 화요일까지 차단 검증(3일이면 월요일 통과 = 회귀 대비 대조).

### 멱등 / 리셋 불변 (의제 6)
- **G-191-NO-DAILY-RESET (HIGH)**: `_reset_daily_state()` 호출 후 `_cooldown_until` **불변**(BFB `_breakout_first_seen` 만 clear / VCP no-op). 일일 리셋로 쿨다운 소멸 영구 차단.
- **G-191-NO-PREPARE-RESET**: prepare() 호출 후 `_cooldown_until` 불변(register 만 접촉).

### 부분 체결 정합 (의제 4)
- **G-191-PARTIAL**: BFB 부분 체결(`total_filled < ordered`) → positions[X] 유지 → on_position_closed 미발화 → `X not in _cooldown_until`(잔량 보유 중 쿨다운 미등록, 재매수는 is_ticker_blocked 가 차단).

### 매매 안전성 8영역
- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = **0** 직접 검증. 변경은 두 전략 파일 on_position_closed/DEFAULT_PARAMS/docstring 한정. order_engine 은 사이클 185 훅 호출 site 재사용(변경 0).

---

## 최종 판정: **GO** (사용자 결정 2 갈림길 확정 전제)

6개 의제 모두 트레이더 의도·셋업 특성 정합. on_position_closed 배선(의제 1) + 무구분 등록(의제 2) + 달력일 유지+BFB 5 상향(의제 3) + 부분체결 정합(의제 4) + 재시작 휘발 허용(의제 5) + 일일 리셋 금지(의제 6). 사이클 185 훅 계약 불변으로 blast radius 최소.

**사용자 결정 갈림길**:
- **① 의제 2**: 청산 유형 무구분(권고 A) vs 손절 후만(옵션 B, 훅 시그니처 확장). → **A 권고**.
- **② 의제 3**: 달력일 유지 + BFB 3→5 + docstring 정정(권고 A) vs 영업일 환산(옵션 B, 공휴일 캐시 인프라). → **A 권고**. VCP 7 유지.

**인계**: `_cooldown_until` DB 영속화(재시작 휘발 관찰 후, 별건) + 익절 후 재진입 정책 재검토(운영 데이터 축적 시).
