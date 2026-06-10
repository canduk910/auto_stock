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

## Phase 2 — 09:00~09:30 1차 측정 (대기 영역)

*(09:30 직후 기록 예정)*

---

## Phase 3 — 09:30~10:00 2차 측정 (대기 영역)

*(10:00 직후 기록 예정)*

---

## Phase 4 — 10:00 종결 보고 (대기 영역)

*(10:00 이후 사이클 92+ 후속 카드 인계 결정 의제 영역)*
