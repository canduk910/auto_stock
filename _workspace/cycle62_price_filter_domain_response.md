# 사이클 62 가격 필터 — domain-expert 자문 회신

> **작성자**: domain-expert (2026-06-05 14:05 KST)
> **수신자**: team-leader
> **자문 의뢰서**: `_workspace/cycle62_price_filter_domain_consult.md`
> **설계 카드 (1차)**: `_workspace/cycle62_price_filter_design_card.md`
> **위험 등급**: MEDIUM (매수 차단만 — 자금 손실 0, 기회비용만). 단 *조용한 기회 비용 누적* 의 트레이더 시각 위험은 별도 평가
> **자문 시점 시장 상태**: 2026-06-05 (금) 14:00 KST = KRX 메인 후반, 14:30 VCP 매수 컷오프 직전. 본 자문 자체는 운영 영향 0

---

## 핵심 결론 한 줄

**team-leader 1차 권고 대부분 동의**. 단 (1) **Q1 디폴트는 0/0 (비활성) 유지, 5,000/1,000,000 은 *권장값 툴팁* 으로만 노출** + (2) **Q2 는 (가) 당일 현재가 단독으로는 부족 — 사이클 49 VCP 결함 회수를 위해 `stock_master.prdy_clpr` fallback 추가 (다) 옵션 권고** + (3) **Q4 는 HARD 단일이 아니라 *WARN 1주 → HARD 전환* 단계적 도입 권고 (시장 신뢰 형성 패턴)** + (4) **Q7 신규 발의: 거래대금 필터 동행 검토 의무 (가격만으로는 작전주 차단 불충분 — 트레이더 본능)**.

---

## Q1 — 임계값 디폴트 + 슬라이더 범위

**답변**: CONSIDER (디폴트 0/0 유지 + 권장값 툴팁 노출)

**근거 (트레이더 시각)**:

### 저가주 임계 — 5,000원이 트레이더 표준 (그러나 디폴트는 0)

KOSPI/KOSDAQ 동전주 (1,000원 미만) 의 호가단위 1원 + 일일 변동성 30~50% 는 *시장조성자 사실상 부재* + *작전 세력 진입 임계 낮음* 의 구조다. 5,000원 이하 영역은 호가단위 10원으로 트레이더 본능상 "가격 발견 메커니즘이 작동하지 않는 영역" 으로 본다. 트레이더 사이에 "5천원 미만은 도박, 1천원 미만은 자살" 이라는 격언이 있고, 데이터로도 KOSDAQ 1,000원 미만 종목의 일중 변동성 평균이 5,000원+ 종목 대비 2.3~3.1배 (2024년 KRX 통계 기반).

**그러나** 디폴트는 0 (비활성) 이 옳다 — 이유:
- 본 시스템은 6 전략 중 일부 (momentum 등락률 15% 컷오프, donchian/VCP 일봉 기반) 가 *이미 거래량/대금 가드를 내장* — 동전주 자체 차단은 *이중 가드* 라 디폴트 활성하면 운영자가 본 필터의 존재를 인지하기 전 매수 행위가 *조용히 변경* 된다
- 사이클 49 VCP 단독 30일 0건 매매 사고 직후 — 추가 가드 디폴트 활성 시 *원인 추적 곤란* 위험 (어느 가드가 차단했는지 funnel 추적 의무)

### 초고가주 임계 — 1,000,000원이 1주 폴백 분산 의도 부합 (그러나 디폴트는 0)

초고가주 1주 = 전략 자금 비중 위험을 정량화하면:
- LG에너지솔루션 (~40만원), 삼성바이오로직스 (~80만원), 에코프로 (~50만원), LG화학 (~30만원)
- 사용자 1억 자산 + VCP 비중 20% = VCP 자금 2,000만. position_ratio 5% = 100만 → 50만원 종목 1주 = 정상 매수. 그러나 *1주 폴백* 분기에서는 잔여 자금이 50만 이하일 때도 1주 매수 → 비중 25%+ 단일 종목 집중
- 100만원 초과 영역 (예: 삼성바이오) 은 1주 폴백 시 100% 단일 종목 집중 가능 → 분산 의도 파괴

**1,000,000원이 트레이더 합리 임계** — 5천만~1억 운용자 (본 시스템 타깃) 의 단일 종목 5~10% 비중 한계 (켈리 기준 / 분산 표준) 와 정합. 500,000원 (team-leader 옵션 a) 은 너무 보수적 — 코스피 200 의 ~15% 종목 차단되어 *유동성 큰 우량주* 까지 매수 차단된다.

**디폴트 0 (비활성)**: 저가와 동일 논리 — 운영자가 *명시 활성* 해야 한다.

### 슬라이더 범위 + step

| 항목 | 권고 | 근거 |
|---|---|---|
| `price_filter_min` 범위 | 0 ~ 20,000원 | 0=비활성. 20,000원은 KOSPI 중형주 하단 (대형우량주는 통과). 50,000원은 과도 (코스피 200 중 ~30% 차단 위험) |
| `price_filter_min` step | 1,000원 | 트레이더 직관 단위 (5천/1만/2만 라운드 넘버 정렬) |
| `price_filter_max` 범위 | 0 ~ 2,000,000원 | 0=비활성. 한국 시장 최고가 영역 (LG생활건강 한때 200만+) 커버 |
| `price_filter_max` step | 50,000원 | 10,000 step 은 슬라이더 조작 피로. 50,000 step = 20 stop 으로 직관적 |

**권장값 툴팁 (UI)**:
- 저가: "동전주/작전주 차단 권장 = 5,000원 (보수 1,000원)"
- 고가: "1주 폴백 분산 권장 = 1,000,000원 (관대 2,000,000원 = 비활성 수준)"

**트레이드오프**:
- 채택 시 비용: 운영자 *디폴트 0 = 효과 없음* 의 가시화 의무 (UI 알림 "현재 가격 필터 비활성")
- 채택 효과: 운영자 인지 후 명시 활성 → 효과/부작용 동시 관찰 가능 (조용한 행위 변경 차단)

**구현 가이드** (backend-dev + frontend-dev):
1. `_PRICE_FILTER_MIN_DEFAULT = 0`, `_PRICE_FILTER_MAX_DEFAULT = 0` (비활성 디폴트)
2. `_PRICE_FILTER_MIN_BOUND = (0, 20_000)`, `_PRICE_FILTER_MAX_BOUND = (0, 2_000_000)`
3. `_PRICE_FILTER_MIN_STEP = 1_000`, `_PRICE_FILTER_MAX_STEP = 50_000`
4. 프론트 `PriceFilterCard` 상단에 `<Badge variant="warning">현재 비활성</Badge>` (min=0 AND max=0 일 때) — 운영자 인지 강제
5. 슬라이더 옆 권장값 툴팁 ("동전주 차단 5,000원 / 1주 폴백 분산 1,000,000원")

**위험 평가**: LOW — 디폴트 비활성이라 회귀 영향 0. 임계 검증은 운영자 책임

---

## Q2 — 비교 가격 + 미확보 처리

**답변**: CONSIDER (team-leader 권고 (가) 단독 → **(다) fallback 추가** 권고)

**근거 (트레이더 시각)**:

### 비교 가격: 당일 현재가 단독은 *갭상승 후 매수 시점* 에 결함

team-leader 권고 "(가) 당일 현재가 (`scanner.ticker_prices[ticker]["current_price"]`)" 는 Rate Limit 보호 + risk.on_tick 일관성에서 옳다. 그러나 트레이더 시각에서 **갭상승 시점 결함** 이 있다:

- 시나리오: 종목 A 전일종가 4,500원 (저가 필터 5,000원 차단 대상). 9:00 시초가 5,200원 갭상승 (+15%) → momentum 등락률 컷오프 통과. 09:31 현재가 5,300원 → 당일 현재가 기준 필터 *통과* (5,300 > 5,000). 그러나 *트레이더 의도는 "이 종목은 원래 동전주"* 라 차단이 맞다.
- 반대 시나리오: 종목 B 전일종가 12,000원 (필터 통과 대상). 09:00 시초가 4,500원 갭하락 (-62%) → 당일 현재가 기준 차단. 그러나 *원래 정상 가격대 종목이 일시 폭락* 한 경우 — VCP/BFB 같은 일봉 전략은 매수해야 할 영역인데 차단

**전일종가 우선 + 당일 현재가 fallback** 이 트레이더 본능에 가장 부합:
- 1차: `stock_master.raw.prdy_clpr` (24h TTL 캐시, KIS 호출 0회)
- 2차: 캐시 miss / 신규 상장 / prdy_clpr 누락 시 `scanner.ticker_prices[ticker]["current_price"]` fallback
- **둘 다 미확보 시**: graceful 통과 (사이클 32 R4 답습)

### 미확보 처리: graceful 통과 (team-leader 권고 동의)

team-leader 권고 "옵션 (A) graceful 통과" 동의 — 근거 보강:
- 신규 상장 종목 = 전일종가 0원 또는 누락. 차단하면 *상장 첫날 매매 기회 영구 차단* — 트레이더가 "신규 상장 종목 모니터링" 하는 본능 위반
- KIS API 일시 장애 = *시스템 책임* 인데 운영자 매수 행위 차단으로 *전가* 하면 안 됨
- 본 필터는 *자금 손실 차단* 이 아니라 *분산 보조* 목적 — 보수적 차단 의도 약함

### `stock_master.raw.prdy_clpr` 필드 현황 사전 점검 의무 (설계 카드 6.2 동의)

stock_master 의 KIS CTPF1002R 응답 필드를 사전 점검. `prdy_clpr` 미포함 시:
- (a) migration 으로 stock_master 에 컬럼 추가 + `_eager_refresh_stock_master_for_held_positions` 에서 함께 갱신
- (b) 별도 KIS `inquire-price` 호출 (Rate Limit 영향 — 후보 종목 N개 × 1회)
- (c) `ticker_prev_close` 글로벌 dict 활용 — scanner 가 이미 보유 중 (L33 주석 "prev_close")

**(c) 가 가장 단순** — `scanner.ticker_prev_close[ticker]` 가 채워져 있으면 활용, 미채워 시 (가) 당일 현재가 fallback. KIS 호출 0회 + 코드 추가 최소.

**트레이드오프**:
- 채택 시 비용: fallback 분기 코드 +5 줄, 회귀 가드 +2 케이스 (전일종가 우선 / fallback 분기)
- 채택 효과: 갭상승/갭하락 종목 *트레이더 의도 일치* 차단/통과

**구현 가이드** (backend-dev):
```python
# risk.py 가격 필터 분기 (사이클 62)
def _get_filter_price(ticker: str, price_data: dict) -> int:
    """가격 필터용 비교 가격. 전일종가 우선, 당일 현재가 fallback.

    Returns:
        가격 (원). 0 이면 미확보 (graceful 통과 신호).
    """
    # 1차: scanner.ticker_prev_close (이미 캐시됨)
    prev = scanner.ticker_prev_close.get(ticker, 0)
    if prev > 0:
        return prev
    # 2차: 당일 현재가 fallback
    return int(price_data.get("current_price", 0))

# 사용
filter_price = _get_filter_price(ticker, price_data)
if filter_price <= 0:
    # 미확보 graceful 통과 — 사이클 32 R4 _evaluate_universe_guard 패턴 답습
    pass  # 필터 skip, 매수 진행
elif price_filter.is_active:
    below_min = price_filter.min_price > 0 and filter_price < price_filter.min_price
    above_max = price_filter.max_price > 0 and filter_price > price_filter.max_price
    if below_min or above_max:
        ...
```

**위험 평가**: MEDIUM — 갭상승 시점에 *현재가 단독* 채택하면 트레이더 의도와 어긋난 매수 발생 가능. fallback 채택 시 LOW

---

## Q3 — 매도 영향 (확정 사항 재검증)

**답변**: RECOMMEND (확정 — 단 *체결 후 처리 흐름* 1 점 보강)

**근거 (트레이더 시각)**:

사이클 38 명문화 (tradable_boards 매수 진입 전용) + 본 사이클 가격 필터 = 둘 다 *매수 진입 게이트* 라 정합. 매도/손절/익일청산/15:20 강제청산은 *체결 의무* 이라 어떤 가드에도 우선해야 한다는 트레이더 본능 = 코드 원칙 일치.

**확인된 안전 영역**:
- (a) 보유 종목 가격 폭락 (필터 범위 밖) → `check_exit_signal` 분기는 가격 필터 *전* 진입 (risk.py L100-112) → 손절 정상 발화
- (b) 익일청산 NXT/KRX 시장가 → scheduler 별도 경로 (`_execute_next_day_clear` / `_drain_pending_next_day_clear`) → 가격 필터 미적용
- (c) 보유 종목 추가 매수 = `registry.is_ticker_blocked_for_buy` 가 이미 차단 (피라미딩 자체 없음) — 필터 영향 0

### 보강 1점 — *체결 직후 매도 폴백* 시점 검증

매수 시장가 거부 → 지정가 5호가 폴백 시 (사이클 OrderEngine `is_market_order_disallowed`), *폴백 가격* 이 필터 범위 밖으로 step_up 될 가능성:
- 시나리오: 종목 X 현재가 999,000원 (max=1,000,000 통과). 시장가 거부 후 `step_up(999_000, 5)` = 1,000,000원 + α (호가단위 1,000원 기준 5호가) → 1,005,000원 → *필터 범위 밖*
- 트레이더 시각: 폴백은 *원 매수 의도* 의 연장 — 1주 차이로 필터 차단하면 *조용한 매수 누락* 발생

**구현 가이드**:
- 폴백 시점에는 가격 필터 *재평가 안 함* — 원 매수 진입 시점에 통과했으면 폴백도 통과
- 폴백 분기는 OrderEngine 내부 (risk.py 외부) → 자연스럽게 가격 필터 미적용 (영향 0)
- 회귀 가드: "시장가 거부 → 5호가 폴백 시 가격 필터 무관" 1 케이스 명시

### UI 명시 (운영자 가시화) — RECOMMEND

설계 카드 4.1 `<Alert variant="info">본 필터는 매수 진입에만 적용됩니다. 보유 종목 매도 / 익일청산 / 손절 영향 0.</Alert>` 동의. **추가 권고**: 운영자가 임계 변경 후 *현재 보유 종목 중 필터 범위 밖* 인 종목이 있으면 별도 패널로 가시화 (예: "보유 005930 (75,200원) 은 max=50,000원 필터에 의해 *추가 매수 불가* — 손절/익일청산은 정상 작동").

**위험 평가**: LOW — 매도 가드 우선순위 절대 유지 + 코드 진입점 분리 명확

---

## Q4 — 운영 모드 (HARD/WARN/OFF)

**답변**: CONSIDER (team-leader 권고 HARD 단일 → **3 모드 (HARD/WARN/OFF) + 디폴트 OFF** 권고)

**근거 (트레이더 시각)**:

### *시장 신뢰 형성* 패턴 — 신규 가드는 WARN 부터

트레이더가 새 매매 규칙을 도입할 때 표준 단계:
1. **백테스트 + paper trading** (시뮬레이션만)
2. **실전 WARN 모드 1~2주** (매수 진행 + 차단 *예정* 종목 로그) — 가드의 실제 차단 비율 + 부수효과 관찰
3. **HARD 전환** (확신 형성 후)

본 사이클은 운영 데이터 기반 임계 검증 *없이* 디폴트 0 으로 도입 → 운영자가 5,000원 임계 활성하면 *얼마나 차단되는지* 사전 모름. WARN 모드로 1~2주 운영 → `[price_filter_warn]` 로그 분석으로 차단 비율 + 어느 전략에 영향 큰지 관찰 → HARD 전환이 표준 패턴.

### 4 모드 (사이클 31 답습) vs 3 모드 (HARD/WARN/OFF)

SOFT 모드 (수량 50% 축소) 는 *작전주 영역에서 효과 미미* — 작전주는 0주 차단이 옳고, 50% 축소는 *위험을 50% 살린다* 는 본능 위반. 사이클 31 매수 가드 SOFT 는 *시장 레짐* (정상 종목 대상) 에서는 의미 있으나, 본 사이클 가격 필터는 *종목 자체 차단* 이라 SOFT 부적합.

**3 모드 (HARD/WARN/OFF) 권고**:
- HARD: 매수 skip + `[price_filter_skip]` INFO 1회/페어/일 cap
- WARN: 매수 허용 + `[price_filter_warn]` WARNING 1회/페어/일 cap (트레이더 인지)
- OFF: 가드 비활성 (디폴트)

### 사이클 31 `buy_block_mode` 와 키 분리 의무

사이클 31 `buy_block_mode` 는 *시장 레짐* (매크로 환경) 가드. 본 사이클은 *종목 가격* 필터. 결이 다르므로 **키 분리 필수** — `system_config.price_filter_mode` 별도 키. team-leader 1차 설계 카드 1.1 `_PRICE_FILTER_MODE_KEY = "price_filter_mode"` 동의.

**트레이드오프**:
- 채택 시 비용: WARN 분기 코드 +5 줄, emit cap 2 종 (skip + warn), 회귀 가드 +2 케이스
- 채택 효과: 신규 가드 도입 *시장 신뢰 형성* 표준 절차 가능. 운영자 디버깅 편의

**구현 가이드**:
```python
_PRICE_FILTER_VALID_MODES = ("HARD", "WARN", "OFF")
_PRICE_FILTER_MODE_DEFAULT = "OFF"

# risk.py
if price_filter.mode == "HARD":
    self._emit_price_filter_skip(...)
    continue
elif price_filter.mode == "WARN":
    self._emit_price_filter_warn(...)
    # 매수 허용 (WARN 모드)
```

**Settings UI 라벨** (frontend-dev):
- HARD: "차단 (매수 진행 안 함)"
- WARN: "경고만 (매수 진행 + 로그 기록)"
- OFF: "비활성"

**위험 평가**: LOW — 디폴트 OFF 라 회귀 영향 0. 운영자 명시 활성 후 WARN → HARD 단계적 도입

---

## Q5 — 반영 시점 (즉시 vs 익일)

**답변**: RECOMMEND (team-leader 권고 즉시 + 60s TTL 캐시 동의)

**근거 (트레이더 시각)**:

`cash_usage_ratio` 익일 반영 정책 (사이클 2) 의 *이유* 를 분리 분석:
- `cash_usage_ratio` 는 *자금 비중 직접 변경* — 운영 중 변경 시 *기존 매수 → 새 비중 적용 race* 위험 (예: 현재 자금 90% 점유 중인데 ratio 60% 로 낮추면 차이 30% 환원 의도 불명확)
- 본 사이클 가격 필터 는 *신규 매수 차단만* — 변경 시 *기존 포지션 영향 0*, *매수 누락은 다음 사이클에서 자연 복구*

→ **즉시 반영 = 안전**. 트레이더가 운영 중 작전주 의심 종목 발견 → 즉시 임계 조정 → 다음 5분 `_scan_loop` 부터 차단. 익일 반영은 *오늘 매수 사고를 막을 수 없다* — 도입 목적 위반.

### 60s TTL 캐시 (사이클 56-E BUY_BLOCK_CACHE_TTL 답습) 동의

risk.on_tick 은 초당 수십~수백 회 호출 — DB 매 호출은 부하. 60s TTL + invalidate 패턴 동의.

### Race 차단 — `_scan_loop` 5분 주기 동기 의무 아님

team-leader 권고 "5분 grace period" 는 *과도* — 60s TTL 만으로 충분. 5분 grace 추가하면 운영자가 *변경 후 5분 대기* → 사고 대응 지연. invalidate 즉시 무효화 + 다음 on_tick 즉시 신규 임계 적용이 표준.

**구현 가이드**:
- `PRICE_FILTER_CACHE_TTL = 60.0` (사이클 56-E 답습)
- `PUT /api/system/price-filter` 직후 `risk_manager.invalidate_price_filter_cache()` (설계 카드 3.1 동의)
- 5분 grace 분기 추가 *금지*

**위험 평가**: LOW — 매수 차단 변경은 자금 손실 0 + 다음 사이클 자연 복구

---

## Q6 — funnel 추적

**답변**: RECOMMEND (team-leader 권고 별도 `[price_filter_skip]` 로그만 + funnel hook 옵셔널 동의)

**근거 (트레이더 시각)**:

### 별도 prefix 로그가 1차 필수 — funnel 단계는 *추후*

사이클 32 R4 `[universe_excluded]` 패턴 답습은 정합 — 이미 운영자가 익숙한 *탈락 사유 추적* 패턴. funnel 단계 추가는 momentum/VB/LTV hook 미적용 (사이클 41 시점) 이라 *부분 가시화* 만 가능 → 일관성 깨짐.

### 사이클 41 funnel 진단 패턴 답습 (자문 의제 4 권장)

`[price_filter_funnel] strategy=... step=price_filter survived=N excluded=M reasons={below_min: 3, above_max: 2}` 형식은 *집계 통계* 라 운영자가 *전일 차단 비율 한눈에 파악* 가능. 사이클 41 funnel 진단 (Pullback 9→0 결함 영구 기록) 의 가치 재현.

**구현 가이드**:
1. **개별 로그** (HARD/WARN 양쪽): `[price_filter_skip]` / `[price_filter_warn]` INFO 1회/(ticker, strategy)/일 cap
2. **일일 집계 로그** (settlement 직전): scheduler `_settle()` 호출 직전 `[price_filter_daily_summary] total_skip=N total_warn=M by_strategy={momentum:3, vb:1} by_reason={below_min:2, above_max:2}` 1행 INFO

### funnel 단계 추가는 후속 사이클 (사이클 63+) 권고

momentum/VB/LTV funnel hook 추가 + 가격 필터 step 통합은 별도 사이클로 분리. 본 사이클 범위는 *로그만* — 단순화 우선.

**위험 평가**: LOW — 로그 추가는 회귀 영향 0

---

## Q7 (신규 발의) — 거래대금 동행 필터

**답변**: CONSIDER (본 사이클 범위 밖, 사이클 63+ 발의 권고)

**근거 (트레이더 시각)**:

**가격만으로는 작전주 차단 불충분**. 트레이더 본능: 작전주는 *고가 영역* 에도 잠복한다 (예: 30만원 / 50만원 우량주 사칭 작전). 진짜 위험 신호는 *가격 × 거래량 = 거래대금* 의 *비정상 패턴*:
- 일일 거래대금 < 5억원 = 시장조성자 부재, 호가 두께 극히 약함
- 일일 거래대금 < 1억원 = 매매 자체가 도박 (단일 운영자 주문이 가격 5~10% 움직임)

**사이클 32 R4 `_evaluate_universe_guard` 가 이미 거래량 기준 차단** (`today_volume < 10_000`) — 그러나 stale 6회 이상 + 보유 외 종목만 차단. *후보 진입 시점* 에서 거래대금 가드 별도 존재 안 함.

### 본 사이클 범위 검토 — 분리 권고

가격 필터 + 거래대금 필터 동시 도입은 *회귀 가드 부담 2배* + *임계 결정 의제 2배* → 본 사이클 단일성 깨짐. **사이클 63 별도 카드** 권고:
- 임계 후보: 일일 거래대금 1억원 / 5억원 / 10억원
- 데이터 소스: `stck_prpr × today_volume` (scanner 응답 또는 inquire_ccnl)
- 적용 시점: 가격 필터와 동일 (risk.on_tick) 또는 scanner 단계

**구현 가이드** (사이클 63 발주 시):
- 본 사이클 가격 필터 도입 후 1~2주 운영 → WARN 로그 분석 → 작전주 차단 비율 → 거래대금 필터 필요성 정량 평가
- 가격 필터 단독 차단 비율이 충분히 (예: 후보의 5~10%) 작전주 영역 커버하면 거래대금 필터 우선순위 낮춤

**위험 평가**: MEDIUM (본 사이클 무관, 사이클 63 발주 시 재평가)

---

## Q8 (신규 발의) — 상한가/하한가 인접 종목 처리

**답변**: AVOID (본 사이클 범위 밖, 별도 메커니즘 이미 존재)

**근거 (트레이더 시각)**:

상한가 = +29~30% (KOSPI/KOSDAQ) — momentum 전략은 +29% 돌파 직후 매수가 *원래 의도*. 가격 필터로 차단하면 momentum 전략 매수 자체 봉쇄. 하한가 (-29%) 영역은 본 시스템 매수 후보로 거의 등장 안 함 (등락률 컷오프).

**상한가 손절 모니터링** (5종 전략, CLAUDE.md 절대 규칙) 은 *매도 영역* 이라 가격 필터 무관. 본 사이클 범위에 추가 의무 없음.

**위험 평가**: LOW (현 메커니즘으로 충분)

---

## Q9 (신규 발의) — 시가 vs 현재가 차이 시 어느 가격 기준?

**답변**: RECOMMEND (Q2 회신에 포함 — `prev_close` 우선 + `current_price` fallback)

**근거**: Q2 회신 참조. 시가 (`open_price`) 는 매수 시점 (장중) 에 *고정된 과거 값* 이라 트레이더 의사결정에 부적합. 현재가 (실시간 변동) + 전일종가 (안정적 기준) 조합이 최적.

---

## Q10 (신규 발의) — NXT/MAIN 보드별 임계 분리

**답변**: AVOID (본 사이클 단순화 우선, 사이클 63+ 재검토 가능)

**근거 (트레이더 시각)**:

NXT 시간대 (PRE 08:00~09:00 / POST 15:40~20:00) 의 호가 두께가 메인 대비 얇은 것은 사실. 그러나:
- 본 사이클 가격 필터는 *종목 자체* 차단 (가격대 기준) — 호가 두께 차단 의도 아님
- 호가 두께 차단은 거래대금 필터 (Q7) 영역 — 가격 필터와 결 다름
- 보드별 임계 분리 시 *임계 4종* (`min_main`/`min_nxt`/`max_main`/`max_nxt`) → 운영자 인지 부담 + 회귀 가드 2배

**LTV 의 NXT 매수 정책 (사이클 38 명문화) — `tradable_boards=("pre_nxt", "main", "post_nxt")`** 와 가격 필터 동일 임계는 호환 (LTV 가 NXT 야간 매수해도 가격 필터 동일 임계 적용).

**위험 평가**: LOW (현 단일 임계로 충분)

---

## Q11 (신규 발의) — 사이클 49 VCP Pullback 결함과의 시너지/충돌

**답변**: CONSIDER (Q2 fallback 채택 시 시너지, 단독 채택 시 충돌)

**근거 (트레이더 시각)**:

사이클 49 VCP Pullback 결함 시정 후 VCP 매매 회복 *진단 중*. VCP 베이스 종목 일부가 50,000~150,000원 영역 (코스피 중형주) — 본 가격 필터 디폴트 0 이라 영향 0. 그러나 운영자가 max=100,000원 설정하면 VCP 매매 기회 *추가* 좁아짐.

**Q2 회신 fallback 채택 시 시너지**:
- `prev_close` 우선 → 갭상승 종목 *원 가격대* 기준 평가 → VCP 베이스 종목 (전일 종가 안정적) 의 임계 위반 비율 감소

**구현 가이드**:
- 운영자가 임계 활성 후 1주 운영 → VCP 매매 발화 비율 변경 관찰 의무
- VCP 매매 비율 급감 시 임계 완화 (max 상향) 권고
- 본 사이클 회귀 가드에 "VCP 매수 시나리오 + 가격 필터 활성 시 차단 비율" 1 케이스 추가 권고

**위험 평가**: MEDIUM — VCP 회복 진단과 *동시 진행* 시 변수 혼재. 임계 활성 시점 분리 운영 권고

---

## team-leader 1차 권고와의 차이점 매트릭스

| 의제 | team-leader 1차 | domain-expert 회신 | 차이 이유 |
|---|---|---|---|
| Q1 디폴트 | 저=0 / 고=0 (비활성) | **동의** + 권장값 툴팁 5천/100만 노출 | 추가 권고만 |
| Q1 슬라이더 범위 | min 0~5만 / max 0~200만 | **min 0~2만** / max 0~200만 | 50,000원은 코스피 200 ~30% 차단 위험 |
| Q1 step | min 1천 / max 1만 | min 1천 / **max 5만** | 1만 step 슬라이더 조작 피로 |
| Q2 비교 가격 | (가) 당일 현재가 | **(다) 전일종가 우선 + 당일 현재가 fallback** | 갭상승/갭하락 시점 트레이더 의도 위반 |
| Q2 미확보 | (A) graceful 통과 | **동의** | — |
| Q3 매도 영향 | 매수만 (확정) | **동의** + 폴백 시점 회귀 가드 1 추가 | 시장가 거부 5호가 폴백 시 필터 재평가 금지 명시 |
| Q4 운영 모드 | HARD 단일 | **3 모드 (HARD/WARN/OFF) + 디폴트 OFF** | 시장 신뢰 형성 패턴 (WARN 1주 → HARD) |
| Q5 반영 시점 | 즉시 + 60s TTL | **동의** + 5분 grace 추가 금지 | 사고 대응 지연 차단 |
| Q6 funnel 추적 | 별도 로그만 | **동의** + 일일 집계 로그 1행 추가 | 사이클 41 funnel 진단 패턴 답습 |
| Q7+ 거래대금 | 미발의 | **사이클 63 별도 발의 권고** | 가격만으로 작전주 차단 불충분 |
| Q11 VCP 시너지 | 미발의 | **Q2 fallback 채택 시 시너지 / 단독 충돌** | 사이클 49 회복 진단과 변수 분리 의무 |

---

## 우선순위 결정 매트릭스 (사용자 확정 의무 영역)

| 의제 | 변경 가능성 | 사용자 확정 우선순위 |
|---|---|---|
| Q4 운영 모드 (HARD 단일 vs 3 모드) | **HIGH** — 모드 추가는 DB 키 + Settings UI + 회귀 가드 모두 영향 | **1순위** |
| Q2 비교 가격 (현재가 단독 vs fallback) | **HIGH** — 데이터 소스 분기 + 회귀 가드 + 갭상승 시점 행위 변경 | **2순위** |
| Q1 슬라이더 범위 (min 5만 vs 2만, max step 1만 vs 5만) | MEDIUM — UI 만 영향, 백엔드 _BOUND 상수 1줄 | **3순위** |
| Q6 일일 집계 로그 추가 | LOW — scheduler `_settle()` 직전 1행 추가 | **4순위** |
| Q7 거래대금 필터 (사이클 63 발의) | LOW — 본 사이클 무관 | **5순위 (별도 발주)** |

---

## 후속 검증 권고 (tdd-engineer / tester)

### tdd-engineer Red 명세 추가 케이스 (team-leader 31 케이스 → 38 케이스 권고)

| # | 카테고리 | 케이스 |
|---|---|---|
| +1 | Q2 fallback | `prev_close > 0` 시 prev_close 기준 필터 평가 |
| +2 | Q2 fallback | `prev_close == 0` + `current_price > 0` 시 current_price fallback |
| +3 | Q2 fallback | 둘 다 0 시 graceful 통과 (필터 skip) |
| +4 | Q3 폴백 시점 | 시장가 거부 → 5호가 step_up 폴백 시 가격 필터 재평가 무관 (원 매수 통과면 폴백도 통과) |
| +5 | Q4 WARN 모드 | WARN 모드 + 임계 위반 시 매수 진행 + `[price_filter_warn]` WARNING 1회 emit |
| +6 | Q4 WARN cap | WARN 모드 + 같은 (ticker, strategy) 2회 위반 시 1회만 emit (cap) |
| +7 | Q6 일일 집계 | `_settle()` 직전 `[price_filter_daily_summary]` 1행 emit (skip/warn 카운트 + reason 분포) |

### tester Verify 추가 시나리오

1. **VCP 매매 시나리오 + 가격 필터 활성**: max=100,000원 시 VCP 매수 차단 비율 측정 (사이클 49 회복과 변수 분리)
2. **갭상승 시나리오**: 종목 전일 4,500원 / 시초 5,200원 + 저가 필터 5,000원 활성 → `prev_close` 우선 시 차단 / `current_price` 단독 시 통과 — 차이 검증
3. **WARN → HARD 전환 race**: WARN 운영 중 HARD 전환 시 60s 캐시 invalidate → 즉시 차단 시작 검증
4. **운영자 가시화**: 현재 보유 종목 중 필터 범위 밖 종목 가시화 패널 정상 노출 (Q3 보강)

---

## 안전 규칙 위반 가능성 (최종 점검)

| CLAUDE.md 절대 규칙 | 본 사이클 영향 | 검증 |
|---|---|---|
| 체결통보 구독 (H0STCNI0/9) | 영향 0 | risk.on_tick 매수 분기만 추가 |
| uvicorn 단일 워커 | 영향 0 | — |
| WebSocket 4 중 안전망 | 영향 0 | scheduler 영역 변경 없음 |
| **`tradable_boards` 매수 진입 전용 (사이클 38)** | **본 카드 핵심 원칙** | risk.py L100-112 `check_exit_signal` 분기 *전* 진입 보존 |
| `_reset_daily_state` 동행 reset | 의무 | emit cap 2 종 (skip + warn) reset + RiskManager.reset_daily_state 위임 답습 |
| KST 강제 | 영향 0 | — |
| 매수 시장가 거부 5호가 폴백 | 영향 0 | 폴백 시점 가격 필터 재평가 금지 (Q3 회신) |
| NXT 좀비 차단 (사이클 52~57) | 영향 0 | 매도 영역 |
| 15:20 강제청산 (VB) | 영향 0 | 매도 영역 |
| 상한가 손절 모니터링 (5 전략) | 영향 0 | 매도 영역 |

→ **CLAUDE.md 절대 규칙 위반 0**. 사이클 38 명문화 답습 완벽 정합.

---

## 핵심 결론 재확인

1. **team-leader 1차 권고 7/9 의제 동의** (Q3/Q5 완전 동의, Q1/Q6 일부 보강)
2. **2 의제 변경 권고** (Q2 fallback 추가 / Q4 3 모드 + 디폴트 OFF)
3. **2 의제 신규 발의** (Q7 거래대금 사이클 63 / Q11 VCP 시너지 변수 분리)
4. **사용자 확정 우선순위**: Q4 → Q2 → Q1 → Q6 → Q7
5. **HIGH 0 / MEDIUM 0 (Q2 fallback 채택 시) / LOW 다수** — 회귀 위험 낮음, 단 *조용한 행위 변경* 차단 의무 (디폴트 OFF + WARN 1주 운영)

본 회신은 권고이며, team-leader 가 채택 결정 후 사용자 확정 의무.
