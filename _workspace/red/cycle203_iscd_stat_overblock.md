# 사이클 203 Red — VCP funnel step3 과차단 시정 (iscd_stat_cls_code 차단 체크 완전 제거)

## 진단 (확정)
`src/engine/scanner.py::_is_master_blocked_for_entry` **L2565-2568**:
```python
# iscd_stat_cls_code: KIS 정본 = "55" 정상 거래중. 빈 문자열은 graceful 통과.
iscd_stat = (raw.get("iscd_stat_cls_code") or "").strip()
if iscd_stat and iscd_stat != "55":
    return True, f"종목상태 비정상 (iscd_stat_cls_code={iscd_stat}, FHKST)"
```
"55만 정상" 가정이 틀림. 운영 DB 3,576종목 실측 (자문 `_workspace/domain_consult/cycle203_iscd_stat_overblock.md`):
- **57 = 정상/그외 (91%, 3,270종목 전부 거래)** → 현 코드가 이 91%를 오차단
- 58 = 현재가0 데이터 신선도 잔재 (정상 대형주 혼입, 거래정지 아님)
- 51 = 정상 (ETF·스팩·우선주 — "관리종목" 가설 실측 반증)
- 52 = 투자위험 (유니버스 0건, 이론상만)
- 53/54/59 = 시장경고 계열 → 전용 플래그(mrkt_warn_cls_code / short_over_yn)가 **실측 100% 커버**

결과: KOSPI200∪KOSDAQ150 정상 대형주 60~75% 오차단 (VCP 182→63).
KIS 는 iscd_stat_cls_code 코드값 의미를 공식 배포하지 않음 → 하드코딩 블록리스트는 미래 회귀 위험.

## 확정 시정 (backend-dev 지시)
1. **`scanner.py` L2565-2568 완전 삭제** (iscd_stat_cls_code 차단 4줄 제거).
2. docstring 정정: L2529 `- sltr_yn (FHKST) / iscd_stat_cls_code != "55" / temp_stop_yn` →
   `- sltr_yn (FHKST) / temp_stop_yn` (iscd 문구 제거, AST 가드 G-203-9 통과 의무).
   L2527 `사이클 155 (raw=FHKST01010100, 6건)` → `5건`, L2519 docstring `13건` 서술은
   `12건` (129 7 + 155 5)으로 정정 권장 (문구 정합, 필수는 iscd 문자열 0건).
3. **전용 플래그 12건 전부 유지** (master_raw: trht_yn / sltr_yn / mang_issu_yn / ssts_hot_yn /
   stange_runup_yn / mrkt_alrm_cls_code≥"02" / invt_alrm_yn + raw: mrkt_warn_cls_code≥"01" /
   invt_caful_yn / short_over_yn / sltr_yn / temp_stop_yn). **차단 로직 본체 변경 0** — iscd 분기만 제거.
4. **merge/적재는 불변** — `condition.py::_FHKST_MERGE_KEYS` 의 `iscd_stat_cls_code` 는 유지
   (raw 에 값은 계속 저장, 단지 차단 기준으로 쓰지 않음). `test_cycle155_ast_merge_keys.py` 불변 확인.

## 신규 Red 파일
- `tests/unit/engine/scanner/test_cycle203_iscd_stat_no_overblock.py` (G-203-1~8, 8케이스)
- `tests/unit/ast/test_cycle203_ast_no_iscd_block.py` (G-203-9 + 9b, 2케이스)

## Red 유효성 (현재 코드 실측)
| 케이스 | 내용 | 현재 코드 |
|---|---|---|
| G-203-1 | iscd=57 정상주 un-block | **FAIL** ✅ |
| G-203-2 | iscd=58 / 51 정상주 un-block | **FAIL** ✅ |
| G-203-3 | 거래정지 (trht_yn) 차단 | PASS (불변식) |
| G-203-4 | 관리종목 (mang_issu_yn) 차단 | PASS (불변식) |
| G-203-5 | 시장경고 (mrkt_warn, 52/53 커버) 차단 | PASS (불변식) |
| G-203-6 | 단기과열 (short_over_yn, 59 커버) 차단 | PASS (불변식) |
| G-203-7 | 투자유의/정리매매/임시정지 차단 | PASS (불변식) |
| G-203-8 | iscd=52 단독(mrkt_warn 부재) un-block (문서화 한계) | **FAIL** ✅ |
| G-203-9 | AST: 함수 영역 iscd_stat_cls_code 0건 | **FAIL** ✅ |
| G-203-9b | 함수 자체 존치 (전용 플래그 보존) | PASS (구조) |

→ 현재 코드: **4 FAIL / 6 PASS**. 시정 적용 후: **10 PASS** (임시 patch 검증 완료).

## 의미 전환 목록 (사이클 66 K-2 패턴 — 임의 삭제 금지, 갱신/xfail)
시정 적용 시 아래 **4건 FAIL** (전부 iscd 를 "차단"으로 단언 = 사이클 203 이전 계약, 갱신 대상):

1. `tests/unit/engine/scanner/test_cycle155_block_13_keys.py::TestCycle155Block13Keys::test_g_155_block_1_fhkst_raw_6_keys`
   - L46-49 `iscd_stat_cls_code=51 → blocked "종목상태"` 단언이 문제. **부분 갱신**: 나머지 5키
     (mrkt_warn/invt_caful/short_over/sltr/temp_stop) 단언은 유지, iscd=51 블록 4줄만 제거하고
     "iscd 는 사이클 203에서 차단 제거 (5키 = raw 6→5)"로 갱신. 함수명/docstring "6 키"→"5 키".
   - 동 파일 L74-75 `{"iscd_stat_cls_code":"55"} → 통과` 단언(test_g_155_block_2)은 **PASS 유지**
     (55도 시정 후 여전히 통과 — 무해). L88 빈 문자열 graceful(block_3)도 PASS 유지.

2. `tests/unit/engine/strategies/test_cycle157_master_block_hook_and_vcp_listfilter.py::TestG157HookMomentumScanStocks::test_g157_hook_momentum_scan_stocks_calls_master_block`
   - L261/L273 `iscd=57 → "거래정지" 차단 기대`가 문제 (실측 57=정상). **갱신**: 차단 종목 mock 을
     iscd=57 대신 실제 차단 플래그로 교체 (예 `raw={"trht_yn":"Y"}` 또는 `master_raw={"trht_yn":"Y"}`).
     정상 종목(222222)은 iscd=55 또는 57 유지. "거래정지" 주석 정정.

3. `...::TestG157HookProtected::test_g157_hook_protected_tickers_pass_through`
   - L299-302/L315 비보유 차단 종목(111111)을 iscd=57 로 둠 → 시정 후 통과되어 `not in survived` 실패.
     **갱신**: 111111 을 실제 차단 플래그(trht_yn=Y 등)로 교체. 보호 종목(005935) 보호 단언은 불변 유지.

4. `...::TestG157HookExcludedFormat::test_g157_hook_excluded_format_dict_ticker_name_reason`
   - L369-371/L384 excluded 종목(555555)을 iscd=57 로 둠 → 시정 후 excluded 0건. **갱신**: 555555 를
     실제 차단 플래그로 교체 (excluded format 검증 의도 보존).

**불변 (갱신 불필요, 확인 완료)**:
- `tests/unit/ast/test_cycle155_ast_merge_keys.py` — iscd 를 **merge 키**로 단언 (적재 계약). 사이클 203은
  차단만 제거하고 merge 유지 → **PASS 불변**.
- `tests/unit/engine/scanner/test_cycle155_safety.py` — iscd 차단 미단언. **PASS 불변**.
- `tests/unit/api/test_cycle155_merge_35_keys.py` — iscd merge/적재 단언. **PASS 불변** (7 PASS).

## 매매 안전성
- scanner 매수 진입 *전* 영역 (사이클 38). `git diff -- src/engine/risk.py src/engine/order_engine.py
  src/realtime/ src/auth/ src/api/order.py` = 0 라인 의무.
- 사이클 32 R4 보유/익일청산 절대 보호 = `apply_master_block_filter` 의 protected_tickers 담당
  (이 함수 밖, 불변). `_is_master_blocked_for_entry` 는 순수 함수(async 아님, DB 무관).
- 방향 = 매수 유니버스 **확대** (오차단 제거) — 위험 종목은 전용 플래그로 100% 커버 유지.

## backend-dev 인계 요약
- scanner.py L2565-2568 삭제 + docstring L2519/L2527/L2529 정정.
- 위 의미 전환 4건 갱신 (iscd=57 차단 mock → 실제 차단 플래그 교체 + block_13_keys 부분 갱신).
- 검증: cycle203 10 PASS + 155/157/155_ast/155_safety 회귀 0 + api/155_merge 7 PASS +
  매매 안전성 8영역 diff 0 + build_index 재생성.
