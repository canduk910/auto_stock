# 주간 파라미터 자문 — 2026-09-10 (목)

> 작성 = 주간 자문 루틴(목 20:30 KST, 읽기 전용). **이 문서는 코드·DB·설정을 아무것도 바꾸지 않았다.**
> 이 파일 1개 외에 리포에 손댄 것이 없다.
> 접속 = `GET https://auto.dkstock.cloud/health` → **200**(Basic Auth reporter, https).
> 모든 수치에 출처를 병기한다. 번들에 없는 것은 "번들에 없음"으로 적었다.
> **예상과 실측을 구분한다** — "실측"이라 적지 않은 것은 코드 판독이거나 추정이다.

---

## 0. 이번 주 한 줄

권고하는 파라미터는 **딱 1개**다 — `vcp_breakout.last_pullback_max` **0.10 → 0.12**(코드 기본값 복원, **완화**).
나머지 6전략은 **무권고**다. 표본이 없거나(BFB 3·momentum 3), 전략이 꺼져 있거나(momentum·VB·LTV),
기대값이 이미 양수라 손댈 이유가 없다(donchian·kojiro).

---

## 1. 한 페이지 요약

정본 = `GET /api/strategies`(20:32 KST 실측) · `GET /api/history`(627행 전수, 7페이지 전부 수집) ·
`GET /api/strategy-funnel/recent?strategy_id=…&days=7`.
**청산 왕복 = 최근 30일(2026-08-11~09-10) `trade_type=SELL` ∧ `status∈{COMPLETED,PARTIAL}` 행 수.**

| 전략 | 라이브 | 30일 왕복 | 판정 | 30일 기대값 | 권고 키 수 |
|---|---|---:|---|---|---:|
| `momentum` | **꺼짐** w=0.0 | 3 | insufficient | −487/왕복 (RR 1.16) | **0** |
| `volatility_breakout` | **꺼짐** w=0.0 | 45 | sufficient | −1,046/왕복 (RR 0.67 < 손익분기 1.25) | **0** |
| `long_tail_volatility` | **꺼짐** w=0.0 | 19 | sufficient | −1,707/왕복 (RR 0.56 < 손익분기 2.17) | **0** |
| `donchian_swing` | 켜짐 w=0.20 | 15 | sufficient | **+169/왕복** (RR 1.35 > 1.14) | **0** (무변경) |
| `bull_flag_breakout` | 켜짐 w=0.20 | 3 | insufficient | −2,877/왕복 (3전패) | **0** (§5 동결) |
| `vcp_breakout` | 켜짐 w=0.20 | **0** | insufficient | 없음 (전 기간 체결 0건) | **1** ← 유일 |
| `kojiro` | 켜짐 w=0.40 | 12 | sufficient | **+97/왕복** (RR 2.06 > 2.00) | **0** (무변경) |

**권고 총계 = 1개, 방향 = 완화.** 일일 튜너(OpenAI)의 조임 편향(§4.1, 실측 98.1%)을 재생산하지 않았다.

### ⚠️ 이 표를 읽기 전에 알아야 할 라이브 변경

**프롬프트 §5 의 서술과 라이브 값이 다르다. 규칙대로 라이브 값을 정본으로 썼다.**

| 항목 | 프롬프트 §5 서술 | **20:32 KST 라이브 실측** |
|---|---|---|
| `momentum` | (언급 없음, 가동 전제) | `enabled=False`, `weight=0.0` |
| `volatility_breakout` | K_ρ=2.5 적용 대상(가동 전제) | `enabled=False`, `weight=0.0` |
| `long_tail_volatility` | K_ρ=2.5 적용 대상(가동 전제) | `enabled=False`, `weight=0.0` |
| `kojiro` | `weight≈0.19` | **`weight=0.40`** |
| `donchian`/`BFB`/`VCP` | (개별 언급 없음) | 각 **0.20** |

Σ(켜진 전략) = 0.20+0.20+0.20+0.40 = **1.00**.
즉 **오늘 기준으로 매매하는 전략은 4개**(donchian·BFB·VCP·kojiro)이고, 30일 표본의 **68%**
(97왕복 중 66 = momentum 3 + VB 45 + LTV 19)는 **더 이상 거래하지 않는 전략에서 나온 것**이다.
이 사실이 이번 주 권고가 1개뿐인 가장 큰 이유다. → 감사 공백은 **결정 항목 D1**.

---

## 2. 계좌 전체 관점

### 2.1 자산과 손익

| 항목 | 값 | 출처 |
|---|---|---|
| 순자산 | **2,553,398원** | `GET /api/performance/daily?days=30` 09-10 `total_asset` = `GET /api/portfolio/risk` `account_gate.net_asset` (2자 일치) |
| 예수금 | 1,535,476원 | 같은 곳 `deposit` |
| 이번 주 실현손익 (09-07~09-10, 4영업일) | **+9,600원** | `perf/daily` `daily_realized_pnl` 합 (+2E+4 −8,800 +400 −2,000) |
| 전주 실현손익 (08-31~09-04) | −28,200원 | 같은 곳 |
| 최근 30행 실현손익 합 | −94,145원 | 같은 곳 (07-30~09-10) |
| 30일 누적수익률 | −5.74% | `GET /api/performance/summary` `total_profit_rate` |

> ⚠️ **누적수익률·일간수익률은 이번 주에도 신뢰할 수 없다.** 같은 응답의 `net_external_cashflow`
> 가 30행 중 |중앙값| **231,496원** · |최대| **1,598,444원** 으로 순자산(2,553,398원)의 최대 **63%** 를
> 오간다. 실제 입출금이 그만큼 있었다면 수익률 분모가 매일 바뀐 것이고, 산식 부산물이라면 수익률
> 자체가 오염된 것이다. 어느 쪽인지 **판별할 근거가 번들에 없다.** → **결정 항목 D5.**
> 이 문서의 손익 판단은 전부 `daily_realized_pnl` 합과 `history` 의 `profit_loss` 합만 썼다.

### 2.2 노출과 오픈리스크

`GET /api/portfolio/risk` 본문(`total_notional_won`·`concurrent_positions` 등)은 **전부 0** 이지만
이것은 **노출이 0이라는 뜻이 아니다** — 20:32 조회 시점에 엔진이 이미 종료돼 있다
(`GET /api/trading/status` `running=false` · `phase=idle` · `last_scan_time=19:59:22`).
`scheduler.py:1045` 의 일일 종료(`매매 시스템 종료`) 후 in-memory 포지션이 비고, `run_daily` 가
다음 영업일 08:20 에 재시작한다. **정상 야간 상태다.**

장중 실측치는 같은 응답의 게이트 스냅샷이 남긴 것을 쓴다:

| 항목 | 값 | 출처 |
|---|---|---|
| 평가 시각 | 2026-09-10 **20:08:20** KST (`age_secs=1457`, `stale=true`) | `account_gate.evaluated_at` |
| 보유 포지션 | **10** | `account_gate.coverage.total_positions` (본문 `by_strategy` 는 종료 후 0) |
| Σ오픈리스크 (실효) | **0.97%** of 순자산 | `account_gate.open_risk_pct` |
| Σ오픈리스크 (프록시) | **2.42%** of 순자산 | `account_gate.open_risk_proxy_pct` |
| 관측 임계 / 차단 임계 | 4.0% / **null(미활성)** | `account_gate.warn_pct` / `block_pct` |
| 한도 초과 포지션 | **1건** | `account_gate.over_cap_count` |
| 게이트 판정 | `ok`, `reasons=[]` | `account_gate.level` |

**계좌 노출은 여유롭다** — 실효 0.97%는 관측 임계 4.0%의 1/4 수준이다. 이번 주 자문에서
리스크 축소를 권고할 계좌 차원의 근거는 없다. (계좌 전체 노출 레버 `cash_usage_ratio` 는
프롬프트 §3 에 따라 내 권고 대상이 아니다.)

### 2.3 진입 시각대별 손익 — cycle262 검증 (이번 주 가장 중요한 실측)

`history` 627행을 (전략, 종목) FIFO 로 매수↔매도 짝지어 297왕복을 만들고 **매수 체결 시각**으로
분류했다. `volatility_breakout` 전 기간:

| 매수 시각대 | 왕복 | 승률 | 합계 손익 | 평균 |
|---|---:|---:|---:|---:|
| **09:00:00~09:01:30** | 29 | **17.2%** | **−110,900원** | −3,824 |
| 09:02~09:30 | 43 | 58.1% | +74,575원 | +1,734 |
| 09:30~12:00 | 35 | 37.1% | −52,551원 | −1,501 |
| 12:00~ | 22 | 31.8% | −1,480원 | −67 |

**개장 90초 코호트 하나가 VB 전 기간 손실(−100,726원)보다 큰 −110,900원을 냈다.** 나머지 세 구간
합은 +20,544원이다. 이것은 cycle262(`open_entry_hold_secs=90`)와 cycle264/265(`[7] STCK_OPRC`
스코프 오염)가 지목한 바로 그 구간이며, 이 자문의 독립 표본이 그 진단을 **뒷받침한다**.

**그리고 게이트는 실제로 닫혔다** — `history` 전수에서 `09:00:00~09:01:30` 구간 매수 체결의
**마지막 날짜는 2026-09-04** 다. cycle262 발효(09-07) 이후 09-07·08·09·10 **4영업일 연속 0건**이고,
라이브 `volatility_breakout.open_entry_hold_secs=90` · `long_tail_volatility.open_entry_hold_secs=90`
로 값도 확인된다. **예상이 아니라 실측이다.**

다만 **근본 시정(cycle265)은 아직 열려 있다.** 90초 보류는 지혈이고 오염된 `[7]` 값 자체는
그대로다(루트 `CLAUDE.md` cycle262 항 "지혈이며 근본 시정이 아니다"). VB·LTV 가 꺼져 있는
지금은 무해하지만 **재활성 전에는 선결 조건**이다. → **결정 항목 D4.**

---

## 3. 전략별 자문

### 3.1 `vcp_breakout` — 이번 주 유일한 권고

```json
{"strategy_id":"vcp_breakout","sample_status":"insufficient","closed_round_trips_30d":0,
 "recommended_params":{"last_pullback_max":0.12},
 "reasoning":"funnel 5일 실측에서 VCP 가 죽는 곳은 step 8(거래량 수축)이 아니라 step 7(Pullback 점진 수축)이다 — 베이스 검출 생존 24/32/22/28/38 이 step7 에서 1/1/2/1/4 로 줄어 평균 92% 가 탈락한다. step7 의 excluded_sample(cap 20/일, 5일치) 중 23건은 pullback 회수가 허용 범위 [2,4] 안이면서 오직 '마지막 폭 ≤ 10%' 하나만 위반했고(예: 010950 S-Oil 11.0% 5일 연속·073240 금호타이어 14.0% 4일·005180 빙그레 10.4%), 그 23건 중 11건이 0.12 에서 통과한다. 라이브 0.10 은 코드 DEFAULT_PARAMS 0.12(vcp_breakout.py:126, '사이클 48 — 0.08→0.12 한국 중소형주 변동성 현실화')보다 조여진 값이므로 이 권고는 신규 완화가 아니라 기본값 복원이다. 2차 병목인 volume_contraction_ratio 는 라이브 1.00 = PARAM_RANGES 상한이라 더 완화할 수 없다.",
 "recommended_weight":null,
 "weight_reasoning":null,
 "hypotheses":[
   {"claim":"VCP 의 체결 0건은 배관 결함이 아니라 step7 임계 엄격 때문이다","evidence":"funnel step1~6 은 매일 정상 통과(3583→1023→709→700→55→38, 09-10)하고 step7 에서만 89~97% 가 탈락한다. 탈락 사유 문자열이 조건별로 구분돼 기록되고 step9/step99 가 값을 산출하므로 배관은 살아 있다(09-08 1건·09-10 2건 prepared 실측)","test":"last_pullback_max=0.12 적용 후 step7 생존 수와 step99 prepared 수를 10영업일 추적","required_sample":10,"confidence":0.8},
   {"claim":"0.12 로 완화해도 하루 prepared 는 3건을 넘지 않아 리스크 증가가 제한적이다","evidence":"step7 이 23건 중 11건만 늘고, 그 뒤 step8(거래량 수축) 통과율이 실측 09-08 1/2·09-10 2/4 = 약 50% 다. 현재 prepared 0.6건/일 → 추정 1.5~3건/일","test":"적용 후 10영업일 step99 일평균과 실제 체결 수","required_sample":10,"confidence":0.6},
   {"claim":"VCP 는 표본을 못 만드는 것이지 지는 것이 아니다","evidence":"전 기간 체결 0건 = 승패 자체가 없다. 그런데 라이브 weight=0.20 으로 예산의 1/5 을 점유한다","test":"체결 10왕복 확보 후 기대값 산출","required_sample":10,"confidence":0.9}],
 "needs_human_decision":[
   {"topic":"volume_contraction_ratio 가 범위 상한에 붙어 있다","issue":"라이브 1.00 = PARAM_RANGES 상한(0.30~1.00)이자 코드 기본값 0.70 보다 이미 완화된 값이다. 2차 병목인데 자문이 더 완화할 수단이 없다","evidence":"09-04·09-07·09-09 는 step7 생존 1건을 step8 이 전부 탈락시켜 prepared 0 (funnel 실측). 09-09 일일 튜너는 오히려 0.8 로 조이라고 권고했다(GET /api/recommendations)","options":["현행 1.00 유지(자문 권고 없음)","PARAM_RANGES 상한 재검토는 코드 변경 = 사람 결정","step7 완화 후 step8 통과율을 10영업일 재측정한 뒤 판단"]},
   {"topic":"체결 0건 전략이 예산 20% 를 점유한다","issue":"weight=0.20 인데 전 기간 왕복 0. allocate_funds 가 Σ 로 정규화하므로 이 20% 는 놀고 있는 자금이 아니라 다른 전략이 못 쓰는 자금이다","evidence":"GET /api/strategies vcp_breakout.weight=0.20 · GET /api/history 627행 중 vcp_breakout 0행","options":["step7 완화 후 10영업일 관찰하고 그때 비중 재검토","즉시 비중 축소(자문은 권고하지 않는다 — 표본 0으로 비중을 깎는 것은 프롬프트 §6 금지 추론)","현행 유지"]}],
 "no_change_reason":null,
 "code_review_notes":"last_pullback_max 는 PARAM_RANGES (0.03, 0.15) 안이고 INT_PARAMS 가 아니며 §4 봉인 키 목록에 없다. pullback_count_min/max(2/4)와 '직전 대비 폭 감소' 단조 조건은 PARAM_RANGES 에 없어 권고 대상이 아니다 — step7 탈락의 나머지 절반은 그 두 조건이 만든 것이므로 이 권고는 병목을 없애지 않고 줄인다."}
```

**사람이 읽는 해설.**
VCP 는 4개월 반 동안 **한 번도 사지 못했다**. 그런데 지금 예산의 20% 를 들고 있다.
"거래가 없으니 비중을 줄이자"는 프롬프트 §6 이 금지한 추론이고, 나도 그렇게 권고하지 않는다.
대신 funnel 을 열어 **어디서 죽는지** 봤다.

죽는 자리는 명확하다. 베이스(base)까지는 매일 22~38종목이 살아 오는데, 그다음
"Pullback 이 점점 얕아지는가" 관문에서 **평균 92%가 잘린다.** 그 관문은 세 조건의 AND 다 —
① 되돌림 횟수가 2~4회 ② 매번 직전보다 얕아질 것 ③ **마지막 되돌림 폭이 10% 이하**.
①②는 튜닝 대상이 아니고(범위 밖), ③만 조정 가능하다.

탈락 종목의 사유 문자열을 5일치 파싱해 보니 **①은 통과했는데 ③만 걸린 종목이 23건**이었다.
S-Oil(11.0%)은 5일 연속, 금호타이어(14.0%)는 4일 연속 같은 이유로 잘렸다. 그중 **11건이
0.12 에서 통과**한다. 그리고 **0.12 는 우리가 지어낸 값이 아니라 코드에 적힌 기본값**이다
(`vcp_breakout.py:126`, 주석 "사이클 48 — 0.08→0.12 한국 중소형주 변동성 현실화").
라이브 0.10 은 그 기본값보다 조여진 상태이고, 최소 2026-08-11 부터 그랬다
(`/api/recommendations` 의 `current_params` 22행 전부 0.1).

즉 이 권고는 **모험이 아니라 원위치**다. 그리고 표본 규약과도 충돌하지 않는다 —
§6 이 표본 부족 시 null 로 두라고 한 것은 **청산 축과 비중 축**이고, `last_pullback_max` 는
**후보를 만드는 진입 필터**다. 후보가 안 나오면 §6 이 요구하는 표본 10왕복은 **영원히 모이지 않는다.**
표본을 모으려면 표본 생성기를 먼저 열어야 한다.

> 📌 **정직하게 밝힐 것** — 일일 튜너도 같은 값을 08-14·08-19·08-25 **세 번** 권고했고 세 번 다
> `expired`(만료) 로 끝났다. **`rejected`(기각)가 아니다** — 사람이 거부한 것이 아니라 손대지
> 않은 채 시효가 지난 것이다(`/api/recommendations` `status` 필드 실측). 명시 기각이었다면
> 프롬프트 §2 에 따라 반복하지 않았을 것이다. 판단은 사람 몫이다.

---

### 3.2 `donchian_swing` — 무변경 (기대값 양수)

```json
{"strategy_id":"donchian_swing","sample_status":"sufficient","closed_round_trips_30d":15,
 "recommended_params":{},
 "reasoning":"30일 15왕복 기대값이 +169원/왕복으로 양수다(승률 46.7%, 평균이익 2,364, 평균손실 1,752, RR 1.35 > 손익분기 1.14). 전 기간 28왕복 기준으로는 −1,118원/왕복이므로 최근 30일이 개선 구간이고, 그 개선을 만든 파라미터를 지금 흔들 근거가 없다. 일일 튜너가 30일간 반복 권고한 position_ratio 0.2→0.15·stop_loss_rate −6→−5·volume_multiplier 1.5→1.8 은 전부 조임이며 기대값이 양수인 구간에서 조이면 RR 1.35 가 손익분기 1.14 아래로 내려갈 위험이 손실 축소 효과보다 크다.",
 "recommended_weight":null,
 "weight_reasoning":"15왕복은 비중 조정 근거로 충분하지 않고, peer 비교 대상인 kojiro(12왕복)도 문턱 근처다. 프롬프트 §6 에 따라 양쪽이 넉넉히 문턱을 넘을 때까지 비중은 건드리지 않는다.",
 "hypotheses":[
   {"claim":"donchian 의 우측 꼬리가 breakout_fail_n_days=2 에 잘리고 있다","evidence":"30일 15왕복 보유일 중앙값 2일·최대 8일. 20일 신고가 돌파 전략의 보유기간으로는 짧다. 이익 상위 3건은 hold=2d(+7,100), hold=2d(+3,900), hold=6d(+2,500) 로 2일 관문 직전·직후에 몰려 있다","test":"breakout_fail_n_days 를 2→4 로 두고 30왕복 비교(봉인 키라 사람 결정 필요, shadow 관측 선행 권장)","required_sample":30,"confidence":0.45},
   {"claim":"stop_loss_rate 는 스탬프 랏에서 실질 무효라 튜닝해도 행위가 안 바뀐다","evidence":"라이브 sizing_mode=turtle · stop_atr=2.0 이고 루트 CLAUDE.md 는 _entry_atr 스탬프 랏이 ATR 손절을 탄다고 못박는다. 튜너가 30일간 stop_loss_rate 를 63회 조이라고 권고했지만 스탬프 랏에는 닿지 않는다","test":"청산 로그에서 손절 발화 사유를 ATR/고정% 로 분류","required_sample":20,"confidence":0.7}],
 "needs_human_decision":[
   {"topic":"atr_trail_mult 가 코드 기본값보다 조여진 채로 남아 있다","issue":"라이브 1.8 vs 코드 DEFAULT 2.0. §4 봉인 키라 자문이 권고할 수 없으나, 30일 보유일 중앙값 2일과 함께 보면 추세추종의 우측 꼬리 절단 신호다","evidence":"GET /api/strategies donchian_swing.atr_trail_mult=1.8 · PARAM_RANGES 주석(recommendation_engine.py)이 cycle223 에서 이 키를 뺀 이유로 '코드 기본값 2.0 → 라이브 1.8 로 더 타이트 이탈'을 명시","options":["2.0 복원(코드 기본값)","현행 1.8 유지","30왕복 쌓일 때까지 판단 보류"]},
   {"topic":"breakout_fail_n_days=2 가 PARAM_RANGES 구 범위의 하한에 정확히 붙어 있다","issue":"§4 봉인 키. cycle223 주석이 '하한에 정확히 붙어 있어 cycle209 과튜닝과 동형 서명'이라고 이미 적어 뒀다","evidence":"GET /api/strategies donchian_swing.breakout_fail_n_days=2 · recommendation_engine.py PARAM_RANGES 주석","options":["2→3 또는 4 로 완화","현행 유지","shadow 관측(청산 사유 분류) 선행"]}],
 "no_change_reason":"30일 기대값 양수 + 표본 15왕복. 이기고 있는 설정을 15왕복 근거로 바꾸는 것은 튜닝이 아니라 잡음이다.",
 "code_review_notes":null}
```

**해설.** donchian 은 이번 주 4개 가동 전략 중 **가장 건강하다**. 30일 기준 승률 46.7%,
손익비 1.35 로 손익분기 1.14 를 넘겼다. 전 기간(28왕복)으로는 아직 −1,118원/왕복이지만
방향은 개선이다.

주의할 것은 **보유기간**이다. 30일 15왕복의 보유일 중앙값이 **2일**이고, 5일 이상 들고 간 것은
3건뿐이다. 20일 신고가를 사서 2일 만에 나오는 것은 추세추종이 아니라 스캘핑에 가깝다.
그 2일을 강제하는 `breakout_fail_n_days=2` 와 트레일링 `atr_trail_mult=1.8`(코드 기본 2.0)은
**둘 다 §4 봉인 키**라 내가 권고할 수 없다. 그래서 결정 항목으로 올린다.

---

### 3.3 `kojiro` — 무변경 (오른쪽 꼬리를 지켜야 한다)

```json
{"strategy_id":"kojiro","sample_status":"sufficient","closed_round_trips_30d":12,
 "recommended_params":{},
 "reasoning":"30일 12왕복 기대값 +97원/왕복(승률 33.3%, 평균이익 9,250, 평균손실 4,480, RR 2.06 > 손익분기 2.00)으로 간신히 양수다. 이 전략의 수익 구조는 전형적인 추세추종 — 이익 상위 4건이 전부 보유 9~21일 구간(+11,500 / +10,200 / +9,600 / +5,700)이고 승률은 낮다. RR 2.06 이 손익분기 2.00 을 3% 마진으로 넘고 있어 청산을 조이면 즉시 음수로 떨어진다. 일일 튜너가 30일간 반복 권고한 position_ratio 0.166→0.10/0.12 와 daily_loss_limit −8→−4/−5/−6 은 전부 그 방향이므로 채택하지 않는다.",
 "recommended_weight":null,
 "weight_reasoning":"12왕복은 프롬프트 §6 문턱을 갓 넘긴 수준이고 기대값 마진이 3% 라 비중 조정 신호로 쓰기에는 잡음이 크다. 라이브 weight=0.40 은 사람이 오늘 정한 값이므로 자문이 뒤집을 근거가 없다.",
 "hypotheses":[
   {"claim":"kojiro 의 기대값은 장기 보유 구간에서만 나온다 — 청산을 조이면 전략이 죽는다","evidence":"30일 12왕복 보유일: 5일 이상이 10건이고 이익 4건(+11,500·+10,200·+9,600·+5,700)이 전부 보유 9~21일. 3일 만에 나온 왕복은 −20,000원으로 30일 최대 손실이다","test":"trail_atr(2.5)·stop_atr(2.0)을 흔들지 말고 30왕복까지 현행 관찰","required_sample":30,"confidence":0.75},
   {"claim":"단일 최대 손실(−20,000원)이 30일 총손익을 지배한다","evidence":"kojiro 30일 총 실현손익 +1,160원인데 최대 손실 1건이 −20,000원이다. 이 1건이 없었으면 +21,160원","test":"그 왕복의 청산 사유(하드손절 −8% / 갭 / 트레일링)를 로그에서 특정","required_sample":1,"confidence":0.9}],
 "needs_human_decision":[
   {"topic":"kojiro 포지션의 전략별 한도 초과가 7일 내내 반복된다","issue":"일일 로그 리포트 7건 전부에 '포지션이 전략별 한도를 초과' 계열 findings 가 있고 severity 가 high 인 날이 4일이다(09-02 kojiro 2건 · 09-03 3건 · 09-04 3건 · 09-07 5건)","evidence":"GET /api/log-reports?days=7 findings · GET /api/portfolio/risk account_gate.over_cap_count=1 (09-10 20:08 스냅샷)","options":["원인 규명 우선(1주 폴백 랏인지 ATR 배관 결함인지 로그로 분류)","K_ρ·K 는 §4 봉인 키이므로 자문 대상 아님 — 사람이 판단","현행 유지하고 관측만"]},
   {"topic":"kojiro 가 단독으로 예산 40% 를 점유한다","issue":"켜진 4전략 중 최대 비중이고 max_positions=6 · position_ratio=0.166 이라 불변식 곱이 0.996 으로 1.0 에 밀착해 있다","evidence":"GET /api/strategies kojiro.weight=0.40 · max_positions=6 · position_ratio=0.166 (곱 = 0.996)","options":["현행 유지(오늘 사람이 정한 값)","30왕복 확보 후 재검토"]}],
 "no_change_reason":"RR 2.06 이 손익분기 2.00 을 3% 마진으로 넘고 있다. 이 마진에서 청산·사이징을 조이면 기대값이 즉시 음수가 된다. 12왕복은 조정 근거로 부족하다.",
 "code_review_notes":null}
```

**해설.** kojiro 는 **승률 33%짜리 전략**이고 그게 정상이다. 30일 12왕복에서 이긴 4번이
+11,500 / +10,200 / +9,600 / +5,700원이고 전부 **9~21일 들고 간 것**이다. 반대로 3일 만에 끝난
왕복이 −20,000원으로 30일 최대 손실이었다.

이 모양에서 손절·트레일링을 조이면 승률은 오르고 **오른쪽 꼬리가 사라진다.** 손익비 2.06 이
손익분기 2.00 을 겨우 3% 마진으로 넘고 있으므로, 평균이익이 조금만 깎여도 기대값이 음수가 된다.
일일 튜너는 30일 동안 `position_ratio` 를 0.166→0.10 으로, `daily_loss_limit` 을 −8→−4 로
반복 권고했다. **채택하지 않는다.**

---

### 3.4 `bull_flag_breakout` — 무변경 (§5 동결 + 표본 3)

```json
{"strategy_id":"bull_flag_breakout","sample_status":"insufficient","closed_round_trips_30d":3,
 "recommended_params":{},
 "reasoning":"청산 왕복 3건(전부 손실, −3,400 / −3,880 / −1,350)이고 첫 체결 09-03 이후 영업일 6일이다. 프롬프트 §5 의 breakout_retention_minutes 동결 조건(왕복 ≥10 AND 영업일 ≥10)이 두 축 모두 미충족이라 그 키는 어떤 방향으로도 권고하지 않는다. 나머지 PARAM_RANGES 키도 완화 여지가 없다 — breakout_volume_mult 는 라이브 1.0 = 범위 하한(가장 느슨), min_market_cap 1e10 = 범위 하한, max_scan_stocks 4000 은 프롬프트 §5 의 사람 결정이다.",
 "recommended_weight":null,
 "weight_reasoning":"3왕복은 어떤 비중 판단에도 부족하다. 3전패는 표본이 아니라 잡음이다.",
 "hypotheses":[
   {"claim":"BFB 의 병목은 후보 생성이 아니라 장중 진입 전환이다","evidence":"funnel step99 prepared 가 5영업일 29/27/24/23/21 건으로 넉넉한데(GET /api/strategy-funnel/recent) 실제 매수는 09-03 이후 6건뿐이다. 후보는 충분하고 장중 돌파·거래량·추격상한(max_breakout_extension_pct=5.0) 관문에서 걸러진다","test":"장중 would_buy 관측(전환율 = 체결 ÷ prepared)을 10영업일 집계","required_sample":10,"confidence":0.7},
   {"claim":"3전패는 표본이 아니라 잡음이다","evidence":"평균손실 2,877원, 보유일 1·2·4일. 승률 0% 의 95% 신뢰구간은 n=3 에서 0~63% 로 아무것도 말하지 못한다","test":"10왕복까지 무개입 관찰","required_sample":10,"confidence":0.9}],
 "needs_human_decision":[
   {"topic":"BFB 의 prepared→체결 전환율이 낮은 원인이 관측되지 않는다","issue":"하루 21~29 후보에서 하루 1건 이하가 체결된다. 임계 엄격인지 추격상한인지 시간창(09:05~14:30)인지 구분할 로그가 번들에 없다","evidence":"funnel step99 5일치 29/27/24/23/21 vs GET /api/history BFB 매수 6건(09-03~09-10)","options":["장중 would_buy shadow 관측 신설(코드 변경 = 사람 결정)","현행 유지하고 10왕복까지 대기"]}],
 "no_change_reason":"§5 동결 조건 미충족(왕복 3 < 10, 영업일 6 < 10) + 나머지 튜닝 가능 키가 이미 범위의 가장 느슨한 끝에 있다.",
 "code_review_notes":null}
```

---

### 3.5 `volatility_breakout` — 무변경 (꺼짐 + 시정 진행 중)

```json
{"strategy_id":"volatility_breakout","sample_status":"sufficient","closed_round_trips_30d":45,
 "recommended_params":{},
 "reasoning":"30일 45왕복 기대값 −1,046원/왕복(승률 44.4%, RR 0.67 < 손익분기 1.25)으로 표본은 충분하고 기대값은 명백히 음수다. 그럼에도 파라미터를 권고하지 않는 이유는 둘이다. (1) 라이브 enabled=False · weight=0.0 이라 어떤 값을 넣어도 행위가 없다. (2) 손실의 위치가 파라미터가 아니라 알려진 결함에 있다 — 전 기간 왕복을 매수 시각으로 나누면 09:00~09:01:30 코호트 29건이 −110,900원으로 VB 전 기간 손실 −100,726원보다 크고 나머지 3구간 합은 +20,544원이다. 이 구간은 cycle262/264/265 가 다루는 [7] STCK_OPRC 시가 오염 구간이며 근본 시정(cycle265)이 아직 열려 있다. 결함 위에서 잰 파라미터로 튜닝하면 결함이 파라미터에 각인된다.",
 "recommended_weight":null,
 "weight_reasoning":"weight=0.0 이 이미 사람이 오늘 내린 결정이다. §4 에 따라 enabled 는 자문 대상이 아니다.",
 "hypotheses":[
   {"claim":"VB 의 음수 기대값은 진입 임계가 아니라 개장 90초 시가 오염이 만든 것이다","evidence":"09:02~09:30 코호트는 43왕복 승률 58.1% · 합계 +74,575원으로 양수다. 같은 파라미터·같은 전략인데 시각대만 다르다","test":"cycle265 시정 후 재활성해 09:02 이후 코호트만으로 30왕복 재측정","required_sample":30,"confidence":0.7},
   {"claim":"cycle262 의 90초 보류 게이트는 실제로 닫혔다","evidence":"history 전수에서 09:00:00~09:01:30 매수 체결의 마지막 날짜가 2026-09-04 다. 발효(09-07) 이후 4영업일 0건이고 라이브 open_entry_hold_secs=90 이 확인된다","test":"재활성 시 같은 구간 0건 유지 확인","required_sample":10,"confidence":0.9}],
 "needs_human_decision":[
   {"topic":"VB 재활성 조건","issue":"30일 표본의 절반(45왕복)을 낸 전략이 꺼졌다. 재활성 여부·조건이 정해져 있지 않다","evidence":"GET /api/strategies volatility_breakout.enabled=false · weight=0.0 (20:32 실측). 09-10 09:09 사용자 PUT 기록은 VB 8% 였다(_workspace/reports/2026-09-10_thursday_autonomous_work.md:65)","options":["cycle265(시가 스코프 근본 시정) 완료 후 재활성","현행 유지(영구 은퇴)","09:02 이후 진입만 허용하는 형태로 재설계 — 코드 변경 = 사람 결정"]}],
 "no_change_reason":"전략이 꺼져 있고, 손실 귀인이 파라미터가 아니라 진행 중인 결함 시정(cycle265)에 있다.",
 "code_review_notes":null}
```

---

### 3.6 `long_tail_volatility` — 무변경 (꺼짐)

```json
{"strategy_id":"long_tail_volatility","sample_status":"sufficient","closed_round_trips_30d":19,
 "recommended_params":{},
 "reasoning":"30일 19왕복 기대값 −1,707원/왕복으로 7전략 중 최악이고(승률 31.6%, 평균이익 1,867, 평균손실 3,356, RR 0.56 vs 손익분기 2.17) 표본도 충분하다. 그러나 라이브 enabled=False · weight=0.0 이라 파라미터 권고의 행위 효과가 0이다. 또한 VB 와 같은 개장 90초 시가 오염 구간을 공유하고(라이브 open_entry_hold_secs=90 동일 적용) 프리장 08:00~09:00 매수 경로까지 갖고 있어, 결함 시정 전 측정치로 튜닝하면 귀인이 섞인다.",
 "recommended_weight":null,
 "weight_reasoning":"weight=0.0 이 이미 사람 결정이다.",
 "hypotheses":[
   {"claim":"LTV 의 RR 0.56 은 손익분기 2.17 대비 격차가 커서 파라미터 조정으로 메우기 어렵다","evidence":"승률 31.6% 를 유지하려면 평균이익이 평균손실의 2.17배여야 하는데 실측은 0.56배다. 3.9배 개선이 필요하다","test":"재활성 시 프리장 진입분과 메인 진입분을 분리해 어느 쪽이 RR 을 깎는지 측정","required_sample":30,"confidence":0.65}],
 "needs_human_decision":[
   {"topic":"LTV 재활성 여부","issue":"기대값이 7전략 중 최악이고 표본도 19왕복으로 충분하다. 재활성한다면 어떤 조건에서인지가 비어 있다","evidence":"GET /api/strategies long_tail_volatility.enabled=false · 30일 −32,425원(history profit_loss 합)","options":["영구 은퇴","cycle265 시정 후 프리장 경로만 제거하고 재활성","현행 유지"]}],
 "no_change_reason":"전략이 꺼져 있어 파라미터 변경의 행위 효과가 0이다.",
 "code_review_notes":null}
```

---

### 3.7 `momentum` — 무변경 (꺼짐 — 그러나 전 기간 유일한 양수 전략)

```json
{"strategy_id":"momentum","sample_status":"insufficient","closed_round_trips_30d":3,
 "recommended_params":{},
 "reasoning":"30일 왕복이 3건뿐이라 §6 에 따라 파라미터·비중 모두 null 이다. 다만 표본 부족은 최근 30일에 한한 것이고, 전 기간 60왕복 기준으로는 기대값 +693원/왕복(승률 31.7%, 평균이익 8,010, 평균손실 3,253, RR 2.46 > 손익분기 2.16)으로 7전략 중 유일하게 누적 실현손익이 양수다(+41,594원). 그 전략이 지금 꺼져 있다.",
 "recommended_weight":null,
 "weight_reasoning":"30일 3왕복. §6 문턱 미달.",
 "hypotheses":[
   {"claim":"momentum 의 최근 거래 감소는 성과 악화가 아니라 후보 고갈이다","evidence":"funnel step99 가 09-09·09-10 모두 0건이다(GET /api/strategy-funnel/recent, 스냅샷 5건뿐이라 단계 분해도 없다). 상한가 모멘텀은 시장에 상한가 종목이 있어야 성립한다","test":"상한가 종목 수와 momentum step99 를 20영업일 대조","required_sample":20,"confidence":0.6}],
 "needs_human_decision":[
   {"topic":"전 기간 유일한 양수 기대값 전략이 비활성화됐다","issue":"momentum 은 60왕복 기준 RR 2.46 · 누적 +41,594원으로 7전략 중 유일하게 양수다. enabled 는 §4 봉인 키라 자문이 권고할 수 없으나, 이 비대칭은 사람이 알고 내린 결정인지 확인이 필요하다","evidence":"GET /api/history 전수 집계(momentum 60왕복 승률 31.7% RR 2.46 합계 +41,594원) vs GET /api/strategies momentum.enabled=false · weight=0.0","options":["재활성(비중은 사람이 결정)","의도된 비활성 — 사유를 결정 로그에 기록","후보 고갈이 원인이면 무해하므로 현행 유지"]}],
 "no_change_reason":"30일 3왕복으로 표본 문턱 미달이고 전략이 꺼져 있다.",
 "code_review_notes":null}
```

---

## 4. 운영 관찰 — 최근 7일 일일 리포트

출처 = `GET /api/log-reports?days=7` (09-02·03·04·07·08·09·10, `findings` 배열).

| 반복 findings | 등장 일수 | severity | 비고 |
|---|---:|---|---|
| **포지션이 전략별 한도를 초과** | **7 / 7** | high 4일 · medium 3일 | 09-02 kojiro 2건 · 09-03 3건 · 09-04 3건 · 09-07 5건 · 09-08 3건 · 09-09 1건 · 09-10 1건. 09-10 20:08 게이트 스냅샷 `over_cap_count=1` |
| **틱 신선도 저하 / stale 재등록 실패** | **7 / 7** | high 3일 | 09-07 은 ERROR 2,048건. cycle252(no_feed 종목 재등록 제외)가 이미 다루는 알려진 현상 |
| 잔고 조회 API HTTP 500 | 5 / 7 | medium | 재시도로 복구된다고 기록됨 |
| 시장 국면(레짐) 조회 실패 | 4 / 7 | medium | 레짐은 관찰 지표이므로 매매 영향 없음(루트 CLAUDE.md) |
| VCP 가 거래량 수축 단계에서 후보 0건 | 2 / 7 | low | §3.1 funnel 실측과 **일치**. 단 실제 지배 병목은 그 앞 단계(Pullback)다 |
| 체결통보↔주문기록 race / 중복 키 | 2 / 7 (09-04·09-09) | high | **cycle271 이 09-10 18:58 배포로 시정** — 다음 주가 첫 검증 |

**자문 관점 정리.**
- **한도 초과 7/7 이 유일하게 매매 산출물에 직접 닿는 반복 항목**이다. 다만 원인 축인
  `max_lot_units`(K)·`max_lot_ratio_mult`(K_ρ)는 §4 봉인 키라 자문이 값을 권고할 수 없다.
  → 결정 항목 D3.
- 틱 신선도·API 500·레짐 실패는 매매 파라미터와 무관한 인프라 항목이라 이 자문의 대상이 아니다.

---

## 5. 이번 주 사람이 결정할 항목

| # | 항목 | 왜 지금인가 | 선택지 |
|---|---|---|---|
| **D1** | **비중 재배분 감사 공백 + VCP 20%** | 09-10 09:09 사용자 PUT 기록은 `momentum 5% / VB 8% / LTV 0% / donchian 17% / BFB 17% / VCP 11% / kojiro 42%` 인데(`_workspace/reports/2026-09-10_thursday_autonomous_work.md:65`), 20:32 라이브는 `0/0/0/0.20/0.20/0.20/0.40` 이다. **두 번째 변경의 기록이 어디에도 없다.** 그 결과 전 기간 체결 0건인 VCP 가 11%→20% 로 올라갔다 | ① 두 번째 변경이 의도된 것인지 확인하고 결정 로그에 기록 ② 의도치 않았다면 09:09 값으로 원복 ③ 현행 유지 |
| **D2** | **`vcp_breakout.last_pullback_max` 0.10 → 0.12** | 이번 주 유일한 권고. 코드 기본값 복원이며 방향은 완화. funnel 5일 실측에서 23건 중 11건이 이 값 하나에만 걸렸다 | ① 적용 ② 0.15(범위 상한)까지 완화 — 23건 중 18건 통과, 위험은 더 큼 ③ 보류 |
| **D3** | **포지션 한도 초과 7일 연속** | 일일 리포트 7/7 · high 4일. 원인 축(K·K_ρ)이 봉인 키라 자문이 값을 못 낸다 | ① 원인 분류 먼저(1주 폴백 랏인지 ATR 배관 결함인지) ② 임계 조정(사람 결정) ③ 관측만 유지 |
| **D4** | **cycle265(`[7] STCK_OPRC` 스코프 근본 시정) 착수 여부** | cycle262 의 90초 보류는 실측으로 닫혔지만(09-05 이후 해당 구간 체결 0건) 오염된 시가 값 자체는 그대로다. VB·LTV 재활성의 **선결 조건** | ① 이번 주말 착수 ② VB·LTV 를 계속 끈 채 보류 ③ 재활성 계획과 함께 결정 |
| **D5** | **`net_external_cashflow` 신뢰성** | 30행 중 |중앙값| 231,496원 · |최대| 1,598,444원 = 순자산의 63%. 이 값이 오염이면 `daily_profit_rate`·`cumulative_return_rate`(−5.74%)가 전부 오염이다. 09-10 보고서 D12 와 동일 사안 | ① 실제 입출금 여부 확인 ② 산식 점검 ③ 확인 전까지 수익률 지표 사용 중단 |
| **D6** | **momentum·VB·LTV 비활성의 사유 기록** | momentum 은 전 기간 유일한 양수 기대값(+41,594원, RR 2.46)인데 꺼졌다. `enabled` 는 §4 봉인 키라 자문이 뒤집을 수 없다 | ① 사유를 결정 로그에 남기고 유지 ② momentum 만 재활성 ③ 셋 다 재검토 |
| **D7** | **일일 튜너 `auto_apply_enabled` OFF 유지 확인** | 이번 주 실측 = 최근 147건 권고 중 조임 679 : 완화 13 = **98.1%**(프롬프트가 인용한 89.2% 보다 심하다). `applied` 는 147건 전부 `None` 이라 현재 자동 적용은 없다 | ① OFF 유지(권고) ② `_workspace/domain_consult/weekly_advice_auto_apply_20260910.md` 의 레벨 0 설계 검토 |

---

## 6. 다음 주 검증 계획 (2026-09-17 목 20:30)

| # | 검증 대상 | 측정 방법 | 성공 서명 | 필요 표본 |
|---|---|---|---|---|
| V1 | D2 적용 시 VCP funnel | `GET /api/strategy-funnel/recent?strategy_id=vcp_breakout` step7·step8·step99 | step7 생존이 현재 1~4 → **3~8**, step99 가 0.6건/일 → **1.5~3건/일** | 5영업일 |
| V2 | VCP 첫 체결 | `GET /api/history` `strategy=vcp_breakout` | 4개월 반 만의 첫 BUY. 1건이라도 나오면 배관 정상이 실증된다 | 1건 |
| V3 | cycle262 게이트 지속 | `history` 매수 체결 시각 `09:00:00~09:01:30` | **0건 유지**(현재 09-07 이후 4영업일 연속 0) | 5영업일 |
| V4 | cycle271 race 시정 | `GET /api/log-reports` findings 에서 "중복 키 / race" 항목 | 09-04·09-09 에 있던 high finding **소멸** | 5영업일 |
| V5 | donchian·kojiro 표본 증분 | `history` SELL 수 | donchian 15→**20+**, kojiro 12→**17+** 면 다음 주에 청산 축 판단 가능 | 각 5왕복 |
| V6 | 한도 초과(D3) | `GET /api/portfolio/risk` `account_gate.over_cap_count` + 일일 리포트 | 일수 7/7 → **감소**. 원인 분류가 끝났으면 그 결과 | 5영업일 |
| V7 | 계좌 오픈리스크 | `account_gate.open_risk_pct` / `open_risk_proxy_pct` | 관측 임계 4.0% 아래 유지(현재 실효 0.97% · 프록시 2.42%) | 상시 |

> **다음 주 자문이 스스로 지킬 것** — 이번 주 무권고로 둔 donchian·kojiro 는 V5 가 채워지면
> 청산 축을 **처음으로** 판단한다. 그때도 기대값이 양수라면 **무권고가 정답**이다.
> 표본이 늘었다는 사실 자체는 조정의 근거가 아니다.

---

## 7. 이 자문이 하지 않은 것

- 파라미터를 **적용하지 않았다**. `PUT`/`PATCH`/`DELETE` 를 한 번도 호출하지 않았다(리포터 자격은 GET 전용).
- `max_scan_stocks` 를 4000→500 으로 낮추라고 **권고하지 않았다**. 일일 튜너가 30일간 72회 권고한
  항목이지만 프롬프트 §5 의 사람 결정(2026-08-08)이다.
- 표본 0건·3건을 근거로 **비중을 깎지 않았다**(§6 금지 추론).
- `max_positions` · `buy_threshold` · `donchian_period` · `max_breakout_extension_pct` ·
  `atr_trail_mult` · `breakout_fail_n_days` · `max_lot_units` · `max_lot_ratio_mult` ·
  `sizing_mode` · `tradable_boards` · `cash_usage_ratio` · `enabled` 를 **권고하지 않았다**(§4 봉인 키).
  의견이 있는 것은 전부 §5 결정 항목으로 올렸다.
- BFB `breakout_retention_minutes` 를 **어느 방향으로도 권고하지 않았다**(§5 동결, 왕복 3<10 ∧ 영업일 6<10).

### 수집 실패 기록

| 호출 | 결과 |
|---|---|
| `GET /api/strategy-funnel/recent` (인자 없음) | **422** `strategy_id` 필수 → 전략별 7회 재호출로 전건 수집 성공 |
| 그 외 8개 엔드포인트 | 전부 200 |

---

*작성 = 주간 파라미터 자문 루틴 (목 20:30 KST) · 읽기 전용 · 자동 적용 없음*
