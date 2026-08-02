# 사이클 F Red 로그 — TE/RR 전략 지표 (백엔드 F-B1~F-B9)

작성: tdd-engineer · 2026-08-02 · 상태: **RED 확정**
명세: `_workspace/red/_behaviors_cycleF_te_rr_20260802.md`
자문: `_workspace/domain_consult/cycle_te_expectancy_dashboard_20260802.md` (§266-276)

## 범위
서적 개념 TE(트레이딩 예지치=거래당 기대손익) + RR비율(손익비) 을 각 전략 최근 3개월
지표로 계산. **관찰 전용, 매매 8영역 diff 0**. 소스 = `get_trade_pairs`(진입가 기준·왕복·
미실현 분리). `recommendation_metrics.compute_metrics`(매도가 기준·PARTIAL 이중카운트) 재사용 금지.

## 신규 파일 (2)
1. `tests/unit/engine/test_cycleF_te_rr_metrics.py` — 순수 함수 `compute_te_rr` (21 케이스)
2. `tests/unit/routes/test_cycleF_te_endpoint.py` — `GET /api/strategies/te` (4 케이스)

## RED 실행 결과
```
python -m pytest tests/unit/engine/test_cycleF_te_rr_metrics.py \
                 tests/unit/routes/test_cycleF_te_endpoint.py -q
→ 19 failed, 4 errors
```
- 순수 함수 19건: `ModuleNotFoundError: No module named 'src.engine.te_metrics'` (의도)
- 엔드포인트 4건: `AttributeError: module 'src.routes.strategies' has no attribute 'invalidate_te_cache'` (의도 — 미구현 심볼)

## 안전 기준선 (GREEN 확인)
- `test_recommendation_metrics_smoke/board_stop_loss/ltv_stop_loss` → 21 passed (compute_metrics 계약 무변경)
- `test_cycleM5_strategies_auto_start` + `test_auto_apply_recommendations` → 11 passed (기존 strategies 라우트 무변경)

## 케이스 매트릭스

### compute_te_rr 순수 함수 (F-B1~F-B6, F-B9)
| 케이스 | 명세 | 검증 |
|--------|------|------|
| te_pct_uses_entry_based | F-B2 HIGH | 매수1만→매도1.1만 = +10.0%(진입가), ≠+9.09%(매도가) |
| te_pct_is_simple_average | F-B2 | TE%=profit_rate 단순평균 |
| te_krw_avg_and_realized_sum | F-B2 | te_krw_avg=profit_loss 평균 / realized_sum_krw=합 |
| decomposition_even_included | F-B3 | 보합 포함 win_rate 분모=N, TE=net/N, avg_win>0/avg_loss<0 |
| rr_ratio_and_required_rr | F-B4 | RR=avg_win/\|avg_loss\|, 필요RR=L/W, margin |
| te_rr_equivalence_boundary | F-B4 | TE>0⟺RR>필요RR (경계 TE=0⟺RR=필요RR, 보합 존재) |
| all_win_rr_none | F-B4 | 전승(avg_loss=0)→RR None + rr_available False + margin None |
| all_loss_required_rr_none | F-B4 | 전패(W=0)→필요RR None + RR None |
| rr_gate_min_wl_below_5 | F-B4 | min(W,L)=4→불가/=5→활성 경계 |
| single_trade_dominant_flag | F-B4 | 최대 승 pnl>총이익합×0.5→True / 균등→False |
| sample_tier_boundaries | F-B5 | N=19 insufficient/20 low/49 low/50 normal |
| verdict_gate_and_sign | F-B5 | N<20 undecided / TE>0 superior / <0 inferior / =0 flat |
| structure_tag_quadrants | F-B6 | robust/fragile/balanced + N<20·rr불가→None |
| window_filter_by_sell_date | F-B1 | sell D-30 포함 / D-154 제외 |
| window_includes_...buy_date | F-B1 | 매수 D-100·청산 D-30 포함 (청산일 기준) |
| open_pairs_excluded | F-B9 | status=='open' 제외 |
| partial_fill_folded | F-B9 | closed 행 개수로 N 정확 (PARTIAL 이중카운트 부재) |
| empty_population_safe_defaults | 엣지 | closed 0건→n=0·rr None·insufficient·undecided |
| strategy_id_passthrough | 엣지 | strategy_id 인자 반영 |

### 엔드포인트 (F-B7, F-B8)
| 케이스 | 명세 | 검증 |
|--------|------|------|
| returns_all_seven_strategies | F-B7 | 7 전략 asdict 리스트 + 17 필드 계약 |
| 5min_cache_skips_db | F-B7 | monotonic mock — TTL 내 재조회 0 / 만료 재조회 |
| months_maps_window_separates_key | F-B7 | months×30=window_days, months별 캐시 키 분리 |
| isolates_per_strategy_exception | F-B8 | 1 전략 실패→빈 디폴트, 나머지 진행 (전략 누락 금지) |

## backend-dev 인계 인터페이스 (확정)

### `src/engine/te_metrics.py` (신규)
```python
from dataclasses import dataclass

@dataclass
class TeRrMetrics:
    strategy_id: str
    n: int
    win: int
    loss: int
    even: int
    win_rate: float          # W / N (보합 포함 분모)
    avg_win_pct: float | None   # 승 profit_rate 평균 (양수, 승 0건 None)
    avg_loss_pct: float | None  # 패 profit_rate 평균 (음수, 패 0건 None)
    te_pct: float            # 모집단 profit_rate 단순평균 (= net/N)
    te_krw_avg: float        # profit_loss 평균
    realized_sum_krw: float  # profit_loss 합
    rr: float | None         # avg_win/|avg_loss|; 전승 or min(W,L)<5 → None
    required_rr: float | None  # L/W; W=0 → None
    rr_margin: float | None  # rr - required_rr; rr None → None
    rr_available: bool       # min(W,L)>=5 AND avg_loss!=0
    sample_tier: str         # 'insufficient'(N<20) / 'low'(20<=N<50) / 'normal'(N>=50)
    verdict: str             # 'undecided'(N<20) / 'superior' / 'inferior' / 'flat'
    structure_tag: str | None  # 'robust'/'fragile'/'balanced'; N<20 or not rr_available → None
    single_trade_dominant: bool  # max(승 profit_loss) > sum(승 profit_loss)*0.5

def compute_te_rr(
    pairs: list[dict], *, now: datetime, window_days: int = 90, strategy_id: str = "",
) -> TeRrMetrics: ...
```
계산 규칙 요약:
- **모집단** = pairs 中 `status=='closed'` ∧ `date.fromisoformat(sell_date) >= (now - timedelta(days=window_days)).date()` (경계 inclusive, open 제외).
- **분류**: profit_rate>0 win / <0 loss / ==0 even. win_rate=W/N.
- **te_pct** = mean(profit_rate) (= 승/패/보합 전체 단순평균, net/N 항등).
- **rr** = avg_win_pct / abs(avg_loss_pct). 전승(avg_loss_pct 없음) 또는 `min(W,L)<5` → None.
- **required_rr** = L/W. W=0 → None.
- **structure_tag** (N>=20 ∧ rr_available): win_rate<0.5 ∧ rr>=1.0 → robust / win_rate>=0.5 ∧ rr<1.0 → fragile / 그 외 balanced.
- **verdict**: N<20 → undecided, else te_pct>0 superior / <0 inferior / ==0 flat.
- **동치 보장**: te_pct 와 rr/required_rr 는 같은 profit_rate 값에서 파생 → TE>0 ⟺ RR>필요RR 자동 성립 (테스트 강제).

### `src/routes/strategies.py` (엔드포인트 + 캐시)
```python
import time
from src.db.trade_history import get_trade_pairs
from src.engine.te_metrics import compute_te_rr

_TE_CACHE_TTL = 300.0
_te_cache: dict[int, tuple[float, list[dict]]] = {}   # months -> (monotonic_expiry, data)

def invalidate_te_cache() -> None: ...   # 테스트/토글용 (convention: invalidate_*)

@router.get("/te", response_model=ApiResponse)
async def get_strategies_te(months: int = 3) -> ApiResponse:
    # 1) 캐시 hit (time.monotonic() < expiry) → 재조회 0
    # 2) miss: registry.all() 순회 → 각 s.strategy_id 로 get_trade_pairs(strategy) →
    #    compute_te_rr(pairs, now=datetime.now(KST), window_days=months*30, strategy_id=s.strategy_id)
    #    전략별 try/except 격리(실패 → 빈 디폴트 compute_te_rr([], ...))
    # 3) data = [asdict(m) for m in metrics]; 캐시 저장; ApiResponse(data=data)
```
계약 주의:
- **`import time` + `time.monotonic()` 필수** (테스트가 `st.time.monotonic` 패치 — kis_quote_accounts 캐시 패턴 답습).
- **months → window_days = months*30** (3→90, 6→180). 캐시 키 = months.
- `data` 는 **list[dict] (asdict)** — `d["strategy_id"]` 접근 계약.
- 라우트 순서: 기존 `/api/strategies` (`""`) 옆 신규 `/te`. `/api/strategies` 60s 폴링 미변경.
- `get_trade_pairs`/`compute_te_rr` 는 **모듈 레벨 심볼** 로 import (테스트가 `st.get_trade_pairs`/`st.compute_te_rr` 패치).

## 매매 안전성 diff 0 의무
변경 = `te_metrics.py`(신규) + `routes/strategies.py`(엔드포인트) + 프론트(별도).
`risk.py / order_engine.py / realtime/ / auth/ / api/order.py` + scheduler 매매 hot path diff 0.
get_trade_pairs read-only.
