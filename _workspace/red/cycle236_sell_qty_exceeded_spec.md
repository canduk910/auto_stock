# cycle236 — N2: 매도 수량 초과(APBK0400) 분류 + 잔고 재대조 수량 보정 (8영역 승인 = order_engine 한정)

> 발단 = 257720 실측: APBK0400 "주문 가능한 수량을 초과했습니다"(TTTC0011U 매도 ×3)가
> 어떤 분류기에도 안 걸려 3회 재시도 낭비 + CRITICAL + positions 보존(다음 시도도 같은
> 수량이라 영구 실패 루프). 사용자 지시 "n2 시작" = 착수 승인(8영역 = `order_engine.py`
> 한정 — `balance.py` 분류기는 비8영역).
>
> ⚠️ **기존 insufficient 경로에 흡수하면 안 된다** — 그 경로는 positions **통째 삭제** +
> "재등록 권고 로그"뿐이라, 부분 보유(257720형 실잔량 2)에서 잔여 수량이 손절 감시 밖으로
> 떨어진다. APBK0400 의 의미("요청 > 가능")는 부분 보유가 내재된 코드 → **재대조·보정**이 정답.

## KIS 근거

- 정본 오류코드 사전은 MCP/로컬 문서(`docs/kis/error-codes.md`)에 부재 — **실측 3건**
  (08-28 15:20:00~03, path=order-cash, tr_id=TTTC0011U 매도, ORD_QTY=3 vs 실보유 2)이 근거.
- 보수 설계 = `msg_cd=="APBK0400"` **∧** msg1 에 "수량"·"초과" 동시 매칭(문구 동반 필수 —
  APBK0400 이 다른 문맥에 재사용돼도 오분류 차단). 소비처는 `execute_sell` 매도 한정.

## 시정 2축

| # | 파일 | 내용 |
|---|------|------|
| S1 | `src/api/balance.py` (비8영역) | `is_sell_qty_exceeded(err) -> bool` 신설 — APBK0400 ∧ ("수량" ∧ "초과"). `is_insufficient_quantity` 무변경(APBK1234 계열 유지) |
| S2 | `src/engine/order_engine.py::execute_sell` (8영역·승인) | market_closed 분기 뒤·insufficient 분기 앞에 신규 분기: `get_balance()` 로 **`sellable_quantity`**(ord_psbl_qty — 기주문 잔량 차감 반영) 재대조 → ① `0 < sellable < pos.quantity` = **수량 보정**: `[sell_qty_reconciled]` WARNING + `pos.quantity = sellable`(메모리) + `save_position` upsert(DB) + `continue`(다음 attempt 가 보정 수량으로 재발사 — 3회 한도 내 자기 치유) ② `sellable == 0 ∧ 보유 > 0` = 전량 기주문 잠김 → positions **보존** + `[sell_qty_locked]` WARNING + return(다음 트리거 대기 — 보정해도 거부 반복) ③ `sellable == 0 ∧ 보유 == 0` = 기존 insufficient 경로 재사용(삭제+reconciliation) ④ `sellable >= pos.quantity` = 이상(수량 충분한데 초과 거부) → 로그 후 일반 재시도 fall-through ⑤ `get_balance` 실패 = graceful → 일반 재시도 fall-through(현행 행위 보존) |

## Red 결정적 입력

- R1 분류기: APBK0400+"주문 가능한 수량을 초과했습니다" → True / APBK0400+타 문구 → False / 타 코드+"수량 초과" → False / APBK1234 는 기존 분류기 소관 불변.
- R2 257720 재현(자기 치유): positions 3주, place_order 1차 APBK0400 거부 → 잔고 sellable=2 → 보정+continue → 2차 place_order **quantity=2 로 성공** + `[sell_qty_reconciled]` + pos.quantity==2 + save_position 호출.
- R3 전량 잠김: sellable=0·quantity=3 → positions 보존 + `[sell_qty_locked]` + 재시도 중단(place_order 1회만).
- R4 실보유 0: sellable=0·quantity=0 → 기존 insufficient 경로(positions 삭제 + `[positions_reconciliation]`).
- R5 잔고 조회 실패: 예외 → 일반 재시도 지속(3회, 현행 행위).
- R6 기존 APBK1234 경로 불변(삭제+권고 로그).
- R7 AST/구조: 분기 순서 = market_closed → **sell_qty_exceeded** → insufficient (market_closed 우선 계약 보존 — `src/api/CLAUDE.md` 분류 순서 절).

## 자체 발견 + 적대 검증 (3렌즈 10 에이전트, 발견 20 → 확증 4) 시정 내역 — 2026-08-29

- **자체 발견 (워크플로 대기 중 선제 시정)**: `[sell_qty_locked]` return 의 `_selling` 처리 —
  **의도적 유지**로 확정(discard 금지): sellable=0·보유>0 = 열린 매도 기주문 실재 = "진행 중"
  표식이 참. 유지가 on_tick 재진입 폭주(APBK0400+get_balance)를 차단하고, stale 은
  `[selling_reconcile]` 180s 재대조(열린주문 존재 검사)가 수습. market_closed 의 discard 와
  다른 이유 = 그쪽엔 열린 주문이 없음. 테스트 단언으로 봉인.

| ID | 심각도 | 결함 | 시정 |
|---|---|---|---|
| **C236-F1** | M | (a) 보정 분기가 `held_qty` 를 안 봐 "정확한 positions + 외부 부분 매도주문 잠김"(held==positions ∧ sellable<held)을 오염으로 오판 → 정상 포지션 하향 보정 → 외부 주문 취소 시 잠긴 주식이 손절 감시 밖(≤15분 사각 + 재등록 시 맥락 초기화) | held 대조 추가 — `held ≥ positions` = **부분 잠김** `[sell_qty_partial_locked]` 보존+중단(`_selling` 유지) / 진짜 오염(held<positions)의 보정 목표는 sellable 이 아니라 **held(보유 실체)** — 잠긴 주식도 보유라 손절 감시 수량은 held 정합, sellable 부족 재거부는 잠김 분기가 흡수 |
| **C236-V1** | M | reconciled 픽스처 축퇴(held==sellable) — `pos.quantity = held` 대입 뮤테이션·DB 보정 수량 오기록이 전 스위트 생존 | 비축퇴 케이스 신설(held=2·sellable=1·pos=3 → calls [3,2] + save_position kwargs quantity==2 단언) |
| **C236-V4** | M | `src/api/CLAUDE.md` 분류 헬퍼 절에 신규 분류 미기재(순서 계약 정본 스테일) | is_sell_qty_exceeded bullet + 검사 순서 4단 명기 |
| **C236-V5** | M | `src/engine/CLAUDE.md` 매도 절에 #1.5 미기재 | #1.5 절 신설(보정/잠김/`_selling` 유지 계약 포함) |

LOW 반영 = C236-F3(로그의 "(sync 후속 보정)" 부정확 → "sync 는 기보유 수량 미갱신" 정정) ·
C236-V6(`docs/kis/error-codes.md` §4 표에 APBK0400 행 등재 — §6-1 절차). LOW 수용 =
C236-F2(get_balance await 중 외부 체결 레이스 — sync 수습) · C236-F4(대출일별 다중 row 과소 —
INQR_DVSN 확인 후속) · C236-F5(3/3 attempt 보정 후 무재발사 — attempt 한도 계약) ·
N2-R4(보정 continue 가 backoff 스킵 — 의도된 자기 치유) · N2-R5(manual-sell 은 execute_sell
미경유 = 분류 미적용 — 가이드의 수동 매도는 실보유 수량 지정이라 무관).
