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
- `get_trade_pairs` 페어에 `buy_trade_ids`·`sell_trade_ids`(string/UUID — `trade_history.id`, 시간순, id 없는 행은 목록에서만 빠짐, open 은 `sell_trade_ids=[]`)
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

## 2차 보완 결정 (2차 통합 검증 결함 고정, 메인 세션 결정 10-08)

2차 통합 검증 판정(보완 필요)의 「배포 전에 고칠 것」 B1~B4 와 함께 처리하기로 한 F1~F14 를 회귀 테스트로 고정한다. 작성 = tdd-engineer, 2026-10-08.

### 테스트 파일

| 파일 | 덮는 것 |
|---|---|
| `tests/unit/routes/test_cycle411c_cost_overlay_route_fixes2.py` | B1 · B2 · B4 · F1 · F2 · F3 · F4 · F6 · F8 · F11 (라우트) — 시계 freezegun **2026-10-07 12:00 KST**, DB 경계 호출 `(start, end)` 기록 |
| `tests/unit/engine/test_cycle411c_cost_overlay_engine_fixes2.py` | B4(`compute_te_rr`) · F1(어댑터·DB 함수) · F5 · F6 · F8(하루 캐시) · 메모 초기화 훅 |
| `tests/unit/routes/test_cycle411c_doc_present_tense.py` | F14 · B2/B4 문구(`src/routes/CLAUDE.md`) |
| `frontend/src/components/__tests__/{PerformanceCard,BalanceTable,OrderMonitor}.cycle411c.test.tsx` | B3 · F3 · F7 · F10 |
| `frontend/src/pages/__tests__/StrategiesTeRr.cycle411c.test.tsx` | F9 · B4(화면) |
| `frontend/src/components/__tests__/costTypes.cycle411c.test.ts` | F12 |
| `frontend/src/components/__tests__/handlers.honesty.cycle411c.test.ts` | F13 |
| `tests/conftest.py::_reset_cost_overlay_memo` (autouse, 이 Red 가 추가) | 매 테스트 전·후 `cost_overlay._reset_cache_for_tests()` — `src.engine.cost_overlay` 가 이미 import 됐을 때만, 함수가 없으면 아무것도 안 한다 |
| `tests/unit/routes/test_cycle411b_cost_overlay_route_fixes.py` 픽스처 | `stock_master.get_etf_group_codes` 가짜 1개 추가(`raising=False`, 같은 `stock_raw` 원천) — F1 구현 뒤에도 M3 테스트가 같은 판정을 보게 한다. 기대값 무변경 |

### 기대값

- **B1 현재가 모름.** 보유 중(open) 페어인데 `profit_loss is None`(21:30 이후·재기동 직후·휴장일 종일)이면 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp` = **None**. 이미 낸 `partial_fee`·`partial_tax` 는 그대로 숫자. `cost_status`·`allocated`·`slippage_won` 는 기존대로.
- **B2 summary net = None.** `/api/performance/summary` 의 `net_total_profit_rate`·`net_avg_daily_profit_rate` 초기값 None — 개시 이래 net 행이 None 이 아닐 때만 채운다(세전 값을 「세후」 칸에 담지 않는다). 개시 이래 재조회(`src.routes.performance.get_performance(days>30)`)도 `_net_overlay_rows` 와 같은 try 안 — 실패 = summary·daily 모두 **200**, summary net 두 칸 None, daily net 6칸 None, WARNING `[cost_overlay_unavailable]`. 기록 없음(`records == []`) 응답의 net 0 은 그대로. `src/routes/CLAUDE.md` summary 행에서 「비용 조회 실패 = gross 값으로 폴백」 문구를 걷는다.
- **B3 화면 null.** `PerformanceCard` 는 `!= null` 로 거른다. summary net 이 null 이면 세전 값을 보이고 **그 카드**(`performance-metric-*` 의 부모 카드)에 「세전」. TE `realized_net_sum_krw` 가 null 이면 `realized-pnl-<id>` 에 세전 `realized_sum_krw`(「0원」 금지) + `realized-row-<id>` 에 「세전」. 세후 칸이 있으면 「세전」 을 달지 않는다(가드 PC3). 타입은 F12.
- **B4 TE 비용 모름.** `compute_te_rr(pairs, *, now, window_days=90, strategy_id="", costs_available: bool = True)` — False 면 `realized_net_sum_krw`·`fee_sum`·`tax_sum` = **None**(`TeRrMetrics` 세 칸 타입 `float | None`), 판정은 페어 값 그대로(net 칸이 없으니 세전 — `te_pct == te_pct_gross`). 기본값 True 는 기존 q4 폴백 그대로. `/api/strategies/te` 는 `overlay_pairs` 를 **별도 try** 로 감싸고 반환 None 또는 예외면 `costs_available=False` 로 계산한다(예외가 그 전략 지표를 통째로 비우지 않는다 — n·세전 값 유지). **실패 결과는 캐시하지 않는다**(또는 60초 이하 — 테스트는 61초 뒤 재조회로 잰다). 화면 `te-realized-<id>`: 세후 값이면 「세후」, `realized_net_sum_krw` 가 null/없음이면 `realized_sum_krw` + 「세전」. `src/routes/CLAUDE.md` TE 행의 「실패해도 pairs 는 gross 그대로」 문구를 걷는다.
- **F1 ETF 판정 일괄 조회.** 새 DB 함수 `src.db.stock_master.get_etf_group_codes(tickers: list[str]) -> dict[str, str | None]` — `pg.fetch` **1회**, SQL = `SELECT ticker, raw->>'scty_grp_id_cd' AS scty_grp_id_cd FROM stock_master WHERE ticker = ANY($1::text[])`(`SELECT *` 금지), 요청 종목 **전부**를 키로(DB 미존재 = None), 빈 입력은 쿼리 생략 `{}`. `cost_overlay.stock_master_etf_flags(trades)` = 고유 종목으로 그 함수 **1회**(`stock_master.get` 호출 0) → 코드가 있는 종목만 `is_etf_like({"scty_grp_id_cd": code}, name)`, 코드 None·공백 종목은 결과에서 뺀다(이름 폴백이 받는다). 조회 예외 = `{}` + DEBUG(전부 이름 폴백 — 기존 graceful 그대로). 잔고 라우트의 종목별 `stock_master_get`(NXT 칸 join)은 이번 범위 밖.
- **F2 잔고 여러 날 매수.** `buy_fee_paid` = open 페어 `buy_trade_ids` **전체**(날짜 무관)의 매수 체결 비용 합 × (남은 수량 ÷ 그 매수 체결 수량 합). 조회 범위는 페어 `buy_date` 부터 오늘까지(또는 같은 결과를 내는 범위). 상태 = 그 체결들 `day_cost_status`.
- **F3 잔고 비용 모름.** 비용 DB 조회 실패(정산·체결 조회 예외)로 open 페어 매수 수수료를 모르면 `buy_fee_paid` = **None**, `buy_fee_status` = **None**(0.0·"estimated" 금지). `sell_cost_rate` 는 기존대로 기본 요율 fail-open. 화면: `buy_fee_paid === null` → `net-pl-<ticker>` 「—」(`?? 0` 금지). 칸 자체가 없는 구 응답은 기존 식(BB2).
- **F4.** `/api/history/pnl` 비용 조회 실패(`overlay_pairs` → None) 시 summary `slippage_n` = **None**(0 아님). 성공인데 페어가 없으면(`{}`) 0.
- **F5 「매도 없음」 = 체결 집합.** `cost_overlay.trade_costs` 는 (trad_dt, pdno) 마다 **그 키의 체결 집합**에 SELL 행(금액 > 0)이 없고 정산 `tl_tax > 0` 이면 — 정산 행 `sll_amt` 와 무관하게 — 세금을 매수 행에 몰지 않고(체결 행 `tax` = 0) `[cost_overlay_tax_unallocated] ` WARNING. 그 키의 체결이 **하나도 없는** 정산 행은 `[cost_overlay_unmatched_cost] trad_dt=YYYY-MM-DD pdno=XXXXXX …` WARNING(반환 dict 에는 아무것도 더하지 않는다 — 귀속할 체결이 없다). 정상 행(짝 있음·매도 체결 있음)은 두 경고 모두 없다.
- **F6 경고 1회.** 위 두 경고는 프로세스 메모리 dedupe — 키 (trad_dt, pdno), **프로세스 수명 동안 1회**(메인 세션 결정 10-08: 3차 검증이 지적한 「오늘 날짜를 키에 넣으면 과거의 짝 없는 정산 행을 매일 다시 경고」 문제를 없애려고 날짜 재발화를 뺐다. 새 날짜의 정산 행은 키가 달라 그대로 경고된다). 같은 요청 2회 = 1줄. `cost_overlay._reset_cache_for_tests()` 가 dedupe 를 비운다.
- **F7 OrderMonitor.** `/api/costs/today` 쿼리 `retry: 0`(`refetchInterval: 5000` 유지). `isError` 면 `order-monitor-net-pnl` 에 「—」(마지막 성공값을 남기지 않는다) + 오류 표시 `order-monitor-net-pnl-error`(문구 「조회 실패」, 「실현 손익」 을 담지 않는다 — OM4 `getByText(/실현 손익/)` 충돌 방지). 첫 조회부터 실패해도 같은 자리에 그린다.
- **F8 요율 하루 캐시·중복 조회.** `cost_overlay.today_window_rates()` 결과를 KST 날짜 단위 메모리 캐시 — 같은 날 두 번째 호출은 DB 를 읽지 않고, 다음 날 다시 읽는다. 실패(예외)는 캐시하지 않는다. `_reset_cache_for_tests()` 가 비운다. 한 요청 안에서 같은 `(start, end)` 를 `get_daily_range`·`get_trades_by_status` 로 두 번 읽지 않는다(잔고: 같은 날 산 보유 여러 종목). 대사(reconcile) 뒤 캐시 무효화는 선택(테스트 없음).
- **F9.** `te-realized-<id>` 는 세후 값에 「세후」 라벨(위 B4 화면과 같은 칸).
- **F10.** `BalanceTable` 「예상 매도비용」·「순 평가손익」 머리칸(`columnheader`)과 `sell-cost-<ticker>`·`net-pl-<ticker>` 칸 class 에 `whitespace-nowrap`. `OrderMonitor` 제목 「주문처리 현황」 class 에 `whitespace-nowrap`, 머리줄(제목의 부모) 텍스트에 「추정」 은 **한 번**(라벨 「(추정)」 과 배지 「추정」 중복 금지 — 배지는 `order-monitor-net-pnl` 안에 남는다, OM1).
- **F11 배분 배지 = 페어 밖과 나눴을 때만 (결정 6 갱신).** 페어 `allocated` = 그 페어 체결 행(`buy_trade_ids` + `sell_trade_ids` + `partial_sell_trade_ids`)이 받은 정산 행 중 **하나라도 이 페어 밖의 체결 행에도 나뉘었을 때만** true. 같은 날 사고 판 단일 페어(정산 1행을 자기 매수·매도 행만 나눠 받음)는 false. 추정 행·open 페어는 기존대로 false. 체결 행 단위 `trade_costs(...)[id]["allocated"]` 의미는 그대로(정산 1행을 2개 이상 체결 행이 나눔). → 위 「메인 세션 결정」 6 을 이 문장이 대체한다.
- **F12 타입.** `frontend/src/types/trading.ts` — `PerformanceSummary.net_total_profit_rate`·`net_avg_daily_profit_rate` · `DailyPerformance` 비용·세후 6칸(`cost_status` 포함) · `TradeRecord.fee`·`tax`·`net_profit_loss`·`cost_status` · `TradePair.cost_status` · `TradePnLSummary.slippage_n` 에 `| null`. `TradePair` 에 `partial_fee?: number | null`·`partial_tax?: number | null`·`partial_sell_trade_ids?: string[]`(화면 미사용, 타입만). `frontend/src/types/strategy.ts` `TeRrMetrics.realized_net_sum_krw`·`fee_sum`·`tax_sum` 에 `| null`.
  - (cycle411d, 3차 검증 후 LOW) `buy_trade_ids`·`sell_trade_ids`·`partial_sell_trade_ids` 는 `string[]` 이다 — `trade_history.id` 가 `UUID`(`supabase/migrations/001_init.sql`)라 `number[]` 는 타입 오기였다.
- **F13 MSW 기본 목 산수.** `/api/history/pnl`: 페어 `net_profit_loss = profit_loss − fee − tax`, `cost_bp` 정의식 ±0.05, summary 합계 = closed 페어 합(`realized_total_krw`·`realized_net_total_krw`·`fee_sum`·`tax_sum`·`closed_count`), 그 핸들러에 `as never` 없음. `/api/performance/daily`: `daily_net_pnl = daily_realized_pnl − daily_fee − daily_tax`, 세후 ≤ 세전, 첫 행 「창 이전 누적」 `(1+누적)/(1+당일)` 이 세전·세후 같음(1e-7). `/api/balance`: `{holdings: [...], summary: {AccountSummary 7키}}`(보유가 있으면 실비용 4칸 포함). `/api/history`: 행에 `fee`·`cost_status`·`order_price`(SELL 이면 `tax`·`net_profit_loss`).
- **F14 정본 현재형.** `README.md`·`src/routes/CLAUDE.md` — 굵은 꼬리표 `**cycle411…**`·`cycle411 보완` 금지, 실비용 표 행에 「보완」·문장 끝 「추가」(`… 추가.`·`… 추가 —`) 금지. 값의 출처 괄호 `(cycle411, 사용자 결정 10-08 …)` 는 허용. 걷어낸 경위는 `docs/history/README.history.md`(새 파일)·`docs/history/src-routes-CLAUDE.history.md` 에 append(둘 다 `cycle411` 언급).

### 실행 결과 (2차 보완 Red, 2026-10-08)
- 백엔드 새 3파일: **36 실패 / 5 통과** — 라우트 16 실패 / 1 통과(F11b 가드) · 엔진 10 실패 / 4 통과(B4b·F5c·F6b·F8b 가드 — 기본값 폴백 보존·정상 행 무경고·하루 넘으면 다시 경고·실패 미캐시) · 문서 10 실패. 실패 사유 = `56.0 is None`(B1) · `0.33 is None`·500(B2) · `14000.0 is None`·캐시된 세전·`n 0 == 20`(B4) · `stock_master.get` 직렬 호출·`AttributeError: get_etf_group_codes`(F1) · `50.0 == 55`(F2) · `0.0 is None`(F3) · `0 is None`(F4) · 매수 행 세금 634.375·경고 0건(F5) · 경고 2건(F6) · 창 조회 2회·같은 범위 4회(F8) · `TypeError: costs_available`(B4) · `True is False`(F11) · `_reset_cache_for_tests` 없음 · 정본 꼬리표·history 부재(F14)
- 전체 백엔드: 42 실패 / 15,764 통과 — 새 36 + 인덱스 신선도 1(재생성 후 통과) + 알려진 환경 5(프론트 인덱스 3 — 루트 `node_modules` 없음 · parquet 2). 기존 테스트 무손상
- 프론트 새 6파일: **21 실패 / 2 통과**(PC3·MH9 가드). 전체 1,131 중 21 실패 · 1,110 통과(기존 1,108 무손상). `tsc -b`·eslint 깨끗
- 영향 인덱스 재생성: 백엔드 1,289 테스트 · 프론트 133(루트 `node_modules` 임시 링크 → 삭제)
