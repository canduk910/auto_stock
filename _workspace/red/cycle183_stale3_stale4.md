# 사이클 183 Red — stale-3 (KST 강제) + stale-4 (60s TTL 캐시 우회)

작성: tdd-engineer (Red 단계). production 미변경. Green = backend-dev.
대상: `src/engine/scanner.py` 단독. **매매 행위 변경 0** (stale-3 = 표시 문자열 / stale-4 = DB read 횟수, 필터 결과 보존).

## 테스트 파일

- 행위: `tests/unit/engine/scanner/test_cycle183_stale3_stale4.py` (8 케이스)
- AST: `tests/unit/ast/test_cycle183_stale3_stale4_ast.py` (3 케이스)
- 합계 **11 케이스** = 현재 FAIL 6 (Red) + PASS 보존 5 (회귀 가드)

---

## 결함 1 (stale-3, LOW — KST 강제 위반)

`scanner.py:681` `_last_scan_time = datetime.now().strftime("%H:%M:%S")` — naive `datetime.now()` (서버 로컬).
바로 아랫줄 L685 `scan_filter_stats["last_run_at"] = datetime.now(KST_TZ).isoformat()` 은 이미 KST → **불일치**.
`_last_scan_time` → `get_scan_status()` 응답 `last_scan_time` (L726) 표시용. CLAUDE.md "모든 시각 데이터 KST 강제" 위반.

**Green 목표**: `datetime.now(KST_TZ).strftime("%H:%M:%S")` (`KST_TZ` = scanner.py:32 기정의). 1줄.

| 가드 | 종류 | 현재 결과 | 근거 |
|------|------|----------|------|
| `test_stale3_last_scan_time_uses_kst_wallclock` | 행위 (freezegun) | **FAIL** | `freeze_time("2024-06-20 00:30:00")` (UTC) = KST 09:30. `fetch_rising_stocks→[]` mock 후 `scan_stocks()` → `_last_scan_time == "09:30:00"` 단언. 현재 naive → 실제 `'00:30:00'` |
| `test_AST3a_last_scan_time_assignment_now_has_tz_arg` | AST | **FAIL** | `_last_scan_time` 할당 RHS 의 `datetime.now(...)` Call 인자 ≥1 의무. 현재 0-arg (L681) |
| `test_AST3b_no_zero_arg_naive_datetime_now_in_module` | AST | **FAIL** | 모듈 전역 0-arg `datetime.now()` Call 0건 의무. 현재 L681 1건 (L220/409/541/685/712 는 KST_TZ/kst 동반 = 제외) |

- 고정 연도 **2024** (사이클 176 날짜 의존 교훈). freezegun 검증: naive now() → "00:30:00" / `datetime.now(KST_TZ)` → "09:30:00" (직접 확인).
- AST = 노드 검사 (Call.args 길이), source 텍스트 스캔 아님 (사이클 167/179 false-positive 교훈).

---

## 결함 2 (stale-4, LOW — 60s TTL 캐시 우회)

`scanner._apply_price_filter` (L136~) L152 `pf = await get_price_filter()` 직접 호출 → 60s TTL 캐시
(`_get_price_filter_for_scanner`, L101) **우회**. `subscribe_filtered_stocks` 가 `_apply_price_filter` 를
tickers(L992) + extra_tickers(L994) [+ priority_groups for-loop(L998, 최대 3키)] 로 호출 →
scan 당 `get_price_filter()` DB read 최대 ~2~5×. L151 오인 주석("subscribe_filtered_stocks 는 별도 최적화")은 stale.

**Green 목표**: L152 `get_price_filter()` → `_get_price_filter_for_scanner()` (캐시 경유). L151 오인 주석 정정/제거.
**정합성 보존**: PUT 즉시 무효화는 `invalidate_price_filter_cache_scanner()` (L113, 사이클 64/148 PUT hook) 가 이미 담당 → scanner↔prepare 정합 + 즉시 반영 영속.

| 가드 | 종류 | 현재 결과 | 근거 |
|------|------|----------|------|
| `test_PERF1_apply_price_filter_cache_within_60s_single_db_read` | 행위 | **FAIL** | 60s 내 `_apply_price_filter` 2회 → `patch("src.engine.scanner.get_price_filter")` call_count == 1 단언. 현재 직접 호출 = 2건 |
| `test_PERF2_subscribe_one_scan_at_most_one_get_price_filter` | 행위(통합) | **FAIL** | `subscribe_filtered_stocks(tickers=2, extra=2)` 1 scan → `get_price_filter` ≤1회 단언. 현재 tickers+extra = 2건 (live priority_groups 경로는 ~4~5) |
| `test_AST4_apply_price_filter_uses_cached_helper_not_direct` | AST | **FAIL** | `_apply_price_filter` 함수 본문 한정 — `_get_price_filter_for_scanner` 호출 ≥1 + `get_price_filter` 직접 호출 0건. 현재 직접 `get_price_filter()` |
| `test_CORRECT1_invalidate_forces_refetch_immediate_reflection` | 행위 | **PASS 보존** | warm → reset_mock → invalidate → apply → DB 재조회 ≥1. 현재/Green 모두 PASS (즉시 반영 영속 가드) |
| `test_CORRECT2a_protected_ticker_early_return_unchanged` | 행위 | **PASS 보존** | 보유 종목 above_max 라도 early-return 통과 (사이클 32 R4 / 64 Q1-D) |
| `test_CORRECT2b_min_max_block_unchanged` | 행위 | **PASS 보존** | below_min/above_max 차단 + skip emit 2행 불변 |
| `test_CORRECT2c_inactive_passthrough_unchanged` | 행위 | **PASS 보존** | 비활성(0/0) → 전체 통과 + stock_master 조회 0 |
| `test_CORRECT2d_bfdy_clpr_miss_graceful_unchanged` | 행위 | **PASS 보존** | bfdy_clpr 미확보(miss/빈 raw) → graceful 통과 (신규상장 영구차단 방지) |

- PERF-2 는 priority_groups=None (tickers+extra) 단순 경로 = 안정적 2 vs 1 갭. live 경로는 ~4~5 (memo 명시).
- 캐시는 **같은 PriceFilter** 반환 → CORRECT-2 결과 불변 (production 회귀 0).

---

## cycle64 캐시 격리 영향 (★ Green 단계 backend-dev 필수 조치)

stale-4 Green 전환 후 `_apply_price_filter` 가 모듈 전역 `_price_filter_cache` 를 읽음 →
**캐시 미격리 기존 테스트는 직전 테스트가 채운 캐시를 hit** 해 patch 미적용 → 오염.
아래 파일은 `_apply_price_filter` 를 런타임 호출 + `scanner.get_price_filter` patch + **setup 무효화 부재** →
**각 fixture/setup 에 `scanner.invalidate_price_filter_cache_scanner()` 추가 의무** (autouse fixture before+after 권장).

| 파일 | 영향 케이스 | 현 격리 상태 | Green 조치 |
|------|------------|-------------|-----------|
| `tests/unit/engine/test_cycle64_price_filter_scanner_apply.py` | B-1~B-5 (5) | autouse 없음 | autouse invalidate fixture 신규 추가 |
| `tests/unit/engine/test_cycle64_price_filter_scanner_protected.py` | C-1, C-2, C-3 (3) | autouse 없음 | autouse invalidate fixture 신규 추가 |
| `tests/unit/engine/test_cycle64_price_filter_scanner_emit_cap.py` | E-1 (1) | autouse 없음 | autouse invalidate fixture 신규 추가 |
| `tests/unit/engine/scanner/test_cycle81_price_filter_key_fix.py` | A-1,A-2,B-1~3,C-1,C-2,D-1,E-1,E-2 (10) | autouse `_reset_cycle81_scanner_state` 존재 (DailyEmitCap 만 reset) | 기존 fixture 에 `invalidate_price_filter_cache_scanner()` 1줄 추가 |
| `tests/unit/engine/scanner/test_cycle81_real_data_regression.py` | G-1 (1) | 격리 없음 | setup invalidate 또는 autouse fixture 추가 |

**영향 받지 않음 (격리 이미 존재 / 캐시 경로 무관)**:
- `test_cycle64_price_filter_scanner_integration.py` (F-1~F-4) — setup invalidate 보유
- `test_cycle64_price_filter_scanner_cache.py` (D-1, D-2) — `_get_price_filter_for_scanner` 직접 테스트, invalidate 보유
- `test_cycle64_price_filter_scanner_daily_summary.py` (H-1) — `emit_*` → `_get_price_filter_for_scanner` (이미 캐시 경로), stale-4 변경 무관 + cycle183 autouse 가 캐시 청소
- `test_cycle65_trade_amount_filter_e2e.py` — autouse invalidate 보유
- `test_cycle83_r6_frequency_regression.py` / `test_cycle83_sk_square_fixture.py` — invalidate 보유
- `test_cycle89_bfdy_clpr_persistence.py` — `inspect.getsource` 소스 검사만 (런타임 호출 0). Green 후에도 `bfdy_clpr` 존재 / `prdy_clpr` 부재 불변 → PASS
- `test_cycle157_master_block_hook_and_vcp_listfilter.py` — `src.db.system_config.get_price_filter` patch + 전략 `_apply_price_filter_in_prepare` (scanner `_apply_price_filter` 무관)
- `tests/unit/ast/test_cycle81_ast_price_filter_key.py` — AST 소스 검사 (런타임 무관)

### 의미 전환 건수 = **0**

영향 케이스 전수 검토 결과 `get_price_filter` **call_count 를 정확히 N회 단언하는 테스트 없음**
(모두 필터 *결과*/emit 로그 단언 → 캐시는 동일 PriceFilter 반환하므로 결과 불변). 따라서 xfail/단언 갱신 의미 전환 0건.
- F-2 (integration) `db_get_mock.call_count == 2` 단언 = 두 apply 호출 **사이에 invalidate** 존재 → Green 후에도 2 (불변, PASS).
- cycle81 E-2 동일 ticker 2회 호출 = **동일 pf** → 캐시 hit 무관, DailyEmitCap 단언(1) 불변 (PASS).

---

## 현재 FAIL 근거 (실측)

```
6 failed, 5 passed (cycle183 단독)
- stale3: assert '00:30:00' == '09:30:00'
- PERF1:  call_count 실제 2건 (캐시 우회)
- PERF2:  call_count 실제 2건 (tickers + extra 직접)
- AST3a/3b/AST4: 0-arg now() / 직접 get_price_filter 검출
```

## baseline PASS 수 (current production, Green 전후 비교용)

| 그룹 | baseline PASS |
|------|--------------|
| `tests/unit/engine/test_cycle64_*` | **18** |
| `test_cycle81_price_filter_key_fix.py` + `test_cycle81_real_data_regression.py` | **11** |
| `test_cycle64_*_integration.py` + `test_cycle65_*_e2e.py` | **8** |
| cycle183 신규 (행위 8 + AST 3) | 6 FAIL + 5 PASS |
| 조합 실행 (cycle183 + 영향 cycle64/81) | 6 FAIL + 29 PASS (기존 24 회귀 0) |

**Green 기대**: stale-3/4 production 2줄(+주석 정정) → cycle183 6 FAIL → PASS 전환. 영향 5 파일 격리 추가 시 cycle64-18 / cycle81-11 baseline 유지(회귀 0).

## SAFETY (매매 안전성 무영향)

- stale-3 = `get_scan_status().last_scan_time` 표시 문자열만. risk/order_engine/realtime/auth/strategies diff 0.
- stale-4 = scanner 매수 진입 *전* 가격 필터 DB read 횟수 (사이클 38 명문화). 필터 결과/구독 집합 불변 (CORRECT-2). 보유 절대 보호(사이클 32 R4) 회귀 0. invalidate PUT hook(사이클 64/148) 영속.
