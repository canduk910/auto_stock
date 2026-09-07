# F-3 조사 — 고지로(kojiro) 갭 스킵 판정의 시가 오염

- 작성 2026-09-07 (월) 장 종료 후 · domain-expert · **읽기 전용** (코드·DB·설정·git 무변경. 운영은 로그 grep + SELECT 만)
- 대상 = 워크리스트 후속 **F-3** ("kojiro 갭스킵 오염")
- 선행 정본 = `_workspace/analysis/2026-09-07_open_scope_dplus1_readout.md` ·
  `_workspace/consult/2026-09-07_open_price_scope_filter.md` ·
  `_workspace/consult/2026-09-07_channel_split_by_session.md`
- 표기 규약 — **[정적]** = 코드가 그렇게 생겼다 / **[실측]** = 오늘(또는 운영 DB) 로그가 그렇게 나왔다 /
  **[추론]** = 앞의 둘로부터 내가 끌어낸 결론. 문장마다 구분한다.

---

## §0. 결론 한 줄

**조건부 오염 — "있다".** kojiro 의 갭 판정은 **두 경로**에서 서로 **다른 시가**를 읽는다 [정적]:
주 경로(`_swing_buy_poll_loop`)는 KRX REST `stck_oprc`(`J`) 라 **깨끗**하고, 부 경로(`risk.on_tick`)는
오염된 통합 채널 `[7]` 을 읽는다 — 그리고 **`risk.on_tick` 은 donchian 만 skip 하고 kojiro 는 skip 하지
않는다**(`risk.py:646`). 오늘 kojiro 후보 14 중 **1 종목(004020)** 이 09:05 이전부터 WS 구독돼 그 부
경로가 실제로 살아 있었고 [실측], 같은 날 WS-구독 코호트 103 종목으로 잰 결과 **진짜 갭업(≥5%) 8건을
WS 시가 기준으로는 8건 전부 놓쳤다(0/8 탐지, 반대 방향 오탐 0)** [실측] — F-3 의 "위험 증가" 가설이
방향·크기 모두 확인됐다.

---

## §1. 갭 판정 입력의 코드 추적 — 대입부까지

### 1.1 판정 본체 [정적]

`src/engine/strategies/kojiro.py:845-862`

```
845   prev_close = info["prev_close"]
847   if open_price > 0 and prev_close > 0:
848       gap_rate = (open_price - prev_close) / prev_close * 100
851       if gap_rate >= gap_up:   → 로그 + self._bought_today.add(ticker) + NONE   # 당일 영구 스킵
855       if gap_rate <= gap_down: → 로그 + self._bought_today.add(ticker) + NONE   # 당일 영구 스킵
861   if open_price > 0 and current_price < open_price: return NONE                 # 장중 붕괴 가드
```

입력은 둘이다.

| 입력 | 출처 | 판정 |
|---|---|---|
| `prev_close` | `info["prev_close"]` ← `prepare()` 가 `get_recent_daily_normalized` 일봉의 `enriched.iloc[-1]["close"]` 로 채운다(`kojiro.py:369, 441`) | **깨끗** — DB 일봉 계열. 후보 (b) |
| `open_price` | **함수 인자**. `_candidates` 도 `ticker_prices` 도 아니다 | **호출자에 따라 다르다** — 아래 §1.2 |

즉 브리핑의 후보 (a)/(b)/(c) 중 **어느 하나가 아니라, 호출 경로에 따라 (a) 이기도 하고 (c) 이기도 하다.**
`kojiro.py` 안에서 `scanner.ticker_prices` 를 직접 읽는 코드는 **0 건**이다(`grep open_price src/engine/strategies/kojiro.py`
= 시그니처 + 갭/붕괴 판정 + `_build_ohlc_df` 의 일봉 `stck_oprc` 뿐) [정적]. P0-1 의 교훈대로 "읽는 쪽" 을
넘어 **호출자 두 곳의 대입부**까지 따라갔다.

### 1.2 호출자 두 곳 [정적]

**경로 A — `_swing_buy_poll_loop` (주 경로, 09:05~09:30 60초 주기)**

```
scheduler.py:2662  detail = await fetch_stock_detail(t)
scheduler.py:2666  open_price = int(detail.get("stck_oprc") or 0)
scheduler.py:2675  signal = strategy.check_buy_signal(t, current_price, open_price)
```
`fetch_stock_detail` → `condition.py:426 _fetch_stock_detail_and_cache` → `kis_get_quote(STOCK_PRICE_URL,
"FHKST01010100", {"fid_cond_mrkt_div_code": "J", ...})` — **`J` = KRX** [정적]. 5초 TTL 캐시.

**경로 B — `risk.on_tick` (부 경로, 틱마다)**

```
risk.py:495-500   ticker_prices[ticker] = {..., "open_price": open_price, ...}   ← 인자를 그대로 저장
risk.py:646       if strategy.strategy_id == "donchian_swing": continue          ← donchian 만 제외
risk.py:648       signal = strategy.check_buy_signal(ticker, current_price, open_price)
```
그 `open_price` 의 대입부는 `realtime/handler.py:411-419 _parse_tick_prices` → `int(fields[7])` —
통합 채널 `H0UNCNT0` 의 `[7] STCK_OPRC` **원문 그대로, 스코프 필터 없음** [정적].

> ⚠️ **`risk.on_tick` 의 skip 목록에 kojiro 는 없다.** 사이클 G안(2026-05-12)이 "일봉 전략의 틱 평가는
> 구조적 낭비" 라며 넣은 `continue` 는 `donchian_swing` **문자열 하나뿐**이고, 2026-07 kojiro 등록 때
> 같이 넣지 않았다 [정적]. `_workspace/consult/2026-09-07_open_price_scope_filter.md` §187 표가 donchian 을
> "무관(매수 평가가 poll 전용)" 으로 분류한 근거가 kojiro 에는 **적용되지 않는다.**

### 1.3 경로 B 가 실제로 도달하려면 [정적]

`check_buy_signal` 이 갭 판정까지 가려면 (i) 그 ticker 가 WS 구독 중이고 틱이 오고 (ii) MAIN 보드 활성
(`tradable_boards=("main",)`) (iii) `_candidates[ticker]["stage"]==1`(= strict entry 통과 후보)
(iv) 09:05~09:30 여야 한다.

그런데 09:05~09:30 구간의 구독 집합은 **breakout(VB/LTV/BFB/VCP) 후보 + 보유 + 익일청산**뿐이다 —
07:59 `_collect_presubscribe_tickers`(`scheduler.py:1798-1803`)와 5분 `_scan_loop`(`scheduler.py:2345-2348`)
둘 다 `_collect_swing_tickers()` 를 **포함하지 않는다** [정적]. kojiro 후보가 구독되는 유일한 자리는
`run_daily` 의 09:30 블록(`scheduler.py:816`, `extra = breakout + swing`)인데 그때는 **매수 창이 이미 닫힌
뒤**다. ⇒ **경로 B 는 "kojiro 후보 ∩ breakout 후보" 교집합에서만 살아난다** [추론].

---

## §2. 오염 여부와 방향·크기

### 2.1 `[7]` 은 장중 내내 프리장 값이다 — 오늘 직접 관측됐다 [실측]

cycle264 `[open_scope_observe]` 는 종목당 하루 1행이라 대부분 09:00:xx 에 소진됐지만, **그날 첫 MAIN 틱이
늦게 온 3 종목**이 결정적 증거를 남겼다:

```
12:18:14  ticker=190510 oprc_hour=080135 tick_open=13990 cntg_hour=121814 hgpr_hour=101042
14:39:26  ticker=161580 oprc_hour=080053 tick_open=26150 cntg_hour=143926 hgpr_hour=140641
14:55:46  ticker=100840 oprc_hour=080003 tick_open=33400 cntg_hour=145545 hgpr_hour=145528
```

**오후 2~3시 틱인데 `[24] OPRC_HOUR` 가 여전히 `08xxxx`** 다. 같은 프레임의 `[27] HGPR_HOUR` 는
`140641`·`145528` 로 **장중 갱신되고 있다** — 즉 프레임이 낡은 게 아니라 `[7]` 만 프리장 값에 **동결**돼
있다. ⇒ 브리핑 질문 3 의 "일-스코프 상수라면 09:05~09:30 에도 프리장 값인가" 는 **그렇다** [실측].
(오늘 09:05~09:30 구간의 `[open_scope_observe]` 행은 **0 건**이다 — cap 이 09:00:xx 에 소진됐다.
그 구간을 **직접** 잰 관측은 없고, 위 세 행이 그 구간을 **양쪽에서 끼워** 증명한다 [추론].)

### 2.2 오염의 크기 — 갭률 오차 [실측]

오늘 `[open_scope_observe]` 107 행 중 `stock_master_daily`(09-07 확정 시가 + 09-04 전일 종가)와 조인된
**103 종목**으로 두 갭률을 계산했다. `gap_ws = (tick_open − prev_close)/prev_close`,
`gap_krx = (확정 시가 − prev_close)/prev_close`.

| 항목 | 값 |
|---|---|
| WS 시가 ≠ KRX 시가 | **98 / 103 (95.1%)** |
| 갭률 오차 \|gap_ws − gap_krx\| 중앙값 / 평균 / **최대** | 0.97 / 1.31 / **6.77** %p |
| WS 시가 < KRX 시가 (갭 **과소** 측정) | **64** |
| WS 시가 > KRX 시가 (갭 **과대** 측정) | 34 |

### 2.3 게이트가 뒤집히는 빈도와 방향 — F-3 가설 확인 [실측]

kojiro 운영 임계(DB 실측 `gap_up_skip_pct=5.0` / `gap_down_skip_pct=-4.0`)로 두 갭률의 **판정**을 비교했다.

| 판정 전이 | 건수 |
|---|---|
| `pass → skip_up` (**진짜 갭업인데 안 걸렀다**) | **8** |
| `skip_up → pass` (안 걸러도 될 걸 걸렀다) | **0** |
| 갭다운 방향 전이 (양방향) | **0** |

**진짜 갭업(gap_krx ≥ 5.0%) 8 종목 전부를 WS 갭률로는 놓쳤다 — 탐지 0/8 (100% 미탐).**

| 종목 | KRX 기준 갭 | WS 기준 갭 |
|---|---|---|
| 089970 | 7.95% | 3.60% |
| **131290** | **6.77%** | **0.00%** |
| 356860 | 5.79% | 3.90% |
| 039030 | 5.64% | 1.02% |
| 031980 | 5.56% | 4.17% |
| 066570 | 5.46% | 3.23% |
| 095610 | 5.04% | 2.18% |
| 042700 | 5.00% | 3.26% |

131290 은 F-3 이 예고한 병리("프리장 시가 ≈ 전일종가면 `gap_rate ≈ 0`")의 **교과서적 실례**다 —
WS 시가 236,500 = 전일 종가 236,500 으로 **갭률이 정확히 0.00%** 인데 KRX 시가는 252,500(+6.77%)이었다.

### 2.4 반대 방향도 봤다 [실측 + 추론]

브리핑이 요구한 반대 방향("스킵해야 할 게 아닌데 스킵")은 **오늘 0 건**이다. 다만 이것은 오늘이
**갭업 우세 장**이었기 때문이다 — 64/98 이 "KRX 시가가 프리장 시가보다 높다" 였다 [실측].
**갭다운 장에서는 부호가 뒤집혀 "가짜 스킵"(= 진입 기회 상실, 리스크 감소 방향)이 우세해진다** [추론].
이는 시가 스코프 자문 §10-7 의 레짐 의존성 경고와 같은 축이고, **하루치로 방향을 못 박으면 안 된다**는
뜻이기도 하다. 다만 **"게이트가 오작동한다"는 사실 자체는 레짐과 무관**하다 — 95.1% 불일치가 그 근거다.

### 2.5 붕괴 가드도 같은 방향으로 무너진다 [정적 + 추론]

`kojiro.py:861` 의 `current_price < open_price` 는 "지금 시가 아래로 무너지고 있으면 사지 마라" 다.
WS 시가가 실제 KRX 시가보다 **낮으면**(오늘 64/98) 이 가드는 **느슨해진다** — 진짜로는 시가 아래인
종목이 "시가 위" 로 판정돼 통과한다. 갭 게이트와 **같은 위험 증가 방향**이다.

### 2.6 래치의 비대칭 — 왜 오염이 한쪽으로만 새는가 [정적 + 추론]

스킵은 `_bought_today.add(ticker)` 로 **당일 영구 래치**이고, 통과는 래치가 아니다(다음 틱에 재평가).
두 경로가 같은 래치를 공유하므로 [정적]:

- 오염된 경로 B 가 **먼저 "통과"** 로 판정하면 → 그대로 매수까지 갈 수 있고, 뒤늦게 도는 깨끗한 경로 A 는
  이미 늦다.
- 오염된 경로 B 가 **먼저 "스킵"** 으로 판정하면 → 래치가 걸려 깨끗한 경로 A 가 **차례를 못 받는다**.

오늘 실측에서 후자(가짜 스킵)는 0 건이고 전자(놓친 스킵)만 8/8 이었다 [실측].
⇒ **래치 구조 자체가 오염을 "위험 증가" 쪽으로 정류(rectify)한다** [추론].

---

## §3. 매수 창(09:05~09:30)에서의 실제 영향

### 3.1 오늘의 실제 매수는 **깨끗한 경로**로 났다 [실측]

```
09:05:00  고지로 매수 신호: 002380 현재가(495000)   → 매수 수량 0 (900s cooldown)
09:05:00  고지로 매수 신호: 003470 현재가(4725)     → 2주 @4,730 체결
```
둘 다 `_swing_buy_poll_loop` 의 첫 사이클(09:05:00)에서 났다 — 003470 은 같은 초에
`[swing_poll] execute_buy 실패: 003470` 트레이스백이 붙어 poll 경로임이 확정된다 [실측].
두 종목 모두 09:05 이전 WS 구독 이력이 **없다**(003470 의 첫 구독은 09:30:46 — 매수 후 보유 종목으로서)
[실측]. ⇒ **오늘 kojiro 의 진입 판정에 오염된 시가는 쓰이지 않았다.**

참고로 KRX 확정값 기준 갭도 둘 다 무해했다: 002380 = +2.28%(493,000 / 482,000),
003470 = −0.53%(4,720 / 4,745) [실측].

### 3.2 그러나 부 경로는 **오늘도 살아 있었다** [실측]

kojiro 후보(16:20 스냅샷 step 9, 14 종목) 중 **004020(현대제철)** 이 08:00:46 구독 창에 들어 있었다
(`[ws_action_summary] label=44606571 ... SUBSCRIBE=20 ['004020', ...]`). 그 종목의 관측은

```
09:00:29  [open_scope_observe] ticker=004020 oprc_hour=080000 tick_open=32300
          cntg_hour=090029 ... in_main_window=false
```

즉 09:05~09:30 동안 004020 의 `check_buy_signal` 은 **`open_price=32,300`(프리장 시가)** 으로 평가됐다
[실측 + 추론]. KRX 확정 시가는 32,500, 전일 종가 31,500 이므로 갭은 **2.54%(오염) vs 3.17%(진짜)** —
**오늘은 게이트가 뒤집히지 않았다**(둘 다 5% 미만). 붕괴 가드만 200원어치 느슨해졌다.

**노출 빈도 = 14 중 1 (7.1%)** [실측]. 구조적 근거는 §1.3 이고, kojiro 후보(~650 유니버스에서 13~24개)와
breakout 후보(~150개)의 교집합이 만드는 비율이므로 **날마다 다르되 0 은 아니다** [추론].

### 3.3 경로 A 가 깨끗하다는 근거는 오늘 독립적으로 검증됐다 [실측]

`_swing_buy_poll_loop` 이 쓰는 `fetch_stock_detail` 은 cycle264 `open_price_observe.py:311-315` 가
`[open_source_compare]` 의 `rest_oprc` 를 얻는 **바로 그 함수**다 [정적]. 그리고 오늘 판독에서
그 `rest_oprc` 는 확정 일봉 시가와 **98/98 완전 일치**했다 [실측, 판독 정본 §3-b].
⇒ 09:05 시점의 REST `stck_oprc`(J)가 KRX 09:00 시가라는 것은 **추론이 아니라 검증된 사실**이다.

---

## §4. 실측 근거와 그 한계

### 4.1 오늘 확보한 것

| 증거 | 값 | 원천 |
|---|---|---|
| kojiro 갭 스킵 발화 | **0 건** (갭업·갭다운 모두) | EC2 `/tmp/d0907.log` 4,855행 전수 grep `고지로 갭` |
| kojiro 매수 신호 | 2 건 (002380·003470), 둘 다 09:05:00 poll | 같은 로그 |
| kojiro 후보 | 아침 prepare 13 (07:45) / 13 (07:56), 저녁 14 (16:20) | `고지로 대순환 준비 완료` 로그 |
| 후보 ∩ 09:05 이전 구독 | **1 / 14** (004020) | `[ws_action_summary]` 08:00~09:04 SUBSCRIBE 149 종목과 대조 |
| 게이트 오작동 base rate | 진짜 갭업 8건 **0/8 탐지**, 오탐 0 | `[open_scope_observe]` 103종목 × `stock_master_daily` |
| `[7]` 일-스코프 상수 | 12:18·14:39·14:55 틱에서 `oprc_hour=08xxxx` | `[open_scope_observe]` 3행 |
| kojiro 운영 파라미터 | `gap_up 5.0` / `gap_down -4.0` / `position_ratio 0.166` / `max_positions 6` / `weight 0.30` / `enabled=t` | `strategy_config` SELECT |

### 4.2 **없는 것 — 명시한다**

1. **`[open_source_compare]` 는 kojiro 를 담지 않는다.** 브리핑 지적대로 그 마커의 대상 집합은
   `open_price_observe._collect_pending` 이 VB·LTV 의 `_targets[...]["boards"]["main"]` 확정 종목에서
   만든다 [정적]. kojiro 후보는 `_targets` 구조 자체가 없어 **구조적으로 들어갈 수 없다**.
2. **09:05~09:30 구간을 직접 잰 `[7]` 관측은 0 건이다.** cap 이 09:00:xx 에 소진된다(§2.1).
   그 구간의 값은 **끼워 넣기 추론**이다.
3. **kojiro 갭 스킵의 과거 발화 이력이 없다.** `system_logs` INFO 보존이 **09-06~09-07 2일**뿐이고
   (INFO 2일 retention), 그 안에 `고지로 갭%` 은 **0 행**이다 [실측]. 09-06 은 일요일이므로 실질
   표본은 오늘 하루다. ⇒ **"평소 얼마나 자주 갭 스킵이 걸리는가" 는 현재 어떤 원천으로도 알 수 없다.**
4. **아침 후보 목록이 어디에도 영속되지 않는다.** `strategy_funnel_snapshots` 의 kojiro 행은 최근 6
   거래일 전부 `is_provisional=true`(16:20 저녁 캡처)뿐이고 09:30 확정 스냅샷이 없다 [실측].
   그래서 §3.2 의 "1/14" 는 **저녁 목록을 아침 목록의 대용으로 쓴 근사**다(아침 13 vs 저녁 14).
5. **004020 이 09:05~09:30 내내 구독을 유지했는지**는 확인하지 못했다(`[ws_action_summary]` 는 5분
   윈도우 집계라 중간 해제를 종목 단위로 못 가른다).

### 4.3 대신 무엇으로 재야 하는가 — 권고 3안

**(가) 코드 0 줄 — 오늘 내가 쓴 방법을 매일 돌린다.** 노출 코호트는 정의상
`kojiro 후보 ∩ WS 구독` 이고, `[open_scope_observe]` 가 **정확히 WS 구독 집합**을 종목당 1행으로
남긴다. 여기에 `strategy_funnel_snapshots`(kojiro step 9)와 `stock_master_daily` 를 조인하면
"오늘 몇 종목이 오염된 갭으로 심사받았고, 그중 몇이 게이트를 뒤집었나" 가 **사후에 완전히 복원된다**.
비용 0, 즉시 가능. 한계 = 4.2-4(아침 목록 부재)와 4.2-2(09:05~09:30 직접 관측 부재).

**(나) 마커 1개 — `[kojiro_gap_observe]` (권고).** `check_buy_signal` 의 갭 판정 **직전**에
`ticker / open_price / prev_close / gap_rate / verdict` 를 1회/(ticker)/일 INFO 로 남긴다.
이것이 있으면 (가)의 한계 둘이 모두 닫히고, 무엇보다 **"어느 경로가 그 종목을 심사했는가"** 가
`open_price` 값 자체로 드러난다(REST 값 ↔ WS 값이 95% 확률로 다르므로). `kojiro.py` 는 8영역이 아니고
관측 전용이라 행위 변경 0 이지만, **매매 파일이므로 사용자 승인을 받고 넣는다**.

**(다) 마커 확장 — `[open_source_compare]` 에 kojiro 코호트 추가.** `_collect_pending` 이
`registry.get("kojiro").get_scanned_tickers()` 를 추가 소스로 받아 `used_open` 자리에
`ticker_prices[t]["open_price"]`(있으면)를 넣는다. (나)보다 배관이 크고 **매수 창이 지난 09:05:30 에
찍히므로 "그 순간 무엇으로 심사했나" 는 여전히 못 잰다** — (나)보다 열등하다.

⇒ **(가)를 지금 당장 + (나)를 다음 사이클** 권고.

---

## §5. cycle265 로 고쳐지는가 — **아니다**

**채널 분리 자문의 주장은 맞다** [정적 검증 완료].

cycle265 의 설계 범위는 시가 스코프 자문 §0 이 못박은 대로 **"`[7]` 은 그대로 두고, `board="main"` 의
목표가 기준가만 KRX REST 로 갈아 끼우는"** 것이다. 같은 문서가 검증 항목으로 두 번 명시한다:

- §8-3 — "kojiro / momentum / donchian / BFB / VCP `check_buy_signal`·`check_exit_signal` **diff 0**"
- §검증 9 — "kojiro/momentum/donchian/BFB/VCP `check_*_signal` **호출 인자 byte 동일**"

즉 cycle265 는 `handler._parse_tick_prices` 도, `risk.py:495` 의 `ticker_prices["open_price"]` 대입도,
`risk.py:648` 의 `check_buy_signal(..., open_price)` 인자도 **의도적으로 건드리지 않는다**.
kojiro 가 읽는 것은 그 인자이므로 **cycle265 이후에도 kojiro 는 오염된 프리장 시가로 갭을 잰다** [추론].

**별도 시정이 필요하다.** 선택지는 §7 에.

---

## §6. 동일 계열 — 다른 전략의 시가 소비처 전수

`ast` 로 7 전략의 `check_buy_signal`/`check_exit_signal` 본체에서 `open_price` 사용 여부를 전수 확인했다 [정적].

| 전략 | 함수 | `open_price` 사용 | 호출 경로 | 오염 노출 |
|---|---|---|---|---|
| **kojiro** | `check_buy_signal:791` | **O** (갭 + 붕괴) | poll(REST) **+ on_tick(WS)** | 🔴 **본 조사 대상** |
| kojiro | `check_exit_signal:892` | X | — | 없음 |
| **momentum** | `check_exit_signal:177` | **O** (익일청산 갭률 `:209`) | on_tick(WS) | 🟠 **오염 — §6.1** |
| momentum | `check_buy_signal:107` | X | — | 없음 |
| **long_tail_volatility** | `check_buy_signal:657` | **O** (보드 목표가 확정) | on_tick(WS) | 🔴 알려진 사안 (cycle265 범위) |
| **long_tail_volatility** | `check_exit_signal:913` | **O** (익일청산 갭률 `:938`) | on_tick(WS) | 🟠 **오염 — §6.1** |
| **volatility_breakout** | `check_buy_signal:848` | **O** (보드 목표가 확정) | on_tick(WS) | 🔴 알려진 사안 (cycle265 범위) |
| volatility_breakout | `check_exit_signal:1149` | X | — | 없음 |
| **donchian_swing** | `check_buy_signal:1583` | **O** (갭 `:1613`) | **poll(REST) 단독** — `risk.py:646` 이 skip | 🟢 **무관** |
| donchian_swing | `check_exit_signal:1664` | X | — | 없음 |
| bull_flag_breakout | 둘 다 | **X** | — | 없음 |
| vcp_breakout | 둘 다 | **X** | — | 없음 |

`ticker_prices[...]["open_price"]` 를 직접 읽는 비-전략 소비처 [정적]:
`scheduler.py:1420`(`_execute_next_day_clear` 08:00) · `scheduler.py:1659-1660`(`_confirm_breakout_open_prices`) ·
`scheduler.py:1927`(`_resolve_open_price` — WS 우선, REST 폴백).

### 6.1 momentum·LTV 익일청산 갭률 — 방향이 kojiro 와 **반대**다 [정적 + 추론]

```
momentum.py:209   gap_rate = (open_price - pos.buy_price)/pos.buy_price*100
momentum.py:211   if gap_rate < gap_up_threshold(10.0): → Signal.NEXT_DAY_CLEAR   # 즉시 청산
                  else                                 → 트레일링 모드
```
프리장 시가가 KRX 시가보다 **낮으면**(오늘 64/98) `gap_rate` 가 과소 측정돼 **트레일링으로 갈 종목이
즉시 청산**된다. 이는 손실 확대가 아니라 **이익 조기 확정 / 상승 여력 포기** 방향이다 [추론] —
kojiro 와 달리 "리스크 증가" 가 아니라 **"기대수익 훼손"** 이다. 정도는 오늘 코호트 기준 갭률 오차
중앙값 0.97%p 이고, 임계가 10.0% 로 높아 **뒤집힘 빈도는 kojiro(5.0%)보다 낮을 것**이다 [추론 — 미측정].

⚠️ **08:00 `_execute_next_day_clear` 경로는 다른 이야기다.** 그 시각의 `[7]` 은 **그 시점의 최신 프리장
시가**이고, 08:00 익일청산의 설계 의도 자체가 "NXT 프리 시가 기준 갭 판정" 이므로 **그 자리에서는
오염이 아니다** [정적]. 문제는 **MAIN 구간의 `on_tick` 평가가 같은 낡은 값을 계속 읽는 것**이다.

### 6.2 donchian 이 무사한 이유가 곧 kojiro 시정의 힌트다 [정적]

donchian 은 갭 로직이 kojiro 와 사실상 동형인데도 무관하다 — 오직 `risk.py:646` 의 `continue` 한 줄
때문이다. **kojiro 를 그 목록에 넣으면 §2·§3 의 노출이 통째로 사라진다**(§7 안 1).

---

## §7. 권고와 사용자 결정 항목

### 7.1 권고 — 3 안 (택일)

| 안 | 내용 | 장점 | 위험 / 비용 |
|---|---|---|---|
| **1. `risk.on_tick` 에서 kojiro 도 skip** (donchian 과 동형, `risk.py:646` 한 줄) | 부 경로 자체를 없앤다. 매수 판정이 poll(REST, 검증된 깨끗) **단독**이 된다 | **가장 작고 가장 확실**. 갭·붕괴 가드가 즉시 정상 동작. cycle265 와 독립 | 🔴 **`risk.py` = 8영역 — 승인 필수.** 매수 평가 빈도가 틱→60초로 줄어 **그 교집합 종목의 진입 타이밍이 최대 60초 늦어진다**(donchian 이 2026-05 부터 감수해 온 것과 동일). 실질 영향 = 오늘 기준 14 중 1 종목 |
| **2. kojiro 안에서 시가를 다시 읽는다** (갭 판정 직전 `fetch_stock_detail` REST 우선) | 8영역 무접촉 | `check_buy_signal` 은 **동기 함수**라 `await` 불가 — 캐시 선주입 배관이 필요하다. **구조적으로 지저분하고 새 실패 모드를 만든다.** **비권고** |
| **3. 관측만 먼저 (`[kojiro_gap_observe]`, §4.3-나)** | 2~3주 표본을 모아 뒤집힘 빈도를 **kojiro 코호트에서 직접** 잰 뒤 1안 결정 | 행위 변경 0. 8영역 무접촉 | 그동안 노출은 지속. 오늘 base rate(8/8 미탐)가 이미 방향을 확정했다는 반론이 가능 |

**나의 권고 = 3 → 1 순차.** 근거: (a) 오늘 실측은 "게이트가 오작동한다" 를 확정했지만 **kojiro 후보
코호트에서 실제로 뒤집힌 사례는 아직 0 건**이다(004020 은 2.54 vs 3.17% 로 안 뒤집혔다). (b) 1안은
8영역(`risk.py`) 변경이라 승인·검증 비용이 있고, 같은 주말에 cycle265(VB·LTV 기준가 교체, 진입 추정
−27.6%)와 함께 배포하면 **두 변경의 귀인이 섞인다**(시가 스코프 자문 §8.1 이 cycle264 를 관측만으로
자른 것과 같은 논리). (c) 3안 마커는
1안의 **사전 근거이자 사후 검증**을 동시에 준다 — 1안 배포 후 그 마커의 `open_price` 가 100% REST 값과
일치하면 시정이 실증된다.

### 7.2 반례 / 이 권고가 깨지는 시나리오

1. **갭다운 장** — 부호가 뒤집혀 오염이 "가짜 스킵"(진입 상실)으로 나타난다. 그때 1안은 **진입을 늘리는**
   방향이 된다. 방향은 레짐 의존이고 **오늘 하루로 손익 기대값을 판정할 수 없다.**
2. **60초 지연의 대가** — 1안은 교집합 종목의 진입을 최대 60초 늦춘다. 09:05~09:30 의 60초는
   대순환 스윙(멀티데이 보유)에는 무의미에 가깝지만, **급등 초입에서는 슬리피지가 붙는다** [추론].
   donchian 이 2026-05-12 사이클 G안 이래 같은 조건으로 운용돼 온 것이 유일한 선례다.
3. **"갭업을 안 거르는 게 오히려 낫다" 는 가설** — 판독 정본 §5 의 010120 사례(오염 진입이 +6,500 익절)와
   같은 축이다. 갭업 5% 스킵은 **추격 매수 회피**라는 트레이더 상식이지만 백테스트로 재검증된 값은 아니다.
   1안은 그 게이트를 **원래 설계대로 작동시키는 것**이지 게이트가 옳다는 증명이 아니다.
4. **교집합이 0 인 날** — 그런 날 1안의 실효는 0 이다. 오늘 1/14 가 전형인지 아닌지 모른다(표본 1일).

### 7.3 사용자 결정 항목

- **결정 ①** — §7.1 의 1안(8영역 `risk.py` 한 줄) / 3안(관측 선행) / 현상 유지 중 택일.
  권고 = **3안 이번 주 → 1안 다음 주말**(cycle265 와 같은 배포에 넣지 말 것 — 귀인 혼선).
- **결정 ②** — 3안을 택하면 `[kojiro_gap_observe]` 마커 신설 승인(매매 파일 `kojiro.py`, 행위 변경 0).
- **결정 ③** — §6.1 momentum·LTV 익일청산 갭률 오염을 **별도 항목(F-5?)으로 등재**할지.
  방향이 "기대수익 훼손" 이라 kojiro 보다 급하지 않지만, **지금 아무 데도 등재돼 있지 않다.**
- **결정 ④** — `strategy_funnel_snapshots` 에 09:30 확정(non-provisional) 스냅샷이 최근 6 거래일
  **전부 없다**(§4.2-4). 이것 자체가 별건 결함일 수 있다 — 조사 항목으로 등재할지.

### 7.4 후속 검증 권고 (tdd-engineer / tester)

- **tdd-engineer** — 1안 채택 시 회귀 가드 2 축: (i) `risk.on_tick` 이 kojiro 에 대해
  `check_buy_signal` 을 **호출하지 않는다**(spy) (ii) `_swing_buy_poll_loop` 경로는 **byte 동일**
  (kojiro 매수가 poll 로는 여전히 난다). 합성 시리즈는 "프리장 시가 = 전일종가, KRX 시가 = 전일종가×1.07"
  (131290 실측 재현)이 결정적이다 — 오염 경로에서는 `gap=0%` 로 통과하고 깨끗한 경로에서는
  `gap=7%` 로 스킵되는 것이 한 케이스에서 갈린다.
- **tester** — 배포 D+1 판독 축 3: (a) `고지로 갭업/갭다운 스킵` 발화 건수의 **증가**(현재 0 → 비0 이
  정상 시정 서명) (b) kojiro 매수 신호의 타임스탬프가 전부 `_swing_poll` 사이클 경계(09:05:00,
  09:06:00, …)에 맞는지 (c) `[kojiro_gap_observe]` 의 `open_price` 가 그날 `stock_master_daily` 확정
  시가와 100% 일치하는지. ⚠️ **의미 반전** — (a)는 배포 전후 grep 합산 금지.

---

## 부록 A — 재현 절차 (코드 0 줄, §4.3-가)

```bash
# 1) WS 관측 시가 추출 (EC2)
grep -o "\[open_scope_observe\] ticker=[0-9A-Za-z]* oprc_hour=[^ ]* tick_open=[0-9-]*" /tmp/d0907.log \
  | sed "s/\[open_scope_observe\] ticker=//;s/ oprc_hour=/|/;s/ tick_open=/|/" > /tmp/ws_open.csv

# 2) KRX 확정 시가 + 전일 종가 (psql, DATABASE_URL)
#    stock_master_daily 에서 bas_dd = 오늘 / max(bas_dd) < 오늘 을 조인

# 3) kojiro 후보 (근사 — 저녁 provisional 스냅샷)
#    strategy_funnel_snapshots where strategy_id='kojiro' and step_no=9

# 4) 09:05 이전 구독 집합
awk "/^<날짜> (08|09:0[0-4])/" /tmp/d0907.log | grep ws_action_summary \
  | grep -oE "SUBSCRIBE=[0-9]+ \[[^]]*\]" | grep -oE "[0-9]{6}" | sort -u
```
