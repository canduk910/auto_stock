# 피라미딩 적용 설계 청사진 — "언제, 무엇을, 어떤 순서로 켜는가"

- 작성: domain-expert (렌즈 4축 read-only 조사 + EC2 운영 DB 실측 재산출)
- 일자: 2026-09-03 · 기준일 2026-09-02 종가/잔고
- 성격: **읽기 전용.** 소스·테스트·DB 무접촉. 이 문서가 유일한 산출물이다.
- 전제: 사용자 지시 = **"가능하면 적용한다. 계좌를 5,000만원까지 키울 계획이다."**
  → 이 문서는 go/no-go 가 **아니다.** *적용을 전제로* 자본 성장 경로 위에서
  **어느 구간에 무엇을 켜고, 지금 당장 무엇을 준비하는가**를 설계한다.

> # 🔴 최종본 (비판 반영) — 2026-09-03 2차 개정
>
> 초판(같은 날 오전) 이후 **적대적 3렌즈 검토(engineering · risk · quant)** 를 거쳤고,
> 제기된 지적을 **전부 코드/DB/시뮬로 독립 재현**한 뒤 반영했다. 반영 내역 전수 = **부록 B**.
> 초판을 이미 읽은 사람이 **반드시 다시 읽어야 할 것 6가지**:
>
> | # | 초판 서술 | 최종본 정정 | 성격 |
> |---|---|---|---|
> | **1** | Stage 1 은 `max_units_per_stock=1` 로 두면 **추가 0건 = 행위 변경 0** | **성립 안 함.** EC2 실측 — kojiro `strategy_config.params` 에 `max_units_per_stock="2"`·`max_units_total="10"` 이 **이미 영속**(34키 전체 병합 dict). `_load_strategy_config` 가 DB 값으로 덮으므로 **첫 배포에서 2유닛이 실발화**한다. 다크 스위치는 **DB 에 없는 새 키**여야 한다(§3.6·§3.9) | **HIGH — 배포 사고 직전** |
> | **2** | 1N 사다리는 Σ리스크가 안 늘어 **"공짜"** (§3.5 표) | **손절 *크기*만 재고 *확률*을 안 쟀다.** 독립 재현(유니버스 965종목·31,498 합성진입): 세트선 도입이 손절률 **53.0% → 75.3%**, "고정 2N 이면 살아남았을 포지션의 **22.3%**"를 손절로 전환. 이 축은 `max_open_risk_pct`·계좌 게이트·`daily_loss_limit` **어디에도 안 잡힌다**(§3.5.1) | **HIGH — 설계 근거 재작성** |
> | **3** | §5.2 비관 = 5,000만에서 **−6,375,255원(−12.8%)/년** | **단위 정규화 오류.** as-built Δ −23,927원은 순자산 **1.14~1.20M**(1R≈1,750) 시절 14왕복 중 12건에서 나왔는데 오늘의 R(3,873)로 나눴다. 올바른 값 **−1.51R/추가유닛** → **−17.2M(−34.4%)/년**. 초판이 "비교 불가·범위 하단"으로 밀어둔 −1.52R 이 **사실상 기준값**이었다(§5.2) | **HIGH — 2.7배 과소** |
> | **4** | 4장은 정적 계약(AST·PK·8영역) 충돌을 전수 정리 | **런타임 상호작용 3축이 통째로 누락.** ①추가↔청산 인터리브(매도 체결이 포지션·스탬프를 지운 뒤 추가가 체결되면 **스탬프 없는 새 포지션 재등록** = 257720급 orphan) ②`_pending_cancel_tasks` 가 매수취소·매도취소를 **ticker 단일 키로 공유**(교차 살해) ③C-26 처방이 실제 race 에서 **작동 불가**(order_no 가 어디에도 없음). → **§4.4 신설, C-35~C-45** | **HIGH — 충돌 목록 불완전** |
> | **5** | §3.4 사이징 스니펫 · §5.3 꼬리표 | 스니펫이 **자기 원칙 P3(1주 폴백 금지)를 위반**한다(캡 소진 시 `_apply_budget_limit(0)` → `_fallback_one_share`). 꼬리표는 사다리 체결가를 무시한 `g×4×유닛명목` 근사라 1N −10% 갭을 **2.2배 과대**. 둘 다 재작성(§3.4·§5.3) | **MEDIUM — 구현자가 복사할 코드** |
> | **6** | §1.3 · §5.4 의 시장 파라미터 | ATR 중앙값 **4.62% → 5.18%**(실측 n=952). §5.4 #10 "실제 픽은 **고**ATR 편향" 은 **방향이 반대** — 현 보유 6종목 중앙 3.85% < 유니버스 5.18% = **저ATR 편향** = ρ클램프·집중 심화 = **낙관 편향이었다**. donchian `atr_trail_mult` 라이브 값은 2.0 이 아니라 **1.8** → "샹들리에가 세트선을 자동으로 덮는다" 는 라이브에서 **거짓**(§1.3·§3.5·§5.4) | **MEDIUM** |
>
> **결론의 방향은 바뀌지 않았다** — 오히려 강화됐다. 롤아웃 순서(Stage 0 → 0.5 → 1 → 2), kojiro 한정,
> 1주 폴백 선행 시정, G3/G3′/G12 가 실질 관문이라는 판정은 전부 유지된다.
> 바뀐 것은 **① 숫자의 크기(2.7배) ② 안전하다고 적었던 것 중 하나(1N Σ리스크)가 안전하지 않다는 사실
> ③ 다크런치가 다크가 아니라는 사실 ④ 충돌 목록이 11건 더 길다는 것** 이다.
>
> **공정을 위해 반대 방향 증거도 기록한다** — 같은 31,498 표본에서 피라미딩의 *평균 손익 자체는 개선됐다*
> (base +0.170 uN/포지션 → 1N×4 +0.556, 유닛당 +0.170 → +0.249). 즉 §5.2 의 음수 부호는
> **"피라미딩 기제" 의 성질이 아니라 "이 표본 × 이 청산규약" 의 성질**이다. 이것이 G12(결합 백테스트)를
> 유일한 반전 경로로 지목하는 정확한 이유다.

---

> ## 어젯밤 문서(`pyramiding_deep_review_20260903.md`)와의 관계
> 그 문서의 **사실·수치는 전부 살아 있고 여기서 인용한다**(섹션 번호 표기). 바뀌는 것은 **프레임 하나**다.
> - 어제: "지금 켜야 하는가?" → **아니오(옵션 A 보류)**.
> - 오늘: "적용한다면 어떻게?" → **Stage 0 → Stage 1 → Stage 2 단계 롤아웃**.
> 두 결론은 **모순이 아니다.** 어제의 보류 근거(§0 ①~④)는 전부 *"오늘 자본 258만 + 현행 청산 규약"* 에
> 걸린 조건부 근거이고, 그중 **가장 큰 항목 하나가 자본 성장으로 자동 해소된다**(1주 폴백).
> 자동 해소되지 **않는** 항목(엣지 부호·집중도·배관 결함)이 곧 **게이트**가 된다.
>
> ### 이 문서가 어젯밤 문서를 정정하는 것 1건
> 렌즈 B 표가 **kojiro 와 donchian 의 유니버스를 뒤바꿔** 배정했다.
> 실측(`kojiro.py:543` `is_kospi200=None, is_kosdaq150=None` vs `donchian_swing.py:694-695` `is_kospi200=True, is_kosdaq150=True`):
> **kojiro = 전체 상장 ∩ 시총500억 ∩ 거래대금10억 (n=957, 중앙가 24,550원)**,
> **donchian = KOSPI200∪KOSDAQ150 ∩ 동일 컷 (n=331, 중앙가 58,200원)**.
> 방향이 반대이므로 **1주 폴백 노출도 숫자가 전부 바뀐다** — kojiro 는 렌즈 B 가 말한 38.2% 가 아니라 **18.8%**(258만),
> donchian 은 69.0% 가 아니라 **70.1%**. 결론(자본이 커지면 폴백이 소멸)은 같지만 **kojiro 의 출발점이 렌즈 B 주장보다 두 배 낫다.**
> §1.3 표가 정정본이다.

---

## 요약 — 결정해야 할 것 **8가지**와 이 문서의 권고 *(최종본에서 2건 추가)*

| # | 결정 | 권고 | 근거 |
|---|---|---|---|
| 1 | 원장 구조 | **가중평단 누적 + `positions` 3컬럼 ALTER** (랏 원장 기각) | 접촉면 4지점 vs 전면 재작성. 유닛별 부분 청산은 `execute_sell` 에 수량 인자가 없어 어차피 별도 대공사 (§3.1) |
| 2 | 대상 전략 | **kojiro 단독.** donchian 은 T3(1억) 이후 재검토, VCP/BFB/VB/momentum/LTV 영구 제외 | §2.3 어젯밤 문서 · donchian 은 유닛 해상도가 2,000만 미만에서 없음(§1.3) |
| 3 | 트리거 앵커 | **`last_entry_price + k×step×N_entry` 단조 사다리** — 가중평단 앵커 금지 | 평단 앵커는 되돌림 재무장 = 물타기 (어젯밤 §2.6 ⑨) |
| 4 | 간격 | **Stage 2 진입 시 1N.** 1/2N 은 T3 이후 | "1N 은 더 나은 규칙이 아니라 더 적은 용량"(어젯밤 §2.6) — 용량을 작게 시작 |
| 5 | 유닛 하한 | **추가 유닛은 계산 수량 ≥ 2주일 때만.** `_fallback_one_share` 추가 경로 **금지** | 1주 폴백이 어젯밤 시뮬 악화의 87.6% 를 지배 (어젯밤 §0.0) |
| 6 | Σ캡 | 4유닛 ON 과 `max_open_risk_pct` 상향은 **한 사이클에 같이 가지 않는다.** 캡 상향은 **유닛-섹터 캡 배포 후 별도 사이클** | 0.5N 은 캡 4.5%가 1.80스택에서 제동하지만 **1N 은 Σ리스크가 안 늘어 캡이 비구속** — 예산 클램프만 남는다(§3.7 · §5.3). 5,000만에서 **계좌 30%가 1~2종목**(ρ클램프 구간, §5.3 정정) |
| **7** | **[최종본 신규] `max_units` ↑ 와 `position_ratio`** | **함께 움직인다.** 4유닛 ON 시 ρ 0.166 → 0.10 동반 검토 | per-ticker 캡 = `ρ × 예산 × max_units` 이고 저ATR 구간에서는 ρ 가 유닛 명목을 **단독 결정**한다 — ρ 를 그대로 두고 유닛만 올리면 집중도가 ATR 과 무관하게 4배(§5.3 정정 3) |
| **8** | **[최종본 신규] 다크런치 방식** | **DB 에 없는 신규 키**(`pyramid_max_units` 기본 0) + 모듈 상수 `_PYRAMID_STRATEGIES=()` | 기존 `max_units_per_stock` 은 **DB 에 "2" 가 이미 영속** — 코드 기본값을 1 로 낮춰도 부팅 시 덮인다(§3.6 정정 ①) |

**한 문장 결론.** 지금 당장 착수할 것은 피라미딩 기제가 아니라 **① 1주 폴백 과잉 시정(G0)** 과
**② Stage 0 관측(`would_add` 20:10 배치)** 두 건이고, 둘 다 8영역 무접촉·매매 행위 변경 0 이며,
**피라미딩을 안 하기로 해도 독립적으로 이득**이다. 기제 코드는 **net 500만 + 배관 4건 동시 시정**에서 시작한다.
⚠️ **최종본 보강** — 배관은 4건이 아니라 **P-1 · P-1b · P-2 · P-3 + C-35~C-45 의 11건**이고,
Stage 1 은 5 사이클이 아니라 **8~10 사이클**이다(§3.9 정정). §5.1 원인 ①의 실증이
**손실의 62%를 만든 018670 1주 폴백 랏**이므로 착수 순서(Stage 0.5 우선)는 더 강해졌다.

---

# 1. 피라미딩 내용정리

## 1.1 책 규칙의 정확한 정의 (터틀 그룹, p.162~179)

| 항목 | **1/2N 룰** (책의 기본) | **1N 룰** (보완) |
|---|---|---|
| 최초 진입 | 돌파 시 1유닛 | 동일 |
| 추가 간격 | **마지막 체결가 + 0.5×N** 도달마다 1유닛 | **마지막 체결가 + 1×N** |
| 동일 종목 상한 | **4유닛** | 4유닛 |
| 추가 시 손절 | **전 유닛 일괄** = `마지막 진입가 − 2N` | 동일 |
| 4유닛 완성 예시 | 2000 / 2050 / 2100 / 2150 (N=100) → 손절 **1950**, 평단 **2075** | 500 / 540 / 580 / 620 (N=40) → 손절 **540**, 평단 560 |
| 유닛별 리스크 | 0.5N / 1N / 1.5N / 2N = **합 5N** | −1N / 0 / 1N / 2N = **합 2N** |

**상위 캡(R15).** 동일 종목 **4유닛** · 상관 높은 군 **6** · 상관 있는 군 **10** · 전체 **12**.

**금기 2.**
1. **물타기 금지** — 손실 중 포지션에 추가하는 것은 리스크 확대. 피라미딩은 **이익 중인 포지션에만**.
2. **되돌림 재무장 금지** — 사다리는 `마지막 체결가` 기준으로 **단조 상승**한다. 갭업 체결 시 다음 눈금이 그만큼 위로 밀린다.
   ("쌀 때 사서 비쌀 때 판다" 는 절대가격이 아니라 **추세 기준**이라는 것이 책의 논지.)

**용어 3.**
- **N** = 최근 20일 True Range 의 지수이동평균(원 단위). 우리 시스템의 `ATR14`/`atr` 이 이 자리에 온다.
- **유닛(Unit)** = `자본의 1% ÷ N` 주식. 즉 *"1N 움직이면 자본의 1% 손익"* 이 되는 수량.
- **세트(Set)** = 같은 종목에 쌓인 1~4유닛의 묶음. **손절선은 세트 전체가 하나**다(개별 유닛 손절 없음).

## 1.2 이 시스템 용어로의 번역

| 책 | 이 시스템 | 근거 |
|---|---|---|
| N | `ATR14` (kojiro `_effective_atr` / donchian `_entry_atr`) | `kojiro.py:1046-1069` · `donchian_swing.py:1764` |
| 1유닛 수량 | `floor(전략예산 × risk_pct ÷ ATR)` = `compute_unit_qty` | `turtle_sizing.py:31-36` |
| "자본의 1%" | **전략예산의 0.5%** (`risk_pct=0.005`) | DB 실측 `risk_pct=0.005` |
| 4유닛 = 5N 리스크 | **전략예산의 2.50%** (`5 × 0.005`) | 산술 |
| 동일종목 4유닛 상한 | `max_units_per_stock` — **현재 값 2, 소비처 0건 dead** | `kojiro.py:209` (주석이 이미 "안전장치 아님" 경고) |
| 상관군 6/10/12 | **부재.** `max_positions_per_sector=2` 는 *종목 개수* 캡 | `kojiro.py:175`, 소비 `:823-838` |
| 세트 손절 = 마지막 진입 −2N | **부재.** 현행은 `pos.buy_price − stop_atr×ATR` (앵커=평단/최초가) | `kojiro.py:913-914` |
| 전 유닛 동시 청산 | **이미 정합** — `execute_sell` 은 항상 `pos.quantity` 전량 | `order_engine.py:592` |

**핵심 번역 3.**

1. **책의 "1N = 자본 1%" 가 우리에겐 "전략예산 0.5%" = 계좌 0.150%(kojiro)** 다.
   유닛 밀도가 책 대비 **1/6.7**. 책의 "전체 12유닛 = 자본 12%" 는 우리 척도로 **계좌 1.80%**.
   → **책 숫자를 그대로 읽고 "위험하다/안전하다" 를 판단하면 틀린다.**
2. **5N 스택 = 전략예산의 2.50% = 계좌의 0.750%** 이고, 이 비율은 **자본과 무관한 상수**다(§1.5).
3. **우리 유닛은 "깨진 벽돌" 이다.** 1주 불가분성 때문에 이론 유닛이 1주 미만이면
   `_fallback_one_share`(`strategy_base.py:431-445`)가 **가격 무관 1주**를 산다 — notional 상한 미검사.
   실측 000815(삼성화재우) 405,500원 × 1주 = **kojiro 예산의 52%가 "1유닛"** 이다.

## 1.3 자본 구간별 유닛 경제학 (실측 재산출, 2026-09-02)

기준: 순자산 `2,582,132` (`daily_performance` strategy='total', 09-02) · `cash_usage_ratio=1.0` ·
Σweight = 1.00 (7전략 enabled 실측) · kojiro w=0.30 · donchian w=0.15 ·
`risk_pct=0.005` (양쪽, DB/코드 실측) · ATR비율 중앙값 kojiro 4.62% / donchian 6.04%.
가격 분포는 **각 전략의 실제 유니버스**를 EC2 read-only 로 재추출했다(§0 정정 참조).

> ### ⚠️ 최종본 정정 — 아래 두 표의 분모 세 개가 틀렸다 (재현: EC2 read-only 2026-09-03)
>
> | 항목 | 초판 | **실측 정정** | 표에 미치는 영향 |
> |---|---|---|---|
> | kojiro 유니버스 ATR비율 **중앙값** | 4.62% | **5.18%** (n=952, ATR14÷최근종가. p05 0.95 · p10 1.89 · p25 3.65 · p75 7.20 · p90 9.23) | 1유닛 명목이 **11% 작아진다** → 아래 "1유닛 명목"·"4유닛 스택 명목"·"스택/예산" 전 행이 과대 |
> | **실제 픽의 ATR 편향** | §5.4 #10 "고ATR 편향" | **저ATR 편향** — 현 보유 kojiro 6종목 실측 3.00/3.12/2.68/6.53/4.57/5.25%, 중앙 **3.85% < 유니버스 5.18%** | §5.4 가 "보수 편향" 으로 분류한 항목이 실은 **낙관 편향**. 저ATR = 유닛 명목 큼 = 집중 심화 |
> | 실효 유닛 명목의 지배 요인 | ATR (`risk_pct ÷ atr_ratio`) | **`atr_ratio < 3.01%` 구간에서는 ATR 이 아니라 `position_ratio` 가 지배** — `compute_unit_qty_guarded`(`turtle_sizing.py:78-79`)가 `budget × position_ratio` 로 클램프. 경계 = `risk_pct ÷ ρ = 0.005 ÷ 0.166 = 3.01%` | 유니버스의 **16.6%**(1% floor 위 밴드로는 ~11.6%)가 이 구간이고 **현 보유 6종목 중 2종목이 그 안**(000815 3.00 · 004690 2.68, 003490 3.12 는 경계 바로 위). 이 구간에서 4유닛 스택 = **예산 69.1% = 계좌 20.7%** (§5.3 재계산) |
>
> **읽는 법.** 아래 표의 "1유닛 명목" 열은 **ATR 4.62% 가정의 상한 근사**로 남겨둔다(초판 대조용).
> 설계 판단에 쓸 값은 **§5.3 재계산 표**이고, 그 표는 ATR 4.62%/5.18%/2.70% 세 시나리오를 병기한다.
> 특히 **`position_ratio` 를 그대로 둔 채 `max_units` 만 올리면 집중도는 ATR 과 무관하게 ρ×4 로 고정**된다 —
> 이것이 §3.4 per-ticker 캡의 실제 크기이고, 초판이 43.3% 로 적은 자리의 라이브 값은 **66.4%** 다.

### kojiro (유니버스 n=957 — 전체상장 ∩ 시총500억 ∩ 거래대금10억, 중앙가 24,550원)

| 순자산 | 전략예산 | **1N 리스크(=1R)** | **1유닛 명목** (=1주 폴백 경계가) | **추가 가능 상한가**(유닛≥2주) | 4유닛 스택 명목 | 스택/예산 | 5N/계좌 | 1주폴백 노출 | **추가불가(<2주) 비율** |
|---|---|---|---|---|---|---|---|---|---|
| **2,582,132** (오늘) | 774,640 | 3,873 | 83,835 | **41,918** | 335,342 | 43.3% | 0.750% | **18.8%** | **34.2%** |
| 5,000,000 | 1,500,000 | 7,500 | 162,338 | 81,169 | 649,351 | 43.3% | 0.750% | 9.7% | 19.2% |
| 10,000,000 | 3,000,000 | 15,000 | 324,675 | 162,338 | 1,298,701 | 43.3% | 0.750% | 4.5% | 9.7% |
| 20,000,000 | 6,000,000 | 30,000 | 649,351 | 324,675 | 2,597,403 | 43.3% | 0.750% | 1.8% | 4.5% |
| **50,000,000** (목표) | 15,000,000 | **75,000** | **1,623,377** | **811,688** | 6,493,506 | 43.3% | 0.750% | **0.2%** | **1.5%** |

### donchian (유니버스 n=331 — KOSPI200∪KOSDAQ150 ∩ 동일 컷, 중앙가 58,200원)

| 순자산 | 예산 | 1R | 1유닛 명목 | 추가 상한가(≥2주) | 1주폴백 노출 | **추가불가(<2주) 비율** |
|---|---|---|---|---|---|---|
| 2,582,132 | 387,320 | 1,937 | 32,063 | 16,031 | **70.1%** | **86.1%** |
| 5,000,000 | 750,000 | 3,750 | 62,086 | 31,043 | 47.4% | 71.3% |
| 10,000,000 | 1,500,000 | 7,500 | 124,172 | 62,086 | 31.1% | 47.4% |
| 20,000,000 | 3,000,000 | 15,000 | 248,344 | 124,172 | 13.9% | 31.1% |
| 50,000,000 | 7,500,000 | 37,500 | 620,861 | 310,430 | 3.9% | **10.6%** |

**읽는 법 3.**
- **"추가불가 비율"** 은 §3.4 의 하한 규칙(추가 유닛 = 계산 수량 **≥2주**)에서 *추가가 아예 발화하지 않는* 종목 비율이다.
  kojiro 는 **5,000만에서 1.5%** — 사실상 전 유니버스에서 피라미딩이 성립한다.
  donchian 은 **5,000만에서도 10.6%**, 2,000만에서 31.1% — **자본 2,000만 미만에서 donchian 피라미딩은 유닛 해상도가 없다.**
- **"스택/예산 43.3%"** 는 자본 무관 상수다. 4유닛 완성 = 전략 예산의 43%를 한 종목에 넣는다는 뜻이며,
  `max_positions=6` 과 정면으로 부딪힌다(§4 C-9).
- **"5N/계좌 0.750%"** 도 자본 무관 상수. 손절이 정상 작동할 때의 계획 손실이다. 꼬리는 다르다(§5.3).
- **[최종본 추가] "계획 손실이 자본 무관 상수" 라는 것은 *손절이 같은 빈도로 발생할 때* 만 참이다.**
  세트선은 손절선을 위로 끌어올리므로 **손절 빈도 자체를 바꾼다** — 이 표의 어느 열에도 그 축이 없다(§3.5.1).
  ⚠️ **이 값은 0.5N 사다리 기준이다.** 이 청사진이 권고하는 **1N 사다리는 4유닛 완성 시 Σ리스크가 2uN = 예산 1.00% = 계좌 0.300%**
  이고, 사다리 도중 최대치도 3uN = 예산 1.50% 다(§3.7 표). 책이 "1/2N 합 5N / 1N 합 2N" 이라 적은 것이 바로 이 차이다.

## 1.4 자본 성장이 바꾸는 것 / 안 바꾸는 것

| | 항목 | 258만 → 5,000만 |
|---|---|---|
| **바뀐다** | 1주 폴백 노출 (kojiro) | 18.8% → **0.2%** |
| **바뀐다** | 추가불가(<2주) 비율 (kojiro) | 34.2% → **1.5%** |
| **바뀐다** | 유닛 해상도 (1유닛 주수, 중앙가 24,550원 기준) | 3.4주 → **66주** |
| **바뀐다** | donchian 실행 가능성 | 사실상 0 → 부분 가능(89%) |
| 안 바뀐다 | 완성 스택 리스크 = 예산 **2.50%**(0.5N 사다리) / **1.00%**(1N 사다리) | 동일 |
| 안 바뀐다 | `max_open_risk_pct` 4.5% ÷ 스택 peak = **1.80 스택**(0.5N) / **3.00 스택**(1N) | 동일 |
| 안 바뀐다 | 4유닛 스택 = 예산 43.3% | 동일 |
| 안 바뀐다 | 기대값의 **부호** | 동일 (§5) |
| 안 바뀐다 | 왕복 비용 = 1N 의 5.3~11.5% | 동일 |

**이것이 단계적 롤아웃의 전부다.** 자본 성장은 피라미딩의 **실행 가능성**만 고치고
**수익성·집중도**는 전혀 고치지 않는다. 후자는 코드(청산 규약·상관군 캡)로만 고친다.

---

# 2. 관련 로직 현재 현황

> 각 항목: **무엇인가 · file:line · 피라미딩에 어떤 제약인가.**

## 2.1 포지션 모델 — 단일 랏이 스키마 레벨에서 강제된다

| 항목 | 근거 | 피라미딩 제약 |
|---|---|---|
| `positions` = `ticker VARCHAR(10) PRIMARY KEY` + 8컬럼 | `supabase/migrations/006_positions.sql:2-12` | **한 종목 = 한 행.** migration 006 이후 ALTER 0건. `entry_atr`/`unit_count`/`last_entry_price` 컬럼 부재 |
| `save_position` = `ON CONFLICT (ticker) DO UPDATE SET` 전 컬럼 | `src/db/positions.py:21-46` | 2차 유닛 저장이 1차 유닛을 **통째로 덮는다** |
| `resolved_high = high_since_buy or buy_price` | `positions.py:32` | 호출부가 `high_since_buy` 를 안 넘기면 **DB 고점이 새 매수가로 리셋** |
| `Position` 데이터클래스 7필드 | `src/engine/strategy_base.py:32-40` | 유닛 수·마지막 진입가를 담을 자리 없음. `:44` 주석 "Position 시그니처 변경 금지"(스코프는 `_MULTIDAY_STRATEGIES` 확장) |
| 부팅 복원 = DB row → Position 1:1 | `src/engine/boot_manager.py:161-170` | 유닛 수 유실 |
| KIS 잔고 보완 복원 = `buy_price=int(h.avg_price)` | `boot_manager.py:223-232` · `scheduler.py:3646-3653` | KIS 는 **평단만** 준다 — 유닛 수는 원리적으로 복원 불가 |
| `_reset_daily_state` 가 `positions.clear()` | `scheduler.py:3806-3820` | 메모리 유닛 상태는 **매일 밤 소멸** → DB 영속 없이는 멀티데이 축적 불가 |
| kojiro `_stop_floor` / `_position_atr` = 인스턴스 메모리 | `kojiro.py:231` · `:238` | 세트 손절선이 **재시작을 못 넘는다** |

## 2.2 매수 경로 — `execute_buy` 첫 줄에서 막힌다

```
check_buy_signal (전략)  →  calc_buy_quantity (전략)  →  _apply_budget_limit (관문)
       →  execute_buy (order_engine)  →  place_order (KIS)  →  체결통보 _handle_buy_fill
```

| 항목 | 근거 | 제약 |
|---|---|---|
| `execute_buy` 최상단 `has_position(ticker)` 차단 | `order_engine.py:226`, `:230` | **추가매수가 첫 줄에서 return** — 재사용 불가 |
| `_apply_budget_limit` = 전 return 강제 관문 | `strategy_base.py:447-484`, AST **A-GATE** `tests/unit/ast/test_budget_limit_ast.py:120-147` | 추가 사이징도 이 관문을 **반드시** 경유해야 함 |
| 관문 내 `await`/DB/HTTP 금지 | `strategy_base.py:470-473`, AST **A-PURE** `:99-118` | 유닛 수는 **메모리 Position 필드**로만 읽어야 함 |
| `calc_buy_quantity` ~ `pending_buys.add` 사이 await 0건 | AST **A-ATOMIC** `:60-97` | 사이징 구간에서 시세/ATR 비동기 조회 불가 |
| **P-1** 체결 병합이 `pos.quantity = total_filled` **절대대입** | `order_engine.py:1210-1213` (`total_filled = _filled_qty[order_no]`, `:79`) | **2차 유닛 체결이 1차 유닛을 소멸시킨다** — 최우선 배관 결함 |
| **P-1b** `pending_buys.discard` 가 전량/부분 분기 **앞** | `order_engine.py:1216-1217` | 부분체결 후 3차 주문이 뚫린다 |
| **P-3** `pending_buys`(set) · `pending_buy_amounts`(dict) · `_pending_cancel_tasks`(dict) 전부 ticker 키 | `strategy_base.py:73`, `:91` · `order_engine.py:1465-1468` | **동일 종목 2주문 공존 불가**. 반면 `_order_qty/_order_strategy/_order_ticker/_pending_buy_orders` 는 order_no 키라 안전(`:79-81`) |
| `save_position` 호출이 `high_since_buy` 미전달 | `order_engine.py:1298-1302` | 추가 체결 시 **DB 고점 리셋** = 트레일링 후퇴 |
| 매수 평가 창 = **09:05~09:30 단일 구간** | `kojiro.py:838-841` | **13:00 에 0.5N 이 나와도 판정 코드가 실행되지 않는다** |
| momentum 폴백 체인의 `is_ticker_held_by_any` → 오염 판정 | `order_engine.py:1163-1178` | 추가 유닛 체결이 매핑 miss 시 **조용히 버려진다** |

## 2.3 재매수 차단 — 4중이고, 안전 게이트 8종이 그 뒤에 있다

| 게이트 | 근거 |
|---|---|
| `is_ticker_blocked_for_buy` = `has_position ∨ is_buy_pending ∨ is_sold_today` (전략 횡단) | `strategy_registry.py:86-98` |
| 소비처 3곳 독립 판정 | `order_engine.py:226`/`:230` · `risk.py:616` · `scheduler.py:2751` |
| kojiro 자체 4중 | `kojiro.py:800-806` (`has_position`/`is_buy_pending`/`is_sold_today`/`_bought_today`) |
| boot 가 **당일 매수 종목을 `sold_today` 에 시드** | `boot_manager.py:272-286` | 

⚠️ **가장 중요한 구조적 사실.** kojiro 의 **매수 안전 게이트 8종이 전부 `check_buy_signal` 안**에 있다 —
계좌 SOFT Σ상한(`kojiro.py:796`) · `buy_disabled`(`:798`) · 보유/주문중(`:800`) · `is_sold_today`(`:802`) ·
`_bought_today`(`:804`) · `is_max_positions`(`:806`) · `is_daily_loss_exceeded`(`:808`) ·
`_is_open_risk_capped`(`:812`) · 섹터 캡(`:823`).
그런데 **보유 종목은 `check_buy_signal` 에 도달하기 전에** 위 3곳에서 걸러진다.
→ **어떤 추가매수 경로를 만들든 이 게이트들을 전부 우회한다. 명시 재판정이 필수다.**
게다가 cycle233 AST 가드(`tests/unit/ast/test_cycle233_ast_account_risk.py:84`)는 `check_buy_signal` 의 `body[0]` 만 보므로 **새 메서드를 볼 수 없다.**

## 2.4 사이징 — 누적 축이 통째로 비어 있다

| 항목 | 근거 | 제약 |
|---|---|---|
| `compute_unit_qty = floor(예산 × risk_pct ÷ ATR)` | `turtle_sizing.py:31-36` | — |
| notional 상한 `min(qty, 예산×position_ratio // 가격)` **호출당** | `turtle_sizing.py:78-79` | **2유닛째를 구조적으로 0주로 만든다.** per-ticker 누적 캡으로 교체 필수 |
| 잔여예산 클램프 = **전략 전체 합** | `strategy_base.py:417-429` `_calc_used_funds`, `:476` | 종목별 캡이 아님. 누적 방어가 이것 **하나뿐** |
| `_fallback_one_share` — notional 상한 미검사 | `strategy_base.py:431-445` | 고가주 1주 = 설계 유닛의 3~15배 (실측 000815 3.10배 / donchian 랏 평균 4.94유닛) |
| `_emit_oversized_fallback` / `compute_over_cap_positions` = **관측만, 수량 무변경** | `strategy_base.py:492-533` · `portfolio_risk.py:226-271` | 4유닛 정상 스택을 **매일 이상 신호로 오탐**하게 됨 |
| `max_open_risk_pct` Σ캡 — **kojiro 에만** | `kojiro.py:186`(DEFAULT 4.5, DB 키 부재=코드값 유효) · 판정 `:969-991` · 계량 `_open_risk_won` `:1072-1089` | 4.5 ÷ 2.5 = **1.80 스택**에서 매수 정지 |
| donchian Σ캡 **부재** | `grep max_open_risk_pct` → kojiro.py 3곳뿐 | donchian 확장은 캡 신설 선행 |
| `position_ratio × max_positions ≤ 1.0` 3중 가드 — **전부 params 축** | AST C-DEFAULT `test_budget_limit_ast.py:162-195` · 런타임 `portfolio_risk.py:273-305` · 자문 `recommendation_engine.py:222-240` | **실보유 유닛을 못 본다** = 4유닛 위반 탐지 불가(P-4) |
| `max_units_per_stock=2` / `max_units_total=10` — **소비처 0건 dead**, 책 값(4/12)과 불일치 | `kojiro.py:209-210`, 경고 주석 `:198-203` | UI 에 "설정된 한도" 로 보임 — **안전장치로 오인 금지** |
| 섹터 캡 = **종목 개수** 2 | `kojiro.py:175`, 소비 `:823-838` | 4유닛 시 **섹터당 8유닛 허용** = 책 R15("높은 상관 6") 초과 |

**실측 현재 상태 (2026-09-02).** kojiro 6포지션 = `max_positions` **포화**, 예산 98.0% 소진.
6종목 중 **4종목이 1주**(000815 405,500 / 004690 130,000 / 005180 75,800 / 285130 47,350).
즉 **오늘 피라미딩을 켜도 예산이 없어 한 주도 못 산다.**

## 2.5 손절/청산 계층 — 앵커가 전부 `pos.buy_price` 다

| 계층 | kojiro | donchian/VCP/BFB |
|---|---|---|
| 하드손절 | `base = pos.buy_price − stop_atr×ATR` (`kojiro.py:913-914`), stop_atr 2.0 | `pos.buy_price − stop_atr×entry_atr` (`donchian_swing.py:1766-1768` / `vcp:1246` / `bfb:1187`) |
| 게이트 | **없음(상시 2ATR)** + `_stop_floor` tighten-only 래칫(`kojiro.py:906-912`) | **`_entry_atr` 스탬프 존재**가 자연 게이트 — 미스탬프면 고정% 경로 |
| ATR 소스 | `_effective_atr` = **live `_candidates` 우선** → `_position_atr` 폴백 (`kojiro.py:1043-1069`) | 하드손절=entry 스냅샷, 트레일링=**live** (`donchian_swing.py:1893-1897`) |
| BE 승격 | `high ≥ buy_price + 1.5×ATR` → floor = `max(floor, buy_price)` (`kojiro.py:921-935`) | 동형 (`donchian_swing.py:1774-1783`) |
| 트레일링(샹들리에) | `high_since_buy − 2.5×ATR` (`kojiro.py:963-969`) — **trail 2.5 > stop 2.0** | `high − 2.0×ATR` — **stop 과 같음** |
| backstop | `hard_stop_pct −8%` | donchian `−9%` / VCP `−5%` / BFB `−4%` (min 밴드) |
| 시간청산 | §3 스테이지3 (가격 무관, `kojiro.py:938-957`) | donchian `breakout_fail_n_days` (`:1806-1826`) / BFB `max_hold_days` (`:1294-1302`) |
| 실효 손절선 미러(계좌 Σ리스크 입력) | `_position_stop_price` 4선 max (`kojiro.py:993-1070`) | `get_effective_stop_price` (`donchian_swing.py:1860-1900` 등) |

**피라미딩 관점 3.**
- **donchian/VCP/BFB 는 세트선을 이미 부분적으로 갖는다** — `atr_trail_mult == stop_atr == 2.0` 이라
  샹들리에 `high−2N` 이 터틀 세트선 `마지막진입−2N` 의 **상위 근사**다(추가 트리거가 `high ≥ 마지막진입` 을 함의하므로).
  단 트레일링은 live ATR, 하드손절은 entry 스냅샷이라 **진입 후 변동성 팽창 시 이 보장이 깨진다.**
- **kojiro 만 `trail 2.5 > stop 2.0`** 이라 샹들리에가 세트선보다 **항상 0.5N 느슨**하다.
  하필 피라미딩 1순위 대상이다 → **kojiro 에 명시적 세트선 배선이 필수.**
- **`_rederive_entry_atr` 은 우리 편이다** — `buy_date` **이전** 봉만 사용(`strategy_base.py:734-759`).
  추가매수 시 `buy_date` 를 갱신하지 않는 규약만 명문화하면 "전 유닛 동일 N" 이 재시작을 넘어 정확히 보존된다.

## 2.6 매도 경로 — 전량 전제 (터틀과 정합)

| 항목 | 근거 | 함의 |
|---|---|---|
| `execute_sell` 에 **수량 인자 없음**, 항상 `pos.quantity` | `order_engine.py:494-500`, `:592` | 터틀 세트 청산(전 유닛 동시)과 **정합** |
| 호출처 전부 전량 | `risk.py:597` · 15:20 `scheduler.py:2110` · 익일 `scheduler.py:1540` | 유닛별 부분 익절은 **불가** |
| 부분 체결 시 잔량 = 취소 후 재주문 | `order_engine.py:1487-1521` | 부분 보유 미잔존 |
| 유일한 수량 하향 = APBK0400 자기치유 | `order_engine.py:760` 부근 (cycle236) | `positions > held` 방향만 |
| BFB measured-move 는 "절반 익절" 의도였으나 전량 구현 | `bull_flag_breakout.py:1276-1290` | 부분 청산 배관 자체가 부재 |

## 2.7 계좌 Σ상한 (cycle233)

| 항목 | 근거 |
|---|---|
| `account_risk_guard` SOFT 게이트, `block_pct=None` = **다크런치** | `src/engine/account_risk_guard.py:35` · `account_risk_watcher.py:16-17` |
| 활성화 = DB `account_risk_block_pct` 한 줄 (권고 6.0) — **실측 키 부재 확인** | `system_config` 실측 (09-03) |
| 신선도 900s 초과 시 fail-open | `account_risk_watcher.py:105`, `:183-215` |
| 소비 **위치 이원화** — 폴/래치형 5전략 = `check_buy_signal` 최상단 / momentum·VB = 발사 직전 | `kojiro.py:796` 등 vs `momentum.py:156` · `volatility_breakout.py:892` |
| AST 가드 G-1 = 7전략 `check_buy_signal` 배선 강제 | `tests/unit/ast/test_cycle233_ast_account_risk.py:84`, `:96` |

## 2.8 관측 · DB · UI · 리포트

| 항목 | 근거 | 제약 |
|---|---|---|
| `daily_log_reports.metrics` **JSONB** | `migrations/013:9`, 삽입 `log_analysis_engine.py:678-688` | **B-lite 배치는 마이그레이션 불요** |
| 집계기 선례 `_aggregate_tick_blind` (정규식 파싱) | `log_analysis_engine.py:309-330` | 그대로 답습 가능 |
| `system_logs` INFO retention **2일** | `src/db/CLAUDE.md` `purge_old_logs` | 관측은 20:10 metrics 로 **수확되어야 보존** |
| `write_log` ±5줄 내 `logger.*` 동시 호출 금지 | AST `tests/unit/ast/test_cycle72_ast_no_logger_write_log_pair.py` | 마커는 `logger.info` 단독 |
| `get_trade_pairs` 가 **이미 분할매수 가중평균 페어링** | `trade_history.py:562-648`, `:624-648` | **손익 뷰 diff 0** — 유일하게 안 건드려도 되는 표면 |
| `trade_history` 부분 UNIQUE `(ticker, order_no, trade_type)` | `migrations/029:29-31` | 유닛별 2행 **정상 공존** |
| **P-2** `update_trade_status` WHERE 에 order_no·LIMIT 부재 | `trade_history.py:113-117`, 동형 `mark_pending_buys_completed:247-266` | PENDING 2건이 **동시에** 뒤집힌다. 취소 경로 `order_engine.py:1474` · sync `scheduler.py:3633` 도 같은 WHERE 공유 |
| `daily_performance` = SELL `profit_loss` 합 | `migrations/010:7-24` | 귀속 구조 무변경. 단 `profit_loss = (price − pos.buy_price) × qty` **gross**(`order_engine.py:1387-1391`) — 수수료·세금 미반영 |
| `daily_realized_pnl` → `daily_loss_limit` | `strategy_base.py:407-413` | **realized 기준** — 미실현 스택 붕괴는 못 막음 |
| `PositionDetail` = 5필드, 소비처 `OrderMonitor.tsx` 단 하나 | `frontend/src/types/trading.ts:150-156` | 생산자 2곳이 **이미 불일치**(`strategy_registry.py:108-118` vs `scheduler.py:1253-1263`) |
| `LogReportMetrics` = `{target_date, logs, trades}` 만 선언 | `frontend/src/types/log_reports.ts`, 렌더 `DailyReportTab.tsx:105-106` | pyramiding 배치를 넣어도 **UI 에 안 보인다**(portfolio_risk_snapshot·tick_blind 도 같은 이유로 이미 미노출) |
| `PortfolioRisk` 타입이 `over_cap_positions`/`account_gate` **누락** | `frontend/src/types/portfolio.ts` vs `routes/portfolio.py:108-110` | 동형 드리프트 선례 |
| **8영역 diff-zero** 대상 = risk/order_engine/session/scanner/strategy_registry/api·order + realtime//auth/ | `tests/unit/ast/test_cycle233_ast_account_risk.py:41-48` | **`boot_manager.py` 는 목록 밖** = 배선 통로 |
| `scheduler.py` **정확히 3,999행**, AST 가 `== 3999` 단언 | `wc -l` 실측 · `tests/unit/ast/test_cycle241_ast_silent_inactive_relative.py:387-396` | **신규 leaf 모듈 강제** |
| 다음 마이그레이션 번호 = **042** (041 이 마지막), CI 는 `sorted(glob)` 자동 적용 | `ls supabase/migrations` · `tests/integration/pg_harness.py:113-119` | 스키마 추가에 CI 코드 변경 0 |

---

# 3. 변경할 로직 상세안

## 3.0 설계 원칙 7 (모든 하위 결정의 상위 계약)

| # | 원칙 | 이유 |
|---|---|---|
| **P1** | **앵커는 `last_entry_price` 단조 사다리.** 가중평단·`high_since_buy` 앵커 금지 | 평단 앵커 = 되돌림 재무장 = 물타기 / 고점 래치 = 스파이크 후 되밀린 가격에 추가 (어젯밤 §2.6 ⑨⑩) |
| **P2** | **N 은 진입 고정(`entry_atr`).** 사다리 눈금과 추가 사이징에 쓰는 N 은 재계산 금지 | kojiro `_effective_atr` 는 live 우선 + `recompute_held_atr` 가 매 부팅 덮어씀 → 눈금이 매일 이동 |
| **P3** | **추가 유닛은 계산 수량 ≥ 2주.** `_fallback_one_share` 추가 경로 **절대 금지** | 어젯밤 §0.0 — 1주 폴백이 손실의 87.6% 지배 |
| **P4** | **손절선은 tighten-only.** 어떤 변경도 손절을 느슨하게 만들면 안 됨 | CLAUDE.md 금기 직격. 재시작 후 세트선 복원 실패가 대표 경로 |
| **P5** | **추가 경로는 매수 안전 게이트 8종을 동일 함수·동일 순서로 재판정** | §2.3 — 경로 신설이 곧 게이트 전면 우회 |
| **P6** | **cap 은 로그에만, 행위는 cap 밖** (cycle237 계약) | 관측기가 신호를 삼키면 결함 주입 |
| **P7** | **행위 변경과 관측 도입은 같은 사이클에 섞지 않는다** | D+1 귀인 분리 (cycle228 선례) |

## 3.1 (a) 랏 원장 vs 가중평단 누적 → **가중평단 채택**

| | ①**가중평단 누적** (채택) | ②랏 원장 신설 |
|---|---|---|
| 스키마 | `positions` **ADD COLUMN 3~4** (무중단) | 신규 `position_lots` 테이블 + CRUD + 이중쓰기 정합 |
| 접촉 | 병합 1곳 + ticker키 4종 승격 + UPDATE WHERE 1곳 + 부팅 복원 4지점 | 위 전부 + `positions.py:21-84` 전 함수 + `boot_manager.py:146-240` + `scheduler.py:3646-3653`(**8영역**) + UI 3계층 |
| 손익 뷰 | **diff 0** (`get_trade_pairs` 가 이미 가중평균) | 랏↔aggregate 진실원 결정 필요 |
| 유닛별 부분 청산 | 불가 | 가능 — **그러나 `execute_sell` 에 수량 인자가 없어 어차피 별도 대공사**(`order_engine.py:494-500`) |
| Σ리스크 회계 | **무수정 정합** (아래 검산) | 재작성 |

**검산 — 가중평단이 책의 5N 과 정확히 일치한다.**
1N 눈금 4유닛(P, P+N, P+2N, P+3N) → 가중평단 `P+1.5N`, 세트 손절 `마지막진입−2N = P+N`.
`_open_risk_won` 식 `qty × (buy_price − stop)`(`kojiro.py:1080-1088`)
= `4u × (P+1.5N − (P+N))` = `4u × 0.5N` = **2uN** = 책 1N룰의 2N. ✔
0.5N 눈금이면 평단 `P+0.75N`, 세트선 `P−0.5N` → `4u × 1.25N` = **5uN** = 책 5N. ✔
→ **`pos.buy_price` 가 진짜 가중평단이기만 하면 Σ리스크·`max_open_risk_pct`·척도 병기가 전부 무수정 정합한다.**

### 3.1.1 스키마 — migration `042_positions_pyramid.sql`

```sql
ALTER TABLE positions
  ADD COLUMN IF NOT EXISTS unit_count       SMALLINT      NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS last_entry_price INTEGER       NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS entry_atr        NUMERIC(14,4) NOT NULL DEFAULT 0;
```
- `DEFAULT` 로 기존 행 무손상. `last_entry_price = 0` / `entry_atr = 0` = **"스탬프 없음"** 센티널
  (⚠️ `0` 을 유효값으로 쓰지 않는다 — cycle226 `_breakout_high==0` 잠복 결함과 동형 함정).
- **`stop_set_price` 컬럼은 두지 않는다.** 세트선은 `last_entry_price − stop_atr × entry_atr` 로 **매번 도출**하고,
  래칫은 기존 `_stop_floor`(메모리) + 부팅 시 도출 재구성으로 처리한다.
  (컬럼을 두면 도출값과 저장값이 갈리는 두 번째 진실원이 생긴다.)
- CI 는 `sorted(glob("*.sql"))` 자동 적용(`pg_harness.py:113-119`) — 워크플로 변경 0.
  ⚠️ `tests/integration/test_cycleM1_1_pg_roundtrip.py:29-58` 이 컬럼 정합을 단언하므로 **동반 갱신 필요**.

### 3.1.2 `Position` 확장 (`strategy_base.py:32-40`)

```python
unit_count: int = 1
last_entry_price: int = 0      # 0 = 미스탬프
entry_atr: float = 0.0         # 0 = 미스탬프
```
**필드 추가는 뒤에 default 로만** — `:44` 주석의 시그니처 안정 요구를 존중.

### 3.1.3 체결 병합 (P-1 시정) — `order_engine.py:1210-1213`

```python
else:  # 같은 order_no 의 후속 부분체결
    pos.quantity = base_qty_before_this_order + total_filled
    ...
```
정확히는 **"이 order_no 가 포지션에 이미 기여한 양"** 을 빼야 한다.
→ 보조 맵 `self._pos_contrib: dict[str, int]`(order_no → 반영 완료 수량, `_filled_qty` 와 같은 생애주기)를 신설하고
```python
delta = total_filled - self._pos_contrib.get(order_no, 0)
if delta <= 0: return                      # 멱등
new_qty  = pos.quantity + delta
pos.buy_price = (pos.buy_price * pos.quantity + price * delta) // new_qty
pos.quantity  = new_qty
pos.last_entry_price = price               # 사다리 앵커 갱신
self._pos_contrib[order_no] = total_filled
# buy_date 는 **갱신 금지** (P2 — _rederive_entry_atr 의 '이전 봉만' 계약 보존)
```
⚠️ **cycle235 overrun 클램프가 조정한 증분**(`order_engine.py:1039-1062`)을 써야 한다.
⚠️ `unit_count` 증가는 **주문 단위**(order_no 최초 기여 시 +1)이지 체결 단위가 아니다.
⚠️ 수량 소스 `fields[9]`(CNTG_QTY)는 AST 봉인 — `fields[16]` 로 바꿔 누적을 흉내내는 시정은
   `tests/unit/ast/test_cycle235_ast_execution_qty.py:12-27` 이 즉시 거부한다. **시정은 병합 로직 쪽에서만.**

### 3.1.4 DB 저장 — `order_engine.py:1298-1302`

```python
await save_position(..., quantity=pos.quantity, buy_price=pos.buy_price,
                    high_since_buy=pos.high_since_buy,        # ← 신규 (고점 리셋 차단)
                    unit_count=pos.unit_count,
                    last_entry_price=pos.last_entry_price,
                    entry_atr=pos.entry_atr)
```
`positions.save_position`(`positions.py:21-58`)에 3+1 인자 추가 + `ON CONFLICT` SET 절 확장.

### 3.1.5 부팅 복원 — **4지점, 그중 1곳은 8영역**

| 지점 | 파일 | 처리 |
|---|---|---|
| DB 복원 | `boot_manager.py:161-170` | 3컬럼 → Position 필드 그대로 |
| KIS 잔고 보완 | `boot_manager.py:223-232` | **유닛 수 원리적 불가** → `unit_count=1`, `last_entry_price=avg_price`, `entry_atr=0`(미스탬프) + `[pyramid_stamp_lost]` WARNING |
| 잔고 재동기화 | `scheduler.py:3646-3653` (**8영역**) | 동일. **diff 0 을 지키려면** 이 지점은 손대지 않고, 재동기화 직후 `boot_manager`/신규 leaf 가 스탬프를 보정하는 방식이 안전 |
| `_stop_floor` 재구성 | `kojiro.py:765-776` | `base` 를 `last_entry_price − stop_atr×entry_atr`(스탬프 있으면)로 계산 → tighten-only `max()` 유지 |

⚠️ **미스탬프(`entry_atr==0`) 시 계약 = "추가 금지 + 손절은 현행 경로 그대로"**.
스탬프가 없다고 손절이 느슨해지면 안 된다(P4).

> ### 🔴 최종본 정정 — "현행 경로 그대로" 가 곧 **P4 위반**이다 (초판이 스스로를 반증한 자리)
> 4유닛 스택에서 세트선 항이 사라지면 손절선이 **얼마나 느슨해지는지**를 초판은 계산하지 않았다.
> 1N 사다리 4유닛: 평단 = `P+1.5N`, 세트선 = `(P+3N) − 2N` = **`P+1N`**.
> 미스탬프 복원 후 `kojiro.py:913-914` 의 `base = pos.buy_price − stop_atr×ATR` = `(P+1.5N) − 2N` = **`P−0.5N`**.
> `hard_stop_pct −8%` backstop 과 `max()` 경합한 실효선:
>
> | ATR 비율 | backstop 위치 | 실효 손절선 | **세트선 대비 완화폭** | 4유닛 환산 | 5,000만 금액 |
> |---|---|---|---|---|---|
> | 5.18% (유니버스 중앙) | ≈ `P−0.16N` | `P−0.16N` | **1.16N** | 4.66 uN | **≈ 350,000원 (계좌 0.70%)** |
> | 2.70% (ρ클램프 = 실제 픽 편향) | ≈ `P−1.58N` | `P−0.5N` | **1.50N** | 6.00 uN | **≈ 450,000원 (계좌 0.90%)** |
>
> → **복원 1회로 계좌의 0.70~0.90% 가 조용히 노출된다.** 그리고 **저ATR 종목이 곧 §5.3 의 66~69% 집중 종목**이므로
> 두 결함이 같은 포지션에서 곱해진다.
> 부수: `_stop_floor`(`kojiro.py:231`)는 in-memory 라 재시작 시 소멸하고, 재구성이 `entry_atr` 스탬프에 의존한다 —
> **스탬프가 없으면 래칫도 복원 못 한다.**
>
> **정정 계약 = "미스탬프 시 손절은 *현행 경로 그대로* 가 아니라 *보수적으로 강제*".**
> 구체적으로: `unit_count > 1` 인데 스탬프가 없으면
> ① `[pyramid_stamp_lost]` **WARNING**(초판 유지) ② **추가 금지**(초판 유지)
> ③ **`hard_stop_pct` 를 평단 기준이 아니라 *최초 매수가 추정* 기준으로 적용**하거나,
>    그 추정이 불가하면 **즉시 청산 후보로 표시**(자동 청산은 금지 — 사용자 결정 사안)
> ④ 발생 자체가 사고 신호이므로 **CRITICAL 승격 검토**.
> ⚠️ 발생 경로는 `_sync_positions_from_balance`(`scheduler.py:3639`)가 `is_ticker_held_by_any` 로
> 기존 포지션을 **보호하므로 덮어쓰기는 아니다** — 위험은 positions 가 실제로 유실된 *뒤*의 재생성 경로,
> 즉 **사고 상황에 정확히 동조**한다.

## 3.2 (b) 추가매수 트리거

| 축 | 결정 | 근거 |
|---|---|---|
| **가격 소스** | `check_exit_signal` 이 받는 `current_price` (WS 틱 + `_swing_rest_poll_loop` 60s REST, 09:30~15:20 커버) | 프리장 보류 게이트(`risk.py:548-585`)를 **공짜로 상속** |
| **판정식** | `current_price >= last_entry_price + step × entry_atr` — **발화 시점 현재가 단독** | 래치(`high_since_buy ≥ level`) 금지 (P1 / 어젯밤 §2.6 ⑩) |
| **눈금** | `step = 1.0 × entry_atr` (Stage 2 시작). 1/2N 은 T3 이후 재검토 | "1N 은 더 적은 용량"(어젯밤 §2.6) — 용량을 작게 시작 |
| **D0(당일) 추가** | **금지.** `buy_date == today` 면 추가 스킵 | ① donchian 실측 0.5N 도달 20건 중 **18건이 D0** = 고점 추격 손실의 주인 ② boot 의 `sold_today` 시드(`boot_manager.py:272-286`)가 재기동 1회로 D0 를 어차피 봉인 — **회피가 무료** |
| **시간창** | `09:30 ~ 15:00` (KST 명시 상수, DB override 불가) | 09:00~09:30 = 시초가 왜곡·최초 진입 창과 충돌 / 15:00 컷 = 15:20 강제청산·장후 단일가(cycle229) 회피 |
| **프리장/애프터** | **전면 금지** — PRE_NXT/POST_NXT 추가 0건 | `tradable_boards` 가 아니라 **명시 상수**로 판정(커플링 차단 독트린) |
| **금요일·연휴 전일** | 추가 금지 (Stage 2 초기), 완화는 별도 결정 | 4유닛 최대 사이즈로 2~3박 갭 노출 (어젯밤 §2.7) |
| **재무장** | 없음. `last_entry_price` 는 **단조 증가만** | 되돌림 재추가 = 물타기 |

**트리거 판정 함수는 전략 파일에 둔다** — `kojiro.py` 신규 메서드
`check_add_signal(ticker, pos, current_price) -> int`(추가할 유닛 수, 0=없음).
`check_exit_signal` 과 같은 파일·같은 데이터에 있어야 세트선과 눈금이 갈리지 않는다.

## 3.3 (c) 추가매수 실행 경로

**결론: 신규 leaf 모듈 `src/engine/pyramid_engine.py` + `boot_manager` 스폰 + `order_engine.execute_add_unit` 신설.**

| 선택지 | 판정 |
|---|---|
| (a) `check_buy_signal` 매수 창 확장 | **단독 무효** — 보유 종목이 `risk.py:616`/`scheduler.py:2751`/`order_engine.py:226,230` 에서 먼저 걸러짐 |
| (b) `scheduler` 에 폴 루프 추가 | **물리적 불가** — `scheduler.py` 정확히 3,999행, AST 가 `== 3999` 단언 |
| (c) `risk.on_tick` 매수 분기 개방 | **위험** — `risk.py` 는 8영역이고 hot path. 틱마다 매수 판정은 폭주 축 신설 |
| **(d) 신규 leaf + `execute_add_unit`** | **채택** — cycle233 `account_risk_watcher` / cycle234 `uptime_monitor` 선례 |

### 3.3.1 `pyramid_engine.py` (신규 leaf, ~250L 예상)

```
ensure_pyramid_loop(registry, order_engine)        # 자기 종료 루프, boot 1회 스폰 + idempotent
  └─ 60초 주기 (09:30~15:00 KST)
     └─ for strategy in _PYRAMID_STRATEGIES(=("kojiro",)):        # 명시 상수
          for ticker, pos in list(strategy.state.positions.items()):
             1) 스탬프 검사   entry_atr>0 ∧ last_entry_price>0        else skip(no_stamp)
             2) D0 검사      pos.buy_date < today                     else skip(d0)
             3) 트리거       strategy.check_add_signal(...)  == 0 → skip(no_trigger)
             4) 게이트 8종   strategy.check_add_gates(ticker)         # §3.3.2
             5) 수량        strategy.calc_add_quantity(ticker, price) # §3.4, ≥2주 아니면 0
             6) 발주        await order_engine.execute_add_unit(...)
```
- **`_swing_buy_poll_loop`(`scheduler.py:2726-2810`) 의 순차 계약 밖**이 되므로 신규 race 축이 생긴다.
  → 완화: 대상이 **보유 종목만**이고 `is_ticker_blocked_for_buy` 가 신규 매수를 여전히 차단하므로
  "같은 종목 신규매수 vs 추가매수" 충돌은 구조적으로 불가. 남는 것은 **추가↔추가 중복**뿐이고
  `pending_buys` per-ticker 가드(승격 후 `(ticker, order_no)`)가 이를 막는다.
- 예외는 전부 흡수 + `[pyramid_loop_error]` WARNING (fail-open — 추가가 안 되는 것이 청산 마비보다 낫다).

### 3.3.2 게이트 동등 재판정 (P5) — `kojiro.check_add_gates()`

`check_buy_signal:796~838` 의 게이트를 **같은 함수·같은 순서**로 재호출한다. 축별 처리:

| 게이트 | 추가 경로 처리 |
|---|---|
| `_account_soft_gate_blocked` | **동일 적용** (⚠️ 어젯밤 §2.6 ⑪ — 계좌 헤드룸 선점 문제는 §3.7) |
| `buy_disabled` | 동일 |
| `has_position` / `is_buy_pending` | **의미 반전** — `has_position` 은 *필수 조건*, `is_buy_pending` 은 여전히 차단 |
| `is_sold_today` | **동일 적용 (절대 뚫지 말 것)** — 손절 직후 재매수 = 진짜 물타기 |
| `_bought_today` | **미적용** (D0 금지가 이미 상위에서 처리) |
| `is_max_positions` | **미적용** (신규 종목이 아님) — 대신 `unit_count < max_units_per_stock` |
| `is_daily_loss_exceeded` | 동일 |
| `_is_open_risk_capped` | **동일 적용** — 여기가 4유닛의 실효 브레이크(§3.7) |
| 섹터 캡 | **유닛 단위로 전환**(§3.6) |

> ### ⚠️ 최종본 추가 — P5 가 구조적으로 은폐한 게이트 4종
> **P5("기존 8종을 동일 함수·동일 순서로 재판정")는 필요조건이지 충분조건이 아니다.**
> 기존 `check_buy_signal` 은 **보유 종목을 다룬 적이 없으므로** 보유 종목에만 필요한 게이트가 목록에 있을 리 없다.
> 아래 4종은 **추가 경로에만 필요한 신규 게이트**이고, 초판 표에는 한 줄도 없었다.
>
> | 신규 게이트 | 왜 필요한가 | 근거 |
> |---|---|---|
> | `ticker not in order_engine._selling` | `execute_sell`(`order_engine.py:494-527`)은 `_selling`·`SellRejectionTracker` 만 보고 **`is_buy_pending` 을 검사하지 않는다**. 매도 발사 직후~체결통보 도착 전 창에서 60초 leaf 가 추가를 발주할 수 있다. `risk.on_tick` 은 이미 `if ticker in self.order_engine._selling: continue`(`risk.py:593`)로 막고 있는데 leaf 에는 그 대응물이 없다 | `order_engine.py:508-527` · `risk.py:593` |
> | `not order_engine._sell_rejection.is_blocked(ticker, now)` | 이 플래그가 켜진 종목 = **"지금 청산이 거부돼 팔 수 없음이 증명된"** 종목이다. 소비처는 매도 진입 게이트(`order_engine.py:519`)뿐이라 매수 축에는 아무 효과가 없다. 10:00 손절 거부(5분 TTL) → 10:02 반등 +1N → 추가 발주가 **어느 게이트에도 안 걸린다.** APBK0918 매도 거부는 최근 17영업일 중 8일 실측 | `order_engine.py:519` · CLAUDE.md NXT 좀비 차단 |
> | `get_effective_stop_price(ticker) < current_price` (read-only 미러) | 청산 신호가 이미 성립한 포지션에 유닛을 얹지 않는다. **부작용 0 인 미러만 호출**한다(VCP/BFB 의 `_effective_setup(observe=False)` 선례 — cap 선소비 차단) | `kojiro.py:993-1070` · cycle233 미러 |
> | `ticker_last_tick` 신선도 ≤ 60~120s | leaf 의 가격 소스는 `scanner.ticker_prices[t]["current_price"]`(WS 틱 + `_run_swing_rest_poll_once`)인데 **신선도 게이트가 없으면 stale 가격으로 발주**한다. cycle239 `_GATE_STALE_MAX_SECS` 선례를 그대로 답습 | `scanner.ticker_last_tick` · `account_risk_watcher.py:105` |
>
> **이 4종은 "P5 재판정" 과 성격이 다르다** — 재판정은 *기존 계약의 보존*이고, 이 4종은 *신규 계약의 신설*이다.
> 따라서 뮤테이션 실증도 별도로 해야 한다(게이트 1개씩 제거 → 각각 FAIL).

**AST 가드 확장 필수** — `test_cycle233_ast_account_risk.py` 의 G-1 을 `check_add_gates` 로 확장하고,
**게이트 1개씩 제거 → 각각 FAIL** 뮤테이션을 실증한다(cycle224 "정의상 항상 참인 가드" 재발 방지).

### 3.3.3 `order_engine.execute_add_unit()` (8영역 접촉 1곳)

`execute_buy` 를 **복사하지 않고** 공통부를 추출한다:
```
execute_buy(...)        = _guard_new_position(...) + _place_and_track(...)
execute_add_unit(...)   = _guard_add_unit(...)     + _place_and_track(...)
```
- `_place_and_track` = 발주 → **매핑 동기 등록**(`_order_qty`/`_order_strategy`/`_order_ticker`/`_pending_buy_orders`, order_no 키라 안전) → `insert_trade` → 취소 타이머.
  ⚠️ **A-ATOMIC** — `calc_add_quantity` ↔ `pending_buys.add` 사이 `await` 0건 유지. AST 가드를 새 함수로 확장.
- `_guard_add_unit` = `has_position` **필수** + `is_buy_pending` 차단 + `is_sold_today` 차단.

### 3.3.4 ticker 단일 키 4종 승격 (P-1b / P-3)

| 대상 | 현행 | 변경 |
|---|---|---|
| `pending_buys: set[str]` | `strategy_base.py:73` | `dict[str, set[str]]` (ticker → order_no 집합) + `is_buy_pending` = 비어있지 않음 |
| `pending_buy_amounts: dict[str,int]` | `strategy_base.py:91` | `dict[tuple[str,str], int]` 또는 ticker → dict[order_no,int]. **합산 소비**(`_calc_used_funds:426-428`) |
| `_pending_cancel_tasks: dict[str,Task]` | `order_engine.py:78` 선언 · 매수 `:1467-1485` · **매도 `:1491-1522`** | `dict[str, Task]` **키를 order_no 로** — 초판은 "추가↔추가" 충돌만 봤으나 실제로는 **매수취소와 매도취소+재주문이 같은 dict 를 공유**한다(아래) |

> ### ⚠️ 최종본 정정 — `_pending_cancel_tasks` 는 매수/매도 **교차 살해**다
> 선언은 한 줄뿐이다: `self._pending_cancel_tasks: dict[str, asyncio.Task] = {}  # ticker -> 취소 대기 태스크`(`order_engine.py:78`).
> 그런데 이 dict 를 **두 개의 다른 목적**이 같은 replace 패턴으로 쓴다 —
> `_schedule_cancel`(매수 잔량 30초 취소, `:1467-1468` `if ticker in ...: [ticker].cancel()`) 과
> `_schedule_cancel_and_reorder`(매도 잔량 취소 + 손절 재주문, `:1491-1492` **동일 패턴**).
>
> **현행이 안전한 이유는 "한 종목에 매수·매도 주문이 동시에 존재할 수 없다" 는 전제 하나뿐**이고,
> 피라미딩은 **정확히 그 전제를 제거한다.** 실현 경로:
> `09:40 추가 발주 → _schedule_cancel 등록` → `09:40:20 반전, 손절 발화 → execute_sell → 매도 부분체결`
> → `_schedule_cancel_and_reorder 가 _pending_cancel_tasks[ticker].cancel()` = **추가주문 취소 타이머 사망**
> → 미체결 추가 매수주문이 KIS 에 잔존 → 매도 전량 체결로 포지션 소멸
> → 잔존 매수주문 체결 → `_handle_buy_fill` 의 `if not pos:` 분기(`:1188`)가 **방금 손절한 종목을 신규 포지션으로 재등록**.
>
> → **order_no 키 승격은 매수 경로만이 아니라 매도 경로(`:1491`,`:1519-1522`)까지 포함**해야 한다. C-2 의 범위를 넓힌다.
| `discard` 위치 | `order_engine.py:1216-1217` (분기 **앞**) | **전량 체결 분기 안으로 이동** |

⚠️ `is_max_positions`(`strategy_base.py:402-405`)가 `len(pending_buys)` 를 세므로
**dict 승격 시 카운트 의미가 바뀐다** — `len()` 대신 "주문 진행 중 ticker 수" 로 명시.

### 3.3.5 `update_trade_status` order_no 필터 (P-2)

`trade_history.py:88-125` 에 `order_no: str | None = None` 인자 추가 → WHERE 에 `AND order_no = $n`.
호출부를 전수 전환하거나, 체결 경로는 이미 존재하는 `_update_trade_status_by_order_no`(`:179-`)로 **정본 이관**.
`mark_pending_buys_completed`(`:247-266`)도 동형 시정.
⚠️ 취소 경로(`order_engine.py:1474`)와 sync(`scheduler.py:3633`)가 **같은 WHERE 를 공유**하므로 셋을 함께 본다.

## 3.4 (d) 사이징

> ### ⚠️ 최종본 정정 — 초판 스니펫은 **자기 원칙 P3 를 위반**했다
> 초판은 마지막 줄에서 `return self._apply_budget_limit(qty, ...)` 를 **무조건** 실행했다.
> 그런데 실제 관문은 (`strategy_base.py:472-474`, 실측):
> ```python
> if qty <= 0:
>     final = self._fallback_one_share(current_price)
> ```
> 즉 **per-ticker 캡이 qty 를 0 으로 깎는 바로 그 순간에 1주 폴백으로 낙하한다** — P3 가 절대 금지한 경로를,
> 캡이 발동하는 순간에 부른다. 둘째 결함: 초판은 `if qty < 2: return 0` 을 **캡 클램프보다 앞**에 뒀다.
> qty=5 가 하한을 통과한 뒤 캡이 1로 깎으면 `_apply_budget_limit(1, …)` 로 **1주 추가가 그대로 발주**된다.
> 하한 검사가 최종 수량이 아니라 중간 수량에 걸려 있어 무력했다. 산문(표)과 코드가 정면 모순이었고,
> **구현자는 표가 아니라 코드를 복사한다.** 아래가 정정본이다.

```python
def calc_add_quantity(self, ticker: str, current_price: int) -> int:
    pos = self.state.positions.get(ticker)
    if pos is None or pos.entry_atr <= 0 or pos.last_entry_price <= 0:
        return 0                                   # P2 미스탬프 → 추가 없음
    budget = self.state.total_investment
    ratio  = float(self.config.params.get("position_ratio", 0) or 0)
    max_u  = int(self.config.params.get(_PYRAMID_MAX_UNITS_KEY, 0) or 0)   # §3.6 신규 키
    if max_u <= 1 or ratio <= 0 or pos.unit_count >= max_u:
        return 0
    # ① 유닛 수량 — 진입 N 고정 (P2). live ATR 금지
    qty = compute_unit_qty(budget, pos.entry_atr, self.config.params["risk_pct"])
    # ② per-ticker **누적** notional 캡 (turtle_sizing 의 호출당 상한을 대체)
    cap = int(budget * ratio * max_u)
    room = max(0, cap - pos.buy_price * pos.quantity)
    qty = min(qty, room // current_price)
    # ③ 전용 관문 — 내부에서 _apply_budget_limit 호출 후 **최종 수량**에 2주 하한 적용
    return self._apply_add_budget_limit(qty, current_price, ticker)
```
```python
def _apply_add_budget_limit(self, qty: int, current_price: int, ticker: str | None) -> int:
    """추가매수 전용 예산 관문. `_apply_budget_limit` 을 경유하되 **1주 폴백을 흡수**한다.

    - 신규매수 관문(`_apply_budget_limit`)의 "0 → `_fallback_one_share` 위임" 분기 순서는
      **계약이므로 건드리지 않는다**(`strategy_base.py:473-474`). 대신 그 위에 얇게 덮는다.
    - A-PURE 동일 제약: await/DB/HTTP 절대 금지.
    """
    if qty <= 0:
        return 0                                   # ← 관문 위임 자체를 안 한다 (P3)
    final = self._apply_budget_limit(qty, current_price, ticker)
    return final if final >= _ADD_MIN_SHARES else 0   # _ADD_MIN_SHARES = 2 (모듈 상수)
```

| 결정 | 값 / 규칙 | 근거 |
|---|---|---|
| **1주 폴백 차단 지점** | `qty <= 0` 이면 **관문을 호출하지 않는다** + 관문 결과가 `< 2` 면 0 | 관문 안에서 막으면 `_apply_budget_limit:473-474` 계약(신규매수 경로)을 깨뜨린다 |
| **2주 하한 적용 순서** | 캡·잔여 클램프 **전부 끝난 최종 수량**에 적용 | 초판처럼 중간 수량에 걸면 무력 |
| **A-GATE 확장 대상** | `calc_add_quantity` 는 `_apply_add_budget_limit` 경유를 요구하고, `_apply_add_budget_limit` 은 `_apply_budget_limit` 경유를 요구하는 **2단 가드** | 초판대로 A-GATE 를 `calc_add_quantity` 에 그대로 확장하면 `final if final>=2 else 0`(Call 노드 아님)이 **FAIL** — 가드와 규칙이 배타적이었다(`test_budget_limit_ast.py:120-147` 실측: 상수 0 외 모든 return 이 `_apply_budget_limit` **Call** 이어야 함) |

| 추가 유닛의 N | **`pos.entry_atr` 고정** (live ATR 금지) | P2 — 눈금과 사이징의 N 이 같아야 커플링 불변식 성립 |
| 하한 | **2주** (G2′) | 1주는 유닛 정의가 붕괴 |
| per-ticker 캡 | `position_ratio × 예산 × max_units_per_stock` − 기보유 명목 | `turtle_sizing.py:78-79` 의 호출당 상한은 누적을 못 봄 |
| 관문 | `_apply_budget_limit` **반드시 경유** | AST A-GATE 를 `calc_add_quantity` 로 **확장**(현행 가드는 `calc_buy_quantity` 만 검사 = 조용한 우회 구멍) |
| 순수성 | 유닛 수는 **메모리 `Position` 필드**로만 읽음. DB/HTTP 금지 | AST A-PURE/A-ATOMIC |

## 3.5 (e) 손절 세트 관리

**핵심: 새 규칙 신설이 아니라 기존 `max()` 에 항 하나를 더한다.**
현행 청산 계층은 "먼저 관통된 선에서 return" 이라 이미 `max(가격선들)` 과 동치이고,
각 전략의 `get_effective_stop_price` / `_position_stop_price` 가 그 사실을 명시적으로 인정한다.

```
실효손절선 = max(
    turtle_set_line,      # ← 신규:  last_entry_price − stop_atr × entry_atr   (unit_count ≥ 2 일 때만)
    base_stop,            # 기존:  buy_price − stop_atr × ATR
    backstop_pct_line,    # 기존:  buy_price × (1 + hard_stop_pct/100)
    breakeven_line,       # 기존:  승격 시 buy_price
    chandelier_line,      # 기존:  high_since_buy − trail_atr × ATR
)
```

| 항목 | 결정 | 근거 |
|---|---|---|
| 세트선 활성 조건 | `unit_count >= 2` **∧** `entry_atr > 0` **∧** `last_entry_price > 0` | 1유닛 포지션의 손절 규약을 **byte 동일 보존**(도입 리스크 0) |
| 앵커 | `last_entry_price` (가중평단 **아님**) | 평단 앵커면 4유닛 스택 리스크가 5N → 8N (예산 2.5% → 4.0%, **+60%**) |
| N | `entry_atr` 고정 | 변동성 팽창 시 세트선이 느슨해지는 것 차단 |
| BE 승격 | **트리거·승격선 모두 `buy_price` 유지**(현행 그대로). 세트선과는 `max()` 로 경합 | 평단이 오르면 승격선도 자동으로 오른다 = tighten 방향. ⚠️ 4유닛 완성 시점(high=P+3N, 평단 P+1.5N)에는 `high ≥ 평단+1.5N` = `P+3N ≥ P+3N` **경계에서 발화** — 1N 눈금은 이 정렬이 좋다(0.5N 눈금은 구조적 미발화, 어젯밤 §0.1 정정2) |
| `_stop_floor` 래칫 | **유지**(tighten-only `max()`) | 하락 중 평단 하락에도 floor 미하강 = 물타기 방지. 유일하게 우리 편인 기존 기제 |
| `high_since_buy` | 추가 시 **유지**(리셋 금지) — DB 경로 포함 | `order_engine.py:1298` 이 미전달이라 **현재 리셋된다**. §3.1.4 가 이를 닫음 |
| 미러 동시 갱신 | `check_exit_signal` **과** `_position_stop_price`/`get_effective_stop_price` **양쪽** | 어긋나면 계좌 Σ리스크 게이트가 오측정(cycle233 커플링). kojiro 만 하면 2지점 |
| 가격 무관 계층 | 무변경 — kojiro §3 stage3, donchian 시간청산, BFB max_hold | 조기청산 = 보수 방향. ⚠️ 다만 **마지막 유닛의 기대 보유기간이 0 이 되는 구간**이 실재(§4 C-16) |
| VCP/BFB `turtle_min_stop_pct` min() 밴드 | **해당 없음**(대상 제외) | 만약 확장한다면 세트선은 min() **뒤**에 적용해야 조임이 무효화되지 않음 |

**세트선이 만드는 Σ리스크 궤적 (유닛×N 단위, `_open_risk_won` 식 `qty × (평단 − 세트선)` 로 검산)**

| 유닛 | 0.5N 사다리 세트선 / Σ리스크 | 1N 사다리 세트선 / Σ리스크 |
|---|---|---|
| 1 | P−2.0N / **2.00uN** (예산 1.00%) | P−2.0N / **2.00uN** (1.00%) |
| 2 | P−1.5N / 3.50uN (1.75%) | P−1.0N / 3.00uN (1.50%) |
| 3 | P−1.0N / 4.50uN (2.25%) | P+0.0N / 3.00uN (1.50%) |
| 4 | P−0.5N / **5.00uN (2.50%)** | P+1.0N / **2.00uN (1.00%)** |
| BE 승격 후(선=평단) | 0 | 0 |

→ **1N 사다리는 유닛을 쌓아도 Σ리스크가 늘지 않는다**(peak 3uN, 완성 시 1유닛과 동일한 2uN).

**검산 — kojiro 는 세트선이 반드시 필요하다.**
kojiro `trail_atr 2.5 > stop_atr 2.0`(`kojiro.py:152-153` 실측)이라 샹들리에 `high−2.5N` 은
1N 눈금 4유닛 시점(high ≥ P+3N)에 `P+0.5N`, 세트선은 `P+3N−2N = P+1N` → **세트선이 0.5N 더 타이트**.
⚠️ **최종본 정정** — 초판은 "donchian(2.0/2.0)이면 샹들리에가 세트선을 자동으로 덮는다" 고 적었으나
**라이브 `donchian_swing.atr_trail_mult = 1.8`**(EC2 `strategy_config` 실측, cycle223 이탈값 잔존)이다.
1.8 < 2.0 이므로 `high−1.8N` 은 세트선 `last−2N` 을 **덮지 못한다** — T3 에서 donchian 을 확장한다면
세트선은 **신규 배선이 필요**하고 "자동으로 정합" 이 아니다.

### 3.5.1 ⚠️ 최종본 신설 — 세트선은 손절 *크기*가 아니라 **손절 확률**을 바꾼다 (초판 최대 누락)

위 표는 **손절이 발생했을 때의 손실 크기**만 잰다. `_open_risk_won`(`kojiro.py:1080-1088`)의 식
`qty × (buy_price − stop)` 이 정확히 그 값이고, `max_open_risk_pct`·계좌 SOFT 게이트가 소비하는 것도 그 값이다.
**그런데 세트선 `last_entry − 2N` 은 유닛 2에서 손절선을 `P−2N` → `P−1N` 으로 1N 끌어올린다**(위 표가 스스로 보여준다).
손절선을 올리면 **손절에 닿을 확률이 올라간다.** 초판은 이 축을 한 번도 재지 않았다.

**독립 재현 (EC2 read-only, 2026-09-03).** kojiro 유니버스 정의(전체상장 ∩ 시총 500억 ∩ 거래대금 10억, n=965)
∩ `min_vol_floor_pct=1.0` ∩ `stock_master_daily` 일봉. 3영업일 간격 합성 진입 **31,498 표본**, 보유 20영업일,
동일봉에서 저가 우선(= 보수적으로 손절 인정), 손절 배수 2.0N 고정.

| 구성 | 손절률 | 평균 손익 | 평균 유닛 | **유닛당** 손익 | **고정2N 생존 → 사다리 손절 전환** |
|---|---|---|---|---|---|
| base (1유닛, 고정 2N) | **53.0%** | +0.170 uN | 1.00 | +0.170 | — |
| **1N 사다리 × 2유닛** (= Stage 2a) | **64.8%** | +0.437 uN | 1.61 | +0.271 | **11.7%** |
| **1N 사다리 × 4유닛** (= Stage 2c) | **75.3%** | +0.556 uN | 2.23 | +0.249 | **22.3%** |
| 0.5N 사다리 × 4유닛 | 71.3% | +0.954 uN | 2.82 | +0.338 | 18.2% |

**읽는 법 4.**
1. **1N×4 는 "고정 2N 이면 살아남았을 포지션의 22.3%" 를 손절로 전환한다.** 대표 경로는
   `P → P+1N(추가) → P−1N`: 피라미딩이 없으면 미손절 보유, 있으면 u1 −1N + u2 −2N = **−3uN 실현**.
   5,000만 기준 1uN = 75,000원 → **건당 −225,000원**.
2. **이 축은 시스템의 어떤 게이트에도 안 잡힌다.** `max_open_risk_pct`(크기) · `account_risk_guard`(실효 손절선 기반, 역시 크기) ·
   `daily_loss_limit`(realized 사후) 전부 **손절 빈도에 맹목**이다. 관측 마커도 없다.
3. **초판의 두 절이 같은 현상을 반대로 설명하고 있었다.** §5.2 는 1N 의 유닛당 Δ 가 0.5N 보다 **나쁘다**
   (−1.87R vs −1.51R)고 관측하고 원인을 "용량" 으로 귀인했는데, **실제 기전이 이것**이다 —
   1N 사다리는 유닛 2에서 손절선을 0.5N 사다리보다 **0.5N 더 끌어올린다**(§3.5 표: `P−1.0N` vs `P−1.5N`).
   위 재현에서도 1N×4 손절률(75.3%)이 0.5N×4(71.3%)보다 **높다** — 같은 방향이다.
4. **그러나 반대 방향 증거도 같은 표에 있다** — 평균 손익 자체는 **개선**된다(+0.170 → +0.556 uN,
   유닛당 +0.170 → +0.249). 즉 세트선은 **"승률을 팔아 손익비를 산다"**. 이것이 추세추종의 본래 거래이고,
   그 거래가 유리한지는 **오른쪽 꼬리가 실제로 붙는가**에 달렸다 — 정확히 G12(결합 청산 백테스트)가 재는 것.

**설계에 미치는 결론 3.**
- **`max_units` 를 2 → 3 → 4 로 올리는 단계적 롤아웃 자체가 이 위험의 완화 수단이다.**
  전환률이 유닛 수의 단조 함수(11.7% @2 → 22.3% @4)이므로, **각 단계에서 실측할 수 있다.**
  → §3.9 Stage 2 의 승급 조건에 **"손절률 변화" 를 명시 지표로 추가**한다(아래 §3.9 정정).
- **`[kojiro_pyramid_stop_shift]` 관측 신설** — 추가가 일어난 포지션에 대해
  `(고정2N 손절선, 세트선, 실제 청산가)` 3값을 청산 시 1행 기록. D+1 에 "세트선이 없었으면 살았는가" 를
  사후 판정할 수 있는 **유일한** 필드이고, 비용은 로그 1행이다.
- **세트선을 "안전장치" 라고 부르지 않는다.** 세트선은 *스택의 최대 손실을 상한*하는 장치이지
  *손실 빈도를 줄이는* 장치가 아니다. 초판 §3.5 의 "1N 은 Σ리스크가 안 늘어 안전" 문장은
  **"Σ리스크가 안 늘 뿐, 손절 빈도는 는다"** 로 교체한다.

## 3.6 (f) 유닛 상한 · 상관군 캡

| 항목 | 현행 | 변경 |
|---|---|---|
| 종목당 유닛 | `max_units_per_stock=2` **dead** (`kojiro.py:209`) | **실배선.** Stage 1 = `1`(다크런치) → Stage 2 = `4`(책 값). `PARAM_RANGES`/`INT_PARAMS` **미편입**(리스크 정체성 상수) |
| 전체 유닛 | `max_units_total=10` **dead** (`:210`) | 실배선, 책 값 **12** 로 정정 |
| 섹터 캡 | `max_positions_per_stock`… 아니라 `max_positions_per_sector=2` **종목 개수** (`:175`, 소비 `:823-838`) | **유닛 카운트로 전환** — `same = Σ unit_count` , cap = **6**(책 "높은 상관 군"). 현행 개수 2 × 4유닛 = **8유닛 허용**은 R15 위반 |
| 유닛 수 진실원 | 없음 (`quantity ÷ 유닛수량` 은 ATR 변동으로 불안정) | **`pos.unit_count`** 단일 진실원 (§3.1.2) |
| `is_max_positions` | 개수 캡 유지 | **대체 금지** — 저ATR 종목 포지션 수 폭증 차단 (CLAUDE.md 독트린) |

> ### ⚠️ 최종본 정정 3 — 위 표의 전제 세 개가 라이브와 어긋난다
>
> **① `max_units_per_stock` 은 dead 가 아니라 *DB 에 값이 살아 있다*.**
> EC2 실측(`strategy_config` kojiro row): `params->>'max_units_per_stock' = "2"`, `max_units_total = "10"`,
> **nkeys=34 = DEFAULT_PARAMS 전체가 병합된 dict 가 그대로 영속**돼 있다.
> 기전 = `kojiro.__init__` 의 `merged = {**DEFAULT_PARAMS, **config.params}`(`kojiro.py:214`) 로 config 가 병합본이 되고,
> `save_params(strategy_id, strategy.config.params)`(`recommendation_engine.py:661` · `routes/recommendations.py:184` ·
> `routes/strategies.py:182`)가 **그 병합본 전체를 쓴다.** 부팅 시 `_load_strategy_config`(`scheduler.py:405+`)의
> `if key in strategy.config.params: strategy.config.params[key] = val` 이 **DB 값으로 코드 기본값을 덮는다.**
> → **코드 기본값을 `1` 로 낮추는 방식의 다크런치는 성립하지 않는다.** 첫 배포에서 곧바로 **2유닛이 실발화**한다.
>
> **② 다크 스위치는 DB 에 *없는 새 키* 여야 한다.** cycle233 `account_risk_block_pct=None` 선례 동형.
> ```
> _PYRAMID_MAX_UNITS_KEY = "pyramid_max_units"   # 신규 키, DEFAULT_PARAMS 기본 0 = 비활성
> _PYRAMID_STRATEGIES    = ()                    # 모듈 상수, Stage 2 에서 ("kojiro",) 로
> ```
> 레거시 `max_units_*` 두 키는 **읽지 않는다**(오인 방지). 부팅 시 그 키의 DB 존재를 `[pyramid_param_anomaly]` 로
> **관찰만** 한다(자동 삭제 금지 — cycle218 "조용한 정규화 금지" 독트린).
> 대안으로 "배포 선행 DB UPDATE" 를 택한다면 그 UPDATE 를 **게이트 문안에 명시**해야 한다(구두 합의 금지).
> ⚠️ 초판의 "전체 유닛 … 책 값 **12** 로 정정" 도 같은 함정 — 그 값을 DB 에 쓰는 순간 되돌리기 어렵다.
>
> **③ 섹터 캡을 "유닛 6" 으로 바꾸는 것은 조임이 아니라 *오늘 대비 3배 완화* 다.**
> 현행은 종목 개수 2 이고 **오늘은 1포지션 = 1유닛이 항등**이므로 실질 **2유닛**이다.
> 초판은 "4유닛 시 섹터당 8유닛 허용 → cap 6" 이라고 *가상 상한 8 대비*로만 서술해 **완화 사실이 드러나지 않았다.**
> 두 서술 다 참이다: **가상 4유닛 세계 대비로는 조임(8→6), 오늘 대비로는 3배 완화(2→6).** 둘 다 적어야 한다.
>
> **④ 그 섹터 캡 자체가 유니버스의 29.5% 에서 fail-open 이다.**
> `_kojiro_sector_key`(`kojiro.py:69-87`)는 KRX 산업지수 12플래그 → `bstp_larg_div_code` → `bstp_medm_div_code` →
> `미분류-{ticker}`(독립 키) 순이고, 소비처(`kojiro.py:825`)가 `if cand_sector and not str(cand_sector).startswith("미분류")`
> 로 **미분류를 통째로 우회**한다. EC2 실측(n=965, 키 29종):
>
> | 섹터 키 | 종목 수 | 비중 | 성격 |
> |---|---|---|---|
> | **미분류-{ticker}** | **285** | **29.5%** | **캡 미적용 (fail-open)** |
> | 업종-1009 | 229 | 23.7% | catch-all 대형 버킷 |
> | 업종-0027 | 130 | 13.5% | catch-all 대형 버킷 |
> | 바이오 · 에너지화학 · 반도체 · 조선 … (명명 12) | 각 18~39 | 합 ~20% | 실질 의미 있는 클러스터 |
>
> → **"29.5% 캡 없음 + 37% 는 상관 의미 없는 거대 버킷"** 이라 한국 중소형주 폭락일 상관 1 수렴을 막을 구조가 아니다.
> §3.7 이 "1N 롤아웃의 사실상 유일한 상관 통제축" 이라고 지목한 것이 이것인데, **그 축이 종이다.**
> → **G11 문안 강화**: 유닛 전환에 더해 **① 미분류를 fail-open 이 아니라 `[pyramid_sector_unknown]` 관측 + 보수 처리
> ② catch-all 업종-1009/0027 을 캡 대상에서 분리**할지 결정해야 한다. 이건 별도 자문 사안으로 등재한다.
>
> **⑤ `max_units_total` 은 어떤 값을 넣어도 바인딩하지 않는다.** 5,000만 기준 유닛 명목이 예산의
> 9.7%(ATR 5.18%) ~ 16.6%(ρ클램프)이므로 12유닛 = 예산 116~199% > 100% → **예산 클램프가 항상 먼저 문다.**
> 즉 제안된 세 캡(종목4 / 전체12 / 섹터6) 중 **실효 제동은 종목4 하나뿐**이고 나머지 둘은
> "안전장치 모양의 비구속 상수" 다 — 지금 `max_units_per_stock=2`/`max_units_total=10` 이 dead 인 것과 **같은 함정을 새로 만든다.**
> → 배선한다면 **비구속임을 주석과 UI 에 명시**하거나, 아예 넣지 않는다.

⚠️ **`max_units_per_stock` 을 4 로 올리는 것과 `max_open_risk_pct` 를 올리는 것은 같은 사이클에 하지 않는다.**
전자만 하면 실질 1.8스택에서 멈추고(안전), 둘 다 하면 집중도가 한 번에 4배 뛴다.

## 3.7 (g) 계좌 Σ상한 · `max_open_risk_pct` 정합

| 축 | 값 | 스택이 먹는 양 (peak 기준) |
|---|---|---|
| kojiro Σ오픈리스크 캡 `max_open_risk_pct` = 4.5% (예산) | 34,859원@258만 / 675,000원@5,000만 | **0.5N: peak 2.50% → 1.80 스택** / **1N: peak 1.50% → 3.00 스택** |
| **예산 명목 상한** `total_investment` | 예산 100% | 4유닛 = 예산 **43.3%** → **2.31 스택** (사다리 무관) |
| 계좌 SOFT Σ상한 `account_risk_block_pct` | **None = 다크런치** | 활성(6.0) 시 스택 1개 = 계좌 0.30~0.75% → 8~20스택. **선점 위험 낮음** |

⚠️ **중요 — 1N 사다리에서는 Σ리스크 캡이 실효 브레이크가 아니다.**
1N 은 유닛을 쌓아도 Σ리스크가 늘지 않으므로(§3.5 표) 캡 4.5%는 3.0스택까지 허용하는 반면
**예산 명목 상한이 2.31스택에서 먼저 물린다**. 즉 1N 롤아웃에서 집중도를 실제로 제한하는 것은
**리스크 캡이 아니라 예산 클램프**이고, 이는 "리스크 균등" 이 아니라 "명목 균등" 축이다.
→ **유닛-섹터 캡(§3.6, cap 6유닛)이 1N 롤아웃에서는 T2 전제가 아니라 사실상 유일한 상관 통제축이다.**

**결정 3.**
1. **`max_open_risk_pct` 4.5 유지 (Stage 2 진입 시).** 0.5N 이면 1.8스택에서 자동 제동되고,
   1N 이면 예산 클램프가 2.31스택에서 제동한다. **어느 쪽이든 첫 실가동의 집중도는 ≤3종목**이다.
2. **캡 상향(6~8)은 §3.6 유닛-섹터 캡 배포 + N≥10 스택 관측 후 별도 사이클.**
   (로드맵 규칙 4 · cycle232 결정: heat 상향은 상관군 캡이 전제.)
3. **계좌 SOFT 게이트는 추가 경로에도 동일 적용**하되, 헤드룸 선점을 관측한다 —
   `[pyramid_account_headroom]` 로 "추가가 소비한 계좌 헤드룸 비율" 을 20:10 metrics 에 기록.
   6% 근처를 한 스택이 채워 나머지 6전략을 굶기는지 **실측으로 판정**(어젯밤 §2.6 ⑪).

## 3.8 (h) 관측 · 대시보드 · 리포트 · 귀속

| 항목 | 설계 |
|---|---|
| 마커 | `[kojiro_pyramid_add] ticker=.. unit_no=2 level=.. price=.. qty=.. entry_atr=.. set_stop=..` / `[kojiro_pyramid_skip] reason=no_stamp\|d0\|no_trigger\|gate_<name>\|below_2shares\|unit_cap\|sector_unit_cap\|risk_cap\|budget\|window_closed` |
| cap 키 | **`(ticker, unit_no)`** — 기존 `DailyEmitCap` 은 ticker 단일 키라 재사용하면 2번째 이후 유닛이 통째로 사라짐 |
| cap 계약 | **로그에만.** 발주·세트선 갱신은 cap 밖 (P6 / cycle237) |
| 관측기 실패 | `_trace_observer_failure` WARNING 1행 (`logger.debug` 단독은 `_DbLogHandler` INFO 컷을 못 넘어 무음과 구별 불가) |
| write_log 병용 금지 | `logger.info` 단독 (AST `test_cycle72_ast_no_logger_write_log_pair.py`) |
| 20:10 리포트 | `metrics["pyramiding"] = {would_add_by_ticker, adds_executed, units_by_ticker, skip_reasons, latch_age_sec, account_headroom_consumed_pct}` — JSONB 라 **마이그레이션 불요**(`migrations/013:9`), 삽입 `log_analysis_engine.py:678-688`, 집계기는 `_aggregate_tick_blind`(`:309-330`) 답습 |
| `trade_history` 귀속 | **무변경** — 유닛별 order_no 행이 정상 공존(`migrations/029:29-31`), `get_trade_pairs` 가 이미 가중평균 페어링(`trade_history.py:624-648`). **단 P-2 시정이 선행**(안 하면 1차 체결이 2차 PENDING 행까지 뒤집음) |
| `daily_performance` | **무변경** — SELL `profit_loss` 합 구조 그대로. 단 `profit_loss` 정확도가 `pos.buy_price` 하나에 의존 → P-1 시정이 곧 손익 정확도 |
| 프론트 | `PositionDetail` 에 `unit_count` 추가 (`frontend/src/types/trading.ts:150-156`) → 생산자 2곳(`strategy_registry.py:108-118` · `scheduler.py:1253-1263` — **이미 불일치**) 정합 → `OrderMonitor.tsx` 배지 → MSW `handlers.ts` + `e2e/fixtures/api-mocks.ts` |
| `PortfolioRisk` | `over_cap_positions` 의 cap 정의를 `ratio × 예산 × unit_count` 로 확장 (`portfolio_risk.py:226-271`) — 안 하면 4유닛 정상 스택이 **매일 이상 신호** |
| `_emit_oversized_fallback` | 동일 확장 (`strategy_base.py:492-533`) |

## 3.9 (i) 롤아웃 3단계

### **Stage 0 — 관측 전용 (지금 착수 가능, 자본 무관)**

| 항목 | 내용 |
|---|---|
| 목적 | ⚠️ **최종본 정정** — 초판은 *"장중에 1N 눈금이 MAE 관통보다 먼저 오는가"* 라고 적었으나 **일봉 배치로는 그 질문에 원리적으로 답할 수 없다**(일봉은 고가·저가의 선후를 담지 않는다 — §5.4 한계 #6 이 스스로 그렇게 적어놓았다). 정정된 목적 = **① 눈금 도달 *빈도*(§5.2 의 1.571/왕복 가정을 실측 대체) ② 2주 하한 적격률 ③ 가상 세트선이 실제 청산가 대비 어디였는지**. 장중 *순서*를 재려면 틱 시각 훅이 필요하고 그건 Stage 1 leaf 의 부산물로 얻는다 — **Stage 0 의 목적이 아니다** |
| 구현 | ① `log_analysis_engine` 에 `_aggregate_pyramiding()` 배치 — 보유 종목의 당일 일봉으로 `would_add` 눈금 수·가상 세트선·2주 하한 통과 여부 산출 ② `metrics["pyramiding"]` 삽입 |
| 매매 행위 | **변경 0** |
| 접촉 파일 | `src/engine/log_analysis_engine.py` (비8영역) · `frontend/src/types/log_reports.ts` + `DailyReportTab.tsx` |
| 8영역 | **0** |
| 회귀 가드 | 배치 순수성 · 보유 0 시 빈 dict · 일봉 결손 graceful · 마커 파싱 |
| 예상 | **1 사이클** |
| ⚠️ | 보유 종목 일봉이 `stock_master_daily` 에 없으면 KIS 폴백 호출 발생(어젯밤 실측: 004690 이 08-21 에서 정지) — "KIS 호출 0" 이 아니다 |

### **Stage 0.5 — 1주 폴백 과잉 시정 (독립 사이클, 피라미딩과 무관하게 유효)**

| 항목 | 내용 |
|---|---|
| 목적 | **진입 시점의 무허가 과잉 피라미딩**을 닫는다. donchian 랏 평균 = **4.94 터틀유닛**(어젯밤 §0.0) |
| 선택지 | ⓐ 이론 유닛 <1주면 스킵 (깨끗하지만 donchian 거래 −79%) / ⓑ 폴백에 notional 상한 (거래 보존, 여전히 1유닛 초과 허용) |
| 권고 | **ⓑ 를 먼저, ⓐ 는 kojiro 한정 실험** — ⓐ 는 매매 빈도를 크게 바꾸므로 사용자 결정 사안 |
| 접촉 | `strategy_base.py` 한 곳 (**비8영역**) |
| 예상 | **1 사이클** |
| ⚠️ | 이것이 **피라미딩보다 크고 급하고 확실한 개선**이다. 고치기 전에 4유닛을 얹으면 15.6유닛짜리 "1유닛" 을 네 번 쌓는다 |

### **Stage 1 — 배관 + 다크런치 (게이트: net ≥ 500만 5영업일 연속)**

| 항목 | 내용 |
|---|---|
| 목적 | 결함 4건 시정 + 스키마·필드·경로를 **전부 깔되 `max_units_per_stock=1` 로 추가가 한 건도 발화하지 않게** |
| 사이클 1 | **P-1 + P-3** — 가중평단 병합 + `_pos_contrib` + ticker키 4종 승격 + `discard` 분기 이동. 8영역 = `order_engine`·`strategy_base`. 회귀 **12+**(§3.1.3 · §3.3.4) |
| 사이클 2 | **P-2** — `update_trade_status` order_no 필터 + `mark_pending_buys_completed` + 취소/sync 경로. 8영역 = `order_engine` 1곳 |
| 사이클 3 | **스키마 + 스탬프** — migration 042 + `Position` 3필드 + `save_position` 확장(+`high_since_buy` 명시) + 부팅 복원 4지점 + `[pyramid_stamp_lost]`. 8영역 = 0 (`boot_manager` 경유) |
| 사이클 4 | **경로 + 게이트 + 사이징** — `pyramid_engine.py` leaf + `check_add_signal`/`check_add_gates`/`calc_add_quantity` + `execute_add_unit` + AST 가드 확장 4종(A-GATE/A-ATOMIC/G-1/신규 유닛캡). `max_units_per_stock=1` = **행위 변경 0** |
| 사이클 5 | **세트선 + 관측 + UI** — `max()` 항 추가(2지점) + 마커 + 20:10 metrics + `over_cap` cap 정의 확장 + 프론트 `unit_count` |
| 8영역 | 사이클 1·2 에서 **`order_engine` 만** (승인 필요). ⚠️ **최종본 정정** — 초판은 같은 문서 안에서 `strategy_base.py` 를 한 번은 8영역, 한 번은 비8영역으로 적었다. **정답 = 비8영역.** 정본 목록(`test_cycle233_ast_account_risk.py:41-48`) = `risk`/`order_engine`/`session`/`scanner`/`strategy_registry`/`api.order` + `realtime/`·`auth/` 디렉토리. `strategy_base` 는 목록 밖 |
| 예상 | ⚠️ **최종본 정정: 5 → 8~10 사이클** (근거 아래) |

> ### ⚠️ 최종본 정정 — Stage 1 의 사이클 산정과 "행위 변경 0" 주장
>
> **① P-3(ticker 키 → order_no 축) 의 blast radius 가 초판 서술의 몇 배다.**
> `pending_buys` 참조 = **136건 / src 9파일 + 테스트 24파일** 실측(`grep -rn`).
> src = `order_engine`(8영역·sha 재핀·승인) · `strategy_base` · `strategy` · `scheduler`(**3,999행 동결 갱신 강제**) ·
> `boot_manager` · `strategy_registry`(8영역) · `strategies/kojiro` · `routes/trading` · `db/trade_history`.
> 초판 §3.3.4 는 `strategy_base:73`/`:91` + `order_engine:1465` **3곳만** 적시했다.
> 테스트 24파일이 `pending_buys.add(` / `= {` 로 직접 상태를 구성하므로 **전부 적응 대상**이다.
> → P-3 단독으로 **2~3 사이클**.
>
> **② `_place_and_track` 추출(§3.3.3)은 현행 A-ATOMIC 테스트를 즉시 FAIL 시킨다.**
> `test_budget_limit_ast.py:60-97` 은 **`execute_buy` 함수 본문 안에** `calc_buy_quantity` 호출 **과**
> `pending_buys.add` 가 **둘 다** 있어야 통과한다(`assert add_lines`). `pending_buys.add` 를 헬퍼로 옮기면
> 가드가 깨지고, 가드를 함수 경계를 넘어 재작성해야 한다.
> 그 함수는 이 프로젝트에서 **가장 많이 봉인된 함수**(8영역 + sha 핀 + 다수 회귀)다.
> → **행위 보존 리팩토링 별도 카드(HIGH)** 로 분리한다. 한 사이클의 하위 항목이 아니다.
>
> **③ §3.3.1 의사코드는 A-ATOMIC 을 *구조적으로* 깬다.**
> 초판 루프는 `5) calc_add_quantity(...)` → `6) await execute_add_unit(...)` → 내부 `await get_buyable` … →
> `pending_buys.add` 순서다. **사이징 read 와 pending 등록 사이에 await 이 여러 개** 있어
> C-8b 가 지키려는 원자성이 공허해진다(두 코루틴이 같은 잔여를 본다).
> **정정 = `execute_buy` 와 동일 배치** — 사이징을 마지막 await **뒤**, 관문 직후에 두고 즉시 등록한다
> (`order_engine.py:273 calc_buy_quantity → :314 pending_buys.add → :371 place_order` 실측 순서).
> leaf 는 "트리거 판정 + 게이트" 까지만 하고 **사이징은 `execute_add_unit` 안으로 들어간다.**
>
> **④ S1-1 과 S1-5 는 "행위 변경 0" 이 아니다.**
> - S1-1 의 `discard` 분기 이동(P-1b)은 `is_buy_pending` → `is_ticker_blocked_for_buy`(전략 횡단) ·
>   `is_max_positions` · `_calc_used_funds` 의 pending 수명을 **부분체결 구간까지 연장**한다
>   = 타 전략 매수 차단 + 사이징 축소라는 **부분체결 레짐의 실제 행위 변경**(257720 이 정확히 그 레짐).
>   → "행위 변경 있음 + D+1 관측 마커 동반" 으로 표기한다.
> - S1-5 는 세트선 `max()` 항(**행위**)과 마커·metrics·UI(**관측**)를 한 사이클에 묶어 **자기 원칙 P7 위반**이다.
>   → **S1-5a(관측 선행) / S1-5b(세트선 행위)** 로 분할한다.
>
> **⑤ `is_max_positions` 이중 계수.** `len(positions) + len(pending_buys)`(`strategy_base.py:402-405` 실측) 이므로
> **추가 주문 중인 종목은 양쪽에 동시 존재**해 신규 진입 슬롯이 한 칸 일찍 닫힌다.
> → `len(set(positions) | pending_keys)` 로 정정. 초판은 dict 승격 시 `len()` 의미 변화만 언급했다.
>
> **⑥ Σ오픈리스크·섹터 유닛 캡이 pending 추가를 계상하지 않는다.**
> `_open_risk_won`(`kojiro.py:1072-1089`)은 `state.positions` 만 순회한다. 한 leaf 패스에서 서로 다른 두 종목의
> 추가가 각각 상대의 pending 리스크를 못 보고 `_is_open_risk_capped` 를 통과할 수 있다(LIMIT 폴백·지연 체결 시 실재).
> 섹터 캡은 `set(positions) | set(pending_buys)`(`kojiro.py:827`) 합집합이라 **개수는 안전**하나
> 유닛 전환 시 **pending 유닛 수를 별도 계상**해야 한다.

### **Stage 2 — 실활성 (게이트: 아래 T2 전부)**

| 단계 | `max_units_per_stock` | 조건 |
|---|---|---|
| 2a | **2** | net ≥ 2,000만 · Stage 1 배포 후 2주 무사고 · `[pyramid_skip]` 사유 분포 정상 · **`[pyramid_stop_shift]` 로 손절률 변화 측정 개시**(§3.5.1) |
| 2b | **3** | 2a 에서 N ≥ 10 스택 · 세트선 발화 정상 · 계좌 헤드룸 선점 미관측 · **손절률 상승폭이 예측(11.7%p→) 범위 안** |
| 2c | **4** (책 값) | net ≥ 5,000만 · 2b 에서 N ≥ 20 · 유닛-섹터 캡 배포 완료 · **손절률 전환 22.3% 예측 대비 실측 확인** |
| 별도 | `max_open_risk_pct` 4.5 → 6~8 | 2c 이후 **별도 사이클** (§3.7) |

⚠️ **최종본 정정 — 자본 게이트가 문서 세 곳에서 서로 달랐다.** 초판 §3.9 Stage 2 표에는 자본 조건이 없고,
§6 도식은 `2a = net ≥ 2,000만` · `2c = net ≥ 5,000만` 이며, T2 게이트 표에는 자본 항목이 아예 없었다.
**정본 = 위 표**(2a 2,000만 / 2c 5,000만)로 통일하고 §6·T2 를 여기에 맞춘다.
그리고 **T1 의 G1(500만)은 "Stage 1 배관 착수" 게이트이지 "실활성" 게이트가 아니다** — §1.3 실측상
500만에서 kojiro 추가불가는 여전히 **20.2%**(EC2 재현 n=898)라 실활성 자본으로는 부족하다.
**⚠️ 그리고 자본 게이트는 §5.2 가 보여주듯 *실행 가능성*만 열지 *수익성*을 열지 않는다** — G3/G3′/G12 가 병렬 관문이다.

---

# 4. 충돌부분 상세정리

> 열: **충돌 · 근거(file:line) · 해소 방법 · 남는 위험 · 사이클**

## 4.1 배관·계약 충돌 (차단성)

| # | 충돌 | 근거 | 해소 | 남는 위험 | 사이클 |
|---|---|---|---|---|---|
| **C-1** | **P-1** 체결 병합 `pos.quantity = total_filled` 절대대입 → 2차 유닛이 1차를 소멸 | `order_engine.py:1210-1213`, `_filled_qty` order_no 키 `:79` | `_pos_contrib` 보조 맵 + 증분 가산 + 가중평단 (§3.1.3) | cycle235 overrun 클램프와의 증분/누적 의미론 혼선 → 회귀 필수 | S1-1 |
| **C-1b** | **P-1b** `pending_buys.discard` 가 전량/부분 분기 **앞** → 부분체결 후 3차 주문 창 | `order_engine.py:1216-1217` | discard 를 전량 분기 안으로 이동 | `is_max_positions` 의 `len(pending_buys)` 의미 변화 | S1-1 |
| **C-2** | **P-3** ticker 단일 키 4종 → 동일 종목 2주문 표현 불가. `_schedule_cancel` 이 1차 잔량취소를 `.cancel()` | `strategy_base.py:73`,`:91` · `order_engine.py:1465-1468` | order_no 축 승격 (§3.3.4) | `_calc_used_funds` 합산 누락 시 예산 이중 청약 | S1-1 |
| **C-3** | **P-2** `update_trade_status` WHERE 에 order_no·LIMIT 부재 → 1차 체결이 2차 PENDING 행까지 COMPLETED. 취소·sync 도 같은 WHERE | `trade_history.py:113-117` · `:247-266` · `order_engine.py:1474` · `scheduler.py:3633` | order_no 인자 추가 또는 `_update_trade_status_by_order_no`(`:179`) 정본화 | 호출부 전수 전환 누락 시 부분 적용 | S1-2 |
| **C-4** | **P-4** `check_budget_invariant` 가 params 만 읽어 실보유 유닛 미검사 | `portfolio_risk.py:273-305` · AST `test_budget_limit_ast.py:162-195` | 실보유 축 관측 신설(차단 아님) | 4유닛 시 불변식 위반이 조용함 | S1-5 |
| **C-5** | `is_ticker_blocked_for_buy` 의 "보유=차단" 이 4곳에서 독립 판정 | `strategy_registry.py:86-98` · `order_engine.py:226`,`:230` · `risk.py:616` · `scheduler.py:2751` | `execute_buy` 재사용 포기 → `execute_add_unit` 신설 (§3.3.3) | 신규매수 게이트와 추가 게이트가 **두 벌**이 되어 드리프트 | S1-4 |
| **C-6** | **매수 안전 게이트 8종이 전부 `check_buy_signal` 안** → 추가 경로가 전면 우회 | `kojiro.py:796-838` | `check_add_gates()` 동일 함수·순서 재판정 + 뮤테이션 실증 (§3.3.2) | 게이트 추가 시 두 곳 동기 의무 | S1-4 |
| **C-7** | cycle233 AST G-1 이 `check_buy_signal` `body[0]` 만 검사 → add 메서드를 못 봄 | `tests/unit/ast/test_cycle233_ast_account_risk.py:84`,`:96` | 가드를 `check_add_gates` 로 확장 | 제3의 위치 신설 시 재발 | S1-4 |
| **C-8** | **A-GATE** 가 `calc_buy_quantity` 만 검사 → `calc_add_quantity` 는 예산 관문 **조용한 우회** | `test_budget_limit_ast.py:120-147` | 가드 함수명 목록 확장 + `_apply_budget_limit` 경유 강제 | 신규 사이징 함수 추가 시 재발 | S1-4 |
| **C-8b** | **A-ATOMIC / A-PURE** — 사이징~pending 구간 await 0건, 관문 내 DB/HTTP 금지 | `test_budget_limit_ast.py:60-97`, `:99-118` · `strategy_base.py:470-473` | 유닛 수는 메모리 `Position` 필드로만. ATR 은 스탬프 | 추가 경로에서 실시간 ATR 조회 유혹 | S1-4 |
| **C-9** | `compute_unit_qty_guarded` notional 상한이 **호출당** → 2유닛째가 구조적으로 0주 | `turtle_sizing.py:78-79` | per-ticker 누적 캡으로 교체 (§3.4) | "터틀 수량 ≤ 비중 수량" 독트린 문구 갱신 필요 | S1-4 |
| **C-10** | `_fallback_one_share` 가 notional 상한 미검사 → 추가에서 쓰면 "4유닛" 이 12유닛 명목 | `strategy_base.py:431-445` | 추가 경로 **금지**(호출측 0=스킵) + 하한 2주 | 관문 분기 순서 계약(`:473-474`)을 건드리면 신규매수 회귀 | S0.5/S1-4 |
| **C-11** | `compute_over_cap_positions` / `_emit_oversized_fallback` 이 4유닛 정상 스택을 **매일 이상 신호로 오탐** | `portfolio_risk.py:226-271` · `strategy_base.py:492-533` | cap 정의를 `ratio × 예산 × unit_count` 로 확장 | 확장 전 배포 시 관측 신뢰도 붕괴 | S1-5 |
| **C-12** | `scheduler.py` 정확히 **3,999행**, AST `== 3999` 단언 | `wc -l` · `test_cycle241_ast_silent_inactive_relative.py:387-396` | 신규 leaf + `boot_manager` 스폰 (cycle233/234 선례) | `_SWING_POLL_STRATEGIES` 순차 보장 **밖** = 신규 race 축 | S1-4 |
| **C-13** | boot 가 당일 매수 종목을 `sold_today` 에 시드 → 재기동 1회로 D0 추가 영구 차단 | `boot_manager.py:272-286` | **D0 추가 금지 결정으로 회피**(§3.2) | D0 를 나중에 열려면 시드를 "재매수 차단" / "피라미딩" 으로 분해해야 함 | 회피 |
| **C-14** | `_reset_daily_state` 의 `positions.clear()` + kojiro `_stop_floor`/`_position_atr` 메모리 전용 | `scheduler.py:3806-3820` · `kojiro.py:231`,`:238` | 3컬럼 DB 영속 + 부팅 재구성 (§3.1.5) | KIS 잔고 복원 경로는 유닛 수 **원리적 불가** → 미스탬프 처리 | S1-3 |
| **C-15** | `save_position` 이 `high_since_buy` 미전달 → 추가 체결 시 **DB 고점이 새 매수가로 리셋** | `order_engine.py:1298-1302` · `positions.py:32` | 명시 전달 + 회귀(불감소 단언) | 다른 `save_position` 호출부도 같은 함정 | S1-3 |

## 4.2 매매 규약 충돌 (설계 결정 필요)

| # | 충돌 | 근거 | 해소 | 남는 위험 | 사이클 |
|---|---|---|---|---|---|
| **C-16** | 시간청산이 **최초 진입일 기준** → 마지막 유닛이 진입 직후 청산될 수 있음 | donchian `:1806-1826` · BFB `:1294-1302` · kojiro §3 `:938-957` | **수용**(세트 = 전량 동시 청산이 터틀 규약과 정합) + 관측 | 추가 유닛의 기대 보유기간이 0 이 되는 구간 실재 | 수용 |
| **C-17** | 가중평단을 하드손절 앵커로 쓰면 4유닛 리스크 5N → **8N**(예산 2.5%→4.0%) | `kojiro.py:913-914` 등 4전략 | 세트선을 `max()` 항으로 추가, 앵커 = `last_entry_price` (§3.5) | `max()` 항 누락 시 조용히 60% 리스크 증가 | S1-5 |
| **C-18** | BE 승격 트리거·승격선이 `buy_price` 앵커 → 평단 상승 시 임계가 밀림 | `kojiro.py:921-935` | **1N 눈금 채택으로 정렬 회복**(4유닛 시점 경계 발화). 0.5N 은 구조적 미발화 | 0.5N 으로 바꾸면 승격이 안 걸림 | 설계 |
| **C-19** | `_effective_atr` **live 우선** + `recompute_held_atr` 가 매 부팅 덮어씀 → 사다리 눈금이 매일 이동 | `kojiro.py:1043-1069` · `:765-776` | `entry_atr` 영속 컬럼 + **사다리/사이징 = entry_atr 고정 / 손절 N = 현행 유지** 명시 분리 | **두 개의 N 이 공존**한다 — CLAUDE.md 커플링 불변식("스탬프=사이징 ATR")과 kojiro live 독트린의 정면 충돌. 문서로 못박아야 | S1-3 |
| **C-20** | `max_positions_per_sector=2` 가 **종목 개수** → 4유닛 시 섹터당 **8유닛**(책 R15 "6" 초과) | `kojiro.py:175`, `:823-838` | 유닛 카운트 전환, cap 6 (§3.6) | `unit_count` 진실원이 흔들리면 캡 무의미 | S2 전 |
| **C-21** | `max_open_risk_pct` 4.5 ÷ 5N 2.5% = **1.80 스택** → 6종목 분산 → 실질 2종목 집중 | `kojiro.py:186`, `:969-991` | **의도된 브레이크로 유지.** 상향은 C-20 배포 후 별도 사이클 | 전략 정체성 전환(분산→집중)을 사용자가 수용해야 | 결정 |
| **C-22** | `position_ratio × max_positions ≤ 1.0` 불변식이 4유닛 시 **최대 4배 위반** (kojiro 0.996→3.98) | AST C-DEFAULT · `portfolio_risk.py:273-305` | 불변식을 `ratio × max_positions × max_units ≤ K` 로 **재정의**하거나, 유닛 축을 별도 캡으로 분리 | 재정의 없이 배포하면 가드가 오탐/침묵 | S1-5 |
| **C-23** | 매도 전량 전제 → 유닛별 부분 익절 불가 | `order_engine.py:494-500`, `:592` | **수용**(터틀 세트 청산과 정합) | BFB measured-move "절반 익절" 은 영구 미구현 | 수용 |
| **C-24** | 계좌 SOFT Σ상한이 7전략 공통 → 한 스택이 헤드룸을 선점하면 나머지 6전략 신규매수 굶김 | `account_risk_guard.py:35` · 소비 위치 이원화 | 추가에도 동일 적용 + `[pyramid_account_headroom]` 실측 후 판정 | 다크런치라 현재는 무해. 활성(6.0) 시 표면화 | S1-5 |
| **C-25** | 프리장 청산 보류가 `high_since_buy` 갱신까지 멈춤 | `risk.py:548-585`, 화이트리스트 `:79` = LTV 만 | 추가 시간창을 09:30~15:00 로 제한(§3.2) → 무관 | 세트선을 `high` 파생으로 두면 08:00~09:00 지연 | 회피 |
| **C-26** | `_handle_buy_fill` 폴백의 `is_ticker_held_by_any` → "보유중 매핑miss 매수 = 오염" 판정 | `order_engine.py:1163-1178` | 판정을 order_no 존재 여부 기준으로 전환 | 추가 유닛의 정상 체결이 조용히 버려짐 | S1-1 |

## 4.3 회계·관측·UI 충돌

| # | 충돌 | 근거 | 해소 | 남는 위험 | 사이클 |
|---|---|---|---|---|---|
| **C-27** | `profit_loss = (price − buy_price) × qty` **gross** — 수수료·세금 미반영. `daily_loss_limit` 도 gross | `order_engine.py:1387-1391` · `strategy_base.py:407-413` | **미해소.** 회전율 4배 변경을 gross 로 관리하게 됨 | 왕복 비용 = 1N 의 5.3~11.5%. 4유닛이면 절대액 4배 | 별도 등재 |
| **C-28** | `daily_loss_limit` 은 **realized** 기준 → 미실현 스택 붕괴를 못 막음 | `strategy_base.py:407-413` | **미해소**(계좌 드로다운 정지선이 담당할 영역, 미구현) | 190,000×4주 스택 하한가 손실이 게이트의 3.7배(어젯밤 §2.7) | 별도 등재 |
| **C-29** | `LogReportMetrics` 타입이 3키만 선언 → pyramiding 배치가 **UI 에 안 보임** | `frontend/src/types/log_reports.ts` · `DailyReportTab.tsx:105-106` | 타입 + 렌더 동반 갱신 | portfolio_risk_snapshot·tick_blind 가 이미 같은 이유로 미노출 | S0 |
| **C-30** | `PositionDetail` 생산자 2곳이 **이미 불일치**(buy_date/strategy_id) | `strategy_registry.py:108-118` vs `scheduler.py:1253-1263` · 타입 `trading.ts:150-156` | `unit_count` 추가 시 두 생산자 + 타입 + MSW + e2e 픽스처 동시 | scheduler 는 8영역이자 3,999행 동결 → **strategy_registry 쪽만** 확장 권고 | S1-5 |
| **C-31** | `system_logs` INFO retention **2일** | `src/db/CLAUDE.md` `purge_old_logs` | 20:10 metrics 수확 필수 | 수확 전 결손 시 증거 소멸 | S0 |
| **C-32** | `write_log` ±5줄 내 `logger.*` 금지 | AST `test_cycle72_ast_no_logger_write_log_pair.py` | 마커는 `logger.info` 단독 | — | S1-5 |
| **C-33** | `DailyEmitCap` ticker 단일 키 | cycle237 선례 | **`(ticker, unit_no)`** 키 | 재사용 시 2번째 이후 유닛 관측 소멸 | S1-5 |
| **C-34** | pg 왕복 통합 테스트가 positions 컬럼 정합 단언 | `tests/integration/test_cycleM1_1_pg_roundtrip.py:29-58` | migration 042 와 동반 갱신 | — | S1-3 |


## 4.4 ⚠️ 최종본 신설 — **런타임 상호작용** 충돌 (초판 통째 누락 축)

> 초판 4.1~4.3 은 **정적 계약**(AST 가드 · PK · 8영역 · 타입) 충돌을 잘 잡았다.
> 빠진 것은 **동시에 살아 있는 두 흐름이 서로를 밟는** 축이다 — 피라미딩은 시스템 역사상 처음으로
> "**한 종목에 매수 주문과 매도 주문이 동시에 존재**" 를 가능하게 만들고, 현행 코드의 여러 안전성이
> **그 불가능성에 암묵적으로 기대고 있다.** 아래는 전부 코드 실측으로 도달 경로를 확인한 것이다.

| # | 충돌 | 근거(file:line) | 해소 | 남는 위험 | 사이클 |
|---|---|---|---|---|---|
| **C-35** | **추가↔청산 인터리브 → 스탬프 없는 orphan 포지션.** 추가 PENDING 중 손절 발화 → `execute_sell` 이 구 `pos.quantity` 매도 → `_handle_sell_fill` 이 `del state.positions[ticker]` + `on_position_closed`(kojiro `_stop_floor`/`_position_atr`/`_held_stage3` pop) + `sold_today.add` → **이후 추가 체결 도착** → `_handle_buy_fill` 의 `if not pos:` 분기가 **신규 Position(buy_price=추가가, buy_date=today)** 등록. kojiro ATR 스탬프 없음 → `_effective_atr` 가 `_candidates` 부재 시 0 → **−8% backstop 만 남는다** | `order_engine.py:494-527`(`is_buy_pending` 미검사) · `:1188-1198`(`if not pos:` 신규 등록) · `kojiro.py:1109-1114`(pop) · `:1043-1069` | ① leaf 게이트 4종 추가(§3.3.2 정정) ② `execute_sell` 진입 시 `is_buy_pending` 이면 **추가 주문 취소 선행** ③ `_handle_buy_fill` 에 `pos is None ∧ ticker in sold_today` → **CRITICAL + 즉시 처리 규약** | 취소 왕복 사이의 잔여 창(수백 ms)은 남는다 — CRITICAL 관측이 최종 방어 | **S1-4 (신규)** |
| **C-36** | **`_pending_cancel_tasks` 매수/매도 교차 살해.** ticker 단일 키를 `_schedule_cancel`(매수)과 `_schedule_cancel_and_reorder`(매도)가 공유 → 손절 부분체결이 추가주문 취소 타이머를 `.cancel()` → 미체결 매수주문이 KIS 에 잔존 → 청산 완료 후 체결 → C-35 경로로 합류 | 선언 `order_engine.py:78` · 매수 `:1467-1485` · **매도 `:1491-1522`** | order_no 키 승격 범위에 **매도 경로 포함**(C-2 확장) | 두 타이머가 동시 존재하게 되므로 취소 순서 회귀 필요 | S1-1 |
| **C-37** | **C-26 의 처방이 실제 race 에서 작동 불가.** 체결통보가 `place_order` 응답보다 먼저 처리되면 `_order_strategy[order_no]` 없음 → `_lookup_strategy_from_trade_history(ticker, order_no, BUY)` 도 **PENDING 행이 아직 없어** None → `is_ticker_held_by_any(ticker)` **True**(1차 유닛 보유) → `[buy_fill_fallback_held_conflict]` **return = 체결 폐기**. 이후 매핑이 등록돼도 **통보는 재도착하지 않는다** → `_completed_orders` 미등록 → PENDING 행 INSERT → 15분 `mark_pending_buys_completed` 가 COMPLETED 로 위조 → 메모리는 1차 수량, KIS 는 2유닛 → `_sync_positions_from_balance` 는 `is_ticker_held_by_any` 로 skip → **무손절 orphan 영구 잔존.** 초판 처방 "order_no 존재 여부 기준" 은 **order_no 가 어디에도 없으므로 성립 불가** | `order_engine.py:1155-1172` · `:273→:314→:371→insert_trade` 순서 · `scheduler.py:3634`,`:3637` | 폴백 체인에 **"`state.is_buy_pending(ticker)` 인 전략 = 추가 주문 소유자"** 귀속 단계 추가 — `pending_buys` 는 `place_order` **전에** 동기 등록되므로 race 창에서 **유일하게 존재하는 신호**다. + `_early_fills[order_no]` 버퍼 후 매핑 등록 시 replay | 두 전략이 동시에 같은 종목을 pending 하는 경우는 `is_ticker_blocked_for_buy` 가 막으므로 귀속은 유일 | **S1-1 (재작성)** |
| **C-38** | **`save_position` ON CONFLICT 가 8컬럼 전부를 EXCLUDED 로 덮는다** → 스탬프 컬럼을 SET 절에 넣으면 **스탬프를 모르는 호출자마다 스탬프를 지운다.** 호출자 3곳 중 초판이 커버한 건 1곳뿐: `order_engine.py:1299`(체결, 커버) · **`order_engine.py:746` `[sell_qty_reconciled]` APBK0400 자기치유(cycle236) — 초판 미언급** · `boot_manager.py:235`(의도적 미스탬프). :746 이 스탬프 없이 호출되면 `unit_count=1/last_entry_price=0/entry_atr=0` 리셋 → 세트선 소멸 → 재시작 후 `recompute_held_atr`(`kojiro.py:768-770`)가 `buy_price − stop_atr×live_atr` 로만 재구성 = **손절 완화**(P4 직격) | `src/db/positions.py:21-58` 실측 · 호출 3곳 | 스탬프 컬럼 **NULL 허용** + `COALESCE(EXCLUDED.x, positions.x)`, 또는 별도 `update_pyramid_stamp()` 로 분리 — **비스탬프 호출자가 스탬프를 건드릴 수 없게** | COALESCE 는 "의도적 0 리셋" 을 표현 못 함 → 리셋은 전용 함수로 | S1-3 |
| **C-39** | **부팅 크래시루프 함정 2개.** ① `pg._init_conn`(`src/db/pg.py:45-72`)은 **jsonb/json 코덱만** 등록 → asyncpg 가 `NUMERIC` 을 **`decimal.Decimal`** 로 반환. §3.1.1 의 `NUMERIC(14,4)` → `Position.entry_atr: float` 에 Decimal 이 들어가 `stop_atr * entry_atr`(float×Decimal)에서 **TypeError** (2026-07-20 `date.fromisoformat` 크래시루프와 동형) ② `deploy.yml:37-47` 이 `ON_ERROR_STOP=0 … \|\| true` 라 **042 실패해도 배포는 진행** → `row["unit_count"]` KeyError / `save_position` INSERT 마다 `column does not exist` | `src/db/pg.py:45-72` · `.github/workflows/deploy.yml:37-47` 실측 | ① 컬럼 타입을 **`DOUBLE PRECISION`** (또는 복원 시 명시 `float()`) ② `row.get(k, default)` ③ 부팅 시 **컬럼 존재 자기점검** → 부재면 `[pyramid_schema_missing]` + **강제 미스탬프 모드**(fail-safe) | 자기점검이 실패하면 여전히 크래시 — try 로 감싸고 fail-safe 로 | S1-3 |
| **C-40** | **비체결 트리거가 미체결 추가를 COMPLETED 로 위조.** `mark_pending_buys_completed(ticker)`(`trade_history.py:247-266`)는 ticker 의 PENDING BUY **전량**을 플립하고, `_sync_positions_from_balance`(`scheduler.py:3634`)가 **보유 종목마다 15분 주기로 무조건 호출**한다(`is_ticker_held_by_any` skip **보다 앞**). 현재는 "보유+PENDING" 이 불가능해 무해하지만 **피라미딩에선 상시 상태**다 → LIMIT 폴백 미체결 추가·30초 취소 창의 행이 **체결 없이 COMPLETED** → 이후 취소 `update_trade_status(CANCELLED) WHERE status=PENDING` 은 0건 → **유령 COMPLETED BUY** → `get_trade_pairs` 가중평균 페어링이 유령 랏을 흡수 = **초판의 "손익 뷰 diff 0" 주장 붕괴** | `trade_history.py:247-266` · `scheduler.py:3628-3640` 실측 · `boot_manager.py:~245` | KIS `get_daily_orders` 의 **`rmn_qty==0` 인 order_no 만** 플립, 또는 N분 이상 경과 행으로 제한 + 로그 | 전환 누락 시 부분 적용 | **S1-2 (범위 확장)** |
| **C-41** | **`is_max_positions` 이중 계수** — `len(positions) + len(pending_buys)` 이므로 추가 주문 중인 종목이 **양쪽에 계상**돼 신규 진입 슬롯이 한 칸 일찍 닫힌다 | `strategy_base.py:402-405` 실측 | `len(set(positions) \| pending_keys)` | 신규매수 빈도가 미세 증가(현행 대비) → D+1 관측 | S1-1 |
| **C-42** | **Σ오픈리스크·섹터 유닛 캡이 pending 추가를 미계상** — `_open_risk_won` 은 `positions` 만 순회. 한 leaf 패스의 두 종목 추가가 서로의 pending 리스크를 못 봄 | `kojiro.py:1072-1089` · 섹터 `:827` | Σ리스크·섹터 유닛에 pending 추가의 `qty × (price − set_stop)` 포함 | pending 가격이 미확정(LIMIT/시장가)이라 근사 | S1-4 |
| **C-43** | **부팅 시드·미체결 복구가 추가 주문을 매핑 밖으로 민다.** ① `boot_manager.py:272-286` 이 **오늘 BUY 행** 종목을 `sold_today` 에 시드 → D1+ 에 추가 체결 후 장중 재시작이면 그날 잔여 추가가 **무음 전면 차단**(보수 방향이나 관측 없음) ② 미체결 복구(`:300-320`)가 `if is_ticker_held_by_any(ticker): continue` 로 **보유 종목의 미체결 주문을 통째 skip** → 재시작을 넘긴 추가 LIMIT 주문이 `pending_buys`/`_order_*` 어디에도 없음 → 체결 통보가 매핑 miss → **C-37 과 같은 종착(폐기)**. 초판 C-13 의 "D0 금지로 회피" 는 **D1+ 재시작 케이스를 덮지 못한다** | `boot_manager.py:272-286` · `:300-320` 실측 | ① 시드를 "재매수 차단" / "피라미딩 억제" **두 마커로 분해** ② 보유 전략과 일치하는 미체결 매수는 **추가 주문으로 복구**(pending 등록 + 매핑 4종) | 복구 시 전략 귀속 오판 가능 → `db_strategy_map` 우선 | S1-3 |
| **C-44** | **`pos.last_entry_price = price` 를 체결량 무관하게 갱신** → 24주 추가가 **1주만 부분체결돼도** 사다리 앵커와 세트선이 한 눈금(1N) 통째로 올라간다. `_stop_floor` 래칫이 tighten-only 라 **되돌릴 수 없다.** 얻지 못한 유닛의 조임 비용을 전액 지불 | §3.1.3 스니펫 · `_stop_floor` `kojiro.py:906-919` · 부분체결 실재 `order_engine.py:1465-1485` | 앵커 갱신을 **체결 완결(`total_filled >= ordered_qty`) 또는 체결률 ≥ 임계** 에서만. 미완결분은 `[pyramid_partial_unit]` 관측 | 30초 취소로 영구 부분인 랏의 유닛 정의 — 아래 C-45 와 함께 처리 | S1-1 |
| **C-45** | **`unit_count` "주문 단위 +1" 정의가 부분체결-후-취소에서 유닛 회계를 부풀린다.** 30% 체결 후 잔량 취소면 **0.3유닛이 1유닛으로 계수** → 사다리 눈금·`max_units_per_stock`·섹터 유닛 캡·Σ 회계 전부 드리프트. `_filled_qty[order_no]` 도 미완결 주문에서 pop 되지 않아(`:1305` 는 전량 분기 안) 누수 동반 | §3.1.3 ⚠️ · `order_engine.py:1305`,`:1327`,`:1441-1462` | 유닛 인정 = **체결률 ≥ 임계**, 취소 시 `_filled_qty < ordered` 면 **감산** + `[pyramid_partial_unit]` | 임계값이 새 파라미터 — 모듈 상수(0.5)로 두고 PARAM_RANGES 미편입 | S1-1 |

### 4.4.1 초판 충돌 항목 중 **실제 충돌이 아닌 것 2건** (철회)

| # | 초판 서술 | 실측 | 처분 |
|---|---|---|---|
| **C-33** | `DailyEmitCap` 이 ticker 단일 키라 `(ticker, unit_no)` 재사용 불가 | `class DailyEmitCap(Generic[K])`(`src/engine/daily_emit_cap.py:32`) — **키 타입 제네릭**이다. 기존 인스턴스가 str 키일 뿐, 튜플 키는 `DailyEmitCap[tuple[str,int]]()` 로 그냥 쓰면 된다 | **철회.** 단, "기존 인스턴스를 재사용하면 안 된다" 는 부분은 유효 → 신규 인스턴스 |
| **C-34** | pg 왕복 통합 테스트가 positions **컬럼 정합**을 단언 → migration 042 와 동반 갱신 필수 | `tests/integration/test_cycleM1_1_pg_roundtrip.py:29-58` 은 `r["ticker"]…` **명명 키만** 단언하고 키 집합 전체를 비교하지 않는다 → 컬럼 추가로 깨지지 않는다 | **강등(필수 → 선택).** 신규 컬럼 단언 추가는 권고이지 차단 요건이 아니다 |

### 4.4.2 초판이 근거를 잘못 댄 것 1건 (결론은 유지)

**C-12 "(b) scheduler 폴 루프 = 물리적 불가"** 는 과장이다.
`test_cycle241_ast_silent_inactive_relative.py:387-396` 의 docstring 이 스스로
*"자기소멸 조건: scheduler.py 를 의도적으로 편집하는 후속 사이클이 이 단언을 갱신하거나 제거한다
(cycle233 동형, **사이클 한정 동결**)"* 라고 적어놓았다 — 영구 금지가 아니다.
게다가 **P-3 승격이 `pending_buys.discard(pending_info["ticker"])` 때문에 scheduler 를 어차피 건드리므로
동결 갱신은 Stage 1 에 이미 포함돼 있다.**
→ **leaf 선택 자체는 옳다.** 다만 근거를 *"3,999행 AST 단언"* 이 아니라
**"scheduler 라인 상한(<4,000L) 헤드룸이 1행 + `_SWING_POLL_STRATEGIES` 순차 계약 밖의 race 축을 만들지 않기 위함"** 으로 정정한다.

### 4.4.3 초판이 만든 두 번째 원장 1건 (단순화)

**`_pos_contrib` 보조 맵(§3.1.3)은 불필요하다.**
`_handle_buy_fill` 은 이미 **overrun 클램프가 적용된 증분** `quantity` 를 인자로 받는다
(`order_engine.py:1039-1062` — `quantity = max(0, ordered_qty − prev_total)` 계산 후 호출).
따라서 `else` 분기(`:1210-1213`)를 `pos.quantity += quantity` + 가중평단(delta=quantity)으로 바꾸면 충분하고,
중복 통보는 P1-B `_completed_buy_orders` 가 상류에서 차단한다.
초판이 §3.1.1 에서 "두 번째 진실원 금지" 를 원칙으로 세우고 §3.1.3 에서 **스스로 두 번째 원장을 만든** 자리다.
→ **`_pos_contrib` 삭제, 증분 인자 사용.** (다만 `_filled_qty[order_no]` 누수는 C-45 로 별도 처리)

---

# 5. 기대효과

## 5.1 왜 어젯밤 시뮬은 음수였는가 — 원인 4분해

as-built 최근사(V3/V4: 터틀 이론 유닛 + 예산 클램프 + D1 시작) 결과는
**kojiro Δ = −23,927원 (적격 14건, 개선 2 / 악화 7), donchian Δ = 0**(추가 무발화)이었다.
부호는 **8개 변형 전부에서 음수**였고 크기는 사이징 규율에 반비례했다(어젯밤 §2.5).

| # | 원인 | 근거 | 이 청사진의 처방 | 해소되나? |
|---|---|---|---|---|
| **1** | **1랏 자체가 이미 과잉 피라미드** — donchian 실제 랏 평균 **4.94 터틀유닛**(최대 15.61). V0 손실의 87.6%가 이론유닛 0주 트레이드 | 어젯밤 §0.0 | **Stage 0.5** + 추가 하한 2주(P3) | **예** — 자본 5,000만에서 kojiro 폴백 노출 0.2% |
| **2** | **청산 규약 혼성** — 손절만 터틀(마지막 진입 −2N), 청산은 현행 전략 규약. 터틀 원전 10/20일 채널 청산과의 **결합 편익 완전 미측정** | 어젯밤 §2.5 한계1 | **미해소.** G12(결합 백테스트)가 유일한 증거 경로 | **아니오** — 최대 미지수 |
| **3** | **1랏 엣지가 음수** — kojiro **−0.43N**(n=14, CI [−1.30,+0.43]) · 승률 21.4% vs 손익분기 36.8% | 어젯밤 §2.6 | **미해소.** 피라미딩은 이 값의 **배수를 키우는 장치**다 | **아니오** — 핵심 게이트 |
| **4** | **추가 유닛이 초기 유닛보다 나쁨** — 사다리 위쪽일수록 최종 손절선(마지막 진입 −2N)에 가까워 손절 시 더 크게 다침 | 어젯밤 §0 ③ | **부분 완화** — 1N 눈금은 스택 Σ리스크를 2uN 로 되돌린다(§3.5). 단 **꼬리는 여전히 4배**(§5.3) | **부분** |

**⑴ 은 자본이 고친다. ⑵⑶⑷ 는 자본이 고치지 않는다.** 이것이 5.2 표의 형태를 결정한다.

## 5.2 자본 구간별 기대값 모형

### 모형 입력 (전부 명시)

| 입력 | 값 | 출처 |
|---|---|---|
| 완결 왕복 / 년 (kojiro) | **130** | 실측 14 SELL / 07-24~08-27 ≈ 25영업일 = 0.56/일 → 138/년. 포화 상한 `max_positions 6 ÷ 7.9영업일 × 246` = 187/년. **보수적으로 130 채택** |
| 무제약 추가유닛 / 왕복 | ~~1.45~~ → **1.571** | ⚠️ **정정** — P(1.0N) 은 "보간 0.45" 가 아니라 **실측치가 원천 데이터에 있다.** kojiro 14왕복 MFE_N 재집계: **P(≥0.5N)=0.643 · P(≥1.0N)=0.571 · P(≥1.5N)=0.357 · P(≥2N)=0.357 · P(≥3N)=0.143** (`pyramid/roundtrips.csv` 재현). 0.5N 사다리 합 = 0.643+0.571+0.357 = **1.571** |
| 적격률 (유닛 ≥ 2주) | 자본별 §1.3 표 | EC2 실측, kojiro 유니버스 n=957 |
| 캘리브레이션 | ~~×0.818~~ → **×0.755** (0.5N) / **×0.710** (1N) | 재산출: 0.78 ÷ (1.571 × 0.658) = 0.755. ⚠️ **초판의 "0.818 = 0.818 내부 일관성 확인" 은 가정값(P=0.45)이 만든 우연**이었다. 또 캘리브 자체가 **모형(258만·≥2주 규칙)과 시뮬(≈117만·≥1주 규칙)을 섞어 비교**한 것이라 5,000만 외삽 근거가 약하다. **최종 "추가유닛/년" 열은 캘리브가 흡수해 초판과 같다**(258만 101 / 5,000만 152) |
| **1R** | `net × 0.30 × 0.005` | `risk_pct` 실측 |
| **Δ / 추가유닛 (as-built)** | ~~−0.56R~~ → **−1.51R** (0.5N) / **−1.87R** (1N) | 🔴 **초판 최대 오류 — 단위 정규화.** Δ −23,927원은 `asset_at_entry` 재현 결과 **14왕복 중 12건이 순자산 1,144,956~1,197,043**(예산 343K~359K → **1R ≈ 1,717~1,796원**)에서 발생했다. 018670·012750 2건만 2,634,665(1R 3,952). 초판의 *"당시 R ≈ 3,900"* 은 **사실이 아니다.** 시뮬 자체의 N단위 열로 정규화하면 ΣΔ = **−16.52R** ÷ 10.9 추가유닛 = **−1.51R**. 초판이 "정규화가 달라 비교 불가·범위 하단" 으로 밀어둔 −1.52R 이 **사실상 기준값**이었다 |
| **Δ / 추가유닛 (순수 피라미딩)** | **−1.27R** (0.5N) / **−1.50R** (1N) | as-built Δ 의 **19%(−4,637원)는 피라미딩 효과가 아니다** — `adds=0` 인 왕복 3건(377450 −4,350 · 002810 +70 · 053800 −357)에 시뮬이 라이브 청산 대신 SMA14 2N 스탑을 **대체 적용**한 효과다. §3.5 설계(세트선은 `unit_count≥2` 에서만)로는 **Δ=0 이어야 한다.** 제거하면 −13.90R ÷ 10.93 = **−1.27R** |
| **95% CI (부트스트랩 20k)** | **[−2.04, −0.11]R** (0.5N, adds>0 6건) / **[−3.95, −0.65]R** (1N) | P(Δ>0) = **1.6%** / **0.1%**. ⚠️ 유효 자유도가 사실상 6~9 이므로 CI 폭 자체가 결론이다 |
| Δ / 추가유닛 (낙관) | **+0.5R** | 결합 청산 개선 후 추세추종 시스템의 통상적 유닛 기대값 — **가정이지 측정치 아님** |
| 1랏 base 기대값 | ~~−0.65R/왕복~~ → **−0.99R/왕복** | ⚠️ **정정** — −0.65R 은 **유닛당** 값(−13.87R ÷ 21.3 초기유닛)을 왕복당으로 오표기한 것이다. 왕복당은 −13.87R ÷ 14 = **−0.99R**. → base 연손실 **−12.7% → −19.3%/년** |

### 결과

> 🔴 **초판 표는 전부 폐기한다.** 아래가 정정본이며, **초판 대비 약 2.3~2.7배 나쁘다.**
> 초판의 "최비관" 열이 사실상 "as-built" 열이었다.

**0.5N 사다리 (Δ/년, 괄호 = %net)**

| 순자산 | 1R | 추가유닛/년 | **순수 −1.27R** | **as-built −1.51R** | **CI 하한 −2.04R** | **CI 상한 −0.11R** | **낙관 +0.5R**(가정) |
|---|---|---|---|---|---|---|---|
| 2,582,132 | 3,873 | 101 | −496,815 (−19.2%) | −590,701 (−22.9%) | −798,034 (−30.9%) | −43,031 (−1.7%) | +195,596 (+7.6%) |
| 5,000,000 | 7,500 | 125 | −1,190,625 (−23.8%) | −1,415,625 (−28.3%) | −1,912,500 (−38.2%) | −103,125 (−2.1%) | +468,750 (+9.4%) |
| 10,000,000 | 15,000 | 139 | −2,647,950 (−26.5%) | −3,148,350 (−31.5%) | −4,253,400 (−42.5%) | −229,350 (−2.3%) | +1,042,500 (+10.4%) |
| 20,000,000 | 30,000 | 147 | −5,600,700 (−28.0%) | −6,659,100 (−33.3%) | −8,996,400 (−45.0%) | −485,100 (−2.4%) | +2,205,000 (+11.0%) |
| **50,000,000** | **75,000** | **152** | **−14,478,000 (−29.0%)** | **−17,214,000 (−34.4%)** | **−23,256,000 (−46.5%)** | **−1,254,000 (−2.5%)** | **+5,700,000 (+11.4%)** |

**1N 사다리 (권고 구성)**

| 순자산 | 추가유닛/년 | **순수 −1.50R** | **as-built −1.87R** | **CI 하한 −2.42R** | **CI 상한 −0.38R** | **낙관 +0.5R** |
|---|---|---|---|---|---|---|
| 2,582,132 | 65 | −377,637 (−14.6%) | −470,787 (−18.2%) | −609,254 (−23.6%) | −95,668 (−3.7%) | +125,879 (+4.9%) |
| 5,000,000 | 80 | −900,000 (−18.0%) | −1,122,000 (−22.4%) | −1,452,000 (−29.0%) | −228,000 (−4.6%) | +300,000 (+6.0%) |
| 10,000,000 | 89 | −2,002,500 (−20.0%) | −2,496,450 (−25.0%) | −3,230,700 (−32.3%) | −507,300 (−5.1%) | +667,500 (+6.7%) |
| 20,000,000 | 94 | −4,230,000 (−21.1%) | −5,273,400 (−26.4%) | −6,824,400 (−34.1%) | −1,071,600 (−5.4%) | +1,410,000 (+7.0%) |
| **50,000,000** | **97** | **−10,912,500 (−21.8%)** | **−13,604,250 (−27.2%)** | **−17,605,500 (−35.2%)** | **−2,764,500 (−5.5%)** | **+3,637,500 (+7.3%)** |

*(참고 — 피라미딩 없는 1랏 base 기대값은 자본 무관 **−19.3%/년**(초판 −12.7% 는 유닛/왕복 혼동).)*

**증폭 배수 재계산 (5,000만, 0.5N).** base −19.3% 위에 피라미딩을 얹으면:

| 시나리오 | base | + 피라미딩 | 합계 | **base 대비 배수** |
|---|---|---|---|---|
| 순수 −1.27R | −19.3% | −29.0% | **−48.3%** | **2.50×** |
| as-built −1.51R | −19.3% | −34.4% | **−53.7%** | **2.78×** |
| CI 하한 −2.04R | −19.3% | −46.5% | −65.8% | 3.41× |
| CI 상한 −0.11R | −19.3% | −2.5% | −21.8% | 1.13× |
| 낙관 +0.5R | −19.3% | +11.4% | −7.9% | 0.41× |

→ 초판의 *"엣지 크기를 약 2배 증폭"* 은 **≈2.8배**로 정정된다. 방향(부호 불변·크기 증폭)은 그대로다.

> ### ⚠️ 표본 한계를 표 안에 명시 — 이 표를 자본 계획의 근거로 쓰지 말 것
> 위 다섯 열은 **하나의 상수**(Δ/추가유닛) × 하나의 빈도 모형으로 만들어졌고,
> 그 상수의 **유효 자유도는 6~9**(adds>0 왕복 수)다. 원 단위 정밀도는 **표기의 산물이지 정보가 아니다.**
> kojiro 실현 왕복 전수(SELL COMPLETED 14건, `trade_history` 실측):
> `−3,550 / −2,880 / −1,900 / +30 / −3,700 / +9,600 / −4,300 / −3,800 / −3,800 / −120 / −100 / −3,400 / −20,000 / +5,700`
> = 누적 **−32,220원**, 승률 **3/14 = 21.4%**.
> **양쪽 꼬리가 각각 단일 거래다** — 이익의 63%가 236200(슈프리마) 1건(+9,600, 초판 §5.4 #2 가 인정),
> 그리고 **손실의 62%가 018670 1건(−20,000)** 인데 초판은 이쪽을 인정하지 않았다.
> 그 018670 은 **225,500원짜리 1주** = 당시 kojiro 예산의 약 29%를 한 주가 차지한 **1주 폴백 랏**이다 —
> 즉 §5.1 이 원인 ①로 지목한 바로 그 병리가 **표의 부호를 통째로 만들고 있다.**
> → **Stage 0.5(1주 폴백 시정)를 먼저 하라는 권고는 이 사실로 더 강해진다.**
>
> **그리고 결정적으로 — 반대 방향 증거가 있다.** §3.5.1 의 31,498 표본 기계적 비교에서
> 피라미딩의 **평균 손익 자체는 개선**됐다(base +0.170 → 1N×4 +0.556 uN, 유닛당 +0.170 → +0.249).
> 그 실험은 전략 고유 청산(샹들리에·스테이지3)을 모델링하지 않고 20영업일 보유 + 세트손절만 적용한
> **기제 분리 실험**이지 전략 백테스트가 아니다. 그럼에도 결론은 분명하다 —
> **위 표의 음수 부호는 "피라미딩 기제" 의 성질이 아니라 "이 표본 × 이 청산규약" 의 성질이다.**
> 초판 §5.1 ②가 그렇게 절반 말해놓고 §5.2 표가 그것을 자본 계획 근거처럼 제시했다.

### 1N 사다리 — 왜 여전히 권고인가 (근거 하나 철회)

정정된 표(위)에서도 1N 이 0.5N 보다 **기대값이 낫지 않다**는 관찰은 유지된다
(as-built −27.2% vs −34.4% 는 절대액이 작을 뿐, **유닛당은 1N 이 더 나쁘다**: −1.87R vs −1.51R).
어젯밤 §2.6 의 *"1N 은 더 나은 규칙이 아니라 더 적은 용량"* 이 재확인된다.

**1N 을 권고하는 근거 3 중 ①은 철회한다.**

| # | 초판 근거 | 최종본 판정 |
|---|---|---|
| ① | 스택 Σ리스크가 2uN 로 유지 = **"공짜"** | 🔴 **철회.** Σ리스크(손절 *크기*)는 안 늘지만 **손절 *빈도*가 는다**(53.0%→75.3%, §3.5.1). 그리고 §3.5.1 재현에서 **1N 의 손절률(75.3%)이 0.5N(71.3%)보다 높다** — 1N 이 유닛 2에서 손절선을 0.5N 더 끌어올리기 때문이다. **초판의 유닛당 관측(1N 이 더 나쁨)과 정확히 같은 기전이고, 초판은 이를 "용량" 으로 오귀인했다.** |
| ② | 4유닛 도달 빈도가 낮아 꼬리 노출이 **덜 잦다** | ✅ **유지.** 실측 도달확률로 1N 사다리 무제약 기대 = 1.071 유닛/왕복 vs 0.5N 1.571. 스택 완성 빈도가 낮다 = 최대 명목 노출 시간이 짧다 |
| ③ | BE 승격이 4유닛 시점에 정렬(C-18) | ✅ **유지.** 0.5N 은 구조적 미발화 |
| ④ | **[신규] 손절률 상승폭이 max_units 의 단조 함수** | ✅ **추가 근거.** 1N×2(Stage 2a) 전환률 11.7% vs 1N×4 22.3% — **단계적 롤아웃이 그 자체로 완화 수단**이고 각 단계에서 실측 가능하다(§3.5.1) |

→ **결론 유지, 근거 교체.** 1N 을 고르는 이유는 "리스크가 안 는다" 가 아니라
**"용량을 작게 시작해 손절률 상승을 단계적으로 실측한다"** 이다.

### 이 표에서 읽어야 할 3가지

1. **%net 이 자본 구간에 거의 무관하다.** (정정된 수치로) **−22.9% → −34.4%** 로 수렴하고 그 이상 나빠지지 않는다.
   **자본 성장은 피라미딩의 기대값을 개선하지 않는다.** 개선되는 것은 "실행 가능성" 뿐이고,
   기대값이 음수인 동안 실행 가능성이 올라간다는 것은 **손실 속도가 올라간다**는 뜻이다.
   → 역설: **오늘 258만에서 켜는 것이 5,000만에서 켜는 것보다 덜 위험한 이유는 1주 폴백이 우연히 브레이크 역할을 하기 때문**이고,
   그 브레이크는 자본이 커지면 **사라진다**. 그러므로 **자본 게이트만으로는 안전하지 않다 — 엣지 게이트가 반드시 필요하다.**
2. **레버리지의 대칭성.** as-built −34.4% / 낙관 +11.4% — 피라미딩은 **엣지의 부호를 바꾸지 않고 크기만 약 2.8배로 증폭**한다
   (base −19.3% 대비 총합 −53.7% vs −7.9%). 즉 **"1랏 엣지가 양수인가" 가 전부**다.
   ⚠️ 대칭이 아니다 — **아래쪽(2.78×)이 위쪽(0.41×)보다 훨씬 두껍다.** 낙관 시나리오조차 총합을 음수에서
   빼내지 못한다(−7.9%). **피라미딩만으로는 base 엣지의 부호를 뒤집을 수 없다.**
3. **낙관 시나리오는 측정치가 아니다.** +0.5R/유닛은 "터틀 채널 청산 결합 후 정상 작동하는 추세추종" 의 통상값을 가정한 것이고,
   우리 표본에서 관측된 적이 없다. **G12(결합 백테스트) 없이 이 열을 근거로 삼으면 안 된다.**

## 5.3 꼬리 위험 (손절이 실패했을 때)

> 🔴 **초판 표 폐기.** 초판은 갭 손실을 `갭% × 4 × 유닛명목` 으로 근사했는데,
> 이는 **사다리의 실제 체결가를 무시한 것**이다. 사다리 진입은 P, P+N, P+2N, P+3N 이므로 평단(P+1.5N)이
> 마지막 진입가(P+3N)보다 **1.5N 낮고**, 갭은 마지막 진입가 기준으로 재야 한다.
> 정확한 식: `손실 = 4u × [평단 − (1−g)×마지막진입가]`.
> (어젯밤 문서 §2.7 은 이 방법을 썼는데 초판이 근사로 **퇴행**시켰다 — 0.5N 값이 어젯밤 표와 원 단위까지 일치하는 것이 그 증거.)

**정정 꼬리표 — 5,000만 기준, ATR 시나리오 3종 병기**

| 시나리오 | **ATR 4.62%** (초판 가정) | **ATR 5.18%** (유니버스 실측 중앙) | **ATR 2.70%** (ρ클램프 구간 = kojiro 실제 픽 편향) |
|---|---|---|---|
| **1유닛 명목** | 1,623,377 (예산 10.8%) | 1,447,876 (9.7%) | **2,490,000 (16.6%) — ρ 클램프** |
| **4유닛 스택 명목** | 6,943,506 (예산 **46.3%** · 계좌 **13.89%**) | 6,241,506 (41.6% · 12.48%) | **10,363,380 (예산 69.1% · 계좌 20.73%)** |
| 계획 손절 — 1N 사다리(2uN) | 150,000 (계좌 0.300%) | 150,000 (0.300%) | 134,460 (0.269%) |
| 계획 손절 — 0.5N 사다리(5uN) | 375,000 (0.750%) | 375,000 (0.750%) | 336,150 (0.672%) |
| **−10% 갭** (1N 사다리) | **289,351 (0.58%) · 1.78×** | 219,151 (0.44%) · 1.51× | **673,296 (1.35%) · 2.70×** |
| **−20% 갭** | 1,028,701 (2.06%) · 3.17× | 888,301 (1.78%) · 3.07× | 1,749,972 (3.50%) · 3.51× |
| **−30% 갭 (하한가)** | **1,768,052 (3.54%) · 3.63×** | 1,557,452 (3.11%) · 3.59× | **2,826,648 (5.65%) · 3.78×** |
| **−51% (이틀 연속 하한가)** | 3,320,688 (6.64%) · 4.01× | 2,962,668 (5.93%) · 4.01× | **5,087,668 (10.18%) · 4.01×** |

*(배수 = 같은 갭을 맞은 **단일 1유닛** 대비. 0.5N 사다리는 평단이 더 낮아 −10% 갭에서 2.89×/2.76×/3.35×.)*

**초판 대비 정정 3.**
1. **초판의 "꼬리는 정확히 4배" 는 −51% 시나리오에서만 참이다.** 가장 빈번한 **−10% 갭에서 1N 스택은 1.78배**이지
   초판이 적은 4.0배가 아니다(2.24배 과대). 배수는 갭이 깊어질수록 4에 수렴한다 —
   *평단과 마지막 진입가의 1.5N 차이가 갭에 묻히기 때문*이다.
   → **"1N 은 계획손실 1.0× 인데 꼬리만 4배" 라는 초판의 핵심 프레임은 수정된다.**
   −10% 갭에서 1N 스택의 손실은 계획손절(150,000)의 **1.93배**이지 4.33배가 아니다.
2. **스택 명목은 43.3% 가 아니라 46.3%** (사다리 체결가 반영). 그리고 **ρ클램프 구간에서는 69.1%.**
3. **가장 중요한 정정 — 실제 바인딩 값은 ATR 이 아니라 `position_ratio` 다.**
   §3.4 의 per-ticker 누적 캡 `ρ × 예산 × max_units` = **0.166 × 15,000,000 × 4 = 9,960,000 = 예산 66.4% = 계좌 19.92%**.
   `compute_unit_qty_guarded`(`turtle_sizing.py:78-79`)가 **`atr_ratio < risk_pct/ρ = 3.01%` 인 모든 종목의 모든 유닛을
   ρ 로 클램프**하므로, 그 구간에서 4유닛 = 예산 66.4% 가 **ATR 과 무관하게 도달**한다.
   그리고 **kojiro 의 실제 픽이 저ATR 편향**이다(현 보유 6종목 중앙 3.85% vs 유니버스 5.18%, 2종목이 3.01% 미만).
   → 예산 안에 들어가는 동시 스택 = **1.51개**. 즉 5,000만에서 **kojiro 예산 30%가 1~2종목에 들어간다** —
   초판 §5.3 하단의 "2.31 스택 / ≤3종목" 은 ATR 4.62% 가정의 산물이다.

→ **꼬리 방어의 결론은 초판과 같되 더 강하다.** `max_open_risk_pct` 는 명목 축에 **정의상 맹목**이고,
실효 제동은 **예산 클램프 + per-ticker 누적 캡** 둘뿐이며, **그 두 축을 정하는 파라미터는 ATR 이 아니라 `position_ratio`** 다.
→ **`max_units` 를 올리는 사이클에서는 `position_ratio` 를 함께 내려야 한다**(예: 4유닛 ON 시 ρ 0.166 → 0.10 이면
per-ticker 캡 = 예산 40%). 초판에는 이 커플링이 없었다.

### 동시 노출 (Σ캡이 실제로 허용하는 최대)

| 구성 | 실효 제동축 | 동시 스택 (ATR 4.62%) | **동시 스택 (ρ클램프 구간)** | 5,000만 명목 | 계좌 비중 | 종목 수 |
|---|---|---|---|---|---|---|
| 0.5N · cap 4.5 (현행) | Σ리스크 | 1.80 | **1.45** | 11,688,312 | 23.4% | ≤2 |
| **1N · cap 4.5 (권고)** | **예산 명목** | 2.16 | **1.45** | 15,000,000 | **30.0%** | **≤2 (저ATR 구간)** |
| 0.5N · cap 6.0 | 예산 명목 | 2.16 | 1.45 | 15,000,000 | 30.0% | ≤2~3 |
| 0.5N/1N · cap 8.0 | 예산 명목 | 2.16 | 1.45 | 15,000,000 | 30.0% | ≤2~3 |

⚠️ **최종본 정정** — 초판의 "2.31 스택 / ≤3종목" 은 스택 명목을 43.3% 로 본 값이다. 사다리 체결가를 반영하면
1N 스택은 예산 **46.3%** → **2.16 스택**이고, **kojiro 픽이 실제로 몰려 있는 ρ클램프 구간(atr<3.01%)에서는
스택이 예산 69.1% → 1.45 스택 = 사실상 한 종목 + 나머지 반쪽**이다.
→ **5,000만에서 kojiro 예산 30%(계좌 30%)가 1~2종목**이 현실적 기대값이다. 초판보다 **한 단계 더 집중**된다.

⚠️ **캡을 6 이상으로 올리면 Σ리스크 캡은 아예 비구속이 되고 예산 클램프(2.31스택 = 예산 100%)만 남는다.**
즉 **`max_open_risk_pct` 상향의 실효 효과는 "리스크 한도 완화" 가 아니라 "제동축을 리스크에서 명목으로 갈아타는 것"** 이다.
5,000만 계좌 기준 어느 구성이든 **계좌의 23~30%가 2~3종목에 들어간다.**
한국 중소형주 폭락일에는 상관이 1로 수렴한다 — **이것이 상관군 유닛 캡(§3.6)이 캡 상향의 전제인 정확한 이유**다.

### 방어되지 않는 축 3

- **`daily_loss_limit` 은 realized 기준 + 사후 차단** — 이미 난 미실현 손실은 못 막는다(`strategy_base.py:407-413`).
  ⚠️ **최종본 추가 — 이 게이트는 스택 규모의 어떤 사건에도 *사전 개입할 수 없다*.**
  kojiro 라이브 `daily_loss_limit = −8.0`(DB 실측), 5,000만 예산 15,000,000 → 한도 **1,200,000원**.
  · 계획대로 손절되는 1N 4유닛 스택 = 2uN = **150,000원** → 한도는 **스택 8개분**. 정상 작동 시 영원히 안 걸린다.
  · −30% 갭 스택(ρ클램프 구간) = **2,826,648원 = 한도의 2.36배**. 그러나 realized 되는 시점엔 이미 전부 발생한 뒤이고
    게이트는 "그 다음 매수" 만 막는다.
  → **너무 커서 안 걸리거나, 걸릴 때는 이미 늦었다.** 초판 C-28 이 "미해소, 별도 등재" 로 처리한 것은
  과소평가다 — §5.3 표의 **모든 행이 정책적으로 무방비**라는 뜻이다.
- **계좌 레벨 스위치가 아예 없다.** cycle233 SOFT 게이트는 `system_config` 에 `account_risk_block_pct`/`warn_pct`
  키가 **부재**(EC2 실측 — 반환 행은 `cash_usage_ratio` 하나)라 여전히 다크런치이고, 게다가 그 게이트도
  **실효 손절선 기반이라 명목 축(= 피라미딩이 공격하는 바로 그 축)에 정의상 맹목**이다.
  7전략이 전부 롱-온리 한국주식 + `cash_usage_ratio=1.0` + Σweight=1.00(실측)이므로 계좌는 **상시 100% 롱**이고,
  kojiro 외에 섹터 캡을 가진 전략은 **하나도 없다**(DB params 실측). 한 스택 −30% = 계좌 5.65%,
  같은 미분류 섹터 2스택 동시 = 11.3%, 그 위에 나머지 6전략 동반 하락 — **이를 중단시킬 스위치가 시스템에 없다.**
- **매도 거부** — 257720 선례(APBK0400 ×3 → 주말 오버나잇)가 4유닛 규모에서 재현되면 위 수치가 실현 손실이 된다.
  최근 17영업일 중 **8일** APBK0918 매도 거부 실측(전부 08:00:0x 프리마켓, donchian·VB).
- **프리장(08:00~09:00) 청산 공백이 4배가 된다.** kojiro 는 `_PRE_MARKET_EXIT_EVAL_STRATEGIES`
  (`risk.py:79` = LTV 만) 밖이라 프리장 **청산 평가 자체를 안 한다** — 이는 APBK0918 거부에 노출되지 않는다는
  뜻에서 유리하지만, 동시에 **그 1시간 동안 손절선이 존재하지 않는다**는 뜻이다.
  초판 C-25 는 "추가 시간창을 09:30~15:00 로 제한 → 무관" 이라 처리했는데, **무관한 것은 *추가 발주*이고
  *청산 공백*은 명목 4배 그대로다.** 세트선이 아무리 타이트해도 08:00~09:00 에는 집행되지 않는다.
- **주말·연휴** — kojiro 평균 보유 7.9영업일. 금요일 4유닛 완성 = 최대 사이즈로 2~3박 갭 노출
  → §3.2 의 "금요일·연휴 전일 추가 금지" 가 이 축의 유일한 방어.

## 5.4 정직한 한계 — 이 표들이 말하지 않는 것

| # | 한계 | 함의 |
|---|---|---|
| 1 | **표본 n=14(kojiro) / 24(donchian).** kojiro CI [−1.30, +0.43] 은 **0을 포함**한다 | "기대값 음수" 는 확정이 아니다. 다만 이는 "하지 말자" 를 약화시키지 않고 **"증거 없이 레버리지를 올리지 말자" 를 강화**한다 |
| 2 | **kojiro 실현 총이익의 63%가 슈프리마 1건**(+9,600원) | 오른쪽 꼬리 논거 전체가 **표본 1건**에 걸려 있다 |
| 3 | **결합 편익 완전 미측정** — 터틀 10/20일 채널 청산 + 피라미딩 | **A를 뒤집을 수 있는 유일한 증거 경로**(G12) |
| 4 | 시뮬은 **BE 승격 × 가중평단 앵커 상호작용 미모델링** | 실제 결과는 시뮬보다 **나쁠 수 있다** |
| 5 | 시뮬 사다리는 `P0 + k×step×N` 고정, 책은 "마지막 체결가 + step" | 고정 사다리는 유닛을 더 빨리 채움 → **음수 엣지에서 손실 과대계상 방향**(보수 편향) |
| 6 | **일봉 기반이라 장중 순서(0.5N 도달 vs MAE 관통의 선후)를 알 수 없다** | Stage 0 관측이 주는 **유일한** 정보 |
| 7 | 수수료·세금 **제외**. 왕복 ≈ 0.32~0.53% = 1N 의 **5.3~11.5%** | 4유닛이면 절대액 4배. gross 손익 관리(C-27) |
| 8 | 연간 왕복 130 은 **25영업일 실측의 외삽** | ±40% 오차 가능. T2 에서 `position_ratio` 0.08~0.10 · `max_positions` 상향 시 비례 확대 |
| 9 | 대조군이 "고정 1유닛" 뿐 | 피라미딩의 고유 편익은 *같은 평균 heat 의 고정 2유닛* 대비 **조건부 사이징**인데 그 대조가 없다 |
| 10 | ~~ATR 중앙값 4.62%는 유니버스 값, 실제 픽은 **고ATR 편향**~~ 🔴 **방향이 반대였다** | 실측: 유니버스 중앙 **5.18%**(n=952), 현 보유 kojiro 6종목 3.00/3.12/2.68/6.53/4.57/5.25 → 중앙 **3.85% = 저ATR 편향**. 저ATR = **유닛 명목이 크다** = `position_ratio` 클램프에 걸린다 = **집중 심화**. 초판이 "보수 편향" 으로 분류한 항목이 실은 **낙관 편향**이었다(§1.3 · §5.3 정정) |
| 13 | **[최종본 신규] 손절 *확률* 축이 초판 전체에서 미측정** | §3.5.1 재현 = 세트선이 손절률을 53.0%→75.3% 로 올린다. 어떤 게이트도 이 축을 못 본다 |
| 14 | **[최종본 신규] as-built Δ 의 19% 는 피라미딩 효과가 아니다** | `adds=0` 왕복 3건의 청산 규약 대체 효과(−4,637원). 순수 Δ 는 −1.27R/−1.50R |
| 15 | **[최종본 신규] as-built 근거가 자기 규칙(P3)이 배제하는 랏으로 구성** | add 이벤트 14건 중 **12건이 1주 add**(theory qty=1). 당시 자본에서 P3(≥2주) 적용 시 적격 3/14, 실제 add 발화는 079160 1건뿐. 유닛당 Δ 는 주수에 선형이라 전이 가능하지만 **표본이 그만큼 얇다** |
| 16 | **[최종본 신규] 오른쪽 꼬리 논거(236200 슈프리마)는 as-built 에서 발화조차 안 했다** | 1R 1,778 / N 2,407 → theory qty **0** → V3 에서 add 0건, Δ 0. 오늘의 R(3,873)에서도 theory=1 이라 **P3 미달**. 적격은 ≈1,000만부터 |
| 17 | **[최종본 신규] `_kojiro_sector_key` 의 29.5% 가 fail-open** | 상관 통제축이 유니버스의 1/3 에서 작동하지 않는다(§3.6 정정 ④) |
| 11 | 낙관 시나리오 +0.5R/유닛은 **가정** | 우리 표본에서 관측된 적 없음 |
| 12 | **kojiro 라이브 기간이 07-21~08-28 뿐**(≈28영업일) — 단일 시장 국면 | 레짐이 바뀌면 전부 다시 재야 한다 |

---

# 6. 권장 롤아웃 일정

```
[지금 ~ ]           Stage 0     관측 (would_add 20:10 배치)          자본 무관 · 8영역 0 · 1사이클
[지금 ~ ]           Stage 0.5   1주 폴백 과잉 시정                    자본 무관 · 8영역 0 · 1사이클
                        │
                        │  ← 게이트 T1
                        ▼
[net ≥ 500만]       Stage 1     배관 11건 + 스키마 + 경로 (다크런치)    8영역 1(order_engine) · 8~10사이클
                                ⚠️ 다크 스위치 = DB 에 없는 신규 키 (기존 max_units_* 는 DB 에 값 존재)
                        │
                        │  ← 게이트 T2
                        ▼
[net ≥ 2,000만]     Stage 2a    max_units 2                          2주 무사고
[+ N≥10 스택]       Stage 2b    max_units 3
[net ≥ 5,000만]     Stage 2c    max_units 4 (책 값)                   유닛-섹터 캡 배포 완료
                        │
                        ▼
[별도 사이클]        max_open_risk_pct 4.5 → 6~8                      상관군 캡 배포 후
[T3 = net 1억]       1/2N 눈금 검토 · donchian 확장 검토
```

## 게이트 T1 (Stage 1 착수 허용)

| # | 게이트 | 측정 | 현재 | 판정 |
|---|---|---|---|---|
| **G0** | **Stage 0.5 완료** — 1주 폴백 과잉 시정 + 회귀 가드 | `[oversized_fallback]` 발화 추세 | donchian 랏 avg 4.94유닛 | ✗ |
| **G0b** | **Stage 0 관측 2주 축적** — `would_add` 눈금 도달 분포 확보 | 20:10 metrics | 미구현 | ✗ |
| **G1** | 순자산 **≥ 500만** 5영업일 연속 | `daily_performance` strategy='total' | **2,582,132 (51.6%)** | ✗ |
| **G4** | `account_risk_block_pct` 실값(6.0) 활성 + 2주 무오탐 | `system_config` 키 존재 | **키 부재 = 다크런치** | ✗ |
| **G6** | 실행 경로 설계 확정 = **신규 leaf `pyramid_engine.py`** | 본 문서 §3.3 채택 여부 | — | **사용자 결정** |
| **G7** | 대상 **kojiro 한정** 확정 | 본 문서 §요약-2 채택 여부 | — | **사용자 결정** |

## 게이트 T2 (Stage 2 실활성 허용) — T1 전부 + 아래

⚠️ **최종본 정정** — 초판 T2 표에 **자본 게이트가 누락**돼 §3.9·§6 과 어긋났다.
**정본 = `2a: net ≥ 2,000만` · `2c: net ≥ 5,000만`**(§3.9 Stage 2 표).
그리고 **T1 의 G1(500만)은 "배관 착수" 게이트이지 "실활성" 게이트가 아니다** — 500만에서 kojiro 추가불가는 여전히 20.2%.

| # | 게이트 | 측정 | 현재 |
|---|---|---|---|
| **G1″** | **순자산 게이트** — 2a: ≥ 2,000만 / 2c: ≥ 5,000만 (5영업일 연속) | `daily_performance` strategy='total' | **2,582,132** |
| **G2** | **자본 무관 런타임 규칙**: 추가 유닛 계산 수량 **≥ 2주**, 1주 폴백 절대 금지 | 코드 계약 + 회귀 | 미구현 |
| **G13** | **[최종본 신규] 다크 스위치 무결성** — 추가 발화가 **DB 에 없는 신규 키**로만 열리고, 레거시 `max_units_*`(DB 값 존재)를 읽지 않음 + `[pyramid_param_anomaly]` 관측 | AST + 부팅 로그 | 미설계 |
| **G14** | **[최종본 신규] 추가↔청산 인터리브 방어** — leaf 게이트 4종(`_selling`/`is_blocked`/실효손절선/신선도) + `execute_sell` 의 추가주문 취소 선행 + orphan CRITICAL, 각각 **뮤테이션 FAIL 실증** | AST + 회귀 (C-35~C-37) | 미설계 |
| **G15** | **[최종본 신규] 손절률 관측** — `[pyramid_stop_shift]` 로 (고정2N선, 세트선, 실제 청산가) 기록. 2a 에서 전환률이 예측(11.7%) 대비 실측 확인 | 20:10 metrics | 미설계 |
| **G16** | **[최종본 신규] `position_ratio` 커플링 결정** — `max_units` 상향과 ρ 하향을 한 결정으로 묶음 | 사용자 결정 | 미결 (N-2) |
| **G3** | kojiro 최근 **30 완결 왕복**의 **N 단위** 기대값 95% CI 하한 > 0 (부트스트랩 20k) ⚠️ **MDE**: sd 1.65N 에서 n=30 통과하려면 평균 **≥ +0.59N** | 왕복 페어링 + 진입 ATR 정규화 (**원 단위 금지**) | n=14, [−1.30,+0.43] |
| **G3′** | **동일 표본 충실 사이징 피라미딩 시뮬 Δ > 0.** G3 통과가 피라미딩 엣지를 **함의하지 않는다**(§5.1 ④) | §2.5 V3/V4 규약 재실행 | Δ −23,927 |
| **G5** | 배관 **P-1 · P-1b · P-2 · P-3 시정 + 회귀** (= Stage 1 사이클 1·2) | 회귀 + 뮤테이션 | 미시정 |
| **G8** | 추가 경로가 매수 게이트 8종 **동일 함수·순서 재판정** + AST 확장 + **게이트 1개 제거 → 각각 FAIL** 뮤테이션 | AST + 행위 | 미설계 |
| **G9** | `entry_atr` 영속 + 부팅 복원 + **재시작 후 사다리 눈금·세트선 불변** 회귀 | migration + 회귀 | 미구현 |
| **G10** | 추가 경로 `_fallback_one_share` 금지 + per-ticker 누적 notional 캡 + 뮤테이션 | AST + 회귀 | 미설계 |
| **G11** | **상관군 유닛 캡** — `max_positions_per_sector` 를 유닛 캡(6)으로 전환 | `portfolio_risk.by_sector` + 회귀 | 개수 캡만 |
| **G12** | **결합 백테스트 스윕** — 피라미딩 × 청산규약(현행 vs 터틀 채널) × 간격(1N·1/2N) 격자 Δ > 0 | 외부 MCP 백테스트 | 미실행 |

**G3 는 사실상 도달 난이도가 매우 높다** — 이것을 알고 채택해야 한다.
현실적 대안 2: **(가)** G3 를 "CI 하한 > 0" 대신 "**점추정 > 0 이고 n ≥ 30**" 으로 완화하되
Stage 2a(유닛 2)까지만 허용하고 2c(유닛 4)는 원안 유지. **(나)** G12(결합 백테스트)를 G3 의 **대체 경로**로 인정.
→ **이 완화 여부가 사용자 결정 사항이다.**

---

# 7. 첫 착수 사이클 명세 초안

> team-leader 가 그대로 사이클 명세로 옮길 수 있는 형태. **두 건은 병렬 가능**(접촉 파일 무교집합).

## 사이클 A — Stage 0: 피라미딩 관측 배치 (`would_add`)

| 항목 | 내용 |
|---|---|
| **목적** | 보유 종목의 1N 눈금 도달 이력을 20:10 리포트에 배치 산출. **매매 행위 변경 0** |
| **접촉 파일** | `src/engine/log_analysis_engine.py` (신규 `_aggregate_pyramiding`) · `frontend/src/types/log_reports.ts` · `frontend/src/components/DailyReportTab.tsx` |
| **8영역** | **0** (diff-zero 가드 통과 필요) |
| **스키마** | **없음** (`daily_log_reports.metrics` JSONB) |
| **산출 필드** | `metrics.pyramiding = { by_ticker: [{ticker, strategy, entry_price, entry_atr_est, levels_reached, would_add_units, unit_qty_est, below_2shares, budget_clamped, virtual_set_stop}], totals: {...} }` |
| **N 추정** | 보유 종목 일봉 `stock_master_daily` → ATR14. **결손 시 skip + 사유 기록**(KIS 폴백은 `get_recent_daily_normalized` 신선도 게이트가 자동 처리 — "호출 0" 아님) |
| **Red 테스트** | ① 보유 0 → 빈 dict ② 일봉 결손 → `reason=no_candles` ③ 1N 도달 2회 → `would_add_units=2` ④ 유닛<2주 → `below_2shares=True` ⑤ D0 보유는 제외 ⑥ 배치 예외 → metrics 나머지 키 보존(graceful) ⑦ 프론트: metrics.pyramiding 없으면 섹션 미렌더 |
| **회귀 가드** | 기존 metrics 9키 불변 · 8영역 diff 0 · `log_analysis_engine` 예외 격리 |
| **D+1 관찰** | `levels_reached` 분포 · `below_2shares` 비율 · totals 가 §5.2 모형의 1.45/왕복 가정과 부합하는지 |
| **예상** | 1 사이클 |

## 사이클 B — Stage 0.5: 1주 폴백 notional 상한 (독립 유효)

> ⚠️ **이 사이클은 병렬 자문에서 이미 명세가 나와 있다** — `_workspace/domain_consult/cycle242_fallback_notional_cap.md`
> (K = **2.0** 전 전략 공통 · 기준 = 이론 유닛 notional × K · 범위 = `sizing_mode=="turtle"` 전략의 **모든 랏**).
> 아래 표는 그 문서와 **정합하며**, 피라미딩 관점에서 붙이는 조건 하나만 다르다:
> **피라미딩 Stage 2 실착수 시 K 를 2.0 → 1.0 으로 조이는 것이 G0 문안에 포함되어야 한다.**
> K=2 랏 위에 4유닛 사다리를 얹으면 최대 **8유닛** = 책 R15("동일 종목 4유닛") 재위반이다.

| 항목 | 내용 |
|---|---|
| **목적** | `_fallback_one_share` 가 notional 상한을 보지 않아 발생하는 **진입 시점 무허가 과잉 피라미딩** 차단 |
| **접촉 파일** | `src/engine/strategy_base.py` **단독** (비8영역) |
| **8영역** | **0** |
| **설계** | `sizing_mode=="turtle"` 전략의 **모든 매수 랏**을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 클램프, 0 이면 매수 없음. ⚠️ **기준축은 이론 유닛 notional(ATR 축)이지 `position_ratio × 예산`(ρ 축)이 아니다** — cycle242 ②가 ρ 축을 명시 기각(ρ ≤ ratio 는 폴백 전면 차단 = ⓐ 위장, ρ > ratio 는 근거 없는 새 상수 + 변동성 맹목) |
| **K 값 결정** | **`K=2.0`** (cycle242 자문 결론과 동일). donchian 진입 −46% · 최대 랏 8.66유닛 → ≤2.0 · 단일 랏 −30% 꼬리 3.18% → ≤1.45%. **피라미딩 Stage 2 시 K→1.0** |
| **비대칭 계약** | **차단만, 확대 금지** — 매수를 **줄이는** 방향이므로 안전. `qty>0` 경로는 **byte 불변** |
| **Red 테스트** | ① 랏 ≤ K유닛 → 현행 동일 ② 초과 → 클램프 + WARNING 1회/ticker/일 ③ 클램프 결과 0 → 매수 없음 ④ ATR 결측/0 → 상한 비활성(fail-open, 현행 동일) ⑤ 고정%손절 5전략 **미접촉**(byte 동일) ⑥ 실측 재현 — donchian 192820(8.69유닛) · kojiro 000815(3.10유닛) |
| **AST 가드** | `_apply_budget_limit` 의 "0 → `_fallback_one_share` 위임" **분기 순서 불변**(계약) |
| **D+1 관찰** | 전략별 매수 건수 변화 · `[oversized_fallback_blocked]` 빈도 · donchian funnel 최종단 |
| ⚠️ **최종본 — 범위 재확인 필요** | 제안 범위는 `sizing_mode=="turtle"` 전략(kojiro·donchian)인데, **보존 창(INFO retention 2일) 안의 실제 `[oversized_fallback]` 관측 3건은 3/3 이 `volatility_breakout`**(108490 ratio 1.81 / 010950 1.13 / 047810 1.01)이고 VB 는 `sizing_mode` 미설정 = position_ratio 다. 창이 짧아 결론은 아니지만 **제안 범위가 관측된 신호를 포함하지 않는다** — 범위를 "turtle 전략" 이 아니라 "**폴백이 발생하는 모든 전략**" 으로 재정의할지 결정 필요 |
| **⚠️ 사용자 승인 필수** | **매매 빈도를 유의미하게 바꾼다.** "안전 방향" 이지만 자동 진행 금지 |
| **예상** | 1 사이클 |

## 착수 순서 권고

1. **사이클 B 먼저**(또는 A 와 병렬) — 피라미딩을 안 하기로 해도 이득이고, §5.1 의 원인 ①을 닫는다.
2. **사이클 A** — Stage 0 관측. 2주 축적 후 §5.2 모형의 `1.45 유닛/왕복` 가정을 실측으로 대체.
3. 그 다음은 **net 500만 도달까지 대기.** 그 사이 G4(`account_risk_block_pct=6.0` 활성)와
   G12(결합 백테스트 스윕)를 독립 진행할 수 있다 — 둘 다 피라미딩 코드와 무관하다.

---

## 부록 A — 사용자 결정이 필요한 항목 **10** *(최종본에서 3건 추가)*

| # | 항목 | 선택지 | 이 문서의 권고 |
|---|---|---|---|
| 1 | 원장 구조 | 가중평단 / 랏 원장 | **가중평단** |
| 2 | 간격 | 1N / 0.5N | **1N**(Stage 2 시작) |
| 3 | D0 추가 | 허용 / 금지 | **금지**(회피가 무료) |
| 4 | `_fallback_one_share` K 값 | 1.0 / 2.0 / 3.0 | **2.0 시작** |
| 5 | G3 완화 | 원안(CI 하한>0) / 점추정>0 ∧ n≥30 / G12 대체 인정 | **G12 대체 인정 + 2a 까지 완화** |
| 6 | 분산 vs 집중 | `max_open_risk_pct` 4.5 유지(실질 2종목) / 6~8 상향 | **4.5 유지**, 상향은 유닛-섹터 캡 후 별도 |
| 7 | donchian 확장 | T3(1억) 재검토 / 영구 제외 | **T3 재검토** — 2,000만 미만은 유닛 해상도 부재. ⚠️ 라이브 `atr_trail_mult=1.8` 이라 세트선 **신규 배선 필요**(초판의 "자동 정합" 은 거짓) |
| **8** | **[최종본] 다크런치 방식** | 코드 기본값 낮추기 / **DB 에 없는 신규 키** / 배포 선행 DB UPDATE | **신규 키** — 기존 `max_units_per_stock` 은 DB 에 `"2"` 가 이미 영속돼 코드 기본값 방식이 **성립하지 않는다**(§3.6 정정 ①) |
| **9** | **[최종본] `max_units` ↑ 시 `position_ratio`** | ρ 유지(0.166) / ρ 동반 하향(→0.10) | **동반 하향 검토** — per-ticker 캡 = `ρ × 예산 × max_units` 이고 저ATR 구간에서 ρ 가 유닛 명목을 **단독 결정**한다. ρ 유지 시 5,000만에서 계좌 30%가 1~2종목(§5.3 정정 3) |
| **10** | **[최종본] 섹터 taxonomy** | 현행 유지(29.5% fail-open) / 재설계 선행 | **재설계를 피라미딩과 분리해 먼저** — 피라미딩을 안 해도 kojiro 전체에 유효한 개선이고, 피라미딩의 유일한 상관 통제축이다(N-1) |

---

### 이 문서가 스스로 인정하는 가장 약한 고리 (초판 원문 — 갱신본은 부록 B 말미)

**"적용한다" 를 전제했지만, §5.2 는 여전히 기대값이 음수라고 말한다.**
이 청사진이 정직하게 할 수 있는 최선은 **"적용하지 말라" 가 아니라 "적용하되 이 순서로, 이 게이트를 지나서"** 이며,
그 게이트 중 **G3/G3′/G12 세 개가 실질적 관문**이다.

---

# 부록 B — 비판 반영 내역 (적대적 3렌즈 검토, 2026-09-03 2차)

> 검토 렌즈 = **engineering**(배관·계약·런타임) · **risk**(리스크 프레임·집중도) · **quant**(수치 재검산).
> 처분 = **반영**(문서 수정) / **부분 반영**(수정 + 잔여 명시) / **철회**(지적이 틀렸음을 실측으로 확인) / **유지**(원문 정당).
> **모든 지적을 그대로 받아들이지 않았다** — 아래 "철회 2건" 은 코드 실측으로 반증했다.
> 반대로 **내가 지적보다 더 나아간 곳도 있다**(R-H1 을 독립 재현하면서 `max_units` 단조성이라는 새 완화 수단을 얻었다).

## B.1 반영 요약

| 렌즈 | 지적 | 반영 | 부분 | 철회 | 강등 |
|---|---|---|---|---|---|
| engineering | 18 | 15 | 0 | 2 (C-33·C-34) | 1 (C-12 근거) |
| risk | 12 | 11 | 1 (R-M3) | 0 | 0 |
| quant | 9 | 8 | 1 (Q-L1) | 0 | 0 |
| **계** | **39** | **34** | **2** | **2** | **1** |

## B.2 전수 — engineering

| # | 지적 | 등급 | 독립 검증 | 처분 · 반영 위치 |
|---|---|---|---|---|
| E-1 | Stage 1 다크런치 전제 미성립 — DB 가 `max_units_per_stock="2"` 로 이미 덮는다 | HIGH | ✅ EC2 실측: kojiro `params` **nkeys=34**, `max_units_per_stock="2"`, `max_units_total="10"` | **반영** — §3.6 정정 ①② (신규 키 `pyramid_max_units` 기본 0 + `_PYRAMID_STRATEGIES=()`), 요약 결정 8 |
| E-2 | 추가↔청산 인터리브 → 스탬프 없는 orphan 재등록 | HIGH | ✅ `order_engine.py:494-527`(`is_buy_pending` 미검사) · `:1188-1198`(`if not pos:` 신규 등록) 실측 | **반영** — §4.4 **C-35** + §3.3.2 게이트 4종 신설 |
| E-3 | C-26 처방("order_no 기준")이 실제 race 에서 작동 불가 — 현행은 체결을 **버린다** | HIGH | ✅ `:1163-1172` `is_ticker_held_by_any → return` 실측 · `:273→:314→:371` 순서 실측 | **반영** — §4.4 **C-37** (`is_buy_pending` 귀속 + `_early_fills` replay) |
| E-4 | `save_position` ON CONFLICT 8컬럼 전부 덮어씀 → cycle236 재대조가 스탬프 삭제 | MEDIUM | ✅ `src/db/positions.py:21-58` 실측, 호출 3곳 | **반영** — §4.4 **C-38** (COALESCE 또는 전용 함수) |
| E-5 | `NUMERIC→Decimal` 부팅 크래시 + 마이그레이션 graceful-skip 사각 | MEDIUM | ✅ `pg._init_conn` jsonb/json 코덱만 실측 · `deploy.yml:37-47` `ON_ERROR_STOP=0 \|\| true` 실측 | **반영** — §4.4 **C-39** (DOUBLE PRECISION + 컬럼 자기점검) |
| E-6 | §3.4 스니펫이 P3 위반(`_apply_budget_limit(0)`→1주) + A-GATE 확장과 2주 하한 상충 | MEDIUM | ✅ `strategy_base.py:472-474` 실측 · `test_budget_limit_ast.py:120-147` 실측 | **반영** — §3.4 **전면 재작성** (`_apply_add_budget_limit` 2단 관문) |
| E-7 | §3.3.1 이 A-ATOMIC 을 구조적으로 깸 + `_place_and_track` 추출이 현행 가드 FAIL | MEDIUM | ✅ `test_budget_limit_ast.py:60-97` 이 `execute_buy` 본문 안 `add_lines` 요구 실측 | **반영** — §3.9 정정 ②③ (사이징을 `execute_add_unit` 안으로 · 추출은 별도 HIGH 카드) |
| E-8 | `mark_pending_buys_completed` 가 held 종목 PENDING 을 15분마다 ticker-wide 플립 | MEDIUM | ✅ `trade_history.py:247-266` · `scheduler.py:3634`(**skip 보다 앞**) 실측 | **반영** — §4.4 **C-40** (`rmn_qty==0` 한정) |
| E-9 | 사이클 5 → 현실 8~10, S1-1/S1-5 는 "행위 변경 0" 아님 | MEDIUM | ✅ `pending_buys` **136건 / src 9파일 + 테스트 24파일** 실측 | **반영** — §3.9 정정 ①④ (S1-5 를 5a/5b 분할) |
| E-10 | `is_max_positions` 이중 계수 + Σ리스크·섹터 pending 미계상 | MEDIUM | ✅ `strategy_base.py:402-405` · `kojiro.py:1072-1089`,`:827` 실측 | **반영** — §4.4 **C-41 · C-42** |
| E-11 | boot `sold_today` 시드 + 미체결 복구 held skip 이 추가를 매핑 밖으로 민다 | MEDIUM | ✅ `boot_manager.py:272-286`,`:300-320` 실측 | **반영** — §4.4 **C-43** |
| E-12 | `strategy_base.py` 8영역 여부를 한 문서 안에서 반대로 적음 | LOW | ✅ `test_cycle233_ast_account_risk.py:41-48` 목록 밖 확인 | **반영** — §3.9 8영역 행 (정답 = **비8영역**) |
| E-13 | "scheduler 폴 루프 물리적 불가" 과장 | LOW | ✅ AST docstring "사이클 한정 동결" 실측 | **강등 + 근거 교체** — §4.4.2 (결론 유지, 근거를 헤드룸·race 로) |
| E-14 | `_pos_contrib` 는 중복 원장 — 이미 증분을 받는다 | LOW | ✅ `order_engine.py:1039-1062` 증분 계산 실측 | **반영** — §4.4.3 (`_pos_contrib` 삭제) |
| E-15 | C-33(`DailyEmitCap` 키) · C-34(pg 왕복 테스트)는 실제 충돌 아님 | LOW | ✅ `daily_emit_cap.py:32` `Generic[K]` · 테스트가 명명 키만 단언 | **철회 / 강등** — §4.4.1 |
| E-16 | 부분체결 후 취소 시 `unit_count` 유닛 회계 부풀림 + `_filled_qty` 누수 | LOW | ✅ `:1305` 전량 분기 안 pop 실측 | **반영** — §4.4 **C-45** |
| E-17 | leaf 가격 소스 미명시 — 신선도 게이트 없으면 stale 발주 | LOW | ✅ `scanner.ticker_prices` / `ticker_last_tick` 실측 | **반영** — §3.3.2 게이트 4종 중 신선도 |
| E-18 | 긍정 확인 (kojiro `_SWING_POLL_STRATEGIES` 포함 · `get_trade_pairs` 가중평균 · deploy 순서) | INFO | ✅ `scheduler.py:144` 등 실측 | **유지** |

## B.3 전수 — risk

| # | 지적 | 등급 | 독립 검증 | 처분 · 반영 위치 |
|---|---|---|---|---|
| R-1 | §3.5 가 손절 *크기*만 재고 *확률*을 안 잼 — 세트선이 손절률 52.6%→75.0% | HIGH | ✅ **독립 재구현으로 재현**: 유니버스 n=965, 31,498 합성진입 → base **53.0%** → 1N×4 **75.3%**, 전환률 **22.3%**(risk: 22.46%) | **반영 + 확장** — **§3.5.1 신설.** 추가로 `1N×2` 를 측정해 **전환률이 max_units 의 단조 함수**(11.7%@2 → 22.3%@4)임을 확인 → Stage 2 승급 조건에 손절률 지표 편입 |
| R-2 | §3.4 스니펫이 캡 소진 시 1주 폴백으로 낙하 | HIGH | ✅ E-6 과 동일 | **반영** — §3.4 재작성 |
| R-3 | P5 가 `_selling` · `is_blocked` 등 신규 게이트를 구조적으로 은폐 | HIGH | ✅ `execute_sell:508-527` · `risk.py:593` 대비 실측 | **반영** — §3.3.2 게이트 4종 |
| R-4 | `_pending_cancel_tasks` 가 매수취소·매도취소를 **ticker 단일 키로 공유** | HIGH | ✅ `order_engine.py:78` 선언 1개, `:1467`(매수) · `:1491`(매도) 동일 replace 패턴 실측 | **반영** — §3.3.4 정정 + §4.4 **C-36** |
| R-5 | 집중도·꼬리가 라이브 파라미터로는 1.5배 — ρ=0.166 이 지배 | HIGH | ✅ `position_ratio=0.166` DB 실측 · ρ클램프 경계 `0.005/0.166=3.01%` · ATR 중앙 **5.18%** · 보유 6종목 중 2종목이 3.01% 미만 | **반영** — §1.3 정정 박스 · §5.3 **꼬리표 재계산**(ATR 3시나리오) · 요약 결정 7(ρ↓ 커플링) |
| R-6 | 섹터 캡 29.5% fail-open · 개수2→유닛6 은 3배 완화 · `max_units_total` 비구속 | MEDIUM | ✅ `_kojiro_sector_key` 정확 호출로 재현: **미분류 285/965 = 29.5%**, 업종-1009 23.7%, 업종-0027 13.5%, 키 29종 | **반영** — §3.6 정정 ③④⑤ + G11 문안 강화 |
| R-7 | Stage 0 이 일봉 배치라 "장중 순서" 질문에 원리적으로 답 못 함 | MEDIUM | ✅ 초판 §5.4 #6 이 스스로 그렇게 적어놓음 | **반영** — §3.9 Stage 0 **목적 재정의**(빈도·적격률·가상 세트선) |
| R-8 | 미스탬프 복원이 4유닛 손절선을 최대 1.5N 느슨하게 — P4 직격 | MEDIUM | ✅ 산식 재현: ATR 5.18% → 1.16N / ATR 2.70% → 1.50N 완화 | **부분 반영** — §3.1.5 정정 박스(정량 표 + 보수 강제 계약 ①~④). **잔여** = "최초 매수가 추정" 방법 미확정(별도 자문) |
| R-9 | `pos.last_entry_price` 를 체결량 무관 갱신 → 1주 체결이 세트선 1N 상승 | MEDIUM | ✅ §3.1.3 스니펫에 완결 조건 부재 확인 | **반영** — §4.4 **C-44** |
| R-10 | `daily_loss_limit` 이 스택과 구조적으로 상호작용 불가 + 계좌 스위치 부재 | MEDIUM | ✅ 한도 1,200,000 vs 계획손절 150,000(8배 여유) / −30% 갭 2,826,648(2.36배 초과) · `system_config` 에 `account_risk_*` 키 부재 실측 | **반영** — §5.3 "방어되지 않는 축" 재작성 |
| R-11 | §5.2 과잉 정밀도 · 손실의 62%가 018670 **1주 폴백 랏** 단일 거래 | LOW | ✅ `trade_history` 14왕복 전수 재현(−32,220원, 승률 3/14) | **반영** — §5.2 표본 한계 박스 |
| R-12 | 라이브 파라미터 5건 불일치(donchian 1.8 · max_positions 6 vs 5 · ATR 5.18 · 저ATR 편향 · VB 폴백 관측) | LOW | ✅ EC2 `strategy_config` 전수 실측 | **반영** — §3.5 검산 정정 · §1.3 · §5.4 #10 · §7 사이클 B 범위 |
| R-13 | 유동성은 제약이 아니고 프리장 청산 공백이 4배가 됨 | INFO | ✅ `risk.py:79` LTV-only 화이트리스트 실측 | **반영** — §5.3 방어되지 않는 축(프리장 항) |

## B.4 전수 — quant

| # | 지적 | 등급 | 독립 검증 | 처분 · 반영 위치 |
|---|---|---|---|---|
| Q-1 | §5.2 Δ/추가유닛 단위 정규화 오류 — "당시 R≈3,900" 이 사실이 아님 | HIGH | ✅ `roundtrips.csv` `asset_at_entry` 재현: **12/14 왕복이 1,144,956~1,197,043 → 1R 1,717~1,796원**, 2건만 3,952. `v3_pertrade.py` 재실행 → **−1.51R / −1.87R** | **반영** — §5.2 **표 전면 폐기·재작성**(5,000만 as-built **−34.4%**) |
| Q-2 | base −0.65R/왕복은 유닛당 값 오표기 → −0.99R, 증폭 ≈2.8배 | MEDIUM | ✅ −13.87R ÷ 14 = −0.99R 재현 | **반영** — §5.2 입력표 + 증폭 배수표 |
| Q-3 | as-built Δ 의 19% 가 `adds=0` 왕복의 청산 규약 대체 효과 | MEDIUM | ✅ 377450 −4,350 · 002810 +70 · 053800 −357 = **−4,637(19.4%)** 재현 | **반영** — §5.2 "순수 피라미딩" 열 신설(−1.27R/−1.50R) |
| Q-4 | §5.3 꼬리표가 사다리 체결가를 무시한 `g×4×명목` 근사로 퇴행 | MEDIUM | ✅ 정확 식 재현: 1N −10% 갭 = **289,351(5,000만)**, 초판 649,351 은 **2.24배 과대**. 배수 1.78×(4.0× 아님) | **반영** — §5.3 꼬리표 재계산 |
| Q-5 | P(1.0N) 은 보간 아니라 **실측 8/14=0.571** 이 원천에 있음 · 캘리브 "일관성" 은 우연 | MEDIUM | ✅ MFE_N 재집계로 재현(0.643/0.571/0.357/0.357/0.143) | **반영** — §5.2 입력표(1.571 · 캘리브 0.755/0.710) |
| Q-6 | Stage 2 자본 게이트가 문서 3곳에서 불일치 | MEDIUM | ✅ §3.9/§6/T2 대조 | **반영** — §3.9 Stage 2 표를 정본화(2a 2,000만 / 2c 5,000만) |
| Q-7 | §1.3 은 재현되나 kojiro 픽이 고가 편향이라 258만·500만 행이 ~1.2배 낙관 | LOW | ✅ 유니버스 중앙가 24,650 재현(초판 24,550) | **부분 반영** — §1.3 정정 박스에 ATR 편향은 명시. **잔여** = 가격 편향은 §5.4 에 미편입(5,000만 결론에 영향 없음) |
| Q-8 | 표본 한계가 표 자체에 미반영 · Stage 0 이 재는 것은 이미 아는 빈도 | LOW | ✅ 236200 theory qty=0 → as-built add 0건 재현 | **반영** — §5.2 한계 박스 · §5.4 #16 · §3.9 Stage 0 목적 재정의 |
| Q-9 | 재현 확인 (adv_sim 6변형 · G3 MDE · 연130왕복 · scheduler 3,999 등) | INFO | ✅ | **유지** |

## B.5 이 개정이 바꾸지 **않은** 것

| 항목 | 유지 이유 |
|---|---|
| 롤아웃 순서 (Stage 0 → 0.5 → 1 → 2) | 모든 지적이 **순서를 강화**했다. 특히 R-11(손실의 62%가 1주 폴백 랏)은 Stage 0.5 우선 권고의 직접 증거다 |
| 대상 **kojiro 단독** | R-12 가 donchian `atr_trail_mult=1.8` 을 드러내 **donchian 확장 난이도가 오히려 올라갔다** |
| 원장 = **가중평단** (랏 원장 기각) | 접촉면 논거는 무손상. E-14 가 오히려 더 단순화(`_pos_contrib` 삭제) |
| **앵커 = `last_entry_price` 단조 사다리** | 물타기 금지 논거 무손상 |
| 추가 유닛 **≥ 2주** 하한 | E-6/R-2 는 *구현 방법*을 고쳤을 뿐 규칙 자체는 강화됐다 |
| **G3 / G3′ / G12 가 실질 관문** | Q-1 이 부호를 **더 확실하게** 만들었다(P(Δ>0)=1.6%) |
| 자본 게이트만으로는 불충분 | Q-1 정정으로 이 논지가 2.7배 강해졌다 |

## B.6 이 개정이 새로 만든 미해결 항목 (별도 등재 권고)

| # | 항목 | 왜 별도인가 |
|---|---|---|
| **N-1** | **섹터 taxonomy 재설계** — 29.5% fail-open + catch-all 37% | 상관 통제축이 종이인데, 고치는 것은 피라미딩과 독립적으로 kojiro 전체에 유효하다. **피라미딩보다 먼저 해도 되는 일** |
| **N-2** | **`position_ratio` ↔ `max_units` 커플링 정책** | 4유닛 ON 시 ρ 를 얼마로 내릴지가 미결. 집중도를 결정하는 유일한 손잡이 |
| **N-3** | **미스탬프 복원 시 "최초 매수가 추정"** | R-8 잔여. KIS 는 평단만 준다 — `trade_history` BUY 행 역추적이 유일 후보 |
| **N-4** | **계좌 레벨 드로다운 정지선** | cycle232 에서 이미 "입출금 보정 선행" 으로 보류된 항목. §5.3 이 그 부재를 다시 증명했다 |
| **N-5** | **`_place_and_track` 행위 보존 리팩토링 (HIGH 카드)** | E-7. 가장 봉인된 함수의 구조 변경 — domain-expert 행위 영향 평가 동반 필수 |
| **N-6** | **`[kojiro_pyramid_stop_shift]` 관측 설계** | §3.5.1. 세트선의 손절률 효과를 사후 판정할 유일한 필드 |

---

### 이 개정본이 스스로 인정하는 가장 약한 고리 (갱신)

초판은 *"§5.2 는 여전히 기대값이 음수라고 말한다"* 를 가장 약한 고리로 적었다.
**정정 후 그 고리는 더 약해진 게 아니라 더 굵어졌다** — 음수의 크기가 2.7배가 됐고 P(Δ>0)=1.6% 다.

**그런데 정확히 같은 개정에서 반대 방향 증거도 나왔다.** §3.5.1 의 31,498 표본 기계적 실험에서
피라미딩 기제 자체는 **평균 손익을 개선**한다(+0.170 → +0.556 uN). 두 결과가 모순이 아닌 이유는
**측정 대상이 다르기 때문**이다 — 전자는 *kojiro 의 실제 청산 규약 아래*, 후자는 *20영업일 고정 보유 아래*.

→ **따라서 이 문서의 진짜 가장 약한 고리는 "기대값이 음수" 가 아니라
"음수인 이유가 피라미딩인지 청산 규약인지를 우리가 아직 구분하지 못한다" 이다.**
그리고 그것을 구분하는 유일한 도구가 **G12(피라미딩 × 청산규약 격자 백테스트)** 다.

**자본 5,000만은 G1(실행 가능성) 하나만 열어주지 G3(수익성)를 열어주지 않는다.**
만약 자본이 5,000만에 도달했는데 G3 가 여전히 닫혀 있다면, 그때 해야 할 일은 피라미딩이 아니라
**kojiro 의 청산이 오른쪽 꼬리를 지키게 만드는 일**이다
(승률 21.4% vs 손익분기 36.8% — 진입을 키우는 것으로는 이 간극이 메워지지 않는다).

---

### 재현 스크립트 (read-only, scratchpad)

| 산출 | 스크립트 |
|---|---|
| Δ/추가유닛 재정규화 · 부트스트랩 · adds=0 오염 분해 | `scratchpad/v3_pertrade.py` (원본 `adv_sim.py`) |
| 꼬리표 사다리 반영 재계산 · per-ticker 캡 | `scratchpad/final/` (본문 §5.3 산식) |
| 유니버스 ATR 분포 · 섹터 키 분포 · **31,498 사다리 손절률 재현** | `scratchpad/final/ec2_sector_ladder.py` (EC2 read-only) |
| `strategy_config` / `system_config` 라이브 파라미터 | `scratchpad/final/ec2_params2.py` |
| 도달확률 실측 (MFE_N) | `scratchpad/pyramid/roundtrips.csv` |
