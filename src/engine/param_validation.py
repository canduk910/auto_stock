"""전략 파라미터 검증 — **순수 함수 leaf** (사이클 278).

`param_catalog` 의 99 스펙만 읽어 요청 파라미터를 검증한다.

* I/O·로깅·전역 상태 0. `src.engine.param_catalog` 외에는 아무 것도 import 하지 않는다
  (AST 가드 `tests/unit/ast/test_cycle278_ast_catalog_guards.py::
  test_param_validation_module_is_leaf_importing_only_catalog`).
* 라우트에 검증을 두면 `src/routes/strategies.py` 가 비대해지고 순수 함수로 테스트할 수
  없다. 또 AI 자문 수동 적용 경로(`src/routes/recommendations.py`)는 PUT 라우트를 거치지
  않고 `strategy.config.params` 를 직접 쓰므로, 검증을 함수로 뽑아 두면 후속 사이클에서
  그 경로에 같은 함수를 붙이는 것이 한 줄이다(이번 사이클에서는 붙이지 않는다).

────────────────────────────────────────────────────────────────────────────
판정 순서 (명세 §5.1)
────────────────────────────────────────────────────────────────────────────
1) 키 존재                     → ``unknown_key``
2) editable                    → ``not_editable``
3) 자료형                      → ``type_mismatch``
4) enum / choices / pattern    → ``not_in_choices`` / ``pattern_mismatch``
5) 전략별 금지 선택지           → ``forbidden_choice``
6) min / max · 최소 항목 수     → ``out_of_range`` / ``too_few_items``
7) 예산 불변식(병합 결과)       → ``budget_invariant``   ← 유일한 다중 키 오류
8) 순서 불변식(병합 결과)       → 경고만
9) 오류가 하나도 없으면 ``accepted`` 만 병합 저장(all-or-nothing)

**첫 오류에서 멈추지 않는다.** 한 번의 저장으로 여러 필드를 고치는 화면이므로,
멈추면 운영자가 오류를 하나씩 왕복하며 고치게 되고 그 왕복마다 all-or-nothing 이
다시 걸린다.

────────────────────────────────────────────────────────────────────────────
경고를 422 로 올리지 않는 것들
────────────────────────────────────────────────────────────────────────────
``budget_invariant_preexisting``
    이미 위반 중인 상태를 **악화시키지 않는** 편집까지 막으면 그 전략은 영구 편집
    불가가 되고 복구 수단이 DB 직접 UPDATE 뿐이다(장중 재시작 금지 D6 때문에 더 위험).
``order_invariant``
    두 키를 동시에 뒤집는 정상 편집(창을 통째로 옮기기)이 중간 상태에서 막힌다.
    다만 위반이 **무증상**(후보 0)이라 반드시 경고로 남긴다.
``no_effect_for_strategy`` / ``range_unbounded``
    값 자체는 유효하다. 그 전략에서 지금 효력이 없다는 사실 / 범위 근거가 없다는
    사실만 화면에 남긴다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from src.engine import param_catalog as pc

__all__ = [
    "EPS",
    "BUDGET_KEYS",
    "MAX_BUDGET_PRODUCT",
    "ERROR_CODES",
    "WARNING_CODES",
    "ParamError",
    "ParamWarning",
    "ValidationResult",
    "validate_params",
]

#: 부동소수 허용오차. `0.15 × 6 = 0.8999999999999999`, `0.3 × 4 = 1.2000000000000002`
#: 이므로 경계 비교는 반드시 EPS 를 낀다. 경계 `1.0` 은 **통과**여야 한다 —
#: 7 전략 중 6 전략의 현재 기본값이 정확히 1.0 이라 `<` 로 바꾸면 전면 저장 불가다.
EPS = 1e-9
MAX_BUDGET_PRODUCT = 1.0
BUDGET_KEYS: tuple[str, str] = ("position_ratio", "max_positions")

ERROR_CODES: tuple[str, ...] = (
    "unknown_key",
    "not_editable",
    "type_mismatch",
    "not_in_choices",
    "pattern_mismatch",
    "forbidden_choice",
    "out_of_range",
    "too_few_items",
    "budget_invariant",
)
WARNING_CODES: tuple[str, ...] = (
    "budget_invariant_preexisting",
    "order_invariant",
    "no_effect_for_strategy",
    "range_unbounded",
)

_TYPE_LABEL: dict[str, str] = {
    "int": "정수",
    "float": "실수",
    "percent": "비율(0.0~1.0, 화면 표시는 %)",
    "bool": "참/거짓",
    "enum": "선택지 중 하나",
    "list_str": "문자열 목록",
    "str": "문자열",
}


@dataclass(frozen=True)
class ParamError:
    """422 `detail` 배열의 원소 하나.

    `key` 가 `None` 인 오류(예산 불변식)는 특정 입력란이 아니라 폼 전체에 붙는다.
    `msg` 는 **한글**이고 pydantic 접두사(`Value error, `)를 넣지 않는다 —
    프론트의 `extractValidationMessage` 가 알려진 접두사만 제거하기 때문이다.
    """

    key: str | None
    code: str
    msg: str
    strategy_id: str
    given: Any = None
    expected: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "code": self.code,
            "msg": self.msg,
            "strategy_id": self.strategy_id,
            "given": self.given,
            "expected": dict(self.expected) if self.expected else {},
        }


@dataclass(frozen=True)
class ParamWarning:
    """200 응답에 함께 실리는 경고 하나 (저장은 이루어졌다)."""

    key: str | None
    code: str
    msg: str
    strategy_id: str
    detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "code": self.code,
            "msg": self.msg,
            "strategy_id": self.strategy_id,
            "detail": dict(self.detail) if self.detail else {},
        }


@dataclass(frozen=True)
class ValidationResult:
    """검증 결과. `errors` 가 비어 있지 않으면 라우트가 **422** 를 낸다."""

    errors: tuple[ParamError, ...] = ()
    warnings: tuple[ParamWarning, ...] = ()
    accepted: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


# ───────────────────────────────────────────────────────────────────────────
# 자료형 판정 헬퍼
# ───────────────────────────────────────────────────────────────────────────
def _is_int(value: Any) -> bool:
    """`bool` 은 `int` 의 서브클래스다 — 정수 키에 `True` 가 들어오면 안 된다."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _choice_values(spec: pc.ParamSpec) -> list[Any]:
    return [c.value for c in spec.choices]


def _choice_match(value: Any, choice: Any) -> bool:
    """`True == 1` · `False == 0` 파이썬 동치를 막는 타입 인지 비교.

    `nxt_tradable` 의 선택지가 `(None, True, False)` 라 이 구분이 실제로 필요하다.
    """
    if value is None or choice is None:
        return value is None and choice is None
    if isinstance(value, bool) or isinstance(choice, bool):
        return isinstance(value, bool) and isinstance(choice, bool) and value == choice
    return bool(value == choice)


def _fmt(value: Any) -> str:
    return f"{value!r}" if isinstance(value, str) else f"{value}"


def _label(spec: pc.ParamSpec) -> str:
    return f"{spec.label_ko}({spec.key})"


def _expected_of(spec: pc.ParamSpec) -> dict[str, Any]:
    exp: dict[str, Any] = {"type": spec.type, "range_src": spec.range_src}
    if spec.min is not None:
        exp["min"] = spec.min
    if spec.max is not None:
        exp["max"] = spec.max
    if spec.choices:
        exp["choices"] = _choice_values(spec)
    if spec.pattern:
        exp["pattern"] = spec.pattern
    if spec.min_items:
        exp["min_items"] = spec.min_items
    if spec.forbidden_choices:
        exp["forbidden"] = [
            {"strategy_id": f.strategy_id, "value": f.value, "reason": f.reason}
            for f in spec.forbidden_choices
        ]
    return exp


# ───────────────────────────────────────────────────────────────────────────
# 키 하나 검증 — 자료형 → choices/pattern → 범위
# ───────────────────────────────────────────────────────────────────────────
def _type_error(sid: str, spec: pc.ParamSpec, value: Any) -> ParamError:
    return ParamError(
        key=spec.key,
        code="type_mismatch",
        msg=(
            f"{_label(spec)}의 자료형이 맞지 않습니다 — {_TYPE_LABEL.get(spec.type, spec.type)}"
            f" 이어야 하는데 받은 값 {_fmt(value)}"
            f" ({type(value).__name__})"
        ),
        strategy_id=sid,
        given=value,
        expected=_expected_of(spec),
    )


def _range_msg(spec: pc.ParamSpec, value: Any) -> str:
    unit = f" {spec.unit}" if spec.unit else ""
    if spec.range_src == "sign":
        if spec.max is not None and spec.max <= 0:
            direction = f"0 이하(음수){unit}"
        else:
            direction = f"0 이상{unit}"
        return (
            f"{_label(spec)}은(는) 부호 규약상 {direction} 이어야 합니다 —"
            f" 받은 값 {_fmt(value)}. 부호가 반대면 코드가 그 게이트를 **조용히 비활성**하거나"
            " (`hard_stop_pct` 처럼) 모든 포지션을 즉시 손절하는 반대 동작을 합니다"
        )
    if spec.min is not None and spec.max is not None:
        bound = f"{spec.min} ~ {spec.max}{unit}"
    elif spec.min is not None:
        bound = f"{spec.min}{unit} 이상"
    else:
        bound = f"{spec.max}{unit} 이하"
    tail = " (비율 저장, 화면 표시는 %)" if spec.type == "percent" else ""
    return f"{_label(spec)}은(는) {bound} 이어야 합니다 — 받은 값 {_fmt(value)}{tail}"


def _forbidden_error(
    sid: str, spec: pc.ParamSpec, given: Any, offending: list[Any],
) -> ParamError | None:
    """전략별 금지 선택지 위반 → 422 (사이클 278 후속 시정 2).

    `choices` 는 값 어휘의 상한이고 이것은 **전략별** 하한이다. 화면이 체크박스를
    비활성으로 그리더라도 서버가 정본이어야 한다 — curl·구버전 화면·자동화가 같은 조합에
    도달할 수 있고, 그 조합이 깨는 것은 루트 `CLAUDE.md` 의 절대 규칙이다.
    """
    hits = [
        f for f in spec.forbidden_choices
        if f.strategy_id == sid and any(_choice_match(v, f.value) for v in offending)
    ]
    if not hits:
        return None
    return ParamError(
        key=spec.key,
        code="forbidden_choice",
        msg=(
            f"{_label(spec)}에 {[_fmt(f.value) for f in hits]} 은(는) 전략"
            f" '{sid}' 에서 금지된 조합입니다 — "
            + " / ".join(f.reason for f in hits)
        ),
        strategy_id=sid,
        given=given,
        expected=_expected_of(spec),
    )


def _check_one(sid: str, spec: pc.ParamSpec, value: Any) -> ParamError | None:
    """한 키의 자료형·선택지·정규식·범위를 본다. 통과하면 `None`."""
    kind = spec.type

    if kind == "enum":
        if not any(_choice_match(value, c) for c in _choice_values(spec)):
            return ParamError(
                key=spec.key,
                code="not_in_choices",
                msg=(
                    f"{_label(spec)}은(는) {_choice_values(spec)} 중 하나여야 합니다 —"
                    f" 받은 값 {_fmt(value)}"
                ),
                strategy_id=sid,
                given=value,
                expected=_expected_of(spec),
            )
        return _forbidden_error(sid, spec, value, [value])

    if kind == "bool":
        if not isinstance(value, bool):
            return _type_error(sid, spec, value)
        return None

    if kind == "list_str":
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            return _type_error(sid, spec, value)
        allowed = _choice_values(spec)
        if allowed:
            bad = [item for item in value if not any(_choice_match(item, c) for c in allowed)]
            if bad:
                return ParamError(
                    key=spec.key,
                    code="not_in_choices",
                    msg=(
                        f"{_label(spec)}의 항목 {bad} 은(는) 허용 목록 {allowed} 밖입니다 —"
                        " 오타는 무증상으로 그 기능을 꺼 버립니다"
                    ),
                    strategy_id=sid,
                    given=value,
                    expected=_expected_of(spec),
                )
        elif spec.pattern:
            bad = [item for item in value if not re.match(spec.pattern, item)]
            if bad:
                return ParamError(
                    key=spec.key,
                    code="pattern_mismatch",
                    msg=(
                        f"{_label(spec)}의 항목 {bad} 이(가) 형식({spec.pattern})에 맞지 않습니다"
                        " — 종목코드는 6자리 숫자입니다"
                    ),
                    strategy_id=sid,
                    given=value,
                    expected=_expected_of(spec),
                )

        forbidden = _forbidden_error(sid, spec, value, list(value))
        if forbidden is not None:
            return forbidden

        if len(value) < spec.min_items:
            return ParamError(
                key=spec.key,
                code="too_few_items",
                msg=(
                    f"{_label(spec)}은(는) 최소 {spec.min_items}개를 선택해야 합니다 —"
                    f" 받은 값 {value}. 빈 목록은 전략마다 효과가 정반대라"
                    " 조용한 사고가 됩니다: momentum·변동성돌파·롱테일·돈치안은 코드"
                    " 기본 보드로 폴백해 매수가 그대로 이어지고(저장했는데 아무 일도"
                    " 일어나지 않는다), 불플래그·VCP·고지로는 허용 보드가 공집합이 되어"
                    " **매수가 전면 중단**됩니다."
                    " 매수를 멈추려면 이 목록을 비우지 말고 전략을 비활성화하세요"
                    " (전략 화면의 사용/미사용 토글)"
                ),
                strategy_id=sid,
                given=value,
                expected=_expected_of(spec),
            )
        return None

    if kind == "str":
        if not isinstance(value, str):
            return _type_error(sid, spec, value)
        if spec.pattern and not re.match(spec.pattern, value):
            return ParamError(
                key=spec.key,
                code="pattern_mismatch",
                msg=(
                    f"{_label(spec)}은(는) HH:MM(24시간) 형식이어야 합니다 —"
                    f" 받은 값 {_fmt(value)}. 형식이 틀리면 장중 매수 판정에서 예외가 납니다"
                    if spec.pattern == r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
                    else (
                        f"{_label(spec)}이(가) 형식({spec.pattern})에 맞지 않습니다 —"
                        f" 받은 값 {_fmt(value)}"
                    )
                ),
                strategy_id=sid,
                given=value,
                expected=_expected_of(spec),
            )
        return None

    if kind == "int":
        if not _is_int(value):
            return _type_error(sid, spec, value)
    elif kind in ("float", "percent"):
        if not _is_number(value):
            return _type_error(sid, spec, value)
    else:  # 닫힌 어휘 밖 — 카탈로그가 깨진 경우로 보고 저장을 막는다
        return _type_error(sid, spec, value)

    if (spec.min is not None and value < spec.min) or (
        spec.max is not None and value > spec.max
    ):
        return ParamError(
            key=spec.key,
            code="out_of_range",
            msg=_range_msg(spec, value),
            strategy_id=sid,
            given=value,
            expected=_expected_of(spec),
        )
    return None


def _coerce(spec: pc.ParamSpec, value: Any) -> Any:
    """검증을 통과한 값의 저장 형태.

    `float`/`percent` 키에 JSON 정수(`1`)가 오면 실수로 맞춘다. 그 밖은 무변환 —
    값 크기로 단위를 추론하는 변환은 **하지 않는다**(폐기된 `v / 100 if v > 1` 재현 금지).
    """
    if spec.type in ("float", "percent") and _is_int(value):
        return float(value)
    return value


# ───────────────────────────────────────────────────────────────────────────
# 불변식
# ───────────────────────────────────────────────────────────────────────────
def _product(params: Mapping[str, Any]) -> float | None:
    ratio = params.get(BUDGET_KEYS[0])
    count = params.get(BUDGET_KEYS[1])
    if not _is_number(ratio) or not _is_number(count):
        return None  # 판정 불가는 fail-open (검사 생략)
    return float(ratio) * float(count)


def _check_budget(
    sid: str, current: Mapping[str, Any], merged: Mapping[str, Any],
) -> tuple[ParamError | None, ParamWarning | None]:
    """§5.3 진리표.

    이미 위반 중인 상태를 **악화시키지 않는** 편집은 통과 + 경고다 — 막으면 그 전략은
    영구 편집 불가가 된다.
    """
    after = _product(merged)
    if after is None or after <= MAX_BUDGET_PRODUCT + EPS:
        return None, None

    ratio = merged.get(BUDGET_KEYS[0])
    count = merged.get(BUDGET_KEYS[1])
    before = _product(current)
    given = {BUDGET_KEYS[0]: ratio, BUDGET_KEYS[1]: count, "product": after}
    expected = {"max_product": MAX_BUDGET_PRODUCT, "keys": list(BUDGET_KEYS)}

    if before is not None and before > MAX_BUDGET_PRODUCT + EPS:
        if after <= before + EPS:
            return None, ParamWarning(
                key=None,
                code="budget_invariant_preexisting",
                msg=(
                    f"이미 예산 불변식을 위반한 상태입니다 — 종목당 비중 × 동시 보유 종목수"
                    f" = {ratio} × {count} = {after:.2f} > {MAX_BUDGET_PRODUCT}."
                    " 이번 저장이 상태를 악화시키지는 않아 진행했지만, 두 값을 함께 조정해"
                    " 1.0 이하로 되돌리는 것이 좋습니다"
                ),
                strategy_id=sid,
                detail={**given, "product_before": before},
            )
        return (
            ParamError(
                key=None,
                code="budget_invariant",
                msg=(
                    f"이미 위반 중인 예산 불변식을 더 악화시킵니다 — 종목당 비중 × 동시 보유"
                    f" 종목수 = {ratio} × {count} = {after:.2f} (저장 전 {before:.2f}),"
                    f" 상한 {MAX_BUDGET_PRODUCT}"
                ),
                strategy_id=sid,
                given={**given, "product_before": before},
                expected=expected,
            ),
            None,
        )

    return (
        ParamError(
            key=None,
            code="budget_invariant",
            msg=(
                f"종목당 비중 × 동시 보유 종목수 = {ratio} × {count} = {after:.2f} 으로"
                f" {MAX_BUDGET_PRODUCT} 을 넘습니다 — 두 값을 같은 저장에서 함께 조정하세요"
            ),
            strategy_id=sid,
            given=given,
            expected=expected,
        ),
        None,
    )


def _comparable(lo: Any, hi: Any) -> bool:
    if isinstance(lo, str) and isinstance(hi, str):
        return True
    return _is_number(lo) and _is_number(hi)


def _check_order_invariants(sid: str, merged: Mapping[str, Any]) -> list[ParamWarning]:
    """`lo_key <= hi_key` 소프트 불변식 — 위반이 **무증상**이라 경고로 남긴다."""
    out: list[ParamWarning] = []
    for inv in pc.ORDER_INVARIANTS:
        if sid not in inv.strategies:
            continue
        lo = merged.get(inv.lo_key)
        hi = merged.get(inv.hi_key)
        if lo is None or hi is None or not _comparable(lo, hi):
            continue
        if lo > hi:
            out.append(
                ParamWarning(
                    key=inv.lo_key,
                    code="order_invariant",
                    msg=(
                        f"{inv.lo_key}({lo}) 이(가) {inv.hi_key}({hi}) 보다 큽니다 —"
                        f" {inv.consequence}"
                    ),
                    strategy_id=sid,
                    detail={
                        "lo_key": inv.lo_key,
                        "hi_key": inv.hi_key,
                        "lo": lo,
                        "hi": hi,
                        "consequence": inv.consequence,
                    },
                )
            )
    return out


# ───────────────────────────────────────────────────────────────────────────
# 공개 진입점
# ───────────────────────────────────────────────────────────────────────────
def validate_params(
    strategy_id: str,
    current_params: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> ValidationResult:
    """요청 파라미터를 검증한다 (순수 함수).

    Args:
        strategy_id: 전략 id.
        current_params: 병합 **전** 그 전략의 현재 params.
        incoming: 요청 바디의 params (부분 dict).

    Returns:
        `ValidationResult` — `errors` 가 비어 있으면 `accepted` 만 병합 저장한다.
    """
    errors: list[ParamError] = []
    warnings: list[ParamWarning] = []
    accepted: dict[str, Any] = {}

    for key, value in incoming.items():
        spec = pc.get_spec(key)
        if key not in current_params or spec is None:
            errors.append(
                ParamError(
                    key=key,
                    code="unknown_key",
                    msg=(
                        f"'{key}' 은(는) 전략 '{strategy_id}' 의 파라미터가 아닙니다 —"
                        " 오타이거나 다른 전략의 키입니다 (조용히 버리지 않습니다)"
                    ),
                    strategy_id=strategy_id,
                    given=value,
                    expected={"keys": list(pc.keys_for_strategy(strategy_id))},
                )
            )
            continue

        if not spec.editable:
            errors.append(
                ParamError(
                    key=key,
                    code="not_editable",
                    msg=(
                        f"{_label(spec)}은(는) 읽기 전용입니다 — 이 키는 어느 전략에서도"
                        " 행위에 쓰이지 않는 잔존 키라, 값을 바꿔도 매매가 바뀌지 않습니다"
                    ),
                    strategy_id=strategy_id,
                    given=value,
                    expected={"editable": False, "deprecated": spec.deprecated},
                )
            )
            continue

        err = _check_one(strategy_id, spec, value)
        if err is not None:
            errors.append(err)
            continue

        accepted[key] = _coerce(spec, value)

    merged = {**dict(current_params), **accepted}

    budget_err, budget_warn = _check_budget(strategy_id, current_params, merged)
    if budget_err is not None:
        errors.append(budget_err)
    if budget_warn is not None:
        warnings.append(budget_warn)

    warnings.extend(_check_order_invariants(strategy_id, merged))

    for key in accepted:
        spec = pc.get_spec(key)
        if spec is None:
            continue
        if strategy_id in spec.deprecated_for:
            warnings.append(
                ParamWarning(
                    key=key,
                    code="no_effect_for_strategy",
                    msg=(
                        f"{_label(spec)}은(는) 지금 설정의 '{strategy_id}' 에서는 효력이"
                        " 없습니다 — 값은 저장했습니다. 해당 보드를 tradable_boards 에"
                        " 추가하면 되살아납니다"
                    ),
                    strategy_id=strategy_id,
                    detail={"deprecated_for": list(spec.deprecated_for)},
                )
            )
        if spec.range_src == "none":
            warnings.append(
                ParamWarning(
                    key=key,
                    code="range_unbounded",
                    msg=(
                        f"{_label(spec)}은(는) 근거 있는 범위가 없어 자료형만 검사했습니다 —"
                        " 값의 타당성은 사람이 판단해야 합니다"
                    ),
                    strategy_id=strategy_id,
                    detail={"range_src": spec.range_src},
                )
            )

    return ValidationResult(tuple(errors), tuple(warnings), accepted)
