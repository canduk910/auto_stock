"""cycle282 Red — `GET /api/market-state` 라우트 계약 (G1~G18).

정본 = `_workspace/red/cycle282_market_state_spec.md` §3 · §6(M9·M10·M15) · §7.1 G.

## 이 파일이 지키는 것

1. **표와 커서는 한 응답에서 나온다** (M9) — `markets[m].row_id` 는 반드시 같은 응답의
   `table` 안에 있고, 둘 다 **하나의 `as_of`** 에서 파생된다(G3·G5). 갈라지면 화면이
   "정규장" 이라면서 정규장 행이 없는 표를 그린다.
2. **모른다를 안다로 바꾸지 않는다** (M10) — 휴장일 조회가 실패하면 `is_trading_day` 는
   `null` 이고 `trading_day_source` 는 `"unknown"` 이다. 기존 `is_market_open()` 의
   fail-open **True** 를 그대로 쓰면 이 계약을 구조적으로 만족할 수 없다(명세 추가-7).
3. **빈 표는 200 이 아니라 500** (M15) — cycle266 의 `except Exception: rows=[]` 가
   진짜 DB 장애를 404 로 3개월 은폐한 그 실패를 되풀이하지 않는다.

## Red 상태 (작성 시점)

`src/routes/market_state.py` · `src/engine/market_state.py` · `src.api.condition.is_trading_day`
가 전부 없다. 라우트 미등록이라 모든 요청이 404 이고, 각 테스트는 "라우트 미등록" 메시지와
함께 FAIL 한다(수집 오류 0).

## 목 전략 — respx 대신 `condition.kis_get_quote` monkeypatch

명세 §7.1 은 respx 를 적었지만, `kis_get_quote` 는 보조 시세계정 풀·토큰 발급을 경유해
HTTP 레벨 목이 계정 상태에 의존한다. 이 리포의 condition 계열 단위 테스트는 예외 없이
`condition.kis_get_quote` 를 AsyncMock 으로 바꾼다(`test_condition_stock_basics.py` 외).
같은 seam 을 써서 **호출 횟수**(G9·G10 캐시 계약)를 직접 센다.
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_UTC = timezone.utc
PATH = "/api/market-state"

_D_0911 = date(2026, 9, 11)
_D_0912 = date(2026, 9, 12)
_D_0914 = date(2026, 9, 14)

#: 13:05:22 KST — 평범한 정규장(KRX K3 / NXT N3)
AT_1305 = datetime(2026, 9, 11, 13, 5, 22, tzinfo=_KST)
#: 08:35:00 KST — K1 ⊃ K2 동시 중첩
AT_0835 = datetime(2026, 9, 11, 8, 35, 0, tzinfo=_KST)

#: §3.1 응답 `data` 최상위 키 — **전수 일치**(G1)
TOP_KEYS = {
    "table_version", "as_of_kst", "on_date", "preview", "cursor_disabled_reason",
    "is_trading_day", "trading_day_source", "market_order", "exchange_order",
    "markets", "table", "order_divisions", "phases", "vocab",
    "findings", "board_note", "unconfirmed_note",
}
STATE_KEYS = {
    "market", "market_label_ko", "row_id", "phase", "name_ko", "tone", "window",
    "match_kind", "match_ko", "is_open", "can_order", "market_order_ok",
    "order_divisions", "order_divisions_by_row", "concurrent_row_ids",
    "quote_channel", "quote_channel_evidence", "decided_by", "code_seen",
    "confidence", "confidence_notes", "seconds_to_next", "next_boundary",
    "next_row_id", "next_phase",
}
ROW_KEYS = {
    "row_id", "market", "start", "end", "phase", "name_ko", "tone",
    "match_kind", "match_ko", "order_divisions", "order_divisions_pending",
    "order_divisions_expired", "can_order", "market_order_ok", "quote_channel",
    "quote_channel_evidence", "overlap_ok", "priority", "effective_from",
    "effective_to", "confidence", "note", "rel",
}
CATALOG_KEYS = {
    "code", "name_ko", "group_ko", "exchange_support",
    "effective_from", "effective_to", "confidence", "note",
}


# ---------------------------------------------------------------------------
# 지연 import — 미구현 단계에서 수집 오류 대신 FAIL
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _import_route():
    try:
        return importlib.import_module("src.routes.market_state"), None
    except Exception as exc:  # noqa: BLE001
        return None, exc


def _route_mod():
    mod, exc = _import_route()
    if mod is None:
        pytest.fail(
            "src/routes/market_state.py 미구현 (Red) — "
            f"{type(exc).__name__}: {exc}"
        )
    return mod


@lru_cache(maxsize=1)
def _import_leaf():
    try:
        return importlib.import_module("src.engine.market_state"), None
    except Exception as exc:  # noqa: BLE001
        return None, exc


def _leaf():
    mod, exc = _import_leaf()
    if mod is None:
        pytest.fail(f"src/engine/market_state.py 미구현 (Red) — {type(exc).__name__}: {exc}")
    return mod


# ---------------------------------------------------------------------------
# KIS 휴장일 스텁 (`condition.kis_get_quote` seam)
# ---------------------------------------------------------------------------
@dataclass
class HolidayStub:
    mode: str = "open"            # open | closed | row_missing | error | slow
    delay: float = 0.0
    calls: list = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.calls)


@pytest.fixture(autouse=True)
def holiday(monkeypatch) -> HolidayStub:
    """모든 테스트에서 KIS 휴장일 호출을 가로챈다(실 네트워크 차단)."""
    from src.api import condition as cond

    stub = HolidayStub()

    async def _fake_kis_get_quote(url, tr_id, params=None, **kwargs):
        params = dict(params or {})
        stub.calls.append({"url": url, "tr_id": tr_id, "params": params})
        if stub.delay:
            await asyncio.sleep(stub.delay)
        if stub.mode == "error":
            raise RuntimeError("KIS chk-holiday 장애 (테스트 주입)")
        if stub.mode == "timeout":
            raise asyncio.TimeoutError("KIS chk-holiday 지연 (테스트 주입)")
        bass = params.get("BASS_DT", "")
        if stub.mode == "row_missing":
            return {"output": [{"bass_dt": "19990101", "opnd_yn": "Y"}]}
        return {"output": [{"bass_dt": bass, "opnd_yn": "N" if stub.mode == "closed" else "Y"}]}

    monkeypatch.setattr(cond, "kis_get_quote", _fake_kis_get_quote, raising=True)
    return stub


@pytest.fixture(autouse=True)
def _clear_trading_day_cache():
    """휴장일 캐시는 테스트 간 누수 금지(성공은 만료 없이 캐시되는 계약이라 더 그렇다)."""
    def _invalidate():
        mod, _ = _import_route()
        if mod is not None and hasattr(mod, "invalidate_market_state_cache"):
            try:
                mod.invalidate_market_state_cache()
            except Exception:
                pass

    _invalidate()
    yield
    _invalidate()


@pytest.fixture
def client():
    from src.main import app

    return TestClient(app)


@pytest.fixture
def soft_client():
    """서버 예외를 재던지지 않고 500 응답으로 보는 클라이언트(M15 검증용)."""
    from src.main import app

    return TestClient(app, raise_server_exceptions=False)


def _fetch(client, *, params=None, at=AT_1305, expect=200):
    with freeze_time(at):
        res = client.get(PATH, params=params or {})
    assert res.status_code != 404 or expect == 404, (
        f"GET {PATH} → 404. 라우트 미등록 (Red) — Green 이 "
        "`src/routes/market_state.py` + `src/main.py` include_router 1행을 만든다"
    )
    assert res.status_code == expect, (
        f"GET {PATH} {params or {}} → {res.status_code} (기대 {expect}) body={res.text[:300]}"
    )
    return res


def _data(client, *, params=None, at=AT_1305):
    body = _fetch(client, params=params, at=at).json()
    assert set(body) >= {"success", "data", "message"}, f"ApiResponse 래퍼 위반 — {sorted(body)}"
    assert body["success"] is True, f"success=False — {body.get('message')!r}"
    return body["data"]


# ===========================================================================
# G1~G4 — 응답 형태
# ===========================================================================
def test_g1_envelope_and_top_level_keys(client):
    """G1 — `{success,data,message}` 래퍼 ∧ data 최상위 키 전수 일치."""
    data = _data(client)
    assert set(data) == TOP_KEYS, (
        f"최상위 키 불일치 — 누락 {sorted(TOP_KEYS - set(data))} / "
        f"초과 {sorted(set(data) - TOP_KEYS)}"
    )
    assert data["table_version"] == _leaf().TABLE_VERSION


def test_g2_markets_keys_match_market_order(client):
    """G2 — `markets` 키 집합 == `market_order`(프론트가 map 할 배열, 추가-4)."""
    data = _data(client)
    assert data["market_order"] == ["KRX", "NXT"], f"market_order={data['market_order']}"
    assert set(data["markets"]) == set(data["market_order"])
    for m, st in data["markets"].items():
        assert set(st) >= STATE_KEYS, f"{m} 상태 키 누락 {sorted(STATE_KEYS - set(st))}"
        assert st["market"] == m
        assert st["decided_by"] == "time" and st["code_seen"] is None


def test_g3_cursor_points_inside_the_same_table(client):
    """G3 (M9) — 커서는 같은 응답의 표 안을 가리킨다. 표 밖이면 화면이 거짓말한다."""
    data = _data(client)
    for m, st in data["markets"].items():
        ids = {r["row_id"] for r in data["table"] if r["market"] == m}
        assert st["row_id"] is None or st["row_id"] in ids, (
            f"{m} 커서 {st['row_id']!r} 가 표({sorted(ids)}) 밖이다 — M9 위반"
        )
        for rid in st["concurrent_row_ids"]:
            assert rid in ids, f"{m} 동시 행 {rid!r} 가 표 밖이다"
    for row in data["table"]:
        assert set(row) >= ROW_KEYS, f"{row.get('row_id')} 행 키 누락 {sorted(ROW_KEYS - set(row))}"


def test_g4_as_of_is_kst_iso_and_on_date_matches(client):
    """G4 — `as_of_kst` 는 `+09:00` ISO ∧ `on_date` 는 그 날짜."""
    data = _data(client)
    as_of = data["as_of_kst"]
    assert as_of.endswith("+09:00"), f"as_of_kst={as_of!r} — KST 오프셋 명시 계약 위반"
    parsed = datetime.fromisoformat(as_of)
    assert parsed.utcoffset() == timedelta(hours=9)
    assert data["on_date"] == parsed.date().isoformat(), (
        f"on_date={data['on_date']} vs as_of {parsed.date()}"
    )
    assert data["preview"] is False and data["cursor_disabled_reason"] is None


def test_g5_single_as_of_is_shared_by_cursor_and_table(client, monkeypatch):
    """G5 (M9·m11·m12) — 시장 2개 커서와 표가 **같은 `as_of` 객체 하나**에서 나온다.

    시장마다 `datetime.now()` 를 다시 부르거나 `get_market_table()` 을 인자 없이 부르면
    자정을 넘기는 순간 표와 커서가 다른 날짜를 본다.
    """
    mod = _route_mod()
    real_state = mod.get_market_state
    real_table = mod.get_market_table
    seen = {"state": [], "table": []}

    def _rec_state(now=None, *, market="KRX"):
        seen["state"].append(now)
        return real_state(now, market=market)

    def _rec_table(on_date=None):
        seen["table"].append(on_date)
        return real_table(on_date)

    monkeypatch.setattr(mod, "get_market_state", _rec_state, raising=True)
    monkeypatch.setattr(mod, "get_market_table", _rec_table, raising=True)

    _data(client)

    assert len(seen["state"]) == 2, (
        f"get_market_state 호출 {len(seen['state'])}회 — 시장 2개에 정확히 1회씩이어야 한다"
    )
    first = seen["state"][0]
    assert first is not None, (
        "라우트가 leaf 에 `now=None` 을 넘겼다 — leaf 가 시장마다 현재시각을 다시 읽게 된다"
    )
    assert all(x is first for x in seen["state"]), "커서 두 개가 서로 다른 as_of 를 썼다"
    assert len(seen["table"]) == 1, f"get_market_table 호출 {len(seen['table'])}회"
    assert seen["table"][0] == first.date(), (
        f"표 날짜 {seen['table'][0]} != 커서 날짜 {first.date()} — 자정 경계에서 갈라진다"
    )


# ===========================================================================
# G6~G10 — 휴장일 결합 (M10 + 캐시)
# ===========================================================================
def test_g6_trading_day_true(client, holiday):
    """G6 — `opnd_yn="Y"` → True ∧ source="kis"."""
    holiday.mode = "open"
    data = _data(client)
    assert data["is_trading_day"] is True, f"is_trading_day={data['is_trading_day']!r}"
    assert data["trading_day_source"] == "kis"
    assert holiday.count == 1, f"KIS 호출 {holiday.count}회"
    assert holiday.calls[0]["tr_id"] == "CTCA0903R"
    assert holiday.calls[0]["params"].get("BASS_DT") == "20260911", (
        f"조회 날짜 {holiday.calls[0]['params']} — KST 오늘이어야 한다"
    )


def test_g7_trading_day_false(client, holiday):
    """G7 — `opnd_yn="N"` → False(표는 그대로 나오고 화면이 '휴장일' 을 띄운다)."""
    holiday.mode = "closed"
    data = _data(client)
    assert data["is_trading_day"] is False
    assert data["trading_day_source"] == "kis"
    assert data["table"], "휴장일이라고 표를 비우면 안 된다 — 표는 시각 상수다"


@pytest.mark.parametrize("mode", ["error", "row_missing"], ids=["exception", "row_missing"])
def test_g8_trading_day_failure_is_null_not_true(client, holiday, mode):
    """G8 (M10·m13) — 실패는 `null` 이다. 임의 True 금지 — '모른다' 를 '개장' 으로 바꾸지 않는다."""
    holiday.mode = mode
    data = _data(client)
    assert data["is_trading_day"] is None, (
        f"조회 실패인데 is_trading_day={data['is_trading_day']!r} — "
        "`is_market_open()` 의 fail-open True 를 그대로 쓰면 M10 을 만족할 수 없다"
    )
    assert data["trading_day_source"] == "unknown"


def test_g8b_trading_day_timeout_is_null(client, holiday):
    """G8b (M10) — KIS 지연은 화면 폴링을 물고 늘어지지 않고 `null` 로 끝난다.

    실제 대기로 재지 않는다 — freezegun 이 `time.monotonic` 을 얼려 이벤트 루프 시계까지
    멈추므로 '진짜 1초 지연' 테스트는 타임아웃이 영원히 안 오고 스위트가 60초 멈춘다.
    대신 지연의 **관측 결과**(`TimeoutError`)를 주입하고, 타임아웃 상한이 실재하는지는
    상수로 확인한다(§3.3 `_TRADING_DAY_TIMEOUT = 5.0`).
    """
    holiday.mode = "timeout"
    data = _data(client)
    assert data["is_trading_day"] is None, "타임아웃을 True 로 메우면 M10 위반"
    assert data["trading_day_source"] == "unknown"

    mod = _route_mod()
    limit = getattr(mod, "_TRADING_DAY_TIMEOUT", None)
    assert isinstance(limit, (int, float)) and 0 < limit <= 10, (
        f"_TRADING_DAY_TIMEOUT={limit!r} — 화면 30초 폴링이 KIS 지연에 물리지 않게 "
        "상한이 있어야 한다"
    )


def test_g8c_route_absorbs_unexpected_raise_as_null(client, monkeypatch):
    """G8c (M10·m13 — Green 검증 라운드 추가) — 라우트의 **바깥 방어선**도 True 로 메우지 않는다.

    `condition.is_trading_day` 는 스스로 예외를 삼켜 None 을 돌려주므로, 라우트의
    `try/except` 는 그 함수가 못 잡는 것 — `asyncio.wait_for` 타임아웃(KIS 가 응답 없이
    5초를 넘김) 과 호출 자체의 실패 — 만 받는다. 그 경로는 G8/G8b 의 stub 으로는 한 번도
    실행되지 않아서, 거기에 `value = True` 를 심어도 스위트가 조용히 초록이었다
    (뮤테이션 실측). **모른다를 개장으로 바꾸는 자리는 한 곳도 남기지 않는다.**
    """
    mod = _route_mod()

    async def _timeout(_target):
        raise asyncio.TimeoutError("wait_for 상한 초과 (테스트 주입)")

    monkeypatch.setattr(mod.condition_api, "is_trading_day", _timeout, raising=True)
    data = _data(client)
    assert data["is_trading_day"] is None, (
        f"라우트 방어선이 is_trading_day={data['is_trading_day']!r} 로 메웠다 — M10 위반"
    )
    assert data["trading_day_source"] == "unknown"
    assert data["table"], "휴장일을 모른다고 표를 비우면 안 된다 — 표는 시각 상수다"


def test_g9_positive_result_is_cached(client, holiday):
    """G9 — 같은 날짜 2회 요청 = KIS 1회. 두 번째 응답은 `source="cache"`."""
    holiday.mode = "open"
    first = _data(client)
    second = _data(client)
    assert holiday.count == 1, (
        f"KIS 호출 {holiday.count}회 — 30초 폴링이 그대로 KIS 호출이 된다"
    )
    assert first["trading_day_source"] == "kis"
    assert second["trading_day_source"] == "cache"
    assert second["is_trading_day"] is True


def test_g10_failure_is_cached_only_briefly(client, holiday, monkeypatch):
    """G10 (m14) — 실패는 짧게만 캐시한다. 영구 캐시면 KIS 가 살아나도 하루 종일 '확인 불가'."""
    mod = _route_mod()
    holiday.mode = "error"

    _data(client)
    _data(client)
    assert holiday.count == 1, (
        f"음성 캐시 부재 — KIS 장애 중 폴링마다 호출 ({holiday.count}회)"
    )

    mod.invalidate_market_state_cache()
    holiday.calls.clear()
    monkeypatch.setattr(mod, "_TRADING_DAY_NEG_TTL", 0.0, raising=True)
    _data(client)
    _data(client)
    assert holiday.count == 2, (
        f"음성 캐시가 만료되지 않는다 (KIS 호출 {holiday.count}회) — "
        "실패를 영구 캐시하면 5분 뒤 복구를 화면이 영원히 모른다"
    )


# ===========================================================================
# G11~G14 — preview · 오류 규약
# ===========================================================================
def test_g11_preview_other_date_disables_cursor(client):
    """G11 — 다른 날짜 미리보기는 커서를 끈다(그 날짜의 '지금' 은 존재하지 않는다)."""
    data = _data(client, params={"on_date": _D_0914.isoformat()})
    assert data["preview"] is True
    assert data["markets"] is None, "preview 인데 커서를 계산했다 — 없는 '지금' 을 지어낸 것이다"
    assert data["cursor_disabled_reason"] == "preview_other_date"
    assert data["on_date"] == _D_0914.isoformat()
    assert datetime.fromisoformat(data["as_of_kst"]).date() == _D_0911, (
        "as_of_kst 는 preview 여도 **지금** 이다"
    )
    ids = {r["row_id"] for r in data["table"] if r["market"] == "KRX"}
    assert "K6" in ids and "K7" not in ids, f"09-14 표가 아니다 — {sorted(ids)}"
    assert {r["rel"] for r in data["table"]} == {"unknown"}, (
        f"preview 표의 rel 이 unknown 이 아니다 — {sorted({r['rel'] for r in data['table']})}"
    )


@pytest.mark.parametrize(
    "value",
    ["2026-13-45", "not-a-date", (date(2026, 9, 11) + timedelta(days=400)).isoformat()],
    ids=["bad_month", "garbage", "out_of_range"],
)
def test_g12_invalid_on_date_is_422(client, value):
    """G12 — 형식 오류·±365일 밖은 422(조용한 오늘 폴백 금지)."""
    _fetch(client, params={"on_date": value}, expect=422)


def test_g13_empty_table_is_500_today_and_404_for_preview(soft_client, monkeypatch):
    """G13 (M15·m15) — **오늘** 표가 비면 200 빈 화면이 아니라 500 이다.

    cycle266 은 `except Exception: rows=[]` 로 진짜 장애를 404 로 3개월 은폐했다.
    표는 코드 상수라 '오늘 행 0' 은 사용자 입력 문제가 아니라 **데이터 결함**이다.
    """
    mod = _route_mod()
    monkeypatch.setattr(mod, "get_market_table", lambda on_date=None: (), raising=True)

    res = _fetch(soft_client, expect=500)
    assert "market_table_empty" in res.text, f"본문에 사유가 없다 — {res.text[:300]}"

    res2 = _fetch(soft_client, params={"on_date": _D_0914.isoformat()}, expect=404)
    assert "no_effective_rows" in res2.text, f"본문에 사유가 없다 — {res2.text[:300]}"


def test_g14_leaf_exception_is_500_not_empty_200(soft_client, monkeypatch):
    """G14 (M15) — leaf 예외를 흡수해 200 빈 응답으로 바꾸지 않는다."""
    mod = _route_mod()

    def _boom(*a, **kw):
        raise RuntimeError("leaf 폭발 (테스트 주입)")

    monkeypatch.setattr(mod, "get_market_state", _boom, raising=True)
    res = _fetch(soft_client, expect=500)
    assert res.status_code == 500


# ===========================================================================
# G15~G17 — 카탈로그 · 상수 · rel
# ===========================================================================
def test_g15_order_division_catalog_shape(client):
    """G15 — 28행 ∧ `exchange_support` 가 거래소 3키 ∧ 값 ⊆ SUPPORT_LEVELS."""
    leaf = _leaf()
    data = _data(client)
    catalog = data["order_divisions"]
    assert len(catalog) == 28, f"카탈로그 {len(catalog)}행"
    assert data["exchange_order"] == ["KRX", "NXT", "SOR"]
    levels = set(leaf.SUPPORT_LEVELS)
    seen_levels = set()
    for item in catalog:
        assert set(item) >= CATALOG_KEYS, f"{item.get('code')} 키 누락 {sorted(CATALOG_KEYS - set(item))}"
        support = item["exchange_support"]
        assert set(support) == set(data["exchange_order"]), (
            f"{item['code']}: exchange_support 키 {sorted(support)}"
        )
        assert set(support.values()) <= levels, f"{item['code']}: 미지 값 {sorted(set(support.values()))}"
        seen_levels |= set(support.values())
    by_code = {i["code"]: i for i in catalog}
    assert by_code["01"]["exchange_support"]["NXT"] == "no", "01(시장가) NXT 는 미지원이다"
    assert by_code["05"]["exchange_support"]["SOR"] == "no", "05 SOR 는 미지원이다"
    assert by_code["27"]["exchange_support"]["SOR"] == "unknown", (
        "27~29 의 SOR 는 **미확인**이다. 미지원과 같은 칸으로 그리면 브리프가 못박은 "
        "'숨기지 않는다' 가 깨진다"
    )
    assert seen_levels == levels, (
        f"세 상태가 전부 등장하지 않는다 — {sorted(seen_levels)} (화면 3상태 검증 불가)"
    )


def test_g16_constants_come_from_leaf(client):
    """G16 — findings·board_note·unconfirmed_note·phases·vocab 은 leaf 상수 그대로."""
    leaf = _leaf()
    data = _data(client)
    assert data["findings"] == list(leaf.FINDINGS), "findings 가 leaf 와 다르다"
    assert len(data["findings"]) == 2
    assert data["board_note"] == leaf.BOARD_VS_MARKET_NOTE
    assert data["unconfirmed_note"] == leaf.UNCONFIRMED_NOTE
    vocab = data["vocab"]
    assert vocab["tones"] == list(leaf.TONES)
    assert vocab["rels"] == list(leaf.RELS)
    assert vocab["support_levels"] == list(leaf.SUPPORT_LEVELS)
    assert vocab["confidences"] == list(leaf.CONFIDENCE_LEVELS)
    assert vocab["division_confidences"] == list(leaf.DIVISION_CONFIDENCE)
    phase_ids = [p["id"] for p in data["phases"]]
    assert phase_ids == [p.value for p in leaf.MarketPhase], f"phases={phase_ids}"
    for p in data["phases"]:
        assert p["label_ko"] and p["tone"] in set(leaf.TONES), f"phase {p}"


def test_g17_rel_is_server_decided(client):
    """G17 (추가-5) — 지난/현재/동시/다음 판정은 **서버**가 한다. 프론트는 `rel` 로만 칠한다."""
    data = _data(client, at=AT_1305)
    rel = {r["row_id"]: r["rel"] for r in data["table"]}
    assert rel["K1"] == "past" and rel["K2"] == "past", f"13:05 rel={rel}"
    assert rel["K3"] == "current", f"13:05 KRX 커서 행 rel={rel.get('K3')!r}"
    assert rel["K4"] == "upcoming" and rel["K5"] == "upcoming"
    assert rel["N3"] == "current"

    early = _data(client, at=AT_0835)
    rel2 = {r["row_id"]: r["rel"] for r in early["table"]}
    assert rel2["K1"] == "current", f"08:35 K1 rel={rel2.get('K1')!r}"
    assert rel2["K2"] == "concurrent", (
        f"08:35 K2 rel={rel2.get('K2')!r} — 동시에 열린 창은 'past/upcoming' 이 아니다"
    )
    krx = early["markets"]["KRX"]
    assert krx["row_id"] == "K1" and krx["concurrent_row_ids"] == ["K2"]
    assert krx["order_divisions"] == ["00", "01", "05"], (
        f"08:35 합집합 위반 — {krx['order_divisions']}"
    )
    assert set(rel2.values()) <= set(_leaf().RELS)


# ===========================================================================
# G18 — 인증
# ===========================================================================
@pytest.mark.real_api_auth
def test_g18_requires_api_key(holiday):
    """G18 — 이 경로도 `ApiAuthMiddleware` 의 전 경로 규약 안에 있다(무자격 401)."""
    from src.config import settings
    from src.main import app

    # ⚠️ `with TestClient(...)` 를 쓰지 않는다 — lifespan 이 돌면 부팅이 실제 KIS
    # `/oauth2/tokenP` 를 때린다(실측). 미들웨어는 lifespan 없이도 요청마다 돈다.
    raw = TestClient(app, raise_server_exceptions=False)
    with freeze_time(AT_1305):
        unauth = raw.get(PATH)
        authed = raw.get(PATH, headers={"X-API-Key": settings.api_auth_key})

    assert unauth.status_code == 401, (
        f"무자격 요청이 {unauth.status_code} — /health 를 뺀 전 경로가 X-API-Key 로 잠긴다"
    )
    assert authed.status_code != 404, (
        f"GET {PATH} → 404. 라우트 미등록 (Red)"
    )
    assert authed.status_code == 200, f"자격 요청 {authed.status_code} — {authed.text[:200]}"
