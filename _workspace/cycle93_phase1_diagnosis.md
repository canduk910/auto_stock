# 사이클 93 Phase 1 진단 — 3 영역 통합 silent 결함 정밀 검토

> **상태**: Phase 1 READ-ONLY 진단 완료. Phase 2 (Red 명세 작성) 사용자 결정 대기.
> **위급도**: **HIGH** (사이클 89 silent 결함 영구 잔존 — stock_master 500+ 영구 미충족 = 후보 풀 자원 절약 + universe guard 실효성 무력).
> **domain-expert 자문 의무**: **권고** (사이클 87 Q3/Q9 + 사용자 신규 발견 stock_master 60 영역 통합 — refactor 패턴 + 단일 진실의 원천 선정).

---

## 1. 사용자 보고 (verbatim)

> "현재 종목마스터 입수도 60개로 그대로야. 해당 부분도 정밀 검토한 뒤 함께 발주하자."

(사이클 87 Phase 2 결과: Q3 `[scan_pool_eager_refresh]` 0건 + Q9 `[stock_master_bulk_refresh]` 0건 영속 + 사용자 신규 보고 stock_master 60 ticker 유지)

---

## 2. 결정적 발견 — 단일 근본 원인 (HIGH)

### 2.1 호출 chain broken — `_universe_eager_refresh_loop(candidates)` 미참조

**`src/engine/scanner.py:1616`** — 모듈 함수:

```python
async def _universe_eager_refresh_loop(candidates: list[str]) -> None:
    """사이클 89 — universe 500 ticker stock_master 순차 upsert 루프.
    - 24h TTL fresh skip
    - ticker 간 50ms sleep
    - graceful: inquire_stock_basics 실패 시 continue
    """
    from src.db.stock_master import is_stale as _sm_is_stale, upsert_one as _sm_upsert
    from src.api.condition import inquire_stock_basics as _inquire_basics
    for ticker in candidates:
        stale = await _sm_is_stale(ticker, max_age_hours=24)
        if not stale: continue
        try:
            basics = await _inquire_basics(ticker)
            await _sm_upsert(basics)
        except Exception: pass
        await _asyncio.sleep(0.05)
```

**`grep -rn "_universe_eager_refresh_loop" src/`** 결과:

| 파일 | 라인 | 호출 형태 |
|------|------|----------|
| `src/engine/scanner.py` | 1616 | 정의 (모듈 함수) |
| `src/engine/scheduler.py` | 502 | self.method 생성 (asyncio.create_task) |
| `src/engine/scheduler.py` | 2591 | self.method 정의 (별개 함수) |

**Scheduler 의 self method (`scheduler.py:2591`) 본체**:

```python
async def _universe_eager_refresh_loop(self) -> None:
    from src.engine.scanner import fetch_top_500_universe  # ← 이거만 import
    # 개장 전 1회
    tickers = await fetch_top_500_universe()  # ← ticker list 받고 *버림*
    logger.info("[universe_eager_refresh] 개장 전 1회 적재 완료 universe=%d", len(tickers))
    while self._running:
        await asyncio.sleep(300)
        tickers = await fetch_top_500_universe()  # ← 동일 결함 반복
        logger.info("[universe_eager_refresh] 5분 주기 적재 완료 universe=%d", len(tickers))
        flush_universe_collector()  # ← summary flush 만
```

**`fetch_top_500_universe()` (`scanner.py:1532`)** 는 KIS volume_rank API 호출 후 ticker list 반환만 — **stock_master upsert 0건**.

### 2.2 동일 결함 — POST `/api/stock-master/refresh-universe` (수동 trigger)

**`src/routes/stock_master.py:52`**:

```python
from src.engine.scanner import fetch_top_500_universe
tickers = await fetch_top_500_universe()  # ← ticker list 받고 *버림*
return ApiResponse(success=True, data={"universe": len(tickers), "elapsed_ms": elapsed_ms}, ...)
```

사용자 UI "지금 새로고침" 버튼 클릭 → POST 호출 → `fetch_top_500_universe()` ticker list 반환 → **stock_master upsert chain 호출 없음** → 60 ticker 영속 유지.

---

## 3. 가설 확정/거부 매트릭스

| 가설 | 평가 | 근거 |
|------|------|------|
| **A. 사이클 91 페이징 코드 결함** | **거부** | `_fetch_volume_rank` (scanner.py:1437) 영역 정합 확인 — `max_pages=15` + `tr_cont` 순환 + `_response_headers["tr_cont"]` 추출 + 50ms sleep 모두 정상 |
| **B. EC2 배포 sticky** | **부분 거부** | `git log` 확인 사이클 91 `9a0e96a` + 사이클 92 `9e556ee` push 완료 (D 영역은 사용자 EC2 SSH 위임) |
| **C. `_response_headers["tr_cont"]` 정합 결함** | **거부** | `base.py:760-772` `httpx.Response.headers.get("tr_cont")` 추출 + iscoroutine() 가드 + 빈 문자열 폴백 graceful — 정합 확인 |
| **D. Q3/Q9 task 자체 미생성** | **거부** | `scheduler.py:493-503` `_scan_pool_eager_refresh_task` + `_universe_eager_refresh_task` 양쪽 `asyncio.create_task` 정상 생성 |
| **E. 신규 — 호출 chain broken (사이클 89 도입 silent 결함)** | **확정 HIGH** | `_universe_eager_refresh_loop(candidates)` 모듈 함수 (`scanner.py:1616`) 0건 호출. scheduler self method 가 `fetch_top_500_universe()` ticker list 만 받고 *버림*. POST 라우트 동일 결함 |

**영속 사이클 89 silent 결함 chain**:

1. 사이클 89 (`05fe1fd`) — `fetch_top_500_universe()` + `_universe_eager_refresh_loop(candidates)` 2 함수 도입 → 호출 wiring 누락
2. 사이클 90 (`3c8ff59`) — POST `/refresh-universe` 신규 시 `fetch_top_500_universe()` 만 호출, upsert chain 미연결 (사이클 89 결함 답습)
3. 사이클 91 (`9a0e96a`) — KIS 페이징 시정 완료 (500 ticker 정상 fetch) — but stock_master 60 영속 = chain broken 이라 영향 0
4. 사이클 92 (`9e556ee`) — TIME_BOOT 충돌 시정 (별개 영역, 본 결함 무관)

**결정적 영역**: 사이클 89 단위 테스트 (`tests/unit/engine/test_cycle89_rate_limit_50ms.py` + `test_cycle89_candidate_pool_protection.py`) 가 **함수 존재**만 검증 + **실제 호출 chain 미검증** = silent 결함 영구 차단 가드 부재.

---

## 4. Q3/Q9 silent 결함 동시 영역 (사이클 87 Phase 2 인계)

### 4.1 `[scan_pool_eager_refresh]` 0건 — 사이클 83 도입 영역

**`src/engine/scheduler.py:2562`** `_scan_pool_eager_refresh_loop` self method:

```python
async def _scan_pool_eager_refresh_loop(self) -> None:
    from src.engine.scanner import (
        _scan_pool_eager_refresh_loop as _scanner_eager_refresh,  # ← 정상 import
        flush_scan_pool_eager_refresh_collector,
    )
    while self._running:
        await asyncio.sleep(300)
        await _scanner_eager_refresh()  # ← 정상 호출 (chain 연결됨)
        flush_scan_pool_eager_refresh_collector()
```

**`_scan_pool_eager_refresh_loop` 사이클 83 영역 = chain 정상**. 0건 영속 원인 = 사용자 보고된 `subscribe_filtered_stocks` 미발화 가능성 (후보 풀이 5분 동안 빈 set 이면 record 0건) — *별개 영역*. **Phase 2 사용자 EC2 SSH 운영 로그 검증 위임 의무**.

### 4.2 `[stock_master_bulk_refresh]` 0건 — 사이클 89 영역

**상황**: `fetch_top_500_universe()` 정의는 정상 (`scanner.py:1586` `[stock_master_bulk_refresh]` emit) + scheduler task 도 정상 생성 (L501) + 호출 정상 (L2618/L2630).

**잠재 원인**:
1. 사이클 89 task 가 production 환경에서 정상 task 시작했으나 `fetch_top_500_universe()` 가 `KisApiError` 또는 timeout 으로 영구 실패 → 예외 graceful (`logger.exception("[universe_eager_refresh] 개장 전 1회 적재 실패")`)
2. 사이클 89 commit 이 production push 후 EC2 컨테이너 재시작 안 됨 (CI deploy 실패 또는 sticky 이전 코드)
3. logger 경로 결함 — 사이클 17 KIS LMS chain 영역 답습 위험

**Phase 2 사용자 EC2 SSH 운영 로그 검증 위임 의무** (Q35=B 옵션 채택 시).

---

## 5. KIS MCP 정본 재검증

### 5.1 volume_rank.py 페이징 패턴

`docs/kis/` + KIS MCP `mcp__kis-code-assistant__search_domestic_stock_api` 정본 영역:
- 응답 헤더 `tr_cont == "M"` → 다음 페이지 (Multi)
- 재호출 `tr_cont = "N"` (Next)
- 종료 `tr_cont in ("", "D", "E")`
- 첫 페이지 응답 한도 ~30건 (KIS 표준)

**사이클 91 시정 (`scanner.py:1481-1529`) = 정본 패턴 100% 정합** — 영역 1 결함 없음 확정.

### 5.2 CTPF1002R (`inquire_stock_basics`)

`stock_master.upsert_one(basics)` 정합성 = 사이클 81 `bfdy_clpr` 키 시정 영속. **호출 chain broken 영역 한정** (E 결함).

---

## 6. EC2 배포 영역 검증

```bash
git log --oneline -5
# 9e556ee 사이클 92
# 9a0e96a 사이클 91
# 3c8ff59 사이클 90
# 05fe1fd 사이클 89
```

push 완료. **EC2 컨테이너 재시작 확인 = 사용자 SSH 영역 위임** (`docker compose ps` + `docker compose logs --tail 50`).

---

## 7. Q34~Q36 사용자 결정 의제 + 권고안

### Q34 (HIGH) — 사이클 93 발주 방향

**권고 = 옵션 A (3 영역 통합 단일 사이클)**:
- 영역 E (stock_master 60 — 확정 HIGH) = 1줄 시정 (scheduler self method + POST 라우트 양쪽에 `from src.engine.scanner import _universe_eager_refresh_loop` import + `tickers = await fetch_top_500_universe(); await _universe_eager_refresh_loop(tickers)` 호출)
- 영역 Q3 (`[scan_pool_eager_refresh]` 0건) = 운영 로그 진단 후 결정
- 영역 Q9 (`[stock_master_bulk_refresh]` 0건) = E 시정 후 자동 해결 가능 (E 가 호출 chain 복구 = bulk_refresh emit 자연 발화)

옵션 B (각 영역 별개) = 사이클 분산으로 silent 결함 chain 운영 잔존 위험 증가, 채택 비권고.
옵션 C (페이징 60 우선 + Q3/Q9 보류) = E 단독 시정만 진행. Q3/Q9 별개 사이클 94+ 인계 가능.

### Q35 (HIGH) — 진단 깊이

**권고 = 옵션 B (A + 사용자 EC2 SSH 운영 로그 수동 확인 동행)**:
- E 결함은 코드 정적 분석으로 확정 (SSH 불요)
- Q9 `[stock_master_bulk_refresh]` 0건 = E 결함의 자연스러운 결과 (chain broken 시 task 가 ticker list 만 받고 종료, summary emit 만 발화) — 운영 로그 추가 검증 *권고*
- Q3 `[scan_pool_eager_refresh]` 0건 = 별개 영역, 운영 로그 필수

옵션 A (Supabase MCP READ-ONLY 만) = MCP 권한 거부로 *불가능* 확정. 옵션 C (단위 테스트 추가) = E 결함 confirm 회귀 가드 신설 의무, Phase 2 채택 권고.

### Q36 (HIGH) — 시정 push 시점

**권고 = 옵션 B (NXT 애프터 15:30+)**:
- 현재 KRX 메인 시간 (09:40 KST) — `_scan_loop` 5분 race + `_universe_eager_refresh_loop` 5분 race 동시 발화 시 KIS Rate Limit + LMS chain 위험
- E 결함은 매매 안전성 직접 영향 영역 *아님* (universe guard 실효성 영역만, 사이클 32 R4 영속 + 보유/익일청산 절대 보호 영속) — 익일 영업일 적용으로 충분
- 옵션 A (즉시) = KRX 메인 시간 중 push 위험 (CLAUDE.md 운영 가이드 위반)
- 옵션 C (익일 07:45 전) = 사이클 92 답습 (TIME_BOOT 07:55 → 07:50 KIS 강제 중단 회피) 영속, 안전 영역

---

## 8. 시정 청사진 (Phase 2 채택 시)

### 8.1 영역 E 시정 (스코프 최소화)

**`src/engine/scheduler.py:2591` `_universe_eager_refresh_loop` self method (2 위치)**:

```python
# 현재 (L2618 + L2630):
tickers = await fetch_top_500_universe()
logger.info("[universe_eager_refresh] ... universe=%d", len(tickers))

# 시정:
from src.engine.scanner import (
    fetch_top_500_universe,
    _universe_eager_refresh_loop as _scanner_upsert_loop,  # 모듈 함수 import
)
tickers = await fetch_top_500_universe()
try:
    await _scanner_upsert_loop(tickers)  # ← chain 복구
except Exception:
    logger.exception("[universe_eager_refresh] stock_master upsert 실패 graceful")
logger.info("[universe_eager_refresh] ... universe=%d", len(tickers))
```

**`src/routes/stock_master.py:52` POST `/refresh-universe` 동일 시정** (Q24 사용자 결정 영속).

### 8.2 회귀 가드 신설 (사이클 89 silent 결함 영구 차단)

**HIGH 5 케이스 (1 신규 파일 `tests/unit/engine/test_cycle93_universe_refresh_chain.py`)**:
- G-CC1 (HIGH) `scheduler._universe_eager_refresh_loop` 본체에 `_universe_eager_refresh_loop(tickers)` (scanner module func) 호출 ≥1건 정적 grep
- G-CC2 (HIGH) `routes/stock_master.py::refresh_universe_now` 본체 동일 grep
- G-CC3 (HIGH) integration test — mock `_inquire_basics` + mock `_sm_upsert` + `_universe_eager_refresh_task` 1회 실행 후 `_sm_upsert.call_count >= N` (N = mock universe 크기, 24h TTL skip 미적용 시 100% 호출)
- G-CC4 (HIGH) integration test — POST `/refresh-universe` 호출 후 `_sm_upsert.call_count >= N`
- **G-AST1 영구 가드 (HIGH)** — `tests/unit/ast/test_cycle93_ast_universe_chain_required.py` 신규: `fetch_top_500_universe()` 호출 사이트에 `_universe_eager_refresh_loop(...)` 호출 ≥1건 AST 정적 검증 (미래 신규 universe refresh 영역 추가 시 chain 누락 영구 차단)

---

## 9. 결론 + 후속 카드

**핵심 발견**: 사이클 89 도입 silent 결함 영구 잔존 = `_universe_eager_refresh_loop(candidates)` 모듈 함수 0건 호출 chain broken. 사이클 91 페이징 시정 (500 ticker 정상 fetch) + 사이클 92 TIME_BOOT 시정은 모두 *별개 영역* + 본 결함 무관. **사이클 93 = 사이클 89 silent 결함 영구 시정 (HIGH)**.

**silent 결함 영구 차단 20 회 누적 (예상)** = 사이클 60/64/65#1/65#2/65#3/66/67/68/72/73/77/77#2/78/79/80/80#2/80#3/80#4/81/**93**.

**사용자 결정 의무 3건 (Q34/Q35/Q36)**. domain-expert 자문 권고 (Q3/Q9/E 통합 단일 사이클 발주 결정 + 회귀 가드 위치 + 사이클 89 silent 결함 영역 확장 평가).

**Phase 2 채택 시 후속 사이클 94+ 인계**:
- Q3 `[scan_pool_eager_refresh]` 0건 영역 별개 진단 (사용자 EC2 SSH 운영 로그 확보 후)
- 사이클 89 단위 테스트 호출 chain 회귀 가드 확장 (G-AST 패턴 답습)
- 사이클 87 Phase 2 결과 `_workspace/cycle87_dplus1_verification.md` 영속 검증
