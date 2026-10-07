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
