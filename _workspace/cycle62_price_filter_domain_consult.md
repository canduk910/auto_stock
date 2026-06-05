# 사이클 62 가격 필터 — domain-expert 자문 의뢰서 (6 의제)

> **작성**: team-leader (2026-06-05 13:30 KST, 사이클 61 sync-docs 완료 직후)
> **수신자**: domain-expert (데이/스윙 트레이더 출신)
> **선행 결정 (사이클 60 사후 확정)**:
> - 필터 의도 = 양쪽 밴드 `[min, max]` (저가 + 초고가 동시 차단)
> - 적용 시점 = scanner 조건검색 직후 (전 전략 공통)
> - 사이클 분할 = 백엔드 + 프론트 단일 사이클
> - 위험 등급 = MEDIUM (매수 차단만 — 자금 손실 0, 기회비용만)
> - push 시점 = NXT 애프터 (주말 의무 없음)
> **설계 카드 (1차 sketch)**: `_workspace/cycle62_price_filter_design_card.md`
> **응답 산출물 경로**: `_workspace/cycle62_price_filter_domain_response.md`
> **응답 형식**: RECOMMEND / CONSIDER / AVOID + 근거 (트레이더 시각) + 트레이드오프 + 구현 가이드 (사이클 60 응답 패턴 답습)

---

## 배경

운영 중 1주 폴백 결함이 발생한 사례:
- **저가주**: 1주 = 호가단위 1원 → 작전주 / 거래량 부족 / 변동성 폭주 위험
- **초고가주**: 1주 50만원 = 전략 자금 100만원 인 경우 1 종목에 50% 비중 — 분산 의도 위반. 사이클 49 VCP 단독 30일 0건 매매 결함 진단 중 일부 종목이 이 영역
- **레짐 영향**: defensive 레짐 (cash_min=75) + 초고가 1주 매수 = 전략 자금 부족 → low_funds_cooldown 누적 → 다른 종목 매수 기회비용

해결 의도:
- scanner 조건검색 직후 단일 진실 원천에서 가격 밴드 필터링
- 보유 종목 매도 / 익일청산 영향 0 (사이클 38 명문화 답습 — `tradable_boards` 매수 진입 전용)
- 운영자 슬라이더로 즉시 인지·조정 가능

---

## Q1 — 임계값 디폴트 (저가주/고가주 차단 기준)

**의제**:

저가주 차단 임계 `price_filter_min` 후보:
- (a) 1,000원 미만 차단 — 호가단위 1원 (사이클 32 R4 universe_guard 저거래량 차단과 시너지)
- (b) 5,000원 미만 차단 — 작전주 / 동전주 회피 통상 임계
- (c) 10,000원 미만 차단 — 극단적 보수
- (d) 0 = 비활성 (디폴트 비활성)

초고가주 차단 임계 `price_filter_max` 후보:
- (a) 500,000원 초과 차단 — 1주 = 전략 자금 50% 비중 위험 (현 6 전략 중 momentum/VB/LTV 가 짧은 timing 으로 1주 폴백 즉시 가능)
- (b) 1,000,000원 초과 차단 — 1주 = 전략 자금 100% 가능 (극단적)
- (c) 2,000,000원 초과 차단 — 거의 모든 종목 통과 (LG에너지솔루션·삼성바이오로직스 등 일부만)
- (d) 0 = 비활성 (디폴트 비활성)

운영자 슬라이더 범위 후보:
- min: 0 ~ 10,000원 (1,000원 단위) — 가장 일반적
- min: 0 ~ 50,000원 (1,000원 단위) — 가시화 범위 넓힘
- max: 0 ~ 2,000,000원 (10,000원 단위) — 거의 모든 한국 종목 커버

**자문 요청**:
1. 저가주 임계 디폴트 권고 (a/b/c/d) + 근거 (호가단위 / 작전주 빈도 / KOSPI/KOSDAQ 분포)
2. 초고가주 임계 디폴트 권고 (a/b/c/d) + 근거 (전략 자금 1주 비중 한계 / 1주 폴백 빈도)
3. 운영자 슬라이더 범위 권고 (min/max 각각 step + 상한)
4. 5,000원 / 1,000,000원 권장값에 대한 트레이더 시각 (작전주 회피 + 비중 분산 균형)

---

## Q2 — 전일종가 미확보 처리 (graceful 통과 vs 보수적 제외)

**의제**:

가격 필터 적용 시 비교 대상:
- 옵션 (가): scanner 조건검색 응답의 **`stck_prpr` (당일 현재가)** — `scan_stocks()` 가 이미 사용 중 (L177)
- 옵션 (나): **전일 종가 (`prdy_clpr`)** — `stock_master.raw.prdy_clpr` 또는 KIS `inquire-price` 별도 호출
- 옵션 (다): 두 영역 평균

신규 상장 / KIS API 일시 장애 / `stock_master` miss 시 처리:
- 옵션 (A): graceful 통과 (필터 비활성, 매수 허용) — 사이클 32 R4 `_evaluate_universe_guard` 의 `inquire_ccnl None` 분기 답습 (제외 보류)
- 옵션 (B): 보수적 제외 (필터 활성, 매수 차단) — sniper 트레이딩 시각에서 정보 부재 = 회피
- 옵션 (C): 옵션별 mode 분기 (HARD=B / WARN=A + 경고 / OFF=A)

**자문 요청**:
1. 비교 대상 권고 ((가)/(나)/(다)) + 근거 (당일 갭상승/하락 시 어떤 가격 기준이 트레이더 의도 부합?)
2. 미확보 시 처리 권고 (A/B/C) + 근거 (작전주 위험 vs 정상 종목 기회비용)
3. 신규 상장 종목 (전일 종가 0원) 특수 처리 권고 (필터 전체 skip vs 보수적 차단)
4. **`scan_stocks` 의 `stck_prpr` (당일 현재가) 직접 활용 가능 여부** — 별도 KIS 호출 0건 가능 (Rate Limit 보호) vs 정확도 (당일 변동성 폭주 시 일시적 폭락/폭등 영향)

---

## Q3 — 보유 종목 매도 영향 (매수만 필터 확정 재확인)

**의제 (확정 사항 재확인)**:

본 사이클 가격 필터는 **매수만 필터링**. 매도 / 익일청산 / 손절 / 트레일링 / 15:20 강제청산 영향 0 (사이클 38 명문화 답습 — `tradable_boards` 매수 진입 전용 패턴).

확인 의제:
- (a) 보유 종목 가격이 필터 범위 밖으로 변동 시 (예: 5,000원 매수 → 800원 폭락) 매도 가드 정상 발화 (손절·트레일링 작동)
- (b) 익일청산 종목 가격이 필터 범위 밖 시 청산 의무 우선 (NXT 시장가 / KRX 시장가)
- (c) 보유 종목 추가 매수 (피라미딩) 시 필터 적용 여부 — 사이클 38 의 매수 진입 = 신규 매수만? 또는 추가 매수 포함?
- (d) 본 시스템은 사이클 38 이후 동일 종목 중복 매수 차단 (`registry.is_ticker_blocked_for_buy`) — 피라미딩 자체 없음 → 필터 영향 0

**자문 요청**:
1. 매도 가드 우선순위 절대 유지 권고 (확정) + 근거 (사이클 38 명문화 인용 + 청산 의무 우선)
2. 보유 종목 가격이 필터 범위 밖 변동 시 신호 누수 위험 점검 (예: 손절 미발화 가능성)
3. 익일청산 NXT/KRX 시장가 청산 시 필터 우회 확인 (코드 적용 위치 = scanner 단계 = 매수 후보 진입 직전 → 매도/청산은 별도 경로)
4. 운영자 가시화 — UI 에 "본 필터는 매수만 적용됩니다" 명시 권고 여부

---

## Q4 — 운영 모드 (HARD/WARN/OFF 3 모드 vs HARD 단일)

**의제**:

사이클 31 매수 가드 4 모드 (HARD/WARN/SOFT/OFF) 패턴 답습:
- 옵션 (가): **HARD 단일 모드** — 단순화. min/max 슬라이더만 운영. 비활성 시 min=0 + max=0 (디폴트)
- 옵션 (나): **3 모드 (HARD/WARN/OFF)**
  - HARD: 즉시 차단 + INFO 로그
  - WARN: 매수 허용 + `[price_filter_warn]` WARNING 로그 1행 (트레이더 인지)
  - OFF: 필터 비활성 (디폴트)
- 옵션 (다): **4 모드 (HARD/WARN/SOFT/OFF)** — 사이클 31 답습
  - SOFT: 매수 허용 + 수량 50% 축소 (예: 100주 → 50주). 작전주 영역 위험 분산
- 옵션 (라): **2 모드 (HARD/OFF)** — HARD 단일과 동등 (디폴트 비활성)

**자문 요청**:
1. 운영자 디버깅 편의 vs 코드 복잡도 trade-off 평가 — 트레이더 시각에서 어느 mode 가 가장 자주 사용될까?
2. SOFT 모드 (수량 50% 축소) 가 작전주 영역에서 의미 있는 위험 완화인지 (vs HARD 차단)
3. WARN 모드의 운영 가치 — 디폴트 OFF → WARN 으로 1~2주 운영 후 HARD 전환 단계적 도입 가능성
4. **사이클 31 매수 가드 4 모드와의 mode 키 통합 가능 여부** — `system_config.buy_block_mode` 영역 vs 별도 `price_filter_mode` 키 분리

---

## Q5 — 반영 시점 (Settings 변경 즉시 vs 익일)

**의제**:

사이클 2 `cash_usage_ratio` 답습:
- "Settings 슬라이더로 조정 → **다음 영업일부터 반영**" (사이클 2 정책)

옵션:
- 옵션 (가): **즉시 반영** — Settings PUT 직후 다음 `_scan_loop` (5분 주기) 부터 신규 임계 적용
- 옵션 (나): **익일 반영** — `_boot` 시점 1회 캐시 → 영업일 중 변경 불가 (사이클 2 답습)
- 옵션 (다): **즉시 반영 + 운영 중 변경 시 cooldown** — 5분 grace period 후 적용 (race 차단)

운영 중 변경 시 위험:
- 임계 상향 (max=200만 → max=100만) → 기존 후보 일부 제외 → 매수 신호 누락 (다음 사이클부터)
- 임계 하향 (min=0 → min=5,000) → 기존 저가 후보 차단 → 매수 신호 누락
- 매수 차단 변경은 *기회비용* 만, *자금 손실* 0 → 즉시 반영의 위험도 낮음 (vs cash_usage_ratio = 자금 비중 직접 변경)

**자문 요청**:
1. 즉시 vs 익일 권고 + 근거 (트레이더 디버깅 편의 vs 일관성)
2. cash_usage_ratio 와 정책 일관성 의무인지 — 자금 비중 변경은 익일 / 매수 필터는 즉시 분리 가능?
3. 즉시 반영 시 race / 일관성 보호 권고 (예: `_scan_loop` 5분 주기 + `_eval_universe_guard` 5분 동기화)
4. **`market_regime.buy_block` 60s TTL 캐시 패턴 적용 가능 여부** — `_get_price_filter()` 호출이 매 스캔마다 발생 시 DB 부하 → 60s 캐시 + `invalidate_*()` 토글 즉시 반영

---

## Q6 — funnel 추적 (`strategy_funnel_snapshots` 단계 추가)

**의제**:

사이클 34 `strategy_funnel_snapshots` 답습:
- 현재 step_no: 사이클 39+41 의 8단계 (BFB/VCP/donchian `prepare()` 의 hook) + 최종 `step_no=99`
- momentum 의 경우 `scan_stocks()` 단일 진입점 — funnel hook 없음 (사이클 41 시점 미적용)
- VB/LTV 의 경우 별도 funnel hook 미존재

가격 필터 funnel 추가 옵션:
- 옵션 (가): **단계 추가** — `step_no=10` (가격 필터) 신규 단계, 통과/탈락 ticker + 사유 (`reason="below_min: price=500 < 1000"`) 기록
- 옵션 (나): **별도 prefix 로그만** — `[price_filter_excluded] ticker=... reason=below_min/above_max prdy_clpr=... min=... max=...` (사이클 32 R4 `[universe_excluded]` 패턴 답습)
- 옵션 (다): **두 영역 병행** — funnel + 로그 (가시성 최대)
- 옵션 (라): **funnel 단계 충돌 회피** — 기존 step_no 와 정합성 (현재 1~99 어떻게 분포되어 있는지 사전 점검 필요)

**자문 요청**:
1. funnel 단계 추가 권고 ((가)/(나)/(다)/(라)) + 근거 (트레이더 디버깅 가치 vs UI 복잡도)
2. 가격 필터가 momentum + VB + LTV 에도 적용되는데 momentum/VB/LTV 는 funnel hook 미적용 — 본 사이클에서 funnel hook 추가 의무 인지
3. **기존 step_no 분포 사전 점검 의무 명시** (현재 BFB/VCP/donchian step_no 1~8 + 99 = 가격 필터 step_no 가 어디 자리?)
4. 사이클 41 funnel 진단 패턴 답습 — `[price_filter_funnel] strategy=... step=price_filter survived=N excluded=M reasons={below_min: 3, above_max: 2}` 형식 권장 여부

---

## 추가 의제 (자문 자유 발의)

domain-expert 가 본 자문 의뢰서 외에 트레이더 관점에서 발견한 위험 / 권고 사항이 있으면 *Q7~* 으로 자유 발의. 예시:

- 가격 필터가 시간대별 (PRE_NXT / MAIN / POST_NXT) 임계 분리 의무인지 (NXT 거래량 적은 시각 = 더 보수적?)
- 호가단위 (사이클 호가단위 헬퍼 `util/tick_size.py`) 와 임계값 정합성 (예: 5,000원 미만 호가 1원, 5,000~10,000원 호가 5원)
- 운영자 슬라이더 변경 후 *현재 보유 종목 중 필터 범위 밖* 인 종목 가시화 (UI 경고 패널)
- 사이클 49 VCP 단독 30일 0건 매매 결함과 본 필터의 시너지 / 충돌 (Pullback 회복 종목 일부가 본 필터 차단되면 VCP 매매 기회 더 좁아짐)

---

## 응답 후속 처리 (team-leader 인계)

domain-expert 자문 응답 (`_workspace/cycle62_price_filter_domain_response.md`) 수신 후:
1. team-leader 가 Q1~Q6 RECOMMEND 채택 → `_workspace/cycle62_price_filter_design_card.md` 의 *TBD-Qn* 영역 확정
2. Q7+ 자유 발의가 본 사이클 범위 영향 시 사용자 결정 인계 (범위 확장 vs 별개 카드 발의)
3. tdd-engineer Red 명세 작성 (사이클 60/61 답습) — 백엔드 + 프론트 + 통합
4. backend-dev + frontend-dev Green 발주
5. tester Verify (카테고리 분리 측정 + flakiness 차단)
6. sync-docs + 사용자 명시 commit + push (NXT 애프터 시점)

---

## 안전 가드

- 본 자문 의뢰서 작성 자체는 운영 영향 0 (문서 산출물만)
- 사이클 62 실제 발주 (코드 변경) 은 사용자 명시 지시 후 별도 진행
- domain-expert 자문은 사이클 60 응답 패턴 답습 — RECOMMEND/CONSIDER/AVOID + 근거 + 트레이드오프 + 구현 가이드
