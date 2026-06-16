# 사이클 155 — KIS API 미관리 데이터 통합 (HIGH+MEDIUM 40 키 일괄)

> team-leader 발주 작업 지시서. tdd-engineer Red → backend-dev Green → tester verify chain.
> 사용자 결정 영속: Q1=B / Q2=A / Q3=A / Q4=A / Q5=A / Q6=A.

## 1. 명세 (사용자 verbatim 영속)

### 통합 범위 (40 키)

**A. FHKST01010100 raw merge 영역 신규 23 키** (현재 5 → 28 키 확장)

HIGH 영역 23 키:
- 밸류에이션 2: `per` / `pbr`
- 외국인 2: `hts_frgn_ehrt` / `frgn_ntby_qty`
- 상한가/하한가 2: `stck_mxpr` / `stck_llam`
- 거래량 2: `vol_tnrt` / `prdy_vrss_vol_rate`
- 신고가 5: `w52_hgpr` / `w52_lwpr` / `w52_hgpr_date` / `d250_hgpr` / `d250_lwpr`
- 진입 차단 6: `mrkt_warn_cls_code` / `invt_caful_yn` / `short_over_yn` / `sltr_yn` / `iscd_stat_cls_code` / `temp_stop_yn`
- 신고가 코드 1: `new_hgpr_lwpr_cls_code`
- 추가 회복 3: `eps` / `bps` (MEDIUM 흡수)

MEDIUM 영역 7 키 (FHKST01010100):
- `eps` / `bps`
- `whol_loan_rmnd_rate` / `ssts_yn` / `last_ssts_cntg_qty`
- `vi_cls_code` / `ovtm_vi_cls_code` (사이클 149 실시간 영역 정합)
- `bstp_kor_isnm` (업종 한글명)

**최종 FHKST01010100 raw merge 영역 = 기존 5 + 신규 23 = 28 키** (+ 추가 MEDIUM 7 = 영역 35 키 영영 영영 의무. 정밀 정합: 사용자 명세 영영 영영 영영 정합 정수 = 35 키).

**B. master_raw 영역 영영 적재 영역 활용 영역 영영 (DB write 0, scanner 활용 영역 의무)**

이미 적재됨 (3,573 row 전수 확인) → scanner.py 영역 활용 의무만 영영:
- 업종 분산 3: `bstp_larg_div_code` / `bstp_medm_div_code` / `bstp_smal_div_code`
- 재무 5: `sale_account` / `bsop_prfi` / `op_prfi` / `thtr_ntin` / `roe`
- krx 12 섹터 yn: `krx_car_yn` / `krx_smcn_yn` / `krx_bio_yn` / `krx_bank_yn` / `krx_enrg_chms_yn` / `krx_stel_yn` / `krx_medi_cmnc_yn` / `krx_cnst_yn` / `krx_scrt_yn` / `krx_ship_yn` / `krx_insu_yn` / `krx_trnp_yn`
- 신규 상장 회피: `stck_lstn_date`

### 진입 차단 영역 확장 (사이클 129 영영 영영 답습)

**1단계 차단 7건 → 13건** (master_raw 영역 7 + FHKST 영역 신규 6):
- 기존 7 (master_raw): `trht_yn` / `sltr_yn` / `mang_issu_yn` / `ssts_hot_yn` / `stange_runup_yn` / `mrkt_alrm_cls_code` ≥1 / `invt_alrm_yn`
- 신규 6 (FHKST raw): `mrkt_warn_cls_code` ≥1 / `invt_caful_yn`=Y / `short_over_yn`=Y / `sltr_yn`=Y (FHKST) / `iscd_stat_cls_code` 비정상 / `temp_stop_yn`=Y

차단 영역 OR 영영 (master_raw + raw 영역 양쪽 영영 영영 영영) — 사이클 129 영영 답습.

---

## 2. tdd-engineer Red 발주 — 회귀 가드 ≥18 케이스

### A 영역 — FHKST01010100 5 → 35 키 확장 (사이클 107 패턴 답습)

| 가드 ID | 영역 | 케이스 |
|---------|------|--------|
| G-155-MERGE-1 | HIGH | `inquire_stock_basics()` 영역 merge 영역 35 키 정합 (사이클 107 5-key 영역 영영 30 키 추가) |
| G-155-MERGE-2 | HIGH | 사이클 145 답습 = per/pbr/vol_tnrt 등 0 값 영영 → 기존 raw 키 영역 영영 영영 영영 (장 시작 전 graceful skip) |
| G-155-MERGE-3 | MEDIUM | FHKST01010100 호출 실패 → graceful + 사이클 144 graceful 카운터 증가 (사이클 88 G-REJECT 답습) |
| G-155-MERGE-4 | HIGH | 진입 차단 6 영영 키 (`mrkt_warn_cls_code` / `invt_caful_yn` / `short_over_yn` / `sltr_yn` / `iscd_stat_cls_code` / `temp_stop_yn`) 영영 정합 (None/공백 graceful) |
| G-155-MERGE-5 | MEDIUM | 신고가 5 (w52_* + d250_*) 영영 정합 |
| G-155-MERGE-6 | MEDIUM | 외국인 2 (`hts_frgn_ehrt` / `frgn_ntby_qty`) 영영 정합 |
| G-155-MERGE-7 | LOW | VI 2 (`vi_cls_code` / `ovtm_vi_cls_code`) 영역 정합 (사이클 149 정합) |

### B 영역 — scanner.py 진입 차단 7건 → 13건 확장 (사이클 129 답습)

| 가드 ID | 영역 | 케이스 |
|---------|------|--------|
| G-155-BLOCK-1 | HIGH | `_is_master_blocked_for_entry()` 영역 FHKST raw 영영 6 키 차단 확장 |
| G-155-BLOCK-2 | MEDIUM | master_raw + raw 영역 OR 영영 영영 (어느 한쪽이라도 차단 = 진입 차단) |
| G-155-BLOCK-3 | HIGH | 보유 종목 절대 보호 (사이클 32 R4 영영 영영 — `_is_master_blocked_for_entry()` 영영 영영 영영 영영 보유 영영 영영 영영) |

### C 영역 — list_by_filter Python-side 영영 영영 (사이클 148 답습)

| 가드 ID | 영역 | 케이스 |
|---------|------|--------|
| G-155-FILTER-1 | LOW | `per_max` / `pbr_max` / `frgn_ehrt_min` 영영 영영 인자 영영 정합 (디폴트 None = 전체 통과) |
| G-155-FILTER-2 | LOW | 영영 영영 영영 영영 (디폴트 None) = 회귀 보존 영영 정합 |

### D 영역 — AST + 안전성

| 가드 ID | 영역 | 케이스 |
|---------|------|--------|
| G-AST-155 | LOW | `inquire_stock_basics()` 영영 35 키 영영 영영 영영 (사이클 145 G-AST1 답습) — merge_keys 영영 영영 영영 영영 영영 |
| G-155-SAFETY-1 | HIGH | risk.on_tick / order_engine / realtime / auth 변경 0 (import 그래프 영영 영영) |
| G-155-SAFETY-2 | HIGH | 매수 진입 *전* 영영 한정 (사이클 38 명문화) — `_is_master_blocked_for_entry()` 호출 사이트 영영 검증 |
| G-155-SAFETY-3 | HIGH | 사이클 81 G-AST1 raw 영역 덮어쓰기 0 (사이클 145 패턴 답습) — 기존 5 키 영영 영영 영영 영영 |
| G-155-SAFETY-4 | MEDIUM | 사이클 32 R4 — 보유 종목 + `_pending_next_day_clear` 영영 차단 영영 영영 (회피 의무) |

### 신규 테스트 파일 영역

- `tests/unit/api/test_cycle155_merge_35_keys.py` — G-155-MERGE-1~7 (7 케이스)
- `tests/unit/engine/scanner/test_cycle155_block_13_keys.py` — G-155-BLOCK-1~3 (3 케이스)
- `tests/unit/db/test_cycle155_list_by_filter_per_pbr.py` — G-155-FILTER-1~2 (2 케이스)
- `tests/unit/ast/test_cycle155_ast_merge_keys_required.py` — G-AST-155 (1 케이스)
- `tests/unit/engine/scanner/test_cycle155_safety.py` — G-155-SAFETY-1~4 (4 케이스)
- 추가 영영 영영 영영 = 5 케이스 영영 영영 (영역 영영 영영 영영 영영 영영 영영) → 합계 **22 케이스**

---

## 3. backend-dev Green 발주

### 시정 영역 1 — `src/api/condition.py::inquire_stock_basics()` (L358~L388)

**현재** (사이클 145 영영 영영, L359):
```python
merged_raw = dict(ctpf_output)
for key in ("acml_tr_pbmn", "lstn_stcn", "acml_vol", "prdy_vrss", "hts_avls"):
    ...
```

**시정 영역**:
```python
# 사이클 155 — FHKST01010100 merge 영역 5 → 35 키 확장 (HIGH 23 + MEDIUM 7)
_FHKST_MERGE_KEYS: tuple[str, ...] = (
    # 기존 5 (사이클 107~108 영영)
    "acml_tr_pbmn", "lstn_stcn", "acml_vol", "prdy_vrss", "hts_avls",
    # 사이클 155 HIGH 23 영영
    "per", "pbr",
    "hts_frgn_ehrt", "frgn_ntby_qty",
    "stck_mxpr", "stck_llam",
    "vol_tnrt", "prdy_vrss_vol_rate",
    "w52_hgpr", "w52_lwpr", "w52_hgpr_date", "d250_hgpr", "d250_lwpr",
    "mrkt_warn_cls_code", "invt_caful_yn", "short_over_yn", "sltr_yn",
    "iscd_stat_cls_code", "temp_stop_yn",
    "new_hgpr_lwpr_cls_code",
    # 사이클 155 MEDIUM 7 영영
    "eps", "bps",
    "whol_loan_rmnd_rate", "ssts_yn", "last_ssts_cntg_qty",
    "vi_cls_code", "ovtm_vi_cls_code",
    "bstp_kor_isnm",
)

# 사이클 145 영영 영영 = 0 값 영영 영영 영영 영영 영영 영영 영영 영영 영영 영영
_ZERO_VALUE_SKIP_KEYS: tuple[str, ...] = (
    "acml_tr_pbmn", "acml_vol",  # 사이클 145 영영 영영
    "per", "pbr", "vol_tnrt", "prdy_vrss_vol_rate",  # 사이클 155 추가 영영
    "hts_frgn_ehrt", "frgn_ntby_qty",
    "w52_hgpr", "w52_lwpr", "d250_hgpr", "d250_lwpr",
    "eps", "bps", "whol_loan_rmnd_rate",
)

merged_raw = dict(ctpf_output)
for key in _FHKST_MERGE_KEYS:
    if key in price_data:
        value = price_data[key]
        if key in _ZERO_VALUE_SKIP_KEYS:
            try:
                numeric_value = float(str(value).replace(",", "") or 0)
                if numeric_value == 0.0:
                    continue
            except (ValueError, TypeError):
                pass
        merged_raw[key] = value
```

### 시정 영역 2 — `src/engine/scanner.py::_is_master_blocked_for_entry()` (사이클 129 영역 영영 7건 영역)

**시정 영역**:
- master_raw 영역 7건 영영 (사이클 129 영영) 영영
- FHKST raw 영역 6건 영영 추가:
  - `raw.mrkt_warn_cls_code` ≥ "01" (시장경고 영영)
  - `raw.invt_caful_yn` == "Y" (투자유의)
  - `raw.short_over_yn` == "Y" (단기과열)
  - `raw.sltr_yn` == "Y" (정리매매, FHKST 영영)
  - `raw.iscd_stat_cls_code` 비정상 (정상 = "55" 영영 영영 영영 영영 — KIS 정본 영영 영영 영영 영영 영영 영영 영영)
  - `raw.temp_stop_yn` == "Y" (임시 정지)

**근거**: 사이클 129 영역 차단 함수 영영 영영 OR 영영 영영 (master_raw + raw 영영) — 어느 한쪽이라도 차단 = 진입 차단.

**보유 종목 영영 영영 영영 영영 의무**: 호출 사이트 영영 사이클 32 R4 영영 영영 영영 영영 영영 영영 (보유 종목 영영 영영 영영 영영 영영 영영 영영). 이는 호출자 영영 영영 영영 → `_is_master_blocked_for_entry()` 본체 영영 영영 변경 0, 호출 사이트 영영 검증만 의무.

### 시정 영역 3 — `src/db/stock_master.py::list_by_filter()` (선택 영영, 사이클 108 답습)

신규 인자 영영 영영 (디폴트 None):
- `per_min: float | None = None` / `per_max: float | None = None`
- `pbr_max: float | None = None`
- `frgn_ehrt_min: float | None = None`

영영 영영 = Python-side 영영 영영 (`raw->>per` 영영 numeric 영영) — 사이클 148 패턴 답습. 디폴트 None = 전체 통과 = 회귀 보존.

**주의**: 사이클 156+ 활용 영역 영영 = 디폴트 None 의무. 영영 영영 영영 영영 영영 영영 영영 영영 영영.

---

## 4. tester verify 발주

### 회귀 영역

1. **풀 회귀 백엔드 3회 flakiness 0** — `python -m pytest -q` × 3회.
2. **사이클 155 격리 PASS** — `pytest tests/unit/api/test_cycle155_*.py tests/unit/engine/scanner/test_cycle155_*.py tests/unit/db/test_cycle155_*.py tests/unit/ast/test_cycle155_*.py`.
3. **프론트 회귀 영영 영영 PASS** — `cd frontend && npm test`.

### Supabase MCP READ-ONLY 검증

16:10 task 영영 영영 영영 (다음 영업일 영영 영영) 후 영영 영영 (사이클 155 종결 직후 영영 영영 = 직접 검증 영영 영영 → 사용자 D+1 영영 영영 또는 즉시 trigger):

```sql
-- stock_master.raw 영역 35 키 영영 영영 분포 영영
SELECT
  COUNT(*) FILTER (WHERE raw ? 'per') AS with_per,
  COUNT(*) FILTER (WHERE raw ? 'pbr') AS with_pbr,
  COUNT(*) FILTER (WHERE raw ? 'hts_frgn_ehrt') AS with_frgn_ehrt,
  COUNT(*) FILTER (WHERE raw ? 'stck_mxpr') AS with_mxpr,
  COUNT(*) FILTER (WHERE raw ? 'vol_tnrt') AS with_vol_tnrt,
  COUNT(*) FILTER (WHERE raw ? 'w52_hgpr') AS with_w52_hgpr,
  COUNT(*) FILTER (WHERE raw ? 'mrkt_warn_cls_code') AS with_mrkt_warn,
  COUNT(*) FILTER (WHERE raw ? 'invt_caful_yn') AS with_invt_caful,
  COUNT(*) FILTER (WHERE raw ? 'short_over_yn') AS with_short_over,
  COUNT(*) FILTER (WHERE raw ? 'temp_stop_yn') AS with_temp_stop,
  COUNT(*) FILTER (WHERE raw ? 'eps') AS with_eps,
  COUNT(*) FILTER (WHERE raw ? 'vi_cls_code') AS with_vi_cls_code,
  COUNT(*) FILTER (WHERE raw ? 'bstp_kor_isnm') AS with_bstp_kor_isnm,
  COUNT(*) AS total
FROM stock_master;
```

기대 영영: 활성 종목 영영 영영 영영 (~3,000 영영) 영영 영영 영영 영영 영영 영영 영영 영영. 0 값 영영 영영 영영 영영 영영 영영 영영 영영 영영 영영 (장 시작 전 영영 영영 영영 = 사이클 145 패턴 답습).

### 매매 안전성 영역 영속 검증

CLAUDE.md "절대 깨지 말 것" 8 영역 변경 0:
- 체결통보 구독 영영 영영 0
- uvicorn 단일 워커 영영 0
- 주문번호 매핑 영역 변경 0
- 체결통보 선행 race 가드 영영 0
- `_reset_daily_state()` 영영 영영 0
- 익일 청산 영영 영영 0
- NXT 매도 거부 좀비 차단 영영 0
- 매수/매도 시장가 거부 영영 0

사이클 영영 영영 영영 매트릭스 영속 검증:
- 사이클 32 R4 / 38 / 81 / 107 / 108 / 129 / 144 / 145 / 149 영역 영영 영영 변경 0 검증

---

## 5. 영속 의무 매트릭스

| 사이클 | 영속 영역 | 사이클 155 영영 |
|--------|----------|---------------|
| 사이클 32 R4 | 보유/익일청산 절대 보호 | `_is_master_blocked_for_entry()` 호출 사이트 영영 |
| 사이클 38 | scanner 매수 진입 전 한정 | 정합 — risk/order 변경 0 |
| 사이클 81 G-AST1 | raw 영역 영영 영영 | 기존 5 키 영영 영영 영영 (사이클 145 패턴 답습) |
| 사이클 88 G-REJECT | graceful 영역 | FHKST 호출 실패 영영 + 사이클 144 카운터 |
| 사이클 107 | inquire_stock_basics merge | 5 → 35 키 확장 (영영 영영) |
| 사이클 108 | list_by_filter 영영 | per_max/pbr_max 인자 영영 (디폴트 None) |
| 사이클 129 | 1단계 차단 7건 | → 13건 영영 (master_raw OR raw) |
| 사이클 144 | graceful 카운터 | FHKST 실패 영영 영영 |
| 사이클 145 | 0 값 영영 영영 영영 영영 | per/pbr/vol_tnrt 영영 동일 영영 |
| 사이클 149 | VI 영역 영영 정합 | vi_cls_code / ovtm_vi_cls_code 영영 |
| 사이클 153/154 | 정규화 컬럼 영영 | 미적용 (raw merge 영영) |

---

## 6. 발주 chain 영영

1. **tdd-engineer Red** — 22 케이스 신규 테스트 파일 4~5 영역 영영. Red 영영 영영 영영 영영 fail 확인.
2. **backend-dev Green** — `condition.py` + `scanner.py` + (선택) `stock_master.py` 시정. 22 케이스 PASS 영영.
3. **tester verify** — 풀 회귀 3회 flakiness 0 + Supabase MCP READ-ONLY + 매매 안전성 영영 영영.

**제약 영영**:
- commit/push 사용자 명시 승인 전 절대 금지
- 16:10 task 영영 영영 영영 영영 영영 영영 사용자 D+1 운영 영영 또는 즉시 trigger 영영 영영
- 의미 없는 반복 문구 금지

---

## 7. 회신 의무 영영 (tester verify 종결 시)

- production 라인 증감 + 신규 회귀 가드 케이스 수 (목표 22)
- 백엔드 풀 회귀 3회 결과 (flakiness 0)
- 16:10 task 영영 영영 영영 영영 영영 영영 (Supabase MCP, raw 영영 신규 30 키 영영 영영 영영 분포)
- 매매 안전성 8 영역 + 사이클 영영 영영 영영 변경 0 검증
- commit/push 사용자 명시 승인 대기
