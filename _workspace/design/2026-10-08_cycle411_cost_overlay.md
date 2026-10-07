# cycle411 — 실적 화면에 실비용(수수료·세금) 합치기 · 명세

사용자 요청(10-08): 「실적이 표시되는 모든 화면의 금액들에 합치기. 매매손익에는 실적 실비용 표칸에서 언급한 컬럼들을 추가 반영.」

## 사용자 결정 (10-08)
- Q1 정산 전 구간 = **실측 요율 추정 + 「추정」 배지** (최근 30달력일 `trade_cost_daily` 로 수수료율 = Σfee÷Σ(buy_amt+sll_amt), 세율 = Σtl_tax÷Σsll_amt, 표본 없으면 0.142%/0.199% 기본값, ETF·ETN(`etf_like.is_etf_like` 또는 stock_master) 매도세 0). 정산값이 들어오면 자동으로 실측으로 바뀐다.
- Q2 **판정도 순손익 기준** — 전략 TE·승률·손익비(`/api/strategies/te` · `compute_te_rr`) 를 net(비용 차감) 기준으로 계산. 세전 값은 별도 칸(`*_gross`)으로 남긴다.
- Q3 **세후 기본 + 세전 토글** — 모든 실적 금액 기본 표시 = 세후(net), 화면 토글로 세전(gross). 저장 스냅샷인 로그 일일리포트(`DailyReportTab`)는 숫자 그대로 두고 「세전」 라벨만.
- Q4 **슬리피지 칸 지금 바로** — 덮인 건수 n 과 함께(`order_price` 있는 행만).

## 설계 (1안 — 읽을 때 합치기, 설계 원문 = 이 파일 아래 「설계 근거」)
- 🔴 **8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`·`src/api/order.py`·`src/realtime/**`·`src/auth/**`)·`scheduler.py` 무접촉. DB 저장값·마이그레이션 무변경.** `trade_history.profit_loss` 의미(세전) 불변.
- 새 leaf `src/engine/cost_overlay.py`: 순수 함수(배분·추정·net TWR 재누적) + async 어댑터.
- `src/engine/trade_cost.py`: `allocate_rows(cost_rows, trades, key=...)` 일반화, 기존 `attribute` 는 이것을 key=strategy 로 호출(행위 보존 — `test_trackc_trade_cost_calc.py` 무수정 통과).
- `src/db/trade_cost.py`: 상태 목록(COMPLETED+PARTIAL) 받는 조회 추가(가산형).
- `src/db/trade_history.py::get_trade_pairs`: 체결 행 id 병행 리스트 `buy_trade_ids`/`sell_trade_ids` 추가(버퍼 튜플 arity 3 유지, cycle276 `order_nos` 방식).
- 라우트 — 기존 칸 유지, **새 칸만 덧붙임**:
  - `/api/performance/daily`: `daily_fee`·`daily_tax`·`daily_net_pnl`·`net_daily_profit_rate`·`net_cumulative_return_rate`·`cost_status`(settled|estimated|mixed)
  - `/api/performance/summary`: `net_total_profit_rate`·`net_avg_daily_profit_rate`
  - `/api/history`: SELL 행 `fee`·`tax`·`net_profit_loss`, BUY 행 `fee` (+ `cost_status`)
  - `/api/history/pnl`: 페어마다 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp`·`slippage_won`·`cost_status`·`allocated`; summary 에 `fee_sum`·`tax_sum`·`realized_net_total_krw`·`realized_net_rate_pct`·`slippage_n`
  - `/api/strategies/te`: 판정 지표를 net 기준으로, 세전 값은 `*_gross` 칸, `realized_net_sum_krw`·`fee_sum`·`tax_sum`
  - 새 `GET /api/costs/today?strategy=` (당일 체결 × 추정 요율 — OrderMonitor 용, scheduler 무접촉 경로)
  - 새 `GET /api/costs/daily?from=&to=` (날짜별 비용·슬리피지 추이)
  - `/api/balance`(또는 프론트 계산): 보유 종목 「예상 매도비용(추정)」·「순 평가손익」
- 거래 단위 귀속: 같은 날·종목 `trade_cost_daily` 1행을 그 날 그 종목 체결 행에 — fee 는 체결금액 비율, tax 는 매도 행만 매도금액 비율. 페어 비용 = 매수 행 fee + 매도 행 fee·tax. 한 날 한 종목 체결 행 2개 이상 = `allocated=true`(「배분」 배지). 보유 중 페어 = 낸 매수 수수료 + 예상 매도비용(추정).
- 비용률(bp) = (fee+tax) ÷ ((매수금액+매도금액)/2) × 10⁴.
- 프론트: TradePnLGrid(수수료·세금·순손익·순손익율·비용률·슬리피지 칸 + 배지 + 요약 바), PerformanceCard(net 기본·세전 토글), ProfitChart(세후/세전 토글), OrderMonitor(오늘 실현 net 추정), BalanceTable(예상 매도비용·순 평가손익), Strategies 「3개월 실현」(net), TradeHistoryGrid(SELL 행 net), DailyReportTab(「세전」 라벨). 세전/세후 토글 상태는 화면 공통(localStorage 기억, try/catch). `frontend/src/types/` 타입은 새 칸 optional.
- 화면 영향 화면 목록·출처표 = 아래 「설계 근거」 §1.

## 테스트
- 백엔드: cost_overlay 순수 함수(3주문·2전략 배분 합 = KIS 1원 이내, 미대사 추정, ETF 세금 0, net TWR 재누적), 라우트 가산 칸·기존 칸 불변 회귀, get_trade_pairs id 병행 리스트, attribute 행위 보존, TE net 판정.
- 프론트: MSW `src/test/handlers.ts` 새 칸·엔드포인트(실제 응답 키 그대로), 각 컴포넌트 새 칸·배지·토글.
- 핀: `tests/unit/ast/test_cycle287_ast_scope.py` `_SRC_TREE_FILES`(+새 파일 수)·`_SRC_TREE_DIGEST`(`_tree_digest()` 해시만) 재계산. 8영역 sha 불변.
- 운영 선행: `POST /api/costs/reconcile` 로 전체 기간 백필(배포 뒤, 366일 단위).

## 배포
backend 재시작 필요 → 장외 창(15:30~16:00 · 21:35~07:45 · 주말·공휴일). 🔴 10-13(화) 07:00~07:45 주계좌 전환과 겹치지 않게 — 10-09(목·공휴일) 또는 10-12(월) 21:35 이후 권장. 🔴 그 전까지 EC2 `.env` 는 현 계좌(끝 1589)라 재생성해도 안전.
