# cycle451 — 실비용 추정 요율 = 가장 최근 정산일 하루의 요율 (Red 명세)

사용자 결정 2026-10-13 — 「추정요율은 가장 최근의 율로 하는게 맞지 않을까?」 → 「응 그래.」
배경: 10-13 아침 주계좌가 수수료 우대 계좌로 바뀌었다(약 0.14% → 약 0.014%). 30일 창 가중 평균은 옛 요율을 30일 동안 섞는다.

## 계약

정산 행(`trade_cost_daily` — `trad_dt`·`buy_amt`·`sll_amt`·`fee`·`tl_tax`)으로 추정 요율을 낼 때:

1. **수수료율** = `buy_amt + sll_amt > 0` 인 정산 행이 있는 **가장 최근 `trad_dt` 하루**의 Σfee ÷ Σ(buy_amt+sll_amt).
2. **세율** = `sll_amt > 0` 인 정산 행이 있는 **가장 최근 `trad_dt` 하루**의 Σtl_tax ÷ Σsll_amt. 수수료율 기준일과 다를 수 있다.
3. 조회 창은 그대로 `[today − window_days, today]`(`RATE_WINDOW_DAYS=30`). 창 안에 근거가 없으면 **그 요율만** 기본값(`DEFAULT_FEE_RATE`·`DEFAULT_TAX_RATE`).
4. 반환 키는 `fee_rate`·`tax_rate`·`source` 셋 그대로(늘리지 않는다). `source` = 둘 중 하나라도 정산 행에서 나왔으면 `"measured"`, 둘 다 기본값이면 `"default"`.
5. `today_window_rates` 의 KST 날짜 단위 캐시·예외 비캐시·`_reset_cache_for_tests()` 는 그대로.
6. 무접촉: 정산값이 있는 체결의 비용, `trade_costs`·`net_twr`·`overlay_pairs` 배분 규칙, ETF 세금 0 규칙, 8영역·`scheduler.py`.

구현 자리는 Green 이 정한다(`estimate_rates` 의미 변경 vs 새 순수 함수). 순수 함수 단위 테스트는 **Green 이 이름을 정한 뒤 추가**한다.

## 호출처 (grep 전수, 2026-10-13)

- `estimate_rates` — `src/` 안 호출은 `src/engine/cost_overlay.py::today_window_rates` **한 곳**뿐. 테스트가 직접 부른다(아래 표).
- `today_window_rates` — `cost_overlay.overlay_pairs` · `routes/costs.py`(today·daily) · `routes/performance.py` · `routes/balance.py` · `routes/history.py`.
- `trad_dt` 모양 — `db/trade_cost.get_daily_range` 가 DATE 열을 그대로 SELECT 한다 → asyncpg `datetime.date`. ISO 문자열로는 오지 않으므로 문자열 케이스는 테스트하지 않는다.

## 새 테스트 — `tests/unit/engine/test_cycle451_latest_day_rates.py`

시계 = freezegun 2026-10-13 12:00 KST · `get_daily_range` 는 창 필터가 있는 메모리 스텁 · DB 실접속 0.

| 테스트 | 증명하는 것 | 현 코드 |
|---|---|---|
| t1 | 옛 요율 10일 + 최근일 하루 새 요율 → `fee_rate` 0.00014 · `tax_rate` 최근일 | 실패(0.001285) |
| t2 | 최근일이 매수만 → `fee_rate` 그날 · `tax_rate` 그 전 가장 최근 매도일(더 옛 매도일과 섞지 않는다) | 실패 |
| t3 | 같은 날 종목 3행 → 그날 전체 합 | 실패 |
| t4a | 창 안 행 없음 → 둘 다 기본값·`default` | 통과(가드) |
| t4b | 창 안 매도 0 → `tax_rate` 만 기본값·`measured`, `fee_rate` 는 최근일 | 실패 |
| t5a | 최근일이 거래금액 0 인 행뿐 → 건너뛰고 그 전 날 | 실패 |
| t5b | 거래금액 0 인 행만 → 둘 다 기본값·`source="default"`(계약 4) | 실패(현재 `measured`) |
| t7 ×2 | 반환 키 집합 = `{fee_rate, tax_rate, source}` · 값은 `float` | 통과(가드) |
| t8 | `GET /api/costs/today` — 오늘 정산 전 체결의 수수료·세금이 최근일 요율로 추정된다 | 실패 |

Red 실행: `python -m pytest tests/unit/engine/test_cycle451_latest_day_rates.py -q` → **7 failed, 3 passed**.

## Green 이 고쳐야 할 기존 테스트

`estimate_rates` 를 그대로 두느냐에 따라 갈린다(시뮬레이션 결과 = 회신 참조).

| 테스트 | 전제 | 영향 |
|---|---|---|
| `tests/unit/engine/test_cycle411_cost_overlay.py::test_r1_rates_when_cost_rows_exist_then_measured_ratio` | 이틀(D1 매수·D2 매도) 행의 **합산 평균** `(99+102)/(700000+720000)` | `estimate_rates` 의미를 바꾸면 실패(새 값 = `102/720000`). 그대로 두면 통과 |
| `tests/unit/routes/test_cycle411b_cost_overlay_route_fixes.py::test_l2_open_pair_after_partial_sell_splits_buy_fee_and_keeps_total` | 기대값을 `estimate_rates(db.cost_rows)`(이틀 합산)로 만들고 라우트 값과 비교 | `estimate_rates` 를 그대로 두고 `today_window_rates` 만 바꾸면 실패. 의미를 바꾸면 통과 |
| `test_cycle411b…::test_m1_balance_holdings_carry_buy_fee_paid` · `test_cycle411_cost_overlay.py::test_t1`·`t2`·`t4c` | `estimate_rates` 를 **이름으로** 부른다(행은 하루뿐이라 값은 같다) | `estimate_rates` 를 지우거나 개명하면 실패 |
| `test_cycle411c…::test_f8a`·`f8b` · `test_cycle411b…::test_m2a~m2e` | 창 안 표본 1행(09-20) → 0.003 / 0.004 | 영향 없음(하루뿐) |

문서(Phase 4.8 대상, 테스트 아님): 「서버 오늘 기준 30일 창」 문구 — `src/engine/cost_overlay.py` docstring · `src/routes/{costs,performance,history,balance}.py` docstring/주석 · `src/routes/CLAUDE.md`(`/api/balance`·`/api/performance/daily`·`/api/costs/today`·`/api/costs/daily` 행) · `src/engine/CLAUDE.md` `cost_overlay.py` 항목. 창 길이는 그대로이고 「창 안 가장 최근 정산일」 로 바뀐다.
