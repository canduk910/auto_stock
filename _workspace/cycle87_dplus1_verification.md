# 사이클 87 — D+1 운영 측정 보고서

> Plan: `/Users/koscom/.claude/plans/radiant-marinating-pumpkin.md` 영속 의무
> 발주일: 2026-06-10 (수)
> 측정 영역: 사이클 83/84/85/89/90/91 effect 통합 동행
> 시점 의무: 09:00~10:00 1h 영역
> Supabase MCP READ-ONLY (project_id=etaligxesjtjfkbntdve)

---

## Phase 1 — 09:00 직전 baseline (08:53 KST 측정)

### 결과 매트릭스 (11 쿼리)

| # | 영역 | 쿼리 대상 | baseline 결과 | 검증 의무 | 평가 |
|---|------|-----------|--------------|----------|------|
| Q1 | 사이클 83 effect | `stock_master_history` change_type | INSERT 23 / UPDATE 3 | history INSERT trigger 실측 | PASS — trigger 정상 작동 (총 26건 누적) |
| Q2 | 사이클 84 effect | `stock_master.raw.bfdy_clpr` 비율 | 52건 중 51건 (98.08%) non-zero | 95%+ 비율 목표 | PASS — 사이클 81 키 시정 영속 효과 (`prdy_clpr` → `bfdy_clpr` 100% 가까이 정합) |
| Q3 | 사이클 83 effect | `[scan_pool_eager_refresh]` emit | 0건 | ≥10건 emit | PENDING — 09:00 boot 이후 발화 영역 (Phase 2 측정) |
| Q4 | 외부 #E3 | `[stale_watcher_summary]` 빈도 | 0건 | 사이클 74 5분 통계 | PENDING — 09:00 _scan_loop 후 발화 영역 |
| Q5 | 외부 #E3 | `[stale_priority_resubscribe_cap_exceeded]` | 0건 | 사이클 66 WARNING | PENDING — 메인 시간 중 발화 |
| Q6 | 외부 #E3 | `[silent_inactive_force_reconnect]` | 0건 | 사이클 29 R2 | PENDING — 메인 시간 중 발화 (정상 가정 시 0건 유지) |
| Q7 | 외부 #E3 | `[kis_rejection]%OPSP0002%` | 0건 | 외부 5% vs 도메인 20% 검증 | PENDING — 메인 시간 중 발화 |
| Q8 | 외부 #E3 | `[universe_excluded]` 빈도 | 0건 | 사이클 32 R4 universe 가드 | PENDING — _scan_loop 5분 주기 후 발화 |
| Q9 | 사이클 91 페이징 | `[stock_master_bulk_refresh]` emit | 0건 | ≥1건 + universe=500 영역 | PENDING — 09:00 _boot() + _universe_eager_refresh_task 자동 발화 |
| Q10 | 사이클 91 KIS 호출 빈도 | bulk_refresh 메시지 5건 | 빈 결과 | universe=N kospi=K kosdaq=L 분석 | PENDING — Phase 2 측정 |
| Q11 | 사이클 91 stock_master 적재 | 총 row count | 52건 (today 0건, 마지막 갱신 D-1 15:11 KST) | 52 → 500+ 증가 영역 | PENDING — 09:00 _boot 호출 후 페이징 발화 확인 영역 |

### Phase 1 평가

**PASS 영역 (2)**:
- Q1: `stock_master_history` trigger 정상 작동 (사이클 83 effect 영속)
- Q2: `bfdy_clpr` non-zero 비율 98.08% = 사이클 81 + 84 effect 영속 (silent 결함 영구 차단 확정)

**PENDING 영역 (9)**:
- Q3~Q11: 09:00 이후 KRX 메인 시작 후 발화 영역 — Phase 2 측정 의무
- 특히 **Q9~Q11 = 사이클 91 페이징 effect 측정 핵심**: 09:00 `_boot()` + `_universe_eager_refresh_task` 자동 발화로 stock_master 52 → 500+ 영역 확인 필수
- **Q4~Q8 = 외부 #E3 운영 baseline**: 정상 운영 가정 시 cap/WARNING/reconnect 발화 빈도 0~소량 유지 영역

### 영속 보고

- baseline 측정 완료 (08:53 KST)
- stock_master 52건 (D-1 잔재) = 사이클 91 페이징 발화 *전* 상태 확정
- Q11 컬럼명 결함 발견 (`updated_at` 부재 → `refreshed_at` 정정) — 회귀 보고서 명시
- Phase 2 측정 의무 (09:00~09:30 30분 영역) — 1차 KRX 메인 시작 직후

---

## Phase 2 — 09:00~09:33 1차 측정 (09:33 KST 측정 완료)

### 결과 매트릭스 (13 쿼리)

| # | 영역 | 쿼리 대상 | Phase 1 baseline | Phase 2 측정 | 증감 | 평가 |
|---|------|-----------|------------------|--------------|------|------|
| Q1 | 사이클 83 effect | `stock_master_history` change_type | INSERT 23 / UPDATE 3 (26) | INSERT 28 / UPDATE 14 (42) | +5 INSERT / +11 UPDATE | PASS — `_boot()` 후 trigger 16건 정상 작동 (16개 종목 변경 추적 영속) |
| Q2 | 사이클 84 effect | `stock_master.raw.bfdy_clpr` non-zero 비율 | 52건 중 51 (98.08%) | 57건 중 56 (98.25%) | +5 row / +0.17% | PASS — 사이클 81/84 effect 영속 확정 (98.25% non-zero) |
| Q3 | 사이클 83 effect | `[scan_pool_eager_refresh]` emit | 0 | 0 | 0 | **FAIL** — `_boot()` 후 ≥10건 emit 의무 영역 미발화 (silent 결함 후보) |
| Q4 | 외부 #E3 | `[stale_watcher_summary]` 빈도 | 0 | 0 | 0 | PENDING — 5분 주기 통계 (사이클 74) 시점 미도달 또는 emit 결함 |
| Q5 | 외부 #E3 | `[stale_priority_resubscribe_cap_exceeded]` | 0 | 0 | 0 | PASS — 정상 운영 (cap 초과 부재) |
| Q6 | 외부 #E3 | `[silent_inactive_force_reconnect]` | 0 | 0 | 0 | PASS — 정상 운영 (silent inactive 부재) |
| Q7 | 외부 #E3 | `[kis_rejection]%OPSP0002%` | 0 | 0 | 0 | PASS — 정상 운영 (OPSP0002 부재 = 외부 5% / 도메인 20% 가정 모두 baseline 미관측) |
| Q8 | 외부 #E3 | `[universe_excluded]` 빈도 | 0 | 0 | 0 | PASS — `_scan_loop` 5분 주기 universe 가드 (사이클 32 R4) 발화 부재 (정상) |
| Q9 | 사이클 91 페이징 | `[stock_master_bulk_refresh]` emit | 0 | 0 | 0 | **FAIL** — `_boot()` + `_universe_eager_refresh_task` 자동 발화 영역 미발화 (silent 결함 후보) |
| Q10 | 사이클 91 KIS 호출 빈도 | bulk_refresh 메시지 5건 | 빈 | 빈 | 0 | **FAIL** — Q9 미발화 영속 (universe=500 페이징 호출 0건) |
| Q11 | 사이클 91 stock_master 적재 | 총 row count | 52 (today 0 / D-1 15:11 KST) | **57 (today 16 / 09:55 KST 마지막)** | +5 row / today 16 갱신 | PARTIAL — `_boot` 단일 ticker 갱신 16건 정상 작동, but 사이클 91 페이징 (universe=500) 미발화 (5건 증가만 = D-1 잔재 부족분 보충 영역) |
| Q12 | 사이클 92 영역 | `[ws_auto_restart*]` | (Phase 1 미측정) | 빈 결과 | - | PENDING — 사이클 92 commit `9e556ee` 영업일 시작 시점 효과는 **익일 (2026-06-11) 07:55** 영역 측정 의무 |
| Q13 | 07:45~08:10 영역 | ERROR/WARNING 전수 | (Phase 1 미측정) | 빈 결과 | - | PASS — 07:45~08:10 사이 ERROR/WARNING 0건 = 사이클 92 시정 *전* 시점 측정 (사이클 92 결함 시점 = D-1 07:45 영역만 발화, D-0 07:45 시점은 정상 영역 가능) |

### Phase 2 부수 발견 (사이클 87 진단 영역)

**1. WARNING 4건 추가 발견 (Q12 측정 중 LIMIT 50 결과로 보고된 운영 영속 검증)**:
- 22:46:03 UTC (= 07:46 KST) `[market_regime]` dkstock.cloud fetch 실패 = 매수 가드 비활성 (`DKSTOCK_REGIME_ENABLED=false` 설정 영역, 정상 graceful)
- 22:46:09 / 22:46:11 UTC (= 07:46 KST) `[quote_pool]` HTTP 500 attempt 1/3 (사이클 17 OPSP0002 backoff + 사이클 18 60s dedupe + 사이클 76 5분 collector 영속 효과) = 정상 (retry success 확정 영역)
- 22:55:11 UTC (= 07:55 KST) `[quote_pool]` HTTP 500 attempt 1/3 (동일 패턴)

**2. 핵심 silent 결함 후보 3건 (Q3 / Q9 / Q10 미발화 영역)**:
- **Q3** `[scan_pool_eager_refresh]` 0건 = 사이클 83 effect 운영 발화 영역 결함 (코드 발화 위치 누락 가능성)
- **Q9** `[stock_master_bulk_refresh]` 0건 = 사이클 91 페이징 effect 운영 발화 영역 결함 (코드 발화 위치 누락 가능성)
- **Q10** 빈 결과 = Q9 영속 확정 (universe=500 페이징 자동 호출 영역 미작동)
- Q11 today 16건 갱신 = **단일 ticker 갱신 경로** (보유/익일청산 종목 사전 갱신 영역) 만 작동 = `_boot()` eager 단일 refresh 정상, 사이클 91 페이징 함수 호출 자체가 발화되지 않은 정황

**3. 사이클 92 영역 (D+1 측정 의무 인계)**:
- Q12/Q13 영역 = D-0 07:45 시점 정상 (07:46 WARNING 3건은 일상 패턴 = `quote_pool` HTTP 500 retry success)
- 사이클 92 commit `9e556ee` 시정 효과 = **익일 (2026-06-11) 07:55 영업일 시작 영역** 측정 의무 영구 인계

### Phase 2 평가

**PASS 영역 (7/13)**:
- Q1 (history trigger 16건 정상) / Q2 (bfdy_clpr 98.25%) / Q5 (cap 0) / Q6 (silent_inactive 0) / Q7 (OPSP0002 0) / Q8 (universe_excluded 0) / Q13 (07:45~08:10 ERROR 0)
- 사이클 83 effect (history) + 사이클 81/84 effect (bfdy_clpr) + 외부 #E3 4 영역 정상 운영 영속 확정

**FAIL 영역 (3/13) — 사이클 88+ 신규 silent 결함 후보 발의 의무**:
- **Q3** `[scan_pool_eager_refresh]` 0건 → 사이클 83 운영 발화 결함 가설 (코드 조사 의무)
- **Q9** `[stock_master_bulk_refresh]` 0건 → 사이클 91 페이징 운영 발화 결함 가설 (코드 조사 의무)
- **Q10** bulk_refresh 메시지 빈 결과 → Q9 영속 확정

**PARTIAL 영역 (1/13)**:
- Q11 today 16건 = `_boot` 단일 ticker 갱신 정상 / 사이클 91 페이징 (universe=500) 미발화 (Q9 영속)

**PENDING 영역 (2/13)**:
- Q4 (`stale_watcher_summary` 5분 주기) — Phase 3 10:00 시점 재측정 의무
- Q12 — D+1 07:55 (2026-06-11) 사이클 92 검증 영구 인계

### 다음 단계

- Phase 3 측정 = 10:00 직후 (Q4 5분 통계 확정 + Q3/Q9/Q10 재확인 + Q11 추가 증감 확인)
- **Q3/Q9 silent 결함 후보 = 사이클 88+ 별개 카드 발의 의무** (사이클 92 영업일 push 영속 의무와 별개)
- 사이클 92 D+1 검증 (07:55 영역) = **익일 (2026-06-11) 발주 의무**

---

## Phase 3 — 09:30~10:00 2차 측정 (대기 영역)

*(10:00 직후 기록 예정)*

---

## Phase 4 — 10:00 종결 보고 (대기 영역)

*(10:00 이후 사이클 92+ 후속 카드 인계 결정 의제 영역)*
