# 사이클 190 Red 작업 지시서 — write_log never-raise 전환 + 크래시 핸들러 예외타입 계측

출처: 7/3 아침 D+1 모니터링에서 발견한 매매 프로세스 크래시 (사용자 승인 = "190 진행" + 설계 결정 = write_log 자체 never-raise).

## 결함 (2026-07-03 07:59 운영 실증)

`scheduler.py:677`(start(), "스윙 유니버스 비어있음" 분기)의 bare `await write_log("INFO", ...)` 가 Supabase HTTP/2 `httpcore.RemoteProtocolError(ConnectionTerminated)` 로 raise → start() 외곽 except(L919, 사이클 146 `KisApiError` graceful 분기에 **미해당** — Supabase 예외는 KisApiError 아님) → finally task 7종 cancel + WS 3세션 종료 → **매매 시스템 종료** (08:00 자동 재시작, 다운 2.7분 + 아침 task 2벌 재실행). "매매 프로세스 오류"는 6/10~7/3 한 달간 8회 발생한 상습 크래시 클래스 (과거 건 원인은 traceback 소실로 미확정 — 단정 금지).

구조 원인 = `src/db/system_logs.py::write_log` 가 INSERT 실패 시 그대로 raise. src/ 전체 직접 `await write_log` 72곳 — 로컬 보호(try/except) 여부가 사이트마다 다르고, "로컬 보호 vs 파국적 외곽 try" 를 AST 로 구분 불가(크래시 지점 L677 이 나이브 기준 '보호됨'으로 오분류).

## 사용자 결정 (AskUserQuestion)

**write_log 자체 never-raise** — 호출부 72곳 무변경, 기존 테스트 patch 타겟 보존, 관찰성 INSERT 가 매매를 죽이는 클래스를 단일 지점에서 영구 차단.

## Green 계약

### 1. `src/db/system_logs.py::write_log` never-raise 전환
```python
async def write_log(log_level, message):
    ...
    try:
        await asyncio.to_thread(lambda: supabase.table("system_logs").insert(data).execute())
    except Exception:
        logger.debug("[write_log_failed] level=%s msg=%.80s", log_level, message)
```
- **logger.debug 단독** (safe_write_log 사이클 56-E 답습 — WARNING 이상이면 `_DbLogHandler` 가 다시 DB INSERT 시도 = 재귀/무한 루프 위험. debug = DbLogHandler 미발화)
- 시그니처/반환(None) 불변. docstring 에 사이클 190 계약("관찰성 함수 — 어떤 예외도 전파 금지") 명시
- `safe_write_log` 는 호환 유지 (변경 0 — 내부적으로 이제 중복 보호이나 무해)

### 2. `src/engine/scheduler.py` 크래시 핸들러 계측 (L919~920)
- `await write_log("ERROR", "매매 프로세스 비정상 종료")` → `await write_log("ERROR", f"매매 프로세스 비정상 종료: {type(exc).__name__}: {str(exc)[:150]}")` — 과거 8회 원인불명 재발 시 DB 만으로 즉시 진단 가능
- `logger.exception("매매 프로세스 오류")` 불변. 그 외 핸들러 흐름(L906 KisApiError graceful / finally) 변경 0

## Red 테스트

### `tests/unit/db/test_cycle190_write_log_never_raise.py` (~5)
- W-1 (HIGH): INSERT 가 `httpx.RemoteProtocolError` raise → `await write_log(...)` 예외 미전파 (return None)
- W-2: `httpcore` ConnectionTerminated 계열 / 일반 Exception 도 미전파 (parametrize)
- W-3: 실패 시 `logger.debug` 1회 발화 + **`logger.warning` 이상 미발화** (DbLogHandler 재귀 차단 계약, caplog)
- W-4: 정상 경로 INSERT 1회 호출 불변 (payload log_level/message/timestamp KST 키 보존 — 사이클 65 H2)
- W-5: `safe_write_log` 기존 계약 보존 (실패 graceful + fallback_debug — 기존 cycle56-E 테스트 있으면 중복 금지, 없는 부분만)

### `tests/unit/engine/test_cycle190_crash_handler_instrument.py` (~3)
- H-1 (HIGH): 크래시 핸들러 경로에서 write_log ERROR 메시지에 예외 타입명(`RemoteProtocolError` 등) + str(exc) 요약 포함
- H-2: `KisApiError` 분기(사이클 146) 행위 불변 — graceful return + 프로세스 보존 경로 유지
- H-3: 예외 요약 150자 절단 (초장문 예외 메시지 DB 부풀림 차단)

### `tests/unit/ast/test_cycle190_ast_write_log_guard.py` (~3)
- A-1: `write_log` 본체 = broad except Try 존재 + except 내 raise 0건 (never-raise 불변식)
- A-2: `write_log` except 절 내 `logger.debug` 호출 + `logger.warning`/`logger.error`/`write_log` 재호출 0건 (재귀 차단)
- A-3: 크래시 핸들러 write_log 호출에 예외 타입 포맷 동반 (source 검사 — `type(exc).__name__` 토큰)

## 기존 테스트 의미 전환 검토 의무
- `tests/unit/db/` 에서 write_log raise 를 계약으로 단언하는 케이스(사이클 56-E safe_write_log 대비 테스트 등) 존재 여부 확인 → 있으면 xfail 의미 전환(사이클 66 K-2) 또는 단언 갱신, 사유 명기
- write_log 를 mock/patch 하는 테스트 다수는 함수 교체라 무영향 예상 — 확인만

## Red 유효성 기준
현재 코드에서 W-1/2/3 + H-1/3 + A-1/2/3 FAIL, 불변식(W-4/5, H-2) PASS 허용.

## Green 범위
`src/db/system_logs.py::write_log` + `src/engine/scheduler.py` 핸들러 1줄. 그 외 파일 변경 금지. 매매 안전성 8영역 diff 0 의무.
