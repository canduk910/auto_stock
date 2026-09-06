# VB 목표가 "보드 시가" 출처 코드 추적 (읽기 전용)

작성 2026-09-06 · 리포 루트 `/Users/koscom/Projects/auto_stock` · HEAD `b985938`
모든 주장에 `파일:행` 근거. 리포/DB/설정 변경 0건, 운영 접근은 SELECT + `docker ps`/`docker logs` 뿐.

---

## 0. 결론 한 문장

VB 목표가의 시가는 **KRX 09:00 시가가 아니라 통합 시세 채널 `H0UNCNT0` 프레임의
`[7] STCK_OPRC`(= KRX+NXT **통합** 일-스코프 시가)** 이고, 09:00:05 스케줄러 확정
경로는 **운영 실측에서 VB 에 대해 0/55 확정**이라 실제 목표가를 확정하는 것은
`check_buy_signal` 안의 틱 폴백(`volatility_breakout.py:866-869`)이다.

---

## 1. VB 목표가 확정 경로 (전체)

### 1.1 목표가 산식

```
target_offset_base = int(prev_range × k)                 # volatility_breakout.py:307, 316-329
target_offset      = max(int(base × k_value_{board}), 0) # :804-807
target_price       = open_price + target_offset          # :809-813
```

- `prev_range` = 직전 완결 일봉의 `stck_hgpr - stck_lwpr` (`:290-294`), 일봉 소스는 DB
  `stock_master_daily` (`get_recent_daily_normalized`, `:166`).
- `k` = 노이즈 비율 평균 (`:271-287`).
- `k_value_krx_main` 운영 DB 실측 = **1.3** (VB), LTV = 1.0
  (`strategy_config.params`, 09-06 SELECT).
- **`open_price` 만이 런타임 입력**이다 — 나머지는 전부 07:55 prepare 시점 상수.

### 1.2 `open_price` 를 넣는 곳은 정확히 두 군데뿐

| # | 호출 지점 | 시가 값의 출처 | 스코프 |
|---|-----------|----------------|--------|
| A | `scheduler._confirm_breakout_open_prices` 1차 폴링 `scheduler.py:1650` | `scanner.ticker_prices[t]["open_price"]` | **통합(H0UNCNT0) `[7]`** |
| B | 같은 함수 2차 폴백 `scheduler.py:1665-1667` | REST `FHKST01010100` `output.stck_oprc`, `fid_cond_mrkt_div_code="J"` | **KRX** |
| C | `check_buy_signal` 인라인 폴백 `volatility_breakout.py:866-869` | `on_tick` 인자 `open_price` | **통합(H0UNCNT0) `[7]`** |

A 와 C 는 같은 값(통합 `[7]`)이고 B 만 스코프가 다르다.
`condition.py:439-444` 가 `"fid_cond_mrkt_div_code": "J"` 를 고정으로 보내고,
KIS 정본(`inquire_price.py` docstring, MCP `read_source_code` 실측)이
`J:KRX, NX:NXT, UN:통합` 이라고 명시한다 ⇒ **B 만 KRX 시가**다.

### 1.3 인라인 폴백(C)의 발동 조건 — 866-869 근방 정독

```python
# volatility_breakout.py:862-873
board = self._resolve_active_board()      # :862
if board is None:                          # :863-864  ← 폴백보다 먼저다
    return Signal.NONE
confirmed = self._open_confirmed.get(ticker, {}).get(board, False)   # :867
if not confirmed and open_price > 0:                                  # :868
    self.on_open_price_confirmed(ticker, open_price, board=board)     # :869
board_info = info.get("boards", {}).get(board)                        # :871
```

- 발동 조건 = ① 활성 보드가 `main`(VB `tradable_boards=["main"]`) ∧ ② 그 보드가
  아직 미확정 ∧ ③ 틱의 `open_price > 0`.
- **보드 해석이 폴백보다 앞**이므로 08:00~09:00 PRE_NXT 구간에는 VB 폴백이 아예 발동하지
  않는다(`_resolve_active_board` `:782-796` 이 `main` 만 허용 → None → early return).
- 발동하면 `_open_confirmed[t]["main"]=True` (`:814`) 가 되어 이후 A/B 경로가 그 종목을
  건너뛴다(`_is_confirmed` `scheduler.py:1616-1620`, 폴링 `:1646-1647`, 폴백 `:1655`).
  즉 **먼저 도착한 틱이 목표가를 확정하고 REST(KRX) 경로를 영구히 배제한다.**
- 예외적으로 `prepare()` 재실행(`:176-178` `_targets/_open_confirmed/_prev_price.clear()`)
  이 있으면 재확정 대상이 된다.

### 1.4 부수 계약

- `on_open_price_confirmed` 는 **첫 확정 보드의 값만** top-level(`open_price`/`target_price`)
  에 복사한다(`:816-820`) — 대시보드/AI 자문/`_emit_breakout_open_confirm` 이 그 값을 읽는다.
- 15:20 컷 `BUY_CUTOFF_KST`(`:27`)는 함수 **최상단**(`:828-847`)이며 `_prev_price` 갱신 이전
  = "컷 틱은 어떤 상태도 갱신하지 않는다"가 명시 계약(`:824-827` 주석).
- 계좌 SOFT 게이트는 **발사 직전**(`:887-892`) — 최상단 금지가 AST 로 봉인돼 있다
  (`tests/unit/ast/test_cycle233_ast_account_risk.py:32,97-122`).

---

## 2. `open_price` 역추적 — 통합 채널 `[7]` 이 무엇인가

### 2.1 파서

```python
# src/realtime/handler.py:273-281
def _parse_tick_prices(fields): return int(fields[2]), int(fields[7])
# :471  current_price, open_price = parsed
# :485-488 await _on_tick(ticker, current_price, open_price, change_rate, day_high=, acml_vol=)
```

- 구독 TR_ID 는 `scanner.py:502` `TICK_TR_ID = "H0UNCNT0"` **단일 활성 채널**이고,
  모든 구독이 이 상수를 쓴다(`scanner.py:1003,1011,1069,1099,1136`).
  `TICK_TR_ID_KRX = "H0STCNT0"`(`:503`)는 cycle257 이후 **미사용 예약 자리**다(`:498-504`).
- 따라서 실시간 경로의 시가는 **전부 통합 채널 `[7]`**이다.

### 2.2 KIS 정본 필드 배치 (MCP `read_source_code` 실측, 2026-09-06)

`ccnl_total`(H0UNCNT0) / `ccnl_krx`(H0STCNT0) 둘 다 46 컬럼, 0-index:

```
[0]MKSC_SHRN_ISCD [1]STCK_CNTG_HOUR [2]STCK_PRPR ... [7]STCK_OPRC [8]STCK_HGPR
[9]STCK_LWPR ... [13]ACML_VOL ... [24]OPRC_HOUR [25]OPRC_VRSS_PRPR_SIGN
[26]OPRC_VRSS_PRPR [27]HGPR_HOUR ... [33]BSOP_DATE [34]NEW_MKOP_CLS_CODE
... [43]HOUR_CLS_CODE [44]MRKT_TRTM_CLS_CODE [45]VI_STND_PRC
```

(두 채널의 유일한 차이는 index 21 `CNTG_CLS_CODE`(통합) vs `CCLD_DVSN`(KRX)이다.)
`handler.py:309-313` 의 로컬 주석과 일치한다.

### 2.3 통합 채널이 08:00 NXT 프리장부터 프레임을 보내는가 — **보낸다**

- 08:00~09:00 은 `MarketBoard.PRE_NXT` 구간(`session.py:63`)이고, 07:59 사전구독
  (`scheduler.py:747-757`)으로 VB/LTV 후보가 이미 등록돼 있다.
- `risk.on_tick` 은 보드 가드 **전에** `ticker_prices[ticker]` 를 무조건 갱신한다
  (`risk.py:493-499`) — 프리장 틱도 그대로 기록된다.
- 08:00:05 의 `_confirm_breakout_open_prices(board="pre_nxt")`(`scheduler.py:768`)는 LTV
  에만 적용되고 VB 는 `tradable_boards` 불일치로 제외된다(`scheduler.py:1607-1610`,
  회귀 `tests/unit/engine/scheduler/test_confirm_open_prices_main_only.py:76-123`).

### 2.4 그 `[7]` 이 NXT 시가인가 KRX 시가인가 — **리포 안에 이미 실측 반증이 있다**

`handler.py:60-67`(및 동일 문구 `tests/unit/realtime/test_cycle222a2_handler_hgpr_hour.py:5-15`):

> 통합 시세 채널(H0UNCNT0)의 일-스코프 필드는 **09:00 에 리셋되지 않는다**.
> 라이브 실측(000250 삼천당제약, 2026-08-21): **MAIN 구간 통합 틱의 일-스코프 시가 = 182,800**
> 인데 같은 날 KRX 일봉 O/H/L/C = 177,500/177,500/166,000/168,700 —
> 182,800 은 … **전일 종가와 정확히 일치**하는 08:00~09:00 NXT 프리장 기준가 체결이다.

- cycle222-a2 는 이 사실을 알고도 **`[8] 고가`에만** 스코프 필터
  (`_parse_day_high`, `[27] HGPR_HOUR` 09:00:00~15:30:00, `handler.py:284-396,110-111`)를 걸었다.
- **`[7] STCK_OPRC` 에는 어떤 스코프 필터도 없다** — 판별자 `[24] OPRC_HOUR` 는 소스 전체에서
  주석 1행(`handler.py:310`) 말고 **파싱조차 되지 않는다**(`grep fields\[24\]` 0건).
- 즉 고가에 대해 확인·시정된 오염이 시가에는 그대로 남아 있다. **가설이 아니라 같은 결함의
  미시정 잔여분**이다.

### 2.5 운영 실측 — 확증 (SELECT only)

`system_logs`(INFO 이상 `src.*` 자동 적재, `src/main.py:166-207`) 조회:

**(a) 09:00:05 확정 경로는 VB 에 대해 아무것도 확정하지 못한다**

```
09-03 09:00:12  [breakout_open_confirm] board=main strategy=volatility_breakout confirmed=0  empty=65
09-04 09:00:11  [breakout_open_confirm] board=main strategy=volatility_breakout confirmed=0  empty=55
09-03 09:35:23  [breakout_open_confirm] board=main strategy=volatility_breakout confirmed=65 empty=0
09-04 09:35:21  [breakout_open_confirm] board=main strategy=volatility_breakout confirmed=55 empty=0
```
(LTV 는 같은 시각 10~18/32~90 부분 확정.) 5초 폴링 + 55~65종목 REST 폴백이 **1초 만에**
끝나고 전부 0 — 폴백 예외는 `scheduler.py:1668` 이 `logger.debug` 로 삼킨다.
⇒ 09:00:05 경로는 VB 에 대해 **사실상 무동작**이고, 남은 확정자는 인라인 폴백(C)뿐이다.

**(b) 인라인 폴백이 쓴 시가 값 = 통합 `[7]`, KRX 시가와 불일치**

목표가 로그(`volatility_breakout.py:898-901`)에서 `open = target − int(int(prev_range×k)×1.3)`
로 역산(운영 `k_value_krx_main=1.3`):

| 일자 | 종목 | 로그 목표가 | 역산 board open | KRX 일봉 시가 | 전일 종가 | 판정 |
|------|------|-------------|-----------------|----------------|-----------|------|
| 09-03 | 086790 하나금융 | 137,799 | **134,900** | 136,100 | **134,900** | 전일종가와 **정확히 일치**, KRX 시가 아님 |
| 09-03 | 105560 KB금융 | 174,146 | **169,300** | 171,600 | 169,100 | 전일종가 +0.12%, KRX 시가 −1.34% |
| 09-04 | 000270 기아 | 131,019 | **128,200** | (09-04 행 placeholder) | 127,400 | 09:35 emit 샘플 `'000270': 128200` 과 **정확히 일치**(= 인라인 폴백이 확정한 값) |

09:35 emit 샘플 vs `stock_master_daily` 09-03 시가 직접 대조:

| 종목 | VB/LTV 기록 시가 | KRX 일봉 시가 | 차이 |
|------|------------------|----------------|------|
| 000270 | 125,500 | 124,900 | +0.48% |
| 000720 | 111,600 | 115,000 | −2.96% |
| 001820 | 114,000 | 114,000 | 일치 |
| 002990 | 17,350 | 17,350 | 일치 |
| 003160 | 30,200 | 30,500 | −0.98% |
| 000880 | 123,000 | 127,000 | −3.15% |
| 001450 | 52,900 | 52,000 | +1.73% |
| 003670 | 177,400 | 180,100 | −1.50% |

**일치하는 종목이 섞여 있다** — 프리장 체결이 없었던 종목은 통합 시가 = KRX 시가가 되기
때문으로 읽힌다(오염은 전수가 아니라 **프리장 체결이 있었던 종목 선택적**). 이는 검토가
보고한 "일부는 −231.9bp, 일부는 전일종가+offset 과 +2.5bp" 의 혼재 패턴과 정합한다.
⚠️ 단 `stock_master_daily` 의 **당일 행은 O=H=L=C=전일종가 placeholder** 라서 09-04 이후
비교는 이 표에 넣지 않았다(데이터 렌즈에서 별도 확인 필요).

---

## 3. 09:00 직후 타이밍

| 시각(KST) | 사건 | 근거 |
|-----------|------|------|
| 07:55 | `_boot` → VB `prepare()` — `_targets/_open_confirmed/_prev_price` clear 후 재구축 | `scheduler.py:56`, `volatility_breakout.py:176-178, 316-330` |
| 07:59 | 사전 구독(돌파+스윙+보유) | `scheduler.py:57, 747-757` |
| 08:00 | PRE_NXT 진입, `_confirm_breakout_open_prices(board="pre_nxt")` — **VB 제외** | `scheduler.py:58, 768`; `:1607-1610` |
| 08:00~09:00 | 통합 채널 프리장 틱 → `ticker_prices[t]["open_price"]` 에 **통합 `[7]`** 기록 | `risk.py:493-499` |
| 09:00:00 | `_BOARD_SCHEDULE` 상 MAIN 시작 | `session.py:65` |
| 09:00:00~+30s | **`session_tracker.active` 는 아직 `{PRE_NXT}` 일 수 있다** — `_session_loop` 가 `SESSION_TICK_INTERVAL=30`초 주기 stale 캐시 | `scheduler.py:76, 1215-1222`; `session.py:139-141, 163-168` |
| ↳ 그 동안 | VB `check_buy_signal` 은 `_resolve_active_board()==None` 으로 즉시 return — **확정도 매수도 없음** | `volatility_breakout.py:862-864` |
| 09:00:05 | `_confirm_breakout_open_prices(board="main")` (보드 인자 명시로 tracker race 우회) | `scheduler.py:59, 780-784` |
| 09:00:05~10 | 1차 WS 폴링(5s/0.5s) → 2차 REST 폴백 | `scheduler.py:1641-1668` |
| 09:00:11~13 | `[breakout_open_confirm]` — **VB confirmed=0** (실측 09-03/09-04) | system_logs |
| ~09:00:2x-3x | tracker 가 MAIN 으로 뒤집힘 → 첫 MAIN 틱이 **인라인 폴백으로 목표가 확정** | `volatility_breakout.py:866-869` |
| 첫 틱 | `prev==0` → 기록만, 신호 없음 | `:879-884` |
| 두 번째 틱 이후 | `prev < target ≤ current` 이면 BUY | `:886` |
| 09:30 | `_scan_loop` 시작 → 5분 주기 `_confirm_breakout_open_prices_if_pending` | `scheduler.py:61, 75, 2335-2345, 2413` |

**`_open_confirmed["main"]` 이 09:00:00~09:01:30 에 False 일 수 있는 조건**
1. 09:00:05 경로가 실패 — 실측 상시(위 (a)). ①-a WS 미수신(구독 슬롯 41/세션 한계 + no_feed,
   `MAX_SUBSCRIPTIONS` 정책), ①-b REST 폴백 예외/`stck_oprc="0"` → `logger.debug` 로 침묵
   (`scheduler.py:1668`).
2. tracker 가 아직 MAIN 이 아님 → 인라인 폴백도 봉쇄(`:863-864`).
3. 틱의 `open_price == 0` (`:868` 조건 불충족).
4. 그 사이 `prepare()` 재실행이 `_open_confirmed` 를 비움(`:177`).

**운영 실측 진입 시각 분포** (`trade_history`, VB BUY, 09:00~09:02 KST):
`09:00:06 / :14 / :16 / :18 / :18 / :20 / :21 / :25 / :27 / :29 / :30 / :31 / :31 / :31 / :32 / :36 / :39 / :44 / :51 / 09:01:06 / :17 / :23 / :34`
— 30초 세션 플립 직후에 몰린다. 검토가 지목한 창과 정확히 겹친다.

---

## 4. 같은 폴백을 쓰는 다른 전략 (영향권)

| 전략 | `open_price` 사용 | 영향 |
|------|-------------------|------|
| **volatility_breakout** | 목표가 = `open + offset` (`:809-813`), 인라인 폴백 `:866-869` | **직접·최대** |
| **long_tail_volatility** | **동형 코드** — `on_open_price_confirmed :609-627`, 인라인 폴백 `:663-665`, 목표가 `:618-621` | **직접**. 게다가 `tradable_boards=["main","pre_nxt"]`(운영 DB)라 08:00 pre_nxt 보드도 별도 확정 |
| donchian_swing | `gap_rate=(open−prev_close)/prev_close` 갭 스킵 (`:1613-1614`) | 간접. 단 매수 평가는 `_swing_buy_poll_loop` 뿐(`risk.py:646-647` 이 tick 평가 제외)이고 그 경로의 `open_price` 는 **REST `stck_oprc`(KRX)** (`scheduler.py:2635`) ⇒ **오염 없음** |
| kojiro | `gap_rate` (`:847-848`) + `current_price < open_price` 면 매수 거부 (`:861`) | 간접. tick 경로면 통합 `[7]` 사용 ⇒ 갭 판정·"시가 아래" 판정이 오염될 수 있음 |
| momentum | `check_exit_signal` 익일청산 갭률만 (`:209`) | 청산 경로 간접 |
| bull_flag_breakout / vcp_breakout | 시그니처만, 본문 미사용 | 없음 |

또한 `_confirm_breakout_open_prices` 자체가 VB·LTV 두 전략을 하드코딩 대상으로 돌린다
(`scheduler.py:1601`). BFB/VCP 는 VB 호환 5키(`open_price` 포함)를 노출만 한다
(`bull_flag_breakout.py:770`, `vcp_breakout.py:911-912`).

---

## 5. 임시 보류(09:00:00~09:01:30 매수 보류)를 넣을 자리 — 코드 사실

### 후보 ① `VolatilityBreakoutStrategy.check_buy_signal` 최상단 — **가능, 선례 있음**

기존 선례(그대로 인용, `volatility_breakout.py:822-847`):

```python
    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """현재 활성 보드의 Target Price 돌파 시 매수."""
        # cycle229 (P1-5) — 15:20 매수 컷. **최상단·`_prev_price` 갱신 이전**이 계약:
        # 뒤에 두면 종가/예상체결가가 baseline 이 되어 장중 재시작 시 거짓 미돌파를
        # 만든다(컷 틱은 어떤 상태도 갱신하지 않는다). 반드시 KST 명시(naive 금지 —
        # 컨테이너 TZ 의존은 P2-6 등재 결함).
        _now_kst = datetime.now(KST)
        if _now_kst.time() >= BUY_CUTOFF_KST:
            if self._buy_cutoff_logged_day != _now_kst.date():
                # 1회/일 관측 — 발화 없이 조용히 막으면 "왜 안 사나"를 영영 못 본다
                # (사이클 224 교훈). 날짜 키 자기 리셋(_reset_daily_state 훅 미의존).
                self._buy_cutoff_logged_day = _now_kst.date()
                logger.info(
                    "[vb_buy_cutoff] 15:20 이후 매수 신호 차단 — ticker=%s "
                    "(장후 동시호가·확정 종가 틱은 진입 대상이 아니다)",
                    ticker,
                )
            return Signal.NONE
```
상수는 모듈 레벨 `BUY_CUTOFF_KST = time(15, 20)` (`:27`, DB override 금지 명시).

- **가부**: 가능. 동기 함수라 `await`/HTTP 불가하지만 시각 비교는 순수 계산이라 무관.
- **구속 조건 3가지(AST 가드가 실제로 강제)**
  1. `datetime.now(KST)` **tz-aware 필수** — naive `datetime.now().time()` 은 RED
     (`tests/unit/ast/test_cycle229_ast_cutoff_guards.py:137-176`).
  2. 계좌 SOFT 게이트를 최상단으로 올리면 안 된다(cycle233 C233-F1,
     `test_cycle233_ast_account_risk.py:110-123`). 새 시각 게이트는 `_is_gate_if`
     (`:55-73`, `_account_soft_gate_blocked` 호출을 test 에 요구)에 걸리지 않으므로
     **최상단 배치 자체는 저촉하지 않는다**.
  3. cycle229 G-3 은 "컷 게이트가 `_prev_price` 참조보다 앞" 을 요구(`:212-245`) — 최상단이면 자동 충족.
- **부작용 (중요)**
  - 보류 구간 동안 `_prev_price[t]["main"]` 이 **0 으로 동결**된다(함수가 `:879` 이전에
    return). 09:01:30 이후 첫 틱은 `prev==0` → 기록만(`:883-884`), 두 번째 틱부터 평가.
    ⇒ **보류 해제 시 거짓 돌파는 생기지 않는다**(오히려 안전 방향).
  - 대신 **`_open_confirmed` 도 동결**된다(`:866-869` 미도달). 09:00:05 경로가 실측상
    0/55 이므로, 보류 해제 후 첫 틱이 **여전히 통합 `[7]`** 로 목표가를 확정한다.
    ⚠️ `[7]` 은 일-스코프 상수라 09:01:30 이 되어도 값이 바뀌지 않는다 ⇒
    **이 보류는 손실 회피이지 시가 출처의 시정이 아니다.**
  - 09:00~09:01:30 에 진짜 돌파가 나고 그 뒤 목표가 위에서 유지되는 종목은 그날 진입이
    통째로 사라진다(`prev`가 목표가 위에서 시작 → `prev < target` 불성립).

### 후보 ② `risk.on_tick` — **가능하나 8영역**

- `check_buy_signal` 호출 지점은 `risk.py:648` 한 곳(틱 경로). 그 앞 `:632-647` 에
  기존 스킵 가드들이 줄지어 있어 삽입 자리는 자연스럽다.
- **부작용/비용**
  - `src/engine/risk.py` 는 **8영역** ⇒ 관측 로그 한 줄도 사용자 승인 대상(CLAUDE.md).
  - **7전략 공통 경로**다. VB 만 막으려면 `strategy.strategy_id` 분기가 필요하고, 이는
    `risk.py:646-647`(donchian 제외) 선례가 있지만 전략 지식이 risk 로 새는 방향이다.
  - `_prev_price`/`_prev_prdy_rate` baseline 이 **모든 전략에서** 동결된다.
  - swing 폴 경로(`scheduler.py:2643`)는 `risk.on_tick` 을 안 타므로 커버되지 않는다
    (VB 에는 무관 — VB 는 tick 경로 전용).

### 후보 ③ `prepare()` — **불가**

- VB `prepare()` 는 07:55 `_boot` 에서 1회 실행되고 그 시점에 **09:00 시가는 존재하지 않는다**
  (`_targets[...]["open_price"] = 0`, `volatility_breakout.py:323`).
- prepare 는 종목 선정/`k`/`prev_range` 만 만든다. 시각 창을 판정할 호출이 없고,
  틱마다 재평가되지도 않는다 ⇒ 시간 창 보류를 구현할 지점이 아니다.
- 굳이 하려면 "그날 VB 후보를 비운다" = 하루 전체 매수 중단이지 90초 보류가 아니다.

### 후보 ④ (참고) `scheduler` 진입 시각 지연

- `TIME_KRX_OPEN_CONFIRM = time(9, 0, 5)`(`scheduler.py:59`)를 늦추는 것은 **보류가 아니다** —
  실측상 이 경로는 이미 0/55 무동작이고, 확정자는 인라인 폴백이다. 늦추면 오히려 KRX REST
  폴백 기회만 더 뒤로 밀린다.

### 권고 요약 (판단 근거만 제시, 결정은 사용자·domain-consult)

- 최소 침습 = **후보 ①**(VB 파일 단독, 8영역 무접촉, cycle229 선례와 동형, AST 3가지 충족 가능).
- 단 ①은 **원인 시정이 아니다**. 원인 시정 후보는 (가) 인라인 폴백을 지우고 09:00:05 REST(KRX)
  경로만 신뢰 (나) `[24] OPRC_HOUR` 스코프 필터를 `[7]` 에 도입(= `_parse_day_high` 대칭,
  `handler.py` = `src/realtime/**` **8영역**) (다) `_confirm_breakout_open_prices` 의 REST 폴백을
  실제로 작동시키기(현재 침묵 실패). 전부 매매 행위 변경이라 승인 + `domain-consult` 선행.

---

## 6. 반증 가능성 / 남은 구멍 (정직한 한계)

1. `stock_master_daily` 의 **당일 행이 placeholder(O=H=L=C=전일종가)** 라 09-04 이후 날짜의
   KRX 시가 대조는 불가능했다. 09-03 비교 8종목 중 2종목은 **일치**했다 — 오염은 전수가 아니다.
2. 위 역산은 `k_value_krx_main=1.3`, `prev_range` = `stock_master_daily` 전일 H−L 을 가정한다.
   `prepare` 가 실제로 읽은 캔들이 다르면(정규화/누락) 역산 값이 흔들린다. 086790(전일종가와
   **정확히 일치**)은 우연으로 보기 어렵지만 단일 표본이다.
3. "통합 `[7]` = NXT 프리장 시가" 는 리포 내 실측(cycle222-a2 000250) + 위 역산의 **정합**으로
   지지되지만, `[24] OPRC_HOUR` 를 직접 관측한 적은 **한 번도 없다**(파싱 코드 0건). 확정하려면
   장중에 `[24]` 를 찍어 보는 관측 배관이 필요하다 — 이것이 가장 값싼 결정적 실험이다.
4. 09:00:05 경로가 왜 0/55 인지(구독 슬롯 부족 vs REST 폴백 실패)는 이 추적으로 확정하지 못했다.
   `scheduler.py:1668` 의 `logger.debug` 침묵이 판별을 막는다.
