# cycle336 — 무송출 코호트 매수 게이트 제거 (B-2) 자문

작성 2026-09-21 · domain-expert · 읽기 전용(소스 무접촉)
요청자 team-lead · 사용자 결정 「넥스트트레이드 거래가능여부가 VCP거래와 무슨 상관이지? …제거해」

---

## 0. 권고 요약 (먼저)

| 항목 | 판정 |
|---|---|
| **① 한 문장** | **채택.** `risk.py:744~745` 의 `if chan_buy_blocked: continue` 두 줄만 걷고, 코호트 기계 전체는 **관측으로 남긴다.** 단계 개방은 권하지 않는다 — 단계안이 막을 구체적 피해가 존재하지 않고, VCP 는 분모(체결)가 0 이라 단계 관측이 원리상 판독 불가다. |
| **② Q1 가설** | **가설이 맞다. 걱정은 뒤집혀 있다.** 차단 코호트는 하루 종일 `H0STCNT0` 고정이라 `acml_vol` 이 **순수 KRX 누적**이고, 비교 대상 `avg_volume_20` 도 `FID_COND_MRKT_DIV_CODE="J"`(KRX) 일봉이다 — **스코프가 정확히 일치한다.** 스코프가 갈리는 쪽은 채널을 하루 1회 바꾸는 `nxt_true` 인데 **그쪽은 이미 열려 있다.** |
| **③ 건수** | **동시 노출 상한은 1원도 안 변한다.** 5전략 예산 합 2,257,236원(순자산의 45.0%) · 슬롯 합 19 · Σ오픈리스크 상한 127,910원(2.55%) — 전부 게이트와 무관한 값이다. 바뀌는 것은 **슬롯을 채우는 속도와 종목 구성**, 그리고 VCP/BFB 가 「구조적 0건」에서 「가끔 발화」로 옮겨가는 것. |
| **④ 놓친 것(🔴 보고 대상)** | (a) **cycle156 이 이미 `nxt_tradable` 을 유니버스 기준에서 제거**했다(`bull_flag_breakout.py:705` 주석 「주문 시점 분기용으로만 활용」). cycle293 게이트는 그 결정을 **다른 계층에 몰래 복원**한 것이다 — 사용자 말이 코드 이력과 정확히 일치한다. (b) **BFB/VCP 는 한 번에 두 가지가 열린다** — 매수 평가 + `vol_gate_no_data` fail-closed 해제. D+1 귀인을 반드시 분리한다. (c) **LTV × `post_nxt`(16:00~20:00 KRX 애프터마켓) 야간 매수가 유일하게 새로 생기는 *시간대* 노출**이다. 막을 일은 아니지만 결정 카드로 올린다. |
| **⑤ 롤백** | **1커밋 revert.** 새 다이얼을 만들지 않는다 — **이미 두 개가 있다**(`PUT /api/strategies/{id}/params` 즉시 축소, `PUT /api/realtime/tick-channel-mode off` 익일 축). cycle335 의 「끌 수 있게 만든 순간 누군가 끈다」가 여기서도 유효하다. |

---

## 1. 질문 요약

`risk.on_tick` 의 매수 분기 직전에 있는 두 줄

```
src/engine/risk.py:744    if chan_buy_blocked:
src/engine/risk.py:745        continue
```

을 걷어내면, `nxt_tradable=False` ∧ 출처 권위 확인된 종목(= 무송출 코호트)에 대해
momentum · volatility_breakout · long_tail_volatility · bull_flag_breakout · vcp_breakout
**5전략의 WS 틱 매수 평가가 열린다**(donchian·kojiro 는 `risk.py:88`
`_TICK_BUY_EVAL_SKIP_STRATEGIES` 로 이미 제외 — REST 폴 소관).

2026-09-21 09:30 실측 = 구독 158 중 **77(49%)** 이 이 코호트다.

---

## 2. 트레이더 시각 — 「NXT 거래가능여부가 VCP 와 무슨 상관인가」

### 2-A. 사용자 말이 맞다. 그리고 코드 이력이 그것을 뒷받침한다

`nxt_tradable` 은 **넥스트트레이드(ATS)가 그 종목을 지정 거래종목 목록에 넣었는가**일 뿐이다.
기업의 수급·추세·변동성·재무 어느 것도 아니고, **주문을 어느 거래소로 보낼지**를 정하는 배선 정보다.

그리고 이 프로젝트는 이미 그렇게 결정한 적이 있다 —

```
src/engine/strategies/bull_flag_breakout.py:705
# 사이클 156 Q0 — nxt_tradable 강제 필터 제거 (주문 시점 분기용으로만 활용).
```

VB·LTV·donchian·BFB·VCP 다섯 전략의 `_scan_universe` 가 모두 `stock_master.list_by_filter` 를
`nxt_tradable=None`(= 전체)로 부른다(`src/db/stock_master.py:600` — 인자가 `None` 이면 WHERE 절
자체가 안 붙는다). **후보 선정 단계에 NXT 축은 이미 없다.**

cycle293 의 매수 게이트는 그 결정을 뒤집으려 만든 것이 아니다. 채널 수리 사이클이
**승인 없이 매매 행위를 바꾸지 않기 위한 범위 규율 장치**였다. changelog 원문이 그렇게 적혀 있다
(§6 인용). 사용자 승인이 내려온 지금, 그 장치의 존재 이유가 소멸했다.

### 2-B. 「NXT 미지정 = 부실 종목」인가 — 아니다, 그리고 부실은 다른 그물이 잡는다

NXT 미지정은 상장 종목의 과반이다(오늘 구독 기준 49%, cycle293 실측 유니버스 64%).
2/3 가까운 집합은 정의상 **품질 축이 아니라 배선 축**이다. 물론 상관은 있다 —
관리종목·정리매매·저유동·우선주·SPAC·신규상장 초기가 NXT 미지정 쪽에 몰린다.

**그런데 그 상관은 이미 다른 그물이 전담한다.**

| 위험 | 잡는 곳 | 코호트와 무관한가 |
|---|---|---|
| 거래정지 / 정리매매 / 관리종목 / 시장경고 / 단기과열 | `scanner._is_master_blocked_for_entry` (`scanner.py:3561`) — 5전략이 `prepare` 에서 `apply_master_block_filter` 경유(`strategy_base.py:1516`) | **예, 무관** |
| ETF / ETN / 리츠 / SPAC / 신주인수권 | `_universe_filter_securities_only`(`scanner.py:2135`, `prdt_type_cd=="300"`) + 6자리 숫자 가드 + `ETF_KEYWORDS`(`scanner.py:494`) | **예, 무관** |
| 저유동 | 시총·거래대금 하한(`MIN_MARKET_CAP=1,000억`·`MIN_TRADE_AMOUNT=200억`, BFB/VCP 는 전략 파라미터) + `stale_universe_guard`(당일 체결량 <10,000 자동 축출) | **예, 무관** |

즉 게이트를 걷어도 **품질 관문은 한 겹도 줄지 않는다.** 이 변경은 「완화」가 아니라
**「배선 정보로 매매 유니버스를 자르던 것의 원복」**이다.

### 2-C. 남는 상관 하나 — 우선주

`005935`(삼성전자우) 류 우선주는 6자리 숫자를 통과하고 시총·거래대금 하한도 통과하며
`prdt_type_cd` 도 보통주와 갈리지 않는 경우가 있다. NXT 미지정 비율은 높다.
실전에서 우선주는 **호가 두께가 본주의 1/10 수준**이고 갭이 크다 — 1주 랏 위주인 지금의 랏 기하와
겹치면 슬리피지가 명목 대비 크게 튄다.

**그러나 이것도 게이트로 막을 일이 아니다** — 게이트는 우선주가 아닌 코호트 종목 76개까지 같이 막는다.
우선주를 걸러야 한다면 **우선주를 거르는 필터**를 따로 세우는 것이 맞다(별도 사이클).
지금은 **D+1 관측 항목**으로만 둔다(§7 판별표 O-5).

### 2-D. 위험 시나리오 — 가설이 깨지는 곳

1. **코호트가 저가주로 몰린 경우** — 설계 랏 ÷ 중앙 주가(`q`)가 개선되어 오히려 좋다.
   반대로 **코호트가 고가주로 몰리면** VCP `q = 150,482 ÷ 주가` 가 1 미만이 되어 1주 폴백이 늘고,
   명목이 「그 종목 주가 그 자체」로 결정된다(랏 기하 메모의 인과 3단). **이건 게이트 문제가 아니라
   랏 문제이고, 이미 알려진 미해결 항목이다.** 다만 코호트 개방이 그 분산을 키울 수 있다.
2. **16:00~20:00 KRX 애프터마켓** — 코호트는 NXT 에 시장이 없으므로 그 시간대의 유일한 체결 채널이
   KRX 애프터다. LTV 만 `post_nxt` 보드를 갖는다(§4-C). 그 구간의 호가 두께는 정규장과 다르다.
3. **자동 원복(`[tick_channel_auto_revert]` ERROR) + 장중 `nxt_tradable` 뒤집힘 동시 발생** —
   이때만 코호트 종목이 장중에 NXT 채널로 옮겨져 `acml_vol` 스코프가 갈린다.
   **소비처가 없어 무해하다**(§3-D).

---

## 3. Q1 — `ACML_VOL` 스코프 대조: **가설 확정, 걱정은 뒤집혔다**

### 3-A. 차단 코호트는 하루 종일 채널을 바꾸지 않는다 (코드 증명)

채널 결정은 `scanner._resolve_channel`(`scanner.py:653`)의 **시각축 × 속성축** 합성이다.

```
scanner.py:688   if chan == TICK_TR_ID_KRX:            # 시각축이 KRX 창
scanner.py:693       return TICK_TR_ID_KRX, ...        #   → 속성축을 보지 않는다
scanner.py:694   desired, attr_reason, decided = _classify_channel(ticker)
scanner.py:695   if decided and desired == TICK_TR_ID_KRX:
scanner.py:696       return TICK_TR_ID_KRX, ...        # 프리 창 + nxt_false → KRX
scanner.py:697   return TICK_TR_ID_NXT, ...
```

그리고 속성축 `_classify_channel`(`scanner.py:603`)의 마지막 줄

```
scanner.py:650   return TICK_TR_ID_KRX, "no_feed", True
```

은 **`classified` ∧ `no_feed` ∧ `provenance_ok`** 일 때만 도달한다.
그 세 조건은 `_stamp_cohort`(`scanner.py:700~716`)가 코호트를 심는 조건과 **완전히 같다.**

⇒ **차단 코호트 = 프리 창에서도 KRX, KRX 창에서도 KRX.**
전환 창은 하루 **`pre_to_krx` 1개뿐**이므로(`tick_channel_clock.py` 모듈 docstring) 이 코호트는
**하루 중 전환 대상이 아니다.** 즉 `tick_volume._observed[ticker]` 는 **08:00 부터 20:00 까지
단일 채널(`H0STCNT0`) 누적**이다.

### 3-B. 비교 대상도 KRX 다

VCP `_evaluate_vol_gate`(`vcp_breakout.py:1171~`)는

```
vol_threshold = int(info["avg_volume_20"] * params["breakout_volume_mult"])
observed      = tick_volume.get_observed_acml_vol(ticker)
```

`avg_volume_20` 의 원천은 `stock_master_daily`(KIS `FHKST03010100`)이고, 그 호출의 시장구분은

```
src/api/condition.py:558   "FID_COND_MRKT_DIV_CODE": "J",     # = KRX
```

**KRX 일봉 ↔ KRX 실측 누적.** 스코프가 정확히 일치한다.

### 3-C. 🔴 위험한 쪽은 이미 열려 있다

| 코호트 | 채널 궤적 | `acml_vol` 스코프 | 매수 평가 |
|---|---|---|---|
| **`nxt_false` (차단 대상)** | 08:00~20:00 **KRX 고정** | 순수 KRX 누적 = 일봉과 **정합** | **지금 닫혀 있다** |
| `nxt_true` | 08:00 NXT → ~09:05 **전환** → KRX | 전환 전 = NXT 누적 / 전환 후 첫 프레임부터 KRX | **지금 열려 있다** |

`nxt_true` 는 전환 직후 첫 KRX 프레임이 도착할 때까지 **NXT 누적값을 들고 있다**
(`tick_volume.record_acml_vol` last-write-wins). 그 값은 KRX 누적보다 **작다**
(실측 `000660`: `H0STCNT0` 3,773,544 vs `H0NXCNT0` 1,981,520) — 즉 게이트가 **보수 방향으로
틀린다**(통과가 어려워진다). 실효 손해는 없지만, **스코프 오염은 이미 열려 있는 쪽에 있다.**

게다가 VCP·BFB 는 `DEFAULT_TRADABLE_BOARDS=("main",)`(`vcp_breakout.py:132`,
`bull_flag_breakout.py:96`)이라 09:00 이전에는 애초에 매수하지 않는다 —
`nxt_true` 의 오염 구간과도 대부분 겹치지 않는다.

**결론 = 이 걱정은 제거의 장애물이 아니다. 오히려 코호트 개방은 「스코프가 더 깨끗한 절반」을 여는 일이다.**

### 3-D. 가설이 깨지는 단 하나의 경로 (그리고 무해한 이유)

`tick_channel_clock.set_day_revert()` 가 발동해 그날 나머지가 「프리 창 규칙」이 되고
**동시에** 16:1x `basics_refresh` 가 어떤 코호트 종목의 `nxt_tradable` 을 True 로 뒤집으면,
그 종목은 `_classify_channel` 이 `nxt_feed` 를 내어 **NXT 채널로 전환**되고 `acml_vol` 이
NXT 누적으로 덮인다.

**무해한 이유 셋** — ① `[tick_channel_auto_revert]` 는 **ERROR** 레벨이라 21:30 리포트
`top_patterns` 에 뜬다(`test_cycle294_ast_stage3.py::test_a23b`) ② 코호트 스탬프는
**하루 단방향 닫힘 래치**라 그 종목은 그날 내내 코호트로 남는다 ③ 그 일이 가능한 시각은
16:1x 이후인데 **`acml_vol` 소비자 둘(VCP·BFB)은 `main` 보드 전용**이라 그 시각에 매수하지 않는다.
LTV 는 `post_nxt` 에서 매수하지만 **`tick_volume` 을 읽지 않는다**(`grep get_observed_acml_vol` 소비처
= VCP·BFB·`llm_buy_gate`·`stale_universe_guard`·`routes/realtime` 뿐).

---

## 4. Q2 — 제거의 진짜 범위: 5전략 동시 개방

### 4-A. 상한은 한 푼도 안 변한다 (이것이 핵심 답이다)

전제 — 순자산 **5,016,078원**(team-lead 실측) · `cash_usage_ratio = 1.0`(가정, §9 확인 필요) ·
Σweight = 1.0 · 비중은 랏 기하 메모 실측 + VCP 0.15 는 **잔차 추론**(§9 확인 필요) ·
`max_positions`/`position_ratio`/`stop_loss_rate` 는 **운영 DB 실측표** 값.

| 전략 | weight | 전략 예산 | `position_ratio` | 설계 랏 | 슬롯 | 손절 | 오픈리스크 상한 |
|---|---|---|---|---|---|---|---|
| momentum | 0.05 | 250,804 | 0.25 | 62,701 | 4 | −5.0% | 12,540 |
| volatility_breakout | 0.05 | 250,804 | **0.35** | 87,781 | **2** | **−5.0%** | 12,540 |
| long_tail_volatility | 0.05 | 250,804 | **0.20** | 50,161 | **4** | **−5.0%**(intraday) | 12,540 |
| bull_flag_breakout | 0.15 | 752,412 | 0.25 | 188,103 | 4 | −5.0% | 37,621 |
| vcp_breakout | 0.15 | 752,412 | 0.20 | 150,482 | 5 | −7.0% | 52,669 |
| **합** | 0.45 | **2,257,236** | — | — | **19** | — | **127,910** |

- **명목 상한** = 2,257,236원 = 순자산의 **45.0%**. `StrategyBase._apply_budget_limit` 관문이
  7전략 `calc_buy_quantity` 의 모든 return 을 통과시켜 전략별 `Σ매수금액 ≤ total_investment` 를
  강제한다(루트 CLAUDE.md 「매수 수량은 전략 잔여 자금 기준」).
- **Σ오픈리스크 상한** = 127,910원 = 순자산의 **2.55%**.
- **이 두 수는 `chan_buy_blocked` 와 아무 관계가 없다.** 게이트는 «어느 종목을 평가하는가»를
  바꿀 뿐 «얼마를 살 수 있는가»를 바꾸지 않는다.

⇒ **Q2 의 「매수 건수가 몇 배가 되는가」에 대한 답: 동시 보유 기준으로는 0배 증가다.**

### 4-B. 그럼 실제로 무엇이 늘어나는가 — 세 가지

1. **후보 밀도** — VCP 오늘 후보 5 중 2(40%)가 코호트. 구독 기준 77/158(49%).
   전략마다 후보 산출 방식이 달라 비율도 다르다(§9 의 사전 SQL 로 확정 권고).
2. **슬롯 회전** — momentum·VB·LTV 는 당일/익일 청산 계열이라 슬롯이 회수된다.
   후보가 늘면 **하루 매수 건수**(동시 보유가 아니라 누적 체결 수)가 늘 수 있다.
   상한은 `슬롯 × 회전수` 이고 `is_sold_today` 가 같은 종목 재매수를 막는다.
   **VB 는 `max_positions=2` + 15:20 일괄청산이라 하루 2건이 사실상 상한이다.**
3. **🔴 VCP·BFB 의 이중 해제** — 코호트는 통합 채널 시절 프레임이 0건이었으므로
   `tick_volume.get_observed_acml_vol` 이 **항상 `None`** 이었다. VCP `_evaluate_vol_gate` 는
   `observed is None` 을 **fail-closed**(`vcp_breakout.py:1198~1208`)로 처리한다.
   게이트를 걷으면 매수 평가가 열리는 **동시에** 거래량 게이트가 `no_data` 에서 **실제 평가**로 바뀐다.
   → D+1 귀인을 반드시 분리한다(§7 O-2).

   ⚠️ **운영 DB 값이 코드와 다르다** — BFB `breakout_volume_mult` = **1.0**(코드 2.0),
   VCP = **1.2**(코드 1.5). BFB 의 임계는 「당일 누적 ≥ 20일 평균」이라 장중 중반이면
   활발한 종목에서 거의 항상 참이다. **BFB 에게 이 변경은 사실상 순수 후보 확대**이고,
   VCP 는 그보다 조금 더 조인 상태다.

### 4-C. 🔴 유일하게 새로 생기는 *시간대* 노출 — LTV × `post_nxt`

`session.py:66` 기준 `POST_NXT = 15:40~20:00` 이고, LTV 만 그 보드를 갖는다
(`session.py:80`, `long_tail_volatility.py:96`). cycle295 의 휴식 컷이 15:40~16:00 주문을 막으므로
실효 구간은 **16:00~20:00 KRX 애프터마켓**이다.

- 코호트 종목은 NXT 에 시장이 없으므로 그 시간대 체결은 **KRX 애프터 단독**이다.
- 통합 채널 시절 그 구간 프레임이 0건이었고, cycle294 이후 프레임은 오지만 게이트가 매수를 막았다.
  ⇒ **게이트를 걷으면 이 조합이 처음으로 생긴다.**
- 주문 라우팅은 `nxt_tradable=False` → `[nxt_downgrade]` → KRX 강제(루트 CLAUDE.md) 로 이미 정합.

**판단 = 막지 않는다.** LTV 의 `post_nxt` 는 사이클 38 에서 사용자가 명시한 설계 의도
(「연속 상한가 익일 청산 + 야간 매수」)이고, 품질 관문(§2-B)은 그 시간대에도 동일하게 걸린다.
다만 **첫 주 동안 16:00~20:00 LTV 매수만 따로 집계**한다(§7 O-4) — 애프터마켓 거부 msg1 원문이
아직 미수집 상태라는 사실(메모 `reference_kis_market_change_20260914`)이 여기서 처음으로
실전 노출된다.

### 4-D. 계좌 SOFT Σ상한은 막지 않는다 (사실 확인)

`account_risk_guard.evaluate_soft_gate` 는 `block_pct=None` 이면 **어떤 값도 block 이 되지 않는다**
(`account_risk_guard.py:35`). 운영 DB `account_risk_block_pct` 가 미설정(다크런치)이므로
`warn` 까지만 도달한다(`account_risk_watcher.py:16~17`, 권고값 6.0).

**그런데 §4-A 의 Σ오픈리스크 상한이 2.55% 라 권고 6.0% 에 닿지 않는다.**
즉 이 가드는 이번 변경에 대해 **활성이든 아니든 결과가 같다.** 별건으로 다룬다.

---

## 5. Q3 — 점진 개방 vs 한 번에: **한 번에 걷는다**

단계안을 권하려면 「한 번에 걷는 것의 구체적 피해」를 대야 한다. **댈 것이 없다.**

| 단계안 | 그것이 막는 것 | 판정 |
|---|---|---|
| **전략 축 (VCP 만 먼저)** | 나머지 4전략의 종목 구성 변화 | **불가.** ① `_tick_buy_eval_blocked_by_channel` 은 ticker 하나만 받는다(`risk.py:91`) — 전략 축을 넣으려면 **새 집합 상수 + 새 다이얼**을 만들어야 하고, 그것이 cycle335 가 거부한 바로 그 물건이다. ② **VCP 는 `trade_history` 생애 0행**이다. VCP 만 열고 D+1 에 0건이 나오면 「열렸는데 신호가 없다」와 「안 열렸다」를 **구분할 수 없다** — 분모가 없는 표본은 관측이 아니다. |
| **관측 기간 (N일 그림자 운영)** | 없음 | **무의미.** 우리가 보려는 것은 「코호트에서 쓸 만한 체결이 나오는가」인데, 체결이 없으면 볼 데이터가 없다. 기다리면 0 이 0 으로 남는다. |
| **종목 수 축 (77 중 20 만)** | 슬롯이 나쁜 종목으로 차는 것 | **막지 못한다.** 부분집합을 열어도 그 부분집합 안에서 같은 일이 일어난다. 그리고 부분집합 선정 기준이 **또 하나의 임의 필터**다. |

**그리고 상한이 안 변한다는 사실(§4-A)이 단계안의 존재 이유를 없앤다.**
단계 개방은 「최악의 경우 손실이 너무 클 때」 쓰는 도구인데, 최악의 경우 손실은
**게이트가 있든 없든 127,910원(2.55%)** 으로 같다.

⚠️ **킬스위치 신설 금지에 동의한다.** 그리고 덧붙일 사실 —
**롤백 다이얼은 이미 두 개 있다**(§8). 새로 만들 필요가 없다.

---

## 6. Q4 — 걷은 뒤 남길 것

### 6-A. 코호트 기계는 **전부 남긴다** (관측 전용 전환)

| 심볼 | 위치 | 처분 | 이유 |
|---|---|---|---|
| `_channel_cohort` | `scanner.py:537` | **유지** | 체결의 코호트 귀인이 D+1 판별표의 축이다(§7). 지우면 「이 체결이 새로 열린 절반에서 나왔는가」를 영영 못 센다 |
| `_stamp_cohort` | `scanner.py:700` | **유지** | 위 dict 의 유일한 생산자 |
| `restamp_cohorts` | `scanner.py:746` | **유지** | 스탬프 재시도(5분·120초 두 배선). 없으면 `unstamped` 가 커져 귀인이 무너진다 |
| `tick_buy_cohort_blocked` | `scanner.py:775` | **유지 · 이름 유지** | AST 가드 4건이 이 이름을 단언한다(§6-C). 개명은 가드 4건 동시 수정 = 불필요한 대가 |
| `_tick_buy_eval_blocked_by_channel` | `risk.py:91` | **유지 · docstring 갱신** | AST 가드가 **함수 존재**를 단언한다. 지우면 붉어진다 |
| `risk.py:620` `chan_buy_blocked = …` | `risk.py:620` | **유지** | `_note_pre_window_krx_frame` 의 게이팅 조건(§6-B) |
| `risk.py:744~745` `if chan_buy_blocked: continue` | — | **🔴 삭제 (이것만)** | 변경의 전부 |
| `[tick_buy_gate]` emit | `scanner.py:1158` | **유지** | 스탬프 배선이 살아 있는지 재는 유일한 계측기. 관측 전용이 된 뒤에는 **귀인 분모**가 된다 |

🔴 **docstring 을 반드시 고친다.** `risk.py:130~131` 의

> B-2(매수 개방)는 이 함수 호출 1줄을 걷는 것이고 **별도 승인 + `domain-consult` + `ACML_VOL` 스코프 대조 1일**(N-2)이 선행 조건이다.

이 문장이 남아 있으면 다음 사람이 「아직 안 걷었구나」로 읽고 `continue` 를 **되살린다.**
「cycle336 에서 세 조건을 모두 충족해 걷었다. 이 술어는 **관측 전용**이다. `continue` 를 되살리려면
사용자 결정을 먼저 뒤집어라」로 교체한다.

### 6-B. `_note_pre_window_krx_frame` — 살아남는다, 그리고 아직 가치가 있다

`risk.py:621~624` 는 게이트 **분기 앞**에 있으므로 `:744~745` 만 걷으면 **byte 동일하게 산다.**

```
risk.py:620   chan_buy_blocked = _tick_buy_eval_blocked_by_channel(ticker)
risk.py:621   if chan_buy_blocked:
risk.py:624       _note_pre_window_krx_frame(ticker)      ← 살아 있다
```

**가치 판정 = 아직 답이 안 나왔다면 유효하다.**
cycle294 §2-D 의 질문은 「`H0STCNT0` 이 KRX 시가 단일가 구간(08:00~09:05)에 프레임을 보내는가」
이고, 답은 `[tick_channel_pre_krx_frame]` 행 수다. **기대값 0행.**

🔴 **team-lead 에게 요청** — 배포 전에 한 줄 확인:
```
09-15 ~ 09-19 (5영업일) system_logs 에서 [tick_channel_pre_krx_frame] 행 수
```
- **0행이면** — 추론이 실측으로 확정됐다. 관측의 목적을 다했으므로 **별도 사이클**에서 정리 후보로 올린다(이번 사이클에 끼워 넣지 않는다 — 한 커밋에 두 가지를 섞으면 revert 가 무뎌진다).
- **1행 이상이면** — cycle294 §0 의 가정이 틀렸다. 그건 **이 자문과 별개의 CRITICAL** 이고, 그 자체로 결정 카드가 된다.

### 6-C. AST 가드 — 게이트의 **존재**를 단언하는 것 (전수)

`grep` 결과 이 게이트를 단언하는 가드는 **네 건**이고, **넷 다 「술어 함수가 존재하고 코호트를 읽는가」만** 본다.
**`on_tick` 의 `continue` 를 단언하는 AST 가드는 없다.**

| 가드 | 파일:줄 | 걷은 뒤 |
|---|---|---|
| `test_a18_buy_gate_reads_the_subscription_fact_not_the_resolver` | `tests/unit/ast/test_cycle293_ast_channel_resolver.py:1073` | **초록 유지** (함수·`tick_buy_cohort_blocked` 존재만 단언) |
| `test_a11_buy_gate_reads_the_cohort_not_the_channel` | `tests/unit/ast/test_cycle294_ast_stage3.py:675` | **초록 유지** |
| `test_a15_cycle293_a18_is_superseded_not_deleted` | `tests/unit/ast/test_cycle294_ast_stage3.py:~705` | **초록 유지** |
| `test_a24_new_scanner_helpers_have_no_io` | `tests/unit/ast/test_cycle294_ast_stage3.py:1160` | **초록 유지** |
| `test_a23_new_markers_exist_in_production[[tick_buy_gate]]` | `tests/unit/ast/test_cycle294_ast_stage3.py:1125` | **초록 유지** (마커 보존) |

🔴 **붉어지는 것은 AST 가 아니라 행위 테스트다** — 이쪽이 진짜 작업량이다:

| 테스트 | 파일:줄 | 현재 단언 | 필요한 처분 |
|---|---|---|---|
| `test_d2_no_feed_cohort_is_still_blocked_but_exit_is_not` | `tests/unit/engine/test_cycle294_stage3.py:669` | 코호트 `buy_calls == []` | **반대 단언으로 교체** — `buy_calls == [NO_FEED]` + `exit_calls == [NO_FEED]`(청산은 무접촉 유지) |
| `test_d3_all_dedicated_does_not_kill_all_buys` | `test_cycle294_stage3.py:703` | `set(buy_calls) == set(nxt_true)` (60) | **`== set(all_tickers)`(100)** 로 교체. 🔴 이 한 케이스가 「게이트가 다시 생겼다」를 잡는 **유일한 값 검사**다 |
| `test_d6_kill_switch_off_does_not_open_the_cohort` | `test_cycle294_stage3.py:776` | `off` 여도 코호트 매수 0 | **의미 재정의** — 이제 코호트는 열려 있으므로 이 테스트의 원래 계약(「킬스위치가 매수를 *여는* 경로가 되면 안 된다」)은 **방향이 뒤집힌다.** 남길 계약 = 「`off` 는 매수 판정을 **바꾸지 않는다**」 = 모드 무관 동일 결과 |
| `test_g9_ticker_axis_gate_blocks_buy_eval_for_no_feed` | `tests/unit/engine/test_cycle293_channel_resolver.py:1096` | 5전략 전부 매수 0 | **반대 단언** (5전략 parametrize 유지 — 전략별로 열렸음을 값으로 확인) |
| `test_g9b_opening_a_channel_never_opens_the_buy_axis` | `test_cycle293_channel_resolver.py:1194` | 채널 개방 ≠ 매수 개방 | **폐기 + 사유 docstring** — 이 계약이 바로 사용자가 뒤집은 것이다 |
| `test_g9c_gate_survives_resolver_divergence` | `test_cycle293_channel_resolver.py:1251` | 리졸버 발산 시에도 닫힘 | **폐기 또는 「발산해도 매수 판정 동일」로 재조준** |
| `test_g9_exit_axis_still_evaluated_for_no_feed` / `test_g9_nxt_true_ticker_buy_eval_unchanged` / `test_g9d` / `test_g9e` / `test_d1` / `test_d4` / `test_d5` / `test_d7` / `test_d8` | — | 청산 평가·순수성·래치·예산 무소모 | **전부 무접촉 초록 유지** — 걷는 것은 `continue` 하나뿐이라 이 계약들은 변하지 않는다 |

⚠️ **`test_d3` 의 돌연변이 가치를 잃지 말 것.** 원래 docstring 이 「0개면 채널 축, 100개면 게이트 소멸」
이라고 적어 뒀다. 100 으로 뒤집은 뒤에도 **「60 이 나오면 게이트가 부활한 것」**을 실패 메시지에
명시해야 이 그물이 계속 산다.

---

## 7. Q5 — 되돌리기와 D+1 판별표

### 7-A. 롤백 = **1커밋 revert.** 새 다이얼 금지

두 줄짜리 변경이다. revert 가 가장 정확하고 가장 빠르다.
그리고 **다이얼은 이미 두 개 있다** —

| 수단 | 반영 시점 | 효과 | 주의 |
|---|---|---|---|
| `PUT /api/strategies/{id}/params` 로 `position_ratio`↓ / `max_positions`↓ | **즉시**(in-memory `config.params` 덮어씀) | 그 전략의 신규 유입만 축소. `enabled` 무접촉 · 하한선 검증 없음 | 보유 중 장중 실효 수단은 이것뿐(cycle232 D6) |
| `PUT /api/realtime/tick-channel-mode` → `off` | **다음 `_boot` 부터** | 통합 채널 복귀 → 코호트 프레임 0 → 매수 0 | 🔴 **즉시 되돌리지 않는다** — 이미 전용 채널에 올라간 구독은 남는다(cycle294 §9-B). 익일 축 다이얼이다 |
| 🔴 `weight=0` / `enabled=false` | — | **금지** | `registry.update_weights` 가 `enabled = weight > 0` 을 자동 토글 = **보유분 손절 정지**(루트 CLAUDE.md 최우선 금기) |

### 7-B. D+1 판별표 — 무엇을 보면 정상이고 무엇을 보면 사고인가

배포 창 = **오늘 21:35 이후**. 첫 시험대 = **09-22(월) 09:00**.

| # | 관측 | 정상 | 🟠 경보 | 🔴 사고 | 어디서 |
|---|---|---|---|---|---|
| **O-1** | 5전략 **하루 매수 건수** (코호트/비코호트 분리) | 합계 ≤ 19 · 코호트분 ≥ 1 | 합계 20~30 | **합계 > 30** 또는 한 전략이 슬롯을 하루 **3회 이상 완전 회전** | `trade_history` ⋈ `stock_master.nxt_tradable` |
| **O-2** | 🔴 **귀인 분리** — VCP/BFB 체결이 「후보가 새로 생겨서」인가 「거래량 게이트가 풀려서」인가 | 두 원인이 로그로 갈린다 | — | 구분 불가 | `[vcp_vol_gate_no_data]` 건수가 **전주 대비 급감**하면 (2)번 기여. 급감 없이 체결만 늘면 (1)번 |
| **O-3** | **동시 보유 명목** 5전략 합 | ≤ 2,257,236원 | 초과 | 초과가 **반복** = 예산 관문 무력화 | `positions` ⋈ 전략 |
| **O-4** | 🔴 **16:00~20:00 LTV 매수** | 0~1건 | 2건 이상 | KIS 거부 신규 msg1 출현 | `trade_history` 시각 + `[kis_rejection]` |
| **O-5** | **체결 종목의 성격** — 우선주(코드 말미 5/7/9)·초고가주 비중 | 우선주 0 | 우선주 1~2 | 우선주가 **한 전략 체결의 과반** | `trade_history` 종목코드 |
| **O-6** | **랏 기하** — 1주 폴백 비율·명목 분산 | 전주 대비 ±10%p | 1주 비율 **+20%p** | `[ratio_notional_blocked] capped_qty=0` 급증 = 코호트가 고가주 편중 | `[oversized_fallback]` · `[ratio_notional_blocked]` |
| **O-7** | **예산 소진 속도** | 오후까지 잔여 있음 | 오전 중 `low_funds` | `[risk_silent_skip] reason=price_gt_total_investment` **급증** = 코호트 주가가 전략 예산을 넘는다 | `[low_funds]` · `[risk_silent_skip]` |
| **O-8** | **게이트 기계 생존** (귀인 분모) | 정규장 창 행에서 `unstamped` 작음 · `stamped_no_feed` ≈ 77 | `unstamped` 증가 | `stamped_no_feed=0` = 스탬프 배선 사망 → 귀인 불가 | `[tick_buy_gate]`(**정규장 창 행**으로 판단 — 프리 창 행의 `unstamped` 가 큰 것은 정상) |
| **O-9** | **손절 커버리지** (변하면 안 되는 것) | `[no_feed_held]` 0 · `_selling` 좀비 0 | — | 코호트 보유분의 손절 미발화 | `[no_feed_held]` · `[priority_drop]` |
| **O-10** | **주문 라우팅** | `[nxt_downgrade]` **증가는 정상**(코호트 주문이 KRX 로 간다) | — | `[kis_rejection]` 중 NXT 관련 거부 출현 = 다운그레이드 누락 | `[nxt_downgrade]` · `[kis_rejection]` |

**🔴 매수 폭증 조기 감지 = O-1 + O-7.** 가장 빠른 신호는 **O-7**이다 —
예산이 오전에 마르면 `[low_funds]`/`block_buy` 가 먼저 뜨고, 그때가 슬롯 회전이 과열된 시점이다.
**임계 = 09:00~10:00 한 시간 안에 어느 전략이든 `max_positions` 를 채우면 즉시 확인.**

### 7-C. 배포 전 한 번 돌릴 읽기 전용 SQL (§9 와 함께)

Q2 를 숫자로 확정하려면 배포 **전**에 한 번이면 된다:

```sql
-- 전략별 후보의 코호트 비중 (09-21 09:30 funnel 스냅샷 기준)
SELECT f.strategy_id,
       count(*) FILTER (WHERE sm.nxt_tradable IS FALSE) AS cohort_n,
       count(*) AS total_n
FROM strategy_funnel_snapshots f,
     LATERAL jsonb_array_elements_text(f.survived_tickers) AS t(ticker)
JOIN stock_master sm ON sm.ticker = t.ticker
WHERE f.target_date = CURRENT_DATE AND f.step_no = 99
GROUP BY f.strategy_id ORDER BY 1;

-- 코호트의 가격 분포 (랏 기하 = O-6 의 사전 예측)
SELECT sm.nxt_tradable,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY d.stck_clpr) AS median_price,
       count(*) 
FROM stock_master sm JOIN stock_master_daily d ON d.ticker = sm.ticker
WHERE d.bas_dd = (SELECT max(bas_dd) FROM stock_master_daily)
  AND sm.hts_avls_eok >= 1000
GROUP BY 1;
```

두 번째 쿼리가 **O-6 의 답을 미리 준다** — 코호트 중앙 주가가 비코호트보다 높으면
1주 폴백이 늘 것이 예측되고, 낮으면 `q` 가 개선된다.

---

## 8. Q6 — cycle293/294 는 왜 이 게이트를 세웠나, 아직 유효한가

### 8-A. 원문 (docs/HARNESS_CHANGELOG.md, cycle293 행)

> 🔴 **매수 축은 열지 않았다(B-1)** — 채널을 열면 시총 1,000억↑ 유니버스의 **64%** 가
> momentum … VCP 5전략 매수 평가에 새로 노출된다(30일 실측 그 5전략의 `nxt_false` 매수 **0건**
> / donchian 8건 · kojiro 3건은 전략 축 skip + REST 폴 소관). BFB/VCP 는 `acml_vol` 실측이
> 들어오면서 `vol_gate_no_data` fail-closed 까지 함께 풀린다(실측: `observed=None` → NONE /
> `5,000,000` → BUY). **B-2(매수 개방)는 별도 승인 + `domain-consult` + U-3(`H0STCNT0` `ACML_VOL`
> 스코프) 대조 1일이 선행이다.**

### 8-B. 근거 세 갈래의 현재 유효성 판정

| 근거 | 내용 | 판정 |
|---|---|---|
| **(1) 범위 규율** | 「채널 **수리** 사이클이 **매매 행위 변경**을 몰래 싣지 않는다」 | ✅ **소멸.** 사용자 승인이 이것을 직접 해소했다. 이것이 게이트의 **본체 이유**였고, 시장 판단이 아니었다 |
| **(2) `ACML_VOL` 스코프 미확인** | 「KRX 전용 채널 누적이 일봉 평균과 비교 가능한가 1일 대조」 | ✅ **해소.** §3 에서 코드로 확정 — 코호트는 하루 종일 KRX 고정, 일봉도 `"J"`(KRX). **정합.** 게다가 걱정의 방향이 뒤집혀 있었다 |
| **(3) 🔴 BFB/VCP 이중 해제** | 「매수 평가 + `vol_gate_no_data` fail-closed 가 **함께** 풀린다」 | 🟠 **사실로서 여전히 유효.** 다만 이것은 **막을 이유가 아니라 귀인 분리 의무**다. 게이트를 걷는 것의 부작용이 아니라 **의도한 효과의 일부**다(그 fail-closed 는 원래 프레임이 안 와서 생긴 인공물이다) |

### 8-C. 🔴 사용자에게 보고할 것 — 근거 (3) 하나

(1)·(2) 는 죽었다. **(3) 은 살아 있다** — 그러나 「하지 말라」가 아니라
**「이 변경은 한 번에 두 가지를 바꾼다」**는 사실 고지다.

> 이 변경으로 BFB·VCP 는 ① 새 종목을 평가하게 되고 ② 그 종목들의 거래량 게이트가
> 「데이터 없음 → 매수 안 함」에서 「실제 비교」로 바뀝니다. 두 변화가 같은 커밋에 있으므로,
> 월요일에 VCP 가 처음 체결되어도 **어느 쪽 덕인지는 로그를 봐야 갈립니다**(§7 O-2).
> 쪼갤 수는 없습니다 — ②는 ①이 없으면 도달조차 못 하는 코드 경로입니다.

### 8-D. 덧붙일 사실 하나 — 게이트는 이미 있던 결정을 뒤집고 있었다

§2-A 의 `bull_flag_breakout.py:705` — **cycle156 이 `nxt_tradable` 강제 필터를 명시적으로 제거**했고
그 결정이 5전략 전부의 `_scan_universe` 에 살아 있다. cycle293 게이트는 같은 기준을
**다른 계층(틱 매수 평가)에 되살린 것**이다. 의도한 것은 아니지만 결과적으로 **두 계층이 반대 방향**을
가리키고 있었다. 사용자 결정은 그 모순을 없애는 방향이다.

---

## 9. 자문의 한계 — 확인이 필요한 세 값

이 메모의 숫자 중 **세 개는 추정**이다. 배포 전에 확정할 것을 권한다(DB 조회 1회).

| 값 | 이 메모가 쓴 값 | 근거 | 확인 방법 |
|---|---|---|---|
| VCP `weight` | **0.15** | 나머지 6전략 합 0.85 의 잔차 | `SELECT strategy_id, weight FROM strategy_config;` |
| `cash_usage_ratio` | **1.0** | 기본값 + `auto_regime_adjust` 보류(D4) | `SELECT value FROM system_config WHERE key='cash_usage_ratio';` |
| 전략별 후보의 코호트 비중 | VCP 40%(실측 5중2) · 나머지 미측정 | team-lead 실측 1건 | §7-C 첫 SQL |

앞의 둘이 틀리면 §4-A 표의 **예산·랏·오픈리스크가 전부 비례해서 틀린다.**
다만 **결론(상한 불변)은 이 세 값과 무관하다** — 게이트는 어느 값에도 개입하지 않기 때문이다.

또한 **도메인 자문은 「값의 상한」까지만 말할 수 있다.** 코호트 종목의 실제 수익성
(승률·손익비)은 이 시스템에 **체결 표본이 없다**(5전략 `nxt_false` 30일 매수 0건).
월요일부터 그 표본이 처음 생긴다 — **첫 2주는 결과가 아니라 관측 기간으로 본다.**

---

## 10. 후속 검증 권고 (tdd-engineer / tester)

### tdd-engineer — 🔴 「값을 검사하는」 회귀 계약

이 저장소는 최근 「존재만 검사하는 그물」로 세 번 실패했다. 아래는 **전부 값 단언**이다.

| # | 계약 (한 줄) | 형태 |
|---|---|---|
| **R1** | 100종목(코호트 40 + `nxt_true` 60) 전원 전용 채널에서 `check_buy_signal` 호출 집합이 **정확히 100종목** | `assert set(buy_calls) == set(all_tickers)` — 60 이면 게이트 부활, 0 이면 채널 축 회귀 (`test_d3` 반전) |
| **R2** | 코호트 보유 종목의 `check_exit_signal` 이 **정확히 1회** 불리고 `execute_sell` 이 **정확히 1회** await 된다 | 청산 무접촉 증명 (`test_d2` 의 살아남는 절반) |
| **R3** | 킬스위치 `off`/`observe`/`enforce` **세 모드 전부**에서 코호트의 `buy_calls` 가 **동일 집합** | 모드가 매수 판정을 바꾸지 않는다 (`test_d6` 재정의) |
| **R4** | 코호트 종목에 `acml_vol=0` 틱 1건 → `get_observed_acml_vol` 이 **`0`**(`None` 아님) → VCP `vol_threshold>0` 이면 `Signal.NONE`, `vol_threshold==0` 이면 통과 | sentinel 계약 보존 (`tick_volume.py` 모듈 docstring) |
| **R5** | 코호트 종목 1개를 08:00→16:30 전 구간 `_applied` 로 추적해 **KRX 단일 채널** 유지 | §3-A 의 스코프 정합 전제를 값으로 봉인 — 실패 메시지에 「acml_vol 스코프가 갈린다」 명시 |
| **R6** | `_stamp_cohort` 가 심은 종목 수 = `[tick_buy_gate]` 의 `stamped_no_feed` 값 | 귀인 분모의 정합. 관측이 죽으면 D+1 판독 불가 |
| **R7** | `risk.py` 소스에 `"B-2(매수 개방)"` 문자열이 **0건**(또는 「cycle336 에서 걷었다」 동반) | docstring 이 낡아 다음 사람이 `continue` 를 되살리는 것을 막는다 |
| **R8** | 5전략 각각에 대해 코호트 종목 1개 틱 → `check_buy_signal` **호출 1회** (parametrize) | 「어느 전략은 여전히 닫혀 있다」를 값으로 배제 |

⚠️ **돌연변이 확인 의무** — R1 을 넣은 뒤 `if chan_buy_blocked: continue` 를 **되살려**
R1 만 붉어지는지 확인한다. 다른 것이 같이 붉어지면 그물이 겹친 것이고,
**아무것도 안 붉어지면 R1 이 공허하다.**

### tester — 통합/운영

1. **배포 전** — §7-C 두 SQL 실행, `[tick_channel_pre_krx_frame]` 5영업일 행 수(§6-B),
   §9 의 세 값 확정.
2. **배포 창** — 21:35 이후. **20:00~21:35 금지**(자문·metrics·일봉 적재·정산).
   이 변경은 `src/` 접촉이므로 **full 모드 = backend 재시작**이다.
3. **09-22 09:00~10:00 집중 관측** — O-7(예산 소진) → O-1(매수 건수) 순.
4. **09-22 16:00~20:00** — O-4(LTV 야간) 단독 확인. 이 구간이 첫 미지 영역이다.
5. **D+1 21:30 리포트** — `[tick_buy_gate]` 정규장 창 행 · `[vcp_vol_gate_no_data]` 전주 대비 ·
   `[ratio_notional_blocked]` · `[nxt_downgrade]` 증분.

---

## 11. 금기 (이 변경에서 하지 말 것)

1. 🔴 **`_stamp_cohort`·`tick_buy_cohort_blocked`·`_channel_cohort`·`restamp_cohorts`·`[tick_buy_gate]` 를 지우지 않는다** — 귀인 분모가 사라지고 되돌릴 수 없다. AST 가드 4건도 붉어진다.
2. 🔴 **새 킬스위치·새 파라미터 키를 만들지 않는다** — 다이얼 둘이 이미 있고(§7-A), cycle335 가 같은 이유로 거부했다.
3. 🔴 **`risk.py:621~624`(`_note_pre_window_krx_frame`)를 같이 건드리지 않는다** — 그 관측의 정리는 별도 사이클. 한 커밋에 섞으면 revert 가 무뎌진다.
4. 🔴 **`weight=0` / `enabled=false` 로 축소하지 않는다** — 보유분 손절 정지.
5. 🔴 **`tick_volume` 을 건드리지 않는다** — `record_acml_vol` 의 last-write-wins 와 sentinel(`None` ≠ `0`) 계약은 이 변경의 **전제**다. 스코프 정합은 채널이 안 바뀌어서 성립하는 것이지 `tick_volume` 을 고쳐서가 아니다.
6. 🔴 **`fields[9]`(체결수량) 무접촉** — 무관한 영역이지만 같은 파일 계열이라 명시한다.
7. 🔴 **VCP/BFB 의 `breakout_volume_mult` 를 이번에 같이 조정하지 않는다** — 운영 DB 값(1.2·1.0)이 코드와 다른 상태 그대로 두고, 게이트 제거 **단독** 효과를 먼저 잰다. 두 변수를 동시에 움직이면 O-2 의 귀인이 무너진다.

---

## 12. 결정 카드 (사용자에게)

| # | 결정 | 권고 | 대안 |
|---|---|---|---|
| **D-1** | `risk.py:744~745` 두 줄 제거 | **승인 (한 번에)** | 단계 개방 — **권하지 않음**(§5, 막을 피해가 없고 VCP 는 판독 불가) |
| **D-2** | LTV × `post_nxt`(16:00~20:00) 코호트 야간 매수 | **열되 첫 주 별도 집계**(O-4) | 지금 닫으려면 LTV `tradable_boards` 에서 `post_nxt` 제거 — 사이클 38 사용자 의도를 뒤집는 일이라 별도 결정 |
| **D-3** | `[tick_channel_pre_krx_frame]` 관측 | **이번엔 유지**, 5영업일 0행 확인 후 별도 사이클에서 정리 | 지금 같이 지우기 — 권하지 않음(revert 가 무뎌진다) |
| **D-4** | 계좌 SOFT Σ상한 활성화(`account_risk_block_pct=6.0`) | **이번 사이클 밖.** Σ오픈리스크 상한이 2.55% 라 6.0% 에 닿지 않아 효과가 없다 | — |

---

# 13. 범위 확정 — 2026-09-21 2차 자문 (사용자 「전체 전략에 대해 제거」)

## 13-A. 🔴 team-lead 의 경계는 **맞다.** 그리고 근거가 생각보다 강하다

> **한 문장 (커밋 메시지·사용자 보고용)**
> **`nxt_tradable` 을 「살 것인가」 판정에서 걷어내고, 「어느 거래소로 보낼 것인가」 배선 세 곳에는 그대로 둔다.**
> — 걷는 것은 `risk.py:744~745` 매수 평가 게이트 **하나**. 남기는 것은 ① 주문 거래소 다운그레이드
> ② 익일청산 KRX 예약 ③ 시세 채널 선택. 셋 다 **매수를 막는 장치가 아니라 주문·시세를 올바른
> 시장으로 보내는 배선**이고, 걷으면 셋 다 **매수가 아니라 청산이 깨진다.**

### 왜 배선을 걷으면 「매수 개방」이 아니라 「손절 마비」가 되는가

**(1) `order_engine._probe_nxt_downgrade_base`(`order_engine.py:753`, 판정 `:808~823`)**

team-lead 가 든 이유(「NXT 미상장 종목에 NXT 주문을 내면 거부된다」)는 맞고, **그보다 더 나쁜
2차 효과**가 `param_catalog.py:1216~1219` 에 이미 적혀 있다:

> ⚠️ **`off` 는 애프터마켓 청산도 함께 끈다** — 44/41 변환의 게이트가 "거래소가 KRX 인가"라서,
> 라우팅을 끄면 거래소가 저장값으로 남아 변환 분기에 도달하지 않고 16:00~20:00 청산이 NXT
> 애프터로 시장가를 발사한다(**NXT 는 시장가를 받지 않는다**). […] 게다가 **NXT 비대상
> 종목(`nxt_tradable=False`)에는 `off` 가 듣지 않는다** — 이미 KRX 로 다운그레이드돼 계속 44/41 을 탄다.

즉 이 다운그레이드는 **KRX 애프터마켓 호가유형 변환(44/41)의 전제**다. 걷으면 코호트 보유분의
16:00~20:00 청산이 ① NXT 애프터로 라우팅되고 ② 시장가라 거부되고 ③ 애초에 NXT 에 그 종목이
없어 또 거부된다 — **삼중 거부 = 손절 마비.** 🔴 **절대 걷지 않는다.**

**(2) `scheduler.py:1416~1440` 익일청산 사전 보류**

`nxt_tradable=False` 면 `_pending_next_day_clear` 에 넣고 **09:00 KRX 시장가로 예약**한다
(DB 영속 `reason="nxt_not_tradable"`). 이게 없으면 08:00 프리장에 NXT 로 익일청산 시장가가
나가고, 코호트는 프리장에 시장 자체가 없으므로 `APBK0918` 거부 → `SellRejectionTracker` 가
**다음 KST 09:00 TTL** 로 잠근다 = 그날 청산 경로가 통째로 막힌다. 🔴 **절대 걷지 않는다.**

**(3) `scanner._classify_channel`(`scanner.py:603~650`) / `no_feed_registry`**

가장 역설적인 것 — 이것을 걷으면 코호트가 통합/NXT 채널로 구독되어 **프레임이 다시 0건**이 되고,
**매수 평가가 도로 0 이 된다.** 사용자가 원한 것과 **정확히 반대 결과**다. 게다가 보유분이 WS blind
가 되어 손절이 REST 폴 단독이 된다(cycle293/294 가 고친 그 결함의 복원). 🔴 **절대 걷지 않는다.**

**(4) `no_feed_registry` stale watcher skip(cycle252)** — 재등록 SEND 폭주(하루 ≈14,600) 차단.
HIGH(보유·익일청산) 경로는 애초에 byte 동일이라 손절 커버리지와 무관. 매수와 접점 0. **남긴다.**

## 13-B. `nxt_tradable` 소비처 전수 분류 (`grep -rn --include='*.py' "nxt_tradable" src/`)

| # | 위치 | 하는 일 | 성격 | 처분 |
|---|---|---|---|---|
| 1 | `risk.py:744~745`(`_tick_buy_eval_blocked_by_channel` 경유) | **매수 평가 차단** | 🔴 매수 게이트 | **걷는다 — 이것 하나** |
| 2 | `order_engine.py:753`·`:808~823` `_probe_nxt_downgrade_base` | NXT/SOR → KRX 주문 다운그레이드 | 주문 배선 | 남긴다 (13-A-1) |
| 3 | `scheduler.py:1416` | 익일청산 09:00 KRX 예약 보류 | 매도 배선 | 남긴다 (13-A-2) |
| 4 | `scanner.py:603~650` `_classify_channel` | 시세 채널 선택 | 시세 배선 | 남긴다 (13-A-3) |
| 5 | `no_feed_registry.py:106` `get_nxt_tradable_map` | 위 #4 의 데이터 원천 + stale skip | 시세 배선 | 남긴다 |
| 6 | 🔴 `donchian_swing.py:103,684,696` / `kojiro.py:171,578,584` **`DEFAULT_PARAMS["nxt_tradable"]`** | `list_by_filter(nxt_tradable=…)` = **후보 유니버스 필터** | 🔴 **매수 유니버스 필터** | **§13-C — 값 확인 필요** |
| 7 | `param_catalog.py:1131` | 위 #6 을 UI 편집 가능 파라미터로 노출(`editable=True`) | 설정 표면 | §13-C |
| 8 | `scanner.py:2586` / `order_engine.py:1887` | KRX 폴백 도장 · 거부 사후 보강 `upsert_one` | 데이터 생산자 | 남긴다 |
| 9 | `routes/balance.py:41` · `routes/stock_master.py:227` | 화면 표시 · 통계 | 표시 | 남긴다 |
| 10 | `models/stock.py:26` · `balance.py:23` · `api/condition.py:451` | 필드 정의 · 파생 | 정의 | 남긴다 |
| 11 | `VB:450` · `LTV:501` · `BFB:709` 주석 | 「사이클 156 Q0 — 강제 필터 제거」 | 주석 | 남긴다(§2-A 근거) |

## 13-C. 🔴 team-lead 가 놓친 것 — donchian·kojiro 의 `nxt_tradable` **파라미터**

**사용자의 「전체 전략」 요구는 `risk.py:744` 한 줄로 완전히 충족되지 않는다.**

- `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES = {"donchian_swing", "kojiro"}` — **이 둘은 틱 매수
  평가를 애초에 안 탄다.** 즉 `:744` 를 걷어도 **donchian·kojiro 에게는 아무 일도 일어나지 않는다.**
- 그 둘에서 NXT 체크가 실제로 존재하는 유일한 자리가 **`DEFAULT_PARAMS["nxt_tradable"]`** 이고,
  `_scan_universe` 가 그것을 `list_by_filter(nxt_tradable=…)` 로 넘긴다
  (`donchian_swing.py:696`, `kojiro.py:584`). `True` 면 **NXT 지정 종목만** 후보가 된다.

**판정 = 코드를 고칠 일이 아니라 값을 확인할 일이다.**

1. **코드 기본값은 `None`(필터 안 함)** 이다 — 오늘 이미 「체크 없음」 상태일 가능성이 높다.
2. 🔴 **운영 DB 를 확인해야 한다.** `strategy_config.params` 드리프트가 39키였고(실측표),
   `PUT /api/strategies/{id}/params` 가 **병합 저장**이라 한 번 박힌 값은 계속 산다.
   ```sql
   SELECT strategy_id, params->'nxt_tradable'
   FROM strategy_config WHERE strategy_id IN ('donchian_swing','kojiro');
   ```
   - **`null` 이면** — 이미 사용자 요구대로다. 보고서에 「두 전략은 원래 필터 없음(확인함)」 한 줄.
   - **`true`/`false` 면** — `PUT /api/strategies/{id}/params` 로 **`null` 로 되돌린다**(즉시 반영,
     `enabled` 무접촉, 하한선 검증 없음). **이것이 「전 전략 적용」을 완성하는 두 번째 조치다.**
3. **키 자체를 지우는 것은 별도 사이클** — `param_catalog.py:1131` · `param_validation.py:179`
   (`(None, True, False)` enum 분기) · UI 가 함께 움직여야 한다. 지금 끼워 넣으면 revert 범위가
   두 줄에서 파일 다섯 개로 늘어난다.
4. ⚠️ **`auto_tunable=False`** 라(`param_catalog.py:1133`) AI 자문이 이 값을 자동으로 켤 수는 없다.
   사람이 UI 로만 바꿀 수 있다 — 위험도는 낮지만 **문이 열려 있다.**

## 13-D. Q3 재답 — 「한 번에 걷되, 관측 기간을 둔다」가 유일한 형태

전략 축 단계안은 전제에서 빠졌다. 남은 형태는 **지금 걷고 며칠 지켜보기**이고, 이것은
「단계 개방」이 아니라 **정상 배포 + 사전 약속된 재판단 시점**이다. **채택 권고.**

### 한 번에 걷을 때 조심할 것 — 네 가지 (전부 §7-B 판별표에 마커가 있다)

| # | 조심할 것 | 왜 한 번에 걷을 때 특히 | 임계 |
|---|---|---|---|
| **C-1** | **5전략 동시 개방 = 같은 종목에 다섯 전략이 동시 신호** | `registry.is_ticker_blocked_for_buy` 가 중복을 막지만, **먼저 도달한 전략이 이긴다.** 코호트 77종목이 한꺼번에 열리면 **어느 전략이 가져갔는가**가 틱 순서에 좌우돼 성과 귀인이 흐려진다 | `trade_history` 전략별 분포가 전주 대비 뒤집히면 확인 |
| **C-2** | **예산 조기 소진** | 후보가 2배가 되면 **오전에 슬롯이 다 찬다.** 오후 신호가 전부 `low_funds` 로 죽으면 그게 「개방 효과 없음」으로 오독된다 | 🔴 **09:00~10:00 안에 어느 전략이든 `max_positions` 도달 → 즉시 확인** (§7-B O-7) |
| **C-3** | **랏 기하 악화** | 코호트 중앙 주가가 높으면 1주 폴백이 늘고 명목이 「그 종목 주가」로 결정된다. 다섯 전략이 동시에 그러면 명목 분산이 한 번에 벌어진다 | `[oversized_fallback]`·`[ratio_notional_blocked] capped_qty=0` (§7-B O-6). 배포 **전** §7-C 두 번째 SQL 로 예측 가능 |
| **C-4** | **LTV × 16:00~20:00** | 이 시간대는 **전례가 0건**이다. 한 번에 걷으면 첫 발생이 예고 없이 온다 | 16:00~20:00 LTV 매수 **1건이라도 발생하면 그날 안에 확인** (§7-B O-4) |

### 사전 약속 — 재판단 시점을 지금 정한다 (사후 협상 방지)

| 시점 | 판단 |
|---|---|
| **D+0 (09-22 10:00)** | C-2 확인. 예산이 한 시간에 마르면 **그날 안에** `position_ratio`↓ 로 속도 조절(revert 아님) |
| **D+0 (09-22 20:00)** | C-4 확인. LTV 야간 매수 발생 여부 + KIS 거부 msg1 |
| **D+1 (09-23 아침)** | §7-B 10행 전수 판독. O-2 귀인 분리 |
| **D+3 (09-24)** | **유지 / 조정 / revert 결정.** 여기까지 코호트 체결 0건이면 「열었는데 신호가 없다」 = 원인이 게이트가 아니었다는 뜻이고, 그건 revert 사유가 아니라 **별도 조사 사유**다 |
| **D+10 (10-02)** | 성과 판단 착수 가능 시점. 🔴 **그 전에는 손익으로 판단하지 않는다** — 코호트 체결 표본이 0 에서 시작하므로 초기 몇 건의 손익은 분산이지 신호가 아니다 |

⚠️ **관측 기간에 다른 변수를 넣지 않는다** — 특히 VCP/BFB `breakout_volume_mult`,
전략 비중, `cash_usage_ratio`(§11-7). 관측 기간의 가치는 **변수가 하나**일 때만 있다.

## 13-E. 관측이 죽는가 / 아무도 안 읽는 값이 되는가 — **아니다. 셋 다 산다**

| 심볼 | 걷은 뒤 읽는 자 | 죽는가 |
|---|---|---|
| `_channel_cohort` | `_emit_tick_buy_gate`(`scanner.py:1181~1186`, `_channel_cohort` 를 직접 순회) + `tick_buy_cohort_blocked` | **안 죽는다** |
| `tick_buy_cohort_blocked` | `risk._tick_buy_eval_blocked_by_channel`(`risk.py:91`) ← `risk.py:620` | **안 죽는다** |
| `_tick_buy_eval_blocked_by_channel` | `risk.py:620` (유지) → `risk.py:621~624` `_note_pre_window_krx_frame` 게이팅 | **안 죽는다** |
| `[tick_buy_gate]` | `_emit_channel_config` → `_emit_tick_buy_gate`. **`risk.py` 와 완전 독립** | **안 죽는다** |
| `restamp_cohorts` | `subscribe_filtered_stocks`(5분) · `stale_watcher_core.py:295`(120초) | **안 죽는다** |

즉 **「죽은 코드」가 되는 것은 하나도 없다.** 기계 전체가 계속 돌고, 역할만
「매수를 막는 장치」에서 **「코호트를 세는 계측기」**로 바뀐다.

⚠️ 단 **정정 하나** — §7-B 의 체결 귀인(O-1)은 `_channel_cohort` 가 아니라
`trade_history ⋈ stock_master.nxt_tradable` **DB 조인**으로 한다. 메모리 dict 는 프로세스
재시작에 날아가고 체결 행에 기록되지도 않는다. `_channel_cohort` 가 재는 것은 **분모**
(오늘 몇 종목이 코호트였나)이고, **분자**(그중 몇이 체결됐나)는 DB 가 답한다. 둘 다 필요하다.

## 13-F. 결정 카드 갱신

| # | 결정 | 권고 |
|---|---|---|
| **D-1** | `risk.py:744~745` 제거 | **승인** (전 전략 동시, 단계 없음) |
| **D-1b** | 🔴 **신규** — donchian·kojiro `params.nxt_tradable` 확인 후 `null` 아니면 `null` 로 되돌림 | **승인 요청.** 이게 없으면 「전체 전략」 요구가 두 전략에서 미충족이다. `PUT params` 라 즉시 반영·`enabled` 무접촉 |
| **D-1c** | `nxt_tradable` **키 자체** 제거(`param_catalog`·`param_validation`·UI) | **이번 사이클 밖.** revert 범위가 파일 5개로 늘어난다 |
| **D-2** | LTV × `post_nxt` 야간 매수 | 열되 C-4 로 감시 |
| **D-3** | `[tick_channel_pre_krx_frame]` | 이번엔 유지, 5영업일 0행 확인 |
| **D-5** | 🔴 **신규** — 재판단 시점 사전 확정(D+0 10:00 / D+0 20:00 / D+1 / D+3 / D+10) | **승인 요청.** 사후 협상을 막는 장치 |

---

# 14. 🔴 `[tick_channel_pre_krx_frame]` 180행 판정 (2026-09-21 3차)

> ⚠️ 팀장이 「§11 로 append」를 요청했으나 이 파일은 이미 §1~§13 이라 **§14** 로 붙인다(§1~§13 무접촉).

## 14-A. 결론 먼저

| 질문 | 판정 |
|---|---|
| cycle294 §0 가정이 틀렸나 = 별건 CRITICAL 인가 | 🔴 **아니다.** 추론은 **K1(시가 단일가)에 대해 참**이고, 빠뜨린 것은 **K2(장전 시간외 종가 08:30~08:40)** 라는 **중첩 행 하나**다. 실측이 그것을 증명한다 — **08:00~08:29 행이 0건**이고 180행 전부가 08:30~08:39 다. 범위 오류이지 사실 오류가 아니다 |
| A. §3(ACML_VOL) 결론이 바뀌나 | **안 바뀐다.** 오히려 **실측으로 확증됐다**(§14-B) |
| B. LTV × `pre_nxt` × K2 노출 | **(a) 무해.** 코드가 **삼중으로 잠근다**(§14-C). 새 가드 불필요 |
| C. 제거 계획 | **그대로 두 줄.** 같이 넣을 것 없음 |
| D. `_note_pre_window_krx_frame` | **남긴다.** 단 **docstring 두 곳을 반드시 고친다**(§14-E) |

팀장 해석(「K2 를 빠뜨린 것」)이 **정확하다.** `market_state.py:308~320` 이 이미
`row_id="K2" · start=08:30 · end=08:40 · match_kind="fixed_price" · confidence=_CONFIRMED` 로
적어 두었고, 노트에 「K1 안에 들어 있는 **의도된 중첩**」까지 명시돼 있다.
**정본은 알고 있었고, cycle294 §2-D 의 서술이 그 행을 참조하지 않았다.**

## 14-B. A — §3 결론은 바뀌지 않는다 (오히려 확증됐다)

### (1) 180행은 §3-A 를 **반증하는 것이 아니라 증명한다**

§3-A 의 주장은 「차단 코호트는 08:00~20:00 `H0STCNT0` 고정」이었다.
프리 창에 **KRX 전용 채널 프레임이 실제로 들어왔다**는 것은, 그 시각에 그 코호트가
**KRX 채널에 있었다는 직접 증거**다. 추론이 아니라 실측이 됐다.

### (2) 스코프 정합 — 분자와 분모 **둘 다** K2 를 포함한다

- **분자** = `H0STCNT0` 누적. K2 체결이 08:30 부터 `acml_vol` 에 쌓이고, **채널이 안 바뀌므로**
  09:00 이후 정규장·애프터까지 **같은 채널에서 이어 쌓인다**. 단일 스코프 유지.
- **분모** = `stock_master_daily.acml_vol` ← KIS `FHKST03010100`, `FID_COND_MRKT_DIV_CODE="J"`.
  이것은 KRX 가 발표하는 **당일 총 누적거래량**이고 시간외종가 거래를 포함한다.
  ⇒ **양쪽 다 포함 = 정합.**

### (3) 🔴 그리고 **그 비교를 하는 두 전략은 그 시각에 매수하지 않는다**

`vcp_breakout.py:132` · `bull_flag_breakout.py:96` = `DEFAULT_TRADABLE_BOARDS = ("main",)`.
08:30 의 활성 보드는 `session.py:63` 기준 `{PRE_NXT}` 뿐이라 `session_tracker.is_tradable` 가
**두 전략을 `risk.py:722` 에서 이미 컷한다.** K2 물량은 그 전략들에게 「09:00 에 물려받는
시작값」일 뿐이고, 판정 시점(장중)에는 분모·분자 모두에 들어 있다.

### (4) 크기 판정 — 122 프레임은 무시할 크기다

- **프레임 ≠ 거래량.** `n=122` 는 그 종목에 온 **체결 프레임 수**이지 주식 수가 아니다.
  K2 는 전일 종가 **고정가**라 소량 분할 체결이 많이 찍힌다 — 프레임이 많아도 물량은 작다.
- 180행 ÷ 5영업일 ≈ **일 36종목**이 코호트 77 중에서 프레임을 받았다(절반 이하).
- 최악을 가정해 **분모가 K2 를 빼고 분자만 포함한다 해도** 방향은 게이트가 **쉬워지는** 쪽이고,
  크기는 장전 시간외 종가 통상 비중(일거래량의 수 % 이하)이다.
  VCP `breakout_volume_mult` 운영값 **1.2 = 20% 마진** 안에 들어간다.
- ⇒ **판정: 무시 가능. §3 의 「KRX↔KRX 정합」 결론 유지.**

## 14-C. B — LTV × `pre_nxt` × K2: **(a) 무해.** 코드가 삼중으로 잠근다

### 먼저 — 08:30 에 보드 가드를 통과하는 전략은 **LTV 하나뿐**이다

`session.py:63` `boards_at(08:30) = {PRE_NXT}`.

| 전략 | `tradable_boards` | 08:30 통과? |
|---|---|---|
| momentum | `("krx_open","main")` | ✗ (KRX_OPEN 은 PRE_NXT 로 통합됐다 — `session.py:62`) |
| volatility_breakout | `("main",)` | ✗ |
| bull_flag_breakout / vcp_breakout | `("main",)` | ✗ |
| **long_tail_volatility** | `("pre_nxt","main","post_nxt")` | **✓ 통과** |

### 그리고 LTV 는 그 구간에 **신호를 낼 수 없다** — 잠금 셋

K2 는 `match_kind="fixed_price"`(`market_state.py:311`) = **전일 종가 고정**이다.
따라서 그 10분 동안 `current_price ≡ 전일종가` 이고, LTV `check_buy_signal` 에서:

| # | 잠금 | 코드 | 왜 걸리는가 |
|---|---|---|---|
| **L1** | **등락률 필터** (가장 먼저 걸린다) | `long_tail_volatility.py:792~798` · 운영/코드 `min_prdy_rate = 5.0` | `prdy_rate = (전일종가 − 전일종가)/전일종가 × 100 = **0.0%** < 5.0` → 즉시 `Signal.NONE` |
| **L2** | **돌파 술어 모순** | `:806` `if prev < target and current_price >= target` | 가격이 고정이라 `prev == current`. 그러면 `current < target ∧ current >= target` = **논리적 모순**. 첫 프레임은 `prev == 0` 이라 `:804` 에서 이미 `NONE` |
| **L3** | **목표가가 구조적으로 위에 있다** | `:787` `target = board_info["target_price"]`, 산출은 `prepare` `:392` `target_offset = int(prev_range × k)` | `board_open` 이 전일종가로 확정돼도 `target = board_open + target_offset > board_open = current` — `:393~397` 이 `target_offset ≤ 0` 인 종목을 후보에서 이미 배제한다 |

L1 이 `ticker_prev_close` 부재로 건너뛰어져도 L2·L3 가 남는다. **방어가 겹쳐 있다.**

### 오염 leak 도 없다 — 경계가 **보드별**이다

- `_open_confirmed` = `self._open_confirmed.get(ticker, {}).get(board, False)` — **보드별 dict**.
  08:30 의 전일종가 확정은 `pre_nxt` 칸에만 들어간다.
- `_prev_price` = `self._prev_price.setdefault(ticker, {}).get(board, 0)` — **보드별**.
  09:00 에 `main` 으로 바뀌면 baseline 이 0 에서 다시 시작(첫 틱 `NONE`).
- `main` 보드 기준가는 cycle272 D1 이 **KRX REST `stck_oprc` 단독**으로 못 박았고
  `source` 신뢰 목록이 `("rest",)` 뿐이라 WS 경로가 조용히 거부된다.
- ⇒ **K2 가격이 `main` 판정에 새어 들어갈 경로가 없다.**

### 덧붙임 — 청산 축에서는 이미 일어나고 있던 일이다

게이트는 **매수 전용**이다. LTV 는 `_PRE_MARKET_EXIT_EVAL_STRATEGIES` 유일 멤버라
**프리장 청산 평가 보류에서 제외**돼 있다 — 즉 **K2 프레임으로 LTV 청산이 평가되는 것은
cycle294 배포 이후 이미 5영업일째 일어나고 있고**, 그 결과가 180행 옆에 사고로 남지 않았다.
게이트 제거가 추가하는 것은 **매수 축 평가**뿐이고, 그쪽은 위 삼중 잠금이 막는다.

### 판정 = **(a) 무해. 새 가드를 걸지 않는다**

만약 (b) 를 택했다면 시각 창(`08:30~08:40`)이나 `MarketPhase.PRE_CLOSE_FIXED` 판정을
새로 들여야 하는데 —
- **시각 리터럴**은 `tick_channel_clock` 계약(시각 리터럴 0건 · G-294-1)과 정면 충돌한다.
- `market_state` 의 phase 로 판정하면 리터럴은 피하지만 **매매 행위 변경 + 신규 게이트**라
  별도 승인·별도 사이클이다.
- **그리고 막을 것이 없다** — 삼중 잠금이 이미 `Signal.NONE` 을 보장한다.
  「아무것도 안 막는 게이트」를 넣는 것은 다음 사람에게 **없는 위험을 있다고 가르치는 일**이다.

⚠️ 단 하나의 잔여 — **`min_prdy_rate` 를 0 이하로 내리면 L1 이 사라진다**(L2·L3 는 남는다).
운영값 5.0 이 이 방어의 첫 겹이라는 사실을 §11 금기에 추가할 것을 권고한다.

## 14-D. C — 제거 계획은 그대로다

`risk.py:744~745` **두 줄만.** 같이 넣을 것 없음. 근거 =
① §14-B 로 ACML_VOL 스코프 쟁점 해소 ② §14-C 로 K2 노출이 행위 0 확정
③ 이 발견은 **관측의 해석**을 바꿀 뿐 **행위**를 바꾸지 않는다.

🔴 **미룰 이유가 없다** — 구체적 피해를 댈 수 없기 때문이다. 이 발견이 드러낸 것은
「08:30~08:40 에 코호트 프레임이 온다」는 **사실**이고, 그 사실의 매수 축 결과는
삼중 잠금에 의해 **`Signal.NONE`** 으로 확정돼 있다.

## 14-E. D — `_note_pre_window_krx_frame` 은 **남긴다.** 단 docstring 을 고친다

### 남기는 이유 (처분 변경)

1차 메모는 「0행이면 정리 후보」라고 썼다. **실측이 180행이므로 그 조건이 성립하지 않는다.**
게다가 이 관측의 **가치가 커졌다** — 이제 「0인가?」를 묻는 일회성 검증이 아니라
**K2 프레임 규모의 상시 계측기**다. 게이트를 걷으면 그 구간이 LTV 매수 평가를 실제로 돌게
되므로(신호는 안 나지만 평가는 돈다), 규모가 튀면 알아야 한다.

`risk.py:621~624` 는 게이트 분기 **앞**이라 `:744~745` 만 걷으면 **byte 동일하게 산다.**
**무접촉이 맞다.**

### 🔴 반드시 고칠 docstring **두 곳** (안 고치면 다음 사람이 오판한다)

| 위치 | 현재 문장 | 고칠 내용 |
|---|---|---|
| `tick_channel_clock.py:400~404`(`note_pre_window_frame`) | 「**[추론, 확신 ≈80%] 보내지 않는다** — 체결가 채널이고 단일가 구간에는 체결이 없다. 이 함수가 그 추론을 D+1 에 실측으로 바꾼다」 | 「**실측 완료(09-15~09-21, 180행)** — K1(시가 단일가)에는 0건이 맞다. 그러나 **K2(장전 시간외 종가 08:30~08:40, `market_state` `row_id="K2"`, `fixed_price`)** 가 K1 안에 중첩돼 있어 그 10분은 체결이 난다. 이 함수는 이제 **K2 프레임 규모의 상시 계측기**다」 |
| `tick_channel_clock.py:445~447`(`emit_pre_window_frame_summary`) | 「**기대값은 0행이다.** 한 행이라도 뜨면 §0 의 추론이 틀린 것이고, 그때는 게이트 추가 여부를 결정 카드로 올린다」 | 「**기대값은 K2 구간(08:30~08:40) 한정 수십 행이다**(실측 일 30~55행). 🔴 **08:30 이전 `first_at` 이 뜨면** 그때가 §0 추론이 틀린 것이다 — K1 단독 구간에 체결이 났다는 뜻이고 결정 카드 대상이다」 |
| `risk.py:139~148`(`_note_pre_window_krx_frame`) | 같은 추론 문구 반복 | 위와 같은 취지로 1~2줄 갱신 |

🔴 **새 판별 기준 = `first_at < 08:30` 이 한 행이라도 뜨는가.**
이것이 원래 추론의 진짜 검정식이고, 지금까지 **0행**이라 추론은 **살아 있다.**

⚠️ **재핀 비용은 늘지 않는다** — `tests/unit/ast/test_cycle287_ast_scope.py::test_s1b` 의
`_SRC_TREE_DIGEST` 는 `src/**/*.py` **전 파일 내용 sha** 라 `risk.py` 한 줄만 고쳐도
어차피 재핀 대상이다. `tick_channel_clock.py` 를 같이 고쳐도 **재핀은 여전히 한 번**이다.
(파일 단위 핀이 `test_cycle290/291/294/295_*` 에 따로 있는지는 스위트 1회 실행으로 확인 —
메모리 「고친 뒤 전체 스위트 재실행」.)

## 14-F. §7-B 판별표 갱신 2행

| # | 관측 | 정상 | 🟠 경보 | 🔴 사고 |
|---|---|---|---|---|
| **O-11** 🆕 | `[tick_channel_pre_krx_frame]` 의 **`first_at` 최솟값** | **≥ 08:30** (K2 안) | 08:20~08:29 가 1행 | 08:00~08:19 가 1행 = K1 단독·NXT 프리 구간에 KRX 체결 = §0 추론 붕괴 |
| **O-12** 🆕 | 08:30~08:40 **LTV 매수 체결** | **0건** (삼중 잠금) | **1건이라도 발생** = L1/L2/L3 중 하나가 깨졌다 → `min_prdy_rate` 값부터 확인 | 2건 이상 |

## 14-G. §11 금기 추가

8. 🔴 **LTV `min_prdy_rate` 를 0 이하로 내리지 않는다** — 그 값(운영 5.0)이 K2 구간
   전일종가 프레임에 대한 **첫 번째 잠금**이다. 내려야 할 이유가 생기면 L2·L3 가 남지만,
   방어 겹이 셋에서 둘로 준다는 사실을 함께 기록한다.
9. 🔴 **K2 노출에 새 게이트를 만들지 않는다** — 막을 것이 없고(§14-C), 시각 리터럴 금기
   (G-294-1)와 충돌하며, 「아무것도 안 막는 게이트」는 다음 사람에게 없는 위험을 가르친다.
