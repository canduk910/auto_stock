"""사이클 93 G-CC3 (HIGH) — POST `/refresh-universe` 라우트 stock_master upsert chain 의무.

Red 명세 (`_workspace/red/cycle93_call_chain_broken.md`):

`src/routes/stock_master.py::refresh_universe_now` (POST 라우트, 사이클 90 도입) 가
`fetch_top_500_universe()` 결과 ticker list 를 scanner module `_universe_eager_refresh_loop`
모듈 함수 (사이클 89 도입, stock_master upsert 담당) 에 정확히 위임해야 한다.

Red 상태 (사이클 93 시점):
- 라우트 L52~L58 가 `tickers = await fetch_top_500_universe()` 후 ticker list *버림*
- scanner module upsert 호출 0회 → FAIL
- 사용자 UI "지금 새로고침" 버튼 클릭해도 stock_master 60 ticker 영속

Green (backend-dev 인계 후):
- 라우트에 `from src.engine.scanner import _universe_eager_refresh_loop as _scanner_upsert_loop`
- `try: await _scanner_upsert_loop(tickers); except Exception: logger.exception(...)` 추가
- 의무 1회 호출 → PASS + 응답 200 + `data.universe=5`

영속 의무:
- 사이클 89 silent 결함 영구 차단 (수동 trigger 영역까지)
- 사이클 90 graceful 영속 (KIS 실패 시 [] 반환 + universe=0)
- 사이클 38 명문화 영속 (`tradable_boards` 영향 0)
- 사이클 32 R4 universe guard 별개 영역 (보유/익일청산 절대 보호 영속)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


_MOCK_TICKERS = ["005930", "402340", "035720", "000660", "035420"]


def test_g_cc3_route_post_refresh_universe_calls_scanner_upsert_chain(monkeypatch):
    """G-CC3: POST `/refresh-universe` 호출 시 scanner module `_universe_eager_refresh_loop`
    가 정확히 ticker list 인자로 1회 호출되어야 한다.

    검증 매트릭스:
    1. mock fetch_top_500_universe → 5 ticker 반환
    2. mock scanner module `_universe_eager_refresh_loop` (AsyncMock)
    3. POST `/api/stock-master/refresh-universe` 호출
    4. 의무:
       - 응답 200 + `success=true` + `data.universe=5` (사이클 90 영속)
       - scanner upsert chain 1회 호출 + 인자 = ticker list

    Red 상태: 라우트 L52 `tickers = await fetch_top_500_universe()` 후 ticker 버림
    → scanner upsert 호출 0회 → FAIL + UI 무용.

    Green: 라우트에 scanner upsert chain 위임 추가 → 1회 호출 → PASS + UI 즉시 효과.
    """
    from src.engine import scanner as _scanner_mod

    fetch_mock = AsyncMock(return_value=list(_MOCK_TICKERS))
    upsert_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(_scanner_mod, "fetch_top_500_universe", fetch_mock, raising=False)
    monkeypatch.setattr(
        _scanner_mod, "_universe_eager_refresh_loop", upsert_mock, raising=False
    )

    from src.main import app
    client = TestClient(app)
    res = client.post("/api/stock-master/refresh-universe")

    # 의무 1: 라우트 응답 200 + universe=5 (사이클 90 영속)
    assert res.status_code == 200, (
        f"POST 200 의무 (사이클 90 영속), 실제 {res.status_code}, body={res.text[:200]}"
    )
    body = res.json()
    assert body["success"] is True
    assert body["data"]["universe"] == 5, (
        f"universe = mock ticker 수 (5) 의무, 실제 {body['data']['universe']}"
    )

    # 의무 2: fetch 1회 호출 (사이클 90 H-4 영속)
    assert fetch_mock.call_count == 1, (
        f"fetch_top_500_universe 1회 호출 의무, 실제 {fetch_mock.call_count}회"
    )

    # 의무 3 (핵심 HIGH): scanner upsert chain 1회 호출
    assert upsert_mock.call_count == 1, (
        f"\n사이클 93 G-CC3 위반 — POST /refresh-universe 라우트에서 "
        f"scanner module `_universe_eager_refresh_loop` 호출 누락:\n\n"
        f"  fetch_top_500_universe 호출:    {fetch_mock.call_count}회\n"
        f"  scanner upsert chain 호출:      {upsert_mock.call_count}회 (의무 1회)\n\n"
        f"  결함 원인: routes/stock_master.py L52~L58 ticker list 버림\n"
        f"             → 사용자 UI '지금 새로고침' 버튼 무용\n"
        f"             → stock_master 60 ticker 영속 (사이클 89 silent 결함)\n\n"
        f"  시정 (Green):\n"
        f"    from src.engine.scanner import (\n"
        f"        fetch_top_500_universe,\n"
        f"        _universe_eager_refresh_loop as _scanner_upsert_loop,\n"
        f"    )\n"
        f"    tickers = await fetch_top_500_universe()\n"
        f"    try:\n"
        f"        await _scanner_upsert_loop(tickers)\n"
        f"    except Exception:\n"
        f"        logger.exception('[refresh_universe_now] stock_master upsert 실패 graceful')"
    )

    # 의무 4: 인자 정확성 (ticker list 그대로 전달)
    args, _kwargs = upsert_mock.call_args
    assert args and list(args[0]) == _MOCK_TICKERS, (
        f"scanner upsert chain 인자 = fetch ticker list 의무, 실제 args={args}"
    )
