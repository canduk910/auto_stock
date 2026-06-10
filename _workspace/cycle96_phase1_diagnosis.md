# 사이클 96 Phase 1 진단 (영구 기록)

**작성일**: 2026-06-10
**상태**: 영속 (사용자 지시 영역 기록)
**카드**: 사이클 94 단일화 영역 silent 결함 + 사이클 89 영역 복원 의무

## 1. 단일 근본 원인

```
KIS API "0000" 응답 = 단일 페이지 30 한도 + 페이징 미지원 silent 결함
```

KIS docstring 인용 영역과 운영 실측 영역의 *불일치* 가 결정적 발견. 사이클 94 시정 (`{"all": "0000"}`)
이 KIS docstring 정본 정합으로 진행되었으나, 운영 실측에서 `tr_cont="M"` 헤더 미수신 (페이징
종료 신호) → 첫 페이지 30 ticker 만 누적 → universe 미적재 확정.

## 2. 사이클 89 영역 복원 = KIS 정본 정합

- KIS "0001" (KOSPI 업종) 응답 = 페이징 17 페이지 정상 (운영 실측)
- KIS "0002" (KOSDAQ 업종) 응답 = 페이징 17 페이지 정상 (운영 실측)
- 사이클 89 영역 = 호출 인자 명명 `"1"`/`"2"` → 사이클 96 `"kospi"`/`"kosdaq"` 가독성 갱신

## 3. 사용자 결정 (영속)

- **Q50=D**: 사이클 89 영역 복원 (`"0001"`/`"0002"`) + 사이클 91 페이징 영역 결합
- **Q51=A**: 진단 완료 직후 push (KRX 메인 중, 사이클 38 명문화 매수 진입 전용 영역 영속)

## 4. 사이클 96 시정 영역 (Green 단계 backend-dev 인계)

`src/engine/scanner.py`:

1. `_MARKET_INPUT_ISCD = {"kospi": "0001", "kosdaq": "0002"}` 영역 복원
2. `_fetch_volume_rank(market="kospi"/"kosdaq", top_n=250, max_pages=17)` 시그너처 변경
3. `fetch_top_500_universe()` 2회 분리 호출 + post-split 영역 폐기 (KOSPI/KOSDAQ 분리 = KIS 자체)
4. emit `unknown=0` 영속 (사이클 95 키 호환)

## 5. xfail 의미 전환 매트릭스 (사이클 66 K-2 패턴)

| 영속 가드 | 사이클 96 시점 | 처리 |
|----------|--------------|------|
| `test_cycle89_kospi_kosdaq_separation.py::test_h3_*` | XPASS (영역 복원 후) | xfail 영속 (의미 전환 가시화) |
| `test_cycle94_fid_input_iscd_fix.py::test_h1_*` | XFAIL (영역 복원 후) | xfail 마킹 영속 |
| `test_cycle94_kospi_kosdaq_split_500.py::test_h4_*` | XFAIL | xfail 마킹 영속 |
| `test_cycle94_ast_no_industry_code.py::test_h6_*` | XFAIL | xfail 마킹 영속 |

## 6. 영속 의무 매트릭스

| 영속 의무 | 본 시정 영향 |
|----------|------------|
| 사이클 32 R4 universe guard (보유/익일청산 절대 보호) | 영향 0 (영역 분리) |
| 사이클 38 명문화 (매수 진입 전용) | 영향 0 |
| 사이클 91 페이징 (tr_cont + AST 가드 5) | **영속 + 결합** |
| 사이클 95 chicken-and-egg unknown 합집합 | **영속 + 영역 0 (graceful 영속, unknown=0 정상)** |
| **CLAUDE.md "절대 깨지 말 것" 8 영역** | **영향 0 전수** |

## 7. Red 단계 영향 인덱스

- 백엔드 2293 → 2308 (사이클 96 신규 +10 신규 fail + sub-test 5 = 15 fail 실측)
- xfail 마킹: 사이클 94 6 케이스 (XPASS) + 사이클 89 H-3 1 케이스 (XFAIL → 사이클 96 시정 후 XPASS 의미 전환)
- 영향 인덱스: backend tests 449 (`_workspace/test_index.yaml` 영속)
