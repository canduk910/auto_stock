# 사이클 23 — 3 전략 (BFB / VCP / donchian) 파라미터/UI 최적화 + AI 자문 자동 적용

**작성**: team-leader (트레이딩 데스크 출신)
**수신**: backend-dev (P1+P2+P3 백엔드) / frontend-dev (P3-3 Settings UI) / tdd-engineer (Red 테스트 25 케이스) / tester (TR 검증)
**TDD 사이클**: tdd-engineer Red → backend-dev + frontend-dev Green → tester 검증
**Plan 파일**: `/Users/koscom/.claude/plans/hashed-munching-eagle.md` (사용자 본 사이클 plan)
**매매 규칙 명세**: `_workspace/00_leader_trading_rules.md` 사이클 23 섹션 (트레이딩 현업 관점 보강)

## 1. 사이클 목표

운영자 보고: 3 전략 거래 0건 또는 신호 부족 + 운영 개선 요구. 사용자 결정:
- **P1 + P2 + P3 본 사이클 묶음** (단순 + 로직 + 자동화 한 번에)
- **자동 weight 감액 = AI 자문 자동 적용** (감액만 + 50% cap + 운영자 명시 토글 ON 후 작동)

## 2. 핵심 안전 원칙 (절대 깨지 말 것)

운영자 자금 안전이 본 사이클의 모든 결정에 우선한다. 다음 원칙을 위반하는 구현은 즉시 중단·재설계:

1. **AI 자문 자동 적용은 감액만** — `recommended_weight < current_weight` 만 자동 적용, 증액 SKIP
2. **50% cap 안전 가드** — `new_weight = max(recommended_weight, current_weight × 0.5)`. 한 사이클 내 weight 반토막 이하 금지
3. **PARAM_RANGES 화이트리스트 검증 통과** — `_validate_recommendations` 가 이미 정제한 결과만 자동 적용
4. **자동 적용 기본 false** — `system_config.auto_apply_enabled` 키, 운영자 명시 활성화 후에만 P3 작동
5. **status='applied_auto'** 마킹 — 운영자 수동 'applied' 와 분리하여 추적성 확보
6. **영구 로그** — `[auto_weight_apply]` / `[auto_params_apply]` / `[auto_apply_skip_increase]` / `[auto_apply_safeguard_skip]` prefix 4종 모두 `system_logs` INSERT
7. **params 자동 적용은 *보수적 키만*** — `stop_loss_rate`/`position_ratio`/`daily_loss_limit` (+ LTV/VB 보드별 손절 변형) 만. k_value/매수 임계/donchian_period 등은 운영자 명시 적용 보존
8. **매매 코드 신호 평가 본체 변경 0** — P2 는 *추가 가드/필터* 만, 기존 매수/매도 분기 (예: ATR 트레일링, 하드 손절) 그대로
9. **donchian 멀티데이 컨벤션 보존** — `Position._MULTIDAY_STRATEGIES` 변경 0, 시간/15:20 강제 청산 없음 유지
10. **VB `DEFAULT_TRADABLE_BOARDS` 변경 0** — POST_NXT 추가 금지 (15:20 일괄매도 정책)

## 3. 작업 영역 9개

### P1 — 단순 추가 (위험 0)

#### P1-1. `recommendation_engine.py` PARAM_RANGES + INT_PARAMS 확장

**파일**: `src/engine/recommendation_engine.py` (line 67-97 `PARAM_RANGES` dict / line 100-108 `INT_PARAMS` set)

**추가할 키 (9개)**:
```python
PARAM_RANGES = {
    ...,
    # ↓ 사이클 23 — VCP 핵심 진입 품질 4 키
    "base_depth_pct": (0.10, 0.50),
    "volume_contraction_ratio": (0.30, 1.00),
    "breakout_volume_mult": (1.0, 5.0),  # BFB 도 동일 키 — VCP/BFB 공용
    "last_pullback_max": (0.03, 0.15),
    # ↓ 사이클 23 — P2 신규 가드/필터 5 키
    "breakout_retention_minutes": (1, 30),
    "breakout_fail_n_days": (2, 20),
    "max_breakout_extension_pct": (0.5, 10.0),
    "box_contraction_period": (5, 30),
    "max_box_volatility_pct": (1.0, 15.0),
}

INT_PARAMS = {
    ...,
    # ↓ 사이클 23 — 정수 캐스트 대상
    "breakout_retention_minutes",
    "breakout_fail_n_days",
    "box_contraction_period",
}
```

**왜?**: AI 자문이 VCP 진입 품질 4 키 + BFB/donchian 신규 가드 5 키를 자동 권고할 수 있도록 화이트리스트 확장.

#### P1-2. BFB `min_trade_amount_failed` 카운터

**파일**: `src/engine/strategies/bull_flag_breakout.py`

**수정 내용**:
1. `_empty_scan_stats()` (line 36-47) 에 `"min_trade_amount_failed": 0` 키 추가 — 총 10 키
2. `_scan_universe` (line 359 부근) 의 `if mcap < min_mcap or trade_amt < min_trade: continue` 분기를 **분리**:
   ```python
   if mcap < min_mcap:
       self._scan_stats.setdefault("mcap_failed", 0)
       self._scan_stats["mcap_failed"] += 1  # 선택 — 옵셔널
       continue
   if trade_amt < min_trade:
       self._scan_stats["min_trade_amount_failed"] += 1
       continue
   ```
3. `src/engine/log_analysis_engine.py` 의 `_collect_strategy_funnel` (line 380) 함수가 BFB 의 `scan_stats` 전체를 metrics 에 포함하도록 보강

**왜?**: BFB 거래 0건 일자에 "거래대금 미달 N종목" 가시화. 운영자 즉시 진단.

#### P1-3. VCP `mcap_pass` scan_stats 1단계 추가

**파일**: `src/engine/strategies/vcp_breakout.py`

**수정 내용**:
1. `_empty_scan_stats()` (line 45-56) 에 `"mcap_pass": 0` 키 추가 — 총 9 키
2. `_scan_universe` (line 428 부근) 의 `if mcap >= min_mcap: filtered.append(ticker)` 통과 분기에서 `self._scan_stats["mcap_pass"] += 1` 카운터 증가
3. 프론트 `ScanMonitor.tsx` 의 `vcp-scan-funnel` STAGES 8 → 9 단계 (mcap_pass 추가) — VB/LTV 컨벤션 동기화

**왜?**: VCP 유니버스 깔때기 세분화. 시총 컷이 너무 빡빡한지 운영자 가시화.

### P2 — 로직 추가 (위험 중, 매매 코드 추가 가드/필터만)

#### P2-1. BFB `breakout_retention_minutes` 유지시간 조건

**파일**: `src/engine/strategies/bull_flag_breakout.py`

**수정 내용**:
1. `DEFAULT_PARAMS` (line 63-94) 에 추가:
   ```python
   "breakout_retention_minutes": 3,  # 기본 3분
   ```
2. `__init__` (line 96-109) 에 신규 인스턴스 변수:
   ```python
   self._breakout_first_seen: dict[str, datetime] = {}
   ```
3. `check_buy_signal` (line 403-470) 의 "돌파 순간" 분기 (line 438-442) **수정**:
   ```python
   # 돌파 순간 (prev<flag_high AND now>=flag_high)
   prev = self._prev_price.get(ticker, 0)
   self._prev_price[ticker] = current_price
   
   now_kst = datetime.now(KST)
   retention_min = int(self.config.params.get("breakout_retention_minutes", 3))
   
   # 첫 돌파 감지 — 등록 + 신호 NONE (대기 시작)
   if prev < flag_high <= current_price and ticker not in self._breakout_first_seen:
       self._breakout_first_seen[ticker] = now_kst
       logger.info(
           "BFB 돌파 1차 감지(retention 대기 시작): %s flag_high(%d) retention=%d분",
           ticker, flag_high, retention_min,
       )
       return Signal.NONE
   
   # 돌파 유지 중 — retention 시간 충족 여부 확인
   first_seen = self._breakout_first_seen.get(ticker)
   if first_seen is not None:
       if current_price < flag_high:
           # 후퇴 — 대기 종료, 등록 제거
           self._breakout_first_seen.pop(ticker, None)
           logger.info("BFB 돌파 후퇴(retention 대기 종료): %s", ticker)
           return Signal.NONE
       elapsed = (now_kst - first_seen).total_seconds()
       if elapsed < retention_min * 60:
           # 아직 대기 중
           return Signal.NONE
       # retention 충족 — 정상 흐름 (거래량 컷 등 다음 가드로 진행)
   else:
       # 첫 돌파도 안 일어났고 dict 에도 없음 — 정상 None
       return Signal.NONE
   ```
4. `register_cooldown_after_exit` (line 555 부근) 옆 또는 매도 체결 후 `self._breakout_first_seen.pop(ticker, None)` 도 추가 (당일 청산 후 재진입 시 깨끗하게)
5. **daily reset**: BFB 는 `StrategyBase._reset_daily_state` override 없이 `_bought_today.clear()` 를 어디서 하는지 확인해야 함. plan 에 따르면 명시적 `_reset_daily_state()` override 추가 — scheduler 의 `_reset_daily_state` 가 전략별 메서드 호출하는 패턴 확인 후 자연 진입 위치에 `self._breakout_first_seen.clear()` 추가

**회귀 가드 4 케이스** — `tests/unit/engine/strategies/test_bull_flag_breakout_retention.py`:
- ✅ 첫 돌파 감지 시 `_breakout_first_seen[ticker] = now`, 신호 NONE
- ✅ retention=3분 후 `freeze_time` 으로 시간 진행, 현재가 ≥ flag_high → BUY 신호
- ✅ retention 중 현재가 < flag_high → `_breakout_first_seen` pop, NONE
- ✅ retention_minutes=0 면 즉시 BUY (회귀 — 기존 동작)

#### P2-2. donchian `breakout_fail_n_days` 시간 기반 청산

**파일**: `src/engine/strategies/donchian_swing.py`

**수정 내용**:
1. `DEFAULT_PARAMS` (line 49-66) 에 추가:
   ```python
   "breakout_fail_n_days": 5,
   ```
2. `__init__` (line 68-76) 에 신규 인스턴스 변수:
   ```python
   self._breakout_high: dict[str, int] = {}  # ticker → 진입 시 20일 돌파선
   ```
3. `check_buy_signal` (line 481-533) 의 BUY 신호 발사 시 (line 517-533 사이) **추가**:
   ```python
   # 매수 신호 발사 시점에 진입 돌파선 등록 (체결통보 도착 전이라도 메모리 한정)
   self._breakout_high[ticker] = info["donchian_high"]
   ```
4. `check_exit_signal` (line 535-564) 의 하드 손절 *직후*, ATR 트레일링 *직전* 에 **추가**:
   ```python
   # 2.5) 시간 기반 청산 (사이클 23 P2-2) — 멀티데이 보유 약한 이탈 빠른 정리
   n_days = int(self.config.params.get("breakout_fail_n_days", 5))
   breakout_high = self._breakout_high.get(ticker, 0)
   if breakout_high > 0 and pos.buy_date:
       today = datetime.now(KST).date()
       days_held = (today - pos.buy_date).days
       if days_held >= n_days and current_price < breakout_high:
           logger.info(
               "donchian 시간 기반 청산: %s 보유 %d일 ≥ %d, 현재가(%d) < 돌파선(%d)",
               ticker, days_held, n_days, current_price, breakout_high,
           )
           return Signal.STOP_LOSS
   ```
5. 매도 체결 후 `_breakout_high.pop(ticker, None)` — `scheduler._reset_daily_state()` 가 아니라 *포지션 종료* 시점에 pop 해야 함. 대안: `risk.on_tick` 의 매도 후 처리 또는 다음 매수 시 자연 덮어쓰기. 본 사이클에서는 매수 시 무조건 덮어쓰기로 처리

**회귀 가드 3 케이스** — `tests/unit/engine/strategies/test_donchian_swing_fail_n_days.py`:
- ✅ N=5일 보유 + 현재가 < 돌파선 → STOP_LOSS
- ✅ N=5일 미달 (3일) 보유 → NONE (시간 가드 진입 안 함)
- ✅ `_breakout_high[ticker]` 등록 누락 (0) → graceful skip, 다른 청산 분기로 진행

#### P2-3. donchian 돌파폭 과열 상한

**파일**: `src/engine/strategies/donchian_swing.py`

**수정 내용**:
1. `DEFAULT_PARAMS` 에 추가:
   ```python
   "max_breakout_extension_pct": 3.0,  # 기본 3%
   ```
2. `check_buy_signal` (line 481-533) 의 시간 가드 (line 502-505) **직후**, 갭 스킵 *전* 또는 *후* 에 추가:
   ```python
   # 돌파폭 과열 상한 (사이클 23 P2-3) — 추격 금지
   max_ext = float(self.config.params.get("max_breakout_extension_pct", 3.0))
   donchian_high = info["donchian_high"]
   if donchian_high > 0:
       # 당일 고가 (open_price 와 current_price 중 큰 것 — high_price 가 시세에 있으면 그것 사용)
       from src.engine.scanner import ticker_prices
       price_info = ticker_prices.get(ticker, {})
       daily_high = max(
           int(price_info.get("stck_hgpr", 0) or 0),
           int(price_info.get("high_price", 0) or 0),
           current_price,
           open_price,
       )
       ext_pct = (daily_high - donchian_high) / donchian_high * 100
       if ext_pct > max_ext:
           logger.info(
               "[donchian_extension_skip] ticker=%s daily_high=%d donchian_high=%d ext_pct=%.2f > %.2f",
               ticker, daily_high, donchian_high, ext_pct, max_ext,
           )
           return Signal.NONE
   ```

**회귀 가드 2 케이스** — `tests/unit/engine/strategies/test_donchian_swing_extension_cap.py`:
- ✅ 당일 고가가 돌파선 대비 3% 초과 → NONE
- ✅ 당일 고가가 돌파선 대비 2% 초과 → BUY 정상 진입

#### P2-4. donchian 박스 수축 보조 필터

**파일**: `src/engine/strategies/donchian_swing.py`

**수정 내용**:
1. `DEFAULT_PARAMS` 에 추가:
   ```python
   "box_contraction_period": 10,
   "max_box_volatility_pct": 5.0,
   ```
2. `_empty_scan_stats()` (line 27-38) 에 `"box_contraction_pass": 0` 키 추가
3. `prepare()` (line 78-216) 의 ATR 통과 분기 (line 185-189) **직후**, `self._candidates[ticker] = {...}` *직전* 에 추가:
   ```python
   # 박스 수축 보조 필터 (사이클 23 P2-4)
   box_period = int(self.config.params.get("box_contraction_period", 10))
   max_box_vol = float(self.config.params.get("max_box_volatility_pct", 5.0))
   if len(candles) > box_period:
       box_highs = highs[1: box_period + 1]
       box_lows = lows[1: box_period + 1]
       box_closes = closes[1: box_period + 1]
       if box_highs and box_lows and box_closes:
           box_range = max(box_highs) - min(box_lows)
           box_mean = sum(box_closes) / len(box_closes)
           if box_mean > 0:
               vol_pct = box_range / box_mean * 100
               if vol_pct > max_box_vol:
                   continue  # 박스 수축 실패 (변동성 너무 큼)
               stats["box_contraction_pass"] += 1
           else:
               continue
   ```

**회귀 가드 3 케이스** — `tests/unit/engine/strategies/test_donchian_swing_box_contraction.py`:
- ✅ 박스 변동성 3% (≤5%) 통과
- ✅ 박스 변동성 7% (>5%) skip
- ✅ `box_contraction_pass` 카운터 정확히 증가

### P3 — AI 자문 자동 적용 (위험 고, 안전 가드 필수)

#### P3-1. `auto_apply_recommendations()` 함수 + scheduler 통합

**파일**: `src/engine/recommendation_engine.py` (신규 함수) + `src/engine/scheduler.py` (호출 추가)

**신규 함수 시그니처**:
```python
async def auto_apply_recommendations(target_date: date) -> dict:
    """20:00 AI 자문 직후 자동 적용 (감액만 + 50% cap + 보수적 파라미터만).
    
    Returns: {"applied": N, "skipped": M, "errors": [...]}
    """
```

**구현 흐름**:
1. `system_config.get_auto_apply_enabled()` 가 False → return `{"applied": 0, "skipped": 0, "reason": "disabled"}`
2. `parameter_recommendations.list_pending_by_date(target_date)` 신규 헬퍼 → pending 자문 목록
3. `trading_scheduler.registry` 에서 각 전략 객체 조회
4. 각 자문 처리:
   - `recommended_weight is None` → SKIP (weight 권고 없음)
   - `current_weight = strategy.config.weight`
   - `recommended_weight >= current_weight` → SKIP + `[auto_apply_skip_increase]` 로그
   - `cap_threshold = current_weight * 0.5`
   - `new_weight = max(recommended_weight, cap_threshold)` (50% cap)
   - `await save_weights({strategy_id: new_weight})`
   - `strategy.config.weight = new_weight` (메모리 반영)
   - **params 보수적 자동 적용 (P3-2)**:
     ```python
     CONSERVATIVE_KEYS = {"stop_loss_rate", "position_ratio", "daily_loss_limit",
                          "intraday_stop_loss", "overnight_stop_loss",
                          "stop_loss_main", "stop_loss_pre_nxt"}
     auto_params = {}
     for k, v in (rec.get("recommended_params") or {}).items():
         if k not in CONSERVATIVE_KEYS:
             continue  # 보수적 키만
         if k not in PARAM_RANGES:
             await write_log("INFO", f"[auto_apply_safeguard_skip] key={k} reason='out_of_param_ranges'")
             continue
         current = strategy.config.params.get(k)
         # "보수적 = 절대값 큰 음수" (stop_loss/daily_loss) 또는 "절대값 작은 양수" (position_ratio)
         is_more_conservative = False
         if k in ("stop_loss_rate", "intraday_stop_loss", "overnight_stop_loss",
                  "stop_loss_main", "stop_loss_pre_nxt", "daily_loss_limit"):
             # 음수 키 — 절대값 작은 = 더 보수적 (예: -7 → -5)
             if current is not None and float(v) > float(current):
                 is_more_conservative = True
         elif k == "position_ratio":
             # 양수 키 — 절대값 작은 = 더 보수적 (예: 0.3 → 0.2)
             if current is not None and float(v) < float(current):
                 is_more_conservative = True
         if is_more_conservative:
             strategy.config.params[k] = v
             auto_params[k] = v
     if auto_params:
         await save_params(strategy_id, strategy.config.params)
         await write_log("INFO", f"[auto_params_apply] strategy={strategy_id} keys={list(auto_params.keys())} values={auto_params}")
     ```
   - `await update_recommendation_status(rec_id, "applied_auto", applied_weight=new_weight, applied_params=auto_params)`
   - `await write_log("INFO", f"[auto_weight_apply] strategy={strategy_id} prev={current_weight} new={new_weight} reason='recommended<current, capped={cap_threshold}'")`

**scheduler 통합** (`src/engine/scheduler.py` line 472 부근, `generate_recommendations()` 호출 직후):
```python
await generate_recommendations()
await write_log("INFO", "20:00 전략수정 AI자문 생성 완료")

# 사이클 23 P3-1 — AI 자문 자동 적용 (감액만 + 50% cap)
try:
    from src.engine.recommendation_engine import auto_apply_recommendations
    target_date = datetime.now(KST).date()
    result = await auto_apply_recommendations(target_date)
    await write_log(
        "INFO",
        f"20:00 AI 자문 자동 적용: applied={result.get('applied', 0)} "
        f"skipped={result.get('skipped', 0)} reason={result.get('reason', '')}",
    )
except Exception as e:
    logger.exception("AI 자문 자동 적용 실패")
    await write_log("ERROR", f"AI 자문 자동 적용 실패: {type(e).__name__}: {e!s}")
```

**DB 변경**:
- `parameter_recommendations.status` ENUM/CHECK 제약에 `'applied_auto'` 추가 — **신규 마이그레이션** `supabase/migrations/0XX_auto_apply_status.sql`:
  ```sql
  ALTER TABLE parameter_recommendations
    DROP CONSTRAINT IF EXISTS parameter_recommendations_status_check;
  ALTER TABLE parameter_recommendations
    ADD CONSTRAINT parameter_recommendations_status_check
    CHECK (status IN ('pending', 'applied', 'partial', 'rejected', 'expired', 'applied_auto'));
  ```
- `src/db/parameter_recommendations.py` 에 신규 헬퍼:
  ```python
  async def list_pending_by_date(target_date: date) -> list[dict]:
      """target_date 의 status='pending' 자문 전체 조회."""
  ```

**회귀 가드 5 케이스** — `tests/unit/engine/test_auto_apply_recommendations.py`:
- ✅ `auto_apply_enabled=False` → `{"applied": 0, "reason": "disabled"}` 반환, DB 변경 0
- ✅ `recommended_weight < current_weight` → `save_weights` 호출, `applied_auto` 상태 마킹
- ✅ `recommended_weight > current_weight` → SKIP (증액 차단) + `[auto_apply_skip_increase]` 로그
- ✅ `recommended_weight < current_weight * 0.5` → `new_weight = current_weight * 0.5` (50% cap 발동)
- ✅ 보수적 키 (`stop_loss_rate=-5` from `-7`) 자동 적용, 비보수적 키 (`k_value_krx_main=1.5`) skip

#### P3-3. Settings UI 토글

**파일**:
- `src/db/system_config.py` — `auto_apply_enabled` 키 + `get_auto_apply_enabled()` / `set_auto_apply_enabled(value)` 헬퍼
- `src/routes/system_integrations.py` — `GET/PUT /api/integrations/auto-apply`
- `frontend/src/api/integrations.ts` — `getAutoApply / setAutoApply`
- `frontend/src/types/integrations.ts` — `IntegrationKey` 에 `'auto-apply'` 추가
- `frontend/src/components/IntegrationToggleCard.tsx` — 4번째 토글

**system_config 헬퍼**:
```python
_AUTO_APPLY_ENABLED_KEY = "auto_apply_enabled"

async def get_auto_apply_enabled() -> bool:
    """AI 자문 자동 적용 토글. 기본 False — 안전 우선."""
    v = await _get_bool_or_none(_AUTO_APPLY_ENABLED_KEY)
    return bool(v) if v is not None else False  # 기본 False

async def set_auto_apply_enabled(value: bool) -> None:
    await _set_bool(_AUTO_APPLY_ENABLED_KEY, value)
```

**routes**:
```python
@router.get("/auto-apply", response_model=ApiResponse)
async def get_auto_apply():
    enabled = await get_auto_apply_enabled()
    return ApiResponse(success=True, data={"enabled": enabled})

@router.put("/auto-apply", response_model=ApiResponse)
async def put_auto_apply(req: AutoApplyRequest):
    try:
        await set_auto_apply_enabled(req.enabled)
    except Exception:
        logger.exception("auto_apply_enabled 저장 실패")
        raise HTTPException(status_code=500, detail="DB 저장 실패")
    return ApiResponse(success=True, data={"enabled": req.enabled})
```

**frontend IntegrationToggleCard.tsx 4번째 토글 메타**:
```typescript
{
  key: 'auto-apply',
  label: 'AI 자문 자동 적용 (감액만 + 50% cap)',
  description:
    '20:00 AI 자문 직후 weight 감액 권고 + 보수적 파라미터 (stop_loss/position_ratio/daily_loss_limit) 를 자동 적용합니다. 증액 권고는 운영자 명시 적용만 가능합니다.',
  confirmOnMessage:
    'AI 자문 자동 적용을 활성화합니다. 매일 20:00 자문 직후 weight 감액 (50% cap) + 보수적 파라미터 가 자동 적용됩니다. 증액은 운영자 명시 적용만 가능합니다. 진행하시겠습니까?',
  confirmOffMessage:
    'AI 자문 자동 적용을 비활성화합니다. 모든 자문은 운영자 수동 적용에서만 반영됩니다. 진행하시겠습니까?',
  envVarName: '— (DB 키 only, 사이클 23)',
}
```

**회귀 가드**:
- 백엔드 2 케이스 — `tests/unit/db/test_system_config_auto_apply.py`:
  - ✅ 기본 False (DB 미설정)
  - ✅ set/get round-trip (True 저장 → True 조회)
- 프론트 2 케이스 — `frontend/src/components/__tests__/IntegrationToggleCard.auto_apply.test.tsx`:
  - ✅ 4번째 토글 렌더 (`data-testid="toggle-auto-apply"`)
  - ✅ ConfirmModal 이중 확인 후 PUT 발사

#### P3-4. 시장 레짐 → 파라미터 동적 조정 (별도 코드 없음)

P3-1 + P3-2 자동 적용으로 *이미* 시장 레짐 반영 (AI 자문 PROMPT 에 12 키 매크로 동봉됨 — 사이클 4). 별도 코드 X.

## 4. 회귀 가드 25 + 2 케이스 (총 27)

| 영역 | 파일 | 케이스 수 |
|------|------|-----------|
| P1-1 | `tests/unit/engine/test_param_ranges_vcp.py` | 5 |
| P1-2 | `tests/unit/engine/strategies/test_bull_flag_breakout_min_trade_failed.py` | 3 |
| P1-3 | `tests/unit/engine/strategies/test_vcp_breakout_mcap_pass.py` | 2 |
| P2-1 | `tests/unit/engine/strategies/test_bull_flag_breakout_retention.py` | 4 |
| P2-2 | `tests/unit/engine/strategies/test_donchian_swing_fail_n_days.py` | 3 |
| P2-3 | `tests/unit/engine/strategies/test_donchian_swing_extension_cap.py` | 2 |
| P2-4 | `tests/unit/engine/strategies/test_donchian_swing_box_contraction.py` | 3 |
| P3-1+2 | `tests/unit/engine/test_auto_apply_recommendations.py` | 5 |
| P3-3 (백엔드) | `tests/unit/db/test_system_config_auto_apply.py` | 2 |
| P3-3 (프론트) | `frontend/src/components/__tests__/IntegrationToggleCard.auto_apply.test.tsx` | 2 |

**기대 베이스라인**:
- 백엔드 1412 → 1437 (+25)
- 프론트 158 → 160 (+2)
- 회귀 0

## 5. 검증 명령

```bash
# 영역별 신규 회귀 가드 (병렬 가능)
python -m pytest tests/unit/engine/test_param_ranges_vcp.py \
                 tests/unit/engine/strategies/test_bull_flag_breakout_min_trade_failed.py \
                 tests/unit/engine/strategies/test_vcp_breakout_mcap_pass.py \
                 tests/unit/engine/strategies/test_bull_flag_breakout_retention.py \
                 tests/unit/engine/strategies/test_donchian_swing_fail_n_days.py \
                 tests/unit/engine/strategies/test_donchian_swing_extension_cap.py \
                 tests/unit/engine/strategies/test_donchian_swing_box_contraction.py \
                 tests/unit/engine/test_auto_apply_recommendations.py \
                 tests/unit/db/test_system_config_auto_apply.py -v
# 기대: 25 신규 케이스 모두 pass

# 백엔드 전체 회귀
python -m pytest -q
# 기대: 1437 passed, 회귀 0

# 프론트 회귀 (P3-3 Settings 토글)
cd frontend && npm test
# 기대: 160 passed, 회귀 0

# 영향 인덱스
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs
```

## 6. 문서 동기화 (sync-docs)

본 사이클 종료 직전:
- `src/engine/strategies/CLAUDE.md` — BFB retention / VCP PARAM_RANGES / donchian fail_n_days + extension_cap + box_contraction 명세 추가
- `src/engine/CLAUDE.md` — `auto_apply_recommendations` 절 추가
- `src/db/CLAUDE.md` — `system_config.auto_apply_enabled` 키 + `parameter_recommendations` status `applied_auto` 추가
- `frontend/CLAUDE.md` — `IntegrationToggleCard.auto_apply` 4번째 토글
- `_workspace/00_leader_trading_rules.md` — 사이클 23 섹션 (이미 완료, 본 spec 참조)
- `docs/HARNESS_CHANGELOG.md` — 사이클 23 1행 (최상단)

## 7. 커밋 단위

가능하면 단일 커밋 (P1 + P2 + P3 + 회귀 + 문서). 부득이 분리 시:
1. P1 + P2 (전략 코드 + 회귀)
2. P3 (자동 적용 + Settings + 마이그레이션 + 회귀)
3. 문서 동기화

**커밋 메시지 (한글 컨벤션)**:
- 단일: `feat(strategies): 3전략 (BFB/VCP/donchian) 파라미터/UI 최적화 + AI 자문 자동 적용 (사이클 23)`
- 분리: `feat(strategies): BFB retention + donchian fail_n_days/extension_cap/box_contraction (사이클 23 P1+P2)`
- 분리: `feat(advisor): AI 자문 자동 적용 (감액만 + 50% cap) + Settings 토글 (사이클 23 P3)`

## 8. push 정책

- **push 보류** — 사용자 별도 명시 승인 후. KRX 메인 시간 외 권장 (15:30+ 또는 익일 07:50 _boot 전)
- EC2 자동 배포: `git push origin main` → GitHub Actions → SSH → `git pull` + 재빌드

## 9. 시간 가이드

- P1 ~30분
- P2 ~2시간
- P3 ~3시간
- 회귀 + 문서 ~1.5시간
- 전체 ~7시간

**병렬 가능 영역**:
- P1-1 / P1-2 / P1-3 (3 파일 독립) — backend-dev 단일 또는 분배
- P2-1 (BFB) / P2-2 + P2-3 + P2-4 (donchian) — 파일 분리 시 병렬
- P3-1 (백엔드) + P3-3 (프론트) — backend-dev + frontend-dev 병렬

## 10. 보고 항목 (작업 종료 시)

1. 변경 파일 N개 + LOC
2. 신규 회귀 가드 25+2=27 케이스 pass 결과
3. 백엔드 1412 → 1437 / 프론트 158 → 160 (회귀 0)
4. 커밋 해시
5. sync-docs 결과
6. push 권장 시점
7. 운영 효과 요약 (BFB 가짜 돌파 감소 / donchian 가짜 돌파 + 과열 추격 차단 / VCP 진입 품질 자동 튜닝 / AI 자문 weight 자동 감액 + 50% cap 안전)

## 11. 의문/주의

- **P2-1 BFB retention 의 daily reset 위치**: `StrategyBase._reset_daily_state` override 가 있는지 또는 scheduler 의 `_reset_daily_state` 가 전략별 메서드를 호출하는지 확인 필요. 명세 무엇이든 `_breakout_first_seen` clear 시점이 누락되면 다음 영업일 잔류 (영업일 사이 시간차 ≥ retention 이므로 즉시 BUY 가능 — 안전성 영향은 적음)
- **P2-2 donchian `_breakout_high` 의 청산 후 pop**: 메모리만 사용, DB 영속화 X. 컨테이너 재시작 시 잃을 수 있으나 N일 청산 분기는 graceful skip (`get(ticker, 0) == 0` 면 skip). 재시작 후 첫 매수 시 자연 등록
- **P3-1 자동 적용 시점**: 20:00 자문 INSERT 직후 동기 호출. settle (20:10) 전 10분 여유 — OpenAI 호출 (전략당 30s × 6 = 3분) + 자동 적용 (6 전략 순회 ~10s) 마진 충분
- **P3-1 status='applied_auto' 마이그레이션**: 운영 DB 적용 시 기존 row 영향 0 (신규 status 값 추가만). 다운그레이드 시 ENUM check 위반 — 운영에 위험 없음

## 12. 사이클 종료 조건

- [x] P1-1: PARAM_RANGES + INT_PARAMS 확장
- [x] P1-2: BFB min_trade_amount_failed 카운터 + log_analysis 노출
- [x] P1-3: VCP mcap_pass scan_stats + 프론트 깔때기 9단계
- [x] P2-1: BFB breakout_retention_minutes
- [x] P2-2: donchian breakout_fail_n_days
- [x] P2-3: donchian max_breakout_extension_pct
- [x] P2-4: donchian box_contraction 보조 필터
- [x] P3-1+2: auto_apply_recommendations + scheduler 통합 + DB CHECK 마이그레이션
- [x] P3-3: Settings UI 4번째 토글 (백엔드 + 프론트)
- [x] 회귀 가드 25 + 2 = 27 케이스 모두 pass
- [x] 백엔드 1437 / 프론트 160 회귀 0
- [x] 문서 동기화 (CLAUDE.md 5개 + HARNESS_CHANGELOG.md + leader_trading_rules.md)
- [x] 커밋 (한글 메시지)
- [x] push 사용자 승인 대기

## 13. team-leader 검수 포인트

각 PR/커밋 검수 시 다음 4가지 우선 확인:
1. **자동 적용이 감액만 + 50% cap 인가?** 증액 분기에 SKIP + 로그 있는가?
2. **`status='applied_auto'` 마킹이 운영자 수동 'applied' 와 분리되어 있는가?**
3. **`auto_apply_enabled` 기본값이 false 인가?** 운영자 명시 활성화 전엔 자동 작동 안 하는가?
4. **매매 코드 신호 평가 본체 변경 0 인가?** P2 는 *추가 가드/필터* 만이고 기존 매수/매도 분기 보존되는가?

위반 시 즉시 작업 중단 + 재설계 지시.
