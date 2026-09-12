"""cycle287 Red — SOR 축: **정직성 가드**.

정본 = cycle287 도메인 자문 §3 (2026-09-12).

## 🔴 브리프의 기본안을 자문이 뒤집었다 — 이 파일이 그 뒤집힘을 고정한다

브리프는 "`exchange` → `deprecated=True`, `editable=False`, choices 에서 SOR 제거"
를 기본안으로 제시했다. 자문 §3-A 가 그것을 **거부**했다:

> `deprecated=True` 는 "값이 바뀌어도 매매가 안 바뀐다" 는 선언이다. 여기서는 **거짓**이고,
> 관례가 금지하는 방향의 거짓말이다(무효라고 표시했는데 실은 유효).

cycle287 이후에도 `exchange` 는 **두 가지로 살아 있다**:

1. **W1·W4·W5·W7·W0 의 실제 거래소** — 프리장(08:00~09:00) 청산·매수가 NXT 로 나가는
   근거가 그 값이고, 15:40~16:00 의 **작동 중인** NXT 애프터 경로도 그 값이다.
2. **`stock_master` 프로브 게이트** — `_strategy_exchange_async` 의
   `if not ticker or base == "KRX": return base` 조기반환 때문에, base 가 `KRX` 가 되면
   `[nxt_downgrade]`·`[stock_master_miss]` 관측과 cycle286 학습이 **조용히 전멸**한다.

⇒ **운영 DB 를 `SOR → KRX` 로 마이그레이션하면 프리장 청산이 사라진다.** 자문의 종착지는
`NXT` 이고, 그것도 **cycle287b**(코드 배포 → D+1 판독 통과 → 카탈로그/프론트 → DB) 다.

## 이 사이클(287)에서 이 축이 하는 일 = 딱 셋

* **N1** — DB 에 `SOR` 이 남아 있어도 **KIS body 는 `KRX`** 임을 end-to-end 로 잰다(RED).
  이것이 "SOR 을 안 쓴다" 의 유일한 **행위** 증거다. 카탈로그·UI 는 표시일 뿐이다.
* **N2** — 🔴 **422 함정**. 백엔드에서 SOR 을 걷어내는 두 방식이 왜 `tradable_boards`
  편집까지 죽이는지를 **실제 검증기로 실증**하고, 자문 권고안(SOR 을 `deprecated=True`
  선택지로 **남긴다**)이 왜 유일하게 안전한지를 고정한다. 지금 초록이고, cycle287b 가
  이 파일을 보고 순서를 지켜야 한다.
* **N3/N4** — `param_catalog`·`market_state` 가 이 사이클에서 **무접촉**임을 의미 수준에서
  복창한다(byte 수준은 `test_cycle287_ast_scope.py::test_s1`/`test_s1b` 가 잰다).

## 왜 "SOR 부재" 를 RED 로 쓰지 않았는가

브리프 4항은 `param_catalog` choices 의 SOR **부재**와 `market_state` 응답의 SOR 열
**부재**를 요구했다. 둘 다 이 사이클에서 **써서는 안 되는 RED** 다:

* 자문 §3-C 가 choices 의 SOR 을 **남기라**고 결론했다(`_choice_values` 가
  `Choice.deprecated` 를 보지 않으므로 저장 어휘가 안 좁아져 §N2 함정이 **0** 이 된다).
* 자문 §3-C 가 `market_state` 의 SOR 열을 **남기라**고 결론했다 — 그 표는 "우리 라우팅"
  이 아니라 "KIS 가 무엇을 받는가" 의 사실 표이고, 열을 지우면 `41~47`·`27~29` 의
  `unknown`("확인 필요")을 만드는 **유일한 소스**가 사라져 **44 의 `ORD_UNPR` 이
  미확인이라는 사실을 화면에서 지운다**(cycle282 "미확인을 미지원으로 접지 않는다" 위반).
* 두 파일은 `test_cycle287_ast_scope.py::_BASE_SHA`/`_SRC_TREE_DIGEST` 로 **diff 0** 이다.

그래서 이 파일은 그 둘의 **현 상태를 잠그고**, 바꾸려는 다음 사이클이 여기를 지나가게 한다.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.order_engine import OrderEngine
from src.engine.session import boards_at
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

KST_TZ = timezone(timedelta(hours=9))
_TICKER = "004990"          # 롯데지주 — 09-12 실측 보유 11종목 중 하나
_SID = "kojiro"
_CUR = 24_800

# ── UTC 리터럴 ↔ KST (cycle286 헤더 규약: order_engine 은 tz-aware 판정) ───
_F_1100 = "2026-09-14 02:00:00"     # KST 11:00 (KRX 정규장)
_F_1605 = "2026-09-14 07:05:00"     # KST 16:05 (KRX 애프터마켓)
_F_0830 = "2026-09-13 23:30:00"     # KST 08:30 (NXT 프리마켓)

#: 09-12 실측 — 7 전략 **전부** 이 값이다.
_OPERATIONAL_EXCHANGE = "SOR"


class _DummyStrategy(StrategyBase):
    def __init__(self, **params) -> None:
        merged = {"exchange": _OPERATIONAL_EXCHANGE}
        merged.update(params)
        super().__init__(
            StrategyConfig(
                strategy_id=_SID, name="kojiro-dummy", enabled=True, weight=1.0,
                params=merged,
            )
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 1


def _make_engine(**params):
    reg = StrategyRegistry()
    strat = _DummyStrategy(**params)
    strat.state.positions[_TICKER] = Position(
        ticker=_TICKER, buy_price=24_800, quantity=5, order_no="ORDER-PRE",
        strategy_id=_SID, buy_date=date(2026, 9, 10),
    )
    reg.register(strat)
    return OrderEngine(reg), strat


@pytest.fixture(autouse=True)
def _rig(monkeypatch: pytest.MonkeyPatch):
    import src.db.stock_master as _sm
    import src.engine.order_engine as _oe
    from src.config import settings
    from src.engine import scanner

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: None)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    monkeypatch.setattr(scanner, "ticker_prices", {_TICKER: {"current_price": _CUR}})
    monkeypatch.setattr(settings, "kis_env", "real")

    async def _instant(_delay):
        return None

    monkeypatch.setattr(_oe.asyncio, "sleep", _instant)
    return None


def _pin_boards(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engine.session import session_tracker

    monkeypatch.setattr(
        session_tracker, "_active", boards_at(datetime.now(KST_TZ).time())
    )


@pytest.fixture
def kis_body(monkeypatch: pytest.MonkeyPatch) -> dict:
    """`place_order` 를 **모의하지 않고** KIS 전송 직전 body 를 가로챈다.

    `place_order` 를 AsyncMock 으로 바꾸면 "엔진이 무엇을 넘겼는가" 까지만 보이고
    `EXCG_ID_DVSN_CD` 가 실제로 실리는지는 안 보인다. 이 사이클의 최대 공허 위험이
    거기라서, 이 축만큼은 `kis_post` 층에서 잰다.
    """
    import src.api.order as _order

    captured: dict = {}

    async def _fake_post(url, tr_id, body, hashkey=None):
        captured.clear()
        captured.update(body)
        return {"output": {"ODNO": "ORD-1", "ORD_TMD": "160500",
                           "KRX_FWDG_ORD_ORGNO": ""}}

    monkeypatch.setattr(_order, "kis_post", _fake_post)
    monkeypatch.setattr(_order, "generate_hashkey", AsyncMock(return_value="hk"))
    return captured


# ===========================================================================
# N1 — DB 에 SOR 이 남아 있어도 **나가는 요청**은 KRX (행위 증거)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frozen, expected_excg, label",
    [
        (_F_1100, "KRX", "정규장 — 사용자 규칙 '정규장에서는 NXT 필요없어'"),
        (_F_1605, "KRX", "애프터 — 사용자 규칙 '나머지는 전부 KRX'"),
    ],
)
async def test_n1_db_sor_never_reaches_kis(
    monkeypatch: pytest.MonkeyPatch, kis_body: dict,
    frozen: str, expected_excg: str, label: str,
) -> None:
    """N1 (RED) — `strategy_config.params.exchange == "SOR"` 인데 **KIS body 는 KRX**.

    운영 DB 7 전략이 전부 `SOR` 이고 이 사이클은 그 값을 바꾸지 않는다(자문 §3 배포
    순서: 코드 → D+1 → 카탈로그/프론트 → DB). 따라서 "SOR 을 쓰지 않는다" 는 주장의
    유일한 **행위** 증거는 **나가는 요청**뿐이다 — 카탈로그·UI 는 표시일 뿐이고,
    내부 변수만 보는 테스트는 배관이 끊겨도 통과한다.

    D+1 판독도 같은 자리를 본다: `[kis_rejection]` body 로그의 `EXCG_ID_DVSN_CD`
    (자문 §7 층2-9 "코드가 아니라 나간 요청을 본다").
    """
    engine, strat = _make_engine()
    assert strat.config.params["exchange"] == "SOR", "리그 전제 — DB 값은 SOR 그대로"
    with freeze_time(frozen):
        _pin_boards(monkeypatch)
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert kis_body, "KIS 요청이 나가지 않았다"
    assert kis_body["EXCG_ID_DVSN_CD"] == expected_excg, (
        f"{label} — DB 의 `SOR` 이 그대로 KIS 로 갔다: {kis_body['EXCG_ID_DVSN_CD']!r}. "
        "운영자는 화면에서 SOR 을 보는데 주문도 SOR 로 나가면 라우팅이 배관에 안 닿은 것이다"
    )
    # DB 값은 **바뀌지 않는다** — 라우팅은 읽기 전용 판정이다.
    assert strat.config.params["exchange"] == "SOR", (
        "라우터가 전략 params 를 변이했다 — 판정은 순수해야 하고, DB 전환은 cycle287b 다"
    )


@pytest.mark.asyncio
async def test_n1b_pre_market_still_uses_the_db_value(
    monkeypatch: pytest.MonkeyPatch, kis_body: dict,
) -> None:
    """N1 (RED) — **프리장은 DB 값을 쓴다**(= `exchange` 는 죽은 입력란이 아니다).

    이 한 줄이 자문 §3-A 가 브리프 기본안(`deprecated=True`)을 거부한 근거다.
    08:00~09:00 청산·매수의 거래소는 여전히 이 파라미터가 정하고, 그 값을 `KRX` 로
    바꾸면 `_strategy_exchange_async` 의 `base == "KRX"` 조기반환 때문에
    **프리장 사전 지정가 변환 + `stock_master` 프로브가 함께 꺼진다**.
    """
    engine, _ = _make_engine()
    with freeze_time(_F_0830):
        _pin_boards(monkeypatch)
        await engine.execute_sell(_TICKER, Signal.STOP_LOSS, _SID)
    assert kis_body["EXCG_ID_DVSN_CD"] == "SOR", (
        "프리장이 KRX 로 라우팅됐다 — 매도 사전 지정가 변환이 죽고 NXT 프리 유동성을 "
        f"잃는다: {kis_body['EXCG_ID_DVSN_CD']!r}"
    )


# ===========================================================================
# N2 — 🔴 422 함정 (조사 8항 · 자문 §3-D)
# ===========================================================================
_SID_LTV = "long_tail_volatility"
#: 운영 실측(09-12) — 7 전략 전부 이 모양이다.
_CURRENT = {"exchange": "SOR", "tradable_boards": ["main", "pre_nxt"]}
#: `frontend/src/pages/Settings.tsx:439` 의 payload — **항상 둘 다** 보낸다.
_SETTINGS_PAYLOAD = {"exchange": "SOR", "tradable_boards": ["main"]}


def _validate(payload, *, current=None):
    from src.engine.param_validation import validate_params

    return validate_params(_SID_LTV, dict(current or _CURRENT), dict(payload))


def _route_save(payload, *, current=None) -> tuple[int, dict]:
    """`PUT /api/strategies/{id}/params` 의 판정을 그대로 재현한다.

    ⚠️ all-or-nothing 은 `validate_params` 가 아니라 **라우트**가 강제한다 —
    검증기는 `accepted` 를 채워서 돌려주고, 라우트가 `result.errors` 가 비지 않으면
    `raise HTTPException(422)` 로 그 `accepted` 를 **통째로 버린다**
    (`src/routes/strategies.py:313-322`). 검증기의 `accepted` 만 보면 "부분 저장이
    된다" 고 오독하게 되므로 여기서 라우트 층위를 명시한다.

    Returns:
        `(status_code, 실제로 저장되는 dict)`.
    """
    result = _validate(payload, current=current)
    if result.errors:
        return 422, {}
    return 200, dict(result.accepted)


def _patch_exchange_spec(monkeypatch: pytest.MonkeyPatch, **changes):
    """`param_catalog.get_spec("exchange")` 만 바꿔치기한다(파일은 diff 0)."""
    from src.engine import param_catalog as pc
    from src.engine import param_validation as pv

    real = pc.get_spec
    patched = dataclasses.replace(real("exchange"), **changes)

    def _fake(key: str):
        return patched if key == "exchange" else real(key)

    monkeypatch.setattr(pv.pc, "get_spec", _fake)
    return patched


def test_n2_current_catalog_accepts_the_settings_payload() -> None:
    """N2 — **현행**에서 "거래소·매매 보드" 카드 저장은 200 이다(기준선).

    이 사이클은 `param_catalog` 를 건드리지 않으므로 이 성질이 유지돼야 한다.
    깨지면 운영자가 장중에 `tradable_boards` 를 못 바꾼다 — 그건 매수 보드 게이트이자
    장중 유일한 실효 조정 수단이다(cycle232 D6: SQL UPDATE 는 다음 재시작에서만 반영).
    """
    assert _route_save(_SETTINGS_PAYLOAD) == (200, _SETTINGS_PAYLOAD)


@pytest.mark.parametrize(
    "label, changes, expected_code",
    [
        # 안 A — choices 에서 SOR 만 제거(editable 유지)
        ("A_choices_drop_sor", {"choices": None}, "not_in_choices"),
        # 안 B — 브리프 기본안(폐기 8키 관례)
        ("B_deprecated_not_editable",
         {"editable": False, "deprecated": True}, "not_editable"),
    ],
)
def test_n2b_naive_sor_removal_kills_tradable_boards_too(
    monkeypatch: pytest.MonkeyPatch, label: str, changes: dict, expected_code: str,
) -> None:
    """N2 — 🔴 SOR 을 **순진하게** 걷어내면 `tradable_boards` 편집까지 죽는다.

    `validate_params` 는 오류가 1건이라도 있으면 `accepted` 를 통째로 버리고 라우트가
    **422 + all-or-nothing** 이다(`src/routes/strategies.py:314-321`). 그리고 벡터는
    `frontend/src/pages/Settings.tsx:439` 한 줄 —

        mutation.mutate({ exchange, tradable_boards: boards })

    `exchange` 초기값이 저장값(= `SOR`)이라 **항상** 실린다. 즉 백엔드만 고치면
    7 전략 전부 그 카드의 저장 버튼이 죽고, 함께 죽는 것이 하필 장중 유일한 실효
    조정 수단인 `tradable_boards` 다.

    ⚠️ 안 B 는 `exchange: "KRX"` 로 보내도 422 다(`not_editable` 은 값과 무관) —
    브리프 기본안이 **가장 엄격한** 쪽이다.
    """
    from src.engine import param_catalog as pc

    if changes.get("choices", "x") is None:
        changes = {"choices": tuple(
            c for c in pc.get_spec("exchange").choices if c.value != "SOR"
        )}
    _patch_exchange_spec(monkeypatch, **changes)

    codes = {(e.key, e.code) for e in _validate(_SETTINGS_PAYLOAD).errors}
    assert ("exchange", expected_code) in codes, f"{label}: {codes}"

    status, saved = _route_save(_SETTINGS_PAYLOAD)
    assert status == 422, label
    assert saved == {}, (
        f"{label}: all-or-nothing 이 깨졌다 — {saved}. `tradable_boards` 가 "
        "`exchange` 오류에 끌려 함께 버려지는 것이 이 함정의 실체다"
    )
    # 같은 상태에서 `tradable_boards` **단독** payload 는 통과한다 —
    # 즉 결함은 카탈로그가 아니라 **프론트가 항상 둘 다 보내는 것**에 있다.
    assert _route_save({"tradable_boards": ["main"]}) == (200, {"tradable_boards": ["main"]})


def test_n2c_the_advisory_option_keeps_saving_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N2 — 자문 권고안(SOR 을 `deprecated=True` 선택지로 **남긴다**)은 422 가 **0** 이다.

    `param_validation._choice_values` 는 `[c.value for c in spec.choices]` 라
    **`Choice.deprecated` 를 보지 않는다** — 화면엔 회색 배지로 뜨면서 저장 어휘는
    안 좁아진다. 그래서 과거 값·비상 curl 롤백 경로가 함께 산다.

    ⇒ cycle287b 의 `param_catalog` 변경은 **이 모양**이어야 한다. 그리고 그때도
    `Settings.tsx` 를 **먼저** 고쳐 `exchange` 를 변경 시에만 payload 에 싣는 것이
    이중 방어다(`StrategyParamsEditor.tsx:271` 관례).
    """
    from src.engine import param_catalog as pc

    choices = tuple(
        dataclasses.replace(c, deprecated=True, label_ko="SOR (폐기 — cycle287)")
        if c.value == "SOR" else c
        for c in pc.get_spec("exchange").choices
    )
    _patch_exchange_spec(monkeypatch, choices=choices)

    assert _route_save(_SETTINGS_PAYLOAD) == (200, _SETTINGS_PAYLOAD)
    # 종착지(cycle287b DB 전환)인 `NXT` 도 저장 가능해야 한다.
    assert _route_save({"exchange": "NXT"}) == (200, {"exchange": "NXT"})


# ===========================================================================
# N3 — `param_catalog` 는 이 사이클에서 무접촉 (의미 수준 복창)
# ===========================================================================
def test_n3_exchange_is_not_marked_deprecated_in_this_cycle() -> None:
    """N3 — `exchange` 는 `deprecated=False` · `editable=True` 다(자문 §3-A·§3-C).

    브리프 기본안을 자문이 뒤집은 지점이다. cycle287 이후에도 이 파라미터는
    **프리장 거래소 + `stock_master` 프로브 게이트**로 살아 있으므로 "미사용" 배지는
    화면에 거짓말을 적는 것이다.

    cycle287b 가 바꾸는 것은 `deprecated` 플래그가 아니라 **`help` 문구**다 —
    "시각이 거래소를 정한다 / 이 값이 실제로 쓰이는 곳은 프리장·15:30~16:00·20:00 이후
    이고, `KRX` 로 두면 프리장 청산과 프로브가 함께 꺼진다".
    """
    from src.engine import param_catalog as pc

    spec = pc.get_spec("exchange")
    assert spec is not None
    assert spec.deprecated is False, (
        "`exchange` 가 폐기 표시됐다 — 프리장 거래소와 `stock_master` 프로브 게이트가 "
        "여전히 이 값을 쓴다(자문 §3-A). 무효 선언은 거짓말이다"
    )
    assert spec.editable is True, (
        "`editable=False` 는 `exchange` 를 보내는 모든 PUT 을 422 로 만든다 — "
        "`Settings.tsx:439` 가 항상 보낸다(N2b)"
    )
    assert "exchange" not in pc.deprecated_keys()


def test_n3b_sor_is_still_a_savable_choice() -> None:
    """N3 — `SOR` 은 여전히 **저장 가능한** 선택지다(자문 §3-C).

    운영 DB 7 전략이 전부 `SOR` 이고 이 사이클은 그 값을 바꾸지 않는다. 어휘를 먼저
    좁히면 N2b 의 422 가 그대로 터진다 — 배포 순서(코드 → D+1 → 카탈로그/프론트 → DB)가
    이 가드로 강제된다.
    """
    from src.engine import param_catalog as pc

    values = [c.value for c in pc.get_spec("exchange").choices]
    assert values == ["KRX", "NXT", "SOR"], values


# ===========================================================================
# N4 — `market_state` SOR 열 유지 + `unknown` 셀 생존 (자문 §3-C)
# ===========================================================================
def test_n4_market_state_keeps_the_sor_column() -> None:
    """N4 — `EXCHANGE_ORDER` 에서 SOR 을 **빼지 않는다**.

    그 표는 "우리가 어디로 주문하는가" 가 아니라 "KIS 가 그 호가유형을 그 거래소에서
    받는가" 의 사실 표다. SOR 은 KIS 에서 사라지지 않았고, 우리가 안 쓰기로 한 사실은
    열 삭제가 아니라 **각주**로 적는다(cycle287b).

    ⚠️ 열을 지우면 픽스처 동기 사슬(생성기 2 + 프론트/E2E 픽스처 4)과 cycle282
    `test_i1/i2/i3` 가 통째로 딸려 온다 — 이 사이클의 범위가 아니다.
    """
    from src.engine.market_state import EXCHANGE_ORDER

    assert tuple(EXCHANGE_ORDER) == ("KRX", "NXT", "SOR"), EXCHANGE_ORDER


def test_n4b_after_market_codes_still_report_unknown_for_sor() -> None:
    """N4 — `41~47` 의 SOR 지원 여부는 화면에서 **`unknown`("확인 필요")** 이어야 한다.

    SOR 열을 지우면 `unknown` 셀을 만드는 유일한 소스가 없어져, **44 의 `ORD_UNPR` 과
    SOR 애프터 지원이 미확인이라는 사실이 화면에서 통째로 사라진다**. 그건 cycle282 가
    명문화한 "미확인을 미지원으로 접지 않는다" 의 정반대이고, 하필 이 사이클의 최대
    미지(자문 §1-C·§1-E)를 지우는 방향이다.
    """
    from src.engine.market_state import ORDER_DIVISIONS

    by_code = {d.code: d for d in ORDER_DIVISIONS}
    for code in ("41", "44"):
        assert code in by_code, f"주문유형 `{code}` 가 표에 없다"
        assert "SOR" in set(by_code[code].exchanges_unknown), (
            f"`{code}` 의 SOR 지원 여부가 미확인(`unknown`)으로 남아 있지 않다 — "
            "모르는 것을 '미지원' 으로 접었다"
        )
        assert "SOR" not in set(by_code[code].exchanges)


# ===========================================================================
# N5 — 후속(cycle287b) 인계: 프론트 payload 벡터
# ===========================================================================
def test_n5_settings_payload_vector_is_documented_for_the_next_cycle() -> None:
    """N5 — `Settings.tsx` 가 `exchange` 를 **변경 시에만** payload 에 싣는다.

    적대 검증(2026-09-12) 시정 — 자문 §3-D 가 "`StrategyParamsEditor` 관례를
    따라 변경된 키만 전송" 을 명시했고, 프론트가 그 형태로 이미 구현됐다(N5 가
    원래 잠그려던 무조건 전송 벡터가 사라졌다). 이 가드는 그 결과를 봉인한다 —
    되돌리면 (a) 백엔드 `param_catalog` 가 SOR 선택지를 좁힐 때(cycle287b)
    422 위험이 생기고 (b) N2b(비상 `tradable_boards` 단독 편집)가 매번
    `exchange` 를 동반 전송해 저장을 오염시킬 수 있다.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    src = (root / "frontend/src/pages/Settings.tsx").read_text(encoding="utf-8")
    assert "if (exchange !== initialExchange) payload.exchange = exchange" in src, (
        "`Settings.tsx` 가 `exchange` 를 변경 시에만 payload 에 담는 다이어티 필드 "
        "관례를 잃었다 — 무조건 전송으로 되돌아가면 안 된다"
    )
    assert "mutation.mutate({ exchange, tradable_boards: boards })" not in src, (
        "무조건 `exchange` 를 담아 보내는 옛 벡터가 되살아났다"
    )
