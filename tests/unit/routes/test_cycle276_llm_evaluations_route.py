"""cycle276 Red — `GET /api/llm-evaluations` (배치) · `/{order_no}` (단건) 라우트 계약.

명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §1-C (C37~C40) · §5.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 파일이 지키는 세 가지

1. **계좌번호는 응답에서 마스킹된다.** 저장은 원문, 응답은 앞 4자리 + `****`.
   리포터 키가 GET/HEAD 를 **경로 무관** 통과시키므로(cycle249) 이 표면에 원문이 실리면
   외부 루틴이 계좌번호를 읽는다. `account_no` 원문 키는 응답에 **존재하지 않는다**.
2. **오류를 삼키지 않는다.** DB 예외 → 500(+`[llm_eval_route_error]`), 결과 없음 → 404.
   `except Exception: rows = []` 형태의 fail-silent 는 cycle266 이 3개월짜리 은폐로
   실증한 패턴이다 — 진짜 DB 장애가 "기록 없음" 으로 위장된다.
3. **`Decimal` 은 라우트가 `float` 으로 사영한다.** asyncpg 가 NUMERIC 을 `Decimal` 로 주고
   pydantic v2 는 JSON 모드에서 그것을 **문자열**로 직렬화한다 — 프론트의 `toFixed` 가
   그대로 죽는다(cycle266 흰 화면). 그래서 이 파일은 파이썬 객체가 아니라 **직렬화된
   JSON 본문을 파싱한 결과**의 타입을 잰다.

## Green 이 정하는 seam

라우트는 db 모듈을 **모듈 단위로** 잡고 쓴다(`from src.db import llm_buy_evaluations as ...`
+ `<alias>.get_by_order(...)`, cycle266 `stock_master.py` 관례). 아래 `_patch_db` 는 route
모듈 속성과 db 모듈 속성 **양쪽**을 갈아끼워 import 스타일에 의존하지 않는다.

## 인증

`ApiAuthMiddleware` 가 최외곽에서 전 경로를 지킨다 — 라우트는 인증 코드를 **한 줄도** 쓰지
않고 `EXEMPT_PATHS` 도 늘리지 않는다(C37). 게다가 아래 헬퍼는 `router` 만 실은 독립
`FastAPI()` 앱을 만들므로 미들웨어 자체가 붙지 않는다.
"""

from __future__ import annotations

import ast
import importlib
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_SRC = _ROOT / "src" / "routes" / "llm_evaluations.py"
_MAIN_SRC = _ROOT / "src" / "main.py"

_ROUTE_MOD = "src.routes.llm_evaluations"
_DB_MOD = "src.db.llm_buy_evaluations"

_ORDER_NO = "0000123456"
_ORDER_NO2 = "0000123457"
_ACCOUNT = "12345678"
_TRADE_DATE = date(2026, 9, 11)
_ORDER_KST = datetime(2026, 9, 11, 9, 1, 31, tzinfo=KST)

_MARKER_ERROR = "[llm_eval_route_error]"


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _route():
    """라우트 모듈 — 부재면 `ModuleNotFoundError`(= 정직한 Red, skip 금지)."""
    return importlib.import_module(_ROUTE_MOD)


def _client() -> TestClient:
    """라우터만 실은 독립 앱 — 미들웨어/lifespan 무관, 라우트 본체만 태운다."""
    app = FastAPI()
    app.include_router(_route().router)
    return TestClient(app, raise_server_exceptions=False)


def _patch_db(monkeypatch, **fns) -> None:
    """db 함수를 fake 로 갈아끼운다(route 모듈 속성 + db 모듈 속성 양쪽).

    Green 이 `from src.db import llm_buy_evaluations as X` 로 잡든
    `from src.db.llm_buy_evaluations import get_by_order` 로 잡든 둘 다 잡힌다.
    """
    route = _route()
    db = importlib.import_module(_DB_MOD)
    for name, fn in fns.items():
        monkeypatch.setattr(db, name, fn, raising=False)
        if hasattr(route, name):
            monkeypatch.setattr(route, name, fn, raising=False)
        for attr in vars(route).values():
            if getattr(attr, "__name__", None) == _DB_MOD:
                monkeypatch.setattr(attr, name, fn, raising=False)


def _row(**over) -> dict:
    """db 가 돌려주는 한 행 — asyncpg 실제 타입(`Decimal`/`date`/`datetime`)으로 만든다.

    ⚠️ 여기서 전부 `float`/`str` 로 만들어 버리면 cycle266 과 똑같이 *의도한 계약*만
    검증하고 *실제 응답*은 한 번도 검증하지 않게 된다.
    """
    row = {
        "trade_date": _TRADE_DATE,
        "account_no": _ACCOUNT,
        "account_product": "01",
        "ticker": "005930",
        "order_no": _ORDER_NO,
        "eval_kind": "order",
        "strategy_id": "volatility_breakout",
        "mode": "shadow",
        "result": "ok",
        "reason": None,
        "score": 62,
        "min_score": 70,
        "would_block": True,
        "rationale": "돌파 초과가 얇고 거래대금이 받쳐주지 않는다",
        "key_risks": ["되돌림"],
        "invalidations": ["목표가 이탈"],
        "model": "gpt-5.6-luna",
        "tokens_in": 3120,
        "tokens_out": 210,
        "cost_usd": Decimal("0.004380"),
        "latency_ms": 3120,
        "verdict_lag_ms": 3480,
        "eval_to_order_lag_ms": 3480,
        "order_kst": _ORDER_KST,
        "order_kst_iso": "2026-09-11T09:01:31.032000+09:00",
        "evaluated_at": _ORDER_KST,
        "evaluated_at_iso": "2026-09-11T09:01:34.512000+09:00",
        "order_price_won": 71_800,
        "ordered_qty": 3,
        "order_notional_won": 215_400,
        "order_division": "MARKET",
        "order_path": "market",
        "exchange": "KRX",
        "board": "main",
        "current_price_won": 71_800,
        "signal_matched": True,
        "signal_price_won": 71_800,
        "signal_time_local": "09:01:31",
        "strategy_board": "main",
        "target_won": 71_650,
        "k": Decimal("0.5000"),
        "breakout_excess_bp": Decimal("20.9000"),
        "post_order_drift_bp": Decimal("-13.9000"),
        "drift_price_won": 71_700,
        "tick_age_s": Decimal("1.20"),
        "budget_total_won": 247_949,
        "budget_remaining_after_won": 32_549,
        "open_positions_n": 1,
        "prompt_version": "a1b2c3d4e5f6",
        "feature_version": "0f1e2d3c4b5a",
        "bars_count": 59,
        "input_payload": {"payload": {"ticker": "005930"}, "tech": {}, "bars30": []},
        "raw_response": {"content": "{\"score\":62}"},
        "created_at": _ORDER_KST,
        "created_at_iso": "2026-09-11T09:01:34.512000+09:00",
    }
    row.update(over)
    return row


def _ok(value):
    async def _fn(*a, **kw):
        return value
    return _fn


def _boom(exc: BaseException):
    async def _fn(*a, **kw):
        raise exc
    return _fn


def _is_json_number(v: Any) -> bool:
    """JSON 숫자인가 — `bool` 은 `int` 의 서브클래스라 명시 배제."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ===========================================================================
# C39 — 계좌 마스킹 헬퍼
# ===========================================================================
@pytest.mark.parametrize(("raw", "expected"), [
    ("12345678", "1234****"),
    ("50123456789", "5012****"),
    ("", "****"),
    ("123", "****"),
    (None, "****"),
])
def test_r1_mask_account_no(raw, expected) -> None:
    """C39 — 앞 4자리 + `****`. 빈 값·8자 미만은 **전체 마스킹**(길이 누출 방지).

    ⚠️ 기존 `mask_secret`(뒤 4자리)을 재사용하지 않는다 — 두 관례를 섞으면 어느 쪽이
    적용됐는지 코드를 읽어야만 알 수 있다.
    """
    fn = getattr(_route(), "mask_account_no", None)
    assert fn is not None, "`mask_account_no` 헬퍼가 없다(Red)"
    assert fn(raw) == expected


# ===========================================================================
# §5.2 — 단건 상세
# ===========================================================================
def test_r2_single_returns_200_with_masked_account(monkeypatch) -> None:
    """§5.2/C39 (뮤테이션 M14) — 200 + `account_no_masked`."""
    _patch_db(monkeypatch, get_by_order=_ok(_row()))
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["account_no_masked"] == "1234****"
    assert data["order_no"] == _ORDER_NO
    assert data["score"] == 62 and data["min_score"] == 70
    assert data["would_block"] is True


def test_r3_single_response_has_no_raw_account_key(monkeypatch) -> None:
    """C40 (뮤테이션 M14) — 응답 어디에도 계좌 **원문**이 없다.

    리포터 키(GET/HEAD 경로 무관 통과)가 이 표면을 읽는다는 점이 이 단언의 이유다.
    """
    _patch_db(monkeypatch, get_by_order=_ok(_row()))
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}")

    assert "account_no" not in resp.json()["data"], "원문 계좌 키가 응답에 남아 있다"
    assert _ACCOUNT not in resp.text, "응답 본문 어딘가에 계좌번호 원문이 실렸다"


def test_r4_single_404_when_missing(monkeypatch) -> None:
    """§5.2 — 기록이 없으면 404 이고 `detail` 에 주문번호가 실린다."""
    _patch_db(monkeypatch, get_by_order=_ok(None))
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}")

    assert resp.status_code == 404
    assert _ORDER_NO in resp.json().get("detail", "")


def test_r5_single_500_on_db_exception(monkeypatch, caplog) -> None:
    """C38 (뮤테이션 M15) — DB 예외는 **500**이고 `[llm_eval_route_error]` 를 남긴다."""
    caplog.set_level(logging.ERROR)
    _patch_db(monkeypatch, get_by_order=_boom(RuntimeError("connection reset")))
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}")

    assert resp.status_code == 500, f"DB 예외인데 {resp.status_code} 를 돌려줬다"
    errors = [r.getMessage() for r in caplog.records
              if r.levelno >= logging.ERROR and _MARKER_ERROR in r.getMessage()]
    assert errors, f"`{_MARKER_ERROR}` 로그가 없다 — 장애가 조용히 지나간다"


def test_r6_single_does_not_swallow_exception_into_404(monkeypatch) -> None:
    """C38 (cycle266 정본) — DB 장애가 "기록 없음"(404)으로 위장되지 않는다.

    `except Exception: return None` 은 진짜 장애를 영구 은폐한다 — 운영에서
    "그 탭은 원래 비어 있어요" 로 3개월 지나간 전례가 있다.
    """
    _patch_db(monkeypatch, get_by_order=_boom(RuntimeError("connection reset")))
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}")

    assert resp.status_code != 404, "DB 예외가 404 로 위장됐다"


def test_r7_numeric_decimal_projected_to_json_number(monkeypatch) -> None:
    """C38/§4 (cycle266 흰 화면) — `NUMERIC` 은 JSON **숫자**로 나간다.

    pydantic v2 는 `Decimal` 을 JSON 모드에서 문자열로 직렬화한다. 프론트가
    `toFixed` 를 부르는 순간 `TypeError` 로 트리 전체가 언마운트된다.
    """
    _patch_db(monkeypatch, get_by_order=_ok(_row()))
    data = _client().get(f"/api/llm-evaluations/{_ORDER_NO}").json()["data"]

    for key in ("cost_usd", "k", "breakout_excess_bp", "post_order_drift_bp", "tick_age_s"):
        assert _is_json_number(data[key]), (
            f"`{key}` 가 JSON 숫자가 아니다: {data[key]!r} ({type(data[key]).__name__})"
        )


def test_r8_single_passes_trade_date_through(monkeypatch) -> None:
    """§5.2 — `trade_date` 쿼리가 db 계층까지 전달된다(같은 ODNO 의 날짜 충돌 해소)."""
    seen: list[dict] = []

    async def _spy(order_no, *, trade_date=None):
        seen.append({"order_no": order_no, "trade_date": trade_date})
        return _row()

    _patch_db(monkeypatch, get_by_order=_spy)
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}?trade_date=2026-09-11")

    assert resp.status_code == 200, resp.text
    assert seen and seen[0]["order_no"] == _ORDER_NO
    assert str(seen[0]["trade_date"]) == "2026-09-11"


# ===========================================================================
# §5.1 — 배치 요약
# ===========================================================================
_KEY1 = "2026-09-11|0000123456"
_KEY2 = "2026-09-11|0000123457"


def test_r9_batch_returns_map_keyed_by_date_and_order_no(monkeypatch) -> None:
    """§5.1 — `data` 키는 `"<trade_date>|<order_no>"` 복합 키다(프론트가 O(1) 로 조회).

    주문번호 단독 키는 같은 번호의 다른 날짜 평가를 지운다(cycle276 후속 B-2).
    """
    _patch_db(monkeypatch, list_by_order_nos=_ok([_row()]))
    resp = _client().get(f"/api/llm-evaluations?order_nos={_ORDER_NO},{_ORDER_NO2}")

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert set(data) == {_KEY1}, f"키 집합이 다르다: {sorted(data)}"
    assert data[_KEY1]["score"] == 62
    assert data[_KEY1]["would_block"] is True
    assert data[_KEY1]["order_no"] == _ORDER_NO
    assert data[_KEY1]["trade_date"] == "2026-09-11"


def test_r9b_summary_key_helper_format() -> None:
    """B-2 — `summary_key()` 는 `날짜|주문번호` 를 만든다(프론트 `llmEvalKey` 와 같은 규약)."""
    fn = getattr(_route(), "summary_key", None)
    assert fn is not None, "`summary_key` 헬퍼가 없다"
    assert fn("2026-09-11", "0000123456") == "2026-09-11|0000123456"


def test_r9c_batch_returns_every_date_for_same_order_no(monkeypatch) -> None:
    """B-2 (핵심) — 같은 주문번호가 두 날짜에 있으면 **두 키 전부** 나간다.

    종전에는 db 계층이 "주문번호당 최신 1행" 으로 접어 오래된 날짜의 평가가 응답에서
    사라졌다. 그 날짜의 거래 행은 버튼이 비활성(= "기록 없음")인데 상세 조회는 날짜와
    함께 물어 멀쩡히 답을 받는다 — 배치와 상세의 날짜 축 비대칭이 화면의 거짓말이다.
    """
    rows = [
        _row(trade_date=date(2026, 9, 11), score=62),
        _row(trade_date=date(2026, 9, 8), score=88),
    ]
    _patch_db(monkeypatch, list_by_order_nos=_ok(rows))
    data = _client().get(f"/api/llm-evaluations?order_nos={_ORDER_NO}").json()["data"]

    assert set(data) == {"2026-09-11|0000123456", "2026-09-08|0000123456"}, (
        f"날짜별 키가 둘 다 없다: {sorted(data)}"
    )
    assert data["2026-09-11|0000123456"]["score"] == 62
    assert data["2026-09-08|0000123456"]["score"] == 88


def test_r10_batch_missing_keys_are_absent_not_null(monkeypatch) -> None:
    """§5.1 — 기록이 없는 주문번호는 **키 자체가 없다**(`null` 값 아님).

    `null` 로 채우면 프론트가 "기록 있음(값 null)" 과 "기록 없음" 을 구별하지 못한다.
    """
    _patch_db(monkeypatch, list_by_order_nos=_ok([_row()]))
    data = _client().get(
        f"/api/llm-evaluations?order_nos={_ORDER_NO},{_ORDER_NO2}"
    ).json()["data"]

    assert _KEY2 not in data, "기록 없는 주문번호가 키로 들어 있다"
    assert _ORDER_NO2 not in data, "주문번호 단독 키가 섞여 있다"


def test_r11_batch_summary_does_not_leak_account_or_payload(monkeypatch) -> None:
    """§5.1/C40 — 요약 응답에 계좌 원문·입력 payload 가 실리지 않는다.

    배치는 페이지당 최대 200건이라 payload 를 실으면 응답이 수 MB 로 부푼다.
    """
    _patch_db(monkeypatch, list_by_order_nos=_ok([_row()]))
    resp = _client().get(f"/api/llm-evaluations?order_nos={_ORDER_NO}")

    assert _ACCOUNT not in resp.text
    assert "input_payload" not in resp.json()["data"][_KEY1]


def test_r12_batch_422_on_zero_order_nos(monkeypatch) -> None:
    """§5.1 — 빈 목록은 **422**(빈 조회가 전체 스캔으로 번지지 않게)."""
    _patch_db(monkeypatch, list_by_order_nos=_ok([]))
    assert _client().get("/api/llm-evaluations?order_nos=").status_code == 422
    assert _client().get("/api/llm-evaluations?order_nos=%20,%20").status_code == 422


def test_r13_batch_422_on_over_200(monkeypatch) -> None:
    """§5.1 — 201건은 422(손익 그리드 최대 페이지 200과 정렬)."""
    _patch_db(monkeypatch, list_by_order_nos=_ok([]))
    many = ",".join(f"{i:010d}" for i in range(201))
    assert _client().get(f"/api/llm-evaluations?order_nos={many}").status_code == 422


def test_r14_batch_accepts_exactly_200(monkeypatch) -> None:
    """§5.1 — 경계값 200 은 통과한다(off-by-one 으로 마지막 페이지가 죽지 않게)."""
    _patch_db(monkeypatch, list_by_order_nos=_ok([]))
    many = ",".join(f"{i:010d}" for i in range(200))
    assert _client().get(f"/api/llm-evaluations?order_nos={many}").status_code == 200


def test_r15_batch_trims_and_dedupes(monkeypatch) -> None:
    """§5.1 — 공백 제거 + 중복 제거 후 db 로 넘어간다."""
    seen: list[list[str]] = []

    async def _spy(order_nos, *, trade_date=None):
        seen.append(list(order_nos))
        return []

    _patch_db(monkeypatch, list_by_order_nos=_spy)
    resp = _client().get(
        f"/api/llm-evaluations?order_nos=%20{_ORDER_NO}%20,{_ORDER_NO},{_ORDER_NO2},"
    )

    assert resp.status_code == 200, resp.text
    assert seen, "db 조회가 일어나지 않았다"
    assert sorted(seen[0]) == sorted({_ORDER_NO, _ORDER_NO2}), (
        f"정규화 결과가 다르다: {seen[0]}"
    )


def test_r16_batch_500_on_db_exception(monkeypatch, caplog) -> None:
    """C38 — 배치도 DB 예외를 삼키지 않는다(빈 맵 200 으로 위장 금지)."""
    caplog.set_level(logging.ERROR)
    _patch_db(monkeypatch, list_by_order_nos=_boom(RuntimeError("pool exhausted")))
    resp = _client().get(f"/api/llm-evaluations?order_nos={_ORDER_NO}")

    assert resp.status_code == 500, f"DB 예외인데 {resp.status_code} 를 돌려줬다"
    assert [r for r in caplog.records
            if r.levelno >= logging.ERROR and _MARKER_ERROR in r.getMessage()]


# ===========================================================================
# C37 / 배선
# ===========================================================================
def test_r17_route_has_no_auth_code_and_no_exempt_change() -> None:
    """C37 — 라우트는 인증 코드를 한 줄도 쓰지 않고 `EXEMPT_PATHS` 도 늘리지 않는다.

    인증은 `ApiAuthMiddleware` 최외곽 단일 지점이 책임진다 — 라우트마다 예외를 두면
    "어느 경로가 열려 있나" 를 아무도 모르게 된다.
    """
    assert _ROUTE_SRC.exists(), "`src/routes/llm_evaluations.py` 가 없다(Red)"
    text = _ROUTE_SRC.read_text(encoding="utf-8")
    for banned in ("X-API-Key", "EXEMPT_PATHS", "api_auth", "authorize("):
        assert banned not in text, f"라우트에 인증 코드(`{banned}`)가 있다"

    from src.middleware.api_auth import EXEMPT_PATHS
    assert EXEMPT_PATHS == frozenset({"/health"}), (
        f"`EXEMPT_PATHS` 가 늘었다: {sorted(EXEMPT_PATHS)}"
    )


def test_r18_router_prefix_and_tag() -> None:
    """§5 — `prefix="/api/llm-evaluations"`(프론트 API 클라이언트 경로와 정합)."""
    router = _route().router
    assert router.prefix == "/api/llm-evaluations"
    paths = {r.path for r in router.routes}
    assert "/api/llm-evaluations" in paths
    assert "/api/llm-evaluations/{order_no}" in paths


def test_r19_router_registered_in_main() -> None:
    """§5 — `src/main.py` 에 import 1줄 + `include_router` 1줄.

    라우터를 만들고 등록을 잊으면 프론트가 404 를 받고, 그 404 는 "평가 기록 없음"
    회색 안내와 **구별되지 않는다**(모달의 404 분기가 그 문구를 쓴다).
    """
    text = _MAIN_SRC.read_text(encoding="utf-8")
    assert "llm_evaluations" in text, "`main.py` 가 라우터를 import 하지 않는다"

    tree = ast.parse(text)
    includes = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "include_router"
        and (ast.get_source_segment(text, n) or "").find("llm_evaluations") >= 0
    ]
    assert len(includes) == 1, f"`include_router(llm_evaluations.router)` {len(includes)}건 (기대 1)"


def test_r20_response_uses_api_response_envelope(monkeypatch) -> None:
    """리포 관례 — 두 엔드포인트 모두 `{success, data, message}` 봉투를 쓴다."""
    _patch_db(monkeypatch, get_by_order=_ok(_row()), list_by_order_nos=_ok([_row()]))

    for url in (f"/api/llm-evaluations/{_ORDER_NO}",
                f"/api/llm-evaluations?order_nos={_ORDER_NO}"):
        body = _client().get(url).json()
        assert set(body) >= {"success", "data", "message"}, f"{url}: 봉투 키 {sorted(body)}"
        assert body["success"] is True


# ===========================================================================
# B-3 (cycle276 후속) — `trade_date` 파싱 실패는 **422**, 200 이 아니다
# ===========================================================================
_BAD_DATES = ["2026-13-45", "어제", "2026/09/11", "20260911", "2026-09-11T09:00:00+09:00"]


@pytest.mark.parametrize("bad", _BAD_DATES)
def test_r21_batch_422_on_unparsable_trade_date(monkeypatch, bad) -> None:
    """B-3 — 형식 위반 `trade_date` 는 422 이고 **db 를 부르지 않는다**.

    종전에는 `_kst.to_date()` 가 경고만 남기고 `None` 을 돌려줘 날짜 축이 사라진 채
    "가장 최근 1행" 이 200 으로 응답됐다 — 오타 하나가 다른 날짜의 평가를 그 행의
    평가처럼 보여주고, 호출자는 자기 요청이 무시된 것을 알 길이 없다.
    """
    called: list[tuple] = []

    async def _spy(order_nos, *, trade_date=None):
        called.append((list(order_nos), trade_date))
        return []

    _patch_db(monkeypatch, list_by_order_nos=_spy)
    resp = _client().get(f"/api/llm-evaluations?order_nos={_ORDER_NO}&trade_date={bad}")

    assert resp.status_code == 422, f"{bad!r} → {resp.status_code} {resp.text}"
    assert called == [], "422 인데 db 조회가 일어났다"


@pytest.mark.parametrize("bad", _BAD_DATES)
def test_r22_detail_422_on_unparsable_trade_date(monkeypatch, bad) -> None:
    """B-3 — 상세도 같다(422 + db 무호출)."""
    called: list[tuple] = []

    async def _spy(order_no, *, trade_date=None):
        called.append((order_no, trade_date))
        return _row()

    _patch_db(monkeypatch, get_by_order=_spy)
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}?trade_date={bad}")

    assert resp.status_code == 422, f"{bad!r} → {resp.status_code} {resp.text}"
    assert called == [], "422 인데 db 조회가 일어났다"


@pytest.mark.parametrize("good", ["2026-09-11", " 2026-09-11 ", ""])
def test_r23_valid_or_empty_trade_date_still_passes(monkeypatch, good) -> None:
    """B-3 — 정상 값·빈 값은 종전대로 통과한다(422 가 정상 경로를 잡아먹지 않는다).

    빈 문자열은 "날짜 축 없음"(`None`) 이다 — 프론트가 `trade_date=undefined` 를 보낼 때
    axios 가 파라미터를 아예 빼지만, 빈 문자열이 들어오는 경로도 422 로 막지 않는다.
    """
    seen: list = []

    async def _spy(order_no, *, trade_date=None):
        seen.append(trade_date)
        return _row()

    _patch_db(monkeypatch, get_by_order=_spy)
    resp = _client().get(f"/api/llm-evaluations/{_ORDER_NO}?trade_date={good}")

    assert resp.status_code == 200, resp.text
    expected = "2026-09-11" if good.strip() else None
    assert seen == [expected], f"db 로 넘어간 값이 {seen!r} (기대 {expected!r})"
