# CLAUDE.md — src/routes/ (FastAPI 라우트)

> 이력: [`docs/history/src-routes-CLAUDE.history.md`](../../docs/history/src-routes-CLAUDE.history.md)

프론트엔드에 데이터를 제공하는 REST API 엔드포인트.

## 인증 — deny-by-default

**이 표의 모든 라우트는 인증 대상이다.** `src/middleware/api_auth.py::ApiAuthMiddleware` 가 **최외곽**에서 `/health` 를 뺀
**전 경로**(`/docs`·`/redoc`·`/openapi.json` 포함)에 `X-API-Key` 를 요구한다. 새 라우트는 접두사와 무관하게 자동 보호된다.
예외 추가 = `EXEMPT_PATHS` 수정 = 계약 변경이다. 금기의 정본 = 루트 `CLAUDE.md` 「핵심 안전 규칙」 의 API 인증 항목.

* **응답** = 401 `{"success": false, "data": null, "message": "unauthorized"}`, 리포터 스코프 위반(`reporter_scope`)만 403
  `"forbidden"`. 사유는 로그에만 남는다(`[api_auth_reject] reason=…`, 사유당 ≤5행/일).
* **상태변경(POST/PUT/PATCH/DELETE)** 은 Origin 검사도 통과해야 한다 — `Origin` 부재(curl·ssh 비상 경로) · Host 일치 ·
  `API_ALLOWED_ORIGINS` 등재 = 허용, 그 외 401 `reason=cross_origin`. CSRF 방어는 이쪽이다(CORS 는 simple request 실행을 못 막는다).
* **포트별 인증** — `:80`(nginx) = Basic Auth(X-API-Key 는 nginx 가 주입) / EC2 내부 `:8000` 직결 = `-H "X-API-Key: …"`
  (비상 매도 절차서 `_workspace/monday_0831_guide.md`).
* 🔴 **인바운드 WebSocket 라우트(`@app.websocket`)를 추가하지 않는다** — 미들웨어가 `http` 아닌 scope 를 그냥 통과시켜 인증 밖이다.
  가드 = `tests/unit/middleware/test_cycle249_websocket_scope_guard.py`.
* **인증은 실수 방어가 아니다** — 범위 안의 위험한 값(예: 손절 −15%)은 params 422 검증(cycle278)도 통과하고, 단일 공유 키라
  누가 바꿨는지 남지 않는다. 보완 = 화면의 2단계 확인(identity 18키 — 아래 「전략 설정 쓰기 경로」 identity 항목)과 운영 기록.

## 엔드포인트 목록

숫자 열 공통 — NUMERIC 은 `Decimal` 이고 pydantic v2 는 그것을 JSON **문자열**로 내보내 프론트 숫자 포맷이 깨진다(아래
「`float` 사영」 의 이유). 깨지는 모양은 둘이다 — 조용히(`toLocaleString` 천단위 구분 상실 · 그리드 `-`) 또는 `toFixed` 의
`TypeError`(렌더 붕괴).

`/api/llm-evaluations/*` · `/api/stock-master/{ticker}/daily` 는 DB 예외를 `except Exception: rows=[]` 로 빈 결과로 바꾸지
않는다 — 「없음」(404·빈 맵) 과 「조회 실패」(500) 가 구별되지 않는다(fail-silent 금지). graceful 로 명시한 관찰 라우트
(`/api/balance` 청산선 · `/api/balance/exit-lines` · `/api/strategies/monitor` · `/api/portfolio/risk` · `/api/log-reports/bundle` · `/api/strategy-funnel` · `/api/market-regime/current`
등)는 이 금기 밖이다.

응답 모양의 정본 = 행에 적은 백엔드 모델·생산 함수다. `frontend/src/types/*` 는 소비자 사본이라 어긋나면 백엔드가 맞다.

| Method | URL | 파일 | 설명 |
|--------|-----|------|------|
| POST | `/api/trading/start` | trading.py | 자동매매 시작. `scheduler.start()` 를 태스크로 띄우고 기다리지 않는다(실행 중이면 `success=false`). ⚠️ **기동 거부 창 `20:00~21:30`**(`scheduler.TIME_SESSION_START_CUTOFF` ~ `TIME_SETTLEMENT`)에서는 `start()` 가 거부해 무동작이다(로그 `장 종료 후 시작 시도 — 거부됨`) |
| POST | `/api/trading/stop` | trading.py | 자동매매 정지(실행 중이 아니면 `success=false`) |
| POST | `/api/trading/restart` | trading.py | 재기동(`stop()` → 1초 → `start()`). ⚠️ **기동 거부 창 `20:00~21:30` 에서는 `stop()` 만 성사돼 정지 상태로 남는다** — `[account_risk_watch_loop_died]` 복구도 그 창에서는 21:30 이후나 다음 영업일 07:45 자동 기동을 기다린다. 그 창의 재기동·크래시는 그날 저녁 블록(20:30 일봉 적재 · `_settle()` · 21:30 일일 로그 분석 · `purge_old_logs`)을 잃는다. **복구 3종** ① `POST /api/stock-master/daily/refresh` — 주말 또는 평일 20:00 이후에만 오늘 봉 저장(커트오프 `time(20,0)` 은 `force=True` 로도 못 넘는다) ② `POST /api/performance/recompute`(멱등) ③ `POST /api/log-reports/run` — **오늘** 날짜만. 21:30 정산·재시작 뒤엔 `api_metrics`/`strategy_funnel` 이 0 이라 복구되지 않고, 1차 스냅샷만 있는 행은 가드가 막지 않아(`force` 무관) 그날 metrics 의 유일한 생존본인 20:05 행을 덮는다. 일봉 결손의 자동 보정 = `src/engine/CLAUDE.md` 「scheduler.py」 절 `TIME_SESSION_START_CUTOFF` 행 |
| POST | `/api/trading/manual-sell` | trading.py | 수동 매도(시장가). 🔴 컷 면제 · 보유보다 적은 수량 허용 · `_selling` 발사 앞 설정 — 계약·알려진 한계 = 아래 「수동 매도」 절 |
| GET | `/api/trading/status` | trading.py | 현재 상태. `?include=system,holdings,orders,scan,strategies` csv 로 sub-section 만(미지정·`all` = 전체). `strategies[*].tradable_boards: list[str]`(DEFAULT_TRADABLE_BOARDS 또는 params.tradable_boards). 거래일지 워커가 `?include=system,holdings,strategies` 로 15초마다 읽는다(G0) — 워커가 쓰는 키 = `running` · `phase` · `strategies[sid].enabled` · `.params` · `.buy_signals[*].ticker/time/price`. 이 키를 바꾸면 워커 기록이 비거나 틀어진다 |
| GET | `/api/trading/positions` | trading.py | 보유 포지션 상세만(BalanceTable 전용) |
| GET | `/api/trading/orders` | trading.py | 주문 추적(pending_buys/fills/pending_cancels)만 |
| GET | `/api/balance` | balance.py | 잔고(예수금 + 보유종목, 0수량 제외). holding 마다 `stock_master.get(ticker)` join → `nxt_tradable`/`krx_halted`/`excg_dvsn_cd`(miss·예외 = None) + `sector`(`resolve_sector_name(…, basics_raw=basics.raw)` — 이미 읽은 raw 를 주입해 재조회 없음). `strategy_id` + 청산선 4필드(`stop_price`/`stop_source`/`target_price`/`target_source`, cycle339) = `engine/position_exit_lines.build_exit_line_map` 이 메모리에서 만든다(DB·KIS 왕복 0, registry 조회 실패 = graceful — 잔고 그대로, 전 종목 `—`). `buy_date`(최초 매입일, KST `YYYY-MM-DD`, cycle397) = 1순위 엔진 포지션(`engine/position_buy_date.resolve_engine_buy_dates`) · 2순위 DB `positions.buy_date`(`db/positions.get_buy_dates`) · 두 출처가 다르면 **더 이른 날짜**(`merge_buy_date`, 피라미딩 대비 「최초」 규약). 🔴 불확실하면 `None` — **숫자를 지어내지 않는다**(틀린 손절가는 없는 것보다 나쁘다. 매입일도 오늘 날짜로 채우지 않는다). `sell_cost_rate`(수수료율+세율, ETF/ETN 은 수수료율만 — 판정 = 이미 읽은 `basics.raw` 로 `is_etf_like`)·`cost_status="estimated"`(cycle411, 사용자 결정 10-08 §3 — `engine/cost_overlay.today_window_rates`, 서버 오늘 기준 30일 창. 표본이 없거나 요율 조회가 실패해도 기본 요율로 낸다 — 화면 참고용 추정이라 잔고를 막지 않는다. 화면이 평가금액에 곱한다) + `buy_fee_paid`/`buy_fee_status`(cycle411 — 엔진 open 페어(`db/trade_history.get_trade_pairs` 모듈 속성 경유)의 `buy_trade_ids` 체결 비용(정산→추정, **매수일~오늘 범위**, 남은 수량 비율)을 더한다. 「모름」 은 0 이 아니라 둘 다 `None` 이다 — 정산·체결 범위 조회 실패 · 조회는 됐는데 그 체결 id 를 못 찾음 · 그 종목 open 페어 중 하나라도 모름 · 매수 수수료 계산 전체의 예외. 페어 없는 보유(수동 매수 등, 페어 조회 실패 포함)는 매입금액 × 추정 수수료율·`estimated`, `buy_trade_ids`·`buy_date` 가 없는 페어는 `0.0`·`estimated`. 같은 `(start, end)` 범위는 한 요청 안에서 한 번만 읽는다) 상세 = `src/engine/CLAUDE.md` 의 `position_exit_lines.py`/`position_buy_date.py`/`cost_overlay.py` 항목 |
| GET | `/api/balance/buyable?ticker=&price=` | balance.py | 매수 가능 금액 |
| GET | `/api/balance/exit-lines` | balance.py | **보유 청산선 스냅샷**(G1, cycle412 — 사용자 결정 E1b). 읽는 곳 = 거래일지 워커(15초) · 대시보드 전략 패널·요약표(10초 — 화면의 실효 손절선 정본, cycle414). 손절선 계산 입력(`_entry_atr`·래치·무장 여부)은 엔진 메모리에만 있어 이 GET 이 워커의 유일한 창이다. `data` = `{running, as_of(KST +09:00), items}` · item = 전략마다 보유 종목마다 1건(같은 종목을 두 전략이 들고 있으면 2건) — `strategy_id`·`ticker`·`stop_price`·`stop_source`·`target_price`·`target_source`(= `engine/position_exit_lines.resolve_exit_lines([s], ticker)` 그대로)·`buy_price`·`quantity`·`high_since_buy`·`buy_date`(ISO)·`order_no`·`entry_atr`(`_entry_atr` → 없으면 kojiro `_position_atr` → 없으면 null)·`kk_armed`(donchian 만 bool, 그 밖 null)·`kk_arm_price`(donchian 미무장 = `ceil(E + kk_breakeven_r × (E − 손절선))`, 무장·그 밖 = null). KIS·DB 호출 0 · 핸들러 본문 `await` 0. **5초 캐시** — 직전 **성공** 응답 뒤 `_EXIT_LINES_CACHE_TTL_S`(5.0초) 안의 재호출은 같은 바이트(`as_of` 포함)를 준다(`json.dumps` 로 직렬화한 본문을 `Response` 로 그대로 낸다). 실패는 전부 HTTP 200 `success=false` 이고 로그는 `logger.debug` 뿐이다(매 회전 때리는 경로라 500 스택트레이스를 쌓지 않는다). 🔴 **read-only** — 전략 registry 를 바꾸지 않는다(변이 메서드·`setattr`·`check_*`·`on_*`·`_apply_budget_limit` 호출 금지 = AST 가드 `tests/unit/ast/test_cycle412_g1_purity.py`). 운영 Position·params 를 바꾸면 손절이 깨진다 |
| GET | `/api/history?page=&size=&ticker=&strategy=` | history.py | 거래 내역(페이징, `size` 1~100). 🔴 **`float` 사영 의무**(`get_trades` 의 `SELECT t.*` NUMERIC `price`·`profit_loss` — 빠지면 `TradeHistoryGrid` 가 그 열을 `-` 로 떨군다). 판정은 **값 타입으로만**(`isinstance(v, Decimal)`) — 컬럼명을 박으면 다음 `ALTER TABLE` 에서 재발한다. 가드 `tests/contract/test_routes_history.py::test_history_numeric_fields_are_json_numbers`(스텁이 **`Decimal`** 이어야 이 경로를 탄다). 체결 행마다 `fee`·`cost_status`(BUY·SELL 공통) + SELL 행 `tax`·`net_profit_loss`(= 그 행 `profit_loss − fee − tax`, cycle411). 비용 조회나 그 뒤 계산(`trade_costs`)이 실패하면 새 칸을 싣지 않고 기존 응답 200 을 그대로 낸다(`[cost_overlay_unavailable]`). 배분(`cost_overlay.trade_costs`)은 이 페이지의 체결 행이 아니라 그 날짜 범위의 **전체** COMPLETED+PARTIAL 체결(`trade_cost_db.get_trades_by_status`)로 하고, 페이지·전략 필터(`?strategy=`)는 배분 **뒤**에 거른다(한 페이지만 보면 그 날 정산 1행 전부를 떠안는 결함을 막는다). 그 (날짜,종목) 체결 집합에 매도가 없는데 정산 행에 세금이 잡히면 매수 행에 몰지 않고 미배분(`[cost_overlay_tax_unallocated]`) · 짝 체결이 하나도 없는 정산 행은 `[cost_overlay_unmatched_cost]`(둘 다 WARNING, `(trad_dt, pdno)` 당 프로세스 수명 1회 — 짝이 아예 없으면 `unmatched_cost` 한 줄만, `tax_unallocated` 는 겹치지 않는다). CANCELLED·PENDING 행은 배분 대상이 아니라 `fee`/`cost_status` 가 없다(None) |
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | history.py | 매매손익 — 매수/매도 페어 1행(가중평균, `size` 1~200). 보유 중은 open 페어(미실현 = `ticker_prices` 현재가). 페어마다 `buy_order_nos`/`sell_order_nos`(리스트 — 매수 주문이 여럿일 수 있어 **단수 금지**) + `pair_key`(= `strategy:ticker:첫 매수 order_no`, 없으면 `None` = AI 자문 버튼 비활성) + `buy_trade_ids`/`sell_trade_ids`·`partial_sell_trade_ids`(cycle411 — 실비용 귀속용 체결 행 id 목록. `trade_history.id` 라 UUID 문자열, 정수 아님. `partial_sell_trade_ids` = open 페어에서 이미 판 SELL 행). `data.summary` = 슬라이스 전 closed 페어 집계(생산 `_build_pnl_summary` · TS 사본 `frontend/src/types/trading.ts` `TradePnLSummary` 12필드(기본 7 + 실비용 5) — `realized_rate_pct` 가중 round2 · `win_rate_pct` round1, 분모 0 이면 비율 0.0). 페어마다 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp`·`slippage_won`·`cost_status`(settled/estimated/mixed)·`allocated`(이 페어의 체결이 받은 정산 행이 **페어 밖** 체결에도 나뉘었을 때만 true, 같은 날 사고 판 단일 페어는 false) 를 `engine/cost_overlay.overlay_pairs` 로 덧붙인다. 거래 단위 귀속 = 수수료 매수+매도 전부·세금 매도행만. open 페어 = 낸 매수 수수료(정산/추정) × **남은 수량 비율** + 예상 매도비용(현재가 = `buy_price+profit_loss/buy_qty` 로 페어 안에서 역산) → `cost_status` 항상 `estimated`. 현재가를 모르면(`profit_loss=None`) `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp` 는 `None`(0 으로 치지 않는다, `partial_fee`·`partial_tax` 는 이미 낸 비용이라 그대로 유지). 분할 매도 뒤 판 몫은 `partial_fee`·`partial_tax` 로 따로 낸다(총합 보존). `slippage_won` = 그 페어 체결 행 중 `order_price` 가 하나도 없으면 `None`(있으면 덮인 행만 합산). summary 에 `fee_sum`·`tax_sum`·`realized_net_total_krw`·`realized_net_rate_pct`·`slippage_n`(closed 페어가 가리키는 체결 행 중 `order_price` 덮인 수) 를 함께 낸다. 비용을 모르면 이 다섯 칸은 `0` 이 아니라 `None` 이다(기존 칸은 그대로) — `overlay_pairs` 가 `None` 을 돌려줄 때와, 라우트가 감싼 `overlay_pairs` 호출이 예외를 낼 때 둘 다(`[cost_overlay_unavailable]`, 응답 200). 비용 조회는 됐는데 closed 페어가 없으면 `0` |
| GET | `/api/history/journal?from=&to=&strategy=&ticker=&status=&outcome=&basis=&sort=&page=&size=` | history.py | **거래일지(1b, cycle413)** — 매수/매도 페어 하나를 복기 카드 한 장으로 묶는다. 쿼리 — 기간 기본 최근 30일(`from`=오늘−30일·`to`=오늘 KST, `costs.py::_parse_range` 재사용 — 형식 위반·`from>to`·366일 초과 **422**) · `status` all/open/closed · `outcome` all/win/loss · `basis` net/gross(이익·손실 판정과 손익 정렬의 기준) · `sort` recent/pnl_asc/pnl_desc · `page` ≥1 · `size` 1~100(기본 20). 정해진 값 밖은 **422**(`Literal`). 고르는 순서 = `get_trade_pairs` → 기간 겹침(`buy_date≤to ∧ (open ∨ sell_date≥from)`) → `status` → `cost_overlay.overlay_pairs`(남은 페어 **전부**에 1회) → 체결 id 문자열화 → `outcome` → `counts` 집계 → 정렬 → 페이지. 그래서 `counts`·`total` 은 필터를 다 적용한 뒤의 수다. 🔴 **체결 id 문자열화는 `overlay_pairs` 호출 뒤다**(`/api/history/pnl` 과 같은 순서) — 비용 맵 키가 `uuid.UUID` 라 먼저 바꾸면 하나도 맞지 않아 오류 없이 페어 비용이 0 이 된다(까닭 = `src/engine/CLAUDE.md` `cost_overlay.py` 「체결 id 의 타입」). 그 뒤 페어의 `*_trade_ids`·체결 행·메모 키·카드 `costs` 블록(`trades_by_id` 키를 `str` 로 바꾼 맵)은 모두 문자열이다. 가드 = `tests/integration/test_cycle413_fix1_journal_pg.py`(실 UUID + `trade_cost_daily` — 카드 `net_krw` = `/pnl` `net_profit_loss` · `costs.status` = `cost_status` · `fee_total` = `entry_fee` + Σ`exits.fee`). `basis=net` 인데 세후가 `None` 이면 세전으로 판정·정렬한다. 둘 다 `None` 이면 `outcome` win/loss 에서 빠지고 손익 정렬에서 맨 뒤다. `recent` = 보유 중(매수 시각 최신순) 먼저, 그다음 청산(매도 시각 최신순). 카드 세부(체결 행 `trade_history.get_trades_by_ids` · `trade_journal.list_orders`/`list_stops`/`list_notes` · `stock_master_daily.get_closes_in_range`/`list_business_days` · `llm_buy_evaluations.list_by_order_nos`)는 **그 페이지 카드만** 원천마다 1번 읽는다. 실패 처리 — `get_trade_pairs` 예외만 500 이다. 나머지는 200 이고 `[journal_route_error]` WARNING 을 남긴다: `record_start` 실패 = 4칸 `null` · `overlay_pairs` 실패 = `cost_available=false` + 비용·세후 칸 `lookup_failed` · 체결 행 실패 = `fills=None` 을 넘긴다(빈 목록으로 바꾸지 않는다 — 카드가 무엇을 「조회 실패」 로 내는지는 `src/engine/CLAUDE.md` `journal_view.py` 항목) · 주문 행·손절선·종가·영업일 실패 = 그 칸만 `lookup_failed` · AI 평가 실패 = 보강 없음 · 메모 실패 = 빈 값(`lookup_failed` 표시 없이 메모 칸이 비어 보인다). 카드 조립 = 순수 leaf `engine/journal_view.py::build_card`(입력 규약·「모름」 5종 = `src/engine/CLAUDE.md` 그 항목) |
| PUT | `/api/history/journal/notes/{anchor_trade_id}` | history.py | 거래일지 메모(D2) — `{"body": str}`. 문자열 아님·누락 **422**(pydantic) · strip 뒤 **코드포인트 4,000자** 초과 **422** · `anchor_trade_id` UUID 꼴 아님 **422**, 그 BUY 체결 행 없음 **404**. 공백만이면 메모 삭제(`data: null`). 그 밖은 strip 한 본문을 upsert 하고(`strategy`·`ticker`·`buy_date` = 그 BUY 행) `anchor_trade_id`·`body`·`created_at`·`updated_at` 을 돌려준다. 인증은 운영 키만 — 리포터 키 PUT **403**(cycle249 그대로) |
| GET | `/api/llm-evaluations?order_nos=<CSV>&trade_date=` | llm_evaluations.py | AI 매수평가 **배치 요약**("AI 자문" 버튼 활성 판정용). 키 = **`"<trade_date>\|<order_no>"` 복합 키**(헬퍼 `summary_key()`·프론트 `llmEvalKey()`) — 날짜마다 한 키다(주문번호 단독 키는 오래된 날짜의 평가를 지운다). 기록 없는 조합은 **키가 없다**(`null` 과 구별). CSV 는 공백·중복 제거 후 **1~200개**(= `/api/history/pnl` `size` 상한 — 함께 움직인다. pnl 페이지만 키우면 그 페이지의 버튼 판정 배치가 422), `trade_date` 는 `YYYY-MM-DD` 만 — 위반 **422**. 요약 10필드(계좌·`input_payload` 제외) |
| GET | `/api/llm-evaluations/retrospective?days=&cost_pct=&strategy=` | llm_evaluations.py | **주간 회고**(cycle297) — 매수 시점 LLM 점수 ↔ 청산 손익 조인·집계, 읽기 전용. `/{order_no}` **보다 먼저 선언**(뒤면 `order_no="retrospective"` 로 잡힌다). `days` 1~90(기본 7) · `cost_pct` 0.0~5.0(기본 0.25, 손실 정의 임계 %) · `strategy` 선택. 창 = **`[today-(days-1), today]`**(`today-days` 면 하루를 두 번 센다). `data` = `window{since,until,days}` · `cost_pct` · `pairs`(`float` 사영) · `aggregate` · `prompt_version_aliases` · `generated_at`. 페어 0건 = **200 + 빈 집계**, DB 예외 = **500** + `[llm_eval_route_error]`(이 로그엔 `order_no=` 문면을 쓰지 않는다). `prompt_version_aliases` 는 등가표일 뿐 — 합산은 소비자(목요일 루틴)가 하고 `aggregate` 안에서 접지 않는다 |
| GET | `/api/llm-evaluations/{order_no}?trade_date=` | llm_evaluations.py | AI 매수평가 단건 상세(모달) — **화이트리스트 사영 53키**(`SELECT *` 금지 — 새 열의 민감 값이 샌다). 계좌번호는 **`account_no_masked`(앞 4자리 + `****`)로만** — 리포터 키도 GET 을 통과한다. `models/kis_quote_account.mask_secret`·`models/krx_open_api.mask_secret`(뒤 4자리)과 방향이 반대라 **재사용 금지**. `Decimal` 6필드 `float` 사영. 기록 없음 **404** · DB 예외 **500** + `[llm_eval_route_error]` · `trade_date` 형식 위반 **422**(DB 호출 전). 신호 시각 열 `signal_time_local` 은 KST 보장이 없다 |
| GET | `/api/performance/summary?strategy=total` | performance.py | 실적 요약(최근 30일). `latest_asset`(`daily_performance.total_asset`) **`float()` 필수**. 가드 `tests/contract/test_routes_balance_perf.py::test_performance_summary_latest_asset_is_json_number`. `net_total_profit_rate`·`net_avg_daily_profit_rate`(순손익 기준, round 4 — gross 는 round 2 라 수수료·세금처럼 작은 차이가 같은 자리로 뭉개지는 것을 피한다)는 30일 창이 아니라 **개시 이래** 전체(`_since_inception_net_rows`, `get_performance(days=36_500, …)` 로 전 기간을 읽어 재누적) 축이다 — 비용이 없으면 gross `cumulative_return_rate` 와 같다. 비용 조회·계산 실패(개시 이래 재조회 포함)는 두 칸 모두 `None` 이다(세전 값을 세후 칸에 담지 않는다, `[cost_overlay_unavailable]`, 응답 200). 창 안 기록이 없으면 두 칸 `0` |
| GET | `/api/performance/daily?days=30&strategy=total` | performance.py | 일별 실적(실현손익 기반 일별 수익률 + TWR 누적 + 외부 입출금). 행마다 `daily_fee`·`daily_tax`·`daily_net_pnl`·`net_daily_profit_rate`·`net_cumulative_return_rate`·`cost_status`(settled/estimated/mixed) 를 함께 낸다. `strategy=` 를 주면 그 전략 체결의 비용만 합친다(배분은 그 날짜 범위 전체 체결로 하고 전략 필터는 배분 뒤에 건다). `net_cumulative_return_rate` 는 이 창이 아니라 개시 이래 전체로 재누적한 값에서 이 창의 날짜만 집는다(창 첫 행부터 다시 쌓지 않는다). 요율은 화면 범위가 아니라 서버 오늘 기준 30일 창(`cost_overlay.today_window_rates`). 비용 조회·계산 실패(개시 이래 재조회 포함)는 `[cost_overlay_unavailable]` WARNING + 새 칸 전부 `None`(기존 칸 그대로, 응답 200) |
| POST | `/api/performance/recompute` | performance.py | trade_history 기반 daily_performance 전체 소급 재계산(멱등) |
| GET | `/api/strategies` | strategies.py | 전략 목록 + 비중 + 상태 + 타겟가 |
| PUT | `/api/strategies/weights` | strategies.py | 전략별 비중 수정 + 즉시 `allocate_funds` + DB 저장. 단위 = **비율(0.0~1.0)**. 가드 = 아래 「전략 설정 쓰기 경로」 절 |
| GET | `/api/strategies/te?months=3` | strategies.py | 전략별 TE/RR 최근 N개월(months×30일), 관찰 전용. `data: TeRrMetrics[]`(7전략 · 19필드 + net 8필드 + 세전 승/패 수 `win_gross`·`loss_gross` 2필드, `src/engine/CLAUDE.md` 의 `te_metrics.py` 항목). 빈번 폴링인 `/api/strategies` 와 분리한 전용 엔드포인트 + **5분 monotonic 캐시**(months 키, `invalidate_te_cache()`). 페어 조회나 비용 조회가 한 전략이라도 실패한 계산은 `_TE_CACHE_FAILURE_TTL`(60초)만 캐시한다. 전략별 예외 격리(페어 조회 실패 = 그 전략만 빈 지표). `compute_te_rr` 호출 **전** `engine/cost_overlay.overlay_pairs(pairs)` 를 **별도 try** 로 불러 페어에 net 칸을 얹는다 — 실패(None 반환·예외)하면 `costs_available=False` 로 넘겨 그 전략은 `realized_net_sum_krw`·`fee_sum`·`tax_sum` 만 `None` 이고 나머지 지표(n·세전 합 등)는 세전 값으로 그대로 계산한다. 모집단 안에 net 칸이 있는 페어와 없는 페어가 섞여도 같은 세 칸이 `None` 이다(`src/engine/CLAUDE.md` 의 `te_metrics.py` 항목) |
| GET | `/api/strategies/params-schema` | strategies.py | 파라미터 카탈로그(`src/engine/param_catalog.py` 105키) + 전략별 적용 키·**현재값·기본값**. 화면(`StrategyParamsEditor`)은 **이 한 응답**으로 폼을 그린다 — 키·라벨·단위·범위·선택지를 프론트에 하드코딩하지 않는다(AST 가드 C35). `data` = 생산 `_build_params_schema` · TS 사본 `frontend/src/types/strategy-params.ts` `ParamsSchemaData` — `groups`(7) · `types`/`risks`/`units`(닫힌 어휘) · `params`(105, `ParamSpec` 전 필드) · `strategies[].params`(현재값)/`defaults`(`DEFAULT_PARAMS` 깊은 복사본) · `invariants.budget`(강제) + `invariants.order`(12건, 경고). 현재값을 같이 싣는 이유 = 따로 받으면 diff 미리보기 기준값이 낡는다 |
| GET | `/api/strategies/monitor` | strategies.py | **전략별 진행상황 스냅샷**(cycle414) — 대시보드 요약표·전략 패널이 10초마다 읽는 엔진 메모리 창. `/api/trading/status` 에 없는 값을 연다. `data` = `{as_of(KST +09:00), running, strategies}` · 전략마다 10키: `prepare`(`_live_prepare_meta` → `as_of`·`phase`·`started_at`·`finished_at`·`ok`, 없으면 null) · `funnel`(`_funnel_steps` 의 `step_no`·`step_name`·`step_conditions`·`survived_count`·`excluded_count` 만 — 생존·탈락 목록은 싣지 않는다) · `market_unit`(터틀 4전략·`etf_trend` 만. 오늘 스냅샷 `_market_unit_snaps[오늘]` 의 `mode`·`ok`·`m`·`state`·`bar_date`·`reason` 그대로, 없으면 `{mode, ok: false, reason: "not_computed"}`. 그 밖 전략 null) · `skips`(오늘 거르기 사유 `{known, day, counts, by_ticker}` — etf `_skip_logged` · donchian `_kk_lot_zero_logged`(`kk_lot_zero`)·`_kk_entry_cap_logged`(`daily_entry_cap`) · VCP/BFB `_gate_emit_capped`. 사유 캡이 없는 전략은 `{known: false}` — 0 으로 쓰지 않는다) · `paused_skips`(`_buy_paused_logged` 의 `skip\|` 키) · `shadow_buys`(`_shadow_logged` 의 `buy\|` 키) · `ticks`(후보 ∪ 보유 → `last_tick_at`·`acml_vol`, 미관측 null) · `candidates`(etf `design_qty`·`cluster_partners`·`cluster_blocked` / donchian `r_won`·`r_pct`·`design_lot` / VCP·BFB `latch_armed_at`(오늘 무장만) + VCP `first_cross_at`·`max` / 그 밖 원본) · `holdings`(etf `entry_n`·`hsb_closed`·`bars_since_buy`·`lines{hard,breakeven,trail,channel}`·`breakout_fail{line,active}`·`effective_stop` / donchian `r_won`·`stop`·`armed`·`channel`·`arm_price`·`target_1r`·`reached_1r`·`days_held`·`days_fallback`·`time_exit_bars`·`max_hold_bars` / 그 밖 `effective_stop`) · `extra`(donchian `daily_entries{count, cap}`, 그 밖 `{}`). 실효 손절선은 `get_effective_stop_price` 엔진 값이고, donchian 무장가는 exit-lines 와 같은 `routes/balance._exit_lines_kk` 로 계산한다(두 출처가 어긋나지 않게). 캡의 `_day`·래치의 `armed_date`·스냅샷 날짜가 오늘이 아니면 「오늘 기록 없음」 으로 보고 객체는 고치지 않는다. KIS·DB 호출 0 · 범위 안 `await` 0. **2초 캐시**(`_MONITOR_CACHE_TTL_S` — 성공 응답만, 직렬화한 본문을 `Response` 로 그대로 낸다). 실패는 HTTP 200 `success=false` + `logger.debug` 뿐. 🔴 **read-only** — 화면을 여는 것만으로 매수·손절 판정이 바뀌면 안 되므로 래치·로그 캡·시장 유닛 경보를 건드리는 호출(`_market_unit_view`·`_latch_entry`·`should_emit`·`mark_emitted`·`count_matching`·`get_targets_status`·`check_*`·`on_*`·`calc_*` 등)을 하지 않는다. 범위 = 핸들러 `get_strategies_monitor` + 이름이 `_monitor` 로 시작하는 모듈 함수 전부 · AST 가드 `tests/unit/ast/test_cycle414_monitor_purity.py`(M1~M8) |
| PUT | `/api/strategies/{id}/params` | strategies.py | 파라미터 수정(부분 dict 병합 + DB 저장, **즉시 반영**). 검증·422 코드·반영 시점 = 아래 「전략 설정 쓰기 경로」 절 |
| GET/PUT | `/api/strategies/system/auto-start` | strategies.py | 자동 매매 시작 설정 조회/변경 |
| GET | `/api/strategies/system/cash-usage-ratio` | strategies.py | 매매 가용 자금 비율 조회 `{ratio}`, 기본 1.0 |
| PUT | `/api/strategies/system/cash-usage-ratio` | strategies.py | 비율 변경. body `{ratio}` `[0.0, 1.0]`, 5% 단위 자동 보정(응답에 보정값). 다음 영업일 `_boot()` 부터 반영. 범위 외 400 |
| GET | `/api/logs` | logs.py | 시스템 로그. `?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&level=ERROR&page=1&size=50` → `data` = `{items, total, total_pages}`. `?limit=50&level=ERROR` 하위 호환(`size` 미지정이면 `limit`). 422 = `from_date>to_date` / `page<1` / `size>200`. KST 강제 — `f"{date}T00:00:00+09:00"` ~ `T23:59:59.999999+09:00` |
| GET | `/api/logs/search` | logs.py | 키워드 검색. `?q=...&level=INFO\|WARNING\|ERROR\|CRITICAL\|ALL&start=ISO&end=ISO&limit=1~1000`(기본 200). `q` 필수(빈 문자열 422). `level=ALL`·None = 무필터. ILIKE substring. `data` = `{logs:[{id,timestamp,log_level,message}], total, has_more}` — 페이징 없음(`has_more=true` 면 UI 가 키워드를 좁히라고 안내) |
| GET | `/api/recommendations` | recommendations.py | 전략수정 AI자문 목록(최근 30일, 신규+이력) |
| GET | `/api/recommendations/{id}` | recommendations.py | 단일 자문 상세 |
| POST | `/api/recommendations/{id}/apply` | recommendations.py | 선택 키만 적용(status pending/partial → applied/partial), 옵션 `apply_weight`. 가드 = 아래 「전략 설정 쓰기 경로」 절 |
| POST | `/api/recommendations/{id}/reject` | recommendations.py | 자문 전체 거절(status → rejected) |
| GET | `/api/log-reports?days=30` | log_reports.py | 일일 로그 분석 리포트 목록(신규순) |
| GET | `/api/log-reports/{YYYY-MM-DD}` | log_reports.py | 단일 영업일 리포트 |
| POST | `/api/log-reports/run?force=0` | log_reports.py | **오늘** 날짜 분석 수동 실행. **기본은 비파괴** — 완성 리포트가 있으면 `generate_daily_log_report` 를 부르지 않고 `success=false`(21:30 정산 뒤 재실행은 `api_metrics`·`strategy_funnel` 0 으로 완성 리포트를 덮는다 — `insert_log_report` = upsert). 완성 = `_is_complete_report` 4축(행 존재 · `metrics.snapshot_pass` 없음 · `summary` 가 비지 않고 `OPENAI_EMPTY_RESPONSE_SUMMARY` 도 아님 · `model` 있음). 막지 않는 경우 = 행 부재 · 1차 스냅샷만 있는 20:05~21:30 · OpenAI 실패 행(수동 복구 경로). 덮어쓰기 = `?force=1`(21:30 이후엔 여전히 파괴적) |
| GET | `/api/log-reports/bundle?date=YYYY-MM-DD` | log_reports.py | 20:20 클라우드 루틴의 분석 입력 번들(리포터 키로 GET 가능). `/{target_date}` **보다 먼저 선언**. `date` 미지정 = 오늘(KST), 미래·형식 오류(엄격 `%Y-%m-%d`) = `success=False`. `data` = `{target_date, collected_at(KST ISO), metrics, process_scoped_keys}`. `_PROCESS_SCOPED_KEYS`(`api_metrics`·`strategy_funnel`·`portfolio_risk_snapshot`)는 프로세스 현재 상태라, **과거 날짜는 이 3키만 그날 저장된 `daily_log_reports.metrics` 로 덮는다**(`_overlay_process_scoped_from_db`, 오늘은 덮지 않는다 — 덮은 `portfolio_risk_snapshot` 은 그날 21:30 스냅샷이다). 저장 행 없음·`metrics` 가 dict 아님·조회 실패 = fail-open(프로세스 값 유지, `success=True`) |
| POST | `/api/log-reports/{YYYY-MM-DD}/external` | log_reports.py | 20:20 루틴의 분석 결과 저장 — **리포터 스코프의 유일한 쓰기 경로**(`src/middleware/api_auth.py::REPORTER_WRITE_PATH_RE`). 바디 `ExternalReportIn`: `provider`(1~40자) / `model`(1~80자) / `summary`(1~4000자) / `findings`(≤50개, OpenAI 경로와 같은 정규화기 `_validate_report`) / `report_md`(선택, ≤200,000자). 범위 위반 422, 날짜 형식 오류 `success=False`. `src/db/log_reports.py::upsert_external_report` 는 `ext_*` 6컬럼에만 쓴다 — 21:30 OpenAI 경로의 summary/findings/metrics/model 무접촉 |
| GET | `/api/system/memory` | system.py | 프로세스 메모리(psutil RSS/VMS/threads/files) + (옵션) tracemalloc top 20 |
| GET | `/api/system/metrics` | system.py | 엔드포인트별 응답시간 p50/p95/p99(최근 1024개 샘플) |
| POST | `/api/system/metrics/reset` | system.py | metrics 누적 샘플 초기화 |
| GET | `/api/system/price-filter` | system.py | 가격 필터 `{min_price, max_price}`(원, 0 = 비활성) |
| PUT | `/api/system/price-filter` | system.py | 부분 갱신 `{min_price?, max_price?}`(None = 보존). `extra="forbid"` — 다른 키(폐기된 `mode` 포함) **422**. 음수 **400**. 같은 요청에 둘 다 > 0 이고 `min_price > max_price` 면 **400**(한쪽만 보내면 저장값과 대조하지 않는다). 저장 뒤 scanner 캐시 무효화로 즉시 반영(실패면 60초 TTL 뒤). 매수 진입 전용 — 기존 구독을 해제하지 않는다(`src/engine/CLAUDE.md` 가격 필터 항목) |
| GET | `/api/system/trade-amount-filter` | system.py | 거래대금 필터 `{min_amount}`(원, 0 = 비활성) |
| PUT | `/api/system/trade-amount-filter` | system.py | 부분 갱신 `{min_amount?}`. `extra="forbid"` → 다른 키 **422**, 음수 **400**. 저장 뒤 scanner 캐시 무효화로 즉시 반영(구독 해제 없음) |
| GET | `/api/realtime/subscriptions` | realtime.py | WebSocket 구독 슬롯 진단(KIS 에 슬롯 조회 API 가 없어 우리 측 추적을 노출). 세션 집계 = `src/realtime/CLAUDE.md` 「라우트 응답」 절. 더해서 `tickers`(subscribed/acked/fresh/stale, sorted) · `reconnect_count` · `ws_connected` · `last_tick_map: dict[ticker, ISO_KST\|null]` · `sessions[*].tickers_detail`(cap 200, stale 우선, 종목당 `ticker/ticker_name/stale/last_tick/retries/last_resub` + `last_cntg_hour`/`today_volume` — `inquire_ccnl` 캐시 TTL 5분·cap 20, 미스 = null) |
| POST | `/api/realtime/resubscribe` | realtime.py | stale(60s 미수신) TICK 종목 즉시 일괄 재구독(`_subscriptions` 보존). 종목마다 **실제로 구독된 채널**(`kis_ws._subscriptions` 에서 만든 `tick_channel_of`, 없으면 `TICK_TR_ID`, 판정 = `TICK_TR_IDS` 멤버십)로 `_send_subscribe(..., subscribe=True)` 만 보낸다(50ms 간격) — 리졸버의 현재 판정이 아니라 구독 사실이 정본이다. 응답 `{resubscribed, tickers}`, WebSocket 끊김 400, 로그 `[ws_manual_resubscribe] count=N tickers=[...]` |
| GET | `/api/realtime/market-operation` | realtime.py | 장운영상태(VI/거래정지/종목상태/서킷브레이커) — **관찰 전용, 매수 가드 미연계**. 소스 `H0UNMKO0`. 모양 = 생산 `get_market_op_state_summary()` · TS 사본 `frontend/src/types/market-operation.ts` `MarketOperationStatus`(카운트·샘플 + `circuit_breaker` 휴리스틱 — CB 전용 필드가 없어 best-effort + `details` cap 200). **`details` = VI ∪ 거래정지 ∪ `get_iscd_stat_active_tickers()`**(cycle371, 51/52/53/54/59 — 58 은 `get_halt_active_tickers()` 의 600초 TTL 이 맡는다. raw 값을 또 합치면 TTL 뒤에도 남는다). 헤더 `iscd_stat_active_count` 는 58 포함 6종 그대로 |
| POST | `/api/realtime/channel-probe` | realtime.py | KRX/NXT 단독 채널 다크런치 프로브(cycle253, 호출 전까지 무동작). body `{ticker(6자리 숫자), tr_id=H0STCNT0}`(허용 `{H0STCNT0, H0NXCNT0}`, **H0UNCNT0 는 422**). 409 = `already_probing`·`already_tick_subscribed`·`held_or_pending_clear`·`in_desired_universe`(breakout∪스윙∪momentum)·`probe_cap`(3)·`subscribe_dropped` / 400 = 메인 `_ws is None`. `kis_ws_pool.subscribe(tr_id, ticker, priority="LOW", bypass_limit=False 리터럴)`. 진입 시 전일 프로브 자동 축출(`action=evict`). `[krx_channel_probe] action=start` 는 **logger 단독**(write_log 병행 = 이중 INSERT) |
| GET | `/api/realtime/channel-probe` | realtime.py | 프로브 상태 `{probes:[…], count}` — 종목당 `ticker,tr_id,started_at,session_label,subscribed,acked,last_tick_at,age_secs,received(last_tick>started_at),first_tick_at(최초 1회 고정),price{price,acml_vol,open_price},live_tick_subscribed,in_desired_now`. `subscribed/acked` 는 세션 원시 `(tr_id,ticker)` 튜플 판정(H0UNCNT0 튜플 무시). 구독 변경 0. `in_desired_now=true` = 후보 편입 = 즉시 DELETE 신호 |
| DELETE | `/api/realtime/channel-probe/{ticker}` | realtime.py | 프로브 해제. `unsubscribe_in_pool` **미사용**(HIGH 로 승격된 종목이면 보조 세션 고아 튜플을 남긴 채 라이브 라우팅을 pop 한다). `[pool._main, *pool._quotes]` 의 튜플 보유 세션마다 `ws.unsubscribe`, 라우팅은 그 세션의 그 종목 튜플이 0 일 때만 pop. 응답 `removed_from`·`received`, 없으면 404. 20:00 `unsubscribe_all` 은 구독만 지우고 등록부는 다음 POST 의 축출이 정리 |
| GET | `/api/realtime/tick-channel-mode` | realtime.py | 채널 리졸버 모드 `{mode(메모리), stored(DB), default, valid_modes, config_key, switch_enabled, switch_offset_secs, switch_config_key, switch_windows}`. DB 조회 실패에도 **200**(`stored=null`). `switch_windows` = 그날 전환 창(`pre_to_krx` **1개**). 다이얼의 뜻 = `src/realtime/CLAUDE.md` 「시세 채널」 절 |
| PUT | `/api/realtime/tick-channel-mode` | realtime.py | 🔴 **장중 킬스위치.** body `{mode, switch_enabled?}`, `mode` ∈ `off`/`observe`/`enforce_low`/`enforce` — 어휘 밖은 **422**(DB 도 안 간다). DB 저장 후 **같은 요청에서 엔진 메모리까지 덮는다**. DB 쓰기가 실패해도 메모리는 반영 + `persisted=false`(`switch_persisted` 도 같다) + `message`. 라우트를 못 써도 폴링 백업(`src/engine/CLAUDE.md` `tick_channel_mode.py` 항목)이 ≤2분 안에 따라온다. ⚠️ `off` 는 **이미 전용 채널에 올라간 구독을 되돌리지 않는다**(장중 전환 금지 — 다음 `_boot`/재구독까지 남는다). `switch_enabled`(생략 = 현행 유지)·미지 필드(422 가 아니라 조용히 무시 — `extra=ignore`) = `src/realtime/CLAUDE.md` 「시세 채널」 절. 신규 엔드포인트 0 이 계약이다 |
| GET | `/api/market-regime/current` | market_regime.py | 메모리 레짐 + 매수 가드 표시 + `cash_usage_ratio` + `auto_regime_adjust` + ETF 레짐(관찰). 🔴 **`buy_blocked` 는 항상 `false`**(라우트 상수 — 레짐은 매수에 개입하지 않는다). `block_reason` = 관찰용 경보 사유. 설정 조회 실패 = graceful(`cash_usage_ratio`=1.0 · `etf_regime_enabled`=`False` · `auto_regime_adjust` 는 판독 불가 = `False`) |
| GET | `/api/market-regime/history?days=30` | market_regime.py | `market_regime_snapshots` 최근 N일 |
| PUT | `/api/market-regime/auto-adjust` | market_regime.py | 매크로 레짐 → `cash_usage_ratio` 자동 갱신 토글(키 `auto_regime_adjust`), **다음 영업일 `_boot` 부터 반영**. `/api/integrations/auto-regime-adjust` 와 동일 동작(Settings UI 는 그쪽) |
| GET | `/api/portfolio/risk` | portfolio.py | 전 전략 포트폴리오 리스크 **관찰 스냅샷**. 🔴 **매수 차단 0**. registry·순자산·섹터 조회가 전부 **graceful**(실패해도 200, 빈 값)이라 이 라우트의 실패가 매매를 멈추지 않는다 |
| GET | `/api/integrations/dkstock-regime` | system_integrations.py | 매크로 레짐 수신 활성 여부(출처 = 우리 `macro` 컨테이너, DB 키 `dkstock_regime_enabled`). `{enabled, source: 'db'\|'env', env_value, db_value}` — DB 우선 / .env fallback(db_value=null 이면 source='env') |
| PUT | `/api/integrations/dkstock-regime` | system_integrations.py | 수신 토글 `{enabled}`. 켜면 매크로 캐시를 비우고 `_refresh_market_regime_and_persist_safely()` 를 백그라운드 task 로 띄운다. 끄면 메모리 regime 을 `MarketRegime.empty()` 로 리셋(관찰 중단 — 매수 행위 불변). DB 실패 500, fetch 실패는 graceful(토글은 성공) |
| GET/PUT | `/api/integrations/kis-mcp` | system_integrations.py | 외부 백테스트 서버 활성 조회/토글(응답 구조 동일). 켜도 즉시 fetch 안 함 — 백테스트는 20:00 자문 시점 발화 |
| GET/PUT | `/api/integrations/auto-regime-adjust` | system_integrations.py | `auto_regime_adjust` 조회/변경 — `/api/market-regime/auto-adjust` 와 동일 동작(Settings UI 위치), 다음 영업일 `_boot` 부터 반영 |
| GET | `/api/integrations/etf-regime` | system_integrations.py | 지수ETF 고지로 스테이지 레짐 관찰 토글 `{enabled, source:'db', env_value:false, db_value}`(.env fallback 없음, `etf_regime_enabled` 기본 false). **관찰 opt-in — 매수 미개입** |
| PUT | `/api/integrations/etf-regime` | system_integrations.py | ETF 레짐 관찰 토글 `{enabled}`. DB 실패 500 |
| GET | `/api/integrations/buy-block` | system_integrations.py | 매수 가드 상태 = 백엔드 `src/models/system_integrations.py::BuyBlockStatusResponse` · TS 사본 `frontend/src/types/integrations.ts` `BuyBlockState`(`mode` ∈ `OFF`/`WARN`/`SOFT`/`HARD` · `thresholds` 4종 · `blocked`·`reasons`·`soft_multiplier`·`data_available`·`guard_inert`) + ETF 관찰 4키(`etf_kospi_stage`/`etf_kosdaq_stage` int\|null · `etf_defensive` bool\|null · `etf_enabled` bool, 소스 `get_current_etf_signal()` — TS 사본 `BuyBlockState` 에는 없다). 🔴 **전부 표시 전용** — 레짐 매수 게이트가 없다(risk.py/scheduler 소비처 0). 운영 DB `buy_block_mode=OFF` 권장(정직 표시). `data_available` = `regime.has_regime_data` · `guard_inert` = `mode != "OFF" and not data_available`(프론트 무력 배너 `buy-block-guard-inert` 근거) |
| PUT | `/api/integrations/buy-block` | system_integrations.py | 부분 갱신 `{mode?, vix_threshold?, fg_high_threshold?, fg_low_threshold?, defensive_enabled?}`. 422 = mode 외 값 / VIX [10,50] · FG_high [50,100] · FG_low [0,50] 밖. DB 실패 500. 저장 직후 `buy_block_state` 캐시를 무효화해 **표시**가 60s TTL 을 기다리지 않는다 — 매수 행위는 바뀌지 않는다 |
| GET | `/api/integrations/auto-apply` | system_integrations.py | AI 자문 자동 적용 토글 `{enabled}`(`system_config.auto_apply_enabled`, 키 부재 = `False`) |
| PUT | `/api/integrations/auto-apply` | system_integrations.py | 토글 `{enabled}`. DB 실패 500. 켜면 20:00 자문 직후 `auto_apply_recommendations` 가 **weight 감액만** 자동 적용한다(`_CONSERVATIVE_KEYS` 가 빈 집합이라 파라미터는 자동 적용하지 않는다 — `src/engine/CLAUDE.md` 의 `auto_apply_recommendations` 항목). ⚠️ 응답 `message` 의 「보수적 파라미터」 문구는 이 동작과 다르다 |
| GET | `/api/integrations/krx-open-api` | system_integrations.py | KRX 정식 OPEN API 설정 `{enabled, base_url, key_masked}` — 키는 `****1234`(뒤 4자리, 8자 미만·빈 값 = `****`)로만 나간다. DB 키 = `krx_open_api_enabled`·`krx_open_api_base_url`·`krx_open_api_key` |
| PUT | `/api/integrations/krx-open-api` | system_integrations.py | 부분 갱신 `{key?, base_url?, enabled?}`(None = 보존, 빈 body = 현재 상태). DB 실패 500(평문 키를 detail·로그에 싣지 않는다). 🔴 `enabled=false` 는 유니버스 적재의 주 소스를 폴백으로 민다 — 끄기 전 소비처 전수 확인, 끈 뒤 적재 종목수 실측(루트 `CLAUDE.md` 「비활성화 시 심층 검증 의무」) |
| GET | `/api/integrations/status-exit` | system_integrations.py | 관리종목(51)·단기과열(59) **보유 청산 + 당일 매수 차단** 킬스위치 조회(cycle369). `{sell_mode, buy_block_mode, stored, default, valid_modes, config_keys{sell, buy}, fire_window{start, end}, today}`. 두 모드 = 엔진 메모리 현재값 · `stored` = DB 원값(`status_exit_mode`·`status_buy_block_mode`, 축마다 독립 조회 — 실패한 축만 `null`, 모양이 틀린 행은 `__cycle369_malformed__`) · `fire_window` = leaf 상수 `FIRE_WINDOW_START`/`FIRE_WINDOW_END`(라우트 시각 리터럴 0, AST R7) · `today` = `status_exit_watch.snapshot()` 의 `{blocks, armed, passes}`(뜻 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절). ⚠️ `armed` 에는 쏘지 않는 `fallback_only` 종목도 있고, `passes` 는 날짜로 거르지 않아 그날 P0 전까지 전날 기록이 `day` 와 함께 보일 수 있다 |
| PUT | `/api/integrations/status-exit` | system_integrations.py | 🔴 **장중 킬스위치.** body `StatusExitModeRequest{sell_mode?, buy_block_mode?}`, 값 ∈ `enforce`/`observe`/`off`. 둘 다 없거나 어휘 밖 = **422**(무변경). 보낸 축만 바꾼다. 🔴 **메모리가 DB 쓰기보다 먼저다** — 보낸 축을 모두 `status_exit_watch.apply_mode(kind, mode, persisted=False)` 로 고정 반영 → 축마다 DB 저장 → 성공한 축만 `persisted=True` 로 고정 해제. 🔴 저장에 실패한 축은 **고정된 채 남는다**(조건·이유·`[status_exit_mode_pinned]` = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절). 응답 = GET 모양 + `persisted`(한 축이라도 실패면 `false`). 로그 `[status_exit_mode] sell_mode= buy_block_mode= persisted=` WARNING. 프론트 소비처는 아직 없다 |
| GET | `/api/integrations/quote-accounts?active_only=false` | kis_quote_accounts.py | 보조 KIS 시세 수신 계좌 목록 `{accounts: KisQuoteAccount[]}`(백엔드 `src/models/kis_quote_account.py::KisQuoteAccount` · TS 사본 `frontend/src/types/kis-quote-accounts.ts`). **app_secret 평문 절대 노출 안 함**(`app_secret_masked` = `****1234`) |
| POST | `/api/integrations/quote-accounts` | kis_quote_accounts.py | 등록 `{label, app_key, app_secret, kis_env:'real'\|'vts'}`. 201/409(label 중복)/422(빈 값)/500. 시세 수신 풀에만 등록(매매·잔고 활용 0) |
| PUT | `/api/integrations/quote-accounts/{id}` | kis_quote_accounts.py | `{active?, label?}`. 200/404/409/422. app_key/app_secret 수정 미지원(감사 추적성 — 삭제 후 재등록) |
| DELETE | `/api/integrations/quote-accounts/{id}` | kis_quote_accounts.py | 계좌 제거. 200/404 |
| GET | `/api/strategy-funnel?strategy_id=&target_date=` | strategy_funnel.py | 영업일 + 전략(생략 = 전체)의 단계별 후보/탈락(`step_no` ASC). `{strategy_id, target_date, snapshots:[{step_no, step_name, survived_count, excluded_count, survived_tickers, excluded_sample}], is_business_day, holiday_note}`. 영업일 = `(true, null)` / 휴장일 = `(false, "오늘은 휴장일 — 영업일 데이터 미수신")` / 판정 실패 = graceful `(true, null)`. KIS `chk-holiday` 결과 재사용(신규 KIS 호출 0) |
| GET | `/api/strategy-funnel/recent?strategy_id=&days=7` | strategy_funnel.py | 최근 N영업일 추이(`strategy_id` 필수, `days` 1~30) |
| POST | `/api/strategy-funnel/snapshot` | strategy_funnel.py | 수동 trigger — 최근 prepare 결과(`_funnel_steps`)를 즉시 저장(prepare 재실행 없음). `scheduler.capture_funnel_snapshots(registry, is_provisional=False, skipped_out=…)` 위임(09:30 자동 hook 과 같다 — 단계별 + `step_no=99`). 응답 `{target_date(오늘), saved_count, count}`. 라벨 가드가 건너뛴 전략·사유(`in_progress` · `prepare_failed` · `as_of_mismatch` · `evening_preview_reject` · `no_meta`)와 다른 기준일은 `message` 꼬리에 붙는다(응답 키 불변 — 판정 순서·자정 규칙 = `src/engine/CLAUDE.md` 「캡처 라벨 가드」 절). `is_provisional=True` 는 저녁 task 전용 |
| POST | `/api/stock-master/refresh-universe` | stock_master.py | universe 적재 수동 발화(`scanner._full_universe_load_once`). 공통 규약 = 표 아래 「stock-master 새로고침 4종」 |
| POST | `/api/stock-master/basics/refresh` | stock_master.py | KIS CTPF1002R + FHKST01010100 매스 보강 — `nxt_tradable`/`krx_halted`/`admin_item` 을 hot path lazy 호출에만 맡기지 않고 일일 1회 갱신. 자동 = `TIME_STOCK_MASTER_BASICS_REFRESH=16:10 KST` + start() 직후 1회 |
| POST | `/api/stock-master/daily/refresh` | stock_master.py | KIS FHKST03010100 일봉 즉시 적재(`_stock_master_daily_load_once()` — 자동 task 와 같은 함수). ⚠️ `run_periodic_task_loop` 를 안 타 신선도 마커를 건드리지 않는다. `_drop_today_bars` 는 그대로 통과하므로 **20:00 KST 이전 실행은 오늘 봉을 쓰지 않는다**(`force` 는 멱등 skip 만 우회) |
| POST | `/api/stock-master/master/refresh` | stock_master.py | KIS 일일 마스터 파일(`kospi_code.mst` / `kosdaq_code.mst`) 다운로드 + cp949 파싱 + `master_raw` 배치 upsert(컬럼 = `src/api/CLAUDE.md` 「kis_master.py」 절). 자동 = `TIME_STOCK_MASTER_MASTER_LOAD=16:30 KST` + start() 직후 1회 |
| GET | `/api/stock-master/refresh-progress` | stock_master.py | 4 작업(universe/basics/daily/master) 진행 상태(5초 폴링). 작업마다 10키 = 생산 `engine/refresh_progress.get_all_progress()` · TS 사본 `frontend/src/types/stock-master.ts` `RefreshProgress`(`status` ∈ `idle`/`running`/`completed`/`failed`). process-local 메모리 상태(uvicorn 단일 워커 의무) |
| GET | `/api/stock-master/stats` | stock_master.py | 집계 8키 = 생산 `db/stock_master.get_stats()` · TS 사본 `frontend/src/types/stock-master.ts` `StockMasterStats` |
| GET | `/api/stock-master/list?limit=100&offset=0&market=&min_market_cap=&min_trade_amount=&name_substr=` | stock_master.py | 페이징 list(refreshed_at DESC), limit ∈ [1,1000], offset ≥ 0(위반 422). `db.stock_master.list_paged_by_filter` 4 필터 = `market`(KOSPI/KOSDAQ/None) / `min_market_cap`(억원, `_eok_to_won` 환산) / `min_trade_amount`(억원 → 원) / `name_substr`(대소문자 무시). `{items, total, limit, offset}`. 🔴 **시총·거래대금 비교는 생성 컬럼 `hts_avls_eok`(억원) / `acml_tr_pbmn_won`(원)**(migration 039)로만 한다 — `raw.hts_avls`/`raw.acml_tr_pbmn` 은 jsonb *문자열*이라 numeric 비교가 항상 false = 조용히 0건 |
| GET | `/api/stock-master/scan-pool/summary` | stock_master.py | `[scan_pool_eager_refresh]` 오늘 KST 발생 수 `{eager_refresh_today}` |
| GET | `/api/stock-master/{ticker}/history?limit=100` | stock_master.py | 변경 이력(`db.stock_master.list_history`, changed_at DESC) `[{ticker, seq, change_type, raw, changed_at}]` — `seq` 0=최신본 / 1=직전본, `change_type` = INSERT/UPDATE/DELETE('TTL_REFRESH' 미발화). 표 정의 = `src/db/CLAUDE.md` 「DB 스키마」 `stock_master_history` |
| GET | `/api/stock-master/{ticker}/daily?days=30` | stock_master.py | 일봉(`stock_master_daily`, bas_dd DESC), days ∈ [1,100]. `_daily_row_for_json(row)` 가 **새 dict 로 사영**(`change_rate`/`prtt_rate` `NUMERIC(8,4)`). 규약 = `Decimal` → `float()`, **필드명 열거 금지**, `raw` 키 **재귀 변환 금지**(G-AST1 영속), 변환 실패는 **필드 단위 fail-open**. 빈 rows → **404**(`detail` = "전략 유니버스 대상만 적재" + F-1 단서), `get_recent_daily` 예외 → `[stock_master_daily_route_error]` + **500**. ⚠️ **F-1(알려진 한계, 미해소)** — `src/db/stock_master_daily.py::get_recent_daily` 가 **스스로** 예외를 삼켜 `[]` 를 돌려주므로 이 500 은 실질 도달 불가이고 DB 장애도 404 다. 그래서 404 `detail` 이 로그의 `stock_master_daily` 를 보라는 단서를 진다. 시정은 매매 행위 변경(그 db 모듈을 전략 `prepare()`·터틀 ATR 등이 공유)이라 **사용자 승인 + `domain-consult` 선행** 대상(`_workspace/00_URGENT_WORKLIST.md` 등재) |
| GET | `/api/stock-master/{ticker}` | stock_master.py | 단건 조회(StockBasics dict). 미존재 404 |
| GET | `/api/stock-chart/candles?ticker=&period=D&years=5` | stock_chart.py | 종목 차트 모달의 1~5년 일·주·월봉 — **읽기 전용 KIS 시세 조회 하나**. 조회·캐시·폭주 방지 = `src/api/period_chart.py::fetch_candle_chart`(계약 정본 = `src/api/CLAUDE.md` 「period_chart.py」 절). 쿼리 = `ticker` `^[0-9]{6}$`(ASCII 숫자만 — `\d` 금지) · `period` `D`\|`W`\|`M`(기본 `D`) · `years` 1~5(기본 5). **인자 위반만 422**. 종목코드는 **쿼리로** 받는다(경로형이면 `MetricsMiddleware` 의 raw path 메트릭 키가 종목마다 는다). `data` = `CandleChart`. 실패는 전부 **HTTP 200 + `success=false`, `data=null`** — 첫 창 `KisApiError`(`[stock_chart_error] stage=first_window`) · `ChartBusyError`(로그는 `period_chart` 의 `[stock_chart_busy]` 한 줄뿐) · 그 밖(`stage=unexpected`, 예외 문자열은 응답에 싣지 않는다). 호출은 **모듈 참조**(`period_chart.fetch_candle_chart(...)`) — 테스트 seam 이라 `from … import` 로 묶지 않는다. 데코레이터는 GET 하나, `src.engine`·`scheduler`·`src.api.order` import 0(AST G3) |
| POST | `/api/costs/reconcile?from=YYYY-MM-DD&to=YYYY-MM-DD` | costs.py | 실비용 사후 대사(트랙 C, 백필 겸용 · 운영자 수동 실행) — **실제 KIS `TTTC8715R` 를 부른다**. 생산 = `engine/trade_cost.reconcile` → `{from, to, kis_rows, saved_rows, pages, truncated, row_fee, row_tax, kis_tot_fee, kis_tot_tltx, totals_match, alerts}`(`totals_match` = 행 합계 ↔ KIS output2 합계 0.5원 이내, 합계가 비면 `null`). 날짜 형식·from>to·366일 초과 = 422(KIS 미호출) · 모의 환경 = 409 · KIS 거부 = 502 · 그 밖 = 500 + `[trade_cost_route_error]`. 리포터 스코프에서는 403 |
| GET | `/api/costs/summary?from=&to=&strategy=` | costs.py | 전략별 실비용 요약 — 생산 = `engine/trade_cost.build_summary` → `{from, to, strategies:[{strategy, gross_pnl, fee, tax, net_pnl, kis_rlzt_pfls, buy_amt, sell_amt, cost_bp, slippage_won, slippage_bp, slippage_n, cost_rows, estimated_rows}], total}`. 귀속·bp 식·슬리피지 출처 = `src/engine/CLAUDE.md` 모듈 맵 `trade_cost.py`. 날짜 422 · DB 예외 500(빈 결과로 위장하지 않는다) · `Decimal` → `float` 사영 |
| GET·PUT | `/api/costs/schedule` | costs.py | 매일 자동 대사 시각(cycle409 — 사용자 결정 10-04 Q1). PUT 바디 `{"time":"HH:MM"\|null, "days":1~31(기본 1)}` → `system_config.trade_cost_reconcile_time` = `{"value":"HH:MM","days":N}` · `time: null` = 끄기(`{"value": null}` 저장, 키 삭제 아님). `HH:MM` 이 아니거나 루프 수명 `[07:45, 21:30)` 밖이거나 `days` 범위 밖 = 422(밖의 시각은 영영 발화하지 않는다) · 저장 예외 = 500 + `[trade_cost_route_error]`. GET = `{enabled, time, days}`(키 없음 = `enabled:false`). 즉시 반영(훅이 60초마다 다시 읽는다). 리포터 스코프에서 PUT 은 403 |
| GET | `/api/costs/today?strategy=` | costs.py | 오늘 체결 × (정산 or 추정 요율), 전략별 + total(cycle411 — OrderMonitor 용, `scheduler.py` 무접촉 경로). `engine/cost_overlay.{today_window_rates,stock_master_etf_flags,trade_costs,day_cost_status}` 만 읽는다 → `{date, fee_rate, tax_rate, rate_source, cost_status, strategies:[{strategy,gross_pnl,fee,tax,net_pnl}], total:{gross_pnl,fee,tax,net_pnl}}`. `strategy=` 는 **배분 뒤에** 그 전략만 거른다(배분 자체는 오늘 전체 COMPLETED+PARTIAL 로 한다). `fee_rate`/`tax_rate`/`rate_source` 는 오늘 하루가 아니라 서버 오늘 기준 30일 창 — KST 날짜 단위로 메모리 캐시한다(같은 날 재조회는 DB 를 읽지 않는다). DB 예외 500 |
| GET | `/api/costs/daily?from=&to=` | costs.py | 날짜별 비용·슬리피지·`cost_status` 추이(cycle411) → `{from, to, days:[{date,fee,tax,slippage_won,slippage_n,cost_status}]}`(체결 없는 날은 0/`null`). 요율은 `from`~`to` 화면 범위가 아니라 서버 오늘 기준 30일 창(`cost_overlay.today_window_rates`, KST 하루 단위 캐시) · ETF 판정은 stock_master 구분 코드 우선(`cost_overlay.stock_master_etf_flags`, `stock_master.get_etf_group_codes` 일괄 조회). 날짜 형식·순서·366일 초과 = 422(`_parse_range` 재사용) · DB 예외 500 |
| GET | `/api/market-regime-label` | market_regime_label.py | 6장세 라벨(cycle410, **관찰 전용**) — `stock_master_daily.get_recent_daily("069500", 400)` 중 오늘(KST) 이전 봉만 써서 `engine/market_regime_label` 로 매긴다(D 일 라벨 = D-1 종가까지). `data` = `{today:{date,label,direction,volatility,slope_pct,vol_pct,basis_date}, history:[{date,label,m}] 최근 60(마지막 = 오늘), since, since_truncated, warmup_from, market_unit:{m,state,above_sma60,sma60_rising,close,sma60,basis_date,source,modes}, thresholds}`. 시장 유닛은 운영 판정 `market_unit.classify` 를 그대로 부른다(날짜마다 그 날 이전 마지막 80봉 — `compute_snapshot` 과 같은 창, 대조 테스트 MU2). 엔진 메모리 스냅샷을 여는 공개 경로가 없어 `source="db_recompute"`(운영 DB 종가 재계산판)다 · 신선도 판정(직전 영업일 봉 없음 → m=1)은 휴장일 조회를 피하려고 되풀이하지 않는다 · 운영 DB 종가를 읽으므로 ETF 보관소 종가 기준 골든(`test_cycle410_market_regime_label.py::test_g1`)과 값이 다를 수 있다(069500 두 출처가 2025-10 이후 197일 약 1% 차이) · `modes` = `strategy_manifest.MARKET_UNIT_SCALE_IDS`(etf_trend 포함 5전략)마다 운영 엔진 파라미터 `market_unit_mode` 를 `normalize_mode` 로(미등록·읽기 실패 = `null`). `basis_date` = 쓴 마지막 봉(20:30 적재 봉은 다음 아침 확정 전까지 잠정) · `warmup_from` = 읽은 첫 봉(히스테리시스 출발점) · `since_truncated=true` 면 `since` 는 하한. 80행 미만·나쁜 종가 = 200 + `success=false` + 사유 |
| GET | `/api/market/breadth?days=20` | market_breadth.py | 시장 등락 통계(cycle416, **관찰 전용** — 매크로 화면 6번째 섹션). 오늘(KST)을 뺀 최근 `days` 영업일(1~60, 기본 20 · 위반만 422)의 코스피·코스닥·합계 종목 수(상승·하락·보합·상한가·하한가·거래 없음)와 상승 비율. 원자료 = KRX 공개 API `krx.fetch_stk_bydd_trd`·`krx.fetch_ksq_bydd_trd` 두 함수뿐(**모듈 참조** — 테스트 seam 이라 `from … import` 로 묶지 않는다, AST G-416-3) · KIS 호출 0. 행 판정·집계 = `engine/market_breadth`(정의 = `src/engine/CLAUDE.md` 모듈 맵). `data` = `{asof_kst, window:{from,to,n_days,requested,complete,lookback_from}, days:[{date,kospi,kosdaq,total}](최신 먼저), summary:{kospi,kosdaq,total}, adr_reference:{oversold,overheated}, source, missing_dates, empty_dates, pending_date}` — 날짜 집계 11키(`rows`·`traded`·`up`·`down`·`flat`·`limit_up`·`limit_down`·`no_trade`·`out_of_band`·`unparsed`·`up_ratio`) · 요약 9키(`n_days`·`up`·`down`·`flat`·`limit_up`·`limit_down`·`no_trade`·`up_ratio`·`adr`). 날짜 창 = 평일 후보를 최신부터 `max(40, 2×days)` 달력일까지 거슬러 본다 — 두 시장 모두 빈 응답 = 휴장(`empty_dates`, 칸을 쓰지 않는다) · 한쪽이라도 호출 실패 또는 한쪽만 빈 응답 = `missing_dates`(칸은 쓰되 `days`·`summary` 에서 뺀다) · 가장 최근 평일이 비었고 지금이 그 다음 평일 10:00 KST 전이면 `pending_date`(아직 미게시, 칸을 쓰지 않는다). 캐시·한도는 **프로세스 메모리**다(재시작·배포 때 비워진다 · 마이그레이션 0) — `(시장, 날짜)` 단위 · 행이 있는 날은 영구 · 빈 날은 600초(`_EMPTY_TTL_SECS`) 뒤 다시 부르고 7일(`_EMPTY_PERMANENT_AFTER_DAYS`)을 넘긴 날은 영구 — 다만 같은 날짜의 다른 시장이 이미 "정상"(rows>0)으로 캐시돼 있으면 영구로 굳히지 않는다(추가 KRX 호출 없이 이미 받은 다른 시장 결과만 보는 교차 확인, cycle418-B 남은 결함 #1 시정 — 두 시장이 같은 원인으로 동시에 비는 경우는 걸러지지 않는 잔여 위험). 굳히는 순간 `[market_breadth_permanent_empty]` WARNING · 최대 512칸(`_CACHE_MAX_ENTRIES`, 넘치면 오래된 날짜부터 버린다) · 같은 키 동시 요청은 태스크 하나를 공유한다 · 동시 호출 4(`_KRX_CONCURRENCY`) · 호출 예외는 1초 뒤 1회 재시도(집계 예외는 재시도하지 않는다) · 요청 시한 45초(`_REQUEST_DEADLINE_SECS` — nginx `location /api/` 기본 60초 안) · KRX 호출 상한 KST 하루 1,000회(`_DAILY_CALL_BUDGET`, 재시도 포함 · 다 쓰면 `[market_breadth_budget_exhausted]` 그날 1회). 실패는 전부 **HTTP 200 + `success=false`, `data=null`** + 사유 문장 — KRX 꺼짐(`krx_open_api_enabled`) · 키 없음 · 설정 조회 예외(`[market_breadth_error] stage=config`) · 창 안 자료 0일(전부 실패 / 한도 소진 / 자료 없음을 문장으로 가른다) · 그 밖 예외(`stage=unexpected` · 예외 문자열은 응답에 싣지 않는다). 완료 로그 `[market_breadth_done]`. 인증은 공통 deny-by-default 그대로다(예외 없음 · 회귀 `test_r6_existing_auth_covers_route`). 🔴 `src/api/krx.py` 무변경(AST G-416-6 — 정의 이름 집합 + 본문 sha256 핀) · 로그·응답 인자에 KRX 키 0(G-416-4) · 두 새 모듈을 import 하는 곳 = 이 라우트와 `src/main.py` 뿐 — 매매 엔진·전략은 읽지 않는다(G-416-5) · 데코레이터는 GET 하나 |

**stock-master 새로고침 4종**(`refresh-universe` · `basics/refresh` · `daily/refresh` · `master/refresh`) 공통 — `?force=`
기본 `True`. **fire-and-forget** — `FastAPI BackgroundTasks` 로 응답 전송 *뒤에* 실행한다(axios 기본 timeout 에 걸려
조용히 실패하지 않게). 같은 작업이 돌고 있으면 `refresh_progress.is_running(<task_key>)` 가드가 **409**. 응답
`{status: "started", task_key}`, message `"<작업> refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링"`.

## 수동 매도 — `POST /api/trading/manual-sell`

body `{ticker, quantity}`, 시장가. 보유 전략이 있으면 그 전략 id·`exchange` 파라미터로 기록·라우팅하고, 없으면 `"momentum"`·`KRX` 다.

- 🔴 **컷 면제 경로** — `place_order` 직접 호출이라 `order_engine._market_rest_gate` 에 닿지 않아 **15:30~16:00 「완전 휴식」
  구간에도 나간다**(운영자 수동 조작은 막지 않기로 한 결정). 경고·`[market_rest_manual_exempt]` = `src/engine/CLAUDE.md` 「order_engine.py」 절.
- **보유보다 적은 수량을 팔 수 있다**(cycle385). 남은 보유는 손절·트레일링·15:20 청산을 계속 받는다.
- 🔴 **`_selling` 은 `place_order` 앞에서 세운다**(AST `test_cycle385_ast_b7.py` A8) — 뒤에 세우면 REST 응답보다 먼저 온 체결의
  `_selling.discard` 뒤에 표식이 서서 잔여 보유의 손절을 막는 좀비가 된다. 세울 때 `_selling_since` 를 적고 `_selling_locked_wait`
  에서 뺀다. 자동 매도가 이미 `_selling` 을 쥐고 있으면 건드리지 않는다(`_added` 거짓 = 손님 주문).
- 🔴 **되돌리는 것은 발사되지 않은 것이 확정된 실패뿐이다** — `_added` 참 ∧ 발사 전(`_sent` 거짓) ∧
  `order_engine._sell_not_placed_reason(e)` 가 이유(`qty_exceeded` · `market_closed` · `market_order_disallowed`)를 줄 때만
  `_selling`·`_selling_since` 를 되돌린다. msg1 문구 기반이라 키워드에 없으면 되돌리지 않는다(판정 정본 = engine 「매도 체결」 절).
- 그 밖의 발사 실패(EGW00201 · 보유 부족 문구 · 모르는 코드 · 전송 예외)는 표식을 두고 `[manual_sell_selling_kept] ticker= err=`
  WARNING — `src/api/base.py::_request` 가 주문 POST 도 전송 오류·5xx 에 다시 보내 앞 전송이 접수됐을 수 있다. 발사 뒤 실패도
  되돌리지 않는다(루트 금기 「주문이 나간 뒤의 실패로 재발사 금지」). 남은 표식은 그 주문의 종료 통보가, 열린 주문이 없으면
  `selling_reconcile` 이 푼다(AST AR3-7).
- 실패 줄 = `수동 매도 실패: <ticker> — <err> selling_released=<이유|->`(ERROR). 끝 칸 `-` = 유지 · 손님 주문 · 발사 뒤 실패.
- 🔴 **주문번호에 수동 주문 표식을 단다** — 매핑 3종과 같은 동기 구간(`place_order` await 뒤 · `insert_trade` await 앞, 사이
  `await` 0)에서 `engine._manual_sell_orders[order_no] = _added`(AST AR8). `strategy_id` 로 수동 주문을 추론하지 않는다. 표식의
  효과(J-2 재주문 · `_selling` 해제)와 남은 보유 규칙의 정본 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」.
- ⚠️ **알려진 한계 넷**
  - ① 16:00~20:00 KRX 애프터에 누르면 44/41 변환·KRX 라우팅 없이 시장가가 나가 거부된다. NXT 애프터 APBK3013
    (`[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다.`)은 시장가 불가 키워드에 걸려 되돌린다
    (`selling_released=market_order_disallowed`). KRX 애프터 거부 msg1 원문은 아직 모른다 — 키워드에 없으면 ④ 와 같다.
    `execute_sell` 위임은 매매 행위 변경이라 별도 승인 대상.
  - ② 접수 뒤 PENDING `insert_trade` 에 경계가 없다 — 체결통보가 먼저 보정 INSERT 를 하면 UNIQUE 위반으로 「매도 주문 실패」 를
    돌려주지만 실제로는 팔렸다. 보유보다 적은 수량을 판 경우(분할 매도) **다시 누르면 추가 매도**다 — 실패 응답이면
    잔고·체결부터 본다.
  - ③ 자동 손절 주문이 걸린 동안 이 주문이 끝나면 `_selling` 이 풀려 다음 틱 손절이 추적 잔여를 한 번 더 낸다(운영자 초과분 ≥
    추적 잔여면 운영자 몫이 팔린다 — engine 「매도 체결」 절 「알려진 한계」 첫 항목).
  - ④ 발사 여부를 모르는 실패는 표식이 남아 그 종목 자동 손절이 그 주문의 종료 통보나 `selling_reconcile`(15분 sync + 180초,
    09:30 전엔 sync 가 돌지 않는다)까지 멈춘다.

## 전략 설정 쓰기 경로 — 비중 · 파라미터 · AI 자문 적용

### `PUT /api/strategies/weights` — 비중

- **`weights` 단위 = 비율(0.0~1.0). 퍼센트(0~100) 금지** — 값 크기로 단위를 추론하지 않는다(AST 가드
  `tests/unit/ast/test_ast_weight_no_magnitude_heuristic.py`). `GET /api/strategies` 의 `weight` 와 같은 단위라 GET↔PUT 왕복이
  항등이다. 범위 위반(음수 / 1.0 초과) = pydantic `field_validator` **422**.
- **Σ 가드** — Σ(payload) > `1.0 + _WEIGHT_SUM_TOLERANCE`(1e-3) = **`success=false` + 저장 미수행** + `[weight_unit_violation]`
  WARNING. `registry.update_weights`/`save_weights` **전** early return 이라 메모리/DB split-brain 이 없다. **초과만** 잡는다
  (Σ<1 부분 payload 허용 — 전략 하나만 되돌리는 복구 저장을 막지 않는다).
- 🔴 **비중 0 가드**(cycle325) — 보유 종목을 든 전략(DB `positions` ∪ 메모리)에 비중 0 = `success=false` + `[weight_zero_guard]`.
  비중 0 은 `enabled` 자동 해제 = 그 보유분의 손절 정지다(루트 `CLAUDE.md` 「핵심 안전 규칙」). 하한선 검증보다 **앞**이라 부팅
  전(예산 합 0)에도 돈다. DB 보유 조회 실패 = 메모리로 판정 + `[weight_zero_probe_degraded]`.
- **매수금액 하한선 검증** — 보유 매수금액 ÷ Σ`total_investment` 미만의 비중은 `success=false`(「보유 종목 매도 후 비중을
  줄여주세요」). Σ`total_investment` 가 0(부팅 전)이면 건너뛴다.
- 통과 → `registry.update_weights` → 즉시 `allocate_funds`(Σ`total_investment` > 0 일 때) → `save_weights`. 비중 0 인데 메모리에서 켜져 있는 전략(= 섀도 전략, `update_weights` 가 켜짐을 지켰다)은 `save_weights(weights, keep_enabled={…})` 로 DB 에도 켜짐을 적는다 — 없으면 호출 모양은 `save_weights(weights)` 그대로(cycle399).
- Σ 검증은 **라우트 계층 전용** — `db.strategy_config.save_weights` 에 넣지 않는다(apply 라우트가 `{strategy_id: weight}` 단건
  partial dict 로 불러 Σ 불변식이 성립하지 않는다). apply 는 자체 Σ 검사(증액 한정)를 갖는다(아래).

### `PUT /api/strategies/{id}/params` — 파라미터 검증

`src/engine/param_validation.validate_params`(순수 함수 leaf)가 검사한다.

| 코드 | 조건 |
|---|---|
| `unknown_key` | 미지 키 |
| `not_editable` | 레거시 8키(`editable=False`) |
| `type_mismatch` | 자료형. `buy_paused`·`shadow_mode` 는 bool 만 — `"true"`·`1`·`null` 은 422 |
| `not_in_choices` / `pattern_mismatch` | enum·보드 목록·정규식. `entry_start="25:00"` 은 반드시 422(형식이 깨지면 매수 판정의 `ValueError` 가 `risk.on_tick` 으로 전파된다) |
| `forbidden_choice` | **VB + `post_nxt`** — 루트 `CLAUDE.md` 의 VB 조항(15:20 일괄매도 전제, POST_NXT 추가 금지)을 카탈로그 `forbidden_choices` 로 서버가 강제한다(화면 비활성은 안내일 뿐) |
| `out_of_range` | 범위 |
| `too_few_items` | **빈 `tradable_boards`**(`min_items=1`) |
| `budget_invariant` | `position_ratio × max_positions > 1.0` |

- **전 오류를 모아** 422 `detail`(배열, 원소 `key`/`code`/`msg`(한글)/`strategy_id`/`given`/`expected`)로 돌려준다. 하나라도
  있으면 **아무것도 저장하지 않는다**(all-or-nothing). 거부 로그 `[param_validation_rejected]` WARNING.
- 통과 = 200 + `data.applied`(저장된 키·값) + `data.warnings`. 부분 dict **병합**(요청에 없는 키 보존), `save_params` 는 병합된
  **전체 dict** 와 메모리의 `enabled`·`weight` 로 호출된다(행이 없을 때만 그 값이 쓰인다 — `src/db/CLAUDE.md` `save_params` 행). 알 수 없는 전략 id = 422 가 아니라 **200 + `success=false`**.
- **반영 시점** — 이 PUT 은 **즉시**다(in-memory `config.params` 를 덮는다). `strategy_config` SQL UPDATE 는 **다음 백엔드
  재시작에서만** 반영된다(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회). 보유 중 장중 재시작 금지(cycle232 D6)라
  **장중 롤백의 실효 수단은 이 PUT 뿐**이다.
- ⚠️ **예산 불변식** — 이미 위반 중인 상태를 악화시키지 않는 편집은 **통과 + `budget_invariant_preexisting` 경고**(막으면 그
  전략이 영구 편집 불가가 되고 복구 수단이 DB 직접 UPDATE 뿐이다). 경계 `1.0` 은 **통과**(EPS=1e-9 — 7 전략 중 6 전략의 기본값이
  정확히 1.0 이라 `<` 면 전면 저장 불가).
- ⚠️ **빈 `tradable_boards` 는 422 다** — 효과가 전략마다 정반대다(momentum·VB·LTV·donchian 은 `session._DEFAULT_TRADABLE_BOARDS`
  폴백으로 매수 계속, BFB·VCP·kojiro 는 매수 전면 중단). 매수를 멈추는 수단은 `buy_paused` 다(`{"params":{"buy_paused":true}}` —
  신규 매수 신호만 멈추고 청산은 그대로).
- identity(리스크 정체성 상수 19키)는 **서버가 막지 않는다** — 2단계 확인은 화면의 절차다(서버가 막으면 장중 긴급 롤백의 유일
  경로가 함께 막힌다).
- ⚠️ **`applies_to` 는 PUT 의 관문이 아니다**(의도된 비대칭) — 미지 키 판정이 `key in strategy.config.params`(런타임 상태)라 DB
  드리프트로 들어온 소관 밖 키도 저장된다. 그 전략이 읽지 않는 키라 매매 영향 0 이고, 조이면 비상 `curl` 롤백 경로가 좁아지므로
  **fail-open**(근거 = `src/engine/param_catalog.py` 모듈 docstring).

### `POST /api/recommendations/{id}/apply` — AI 자문 적용

- body `{keys: [...], apply_weight: bool=False}`. status 가 `pending`/`partial` 이 아니면 거부.
- 적용 키 = `keys` ∩ `recommended_params` ∩ **`PARAM_RANGES`**. 화이트리스트 밖 키는 `[manual_apply_safeguard_skip]` 후 빼고
  나머지만 적용한다(뺀 키는 `remaining` 에 남아 status `partial`, 응답 message 에도 실린다). 적용할 키·비중이 없으면 `success=false`.
- `apply_weight=true` → `recommended_weight` 를 `save_weights` 로 저장 + `applied_weight` 기록(`recommended_weight=null` 이면
  거부). weight 단독 적용 가능. `allocate_funds` 는 다시 부르지 않는다(다음 `_boot` 반영). 비중 0 을 켜진 섀도 전략에 적용하면
  `save_weights(…, keep_enabled={sid})` 로 DB 켜짐을 지킨다(cycle399 — 안 그러면 다음 재시작에 섀도 기록이 끊긴다).
- **증액 시 Σ 사전 검증** — `new_weight > 현재 weight` 이고 `타 전략 현재 weight 합 + new_weight > 1.0 + _WEIGHT_SUM_TOLERANCE`
  면 `[weight_sum_violation]` + `success=false`(params 적용 *전* early return — weight/params/status 무저장). **감액(`new <= 현재`)은
  Σ 상태와 무관하게 항상 통과**(Σ>1 로 오염된 상태의 복구 수단). float 변환 실패면 검사를 건너뛴다(fail-open).
  `_WEIGHT_SUM_TOLERANCE` 는 `routes/strategies.py` 에서 import(단일 진실원).
- 🔴 **비중 0 가드**(cycle333) — 보유 중인 전략에 비중 0 이면 **비중만 거부하고 파라미터 적용은 진행**한다(응답 message +
  `[weight_zero_guard] … route=recommendations`). 이 경로는 메모리 `config.weight` 만 바꾸고 `enabled` 는 안 건드려, 막지 않으면 다음
  재시작에서야 손절 정지가 드러난다. 양수 비중은 판정하지 않는다. 보유 조회 실패 = **fail-open**(`[weight_zero_guard_degraded]`).
  ⚠️ 이 경로에는 매수금액 하한선 검증이 없다 — 0 이 아닌 작은 비중은 그대로 저장된다.

## 장운영상태 화면 — `market_state.py` · `market_ops.py`

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/market-state` | 장 운영 시간표(코드 상수) + 두 시장(KRX/NXT) 커서 + 주문유형 카탈로그. `?on_date=` 로 다른 날짜 미리보기(±365일). `is_trading_day` 는 3상태(true/false/**null**="모른다") — `condition.is_trading_day` 전용이고 매매 경로의 fail-open `is_market_open()` 과 다르다. 코드 상수라 DB 장애와 무관하게 항상 200. 상세 = `src/engine/CLAUDE.md` `market_state.py` 절 |
| GET | `/api/market-ops` | 오늘 야간작업 현황 — 시각순 14행(basics 보강·purge·마스터·재무·토큰 재발급·매수중단·AI자문·유니버스·metrics 스냅샷·클라우드 루틴·일봉 적재·저녁 funnel·정산·로그분석). 행 `{id, label_ko, scheduled_at, status, last_success_at, evidence, note}`. 판정 = 아래 |

`GET /api/market-ops` 행 판정:

- `scheduled_at` 은 `scheduler.TIME_*`/`quote_token_refresh.TIME_QUOTE_TOKEN_REFRESH` 에서 읽는다 — 라우트 소스 시각 리터럴
  0건(AST 가드 `test_cycle285_ast_market_ops.py`).
- 상태 어휘 = `scheduled`/`running`/`done`/`failed`/`skipped_fresh`/`skipped_weekly`/`overwritten`/`not_fired`/`holiday`/`unknown`.
- 마커로 판정하지 않는 작업 4개 — `full_universe_load`(진행률만, `marker_iso=None` — 그 마커는 부팅 즉시 실행의 영업일 슬롯
  게이트용, `src/engine/CLAUDE.md` 「정기 task 루프」) · `evening_funnel_capture`(산출물) · `stock_master_daily_purge`·
  `quote_token_refresh`(마커도 산출물도 없어 시각이 지나도 `failed` 가 아니라 `unknown`).
- **휴장 확정**(`is_trading_day=False`)이면 증거가 아직 없는(`not_fired`/`scheduled`) 행만 `holiday` — 증명된 사실은 지우지
  않는다. 휴장 여부를 모르면(`None`) `not_fired` 는 `unknown`. `_no_evidence_status` 의 `unknown` 과 `_milestone_status` 의
  시각-경과 `done` 은 휴장 여부와 무관하게 그대로다.
- **20:05 metrics 스냅샷** — 21:30 정산이 같은 JSONB 컬럼을 덮어 `snapshot_pass` 키가 사라진다. 정산 시각이 지났고 실재하는
  완전판(`_is_complete_report` 4축)이 있으면 `overwritten`(정상), 없으면(20:20 루틴 placeholder 행만 등) `unknown`.
- 소스가 개별 실패하면(`evidence_errors`) 그 소스에만 의존하는 행은 `unknown`(`scheduled` 는 시계 판정이라 보존).
- **evidence-time 게이트** — 마커·진행률 기반 행(`full_universe_load`/`stock_master_daily_load` 등)은 예정 시각보다 2시간 넘게
  이른 "오늘 날짜" 증거(부팅 즉시실행·수동 새로고침)를 성공으로 인정하지 않는다.
- `evening_funnel_capture` 산출물(evidence 키 `snapshot_rows_today`, 이름은 계약) = `strategy_funnel_snapshots` 중
  **`target_date > 오늘` ∧ `is_provisional=TRUE` ∧ `snapshot_at >= _funnel_evidence_floor(today)`**(오늘 저녁 쓴 **다음 세션**
  잠정 행). 하한 = `TIME_EVENING_FUNNEL_CAPTURE`(21:00) − `_SCHEDULE_EVIDENCE_GRACE`(2시간) = 19:00 KST. `funnel_last_at` 은
  조건 없는 전체 기간 최댓값.
- **읽기 전용** — 8영역·`scheduler.py`·전략 7파일·`market_state.py` 무접촉. DB = 단일 `fetchrow` 집계 +
  `get_task_last_success_bulk` + `refresh_progress`(메모리) + `daily_log_reports` 1행.
- 실시간 장운영(VI·서킷브레이커)은 이 라우트에 없다 — 프론트는 `GET /api/realtime/market-operation` 을 쓴다.

## backtest.py — `/api/backtest/*`

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/backtest/mcp/health` | 외부 MCP 백테스트 서버(`http://43.202.187.5:3846/mcp`) 헬스체크. 실행/조회 엔드포인트는 미구현 |

`KIS_MCP_ENABLED` 가 꺼져 있으면 외부 호출 없이 graceful. 매매 hot path 무관.

## 응답 형식
모든 응답은 `models/response.py`의 `ApiResponse` 래퍼 사용:
```json
{ "success": true, "data": { ... }, "message": "ok" }
```

## 프론트엔드 연동
- 프론트가 사용하는 TypeScript 타입: `frontend/src/types/`
- 응답 필드명 변경 시 반드시 프론트 타입도 동기화할 것
- 페이징 응답에 `total`, `total_pages` 필드 포함 필수
- history, performance API에 `strategy` 쿼리 파라미터 지원 (전략별 필터)
