# 사이클 163 Red 작업서 — #5 + #6 통합

## 시정 의도

- #5 (HIGH): `_boot()` 영역 prepare 호출 *전* `stock_master.count_active()` 가드 + 4 전략 (LTV/donchian/BFB/VCP) 자동 재시도 hook 통일
- #6 (MEDIUM): `_handle_buy_fill` 전량 체결 분기 3 영역 try/except 분리 + 가시화 강화

## 파일 변경

### 신규 추가
- `src/db/stock_master.py::count_active()` (사이클 128 count="exact" 패턴 답습)

### 본체 변경
- `src/engine/boot_manager.py` — prepare 호출 *전* count 가드 hook (5분 cap + 10초 polling)
- `src/engine/strategies/long_tail_volatility.py::prepare()` — 사이클 158 VB 패턴 답습
- `src/engine/strategies/donchian_swing.py::prepare()` — 동일
- `src/engine/strategies/bull_flag_breakout.py::prepare()` — 동일
- `src/engine/strategies/vcp_breakout.py::prepare()` — 동일
- `src/engine/order_engine.py::_handle_buy_fill` 전량 체결 분기 3 영역 try/except 분리

### 회귀 가드 신규 파일
- `tests/unit/db/test_cycle163_count_active.py` (2 케이스)
- `tests/unit/engine/test_cycle163_boot_prepare_guard.py` (4 케이스)
- `tests/unit/engine/strategies/test_cycle163_prepare_retry_hook.py` (4 케이스)
- `tests/unit/engine/test_cycle163_buy_fill_db_error_isolation.py` (6 케이스)
- `tests/unit/ast/test_cycle163_ast_persistence.py` (3 케이스)

## 영속 의무 (변경 0)

- 사이클 88 G-REJECT-1: `_on_tick` / `_on_board` raise 영속 (다른 callback 영역 변경 0)
- 사이클 147 `_handle_sell_fill` 영속 (변경 0)
- 사이클 158 VB 자동 재시도 hook 영속 (확장만)
- 사이클 161 `_handle_buy_fill` price 인자 영속
