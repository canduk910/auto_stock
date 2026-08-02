# 사이클 F (TE/RR 전략 지표) 백엔드 통합·안전성·실측 검증 리포트

작성: tester · 2026-08-02
대상: `src/engine/te_metrics.py`(신규, working tree) + `src/routes/strategies.py::get_strategies_te`(수정, working tree)
명세: `_workspace/red/_behaviors_cycleF_te_rr_20260802.md` (F-B1~F-B9)
자문: `_workspace/domain_consult/cycle_te_expectancy_dashboard_20260802.md`

배포 상태: EC2 커밋 `c54ce96` = 로컬 HEAD 동일 → `get_trade_pairs` 배포됨, `compute_te_rr` 미배포 → 실측은 compute_te_rr 로직을 1:1 인라인 재현하여 배포된 `get_trade_pairs` 실데이터로 컨테이너 내부 실행.

---

## 항목별 판정 요약

| # | 검증 항목 | 판정 |
|---|-----------|------|
| 1 | 엔드포인트 end-to-end (7전략 리스트·months→window·5분 캐시·예외격리·19필드) | **PASS** (23 GREEN) |
| 2 | EC2 실측 vs team-leader 인라인 | **PASS** (전 전략 정확 일치) |
| 3 | 동치 verdict 부호 == (RR>필요RR) | **PASS** (게이트 통과 3전략 전부) |
| 4 | 매매 안전성 8영역 diff 0 + read-only | **PASS** (변경 파일 0) |
| 5 | 장중 DB 부하 (전용 엔드포인트+5분 캐시) | **PASS** (경미 관찰 1건) |
| 6 | 전체 백엔드 무회귀 | **PASS** (4095 passed, 0 failed) |

**결함: 없음.** 관찰 사항 2건 + 참고 1건(하단).

---

## 1번 — 엔드포인트 end-to-end

`tests/unit/routes/test_cycleF_te_endpoint.py` 4케이스 + `tests/unit/engine/test_cycleF_te_rr_metrics.py` 19케이스 = **23 GREEN** (0.37s).

- 7전략 리스트 반환 + 19필드 asdict 정합 (`test_te_endpoint_returns_all_seven_strategies`)
- 5분(300s) TTL 캐시: monotonic mock 으로 2회 호출 시 get_trade_pairs 1회, TTL 경과 후 재조회 (`test_te_endpoint_5min_cache_skips_db`)
- months→window_days=months×30 (3→90 / 6→180) + 캐시 키 분리 (`test_te_endpoint_months_maps_window_and_separates_cache_key`)
- 전략별 예외 격리: 1전략 실패 → 빈 디폴트(n=0/undecided), 나머지 정상 (`test_te_endpoint_isolates_per_strategy_exception`)

라우트 함수 직접 await 호출(TestClient 미사용) — 사이클 127 anyio portal hang 차단 준수.

## 2번 — EC2 실측 전략별 TE/RR/표본 명단

측정: 2026-08-02 14:40 KST, window_days=90 (months=3).

| 전략 | N | 승/패/보합 | 승률 | TE% | TE₩평균 | 3개월실현₩ | RR | 필요RR | rr_margin | rr_available | sample_tier | verdict | structure | team-lead 인라인 대조 |
|------|---|-----------|------|-----|---------|-----------|-----|--------|-----------|:---:|-----------|---------|-----------|----------------------|
| momentum | 36 | 10/25/1 | 27.8% | **+0.820** | +1,035 | +37,265 | **3.230** | 2.500 | +0.730 | ✓ | low | superior | robust | N36 +0.82 RR3.23 필요2.50 ✓ 일치 |
| volatility_breakout | 65 | 23/42/0 | 35.4% | **−0.629** | −2,634 | −171,205 | **1.354** | 1.826 | −0.472 | ✓ | normal | inferior | robust | N65 −0.63 RR1.35 필요1.83 열위 ✓ 일치 |
| long_tail_volatility | 42 | 20/22/0 | 47.6% | **+1.050** | +732 | +30,730 | 1.720 | 1.100 | +0.620 | ✓ | low | superior | robust | N42 +1.05 ✓ 일치 |
| donchian_swing | 9 | 1/8/0 | 11.1% | −4.419 | −3,244 | −29,200 | None | 8.000 | None | ✗ | insufficient | undecided | None | N9 표본부족 ✓ 일치 |
| bull_flag_breakout | 0 | 0/0/0 | — | 0.0 | 0 | 0 | None | None | None | ✗ | insufficient | undecided | None | N0 ✓ 일치 |
| vcp_breakout | 0 | 0/0/0 | — | 0.0 | 0 | 0 | None | None | None | ✗ | insufficient | undecided | None | N0 ✓ 일치 |
| kojiro | 3 | 0/3/0 | 0% | −7.070 | −2,777 | −8,330 | None | None | None | ✗ | insufficient | undecided | None | N3 표본부족 ✓ 일치 |

### 표본 게이트 실적용 명단

- **sample_tier=normal (N≥50)**: volatility_breakout(65) 단독
- **sample_tier=low (20≤N<50)**: momentum(36), long_tail_volatility(42)
- **sample_tier=insufficient (N<20)**: donchian(9), kojiro(3), BFB(0), VCP(0) → 전부 verdict=undecided 뮤트
- **RR 게이트(min(W,L)≥5) 통과 = rr_available=True**: momentum(min10), VB(min23), LTV(min20) 3전략만
  - donchian: min(1,8)=1<5 → rr=None (필요RR=8.0 은 W>0 이라 계산되나 미사용)
  - kojiro/BFB/VCP: W=0 또는 표본 0 → 필요RR None, rr_available=False

## 3번 — 동치 검증

게이트 통과 3전략(verdict decided) 전부 `sign(te_pct) == sign(rr_margin)` 성립 → **TE>0 ⟺ RR>필요RR 동치가 실데이터에서 확증**:

- momentum: TE +0.820 / margin +0.730 (RR 3.230 > 필요 2.500) → 둘 다 양수 → superior 일치
- VB: TE −0.629 / margin −0.472 (RR 1.354 < 필요 1.826) → 둘 다 음수 → inferior 일치
- LTV: TE +1.050 / margin +0.620 (RR 1.720 > 필요 1.100) → 둘 다 양수 → superior 일치

경계 TE≈0 케이스: 합성 회귀 `test_te_rr_equivalence_including_boundary`(10승+10패+보합1=N21, RR==필요RR, margin=0, verdict=flat) GREEN.
insufficient 표본(donchian/kojiro)은 TE 부호 무관 verdict=undecided 로 정상 게이트.

## 4번 — 매매 안전성

`git diff HEAD -- src/engine/risk.py order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/scheduler.py` = **0** (변경 파일 자체 없음, working tree status 미등장).
`get_trade_pairs` = `SELECT ... WHERE status=ANY` read-only (쓰기·주문·손절 경로 무접촉).
사이클 F 변경 파일 = te_metrics.py(신규) + routes/strategies.py(수정) + 테스트 2개 뿐. 8영역 diff 0 재확인.

## 5번 — 장중 DB 부하

전용 `GET /api/strategies/te` + 300s TTL `time.monotonic` 프로세스 캐시(months 키 분리). 60s 폴링 `/api/strategies` 와 분리 → 캐시 미스 시에만 7전략 × get_trade_pairs 1회 = 최대 7쿼리/5분(≈1.4쿼리/분). KRX 메인시간 반복조회 부하를 캐시가 흡수. `invalidate_te_cache()` 격리 검증됨.

## 6번 — 전체 백엔드 무회귀

`python -m pytest -q --ignore=tests/integration` → **4095 passed, 8 skipped, 326 xfailed, 12 xpassed, 0 failed** (88.6s). 사이클 F 23케이스 포함.

---

## 발견 결함 / 관찰 사항

**결함 없음.** 백엔드는 관찰 전용 + 명세 정합.

- **관찰 1 (프론트 표현 유의)**: VB 가 `verdict=inferior` + `structure_tag=robust` 동시 표출. 명세 정합(F-B5=TE 부호 / F-B6=승률0.5·RR1.0 사분면, 서로 독립). 의미상 정합 — "돌파형(저승률·고RR 사분면) 구조이나 실현 RR 1.35 가 손익분기 필요RR 1.83 미달로 현재 열위". 자문 §262 가 예견한 "구조 태그 사분면 경계(RR1.0)와 손익분기선(필요RR) 불일치" 실제 사례. **프론트 F-FE 에서 '견고형' 배지가 '우량'으로 오독되지 않도록 verdict(열위)와 병렬 표시 권고** — 백엔드 데이터는 정상.
- **관찰 2 (경미, 장래)**: `get_trade_pairs` 는 날짜 인자 없이 전략별 trade_history 전체 이력 스캔(momentum 전체 closed 51, VB 83 수준). 현재 볼륨 무시 가능 + 5분 캐시 흡수하나, 이력 대량 누적 시 스캔 선형 증가 — 장래 sell_date 사전 필터 인계 고려.
- **참고**: donchian 은 `required_rr=8.0` 산출되나 `rr=None`(min(W,L)<5) + `sample_tier=insufficient`. 프론트 F-FE3 의 N<20 뮤트가 게이지·구조·배지 전부 숨김 → 오표시 위험 없음. 데이터 구조 건전.

## 최종 수치

- 사이클 F 테스트: **23 passed** (engine 19 + routes 4)
- 전체 백엔드(integration 제외): **4095 passed / 0 failed** (88.6s)
- 매매 안전성 8영역 diff: **0**
- EC2 실측: **7전략 전부 team-leader 인라인과 일치**

**판정: 백엔드 통합·안전성·실측 전 항목 PASS. 배포 GO. 프론트 F-FE 진행 시 관찰 1 반영 권고.**

---

## 부록 — FE↔BE 경계면 검증 (프론트 F-FE 완료 후 추가, 2026-08-02)

프론트 dev(fdev-cycleF) TE/RR 카드 구현 완료 알림 수신 후 "양쪽 동시 읽기" 경계면 교차 검증 수행.

### 타입 정합 (19필드 1:1)

`frontend/src/types/strategy.ts::TeRrMetrics` ↔ 백엔드 `src/engine/te_metrics.py::TeRrMetrics` asdict = **19필드 완전 일치** (nullability + 리터럴 union 포함):
- `avg_win_pct`/`avg_loss_pct`/`rr`/`required_rr`/`rr_margin` = `number | null` ↔ `float | None` 정합
- `sample_tier: 'insufficient'|'low'|'normal'` ↔ 백엔드 `_sample_tier` 반환 3값 정합
- `verdict: 'undecided'|'superior'|'inferior'|'flat'` ↔ 백엔드 4분기 정합
- `structure_tag: 'robust'|'fragile'|'balanced'|null` ↔ 백엔드 3값/None 정합

### URL/mock 경로 정합

- 프론트 `getStrategyTeRr(months=3)` → `apiClient.get('/strategies/te', {params:{months}})`. `apiClient.baseURL='/api'` → 최종 `/api/strategies/te?months=3` = 백엔드 라우트 **일치**
- MSW `src/test/handlers.ts`: `${base}/strategies/te` → `wrap([])` 등록
- Playwright `e2e/fixtures/api-mocks.ts:124`: `**/api/strategies/te*` (구체 라우트, 광범위 wildcard 부재로 LIFO 무영향) → `envelope([])` 등록

### 프론트/E2E 실행

- 프론트 TE/RR 카드 vitest `StrategiesTeRr.test.tsx`: **10 passed** (독립 재실행)
- E2E `e2e/strategies.spec.ts`: **9 passed** (TE 섹션 추가로 인한 strategies 페이지 회귀 없음)

### 발견 — E2E 커버리지 갭 (MEDIUM, 결함 아님)

`e2e/strategies.spec.ts` 는 신규 TE/RR testid(`te-section`/`te-verdict`/`rr-gauge`/`te-structure` 등)를 **전혀 검증하지 않음**. 프론트 dev 가 api-mock 은 등록했으나 E2E 단언 케이스는 미추가(본인도 "직접 실행 안 함" 명시). vitest(10케이스)가 렌더 로직은 커버하므로 실동작 위험은 낮으나, 표본 게이트 3분기(N<20 뮤트 / 20≤N<50 게이지 / N≥50 정상)의 실브라우저 렌더 E2E 는 미존재. **인계: strategies.spec.ts 에 te-section 3분기 렌더 E2E 추가** (frontend-dev 또는 tdd-engineer).
