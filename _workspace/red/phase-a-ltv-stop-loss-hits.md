# Phase A — LTV `stop_loss_hits=0` 결함 진단 보고서 (2026-05-17)

> **본 문서는 진단만**입니다. fix 코드는 작성하지 않았고, 후속 fix 사이클 인계가 필요합니다.

## 1. 배경

5/15(금) 19:50 → 20:00 첫 4 전략 자문 발화 데이터 분석에서 LTV(`long_tail_volatility`) 만 다음과 같은 모순을 보였습니다:

- `metrics.stop_loss_hits = 0`
- `metrics.max_loss_pct = -7.554%`
- `metrics.avg_loss_pct = -3.797%`
- 현재 LTV 손절 임계치: `intraday_stop_loss = -2.5%`, `overnight_stop_loss = -2.0%`

→ 분석 대상 10영업일 동안 최대 -7.55% 손실이 발생했고, 평균 손실도 임계치(-2.5%)를 크게 초과하는데 손절 카운터는 0. 결함 의심.

## 2. 진단

### 2-1. `recommendation_metrics.compute_metrics()` 핵심 코드

`src/engine/recommendation_metrics.py:97-105`:

```python
stop_loss_rate = _safe_float(current_params.get("stop_loss_rate"))
stop_loss_hits = 0
if stop_loss_rate < 0 and loss_pcts:
    threshold = stop_loss_rate + 0.5  # 허용 오차 0.5%p
    for p in loss_pcts:
        if p <= threshold:
            stop_loss_hits += 1
```

여기서 `current_params.get("stop_loss_rate")` **단일 키 참조** 가 결함의 root cause.

### 2-2. 전략별 손절 파라미터 키 비교

| 전략 | 손절 키 | DEFAULT_PARAMS 위치 |
|------|---------|------|
| momentum | `stop_loss_rate = -7.5` | `src/engine/strategies/momentum.py:31` |
| volatility_breakout | `stop_loss_rate = -3.0` | `src/engine/strategies/volatility_breakout.py:34` |
| donchian_swing | `stop_loss_rate = -7.0` | `src/engine/strategies/donchian_swing.py:62` |
| bull_flag_breakout | `stop_loss_rate = -5.0` | `src/engine/strategies/bull_flag_breakout.py:83` |
| vcp_breakout | `stop_loss_rate = -7.0` | `src/engine/strategies/vcp_breakout.py:96` |
| **long_tail_volatility** | **`intraday_stop_loss = -3.0` / `overnight_stop_loss = -5.0`** | `src/engine/strategies/long_tail_volatility.py:50,53` |

→ **LTV 만** 손절을 두 키로 분리. `current_params.get("stop_loss_rate")` 가 `None` 반환 → `_safe_float(None) = 0.0` → `if stop_loss_rate < 0` 조건 False → 분기 진입 안 함 → `stop_loss_hits = 0` 고정.

### 2-3. `risk.py` / LTV `check_exit_signal` execution 경로 점검

`src/engine/strategies/long_tail_volatility.py:526-589` 분석 결과 **execution 경로는 정상**:

- 당일 모드(`_limit_up_reached` 미등록): `loss_rate <= self.config.params["intraday_stop_loss"]` 분기 정상 작동 → `Signal.STOP_LOSS`
- 익일 모드(상한가 도달 후): `loss_rate <= self.config.params["overnight_stop_loss"]` 분기 정상 작동
- 익일 청산 보류(`_next_day_clear_pending`) 중에도 overnight_stop_loss 만 손절 평가 유지

`risk.py::on_tick` 도 LTV 전용 분기 없이 `check_exit_signal` 결과만 평가 → 결함 무관.

→ execution 결함(분류 b) 아님.

### 2-4. 실 데이터 SQL 검증 (5/15 LTV)

운영 Supabase MCP 로 `trade_history` 조회:

```sql
select
  count(*) as total_completed_sells,
  count(*) filter (where (price*quantity)>0
                     and (profit_loss/(price*quantity))*100 <= -2.5) as below_intraday_stop_minus_2_5,
  count(*) filter (where (price*quantity)>0
                     and (profit_loss/(price*quantity))*100 <= -3.0) as below_intraday_stop_minus_3_0,
  min(case when (price*quantity)>0 then (profit_loss/(price*quantity))*100 end) as max_loss_pct
from trade_history
where strategy = 'long_tail_volatility'
  and trade_type = 'SELL'
  and status in ('COMPLETED','PARTIAL')
  and (timestamp at time zone 'Asia/Seoul')::date = '2026-05-15';
```

**결과**:

| 항목 | 값 |
|------|-----|
| total_completed_sells | 2 |
| below_intraday_stop_minus_2_5 | 1 |
| below_intraday_stop_minus_3_0 | 1 |
| below_overnight_stop_minus_5_0 | 0 |
| max_loss_pct (sell gross 기준) | -3.030% |
| total_realized_pnl | 22,300원 |

LTV 5/15 SELL 행 raw:
- `066570` LG전자: pnl_pct = +10.917% (익절)
- `064400` 에스에이엠지엠: pnl_pct = -3.030% (**손절 임계 -2.5% 도달**)

5/15 단일 영업일 기준 손절 1건이 명확함에도 자문 metrics 는 `stop_loss_hits = 0` 으로 저장.

### 2-5. 자문 저장 metrics 원본 확인

```sql
select metrics from parameter_recommendations
where target_date='2026-05-15' and strategy_id='long_tail_volatility';
```

```json
{
  "win_rate": 0.4615, "buy_count": 13, "win_count": 6, "loss_count": 7,
  "sell_count": 13, "avg_loss_pct": -3.797, "max_loss_pct": -7.554,
  "stop_loss_hits": 0,
  "analyzed_days": 10
}
```

10영업일 누적으로 평균 손실 -3.797% (임계치 -2.5% 초과) + 최대 손실 -7.554% 인데도 `stop_loss_hits=0`. 결함 행위 일관성 확인.

## 3. 결함 분류

**(a) metrics 계산 결함** — `recommendation_metrics.compute_metrics()` 의 `stop_loss_hits` 계산 로직이 LTV 의 분리 손절 키(`intraday_stop_loss` / `overnight_stop_loss`)를 인지하지 못함.

execution(분류 b) 결함 아님. LTV 의 실제 손절 로직(`check_exit_signal`)은 정상 작동.

## 4. 후속 fix 방향 권고 (별도 사이클 발의 권장)

### 옵션 1 — `compute_metrics()` 가 전략 ID 별 분기

`compute_metrics(trades, performance, current_params, strategy_id=None)` 시그니처 확장:

- `strategy_id == "long_tail_volatility"` 면:
  - `intraday_stop_loss` 기준 손절 + `overnight_stop_loss` 기준 손절을 각각 카운트
  - 또는 두 임계치 중 **더 큰 손실 임계치**(overnight, -5.0%) 단일 사용
- 그 외 전략은 기존 `stop_loss_rate` 그대로

**장점**: LTV 만 수정, 다른 전략 영향 없음.
**단점**: strategy_id 가 metrics 계산 책임에 결합됨.

### 옵션 2 — `_normalize_stop_loss_rate()` 헬퍼

`current_params` 입력 → "유효 손절률" 단일 값 반환:

```python
def _normalize_stop_loss_rate(current_params: dict) -> float:
    # 1순위: stop_loss_rate
    r = current_params.get("stop_loss_rate")
    if r is not None:
        return _safe_float(r)
    # 2순위: 분리 키 — 더 보수적인(작은 절대값) 임계치 사용
    intraday = current_params.get("intraday_stop_loss")
    overnight = current_params.get("overnight_stop_loss")
    candidates = [_safe_float(x) for x in (intraday, overnight) if x is not None]
    if not candidates:
        return 0.0
    # LTV 는 intraday(-3%)가 overnight(-5%)보다 절대값 작아 더 자주 도달
    # → 더 보수적인(절대값 큰) 쪽이 "확실히 손절 도달" 카운트로 적절
    return min(candidates)  # 더 음수 (절대값 큰) 쪽
```

**장점**: 시그니처 보존, 다른 전략 동작 영향 없음, 향후 다른 전략이 분리 키 도입 시에도 자동 동작.
**단점**: "유효 손절률" 정의가 LTV 의 2단계 모드(당일/익일) 의미와 1:1 매핑되지 않음. 보수적 카운트(`min` = 절대값 큰 쪽)로 underestimate 될 수 있음.

### 옵션 3 — `stop_loss_hits` 다중 카운트

`stop_loss_hits` 필드를 `{intraday: N, overnight: M}` dict 로 확장 + LTV 만 두 키 각각 카운트.

**장점**: 정보 손실 없음.
**단점**: 스키마 변경 + UI 영향 + LLM 프롬프트 변경. 다른 전략과 metrics 일관성 깨짐.

### 권장

**옵션 2(`_normalize_stop_loss_rate()` 헬퍼)** 우선. 사유:
1. 다른 전략 영향 없음 — 단일 함수 추가만
2. LTV 만 분리 키 사용 중이므로 옵션 1(strategy_id 분기)은 over-engineering
3. 옵션 3 은 UI/프롬프트 동시 변경 부담 큼
4. 보수적 카운트(절대값 큰 쪽) 의 underestimate 는 자문 LLM 입력으로 충분 — "손절 도달 1건 이상" 신호만 노출되면 LLM 이 손절률 조정 권고 가능

후속 fix 사이클은 TDD 사이클(`tdd-cycle` 스킬)로 진행 권장. Red 케이스:
- LTV `current_params` 에 `stop_loss_rate` 없고 `intraday_stop_loss=-2.5` 만 있을 때 손실 -3% 매도 1건 → `stop_loss_hits=1`
- 기존 momentum/VB/donchian/bull_flag/vcp 회귀 보존
- 5/15 LTV 실측 fixture 로 회귀(13건 SELL, 7건 loss, `stop_loss_hits >= 1`)

## 5. 본 사이클에서 패치 안 한 이유

Phase A 명세는 **진단만**. fix 는 별도 사이클 분리 결정 — root cause 명확하고 옵션 3 종이 트레이드오프 다르며, 자문 발화 1주 주기(주말 미발화)라 5/18 월요일 자문 전까지 fix 가능. 본 사이클(Phase B PARAM_RANGES 확장) 과 분리해 commit 단위를 작게 유지.

## 6. 영향도

- 다음 자문 사이클(5/18 월 20:00) 까지 fix 미적용 시 LTV `stop_loss_hits = 0` 유지 → LLM 이 "손절 도달 안 함" 으로 오인 → 손절률 완화(절대값 축소) 권고 가능성. 운영자 검수(Recommendations UI) 단계에서 차단 필요.
- 다른 5 전략은 영향 없음 (`stop_loss_rate` 단일 키 사용).
