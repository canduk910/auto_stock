# 사이클 97 Phase 1 진단 (영구 기록)

**작성일**: 2026-06-10
**상태**: 영속 (사용자 보고 영역 기록)
**카드**: 사이클 89/91/94/96 전체 영역 영구 폐기 가설 + 대안 영역 결정

## 1. 단일 근본 원인 (영구 확정)

```
KIS volume_rank API (FHPST01710000) = 단일 페이지 30 ticker 한도 영역
+ "0001"/"0002" 업종 필터 응답 영구 30 한도
+ tr_cont = "M" 미반환 → 페이징 영역 자체 비기능
+ 사이클 91 페이징 코드 = KIS 응답 영역에서 무용
```

### 1.1 운영 실증 결정적 증거 (Supabase MCP READ-ONLY)

| 시각 KST | universe | kospi | kosdaq | elapsed_ms | 영역 |
|---------|---------|-------|--------|-----------|------|
| 14:23~15:38 (총 16회) | **29** | 23~25 | 4~6 | 1556~2229 | 사이클 89/94 영역 (페이징 영속) |
| 15:40~15:45 (총 4회) | **60** | 30 | 30 | 115~186 | 사이클 96 배포 후 영역 |

**결정적 영구 발견**:
- 사이클 96 배포 시점 15:38:57 → 15:40:12 universe **29 → 60** 단발 전환 확정
- 사이클 96 elapsed_ms 115~186ms ≪ 사이클 89 1556~2229ms = **추가 페이징 호출 0건** (stock_master cache 흡수만)
- universe = KOSPI 30 + KOSDAQ 30 = **각 호출당 단일 페이지 30 ticker 한도 = KIS API 자체 한계**

### 1.2 stock_master 현황 (READ-ONLY)

```
total = 82 (KOSPI excg=02: 53 + KOSDAQ excg=03: 29)
recent_6h = 48 (사이클 96 배포 후 캐시 적재)
```

= 시스템 전체 누적 캐시 82 ticker (사이클 89 시점 누적분 포함) vs 매 호출 universe = 60

## 2. KIS MCP 정본 재검증 (필수 영역)

### 2.1 volume_rank.py 정본 (`/uapi/domestic-stock/v1/quotations/volume-rank`, FHPST01710000)

```python
# KIS docstring: tr_cont == "M" 시 다음 페이지 존재
# 운영 실측: tr_cont 미반환 → 페이징 영역 자체 미작동
# fid_input_iscd = "0000"(전체) / "0001"(KOSPI) / "0002"(KOSDAQ) / 업종코드
```

**docstring vs 실측 불일치 영구 확정** (사이클 96 § 1 영역 영구 영속).

### 2.2 fluctuation.py 정본 (`/uapi/domestic-stock/v1/ranking/fluctuation`, FHPST01700000)

```python
def fluctuation(
    ...
    fid_input_cnt_1: str,  # 입력 수1 (조회할 종목 수) ← 결정적 파라미터
    fid_rank_sort_cls_code: str,  # 0000: 등락률순
    fid_rsfl_rate1: str,  # 등락 비율1 (하락률 하한)
    fid_rsfl_rate2: str,  # 등락 비율2 (상승률 상한)
    tr_cont: str = "",  # tr_cont == "M" 페이징 영속
)
```

**결정적 영구 발견**: `fid_input_cnt_1` = "조회할 종목 수" 파라미터 영속 존재 = **사용자 영역 영구 제어 가능 영역**. volume_rank 영역 (단일 페이지 30 한도) 와 영구 차별.

### 2.3 psearch_title / psearch_result (조건검색 영역)

| function_name | api_name | 영역 |
|--------------|----------|------|
| psearch_title | 종목조건검색 목록조회 | HTS 사용자 영구 등록 조건 list |
| psearch_result | 종목조건검색조회 | seq 인자 → 조건 매칭 종목 list |

**영역 한계**: HTS 사전 등록 의존 + 사용자 매번 등록 의무 영역.

## 3. KIS API 영역 한도 영역 영구 명문화

| API | tr_id | 페이지 한도 | 페이징 영역 | 사용자 제어 영역 |
|-----|-------|----------|----------|--------------|
| **volume_rank** | FHPST01710000 | **30 영구** | tr_cont 미반환 (운영 실측) | 없음 |
| **fluctuation** | FHPST01700000 | **fid_input_cnt_1 제어** | tr_cont 영속 (docstring) | 영구 (조회 종목 수) |
| psearch_title | HHKST03900300 | - | - | HTS 사전 등록 |
| psearch_result | HHKST03900400 | - | - | seq 의존 |

## 4. 대안 영역 평가 매트릭스 (Q52 의제)

| ID | 대안 영역 | 효과 | 위험 | 구현 영역 | 결정적 영구 평가 |
|----|---------|-----|------|---------|-------------|
| **A** | KIS **fluctuation** 영역 도입 (등락률 순위) | **300~500 ticker 영구 가능** (fid_input_cnt_1 영구 제어) | LOW (KIS 정본 + 페이징 영속) | scanner.py `_fetch_fluctuation_rank` 신규 + scheduler 통합 | **HIGH 권고** (단일 영구 시정 영역) |
| B | KIS **psearch_result** 영역 도입 | 사용자 영구 등록 조건 영역 다수 | HIGH (HTS 사전 등록 의무 + seq 영역 변경 가능) | KIS condition_id 영구 의존 | 비권고 |
| C | KIS **inquire-market** 영역 (사이클 95 unknown 합집합 영역 확장) | 전체 KRX 종목 list 영구 | MEDIUM (영역 미식별) | KIS MCP 영역 추가 검색 의무 | 보류 |
| D | **외부 영역** (네이버/거래소) | 영구 영역 한계 | HIGH (외부 의존 + 도메인 변경) | requests 영역 신규 | 비권고 |
| **E** | **사이클 89/91/94/96 영구 폐기 + 60 ticker 영속 수용** | 효과 0 | LOW | 코드 변경 0 | **LOW 위급 영역 영구 영속 영역** |

### 4.1 결정적 영구 권고 = 옵션 A (fluctuation 영역 도입)

**근거 매트릭스**:
1. `fid_input_cnt_1` = 사용자 영구 제어 영역 (docstring 정본)
2. `tr_cont` 페이징 영속 (docstring 정본, 운영 실측은 사이클 97 영역 의무)
3. KOSPI/KOSDAQ 영역 분리 = fid_input_iscd `"0000"` 단일 호출 (페이징 영속)
4. 매수 진입 전용 영역 (사이클 38 명문화 영속) = 등락률 순위 영역 매수 신호와 정합
5. 사이클 89/91/94/96 영역 전수 영구 폐기 + 사이클 95 chicken-and-egg unknown 합집합 영속

## 5. 영속 의무 매트릭스 (대안 영역 채택 시)

| 영속 의무 | 옵션 A 영향 |
|----------|-----------|
| 사이클 32 R4 universe guard (보유/익일청산 절대 보호) | 영향 0 (영역 분리) |
| 사이클 38 명문화 (매수 진입 전용) | 영향 0 (영구 정합) |
| 사이클 95 chicken-and-egg unknown 합집합 | **영속** (graceful 영역) |
| **CLAUDE.md "절대 깨지 말 것" 8 영역** | **영향 0 전수** |
| 사이클 91 페이징 (tr_cont + AST 가드 5) | **영구 폐기** (volume_rank 영역만) → 신규 fluctuation 영역 페이징 의무 |

## 6. xfail 의미 전환 매트릭스 (사이클 96 답습)

| 영속 가드 | 사이클 97 시점 | 처리 |
|----------|-------------|------|
| `test_cycle89_kospi_kosdaq_separation.py` | XFAIL (영구 폐기) | xfail 마킹 영속 |
| `test_cycle91_volume_rank_pagination.py` | XFAIL (영구 폐기) | xfail 마킹 영속 |
| `test_cycle94_fid_input_iscd_fix.py` | XFAIL 영속 | 영속 |
| `test_cycle96_volume_rank_kospi_kosdaq_restore.py` | XFAIL (영구 폐기) | xfail 마킹 영속 |
| `test_cycle97_fluctuation_*.py` (신규) | RED → GREEN | 신규 영구 가드 |

## 7. 사용자 결정 의제 (영구 영속)

### Q52 (HIGH) 대안 영역 선택

- **A**: KIS `fluctuation` 영역 신규 도입 (등락률 순위, fid_input_cnt_1=300+ 영구 제어) — **권고**
- B: KIS `psearch_result` 조건검색 영역 도입 (HTS 사전 등록 영역)
- C: KIS `inquire-market` 영역 추가 검색 (사이클 95 unknown 합집합 영역 확장)
- D: 외부 영역 (네이버 금융 / 한국거래소 OpenAPI 등)
- **E**: 사이클 89/91/94/96 영역 전수 폐기 + 60 ticker 영구 영속 수용 (시스템 본질 한계 영역)

### Q53 (HIGH) 시정 영역 영구 폐기 여부

- **A**: 사이클 89/91/94/96 전수 폐기 + 신규 영역 도입 (Q52=A 채택 시)
- B: 사이클 89/91/94/96 영속 + 60 ticker 영구 영속 수용 (Q52=E 채택 시)
- C: 사이클 89/91/94/96 영속 + 신규 영역 추가 (병행 영역, Q52=A+B 결합 시)

### Q54 (HIGH) 사이클 97 발주 시점

- A: 진단 직후 (KRX 메인 시간 = 사이클 38 명문화 영속 안전)
- **B**: 15:30 NXT 애프터 (보수적 마진 + KRX 메인 종료) — **권고** (사이클 91/94/96 답습)

## 8. 영구 영속 의무

- 코드 변경 0 (Phase 1 진단 단독)
- Q52~Q54 사용자 결정 의제 영구 영속
- Phase 2 명세 분해 = Q52 결정 후 영구 시작
- KIS MCP 정본 영속 (volume_rank vs fluctuation docstring 영구 명문화)
- Supabase 운영 실증 (universe 60 영구 영속 = 사이클 89/96 시점 100% 영구 일치 검증)
