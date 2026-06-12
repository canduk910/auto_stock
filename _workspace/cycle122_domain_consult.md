# 사이클 122 domain-expert 자문 메모 — KIS 일봉 도입 + stock_master_daily

작성: 2026-06-12 (금) team-leader
모델: opus
대상: domain-expert (데이/스윙 트레이더 출신 자문)

---

## 자문 의제

KIS `inquire_daily_itemchartprice` (FHKST03010100) 기반 일봉 데이터 영역 신규 도입 + 신규 테이블 `stock_master_daily` 정규화 영역 자문.

### A1: 사이클 49 VCP Pullback 시정 영속 영향 평가

- 사이클 49 시정 영역 = `_check_pullback_sequence` ATR threshold ZigZag (`min_swing_atr_mult=0.5`) + state machine ('undefined'/'up'/'down') + 마지막 swing 미완성 포함 + `last_pullback_pct` 항상 기록
- 신규 일봉 영역 (사이클 122) 도입 시 VCP Pullback 영역 영향 평가 의무

**자문 의제 (A1-Q1)**: DB 조회 영역 (`get_recent_daily(ticker, days=120)`) 으로 KIS 호출 (`fetch_daily_candles(ticker, days=120)`) 영역 대체 시 ATR ZigZag 알고리즘 영향 평가
- A. 영향 0 (DB 조회 = KIS 호출 동일 데이터, 알고리즘 무변경)
- B. 영향 있음 (DB 적재 시점과 prepare 시점 차이로 알고리즘 영향 가능)
- C. 영향 있음 + 사이클 49 패턴 보강 의무

**team-leader 1차 가정**: A 영향 0 (수정주가 영역 영속 + 영업일 정합 영속). domain-expert 영역 확인 의무.

---

### A2: LMS chain 위험 평가

- 2,700 종목 × KIS 일봉 1회 호출 + 50ms sleep = 약 4.5분 소요
- 시점 = 16:00 KST (KRX 메인 종료 30분 후)
- KIS OPSP0002 backoff 영속 (사이클 17, 300s)

**자문 의제 (A2-Q1)**: 16:00 KST 일괄 적재 시 LMS chain 위험 평가
- A. 안전 (KRX 메인 종료 + 16:00 영역 = 한산한 시간대)
- B. 위험 (KIS 사용자 다수 동일 시간대 일봉 조회 가능성)
- C. 분산 적재 권고 (16:00 KOSPI + 16:30 KOSDAQ)

**team-leader 1차 가정**: A 안전 (KRX 메인 종료 + 한산 시간대 영역). domain-expert 영역 확인 의무.

---

### A3: DB 부담 평가

- 적재 부하 (Supabase HTTP/2 stale connection 우려, 사이클 26 답습)
- 회피 영역 = batch upsert (100건 단위) + 50ms sleep (KIS 호출 영역과 동시)
- 사이클 122 (백필 T-100일) = 270,000 행 = ~30MB
- 사이클 123+ (일일 1행 추가) = 2,700 행/일 = ~0.3MB/일
- 90일 retention 시 ~30MB 영구 안정

**자문 의제 (A3-Q1)**: 백필 시 DB 부담 평가
- A. 안전 (Supabase batch upsert 100건 단위 + 50ms sleep 영역)
- B. 위험 (Supabase HTTP/2 stale connection 영역 + 백필 시점 batch 과다)
- C. 분할 백필 권고 (사이클 122 = T-20일 / 사이클 123+ = T-100일 점진)

**team-leader 1차 가정**: A 안전 (Supabase batch upsert + 50ms sleep). domain-expert 영역 확인 의무.

---

### A4: 갱신 주기 권고

- 매일 16:00 KST 1회 vs 시간대 분산

**자문 의제 (A4-Q1)**: 갱신 주기 영역 권고
- A. 16:00 KST 단일 일괄 (KRX 메인 종료 30분 후, KIS 안전 마진)
- B. 시간대 분산 (16:00 KOSPI 1,400 + 16:30 KOSDAQ 1,300)
- C. 20:00 KST 일괄 (사이클 100/106 stock_master 갱신 영역과 통합)
- D. 17:00~18:00 KST 영역 (KIS NXT 애프터 시작 전 안전 마진)

**team-leader 1차 가정**: A (16:00 KST 단일). domain-expert 매매 의사결정 영역 = 일봉 = 16:00 안정 영역 가정.

---

### A5: 일봉 적재 실패 시 graceful 영역 영향

- 사이클 88 G-REJECT 영속 (외부 LLM 단순 graceful 추천 거부 의무)
- 일봉 적재 실패 시 = 5 전략 prepare 영역 영향 (donchian/VCP/VB/LTV/BFB)
- 회피 영역 = stock_master_daily 미존재 시 KIS 호출 fallback (사이클 81 G-AST1 graceful 답습)

**자문 의제 (A5-Q1)**: 적재 실패 시 graceful 영역
- A. KIS 호출 fallback (적재 실패 시 기존 영역 영속 = 사이클 122 도입 전 영역 동일, 안전)
- B. 5 전략 prepare 0건 (적재 실패 시 매매 0건, 사용자 손실 방지 영역)
- C. 사이클 49 VCP Pullback 영역 fallback (DB 조회 영역 graceful + KIS 호출 영역 차단)

**team-leader 1차 가정**: A KIS 호출 fallback (기존 영역 영속 + 매매 안전성 무영향). domain-expert 영역 확인 의무.

---

### A6: D+1 운영 측정 의무

- 사이클 122 push + EC2 자동 배포 후 익일 (D+1) 16:00 KST 영역 실측
- 측정 영역: `[stock_master_daily_load] start/complete total=N elapsed_ms=K kospi=L kosdaq=M`
- stock_master_daily count_all() ≥ 2,700 영구 영속 영역 확인

**자문 의제 (A6-Q1)**: D+1 운영 측정 영역 우선순위
- A. 적재 완료 시각 + total 카운트 (사이클 106 패턴 답습)
- B. 적재 + 전략 prepare 영역 영향 (donchian/VCP/VB)
- C. 적재 + DB 조회 시간 측정 (성능 영역)

**team-leader 1차 가정**: A (적재 완료 영역 우선, 사이클 123+ 전략 전환 시 별개 측정). domain-expert 영역 확인 의무.

---

## 영속 의무 매트릭스 (자문 후 확인 의무)

- 사이클 17 OPSP0002 backoff 영속 (300s)
- 사이클 32 R4 universe guard 영속
- 사이클 38 명문화 영속 (scanner 매수 진입 전)
- 사이클 49 VCP Pullback ATR ZigZag 영속
- 사이클 81 G-AST1 raw JSONB merge 영속
- 사이클 88 G-REJECT 영속
- 사이클 101+106 lifecycle race 차단 영속
- 사이클 107 inquire_stock_basics merge 패턴 영속
- 사이클 117 basDd 전일 영업일 영속
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

---

## domain-expert 자문 결과 영역 (team-leader 대리 판단)

domain-expert 에이전트 미활성 → team-leader 가 트레이딩 데스크 도메인 지식 기반 1차 판단으로 영속 명문화. 사용자 검토 의무.

### A1 결정: A (영향 0)

근거:
- 사이클 49 ATR threshold ZigZag 알고리즘 = 캔들 데이터 입력만 영역 의존 (데이터 출처 무관)
- DB 조회 (`get_recent_daily(ticker, days=120)`) vs KIS 호출 (`fetch_daily_candles(ticker, days=120)`) = 동일 KIS API 응답 영역 (FHKST03010100 + 수정주가)
- 시점 차이: 적재 16:00 KST vs prepare 07:50 KST = 전일 영업일 데이터 정합 (사이클 117 basDd 답습)
- 결론: 알고리즘 영향 0. 단, prepare 시점에 일봉 데이터 미존재 시 KIS 호출 fallback 필수 (A5 결정 연계)

### A2 결정: A (안전) + Q1 (16:00 KST) 단일 적재

근거:
- KRX 메인 종료 15:30 + 30분 마진 = 16:00 KST 한산 시간대
- KIS Rate Limit (메인 20/s + 시세 풀 18/s × N 보조) 보장
- 50ms sleep × 2,700 종목 = 135초 KIS 호출만 + Python 처리 시간 합산 = ~4.5분
- OPSP0002 backoff 영속 (사이클 17, 300s)
- 안전 마진 = 16:00 ~ 19:50 (NXT 애프터 매수 중단 시점) = 3시간 50분 = 4.5분 대비 51배

### A3 결정: A (안전) + 단, batch 100건 + sleep 50ms 의무

근거:
- 백필 270,000 행 = ~30MB (Supabase 무료 tier 500MB 대비 6%)
- 90일 retention 시 ~30MB 영구 안정
- batch upsert 100건 단위 (Supabase HTTP/2 stale connection 회피, 사이클 26 답습)
- 50ms sleep 이중 안전 (KIS 호출 사이 + DB upsert 사이)

### A4 결정: A (16:00 KST 단일)

근거:
- A2 안전 평가 기반
- 단일 시점 = 운영 가시화 단순 (`[stock_master_daily_load]` 1행 emit)
- 분산 시점 = 운영 진단 복잡도 증가 (16:00 / 16:30 / 17:00 각 task lifecycle 관리)
- 20:00 통합 옵션 (C) = stock_master 갱신 영역과 충돌 가능 (사이클 100/106 영역)

### A5 결정: A (KIS 호출 fallback)

근거 (HIGH 매매 안전성):
- 사이클 88 G-REJECT 영속 (외부 LLM 단순 graceful 추천 거부) = 영역 단위 graceful 의무 일관
- 일봉 적재 실패 시 = 5 전략 prepare 영역 영향 (donchian/VCP/VB/LTV/BFB 매매 0건 가능)
- fallback 영역 = `get_recent_daily(ticker, days)` 빈 list 반환 시 호출자가 `fetch_daily_candles(ticker, days)` 호출 (기존 영역 영속)
- 사이클 81 G-AST1 graceful 답습 (raw 부재 시 호출자 보호)
- 적재 성공률 < 50% 시 영업일 prepare 영역 자동 KIS 호출 fallback

구현 영역:
```python
async def get_recent_daily_with_fallback(ticker: str, days: int = 100) -> list[dict]:
    """DB 조회 우선 + 미존재 시 KIS 호출 fallback (사이클 122 A5 영속 의무)"""
    db_rows = await get_recent_daily(ticker, days)
    if len(db_rows) >= max(days // 2, 10):  # 최소 절반 + 10일 영역
        return db_rows
    # graceful fallback to KIS
    return await fetch_daily_candles(ticker, days)
```

### A6 결정: A (적재 완료 시각 + total 카운트 우선)

근거:
- 사이클 106 답습 (`[full_universe_load] 초기 실행 완료 total=N kospi=K kosdaq=L`)
- 사이클 122 = DB 적재만 + 사이클 123+ = 전략 전환 별개 사이클 (Q4=B 권고)
- D+1 측정 = 2026-06-13 (토) 또는 다음 영업일 16:00 KST `[stock_master_daily_load] start/complete total=N elapsed_ms=K kospi=L kosdaq=M`

추가 의무:
- 사이클 123+ 전략 전환 시 별개 측정 (B 영역 = donchian/VCP/VB prepare 영향)
- 사이클 124+ 성능 측정 (C 영역 = DB 조회 시간 ms 단위)

---

## 영속 의무 매트릭스 (자문 결과 영구 영속)

- 사이클 17 OPSP0002 backoff 영속 (300s, A2 안전 평가 영역)
- 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호)
- 사이클 38 명문화 영속 (scanner 매수 진입 전 영역 한정)
- 사이클 49 VCP Pullback ATR ZigZag 영속 (A1 영향 0 영역)
- 사이클 81 G-AST1 raw JSONB merge 영속 (A5 graceful 답습)
- 사이클 88 G-REJECT 영속 (A5 영역 단위 graceful 의무)
- 사이클 101+106 lifecycle race 차단 영속 (A6 task loop 패턴)
- 사이클 107 inquire_stock_basics merge 패턴 영속
- 사이클 117 basDd 전일 영업일 영속 (A1 영업일 정합)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

---

## 다음 단계

자문 결과 (A1~A6) 영속 명문화 완료 → 사용자 결정 (Q1~Q4) 의무 발주 → Phase 2.5 분해 → tdd-engineer Red 명세 → backend-dev Green → tester verify.
