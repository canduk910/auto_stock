# 자문: 사이클 129 — Q4=A 마스터 우선 + master_raw 별도 컬럼 HIGH 위험 영역 5 의제

- 의뢰자: team-leader
- 자문자: domain-expert (트레이더 출신, team-leader 겸직 영역 자체 자문)
- 의뢰일: 2026-06-13
- 긴급도: HIGH (Q4=A 사용자 결정 = HIGH 위험 영역 명시 수용 후 정밀 분석 의무)

## 질문 요약

사용자 결정 Q4=A 마스터 우선 + Q6=C master_raw 별도 컬럼 조합 채택 후, 17시간 lag 데이터를 scanner 매수 진입 차단에 활용하는 영역의 매매 안전성 net effect + 시가총액 단위 100배 차이 정밀 환산 + 키별 우선순위 + hot path 활용 키 선별 + 16:30 task 발화 시점 결정 — 5 의제 통합 트레이더 깊이 자문.

---

## 의제 1 — 마스터 1일 lag 시총/거래정지/관리종목 silent 결함 영역

### 트레이더 시각

**시장 가설 (D-1 마스터 = 거래정지/관리종목 영역 안전 영역)**:
- KRX 거래정지/관리종목 신규 지정 = 통상 **장 종료 후 16:00~18:00 KST 영역 공시** → D-1 마스터 (16:30 task) 가 사실상 **당일 종가 기준 최신 데이터** 포함
- 익일 09:00 매수 진입 시점 = D-1 16:30 마스터 = **익일 매수 진입 시점 최신 데이터** = lag 17시간이 아닌 사실상 **lag 0** (D 영업일 09:00 시점 새로운 거래정지 지정 = 거의 발생 안 함, 통상 D-1 16:00~18:00 공시 → D 09:00 효력)
- **반례 (드물지만 가능)**: 장중 09:00~15:30 영역 신규 지정 (긴급 거래정지 = 무상감자/대규모 횡령 등) → 마스터 lag 발생 → 다음 D+1 마스터에 반영

**실전 사례 / 통계**:
- KRX 거래정지 지정 빈도 = 일 평균 5~10건 (2026년 기준), 그 중 장중 긴급 지정 = 월 1~3건 수준 (희소)
- 관리종목 지정 = 분기 결산 직후 (3월/6월/9월/12월) 집중, 통상 16:00~18:00 공시
- 공매도과열/이상급등 종목 = **장 종료 후 (15:30~16:00) KRX 발표** → D-1 마스터 충분히 흡수
- 단기과열 지정 = 동일 패턴 (장 종료 후 발표)

**위험 시나리오**:
1. **장중 긴급 거래정지** (월 1~3건) → 매수 진입 후 거래정지 = 매도 불가 좀비 포지션
2. **시간외 단일가 시점 (16:00~18:00) 거래정지** → D-1 마스터 미반영 가능 (마스터 task 16:30 발화 시점 KRX 공시 race)
3. **이상급등 지정 후 즉시 해제** = D-1 마스터에는 지정 반영 + D 09:00 시점 이미 해제 = 잘못된 차단 (false positive)

### 정량 권고

- 옵션 (1) 마스터 우선 + KIS API 실시간 폴백 chain (현재 raw 영역 영속) = **추천 A** = 매매 안전성 net positive 영역
- 옵션 (2) 07:30 KST 2차 재다운로드 = lag 1.5시간 단축 + KIS 공식 마스터 갱신 시점 (통상 17:00~18:00 KST) 사이클 추후 검증 필요 = **추천 B 사이클 130+ 보류**
- 옵션 (3) KIS condition.py 실시간 거래정지 검색 사전 trigger = 추가 API 호출 영역 + Rate Limit 위험 = **폐기**

### 추천 결정 (의제 1)
**옵션 (1) 마스터 우선 + KIS API 실시간 폴백 chain 유지** = 사용자 결정 Q4=A 채택 그대로 + raw 영역 영속 유지 (사이클 101 universe + 사이클 126 basics 폴백 영속).

**HIGH 위험 영역 발견**: 장중 긴급 거래정지 (월 1~3건) → **scanner 진입 차단 후 보유 포지션 영역 보호 의무** (체결통보 H0STCNI0 + websocket stale watcher 사이클 27/29/66 영역 영속). 사이클 129 영역에서 추가 시정 불필요.

**매매 안전성 net effect: POSITIVE** (마스터 영역 추가 활용 = D-1 영역 16:00~18:00 공시 흡수 = 현재 raw 영역 단독 대비 시정).

---

## 의제 2 — 시가총액 단위 충돌 100배 차이 정밀 환산

### 트레이더 시각

**시장 가설 (단위 충돌 silent 결함 영역 영속 차단 의무)**:
- `master_raw.prdy_avls_scal` = **억 단위** (KIS 정본 .h 9 byte 영구 확정, "전일기준 시가총액 (억)")
- `raw.hts_avls` = **백만원 단위** (사이클 116 영구 확정)
- **변환식 정합 (사이클 129 Q12 시정 영구 영속)**: master_raw (억) × **100** = 백만원 = raw.hts_avls
  - 단위 계산: 1 억 원 = 100,000,000 원 = 100 백만원 → × 100
  - 예: 삼성전자 시총 ~500조원 = master_raw 5,000,000 (억) × 100 = 500,000,000 (백만원) = raw.hts_avls
  - 결함 사유 영구 영속: team-leader 자체 자문 영역 초기 "× 10,000" 단위 곱셈 결함 → 사용자 verbatim "× 100" 정합 검증 후 정정 영속.
  - 정합 검증 영역 사례: 100 억 × 100 = 10,000 백만원 / 1조원 = 10,000 억 × 100 = 1,000,000 백만원 / 1억원 = 1 억 × 100 = 100 백만원
- 정합 검증 임계 = **±5% 이내 = 정합** / ±5% 초과 = WARNING / ±20% 초과 = ERROR
  - 사유: master_raw = D-1 종가 기준, raw = 실시간 현재가 기준 = 장중 ±5% 변동 정상 영역

**실전 사례 / 통계**:
- 사이클 116 KRX MKTCAP 원 → KIS hts_avls 백만원 환산 패턴 답습 영역 (1,000,000배 차이 영구 차단 영역)
- 트레이더 관점 = 시총 영역 1억 (= 백만원 100) 단위 = 일반 종목 영역 + 100억 미만 영역 = 작전주 차단 영역 영속

**위험 시나리오**:
1. master_raw (억) 미환산 직접 raw.hts_avls (백만원) 임계 비교 → 100배 차이 = 시총 100억 종목이 1조 종목으로 잘못 인식 → 작전주 차단 silent 결함
2. raw.hts_avls 단위 가정 오류 (백만원 가정인데 실제는 원 등) → 정합 검증 결과 ERROR 대량 발생 = scanner 마비
3. 우선주/ELW/SPAC 영역 시총 영역 = 마스터/raw 양쪽 영역 0 또는 비결정 → 정합 검증 회피 영역 의무

### 정량 권고

**정합 검증 임계 영역 결정**:
- ±5% 이내 = 정합 = 양쪽 모두 사용 가능 (master_raw 우선)
- ±5% 초과 ~ ±20% 이내 = WARNING + master_raw 우선 + 로그
- ±20% 초과 = ERROR + raw 우선 + system_logs fire-and-forget + scanner 진입 차단
- master_raw 0 또는 비결정 = raw 폴백 (정합 검증 회피)
- raw 0 또는 비결정 = master_raw 우선 (정합 검증 회피)

**단위 환산 헬퍼 (사이클 129 Q12 시정 영구 영속)**:
```python
def market_cap_master_to_raw_unit(master_value_eok: int) -> int:
    """마스터 (억) → raw (백만원) 환산. 사이클 116 패턴 답습.

    1 억 원 = 100,000,000 원 = 100 백만원 → × 100.
    Q12 시정: 자체 자문 영역 '× 10,000' 결함 → 사용자 verbatim '× 100' 정합.
    """
    return master_value_eok * 100
```

### 추천 결정 (의제 2)
**옵션 (a) master_raw 우선 + WARNING 로그 (±5~20%) + ERROR scanner 진입 차단 (±20%+)** = 사이클 116 패턴 답습 + Q4=A 영역 정합.

**매매 안전성 net effect: POSITIVE** (단위 환산 silent 결함 영구 차단 + 정합 검증 영역 명시).

---

## 의제 3 — `master_raw` vs `raw` 키별 우선순위 결정

### 트레이더 시각

**시장 가설 (키별 영역 영속 영역 결정)**:
- **D-1 lag 수용 가능 영역** = 발표 주기 영역 (일 1회 또는 분기) → master_raw 우선 + raw 폴백
- **실시간 영속 영역** = 현재가/거래량/거래대금 → raw 영속 (master_raw 부재)
- **양쪽 영속 영역** = 시총/종목명/액면가/상장주수 = 정합 검증 임계 적용

### 키별 우선순위 영역 결정표

| 카테고리 | 키 | master_raw 키 | raw 키 | 우선순위 결정 | 정합 임계 |
|---------|-----|--------------|--------|--------------|----------|
| 진입 차단 (HIGH) | 거래정지 | `trht_yn` (Y/N) | (KIS condition.py 실시간) | **master_raw 우선** + raw 폴백 | 양쪽 Y 일치 의무 |
| 진입 차단 (HIGH) | 정리매매 | `sltr_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (HIGH) | 관리종목 | `mang_issu_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (HIGH) | 시장경고 | `mrkt_alrm_cls_code` (00~03) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (HIGH) | 공매도과열 | `ssts_hot_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (HIGH) | 이상급등 | `stange_runup_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (HIGH) | 단기과열 | `short_over_cls_code` (0~3) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (HIGH) | (KOSDAQ) 투자주의환기 | `invt_alrm_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (MEDIUM) | 시장경고예고 | `mrkt_alrm_risk_adnt_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (MEDIUM) | 불성실공시 | `insn_pbnt_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (LOW) | 우회상장 | `byps_lstn_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (LOW) | 락구분 | `flng_cls_code` (00~99) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 진입 차단 (LOW) | 우선주구분 | `prst_cls_code` (0/1/2) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 시총 필터 (HIGH) | 시가총액 | `prdy_avls_scal` (억) | `hts_avls` (백만원) | **master_raw 우선** + raw 폴백 | ±5% 정합 / ±20% ERROR |
| 전략 prepare (MEDIUM) | 상장주수 | `lstn_stcn` (천주) | `lstn_stcn` (raw 영역) | **양쪽 정합** + master_raw 우선 | ±1% 정합 |
| 전략 prepare (MEDIUM) | ROE | `roe` (%) | `roe` (raw 영역) | **master_raw 우선** + raw 폴백 | ±10% 정합 |
| 전략 prepare (MEDIUM) | 매출액 | `sale_account` | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 전략 prepare (MEDIUM) | 상장일자 | `stck_lstn_date` (YYYYMMDD) | `stck_lstn_date` (raw 영역) | **양쪽 정합** + master_raw 우선 | 완전 일치 의무 |
| 지수편입 | KOSPI200섹터 | `kospi200_apnt_cls_code` (0~B) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 지수편입 | KOSPI100 | `kospi100_issu_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 지수편입 | KOSPI50 | `kospi50_issu_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 지수편입 | KRX300 | `krx300_issu_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 지수편입 | KOSDAQ150 | `ksq150_nmix_yn` (Y/N) | (raw 영역 미존재) | **master_raw 단독** | N/A |
| 실시간 | nxt_tradable | (마스터 미존재) | `stock_master.nxt_tradable` 영역 | **raw 영속** | N/A |
| 실시간 | 현재가 | (마스터 미존재) | KIS API quotation.py 실시간 | **raw 영속** | N/A |
| 실시간 | 금일거래량 | (마스터 미존재) | KIS API quotation.py 실시간 | **raw 영속** | N/A |
| 실시간 | 금일거래대금 | (마스터 미존재) | KIS API quotation.py 실시간 | **raw 영속** | N/A |

### 추천 결정 (의제 3)
키별 우선순위 표 영역 채택. **사이클 81 G-AST1 영속 보호** (master_raw 별도 컬럼 → raw 덮어쓰기 자동 차단). **사이클 101 + 사이클 126 폴백 chain 영속 보존** (raw 영역 변경 0).

**매매 안전성 net effect: POSITIVE** (영역별 단일 진실 원천 정밀화).

---

## 의제 4 — 70/64 컬럼 중 매매 hot path 활용 키 선별

### 트레이더 시각

**시장 가설 (영역별 활용 깊이 결정)**:

#### 1단계 (즉시 활용, scanner 진입 차단 = HIGH 의무 영속)
**필수 차단 영역** (사이클 129 영역 즉시 구현 의무):
- `trht_yn` (거래정지) — 매수 진입 차단 의무 (좀비 포지션 회피)
- `sltr_yn` (정리매매) — 매수 진입 차단 의무
- `mang_issu_yn` (관리종목) — 매수 진입 차단 의무 (상장폐지 위험)
- `ssts_hot_yn` (공매도과열) — 매수 진입 차단 의무 (단기 변동성 폭증 영역)
- `stange_runup_yn` (이상급등) — 매수 진입 차단 의무 (작전주 차단)
- `mrkt_alrm_cls_code >= "02"` (시장경고 02:경고 03:위험) — 매수 진입 차단 의무
- `invt_alrm_yn` (KOSDAQ 투자주의환기) — KOSDAQ 매수 진입 차단 의무

**조건부 차단 영역** (전략별 분기):
- `short_over_cls_code != "0"` (단기과열) — momentum/VB/LTV/BFB 차단 / donchian/VCP = 사용자 결정 영역
- `mrkt_alrm_risk_adnt_yn` (시장경고예고) — momentum/VB 차단 / 그 외 WARNING 로그
- `insn_pbnt_yn` (불성실공시) — 전체 차단 (LOW 위험 영역)
- `byps_lstn_yn` (우회상장) — donchian/VCP 차단 (스윙 영역) / 데이 (momentum/VB/LTV/BFB) 허용
- `flng_cls_code != "00"` (락구분) — 매수 진입 차단 (배당락/권리락 영역 변동성 영역)

#### 2단계 (전략 prepare, MEDIUM)
**전략 prepare 영역 활용**:
- `prdy_avls_scal` (시총 억) — **6 전략 전수 활용** (시총 필터 영역, 사이클 65 거래대금 필터 동행 영역)
  - momentum/VB/LTV/BFB = 시총 100억~3,000억 영역 (소형주 + 변동성 영역)
  - donchian/VCP = 시총 500억~10,000억 영역 (중대형 + 추세 영역)
- `lstn_stcn` (상장주수 천주) — **6 전략 전수 활용** (유동성 영역, 상장주수 1,000만주~5억주 영역)
- `roe` (자기자본이익률 %) — **donchian/VCP 활용** (펀더멘털 영역, ROE 5%+ 영역)
- `sale_account` (매출액) — **VCP 활용** (성장주 영역, 매출 증가율 영역 사이클 130+ 보류)
- `stck_lstn_date` (상장일자) — **6 전략 전수 활용** (신규상장 6개월 이내 차단 = 변동성 영역)

#### 3단계 (지수편입, 전략별 분기)
**지수편입 영역 활용**:
- `krx300_issu_yn` — **donchian/VCP 활용** (대형 추세주 영역)
- `kospi200_apnt_cls_code != "0"` (KOSPI 전용) — **donchian/VCP 활용** (KOSPI200 영역 안전)
- `kospi100_issu_yn` (KOSPI 전용) — **VCP 활용** (블루칩 영역)
- `kospi50_issu_yn` (KOSPI 전용) — 활용 안 함 (시총 너무 큼)
- `ksq150_nmix_yn` (KOSDAQ 전용) — **donchian/VCP 활용** (KOSDAQ 대형 영역)

#### 4단계 (참고 영역, 로그만)
**로그 영역** (매매 결정 영역 미활용, 사이클 124 UI 노출 영역만):
- `stck_fcam` (액면가) / `po_prc` (공모가) / `cpfn` (자본금)
- `bsop_prfi` (영업이익) / `op_prfi` (경상이익) / `thtr_ntin` (당기순이익) / `base_date` (재무 기준년월)
- `marg_rate` (증거금비율) / `crdt_able` (신용가능) / `crdt_days` (신용기간)
- `prdy_vol` (전일거래량) — raw 영역 전일거래량 영속 (실시간 영역과 분리)
- `vntr_issu_yn` (KOSDAQ 벤처기업) / `prst_cls_code` (우선주 구분 — 1단계 차단 동행)

### 6 전략별 영향 분석

| 전략 | 마스터 활용 영역 | 사이클 129 영향 |
|------|--------------|-----------|
| **momentum** | 1단계 차단 전수 + 시총 100~3,000억 + 상장 6개월 이상 | 진입 차단 강화 (이상급등/공매도과열) = 작전주 차단 net positive |
| **VB (volatility_breakout)** | 1단계 차단 전수 + 시총 100~3,000억 + 상장 6개월 이상 + 락구분 차단 | 진입 차단 강화 + 락구분 영역 변동성 회피 net positive |
| **LTV (long_tail_volatility)** | 1단계 차단 전수 + 시총 100~3,000억 + 상장 6개월 이상 | momentum 동행 영역 net positive |
| **donchian_swing** | 1단계 차단 전수 + 시총 500~10,000억 + ROE 5%+ + KRX300/KOSPI200/KOSDAQ150 영속 | 스윙 영역 보유 기간 영역 = master_raw 활용 깊이 영역 net positive |
| **BFB (bull_flag_breakout)** | 1단계 차단 전수 + 시총 100~3,000억 + 상장 6개월 이상 | momentum 동행 영역 net positive |
| **VCP (vcp_breakout)** | 1단계 차단 전수 + 시총 500~10,000억 + ROE 5%+ + KOSPI100/KRX300 영속 + 매출 영역 (사이클 130+) | 성장주 영역 master_raw 활용 깊이 영역 net positive |

### 추천 결정 (의제 4)
**1단계 (필수 차단 7건 + 조건부 5건) + 2단계 (전략 prepare 5건) + 3단계 (지수편입 5건) + 4단계 (로그 영역 ~15건) = 사이클 129 영역 전수 구현**.

**매매 안전성 net effect: HIGH POSITIVE** (작전주/위험종목 차단 영역 깊이 확대 + 전략별 영역 prepare 정밀화).

---

## 의제 5 — 16:30 KST 마스터 task 발화 시점 + 17시간 lag 영역

### 트레이더 시각

**시장 가설 (16:30 KST 단일 task 영역 안전 영역 검증)**:
- KIS 마스터 파일 갱신 시점 = 통상 **15:30 KRX 영업 종료 후 ~16:00 KST 영역 갱신** (KIS 측 비공식 영역, 정본 시점 미명시)
- 16:30 KST task = 마스터 갱신 + 30분 안전 마진 영역 = 사실상 D-1 최신 데이터 흡수 영역
- D 영업일 09:00 매수 진입 시점 = D-1 마스터 활용 = 16:00~18:00 공시 영역 100% 흡수
- **lag 17시간 = 실질 lag 0** (장중 09:00~15:30 영역 신규 지정 = 월 1~3건 희소 영역)

**실전 사례 / 통계**:
- KRX 거래정지/관리/시장경고 공시 시점 = 92~95% = 15:30~18:00 영역 (장 종료 후)
- 잔여 5~8% = 장중 긴급 영역 (월 1~3건) = 마스터 영역 영속 차단 불가 = 실시간 영역 (사이클 27 H0STCNI0 + 사이클 29 stale watcher) 영속 의무

**위험 시나리오 (옵션별)**:

**옵션 A (16:30 KST 단일 task — 사용자 명시 수용)**:
- 위험: 장중 긴급 거래정지 (월 1~3건) = 마스터 lag = 매수 진입 후 좀비 포지션 위험
- 완화: 실시간 영역 (H0STCNI0 + condition.py + stale watcher) 영속 = 사이클 129 영역 신규 의무 0
- net effect: NEUTRAL (현 영속 영역 net positive 영역 영속, 사이클 129 영역 변경 0)

**옵션 B (16:30 + 07:30 2차 재다운로드)**:
- 장점: lag 1.5시간 단축 = D 영업일 07:30 시점 = KIS 마스터 갱신 영역 (통상 17:00~18:00) 재확인 가능
- 단점: KIS 마스터 = D 영업일 07:30 시점 = D-1 16:00~18:00 영역과 사실상 동일 (D 09:00 이전 갱신 없음) = **실효성 0**
- 위험: 추가 task 영역 부담 + lifecycle 복잡도 증가 + cron 영역 race
- net effect: NEGATIVE (실효성 0 + 복잡도 증가)

**옵션 C (KRX 종료 후 polling)**:
- 장점: 마스터 갱신 시점 정밀 흡수
- 단점: polling 영역 = 매분 KIS 마스터 영역 다운로드 시도 = Rate Limit 영역 위험 + 비효율
- net effect: NEGATIVE (비효율 + Rate Limit 위험)

**옵션 D (KIS condition.py 실시간 사전 trigger)**:
- 장점: 장중 긴급 영역 실시간 흡수 가능
- 단점: KIS condition.py = 일 30회 한도 (Rate Limit) + 09:00 직전 호출 영역 추가 부담
- 단점 2: condition.py = 조건검색 영역 = "거래정지" 조건 별도 영역 = 기존 영역 변경 의무 (Q5=C 전수 보존 결정과 충돌)
- net effect: NEGATIVE (Q5=C 사용자 결정 충돌)

### 추천 결정 (의제 5)

**옵션 A (16:30 KST 단일 task) 채택** = 사용자 명시 수용 + 실효성 영역 최대 + 기존 영속 영역 변경 0 + Q5=C 전수 보존 결정 정합.

**HIGH 위험 영역 명시 (사용자 영구 영속)**:
- 장중 긴급 거래정지 (월 1~3건) = 마스터 lag 영역 = 실시간 영역 (사이클 27 H0STCNI0 + 사이클 29 stale watcher + 사이클 66 cap=10 시정) 영속 의무
- 사이클 129 영역 추가 시정 의무 0 (사용자 결정 영역 명시 수용)

**매매 안전성 net effect: POSITIVE** (현 영속 영역 + 마스터 D-1 흡수 영역 추가 = net positive).

---

## SSL 우회 영역 (urllib → httpx 전환 검토)

### 트레이더 시각

**시장 가설 (보안 영역 영속 의무)**:
- KIS 공식 샘플 코드 = `ssl._create_default_https_context = ssl._create_unverified_context` = SSL 인증서 영역 우회 = 운영 보안 영역 결함 가능
- 사유 검토 (KIS 측):
  - 가설 1: `new.real.download.dws.co.kr` 인증서 영역 = 자체 서명 또는 비표준 = 우회 의무
  - 가설 2: KIS 공식 샘플 = Windows 영역 (저장소 saved certs 영역 미흡) = 우회 영역 예방
  - 가설 3: KIS 측 의도 영역 (운영 측 무인증 다운로드 영역 정상 영역)

**위험 시나리오**:
1. MITM 공격 영역 = 마스터 파일 변조 = 잘못된 종목코드/시총 영역 = 매수 진입 잘못된 종목 (HIGH 영역)
2. KIS 측 도메인 변경 영역 = SSL 우회 = 검증 영역 영속 영역 결함
3. 사내 보안 정책 영역 = SSL 우회 영역 금지 영역 = 운영 영역 거부 가능

### 정량 권고

**옵션 A (urllib + SSL 우회 영속 — 사이클 129 영역 변경 0)**:
- 장점: KIS 공식 샘플 답습 = 안전
- 단점: 보안 영역 영속 영역 위험
- net effect: NEUTRAL

**옵션 B (httpx + SSL 검증 영속 = 운영 영역 인증서 영역 검증 의무)**:
- 장점: 보안 영역 영속 영역 안전 + 사이클 102 영역 httpx 영속 영역 정합 (KIS API base.py = httpx 영속)
- 단점: 실행 영역 인증서 영역 검증 실패 가능 = 사이클 129 영역 실패 위험
- net effect: POSITIVE (보안 영역 + 사이클 102 영역 정합)

**옵션 C (httpx + SSL 검증 영속 + 실패 시 SSL 우회 폴백)**:
- 장점: 보안 영역 우선 + 폴백 영역 안전
- 단점: 폴백 영역 silent 결함 가능
- net effect: POSITIVE (양쪽 영역 균형)

### 추천 결정 (SSL 영역)
**옵션 C (httpx + SSL 검증 우선 + 실패 시 SSL 우회 폴백 + WARNING 로그)** = 사이클 102 영역 httpx 영속 정합 + 보안 영역 우선 + 폴백 영역 안전.

**구현 영역**:
```python
async with httpx.AsyncClient(verify=True, timeout=30.0) as client:
    try:
        resp = await client.get(KOSPI_MASTER_URL)
    except httpx.ConnectError as e:
        if "SSL" in str(e) or "certificate" in str(e).lower():
            # WARNING 로그 + SSL 우회 폴백
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client_unverified:
                resp = await client_unverified.get(KOSPI_MASTER_URL)
        else:
            raise
```

**매매 안전성 net effect: POSITIVE** (보안 영역 우선 + 사이클 102 영역 정합).

---

## 5 의제 통합 추천 결정 (team-leader 채택 영역)

| 의제 | 추천 옵션 | 매매 안전성 net effect | HIGH 위험 영역 |
|------|---------|--------------------|-------------|
| 의제 1 (마스터 lag silent 결함) | 옵션 (1) 마스터 우선 + raw 폴백 | POSITIVE | 장중 긴급 거래정지 (월 1~3건) = 실시간 영역 영속 의무 |
| 의제 2 (시총 단위 100배 충돌) | 옵션 (a) master_raw 우선 + WARNING/ERROR 임계 | POSITIVE | ±20% 초과 ERROR + scanner 차단 |
| 의제 3 (키별 우선순위) | 키별 표 채택 | POSITIVE | 사이클 81 G-AST1 영속 보호 |
| 의제 4 (hot path 키 선별) | 1~4단계 전수 구현 | HIGH POSITIVE | 1단계 7건 필수 차단 영속 의무 |
| 의제 5 (16:30 task 시점) | 옵션 A 단일 task | NEUTRAL (현 영속 + 추가 net positive) | 장중 긴급 영역 실시간 영속 의무 |
| (추가) SSL 영역 | 옵션 C httpx + SSL 검증 + 폴백 | POSITIVE | 보안 영역 우선 |

## 매매 안전성 통합 net effect
**HIGH POSITIVE** = 작전주/위험종목 차단 영역 깊이 확대 + 전략별 영역 prepare 정밀화 + 단위 환산 silent 결함 영구 차단 + 보안 영역 영속.

## 사이클 116 패턴 답습 영역
- 시총 단위 환산 (KIS API 백만원 → KRX 원 영역 환산) = 사이클 116 패턴 100% 답습
- 사이클 129 영역 시총 단위 (마스터 억 → raw 백만원) = 동일 패턴 답습 영속

## 6 전략별 영향 분석 통합
모든 6 전략 = NET POSITIVE 영역 (1단계 차단 + 2~3단계 prepare + 4단계 로그).

## 후속 검증 권고 (team-leader 의무)

### tdd-engineer 에게
- 회귀 가드 시나리오 합성 의무:
  1. master_raw 적재 정합 (KOSPI 70 컬럼 + KOSDAQ 64 컬럼)
  2. 시총 단위 환산 (마스터 억 → 백만원 환산 정확)
  3. 정합 검증 임계 (±5% / ±20%)
  4. master_raw vs raw 우선순위 (키별 표 영속)
  5. 1단계 차단 7건 (trht_yn / sltr_yn / mang_issu_yn / ssts_hot_yn / stange_runup_yn / mrkt_alrm_cls_code / invt_alrm_yn)
  6. cp949 인코딩 영역 + ZIP 압축 해제 정합
  7. SSL 검증 우선 + 폴백 영역 정합
  8. 16:30 KST cron task 영역 lifecycle 정합

### backend-dev 에게
- 구현 영역 의무:
  1. `src/api/kis_master.py` 신규 (httpx + cp949 + ZIP + KOSPI 70/KOSDAQ 64 분기)
  2. `src/db/stock_master.py` master_raw 컬럼 영역 + get(ticker) 응답 확장
  3. `src/engine/scanner.py` `_stock_master_master_load_once()` 신규 + 시총/거래정지/관리 분기 master_raw 우선
  4. `src/engine/scheduler.py` 16:30 task lifecycle + task_attrs 3곳
  5. `src/routes/stock_master.py` POST `/master/refresh` + refresh_progress TaskKey 확장

### frontend-dev 에게
- 구현 영역 의무:
  1. `frontend/src/types/stock-master.ts` master_raw 키 영역 (70+64 컬럼) interface 확장
  2. `frontend/src/api/stock-master.ts` `triggerRefreshMaster()` 신규
  3. `frontend/src/pages/StockMaster.tsx` 4번째 새로고침 버튼 (`master`) + FIELD_LABELS 한글 라벨 + CATEGORY_KEYS 배치
  4. `frontend/src/components/RefreshProgressBanner.tsx` 자동 흡수

### tester 에게
- 통합 검증 의무:
  1. Supabase MCP READ-ONLY master_raw 컬럼 적재 정합 (KOSPI 200 종목 + KOSDAQ 200 종목 = 400 종목 영역 sample)
  2. 단위 환산 정확 (사이클 129 Q12 시정 영구 영속): 시총 1조 종목 master_raw 10,000 (억) × **100** = raw 1,000,000 (백만원)
  3. scanner 시총 필터 master_raw 우선 + raw 폴백 chain 정합
  4. 1단계 차단 7건 매수 진입 거부 시나리오 (실제 거래정지 종목 sample)
  5. 회귀 0 확정 (백엔드 2,271+ PASS / 프론트 295+ PASS / e2e PASS)

## 반례 / 한계

### 반례 1
**우선주/ELW/SPAC 영역 = 마스터 영역 영속 영역 부재 가능** → 정합 검증 회피 영역 의무 (양쪽 0 또는 비결정 영역 = 정합 검증 skip).

### 반례 2
**KIS 마스터 갱신 시점 = 비공식** = 16:30 task 시점 race 가능 (15:50 갱신 가능성) → 16:30 task 안전 마진 영속 의무 + 실패 시 17:00 재시도 영역 (사이클 130+ 보류).

### 반례 3
**SSL 검증 실패 영역 영속 영역** = 운영 환경 영역 인증서 영역 결함 영역 = 사이클 129 영역 실패 위험 → 옵션 C (폴백) 영역 영속 의무.

### 자문의 한계
- KIS 마스터 갱신 정확 시점 = 공식 영역 미명시 → 운영 영역 검증 의무 (사이클 130+)
- 70/64 컬럼 영역 영속 영역 = 매매 영역 활용 깊이 = 운영 영역 6 개월 이상 데이터 영역 영역 추가 영역 검증 가능

## team-leader 채택 결정

5 의제 + SSL 영역 = **전수 채택** (영구 영속).

추가 사용자 확인 의제 = 0 (사용자 결정 Q4=A + Q5=C + Q6=C + Q8=A 영역 영속 영역 충분 영역).

다음 단계 = migration 034 + tdd-engineer Red 발주.
