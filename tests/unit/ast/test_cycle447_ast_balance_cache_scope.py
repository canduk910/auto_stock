"""cycle447 제안 3 — `get_balance_cached()` 사용 범위 영구 가드.

매도/매수 직전 재대조(`order_engine.py` #1.5·D1 판정, `selling_reconcile.
reconcile_selling_unknown_one`)는 항상 `get_balance()` 를 직접 불러야 한다
— 20초 캐시된 값으로 "지금 진짜 잔고가 몇 주인가"를 판정하면 안 된다
(`_workspace/analysis/balance_5xx_20261011/result.md` 제안 3).

이 가드는 그 두 파일의 소스 텍스트에 `get_balance_cached` 토큰이 등장하지
않는지만 본다 — 새 호출부가 실수로 캐시 경로를 끌어오면 즉시 붉어진다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_FORBIDDEN_FILES = (
    "src/engine/order_engine.py",
    "src/engine/selling_reconcile.py",
)


@pytest.mark.parametrize("rel_path", _FORBIDDEN_FILES)
def test_sell_path_reconciliation_never_uses_cached_balance(rel_path: str):
    text = (_ROOT / rel_path).read_text(encoding="utf-8")
    assert "get_balance_cached" not in text, (
        f"{rel_path} 가 `get_balance_cached` 를 참조한다 — 매도 직전 재대조는 "
        "항상 실제 `get_balance()` 를 직접 불러야 한다(제안 3 금기)"
    )
