# 외부 LLM 의견서 도메인 검토 — 시세 수신 오류 관점

**일자**: 2026-06-09
**컨설턴트**: domain-expert (데이/스윙 트레이더 출신)
**산출물 범위**: 자문 단독 (코드 변경 0)
**선행 영속**: 사이클 17/29 R1~R3/32 R4/55 R-1/66/67/74

---

## 총평 (한 줄)

외부 LLM 의견은 **stale 판정 단위 (종목 vs 세션) 의 트레이드오프를 정확히 짚었으나, "전체 WS 메시지 기준" 단일 채택은 도메인 의무 (HIGH 보유 종목의 매도 hot path 보장) 와 정면 충돌**한다. 본 시스템은 이미 **사이클 29 R2 silent_inactive (세션 단위, 3중 가드)** + **R1 종목 단위 (시간 기반 force_retry)** 의 **2 계층 하이브리드**로 외부 추천을 *부분 답습*한 상태다. 원인 가능성 분포 (40/25/20/10/5) 는 *도메인 실측* 과 어긋난다 — 실제 비중은 **상태 불일치 < 5% / Pool 구조 ≈ 0% / WS 장애 ≈ 15~20% / stale 과민 ≈ 30% / reconnect 꼬임 ≈ 10%**.

---

## Q1 — "종목별 stale" vs "전체 WS stale" 도메인 평가

### 1-1. 거래량 적은 종목의 정상 tick 빈도 실측 (도메인 감각)

| 종목군 | KRX 메인 정상 tick 빈도 | NXT 시간 |
|--------|------------------------|---------|
| 대형주 (삼성/SK하이닉스/NAVER) | 초당 5~50 tick | 분당 1~5 tick |
| 코스닥 중형주 (테마 활성) | 초당 1~10 tick | 분당 0~2 tick |
| 우선주 (삼성전자우 등) | 분당 1~10 tick | 분당 0~1 tick |
| ETF (KODEX 200 등) | 초당 1~5 tick (LP 호가) | 분당 0~1 tick |
| 동전주 / 작전주 | 분당 0~5 tick (체결 공백 5~30분 정상) | 거의 없음 |
| 거래정지 / 정리매매 | 0 (분/시간 단위 공백) | 0 |

**핵심**: `STALE_FRESHNESS_SECS=60` 영속은 **대형주 + 코스닥 활성주** 기준 적정. 우선주/동전주/ETF/장마감 직전은 **정상 공백이 60s 초과** 빈번. 외부 LLM 의 "정상 종목도 계속 재구독 루프" 우려는 **도메인적으로 타당**.

### 1-2. 15:25~15:30 + NXT 정상 tick 빈도

- KRX 메인 15:20~15:30 동시호가: **체결 0** (호가 누적만, 15:30:00.xx 일괄 체결) → 60s stale 위양성 발생 영역
- NXT POST (15:40~20:00): 시장조성자 슬림, **분당 0~1 tick 정상** → 종목 단위 stale 판정 시 거의 모든 후보가 stale
- NXT PRE (08:00~09:00): 호가 두께 약함, 분당 0~2 tick

**현 영속 보강**: 사이클 32 R4 universe guard 가 **stale + today_volume < 10,000 + 보유 외** 조건으로 unsubscribe → **NXT 시간대 위양성은 universe guard 가 흡수**. 다만 KRX 15:20~15:30 동시호가 영역은 별도 가드 없음 (5분 윈도우).

### 1-3. 외부 추천 "전체 WS 기준" 채택 시 도메인 위험 (HIGH)

**위험 시나리오**:
- SK하이닉스 활성 (초당 30 tick) + 삼성전자 정지 (5분 무거래) → 세션 fresh_ratio 1/2 = 50% > 0.2 → **세션 정상 판정** → 삼성전자 진짜 silent (KIS LMS 개별 종목 정지) **미감지** → 보유 시 매도 hot path 마비
- **2026-05-29 사이클 29 005935 사고**: 삼성전자우 (HIGH 우선) 가 메인 편중으로 8분 영구 잔류 → 매도 미체결 위험. 이 사고의 root cause = *종목 단위 가시성*이 있었기에 진단 가능했음. 전체 WS 기준이면 **사고 자체를 발견 못 함**.

**도메인 권고**: **종목 단위 + 세션 단위 2 계층 하이브리드 영속 (현 상태)**. 외부 추천 *단일 전환은 거부*. 대신 **보유 / `_pending_next_day_clear` 만 종목 단위 60s stale 유지** + **후보 종목은 universe guard + 5분 윈도우로 완화** 검토 가능 (사이클 87+ 카드 후보).

### 1-4. 사이클 29 R2 가 외부 추천 부분 답습?

**YES — 정확히**. 사이클 29 R2 silent_inactive 는 `fresh_ratio < 0.2 + subscribed >= 5 + 5분 지속` *세션 단위* 3중 가드 = 외부 추천 "전체 WS 메시지 기준 stale" 의 **세션 단위 구현체**. 외부 LLM 은 본 시스템이 이미 답습했음을 모름.

---

## Q2 — "상태 불일치 25%" 도메인 평가

### 2-1. SubscriptionRegistry 단일 통합 시 KIS 41 한도 분산 영향

**도메인 위험 (HIGH)**: KIS WebSocket 세션당 41 구독 한도는 **물리적 KIS 정책** (앱키 단위). 단일 Registry 로 추상화하면 **세션 매핑 로직이 Registry 내부 캡슐화**되는 것은 가능하나, **bypass_limit=True HIGH 우선 보장 + 멀티 세션 라운드로빈 + active=true 부분 인덱스** 영역은 도메인 의무. Registry 가 이 의무를 흡수해야 함 — 단순 dict 통합은 **사이클 29 R3 priority 분리 회귀 위험**.

### 2-2. `_subscriptions` vs `_subscriptions_acked` 분리 영속 의무

**영속 의무 = YES**. KIS WebSocket 은 **SUBSCRIBE 송신 ↔ ACK 수신 사이 race** 존재 (수십 ms~수초). orphan ACK (이미 unsubscribe 한 종목 ACK 늦게 수신) 시 `_subscriptions_acked` 가 분리 보존돼야 *진짜 구독 상태 vs KIS 서버 인지 상태* 정합 가드 가능. **단일 통합 시 race window 영구 silent 결함 위험** — 사이클 67 G-15/G-17 AST 영구 가드 회귀.

### 2-3. KIS LMS / 앱키 정지 chain 영속 가능?

**가능 — 단 단일 Registry 가 OPSP0002 backoff (사이클 17) + silent_inactive 세션 cap (R2) 분기 영속 흡수 조건**. 외부 추천 단순 통합 시 **시간당 세션당 2회 cap 회귀 → KIS 앱키 정지 chain 위험 재발**.

**도메인 권고**: 상태 불일치 25% 가설은 **도메인 실측과 어긋남**. 현 영속 4 dict (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`) 는 *분리 의무*가 있는 영역. 외부 LLM 은 race / KIS 정책 / 멀티 세션 한도 영역을 모름.

---

## Q3 — "reconnect 꼬임 20%" 도메인 평가

### 3-1. 4중 안전망 단일화 위험

**HIGH 위험**. 4중 안전망 (F1 / `_scan_loop` 5분 / K stale watcher 120s / `_resubscribe_stale_priority` 5분) 은 **각각 다른 시간 척도 + 다른 트리거**:

| 안전망 | 시간 척도 | 트리거 |
|-------|----------|--------|
| F1 | 즉시 (재연결 1회) | 소켓 disconnect 이벤트 |
| `_scan_loop` | 5분 | 스캐너 후보 갱신 |
| K stale watcher | 120s | 종목별 tick 부재 |
| `_resubscribe_stale_priority` | 5분 | priority HIGH 우선 |

**단일 restore 로 통합 시**: F1 즉시 영역 손실 → 매도 hot path **수초~수분 공백** → 보유 종목 stop loss 미발화 위험. 사이클 29 005935 8분 잔류 사고 재현 위험.

### 3-2. 보유/익일청산 절대 보호 영역 영향

**단일 restore 가 우선순위 분기 (bypass_limit=True/False) 흡수 가능** 조건이면 보장 가능. 단 외부 LLM 의견서가 *우선순위 영역 명시 없음* → 단순 통합 시 **CLAUDE.md "절대 깨지 말 것" 위반**.

### 3-3. KIS 거부 코드 영역별 분리 복구 영속 필요

**필수**. OPSP0002 (이미 구독) vs APBK0918 (장 운영시간 외) vs 5xx (서버 오류) vs 토큰 만료는 **복구 전략이 완전 다름**:
- OPSP0002 → backoff (사이클 17) 후 skip
- APBK0918 → NXT 좀비 차단 (사이클 55 R-1 TTL)
- 5xx → 재시도 + dedupe (사이클 18/76)
- 토큰 만료 → 자동 재발급 (사이클 56-E)

단일 restore 영구 차단.

---

## Q4 — "실제 WS 장애 5%" 도메인 평가

**도메인 실측 (사이클 74 `[ws_action_summary]` + 사이클 76 api retry 5분 collector 기준 추정)**:

| 장애 유형 | 실측 빈도 (영업일 기준) |
|----------|----------------------|
| OPSP0002 ALREADY (정상 동작) | 일 100~500건 (재구독 race) |
| 5xx HTTP | 일 10~50건 (recovered 1.0x 정상) |
| 토큰 만료 자동 재발급 | 일 1~2건 (자정 + 12시간) |
| 진짜 KIS WS 끊김 (재연결 필요) | 주 1~3건 |
| 앱키 정지 / LMS 차단 | 분기 0~1건 (사이클 17/29 R2 이후 0건) |

**평가**: 외부 LLM "5%" 추정은 **앱키 정지 빈도만 보면 타당**, 단 OPSP0002/5xx 합산 빈도는 일 100건+ → **20% 영역**이 도메인 정합. 외부 LLM 의 빈도 감각이 KIS 운영 안정성을 *과대평가*함.

---

## Q5 — 4 계층 분할 도메인 영향

### 5-1. 체결통보 영역 분리 + 사이클 38 명문화 영속

**조건부 가능**. RealtimeManager 가 H0STCNI0/H0STCNI9 (체결통보) 와 H0STCNT0/H0STASP0 (시세) 를 **물리적 다른 세션**으로 분리 유지하면 가능. 단 4 계층 추상화로 *논리 통합* 하면 **CLAUDE.md "체결통보 구독 제거 금지" 위반 잠재 회귀** — 시세 세션 stale 복구 시 체결통보 세션 동반 reconnect 하면 PENDING 주문 누락 위험.

사이클 38 `tradable_boards` 매수 진입 전용 명문화는 `risk.on_tick` 의 분기 로직 → StrategyEngine 영역. 4 계층 분할 시 **이 분기를 StrategyEngine 내부에 보존**해야 함 (RealtimeManager 가 매도 tick 을 차단하면 안 됨).

### 5-2. SubscriptionRegistry 단일 영역에서 41 한도 + 멀티 세션 + HIGH bypass 보장

**가능 — 단 Registry 가 다음 영역 모두 흡수 조건**:
- 멀티 세션 라운드로빈 (`_ticker_to_session`)
- HIGH 우선 bypass_limit=True (사이클 29 R3)
- ACK race 분리 (`_subscriptions_acked`)
- KIS 거부 코드 backoff 분기 (OPSP0002 / APBK0918 / 5xx)
- silent_inactive 세션 cap (사이클 29 R2)

**도메인 권고**: 외부 추천 4 계층 추상화는 *논리적으로 깔끔*하나, KIS 도메인 의무 5종 (41 한도 / HIGH bypass / ACK race / 거부 분기 / 세션 cap) 을 단일 추상화에 흡수하면 **Registry 자체가 비대화 (사이클 67 stale_manager 분해 회귀)**. 점진적 추출 (Phase 2-B SubscriptionRegistry 만 단독 사이클) 권고.

---

## 외부 의견 타당 vs 위험 영역 매트릭스

| 항목 | 도메인 평가 |
|------|-----------|
| stale 단위 (종목 vs 세션) 트레이드오프 인식 | **타당** (사이클 29 R2 부분 답습 모름) |
| "전체 WS 기준 단일 채택" | **위험** (HIGH 종목 매도 hot path 마비, 005935 사고 재현) |
| "상태 불일치 25%" | **부정확** (실제 < 5%, 4 dict 분리 의무) |
| "reconnect 단일화" | **위험** (4중 안전망 시간 척도 다름, KIS 거부 분기 다름) |
| "실제 WS 장애 5%" | **과소 추정** (실제 ≈ 20%, OPSP0002/5xx 합산) |
| 4 계층 분할 (Registry / Dispatcher / Engine) | **조건부 타당** (점진 추출 시) |
| 우선주/ETF/동전주 정상 공백 인식 | **타당** (사이클 32 R4 universe guard 가 이미 흡수) |
| 장마감 직전 (15:20~15:30) stale 위양성 | **타당 + 미흡 영역** (현 영속 미보강, 후속 카드 후보) |

---

## team-leader 인계 — 사이클 87+ 후속 카드 후보

### 카드 #A (MEDIUM) — 후보 종목 stale 임계 완화
- **근거**: Q1-3 도메인 위험 + 우선주/ETF/동전주 정상 공백 인식
- **시정**: HIGH (보유/`_pending_next_day_clear`) = `STALE_FRESHNESS_SECS=60` 유지, LOW (후보) = `STALE_FRESHNESS_SECS_LOW=300` 신규 도입 + universe guard 영속 보장
- **회귀 가드**: 사이클 29 005935 사고 H 4 freezegun 재현 PASS 영속 + LOW 후보 5분 임계 신규 케이스
- **위험**: 후보 종목 진짜 silent 5분 지연 감지 → 매수 기회 손실 (도메인 수용 가능, 매도 hot path 무관)

### 카드 #B (LOW) — 15:20~15:30 동시호가 stale 가드
- **근거**: Q1-2 KRX 동시호가 영역 정상 공백 (체결 0)
- **시정**: K stale watcher 가 15:18~15:32 시간대 stale 판정 skip + `[stale_closing_auction_skip]` INFO
- **회귀 가드**: freezegun 15:25 + tick 0 → stale 판정 0건

### 카드 #C (LOW, 후속 운영 측정) — OPSP0002 / 5xx / 토큰 만료 빈도 영속 측정
- **근거**: Q4 도메인 실측 vs 외부 LLM 5% 추정 격차 정량 검증
- **시정**: 사이클 74 `[ws_action_summary]` + 사이클 76 api retry collector 영속 운영 1주 측정 후 외부 의견 재평가

### 거부 카드 — 외부 추천 4 계층 분할 단일 사이클
- **이유**: SubscriptionRegistry 단일 흡수 영역 5종 (41/bypass/ACK/거부/cap) → 비대화 위험 + 회귀 위험 HIGH. 사이클 67 stale_manager 분해 패턴 답습 (Phase 2-A 3 단계 분할) 권고.

---

## 결론

외부 LLM 의견서는 **stale 트레이드오프 도메인 직관은 정확**하나, **본 시스템 영속 패턴 (사이클 17/29/32/55/66/67/74) 의 답습 깊이를 모름**. 단일 채택 시 **HIGH 보유 종목 매도 hot path 마비 + 005935 사고 재현 위험**. 도메인 권고 = **카드 #A/#B/#C 단계적 채택**, 4 계층 분할은 **점진 추출 (Phase 2-B 단일 사이클)** 권고. 영속 4중 안전망 + 2 계층 stale + 4 dict 분리 + KIS 거부 분기 = **모두 도메인 의무 영역, 영속 유지**.
