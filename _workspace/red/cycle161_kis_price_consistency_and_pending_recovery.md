# 사이클 161 — KIS 체결단가 정합 + boot PENDING 자동 복구 (HIGH)

## 발주 배경

- 사용자 보고 005940 NH투자증권 6/16 사고 정합
 - SELL trade_history PENDING + price 33,350원 + profit_loss 0 영구 잔존 (HTS 실제 33,250원 체결)
 - BUY trade_history 33,400원 vs HTS 33,350원 (+50원 차이)
- 사이클 147 commit `1772508` strategy fallback + UniqueViolation 강제 UPDATE 시정 완료. 그러나 자연 복구 미발화

## Phase 1 진단 (KIS MCP 정본 + 로컬 코드)

### KIS MCP 정본 영구 확정

- **주문 응답 (TTTC0011U/TTTC0012U 영역)** = `KRX_FWDG_ORD_ORGNO` + `ODNO` + `ORD_TMD` 3 키. **체결가 응답 부재**
- **체결통보 (H0STCNI0) 26 컬럼**:
 - `CNTG_UNPR` (체결단가, idx 10) — 실제 체결가
 - `ODER_PRC` (주문가격, idx 25)
 - `ORD_COND_PRC` (호가조건가격, idx 18)
 - `CNTG_QTY` (체결수량, idx 9)
 - `CNTG_YN` (체결여부, idx 13) = "2" 체결 / "1" 접수
- `src/realtime/handler.py:166` 영역 = `price = int(fields[10])` = `CNTG_UNPR` 정합

### 코드 영역 결함 정밀 진단

**결함 #1 (HIGH 매매 안전성 직결, 의제 K)**: `_handle_buy_fill` 영역 `update_trade_status` 호출 시 **`price` 인자 누락**

```python
# src/engine/order_engine.py:983 (사이클 147 영속)
affected = await update_trade_status(ticker, TradeType.BUY, TradeStatus.COMPLETED, strategy=strategy_id)
# → price 인자 부재 → trade_history.price = PENDING INSERT 시점 record_price (주문가/scanner current_price) 영속
```

대비 `_handle_sell_fill` 영역 (line 1076-1079):
```python
affected = await update_trade_status(
 ticker, TradeType.SELL, TradeStatus.COMPLETED,
 strategy=strategy_id, price=price, profit_loss=profit_loss,
)
# → price 인자 명시 → 체결단가 (CNTG_UNPR) 영속
```

→ **005940 BUY 33,400원 vs HTS 33,350원 (+50원 차이) 정합** = scanner `current_price` 33,400원 시점 매수 → 체결단가 33,350원 (호가 한 단계 위) → BUY UPDATE 시점에 체결단가 미반영 → PENDING INSERT 33,400원 그대로 잔존.

**결함 #2 (LOW 자동 복구, 의제 A)**: `_boot()` 영역 PENDING 자동 sync hook 부재

- `_sync_orders_to_db` 는 KIS 주문체결내역 → trade_history INSERT (수동 매매 흡수). PENDING row 영역 자동 복구 hook 부재
- 005940 사고 영역 = callback 영역 race + UPDATE 0 affected + INSERT UniqueViolation chain → 자연 복구 미발화
- 사이클 147 강제 UPDATE 영역 시정 후에도 callback 자체 미발화 시 잔존

## Phase 2 시정 방향

### 의제 K 시정 (HIGH 매매 안전성)

`_handle_buy_fill` 영역 `update_trade_status` 호출에 `price=price` 인자 추가 + 보정 INSERT 영역 UniqueViolation 시 강제 UPDATE 추가 (`_handle_sell_fill` 패턴 100% 답습).

### 의제 A 시정 (보강)

`_boot()` 영역에 `_recover_pending_trades()` hook 추가:
- 당일 KST 영역 PENDING/PARTIAL row 영역 전수 추출
- KIS 주문체결내역 (`get_daily_orders`) 영역과 교차 검증
- KIS 영역 = "전량체결" 시 trade_history 강제 UPDATE (체결가 + COMPLETED)

본 사이클 161 = 의제 A 영역 = 진단 + 1차 영역 폐기 (사이클 162+ 자문 후). 사이클 161 = **의제 K HIGH 시정 집중**.

## 회귀 가드 ≥10 케이스

- G-161-K-1 (HIGH): `_handle_buy_fill` 영역 `update_trade_status(BUY, COMPLETED, price=체결단가)` 호출 영구 가드
- G-161-K-2 (HIGH): BUY UPDATE 시점 trade_history.price = CNTG_UNPR (체결단가)
- G-161-K-3: BUY 보정 INSERT 영역 UniqueViolation 영역 강제 UPDATE (사이클 147 `_handle_sell_fill` 패턴 답습)
- G-161-K-4: 부분 체결 (PARTIAL) BUY 영역도 price 인자 명시
- G-161-K-5 (HIGH): `_handle_sell_fill` 영역 price 인자 보존 (회귀 0)
- G-161-K-6: AST 정적 가드 = `_handle_buy_fill` 영역 `update_trade_status` 호출 시 `price=` keyword 의무
- G-161-SAFETY-1 (HIGH): risk.on_tick / realtime / auth 변경 0 직접 검증
- G-161-SAFETY-2: 매도/익일청산/15:20 강제청산 hot path 변경 0 검증
- G-161-DOCSTRING: 사이클 161 docstring 명세

## 영속 의무 매트릭스

- 사이클 30 trade_history UNIQUE 인덱스 `(ticker, order_no, trade_type)` 영속
- 사이클 38 명문화 (매수 진입 영역 + 영역 별도)
- 사이클 102 G-REJECT-1 callback exception raise 영속
- 사이클 147 `_handle_sell_fill` strategy fallback + UniqueViolation 강제 UPDATE 영속

## 영구 차단 영역

- 단순 swallow 영역 영구 거부 (`raise` 영속)
- price 인자 누락 silent 결함 미래 재발 차단 = AST 정적 가드 G-161-K-6
- 사이클 30 UNIQUE 인덱스 + 사이클 147 강제 UPDATE chain 영속
