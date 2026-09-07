"""cycle266 — GET /api/stock-master/{ticker}/daily 직렬화 계약 정본 가드 (C-1).

명세 = `_workspace/specs/cycle266_daily_tab_fix.md` §3-A (A-1 / A-2 / A-3).

## 이 파일이 존재하는 이유

`stock_master_daily.change_rate` / `prtt_rate` 는 `NUMERIC(8,4)` 이고 asyncpg 는
그것을 `decimal.Decimal` 로 준다. 라우트는 그 dict 를 그대로 `ApiResponse.data`
(`Any`) 에 실어 반환하고, pydantic v2 는 JSON 모드에서 `Decimal` 을 **문자열**로
직렬화한다 ⇒ 브라우저는 `change_rate: "0.0000"` 을 받고 `.toFixed(2)` 에서
`TypeError` 로 죽는다. 2026-06-13(dc66026, 사이클 124) 이후 이 탭은 **한 번도
동작한 적이 없다**.

그런데 세 개의 목(`frontend/src/test/handlers.ts` · `e2e/fixtures/api-mocks.ts` ·
`frontend/src/pages/__tests__/StockMaster.test.tsx`)이 전부 `change_rate` 를
**진짜 number** 로 만들어 두어 *의도한 계약*만 검증했고 *실제 응답*은 한 번도
검증하지 않았다 — 그래서 3개월 넘게 전부 초록이었다.

⇒ **이 파일이 유일한 진짜 계약 가드다.** 라우트를 실제로 태우고, 파이썬 객체가
아니라 **직렬화된 JSON 본문을 파싱한 결과**의 타입을 잰다.

## 🔴 절대 제약

`src/db/stock_master_daily.py::get_recent_daily` 는 **고치지 않는다**
(6 전략 `prepare()` + 터틀 사이징 ATR + 수정주가 락 게이트 공유 = 매매 행위 영역).
따라서 이 파일의 모든 가짜 DB 는 `monkeypatch` 로 주입하며, 시정 지점은
`src/routes/stock_master.py::get_stock_master_daily` **단독**이다.

## backend-dev 와 합의한 인터페이스 (Red 가 강제하는 계약)

* A-1  `Decimal` 값 → `float()`. **필드명 열거 금지**(값 타입으로 판정).
       원본 row 는 read-only — **새 dict** 를 만든다.
* A-1b `raw` 키는 **값 그대로 전달**(재귀 변환 금지, 사이클 81 G-AST1 영속).
* A-1c `Decimal` 이 아닌 타입(`date`/`int`/`str`/`None`)은 손대지 않는다.
* A-1d `float()` 실패는 **fail-open** = 원값 유지 (응답이 통째로 사라지는 것보다 낫다).
* A-2  `get_recent_daily` 예외 → `logger.exception` + **HTTP 500**. 삼키지 않는다.
* A-3  빈 rows → **404 유지**, `detail` 에 ticker · `"미적재"` · `days=` 포함.

인증 미들웨어는 `tests/conftest.py::_neutralize_api_auth` 가 이미 중립화한다
(`real_api_auth` 마커를 쓰지 않는다). 게다가 아래 헬퍼는 `router` 만 실은
독립 `FastAPI()` 앱을 만들므로 미들웨어 자체가 붙지 않는다.
"""

from __future__ import annotations

import datetime
import decimal
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _client() -> TestClient:
    """라우터만 실은 독립 앱 — 미들웨어/lifespan 무관, 라우트 본체만 태운다."""
    from src.routes.stock_master import router

    app = FastAPI()
    app.include_router(router, prefix="/api/stock-master")
    return TestClient(app, raise_server_exceptions=False)


def _sample_row(**overrides: Any) -> dict:
    """운영 DB 가 실제로 주는 모양 — asyncpg NUMERIC → Decimal, DATE → date."""
    row = {
        "ticker": "005930",
        "bas_dd": datetime.date(2026, 9, 5),
        "open_price": 74000,
        "high_price": 75500,
        "low_price": 73500,
        "close_price": 75000,
        "volume": 1_000_000,
        "trade_value": 75_000_000_000,
        "change_rate": decimal.Decimal("0.0000"),
        "flng_cls_code": "",
        "prtt_rate": decimal.Decimal("1.2300"),
        "raw": {"stck_clpr": "75000", "prdy_ctrt": "0.00"},
    }
    row.update(overrides)
    return row


def _get(rows: Any, *, ticker: str = "005930", days: int = 1, raises: Any = None):
    """`get_recent_daily` 를 가짜로 갈아끼우고 라우트를 실제로 태운다."""
    kwargs: dict[str, Any] = {"new_callable": AsyncMock}
    if raises is not None:
        kwargs["side_effect"] = raises
    else:
        kwargs["return_value"] = rows
    with patch(
        "src.routes.stock_master.stock_master_daily.get_recent_daily", **kwargs
    ):
        return _client().get(f"/api/stock-master/{ticker}/daily?days={days}")


def _is_json_number(value: Any) -> bool:
    """JSON 숫자인가 — `bool` 은 `int` 의 서브클래스라 명시 배제."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ─────────────────────────────────────────────────────────────────────────────
# A-1 — Decimal → JSON 숫자
# ─────────────────────────────────────────────────────────────────────────────

async def test_c266_a1_1_change_rate_is_json_number_not_string():
    """A-1: `change_rate` 가 직렬화된 JSON 본문에서 문자열이 아니라 숫자여야 한다.

    ⚠️ 파이썬 객체 레벨이 아니라 **응답 JSON 파싱 결과** 레벨이어야 한다 —
    그 경계가 바로 이 결함이 3개월간 숨은 지점이다(라우트 안에서는 Decimal 이고
    pydantic v2 가 JSON 모드에서 문자열로 바꾼다).
    """
    resp = _get([_sample_row()])

    assert resp.status_code == 200, f"status={resp.status_code} body={resp.text}"
    row = resp.json()["data"][0]

    assert _is_json_number(row["change_rate"]), (
        f"change_rate 가 JSON 숫자가 아니다: {row['change_rate']!r} "
        f"(type={type(row['change_rate']).__name__}). "
        f"프론트 `row.change_rate.toFixed(2)` 가 TypeError 로 죽는 지점. "
        f"raw body={resp.text}"
    )
    assert row["change_rate"] == 0.0


async def test_c266_a1_2_prtt_rate_is_json_number_not_string():
    """A-1: `prtt_rate`(NUMERIC(8,4)) 도 같은 계약 — 값까지 보존한다."""
    resp = _get([_sample_row()])

    row = resp.json()["data"][0]
    assert _is_json_number(row["prtt_rate"]), (
        f"prtt_rate 가 JSON 숫자가 아니다: {row['prtt_rate']!r}"
    )
    assert row["prtt_rate"] == pytest.approx(1.23), (
        f"Decimal→float 변환이 값을 바꿨다: {row['prtt_rate']!r} != 1.23"
    )


async def test_c266_a1_3_conversion_is_field_name_agnostic():
    """A-1: 필드명 하드코딩 금지 — 미래에 늘어날 NUMERIC 컬럼도 자동으로 덮인다.

    `change_rate`/`prtt_rate` 만 열거하는 구현은 이 케이스에서 붉어진다.
    """
    resp = _get([_sample_row(future_numeric_col=decimal.Decimal("-3.5000"))])

    row = resp.json()["data"][0]
    assert _is_json_number(row["future_numeric_col"]), (
        f"필드명을 열거한 구현으로 보인다 — 미지의 NUMERIC 컬럼 "
        f"future_numeric_col 이 {row['future_numeric_col']!r} 로 남았다. "
        f"값 타입(`isinstance(v, Decimal)`)으로 판정해야 한다."
    )
    assert row["future_numeric_col"] == pytest.approx(-3.5)


async def test_c266_a1_4_raw_jsonb_is_not_recursively_converted():
    """A-1b: `raw` 안쪽은 **변형되지 않는다** — 사이클 81 G-AST1 "raw 변형 0" 영속.

    raw 안에 Decimal 이 있어도 그대로 통과해야 한다. 오늘 pydantic v2 는 그것을
    문자열로 직렬화하므로 **문자열로 남아 있음**이 곧 "라우트가 raw 를 건드리지
    않았다"의 증거다. 재귀 변환을 넣으면 숫자가 되어 이 단언이 붉어진다.
    """
    raw = {"stck_clpr": "75000", "nested_dec": decimal.Decimal("9.8700"), "n": 3}
    resp = _get([_sample_row(raw=raw)])

    row = resp.json()["data"][0]
    assert row["raw"]["nested_dec"] == "9.8700", (
        f"raw 안쪽이 변형됐다: {row['raw']['nested_dec']!r}. "
        f"사이클 81 G-AST1 'raw 변형 0' 위반 — raw 키는 값을 그대로 전달한다."
    )
    assert row["raw"]["stck_clpr"] == "75000"
    assert row["raw"]["n"] == 3
    assert set(row["raw"]) == {"stck_clpr", "nested_dec", "n"}


async def test_c266_a1_5_non_decimal_types_untouched():
    """A-1c: Decimal 이 아닌 타입은 손대지 않는다 — 기존 직렬화 계약 보존.

    특히 `bas_dd` 는 `DATE` 컬럼이라 직렬화는 `YYYY-MM-DD` 다
    (프론트 타입 주석의 `YYYYMMDD` 는 거짓 — B-2 에서 주석만 시정).
    """
    resp = _get([_sample_row(flng_cls_code=None)])

    row = resp.json()["data"][0]
    assert row["bas_dd"] == "2026-09-05", f"bas_dd={row['bas_dd']!r}"
    assert row["ticker"] == "005930" and isinstance(row["ticker"], str)
    assert row["open_price"] == 74000 and isinstance(row["open_price"], int)
    assert row["volume"] == 1_000_000 and isinstance(row["volume"], int)
    assert row["flng_cls_code"] is None, "None 을 임의로 바꾸지 않는다"


async def test_c266_a1_6_source_rows_are_not_mutated():
    """A-1: `get_recent_daily` 반환값은 **읽기 전용** — 새 dict 를 만든다.

    같은 row 객체가 다른 소비자(6 전략 prepare / 터틀 ATR)에게 갈 수 있으므로
    라우트가 제자리에서 값을 바꾸면 매매 행위 변경이다.
    """
    raw = {"stck_clpr": "75000"}
    source = _sample_row(raw=raw)
    rows = [source]

    resp = _get(rows)
    assert resp.status_code == 200

    assert isinstance(source["change_rate"], decimal.Decimal), (
        f"원본 row 가 제자리에서 변형됐다: change_rate={source['change_rate']!r}. "
        f"새 dict 로 사영해야 한다(같은 객체가 전략 prepare 로 간다)."
    )
    assert isinstance(source["prtt_rate"], decimal.Decimal)
    assert source["bas_dd"] == datetime.date(2026, 9, 5)
    assert source["raw"] is raw, "raw 는 같은 객체를 그대로 전달한다"
    assert rows[0] is source, "리스트 원소를 갈아끼우지 않는다"


async def test_c266_a1_7_conversion_failure_is_fail_open():
    """A-1d: 변환 실패는 **fail-open** — 원값 유지, 200 유지.

    응답이 통째로 사라지는(500) 것보다 그 한 칸이 문자열로 남는 편이 낫다.
    """

    class _ExplodingDecimal(decimal.Decimal):
        def __float__(self) -> float:  # noqa: D105
            raise ValueError("float() 폭발 — fail-open 경로 재현")

    resp = _get([_sample_row(change_rate=_ExplodingDecimal("1.0000"))])

    assert resp.status_code == 200, (
        f"변환 실패가 응답을 통째로 죽였다 (status={resp.status_code}) — "
        f"fail-open 계약 위반. body={resp.text}"
    )
    row = resp.json()["data"][0]
    assert "change_rate" in row, "fail-open 은 키를 지우는 것이 아니라 원값 유지다"
    # 다른 필드는 정상 변환되어야 한다 (한 칸 실패가 전체를 막지 않는다)
    assert _is_json_number(row["prtt_rate"]), (
        f"한 필드의 변환 실패가 같은 row 의 다른 필드까지 막았다: {row!r}"
    )


async def test_c266_a1_8_all_rows_converted_not_just_first():
    """A-1: 사영은 **모든 row** 에 적용된다 (첫 행만 고치는 구현 차단)."""
    rows = [
        _sample_row(bas_dd=datetime.date(2026, 9, 5), change_rate=decimal.Decimal("1.2300")),
        _sample_row(bas_dd=datetime.date(2026, 9, 4), change_rate=decimal.Decimal("-2.5000")),
        _sample_row(bas_dd=datetime.date(2026, 9, 3), change_rate=decimal.Decimal("0.0000")),
    ]
    resp = _get(rows, days=3)

    data = resp.json()["data"]
    assert len(data) == 3
    for i, r in enumerate(data):
        assert _is_json_number(r["change_rate"]), (
            f"row[{i}] change_rate 미변환: {r['change_rate']!r}"
        )
    assert [r["change_rate"] for r in data] == [
        pytest.approx(1.23),
        pytest.approx(-2.5),
        pytest.approx(0.0),
    ]


async def test_c266_a1_9_envelope_and_call_contract_preserved():
    """A-1: 기존 계약(ApiResponse envelope · 호출 인자) 무변경 — 회귀 방지."""
    with patch(
        "src.routes.stock_master.stock_master_daily.get_recent_daily",
        new_callable=AsyncMock,
        return_value=[_sample_row()],
    ) as mock_get:
        resp = _client().get("/api/stock-master/005930/daily?days=7")

    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list) and len(body["data"]) == 1
    assert body["message"] == "1일 일봉"
    mock_get.assert_awaited_once_with(ticker="005930", days=7)


# ─────────────────────────────────────────────────────────────────────────────
# A-2 — DB 예외 은폐 중단 (404 vs 500 분리)
# ─────────────────────────────────────────────────────────────────────────────

async def test_c266_a2_1_db_exception_becomes_500_not_404():
    """A-2: `get_recent_daily` 예외 → **500**. 라우트가 삼켜 404 로 위장하지 않는다.

    ⚠️ **이 500 경로는 오늘 운영에서 실질적으로 도달하지 않는다** —
    `src/db/stock_master_daily.py::get_recent_daily` 자신이 내부에서
    `except Exception → return []` 로 이미 삼키기 때문이다(같은 파일 283-289행).
    그 db 모듈은 6 전략 `prepare()` + 터틀 사이징 ATR 을 공유하므로 별도 승인 +
    행위 영향 평가 대상이라 이번 사이클에서 고치지 않는다(후속 F-1).

    ⇒ 따라서 이것은 monkeypatch 로만 재현되는 **계약 가드**다. 지키는 것은
    "라우트가 더 이상 은폐하지 않는다"는 성질이며, db 가 나중에 예외를 올리도록
    바뀌는 순간 이 가드가 실동한다. 이 테스트를 '도달 불가'라며 지우면 안 된다.

    ⚠️ 종전 가드 `test_cycle124_stock_master_daily_route.py::test_g_daily2b_graceful_on_exception`
    이 정확히 반대(예외 → 404)를 못박고 있다 — Green 단계에서 그 파일도 함께
    갱신해야 한다(계약 반전, 의도된 것).
    """
    resp = _get(None, ticker="000001", raises=RuntimeError("DB 장애"))

    assert resp.status_code == 500, (
        f"DB 예외가 {resp.status_code} 로 위장됐다 — 404('없음')와 "
        f"500('실패')는 분리되어야 한다. body={resp.text}"
    )
    assert resp.status_code != 404, "예외를 '데이터 없음'으로 은폐 금지"


async def test_c266_a2_2_db_exception_is_logged_with_traceback(caplog):
    """A-2: 예외는 ERROR 로 **traceback 과 함께** 남는다 (logger.exception).

    ⚠️ CI 루트 로거는 DEBUG 라 실패 흔적 debug 행까지 잡힌다 —
    단언은 `levelno >= ERROR` ∧ 로거 이름 `src.routes.stock_master` 로 한정한다.
    """
    caplog.set_level(logging.DEBUG)

    resp = _get(None, ticker="000001", raises=RuntimeError("DB 장애"))
    assert resp.status_code == 500

    hits = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and r.name.startswith("src.routes.stock_master")
    ]
    assert hits, (
        "DB 예외가 조용히 사라졌다 — src.routes.stock_master 로거에 ERROR 행이 없다. "
        f"records={[(r.name, r.levelname) for r in caplog.records]}"
    )
    assert any(r.exc_info is not None for r in hits), (
        "traceback 이 없다 — `logger.error` 가 아니라 `logger.exception` 을 써야 "
        "진짜 DB 장애의 원인을 사후에 읽을 수 있다."
    )
    assert any("000001" in r.getMessage() for r in hits), (
        f"로그에 ticker 가 없다 — 어느 종목에서 터졌는지 알 수 없다. "
        f"messages={[r.getMessage() for r in hits]}"
    )


async def test_c266_a2_3_http_exception_is_not_swallowed_as_500():
    """A-2: 라우트가 스스로 올린 `HTTPException(404)` 를 500 으로 재포장하지 않는다.

    `except Exception` 을 그대로 두고 `raise HTTPException(500)` 만 덧붙이면
    빈 rows 의 404 가 500 으로 바뀐다 — 그 구현을 잡는다.
    """
    resp = _get([])
    assert resp.status_code == 404, (
        f"빈 rows 는 여전히 404 여야 한다 (got {resp.status_code}). "
        f"404('적재 대상 아님')와 500('실패')의 분리가 이 사이클의 핵심이다."
    )


async def test_c266_a2_4_post_only_path_still_405():
    """A-2 회귀: 사이클 90 라우팅 가드(POST only 경로 → 405) 무변경."""
    resp = _client().get("/api/stock-master/daily/daily")
    assert resp.status_code == 405, f"got {resp.status_code}: {resp.text}"


# ─────────────────────────────────────────────────────────────────────────────
# A-3 — 404 문구: "오류" 가 아니라 "적재 대상 아님"
# ─────────────────────────────────────────────────────────────────────────────

async def test_c266_a3_1_404_detail_says_not_loaded_not_error():
    """A-3: 404 `detail` 은 미적재 취지 — 운영 실측 3,583 중 1,773(49.5%)이 정상 미적재다.

    일봉은 전 종목이 아니라 전략 유니버스 대상만 적재된다. "데이터 없음"은
    운영자에게 장애처럼 읽힌다.
    """
    resp = _get([], ticker="123456", days=30)

    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "123456" in detail, f"ticker 누락: {detail!r}"
    assert "미적재" in detail, (
        f"404 문구가 미적재 취지가 아니다: {detail!r} — "
        f"일봉은 전 종목 적재가 아니므로 '오류'가 아니라 '적재 대상 아님'이다."
    )
    assert "days=30" in detail, f"days 컨텍스트 누락: {detail!r}"


async def test_c266_a3_2_404_detail_stays_a_string_not_a_dict():
    """A-3: 응답 형태 변경 최소화 — `detail` 은 문자열을 유지한다.

    프론트가 `error.response?.status === 404` 로만 판별하므로(DetailModal 의
    `is404` 선례) 구조를 dict 로 바꿀 이유가 없다.
    """
    resp = _get([], ticker="123456")
    assert isinstance(resp.json()["detail"], str)


# ─────────────────────────────────────────────────────────────────────────────
# D-1 (cycle266 마무리 라운드, tester 적대 검토) — 404 문구가 원인을 **단정하지 않는다**
#
# A-3 의 새 문구("미적재 — 전략 유니버스 대상만 적재됩니다")는 종전 "일봉 데이터 없음"
# 보다 친절하지만 **원인을 단정**한다. 라우트는 더 이상 예외를 삼키지 않으나
# `src/db/stock_master_daily.py::get_recent_daily` 가 **자신이** DB 예외를 삼키고
# `[]` 를 돌려주므로(그 모듈은 6 전략 prepare + 터틀 ATR 공유 = 이 사이클 무접촉),
# 진짜 DB 장애도 여기 404 로 도착한다. 운영자가 그것을 "정상 미적재"로 읽고 넘기면
# 장애를 놓친다 ⇒ detail 에 단서 + **검색 가능한 로그 토큰**을 함께 싣는다.
#
# 실제 로그 토큰(양쪽 다 `stock_master_daily` 로 잡힌다):
#   db   : "[stock_master_daily] get_recent_daily 실패 graceful ticker=..."
#   route: "[stock_master_daily_route_error] ticker=... days=..."
# ─────────────────────────────────────────────────────────────────────────────

async def test_c266_d1_1_404_detail_does_not_assert_the_cause_alone():
    """D-1: 404 detail 이 "미적재" 만 말하고 끝나지 않는다 — 조회 실패 가능성 단서.

    이 단서가 사라지면 안내가 원인을 단정하게 되고, `get_recent_daily` 가 삼킨
    DB 장애가 "정상 미적재" 로 위장된다.
    """
    detail = _get([], ticker="123456", days=30).json()["detail"]

    # A-3 필수 3요소는 그대로 유지 (계약 회귀 방지)
    assert "123456" in detail and "미적재" in detail and "days=30" in detail, detail

    assert "실패" in detail, (
        f"404 문구가 조회 실패 가능성을 말하지 않는다: {detail!r} — "
        f"`get_recent_daily` 가 DB 예외를 스스로 삼켜 `[]` 를 돌려주므로 "
        f"진짜 장애도 이 404 로 도착한다(D-1)."
    )


async def test_c266_d1_2_404_detail_carries_a_greppable_log_token():
    """D-1: 단서는 운영자가 **실제로 검색할 수 있는 토큰**을 담는다.

    "로그를 확인하세요" 만으로는 무엇을 찾을지 알 수 없다. db 모듈과 라우트가
    남기는 두 마커 모두 `stock_master_daily` 로 grep 된다.
    """
    detail = _get([], ticker="123456", days=30).json()["detail"]

    assert "stock_master_daily" in detail, (
        f"검색 가능한 로그 토큰 누락: {detail!r} — "
        f"db 마커 '[stock_master_daily] get_recent_daily 실패 graceful' 과 "
        f"라우트 마커 '[stock_master_daily_route_error]' 를 모두 잡는 접두다(D-1)."
    )


def test_c266_d1_3_log_token_in_detail_matches_the_real_markers():
    """D-1: 안내가 가리키는 토큰이 **실제로 남는 로그 문자열**과 맞는지 소스로 대조.

    문구만 고치고 로그 마커를 바꾸면(또는 그 반대) 안내가 존재하지 않는 것을
    찾으라고 시킨다. 두 파일의 실제 리터럴을 읽어 대조한다.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    route_src = (root / "src/routes/stock_master.py").read_text(encoding="utf-8")
    db_src = (root / "src/db/stock_master_daily.py").read_text(encoding="utf-8")

    assert "[stock_master_daily_route_error]" in route_src, (
        "라우트 500 경로의 로그 마커가 사라졌다 — 404 안내가 가리키는 대상이 없어진다."
    )
    assert "[stock_master_daily] get_recent_daily 실패" in db_src, (
        "db 모듈의 graceful 마커가 바뀌었다 — 404 안내의 토큰과 어긋난다. "
        "(이 파일은 db 모듈을 **읽기만** 한다 — 무접촉 제약 유지)"
    )

    detail_line = [
        line for line in route_src.splitlines()
        if "HTTPException(404" in line and "미적재" in line
    ]
    assert len(detail_line) == 1, f"404 detail 리터럴을 특정하지 못했다: {detail_line!r}"
    assert "stock_master_daily" in detail_line[0], detail_line[0]
