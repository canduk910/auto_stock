# 사이클 64 — 가격 필터 위치 변경 (risk → scanner) + 단순화 도메인 자문 회신

> **작성자**: domain-expert (데이/스윙 트레이더 출신 컨설턴트)
> **작성 시각**: 2026-06-06 (토) KST — KRX/NXT 휴장 (운영 영향 0)
> **수신자**: team-leader
> **자문 의뢰서**: `_workspace/cycle64_price_filter_scanner_domain_consult.md`
> **선행 설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` v1
> **선행 사이클 62 회신**: `_workspace/cycle62_price_filter_domain_response.md`
> **위험 등급 종합**: MEDIUM. 사용자 사전 결정 (위치 이전 + 모드 폐기) 의 안전성 검증 + 6 미확정 영역 권고

---

## 핵심 결론 한 줄

**사용자 사전 결정 4건 전부 트레이더 시각에서 RECOMMEND** (위치 이전 + 모드 폐기 + 전일종가 단독 + DailyEmitCap 1회/일). 단 (1) **Q1 보유/익일청산 보호는 옵션 A 단독 부족 — `_apply_price_filter` 최상단 early-return + scanner 함수마다 `protected_tickers` 명시 전달 + AST 정적 가드 (옵션 D 신규)** (2) **Q2 graceful 통과 + KIS `inquire-price` 사전 fetch 비채택 (Rate Limit + scanner 호출 hot path 부담)** (3) **Q4 진입점은 `subscribe_filtered_stocks` *직전 단일 hook* (옵션 A) — 6 전략 prepare 내부 분산 (옵션 B) 절대 금지** (4) **Q7 신규 발의 5건** — scanner 차단이 *기존 구독* 종목 unsubscribe 발화하면 안 됨 / `prdy_clpr` 액면분할 즉시 invalidate / 사이클 62 운영 데이터 1일 손실 인계 / funnel `step_no=98` 별도 단계 분리 권고 / **사이클 62 갭상승 회피 효과 영구 폐기 위험 (HIGH)** — `current_price` fallback 폐기로 갭상승 종목 (전일 동전주 → 시초 5,000원+) 통과 결함 재발. 거래대금 동행 필터 (사이클 67+) 로 *결을 다른 차원에서* 보강 권고

---

## Q1 — 보유/익일청산 보호 안전 가드 (HIGH)

**답변**: **RECOMMEND 옵션 A + 신규 옵션 D 보강 (3 중 안전망)**

**근거 (트레이더 시각)**:

scanner 단계 차단은 *후보 풀 자체 축소* → WS 구독 *발화 안 됨* → 시세 끊김 → on_tick 평가 0 회 → 매도/익일청산/손절 *발화 자체 차단* 위험. risk.on_tick 에서는 *시세 수신 후* 차단이라 매도 분기가 먼저 진입 가능했지만, scanner 차단은 *진입 게이트 자체* 라 보유 종목이 *조용히 시세 끊긴 채 잔류* 하면 손절 발화 0 → 트레이더 입장에서 가장 무서운 결함 시나리오.

사이클 32 R4 universe guard 의 `protected_tickers = positions ∪ _pending_next_day_clear` 패턴은 *행위 검증된 표준* 이라 답습 의무. 다만 **사이클 32 R4 는 stale 6+ 조건 만족 시에만 발화** (희소 사건) 인 반면, **사이클 64 가격 필터는 매 5분 `_scan_loop` 마다 모든 후보 평가** (hot path) — 호출 빈도 100배 이상. 따라서 *코드 한 곳 누락* 이 *영구 시세 끊김* 으로 직결될 위험이 R4 대비 비교 불가.

### 옵션 D (신규 발의) — 3 중 안전망

옵션 A (사이클 32 R4 답습) 기본 + 다음 2 안전망 추가:

1. **`_apply_price_filter` 최상단 early-return 가드** (필수 의무):
   ```python
   async def _apply_price_filter(
       candidates: list[str],
       *,
       protected_tickers: set[str],
   ) -> list[str]:
       pf = await _get_price_filter_for_scanner()
       if not pf.is_active:
           return candidates
       survivors: list[str] = []
       for ticker in candidates:
           # === 최상단 early-return (사이클 32 R4 답습) ===
           if ticker in protected_tickers:
               survivors.append(ticker)
               continue  # 필터 평가 skip — prdy_clpr 조회조차 안 함
           # === 이하 필터 평가 ===
           ...
   ```
   — `protected_tickers` 조회는 가격 평가 *전* 단독 분기. KIS 호출 비용 0 + 불필요 캐시 미스 0.

2. **AST 정적 회귀 가드 (G 카테고리 신규)** — 사이클 60 Q3-G6 / 사이클 61 D-1 / 사이클 63 D-2 패턴 답습:
   ```python
   # tests/unit/engine/test_cycle64_price_filter_scanner_protected_invariant.py
   def test_apply_price_filter_calls_must_pass_protected_tickers_kwarg():
       """`_apply_price_filter` 호출은 `protected_tickers=` keyword-only 인자 필수.

       AST 정적 가드 — 호출자 누락 시 CI 실패. 위치 인자 호출 차단."""
       import ast
       from pathlib import Path
       src = Path("src/engine/scanner.py").read_text()
       src += "\n" + Path("src/engine/scheduler.py").read_text()
       tree = ast.parse(src)
       for node in ast.walk(tree):
           if isinstance(node, ast.Call):
               fn = node.func
               if isinstance(fn, ast.Attribute) and fn.attr == "_apply_price_filter":
                   # keyword 인자에 protected_tickers 명시 의무
                   kw_keys = {kw.arg for kw in node.keywords}
                   assert "protected_tickers" in kw_keys, \
                       f"_apply_price_filter 호출 누락: line {node.lineno}"
               elif isinstance(fn, ast.Name) and fn.id == "_apply_price_filter":
                   kw_keys = {kw.arg for kw in node.keywords}
                   assert "protected_tickers" in kw_keys
   ```
   — 호출자가 *깜빡* `_apply_price_filter(candidates)` 만 호출하면 CI 실패. 함수 시그니처 의무.

3. **헬퍼 함수 단일화** — `_collect_protected_tickers_for_scanner()` scanner 모듈 공개:
   ```python
   def _collect_protected_tickers_for_scanner() -> set[str]:
       """보유 + 익일청산 합집합. 사이클 32 R4 답습."""
       from src.engine.strategy_registry import registry
       protected: set[str] = set()
       for s in registry.all():
           protected |= set(s.state.positions.keys())
       # _pending_next_day_clear 는 scheduler 영역 — lazy import + try/except
       try:
           from src.engine import scheduler as _sched
           if getattr(_sched, "trading_scheduler", None) is not None:
               protected |= {t for (t, _) in _sched.trading_scheduler._pending_next_day_clear}
       except Exception:
           pass  # scheduler 미초기화 (단위 테스트) graceful
       return protected
   ```
   — 모든 호출자 (`scan_stocks`, `_collect_breakout_tickers` 호출 후, donchian prepare 등) 가 *동일 헬퍼* 통과. 한 함수에서 *positions* 만 모으고 *_pending_next_day_clear* 빠뜨리는 결함 차단.

**트레이드오프**:
- 채택 비용: 헬퍼 1개 + AST 가드 1개 + reset_daily 동행 정리. 코드 ~30 줄 추가
- 채택 효과: *조용한 시세 끊김* 결함 *AST 단계에서 영구 차단*. 사이클 32 R4 보다 호출 빈도 100배 이상이라 무인 보호 필수

**구현 가이드** (backend-dev):
1. `scanner._collect_protected_tickers_for_scanner()` 모듈 공개 함수 신규
2. `scanner._apply_price_filter` 최상단 early-return (`if ticker in protected_tickers: survivors.append; continue`)
3. 모든 호출자 `_apply_price_filter(candidates, protected_tickers=_collect_protected_tickers_for_scanner())` 형태로 호출
4. AST 정적 가드 1 케이스 — G 카테고리 추가 (team-leader 1차 G=1 → **G=2**)
5. 회귀 가드 C 카테고리에 **C-4 신규 (HIGH)** — `_collect_protected_tickers_for_scanner` 가 positions + _pending_next_day_clear 합집합 정확성 검증

**위험 평가**: **HIGH** — 시세 끊김 → 손절 발화 0 결함 직접 영역. 3 중 안전망 의무

---

## Q2 — `prdy_clpr` 미확보 처리 (graceful 통과 vs 보수적 제외)

**답변**: **RECOMMEND graceful 통과 (사용자/team-leader 사전 결정 동의) + KIS 사전 fetch 비채택 권고 (현 설계 카드 2.2 2순위 폐기)**

**근거 (트레이더 시각)**:

### graceful 통과 동의 — 다만 *작전주 통과 위험* 의 트레이더 본능

사이클 62 답습 (보수적 = 매수 허용) 동의. 다만 *작전주 신규 상장* 케이스는 우려:
- 사이클 62 답변 인용: "KIS API 일시 장애 = *시스템 책임* 인데 운영자 매수 행위 차단으로 *전가* 하면 안 됨" — 본 사이클도 동일
- 그러나 본 사이클은 scanner 단계 → *전체 매수 후보의 1~5% 신규 상장 비율* 이 *전체 매수 비중* 에 직접 영향 (risk.on_tick 단계는 다른 가드 통과 후 잔존 종목만 영향)
- 트레이더 본능: 신규 상장 = *상장 첫날 변동성 50~100%* + *작전주 비중 5~15%* (코스닥). 시스템적 가드 부재 시 운영자가 *직접 화이트리스트* 관리 의무

→ Q3 (신규 상장 영향) 와 묶어 처리 — *graceful 통과는 유지하되 신규 상장 자체를 모든 전략에서 사전 제외* 안 검토 의무.

### KIS `inquire-price` (FHKST01010100) 사전 fetch 비채택 권고 (현 설계 카드 폐기)

team-leader 설계 카드 §2.2 의 "2순위 KIS pre-fetch + stock_master upsert" 는 *트레이더 본능 반대*:

1. **Rate Limit 영향 과소평가**: 의뢰서 §Q2.2 의 "momentum 30 / VB 40 / BFB+VCP 40+" 합 = 100~150 호출 / 5분 사이클 = **분당 20~30 호출**. KIS Rate Limit 20 req/s = *단일 burst 1초* 만으로 limit 도달. `_scan_loop` 5분 주기 첫 진입에 burst → 다른 KIS 호출 (체결통보 처리 race? 잔고 조회?) 과 충돌
2. **scanner = hot path**: 5분마다 발화. 신규 종목 매번 KIS 호출 시 *cumulative* 호출 누적 → KIS LMS 위험 (사이클 17/29 의 *KIS 공식 답변* 답습 — "재등록 polling 금지")
3. **scanner 캐시 hit 비율 낮음**: `stock_master.get` 의 24h TTL 캐시는 *기존 매수/매도 진입 직전 lazy* 패턴에 최적화. scanner 는 *신규 후보 매번 다름* → 캐시 hit 비율 낮음 → KIS 호출 폭주
4. **사이클 32 R4 universe guard 와 결 다름**: R4 의 `inquire_ccnl` 호출은 stale 종목 *cap=20 + 50ms sleep + 보유 우선 + 5분 TTL* 으로 *극도로 보수적* — 그러나 scanner 가격 필터는 *전체 후보* 평가라 cap 적용 곤란

**대안 (RECOMMEND)**: **stock_master 캐시 단독 + 미확보 시 graceful 통과**
- 1순위: `stock_master.get(ticker).raw.get("prdy_clpr")` — 24h TTL 캐시 hit 시 KIS 호출 0
- 2순위: 미확보 시 **즉시 graceful 통과** (KIS 사전 fetch 폐기)
- 운영 효과: stock_master 캐시 hit 비율은 시간이 지날수록 자연 상승 (보유 종목 + `_eager_refresh_stock_master_for_held_positions` 보강). scanner 첫 사이클 = miss 다수 → graceful 통과 (운영자 자연 인지) → 시간이 지나면 cache hit ↑ → 필터 효과 ↑
- 운영자 가시화: `[price_filter_scanner_miss]` 신규 prefix 1회/(ticker, 사이클)/일 INFO — 통과한 종목 중 미확보 비율 정량화

**구현 가이드 시정 (현 설계 카드 §2.2 부분 폐기)**:

```python
async def _fetch_prdy_clpr_for_filter(ticker: str) -> int:
    """가격 필터용 전일종가. stock_master 단독 (KIS 사전 fetch 금지).

    Returns:
        prdy_clpr (원). 0 이면 미확보 (graceful 통과 신호).
    """
    basics = await stock_master_get(ticker)  # 24h TTL 캐시
    if not basics or not basics.raw:
        return 0
    try:
        return int(basics.raw.get("prdy_clpr", 0) or 0)
    except (TypeError, ValueError):
        return 0
    # 2순위 KIS inquire-price 호출 — 신규 폐기 (Rate Limit 위험)
```

**트레이드오프**:
- 채택 비용: stock_master 캐시 miss 종목 graceful 통과 → 효과 약간 감소
- 채택 효과: KIS Rate Limit 위험 0 + scanner hot path 안정성 + 캐시 hit 자연 상승 곡선

**위험 평가**: **MEDIUM** — graceful 통과는 안전하나 *작전주 통과 위험* 보강 의무 (Q3 + Q7-5)

---

## Q3 — 신규 상장 영향 (`prdy_clpr` 부재 1일차)

**답변**: **CONSIDER 옵션 B (graceful 통과 + 전략별 자연 필터에 위임)** — 옵션 A (사전 제외) 트레이더 본능 일부 반대

**근거 (트레이더 시각)**:

### 신규 상장 1일차의 전략별 자연 차단 비율

| 전략 | 신규 상장 1일차 통과 가능성 | 근거 |
|---|---|---|
| momentum | **HIGH** (15%+ 등락률 빈번) | `prdy_ctrt` = 시초가 대비 등락 (0 vs 시초가) 기준이라 *상장 첫날* 도 +15% 가능. 시총/거래대금 통과 시 후보 진입 |
| VolatilityBreakout | **LOW** (전일 range 미확보) | `prev_high - prev_low` 계산 불가 → `K * range = 0` → target_price = open → 의미 없음 |
| LongTailVolatility | **LOW** (전일 캔들 미확보) | 긴 꼬리 양봉 판정 불가 → 후보 진입 0 |
| BullFlagBreakout | **LOW** (베이스 미형성) | 8일+ 횡보 베이스 필수 → 첫날 후보 0 |
| VCPBreakout | **LOW** (Pullback 시퀀스 미확보) | 베이스 + Pullback 시퀀스 필수 → 후보 0 |
| DonchianSwing | **LOW** (60일 EMA 미확보) | 60일 일봉 필수 → prepare() skip |

→ **신규 상장 1일차 실제 위험은 momentum 단독**. VB/LTV/BFB/VCP/donchian 은 *전략 본질* 이 신규 상장 차단.

### momentum 신규 상장 매수의 트레이더 본능 평가

momentum 전략 = "당일 +15% 이상 상승" 후보. 신규 상장 종목이 이 영역 진입하는 케이스:
- IPO 흥행 첫날 = +30% 상한가 빈번 (LG에너지솔루션 2022.01 / 카카오뱅크 2021.08 등) — 시스템 상한가 차단 (`change_rate >= 30.0`) 으로 자연 차단
- IPO 부진 첫날 = +5~25% 범위 — momentum 후보 진입 가능
- 작전주 신규 상장 = 가격 발견 메커니즘 부재 영역 — *시스템적 차단 가치 있음*

**옵션 평가**:
- 옵션 A (사전 제외) = 신규 상장 IPO 흥행 매수 기회 영구 차단 — 트레이더 본능 *반대* (LG엔솔 첫날 +99% 못 잡으면 손해)
- 옵션 B (graceful 통과 + 자연 차단) = 시스템 단순 + 작전주 차단은 거래대금 필터 (사이클 67+) 에 위임 — 트레이더 본능 *최적*
- 옵션 C (화이트리스트) = 운영자 매일 IPO 확인 부담 — 자동매매 정신 위배

**RECOMMEND 옵션 B 채택**:
1. 본 사이클 가격 필터: `prdy_clpr=0` 신규 상장 → graceful 통과 (사용자/team-leader 결정 동의)
2. 거래대금 동행 필터 (사이클 67+) 도입 시 *그 때* 신규 상장 처리 정밀 평가 (작전주 차단)
3. `_workspace/00_leader_trading_rules.md` 에 신규 상장 처리 규칙 *명시 안 함* (시스템 디폴트 = 통과, 자연 차단 의존)

**트레이드오프**:
- 채택 비용: 작전주 신규 상장 momentum 통과 잔존 (1일차 통과율 추정 1~3%)
- 채택 효과: IPO 흥행 매수 기회 보존 + 시스템 단순 + 차후 거래대금 필터로 정밀 보강

**위험 평가**: **MEDIUM** — momentum 단독 위험. 거래대금 필터 (사이클 67+) 로 보강 의무

---

## Q4 — scanner 진입점 정확성 (HIGH)

**답변**: **RECOMMEND 옵션 A + 옵션 C 조합 (단일 진입점 = `subscribe_filtered_stocks` 직전 단일 hook + 공통 헬퍼)**. 옵션 B (6 전략 분산) **AVOID**

**근거 (트레이더 시각)**:

### 옵션 B (6 전략 분산) 결함 — 트레이더 본능

운영자가 *신규 전략 추가* 할 때마다 가격 필터 hook *깜빡 누락* 위험. 사이클 49 VCP Pullback 결함 (30일 0건 매매) 답습 — *명세는 있는데 코드 누락* 결함이 영업일 30 회 잠복했다. 단일 진입점 = *단일 진실 원천* = 사이클 38 명문화 답습 (`tradable_boards` 매수 진입 전용 = 단일 진실 원천 패턴) 트레이더 본능 일치.

### 옵션 A 구체화 — `subscribe_filtered_stocks` 직전 단일 hook

scanner.py L494 `subscribe_filtered_stocks(tickers, extra_tickers, ...)` 는 모든 전략의 *WS 구독 진입점*. 이 함수 *직전* 에 가격 필터 적용:

```python
# src/engine/scanner.py 신규 (subscribe_filtered_stocks 시그니처 수정 아님)

async def subscribe_filtered_stocks(
    tickers: list[str],
    extra_tickers: list[str] | None = None,
    source_counts: dict | None = None,
    *,
    priority_groups: dict | None = None,
) -> None:
    """기존 시그니처 보존. 함수 *내부 첫 줄* 에서 가격 필터 적용."""
    # === 사이클 64 신규 — 가격 필터 (단일 hook) ===
    protected = _collect_protected_tickers_for_scanner()
    tickers = await _apply_price_filter(tickers, protected_tickers=protected)
    if extra_tickers:
        extra_tickers = await _apply_price_filter(extra_tickers, protected_tickers=protected)
    if priority_groups:
        for key in priority_groups:
            priority_groups[key] = await _apply_price_filter(
                priority_groups[key], protected_tickers=protected,
            )
    # === 기존 로직 ===
    ...
```

— 호출자 시그니처 변경 0. 모든 호출자 자동 통과. *전 전략 공통 의무 자동 충족*. Q4-3 AST 정적 가드는 *시그니처 변경 0* 이라 사이클 60 Q3-G6 패턴 답습 — 6 전략 어떤 호출자도 누락 불가.

### donchian_swing KOSPI200/KOSDAQ150 고정 유니버스도 필터 적용 의무

의뢰서 §Q4.2 질문 = "우량주는 사실상 필터 무영향이지만 일관성 vs 예외 처리". **일관성 우선** 권고:
- 운영자가 max=50,000원 (보수적) 설정 시 → KOSPI200 일부 (삼성전자 75,000원 등) 차단 *의도* 가능. donchian 만 예외 처리하면 운영자 인지 부담
- 단일 진입점 옵션 A 가 자동으로 donchian 도 필터 적용 (subscribe_filtered_stocks 통과 시점). 별도 분기 0 → 일관성 자연 확보
- 보유 KOSPI200 종목은 옵션 D `protected_tickers` 가 자동 보호 → 매도/익일청산 영향 0

### 옵션 C (공통 헬퍼) 분리 의무

`_apply_price_filter` 함수는 scanner.py 모듈 함수 (RiskManager 멤버 아님). 사이클 60 logger 명시 binding 패턴:
```python
logger = logging.getLogger("src.engine.scanner")  # 사이클 60 명시 binding
```

`_collect_protected_tickers_for_scanner` 도 scanner 모듈 함수 — scheduler lazy import + `getattr(_sched, "trading_scheduler", None)` 가드 (단위 테스트 graceful).

### AST 정적 가드 (Q4-3 + 옵션 D 통합)

- G-1 (사이클 62 답습) — `src/engine/risk.py` 에 `price_filter` 참조 0건 (사이클 62 코드 완전 제거 확인)
- G-2 (Q1 옵션 D 신규) — `_apply_price_filter` 호출 시 `protected_tickers=` keyword-only 필수

**트레이드오프**:
- 채택 비용: 호출자 시그니처 변경 0 (`subscribe_filtered_stocks` 내부 1~5 줄 추가)
- 채택 효과: 단일 진실 원천 + 신규 전략 추가 시 hook 누락 위험 0 + AST 정적 가드 영구 보호

**위험 평가**: **HIGH** — 누락 시 *조용한 매수 통과* + 신규 전략 추가 race. 단일 hook + AST 가드 필수

---

## Q5 — WS 구독 슬롯 영향

**답변**: **RECOMMEND 디폴트 0/0 비활성 보존 + 운영자 1주 데이터 축적 후 임계 미세 조정**

**근거 (트레이더 시각)**:

### scanner 차단의 슬롯 절약 효과 정량 추정

사이클 28 실측 (HARNESS_CHANGELOG 인용): main=25/보조 9 = 합 34/41 (83% 슬롯 사용). 보유 = HIGH 절대 보장. 후순위 LOW = breakout/momentum/swing 후보.

운영자 임계 5,000 / 1,000,000 활성 시 추정 차단 비율:
- 5,000원 미만 = KOSPI/KOSDAQ 합 ~15% (2024년 KRX 통계, 동전주 + 저가주)
- 1,000,000원 초과 = KOSPI/KOSDAQ 합 ~2~3% (소수 초고가주)
- 합계 차단 비율 = **17~18%** → 후보 34 종목 → 28 종목 (6 종목 절약)

**효과 평가**:
- HIGH (보유/익일청산) 영향 0 (옵션 D 절대 보호)
- LOW 후순위 6 종목 절약 → 보조 세션 부담 감소 + `[priority_drop]` 발생 빈도 감소
- 사이클 24 silent inactive 감지 (fresh_ratio < 20%) 임계 도달 위험 자연 감소

### 운영자 디폴트 0/0 보존 권고

사이클 62 답습 — 디폴트 비활성 → 운영자 *명시 활성* → 데이터 축적 → 임계 미세 조정. 사이클 64 위치 변경은 *효과 강화 + 슬롯 절약* 이라 디폴트 활성 유혹 강하나, **운영 데이터 1주 (실제로 사이클 62 운영 1일차 종결 시점) 만큼은 비활성 권고**.

→ Q7-3 (신규 발의) 와 연계 — 사이클 62 운영 데이터 1일 손실 인계 + 사이클 64 신규 위치 1주 운영 후 임계 권고

### donchian_swing 보유 종목 BREAKOUT_LOW_CAP=25 보호

scanner.py `BREAKOUT_LOW_CAP=25` 영속 의무 — 가격 필터 활성화 시에도 변경 0. 옵션 D `protected_tickers` 가 자동 보호 → donchian 보유 KOSPI200 종목은 cap 적용 *전* protected 분리 → cap 영향 0.

**구현 가이드**:
1. 디폴트 0/0 보존 (사이클 62 답습)
2. 운영자 1주 운영 후 `[price_filter_scanner_skip]` 로그 카운트 + funnel snapshot 차단 종목 분석 → 임계 권고 (예: 5,000 / 800,000 또는 3,000 / 1,500,000)
3. 사이클 67+ 거래대금 필터 도입 시 가격 필터 임계 재평가 (작전주 차단 분담)

**트레이드오프**:
- 채택 비용: 디폴트 0/0 → 운영자 명시 활성화 의무 (UX 부담)
- 채택 효과: 운영자 인지 + 데이터 축적 후 정밀 임계 + 보유 절대 보호

**위험 평가**: **LOW** (긍정 효과 우세)

---

## Q6 — 사이클 62 회귀 가드 폐기 범위 검증 (도메인 시각)

**답변**: **RECOMMEND team-leader 1차 폐기/갱신 범위 동의 + 1 의제 추가 (H 카테고리 일일 집계는 scanner 영역 이전 — 옵션 B 권고)**

**근거 (트레이더 시각)**:

### 폐기 18 케이스 검증 — 도메인 시각 추가 의견 없음

team-leader 1차 분류 (B 4 + D 2 + F 5 + G 2 + H 1 + B&FE-5) 적절. 모드 폐기 + risk.on_tick 영역 자체 제거 → 자연 폐기. 사이클 62 코드 본체 제거 = G 신규 1 케이스 (AST 정적 가드) 로 영속 보호.

### H 카테고리 (일일 집계) — 옵션 B (scanner 영역 이전) RECOMMEND

team-leader 의뢰서 Q6.1 옵션:
- 옵션 A (폐기) — 단순화 우선
- 옵션 B (scanner 영역 이전) — 일일 차단 카운트 + reason 분포
- 옵션 C (funnel snapshot 통합)

**옵션 B RECOMMEND** 근거:
1. **운영자 가시화 트레이더 본능** — 디폴트 0/0 비활성 환경에서도 운영자 *활성 1주 후 차단 비율 한눈에 파악* 가치 있음. `[price_filter_scanner_daily_summary] mode=scanner_position_change min=5000 max=1000000 daily_skip=N reasons={below_min:3, above_max:1, no_prev_close:5}` 1행 INFO 발화
2. **사이클 41 funnel 진단 패턴 답습** — 사이클 41 Pullback 9→0 결함 영구 기록 가치 (사이클 49 시정 root cause). 가격 필터도 *조용한 차단 누적* 위험 → 일일 집계로 시각화 의무
3. **옵션 C funnel 통합은 본 사이클 범위 밖** — 사이클 34/41 funnel hook 영역 추가 의제 = 별도 사이클 분리 권고

**구현 가이드**:
```python
# scheduler._settle() 직전 호출
await scanner.emit_price_filter_scanner_daily_summary()

# scanner.py 신규
async def emit_price_filter_scanner_daily_summary() -> None:
    """일일 차단 카운트 + reason 분포 1행 INFO + system_logs."""
    pf = await _get_price_filter_for_scanner()
    msg = (
        f"[price_filter_scanner_daily_summary] active={pf.is_active} "
        f"min={pf.min_price} max={pf.max_price} "
        f"daily_skip={_price_filter_scanner_skip_count_today} "
        f"reasons={dict(_price_filter_scanner_skip_reasons_today)}"
    )
    logger.info(msg)
    try:
        from src.db.system_logs import write_log
        await write_log("INFO", msg)
    except Exception:
        logger.debug("[price_filter_scanner_daily_summary] write_log 실패", exc_info=True)
```

회귀 가드 H 신규 1 케이스 (scanner 영역 일일 집계). team-leader 1차 신규 20 → **21 케이스**.

### 사이클 62 E 카테고리 (매도 영향 0) — *재검증 필수* 동의

team-leader 권고 "E 4 케이스 → scanner 영역에서 동일 행위 보존 재검증 + E-4 AST 가드 유지 (risk → scanner)" 동의. 매도/익일청산/손절/Trailing/15:20 강제청산 영향 0 보장은 *사이클 38 명문화 영속 의무* 라 영역 변경에도 회귀 가드 형태 유지. 단, 본 사이클 신규 C 카테고리 (보유/익일청산 절대 보호 3 케이스) 와 *행위 중복* 가능성 → 정리 권고:
- E-1, E-2, E-3 → scanner 영역 신규 C-1, C-2, C-3 와 *동일 행위 검증* → C 카테고리로 통합
- E-4 AST 가드 → 영역 변경 (risk → scanner) 보존 + G 신규 (risk.py 에 price_filter 참조 0건) 와 통합

→ 사이클 62 E 4 케이스 → 사이클 64 C+G 카테고리 흡수 통합 → 중복 회귀 가드 차단

### 최종 회귀 가드 합계

team-leader 1차 (폐기 18 + 갱신 8 + 신규 20 = ~32) → 도메인 권고 후:
- 폐기: 18 케이스 동의 (변경 0)
- 갱신: 8 케이스 동의
- 신규: 20 → **21** (H 신규 1 추가) + **C-4 신규 (HIGH 옵션 D 답습)** → **22 케이스**
- 합계: 갱신 8 + 신규 22 = **30 케이스 (HIGH 4 + MEDIUM 7 + LOW 19)**

---

## Q7 (신규 발의) — 5건 — 트레이더 시각 추가 위험 + 대안

### Q7-1 (HIGH) — scanner 차단이 *기존 구독 종목 unsubscribe 발화* 위험

**의제**: 운영 중 임계 변경 시 (예: Settings UI 에서 max 1,000,000 → 500,000 변경) 기존 *이미 구독된 매수 후보 종목* (예: 800,000원 종목) 을 자동 unsubscribe 해야 하는가?

**답변**: **AVOID 자동 unsubscribe** — *다음 `_scan_loop` 5분 사이클 자연 delta unsubscribe* 위임. 보유/익일청산 절대 보호 영속.

**근거 (트레이더 시각)**:
- 사이클 15-A `_delta_unsubscribe_dropped(new_set)` 패턴 = "빠진 종목만 unsubscribe" 자연 처리. 가격 필터 변경 후 다음 `_scan_loop` 진입 → `_apply_price_filter` 적용 → 새 후보 풀 → delta unsubscribe → KIS LMS 위험 0
- 즉시 unsubscribe 시 (사용자 UI 토글 즉시 반영) → KIS 등록/해제 race → 사이클 17 OPSP0002 폭주 위험 (KIS 공지 "비정상 케이스 2 무한 등록/해제") 재발
- 보유 종목은 옵션 D `protected_tickers` 가 자동 보호 → unsubscribe 후보 자체 안 됨 → 시세 끊김 0

**구현 가이드**: `invalidate_price_filter_cache_scanner()` 는 *캐시만 무효화* + *unsubscribe 발화 안 함*. 다음 `_scan_loop` 5분 자연 적용.

**위험 평가**: **HIGH** (잘못 구현 시 KIS LMS chain — 사이클 17 답습 의무)

---

### Q7-2 (MEDIUM) — `prdy_clpr` 캐시 stale 위험 (정정/액면분할 시 즉시 invalidate)

**의제**: stock_master 24h TTL 캐시 → 정정공시/액면분할 발생 시 *전일종가* 가 *현재 가격대* 와 50% 이상 괴리 가능 → 가격 필터 결함

**답변**: **CONSIDER** — 본 사이클 영역 밖, 다만 가시화 의무

**근거 (트레이더 시각)**:
- 액면분할 예: 삼성전자 2018.05 (50:1 분할) → 전일종가 2,650,000 → 50,000 갑작 변경. stock_master 24h 캐시면 *분할 후 24h* 까지 가격 필터 *오작동 가능* (max=1,000,000 시 분할 후 50,000 종목이 *원래 100% 분할 대상* 인데 *통과 처리*)
- 본 시스템은 액면분할 자동 감지 미구현 → KIS 응답 자체에서 *분할 적용 prdy_clpr* 가 자연 갱신 (다음 `_eager_refresh_stock_master_for_held_positions` 또는 사이클 매수 시점 lazy 갱신)
- 트레이더 본능: 액면분할은 분할 1~3일 전 KIS 공시 → 운영자 인지 가능. 자동 invalidate 메커니즘은 *추후 카드*

**구현 가이드**: 본 사이클 변경 0. `_workspace/00_leader_trading_rules.md` 에 *후속 카드* 명시:
- 후속 카드 #X (LOW): 액면분할/정정공시 발생 시 `stock_master` invalidate 메커니즘 (KIS 공시 API + 24h 미만 TTL 분할 종목 자동 갱신)

**위험 평가**: **LOW** (희소 사건, 본 사이클 영역 밖)

---

### Q7-3 (MEDIUM) — 사이클 62 운영 데이터 1일 손실 인계

**의제**: 사이클 62 (2026-06-05 종결, 디폴트 0/0 비활성) 운영 1일 후 사이클 64 위치 변경 → *사이클 62 risk.on_tick 영역 운영 로그 1일* 만 축적되고 *영원히 미활용*

**답변**: **CONSIDER** — 사이클 63 회고 (HARNESS_CHANGELOG) 에 명시 영구 기록 권고

**근거 (트레이더 시각)**:
- 사이클 62 운영 1일 (2026-06-05 ~ 2026-06-06 KST) 의 `[price_filter_skip]` / `[price_filter_warn]` / `[price_filter_daily_summary]` 로그 = 디폴트 OFF 라 차단 0 → 운영 데이터 0 (자연 손실 0)
- 그러나 운영자가 활성화 했을 경우 (가능성 낮음) 1일 데이터 손실 → *추적 불가능 영구 손실*
- 사이클 64 신규 prefix `[price_filter_scanner_skip]` 로 명확 분리 → 사이클 62 로그 가 잔존해도 *혼동 없음* (prefix 다름)

**구현 가이드**: HARNESS_CHANGELOG.md 사이클 64 행에 다음 명시:
> "사이클 62 (디폴트 OFF) 운영 1일 후 위치 변경 — 사이클 62 영역 로그 (`[price_filter_skip]` / `[price_filter_warn]` / `[price_filter_daily_summary]`) 는 운영 데이터 손실 0 (디폴트 OFF, 차단 0). 사이클 64 신규 prefix `[price_filter_scanner_skip]` / `[price_filter_scanner_daily_summary]` 로 영구 분리"

**위험 평가**: **LOW** (디폴트 OFF 영속 → 데이터 손실 0)

---

### Q7-4 (MEDIUM) — funnel `step_no` 별도 단계 분리

**의제**: scanner 차단 종목 = `strategy_funnel_snapshots` 의 어느 step 에 표시?

**답변**: **RECOMMEND** — 사이클 32 R4 universe guard 와 분리 + step_no=98 신규 (사이클 41 명세 답습)

**근거 (트레이더 시각)**:
- 사이클 41 funnel 명세: BFB/VCP/donchian 각 8 단계 + 최종 step_no=99. universe guard 차단 = 별도 step 으로 *원인 분리* 필요
- 가격 필터 차단도 *원인 분리* 의무 — *작전주 차단 효과* vs *유량 우량주 차단 결함* 구분 가능
- 권고 step_no:
  - step_no=97 = universe guard 차단 (사이클 32 R4) — 신규 별도 step 분리 (현재 미구현)
  - **step_no=98 = 가격 필터 차단 (사이클 64 신규)** — survived/excluded 분리 + reason (below_min/above_max/no_prev_close)
  - step_no=99 = 최종 (사이클 41 영속)

**구현 가이드**: 본 사이클 범위에 *추가 회귀 가드 1 케이스* 만 — `_apply_price_filter` 호출 시 funnel snapshot hook (optional, default off) 추가. 본 사이클 핵심 영역 (가격 필터 분리) 과 분리. 운영자가 funnel snapshot 모니터링 시 자연 확인:
```python
# scanner._apply_price_filter 내부 끝
try:
    from src.db.strategy_funnel import insert_snapshot
    await insert_snapshot(
        target_date=today_kst,
        strategy_id="ALL",  # 단일 hook 이라 strategy 분리 불가 — ALL 전략 공통
        step_no=98,
        step_name="price_filter_scanner",
        survived_count=len(survivors),
        survived_tickers=[{"ticker": t} for t in survivors[:200]],
        excluded_count=len(candidates) - len(survivors),
        excluded_sample=[{"ticker": t, "reason": "below_min/above_max/no_prev_close"} for t in excluded[:20]],
    )
except Exception:
    logger.debug("[price_filter_scanner_funnel] hook 실패 graceful", exc_info=True)
```

→ 회귀 가드 F 신규 1 케이스 (funnel hook). team-leader 1차 신규 20 → **22 (H+F)** + Q1 옵션 D C-4 = **23 케이스**

**위험 평가**: **LOW** (운영자 가시화 가치)

---

### Q7-5 (HIGH) — 사이클 62 갭상승 회피 효과 영구 폐기 위험

**의제**: 사이클 62 §Q2 fallback (전일종가 + 현재가 fallback) 으로 *갭상승 종목* (전일 4,500원 동전주 → 시초 5,200원 +15%) 차단 효과를 사이클 64 (전일종가 단독) 가 *영구 폐기* — 작전주 갭상승 진입 결함 재발 위험

**답변**: **CONSIDER** — 사용자/team-leader 사전 결정 보존 (scanner = WS 구독 *전* → 현재가 미확보 = 구조적 한계) + 거래대금 동행 필터 (사이클 67+) 로 *결을 다른 차원에서* 보강 의무

**근거 (트레이더 시각)**:

### 사이클 62 답변 §Q2 인용
> "시나리오: 종목 A 전일종가 4,500원 (저가 필터 5,000원 차단 대상). 9:00 시초가 5,200원 갭상승 (+15%) → momentum 등락률 컷오프 통과. 09:31 현재가 5,300원 → 당일 현재가 기준 필터 *통과* (5,300 > 5,000). 그러나 *트레이더 의도는 "이 종목은 원래 동전주"* 라 차단이 맞다."

→ 사이클 62 채택 옵션 (전일종가 우선 + 현재가 fallback) 은 *전일종가 우선 평가* 라 갭상승 종목 = *전일 4,500원 기준* 차단. 사이클 64 = 전일종가 단독 → *동일 차단 유지* (사이클 62 시정 효과 영속)

### 사이클 64 결함 시나리오 — *전일종가 부재* 종목의 갭상승

위 시나리오 변형:
- 신규 상장 1일차 종목 X: `prdy_clpr=0` (전일 거래 없음). 시초가 8,000원 (IPO 부진) → 11:00 +30% 상한가 10,400원 도달 → momentum +30% 차단 (상한가 컷오프)
- 신규 상장 1일차 작전주 Y: `prdy_clpr=0`. 시초가 1,000원 (IPO 흥행 실패) → +25% 등락률 1,250원 도달 → momentum 후보 진입 → **graceful 통과 (사이클 64) → 매수 발화** → 트레이더 본능 *위반* (전일종가 없는데 1,250원 = 명백히 동전주)

→ **사이클 64 graceful 통과 (Q2) 가 작전주 신규 상장 매수 진입 통로**

### 보강 권고 — 거래대금 동행 필터 (사이클 67+) 우선순위 격상

사이클 62 §Q7 발의 = 거래대금 동행 필터 (사이클 63+ 권고). 사이클 64 가 *갭상승 회피 효과 폐기* 한 이상, *동전주 작전주 차단의 다른 차원* (거래대금) 필요성이 *사이클 62 시점보다 격상*:
- 가격 필터 = 가격 1차원 차단 (사이클 64)
- 거래대금 필터 = 가격 × 거래량 = 2차원 차단 (사이클 67+) — 작전주 = *거래대금 < 5억* 영역 자연 차단
- 신규 상장 작전주 = 거래대금 < 1억 빈번 → 사이클 67+ 거래대금 1억 임계 활성화 시 자동 차단

**구현 가이드**: 본 사이클 변경 0. `_workspace/cycle64_*` 의 *후속 카드* 에 다음 명시:
- 후속 카드 #N (HIGH): **사이클 67+ 거래대금 동행 필터 우선순위 격상** — 사이클 64 가격 필터 위치 변경으로 갭상승 회피 효과 폐기 → 거래대금 필터 (1억/5억/10억 임계) 가 작전주 차단 *유일 메커니즘*. 사이클 67 발주 의무

**대안 1** (본 사이클 즉시 시정 — 단순화 위반): scanner 단계에서 시가 (`open_price`) 도 fetch → 전일종가 부재 시 시가 fallback. KIS 호출 폭주 위험 (Q2 동일) → 채택 곤란.

**대안 2** (사이클 65 즉시 발주): 사이클 64 즉시 후 *사이클 65 = 거래대금 동행 필터* 별도 발주. 사이클 64 운영 1주 데이터 축적 *불필요* (갭상승 회피 효과 폐기 즉시 시정 우선).

→ team-leader 권고: **사이클 65 거래대금 동행 필터 즉시 발주** 검토. 본 사이클 운영 데이터 1주 대기 후 사이클 67+ 발주 vs 즉시 발주 사용자 결정 의무.

**위험 평가**: **HIGH** — 갭상승 회피 효과 폐기 = 작전주 매수 진입 통로 재발 위험. 거래대금 필터 우선순위 격상 의무

---

## team-leader 1차 권고와의 차이점 매트릭스

| 의제 | team-leader 1차 | domain-expert 회신 | 차이 이유 |
|---|---|---|---|
| Q1 옵션 | 옵션 A/B/C 중 결정 | **옵션 A + D 신규 (3 중 안전망)** | hot path 호출 빈도 사이클 32 R4 의 100배 → AST 가드 + 헬퍼 + early-return |
| Q2 prdy_clpr 미확보 | graceful 통과 + KIS 사전 fetch 2순위 | **graceful 통과 + KIS 사전 fetch 비채택** | Rate Limit + hot path 부담. stock_master 단독 |
| Q3 신규 상장 | 옵션 A/B/C 결정 | **옵션 B (graceful 통과 + 전략별 자연 필터)** | IPO 흥행 매수 기회 보존. 작전주는 Q7-5 거래대금 필터 위임 |
| Q4 진입점 | 옵션 A+C 권고 | **동의** + `subscribe_filtered_stocks` 내부 1차 hook + 호출자 시그니처 변경 0 | 단일 진실 원천 + 자동 통과 + 신규 전략 추가 누락 차단 |
| Q5 슬롯 영향 | 디폴트 0/0 + 1주 후 임계 | **동의** + 운영자 가시화 의무 (Q6 H 영역) | 운영자 인지 + 데이터 축적 |
| Q6 H 카테고리 | 폐기 또는 scanner 이전 | **scanner 영역 이전 (옵션 B)** + funnel hook (Q7-4) | 사이클 41 funnel 진단 패턴 답습 |
| Q7+ 자유 발의 | 5 예시 영역 안내 | **Q7-1~Q7-5 5건 신규 발의** | Q7-5 HIGH (갭상승 회피 효과 폐기 위험) |

---

## 우선순위 결정 매트릭스 (사용자 확정 의무 영역)

| 의제 | 변경 가능성 | 사용자 확정 우선순위 | 사유 |
|---|---|---|---|
| **Q7-5 거래대금 필터 우선순위 격상** | HIGH | **1순위** | 사이클 64 가격 필터 갭상승 회피 효과 폐기 즉시 보강. 사이클 65 즉시 발주 vs 사이클 67 1주 대기 결정 |
| **Q1 옵션 D (3 중 안전망)** | HIGH | **2순위** | hot path 호출 빈도 사이클 32 R4 100배 → 시세 끊김 결함 차단 필수. AST 가드 + 헬퍼 추가 회귀 가드 비용 |
| **Q4 진입점 옵션 A** | HIGH | **3순위** | subscribe_filtered_stocks 내부 hook 채택 시 호출자 시그니처 변경 0 + AST 가드 |
| Q2 KIS 사전 fetch 비채택 | MEDIUM | **4순위** | 설계 카드 §2.2 2순위 폐기. Rate Limit 위험 |
| Q6 H 카테고리 scanner 이전 | MEDIUM | **5순위** | 운영자 가시화 + 회귀 가드 1 케이스 |
| Q3 옵션 B (graceful + 자연 필터) | MEDIUM | **6순위** | IPO 흥행 보존 + 작전주는 Q7-5 위임 |
| Q7-1 자동 unsubscribe 방지 | HIGH | **7순위** | KIS LMS chain 차단 — invalidate_cache 가 unsubscribe 발화 안 함 의무 |
| Q5 디폴트 0/0 보존 | LOW | **8순위** | 사이클 62 답습 |
| Q7-4 funnel hook step_no=98 | LOW | **9순위** | 운영자 가시화 |
| Q7-2 액면분할 invalidate | LOW | **10순위** | 후속 카드 |
| Q7-3 사이클 62 데이터 손실 | LOW | **11순위** | 디폴트 OFF 영속 → 데이터 손실 0 |

---

## 회귀 가드 영향 매트릭스 (도메인 권고 후)

| 카테고리 | team-leader 1차 | 도메인 권고 후 | 변경 |
|---|---|---|---|
| A (system_config 단순화) | 4 | 4 | 변경 0 |
| B (`_apply_price_filter`) | 5 | 5 | 변경 0 |
| **C (보유/익일청산 절대 보호 HIGH)** | 3 | **4** | C-4 신규 (`_collect_protected_tickers_for_scanner` 정확성, Q1 옵션 D) |
| D (60s TTL 캐시) | 2 | 2 | 변경 0 |
| E (emit cap) | 2 | 2 | 변경 0 |
| F (integration E2E) | 3 | **4** | F-4 신규 (funnel step_no=98 hook, Q7-4) |
| **G (AST 정적)** | 1 | **2** | G-2 신규 (`_apply_price_filter` 호출 `protected_tickers=` keyword 의무, Q1 옵션 D) |
| **H (일일 집계 신규)** | 0 | **1** | H-1 신규 (`emit_price_filter_scanner_daily_summary`, Q6 옵션 B) |
| **합계 신규** | **20** | **24** | +4 (도메인 권고 4건 추가) |
| 갱신 (사이클 62) | 8 | 8 | 변경 0 |
| 폐기 (사이클 62) | 18 | 18 | 변경 0 |
| **합계 (신규 + 갱신)** | **28** | **32** | +4 |

**안전성 분포 (도메인 권고 후)**:
- **HIGH 5** (C-1, C-2, C-3, C-4 + G-2) — 보유/익일청산 절대 보호 + AST 가드
- **MEDIUM 8** — scanner 진입점 + 60s 캐시 + Settings PUT 즉시 반영 + WS 슬롯 영향 + 사이클 62 코드 제거 + H 신규 + F-4 funnel + Q7-1 KIS LMS 방지
- **LOW 19** — DB 단순화 + API 라우트 + Settings 카드 + emit cap 등

---

## 안전 규칙 위반 가능성 (최종 점검)

| CLAUDE.md 절대 규칙 | 본 사이클 영향 | 검증 |
|---|---|---|
| 체결통보 구독 (H0STCNI0/9) | 영향 0 | scanner 단계 신규 |
| uvicorn 단일 워커 | 영향 0 | — |
| WebSocket 4 중 안전망 (F1+scan_loop+K stale watcher+resubscribe_stale) | 영향 0 | scanner 차단 종목 = 구독 자체 없음 → stale 진입 안 함 |
| `tradable_boards` 매수 진입 전용 (사이클 38) | **본 카드 핵심 영역 직접** | scanner 차단 = 매수 진입 게이트만. 매도/익일청산/손절/15:20 강제청산 영향 0 |
| `_reset_daily_state` 동행 reset | 의무 | emit cap + count + reasons dict + protected_tickers 캐시 모두 reset |
| KST 강제 | 영향 0 | — |
| 매수 시장가 거부 5호가 폴백 | 영향 0 | scanner 단계 = order_engine 영역 무관 |
| NXT 좀비 차단 (사이클 52~57) | 영향 0 | 매도 영역 |
| 15:20 강제청산 (VB) | 영향 0 | 매도 영역 |
| 상한가 손절 모니터링 (5 전략) | 영향 0 | 매도 영역 |
| **WebSocket 시세 보유·익일청산 우선 보장 (MAX 41)** | **본 카드 핵심 영역 직접** | Q1 옵션 D `protected_tickers` 최상단 early-return 가드 의무. AST 정적 가드 G-2 영속 |
| **K stale watcher 우선순위 분리 (사이클 29-R3)** | 영향 0 | scanner 차단 종목 = 구독 안 됨 → stale 진입 안 함 |

→ **CLAUDE.md 절대 규칙 위반 0**. 단 **Q1 옵션 D + Q7-1 (KIS LMS 차단)** 영속 의무.

---

## 후속 카드 인계 (사이클 65+)

| 카드 # | 위험 | 의제 | 사유 |
|---|---|---|---|
| #X (HIGH) | 거래대금 동행 필터 (Q7-5) | 사이클 65 즉시 발주 vs 사이클 67+ 1주 대기 결정 — 사용자 의무 | 사이클 64 갭상승 회피 효과 폐기 즉시 보강 |
| #Y (LOW) | 액면분할/정정공시 invalidate (Q7-2) | KIS 공시 API + 24h 미만 TTL 분할 종목 자동 갱신 | 희소 사건, 본 사이클 영역 밖 |
| #Z (MEDIUM) | universe guard funnel step 분리 (Q7-4) | step_no=97 universe guard / step_no=98 가격 필터 / step_no=99 최종 | 사이클 41 funnel 명세 정합 |
| #5 (HIGH, 사이클 63 인계) | `_resubscribe_stale_priority` cap=10 priority 분리 결함 | priority 분리 *후* HIGH 먼저 + LOW 잔여 cap | 사이클 64 영향 0 (별도 영역) |
| #14 (MEDIUM, 사이클 63 인계) | `stale_manager.py` 1,076L sub-module 분해 | 3+1 청사진 | 사이클 64 영향 0 |

---

## 후속 검증 권고 (tdd-engineer / tester)

### tdd-engineer Red 명세 추가 케이스 (team-leader 20 → 24)

| # | 카테고리 | 케이스 |
|---|---|---|
| +1 | C (HIGH) | C-4: `_collect_protected_tickers_for_scanner()` 가 positions + `_pending_next_day_clear` 합집합 정확성. 단일 헬퍼 통과 의무 |
| +2 | G (HIGH) | G-2: `_apply_price_filter` 호출 시 `protected_tickers=` keyword-only 인자 필수 (AST 정적 가드) |
| +3 | F (MEDIUM) | F-4: `_apply_price_filter` 내부 funnel step_no=98 hook 정상 호출 (excluded 종목 reason 분류) |
| +4 | H (MEDIUM) | H-1: `_settle()` 직전 `emit_price_filter_scanner_daily_summary()` 1행 INFO + system_logs |

### tester Verify 추가 시나리오

1. **Q7-1 KIS LMS 차단**: Settings UI 임계 변경 → `invalidate_price_filter_cache_scanner()` 즉시 호출 → 다음 `_scan_loop` 5분 자연 delta unsubscribe (즉시 unsubscribe 발화 0건 검증)
2. **옵션 D 3 중 안전망**: 보유 종목이 임계 외 가격 변동 시 → scanner 통과 (protected 보호) → WS 구독 유지 → 손절 발화 정상 (시세 끊김 0)
3. **Q3 신규 상장 graceful 통과**: `prdy_clpr=0` 종목 → 통과 → momentum 매수 진입 정상
4. **Q7-5 갭상승 회피 효과 폐기 시뮬레이션**: 신규 상장 작전주 (`prdy_clpr=0`, 시초가 1,000원, +25% 후 1,250원) → graceful 통과 결함 시나리오 정량 측정 → 거래대금 필터 (사이클 65/67) 우선순위 정량 근거
5. **flakiness 3회 반복**: HIGH 5 케이스 (C-1~C-4 + G-2) freezegun 3회 반복 안정성

---

## 핵심 결론 재확인

1. **사용자 사전 결정 4건 전부 트레이더 시각 RECOMMEND** (위치 이전 + 모드 폐기 + 전일종가 단독 + DailyEmitCap 1회/일)
2. **Q1 옵션 D 신규 (3 중 안전망)** — hot path 100배라 사이클 32 R4 답습 단독 부족
3. **Q2 KIS 사전 fetch 비채택** — Rate Limit + hot path 부담 (설계 카드 §2.2 2순위 폐기)
4. **Q4 진입점 옵션 A (`subscribe_filtered_stocks` 내부 hook)** — 호출자 시그니처 변경 0 + 신규 전략 추가 누락 차단
5. **Q6 H 카테고리 scanner 이전 (옵션 B)** — 운영자 가시화 의무
6. **Q7 신규 발의 5건** — 핵심 **Q7-5 (HIGH) 거래대금 필터 우선순위 격상** + Q7-1 (HIGH) KIS LMS 차단
7. **회귀 가드 합계** — team-leader 1차 20 → **24** (HIGH +1, MEDIUM +2, LOW +1)
8. **CLAUDE.md 절대 규칙 위반 0** — 단 Q1 옵션 D + Q7-1 영속 의무
9. **사용자 결정 1순위** = Q7-5 거래대금 필터 사이클 65 즉시 발주 vs 사이클 67+ 1주 대기

본 회신은 권고이며, team-leader 가 채택 결정 후 사용자 확정 의무.

---

## 산출물 경로

- 본 응답서: `_workspace/cycle64_price_filter_scanner_domain_response.md`
- 자문 의뢰서: `_workspace/cycle64_price_filter_scanner_domain_consult.md` (수신)
- 설계 카드 v1: `_workspace/cycle64_price_filter_scanner_design_card.md` (참조)
- 사이클 62 회신: `_workspace/cycle62_price_filter_domain_response.md` (선행 참조)
