# U1 — VB·LTV `main` 목표가 기준 시가 소비 경로 전수 (2026-09-10 목, 장 종료 후)

> **읽기 전용 조사다 — 코드·DB·설정·EC2 파일을 한 글자도 바꾸지 않았다.**
> 운영 접근은 전부 GET/읽기(컨테이너 로그 tail · `/api/logs/search` GET · salvage JSON).
> 이 문서는 **결정하지 않는다.** 경로를 줄 번호로 놓고, 후보안을 접촉 비용과 함께 나열한다.
>
> **표기 규약** — **[코드]** = 소스에서 직접 확인 / **[실측]** = 운영 로그·덤프에서 관측 /
> **[산출]** = 실측값으로 계산 / **[추론]** = 위 셋 중 어느 것도 아닌 것.
> **[추론]** 위에 배포 결정을 세우지 마라.
>
> **범위 계약(사용자 D1 §범위 "여섯가지 유지")** — 전략 비중 · `position_ratio` ·
> `max_positions` · 랏 캡(K·K_ρ) · `open_entry_hold_secs`(90초) · LTV 청산 규약,
> 이 여섯은 **무접촉**이다. 아래 어떤 후보안도 이 값들을 바꾸지 않는다.
> 기준: 리포 HEAD `a10191b`.

---

## 1. 한 장 요약

1. **`[7] STCK_OPRC` 는 파싱→캐시→확정→목표가까지 4단으로 흐르고, 중간에 신선도 검사가 한 번도 없다.**
   `scanner.ticker_prices[t]["open_price"]` 는 마지막 틱의 `[7]` 을 **덮어쓰기만** 하고 타임스탬프를
   같이 저장하지 않는다(`ticker_last_tick` 은 별도 dict 이고 시가 확정 경로가 읽지 않는다).
2. **WS 가 REST 를 이기는 이유는 셋이고, 그중 가장 강한 것은 "폴링이 캐시의 나이를 안 본다" 는 것이다**(§3).
3. **`main` 기준가를 REST 로 바꾸는 가장 작은 diff 는 `on_open_price_confirmed` 한 메서드다**(§7 후보 A).
   그 메서드는 어떤 sha 핀에도 걸려 있지 않고, 전략의 **모든** 시가 확정이 이 한 곳으로 모인다.
4. **"장 시작 시점에 전 종목 REST 확보가 가능한가" = 시간은 된다(약 13~17초), 값은 20~27% 가 아직 없다**(§6).
   현행 09:00:05 폴백이 이미 하루 28~75콜을 4초 안에 쏘고 있고 그때 `stck_oprc>0` 을 못 받은
   (전략,종목) 쌍이 3일 실측 **36 / 18 / 48**(= 23.7% / 20.0% / 27.4%)다 ⇒ **유계 재시도가 선택이 아니라 필수**다.
5. **현행에서 그 구멍을 메우고 있는 것이 바로 오염원**이다 — 전략 인라인 확정(§2 ⑤). 인라인을 막으면
   재시도를 붙이기 전까지 그 20~27% 는 09:35 까지 목표가가 없다(§6-c).

---

## 2. 경로 전수 — 줄 번호 표

### 2-a. 수집 (WS `[7]`)

| # | 파일:줄 | 무엇 |
|---|---|---|
| ① | `src/realtime/handler.py:411-418` | `_parse_tick_prices(fields)` → `return int(fields[2]), int(fields[7])`. **소스 세그먼트 sha 핀 대상**(cycle264). 실패는 `None` → 틱 폐기 |
| ② | `src/realtime/handler.py:564` `_handle_tick` | 진입점. `603` `parsed = _parse_tick_prices(fields)` · `609` `current_price, open_price = parsed` |
| ③ | `src/realtime/handler.py:620` | `_maybe_log_open_scope_observe(fields, open_price)` — cycle264 관측(행위 0). 게이트 = `[1] STCK_CNTG_HOUR` MAIN 창, 라벨 = `[24] OPRC_HOUR`(`357`) |
| ④ | `src/realtime/handler.py:624-626` | `change_rate = (current - open)/open*100` — `[7]` 의 **두 번째** 소비처(등락률) |
| ⑤ | `src/realtime/handler.py:629-633` | `await _on_tick(ticker, current_price, open_price, change_rate, day_high=, acml_vol=)` |
| ⑥ | `src/realtime/handler.py:397-408` `dispatch_message` | `H0STCNT0`(KRX 단독) · `H0UNCNT0`(통합) · `H0NXCNT0`(NXT 단독) **셋 다 같은 `_handle_tick`** 으로 간다 = 채널 정보가 이 지점에서 **소실**된다. 채널 리졸버(P1-7 B)가 고쳐야 할 자리이자, ①~⑤ 어디에도 "이 값이 어느 보드의 시가인가" 가 남지 않는 이유 |

> **[코드]** `[7]` 은 `_parse_tick_prices` 밖에서 재파싱되지 않는다 — 관측기(③)도 `open_price`
> 인자를 그대로 받는다(handler.py:319-321 주석이 그 계약을 명시). 즉 **`[7]` 의 유일한 진입구는 ①**이다.

### 2-b. 캐시 (`scanner.ticker_prices`)

| # | 파일:줄 | 무엇 |
|---|---|---|
| ⑦ | `src/engine/risk.py:442-450` | `RiskManager.on_tick(ticker, current_price, open_price, change_rate, *, day_high=0, acml_vol=-1)` |
| ⑧ | `src/engine/risk.py:495-500` | `ticker_prices[ticker] = {"current_price":…, "open_price": open_price, "change_rate":…, "prdy_ctrt":…}` — **통째 재대입**. 타임스탬프 없음 |
| ⑨ | `src/engine/risk.py:503-504` | `ticker_last_tick[ticker] = now_kst` — 신선도 정보는 **여기에만** 있고 시가 확정 경로는 이 dict 를 읽지 않는다 |
| ⑩ | `src/engine/scanner.py:452-453` | `ticker_prices: dict[str, dict]` 전역 정의 + 형태 주석 |
| ⑪ | `src/engine/scheduler.py:2795-2818` (`_run_swing_rest_poll_once`) | **두 번째 writer** — donchian∪kojiro 의 후보/보유/주문중 종목에 대해 `fetch_stock_detail` 의 **REST `stck_oprc`** 를 같은 `ticker_prices[t]["open_price"]` 에 쓴다. 09:05~09:30 보유 전용 · 09:30~15:20 전체, 60초 주기(`SWING_REST_POLL_INTERVAL_SECS=60`, 종목 간 `0.05s`) |

> **[코드]** ⑪ 때문에 `ticker_prices[t]["open_price"]` 는 **출처가 섞인 값**이다(WS `[7]` 또는 KRX REST).
> VB/LTV 종목이 donchian/kojiro 후보와 겹치면 09:30 이후 그 키가 REST 값으로 바뀐다.
> 09:00:05 확정에는 영향이 없지만(폴 시작 전), **09:35 재확정**(§2-d ⑳)에는 영향이 있을 수 있다.

### 2-c. 확정 (`_targets[...]["boards"]["main"]`)

| # | 파일:줄 | 무엇 |
|---|---|---|
| ⑫ | `src/engine/scheduler.py:61` | `TIME_KRX_OPEN_CONFIRM = time(9, 0, 5)` |
| ⑬ | `src/engine/scheduler.py:789` | `await self._confirm_breakout_open_prices(board="main")` — **정각 호출부**(board 명시 의무) |
| ⑭ | `src/engine/scheduler.py:790` | 바로 뒤 `await self._drain_pending_next_day_clear()` — 익일청산 시장가 정리가 ⑬ 의 소요시간만큼 **뒤로 밀린다** |
| ⑮ | `scheduler.py:1581-1592` | `_confirm_breakout_open_prices(*, max_wait_s=5.0, interval_s=0.5, board=None)` 시그니처·계약 |
| ⑯ | `scheduler.py:1610-1623` | 대상 수집 — sid 는 `("volatility_breakout","long_tail_volatility")` **하드코딩**, `config.enabled` ∧ `get_tradable_boards` 에 board 포함 ∧ `_targets`/`on_open_price_confirmed` 보유 |
| ⑰ | `scheduler.py:1640-1650` | `all_already_confirmed` idempotent skip(전량 확정이면 1·2차·로그 전부 skip) |
| ⑱ | `scheduler.py:1652-1668` | **1차 = WS 캐시 폴링**. `elapsed<5.0`, `interval 0.5`. 핵심 = `1660-1662` `price_info = ticker_prices.get(ticker)` → `if price_info and price_info.get("open_price",0) > 0:` → `on_open_price_confirmed(ticker, price_info["open_price"], board=board)`. **신선도·출처 검사 0** |
| ⑲ | `scheduler.py:1670-1684` | **2차 = REST 폴백**(미확정 종목만). `detail = await fetch_stock_detail(ticker)` → `1677` `open_price = int(detail.get("stck_oprc","0"))` → `>0` 이면 확정 + `1682` `open_price_observe.mark_confirmed_via_rest(sid,ticker,board)`. `1683-1684` `except Exception: logger.debug(...)` — **"0" 과 "예외" 를 구분하지 않는다** |
| ⑳ | `scheduler.py:1686-1689` | `logger.info("%s 시가 확정 [%s]: %d/%d종목")` + `_emit_breakout_open_confirm` |
| ㉑ | `scheduler.py:1691-1739` | `[breakout_open_confirm] … truth_confirmed=%d truth_total=%d`(cycle264 C3, 본체 = `open_price_observe.count_board_confirmed`) |
| ㉒ | `strategies/volatility_breakout.py:824-846` / `long_tail_volatility.py:637-655` | **`on_open_price_confirmed(ticker, open_price, board="main")` — 유일한 확정 함수**. `boards[board] = {open_price, target_price = open_price + target_offset, target_offset}` 을 **무조건 덮어쓴다**(setdefault 는 `boards` dict 에만 걸린다) + `_open_confirmed[ticker][board]=True` + 최초 1회 top-level 호환 키 |
| ㉓ | `volatility_breakout.py:342-353` / `long_tail_volatility.py:357-366` | `prepare()` 가 `_targets[t]` 초기화(`"open_price": 0`) + `_open_confirmed[t] = {}` |
| ㉔ | `scheduler.py:777` / `855` | `board="pre_nxt"`(08:00) / `board="post_nxt"`(15:30) — **다른 boards 키**로 격리 |
| ㉕ | `scheduler.py:805` / `828` | board 미지정 자동 결정 호출(중간 부팅·09:00:05 이후 시작) |
| ㉖ | `scheduler.py:2367-2380` (`_scan_loop`) → `2447-2521` | `_confirm_breakout_open_prices_if_pending()` — **현행 유일의 재시도**. `SCAN_INTERVAL=300`(scheduler.py:77)이고 `_scan_loop` 는 09:30 스캔 이후 생성되므로 **첫 재시도가 실측 09:35:1x** |

### 2-d. 소비 (목표가 → 매수 판정)

| # | 파일:줄 | 무엇 |
|---|---|---|
| ㉗ | `risk.py:648` | `signal = strategy.check_buy_signal(ticker, current_price, open_price)` — **WS 틱의 `[7]` 이 인자로 그대로** 들어간다 |
| ㉘ | `volatility_breakout.py:848` / `long_tail_volatility.py:657` | `check_buy_signal(self, ticker, current_price, open_price)` |
| ㉙ | **`volatility_breakout.py:899-901`** / **`long_tail_volatility.py:705-707`** | **인라인 확정** — `confirmed = self._open_confirmed.get(ticker,{}).get(board,False)` → `if not confirmed and open_price > 0: self.on_open_price_confirmed(ticker, open_price, board=board)`. **오염원 #1이자 현행 구멍 메우기 담당**(§3·§6-c) |
| ㉚ | `volatility_breakout.py:903-909` / `long_tail_volatility.py:709-715` | `board_info = info["boards"][board]` → `target = board_info["target_price"]`(≤0 이면 NONE) |
| ㉛ | `volatility_breakout.py:911-912` / `long_tail_volatility.py:725-726` | `prev = self._prev_price[ticker][board]` 갱신 — **baseline 은 보류/게이트보다 앞**(cycle233 C233-F1 계약) |
| ㉜ | `volatility_breakout.py:918` / `long_tail_volatility.py:732` | `if prev < target and current_price >= target:` = **돌파 발사점** |
| ㉝ | (발사 직전 게이트) | `volatility_breakout.py:925` `_account_soft_gate_blocked`(cycle233, VB 는 발사점) / LTV 는 함수 최상단 `long_tail_volatility.py:669` |
| ㉞ | **`volatility_breakout.py:937`** / **`long_tail_volatility.py:743`** | **cycle262 진입 보류 판정 자리** — `_hold_elapsed = self._open_entry_hold_elapsed(_now_kst, _hold_secs)`; `is not None` 이면 `[open_entry_hold_blocked]` 1행 후 `Signal.NONE`. 창 = KST `[09:00:00, 09:01:30)` |
| ㉟ | `volatility_breakout.py:872-873` / `long_tail_volatility.py:677-678` | `_read_open_entry_hold_secs()` + `_emit_open_entry_hold_config()` — 카나리아는 **매 평가**, 판정은 ㉞ (일부러 분리) |
| ㊱ | `volatility_breakout.py:970-988` / `long_tail_volatility.py:774-792` | 발사 — `board_open` 으로 `change_rate` 계산 + `buy_signals` append + `Signal.BUY` |

### 2-e. 관측 (cycle264 leaf)

| # | 파일:줄 | 무엇 |
|---|---|---|
| ㊲ | `open_price_observe.py:100` | `TIME_OPEN_SOURCE_COMPARE = time(9,5,30)` |
| ㊳ | `open_price_observe.py:103` | `_OPEN_SOURCE_COMPARE_MAX_PER_SEC = 5`(종목 간 `asyncio.sleep(0.2)`) |
| ㊴ | `open_price_observe.py:118-127` | `mark_confirmed_via_rest(sid,ticker,board)` — **호출부는 `scheduler.py:1682` 단 하나**([코드] 전수 grep). ⇒ 방향 리포트 §4-b 의 **[추론]**("새 주경로에도 mark 를 달아야 한다")은 **[코드]로 확정**된다 |
| ㊵ | `open_price_observe.py:129-136` | `was_confirmed_via_rest` — 판정 실패 시 `False`(= ws 가정) |
| ㊶ | `open_price_observe.py:199-224` | `_collect_pending` — `used_open` 정본은 `_targets["boards"]["main"]["open_price"]`(캐시가 아니다), `used_open<=0` skip + cap peek 이 REST **앞** |
| ㊷ | `open_price_observe.py:226-282` | `[open_source_compare] … used_src=ws|rest reason=ok|rest_zero|rest_error` — **`reason` 3분기 서식이 이미 존재**한다(§5 재사용 재료) |
| ㊸ | `scheduler.py:1740-1744` | `_run_open_source_compare_once` 얇은 위임(leaf 패턴 정본) · `scheduler.py:722-725` task 생성 |

---

## 3. 왜 WS 캐시가 REST 를 먼저 이기는가 — 경로 셋 [코드]

| 순위 | 경로 | 언제 | 왜 이기나 |
|---|---|---|---|
| **1** | ⑱ 1차 폴링이 **캐시의 나이를 안 본다** | 09:00:05 ~ 09:00:10 | `ticker_prices[t]["open_price"]` 는 08:00~09:00 프리장 틱이 남긴 값이 그대로 살아 있다(⑧ 은 통째 재대입이라 값은 있고 시각은 없다). **MAIN 틱이 아직 한 개도 안 왔어도** `>0` 이면 확정된다 ⇒ `oprc_hour=080000` 확정의 주 경로 |
| **2** | ⑲ 2차 REST 는 **"미확정" 종목만** 본다 | 09:00:10 ~ | 1차가 이미 확정을 심었으므로 REST 는 차례가 오지 않는다. 방향 리포트가 "REST 폴백은 고장이 아니라 차례가 오지 않을 뿐" 이라 쓴 그 구조 |
| **3** | ㉙ 전략 인라인 확정 | 09:00:00 ~ (첫 MAIN 틱) | `_resolve_active_board()` 가 `main` 을 돌려주는 순간부터(= 세션 트래커가 MAIN 진입을 반영한 뒤, `SESSION_TICK_INTERVAL=30`s 주기라 09:00:00~09:00:30 사이 어딘가) **09:00:05 스케줄러보다 먼저** 확정할 수 있다 |

**[코드] 세 경로 모두 같은 함수 ㉒ 로 수렴한다.** ⇒ `main` 기준가의 출처를 바꾸려면 **㉒ 한 곳**이
유일한 좁은 목이다(§7 후보 A 의 근거).

---

## 4. `pre_nxt`(LTV 08:00) 와 `main` 이 갈리는 자리

| 축 | `pre_nxt` | `main` |
|---|---|---|
| 확정 호출 | `scheduler.py:777` (08:00, board 명시) | `scheduler.py:789` (09:00:05, board 명시) |
| 저장 키 | `_targets[t]["boards"]["pre_nxt"]` | `_targets[t]["boards"]["main"]` |
| K 계수 | `_BOARD_K_KEY[board]` → `k_value_nxt_pre` | → `k_value_krx_main` |
| 대상 전략 | LTV 만(`DEFAULT_TRADABLE_BOARDS=("pre_nxt","main","post_nxt")`). VB 는 `("main",)` 이라 ⑯ 의 `get_tradable_boards` 필터에서 빠진다 | VB·LTV 둘 다 |
| 시가의 **정당성** | 08:00~09:00 의 `[7]` = 그 보드의 진짜 시가 ⇒ **오염 아님. 무접촉이 옳다** | 09:00 KRX 시가여야 하는데 `[7]` 이 프리장 값 ⇒ 오염 |
| top-level 호환 키 | ㉒ 의 `if not info.get("open_price")` 가 **먼저 확정된 보드**(= LTV 는 08:00 pre_nxt)의 값을 넣는다. 대시보드·AI 자문 표시 전용 | 이미 채워져 있으면 갱신 안 됨 |

**[코드] `check_buy_signal` 은 top-level 이 아니라 `boards[board]` 를 읽는다**(㉚) ⇒ 두 보드의 목표가는
서로 오염시키지 않는다. **`board=="main"` 스코프로만 시정하면 LTV 프리장 매수는 byte 동일**이다.

---

## 5. 청산 규약에 시가가 관여하는가 (= 범위 밖 표시)

| 소비처 | 파일:줄 | `[7]` 을 쓰는가 | 이번 범위 |
|---|---|---|---|
| VB `check_exit_signal` | `volatility_breakout.py:1149-1151` | **아니다** — `open_price` 인자를 받기만 하고 본문에서 한 번도 읽지 않는다 | 무관 |
| VB 15:20 강제청산 | `volatility_breakout.py:1236-1238` `check_force_clear` + `scheduler._force_clear_main_only` | **아니다** — `positions.keys()` 전량 | 무관 |
| LTV `check_exit_signal` 익일 갭률 | `long_tail_volatility.py:938` `gap_rate = (open_price - pos.buy_price)/pos.buy_price*100` | **그렇다** | **범위 밖 — LTV 청산 규약(여섯 가지 중 하나). 무접촉** |
| momentum 익일 갭률 | `momentum.py:209` | 그렇다 | 범위 밖 (F-3b) |
| kojiro 갭스킵·시가아래 붕괴 가드 | `kojiro.py:858-901` | 그렇다 | 범위 밖 (F-3) |
| donchian 갭스킵 + `ext_pct` | `donchian_swing.py:1613-1614`, `1626-1634` | 그렇다 | 범위 밖. **단, donchian 은 `risk.on_tick` 에서 skip 되고**(`risk.py:646-647`) **`_swing_buy_poll_loop` 가 REST `stck_oprc` 를 넘긴다**(`scheduler.py:2668-2677`) ⇒ 이미 KRX REST 기준 |
| 익일청산 갭 판정(스케줄러) | `scheduler.py:1421-1425` `today_open = price_data.get("open_price",0)` → 0 이면 `_resolve_open_price(…, max_wait_s=2.0)` (`scheduler.py:1916-1941`, WS 폴링 → REST 폴백) | 그렇다 | 범위 밖(익일청산 규약) |

> **[코드] `[7]` 소비처는 6곳** — ① VB main 목표가 ② LTV main 목표가 ③ LTV `pre_nxt`/`post_nxt` 목표가
> ④ 익일청산 갭률(LTV·momentum·스케줄러) ⑤ kojiro 갭 가드 ⑥ `change_rate`(handler:625, 대시보드/`prdy_ctrt` 옆).
> **이번 시정이 건드리는 것은 ① ② 뿐이고, `[7]` 자체를 0 으로 강등하지 않는 한 나머지는 무접촉이다**
> (자문 §0 "0 강등 금지" 와 정합).

---

## 6. 사용자 질문 D1 — "장 시작 시점에 전 구독대상 REST 확보가 가능한가"

### 6-a. 기존 REST 함수 계약 [코드]

| 축 | 사실 |
|---|---|
| 함수 | `src/api/condition.py:462` `async def fetch_stock_detail(ticker: str) -> dict` |
| TR | `src/api/condition.py:439-444` — `kis_get_quote(STOCK_PRICE_URL, "FHKST01010100", {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker})`. **`J` = KRX** ⇒ D1 이 말한 "KRX 시가" 정본 |
| 캐시 | `_PRICE_CACHE_TTL = 5s` TTL + **single-flight**(`asyncio.Task` + `asyncio.shield`, `condition.py:476-500`). ⇒ VB·LTV 가 같은 종목을 5초 안에 각각 물어도 **KIS 호출은 1회** |
| 라우팅 | `src/api/base.py:656-676` `kis_get_quote` → `693-` `_request_via_quote_pool` — 화이트리스트 path 가드(`713`), 보조 시세계정 라운드로빈 + 메인 폴백, 3회 재시도 |
| Rate limit | `src/api/base.py:437-451` `_rate_limit()` — **전역 20건/초**(메인·보조 공용, 락 안에서 sleep). 라벨별 세마포어는 메인 20 / 보조 18(`base.py:112`) |
| `stck_oprc` "0" 처리 | **현행 확정 루프에는 없다** — `scheduler.py:1677` `int(detail.get("stck_oprc","0"))` 이 `>0` 이 아니면 그냥 미확정으로 남고, 빈 문자열이면 `int("")` 가 `ValueError` 를 던져 `1683` 의 `except Exception` 이 삼킨다. **"0" 과 "예외" 가 구분되지 않는다** |
| 이미 있는 분리 서식 | `open_price_observe.py:262-270` 이 `reason = ok / rest_zero / rest_error` 를 **이미 구현**해 뒀다 ⇒ 재사용 가능 |
| throttle 선례 | `open_price_observe.py:103` 5건/초(0.2s) · `scheduler.py:132` `SWING_REST_POLL_TICKER_SLEEP_SECS = 0.05`(=20/s) |

**판정: 재사용 가능하다.** 신규 KIS 배관은 필요 없고, `open_price_observe._fetch_stock_detail`
(`open_price_observe.py:311-315`, 지연 import 래퍼)까지 그대로 답습하면 된다.
**다만 `reason` 3분기 · 유계 재시도 · throttle 값은 신규 설계 대상**이다.

### 6-b. 시간은 되는가 — 3일 실측 [실측]/[산출]

정본 = `scratchpad/obs_salvage/salvage_{breakout_open_confirm,open_source_compare}_2026-09-0{8,9,10}.json`
+ `GET /api/logs/search?q=시가 확정`(total=17, 컨테이너 안에서 실행).

| 축 | 09-08 | 09-09 | 09-10 |
|---|---|---|---|
| VB `_targets`(main) | 59 | 53 | 81 |
| LTV `_targets`(main) | 93 | 37 | 94 |
| **합(전략,종목) 쌍** | **152** | **90** | **175** |
| 09:00:1x `truth_confirmed` VB / LTV | 47 / 69 | 42 / 30 | 61 / 66 |
| **09:00 시점 미확정 쌍** | **36 (23.7%)** | **18 (20.0%)** | **48 (27.4%)** |
| 09:05:30 `used_src=rest` VB / LTV | 7 / 14 | 6 / 4 | 11 / 16 |
| **[산출] 09:00 REST 실제 호출수** | **57** | **28** | **75** |
| VB `시가 확정 [main]` 로그 시각 | 09:00:11.632 | 09:00:11.390 | 09:00:13.071 |
| LTV `시가 확정 [main]` 로그 시각 | 09:00:14.007 | 09:00:12.004 | 09:00:14.547 |
| **[산출] 1차 폴 종료(09:00:10.1 [추론]) → LTV 완료** | **3.9s** | **1.9s** | **4.45s** |
| **[산출] 그 구간 실효 처리율** | **14.6 콜/s** | **14.7 콜/s** | **16.9 콜/s** |
| 09:05:30 대조 루프 span / 행 | 40.5s / 116 | 23.6s / 72 | 39.4s / 127 |
| **[산출] 직렬 REST 지연**(span/행 − 0.2s throttle) | **0.152 s/콜** | **0.132 s/콜** | **0.113 s/콜** |
| 확정 종목 union(중복 제거) | 89 | 58 | 98 |
| **union 상한**(미확정 포함) | ≤125 | ≤76 | ≤146 |

**[산출] 전 대상 REST 일괄 조회 소요 추정**
- 순수 직렬 = `146 × 0.113 ≈ 16.5s`(최악) / `89 × 0.152 ≈ 13.5s`(중앙) ⇒ **09:00:05 시작 → ~09:00:19~22 완료**
- cycle262 진입 보류 종료(**09:01:30**)까지 **약 68~77초 여유** ⇒ **창 안에 들어온다**
- 전역 20/s 한도 대비: 16.5s 동안 평균 8.8콜/s ⇒ **한도의 44%**. 09:00 매수 주문과 다투더라도 여유가 있다
- 동시성을 조금만 주면(예: 5 병렬 + 0.05s 간격) 3~4초. **다만 09:00~09:01:30 은 매수 주문 구간이므로 직렬 유지가 보수적 선택**

> ⚠️ **[추론] 표시** — "1차 폴 종료 09:00:10.1" 은 코드상(`max_wait_s=5.0`, `interval_s=0.5`)의 계산이지
> 로그로 직접 관측한 시각이 아니다. 실효 처리율 14.6~16.9 콜/s 는 그 전제 위에 있다.
> 전제와 무관한 **하한 근거**는 09:05:30 루프의 직렬 지연 0.113~0.152 s/콜(= 6.6~8.8 콜/s)이고,
> 그 보수적 값으로 계산해도 146콜 = 16.5~22초로 **90초 창 안**이다.

### 6-c. 값은 확보되는가 — **아니다, 20~27% 는 09:00 에 아직 없다** [실측]

- 09:00:10~14 에 1차(WS)·2차(REST)를 **모두** 돌린 뒤에도 미확정으로 남은 (전략,종목) 쌍이
  **36 / 18 / 48**(23.7% / 20.0% / 27.4%)다. 이 쌍들은 2차 REST 를 **시도했고** `stck_oprc>0` 을 받지 못했다
  (또는 예외 — §6-a 대로 현행 코드는 둘을 구분하지 않는다).
- 이 코호트는 09:05:30 대조에도 나타나지 않는다(㊶ `used_open<=0` skip) ⇒ **3일치 판독의 `reason≠ok = 0` 은
  "REST 가 언제나 답했다" 는 뜻이 아니라 "이미 확정된 종목만 물었다" 는 뜻이다.** 판독 시 혼동 금지.
- **현행에서는 이 구멍이 보이지 않는다** — ㉙ 인라인 확정이 그 종목의 첫 MAIN 틱에서(오염된 값으로라도)
  목표가를 세우기 때문이다. 인라인을 막는 설계는 **반드시 유계 재시도를 함께 넣어야** 한다.
- 현행 재시도(㉖)의 첫 발화는 실측 **09:35:1x**(`SCAN_INTERVAL=300` + `_scan_loop` 이 09:30 스캔 후 생성)
  ⇒ 재시도 없이는 **약 35분** 목표가 공백. (방향 리포트의 "09:30 까지 1.5시간" 은 `_swing_buy_poll_loop`
  창 기준 표현으로 보이며, 실측 첫 재확정은 09:35 다.)
- 09:35 재확정 실측: 09-08 VB 59/59 · LTV 93/93, 09-09 VB 53/53 · LTV 37/37, 09-10 VB 81/81
  (**09-10 LTV 09:35 행은 없다** — §9 미결 3).

---

## 7. "가장 작은 diff" 후보 3안

> 셋 다 **8영역 접촉 0**이고 여섯 가지 무접촉 값을 바꾸지 않는다.
> 셋 다 킬스위치 `open_price_scope_mode`(전략별 `"off"|"enforce"`, **키 부재 = off = 현행**)를 전제한다 —
> 그 키는 `DEFAULT_PARAMS` 신규 키이므로 **어느 후보든 전략 2파일 diff 가 불가피**하고,
> 루트 CLAUDE.md 규약상 **사용자 승인 + `domain-consult` 선행 대상**이다.

### 7-a. 비교표

| 축 | **A — `on_open_price_confirmed` 에 출처 게이트** | **B — confirm 루프 우선순위 역전** | **C — 확정 후 REST 덮어쓰기** |
|---|---|---|---|
| 한 줄 | ㉒ 에 `source` 인자를 달고 `board=="main" ∧ enforce` 면 `source!="rest"` 확정을 거부 | ⑮ 안에서 `main` 일 때 1차를 REST, 2차를 WS 로 뒤집는다(본체는 leaf 위임) | ⑬ 직후 leaf 를 1회 호출해 **모든** main 타깃을 REST 시가로 재확정(덮어쓰기) |
| 주 diff 위치 | `volatility_breakout.py:824-846` · `long_tail_volatility.py:637-655` (+ 두 `DEFAULT_PARAMS`) | 신규 leaf `src/engine/open_price_rest.py` + `scheduler.py:1652-1684` 분기 | 신규 leaf + `scheduler.py:789-790` 사이 1줄 |
| **8영역 접촉** | **0** | **0** | **0** |
| **`scheduler.py` 라인 증가** | **+0** (`1679` 에 `source="rest"` 인자 추가 · `789` 에 `max_wait_s=0.0` 추가 = 기존 줄 안에서 해결) | **+3~6** (위임 호출·분기). 현 3,898L / 상한 3,900L = **여유 2행** ⇒ 주석 정리 또는 leaf 로 더 밀어야 한다 | **+1~2** (import 는 기존 `from src.engine import open_price_observe` 줄 옆에 1줄) |
| **전략 sha 핀**(cycle264 C4 6개) | **무영향** — `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` 를 한 글자도 안 바꾼다(㉙ 호출부 그대로, 게이트는 피호출부에). `on_open_price_confirmed` 는 핀 대상이 아니다 | 무영향 | 무영향 |
| 오염 경로 차단 범위 | **셋 다**(§3 의 1·2·3) — 세 경로가 전부 ㉒ 로 수렴하므로 한 곳에서 닫힌다 | 1·2 는 닫히나 **3(인라인)은 안 닫힌다** ⇒ A 를 사실상 동반해야 완결 | 1·2·3 모두 **사후 정정**(덮어쓰기)으로 무효화. 단 REST 실패 종목은 오염된 채 남는다 |
| REST 호출량 | 전 대상(§6-b, ~13~22초) — 1차 폴이 무의미해지므로 `max_wait_s=0.0` 으로 5초 절약 권고 | 전 대상 동일 | 전 대상 + **기존 1차/2차 호출과 중복**(5s TTL 밖이면 두 배) |
| `_drain_pending_next_day_clear` 지연(⑭) | 09:00:14 → **~09:00:22**(폴 5초를 없애므로 순증 ~8초) | 09:00:14 → ~09:00:27(폴 5초 유지 시) | 09:00:14 → ~09:00:30(확정 후 추가 스윕) |
| 남는 구멍 | REST 0 코호트(20~27%)가 **목표가 없음** ⇒ 유계 재시도 필수 | 동일 + 인라인이 그 구멍을 오염값으로 메워 **부분 오염이 잔존**(귀인 혼탁) | REST 0 코호트는 **오염값 그대로 유지**(현행과 동일) ⇒ 지혈이 불완전하지만 구멍도 안 생긴다 |
| 관측 seam | `used_src` 확장 자리 그대로(`ws|rest|ws_krx`) — ㊴ 가 단일 호출부라 새 주경로에도 mark 를 달면 된다 | 동일 | **덮어쓰기 전/후 두 값**을 다 남겨야 해서 서식이 하나 더 필요 |
| 롤백 | `PUT /api/strategies/{id}/params {"open_price_scope_mode":"off"}` 즉시(D6) | 동일 | 동일 |
| 되돌리기 난이도 | 낮음(한 함수의 조기 return) | 중간(분기 2개) | 낮음(호출 1줄 제거) |

### 7-b. 권고가 아니라 재료로서의 관찰

- **A 가 가장 작고 가장 좁다.** §3 의 세 경로가 전부 ㉒ 로 수렴한다는 [코드] 사실이 근거이고,
  cycle264 가 남긴 C4 sha 핀 6개를 **하나도 갱신하지 않아도 된다**(핀은 `check_*`/`calc_*` 만 잡는다).
- **A 는 단독으로 완결되지 않는다** — REST 를 실제로 쏘는 주체가 필요하다. 그 주체로는
  (a) 기존 2차 폴백(⑲)에 전부 떨어뜨리기(= `max_wait_s=0.0`, scheduler 라인 +0) 또는
  (b) 신규 leaf 스윕(재시도 포함) 두 갈래가 있고, **유계 재시도를 어디에 두느냐가 실질 설계 결정**이다.
  (a) 는 재시도가 없고 (b) 는 leaf 신규 파일이 필요하다.
- **B 는 A 없이 쓰면 인라인 경로가 남아 "무엇이 기준가를 정했는가" 가 다시 흐려진다.**
- **C 는 구멍을 만들지 않는다는 장점**이 있지만(현행 대비 순수 개선), "오염값으로 한 번 확정한 뒤
  덮어쓴다" 는 구조라 D+1 판독에서 `used_open` 의 의미가 시점 의존이 된다.
- 어느 안이든 **`board=="main"` 스코프**가 계약이다 — `pre_nxt`(§4)와 `post_nxt` 는 무접촉.

---

## 8. 회귀·가드 표면 (착수 전 반드시 볼 것)

| 가드 | 파일 | 이번 시정이 건드리는가 |
|---|---|---|
| `test_c7_no_killswitch_param_introduced` | `tests/unit/ast/test_cycle264_scope_and_pins.py:277-294` | **RED 확정** — `src/**` 어디에도 `open_price_scope_mode` 문자열을 금지한다. cycle272 가 이 테스트를 갱신·삭제해야 한다(파일 헤더가 "cycle265 가 갱신" 이라 이미 예고) |
| `test_c4_strategy_entry_methods_pinned` | 같은 파일 `201-250` | **후보 A/B/C 모두 무영향**(㉒ 는 핀 대상이 아니다). 인라인 호출부(㉙)를 건드리면 그때 RED |
| `test_c7_scheduler_line_cap` (<3,900L) + cycle257 대조 | 같은 파일 `72-105` | HEAD 실측 **3,898L**, 여유 **2행**. 후보 B 는 leaf 위임 없이는 위반 |
| `test_c7_markers_live_only_in_two_files` | 같은 파일 `257-275` | cycle264 마커 2종 한정 — 신규 마커 이름은 자유 |
| `_parse_tick_prices` 소스 세그먼트 sha 핀 | 같은 파일(cycle264) + `tests/unit/realtime/test_handler_tick_parse_guard.py` | **[7] 파싱을 안 건드리므로 무영향** |
| 시가 확정 회귀 | `tests/unit/engine/scheduler/test_confirm_open_prices_main_only.py` · `tests/integration/test_confirm_open_prices.py` · `test_post_nxt_open_price_confirm.py` · `tests/unit/engine/test_cycle164_open_confirm_retry_chain.py` | **직격**. 세 후보 모두 이 4파일의 기대를 바꾼다 |
| cycle262 보류 | `tests/unit/engine/strategies/test_cycle262_open_entry_hold.py` | 값·창 무접촉이면 그대로 통과해야 한다(= 통과가 계약) |
| cycle264 대조 | `tests/unit/engine/test_cycle264_open_source_compare.py` | `used_src` 의미가 바뀌면 갱신 필요 |

---

## 9. 미결 / 확인 불가

| # | 항목 | 상태 |
|---|---|---|
| 1 | **09:00 REST 미확정 20~27% 의 내역** | `stck_oprc="0"`(미프린트)인지 예외(타임아웃/5xx)인지 **구분 불가** — 현행 `scheduler.py:1683` 이 둘을 한 `except` 로 삼킨다. `open_price_observe` 의 `reason` 3분기를 이 경로에 옮기기 전에는 알 수 없다 |
| 2 | **1차 폴 종료 시각** | **[추론]**(코드상 5.0s). 실효 처리율 14.6~16.9 콜/s 는 이 전제 위에 있다. 전제 없는 하한은 6.6~8.8 콜/s(§6-b) |
| 3 | **09-10 LTV 09:35 재확정 로그 부재** | VB 는 `81/81` 을 남겼는데 LTV 는 그날 09:35 행이 없다(`[breakout_open_confirm]` 4행 · `q=시가 확정` total=17 양쪽 모두). ⑳ 의 emit 은 sid 루프 안이라 둘 다 나와야 한다 ⇒ **미규명**. 09-10 LTV 는 66/94 로 하루를 났을 가능성 |
| 4 | **`ticker_prices` 출처 혼입의 영향 범위** | ⑪ 이 09:30 이후 donchian∪kojiro 종목의 `open_price` 를 REST 로 덮는다. VB/LTV 와의 종목 겹침 비율을 재지 않았다 ⇒ ㉖(09:35 재확정)이 이미 일부는 REST 기준으로 확정하고 있을 수 있다 |
| 5 | **컨테이너 로그 보존** | 오늘 18:57 KST 재시작(cycle270/271 배포)으로 **오전 컨테이너 로그는 소실**. 아침 구간 정본은 salvage JSON + `system_logs` 뿐 |
| 6 | **KRX 원천 대조** | 대조 기준은 여전히 `stock_master_daily`(KIS 일봉)이고 KRX 거래소 원천과의 직접 대조는 이 조사 범위 밖(선례 판독과 같은 전제) |

---

## 10. 명세에 대한 이견 (고치지 않고 기록만)

1. **방향 리포트 §4-b 의 [추론] 하나가 [코드]로 승격된다** — "`used_src` 라벨은 `mark_confirmed_via_rest` 가
   2차 폴백 분기에서만 붙이므로 새 주경로에도 mark 를 달아야 한다" 는 추론이 아니라 사실이다
   (호출부 전수 = `scheduler.py:1682` 1곳).
2. **"09:30 까지 1.5시간 목표가 구멍"(방향 리포트 §4-a 위험 ②)의 시각 표현** — 실측 첫 재확정은
   **09:35:1x**(`_scan_loop` 경유)이고, 09:00 기준 약 **35분**이다. "1.5시간" 은 다른 기준(swing poll 창)으로
   보인다. **결론(유계 재시도 필수)은 그대로 유효**하며 오히려 근거가 더 단단하다(구멍의 크기가 20~27%로 실측됨).
3. **자문 결정 ④ (ii)안("판별자 `[24]` 없이 REST 만")과 D1("체크할 필요 없이 KRX 시가를 쓰는 게 원칙")은 정합한다.**
   `[24]` 를 안 쓰는 설계에서는 §3 의 세 경로를 전부 막아야 "항상 REST" 가 성립하고, 그것이 ㉒ 한 곳에서
   가능하다는 것이 이 조사의 결론이다.
4. **D1 의 "구독채널 분리 없이" 제약과 §5 의 소비처 표는 정합한다** — `[7]` 을 0 으로 강등하지 않고
   `board=="main"` 목표가만 REST 로 갈면 나머지 4개 소비처(익일청산 갭·kojiro 갭·`change_rate`·LTV pre_nxt)는
   **byte 동일**하다.

---

*작성 2026-09-10 목 장 종료 후 · 코드·DB·설정 변경 0 · 커밋 0 · EC2 접근은 전부 읽기 전용.*
