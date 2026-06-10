# 사이클 93 Red 명세 — 호출 chain broken 영구 시정 (사이클 89 도입 silent 결함)

> **상태**: Red 단계. backend-dev Green 단계 대기.
> **위급도**: HIGH (사이클 89 도입 silent 결함 21회 누적 차단 시점, 사용자 보고 stock_master 60 ticker 영속).
> **영역**: scheduler `_universe_eager_refresh_loop` self method 2 분기 + POST `/api/stock-master/refresh-universe` 라우트 = **3 사이트 통합 단일 사이클** (Q34=A 채택).
> **사용자 결정 영속**: Q34=A 3 영역 통합 / Q35=B 코드 정적 분석 + EC2 SSH 수동 확인 / Q36=A 진단 직후 push.

---

## 1. 결함 chain (Phase 1 진단 확정)

`src/engine/scanner.py:1616::_universe_eager_refresh_loop(candidates: list[str])` =
사이클 89 도입 **stock_master upsert 담당** 모듈 함수. **호출 0건** 영속.

| # | 사이트 | 결함 | 효과 |
|---|--------|------|------|
| 1 | `src/engine/scheduler.py:2618` `_universe_eager_refresh_loop` 본체 — 개장 전 1회 분기 | `fetch_top_500_universe()` 호출 후 ticker list **버림** | stock_master upsert 0건 → 60 ticker 영속 |
| 2 | `src/engine/scheduler.py:2630` `_universe_eager_refresh_loop` 본체 — 5분 주기 분기 | 동일 결함 반복 | 5분마다 universe 갱신 무용 |
| 3 | `src/routes/stock_master.py:52` POST `/refresh-universe` 라우트 | `fetch_top_500_universe()` 호출 후 ticker list **버림** | UI "지금 새로고침" 버튼 무용 |

운영 실측 효과 (사용자 보고):
- stock_master `count_all = 60` 영속 (사이클 89 배포 이후 += 0)
- `[stock_master_bulk_refresh]` summary emit 정상 (fetch_top_500_universe 내부 emit)
- but **stock_master 60 ticker 영속** = chain broken 결과

silent 결함 영구 차단 매트릭스 누적 (예상):
사이클 60 / 64 / 65#1 / 65#2 / 65#3 / 66 / 67 / 68 / 72 / 73 / 77 / 77#2 / 78 / 79 / 80 / 80#2 / 80#3 / 80#4 / 81 / 89 / **93** = **21 회**

---

## 2. 시정 매트릭스 (Green 단계 backend-dev 인계)

### 2.1 `src/engine/scheduler.py::_universe_eager_refresh_loop` (L2591~)

```python
async def _universe_eager_refresh_loop(self) -> None:
    """사이클 93 (2026-06-10) — 호출 chain broken 영구 시정.

    사이클 89 도입 시 _scanner_upsert_loop(tickers) 호출 누락 = silent 결함 21회 누적.
    """
    from src.engine.scanner import (
        fetch_top_500_universe,
        _universe_eager_refresh_loop as _scanner_upsert_loop,  # 사이클 93 신규
    )
    from src.engine.stock_master_metrics import flush_universe_collector

    _UNIVERSE_REFRESH_WINDOW_SECS = 300.0

    # 개장 전 1회 즉시 실행
    try:
        tickers = await fetch_top_500_universe()
        logger.info(
            "[universe_eager_refresh] 개장 전 1회 fetch 완료 universe=%d",
            len(tickers),
        )
        # 사이클 93 신규 — stock_master upsert chain
        try:
            await _scanner_upsert_loop(tickers)
            logger.info("[universe_eager_refresh] stock_master upsert 완료")
        except Exception:
            logger.exception("[universe_eager_refresh] stock_master upsert 실패 graceful")
    except Exception:
        logger.exception("[universe_eager_refresh] 개장 전 1회 적재 실패")

    # 5분 주기 반복
    while self._running:
        await asyncio.sleep(_UNIVERSE_REFRESH_WINDOW_SECS)
        try:
            tickers = await fetch_top_500_universe()
            logger.info(
                "[universe_eager_refresh] 5분 주기 fetch 완료 universe=%d",
                len(tickers),
            )
            # 사이클 93 신규 — stock_master upsert chain
            try:
                await _scanner_upsert_loop(tickers)
                logger.info("[universe_eager_refresh] stock_master upsert 완료")
            except Exception:
                logger.exception("[universe_eager_refresh] stock_master upsert 실패 graceful")
        except Exception:
            logger.exception("[universe_eager_refresh] 5분 주기 적재 실패")
        try:
            flush_universe_collector()
        except Exception:
            logger.exception("[universe_collector] flush 실패")
```

### 2.2 `src/routes/stock_master.py::refresh_universe_now` (L34~)

```python
async with _refresh_universe_lock:
    from src.engine.scanner import (
        fetch_top_500_universe,
        _universe_eager_refresh_loop as _scanner_upsert_loop,  # 사이클 93 신규
    )

    start_time = time.monotonic()
    try:
        tickers = await fetch_top_500_universe()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # 사이클 93 신규 — stock_master upsert chain
    try:
        await _scanner_upsert_loop(tickers)
    except Exception:
        logger.exception("[refresh_universe_now] stock_master upsert 실패 graceful")

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    # ... 응답 영속 ...
```

---

## 3. 회귀 가드 5 케이스 (HIGH 4 + LOW 1)

### G-CC1 (HIGH) — scheduler 개장 전 1회 분기

`tests/unit/engine/test_cycle93_scheduler_upsert_chain.py`

- mock `fetch_top_500_universe` → 5 ticker 반환
- mock `_universe_eager_refresh_loop` (scanner module) 호출 카운트
- scheduler `_universe_eager_refresh_loop` self method 호출 (`_running=False` 분기 우회 — 개장 전 1회만 실행)
- 의무: scanner module `_universe_eager_refresh_loop` 가 **5 ticker list 인자로 1회 호출**

### G-CC2 (HIGH) — scheduler 5분 주기 분기

`tests/unit/engine/test_cycle93_scheduler_5min_upsert_chain.py`

- freezegun + `asyncio.sleep` mock (5분 즉시 진행)
- mock `fetch_top_500_universe` → 5 ticker 반환 (개장 전 1회 + 5분 1회 = 2 회)
- 의무: 2회 호출 후 `_running=False` → scanner module `_universe_eager_refresh_loop` 가 **2 회 호출**

### G-CC3 (HIGH) — POST 라우트 chain

`tests/unit/routes/test_cycle93_route_upsert_chain.py`

- mock `fetch_top_500_universe` → 5 ticker 반환
- mock scanner module `_universe_eager_refresh_loop`
- POST `/api/stock-master/refresh-universe` 호출
- 의무: scanner module `_universe_eager_refresh_loop` 가 **5 ticker list 인자로 1회 호출** + 응답 200 + `data.universe=5`

### G-CC4 (HIGH) — graceful 영속

`tests/unit/engine/test_cycle93_upsert_graceful.py`

- mock `fetch_top_500_universe` → 5 ticker 반환
- mock scanner module `_universe_eager_refresh_loop` → `raise RuntimeError("upsert 실패")`
- scheduler `_universe_eager_refresh_loop` 본체 호출
- 의무: 예외 흡수 + 전체 chain 진행 (다음 사이트 도달 = `flush_universe_collector` 호출) + `caplog` ERROR ≥ 1건

### G-AST1 (LOW) — AST 영구 가드

`tests/unit/ast/test_cycle93_ast_chain_required.py`

- `src/engine/scheduler.py::_universe_eager_refresh_loop` 본체 AST 분석:
  - `_scanner_upsert_loop` 또는 `_universe_eager_refresh_loop` 호출 노드 ≥ 1건
- `src/routes/stock_master.py::refresh_universe_now` 본체 AST 분석:
  - `_scanner_upsert_loop` 또는 `_universe_eager_refresh_loop` 호출 노드 ≥ 1건
- **미래 silent 결함 영구 차단**: 신규 universe refresh 영역 추가 시 chain 누락 정적 검출

---

## 4. 영향 인덱스

- backend tests: 416 → **421** (+5 신규)
- backend modules: 99 영속 (production 코드 변경 0)
- frontend: 무영향
- 영향 인덱스 갱신: `_workspace/test_index.yaml` (Green 단계 직후 `build_index.py` 재실행)

---

## 5. 안전 가드 (Red 단계 의무)

- 모든 5 케이스 = **Red 상태로 작성** (Green 도달 전 FAIL 검증 의무)
- production 코드 변경 0 (Red 단계 의무, scheduler.py / routes/stock_master.py 무변경)
- 매매 안전성 무영향:
  - universe refresh = 시세/stock_master 영역, 매도/익일청산/15:20 강제청산 영향 0
  - 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호)
  - 사이클 38 명문화 영속 (`tradable_boards` 매수 진입 전용)
- WebSocket 4중 안전망 영속 / 사이클 17 KIS LMS chain 영역 무관

---

## 6. Green 검증 의무 (backend-dev 인계 후)

- 5 케이스 모두 PASS
- 백엔드 2255 → 2260 PASS (+5)
- 회귀 0건
- flakiness 0 (3 회 반복)
- coverage 영속
- 운영 효과 (push 후): stock_master `count_all` 60 → 점진 증가 + `[stock_master_bulk_refresh]` 정상 + `[universe_eager_refresh] stock_master upsert 완료` INFO 정상 발화
