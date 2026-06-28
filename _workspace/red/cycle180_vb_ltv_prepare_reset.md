# Red 명세 — 사이클 180: VB/LTV `prepare()` 시작부 3-dict 리셋 (strat-1 HIGH/CONFIRMED)

- 작성: tdd-engineer (Red 전담)
- 자문 근거: `_workspace/domain_consult/cycle180_vb_ltv_prepare_reset.md` (5 의제 전부 GO + §7 가드 taxonomy)
- 산출물: 본 md + 테스트 2 파일 (아래)
- **구현(Green) 금지** — backend-dev 가 별도. Red/Green 독립성 보존이 본 사이클 핵심.

---

## 1. 확정 결함 (코드 정독 + 직접 검증)

VB(`src/engine/strategies/volatility_breakout.py`) / LTV(`src/engine/strategies/long_tail_volatility.py`)
`prepare()` 가 `self._targets` / `self._open_confirmed` / `self._prev_price` 를 **시작부에서 비우지 않는다.**

- 3-dict 는 prepare 의 종목별 *재할당* (VB L267/279, LTV L293/304) 외에는 프로세스 생애 동안 절대 비워지지 않음.
- `scheduler._reset_daily_state()` (L3804~L3818, 20:10 유일 일일 리셋) 는 `strategy.state.*` + order_engine
  추적 + scanner 글로벌 dict 만 비우고, **전략 인스턴스 필드 `_targets`/`_open_confirmed`/`_prev_price`/
  `_limit_up_reached` 는 단 한 줄도 건드리지 않음** (직접 grep 확정).
- 전일 universe 에서 빠진 종목이 영원히 잔존 → `_scanned_tickers = list(self._targets.keys())`
  (VB L293/LTV L318) → 구독 → 틱 → `check_buy_signal` 이 stale `_targets[전일종목]` 의 전일 open_price/
  target_offset 으로 매수 판정 → 절대규칙 "돌파 = 이전틱 < 기준가 AND 현재틱 >= 기준가" 의 **기준가 오염**.

형제 전략(donchian/BFB/VCP)은 이미 prepare 시작부 `self._candidates={}` 리셋 → 본 사이클은 **5 전략 중
3 전략이 채택한 컨벤션으로 VB/LTV 를 정합** (신규 패턴 아님, 회귀 위험 기준선 낮음, 자문 §2-확정2).

## 2. 시정 명세 (Green 이 구현 — Red 가 강제하는 것)

VB + LTV `prepare()` **시작부**(첫 `await self._scan_universe()` 호출 *전*, `_empty_scan_stats()`/
`_reset_funnel_steps` 부근 = VB L126/LTV L134 직전 또는 인접)에 정확히 3줄씩:

```python
self._targets.clear()
self._open_confirmed.clear()
self._prev_price.clear()
```

- **제외 (절대 clear/리셋 금지)**: `_limit_up_reached`(LTV), `_next_day_clear_pending`(both).
  - `_limit_up_reached` clear 시 → 상한가 익일청산 종목이 15:20 강제청산 오편입 + -3% 손절 모드 격하
    (롱테일 핵심 수익 구조 파괴, 자문 §의제2 절대 제외).
  - `_next_day_clear_pending` 리셋 시 → 익일청산 race 가드 무력화 (무한 신호 폭주 위험).

## 3. 테스트 파일

| 파일 | 그룹 | 현재(미시정) |
|------|------|-------------|
| `tests/unit/engine/strategies/test_cycle180_vb_ltv_prepare_reset.py` | A(결함 재현) + B(SAFETY) | A FAIL / B PASS |
| `tests/unit/ast/test_cycle180_prepare_reset_ast.py` | C(정적) + D(영속) | C.7/C.9 FAIL / C.8·D PASS |

mock 패턴 (cycle158/cycle173 답습): `_scan_universe`/`_apply_master_block_filter_in_prepare`/
`src.db.stock_master_daily.get_recent_daily_normalized`/`asyncio.sleep` 를 patch.
일봉 `_valid_candles()` = **날짜 의존 제거** (고정 연도 2024, cycle176 hotfix 교훈) → prev_idx=0 안정.

## 4. 가드 ID ↔ 매핑 (domain-expert §7 taxonomy 정합)

### A. 핵심 결함 재현 (현재 FAIL = Red 증명, 시정 후 PASS)

| 가드 ID | 테스트 | 검증 |
|---------|--------|------|
| G-180-EMPTY-GATE-VB | `test_g_180_empty_gate_vb_targets_drop_stale` | 2차 prepare 후 `_targets` 전일 A 미포함 + B 만 |
| G-180-EMPTY-GATE-VB-AUX | `test_g_180_empty_gate_vb_open_confirmed_prev_price_drop_stale` | `_open_confirmed`/`_prev_price` 전일 A 잔존 0 |
| G-180-EMPTY-GATE-LTV | `test_g_180_empty_gate_ltv_targets_drop_stale` | LTV `_targets` 전일 A 미포함 + B 만 |
| G-180-EMPTY-GATE-LTV-AUX | `test_g_180_empty_gate_ltv_open_confirmed_prev_price_drop_stale` | LTV aux 2-dict 전일 A 잔존 0 |
| G-180-SCANNED-VB | `test_g_180_scanned_vb_excludes_stale` | `get_scanned_tickers()` 전일 A 부재 |
| G-180-SCANNED-LTV | `test_g_180_scanned_ltv_excludes_stale` | LTV 동일 |
| G-180-STALE-BUY-VB | `test_g_180_stale_buy_vb_blocked` | 전일 X stale target 매수 0건 (현재 s2==BUY) |
| G-180-STALE-BUY-LTV | `test_g_180_stale_buy_ltv_blocked` | LTV 동일 (min_prdy_rate=0 격리) |
| G-180-AST-CLEAR-PRESENT | `test_g_180_ast_clear_present[3 dict × 2 전략]` | prepare AST 에 `self.<attr>.clear()` ≥1 |
| G-180-AST-CLEAR-POSITION | `test_g_180_ast_clear_before_scan_universe[2 전략]` | 3 clear 가 첫 `_scan_universe()` *전* lineno |

### B+C.8+D. SAFETY/영속 가드 (현재도 PASS, 시정 후에도 PASS 의무)

| 가드 ID | 테스트 | 검증 |
|---------|--------|------|
| G-180-LIMITUP-EXCLUDE | `test_g_180_limitup_exclude_ltv_preserved` | prepare 후 `_limit_up_reached` 보존 |
| G-180-NDC-EXCLUDE-VB/LTV | `test_g_180_ndc_exclude_{vb,ltv}_preserved` | prepare 후 `_next_day_clear_pending` True 유지 |
| G-180-EXIT-PATH-VB/LTV | `test_g_180_exit_path_{vb,ltv}_stop_loss_after_prepare` | _targets clear 돼도 손절/15:20 강제청산 정상 |
| G-180-AST-FORBIDDEN-ABSENT | `test_g_180_ast_forbidden_reset_absent[2 attr × 2 전략]` | prepare AST 에 `_limit_up_reached.clear()` + `_next_day_clear_pending=` 0건 |
| G-180-AST-EXIT-NO-SIDE-EFFECT | `test_g_180_ast_exit_path_no_reset_no_funnel[2 fn × 2 전략]` | check_exit/force_clear 본체 clear/funnel hook 0건 |
| G-180-AST-NO-RISK-IMPORT | `test_g_180_ast_no_risk_order_import[2 전략]` | risk/order_engine import 0건 |

## 5. Red 실행 결과 (현재 미시정 코드)

```
python -m pytest tests/unit/engine/strategies/test_cycle180_vb_ltv_prepare_reset.py \
                 tests/unit/ast/test_cycle180_prepare_reset_ast.py -q
→ 16 failed, 15 passed in 0.36s
```

- **16 FAIL (Red 증명)** = A 그룹 8 (EMPTY-GATE 4 + SCANNED 2 + STALE-BUY 2) + C.7 6 (clear-present 3×2)
  + C.9 2 (clear-position 2). 모두 "현재 코드에 시정 부재" 가 원인.
  - 대표 메시지: `VB 2차 prepare 후 전일 종목 ['100001','100002'] 가 _targets 에 잔존:
    {'200001','200002','100002','100001'}` / `assert <Signal.BUY> == <Signal.NONE>` (stale target 매수).
  - 1차 prepare "전제(precondition)" assert 는 통과 → mock 셋업 정상 (false-fail 아님).
- **15 PASS (SAFETY/영속 가드, 현재도 통과)** = B 그룹 5 (LIMITUP 1 + NDC 2 + EXIT-PATH 2) + C.8 4
  (forbidden-absent 2×2) + D 6 (exit-no-side-effect 4 + no-risk-import 2). 시정 후에도 PASS 의무
  (Green 이 `_limit_up_reached.clear()` 또는 `_next_day_clear_pending=False` 를 prepare 에 잘못
  추가하면 C.8 즉시 FAIL = 영구 차단).

## 6. Green-readiness 검증 (src/ 미변경, 래퍼 모사)

prepare 시작부 3-dict clear 를 인스턴스 래퍼로 모사(`_targets.clear()` 등 후 원본 prepare 호출) →
A 그룹 전부 PASS 전환 확인:

```
GREEN A.1 targets: {'200002','200001'}      # 전일 A 소멸, 당일 B 만
GREEN A.3 stale buy: Signal.NONE Signal.NONE # stale target 매수 차단
GREEN LTV A.1 targets: {'200001'}
GREEN B.4 limit_up preserved under fix: OK   # SAFETY 유지
ALL GREEN-READINESS CHECKS PASS
```

→ Red→Green 전환 논리 보장. backend-dev 는 VB/LTV prepare 시작부 3줄 추가만 하면 됨.

## 7. backend-dev 인계 (Green 지시)

1. VB `volatility_breakout.py::prepare` — `stats = _empty_scan_stats()` ~ `self._reset_funnel_steps(VB_FUNNEL_STAGES)`
   (L126~L129) 직후, 첫 `tickers = await self._scan_universe()` (L133) *전* 에 3줄 추가.
2. LTV `long_tail_volatility.py::prepare` — L134~L137 직후, L141 *전* 에 3줄 추가.
3. `_limit_up_reached` / `_next_day_clear_pending` 절대 미참조.
4. 다른 영역(check_exit_signal/check_force_clear/risk/order_engine) 변경 0.

## 8. tester 인계 (사이클 종료 시)

- 영향 인덱스: `python tools/test_impact/build_index.py` + `manual_overrides.yaml` (전략 모듈 동적 의존).
- 합성 시계열 회귀(자문 §7): 전일 universe A → 당일 universe B + A 전일 target 돌파 틱 주입 →
  시정 적용 시 A 매수 0건 / 미적용 시 A 매수 발생 (결함→시정 효과 직접 입증) — `test_g_180_stale_buy_*` 가
  단위 수준에서 이미 커버.
- 운영 검증 D+1: 09:00:05~09:35 VB/LTV `get_scanned_tickers()` 가 당일 universe 와 일치(전일 잔존 0).
