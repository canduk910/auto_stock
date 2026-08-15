# refactor-review A3 (Red) — `_refine_cooldown_business_days` base 승격

**상태**: Red 작성 완료 (tdd-engineer). Green = backend-dev.
**테스트 파일**: `tests/unit/engine/strategies/test_refactor_a3_cooldown_base.py`
**선례**: H-1 `_apply_high_since_buy_from_candles`(`test_kojiro_high_since_buy_recovery.py`) · A5/A6 `_rederive_entry_atr`/`_atr`(`test_refactor_a5a6_atr_base.py`)

## 목표

`_refine_cooldown_business_days` 4벌 byte-identical(로그 접두사 1토큰만 상이) → `StrategyBase` 단일 정의 + 전략별 `_COOLDOWN_LOG_LABEL: ClassVar[str]` override 로 승격. **행위 보존 리팩토링** — 매매 로직/청산/쿨다운 배선 무변경.

## 현재 4벌 위치 (실측 확인)

| 전략 | 파일:라인 | 로그 접두사 |
|------|-----------|-------------|
| bfb | `bull_flag_breakout.py:1094` | `[bfb]` |
| ltv | `long_tail_volatility.py:134` | `[ltv]` |
| vcp | `vcp_breakout.py:1179` | `[vcp]` |
| vb  | `volatility_breakout.py:1035` | `[vb]` |

**ltv/vb 접두사 = tdd-engineer 소스 실측 확인 완료** (`[ltv]`/`[vb]`, 카드의 "추정" 아님).

본문 4벌 동일 (접두사만 상이):
```python
async def _refine_cooldown_business_days(self, ticker: str) -> None:
    days = self.config.params["reentry_cooldown_days"]
    today = datetime.now(KST).date()
    try:
        accurate = await add_business_days(today, days)
        self._cooldown_until[ticker] = accurate
    except Exception:
        logger.warning("[bfb] 영업일 정정 실패 (ticker=%s) — 근사값 유지", ticker)
```

## Green 계약

1. **base 단일 정의** `StrategyBase._refine_cooldown_business_days(self, ticker)` async:
   ```python
   async def _refine_cooldown_business_days(self, ticker: str) -> None:
       days = self.config.params["reentry_cooldown_days"]
       today = datetime.now(KST).date()
       try:
           accurate = await add_business_days(today, days)
           self._cooldown_until[ticker] = accurate
       except Exception:
           logger.warning("%s 영업일 정정 실패 (ticker=%s) — 근사값 유지",
                          self._COOLDOWN_LOG_LABEL, ticker)
   ```
   - label `"[bfb]"`(대괄호 포함) + 형식 `"%s 영업일 정정 실패..."` = 현행 `"[bfb] 영업일 정정 실패..."` 와 **byte-identical**.
2. **ClassVar** `StrategyBase._COOLDOWN_LOG_LABEL: ClassVar[str | None] = None` (`_HIGH_RECOVER_LABEL` 선례 동형).
3. **4 전략 override**: bfb=`"[bfb]"` / vcp=`"[vcp]"` / ltv=`"[ltv]"` / vb=`"[vb]"`.
4. **4 전략 소스에서 `def _refine_cooldown_business_days` 제거** (base 위임만).
5. **`register_cooldown_after_exit` 는 승격 금지** — bfb 변형은 `_breakout_first_seen.pop(ticker, None)` 동반이라 다른 3벌과 byte-identical 아님. A3 는 `_refine_cooldown_business_days` **만** 승격.
6. **`on_position_closed` 무변경** — 각 전략이 계속 `register_cooldown_after_exit` + `asyncio.create_task(self._refine_cooldown_business_days(ticker))` 호출 (호출 = 상속 메서드, 정의만 이동).

## ⚠️ 패치 seam 계약 (필독 — 위반 시 cycle191/201/213 회귀)

base 승격 후에도 `add_business_days` 를 **concrete 전략 모듈 네임스페이스로 resolve** 해야 한다 (stale_manager `sys.modules[type(self).__module__]` 패턴, 사이클 61 D-1 AST 선례):

```python
import sys
_mod = sys.modules.get(type(self).__module__)
_add_bd = getattr(_mod, "add_business_days", None) or _fallback_import()
accurate = await _add_bd(today, days)
```

- 이유: 기존 cycle191/201/213 테스트 + 본 A3 행위 테스트가 **모두 전략 모듈 바인딩**(`monkeypatch.setattr(<strategy_mod>, "add_business_days", ...)`)을 패치한다.
- base 가 `strategy_base.add_business_days` 나 `src.api.condition.add_business_days` 를 **직접** 참조하면 이 seam 이 깨져 → 요구 6 위반(cycle191/201/213 FAIL) + A3-3/A3-4 행위 테스트 동반 FAIL.
- 각 전략 모듈의 `from src.api.condition import add_business_days` **import 유지** (resolve 소스 + 패치 타깃).

## 8영역 무접촉 / FREEZE·다크런치 무관

- 전략 파일 + `strategy_base.py` 만 접촉. realtime/risk/order_engine/scanner(매수)/session/auth/api.order = diff 0.
- kojiro FREEZE·VCP/BFB 다크런치 무관 (kojiro/donchian/momentum 은 cooldown 미보유 = 상속만·호출 0, VCP/BFB check_buy/exit 본체 byte 보존).

## Red 실행 결과 (현 코드)

`pytest tests/unit/engine/strategies/test_refactor_a3_cooldown_base.py` → **5 failed, 12 passed**

**truly-RED (승격 후 PASS)** 5:
- `test_a3_1_no_duplicate_refine_definition_in_strategy_files` — 4벌 def 존재.
- `test_a3_2_base_has_refine_and_is_async` — base 미정의.
- `test_a3_4_cooldown_log_label_classvar_per_strategy` — ClassVar 부재.
- `test_a3_4_base_cooldown_log_label_default_none` — ClassVar 부재.
- `test_a3_5_non_cooldown_strategies_inherit_base_refine` — base 미정의 → kojiro/donchian/momentum 상속 없음.

**행위 보존·scope 가드 (양 상태 PASS)** 12: A3-2b 상속·A3-3 성공 x4·A3-4 실패+접두사 x4·A3-5b/5c 소스 배선 부재·A3-6 register 잔존.

## 회귀 baseline (Green 후 재실행 = 요구 6)

- `test_cycle191_cooldown_wiring.py` + `test_cycle201_vb_reentry_cooldown.py` + `test_cycle213_ltv_reentry_cooldown.py` = **39 passed** (현재).
- `test_cycle191_cooldown_ast.py` + `test_cycle201_vb_cooldown_ast.py` + `test_cycle213_ltv_cooldown_ast.py` = **17 passed** (현재). G-191/201/213 NO-DAILY-RESET + `on_position_closed` register 호출 가드 = 승격 무영향(정의 아닌 호출 검증).
