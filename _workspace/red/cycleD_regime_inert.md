# 사이클 D — 레짐 가드 silent inert 가시화 (Red 로그)

**날짜:** 2026-07-31
**명세:** `_workspace/red/_behaviors_cycleD_regime_inert_20260731.md`
**성격:** 관찰성만 추가. 매매 행위(blocked/soft_multiplier) byte 동일 = fail-open 보존.

## 배경
dkstock.cloud Let's Encrypt 인증서 07-27 만료 → `refresh_from_dkstock()` 가
`MarketRegime.empty()` 반환 → 07-27~31 4일간 매수 가드(mode=SOFT) 무력화됐으나
아무 경보 없이 대시보드는 "정상+평온" 표시. 근본 결함 = `get_buy_block_state()` 가
"데이터 있고 평온"과 "데이터 없음(empty)"을 동일 `blocked=False, reasons=[]` 로 반환.

## 신규 테스트 파일
- `tests/unit/engine/test_cycleD_regime_inert.py` (D-1 ~ D-4, 14 케이스)
- `tests/unit/routes/test_cycleD_buyblock_inert_field.py` (D-5, 3 케이스)

## Red 실행 결과 (2026-07-31)
`pytest tests/unit/engine/test_cycleD_regime_inert.py tests/unit/routes/test_cycleD_buyblock_inert_field.py`
→ **15 failed, 2 passed** (총 17)

15 실패 = 구현 대상 (결함 부재로 인한 RED, 오류 없음).
2 통과 = D-4 "미발화" 음성 가드 (현행 코드 경보 0 → GREEN 상태에서도 유지되는 정상 가드).

### D-1 `MarketRegime.has_regime_data` 프로퍼티 (5 케이스, 전부 RED)
판정 = `regime/vix/fear_greed_score` 중 1개라도 not None 또는 `bool(raw)`.
- `empty()` → False / `from_macro_cycle(정상 macro)` → True / vix 단독 → True /
  raw 단독 → True / 전부 None+raw={} → False
- **실패 양상**: `AttributeError: 'MarketRegime' object has no attribute 'has_regime_data'` (5건)

### D-2 `BuyBlockState.data_available: bool = True` 필드 (2 케이스, 전부 RED)
- 기존 3-인자 생성 → data_available 자동 True (회귀 0)
  - **실패 양상**: `AssertionError: BuyBlockState.data_available 필드 부재` (hasattr False)
- 명시 `data_available=False` 생성 가능
  - **실패 양상**: `TypeError: BuyBlockState.__init__() got an unexpected keyword argument 'data_available'`

### D-3 `get_buy_block_state()` 가 `data_available = has_regime_data` 세팅 (4 케이스, 전부 RED)
매매 행위 회귀 단언 동봉 (blocked/soft_multiplier/reasons 불변).
- empty+SOFT → data_available=False (+ blocked=False, mult=1.0, reasons=[] 불변)
- data+SOFT(임계 미발동) → data_available=True (+ 매매 행위 불변)
- empty+HARD → data_available=False (+ blocked=False fail-open 보존)
- 캐시 hit 2번째 호출에도 data_available 동일 (60s TTL 상호작용 보존)
- **실패 양상**: `AttributeError: 'BuyBlockState' object has no attribute 'data_available'` (4건)

### D-4 boot 매크로 경로 `[regime_guard_inert]` WARNING (3 케이스, 1 RED + 2 음성 GREEN)
`scheduler._refresh_market_regime_and_persist()` 직접 단위 호출 + caplog(`src.engine.scheduler`).
buy_block_mode 조회 = `src.db.system_config.get_buy_block_mode` monkeypatch.
- **empty regime + SOFT → 경보 1건 발화** → **RED** (`AssertionError: ... 경보 미발화, assert 0 == 1`)
- empty regime + OFF → 미발화 → **현재 PASS** (음성 가드, 구현 후 유지)
- 데이터 유입 regime + SOFT → 미발화 → **현재 PASS** (음성 가드, 구현 후 유지)

### D-5 `BuyBlockStatusResponse.data_available` + `guard_inert` (3 케이스, 전부 RED)
`_build_buy_block_status()` 직접 호출. `guard_inert = mode != "OFF" and not data_available`.
- empty+SOFT → data_available=False, guard_inert=True (+ mode/blocked/mult 회귀 0)
- data+SOFT → data_available=True, guard_inert=False
- empty+OFF → data_available=False, guard_inert=False (OFF 는 무력 아님)
- **실패 양상**: `AttributeError: 'BuyBlockStatusResponse' object has no attribute 'data_available'` (2건)
  + `AssertionError: BuyBlockStatusResponse.data_available 부재` (hasattr False, 1건)

## D-6 안전 기준선 (기존 스위트 GREEN 확인)
```
pytest tests/unit/engine/test_market_regime.py \
       tests/unit/engine/test_market_regime_buy_block_cache.py \
       tests/unit/engine/test_market_regime_buy_block_state.py \
       tests/unit/engine/test_risk_buy_block_modes.py \
       tests/unit/engine/test_risk_regime_guard.py \
       tests/contract/test_routes_system_integrations.py \
       tests/integration/test_boot_market_regime.py
→ 54 passed
```
매매 안전성 = risk.on_tick 의 blocked/soft_multiplier 소비 무변경 (신규 필드는 로깅/표시용).

## backend-dev 인계 인터페이스 (확정)
1. **`MarketRegime.has_regime_data` (property)** — `market_regime.py`,
   `return (self.regime is not None or self.vix is not None
   or self.fear_greed_score is not None or bool(self.raw))`.
2. **`BuyBlockState.data_available: bool = True`** — dataclass 필드 추가 (default True).
   기존 4 필드(mode/blocked/soft_multiplier/reasons) 뒤에 배치.
3. **`get_buy_block_state()`** — 생성하는 모든 BuyBlockState(OFF/HARD/WARN/SOFT/unknown/db-fallback
   전 분기)에 `data_available=self.has_regime_data` 세팅. blocked/soft_multiplier/reasons 로직
   완전 무변경. 캐시 저장/hit 경로도 값 보존.
4. **경보 위치** — `scheduler._refresh_market_regime_and_persist()`, `set_current_regime(regime)`
   (L2131) 직후. `mode = await src.db.system_config.get_buy_block_mode()` (try/except graceful 권장)
   후 `if not regime.has_regime_data and mode != "OFF": logger.warning("[regime_guard_inert] mode=%s
   설정됐으나 매크로 데이터 미유입 → 가드 무력, 데이터 복구 전까지 매수 무제한 통과", mode)`.
   boot 1회/일, cap 불요, `_DbLogHandler` 로 system_logs 자동 영속.
5. **`BuyBlockStatusResponse`** — `data_available: bool` + `guard_inert: bool` 필드 추가
   (`src/models/system_integrations.py`). `_build_buy_block_status` 가
   `data_available=regime.has_regime_data`, `guard_inert=(state.mode != "OFF" and not data_available)`
   로 채움 (`src/routes/system_integrations.py`).

## 범위 외 (별도 결정 인계)
fail-open → fail-safe 전환 / 수동 방어 오버라이드 / dkstock 인증서 갱신(운영) /
장중 매크로 재시도 — 명세 §인계 참조.
