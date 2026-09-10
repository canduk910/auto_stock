# 손익 정의 2종 불일치 원인 분석 (D8)

- 작성: 2026-09-10 (읽기 전용 조사 — 소스 무변경, 운영 DB SELECT 전용)
- 발단: `_workspace/domain_consult/weekly_advice_2026-09-10.md` §2.1 D8 / §4.6 `needs_human_decision`
- 데이터: 운영 RDS `trade_history` 전 기간 614행(COMPLETED·PARTIAL), 2026-04-22 ~ 2026-09-10
- 재현: 자문 수치와 **원 단위까지 일치** (col −110,737 / pair −177,710 / 차이 66,973 / VB 65,363)

---

## 0. 한 문장 결론

두 정의의 차이는 산식의 차이가 **아니라 데이터 오염**이다 — `trade_history.profit_loss` 는
체결 시점 **메모리 포지션의 `buy_price`** 로 계산되고 pair 재계산은 **DB 의 BUY 행 `price`** 를
쓰는데, 이 둘이 어긋나는 사건이 세 갈래로 존재하며 그 대부분(66,973원 중 약 66,000원)이
**2026-05-21~05-22 이틀, 종목 2개, 행 4개**에 몰려 있다. 2026-06-18 이후 전 전략 잔여 차이는
**총 −670원**(5건, 건당 30~500원)으로 사실상 수렴했다.

---

## 1. 두 정의의 코드 위치와 규칙

### 1.1 정의 A — `trade_history.profit_loss` 행 합 (`daily_performance` 가 쓰는 값)

| 단계 | 위치 | 규칙 |
|------|------|------|
| 계산 | `src/engine/order_engine.py:1430` | `profit_loss = (price - buy_price) * quantity` |
| `price` | `handle_execution_notice` 인자 (`handler.py` `fields[10]` CNTG_UNPR) | **이번 체결통보의 체결가** |
| `buy_price` | `order_engine.py:1424-1428` `state.positions[ticker].buy_price` | **메모리 포지션의 매수가** — DB BUY 행이 아니다. 포지션이 없으면 `buy_price = price` 로 두어 손익 0 |
| `quantity` | `handle_execution_notice(quantity=)` | **이번 통보의 증분 체결수량**(`total_filled` 아님) |
| 기록 | `order_engine.py:1449-1453`(전량) / `:1501`(부분) → `src/db/trade_history.py:88-123` | `UPDATE ... SET status, price, profit_loss WHERE ticker=$ AND trade_type=$ AND status='PENDING' AND strategy=$` |
| 정산 | `scheduler.py:3635-3638` → `src/db/daily_performance.py:107-124` → `supabase/migrations/012_*.sql` | DB 함수 `recompute_daily_performance()` 가 **SELL `profit_loss` 합**으로 `daily_realized_pnl` 을 전략별·total 모두 덮어쓴다 |

⚠️ `scheduler.py:3663` 의 전략별 `s_pnl = strategy.state.daily_realized_pnl`(체결 조각마다
누산한 in-memory 값)은 같은 `_settle()` 끝의 `recompute_from_trades()` 가 **즉시 덮어쓴다**.
즉 `daily_performance` 는 어느 행이든 정의 A 하나다.

**부분 체결 시 규칙(설계상 결함 가능성)** — `quantity` 는 증분이므로, 매도가 N조각으로
체결되면 마지막 `update_trade_status` 가 **마지막 조각의 손익만** 컬럼에 남긴다(누적이 아니다).
또한 `update_trade_status` 는 `quantity` 컬럼을 **갱신하지 않으므로** 행의 수량은 주문 수량으로
남는다. → 실측상 이 경로가 만든 오차는 **0원**(§2.4).

**당일 재매수·재진입** — `_bought_today`/`sold_today` 가 당일 재매수를 막으므로 같은 (ticker,
strategy) 의 매수→매도 사이클은 날짜로 분리된다. VB 는 cycle201 재진입 쿨다운도 있다.

### 1.2 정의 B — closed pair 재계산 (TE 대시보드가 쓰는 값)

| 항목 | 위치 | 규칙 |
|------|------|------|
| 페어링 | `src/db/trade_history.py:562-674` `get_trade_pairs()` | `(ticker, strategy)` 그룹 안에서 `timestamp ASC`, 누적 보유수량이 **0 이하로 돌아오는 시점마다** 1 페어 emit. FIFO 가 아니라 **사이클 단위 가중평균**이다 |
| 대상 | `:583-587` | `status IN ('COMPLETED','PARTIAL')` — **PENDING·CANCELLED 는 제외** |
| 매수가 | `:630` | 사이클 안 BUY 행들의 **수량가중평균**(`price`×`quantity`) |
| 손익 | `:632` | `pl = (sell_avg - buy_avg) * sell_total_qty` — **매도 수량 기준**. 수수료·세금 미포함 |
| 소비처 | `src/routes/history.py:42-75` `/api/history/pnl`, `src/routes/strategies.py:93-95` → `src/engine/te_metrics.py:69` `compute_te_rr` | TE% 는 `profit_rate`(진입가 기준) 단순평균, `realized_sum_krw` 는 pair `profit_loss` 합 |

두 정의 모두 **수수료·거래세를 포함하지 않는다**. 차이의 원인이 아니다.

---

## 2. 실측 대조

### 2.1 전략별 (전 기간, 원)

| 전략 | 컬럼 합(정의 A) | pair 합(정의 B) | 차이(A−B) |
|------|---------------|----------------|-----------|
| volatility_breakout | −100,726 | −166,089 | **+65,363** |
| long_tail_volatility | −845 | −2,635 | +1,790 |
| momentum | +41,594 | +40,044 | +1,550 |
| donchian_swing | −31,290 | −29,590 | −1,700 |
| kojiro | −10,840 | −10,810 | −30 |
| bull_flag_breakout | −8,630 | −8,630 | 0 |
| **합계** | **−110,737** | **−177,710** | **+66,973** |

### 2.2 월별 (전 전략, closed pair 기준. 값은 pair−col)

| 매도 월 | pair 합 | 컬럼 합 | 차이(B−A) | pair 수 | 차이 발생 |
|--------|--------|--------|-----------|--------|----------|
| 2026-04 | 55,285 | 54,348 | +937 | 37 | 12 |
| 2026-05 | −56,820 | 15,800 | **−72,620** | 63 | 44 |
| 2026-06 | 1,460 | 6,750 | −5,290 | 40 | 19 |
| 2026-07 | −85,320 | −85,350 | +30 | 53 | 1 |
| 2026-08 | −60,965 | −60,865 | −100 | 67 | 2 |
| 2026-09 | −31,350 | −31,050 | −300 | 37 | 1 |

**차이는 5월에 몰려 있고 6월 중순 이후 소멸했다.** 이 문서의 나머지는 그 이유를 다룬다.

### 2.3 VB 차이 상위 10건

| # | 매수일시 | 매도일시 | 종목 | 수량 | 컬럼값 | pair값 | 차이(B−A) | 추정 원인 |
|---|----------|----------|------|------|--------|--------|-----------|-----------|
| 1 | 05-22 09:11:50 | 05-22 15:20:08 | 000250 삼천당제약 | 1 | −8,500 | −67,000 | −58,500 | ① 무-LIMIT UPDATE 도배 |
| 2 | 05-21 09:03:57 | 05-21 15:20:05 | 000250 삼천당제약 | 1 | −8,500 | −57,500 | −49,000 | ① 무-LIMIT UPDATE 도배 |
| 3 | 05-21 09:29:15 | 05-21 15:20:06 | 066570 LG전자 | 1 | −9,000 | +35,000 | **+44,000** | ① 무-LIMIT UPDATE 도배 |
| 4 | 06-15 09:00:30 | 06-15 15:20:07 | 005490 POSCO홀딩스 | 1 | +2,000 | −1,500 | −3,500 | ② 메모리 매수가 ≠ BUY 행 |
| 5 | 05-12 08:05:47 | 05-12 10:43:15 | 005930 삼성전자 | 1 | −18,000 | −20,500 | −2,500 | ② |
| 6 | 05-22 08:03:21 | 05-22 09:02:20 | 066570 LG전자 | 1 | −9,000 | −11,500 | −2,500 | ① |
| 7 | 05-20 08:15:05 | 05-20 08:41:33 | 042700 (종목명 미기록) | 1 | −13,000 | −15,500 | −2,500 | ② |
| 8 | 06-12 09:00:20 | 06-12 14:50:27 | 066570 LG전자 | 1 | −12,000 | −13,000 | −1,000 | ② |
| 9 | 06-04 09:05:08 | 06-04 09:32:44 | 000250 삼천당제약 | 1 | −8,500 | −9,500 | −1,000 | ① |
| 10 | 06-04 11:13:40 | 06-04 15:20:03 | 028260 삼성물산 | 1 | +7,000 | +8,000 | +1,000 | ② |

전체 VB = closed pair 129건 중 차이 발생 **29건**, 그 합 −75,733원.
여기에 **어느 pair 에도 안 들어간 VB SELL 행 2건**(컬럼 합에는 포함, pair 합에는 미포함,
합계 −10,370원)을 더하면 A−B = **+65,363원**으로 정확히 닫힌다.

### 2.4 배제된 가설

| 가설 | 판정 | 근거 |
|------|------|------|
| 부분 체결(매도 N조각) 때문에 컬럼이 마지막 조각만 담는다 | **기각** | 전 기간 297 pair 중 `n_buy>1 or n_sell>1` 인 pair 는 **1건**(092220 momentum, 2026-04-22~24)뿐이고 그 차이는 **0원** |
| 분할 매도 / 잔량 취소로 행 `quantity` 가 주문 수량으로 남는다 | 실측 영향 0 | 위와 동일. 다만 **코드상 결함은 실재**하므로 §4 후속에 남긴다 |
| 수수료·세금 포함 여부 | **기각** | 두 정의 모두 미포함 |
| 반올림 | **기각** | 차이가 44,000·58,500원 단위 |

---

## 3. 차이를 만드는 세 갈래 메커니즘

### ① `update_trade_status` 의 무-LIMIT UPDATE — 같은 값이 여러 행에 도배된다 (지배적)

`src/db/trade_history.py:110-117` 의 UPDATE 는 `order_no` 를 쓰지 않고
`(ticker, trade_type, status='PENDING', strategy)` 만으로 매칭하며 **`LIMIT` 이 없다**.
같은 (ticker, trade_type, strategy) 의 PENDING 행이 2개 이상이면 **전부** 같은
`price` + `profit_loss` 로 덮인다.

운영 DB 실측 — 서로 **다른 날짜**에 동일한 `(ticker, strategy, price, profit_loss)` 를 가진
SELL 행 그룹이 3개 존재한다:

| 종목 | 전략 | price | profit_loss | 행 수 | 날짜 |
|------|------|-------|-------------|-------|------|
| 000250 | volatility_breakout | 306,000 | −8,500 | 3 | 05-21 15:20 / 05-22 15:20 / 06-04 09:32 |
| 066570 | volatility_breakout | 234,000 | −9,000 | 2 | 05-21 15:20 / 05-22 09:02 |
| 073240 | volatility_breakout | 6,090 | +130 | 2 | 07-21 08:00 / 07-22 08:00 |

같은 종목의 BUY 행은 매일 값이 다르다(000250: 363,500 → 373,000 → 315,500 → 261,000).
즉 **오염된 쪽은 SELL 행의 `price` 와 `profit_loss` 이며 둘은 한 사건에서 나온 한 쌍**이다.
그래서 이 행들은 **정의 A 도 정의 B 도 참이 아니다** — 두 정의 모두 오염된 매도가를 읽는다.
차이가 나는 이유는 BUY 행만 오염을 피했기 때문이다.

이 3그룹이 VB 차이 −75,733원 중 **−66,000원**(상위 1·2·3·6·9번)을 만든다.

### ② 메모리 `Position.buy_price` ≠ `trade_history` BUY 행 `price` (잔여, 소액)

`profit_loss` 는 메모리 포지션의 매수가를, pair 는 DB BUY 행의 체결가를 읽는다. 포지션이
매수 체결통보로 등록되지 **않은** 경로에서는 이 둘이 갈린다:

- `src/engine/boot_manager.py:196` — KIS 잔고 보완 복구, `buy_price = int(h.avg_price)` (`pchs_avg_pric` 매입평균가격)
- `src/engine/scheduler.py:3547` — `_sync_positions_from_balance`, 동일하게 `int(h.avg_price)`
- `src/engine/order_engine.py` `[buy_fill_fallback_held_conflict]` — 타 전략이 이미 보유 중이면 매수 체결통보가 포지션을 **덮지 않고 skip** 한다

`system_logs`(보존 범위 08-11~) 로 확인한 06-18 이후 잔여 5건은 **전부 이 갈래**이며
**전부 익일 청산**(매수일 ≠ 매도일)이다:

| 매수 | 매도 | 종목 | 전략 | pair | 컬럼 | 차이 | 로그 증거 |
|------|------|------|------|------|------|------|-----------|
| 06-17 14:03 | 06-18 08:26 | 196170 | volatility_breakout | 1,000 | 500 | +500 | (로그 보존 밖) |
| 07-27 09:05 | 07-30 11:34 | 377450 | kojiro | 60 | 30 | +30 | (로그 보존 밖) |
| 08-26 14:44 | 08-27 09:00 | 078930 | long_tail_volatility | 2,100 | 2,000 | +100 | `[buy_fill_fallback_held_conflict] order_no=0001329100` |
| 08-28 09:15 | 08-31 09:00 | 257720 | volatility_breakout | 4,000 | 4,200 | −200 | BUY 행 `status=PARTIAL`, 매도 시 `[sell_qty_reconciled] positions=3→2` |
| 08-31 08:13 | 09-01 08:00 | 161890 | long_tail_volatility | −11,500 | −11,200 | −300 | `[buy_fill_fallback_held_conflict] order_no=0000042100` |

KIS 매입평균가격은 체결가와 수백 원 이내라 오차가 작다. **현재 남아 있는 유일한 활성 갈래다.**

### ③ PENDING BUY 행이 짝을 잃힌 SELL 을 pair 뷰에서 지운다

`get_trade_pairs` 는 `status IN ('COMPLETED','PARTIAL')` 만 읽는다. BUY 행이 PENDING 으로
남으면 그 사이클은 `buy_total_qty <= 0` 이라 pair 가 emit 되지 않고, **매도는 컬럼 합에만
남고 pair 합에서는 사라진다.**

운영 DB PENDING 잔존 = BUY 11행 + SELL 1행(+ CANCELLED SELL 1행).
그 중 000250 의 `2026-06-10 09:31 BUY 261,000 1주 PENDING` 이 같은 날 09:36 의
SELL(−10,500원)을 pair 에서 통째로 지운다. VB 고아 SELL 2건 합 −10,370원이 여기서 나온다.

---

## 4. 어느 쪽이 정본인가

### 4.1 판정

**둘 다 아니다. 원천 데이터가 오염됐고, 정의 B(pair)가 더 검증 가능한 형태일 뿐이다.**

- 갈래 ①의 행에서는 `price` 자체가 다른 날의 값이므로 **두 정의 모두 틀렸다**.
- 갈래 ②에서는 pair 가 옳다 — 체결통보의 체결가(CNTG_UNPR)가 그 거래의 실제 체결가이고,
  KIS 매입평균가격은 계좌 전체 평균이라 그 왕복의 손익이 아니다.
- 갈래 ③에서는 컬럼 합이 옳다 — 매도는 실제로 일어났고 pair 뷰가 누락시킬 뿐이다.
- 다만 정의 B 는 **매수 행 × 매도 행**이라는 두 관측을 곱해 쓰므로 어느 한쪽이 오염되면
  즉시 드러난다. 정의 A 는 관측(체결가) 하나와 **재구성된 상태**(메모리 매수가) 하나를
  쓰므로 오염이 그럴듯한 소액 손익으로 은폐된다. 감사 가능성은 B 가 높다.

### 4.2 계좌 실측과의 대조 — 이번 조사로는 **결론 불가**

`daily_performance` 로 05-21 을 대조하면 순자산 Δ = +21,316원인데 정의 A 는 −20,500원,
정의 B 는 −25,500원이다. 어느 쪽도 맞지 않는다. 순자산 Δ 가 실현손익이 아니라 **외부 입출금**에
지배되기 때문이다(같은 주 05-19 는 실현 −12,600원인데 순자산이 +106,716원 늘었다).
`net_external_cashflow` 자체가 §5 의 이유로 못 믿는 값이므로 보정도 불가능하다.

**결정적 대조를 하려면 KIS 정본이 필요하다.** 두 경로가 있고 둘 다 현재 미사용이다:

- `주식잔고조회_실현손익` (`inquire_balance_rlz_pl`, 국내주식 주문/계좌) — KIS 가 계산한 실현손익
- `주식일별주문체결조회` (`get_daily_orders`, TTTC0081R) 의 `avg_prvs`(평균체결가) — 조회 가능
  기간 안이면 `trade_history.price` 오염 행을 직접 반증할 수 있다. 5월분은 조회 기간 밖일
  가능성이 높다

---

## 5. 부수 — `net_external_cashflow` 의 T+2 시점 어긋남 (가설 **확인됨**)

### 5.1 산식

`src/engine/scheduler.py:3620-3632`

```python
prev_deposit = float(prev_total["deposit"]) if prev_total else float(summary.deposit)   # :3620
buy_total  = Σ price × quantity  (당일 BUY 행)                                            # :3625
sell_total = Σ price × quantity  (당일 SELL 행)                                           # :3627
net_trade_cashflow = sell_total - buy_total                                              # :3629
net_ext_cashflow = (float(summary.deposit) - prev_deposit) - net_trade_cashflow          # :3632
```

`summary.deposit` 은 `src/api/balance.py:214` 에서 `output2.dnca_tot_amt` 를 그대로 읽는다
(`src/models/balance.py:29`). `recompute_daily_performance()` 는 `deposit` 을 건드리지 않으므로
`daily_performance.deposit` 은 KIS 원값 그대로다.

### 5.2 실측 — 예수금이 순자산을 **2영업일 지연**해 따라온다

| 날짜 | `total_asset`(nass_amt) | `deposit`(dnca_tot_amt) | 일치 대상 |
|------|------------------------|------------------------|-----------|
| 2026-05-19 | 1,200,954 | 788,044 | |
| 2026-05-20 | 1,174,058 | 1,027,762 | |
| 2026-05-21 | 1,195,374 | **1,200,954** | = 05-19 `total_asset` |
| 2026-05-22 | 1,183,152 | **1,174,058** | = 05-20 `total_asset` |
| 2026-05-26 | 1,201,218 | **1,195,374** | = 05-21 `total_asset` |

원 단위까지 3연속 일치다. 국내주식 T+2 결제 때문에 D+0 예수금은 **2영업일 전까지 결제된
현금**만 담는다(그 시점 계좌는 전량 현금이라 순자산과 같아진다). 산식은 그 **T+2 지연 현금**
차분에서 **당일(T+0) 매매금액**을 빼므로, 매매가 있는 날마다 최대 이틀치 결제 금액이
"외부 입출금"으로 오계상된다.

전 기간 94행 분포: |중앙값| **145,630원**, 최소 −694,631원, 최대 **+1,598,444원**.
자문 §2.1 각주의 "산식 부산물인지 진짜 입출금인지 판별할 근거가 없다"(D5) 는 **산식 부산물**로 닫힌다.

### 5.3 대체 필드 (KIS 공식 명칭, `inquire_balance` output2)

KIS MCP `inquire_balance` 정본 컬럼 매핑에서 확인:

| 필드 | 공식 명칭 | 성격 |
|------|-----------|------|
| `dnca_tot_amt` | 예수금총금액 | **현재 사용 중.** D+0 결제 기준 |
| `nxdy_excc_amt` | 익일정산금액 | D+1 정산 반영 |
| `prvs_rcdl_excc_amt` | 가수도정산금액 | **D+2 정산 반영** — 당일 매매까지 모두 반영된 예수금 |
| `thdt_buy_amt` / `thdt_sll_amt` | 금일매수금액 / 금일매도금액 | KIS 가 집계한 당일 매매금액 |
| `thdt_tlex_amt` | 금일제비용금액 | 당일 수수료·세금 |
| `bfdy_buy_amt` / `bfdy_sll_amt` / `bfdy_tlex_amt` | 전일매수/매도/제비용금액 | |

`prvs_rcdl_excc_amt` 가 T+0 매매금액과 시점이 맞는 유일한 필드다. 또한 KIS 자신의
`thdt_buy_amt`/`thdt_sll_amt`/`thdt_tlex_amt` 를 쓰면 우리 `trade_history` 재집계와
**독립 검산**이 되고 수수료까지 들어온다.

⚠️ `AccountSummary`(`src/models/balance.py:28-35`)에 이 세 필드가 **없다** — 파서
(`src/api/balance.py:211-221`)와 모델을 함께 늘려야 한다. `src/api/balance.py` 는 8영역이
아니지만 `scheduler.py` 는 승인 대상이다.

---

## 6. 시정 방향

### 6.1 행위 변경 0 (관측·문서만, 사전 승인 범위 안)

| # | 조치 | 파일 | 비고 |
|---|------|------|------|
| O-1 | 두 화면의 숫자가 다른 이유를 문서화 — `daily_performance`=컬럼 합, TE/매매손익=pair 재계산, 5월 오염 구간 명시 | `src/db/CLAUDE.md`, `frontend/CLAUDE.md` | |
| O-2 | `update_trade_status` 가 **2행 이상**을 갱신하면 `[trade_status_update_multi]` WARNING 1행 | `src/db/trade_history.py` | 반환값 `affected` 를 이미 계산하고 있다. 갈래 ①이 지금도 살아 있는지 재는 유일한 채널 |
| O-3 | PENDING 잔존 BUY 행(현재 11건) 일일 카운트 관측 | 신규 leaf 또는 기존 정산 로그 | 갈래 ③의 분모 |
| O-4 | 정의 A↔B 차이를 `/api/history/pnl` 응답 `summary` 에 진단 필드로 병기 | `src/routes/history.py` | 표시만, 계산 무변경 |

### 6.2 코드 변경 필요 (승인 대상)

| # | 조치 | 파일 | 위험 |
|---|------|------|------|
| C-1 | `update_trade_status` 매칭에 `order_no` 를 추가하고 `LIMIT 1`(또는 `ctid` 단건 한정) 적용 | `src/db/trade_history.py` | **근본 시정.** 8영역 아님. 다만 `order_no` 가 빈 문자열인 수동/외부 주문 행 호환을 지켜야 한다(현재 PENDING 8행이 `order_no=''`) |
| C-2 | 매도 부분 체결 시 `profit_loss` 를 **누적**으로 쓰고 `quantity` 를 `total_filled` 로 갱신 | `src/engine/order_engine.py`(8영역) + `src/db/trade_history.py` | 현재 실측 영향 0이나 코드상 결함. **8영역 = 승인 + `domain-consult` 선행** |
| C-3 | 잔고 복구 경로가 `Position.buy_price` 를 KIS 매입평균가격 대신 `trade_history` 직전 BUY 행 체결가로 잡는다 | `boot_manager.py:196`, `scheduler.py:3547`(승인 대상) | **매매 행위 변경** — `buy_price` 는 손절·트레일링 기준가다. `domain-consult` 필수 |
| C-4 | `net_external_cashflow` 를 `prvs_rcdl_excc_amt` 기준으로 전환 + `thdt_*` 병기 | `src/models/balance.py`, `src/api/balance.py`, `scheduler.py:3620-3632`(승인 대상) | 산식에 안 들어가는 기록 전용 필드라 수익률 무영향(자문 §2.1 확인). 과거 94행은 소급 재계산 불가 |
| C-5 | 두 정의 중 하나로 통일 | `daily_performance` 재계산 함수 또는 TE 경로 | **통일은 오염을 지우지 못한다.** C-1·C-3 뒤에 논의 |

### 6.3 착수 순서 권고

O-2 (갈래 ① 활성 여부 실측) → C-1 → C-3(자문 선행) → C-4 → C-5 판단.
과거 데이터 백필은 **권고하지 않는다** — 오염 행의 참값을 복원할 근거가 없다(5월 로그 부재,
KIS 일별체결 조회 기간 밖). 구간을 표시하고 지표에서 제외하는 편이 정직하다.

---

## 7. 결정 카드 문안

> **카드 A — 손익 숫자 2종을 어떻게 할까요**
>
> 대시보드 두 곳의 손익 숫자가 66,973원 다릅니다. 원인은 계산식이 아니라 **5월 21~22일
> 이틀 동안 매도 기록 4행에 잘못된 값이 덮어써진 것**입니다. 6월 18일 이후 차이는 전
> 전략 합쳐 670원으로 사실상 없습니다.
>
> - **선택 1 (권고)** — 덮어쓰기를 일으킨 코드를 고치고(주문번호로 대상을 한정), 5월
>   오염 구간은 지표에서 제외 표시한다. 과거 숫자는 되돌리지 않는다.
> - **선택 2** — 두 화면을 한쪽 정의로 통일한다. 숫자는 같아지지만 **틀린 값끼리 같아질 뿐**이다.
> - **선택 3** — 현행 병존 유지 + 차이 나는 이유만 문서화한다.
>
> 선택 1 은 `src/db/trade_history.py` 한 파일(8영역 아님)이면 됩니다.

> **카드 B — 매수가를 어디서 읽을지 (매매 행위 변경)**
>
> 밤을 넘긴 포지션은 재시작 때 매수가를 **증권사 계좌 평균매입가**에서 가져옵니다. 실제
> 체결가와 수백 원 다르고, 그 값이 **손절·트레일링의 기준가**입니다. 체결 기록의 체결가로
> 바꾸면 손익 숫자는 정확해지지만 **손절 발동 지점이 달라집니다**.
>
> - **선택 1** — `domain-consult` 자문 후 전환한다.
> - **선택 2 (권고)** — 현행 유지. 오차가 30~500원으로 작고, 손절 규약 변경 위험이 이익보다 크다.
>   대신 두 값이 다를 때 로그 1행만 남긴다(행위 변경 0).

> **카드 C — 외부 입출금 숫자 (기록 전용, 수익률 무영향)**
>
> `net_external_cashflow` 는 실제 입출금이 아니라 **국내주식 2일 결제 지연이 만든 착시**임을
> 확인했습니다(예수금이 순자산을 정확히 2영업일 지연해 따라오는 것을 3일 연속 원 단위로 확인).
> 이 값은 수익률 산식에 들어가지 않으므로 **과거 수익률은 오염되지 않았습니다.**
>
> - **선택 1 (권고)** — 증권사 응답의 `가수도정산금액`(D+2 반영)으로 교체하고, 증권사가 집계한
>   금일매수/매도/제비용 금액도 함께 기록해 우리 집계와 교차 검산한다. 과거 94일치는 소급 불가.
> - **선택 2** — 이 필드를 아예 기록하지 않는다(쓰는 곳이 없다).
>
> 선택 1 은 `scheduler.py` 를 건드리므로 **승인이 필요**합니다.

---

## 8. 열린 질문

1. 갈래 ①(무-LIMIT UPDATE 도배)이 **지금도 발생 중인지** 모른다. 관측 O-2 없이는 잴 수 없다.
   마지막 확인 사례는 2026-07-22(073240)로 두 달 전이다.
2. 05-21~05-22 오염 행의 참 체결가는 복원 경로가 없다(`system_logs` 는 08-11 부터).
3. `daily_performance.deposit` 이 2영업일 지연이라는 것은 **전량 현금 상태의 날들**로만
   확인했다. 보유가 있는 날에도 같은 지연인지는 `prvs_rcdl_excc_amt` 를 실제로 받아 봐야 안다.
4. `total_asset` 이 쓰는 `nass_amt`(순자산금액)의 결제 시점 성격은 확인하지 않았다.
   여기도 T+2 지연이면 일별 수익률의 분모가 흔들린다.
