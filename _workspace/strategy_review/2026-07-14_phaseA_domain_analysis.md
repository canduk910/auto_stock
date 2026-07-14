# 매매전략 개선 심층분석 Phase A — 도메인 자문

작성: domain-expert (데이/스윙 트레이더 출신 컨설턴트)
일자: 2026-07-14
입력: 사용자 실측 데이터(신규 프로젝트 DB) + 코드/DB 교차검증
산출물 성격: **우선순위 개선안 백로그** (권고 — team-leader 최종 채택)

> ⚠️ 본 메모의 모든 권고는 **prepare/파라미터 계층** 한정. 매매 안전성 8영역
> (risk.on_tick / order_engine / realtime / auth / scanner 구독 / session / strategy_registry)
> 은 무관하다. 208/209와 동일한 blast radius (DB param + PARAM_RANGES + prepare 임계).

---

## 0. 실측 교차검증 (코드/DB 대조로 확정한 사실)

자문 전 사용자 제시 데이터를 코드·운영 DB(`qqylpfzlbfxnkrrdcsxr`, 신규 프로젝트)와 대조했다.
**브리핑과 어긋나는 항목을 먼저 명시** — 권고의 정확도를 위해 중요하다.

### 0-1. auto-apply ratchet 메커니즘 — 코드로 확정

`recommendation_engine.py::auto_apply_recommendations` (L976~):

```python
_CONSERVATIVE_KEYS = {stop_loss_rate, position_ratio, daily_loss_limit,
                      intraday_stop_loss, overnight_stop_loss,
                      stop_loss_main, stop_loss_pre_nxt}
_STOP_LOSS_KEYS    = {..., daily_loss_limit}   # 음수 키

# ② 자동 적용 게이트 (L1077~1084)
if k in _STOP_LOSS_KEYS:
    if float(v) > float(current_v):   # 손절/한도: 절대값 작아질 때만 = 조이기만
        is_conservative = True
elif k == "position_ratio":
    if float(v) < float(current_v):   # 비중: 작아질 때만 = 줄이기만
        is_conservative = True
```

**확정 — 사용자 진단 정확**:
- 손절/일일한도 키는 `float(v) > float(current_v)` = **절대값이 작아지는(조이는) 방향만** 통과.
- position_ratio 는 **작아지는 방향만** 통과.
- **하한 가드(floor) 없음** — `-0.8` 아래로도 계속 조여질 수 있음(다만 자문값이 그보다 조이길 권해야).
- **되돌리는(완화) 경로 없음** — 완화 자문은 `is_conservative=False` → 무시. 운영자가 수동 apply 해야만 복원.
- 이것이 **단조 조임(monotone ratchet)** 구조다. AI가 매일 조금씩 손절/한도를 조이면 시간에 걸쳐 누적되고, 되돌아오는 힘은 시스템 안에 없다.

### 0-2. 신규 프로젝트에서의 ratchet 실제 경로 — **auto-apply 아님, 수동 apply**

운영 DB 실측:
- `parameter_recommendations`: 259건 (2026-05-04 ~ 07-13), `status='applied_auto'` = **0건**.
- status 분포: applied 15 / partial 28 / pending 6 / expired 210.

→ **신규 프로젝트의 ratchet 은 auto_apply(자동) 가 아니라 수동 apply(applied/partial 43건)로 발생했다.**
   즉 `auto_apply_enabled` 는 현재 꺼져 있거나 미발화 상태다.

**이것이 권고에 미치는 함의(중요)**:
- 브리핑의 donchian 시계열(5/12 -6 → 6/02 -0.8)은 *구프로젝트* 통계다. 신규 DB엔 그 이력이 없다.
  다만 신규 DB의 **현재값**이 그 ratchet 결과를 그대로 상속(donchian daily_loss -0.8, stop -3.2)했다 →
  **현상(교살 상태)은 실재**, 원인 계보만 수동/자동 혼재.
- systemic 결함은 **여전히 유효**하다. 지금은 자동이 꺼져 있어 수동으로 조여졌지만,
  auto_apply 를 켜는 순간 동일 ratchet 이 *자동으로* 재개된다(A-1 P0 근거).
- AI 자문 UI가 "감액/조임만 원클릭 apply"를 반복 노출하면, 운영자 수동 apply 도
  구조적으로 조임 편향(완화 자문은 "무시"가 자연스럽고 조임 자문은 "안전하니 적용"이 자연스러움)을 가진다.

### 0-3. 전략별 현재 DB 값 — 확정 (브리핑 정정 포함)

| 전략 | 확정 현재값 | 브리핑 대비 정정 |
|---|---|---|
| donchian | daily_loss -0.8 / stop -3.2 / min_mcap **100억**(10000000000) / period 20 / ext **4.0**(209반영) / weight 0.12 | min_mcap = 100억 (브리핑 "3000억 원본 Q2=D 임시완화 100억" → 현재 100억 확정). box param 값은 DB 잔존하나 208로 필터 제거되어 **미사용**(무해) |
| VB | pos_ratio 0.5 / max_pos 2 / stop **-5**(복원됨) / daily_loss **-7**(복원됨) / k_krx 1.3 / weight 0.24 | stop/daily 이미 복원. k_period 15 |
| LTV | min_prdy 5 / intraday_stop **-5**(복원됨) / daily_loss **-7** / overnight **-2** / weight 0.18 / **reentry 쿨다운 키 없음** | 브리핑 "intraday -2" → DB **-5** (이미 복원). daily "-2.2" → **-7** |
| momentum | buy_threshold 29 / stop **-5** / daily_loss **-10** / weight 0.24 | 이미 복원 확인 |
| VCP | base_depth 0.35 / last_pullback_max 0.1 / reentry 7 / weight 0.12 | 일치 |
| BFB | pole_min_return **20**(DB) / flag_retr 0.382 / reentry 3 / weight 0.12 | **코드 DEFAULT=15.0 인데 DB=20** = DB가 코드보다 엄격. 브리핑 "코드 15?" 정확 |

**핵심 정정 3건**:
1. donchian min_mcap = **100억**(이미 임시완화 상태), "3000억 방치" 아님. 원복 대상이 3000억이 아니라 "100억을 유지할지/올릴지" 문제.
2. VB/LTV/momentum 손절·한도는 **이미 수동 복원됨** — 방치된 건 **donchian 단독**(사용자 진단 정확).
3. BFB pole_min_return 은 **DB=20 이 실효값**(코드 15 는 무시됨). BFB 진입 엄격도 평가는 **20 기준**으로 해야 한다.

---

## 1. 판단 요청별 결론

### 판단 1 — systemic: auto-apply ratchet 이 전략 교살 구조 결함인가?

**결론: YES, 구조적 결함이다. P0(구조 가드) + P1(정비).**

**트레이더 시각 — 왜 이게 치명적인가**:
손절과 일일한도는 "이 전략의 정체성"이다. 손절 -6% 짜리 스윙 전략과 -3% 짜리 전략은
*완전히 다른 전략*이다. 전자는 "노이즈 견디고 추세 먹는다", 후자는 "칼같이 자르고 다음 기회".
AI가 "지난 N일 손실 크니 손절을 조이자"를 매일 권하고, 그게 조임 방향만 적용되면,
전략은 **자기도 모르게 다른 전략으로 변태**한다. 특히 돌파·스윙류는 손절을 조이면
**정상적인 되돌림(whipsaw)에 상시 손절** → 승률 급락 → AI가 다시 "손실 크니 더 조이자" →
**죽음의 나선(death spiral)**. donchian daily_loss -0.8 이 정확히 이 종착점이다.

**정량 근거**:
- donchian `is_daily_loss_exceeded`: `loss_rate = daily_realized_pnl / total_investment × 100 <= -0.8`.
  전략 배정자금의 **-0.8%** 실현손실 1회 = 당일 매수 전면 중단. 손익비 2.65 전략인데
  첫 손절 1회(평균 -4,340원)면 그날 끝. 승률 17%라 첫 진입이 손절일 확률이 높음 → **사실상 매일 1종목 진입 후 중단**.
- stop -3.2%: 20일 신고가 돌파 스윙에서 정상 되돌림 폭. ATR 기준 하루 변동성이 -3.2% 를
  자주 건드리는 종목군(코스닥 중소형)에서 **돌파 직후 눌림에 상시 손절**.

**시정 방향 — 3층 방어 권고**:

**(P0-a) 손절·일일한도·비중 키를 auto_apply 대상에서 제외** (가장 근본).
- `_CONSERVATIVE_KEYS` 에서 `daily_loss_limit` 우선 제거, 이어 `stop_loss_rate`/`intraday_stop_loss`/
  `overnight_stop_loss`/`stop_loss_main`/`stop_loss_pre_nxt` 전량 제거 검토.
- 논거: 이 키들은 **전략 정체성 상수**다. 진입 임계(208/209)와 동일 논리 —
  "AI 자동튜닝 부적합, 사람이 판단"의 대상. 자동으로 조이는 것이 위험하지, 자동으로 완화하는 것도 위험.
- position_ratio 는 자금관리 핵심이라 자동 축소도 위험(과소진입) → 함께 제외 권고.
- **결과: auto_apply 는 weight 감액만 남김**(그것도 death-spiral 소지 있으나 별건).

**(P0-b) 하한 가드(floor) 신설** — P0-a를 부분 채택 시의 최소 안전장치.
- 만약 손절 키를 auto 대상에 남긴다면, 전략별 손절 하한(예: donchian daily_loss ≥ -3.0,
  stop ≥ -4.0)을 `PARAM_RANGES` 하한과 별도로 auto_apply 게이트에 명시.
- `float(v) > float(current_v) AND v >= FLOOR[k]` 조건 추가.
- **차선책** — P0-a(전면 제외)가 더 깔끔하다. floor 는 "어디가 하한인가"를 매 전략 논쟁해야 함.

**(P1) 복원(완화) 경로 신설**.
- 현재 완화 자문은 영구 무시된다. 최소한 **완화 자문을 운영자에게 명시적으로 노출**하고
  (예: 리포트에 "AI가 donchian daily_loss -0.8 → -3.0 완화 권고, 미적용"),
  원클릭 apply 를 조임과 대칭으로 제공. Phase C(자문 품질) 로 이관 가능.

**(P1) PARAM_RANGES 정비** — 판단 6에서 상술.

**우선순위: P0** (auto_apply 켜기 전 필수. 지금 꺼져 있어 급하진 않으나, 켜는 순간 재교살).

**반례/한계**:
- auto_apply 가 현재 0건 = 지금 당장의 손실 원인은 아님. "지금 아프지 않다"는 이유로 미루면,
  auto 를 켜는 미래 시점에 조용히 재발한다. 구조 결함은 발현 전 차단이 정석.
- 손절 키 전면 제외 시 "AI가 정말 필요한 조임"도 자동 반영 안 됨 → 수동 부담↑.
  그러나 손절은 하루 늦게 조여도 손실 제한적, 잘못 조이면 전략 사망 → **비대칭적으로 제외가 안전**.

---

### 판단 2 — donchian: daily_loss -0.8 / stop -3.2 방치. 복원값 + min_mcap 일정?

**결론: P0. 208/209와 즉시 사이클화 가능.**

**트레이더 시각**:
208(박스필터 제거)·209(extension 0.5→4.0)로 "매수 신호가 나오게" 만들었다.
그런데 **신호가 나와도 진입 직후 죽는다** — stop -3.2 는 돌파 스윙엔 너무 타이트하고,
daily_loss -0.8 은 "첫 손절 = 당일 영업 종료". 두 개를 안 풀면 208/209는 반쪽짜리다.
donchian 성과(6건, 승률 17%, 손익비 2.65, 총 -10,200)는 **표본 부족 + 교살 상태의 결과**라
지금 성과로 전략을 판단하면 안 된다. 먼저 정상 파라미터로 되돌린 뒤 재관측해야 한다.

**정량 권고값**:

| 키 | 현재(교살) | 권고 복원값 | 근거 |
|---|---|---|---|
| `stop_loss_rate` | -3.2 | **-6.0** | 코드 주석·구프로젝트 원본값 -6. 20일 신고가 돌파의 정상 되돌림 흡수. ATR trail(1.8×)이 추세 이탈은 별도 관리하므로 하드손절은 넉넉히 |
| `daily_loss_limit` | -0.8 | **-6.0** (최소 -4.0) | code DEFAULT=-8.0. 배정자금 -0.8% 중단은 "1종목 손절=종료". 멀티데이 스윙(max_pos 3)에서 최소 2~3종목 손절 여지(-4~-6%) 필요. **-6.0 권고**, 보수적이면 -4.0 |
| `min_market_cap` | 100억 | **유지(100억) 또는 500억** | 100억은 이미 완화된 상태(Q2=D). 3000억 원복은 **비권고** — donchian(코스닥 중소형 돌파 포함 유니버스)에 3000억은 대형주만 남겨 신고가 돌파 후보 고갈. 유동성 리스크가 걱정이면 500억 + trade_amount 200억(현재값) 조합으로 충분. **원복 서두르지 말 것** |

**즉시 사이클화 (P0, 208/209 패턴 동일)**:
```
donchian_swing params:
  daily_loss_limit: -0.8 → -6.0   (또는 보수 -4.0)
  stop_loss_rate:   -3.2 → -6.0
  min_market_cap:   유지 (100억)  ← 원복 보류
```
- 변경 = DB param UPDATE + `_workspace/00_leader_trading_rules.md` 동기화.
- 매매 안전성 8영역 무관(prepare/exit 임계값). `is_daily_loss_exceeded`/손절 분기는 값만 바뀜.
- **선행 권고**: 이 복원을 208/209보다 우선하거나 동시 배포. 안 그러면 208/209 효과 측정이 교살 상태에서 이뤄져 오판.

**반례/한계**:
- daily_loss -6.0 은 "하루에 배정자금 6% 까지 손실 허용" = 위험 상향. 그러나 donchian weight 0.12
  (전체의 12%) × -6% = 전체 순자산 -0.72%/일 최악치. max_pos 3 감안 수용 가능.
- min_mcap 100억 유지 시 저유동성 종목 진입 위험 → 현재 min_trade_amount 200억이 2차 방어.
  D+1 실측으로 진입 종목 유동성 관찰 권고.

---

### 판단 3 — BFB/VCP 무거래: 패턴 희소(정상)인가 vs 진입 과엄인가?

**결론: 데이터로 단정 불가 → Phase B funnel 스윕 필수 지정. 비중 재배분은 Phase B 후.**

**트레이더 시각**:
BFB(불플래그)와 VCP(변동성 수축 패턴)는 **본질적으로 희소한 패턴**이다.
- VCP: Minervini 원형. 베이스 25~75일 + 수축 2~4회 + 마지막 눌림 ≤10% + EMA 정배열.
  **정상 시장에서도 하루 0~수 종목**. 한국 급등주는 베이스 형성 없이 바로 튀는 경우가 많아
  VCP 셋업 자체가 드물다. **무거래가 곧 결함은 아니다.**
- BFB: 폴(+15~20% 급등) + 플래그(얕은 눌림) + 돌파. 한국 급등주는 눌림이 얕고 빨라
  플래그 구간 포착이 구조적으로 어렵다(사이클 198에서 flag_lookback_min 3→2 완화한 이력).

**그러나 "과엄" 혐의도 실재**:
- BFB `pole_min_return` **DB=20**(코드 15보다 엄격). +20% 폴 + 음봉비율 필터 교집합이
  한국 ±30% 환경에서 좁다(코드 주석이 정확히 이 문제를 지적하며 15로 낮췄으나 DB는 20 유지).
- VCP `base_depth_pct 0.35` / `last_pullback_max 0.1`: 베이스 깊이 35%, 마지막 눌림 10% —
  둘 다 타이트. 한국 변동성에선 베이스가 더 깊고 눌림도 더 큰 게 정상.

**판정 불가 이유(데이터 한계 명시)**:
성과지표가 **부재**(매도 0건). funnel 실측(각 단계 몇 종목이 어디서 탈락하는지) 없이는
"패턴이 아예 없어서 0"인지 "패턴 후보는 있는데 마지막 임계에서 다 탈락"인지 구분 불가.
이건 **Phase B funnel 스윕의 정확한 대상**이다.

**Phase B 지정 (필수)**:
| 전략 | funnel 관찰 포인트 | 스윕 후보 키 |
|---|---|---|
| BFB | 폴 통과 수 vs 플래그 통과 수 vs 돌파 통과 수 | `pole_min_return` 20→15(코드 정합), `flag_retracement_max` 0.382→0.5, `flag_lookback_min` |
| VCP | 베이스 통과 vs 수축 통과 vs 마지막눌림 통과 vs EMA정배열 통과 | `base_depth_pct` 0.35→0.5, `last_pullback_max` 0.1→0.15, `pullback_count_min` |

- funnel 에서 **초기 단계(폴/베이스)부터 0** = 진짜 희소 → 방치 정당.
- **마지막 단계(플래그/눌림/EMA)에서만 0** = 과엄 → 해당 키 완화(P1~P2).

**비중 재배분(각 12%)**:
- **Phase B 전까지 보류**. 무거래 = 자금 0 사용 = 다른 전략에 자금 안 뺏김(할당은 되나 미집행).
  성급히 BFB/VCP 12%→축소 후 momentum/LTV 로 재배분하면, funnel 완화로 BFB/VCP 살아날 여지를 죽인다.
- 단, momentum(+47K, 검증된 최고)이 자금 부족으로 기회 놓친다면 **일시적 재배분** 고려 가능(판단 5 참조).

**우선순위: Phase B (funnel 스윕)**. 비중은 Phase B 결과 후 P1~P2.

**반례/한계**:
- 무거래가 몇 주 더 지속되고 funnel 초기단계부터 0이면, 완화해도 안 나올 수 있음 →
  그땐 "한국 시장 부적합 패턴"으로 비중 축소가 정답. 지금 단정은 이르다.

---

### 판단 4 — VB -40K 최대손실: 승률33%+손익비1.57인데 43손실. 구조 문제?

**결론: P1. position_ratio 0.5 + max_positions 2 조합이 손실 증폭 구조. 201 쿨다운 실효는 부분적.**

**트레이더 시각 — 왜 손익비 1.57에 43손실인가**:
승률 33% + 손익비 1.57 이면 기대값은 양수여야 정상:
`0.33 × 1.57 - 0.67 × 1 = 0.518 - 0.67 = -0.152` → **기대값 음수!**
손익비 1.57 은 손절이 이기려면 **승률 39% 이상** 필요(1/(1+1.57)=0.389).
즉 VB는 **승률이 손익비를 못 받쳐주는** 상태다. 이건 파라미터 조임이 아니라
**진입 질(entry quality) 또는 손절 폭 문제**.

**구조 진단**:
- `position_ratio 0.5` + `max_positions 2`: 종목당 배정자금의 50%, 최대 2종목 = **사실상 전액을 2종목에 몰빵**.
  손익비 1.57 짜리 전략을 고비중 2종목에 집중 = **분산 없이 변동성만 증폭**. avg_loss -5,947
  (전략 중 최대)이 이걸 증언한다.
- k_value_krx_main 1.3: 돌파 임계. 낮으면 페이크 돌파 자주 물림 → 승률 하락. VB avg_loss가
  큰 것과 정합(페이크에 물려 stop -5%까지 감).

**근본 개선 방향 (P1)**:
1. **position_ratio 0.5 → 0.3~0.35** (P1, 즉효·저위험): 종목당 비중 낮춰 손실 변동성 축소.
   승률이 안 받쳐주는 전략은 베팅을 줄이는 게 정석. max_positions 는 2 유지(또는 3으로 늘려 분산).
   - 대안: pos_ratio 0.35 + max_pos 3 = 유사 총노출, 분산 개선.
2. **k_value_krx_main 1.3 → 1.5** (P2, 관찰 후): 돌파 임계 상향 = 페이크 필터 → 승률 개선 기대.
   단 진입 빈도 감소 → funnel 관찰 동반(Phase B).
3. **201 재진입 쿨다운(2영업일) 실효 점검** (P1 관찰): 코드상 배선됐으나(cycle 201),
   최근 VB 손실이 재진입 whipsaw 인지 신규 진입 손절인지 **trade-level 재진단 필요**.
   구프로젝트에선 LS ELECTRIC 재진입이 총손실 45% 였음. 신규 DB의 VB 손실 구성 분석이 P1 후속.

**우선순위**: P1 = pos_ratio 0.5→0.35 (즉시 사이클 가능, param 변경). P2 = k값 상향(funnel 관찰 후).

**반례/한계**:
- pos_ratio 축소는 avg_win 도 같이 줄인다. 손익비는 불변, **총손익 변동성만 축소**(하락 완충).
  근본 승률 문제는 k값·진입질로 별도 해결해야 함.
- 표본 69건은 통계적으로 유의하나, 시장 레짐(변동성 국면)에 VB 성과가 크게 좌우됨 →
  -40K가 특정 급락 국면 집중인지 trade-level 확인 권고.

---

### 판단 5 — momentum 최고(+47K)인데 6/17 중단: 왜? 비중 확대?

**결론: 중단 원인 규명 필요(P1 진단). 비중 확대는 원인 규명 후.**

**트레이더 시각**:
momentum(+47,404, 승률 30%, 손익비 2.67)은 **검증된 최고 전략**. 손익비 2.67은
승률 30%에서 기대값 `0.30×2.67 - 0.70 = 0.801-0.70 = +0.101` 확실히 양수.
이게 6/17 이후 멈췄다면 **돈 버는 엔진이 꺼진 것** — 최우선 규명 대상.

**중단 가능 원인 (규명 필요)**:
- `buy_threshold 29`: 등락률 29% 이상 진입. 이건 **매우 높은 임계**(당일 +29% 급등주).
  이런 종목은 하루 수 개뿐 + 이미 단기과열/이상급등 플래그로 scanner에서 차단될 수 있음.
  → **유니버스 이슈** 혐의(scanner 매수 진입 차단 플래그와 buy_threshold 29의 상호작용).
- momentum 은 실시간 scan_stocks(등락률 순위) 기반 → 유니버스 결손(사이클 176 거래대금 결손 등)
  또는 급등주 차단 정책(투자주의/단기과열)과 충돌 시 후보 고갈.
- prepare 임계 희소 vs 운영 결함 구분이 안 됨 → **로그 실측 필요**.

**Phase B/진단 지정**:
- funnel 로 momentum 유니버스 → buy_threshold 통과 수 관찰.
- system_logs 에서 6/17 이후 momentum 매수 신호/차단 로그 실측.
- 사이클 204(투자주의/투자유의 차단 해제)가 신규 프로젝트에 반영됐는지 확인 —
  momentum 급등주가 이 플래그로 차단되면 정확히 6/17 류의 중단 발생.

**비중 확대**:
- +47K 실적은 확대 매력 충분. **단, 중단 원인이 "구조적 희소"면 비중 늘려도 집행 안 됨**(자금만 놀림).
  "운영 결함(유니버스/차단)"이면 그걸 먼저 고쳐야 비중 확대가 의미.
- **원인 규명 후** momentum weight 0.24 → 0.30 검토(BFB/VCP 무거래분 재배분 원천).

**우선순위: P1 진단**(중단 원인). 비중은 진단 후.

**반례/한계**:
- buy_threshold 29 는 "고품질 급등만" 필터로 승률·손익비를 만든 요인일 수 있음 →
  낮추면 진입 늘지만 질 하락. 함부로 완화 금지. 중단이 결함인지 설계인지부터.

---

### 판단 6 — 진입 임계 PARAM_RANGES 잔존 6키: 208/209처럼 제외?

**결론: 키별 차등. 진입 임계=전략 정체성은 제외(P1), 튜닝 여지 있는 폭 파라미터는 유지 또는 floor.**

**원칙 (208/209 선례 = "진입 임계는 전략 정체성 상수, AI 자동튜닝 부적합")**:

| 키 | 전략 | 성격 | 권고 | 우선순위 |
|---|---|---|---|---|
| `buy_threshold` | momentum | **진입 정체성**(29% 급등 = 전략 자체) | **제외** — AI가 낮추면 다른 전략됨 | P1 |
| `donchian_period` | donchian | **진입 정체성**(20일 신고가 = 전략 정의) | **제외** — 10~60 범위 튜닝은 전략 변태 | P1 |
| `min_prdy_rate` | LTV | 진입 문턱(전일등락 5%) | **제외** 검토 — 롱테일 셋업 정의 | P1~P2 |
| `min_market_cap` | 전전략 | 유니버스 필터(유동성) | **유지 가능** — 시총 컷은 위험관리 성격, AI 튜닝 무해에 가까움. 단 floor(최소 100억) 권고 | P2 |
| `last_pullback_max` | VCP | 패턴 임계(마지막 눌림) | **제외 또는 신중** — VCP 정체성. Phase B 스윕 대상이므로 자동튜닝과 충돌 | P2 |
| `exclude_consecutive_limit` | LTV | 연속상한가 제외 수 | **유지 가능** — 위험회피 성격(작전주 회피). 조임은 안전 방향 | P2 |

**트레이더 시각**:
"진입 임계"와 "위험관리 임계"를 구분해야 한다.
- **진입 임계**(buy_threshold, donchian_period, min_prdy_rate, last_pullback_max):
  이걸 AI가 흔들면 전략이 다른 전략이 된다. 208/209 논리 그대로 → **제외**.
- **위험/유니버스 임계**(min_market_cap, exclude_consecutive_limit):
  이건 조여도 "더 안전"한 방향이라 AI 자동 조임이 상대적으로 무해. 단 min_mcap 은
  너무 조이면(대형주만) 후보 고갈 → **floor(하한 100억) 권고**.

**우선순위**:
- P1: `buy_threshold`, `donchian_period` 제외 (명백한 진입 정체성, 208/209 직후속).
- P2: `min_prdy_rate`, `last_pullback_max` 제외 + `min_market_cap` floor.
- `volume_multiplier`/`long_ma_period`/`atr_trail_mult`/`k_value_*` 등 "폭·배수" 파라미터는
  튜닝 여지 실재 → **유지**(단 A-1 P0 손절 floor 와 별개).

**반례/한계**:
- 전부 제외하면 auto_apply/AI 자문의 param 튜닝 가치가 거의 0이 됨 → 자문이 weight 만 만지게 됨.
  이게 나쁜 건 아니나(param 은 사람이, weight 만 자동), 자문 시스템 재설계 함의 → Phase C 논의.

---

### 판단 7 — LTV 재진입 쿨다운(201 후속): 테스 이틀 whipsaw 근거로 도입?

**결론: P1 도입 권고. 단 LTV 특성상 쿨다운 설계가 VB/BFB와 달라야 함(domain 후속 필요).**

**트레이더 시각 — 테스(095610) 이틀 whipsaw**:
7/13 테스 -10,100 → 7/14 테스 재매수 -9,900 = **이틀 연속 같은 종목 손절 -20,000**.
이건 전형적 **재진입 whipsaw** — 손절한 종목이 다음날 다시 셋업 충족 → 재매수 → 또 손절.
201 사이클에서 VB에 정확히 이 문제(LS ELECTRIC 4일 재진입 -26,000 = 총손실 45%)로
재진입 쿨다운(2영업일)을 도입한 선례가 있다. **LTV도 동일 무방비 상태**(DB에 reentry 키 없음).

**그러나 LTV 쿨다운은 VB와 설계가 달라야 한다 (중요)**:
- LTV(롱테일 변동성)는 **연속 상한가 익일 청산** 전략 — `_limit_up_reached` 종목은
  밤새 보유 후 익일 NXT 청산한다. tradable_boards=("main","pre_nxt").
- VB(당일청산)와 달리 LTV는 **멀티데이 보유 특성**이 있어, 쿨다운을 잘못 걸면
  정상적인 익일 청산·재진입 사이클을 깨뜨릴 수 있음.
- 201 인계에도 "LTV 는 overnight 상한가 특성상 쿨다운 설계 상이 → 별도 domain 평가"로 명시됨.

**권고 (P1, 단 설계 자문 선행)**:
1. **재진입 쿨다운 도입 방향은 GO** — 테스 whipsaw 는 명백한 손실 누출.
2. **쿨다운 기간·조건 설계는 별도 domain-consult 필요**:
   - 손절 청산 후에만 쿨다운(익절/정상 익일청산 후는 쿨다운 없음) — 테스 케이스는 손절이므로 커버.
   - 기간: VB 2영업일 복사 금지. LTV는 셋업 재형성이 느릴 수 있어 2~3영업일 검토.
   - `_limit_up_reached`(상한가 모드)와의 상호작용 — 쿨다운이 상한가 익일 보유를 안 깨는지 확인.
3. 구현 시 **cycle 191 배선(on_position_closed 훅)** 재사용 — LTV에 override 추가.
   BFB/VCP는 이미 배선됨(reentry_cooldown_days 3/7), LTV만 미배선.

**우선순위: P1** (손실 직결, 근거 명확). **단 설계 domain-consult 선행** → 그 후 사이클화.

**반례/한계**:
- 쿨다운이 "다음날 정말 좋은 재진입 기회"도 막음. 그러나 손절 직후 같은 종목 재매수는
  통계적으로 whipsaw 확률 높음(추세 훼손 종목) → 비대칭적으로 쿨다운이 이득.
- 테스 2건은 표본이 작다. LTV 전체 재진입 손실 패턴을 trade-level 로 확인하면 근거 강화(P1 후속).

---

## 2. 우선순위 백로그 (요약 표)

| # | 개선안 | 전략 | 문제(정량근거) | 개선 방향(값) | 안전성영향 | 예상사이클 | 우선순위 |
|---|---|---|---|---|---|---|---|
| A | **donchian 손절/한도 복원** | donchian | daily_loss -0.8(배정자금 -0.8%=당일중단) + stop -3.2(돌파 되돌림 상시손절). 208/209 효과 무력화 | daily_loss -0.8→**-6.0**(보수 -4.0), stop -3.2→**-6.0** | 무관(exit 임계값) | 1사이클(208/209형) | **P0** |
| B | **auto_apply 손절키 제외(ratchet 차단)** | 전전략 | `float(v)>current` 게이트=조임만 통과, 완화경로 없음=단조교살. auto 켜는 순간 재발 | `_CONSERVATIVE_KEYS` 에서 daily_loss_limit+손절5키 제거 | 무관(param 정책) | 1사이클 | **P0** |
| C | **VB position_ratio 축소** | VB | 승률33%+손익비1.57=기대값 음수. pos_ratio 0.5+max_pos 2=2종목 몰빵, avg_loss -5,947 최대 | pos_ratio 0.5→**0.35**(±max_pos 3) | 무관(calc_qty) | 1사이클 | **P1** |
| D | **진입임계 PARAM_RANGES 제외(1차)** | momentum,donchian | buy_threshold/donchian_period=진입 정체성, AI튜닝시 전략변태(208/209 논리) | 2키 PARAM_RANGES 제외 | 무관(param 정책) | 1사이클 | **P1** |
| E | **LTV 재진입 쿨다운 도입** | LTV | 테스 이틀 whipsaw -20,000. LTV reentry 무방비(DB 키 없음) | on_position_closed 훅 override, 기간 2~3영업일 | 무관(prepare/훅)*설계선행 | 1사이클(+domain-consult) | **P1** |
| F | **momentum 중단 원인 규명** | momentum | +47K 최고인데 6/17 중단. 유니버스/차단 vs 희소 미구분 | funnel+로그 실측, 204 차단해제 반영 확인 | 무관(진단) | Phase B | **P1** |
| G | **BFB/VCP funnel 스윕** | BFB,VCP | 무거래 0건. 희소 vs 과엄 미구분(성과지표 부재) | funnel 단계별 탈락 관찰 → 임계 완화 후보 도출 | 무관(관찰→param) | Phase B | **P1** |
| H | **진입임계 제외(2차) + min_mcap floor** | LTV,VCP,전전략 | min_prdy_rate/last_pullback_max 정체성, min_mcap 과조임시 고갈 | 2키 제외 + min_mcap floor 100억 | 무관(param 정책) | 1사이클 | **P2** |
| I | **VB k값 상향** | VB | k_krx 1.3 페이크 돌파 물림 → 승률 저하 | 1.3→1.5 (funnel 관찰 후) | 무관(prepare 임계) | Phase B후 | **P2** |
| J | **복원(완화) 경로 노출** | 전전략 | 완화 자문 영구 무시=ratchet 되돌림 힘 부재 | 리포트에 미적용 완화자문 노출+원클릭 | 무관(자문 품질) | Phase C | **P2** |
| K | **비중 재배분 검토** | BFB,VCP→momentum | 무거래 12%×2 유휴 vs 검증전략 자금 | G/F 결과 후 판정 | 무관(weight) | Phase B후 | **P2** |

---

## 3. P0 즉시 사이클화 스펙 (208/209 형식, 값 포함)

### P0-A: donchian 손절/한도 복원 (판단 2)
```
DB strategy_config['donchian_swing'].params:
  daily_loss_limit:  -0.8  → -6.0   (보수 대안 -4.0)
  stop_loss_rate:    -3.2  → -6.0
  min_market_cap:    변경 없음 (100억 유지, 원복 보류)
동기화: _workspace/00_leader_trading_rules.md donchian 절
가드: is_daily_loss_exceeded / STOP_LOSS 분기 값만 변경, 로직 불변
검증: 격리 테스트 + donchian prepare 회귀 0 + 매매안전성 8영역 diff 0
```

### P0-B: auto_apply ratchet 차단 (판단 1)
```
recommendation_engine.py:
  _CONSERVATIVE_KEYS 에서 제거:
    daily_loss_limit  (1순위 — donchian 교살 직접 원인)
    stop_loss_rate / intraday_stop_loss / overnight_stop_loss
    stop_loss_main / stop_loss_pre_nxt
  → auto_apply 는 weight 감액 + position_ratio(별도 판단) 만 잔존
  (position_ratio 도 함께 제외 권고 — 자동 축소=과소진입 위험)
가드: auto_apply_recommendations 테스트 — 손절키 auto 적용 0건 단언
      + AST 가드(_CONSERVATIVE_KEYS 에 손절키 부재)
검증: recommendation 회귀 + auto_apply 격리
주의: 현재 auto_applied=0 이므로 즉효 손실 없음. 예방적 P0(auto 켜기 전 필수)
```

**배포 순서 권고**: P0-A(donchian 복원) 먼저 또는 P0-B와 동시. P0-A 없이 208/209 효과를
교살 상태에서 측정하면 오판. P0-B는 auto_apply 켜기 전까지 시간 여유 있으나 함께 처리 권장.

---

## 4. 데이터 한계 명시 (권고 신뢰도)

1. **신규 프로젝트 성과 표본 부족**: donchian 6건/BFB 0건/VCP 0건 = 통계적 판단 불가.
   A(복원)는 "교살 해제 후 재관측"이 목적이지 "성과 개선 확정"이 아니다.
2. **ratchet 계보 혼재**: 신규 DB의 조임은 수동 apply(43건) 결과. auto_applied=0.
   systemic 결함(P0-B)은 *미래 재발 방지* 성격이지 *현재 손실 원인*이 아니다.
   → "지금 안 아프다"고 미루면 auto 켜는 시점에 조용히 재발.
3. **funnel 실측 부재**: BFB/VCP/momentum 희소 vs 과엄 판정은 Phase B 없이는 추정.
   본 메모의 완화 후보값(pole 20→15, base_depth 0.35→0.5 등)은 **스윕 시작점**이지 확정값 아님.
4. **trade-level 재진단 미실시**: VB -40K, LTV whipsaw 의 손실 구성(재진입 vs 신규)은
   trade_history 상세 분석(P1 후속) 후 근거 강화. 본 메모는 파라미터/성과 집계 수준.
5. **BFB code/DB 불일치**: pole_min_return code=15 vs DB=20. 실효는 DB=20.
   funnel·완화 논의는 반드시 **DB 실효값 기준**. code 정합(15)도 옵션에 포함.

---

## 5. Phase B / C 이관 항목

**Phase B (funnel 스윕)**:
- BFB funnel: 폴/플래그/돌파 단계별 탈락 → pole_min_return, flag_retracement_max, flag_lookback_min
- VCP funnel: 베이스/수축/눌림/EMA 단계별 탈락 → base_depth_pct, last_pullback_max, pullback_count_min
- momentum: 유니버스→buy_threshold 통과 수 + 6/17 중단 로그 실측
- VB: k값 상향(1.3→1.5) funnel 영향 + 재진입 손실 구성 trade-level
- 비중 재배분: 위 결과 종합 후 판정

**Phase C (자문 품질)**:
- 복원(완화) 경로 노출 — 미적용 완화 자문 리포트화 + 원클릭
- auto_apply 재설계 — param 은 사람/weight 만 자동? 자문 가치 재정의
- 진입임계 전면 제외 후 자문 시스템 역할 축소 함의

---

## 6. 트레이더 한 줄 요약

> **208/209는 "신호가 나오게" 했다. 그런데 donchian은 신호가 나와도 진입 직후 죽는다
> (stop -3.2, daily_loss -0.8). 먼저 손절/한도를 정상 복원(-6.0)하고(P0-A),
> AI가 다시 조이지 못하게 손절키를 auto_apply에서 빼라(P0-B). 이 둘이 P0.
> VB는 승률이 손익비를 못 받쳐(기대값 음수) — 비중부터 낮춰라(P1).
> LTV 테스 whipsaw는 재진입 쿨다운으로 막되 LTV 특성상 설계 자문 먼저(P1).
> BFB/VCP/momentum은 funnel 없이 판단 불가 — Phase B로 넘겨라.**
