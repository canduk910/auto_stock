# Red 명세 — 사이클 104: Playwright E2E 신규 페이지 검증

**작성일**: 2026-06-11  
**담당**: frontend-dev  
**상태**: Phase 3 Red 명세 완료

---

## 배경

사이클 103 신규 2 페이지 (`/realtime-health`, `/strategies`) 가 단위 테스트(vitest 18 PASS) 영속 완료됨.
사이클 86 패턴 답습 (stock-master.spec.ts) = Playwright e2e 통합 검증 단계.

---

## 회귀 가드 케이스 매트릭스

### HIGH 8 케이스

| ID | 파일 | 케이스 |
|----|------|--------|
| H-RH1 | realtime-health.spec.ts | 4 카드 testid 렌더 visible |
| H-RH2 | realtime-health.spec.ts | 빈 데이터 graceful ("데이터 없음" / "0건 — 정상") |
| H-RH3 | realtime-health.spec.ts | api-mocks ECONNREFUSED 0건 (LIFO 정합 영속) |
| H-RH4 | realtime-health.spec.ts | 페이지 제목 "실시간 건강 모니터링" visible |
| H-ST1 | strategies.spec.ts | 6 전략 카드 testid 렌더 visible |
| H-ST2 | strategies.spec.ts | 4 임계 한글 라벨 visible (손절 임계 / 일일 손실 한도 / 트레일링 임계 / 종목당 비율) |
| H-ST3 | strategies.spec.ts | api-mocks ECONNREFUSED 0건 (LIFO 정합 영속) |
| H-ST4 | strategies.spec.ts | 페이지 제목 "전략 현황" visible |

### MEDIUM 3 케이스

| ID | 파일 | 케이스 |
|----|------|--------|
| M-RH5 | realtime-health.spec.ts | 시간 윈도우 토글 (24h / 7d) 버튼 visible |
| M-ST5 | strategies.spec.ts | momentum 손절 임계 값 렌더 (mock -7.5%) |
| M-MOB | strategies.spec.ts | 모바일 viewport 375px 햄버거 9개 메뉴 (실시간 상태 + 전략 현황 포함) |

### LOW 2 케이스

| ID | 파일 | 케이스 |
|----|------|--------|
| L-NAV1 | realtime-health.spec.ts | PC 메뉴 "실시간 상태" 링크 클릭 → /realtime-health URL |
| L-NAV2 | strategies.spec.ts | PC 메뉴 "전략 현황" 링크 클릭 → /strategies URL |

---

## api-mocks.ts 영역 확인

- `**/api/logs/search*` — 사이클 103 영역 영속 (실시간 건강 4 prefix grep)
- `**/api/strategies` (GET) — 사이클 103 영역 영속 (전략 현황 mock, strategies dict 형식)
- LIFO 정합: 모든 신규 라우트가 기존 wildcard 후 등록 영속

---

## 영속 의무

- 사이클 80 hotfix #3/#4 Playwright LIFO 정합 영속
- 사이클 86 답습 (stock-master.spec.ts 패턴 100% 답습)
- 사이클 89 한글 친숙 용어 영속 ("손절 임계" / "실시간 건강 모니터링")
- 사이클 81 G-MOBILE-7 → G-MOBILE-9 갱신 영속 (9개 메뉴)

---

## 산출물

1. `e2e/realtime-health.spec.ts` 신규
2. `e2e/strategies.spec.ts` 신규
3. (api-mocks.ts 변경 없음 — 사이클 103 영역 이미 등록 영속 확인)
