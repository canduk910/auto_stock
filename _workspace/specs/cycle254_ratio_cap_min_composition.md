# cycle254 명세 — 터틀 1주 폴백 랏에 ρ축 상한을 `min` 합성 (결정 ⑦ 개정)

- 작성 2026-09-05 (토) · 사용자 결정 "D3 권고 B" (09-05 12:5x)
- 자문 정본: `_workspace/domain_consult/cycle254_turtle_fallback_rho_exposure.md` (권고 B)
- 승인 범위: `src/engine/strategy_base.py` **단독**(8영역 아님) + 테스트 + 정본 문서 3.
  8영역·`scheduler.py`·`turtle_sizing.py`·`portfolio_risk.py`·전략 7파일 **diff 0**.
- 배포 창: 장외(토/일) — 보유 무관. D+1 판독 = 월 09-07.

## 0. 선결 확인 (F-9 실재 판정) — 배포 전 필수

09-05 아침 `[ratio_cap_config]` 판독(메모리 `project_0904_night_deploys`)에서 donchian·kojiro 는
`sizing_mode=turtle cap=backstop` = 터틀 활성 = **F-9 실재**. 구현 착수 전 `system_logs` 로
한 번 더 확인하고 이 문단에 실측 행을 붙인다. 두 전략 다 `cap=on` 이면 **이 사이클은 하지 않는다**
(워크리스트 "터틀 전환 시 선결" 로 재분류).

## 1. 무엇을 바꾸나 (행위)

`_apply_ratio_notional_cap` 의 조기탈출 **한 조건**만 좁힌다.

```python
# 현행 (결정 ⑦ — 상호배타)
if governs:
    if gov_reason == "probe_error":
        self._emit_ratio_cap_skipped(ticker, "k_axis_probe_error", final, current_price)
    return final

# cycle254 (min 합성) — 판정 실패 fail-open 만 남긴다
if governs and gov_reason == "probe_error":
    self._emit_ratio_cap_skipped(ticker, "k_axis_probe_error", final, current_price)
    return final
```

- `_lot_units_cap_governs(ticker)` **호출은 그대로 남긴다**(AST G-245-4 가 호출 존재를 핀 + `probe_error` fail-open 이 F-10d 계약).
- 그 아래 `cap <= 0` 스킵·`cap_qty = cutoff // price`·`final <= cap_qty` 통과·`_emit_ratio_notional_blocked`·`return cap_qty` 는 **byte 동일**.
- 관문 순서(폴백 → K캡 → `[oversized_fallback]` → ρ캡 → return) 무변경. 반환 타입 `int` 유지.
- `_emit_ratio_cap_config` 의 라벨: `mode == "turtle"` 이면 `"backstop"` → **`"on"`** 으로 통일(분기 자체를 지운다 — `k is None` 이면 off, 그 외 on). docstring 의 3라벨 표를 2라벨로.

### 왜 이 자리에서만 실효하나 (항등식)
- 사이즈드 터틀 랏: `compute_unit_qty_guarded` 가 `min(qty, int(B×ρ)//P)` 를 **무조건** 적용 ⇒ 명목 ≤ B×ρ ≤ K_ρ×B×ρ ⇒ `final <= cap_qty` 로 통과. **수량 불변**.
- PR 낙하 랏 `int(B×ρ)//P`: 정의상 같다. **불변**.
- 1주 폴백 랏(`P > ρB`): `cap_qty = int(K_ρ × int(B×ρ)) // P` 가 0 이면 **차단(0주)**, 아니면 1 유지.
- 자문 격자 1,728 조합 실측: 차이 122 = 전부 1주 폴백 · 전부 축소(1→0) · 증가 0. 실측 11랏 대입 변경 0.

## 2. 붉어지는 기존 테스트 (정확히 2건, 둘 다 결정 ⑦의 직접 귀결 — 개정)

| 테스트 | 현행 단언 | 개정 |
|---|---|---|
| `test_f245_7b_turtle_over_rho_cutoff_is_not_cut` (`tests/unit/engine/test_cycle245_ratio_notional_cap.py:446`) | `qty == 1` · BLOCKED 0 · `cap=backstop` | `qty == 0` · `[ratio_notional_blocked] … path=fallback req_qty=1 capped_qty=0 cutoff=195150` 정확 1행 · `cap=on` · `[oversized_fallback]` 1행 유지(관측이 ρ캡 **앞**) |
| `test_f245_16b_config_marker_backstop_label` (:900) | 문자열 `cap=backstop` | `cap=on` (나머지 필드 byte 동일) |

- `test_f245_10d_governs_probe_error_is_fail_open`(:585) 은 **무수정 통과해야 한다** — 블록째 지우면 붉어진다(§1 diff 가 조기 반환을 남기는 이유).
- cycle242 `test_cycle242_fallback_notional_cap.py` **97/0 무수정**, cycle233 `test_cycle233_oversized_fallback.py` 무수정.
- AST `test_cycle245_ast_ratio_notional_cap.py` 전건 무수정 통과(G-245-4 는 호출 존재만 핀).
- 라벨 상수/문자열 `"backstop"` 이 `strategy_base.py` 에서 **0건**이 되어야 한다(신규 AST 가드).

## 3. 신규 회귀 (tdd-engineer — 파일 `tests/unit/engine/test_cycle254_ratio_cap_min_composition.py` + AST 1파일)

- **F-9a** `test_f245_7b` 개정본(위 표) — donchian `_dc()` B=390,300 · ATR 3,000 · P 300,000.
- **F-9b 사이즈드 터틀 랏 무접촉** — `compute_unit_qty_guarded` 가 만든 qty ≥ 2 랏은 `min` 합성 전후 동일. 실증은 격자로: P ∈ {5k,10k,20k,50k}, ATR% ∈ {1,2,4,8}, B ∈ {390,300; 1,000,000} 에서 HEAD 경로(모의: `governs` 조기탈출을 monkeypatch 로 복원) vs cycle254 수량 일치.
- **F-9c 격자 차분 회귀** — 차이 집합 == `(HEAD수량 == 1) ∧ (P > int(K_ρ × int(B × ρ)))` 정확 일치 + **수량 증가 0** 단언. 최소 500 조합.
- **F-9d** probe_error fail-open — `_lot_units_cap_governs` 를 `(True, "probe_error")` 로 패치하면 수량 불변 + `[ratio_cap_skipped] reason=k_axis_probe_error` 1행 (F-10d 와 별개 파일에도 1건 두어 이 사이클이 그 계약을 안다는 것을 고정).
- **F-9e** K축 결과 불변 — `[fallback_notional_capped]` 발화 조건·수량이 turtle 랏에서 byte 동일(cycle242 픽스처 재사용).
- **F-9f 경계** — `final × P == cutoff` 통과(경계 포함), `+1원` 차단. 폴백 경로에서.
- **F-9g kojiro** — kojiro 인스턴스로 1주 폴백 P=400,000·cutoff 323,952 → 0 + BLOCKED 1행(`strategy=kojiro`).
- **AST G-254-1** `strategy_base.py` 에 문자열 리터럴 `"backstop"` 0건.
- **AST G-254-2** `_apply_ratio_notional_cap` 본체에 `governs` 를 단독 조건으로 쓰는 `if governs:` 가 0건이고, `gov_reason == "probe_error"` 비교가 존재(BoolOp And 안). 뮤테이션 "조기탈출 복원" 을 구조로도 막는다.
- **AST G-254-3** `_lot_units_cap_governs(` 호출이 `_apply_ratio_notional_cap` 안에 존재(G-245-4 와 중복이지만 이 사이클 파일에도 둔다 — 삭제 뮤테이션 검출 분산).

## 4. 뮤테이션 표적 (tester)
1. `governs and gov_reason == "probe_error"` → `governs` (결정 ⑦ 회귀) — F-9a·G-254-2 가 잡아야 한다.
2. `==` → `!=` (fail-closed 반전) — F-9d.
3. `final <= cap_qty` → `<` — F-9f.
4. `cap_state = "on"` → `"backstop"` — 16b 개정 + G-254-1.
5. `_lot_units_cap_governs` 호출 삭제 — G-245-4/G-254-3.
6. `cap_qty = cutoff // current_price` → `cap // current_price` — F-9a(0 은 같으니 F-9f 경계로).

## 5. 정본 문서 동반 개정 (Green 단계에서 같이)
- 루트 `CLAUDE.md` 「랏 명목 ρ축 상한」 문단: "두 캡은 상호배타 — `min` 합성 없음" → "K축 심사 랏도 ρ축이 **`min` 으로 후심사**한다(cycle254). 사이즈드 터틀·PR 낙하 랏은 항등식으로 무접촉, 실효는 1주 폴백뿐". "항등식 … ρ축이 심사한 랏 한정 / 잔여 노출 kojiro 3.86배·donchian 5.00배 / 후속 F-9" 문장 삭제·정정. 하네스 표 1행 추가(15행 유지 — 가장 오래된 1행 제거) + `docs/HARNESS_CHANGELOG.md` append.
- `_workspace/00_leader_trading_rules.md:57~65`: 같은 문장 + 「잔여 노출(명시)」 블록 → "닫힘(cycle254)".
- `src/engine/strategy_base.py` `_apply_budget_limit` docstring "상호배타" 2곳 + `_emit_ratio_cap_config` docstring 라벨 표.
- cycle245 스펙(`_workspace/specs/` 의 cycle245 문서가 있으면) §3-3·§3-7b·R7 에 "cycle254 로 개정" 주석 1줄씩(본문 재작성 금지 — 이력).
- `_workspace/00_URGENT_WORKLIST.md` D3 행 → 완료 + F-9 종결.

## 6. D+1 판독 (월 09-07, `system_logs` 직접 조회 — 20:10 리포트는 INFO 마커 미도달)
| # | 서명 | 기대 |
|---|---|---|
| 1 | `[ratio_cap_config] strategy=donchian_swing sizing_mode=turtle cap=on k=2.50 … cutoff_price=195150` | 1행 (`backstop` 잔존 = 미반영) |
| 2 | `[ratio_cap_config] strategy=kojiro … cap=on … cutoff_price=323952` | 1행 (387,320 이면 DB `position_ratio` 0.20 = 08-08 지혈 롤백 의심) |
| 3 | `[ratio_notional_blocked] strategy=donchian_swing\|kojiro path=fallback` | 0건(나오면 F-9 첫 실측 표본 — ticker·price·ATR% 기록) |
| 4 | `[fallback_notional_capped]` 건수 | 배포 전과 동일(변하면 K축 접촉 = 롤백) |
| 5 | `[ratio_cap_skipped] reason=k_axis_probe_error` | 0건 |
| 6 | donchian·kojiro 매수 건수 | 직전 5영업일 평균 대비 감소 0 |
| 7 | `[oversized_fallback]` 건수 | 동일(ρ캡 **앞**에서 발화) |

⚠️ 의미 전환 2 — `cap=backstop` → `cap=on` 라벨 / R7 자기검증 반전: 터틀 행에서 `[oversized_fallback] ratio > k` 인데 같은 (전략, ticker, 일자)에 `[ratio_notional_blocked]` 도 `[ratio_cap_skipped]` 도 없으면 **캡 우회 = 결함**. 배포 전후 같은 grep 합산 금지.

## 7. 롤백
- 코드 롤백 불필요 — 해당 전략 `max_lot_ratio_mult = 20.0` (PUT 즉시 / SQL 은 다음 재시작). K_ρ 상한 20.0 이면 cutoff 가 P 를 넘어 1주 폴백도 통과.
- 이번 변경은 **수량을 늘리지 않는다**(min). 보유 8종목 청산 규약 무접촉(`check_exit_signal` diff 0).
