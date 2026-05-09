# 백엔드 TDD 패턴 (pytest + respx + freezegun)

## 의존성 주입 fixture (conftest.py 핵심)

| Fixture | 목적 | 적용 |
|---------|------|------|
| `mock_kis` | `respx`로 KIS REST 모킹 + `fixtures/kis_responses/` 자동 로드 | 모든 단위/계약 |
| `fake_ws` | `FakeKisWebSocket` — 메시지 큐 기반 가짜 WS | realtime 테스트 |
| `fake_supabase` | 인메모리 dict 기반 `FakeSupabaseRepo` | db/routes 테스트 |
| `freeze_time_kst` | KST 기준 `freeze_time` 헬퍼 | 시간 의존 코드 |
| `clean_strategy_state` | 전략 state 초기화 | 전략 테스트 |

## 디렉토리별 작성 패턴

### `tests/unit/api/`
- `respx.MockRouter`로 KIS 엔드포인트 라우팅
- 각 응답은 `fixtures/kis_responses/<tr_id>_<scenario>.json` 로드
- 검증: 호출 횟수, 헤더, body, 응답 파싱 결과

```python
async def test_place_order_when_buy_then_kis_receives_correct_tr_id(mock_kis):
    mock_kis.post("/uapi/domestic-stock/v1/trading/order-cash").respond(
        json=load_fixture("VTTC0802U_success.json")
    )
    result = await order.place_order(ticker="005930", quantity=10, price=0, side="BUY")
    assert result.order_no == "0000123456"
    assert mock_kis.calls[0].request.headers["tr_id"] == "VTTC0802U"
```

### `tests/unit/engine/strategies/`
- 시뮬레이션 가격 series 입력 → check_buy/exit 호출 → 신호 출력 검증
- 보드별 동작은 `MarketBoard.MAIN`/`PRE_NXT` 등으로 명시
- DB/외부 호출 없이 순수 함수처럼 다룬다

```python
def test_volatility_breakout_when_target_breached_then_buy_signal(clean_strategy_state):
    strategy = VolatilityBreakoutStrategy()
    strategy.set_target_price("005930", board=MarketBoard.MAIN, value=82000)
    signal = strategy.check_buy_signal("005930", current=82500, board=MarketBoard.MAIN, prev_tick=81500)
    assert signal == Signal.BUY
```

### `tests/integration/`
- OrderEngine + RiskManager + Strategy + FakeSupabase 결합
- `freeze_time_kst("2026-05-08 15:19:55")` 형태로 시각 고정
- 체결통보 race 테스트: REST 응답을 일부러 지연시키고 WS 메시지를 먼저 흘림

```python
async def test_chegyeol_race_when_ws_first_then_completed_row(
    order_engine, fake_supabase, fake_ws, mock_kis
):
    # WS 체결통보가 REST 응답보다 먼저 도착
    await fake_ws.push("H0STCNI9", build_fill_msg(order_no="A1", ticker="005930", qty=10))
    await mock_kis.delay_next_response(seconds=0.1)
    await order_engine.execute_buy(strategy_id="momentum", ticker="005930", qty=10)
    rows = fake_supabase.table("trade_history").select_all()
    assert len([r for r in rows if r["ticker"] == "005930"]) == 1
    assert rows[0]["status"] == "COMPLETED"
```

### `tests/contract/`
- FastAPI `TestClient` + 응답 pydantic 모델 검증
- 모든 19개 엔드포인트가 `success/data/message` 래퍼를 따르는지

```python
def test_get_balance_response_schema(client, fake_supabase):
    r = client.get("/api/balance")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"success", "data", "message"}
    assert isinstance(body["data"]["positions"], list)
```

## 시간 freeze 표준

```python
from freezegun import freeze_time

@freeze_time("2026-05-08 15:19:55", tz_offset=9)  # KST
async def test_force_clear_at_1520(scheduler, fake_supabase):
    await scheduler.tick()  # 5초 전 — 청산 안 됨
    assert not fake_supabase.was_called("delete_position")

    with freeze_time("2026-05-08 15:20:01", tz_offset=9):
        await scheduler.tick()
        assert fake_supabase.was_called("delete_position")
```

## DB 의존성 주입 가이드 (Phase A 1회 리팩터)

`src/db/*` 가 모듈 전역 client를 사용하면 fake 주입이 까다롭다. 다음 패턴으로 점진 마이그레이션:

```python
# Before
from src.db.supabase_client import client
async def insert_trade(row): ...

# After
class TradeHistoryRepo:
    def __init__(self, client=None):
        self._client = client or default_client()
    async def insert(self, row): ...

# 호출부 호환: default_client()는 기존 전역 client 반환
```

테스트에서는 `TradeHistoryRepo(client=FakeSupabaseClient())`를 주입.

## 흔한 함정

| 함정 | 해결 |
|------|------|
| `asyncio.sleep(...)`이 테스트를 느리게 함 | `pytest-asyncio` + `monkeypatch.setattr(asyncio, 'sleep', ...)`로 즉시 진행 또는 시간 freeze 결합 |
| 전역 dict 상태 (scanner의 ticker_prices 등) 누출 | 각 테스트 시작 전 reset fixture |
| `respx`가 등록 안 한 라우트로 가서 실제 호출 시도 | `respx.mock(assert_all_called=True)` + 명시적 라우트 |
| 토큰 갱신 재귀 | 토큰 fixture를 명시적으로 셋업, 만료 분기는 별도 테스트 |
