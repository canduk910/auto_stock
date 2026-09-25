"""cycle290 Red — 장중 킬스위치 두 키 등재: 행위 불변 + 카탈로그 계약 + 부팅 병합.

정본 = cycle290 도메인 자문 §S1·§S2·§S6 (2026-09-13) + 사용자 결정 D1 "나머지는 권고대로".

## 무엇을 고치는 사이클인가

cycle287(커밋 `7dc6dae`)이 KRX 애프터마켓 청산 경로를 열고 킬스위치 **두 개**를
만들었지만, 두 키가 `param_catalog` 에도 어느 전략 `DEFAULT_PARAMS` 에도 없어
`PUT /api/strategies/{id}/params` 가 `unknown_key` 422 였다(2026-09-13 실측).
`param_validation` 의 미지 키 판정이 `key not in current_params **or** spec is None`
이므로 **카탈로그 등재와 `DEFAULT_PARAMS` 등재가 둘 다** 필요하다.

⇒ 09-14(월) 16:00~20:00 에 애프터 청산이 오작동하면 끌 방법이 셋 다 막힌다:
PUT 은 422 · `strategy_config` SQL UPDATE 는 다음 재시작에서만(cycle245 실측) ·
1커밋 revert + 재배포는 **그 자체가 그 창의 재시작**이다.

## 🔴 제1 계약 — 행위 변경 0

두 키를 **코드 상수와 똑같은 값**으로 넣는다. 그러면 `params.get(key, DEFAULT)` 가
같은 값을 돌려주므로 결정론 경로의 매매 행위가 한 글자도 바뀌지 않는다.

* `order_exchange_clock_mode` = `order_engine._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT`
* `after_market_exit_division` = `order_engine._AFTER_EXIT_DIVISION_DEFAULT`

**리터럴을 이 파일에 다시 타이핑하지 않는다**(자문 조건 1) — 모듈 상수에서 읽어 대조한다.
그래야 나중에 상수가 움직일 때 이 가드가 붉어진다(cycle245 G-245-6 선례).

⚠️ "행위 변경 0" 은 **무조건이 아니다** — 20:00 AI 자문 프롬프트(`current_params` 를
payload 에 통째로 싣는다)에는 두 키가 추가된다. 값은 4중 차단 때문에 바뀔 수 없지만
프롬프트 텍스트가 달라지므로 자문의 다른 출력(특히 `recommended_weight`)이 전일과
재현되지 않는다. cycle242·245·262·272·274 의 키 추가가 모두 같은 성질이었다(선례 5회).

## 왜 7 전략 전부인가

라우팅(`_apply_clock`·`_strategy_exchange_async`)과 애프터 변환(`execute_sell`·
`_cancel_and_reorder`)은 `strategy_id` 로 params 를 조회하는 **전 전략 공통 경로**다.
일부만 등재하면 나머지는 `key not in current_params` 로 여전히 422 이고, 하필 그 전략이
보유 중이면 그 순간 끌 수단이 없다. `tradable_boards` 는 **매수 진입 전용**이므로
"애프터에 청산이 나갈 수 있는 전략만" 이라는 선별은 성립하지 않는다(루트 CLAUDE.md 금기).

## 🔴 dial 은 `_clock_params` 가 유일 출처가 아니다

실제 44/41 행위를 정하는 두 곳(`execute_sell` · `_cancel_and_reorder`)은
`_clock_params` 를 거치지 않고 `config.params` 를 직접 읽는다(자문 §1-A). 그래서
`_clock_params` 단위 등가만으로는 부족하고, 이 파일은 **세 읽는 곳 전부**를 잰다.
"""

from __future__ import annotations

import ast
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_KST = timezone(timedelta(hours=9))

#: 등재 대상 두 키. `order_engine` 이 이미 읽고 있다.
_MODE_KEY = "order_exchange_clock_mode"
_DIAL_KEY = "after_market_exit_division"
_NEW_KEYS: tuple[str, ...] = (_MODE_KEY, _DIAL_KEY)

_STRATEGY_IDS: tuple[str, ...] = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
)


def _defaults(sid: str) -> dict:
    """전략 클래스의 `DEFAULT_PARAMS` 사본 (import 는 함수 안 — 수집 시 부작용 0)."""
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
    return copy.deepcopy(dict(table[sid].DEFAULT_PARAMS))


class _FakeStrategy:
    def __init__(self, sid: str, params: dict) -> None:
        self.strategy_id = sid
        self.config = SimpleNamespace(name=f"{sid}-전략", params=params)


class _FakeRegistry:
    def __init__(self, m: dict[str, _FakeStrategy]) -> None:
        self._m = m

    def get(self, sid: str):
        return self._m.get(sid)


def _engine_self(params_by_sid: dict[str, dict]):
    """`OrderEngine._clock_params` 를 부를 최소 self (registry 만 쓴다)."""
    return SimpleNamespace(
        registry=_FakeRegistry({
            sid: _FakeStrategy(sid, p) for sid, p in params_by_sid.items()
        })
    )


def _clock_params(params: dict, sid: str = "long_tail_volatility") -> tuple[str, str]:
    from src.engine.order_engine import OrderEngine

    return OrderEngine._clock_params(_engine_self({sid: params}), sid)


# ===========================================================================
# 1 — 등재 (RED)
# ===========================================================================
@pytest.mark.parametrize("sid", _STRATEGY_IDS)
@pytest.mark.parametrize("key", _NEW_KEYS)
def test_g290_11_two_keys_are_in_every_strategy_default_params(sid: str, key: str) -> None:
    """RED — 두 키가 **7 전략 전부**의 `DEFAULT_PARAMS` 에 있다.

    `param_validation` 의 미지 키 판정이 `key not in current_params or spec is None`
    이라 카탈로그 등재만으로는 PUT 이 통하지 않는다 — `DEFAULT_PARAMS` 가 곧 부팅 시
    `config.params` 의 기반이고(`merged = {**DEFAULT_PARAMS, **config.params}`), 그것이
    `current_params` 다.
    """
    assert key in _defaults(sid), (
        f"{sid}.DEFAULT_PARAMS 에 `{key}` 부재 — 그 전략은 장중에 끌 수 없다(422)"
    )


@pytest.mark.parametrize("sid", _STRATEGY_IDS)
@pytest.mark.parametrize(
    "key, const_name",
    [
        (_MODE_KEY, "_ORDER_EXCHANGE_CLOCK_MODE_DEFAULT"),
        (_DIAL_KEY, "_AFTER_EXIT_DIVISION_DEFAULT"),
    ],
)
def test_g290_12_default_value_equals_order_engine_constant(
    sid: str, key: str, const_name: str
) -> None:
    """🔴 RED — 등재 값 ≡ `order_engine` 모듈 상수 (행위 변경 0 의 전제).

    **값이 상수와 다르면 그 순간 매매 행위가 바뀐다.** 리터럴("enforce"/"44")을 이
    테스트에 다시 적지 않는다 — 모듈에서 읽어야 상수가 움직일 때 붉어진다.
    """
    from src.engine import order_engine as oe

    expected = getattr(oe, const_name)
    got = _defaults(sid).get(key, "<부재>")
    assert got == expected, (
        f"{sid}.DEFAULT_PARAMS[{key!r}] = {got!r} ≠ order_engine.{const_name} "
        f"= {expected!r} — 등재만으로 매매 행위가 바뀐다"
    )


#: cycle297(2026-09-17) — 5전략 LLM 매수평가 shadow 확대(사용자 결정 "결정 2 진행")로
#: momentum/donchian_swing/bull_flag_breakout/vcp_breakout/kojiro 에 4키가 새로
#: 추가됐다. `_NEW_KEYS`(cycle290 전용, 2키)와는 **다른 축**이라 섞지 않는다 — 섞으면
#: "cycle290 은 등재 2키뿐" 이라는 이 파일의 원래 명제가 흐려진다.
_CYCLE297_NEW_KEYS: tuple[str, ...] = (
    "llm_gate_mode", "llm_gate_min_score", "llm_gate_daily_call_cap", "llm_gate_timeout_secs",
)
_CYCLE297_AFFECTED_SIDS: frozenset[str] = frozenset({
    "momentum", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro",
})


#: cycle300(2026-09-18) — VCP 전용 일봉 읽기 깊이 스위치. 또 **다른 축**이라 위 둘과
#: 섞지 않는다(사용자 명시 승인 "100행 클램프도 해결하자"). VCP 한 전략에만 붙는다.
_CYCLE300_NEW_KEYS: tuple[str, ...] = ("daily_fetch_depth_mode",)
_CYCLE300_AFFECTED_SIDS: frozenset[str] = frozenset({"vcp_breakout"})


#: cycle352(2026-09-25) — LTV 전용 15:20 상한가 유지 확인 킬스위치. 또 **다른 축**이라
#: 위와 섞지 않는다(사용자 결정 D5 F3①). LTV 한 전략에만 붙는다.
_CYCLE352_NEW_KEYS: tuple[str, ...] = ("limit_up_close_hold_mode",)
_CYCLE352_AFFECTED_SIDS: frozenset[str] = frozenset({"long_tail_volatility"})


def _expected_new_keys(sid: str) -> set[str]:
    expected = set(_NEW_KEYS)
    if sid in _CYCLE297_AFFECTED_SIDS:
        expected |= set(_CYCLE297_NEW_KEYS)
    if sid in _CYCLE300_AFFECTED_SIDS:
        expected |= set(_CYCLE300_NEW_KEYS)
    if sid in _CYCLE352_AFFECTED_SIDS:
        expected |= set(_CYCLE352_NEW_KEYS)
    return expected


#: cycle301(2026-09-18, 사용자 승인 D3·D4) — VCP `ema_mid`/`ema_long`/`min_swing_atr_mult`
#: 3키의 **값**을 운영 DB 실측(150/200/1.0)에 맞춰 올렸다. `_CYCLE297_NEW_KEYS`/
#: `_CYCLE300_NEW_KEYS`(신규 키 추가)와는 다른 축이다 — 이 3키는 cycle290 착수
#: 시점에도 이미 `DEFAULT_PARAMS` 에 있던 키라 `test_g290_13`(키 **집합**의 델타,
#: `_expected_new_keys` 소관)에는 영향이 없어야 한다. 그래서 `_expected_new_keys()`
#: 에 섞지 않는다 — 섞으면 `now - pre`(실제로는 비어 있다, 두 스냅샷 모두 이 키를
#: 갖고 있으므로)와 `expected_new`(3키가 추가돼 부풀려진다)가 어긋나 `test_g290_13`
#: 이 붉어진다. 대신 `test_g290_14`(키별 **값** 비교) 에서만 이 3키를 뺀다 — 역사
#: 스냅샷(`_PRE_CYCLE290_DEFAULTS`)은 cycle290 착수 시점 값(ema_mid=60/ema_long=120/
#: min_swing_atr_mult=0.5)을 그대로 보존하고, cycle301 이 정당하게 바꾼 이 3키만
#: 비교에서 뺀다. VCP 한 전략에만 붙는다(kojiro 의 `ema_long=40`/`ema_mid=20` 은
#: 다른 전략의 다른 키라 무접촉).
_CYCLE301_CHANGED_KEYS: tuple[str, ...] = ("ema_mid", "ema_long", "min_swing_atr_mult")
_CYCLE301_AFFECTED_SIDS: frozenset[str] = frozenset({"vcp_breakout"})


def _excluded_from_value_comparison(sid: str) -> set[str]:
    """`test_g290_14` 값 비교에서 뺄 키 = 신규 키(`_expected_new_keys`) + cycle301 값 변경분.

    `_expected_new_keys(sid)` 는 `test_g290_13` 의 키 집합 델타(`now - pre`)와 등식
    비교되므로 값만 바뀐 기존 키를 거기 섞으면 그 등식이 깨진다(위 주석 참조). 이 함수는
    값 비교 전용이라 안전하게 합칠 수 있다.
    """
    excluded = _expected_new_keys(sid)
    if sid in _CYCLE301_AFFECTED_SIDS:
        excluded |= set(_CYCLE301_CHANGED_KEYS)
    return excluded


@pytest.mark.parametrize("sid", _STRATEGY_IDS)
def test_g290_13_key_set_delta_is_exactly_the_two_new_keys(sid: str) -> None:
    """RED — `DEFAULT_PARAMS` 키 집합의 변화가 **정확히 +2**, 삭제 0.

    🔁 cycle297 — VB·LTV 는 여전히 +2 뿐이지만, 5전략(momentum/donchian_swing/
    bull_flag_breakout/vcp_breakout/kojiro)은 사용자 승인 하에 +4 가 더해져 총 +6 이다
    (`_expected_new_keys` 가 그 차이를 sid 별로 표현한다 — `_NEW_KEYS` 자체는 cycle290
    전용 2키로 불변).
    """
    pre = set(_PRE_CYCLE290_DEFAULTS[sid])
    now = set(_defaults(sid))
    expected_new = _expected_new_keys(sid)
    assert now - pre == expected_new, f"예상 밖 신규 키: {sorted(now - pre - expected_new)}"
    assert pre - now == set(), f"키가 사라졌다: {sorted(pre - now)}"


@pytest.mark.parametrize("sid", _STRATEGY_IDS)
def test_g290_14_all_other_default_values_are_untouched(sid: str) -> None:
    """행위 불변 — 신규 키를 뺀 나머지 **값 전부**가 착수 시점과 같다.

    sha 핀 재산출은 "기존 값도 같이 바뀌었을 수 있다" 는 구멍을 남긴다(자문 A2). 여기서는
    dict 를 직접 비교하므로 실패 시 무엇이 바뀌었는지 그대로 읽힌다. 🔁 cycle297 —
    제외 집합이 sid 별로 `_expected_new_keys` 를 쓴다(위 test_g290_13 과 동일 축).
    🔁 cycle301 — VCP 는 여기에 `_CYCLE301_CHANGED_KEYS`(값만 바뀐 기존 키 3개)가
    추가로 빠진다(`_excluded_from_value_comparison` 참조. `test_g290_13` 의 키 집합
    델타에는 섞지 않는다 — 위 정의부 주석).
    """
    excluded = _excluded_from_value_comparison(sid)
    now = {k: v for k, v in _defaults(sid).items() if k not in excluded}
    # cycle301 — `_CYCLE301_CHANGED_KEYS` 는 역사 스냅샷에도 값이 존재하는 **기존** 키라
    # (신규 키와 달리) 양쪽에서 똑같이 제외해야 항목 수가 맞는다. 신규 키(`_expected_new_keys`
    # 소관)는 애초에 스냅샷 쪽에 없으므로 이 필터가 스냅샷 쪽에서는 no-op 이다.
    baseline = {k: v for k, v in _PRE_CYCLE290_DEFAULTS[sid].items() if k not in excluded}
    assert now == baseline, (
        "신규 키·cycle301 값 변경분 외의 `DEFAULT_PARAMS` 값이 바뀌었다 — "
        "cycle290/297/300/301 의 범위는 등재·승인된 값 변경뿐이다"
    )


# ===========================================================================
# 2 — 행위 불변: 읽는 곳 세 군데
# ===========================================================================
@pytest.mark.parametrize("sid", _STRATEGY_IDS)
def test_g290_21_clock_params_identical_with_and_without_the_keys(sid: str) -> None:
    """행위 불변 — 키를 넣은 뒤 반환 튜플이 **키가 없을 때와 완전히 동일**.

    `_clock_params` 는 `str(params.get(key, DEFAULT))` + dial 화이트리스트뿐이므로
    등재 값이 기본값과 같으면 항등이다. 등재 전에는 두 dict 가 같아 자동 성립하고,
    등재 후에 값이 어긋나면 이 단언이 깨진다.
    """
    from src.engine import order_engine as oe

    full = _defaults(sid)
    stripped = {k: v for k, v in full.items() if k not in _NEW_KEYS}

    assert _clock_params(full, sid) == _clock_params(stripped, sid)
    assert _clock_params(full, sid) == (
        oe._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT, oe._AFTER_EXIT_DIVISION_DEFAULT,
    )


def test_g290_22_clock_params_fallbacks_are_unchanged() -> None:
    """행위 불변 — 미지 전략·None·조회 예외의 fail-open 폴백 경로가 살아 있다."""
    from src.engine import order_engine as oe
    from src.engine.order_engine import OrderEngine

    expected = (oe._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT, oe._AFTER_EXIT_DIVISION_DEFAULT)
    me = _engine_self({"momentum": _defaults("momentum")})
    assert OrderEngine._clock_params(me, None) == expected
    assert OrderEngine._clock_params(me, "no_such_strategy") == expected

    class _Boom:
        def get(self, sid):  # noqa: D401 - 조회 자체가 던진다
            raise RuntimeError("registry down")

    assert OrderEngine._clock_params(SimpleNamespace(registry=_Boom()), "x") == expected


#: 등재 **전** 실측 격자(2026-09-13). `mode="enforce"` 에서는 `side` 가 결과에 영향을
#: 주지 않는다(clause 3 이 `sell_only` 전용) — 그 사실도 아래 테스트가 함께 잰다.
#: (date, "HH:MM", base) -> (routed, reason)
_ROUTE_GRID: dict[tuple[str, str, str], tuple[str, str]] = {}
for _d, _rows in {
    # 09-14 제도 변경 **이전** — 16:00~20:00 은 KRX 가 우리 호가를 안 받는다
    "2026-09-11": {
        "08:30": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "pre_nxt_keep"),
                  "SOR": ("SOR", "pre_nxt_keep")},
        "08:55": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "pre_nxt_keep"),
                  "SOR": ("SOR", "pre_nxt_keep")},
        "09:10": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "12:00": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "15:25": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "15:35": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "both_unsupported_keep"),
                  "SOR": ("SOR", "both_unsupported_keep")},
        "16:30": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "krx_unsupported_keep"),
                  "SOR": ("SOR", "krx_unsupported_keep")},
        "19:30": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "krx_unsupported_keep"),
                  "SOR": ("SOR", "krx_unsupported_keep")},
        "20:30": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "both_unsupported_keep"),
                  "SOR": ("SOR", "both_unsupported_keep")},
    },
    # 09-14 **이후** — 16:00~20:00 KRX 애프터마켓이 `41~47` 을 받아 KRX 로 라우팅된다
    "2026-09-14": {
        "08:30": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "pre_nxt_keep"),
                  "SOR": ("SOR", "pre_nxt_keep")},
        "08:55": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "pre_nxt_keep"),
                  "SOR": ("SOR", "pre_nxt_keep")},
        "09:10": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "12:00": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "15:25": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "15:35": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "both_unsupported_keep"),
                  "SOR": ("SOR", "both_unsupported_keep")},
        "16:30": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "19:30": {"KRX": ("KRX", "base_krx"), "NXT": ("KRX", "krx_by_clock"),
                  "SOR": ("KRX", "krx_by_clock")},
        "20:30": {"KRX": ("KRX", "base_krx"), "NXT": ("NXT", "both_unsupported_keep"),
                  "SOR": ("SOR", "both_unsupported_keep")},
    },
}.items():
    for _t, _bases in _rows.items():
        for _b, _exp in _bases.items():
            _ROUTE_GRID[(_d, _t, _b)] = _exp


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("cell", sorted(_ROUTE_GRID))
def test_g290_23_route_grid_is_unchanged_by_registration(
    cell: tuple[str, str, str], side: str
) -> None:
    """행위 불변 — 등재 전 실측 격자 9시각 × 3거래소 × 2방향 × 2날짜가 그대로다.

    ⚠️ 시각은 tz-aware KST `datetime` 으로 명시한다(`date.today()` 금지) — TZ=UTC 로
    돌려도 같은 결과여야 한다.
    """
    from src.engine import order_engine as oe

    day, hhmm, base = cell
    moment = datetime.fromisoformat(f"{day}T{hhmm}:00+09:00")
    assert moment.tzinfo is not None and moment.utcoffset() == timedelta(hours=9)
    got = oe._route_exchange_by_clock(
        base, side=side, mode=oe._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT, now=moment,
    )
    assert got == _ROUTE_GRID[cell], f"{day} {hhmm} base={base} side={side}: {got}"


@pytest.mark.parametrize("sid", _STRATEGY_IDS)
def test_g290_24_exit_division_read_sites_see_the_default(sid: str) -> None:
    """🔴 dial 은 읽는 곳이 **셋**이고 둘은 `_clock_params` 를 안 쓴다(자문 §1-A).

    `execute_sell`(:1137) · `_cancel_and_reorder`(:2331) 이 `config.params` 를 직접
    읽는다 — 등재 값이 화이트리스트 안의 기본값이므로 세 곳이 모두 같은 값을 본다.
    이 테스트는 그 **세 곳이 공유하는 폴백 관용구**를 재현해 잰다(async 주문 경로
    전체를 세우지 않고도 값 동일성을 잰다).
    """
    # 세 읽는 곳의 공통 관용구 — 어느 한 곳이 다른 기본값을 쓰면 여기서 갈린다.
    from src.engine import order_engine as oe

    params = _defaults(sid)
    for site in ("_clock_params", "execute_sell", "_cancel_and_reorder"):
        raw = str(params.get(_DIAL_KEY, oe._AFTER_EXIT_DIVISION_DEFAULT))
        dial = raw if raw in oe._AFTER_EXIT_DIVISION_ALLOWED else oe._AFTER_EXIT_DIVISION_DEFAULT
        assert dial == oe._AFTER_EXIT_DIVISION_DEFAULT, f"{site} 가 보는 dial = {dial}"
    assert _clock_params(params, sid)[1] == oe._AFTER_EXIT_DIVISION_DEFAULT


def test_g290_25_dial_read_sites_share_one_whitelist_and_one_default() -> None:
    """dial 을 읽는 세 곳이 **같은 상수 이름**을 참조한다(리터럴 흩뿌리기 금지).

    등재 값을 기본값으로 맞추는 것이 행위 불변의 전제인데, 어느 읽는 곳이 자기
    리터럴을 갖고 있으면 그 전제가 한쪽에서만 성립한다.
    """
    src = (_ROOT / "src/engine/order_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    sites = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "get":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != _DIAL_KEY:
            continue
        sites += 1
        assert len(node.args) >= 2, f"`{_DIAL_KEY}` get 에 기본값 인자가 없다"
        fallback = node.args[1]
        assert isinstance(fallback, ast.Name) and (
            fallback.id == "_AFTER_EXIT_DIVISION_DEFAULT"
        ), f"기본값이 상수 참조가 아니다: {ast.dump(fallback)[:80]}"
    assert sites == 3, (
        f"`{_DIAL_KEY}` 를 읽는 곳이 {sites} 군데다 — 자문 §1-A 는 3(=`_clock_params`·"
        f"`execute_sell`·`_cancel_and_reorder`) 을 실측했다. 늘거나 줄었으면 이 사이클의 "
        f"등가 증명 범위를 다시 잡아라"
    )


# ===========================================================================
# 2b — `execute_sell` 실경로 등가 (검증 발견 MEDIUM-3/LOW-4 후속 —
#      `test_g290_24` 는 세 읽는 곳의 **공통 관용구**만 재현했지, `execute_sell` 을
#      실제로 호출하지 않았다. 여기서는 실 전략(등재된 키를 실제로 갖는
#      `LongTailVolatilityStrategy`)으로 `execute_sell` 을 직접 돌려 dial 등가를
#      `_cur_after>0`/`==0` 두 갈래 모두 확인한다 — cycle287 K5 리그를 재사용한다.)
# ===========================================================================
_LTV_SID = "long_tail_volatility"
_LTV_TICKER = "161580"
_LTV_CUR = 24_800
_F_KRX_AFTER_1630 = "2026-09-15 07:30:00"  # UTC → KST 2026-09-15 16:30:00 (애프터 개장 중)


def _make_real_ltv_engine(*, dial: str | None):
    """실 `LongTailVolatilityStrategy`(등재된 `DEFAULT_PARAMS` 그대로, `exchange=SOR`
    로 override 해 라우터 clause 1 을 실제로 태운다 — 운영 DB 실측값과 동일)."""
    from src.engine.strategy_base import Position
    from src.engine.strategy_registry import StrategyRegistry
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from datetime import date as _date

    params: dict = {"exchange": "SOR"}
    if dial is not None:
        params[_DIAL_KEY] = dial
    strat = LongTailVolatilityStrategy(
        StrategyConfig(
            strategy_id=_LTV_SID, name="ltv-real", enabled=True, weight=1.0,
            params=params,
        )
    )
    strat.state.total_investment = 10_000_000
    strat.state.positions[_LTV_TICKER] = Position(
        ticker=_LTV_TICKER, buy_price=24_000, quantity=5, order_no="ORDER-PRE",
        strategy_id=_LTV_SID, buy_date=_date(2026, 9, 10),
    )
    reg = StrategyRegistry()
    reg.register(strat)
    from src.engine.order_engine import OrderEngine

    return OrderEngine(reg), strat


@pytest.fixture
def _real_ltv_rig(monkeypatch: pytest.MonkeyPatch):
    """cycle287 K5 리그와 동일한 격리 — DB·LLM·현재가 캐시·실전 환경·재시도 무력화."""
    import src.engine.order_engine as _oe
    import src.db.stock_master as _sm
    from src.config import settings
    from src.engine import scanner
    from src.engine.session import session_tracker, boards_at

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: None)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "is_stale", AsyncMock(return_value=False))
    monkeypatch.setattr(scanner, "ticker_prices", {_LTV_TICKER: {"current_price": _LTV_CUR}})
    monkeypatch.setattr(settings, "kis_env", "real")

    async def _instant(_delay):
        return None

    monkeypatch.setattr(_oe.asyncio, "sleep", _instant)

    def _pin() -> None:
        monkeypatch.setattr(
            session_tracker, "_active", boards_at(datetime.now(_KST).time())
        )

    return _pin


@pytest.fixture
def _mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = type(
        "R", (), {"order_no": "ORD-1", "order_time": "163000", "krx_org_no": ""}
    )()
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.mark.asyncio
async def test_g290_26_execute_sell_real_strategy_default_dial_matches_baseline(
    monkeypatch: pytest.MonkeyPatch, _real_ltv_rig, _mock_place_order: AsyncMock,
) -> None:
    """RED (자문 §S6-B4) — 등재된 키(부재와 동일한 값)로 **실** `execute_sell` 을 돌려도
    cycle287 이 "키 부재" 로 검증한 결과(=44, `ORD_UNPR=0`)와 byte 동일하다.

    `test_g290_24` 는 세 읽는 곳의 공통 관용구를 테스트 안에서 재현했을 뿐 `execute_sell`
    을 직접 부르지 않았다 — 이 테스트가 그 구멍을 메운다. dial 키를 아예 안 주면(=
    등재 전과 동일하게 "부재") `LongTailVolatilityStrategy.__init__` 이 자기
    `DEFAULT_PARAMS`(cycle290 이 등재한 `"44"`)로 채운다 — 그래서 "부재"와 "등재된
    기본값"이 실 전략에서는 이미 같은 코드경로다(등재의 요점 그 자체).
    """
    from src.engine.strategy_base import Signal
    from freezegun import freeze_time

    engine, _strat = _make_real_ltv_engine(dial=None)
    _real_ltv_rig()
    with freeze_time(_F_KRX_AFTER_1630):
        _real_ltv_rig()  # 시각이 얼어붙은 뒤 다시 보드를 고정
        await engine.execute_sell(_LTV_TICKER, Signal.STOP_LOSS, _LTV_SID)

    kw = _mock_place_order.await_args.kwargs
    assert kw["order_division"].value == "44", kw["order_division"]
    assert kw["price"] == 0, "44(최유리지정가)는 ORD_UNPR=0 이어야 한다"
    assert kw["exchange"] == "KRX"


@pytest.mark.asyncio
async def test_g290_27_execute_sell_real_strategy_dial_41_with_current_price(
    monkeypatch: pytest.MonkeyPatch, _real_ltv_rig, _mock_place_order: AsyncMock,
) -> None:
    """RED (자문 §S6-B4, `_cur_after>0` 갈래) — `dial="41"` + 현재가 있음 →
    `step_down(현재가, 5)` 지정가로 실제로 나간다(실 전략 경로)."""
    from src.engine.strategy_base import Signal
    from src.engine.util.tick_size import step_down
    from freezegun import freeze_time

    engine, _strat = _make_real_ltv_engine(dial="41")
    with freeze_time(_F_KRX_AFTER_1630):
        _real_ltv_rig()
        await engine.execute_sell(_LTV_TICKER, Signal.STOP_LOSS, _LTV_SID)

    kw = _mock_place_order.await_args.kwargs
    assert kw["order_division"].value == "41", kw["order_division"]
    assert kw["price"] == step_down(_LTV_CUR, steps=5)
    assert kw["exchange"] == "KRX"


@pytest.mark.asyncio
async def test_g290_28_execute_sell_real_strategy_dial_41_without_current_price(
    monkeypatch: pytest.MonkeyPatch, _real_ltv_rig, _mock_place_order: AsyncMock,
) -> None:
    """RED (자문 §S6-B4, `_cur_after==0` 갈래) — `dial="41"` + 현재가 결측이면 변환이
    **취소**되고 시장가가 그대로 나간다(help 의 경고를 실 전략 경로로 확증).

    이 갈래에서는 `[after_exit_division]` 마커도 나지 않는다(help·자문이 경고하는
    "봉인 3종 무력화" 창의 실경로 증거).
    """
    from src.engine.strategy_base import Signal
    from src.engine import scanner
    from freezegun import freeze_time

    engine, _strat = _make_real_ltv_engine(dial="41")
    monkeypatch.setattr(scanner, "ticker_prices", {})  # 현재가 결측
    with freeze_time(_F_KRX_AFTER_1630):
        _real_ltv_rig()
        monkeypatch.setattr(scanner, "ticker_prices", {})
        await engine.execute_sell(_LTV_TICKER, Signal.STOP_LOSS, _LTV_SID)

    kw = _mock_place_order.await_args.kwargs
    assert kw["order_division"].value == "01", (
        f"현재가 결측인데 변환됐다 — help 의 `cur=0` 경고가 실경로에서 거짓이다: "
        f"{kw['order_division']}"
    )


# ===========================================================================
# 3 — 카탈로그 계약 (RED)
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_KEYS)
def test_g290_31_spec_exists_with_the_agreed_field_values(key: str) -> None:
    """RED — 두 키가 `param_catalog` 에 있고 합의된 필드값을 갖는다(자문 §S2).

    `editable=False` 면 이 사이클이 고치려는 증상이 사유만 `not_editable` 로 바뀐 채
    남는다. `auto_tunable=True` 는 가드 C4(`auto_tunable_keys() ⊆ PARAM_RANGES`)와
    충돌해 구조적으로 불가능하다. `range_src="none"` 은 값 집합이 소스에 실재하므로
    거짓이고 C9 의 "정확히 9키" 단언도 깬다.
    """
    from src.engine import param_catalog as pc

    spec = pc.get_spec(key)
    assert spec is not None, f"`{key}` 가 param_catalog 에 없다 — PUT 이 422 다"
    assert spec.type == "enum", spec.type
    assert spec.range_src == "enum", spec.range_src
    assert spec.editable is True, "editable=False 면 모든 PUT 이 not_editable 422 다"
    assert spec.auto_tunable is False, "AI 자문이 킬스위치를 뒤집으면 안 된다"
    assert spec.deprecated is False, spec.deprecated
    assert spec.risk == "identity", (
        f"risk={spec.risk!r} — 청산 수단을 끄는 스위치이고 기존 모드 킬스위치"
        f"(`open_price_scope_mode`·`llm_gate_mode`)가 전부 identity 다"
    )
    assert (spec.min, spec.max, spec.step) == (None, None, None)
    assert spec.unit == ""
    assert spec.group == "time_board", (
        f"group={spec.group!r} — `exchange` 와 같은 아코디언이어야 비상 롤백이 한 화면에서 "
        f"끝난다"
    )
    assert spec.choices, "enum 인데 choices 가 비었다"
    assert spec.forbidden_choices == ()
    assert spec.deprecated_for == ()


@pytest.mark.parametrize("key", _NEW_KEYS)
def test_g290_32_applies_to_is_all_seven_and_matches_default_params(key: str) -> None:
    """RED — `applies_to` == `STRATEGY_IDS` == 그 키를 가진 전략 집합.

    카탈로그 가드 C3 가 `applies_to ≡ 키 보유 전략 집합` 을 **정확히** 강제하므로
    등재 범위와 이 필드는 한 몸이다.
    """
    from src.engine import param_catalog as pc

    spec = pc.get_spec(key)
    assert spec is not None
    assert tuple(spec.applies_to) == pc.STRATEGY_IDS, spec.applies_to
    holders = tuple(sid for sid in pc.STRATEGY_IDS if key in _defaults(sid))
    assert tuple(spec.applies_to) == holders, (
        f"applies_to={spec.applies_to} ≠ DEFAULT_PARAMS 보유 전략 {holders}"
    )


@pytest.mark.parametrize("sid", _STRATEGY_IDS)
@pytest.mark.parametrize("key", _NEW_KEYS)
def test_g290_33_keys_for_strategy_includes_both(sid: str, key: str) -> None:
    """RED — `keys_for_strategy(sid)` 가 두 키를 포함한다(화면·422 `expected` 원천)."""
    from src.engine import param_catalog as pc

    assert key in pc.keys_for_strategy(sid), f"{sid} 의 키 목록에 `{key}` 없음"


def test_g290_34_dial_choices_come_from_the_source_whitelist() -> None:
    """🔴 RED — dial `choices` 값 집합 == `order_engine._AFTER_EXIT_DIVISION_ALLOWED`.

    하드코딩 목록과 소스가 갈리면 화면이 **저장할 수 없는 값**을 보여 준다(또는 실제로
    동작하는 값을 숨긴다). 런타임 집합을 직접 읽어 대조한다.
    """
    from src.engine import order_engine as oe
    from src.engine import param_catalog as pc

    spec = pc.get_spec(_DIAL_KEY)
    assert spec is not None, f"`{_DIAL_KEY}` 스펙 부재"
    got = {c.value for c in spec.choices}
    assert got == set(oe._AFTER_EXIT_DIVISION_ALLOWED), (
        f"choices={sorted(got)} ≠ _AFTER_EXIT_DIVISION_ALLOWED="
        f"{sorted(oe._AFTER_EXIT_DIVISION_ALLOWED)}"
    )
    assert all(isinstance(c.value, str) for c in spec.choices), (
        "dial 값은 **문자열**이다 — 정수 44 는 `not_in_choices` 로 거부돼야 한다"
    )
    assert oe._AFTER_EXIT_DIVISION_DEFAULT in got


def test_g290_35_mode_choices_come_from_the_router_source() -> None:
    """🔴 RED — mode `choices` == 라우터의 `mode` 비교 리터럴 ∪ 기본값 상수.

    `order_engine` 에는 `_ALLOWED_CLOCK_MODES` 같은 집합이 **없다** — 어휘는
    `_route_exchange_by_clock` 의 `if mode == ...` 두 줄과 기본값 상수뿐이다(실측:
    `{"off", "sell_only"}` + `"enforce"`). 목록을 손으로 베끼면 라우터가 clause 를
    늘릴 때 화면이 조용히 낡는다.
    """
    from src.engine import order_engine as oe
    from src.engine import param_catalog as pc

    src = (_ROOT / "src/engine/order_engine.py").read_text(encoding="utf-8")
    fn = next(
        n for n in ast.parse(src).body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_route_exchange_by_clock"
    )
    literals = {
        c.value
        for n in ast.walk(fn)
        if isinstance(n, ast.Compare)
        and isinstance(n.left, ast.Name) and n.left.id == "mode"
        for c in n.comparators
        if isinstance(c, ast.Constant) and isinstance(c.value, str)
    }
    assert literals == {"off", "sell_only"}, (
        f"라우터의 mode 비교 리터럴이 바뀌었다: {sorted(literals)} — choices 와 "
        f"`src/engine/CLAUDE.md` 를 함께 갱신하라"
    )
    expected = literals | {oe._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT}

    spec = pc.get_spec(_MODE_KEY)
    assert spec is not None, f"`{_MODE_KEY}` 스펙 부재"
    got = {c.value for c in spec.choices}
    assert got == expected, f"choices={sorted(got)} ≠ 소스 어휘 {sorted(expected)}"


@pytest.mark.parametrize("key", _NEW_KEYS)
def test_g290_36_choices_have_korean_labels_and_no_deprecated_entry(key: str) -> None:
    """RED — 선택지 라벨은 한국어이고 폐기 항목이 없다(전부 살아 있는 값이다)."""
    from src.engine import param_catalog as pc

    spec = pc.get_spec(key)
    assert spec is not None
    for choice in spec.choices:
        assert choice.label_ko.strip(), f"{key}/{choice.value} 라벨 비어 있음"
        assert any("가" <= ch <= "힣" for ch in choice.label_ko), (
            f"{key}/{choice.value} 라벨에 한글이 없다: {choice.label_ko!r}"
        )
        assert choice.deprecated is False, f"{key}/{choice.value} 가 deprecated 다"


@pytest.mark.parametrize(
    "key, phrase",
    [
        # 자문 조건 3 — 사고 중에 읽는 글이므로 무엇이 함께 꺼지는지가 들어가야 한다.
        (_MODE_KEY, "sell_only"),
        (_MODE_KEY, "애프터"),
        (_DIAL_KEY, "44"),
        (_DIAL_KEY, "41"),
    ],
)
def test_g290_37_help_names_the_side_effects(key: str, phrase: str) -> None:
    """RED — `help` 가 부작용·대안을 이름으로 말한다(자문 조건 3).

    `off` 는 라우팅만 끄는 것이 아니라 **애프터 44/41 변환까지 죽인다**(그 게이트가
    `target_exchange == "KRX"` 다). 매수만 되돌리는 중간 다이얼이 `sell_only` 라는
    사실이 help 에 없으면 운영자가 사고 중에 `off` 를 고른다.
    """
    from src.engine import param_catalog as pc

    spec = pc.get_spec(key)
    assert spec is not None
    assert phrase in spec.help, f"`{key}` help 에 {phrase!r} 언급 없음: {spec.help[:120]}"


def test_g290_38_catalog_spec_count_is_102() -> None:
    """카탈로그 스펙 수 99 → **101**(cycle290) → **102**(cycle300 깊이 스위치) →
    **103**(cycle352 15:20 상한가 유지 확인). 중복 없음.

    cycle278 계열 가드 4곳(`test_cycle278_param_catalog`·`test_cycle278_params_schema`·
    `test_routes_strategies`·프론트 `_ast_param_key_hardcode`)이 같은 숫자를 세므로
    키를 늘리는 사이클은 그 넷을 함께 옮긴다.
    """
    from src.engine import param_catalog as pc

    assert len(pc.PARAM_SPECS) == 103, len(pc.PARAM_SPECS)
    assert len(pc.SPEC_BY_KEY) == 103, len(pc.SPEC_BY_KEY)
    assert len({s.key for s in pc.PARAM_SPECS}) == 103, "키 중복"


# ===========================================================================
# 4 — AI 자문 자동 적용 차단 (등재 후에도 닫혀 있어야 한다)
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_KEYS)
def test_g290_41_not_in_param_ranges_or_int_params(key: str) -> None:
    """런타임 dict 이중 봉인 — cycle287 `test_s5` 와 같은 계약을 여기서도 잠근다.

    🔴 이 단언이 4중 차단(`_validate_recommendations` → `_CONSERVATIVE_KEYS` →
    `auto_apply` safeguard → 수동 적용 필터) 전체의 **유일한 상류 봉인**이다.
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert key not in PARAM_RANGES, f"`{key}` 가 PARAM_RANGES 에 들어왔다"
    assert key not in INT_PARAMS, f"`{key}` 가 INT_PARAMS 에 들어왔다"


@pytest.mark.parametrize("key", _NEW_KEYS)
def test_g290_42_not_auto_tunable_in_catalog(key: str) -> None:
    """RED — `auto_tunable_keys()` 에 두 키가 없다(가드 C4 와 같은 방향)."""
    from src.engine import param_catalog as pc

    assert key not in pc.auto_tunable_keys()


@pytest.mark.parametrize("key, bad", [(_MODE_KEY, "off"), (_DIAL_KEY, "41")])
def test_g290_43_llm_recommendation_cannot_set_the_keys(key: str, bad: str) -> None:
    """AI 자문이 두 키를 추천해도 **저장 후보에 들어가지 않는다**.

    `_validate_recommendations` 가 `key not in PARAM_RANGES` 에서 `continue` 하므로
    `recommended_params` JSONB 에 애초에 남지 않는다. `float(val)` 캐스트보다 **앞**
    이라 `"44"` → `44.0` 함정도 도달 불가다.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    current = _defaults("long_tail_volatility")
    current.setdefault(key, bad)  # 등재 전에도 "현재 params 에 있다" 조건을 만족시킨다
    validated, *_ = _validate_recommendations(
        {"recommended_params": {key: bad}, "reasoning": "테스트"}, current
    )
    assert key not in validated, f"자문이 `{key}` 를 저장 후보로 통과시켰다"


def test_g290_44_auto_apply_params_loop_is_still_closed() -> None:
    """`_CONSERVATIVE_KEYS` 가 비어 있어 `auto_apply` params 루프가 전 키를 건너뛴다.

    이게 채워지면 20:00 자문이 **살아 있는 전략 객체**를 변이할 수 있게 되므로 두 키의
    노출 판정이 달라진다 — 그때 이 사이클의 결론을 다시 계산해야 한다.
    """
    from src.engine.recommendation_engine import _CONSERVATIVE_KEYS

    assert set(_CONSERVATIVE_KEYS) == set(), (
        f"_CONSERVATIVE_KEYS 가 채워졌다: {sorted(_CONSERVATIVE_KEYS)} — auto_apply 가 "
        f"파라미터를 즉시 반영하게 됐으니 킬스위치 노출 판정을 재검토하라"
    )


# ===========================================================================
# 5 — 부팅 병합 (`_load_strategy_config`)
# ===========================================================================
def _cfg(params: dict) -> dict:
    return {"enabled": True, "weight": 0.1, "params": params}


@pytest.mark.asyncio
@pytest.mark.parametrize("sid", _STRATEGY_IDS)
async def test_g290_51_boot_keeps_code_default_when_db_lacks_the_keys(sid: str) -> None:
    """RED — DB params 에 두 키가 없으면 **코드 기본값이 남는다**(현재 운영 상태).

    병합은 `if key in strategy.config.params` 라 코드 키 집합이 화이트리스트다 —
    DB 에 없는 키는 코드 값이 그대로고, DB 에만 있는 키는 조용히 버려진다(지금 두 키가
    정확히 그 상태여서 PUT 이 422 였다).

    2026-09-13 운영 DB 실측: 7 전략 **전부** 두 키 없음 ⇒ 배포 후 첫 부팅의 값은 코드
    기본값 = 현행 행위. 드리프트 위험 0.
    """
    from src.engine import order_engine as oe
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    strategy = sched.registry.get(sid)
    assert strategy is not None, f"{sid} 미등록 — 이 테스트의 전제가 깨졌다"

    with patch("src.db.strategy_config.load_all", AsyncMock(return_value={sid: _cfg({})})):
        await sched._load_strategy_config()

    assert strategy.config.params[_MODE_KEY] == oe._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT
    assert strategy.config.params[_DIAL_KEY] == oe._AFTER_EXIT_DIVISION_DEFAULT


@pytest.mark.asyncio
async def test_g290_52_boot_lets_db_value_win_when_present() -> None:
    """RED — DB 에 값이 있으면 그것이 이긴다(부팅 롤백 경로가 살아 있다).

    등재 **전**에는 `if key in strategy.config.params` 가 거짓이라 DB 값이 조용히
    버려졌다 — 그래서 SQL UPDATE 조차 다음 재시작에서도 안 먹었다.
    """
    from src.engine.scheduler import TradingScheduler

    sid = "long_tail_volatility"
    sched = TradingScheduler()
    strategy = sched.registry.get(sid)
    assert strategy is not None

    db = {sid: _cfg({_MODE_KEY: "off", _DIAL_KEY: "41"})}
    with patch("src.db.strategy_config.load_all", AsyncMock(return_value=db)):
        await sched._load_strategy_config()

    assert strategy.config.params[_MODE_KEY] == "off"
    assert strategy.config.params[_DIAL_KEY] == "41"
    assert _clock_params(dict(strategy.config.params), sid) == ("off", "41")


@pytest.mark.asyncio
async def test_g290_53_config_loaded_guard_means_sql_needs_a_restart() -> None:
    """`_config_loaded` 가 프로세스당 1회 — SQL 롤백은 재시작 전까지 안 먹는다.

    cycle232 D6(보유 중 장중 재시작 금지)과 겹치면 **장중 실효 수단은 PUT 뿐**이다.
    이 단언이 깨지면(재로드 경로가 생기면) 문서·help 의 "PUT 이 유일 경로" 문안을
    함께 갱신하라.
    """
    from src.engine.scheduler import TradingScheduler

    sid = "long_tail_volatility"
    sched = TradingScheduler()
    first = AsyncMock(return_value={sid: _cfg({})})
    with patch("src.db.strategy_config.load_all", first):
        await sched._load_strategy_config()
    assert first.await_count == 1, "첫 로드가 DB 를 읽지 않았다 — 전제 붕괴"

    second = AsyncMock(return_value={sid: _cfg({_MODE_KEY: "off"})})
    with patch("src.db.strategy_config.load_all", second):
        await sched._load_strategy_config()
    assert second.await_count == 0, "`_config_loaded` 가드가 사라졌다"
    assert sched.registry.get(sid).config.params.get(_MODE_KEY) != "off"


# ===========================================================================
# 착수 시점(2026-09-13, HEAD `b985938`) `DEFAULT_PARAMS` 값 전수 스냅샷
#
# ⚠️ 이 dict 는 **행위 불변의 기준선**이다. 두 키 등재 외의 변경이 섞이면
#    `test_g290_13`/`test_g290_14` 가 그 자리를 가리킨다. 값을 바꾸는 다음 사이클이
#    이 스냅샷을 갱신한다(그때는 그 사이클이 매매 행위 변경 승인을 받은 것이다).
#
# 🔴 `exchange` 가 7 전략 전부 `"KRX"` 임에 주의 — 운영 DB 는 **`"NXT"`** 로 덮고 있다
# (2026-09-13 04:3x 사용자 결정 D3 로 `SOR`→`NXT` PUT 완료. 그 전 값은 `SOR` 이었고
#  `_CLOCK_ROUTED_BASES = ("NXT","SOR")` 이라 **둘 다 시각 재판정 대상**이므로 이 스위치의
#  작동 여부는 D3 전후로 바뀌지 않는다 — 바뀐 것은 프리장 주문이 나가는 거래소뿐이다)
#    (2026-09-13 실측, `_workspace/00_URGENT_WORKLIST.md` 판독표 · cycle286 C4-a).
#    `off` 킬스위치의 파괴력은 DB 값이 NXT/SOR 일 때만 성립한다(base 가 KRX 면
#    라우터 clause 1 에서 mode 검사 전에 빠져나간다) — 지금은 실제로 작동한다.
# ===========================================================================
_PRE_CYCLE290_DEFAULTS: dict[str, dict] = {
    "momentum": {
        "buy_threshold": 29.0,
        "daily_loss_limit": -5.0,
        "exchange": 'KRX',
        "gap_up_threshold": 10.0,
        "max_lot_ratio_mult": 2.5,
        "max_positions": 4,
        "position_ratio": 0.25,
        "stop_loss_rate": -7.5,
        "tradable_boards": ['krx_open', 'main'],
        "trailing_stop_rate": -2.0,
    },
    "volatility_breakout": {
        "daily_loss_limit": -5.0,
        "exchange": 'KRX',
        "failed_breakout_buffer_pct": -0.5,
        "failed_breakout_confirm_ticks": 2,
        "failed_breakout_exit_enabled": False,
        "k_period": 20,
        "k_value_krx_main": 1.0,
        "k_value_nxt_post": 1.0,
        "k_value_nxt_pre": 1.0,
        "llm_gate_daily_call_cap": 20,
        "llm_gate_min_score": 70,
        "llm_gate_mode": 'shadow',
        "llm_gate_timeout_secs": 20,
        "max_lot_ratio_mult": 2.5,
        "max_positions": 10,
        "max_scan_stocks": 100,
        "min_market_cap": 100000000000,
        "min_trade_amount": 20000000000,
        "open_entry_hold_secs": 90,
        "open_price_scope_mode": 'enforce',
        "position_ratio": 0.1,
        "quant_filter_enabled": False,
        "quant_max_mf_rank": 0,
        "quant_min_f_score": 0,
        "reentry_cooldown_days": 2,
        "rs_filter_enabled": False,
        "rsi_extreme_max": 85,
        "rsi_filter_enabled": False,
        "stop_loss_rate": -3.0,
        "tradable_boards": ['main'],
    },
    "long_tail_volatility": {
        "daily_loss_limit": -5.0,
        "exchange": 'KRX',
        "exclude_consecutive_limit": 2,
        "gap_up_threshold": 10.0,
        "intraday_stop_loss": -3.0,
        "k_period": 20,
        "k_value_krx_main": 1.0,
        "k_value_nxt_post": 1.0,
        "k_value_nxt_pre": 1.0,
        "limit_up_threshold": 29.0,
        "llm_gate_daily_call_cap": 20,
        "llm_gate_min_score": 70,
        "llm_gate_mode": 'shadow',
        "llm_gate_timeout_secs": 20,
        "max_lot_ratio_mult": 2.5,
        "max_positions": 6,
        "max_scan_stocks": 100,
        "min_market_cap": 100000000000,
        "min_prdy_rate": 5.0,
        "min_trade_amount": 20000000000,
        "open_entry_hold_secs": 90,
        "open_price_scope_mode": 'enforce',
        "overnight_stop_loss": -5.0,
        "position_ratio": 0.15,
        "reentry_cooldown_days": 2,
        "tradable_boards": ['pre_nxt', 'main', 'post_nxt'],
        "trailing_stop_rate": -2.0,
    },
    "donchian_swing": {
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        "breakeven_promote_atr": 1.5,
        "breakout_fail_n_days": 5,
        "channel_exit_period": 10,
        "daily_loss_limit": -8.0,
        "donchian_period": 20,
        "exchange": 'KRX',
        "exclude_tickers": [],
        "gap_skip_threshold": 3.0,
        "long_ma_period": 60,
        "max_breakout_extension_pct": 4.0,
        "max_lot_ratio_mult": 2.5,
        "max_lot_units": 2.0,
        "max_positions": 5,
        "max_scan_stocks": 400,
        "min_market_cap": 50000000000,
        "min_trade_amount": 1000000000,
        "min_vol_floor_pct": 1.0,
        "nxt_tradable": None,
        "position_ratio": 0.2,
        "risk_pct": 0.005,
        "sizing_mode": 'position_ratio',
        "stop_atr": 2.0,
        "stop_loss_rate": -7.0,
        "tradable_boards": ['main'],
        "turtle_backstop_pct": -9.0,
        "volume_multiplier": 1.5,
        "volume_period": 20,
    },
    "bull_flag_breakout": {
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        "breakeven_promote_atr": 0.0,
        "breakout_retention_minutes": 3,
        "breakout_volume_mult": 2.0,
        "daily_loss_limit": -6.0,
        "entry_end": '13:00',
        "entry_start": '09:05',
        "exchange": 'KRX',
        "flag_lookback_max": 10,
        "flag_lookback_min": 2,
        "flag_retracement_max": 0.5,
        "flag_volume_ratio": 0.6,
        "max_breakout_extension_pct": 5.0,
        "max_hold_days": 5,
        "max_lot_ratio_mult": 2.5,
        "max_lot_units": 2.0,
        "max_positions": 4,
        "max_scan_stocks": 4000,
        "min_market_cap": 10000000000,
        "min_trade_amount": 1500000000,
        "min_vol_floor_pct": 1.0,
        "pole_lookback_max": 10,
        "pole_lookback_min": 3,
        "pole_max_red_ratio": 0.45,
        "pole_min_return": 15.0,
        "position_ratio": 0.25,
        "reentry_cooldown_days": 3,
        "risk_pct": 0.005,
        "sizing_mode": 'position_ratio',
        "stop_atr": 2.0,
        "stop_loss_rate": -5.0,
        "tradable_boards": ['main'],
        "turtle_backstop_pct": -7.0,
        "turtle_min_stop_pct": -4.0,
    },
    "vcp_breakout": {
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        "base_depth_pct": 0.3,
        "base_max_days": 75,
        "base_min_days": 25,
        "breakeven_promote_atr": 0.0,
        "breakout_volume_mult": 1.5,
        "daily_loss_limit": -8.0,
        # ⚠️ ema_long/ema_mid/min_swing_atr_mult — 이 스냅샷은 **cycle290 착수 시점**
        # (2026-09-13, HEAD `b985938`) 값(120/60/0.5)을 그대로 보존한다. cycle301
        # (2026-09-18, 사용자 승인 D3·D4)이 이 3키의 코드 값을 150/200/1.0 으로 올렸지만
        # 여기서 값을 함께 옮기면 이 dict 가 "cycle290 착수 시점" 이라는 원래 의미를
        # 잃는다 — 값을 덮지 않고, `_CYCLE301_CHANGED_KEYS` 로 `test_g290_14` 비교에서만
        # 뺀다(아래 정의부 참조).
        "ema_long": 120,
        "ema_mid": 60,
        "ema_short": 50,
        "entry_end": '14:30',
        "entry_start": '09:05',
        "exchange": 'KRX',
        "last_pullback_max": 0.12,
        "long_ema_uptrend_days": 20,
        "max_breakout_extension_pct": 7.5,
        "max_lot_ratio_mult": 2.5,
        "max_lot_units": 2.0,
        "max_positions": 5,
        "max_scan_stocks": 4000,
        "min_market_cap": 10000000000,
        "min_swing_atr_mult": 0.5,
        "min_trade_amount": 1000000000,
        "min_vol_floor_pct": 1.0,
        "position_ratio": 0.2,
        "pullback_count_max": 4,
        "pullback_count_min": 2,
        "reentry_cooldown_days": 7,
        "risk_pct": 0.005,
        "sizing_mode": 'position_ratio',
        "stop_atr": 2.0,
        "stop_loss_rate": -7.0,
        "tradable_boards": ['main'],
        "turtle_backstop_pct": -9.0,
        "turtle_min_stop_pct": -5.0,
        "volume_contraction_ratio": 0.7,
    },
    "kojiro": {
        "atr_period": 20,
        "atr_ratio_max": 0.06,
        "atr_ratio_min": 0.01,
        "breakeven_promote_atr": 0.0,
        "daily_loss_limit": -8.0,
        "ema_long": 40,
        "ema_mid": 20,
        "ema_short": 5,
        "exchange": 'KRX',
        "exclude_tickers": [],
        "gap_down_skip_pct": -4.0,
        "gap_up_skip_pct": 5.0,
        "hard_stop_pct": -8.0,
        "macd_signal": 9,
        "max_lot_ratio_mult": 2.5,
        "max_lot_units": 2.0,
        "max_open_risk_pct": 4.5,
        "max_positions": 5,
        "max_positions_per_sector": 2,
        "max_scan_stocks": 4000,
        "max_units_per_stock": 2,
        "max_units_total": 10,
        "min_market_cap": 50000000000,
        "min_trade_amount": 1000000000,
        "min_vol_floor_pct": 1.0,
        "nxt_tradable": None,
        "position_ratio": 0.2,
        "rank_w_band": 0.3,
        "rank_w_fresh": 0.3,
        "rank_w_macd3": 0.4,
        "risk_pct": 0.005,
        "sizing_mode": 'position_ratio',
        "slope_lookback": 1,
        "stage1_freshness": 5,
        "stop_atr": 2.0,
        "tradable_boards": ['main'],
        "trail_atr": 2.5,
    },
}
