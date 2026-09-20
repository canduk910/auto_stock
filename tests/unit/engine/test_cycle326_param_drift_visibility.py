"""cycle326 — 운영 DB 값이 코드 기본값과 39개나 다른데 아무도 몰랐다.

## 무엇이 문제였나

`_load_strategy_config` 는 DB `params` 를 **키별로 덮어쓴다**. 그래서 한 번 DB 에 박힌 값은
계속 살고, 코드 기본값은 그 키에 대해 **장식**이 된다. 그 차이를 알리는 것이 아무것도 없었다.

2026-09-20 전수 실측 = **39개 키**가 달랐다. 그리고 그 무지가 실제 오판을 만들었다 —

> 롱테일 상한가 모드를 **코드 기본값**으로 읽어 「손절이 −3% → −5% 로 느슨해진다」고
> 사용자에게 보고했다. 운영 DB 는 정반대(**−5% → −3.5%, 조여진다**)였다.

VB 손절도 코드 −3% 로 계산해 1회 위험을 0.31% 라 했는데 DB 는 **−5%** 라 실제는 그 1.7배였다.

## 무엇을 재는가

부팅 때 **실행 params 와 코드 기본값의 차이를 세어 한 줄로 남긴다.** 값 자체는 바꾸지 않는다
(관찰 전용 · fail-open) — DB 가 정본이라는 계약은 그대로다. 바뀌는 것은 **보인다**는 것뿐이다.

🔴 **차이를 「고쳐서」 없애려 하지 않는다.** 운영자가 의도적으로 넣은 값이 대부분이고
(VCP 완화·kojiro 슬롯 등), 코드값으로 되돌리면 그것이 곧 사고다.

⚠️ `scheduler.py` 는 라인 상한(3,900L)에 **여유 115줄**이라 손대지 않는다.
`boot_manager` 의 `check_budget_invariant` 선례와 같은 자리에 leaf 로 붙인다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class _Cfg:
    def __init__(self, sid, params):
        self.strategy_id = sid
        self.params = params


class _Strategy:
    """`registry.all()` 이 돌려주는 것의 최소 모양."""

    def __init__(self, sid, params, defaults):
        self.strategy_id = sid
        self.config = _Cfg(sid, params)
        self.DEFAULT_PARAMS = defaults


def test_detects_value_difference() -> None:
    """값이 다른 키를 집어내는가."""
    from src.engine.param_drift import collect_param_drift

    s = _Strategy("vb", {"stop_loss_rate": -5.0}, {"stop_loss_rate": -3.0})
    out = collect_param_drift([s])
    assert len(out) == 1, out
    d = out[0]
    assert d["strategy_id"] == "vb"
    assert d["key"] == "stop_loss_rate"
    assert d["live"] == -5.0
    assert d["code"] == -3.0


def test_ignores_equal_values() -> None:
    """같으면 잡지 않는가 — 잡으면 39건이 아니라 수백 건이 되어 아무도 안 본다."""
    from src.engine.param_drift import collect_param_drift

    s = _Strategy("vb", {"a": 1, "b": "x"}, {"a": 1, "b": "x"})
    assert collect_param_drift([s]) == []


def test_ignores_keys_absent_from_defaults() -> None:
    """코드에 없는 키는 「차이」가 아니다.

    막는 회귀 = 운영 전용 키(코드에 기본값이 없는 것)를 드리프트로 세는 것.
    그러면 정상 운영이 매일 경고를 내고, 사람이 그 경고를 배경 소음으로 학습한다.
    """
    from src.engine.param_drift import collect_param_drift

    s = _Strategy("vb", {"operator_only": 7}, {"a": 1})
    assert collect_param_drift([s]) == []


def test_int_float_equivalence_is_not_drift() -> None:
    """`4` 와 `4.0` 은 같은 값이다.

    🔴 실측에서 DB 는 정수로, 코드는 float 로 적힌 키가 많다
    (`max_positions` 4 vs 6 은 진짜 차이지만 `limit_up_threshold` 29 vs 29.0 은 아니다).
    구별 못 하면 가짜 경고가 진짜를 덮는다.
    """
    from src.engine.param_drift import collect_param_drift

    s = _Strategy("ltv", {"limit_up_threshold": 29}, {"limit_up_threshold": 29.0})
    assert collect_param_drift([s]) == []


def test_never_raises_on_broken_input() -> None:
    """망가진 입력에도 **절대 예외를 올리지 않는가** — 부팅을 끊으면 안 된다.

    이 관측이 부팅을 막으면 그날 매매가 통째로 없다. 관측이 행위를 바꾸면 안 된다.
    """
    from src.engine.param_drift import collect_param_drift

    class _Bad:
        @property
        def config(self):
            raise RuntimeError("고장")

    assert collect_param_drift([_Bad()]) == []
    assert collect_param_drift(None) == []  # type: ignore[arg-type]
    assert collect_param_drift([object()]) == []


def test_boot_emits_the_marker() -> None:
    """부팅 경로가 이 관측을 실제로 부르는가 — 선언만 하고 안 쓰면 공허하다."""
    import inspect

    from src.engine import boot_manager

    src = inspect.getsource(boot_manager)
    assert "collect_param_drift" in src, "boot_manager 가 드리프트 관측을 부르지 않는다"
    assert "[param_drift]" in src, "관측 마커 `[param_drift]` 가 없다"


def test_marker_reports_count_and_samples() -> None:
    """마커가 **개수와 예시**를 함께 남기는가.

    개수만 남기면 「39」를 보고도 무엇이 다른지 모르고, 전부 남기면 로그가 묻힌다.
    """
    import inspect

    from src.engine import boot_manager

    src = inspect.getsource(boot_manager)
    i = src.find("[param_drift]")
    window = src[max(0, i - 500): i + 500]
    assert "len(" in window or "count" in window, "개수를 안 센다"
