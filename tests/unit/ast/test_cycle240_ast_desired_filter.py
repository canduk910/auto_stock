"""cycle240 Red — AST 영구 가드: LOW desired 교집합의 **위치·범위·게이트** 봉인.

> 정본 스펙: `_workspace/red/cycle240_resubscribe_desired_filter_spec.md` §4.2
> 대상: `src/engine/stale_watcher_core.py`

행위 테스트(`tests/unit/engine/stale_manager/test_cycle240_resubscribe_desired_filter.py`)가
잡지 못하는 **구조**를 고정한다 — 필터가 throttle/cap 뒤로 밀리거나, HIGH 에도 걸리거나,
게이트에 momentum 이 끼어들거나, 헬퍼가 scheduler 를 정적 import 하는 회귀.

| ID | 검사 | 뮤테이션 표적 |
|----|------|--------------|
| G-240-1 | 본문 텍스트 index: 분리 < 필터 < 동시호가 < throttle < cap | 필터 위치 이동(m4) |
| G-240-2 | 분리 이후 `high_targets` 재대입 0 ∧ 필터 iter 는 `low_targets` 뿐 | HIGH 필터 적용(m2) |
| G-240-3 | 헬퍼: scheduler 정적 import 0 · `Await` 0 · `write_log` 0 · Try 하위 접근 | m8 / cycle63 D-1 / cycle72 |
| G-240-4 | 호출부가 `Try` 하위 | 예외 전파(m11) |
| G-240-5 | `_filter_active` = breakout ∧ high_ok (momentum 불참) | 게이트에 momentum 편입(m3) |
| G-240-6 | 종료 INFO 첫 인자 상수 prefix·첫 필드 보존 + 신규 필드 | prefix 변조(m7) |
| G-240-7 | HIGH 수집 3 except 각각 `_high_collect_ok = False` | 플래그 누락(m6) |

Red 시점: G-240-1 ~ G-240-7 **전부 FAIL** (필터 블록·헬퍼·플래그·로그 필드 전부 부재).

기존 가드는 재작성하지 않는다(중복) — G-17(cycle67) / GS-6(cycle215) / D-1·D-2(cycle63) /
G-6~G-13(cycle67) / G-8-B(cycle74) / cycle72 write_log / G218-6(cycle218) 는 표적 실행에
포함만 한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CORE = _REPO_ROOT / "src" / "engine" / "stale_watcher_core.py"

_FUNC = "resubscribe_stale_priority"
_HELPER = "_collect_low_desired"

_SPLIT_LINE = "low_targets = [t for t in stale_tickers if t not in high_tickers]"
_CALL_AUCTION = "is_call_auction_now("
_THROTTLE = "RESUBSCRIBE_THROTTLE_SECS"
_CAP = "max(0, cap - len(high_targets))"


def _tree() -> ast.Module:
    assert _CORE.exists(), f"{_CORE} 미존재"
    return ast.parse(_CORE.read_text(encoding="utf-8"))


def _find_func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _require_func(name: str):
    node = _find_func(_tree(), name)
    if node is None:
        pytest.fail(
            f"`{name}` 미정의 — cycle240 시정 의무 (스펙 §2.1/§2.2). 현행 부재 → Red."
        )
    return node


def _index(body: str, needle: str, label: str) -> int:
    i = body.find(needle)
    if i < 0:
        pytest.fail(f"본문에 {label} (`{needle}`) 부재 — cycle240 시정 미이행 → Red.")
    return i


# ===========================================================================
# G-240-1 — 순서 계약: 분리 → desired 필터 → 동시호가 → throttle → cap
# ===========================================================================
def test_g240_1_filter_between_split_and_call_auction():
    """필터는 high/low 분리 **직후**, cycle216 A/B 와 cap **앞** 이어야 한다.

    cap 이 "필터 통과분 LOW" 에만 적용되어야 유령이 cap 10 을 소비하지 못한다.
    필터를 throttle/cap 뒤로 옮기면 결함의 실비용(슬롯 잠식)이 그대로 남는다.
    """
    body = ast.unparse(_require_func(_FUNC))

    i_split = _index(body, _SPLIT_LINE, "low/high 분리 대입")
    i_filter = -1
    for line in body.splitlines():
        if "_desired_low" in line and " for " in line and " if " in line:
            i_filter = body.find(line.strip())
            break
    assert i_filter >= 0, (
        "`_desired_low` 를 참조하는 필터 comprehension 부재 — cycle240 시정 의무."
    )
    i_auction = _index(body, _CALL_AUCTION, "cycle216 A 동시호가 게이트")
    i_throttle = _index(body, _THROTTLE, "cycle216 B throttle")
    i_cap = _index(body, _CAP, "cap 슬라이스 (G-17)")

    assert i_split < i_filter < i_auction < i_throttle < i_cap, (
        "순서 계약 위반. 기대: 분리 → desired 필터 → 동시호가(A) → throttle(B) → cap. "
        f"실제 index: split={i_split} filter={i_filter} auction={i_auction} "
        f"throttle={i_throttle} cap={i_cap}"
    )


# ===========================================================================
# G-240-2 — HIGH 는 필터 경로를 지나지 않는다 (구조적 면제)
# ===========================================================================
def test_g240_2_high_targets_never_refiltered():
    """`high_targets` 는 분리 대입 이후 **재대입 0건** ∧ 필터 iter 는 `low_targets` 뿐.

    HIGH ⊆ desired 이므로 소스에 걸어도 결과는 같지만 "같다" 는 registry 정상일 때뿐이다.
    보유·익일청산 재구독 보장은 구조로 봉인한다(스펙 §3-1).
    """
    func = _require_func(_FUNC)
    body_src = ast.unparse(func)
    split_at = body_src.find(_SPLIT_LINE)
    assert split_at >= 0, "분리 대입 부재"

    reassigns = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "high_targets":
                    reassigns.append(ast.unparse(node))
    assert len(reassigns) == 1, (
        "`high_targets` 는 분리 대입 1회뿐 — 필터·throttle 어느 것도 HIGH 를 다시 "
        f"가공하지 않는다. 실제 대입: {reassigns}"
    )

    bad = []
    seen = 0
    for node in ast.walk(func):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            txt = ast.unparse(node)
            if "_desired_low" not in txt:
                continue
            seen += 1
            iters = {ast.unparse(g.iter) for g in node.generators}
            if iters != {"low_targets"}:
                bad.append((txt, sorted(iters)))
    assert seen >= 1, (
        "`_desired_low` 를 참조하는 필터 comprehension 부재 — 이 가드가 **공허하게** "
        "초록이 되는 것을 막는다 (cycle224 자기 가드 공허화 교훈). cycle240 시정 미이행 → Red."
    )
    assert bad == [], (
        "desired 필터의 iterable 은 `low_targets` 뿐이어야 한다 — `stale_tickers`(소스) 나 "
        f"`high_targets` 에 걸면 HIGH 가 잘린다. 실제: {bad}"
    )


# ===========================================================================
# G-240-3 — 헬퍼 순수성: scheduler 정적 import 0 · await 0 · write_log 0
# ===========================================================================
def test_g240_3_helper_is_pure_and_lazy():
    """`_collect_low_desired` = scheduler 인스턴스 메서드 호출 + scanner lazy read 뿐.

    - `from src.engine.scheduler import ...` 는 cycle63 D-1(순환 import) 위반.
    - `await` / DB / `write_log` 는 5분 hot path 에 들어가선 안 된다(cycle72).
    - `_last_scan_result` 접근은 반드시 `Try` 하위 (모듈 전역 read 실패 흡수).
    """
    helper = _require_func(_HELPER)
    txt = ast.unparse(helper)

    for node in ast.walk(helper):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "src.engine.scheduler", (
                "헬퍼가 scheduler 를 정적 import 하면 cycle63 D-1(의존 방향/순환) 위반. "
                f"실제: {ast.unparse(node)}"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "src.engine.scheduler" not in alias.name, (
                    f"scheduler 정적 import 금지. 실제: {ast.unparse(node)}"
                )

    assert not [n for n in ast.walk(helper) if isinstance(n, ast.Await)], (
        "헬퍼는 동기 순수 함수 — `await` 0건 (5분 hot path)."
    )
    assert "write_log" not in txt, (
        "cycle72 hotfix 영속 — `write_log` 직접 호출 금지 (logger → _DbLogHandler 위임)."
    )
    assert "_collect_breakout_tickers" in txt, (
        "breakout desired 는 `scheduler._collect_breakout_tickers()` 경유 의무 "
        "(`_universe_excluded_today` 제거 내장 — 전략 `get_scanned_tickers()` 직접 "
        "합산은 축출 종목을 되살린다)."
    )

    tries = [n for n in ast.walk(helper) if isinstance(n, ast.Try)]
    guarded = any("_last_scan_result" in ast.unparse(t) for t in tries)
    assert guarded, (
        "`scanner._last_scan_result` 접근은 `Try` 하위 의무 — 모듈 전역 read 실패가 "
        "재구독을 끊으면 안 된다."
    )
    guarded_breakout = any("_collect_breakout_tickers" in ast.unparse(t) for t in tries)
    assert guarded_breakout, (
        "`_collect_breakout_tickers()` 호출도 `Try` 하위 의무 (registry 미주입 인스턴스 보호)."
    )


# ===========================================================================
# G-240-4 — 호출부는 Try 하위 (관측 실패 ≠ 행위)
# ===========================================================================
def test_g240_4_helper_call_is_guarded():
    """`_collect_low_desired(` 호출이 `Try` 안에 있어야 한다.

    헬퍼가 던지면 게이트 off 로 폴백해야지, 재구독 루프를 끊어선 안 된다(cycle237 교훈).
    """
    func = _require_func(_FUNC)
    tries = [n for n in ast.walk(func) if isinstance(n, ast.Try)]
    assert any(f"{_HELPER}(" in ast.unparse(t) for t in tries), (
        f"`{_HELPER}(` 호출이 `Try` 하위가 아니다 — 관측기 자기 실패가 청산 감시 재구독을 "
        "끊는 경로가 열린다."
    )


# ===========================================================================
# G-240-5 — 활성 게이트는 breakout(소유 소스) ∧ HIGH 수집 성공. momentum 불참.
# ===========================================================================
def test_g240_5_gate_excludes_momentum():
    """`_filter_active` 값 표현식: `_breakout_desired` ∧ `_high_collect_ok`, `_momentum_desired` 부재.

    `scanner._last_scan_result` 는 **모듈 전역**이라 다른 테스트/런의 잔여값이 남는다.
    그것이 게이트를 켜면 기존 LOW 회귀가 수집 순서에 따라 깨진다(스펙 §1 정정 2).
    게이트는 scheduler **소유** 소스에만 건다.
    """
    func = _require_func(_FUNC)
    values = [
        node.value for node in ast.walk(func)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_filter_active" for t in node.targets)
    ]
    assert len(values) == 1, (
        f"`_filter_active` 대입 정확히 1건 의무. 실제: {len(values)}"
    )
    names = {n.id for n in ast.walk(values[0]) if isinstance(n, ast.Name)}
    assert "_breakout_desired" in names, (
        f"게이트는 breakout 소스를 근거로 한다. 실제 참조: {sorted(names)}"
    )
    assert "_high_collect_ok" in names, (
        "HIGH 수집 실패 시 필터 skip (이중 보호) — 플래그가 게이트에 포함되어야 한다. "
        f"실제 참조: {sorted(names)}"
    )
    assert "_momentum_desired" not in names, (
        "momentum 은 desired 에 **가산만** 하고 활성 판정에 참여하지 않는다. "
        f"실제 참조: {sorted(names)}"
    )


# ===========================================================================
# G-240-6 — 종료 INFO 서식: prefix + 첫 필드 byte 보존 + 신규 필드
# ===========================================================================
def test_g240_6_info_format_preserved_and_extended():
    """`[stale_priority_resubscribe] count=%d tickers=%s` 로 **시작** + `filtered_not_desired=%d` 포함.

    `test_scan_loop_stale_priority` 가 `"count=10" in log_text` 를 substring 단언하므로
    첫 필드 순서가 계약이다. 운영 grep 연속성도 같은 이유로 prefix 를 고정한다.
    """
    func = _require_func(_FUNC)
    fmts = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr == "info"):
            continue
        if not (isinstance(f.value, ast.Name) and f.value.id == "logger"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            fmts.append(node.args[0].value)
        elif node.args and isinstance(node.args[0], ast.JoinedStr):
            fmts.append("<f-string 금지>")

    target = [s for s in fmts if s.startswith("[stale_priority_resubscribe]")]
    assert target, (
        f"`[stale_priority_resubscribe]` INFO 서식 상수 부재. 실제 logger.info 서식: {fmts}"
    )
    fmt = target[0]
    assert fmt.startswith("[stale_priority_resubscribe] count=%d tickers=%s"), (
        "prefix + 첫 두 필드 byte 보존 의무 (필드 **추가**만 허용). "
        f"실제: {fmt!r}"
    )
    for field in ("desired_low=%d", "filtered_not_desired=%d", "filtered_sample=%s"):
        assert field in fmt, (
            f"신규 관측 필드 `{field}` 누락 — D+1 판독 채널이 성립하지 않는다. 실제: {fmt!r}"
        )


# ===========================================================================
# G-240-7 — HIGH 수집 3 except 분기 각각 `_high_collect_ok = False`
# ===========================================================================
def test_g240_7_high_collect_flag_set_in_every_except():
    """cycle66 try/except 4중 가드는 **구조 불변**, except 분기에 플래그만 추가한다.

    outer(`registry.all()`) / inner(`positions.keys()`) / NDC 세 곳 어디서 실패해도
    HIGH 가 LOW 로 오분류될 수 있다 → 그 상태의 필터는 보유 종목을 자를 수 있다.
    """
    func = _require_func(_FUNC)

    relevant = [
        n for n in ast.walk(func)
        if isinstance(n, ast.Try)
        and ("high_tickers.update" in ast.unparse(n) or "registry.all" in ast.unparse(n))
    ]
    assert len(relevant) == 3, (
        "cycle66 try/except 4중 가드 구조(outer / inner / NDC = Try 3) 불변 의무. "
        f"실제 Try 수: {len(relevant)}"
    )

    handlers = [h for t in relevant for h in t.handlers]
    assert len(handlers) == 3, f"except 분기 3개 의무. 실제: {len(handlers)}"
    missing = [
        ast.unparse(h) for h in handlers
        if "_high_collect_ok = False" not in ast.unparse(h)
    ]
    assert missing == [], (
        "HIGH 수집 실패를 삼키면 필터가 보유 종목을 자를 수 있다 — 모든 except 분기에서 "
        f"`_high_collect_ok = False` 의무. 누락: {missing}"
    )
