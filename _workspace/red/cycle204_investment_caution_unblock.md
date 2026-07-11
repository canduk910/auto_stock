# 사이클 204 — 투자주의 차단 해제 (HIGH 매매 기회 — 급등주 복원)

**명세 출처**: `_workspace/domain_consult/cycle204_investment_caution_unblock.md`
(KIS 삼각검증 00=정상/01=투자주의/02=투자경고/03=투자위험 + 차단 index 9종목 전부 우량 대형주 실증)
**사용자 통찰**: 급등 → 투자주의 지정 → 돌파전략 후보에서 제거되는 역설
**행위**: `scanner._is_master_blocked_for_entry` raw 분기에서 투자주의(mrkt_warn "01") + 투자유의(invt_caful_yn) 차단 해제. 투자경고(02)/투자위험(03) + 급등 3플래그는 유지.

## Red

### 신규 테스트 파일
- `tests/unit/engine/scanner/test_cycle204_investment_caution_unblock.py` (7 케이스, 순수 함수 — mock 없음)
- `tests/unit/ast/test_cycle204_ast_no_caution_block.py` (3 케이스 — 함수 영역 한정 AST)

### 케이스 목록 및 현재 코드 판정
| 케이스 | 성격 | 현재 코드 | 기대(Green) | Red? |
|--------|------|-----------|-------------|------|
| G-204-1 mrkt_warn "01" un-block | 핵심 | (True,"FHKST 시장경고 (01)") | (False,"") | **FAIL** |
| G-204-2 invt_caful un-block | 핵심 | (True,"투자유의...") | (False,"") | **FAIL** |
| G-204-3 mrkt_warn "02" blocked | SAFETY 불변 | blocked | blocked | PASS |
| G-204-4 mrkt_warn "03" blocked | SAFETY 불변 | blocked | blocked | PASS |
| G-204-5 급등 3플래그 blocked | SAFETY 불변 | blocked | blocked | PASS |
| G-204-6 기타 전용 플래그 blocked | SAFETY 불변 | blocked | blocked | PASS |
| G-204-7 warn"01"+단기과열 → 단기과열 차단 | 경계 | (True,"시장경고 (01)") | (True,"단기과열...") | **FAIL** |
| G-204-8 AST invt_caful 참조 0 | AST | 잔존 | 0건 | **FAIL** |
| G-204-8b AST mrkt_warn `>= "02"` | AST | `>= "01"` | `>= "02"` | **FAIL** |
| G-204-8c 함수 존치 | 구조 | 존재 | 존재 | PASS |

### 실행 결과 (Red 유효성)
```
pytest tests/unit/engine/scanner/test_cycle204_investment_caution_unblock.py tests/unit/ast/test_cycle204_ast_no_caution_block.py -q
> 5 failed, 5 passed
FAILED ... test_g_204_1_market_warn_01_unblock       (핵심)
FAILED ... test_g_204_2_invt_caful_unblock           (핵심)
FAILED ... test_g_204_7_warn01_with_runup_still_blocked  (경계 — reason=단기과열)
FAILED ... test_g_204_8_no_invt_caful_reference_in_block_func  (AST)
FAILED ... test_g_204_8b_market_warn_threshold_is_02  (AST)
```
명세 요구 "(1)(2)(8) FAIL + (3~7) PASS" 대비 — (7) 도 FAIL (더 강한 가드: 현재 warn "01" 이 먼저 매칭돼 reason 이 "시장경고"라 "단기과열" 단언 실패. Green 후 warn "01" un-block → short_over_yn 로 차단되어 reason=단기과열 PASS). (8b) 는 명세 (8) AST 를 2 분해.

## Green (backend-dev 구현 지시)

대상: `src/engine/scanner.py::_is_master_blocked_for_entry` **raw(FHKST01010100) 분기만**.

1. **L2562** mrkt_warn 임계 완화:
   ```python
   # 전 (사이클 155)
   if isinstance(mrkt_warn, str) and mrkt_warn >= "01" and mrkt_warn != "":
       return True, f"FHKST 시장경고 ({mrkt_warn})"
   # 후 (사이클 204) — 투자주의 01 해제, 투자경고 02/투자위험 03 유지
   if isinstance(mrkt_warn, str) and mrkt_warn >= "02":
       return True, f"FHKST 시장경고 ({mrkt_warn})"
   ```
   (`mrkt_warn != ""` 는 `>= "02"` 로 자연 흡수되나 제거는 선택 — 빈 문자열 `"" >= "02"` = False.)

2. **L2564-2565** 투자유의 차단 블록 **완전 삭제**:
   ```python
   # 삭제 대상
   if (raw.get("invt_caful_yn") or "").strip().upper() == "Y":
       return True, "투자유의 (invt_caful_yn=Y, FHKST)"
   ```

3. **docstring/주석 카운트 정정 (실측 라인)** — 차단 = master_raw 7 + raw 4 = **11건** (invt_caful 제거로 raw 5→4):
   - L2519 함수 요약 `"12건 매수 진입 차단 (사이클 129 7 + 사이클 155 5 확장)"` → `"11건 ... (사이클 129 7 + 사이클 155 4)"`.
   - L2527 `사이클 155 (raw=FHKST01010100, 5건):` → `4건`.
   - L2528 `mrkt_warn_cls_code >= "01" / invt_caful_yn / short_over_yn` → `mrkt_warn_cls_code >= "02" / short_over_yn` (invt_caful_yn 제거).
   - L2559 주석 `# 사이클 155 — FHKST01010100 raw 분기 (6 키).` → `(4 키).` (mrkt_warn02/short_over/sltr/temp_stop).
   - L649 주석 `_is_master_blocked_for_entry 12건 (master_raw 7 + raw 5)` → `11건 (master_raw 7 + raw 4)`.
   - `apply_master_block_filter` docstring: L2581 `1단계 진입 차단 12건 hook` + L2584 `12건 (master_raw 7 + raw 5)` + L2592 `사이클 155 raw 5건 = 12건` → 각 **11건 / raw 4** 로 정정.

4. **불변 (절대 건드리지 말 것)**: `condition.py::_FHKST_MERGE_KEYS` 의 `mrkt_warn_cls_code`/`invt_caful_yn` merge(적재) 는 **유지** — 차단만 완화. `test_cycle155_ast_merge_keys.py` 는 merge 키만 검사하므로 무변경 (transition 아님).

## 의미 전환 (Green 시 backend-dev 갱신 의무 — 임의 삭제 금지, 사이클 66 K-2 / 203 답습)

Green 후 아래 기존 단언이 새 정본과 모순 → **갱신** (invert to un-block + 카운트 정정). 삭제 아님.

### `tests/unit/engine/scanner/test_cycle155_block_13_keys.py`
- **`test_g_155_block_1_fhkst_raw_5_keys` L33-41**: mrkt_warn "01" 차단 단언(L34-36) + invt_caful "Y" 차단 단언(L39-41) → 사이클 204 un-block 으로 **갱신**. 방식 = "01" 케이스를 "02" 로 교체 + invt_caful 블록을 un-block 단언 `assert b is False` 로 invert (또는 cycle204 신규 파일이 이미 커버하므로 해당 두 블록 제거하되 docstring 에 "사이클 204 의미 전환 — cycle204 파일 참조" 명시). "5키" 카운트 문구 → "4키" (raw 분기 = mrkt_warn02/short_over/sltr/temp_stop, invt_caful 제거) 로 정정. 클래스명 `TestCycle155Block13Keys` + docstring "13건"→"11건"(master 7 + raw 4) 동반 정정.

### `tests/unit/engine/scanner/test_cycle203_iscd_stat_no_overblock.py`
- **`test_g_203_7_invt_caful_sltr_temp_stop_still_blocked` L104-116**: invt_caful "Y" 차단 단언(L106-108) → **갱신** (un-block `assert b is False`). 나머지 sltr/temp_stop 은 불변(유지). 메서드명/docstring 의 "투자유의" 문구 정정.
- **`test_g_203_5_market_warn_covers_52_53` L85-93**: 이미 mrkt_warn **"02"** 로 단언 → **무변경(PASS 유지)**. docstring L86 의 `>="01"` 문구만 `>="02"` 로 cosmetic 정정 권장 (기능 무관).

### 무변경 확인
- `test_cycle155_ast_merge_keys.py` — merge 키만 검사 (적재 유지) → **transition 아님**.
- `test_cycle204_*` 신규 파일 — Green 후 10 PASS 목표.

## 매매 안전성
- scanner 매수 진입 *전* 영역 (사이클 38). `_is_master_blocked_for_entry` = 순수 함수(async 아님, DB 무관).
- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/` = 0 라인 의무.
- 사이클 32 R4 (보유/익일청산 절대 보호) 무영향 — 본 함수는 진입 차단 판정만, 보호는 호출 사이트(`apply_master_block_filter`).

## Refactor
- 없음 (완화만). 영향 인덱스 재생성은 Green 확정 후.
