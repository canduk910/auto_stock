---
name: risk-review
description: "리스크관리부서 관점의 위험 노출 점검·주간 자문 리스크 검토 절차. 운용 전략의 계좌 오픈리스크·전략별 노출·섹터·묶음 집중·손절 거리·멀티데이 갭 위험·유동성·낙폭을 실측하고, 시장 유닛(시장별 종합지수)·매크로 레짐·6장세와 비교해 노출 축소 권고를 신호등과 함께 낸다. 「주간 자문 검토」, 「리스크 점검/리뷰」, 「위험 노출」, 「장세 대비 포지션」, 「한도 사용률」, 「노출 줄여야 하나」, 「리스크 보고서 다시/업데이트」 요청이나 목요일 주간 자문 산출물이 나온 뒤에는 반드시 이 스킬을 쓴다(risk-manager 에이전트). 개별 매매 판단의 시장 해석(domain-consult)이나 코드 변경(auto-trading-orchestrator)에는 쓰지 않는다."
---

# Risk Review — 위험 노출 점검과 주간 자문 리스크 검토

리스크관리부서의 일은 「얼마나 잃을 수 있는가」를 재고, 장세에 비해 과한 노출을 찾아, 줄이는 수단을 권하는 것이다. 권고만 하고 실행하지 않는다 — 비중·파라미터·전략 on/off 는 사용자 결정 사항이기 때문이다.

## 0. 컨텍스트 확인
- `_workspace/risk/` 에 지난 보고서가 있으면 먼저 읽는다. 지난주 권고의 채택 여부(`docs/HARNESS_CHANGELOG.md`·`GET /api/strategies` 현재값과 대조)와 그 뒤 노출 변화를 1절에 적는다.
- 주간 자문 산출물을 찾는다: `_workspace/domain_consult/weekly_advice_*.md`(최신) · `GET /api/recommendations`(최근 7일) · 루틴 브랜치·PR(`git fetch --prune` 뒤 `gh pr list`·`claude/weekly-advice-*` 브랜치 — main 에 없을 수 있다). 없으면 그 사실을 첫 줄에 적고 노출 점검만 한다.

## 1. 실측 — 어디서 무엇을 재나
운영 값만 쓴다. EC2 `ssh auto-stock`, 원격 첫 줄 `export TZ=Asia/Seoul`, backend 컨테이너 안 python(`src.db.pg`·`urllib` + 헤더 `X-API-Key` = 컨테이너 env `API_AUTH_KEY`, 값 출력 금지). 조회만 한다.

| 축 | 원천 |
|---|---|
| 계좌 오픈리스크·전략별·섹터별 | `GET /api/portfolio/risk`(척도 병기 — 프록시 `buy×qty×|하드손절%|` 와 실효 손절선 기준), 계좌 게이트 `account_gate`(warn/block 임계·stale) |
| 전략 설정·예산·보유 | `GET /api/strategies`(비중·`enabled`·`buy_paused`·`shadow_mode`·`market_unit_mode`·`position_ratio`·`max_positions`·`sizing_mode`·`risk_pct`) · `GET /api/strategies/system/cash-usage-ratio` · `GET /api/trading/status` |
| 손절 거리 | `GET /api/balance/exit-lines`(실효 손절선·출처) + 현재가 — `—`·`engine_idle`·`mode_dependent` 는 「모름」 |
| 묶음(상관) 집중 | `system_logs` 오늘 `[account_cluster_assign]`(묶음별 held_u·notional_pct·cap — 기록 전용) |
| 장세 | `GET /api/market-unit/chart`(시장별 state·m·effective) · `GET /api/market-regime/current`(관찰 지표) · `GET /api/market-regime-label`(6장세) |
| 성과·손실 | `daily_performance`(전략별 TWR·실현, `strategy='total'` 행은 합계라 SUM 에서 뺀다) · `GET /api/strategies/te`(TE·RR·표본) · `GET /api/costs/summary` |
| 유동성 | 보유 종목 `stock_master.raw.acml_tr_pbmn`(거래대금) 대비 보유 명목 |
| 운영 위험 | 오늘 ERROR·CRITICAL · `[market_unit_unavailable]` · 레짐 `data_available=false` · 보조 시세 세션 비활성 |

🔴 SUM 전에 행의 정체를 본다(합계 행·중복 행). 2배·10배 수치는 의심하고 교차 검산(`total_asset ÷ weight` 등)을 한 줄 둔다.

## 2. 판정 — 무엇을 위험으로 보나
한도는 **이미 코드·DB 에 있는 값**을 기준으로 쓴다(새 한도를 지어내지 않는다). 없는 축은 「한도 없음 — 관찰값」으로 적는다.

| 항목 | 기준 | 노랑 | 빨강 |
|---|---|---|---|
| 계좌 Σ오픈리스크 | `account_risk_warn_pct`·`account_risk_block_pct`(DB) | warn 이상 | block 이상 또는 게이트 stale |
| 전략 오픈리스크 | kojiro `max_open_risk_pct` · 그 밖은 `position_ratio × max_positions × |손절|` | 80% 이상 | 초과 |
| 묶음 집중 | `account_cluster` `CLUSTER_CAP_U`·`CLUSTER_CAP_PCT` | cap 도달 | cap 초과 |
| 손절 거리 | 실효 손절선까지 | 1% 미만 종목 있음 | 손절선 「모름」 보유 있음 |
| 갭 위험 | 멀티데이 보유 명목 × 하락 장세 | 하락 장세 + 멀티데이 노출 증가 | 하락 장세 + 손절 폭 > 일평균 변동 2배 |
| 장세 대비 | 시장 유닛 `down_falling`(m=0) 시장의 보유·신규 노출 | m<1 인데 `shadow` 모드 전략이 그 시장에서 산다 | m=0 시장에 신규 노출이 늘었다 |
| 유동성 | 보유 명목 ÷ 일 거래대금 | 1% 이상 | 5% 이상 |
| 낙폭 | 누적 TWR 고점 대비 | −5% | −10% |
| 데이터 공백 | fail-open 상태 | 하나 있음 | 손절·한도 판정에 걸림 |

문턱(1%·5%·−5% 등)은 이 스킬의 **관찰 기준**이다. 매매 규칙이 아니며, 바꾸려면 사용자에게 묻는다.

## 3. 권고 — 줄이는 수단
효과가 빠르고 되돌리기 쉬운 순서로 고른다.

1. `buy_paused=true`(그 전략 신규 매수만 멈춤, 청산·손절은 그대로, PUT 즉시)
2. `position_ratio`·`max_positions` 축소(불변식 `position_ratio × max_positions ≤ 1.0` 유지, PUT 즉시)
3. `market_unit_mode` `shadow` → `enforce`(장세 축소를 실제로 적용)
4. `cash_usage_ratio` 하향(계좌 전체, 다음 영업일 반영)
5. 비중 재배분 — 보유 있는 전략의 비중 0 은 **금지**(손절 정지). 줄이기만, 0 은 보유 0 확인 뒤에만.

권고마다 `전략 · 키 · 현재값 → 권고값 · 줄어드는 노출(원·%) · 부작용 · 되돌리는 법`을 적는다. 🔴 `PARAM_RANGES`/`INT_PARAMS` 편입 금지 키(리스크 정체성 상수 — `max_positions`·`max_lot_units`·`max_lot_ratio_mult`·`buy_paused`·`shadow_mode`·`market_unit_mode` 등)는 사람이 PUT 으로만 바꾼다고 명시한다.

## 4. 산출물 — `_workspace/risk/YYYY-MM-DD_weekly_risk.md`
```
# 주간 리스크 검토 YYYY-MM-DD
신호등: 🟢/🟡/🔴 · 권고 n건(빨강 n) · 측정 시각 KST
## 1. 지난주 권고 결과
## 2. 노출 요약 (계좌·전략별 표 — 예산·보유 명목·오픈리스크·한도·사용률)
## 3. 장세 대비 (시장별 m·state ↔ 그 시장 보유·신규 노출)
## 4. 집중·유동성·손절 거리·갭
## 5. 주간 자문 권고의 위험 영향 (권고별: 노출 증감 · 리스크 의견 동의/조건부/반대)
## 6. 권고 (표 — 3절 형식)
## 7. 측정 불가·데이터 공백
## 8. 결정 기록 (team-leader 채택/보류/반려 + 사유 — 회신 뒤 채운다)
```
쉬운 말·짧은 문장, 숫자는 원문 출처(API·쿼리)와 함께. 결정 카드가 필요하면 report-writer 에게 넘긴다(`cycle-report`).

## 5. 흐름 — team-leader 와 함께 검토
1. risk-manager 가 1~4 를 만든다.
2. team-leader 에게 신호등·권고 요약을 보낸다. team-leader 는 각 권고를 채택/보류/반려하고 사유를 회신한다.
3. 채택된 것 중 매매 행위를 바꾸는 것은 사용자 결정 + `domain-consult` 선행(루트 `CLAUDE.md`). 실행은 사용자 승인 뒤 메인 세션이 한다.
4. 빨강은 회신을 기다리지 않고 사용자에게도 바로 보고한다.

## 테스트 시나리오
- 정상: 목요일 주간 자문 md 가 있고 보유 3종목 → 표 2~4 채움, 자문의 비중 증액 권고 1건에 「조건부 — 그 전략 오픈리스크 사용률 85%」.
- 실패: 주간 자문 루틴 실패 + `/api/portfolio/risk` 500 → 첫 줄 「자문 산출물 없음」, 계좌 오픈리스크 「측정 불가」를 노랑으로, 나머지 축은 진행.
