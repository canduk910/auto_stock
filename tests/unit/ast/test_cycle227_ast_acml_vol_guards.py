"""cycle227 W7 — AST 영구 가드 4종.

| # | 가드 | 지키는 것 |
|---|---|---|
| AST-1 | 전 소스에서 `ticker_prices` 에 `acml_vol` **대입** 0건 | 유령 키 재발 + donchian `ext_pct` 커플링 |
| AST-2 | BFB·VCP 기존 거래량 컷 블록 **소스 텍스트 pin** | Stage 0 봉인 (행위 변경 0) |
| AST-3 | handler `_handle_tick` 의 `len(fields) < 10` 가드 상수 불변 | 손절·트레일링 틱 drop 차단 |
| AST-4 | `tick_volume.py` = leaf (8영역·scheduler import 0건) | 커밋 분리 + 순환 의존 차단 |

## AST-1 이 왜 필요한가

P0-1 결함의 시정은 "값을 흘리는 것" 인데, **가장 손쉬운 구현이 정확히 금지된 것**이다 —
`ticker_prices[t]["acml_vol"] = v` 한 줄이면 게이트가 즉시 살아난다. 그러나
`donchian_swing` 이 같은 dict 에서
`daily_high = max(stck_hgpr, high_price, current_price, open_price)` 를 읽어
`ext_pct` 과열 가드를 계산하므로, 키가 채워지면 **donchian 매수 행위가 바뀐다.**
이 가드는 그 지름길을 영구 차단한다.

## AST-2 는 이번 사이클에서 "의미 전환 예정" 표시가 붙은 가드다

Stage 0 은 배관·관측만 넣고 게이트를 건드리지 않는다. 1~2 영업일 실측 후
**게이트 전환 사이클**에서 이 가드를 의미 전환(pin 갱신)하는 것이 정상 경로다.
지금 이 가드가 실패하면 = Stage 0 범위를 벗어난 것이다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit

SRC = Path("src")


def _py_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


# ===========================================================================
# AST-1 — `ticker_prices` 에 `acml_vol` 대입 0건
# ===========================================================================

def _is_ticker_prices_subscript(node: ast.AST) -> bool:
    """`ticker_prices[...]` / `scanner.ticker_prices[...]` 인가."""
    if not isinstance(node, ast.Subscript):
        return False
    base = node.value
    if isinstance(base, ast.Name):
        return base.id == "ticker_prices"
    if isinstance(base, ast.Attribute):
        return base.attr == "ticker_prices"
    return False


def _dict_has_acml_vol_key(node: ast.AST) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    return any(
        isinstance(k, ast.Constant) and k.value == "acml_vol" for k in node.keys
    )


def _collect_acml_vol_writes(tree: ast.Module) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # (a) ticker_prices[t]["acml_vol"] = v
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for tgt in targets:
            if (
                isinstance(tgt, ast.Subscript)
                and isinstance(tgt.slice, ast.Constant)
                and tgt.slice.value == "acml_vol"
                and _is_ticker_prices_subscript(tgt.value)
            ):
                hits.append((node.lineno, 'ticker_prices[...]["acml_vol"] = ...'))
        # (b) ticker_prices[t] = {... "acml_vol": ...}
        if isinstance(node, ast.Assign) and _dict_has_acml_vol_key(node.value):
            for tgt in node.targets:
                if _is_ticker_prices_subscript(tgt):
                    hits.append((node.lineno, 'ticker_prices[...] = {"acml_vol": ...}'))
        # (c) ticker_prices[t].update({... "acml_vol": ...})
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("update", "setdefault")
            and _is_ticker_prices_subscript(node.func.value)
            and any(_dict_has_acml_vol_key(a) for a in node.args)
        ):
            hits.append((node.lineno, "ticker_prices[...].update({...acml_vol...})"))
    return hits


def test_AST1_no_acml_vol_assignment_into_ticker_prices():
    """AST-1 — `ticker_prices` 에 `acml_vol` 을 쓰는 코드가 전 소스에 0건.

    이 가드가 깨지면 donchian 의 `ext_pct` 과열 가드가 켜져 **매수 행위가 바뀐다**.
    관측값은 `tick_volume` 모듈에만 살아야 한다.
    """
    violations: list[str] = []
    for path in _py_files():
        try:
            tree = ast.parse(_read(path))
        except SyntaxError as exc:  # pragma: no cover - 소스 손상 방어
            pytest.fail(f"{path} SyntaxError: {exc}")
        for lineno, pattern in _collect_acml_vol_writes(tree):
            violations.append(f"{path}:{lineno} — {pattern}")

    assert not violations, (
        "`ticker_prices` 에 `acml_vol` 대입 발견 — donchian `ext_pct` 커플링으로 "
        "매수 행위가 바뀐다. 관측값은 `src/engine/tick_volume.py` 에만 둘 것:\n  "
        + "\n  ".join(violations)
    )


# ===========================================================================
# AST-2 — BFB·VCP 거래량 컷 블록 소스 pin (Stage 0 봉인)
# ===========================================================================

_BFB_GATE_BLOCK = """        # 거래량 컷
        from src.engine.scanner import ticker_prices
        info_price = ticker_prices.get(ticker, {})
        acml_vol = int(info_price.get("acml_vol", 0) or 0)
        vol_threshold = int(info["flag_avg_volume"] * self.config.params["breakout_volume_mult"])
        if acml_vol < vol_threshold:
            return Signal.NONE
"""

_VCP_GATE_BLOCK = """        # 거래량 컷
        from src.engine.scanner import ticker_prices
        info_price = ticker_prices.get(ticker, {})
        acml_vol = int(info_price.get("acml_vol", 0) or 0)
        avg20 = info.get("avg_volume_20", 0)
        vol_threshold = int(avg20 * self.config.params["breakout_volume_mult"])
        if vol_threshold > 0 and acml_vol < vol_threshold:
            return Signal.NONE
"""


@pytest.mark.parametrize(
    "path,block",
    [
        ("src/engine/strategies/bull_flag_breakout.py", _BFB_GATE_BLOCK),
        ("src/engine/strategies/vcp_breakout.py", _VCP_GATE_BLOCK),
    ],
    ids=["bfb", "vcp"],
)
def test_AST2_existing_volume_gate_block_is_byte_identical(path, block):
    """AST-2 — Stage 0 은 게이트를 **한 글자도** 바꾸지 않는다.

    관측 훅은 이 블록 **직전**에 삽입된다. 이 pin 이 깨지면 관측 사이클이
    행위 변경 사이클로 미끄러진 것이다 — 게이트 전환은 실측 1~2 영업일 후 별도 사이클.
    """
    src = _read(Path(path))
    assert src.count(block) == 1, (
        f"{path} 의 거래량 컷 블록이 pin 과 다르다 (일치 {src.count(block)}건). "
        "Stage 0 = 행위 변경 0. 게이트를 바꿨다면 이 가드를 **의미 전환**하는 별도 "
        "사이클이어야 한다."
    )


# ===========================================================================
# AST-3 — handler `len(fields) < 10` 가드 불변
# ===========================================================================

def test_AST3_handle_tick_field_guard_stays_at_ten():
    """AST-3 — 가드를 `< 14`/`< 15` 로 올리면 필드 10~14개 payload 가 통째 drop 된다.

    그 틱으로 돌던 **손절·트레일링이 조용히 죽는** 방향이라 매매 안전성 퇴행이다.
    `fields[13]` 은 가드를 올리는 대신 `try/except → -1 sentinel` 로 읽는다
    (`_parse_day_high` 선례).
    """
    tree = ast.parse(_read(Path("src/realtime/handler.py")))
    func = next(
        (
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_handle_tick"
        ),
        None,
    )
    assert func is not None, "`_handle_tick` 미발견"

    thresholds: list[int] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "len"
            and left.args
            and isinstance(left.args[0], ast.Name)
            and left.args[0].id == "fields"
        ):
            # drop 가드는 `len(fields) < N` 형태만이다.
            # (`fields[0] if len(fields) >= 1 else ...` 같은 방어 표현은 대상 아님)
            for op, cmp_node in zip(node.ops, node.comparators):
                if (
                    isinstance(op, ast.Lt)
                    and isinstance(cmp_node, ast.Constant)
                    and isinstance(cmp_node.value, int)
                ):
                    thresholds.append(cmp_node.value)

    assert thresholds == [10], (
        f"`_handle_tick` 의 `len(fields) <` 비교 상수가 {thresholds} 다. `[10]` 이어야 한다 — "
        "가드 상향은 정상 가격 틱을 drop 시켜 손절·트레일링을 죽인다"
    )


# ===========================================================================
# AST-4 — `tick_volume.py` 는 leaf
# ===========================================================================

_FORBIDDEN_IMPORT_SUBSTRINGS = (
    "src.engine.scheduler",
    "src.engine.risk",
    "src.engine.order_engine",
    "src.engine.scanner",
    "src.engine.session",
    "src.engine.strategy_registry",
    "src.realtime",
    "src.auth",
    "src.api.order",
    "src.db",
)


def test_AST4_tick_volume_is_leaf_module():
    """AST-4 — 관측 모듈은 8영역·scheduler 를 import 하지 않는다.

    날짜 키 자기 리셋 설계의 목적이 `scheduler.py` diff 0 (미커밋 cycle221 잔류와
    커밋 분리) 인데, import 로 결합되면 그 분리가 무의미해진다.
    `portfolio_risk.py` 순수 모듈 선례.
    """
    path = Path("src/engine/tick_volume.py")
    assert path.exists(), "`src/engine/tick_volume.py` 부재 (W3 미구현)"

    tree = ast.parse(_read(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)

    violations = [
        m for m in modules
        if any(m == f or m.startswith(f + ".") or m == f for f in _FORBIDDEN_IMPORT_SUBSTRINGS)
        or any(m.startswith(f) for f in _FORBIDDEN_IMPORT_SUBSTRINGS)
    ]
    assert not violations, (
        f"`tick_volume.py` 가 leaf 계약을 어겼다 — 금지 import: {violations}"
    )
