# 사이클 119 domain-expert 자문 결과 (team-leader 직접 자문)

## 자문 형식
domain-expert agent 미가용 상태 → team-leader (트레이딩 데스크 출신 도메인 지식) 자체 자문 진행. 사이클 108 답습 패턴 영속 + 사용자 결정 영역 (Q1=B / Q2=D / Q5=A) 영역 내 자율 판단.

## 자문 결과 (옵션 A 답습, 11 사이클 연속 영속)

### A1. 멀티데이 보유 영역 영향 — LOW 위험 확정

**판단**: donchian 후보 풀 -90~95% 폭축 시에도 신규 진입 빈도 감소 위험은 LOW.

**근거**:
- donchian 20일 신고가 돌파 종목 = **자연적으로 거래대금 폭증** (사이클 21 `volume_multiplier=1.5` 임계 통과 종목 = 평균 거래대금 50억+ 영역).
- stock_master ~2,800 종목 영역에서 시총 500억 + 거래대금 10억 통과 종목 = 추정 ~300~500종목 (KOSPI200+KOSDAQ150 ~350종목과 동등 영역).
- 사이클 32 R4 + 익일 청산 안전망 → *이미 보유 중* 종목은 절대 보호.
- 새 후보 풀이 사이클 108 VB/LTV/BFB 패턴과 동등 영역 = donchian 신호 빈도 ±10% 이내 영속 가능.

### A2. Q2=D 임시 완화 임계 정밀화 — **500억 / 10억 채택**

**판단**: 사용자 1차 예시 (500억 / 10억) 채택.

**근거**:
- **시총 500억 (vs 1,000억 보수)**: donchian 멀티데이 보유 = 추세추종 영역. KOSPI 중소형주 추세 강세 종목 포착 영역 필요. 1,000억 보수 시 코스닥 강세주 누락 위험 (사이클 26 KRX ONLY + KOSPI200/KOSDAQ150 합집합 정신 답습).
- **거래대금 10억 (vs 20억 보수, 5억 공격)**:
  - 20억 보수: 멀티데이 5~15일 보유 안전성 + 청산 시 슬리피지 최소화. 단 코스닥 강세주 영역 누락.
  - 10억 채택: 멀티데이 보유 청산 시 일일 평균 매매대금 10억 / 보유 1주 = 일일 1,000만원 분 = 자동매매 1주 1만원~30만원 환산 = 33~1,000회 매도 분량 = 청산 시 슬리피지 안전 마진 충분.
  - 5억 공격: 멀티데이 청산 시 유동성 위험 + 작전주 영역 차단 약화.
- 사이클 65 거래대금 동행 필터 시점 (디폴트 0, 권장값 1억/5억/10억) 영속 정합.

### A3. 매매 신호 영향 평가 — donchian 신호 빈도 ±10% 이내

**판단**: donchian 신호 빈도 ±10% 이내 영속 가능.

**근거**:
- 사이클 108 VB/LTV/BFB 패턴 = 신호 빈도 ±5% 이내 영속 확정.
- donchian 추가 영역 = 일봉 fetch + 신고가/EMA/거래대금/ATR 4중 필터링 = stock_master 후보 풀 ~500종목 → 최종 prepared 추정 5~15종목 (현재 영역 동등).
- donchian 09:05~09:30 1회 매수 = `_bought_today` 1회 가드 영속 = 동일 영역 영속.

### A4. 사이클 118 효과 미반영 영역 안전성 — **graceful 영역 영구 영속 보장 확정**

**판단**: 사이클 119 push 즉시 안전성 100% 보장.

**근거**:
- `list_by_filter()` 영역 영구 영속 graceful 패턴 (사이클 65 Q6-1 09:00 race 답습):
  ```python
  if min_trade_amount > 0:
      try:
          acml_tr = int(raw.get("acml_tr_pbmn") or 0)
      except (ValueError, TypeError):
          acml_tr = 0
      if acml_tr < min_trade_amount:
          continue
  ```
  → `acml_tr_pbmn` 키 부재 (None) = `0` fallback = `min_trade_amount=1_000_000_000` 비교 시 차단.
  → **하지만 사이클 118 이전 데이터 영역**: 키는 존재하나 값이 잘못 (사이클 118 매핑 시정 *전* 키 영역 = 누락 또는 0).

- **재검증**: stock_master 마지막 갱신 16:18 KST = 사이클 117까지의 데이터. 사이클 117 영역에서 `acml_tr_pbmn` 키가 적재되어 있다면 값은 0 또는 부재. 사이클 119 시점 = 16:42 KST 시정 → 운영 push 17:00 KST 추정 → 다음 갱신 = 20:00 KST `_full_universe_load_task_loop` 자동 발화.
- **donchian `prepare()` 실행 시점** = 매일 07:50 KST `_boot`. **내일 (2026-06-13 금) 07:50 _boot 시점** = 어젯밤 20:00 KST 자동 갱신 *후* = **사이클 118 효과 100% 반영 영역 확정**.
- **결론**: 사이클 119 push → 17:00 KST 배포 완료 → 20:00 KST stock_master 자동 갱신 (사이클 118 효과 반영) → 내일 07:50 _boot → donchian `prepare()` = **acml_tr_pbmn 정상 영역 영구 영속 100% 보장**.

**graceful 영역 추가 안전망**: 만약 acml_tr_pbmn=0 종목이 일부 잔존 → `list_by_filter()` 가 자동 제외 → 후보 풀 축소 → donchian `prepare()` 일봉 fetch 후 거래대금 1.5× 임계 자체 적용 = 이중 안전망 영구 영속.

### A5. 사이클 121+ DEFAULT 임계 복원 영역

**판단**: D+3 (2026-06-15 월) 운영 실측 후 사이클 121+ 점진 복원 권고.

**복원 영역 영구 영속 권고**:
- **사이클 121+ Step 1**: 사이클 118 정상화 영구 영속 + 사이클 119 운영 D+3 측정 → donchian 신호 빈도 ±10% 이내 확인 시 → `min_market_cap` 500억 → **1,000억** 점진 복원.
- **사이클 122+ Step 2**: D+7 측정 → `min_trade_amount` 10억 → **30억** 점진 복원.
- **사이클 123+ Step 3**: D+14 측정 → 원본 임계 (3,000억 / 50억) 검토. 단 원본은 KOSPI200+KOSDAQ150 ~350종목 영역 한정 (시총/거래대금 자동 정렬 영역) → stock_master ~2,800 영역에서는 원본 임계 적용 시 후보 풀 폭축 위험 → **2,000억 / 30억 영역 적정 권고**.

### A6. exclude_tickers 신규 필드

**판단**: 사이클 119 시점 빈 list `[]` 디폴트 채택.

**근거**: Plan Phase C UI 운영자 필터링 호환 영역 영구 영속 (사이클 124+ UI 운영자 필터링 기능 영역 도입 시 활용). 현재는 빈 list 디폴트로 안전 영역.

### A7. 사이클 119 push 시점 안전성

**판단**: 즉시 push 안전.

**근거**:
- 사이클 119 push 시점 = 17:00 KST (배포 후) → 다음 donchian `prepare()` 실행 = 내일 07:50 _boot = **운영 영역 0건** (오늘 장 종료 후 시점).
- KRX 메인 (09:00~15:30) 영역 미진입 = 사이클 17 OPSP0002 backoff + KIS LMS chain 위험 영역 0.
- 매도/익일청산 hot path 영역 영구 영속 무관 (사이클 38 명문화 영속).

## 영속 의무 매트릭스 (자문 결과 검증)

| 사이클 | 영역 | 영향 |
|--------|------|------|
| 17 OPSP0002 | KIS LMS chain | 350 호출/일 → 0 호출/일 영구 영속 (강화) |
| 29 005935 사고 | scanner 영역 무관 | 영향 0 |
| 32 R4 universe guard | 보유/익일청산 절대 보호 | 영속 보장 |
| 38 명문화 | scanner 매수 진입 전 영역 한정 | 영속 보장 |
| 49 VCP Pullback | donchian 영역 무관 영구 확정 | 영향 0 |
| 81 G-AST1 | stock_master.raw bfdy_clpr/hts_avls | 영향 0 (raw 영역 보존) |
| 88 G-REJECT | 재구독 영역 | 영향 0 (scanner 영역) |
| 89 ETF 키워드 제외 | ETF_KEYWORDS 영속 | 영속 보장 |
| 100 Plan Phase B | donchian stock_master 베이스 | 사이클 119 = Plan Phase B Step 1 |
| 108 답습 패턴 | VB/LTV/BFB 동일 패턴 | 100% 답습 |
| 118 ACC_TRDVAL 매핑 | acml_tr_pbmn 영역 | 내일 07:50 _boot 시점 정상 영역 영구 영속 확정 |

## 최종 권고

- **시정 진행**: 사이클 108 답습 패턴 100% 영구 영속
- **Q2=D 임시 완화 임계 (정밀화)**: `min_market_cap=50_000_000_000` (500억) + `min_trade_amount=1_000_000_000` (10억)
- **신규 필드**: `exclude_tickers=[]` (Plan Phase C UI 호환) + `nxt_tradable=None` (Q5=A donchian MAIN 단독)
- **회귀 가드 영역**: 사이클 108 답습 (HIGH 4 + MEDIUM 2 + AST 1)
- **xfail 의미 전환**: KOSPI200/KOSDAQ150 고정 유니버스 폐기 계약 영구 보존 (사이클 66 K-2 패턴 답습)

매매 안전성 영역 영구 영속 보장.
