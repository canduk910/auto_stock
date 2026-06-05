# 사이클 62 가격 필터 — 설계 카드 (자문 결과 확정 적용 — v2)

> **작성**: team-leader (2026-06-05 13:35 KST 초안 → **14:25 KST 자문 결과 확정 갱신 v2**)
> **사용자 결정 (사이클 60 사후 확정)**:
> - 필터 의도 = 양쪽 밴드 `[min, max]` (저가 + 초고가 동시 차단)
> - 적용 시점 = scanner 조건검색 직후 (전 전략 공통) → *재확정*: **`risk.on_tick` 단일 진입점** (사이클 31 `[risk_silent_skip]` 패턴 답습)
> - 사이클 분할 = 백엔드 + 프론트 단일 사이클
> - 위험 등급 = MEDIUM (매수 차단만 — 자금 손실 0, 기회비용만)
> - push 시점 = NXT 애프터 (주말 의무 없음)
> **선행 자문**: `_workspace/cycle62_price_filter_domain_consult.md` (Q1~Q6 + 자유 발의)
> **자문 응답**: `_workspace/cycle62_price_filter_domain_response.md` — **전부 채택 (옵션 A)**
> **CLAUDE.md 절대 규칙 충돌**: 없음 (매수 진입 전용, `tradable_boards` 사이클 38 명문화 답습)
> **회귀 가드 합계**: 31 → **38 케이스** (자문 +7)

---

## 0. 자문 결과 확정 사항 (7 영역 — 모두 옵션 A 채택)

| 의제 | 확정 내용 | 비고 |
|---|---|---|
| **Q1** 임계 디폴트 | DB 디폴트 `0/0` (비활성) + UI 권장값 툴팁 **저 5,000원 / 고 1,000,000원** + 슬라이더 max **0~2,000,000원** / step **50,000원** | 운영자가 슬라이더 조작 시점에 권장값 가시화. 디폴트 비활성으로 운영 시작 안전성 |
| **Q2** 비교 가격 | **`prev_close` 우선 + `current_price` fallback** (갭상승/하락 시점 결함 회피) — `scanner.ticker_prev_close: dict[str, int]` (L36) 활용 | 미확보 시 graceful 통과 (필터 비활성, 매수 허용) |
| **Q3** 매도 영향 | 매수만 필터 확정 + **시장가 거부 5호가 폴백 시 가격 필터 재평가 금지 회귀 가드 추가** | `order_engine.py` L411/664 의 `step_up(5)`/`step_down(5)` 폴백은 *체결 가격 변경* — 필터 재평가하면 매도 차단 위험 |
| **Q4** 운영 모드 | **3 모드 HARD / WARN / OFF + 디폴트 OFF** | HARD 단일 반박 — WARN 1주 운영 후 HARD 전환 (시장 신뢰 형성 단계적 도입) |
| **Q5** 반영 시점 | **즉시 + 60s TTL 캐시 + 5분 grace 금지** | 사고 대응 지연 차단 (60s 이상 grace 가 KIS 작전주 차단 지연 발생 위험) |
| **Q6** funnel | 별도 `[price_filter_skip]` 로그 + **`_settle()` 직전 `[price_filter_daily_summary]` 1행 추가** | 매일 정산 직전 일일 집계 (block/warn 카운트 + reason 분포). `strategy_funnel_snapshots` 단계 추가는 보류 |
| **Q7** 거래대금 (자유 발의) | **사이클 63 별개 카드 발의** | 본 사이클 범위 밖 |
| **Q11** VCP 시너지 (자유 발의) | Q2 fallback 채택으로 자동 시너지 | 운영 후 변수 분리 모니터링 (별도 사이클 미발의) |

---

## 1. DB 스키마 (확정)

### 1.1 `system_config` 신규 키 3 종 (Q1 + Q4 확정)

```python
# src/db/system_config.py (확장)

_PRICE_FILTER_MIN_KEY = "price_filter_min"   # 정수 (원). 0 = 비활성
_PRICE_FILTER_MAX_KEY = "price_filter_max"   # 정수 (원). 0 = 비활성 (무한대 의미)
_PRICE_FILTER_MODE_KEY = "price_filter_mode" # "HARD" / "WARN" / "OFF" 3 모드 (Q4 확정)

# Q1 디폴트 — 비활성 (운영 시작 안전성 우선)
_PRICE_FILTER_MIN_DEFAULT = 0
_PRICE_FILTER_MAX_DEFAULT = 0
_PRICE_FILTER_MODE_DEFAULT = "OFF"           # Q4 — 사이클 31 buy_block_mode 답습 (OFF 디폴트)

# Q1 슬라이더 범위
_PRICE_FILTER_MIN_BOUND = (0, 50_000)        # 0 ~ 5만원
_PRICE_FILTER_MAX_BOUND = (0, 2_000_000)     # 0 ~ 200만원
_PRICE_FILTER_MIN_STEP = 1_000                # 1,000원 단위 (저가주 정밀 조정)
_PRICE_FILTER_MAX_STEP = 50_000               # 50,000원 단위 (고가주 거친 조정 — Q1 사용자 확정)

# Q1 권장값 (UI 툴팁만 — DB 디폴트 아님)
_PRICE_FILTER_MIN_RECOMMENDED = 5_000        # 작전주 / 동전주 회피 통상 임계
_PRICE_FILTER_MAX_RECOMMENDED = 1_000_000    # 1주 폴백 자금 비중 한계

# Q4 모드
_PRICE_FILTER_VALID_MODES = ("HARD", "WARN", "OFF")
```

### 1.2 헬퍼 시그니처 (Q4 3 모드 + Q5 즉시 반영)

```python
from pydantic import BaseModel

class PriceFilter(BaseModel):
    """가격 필터 설정 (사이클 62, 2026-06-05)."""
    min_price: int  # 0 = 비활성
    max_price: int  # 0 = 비활성 (무한대 의미)
    mode: str       # "HARD" / "WARN" / "OFF"

    @property
    def is_active(self) -> bool:
        """OFF 또는 임계값 0/0 이면 비활성. HARD/WARN 일 때만 활성."""
        if self.mode == "OFF":
            return False
        return self.min_price > 0 or self.max_price > 0


async def get_price_filter() -> PriceFilter:
    """현재 가격 필터 설정 조회. 키 부재 시 디폴트 PriceFilter(0, 0, "OFF") 반환.

    3 키 병합 + Pydantic 반환 (buy_block_mode 패턴 답습).
    """
    ...

async def set_price_filter(
    *,
    min_price: int | None = None,
    max_price: int | None = None,
    mode: str | None = None,
) -> None:
    """부분 갱신 — None 인 키는 보존.

    - min_price 범위 외 ValueError ([0, 50_000])
    - max_price 범위 외 ValueError ([0, 2_000_000])
    - mode 가 ("HARD", "WARN", "OFF") 외 ValueError

    호출 직후 라우트가 `risk_manager.invalidate_price_filter_cache()` 호출 의무 (Q5 즉시 반영).
    """
    ...
```

### 1.3 마이그레이션

**불필요** — `system_config` 테이블은 기존 (key + value JSONB 구조). 키만 추가.

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

## 2. 적용 위치 (`src/engine/risk.py` — 단일 진입점 확정)

### 2.1 진입점 (확정)

**`risk.on_tick` 단일 진입점** (사이클 31 `[risk_silent_skip]` 패턴 답습):
- `check_exit_signal` 분기 *전* 진입 보존 (사이클 38 명문화 — `tradable_boards` 매수 진입 전용)
- 6 전략 자동 적용 (단일 진실의 원천)
- scanner 단계 무영향 (분리)
- 매도/익일청산/손절/15:20 강제청산/Trailing 영향 0

### 2.2 비교 가격 데이터 소스 (Q2 확정 — `prev_close` 우선 + `current_price` fallback)

| 우선순위 | 데이터 소스 | 미확보 시 |
|---|---|---|
| **1순위** | `scanner.ticker_prev_close[ticker]` (L36 `dict[str, int]`) | 2순위로 fallback |
| **2순위** | `price_data["current_price"]` (WS 실시간) | graceful 통과 (필터 비활성) |

**근거 (자문 Q2)**:
- `prev_close` 우선 — 갭상승/하락 시점 결함 회피 (작전주가 갭상승으로 7,000원 → 12,000원 되어도 전일 종가 4,000원 기준 차단 유지)
- `current_price` fallback — 신규 상장 또는 WS 늦은 종목 graceful 보호
- KIS 별도 호출 0 회 (Rate Limit 보호)

### 2.3 필터 적용 코드 sketch (확정)

```python
# src/engine/risk.py (확장 — risk_silent_skip 패턴 답습)

async def on_tick(ticker, price_data):
    ...
    for strategy in self.registry.enabled():
        ...
        # 기존 가드 — 보드 / 매수 가드 / 중복 / 자금 사전 가드
        ...

        # 사이클 62 (2026-06-05) — 가격 필터 가드 (매수 진입 전용)
        # **사이클 38 명문화**: check_exit_signal 분기 *전* 진입 — 매도 영향 0
        price_filter = await self._get_price_filter_cached()  # 60s TTL
        if price_filter.is_active:
            # Q2 확정 — prev_close 우선 + current_price fallback
            from src.engine.scanner import ticker_prev_close as _prev_close_dict
            ref_price = _prev_close_dict.get(ticker, 0)
            if ref_price <= 0:
                ref_price = int(price_data.get("current_price", 0))
            if ref_price > 0:  # 미확보 (0/None) 시 graceful 통과
                below_min = price_filter.min_price > 0 and ref_price < price_filter.min_price
                above_max = price_filter.max_price > 0 and ref_price > price_filter.max_price
                if below_min or above_max:
                    reason = "below_min" if below_min else "above_max"
                    if price_filter.mode == "HARD":
                        await self._emit_price_filter_skip(
                            ticker, strategy.id, reason, ref_price, price_filter
                        )
                        continue  # 매수 신호 평가 skip
                    elif price_filter.mode == "WARN":
                        await self._emit_price_filter_warn(
                            ticker, strategy.id, reason, ref_price, price_filter
                        )
                        # 매수 허용 (WARN 모드 — 트레이더 인지만)
                    # OFF 는 if price_filter.is_active 에서 차단됨

        # 기존 check_buy_signal 로 진행
        signal = strategy.check_buy_signal(ticker, price_data)
        ...
```

### 2.4 Q3 시장가 폴백 회귀 가드 (HIGH 부재 영역의 안전 가드)

**자문 Q3 추가 가드 의무**: `order_engine.py` 의 시장가 거부 5호가 폴백 (`step_up(5)`/`step_down(5)`) 시 가격 필터 재평가 금지.

**근거**:
- 시장가 거부 → `step_up(current_price, 5)` 폴백 → 호가 5단계 상승 가격으로 지정가 재시도
- 이 폴백은 *체결 가격 변경* (운영 가드) — 가격 필터를 재평가하면 *매도 폴백 차단* 위험 (사이클 38 명문화 위반)
- `risk.on_tick` 의 가격 필터는 *매수 진입 전용*. order_engine 의 매수/매도 폴백은 별도 흐름 — 필터 재평가 호출 금지

**구현 가이드**:
- `order_engine.py` L411 (매수 폴백) + L664 (매도 폴백) 모두 `risk_manager._get_price_filter_cached()` 호출 *금지*
- 회귀 가드: `tests/unit/engine/test_cycle62_price_filter_market_fallback_no_recheck.py` 신규 (Q3 +1 케이스)
- `order_engine` 폴백 흐름에 `risk_manager` 참조 자체가 없어야 — `ast` 정적 검증 가드 또는 mock spy

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

## 5. 회귀 가드 38 케이스 (team-leader 31 + 자문 +7 확정)

### 5.1 백엔드 unit (25 케이스)

| 카테고리 | 케이스 | 영역 |
|---|---|---|
| A `system_config` 헬퍼 | 5 | get 디폴트(OFF) / set 부분 갱신 / min 범위 외 ValueError / max 범위 외 ValueError / mode 외 ValueError |
| B `risk.py` 필터 적용 (HARD) | 4 | min 차단 (HARD) / max 차단 (HARD) / 임계 0/0 통과 / mode=OFF 통과 |
| C emit cap | 2 | 같은 (ticker, strategy) 1회/일 emit / `reset_daily_state` 동행 reset (cap 2 종) |
| D 60s TTL 캐시 | 2 | hit / 만료 후 재조회 + invalidate 즉시 무효화 |
| **E 매도 영향 0 검증 (사이클 38 답습) +1** | **4** | (1) 보유 손절 정상 / (2) 익일청산 NXT 시장가 정상 / (3) 트레일링 정상 / **(4) Q3 시장가 거부 5호가 폴백 시 필터 재평가 금지 — `order_engine` 폴백 흐름에 `risk_manager._get_price_filter_cached()` 호출 0건 (mock spy 또는 ast 정적 검증)** |
| **F 미확보 graceful (Q2 fallback) +3** | **5** | (1) `ticker_prev_close` miss + `current_price` 사용 (fallback 동작) / (2) `prev_close` 0 + `current_price` 0 → graceful 통과 / (3) `prev_close` 5000 + `current_price` 12000 (갭상승) → `prev_close` 우선 기준 차단 / (4) 신규 상장 (양쪽 0) → 필터 skip + 매수 허용 / (5) `prev_close` 활용 시 `current_price` 변동 영향 0 (사이클 49 VCP 시너지 회귀) |
| **G Q4 WARN 모드 +2** | **2** | (1) WARN 모드 매수 허용 + `[price_filter_warn]` WARNING 로그 emit / (2) WARN 모드 emit cap 별도 적용 (skip cap 과 분리) |
| **H Q6 일일 집계 +1** | **1** | `_settle()` 직전 `[price_filter_daily_summary] block=X warn=Y reasons={below_min: N, above_max: M}` 1행 emit |
| **합계 unit** | **25** | (기존 18 + 자문 +7) |

### 5.2 백엔드 integration (5 케이스)

| # | 시나리오 | 검증 |
|---|---|---|
| I-1 | risk.on_tick 매수 차단 E2E | momentum 등락률 15% + 가격 필터 HARD 차단 → 매수 skip + `[price_filter_skip]` 로그 |
| I-2 | Settings PUT → 60s 캐시 invalidate → 다음 on_tick 즉시 반영 | E2E (Q5 즉시 반영, 5분 grace 금지 검증) |
| I-3 | 보유 손절 정상 발화 (필터 활성 HARD + `current_price < min`) | 보유 종목 1주 매수 → 가격 폭락 → 손절 발화 (E-1 보강) |
| I-4 | 익일청산 정상 (필터 활성 HARD + `current_price > max`) | `_pending_next_day_clear` → NXT 시장가 청산 (E-2 보강) |
| I-5 | mode 변경 race (HARD → OFF 즉시 전환) | invalidate 후 1초 이내 OFF 반영 — 5분 grace 금지 |

### 5.3 백엔드 contract (3 케이스)

| # | 시나리오 | 검증 |
|---|---|---|
| C-1 | `GET /api/system/price-filter` 200 + PriceFilter 응답 | Pydantic 스키마 검증 (min/max/mode 3 필드) |
| C-2 | `PUT /api/system/price-filter` 200 + 부분 갱신 | 일부 키만 전달 시 나머지 보존 + 200 응답 |
| C-3 | `PUT` 범위 외 → 400 + error message | `min_price=-1` / `max_price=3_000_000` / `mode="INVALID"` 모두 400 |

### 5.4 프론트 vitest (5 케이스)

| # | 시나리오 | 검증 |
|---|---|---|
| F-1 | `PriceFilterCard` 초기 fetch + 렌더 | MSW mock `/api/system/price-filter` + 슬라이더 + 토글 + 권장값 툴팁 (저 5,000 / 고 1,000,000) 렌더 |
| F-2 | 슬라이더 조작 → state 갱신 | min step=1,000 / max step=50,000 변경 확인 |
| F-3 | 저장 버튼 → PUT 호출 + toast (즉시 반영) | MSW + render — "가격 필터가 즉시 반영되었습니다" toast |
| F-4 | 범위 외 입력 → clamp 또는 비활성화 | min 50,001 / max 2,000,001 입력 시 UI 가드 |
| F-5 | mode 3 토글 (HARD / WARN / OFF) | 토글 전환 검증 |

### 5.5 안전성 분포

- **HIGH 0** (자금 손실 영역 아님 — 매수 차단만)
- **MEDIUM 3** — scanner 진입 / 60s 캐시 race / Settings UI 즉시 반영 race
- **LOW 35** — API 라우트 / Settings 카드 / DB 헬퍼 / WARN 모드 / 일일 집계 / Q2 fallback / Q3 폴백 가드

**합계**: 백엔드 unit 25 + integration 5 + contract 3 + 프론트 5 = **38 케이스** (team-leader 31 + 자문 +7)

### 5.6 카테고리 분리 파일 12~15 권고 (사이클 60/61 답습)

tdd-engineer 가 본 명세 기반 파일 분리:

| # | 파일 | 카테고리 | 케이스 |
|---|---|---|---|
| 1 | `tests/unit/db/test_cycle62_price_filter_config.py` | A | 5 |
| 2 | `tests/unit/engine/test_cycle62_price_filter_hard.py` | B | 4 |
| 3 | `tests/unit/engine/test_cycle62_price_filter_emit_cap.py` | C | 2 |
| 4 | `tests/unit/engine/test_cycle62_price_filter_cache_ttl.py` | D | 2 |
| 5 | `tests/unit/engine/test_cycle62_price_filter_sell_safety.py` | E-1,2,3 | 3 |
| 6 | `tests/unit/engine/test_cycle62_price_filter_market_fallback_no_recheck.py` | E-4 (Q3) | 1 |
| 7 | `tests/unit/engine/test_cycle62_price_filter_fallback_prev_close.py` | F | 5 |
| 8 | `tests/unit/engine/test_cycle62_price_filter_warn_mode.py` | G | 2 |
| 9 | `tests/unit/engine/test_cycle62_price_filter_daily_summary.py` | H | 1 |
| 10 | `tests/integration/test_cycle62_price_filter_e2e.py` | I-1~I-5 | 5 |
| 11 | `tests/contract/test_cycle62_price_filter_routes.py` | C-1~C-3 | 3 |
| 12 | `frontend/src/components/__tests__/PriceFilterCard.test.tsx` | F-1~F-5 | 5 |
| **합계** | | | **38 (12 파일)** |

---

## 6. 데이터 소스 (Q2 확정 — `prev_close` 우선 + `current_price` fallback)

### 6.1 확정 데이터 소스 분기

```python
# src/engine/risk.py (확정 흐름)
from src.engine.scanner import ticker_prev_close

ref_price = ticker_prev_close.get(ticker, 0)
if ref_price <= 0:
    ref_price = int(price_data.get("current_price", 0))
if ref_price <= 0:
    # 양쪽 모두 미확보 — graceful 통과 (필터 비활성, 매수 허용)
    pass  # 필터 평가 자체 skip
else:
    # 필터 평가
    ...
```

### 6.2 `scanner.ticker_prev_close` 활용 근거

- L36 `ticker_prev_close: dict[str, int] = {}` — WS `_handle_tick` 가 KIS `H0STCNT0/H0NXCNT0` 응답에서 추출 (실시간 갱신)
- `_reset_daily_state` 의 scanner clear 동행 (L3580 `ticker_prev_close.clear()`) — 매일 _boot 부터 신선
- KIS 별도 호출 0 회 (Rate Limit 보호)
- `stock_master.prdy_clpr` 미사용 (필드 존재 확인 의무 회피)

### 6.3 갭상승 시점 결함 회피 시너지

| 시나리오 | `prev_close` 우선 동작 | `current_price` 단독 동작 (배제) |
|---|---|---|
| 작전주 갭상승 (전일 4,000 → 당일 12,000) | `prev_close=4,000 < min=5,000` 차단 (의도 부합) | `current_price=12,000 > min` 통과 (작전주 매수 위험) |
| VCP Pullback 회복 (전일 8,000 → 당일 7,500) | `prev_close=8,000` 기준 평가 (안정적) | `current_price=7,500` 기준 평가 (당일 변동성 노출) |
| 신규 상장 (전일 0 → 당일 5,000) | fallback `current_price=5,000` | 동일 |

→ Q11 자문 의제 답습: **VCP Pullback 회복 종목 차단 위험 감소** (사이클 49 VCP 30일 0건 매매 결함과 시너지)

---

## 7. funnel 추적 (Q6 확정)

### 7.1 확정 결정 (Q6 자문)

| 영역 | 확정 |
|---|---|
| funnel 단계 (`strategy_funnel_snapshots`) | **미추가** (`step_no` 충돌 회피 + 단순화) |
| 매 차단 로그 | `[price_filter_skip] ticker=... strategy=... reason=... ref_price=... min=... max=... mode=...` |
| 매 WARN 로그 | `[price_filter_warn] ticker=... strategy=... reason=... ref_price=... min=... max=... mode=WARN` |
| **일일 집계 (신규, 사이클 41 funnel 진단 패턴 답습)** | `_settle()` 직전 `[price_filter_daily_summary] block_count=X warn_count=Y reasons={below_min: N, above_max: M}` 1행 |

### 7.2 emit cap 정책 보존

- `[price_filter_skip]` / `[price_filter_warn]`: 1회/(ticker, strategy)/일 (사이클 31 `DailyEmitCap` 답습)
- `[price_filter_daily_summary]`: 1회/일 (`_settle()` 진입 직전)

### 7.3 일일 집계 구현 위치

`src/engine/risk.py` 의 `RiskManager` 에 카운터 필드 추가:
```python
@dataclass
class RiskManager:
    ...
    _price_filter_skip_count_today: int = 0
    _price_filter_warn_count_today: int = 0
    _price_filter_skip_reasons_today: dict[str, int] = field(default_factory=dict)  # {"below_min": 3, "above_max": 2}

    async def emit_daily_summary(self) -> None:
        """`_settle()` 진입 직전 호출. emit cap 1회/일."""
        msg = (
            f"[price_filter_daily_summary] block_count={self._price_filter_skip_count_today} "
            f"warn_count={self._price_filter_warn_count_today} "
            f"reasons={dict(self._price_filter_skip_reasons_today)}"
        )
        logger.info(msg)
        try:
            await write_log("INFO", msg)
        except Exception:
            logger.debug("[price_filter_daily_summary] write_log 실패", exc_info=True)

    def reset_daily_state(self) -> None:
        ...
        # 사이클 62 — 일일 카운터 reset
        self._price_filter_skip_count_today = 0
        self._price_filter_warn_count_today = 0
        self._price_filter_skip_reasons_today.clear()
        # 사이클 56-D 답습 (emit cap)
        self._price_filter_skip_logged_today.reset_daily()
        self._price_filter_warn_logged_today.reset_daily()
```

호출 위치: `scheduler._settle()` 진입 직후, `_reset_daily_state` 이전 (집계가 reset 보다 먼저).

---

## 8. 위험 평가 매트릭스 (확정)

| 영역 | 위험 | 완화 |
|---|---|---|
| risk.on_tick 추가 분기 (매수 진입 전 단일 게이트) | MEDIUM | 회귀 가드 B 4 케이스 (HARD 차단/통과 검증) |
| 60s TTL 캐시 race | MEDIUM | 회귀 가드 D 2 케이스 + invalidate 보장 + 5분 grace 금지 (Q5) |
| Settings UI 즉시 반영 race | MEDIUM | I-2/I-5 integration 2 케이스 |
| 보유/익일청산 매도 영향 0 (사이클 38) | LOW | E 카테고리 4 케이스 (E-1,2,3 + Q3 E-4 시장가 폴백 가드) |
| Q2 fallback 동작 (`prev_close` 우선) | LOW | F 카테고리 5 케이스 (갭상승 / 미확보 / 신규상장 시너지) |
| Q3 시장가 폴백 시 필터 재평가 (HIGH 가드) | LOW | E-4 단독 케이스 — `ast` 정적 검증 또는 mock spy |
| Q4 WARN 모드 emit | LOW | G 카테고리 2 케이스 (WARN 분기 + cap 분리) |
| Q6 일일 집계 (`_settle` 진입 직전) | LOW | H 카테고리 1 케이스 |
| DB 헬퍼 / API 라우트 / Settings 카드 | LOW | A/C/F 카테고리 13 케이스 |

→ HIGH 0 / **MEDIUM 3** / **LOW 35**. **자금 손실 위험 없음** (매수 차단만).

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

## 12. 절대 깨지 말 것 (체크리스트 — 확정)

CLAUDE.md 절대 규칙 + 사이클 38 명문화 + 자문 추가 가드:

- [x] 체결통보 구독 영역 무관
- [x] uvicorn 단일 워커 영향 0
- [x] WebSocket 4 중 안전망 영향 0 (risk.on_tick 추가 분기만, scheduler 영역 변경 0)
- [x] **`tradable_boards` 매수 진입 전용 (사이클 38)** — 본 카드 핵심 원칙. 매도/손절/Trailing/익일청산/15:20 강제청산 모두 필터 미적용
- [x] **Q3 시장가 거부 5호가 폴백 시 필터 재평가 금지** — `order_engine.py` L411 (매수 폴백 `step_up(5)`) + L664 (매도 폴백 `step_down(5)`) 모두 `risk_manager._get_price_filter_cached()` 호출 0건 (E-4 회귀 가드)
- [x] `_reset_daily_state` 동행 reset — emit cap 2 종 + 일일 집계 카운터 3 필드 reset 의무 (사이클 56-D RiskManager.reset_daily_state 패턴)
- [x] `_settle()` 진입 직전 `emit_daily_summary()` 호출 — 집계가 reset 보다 먼저
- [x] KST 강제 (모든 시각)
- [x] logger 명시 binding (사이클 60 I1 패턴) — `logging.getLogger("src.engine.risk")` 또는 모듈 logger
- [x] 사이클 31 매수 가드 4 모드와 *충돌 없음* — 별도 키 (`price_filter_mode` vs `buy_block_mode`) 분리
- [x] **Q5 즉시 반영 + 5분 grace 금지** — `cash_usage_ratio` 익일 정책과 *분리 가능* (자금 비중 vs 매수 필터 본질 차이)
- [x] **Q2 fallback 동작 영구 보존** — `prev_close` 우선 / `current_price` fallback / 양쪽 미확보 graceful 통과 (3 단계 분기)
- [x] **Q4 WARN 모드는 매수 허용 + 로그만** — 매수 차단 효과는 HARD 모드 단독, WARN 은 시장 신뢰 형성 단계용
- [x] **Q1 디폴트 OFF** — 운영자 명시 활성화 의무 (운영 시작 안전성)

---

## 13. 작업 순서 (확정 — 사이클 60/61 답습)

1. ✅ **사이클 61 commit + push 완료** (사용자 명시 — 사이클 62 sketch 동행 commit)
2. ✅ **사용자 사이클 62 발주 결정 = 옵션 A 채택 (자문 결과 전부 적용)**
3. ✅ **domain-expert 자문 응답** (`_workspace/cycle62_price_filter_domain_response.md`) 수신
4. ✅ **team-leader 채택 + 7 영역 확정** (본 카드 v2 갱신)
5. **tdd-engineer Red 발주 (다음 단계)** — `_workspace/red/cycle62_price_filter.md` 작성 + 38 케이스 본체 작성
6. **backend-dev + frontend-dev 동시 Green 발주** — 백엔드 (DB 헬퍼 + risk.py 3 모드 + Q2 fallback + 라우트 + 60s TTL + 일일 집계) + 프론트 (PriceFilterCard 슬라이더 2 + mode 토글 + 권장값 툴팁) 동시 작업
7. **tester Verify** — 4 카테고리 분리 측정 (사이클 60/61 답습) + flakiness 3 회 반복 + **매도 영향 0 (E 카테고리 4 케이스) 우선 검증** + 매수 진입 race 검증
8. **sync-docs** — CLAUDE.md 매수 가드 영역 + `src/engine/CLAUDE.md` risk.py 본문 갱신 + `src/db/CLAUDE.md` system_config 3 키 + `frontend/CLAUDE.md` PriceFilterCard + HARNESS_CHANGELOG 사이클 62 행
9. **사용자 명시 commit + push 지시 대기** (NXT 애프터 18:00 이후 — 현재 14:25 KST → 3h 35min 여유)
10. **사이클 63 = 거래대금 동행 필터 (Q7 인계)** — `_workspace/refactor/2026-06-04_review.md` 카드 #13 발의

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
