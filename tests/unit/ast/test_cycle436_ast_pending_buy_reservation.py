"""cycle436 카드 E — `pending_buy_amounts` 넣기·빼기 단일 진입점 AST 가드.

명세 = 사용자 지시(2026-10-10) — "pending_buy_amounts 의 넣기·빼기를 한 곳으로 모으고,
키를 (ticker, order_no) 로 바꾼다". 커밋 ① 은 **행위 0** — 키는 아직 `ticker` 다.

- **G1**: `src/**/*.py` 전체에서 `StrategyState` 가 정의된
  `src/engine/strategy_base.py` **밖**의 모든 파일에, `.pending_buy_amounts`
  속성 접근(AST `Attribute`, `attr == "pending_buy_amounts"`)이 0 건이어야 한다.
  읽기(합계)·쓰기(등록/해제/비우기) 전부 `StrategyState.reserve_buy` /
  `release_buy` / `clear_buy_reservations` / `total_pending_buy_amount` 메서드를
  거친다.
- **G2**: `StrategyState` 에 네 메서드가 모두 존재하고, `reserve_buy`/`release_buy`
  는 `order_no` 키워드를 받는다(커밋 ①은 무시하지만 시그니처는 고정해 둔다 —
  커밋 ②가 키를 `(ticker, order_no)` 로 바꿀 때 호출부를 또 고치지 않는다).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.engine.strategy_base import StrategyState

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_STATE_MODULE_REL = "src/engine/strategy_base.py"


def _iter_src_files():
    for p in sorted(_SRC.rglob("*.py")):
        rel = p.relative_to(_ROOT).as_posix()
        if rel == _STATE_MODULE_REL:
            continue
        yield rel, p


def test_g1_pending_buy_amounts_accessed_only_inside_strategy_state():
    offenders: list[str] = []
    for rel, path in _iter_src_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "pending_buy_amounts":
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        f"`pending_buy_amounts` 직접 접근 {offenders} — StrategyState 의 "
        "reserve_buy/release_buy/clear_buy_reservations/total_pending_buy_amount "
        "메서드를 거쳐야 한다(cycle436 카드 E)"
    )


def test_g2_strategy_state_has_the_four_methods():
    for name in ("reserve_buy", "release_buy", "clear_buy_reservations", "total_pending_buy_amount"):
        assert hasattr(StrategyState, name), f"StrategyState.{name} 없음"

    reserve_sig = inspect.signature(StrategyState.reserve_buy)
    assert list(reserve_sig.parameters) == ["self", "ticker", "order_no", "amount"], (
        f"reserve_buy 시그니처 {list(reserve_sig.parameters)} — "
        "(ticker, order_no, amount) 가 필요하다(커밋 ②의 키 변경 선행 고정)"
    )

    release_sig = inspect.signature(StrategyState.release_buy)
    assert list(release_sig.parameters) == ["self", "ticker", "order_no"], (
        f"release_buy 시그니처 {list(release_sig.parameters)} — "
        "(ticker, order_no=None) 가 필요하다"
    )
    assert release_sig.parameters["order_no"].default is None, (
        "release_buy 의 order_no 는 기본값 None — 종목 전체 해제(정산·종목 차단 해제 등)"
    )
