"""cycle324 — 정본이 「AI 매수평가는 VB·LTV 뿐」이라고 말하던 것 (코드는 7전략이었다).

## 무엇이 어긋나 있었나

cycle297(2026-09-17 `a61ded9`)이 나머지 5전략에 `"llm_gate_mode": "shadow"` 를 넣어
**7전략 전부**로 넓혔다. 사용자 결정 원문 = 「모든 전략에 걸어 데이터를 쌓고 전략별로 하나씩 enforce」.

그런데 그 커밋은 **명세 문서 2개만** 건드렸고 `README.md`·`docs/architecture.md` 는 손대지 않았다.
그래서 사흘 동안 정본이 —

| 문서 | 낡은 서술 |
|---|---|
| `README.md` ×5 | 「해당 없음 — `llm_buy_gate` 배선은 VB·LTV 두 전략뿐이다」 |
| `docs/architecture.md` §15.2 | 「켜져 있는 전략은 그 둘뿐이다 … 나머지 5 전략은 키 부재 = off」 |
| `docs/architecture.md` 도식 | 「llm_buy_gate (AI 매수평가 — VB·LTV 만)」 |

— 라고 말하고 있었다. 🔴 **저장소가 공개로 전환된 뒤라 틀린 설명이 그대로 읽힌다.**

## 왜 사람이 못 잡았나

`/sync-docs` 매핑 표는 이미 `src/engine/*` → `README.md`(전략 표) 를 적고 있었다.
즉 **규칙이 없어서가 아니라 그 사이클이 안 돌린 것**이다. 규칙은 사람이 건너뛴다.

## 이 파일이 지키는 계약

**코드가 진실이다.** `DEFAULT_PARAMS` 의 `llm_gate_mode` 를 세어, 정본이 그 수와
어긋나는 말을 하면 붉어진다. 전략이 늘거나 줄면 문서도 같이 움직여야 한다.

⚠️ 배선 자체는 **전략 무관**이다 — `order_engine` 의 호출부 2곳(주 경로·지정가 폴백)이
모든 전략을 같은 코드로 태우고, 갈리는 것은 `llm_gate_mode` 값 하나뿐이다
(`llm_buy_gate._read_mode`). 그래서 "어느 전략이 켜졌나"는 **파라미터 문제**이지 배선 문제가 아니다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_STRATEGY_DIR = _ROOT / "src/engine/strategies"

#: 정본 — 여기 적힌 수와 문서가 어긋나면 붉어진다.
_CANON_DOCS = ("README.md", "docs/architecture.md")

#: 「둘뿐이다」 계열. 🔴 **반드시 AI 매수평가 문맥 안에서만 본다.**
#: 초판은 문맥 없이 「두 전략」을 찾다가 `README.md` 의 15:20 강제 청산 행을 잡았다 —
#: 그건 실제로 VB·LTV 둘뿐이라 **사실이 맞는 줄**이고, 고치면 거짓이 된다.
#: (오늘 네 번째로 밟은 같은 함정 = 금지 패턴을 문맥 없이 찾으면 무관한 사실을 잡는다.)
_GATE_CONTEXT = ("llm_buy_gate", "llm_gate_mode", "AI 매수평가")
_STALE_PATTERNS = (
    r"두 전략뿐",
    r"VB·LTV 만",
    r"나머지 5\s*전략은 키 부재",
    r"켜져 있는 전략은 그 둘뿐",
)


def _strategies_with_gate() -> list[str]:
    """`DEFAULT_PARAMS` 에 `llm_gate_mode` 를 가진 전략 파일 목록."""
    out = []
    for p in sorted(_STRATEGY_DIR.glob("*.py")):
        if p.name.startswith("_") or p.name == "__init__.py":
            continue
        body = p.read_text(encoding="utf-8")
        if re.search(r'^\s+"llm_gate_mode":', body, re.M):
            out.append(p.stem)
    return out


def test_gate_is_wired_for_every_strategy() -> None:
    """모든 전략이 `llm_gate_mode` 를 갖는가 — 사용자 결정(「모든 전략에 걸어」)의 계약.

    막는 회귀 = 새 전략을 추가하면서 이 키를 빼먹는 것. 그러면 그 전략의 매수만
    조용히 기록에서 빠지고, 나중에 표본을 보는 사람이 그 사실을 모른다.
    """
    have = _strategies_with_gate()
    all_files = [
        p.stem for p in sorted(_STRATEGY_DIR.glob("*.py"))
        if not p.name.startswith("_") and p.name != "__init__.py"
    ]
    # 전략이 아닌 헬퍼 모듈이 섞일 수 있으므로 `DEFAULT_PARAMS` 를 가진 것만 전략으로 본다.
    strategies = [
        s for s in all_files
        if "DEFAULT_PARAMS" in (_STRATEGY_DIR / f"{s}.py").read_text(encoding="utf-8")
    ]
    missing = sorted(set(strategies) - set(have))
    assert not missing, (
        f"`llm_gate_mode` 가 없는 전략: {missing}\n"
        "  → 그 전략의 매수는 AI 매수평가 기록에서 조용히 빠진다.\n"
        "  사용자 결정(2026-09-17) = 「모든 전략에 걸어 데이터를 쌓고 전략별로 하나씩 enforce」"
    )
    assert len(strategies) >= 7, f"전략을 {len(strategies)}개만 찾았다 — 탐색이 헛돈다"


def test_canon_docs_do_not_claim_two_strategies_only() -> None:
    """정본이 「VB·LTV 둘뿐」이라고 말하지 않는가.

    막는 회귀 = 코드를 넓혀 놓고 정본을 안 고치는 것(cycle297 이 정확히 그랬다).
    🔴 저장소가 공개라 틀린 설명이 그대로 읽힌다.
    """
    n = len(_strategies_with_gate())
    if n < 3:
        pytest.skip(f"게이트가 {n}전략뿐이라 「둘뿐」 서술이 거짓이 아니다")

    offenders: list[str] = []
    for rel in _CANON_DOCS:
        path = _ROOT / rel
        assert path.is_file(), f"정본이 없다: {rel}"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # 문맥 게이트 — AI 매수평가 얘기인 줄에서만 「둘뿐」을 문제 삼는다
            if not any(k in line for k in _GATE_CONTEXT):
                continue
            for pat in _STALE_PATTERNS:
                if re.search(pat, line):
                    offenders.append(f"{rel}:{i} — {line.strip()[:110]}")

    assert not offenders, (
        f"코드는 {n}전략인데 정본이 「둘뿐」이라고 말한다:\n  " + "\n  ".join(offenders)
    )


def test_wiring_is_strategy_agnostic() -> None:
    """배선이 전략 무관인가 — 「어느 전략이 켜졌나」가 파라미터 문제라는 전제.

    막는 회귀 = `order_engine` 호출부에 전략 이름 분기를 넣는 것. 그러면 문서가 말하는
    「`llm_gate_mode` 하나로 갈린다」가 거짓이 되고, 이 파일의 다른 단언도 무의미해진다.
    """
    oe = (_ROOT / "src/engine/order_engine.py").read_text(encoding="utf-8")
    calls = [i for i, ln in enumerate(oe.splitlines(), 1) if "observe_order(" in ln]
    assert len(calls) == 2, (
        f"`observe_order` 호출이 {len(calls)}곳이다(기대 2 = 주 경로 · 지정가 폴백). "
        "늘거나 줄었으면 커버리지 전제가 바뀐 것이니 문서와 함께 재검토한다."
    )
    # 호출 줄 주변 6줄에 전략 이름 리터럴이 있으면 분기 의심
    lines = oe.splitlines()
    for c in calls:
        window = "\n".join(lines[max(0, c - 4): c + 3])
        for sid in ("volatility_breakout", "long_tail_volatility", "momentum"):
            assert f'"{sid}"' not in window, (
                f"observe_order 호출부({c}행) 근처에 전략 이름 리터럴 {sid} 가 있다 — "
                "배선이 전략별로 갈리면 문서 서술이 거짓이 된다"
            )
