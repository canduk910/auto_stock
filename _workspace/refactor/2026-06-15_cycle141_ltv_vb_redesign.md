# refactor-expert 자문: 사이클 141 — LTV 결함 통합 시정 (VB 기반 재설계 구조)

- **의뢰자**: team-leader
- **의뢰일**: 2026-06-15
- **긴급도**: HIGH (매매 안전성 직결 — LTV 보유 종목 일일 silent 매도 미발화 위험)
- **위험 등급**: HIGH (scheduler.py + risk/order_engine hot path 인접 영역)

## 자문 의제

1. VB 정합 메커니즘 분석 (사용자 verbatim "VB는 잘 동작")
2. scheduler ↔ strategy 상태 동기화 패턴 (결함 #2 영역이 LTV에만 있는지)
3. VB 로직 기반 LTV 재설계 구조 권고 (사용자 의도 = "VB 기초로 LTV 결함 해소 구조 *추가*")
4. 회귀 위험 영역 평가 (LTV 보유 종목 + 매매 안전성)

---

## 1. VB 정합 메커니즘 분석

### VB의 단순성 영역 영구 영속

**VB `DEFAULT_TRADABLE_BOARDS = ("main",)`** — KRX MAIN 단독 (사이클 26 영속). 단일 보드 영역.

**VB 매도 hot path 영역**:
- `check_exit_signal`: 손절 (`stop_loss_main`/`stop_loss_rate` 폴백) → Signal.STOP_LOSS
- `check_force_clear`: `_force_clear_main_only` (`scheduler.py:1786~1807`) 가 15:20 호출 = **모든 종목 보류 없이 청산** (POST_NXT 미포함 → `keeps_post_nxt=False` → `continue` 미발화 → `check_force_clear()` 호출 → 전량 청산)

**VB의 정합 작동 영역 영구 영속**: 
```python
# scheduler.py:1793~1797 영역
allowed = get_tradable_boards(sid, strategy.config.params)
keeps_post_nxt = MarketBoard.POST_NXT in allowed
# VB는 allowed = (MAIN,) → keeps_post_nxt = False → continue 미발화
# → check_force_clear() 정상 호출 → 전량 청산
```

**VB의 익일 청산 영역**: VB는 본질적으로 당일 청산 (15:20 일괄). 익일 청산은 *비상 안전망*만 (`_execute_next_day_clear` 대상 포함, 시세 미수신/거부 시 회복용). 따라서 결함 #2의 트레일링 분기 영역 영구 영속이 **VB는 의미 약함** (15:20 이전 정상 청산이 표준 영역).

### VB는 왜 결함 없는가

1. **단일 보드 (MAIN)** → `_force_clear_main_only` 의 POST_NXT 가드 우회 영역 영구 영속.
2. **15:20 강제 청산이 표준** → 익일 청산 영역 영구 영속 우회.
3. **`_limit_up_reached` 영역 영구 영속 없음** → 트레일링 모드 전환 영역 영구 영속 없음 → 결함 #2 영역 영구 영속 미해당.

---

## 2. scheduler ↔ strategy 상태 동기화 패턴

### 결함 #2 영역 영구 영속 — LTV에만 발생하는 영역

**결함 #2 본체** (`scheduler.py:1210~1215`):
```python
if gap_rate >= gap_up_threshold:
    logger.info("트레일링 스탑 모드: %s 갭률 %.1f%% (전략: %s)", t(ticker), gap_rate, strategy_id)
    await write_log("INFO", f"트레일링 스탑 모드: {t(ticker)} 갭률 {gap_rate:.1f}% ({strategy_id})")
    # LTV._limit_up_reached.add(ticker) 호출 없음 ← 결함
    # pos.high_since_buy = today_open 설정 없음 ← 결함
```

**결함 #2의 본질 영역 영구 영속**: scheduler가 "트레일링 모드 진입" 영역 영구 영속 메시지만 emit. **LTV strategy 객체는 후성을 *모름*** → `check_exit_signal` 에서 `_limit_up_reached` 미등록 → 당일 모드 진입 → `intraday_stop_loss=-3%` 임계만 작동 → 트레일링 영역 미발화.

### 다른 전략 영역 영구 영속 확인

| 전략 | `_limit_up_reached` | `_execute_next_day_clear` 트레일링 영역 | 결함 #2 해당 |
|------|---------------------|------------------------------------|-------------|
| momentum | 없음 | `high_since_buy` 자체 추적 | 영향 미해당 |
| VB | 없음 | 익일 청산 = 비상 안전망 (15:20 표준) | 영향 미해당 (의미 약함) |
| **LTV** | **있음** | **상한가 모드 전용 트레일링 영역** | **결함 #2 직접 해당** |
| donchian | 없음 (멀티데이) | 익일 청산 영역 없음 | 영향 미해당 |
| BFB | 없음 (당일 청산) | 익일 청산 영역 없음 | 영향 미해당 |
| VCP | 없음 (멀티데이) | 익일 청산 영역 없음 | 영향 미해당 |

**결론 영역 영구 영속**: **결함 #2 = LTV 전용 결함 영역 영구 영속**. VB 답습 시도 시 위험 0 (VB는 트레일링 모드 영역 영구 영속 없음).

### 결함 #1 — LTV에만 발생하는 영역

**결함 #1 본체** (`scheduler.py:1790~1801`):
```python
allowed = get_tradable_boards(sid, strategy.config.params)
keeps_post_nxt = MarketBoard.POST_NXT in allowed
if keeps_post_nxt:  # LTV = True (("pre_nxt", "main", "post_nxt"))
    logger.info("%s POST_NXT 활성 — 15:20 강제 청산 보류, ...", ...)
    continue  # ← LTV.check_force_clear() 호출 *자체* 안 함
```

**결함 #1의 본질 영역 영구 영속**: LTV의 `check_force_clear()` 본체 (`long_tail_volatility.py:590~595`)는 **상한가 모드가 아닌 종목만 청산** 의도였으나, scheduler가 POST_NXT 활성 시 `continue` 발화 → **모든 종목 보류** (상한가 모드 영역 + 일반 종목 모두).

**LTV의 도메인 의도 영역 영구 영속 (사이클 38 명문화 영속)**:
- 상한가 모드 종목 → POST_NXT 익일 청산 모드 진입 (현행 정합)
- 일반 종목 (상한가 미도달) → **15:20 즉시 청산** (현행 결함, scheduler가 호출 자체 안 함)

---

## 3. VB 로직 기반 LTV 재설계 구조 권고

### 사용자 의도 영역 영구 영속

> "VB로직을 기초로 기존LTV로직의 결함들을 해소할 수 있는 구조를 추가로 쌓자"

**핵심 영역 영구 영속**: 기존 LTV 폐기 X + VB 기초 *추가* 구조 영역 영구 영속.

### 권고 영역 영구 영속 (사이클 67 stale_manager 4 sub-module 분해 패턴 답습)

#### 권고 #1 — 결함 #1 시정: `_force_clear_main_only` 영역 영구 영속 LTV 분기 영구 영속

**현행 (scheduler.py:1786~1807)**:
```python
for sid in ("volatility_breakout", "long_tail_volatility"):
    # ...
    allowed = get_tradable_boards(sid, strategy.config.params)
    keeps_post_nxt = MarketBoard.POST_NXT in allowed
    if keeps_post_nxt:
        logger.info("%s POST_NXT 활성 — 15:20 강제 청산 보류, ...", ...)
        continue  # ← 모든 종목 보류 결함
    
    clear_tickers = strategy.check_force_clear()
    # ...
```

**권고 시정**:
```python
for sid in ("volatility_breakout", "long_tail_volatility"):
    # ...
    # 사이클 141 — 결함 #1 시정: POST_NXT 활성 여부 무관 check_force_clear() 호출.
    # LTV의 check_force_clear() 본체가 _limit_up_reached 영역으로 상한가 모드 종목 제외 영속.
    # VB의 check_force_clear()는 전량 청산 영속 (POST_NXT 미포함).
    clear_tickers = strategy.check_force_clear()
    if not clear_tickers:
        continue
    
    # 운영 로그 영역 영구 영속 (사이클 141 신규)
    allowed = get_tradable_boards(sid, strategy.config.params)
    keeps_post_nxt = MarketBoard.POST_NXT in allowed
    if keeps_post_nxt:
        logger.info(
            "%s POST_NXT 활성 — 15:20 강제 청산: %d 종목 (상한가 모드 영역 영구 영속 종목 제외)",
            strategy.config.name, len(clear_tickers),
        )
    
    await write_log("INFO", f"{strategy.config.name} 15:20 강제 청산 대상: {clear_tickers}")
    for ticker in clear_tickers:
        if ticker in strategy.state.positions:
            await self.order_engine.execute_sell(ticker, Signal.FORCE_CLEAR, sid)
            logger.info("%s 강제 청산: %s", strategy.config.name, t(ticker))
```

**영역 영구 영속 효과**:
- VB는 변경 0 (이미 `keeps_post_nxt=False` 영역 영속, `check_force_clear()` 전량 청산 영속)
- LTV는 `check_force_clear()` 호출 영역 → **상한가 모드 영역 종목 제외 + 일반 종목 청산** = 사이클 38 명문화 영속 정합

#### 권고 #2 — 결함 #2 시정: `_execute_next_day_clear` 트레일링 분기 영구 영속 strategy 상태 영구 영속

**현행 (scheduler.py:1210~1215)**:
```python
if gap_rate >= gap_up_threshold:
    logger.info("트레일링 스탑 모드: %s 갭률 %.1f%% (전략: %s)", t(ticker), gap_rate, strategy_id)
    await write_log("INFO", f"트레일링 스탑 모드: {t(ticker)} 갭률 {gap_rate:.1f}% ({strategy_id})")
    # ← strategy 후성 미동기화
```

**권고 시정 (VB 답습 + LTV 특화)**:
```python
if gap_rate >= gap_up_threshold:
    # 사이클 141 — 결함 #2 시정: LTV strategy 상태 영역 영구 영속 동기화 영구 영속.
    # check_exit_signal 의 트레일링 영역 영구 영속 진입 의무 영구 영속.
    if strategy_id == "long_tail_volatility":
        strategy = self.registry.get(strategy_id)
        if strategy and hasattr(strategy, "_limit_up_reached"):
            strategy._limit_up_reached.add(ticker)
        pos.high_since_buy = today_open  # 트레일링 기준점 = 시가
    
    logger.info(
        "트레일링 스탑 모드: %s 갭률 %.1f%% (전략: %s, 기준가: %d)",
        t(ticker), gap_rate, strategy_id, today_open,
    )
    await write_log(
        "INFO",
        f"트레일링 스탑 모드: {t(ticker)} 갭률 {gap_rate:.1f}% ({strategy_id}, 기준가: {today_open})",
    )
```

**영역 영구 영속 효과**:
- VB는 변경 0 (`strategy_id != "long_tail_volatility"` → 분기 미진입)
- LTV는 `_limit_up_reached` 영역 등록 + `high_since_buy` 영역 기준점 설정 → `check_exit_signal` 의 익일 청산 트레일링 영역 영구 영속 분기 정상 작동
- **후성 093370 운영 사례 재현 시 시정 효과 영구 영속**: 6/15 시가 갭률 ≥ `gap_up_threshold` → 트레일링 모드 진입 → `_limit_up_reached.add("093370")` + `high_since_buy=today_open` → `check_exit_signal` 트레일링 분기 진입 → 6/15 일중 고점 23,700원 추적 → -5.91% 하락 시 `trailing_stop_rate=-1.2%` 임계 발화 → 매도 정상

#### 권고 #3 — refactor 영역 영구 영속 (사이클 67 답습)

**현행 영역 영구 영속**: `_force_clear_main_only` + `_execute_next_day_clear` 영역 모두 scheduler.py 내부 영역 영구 영속.

**영역 영구 영속 권고 (사이클 67 stale_manager 4 sub-module 분해 답습)**: 본 사이클 141은 **결함 시정 단독**. 분해 영역 영구 영속은 카드 #26 (scheduler.py 분해 HIGH) 후속 사이클 인계.

**이유 영역 영구 영속**: 분해 + 결함 시정 동시 사이클 = 회귀 위험 영역 영구 영속 ↑. 사이클 67 답습 = **행위 보존 우선** → 분해 영역 영구 영속 후속 사이클 인계.

### 추정 라인 영역 영구 영속

| 영역 | 추정 라인 | 위험 |
|------|----------|------|
| `_force_clear_main_only` 시정 (결함 #1) | +5~10L | LOW |
| `_execute_next_day_clear` 트레일링 분기 시정 (결함 #2) | +8~12L | MEDIUM (LTV strategy 상태 동기화) |
| 회귀 가드 신규 가드 (결함 #1+#2) | +120~150L | LOW |
| 후성 093370 운영 사례 재현 통합 테스트 | +50~80L | MEDIUM (freezegun + 시뮬레이션) |
| **합** | **+183~252L (실 production +13~22L)** | **MEDIUM** |

---

## 4. 회귀 위험 영역 평가

### LTV 보유 종목 영역 영구 영속 영향

**현재 LTV 보유 종목 영역 영구 영속**: 후성 093370 영역 영구 영속 (운영 사례).

**영역 영구 영속 영향 평가**:
1. **결함 #1 시정 후**: 15:20 강제 청산 영역 영구 영속에서 LTV 일반 종목 (상한가 미도달) 즉시 청산. 후성 093370이 상한가 미도달 종목이면 → **즉시 청산** (현행 silent 보류 영구 차단).
2. **결함 #2 시정 후**: 익일 청산 트레일링 분기 영역 영구 영속이 LTV strategy 상태 영역 영구 영속 동기화 → `check_exit_signal` 트레일링 영역 영구 영속 분기 정상 작동.

### CLAUDE.md "절대 깨지 말 것" 8 영역 영구 영속

- **체결통보 구독 영역 영구 영속**: 변경 0 (lifecycle hook 영역 외)
- **uvicorn 단일 워커 영역 영구 영속**: 변경 0
- **주문번호 매핑 영역 영구 영속**: 변경 0 (place_order 영역 외)
- **체결통보 선행 race 가드 영역 영구 영속**: 변경 0 (`_completed_orders` 영역 외)
- **`_reset_daily_state()` 영역 영구 영속**: 변경 0 (LTV `_limit_up_reached.clear()` 영속)
- **익일 청산 영역 영구 영속**: **시정 영역 영구 영속** — `_pending_next_day_clear` + 30s 안정화 보존 + 트레일링 분기 영역 영구 영속 strategy 상태 동기화 *추가* (사용자 의도 영구 영속)
- **NXT 매도 거부 좀비 차단 영역 영구 영속**: 변경 0
- **WebSocket 시세 영역 영구 영속**: 변경 0

### 회귀 가드 명세 영역 영구 영속

#### G-141-A — 결함 #1 시정 회귀 가드 (5 케이스)

1. **G-141-A1**: `_force_clear_main_only` 영역 영구 영속 LTV `check_force_clear()` 호출 보장 영역 영구 영속 (mock LTV with `keeps_post_nxt=True`)
2. **G-141-A2**: VB는 변경 0 영역 영구 영속 (mock VB with `keeps_post_nxt=False` → `check_force_clear()` 호출 영속)
3. **G-141-A3**: LTV `check_force_clear()` 반환값 영역 영구 영속 = 상한가 모드 영역 종목 제외 + 일반 종목 포함
4. **G-141-A4**: `_limit_up_reached` 영역 영구 영속 상한가 모드 종목 영역 영구 영속 청산 영구 차단 (`Signal.FORCE_CLEAR` 호출 0건)
5. **G-141-A5**: AST 가드 영역 영구 영속 (`continue` 분기 영구 영속 `check_force_clear()` 호출 *전* 영역 영구 영속 차단)

#### G-141-B — 결함 #2 시정 회귀 가드 (6 케이스)

1. **G-141-B1**: `_execute_next_day_clear` 트레일링 분기 영역 영구 영속 LTV `_limit_up_reached.add(ticker)` 호출 보장 영역 영구 영속
2. **G-141-B2**: `_execute_next_day_clear` 트레일링 분기 영역 영구 영속 LTV `pos.high_since_buy = today_open` 설정 보장 영역 영구 영속
3. **G-141-B3**: VB는 변경 0 영역 영구 영속 (`strategy_id == "volatility_breakout"` → 분기 미진입)
4. **G-141-B4**: `_limit_up_reached` 영역 영구 영속 등록 후 `check_exit_signal` 트레일링 영역 영구 영속 분기 진입 영역 영구 영속
5. **G-141-B5**: 후성 093370 운영 사례 재현 영역 영구 영속 (freezegun + 시뮬레이션, 6/15 일중 고점 23,700원 → -5.91% 하락 → 트레일링 발화 영역 영구 영속)
6. **G-141-B6**: AST 가드 영역 영구 영속 (트레일링 분기 영구 영속 `_limit_up_reached.add` 호출 영역 영구 영속 검증)

#### G-141-C — 매매 안전성 영역 영구 영속 영향 0 (3 케이스)

1. **G-141-C1**: CLAUDE.md "절대 깨지 말 것" 8 영역 영구 영속 변경 0 (AST 가드 영구 영속)
2. **G-141-C2**: `risk.on_tick` / `order_engine` / `realtime/` / `auth/` import 0건 영역 영구 영속
3. **G-141-C3**: `_pending_next_day_clear` + 30s 안정화 영역 영구 영속 보존 영역 영구 영속

### 사이클 분할 권고 영역 영구 영속

**옵션 A — 통합 단일 사이클** (사이클 141):
- 결함 #1 + #2 + 회귀 가드 + 운영 사례 재현 = 합 +183~252L
- 위험 = MEDIUM
- 회귀 가드 = 14 케이스

**옵션 B — 분할 사이클**:
- 사이클 141 = 결함 #1 단독 (15:20 강제 청산 영역 영구 영속, LOW 위험)
- 사이클 142 = 결함 #2 단독 (익일 청산 트레일링 영역 영구 영속, MEDIUM 위험)

**권고 영역 영구 영속**: **옵션 A 통합 단일 사이클** — 두 결함이 모두 LTV 영역 영역 영구 영속 한정 + 매매 안전성 직결 (silent 매도 미발화 영구 차단 의무) + 회귀 가드 명세 동행 영역 영구 영속.

---

## 최종 권고 영역 영구 영속

1. **결함 #1 시정 영역 영구 영속** (`_force_clear_main_only` LTV 분기 영구 영속): **즉시 진행 권고 영역 영구 영속** — 사이클 38 명문화 영역 영구 영속 정합 영역 영구 영속.
2. **결함 #2 시정 영역 영구 영속** (`_execute_next_day_clear` 트레일링 분기 영구 영속): **즉시 진행 권고 영역 영구 영속** — 후성 093370 운영 사례 재현 영역 영구 영속 매도 의무 영역 영구 영속.
3. **분해 영역 영구 영속**: **카드 #26 후속 사이클 인계 영역 영구 영속** — 사이클 67 답습 + 행위 보존 우선 영역 영구 영속.
4. **회귀 가드 명세 영역 영구 영속**: 14 케이스 (G-141-A 5 + G-141-B 6 + G-141-C 3) 영역 영구 영속.
5. **사이클 분할 권고 영역 영구 영속**: 옵션 A 통합 단일 사이클 영역 영구 영속.

## refactor 영역 영구 영속 위험 평가 영역 영구 영속

- **회귀 위험 영역 영구 영속**: MEDIUM (scheduler.py + LTV strategy 상태 동기화 영역 영구 영속)
- **매매 안전성 영향 영역 영구 영속**: 시정 영역 영구 영속 (silent 매도 미발화 영구 차단 + 사이클 38 명문화 정합)
- **행위 보존 영역 영구 영속**: VB 변경 0 (사용자 verbatim "VB는 잘 동작" 보존)
- **회귀 가드 명세 영역 영구 영속**: 14 케이스 영역 영구 영속

자문 영역 영구 영속 완료 영역 영구 영속.
