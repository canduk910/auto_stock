"""cycle254 Red (AST) — ρ캡 조기탈출 축소의 구조 계약 봉인.

명세 `_workspace/specs/cycle254_ratio_cap_min_composition.md` §3(G-254-1/2/3) · §4.
행위 테스트로는 잡히지 않는 **구조**만 정적으로 고정한다.

- G-254-1  `strategy_base.py` 에 `"backstop"` 0건 — 라벨 상수(`cap_state`)와
           그 라벨을 정의·인용하는 docstring/주석 전부. `min` 합성 후 ρ축은
           "K축이 fail-open 할 때만 받는 백스톱" 이 아니라 **상시 후심사** 이므로
           `backstop` 은 거짓 라벨이고, D+1 판독(`cap=on`)과 R7 자기검증 규칙이
           그 문자열에 매여 있다(명세 §6 ⚠️ 의미 전환).
- G-254-2  `_apply_ratio_notional_cap` 안에서 `governs` 를 **단독 조건**으로 쓰는
           분기가 0건이고, `gov_reason == "probe_error"` 비교가 `BoolOp(And)` 안에
           존재한다. 뮤테이션 "조기탈출 복원"(`governs and gov_reason == ...`
           → `governs`)을 행위(F-9a)와 구조 양쪽에서 막는다.
- G-254-3  `_lot_units_cap_governs(` 호출이 그 함수 안에 **존재**한다
           (G-245-4 와 중복이지만 삭제 뮤테이션 검출을 이 파일에도 분산).

헬퍼는 cycle242/245 AST 가드 관례대로 **로컬 복제**한다(타 테스트 모듈 import 금지).
"""

from __future__ import annotations

import ast
import re
import inspect
from pathlib import Path

import pytest

from src.engine.strategy_base import StrategyBase

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SB = _ROOT / "src" / "engine" / "strategy_base.py"

RHO_CAP = "_apply_ratio_notional_cap"
GOVERNS = "_lot_units_cap_governs"
DEAD_LABEL = "backstop"


# ---------------------------------------------------------------------------
# 헬퍼 (로컬 복제)
# ---------------------------------------------------------------------------
def _sb_source() -> str:
    return inspect.getsource(StrategyBase)


def _func_node(source: str, name: str) -> ast.AST:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 함수를 찾지 못했습니다 (cycle254 미구현 또는 개명)")


def _calls_named(fn: ast.AST, name: str) -> list[ast.Call]:
    hits = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if fname == name:
                hits.append(node)
    return hits


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


# ---------------------------------------------------------------------------
# G-254-1 — 죽은 라벨 `"backstop"` 0건
# ---------------------------------------------------------------------------
def test_g254_1a_no_backstop_string_constant():
    """`cap_state = "backstop"` 분기가 남아 있으면 D+1 서명 1·2 가 오판된다.

    (뮤테이션 표적 4 — `cap_state = "on"` → `"backstop"` 복원)
    """
    tree = ast.parse(_SB.read_text(encoding="utf-8"))
    hits = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and DEAD_LABEL in n.value
    ]
    assert not hits, (
        f'`"{DEAD_LABEL}"` 문자열 상수가 {len(hits)} 개 남아 있습니다 '
        f"(줄 {[n.lineno for n in hits]}) — cycle254 는 라벨을 off/on 2 종으로 "
        "통일합니다(`k is None` 이면 off, 그 외 on)"
    )


def test_g254_1b_no_backstop_token_in_source():
    """주석·docstring 까지 포함해 0건 — 계약 문안이 코드와 어긋난 채 남지 않게.

    특히 `_emit_oversized_fallback` docstring 의 R7 자기검증 문단은 `cap=backstop`
    행을 **정상**으로 분류한다. `min` 합성 후 그 분류는 반대로 뒤집히므로
    (명세 §6 ⚠️) 문장을 남겨 두면 운영자가 캡 우회를 정상으로 읽는다.
    """
    src = _SB.read_text(encoding="utf-8")
    # 단어 경계로 잰다 — `turtle_backstop_pct`(하드손절 파라미터명, 전략 7파일·
    # portfolio_risk 의 정식 키)가 훗날 공통 헬퍼로 이 파일에 올라와도 오탐하지 않는다.
    # 표적은 ρ캡 라벨 `cap=backstop` / `"backstop"` 리터럴의 부활이다.
    token = re.compile(r"(?<!\w)" + re.escape(DEAD_LABEL) + r"(?!\w)")
    lines = [
        (i, line.strip())
        for i, line in enumerate(src.splitlines(), start=1)
        if token.search(line)
    ]
    assert not lines, (
        f"`{DEAD_LABEL}` 토큰이 {len(lines)} 줄 남아 있습니다: "
        f"{[i for i, _ in lines]} — 라벨 상수 + docstring(라벨 표 · R7 자기검증 · "
        "판정기 설명)을 명세 §5 대로 함께 개정하세요"
    )


# ---------------------------------------------------------------------------
# G-254-2 — `governs` 단독 조기탈출 0건 + `probe_error` 는 And 안
# ---------------------------------------------------------------------------
def test_g254_2a_no_bare_governs_early_exit():
    """`if governs:` (또는 `gov_reason` 을 안 보는 어떤 분기든) = 결정 ⑦ 회귀.

    cycle245 는 이 분기 하나로 K축 심사 랏 전체를 ρ축 밖에 두었고, 그 결과가
    F-9(터틀 1주 폴백 = 전략 예산 100% 랏)였다. cycle254 이후 `governs` 는
    **`probe_error` 판정에만** 쓰인다.
    """
    fn = _func_node(_sb_source(), RHO_CAP)
    offenders = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If)
        and "governs" in _names_in(n.test)
        and "gov_reason" not in _names_in(n.test)
    ]
    assert not offenders, (
        f"{RHO_CAP} 안에 `governs` 를 단독 조건으로 쓰는 분기가 "
        f"{len(offenders)} 개 있습니다 — K축 심사 랏이 ρ축을 통째로 우회합니다"
        "(결정 ⑦ 회귀)"
    )


def test_g254_2b_probe_error_guard_is_a_conjunction():
    """`if governs and gov_reason == "probe_error": … return` 구조를 핀한다.

    - `and` 가 아니라 별도 중첩 `if` 로 되돌리면(HEAD 형태) 첫 단언이 붉어진다.
    - `==` → `!=` 뮤테이션(fail-closed 반전)은 F-9d 가 행위로도 잡지만
      비교 연산자를 구조로도 고정한다.
    """
    fn = _func_node(_sb_source(), RHO_CAP)
    guards = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.BoolOp):
            continue
        if not isinstance(node.test.op, ast.And):
            continue
        names = _names_in(node.test)
        if "governs" not in names or "gov_reason" not in names:
            continue
        cmps = [
            c for c in ast.walk(node.test)
            if isinstance(c, ast.Compare)
            and isinstance(c.left, ast.Name) and c.left.id == "gov_reason"
            and any(isinstance(x, ast.Constant) and x.value == "probe_error"
                    for x in c.comparators)
        ]
        if cmps:
            guards.append((node, cmps))

    assert guards, (
        f"{RHO_CAP} 안에 `governs and gov_reason == \"probe_error\"` 형태의 "
        "fail-open 관문이 없습니다 — 조기탈출을 블록째 지우면 F-10d(판정기 내부 "
        "예외 fail-open) 계약이 사라집니다"
    )
    node, cmps = guards[0]
    ops = {type(op).__name__ for c in cmps for op in c.ops}
    assert ops == {"Eq"}, (
        f"`gov_reason` 비교 연산자가 {ops} — `==` 만 허용됩니다"
        "(`!=` 는 판정 실패 랏을 차단하는 fail-closed 반전)"
    )
    assert any(isinstance(n, ast.Return) for n in ast.walk(node)), (
        "fail-open 관문이 조기 반환하지 않습니다 — `probe_error` 랏이 계속 진행하면 "
        "판정 불가 상태에서 ρ캡이 적용됩니다"
    )


# ---------------------------------------------------------------------------
# G-254-3 — 판정기 호출 존치 (삭제 뮤테이션 검출 분산)
# ---------------------------------------------------------------------------
def test_g254_3_governs_probe_call_survives():
    """`_lot_units_cap_governs` 호출이 사라지면 `probe_error` fail-open 도 사라진다.

    G-245-4 와 중복이지만 의도적이다 — 뮤테이션 5(호출 삭제)를 두 파일이 각각 잡는다.
    """
    fn = _func_node(_sb_source(), RHO_CAP)
    assert _calls_named(fn, GOVERNS), (
        f"{RHO_CAP} 이 {GOVERNS} 를 호출하지 않습니다 — cycle254 는 이 호출을 "
        "**남긴다**(판정 실패 fail-open 이 F-10d 계약)"
    )


# ---------------------------------------------------------------------------
# G-254-4 — 정본 문서 2파일(`src/engine/CLAUDE.md`·`src/engine/strategies/CLAUDE.md`)의
# 구 결정 ⑦("상호배타"/`cap=backstop`) 잔존 가드. 워크리스트(`_workspace/`)는 살아
# 있는 작업 문서라 영구 가드 대상에서 뺐다(메인 세션 결정, 4c/4e/4f 삭제 — 범용
# 구절 '행은 정상이다' 검사는 무관한 문단에서 오탐한다).
#
# cycle254 검증(적대 리뷰)이 확증한 발견 2건 — `src/engine/strategy_base.py` 는
# 이미 개정됐지만(backstop 0건, G-254-1a/b) 그 코드가 실제로 진실인 것을 서술
# 해야 할 하위 CLAUDE.md 2파일 + 워크리스트 D+1 판독 표가 개정 대상에서 빠져
# 구 결정 ⑦("상호배타 — min 합성 없음" · `cap=backstop` 은 정상/기대값)을 그대로
# 서술하고 있었다. 코드 결함은 아니지만(strategy_base.py backstop 0건), 이 문서가
# 어긋난 채 남으면 (a) 다음 사이클이 이 문단을 근거로 조기탈출을 복원하는 회귀를
# 저지르거나 (b) 월 09-07 D+1 판독자가 정상 배포(`cap=on`)를 "배치 오류"로 오판
# 하거나 R7 자기검증에서 터틀 행을 제외해 캡 우회를 놓칠 수 있다.
# ---------------------------------------------------------------------------
_ENGINE_MD = _ROOT / "src" / "engine" / "CLAUDE.md"
_STRATEGIES_MD = _ROOT / "src" / "engine" / "strategies" / "CLAUDE.md"


def test_g254_4a_engine_claude_md_has_no_exclusive_cap_claim():
    """하위 CLAUDE.md(진실의 원천)가 구 결정 ⑦ 을 현행 계약으로 서술하면
    다음 사이클이 뮤테이션 M1(조기탈출 복원) 형태로 회귀할 수 있다.

    `cycle254` 토큰이 같은 줄에 있으면 "폐기됐다"는 이력 서술로 간주해 허용한다
    (예: strategy_base.py docstring "구 결정 ⑦ '상호배타' 폐기(cycle254)").
    """
    text = _ENGINE_MD.read_text(encoding="utf-8")
    stale = [
        i for i, line in enumerate(text.splitlines(), 1)
        if "상호배타" in line and "min" in line and "cycle254" not in line
    ]
    assert not stale, (
        f"src/engine/CLAUDE.md {stale} 줄이 '두 캡 상호배타' 를 현행 계약으로 "
        "서술합니다 — cycle254 이후 K축 심사 랏도 ρ축이 `min` 으로 후심사하도록 개정하세요"
    )


def test_g254_4b_engine_claude_md_has_no_silent_pass_claim():
    """"심사 조건이 전부 참이면 ρ축은 조용히 통과한다" 는 cycle254 이후 거짓이다
    (그 경우도 `min` 합성으로 후심사한다 — 실효는 1주 폴백 랏뿐)."""
    text = _ENGINE_MD.read_text(encoding="utf-8")
    assert "ρ축은 조용히 통과한다" not in text, (
        "src/engine/CLAUDE.md 가 K축 심사 랏이 ρ축을 조용히 통과한다고 서술합니다 — "
        "cycle254 는 그 랏도 `min` 으로 후심사합니다(항등식 무접촉일 뿐 통과 자체는 "
        "ρ축을 거칩니다)"
    )



def test_g254_4d_strategies_claude_md_has_no_fail_open_only_claim():
    """"donchian·kojiro 는 `cap=backstop` 이라 K축 fail-open 시에만 …" 는
    cycle254 이후 거짓이다 — 1주 폴백 랏에는 **상시** 적용된다."""
    text = _STRATEGIES_MD.read_text(encoding="utf-8")
    assert "fail-open 시에만" not in text, (
        "src/engine/strategies/CLAUDE.md 가 ρ축 캡을 'K축 fail-open 시에만' "
        "적용된다고 서술합니다 — cycle254 이후 1주 폴백 랏엔 상시 적용됩니다"
    )
    assert "cap=backstop" not in text, (
        "src/engine/strategies/CLAUDE.md 에 폐기된 `cap=backstop` 라벨이 "
        "남아 있습니다(cycle254 이후 라벨은 off/on 2종뿐)"
    )

