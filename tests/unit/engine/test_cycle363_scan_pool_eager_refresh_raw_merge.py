"""cycle363 F-1 — `_scan_pool_eager_refresh_loop` 기존 raw 머지 보존 회귀 가드.

독립 검증 finding #1/#5(major) — 풀 eager refresh(5분 주기)가 09-28 +600초 재준비와
같은 시각에 도는데, `upsert_one` 전 기존 raw 머지가 없어 장전(개장 전) 갱신이 돌면
거래대금 등 0값 키(cycle145 `_ZERO_VALUE_SKIP_KEYS`)가 raw 통째 교체로 지워진다.
사용자 승인(8영역) — `_stock_master_basics_refresh_once`(cycle176)와 같은 규칙을
`_scan_pool_eager_refresh_loop` 에도 적용한다.

패턴은 `test_cycle176_basics_refresh_raw_merge.py` 를 그대로 답습한다 — 다만 이
루프는 `list_all` 페이징으로 기존 raw 를 미리 로드하지 않고, stale 판정을 통과한
종목마다 `stock_master.get(ticker)` 로 개별 조회한다(그 자체가 stale 일 때만 부르는
KIS 재조회와 같은 자리라 추가 호출 비용이 이미 stale 판정에 편승한다).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.stock import StockBasics

pytestmark = pytest.mark.unit


def _basics(ticker: str, raw: dict) -> StockBasics:
    return StockBasics(
        ticker=ticker, name="", excg_dvsn_cd="",
        nxt_tradable=False, krx_halted=False, admin_item=False, raw=raw,
    )


def _prev(ticker: str, raw: dict) -> StockBasics:
    """`stock_master.get()` 이 돌려주는 기존 행 대역."""
    return _basics(ticker, raw)


@pytest.mark.asyncio
async def test_g363_f1_merge1_preserves_existing_pbmn_when_new_lacks():
    """새 raw 에 거래대금 부재(개장 전 0 skip) + 기존 raw 에 있음 → 보존."""
    from src.engine import scanner

    new_basics = _basics("005930", {"hts_avls": "1234", "bfdy_clpr": "70000"})
    upsert_mock = AsyncMock(return_value=None)

    with patch(
        "src.db.stock_master.is_stale", AsyncMock(return_value=True),
    ), patch(
        "src.db.stock_master.get",
        AsyncMock(return_value=_prev("005930", {"acml_tr_pbmn": "1000000", "acml_vol": "500"})),
    ), patch(
        "src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics),
    ), patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._scan_pool_eager_refresh_loop(["005930"])

    assert upsert_mock.await_count == 1
    saved = upsert_mock.await_args.args[0]
    assert saved.raw.get("acml_tr_pbmn") == "1000000", "기존 거래대금 보존 실패(F-1 재발)"
    assert saved.raw.get("acml_vol") == "500"
    assert saved.raw.get("hts_avls") == "1234", "새 키 반영 의무"


@pytest.mark.asyncio
async def test_g363_f1_merge2_new_value_overrides_existing():
    """새 raw 값이 있으면 신값이 우선한다(보존이 아니라 덮어쓰기)."""
    from src.engine import scanner

    new_basics = _basics("005930", {"acml_tr_pbmn": "2000000"})
    upsert_mock = AsyncMock(return_value=None)

    with patch(
        "src.db.stock_master.is_stale", AsyncMock(return_value=True),
    ), patch(
        "src.db.stock_master.get",
        AsyncMock(return_value=_prev("005930", {"acml_tr_pbmn": "1000000"})),
    ), patch(
        "src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics),
    ), patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._scan_pool_eager_refresh_loop(["005930"])

    saved = upsert_mock.await_args.args[0]
    assert saved.raw.get("acml_tr_pbmn") == "2000000"


@pytest.mark.asyncio
async def test_g363_f1_merge3_no_existing_row_no_crash():
    """`stock_master.get()` 이 None(신규 ticker) → basics.raw 그대로, 크래시 0."""
    from src.engine import scanner

    new_basics = _basics("005930", {"hts_avls": "1234"})
    upsert_mock = AsyncMock(return_value=None)

    with patch(
        "src.db.stock_master.is_stale", AsyncMock(return_value=True),
    ), patch(
        "src.db.stock_master.get", AsyncMock(return_value=None),
    ), patch(
        "src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics),
    ), patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._scan_pool_eager_refresh_loop(["005930"])

    saved = upsert_mock.await_args.args[0]
    assert saved.raw.get("hts_avls") == "1234"


@pytest.mark.asyncio
async def test_g363_f1_get_failure_is_graceful_no_merge():
    """`stock_master.get()` 예외 → 머지 없이(현행 raw 그대로) 계속 진행(never-raise)."""
    from src.engine import scanner

    new_basics = _basics("005930", {"hts_avls": "1234"})
    upsert_mock = AsyncMock(return_value=None)

    with patch(
        "src.db.stock_master.is_stale", AsyncMock(return_value=True),
    ), patch(
        "src.db.stock_master.get", AsyncMock(side_effect=RuntimeError("pg down")),
    ), patch(
        "src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics),
    ), patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._scan_pool_eager_refresh_loop(["005930"])

    assert upsert_mock.await_count == 1, "조회 실패가 refresh 자체를 막으면 안 된다"
    saved = upsert_mock.await_args.args[0]
    assert saved.raw.get("hts_avls") == "1234"


@pytest.mark.asyncio
async def test_g363_f1_preserve_all_zero_skip_keys():
    """cycle145 `_ZERO_VALUE_SKIP_KEYS` 전부 — 새 raw 부재 시 기존값 전 키 보존."""
    from src.engine import scanner
    from src.api.condition import _ZERO_VALUE_SKIP_KEYS

    existing = {k: "100" for k in _ZERO_VALUE_SKIP_KEYS}
    existing["hts_avls"] = "999"
    new_basics = _basics("005930", {"hts_avls": "1234"})
    upsert_mock = AsyncMock(return_value=None)

    with patch(
        "src.db.stock_master.is_stale", AsyncMock(return_value=True),
    ), patch(
        "src.db.stock_master.get", AsyncMock(return_value=_prev("005930", dict(existing))),
    ), patch(
        "src.api.condition.inquire_stock_basics", AsyncMock(return_value=new_basics),
    ), patch("src.db.stock_master.upsert_one", upsert_mock):
        await scanner._scan_pool_eager_refresh_loop(["005930"])

    saved = upsert_mock.await_args.args[0]
    for k in _ZERO_VALUE_SKIP_KEYS:
        assert saved.raw.get(k) == "100", f"{k} 보존 실패(F-1 재발)"


@pytest.mark.asyncio
async def test_g363_f1_fresh_ticker_skips_without_touching_get():
    """fresh(24h 이내) 종목은 `stock_master.get()` 조차 부르지 않는다(불필요 DB 왕복 0)."""
    from src.engine import scanner

    get_mock = AsyncMock(return_value=None)
    with patch(
        "src.db.stock_master.is_stale", AsyncMock(return_value=False),
    ), patch("src.db.stock_master.get", get_mock), patch(
        "src.api.condition.inquire_stock_basics", AsyncMock(),
    ), patch("src.db.stock_master.upsert_one", AsyncMock()), patch(
        "asyncio.sleep", AsyncMock(),
    ):
        await scanner._scan_pool_eager_refresh_loop(["005930"])

    assert get_mock.await_count == 0


def test_g363_f1_ast_merge_present_in_eager_refresh():
    """G363-F1-AST — 루프 함수에 기존 raw 머지 로직이 정적으로 존재(silent 회귀 차단)."""
    import ast
    import inspect
    from src.engine import scanner

    src = inspect.getsource(scanner._scan_pool_eager_refresh_loop)
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "_prev_raw" in names, "기존 raw 보관 이름 부재"
    has_dict_merge = any(
        isinstance(n, ast.Dict) and any(k is None for k in n.keys)
        for n in ast.walk(tree)
    )
    assert has_dict_merge, "raw 머지 ({**기존, **신규}) 패턴 부재"
