# 사이클 6 통합 마감 — Red 명세

**작성자**: team-leader  
**작성일**: 2026-05-20  
**범위**: 로그 모듈 한정 (매매 코드 침범 0)

---

## 배경

기존 사이클 6 (2026-05-17) 의 "로그 메뉴 + 기간 필터 + 탭 통합" 은 1차 완료.  
사용자 신규 요청 (2026-05-20):

1. **로그 검색 기능 추가** — 키워드 substring 검색
2. **등급별 retention 정책** — INFO 2일 / WARNING+ 30일

사용자 결정: **옵션 B 통합 1 사이클로 마감** (사이클 6 범위 확장).

---

## 행위 (Behaviors) — 검증 가능한 단위

### A. 백엔드 — DB Retention

#### A1. `purge_old_logs()` — 등급별 분리 DELETE
- 시점: 호출 시 `now_kst = datetime.now(KST)` 캡처
- INFO 등급: `timestamp < (now_kst - timedelta(days=2)).isoformat()` (KST `+09:00` suffix)
- WARNING/ERROR/CRITICAL 등급: `timestamp < (now_kst - timedelta(days=30)).isoformat()` (KST `+09:00` suffix)
- 반환: `{"info_deleted": int, "high_deleted": int, "elapsed_ms": int}`
- INFO 1행 영구 로그: `[log_retention] info_deleted=N high_deleted=M elapsed_ms=K`
- **안전 가드**:
  - 1회 DELETE 최대 행 수 cap 100,000 (supabase `range(0, MAX_PURGE_BATCH-1)` 패턴 또는 명시적 limit)
  - WHERE 조건 누락 시 raise (방어 코드 — `cutoff` 가 None 이면 RuntimeError)

#### A2. scheduler 통합
- `_log_analysis_engine` 직후, `_reset_daily_state()` *직전*
- `await purge_old_logs()` 호출
- 실패는 graceful: `try/except Exception as e: logger.exception(...) + write_log("INFO", f"[log_retention_skip] reason=...")` 다음 사이클 재시도

### B. 백엔드 — 검색 endpoint

#### B1. `search_logs()` — `src/db/system_logs.py` 신규
- 시그니처: `async def search_logs(q: str, *, level: str | None = None, start: str | None = None, end: str | None = None, limit: int = 200) -> dict`
- `q` LIKE 매칭: supabase-py `ilike("message", f"%{q}%")` (대소문자 무시)
- `level` 필터: `level != "ALL"` 면 `eq("log_level", level)`
- `start` / `end`: ISO 8601 (UTC 또는 `+09:00`) → 그대로 `gte` / `lte`
- `limit`: 기본 200, 최대 1000 (호출자 측 clamping)
- 반환: `{"logs": list[dict], "total": int, "has_more": bool}`
  - `total` 은 supabase `count="exact"`
  - `has_more = total > len(logs)`

#### B2. `/api/logs/search` endpoint — `src/routes/logs.py` 신규
- 시그니처: `@router.get("/search", response_model=ApiResponse)`
- 쿼리: `q: str` (필수, 빈 문자열 422) / `level: str | None` / `start: str | None` / `end: str | None` / `limit: int = Query(200, ge=1, le=1000)`
- `q` 빈 문자열 거부 — `q: str = Query(..., min_length=1)`
- 응답: `ApiResponse(success=True, data={"logs": [...], "total": N, "has_more": bool})`

### C. 프론트엔드 — 검색 박스

#### C1. `frontend/src/api/logs.ts::searchLogs()` 추가
- 시그니처: `searchLogs(params: SearchParams): Promise<SearchPayload>`
- `SearchParams { q: string; level?: string|null; start?: string|null; end?: string|null; limit?: number }`
- `SearchPayload { logs: LogEntry[]; total: number; has_more: boolean }`
- GET `/logs/search` axios 호출

#### C2. `SystemLogsTab.tsx` 확장
- 필터 바 위에 검색 박스 추가:
  - 키워드 input `data-testid="system-logs-search-input"` (placeholder "키워드 검색")
  - 검색 버튼 `data-testid="system-logs-search-button"`
  - 초기화 버튼 `data-testid="system-logs-search-clear"` (검색 모드에서만 노출)
- 검색 모드 토글:
  - 검색어 비어있고 미실행 → 기존 페이징 모드 (`fetchLogs`)
  - 검색 버튼 클릭 시 `searchMode=true`, `searchQuery=q` 저장 → `searchLogs` 호출
  - 초기화 클릭 시 `searchMode=false`, `searchQuery=""` → 기존 페이징 모드 복귀
- 검색 모드 동안:
  - level + from/to date 모두 search 인자로 함께 전달 (현재 입력값 활용)
  - 자동 새로고침 비활성
  - 페이징 비활성 (limit 200 1회 응답, has_more 시 "검색 결과 200건 초과 — 키워드를 좁혀주세요" 안내)
- 검색 결과 0건 → "검색 결과가 없습니다." (기존 "로그가 없습니다." 와 메시지 분리)
- 로딩 인디케이터 — `isLoading` 동안 "검색 중..."

### D. 문서 동기화

- `src/db/CLAUDE.md` — `system_logs.py` 절에 `purge_old_logs`/`search_logs` + retention 정책
- `src/routes/CLAUDE.md` — `/api/logs/search` 행 추가
- `src/engine/CLAUDE.md` — settlement 흐름 표에 `purge_old_logs` 1행
- `frontend/CLAUDE.md` — Logs 페이지 검색 박스 명시
- `_workspace/00_leader_trading_rules.md` — 사이클 6 통합 1행
- `docs/HARNESS_CHANGELOG.md` — 사이클 6 통합 마감 1행

---

## 안전 원칙

- 매매 코드(`risk.on_tick` / `order_engine` / 전략 6개) 무변경
- `purge_old_logs` 단일 트랜잭션 cap 100,000 행
- WHERE 조건 cutoff None 가드 → `RuntimeError("cutoff must not be None")` 즉시 raise
- scheduler 통합부 예외 흡수 — 본 흐름 보호
- 한글 커밋 메시지 (prefix 영문)
- push 별도 명시 승인 (커밋까지만)

---

## 회귀 가드 케이스

### 백엔드 — `tests/unit/db/test_system_logs_retention.py` 신규
1. `purge_old_logs` INFO/HIGH 등급별 cutoff 분리 → 2일/30일 cutoff 확인
2. KST `+09:00` suffix 강제
3. cap 100,000 행 적용
4. WHERE cutoff None → RuntimeError
5. 반환 dict `{info_deleted, high_deleted, elapsed_ms}` 형식 + 키 누락 없음
6. INFO 영구 로그 `[log_retention]` prefix 확인

### 백엔드 — `tests/unit/db/test_system_logs_search.py` 신규
1. `search_logs(q="OPSP")` → `ilike("message", "%OPSP%")` 호출
2. `level=ERROR` 동시 적용 → `eq("log_level", "ERROR")` + `ilike` 모두 호출
3. `level=ALL` → `eq` 호출 안 함
4. `start`/`end` → `gte`/`lte` 호출
5. `limit=200` clamping (>1000 거부 또는 1000으로 clamp)
6. 반환 dict `{logs, total, has_more}` 형식
7. `has_more = total > len(logs)` 검증
8. 빈 검색어 → ValueError (route 측 422 회귀 분리)

### 백엔드 — `tests/contract/test_routes_logs_search.py` 신규
1. `GET /api/logs/search?q=OPSP` → 200 + `data.logs` 배열
2. `q` 누락 → 422
3. `limit=2000` → 422 (max 1000)
4. `limit=0` → 422 (min 1)
5. 응답 ApiResponse 래퍼 `{success, data, message}`

### 프론트엔드 — `SystemLogsTab.test.tsx` 확장
1. 검색어 입력 + 검색 버튼 클릭 → `/api/logs/search` API 호출 + `q` 인자 전달
2. 검색 결과 렌더 → 행 표시 (검색 모드 진입 확인 via `searchMode` UI cue)
3. 0건 → "검색 결과가 없습니다." 메시지
4. 초기화 버튼 클릭 → 검색 모드 종료, 기존 `/api/logs` 호출 복귀

---

## 시간 가이드
- 백엔드 Green: ~30분
- 프론트엔드 Green: ~30분
- 통합 검증 + sync-docs: ~20분
- 총 ~1.5시간

---

## 검증 명령

```bash
# 신규 회귀 가드
python -m pytest tests/unit/db/test_system_logs_retention.py \
                 tests/unit/db/test_system_logs_search.py \
                 tests/contract/test_routes_logs_search.py -v

# 백엔드 전체
python -m pytest -q

# 프론트엔드
cd frontend && npm test
```
