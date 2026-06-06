# 사이클 65 거래대금 동행 필터 — Red 명세 (tdd-engineer 발주서)

> **작성**: team-leader (2026-06-06 KST)
> **선행 카드**: `_workspace/cycle65_trade_amount_filter_design_card.md` v2 (자문 옵션 A 전부 적용)
> **선행 자문**: `_workspace/cycle65_trade_amount_filter_domain_response.md`
> **위험 등급**: **HIGH** (작전주 차단 유일 메커니즘 + 사이클 64 답습)
> **회귀 가드 합계**: **28 케이스** (HIGH 3 / MEDIUM 8 / LOW 17)
> **목표**: 28 케이스 전부 Red (현 시점 Green 구현 0 → 전부 실패) 작성 → backend-dev + frontend-dev 병렬 Green 발주

---

## 0. 발주 원칙 (tdd-engineer 의무)

1. **Red 우선**: 28 케이스 전부 실패 검증 — `python -m pytest tests/unit/.../test_cycle65_*.py` 가 28 fail 도달 확인 후 인계
2. **분리 파일 12 청사진 (백엔드 9 + 프론트 1 + integration 2)** — 단일 파일 비대화 방지 (사이클 64 답습)
3. **사이클 64 fixture 재사용** — 보유/익일청산 protected_tickers mock 패턴, scanner mock 패턴, DailyEmitCap mock 패턴, AST walk 패턴
4. **테스트 격리 의무** — `_trade_amount_filter_cache` / `_trade_amount_filter_scanner_skip_logged_today` / `_trade_amount_filter_scanner_skip_count_today` autouse fixture reset
5. **회귀 가드 위치 일관** — 사이클 64 디렉토리 패턴 답습 (`tests/unit/db/`, `tests/unit/engine/scanner/`, `tests/unit/routes/`, `tests/integration/`, `frontend/src/components/__tests__/`)

---

## 1. 분리 파일 청사진 (12 파일)

| # | 파일 경로 | 케이스 | 카테고리 |
|---|---|---|---|
| 1 | `tests/unit/db/test_cycle65_trade_amount_filter_config.py` | A-1, A-2, A-3 | A `system_config` (3) |
| 2 | `tests/unit/engine/scanner/test_cycle65_apply_trade_amount_filter.py` | B-1, B-2, B-3, B-4 | B `_apply_trade_amount_filter` 본체 (4) |
| 3 | `tests/unit/engine/scanner/test_cycle65_get_acml_tr_pbmn_fallback.py` | B-5 | B-5 옵션 C 통합 폴백 (1) |
| 4 | `tests/unit/engine/scanner/test_cycle65_trade_amount_filter_protected.py` | C-1, C-2 | C 보유/익일청산 보호 (2, HIGH) |
| 5 | `tests/unit/engine/scanner/test_cycle65_trade_amount_filter_cache.py` | D-1, D-2, E-1, E-2 | D 캐시 + E DailyEmitCap (4) |
| 6 | `tests/unit/engine/scanner/test_cycle65_trade_amount_filter_ast_guards.py` | G-1, H-2 (AST) | G AST keyword 의무 (1, HIGH) + H-2 AST 직접 호출 |
| 7 | `tests/unit/engine/scanner/test_cycle65_daily_summary.py` | H-1 | H scanner daily_summary (1) |
| 8 | `tests/unit/engine/test_cycle65_scheduler_integration.py` | H-2 (호출 동작) | H-2 scheduler 통합 (1) |
| 9 | `tests/unit/routes/test_cycle65_trade_amount_filter_route.py` | C-R-1 | C-Route API (1) |
| 10 | `tests/integration/test_cycle65_trade_amount_filter_e2e.py` | F-1, F-2, F-3, F-4 | F integration E2E (4) |
| 11 | `tests/integration/test_cycle65_trade_amount_filter_option_c_race.py` | I-1, I-2 | I integration Q6 자문 신규 (2) |
| 12 | `frontend/src/components/__tests__/TradeAmountFilterCard.test.tsx` | F-FE-1, F-FE-2, F-FE-3, F-FE-4 | F-FE 프론트 (4) |

**합계**: 백엔드 11 파일 × 24 케이스 + 프론트 1 파일 × 4 케이스 = **12 파일 × 28 케이스**

---

## 2. 케이스 상세 명세 (28)

### File 1 — `tests/unit/db/test_cycle65_trade_amount_filter_config.py` (3)

#### A-1 [LOW] `get_trade_amount_filter` 디폴트
```python
import pytest
from src.db import system_config

@pytest.mark.asyncio
async def test_get_trade_amount_filter_default():
    """미설정 시 min_amount=0 + is_active=False 반환."""
    # supabase mock: row 미존재 시
    with mock_supabase_select_returns([]):
        taf = await system_config.get_trade_amount_filter()
        assert taf.min_amount == 0
        assert taf.is_active is False
```

#### A-2 [LOW] `set_trade_amount_filter(min_amount=100_000_000)` 갱신 + 재조회 일치
```python
@pytest.mark.asyncio
async def test_set_then_get_trade_amount_filter():
    await system_config.set_trade_amount_filter(min_amount=100_000_000)
    taf = await system_config.get_trade_amount_filter()
    assert taf.min_amount == 100_000_000
    assert taf.is_active is True
```

#### A-3 [LOW] `set_trade_amount_filter(min_amount=-1)` → ValueError
```python
@pytest.mark.asyncio
async def test_set_trade_amount_filter_negative_raises():
    with pytest.raises(ValueError):
        await system_config.set_trade_amount_filter(min_amount=-1)
```

---

### File 2 — `tests/unit/engine/scanner/test_cycle65_apply_trade_amount_filter.py` (4)

#### B-1 [LOW] 비활성 → 모든 후보 통과
```python
import pytest
from src.engine import scanner
from src.db.system_config import TradeAmountFilter

@pytest.mark.asyncio
async def test_apply_trade_amount_filter_inactive_passes_all(monkeypatch):
    """min_amount=0 (비활성) → 모든 후보 통과 (Q6-1 09:00 race 영속)."""
    async def _stub_get():
        return TradeAmountFilter(min_amount=0)
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)

    survivors = await scanner._apply_trade_amount_filter(
        ["A001", "A002", "A003"], protected_tickers=set()
    )
    assert survivors == ["A001", "A002", "A003"]
```

#### B-2 [LOW] 임계 미만 차단
```python
@pytest.mark.asyncio
async def test_apply_trade_amount_filter_below_min_excluded(monkeypatch):
    """min_amount=1억, 후보 trade_amount_raw=5천만 → 차단."""
    async def _stub_get():
        return TradeAmountFilter(min_amount=100_000_000)  # 1억
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "A001": {"trade_amount_raw": 50_000_000},  # 5천만
    })
    survivors = await scanner._apply_trade_amount_filter(
        ["A001"], protected_tickers=set()
    )
    assert survivors == []
```

#### B-3 [LOW] 미확보 graceful 통과 (Q6-1 영속)
```python
@pytest.mark.asyncio
async def test_apply_trade_amount_filter_missing_data_graceful_passes(monkeypatch):
    """양쪽 miss → _get_acml_tr_pbmn=0 → graceful 통과 (Q6-1 09:00 race)."""
    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)
    monkeypatch.setattr(scanner, "ticker_market_info", {})  # scanner miss
    # stock_master mock: get() returns None
    monkeypatch.setattr(
        "src.db.stock_master.get",
        AsyncMock(return_value=None),
    )
    survivors = await scanner._apply_trade_amount_filter(
        ["A001"], protected_tickers=set()
    )
    assert survivors == ["A001"]  # graceful 통과
```

#### B-4 [LOW] 임계 이상 통과
```python
@pytest.mark.asyncio
async def test_apply_trade_amount_filter_above_min_passes(monkeypatch):
    """min_amount=1억, 후보 trade_amount_raw=50억 → 통과."""
    async def _stub_get():
        return TradeAmountFilter(min_amount=100_000_000)
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "A001": {"trade_amount_raw": 5_000_000_000},  # 50억
    })
    survivors = await scanner._apply_trade_amount_filter(
        ["A001"], protected_tickers=set()
    )
    assert survivors == ["A001"]
```

---

### File 3 — `tests/unit/engine/scanner/test_cycle65_get_acml_tr_pbmn_fallback.py` (1)

#### B-5 [MEDIUM 자문 신규] Q2 옵션 C 통합 폴백 검증 (3 경로)
```python
@pytest.mark.asyncio
async def test_get_acml_tr_pbmn_scanner_first_hit(monkeypatch):
    """1순위 — scanner ticker_market_info hit."""
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "A001": {"trade_amount_raw": 30_000_000_000},  # 300억
    })
    # stock_master 호출되면 안 됨
    sm_mock = AsyncMock()
    monkeypatch.setattr("src.db.stock_master.get", sm_mock)
    result = await scanner._get_acml_tr_pbmn("A001")
    assert result == 30_000_000_000
    sm_mock.assert_not_called()

@pytest.mark.asyncio
async def test_get_acml_tr_pbmn_scanner_miss_stock_master_hit(monkeypatch):
    """2순위 — scanner miss 후 stock_master.raw.acml_tr_pbmn hit."""
    monkeypatch.setattr(scanner, "ticker_market_info", {})
    basics = MagicMock()
    basics.raw = {"acml_tr_pbmn": "15000000000"}  # 150억 (문자열)
    monkeypatch.setattr("src.db.stock_master.get", AsyncMock(return_value=basics))
    result = await scanner._get_acml_tr_pbmn("A001")
    assert result == 15_000_000_000

@pytest.mark.asyncio
async def test_get_acml_tr_pbmn_both_miss_returns_zero(monkeypatch):
    """둘 다 miss → 0 반환 (graceful 통과 위임)."""
    monkeypatch.setattr(scanner, "ticker_market_info", {})
    monkeypatch.setattr("src.db.stock_master.get", AsyncMock(return_value=None))
    result = await scanner._get_acml_tr_pbmn("A001")
    assert result == 0
```

> **단일 케이스 B-5 가 3 함수로 분리** — pytest 1 케이스 = 1 시나리오 분기 (Q2 옵션 C 3 경로 정합성)

---

### File 4 — `tests/unit/engine/scanner/test_cycle65_trade_amount_filter_protected.py` (2, HIGH)

#### C-1 [HIGH] 보유 종목 → 거래대금 50만이어도 통과
```python
@pytest.mark.asyncio
async def test_protected_position_passes_below_threshold(monkeypatch):
    """보유 종목 (positions) → 거래대금 50만이어도 통과 (3 중 안전망)."""
    async def _stub_get():
        return TradeAmountFilter(min_amount=10_000_000_000)  # 100억
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "A001": {"trade_amount_raw": 500_000},  # 50만
    })
    # protected_tickers 에 A001 포함
    survivors = await scanner._apply_trade_amount_filter(
        ["A001"], protected_tickers={"A001"}
    )
    assert survivors == ["A001"]  # 거래대금 절대 미만이어도 통과
```

#### C-2 [HIGH] 익일청산 → 거래대금 100만이어도 통과
```python
@pytest.mark.asyncio
async def test_protected_next_day_clear_passes_below_threshold(monkeypatch):
    """익일청산 종목 → 거래대금 100만이어도 통과."""
    async def _stub_get():
        return TradeAmountFilter(min_amount=10_000_000_000)
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "B999": {"trade_amount_raw": 1_000_000},
    })
    survivors = await scanner._apply_trade_amount_filter(
        ["B999"], protected_tickers={"B999"}
    )
    assert survivors == ["B999"]
```

---

### File 5 — `tests/unit/engine/scanner/test_cycle65_trade_amount_filter_cache.py` (4)

#### D-1 [MEDIUM] 60s 내 재호출 시 DB 미조회
```python
@pytest.mark.asyncio
async def test_cache_hit_within_ttl(monkeypatch):
    """60s 내 재호출 — get_trade_amount_filter DB call 1회만."""
    db_call_count = 0
    async def _stub_db():
        nonlocal db_call_count
        db_call_count += 1
        return TradeAmountFilter(min_amount=1_000_000_000)
    monkeypatch.setattr(
        "src.engine.scanner.get_trade_amount_filter", _stub_db
    )
    # cache reset
    scanner._trade_amount_filter_cache = None
    scanner._trade_amount_filter_cache_expires_at = 0.0

    await scanner._get_trade_amount_filter_for_scanner()
    await scanner._get_trade_amount_filter_for_scanner()
    await scanner._get_trade_amount_filter_for_scanner()
    assert db_call_count == 1
```

#### D-2 [LOW] invalidate 후 unsubscribe 발화 0 (Q7-1)
```python
def test_invalidate_does_not_trigger_unsubscribe(monkeypatch):
    """invalidate_trade_amount_filter_cache_scanner 가 ws.unsubscribe 호출 0."""
    ws_unsub_mock = MagicMock()
    monkeypatch.setattr("src.realtime.websocket.unsubscribe", ws_unsub_mock)
    monkeypatch.setattr(
        "src.realtime.websocket_pool.unsubscribe", ws_unsub_mock, raising=False,
    )

    scanner._trade_amount_filter_cache = TradeAmountFilter(min_amount=1_000_000_000)
    scanner.invalidate_trade_amount_filter_cache_scanner()
    assert scanner._trade_amount_filter_cache is None
    ws_unsub_mock.assert_not_called()  # KIS LMS chain 차단 (Q7-1)
```

#### E-1 [LOW] 동일 ticker 차단 2회 → write_log 1회만 호출
```python
@pytest.mark.asyncio
async def test_emit_cap_logs_once_per_ticker(monkeypatch):
    """동일 ticker 차단 2회 → system_logs write_log 1회만 발화."""
    write_log_mock = AsyncMock()
    monkeypatch.setattr("src.db.system_logs.write_log", write_log_mock)
    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "A001": {"trade_amount_raw": 50_000_000},
    })

    scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())
    await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())
    assert write_log_mock.call_count == 1
```

#### E-2 [LOW] reset 후 동일 ticker 차단 → write_log 재호출
```python
@pytest.mark.asyncio
async def test_reset_daily_state_re_enables_emit(monkeypatch):
    """reset_trade_amount_filter_daily_state 후 동일 ticker → write_log 재호출."""
    write_log_mock = AsyncMock()
    monkeypatch.setattr("src.db.system_logs.write_log", write_log_mock)
    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "A001": {"trade_amount_raw": 50_000_000},
    })

    scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())
    scanner.reset_trade_amount_filter_daily_state()
    await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())
    assert write_log_mock.call_count == 2
```

---

### File 6 — `tests/unit/engine/scanner/test_cycle65_trade_amount_filter_ast_guards.py` (G-1 + H-2 AST 2 함수)

#### G-1 [HIGH] `_apply_trade_amount_filter` 호출은 `protected_tickers=` keyword 의무
```python
import ast

def test_apply_trade_amount_filter_calls_must_pass_protected_tickers_kwarg():
    """`_apply_trade_amount_filter` 호출은 `protected_tickers=` keyword-only 의무.

    Q1 옵션 D 답습 — 누락 시 보유 종목 거래대금 필터 차단 위험 (HIGH).
    사이클 64 G-2 패턴 답습.
    """
    src = open("src/engine/scanner.py", encoding="utf-8").read()
    tree = ast.parse(src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name == "_apply_trade_amount_filter":
                kw_keys = {kw.arg for kw in node.keywords if kw.arg}
                if "protected_tickers" not in kw_keys:
                    violations.append(node.lineno)
    assert not violations, (
        f"_apply_trade_amount_filter 호출에 protected_tickers= keyword 누락 "
        f"(lines={violations}) — Q1 옵션 D 위반"
    )

def test_apply_trade_amount_filter_call_count_in_subscribe_filtered_stocks():
    """subscribe_filtered_stocks 내부에서 _apply_trade_amount_filter 호출 4회 의무.

    호출 위치: tickers (1) + extra_tickers (1) + priority_groups 3 키 (breakout/momentum/swing).
    누락 시 일부 priority key 만 필터 적용 = 회귀.
    """
    src = open("src/engine/scanner.py", encoding="utf-8").read()
    tree = ast.parse(src)
    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "subscribe_filtered_stocks":
            target_func = node
            break
    assert target_func is not None, "subscribe_filtered_stocks 함수 미발견"
    call_count = 0
    for node in ast.walk(target_func):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if name == "_apply_trade_amount_filter":
                call_count += 1
    assert call_count == 4, f"호출 4회 의무 (실제 {call_count}회)"
```

> H-2 AST 케이스 (scheduler 직접 호출 try/except 감싸지 않음) 는 File 8 에서 통합.

---

### File 7 — `tests/unit/engine/scanner/test_cycle65_daily_summary.py` (1)

#### H-1 [LOW] daily_summary INSERT prefix 검증
```python
@pytest.mark.asyncio
async def test_daily_summary_writes_with_correct_prefix(monkeypatch):
    """emit_trade_amount_filter_scanner_daily_summary → system_logs INSERT prefix 검증."""
    write_log_mock = AsyncMock()
    monkeypatch.setattr("src.db.system_logs.write_log", write_log_mock)
    scanner._trade_amount_filter_scanner_skip_count_today["total"] = 42

    await scanner.emit_trade_amount_filter_scanner_daily_summary()
    write_log_mock.assert_called_once()
    args = write_log_mock.call_args
    assert args[0][0] == "INFO"
    assert "[trade_amount_filter_scanner_daily_summary]" in args[0][1]
    assert "block_count=42" in args[0][1]
```

---

### File 8 — `tests/unit/engine/test_cycle65_scheduler_integration.py` (1)

#### H-2 [MEDIUM] scheduler `_settle()` 가 daily_summary 직접 호출 + AST 가드
```python
@pytest.mark.asyncio
async def test_scheduler_settle_invokes_trade_amount_daily_summary(monkeypatch):
    """scheduler._settle() 진입 직전 emit_trade_amount_filter_scanner_daily_summary 호출 의무.

    사이클 64 hotfix H-2 패턴 답습 — 직접 호출 (AttributeError 가드 X).
    """
    from src.engine import scheduler as sched_module
    emit_price_mock = AsyncMock()
    emit_trade_mock = AsyncMock()
    monkeypatch.setattr(
        "src.engine.scanner.emit_price_filter_scanner_daily_summary", emit_price_mock,
    )
    monkeypatch.setattr(
        "src.engine.scanner.emit_trade_amount_filter_scanner_daily_summary", emit_trade_mock,
    )
    ts = sched_module.TradingScheduler()
    # _settle 내부 다른 의존성 mock (필요 시)
    ...
    await ts._settle()
    emit_trade_mock.assert_called_once()

def test_scheduler_settle_calls_emit_trade_amount_directly_no_try_except():
    """AST 가드 — scheduler._settle 내부에서 emit_trade_amount_filter_scanner_daily_summary 호출이
    try/except 로 감싸이지 않음 (사이클 64 hotfix H-2 영구 패턴 답습).

    감싸이면 AttributeError 가 silent 되어 회귀 가시화 불가.
    """
    src = open("src/engine/scheduler.py", encoding="utf-8").read()
    tree = ast.parse(src)
    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_settle":
            target_func = node
            break
    # 호출 노드 추출
    violations = []
    for node in ast.walk(target_func):
        if isinstance(node, ast.Try):
            for try_node in ast.walk(node):
                if isinstance(try_node, ast.Call):
                    fn = try_node.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else None)
                    if name == "emit_trade_amount_filter_scanner_daily_summary":
                        violations.append(node.lineno)
    assert not violations, (
        f"emit_trade_amount_filter_scanner_daily_summary 호출이 try/except 로 감싸짐 "
        f"(lines={violations}) — 사이클 64 hotfix H-2 영구 패턴 위반"
    )

def test_scheduler_reset_daily_state_calls_reset_trade_amount():
    """AST 가드 — _reset_daily_state 가 reset_trade_amount_filter_daily_state 호출 의무."""
    src = open("src/engine/scheduler.py", encoding="utf-8").read()
    tree = ast.parse(src)
    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_reset_daily_state":
            target_func = node
            break
    found = False
    for node in ast.walk(target_func):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else None)
            if name == "reset_trade_amount_filter_daily_state":
                found = True
                break
    assert found, "_reset_daily_state 가 reset_trade_amount_filter_daily_state 호출 누락"
```

---

### File 9 — `tests/unit/routes/test_cycle65_trade_amount_filter_route.py` (1)

#### C-R-1 [MEDIUM] PUT body 검증 (extra=forbid 422 + 음수 400 + 정상 invalidate)
```python
import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_put_extra_field_returns_422():
    """extra 키 → 422 (extra=forbid)."""
    res = client.put("/api/system/trade-amount-filter", json={
        "min_amount": 100_000_000,
        "unexpected_key": 42,
    })
    assert res.status_code == 422

def test_put_negative_returns_400():
    """min_amount=-1 → 400 (ValueError)."""
    res = client.put("/api/system/trade-amount-filter", json={"min_amount": -1})
    assert res.status_code == 400

def test_put_normal_invokes_invalidate(monkeypatch):
    """정상 PUT → invalidate_trade_amount_filter_cache_scanner 호출 검증."""
    inv_mock = MagicMock()
    monkeypatch.setattr(
        "src.engine.scanner.invalidate_trade_amount_filter_cache_scanner", inv_mock,
    )
    res = client.put("/api/system/trade-amount-filter", json={"min_amount": 100_000_000})
    assert res.status_code == 200
    inv_mock.assert_called_once()
```

---

### File 10 — `tests/integration/test_cycle65_trade_amount_filter_e2e.py` (4)

#### F-1 [MEDIUM] scan → price → trade_amount → subscribe 정합성
```python
@pytest.mark.asyncio
async def test_e2e_scan_then_price_then_trade_amount_then_subscribe(monkeypatch):
    """scan 결과 → _apply_price_filter → _apply_trade_amount_filter → ws.subscribe.

    사이클 64 + 65 연속 호출 검증 — 호출 순서 + survivors 흐름.
    """
    # mock subscribe / price filter / trade amount filter
    ...
    # subscribe_filtered_stocks 진입 → 4 호출 순서 검증 (call_args_list)
```

#### F-2 [MEDIUM] 보유 종목 보호 E2E (가격 + 거래대금 양쪽 통과)
```python
@pytest.mark.asyncio
async def test_e2e_held_position_protected_across_both_filters(monkeypatch):
    """보유 종목 → 가격 필터 + 거래대금 필터 양쪽 통과 (3 중 안전망 일관)."""
    ...
```

#### F-3 [LOW] funnel hook step_no=97 INSERT
```python
@pytest.mark.asyncio
async def test_funnel_hook_step_no_97_inserted(monkeypatch):
    """_apply_trade_amount_filter 활성 시 strategy_funnel_snapshots step_no=97 INSERT."""
    insert_mock = AsyncMock()
    monkeypatch.setattr("src.db.strategy_funnel.insert_snapshot", insert_mock)
    ...
    await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())
    insert_mock.assert_called_once()
    kwargs = insert_mock.call_args.kwargs
    assert kwargs["step_no"] == 97
    assert kwargs["step_name"] == "trade_amount_filter_scanner"
```

#### F-4 [LOW 자문 신규] 사이클 64+65 순차 hook E2E (가격 차단 → 거래대금 미도달)
```python
@pytest.mark.asyncio
async def test_e2e_price_blocked_ticker_does_not_reach_trade_amount(monkeypatch):
    """가격 필터로 차단된 종목은 거래대금 필터 호출 대상에 포함 안 됨.

    순차 hook 검증 — Q3 옵션 A 패턴.
    """
    # _apply_price_filter mock: ["A001"] → [] (차단)
    # _apply_trade_amount_filter spy: 호출 시 candidates 인자 = [] 검증
    ...
```

---

### File 11 — `tests/integration/test_cycle65_trade_amount_filter_option_c_race.py` (2, 자문 신규)

#### I-1 [MEDIUM] 옵션 C 통합 폴백 정합성 (`ticker_market_info["trade_amount_raw"]` 키 존재)
```python
@pytest.mark.asyncio
async def test_scanner_populates_trade_amount_raw_key(monkeypatch):
    """scanner._scan_stocks 가 ticker_market_info 에 trade_amount_raw 키 보강 검증.

    scanner.py:453 변경 정합성 — 기존 trade_amount (억 단위) 보존 + 신규 trade_amount_raw (원 단위).
    """
    # mock fetch_rising_stocks → 후보 1건
    fake_raw = [{
        "stck_shrn_iscd": "A001",
        "hts_kor_isnm": "테스트종목",
        "prdy_ctrt": "20.0",
        "stck_prpr": "5000",
        "lstn_stcn": "100000000",  # 1억주
        "acml_tr_pbmn": "30000000000",  # 300억
    }]
    monkeypatch.setattr(
        "src.engine.scanner.fetch_rising_stocks", AsyncMock(return_value=fake_raw),
    )
    await scanner.scan_stocks()
    info = scanner.ticker_market_info.get("A001")
    assert info is not None
    assert info["trade_amount_raw"] == 30_000_000_000  # 원 단위 정밀값
    assert info["trade_amount"] == 300  # 억 단위 (기존 호환)
```

#### I-2 [LOW] Q6-1 09:00 race 영속 검증
```python
@pytest.mark.asyncio
async def test_q6_1_09am_race_graceful_no_emit(monkeypatch):
    """09:00 직후 trade_amount_raw=0 + stock_master.raw.acml_tr_pbmn=0 → graceful 통과 + emit 0.

    Q6-1 HIGH 영속 — 시스템 매매 무용 위험 차단.
    """
    write_log_mock = AsyncMock()
    monkeypatch.setattr("src.db.system_logs.write_log", write_log_mock)

    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)  # 10억 활성
    monkeypatch.setattr(scanner, "_get_trade_amount_filter_for_scanner", _stub_get)

    # scanner 1순위 — trade_amount_raw=0
    monkeypatch.setattr(scanner, "ticker_market_info", {
        "A001": {"trade_amount_raw": 0},  # 09:00 직후 누적 미반영
    })
    # stock_master 2순위 — acml_tr_pbmn=0 (장중 reset 가정)
    basics = MagicMock()
    basics.raw = {"acml_tr_pbmn": "0"}
    monkeypatch.setattr("src.db.stock_master.get", AsyncMock(return_value=basics))

    scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    survivors = await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())
    assert survivors == ["A001"]  # graceful 통과

    # write_log 호출 0 — skip emit 미발화 (filter pass)
    write_log_calls_for_skip = [
        c for c in write_log_mock.call_args_list
        if "[trade_amount_filter_scanner_skip]" in str(c)
    ]
    assert len(write_log_calls_for_skip) == 0
```

---

### File 12 — `frontend/src/components/__tests__/TradeAmountFilterCard.test.tsx` (4)

#### F-FE-1 [LOW] 초기 fetch + 슬라이더 렌더 (디폴트 0)
```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { TradeAmountFilterCard } from '../TradeAmountFilterCard'

test('초기 fetch + 슬라이더 디폴트 0 렌더', async () => {
  // MSW: GET /api/system/trade-amount-filter → { min_amount: 0 }
  render(<TradeAmountFilterCard />)
  const slider = await screen.findByTestId('trade-amount-filter-min-slider')
  expect(slider).toHaveValue('0')
})
```

#### F-FE-2 [LOW] 슬라이더 조작 + 저장 → PUT body
```tsx
test('슬라이더 조작 후 저장 → PUT body 검증', async () => {
  // MSW: PUT spy, slider input event 100억
  ...
  expect(putBody).toEqual({ min_amount: 10_000_000_000 })
})
```

#### F-FE-3 [LOW] 권장값 마커 (1억/5억/10억) 빠른 선택 버튼
```tsx
test('권장값 마커 버튼 클릭 시 슬라이더 값 갱신', async () => {
  render(<TradeAmountFilterCard />)
  const btn5 = await screen.findByRole('button', { name: /5억/ })
  fireEvent.click(btn5)
  const slider = screen.getByTestId('trade-amount-filter-min-slider')
  expect(slider).toHaveValue('500000000')
})
```

#### F-FE-4 [MEDIUM 자문 신규] 안내 배너 텍스트 검증
```tsx
test('안내 배너 — 보유/익일청산 보호 + Q6-1 09:00 race graceful 명시', async () => {
  render(<TradeAmountFilterCard />)
  expect(await screen.findByText(/보유.*익일청산.*절대 제외 안 됨/)).toBeInTheDocument()
  expect(screen.getByText(/09:00.*graceful.*Q6-1/)).toBeInTheDocument()
})
```

---

## 3. autouse fixture (각 백엔드 파일 상단 의무)

```python
@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 scanner 모듈 전역 reset — 테스트 격리 의무."""
    from src.engine import scanner
    scanner._trade_amount_filter_cache = None
    scanner._trade_amount_filter_cache_expires_at = 0.0
    scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    for k in scanner._trade_amount_filter_scanner_skip_count_today:
        scanner._trade_amount_filter_scanner_skip_count_today[k] = 0
    yield
    scanner._trade_amount_filter_cache = None
    scanner._trade_amount_filter_cache_expires_at = 0.0
    scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    for k in scanner._trade_amount_filter_scanner_skip_count_today:
        scanner._trade_amount_filter_scanner_skip_count_today[k] = 0
```

---

## 4. 사이클 64 fixture 재사용 매트릭스

| fixture | 사이클 64 출처 | 사이클 65 재사용 |
|---|---|---|
| `protected_tickers` mock | sca64 C-1/C-2 | ✅ C-1/C-2 동일 패턴 |
| scanner module reset | sca64 autouse | ✅ 위 autouse 패턴 답습 |
| DailyEmitCap reset | sca64 E-1/E-2 | ✅ E-1/E-2 동일 패턴 |
| AST walk (`_apply_price_filter` 호출 검증) | sca64 G-2 | ✅ G-1 패턴 답습 (이름만 변경) |
| supabase mock | sca64 A-1~A-3 | ✅ A-1~A-3 동일 패턴 |
| FastAPI TestClient | sca64 C-R-1 | ✅ C-R-1 동일 패턴 |
| MSW (frontend) | sca64 F-FE-1~F-FE-4 | ✅ F-FE-1~F-FE-4 동일 패턴 |

---

## 5. Red 검증 절차 (tdd-engineer 의무)

1. 12 파일 28 케이스 작성 후 `python -m pytest tests/unit/db/test_cycle65_*.py tests/unit/engine/scanner/test_cycle65_*.py tests/unit/engine/test_cycle65_*.py tests/unit/routes/test_cycle65_*.py tests/integration/test_cycle65_*.py -q` 실행
2. **28 fail** 확인 (구현 영역 0 → 전부 ImportError/AttributeError/NameError)
3. 프론트엔드 `cd frontend && npm test src/components/__tests__/TradeAmountFilterCard.test.tsx -- --run` → **4 fail** 확인
4. 백엔드 + 프론트 합계 **32 fail (28 + 4)** 도달 후 team-leader 에게 보고
5. team-leader 가 backend-dev + frontend-dev 병렬 Green 발주

---

## 6. Green 발주 시 backend-dev / frontend-dev 인계 정보

### backend-dev 인계 (Green 구현 영역)

- `src/db/system_config.py` — `TradeAmountFilter` 모델 + `get_trade_amount_filter` + `set_trade_amount_filter` (3 함수)
- `src/engine/scanner.py` — **(1)** `ticker_market_info[ticker]` 에 `trade_amount_raw` 키 추가 (line 453) **(2)** `_apply_trade_amount_filter` + `_get_acml_tr_pbmn` + `_get_trade_amount_filter_for_scanner` + `invalidate_trade_amount_filter_cache_scanner` + `emit_trade_amount_filter_scanner_daily_summary` + `reset_trade_amount_filter_daily_state` + 모듈 전역 캐시 변수 4개 (`_trade_amount_filter_cache` / `_trade_amount_filter_cache_expires_at` / `_trade_amount_filter_scanner_skip_logged_today` / `_trade_amount_filter_scanner_skip_count_today`) **(3)** `subscribe_filtered_stocks` 내부 `_apply_trade_amount_filter` 순차 hook 4 호출 추가
- `src/engine/scheduler.py` — `_settle()` 진입 직전 `emit_trade_amount_filter_scanner_daily_summary` 호출 추가 (사이클 64 직후) + `_reset_daily_state()` 끝부분 `reset_trade_amount_filter_daily_state` 호출 추가
- `src/routes/system.py` — `/trade-amount-filter` GET/PUT + `TradeAmountFilterUpdateRequest` (extra=forbid)

### frontend-dev 인계 (Green 구현 영역)

- `frontend/src/types/trade-amount-filter.ts` (신규) — `TradeAmountFilter` / `TradeAmountFilterUpdate`
- `frontend/src/api/system.ts` 또는 신규 모듈 — `getTradeAmountFilter()` / `putTradeAmountFilter(body)`
- `frontend/src/components/TradeAmountFilterCard.tsx` (신규) — 슬라이더 + 권장 마커 버튼 + 저장 + 안내 배너
- `frontend/src/pages/Settings.tsx` (수정) — `PriceFilterCard` 옆 `TradeAmountFilterCard` 배치

### tester 인계 (Verify 영역)

- V1~V13 (사이클 64 답습) + V-Scanner (신규 hook 호출 카운트) + V-AST (G-1 + H-2 AST 가드 영속) + V-TradeAmount-Q6-1 (09:00 race E2E)
- 사이클 64 hotfix 영속: H-2 (scheduler 직접 호출) + G-3 (폐기 메서드 0) 검증 의무

---

## 7. 안전 가드

- 모든 케이스는 **운영 영향 0** (mock + fixture 격리)
- 회귀 가드 추가 = 사이클 64 24 + 사이클 65 28 = **누적 52 케이스** (가격 + 거래대금 필터 회귀 보장)
- **사이클 64 회귀 검증 의무**: 사이클 65 Green 후 사이클 64 회귀 가드 24 케이스 100% PASS 보존 확인 (별도 `pytest tests/unit/.../test_cycle64_*.py` PASS 의무)
- 디폴트 0 영속 → push 즉시 회귀 0

---

## 8. 후속 카드 인계 (사이클 65 종결 후 발의)

- **카드 #16 (MEDIUM)** — Q6-4 후보 풀 폭축 역설 risk 2주 회고 (사이클 67+)
- 자문 §Q5 = 2주 후 운영 데이터 통계 유의성 회고 의무
