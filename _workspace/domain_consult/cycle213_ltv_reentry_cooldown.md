# 자문 — 사이클 213 LTV(long_tail_volatility) 재진입 쿨다운 설계

## 질문 요약

테스(095610) LTV 가 7/13 매수→손절 -10,100, 7/14 **재매수**→손절 -9,900 = 이틀 연속 같은 종목 손절 -20,000(whipsaw). LTV 는 재진입 쿨다운 무방비(DB `reentry_cooldown_days` 키 없음, `on_position_closed` override 는 상한가 모드 discard 만). BFB(3)/VCP(7)/VB(2, 사이클 201)는 배선됨. LTV 만 미배선. 사이클 201 인계가 "LTV 는 overnight 상한가 특성상 쿨다운 설계 상이 → 별도 domain 평가" 로 남긴 항목.

결론 필수: (a) 도입 여부 (b) 기간 (c) 발동 조건(손절만 vs 전체) (d) `_limit_up_reached` 무충돌 검증 (e) cycle 191 배선 재사용 스펙 + LTV 특유 가드.

---

## 트레이더 시각

### 시장 가설 — LTV 는 두 개의 다른 전략이 한 클래스에 붙어 있다

LTV 는 사실상 **모드가 두 개**다. 코드로도 `check_exit_signal` 이 `_limit_up_reached` 로 완전히 갈린다.

1. **당일 모드(상한가 미도달)** — 이게 테스 케이스다. VB 와 거의 동일한 변동성 돌파 진입 + 전일대비 5%↑ 필터. 청산은 당일 `intraday_stop_loss -3%`(코드 DEFAULT, DB 는 다를 수 있음) + 15:20 강제청산. **당일 청산 = VB 와 같은 whipsaw 위험 구조.** 진입 셋업(전일대비 5%↑ + 롱테일 노이즈)이 오늘 깨졌는데 내일 또 같은 조건이 성립하면 무방비로 재매수한다.

2. **상한가 모드(`_limit_up_reached`)** — 급등 종목이 +29% 상한가 근처 도달 → 밤새 보유 → 익일 NXT 프리 청산. 이건 **정상 사이클이 재진입을 포함**한다. 익절/트레일링으로 익일 청산한 뒤 그 종목이 다시 셋업을 만들면 재진입이 트레이더 의도에 부합한다(롱테일 = 급등주 여러 번 먹는 게 설계).

핵심 통찰: **whipsaw 손실은 당일 모드에서만 발생하고, 정상 재진입 사이클은 상한가 모드에서만 발생한다.** 이 둘을 발동 조건으로 분리할 수 있으면 쿨다운을 걸어도 롱테일 수익 구조를 안 깬다.

### 실전 사례 / 통계

- 테스 095610: 7/13 매수→-10,100 손절, 7/14 재매수→-9,900 손절. 둘 다 **당일 손절**(상한가 미도달 모드). = 당일 모드 whipsaw 의 교과서. 쿨다운 있었으면 7/14 재매수 차단으로 -9,900 방어.
- 사이클 201 VB 재진단(LS ELECTRIC 4일 재진입 -26,000 = VB 총손실 45%)과 **완전 동형**. VB 는 당일청산 전략이라 재진입 쿨다운이 whipsaw 손실 직격이었다. LTV 당일 모드는 VB 와 진입/청산 구조가 사실상 같으므로 같은 병이 있다.
- 한국 급등주 whipsaw 리듬: 전일대비 5%↑로 오늘 진입 → 오늘 되밀려 -3% 손절 → 다음날 다시 5%↑ 튀면 또 진입. 급등주는 손절 후 하루 이틀 조정/재급등을 반복하므로 **당일 손절 직후 재진입은 통계적으로 손익비가 나쁘다**(진입 셋업이 신뢰를 잃은 상태에서 노이즈에 재진입).

### 위험 시나리오 (가설이 깨지는 경우)

1. **상한가 모드 종목의 손절도 쿨다운을 걸면?** — 상한가 도달 후 익일 갭 하락 -2% overnight 손절이 발생한 종목. 이건 "급등 후 조정"이라 재진입 셋업이 오히려 유효할 수 있다(다시 급등 가능). 여기에 쿨다운을 걸면 롱테일 재진입 기회를 놓친다. → **발동 조건을 "손절만"으로 좁혀도 상한가 모드 손절까지 포함하면 이 위험이 남는다.** (아래 (c) 에서 정밀화)
2. **당일 모드 익절/15:20 청산에 쿨다운?** — 당일 상한가 미도달 종목이 손절 없이 15:20 강제청산됐다면(본전~소폭) 재진입 셋업은 살아있을 수 있다. 여기에 쿨다운 걸면 기회손실. → 발동 조건이 "전체"면 이 위험이 발생.
3. **쿨다운 dict 를 일일 리셋하면?** — 상한가 종목은 여러 날 밤샘 보유. `_cooldown_until` 을 `_reset_daily_state`/prepare 에서 리셋하면 멀티데이 상태가 깨진다. (BFB/VCP/VB 도 동일 가드 — G-NO-DAILY-RESET)

---

## 정량 권고

### (a) 도입 — **GO**

테스 케이스가 재현 가능한 whipsaw 이고, VB(사이클 201)와 동형 근본원인이며, BFB/VCP/VB 3전략이 이미 배선된 상태에서 LTV 만 무방비인 건 명백한 갭이다. 도입 권고.

### (b) 기간 — **2영업일**

- **VB(2) 복사가 오히려 정답이다.** 사이클 201 인계는 "VB 2영업일 복사 금지(당일청산 특성 상이)"라 했지만, 그 경고는 LTV 를 *당일청산 전략과 다르다*고 전제한 것이다. 실제로는 **LTV 당일 모드 = VB 와 동일한 당일청산 구조**다. whipsaw 가 발생하는 건 당일 모드뿐이고, 당일 모드는 VB 와 진입/청산 리듬이 같으므로 **VB 와 같은 2영업일이 자연스럽다.**
- BFB(3)/VCP(7)은 멀티데이 스윙 전략이라 셋업 재형성에 며칠~일주일 걸린다. LTV 당일 모드는 그렇지 않다. 3~7 을 쓰면 급등주 특성상 이틀 뒤 유효한 재셋업까지 과잉 차단.
- **급등주 조정이 길 수 있으니 더 길게?** 반론: 쿨다운의 목적은 "손절 직후 노이즈 재진입 차단"이지 "재진입 영구 금지"가 아니다. 2영업일이면 손절 당일+다음날 노이즈를 걸러내고, 진짜 재급등 셋업(3일차 이후)은 통과시킨다. 테스 케이스(7/13→7/14 연속)를 2영업일이 정확히 차단한다.
- 값은 `reentry_cooldown_days = 2` — **VB 와 같은 값**이지만 별도 키로 둔다(전략 독립 튜닝 여지). PARAM_RANGES 미등록(BFB/VCP/VB 답습 — 진입 리듬 상수, AI 자동튜닝 부적합).

### (c) 발동 조건 — **손절 청산만, 그중에서도 당일 모드 손절 우선. 단, 구현 제약상 "전량 청산 시 상한가 모드가 아니었던 종목"으로 근사.**

여기가 LTV 특유의 핵심이고, 결론을 정확히 못 박아야 한다.

**이상적 발동 조건**: 당일 모드 손절(`intraday_stop_loss` 발동)에만 쿨다운. 상한가 모드 청산(익절/트레일링/overnight 손절/익일청산)은 쿨다운 없음.

**구현 제약 (중요)**: `order_engine._handle_sell_fill` 의 `on_position_closed(ticker)` 훅은 **청산 유형(exit_reason)을 인자로 받지 않는다.** 매도 체결이면 손절/트레일링/익일청산/15:20 강제청산 무엇이든 같은 site 에서 호출된다. 따라서 훅 시점에 "이게 손절이었나"를 직접 알 수 없다.

**해결 — 훅 시점의 `_limit_up_reached` 멤버십으로 근사한다:**

- `on_position_closed(ticker)` 진입 시점에 `ticker in self._limit_up_reached` 이면 = **상한가 모드 종목** → 쿨다운 등록 **안 함**(정상 재진입 사이클 보존). 그 다음 기존 `discard` 수행.
- `ticker not in self._limit_up_reached` 이면 = **당일 모드 종목** → 이 종목이 청산됐다는 건 (당일 손절 OR 15:20 강제청산) 둘 중 하나. → 쿨다운 등록.

**이 근사가 위험 시나리오 2(당일 15:20 본전 청산에도 쿨다운)를 완전히 못 막는 건 인정한다.** 그러나:
1. 당일 모드에서 15:20 강제청산되는 종목은 애초에 "전일대비 5%↑로 진입했지만 당일 상한가도 못 가고 손절선도 안 닿은 어정쩡한 종목"이다. 재진입 셋업이 특별히 유효하지 않다. 2영업일 쿨다운의 기회손실이 미미하다.
2. 반대로 이 근사의 이득 — 당일 손절 whipsaw(테스 케이스)를 정확히 차단 + 상한가 정상 재진입을 정확히 보존 — 이 훨씬 크다.
3. exit_reason 을 훅에 배선하려면 order_engine 시그니처 변경(매매 안전성 8영역 중 order_engine 직접 수정) → 회귀 위험 급증. **`_limit_up_reached` 근사는 order_engine diff 0 을 지키면서 트레이더 의도의 90%를 달성한다.** 이게 비용 대비 최적.

**결론(c)**: "손절만"의 트레이더 의도를 `_limit_up_reached` 멤버십 게이트로 근사 구현. = **당일 모드로 청산된 종목에만 쿨다운, 상한가 모드 종목은 쿨다운 면제.** order_engine 무변경.

> **미세 보강(선택)**: 15:20 본전 청산 기회손실이 운영상 유의미하다고 판단되면, LTV `check_exit_signal` 의 `intraday_stop_loss` 손절 발동 분기에서 `self._stop_loss_fired_today: set[str]` 에 ticker 를 기록해두고, `on_position_closed` 에서 `ticker in _stop_loss_fired_today AND ticker not in _limit_up_reached` 일 때만 쿨다운 등록하는 정밀화가 가능하다. 이 set 은 transient 라 `_reset_daily_state` 에서 clear(당일 손절 기록이므로). **1차 구현은 `_limit_up_reached` 근사로 충분**하고, 정밀화는 운영 관찰 후 별도 사이클 인계 권고(과설계 회피).

### (d) `_limit_up_reached` 무충돌 검증

**무충돌 근거 (코드 사실 기반):**

1. **시점 분리** — `on_position_closed` 는 매도 **체결 시점**(포지션 전량 제거 직후)에 호출된다(`_handle_sell_fill:1176-1180`, `execute_sell:793-796`). 사이클 142 의 상한가 모드 재확립(`_execute_next_day_clear` 트레일링 분기 `_limit_up_reached.add`)과 08:00 재확립(cycle 142)은 **보유 중인 종목**에 대해 일어난다. 전량 매도돼서 포지션이 없어진 종목에 재확립이 다시 일어나지 않는다. → 쿨다운 등록(매도 후)과 상한가 재확립(보유 중)은 시간축에서 겹치지 않는다.

2. **discard 순서** — 현재 LTV `on_position_closed` 는 `_limit_up_reached.discard(ticker)`(사이클 185). 쿨다운 게이트는 **discard *전*에 멤버십을 읽어야 한다**. 즉:
   ```
   def on_position_closed(ticker):
       was_limit_up = ticker in self._limit_up_reached   # discard 전에 읽기
       self._limit_up_reached.discard(ticker)            # 사이클 185 보존
       if not was_limit_up:                              # 당일 모드였던 종목만
           self.register_cooldown_after_exit(ticker)
           # + refine task
   ```
   discard 를 먼저 하면 `was_limit_up` 이 항상 False 가 되어 상한가 종목에도 쿨다운이 걸린다(위험 시나리오 1 재발). **순서가 안전성의 핵심.**

3. **`_cooldown_until` 은 `_limit_up_reached` 와 독립 dict** — 쿨다운 등록이 상한가 set 을 건드리지 않는다(discard 는 사이클 185 로직 그대로 보존). 익일 보유 상한가 종목의 밤샘 청산 모드가 깨질 경로 없음.

4. **멀티데이 미리셋 (필수)** — `_cooldown_until` 을 `prepare()`/`_reset_daily_state`(override 없음, 하지만 신설 시)에서 절대 clear 금지. LTV prepare 는 이미 사이클 180 에서 `_targets/_open_confirmed/_prev_price` 만 clear 하고 `_limit_up_reached/_next_day_clear_pending` 는 "청산 모드 경로용이라 절대 미포함"이라 명시. **`_cooldown_until` 도 동일 부류(멀티데이 청산 결합) → prepare clear 라인에 절대 추가 금지.** AST 가드로 영구 차단(BFB 191 G-NO-DAILY-RESET 답습).

**검증 방법(회귀 테스트로 증명)**:
- 상한가 종목(`_limit_up_reached` 멤버) 전량 매도 → `_cooldown_until` 에 등록 **안 됨** + `_limit_up_reached` 에서 discard **됨**(사이클 185 보존) 동시 단언.
- 당일 모드 종목(비멤버) 전량 매도 → `_cooldown_until` 등록 **됨**.
- 상한가 종목 익일 청산 후 재셋업 → 재매수 **허용**(쿨다운 미등록이므로 게이트 통과) = 정상 사이클 불변.

### (e) cycle 191 배선 재사용 스펙 + LTV 특유 가드

VB(사이클 201)가 이미 BFB(191) 패턴을 그대로 복사해서 재사용 검증이 끝난 상태다. LTV 는 **VB 패턴을 복사하되 `on_position_closed` 에 상한가 게이트 한 겹만 추가**한다.

**재사용 (VB/BFB 191 동형)**:
1. `DEFAULT_PARAMS["reentry_cooldown_days"] = 2` 추가.
2. `__init__` 에 `self._cooldown_until: dict[str, date] = {}` 추가.
3. `from src.api.condition import add_business_days` import.
4. `register_cooldown_after_exit(ticker)` 신설 — 즉시 달력일 근사(`today + timedelta(days=days+2)`).
5. `_refine_cooldown_business_days(ticker)` async 신설 — `add_business_days(today, days)` CTCA0903R 정확 N영업일 정정, 실패 graceful 근사값 유지.
6. `check_buy_signal` 매수 게이트 추가 — `is_sold_today` 직후(VB 는 664-666행 위치):
   ```
   today = datetime.now(KST).date()
   cd_until = self._cooldown_until.get(ticker)
   if cd_until and cd_until >= today:
       return Signal.NONE
   ```

**LTV 특유 (VB 와 다른 유일한 부분) — `on_position_closed` override 확장**:
```python
def on_position_closed(self, ticker: str) -> None:
    """사이클 213 — 당일 모드 종목만 재진입 쿨다운(상한가 모드 면제)."""
    was_limit_up = ticker in self._limit_up_reached   # discard 전 판정 (게이트 핵심)
    self._limit_up_reached.discard(ticker)             # 사이클 185 보존
    if was_limit_up:
        return                                          # 상한가 모드 = 정상 재진입 사이클 → 쿨다운 면제
    self.register_cooldown_after_exit(ticker)
    coro = self._refine_cooldown_business_days(ticker)
    try:
        asyncio.create_task(coro)
    except RuntimeError:
        coro.close()   # 이벤트 루프 없는 환경 — 근사값 유지 (VB 871행 패턴)
```

**LTV 특유 가드 요약**:
- G-213-DISCARD-ORDER (HIGH): `was_limit_up` 을 `discard` *전*에 읽는다. discard 먼저면 상한가 면제 붕괴.
- G-213-LIMIT-UP-EXEMPT (HIGH): 상한가 멤버 청산 시 쿨다운 미등록.
- G-213-SET-185-PRESERVE (HIGH): 사이클 185 `_limit_up_reached.discard` 항상 수행(면제든 등록이든).
- G-213-NO-DAILY-RESET (HIGH): `_cooldown_until` 이 prepare/`_reset_daily_state` 에서 미접촉(AST 정적).
- `asyncio` import 확인 — LTV 는 이미 top-level `import asyncio` 있음(14행). VB `on_position_closed` 는 모듈 top `import asyncio`(13행) 사용. LTV 도 동일하므로 create_task/coro.close 사용 가능.

---

## 현 코드와의 정합성

### 충돌 항목 — **없음 (order_engine diff 0)**

- `on_position_closed` 훅은 **이미 사이클 185/191 로 order_engine 2 site 에 배선 완료**(`_handle_sell_fill:1180` + `execute_sell:796`). LTV `on_position_closed` override 를 확장만 하면 order_engine 무변경. **매매 안전성 8영역(order_engine 포함) diff 0 목표 달성 가능.**
- `check_buy_signal` 게이트 추가 = LTV 자체 파일 내부(strategies 는 8영역 밖). VB 사이클 201 이 동일 위치에 이미 추가한 선례.
- DB `strategy_config.long_tail_volatility.params` 에 `reentry_cooldown_days` 키 부재 → `{**DEFAULT_PARAMS, **config.params}` 머지로 DEFAULT 2 자동 적용. DB 마이그레이션 불요.

### 변경 vs 유지

- **변경 권고**: LTV `on_position_closed` override 확장(상한가 게이트) + `register_cooldown_after_exit`/`_refine_cooldown_business_days`/`_cooldown_until`/DEFAULT_PARAMS 키 + `check_buy_signal` 게이트. 전부 LTV 파일 내부.
- **유지(불변)**: order_engine 2 site / 사이클 185 discard 로직 / `_limit_up_reached` 재확립(cycle 142) / prepare clear 라인(사이클 180) / check_exit_signal 본체.

---

## 반례 / 한계

1. **`_limit_up_reached` 근사의 15:20 본전 청산 기회손실** — 당일 모드 15:20 강제청산 종목에도 쿨다운이 걸린다(exit_reason 미배선 제약). 위 (c) 에서 논한 대로 기회손실 미미(어정쩡한 종목)이나, 운영 관찰 후 `_stop_loss_fired_today` set 정밀화 인계.

2. **재시작 시 `_cooldown_until` 휘발** — VB/BFB/VCP 와 동일 한계. 프로세스 재시작하면 메모리 dict 소실 → 쿨다운 리셋. 당일 재시작 시 재진입 가능해짐. VB 사이클 201 인계 (a)와 동일 = "영속화는 관찰 후 판단". LTV 도 동일 인계.

3. **상한가 모드 종목의 overnight 손절도 면제됨** — 이건 의도적(급등 후 조정 = 재급등 가능)이나, 만약 상한가 종목이 급락 후 재차 급락 반복하는 케이스라면 면제가 손실을 키울 수 있다. 다만 이런 종목은 애초에 다음 진입 시점에 전일대비 5%↑ 필터 + master_block 필터가 1차 방어. 관찰 후 재평가.

4. **DB 값 우선** — 만약 운영자가 DB 에 `reentry_cooldown_days` 를 명시하면 DEFAULT 2 대신 DB 값 채택(머지 순서). 코드-DB 정합 유지 필요(현재 DB 미설정이므로 무해).

---

## 후속 검증 권고 (tdd-engineer / tester 에게)

### 회귀 가드 후보

1. **테스 whipsaw 차단 재현 (HIGH)** — 당일 모드 종목(비 `_limit_up_reached`) 손절 청산 → `on_position_closed` → `_cooldown_until` 에 today+근사 등록 → 다음 영업일 `check_buy_signal`(돌파 셋업 성립) 이 쿨다운 게이트로 `Signal.NONE`. freezegun 으로 today→+1영업일 전진. 테스 7/13→7/14 정확 재현.

2. **상한가 익일청산 정상 사이클 불변 (HIGH)** — `_limit_up_reached` 멤버 종목 청산 → `on_position_closed` → `_cooldown_until` **미등록** + `_limit_up_reached` **discard 됨**(사이클 185 동시 단언) → 재셋업 시 `check_buy_signal` **허용**.

3. **discard 순서 (HIGH)** — `on_position_closed` 가 `was_limit_up` 을 discard 전에 판정하는지 AST/행위 검증. (mock 으로 상한가 멤버 넣고 호출 → 등록 안 되고 discard 됨을 동시 확인 = 순서 검증)

4. **멀티데이 상태 미리셋 (HIGH, AST)** — `prepare()` + `_reset_daily_state`(override 신설 시) 영역에서 `_cooldown_until` 토큰 부재. BFB 191 `G-191-NO-DAILY-RESET` AST 패턴 답습.

5. **cooldown 값/영업일 정정** — `reentry_cooldown_days == 2` + `add_business_days` 정정 성공/실패 graceful(VB 사이클 201 `test_cycle201_vb_reentry_cooldown.py` 답습).

6. **매매 안전성 8영역 diff 0 (HIGH)** — `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = 0. LTV 파일 + condition.py(add_business_days 재사용, 신규 TR 0)만 변경.

### 인계 (별도 사이클)

- (a) `_cooldown_until` 영속화(재시작 휘발, VB 201 과 동일 — 관찰 후 판단)
- (b) 15:20 본전 청산 기회손실 유의미 시 `_stop_loss_fired_today` set 정밀화(당일 손절만 정확 게이트)
- (c) 상한가 overnight 손절 반복 급락 종목 면제 재평가
- (d) D+1 실측 = 당일 모드 손절 청산 시 `_cooldown_until` 등록 + refine 정정 로그 + 상한가 청산 시 미등록 확인
