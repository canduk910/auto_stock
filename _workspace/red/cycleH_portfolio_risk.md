# 사이클 H Red — 포트폴리오 전체 리스크·섹터 노출 관찰 훅 (Phase 1, 관찰 전용)

작성: tdd-engineer / 2026-08-02
정본 명세: `_workspace/cycleH_portfolio_risk_phase1_spec.md` + `_workspace/00_leader_trading_rules.md` "사이클 H" 절

## 목적

터틀 자금관리 서적 대조 감사 갭 2건(포트폴리오 총리스크 상한 부재 + 전략 간 섹터 집중 무통제) 의 Phase 1 계량·가시화. **배제 0 · 매수 차단 0 · 매매 행위 byte 동일.** 순수함수 모듈 + 라우트 + 20:10 리포트 배선만.

## Red 테스트 파일 (절대경로)

- `/Users/koscom/Projects/auto_stock/tests/unit/engine/test_cycleH_portfolio_risk.py` — (a) extract_hard_stop_pct + (b) compute_portfolio_risk_snapshot 순수함수 결정적 검증 (29 케이스)
- `/Users/koscom/Projects/auto_stock/tests/unit/routes/test_cycleH_portfolio_route.py` — (c) `GET /api/portfolio/risk` 스키마 + graceful 200 (4 케이스)
- `/Users/koscom/Projects/auto_stock/tests/unit/engine/test_cycleH_log_analysis_snapshot.py` — (d) 20:10 metrics `portfolio_risk_snapshot` 배선 + graceful (2 케이스)
- `/Users/koscom/Projects/auto_stock/tests/unit/ast/test_cycleH_ast_portfolio_risk_isolation.py` — (e) 8영역 격리 + portfolio_risk.py 순수성 + (f) import sanity (8 케이스)

총 43 케이스.

## 케이스 목록 + 의도

### (a) `extract_hard_stop_pct(params, *, default=-7.0)` — 12 케이스
후보 7키(stop_loss_rate / intraday_stop_loss / overnight_stop_loss / stop_loss_main / stop_loss_pre_nxt / turtle_backstop_pct / hard_stop_pct) 中 음수만 → min(최대 계획 손실). 후보 0건/None → default -7.0 (0.0 금지 — 리스크 0 오인 차단).
- donchian형 {-7.0, -9.0} → **-9.0** / kojiro형 {hard_stop_pct -8.0} → **-8.0** / LTV형 {intraday -3, overnight -5} → **-5.0**
- 양수 무시 / 전부 양수 → default / 빈 dict → default / None 입력 → default / None 값 키 skip / 다중 음수 min / custom default override / 7키 개별 인식

### (b) `compute_portfolio_risk_snapshot(strategies, *, net_asset, hard_stop_pcts, sector_of)` — 17 케이스
리스크 프록시 = buy_price×quantity×|pct|/100 (int). 결정론 시나리오(수치 고정):
- donchian(-9.0): 005930 10,000×10 + 000660 20,000×5 / vcp(-7.0): 035720 5,000×20 / kojiro(-8.0): 051910 40,000×2 / momentum: 0 포지션
- 섹터: 005930·000660 → 반도체(합산) / 035720 → 미분류-035720(독립) / 051910 → 에너지화학

기대값: total_notional=380,000 / total_open_risk=31,400 / concurrent=4 / open_risk_pct_of_net=**3.14**(round 2) / top_sector=반도체 risk 18,000 share **57.32%**.
- by_strategy 0 포함(momentum 0 dict) / hard_stop_pcts 결측 전략 default -7.0 / by_sector 동일섹터 합산 + 미분류 독립 / sector_of 결측 ticker → 미분류-{ticker} / top_sector None(포지션 0) / net_asset 0·음수 → pct 0.0 / 빈 strategies 0 스냅샷 / 전 전략 0 포지션 0 스냅샷 / 필드 결손 포지션 skip graceful / state 미보유 스텁 getattr 방어 / **배제 0 (입력 positions·sector_of·hard_stop_pcts 무변경 2 케이스)**

### (c) 라우트 — 4 케이스
`src.routes.portfolio.get_portfolio_risk() -> ApiResponse`. success=true + data 스냅샷 7키 존재 / get_balance 실패 → net_asset=0 200 graceful / stock_master 실패 → 섹터 미분류 폴백 200 / 빈 registry → 0 스냅샷 200. **라우트 함수 직접 await(TestClient 금지, 사이클 127).**

### (d) log_analysis — 2 케이스
metrics dict 에 `portfolio_risk_snapshot` 키 + 기존 키 병존 / 스냅샷 빌드 예외 시 키 None + 리포트 INSERT 보존.

### (e)(f) AST 격리 + import sanity — 8 케이스
8영역(risk/order_engine/strategy_registry/scanner/session/api·order/realtime/*/auth/*)에 portfolio_risk 참조 0 / portfolio_risk.py 소스 registry·kojiro·db·http import 0 + _kojiro_sector_key·trading_scheduler 토큰 0 / routes.portfolio·log_analysis 순환 없이 로드 + _kojiro_sector_key 재사용.

## Red 실행 결과 (2026-08-02)

```
40 failed, 3 passed in 0.51s
```

**FAIL 40 = 전부 의도된 미구현.**
- ImportError: `src.engine.portfolio_risk` 모듈 부재 → (a)(b) 전량 + AST 순수성/module_exists
- ImportError: `src.routes.portfolio` 모듈 부재 → (c) 전량 + import sanity 라우트 로드
- AttributeError/assert: `log_analysis_engine._build_portfolio_risk_snapshot` 헬퍼 부재 + metrics 키 미주입 → (d) + import sanity 헬퍼 존재

**PASS 3 = Red/Green 양쪽 유지되는 영구 가드** (behavior-under-test 아님):
- `TestEightAreaIsolation::test_no_portfolio_risk_import_or_reference_in_eight_areas` (지금도 8영역 참조 0)
- `TestEightAreaIsolation::test_strategy_registry_no_portfolio_risk_method` (registry 참조 0)
- `TestImportSanity::test_kojiro_sector_key_importable` (kojiro 섹터 정본 이미 존재)

기존 스위트 회귀 0 — `tests/unit/{engine,routes,ast}` 2,982 케이스 collection 정상(신규 포함).

## backend-dev 구현 주의점

1. **신규 순수함수 모듈** `src/engine/portfolio_risk.py`:
   - `extract_hard_stop_pct(params: dict | None, *, default: float = -7.0) -> float` — 7키 음수만 min, 후보 0건/None → default. `_normalize_stop_loss_rate`(recommendation_metrics) 는 결측→0.0 이라 **재사용 금지**(동형 신규, docstring 선례 명시).
   - `compute_portfolio_risk_snapshot(strategies, *, net_asset, hard_stop_pcts, sector_of) -> dict` — 반환 7키(total_notional_won / total_open_risk_won / open_risk_pct_of_net / concurrent_positions / by_strategy / by_sector / top_sector). **리스크 프록시 int 변환**은 명세 "int 반올림" — 테스트 수치는 정확히 나누어떨어지므로 `int(round(...))` / `round(...)` / 정수나눗셈 어느 쪽도 통과(경계 반올림 미검증). round 정책만 by_strategy·by_sector·total 에 일관 적용.
   - `open_risk_pct_of_net` = net_asset>0 → `round(risk/net*100, 2)`, 아니면 0.0. `top_sector.risk_share_pct` = `round(risk_won/total_open_risk_won*100, 2)`.
   - `state.positions` 접근 `getattr(strat, "state", None)` → `getattr(state, "positions", {})` 2단 방어(사이클 56-D). 포지션 buy_price/quantity None·비수치 → skip continue(graceful).
   - **8영역·registry·kojiro·db·http import 절대 금지** (AST 가드). sector_of 는 호출자가 주입.

2. **라우트** `src/routes/portfolio.py`:
   - 테스트가 monkeypatch 하는 **module-level 이름**: `get_balance`(from src.api.balance), `trading_scheduler`(from src.engine.scheduler), `stock_master`(import src.db.stock_master as ...). 이 3개를 module-level 로 import 해야 monkeypatch 적중.
   - hard_stop 추출 소스: 명세는 `s.params` 로 적었으나 실물 `StrategyBase` 는 `.config.params`. **`getattr(s, "params", None) or getattr(getattr(s, "config", None), "params", {})`** 폴백 권장(테스트 fake 는 양쪽 노출). 안전하게 `s.config.params` 우선.
   - sector_of 빌드: 보유 ticker 합집합 → `await stock_master.get(ticker)` → master_raw → `_kojiro_sector_key(master_raw, ticker)`. get 실패/None → `_kojiro_sector_key(None, ticker)` = 미분류-{ticker} 폴백(전체 try/except).
   - graceful: get_balance 실패 → net_asset=0 로 진행 + **200**. 500 금지. `main.py` include_router + `routes/CLAUDE.md` 카탈로그 갱신.

3. **log_analysis_engine**:
   - async 헬퍼 `_build_portfolio_risk_snapshot(_now_kst=None) -> dict | None` 신규(get_balance + registry + extract + sector_of + compute 조립).
   - `generate_daily_log_report` 가 이를 **try/except 로 감싸** metrics["portfolio_risk_snapshot"] 주입(예외 → None). 실패해도 insert_log_report 보존(사이클 88 G-REJECT). 정산 경로에서 `[portfolio_risk] open_risk_won=.. pct_of_net=.. positions=.. top_sector=..` 1행 emit(hot path 발화 금지).

4. **PARAM_RANGES 미편입** — default -7.0 등 정체성 상수(사이클 198/208/209/212 선례).

## 사이클 종료 시 (Green 확인 후)
- `python tools/test_impact/build_index.py` 재실행 + 신규 4 파일 ↔ portfolio_risk.py / routes/portfolio.py / log_analysis_engine.py 매핑 반영. 동적 seam(라우트 monkeypatch·헬퍼)은 필요 시 `manual_overrides.yaml` 보강.
