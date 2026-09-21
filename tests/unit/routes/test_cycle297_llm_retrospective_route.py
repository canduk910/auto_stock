"""cycle297 Red — G4: `GET /api/llm-evaluations/retrospective` 읽기 전용 라우트 계약.

명세 = `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` §3.5(라우트) · §5.1 G4.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 파일이 지키는 다섯 가지

1. **등록 순서** — `/retrospective` 가 `/{order_no}` **앞**이어야 한다. 뒤에 두면 FastAPI 가
   `retrospective` 를 주문번호로 잡아 404 다(M22). AST 로도 재지만(cycle297 G2-10) 여기서는
   **실제 라우터 매칭**으로 잰다 — 두 축이 다른 실패 모드를 덮는다.
2. **계좌번호 부재** — 리포터 스코프 키가 GET/HEAD 를 경로 무관 통과시키므로(cycle249)
   이 표면에 원문이 실리면 외부 루틴이 계좌를 읽는다. 직렬화된 **본문 문자열**을 훑는다(M21).
3. **범위 위반은 422** — `days` 1~90, `cost_pct` 0~5. 조용히 클램프하면 호출자는 자기 요청이
   무시된 것을 알 길이 없다(cycle276 `trade_date` 와 같은 관례, M23).
4. **오류를 삼키지 않는다** — DB 예외 → 500 + `[llm_eval_route_error]`. 페어 0건 → **200 + 빈 집계**
   (404 아님 — "이번 주 청산 없음" 은 오류가 아니다).
5. **`Decimal` 은 라우트가 `float` 로 사영한다** — pydantic v2 는 JSON 모드에서 `Decimal` 을
   **문자열**로 직렬화해 프론트/루틴의 산술이 죽는다(cycle266 흰 화면).

## 쓰기 0

이 라우트는 어떤 경로로도 DB 를 쓰지 않는다 — `pg.execute`/`insert`/`upsert` 호출이
모듈 소스에 없어야 한다(AST).
"""

from __future__ import annotations

import ast
import importlib
from datetime import date
import logging
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_SRC = _ROOT / "src" / "routes" / "llm_evaluations.py"

_ROUTE_MOD = "src.routes.llm_evaluations"
_TRADE_DB_MOD = "src.db.trade_history"
_EVAL_DB_MOD = "src.db.llm_buy_evaluations"

_PATH = "/api/llm-evaluations/retrospective"
_MARKER_ERROR = "[llm_eval_route_error]"

_ACCOUNT = "12345678"


def _route():
    """라우트 모듈 — 부재면 그대로 터진다(skip 금지 = 정직한 Red)."""
    return importlib.import_module(_ROUTE_MOD)


def _client() -> TestClient:
    """라우터만 실은 독립 앱 — 미들웨어/lifespan 무관, 라우트 본체만 태운다."""
    app = FastAPI()
    app.include_router(_route().router)
    return TestClient(app, raise_server_exceptions=False)


def _patch(monkeypatch, *, pairs=None, evals=None, pairs_exc=None, evals_exc=None,
           freeze_today=True) -> None:
    """`get_trade_pairs` / `list_by_order_nos` 를 fake 로.

    route 모듈 속성 + db 모듈 속성 **양쪽**을 갈아끼워 import 스타일에 의존하지 않는다
    (cycle276 `_patch_db` 관례).
    """
    route = _route()
    trade_db = importlib.import_module(_TRADE_DB_MOD)
    eval_db = importlib.import_module(_EVAL_DB_MOD)

    async def _fake_pairs(*a, **kw):
        if pairs_exc is not None:
            raise pairs_exc
        return list(pairs or [])

    async def _fake_evals(order_nos, **kw):
        if evals_exc is not None:
            raise evals_exc
        keys = {str(x) for x in (order_nos or [])}
        return [r for r in (evals or []) if str(r.get("order_no")) in keys]

    targets = [
        (trade_db, "get_trade_pairs", _fake_pairs),
        (eval_db, "list_by_order_nos", _fake_evals),
    ]
    for mod, name, fn in targets:
        monkeypatch.setattr(mod, name, fn, raising=False)
        if hasattr(route, name):
            monkeypatch.setattr(route, name, fn, raising=False)
        for attr in vars(route).values():
            if getattr(attr, "__name__", None) in (_TRADE_DB_MOD, _EVAL_DB_MOD):
                if hasattr(attr, name):
                    monkeypatch.setattr(attr, name, fn, raising=False)

    # 🔴 **벽시계를 고정한다.** 라우트의 기본 창은 `[today-(days-1), today]` 이고
    # 아래 픽스처는 `sell_date="2026-09-15"` 라, 실제 오늘이 09-21 을 넘어가는
    # 순간부터 페어가 창 **밖**으로 밀려 `pairs` 가 빈 배열이 된다 — 테스트가
    # 어느 날 갑자기, 코드 변경 없이 붉어진다(2026-09-22 00:0x 실측으로 7건이
    # 그렇게 깨졌다). 이 저장소가 cycle295 에서 같은 계열로 **매일 30분간 CI 를
    # 붉게** 만든 적이 있다. 조회 창을 쓰는 테스트는 시각을 고정한다.
    # `freeze_today=False` 는 **창 경계 자체를 재는 테스트** 전용이다 — 그쪽은
    # freezegun 으로 자기 시각을 고정하므로 여기서 덮으면 그 고정이 무력화된다.
    if freeze_today:
        monkeypatch.setattr(route, "today_kst", lambda: _FROZEN_TODAY, raising=False)


#: 픽스처가 상정하는 「오늘」. `_pair()` 의 `sell_date`(2026-09-15)가 기본 창
#: `days=7` = `[today-6, today]` 안에 들도록 잡는다. 픽스처 날짜를 바꾸면 여기도 바꾼다.
_FROZEN_TODAY = date(2026, 9, 18)


def _pair(**over) -> dict:
    row = {
        "buy_date": "2026-09-11", "buy_time": "09:05:12",
        "sell_date": "2026-09-15", "sell_time": "10:31:02",
        "ticker": "005930", "ticker_name": "삼성전자",
        "buy_price": 80_000.0, "buy_qty": 10,
        "sell_price": 77_200.0, "sell_qty": 10,
        "profit_loss": -28_000.0, "profit_rate": -3.5,
        "status": "closed", "strategy": "donchian_swing",
        "buy_order_nos": ["0000123456"], "sell_order_nos": ["0000999999"],
        "pair_key": "donchian_swing:005930:0000123456",
    }
    row.update(over)
    return row


def _ev(**over) -> dict:
    """db 가 돌려주는 한 행 — asyncpg 실제 타입(`Decimal`)을 섞는다.

    ⚠️ 전부 `float` 로 만들어 두면 *의도한 계약*만 검증하고 *실제 직렬화*는 한 번도
    검증하지 않게 된다(cycle266 목 괴리 패턴).
    """
    row = {
        "trade_date": "2026-09-11",
        "order_no": "0000123456",
        "account_no": _ACCOUNT,          # ← 응답에 새면 안 되는 값
        "account_product": "01",
        "ticker": "005930",
        "strategy_id": "donchian_swing",
        "mode": "shadow",
        "result": "ok",
        "reason": None,
        "score": 42,
        "min_score": 70,
        "would_block": True,
        "rationale": "채널 상단 안착이 얕다",
        "prompt_version": "pv0000000001",
        "feature_version": "fv0000000001",
        "model": "gpt-5.6-luna",
        "cost_usd": Decimal("0.004380"),
        "k": Decimal("0.5"),
    }
    row.update(over)
    return row


def _body(resp) -> dict:
    payload = resp.json()
    assert payload.get("success") is True, payload
    return payload["data"]


# ===========================================================================
# G4-1 — 200 응답 형태
# ===========================================================================
def test_g4_1a_returns_window_costpct_pairs_aggregate_and_aliases(monkeypatch) -> None:
    """G4-1 — 최상위 키 5종 + `generated_at`.

    `window` 가 없으면 목요일 루틴이 "언제부터 언제까지의 표본인가" 를 응답만 보고 알 수
    없다 — `days` 를 되돌려 주는 것만으로는 휴장·주말 경계를 못 잰다.
    """
    _patch(monkeypatch, pairs=[_pair()], evals=[_ev()])
    data = _body(_client().get(_PATH, params={"days": 7}))

    for key in ("window", "cost_pct", "pairs", "aggregate",
                "prompt_version_aliases", "generated_at"):
        assert key in data, f"응답에 `{key}` 부재 — 실측 {sorted(data)}"
    assert set(data["window"]) >= {"since", "until", "days"}
    assert data["window"]["days"] == 7
    assert data["cost_pct"] == pytest.approx(0.25)
    assert len(data["pairs"]) == 1
    assert data["aggregate"]["overall"]["n_pairs"] == 1
    assert data["aggregate"]["overall"]["n_scored"] == 1


def test_g4_1b_default_days_is_seven(monkeypatch) -> None:
    """G4-1 — `days` 미지정 기본 7(주간 회고의 기본 창)."""
    _patch(monkeypatch, pairs=[], evals=[])
    assert _body(_client().get(_PATH))["window"]["days"] == 7


def test_g4_1c_prompt_version_aliases_is_present_for_the_one_time_break(monkeypatch) -> None:
    """G4-1 — `prompt_version_aliases` 가 **키로 존재**한다(값은 배포 후 Green 이 채운다).

    §3.4 의 1회성 단절(VB·LTV 의 X→Y) 때문에 목요일 루틴이 두 버전을 합산할 근거가
    필요하다. 키 자체가 없으면 루틴이 등가 관계를 알 방법이 없다.
    """
    _patch(monkeypatch, pairs=[], evals=[])
    aliases = _body(_client().get(_PATH))["prompt_version_aliases"]
    assert isinstance(aliases, (dict, list)), f"aliases 타입 {type(aliases)}"


# ===========================================================================
# G4-2 — 계좌번호는 어떤 경로로도 새지 않는다
# ===========================================================================
def test_g4_2_account_no_never_appears_in_the_serialized_body(monkeypatch) -> None:
    """G4-2 (M21) — 직렬화된 **본문 문자열**에 계좌번호도, `account_no` 키도 없다.

    파이썬 객체를 훑으면 중첩 dict 한 겹을 놓친다 — 원시 본문을 훑는 것이 유일하게
    빠짐없는 방법이다. **양성 대조군** = 같은 응답에 평가 행이 실제로 실려 있는지 함께
    잰다(응답이 통째로 비어 "계좌가 없다" 로 위장하지 못한다).
    """
    _patch(monkeypatch, pairs=[_pair()], evals=[_ev()])
    resp = _client().get(_PATH, params={"days": 7})
    raw = resp.text
    assert resp.status_code == 200
    assert _ACCOUNT not in raw, "응답 본문에 계좌번호 원문이 있다"
    assert '"account_no"' not in raw, "응답 본문에 `account_no` 키가 있다"
    # 양성 대조군 — 실을 것은 실었다.
    assert '"pv0000000001"' in raw and '"0000123456"' in raw


# ===========================================================================
# G4-3 — 범위 검증 422
# ===========================================================================
@pytest.mark.parametrize(
    "params",
    [
        {"days": 0},
        {"days": 91},
        {"days": -1},
        {"days": "abc"},
        {"cost_pct": -1},
        {"cost_pct": 5.1},
    ],
)
def test_g4_3a_out_of_range_query_is_422(monkeypatch, params) -> None:
    """G4-3 (M23) — 범위 밖은 **422**(조용한 클램프 금지).

    `days=91` 을 90 으로 깎아 200 을 주면 루틴은 3개월을 물었다고 믿고 1주치를 읽는다.
    """
    _patch(monkeypatch, pairs=[], evals=[])
    resp = _client().get(_PATH, params=params)
    assert resp.status_code == 422, f"{params} → {resp.status_code}"


@pytest.mark.parametrize("params", [{"days": 1}, {"days": 90}, {"cost_pct": 0}, {"cost_pct": 5}])
def test_g4_3b_boundary_values_are_accepted(monkeypatch, params) -> None:
    """G4-3 **양성 대조군** — 경계값은 200 이다.

    "전부 422" 로 만들어 위 테스트를 통과시키는 구현을 막는다.
    """
    _patch(monkeypatch, pairs=[], evals=[])
    resp = _client().get(_PATH, params=params)
    assert resp.status_code == 200, f"{params} → {resp.status_code} {resp.text[:200]}"


def test_g4_3c_strategy_filter_is_optional_and_narrows(monkeypatch) -> None:
    """G4-3 — `strategy` 는 선택이고 주면 그 전략만 남는다(R7 완화 수단)."""
    _patch(
        monkeypatch,
        pairs=[_pair(ticker="000001", strategy="donchian_swing", buy_order_nos=["A1"]),
               _pair(ticker="000002", strategy="kojiro", buy_order_nos=["A2"])],
        evals=[_ev(order_no="A1"), _ev(order_no="A2", strategy_id="kojiro")],
    )
    data = _body(_client().get(_PATH, params={"strategy": "kojiro"}))
    assert {p["strategy"] for p in data["pairs"]} == {"kojiro"}


# ===========================================================================
# G4-4 — 빈 결과 200 · DB 예외 500
# ===========================================================================
def test_g4_4a_no_pairs_is_200_with_empty_aggregate(monkeypatch) -> None:
    """G4-4 — 청산 0건은 **200 + 빈 집계**(404 아님).

    404 로 만들면 휴장 주간마다 목요일 루틴이 장애로 오인해 리포트가 붉어진다.
    """
    _patch(monkeypatch, pairs=[], evals=[])
    resp = _client().get(_PATH)
    assert resp.status_code == 200
    data = _body(resp)
    assert data["pairs"] == []
    assert data["aggregate"]["overall"]["n_pairs"] == 0


@pytest.mark.parametrize("which", ["pairs", "evals"])
def test_g4_4b_db_exception_is_500_with_marker(monkeypatch, caplog, which) -> None:
    """G4-4 — 두 DB 호출 **어느 쪽**이 터져도 500 + `[llm_eval_route_error]`.

    `except Exception: rows = []` 형태의 fail-silent 는 cycle266 이 3개월짜리 은폐로
    실증한 패턴이다 — 진짜 DB 장애가 "이번 주 청산 없음" 으로 위장된다.

    caplog 단언은 **WARNING 이상 + 마커 prefix** 로 한정한다(CI 루트 로거는 DEBUG 라
    실패 흔적 debug 행까지 잡힌다 — cycle252 T2).
    """
    kw = {"pairs_exc": RuntimeError("boom")} if which == "pairs" else {"evals_exc": RuntimeError("boom")}
    _patch(monkeypatch, pairs=[_pair()], evals=[_ev()], **kw)

    with caplog.at_level(logging.WARNING):
        resp = _client().get(_PATH)
    assert resp.status_code == 500, resp.text[:300]

    hits = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(_MARKER_ERROR)
    ]
    assert hits, f"`{_MARKER_ERROR}` WARNING 이상 로그가 없다"

    # 🔴 **거짓 초록 차단** — 라우트가 없으면 이 요청은 `/{order_no}` 에 먹혀
    # `get_by_order("retrospective")` 가 실 DB 를 찔러 500 + 같은 마커를 낸다.
    # 즉 "500 이고 마커가 있다" 만으로는 아무것도 증명되지 않는다. 회고 핸들러가 낸
    # 로그임을 가리는 discriminator = 상세 핸들러의 `order_no=` 문면이 **없을** 것.
    # (Green 은 회고 실패 로그에 `retrospective days=...` 형태를 남긴다.)
    assert any("order_no=" not in r.getMessage() for r in hits), (
        f"500 이 상세 핸들러(`/{{order_no}}`)에서 났다 — 회고 라우트가 아직 없거나 "
        f"등록 순서가 뒤집혔다. 로그={[r.getMessage() for r in hits]}"
    )
    assert any("retrospective" in r.getMessage() for r in hits), (
        f"회고 실패 로그에 경로 식별자가 없다 — 로그={[r.getMessage() for r in hits]}"
    )


# ===========================================================================
# G4-5 — `Decimal` → `float` 사영
# ===========================================================================
def test_g4_5_decimal_is_projected_to_float_in_the_json_body(monkeypatch) -> None:
    """G4-5 — 응답 JSON 에 `Decimal` 이 **문자열**로 나가지 않는다.

    pydantic v2 는 JSON 모드에서 `Decimal` 을 문자열로 직렬화한다 — 루틴의 산술과
    프론트의 `toFixed` 가 그대로 죽는다(cycle266 흰 화면). 파이썬 객체가 아니라
    **직렬화된 본문을 파싱한 결과**의 타입을 잰다.

    🔴 cycle297 검증 정정 — 종전 이 테스트는 `cost_usd`·`k` 에 `Decimal` 을 심고 그 두 키가
    문자열이 아님을 단언했다. 그런데 그 둘은 `llm_retrospective._EVAL_WHITELIST` 에 없어
    **라우트가 본 적도 없는 키**라, 단언이 존재하지 않는 값에 걸려 항상 통과했다(사영을
    통째로 지우는 뮤테이션도 초록). 화이트리스트 안의 수치 키(`score`·`min_score`)에 심고
    `evaluations` 와 `primary` **양쪽**을 잰다.
    """
    _patch(monkeypatch, pairs=[_pair()],
           evals=[_ev(score=Decimal("42"), min_score=Decimal("70"))])
    data = _body(_client().get(_PATH))
    row = data["pairs"][0]
    evs = row["evaluations"]
    assert evs, "평가가 실리지 않았다"
    targets = list(evs) + ([row["primary"]] if isinstance(row.get("primary"), dict) else [])
    assert len(targets) == 2, f"primary 가 사영되지 않았다 — {row.get('primary')!r}"
    for obj in targets:
        for key in ("score", "min_score"):
            value = obj.get(key)
            assert isinstance(value, (int, float)) and not isinstance(value, bool), (
                f"`{key}` 가 수치로 직렬화되지 않았다 — {value!r} ({type(value).__name__})"
            )
        assert float(obj["score"]) == 42.0 and float(obj["min_score"]) == 70.0


# ===========================================================================
# G4-6 — 라우팅: `/{order_no}` 가 `retrospective` 를 삼키지 않는다
# ===========================================================================
def test_g4_6a_retrospective_is_not_swallowed_by_the_order_no_route(monkeypatch) -> None:
    """G4-6 (M22) — 실제 라우터 매칭으로 잰다.

    `/{order_no}` 가 먼저 등록되면 `retrospective` 가 주문번호로 잡혀 404 다. AST 순서
    검사(G2-10)와 다른 실패 모드를 덮는다 — 예를 들어 두 라우트가 별도 `APIRouter` 에
    있고 `include_router` 순서가 뒤집힌 경우는 lineno 로는 못 잡는다.
    """
    _patch(monkeypatch, pairs=[], evals=[])
    resp = _client().get(_PATH)
    assert resp.status_code == 200, (
        f"{_PATH} → {resp.status_code} — `/{{order_no}}` 에 먹혔을 수 있다: {resp.text[:200]}"
    )


def test_g4_6b_existing_detail_route_still_works(monkeypatch) -> None:
    """G4-6 **양성 대조군** — 기존 단건 상세 경로가 살아 있다.

    새 경로를 앞에 끼워 넣다가 `/{order_no}` 를 망가뜨리면 거래기록 UI 의 "AI 자문"
    모달이 전부 죽는다(cycle276 계약).
    """
    route = _route()
    db = importlib.import_module(_EVAL_DB_MOD)

    async def _fake_get(order_no, **kw):
        return None

    monkeypatch.setattr(db, "get_by_order", _fake_get, raising=False)
    if hasattr(route, "get_by_order"):
        monkeypatch.setattr(route, "get_by_order", _fake_get, raising=False)

    resp = _client().get("/api/llm-evaluations/0000123456")
    assert resp.status_code == 404, f"단건 상세가 깨졌다 — {resp.status_code} {resp.text[:200]}"


# ===========================================================================
# G4-7 — 읽기 전용 (쓰기 0)
# ===========================================================================
def test_g4_7_route_module_has_no_write_path() -> None:
    """G4-7 — 라우트 모듈 소스에 쓰기 토큰이 없다.

    회고는 관측이다 — 관측이 상태를 바꾸면 그 숫자를 다음 주에 믿을 수 없다.
    """
    src = _ROUTE_SRC.read_text(encoding="utf-8")
    for token in ("pg.execute", "INSERT", "UPDATE ", "DELETE ", "upsert", ".post(", ".put("):
        assert token not in src, f"라우트에 쓰기 토큰 `{token}` 이 있다"

    tree = ast.parse(src)
    decorators = [
        d.func.attr
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        for d in n.decorator_list
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
        and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
    ]
    assert decorators, "라우터 데코레이터가 하나도 없다"
    assert set(decorators) <= {"get"}, f"GET 외 메서드가 있다 — {sorted(set(decorators))}"


# ===========================================================================
# G4-8 ~ G4-10 — 검증 후속(2026-09-17): 라우트가 **쿼리를 실제로 쓰는가**
# ===========================================================================
# 뮤테이션 렌즈가 두 건을 ESCAPED 로 잡았다 — ① `aggregate(rows, cost_pct=0.0)` 고정
# ② `since = until - days`(8일 창). 기존 22건이 전부 통과한 이유는 픽스처의
# `profit_rate` 가 −3.5 하나뿐이라 `cost_pct` 가 결과를 바꿀 표본이 없었고,
# `window.since` 값을 아무 테스트도 단언하지 않았기 때문이다.


@pytest.mark.parametrize(
    "cost_pct,expect_block_loss",
    [
        (0.0, 0),    # 비용 0 가정 → +0.10% 왕복은 이익
        (0.25, 1),   # 수수료·세금 근사 → 같은 왕복이 손실
    ],
)
def test_g4_8_cost_pct_query_actually_changes_the_aggregate(
    monkeypatch, cost_pct: float, expect_block_loss: int,
) -> None:
    """G4-8 — 쿼리 `cost_pct` 가 집계 판정을 실제로 바꾼다.

    라우트가 상수를 넘기면(뮤테이션 RT5) 두 호출의 결과가 같아 붉다. **양성 대조군** =
    같은 페어를 두 임계로 돌려 **둘이 달라야** 초록이다.
    """
    _patch(monkeypatch, pairs=[_pair(profit_rate=0.10, profit_loss=800.0)], evals=[_ev()])
    data = _body(_client().get(f"{_PATH}?cost_pct={cost_pct}"))
    assert data["cost_pct"] == pytest.approx(cost_pct)
    assert data["aggregate"]["overall"]["n_block_loss"] == expect_block_loss


def test_g4_9_row_outcome_matches_the_aggregate_loss_definition(monkeypatch) -> None:
    """G4-9 — 응답의 행 `outcome` 과 `aggregate` 가 **같은 손실 정의**를 쓴다.

    종전 leaf 는 행을 `profit_rate < 0` 으로, 집계를 `<= cost_pct` 로 판정해
    `0 < profit_rate <= cost_pct` 구간의 페어가 표에서는 `win`, 집계에서는 손실이었다.
    목요일 루틴이 표와 집계를 나란히 읽으면 숫자가 맞지 않는다.
    """
    _patch(monkeypatch, pairs=[_pair(profit_rate=0.10, profit_loss=800.0)], evals=[_ev()])
    data = _body(_client().get(f"{_PATH}?cost_pct=0.25"))
    row = data["pairs"][0]
    assert row["outcome"] == "loss", f"행 outcome={row['outcome']} (집계는 손실로 센다)"
    assert data["aggregate"]["overall"]["n_block_loss"] == 1


def test_g4_10_window_is_a_days_inclusive_range_ending_today(monkeypatch) -> None:
    """G4-10 — `window` 가 `[today-(days-1), today]` **포함 창**이다(= 정확히 `days` 일).

    주간 루틴이 매주 목요일에 도니 `days=7` 이 7일이어야 창이 겹치지 않는다.
    `today-days` 면 8일 창이 되어 매주 하루가 두 번 집계된다. 값을 직접 단언하지 않으면
    그 off-by-one 이 영원히 안 보인다(뮤테이션 RT1 ESCAPED).
    """
    freezegun = pytest.importorskip("freezegun")
    with freezegun.freeze_time("2026-09-17 10:00:00+09:00"):
        _patch(monkeypatch, pairs=[], evals=[], freeze_today=False)
        data = _body(_client().get(f"{_PATH}?days=7"))
    assert data["window"] == {"since": "2026-09-11", "until": "2026-09-17", "days": 7}


def test_g4_11_prompt_version_aliases_map_the_one_time_break(monkeypatch) -> None:
    """G4-11 — 등가표가 VB·LTV 의 배포 전→후 키를 담는다(§3.4).

    비어 있으면 목요일 루틴이 09-11~09-16 표본과 배포 후 표본을 합칠 근거가 없다.
    키·값 모두 `"<sid>|<pv>"` 형식이고 **같은 전략 안에서만** 맺어져야 한다 —
    전략을 가로지르는 등가는 서로 다른 잣대의 표본을 섞는다.
    """
    _patch(monkeypatch, pairs=[], evals=[])
    aliases = _body(_client().get(_PATH))["prompt_version_aliases"]
    assert isinstance(aliases, dict) and aliases, "등가표가 비었다"
    for src_key, dst_key in aliases.items():
        assert src_key.count("|") == 1 and dst_key.count("|") == 1, (src_key, dst_key)
        src_sid, src_pv = src_key.split("|")
        dst_sid, dst_pv = dst_key.split("|")
        assert src_sid == dst_sid, f"전략을 가로지르는 등가 — {src_key} → {dst_key}"
        assert src_pv != dst_pv, f"같은 버전끼리 맺혔다 — {src_key}"
        assert len(src_pv) == 12 and len(dst_pv) == 12
    # 값 축 — 배포 후 키는 현재 소스로 계산한 값과 일치해야 한다(표가 낡으면 붉다).
    from src.engine.llm_buy_gate import _prompt_version, reset_llm_buy_gate_state

    reset_llm_buy_gate_state()
    for dst_key in aliases.values():
        sid, pv = dst_key.split("|")
        assert _prompt_version(sid) == pv, (
            f"{sid}: 등가표의 배포 후 버전 {pv} != 현재 {_prompt_version(sid)} — "
            "프롬프트를 바꿨으면 `_PROMPT_VERSION_ALIASES` 도 함께 갱신하라"
        )
