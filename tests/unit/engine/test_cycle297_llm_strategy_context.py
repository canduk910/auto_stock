"""cycle297 Red — G1: 전략별 LLM 컨텍스트 · 「해당 없음」 분리 · 손절/청산 배선 · 전략별 prompt_version.

명세 = `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` §3.1 · §3.2 · §3.3 · §3.4 · §5.1 G1.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 파일이 지키는 네 가지

1. **7전략 전부가 자기 잣대로 채점된다.** 지금 `_STRATEGY_META` 에는 VB·LTV 둘뿐이고
   `build_messages` 는 나머지를 `{"name": sid, "entry_rule": "", "matters": ""}` 로 폴백한다
   — donchian(20일 신고가 스윙)·kojiro(이평 대순환)를 **빈 컨텍스트**로 채점하면 그 데이터의
   적중률은 전략 특성이 아니라 **잣대 오류**를 잰다. 5전략에 shadow 를 켜기 전에 닫아야 하는
   선결 조건이다(명세 §1.2 F5).
2. **결측(`null`)과 「해당 없음」은 다르다.** `target_won`/`k`/`breakout_excess_bp` 는
   momentum·donchian·VCP·kojiro 의 `buy_signals` 에 애초에 없는 개념이라 지금은 **영구 null** 이
   실린다. SYSTEM_PROMPT 의 "결측 필드가 3개 이상이면 score 는 50 을 넘기지 않는다" 가
   구조적으로 발동해 `would_block=True` 가 상시가 된다(F7). 없는 개념은 **키 자체를 뺀다**.
3. **손절폭 0.0 은 거짓말이다.** `_read_stop_loss_pct` 가 VB·LTV 외에 `0.0` 을 돌려주므로
   판단 기준 4("`stop_loss_pct` 절대값이 `atr14_pct` 보다 작으면 낮게 매긴다")에 **항상** 걸린다(F6).
4. **VB·LTV 의 user payload 는 한 글자도 바뀌지 않는다.** 5전략 확대가 기존 두 전략의
   프롬프트를 건드리면 09-11~09-16 표본과의 연속성이 사라진다. G1-6 이 byte 단위로 잰다.

## 양성 대조군 (cycle292 교훈 — 부정 단언만 있으면 코드가 사라져도 초록이다)

- G1-1/G1-3 : META 가 **7건 전부 있고 폴백이 도달 불가**함을 잰다(있어야 할 것의 존재).
- G1-5      : NA 키가 "빠졌는지" 만 보지 않고, 남은 키가 `_SNAPSHOT_KEYS` 순서 그대로임도 잰다.
- G1-6      : "안 바뀐다" 의 짝으로 **sha 가 실제로 계산 가능**(메시지가 비어 있지 않음)함을 함께 잰다.
- G1-8      : "0.0 이 아니다" 의 짝으로 각 전략의 **실제 기대값**을 직접 대조한다.
- G1-10     : "달라진다" 의 짝으로 같은 sid 두 번 호출이 **같은 값**(캐시 정상)임을 잰다.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

_FEATURES_MOD = "src.engine.llm_features"
_GATE_MOD = "src.engine.llm_buy_gate"

_VB = "volatility_breakout"
_LTV = "long_tail_volatility"
_VBLTV = (_VB, _LTV)

#: 목표가(돌파선) 개념이 없는 전략의 스냅샷 키 — 결측이 아니라 **해당 없음**(명세 §3.2).
_NA_TARGET_KEYS = ("target_won", "k", "breakout_excess_bp")

#: 멀티데이 4전략 — "당일 15:20 청산" 전제가 **없다**.
#: 명세 §5.3 M3 은 3전략(donchian·VCP·kojiro)을 들지만 BFB 도 `max_hold_days=5` 의
#: 영업일 시간 청산이라 15:20 규약이 없다(`strategies/CLAUDE.md:157`). 넷 다 막는 쪽이
#: 좁고 정확하다 — VB 잣대 오염을 막는 것이 이 단언의 목적이기 때문이다.
_MULTIDAY = ("donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro")


def _lf():
    """`llm_features` — 부재/미구현이면 그대로 터진다(skip 금지 = 정직한 Red)."""
    return importlib.import_module(_FEATURES_MOD)


def _gate():
    return importlib.import_module(_GATE_MOD)


def _strategy_ids() -> tuple[str, ...]:
    from src.engine.param_catalog import STRATEGY_IDS

    return tuple(STRATEGY_IDS)


# ---------------------------------------------------------------------------
# payload 픽스처 — **생산자(`llm_buy_gate.observe_order`)의 키 집합**과 맞춘다.
# 손으로 쓴 픽스처가 생산자와 어긋나면 그 괴리가 결함을 통째로 가린다(cycle274 파인딩 #1).
# ---------------------------------------------------------------------------
def _payload(sid: str = _VB, *, name: str = "삼성전자") -> dict:
    return {
        "strategy": sid,
        "strategy_id": sid,
        "ticker": "005930",
        "name": name,
        "board": "main",
        "order_kst": "2026-09-11T09:04:42+09:00",
        "mins_from_krx_open": 4,
        "order_price_won": 80500,
        "board_open_won": 80000,
        "target_won": 80500,
        "k": 0.5,
        "breakout_excess_bp": 0.0,
        "prdy_close_won": 70000,
        "prdy_ctrt_pct": 15.0,
        "intraday_ctrt_pct": 0.625,
        "acml_vol_shares": 1_000_000,
        "vol_ratio_vs_avg20": 1.25,
        "vol_ratio_time_norm": 2.5,
        "order_division": "01",
        "order_path": "primary",
        "exchange": "KRX",
        "stop_loss_pct": -3.0,
        "budget_won": 247_949,
        "position_ratio": 0.10,
        "market_cap_eok": 5_000_000,
        "trade_amount_eok": 3_000,
        "exit_rule": "손절 -3.0%. 익절·트레일링 없음. 당일 15:20 전량 시장가 청산(오버나잇 없음).",
        # 운영 설정값 — snapshot 화이트리스트가 이것들을 **빼는지**가 계약이다.
        # `now_kst` 는 raw datetime(생산자가 실제로 넣는 그대로, JSON 직렬화 불가).
        "min_score": 70,
        "daily_cap": 20,
        "timeout_s": 20,
        "model": "gpt-5.6-luna",
        "mode": "shadow",
        "now_kst": datetime(2026, 9, 11, 9, 4, 42, tzinfo=KST),
    }


_TECH = {"rsi14": 55.0, "atr14_pct": 2.5, "pos_in_ch20_pct": 88.0}


def _bar(i: int) -> dict:
    return {
        "stck_bsop_date": f"2026080{i % 9 + 1}",
        "stck_oprc": "1000",
        "stck_hgpr": "1010",
        "stck_lwpr": "990",
        "stck_clpr": "1000",
        "acml_vol": "10000",
    }


_BARS30 = [_bar(i) for i in range(30)]


def _user_obj(sid: str) -> dict:
    content = _lf().build_messages(_payload(sid), _TECH, _BARS30)[1]["content"]
    return json.loads(content[content.index("{"):])


# ===========================================================================
# G1-1 / G1-2 / G1-3 — `_STRATEGY_META` 7건 + 폴백 도달 불가
# ===========================================================================
def test_g1_1_strategy_meta_covers_exactly_the_seven_registered_strategies() -> None:
    """G1-1 — META 키 집합 ≡ `param_catalog.STRATEGY_IDS`(7, 순서 무관).

    **양성 대조군** = 7개가 실제로 있어야 초록이다(하나만 빠져도 붉다, M1).
    부분집합/상위집합 어느 방향의 드리프트도 잡는다 — 등록되지 않은 전략의 META 가
    남아 있으면 그 문구가 누구의 잣대인지 아무도 모른다.
    """
    meta = _lf()._STRATEGY_META
    assert set(meta) == set(_strategy_ids()), (
        f"`_STRATEGY_META` 키 {sorted(meta)} != STRATEGY_IDS {sorted(_strategy_ids())}"
    )


@pytest.mark.parametrize("sid", _strategy_ids())
def test_g1_2_each_meta_has_three_nonempty_fields_and_no_exit_rule(sid: str) -> None:
    """G1-2 — `name`·`entry_rule`·`matters` 가 공백 제거 후 20자 이상이고 `exit_rule` 키는 **없다**.

    `exit_rule` 을 META 에 두면 하드코딩된 청산 규약이 라이브 params 를 덮는다 —
    호출자가 `payload["exit_rule"]` 로 실어 보내는 것이 유일한 출처다(cycle274 test_f3_10).
    길이 20 은 "빈 문자열이 아니다" 보다 강한 양성 대조군이다(M2: `matters=""`).
    """
    m = _lf()._STRATEGY_META[sid]
    for field in ("name", "entry_rule", "matters"):
        assert field in m, f"{sid}: `{field}` 키 부재"
        text = str(m[field]).strip()
        assert len(text) >= 20 or field == "name", f"{sid}.{field} 가 너무 짧다: {text!r}"
        assert text, f"{sid}.{field} 가 비었다"
    assert "exit_rule" not in m, (
        f"{sid}: META 에 `exit_rule` 이 있다 — 청산 규약은 호출자가 라이브 params 로 만든다"
    )


@pytest.mark.parametrize("sid", _strategy_ids())
def test_g1_3_build_messages_fallback_is_unreachable_for_every_strategy(sid: str) -> None:
    """G1-3 — 7전략 전수에 대해 `strategy` 블록이 **빈 컨텍스트가 아니다**.

    `_STRATEGY_META.get(sid, {...})` 폴백 리터럴은 남아도 되지만, 등록된 전략이 그 길로
    떨어지면 안 된다. `build_messages` 를 실제로 태워 재므로 META 를 고치고 렌더를 안 고친
    경우(또는 그 반대)도 잡힌다 — dict 만 읽는 단언으로는 못 잡는 축이다.
    """
    block = _user_obj(sid)["strategy"]
    assert block["id"] == sid
    assert block["entry_rule"].strip(), f"{sid}: entry_rule 이 비었다(폴백 도달)"
    assert block["matters"].strip(), f"{sid}: matters 가 비었다(폴백 도달)"
    assert block["name"].strip() != sid, (
        f"{sid}: name 이 전략 id 그대로다 — 폴백(`{{'name': str(sid)}}`)에 떨어졌다"
    )


# ===========================================================================
# G1-4 — 수치 토큰 대조 (문구가 문서의 규칙과 일치하는가)
# ===========================================================================
#: (필수 토큰, 후보 토큰) — 필수는 전부, 후보는 **3개 이상** 포함되어야 한다.
#: 출처 = 명세 §3.1 표(각 전략 파일 docstring + `strategies/CLAUDE.md:150-159`).
#: 이 토큰들은 Green 이 맞춰야 할 **계약**이다 — 수치를 문서와 다르게 쓰면 붉어진다.
_NUMERIC_TOKENS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "momentum": (("29", "15:20"), ("29", "30", "15:20", "7.5", "10", "익일")),
    "volatility_breakout": (("15:20",), ("15:20", "K", "돌파", "시가")),
    "long_tail_volatility": (("상한가",), ("상한가", "5%", "꼬리", "돌파")),
    "donchian_swing": (("20일", "60"), ("20일", "60", "1.5", "ATR", "영업일", "9")),
    "bull_flag_breakout": (("15%", "50%"), ("15%", "50%", "60%", "2", "5", "영업일")),
    "vcp_breakout": (("120", "30%"), ("50", "60", "120", "30%", "12%", "70%", "1.5", "7")),
    "kojiro": (("EMA", "40"), ("5", "20", "40", "6", "1.0", "6.0", "8", "2.5")),
}


@pytest.mark.parametrize("sid", sorted(_NUMERIC_TOKENS))
def test_g1_4_meta_text_cites_the_documented_numbers(sid: str) -> None:
    """G1-4 — `entry_rule + matters` 가 문서의 수치를 실제로 인용한다.

    문구만 길고 수치가 없으면 모델이 "왜 지금 사는가" 를 못 읽는다. 필수 토큰은 그
    전략을 다른 전략과 가르는 값이고(M3: donchian 에 VB 잣대를 넣으면 `20일`·`60` 이 사라진다),
    후보 3개 이상은 "한 수치만 넣고 때운" 문구를 거른다.
    """
    m = _lf()._STRATEGY_META[sid]
    text = f"{m.get('entry_rule', '')} {m.get('matters', '')}"
    required, candidates = _NUMERIC_TOKENS[sid]
    missing = [t for t in required if t not in text]
    assert not missing, f"{sid}: 필수 수치 토큰 {missing} 부재 — 실제 문구={text!r}"
    hits = [t for t in candidates if t in text]
    assert len(hits) >= 3, f"{sid}: 후보 토큰 {len(hits)}개(3개 이상 필요) — 적중={hits}"


@pytest.mark.parametrize("sid", _MULTIDAY)
def test_g1_4b_multiday_meta_never_claims_same_day_liquidation(sid: str) -> None:
    """G1-4b (M3 보강) — 멀티데이 전략 문구에 `15:20`·`당일 청산` 이 **없다**.

    VB 의 "이익이 자랄 시간이 개장~15:20 뿐이다" 를 복사해 넣으면 5~15영업일 보유 전략을
    데이트레이딩 잣대로 채점한다 — 그 표본은 전략이 아니라 잣대를 잰다(명세 §1.2 F5).
    **부정 단언이지만 짝(G1-4)이 양성 대조군**이라 문구가 통째로 비어도 초록이 되지 않는다.
    """
    m = _lf()._STRATEGY_META[sid]
    text = f"{m.get('entry_rule', '')} {m.get('matters', '')}"
    for banned in ("15:20", "당일 청산", "당일청산"):
        assert banned not in text, f"{sid}: 멀티데이 전략 문구에 `{banned}` 가 있다 — VB 잣대 오염"


# ===========================================================================
# G1-5 — `_SNAPSHOT_NA_KEYS` / `snapshot_keys_for` (결측 ≠ 해당 없음)
# ===========================================================================
def test_g1_5a_snapshot_keys_for_vb_and_ltv_is_the_full_tuple() -> None:
    """G1-5 — VB·LTV 는 `_SNAPSHOT_KEYS` **그대로**(순서까지).

    두 전략의 payload byte 동일(G1-6)의 전제다. NA 목록에 실수로 들어가면 여기서 먼저 붉다.
    """
    lf = _lf()
    for sid in _VBLTV:
        assert lf.snapshot_keys_for(sid) == tuple(lf._SNAPSHOT_KEYS), (
            f"{sid}: snapshot 키가 `_SNAPSHOT_KEYS` 와 다르다"
        )


@pytest.mark.parametrize(
    "sid,na",
    [
        # 🔴 cycle297 검증 정정 — 종전 표는 donchian·VCP 를 `_NA_TARGET_KEYS` 로 두었다.
        # 그 분류는 사실과 달랐다: 두 전략은 돌파선을 `buy_signals` 에 이미 싣는다
        # (`donchian_swing.py` `"donchian_high"` · `vcp_breakout.py` `"base_high"`).
        # 같은 프롬프트의 `entry_rule` 이 "기준가 대비 +4% 초과 추격 금지"(donchian)·
        # "돌파선 대비 +7.5%"(VCP)라고 말하면서 `not_applicable` 은 "목표가 개념이 없다"
        # 고 말해 모델에 모순된 두 문장을 먹였다. `_BREAKOUT_LINE_KEYS`(G1-5c)가 그 값을
        # 실제로 읽으므로 이제 `k` 만 「해당 없음」이다.
        ("momentum", _NA_TARGET_KEYS),
        ("kojiro", _NA_TARGET_KEYS),
        ("donchian_swing", ("k",)),
        ("vcp_breakout", ("k",)),
        # BFB 의 `target_price` 는 돌파선이 아니라 **측정 이동 목표가**(`flag_high` + 폴
        # 높이)다 — 돌파선은 `flag_high` 다. `_BREAKOUT_LINE_KEYS` 가 그것을 읽는다.
        ("bull_flag_breakout", ("k",)),
    ],
)
def test_g1_5b_na_keys_are_absent_not_null(sid: str, na: tuple[str, ...]) -> None:
    """G1-5 — 「해당 없음」 키는 **키 자체가 없다**(`None` 으로 채우면 안 된다).

    `snapshot.get("k") is None` 은 M5(빼는 대신 None 채우기)를 통과시킨다 — `not in` 으로만
    잰다. **양성 대조군** = 나머지 키가 `_SNAPSHOT_KEYS` 순서 그대로 전부 남아 있음을 함께 잰다
    (M4: NA 목록을 비우면 남는 키가 늘어 붉고, NA 목록을 부풀리면 줄어 붉다).
    """
    lf = _lf()
    keys = lf.snapshot_keys_for(sid)
    expected = tuple(k for k in lf._SNAPSHOT_KEYS if k not in set(na))
    assert keys == expected, f"{sid}: snapshot 키 {keys} != 기대 {expected}"

    snapshot = _user_obj(sid)["snapshot"]
    for key in na:
        assert key not in snapshot, (
            f"{sid}: snapshot 에 `{key}` 키가 남아 있다 — 해당 없음은 키를 뺀다(null 금지)"
        )
    # 양성 대조군 — 빼야 할 것만 빠졌다.
    for key in expected:
        assert key in snapshot, f"{sid}: snapshot 에서 `{key}` 가 사라졌다(과잉 제거)"


# ===========================================================================
# G1-6 — VB·LTV user payload **byte 동일** (착수 시점 sha 핀)
# ===========================================================================
#: cycle297 착수 시점(HEAD `a4580b6`) `build_messages(_payload(sid), _TECH, _BARS30)[1]["content"]`
#: 의 sha256 앞 16자. 🔴 **이 값을 갱신하지 마라** — 갱신해야 할 것 같으면 VB·LTV 프롬프트를
#: 바꾼 것이고, 그건 이 사이클의 범위 밖이다(09-11~09-16 표본과의 연속성이 끊긴다).
# ⚠️ 이름에 `_CONTENT_SHA` 를 쓰지 않는다 — `test_cycle223g3::_discover_pin_guard_files`
# 가 그 토큰으로 **8영역 한시 승인 핀**을 찾는다. 이 핀은 8영역과 무관한
# 프롬프트 byte 불변 증거이므로 그 목록에 섞이면 8영역 변경마다 여기에도
# 한시 등록을 요구하게 된다(2026-09-17 실측: `src/auth/CLAUDE.md` 변경에서 발화).
_VBLTV_USER_PROMPT_SHA: dict[str, str] = {
    "volatility_breakout": "cb6f843cdb1d1d9e",
    "long_tail_volatility": "b095a46c416ba13e",
}


@pytest.mark.parametrize("sid", sorted(_VBLTV_USER_PROMPT_SHA))
def test_g1_6_vb_ltv_user_payload_is_byte_identical(sid: str) -> None:
    """G1-6 — 5전략 확대가 VB·LTV 프롬프트를 **한 글자도** 바꾸지 않았다는 기계 증거.

    `_SNAPSHOT_KEYS` 추가(M25)·VB 에 `not_applicable` 삽입(M6)·SYSTEM_PROMPT 재작문이
    전부 여기서 붉어진다. **양성 대조군** = 내용이 비어 있지 않고 JSON 으로 파싱되는지도 함께
    잰다(빈 문자열이 우연히 같은 sha 를 낼 수는 없지만, 렌더가 통째로 죽어도 "sha 가 같다"
    로 위장되는 경로를 원천 차단한다).
    """
    content = _lf().build_messages(_payload(sid), _TECH, _BARS30)[1]["content"]
    assert len(content) > 500, f"{sid}: user 메시지가 비정상적으로 짧다({len(content)}자)"
    obj = json.loads(content[content.index("{"):])
    assert obj["strategy"]["id"] == sid and obj["snapshot"], f"{sid}: 렌더 결과가 비정상"

    got = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    assert got == _VBLTV_USER_PROMPT_SHA[sid], (
        f"{sid}: user payload 가 바뀌었다 — cycle297 은 VB·LTV 프롬프트를 건드리지 않는다. "
        f"🔴 핀을 갱신하지 말고 코드를 되돌려라. 현재 sha={got}"
    )


# ===========================================================================
# G1-7 — `not_applicable` 문구는 5전략에만
# ===========================================================================
@pytest.mark.parametrize("sid", ["momentum", "donchian_swing", "bull_flag_breakout",
                                 "vcp_breakout", "kojiro"])
def test_g1_7a_five_strategies_get_not_applicable_note(sid: str) -> None:
    """G1-7 — 5전략의 `strategy` 블록에 「해당 없음」 설명이 실린다.

    키를 빼기만 하면 모델은 "입력이 짧다" 로 읽고 여전히 낮게 매긴다 — **왜** 없는지를
    말해 줘야 판단 기준 1(돌파의 질)을 다른 축으로 대신 본다(명세 §3.2).
    """
    block = _user_obj(sid)["strategy"]
    assert "not_applicable" in block, f"{sid}: `not_applicable` 문구 부재"
    text = str(block["not_applicable"]).strip()
    assert len(text) >= 20, f"{sid}: `not_applicable` 문구가 너무 짧다: {text!r}"


@pytest.mark.parametrize("sid", _VBLTV)
def test_g1_7b_vb_ltv_never_get_not_applicable_note(sid: str) -> None:
    """G1-7 — VB·LTV 블록에는 그 키가 **없다**(byte 동일의 직접 귀결, M6)."""
    assert "not_applicable" not in _user_obj(sid)["strategy"], (
        f"{sid}: VB·LTV 에 `not_applicable` 이 새로 들어갔다 — payload 가 바뀐다"
    )


# ===========================================================================
# G1-8 — 손절·청산 규약 배선 (`_read_stop_loss_pct` / `_read_exit_rule`)
# ===========================================================================
def _default_params(sid: str) -> dict:
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    table = {
        "momentum": MomentumStrategy,
        "volatility_breakout": VolatilityBreakoutStrategy,
        "long_tail_volatility": LongTailVolatilityStrategy,
        "donchian_swing": DonchianSwingStrategy,
        "bull_flag_breakout": BullFlagBreakoutStrategy,
        "vcp_breakout": VcpBreakoutStrategy,
        "kojiro": KojiroStrategy,
    }
    return dict(table[sid].DEFAULT_PARAMS)


#: `DEFAULT_PARAMS` 기준 관측 시점 손절폭(명세 §3.3 표). ATR 재해석 **전** 값이다.
_EXPECTED_STOP_PCT: dict[str, float] = {
    "momentum": -7.5,            # stop_loss_rate
    "volatility_breakout": -3.0,  # stop_loss_rate (기존 계약, 회귀 확인용)
    "long_tail_volatility": -3.0,  # intraday_stop_loss (기존 계약)
    "donchian_swing": -7.0,      # stop_loss_rate
    "bull_flag_breakout": -5.0,  # stop_loss_rate
    "vcp_breakout": -7.0,        # stop_loss_rate
    "kojiro": -8.0,              # hard_stop_pct
}


@pytest.mark.parametrize("sid", sorted(_EXPECTED_STOP_PCT))
def test_g1_8a_read_stop_loss_pct_is_never_zero(sid: str) -> None:
    """G1-8 — 7전략 전부 `< 0` 이고 **문서의 실제 값**과 같다.

    "0.0 이 아니다" 만 재면 `-0.01` 같은 위장을 통과시킨다 — 기대값 직접 대조가 양성
    대조군이다(M8: kojiro 에 0.0). 0.0 이면 SYSTEM_PROMPT 판단 기준 4 가 **항상** 발동해
    그 전략의 모든 점수가 구조적으로 깎인다(명세 §1.2 F6).
    """
    got = _gate()._read_stop_loss_pct(sid, _default_params(sid))
    assert got < 0.0, f"{sid}: stop_loss_pct={got} (0.0 은 거짓말이다)"
    assert got == pytest.approx(_EXPECTED_STOP_PCT[sid]), (
        f"{sid}: stop_loss_pct={got}, 기대 {_EXPECTED_STOP_PCT[sid]}"
    )


#: `exit_rule` 문구가 인용해야 할 값(라이브 params 에서 읽은 것이어야 한다).
_EXIT_RULE_TOKENS: dict[str, tuple[str, ...]] = {
    "momentum": ("7.5", "10", "2"),
    "volatility_breakout": ("15:20",),
    "long_tail_volatility": ("상한가",),
    "donchian_swing": ("9", "2", "10"),
    "bull_flag_breakout": ("5", "2"),
    "vcp_breakout": ("7", "2"),
    "kojiro": ("8", "2", "2.5"),
}


@pytest.mark.parametrize("sid", sorted(_EXIT_RULE_TOKENS))
def test_g1_8b_read_exit_rule_is_nonempty_and_quotes_live_params(sid: str) -> None:
    """G1-8 — 7전략 전부 비공백이고 라이브 params 값을 인용한다(M7: donchian 분기 삭제).

    **하드코딩 탐지** = 값을 바꿔 넣으면 문구도 바뀌어야 한다. 아래에서 `stop` 계열 키를
    눈에 띄는 값으로 바꾸고 문구가 따라 변하는지 확인한다.
    """
    gate = _gate()
    params = _default_params(sid)
    text = gate._read_exit_rule(sid, params)
    assert isinstance(text, str) and text.strip(), f"{sid}: exit_rule 이 비었다"
    hits = [t for t in _EXIT_RULE_TOKENS[sid] if t in text]
    assert hits, f"{sid}: exit_rule 이 params 값을 하나도 인용하지 않는다 — {text!r}"


@pytest.mark.parametrize(
    "sid,key,value",
    [
        ("momentum", "stop_loss_rate", -11.25),
        ("donchian_swing", "turtle_backstop_pct", -11.25),
        ("bull_flag_breakout", "stop_loss_rate", -11.25),
        ("vcp_breakout", "stop_loss_rate", -11.25),
        ("kojiro", "hard_stop_pct", -11.25),
    ],
)
def test_g1_8c_exit_rule_follows_live_param_override(sid: str, key: str, value: float) -> None:
    """G1-8 — `exit_rule` 이 **하드코딩 문자열이 아니다**.

    DB 오버라이드(`params_snapshot = dict(strategy.config.params)`)가 반영되지 않으면
    프롬프트가 실제 청산 규약과 다른 값을 말한다 — 모델이 "손절폭 vs 잡음" 을 틀린
    수치로 판단한다. `-11.25` 는 어떤 기본값과도 겹치지 않는 표식이다.
    """
    params = _default_params(sid)
    params[key] = value
    text = _gate()._read_exit_rule(sid, params)
    assert "11.25" in text, f"{sid}: `{key}={value}` 오버라이드가 exit_rule 에 반영되지 않았다 — {text!r}"


# ===========================================================================
# G1-9 — `_resolve_stop_loss_pct` (ATR 손절 전략 재해석, 명세 §3.3)
# ===========================================================================
_TURTLE_D = {
    "sizing_mode": "turtle", "stop_atr": 2.0,
    "turtle_backstop_pct": -9.0, "stop_loss_rate": -7.0,
}
_TURTLE_BFB = {
    "sizing_mode": "turtle", "stop_atr": 2.0,
    "turtle_backstop_pct": -7.0, "turtle_min_stop_pct": -4.0, "stop_loss_rate": -5.0,
}
_TURTLE_VCP = {
    "sizing_mode": "turtle", "stop_atr": 2.0,
    "turtle_backstop_pct": -9.0, "turtle_min_stop_pct": -5.0, "stop_loss_rate": -7.0,
}
_KOJIRO = {"sizing_mode": "position_ratio", "stop_atr": 2.0, "hard_stop_pct": -8.0}


@pytest.mark.parametrize(
    "sid,params,atr14_pct,expected",
    [
        # donchian — `max(-(stop_atr×atr), backstop)` = 타이트한 쪽
        ("donchian_swing", _TURTLE_D, 3.0, -6.0),
        ("donchian_swing", _TURTLE_D, 6.0, -9.0),   # 2×6=12 → backstop -9 가 상한
        ("donchian_swing", _TURTLE_D, None, -7.0),  # ATR 결측 → 고정% (0.0 위장 금지)
        # BFB — `clamp(-(stop_atr×atr), backstop, min_stop)` = [-7.0, -4.0]
        ("bull_flag_breakout", _TURTLE_BFB, 1.0, -4.0),
        ("bull_flag_breakout", _TURTLE_BFB, 3.0, -6.0),
        ("bull_flag_breakout", _TURTLE_BFB, 5.0, -7.0),
        # VCP — [-9.0, -5.0]
        ("vcp_breakout", _TURTLE_VCP, 1.0, -5.0),
        ("vcp_breakout", _TURTLE_VCP, 3.0, -6.0),
        ("vcp_breakout", _TURTLE_VCP, 6.0, -9.0),
        # kojiro — sizing_mode 무관, 항상 `max(hard_stop_pct, -(stop_atr×atr))`
        ("kojiro", _KOJIRO, 3.0, -6.0),
        ("kojiro", _KOJIRO, 5.0, -8.0),
        ("kojiro", _KOJIRO, None, -8.0),
        # momentum — ATR 손절 전략이 아니다(고정 % 그대로)
        ("momentum", {"stop_loss_rate": -7.5}, 3.0, -7.5),
    ],
)
def test_g1_9a_resolve_stop_loss_pct_golden(sid, params, atr14_pct, expected) -> None:
    """G1-9 — ATR 재해석 골든 표.

    M9(`min` = 느슨한 쪽)을 죽인다 — 느슨한 쪽을 고르면 donchian atr=3.0 이 `-9.0` 이 되어
    "손절이 잡음보다 3배 넓다" 는 거짓을 모델에 먹인다. 결측(`None`)에 `0.0` 을 돌려주는
    회귀도 같은 표가 잡는다.
    """
    got = _gate()._resolve_stop_loss_pct(sid, params, {"atr14_pct": atr14_pct})
    assert got == pytest.approx(expected), f"{sid} atr={atr14_pct}: {got} != {expected}"


def test_g1_9b_non_turtle_donchian_keeps_fixed_pct() -> None:
    """G1-9 — `sizing_mode="position_ratio"` 인 donchian 은 ATR 재해석을 **타지 않는다**.

    DB 토글 하나로 손절 규약이 바뀌면 안 된다는 루트 CLAUDE.md 금기의 프롬프트 축 대응물이다
    (미스탬프 랏은 실제로 고정 -7% 를 탄다).
    """
    params = {**_TURTLE_D, "sizing_mode": "position_ratio"}
    got = _gate()._resolve_stop_loss_pct("donchian_swing", params, {"atr14_pct": 3.0})
    assert got == pytest.approx(-7.0), f"비-터틀 donchian 이 ATR 재해석을 탔다: {got}"


def test_g1_9c_resolve_never_returns_zero_or_positive() -> None:
    """G1-9 — 어떤 입력에도 `0.0`/양수를 돌려주지 않는다(fail-open 은 고정% 로).

    tech 가 통째로 비었거나 이상한 타입이어도 손절폭은 음수여야 한다 — 0.0 은
    판단 기준 4 를 항상 발동시키는 거짓말이다(F6).
    """
    gate = _gate()
    for sid in _strategy_ids():
        for tech in ({}, {"atr14_pct": None}, {"atr14_pct": "x"}, None):
            got = gate._resolve_stop_loss_pct(sid, _default_params(sid), tech)
            assert got < 0.0, f"{sid} tech={tech!r}: {got}"


# ===========================================================================
# G1-10 — 전략별 `prompt_version`
# ===========================================================================
def test_g1_10a_prompt_version_takes_strategy_id_and_differs_per_strategy() -> None:
    """G1-10 — `_prompt_version(sid)` 가 전략마다 다르다(M10: 인자 무시).

    사용자가 원한 **재귀 개선의 단위가 전략**이므로 버전 축도 전략이어야 한다 —
    kojiro 컨텍스트를 고쳤는데 donchian 표본까지 버전이 갈리면 회고가 매주 리셋된다.
    """
    gate = _gate()
    versions = {sid: gate._prompt_version(sid) for sid in _strategy_ids()}
    for sid, v in versions.items():
        assert isinstance(v, str) and len(v) == 12, f"{sid}: prompt_version={v!r}"
    assert len(set(versions.values())) == len(versions), (
        f"전략별로 갈리지 않는다 — {versions}"
    )


def test_g1_10b_prompt_version_is_stable_within_a_process() -> None:
    """G1-10 **양성 대조군** — 같은 sid 를 두 번 불러도 같다(캐시 정상).

    매 호출 재계산이 아니라 캐시여야 한다는 계약이자, 위 "달라진다" 단언이 난수로
    통과하는 것을 막는 짝이다.
    """
    gate = _gate()
    for sid in _strategy_ids():
        assert gate._prompt_version(sid) == gate._prompt_version(sid)


def test_g1_10c_prompt_version_changes_when_that_strategy_meta_changes(monkeypatch) -> None:
    """G1-10 — META 문구 1자 변경이 **그 전략의 버전만** 바꾼다(M11: blob 에서 META 제외).

    META 가 해시 blob 에 없으면 전략 컨텍스트를 고쳐도 `prompt_version` 이 그대로라
    "프롬프트 변경 전후 행 섞기 금지"(자문 §7-1)가 전략 축에서 조용히 뚫린다.
    """
    gate = _gate()
    lf = _lf()

    def _fresh(sid: str) -> str:
        gate.reset_llm_buy_gate_state()
        if hasattr(gate, "_prompt_version_cache"):
            monkeypatch.setattr(gate, "_prompt_version_cache", {}, raising=False)
        return gate._prompt_version(sid)

    before_d = _fresh("donchian_swing")
    before_k = _fresh("kojiro")

    patched = {k: dict(v) for k, v in lf._STRATEGY_META.items()}
    patched["donchian_swing"]["matters"] = patched["donchian_swing"]["matters"] + "."
    monkeypatch.setattr(lf, "_STRATEGY_META", patched)

    after_d = _fresh("donchian_swing")
    after_k = _fresh("kojiro")

    assert after_d != before_d, "donchian META 를 고쳤는데 prompt_version 이 그대로다"
    assert after_k == before_k, "kojiro META 는 안 고쳤는데 prompt_version 이 바뀌었다"
