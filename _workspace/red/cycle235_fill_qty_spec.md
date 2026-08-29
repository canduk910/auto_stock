# cycle235 — N1 부분 체결 수량 오염 시정 (257720 실사고, 8영역 승인 = handler·order_engine 한정)

> 발단 = 08-28 257720: BUY 2주 주문 → 실체결 2주(1+1)인데 `positions.quantity=3` →
> 15:20 강제청산 3주 매도 → APBK0400 ×3 → CRITICAL → 주말 오버나잇(월요일 manual-sell 2주 예정).
> 사용자 지시 "N1부터 작업 시작" = 8영역 승인(범위: `realtime/handler.py` 수량 파싱 1줄 +
> `order_engine.py` 방어 클램프). 나머지 6영역 diff 0 유지.

## 근본 원인 (KIS 정본 `ccnl_notice` 26컬럼 대조 — MCP 실조회)

| 인덱스 | KIS 정본 | 현행 handler 주석/코드 |
|---|---|---|
| fields[9] | **CNTG_QTY (체결수량 — 통보 건별 증분)** | "주문수량" (미사용) |
| fields[16] | **ODER_QTY (주문수량)** | "체결수량(CNTG_QTY)" ← **quantity 로 사용 중 (오독)** |

주석이 정본과 **뒤집혀** 있고 코드가 주석을 따랐다. 단일 전량 체결은 CNTG_QTY==ODER_QTY 라
**잠복**, 부분/분할 체결에서만 발현. 257720 실측 fields[16]=(1,2)(자식주문 1주 + 원주문 2주),
엔진이 증분으로 합산 → 1+2=3. fields[9]=(1,1) 이면 합 2 = 실체결 정합.

## 시정 3축

| # | 파일 | 내용 |
|---|------|------|
| S1 | `src/realtime/handler.py` (8영역·승인) | `quantity = int(fields[9])` (CNTG_QTY 정본) + 필드 주석 전면 정정([9]↔[16]) . 접수(1)/체결(2) 필터·계좌 필터·price fields[10]·나머지 파싱 불변 |
| S2 | `src/engine/order_engine.py` (8영역·승인) | `handle_execution_notice` 누적 직후 **overrun 클램프**: `_order_qty` 매핑이 **있을 때만** `total_filled > ordered_qty` 면 `[fill_qty_overrun]` WARNING + `_filled_qty`/`total_filled` 를 ordered 로 캡(BUY·SELL 공통 방어 — 주문수량 초과 체결은 물리적으로 불가, 파싱/중복 이상의 최후 방어망). 매핑 부재(수동/외부 주문)는 ordered=quantity 폴백이라 클램프 **미적용**(다중 통보 오캡 방지) |
| S3 | `src/db/trade_history.py` (비8영역) | `_update_trade_status_by_order_no` WHERE `status='PENDING'` → `status IN ('PENDING','PARTIAL')` — 전량 체결 보정 경로가 PARTIAL row 를 COMPLETED 로 못 올려 257720 trade 가 PARTIAL 영구 잔존하던 N1-b 시정(COMPLETED/CANCELLED 는 계속 불변) |

## Red 결정적 입력

- R1 파서: 26필드 payload(fields[9]=1, fields[16]=2, [13]="2") → 콜백 quantity==**1** (현행 2 = RED). 접수 통보([13]="1") 스킵 보존. 필드 부족(<15) 무시 보존.
- R2 257720 재현: 매핑 ordered=2, 통보 quantity (1,2) → 클램프로 `pos.quantity==2` + `[fill_qty_overrun]` WARNING + 전량 COMPLETED (현행 3 = RED).
- R3 정상 부분 체결 (1,1): pos 1→2, overrun 무발화, PARTIAL→COMPLETED.
- R4 매핑 부재: ordered=quantity 폴백 경로에서 2차 통보가 클램프로 잘리지 **않는다**.
- R5 SELL 공통: ordered=3 매핑, 통보 (2,2) → total 3 캡 → 전량 매도 처리 정상.
- R6 N1-b: PARTIAL row 대상 강제 UPDATE COMPLETED → SQL 이 PENDING+PARTIAL 포괄(affected>0). COMPLETED row 는 여전히 비대상.
- R7 AST: handler 에 `int(fields[9])` quantity 대입 존재 + `fields[16]` 의 quantity 대입 0. 승인 외 6영역(risk/session/scanner/registry/auth/api.order) diff 0 은 커밋 전 git diff 실측.

## 적대 검증 (3렌즈 7 에이전트, 발견 16 → 확증 4) 시정 내역 — 2026-08-29

| ID | 심각도 | 결함 | 시정 |
|---|---|---|---|
| C235-F1 | M→L | CNTG_QTY 빈값 → quantity=0 이 매핑 부재 폴백(ordered=0)과 결합 시 `0>=0` 전량 판정 — BUY 0주 포지션 봉인·SELL 포지션 무단 삭제 가능(pre-existing 잔존 리스크, cycle235 회귀 아님) | `handle_execution_notice` 진입부 `quantity<=0` → `[fill_qty_zero]` WARNING + drop(fail-closed — 정본상 체결통보 CNTG_QTY 항상 양수). 회귀 테스트 동반 |
| C235-R1 | M | 클램프가 누적만 캡·증분(quantity)은 원시값 → `_handle_sell_fill` 손익이 초과분만큼 왜곡(daily_realized_pnl = 일일손실 게이트 소비값) | 클램프 시 유효 증분 동반 캡 `quantity = max(0, ordered − prev_total)`. R5 테스트에 pnl 정합 단언 추가 |
| C235-V1 | M | R6 테스트 종결상태 불변 가드가 `or True` 공허 — COMPLETED 편입 뮤테이션 미검출 | SQL 텍스트 검사 폐기 → **바인딩 args 의 status 리스트 정확 일치**(["PARTIAL","PENDING"]) 단언 |
| C235-V2 | M | 부분→전량 정상 완결이 WARNING/ERROR 3연타(UNIQUE 위반 보정 + 30초 잔여취소 실패)를 남겨 D+1 오귀인 위험 | monday_0831_guide 에 "정상 시그니처" 명시. 후속 후보 = 전량 분기에서 잔여취소 타이머 해제 + 1차 UPDATE 의 PARTIAL 포괄(행위 결정 사안 — 워크리스트 등재) |

LOW 12 중 반영 = V6(핀 주석 항목 수 정정). 주요 수용 = C235-R2(forced UPDATE 가 order_no 무스코프? — 아님, order_no 키 스코프 확인됨·과거 잔존 PARTIAL 은 동일 order_no 한정) · C235-R3(`_completed_orders` 무한 적재 — 일일 리셋 확인 필요, 후속) · C235-V3(AST 정규식 우회 — 행위 테스트 R1 이 봉인) · C235-F2(비숫자 CNTG_QTY int 예외는 websocket 수신 루프가 흡수 = silent drop, 정본상 희귀 수용).
