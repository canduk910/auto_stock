# 사이클 103 Phase 2 명세 분해 — 운영 가시화 UI 신규 (RealtimeHealth 페이지)

**발주자**: team-leader (사이클 103 Phase 2)
**일시**: 2026-06-11 (목) KST
**위급도**: **MEDIUM** (운영자 가시화 영역 + 매매 hot path 영역 무관 + frontend 단독 시정)
**범위**: 사이클 102 신규 prefix 3 영역 + `[ws_auto_restart]` 4 영역 단일 페이지 통합 (frontend-dev 단독 사이클)
**선행**: 사이클 102 verify + 사이클 102 신규 prefix 3 영역 (`[dispatch_drop_summary]` / `[callback_exception]` / `[stale_force_retry]`) + 사이클 92 `[ws_auto_restart]` 영속
**코드 변경 (Phase 2)**: 0 (명세 단독)
**Phase 3 인계**: tdd-engineer Red 작성

---

## 1. 사용자 결정 요약 (영속)

| 의제 | 채택 | 영속 의무 |
|------|------|---------|
| **Q1** 사이클 103 진행 방향 | **운영 가시화 UI 추가** (frontend-dev 단독 시정) | 사이클 102 신규 prefix 3 영역 운영자 노출 의무 |
| **Q2** D+1 측정 시점 | **통합 측정** (사이클 104 영역 예약 = 2026-06-12 (금) 07:50~08:10 + 09:00~10:00 + 20:00~20:30 통합) | 사이클 102 + 사이클 103 효과 1회 통합 검증 |
| **Q3** Plan Phase A 자문 | **자문 생략** (LOW 위험 영역 영구 영속) | domain-expert 자문 0 |

---

## 2. team-leader 권장 Phase 2 결정 의제 (Q10~Q13)

사용자 결정 의제 4 영역 (UI 위치 / 데이터 영역 / 카드 영역 / 시간 윈도우) — Phase 3 진입 *전* 사용자 회수 의무.

### Q10: UI 영역 위치

| 옵션 | 설명 | 영속 의무 |
|------|------|---------|
| (A) | Dashboard 4 카드 추가 | 사이클 41 StrategyFunnel 답습 — Dashboard 화면 비대화 위험 |
| (B) | **신규 페이지 `/realtime-health` (8번째 메뉴)** | 사이클 85 StockMaster 단일 페이지 답습 — **권장 (영구 영속)** |
| (C) | StrategyFunnel UI 영역 흡수 | 책임 영역 혼동 위험 |
| (D) | Settings UI 영역 흡수 | 사용자 매매 설정 영역 혼동 위험 |

**team-leader 권장**: **(B) 신규 페이지** — 실시간 시세 건강 영역 = 독립적 운영자 영역, 매매 hot path 영역과 분리, 사이클 85 답습 패턴 영속.

**페이지 경로**: `/realtime-health` (사이클 85 `/stock-master` 답습)
**페이지 라벨**: `실시간 건강` (PC 메뉴 + 모바일 햄버거 Drawer)
**메뉴 순서**: `navItems` 7개 → 8개 (사이클 85 + 1)

### Q11: 데이터 영역

| 옵션 | 설명 | 영속 의무 |
|------|------|---------|
| (A) | **system_logs 직접 조회** (60s polling) | 사이클 85 StockMaster 답습 — **권장 (영구 영속)** |
| (B) | 신규 API endpoint (예: `GET /api/realtime/health-metrics`) | 백엔드 영역 신규 = 사이클 103 frontend 단독 시정 위반 |
| (C) | WebSocket 실시간 push | 신규 영역 = 사이클 103 범위 외 |

**team-leader 권장**: **(A) system_logs 직접 조회 + 60s polling** — 사이클 85 답습 영구 영속, 신규 API 영역 0 = 빠른 시정.

**활용 API**: 기존 `searchLogs({q, level, start, end, limit})` (사이클 6 `/api/logs/search` 영속)
- prefix별 grep 검색: `q=[dispatch_drop_summary]` / `q=[callback_exception]` / `q=[stale_force_retry]` / `q=[ws_auto_restart]`
- 시간 범위: 24h / 7일 토글 (Q13 채택 시)
- level 필터: INFO/WARNING/ERROR

### Q12: 카드 영역

| 옵션 | 설명 | 영속 의무 |
|------|------|---------|
| 3 카드 | `[dispatch_drop_summary]` + `[callback_exception]` + `[stale_force_retry]` 각 1 카드 | 사이클 102 영역 한정 |
| **4 카드** | 위 3 + `[ws_auto_restart]` (사이클 92 영역 영속) | **권장 (영구 영속)** — 자동 재기동 영역 가시화 |

**team-leader 권장**: **4 카드** — 사이클 92 영역 자연 인계 영속, `[ws_auto_restart]` 0건 영속 운영자 확인 의무 (KIS LMS chain 차단 안전 마진).

**4 카드 매트릭스**:

| 카드 | 데이터 영역 | 노출 메트릭 | 색상 |
|------|---------|---------|------|
| **Dispatch Drop** | `[dispatch_drop_summary]` grep | `drops_total` 카운트 + 상위 5 ticker (cap) | amber (≥1건/일 주의) |
| **Callback Exception** | `[callback_exception]` grep | 발생 카운트 + 최근 5건 (handler/ticker/order_no) | red (≥1건/일 ERROR 영역) |
| **Stale Force Retry** | `[stale_force_retry]` grep | 발생 카운트 + 상위 5 ticker | gray (정상 50~70건/일 영역) |
| **WS Auto Restart** | `[ws_auto_restart]` grep | 발생 카운트 + 최근 1건 시각 | gray (정상 0건/일, ≥1건 amber) |

### Q13: 시간 윈도우

| 옵션 | 설명 | 영속 의무 |
|------|------|---------|
| (A) | 최근 24h (1일 영역) | 단일 영역 영속 |
| (B) | 최근 7일 (1주 영역) | 추세 영역 영속 |
| (C) | **사용자 선택 토글 (24h / 7일)** | 사이클 85 답습 — **권장 (영구 영속)** |

**team-leader 권장**: **(C) 사용자 선택 토글** — 사이클 85 답습 패턴 영속, 운영자 즉시 영역 (24h) + 추세 영역 (7일) 양쪽 영속 보장.

**토글 testid**: `time-window-toggle-24h` / `time-window-toggle-7d` (사이클 85 영속 패턴)

---

## 3. Phase 3 frontend-dev Red 인계 명세

### 3-A 신규 파일 후보

| 파일 | 추정 LOC | 명세 |
|------|---------|------|
| `frontend/src/types/realtime-health.ts` | ~40L | 4 카드 데이터 타입 (`DispatchDropMetric` + `CallbackExceptionMetric` + `StaleForceRetryMetric` + `WsAutoRestartMetric` + `RealtimeHealthSummary` 통합) |
| `frontend/src/api/realtime-health.ts` | ~80L | `fetchRealtimeHealth(window: '24h'\|'7d')` 함수 — 기존 `searchLogs` 4회 호출 + parse + 통합. ApiResponse `data.data` 추출 패턴 (사이클 84 영속) |
| `frontend/src/pages/RealtimeHealth.tsx` | ~280L | 단일 페이지 4 카드 + 시간 윈도우 토글 (사이클 85 StockMaster 답습) |
| `frontend/src/App.tsx` | +5L | `navItems` 7 → 8 (`실시간 건강` / `/realtime-health`) + 라우트 + `MobileMenuLabel` 매핑 + 모바일 햄버거 Drawer 8개 |
| `frontend/src/test/handlers.ts` MSW | +30L | `searchLogs` 4 prefix mock handler 추가 (24h / 7d 양쪽) |
| `e2e/fixtures/api-mocks.ts` Playwright | +20L | wildcard `**/api/logs/search**` *전* 등록 + 4 구체 라우트 *후* 등록 (LIFO 정합 영속, 사이클 80 hotfix #3 답습) |

### 3-B 테스트 후보

| 테스트 | 위급도 | 명세 |
|------|------|------|
| `frontend/src/api/__tests__/realtime-health.test.ts` | HIGH | API 함수 단위 (4 prefix 호출 정합 + 24h/7d window + 통합 응답) |
| `frontend/src/pages/__tests__/RealtimeHealth.test.tsx` | HIGH | 4 카드 렌더 + 시간 윈도우 토글 + 60s polling + 빈 데이터 graceful + 에러 graceful |
| `frontend/src/__tests__/AppShell.test.tsx` | MEDIUM | PC 8개 메뉴 갱신 + 모바일 햄버거 Drawer 8개 갱신 + 8번째 메뉴 라우트 |
| `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts` | HIGH | `TARGET_PAGES` 확장 `RealtimeHealth.tsx` 추가 (사이클 65 H3 + 사이클 75 G-RT3 + 사이클 80 hotfix #1 + 사이클 85 G-AST-RT 답습) |
| `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts` | HIGH | `REQUIRED_REALTIME_HEALTH_ENDPOINTS` literal 추가 + `it.each` + `isRouteRegistered` 검증 (사이클 75 G-AST5 + 사이클 85 G-AST-MOCK 답습) |
| `tests/unit/e2e_mocks/test_cycle103_api_mocks_realtime_health_lifo.py` | HIGH | wildcard *전* + 4 구체 *후* LIFO 정합 영구 가드 (사이클 80 hotfix #3/#4 + 사이클 85 G-AST-LIFO 답습) |

### 3-C 회귀 가드 매트릭스 (16 sub-case 권장)

| 매트릭스 | 위급도 | sub-case | 명세 |
|------|------|---------|------|
| **H-1** Dispatch Drop 카드 | HIGH | 2 | fetch 후 렌더 + 상위 5 ticker 정렬 |
| **H-2** Callback Exception 카드 | HIGH | 2 | fetch 후 렌더 + ERROR 색상 red 영속 |
| **H-3** Stale Force Retry 카드 | HIGH | 2 | fetch 후 렌더 + 사이클 102 Q73=B 임계 상향 영속 (50~70건/일 정상) |
| **H-4** WS Auto Restart 카드 | HIGH | 2 | fetch 후 렌더 + 0건 영속 운영자 가시화 (사이클 92 영속) |
| **G-AST-RT** useQuery retry:1 | HIGH | 1 | `RealtimeHealth.tsx` `TARGET_PAGES` 추가 (사이클 65 H3 영속) |
| **G-AST-MOCK** api-mocks 등록 영구 가드 | HIGH | 1 | `REQUIRED_REALTIME_HEALTH_ENDPOINTS` literal vs api-mocks 정합 (사이클 75 G-AST5 + 사이클 85 답습) |
| **G-AST-LIFO** Playwright LIFO 정합 | HIGH | 1 | wildcard *전* + 4 구체 *후* (사이클 80 hotfix #3/#4 영속) |
| **M-1** 시간 윈도우 토글 | MEDIUM | 1 | 24h ↔ 7d 클릭 시 refetch + queryKey 변경 |
| **M-2** 60s polling | MEDIUM | 1 | `refetchInterval: 60_000` (사이클 85 답습) |
| **M-3** 모바일 햄버거 8개 | MEDIUM | 1 | Drawer 8개 메뉴 영속 (사이클 81 M-1~M-8 + 사이클 85 M-9 답습) |
| **L-1** KST 영속 | LOW | 1 | `Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시 + `getHours()` 0건 (사이클 68 영속) |
| **L-2** 빈 데이터 graceful | LOW | 1 | 4 prefix 모두 0건 시 "정상 (지난 24h 이슈 0건)" 안내 영속 |

### 3-D 시각 UI 명세 (운영자 가독성)

**카드 레이아웃** (사이클 41 StrategyFunnel 4 카드 답습):
- 4 카드 grid 2x2 (PC) / 1x4 (모바일)
- 카드 헤더: 한글 라벨 (사이클 89 영속) + 카운트 (대형 숫자) + 색상 배지 (정상/주의/위험)
- 카드 본문: 상위 5건 ticker 리스트 (handler/order_no 함께, callback_exception 영역)

**시간 윈도우 토글** (사이클 85 답습):
- 상단 우측 배치 (사이클 85 stats 카드 옆)
- `time-window-toggle-24h` / `time-window-toggle-7d` 버튼 그룹 (선택 시 active 색상)
- 변경 시 queryKey 갱신 → 4 useQuery 동시 refetch

**한글 친숙 용어** (사이클 89 영속 + 사이클 75 영속):
- `Dispatch Drop` → "시세 메시지 누락"
- `Callback Exception` → "콜백 예외"
- `Stale Force Retry` → "강제 재구독"
- `WS Auto Restart` → "WebSocket 자동 재기동"
- 사이클 언급 0 + 영문 용어 최소화 (사이클 89 hotfix #2 영속)

---

## 4. 영속 의무 매트릭스 (HIGH)

| 영역 | 사이클 | 영속 의무 |
|------|------|---------|
| 4 카드 패턴 | 사이클 41 StrategyFunnel | 4 카드 grid + 상위 5 ticker 정렬 영속 |
| useQuery retry:1 | 사이클 65 H3 + 사이클 75 G-RT3 + 사이클 80 hotfix #1 + 사이클 85 G-AST-RT | `RealtimeHealth.tsx` `TARGET_PAGES` 추가 영속 |
| KST 일관성 | 사이클 68 + 사이클 85 G-KST | `Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시 + `getHours()` 0건 |
| api-mocks 영구 가드 | 사이클 75 G-AST5 + 사이클 85 G-AST-MOCK | `REQUIRED_REALTIME_HEALTH_ENDPOINTS` literal vs api-mocks 정합 |
| Playwright LIFO 정합 | 사이클 80 hotfix #3/#4 + 사이클 85 G-AST-LIFO | wildcard *전* + 4 구체 *후* 영구 가드 |
| 모바일 햄버거 메뉴 | 사이클 81 M-1~M-8 + 사이클 85 M-9 | Drawer 8개 메뉴 영속 |
| 한글 친숙 용어 + 사이클 언급 0 | 사이클 89 + 사이클 75 | 영문 용어 최소화 영속 |
| ApiResponse 정합 | 사이클 84 5 GET 라우트 영속 | `data.data` 추출 패턴 영속 |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 영속 | 매매 hot path 영역 무관 영속 (UI 단독) |

---

## 5. Phase 3 인계 의무 매트릭스

### 5-A frontend-dev Red 작성 의무

1. `_workspace/red/cycle103_realtime_health_ui.md` 신규 (Phase 3 Red 명세)
2. 6 신규 파일 작성 (types / api / page / App.tsx / handlers / api-mocks)
3. 6 테스트 파일 작성 (api / page / AppShell / AST 2 + pytest)
4. 16 sub-case 회귀 가드 매트릭스 영속 (4 HIGH 8 + 2 MEDIUM 3 + 2 LOW 2)

### 5-B tester verify 의무 (Phase 4)

1. frontend 245 → 261 PASS 영속 (16 신규)
2. backend 2315 → 2316 PASS 영속 (G-AST-LIFO 1 신규)
3. flakiness 0 검증 (3 회 반복)
4. CLAUDE.md "절대 깨지 말 것" 8 영역 영속 검증

### 5-C 사용자 결정 회수 의무 (Phase 3 진입 *전*)

**team-leader 권장 영역 4종 사용자 회수 의무**:
- Q10 = **(B) 신규 페이지 `/realtime-health`** (사이클 85 답습)
- Q11 = **(A) system_logs 직접 조회 + 60s polling** (기존 `searchLogs` 활용)
- Q12 = **4 카드** (사이클 92 `[ws_auto_restart]` 포함)
- Q13 = **(C) 사용자 선택 토글 (24h / 7일)** (사이클 85 답습)

---

## 6. 사이클 103 운영 효과 예상 (push + EC2 자동 배포 후)

- 사용자 UI 메뉴 "실시간 건강" 클릭 → 4 카드 실시간 노출
- `[dispatch_drop_summary]` 0건/일 운영자 즉시 확인 → silent 누락 영역 가시화
- `[callback_exception]` 0건/일 운영자 즉시 확인 → 콜백 예외 빈도 영구 모니터링
- `[stale_force_retry]` 50~70건/일 정상 영역 운영자 즉시 확인 → 사이클 29 124~141건/일 대비 감소 (사이클 102 Q73=B 임계 상향 효과)
- `[ws_auto_restart]` 0건/일 정상 영역 운영자 즉시 확인 → KIS LMS chain 안전 마진 영역

---

## 7. 사이클 104+ 후속 카드 인계 (영구 영속)

- **사이클 104 = D+1 통합 측정** (2026-06-12 (금) 07:50~08:10 + 09:00~10:00 + 20:00~20:30 통합) — Q2=통합 영속
- **Plan Phase A 자문** = LOW 위험 영역 영구 영속 (Q3=자문 생략)
- **카드 #21 (LOW)** 사이클 74 stale_watcher logging flaky (영속)
- **카드 #16** (MEDIUM 사이클 71+ Q6-3 후보 풀 폭축 회고)
- **auth 1.43x** (LOW)

---

## 8. 변경 통계 추정 (Phase 3 + Phase 4 통합)

- **frontend production**: ~430L 순증 (types 40 + api 80 + page 280 + App.tsx 5 + handlers 30 + api-mocks -5)
- **frontend 테스트**: ~250L 순증 (api 80 + page 120 + AppShell 30 + AST 2 + 20)
- **backend 테스트**: ~50L 순증 (pytest AST G-AST-LIFO 1 파일)
- **production 백엔드 변경**: 0 (frontend 단독 사이클)

---

## 9. Phase 3 진입 조건

1. 사용자 Q10/Q11/Q12/Q13 회수 완료 (또는 team-leader 권장 영역 채택 명시)
2. tdd-engineer 호출 시점 = Phase 2 사용자 결정 회수 완료 *직후*
3. Phase 3 Red 명세 = `_workspace/red/cycle103_realtime_health_ui.md` 신규 생성
4. Phase 4 verify = backend 2316 + frontend 261 = 합계 2577 PASS 영속 예상

---

**team-leader 서명**: Phase 2 명세 분해 영구 영속 완료. Phase 3 tdd-engineer 인계 의무 영속.
