# 주간 파라미터 자문 — 2026-09-10 (목)

> 작성 = 주간 자문 루틴(목 20:30 KST, 읽기 전용). **이 문서는 코드·DB·설정을 아무것도 바꾸지 않았다.**
> 이 파일 1개 외에 리포에 손댄 것이 없다.
> 접속 = `GET https://auto.dkstock.cloud/health` → **200**(Basic Auth reporter, https).
> 모든 수치에 출처를 병기한다. 번들에 없는 것은 "번들에 없음"으로 적었다.
> **예상과 실측을 구분한다** — "실측"이라 적지 않은 판단은 코드 판독이거나 추정이다.
>
> 📌 **v3 (PR #21·#22 리뷰 반영)** — 초판의 수치·근거 지적 13건을 검증해 12건이 유효했다.
> 시정 내역은 §8 에 전부 적었다. **판정이 바뀐 전략이 셋(donchian·LTV·kojiro)이다.**

---

## 0. 이번 주 한 줄

권고하는 파라미터는 **딱 1개**다 — `vcp_breakout.last_pullback_max` **0.10 → 0.12**(코드 기본값 복원, **완화**).
나머지 6전략은 **무권고**다. 표본이 없거나(VCP 0·BFB 3·momentum 8), 전략이 꺼져 있거나(momentum·VB·LTV),
개선해야 할 축의 키가 **봉인 키**라 자문이 손댈 수 없다(donchian·kojiro).

⚠️ 그 1개의 **기대 효과도 작다**(step7 생존 +약 1.2건/일). 실제 일봉 재실행으로 확인한
VCP 병목의 **88%는 단조 수축 조건**이고 그 키는 튜닝 대상이 아니다 → 결정 항목 **D3'**.

**이번 주 진짜 소식은 권고가 아니라 판정이다** — 정본 지표(`GET /api/strategies/te`) 기준으로
가동 중인 `donchian_swing` 이 **열위(inferior)** 이고, 꺼져 있는 `long_tail_volatility` 가
**7전략 중 유일한 우위(superior)** 다.

---

## 1. 한 페이지 요약

**판정의 정본 = `GET /api/strategies/te`** (`src/engine/te_metrics.py::compute_te_rr`).
계약: 모집단 = `get_trade_pairs()` 의 **closed pair**(`(ticker, strategy)` 별 보유수량이 0으로
돌아올 때 1왕복 — 분할 매수·분할 매도는 가중평균으로 **한 왕복에 합산**), 창 = **청산일 기준 90일**,
승패는 **진입가 기준 수익률(`profit_rate`, %)** 부호, **필요RR = 패/승(`L/W`)**, RR 은
`min(W,L) ≥ 5` 일 때만 산출.

| 전략 | 라이브 | 왕복 n | 승률 | RR | 필요RR | TE% | **판정** | 표본등급 | 권고 |
|---|---|---:|---:|---:|---:|---:|---|---|---:|
| `momentum` | **꺼짐** w=0.0 | 8 | 37.5% | — | 1.67 | −1.53 | undecided | insufficient | **0** |
| `volatility_breakout` | **꺼짐** w=0.0 | 83 | 38.6% | 1.01 | 1.56 | −0.61 | **inferior** | normal | **0** |
| `long_tail_volatility` | **꺼짐** w=0.0 | 51 | 43.1% | 1.50 | 1.32 | **+0.27** | **superior** | normal | **0** |
| `donchian_swing` | 켜짐 w=0.20 | 22 | 31.8% | 0.50 | 2.14 | −2.26 | **inferior** | low | **0** |
| `bull_flag_breakout` | 켜짐 w=0.20 | 3 | 0.0% | — | — | −4.88 | undecided | insufficient | **0** |
| `vcp_breakout` | 켜짐 w=0.20 | **0** | — | — | — | 0.00 | undecided | insufficient | **1** ← 유일 |
| `kojiro` | 켜짐 w=0.40 | 17 | 29.4% | 1.77 | 2.40 | −0.91 | undecided | insufficient | **0** |

**권고 총계 = 1개, 방향 = 완화.** 일일 튜너(OpenAI)의 조임 편향(§4.1, 실측 98.1%)을 재생산하지 않았다.

> ⚠️ **가동 중 4전략 중 판정이 선 것은 donchian 하나이고 그것이 열위다.** 나머지 셋은
> 전부 `undecided`(BFB 3왕복·VCP 0왕복·kojiro 17왕복 < 등급 문턱 20). 즉 **오늘 이 계좌는
> 판정된 전략 하나가 지고 있고 나머지는 아직 모르는 상태**로 예산 100% 를 쓰고 있다.

### ⚠️ 라이브 값이 루틴 프롬프트 서술과 다르다

**규칙대로 라이브 값을 정본으로 썼다.** 20:32 KST `GET /api/strategies` 실측:

| 항목 | 프롬프트 §5 서술 | **라이브 실측** |
|---|---|---|
| `momentum` | (가동 전제) | `enabled=False`, `weight=0.0` |
| `volatility_breakout` | K_ρ 적용 대상(가동 전제) | `enabled=False`, `weight=0.0` |
| `long_tail_volatility` | K_ρ 적용 대상(가동 전제) | `enabled=False`, `weight=0.0` |
| `kojiro` | `weight≈0.19` | **`weight=0.40`** |
| donchian / BFB / VCP | (개별 언급 없음) | 각 **0.20** |

Σ(켜진 전략) = **1.00**. 09-10 09:09 사용자 PUT 기록(`momentum 5% / VB 8% / LTV 0% /
donchian 17% / BFB 17% / VCP 11% / kojiro 42%`, `_workspace/reports/2026-09-10_thursday_autonomous_work.md:65`)
과도 다르며 **두 번째 변경의 기록이 없다** → 결정 항목 **D1**.

---

## 2. 계좌 전체 관점

### 2.1 자산과 손익

| 항목 | 값 | 출처 |
|---|---|---|
| 순자산 | **2,553,398원** | `GET /api/performance/daily?days=30` 09-10 `total_asset` = `GET /api/portfolio/risk` `account_gate.net_asset` (2자 일치) |
| 예수금 | 1,535,476원 | 같은 곳 `deposit` |
| 이번 주 실현손익 (09-07~09-10, 4영업일) | **+9,600원** | `perf/daily` `daily_realized_pnl` 합 |
| 전주 실현손익 (08-31~09-04) | −28,200원 | 같은 곳 |
| 최근 30행 실현손익 합 | −94,145원 | 같은 곳 (07-30~09-10) |
| 30일 누적수익률 | −5.74% | `GET /api/performance/summary` |

**수익률 산식 (코드 실측, `src/engine/scheduler.py:3641-3645`)** —
`daily_profit_rate = daily_realized_pnl_total ÷ prev_total_asset × 100`,
`cumulative_return_rate` 는 그 값을 복리 누적한다. **`net_external_cashflow` 는 산식에 들어가지
않고 기록만 된다.**

> ⚠️ **그러므로 "현금흐름이 이상하니 수익률도 오염" 은 성립하지 않는다** — 초판의 그 문장은
> 철회한다(§8 C2). 다만 `net_external_cashflow` 가 30행 중 |중앙값| **231,496원** ·
> |최대| **1,598,444원**(순자산의 63%)으로 큰 것은 그 자체로 **진단이 필요한 사실**이다:
> 실제 입출금이었다면 분모 `prev_total_asset` 이 그만큼 움직였다는 뜻이고, 산식에 입출금
> 보정이 없으므로 **일별 수익률의 분모가 왜곡됐는지는 따로 확인해야 한다**. 산식 부산물이라면
> 수익률은 무해하고 이 필드만 못 믿는다. **어느 쪽인지 판별할 근거가 번들에 없다** → **D5**.
> 이 문서의 손익 판단은 전부 실현손익 합과 closed pair 로만 했다.

**⚠️ 손익 정의 2종이 서로 다른 값을 낸다 (신규 발견, D8)** — 같은 체결 이력에서
`trade_history.profit_loss` 행 합(= `daily_performance` 가 쓰는 값)과 closed pair 재계산
(= TE 대시보드가 쓰는 값)이 전 기간 **−110,737원 vs −177,710원**으로 **66,973원** 다르고,
그중 **VB 하나가 65,363원**(−100,726 vs −166,089)이다. 나머지 5전략은 합쳐 −1,610원이라
전략 전반의 반올림 문제가 아니라 **VB 국소 현상**이다.

### 2.2 노출과 오픈리스크

`GET /api/portfolio/risk` 본문은 전부 0 이지만 **노출이 0이라는 뜻이 아니다** — 20:32 조회
시점에 엔진이 이미 종료돼 있다(`GET /api/trading/status` `running=false` · `phase=idle` ·
`last_scan_time=19:59:22`). `scheduler.py:1045` 의 일일 종료 후 in-memory 포지션이 비고
`run_daily` 가 다음 영업일 08:20 에 재시작한다. **정상 야간 상태다.**

장중 실측치는 같은 응답의 게이트 스냅샷을 쓴다:

| 항목 | 값 |
|---|---|
| 평가 시각 | 2026-09-10 **20:08:20** KST (`age_secs=1457`, `stale=true`) |
| 보유 포지션 | **10** |
| Σ오픈리스크 (실효 / 프록시) | **0.97%** / **2.42%** of 순자산 |
| 관측 임계 / 차단 임계 | 4.0% / **null(미활성)** |
| 한도 초과 포지션 | **1건** |
| 게이트 판정 | `ok`, `reasons=[]` |

**20:08:20 스냅샷 기준으로는 계좌 노출이 여유롭다**(실효 0.97% = 관측 임계의 1/4).
⚠️ 그 스냅샷은 `stale=true`(조회 시각 20:32 기준 `age_secs=1457`)이고 그 사이 엔진이
종료됐으므로 **20:32 현재 노출을 보증하지 않는다** — 다만 종료 후에는 신규 진입이 없으므로
그 사이 노출이 늘었을 경로도 없다. 어느 쪽이든 이번 주 자문에서 리스크 축소를 권고할
계좌 차원의 근거는 없고, 계좌 전체 노출 레버 `cash_usage_ratio` 는 §3 에 따라 권고 대상이 아니다.

### 2.3 진입 시각대별 손익 — cycle262 검증

`GET /api/history` 627행을 §1 의 closed pair 규칙으로 묶고(전 기간 297왕복, 그중 VB **129왕복**)
**매수 시각**(첫 매수 체결)으로 나눴다. 경계는 cycle262 의 실제 창(`[09:00:00, 09:01:30)`)과
**정확히 일치**시켰다.

| 매수 시각대 | 왕복 | 승률 | 합계 손익 | 평균 |
|---|---:|---:|---:|---:|
| **09:00:00~09:01:29** | 22 | **13.6%** | **−68,800원** | **−3,127원** |
| 09:01:30~09:29:59 | 50 | 54.0% | −44,285원 | −886원 |
| 09:30:00~11:59:59 | 35 | 37.1% | −51,644원 | −1,476원 |
| 12:00:00~ | 22 | 31.8% | −1,360원 | −62원 |
| **합계** | **129** | 38.8% | **−166,089원** | −1,288원 |

네 구간 합이 VB 전 기간 합과 **정확히 일치**한다(모집단·경계 동일).

**읽는 법** — 개장 90초 코호트는 **승률이 13.6%로 압도적으로 낮고**(다음 구간 54.0%)
**왕복당 평균 손실이 3.5배**다(−3,127 vs −886). 전체 손실의 **41%(68,800/166,089)** 를
왕복 **17%(22/129)** 가 만들었다. 이것은 cycle262/264/265 가 지목한 그 구간이며,
이 자문의 독립 표본이 그 진단을 뒷받침한다.

> ⚠️ **다만 이것은 연관이지 인과가 아니다.** 포렌식 정본이 "조기(09:00~09:01:30) **전용**
> 결함" 가설을 **명시적으로 기각**한다 — 오염된 `[7]` 은 일-스코프 상수라 **대조군에도 존재**하고
> 위반이 **39~59/96**, 조기 구간은 "피해가 최대인 구간일 뿐"이며 90초 보류는 **지혈**로 규정된다
> (`_workspace/analysis/entry_price_0900_20260906/forensic.md:19,246-254`). 따라서
> **09:01:30 이후 코호트를 "오염되지 않은 대조군"으로 읽으면 안 된다.** 위 표는 "어느 구간의
> 피해가 가장 큰가"를 보여줄 뿐, "그 구간만 고치면 VB 가 낫는다"를 뜻하지 않는다.
> VB 의 열위를 파라미터가 아닌 결함으로 귀인하려면 **cycle265 로 정상 기준가를 확보한 뒤**
> 같은 시각대끼리 대조해야 한다.

> ⚠️ 초판은 이 코호트가 "VB 전 기간 손실보다 크다"고 썼다. **경계를 09:02 로 잘못 잡았고
> 모집단이 섞였다** — 철회하고 위 표로 대체한다(§8 C3).

**그리고 게이트는 실제로 닫혔다** — `history` 전수에서 `09:00:00~09:01:30` 구간 매수 체결의
**마지막 날짜는 2026-09-04** 다. cycle262 발효(09-07) 이후 09-07·08·09·10 **4영업일 연속 0건**이고,
라이브 `volatility_breakout.open_entry_hold_secs=90` · `long_tail_volatility.open_entry_hold_secs=90`
로 값도 확인된다. **예상이 아니라 실측이다.**

다만 **근본 시정(cycle265)은 아직 열려 있다.** 90초 보류는 지혈이고 오염된 `[7]` 값 자체는
그대로다. VB·LTV 가 꺼져 있는 지금은 무해하지만 **재활성 전 선결 조건**이다 → **D4**.

---

## 3. 시스템 사실 (라이브 우선)

- 종목당 매수금액 = `순자산 × cash_usage_ratio × (weight / Σweight_enabled) × position_ratio`.
  **weight 는 상대 비율** — 한 전략의 weight 를 낮추면 그 자금은 현금이 아니라 다른 전략으로 간다.
  `weight=0.0` 은 축소가 아니라 **비활성화**다. 계좌 전체 노출 레버는 `cash_usage_ratio` 이며
  자문 권고 대상이 아니다.
- 불변식 `position_ratio × max_positions ≤ 1.0`. `max_positions` 는 봉인 키.
- 사이징: donchian·kojiro 는 `sizing_mode="turtle"`. 랏 상한 2축 `max_lot_units`(K=2.0) ·
  `max_lot_ratio_mult`(K_ρ=2.5) 둘 다 봉인 키.
- 청산은 매수 보드와 무관하게 항상 작동. 프리장 청산 평가 보류 화이트리스트 = LTV 만.
- 레짐(dkstock)은 관찰 지표이며 매수를 차단하지 않는다.

---

## 4. 전략별 자문

### 4.1 `vcp_breakout` — 이번 주 유일한 권고

```json
{"strategy_id":"vcp_breakout","sample_status":"insufficient","closed_round_trips_90d":0,
 "recommended_params":{"last_pullback_max":0.12},
 "reasoning":"funnel 5일 실측에서 VCP 가 죽는 곳은 step 8(거래량 수축)이 아니라 step 7(Pullback 점진 수축)이다 — 베이스 검출 생존 24/32/22/28/38 이 step7 에서 1/1/2/1/4 로 줄어 통합 93.75%(135/144, 일자별 단순평균 93.90%)가 탈락한다. step7 은 세 술어의 AND(회수 [2,4] AND 직전 대비 폭 단조 감소 AND 마지막 폭 <= last_pullback_max)인데 그중 last_pullback_max 만 PARAM_RANGES 에 있다. 탈락 종목의 실제 일봉을 GET /api/stock-master/{ticker}/daily 로 받아 _detect_base + _check_pullback_sequence 를 라이브 파라미터로 재실행한 결과(23행), 폭 단독 위반은 6행뿐이고 0.12 에서 정확히 그 6행이 통과한다(010950 S-Oil 5일 연속 + 204620 글로벌텍스프리 1일 = 2종목). 0.15 로 더 완화해도 추가 통과는 0 이다. 라이브 0.10 은 코드 DEFAULT_PARAMS 0.12(vcp_breakout.py:126)보다 조여진 값이므로 이 권고는 신규 완화가 아니라 기본값 복원이며, 기대 효과는 step7 생존 +약 1.2건/일로 작다. 2차 병목인 volume_contraction_ratio 는 라이브 1.00 = PARAM_RANGES 상한이라 더 완화할 수 없다.",
 "recommended_weight":null,
 "weight_reasoning":null,
 "hypotheses":[
   {"claim":"VCP 의 체결 0건은 배관 결함이 아니라 step7 임계 엄격 때문이다","evidence":"funnel step1~6 은 매일 정상 통과(3583→1023→709→700→55→38, 09-10)하고 step7 에서만 89~97% 가 탈락한다. 탈락 사유가 조건별로 기록되고 step9/step99 가 값을 산출하므로 배관은 살아 있다(09-08 1건·09-10 2건 prepared 실측)","test":"last_pullback_max=0.12 적용 후 step7 생존 수와 step99 prepared 수를 10영업일 추적","required_sample":10,"confidence":0.8},
   {"claim":"step7 의 지배 병목은 last_pullback_max 가 아니라 단조 수축(strict, 등호 거부)이다","evidence":"회수가 [2,4] 안인 step7 탈락 51행 중 28행은 폭도 임계 이하라 남는 위반 술어가 단조뿐이고(코드상 연역), 나머지 23행은 실제 봉 재실행에서 17행이 단조도 함께 위반했다 = 45/51(88%). 단조 검사는 vcp_breakout.py:786-788 의 strict 비교이고 폭 검사(:791)보다 먼저 early-return 하므로 funnel 사유 문자열로는 구분되지 않는다","test":"pullback 폭 수열을 종목별로 덤프해 '거의 수축'(직전 대비 +5% 이내 반등) 비율을 오프라인 측정","required_sample":0,"confidence":0.9},
   {"claim":"0.12 로 완화해도 하루 prepared 는 3건을 넘지 않아 리스크 증가가 제한적이다","evidence":"step7 이 5일에 6행(2종목)만 늘고, 그 뒤 step8 통과율이 실측 09-08 1/2·09-10 2/4 = 약 50% 다. 현재 prepared 0.6건/일 → 추정 0.8~1.5건/일","test":"적용 후 10영업일 step99 일평균과 실제 체결 수","required_sample":10,"confidence":0.7}],
 "needs_human_decision":[
   {"topic":"step7 의 진짜 병목은 단조 수축이고 그 키는 튜닝 대상이 아니다","issue":"vcp_breakout.py:786-788 은 pullback 폭이 직전보다 반드시 작아야 한다(strict, 등호 거부). 대응 파라미터가 없어 자문이 손댈 수 없는데, 회수 조건을 통과한 탈락 51행 중 45행(88%)이 여기 걸린다","evidence":"28행은 폭도 임계 이하라 남는 위반 술어가 단조뿐(코드 연역) + 23행 실제 봉 재실행에서 17행 단조 위반 확인. 재실행은 GET /api/stock-master/{ticker}/daily 100일 + 라이브 파라미터로 순수 메서드 직접 호출, funnel 이 기록한 마지막 폭과 23/23 일치","options":["현행 strict 유지","등호 허용 또는 허용 오차(curr <= prev × 1.05) 도입 — 코드 + 매매 행위 변경이라 승인 + domain-consult 선행","pullback_count_max 4→5,6 확대(역시 PARAM_RANGES 밖)"]},
   {"topic":"D2 적용의 선결 조건 — VCP·BFB max_lot_ratio_mult 20.0 잔재","issue":"두 전략의 K_rho 는 cycle245 배포 직전 표본 보호용 임시값 20.0 이 DB 에 그대로다. D2 는 VCP 의 첫 진입을 여는 변경이므로, 복원 없이 적용하면 4개월 반 만의 첫 랏이 rho축 명목 상한이 꺼진 채로 나간다","evidence":"_workspace/00_URGENT_WORKLIST.md 결정표 항목 6 = 'max_lot_ratio_mult 20.0 -> 2.5 복원은 VCP 첫 진입 개방과 같은 사이클에서 반드시 동반' + 잔여 결함 2번 '최소한 VCP 진입 개방 전 2.5 복원'","options":["D2 와 같은 사이클에서 VCP·BFB K_rho 를 2.5 로 복원(권고)","K_rho 복원 없이는 D2 를 적용하지 않는다","D2 보류"]},
   {"topic":"volume_contraction_ratio 가 범위 상한에 붙어 있다","issue":"라이브 1.00 = PARAM_RANGES 상한(0.30~1.00)이자 코드 기본값 0.70 보다 이미 완화된 값이다. 2차 병목인데 자문이 더 완화할 수단이 없다","evidence":"09-04·09-07·09-09 는 step7 생존 1건을 step8 이 전부 탈락시켜 prepared 0 (funnel 실측). 09-09 일일 튜너는 오히려 0.8 로 조이라고 권고했다","options":["현행 1.00 유지","PARAM_RANGES 상한 재검토는 코드 변경 = 사람 결정","step7 완화 후 step8 통과율 10영업일 재측정 뒤 판단"]},
   {"topic":"체결 0건 전략이 예산 20% 를 점유한다","issue":"weight=0.20 인데 전 기간 왕복 0. allocate_funds 가 Σ 로 정규화하므로 이 20% 는 다른 전략이 못 쓰는 자금이다","evidence":"GET /api/strategies vcp_breakout.weight=0.20 · GET /api/strategies/te n=0","options":["step7 완화 후 10영업일 관찰하고 그때 재검토","즉시 축소(자문은 권고하지 않는다 — 표본 0으로 비중을 깎는 것은 §6 금지 추론)","현행 유지"]}],
 "no_change_reason":null,
 "code_review_notes":"last_pullback_max 는 PARAM_RANGES (0.03, 0.15) 안이고 INT_PARAMS 가 아니며 봉인 키 목록에 없다. funnel 의 step7 탈락 사유 문자열은 세 술어의 AND 를 통째로 서술하고 회수·마지막 폭을 검사 이전에 무조건 기록하므로(vcp_breakout.py:776-779) 어느 술어가 탈락시켰는지 로그만으로는 구분되지 않는다. 관측 개선 후보(코드 변경, 이번 권고 아님) = 탈락 사유에 실패한 술어명 병기."}
```

**해설.** VCP 는 4개월 반 동안 **한 번도 사지 못했다**. 그런데 예산의 20% 를 들고 있다.
"거래가 없으니 비중을 줄이자"는 §6 이 금지한 추론이고 그렇게 권고하지 않는다.
대신 funnel 을 열어 **어디서 죽는지** 봤다.

베이스(base)까지는 매일 22~38종목이 살아 오는데, 그다음 "Pullback 이 점점 얕아지는가"
관문에서 **93.75%가 잘린다**(135/144, 일자별 단순평균 93.90%). 그 관문은 세 조건의 AND 다 — ① 되돌림 횟수 2~4회
② 매번 직전보다 얕아질 것 ③ **마지막 되돌림 폭 10% 이하**. ①②는 범위 밖이고 ③만 조정 가능하다.

**여기서 로그만으로는 답이 안 나온다.** 탈락 사유 문자열은 세 조건을 통째로 나열하고,
회수와 마지막 폭은 **어느 검사도 하기 전에 무조건 기록된다**(`vcp_breakout.py:776-779`).
게다가 ② 단조 검사(`:786-788`)가 ③ 폭 검사(`:791`)보다 **먼저** 걸러내고 빠져나간다.
즉 "회수 OK · 폭 11%" 라고 적힌 줄은 ③에 걸린 건 맞지만 **②에도 걸렸는지는 로그에 없다.**

그래서 **실제 일봉을 받아 술어를 직접 다시 돌렸다**(절차는 §7). funnel 이 기록해 둔
마지막 폭과 재실행 값이 **23행 전부 일치**해 재현이 충실함을 먼저 확인했다. 결과:

| 구분 | 행 | 0.12 에서 | 0.15 에서 |
|---|---:|---|---|
| ③만 위반 (폭 단독) | **6** | **통과** | 통과 |
| ②③ 동시 위반 (단조도 깨짐) | **17** | 탈락 | 탈락 |

**0.12 로 되돌리면 6행이 살아난다 — 종목으로는 둘뿐이다**(010950 S-Oil 5일 연속 +
204620 글로벌텍스프리 1일). **0.15 까지 열어도 추가 통과는 0** 이라 더 완화할 이유가 없다.
5일에 6행이니 step7 생존이 하루 약 1.2건 느는 셈이고, 그 뒤 거래량 수축 통과율이 실측
절반이라 **prepared 는 0.6건/일 → 0.8~1.5건/일** 정도다. 작다.

그리고 이 재실행이 **더 중요한 것**을 알려줬다. 회수 조건을 통과한 탈락 51행 중
**45행(88%)이 ② 단조 수축에 걸린다**. ②는 **등호도 거부하는 strict 비교**라 직전과 폭이
같기만 해도 탈락한다. **VCP 가 후보를 못 만드는 진짜 이유는 여기다.** 그런데 ②에는 대응
파라미터가 없어 자문이 손댈 수 없다 → **D3'**.

그렇다면 0.12 권고는 왜 남기나. **모험이 아니라 원위치**이기 때문이다 — 0.12 는 코드에
적힌 기본값이고(`vcp_breakout.py:126`, 주석 "사이클 48 — 0.08→0.12 한국 중소형주 변동성
현실화"), 라이브 0.10 은 최소 2026-08-11 부터 그보다 조여진 상태였다(`/api/recommendations`
`current_params` 22행 전부 0.1). 효과는 작지만 방향이 옳고 되돌리기 쉽다.
표본 규약과도 충돌하지 않는다 — §6 이 표본 부족 시 null 로 두라고 한 것은 **청산 축과
비중 축**이고 `last_pullback_max` 는 **후보를 만드는 진입 필터**다. 후보가 안 나오면
§6 이 요구하는 표본 10왕복은 **영원히 모이지 않는다.**

> 📌 **정직하게 밝힐 것** — 일일 튜너도 같은 값을 08-14·08-19·08-25 **세 번** 권고했고
> 세 번 다 `expired`(만료)로 끝났다. **`rejected`(기각)가 아니다.** 명시 기각이었다면
> 반복하지 않았을 것이다. 판단은 사람 몫이다.

⚠️ **이 한 키로 VCP 가 살아나지는 않는다.** 병목의 88%는 그대로 남는다.

---

### 4.2 `donchian_swing` — 무권고, 그러나 **열위**다 (초판에서 판정 뒤집힘)

```json
{"strategy_id":"donchian_swing","sample_status":"sufficient","closed_round_trips_90d":22,
 "recommended_params":{},
 "reasoning":"정본 지표 실측 = 승률 31.8%, RR 0.50, 필요RR 2.14, TE −2.26%/왕복, verdict inferior. RR 이 손익분기의 1/4 수준이라 격차가 크다. 구조는 avg_win_pct 2.15% vs avg_loss_pct −4.32% — 이기는 거래를 너무 일찍 끊고 지는 거래를 크게 두는 전형적 서명이며, 20일 신고가 돌파 전략의 30일 보유일 중앙값이 2일(최대 8일)이라는 사실과 일치한다. 그런데 이 구조를 만드는 두 키(atr_trail_mult 라이브 1.8 vs 코드 기본 2.0, breakout_fail_n_days 라이브 2 = 구 범위 하한)는 전부 봉인 키라 자문이 권고할 수 없다. PARAM_RANGES 안에 남은 donchian 키(position_ratio·stop_loss_rate·daily_loss_limit·long_ma_period·volume_multiplier·min_market_cap·min_trade_amount)는 어느 것도 RR 축을 고치지 못하며, 일일 튜너가 30일간 반복 권고한 방향(전부 조임)은 RR 을 더 악화시킨다. 따라서 무권고이되 이것은 '괜찮다'가 아니라 '자문이 손댈 수 있는 키가 없다'는 뜻이다.",
 "recommended_weight":null,
 "weight_reasoning":"표본 등급이 low(n=22 < 50)이고 peer 비교 대상인 kojiro 는 insufficient 라 §6 의 'peer 양쪽 모두 문턱 통과' 조건이 성립하지 않는다. 비중은 건드리지 않는다.",
 "hypotheses":[
   {"claim":"donchian 의 우측 꼬리가 breakout_fail_n_days=2 와 atr_trail_mult=1.8 에 잘리고 있다","evidence":"avg_win_pct 2.15% 는 20일 신고가 돌파의 기대 이동폭에 비해 작고 avg_loss_pct −4.32% 의 절반이다. 30일 15왕복 보유일 중앙값 2일·최대 8일이며 이익 상위 3건이 hold=2d(+7,100) / 2d(+3,900) / 6d(+2,500) 로 2일 관문 근처에 몰려 있다. cycle223 주석이 이미 같은 진단(19왕복 MFE 대비 −12%·RR 0.47)을 기록해 뒀고 이번 90일 표본이 그것을 재확인한다","test":"breakout_fail_n_days 2→4, atr_trail_mult 1.8→2.0 을 각각 단독으로 두고 30왕복 비교(봉인 키 = 사람 결정, shadow 관측 선행 권장)","required_sample":30,"confidence":0.6},
   {"claim":"stop_loss_rate 튜닝은 행위를 바꾸지 못한다","evidence":"라이브 sizing_mode=turtle · stop_atr=2.0 이고 루트 CLAUDE.md 는 _entry_atr 스탬프 랏이 ATR 손절을 탄다고 못박는다. 튜너가 30일간 stop_loss_rate 조임을 63회 권고했지만 스탬프 랏에는 닿지 않는다","test":"청산 로그에서 손절 발화 사유를 ATR/고정% 로 분류","required_sample":20,"confidence":0.7}],
 "needs_human_decision":[
   {"topic":"가동 중 유일하게 판정이 선 전략이 열위인데 자문이 고칠 키가 없다","issue":"verdict inferior · RR 0.50 vs 필요RR 2.14. 개선 축(트레일링 배수·보유일 관문)이 전부 봉인 키라 주간 자문 체계 안에서는 구조적으로 방치된다","evidence":"GET /api/strategies/te donchian_swing · GET /api/strategies atr_trail_mult=1.8(코드 기본 2.0) · breakout_fail_n_days=2 · recommendation_engine.py PARAM_RANGES 주석(cycle223)","options":["atr_trail_mult 2.0 복원 + breakout_fail_n_days 2→4 를 사람이 결정(domain-consult 선행)","현행 유지하고 50왕복까지 관찰","비중 축소 — 단, 그 자금은 현금이 아니라 VCP(왕복 0)를 포함한 나머지로 간다"]}],
 "no_change_reason":"PARAM_RANGES 안에 RR 축을 고칠 키가 없다. 조임 방향 권고는 RR 을 더 낮춘다.",
 "code_review_notes":null}
```

**해설.** 초판은 donchian 을 "가장 건강하다"고 썼다. **틀렸다.** 그 판단은 30일 창의
**원화** 실현손익(+2,530원)에 기댄 것이었는데, 정본 지표는 **90일 창의 진입가 기준 수익률**로
승패와 RR 을 재고 **필요RR 을 `패/승` 으로** 계산한다. 그 기준에서 donchian 은
승률 31.8% · RR 0.50 · 필요RR 2.14 · **verdict `inferior`** 다.

두 값이 갈리는 이유는 단순하다 — **이긴 거래의 금액은 컸지만 비율은 작았다.**
평균 이익 2.15% vs 평균 손실 −4.32%. 20일 신고가를 사서 평균 2%에 나오는 것은
추세추종이 아니다. 그리고 그렇게 만드는 두 손잡이(`atr_trail_mult` 1.8, 코드 기본은 2.0 /
`breakout_fail_n_days` 2, 구 범위의 하한)는 **둘 다 봉인 키**라 내가 권고할 수 없다.

**그래서 무권고는 "괜찮다"가 아니라 "이 체계 안에서는 고칠 수 없다"는 뜻이다.** → **D3**

---

### 4.3 `kojiro` — 무권고 (판정 유보, 조이면 안 되는 구조)

```json
{"strategy_id":"kojiro","sample_status":"sufficient","closed_round_trips_90d":17,
 "recommended_params":{},
 "reasoning":"정본 지표 = 승률 29.4%, RR 1.77, 필요RR 2.40, TE −0.91%/왕복, verdict undecided, 표본등급 insufficient(n=17 < 20). §6 문턱(10왕복)은 넘겼지만 저장소 자신의 등급 기준은 아직 판정 불가로 본다. 구조는 추세추종의 정상형 — 30일 12왕복에서 이긴 4건이 전부 보유 9~21일이고 평균 이익 10.89% vs 평균 손실 −3.76% 다. 필요RR 2.40 에 RR 1.77 로 못 미치는 것은 승률이 낮기 때문이며, 이 형태에서 청산을 조이면 승률은 오르지만 오른쪽 꼬리가 잘려 RR 이 함께 떨어진다. 일일 튜너가 30일간 반복 권고한 position_ratio 0.166→0.10/0.12 와 daily_loss_limit −8→−4/−5/−6 은 전부 그 방향이라 채택하지 않는다.",
 "recommended_weight":null,
 "weight_reasoning":"표본등급 insufficient. 비중 조정 신호로 쓰기에 이르다. 라이브 weight=0.40 은 사람이 오늘 정한 값이므로 자문이 뒤집을 근거가 없다.",
 "hypotheses":[
   {"claim":"kojiro 의 기대값은 장기 보유 구간에서만 나온다 — 청산을 조이면 전략이 죽는다","evidence":"30일 12왕복 보유일: 5일 이상이 10건이고 이익 4건(+11,500·+10,200·+9,600·+5,700원)이 전부 보유 9~21일. 3일 만에 나온 왕복은 −20,000원으로 30일 최대 손실이다. 평균 이익률 10.89%는 7전략 중 최고","test":"trail_atr(2.5)·stop_atr(2.0)을 흔들지 말고 30왕복까지 현행 관찰","required_sample":30,"confidence":0.75},
   {"claim":"단일 최대 손실 1건이 30일 총손익을 지배한다","evidence":"kojiro 30일 실현합 +1,160원인데 최대 손실 1건이 −20,000원이다. 그 1건이 없었으면 +21,160원","test":"그 왕복의 청산 사유(하드손절 −8% / 갭 / 트레일링)를 로그에서 특정","required_sample":1,"confidence":0.9}],
 "needs_human_decision":[
   {"topic":"kojiro 포지션의 전략별 한도 초과가 7일 내내 반복된다","issue":"일일 로그 리포트 7건 전부에 '포지션이 전략별 한도를 초과' 계열 findings 가 있고 severity high 가 4일이다(09-02 kojiro 2건 · 09-03 3건 · 09-04 3건 · 09-07 5건)","evidence":"GET /api/log-reports?days=7 findings · GET /api/portfolio/risk account_gate.over_cap_count=1","options":["원인 규명 우선(1주 폴백 랏인지 ATR 배관 결함인지 로그 분류)","K·K_ρ 는 봉인 키이므로 자문 대상 아님 — 사람이 판단","현행 유지하고 관측만"]},
   {"topic":"kojiro 가 단독으로 예산 40% 를 점유하는데 판정은 아직 유보다","issue":"켜진 4전략 중 최대 비중이고 max_positions=6 · position_ratio=0.166 이라 불변식 곱이 0.996 으로 1.0 에 밀착","evidence":"GET /api/strategies kojiro.weight=0.40 · 곱 0.996 · GET /api/strategies/te tier=insufficient","options":["현행 유지(오늘 사람이 정한 값)","20왕복 확보 후 재검토"]}],
 "no_change_reason":"표본등급 insufficient + 구조가 저승률·고RR 이라 조임이 곧 열화다.",
 "code_review_notes":null}
```

**해설.** kojiro 는 **승률 29%짜리 전략**이고 그게 정상이다. 이긴 4번이 전부 9~21일 들고 간
거래였고 평균 이익률 10.89%는 7전략 중 가장 높다. 반대로 3일 만에 끝난 왕복이 −20,000원으로
30일 최대 손실이었다. 이 모양에서 손절·트레일링을 조이면 승률은 오르고 **오른쪽 꼬리가
사라진다.** 정본 등급이 아직 `insufficient` 이므로 판정도 유보한다.

---

### 4.4 `bull_flag_breakout` — 무권고 (§5 동결 + 표본 3)

```json
{"strategy_id":"bull_flag_breakout","sample_status":"insufficient","closed_round_trips_90d":3,
 "recommended_params":{},
 "reasoning":"왕복 3건(전부 손실, 평균 −4.88%)이고 첫 체결 09-03 이후 영업일 6일이다. breakout_retention_minutes 동결 조건(왕복 >=10 AND 영업일 >=10)이 두 축 모두 미충족이라 그 키는 어떤 방향으로도 권고하지 않는다. 나머지 PARAM_RANGES 키도 완화 여지가 없다 — breakout_volume_mult 라이브 1.0 = 범위 하한(가장 느슨), min_market_cap 1e10 = 범위 하한, max_scan_stocks 4000 은 사람 결정이다.",
 "recommended_weight":null,
 "weight_reasoning":"3왕복은 어떤 비중 판단에도 부족하다. 3전패는 표본이 아니라 잡음이다.",
 "hypotheses":[
   {"claim":"BFB 의 병목은 후보 생성이 아니라 장중 진입 전환이다","evidence":"funnel step99 prepared 가 5영업일 29/27/24/23/21 건으로 넉넉한데 실제 매수는 09-03 이후 6건뿐이다. 후보는 충분하고 장중 돌파·거래량·추격상한(max_breakout_extension_pct=5.0) 관문에서 걸러진다","test":"장중 would_buy 관측(전환율 = 체결 / prepared)을 10영업일 집계","required_sample":10,"confidence":0.7},
   {"claim":"3전패는 표본이 아니라 잡음이다","evidence":"승률 0%의 95% 신뢰구간은 n=3 에서 0~63% 로 아무것도 말하지 못한다","test":"10왕복까지 무개입 관찰","required_sample":10,"confidence":0.9}],
 "needs_human_decision":[
   {"topic":"BFB 의 prepared→체결 전환율이 낮은 원인이 관측되지 않는다","issue":"하루 21~29 후보에서 하루 1건 이하가 체결된다. 임계 엄격인지 추격상한인지 시간창(09:05~14:30)인지 구분할 로그가 번들에 없다","evidence":"funnel step99 5일치 29/27/24/23/21 vs GET /api/history BFB 매수 6건","options":["장중 would_buy shadow 관측 신설(코드 변경 = 사람 결정)","현행 유지하고 10왕복까지 대기"]}],
 "no_change_reason":"동결 조건 미충족(왕복 3 < 10, 영업일 6 < 10) + 나머지 튜닝 가능 키가 이미 범위의 가장 느슨한 끝에 있다.",
 "code_review_notes":null}
```

---

### 4.5 `long_tail_volatility` — 무권고, 그러나 **유일한 우위**인데 꺼져 있다 (초판에서 판정 뒤집힘)

```json
{"strategy_id":"long_tail_volatility","sample_status":"sufficient","closed_round_trips_90d":51,
 "recommended_params":{},
 "reasoning":"정본 지표 = 승률 43.1%, RR 1.50, 필요RR 1.32, TE +0.27%/왕복, verdict superior, structure_tag robust, 표본등급 normal. 7전략 중 유일하게 우위 판정이고 표본도 51왕복으로 충분하다. 그런데 라이브는 enabled=False · weight=0.0 이라 어떤 파라미터를 넣어도 행위가 없다. 또한 VB 와 같은 개장 90초 시가 오염 구간을 공유하고(open_entry_hold_secs=90 동일 적용) 프리장 08:00~09:00 매수 경로까지 갖고 있어, cycle265 시정 전 측정치로 튜닝하면 귀인이 섞인다. 따라서 무권고이고 쟁점은 파라미터가 아니라 재활성 여부다.",
 "recommended_weight":null,
 "weight_reasoning":"enabled 는 봉인 키다. weight=0.0 은 사람이 오늘 내린 결정이므로 자문이 뒤집지 않는다.",
 "hypotheses":[
   {"claim":"원화 기준과 비율 기준 판정이 LTV 에서 가장 크게 갈린다","evidence":"90일 정본은 TE +0.27%/왕복(superior)인데 30일 원화 실현합은 −32,625원이다. 즉 비율로는 이기고 금액으로는 지고 있다 = 이긴 거래의 랏이 작았거나 진 거래의 랏이 컸다","test":"LTV closed pair 를 매수금액 구간별로 나눠 승률·수익률 대조. 1주 폴백 랏(cycle245 컷오프 130,100원 부근) 비중 확인","required_sample":51,"confidence":0.6}],
 "needs_human_decision":[
   {"topic":"7전략 중 유일한 우위 판정 전략이 꺼져 있다","issue":"verdict superior · RR 1.50 > 필요RR 1.32 · 표본 51왕복(normal)인데 weight=0.0 이다. enabled 는 봉인 키라 자문이 권고할 수 없으나 이 비대칭은 확인이 필요하다","evidence":"GET /api/strategies/te long_tail_volatility(verdict=superior, structure_tag=robust) vs GET /api/strategies enabled=false","options":["재활성(비중은 사람이 결정)","cycle265 시정 후 재활성","의도된 비활성 — 사유를 결정 로그에 기록. 원화 실현합이 음수인 것이 사유라면 위 가설(랏 크기)을 먼저 확인"]}],
 "no_change_reason":"전략이 꺼져 있어 파라미터 변경의 행위 효과가 0이다.",
 "code_review_notes":null}
```

**해설.** 초판은 LTV 를 "7전략 중 최악"이라고 썼다. **정본 기준으로는 정반대다.**
초판의 근거는 30일 **원화** 기대값(−1,707원/왕복)이었는데, 90일 **비율** 기준으로는
TE +0.27%/왕복 · RR 1.50 > 필요RR 1.32 로 **유일한 `superior`** 다.

두 값이 갈린다는 사실 자체가 실마리다 — **비율로는 이기는데 금액으로는 진다**면
이긴 거래의 매수금액이 작았거나 진 거래가 컸다는 뜻이다. cycle245 가 09-04 에 LTV
1주 폴백 랏(000500, 설계의 4.23배)을 지목한 것과 같은 방향이다. 확인 전에는 재활성도
비활성 유지도 근거가 약하다.

---

### 4.6 `volatility_breakout` — 무권고 (꺼짐 + 시정 진행 중)

```json
{"strategy_id":"volatility_breakout","sample_status":"sufficient","closed_round_trips_90d":83,
 "recommended_params":{},
 "reasoning":"정본 지표 = 승률 38.6%, RR 1.01, 필요RR 1.56, TE −0.61%/왕복, verdict inferior, 표본 83왕복(normal). 표본은 7전략 중 가장 크고 판정도 명확하다. 그럼에도 파라미터를 권고하지 않는 이유는 둘이다. (1) 라이브 enabled=False · weight=0.0 이라 어떤 값도 행위가 없다. (2) 손실의 위치가 파라미터가 아니라 알려진 결함에 있다 — 전 기간 129왕복을 매수 시각으로 나누면 09:00:00~09:01:29 코호트 22왕복이 승률 13.6%·평균 −3,127원으로, 왕복 17%가 전체 손실의 41%를 만들었다. 다만 포렌식 정본은 오염이 그 구간 전용이라는 가설을 기각한다 — [7] 은 일-스코프 상수라 대조군에도 39~59/96 위반이 있고 조기 구간은 피해가 최대인 구간일 뿐이다(forensic.md:19,246-254). 즉 오염된 것은 특정 시각대가 아니라 표본 전체이고, 근본 시정(cycle265)은 아직 열려 있다. 결함 위에서 잰 파라미터로 튜닝하면 결함이 파라미터에 각인되므로, 이 83왕복은 파라미터 판단의 근거로 쓰지 않는다.",
 "recommended_weight":null,
 "weight_reasoning":"weight=0.0 이 이미 사람이 내린 결정이다. enabled 는 봉인 키다.",
 "hypotheses":[
   {"claim":"개장 90초 코호트에 손실이 집중된다는 것은 연관(association)이고, 이것만으로 VB 의 열위를 그 구간 탓으로 귀인할 수는 없다","evidence":"09:00 코호트 22왕복 승률 13.6% vs 09:01:30~09:29:59 50왕복 54.0% 로 격차는 크다. 그러나 포렌식 정본이 '조기 전용 결함' 가설을 명시적으로 기각한다 — 오염된 [7] 은 일-스코프 상수라 대조군에도 존재하고 위반이 39~59/96 이며, 90초 보류는 지혈로 규정된다(_workspace/analysis/entry_price_0900_20260906/forensic.md:19,246-254). 즉 후속 시각대는 깨끗한 대조군이 아니므로 시각 분할은 인과를 세우지 못한다","test":"cycle265 로 [7] 스코프를 시정해 정상 기준가를 확보한 뒤, 오염 전후 같은 시각대끼리 30왕복 대조","required_sample":30,"confidence":0.5},
   {"claim":"cycle262 의 90초 보류 게이트는 실제로 닫혔다","evidence":"history 전수에서 09:00:00~09:01:30 매수 체결의 마지막 날짜가 2026-09-04 다. 발효(09-07) 이후 4영업일 0건이고 라이브 open_entry_hold_secs=90 확인","test":"재활성 시 같은 구간 0건 유지 확인","required_sample":10,"confidence":0.9}],
 "needs_human_decision":[
   {"topic":"VB 재활성 조건","issue":"표본이 가장 큰 전략(83왕복)이 꺼졌다. 재활성 여부·조건이 정해져 있지 않다","evidence":"GET /api/strategies enabled=false · GET /api/strategies/te verdict=inferior · 09-10 09:09 사용자 PUT 기록은 VB 8% 였다","options":["cycle265 완료 후 재활성","현행 유지(영구 은퇴)","09:01:30 이후 진입만 허용하는 형태로 재설계 — 코드 변경 = 사람 결정"]},
   {"topic":"VB 에서만 손익 정의 2종이 65,363원 어긋난다","issue":"trade_history.profit_loss 행 합 −100,726원 vs closed pair 재계산 −166,089원. 나머지 5전략 합계 차이는 −1,610원이라 VB 국소 현상이다","evidence":"GET /api/history 627행 · get_trade_pairs 규칙 재구현 · §2.1","options":["VB 의 분할 체결·당일 재진입 이력을 열어 어느 정의가 맞는지 확정","daily_performance 와 TE 대시보드 중 하나로 정본 통일","현행 병존 유지(단, 두 화면 숫자가 다른 이유를 문서화)"]}],
 "no_change_reason":"전략이 꺼져 있고, 손실 귀인이 파라미터가 아니라 진행 중인 결함 시정(cycle265)에 있다.",
 "code_review_notes":null}
```

---

### 4.7 `momentum` — 무권고 (표본 부족)

```json
{"strategy_id":"momentum","sample_status":"insufficient","closed_round_trips_90d":8,
 "recommended_params":{},
 "reasoning":"정본 90일 창 왕복이 8건뿐이라 §6 에 따라 파라미터·비중 모두 null 이다. 그 8왕복은 승률 37.5% · TE −1.53%/왕복 · single_trade_dominant=true 로 한 거래가 지배한다. 전 기간(54왕복)으로 넓히면 실현합 +40,044원으로 7전략 중 유일한 양수지만, 그 이익은 90일 창 밖의 오래된 거래에서 나온 것이므로 현재 파라미터의 성적으로 읽으면 안 된다. 라이브는 enabled=False 이기도 하다.",
 "recommended_weight":null,
 "weight_reasoning":"90일 8왕복. §6 문턱 미달.",
 "hypotheses":[
   {"claim":"momentum 의 최근 거래 감소는 성과 악화가 아니라 후보 고갈이다","evidence":"funnel step99 가 09-09·09-10 모두 0건이다(스냅샷 5건뿐이라 단계 분해도 없다). 상한가 모멘텀은 시장에 상한가 종목이 있어야 성립한다","test":"상한가 종목 수와 momentum step99 를 20영업일 대조","required_sample":20,"confidence":0.6}],
 "needs_human_decision":[
   {"topic":"전 기간 유일한 원화 양수 전략이 비활성화됐다 — 단 근거는 약하다","issue":"전 기간 54왕복 실현합 +40,044원으로 7전략 중 유일한 양수다. 그러나 정본 90일 창에서는 8왕복·TE −1.53%·single_trade_dominant 라 '지금도 좋다'는 근거가 되지 못한다. enabled 는 봉인 키다","evidence":"closed pair 전 기간 집계(momentum 54왕복 +40,044원) vs GET /api/strategies/te(n=8, te_pct −1.53, single_trade_dominant=true) vs GET /api/strategies enabled=false","options":["의도된 비활성 — 사유를 결정 로그에 기록","후보 고갈이 원인이면 켜 두어도 무해(거래가 없으므로) → 재활성해 표본을 모은다","현행 유지"]}],
 "no_change_reason":"90일 8왕복으로 표본 문턱 미달이고 전략이 꺼져 있다.",
 "code_review_notes":null}
```

---

## 5. 운영 관찰 — 최근 7일 일일 리포트

출처 = `GET /api/log-reports?days=7` (09-02·03·04·07·08·09·10 `findings`).

| 반복 findings | 등장 일수 | severity |
|---|---:|---|
| **포지션이 전략별 한도를 초과** | **7 / 7** | high 4일 · medium 3일 |
| **틱 신선도 저하 / stale 재등록 실패** | **7 / 7** | high 3일 (09-07 ERROR 2,048건) |
| 잔고 조회 API HTTP 500 | 5 / 7 | medium |
| 시장 국면(레짐) 조회 실패 | 4 / 7 | medium (레짐은 관찰 전용이라 매매 영향 없음) |
| VCP 가 거래량 수축 단계에서 후보 0건 | 2 / 7 | low (§4.1 funnel 과 일치. 단 지배 병목은 그 앞 단계) |
| 체결통보↔주문기록 race / 중복 키 | 2 / 7 (09-04·09-09) | high — **cycle271 이 09-10 18:58 배포로 시정**, 다음 주가 첫 검증 |

한도 초과 7/7 이 유일하게 매매 산출물에 직접 닿는 반복 항목이다. 원인 축
(`max_lot_units`·`max_lot_ratio_mult`)은 봉인 키라 자문이 값을 권고할 수 없다 → **D6**.

### 5.1 일일 튜너(OpenAI)의 방향 편향 — 실측

`GET /api/recommendations` 147건에서 `current_params` 와 `recommended_params` 에 **둘 다** 있는
수치 키를 방향별로 셌다: **조임 679 : 완화 13 = 98.1%**(프롬프트가 인용한 89.2%보다 심하다).
상위 항목 = `position_ratio` 조임 111 · `daily_loss_limit` 조임 108 · `max_scan_stocks` 조임 72
(= 사람이 2026-08-08 에 4000 으로 정한 결정을 매일 되돌리려는 시도).

**자동 적용은 실제로 없다 (교차 확인 4종)** — `GET /api/integrations/auto-apply` → `enabled=false` ·
147건 `status` 분포 = `expired` 136 / `rejected` 7 / `pending` 4 (**`applied` 도 `applied_auto` 도 0건**) ·
`applied_params` 0건 · `applied_weight` 0건 · `applied_at` 0건.

---

## 6. 이번 주 사람이 결정할 항목

| # | 항목 | 요지 |
|---|---|---|
| **D1** | **비중 재배분 감사 공백 + VCP 20%** | 09:09 PUT 기록과 20:32 라이브가 다르고 **두 번째 변경의 기록이 없다.** 그 결과 전 기간 왕복 0인 VCP 가 11%→20% 로 올라갔다 |
| **D2** | **`vcp_breakout.last_pullback_max` 0.10 → 0.12** | 이번 주 유일한 권고. 코드 기본값 복원 · 방향 완화. 실제 일봉 재실행 결과 23행 중 **6행**(2종목)이 이 값 하나에만 걸린다. **효과는 작다**. **0.15 는 선택지가 아니다**(추가 통과 0 으로 실측). ⚠️ **선결 조건 있음 — D2' 를 먼저 읽을 것** |
| **D2'** | ⚠️ **D2 의 선결 조건 — VCP·BFB `max_lot_ratio_mult` 20.0 → 2.5 복원** | 두 전략의 K_ρ 는 cycle245 배포 직전 **표본 보호용 임시값 20.0** 이 DB 에 그대로 남아 있다. **D2 는 VCP 의 첫 진입을 여는 변경이므로, 복원 없이 적용하면 4개월 반 만의 첫 랏이 ρ축 명목 상한이 꺼진 채로 나간다.** 워크리스트가 이미 "VCP 첫 진입 개방과 **같은 사이클에서** 반드시 동반"으로 못박아 둔 항목이다(`_workspace/00_URGENT_WORKLIST.md` 결정표 ⑥ · 잔여 결함 2번) |
| **D3** | **donchian 이 열위인데 고칠 키가 봉인돼 있다** | verdict `inferior` · RR 0.50 vs 필요RR 2.14. 개선 축 `atr_trail_mult`(1.8, 코드 기본 2.0)·`breakout_fail_n_days`(2, 구 범위 하한) 둘 다 봉인 키 → 주간 자문 체계 안에서는 구조적으로 방치된다 |
| **D3'** | **VCP step7 단조 수축 조건(strict)** | 회수 조건 통과 탈락 51행의 **45행(88%)** 이 여기 걸린다. 등호도 거부하는 비교라 폭이 직전과 같기만 해도 탈락. **대응 파라미터 없음** = VCP 4개월 반 무체결의 진짜 이유 |
| **D4** | **cycle265(`[7] STCK_OPRC` 스코프 시정) 착수 여부** | 90초 보류는 실측으로 닫혔지만 오염된 시가 값 자체는 그대로. **VB·LTV 재활성의 선결 조건** |
| **D5** | **`net_external_cashflow` 진단** | 수익률 산식이 이 값을 쓰지 않는다는 것은 확인했다(§2.1). 남은 질문은 **실제 입출금이 있었는가** — 있었다면 분모 `prev_total_asset` 보정이 필요한지 별도 검증 |
| **D6** | **포지션 한도 초과 7일 연속** | 일일 리포트 7/7 · high 4일. 원인 축이 봉인 키라 자문이 값을 못 낸다. 원인 분류(1주 폴백 랏 vs ATR 배관 결함) 먼저 |
| **D7** | **꺼진 3전략의 사유 기록 — 특히 LTV** | LTV 는 **유일한 `superior`**(RR 1.50 > 필요 1.32, 51왕복)인데 꺼져 있다. momentum 은 전 기간 원화 양수지만 90일 표본은 8왕복뿐. VB 는 `inferior` 로 비활성이 정합 |
| **D8** | **손익 정의 2종 불일치** | 전 기간 −110,737원(행 합) vs −177,710원(closed pair), 차이 66,973원 중 **VB 가 65,363원**. 두 화면이 다른 숫자를 보여준다 |
| **D9** | **`auto_apply_enabled` OFF 유지 확인** | 실측 조임 편향 98.1% · 현재 `enabled=false` · 자동 적용 이력 0건. 유지 권고 |

---

## 7. 다음 주 검증 계획 (2026-09-17 목 20:30)

| # | 검증 대상 | 성공 서명 | 필요 표본 |
|---|---|---|---|
| V1 | D2 적용 시 VCP funnel | step7 생존 1~4 → **2~5**(+약 1.2건/일), step99 0.6 → **0.8~1.5건/일**. ⚠️ **다음 주(5영업일) 판독은 중간 읽기이며 가설을 확정하지 못한다** — §4.1 가설 2건이 `required_sample: 10`(영업일)이므로 **확정 판정은 2주 뒤(2026-09-24)**. 5일 시점에 값이 범위를 크게 벗어나면 그것만 즉시 재조사 | 확정 10영업일 (중간 5) |
| V1b | D3' 정량화(코드 변경 없이) | 탈락 종목 pullback 폭 수열을 덤프해 직전 대비 반등 5%·10% 이내 비율 산출 → D3' 판단 근거 | 0(즉시 가능) |
| V2 | VCP 진입 배관 | ⚠️ **BUY 1건은 "한 경로가 끝까지 통과했다"는 증거일 뿐 배관 정상 입증이 아니다**(간헐적 누락은 그대로 숨는다). 성공 서명 = `prepared → step99 → would_buy → order` 전환을 **5영업일 연속 집계**해 단계 간 누락이 없을 것. 첫 BUY 는 그 집계의 시작점이지 종료 조건이 아니다 | 5영업일 |
| V3 | cycle262 게이트 지속 | 09:00:00~09:01:30 매수 체결 **0건 유지**(현재 4영업일 연속 0) | 5영업일 |
| V4 | cycle271 race 시정 | 09-04·09-09 의 중복 키 high finding **소멸** | 5영업일 |
| V5 | donchian·kojiro 표본 증분 | `/api/strategies/te` n 이 donchian 22→**30+**, kojiro 17→**20+**(등급 문턱) | **donchian +8왕복 · kojiro +3왕복**(전략별로 다르다 — "각 5" 로 잡으면 donchian 은 27 에 그쳐 목표 미달로 **거짓 실패**가 난다). ⚠️ 하루 0~1왕복 유입이라 donchian 8왕복은 다음 주 1회로는 어렵다 = **2~3주 누적 지표** |
| V6 | 한도 초과(D6) | 등장 일수 7/7 → **감소** | 5영업일 |
| V7 | 계좌 오픈리스크 | 관측 임계 4.0% 아래 유지(현재 실효 0.97%) | 상시 |

> **다음 주 자문이 스스로 지킬 것** — 판정은 `/api/strategies/te` 를 **먼저** 읽고
> 시작한다. 이번 주 초판이 뒤집힌 이유가 그것을 나중에 봤기 때문이다.
> 그리고 kojiro 가 등급 문턱(20왕복)을 넘어도 **RR 이 필요RR 을 넘지 못하면 조이지 않는다** —
> 저승률·고RR 구조에서 조임은 개선이 아니라 열화다.

---

## 8. 초판에서 시정한 것 (PR #21 자동 리뷰 반영)

| # | 지적 | 검증 결과 | 조치 |
|---|---|---|---|
| **C1** | "청산 왕복"을 SELL 체결 행 수로 셌다 — `get_trade_pairs()` 는 분할 체결을 한 왕복으로 합친다 | **유효.** 전 기간 SELL 행 305 vs closed pair **297**. 30일 창에서는 우연히 일치했으나 정의가 틀렸다 | 판정 근거를 `GET /api/strategies/te`(정본 계약)로 전면 교체 |
| **C2** | `net_external_cashflow` 가 이상하다고 수익률이 오염됐다고 결론낼 수 없다 | **유효.** `scheduler.py:3641-3645` 실측 — `daily_profit_rate = 실현손익합 ÷ 전일자산`, 누적은 복리. 현금흐름 필드는 **산식에 없다** | 문장을 "현금흐름 진단 필요"로 낮추고 남은 위험(분모 왜곡)만 명시 |
| **C3** | 시각 구간 경계가 09:01:30 이 아니라 09:02 라 30초가 빠졌고 합이 안 맞는다 | **유효.** 경계 오류 + 모집단 혼재(버킷은 pair, 비교 대상은 행 합) | 경계를 `[09:00:00, 09:01:30)` 로 고치고 모집단을 pair 로 통일 → 네 구간 합이 −166,089원으로 **정확히 일치**. "전 기간 손실보다 크다"는 문장 철회(실제 41%) |
| **C4** | `applied=None` 만으로 자동 적용 없음을 결론낼 수 없다 | **유효.** | 교차 확인 4종 추가 — `auto-apply enabled=false` · status 분포(`applied_auto` 0건) · `applied_params`/`applied_weight`/`applied_at` 전부 0건 (§5.1) |
| **C5** | momentum 필요RR 2.16 은 보합을 패로 센 값. 계약은 `L/W ≈ 1.79` | **유효.** `te_metrics.py:141` `required_rr = loss / win` 확인 | 전 전략 필요RR 을 정본 값으로 교체 |
| **C6** | step7 `excluded_sample` 텍스트로 "폭만 위반"을 증명할 수 없다 — 단조 검사가 먼저 early-return 한다 | **유효.** 실제 일봉 재실행 결과 23행 중 **17행이 단조도 위반** | 6행으로 정정(초판 11행), 0.15 선택지 삭제, 단조 수축을 **D3'** 로 신설 |
| **C7** | D2 에 K_ρ=20 복원 선결 조건이 빠졌다 | **유효(안전).** 워크리스트가 "VCP 첫 진입 개방과 같은 사이클에서 반드시 동반"으로 이미 못박음 | **D2' 신설** + VCP JSON 결정 항목 추가 |
| **C8** | step7 탈락률 "평균 92%" 가 표시 수치와 불일치 | **유효.** 통합 135/144 = 93.75%, 일자별 단순평균 93.90% | 두 값 병기로 교체(2곳) |
| **C9** | 계좌 노출 결론이 근거보다 강하다(스냅샷 `stale=true`) | **유효.** | "20:08:20 스냅샷 기준"으로 한정 + 20:32 미보증 명시 |
| **C10** | V2 성공 서명이 "첫 BUY 1건"으로 약하다 | **유효.** | `prepared→step99→would_buy→order` 5영업일 연속 집계로 강화 |
| **C11** | **09:01:30 이후 코호트를 오염 없는 대조군으로 다뤘다** | **유효(가장 중요).** 포렌식이 "조기 전용 결함" 을 **명시적으로 기각** — `[7]` 은 일-스코프 상수라 대조군에도 **39~59/96** 위반이 있고 90초 보류는 **지혈**(`forensic.md:19,246-254`) | 시각 분할을 **연관**으로 격하(인과 주장 철회), §2.3 에 경고 박스 추가, VB 가설 재작성(confidence 0.7→0.5) + 검증 방법을 "cycle265 시정 후 같은 시각대끼리 대조" 로 교체 |
| **C12** | V5 표본 목표와 "각 5왕복" 이 산술 불일치 | **유효.** donchian 22→30 은 **+8**, kojiro 17→20 은 **+3** | 전략별로 분리 표기 + 하루 0~1왕복 유입이라 **2~3주 누적 지표**임을 명시 |
| **C13** | V1 이 5영업일로 10영업일 가설을 판정한다 | **유효.** §4.1 가설 2건이 `required_sample: 10` | V1 을 **중간 읽기**로 격하하고 확정 판정을 **10영업일(2026-09-24)** 로 명시 |

**판정이 바뀐 전략** — donchian(건강 → **열위**) · LTV(최악 → **유일 우위**) · kojiro(양수 → **판정 유보**).
**권고 자체는 초판과 같다**(VCP 1건). 방향이 옳고 되돌리기 쉬운 기본값 복원이기 때문이다.

---

## 9. 이 자문이 하지 않은 것

- 파라미터를 **적용하지 않았다**. `PUT`/`PATCH`/`DELETE` 를 한 번도 호출하지 않았다.
- `max_scan_stocks` 4000→500 을 **권고하지 않았다**(튜너가 72회 권고했지만 사람 결정).
- 표본 0건·3건을 근거로 **비중을 깎지 않았다**(§6 금지 추론).
- 봉인 키 12종(`max_positions`·`buy_threshold`·`donchian_period`·`max_breakout_extension_pct`·
  `atr_trail_mult`·`breakout_fail_n_days`·`max_lot_units`·`max_lot_ratio_mult`·`sizing_mode`·
  `tradable_boards`·`cash_usage_ratio`·`enabled`)를 **권고하지 않았다**. 의견은 전부 §6 으로.
- BFB `breakout_retention_minutes` 를 **어느 방향으로도 권고하지 않았다**(동결 조건 미충족).

### 수집 기록

| 호출 | 결과 |
|---|---|
| `GET /api/strategy-funnel/recent` (인자 없음) | **422** `strategy_id` 필수 → 전략별 7회 재호출로 전건 수집 |
| `GET /api/stock-master/{ticker}/daily?days=100` × 12종목 | 200 (§4.1 술어 재실행용) |
| `GET /api/strategies/te` · `GET /api/integrations/auto-apply` | 200 (v2 에서 추가) |
| 그 외 8개 엔드포인트 | 전부 200 |

### §4.1 재실행 방법 (재현 가능하도록 명시)

1. `GET /api/stock-master/{ticker}/daily?days=100` → 각 행의 `raw`(KIS 원본 키) 추출.
2. 스냅샷 날짜 D 기준 재현을 위해 `bas_dd >= D` 인 봉 제거(= 그날 아침 prepare 가 본 창).
3. `GET /api/strategies` 의 **라이브** `vcp_breakout.params` 를 주입한 `VcpBreakoutStrategy` 로
   `_detect_base(candles)` → `_check_pullback_sequence(candles, base)` 를 임계 0.10 / 0.12 / 0.15 /
   1.0(단조 단독 판정용) 네 번 호출.
4. **검증** — funnel `excluded_sample` 의 "마지막 폭"과 재실행의 `base["last_pullback_pct"]` 가
   **23/23 일치**. 코드 변경 0줄(순수 메서드 호출), DB·KIS 접근 0.

---

*작성 = 주간 파라미터 자문 루틴 (목 20:30 KST) · 읽기 전용 · 자동 적용 없음*
