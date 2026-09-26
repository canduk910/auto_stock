# cycle369 명세 — 관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단(지정 첫날 포함)

- 작성: domain-expert(명세 저자) · 2026-09-26(토, 휴장) · HEAD `e8198993` · 범위 = 구현 명세. `src/` 무수정 · 운영 DB 읽기 전용 조회 4회(EC2 컨테이너 asyncpg) · KIS 호출 0 · 커밋 없음
- 설계 정본: [`_workspace/domain_consult/cycle369_status_51_59_exit.md`](../domain_consult/cycle369_status_51_59_exit.md)(이하 「자문」). 이 명세는 자문 §4 를 **그대로 채택**하고, 아래 세 곳만 바꾼다.
  1. 자문 §4(c) 「새 차단 목록은 두지 않는다」 → **폐기**. 사용자 답(2026-09-26 11시 ①) 「지정 첫날 매수를 막는거지」로 **당일 매수 차단 장치를 새로 넣는다**(§4).
  2. 자문 §4(a) 판정식의 `iscd` 는 **전용 플래그가 비어 있을 때만** 쓴다(자문은 단순 OR). 근거 §2.
  3. 킬스위치를 둘로 나눈다. 청산은 `status_exit_mode`, 매수 차단은 `status_buy_block_mode` 다(§5).
- 사용자 결정 원문
  - 2026-09-25 21:5x: 「관리종목51과 단기과열59가 발동했는데 해당 종목을 보유하고 있으면 시장가로 청산하게 하고 재구독 중지등으로 신규매수를 중단하자.」
  - 2026-09-26 11시: ② 신규 매수는 「당일 재매수 차단(`is_sold_today`) + 신규 진입 필터」로 막는다. 구독 해제는 하지 않고, 보유 종목은 그대로 시장가로 청산한다. ① 「지정 첫날 매수를 막는거지」 → 보유하지 않은 후보의 지정 첫날(T+1) 매수도 막는다.
  - 「1. 369사이클 진행 시작하자.」

---

## 0. 결론

1. **청산은 자문대로 한다.** 새 leaf `src/engine/status_exit_watch.py` 가 보유 종목을 REST `FHKST01010100` 으로 읽고, KRX 정규장 **09:00:30~15:28** 안에서 읽은 값이 관리 또는 단기과열이면 `order_engine.execute_sell(t, Signal.STATUS_EXIT, sid)` 를 시장가로 부른다.
2. **첫날 매수 차단 = 「그날 라이브로 읽은 상태가 관리·단기과열이면 그날 그 종목의 매수 신호를 막는다」.** 판정은 매 영업일 새로 한다. 그래서 첫날만이 아니라 지정 기간 내내 막는다. 다음 날 진입 필터가 이미 걸러 주는 날에는 이 장치가 할 일이 없을 뿐이다.
3. **막는 자리 = `StrategyBase._account_soft_gate_blocked` 의 첫 문장**(`strategy_base.py:1286`, 8영역 밖). 7전략의 `check_buy_signal` 이 모두 이 게이트를 거친다는 것을 AST 가드(`test_cycle233_ast_account_risk.py`)가 이미 강제한다. 매수 경로 2곳(틱 `risk.py:770` · 스윙 REST `scheduler.py:2805`)이 전부 이 게이트를 지난다. 순수 메모리 조회라 A-PURE·A-ATOMIC 과 무관하다. `calc_buy_quantity` 앞에서 끝나므로 「투자금 부족」 쿨다운으로 잘못 기록되지 않는다. 게이트 위치(폴·래치형 5전략은 첫 문장, momentum·VB 는 발사 직전)도 그대로 물려받아 기준가가 얼지 않는다.
4. **읽는 시점.**
   - 08:45 에 장 전 1회 읽는다. 장 전 값은 전날 것일 수 있어 참고만 한다.
   - **09:00:00 에 장중 1회 전수**로 읽는다(후보 약 150~200종목, 약 24초).
   - 그 뒤 60초마다 새로 들어온 후보만 읽는다.
   - `condition.fetch_stock_detail` 에 **관측 훅**을 달아, 다른 경로가 이미 부르는 조회도 레지스트리에 기록한다.
     - 스윙 매수 폴: 매수 평가 직전에 조회한다.
     - VB·LTV 기준가 REST: 목표가를 세우기 직전에 조회한다.
     - momentum 급등 스캔: 후보로 받는 순간 조회한다.
   - 그래서 세 경로는 **추가 호출 0 으로, 결정적으로** 덮인다.
5. **아직 못 읽은 종목은 막지 않는다(fail-open).** 근거는 셋이다(§4.3).
   - 읽기 실패로 모든 매수를 멈추는 것은 허용하지 않는다(과제 조건).
   - 커버리지 표상 공백은 09:00:00~09:00:24 에 momentum 이 관리종목(연속매매)을 사는 경우뿐이다. 단기과열은 09:30 까지 체결이 없다.
   - 남는 누수는 청산 쪽이 300초 안에 판다(`bought_today=1` 로 드러난다).
6. **8영역 접촉 0.**
   - 바뀌는 파일: `strategy_base.py` · `condition.py`(훅 1곳) · `scheduler.py`(task 1줄 + 이름 3곳, 3,777 → 3,781줄) · `system_config.py` · `routes/system_integrations.py` · `models/system_integrations.py` · 새 leaf 1개.
   - 테스트: `tests/conftest.py`(autouse 중립화 1개) · `pyproject.toml`(마커 1개).
7. **`needs_user = false`.** 사용자 결정 범위 안에서 모두 정해진다. 새로 매매를 바꾸는 것은 「51·59 종목을 그날 사지 않는다」뿐이고, 이는 사용자 원문 「신규매수를 중단하자」와 같다.

---

## 1. 매수 경로 전수 (HEAD `e8198993`, 파일:행)

| 경로 | 종목이 들어오는 곳 | 신호 | 주문 |
|---|---|---|---|
| **틱 매수** `RiskManager.on_tick` | 구독 종목의 모든 틱. 전략 루프 `risk.py:642` `for strategy in self.registry.enabled()` | `risk.py:770` `strategy.check_buy_signal(...)` | `risk.py:773` `execute_buy` |
| ├ VB | `_targets` (`volatility_breakout.py:399` `_scanned_tickers = list(self._targets.keys())`, 멤버 확인 `:939`) | 발사 직전 게이트 `:974` | 〃 |
| ├ LTV | `_targets` (`long_tail_volatility.py:453`, 멤버 확인 `:795`) | 첫 문장 게이트 `:767` | 〃 |
| ├ BFB | `_candidates` (`bull_flag_breakout.py:513`, 멤버 확인 `:962`) | 첫 문장 게이트 `:947` | 〃 |
| ├ VCP | `_candidates` (`vcp_breakout.py:666`, 멤버 확인 `:1404`) | 첫 문장 게이트 `:1387` | 〃 |
| └ momentum | **후보 목록이 없다.** 구독 종목 중 `ticker_prev_close > 0` 이면 모두 평가한다(`momentum.py:153`). `ticker_prev_close` 를 채우는 곳은 급등 스캔(`condition.py:836`, `fetch_rising_stocks` → `fetch_stock_detail` `:829`)과 6전략 prepare(`vcp_breakout.py:592` 등 6곳)다 | 발사 직전 게이트 `:176` | 〃 |
| **스윙 REST 매수 폴** `_swing_buy_poll_loop` (`scheduler.py:2697`, 09:05~09:30) | donchian·kojiro `get_scanned_tickers()` (`:2766`). `_bought_today`(`:2775`)·`is_ticker_blocked_for_buy`(`:2779`) 로 거른 뒤 | `:2791` `fetch_stock_detail(t)` → `:2805` `check_buy_signal` (첫 문장 게이트 `donchian_swing.py:1620` · `kojiro.py:887`) | `:2818` `execute_buy` |
| 그 밖 | **없다.** `execute_buy` 호출부는 위 2곳뿐이다. `place_order` 의 BUY 는 `execute_buy` 안에만 있다(`order_engine.py:1416`·`:1532` 지정가 폴백). `routes/trading.py:166` 수동 주문은 SELL 전용이다 | — | — |

- donchian·kojiro 는 틱 매수 평가에서 빠진다(`risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES`, `:752`).
- 운영 DB 실측(2026-09-26, `strategy_config`): **7전략 모두 `tradable_boards=["main"]`** 이다. 코드 기본값과 달리 LTV 도 `pre_nxt`·`post_nxt` 가 꺼져 있다. 그래서 지금 운영에서 09:00 전 매수는 구조적으로 0 이다. 최근 30일 LTV 프리장 체결 8건은 전부 09-15 이전이다. BFB 는 `entry_start=09:05`, `entry_end=09:04` 라 진입 창이 없다.
- 과거 체결로 본 첫 매수 시각(최근 30일 BUY 체결): VB 는 대부분 09:00:35 이후다(09:00:29 1건은 cycle272 이전). BFB·donchian·kojiro 는 09:05:00, momentum 은 최초 09:00:33(08-27)이다.

---

## 2. 판정 규칙 (공통 순수 함수)

```python
# src/engine/status_exit_watch.py
def classify(output) -> StatusRead      # 순수, never-raise
```

| 필드 | 규칙 |
|---|---|
| 정규화 | 값이 `str` 이면 `.strip().upper()` 를 한다. `"Y"`/`"N"` 만 유효하다. 그 밖의 문자열은 **None 으로 취급**하고 `unknown_values` 에 원문을 담는다(→ `[status_exit_unknown_value]`) |
| `mang` | `mang_issu_cls_code` (관리) |
| `short_over` | `short_over_yn` (단기과열 **지정·연장**. 예고는 `N` 이다. 자문 §2.3 실측) |
| `iscd` | `iscd_stat_cls_code` (strip) |
| `managed` | `mang == "Y"` **or** (`mang is None` **and** `iscd == "51"`) |
| `overheat` | `short_over == "Y"` **or** (`short_over is None` **and** `iscd == "59"`) |
| `halted` | `iscd == "58"` or `temp_stop_yn == "Y"` |
| `flags_missing` | `(mang is None and iscd != "51") or (short_over is None and iscd != "59")` |
| `price_ok` | `stck_prpr` 가 양의 정수 문자열 |
| `fetch_fail` | 호출 예외 · 응답이 dict 가 아님 · output 이 비어 있음 |
| `iscd_conflict` | (`mang == "N"` and `iscd == "51"`) or (`short_over == "N"` and `iscd == "59"`) → 판정은 플래그를 따르고 `[status_exit_iscd_conflict]` INFO 를 1회/일 남긴다 |

**쓰지 않는 것**(자문 K1·K2·K10):
- `ssts_hot_yn` — 공매도과열이다.
- master `short_over_cls_code` — `1` 은 예고다.
- `stock_master.raw`/`master_raw` DB 값 — 하루 늦다.
- `H0UNMKO0` 프레임 단독 — 힌트로만 쓴다.

**자문 대비 변경 — `iscd` 는 전용 플래그가 비었을 때만 쓴다.**
- 자문 실측(09-23 스냅샷)은 51 ⊆ 관리(100/100), 59 ↔ `short_over_yn=Y`(10/10)라 두 식의 결과가 같다.
- 그러나 `scanner.py:3594` 의 cycle203 실측 주석은 「51=정상 ETF/스팩/우선주」라고 적었다. 51 이 관리 아닌 종목을 담던 시기가 있었다는 뜻이다.
- 매도는 틀리면 비싸다. 그래서 명시적인 `"N"` 을 `iscd` 가 뒤집지 못하게 한다. 실측 데이터에서는 결과가 같고 더 안전하다.

**경로별 해석**(같은 `StatusRead` 에서):

| 용도 | 해당 | 모름 | 해당 없음 |
|---|---|---|---|
| 청산(§3) | `(managed or overheat) and not halted and price_ok and not fetch_fail` → 발사 후보 | `fetch_fail or not price_ok or (flags_missing and not (managed or overheat))` | 그 밖 |
| 청산 대기 | `(managed or overheat) and halted` → `[status_exit_wait_halt]` | — | — |
| 매수 차단(§4) | `managed or overheat` (가격·정지와 무관. 막는 쪽이라 보수적으로 둔다) | `fetch_fail or (flags_missing and not (managed or overheat))` | 그 밖 = **판정 완료(clean)** |

자문 §2.3 실측 응답 7건이 A 테스트의 픽스처다(§9).

---

## 3. 보유 청산 (sell side) — 자문 §4(a)(b)(e)(g)(h) 확정본

| 항목 | 값 |
|---|---|
| 대상 | `registry.all()` 의 모든 전략(**꺼진 전략 포함**)의 `state.positions` 중 `quantity > 0`. 종목별 조회는 1회, 판정은 (전략, 종목)마다 |
| 조회 | `condition.fetch_stock_detail(t)` 만 쓴다(시세 풀 · 5초 TTL · 단일 비행). 직접 `kis_*` 호출 0 |
| 장 전 arm | §4.3 P0 패스(08:45, 또는 `pre_nxt` 활성이면 07:59)에서 해당이면 `[status_exit_armed] src=rest phase=pre` 만 남긴다. **주문 0** |
| 발사 창 | **`09:00:30 <= now < 15:28:00` KST.** 창 밖(프리장·15:28~·애프터 16:00~20:00)은 주문하지 않는다(자문 K4·K5) |
| 발사 조건 | 창 안 **이번 패스의 조회값**이 발사 후보 ∧ 모드 `enforce` ∧ `t not in order_engine._selling`(읽기만) ∧ 그날 발사 횟수 < **3** |
| 발사 | `await order_engine.execute_sell(t, Signal.STATUS_EXIT, sid)`. **`limit_price` 인자 없음 = 시장가.** 거래소는 `execute_sell` 이 정한다(09:00~20:00 `krx_by_clock` → KRX). `[status_exit_fire]` 는 **await 전에** 남긴다. 발사 횟수 증가도 await 전에 한다. 예외는 흡수하고 `[status_exit_fire_error]` 를 남긴다. `CancelledError` 는 re-raise 한다 |
| 주기 | 창에 처음 들어오는 반복에서 즉시 1회(09:00:30 또는 재시작 시각). 그 뒤 격자 `09:00:30 + k·300s` 의 다음 칸마다. 마지막 칸은 15:25:30. 하루 약 78회 × 보유 12 ≈ **940콜**(스윙 60초 REST 폴과 5초 캐시로 일부 겹친다) |
| 정지 겹침 | `halted` 면 대기한다(`[status_exit_wait_halt]` 1회/일). 다음 패스에서 풀리면 발사한다 |
| 해제 | arm 된 종목이 창 안 조회에서 해당 없음 → `[status_exit_disarmed]` |
| 모름 | 발사 0 · `[status_exit_unknown]` 1회/일. 다음 패스에서 다시 읽는다 |
| 상한 | (날짜, 종목)당 3회. 초과하면 `[status_exit_giveup]` CRITICAL 1회/일. 카운터 키에 날짜가 있어 `_reset_daily_state` 는 무접촉이다 |
| 프레임 힌트 | 패스에서 `market_operation_monitor.get_last_event(t)` 를 **읽기만** 한다. `iscd_stat_cls_code in {"51","59"}` 이면 `[status_exit_frame_hint]` 1회/일(자문 §4(a)) |
| 새 타이머 | **금지**(자문 K9). 30분 단일가 대기는 기존 `selling_reconcile` 의 열린 주문 보존에 맡긴다 |
| 구독 | **무접촉.** leaf 에 `src.realtime` import 0 · `unsubscribe` 토큰 0(자문 K7) |

`Signal.STATUS_EXIT = "STATUS_EXIT"` 를 `strategy_base.Signal` 에 추가한다(`FORCE_CLEAR` 다음 줄). `signal.value` 는 로그에만 쓰인다(자문 §4(e)). src 에 Signal→라벨 매핑이나 멤버 전수 열거는 없다(grep 0건).

---

## 4. 당일 매수 차단 (buy side) — 신규

### 4.1 무엇을 막나

- **대상 판정**: 그날(KST 날짜) 라이브 FHKST 조회에서 `managed or overheat` 이면 그날 그 종목의 **신규 매수 신호**를 7전략 모두에서 막는다.
- **막지 않는 것**: 청산·손절·트레일링·익일청산·15:20 강제청산. 게이트는 `check_buy_signal` 안에만 있어 청산 경로와 구조적으로 무관하다. 구독도 건드리지 않는다.
- **이미 있는 두 장치와의 관계**:
  - 판 종목의 당일 재매수 → `is_sold_today`(무변경).
  - 다음 날부터 → 진입 필터 `_is_master_blocked_for_entry`(무변경).
  - 이 장치는 그 두 장치가 못 보는 **「오늘 막 지정된 비보유 후보」** 를 덮는다.
  - 매일 새로 읽으므로 진입 필터가 늦는 날도 덮는다. 예: 관리종목 master 파일이 하루 늦으면 둘째 날까지 필터를 통과할 수 있다(자문 §9③ 미판별).

### 4.2 누구를 읽나 — `buy_targets(registry)` 와 비용

```
buy_targets = (
    ⋃ enabled 전략 s: set(s.get_scanned_tickers()) ∪ keys(getattr(s, "_targets", {})) ∪ keys(getattr(s, "_candidates", {}))
  ∪ (keys(scanner.ticker_prev_close)  if momentum 이 enabled)      # momentum 평가 우주의 상위집합
) − { t : registry.is_ticker_blocked_for_buy(t) }                   # 보유·주문중·당일매도 = 어차피 못 산다
  − { t : not (len(t) == 6 and t.isdigit()) }                        # 진입은 6자리 숫자만
```

- 모든 private 속성은 `getattr(..., default)` 로 방어적으로 **읽기만** 한다(선례: `open_price_rest._pending_main_tickers` 가 `_targets`·`_open_confirmed` 를 읽는다).
- `scanner` 는 **함수 안에서 lazy import** 한다(8영역 파일을 읽기만 하고 수정하지 않는다).
- **우선순위(P1 정렬)**:
  - ① momentum 급등 목록 = `ticker_prev_close` 키 중 어느 전략 후보에도 없는 것. +29% 에 가장 가깝다.
  - ② BFB·VCP 후보.
  - ③ VB·LTV `_targets`.
  - ④ donchian·kojiro 후보.
  - 같은 순위 안에서는 종목코드 오름차순이다(결정적).

**비용 실측**(운영 DB, `strategy_funnel_snapshots.step_no=99`, 09-14~09-23 영업일 8일):

| 날짜 | 6전략 후보 합집합 | VB∪LTV | BFB∪VCP | donchian∪kojiro |
|---|---|---|---|---|
| 09-23 | 139 | 101 | 45 | 14 |
| 09-22 | 143 | 106 | 39 | 16 |
| 09-18 | **175** | 141 | 29 | 12 |
| 09-15 | 126 | 96 | 24 | 16 |

- momentum 급등 목록: 스캔 1회당 등락률 15%+ 종목이 18~23개다(EC2 로그 09-22·09-23, 하루 123회 스캔).
- ⇒ **P1 대상 ≈ 150~200종목.**
- 페이싱 = `open_price_rest` 선례 `_TICKER_SLEEP_S=0.05`. 실측 R1 은 79콜에 9.3초였다(≈118ms/종목, 09-23 로그). ⇒ **200종목 ≈ 24초.**

| 패스 | 콜/일 |
|---|---|
| P0 장 전(보유+후보) | 160~210 |
| P1 09:00:00 전수 | 150~200 |
| INC 60초 증분 | 0~20 |
| 청산 패스(§3) | ≈940 |
| **합계(신규)** | **≈1,300~1,400** |

- 관측 훅이 거두는 스윙 폴(09:05~09:30)·기준가 REST(R1 79콜 + 뒤 라운드)·급등 스캔은 **이미 나가는 호출**이라 추가 0 이다.

### 4.3 언제 읽나 — 패스·관측 훅·미검사 처리

**용어**:
- **장중 판정(in-session)** = 그날 `now.time() >= 09:00:00` 에 읽은 **판정 완료**(해당 또는 clean) 조회. 모름은 판정이 아니다.
- **장 전(pre-session)** = 그 전의 조회. KIS 장 전 값이 그날 것인지 전날 것인지 모른다(자문 §9②).

| 패스 | 시각 | 대상 | 규칙 |
|---|---|---|---|
| **P0** | 08:45:00. 단, **enabled 전략 중 `tradable_boards` 에 `pre_nxt` 가 있으면 07:59:00**(`pre_pass_time(registry)`, 순수) | 보유 ∪ `buy_targets` | 장 전 기록. 해당이면 **장 전 차단**을 건다(보수적). clean 은 「판정 완료」로 치지 않는다. 재시작이 P0 시각~09:00 사이면 즉시 1회 |
| **P1** | 09:00:00 (재시작이 09:00~15:20 이면 즉시) | `buy_targets` − 오늘 장중 판정 완료 | P1 은 날마다 1회. 패스 벽시계 상한 **25초**(다음 청산 패스를 늦추지 않게). 못 읽은 나머지는 INC 로 넘어간다 |
| **INC** | P1 뒤 60초마다, `< 15:20:00` (momentum·VB·LTV 매수 컷 `BUY_CUTOFF_KST=15:20`) | `buy_targets` − 오늘 장중 판정 완료 − 모름 3회 소진 | 대상이 0 이면 호출 0 이다. BFB·VCP 의 장중 재-prepare(`scheduler._reprepare_breakout_if_empty`)로 새로 들어온 후보를 여기서 읽는다 |
| **관측 훅** | 항상 | `condition._fetch_stock_detail_and_cache` 가 **새로 조회할 때마다** | 같은 레지스트리에 기록한다(아래). 캐시 적중 경로는 부르지 않는다. 그 응답은 처음 조회할 때 이미 기록됐다 |

**레지스트리 갱신 규칙** `record_read(ticker, read, *, now, src)` (관측 훅·P0·P1·INC·청산 패스 공용, never-raise):
1. 6자리 숫자가 아니면 무시한다.
2. 모름이면 `(날짜, 종목)` 시도 횟수 +1, `[status_block_unknown]` 1회/일. 상태는 바꾸지 않는다. 3회가 되면 그날 INC 대상에서 뺀다(`giveup=1`).
3. 장 전이면 측정용 `pre_seen[t]=(날짜, 해당?)` 를 기록한다. 해당이면서 그날 항목이 없으면 `phase=pre` 차단을 만들고 `[status_block_armed] phase=pre`.
4. 장중 판정이면 `in_seen[t]=날짜` 를 기록한다.
   - 해당 → 그날 항목이 없거나 `phase=pre` 면 `phase=in` 으로 만들거나 승격한다. `[status_block_armed] phase=in`. P0 가 이 종목을 봤다면 `[status_block_pre_session_check] pre=Y|N in=Y` 를 남긴다(자문 §9② 의 직접 측정).
   - clean → 그날 `phase=pre` 항목이면 **해제**하고 `[status_block_released] reason=pre_session_stale`. `phase=in` 항목이면 **유지**(그날 고정)하고 `[status_block_flip_ignored]` 1회/일.

**경로별 커버리지 — 「읽기 전에 매수가 먼저 나갈 수 있나」**

| 경로 | 첫 매수 가능 시각 | 그 전에 반드시 일어나는 조회 | 결정적? |
|---|---|---|---|
| VB·LTV `main` (`open_price_scope_mode=enforce`, 운영 DB 둘 다 enforce) | 09:00:35 R1 이후. 목표가는 REST 확정으로만 선다(`open_price_rest.py:554` 조회 → `:571` `on_open_price_confirmed`) | 같은 조회가 관측 훅을 먼저 지난다 | **예**(추가 콜 0) |
| donchian·kojiro | 09:05~09:30 스윙 폴 | `scheduler.py:2791` 조회 → 훅 → `:2805` 신호 | **예**(추가 콜 0) |
| momentum · 급등 목록 | 후보로 받은 뒤 | `condition.py:829` 조회 → 훅(받는 순간) | **예**. 단, 장 전 스캔으로 받은 종목은 장 전 기록이라 P1 이 다시 읽는다 |
| momentum · 다른 전략 후보(구독 ∩ prev_close) | 09:00:00 이후 두 번째 틱 | P1(우선순위 ①~③) | 시각 의존. 공백 ≈ 09:00:00~P1 도달(최대 약 24초) |
| BFB·VCP | 09:05 (운영 DB `entry_start`) | P1(09:00:24 전후 완료) | 사실상 예(5분 여유) |
| LTV `pre_nxt`·`post_nxt` | 운영 DB 에서 **꺼져 있다** | 켜면 P0 가 07:59 로 당겨진다. 장 전 값의 신선도는 모른다 | 조건부(§12) |

**단기과열(59)은 공백이 사실상 0 이다.**
- 지정되면 정규장이 **30분 단일가**다(자문 §2.5 KRX 규정).
- 09:00 시가 단일가 뒤 다음 체결은 09:30 이다. momentum 은 첫 틱을 기록만 하고(`momentum.py` 「첫 tick은 기록만」), VB 돌파에는 목표가 위 틱이 필요하다.
- 그래서 09:30 전에는 어떤 틱 매수도 날 수 없고, 그때는 P1 이 끝난 지 오래다.
- 남는 공백은 **관리(51, 연속매매)가 지정 첫날 09:00:00~09:00:24 에 momentum 임계(+29%)를 넘는 경우**뿐이다. 관리종목 지정 첫날의 +29% 급등은 드물다.

**못 읽은 종목 = fail-open(막지 않는다).** 근거:
- (a) 과제 조건이다. 「확인될 때까지 모든 매수를 막는 것은 허용되지 않는다」.
- (b) fail-closed 로 두면 시세 풀 장애 하나로 7전략의 매수가 모두 조용히 멈춘다. 매수를 막는 통제가 결측에서 막으면 안 된다는 프로젝트 원칙과 같은 방향이다(루트 CLAUDE.md ρ축 「키 부재=OFF」 근거, 「유령 키가 두 전략을 전 기간 체결 0건」).
- (c) 위 표상 공백이 구조적으로 작다.
- (d) 새는 경우에도 청산 쪽이 다음 패스(≤300초)에서 팔고, `[status_exit_fire] bought_today=1` 로 드러난다.

### 4.4 막는 자리 (choke point) — 결정과 기각안

**채택: `StrategyBase._account_soft_gate_blocked` 첫 문장에 상태 검사를 얹는다.**

```python
# src/engine/strategy_base.py
def _account_soft_gate_blocked(self, ticker: str | None = None) -> bool:
    """(기존 docstring) + cycle369 — 공통 신규 매수 게이트: 종목상태(관리·단기과열) 당일 차단을 먼저 본다."""
    if self._status_buy_blocked(ticker):     # ← 첫 문장 (AST 가드 J25)
        return True
    ... 기존 본문 byte 동일 ...

def _status_buy_blocked(self, ticker: str | None) -> bool:
    """cycle369 — 관리종목·단기과열 당일 매수 차단(지정 첫날 포함). 순수 메모리 조회.
    fail-open(판정 예외 → False). leaf 는 lazy import(순환 차단). 로그는 leaf 가 남긴다."""
    if not ticker:
        return False
    try:
        from src.engine import status_exit_watch
        return bool(status_exit_watch.buy_gate(ticker, self.strategy_id))
    except Exception:
        logger.debug("[status_block_gate_failed] ticker=%s", ticker, exc_info=True)
        return False
```

채택 이유:
1. **모든 매수 경로를 덮는다.** 매수 신호의 호출부는 `risk.py:770`·`scheduler.py:2805` 두 곳이다. 7전략의 `check_buy_signal` 은 모두 이 게이트를 거친다. 이것은 기존 AST 가드 G-1(`test_cycle233_ast_account_risk.py`: 첫 문장 5전략 · 발사 직전 2전략)이 **이미 강제**하고, 새 전략도 이 게이트 배선이 의무다(`strategies/CLAUDE.md:170`). 새 전략이 생겨도 상태 차단이 자동으로 따라온다.
2. **기준가 동결이 없다(자문 K13 신설).** momentum·VB 는 게이트가 **발사 직전**(기준가 갱신 뒤)에 있다(C233-F1). 장 전 차단이 장중 clean 으로 풀려도 거짓 돌파가 나지 않는다. 최상단이나 `risk.on_tick` 에서 `continue` 로 막으면 `_prev_price`/`_prev_prdy_rate` 가 얼어 해제 뒤 첫 틱이 거짓 돌파가 된다.
3. **「투자금 부족」 오귀인이 없다(K14).** 신호가 `Signal.NONE` 이면 `execute_buy`·`calc_buy_quantity` 가 불리지 않는다. 따라서 `block_low_funds`(`order_engine.py` 「매수 수량 0 → cooldown」)도 없다. `signal_count_today` 도 늘지 않는다.
4. **A-PURE·A-ATOMIC 무관.** `_apply_budget_limit` 호출 그래프 밖이고 동기다. `buy_gate` 는 dict 조회 + 날짜 비교 + 상한 걸린 로그뿐이다(await·DB·HTTP 0, AST J23).
5. **8영역 0.** `strategy_base.py` 는 8영역이 아니다.

기각안:

| 안 | 기각 이유 |
|---|---|
| (B) 7전략 `check_buy_signal` 에 게이트를 한 줄씩 새로 추가 | 전략 7파일 + 핀 7종을 바꾸고 배치 규약(첫 문장/발사 직전)을 새로 검증해야 한다. 이미 강제되는 공통 게이트를 두고 중복이다 |
| (C) `registry.is_ticker_blocked_for_buy` 에 추가 | 8영역(`strategy_registry.py`)이다. `risk.py:723` 에서 `check_buy_signal` **앞** `continue` 라 momentum·VB 기준가가 언다(K13). 스윙 폴 필터(`:2779`)에서 조회 자체가 빠져 관측 훅도 못 탄다 |
| (D) `order_engine.execute_buy` 머리 | 8영역이다. 신호가 이미 발사된 뒤라 `signal_count_today` 가 오염되고 LLM 셰도 평가가 헛돈다 |
| (E) `calc_buy_quantity`/`_apply_budget_limit` 에서 0 반환 | 「매수 수량 0 → 900s cooldown」 = 투자금 부족으로 오귀인된다(과제 금지). A-PURE 관문 안이다 |
| (F) 후보 dict(`_candidates`/`_targets`)에서 제거 | momentum 은 후보 목록이 없어 못 막는다. 전략 내부 상태를 외부에서 바꾼다. 재-prepare 가 다시 넣는다 |

**`condition.py` 관측 훅**(자문 §4(f) 목록 밖 · 8영역 밖 — 결정성을 위해 넣는다):

```python
# src/api/condition.py — _fetch_stock_detail_and_cache 안, `output = data.get("output", {})`(:484) 바로 다음 · 캐시 lock 앞
        _notify_status_observer(ticker, output)   # cycle369

def _notify_status_observer(ticker: str, output) -> None:
    """cycle369 — 종목상태(관리·단기과열) 관측 훅. 매수 차단 레지스트리에 기록만 한다. never-raise.
    api→engine lazy import 선례 = 이 파일 `fetch_rising_stocks` 의 `from src.engine.scanner import ticker_prev_close`."""
    try:
        from src.engine import status_exit_watch
        status_exit_watch.observe_fhkst(ticker, output)
    except Exception:
        logger.debug("[status_observer_failed] ticker=%s", ticker, exc_info=True)
```

- 훅이 없으면 VB·LTV·스윙·momentum 신규 후보의 커버리지가 「P1/INC 가 먼저 도착하느냐」 에 달린다. 훅이 있으면 그 세 경로가 **호출 0 으로 결정적**이 된다.
- 🔴 훅이 예외를 흘리면 모든 FHKST 소비자가 깨진다. 그러면 VB·LTV 목표가가 영영 서지 않는다(K19). **이중 try**(훅 + leaf 내부)가 계약이다.
- 기존 가드 `test_ga3_4`(시장분류 `"J"` dict 상수)와 cycle282 H5(`is_market_open`·`next_trading_day` 세그먼트 핀)는 영향이 없다.
- 팀장이 §4(f) 목록 엄수를 택하면 이 훅을 빼도 된다. 그러면 위 세 경로가 「P1/INC 도착 순서」로 강등되고(§4.3 표의 「예」 3칸이 「시각 의존」이 된다), J13·J14·J15 가 기대값을 바꾼다. **권고는 넣는 쪽이다.**

### 4.5 차단 수명

- 항목 키 = `(KST 날짜, 종목)`. 게이트는 `entry.day != today` 면 무시한다(**지연 만료**). `_reset_daily_state`·`OrderEngine.reset_daily_state` 는 무접촉이다.
- P0 가 다른 날짜의 항목·시도 횟수·로그 상한을 비운다(메모리 위생).
- 그날 안에서:
  - 장 전 차단은 장중 clean 이면 풀린다.
  - 장중 차단은 그날 풀리지 않는다(보수적. 지정·해제는 다음 날 효력이라 장중에 풀릴 일이 없다).
- 다음 날부터 이어지는 장치:
  - 매일 P1 이 다시 읽는다.
  - 진입 필터: 59 는 raw `short_over_yn`(16:10 갱신), 51 은 master `mang_issu_yn`(16:30).
  - 판 종목은 `is_sold_today`.

### 4.6 게이트 계약 `buy_gate(ticker, strategy_id) -> bool` (hot path)

```
e = _buy_flags.get(ticker)            # 해당 종목만 들어 있다 → 대부분 miss 로 즉시 False
if e is None: return False
if e.day != _now_kst().date(): return False
mode = _buy_mode                       # 메모리 캐시(§5)
if mode == "off": return False
if mode == "observe": [status_block_buy_would_skip] 1회/(날짜,종목,전략); return False
[status_block_buy_skip] 1회/(날짜,종목,전략); _skip_counts[(날짜, 종목, 전략)] += 1; return True
```
전체를 `try/except Exception → False` 로 감싼다. await·DB·HTTP·`write_log` 0 이다(AST J23). 로그는 `logger.info` 만 쓴다(동기). 영속 기록은 패스가 `[status_block_summary]` 로 남긴다(§6).

---

## 5. 킬스위치 + 라우트

| 키 (`system_config`, JSONB `{"value": str}`) | 대상 | 값 | 키 없음 | 알 수 없는 값 | DB 조회 실패 |
|---|---|---|---|---|---|
| `status_exit_mode` | 청산(§3) | `enforce`·`observe`·`off` | **enforce** (사용자 결정 「시장가로 청산」) | **observe** + `[status_exit_mode_invalid]` 1회/일 | **직전 값 유지**(처음이면 enforce) |
| `status_buy_block_mode` | 매수 차단(§4) | 〃 | **enforce** (사용자 결정 ① 「지정 첫날 매수를 막는거지」) | observe + 〃 | 〃 |

- **둘로 나누는 이유**: 롤백 시나리오가 다르다. 판정이 틀려 잘못 팔 때는 청산만 끄고 차단은 남기는 편이 싸다. 차단이 과잉일 때는 차단만 끈다. 한 키면 한쪽 사고에 다른 쪽 보호까지 잃는다.
- **「키 없음 = enforce」 가 ρ축 관례(키 없음 = OFF)와 반대인 이유**:
  - ρ축은 구성상 모든 랏에 걸리는 통제라 유령 키가 전략 전체를 멈춘다.
  - 이 차단은 **라이브 조회가 양성인 종목에만** 걸린다. 결측이면 fail-open 이라 전체 정지 경로가 없다.
  - 사용자가 명시로 켜기로 결정했다.
- `observe` 의미:
  - 청산: 읽고 판정하되 발사 대신 `[status_exit_would_fire]`.
  - 매수: 읽고 기록하되 게이트는 False + `[status_block_buy_would_skip]`.
- `off` 의미: 그 축의 조회 패스를 돌지 않는다(청산 = 보유 조회 0, 매수 = P0 후보·P1·INC 조회 0). 관측 훅 기록은 계속한다(비용 0, GET 에서 「켜면 무엇이 막히나」를 보여 준다). 게이트는 False 다.
- **새로 읽는 시점**: task 시작 직후 1회, 그리고 **모든 패스 시작 시**. 09:00~15:20 에는 60초 이내다. SQL UPDATE 도 그 안에 반영된다.
- `system_config.py` 에 추가: `get_status_exit_mode_raw()`·`set_status_exit_mode(mode)`·`get_status_buy_block_mode_raw()`·`set_status_buy_block_mode(mode)`.
  - getter 는 `_select_value` 를 직접 쓴다. 키 없음 → `None` · 값 → `str` · **DB 예외는 삼키지 않고 전파**한다.
  - leaf 가 예외를 「직전 값 유지」로 처리한다. `_get_string_or_none` 은 예외를 None 으로 삼켜 「키 없음 = enforce」 와 구분할 수 없어서 쓰지 않는다.
- **라우트** `src/routes/system_integrations.py` (prefix `/api/integrations`, 선례 `/buy-block`·`/api/realtime/tick-channel-mode`):
  - `GET /api/integrations/status-exit` → `ApiResponse.data`:
    - `sell_mode`·`buy_block_mode`(메모리 현재값) · `stored`{두 키의 DB 값 또는 null} · `default`·`valid_modes`·`config_keys`
    - `fire_window`: leaf 상수를 문자열로 바꾼 값(라우트에 시각 리터럴 금지)
    - `today`: `status_exit_watch.snapshot()` = {`blocks`: [ticker·reason·phase·src·at·cand·skips{sid:n}], `armed`: [ticker·strategy·reason·state·fires·last_fire_at], `passes`: {kind: at·targets·read·flagged·unknown·fetch_fail·truncated·elapsed_ms}}
  - `PUT /api/integrations/status-exit` 바디 `StatusExitModeRequest{sell_mode: Optional[str], buy_block_mode: Optional[str]}`(`src/models/system_integrations.py`):
    - 둘 다 없으면 **422**. 준 값이 어휘 밖이면 **422**(아무것도 바꾸지 않는다).
    - 각 키를 DB 에 저장한다(실패 시 `persisted=false`, 그래도 메모리 반영은 한다 — 사고 중 `off` 가 먼저다).
    - `status_exit_watch.apply_mode(kind, mode)` 로 **즉시 반영**한다.
    - `[status_exit_mode] sell_mode= buy_block_mode= persisted=` WARNING. 응답 = GET 모양 + `persisted`.
  - 인증: 기존 `ApiAuthMiddleware` + 상태변경 Origin 검사가 그대로 적용된다(추가 작업 0). 프론트 소비처가 없어 `e2e/fixtures/api-mocks.ts`·`frontend/src/types` 는 무변경이다.

---

## 6. 관측 마커

로그 상한 키는 전부 날짜를 포함한다(`DailyEmitCap` 재사용, 키 `(날짜, …)`). 관측 실패는 흡수하고 판정·발사에 영향을 주지 않는다.
- 영속: `write_log` 는 async 패스에서만 부른다.
- 동기 경로(훅·게이트)는 `logger` 만 쓴다. `_DbLogHandler` 가 INFO+ 를 system_logs 로 best-effort 큐잉하지만 09:00 폭주 때 큐(10,000)가 넘칠 수 있다.
- 그래서 매수 차단의 사실은 패스가 `[status_block_summary]` 로 `write_log` 한다.

| 마커 | 레벨·경로 | 상한 | 필드 |
|---|---|---|---|
| `[status_exit_armed]` | INFO | (날짜,종목,사유) 1회 | `ticker= strategy= reason= iscd= mang= short_over= src=rest\|frame phase=pre\|in at=` |
| `[status_exit_disarmed]` | INFO | 1회/일 | |
| `[status_exit_fire]` | **WARNING logger + `write_log`** | 발사마다(≤3/일) | `ticker= strategy= reason=managed\|overheat\|managed+overheat iscd= mang= short_over= qty= mode=enforce attempt=n bought_today=0\|1` |
| `[status_exit_fire_error]` | WARNING | 발사마다 | 예외 타입·메시지 150자 |
| `[status_exit_would_fire]` | WARNING logger + `write_log` | 1회/일 | observe |
| `[status_exit_wait_halt]` | INFO | 1회/일 | `iscd=58\|temp_stop` |
| `[status_exit_unknown]` · `[status_exit_unknown_value]` · `[status_exit_iscd_conflict]` | INFO | 1회/일 | 응답 None · 규칙 밖 원문 · 플래그↔iscd 충돌 |
| `[status_exit_frame_hint]` | INFO | 1회/일 | 프레임 `iscd_stat_cls_code` |
| `[status_exit_giveup]` | **CRITICAL logger + `write_log`** | 1회/일 | `fires=3` |
| `[status_exit_summary]` | INFO | 청산 패스마다 | `held= checked= flagged= fired= halted= unknown= fetch_fail= mode=` |
| `[status_block_armed]` | **WARNING** logger | (날짜,종목) 1회 | `ticker= reason= phase=pre\|in src=fetch\|p0\|p1\|inc\|sell iscd= mang= short_over= cand=0\|1` (`cand` = 그 순간 enabled 전략 후보인가 → 진입 필터 누락 빈도) |
| `[status_block_released]` | INFO | 1회/일 | `reason=pre_session_stale` |
| `[status_block_flip_ignored]` | INFO | 1회/일 | 장중 해당 뒤 장중 clean |
| `[status_block_pre_session_check]` | INFO | (날짜,종목) 1회 | `pre=Y\|N\|none in=Y` — 자문 §9② 측정 |
| `[status_block_buy_skip]` | INFO | (날짜,종목,전략) 1회 | `ticker= strategy= reason= phase=` |
| `[status_block_buy_would_skip]` | INFO | 〃 | observe |
| `[status_block_unknown]` | INFO | 1회/일 | `attempts= reason=fetch_fail\|empty\|flags_none giveup=0\|1` |
| `[status_block_pass]` | INFO | P0·P1 항상, INC 는 read>0 일 때 | `kind=p0\|p1\|inc targets= read= flagged= unknown= fetch_fail= skipped_seen= truncated= elapsed_ms= mode=` |
| `[status_block_summary]` | **`write_log` WARNING** | 패스 끝, 차단 집합 또는 skip 카운트가 바뀌었을 때만 | `day= blocked=N tickers=t:reason,… skips=sid:n,… mode=` |
| `[status_exit_mode]` · `[status_exit_mode_invalid]` | WARNING | 변경마다 / 1회/일 | |
| `[status_exit_loop_exit]` | INFO | 1회/일 | `reason=running_false\|after_close` (liveness) |
| `[status_block_gate_failed]` · `[status_observer_failed]` | **DEBUG** | — | fail-open 흔적(hot path 라 INFO 금지) |

---

## 7. 파일 변경 목록 · 8영역 · scheduler · 핀

| 파일 | 변경 | 분류 |
|---|---|---|
| **신규** `src/engine/status_exit_watch.py` | 상수·`classify`·`record_read`·`observe_fhkst`·`buy_gate`·`buy_targets`·`pre_pass_time`·`due_actions`(순수 planner)·`run_pre_pass`/`run_buy_pass`/`run_sell_pass`·`task_loop(sched)`·`refresh_modes`/`apply_mode`/`current_modes`·`snapshot`·`reset_state_for_test`·`_now_kst()` seam. **모듈 최상위 import = 표준 라이브러리만**(asyncio·logging·dataclasses·datetime·collections·typing). `condition`·`scanner`·`system_config`·`system_logs`·`market_operation_monitor`·`strategy_base.Signal` 은 전부 함수 안 lazy import(순환 차단 · `condition`·`strategy_base` 가 이 모듈을 lazy import 한다) | 비8영역 |
| `src/engine/strategy_base.py` | `Signal.STATUS_EXIT` 1줄 · `_status_buy_blocked` 신규 · `_account_soft_gate_blocked` 첫 문장 2줄 + docstring 1줄 | 비8영역. whole-file sha 핀 재핀 |
| `src/api/condition.py` | `_notify_status_observer` 신규 + `_fetch_stock_detail_and_cache` 안 호출 1줄 | 비8영역(자문 §4(f) 목록 밖, §4.4 근거) |
| `src/engine/scheduler.py` | `start()` 의 `:768`(`_main_rest_basis_task` 생성) 다음 줄에 `self._status_exit_task = asyncio.create_task(status_exit_watch.task_loop(self))  # cycle369 …` + 모듈 상단 `:43` `from src.engine import market_op_subscribe, quote_token_refresh` 줄 끝에 `, status_exit_watch` 를 덧붙인다(새 줄 0. leaf 최상위가 표준 라이브러리만이라 순환 없음) + task_attrs 튜플 3곳(`:1062`·`:1189`·`:1225`)의 `_main_rest_basis_task` 줄 다음에 `"_status_exit_task",  # cycle369 …` 각 1줄 | **승인 대상**(사용자 승인 「369사이클 진행」 + 자문 §4(f)). **3,777 → 3,781줄**(+4). 상한 3,900 이내 |
| `src/db/system_config.py` | 키 상수 2 + getter/setter 4 | 비8영역 |
| `src/routes/system_integrations.py` | GET/PUT `/status-exit` | 비8영역 |
| `src/models/system_integrations.py` | `StatusExitModeRequest` | 비8영역 |
| `tests/conftest.py` | autouse `_neutralize_status_watch`: 매 테스트 전 `reset_state_for_test()` + 마커 `real_status_watch` 가 **없으면** `observe_fhkst`→no-op, `buy_gate`→`False` 로 monkeypatch. 선례 = `_neutralize_api_auth`·`_neutralize_market_rest`. **이유(K20)**: 레지스트리는 모듈 전역이다. api 테스트가 `short_over_yn:"Y"` 픽스처로 `005930` 을 기록하면, 같은 날짜로 도는 `test_cycle233_watcher_gate.py:266`(`_account_soft_gate_blocked("005930") is False`)가 뒤집힌다 | 테스트 |
| `pyproject.toml` | `markers` 에 `"real_status_watch: 종목상태 매수차단 중립화 픽스처 옵트아웃 (leaf·배선 직접 검증)"` — `filterwarnings=error` 라 **Red 와 같은 커밋**에 넣는다 | 테스트 설정 |

**8영역 접촉 0**:
- 무변경: `risk.py`·`order_engine.py`·`session.py`·`scanner.py`·`strategy_registry.py`·`api/order.py`·`src/realtime/**`·`src/auth/**`.
- 새 코드가 8영역을 **부르거나 읽는** 곳은 셋뿐이다: `order_engine.execute_sell`·`order_engine._selling`·`registry.is_ticker_blocked_for_buy`·`scanner.ticker_prev_close` 읽기(모두 공개 호출이거나 읽기 전용).
- 추가로 무변경: `market_operation_monitor.py`·`market_operation.py`(`get_last_event` 읽기만) · 전략 7파일(무변경 — 게이트가 공통이라서다) · `src/realtime/CLAUDE.md`(수정 금지).

**핀 재핀 절차**(`feedback_rerun_suite_after_edit`):
- 구현이 끝난 뒤 **전체 백엔드 스위트**를 돌린다.
- 붉어진 sha 핀은 **바뀐 파일이 위 목록 안인지 확인한 뒤 값만** 옮긴다. 각 줄에 `# 🔁 cycle369 재핀 — <파일> <무엇>` 주석을 단다.
- 예상 군:
  - `test_cycle287_ast_scope.py`: `_SRC_TREE_FILES` 158→159 · `_PINNED_DIR_FILE_COUNTS["src/engine"]` 80→81 · `_SRC_TREE_DIGEST` · **`_SCHEDULER_LINES` 3777→실측**
  - `strategy_base.py`·`scheduler.py` whole-file 핀 군(grep 결과 cycle274·276·278·282·286·287·290·291·293·294·297 등 약 11+10곳)
  - scheduler 세그먼트 핀(cycle264·269·272·292·295·298 등, 해당 시)
- 8영역 sha 핀(`test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS` 절차)은 **움직이면 안 된다.** 움직이면 설계 위반이다.
- 재핀 뒤 전체 스위트를 한 번 더 돌린다. 영향 인덱스는 `python tools/test_impact/build_index.py` 만 다시 만든다(프론트 무변경).

---

## 8. 크리티컬 분기 (자문 K1~K12 승계 + 신설)

| # | 분기 | 틀리면 | 막는 것 |
|---|---|---|---|
| K1~K12 | 자문 §5 그대로(공매도과열 오독 · 예고 오독 · 51 단독 · 애프터 발사 · 장 전 발사 · None 오독 · 구독 해제 · 정지 반복 발사 · 단일가 대기 오판 · DB 판정 · 「바로」 차이 · 「재구독 중지」 차이) | — | §2·§3 |
| K3' | **`iscd` 가 명시 `N` 을 뒤집음**(자문의 단순 OR) | cycle203 이 본 「51=정상 ETF/스팩/우선주」 류가 섞이면 시장가 오매도 | 플래그 우선 · iscd 는 None 폴백(§2) + 충돌 마커 |
| K13 | **momentum·VB 게이트를 최상단이나 `risk.on_tick` 으로 옮김** | 기준가 동결 → 장 전 차단 해제 뒤 첫 틱 거짓 돌파(추격 상한 없는 매수) | 공통 게이트(발사 직전) 재사용 + 기존 AST G-1 + J11 |
| K14 | **수량 0 반환으로 차단** | 「매수 수량 0 → 900s cooldown」 = 투자금 부족 오귀인 | 신호 단계 차단 + J12 |
| K15 | **미검사 = 차단(fail-closed)** | 시세 풀 장애 → 7전략 매수 전면 정지(무증상) | fail-open + §4.3 커버리지 |
| K16 | **장 전 clean 을 「판정 완료」로 셈** | 장 전 값이 전날 것이면 P1 이 그 종목을 건너뛰어 첫날을 놓친다 | 장중 판정만 `in_seen` · J3 · 돌연변이 M24 |
| K17 | **차단이 다음 날까지 남음** | 해제된 종목을 이유 없이 계속 막는다 | 날짜 키 지연 만료 · J9 |
| K18 | **`is_ticker_blocked_for_buy`(8영역)에 넣음** | 8영역 접촉 + K13 + 스윙 폴 조회가 사라져 훅 커버리지 상실 | 기각(§4.4) |
| K19 | **관측 훅이 예외를 흘림** | 모든 FHKST 소비자 사망 → VB·LTV 목표가 영구 미확정, 스윙 매수·손절 폴 정지 | 이중 try · J16 · M23 |
| K20 | **테스트 간 레지스트리 누수** | 무관한 테스트의 `_account_soft_gate_blocked("005930")` 가 True 가 되어 CI 붉음(시각·순서 의존 flaky) | autouse 중립화 + 옵트아웃 마커 · J27 |
| K21 | **P1 이 청산 첫 패스를 밀어냄** | 09:00:30 청산이 P1 완료까지 지연 | 패스 벽시계 상한 25초 · J18 |
| K22 | **게이트에서 `write_log`/DB 호출** | hot path 에 await → 틱 처리 지연. `check_buy_signal` 은 동기라 호출 자체가 불가하거나 fire-and-forget 누수 | 게이트는 logger 만 · AST J23 |
| K23 | **보유 종목을 매수 차단 대상 조회에 넣음 / 꺼진 전략 후보를 넣음** | 불필요한 호출. 꺼진 전략은 사지 않는다 | `buy_targets` 규칙 · J17 |

---

## 9. Red 테스트 시나리오 (tdd-engineer)

- 공통 규약:
  - 새 테스트 모듈은 `pytestmark = pytest.mark.real_status_watch` 를 단다.
  - 시각은 freezegun 또는 `status_exit_watch._now_kst` monkeypatch 로 고정하고, **경계 양쪽**을 잰다(`feedback_time_window_gate_tests`).
  - caplog 는 WARNING 이상이거나 `caplog.set_level(logging.INFO, logger="src.engine.status_exit_watch")` + 마커 prefix 로 단언한다.
  - 픽스처 원문 = 자문 §2.3 실측 7건.

**A. 분류 `classify`** (자문 A1~A10 승계 + 변경분)
- A1 294140(`iscd=51`, mang Y) → managed.
- A2 016790(`iscd=58`, mang Y) → managed ∧ halted → 청산 발사 금지 · 매수 차단 대상.
- A3 005160·000545 → overheat.
- A4 356680 예고(`short_over=N`, iscd 57) → 해당 없음.
- A5 043090(플래그 None · 가격 0) → 청산 모름 · 매수 모름. 「해당 없음」 처리 금지.
- A6 `ssts_hot_yn=Y` 만 있는 응답 → 해당 없음.
- A7 iscd 52/53/54/55/57/00 → 해당 없음.
- A8 `"y"`·`" Y "` → Y.
- A9 `"1"` → None 취급 + unknown_value.
- A10 managed+overheat → `reason=managed+overheat`.
- **A11** mang None + iscd 51 → managed(폴백).
- **A12** mang `"N"` + iscd 51 → **해당 없음** + `iscd_conflict`.
- **A13** short_over None + iscd 59 → overheat.
- **A14** 응답 비-dict · 빈 dict → fetch_fail.

**B. 발사 창** (자문 B1~B5)
- B1 08:59:59 해당 → `execute_sell` 0회, armed 1.
- B2 09:00:29 → 0회 / 09:00:30 → 1회.
- B3 15:27:59 → 1회 / 15:28:00 → 0회.
- B4 16:30(`is_production=True`) → 0회.
- B5 07:50·20:30 → 0회.

**C. 확인 두 번** (자문 C1~C3)
- C1 P0 해당 → 09:00:30 재조회 clean → 0회 + disarmed.
- C2 프레임 59, REST `N` → 0회 + frame_hint.
- C3 REST 예외 → 0회. 다음 패스에서 다시 읽는다.

**D. 발사 계약** (자문 D1~D7)
- D1 인자 `(ticker, Signal.STATUS_EXIT, sid)` · `limit_price` 키워드 **없음**.
- D2 꺼진 전략 보유도 대상.
- D3 포지션 없음 / `quantity=0` → skip.
- D4 `_selling` 안 → skip.
- D5 4번째 패스 → 0회 + giveup CRITICAL 1회.
- D6 날짜가 바뀌면 카운터를 새로 센다.
- D7 halted → 0회 + wait_halt, 다음 패스에서 풀리면 1회.
- **D8** `bought_today=1`(buy_date == 오늘) 필드.
- **D9** `execute_sell` 예외 → 흡수 + fire_error, 루프 생존.
- **D10** `[status_exit_fire]` 가 `execute_sell` await **전에** 기록된다(모의 `execute_sell` 이 첫 줄에서 hang).

**E. 모드** (자문 E1~E5 + 축 분리)
- E1 `status_exit_mode=off` → 보유 FHKST 0콜.
- E2 observe → would_fire, `execute_sell` 0회.
- E3 알 수 없는 값 → observe + invalid 마커.
- E4 DB 예외 → 직전 값 유지.
- E5 키 없음 → enforce.
- **E6** `status_buy_block_mode=off` → P0 후보·P1·INC 0콜, 게이트 False, 관측 훅 기록은 유지(snapshot 에 보임).
- **E7** 두 축 독립: 청산 off + 차단 enforce → 차단만 동작 / 역으로도.
- **E8** getter 가 DB 예외를 **전파**한다(키 없음 None 과 구분).

**F. 비간섭 (AST/구조)** (자문 F1~F5)
- F1 leaf 에 `src.realtime` import 0 · `unsubscribe` 토큰 0.
- F2 leaf 가 `order_engine` 에서 쓰는 속성은 `execute_sell`·`_selling` 뿐.
- F3 8영역 파일 diff 0(`_EIGHT_AREAS` git diff) + **8영역 파일에 `status_exit_watch` 토큰 0**.
- F4 leaf 의 DB 쓰기는 `write_log` 뿐 · `system_config` 쓰기 0(쓰기는 라우트만).
- F5 **양성 대조군**: managed 픽스처에서 발사가 실제로 일어난다.
- **F6** leaf 에 `kis_request`·`kis_get_quote`·`httpx` 토큰 0. 조회는 `fetch_stock_detail` 만.
- **F7** leaf 모듈 최상위 import 는 표준 라이브러리만.

**G. 통합 청산** (실제 `execute_sell` + `place_order` 모의)
- G1 10:05 59 종목 → `ORD_DVSN="01"` · KRX(NXT 기반 종목 포함).
- G2 APBK1943 → 지정가 5호가 폴백 1회.
- G3 APBK0918 → 포지션 보존, 다음 패스 재발사(상한 안).

**H. 재매수 회귀**
- H1 체결 뒤 같은 날 `is_ticker_blocked_for_buy` True.
- H2 다음 날 prepare 에서 raw `short_over_yn=Y` · master `mang_issu_yn=Y` 제외. 기존 테스트가 있는지 먼저 확인하고, 없으면 추가한다.

**J. 당일 매수 차단 (신규)**
- **J0 첫날 시나리오 통합**: T일 후보가 진입 필터 통과(raw `short_over_yn=N`) → T+1 09:00:00 P1 조회가 `short_over_yn=Y` → 그 종목 틱 `RiskManager.on_tick` 에서 VB·momentum 이 돌파해도 `execute_buy` 0회. 양성 대조: 같은 설정에서 `N` 이면 `execute_buy` 1회.
- J1 장중 해당 기록 → 7전략 모두 `buy_gate` True, `[status_block_armed] phase=in` 1회.
- J2 P0 해당(08:45) → 09:00 전 게이트 True → 09:00:05 장중 clean → 해제(False) + released.
- J3 P0 clean + 장중 해당 → P1 이 **그 종목을 반드시 다시 읽는다** → 차단 + `pre_session_check pre=N in=Y`.
- J4 모름(043090) → 게이트 False(fail-open) + unknown, 다음 INC 에서 재조회, 3회 뒤 giveup(INC 대상 제외).
- J5 `ssts_hot_yn=Y` 만 → 차단 0.
- J6 예고(356680) → 차단 0.
- J7 A11·A13 폴백 → 차단.
- J8 게이트: enforce True / observe False + would_skip / off False / `buy_gate` 예외 → `_status_buy_blocked` False + DEBUG 흔적 / `ticker=None` → False.
- J9 D일 차단이 D+1 에 적용되지 않는다(freezegun 날짜 이동, reset 호출 없이).
- **J10 7전략 배선(양성·음성)**: 7전략 × `check_buy_signal` 을 `test_cycle233_watcher_gate.py::TestR7StrategyWiring` 모양으로 파라미터화한다. 계좌 게이트 off + 상태 차단 on → 전부 `Signal.NONE`. **양성 대조**: 차단 off 에서 donchian(09:10, 후보 정보·가격 조건 충족)이 `Signal.BUY`. 대조군 없이 부정 단언만 두면 본체가 사라져도 초록이다.
- J11 **edge 전략 기준가**: momentum. 장 전 차단 중 임계 교차 틱 → NONE. 장중 clean 으로 해제 → 다음 틱이 임계 위에 머물러 있어도(새 교차 없음) NONE(거짓 돌파 없음). VB 도 같은 모양(`_prev_price` 갱신 확인).
- J12 **오귀인 없음**: 차단 종목 틱 → `execute_buy` 미호출 · `state.is_low_funds_blocked(ticker)` False · 「매수 수량 0」 로그 0 · `signal_count_today` 불변.
- J13 **스윙 폴 결정성**: `_swing_buy_poll_loop` 1사이클(09:10 고정, `kis_get_quote` 모의 → `mang_issu_cls_code:"Y"`), **P1/INC 미실행 상태**에서 `execute_buy` 0회. 양성 대조 `N` → 1회.
- J14 **기준가 REST 결정성**: `run_main_rest_basis_round` R1(09:00:35), VB 후보 응답 `short_over_yn:"Y"` → `on_open_price_confirmed` 는 일어난다(목표가는 선다). 이어진 돌파 틱에서 VB `check_buy_signal` NONE · `[status_block_armed] src=fetch`.
- J15 **momentum 받는 순간**: `fetch_rising_stocks`(09:40) 응답 관리 Y → 기록 `phase=in` → momentum 교차 → NONE.
- J16 **훅 안전**: `observe_fhkst` 가 raise 해도 `fetch_stock_detail` 은 output 을 돌려주고 캐시에 쓰며 호출자는 정상이다. 캐시 적중 경로에서는 훅이 호출되지 않는다. AST: 훅 호출이 `_fetch_stock_detail_and_cache` 안 `output` 대입 **뒤**에 있고, `_notify_status_observer` 본문은 lazy import + `try/except Exception` 이다.
- J17 `buy_targets`: enabled 전략 후보 ∪ `ticker_prev_close`(momentum enabled 일 때만) − 보유·주문중·당일매도 − 비6자리 숫자. 꺼진 전략 후보는 제외. 우선순위 ①급등 목록이 맨 앞.
- J18 P1 벽시계 상한 25초 → `truncated=1`, 나머지를 다음 INC 가 읽는다. 09:00:30 청산 패스가 P1 때문에 25초 넘게 밀리지 않는다(planner 단위).
- J19 모름 재시도 상한 3회/일.
- J20 `pre_pass_time`: 기본 08:45 / enabled 전략의 `tradable_boards` 에 `pre_nxt` → 07:59 / 꺼진 전략의 `pre_nxt` 는 무시.
- J21 **재시작**: 10:30 에 task 시작 → 즉시 P1 + 즉시 청산 패스. 08:50 시작 → 즉시 P0. 15:40 시작 → 조회 0, `loop_exit reason=after_close`.
- J22 **영속**: 차단이 생긴 패스 끝에 `[status_block_summary]` 가 `write_log` 로 1회(모의 캡처). 변화가 없으면 0회.
- J23 **순수성 AST**: `buy_gate`·`observe_fhkst`·`record_read`·`classify` 에 `Await`·`AsyncFunctionDef` 0 · `write_log`·`pg.`·`kis_`·`fetch_` 호출 0. `StrategyBase._status_buy_blocked` 에 Await 0 · import 는 함수 안.
- J24 기존 A-GATE·A-PURE·A-ATOMIC(`test_budget_limit_ast.py`) 무변경 초록.
- J25 **AST**: `_account_soft_gate_blocked` 의 첫 문장(docstring 제외)이 `if self._status_buy_blocked(ticker): return True`.
- J26 `planner due_actions`: 07:44 → [] / 08:45:00 → pre / 09:00:00 → buy_open / 09:00:30 → sell / 09:01:00(P1 끝난 뒤) → inc / 15:20:00 → inc 없음 / 15:25:30 → sell / 15:28:00 → sell 없음 / 15:30 → exit.
- J27 **누수 방지**: autouse 중립화 아래에서 api 테스트 모양으로 `short_over_yn:"Y"` 를 흘려도, 다음 테스트의 `_account_soft_gate_blocked("005930")` 가 False(두 테스트를 한 모듈에 순서대로).

**R. 라우트**
- R1 GET 모양(키 전수 · `fire_window` 는 leaf 상수 유래 · `today` 스냅샷).
- R2 PUT `{"sell_mode":"observe"}` → DB 저장 + 메모리 즉시 반영 + 응답 에코 + WARNING 마커.
- R3 어휘 밖 → 422, 아무것도 안 바뀜.
- R4 빈 바디 → 422.
- R5 DB 쓰기 예외 → 메모리 반영, `persisted=false`.
- R6 `buy_block_mode` 만 PUT → sell 무접촉.
- R7 라우트 파일에 `HH:MM` 시각 리터럴 0.

**S. scheduler 배선**
- S1 `start()` 가 `_status_exit_task` 를 만든다.
- S2 기존 task-cancel AST 가드(cycle79·83·89·101 계열)가 새 속성을 요구하고, 세 튜플 모두에 있다.
- S3 `_SCHEDULER_LINES` 실측 < 3,900.

---

## 10. 돌연변이 (각각이 죽어야 한다 — 적어도 하나의 테스트가 붉어진다)

| # | 돌연변이 | 죽이는 테스트 |
|---|---|---|
| M1 | 플래그 `== "Y"` → `!= "N"` (None → 해당) | A5·J4 |
| M2 | `ssts_hot_yn` 포함 | A6·J5 |
| M3 | 예고 포함(`short_over_cls_code != "0"` 등) | A4·J6 |
| M4 | iscd 폴백 제거(플래그만) | A11·A13·J7 |
| M5 | iscd 무조건 OR(명시 `N` 도 뒤집음) | A12 |
| M6 | 전용 플래그 제거(iscd 만) | A2(016790 iscd 58) |
| M7 | 발사 창 시작 09:00:30 → 09:00:00 | B2 |
| M8 | 발사 창 끝 `<` → `<=` 15:28 | B3 |
| M9 | 창 판정 제거(애프터 발사) | B4 |
| M10 | halted 무시 | A2·D7 |
| M11 | 창 안 재조회 생략(P0 arm 으로 발사) | C1 |
| M12 | 발사 상한 제거 | D5 |
| M13 | 발사 카운터 날짜 키 제거 | D6 |
| M14 | `_selling` 검사 제거 | D4 |
| M15 | `limit_price=` 전달 | D1 |
| M16 | `registry.enabled()` 로 청산 대상 축소 | D2 |
| M17 | 게이트가 모름을 차단 | J4 |
| M18 | 게이트 날짜 비교 제거 | J9 |
| M19 | `_account_soft_gate_blocked` 첫 문장 제거 | J10·J25·J0 |
| M20 | `_status_buy_blocked` 예외 시 True(fail-closed) | J8 |
| M21 | observe 가 차단 | E2·J8 |
| M22 | off 인데 조회 | E1·E6 |
| M23 | `condition.py` 훅 호출 제거 | J13·J14·J15 |
| M24 | 훅 예외 전파(`try` 제거) | J16 |
| M25 | 장 전 clean 을 `in_seen` 에 기록 | J3 |
| M26 | 장 전 차단이 장중 clean 으로 안 풀림 | J2 |
| M27 | 장중 차단이 장중 clean 으로 풀림(비고정) | J1 연장(flip_ignored) |
| M28 | `buy_targets` 가 보유·꺼진 전략 후보 포함 | J17 |
| M29 | 모름 재시도 상한 제거 | J19 |
| M30 | 키 없음 → observe/off | E5 |
| M31 | 알 수 없는 값 → enforce | E3 |
| M32 | P1 벽시계 상한 제거 | J18 |
| M33 | `[status_exit_fire]` 를 `execute_sell` await 뒤로 | D10 |
| M34 | 게이트에서 `write_log` 호출 | J23 |
| M35 | autouse 중립화 제거 | J27 |

---

## 11. 롤백 · 배포

- **즉시(재시작 없음)**: `PUT /api/integrations/status-exit` `{"sell_mode":"off"}` 및/또는 `{"buy_block_mode":"off"}`(또는 `observe`). SQL UPDATE 도 다음 패스(≤60초, 09:00~15:20)에 반영된다.
- **코드 롤백**: 커밋 revert → full 배포(backend 재시작). 창 = 15:30~16:00 · 21:35~익일 07:45 · 주말. **보유가 있으면 KRX 장중 push 금지(D6)** · 20:00~21:35 push 금지(D8).
- DB 스키마 변경 0. `system_config` 행은 PUT 이 처음 불릴 때만 생긴다. 롤백 때 지울 필요가 없고, 키가 남아도 코드가 없으면 무해하다.
- 배포 모드: `src/` 변경이라 **full**. 첫 배포는 주말이나 평일 21:35 뒤가 좋다. 배포 뒤 첫 영업일 08:45~09:05 에 `[status_block_pass] kind=p0|p1`·`[status_exit_summary]` 가 한 줄씩 나오는지 확인한다(자문 §9④).

---

## 12. 반례 · 한계

- **장중 새 지정**: P1 뒤 장중에 지정되는 관리종목은 INC 가 이미 판정한 종목을 다시 읽지 않아 놓친다. 다만 보통 거래정지(58)와 함께 와서 매수 자체가 불가하고, 다음 날 P1 이 잡는다.
- **장 전 신선도 미판별**(자문 §9②): `pre_nxt` 매수를 다시 켜면 08:00~09:00 커버리지는 장 전 FHKST 가 그날 값을 주느냐에 달린다. `[status_block_pre_session_check]` 가 첫 지정 사건일에 답을 준다.
- **`open_price_scope_mode=off` 롤백 중**: VB·LTV 목표가가 WS 로 서면 결정적 커버리지가 P1 도착 순서로 강등된다.
- **시세 풀 장애**: fail-open 이라 새 매수가 나갈 수 있다. 청산 쪽이 다음 패스에 판다(`bought_today=1`). 둘 다 장애면 다음 날 진입 필터가 막는다.
- **장중 고정**: KIS 가 한 번 잘못 `Y` 를 주면 그날 그 종목은 막힌다(보수적). `[status_block_flip_ignored]` 로 빈도를 잰다.
- **LLM 셰도 기록 공백**: 막힌 신호는 주문이 되지 않으므로 `llm_buy_evaluations` 에 행이 없다. 「주문 1건 = 1행」 계약과 일치한다.
- **추세 연장 손실·재개 단일가 최악가**: 자문 §7 그대로다.

---

## 13. 후속

| 누구 | 무엇 |
|---|---|
| tdd-engineer | §9 Red(마커 등록 + conftest 중립화를 같은 커밋에) |
| backend-dev | §7 파일만. `scheduler.py` 는 +4줄 |
| tester | §10 돌연변이 전수 + 전체 스위트 2회(재핀 전·후) |
| report-writer `/sync-docs` | `src/engine/CLAUDE.md` 새 leaf 절 · `strategies/CLAUDE.md:170` 공통 게이트에 상태 차단이 얹혔다는 한 줄 · `src/api/CLAUDE.md:264` 참조를 새 leaf 로 + `condition.py` 관측 훅 · `src/routes/CLAUDE.md` 새 라우트 · `src/db/CLAUDE.md` 키 2개 · 루트 CLAUDE.md 안전 규칙 한 줄(「51·59 청산은 KRX 정규장 09:00:30~15:28 만, 보유 구독 무접촉, 당일 매수 차단은 공통 게이트」) · `_workspace/00_leader_trading_rules.md`. **`src/realtime/CLAUDE.md` 는 건드리지 않는다** |
| 운영 실측 | 배포 첫 주 `[status_block_pass]` 의 `unknown`·`fetch_fail` 비율 · `[status_block_armed] cand=1` 건수(진입 필터 누락 = 첫날 공백의 실제 빈도) · `[status_exit_fire] bought_today=1` 건수(누수) |

---

## 부록 — 이번 명세의 실측 (읽기 전용, 2026-09-26)

- `strategy_config`(운영 DB): `tradable_boards` 7전략 모두 `["main"]`. BFB `entry_start 09:05 / entry_end 09:04` · VCP `09:05 / 14:30`. VB·LTV `open_price_scope_mode=enforce`. `enabled` 7전략 모두 True.
- `strategy_funnel_snapshots` step 99 후보 수(09-14~09-23): BFB 20~36 · donchian 0~6 · kojiro 8~17 · LTV 82~96 · VCP 1~14 · VB 56~81. 합집합 126~175.
- `trade_history` BUY 체결 최근 30일 시각 분포:
  - 09:00 전: LTV 8건(마지막 09-15).
  - 09:00~09:00:35: VB 1(09-04) · LTV 1(08-28).
  - 09:00:35~09:05: VB 16.
  - BFB·donchian·kojiro 최초 09:05:00. momentum 최초 09:00:33(08-27).
- EC2 로그: 급등 스캔 「등락률 15%+ 종목」 18~23개/회, 123회/일(09-22·09-23). R1 `calls=79 elapsed_ms=9331`(09-23).
- 코드 사실: `execute_buy` 호출부 2곳(`risk.py:773`·`scheduler.py:2818`) · `check_buy_signal` 호출부 2곳(`risk.py:770`·`scheduler.py:2805`) · 공통 게이트 7전략 배선(`kojiro.py:887`·`momentum.py:176`·`vcp_breakout.py:1387`·`volatility_breakout.py:974`·`long_tail_volatility.py:767`·`donchian_swing.py:1620`·`bull_flag_breakout.py:947`) · `scheduler.py` 3,777줄(`test_cycle287_ast_scope.py::_SCHEDULER_LINES = 3777`).
- 스크립트: 세션 scratchpad `c369s/p1~p4.py`.
