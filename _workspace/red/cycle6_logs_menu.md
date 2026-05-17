# 사이클 6 — 로그 메뉴 신설 + 년/월/일 필터

날짜: 2026-05-17
목적: 대시보드 하단 시스템 로그 viewer 를 별도 /logs 메뉴로 분리하고 두 탭(시스템 로그 / 일일 로그 분석) 통합. 시스템 로그 탭에 기간(from_date/to_date) + 페이징 필터 추가.

## 자율 결정 사항
1. **기간 검색**: from_date / to_date 분리 date input (단일 날짜 아님). 기본값 둘 다 오늘(KST).
2. **URL 쿼리**: `?tab=system | daily-report` (기본 `system`). 시스템 로그를 더 자주 조회한다는 트레이더 관점 우선.
3. **컴포넌트 추출**: `LogReports.tsx` → `DailyReportTab.tsx` 신규 (JSX 동일). `LogReports.tsx` 자체는 `Navigate to="/logs?tab=daily-report" replace />` 로 단순화.

## 행위 (Red 대상)

### 백엔드 — `src/db/system_logs.py`

**B1. `get_logs()` 시그니처 확장 — 페이징 응답 dict 반환**
- 입력: `limit=50, log_level=None, from_date=None, to_date=None, page=1, size=50`
- 출력: `{"items": list[dict], "total": int, "total_pages": int}`
- `size` 명시 시 size 사용, 미명시면 limit 사용 (하위 호환)
- `total_pages = ceil(total / effective_size)` (total 0 이면 0)

**B2. KST 기간 필터링**
- `from_date` 명시 시 `timestamp >= f"{from_date}T00:00:00+09:00"`
- `to_date` 명시 시 `timestamp <= f"{to_date}T23:59:59.999999+09:00"`
- `log_level` 명시 시 함께 적용
- 둘 다 None 이면 기간 무필터 (기존 동작 보존)

**B3. 페이징 정확성**
- offset = (page - 1) * effective_size
- `.range(offset, offset + effective_size - 1)` (supabase-py 페이징 패턴)
- 최신순 timestamp DESC 정렬 유지
- total 은 `count="exact"` 옵션으로 별도 쿼리 또는 동일 쿼리에서 추출

**B4. 기존 limit 단독 호출 회귀 보존**
- `await get_logs(limit=50)` 호출 시 dict 반환 → 호출자 `recent_logs` 라우트도 함께 갱신
- conftest mock `fake_get_logs` 도 dict 반환으로 갱신 필요 (테스터가 처리)

### 백엔드 — `src/routes/logs.py`

**B5. 신규 쿼리 파라미터**
- `from_date: date | None = None`, `to_date: date | None = None`, `page: int = 1`, `size: int = 50`
- `limit` 은 deprecated 이지만 보존 (size 우선)
- 응답 `ApiResponse(data={items, total, total_pages})` 구조

**B6. 422 검증**
- page < 1, size < 1 또는 size > 200 → 422
- from_date > to_date → 422 또는 자동 swap (자율 결정: **422 거부**, 운영자 실수 명시)

### 프론트엔드

**F1. App.tsx 라우트/메뉴 갱신**
- 메뉴 항목: "/log-reports 일일 로그 분석" → "/logs 로그"
- `/log-reports` 라우트는 `<Navigate to="/logs?tab=daily-report" replace />` 로 유지 (북마크 호환)
- `/logs` 라우트 신설 → `<Logs />` lazy

**F2. `pages/Logs.tsx` 신규 — 탭 컨테이너**
- `useSearchParams` 로 `?tab` 쿼리 동기화
- 기본 탭: `system`
- 탭 클릭 시 URL 갱신 (replace, push 둘 다 무방)
- 탭 컴포넌트: `<SystemLogsTab />` / `<DailyReportTab />`

**F3. `components/SystemLogsTab.tsx` 신규**
- 기본 from_date/to_date = 오늘(KST, `Intl.DateTimeFormat`로 변환)
- 2개 date input + level select (DEBUG/INFO/WARNING/ERROR/ALL) + size 50 고정
- 페이징 컨트롤 (이전/다음 + "page / total_pages"), 빈 결과 처리
- 로그 표 (timestamp KST / level / message), `LEVEL_STYLE` 동일
- API: `apiClient.get('/logs', {params: {from_date, to_date, level, page, size}})`
- `useQuery` queryKey `['systemLogs', from_date, to_date, level, page]`

**F4. `components/DailyReportTab.tsx` 신규**
- 기존 `LogReports.tsx` 의 JSX 본문(`<ReportCard/>` + 좌측 리스트 + run 버튼) 그대로 추출
- export default function 명만 `DailyReportTab` 로 변경
- `formatDateTime`, `FindingCard`, `ReportCard` 도 함께 이전

**F5. `pages/LogReports.tsx` 처리**
- 단순화: `export default function LogReports() { return <Navigate to="/logs?tab=daily-report" replace /> }`
- 또는 App.tsx 의 라우트에서 직접 `Navigate` 사용 → LogReports.tsx 삭제. **자율 결정: LogReports.tsx 삭제 + App.tsx 라우트에 inline Navigate.** lazy import 부담 제거.

**F6. `pages/Dashboard.tsx`**
- `LogViewer` import + 121행 `<LogViewer />` 제거
- 다른 참조 없는지 확인 (LogViewer.tsx 파일 자체는 보존 — SystemLogsTab 이 재사용할 수도 있고 회귀 영향 0)

**F7. KST 컨벤션 강제**
- `toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })`
- 오늘 날짜 계산: `Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())` 또는 `formatToParts` 로 YYYY-MM-DD 구성. `new Date().toISOString().slice(0, 10)` 금지 (UTC 기준)

## Red 테스트 명세

### 백엔드 단위 — `tests/unit/db/test_system_logs_filter.py` (신규)
1. `test_get_logs_default_returns_dict_with_pagination_meta` — `await get_logs()` 호출 시 `{items, total, total_pages}` 구조
2. `test_get_logs_from_to_date_filter_kst` — supabase 호출 시 `timestamp >= "{date}T00:00:00+09:00"`, `<= "{date}T23:59:59.999999+09:00"` 필터 확인
3. `test_get_logs_page_size_pagination` — page=2, size=10 → offset=10, range(10, 19) 호출 확인
4. `test_get_logs_total_pages_calculation` — total=23, size=10 → total_pages=3
5. `test_get_logs_legacy_limit_only_call` — `await get_logs(limit=50)` 호출 시 dict 반환 + size=50 흡수
6. `test_get_logs_level_with_date_filter` — log_level + from_date 동시 적용
7. `test_get_logs_empty_result` — total=0, items=[], total_pages=0

### 백엔드 계약 — `tests/contract/test_routes_logs.py` (확장)
1. 기존 3 케이스 갱신 (response `data` 가 dict 구조)
2. `test_logs_with_date_filter` — `?from_date=2026-05-15&to_date=2026-05-17` → mock get_logs 호출 인자에 두 date 전달
3. `test_logs_with_page_size` — `?page=2&size=20` → mock 호출 인자에 page=2, size=20
4. `test_logs_invalid_page_zero_returns_422` — `?page=0` → 422
5. `test_logs_invalid_size_too_large_returns_422` — `?size=300` → 422
6. `test_logs_from_after_to_returns_422` — `?from_date=2026-05-17&to_date=2026-05-15` → 422
7. `test_logs_response_includes_total_and_total_pages` — `data.items`, `data.total`, `data.total_pages` 키 존재

### 프론트엔드 — `frontend/src/pages/__tests__/Logs.test.tsx` (신규)
1. 기본 렌더 시 `?tab=system` 미지정이면 시스템 로그 탭 활성
2. `?tab=daily-report` URL 진입 시 일일 로그 분석 탭 활성
3. 일일 로그 분석 탭 클릭 → URL `?tab=daily-report` 갱신
4. 시스템 로그 탭 클릭 → URL `?tab=system` 갱신 (또는 ?tab 제거)
5. 두 탭 버튼 동시 노출 + aria 또는 active class 검증

### 프론트엔드 — `frontend/src/components/__tests__/SystemLogsTab.test.tsx` (신규)
1. 기본 from_date/to_date 가 오늘(KST) 로 설정되어 API 호출 인자 포함
2. from_date 변경 → API 재호출 (queryKey 갱신)
3. level 선택 → API 호출 인자에 level 포함
4. 페이징 "다음" 클릭 → page=2 로 API 재호출
5. total_pages=1 일 때 "다음" 버튼 disabled
6. 빈 결과 ("로그가 없습니다.") 표시
7. 로그 행 timestamp 가 KST 시각으로 표시 (`Asia/Seoul`)

### 회귀 가드 — App 라우트
- `/log-reports` 접근 시 `/logs?tab=daily-report` 로 리다이렉트 → 별도 단순 테스트 추가 가능 (선택)

## Green 후 문서 갱신
- `src/routes/CLAUDE.md`: `/api/logs` 시그니처
- `src/db/CLAUDE.md`: `get_logs` 반환 dict
- `frontend/CLAUDE.md`: Logs 페이지 추가, Dashboard 의 LogViewer 제거, /log-reports redirect
- `_workspace/00_leader_trading_rules.md`: 사이클 6 섹션
- `docs/HARNESS_CHANGELOG.md`: 사이클 6 1행

## 안전 원칙
- 매매 코드 침범 0
- 기존 호출 시그니처 하위 호환 (limit 단독 호출 → size 흡수)
- /log-reports 북마크 호환 (Navigate replace)
- KST 강제 (백엔드 ISO timezone +09:00 / 프론트 Intl timeZone)
