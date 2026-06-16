# 사이클 149 domain-expert 자문 — 종목별 H0UNMKO0 구독 확장 + VI/거래정지 stale 회피

작성: 2026-06-16
요청자: team-leader (사이클 149 발주)
범위: H0UNMKO0 종목별 구독 + VI/거래정지 시 stale 판정 회피

---

## 의제 5건

### 의제 1 — VI_CLS_CODE 정본 코드값

**질문:** VI_CLS_CODE 활성/해제 코드값은 무엇인가? "0"/"1" 인가, "N"/"Y" 인가?

**도메인 권고:**

KIS 공식 H0UNMKO0 응답 정의에는 코드값 매핑이 누락되어 있다. KIS 공식 inquire_vi_status REST 응답 `vi_cls_code` 코드 정의를 기반으로 추정 = **"0" = 해제 / "1" = 활성 (정적 또는 동적)**. OVTM_VI_CLS_CODE 도 동일.

**채택안:** 구현 시 **enum 처리 금지** — 단순히 truthy 매핑 (`code not in ("", "0", None)` 시 활성). KIS 가 향후 "2"(정적) / "3"(동적) 등으로 세분화해도 호환. TRHT_YN 도 동일 패턴 (`"Y"` = 정지, 그 외 = 해제).

**반례:** "0" 대신 빈 문자열로 해제 표시하는 KIS API 도 다수 있음 (사이클 95 unknown 영역). 코드값 화이트리스트 대신 **블랙리스트 ("0", "", None = 비활성)** 채택.

---

### 의제 2 — MAX_SUBSCRIPTIONS=41 vs H0UNMKO0 독립성

**질문:** H0UNMKO0 종목별 구독 (~30종목) 이 시세 TICK 구독 41 한도와 별개인가, 공유하는가?

**도메인 권고:**

KIS 공식 LMS 한도는 **TR_ID 무관, 세션당 총 41 구독**으로 알려져 있음. H0UNMKO0 도 동일 한도 적용된다.

**채택안:** H0UNMKO0 는 **체결통보(H0STCNI0) + 통합 장운영(H0UNMKO0/005930)** 와 동일하게 **메인 세션 단일** + **`bypass_limit=True` 적용** (보유/익일청산 시세 TICK 와 동일 보호 등급). 단, **cap 의무**: H0UNMKO0 종목 ≤ 20 으로 자체 제한. 메인 세션 슬롯 = TICK 41 + 체결통보 1 + H0UNMKO0 시장 1 + 종목별 H0UNMKO0 ≤ 20 = 최대 63 (KIS LMS 한도 41 초과 영역) — **bypass_limit=True 가드만 의존**. 보조 세션은 H0UNMKO0 절대 금지 (체결통보 메인 단일 패턴과 동일).

**반례:** KIS LMS chain 사고 위험 영역 직결. **자문 사이클 17 OPSP0002 backoff 300s 패턴 영구 영속 답습 의무**. 종목별 H0UNMKO0 SUBSCRIBE 도 backoff 영역 진입 시 자연 차단.

---

### 의제 3 — 보유 + 후보 합집합 적정 cap

**질문:** 종목별 H0UNMKO0 구독 대상은 어떻게 결정하나? 보유 + 익일청산 + 전략 후보 합집합 = 운영 실측 ~30~80 종목.

**도메인 권고:**

H0UNMKO0 데이터는 *시세 데이터 보조 신호* 영역 (VI/거장정지 시 시세 미수신 = 정상). 따라서 **시세 구독 풀과 동일 우선순위 정책 답습**:
- HIGH (보유/익일청산) → 종목별 H0UNMKO0 **반드시 구독** (cap 무시, 손절 평가 안전 우선)
- LOW (전략 후보) → 종목별 H0UNMKO0 **cap=20 적용** (KIS LMS 안전 마진)

**채택안:**
- HIGH 종목 = bypass_limit=True (cap 밖에서도 강제 구독)
- LOW 종목 = cap=20 (sorted 결정적 순서로 결정)
- 합계 = HIGH (보통 0~10) + LOW (20) = ~20~30 종목 (보수적)

**반례:** 보유 종목이 41 초과 시 (현실적으로 거의 없음) HIGH 단독 cap 위반 WARNING + 강제 구독. 사이클 66 K-10 `[stale_priority_resubscribe_cap_exceeded]` 패턴 답습.

---

### 의제 4 — REST inquire_vi_status 부팅 1회 적정성

**질문:** WebSocket H0UNMKO0 가 구독 시점 *이전* (07:50 _boot 시점) VI 활성 종목을 어떻게 알 수 있나?

**도메인 권고:**

부팅 시점 = 07:50 KST = 장 시작 *전* = VI 활성 종목 거의 없음. 즉 부팅 폴백은 **운영 안전 마진 형식**:
- REST `inquire_vi_status` 1회 호출 (FHPST01390000)
- 응답 = 직전 영업일 또는 당일 시작 직후 VI 종목 리스트 (`vi_cls_code != "0"`)
- `_vi_active_tickers` set 사전 등록 → WebSocket 구독 시점 즉시 활용

**채택안:** Q2=A 채택 (자문 정합). 단, **부팅 1회만** + **graceful 폴백** (KIS 거부 시 set 비워 시작, WebSocket 수신 후 자연 보충).

**반례:** 운영 실측 부팅 시 VI 활성 = 0~3 종목 (극히 드묾). 따라서 REST 호출 결함 시 매매 안전성 영향 0. WebSocket 수신만으로 충분.

---

### 의제 5 — 장 임시연장 MRKT_TRTM_CLS_CODE stale 회피 범위

**질문:** MRKT_TRTM_CLS_CODE (장 임시연장) 도 stale 회피 대상에 포함하는가?

**도메인 권고:**

MRKT_TRTM_CLS_CODE 는 **전체 시장 단위** 신호 (특정 종목 단위 아님). 임시연장 시 모든 종목 시세 송수신 유지. stale 회피와 **무관**.

대신 stale 회피 대상은 **종목 단위 신호 3 영역**:
1. **VI 활성** (VI_CLS_CODE != "0" or OVTM_VI_CLS_CODE != "0") — VI 발동 시 시세 일시 중단 (2~10분)
2. **거래정지** (TRHT_YN == "Y") — 시세 영구 중단 (수시 ~ 종일)
3. **종목상태 이상** (ISCD_STAT_CLS_CODE 정지/관리 상태) — 시세 미수신 정합

**채택안:** stale 회피 대상 = `_vi_active_tickers` ∪ `_halt_active_tickers` 단일 set (3 영역 통합 — 코드 단순화). MRKT_TRTM_CLS_CODE 는 **무시** (운영 로그만).

**반례:** 향후 KIS 가 MRKT_TRTM_CLS_CODE 의미를 확대해 종목별 신호로 사용하면 재검토 필요. 현재는 시장 전체 신호 영역 확정.

---

## 영속 의무 매트릭스 (자문 채택 결과)

| 영역 | 채택 | 사유 |
|------|------|------|
| 의제 1 | "0"/빈 = 비활성 블랙리스트 (truthy 매핑) | KIS API 코드값 향후 확장 호환 |
| 의제 2 | 메인 세션 단일 + bypass_limit=True + HIGH/LOW cap 분리 | KIS LMS chain 차단 + 손절 안전 우선 |
| 의제 3 | HIGH bypass / LOW cap=20 / 합 ≤30 | 사이클 66 K-10 패턴 답습 |
| 의제 4 | 부팅 REST 1회 + graceful 폴백 | 안전 마진 + 결함 시 영향 0 |
| 의제 5 | 종목 단위 3 영역 (VI + 거래정지 + 종목상태) — MRKT_TRTM 제외 | 시장 단위 신호 무관 |

## 매매 안전성 평가

- **stale 회피 = stale 판정 *지연*만** (재구독 발화 차단)
- **`check_exit_signal` 영역 무영향** = 손절/익일청산 hot path 항상 작동 (사이클 38 명문화)
- **risk.on_tick / order_engine / auth 변경 0 의무**
- **사이클 29 005935 사고 영역 영속** = 보유 종목 시세 미수신 시 강제 재구독 행위는 VI 해제 후 자연 발화

## 회신 = team-leader 채택

자문 5건 모두 채택. Plan 영역 변경 0 (Plan 의 모든 결정 = 자문 채택 정합).
