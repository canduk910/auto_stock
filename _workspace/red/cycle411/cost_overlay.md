# cycle411 Red — 실적 화면에 실비용(수수료·세금) 합치기

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` (사용자 결정 10-08 Q1~Q4).
작성 = tdd-engineer, 2026-10-08. 브랜치 `feat/cost-overlay` (작업 디렉터리 `auto_stock_c411`).

## 테스트 파일

| 파일 | 덮는 것 |
|---|---|
| `tests/unit/engine/test_cycle411_cost_overlay.py` | 추정 요율 · `allocate_rows` 일반화 · 체결 행 단위 비용(정산/추정/ETF/배분) · net TWR · 날짜 상태 · leaf import 경계 |
| `tests/unit/engine/test_cycle411_te_net.py` | `compute_te_rr` net 판정 + `*_gross` 칸 |
| `tests/unit/db/test_cycle411_cost_overlay_db.py` | `get_trade_pairs` id 병행 리스트 · `trade_cost.get_trades_by_status` |
| `tests/unit/routes/test_cycle411_cost_overlay_routes.py` | 라우트 7곳 가산 칸 + 기존 칸 불변 + 비용 조회 실패 시 기존 응답 유지 |
| `tests/unit/ast/test_cycle411_ast_scope.py` | 8영역·`scheduler.py` 내용 sha 불변 · 행위 보존 테스트 2파일 무수정 (사이클 한정, 머지 후 삭제) |
| `frontend/src/components/__tests__/{PerformanceCard,ProfitChart,TradePnLGrid,OrderMonitor,BalanceTable,TradeHistoryGrid}.cost.cycle411.test.tsx` | 각 화면 새 칸·배지·토글 |
| `frontend/src/components/__tests__/DailyReportTab.gross.cycle411.test.tsx` | 「세전」 라벨 |
| `frontend/src/pages/__tests__/StrategiesTeRr.cost.cycle411.test.tsx` | 3개월 실현 = 세후 |
| `frontend/src/components/__tests__/handlers.honesty.cycle411.test.ts` | MSW 기본 목·e2e api-mocks 정직화 |

## 인터페이스 (이 Red 가 정한 계약 — 구현은 이름·모양을 따른다)

### 백엔드 순수 함수 `src/engine/cost_overlay.py` (새 leaf, 8영역·scheduler import 금지)
- `estimate_rates(cost_rows) -> {"fee_rate": float, "tax_rate": float, "source": "measured"|"default"}` — 기본값 0.00142 / 0.00199
- `trade_costs(cost_rows, trades, rates, etf_tickers=frozenset()) -> dict[id, {"fee","tax","cost_status","allocated"}]`
  - trades 행 키 = `id, trade_date(date), ticker, ticker_name, trade_type, strategy, price, quantity, profit_loss, order_price, status`
  - ETF 판정 = `etf_tickers` 에 있거나 `etf_like.is_etf_like(None, ticker_name)` (stock_master raw 는 어댑터가 `etf_tickers` 로 넘긴다)
  - 정산값이 있으면 ETF 라도 정산 세금을 그대로 쓴다
- `net_twr(records, costs_by_date) -> list[dict]` — records = `daily_performance` 행(오름차순), costs_by_date = `{date: {"fee","tax","cost_status"}}`. 반환 행 키 = `date, daily_fee, daily_tax, daily_net_pnl, net_daily_profit_rate, net_cumulative_return_rate, cost_status`
- `day_cost_status(statuses) -> "settled"|"estimated"|"mixed"`

### `src/engine/trade_cost.py`
- `allocate_rows(cost_rows, trades, key=...)` — 결과 행에 `key` 이름의 칸. `attribute(c, t) == allocate_rows(c, t, key="strategy")`

### DB (가산형)
- `src/db/trade_cost.py::get_trades_by_status(start, end, statuses)` — `status = ANY($n::text[])`, KST `trade_date`, `id`·`ticker_name`·`order_price`·`status` 포함
- `get_trade_pairs` 페어에 `buy_trade_ids`·`sell_trade_ids`(int, 시간순, id 없는 행은 목록에서만 빠짐, open 은 `sell_trade_ids=[]`)
- 라우트 테스트는 `src.db.trade_cost.get_daily_range`·`get_trades_by_status`·`src.db.daily_performance.get_performance` **모듈 속성**을 갈아 끼운다 → 구현은 `from src.db import trade_cost as trade_cost_db` 처럼 모듈 경유로 부른다

### 라우트 응답 칸
- `/api/performance/daily` 행: `daily_fee, daily_tax, daily_net_pnl, net_daily_profit_rate, net_cumulative_return_rate, cost_status`
- `/api/performance/summary`: `net_total_profit_rate, net_avg_daily_profit_rate`
- `/api/history` 행: SELL `fee, tax, net_profit_loss`(= 그 행 profit_loss − 그 행 fee − tax), BUY `fee`, 공통 `cost_status`
- `/api/history/pnl` 페어: `fee, tax, net_profit_loss, net_profit_rate, cost_bp, slippage_won, cost_status, allocated`; summary: `fee_sum, tax_sum, realized_net_total_krw, realized_net_rate_pct, slippage_n`(closed 페어 기준)
- `/api/strategies/te`: `te_pct`·`win`·`loss`·`verdict` 등 판정 = net, `te_pct_gross, te_krw_avg_gross, win_rate_gross`, `realized_sum_krw`(세전 그대로), `realized_net_sum_krw, fee_sum, tax_sum`
- `GET /api/costs/today?strategy=`: `{date, fee_rate, tax_rate, rate_source, cost_status, strategies:[{strategy,gross_pnl,fee,tax,net_pnl}], total:{gross_pnl,fee,tax,net_pnl}}`
- `GET /api/costs/daily?from=&to=`: `{from, to, days:[{date, fee, tax, slippage_won, slippage_n, cost_status}]}` — 날짜 오류 422(`_parse_range` 재사용)
- `/api/balance` 보유 종목: `sell_cost_rate`(fee_rate + tax_rate, ETF 는 fee_rate), `cost_status="estimated"` — 화면이 실시간 평가금액에 곱한다
- 비용 조회 실패 = 기존 응답 200 그대로, 새 순손익 칸만 None (기존 `tests/contract` 무수정 통과)

### 프론트
- 토글 = testid `cost-basis-toggle` 안 버튼 `세후`/`세전`(`aria-pressed`), localStorage `autostock.costBasis` = `net|gross`(try/catch), 화면 공통(같은 화면 두 토글이 함께 바뀜). net 칸 없으면 세전 값.
- ProfitChart: 차트 컨테이너 testid `profit-chart-daily`·`profit-chart-cumulative` + `data-series` 속성(그리는 dataKey). 제목에 `세후`/`세전`.
- TradePnLGrid: 머리 `수수료·세금·순손익·순손익율·비용률·슬리피지`, 비용률 `NN.NNbp`, 배지 텍스트 `추정`/`배분`, 요약 testid `pnl-summary-net`·`pnl-summary-cost`(수수료+세금)·`pnl-summary-slippage`(`N건`)
- OrderMonitor: testid `order-monitor-net-pnl`(`/api/costs/today` total 또는 strategy= 결과) + `추정` 배지
- BalanceTable: 머리 `예상 매도비용`·`순 평가손익`, testid `sell-cost-<ticker>`(+`추정`)·`net-pl-<ticker>`, 비율 없으면 `—`
- TradeHistoryGrid: 머리 `순손익`, SELL 행 `net_profit_loss`, estimated 면 `추정`
- Strategies: `te-realized-<id>` = `realized_net_sum_krw`(없으면 `realized_sum_krw`)
- DailyReportTab: 실현손익 라벨에 `세전`, 숫자 그대로
- MSW 기본 목: `/api/history/pnl`·`/api/performance/{daily,summary}`(daily 는 배열)·`/api/costs/{today,daily}` 실제 키. e2e `api-mocks.ts` 에 `/api/costs/today`

## Green 이 함께 할 일 (이 Red 밖)
- `tests/unit/ast/test_cycle287_ast_scope.py` `_SRC_TREE_FILES` +1(`engine/cost_overlay.py`) · `_SRC_TREE_DIGEST` 재계산
- `frontend/src/types/` 새 칸 optional

## 실행 결과 (Red, 2026-10-08)
- 백엔드 새 5파일: 38 실패 / 19 통과 — 실패 사유 = `ModuleNotFoundError: src.engine.cost_overlay` · `AttributeError: allocate_rows`/`get_trades_by_status` · `KeyError: buy_trade_ids`/`te_pct_gross`/`daily_fee`/`fee`/`fee_sum`/`sell_cost_rate`/`cost_status` · `/api/costs/{today,daily}` 404 · TE net 판정 `assert 20 == 0`. 통과 19 = 범위 가드(G1~G3) · 비용 실패 시 기존 응답 유지(F1) · `get_completed_trades` 보존(B2)
- 프론트 새 9파일: 23 실패 / 4 통과(PN3·PN5·OM4·G5 — 세전 폴백·구 응답 회귀 가드 성격), 기존 테스트 전부 통과(전체 1073 통과 중 새 4 포함)

## 메인 세션 결정 (Red 모호점 1~9, 10-08)
1. `/api/history` SELL 행 `net_profit_loss` = 그 행 `profit_loss − fee − tax` (행 단위). 매수 수수료는 BUY 행에 남는다 — 그대로 채택.
2. 비용 조회 실패 = 기존 응답 200 유지 · 새 net 칸만 None · WARNING 로그 마커 `[cost_overlay_unavailable]` 1줄. `/api/costs/*` 자체는 기존대로 오류를 숨기지 않는다.
3. 잔고 = 백엔드는 `sell_cost_rate`(ETF 는 수수료율만)만 싣고 화면이 곱한다. **순 평가손익 = 평가손익 − 예상 매도비용 − 이미 낸 매수 수수료(정산 실측 있으면 실측, 없으면 추정)** — 매매손익 표의 페어 net 과 같은 정의로 맞춘다. 매수 수수료를 백엔드가 종목별로 `buy_fee_paid`(+status)로 함께 싣는다.
4. 추정 요율 창 기준일 = 서버 오늘(KST) — 채택.
5. 보유 중 페어 예상 매도비용 = 현재가 × 보유수량 × (수수료율 + 세율, ETF 는 수수료율만).
6. 추정 행의 `allocated` = false (배분은 정산 행이 있고 같은 날·종목 체결 2건 이상일 때만 true).
7. TE: `realized_sum_krw` 세전 유지 + `realized_net_sum_krw` 별도 · `*_gross` 는 te_pct·te_krw_avg·win_rate 3개 + `rr_gross`·`verdict_gross` 도 둔다(판정이 바뀐 이유를 화면에서 비교할 수 있게).
8. `/api/performance/daily` MSW 목 배열 정직화 — 채택.
9. localStorage 키 `autostock.costBasis` — 채택.

## 보완 결정 (통합 검증 결함 고정, 메인 세션 결정 10-08)

tester 합성 시나리오 x1~x10 이 찾은 결함을 회귀 테스트로 고정한다. 작성 = tdd-engineer, 2026-10-08.

### 테스트 파일

| 파일 | 덮는 것 |
|---|---|
| `tests/unit/routes/test_cycle411b_cost_overlay_route_fixes.py` | H1 · H2 · M1 · M2 · M3 · M4 · L2 (라우트) — 시계 freezegun **2026-10-07 12:00 KST** 고정 |
| `tests/unit/engine/test_cycle411b_cost_overlay_engine_fixes.py` | H2(세금 미배분) · M3(`etf_flags`) · M5(`win_gross`·`loss_gross`) |
| `tests/unit/db/test_cycle411b_partial_sell_ids.py` | L2 `partial_sell_trade_ids` |
| `frontend/src/components/__tests__/{PerformanceCard,ProfitChart,OrderMonitor,BalanceTable,TradePnLGrid,TradeHistoryGrid}.cycle411b.test.tsx` · `costsTypes.cycle411b.test.ts` | M1 · M4 · M5 · M6 · L1 · L3 (화면) |
| `frontend/src/components/__tests__/TradePnLGrid.cost.cycle411.test.tsx` G2 | **기대값 1줄 갱신** `23.01bp` → `23.0bp` (L1 — 위 계약 「비용률 `NN.NNbp`」 를 대체) |

### 기대값

- **H1 세후 누적 = 개시 이래.** `/api/performance/daily` 행의 `net_cumulative_return_rate` 와 `/api/performance/summary` 의 `net_total_profit_rate` 는 창 첫 행부터 다시 쌓지 않는다 — 개시 이래 전 기간 `daily_performance` 로 net TWR 을 계산하거나, 창 직전까지의 누적을 이어 붙인다(둘 다 허용 — 테스트는 창 밖 비용이 없는 경우만 본다). 비용 0 이면 net 누적 = `cumulative_return_rate`(daily 1e-9 · summary 는 기존 4자리 반올림이라 1e-4). 창 밖 행은 라우트 모듈 속성 `src.routes.performance.get_performance(days=…)` 로 더 길게 읽는다(테스트 가짜는 `days` 를 존중한다).
- **H2 배분 모집단.** 배분은 항상 **그 날짜 범위 전체 COMPLETED+PARTIAL 체결**(`trade_cost_db.get_trades_by_status`)로 한 뒤 id·전략·페이지로 거른다 — `/api/history`(페이지·`strategy=`) · `/api/performance/daily?strategy=` · `/api/costs/today?strategy=`. `/api/history` 의 CANCELLED·PENDING 행은 `fee`·`tax`·`net_profit_loss`·`cost_status` 를 싣지 않거나 None, 다른 행 몫도 그대로.
  - 정산 행 매도 체결금액 합이 0 인데 `tl_tax > 0` 이면 세금을 매수 행에 몰지 않는다 — 그 세금은 미배분(체결 행 `tax` = 0), WARNING 1줄 `[cost_overlay_tax_unallocated] …`(공백 포함 prefix). 처리 위치 = `cost_overlay.trade_costs` — `trade_cost.attribute`/`allocate_rows(key="strategy")` 결과는 그대로(트랙 C 요약 행위 보존, H2c).
- **M1 잔고.** `/api/balance` 보유 종목마다 `buy_fee_paid`(float) + `buy_fee_status`(`settled`|`estimated`|`mixed`). 엔진 페어(`src.db.trade_history.get_trade_pairs` **모듈 속성 경유**)의 open 페어 `buy_trade_ids` 체결 행 비용(정산 → 없으면 추정)을 더하고, 페어가 없는 보유(수동 매수)는 `purchase_amount × 추정 수수료율`, `estimated`. 분할 매도 뒤면 남은 수량 비율(L2 와 같은 식). 화면 순 평가손익 = round(평가손익 − round(평가금액 × `sell_cost_rate`) − `buy_fee_paid`) — `buy_fee_paid` 없으면 기존 식.
- **M2 추정 요율 창.** `estimate_rates` 입력 = **서버 오늘(KST, `today_kst()`) 기준 `[today − 30일, today]`** 정산 행 — 모든 라우트 공통(`/api/costs/{today,daily}` · `/api/history` · `/api/history/pnl` · `/api/performance/daily`·`summary` · `/api/strategies/te` · `/api/balance`). 화면 날짜 범위 행은 정산 대사(배분)에만 쓴다. 표본 없으면 기본값.
- **M3 ETF 판정.** `trade_costs(..., etf_flags: Mapping[str, bool] | None = None)` 신설 — 판정이 있는 종목은 그 값만 본다(이름 키워드보다 우선), 없으면 기존(`etf_tickers` → 이름 폴백). 라우트는 `src.db.stock_master.get(ticker)` **모듈 속성 경유**로 `is_etf_like(basics.raw, name)` 를 계산해 넘긴다(open 페어 예상 매도세도 같은 판정). `BNK금융지주`(`scty_grp_id_cd=ST`) 매도세 > 0 · `KIWOOM 200`(`EF`) 0.
- **M4 「모름」 ≠ 0.** 비용 조회 실패 시 `/api/history/pnl` summary 의 `realized_net_total_krw`·`realized_net_rate_pct`·`fee_sum`·`tax_sum` = None. 페어 `slippage_won` = 그 페어 체결 행 중 `order_price` 가 하나도 없으면 None(있으면 덮인 행만 합산). 화면: `pnl-summary-cost`·`pnl-summary-net` 은 null 이면 `—`(`0원` 금지) · ProfitChart 는 net 칸이 null 이어도 세전 시리즈로 폴백하고 제목에 `세후` 를 달지 않는다(`세전`).
- **M5 세전 승률.** `compute_te_rr` → `win_gross`·`loss_gross`(int, 빈 지표 0). PerformanceCard 세전 모드 = `승률 {win_rate_gross}% (승{win_gross}/패{loss_gross})`, 없으면 기존 값.
- **M6 OrderMonitor.** `/api/costs/today` 는 세전 실현손익(`/api/trading/status`, 5초)과 같은 주기로 다시 읽는다(`refetchInterval` 등).
- **L1 표기.** 원 단위 = 정수 원(반올림) + `원` — TradePnLGrid 수수료·세금·슬리피지·`pnl-summary-cost` · TradeHistoryGrid 순손익 · OrderMonitor 순손익 · BalanceTable 순 평가손익. 비용률 = 소수 1자리 `22.8bp`.
- **L2 분할 매도.** DB `get_trade_pairs` 의 모든 페어에 `partial_sell_trade_ids`(open = 그 사이클 안에서 이미 판 SELL 행 id 시간순, closed = `[]`). open 페어 `fee` = 매수 수수료 × (남은 수량 ÷ `buy_trade_ids` 매수 수량 합) + 남은 수량 예상 매도수수료, `tax` = 남은 수량 예상 매도세. 판 몫은 새 칸 `partial_fee`(매수 수수료 × 판 비율 + 부분 매도 수수료) · `partial_tax`(부분 매도세). 총합 보존 = 낸 비용 합 = 정산 행 합.
- **L3.** `frontend/src/types/costs.ts::CostDailyDay.cost_status: CostStatus | null`.

### 보고만 (테스트 아님)
- `frontend/package-lock.json` 의 이번 사이클 무관 변동(cd201f52 +23줄)은 main 버전으로 되돌릴 대상.

### 실행 결과 (보완 Red, 2026-10-08)
- 백엔드 새 3파일: 27 실패 / 2 통과 — 통과 2 = H2b2(매도 있는 날 세금은 매도 행)·H2c(`attribute` 행위 보존) 가드 성격. 실패 사유는 각 테스트가 겨냥한 결함(창 재누적 · 페이지/필터/취소 행 배분 · 화면 범위 요율 · 이름 폴백 ETF · `0.0 is None` · `KeyError: buy_fee_paid`/`win_gross`/`partial_sell_trade_ids` · `TypeError: etf_flags` · 경고 0건)
- 프론트 새 7파일: 9 실패 / 3 통과(PB1·PB3·BB2 — 기존 행위 가드) + 갱신한 G2 1 실패. 전체 1108 중 10 실패 · 1098 통과(기존 테스트 무손상)
