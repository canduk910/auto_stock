# Red 명세 — 사이클 66 `_resubscribe_stale_priority` cap=10 결함 시정

> **작성**: 2026-06-06 (토) · team-leader
> **위험 등급**: **HIGH** (K stale watcher 영역, KIS LMS/앱키 정지 chain 직접 영역, 005935 사고 패턴)
> **Red 산출 대상**: `tests/unit/engine/stale_manager/test_cycle66_resubscribe_cap_priority_fix.py` (단일 파일, 11 케이스)
> **답습 기반**: 사이클 60/61/62/63 Red 명세 패턴 (freezegun + caplog + mock patch)
> **확정 근거**: `_workspace/cycle66_cap10_fix_design_card.md` v2 + `_workspace/cycle66_cap10_fix_domain_response.md` (Q1~Q6-6 옵션 A 전부 채택)

---

## 1. 시정 대상 코드 (재확인)

| 위치 | 함수 | 현 라인 | 시정 라인 수 |
|------|------|---------|-------------|
| `src/engine/stale_manager.py` | `resubscribe_stale_priority(scheduler, cap=10)` | L1023~L1034 | ~12L 교체 |

**시정 핵심**:
1. `high_tickers` 구성 = try/except 4중 가드로 본체 패턴 통일 (Q2)
2. priority 분리 *먼저* (Q1)
3. HIGH > cap 시 WARNING 로그 + HIGH 모두 보장 (Q3)
4. `targets = high_targets + low_targets[: max(0, cap - len(high_targets))]`

---

## 2. 회귀 가드 11 케이스 명세 (카테고리별)

> **HIGH 케이스 4 건 = tdd-engineer Red 단계 *전수 우선* 작성 의무** (사이클 60/61/63 답습)
> **freezegun 의무**: 모든 케이스 (stale 판정 = now - last_tick > 60s)
> **caplog 의무**: K-10 (WARNING 로그 발화 검증)
> **mock patch 경로**: `src.realtime.websocket_pool.kis_ws_pool` (사이클 63 답습 영속)

### 카테고리 K — 결함 시정 검증 (11 케이스: HIGH 4 / MEDIUM 2 / LOW 4 + AST 1)

| 번호 | 케이스 명 | 위험 | 검증 패턴 |
|------|----------|------|----------|
| **K-2 갱신** | 사이클 63 K-2 의미 전환 — HIGH 1 사전순 마지막 + LOW 12 + cap=10 시정 confirm | **HIGH** | stale_tickers = sorted(["000020", ..., "000200", "005935"]) (13건) + high_tickers={"005935"} + cap=10 → targets 에 "005935" 포함 (`assert "005935" in resubscribed`). **Q6-4 docstring 명시 의무 = 별도 검증** (test docstring 에 "사이클 63 결함 confirm → 사이클 66 시정 confirm" 명시) |
| **K-3 신규** | HIGH > cap 경계 (HIGH 12 + LOW 0 + cap=10 → HIGH 12 모두 통과) | **HIGH** | high_tickers = {12 종목 set} + LOW 0 + cap=10 → `len(resubscribed) == 12` + 모두 HIGH priority. `kis_ws_pool.subscribe.call_count == 12` |
| **K-4 신규** | HIGH 5 + LOW 20 + cap=10 (HIGH 사전순 후반) → HIGH 5 + LOW 5 | **HIGH** | stale_tickers sorted = LOW 20 + HIGH 5 (사전순 후반 위치) + cap=10 → `len(resubscribed) == 10` + HIGH 5 모두 포함 + LOW 5 만 포함 |
| K-5 신규 | HIGH 0 + LOW 20 + cap=10 (기존 동일 행위 보존) | LOW | high_tickers=set() + stale_tickers 20건 + cap=10 → `len(resubscribed) == 10` + 모두 LOW priority |
| K-6 신규 | HIGH 5 + LOW 0 + cap=10 → targets = HIGH 5개만 | LOW | high_tickers = 5종목 + LOW 0 + cap=10 → `len(resubscribed) == 5` + 모두 HIGH priority |
| K-7 신규 | stale_tickers 비어있음 → early return | LOW | ticker_last_tick = {} (모두 fresh) → `resubscribed == []` + `kis_ws_pool.subscribe.call_count == 0` |
| **K-8 신규** | `high_tickers` 구성 사이클 25-B HIGH/LOW 분리 일관 (positions ∪ next_day_clear) | **HIGH** | registry.positions = {"005930"} + `_pending_next_day_clear = {("005935", "VB")}` → high_tickers = {"005930", "005935"} 검증. registry 예외 던질 때 positions = set() 폴백 검증 (try/except 4중 가드 Q2) |
| **K-9 신규 (Q4 도메인)** | HIGH 0 + LOW 0 (둘 다 비어있음 edge) → early return | LOW | stale_tickers = [] + high_tickers = set() → `resubscribed == []` (K-7 과 동일 동작 보장) |
| **K-10 신규 (Q4 도메인)** | HIGH > cap 시 WARNING 로그 발화 검증 | **MEDIUM** | high_tickers = 12종목 stale + cap=10 → `write_log` patch + `assert_called_with(level="WARNING", message contains "[resubscribe_stale_priority] HIGH 종목 수 (12) > cap (10)")`. 발화 카운트 1회 정확 |
| **AST** | priority 분리 *후* cap 적용 정적 가드 | **MEDIUM** | `ast.parse(stale_manager.py)` 후 `resubscribe_stale_priority` 함수 본체 source 내:<br>1. `low_targets[: max(0, cap - len(high_targets))]` substring 존재 의무<br>2. `stale_tickers[:cap]` substring 부재 의무 (결함 영속 차단) |

---

## 3. 케이스별 상세 fixture / 검증

### K-2 갱신 (HIGH — 사이클 63 결함 confirm 의미 전환)

**Fixture**:
```python
@freeze_time("2026-06-08 10:00:00", tz_offset=9)
async def test_k2_high_1_low_12_cap_10_high_preserved_after_fix(monkeypatch, caplog):
    """사이클 63 K-2 결함 confirm → 사이클 66 시정 confirm (Q6-4 docstring 의무).

    사이클 63: targets = stale_tickers[:10] 로 HIGH "005935" cap 밖 잘림 → 결함 confirm PASS.
    사이클 66: priority 분리 *먼저* 적용으로 HIGH 절대 우선 → 시정 confirm PASS.
    """
    now = datetime.now(KST_TZ)
    stale_ts = now - timedelta(seconds=90)
    tickers = [f"{i:06d}" for i in range(20, 220, 20)] + ["005935"]  # sorted = 12 LOW + 1 HIGH (마지막)
    for t in tickers:
        ticker_last_tick[t] = stale_ts

    scheduler = make_scheduler_stub(positions={"005935"}, pending_ndc=set())
    mock_ws = AsyncMock()
    monkeypatch.setattr("src.realtime.websocket_pool.kis_ws_pool", mock_ws)

    resubscribed = await resubscribe_stale_priority(scheduler, cap=10)

    assert "005935" in resubscribed  # HIGH 절대 보장
    assert len(resubscribed) == 10
    # HIGH "005935" priority 검증
    high_calls = [c for c in mock_ws.subscribe.call_args_list if c.kwargs.get("priority") == "HIGH"]
    assert any(c.args[1] == "005935" for c in high_calls)
```

### K-3 (HIGH — HIGH > cap 모두 통과)

**Fixture**:
```python
@freeze_time("2026-06-08 10:00:00", tz_offset=9)
async def test_k3_high_12_low_0_cap_10_all_high_allowed(monkeypatch):
    """HIGH > cap 경계 — HIGH 12 + LOW 0 + cap=10 → HIGH 12 모두 통과 (Q3 옵션 A)."""
    now = datetime.now(KST_TZ)
    stale_ts = now - timedelta(seconds=90)
    high_tickers_set = {f"00{i:04d}" for i in range(1, 13)}  # 12 종목
    for t in high_tickers_set:
        ticker_last_tick[t] = stale_ts

    scheduler = make_scheduler_stub(positions=high_tickers_set, pending_ndc=set())
    mock_ws = AsyncMock()
    monkeypatch.setattr("src.realtime.websocket_pool.kis_ws_pool", mock_ws)

    resubscribed = await resubscribe_stale_priority(scheduler, cap=10)

    assert len(resubscribed) == 12  # cap=10 위반 허용
    assert mock_ws.subscribe.call_count == 12
    # 모두 HIGH priority
    for call in mock_ws.subscribe.call_args_list:
        assert call.kwargs["priority"] == "HIGH"
        assert call.kwargs["bypass_limit"] is True
```

### K-4 (HIGH — HIGH 5 + LOW 20 분리)

```python
@freeze_time("2026-06-08 10:00:00", tz_offset=9)
async def test_k4_high_5_low_20_cap_10_split_correctly(monkeypatch):
    """HIGH 5 + LOW 20 + cap=10 (HIGH 사전순 후반) → HIGH 5 + LOW 5."""
    now = datetime.now(KST_TZ)
    stale_ts = now - timedelta(seconds=90)
    low_tickers = {f"00{i:04d}" for i in range(1, 21)}  # 000001~000020 (LOW)
    high_tickers_set = {f"00{i:04d}" for i in range(50, 55)}  # 000050~000054 (사전순 후반)
    for t in low_tickers | high_tickers_set:
        ticker_last_tick[t] = stale_ts

    scheduler = make_scheduler_stub(positions=high_tickers_set, pending_ndc=set())
    mock_ws = AsyncMock()
    monkeypatch.setattr("src.realtime.websocket_pool.kis_ws_pool", mock_ws)

    resubscribed = await resubscribe_stale_priority(scheduler, cap=10)

    assert len(resubscribed) == 10
    high_in_result = [t for t in resubscribed if t in high_tickers_set]
    low_in_result = [t for t in resubscribed if t in low_tickers]
    assert len(high_in_result) == 5  # HIGH 5 모두 보장
    assert len(low_in_result) == 5  # LOW 잔여 cap = 5
```

### K-8 (HIGH — try/except 4중 가드 폴백 검증)

```python
@freeze_time("2026-06-08 10:00:00", tz_offset=9)
async def test_k8_registry_exception_falls_back_to_empty_positions(monkeypatch):
    """Q2 try/except 4중 — registry.all() 예외 시 positions=set() 폴백."""
    now = datetime.now(KST_TZ)
    stale_ts = now - timedelta(seconds=90)
    ticker_last_tick["005930"] = stale_ts

    scheduler = make_scheduler_stub(positions=None, pending_ndc={("005935", "VB")})
    # registry mock 이 예외 던지도록 강제
    mock_registry = MagicMock()
    mock_registry.all.side_effect = RuntimeError("registry crash")
    monkeypatch.setattr("src.engine.strategy_registry.registry", mock_registry)
    mock_ws = AsyncMock()
    monkeypatch.setattr("src.realtime.websocket_pool.kis_ws_pool", mock_ws)

    resubscribed = await resubscribe_stale_priority(scheduler, cap=10)

    # positions = set() 폴백 → high_tickers = {"005935"} (next_day_clear 만)
    # stale_tickers = ["005930"] → LOW 처리
    assert "005930" in resubscribed
    low_calls = [c for c in mock_ws.subscribe.call_args_list if c.kwargs.get("priority") == "LOW"]
    assert any(c.args[1] == "005930" for c in low_calls)
```

### K-10 (MEDIUM — WARNING 로그 발화)

```python
@freeze_time("2026-06-08 10:00:00", tz_offset=9)
async def test_k10_high_over_cap_emits_warning_log(monkeypatch):
    """Q3 — HIGH > cap 시 WARNING 로그 발화 검증."""
    now = datetime.now(KST_TZ)
    stale_ts = now - timedelta(seconds=90)
    high_tickers_set = {f"00{i:04d}" for i in range(1, 13)}  # 12 HIGH
    for t in high_tickers_set:
        ticker_last_tick[t] = stale_ts

    scheduler = make_scheduler_stub(positions=high_tickers_set, pending_ndc=set())
    mock_ws = AsyncMock()
    monkeypatch.setattr("src.realtime.websocket_pool.kis_ws_pool", mock_ws)
    mock_write_log = AsyncMock()
    monkeypatch.setattr("src.db.system_logs.write_log", mock_write_log)

    await resubscribe_stale_priority(scheduler, cap=10)

    # WARNING 로그 1회 발화 검증
    warning_calls = [
        c for c in mock_write_log.call_args_list
        if c.args[0] == "WARNING" and "HIGH 종목 수 (12) > cap (10)" in c.args[1]
    ]
    assert len(warning_calls) == 1
```

### AST (MEDIUM — 정적 가드)

```python
def test_ast_priority_split_before_cap_application():
    """priority 분리 *후* cap 적용 정적 가드 (G AST 가드 답습)."""
    import ast
    from pathlib import Path

    source = Path("src/engine/stale_manager.py").read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "resubscribe_stale_priority":
            func_source = ast.unparse(node)
            # 시정 안 substring 의무
            assert "low_targets[: max(0, cap - len(high_targets))]" in func_source, \
                "사이클 66 시정 안 (LOW 잔여 cap) 누락"
            # 결함 영속 차단
            assert "stale_tickers[:cap]" not in func_source, \
                "사이클 63 K-2 결함 (priority 분리 *전* cap 적용) 영속"
            break
    else:
        pytest.fail("resubscribe_stale_priority 함수 미발견")
```

---

## 4. fixture helper

```python
def make_scheduler_stub(positions: set[str] | None, pending_ndc: set[tuple[str, str]]):
    """scheduler 스텁 — registry.all() + _pending_next_day_clear + _stale_last_resubscribe_at."""
    scheduler = MagicMock()
    if positions is not None:
        strategy_mock = MagicMock()
        strategy_mock.state.positions = {t: MagicMock() for t in positions}
        scheduler.registry.all.return_value = [strategy_mock]
    else:
        scheduler.registry.all.return_value = []
    scheduler._pending_next_day_clear = pending_ndc
    scheduler._stale_last_resubscribe_at = {}
    return scheduler


@pytest.fixture(autouse=True)
def clear_ticker_last_tick():
    """각 케이스 전후 ticker_last_tick 격리."""
    from src.engine.scanner import ticker_last_tick
    ticker_last_tick.clear()
    yield
    ticker_last_tick.clear()
```

---

## 5. 검증 후 산출 보고서

tdd-engineer Red 단계 완료 시:

| 항목 | 기대 결과 |
|------|----------|
| 케이스 총 수 | **11** (K-2 갱신 + K-3~K-10 신규 + AST) |
| HIGH 케이스 | **4** (K-2, K-3, K-4, K-8) — 전수 우선 작성 |
| MEDIUM 케이스 | **2** (K-10, AST) |
| LOW 케이스 | **4** (K-5, K-6, K-7, K-9) |
| Red 단계 PASS 케이스 | **K-2 만** (현 결함 코드 그대로 = 결함 confirm PASS, 사이클 63 의미 영속) |
| Red 단계 FAIL 케이스 | **K-3, K-4, K-8 (그리고 K-10 WARNING + AST)** = 10건 — Green 시정 후 PASS 전환 |
| freezegun 사용 케이스 | 11건 전부 |
| caplog/mock write_log 사용 케이스 | K-10 1건 |
| AST 정적 가드 | 1건 (AST) |

---

## 6. backend-dev Green 인계 사항

1. **단일 파일 단일 함수 시정** — `src/engine/stale_manager.py::resubscribe_stale_priority` L1023~L1034 본체만
2. **호환 layer / wrapper 변경 0** — scheduler.py wrapper (L2690~L2789) 무변경
3. **K stale watcher 본체 (`check_and_resubscribe_stale`) 변경 0** — 사이클 63 A3 답습 본체 보존
4. **docstring 갱신 의무 (Q6-4)** — "사이클 63 결함 confirm → 사이클 66 시정 confirm" 문구 추가
5. **try/except 4중 가드 본체 패턴 답습** — `_check_and_resubscribe_stale` L820~L831 (또는 stale_manager 본체 함수) 패턴 그대로

---

## 7. tester Verify 인계 사항 (V1~V13 + V-AST + V-A3)

| Verify | 검증 |
|--------|------|
| V1~V13 | 백엔드 전체 회귀 (pytest 전체 PASS, 사이클 65 시점 1748 → +11 = ~1759) |
| V-AST | AST 정적 가드 케이스 PASS |
| V-A3 (월요일 1h) | 시나리오 A/B/C/D 결합 효과 측정 (Q5 신규 시나리오 D 포함) |
| 신규 측정 지표 3 | (1) HIGH/LOW 분포 (2) WARNING 발화 카운트 (3) HIGH 누락 0건 |
