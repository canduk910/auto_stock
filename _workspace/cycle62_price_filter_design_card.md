# 사이클 62 가격 필터 — 설계 카드 (1차 sketch)

> **작성**: team-leader (2026-06-05 13:35 KST, 사이클 61 sync-docs 완료 직후 동행 작성)
> **사용자 결정 (사이클 60 사후 확정)**:
> - 필터 의도 = 양쪽 밴드 `[min, max]` (저가 + 초고가 동시 차단)
> - 적용 시점 = scanner 조건검색 직후 (전 전략 공통)
> - 사이클 분할 = 백엔드 + 프론트 단일 사이클
> - 위험 등급 = MEDIUM (매수 차단만 — 자금 손실 0, 기회비용만)
> - push 시점 = NXT 애프터 (주말 의무 없음)
> **선행 자문**: `_workspace/cycle62_price_filter_domain_consult.md` (Q1~Q6 + 자유 발의)
> **자문 응답 예정 경로**: `_workspace/cycle62_price_filter_domain_response.md`
> **CLAUDE.md 절대 규칙 충돌**: 없음 (매수 진입 전용, `tradable_boards` 사이클 38 명문화 답습)

---

## 0. 자문 결과 후 변경 가능 영역 (*TBD-Qn* 표기)

| 영역 | 의제 | 기본 sketch |
|---|---|---|
| 임계 디폴트 (저/고) | Q1 | 저=0 (비활성) / 고=0 (비활성) — *TBD-Q1* |
| 비교 가격 (전일종가 vs 당일현재가) | Q2 | 당일 현재가 (`stck_prpr`) — *TBD-Q2* (자문 결과로 변경 가능) |
| 미확보 처리 (graceful vs 보수적) | Q2 | graceful 통과 (필터 비활성) — *TBD-Q2* |
| 보유 매도 영향 (확정 재확인) | Q3 | 매수만 필터 (사이클 38 답습) — **확정** |
| 운영 모드 수 (1/2/3/4 모드) | Q4 | HARD 단일 — *TBD-Q4* |
| 반영 시점 (즉시 vs 익일) | Q5 | 즉시 + 60s TTL 캐시 — *TBD-Q5* |
| funnel 추적 단계 | Q6 | 별도 prefix 로그 + funnel hook 옵셔널 — *TBD-Q6* |

---

## 1. DB 스키마

### 1.1 `system_config` 신규 키 (3 종, Q4 결과 의존)

```python
# src/db/system_config.py (확장)

_PRICE_FILTER_MIN_KEY = "price_filter_min"   # 정수 (원). 0 = 비활성
_PRICE_FILTER_MAX_KEY = "price_filter_max"   # 정수 (원). 0 = 비활성 (무한대 의미)
_PRICE_FILTER_MODE_KEY = "price_filter_mode" # *TBD-Q4*: "HARD" 단일 또는 "HARD"/"WARN"/"OFF" 3 모드

_PRICE_FILTER_MIN_DEFAULT = 0   # *TBD-Q1*
_PRICE_FILTER_MAX_DEFAULT = 0   # *TBD-Q1*
_PRICE_FILTER_MODE_DEFAULT = "OFF"  # *TBD-Q4*. 안전 우선 (사이클 31 buy_block_mode 답습)

# 범위 (운영자 슬라이더 한도)
_PRICE_FILTER_MIN_BOUND = (0, 50_000)        # *TBD-Q1* — 0 ~ 5만원
_PRICE_FILTER_MAX_BOUND = (0, 2_000_000)     # *TBD-Q1* — 0 ~ 200만원
_PRICE_FILTER_MIN_STEP = 1_000                # 1,000원 단위
_PRICE_FILTER_MAX_STEP = 10_000               # 10,000원 단위
_PRICE_FILTER_VALID_MODES = ("HARD", "WARN", "OFF")  # *TBD-Q4*
```

### 1.2 헬퍼 시그니처 (`cash_usage_ratio` 패턴 답습)

```python
from pydantic import BaseModel

class PriceFilter(BaseModel):
    """가격 필터 설정 (사이클 62, 2026-06-05)."""
    min_price: int  # 0 = 비활성
    max_price: int  # 0 = 비활성 (무한대 의미)
    mode: str       # "HARD" / "WARN" / "OFF"

    @property
    def is_active(self) -> bool:
        """min 또는 max 가 0 초과 + mode != OFF 면 활성."""
        return self.mode != "OFF" and (self.min_price > 0 or self.max_price > 0)


async def get_price_filter() -> PriceFilter:
    """현재 가격 필터 설정 조회. 키 부재 시 디폴트 반환 (모두 비활성).

    `buy_block_mode` 패턴 답습 — 3 키 병합 + Pydantic 반환.
    """
    ...

async def set_price_filter(
    *,
    min_price: int | None = None,
    max_price: int | None = None,
    mode: str | None = None,
) -> None:
    """부분 갱신 — None 인 키는 보존. 범위 외 ValueError. 모드 외 ValueError.

    `set_buy_block_thresholds` 부분 갱신 패턴 답습.

    절대 호출 직후 `invalidate_price_filter_cache()` (Q5 즉시 반영 시).
    """
    ...
```

### 1.3 마이그레이션

신규 마이그레이션 **불필요** — `system_config` 테이블은 기존 (key + value JSONB 구조). 키만 추가.

---

## 2. 적용 위치 (`src/engine/scanner.py`)

### 2.1 진입점 선택 (전 전략 공통 진실의 원천)

**선택**: `scanner.scan_stocks()` 의 *반환 직전* + `subscribe_filtered_stocks()` 의 *입력 직후* — 두 영역 분리 적용:
- **`scan_stocks()`** (momentum) — L215 `filtered.append(ticker)` 직전 신규 가드 (단일 함수 적용)
- **BFB / VCP / donchian / VB / LTV** `prepare()` 의 universe 결정 직후 — 6 전략 공통 가드 (자문 결과 후 결정)

**대안 검토**:
- 옵션 (가) **단일 진입점 (scanner.scan_stocks + prepare 6개)** — 코드 중복 가능성, 6 곳 변경
- 옵션 (나) **risk.on_tick 직전 단일 가드** — `state.is_low_funds_blocked` 옆에 신규 가드 1 줄 추가. **권고** (코드 변경 최소, 진입점 단일)
- 옵션 (다) **OrderEngine.execute_buy 진입 직후** — 가장 마지막 게이트, 호출 누락 0건 보장

**team-leader 권고**: **옵션 (나) `risk.on_tick`** — 사이클 31 `[risk_silent_skip]` 패턴 답습. 단일 진입점 + 모든 전략 자동 적용 + funnel 영향 분리 (scanner 단계는 무영향, risk 단계에서 차단).

### 2.2 비교 가격 데이터 소스 (Q2 결과 의존)

| 옵션 | 데이터 소스 | KIS 호출 | 정확도 | team-leader 권고 |
|---|---|---|---|---|
| (가) **당일 현재가** | `scanner.ticker_prices[ticker]["current_price"]` | 0 회 (WS 실시간) | 당일 갭상승/하락 영향 | **권고** — Rate Limit 보호 + risk.on_tick 진입점 일관 |
| (나) **전일 종가** | `stock_master.raw.prdy_clpr` | 0 회 (24h TTL) | 안정적, 작전주 회피 의도 부합 | 자문 결과 의존 — `stock_master.raw` 의 `prdy_clpr` 필드 미확보 시 fallback 정책 |
| (다) **두 영역 fallback** | (나) → (가) | 0 회 | 가장 안전 | 코드 복잡 |

**team-leader 권고**: **옵션 (가) 당일 현재가** — 사이클 61 stale_manager 패턴 일관 (실시간 데이터 우선). 자문 결과로 변경 가능.

### 2.3 필터 적용 코드 sketch (옵션 (나) `risk.on_tick`)

```python
# src/engine/risk.py (확장 — risk_silent_skip 패턴 답습)

async def on_tick(ticker, price_data):
    ...
    for strategy in self.registry.enabled():
        ...
        # 기존 가드 — 보드 / 매수 가드 / 중복 / 자금 사전 가드
        ...

        # 사이클 62 (2026-06-05) — 가격 필터 가드 (매수 진입 전용)
        price_filter = await self._get_price_filter_cached()  # 60s TTL
        if price_filter.is_active:
            current_price = price_data.get("current_price", 0)
            below_min = price_filter.min_price > 0 and current_price < price_filter.min_price
            above_max = price_filter.max_price > 0 and current_price > price_filter.max_price
            if below_min or above_max:
                reason = "below_min" if below_min else "above_max"
                if price_filter.mode == "HARD":
                    self._emit_price_filter_skip(ticker, strategy.id, reason, current_price, price_filter)
                    continue  # 매수 신호 평가 skip
                elif price_filter.mode == "WARN":
                    self._emit_price_filter_warn(ticker, strategy.id, reason, current_price, price_filter)
                    # 매수 허용 (WARN 모드)
                # OFF 는 if price_filter.is_active 분기 진입 안 함

        # 기존 check_buy_signal 로 진행
        ...
```

### 2.4 emit cap 정책 (1회/ticker/strategy/일)

사이클 31 `_risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]]` 패턴 답습:

```python
# RiskManager 필드 (사이클 56-D 패턴)
_price_filter_skip_logged_today: DailyEmitCap[tuple[str, str]] = field(default_factory=DailyEmitCap)
_price_filter_warn_logged_today: DailyEmitCap[tuple[str, str]] = field(default_factory=DailyEmitCap)

# emit 헬퍼
def _emit_price_filter_skip(self, ticker, strategy_id, reason, current_price, price_filter):
    key = (ticker, strategy_id)
    if not self._price_filter_skip_logged_today.should_emit(key):
        return  # 매 틱 폭주 차단 (cap)
    logger.info(
        "[price_filter_skip] ticker=%s strategy=%s reason=%s price=%d min=%d max=%d mode=%s",
        ticker, strategy_id, reason, current_price,
        price_filter.min_price, price_filter.max_price, price_filter.mode,
    )
    try:
        await write_log("INFO", f"[price_filter_skip] ticker={ticker} strategy={strategy_id} reason={reason} ...")
    except Exception:
        logger.debug("[price_filter_skip] write_log 실패", exc_info=True)
```

`reset_daily_state` 동행 reset (사이클 56-D 패턴 — RiskManager `reset_daily_state` 위임):
```python
def reset_daily_state(self) -> None:
    """RiskManager 일일 상태 초기화 (사이클 56-D, 사이클 62 확장)."""
    self._risk_silent_skip_logged_today.reset_daily()
    # 사이클 62 신규
    self._price_filter_skip_logged_today.reset_daily()
    self._price_filter_warn_logged_today.reset_daily()
```

### 2.5 60s TTL 캐시 (Q5 즉시 반영 시)

사이클 56-E `BUY_BLOCK_CACHE_TTL=60.0` 답습:

```python
# RiskManager 필드
_price_filter_cache: PriceFilter | None = field(default=None, compare=False, repr=False)
_price_filter_cache_expires_at: float = field(default=0.0, compare=False, repr=False)

PRICE_FILTER_CACHE_TTL = 60.0

async def _get_price_filter_cached(self) -> PriceFilter:
    """60s TTL 캐시. invalidate 토글 시 즉시 무효화."""
    import time as _t
    now = _t.monotonic()
    if self._price_filter_cache is not None and now < self._price_filter_cache_expires_at:
        return self._price_filter_cache
    pf = await get_price_filter()
    self._price_filter_cache = pf
    self._price_filter_cache_expires_at = now + PRICE_FILTER_CACHE_TTL
    return pf

def invalidate_price_filter_cache(self) -> None:
    """Settings PUT 직후 즉시 반영."""
    self._price_filter_cache = None
    self._price_filter_cache_expires_at = 0.0
```

---

## 3. API 라우트

### 3.1 신규 라우트 (`src/routes/system_integrations.py` 또는 신규 `price_filter.py`)

```python
# GET /api/system/price-filter — 현재 설정 조회
@router.get("/price-filter")
async def get_price_filter_endpoint():
    pf = await get_price_filter()
    return ApiResponse(success=True, data=pf, message="ok")

# PUT /api/system/price-filter — 부분 갱신
class PriceFilterRequest(BaseModel):
    min_price: int | None = None  # None = 보존
    max_price: int | None = None  # None = 보존
    mode: str | None = None       # None = 보존

@router.put("/price-filter")
async def set_price_filter_endpoint(req: PriceFilterRequest):
    try:
        await set_price_filter(
            min_price=req.min_price,
            max_price=req.max_price,
            mode=req.mode,
        )
        # 사이클 62 — 즉시 반영 (Q5 권고)
        from src.engine.scheduler import trading_scheduler
        trading_scheduler.risk_manager.invalidate_price_filter_cache()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(success=True, data=None, message="가격 필터가 즉시 반영되었습니다.")
```

**대안 1**: 기존 `strategies.py` 의 `set_cash_usage_ratio_endpoint` 옆에 추가 (cash_usage_ratio 패턴 답습)
**대안 2**: 신규 `src/routes/price_filter.py` 단독 라우트 (분리 명확성)
**team-leader 권고**: 대안 1 (`strategies.py` 옆) — 운영자가 한 곳에서 모든 매수 가드 관련 설정 조회 가능

---

## 4. UI (`frontend/src/pages/Settings.tsx`)

### 4.1 `PriceFilterCard` 신규 컴포넌트

```tsx
// frontend/src/components/PriceFilterCard.tsx (신규)

interface PriceFilter {
  min_price: number;  // 0 = 비활성
  max_price: number;  // 0 = 비활성
  mode: "HARD" | "WARN" | "OFF";
}

export function PriceFilterCard() {
  const [filter, setFilter] = useState<PriceFilter>({ min_price: 0, max_price: 0, mode: "OFF" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/system/price-filter").then(...).then(setFilter);
  }, []);

  const onSave = async () => {
    setSaving(true);
    await fetch("/api/system/price-filter", {
      method: "PUT",
      body: JSON.stringify(filter),
      headers: { "Content-Type": "application/json" },
    });
    setSaving(false);
    toast.success("가격 필터가 즉시 반영되었습니다.");  // Q5 즉시 반영
  };

  return (
    <Card>
      <CardHeader>가격 필터 (매수 진입 전용)</CardHeader>
      <CardBody>
        <Slider label="저가주 차단 (원)"
                min={0} max={50000} step={1000}
                value={filter.min_price}
                onChange={(v) => setFilter({...filter, min_price: v})} />
        <Tooltip text="0 = 비활성. 권장: *TBD-Q1*">권장값 보기</Tooltip>

        <Slider label="초고가주 차단 (원)"
                min={0} max={2000000} step={10000}
                value={filter.max_price}
                onChange={(v) => setFilter({...filter, max_price: v})} />
        <Tooltip text="0 = 비활성. 권장: *TBD-Q1*">권장값 보기</Tooltip>

        {/* Q4 결과로 3 모드면 토글 추가 */}
        <Select label="운영 모드"
                value={filter.mode}
                options={["HARD", "WARN", "OFF"]}  // *TBD-Q4*
                onChange={(v) => setFilter({...filter, mode: v as any})} />

        <Alert variant="info">본 필터는 매수 진입에만 적용됩니다. 보유 종목 매도 / 익일청산 / 손절 영향 0.</Alert>

        <Button onClick={onSave} loading={saving}>저장 (즉시 반영)</Button>
      </CardBody>
    </Card>
  );
}
```

### 4.2 Settings.tsx 통합

```tsx
// frontend/src/pages/Settings.tsx
import { PriceFilterCard } from "@/components/PriceFilterCard";

export default function Settings() {
  return (
    <div>
      {/* 기존 카드들 */}
      <CashUsageRatioCard />
      <BuyBlockCard />
      ...
      {/* 사이클 62 신규 */}
      <PriceFilterCard />
    </div>
  );
}
```

---

## 5. 회귀 가드 청사진 (사이클 60 A1 17 + 사이클 61 A2 20 패턴 답습)

### 5.1 백엔드 unit (~18 케이스)

| 카테고리 | 케이스 | 영역 |
|---|---|---|
| A `system_config` 헬퍼 | 5 | get/set 디폴트 / 부분 갱신 / 범위 외 ValueError / 모드 외 ValueError / Pydantic 검증 |
| B `risk.py` 필터 적용 | 4 | min 차단 / max 차단 / 비활성 통과 / mode=OFF 통과 |
| C emit cap | 2 | 같은 (ticker, strategy) 1회/일 emit / `reset_daily_state` 동행 reset |
| D 60s TTL 캐시 | 2 | hit / 만료 후 재조회 / invalidate 즉시 무효화 |
| E `tradable_boards` 매수 진입 전용 (사이클 38 답습) | 3 | 보유 손절 정상 발화 / 익일청산 정상 / 트레일링 정상 (필터 비활성 동작) |
| F 미확보 graceful (Q2 결과 의존) | 2 | `current_price=0` 시 필터 skip / `stock_master` miss 시 fallback |

### 5.2 백엔드 integration (~5 케이스)

| # | 시나리오 | 검증 |
|---|---|---|
| I-1 | scanner → strategy.prepare → risk.on_tick 매수 차단 흐름 | momentum 등락률 15% + 가격 필터 차단 → 매수 skip |
| I-2 | Settings PUT → 60s 캐시 invalidate → 다음 on_tick 즉시 반영 | E2E |
| I-3 | 보유 손절 정상 발화 (필터 활성 + 가격 < min) | 보유 종목 1주 매수 → 가격 폭락 → 손절 발화 (필터 영향 0) |
| I-4 | 익일청산 정상 (필터 활성 + 가격 > max) | `_pending_next_day_clear` → NXT 시장가 청산 (필터 영향 0) |
| I-5 | mode 변경 race (HARD → OFF 즉시 전환) | 5분 grace period 보장 또는 즉시 변경 검증 (Q5 결과 의존) |

### 5.3 백엔드 contract (~3 케이스)

| # | 시나리오 | 검증 |
|---|---|---|
| C-1 | `GET /api/system/price-filter` 200 + PriceFilter 응답 | Pydantic 스키마 검증 |
| C-2 | `PUT /api/system/price-filter` 200 + 부분 갱신 | 일부 키만 전달 시 나머지 보존 |
| C-3 | `PUT` 범위 외 → 400 + error message | `min_price=-1` / `max_price=3_000_000` / `mode="INVALID"` 모두 400 |

### 5.4 프론트 vitest (~5 케이스)

| # | 시나리오 | 검증 |
|---|---|---|
| F-1 | `PriceFilterCard` 초기 fetch + 렌더 | MSW mock /api/system/price-filter |
| F-2 | 슬라이더 조작 → state 갱신 | min/max 변경 확인 |
| F-3 | 저장 버튼 → PUT 호출 + toast | MSW + render |
| F-4 | 범위 외 입력 → 비활성 또는 clamp | UI 가드 |
| F-5 | mode 토글 (Q4 결과로 3 모드 시) | OFF → HARD → WARN 전환 |

### 5.5 안전성 (사이클 60/61 패턴 답습)

- HIGH 0 (자금 손실 영역 아님 — 매수 차단만)
- MEDIUM 3 (scanner 진입 / 60s 캐시 race / Settings UI 즉시 반영 race)
- LOW 12 (API 라우트 / Settings 카드 / DB 헬퍼)

**합계 청사진**: 백엔드 18 + integration 5 + contract 3 + 프론트 5 = **31 케이스** (사이클 60 A1 17 / 사이클 61 A2 20 보다 많음 — 백엔드 + 프론트 단일 사이클 특성)

---

## 6. 데이터 소스 분기 (Q2 결과 의존)

### 6.1 옵션별 sketch

| 옵션 | 데이터 소스 | KIS 호출 | 캐시 | team-leader 권고 |
|---|---|---|---|---|
| **(가) 당일 현재가** | `scanner.ticker_prices[ticker]["current_price"]` (WS 실시간) | 0 회 | WS 자동 | **권고** |
| **(나) 전일 종가 (stock_master)** | `stock_master.get(ticker).prdy_clpr` (24h TTL) | 0~1 회 (miss 시) | 24h | 자문 결과로 채택 가능 |
| **(다) 두 영역 fallback** | (나) → (가) | 0~1 회 | 24h + WS | 가장 안전 |

### 6.2 stock_master `prdy_clpr` 필드 현황 확인 필요

현재 `stock_master.raw` 가 KIS CTPF1002R 응답을 저장 — `prdy_clpr` 필드 포함 여부 사전 점검 의무. 미포함 시 옵션 (나) 채택 시 마이그레이션 또는 별도 KIS 호출 필요.

---

## 7. funnel 추적 (Q6 결과 의존)

### 7.1 옵션별 sketch

| 옵션 | funnel 단계 | 로그 | team-leader 권고 |
|---|---|---|---|
| **(가) 단계 추가** | `step_no=10` 신규 (가격 필터) | `[price_filter_excluded]` 별도 | 자문 결과 |
| **(나) 로그만** | 없음 | `[price_filter_skip]` (사이클 32 R4 `[universe_excluded]` 답습) | **권고 (1차)** — 단순화 + 사이클 41 funnel 진단 패턴 답습 시 추후 추가 가능 |
| **(다) 두 영역 병행** | (가) + (나) | 양쪽 | 가시성 최대, 코드 복잡 |

### 7.2 momentum/VB/LTV funnel hook 미적용 영향

사이클 41 funnel hook = BFB/VCP/donchian 만. momentum/VB/LTV 는 hook 없음. 가격 필터가 risk.on_tick 단일 진입점이라 funnel hook 추가 의무 없음 — 별도 `[price_filter_skip]` 로그만으로 충분.

---

## 8. 위험 평가 매트릭스

| 영역 | 위험 | 완화 |
|---|---|---|
| scanner 진입 / risk.on_tick 추가 분기 | MEDIUM | 회귀 가드 B 카테고리 4 케이스 |
| 60s 캐시 race | MEDIUM | 회귀 가드 D 카테고리 2 케이스 + invalidate 보장 |
| Settings UI 즉시 반영 race | MEDIUM | I-5 integration 케이스 |
| 보유/익일청산 매도 영향 0 (사이클 38) | LOW | E 카테고리 3 케이스 (정상 동작 검증) |
| 매수 신호 누락 (필터 차단 = 의도된 동작) | LOW | 기회비용만, 자금 손실 0 |
| DB 헬퍼 / API 라우트 / Settings 카드 | LOW | A/C/F 카테고리 13 케이스 |

→ HIGH 0 / MEDIUM 3 / LOW 12. **자금 손실 위험 없음** (매수 차단만).

---

## 9. 사이클 분할 (사용자 결정 답습)

- **단일 사이클** (백엔드 + 프론트 동시) — 사용자 결정
- 회귀 가드 31 케이스 (사이클 60 A1 17 / 사이클 61 A2 20 보다 많음 — 풀스택 특성)
- 예상 소요: tdd-engineer Red (1.5h) + backend-dev Green (2h) + frontend-dev Green (1h) + tester Verify (1h) + sync-docs (0.5h) = **~6h**

---

## 10. push 시점

- **NXT 애프터 18:00 이후** — 사용자 결정 (주말 의무 없음, 매수 차단만이라 안전)
- 매도/익일청산 영향 0 → 운영 시간대 push 도 회귀 위험 낮음 (사이클 38 답습)
- 18:00 이후 1~2h tester verify 동반

---

## 11. 예상 효과

### 11.1 작전주 / 동전주 차단

- VCP / BFB 매수 후보 중 5,000원 미만 종목 자동 제외 → 매매 안전성 강화
- 사이클 32 R4 `_evaluate_universe_guard` 의 거래량 기준 차단과 시너지 (가격 + 거래량 이중 가드)

### 11.2 초고가주 1주 폴백 차단

- LG에너지솔루션 / 삼성바이오로직스 등 50만원+ 종목의 1주 폴백 차단
- 전략 자금 분산 효과 (사이클 49 VCP 단독 30일 0건 매매 결함 진단 일부 회수)

### 11.3 사이클 49 VCP Pullback 결함과의 시너지 / 충돌 (자문 의제 Q7+)

- VCP 매매 기회 좁아질 가능성 — 자문에서 점검 의무 (트레이더 시각)

---

## 12. 절대 깨지 말 것 (체크리스트)

CLAUDE.md 절대 규칙 + 사이클 38 명문화:

- [x] 체결통보 구독 영역 무관
- [x] uvicorn 단일 워커 영향 0
- [x] WebSocket 4 중 안전망 영향 0 (risk.on_tick 추가 분기만, scheduler 영역 변경 0)
- [x] **`tradable_boards` 매수 진입 전용 (사이클 38)** — 본 카드 핵심 원칙. 매도/손절/Trailing/익일청산/15:20 강제청산 모두 필터 미적용
- [x] `_reset_daily_state` 동행 reset — emit cap 2 종 reset 의무 (사이클 56-D RiskManager.reset_daily_state 패턴)
- [x] KST 강제 (모든 시각)
- [x] logger 명시 binding (사이클 60 I1 패턴) — `logging.getLogger("src.engine.risk")` 또는 모듈 logger
- [x] 사이클 31 매수 가드 4 모드와 *충돌 없음* — 별도 키 (`price_filter_mode` vs `buy_block_mode`) 분리
- [x] `cash_usage_ratio` 정책 일관성 (즉시 vs 익일) — Q5 자문 결과 의존, 자금 비중 vs 매수 필터 분리 가능성

---

## 13. 작업 순서 (확정 — 사이클 60/61 답습)

1. **사이클 61 commit + push 완료 대기** (사용자 명시)
2. **사용자 사이클 62 발주 결정** (자문 발주 vs 직행)
3. **domain-expert 자문** (`_workspace/cycle62_price_filter_domain_response.md`) — 6 의제 + 자유 발의
4. **team-leader Q1~Q6 채택 + *TBD-Qn* 영역 확정**
5. **tdd-engineer Red 발주** (`_workspace/red/cycle62_price_filter.md`, 31 케이스)
6. **backend-dev + frontend-dev 동시 Green 발주** — 백엔드 DB 헬퍼 + risk.py + API 라우트 + 프론트 PriceFilterCard 동시 작업
7. **tester Verify** — 4 카테고리 분리 측정 (사이클 60 hotfix 답습) + flakiness 차단 + 보유/익일청산 안전성 검증 우선
8. **sync-docs** — CLAUDE.md 매수 가드 영역 + `src/engine/CLAUDE.md` risk.py 행 갱신 + `src/db/CLAUDE.md` system_config 키 추가 + HARNESS_CHANGELOG 사이클 62 행
9. **사용자 명시 commit + push 지시 대기** (NXT 애프터 18:00 이후)

---

## 14. 사이클 60/61 답습 패턴 매트릭스

| 항목 | 사이클 60 (A1) | 사이클 61 (A2) | 사이클 62 (가격 필터) |
|---|---|---|---|
| logger 명시 binding | ✅ `logging.getLogger("src.engine.scheduler")` | ✅ stale_manager.py 단일 logger 재사용 | risk.py 모듈 logger 사용 또는 명시 binding |
| 카테고리 분리 측정 (tester) | ✅ 4 카테고리 분리 (hotfix 답습) | ✅ 11 단계 분리 + flakiness 3회 반복 | 동일 패턴 답습 의무 |
| 5 상수 re-export (`is` 동일성) | ✅ 5종 | ✅ 5종 추가 (총 10종) | 해당 없음 (system_config 키만) |
| `sys.modules.get` 패턴 | 해당 없음 | ✅ scheduler 네임스페이스 우선 | 해당 없음 (단일 모듈 진입점) |
| AST 의존성 역전 정적 검증 | ✅ Q3-G6 | ✅ D-1 (lazy import 제거 검증) | 해당 없음 (단일 모듈) |
| flakiness 차단 (3회 반복) | ✅ tester | ✅ tester | 동일 패턴 답습 의무 |
| HIGH 케이스 우선 검증 | A1 = HIGH 1 (reset 동행) | A2 = HIGH 3 (C/I/J) | **HIGH 0** (자금 손실 영역 아님) |
| `_reset_daily_state` 동행 | ✅ `_stale_state.reset_daily()` | ✅ 자동 보존 (사이클 48 통합) | ✅ RiskManager.reset_daily_state() 위임 답습 (사이클 56-D) |
| 부분 UNIQUE 인덱스 (사이클 30) | 해당 없음 | 해당 없음 | 해당 없음 (system_config key UNIQUE 기존) |

---

## 15. 사이클 62 발주 시 권장 다음 단계

| # | 단계 | 에이전트 / 도구 | 산출물 |
|---|---|---|---|
| 1 | domain-expert 자문 | Task (domain-expert subagent) | `_workspace/cycle62_price_filter_domain_response.md` |
| 2 | team-leader 채택 + *TBD-Qn* 확정 | team-leader | 본 설계 카드 갱신 |
| 3 | tdd-engineer Red | Task (tdd-engineer) | `_workspace/red/cycle62_price_filter.md` (31 케이스) + 백엔드 + 프론트 pytest/vitest 본체 |
| 4 | backend-dev Green | Task (backend-dev) | `src/db/system_config.py` + `src/engine/risk.py` + `src/routes/strategies.py` 또는 신규 라우트 + 영향 인덱스 갱신 |
| 5 | frontend-dev Green | Task (frontend-dev) | `frontend/src/components/PriceFilterCard.tsx` + `frontend/src/pages/Settings.tsx` 통합 |
| 6 | tester Verify | Task (tester) | 4 카테고리 분리 측정 + flakiness 3회 + HIGH 영역 우선 (보유/익일청산 안전성) |
| 7 | sync-docs | Task (skill `sync-docs`) | CLAUDE.md 갱신 + HARNESS_CHANGELOG |
| 8 | commit + push | 사용자 명시 + git | NXT 애프터 18:00 이후 |

---

## 16. 안전 가드

- 본 sketch 작성은 운영 영향 0 (문서 산출물만)
- 사이클 62 실제 발주는 사용자 명시 지시 후 별도 진행
- *TBD-Q1~Q6* 영역은 자문 응답 후 변경 가능 — 본 sketch 는 1차 sketch (확정 아님)
- HIGH 0 등급이므로 사이클 60/61 만큼 회귀 가드 부담 적음, 단 보유/익일청산 안전성 (E 카테고리) 만큼은 사이클 38 답습 의무
