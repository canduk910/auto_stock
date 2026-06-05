# 사이클 62 가격 필터 — Red 명세 (38 케이스 / 12 파일)

> **작성**: tdd-engineer (2026-06-05 14:35 KST)
> **선행**: `_workspace/cycle62_price_filter_design_card.md` (v2, 자문 옵션 A 전부 채택)
> **선례**: 사이클 60/61 Phase 2-A1/A2 답습 (12 파일 분리 + freezegun + AsyncMock + caplog logger 명시)
> **위험 등급**: MEDIUM (매수 차단만, 자금 손실 0)
> **회귀 가드 합계**: 38 (백엔드 unit 25 + integration 5 + contract 3 + 프론트 5)

---

## §1. grep 결과 (Red 시점 미존재 영역)

### 1.1 system_config 3 키 부재 확인
```
$ grep -n "price_filter_min\|price_filter_max\|price_filter_mode" src/db/system_config.py
# (no match) — Red 정답
```

### 1.2 risk.on_tick 진입점 정확성 확인
```
$ grep -n "_get_price_filter_cached\|_emit_price_filter_skip\|invalidate_price_filter_cache" src/engine/risk.py
# (no match) — Red 정답
```
- `RiskManager._risk_silent_skip_logged_today` 기존 `DailyEmitCap` 필드는 line 44 (사이클 56-D)
- `reset_daily_state()` 위임 패턴 line 46-52 — A2 캐시 4 종은 본 사이클에서 추가
- `on_tick` 매수 평가 진입 line 86 `for strategy in self.registry.enabled():`
- `check_exit_signal` 분기 line 99-112 — 본 영역 *위* 에서는 절대 가격 필터 평가 금지

### 1.3 API 라우트 부재 확인
```
$ grep -rn "/price-filter\|PriceFilterRequest\|PriceFilterResponse" src/routes/
# (no match) — Red 정답
```

### 1.4 프론트 컴포넌트 부재 확인
```
$ ls frontend/src/components/PriceFilterCard.tsx
# No such file — Red 정답
```

### 1.5 scanner.ticker_prev_close 활용 가능성
- `src/engine/scanner.py:36` — `ticker_prev_close: dict[str, int] = {}`
- 글로벌 dict — Q2 fallback 사용 가능 (수정 없이 read-only)

### 1.6 order_engine 폴백 흐름 (Q3 회귀 가드 대상)
- L411 — 매수 폴백 `step_up(current_price, 5)`
- L676 — 매도 폴백 `step_down(cur_price, 5)`
- 양쪽 모두 `risk_manager._get_price_filter_cached` 호출 금지 (E-4 케이스로 검증)

---

## §2. 38 케이스 카테고리 분류

### 백엔드 unit 25 케이스 (8 파일)

| # | 파일 | 카테고리 | 케이스 수 | 매핑 |
|---|---|---|---|---|
| 1 | `tests/unit/db/test_cycle62_price_filter_system_config.py` | A — 헬퍼 | 5 | A-1~A-5 |
| 2 | `tests/unit/engine/test_cycle62_price_filter_risk_on_tick.py` | B — risk 분기 | 4 | B-1~B-4 |
| 3 | `tests/unit/engine/test_cycle62_price_filter_emit_cap.py` | C — emit cap | 2 | C-1, C-2 |
| 4 | `tests/unit/engine/test_cycle62_price_filter_cache.py` | D — 60s TTL | 2 | D-1, D-2 |
| 5 | `tests/unit/engine/test_cycle62_price_filter_sell_unaffected.py` | E — 매도 무영향 | 4 | E-1~E-4 |
| 6 | `tests/unit/engine/test_cycle62_price_filter_q2_fallback.py` | F — Q2 fallback | 5 | F-1~F-5 |
| 7 | `tests/unit/engine/test_cycle62_price_filter_warn_mode.py` | G — WARN | 2 | G-1, G-2 |
| 8 | `tests/unit/engine/test_cycle62_price_filter_daily_summary.py` | H — 일일 집계 | 1 | H-1 |

### 백엔드 integration 5 케이스 (1 파일)

| # | 파일 | 카테고리 | 케이스 수 |
|---|---|---|---|
| 9 | `tests/integration/test_cycle62_price_filter_integration.py` | I — E2E | 5 |

### 백엔드 contract 3 케이스 (1 파일)

| # | 파일 | 카테고리 | 케이스 수 |
|---|---|---|---|
| 10 | `tests/contract/test_cycle62_routes_price_filter.py` | C-Route | 3 |

### 프론트 vitest 5 케이스 (1 파일)

| # | 파일 | 카테고리 | 케이스 수 |
|---|---|---|---|
| 11 | `frontend/src/components/__tests__/PriceFilterCard.test.tsx` | F-FE | 5 |

### Red 명세 (1 파일)

| # | 파일 | 비고 |
|---|---|---|
| 12 | `_workspace/red/cycle62_price_filter.md` | 본 문서 |

**합계: 38 케이스 / 12 파일**

---

## §3. mock 패턴 매트릭스

| 카테고리 | 외부 의존성 | mock 패턴 |
|---|---|---|
| A — system_config | Supabase (`asyncio.to_thread`) | `fake_supabase` fixture (`tests/conftest.py:296`) — 기존 buy_block 테스트 답습 |
| B — risk on_tick | `get_price_filter` / `scanner.ticker_prev_close` / `_get_price_filter_cached` | `AsyncMock` + `patch.object(RiskManager, "_get_price_filter_cached")` |
| B — risk on_tick | `OrderEngine.execute_buy` | `MagicMock(execute_buy=AsyncMock())` — 매수 발사 검증 |
| B — risk on_tick | `get_current_regime().get_buy_block_state` | `patch("src.engine.risk.get_current_regime")` + `BuyBlockState(mode="OFF")` |
| C — emit cap | `write_log` | `patch("src.db.system_logs.write_log", AsyncMock())` |
| D — TTL cache | `time.monotonic` | `freezegun.freeze_time` + `monkeypatch.setattr(time, "monotonic")` |
| D — TTL cache | `get_price_filter` DB 호출 | `AsyncMock(side_effect=...)` 으로 호출 횟수 검증 |
| E — 매도 무영향 | `OrderEngine.execute_sell` + `check_exit_signal` | 같은 `AsyncMock` + `MagicMock` 패턴 |
| E-4 | `order_engine` 폴백 흐름 | `inspect.getsource(order_engine)` 정적 검증 — `risk_manager` 참조 0건 |
| F — Q2 fallback | `scanner.ticker_prev_close` | `monkeypatch.setattr(scanner, "ticker_prev_close", {...})` |
| G — WARN | logger + `write_log` | `caplog.set_level(logging.WARNING, logger="src.engine.risk")` |
| H — 일일 집계 | `_settle()` | `patch.object(scheduler, "_emit_price_filter_daily_summary", AsyncMock())` |
| I — integration | E2E (DB + risk + order_engine + scheduler) | `fake_supabase` + 6 전략 mock + `freeze_time` |
| C-Route | FastAPI TestClient | `monkeypatch.setattr(sc, "get_price_filter", AsyncMock(...))` |
| F-FE | MSW handlers | `server.use(http.get('/api/system/price-filter', ...))` |

---

## §4. freezegun 사용 위치

| 케이스 | 시각 freeze 이유 |
|---|---|
| D-1 | TTL 내 (60s) `now=time.monotonic` 고정 → 캐시 hit 검증 |
| D-2 | TTL 만료 (61s) — `freeze_time` 후 60s+1ms 진행 후 캐시 miss + DB 재호출 검증 |
| H-1 | `_settle()` 시각 = 20:10 KST — 일일 집계 emit prefix 검증 |
| I-2 | Settings PUT → 60s 캐시 invalidate 즉시 반영 race 검증 |
| I-5 | mode 변경 race (HARD → OFF 즉시 전환) |

---

## §5. 회귀 가드 매트릭스 (CLAUDE.md 절대 규칙 매핑)

| # | 케이스 | 보호 대상 (CLAUDE.md 절대 규칙) |
|---|---|---|
| B-4 / E-1 / E-2 / E-3 | `check_exit_signal` 분기 *전* 진입, 매도/익일청산/손절 무영향 | **사이클 38 명문화** — `tradable_boards` 매수 진입 전용 |
| E-4 | 매수 시장가 거부 5호가 폴백 시 가격 필터 재평가 금지 | "매수 시장가 거부 → `step_up(current_price, 5)` 지정가 1회 폴백" (변경 불가) |
| C-2 | `reset_daily_state` 동행 emit cap clear | "`_reset_daily_state` 동행 reset" |
| F-3 | `prev_close` 미존재 + `current_price` 미존재 → graceful 통과 | 신규 상장 영구 차단 방지 |
| F-4 | 갭상승 (prev=4500 / cur=5200) → prev_close 우선 차단 | 작전주 갭상승 회피 |
| G-1 | WARN 모드 매수 허용 (사이클 31 buy_block_mode WARN 답습) | 매수 사후 가시화 보장 |
| H-1 | 일일 집계 emit `_settle` 직전 1행 | 운영자 일일 차단 비율 가시화 |
| I-1 | mode=HARD + 범위 외 → 매수 차단 + 로그 INSERT | E2E 운영 가시성 |
| I-3 | 보유 손절 정상 (필터 무관) | 사이클 38 통합 검증 |
| I-4 | 익일청산 정상 (필터 무관) | 사이클 38 통합 검증 |
| CR-3 | PUT 400 검증 (음수 / max<min / 잘못된 mode) | 입력 검증 보장 |
| F-FE-3 | 저장 → PUT + toast | UI 즉시 반영 보장 |

---

## §6. 통과 기준

### 6.1 Red 시점 (현 시점)
- **38 케이스 모두 FAIL/AttributeError/ImportError 정답**
  - A 5 — `get_price_filter` / `set_price_filter` / `PriceFilter` 미존재 → `ImportError` 또는 `AttributeError`
  - B 4 — `_get_price_filter_cached` 메서드 미존재 → `AttributeError`
  - C 2 — `_emit_price_filter_skip` / `_price_filter_skip_logged_today` 필드 미존재
  - D 2 — `PRICE_FILTER_CACHE_TTL` 상수 미존재
  - E 4 — E-1~E-3 은 통과 가능 (사이클 38 기존 보호 — 회귀 가드 의도). E-4 는 `_emit_price_filter_skip` 의존
  - F 5 — `_get_price_filter_cached` 의존
  - G 2 — `_price_filter_warn_logged_today` 필드 의존
  - H 1 — `_emit_price_filter_daily_summary` 메서드 의존
  - I 5 — `_get_price_filter_cached` + DB 헬퍼 의존
  - C-Route 3 — `/api/system/price-filter` 라우트 미존재 → 404 → FAIL
  - F-FE 5 — `PriceFilterCard.tsx` 미존재 → import error

### 6.2 Green 시점 (backend-dev + frontend-dev Green 완료 후)
- **38 케이스 모두 PASS** + 백엔드 1882 → 1882+33=1915 PASS / 프론트 +5 PASS
- 백엔드 기존 1882 PASS 무영향 (회귀 0)
- 프론트 기존 160 PASS 무영향 (회귀 0)

### 6.3 사이클 38 명문화 영속 확인
- B-4 + E-1~E-4 PASS = `tradable_boards` 매수 진입 전용 원칙 보존
- E-4 ast 검증 = 매수/매도 폴백 흐름 가격 필터 재평가 0건

---

## §7. backend-dev + frontend-dev Green 발주 명세 (6 작업)

| # | 작업 | 담당 | 영향 파일 |
|---|---|---|---|
| G1 | system_config 3 키 + PriceFilter Pydantic | backend-dev | `src/db/system_config.py` |
| G2 | risk.on_tick 필터 분기 추가 (`check_exit_signal` *후*, `check_buy_signal` *전*) | backend-dev | `src/engine/risk.py` |
| G3 | `/api/system/price-filter` GET/PUT 라우트 | backend-dev | `src/routes/strategies.py` 또는 신규 `src/routes/price_filter.py` |
| G4 | 60s TTL 캐시 + invalidate (RiskManager) | backend-dev | `src/engine/risk.py` (G2 동시 작업) |
| G5 | `_settle()` 직전 일일 집계 emit | backend-dev | `src/engine/scheduler.py` |
| G6 | `PriceFilterCard.tsx` + Settings.tsx 통합 + `frontend/src/api/system.ts` 확장 | frontend-dev | `frontend/src/components/PriceFilterCard.tsx` + `frontend/src/pages/Settings.tsx` + `frontend/src/api/system.ts` + `frontend/src/types/system.ts` |

**영향 인덱스 갱신**: Green 완료 후 backend-dev / frontend-dev 가 `python tools/test_impact/build_index.py` + `node tools/test_impact/build_index_frontend.mjs` 재실행 의무.

---

## §8. 안전 가드 (작성 시점 — 14:35 KST KRX 메인)

- production code 절대 수정 0 — Red 단계는 테스트 파일만 추가
- 사이클 60/61 회귀 가드 1882 PASS 영속 (본 사이클 Red 시점에는 영향 0)
- 38 케이스 작성 후 Red 확인 시 백엔드 단독 실행 → 36 케이스 FAIL/Error, 프론트 단독 → 5 케이스 FAIL = Red 정답

---

## §9. 작성 완료 후 보고 형식 답습

1. 38 케이스 모두 FAIL/ImportError 확인 (4 카테고리 분리 측정)
2. freezegun + mock 사용 위치 표 (§3 / §4)
3. 회귀 가드 매트릭스 (§5)
4. 코드 정독 결과 명세 검증
5. backend-dev + frontend-dev Green 발주 매트릭스 (§7)
