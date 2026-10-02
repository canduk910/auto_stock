"""cycle406 카드 #4 — 공통 필수 키를 전략 명부 하나로 glob 검사.

`_workspace/refactor/2026-09-27_strategy_add_remove_structure.md` 카드 #4:
「공통 필수 키 12개를 `tests/_strategy_census.py` 명부로 glob 검사(각 전략
`DEFAULT_PARAMS` ⊇ 12키). 카탈로그 12 스펙은 `applies_to=STRATEGY_IDS` 별칭으로.
값은 `StrategyBase` 로 끌어올리지 않는다.」

실측(cycle406) — 메모가 적힌 09-27 이후 `shadow_mode`(cycle399)·`daily_loss_limit`
이 늘고 `etf_trend`(cycle403, 8번째 전략)가 더해져 실제 교집합은 **14개**다. 카탈로그
쪽 "applies_to=STRATEGY_IDS 별칭"은 이미 되어 있다(`param_catalog._ALL7 = STRATEGY_IDS`,
cycle278 이후 누적 — 이 테스트가 다시 확인한다). 이 파일이 새로 더하는 것은 카탈로그를
거치지 않는 **직접** 명부 검사다: 이름 붙은 안전 가드(A-GATE·C-DEFAULT·cycle233 게이트
위치)가 전부 그렇듯, 카탈로그 쪽 교차검사(`test_applies_to_when_compared_then_matches_default_params_exactly`)
는 새 전략이 키 하나를 빠뜨리면 "그 키의 `applies_to` 가 어긋난다"는 간접 증상으로만
드러난다. 여기서는 "이 키가 없다"는 직접 메시지로 실패한다.

값은 바꾸지 않는다 — `tests/`·`src/engine/param_catalog.py` 의 `_ALL7` 별칭 확인만.
`src/engine/strategies/*.py` 는 읽기만 한다(AST, import 없음).

자기검사: `REQUIRED_COMMON_KEYS` 가 비어 있거나 `MIN_STRATEGIES` 보다 적은 명부를
돌면 안 되므로 census 쪽 자기검사(`tests/unit/ast/test_strategy_census.py`)에 얹힌다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.engine import param_catalog as pc
from tests import _strategy_census as census

#: 실측(cycle406) 교집합 14 키. 전부 `src/engine/strategies/CLAUDE.md` 「새 전략 추가」
#: 5번 배선 의무가 이름으로 열거하는 키들이다. 늘리거나 줄이는 사이클은 이 튜플과
#: 위 독스트링의 "14" 를 함께 고친다(`test_required_keys_count_matches_doc_claim`).
REQUIRED_COMMON_KEYS: tuple[str, ...] = (
    "buy_paused",
    "shadow_mode",
    "daily_loss_limit",
    "position_ratio",
    "max_positions",
    "max_lot_ratio_mult",
    "tradable_boards",
    "exchange",
    "order_exchange_clock_mode",
    "after_market_exit_division",
    "llm_gate_mode",
    "llm_gate_min_score",
    "llm_gate_daily_call_cap",
    "llm_gate_timeout_secs",
)


def _default_params_keys_ast(fname: str) -> frozenset[str]:
    """그 전략 파일의 `DEFAULT_PARAMS` 키 집합(AST, import 없음).

    `tests/_strategy_census.py::strategy_class_name_ast` 로 클래스를 찾고,
    그 클래스 바디의 `DEFAULT_PARAMS = {...}` 딕셔너리 리터럴에서 키만 뽑는다.
    """
    cls_name = census.strategy_class_name_ast(fname)
    tree = ast.parse((census.STRATEGIES_DIR / fname).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == cls_name):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(getattr(t, "id", None) == "DEFAULT_PARAMS" for t in stmt.targets):
                continue
            assert isinstance(stmt.value, ast.Dict), f"{fname}: DEFAULT_PARAMS 가 dict 리터럴이 아니다"
            keys: set[str] = set()
            for k in stmt.value.keys:
                assert isinstance(k, ast.Constant) and isinstance(k.value, str), (
                    f"{fname}: DEFAULT_PARAMS 키가 문자열 리터럴이 아니다"
                )
                keys.add(k.value)
            return frozenset(keys)
    raise AssertionError(f"{fname}::{cls_name} 에서 DEFAULT_PARAMS 를 찾지 못했다")


def test_required_common_keys_when_nonempty_then_at_least_min_strategies_guard_meaningful():
    """자기검사 — 빈 목록이면 아래 parametrize 가 전부 거짓 초록(=검사 안 함)이 된다."""
    assert len(REQUIRED_COMMON_KEYS) >= 1
    assert len(census.STRATEGY_FILES) >= census.MIN_STRATEGIES


@pytest.mark.parametrize("fname", census.STRATEGY_FILES)
def test_default_params_when_checked_then_superset_of_required_common_keys(fname: str):
    """카드 #4 본문 — 명부의 전략 파일 전부가 공통 필수 키를 전부 갖는다."""
    keys = _default_params_keys_ast(fname)
    missing = set(REQUIRED_COMMON_KEYS) - keys
    assert not missing, (
        f"{fname}: 공통 필수 키 누락 {sorted(missing)} — 새 전략이라면 "
        "`src/engine/strategies/CLAUDE.md` 「새 전략 추가」 5번 배선 의무를 봐라. "
        "값을 바꾸는 게 아니라 다른 전략과 같은 값으로 그 키를 DEFAULT_PARAMS 에 적는다."
    )


def test_required_common_keys_when_compared_to_catalog_then_all_aliased_to_strategy_ids():
    """공통 필수 키는 카탈로그에서 `applies_to=STRATEGY_IDS` 별칭이어야 한다(카드 #4 둘째 문장).

    `param_catalog._ALL7` 은 모듈 비공개 변수라 직접 import 하지 않고, 공개 상수
    `STRATEGY_IDS` 와 `applies_to` 가 **같은 튜플(동일성)** 인지로 "별칭" 여부를 잰다 —
    값만 같고 따로 선언된 복붙은 여기서 걸린다(의도대로 `_ALL7 = STRATEGY_IDS` 를 강제).
    """
    by_key = {s.key: s for s in pc.PARAM_SPECS}
    for key in REQUIRED_COMMON_KEYS:
        spec = by_key.get(key)
        assert spec is not None, f"{key}: 카탈로그에 스펙이 없다"
        assert spec.applies_to is pc.STRATEGY_IDS, (
            f"{key}: applies_to 가 `pc.STRATEGY_IDS` 별칭이 아니다(다른 튜플 객체) — "
            "`_ALL7 = STRATEGY_IDS` 별칭을 쓰지 않고 따로 적었을 가능성"
        )


def test_required_common_keys_when_counted_then_matches_docstring_claim():
    """독스트링의 "14" 가 튜플 길이와 어긋나면 바로 여기서 잡는다(문서 드리프트 방지)."""
    assert len(REQUIRED_COMMON_KEYS) == 14
