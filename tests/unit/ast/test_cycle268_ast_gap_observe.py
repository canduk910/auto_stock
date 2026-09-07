"""cycle268 Red (AST) — `[kojiro_gap_observe]` 의 **구조적 계약** 봉인.

정본 명세 = `_workspace/specs/cycle268_kojiro_gap_observe.md` §6.2
자매 파일 = `tests/unit/engine/test_cycle268_kojiro_gap_observe.py`(leaf 행위) ·
            `tests/unit/engine/strategies/test_cycle268_kojiro_gap_behavior.py`(행위 보존)

**Red 단계 — 테스트만. `src/` 미변경.**

| # | 가드 | 지키는 것 | 수명 |
|---|---|---|---|
| G-266-1 | leaf 의 `src.*` import = `daily_emit_cap`·`observer_trace` + 함수-지역 `scanner` 뿐 | leaf 계약(순환·결합 차단) | 영구 |
| G-266-2 | leaf 에 `await`/`async def`/`pg.`/`kis_`/`create_task`/`fetch_stock_detail`/`write_log` 0건 | §3-3 hot path | 영구 |
| G-266-3 | `check_buy_signal` 안의 관측 호출이 **정확히 6개** ∧ 전부 **직접 호출**(`self.` 래퍼 0) | §3.1 `depth=2` 전제 | 영구 |
| G-266-4 | 6 호출이 전부 **바 statement**(반환값 미사용) | §2.2 "바 statement 삽입" | 영구 |
| G-266-5 | 6 verdict 의 **삽입 위치**(기존 로그 뒤 · `_bought_today.add` 앞 · 섹터캡 앞) | §2.2 표 | 영구 |
| G-266-6 | 기존 갭업/갭다운 스킵 로그 **byte 불변** | 과거 로그 대조 | 영구 |
| G-266-7 | kojiro `DEFAULT_PARAMS` 키 집합 불변 | 신규 키 금지 | 영구(값 변경 시 갱신) |
| G-266-8 | `check_buy_signal` 에 `await`/DB/HTTP 토큰 0건 | §3-3 | 영구 |
| G-266-9 | 마커·모듈명이 허용 파일 밖으로 새지 않는다 | 접촉 범위 | 영구 |
| G-266-10 | 킬스위치/모드 파라미터 신설 0 | 관측은 끄고 켜는 대상이 아니다 | 영구 |
| G-266-11 | `scheduler.py` < 3,900L ∧ cycle257 상한과 정합 | 라인 여유 3행 | 영구 |
| G-266-12 | leaf `observe_gap` 시그니처(`depth` kwonly 기본 2) + never-raise 골격 | §3.1 / §3-1 | 영구 |
| G-266-13 | leaf 는 read-only — 변형 메서드/대입 0건, 신규 cap 클래스 0 | §3-2 / cycle258 배관 | 영구 |
| G-266-14 | 8영역·`scheduler.py`·타 전략 6파일 워킹트리 diff 0 | 접촉 범위 | **⚠️ 사이클 한정** |

## 수명 판단 — 왜 sha 핀을 새로 만들지 않는가

리포 선례가 둘로 갈린다.

- **내용 sha 핀 dict**(`*_CONTENT_SHA`)는 **8영역 승인 사이클 전용**이고,
  `test_cycle223g3_ast_guard_sees_staged.py::test_g3_9a` 가 그 dict 를 가진 파일이
  **정확히 4개**임을 강제한다. cycle268 은 8영역을 한 글자도 만지지 않으므로 그
  기전에 편입될 사유가 없고, 편입하면 오히려 "핀은 항상 4곳" 목록을 깨뜨린다.
  ⇒ **이 파일은 `*_CONTENT_SHA` 이름의 모듈 레벨 dict 를 정의하지 않는다.**
- **메서드 세그먼트 sha 핀**(cycle264 `_STRATEGY_PINS`)은 VB/LTV 6 메서드를 이미
  덮고 있고 **아직 살아 있다**(cycle265 가 갱신·삭제 예정). 같은 성격의 핀을 나머지
  6 전략에 더 만들면 그 부채가 6개 늘고, 다음 전략 수정 사이클마다 "핀 재산출" 이
  본 작업을 가린다. cycle240 A11b·cycle252 G-252-5b 가 이미 "커밋 후 공허해지는
  가드를 영구로 두지 마라" 를 못박았다.

⇒ 이 사이클의 "타 전략 무접촉" 은 **① 마커/모듈명 containment(영구) + ② 워킹트리
diff 범위 가드(G-266-14, 사이클 한정)** 로 지킨다. G-266-14 는 **커밋 직후 삭제**한다
(cycle264 `test_c7_working_tree_touches_only_allowed_files` 선례 — 그 파일 헤더가
"커밋(38f2560) 직후 삭제 완료" 라고 적어 둔 바로 그 패턴).

## `ast.dump` sha 를 쓰지 않는 이유

파이썬 3.12(CI)/3.13(로컬) 출력이 달라 로컬 초록·CI 실패가 난다(cycle256 G-250-5 ·
cycle259 S4a). 소스 스캔에 `git grep`/`git ls-files` 도 쓰지 않는다 — 추적 파일만 보므로
Green 이 새로 만든 미추적 파일을 로컬에서 놓친다(cycle259 S4b). 전부 `Path.rglob` + AST 다.
(예외 = G-266-14 의 워킹트리 diff 판정 — git 없이는 정의되지 않는 질문이다.)
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"

LEAF_REL = "src/engine/kojiro_gap_observe.py"
KOJIRO_REL = "src/engine/strategies/kojiro.py"
LEAF = _ROOT / LEAF_REL
KOJIRO = _ROOT / KOJIRO_REL

OBSERVE_FN = "observe_gap"
RESET_FN = "reset_kojiro_gap_observe_cap"
MARKER = "[kojiro_gap_observe]"
MODULE_TOKEN = "kojiro_gap_observe"

VERDICTS = ("candidate", "no_data", "skip_up", "skip_down", "collapse", "pass")

# 명세 §2.2 — 기존 로그 두 줄은 byte 불변 (과거 로그 대조 유지)
GAP_UP_LOG = "고지로 갭업 스킵: %s 갭률 %.1f%% ≥ %.1f%%"
GAP_DOWN_LOG = "고지로 갭다운 스킵: %s 갭률 %.1f%% ≤ %.1f%%"

# 2026-09-07 HEAD 실측. 신규 키 금지 — 늘어나면 사용자 결정 사안이다.
KOJIRO_PARAM_KEYS = (
    "atr_period", "atr_ratio_max", "atr_ratio_min", "breakeven_promote_atr",
    "daily_loss_limit", "ema_long", "ema_mid", "ema_short", "exchange",
    "exclude_tickers", "gap_down_skip_pct", "gap_up_skip_pct", "hard_stop_pct",
    "macd_signal", "max_lot_ratio_mult", "max_lot_units", "max_open_risk_pct",
    "max_positions", "max_positions_per_sector", "max_scan_stocks",
    "max_units_per_stock", "max_units_total", "min_market_cap",
    "min_trade_amount", "min_vol_floor_pct", "nxt_tradable", "position_ratio",
    "rank_w_band", "rank_w_fresh", "rank_w_macd3", "risk_pct", "sizing_mode",
    "slope_lookback", "stage1_freshness", "stop_atr", "tradable_boards",
    "trail_atr",
)

BANNED_HOTPATH_TOKENS = ("pg.", "kis_", "create_task", "fetch_stock_detail",
                         "write_log", "supabase")


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _src(path: Path) -> str:
    assert path.exists(), (
        f"{path.relative_to(_ROOT)} 부재 — cycle268 Green 이 만들어야 하는 파일이다 "
        "(명세 §0 접촉 파일 표)"
    )
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> tuple[ast.Module, str]:
    src = _src(path)
    return ast.parse(src), src


def _find_func(node: ast.AST, name: str):
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _kojiro_class(tree: ast.Module) -> ast.ClassDef:
    cls = next((n for n in tree.body
                if isinstance(n, ast.ClassDef) and n.name == "KojiroStrategy"), None)
    assert cls is not None, "KojiroStrategy 클래스를 찾지 못했다"
    return cls


def _check_buy(tree: ast.Module) -> ast.FunctionDef:
    fn = _find_func(_kojiro_class(tree), "check_buy_signal")
    assert fn is not None, "KojiroStrategy.check_buy_signal 을 찾지 못했다"
    return fn


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _observe_calls(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call) and _call_name(n) == OBSERVE_FN]


def _verdict_of(call: ast.Call) -> str | None:
    """관측 호출의 verdict — 2번째 **위치 인자**(계약)."""
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        return call.args[1].value
    for kw in call.keywords:
        if kw.arg == "verdict" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def _observe_lines_by_verdict(fn: ast.AST) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in _observe_calls(fn):
        v = _verdict_of(c)
        if v is not None:
            out[v] = c.lineno
    return out


def _log_const_line(fn: ast.AST, text: str) -> int | None:
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and _call_name(n) in ("info", "warning", "debug"):
            for a in n.args:
                if isinstance(a, ast.Constant) and a.value == text:
                    return n.lineno
    return None


def _bought_today_add_lines(fn: ast.AST) -> list[int]:
    lines = []
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "add"
                and isinstance(n.func.value, ast.Attribute)
                and n.func.value.attr == "_bought_today"):
            lines.append(n.lineno)
    return sorted(lines)


# ===========================================================================
# G-266-1 — leaf import 계약
# ===========================================================================
def test_g268_1_leaf_src_imports_are_confined():
    tree, _ = _tree(LEAF)

    module_level, function_local = [], []
    func_nodes = [n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    local_ids = {id(n) for f in func_nodes for n in ast.walk(f)
                 if isinstance(n, (ast.Import, ast.ImportFrom))}

    for n in ast.walk(tree):
        if not isinstance(n, (ast.Import, ast.ImportFrom)):
            continue
        names = ([n.module] if isinstance(n, ast.ImportFrom) and n.module
                 else [a.name for a in n.names])
        for name in names:
            if not (name or "").startswith("src"):
                continue
            (function_local if id(n) in local_ids else module_level).append(name)

    assert sorted(set(module_level)) == [
        "src.engine.daily_emit_cap", "src.engine.observer_trace",
    ], (
        f"leaf 모듈 레벨 `src.*` import 실측 {sorted(set(module_level))} — "
        "cycle258 배관(`KstDailyEmitCap`·`trace_observer_failure`) 둘만 허용된다. "
        "새 방언을 만들지 마라"
    )
    assert set(function_local) <= {"src.engine.scanner"}, (
        f"leaf 함수-지역 `src.*` import 실측 {sorted(set(function_local))} — "
        "`scanner` 하나만 허용(donchian_swing:1626 선례). scheduler/registry/db 금지"
    )


def test_g268_1b_leaf_exposes_reset_hook():
    tree, _ = _tree(LEAF)
    assert _find_func(tree, RESET_FN) is not None, (
        f"`{RESET_FN}()` 부재 — cap 강제 초기화 훅은 테스트·운영의 단일 seam 이다 "
        "(cycle264 `reset_open_source_compare_cap` 선례)"
    )


# ===========================================================================
# G-266-2 — leaf hot path 금기
# ===========================================================================
def test_g268_2_leaf_has_no_async_or_io():
    tree, src = _tree(LEAF)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)], (
        "leaf 에 `async def` 금지 — `check_buy_signal` 은 동기 hot path 다"
    )
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Await)], (
        "leaf 에 `await` 금지"
    )
    hits = [t for t in BANNED_HOTPATH_TOKENS if t in src]
    assert hits == [], f"leaf 에 DB/HTTP/백그라운드 토큰이 있다: {hits}"


# ===========================================================================
# G-266-3 / G-266-4 — 호출 지점 6곳, 전부 직접 호출 · 바 statement
# ===========================================================================
def test_g268_3_six_direct_calls_in_check_buy_signal():
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    calls = _observe_calls(fn)
    assert len(calls) == 6, (
        f"`check_buy_signal` 안의 관측 호출 {len(calls)}개 — 명세 §2.2 는 **6곳**이다 "
        "(candidate/no_data/skip_up/skip_down/collapse/pass)"
    )
    self_wrapped = [c for c in calls
                    if isinstance(c.func, ast.Attribute)
                    and isinstance(c.func.value, ast.Name)
                    and c.func.value.id == "self"]
    assert self_wrapped == [], (
        "관측 호출이 `self.*` 래퍼 메서드를 경유한다 — 프레임이 하나 더 쌓여 "
        "`sys._getframe(depth=2)` 전제가 어긋나고 `caller` 가 통째로 거짓이 된다(§3.1)"
    )


def test_g268_3b_no_wrapper_method_calls_the_leaf():
    """kojiro 안에서 관측 함수를 부르는 곳은 `check_buy_signal` 하나뿐."""
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    inside = {id(c) for c in _observe_calls(fn)}
    # 비-공허성 — 기준선이 없으면 이 가드는 뮤테이션 전후 모두 통과한다(cycle224 교훈).
    assert len(inside) == 6, (
        f"`check_buy_signal` 안의 관측 호출 {len(inside)}개/6 — 기준선 부재"
    )
    outside = [c for c in _observe_calls(tree) if id(c) not in inside]
    assert outside == [], (
        f"`check_buy_signal` 밖에서 관측 함수를 부른다(라인 {[c.lineno for c in outside]}) — "
        "래퍼가 생기면 depth 전제가 깨진다"
    )


def test_g268_4_calls_are_bare_statements():
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    bare = [n for n in ast.walk(fn)
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
            and _call_name(n.value) == OBSERVE_FN]
    assert len(bare) == 6, (
        f"바 statement 관측 호출 {len(bare)}개/6 — 반환값을 쓰거나 조건에 넣으면 "
        "관측이 매매 판정의 입력이 된다(§3-1 '반환값은 항상 None')"
    )


def test_g268_4b_all_six_verdicts_present_and_unique():
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    got = sorted(_verdict_of(c) for c in _observe_calls(fn))
    assert got == sorted(VERDICTS), (
        f"verdict 리터럴 실측 {got} — 6종이 각각 정확히 한 번씩 쓰여야 한다"
    )


# ===========================================================================
# G-266-5 — 삽입 위치 (명세 §2.2 표)
# ===========================================================================
def test_g268_5_insertion_points_are_ordered_correctly():
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    at = _observe_lines_by_verdict(fn)
    missing = [v for v in VERDICTS if v not in at]
    assert not missing, f"verdict {missing} 호출 지점 부재"

    adds = _bought_today_add_lines(fn)
    assert len(adds) == 3, (
        f"`self._bought_today.add` 실측 {len(adds)}곳 — 갭업/갭다운/최종 3곳이 계약이다"
    )
    a_up, a_down, a_final = adds

    l_up = _log_const_line(fn, GAP_UP_LOG)
    l_down = _log_const_line(fn, GAP_DOWN_LOG)
    assert l_up and l_down, "기존 갭 스킵 로그를 찾지 못했다(G-266-6 참조)"

    assert l_up < at["skip_up"] < a_up, (
        f"skip_up 관측은 기존 로그({l_up}) **뒤**, `_bought_today.add`({a_up}) **앞** — "
        f"실측 {at['skip_up']}"
    )
    assert l_down < at["skip_down"] < a_down, (
        f"skip_down 관측 위치 위반 — 로그 {l_down} / 관측 {at['skip_down']} / add {a_down}"
    )
    assert a_down < at["collapse"] < a_final, (
        f"collapse 관측은 붕괴 분기 안(갭 블록 뒤, 최종 add 앞) — 실측 {at['collapse']}"
    )
    assert at["collapse"] < at["pass"] < a_final, (
        f"pass 관측은 붕괴 가드 통과 후 최종 `_bought_today.add`({a_final}) **앞** — "
        f"실측 {at['pass']}"
    )
    assert at["candidate"] < at["no_data"] < at["skip_up"], (
        "candidate 는 맨 앞, no_data 는 갭 게이트 else 자리다"
    )


def test_g268_5b_candidate_precedes_sector_cap_and_time_gate():
    """지점 1 = 섹터캡·시간창 판정 **전** — A/B 비율의 분모가 그 게이트에 먹히면 안 된다."""
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    at = _observe_lines_by_verdict(fn)
    assert "candidate" in at, "candidate 호출 지점 부재"

    sector_line = next(
        (n.lineno for n in ast.walk(fn)
         if isinstance(n, ast.Call)
         and any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                 and a.value.startswith("[kojiro_sector_cap]") for a in n.args)),
        None,
    )
    assert sector_line, "`[kojiro_sector_cap]` 로그를 찾지 못했다"
    assert at["candidate"] < sector_line, (
        f"candidate({at['candidate']}) 가 섹터캡 로그({sector_line}) 뒤로 밀렸다"
    )

    time_line = next(
        (n.lineno for n in ast.walk(fn)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and n.func.attr == "time"),
        None,
    )
    assert time_line, "시간창 게이트(`datetime.now(KST).time()`)를 찾지 못했다"
    assert at["candidate"] < time_line, (
        f"candidate({at['candidate']}) 가 시간창 게이트({time_line}) 뒤로 밀렸다"
    )


def test_g268_5c_no_data_lives_in_the_else_of_the_gap_gate():
    """지점 2 = `if open_price > 0 and prev_close > 0:` 의 **else**."""
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    hit = False
    for n in ast.walk(fn):
        if not isinstance(n, ast.If):
            continue
        test_src = ast.dump(n.test)
        if "open_price" not in test_src or "prev_close" not in test_src:
            continue
        for stmt in n.orelse:
            for c in _observe_calls(stmt):
                if _verdict_of(c) == "no_data":
                    hit = True
    assert hit, (
        "`no_data` 관측이 갭 게이트의 `else:` 블록 안에 없다 — "
        "'갭 게이트가 평가조차 안 됨' 코호트가 침묵으로 사라진다(§1 판독 표 5행)"
    )


# ===========================================================================
# G-268-15 — 호출 지점의 예외 흡수는 **무흔적 `pass` 가 아니다** (팀장 판정 ①)
# ===========================================================================
def test_g268_15_call_sites_absorb_with_a_trace_not_bare_pass():
    """6개 관측 호출을 감싼 `except` 가 흔적 함수를 부른다.

    무흔적 `pass` 는 cycle258 카드 #5 가 금지한 형태다 — 관측기가 죽어도 아무도
    모르게 되고, 그러면 이 마커의 **결측이 "오염이 없었다" 로 오독된다**
    (명세 §1 판독 표 5행).
    """
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)

    guarded = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        if not any(_observe_calls(st) for st in node.body):
            continue          # 관측 호출을 감싼 try 만 본다(기존 ATR 스탬프 try 제외)
        guarded.append(node)

    assert len(guarded) == 6, (
        f"관측 호출을 감싼 `try` {len(guarded)}개/6 — 6 지점 모두 방어돼야 한다"
    )
    for t in guarded:
        for h in t.handlers:
            assert isinstance(h.type, ast.Name) and h.type.id == "Exception", (
                f"라인 {h.lineno}: 흡수기가 `except Exception` 이 아니다 — "
                "핸들러를 좁히면 fail-open 계약이 뚫린다(cycle262 HIGH 선례)"
            )
            body_src = " ".join(ast.dump(st) for st in h.body)
            assert "absorb_call_failure" in body_src, (
                f"라인 {h.lineno}: 무흔적 `pass` — "
                "`absorb_call_failure(ticker)` 로 흔적을 남긴다(cycle258 카드 #5)"
            )


def test_g268_15b_absorber_is_a_direct_leaf_call():
    """흡수기도 leaf 의 공개 함수 **직접 호출**이다 — 전략 안에 방언을 만들지 않는다."""
    tree, src = _tree(KOJIRO)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and _call_name(n) == "absorb_call_failure"]
    assert len(calls) == 6, f"`absorb_call_failure` 호출 {len(calls)}개/6"
    wrapped = [c for c in calls
               if isinstance(c.func, ast.Attribute)
               and isinstance(c.func.value, ast.Name) and c.func.value.id == "self"]
    assert wrapped == [], "`self.*` 래퍼 경유 금지"
    assert "def absorb_call_failure" not in src, (
        "흡수기를 전략 파일에 재정의하지 마라 — leaf 단일 소유(cycle258 표준)"
    )


# ===========================================================================
# G-268-16 — 프로덕션은 cap 을 리셋하지 않는다 (팀장 판정 ②)
# ===========================================================================
def test_g268_16_production_never_resets_the_observation_cap():
    """`reset_kojiro_gap_observe_cap` 은 **테스트 전용 훅**이다.

    프로덕션에서 부르면 그날 cap 이 조용히 비워져 같은 종목이 재발화한다 —
    행 수의 신뢰성이 곧 이 사이클이 재려는 값이라 관측이 스스로를 오염시킨다.
    (`__init__` 에서 부르던 초안이 정확히 그 경로였다.)
    """
    offenders = {}
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        if rel == LEAF_REL:
            continue          # 정의부 자신
        if RESET_FN in path.read_text(encoding="utf-8"):
            offenders[rel] = RESET_FN
    assert not offenders, (
        f"프로덕션 코드가 관측 cap 을 리셋한다: {offenders}. "
        "테스트 격리는 테스트의 autouse fixture 로 한다"
    )


# ===========================================================================
# G-268-17 — `no_data` 그림자 분기의 조건 드리프트 차단
# ===========================================================================
def test_g268_17_no_data_shadow_condition_matches_the_real_gap_gate():
    """`no_data` 관측용 `if/else` 의 조건이 실제 갭 게이트 조건과 **문자 그대로 같다**.

    구현은 기존 갭 게이트 `if` 를 재배열하지 않으려고(명세 §2.2) 같은 조건의
    **그림자 `if/else`** 를 앞에 두는 형태를 골랐다. 그 대가로 조건이 두 벌이 되어
    한쪽만 수정되면 `no_data` 가 "갭 게이트가 실제로 돌았는데도" 발화하거나 그
    반대가 된다 — 매매는 멀쩡한데 **판독이 조용히 거짓이 되는** 결함이다.
    두 조건 트리를 같은 인터프리터 안에서 비교해 드리프트를 막는다.

    (⚠️ `ast.dump` 를 **핀 값으로 박지 않는다** — 3.12/3.13 출력이 달라 CI 만 붉어진다.
     같은 프로세스 안의 두 트리 **비교**는 그 문제와 무관하다.)
    """
    tree, _ = _tree(KOJIRO)
    fn = _check_buy(tree)
    gates = [n for n in ast.walk(fn)
             if isinstance(n, ast.If)
             and "open_price" in ast.dump(n.test) and "prev_close" in ast.dump(n.test)]
    assert len(gates) == 2, (
        f"`open_price`+`prev_close` 조건 `if` {len(gates)}개 — 그림자 1 + 실제 1 이 계약이다. "
        "구조가 바뀌었으면 이 가드를 함께 갱신하라"
    )
    a, b = sorted(gates, key=lambda n: n.lineno)
    assert ast.dump(a.test) == ast.dump(b.test), (
        "`no_data` 그림자 조건이 실제 갭 게이트 조건과 갈라졌다 — "
        f"그림자(L{a.lineno}) `{ast.unparse(a.test)}` vs "
        f"실제(L{b.lineno}) `{ast.unparse(b.test)}`. "
        "`no_data` 코호트 판정이 조용히 거짓이 된다"
    )
    assert any(_observe_calls(st) for st in a.orelse), (
        "그림자 `if` 의 `else` 에 `no_data` 관측이 없다"
    )
    assert all(isinstance(st, ast.Pass) for st in a.body), (
        "그림자 `if` 의 참 분기는 `pass` 뿐이어야 한다 — 행위가 들어가면 안 된다"
    )


# ===========================================================================
# G-266-6 / G-266-7 — 기존 로그 byte 불변 · DEFAULT_PARAMS 키 집합 불변
# ===========================================================================
@pytest.mark.parametrize("text", [GAP_UP_LOG, GAP_DOWN_LOG])
def test_g268_6_existing_skip_logs_are_byte_identical(text):
    src = _src(KOJIRO)
    assert src.count(f'"{text}"') == 1, (
        f"기존 스킵 로그 문자열이 바뀌었다: {text!r} — 과거 로그 대조가 끊긴다(§2.2)"
    )


def test_g268_7_default_params_key_set_unchanged():
    tree, _ = _tree(KOJIRO)
    cls = _kojiro_class(tree)
    node = next(
        (n.value for n in cls.body
         if isinstance(n, ast.Assign) and len(n.targets) == 1
         and isinstance(n.targets[0], ast.Name)
         and n.targets[0].id == "DEFAULT_PARAMS"),
        None,
    )
    assert isinstance(node, ast.Dict), "KojiroStrategy.DEFAULT_PARAMS dict 를 찾지 못했다"
    keys = tuple(sorted(k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)))
    assert keys == tuple(sorted(KOJIRO_PARAM_KEYS)), (
        "kojiro `DEFAULT_PARAMS` 키 집합 변경 — cycle268 은 관측 전용이라 신규 키가 "
        f"금지다(명세 §7). 추가분={sorted(set(keys) - set(KOJIRO_PARAM_KEYS))} "
        f"삭제분={sorted(set(KOJIRO_PARAM_KEYS) - set(keys))}"
    )


# ===========================================================================
# G-266-8 — check_buy_signal hot path 금기
# ===========================================================================
def test_g268_8_check_buy_signal_stays_sync_and_io_free():
    tree, src = _tree(KOJIRO)
    fn = _check_buy(tree)
    assert isinstance(fn, ast.FunctionDef), "`check_buy_signal` 이 async 가 됐다"
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    seg = ast.get_source_segment(src, fn) or ""
    hits = [t for t in BANNED_HOTPATH_TOKENS if t in seg]
    assert hits == [], f"`check_buy_signal` 에 DB/HTTP 토큰이 들어왔다: {hits}"


# ===========================================================================
# G-266-9 / G-266-10 — 접촉 범위 · 킬스위치 금지
# ===========================================================================
def test_g268_9_marker_and_module_confined():
    marker_files, module_files = [], []
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            marker_files.append(rel)
        if MODULE_TOKEN in text:
            module_files.append(rel)
    assert sorted(marker_files) == [LEAF_REL], (
        f"마커 `{MARKER}` 가 leaf 밖에 있다: {sorted(marker_files)} — "
        "서식은 leaf 단일 소유다"
    )
    assert sorted(module_files) == sorted([LEAF_REL, KOJIRO_REL]), (
        f"`{MODULE_TOKEN}` 참조 파일 실측 {sorted(module_files)} — "
        "명세 §0 접촉 파일은 정확히 2개다"
    )


def test_g268_10_no_killswitch_param_introduced():
    """관측은 끄고 켜는 대상이 아니다(cycle264 동형) + `DEFAULT_PARAMS` 신규 키 금지."""
    banned = ("kojiro_gap_observe_enabled", "gap_observe_enabled",
              "gap_observe_mode", "kojiro_gap_observe_secs")
    offenders: dict[str, list[str]] = {}
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        hits = [b for b in banned if b in text]
        if hits:
            offenders[path.relative_to(_ROOT).as_posix()] = hits
    assert not offenders, f"킬스위치/모드 파라미터 금지: {offenders}"


# ===========================================================================
# G-266-11 — scheduler.py 무접촉 (라인 여유 3행)
# ===========================================================================
def test_g268_11_scheduler_line_cap():
    lines = (_SRC / "engine" / "scheduler.py").read_text(encoding="utf-8").count("\n") + 1
    assert lines < 3900, (
        f"scheduler.py {lines}L — cycle257 영구 가드와 같은 예산(3,900L)을 넘었다. "
        "cycle268 은 scheduler 를 만지지 않는다(명세 §7)"
    )


def test_g268_11b_line_cap_matches_cycle257_guard():
    """느슨한 자체 가드가 위반을 초록으로 덮던 결함(cycle264 적대 검증 HIGH)의 재발 차단."""
    mine = Path(__file__).read_text(encoding="utf-8")
    theirs = (_ROOT / "tests" / "unit" / "ast"
              / "test_cycle257_ast_dead_code_removed.py").read_text(encoding="utf-8")
    caps_mine = {int(c) for c in re.findall(r"assert lines < (\d+)", mine)}
    caps_theirs = {int(c) for c in re.findall(r"assert count < (\d+)", theirs)}
    assert caps_mine, "cycle268 라인 상한 단언을 찾지 못했다"
    assert caps_theirs, "cycle257 라인 상한 단언을 찾지 못했다"
    assert min(caps_mine) <= min(caps_theirs), (
        f"cycle268 상한({sorted(caps_mine)})이 cycle257({sorted(caps_theirs)})보다 느슨하다"
    )


# ===========================================================================
# G-266-12 — leaf 시그니처 · never-raise 골격
# ===========================================================================
def test_g268_12_observe_gap_signature():
    tree, _ = _tree(LEAF)
    fn = _find_func(tree, OBSERVE_FN)
    assert fn is not None, f"leaf 에 `{OBSERVE_FN}` 정의가 없다"

    kwonly = [a.arg for a in fn.args.kwonlyargs]
    for required in ("arg_open", "prev_close", "current_price", "params", "depth"):
        assert required in kwonly, (
            f"`{OBSERVE_FN}` 키워드 전용 인자 `{required}` 부재 — 실측 {kwonly}"
        )
    assert [a.arg for a in fn.args.args][:2] == ["ticker", "verdict"], (
        "`ticker`, `verdict` 는 위치 인자 1·2 다(테스트·호출부 공통 계약)"
    )

    idx = kwonly.index("depth")
    default = fn.args.kw_defaults[idx]
    assert isinstance(default, ast.Constant) and default.value == 2, (
        "`depth` 기본값은 **2** 다 — leaf → `check_buy_signal` → 실제 호출자(§3.1)"
    )


def test_g268_12b_observe_gap_is_never_raise():
    tree, _ = _tree(LEAF)
    fn = _find_func(tree, OBSERVE_FN)
    assert fn is not None
    body = [n for n in fn.body if not isinstance(n, ast.Expr)
            or not isinstance(n.value, ast.Constant)]   # docstring 제외
    assert len(body) == 1 and isinstance(body[0], ast.Try), (
        "`observe_gap` 본체 전체가 하나의 `try` 여야 한다 — 어떤 실패도 "
        "`check_buy_signal` 로 새면 매매 행위가 바뀐다(§3-1)"
    )
    handlers = body[0].handlers
    assert any(isinstance(h.type, ast.Name) and h.type.id == "Exception"
               for h in handlers), (
        f"흡수기가 `except Exception` 이 아니다 — 실측 "
        f"{[ast.dump(h.type) if h.type else 'bare' for h in handlers]}. "
        "핸들러를 좁히는 뮤테이션이 fail-open 계약을 뚫는다(cycle262 HIGH 선례)"
    )
    assert any("trace_observer_failure" in ast.dump(h) for h in handlers), (
        "무흔적 `pass` 금지(cycle258 카드 #5) — "
        "`observer_trace.trace_observer_failure` 로 흔적을 남긴다"
    )


# ===========================================================================
# G-266-13 — leaf read-only · cycle258 배관 재사용
# ===========================================================================
def test_g268_13_leaf_reuses_kst_daily_emit_cap():
    tree, src = _tree(LEAF)
    assert "KstDailyEmitCap" in src, (
        "cap 은 `KstDailyEmitCap` 재사용이다 — 날짜 리셋 블록을 손으로 다시 쓰지 마라"
        "(cycle258 표준)"
    )
    new_caps = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert new_caps == [], f"leaf 에 신규 클래스 정의 금지 — 실측 {new_caps}"


def test_g268_13b_leaf_never_mutates_shared_state():
    """§3-2 — 어떤 dict 도 생성·변경하지 않는다(cycle242 G-242-8 동형)."""
    tree, _ = _tree(LEAF)
    mutators = {"add", "pop", "update", "clear", "setdefault", "discard",
                "append", "extend", "remove", "insert"}
    offenders = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in mutators:
                # cap 자신의 기록(mark_emitted/emit_once)은 관측기 내부 상태다.
                base = getattr(n.func.value, "id", "") or getattr(n.func.value, "attr", "")
                if "cap" not in str(base).lower():
                    offenders.append((n.lineno, n.func.attr, base))
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, (ast.Subscript, ast.Attribute)):
                    offenders.append((n.lineno, "assign", ast.dump(t)[:60]))
    assert offenders == [], (
        f"leaf 가 공유 상태를 변경한다: {offenders} — 관측기는 **읽기만** 한다"
    )


def test_g268_13c_leaf_does_not_touch_strategy_internals():
    src = _src(LEAF)
    banned = ("_bought_today", "_candidates", "_position_atr", "_position_sectors",
              "self.state", "buy_signals", "Signal.")
    hits = [b for b in banned if b in src]
    assert hits == [], (
        f"leaf 가 전략 내부 상태를 참조한다: {hits} — 관측이 판정의 입력이 되면 "
        "'행위 변경 0' 이 깨진다"
    )


# ===========================================================================
# G-266-14 — 워킹트리 접촉 범위 (⚠️ **사이클 한정 — cycle268 커밋 직후 삭제**)
# ===========================================================================
#
# bare `git diff HEAD` 는 커밋 뒤 공허해지고 그다음 편집에서 무조건 RED 가 된다
# (cycle240 A11b · cycle252 G-252-5b). 그래서 이 가드는 **영구가 아니다** —
# cycle268 커밋 직후 이 섹션(그리고 이 상수 블록)을 삭제한다.
# ---------------------------------------------------------------------------
CYCLE_SCOPED_DELETE_AFTER_COMMIT = (
    "test_g268_14_untouchable_files_have_zero_diff",
    "test_g268_14b_engine_scope_is_two_files",
)

_UNTOUCHABLE = (
    # 8영역 (CLAUDE.md 정본)
    "src/engine/risk.py", "src/engine/order_engine.py", "src/engine/session.py",
    "src/engine/scanner.py", "src/engine/strategy_registry.py", "src/api/order.py",
    "src/auth", "src/realtime",
    # 라인 상한 때문에 같은 승인 대상
    "src/engine/scheduler.py",
    # 나머지 전략 6파일
    "src/engine/strategies/momentum.py",
    "src/engine/strategies/volatility_breakout.py",
    "src/engine/strategies/long_tail_volatility.py",
    "src/engine/strategies/donchian_swing.py",
    "src/engine/strategies/bull_flag_breakout.py",
    "src/engine/strategies/vcp_breakout.py",
)


def test_g268_14_untouchable_files_have_zero_diff():
    """8영역 · `scheduler.py` · 타 전략 6파일 워킹트리 diff **0** (명세 §0)."""
    def _git(*args):
        return subprocess.run(["git", *args], cwd=_ROOT, capture_output=True,
                              text=True, check=True).stdout.split()

    changed = sorted(set(_git("diff", "HEAD", "--name-only", "--", *_UNTOUCHABLE))
                     | set(_git("ls-files", "--others", "--exclude-standard",
                                "--", *_UNTOUCHABLE)))
    assert changed == [], (
        f"cycle268 이 만지면 안 되는 파일이 바뀌었다: {changed}. "
        "접촉 허용은 `src/engine/kojiro_gap_observe.py` + "
        "`src/engine/strategies/kojiro.py` 둘뿐이다(명세 §0)"
    )


def test_g268_14b_engine_scope_is_two_files():
    """`src/engine/**` 안에서 바뀐 파일이 명세 §0 의 2개뿐이다.

    ⚠️ 스코프를 `src/` 전체가 아니라 `src/engine/` 으로 좁힌 이유 — 이 워킹트리는
    여러 에이전트가 공유한다(작성 시점 실측: 다른 작업이 `src/routes/stock_master.py`
    를 편집 중이었고 `src/` 전체 스코프가 그것을 cycle268 위반으로 잡았다). 8영역
    (`src/api/order.py`·`src/realtime/**`·`src/auth/**`)은 G-266-14 가 이미 파일
    단위로 지키므로 커버리지 손실은 없고, 오탐만 사라진다.
    """
    def _git(*args):
        return subprocess.run(["git", *args], cwd=_ROOT, capture_output=True,
                              text=True, check=True).stdout.split()

    changed = set(_git("diff", "HEAD", "--name-only", "--", "src/engine")) | set(
        _git("ls-files", "--others", "--exclude-standard", "--", "src/engine"))
    extra = sorted(changed - {LEAF_REL, KOJIRO_REL})
    assert extra == [], f"허용 범위 밖 `src/engine` 변경: {extra}"
