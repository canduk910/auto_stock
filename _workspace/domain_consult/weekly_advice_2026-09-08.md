# 주간 파라미터 자문 — 2026-09-08 (화)

> 작성 = 주간 자문 루틴(화 20:30 KST). **읽기 전용 산출물이다** — 코드·파라미터를 바꾸지 않았고
> 적용은 사람이 `PUT /api/strategies/{id}/params` 로 수동 반영한다.
> 접속 = `https://auto.dkstock.cloud/health` → **200** (HTTPS + Basic, 2026-09-05 TLS 전환 후 정상).
> 수집 시각 = 2026-09-08 20:30 KST 이후. 이 시각 엔진은 `running=false / phase=idle`
> (20:10 정산 완료 후) 이므로 `total_investment`·`positions`·`portfolio/risk` 는 모두 0 이다 —
> **결함이 아니라 정지 상태의 정상 스냅샷**이며, 예산은 매일 07:55 `_boot()` 에서 재배분된다.

---

## 0. 이번 주 권고의 성격 (먼저 읽을 것)

권고한 파라미터는 **3개뿐이고 전부 "완화"** 다 (조임 0 : 완화 3). 비중(weight) 권고는 **7전략 전부 null** 이다.

그 이유는 회피가 아니라 측정 결과다. 전 기간 확정 왕복 289건의 **1회당 수익률 평균은 −0.22%
(표준편차 6.63%p, t = −0.57)** 로, 계좌 전체가 "0 과 구별되지 않는" 구간에 있다. 전략별로도
donchian_swing 을 뺀 6개 전부 t 값이 ±1.6 안이다. 이 상태에서 비중을 옮기는 것은 잡음을 쫓는
일이고, 종전 일일 자동 자문(OpenAI, gpt-5.6-luna)이 **매일** weight 를 바꿔 권고해 온 것이
정확히 그 잡음 추종이다(§4 참조 — 09-01~09-08 8회 자문에서 같은 조임 세트가 반복됐고
`applied` 는 전건 `None`, 즉 한 번도 적용되지 않았다).

대신 이번 주의 실제 가치는 파라미터 숫자가 아니라 **§5 의 사람 결정 항목 9건**에 있다. 특히
`ρ축 랏 상한이 전략별 "최대 매수 가능 주가"를 만들고 있다`(D-1)와
`donchian 청산 2키가 코드 기본값보다 조여진 채 봉인됐다`(D-2)는 각각 독립된 실측 근거를 가진다.

---

## 1. 한 페이지 요약

| 전략 | 30일 확정 왕복 | 판정 | 30일 승률 | 30일 RR | 손익분기 RR | 30일 %합 | 30일 원 | 권고 키 |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `momentum` | 3 | insufficient | 33.3% | 0.98 | 2.00 | −6.21%p | −1,460 | **0** |
| `volatility_breakout` | 41 | sufficient | 48.8% | 0.88 | 1.05 | −6.55%p | −35,780 | **0** (무변경) |
| `long_tail_volatility` | 18 | sufficient | 27.8% | 0.65 | 2.60 | −29.29%p | −35,225 | **2** (둘 다 완화) |
| `donchian_swing` | 17 | sufficient | 41.2% | 0.57 | 1.43 | −22.47%p | +2,030 | **0** (허용 키에 지렛대 없음) |
| `bull_flag_breakout` | 2 | insufficient | 0.0% | — | — | −7.71%p | −4,750 | **0** (§5 동결 대상) |
| `vcp_breakout` | **0** | insufficient | — | — | — | — | — | **1** (완화, 후보 공급) |
| `kojiro` | 10 | sufficient | 30.0% | **3.24** | 2.33 | **+11.39%p** | −10,020 | **0** (무변경) |

- 출처 = `GET /api/history/pnl` 전 페이지의 `data.pairs`(297 페어, 그중 확정 289) 를 `sell_date ≥ 2026-08-09`
  로 거른 값. `RR = 평균이익% ÷ |평균손실%|`, `손익분기 RR = (1−승률) ÷ 승률`.
  **RR > 손익분기 RR 이면 기대값 양수**다. 30일 창에서 그 조건을 넘는 전략은 `kojiro` 하나다.
- `원` 열은 같은 페어의 `profit_loss` 합이다. **`kojiro` 는 %로는 +11.39%p 인데 원으로는 −10,020**
  이고 **`donchian_swing` 은 %로 −22.47%p 인데 원으로는 +2,030** 이다 — 부호가 반대로 뒤집힌다.
  원인은 §2.3 의 랏 크기 왜곡이며, 그래서 **이 보고서의 전략 비교는 전부 % 기준**이다.

---

## 2. 계좌 전체 관점

### 2.1 자산·손익

| 항목 | 값 | 출처 |
|---|---:|---|
| 순자산(최신) | **2,535,556 원** | `GET /api/performance/summary` → `data.latest_asset` |
| 30일 누적 수익률 | **−5.61%** | 같은 응답 `data.total_profit_rate` |
| 일평균 수익률 | −0.21% | 같은 응답 `data.avg_daily_profit_rate` |
| 전 기간 실현손익 | **−176,110 원 (−0.51%)** | `GET /api/history/pnl` → `data.summary.realized_total_krw` / `realized_rate_pct` |
| 전 기간 확정 왕복 / 승률 | 289건 / **38.0%** | 같은 `summary.closed_count` / `win_rate_pct` |
| 최근 30행 실현손익 합 | −115,345 원 | `GET /api/performance/daily?days=30` (2026-07-28~09-08) `data[].daily_realized_pnl` 합 |
| 같은 기간 외부 입출금 순합 | **+1,294,052 원** | 같은 응답 `data[].net_external_cashflow` 합 |
| 이번 주(09-02~09-08, 5영업일) 실현손익 | **−6,850 원** | 같은 응답 `data[]` 해당 5행 합 |

> ⚠️ **순자산 증가는 성과가 아니다.** 같은 30행에서 총자산은 1,157,348원(07-28)에서 2,535,556원
> (09-08)으로 늘었지만 그 차이(+1,378,208)보다 외부 입금 순합(+1,294,052)이 크고 실현손익은
> −115,345 다. 누적 수익률(`cumulative_return_rate`)은 −5.61% 로 이 입금을 이미 상쇄해 계산된 값이다.

### 2.2 노출·오픈리스크

`GET /api/portfolio/risk` → `data.total_notional_won` 0 / `data.total_open_risk_won` 0 /
`data.concurrent_positions` 0 / `data.by_sector` {}. **수집 시각(엔진 정지)의 값이므로 "노출 없음"이 아니라 "측정 불가"로 읽어야
한다.** 장중 노출의 대리 지표는 일일 로그 리포트 쪽에 있다 — 09-07 리포트 `ext_findings` 의
`계좌 게이트 open_risk_proxy_pct 3.82% — 경고선 4.0% 에 0.18%p 근접`(low) 이 이번 주 유일한
정량 기록이고, 같은 리포트가 `삼성화재우 1주 405,500원 = 순자산 15.7%, 보험 섹터 리스크 39.5%`
(09-04, medium) 를 남겼다. **한 종목이 순자산의 15.7% 를 차지한 것은 설계가 아니라 §2.3 의 결과다.**

### 2.3 이번 주 가장 중요한 계좌 사실 — 랏 크기가 설계가 아니라 주가로 정해진다

최근 30일 확정 왕복 91건의 매수 수량 분포:

| 수량 | 1주 | 2주 | 3주 | 5주 | 6주 |
|---|---:|---:|---:|---:|---:|
| 건수 | **78 (86%)** | 7 | 3 | 2 | 1 |

명목금액은 **최소 7,770원 ~ 최대 387,500원 = 50배 차이**(중앙값 103,200원)다. 즉 대부분의 랏은
`position_ratio` 가 정한 설계 랏이 아니라 **1주 폴백**이고, 그 랏의 크기는 그날 그 종목의
**주가**가 정한다. 결과가 §1 표의 부호 역전이다 — `kojiro` 30일 최대 손실은 SK가스 1주
245,500원(−8.15% = −20,000원)인데, 같은 기간 최대 이익 슈프리마 1주 48,200원(+19.92%)의
명목은 그 1/5 이다. **수익률로 이긴 매매가 금액으로 졌다.**

이 사실은 일일 운영 리포트가 7일 중 5일 HIGH 로 반복해 온
`포지션 N건이 전략별 자금/명목 한도를 초과`(08-31·09-02·09-03·09-04·09-07·09-08)와 같은 현상이다.

**그리고 여기서 파생되는, 이번 주 최대의 발견이 §5 D-1 이다** — cycle245 의 ρ축 랏 상한
(`max_lot_ratio_mult`, K_ρ)은 1주 폴백을 막기 위한 통제인데, 계좌가 2.5M원 규모라 그 컷오프가
사실상 **전략별 "최대 매수 가능 주가"** 로 작동한다. 컷오프를 넘는 주가의 종목은 1주도 못 사고
그냥 매수되지 않는다.

```
매수 가능 주가 상한 ≈ 순자산 × cash_usage_ratio × (weight ÷ Σweight) × position_ratio × K_ρ
```

라이브 값(순자산 2,535,556 · `cash_usage_ratio` **1.0** — `GET /api/strategies/system/cash-usage-ratio`
→ `data.ratio` (전문 `{"success":true,"data":{"ratio":1.0},"message":""}`) · Σweight_enabled = 1.00 ·
전 전략 K_ρ = 2.5) 대입:

| 전략 | weight | position_ratio | **매수 가능 주가 상한(원, 근사)** |
|---|---:|---:|---:|
| `momentum` | 0.05 | 0.25 | **≈ 79,200** |
| `long_tail_volatility` | 0.10 | 0.20 | **≈ 126,700** |
| `vcp_breakout` | 0.10 | 0.20 | **≈ 126,700** |
| `donchian_swing` | 0.15 | 0.20 | ≈ 190,100 |
| `bull_flag_breakout` | 0.15 | 0.25 | ≈ 237,700 |
| `kojiro` | 0.30 | 0.166 | ≈ 315,600 |
| `volatility_breakout` | 0.15 | 0.35 | ≈ 332,700 |

- 근사인 이유 = 실제 컷오프는 `int(K_ρ × int(예산 × position_ratio))` 로 두 번 절삭되고, 예산은
  **그날 07:55 `_boot()` 시점 순자산**으로 배분되므로 20:30 스냅샷과 다르다.
- 독립 실측 2건이 이 계산과 일치한다:
  1. 09-07 일일 리포트 `ext_findings` — `LTV 매수 수량 0 쿨다운 16건 — 예산 대비 고가주 후보로
     1주도 매수 불가`(medium). LTV 상한 126,700원과 정확히 같은 현상이다.
  2. 09-08 `vcp_breakout` 의 **유일한** 최종 후보 095610 의 `prev_close` 는 **152,700원**
     (`GET /api/strategies` → `data.vcp_breakout.targets["095610"].prev_close`)으로 VCP 상한
     126,700원을 넘는다 → 후보가 생겨도 **매수 불가**다.

---

## 3. 전략별 절

### 3.1 `volatility_breakout` — 표본 충분, 무변경

```json
{"strategy_id":"volatility_breakout","sample_status":"sufficient","closed_round_trips_30d":41,
 "recommended_params":{},
 "reasoning":"30일 승률 48.8%·평균이익 2.48%·평균손실 2.80% → RR 0.88 로 손익분기 RR 1.05 를 근소하게 밑돈다(출처 /api/history/pnl, sell_date≥2026-08-09). 그러나 전 기간 125왕복의 1회당 평균은 −0.13%p(표준편차 5.02, t=−0.29)로 0 과 구별되지 않는다. 소스 확인 결과 이 전략의 청산 경로는 stop_loss_rate 와 15:20 강제청산 둘뿐이고 익절·트레일링이 없어(src/engine/strategies/volatility_breakout.py::check_exit_signal) 평균이익은 파라미터가 아니라 시장의 일중 변동폭 공급으로 정해진다 — 실제로 월별 평균이익은 04월 6.38%→08월 2.40% 로 줄었는데 같은 기간 승률은 33.3%→55.2% 로 올랐다(시장 압축의 서명이지 조임의 결과가 아니다). 따라서 허용 키 어느 것도 RR 을 올리지 못한다.",
 "recommended_weight":null,"weight_reasoning":null,
 "hypotheses":[{"claim":"VB 의 평균이익 축소는 파라미터가 아니라 시장 일중 변동폭 축소 때문이다","evidence":"월별 avgW 6.38→7.73→3.14→3.63→2.40→2.98%, 같은 기간 WR 33.3→40.9→33.3→32.0→55.2→38.5%. 익절·트레일링 파라미터 부재(소스 확인)","test":"KODEX200 또는 후보 유니버스의 일중 (고가−저가)/시가 월별 중앙값을 avgW 와 나란히 놓는다","required_sample":0,"confidence":0.75},
  {"claim":"k_value_krx_main 을 1.3 에서 낮추면 진입이 이르러져 15:20 까지 남은 상승 여력이 커지고 avgW 가 오른다","evidence":"현재 k=1.3(코드 기본 1.0 대비 상향). 진입가가 시가+K×전일레인지 이므로 K가 클수록 잔여 상승폭이 작다 — 메커니즘 추론이며 관측 교차검증은 없다","test":"k 를 1.3 유지군 vs 1.0 전환군으로 나눠 2주씩 avgW·WR·RR 을 비교(같은 날 같은 종목이 아니므로 최소 2주 필요)","required_sample":30,"confidence":0.35}],
 "needs_human_decision":[{"topic":"VB 에 검출 가능한 우위가 있는가","issue":"125왕복 4.5개월에 걸쳐 1회당 평균 −0.13%p(t=−0.29). '지고 있다'가 아니라 '우위가 측정되지 않는다'이며, 거래비용이 있는 한 장기적으로는 완만한 출혈이다","evidence":"/api/history/pnl 125 페어, mean −0.13%p, sd 5.02, t=−0.29. 원 기준 전 기간 −89,226원(전략 중 최대) — 단 이는 VB 의 position_ratio 0.35 가 7전략 중 최대라 명목이 커서 생긴 것이지 %우위가 더 나빠서가 아니다","options":["현행 유지하고 N=200 까지 관측(권고: 기본)","weight 0.15 를 낮춘다 — 단 상대비율이라 그 자금은 현금이 아니라 다른 전략으로 간다","position_ratio 0.35→0.25 로 명목만 줄인다 — 단 §2.3 의 매수 가능 주가 상한이 332,700→237,700 으로 내려가 유니버스가 함께 잘린다","enabled=false 로 중단"]}],
 "no_change_reason":"허용 키(PARAM_RANGES) 중 RR 을 올릴 수 있는 지렛대가 없다. 일일 자동 자문이 반복 권고해 온 stop_loss_rate −5.0→−4.0 은 30일 41건 중 손절선에 닿은 4건에만 작용하고(−5.5/−5.1/−5.0/−5.0%) 평균이익은 전혀 올리지 못하므로 RR 을 더 낮춘다.",
 "code_review_notes":"failed_breakout_exit_enabled=false 로 꺼져 있다(코드 기본과 동일). 이 경로는 '돌파선 재이탈 2틱 연속 시 조기청산'으로 avgL 을 직접 줄이는 유일한 설계 수단인데, 켜면 RR 의 분모가 작아지므로 방향이 맞다 — 다만 진입 직후 되돌림에 즉발해 승률도 함께 깎을 수 있어 별도 검증 사이클이 필요하다. PARAM_RANGES 밖 키라 여기서는 권고하지 않는다."}
```

### 3.2 `long_tail_volatility` — 표본 충분, **완화 2건 권고**

```json
{"strategy_id":"long_tail_volatility","sample_status":"sufficient","closed_round_trips_30d":18,
 "recommended_params":{"trailing_stop_rate":-2.0,"overnight_stop_loss":-3.5},
 "reasoning":"30일 RR 0.65 가 손익분기 RR 2.60 에 크게 못 미치는데, 원인은 손실이 아니라 이익이다 — 평균손실은 3.01%(전 기간 3.40%)로 오히려 줄었고 평균이익이 5.03%(전 기간)에서 1.97%(30일)로 무너졌다. 월별로 avgW 는 06월 8.56%·07월 5.18% 에서 08월 1.81%·09월 3.80% 로 떨어졌고 최대이익도 06~07월 30.61%/31.60% 에서 08월 3.04% 로 잘렸다(출처 /api/history/pnl 65 페어 월별 집계). 이 전략의 전 기간 우위는 사실상 4건의 큰 이익(+12.25/+30.61/+14.79/+31.60%, 전부 05~07월)에서 나왔으므로 오른쪽 꼬리를 되살리는 것 외에 승률 개선으로는 손익분기를 넘길 수 없다. 라이브 trailing_stop_rate 는 −1.2 로 코드 기본값 −2.0 보다 40% 조여져 있고(src/engine/strategies/long_tail_volatility.py::DEFAULT_PARAMS), 급등주에서 −1.2% 되돌림은 잡음 구간이다 — 기본값 복원을 권고한다. overnight_stop_loss 도 라이브 −2.0 이 코드 기본 −5.0 보다 크게 조여져 있는데, 이 전략은 pre_nxt 보드를 쓰는 유일한 전략이고 프리장 청산 평가 보류 화이트리스트에 들어 있는 것 자체가 프리장 왜곡 틱을 신뢰하지 않는다는 뜻이므로 −2% 는 그 왜곡에 즉발할 수준이다. 전면 복원 대신 −3.5 로 한 걸음만 옮긴다.",
 "recommended_weight":null,"weight_reasoning":null,
 "hypotheses":[{"claim":"trailing_stop_rate −1.2 → −2.0 은 승률을 낮추고 RR 을 올린다(기대값 개선의 유일한 축)","evidence":"30일 이익 5건이 +0.44/+0.93/+1.63/+3.04/+3.80% 로 전부 트레일 폭의 1~3배 구간에 몰려 있다. 전 기간 5% 이상 이익 4건은 전부 05~07월","test":"복원 후 2주간 avgW·WR·RR 을 30일 기준선(1.97% / 27.8% / 0.65)과 비교. 승률이 내려도 RR 이 손익분기(승률에 따라 재계산) 위로 올라오면 성공","required_sample":15,"confidence":0.6},
  {"claim":"LTV 의 실제 제약은 청산이 아니라 §2.3 의 매수 가능 주가 상한 126,700원이다","evidence":"09-07 일일 리포트 ext_findings: 'LTV 매수 수량 0 쿨다운 16건 — 예산 대비 고가주 후보로 1주도 매수 불가'(medium). LTV 유니버스는 시총 500억 이상 전일 5% 이상 급등주라 상당수가 이 상한 위에 있다","test":"[ratio_notional_blocked] 마커의 LTV 행을 종목·주가와 함께 집계해 '상한 초과로 버려진 후보' 비율을 잰다","required_sample":10,"confidence":0.7}],
 "needs_human_decision":[{"topic":"LTV 의 매수 가능 주가 상한을 올릴 것인가","issue":"현재 상한 ≈126,700원. position_ratio 를 0.20→0.25 로 올리면 상한이 ≈158,500원이 되고 불변식 position_ratio × max_positions = 0.25 × 4 = 1.00 을 정확히 만족해 여전히 합법이다. 다만 30일 기대값이 음수인 전략의 랏을 키우는 것이라 청산 완화(위 권고)의 효과를 먼저 확인한 뒤가 순서다","evidence":"09-07 리포트 '매수 수량 0 쿨다운 16건'. 라이브 position_ratio 0.20 / max_positions 4","options":["청산 완화 2주 관측 후 재판단(권고)","position_ratio 0.20→0.25 즉시 상향","weight 0.10 을 올려 예산 자체를 키운다(다른 전략에서 가져와야 함)","현행 유지"]}],
 "no_change_reason":null,
 "code_review_notes":"intraday_stop_loss 는 라이브 −5.0 으로 코드 기본 −3.0 보다 이미 완화돼 있어 이번 권고에서 뺐다. gap_up_threshold 는 라이브 7.0 / 기본 10.0 으로 조여져 있으나 진입 필터라 청산 축 진단과 분리했고, min_market_cap 은 라이브 500억 / 기본 1,000억으로 완화돼 있어 후보 공급은 제약 요인이 아니다(09-08 funnel: universe_candidates 100 → final_prepared 85)."}
```

### 3.3 `donchian_swing` — 표본 충분, **허용 키에 지렛대 없음 (사람 결정으로 넘김)**

```json
{"strategy_id":"donchian_swing","sample_status":"sufficient","closed_round_trips_30d":17,
 "recommended_params":{},
 "reasoning":"7전략 중 유일하게 통계적으로 유의한 음의 기대값이다 — 전 기간 28왕복 1회당 평균 −2.35%p(표준편차 4.21, t=−2.95). 30일 RR 0.57 vs 손익분기 1.43. 문제의 위치는 명확하다: 20일 신고가 돌파 추세추종인데 전 기간 최대 이익이 **+5.23%** 이고 평균이익이 2.51%, 보유일수 중앙값 3일·최대 9일이다. 추세추종의 수익은 소수의 큰 왕복에서 나오는데 그 꼬리가 통째로 없다. 그런데 그 꼬리를 만드는 두 키(atr_trail_mult 라이브 1.8 vs 코드 기본 2.0, breakout_fail_n_days 라이브 2 vs 코드 기본 5)는 사이클 223 에서 PARAM_RANGES 에서 제거된 봉인 키라 이 자문이 권고할 수 없다. 허용 키 중 stop_loss_rate(라이브 −6.0, 기본 −7.0) 완화는 평균손실 3.75% 를 더 키워 RR 을 오히려 낮추므로 권고하지 않는다.",
 "recommended_weight":null,"weight_reasoning":null,
 "hypotheses":[{"claim":"보유일수를 제한하는 것은 트레일이 아니라 breakout_fail_n_days=2 다","evidence":"라이브 2 는 코드 기본 5 의 40% 다. '2영업일 안에 신고가를 못 만들면 청산'은 20일 채널 돌파가 되돌림을 소화할 시간을 주지 않는다. 관측된 보유일수 중앙값 3일이 이 값과 정합한다","test":"5 로 복원 후 보유일수 분포와 최대이익 분포를 28건 기준선(중앙값 3일, 최대 +5.23%)과 비교","required_sample":20,"confidence":0.65},
  {"claim":"30일 원 기준 +2,030 은 우위의 증거가 아니라 랏 크기 잡음이다","evidence":"같은 17건의 % 합은 −22.47%p 다. 최대 손실 팬오션 5주 31,400원(−9.24%)과 최대 이익 ISC 1주 162,500원(+4.37%)의 명목이 5배 어긋난다","test":"§2.3 의 1주 폴백 비율이 내려간 뒤 원 기준과 % 기준의 부호가 일치하는지 재확인","required_sample":20,"confidence":0.85}],
 "needs_human_decision":[{"topic":"donchian 청산 2키를 코드 기본값으로 복원할 것인가","issue":"atr_trail_mult 1.8→2.0, breakout_fail_n_days 2→5. 두 키 모두 사이클 223 에서 AI 튜닝 대상에서 제외됐지만 **라이브 값은 그때 조여진 상태 그대로 남아 있고 코드 기본값으로 되돌려진 적이 없다**. 제외의 취지가 '단기 손실 목적함수의 튜너가 추세추종을 데이트레이딩으로 변태시키는 것을 막는다'였다면, 그 변태의 결과물인 현재 값을 그대로 두는 것은 취지의 절반만 집행한 상태다","evidence":"라이브 params(GET /api/strategies → data.donchian_swing.params) atr_trail_mult=1.8 / breakout_fail_n_days=2 vs DEFAULT_PARAMS 2.0 / 5. 전 기간 28왕복 t=−2.95(7전략 중 유일한 유의 음수), 최대이익 +5.23%, 평균이익 2.51%, 보유 중앙값 3일","options":["두 키 모두 코드 기본값 복원(2.0 / 5) — 권고 방향이나 매매 행위 변경이라 승인 + domain-consult 선행 필요","breakout_fail_n_days 만 먼저 5 로 복원해 보유기간 축과 트레일 축을 분리 관측","현행 유지하고 N=50 까지 관측","전략 중단"]},
  {"topic":"sizing_mode=turtle 이 이 전략에 맞는가","issue":"라이브는 turtle 이지만 코드 기본은 position_ratio 다. 30일 17건 중 5주·2주 랏이 섞여 있는데 손실 최대건(팬오션 5주)이 가장 큰 명목이었다","evidence":"라이브 sizing_mode='turtle', risk_pct 0.005, max_lot_units 2.0 vs DEFAULT_PARAMS sizing_mode='position_ratio'","options":["현행 유지(권고 — 손절이 ATR 기반이라 터틀이 정합한다)","코드 기본으로 되돌린다","별도 사이클에서 _entry_atr 스탬프 비율을 먼저 실측한다"]}],
 "no_change_reason":"기대값을 되돌릴 수 있는 두 키가 전부 봉인 키(atr_trail_mult·breakout_fail_n_days)라, 허용 키에서 억지로 하나를 고르면 근거 없는 변경이 된다. 무변경 + 사람 결정 상신이 정직한 산출물이다.",
 "code_review_notes":"daily_loss_limit 도 라이브 −6.0 / 기본 −8.0 으로 조여져 있다. 09-08 funnel 은 5단계(신고가 돌파) 116→9, 6단계(EMA 우상향) 9→9, 7단계(거래대금) 9→5 로 거래량 필터가 후보를 절반 가까이 줄이지만, 기대값이 음수인 상태에서 후보를 늘리면 손실만 늘어나므로 volume_multiplier 완화는 권고하지 않는다."}
```

### 3.4 `kojiro` — 표본 문턱 도달(10), 무변경

```json
{"strategy_id":"kojiro","sample_status":"sufficient","closed_round_trips_30d":10,
 "recommended_params":{},
 "reasoning":"30일 승률 30.0%·평균이익 13.58%·평균손실 4.19% → RR 3.24 로 손익분기 RR 2.33 을 유일하게 넘긴다(30일 % 합 +11.39%p). 보유일수 중앙값 16일·최대 28일, 최대이익 +19.92% 로 '낮은 승률 + 큰 이익 + 긴 보유'라는 대순환 스윙의 설계 형태를 7전략 중 유일하게 실현하고 있다. 표본이 정확히 문턱(10)이고 전 기간 15왕복 기준으로는 1회당 −1.17%p(t=−0.54)로 아직 유의하지 않으므로, 지금 할 일은 조정이 아니라 표본을 더 쌓는 것이다. 어떤 청산 조임도 이 전략의 유일한 수익원인 오른쪽 꼬리를 직접 자른다.",
 "recommended_weight":null,"weight_reasoning":null,
 "hypotheses":[{"claim":"kojiro 의 원 기준 손실(−10,020)은 전략이 아니라 랏 크기 왜곡의 결과다","evidence":"30일 최대 손실 SK가스 1주 245,500원(−8.15%=−20,000원)의 명목이 최대 이익 슈프리마 1주 48,200원(+19.92%=+9,600원)의 5.1배다. 설계 랏은 ≈126,300원(순자산×0.30×0.166)인데 SK가스는 그 1.94배로 1주 폴백을 통해 들어갔다","test":"[ratio_notional_blocked]·[fallback_cap_skipped] 마커에서 kojiro 1주 폴백 랏의 명목 분포를 설계 랏과 대조","required_sample":10,"confidence":0.8}],
 "needs_human_decision":[{"topic":"breakeven_promote_atr 1.5 를 유지할 것인가","issue":"라이브 1.5 는 코드 기본 0.0(비활성)에서 켜진 값으로, +1.5 ATR 도달 시 손절선을 본전으로 끌어올린다. 설계대로 작동하는 유일한 전략의 오른쪽 꼬리에 걸린 유일한 조임이며 PARAM_RANGES 밖 키라 이 자문은 권고할 수 없다. 30일 이익 3건(+7.36/+13.46/+19.92%)이 모두 1.5 ATR 을 넘겨 살아남았으므로 지금 당장의 피해 증거는 없다 — '켜 두어도 무해했다'는 관측이지 '켜야 한다'는 근거는 아니다","evidence":"라이브 breakeven_promote_atr=1.5 vs DEFAULT_PARAMS 0.0. 30일 이익 3건 전부 +7% 이상","options":["현행 유지(권고 — 피해 증거 없음, 표본 부족)","0.0 으로 되돌려 꼬리를 완전 개방","N=25 까지 관측 후 재판단"]},
  {"topic":"F-3 갭 판정 오염(워크리스트 등재, 미착수)","issue":"_workspace/00_URGENT_WORKLIST.md '결정 대기' 3번 — risk.py:646 skip 목록에 kojiro 미포함으로 갭률 판정이 오염된다. 관측(cycle268)만 배포됐고 시정은 행위 변경이라 승인 대기 중이다. gap_up_skip_pct 5.0 / gap_down_skip_pct −4.0 이 잘못된 갭률로 평가되면 진입·익일청산 판정이 함께 틀어진다","evidence":"_workspace/00_URGENT_WORKLIST.md 결정 대기 3번(원문 그대로). 이 자문은 코드를 읽지 않고 워크리스트 기재 사실만 인용한다","options":["화~목 관측 판독 후 착수(워크리스트의 현재 계획)","즉시 착수","보류"]}],
 "no_change_reason":"30일 기대값이 유일하게 양수이고, 허용 키 중 이 형태를 개선할 수 있는 것이 없다. 표본 문턱을 갓 넘긴 시점의 조정은 잡음 추종이다.",
 "code_review_notes":"position_ratio 0.166 은 코드 기본 0.20 이 아니라 2026-08-08 불변식 지혈 결정값이므로 그대로 둔다(0.166 × max_positions 6 = 0.996 ≤ 1.0). max_positions 라이브 6 vs 기본 5 는 봉인 키라 언급만 한다. 09-08 funnel 은 5단계(ATR 밴드) 663→235, 7단계(스테이지1+3선 우상향) 235→69, 8단계(6→1 전환 인접) 69→16 으로 후보 공급은 건강하다."}
```

### 3.5 `momentum` — 표본 부족(3), 무변경

```json
{"strategy_id":"momentum","sample_status":"insufficient","closed_round_trips_30d":3,
 "recommended_params":{},
 "reasoning":"30일 확정 왕복 3건은 표본 규약 문턱(10) 미달이라 청산·비중 축 권고를 내지 않는다. 다만 배경 사실은 기록할 가치가 있다 — 전 기간 54왕복 기준 1회당 +0.67%p(t=+0.52), 합 +36.09%p, 원 +41,594 로 **원·% 양쪽 모두 양수인 유일한 전략**이고 RR 2.20 vs 손익분기 1.84 다. 문제는 성과가 아니라 공급이다: 04~06월 49왕복에서 07~09월 5왕복으로 말랐다. 09-08 funnel 은 universe_candidates 14 → rate_pass 13 → mcap_pass 9 → trade_amount_pass 8 → limit_up_excluded 1 → final_prepared 6 으로 배관은 정상 통과하고 입구(전일 급등 종목 14개)가 좁다 — 즉 원인은 (c) 배관 결함이 아니라 (b) 후보 없음이며, 상한가·급등주 공급은 시장 레짐이 정한다.",
 "recommended_weight":null,"weight_reasoning":null,
 "hypotheses":[{"claim":"momentum 의 우위는 전적으로 오른쪽 꼬리에 있고, 라이브 trailing_stop_rate −1.3 은 그 꼬리를 자른다","evidence":"전 기간 월별 최대이익 04월 +20.85% / 05월 +41.11% / 06월 +26.53%, 평균이익 7.07~15.51%. 라이브 trailing_stop_rate −1.3 은 코드 기본 −2.0 의 65% 이고 stop_loss_rate −5.0 은 기본 −7.5 의 67% 다","test":"공급이 돌아온 뒤 −2.0 복원 전후로 avgW·최대이익 분포 비교","required_sample":10,"confidence":0.6},
  {"claim":"§2.3 의 매수 가능 주가 상한 ≈79,200원(7전략 중 최저)이 공급 고갈에 더해 후보를 추가로 자른다","evidence":"weight 0.05(최저) × position_ratio 0.25 × K_ρ 2.5 × 순자산. 단 cycle245 배포일은 2026-09-04 라 07월에 시작된 고갈 자체는 설명하지 못한다 — 현재 시점의 제약일 뿐이다","test":"[ratio_notional_blocked] 의 momentum 행 유무를 확인","required_sample":5,"confidence":0.5}],
 "needs_human_decision":[{"topic":"전 기간 유일한 양(+)의 전략이 최저 비중(0.05)을 갖는 것이 의도인가","issue":"momentum 은 원 +41,594 / % +36.09%p 로 두 기준 모두 유일한 양수인데 weight 0.05 로 7전략 중 최저다. 표본 규약상 30일 3왕복으로는 비중 권고를 낼 수 없으나, 이 배치가 관측에 기반한 결정인지 아니면 종전 일일 자문의 반복 축소 권고(09-01~09-08 사이 0.02~0.03 반복 권고)가 누적된 결과인지는 사람이 확인해야 한다","evidence":"/api/history/pnl data.summary 및 54 페어 집계 mean +0.67%p, sum +36.09%p, 원 +41,594. /api/strategies data.momentum.weight=0.05. /api/recommendations 최근 8일 momentum recommended_weight 0.02~0.03 반복(applied 전건 None)","options":["현행 유지 — 07~09월 5왕복으로는 공급이 없어 비중이 무의미(권고: 표본이 돌아올 때까지 유지)","weight 상향 — 단 상대비율이라 다른 전략에서 가져와야 한다","공급 조건(buy_threshold 29, 봉인 키)을 별도 사이클에서 재검토"]}],
 "no_change_reason":"30일 확정 왕복 3건 < 문턱 10. 표본 규약에 따라 청산·비중 축 권고를 내지 않는다.",
 "code_review_notes":"라이브 daily_loss_limit −10.0 은 코드 기본 −5.0 보다 완화돼 있어 조임 드리프트의 예외다. gap_up_threshold 는 라이브·기본 모두 10.0 으로 일치한다."}
```

### 3.6 `bull_flag_breakout` — 표본 부족(2), 동결 준수

```json
{"strategy_id":"bull_flag_breakout","sample_status":"insufficient","closed_round_trips_30d":2,
 "recommended_params":{},
 "reasoning":"확정 왕복 2건(−1.40%, −6.31%)으로 문턱 10 미달이다. 그리고 breakout_retention_minutes=0(2026-09-03 진입 완화 실험)은 '청산 왕복 ≥10 그리고 영업일 ≥10 이 둘 다 충족될 때까지 어떤 방향으로도 권고 금지' 동결 대상이며 오늘 기준 왕복 2건·영업일 4일(09-03~09-08)로 둘 다 미충족이다. 후보 공급은 건강하다 — 최근 5영업일 final_prepared 25/22/29/27/24 로 안정적이고, 09-03 이후 매수 3건(09-03 001450, 09-04 452430, 09-07 114810·000500)이므로 체결률은 자문 실측 ≈0.5건/일과 정합한다. 즉 배관 결함이 아니라 정상적인 표본 형성 중이다.",
 "recommended_weight":null,"weight_reasoning":null,
 "hypotheses":[{"claim":"BFB 는 배관 결함 없이 표본을 쌓고 있다","evidence":"09-08 funnel: universe_union 3583 → 862 → 573 → 567 → pole_pass 243 → flag_pass 91 → volume_contraction_pass 24 → final_prepared 24. 09-03 이후 실체결 3건","test":"영업일 10일·왕복 10건 도달 시점(대략 2026-09-17 전후)에 동결 해제하고 재평가","required_sample":10,"confidence":0.8}],
 "needs_human_decision":[{"topic":"BFB·VCP 의 K_ρ=20 표본 보호 예외가 라이브에 없다","issue":"주간 자문 절차 §5 는 'BFB·VCP 는 K_ρ=20(표본 보호)'로 기재하지만 라이브 값은 두 전략 모두 max_lot_ratio_mult=2.5 다(7전략 전부 2.5). 라이브가 정본이라는 규칙에 따르면 표본 보호 예외는 현재 걸려 있지 않으며, 그 결과 §2.3 의 매수 가능 주가 상한이 두 전략에도 그대로 적용된다(BFB ≈237,700원 / VCP ≈126,700원)","evidence":"GET /api/strategies → data.<전략>.params.max_lot_ratio_mult 이 7전략 전부 2.5. 절차 문서 §5 기재와 불일치","options":["절차 문서 §5 를 라이브에 맞춰 정정(사실 정합)","DB/PUT 으로 BFB·VCP 를 20.0 으로 되돌려 표본 보호를 실제로 건다","현행 유지하되 두 전략의 표본 형성 기간을 늘려 잡는다"]}],
 "no_change_reason":"표본 문턱 미달 + breakout_retention_minutes 동결 조건 미충족. 어떤 방향의 권고도 절차 위반이다.",
 "code_review_notes":null}
```

### 3.7 `vcp_breakout` — 체결 0건, **후보 공급 완화 1건 권고**

```json
{"strategy_id":"vcp_breakout","sample_status":"insufficient","closed_round_trips_30d":0,
 "recommended_params":{"last_pullback_max":0.15},
 "reasoning":"전 기간 체결 0건이다. funnel 로 원인을 (a)임계 엄격 / (b)후보 없음 / (c)배관 결함으로 갈라 보면 (a) 이며, 그것도 두 관문에 몰려 있다 — 5단계 EMA 정렬이 668→41(94% 사멸), 7단계 Pullback 점진 수축이 22→2(91% 사멸)다(2026-09-08, GET /api/strategy-funnel/recent?strategy_id=vcp_breakout). 두 94% 관문이 직렬이라 생존률이 0.4% 수준이 되고, 실제로 최근 5영업일 final_prepared 는 0/0/0/0/1 이다. 배관은 정상이다(8·9·99 단계가 생존자를 그대로 통과시킨다). 7단계 배제 사유 샘플 20건을 분해하면 회수>4회 6건(30%), 회수 2~4회이나 마지막 폭>10% 6건(30%), 회수·폭 모두 통과했으나 단조 수축 실패 4건(20%), swing 미검출 3건(15%), 회수<2 1건(5%) 이다. 이 중 화이트리스트로 손댈 수 있는 가장 큰 덩어리가 last_pullback_max 이고, 라이브 0.10 은 코드 기본값 0.12 보다도 조여져 있다. 범위 상한 0.15 로 올려 후보 공급부터 확보한다.",
 "recommended_weight":null,"weight_reasoning":null,
 "hypotheses":[{"claim":"last_pullback_max 0.10→0.15 는 7단계 생존자를 1~2건에서 5~7건으로 늘린다","evidence":"09-08 배제 샘플 중 회수 2~4회이면서 마지막 폭이 10~15% 구간인 종목 5건(010950 11.0% / 078340 11.9% / 092730 11.8% / 251970 13.0% / 073240 14.0%)","test":"적용 후 5영업일 funnel 7단계 survived_count 를 기준선(1/1/1/1/2)과 비교","required_sample":0,"confidence":0.5},
  {"claim":"완화해도 체결은 0 으로 남는다 — 진짜 벽은 8단계와 매수 가능 주가 상한이다","evidence":"최근 5일 중 4일은 7단계 생존자 1건이 8단계(거래량 수축)에서 전부 탈락했다(089860 롯데렌탈 반복). 그리고 09-08 유일 최종 후보 095610 의 prev_close 152,700원은 VCP 상한 ≈126,700원(§2.3)을 넘어 1주도 살 수 없다","test":"완화 후 2주간 final_prepared>0 인 날의 후보 주가를 상한과 대조해 '후보는 생겼는데 못 산' 건수를 센다","required_sample":0,"confidence":0.7}],
 "needs_human_decision":[{"topic":"VCP EMA 정렬 3키가 화이트리스트 밖에서 94% 를 죽인다","issue":"라이브 ema_short/mid/long = 50/150/200 인데 코드 기본은 50/60/120 이다. 5단계에서 668→41(93.9% 사멸)이 이 정렬 조건이며 PARAM_RANGES 에 없어 이 자문이 권고할 수 없다. 7단계만 완화해도 5단계에서 이미 41개만 남으므로 체결이 생길지 불확실하다","evidence":"09-08 funnel 5단계 668→41. 최근 5일 41/45/50/57/41. 라이브 params vs src/engine/strategies/vcp_breakout.py::DEFAULT_PARAMS","options":["코드 기본(50/60/120)으로 복원해 후보 공급을 먼저 확보","150/200 을 유지하고 7단계 완화 효과만 2주 관측(권고: 한 번에 한 축)","중간값(50/100/150)으로 한 걸음","전략 중단하고 weight 0.10 을 회수"]},
  {"topic":"volume_contraction_ratio 가 범위 상한(1.00)인데도 생존자를 죽인다","issue":"라이브 1.00 은 PARAM_RANGES 상한(0.30~1.00)이고 코드 기본 0.70 보다 이미 최대로 완화된 값인데, 최근 5일 중 4일 7단계 생존자 1건을 8단계에서 전부 탈락시켰다. 즉 화이트리스트 안에서는 더 이상 손쓸 수단이 없다. 조건이 '마지막 5일 평균 거래량 < 베이스 직전 20일 평균 × 100%' 이므로 1.00 에서 탈락한다는 것은 후보들이 베이스 후반에 이미 거래량 팽창을 시작했다는 뜻이다 — 그렇다면 이 게이트의 의도(수축 확인)와 대상(이미 돌파 중인 종목)이 어긋나 있다","evidence":"09-02~09-07 4일 연속 089860 롯데렌탈 단독 탈락. 09-08 도 1건 탈락. 일일 리포트 09-03 medium 'vcp_breakout 스캔이 거래량 수축 단계에서 전부 탈락함' / 09-07 medium 'vcp_breakout 후보 0 — 8단계 거래량 수축에서 전멸'","options":["PARAM_RANGES 상한을 1.00 초과로 넓힌다(사실상 게이트 무력화 — 신중)","조건식을 '마지막 5일 < 베이스 평균' 이 아니라 '베이스 후반 < 베이스 전반' 으로 재정의(코드 변경, 별도 사이클)","현행 유지하고 5·7단계 완화 효과를 먼저 본다(권고)"]},
  {"topic":"pullback_count_max=4 + 엄격 단조 수축의 결합","issue":"7단계 배제 사유에서 회수 5~13회가 반복 등장한다(09-02 샘플: 신한지주 10회, 메리츠금융 11회, 삼성화재우 13회). 25~75일 베이스에서 ZigZag 가 그만큼의 swing 을 뽑아내는데 허용 회수는 2~4 다. 게다가 통과하려면 그 2~4개 폭이 **등호 없이** 단조 감소해야 해서(코드 확인) 회수 4일 때 무작위 순서 통과 확률은 1/24 수준이다. pullback_count_min/max 와 min_swing_atr_mult(라이브 1.0 vs 기본 0.5) 모두 PARAM_RANGES 밖이다","evidence":"src/engine/strategies/vcp_breakout.py 의 pullback 판정부(회수 범위 → 엄격 단조 → 마지막 폭 순서). funnel 배제 샘플의 회수 분포","options":["pullback_count_max 를 4→6 으로 넓힌다(코드/화이트리스트 변경 필요)","단조 수축을 '전체 엄격'에서 '마지막 폭 < 첫 폭'으로 완화","min_swing_atr_mult 를 올려 swing 검출 자체를 줄이면 회수가 범위 안으로 들어온다 — 조임처럼 보이지만 깔때기는 넓어지는 역설","현행 유지"]},
  {"topic":"체결 0건 전략이 weight 0.10 을 점유하는 것","issue":"vcp_breakout 은 전 기간 체결 0건인데 상대 비중 0.10 을 갖는다. weight 는 상대 비율이므로 이 10% 는 현금으로 남는 것이 아니라 **다른 전략이 쓸 수 있었던 몫**이다. 표본 규약상 이 자문은 비중을 권고하지 않는다(insufficient)","evidence":"GET /api/strategies → data.vcp_breakout.weight=0.10, 체결 이력 0건(/api/history data.trades 609행 중 vcp_breakout 0행)","options":["후보 공급 완화 2주 관측 후 재판단(권고)","weight 를 낮춰 다른 전략으로 돌린다 — 단 weight=0.0 은 축소가 아니라 비활성화다","현행 유지"]}],
 "no_change_reason":null,
 "code_review_notes":"base_depth_pct 는 라이브 0.35 / 기본 0.30 으로 이미 완화돼 있고 6단계(베이스 검출)는 41→22 로 병목이 아니라 손대지 않는다. breakout_volume_mult 라이브 1.2 / 기본 1.5 도 완화 방향이다. 즉 VCP 의 조임은 EMA 3키·last_pullback_max·min_swing_atr_mult 에 집중돼 있고, 그중 화이트리스트 안에 있는 것은 last_pullback_max 하나뿐이다."}
```

---

## 4. 운영 관찰 — 최근 7일 일일 리포트에서 반복되는 항목

출처 = `GET /api/log-reports?days=7` 의 `data[]` (7행: 08-31, 09-01, 09-02, 09-03, 09-04, 09-07, 09-08).
`findings` = 20:10 자동 분석(gpt-5.6-luna), `ext_findings` = Claude 일일 분석(09-04·09-07 2행만 존재).

| 반복 항목 | 빈도 | 등급 | 매매 영향 |
|---|---:|---|---|
| **포지션 N건이 전략별 자금·명목 한도 초과** | **5/7일** (08-31·09-02·09-03·09-04·09-07·09-08) | high/medium | §2.3 의 1주 폴백과 같은 현상. 이번 주 최우선 |
| WebSocket stale 종목 강제 재등록 실패 반복 | 4/7일 (08-31·09-03·09-07·09-08) | high | 손절 커버리지. cycle252 가 LOW 경로 churn 만 끊었고 근본(채널 리졸버)은 프로브 대기 중 |
| 잔고 조회 API HTTP 5xx | 6/7일 | medium/low | 전건 재시도 복구. 09-07 은 26회(오후 집중) |
| 틱 커버리지 65~70% 반복 | 2/7일 (09-02·09-04) | medium | 09-04 ext: 후보 35~38종목(구독 33%)이 종일 시세 미수신 |
| vcp_breakout 후보 0 / 거래량 수축 전멸 | 2/7일 (09-03·09-07) | medium | §3.7 과 같은 사안. 자동 분석도 독립적으로 같은 관문을 지목했다 |
| 장외 시장가 매도 거부(APBK) | 3/7일 (08-31·09-02·09-08) | medium | 폴백 경로 정상 동작 범위 |

09-07 `ext_findings` 의 HIGH 2건 — `[7] STCK_OPRC 프리장 오염 실측 확증 — 목표가 102/106 종목이
실제로 달라짐` 과 `장후 stale 재등록 실패 ERROR 2,048행 폭주` — 은 이미
`_workspace/00_URGENT_WORKLIST.md` 에 cycle265/F-2 로 등재돼 진행 중이므로 여기서 중복 상신하지
않는다. 다만 **첫 번째 항목은 이 보고서의 VB·LTV 진단에 직접 영향**을 준다: 목표가의 기준 시가가
오염돼 있었다면 진입가가 설계와 달랐고, 그만큼 §3.1·§3.2 의 avgW 해석에 잡음이 섞인다.
cycle262(09:00 직후 90초 진입 보류)의 첫 실전 효과와 함께 다음 주에 재확인해야 한다.

---

## 5. 이번 주 사람이 결정할 항목 (9건)

| # | 제목 | 근거 강도 | 관련 절 |
|---|---|---|---|
| **D-1** | ρ축 랏 상한이 전략별 "최대 매수 가능 주가"를 만든다 — momentum ≈79,200원 / LTV·VCP ≈126,700원 | 실측 2건 교차확인 | §2.3 |
| **D-2** | donchian 청산 2키를 코드 기본값으로 복원할 것인가 (atr_trail_mult 1.8→2.0, breakout_fail_n_days 2→5) | t=−2.95, 7전략 중 유일한 유의 음수 | §3.3 |
| **D-3** | VCP EMA 정렬 3키(50/150/200 vs 코드 50/60/120)가 668→41 로 94% 를 죽인다 | funnel 5일 연속 | §3.7 |
| **D-4** | VCP volume_contraction_ratio 가 범위 상한(1.00)인데도 생존자 4/5 를 죽인다 | funnel + 자동분석 2일 독립 지목 | §3.7 |
| **D-5** | VCP pullback_count_max=4 + 엄격 단조 수축의 결합(회수 5~13회가 배제 사유 최다) | 배제 샘플 분해 | §3.7 |
| **D-6** | 체결 0건 전략(VCP)이 상대 비중 0.10 을 점유하는 것 | 체결 이력 0행 | §3.7 |
| **D-7** | 전 기간 유일한 양(+)의 전략(momentum, +41,594원)이 최저 비중 0.05 를 갖는 것이 의도인가 | 289 페어 집계 | §3.5 |
| **D-8** | BFB·VCP 의 K_ρ=20 표본 보호 예외가 라이브에 없다(7전략 전부 2.5) | 라이브 params | §3.6 |
| **D-9** | VB 에 검출 가능한 우위가 있는가 (125왕복 t=−0.29, 원 기준 최대 손실원) | 125 페어 | §3.1 |

부수 관찰(결정 항목 아님):
- `GET /api/history` 에 `days` 쿼리 파라미터가 **없다**(`src/routes/history.py::trade_history` 는
  `page`/`size`/`ticker`/`strategy` 만 받는다). `?days=30` 은 조용히 무시되고 전 기간이 반환된다.
  이 절차 문서의 "최근 30일 체결" 지시는 `days` 로 달성되지 않으므로, 이번 보고서는 전 페이지를
  받아 `sell_date` 로 직접 걸렀다. 다음 주 루틴도 같은 방식이어야 한다.
- `GET /api/strategy-funnel/recent` 는 `strategy_id` 가 **필수**다(없으면 422). 전략별로 7회 호출했다.

---

## 6. 다음 주(2026-09-15) 검증 계획

| 대상 | 무엇을 볼 것인가 | 성공 판정 | 필요 표본 |
|---|---|---|---|
| LTV `trailing_stop_rate` −2.0 (적용 시) | avgW·WR·RR | avgW > 1.97%(기준선) 이고 RR > 그때의 손익분기 RR | 15왕복 |
| LTV `overnight_stop_loss` −3.5 (적용 시) | 프리장 구간 청산 건수와 그 평균손실 | 프리장 즉발 청산 감소, avgL 3.01% 이하 유지 | 10왕복 |
| VCP `last_pullback_max` 0.15 (적용 시) | funnel 7단계 `survived_count` | 기준선 1/1/1/1/2 대비 5영업일 중 3일 이상 ≥3 | 0 (funnel 즉시) |
| VCP 매수 가능 주가 상한 | final_prepared>0 인 날 후보 `prev_close` vs ≈126,700원 | "후보는 생겼는데 못 산" 건수를 명시적으로 집계 | 0 |
| BFB 동결 해제 조건 | 확정 왕복 수 · 09-03 이후 영업일 수 | 왕복 ≥10 **그리고** 영업일 ≥10 → 다음 주 해제 재판정 | 10왕복 |
| kojiro | 표본을 15→25 왕복으로 | RR 3.24 / 손익분기 2.33 관계가 유지되는지 | 25왕복 |
| momentum | 후보 공급(funnel `universe_candidates`) 회복 여부 | 일 14 → 30 이상 회복 시 표본 규약 재적용 | 10왕복 |
| 계좌 전체 | 1주 폴백 비율(현재 86%) | 60% 이하로 내려가면 원 기준 전략 비교가 다시 유효해진다 | 30왕복 |

---

## 7. 이번 주 권고 요약 (적용 대상 3키, 전부 완화)

| 전략 | 키 | 현재 → 권고 | 범위 | 코드 기본값 | 방향 |
|---|---|---|---|---|---|
| `long_tail_volatility` | `trailing_stop_rate` | −1.2 → **−2.0** | (−10.0, 0.0) | −2.0 (복원) | 완화 |
| `long_tail_volatility` | `overnight_stop_loss` | −2.0 → **−3.5** | (−15.0, 0.0) | −5.0 (부분 복원) | 완화 |
| `vcp_breakout` | `last_pullback_max` | 0.10 → **0.15** | (0.03, 0.15) | 0.12 (상한까지) | 완화 |

- 적용 수단 = `PUT /api/strategies/{strategy_id}/params` (즉시 반영). `strategy_config` SQL UPDATE 는
  다음 백엔드 재시작에서만 반영되므로 보유 중 장중에는 PUT 이 유일 경로다.
- 부분 PUT 은 안전하다 — 라우트(`src/routes/strategies.py::update_params`)가
  `if key in strategy.config.params` 로 **기존 키만 병합**한 뒤 전체를 저장하므로 나머지 키는 보존된다.
  위 3키는 전부 이미 라이브 params 에 존재하므로 그대로 통과한다.
  ⚠️ 반대로 **`config.params` 에 아직 없는 키는 조용히 버려진다**(응답은 `success=true`) — 신규 키를
  넣으려면 코드 배포가 선행돼야 하고, 그때 `save_params` 가 in-memory params 전체를 써서 미리 넣어 둔
  SQL 값을 덮는다. 이번 권고에는 신규 키가 없다.
- 비중(weight) 권고 = **7전략 전부 null**(변경 없음).

---

*이 문서는 읽기 전용 자문이다. 어떤 파라미터도 적용되지 않았고, 어떤 매매·설정 API 도 호출하지 않았다.*
