# 자문 — 사이클 180: VB/LTV `prepare()` 시작부 3-dict 일괄 리셋의 매매 행위 영향

작성: domain-expert (데이/스윙 트레이더 출신 컨설턴트)
대상: team-leader 확정 명세 검증/반박 (재스카우트 아님)
산출물: `_workspace/domain_consult/cycle180_vb_ltv_prepare_reset.md`

---

## 0. 의제별 결론 요약 (tdd-engineer Red 설계 직접 인용용)

| 의제 | 결론 | 조건 |
|------|------|------|
| **1 (a)** empty-gate → 09:00 시가확정 미손실 | **GO** | empty-gate 논증은 intraday 재prepare 2경로(boot 660, reprepare 2501)에 대해 **참**. 그 두 경로는 `_targets`가 빈 경우에만 발화 → 잃을 confirmed 가 애초에 0. 게다가 prepare 는 `_targets[ticker]=` 재할당 시 `_open_confirmed[ticker]={}`(L279/L304)로 **clear 유무와 무관하게** 종목별 리셋. 따라서 "후보 0건 재prepare 가 시가확정을 날린다"는 시나리오는 **실재하지 않음**. |
| **2 (b)** `_limit_up_reached` 제외 | **GO (제외 필수, 절대)** | clear 에 포함 시 보유 상한가-익일청산 종목이 (i) 15:20 강제청산 대상으로 잘못 편입(`check_force_clear` L814-817) (ii) 익일 트레일링이 당일 -3% 손절 모드로 격하 → **롱테일 핵심 수익 구조 파괴**. 제외는 타협 불가. |
| **3 (c)** 16:20 저녁 prepare ↔ D+1 boot 상호작용 | **GO (clear 가 오히려 더 안전)** | (i) 보유 매수판정 무관(보유→check_buy early-return) (ii) D+1 새벽 stale 무해(VB 보드가드 + 07:50 재clear) (iii) clear→재할당 사이 빈 window 는 보유 청산경로(3-dict 미참조)에 무영향 + 매수경로는 NONE 반환(stale 매수보다 안전). **단 1개 신규 미세 위험** = 장중 재시작 후 16:20 immediate-run 의 빈 window 가 VB/LTV 매수신호를 수 초 억제(아래 §3-나 + §반례). |
| **4 (d)** clear 후 0건 = 빈 `_targets` 정합성 | **GO (0건이 옳음 — team-leader 동의)** | 전일 누적분으로 매수 = 전일 시가/Range 기준 stale 진입 = 교과서적 결함. 0건=미거래가 트레이더 정답. "fallback 역할"은 의도된 동작이 아니라 결함의 부작용. |
| **5** 추가 발견 | **보강 권고 동반 GO** | (a) `_prev_price` board-level dict clear 는 **안전**(edge 검출 self-heal, 거짓 돌파 불가). (b) `get_targets_status` 순회는 관찰성 전용 — 무영향. (c) donchian/BFB/VCP 는 **이미** `_candidates={}` 로 prepare 시작부 리셋 = cycle 180 은 형제 전략 정합성 복원(신규 위험 아님). (d) `_limit_up_reached` 가 `_reset_daily_state`에도 빠진 **선재 latent 버그** 발견(스코프 외, 별건 인계). |

**총평: 5개 의제 전부 GO.** 스코프(시작부 3-dict clear, `_limit_up_reached`/`_next_day_clear_pending` 제외) 는 정당. 유일한 신규 위험(장중 재시작 빈 window)은 negligible + 기존 운영정책(장중 재시작 자제)으로 이미 완화됨.

---

## 1. 질문 요약

VB/LTV `prepare()` 가 장수 싱글톤 인스턴스의 `_targets`/`_open_confirmed`/`_prev_price` 를 종목별 **할당만** 하고 시작부에서 비우지 않아, 전일 종목이 누적된다. 누적 `_targets` → `_scanned_tickers`(= `list(self._targets.keys())`) → scanner 구독 → 틱 수신 → `check_buy_signal` 이 **전일 타겟가**로 매수판정 → "돌파 = 이전틱<기준가 AND 현재틱>=기준가" 절대규칙 위반(기준가가 오늘 시가/Range 아닌 전일값).

시정 = `prepare()` 시작부(`_scan_universe()` 호출 *전*, `_empty_scan_stats()` 부근)에 `_targets.clear()` + `_open_confirmed.clear()` + `_prev_price.clear()` 3줄. 본 메모는 team-leader 라인 스카우트가 끝난 **확정 명세의 행위 영향을 검증/반박**한다.

---

## 2. 결함 근본원인 — 코드 정독 확정 (team-leader 라인 인용 재확인)

**확정 1: 기존 리셋 경로 자체가 없다.**
`scheduler._reset_daily_state()`(L3804~L3910, 20:10 정산 후 유일한 일일 리셋)를 정독한 결과 — `strategy.state.*`(positions/pending_buys/sold_today/...) + order_engine 추적 + scanner 글로벌 dict 만 비운다. **전략 인스턴스 필드 `_targets`/`_open_confirmed`/`_prev_price`/`_limit_up_reached`/`_scanned_tickers` 는 단 한 줄도 건드리지 않는다.** 즉 이 3-dict 는 prepare 의 종목별 재할당(VB L267/L279, LTV L293/L304) 외에는 **프로세스 생애 동안 절대 비워지지 않는다**. 전일 universe 에서 빠진 종목은 영원히 잔존 → 결함 서술 100% 확정.

**확정 2: 형제 전략은 이미 prepare 시작부에서 리셋한다.**
donchian(L139 `self._candidates = {}`) / BFB(L150 `self._candidates = {}`) / VCP(L177 `self._candidates = {}`) — 3 전략 모두 prepare 진입 직후 후보 dict 를 **빈 dict 로 재바인딩**한다(0건 early-return 경로 L157/L201 등에서도 재리셋). VB/LTV 만 이 리셋이 누락된 **비대칭**이 결함의 정체다. → **cycle 180 은 신규 패턴 도입이 아니라, 5 전략 중 3 전략이 이미 채택한 "prepare 시작부 후보 리셋" 컨벤션으로 VB/LTV 를 정합시키는 작업**이다. 회귀 위험 평가의 기준선이 크게 낮아진다.

> 메모: 형제 전략은 `= {}`(재바인딩), 스코프는 `.clear()`(in-place). 효과 동일. `.clear()` 가 외부 참조 보유자에게 영향을 줄 수 있으나, 3-dict 는 전부 `self._targets` 경유로만 접근되고 외부에 레퍼런스를 넘기는 코드가 없으므로(아래 §5-나 `get_targets_status` 도 `self._targets.items()` 직접 순회) `.clear()` 안전.

---

## 3. 트레이더 시각 + 코드 정합 — 의제별 분석

### 의제 1 (a) — empty-gate 가 09:00 시가확정을 지키는가

**호출처 전수(grep 확정):** VB/LTV `prepare()` 를 부르는 곳은 정확히 4종.
1. `boot_manager.py:111` — boot 1회 **무조건**, 07:50 (= 09:00:05 시가확정 **전**).
2. `scheduler.py:660-667` — boot 내 `if not self._collect_breakout_tickers():` **빈 경우만**, `now <= 09:00:05` 가드.
3. `scheduler.py:2511` — `_reprepare_breakout_if_empty`, `if scanned: continue` **빈 경우만**, 5분 주기.
4. `scheduler.py:3131 _evening_funnel_capture_once` 내 `await prep()` — 16:20 **무조건**(+ start() 마다 immediate-run, 아래 §3-나).

`_collect_breakout_tickers`(L1625) 와 `_reprepare_breakout_if_empty`(L2479) 둘 다 게이트가 `get_scanned_tickers()`(= `list(self._targets.keys())`)의 **빈 여부**다.

**트레이더/코드 논증:** intraday 재prepare(경로 2·3)는 **`_targets`가 비어있을 때만** 발화한다. `_targets`가 비었다 ⟺ confirmed open price 도 0개 ⟺ **clear 가 날릴 시가확정 자체가 존재하지 않는다.** 09:00:05 에 confirmed 된 종목이 있으면 `_targets`는 비어있지 않고 → 경로 2·3 는 `continue`/skip → clear 미발화. 즉 "09:01 후보 0건 → 재prepare → clear → 이미 확정된 open_confirmed 소멸" 시나리오는 **논리적으로 성립 불가**(전제 모순: 후보 0건이려면 confirmed 도 0건).

**추가 핵심(clear 전후 동일성):** 설령 어떤 종목이 재prepare 결과에 *다시* 포함돼도, prepare 는 그 종목에 `_targets[ticker]=` 재할당 시 **반드시** `_open_confirmed[ticker]={}`(VB L279 / LTV L304) 로 confirmed 를 리셋한다 — **clear 도입 여부와 무관하게**. 따라서 재prepare 의 시가확정 영향은 clear 도입 전후로 **달라지지 않는다**(today 종목엔 동일, stale 종목 제거만 추가). 09:00:05 직후 cycle-164 `_confirm_breakout_open_prices_if_pending`(5분 재시도)가 미확정 종목을 자동 재확정하므로 일시 미확정도 자가복구.

**결론: GO.** empty-gate 추론은 intraday 재prepare 경로에 대해 건전. 시가확정 손실 시나리오 미실재.

### 의제 3 (c) 일부 — 의제 1과 직결되는 16:20 immediate-run (§3-나로 통합)

### 3-나. (의제 1·3 공통 핵심 nuance) 16:20 저녁 task 의 `immediate_first_run`

`_evening_funnel_capture_task_loop`(L3203) 는 `run_periodic_task_loop(... initial_delay_secs=600)` 를 호출하며, `immediate_first_run` 기본값이 **True**(`task_loop_helper.py:50`). 즉 **매 start() 마다**(07:50 정상 boot 뿐 아니라 **장중 EC2 재시작 포함**) 600초 후 `_evening_funnel_capture_once` 가 1회 실행되고, 그 안에서 5 전략(VB/LTV 포함) prepare 가 **무조건** 호출된다. → 이것이 empty-gate 가 아닌 **유일한 intraday prepare 경로**.

**시나리오 분석 (11:00 KST 재시작 가정):**
- 11:00 재시작 → `_boot` 의 `boot_manager:111` prepare 무조건 1회 → 오늘 `_targets` 재구성. `now>09:00:05` 라 경로 2(L660) skip. cycle-164 5분 재시도가 시가 재확정.
- ~11:10 evening immediate-run → 5 전략 prepare **무조건** → `_targets` clear→재구성. open_confirmed 리셋 → cycle-164 가 다시 재확정.

**clear 의 한계 효과(보유/오늘 종목):** evening prepare 는 clear 유무와 무관하게 today 종목에 `_targets[ticker]={open_price:0,...}` + `_open_confirmed[ticker]={}` 재할당. 따라서 today 종목엔 동일. clear 의 marginal 효과 = **전일-only stale 종목 제거뿐** → 더 안전(stale 종목의 잘못된 post_nxt 매수 차단, LTV 는 post_nxt 매수 가능하므로 실익 있음).

**유일한 신규 미세 위험:** clear→재할당 사이 `_scan_universe()` + `gather(_fetch_one)` await 구간 동안 `_targets`가 **수 초간 완전히 빈다**. 이 window 에 VB/LTV 매수 틱이 오면 `check_buy_signal` 이 `info=None` → `NONE` 반환 → **그 틱의 매수신호 누락**. no-clear 라면 이 window 동안 (재시작-boot 가 만든) **오늘의 정상 타겟**이 읽혀 매수가능했을 수도 있다 — 즉 이 narrow 케이스(장중 재시작 → boot 가 오늘 타겟 구성 → 10분 뒤 evening immediate-run 이 MAIN 중 clear)에서만 clear 가 수 초의 매수 공백을 만든다.

**평가:** (1) 발생조건이 "장중 EC2 재시작"으로 극히 드물고 CLAUDE.md 가 이미 "KRX 메인(09:00~15:30) 빈번한 push 자제"로 정책 차단. (2) window 는 한 prepare 사이클(수 초). (3) 돌파는 prev!=0 이 필요(첫 틱은 기록만)하므로 어차피 1틱 지연 + retention 으로 재포착. (4) **donchian/BFB/VCP 는 이미 동일 window 를 갖고 있고**(이미 `_candidates={}` 리셋) 운영 사고 보고 0건. → negligible. **GO + 반례에 명시.**

### 의제 3 (c) — 3가지 세부

**(i) 그날 장중 보유 종목 매수판정 영향:** 없음. 16:20 은 장 마감 후 + `check_buy_signal` 은 보유 시 L649/L682 `has_position` early-return. 무관 확정.

**(ii) D+1 새벽까지 16:20 _targets 가 stale 로 남아도 무해한가:** 무해.
- 16:20 prepare 가 만든 `_targets`는 **오늘(T) 종가 Range 기반 = 사실상 D+1 후보 타겟**(funnel 의 본래 목적: 운영자 야간 후보 확인).
- VB: `tradable_boards=("main",)` → `_resolve_active_board()`가 overnight(pre_nxt/post_nxt)엔 None → `check_buy_signal` NONE. **VB 는 야간 매수 구조적 불가** → stale 무해.
- LTV: `("pre_nxt","main","post_nxt")` → post_nxt(15:40~19:50, 19:50 buy_disabled)·pre_nxt(08:00~09:00) 매수 가능. 하지만 이때 타겟은 16:20 에 새로 만든 today-range 기반(= cycle-171 기존 동작, clear 무관). **clear 는 stale 전일종목만 제거 → LTV 야간 매수에서 stale 종목 오진입을 오히려 차단**(더 안전).
- 다음날 07:50 boot prepare 가 clear→재구성으로 신선화. D+1 새벽 잔존분이 매수로 이어질 경로 없음(VB 보드가드 + LTV 는 today-range 기반 + buy_disabled 19:50).

**(iii) 16:20 clear 직후~재할당 전 빈 순간에 보유 종목 check_exit/force_clear 동시호출:** **안전.** team-leader 라인 grep 재확인 — VB `check_exit_signal`(L791/797)·`check_force_clear`(L802~) 는 `_next_day_clear_pending`(bool) 만, LTV `check_exit_signal`(L760/763/804)·`check_force_clear`(L816)는 `_limit_up_reached`(set)+`_next_day_clear_pending`(bool) 만 사용 → **3-dict 미참조**. 빈 window 에 청산경로가 돌아도 청산은 정상 발화. 직접 코드 재확인 완료.

**결론: GO.** 3가지 모두 무영향~더 안전. 단 (iii)의 매수경로 빈 window 는 §3-나의 미세 위험으로 별도 인지.

### 의제 2 (b) — `_limit_up_reached` clear 제외의 타당성

**제외 필수 — 보유 청산 안전성 직결. 절대 타협 불가.** LTV 상한가 익일청산 모드는 `_limit_up_reached` set 멤버십에 전적으로 의존:
- `check_force_clear()`(L814-817): `return [t for t in positions if t not in self._limit_up_reached]`. 즉 **15:20 강제청산 대상에서 상한가 종목을 빼는** 기준이 이 set. 만약 prepare 시작부에서 `_limit_up_reached` 도 clear 하면 → 보유 상한가 종목이 set 에서 사라짐 → **15:20 에 강제청산 대상으로 잘못 편입** → 익일 NXT 프리 롱테일 청산 대신 당일 마감 청산 → **롱테일 전략의 핵심(상한가 익일 보유) 파괴**.
- `check_exit_signal()`(L760): `if ticker in self._limit_up_reached:` 분기로 익일 갭/트레일링(overnight_stop_loss -5%, gap_up_threshold +10%, trailing -2%) 적용. clear 시 → 이 분기 미진입 → "당일 모드"(L792~) 로 격하 → **intraday_stop_loss -3%** 만 작동 → +29% 상한가 종목이 -3% 손절 임계에 노출 + 트레일링 미발화. 후성(093370) 류 운영사례(매수 17,150→고점 23,700→마감 22,300)에서 보았던 정확히 그 결함 재현.

**구체 사고 시나리오:** 종목 X 가 T일 +29% 상한가 → `_limit_up_reached.add(X)`(check_exit L804) → 익일청산 모드. 만약 T+1 07:50 boot prepare 가 `_limit_up_reached.clear()` 한다면 → T+1 아침 NXT 프리 청산 직전에 X 의 상한가 플래그 소실 → `check_exit_signal` 이 X 를 당일 모드로 처리 + (만약 still held & MAIN) `check_force_clear` 가 X 를 15:20 청산 대상으로 편입 → 운영자 의도(상한가 익일 갭 캡처) 정반대 실행 → 손익 구조 붕괴.

**결론: GO (제외 필수).** 스코프의 `_limit_up_reached` 제외 결정은 **보유 종목 청산 안전성의 필수 조건**이며 정당. `_next_day_clear_pending`(strat-4) 동일 — bool 가드로 익일청산 race 차단용, clear 시 무한 신호 폭주(VB L788 주석 영역) 위험.

> **선재 latent 버그 발견(스코프 외, §5-라):** `_limit_up_reached` 는 `_reset_daily_state`(20:10)에서도 비워지지 않는다(L3804~ 정독 확정). 즉 프로세스 생애 누적. 동일 ticker 가 후일 LTV 에 재매수되면 첫 `check_exit_signal` 부터 상한가 모드로 오진입(15:20 청산 제외 + -5% 모드). **cycle 180 과 무관한 별건**이나, "상한가 종목 청산 안전성" 테마라 함께 인계.

### 의제 4 (d) — clear 후 retry(cap3)/0건 시 빈 `_targets` 정합성

VB L134-146 / LTV L142-154 의 `for retry_attempt in range(3)`(stock_master 0건 시 sleep 30초 후 재시도, 사이클 158/163) 가 끝까지 0건이면 clear 도입 후 `_targets`가 빈 채 prepare 종료.

**트레이더 판단 — team-leader 동의:**
- **"전일 누적분으로 매수"는 의도된 fallback 이 아니라 결함의 부작용.** 전일 `_targets`의 open_price/target_price 는 전일 시가·전일 Range 기준이다. 오늘 시장이 갭상승/갭하락했거나 변동성 레짐이 바뀌었으면 전일 타겟은 무의미. 전일 타겟가로 오늘 진입 = 잘못된 기준가 돌파 매수 = "돌파 = 이전틱<기준가 AND 현재틱>=기준가" 규칙의 기준가가 오염된 상태. **데이트레이더 관점에서 명백한 stale-signal 진입 오류.**
- **transient 실패(DB 히컵)에서도 0건이 옳다.** 0건=미거래는 안전(자본 보존). universe 가 복구되면 07:50 boot / 5분 reprepare / 16:20 evening retry 가 자연 재충전. 전일 타겟으로의 "fallback 매수"는 복구가 아니라 위험 노출.
- LTV 의 상한가 보유 종목은 `_targets`와 무관(`_limit_up_reached`+positions 로 청산) → 0건이어도 보유 청산 안전성 영향 0. retry 90초 동안 빈 `_targets`도 청산경로 무참조라 무해.

**결론: GO (0건이 정답).** team-leader 판단에 **트레이더 관점 전면 동의.** 반박 없음.

---

## 4. 추가 발견 (의제 5)

**가. `_prev_price` board-level dict clear 는 안전 (거짓 돌파 불가).**
`_prev_price: dict[str, dict[str,int]]`(VB L96 / LTV L107, ticker→{board:price}). `.clear()` 는 전 종목 전 보드의 직전틱가를 0(부재)로. edge 검출 L681/L720 `if prev == 0: return NONE`(첫 틱은 기록만). 분석:
- clear 후 첫 틱 가격 P 에서 `prev=P` 기록. 다음 틱부터 정상 edge 평가.
- P 가 이미 target 이상이면 → 이후 `prev>=target` 유지 → `prev<target` edge 조건 영원히 false → **거짓 매수 불가**.
- P 가 target 미만이면 → 정상적으로 상향 교차 대기.
- 즉 `_prev_price` clear 는 어떤 경우에도 **가짜 돌파를 만들지 못한다**(self-heal). 보유(has_position)/당일매도(is_sold_today)/max_positions 가드가 이중으로 재매수 차단. 유일 효과 = clear 직후 1틱 매수 검출 지연(negligible). **안전 확정.**

> no-clear 대비 신규성: prepare 는 원래 `_prev_price` 를 건드리지 않았다(`_reset_daily_state`만 비움). cycle 180 clear 는 prepare 시작부에서 `_prev_price`를 비우는 **신규 동작**이나, 위 분석대로 거짓 돌파 불가 + 1틱 지연만 → GO.

**나. `get_targets_status`(VB L493~523 / LTV L537~562) 는 관찰성 전용 — 무영향.**
`for ticker, info in self._targets.items()` 순회는 **상태/모니터링 메서드**다. 소비처 grep 확정:
- `strategy_registry.py:126-127` `get_strategies_status()` → 프론트 대시보드 노출.
- `scheduler.py:1598` `_emit_breakout_open_confirm` → `logger.debug` 로깅(L1600 실패 시 graceful).
→ **매매 의사결정이 이 메서드를 읽지 않는다.** clear 의 빈 window 동안 `{}` 반환(UI 잠깐 타겟 비표시) + stale 종목 제거(오히려 정확). 트레이딩 무영향. **무해 확정.**

**다. donchian/BFB/VCP 는 이미 동일 컨벤션 — cycle 180 은 정합성 복원.**
§2-확정2 재강조: 3 형제 전략이 prepare 시작부 `self._candidates={}` 로 이미 리셋. VB/LTV 만 누락. → **cycle 180 의 회귀 위험은 "신규 패턴" 이 아니라 "이미 검증된 패턴의 누락 보정"** 으로 평가. 스코프(VB/LTV 한정)는 정당 — 형제 3 전략은 손댈 필요 없음(이미 정상). (단 그들의 `_prev_price`/`_breakout_first_seen` 등 부속 상태 리셋 정책은 cycle 180 범위 밖, 별도 감사 불요 — 그들은 has_position/cooldown 가드 체계가 다름.)

**라. 선재 latent 버그 — `_limit_up_reached` 가 일일 리셋에서도 누락(스코프 외 인계).**
§2-확정1 + §의제2 메모. `_reset_daily_state` 가 `_limit_up_reached` 를 비우지 않아 프로세스 생애 누적 → 동일 ticker 후일 LTV 재매수 시 첫 틱부터 상한가 모드 오진입(15:20 청산 제외 + -5% 모드 + 트레일링). **cycle 180 의 clear 와는 무관**(clear 가 이걸 고치지도 악화시키지도 않음 — clear 에서 제외하므로). 별건으로 team-leader 인계 권고: `_reset_daily_state` 또는 종목 매도 시점에 `_limit_up_reached.discard(ticker)` 추가 검토.

---

## 5. 현 코드와의 정합성

- **충돌 없음.** 스코프(시작부 `_targets`/`_open_confirmed`/`_prev_price` 3-dict clear, `_limit_up_reached`/`_next_day_clear_pending` 제외)는 CLAUDE.md "절대 깨지 말 것" 8영역 어느 것과도 충돌하지 않는다. 특히:
  - "매수 신호는 반드시 돌파 순간 감지(이전틱<기준가 AND 현재틱>=기준가)" → cycle 180 이 이 규칙을 **복원**(기준가가 오늘 값이 되도록).
  - "VB 당일 15:20 일괄매도" / "tradable_boards 는 매수 진입 전용" → 청산경로 3-dict 무참조라 무영향.
  - "익일 청산은 시가 수신 후 30s 안정화" → `_next_day_clear_pending` 제외로 보존.
- **DEFAULT_PARAMS / tradable_boards 변경 0.** 행위 보존(매수 target 산출 로직 불변, 오직 stale 누적 제거).
- **`_reset_daily_state` 와 역할 분리:** cycle 180 은 prepare 시작부(= prepare 호출 시점마다)에 3-dict 를 비우고, `_reset_daily_state` 는 20:10 일일 1회 state.* 를 비운다. **중복 아님 — 보완.** 오히려 cycle 180 은 `_reset_daily_state` 가 빠뜨린 3-dict 리셋을 prepare 단위로 메운다(더 빈번 + 매 universe 재구성마다 정합).

---

## 6. 반례 / 한계 (가설이 깨지는 경계)

1. **장중 EC2 재시작 + 16:20 immediate-run 의 빈 window(§3-나).** 유일한 신규 위험. 장중(09:00~15:30) 재시작 → ~10분 뒤 evening immediate-run 이 MAIN 중 clear→재구성 → 수 초 매수신호 공백(VB/LTV). no-clear 였다면 그 window 에 오늘 타겟이 읽혀 매수가능했을 narrow 케이스. **완화: (1) 발생빈도 극저(장중 재시작 자제 정책 기존 존재) (2) window 수 초 (3) 1틱 지연 + retention 재포착 (4) donchian/BFB/VCP 이미 동일 window 무사고.** → 수용 가능, 반례로 명시.
2. **`.clear()` vs `= {}` 선택.** 형제 전략은 `= {}`. 스코프는 `.clear()`. 효과 동일하나, 만약 미래에 `_targets` 레퍼런스를 외부로 넘기는 코드가 추가되면 `.clear()`(in-place)와 `= {}`(rebind)의 차이가 발현. 현재는 외부 레퍼런스 0 → 무관. 한계로 기록(미래 코드 추가 시 재검토).
3. **빈 window 가 수 초인 이유 = clear 와 재할당 사이 await.** clear 가 `_scan_universe()` 호출 *전*(시작부)이고 재할당은 fetch loop *후*라, await 구간 전체가 빈 window. 더 짧게 하려면 "로컬 dict 빌드 후 끝에서 atomic swap" 이 이론상 안전하나 **스코프 확장 + 형제 전략과 불일치**. 빈 window 가 stale window 보다 항상 안전(잘못된 매수 0)하므로 **현 스코프(시작부 clear) GO**, atomic-swap 은 선택적 미래 정제로만 기록(불요).
4. **momentum 제외 타당.** momentum 은 prepare 없음(실시간) → 3-dict 무관 → 스코프 제외 정당.

---

## 7. 후속 검증 권고 (tdd-engineer Red 설계 / tester)

tdd-engineer 가 Red 에서 직접 검증할 행위(의제별):

- **G-180-EMPTY-GATE (의제1):** VB/LTV prepare 1회차에 universe A 구성(`_open_confirmed[A]["main"]=True` 시뮬) → 2회차 prepare(clear 포함) universe B(A 미포함) → `_targets`/`_open_confirmed`/`_prev_price` 에 A 잔존 0 AND B 만 존재. + 재prepare 가 empty-gate(`get_scanned_tickers()` 빈 경우만) 임을 호출 카운트로 검증.
- **G-180-CONFIRM-PRESERVE (의제1):** 같은 종목 X 가 2회 prepare 모두 포함 시, prepare 가 `_open_confirmed[X]={}` 재할당함을 확인(clear 유무로 결과 불변 = 동등성). 즉 clear 가 confirmed 보존/소실에 **차이를 만들지 않음**을 단언.
- **G-180-LIMITUP-EXCLUDE (의제2, HIGH):** LTV `_limit_up_reached={X}` + 보유 X 상태에서 prepare 호출 → prepare 후 `X in _limit_up_reached` 유지 AND `check_force_clear()` 가 X 제외 AND `check_exit_signal(X)` 익일 모드 분기 유지. (clear 가 `_limit_up_reached` 를 절대 안 비움 단언.)
- **G-180-NDC-EXCLUDE (의제2):** `_next_day_clear_pending=True` 상태에서 prepare → True 유지 단언.
- **G-180-EVENING-INTERACT (의제3):** 16:20 evening prepare 시뮬 → 보유 종목 check_exit/force_clear 가 prepare 중(빈 `_targets`) 호출돼도 정상 청산 신호(3-dict 무참조 확인). + stale 종목이 evening prepare 후 `_targets` 에서 제거됨.
- **G-180-ZERO-CANDIDATES (의제4):** prepare 가 retry cap3 후 0건 → `_targets=={}` AND `check_buy_signal(아무종목)` == NONE(전일 타겟 매수 0건 단언).
- **G-180-PREVPRICE-NOFALSE (의제5-가):** `_prev_price` clear 후 첫 틱(target 이상 가격)에서 거짓 BUY 미발생 단언(self-heal).
- **G-180-SAFETY (전역, HIGH):** `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` == 0 라인. VB/LTV `check_exit_signal`/`check_force_clear` 본체 3-dict 미참조 AST 가드. (cycle 173/148/170 SAFETY 패턴 답습.)
- **합성 시계열(tester 인계):** "전일 종목 잔존 → 오늘 전일타겟 돌파 매수" 회귀 재현 시계열(전일 universe A, 오늘 universe B, A 의 전일 target_price 를 넘는 틱 주입 → cycle 180 적용 시 A 매수 0건 / 미적용 시 A 매수 발생)으로 결함→시정 효과 직접 입증.

**운영 검증(D+1):** push 후 첫 영업일 09:00:05~09:35 VB/LTV `get_scanned_tickers()` 가 당일 universe 와 일치(전일 잔존 0) + funnel step1 후보가 전일과 독립적으로 재구성됨을 Supabase `strategy_funnel_snapshots` / 라이브 로그로 확인.

---

## 8. 최종 권고

**5개 의제 전부 GO.** 스코프(VB/LTV `prepare()` 시작부 `_targets`/`_open_confirmed`/`_prev_price` 3줄 clear, `_limit_up_reached`/`_next_day_clear_pending` 제외)는 트레이더 관점·코드 정합 양면에서 정당하다. 핵심 근거:
1. empty-gate 가 intraday 시가확정 손실을 구조적으로 차단(전제 모순으로 시나리오 미실재).
2. prepare 의 종목별 `_open_confirmed[ticker]={}` 재할당이 clear 전후 동등성 보장.
3. 청산경로(check_exit/force_clear)가 3-dict 를 미참조 → 보유 종목 절대 안전.
4. `_limit_up_reached`/`_next_day_clear_pending` 제외가 상한가 익일청산 안전성의 필수 조건.
5. donchian/BFB/VCP 가 **이미** 동일 컨벤션(`_candidates={}`) → 신규 위험이 아닌 정합성 복원.

**유일 조건부 인지사항:** 장중 EC2 재시작 후 16:20 immediate-run 의 수 초 빈 window(§3-나/반례1). negligible + 기존 운영정책으로 완화. 별도 코드 대응 불요(인지로 충분).

**별건 인계(스코프 외):** `_limit_up_reached` 가 `_reset_daily_state`에도 누락된 선재 latent 버그(§5-라) — team-leader 검토 권고.
