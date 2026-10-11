# 전략별 예산 사용률·칸 수 측정 — 오프라인 Claude Code 전달 지시서

> 작성 2026-10-02 · 계기 = 사용자 질문 「전략당 종목 수 제한(`max_positions`)이 너무 작게 투자하는 효과가 있지 않나」.
> 이 문서 전체를 오프라인 세션의 첫 메시지로 붙여 넣는다. 받는 세션은 루트 `CLAUDE.md` 하네스(team-leader 1차 라우팅)를 따른다.

---

## 0. 받는 세션에게 — 한눈에

- **이번 일은 측정뿐이다.** 운영 DB 를 읽기만 하고, 파라미터·비중·코드는 바꾸지 않는다.
- 결과로 전략마다 「칸이 남는다 / 칸이 모자라다 / 1주 문제」 중 어디에 해당하는지 판정한다(§4 의 규칙은 측정 전에 고정).
- 판정에 따른 파라미터 변경안은 **제안만** 한다. 실제 변경은 매매 행위 변경이라 domain-consult + 사용자 승인 대상이다(루트 CLAUDE.md 「여전히 승인이 필요한 것」).
- 커밋·push 는 사용자가 명시할 때만.

### 용어 풀이

| 용어 | 쉬운 뜻 |
|---|---|
| 칸(슬롯) | 전략 하나가 동시에 들고 있을 수 있는 종목 수 = `max_positions` |
| 랏 | 한 번에 사는 묶음. 설계 금액 = 전략 예산 × `position_ratio` |
| 예산 사용률 | 그날 실제로 주식에 들어간 돈 ÷ 그 전략 예산 |
| 칸 찬 날 | 보유 + 매수 대기 종목 수가 `max_positions` 에 닿은 날 |
| 1주 폴백 | 설계 랏으로 0주가 나오면 1주라도 사는 예외 경로 |
| q | 설계 랏 ÷ 그 전략이 사는 종목의 중앙 주가 = 한 랏에 몇 주를 사나 |

---

## 1. 배경 — 이미 확인된 사실 (2026-10-01~02 클라우드 세션)

1. **한 종목 금액은 `max_positions` 가 아니라 `position_ratio` 가 정한다.** 다만 불변식 `position_ratio × max_positions ≤ 1.0`(AST C-DEFAULT, `portfolio_risk.check_budget_invariant`)이 둘을 묶어서 칸을 늘리면 랏이 작아진다.
2. **q 실측(입금 후 순자산 약 500만, 루트 CLAUDE.md 「자금 관리」)** — VB **0.74** · LTV 1.11 · donchian 2.70 · momentum 4.34 · BFB 5.66 · kojiro 10.11. VB 는 설계 랏으로 1주도 못 산다.
3. **빈 칸의 예산은 다른 전략이 못 쓴다.** `StrategyRegistry.allocate_funds`(`src/engine/strategy_registry.py:36-45`)가 전략별 `total_investment` 를 고정 배분하고, 예산을 빌려주는 경로가 없다.
4. **「칸이 차서 못 산」 기록은 없다.** 7전략 `check_buy_signal` 이 `if self.is_max_positions(): return Signal.NONE` 으로 조용히 넘어간다(`vcp_breakout.py:1411` · `volatility_breakout.py:941` · `long_tail_volatility.py:797` · `bull_flag_breakout.py:969` · `kojiro.py:909` · `momentum.py:149` · `donchian_swing.py:1642`). 판정 = `len(positions) + len(pending_buys) >= max_positions`(`strategy_base.py:542-545`).
5. **전략별 일일 예산은 복원 가능하다.** 21:30 정산이 전략마다 `daily_performance(strategy=sid).total_asset = state.total_investment + 당일 실현손익` 을 쓴다(`scheduler.py:3537-3561`). → **예산 ≈ `total_asset − daily_realized_pnl`**. 계좌 전체는 `strategy='total'` 행의 `total_asset`(순자산)·`deposit`(예수금).
6. **파라미터 현재값은 DB 가 정본이다.** 코드 `DEFAULT_PARAMS` 와 다르다(예: kojiro·BFB·VCP 는 PUT 으로 `sizing_mode=turtle` 전환됨). `strategy_config.params` 를 읽는다. 과거 변경 이력은 DB 에 없다 → §3.3 의 사건표로 기간을 나눈다.

---

## 2. 산출물

- 스크립트: `tools/slot_utilization_review.py` — `tools/kojiro_live_review.py` 와 같은 모양(READ-ONLY 선언, DSN·SSL 처리 복사, 표준출력에 표). DB 쓰기 0, KIS 호출 0.
- 실행: EC2 에서 `docker compose exec -T backend python - < tools/slot_utilization_review.py > slot_util.txt`. 사용자가 결과를 붙여 넣으면 분석한다.
- 보고: `_workspace/analysis/slot_utilization_20261002/`(원문 md + 집계 CSV) → 쉬운 말 요약 + 결정 카드. 결정 카드가 3개 이상이면 `cycle-report` 스킬.
- 테스트: 보유 재구성 함수(§3.2)는 순수 함수로 떼어 `tests/unit/tools/` 에 단위 테스트(부분 매도·같은 날 사고팔기·PENDING/CANCELLED 제외).

---

## 3. 측정 방법

### 3.1 기간

- 주 기간 = **2026-09-21 ~ 최근 정산일**(09-20 입금으로 순자산이 약 2배가 된 뒤).
- 비교 기간 = 그 이전 60영업일(입금 전 — 랏이 절반이던 때). 두 기간을 섞지 않는다.

### 3.2 보유 재구성 (전략·종목·날짜)

- 출처 = `trade_history` 중 `status IN ('COMPLETED','PARTIAL')` — 매수(`trade_type='BUY'`)·매도. `strategy_id`·`ticker`·`price`·`quantity`·`timestamp`(KST 로 변환). PENDING·CANCELLED 제외.
- 종목별로 시간순 누적해 「그날 장 마감 보유 수량·매입원가」 를 만든다. **부분 매도가 있다**(cycle385 이후) — 수량을 빼고 0 이 되면 닫는다.
- **장중 최대치도 따로** 낸다 — VB(당일 15:20 청산)·momentum(익일 청산)은 장 마감 보유로 보면 사용률이 0 에 가깝게 나온다. 체결 시각 순서로 동시 보유 종목 수의 그날 최댓값을 잰다.
- 교차 검증 = 오늘 날짜의 재구성 결과가 `positions` 테이블과 종목·수량 일치하는지(불일치는 목록으로 보고, 원인을 추측하지 않는다).

### 3.3 기간을 가르는 사건 (사용률을 칸 탓으로 오해하지 않게)

| 날짜 | 사건 | 영향 |
|---|---|---|
| 09-20 | 입금(250만→500만) | 모든 전략 예산 2배 |
| 09-25 저녁~ | BFB `entry_end` 09:04 | BFB 신규 매수 사실상 멈춤 |
| 09-26 | VCP `sizing_mode=turtle` | VCP 랏 산식 변경 |
| 09-27 16:14~ | donchian `buy_paused=true` | donchian 신규 매수 0 — **칸과 무관한 빈 칸** |
| 09-28 21:42 | LTV 비중 0(퇴출) · `cash_usage_ratio` 0.95 | LTV 제외 |
| 09-29 | BFB `sizing_mode=turtle` | BFB 랏 산식 변경 |

- 워크리스트(`_workspace/00_URGENT_WORKLIST.md`)에서 이 표 밖의 비중·파라미터 변경을 더 찾아 추가한다.
- 매수를 멈춘 기간(`buy_paused`·`entry_end` 조정)은 그 전략의 사용률·칸 판정에서 **뺀다**.

### 3.4 지표 (전략별 · 계좌 전체)

1. **예산 사용률** = 장 마감 매입원가 합 ÷ 그날 예산(§1-5). 평균·중앙·분포(0% 인 날 비율 포함). 장중 최대 기준도 같이.
2. **칸 사용률** = 보유 종목 수 ÷ `max_positions`. **칸 찬 날 비율**(장 마감·장중 최대 둘 다).
3. **계좌 전체 현금 비중** = 1 − (전 전략 매입원가 합 ÷ 순자산). 의도된 현금(`cash_usage_ratio` 0.95 → 5%)과 분리해 「의도 밖 현금」 을 따로 적는다.
4. **랏 모양** = 매수 1건당 주식 수 분포, 1주 매수 비율, 설계 랏(예산 × `position_ratio`) ÷ 체결가 = 건별 q. 루트 CLAUDE.md 의 q 와 비교.
5. **놓친 신호 근사치** — 기록이 없으므로(§1-4) 근사한다:
   - 일봉 스윙(kojiro·donchian·BFB·VCP): `strategy_funnel_snapshots` 의 그날 마지막 단계 통과 종목(`survived_tickers`) 중 그 전략이 안 산 종목 수를, **칸 찬 날과 아닌 날로 나눠** 센다. 칸 찬 날에만 많으면 칸 부족의 증거다.
   - 틱형(VB·momentum): 근사가 약하다. 「칸 찬 날의 비율」 만 보고 놓친 수는 「측정 불가」 로 적는다.
   - funnel 통과 ≠ 매수 신호다(그 뒤에도 가격·시간 조건이 있다). 이 한계를 보고서에 적는다.
6. **사용률과 성과** — 예산 사용률 구간별 그 전략의 실현손익(같은 기간). 표본이 작으면(전략당 청산 < 10) 「표본 부족」.

---

## 4. 판정 규칙 (측정 전에 고정 — 결과를 보고 바꾸지 않는다)

매수를 멈춘 기간을 뺀 주 기간에서, 전략마다:

| 판정 | 조건 | 뜻 | 후보 처방(제안만) |
|---|---|---|---|
| **A 칸 남음** | 칸 찬 날 < 10% **그리고** 평균 칸 사용률 < 50% | 칸이 남아 돌고, 칸 수가 랏만 작게 만든다 | ① `max_positions` 줄이고 `position_ratio` 올리기(불변식 유지, `weight` 무접촉) |
| **B 칸 부족** | 칸 찬 날 ≥ 30% **그리고** (스윙이면) 칸 찬 날의 미매수 funnel 통과 수가 아닌 날보다 많다 | 신호를 놓치고 있다 | ① 금지. ② 비중 재배분 또는 칸 유지 |
| **C 1주 문제** | 매수 건 중 1주 비율 > 50% **또는** 건별 q 중앙 < 2 | 칸과 무관하게 랏이 너무 작다 | 비중 재배분(② ) — CLAUDE.md 「배분 문제」 |
| **D 정상** | 위에 해당 없음 | — | 변경 없음 |

- A 와 C 는 겹칠 수 있다(VB 예상). 겹치면 둘 다 적는다.
- 처방 ①을 제안할 때 **한 종목 손절 충격**을 함께 적는다: 새 랏 × |손절%| ÷ 순자산. 예: kojiro `hard_stop_pct` −8%.
- 처방 ③ 「전략 간 남는 예산 공유」 는 이번 판정에서 다루지 않는다(8영역 `strategy_registry.py` + 집중 위험 — 별도 설계 주제). 계좌 전체 「의도 밖 현금」 이 20% 를 넘으면 별도 결정 카드로만 올린다.

---

## 5. 선택 단계 — 「칸 차서 못 산」 관측 마커 (승인 후에만)

§3.4-5 근사가 약하면 다음을 결정 카드로 올린다(이번에 구현하지 않는다).

- 7전략 `check_buy_signal` 의 `is_max_positions()` 분기에 관측 마커 `[slot_full_skip] strategy= ticker=` 를 **종목당 하루 1회**만 남긴다. 행위 변경 0(반환값 그대로).
- 전략 파일은 8영역이 아니지만 매수 경로라 사전 승인 범위에 넣지 않는다. 틱마다 불리므로 중복 억제 집합은 `_reset_daily_state` 동행으로 비운다.
- INFO 는 보존 2일이라 15:30 에 전략별 건수 요약 1줄을 남기는 방안도 함께 제시한다.

---

## 6. 진행 순서 (받는 세션)

1. 워크리스트 읽기 → team-leader 에 이 문서 전달.
2. 스크립트 작성(tdd-engineer 가 보유 재구성 단위 테스트 먼저) → 사용자에게 EC2 실행 명령 전달 → 결과 수신.
3. 분석·판정(§4 표 그대로). 판정이 처방 ①·② 로 이어지면 **domain-consult** 로 전략별 새 값 자문(손절 충격·신호 빈도·슬리피지).
4. 보고서 + 결정 카드. 파라미터 변경은 사용자 결정 뒤 `PUT /api/strategies/{id}/params`(즉시 반영)로, 장외에, 보유 영향 확인 후.

## 7. 연결

- 평균회귀 지시서(`design/2026-10-01_mean_reversion_handoff.md`)의 「kojiro 에서 비중 0.05」 결정과 이어진다. 이 측정에서 kojiro 가 A(칸 남음)로 나오면 0.05 이전 부담이 작고, B 로 나오면 이전 시점·방식을 다시 본다.
- VB 는 12-31 시한부·장세 게이트 결정 보류 중이다(워크리스트). VB 처방은 그 결정과 묶어 올린다.

## 8. 금지

- DB 쓰기 · KIS 호출 · 파라미터/비중 변경 · 측정 뒤 판정 규칙 조정
- `weight=0` 으로 칸을 정리하는 제안(= 전략 비활성화 = 손절 정지 금기)
- 보유 중인 전략의 `max_positions` 를 보유 수보다 낮추는 제안(신규 매수만 막히고 기존 보유는 유지되지만, 의도와 다르게 오래 막힐 수 있다 — 제안 시 그 영향을 적는다)
