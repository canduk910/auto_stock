# 사이클 D 통합·안전성 검증 리포트 — 레짐 가드 silent inert 가시화

- **날짜**: 2026-07-31
- **검증자**: tester (QA)
- **명세**: `_workspace/red/_behaviors_cycleD_regime_inert_20260731.md`
- **Red 로그**: `_workspace/red/cycleD_regime_inert.md`
- **성격**: 관찰성만 추가. 매매 행위(blocked/soft_multiplier) byte 동일 = fail-open 보존.

## 종합 판정

백엔드 구현(D-1~D-6)은 명세와 정확히 1:1 정합하고 매매 안전성 diff 0이 직접 검증되어 **백엔드는 검증 통과**. 다만 **이 사이클의 명시 목적(운영자가 대시보드에서 "가드 무력"을 인지)은 미달성** — 백엔드가 `guard_inert` 필드를 내보내지만 프론트에 렌더하는 요소가 전무하고, 프론트 타입에 필드 자체가 없음. **frontend-dev 동반 사이클 필요**(항목 3).

## 항목별 PASS/FAIL

| # | 검증 항목 | 판정 |
|---|-----------|------|
| 1 | boot 경보 end-to-end | PASS |
| 2 | API 계약 정합 (백엔드) | PASS / 프론트 타입·mock 미갱신(항목 3 편입) |
| 3 | 프론트 가시화 갭 | **FAIL — frontend-dev 동반 사이클 필요** |
| 4 | 매매 안전성 8영역 diff 0 | PASS |
| 5 | 60s TTL 캐시 상호작용 | PASS |
| 6 | 전체 백엔드 무회귀 | PASS (4036 passed / 0 failed) |

## 항목 상세

### 1. boot 경보 end-to-end — PASS
- 경보는 실경로 `scheduler._refresh_market_regime_and_persist`(`src/engine/scheduler.py:2133-2147`), `set_current_regime(regime)` 직후 배치. 명세 위치 정합.
- 실 배선 확인: `src/engine/boot_manager.py:66` 이 `_refresh_market_regime_and_persist()` 호출 → boot 1회/일 발화 경로 확정.
- empty regime + mode≠OFF 에서만 `[regime_guard_inert]` WARNING 발화, OFF/데이터 유입 시 미발화 — D-4 3케이스 PASS.
- `get_buy_block_mode()` DB 실패는 `try/except`로 감싸 `logger.exception` 후 경보 skip + boot 계속(graceful). fail-open 방향 안전.

### 2. API 계약 정합 — 백엔드 PASS
- `_build_buy_block_status`(`src/routes/system_integrations.py:277-292`): `data_available = regime.has_regime_data`, `guard_inert = state.mode != "OFF" and not data_available`. 정상/fallback 두 경로 모두 `regime`이 try 이전(L267) 정의 → fallback 안전.
- D-5 라우트 3케이스 PASS: empty+SOFT→inert=true / data+SOFT→false / OFF+empty→false.
- **프론트 타입/mock 갱신 요구 여부**: 신규 2필드는 Pydantic default(`True`/`False`)를 가진 additive 필드 → 기존 프론트/MSW/e2e mock을 깨지 않음(프론트가 아직 안 읽고 TS는 여분 필드 무시). 그러나 **가시화 기능을 실제 구현하려면 프론트 타입·mock 갱신 필수**(항목 3).

### 3. [핵심] 프론트 가시화 갭 — FAIL, frontend-dev 동반 사이클 필요
- **매수 가드 카드 컴포넌트 경로**: `frontend/src/components/IntegrationToggleCard.tsx` 의 `BuyBlockSection`(181라인~).
- **guard_inert 배너 렌더 유무**: **없음**. 이 컴포넌트는 mode / soft_multiplier(308-315) / reasons(319-336) / blocked만 렌더하고 `guard_inert` 배너·경고 렌더가 전무.
- **소비 타입**: `frontend/src/types/integrations.ts::BuyBlockState`(44-50)에 `data_available`/`guard_inert` 필드가 아예 없음.
- **대체 표시 부재**: `MarketRegimeCard.tsx`가 amber 배너(`market-regime-block-banner`, 104라인)를 렌더하나 이는 `buy_blocked`/`block_reason`(market_regime 계열) — 이번 `guard_inert`와 별개 필드로 가드 무력 상태를 대신 표시 못 함.
- **결론**: 백엔드 필드만으론 화면에 아무것도 안 뜸. 운영자는 여전히 "정상+평온" 인지 → false sense of protection 근본 결함이 UI 레벨에서 잔존.

**필요한 frontend-dev 변경 요약**:
1. `frontend/src/types/integrations.ts::BuyBlockState`에 `data_available: boolean` + `guard_inert: boolean` 추가
2. `IntegrationToggleCard.tsx::BuyBlockSection`에 `data.guard_inert === true` 시 degraded 배너 렌더(amber/red, testid 부여, 예: "매크로 데이터 미유입 — 가드 무력, 매수 무제한 통과 중")
3. mock 동기화: e2e `e2e/fixtures/api-mocks.ts` buy-block 라우트(244-258 응답 블록)에 신규 2필드 추가 + 프론트 vitest buy-block stub(현재 `setupToggleStubs` 경유, `handlers.ts`에 직접 buy-block 핸들러 없음)에 필드 추가
4. 회귀 가드: guard_inert=true 시 배너 노출 / false·OFF 시 미노출 vitest 케이스

### 4. 매매 안전성 8영역 diff 0 — PASS
- `git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py` = **0 라인**(직접 확인). blocked/soft_multiplier 소비 경로 byte 동일, 신규 필드는 로깅/표시 전용.

### 5. 60s TTL 캐시 상호작용 — PASS
- `get_buy_block_state()` 5개 분기(OFF/HARD/WARN/SOFT/unknown-fallback) 모두 캐시 저장 *전* `data_available=self.has_regime_data` 세팅 → 캐시된 state에 값 보존.
- 라우트는 별도로 `regime.has_regime_data`를 재계산해 응답에 사용하나, regime 필드가 인스턴스 불변 + 캐시가 인스턴스 단위라 캐시된 `state.data_available`와 항상 일치.
- D-3 캐시 hit 케이스(`test_get_buy_block_state_data_available_survives_cache`) PASS.

### 6. 전체 백엔드 무회귀 — PASS
- `pytest tests -q --ignore=tests/integration` → **4036 passed, 8 skipped, 326 xfailed, 12 xpassed, 0 failed** (89.8s).
- 사이클 D 신규 17건(engine 14 + routes 3) 전부 PASS.
- 팀장 언급 `test_cycle64_routes_price_filter::test_CR1` 격리 flake는 **이번 전체 실행에서 재현되지 않음**(0 failed) — 사이클 D 무관 확인.

## 발견 결함

- **DEF-1 (MEDIUM, 사이클 목적 미달)**: 프론트 가시화 부재. 백엔드 `guard_inert` 필드가 어떤 UI에도 렌더되지 않아 사이클 D 명시 목적(운영자 대시보드 인지) 미달성. 항목 3 frontend-dev 변경으로 봉합 필요. 매매 안전성/데이터 무관, 관찰성 갭.
- 그 외 백엔드 로직·안전성·계약 결함 없음.

## 최종 수치

- 사이클 D 신규 테스트: **17 PASS** (14 engine + 3 routes)
- 전체 백엔드: **4036 passed / 0 failed** (integration 제외)
- 매매 안전성 8영역: **diff 0 라인** (직접 검증)
- 변경 소스 diff: `market_regime.py` +27 / `scheduler.py` +16 / `models/system_integrations.py` +9 / `routes/system_integrations.py` +11 — 전부 명세 D-1~D-5와 1:1 정합

## team-leader 조치 권고

백엔드는 머지 가능하나, 사이클 목적 완결을 위해 **frontend-dev 동반 사이클(항목 3의 4단계)을 즉시 발주** 권고. 프론트 없이 배포하면 백엔드 계약만 준비된 채 운영자 가시화는 여전히 blind 상태로 잔존.
