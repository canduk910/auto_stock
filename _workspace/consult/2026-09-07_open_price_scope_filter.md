# 카드 ① — 시가 기준가 근본 시정 (방향 설계 자문)

- 작성 2026-09-06 (일) · domain-expert · **읽기 전용** (코드·DB·설정·git 무변경, 운영은 SELECT + `docker ps` 만)
- 대상 = 후속 **F-2** (`[7] STCK_OPRC` 에 `[24] OPRC_HOUR` 스코프 필터)
- 선행 정본 = `_workspace/analysis/entry_price_0900_20260906/{forensic.md,code_trace.md}` ·
  `_workspace/consult/2026-09-06_open_entry_hold.md`
- 승인 상태 = 카드 ① **승인됨**. 이 문서는 "해도 되나" 가 아니라 **"어떻게 해야 안전한가"** 를 설계한다.

---

## 0. 권고 한 문단

**소스(`handler._parse_tick_prices`)에서 `[7]` 을 0 으로 강등하는 fail-closed 는 쓰면 안 된다** — `[7]` 은
VB 목표가 말고도 08:00 익일청산 갭 판정·LTV 프리장 보드 목표가·kojiro 갭스킵/시가아래 가드·momentum
익일청산 갭률까지 **여섯 소비처**가 공유하는데, 그중 셋은 0 을 받으면 *조용히 가드가 꺼지거나*(kojiro)
*강제 청산으로 뒤집히고*(momentum) *프리장 매매가 통째로 죽는다*(LTV·익일청산). 대신 **`[7]` 은 그대로
두고 스코프 판별만 얹어, `board="main"` 의 목표가 기준가만 KRX REST(`stck_oprc`, `J`)로 갈아 끼우는**
방향을 권고한다(후보 B 계열). 그리고 이 자문은 조사 정본의 전제 하나를 **실측으로 뒤집었다** — "09:00:05
확정 경로는 `confirmed=0` 으로 무동작" 은 **표시 버그**였고, 실제로는 09-03 VB **51/65**, 09-04 VB
**46/55** 를 확정하고 있었다(§1). 즉 REST 폴백은 고장 나 있지 않고, **오염된 WS 캐시가 먼저 이겨서
REST 차례가 오지 않을 뿐**이다 — (B)는 새 배관을 까는 일이 아니라 **우선순위를 뒤집는 일**이다. 다만
`[24] OPRC_HOUR` 도 REST `stck_oprc` 도 **한 번도 관측된 적이 없고**, 시정하면 VB 진입이 실측 추정
**−27.6%** 줄어들 만큼 행위가 크게 바뀌므로(§9), **월요일에는 행위를 바꾸지 말고 하루치 관측만 심고
(cycle264, 무행위), 다음 주말에 시정(cycle265)** 하기를 권고한다. cycle262 의 90초 보류가 이미 손실의
39% 를 막고 있어 한 주를 더 기다리는 비용은 작다.

---

## 1. ⚠️ 먼저 — 조사 정본의 전제 하나가 실측으로 뒤집혔다

### 1.1 `[breakout_open_confirm] confirmed=0` 은 **표시 버그**다

`forensic.md §1-b` / `code_trace.md §2.5(a)` 는 09:00:05 확정 경로가 "WS·REST 양쪽 다 실패해
`confirmed=0 empty=55/65`" 라고 판정했고, 그 위에 "실제 확정자는 인라인 폴백뿐" 이라는 결론을 세웠다.

**같은 함수가 바로 앞줄에 남기는 비필터 로그를 조회하니 반대였다** (운영 `system_logs`, 2026-09-06 SELECT):

```
09-03 09:00:12  변동성 돌파 시가 확정 [main]: 51/65종목      ← 지상 진실 (scheduler.py:1673)
09-03 09:00:12  [breakout_open_confirm] ... confirmed=0 empty=65   ← 같은 순간, 같은 전략
09-04 09:00:11  변동성 돌파 시가 확정 [main]: 46/55종목
09-04 09:00:11  [breakout_open_confirm] ... confirmed=0 empty=55
09-03 09:00:19  롱테일 변동성 돌파 시가 확정 [main]: 52/90종목  vs  emit confirmed=18 empty=72
09-04 09:00:13  롱테일 변동성 돌파 시가 확정 [main]: 18/32종목  vs  emit confirmed=10 empty=22
09-03 08:00:05  롱테일 변동성 돌파 시가 확정 [pre_nxt]: 5/10종목 vs emit confirmed=0 empty=5
```

**원인(코드 사실).** `_emit_breakout_open_confirm`(`scheduler.py:1676`)은 `_open_confirmed` 를 직접 세지
않고 `strategy.get_targets_status()` 를 거친다. 그 함수는 **`session_tracker.active ∩ tradable_boards`
로 보드를 가린다**(`volatility_breakout.py:708-719`). 09:00:05~09:00:2x 에는 세션 트래커가 30초 주기
stale 캐시라 `active = {PRE_NXT}` 이고, VB 의 `tradable_boards = ["main"]` 이므로 **교집합 = ∅** →
`if not exposed_boards:` 분기가 `open_price: 0` 으로 덮는다(`:766-775`) ⇒ **전 종목 0**.
LTV 는 `tradable_boards=["main","pre_nxt"]` 라 교집합이 `{pre_nxt}` 로 비지 않고, emit 이
`.get("main")` 에 실패해 **top-level(= 첫 확정 보드 = pre_nxt) 값**으로 폴백한다 — 그래서 LTV 만
0 이 아닌 엉뚱한 수를 보였다.

**결과적으로 뒤집히는 것 셋**

| 조사 정본의 서술 | 실측 정정 |
|---|---|
| "09:00:05 경로는 사실상 무동작(0/55·0/65)" | **VB 46~51 종목을 확정한다**(70~78%) |
| "남은 확정자는 인라인 폴백뿐 ⇒ 100% 오염 경유" | 인라인 폴백은 **나머지 9~14 종목 + 09:30 이후** 담당 |
| "(B) REST 폴백은 같은 이유로 또 실패할 것" | REST 폴백은 **고장이 아니다.** 그 앞의 WS 폴링이 먼저 이겨 **차례가 오지 않을 뿐** |

### 1.2 그래도 결함의 결론 자체는 그대로다 — 오히려 증거가 하나 늘었다

WS 폴링이 읽는 것도 `ticker_prices[t]["open_price"]` = **같은 오염된 `[7]`** 이다
(`scheduler.py:1648-1650` ← `risk.py:497` ← `handler.py:471`). 그러니 "46~51 종목이 확정됐다" 는
"46~51 종목이 **오염된 값으로** 확정됐다" 는 뜻이고, 포렌식의 손익·역산 증거는 전부 유효하다.

그리고 위 로그가 **다섯 번째 독립 증거**를 준다. 09-03 LTV 의 09:00:19 sample(= 위 해석상 **pre_nxt 보드**
값)과 09:35 sample(= **main 보드** 값)을 나란히 놓으면:

| ticker | 09:00:19 (pre_nxt 보드) | 09:35 (main 보드) | KRX 일봉 시가 |
|---|---:|---:|---:|
| 000720 | 111,600 | **111,600** | 115,000 (−296bp) |
| 000880 | 123,000 | **123,000** | 127,000 (−315bp) |
| 001450 | 52,900 | **52,900** | 52,000 (+173bp) |
| 003670 | 177,400 | **177,400** | 180,100 (−150bp) |

**프리장 보드 시가와 메인 보드 시가가 4/4 완전히 같은 수**다. 두 보드가 같은 값일 수 있는 경우는
"main 확정이 프리장 스코프 `[7]` 을 그대로 채택했다" 뿐이다.
⚠️ 이 표는 "09:00:19 값 = pre_nxt 보드 값" 이라는 **코드 모델 기반 해석**에 의존한다(§1.1 의
top-level 폴백 경로). 하드 증거가 아니라 **강한 정황**으로 취급하라.

### 1.3 그래서 이 사이클이 반드시 같이 고쳐야 할 것

`[breakout_open_confirm]` 은 **운영자와 조사자를 정반대로 오도한 관측기**다. 조사 하나가 이 로그
때문에 틀린 인과를 세웠고, 그 위에 배포가 하나 올라갔다(cycle262 — 결론은 다행히 무관하게 유효).
행위 0, 로그 1줄짜리 시정이므로 **관측 사이클(cycle264)에 반드시 동봉**하기를 권고한다.

---

## 2. 질문 1 — `[24] OPRC_HOUR` 가 KIS 스펙상 정확히 무엇인가

### 2.1 필드 배치 (KIS MCP `read_source_code` 재실측, 2026-09-06)

`ccnl_total`(H0UNCNT0) 46 컬럼 0-index, 이 자문에서 다시 확인했다:

```
[0]MKSC_SHRN_ISCD [1]STCK_CNTG_HOUR [2]STCK_PRPR ... [7]STCK_OPRC [8]STCK_HGPR [9]STCK_LWPR
... [13]ACML_VOL ... [23]PRDY_VOL_VRSS_ACML_VOL_RATE
[24]OPRC_HOUR [25]OPRC_VRSS_PRPR_SIGN [26]OPRC_VRSS_PRPR
[27]HGPR_HOUR [28]HGPR_VRSS_PRPR_SIGN [29]HGPR_VRSS_PRPR
[30]LWPR_HOUR [31]LWPR_VRSS_PRPR_SIGN [32]LWPR_VRSS_PRPR
[33]BSOP_DATE [34]NEW_MKOP_CLS_CODE ... [43]HOUR_CLS_CODE [44]MRKT_TRTM_CLS_CODE [45]VI_STND_PRC
```

`[24]/[27]/[30]` 은 **완전한 3-형제**(시가/고가/저가 각각의 "그 값이 찍힌 시각")이고, 각각 뒤에
`_VRSS_PRPR_SIGN`/`_VRSS_PRPR`(현재가 대비 부호/차)이 붙는 **동일 서식의 3-튜플**이다. 따라서
`[24]` 는 `[27] HGPR_HOUR` 와 **같은 타입·같은 서식(HHMMSS 6자리 문자열)·같은 의미 축**이다.
`_parse_day_high` 가 `[27]` 에 쓴 파싱·창 판정을 `[24]` 에 **그대로** 쓸 수 있다.

### 2.2 프리장 체결이 없던 종목은 `[24]` 가 무엇을 주는가 — **추측이다. 측정된 적 없다.**

이것이 판정 규칙을 가르는 질문인데, 정직하게 말해 **답을 모른다**.

- 코드 사실: `grep fields\[24\]` = **0건**. 이 프로젝트는 `[24]` 를 한 번도 읽어 본 적이 없다.
- KIS 문서 사실: 로컬 캐시 `docs/kis/domestic-stock-realtime.md` 에는 **필드 단위 설명이 없다**
  (API 목록 + Request/Response 예시뿐). MCP 정본도 컬럼 **이름**만 준다.
- 따라서 아래는 전부 **추론**이며, 이 자문이 shadow 를 권고하는 첫 번째 이유다.

**추론(확신도 높음)** — "시가 시간" 은 그 종목의 **세션 첫 체결이 프린트된 시각**이다. 그러면:

| 상황 | `[24]` 추정값 | `[7]` 추정값 |
|---|---|---|
| 08:00~09:00 NXT 프리장 체결 있음 | `0800xx` (= 프리장 첫 체결 시각) | 프리장 시가 |
| 프리장 체결 없음, KRX 시가 단일가 체결 | `090000`~`090030` (**랜덤엔드**) | KRX 시가 |
| 프리장·시가단일가 모두 미체결, 09:0x 첫 체결 | 그 체결 시각 | 그 체결가 |
| 당일 무체결 | `000000` 또는 빈 문자열 | `0` |

**추론의 근거**는 형제 필드의 라이브 실측이다 — `[day_high_scope_skip]` 이 09-03 **93행**, 09-04
**71행**을 남겼고 **전부 `hgpr_hour=08xxxx`** 였다. 즉 이 채널의 `*_HOUR` 계열은 **09:00 에 리셋되지
않고 08:00 프리장 시각을 MAIN 구간 틱에 계속 실어 보낸다**는 것이 이미 실측됐다. `[24]` 만 다르게
동작할 이유가 없다.

### 2.3 ⚠️ `[27]` 과의 **결정적 비대칭** — 시가 필터는 *탐지기*이지 *시정*이 아니다

| | `[8] 고가` (cycle222-a2) | `[7] 시가` (이번 건) |
|---|---|---|
| 그 값이 하루 중 **갱신되는가** | **된다** — MAIN 고가가 프리장 고가를 넘으면 `[27]` 이 09:xx 로 전진 | **안 된다** — 세션 시가는 첫 체결에서 확정, 종일 상수 |
| 창 밖일 때 버리면 | 잠시(또는 갭다운이면 종일) 0 = "러닝 max" 로 **퇴화만** 함 | **종일 0** = 그 종목의 main 목표가가 **영영 안 잡힘** |
| 필터 단독으로 고쳐지는가 | 대체로 예 | **아니오 — 대체 소스가 반드시 필요** |
| fail-closed 방향 비대칭 | 버리면 현상 유지 / 채택하면 조기 청산 → 버린다 | 버리면 **매수 정지** / 채택하면 잘못된 목표가 → 단순 비대칭 없음 |

**이것이 이 사이클의 설계 핵심이다.** `[24]` 는 "이 `[7]` 은 KRX 메인 시가가 아니다" 를 알려 주는
**판별자**일 뿐, KRX 메인 시가를 **주지 않는다**. 그 값은 오직 **KRX REST**(`FHKST01010100`,
`fid_cond_mrkt_div_code="J"`, `output.stck_oprc`)에서만 나온다. 그래서 어떤 후보를 고르든 설계는
**"판별 + 대체" 2부**여야 한다.

### 2.4 대안 판별자 검토 (기각)

- **`[1] STCK_CNTG_HOUR`** — 틱 자신의 체결 시각. "이 틱이 MAIN 틱인가" 는 알려 주지만 `[7]` 이
  언제 찍혔는지는 모른다. `_maybe_log_day_high_scope_skip` 이 쓰는 **게이트**일 뿐 판별자가 아니다.
- **첫 MAIN 틱의 `[2] STCK_PRPR` 로 시가를 재구성** — 구독 슬롯 41 한계·no_feed(cycle252)·WS 지연
  때문에 "처음 **관측된** MAIN 틱" 은 시가 단일가 체결이 아니라 그 뒤 몇 틱일 수 있다. 변동성 큰
  개장에서 수십~수백 bp 어긋난다. **시가를 근사로 대체하면 목표가가 다시 근거를 잃는다** — 기각.
- **`[34] NEW_MKOP_CLS_CODE` / `[43] HOUR_CLS_CODE`** — **틱 자신의** 장운영/시간 구분이다.
  `[1]` 과 같은 축이고 `[7]` 의 스코프를 말해 주지 않는다. 다만 shadow 에 **부가 기록**해 두면
  "프리장 틱 / 시가단일가 틱 / 장중 틱" 라벨이 붙어 판독이 쉬워진다(권고: 기록만).

---

## 3. 질문 2 — `_parse_tick_prices` 반환값 전수 추적: 시가를 바꾸면 또 무엇이 바뀌는가

### 3.1 배관

```
handler._parse_tick_prices(fields)  → (int(fields[2]), int(fields[7]))      handler.py:279
  → handler._handle_tick            → change_rate = (cur-open)/open*100     handler.py:478-479
  → _on_tick(ticker, cur, open, change_rate, day_high=, acml_vol=)          handler.py:485-488
  → RiskManager.on_tick(...)                                                risk.py:446
      ├─ ticker_prices[ticker] = {"current_price","open_price","change_rate","prdy_ctrt"}   risk.py:495-499
      ├─ strategy.check_exit_signal(ticker, cur, open)   (보드 가드 前)      risk.py:595
      └─ strategy.check_buy_signal(ticker, cur, open)    (보드 가드 後)      risk.py:648
```

### 3.2 소비처 × 필요한 스코프 × **소스에서 0 으로 강등했을 때** 무슨 일이 나는가

| # | 소비처 (파일:행) | 필요한 시가 | `[7]`→0 시 코드 동작 | 판정 |
|---|---|---|---|---|
| 1 | VB `on_open_price_confirmed` + 인라인 폴백 (`volatility_breakout.py:825-838, 866-869`) | **KRX main 시가** | `open_price<=0` 조기 return → `boards["main"]` 미생성 → `board_info` None → `Signal.NONE`. **단 `_confirm_breakout_open_prices` REST 폴백이 구제한다** | 고치려는 대상 |
| 2 | LTV `board="main"` (`long_tail_volatility.py:636-654, 704-706`) | **KRX main 시가** | 동일 | 고치려는 대상 |
| 3 | LTV `board="pre_nxt"` (08:00:05 confirm + 프리장 인라인 폴백) | **프리장 시가 (지금 값이 정답)** | 프리장 내내 0 ⇒ **LTV 프리장 매수 전면 사망**. REST `"J"` 는 08:00 에 KRX 시가가 없으므로 구제 불가 | **🔴 파괴** |
| 4 | `scheduler._execute_next_day_clear` (08:00:30, `scheduler.py:1409-1418`) | **오늘 첫 시가(프리장)** | `today_open<=0` → `_resolve_open_price` 도 0 → `_pending_next_day_clear` ⇒ **모든 익일청산이 09:00 KRX 시장가로 밀린다**. 덤으로 LTV 갭업 종목의 `pos.high_since_buy = today_open` 앵커 리셋(사이클 142)이 사라져 **09:00 개장 즉시 매도** 위험 부활 | **🔴 파괴** |
| 5 | `momentum.check_exit_signal` 익일청산 갭률 (`momentum.py:209-222`) | 오늘 시가 | `gap_rate = (0 - buy_price)/buy_price = −100%` < `gap_up_threshold(10)` ⇒ **무조건 `Signal.NEXT_DAY_CLEAR`**. 프리장은 `_defers_pre_market_exit` 가 막지만(`risk.py:214`), **MAIN 구간에도 `[24]`=08:xx 인 종목은 종일 0** 이라 갭업 러너까지 강제 청산 | **🔴 위험 반전** |
| 6 | `kojiro.check_buy_signal` 갭업/갭다운 스킵 + "시가 아래" 거부 (`kojiro.py:847-862`) | KRX main 시가 | 두 가드가 **`if open_price > 0` 로 감싸여 있어 통째로 침묵** ⇒ 갭업 5%↑·시가 아래 종목을 **거르지 않고 산다** = **리스크 증가 방향** | **🔴 가드 무음 해제** |
| 7 | `donchian_swing.check_buy_signal` 갭스킵 (`donchian_swing.py:1613-1621`) | KRX 시가 | **무관** — 매수 평가가 `_swing_buy_poll_loop` 전용이고 그 경로의 시가는 이미 REST `stck_oprc`(`scheduler.py:2635`) | 무영향 |
| 8 | `handler` 파생 `change_rate` → `ticker_prices["change_rate"]` | 표시 | 0.0 폴백. momentum 은 자기 `prev_close` 로 따로 계산(`momentum.py:138`) | 표시만 |
| 9 | `routes/realtime.py:339`, `scanner.get_scan_state` | 표시 | 0 표시 | 표시만 |

**결론.** `[7]` 은 여섯 개의 서로 다른 의미로 소비되고, 그중 **3·4·5·6 은 프리장/세션 시가가 정답이거나
0 을 "가드 해제"로 해석**한다. **소스 레벨 파괴는 명확히 기각**이다. 특히 6(kojiro)은 후속 F-3 이
"갭을 잘못 잰다" 로 등재해 둔 항목인데, 소스 0 강등은 그것을 "갭을 아예 안 잰다" 로 **악화**시킨다.

---

## 4. 질문 3 — 보드별로 어떻게 갈라야 하는가

**규칙(트레이더 어법).** *기준가는 "내가 지금 매매하는 세션이 열린 가격" 이어야 한다.*

| 보드 | 옳은 기준가 | 근거 |
|---|---|---|
| `pre_nxt` (08:00~09:00) | **프리장 시가 = 현재의 `[7]`** | 그 세션에서 매매하니 그 세션의 시가가 기준. LTV 의 설계 의도(사이클 38) |
| `main` (09:00~15:30) | **KRX 09:00 시가** | 15:20 당일청산 전략의 세션은 KRX 정규장이다 |
| `post_nxt` (15:40~20:00) | 애프터 세션 시가 (현행 유지) | VB·LTV 모두 `tradable_boards` 에 없음 — 이번 범위 밖 |

**왜 "NXT 시대에는 프리장 시가가 진짜 시가 아닌가" 에 대한 반론까지 적어 둔다.** 통합 시장에서
"오늘의 시가" 를 08:00 로 보는 해석은 그 자체로 틀린 말이 아니다. 그러나 이 전략에서는 성립하지 않는다:

1. **단위 불일치.** `target_offset = int(prev_range × k) × k_value` 의 `prev_range` 는 **KRX 일봉의
   H−L** 이다(`stock_master_daily`). KRX 스케일의 변동폭을 NXT 프리장 기준가에 얹으면 두 시장의
   기준선이 섞인다.
2. **프리장 시가는 정보가 없다.** 호가 두께가 얇고 거래원이 슬림해 프리장 첫 체결은 전일 종가(기준가)
   근처의 소량 체결인 경우가 대부분이다 — 실제로 cycle222-a2 의 000250 실측이 "프리장 시가 =
   전일 종가와 **정확히 일치**" 였다. 그 값은 오늘 세션에 대해 아무것도 말해 주지 않는다.
3. **돌파의 확인 기능이 사라진다.** 포렌식 105560 사례: 역산 기준가 169,300 은 그날 KRX 정규장
   **저가 169,400 보다도 낮다** — KRX 세션에서 **한 번도 체결되지 않은 가격**이다. 그 위에 세운
   목표가는 09:00:00 에 이미 뚫려 있고, VB 는 추격 상한이 없으므로 **"돌파 확인" 이 아니라
   "시초가 무조건 추격매수"** 가 된다.

⇒ **`main` 에 한해서만** 기준가를 갈아 끼운다. **`pre_nxt` 는 무접촉**이 계약이고, 회귀 가드로 못 박아야
한다(LTV 프리장 매수 경로 diff 0).

---

## 5. 후보 평가

### (A) fail-closed(0 강등) — **기각**

- 먼저 브리핑의 전제를 하나 **정정**한다. "0 이면 그 종목 그날 진입 포기" 는 절반만 맞다 — 실제로는
  `_confirm_breakout_open_prices` 의 **WS 분기가 실패하면서 REST 분기로 라우팅**된다(§1). 그래서
  (A)는 "매수 전면 중단" 이 아니라 사실상 **"REST 로 갈아 끼우기"의 난폭한 구현**이다.
- 그러나 그 부수효과가 §3.2 의 3·4·5·6 을 **동시에** 부순다. 목적(main 목표가)에 필요한 것보다
  **훨씬 넓은 파괴**를 대가로 치른다.
- 추가로 (A)는 fail-closed 인데, 이 시스템의 명시 금기는 "설정/데이터가 없으면 매매를 막는" 방향이다
  (P0-1 유령 키가 BFB/VCP 를 전 기간 체결 0건으로 만든 그 방향). **기각.**

### (B) REST 폴백 — **채택 (핵심 수단)**

- **"왜 09:00:05 경로가 무동작인가" 에 대한 답 = 무동작이 아니었다**(§1.1). 확정은 되고 있고,
  다만 **WS 폴링이 먼저 돌아 오염된 값으로 확정해 버려 REST 분기가 그 종목을 건너뛴다**
  (`scheduler.py:1641-1652` 폴링 → `:1657` `unconfirmed` 만 REST).
  ⇒ **(B)는 새 경로를 만드는 일이 아니라 `board=="main"` 일 때 WS 분기를 신뢰하지 않는 일이다.**
- **미확정으로 남는 9~14 종목**(09-03 14/65, 09-04 9/55)은 REST 실패가 아니라 **그 시각에 아직
  체결이 없어 `stck_oprc="0"` 인 종목**으로 읽는 것이 자연스럽다(거래정지·초저유동·시가단일가 미체결).
  그 종목들은 이후 인라인 폴백/09:30 `_scan_loop` 재시도로 채워진다(`[open_confirm_retry]`).
- **호출량·Rate Limit 산정 (코드 + 실측)**
  - 대상 = VB `_targets` 55~65 + LTV 32~90, 합집합 추정 **~100~140** (VB·LTV 유니버스 상당 부분 중복).
  - `fetch_stock_detail` = `kis_get_quote` → **시세 풀 화이트리스트 통과**
    (`/uapi/domestic-stock/v1/quotations/inquire-price`, `base.py:79`). 보조 계좌 **7개 활성**(DB 실측),
    라벨별 `Semaphore(18)`, 그러나 **`_rate_limit()` 는 전역 초당 20건**(`base.py:437-452`)이다.
  - 호출은 **순차 await** 다(`scheduler.py:1657-1663`). 운영 실측 처리율 = LTV 38종목이 09:00:13→
    09:00:19 = **~6.3건/초**. ⇒ 140종목 ≈ **20~25초**.
  - **90초 보류(cycle262) 안에 충분히 들어간다** — 09:00:05 시작이면 ~09:00:30 종료, 진입 재개
    09:01:30. 이 시너지는 우연이 아니라 cycle262 가 벌어 준 시간이다.
  - ⚠️ **부작용 1** — `_drain_pending_next_day_clear()` 가 confirm **뒤**에 순차 호출된다
    (`scheduler.py:780-782`). 보류된 익일청산 시장가 정리가 ~09:00:12 → ~09:00:30 으로 밀린다.
    (완화: drain 을 confirm **앞**으로 옮기거나 — 시장가라 시가 확정과 무관 — REST 를 10건 단위
    `gather` 로 제한 병렬화. **둘 다 별도 결정 항목**으로 남긴다.)
  - ⚠️ **부작용 2 — 랜덤엔드.** KRX 는 **시가 단일가에도 랜덤엔드(0~30초)** 를 적용한다. 09:00:05 의
    REST 는 아직 시가가 프린트되지 않은 종목에 `stck_oprc="0"` 을 줄 수 있다. ⇒ **보류 창 안에서
    유계 재시도**(예: 09:00:40, 09:01:10)를 반드시 붙인다. 안 붙이면 그 종목은 09:30 `_scan_loop`
    까지 목표가가 없다(**1.5시간 구멍**).
- ⚠️ **미검증 전제.** `fid_cond_mrkt_div_code="J"` = **KRX** 는 KIS 정본으로 확인했다(MCP
  `inquire_price` docstring: `J:KRX, NX:NXT, UN:통합`, 2026-09-06 실측). 그러나 **09:00 직후의
  `stck_oprc` 가 실제로 KRX 시가인지 라이브로 대조한 적은 없다.** 이것이 shadow 를 권고하는
  두 번째 이유다.

### (C) 보류(유효 시가가 올 때까지 목표가 확정 연기) — **단독으로는 불가**

`[24]` 는 **하루 상수**다(§2.3). 프리장 체결이 있었던 종목은 09:00 이 지나도, 15:00 이 지나도
`oprc_hour = 08xxxx` 다. ⇒ "유효한 시가가 올 때까지 기다린다" = **영원히 기다린다** =
그 코호트(추정 **≥32%**, 아래 §10) 의 **종일 매수 정지**. cycle262 의 90초 보류와 **성격이 다르다**
(그쪽은 시계가 흘러가면 반드시 풀린다). **(B)와 결합할 때만 의미가 있다** — 즉 "REST 가 값을 줄
때까지 그 종목의 main 목표가를 확정하지 않는다" 라는 형태로만 살아남는다.

### (D) shadow 선행 — **채택 (1단계)**

`[24]` 도 REST `stck_oprc` 도 **한 번도 관측된 적이 없다**. 그리고 시정의 행위 영향이 크다(§9).
관측은 행위가 0 이므로 월요일 판독을 오염시키지 않는다.

### (E) 권고안 = **D → (B+C) 2단계**, 판별자는 `[24]`, 대체자는 REST

```
cycle264 (관측·무행위)  ─ 월요일 09:00 발효
   ① handler: [24] 파싱 + [open_scope_observe] 마커 (1회/ticker/일, MAIN 창 게이트)  … 8영역
   ② scheduler: 09:05 백그라운드 대조 태스크 [open_source_compare]                    … 비8영역
   ③ scheduler: [breakout_open_confirm] 표시 버그 시정 (§1.3)                          … 비8영역
        ↓  하루치 데이터로 3자 대조: 사용된 시가 vs REST stck_oprc vs stock_master_daily KRX 시가
cycle265 (시정)         ─ 다음 주말 배포
   ④ board=="main" 일 때 WS 분기를 스코프 게이트로 통과시키고, 실패 시 REST 로 대체
   ⑤ VB/LTV 인라인 폴백도 main 에서는 스코프 게이트 통과분만 채택
   ⑥ 보류 창 안 유계 재시도 + 파라미터 킬스위치
```

---

## 6. 질문 4 — 배선 위치, 8영역 접촉, 회귀 표면

| 배선안 | 파일 | 8영역? | 실효 | 평가 |
|---|---|:--:|---|---|
| **H. handler 파싱부에서 `[7]` 을 0 강등** | `handler.py` | ✅ | 여섯 소비처 전부에 전파 | **금지** (§3.2) |
| **R. `risk.on_tick` 에서 전략별 분기** | `risk.py` | ✅ | 전략 지식이 risk 로 샌다. `_prev_price` baseline 동결 등 부작용 | 비권고 |
| **S. `scheduler._confirm_breakout_open_prices` 에서 main 한정 대체** | `scheduler.py` | ❌(승인 필요·라인 상한) | **정확히 목표가 확정 경로만** 바뀐다 | **권고 (주 배선)** |
| **T. 전략 파일(VB/LTV)에서 main 인라인 폴백 게이트** | `volatility_breakout.py`·`long_tail_volatility.py` | ❌ | 스케줄러가 못 잡은 잔여분(9~14종목·09:30 이후·재-prepare 후) 커버 | **권고 (보조 배선)** |
| **O. handler 에 판별자 *관측만* 얹기** | `handler.py` | ✅ | 행위 0. `[day_high_scope_skip]` 과 동형 | **권고 (shadow 한정)** |

### 6.1 판별자를 전략까지 흘리려면 — 두 가지 길

시정 단계(T)에서 VB/LTV 가 "이 틱의 `[7]` 이 main 스코프인가" 를 알아야 한다.

- **(i) 배관 확장** — `handler → _on_tick(oprc_hour=) → risk.on_tick → leaf 모듈`.
  `day_high`(cycle222-a)·`acml_vol`(cycle227) 이 쓴 **키워드 + 기본값** 패턴 그대로라 기존 호출자
  무해. 다만 **8영역 2파일**(handler + risk)을 시정 사이클에 끌어들인다.
  ⚠️ 저장은 반드시 **전용 leaf 모듈**(`tick_volume` 선례)에 — `ticker_prices` 주입 금지
  (donchian `ext_pct` 가 그 dict 를 읽는다, `donchian_swing.py:1626-1634`).
- **(ii) 판별자 없이** — main 인라인 폴백을 **끄고** 스케줄러 REST 확정만 신뢰.
  8영역 **0접촉**. 대신 스케줄러가 못 잡은 종목은 다음 재시도까지 목표가가 없다(커버리지 손실).

**권고**: cycle265 는 **(ii)로 시작**하고(8영역 0), shadow 결과가 `[24]` 의 신뢰성을 입증하면
**(i)로 승격**해 인라인 폴백 커버리지를 되살린다. 이렇게 하면 시정의 성패가 **미검증 필드에
걸리지 않는다** — `[24]` 가 쓸모없는 값으로 판명돼도 시정은 그대로 선다.

### 6.2 회귀 표면 (시정 단계에서 반드시 잠글 것)

1. **LTV `pre_nxt` 경로 diff 0** — 08:00:05 confirm·프리장 인라인 폴백·프리장 목표가 산식.
2. **`_execute_next_day_clear` diff 0** — `ticker_prices["open_price"]` 소비 무접촉.
3. **kojiro / momentum / donchian / BFB / VCP `check_buy_signal`·`check_exit_signal` diff 0**.
4. **`handler._parse_tick_prices` 반환값 byte 동일** — `[7]` 은 절대 가공하지 않는다(AST 가드).
5. **`_open_confirmed` 계약** — 한 번 확정된 보드는 재확정되지 않는다(idempotent skip 보존).
6. **`_apply_budget_limit` / `check_exit_signal` 무접촉** — 진입 기준가만 바뀌고 수량·청산 규약은 불변.
7. **`session_tracker` 커플링 금지** — main 스코프 창은 `_HGPR_HOUR_MAIN_START/END` 와 같은
   **명시 상수**(09:00:00~15:30:00)로 판정한다. `tradable_boards`·`_BOARD_SCHEDULE`(15:40) 로
   판정하면 매수 목적 보드 변경이 기준가 규약을 조용히 바꾼다(cycle222-a3 G-7 선례).

---

## 7. 질문 5 — 관측 마커 설계

브리핑의 지적이 정확하다. 고가는 "걸렀다" 로 충분하지만 **시가는 fail-open 이라 "무엇으로
대체했다" 를 남겨야** 한다. 아래는 4종 + 1 카나리아.

### 7.1 cycle264 (shadow)

**① `[open_scope_observe]`** — `handler.py`, **INFO**, **1회/ticker/일**, `KstDailyEmitCap`(cycle258) 재사용

```
[open_scope_observe] ticker=%s oprc_hour=%s tick_open=%d cntg_hour=%s hgpr_hour=%s
                     mkop=%s hour_cls=%s in_main_window=%s
```
- **게이트** = `[1] STCK_CNTG_HOUR` 가 MAIN 창(090000~153000) 안일 때만
  (`_maybe_log_day_high_scope_skip` 과 동일 설계 — 프리장 틱이 1회 cap 을 태우면 코호트 분모가 죽는다).
- **창 안/밖 모두 남긴다**(`in_main_window=true|false`) — 분모가 있어야 오염 **비율**을 잰다.
  `[day_high_scope_skip]` 은 skip 만 남겨서 분모가 없었고, 그래서 지금 "93/287" 을 **추정**으로만 쓴다.
- **볼륨** — 구독 ~287 × 1행 = **~290행/일**. 운영 `system_logs` 는 거래일 **8,238~8,542행/일**
  (09-03/09-04 실측)이므로 +3.4% 다. 보존은 08-06 부터 살아 있다. **수용 가능.**
- ⚠️ 배치 = **`_handle_tick` 안, `parsed` 성공 뒤**, `try/except` 로 완전 흡수.
  **`_parse_tick_prices` 는 한 글자도 건드리지 않는다**(byte 동일). 이 함수에서 예외가 새면
  `_on_tick` 이 re-raise 해 **WS 재연결이 틱마다 발생**한다(사이클 88 G-REJECT-1) = 손절 사각.

**② `[open_source_compare]`** — `scheduler.py`, **INFO**, 1회/(ticker,strategy)/일, **09:05 백그라운드**

```
[open_source_compare] strategy=%s ticker=%s board=main used_open=%d rest_oprc=%d
                      delta_bp=%.1f target_used=%d target_if_rest=%d
```
- `used_open` = 그날 실제로 목표가를 만든 값(`strategy._targets[t]["boards"]["main"]["open_price"]`).
- `rest_oprc` = 그 시점 `fetch_stock_detail(ticker)["stck_oprc"]`.
- **왜 09:05 인가** — KRX 시가는 프린트되면 하루 종일 불변이므로 언제 읽어도 같다. 09:00~09:01:30
  (보류 해제 직전)에 140건을 쏘면 전역 20건/초 한도를 매수 주문과 다투게 된다. **09:05 는 공짜다.**
- **throttle** = 5건/초 상한 + `asyncio.sleep` — 스캔·폴 루프와 경합 금지.
- 이 한 줄이 **세 소스(사용값·REST·`stock_master_daily` KRX 시가)를 익일 오프라인에서 3자 대조**
  하게 해 주고, 그것이 카드 ①의 모든 미검증 전제를 한 번에 닫는다.

**③ `[breakout_open_confirm]` 표시 버그 시정** (§1.3) — `_open_confirmed` 를 직접 세거나,
현행 필드를 남기고 `truth_confirmed=%d truth_total=%d` 를 **추가**한다(하위 호환 안전).

### 7.2 cycle265 (시정)

**④ `[open_scope_substituted]`** — **"무엇으로 대체했다"** 정본, 1회/(ticker,strategy)/일

```
[open_scope_substituted] strategy=%s ticker=%s board=main reason=oprc_hour_out_of_window
                         tick_open=%d oprc_hour=%s substituted_with=rest rest_oprc=%d
                         delta_bp=%.1f target_before=%d target_after=%d
```

**⑤ `[open_scope_unresolved]`** — 대체도 실패해 **그 종목이 목표가를 못 가진** 경우 (**커버리지 손실 정본**)

```
[open_scope_unresolved] strategy=%s ticker=%s board=main reason=rest_zero|rest_error|no_tick
                        retry_no=%d
```
- 이 마커가 **0 이 아니면 "고치려다 매수를 잃고 있다"** 는 뜻이다. cycle262 의
  `[open_entry_hold_blocked]` 와 같은 급의 판독 정본으로 다뤄야 한다.

**⑥ `[open_scope_config]`** — 카나리아, **1회/(strategy, **값**)/일**
(cycle262 `[open_entry_hold_config]` 가 확립한 이탈 — 장중 `PUT /params` 로 값을 바꿔도
마커가 남아야 한다)

```
[open_scope_config] strategy=%s mode=off|enforce source=default|override
```

**공통 계약** (cycle262 계약 ⑩ 답습, 어기면 안 된다)
- 모든 emit 은 `try/except` + `observer_trace.trace_observer_failure` 로 **2차 예외까지 흡수**.
- **행위는 관측 밖** — 마커가 어떻게 터지든 기준가 선택 결과는 바뀌지 않는다.
- cap 은 **마커마다 별개 인스턴스**(같은 슬롯을 다투면 config 1행이 그날 표본을 통째로 침묵시킨다,
  cycle236 선례).
- hot path 는 `logger` 만 — `write_log`/DB/`await` 금지(AST A-1 동형).

---

## 8. 질문 6·7 — 배포 시점과 되돌리기

### 8.1 배포 시점 — **월요일에는 관측만. 시정은 다음 주말.**

**오늘 이미 두 사이클이 올라갔다**(cycle262 = VB·LTV 진입 행위 변경, cycle263 = 일봉 적재).
월요일 09:00 은 그 둘의 **첫 실전 검증**이다. 여기에 기준가 시정까지 얹으면:

- VB 진입 건수가 추정 **−27.6%**(§9) 줄어드는데, 그것이 (a) 90초 보류 때문인지 (b) 기준가 상향
  때문인지 (c) 그날 장세인지 **분리 불가능**해진다.
- `[open_entry_hold_blocked]`(cycle262 의 would_buy 정본)의 의미가 바뀐다 — 기준가가 바뀌면
  "막지 않았으면 샀을 것" 의 목표가 자체가 달라져 그 마커가 재검토 트리거로 못 쓰인다.

반면 **관측(cycle264)은 행위가 0** 이라 월요일 판독을 오염시키지 않고, **월요일은 이번 주 유일한
관측 기회**다(다음 개발 창은 주말). 놓치면 시정이 한 주 더 밀린다.

| | 권고 | 근거 |
|---|---|---|
| **오늘(일) 밤 배포** | ① handler 관측 마커 ② scheduler 09:05 대조 ③ `[breakout_open_confirm]` 표시 시정 | 행위 0, 월요일 발효, 독립 커밋으로 단독 revert 가능 |
| **월요일 장중** | **아무것도 배포하지 않는다** (보유 중 09:00~15:30 push 금지 = D6) | cycle232 D6 |
| **다음 주말** | 기준가 시정(cycle265) + 킬스위치 | shadow 3자 대조 결과를 읽은 뒤 |

⚠️ 오늘 밤 배포는 **full 모드**(`src/**` 변경 ⇒ backend 재생성)다. 주말 장외라 D6 는 안 걸리지만
`20:00~20:15` 는 주말에도 push 금지다.

### 8.2 되돌리기 — 파라미터 킬스위치 (cycle262 선례를 그대로)

- **cycle264(관측)** — 파라미터 불필요. 되돌리기 = 다음 커밋 revert. 마커가 시끄러우면
  cap 이 이미 1회/ticker/일이라 폭주 위험 없음.
- **cycle265(시정)** — **`open_price_scope_mode`**(전략별, `"off" | "enforce"`) 권고.
  - **키 부재 = `off` = 현행 행위(fail-open)** — cycle245 K_ρ 관례와 같은 방향. *매수를 줄이는
    통제*이므로 "설정이 없으면 막는다" 는 P0-1 재현 경로다.
  - `DEFAULT_PARAMS` 에 **VB·LTV 둘 다** 명시(AST 가드로 스코프 = 정확히 둘).
  - **`PARAM_RANGES`/`INT_PARAMS` 편입 금지** — 진입 정체성 상수. AI 자문 자동 적용 화이트리스트도 배제.
  - **반영 시점** = `PUT /api/strategies/{id}/params` **즉시**(라우트가 in-memory `config.params` 를
    덮는다) / `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만**. D6 때문에
    **장중 실효 롤백 수단은 PUT 뿐**이다.
  - ⚠️ **배포 전 PUT 은 무음 실패한다** — 라우트가 미지 키를 조용히 버리고 `params` JSONB 를 통째로
    덮어 먼저 넣은 값까지 지운다(cycle245 실측). **DB 선반영 금지.**
  - 부분 롤백 = VB 만 `enforce`, LTV 는 `off` (키가 전략별이라 가능).

---

## 9. 행위 영향 규모 — **VB 진입이 추정 27.6% 사라진다**

`data/vb_forensic_final.csv`(VB BUY 116건, 2026-04-24~09-04, 09-06 일봉 보정 반영) 위에서
"기준가를 KRX 시가로 바꿨다면 그날 고가가 새 목표가를 넘겼는가" 를 계산했다.

| 지표 | 값 |
|---|---|
| KRX시가 기준 목표가를 당일고가가 **넘김**(= 진입 유지 추정) | **84/116 (72.4%)** |
| **못 넘김**(= 진입 소멸 추정) | **32/116 (27.6%)** |
| 조기(09:00~09:01:30) 코호트 20건 중 소멸 | **11 / 유지 9** |
| KRX시가 − 역산기준가 (bp) | median **+85.3** · mean **+196.1** |
| 방향이 "목표가 상승(=진입 어려워짐)" 인 비율 | **79/116 (68%)** |

**트레이더 해석.** 목표가가 median 85bp·mean 196bp 올라간다. VB 의 `target_offset` 자체가
대략 종목가의 1.3~2.6% 수준이므로, **기준가 오차가 offset 과 같은 크기의 오차**였다는 뜻이다.
"돌파 확인" 이라는 장치가 절반쯤 무효였고, 고치면 **진입 빈도가 눈에 띄게 준다**. 손익비가
좋아질 가능성이 높지만(가짜 돌파 제거) **표본이 줄어 확인에 더 오래 걸린다** — 이건 트레이드오프이지
공짜가 아니다. 사용자가 "VB 가 갑자기 안 산다" 를 결함으로 오해하지 않도록 **사전에 이 숫자를
공유**해야 한다.

⚠️ 이 추정의 한계 = (a) `implied_open_cap`(역산 기준가)은 `k_value_krx_main=1.3` 가정에 의존한다
(과거 구간이 1.0 이었다면 값이 흔들린다) (b) "당일 고가 ≥ 목표가" 는 대용 지표다 — 실제 조건은
`prev < target ≤ current` 라 **장중 경로**를 봐야 하는데 일봉만 있다 (c) 매수 시각 이후에만
고가가 형성된 경우는 과대 추정한다.

---

## 10. 반례 / 한계 — 이 권고가 틀릴 수 있는 경우

1. **`[24] OPRC_HOUR` 가 기대와 다르게 동작할 수 있다.** 한 번도 안 찍어 봤다. 예컨대
   KIS 가 이 필드만 09:00 에 리셋하거나, 통합 채널에서 항상 `090000` 을 주거나, 빈 문자열일 수 있다.
   ⇒ 그래서 shadow 가 선행이고, 그래서 cycle265 의 1차 구현은 **`[24]` 에 의존하지 않는 (ii) 안**이다.
2. **REST `"J"` `stck_oprc` 가 정말 KRX 시가라는 보장이 없다.** KIS 정본 문자열
   (`J:KRX, NX:NXT, UN:통합`)은 확인했지만 **라이브 대조는 0회**다. 만약 KIS 가 통합 피드를
   섞어 준다면 **틀린 수를 다른 틀린 수로 바꾸는 것**이 된다. `[open_source_compare]` 의 3자 대조가
   유일한 방어다.
3. **"프리장 시가가 진짜 시가" 라는 반대 해석이 성립하는 종목군이 있다.** NXT 프리장에 실질
   유동성이 붙은 종목(대형주 일부)이면 프리장 시가가 정보를 담는다. 그런 종목에서는 이번 시정이
   **정상 신호를 지우는** 쪽으로 작동할 수 있다. ⇒ shadow 에서 `[24]`·프리장 거래량과 함께
   코호트를 나눠 보는 것이 후속 과제.
4. **오염 규모를 아직 모른다.** 지금 가진 것은 (a) `[day_high_scope_skip]` 93/71행 vs 구독 ~287
   = **≥25~32%**(고가가 프리장에 찍힌 종목만 세므로 **하한**) (b) 09-03 스탬프 10종목 중 7 불일치
   (n=10, 편향 가능) (c) 매수 코호트 116건 중 97%가 >10bp 차 — 그러나 이건 **선택 편향**(기준가가
   낮을수록 매수가 나기 쉽다) + 역산 잡음이 섞여 **과대**다. 셋이 25%~97% 로 흩어져 있다.
   REST 부하 산정이 이 숫자에 걸려 있으므로 shadow 로 확정해야 한다.
5. **cycle262 와의 상호작용.** 90초 보류가 REST 확정 시간을 벌어 준다는 것이 (B)의 안전 마진인데,
   **누군가 `open_entry_hold_secs` 를 0 으로 롤백하면 그 마진이 사라진다.** cycle265 는 보류 값에
   **의존하지 않도록** 설계해야 한다(= 목표가가 미확정이면 그냥 매수 신호를 내지 않는다 — 이미
   그렇게 동작한다. 명시적으로 테스트로 못 박을 것).
6. **커버리지 손실이 손익을 악화시킬 수 있다.** (ii) 안은 인라인 폴백을 끄므로 REST 가 실패한
   9~14 종목이 09:30 까지 목표가 없이 지나간다. 그중 승자가 있었다면 그 손실은 실현되지 않은
   기회비용으로만 남아 **측정되지 않는다**. `[open_scope_unresolved]` 마커가 그 규모를 세는
   유일한 수단이다.
7. **레짐 의존.** 갭업이 잦은 장(지금)에서는 오염이 "목표가를 낮춰" 과잉 진입을 만들지만,
   갭다운 장에서는 반대로 **목표가를 높여 진입을 막는다**. §9 의 −27.6% 는 지난 4.5개월 레짐의
   숫자이고 레짐이 바뀌면 부호가 달라질 수 있다.
8. **`_drain_pending_next_day_clear` 지연(§5-B 부작용 1)이 실제 청산 슬리피지로 나타날 수 있다.**
   09:00:12 → 09:00:30 은 개장 직후 변동성 구간에서 무시할 수 없는 15~20초다. 보류 종목이 몇 개
   없다는 것이 완화 요인이지만, 이 항목은 **결정 항목으로 올린다**.
9. **`get_targets_status()` 를 고치면 UI/AI 자문 표시가 바뀐다.** `[breakout_open_confirm]` 만
   고치고 `get_targets_status` 는 건드리지 않는 편이 안전하다(그 함수의 보드 가리기 자체는
   대시보드 목적상 의도된 동작일 수 있다). **표시 시정은 emit 쪽에서만** 하기를 권고한다.

---

## 11. 사람이 결정할 항목

| # | 결정 | 선택지 | 자문 권고 |
|---|---|---|---|
| ① | **월요일에 시정을 넣을 것인가** | (a) 관측만 (b) 관측+시정 (c) 아무것도 안 함 | **(a)** — 오늘 이미 2 사이클. 원인 분리 불가 위험 + 미검증 전제 2건 |
| ② | **shadow 마커 볼륨** `[open_scope_observe]` ~290행/일 | (a) 전 구독 종목 (b) VB·LTV `_targets` 한정(~100) (c) 안 함 | **(a)** — 분모가 있어야 오염률을 잰다. 현행 8,300행/일 대비 +3.4% |
| ③ | **`[open_source_compare]` 시각** | (a) 09:05 (b) 09:00:35 (c) 안 함 | **(a)** — KRX 시가는 불변이라 늦게 읽어도 같고, 진입 창과 Rate Limit 을 다투지 않는다 |
| ④ | **cycle265 1차 구현** | (i) `[24]` 배관까지(8영역 2파일) (ii) `[24]` 없이 REST 만(8영역 0) | **(ii) 로 시작 → shadow 결과 보고 (i) 승격** — 시정의 성패를 미검증 필드에 걸지 않는다 |
| ⑤ | **`_drain_pending_next_day_clear` 순서** | (a) 현행 유지(확정 뒤, ~20초 지연 감수) (b) confirm 앞으로 이동 (c) REST 제한 병렬화 | (b) 가 가장 싸고 부작용이 없어 보이나 **스케줄러 순서 변경 = 별도 승인**. 사용자 판단 |
| ⑥ | **VB 진입 −27.6% 를 수용하는가** | (a) 수용 (b) `k_value_krx_main` 1.3 → 하향으로 빈도 보전 | **(a) 먼저, 2주 관측 후 (b) 재논의** — 기준가와 K 를 동시에 바꾸면 어느 쪽 효과인지 못 읽는다 |
| ⑦ | **킬스위치 키 이름·기본값** | `open_price_scope_mode` / 키 부재 = `off` | 권고대로. `PARAM_RANGES` 편입 금지 |
| ⑧ | **`[breakout_open_confirm]` 표시 시정 동봉** | (a) 동봉 (b) 별도 | **(a)** — 이 로그가 조사 하나를 오도했다 |

---

## 12. 후속 검증 권고 (tdd-engineer / tester)

**cycle264 (관측)**
1. `_parse_tick_prices` **소스 세그먼트 sha 핀** — 이 사이클이 그 함수를 건드리지 않았음을 증명.
2. `[open_scope_observe]` emit 이 예외를 던져도 `_handle_tick` 이 **틱을 정상 처리**하는지
   (폭발기 주입 → `_on_tick` 호출 인자 byte 동일 확인). cycle262 `test_c10_4` 패턴.
3. cap 이 **MAIN 창 게이트 뒤**에 있어 프리장 틱이 1회 cap 을 태우지 않는지
   (`_maybe_log_day_high_scope_skip` 회귀와 동형 격자).
4. `[open_source_compare]` 태스크가 **예외·타임아웃에도 스캔 루프를 끊지 않는지**, 그리고
   throttle 이 실제로 5건/초를 넘지 않는지(가짜 시계).
5. `[breakout_open_confirm]` 시정이 **`session_tracker.active` 가 `{PRE_NXT}` 인 상태에서
   `truth_confirmed` 를 정확히 세는지** — 이번에 발견한 그 조건을 그대로 재현하는 테스트.

**cycle265 (시정)**
6. **합성 시리즈 3종** — (가) `oprc_hour=080012` + 프리장 시가 → main 목표가는 **REST 값**으로
   서고 `[open_scope_substituted]` 1행 (나) `oprc_hour=090003` + KRX 시가 → **틱 값 그대로**,
   대체 마커 0행 (다) `oprc_hour` 파싱 실패 → **fail-open(현행 값)** + `[open_scope_unresolved]` 아님.
7. **LTV `pre_nxt` 무접촉 격자** — 08:00~09:00 구간 틱으로 pre_nxt 목표가가 **현행과 byte 동일**.
8. **랜덤엔드 격자** — 09:00:05 REST `stck_oprc="0"` → 미확정 유지 → 09:00:40 재시도에서 확정,
   그 사이 **매수 신호 0**.
9. **kojiro/momentum/donchian/BFB/VCP `check_*_signal` 호출 인자 byte 동일** (AST + spy).
10. **뮤테이션** — 창 경계(`090000` 포함 / `153000` 포함 / `085959` 배제), fail-open 방향
    (예외 시 현행 값 유지), `min`/`max` 방향 뒤집기.
11. **부하 회귀** — 140 종목 REST 확정이 `_rate_limit` 전역 20/s 를 넘지 않고 90초 안에 끝나는지
    (가짜 시계 + 호출 카운터).
