"""cycle233 R11 — 계좌 리스크 패키지 구조 봉인 (AST/소스 정적 가드).

봉인 목록:
- G-1: 7전략 `check_buy_signal` 본문에 `_account_soft_gate_blocked` 호출 존재
  (신규 전략 추가 시 배선 누락 영구 차단 — 자문 안 1-C-β AST 의무).
- G-2: 8영역 파일에 `account_risk` 토큰 0 (8영역 diff 0 의 정적 절반).
- G-3: `account_risk_guard.py` = 순수 leaf — src 내부 import 금지
  (portfolio_risk/turtle_sizing/tick_volume 선례).
- G-4: `account_risk_watcher.py` 에 `buy_disabled` 토큰 0 — D1 이원화 봉인
  (감시자가 risk.py 일일손실 세팅을 지우는 회귀의 구조적 차단).
- G-5: `strategy_base.py` 의 watcher import 는 함수-레벨(lazy) — 순환 import 차단.
- G-6: `scheduler._api_recovered_collector_loop` 에 감시 호출 존재 (5분 주기 배선).
- G-7: `boot_manager.py` 에 `run_account_risk_watch_once` 호출 존재 (부팅 창 봉합 —
  자문 §2.5-γ 반례 2 요구사항. 제거 뮤테이션 검출).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"

# 게이트 위치 규약 (적대 검증 C233-F1):
# - 폴/래치형 5전략 = check_buy_signal **첫 문장**(baseline 상태가 없어 최상단 안전)
# - edge-crossing 2전략(momentum/VB) = **발사 직전**(baseline 갱신 뒤) — 최상단이면
#   block 구간 동안 baseline 동결 → 해제 후 첫 틱 거짓 돌파(추격 상한 없는 매수)
GATE_FIRST_FILES = [
    "long_tail_volatility.py", "donchian_swing.py",
    "bull_flag_breakout.py", "vcp_breakout.py", "kojiro.py",
]
GATE_PRE_BUY_FILES = ["momentum.py", "volatility_breakout.py"]
STRATEGY_FILES = GATE_FIRST_FILES + GATE_PRE_BUY_FILES

EIGHT_AREAS = [
    SRC / "engine" / "risk.py",
    SRC / "engine" / "order_engine.py",
    SRC / "engine" / "session.py",
    SRC / "engine" / "scanner.py",
    SRC / "engine" / "strategy_registry.py",
    SRC / "api" / "order.py",
]
EIGHT_AREA_DIRS = [SRC / "realtime", SRC / "auth"]


def _check_buy_fn(path: Path) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "check_buy_signal":
            return node
    raise AssertionError(f"{path.name}: check_buy_signal 부재")


def _is_gate_if(node: ast.stmt) -> bool:
    """게이트 If — `if self._account_soft_gate_blocked(...): return Signal.NONE`.

    Call 이 **If.test 안**에 있고 body 가 `return Signal.NONE` 단독이어야 한다 —
    bare call(결과 버림)·미호출 참조 뮤테이션이 통과하던 공허성(적대 검증 F3) 봉인.
    """
    if not isinstance(node, ast.If):
        return False
    test_calls = [
        c for c in ast.walk(node.test)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
        and c.func.attr == "_account_soft_gate_blocked"
    ]
    if not test_calls:
        return False
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
        return False
    ret = ast.dump(node.body[0])
    return "NONE" in ret and "Signal" in ret


def _stmt_blocks(fn: ast.FunctionDef):
    for node in ast.walk(fn):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block:
                yield block


class TestG1SevenStrategyWiring:
    def test_gate_first_strategies_have_gate_as_first_statement(self):
        for fname in GATE_FIRST_FILES:
            fn = _check_buy_fn(SRC / "engine" / "strategies" / fname)
            body = list(fn.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)):
                body = body[1:]  # docstring 제외
            assert body and _is_gate_if(body[0]), (
                f"{fname}: 게이트 If 가 check_buy_signal 첫 문장이 아님 — "
                "부작용/상태 갱신 앞 배치가 계약 (cycle233 M6)"
            )

    def test_edge_crossing_strategies_gate_before_buy_return(self):
        """momentum/VB — 게이트는 baseline 갱신 **뒤**, BUY 발사 **직전** (C233-F1).

        🔁 2026-09-11 (cycle274) — `buy_idx` 판정이 직접 `Return(BUY)` 뿐 아니라
        **"모든 분기가 `Return(BUY)` 로 귀결되는 `Try` 문"** 도 인정하도록 넓어졌다.
        VB 가 cycle274 LLM 게이트 관측 호출부의 예외를 `try/except` 로 흡수하면서
        (`llm_buy_gate.observe_signal(...)` 이 monkeypatch 로 터져도 `Signal.BUY`
        가 동일해야 한다는 별도 계약, C2) `return Signal.BUY` 가 이 블록의 **직접**
        원소가 아니라 그 try/except 의 두 분기(try 본문 끝·except 핸들러 끝) 안에
        중첩된다 — 원래의 직접-일치 검사는 이 정당한 구조 변화에도 항상 실패한다.
        ⚠️ **넓히는 폭을 최소로 잡았다** — `ast.walk(s)` 로 하위 트리 전체를
        재귀 탐색하면(1차 시도, 폐기) momentum.py 에서 무관한 블록의 무관한
        중첩 반환까지 조기 매치돼 `break` 를 먼저 태워 **오탐 회귀**를 냈다
        (그 블록엔 게이트가 없어 `ok=False`). 그래서 "Try 문 자신이 **모든**
        분기에서 BUY 로 끝난다" 는 좁은 조건만 추가했다 — 임의의 중첩 반환이
        아니라 정확히 이 사이클이 만든 패턴(try/except 양쪽 다 같은 반환으로
        수렴)만 인정한다. momentum.py 처럼 직접 `Return(BUY)` 인 기존 케이스는
        그대로 잡힌다(엄격한 상위집합).

        🔁 2026-09-11 (cycle274 검증 라운드2 파인딩 #7) — `orelse`/`finalbody`
        를 판정에 넣었다. 종전 판정은 `Try.body` 와 `handlers` 만 봐서
        `try: ... except: return BUY else: return Signal.NONE` 같은 구조가
        (정상 완주 시 `orelse` 만 실행되고 그 경로가 NONE 을 반환하는데도)
        `try.body` 가 애초에 Return 으로 안 끝나 판정 자체가 False 로 빠지며
        이 가드를 그냥 통과했다 — 게이트의 실제 불변식(BUY 발사보다 게이트가
        먼저 평가된다)을 넓힌 판정이 놓칠 수 있는 사각이었다. `finally` 안에
        Return 이 있으면 흐름이 거기로 흡수될 수 있어 판정 자체를 거부한다.
        VB/LTV 의 현재 구조는 `else`/`finally` 를 쓰지 않으므로 이 강화는
        기존 케이스에 영향이 없다(상한집합 그대로).
        """
        def _try_all_branches_return_buy(node: ast.stmt) -> bool:
            if not isinstance(node, ast.Try):
                return False
            if any(isinstance(n, ast.Return) for s in node.finalbody for n in ast.walk(s)):
                return False
            branches = [node.body] + [h.body for h in node.handlers]
            if node.orelse:
                branches.append(node.orelse)
            if not branches:
                return False
            return all(
                b and isinstance(b[-1], ast.Return) and b[-1].value is not None
                and "BUY" in ast.dump(b[-1].value)
                for b in branches
            )

        for fname in GATE_PRE_BUY_FILES:
            fn = _check_buy_fn(SRC / "engine" / "strategies" / fname)
            ok = False
            for block in _stmt_blocks(fn):
                buy_idx = [
                    i for i, s in enumerate(block)
                    if (isinstance(s, ast.Return) and s.value is not None
                        and "BUY" in ast.dump(s.value))
                    or _try_all_branches_return_buy(s)
                ]
                if not buy_idx:
                    continue
                gate_idx = [i for i, s in enumerate(block) if _is_gate_if(s)]
                ok = bool(gate_idx) and min(gate_idx) < min(buy_idx)
                break
            assert ok, (
                f"{fname}: `return Signal.BUY` 와 같은 블록의 그 앞에 게이트 If 부재 "
                "— 발사 직전 게이트가 계약 (baseline 동결 금지, C233-F1)"
            )
            # 최상단(첫 문장) 게이트 금지 — baseline 동결 재발 방지
            body = list(fn.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)):
                body = body[1:]
            assert not (body and _is_gate_if(body[0])), (
                f"{fname}: edge-crossing 전략의 최상단 게이트 금지 (C233-F1 — "
                "block 구간 baseline 동결 → 해제 후 거짓 돌파)"
            )


class TestG2EightAreasUntouched:
    def test_no_account_risk_token_in_eight_areas(self):
        offenders = []
        files = list(EIGHT_AREAS)
        for d in EIGHT_AREA_DIRS:
            files.extend(d.rglob("*.py"))
        for f in files:
            if "account_risk" in f.read_text(encoding="utf-8"):
                offenders.append(str(f))
        assert not offenders, f"8영역에 account_risk 참조: {offenders}"


class TestG3GuardLeafPurity:
    def test_guard_has_no_src_imports(self):
        path = SRC / "engine" / "account_risk_guard.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                bad.extend(a.name for a in node.names if a.name.startswith("src."))
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").startswith("src."):
                    bad.append(node.module)
        assert not bad, f"순수 leaf 계약 위반 import: {bad}"


class TestG4WatcherNeverTouchesBuyDisabled:
    def test_no_buy_disabled_token(self):
        path = SRC / "engine" / "account_risk_watcher.py"
        assert "buy_disabled" not in path.read_text(encoding="utf-8"), (
            "D1 이원화 위반 — Σ 순간 게이트는 buy_disabled 를 절대 만지지 않는다"
        )


class TestG5LazyImportInStrategyBase:
    def test_watcher_import_is_function_level(self):
        path = SRC / "engine" / "strategy_base.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # 모듈 최상위만 검사
            if isinstance(node, ast.ImportFrom) and "account_risk_watcher" in (node.module or ""):
                raise AssertionError("strategy_base 최상위에서 watcher import — lazy 필수")
            if isinstance(node, ast.Import):
                assert not any("account_risk_watcher" in a.name for a in node.names)


class TestG6PeriodicWiring:
    """주기 배선 = watcher 자기 종료 루프 (scheduler 라인 상한 가드 존중 — scheduler diff 0).

    루프는 `_running` 감시로 자연 종료(≤60s)하므로 cancel 목록/task_attrs 미등록이
    설계다. 스폰은 `ensure_watch_loop` 단일 지점 + 중복 스폰 가드.
    """

    def test_watcher_has_self_terminating_loop(self):
        """구조 검사 — docstring 문자열이 검사를 공허화하지 못하게(적대 검증 F2)
        While/If 의 **test 노드만** 본다 (전체 dump 문자열 검색 금지)."""
        path = SRC / "engine" / "account_risk_watcher.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        loop_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "watch_loop":
                loop_fn = node
        assert loop_fn is not None, "watch_loop 부재 — 주기 평가 배선 소멸"
        # 최상위 문장 중 While 존재 (if 로 강등 = 주기 반복 소멸 뮤테이션 검출)
        top_while = next(
            (s for s in loop_fn.body if isinstance(s, ast.While)), None)
        assert top_while is not None, "while 부재 — 5분 주기 반복(순간 게이트 전제) 소멸"
        assert "_running" in ast.dump(top_while.test), (
            "while 조건에 _running 부재 — 좀비 루프 (자기 종료 계약)"
        )
        assert any(
            isinstance(c, ast.Call) and "run_account_risk_watch_once" in ast.dump(c)
            for c in ast.walk(top_while)
        ), "루프 본문에 평가 호출 부재"
        # sleep 조각 내 _running 탈출 검사 (stop 후 ≤60s 종료 계약)
        inner_exit = [
            n for n in ast.walk(top_while)
            if isinstance(n, ast.If) and "_running" in ast.dump(n.test)
        ]
        assert inner_exit, "sleep 조각 내 _running 탈출 검사 부재 — 최대 300s 지연 종료"

    def test_scheduler_untouched(self):
        """scheduler.py 에 watcher 참조 0 — 라인 상한 가드(<4,000L) 보호 설계."""
        path = SRC / "engine" / "scheduler.py"
        assert "account_risk" not in path.read_text(encoding="utf-8")


class TestG7BootSyncWiring:
    def test_boot_manager_calls_watch_once(self):
        path = SRC / "engine" / "boot_manager.py"
        text = path.read_text(encoding="utf-8")
        assert "run_account_risk_watch_once" in text, (
            "부팅 동기 1회 평가 부재 — 07:55 부팅 ~ 첫 주기(5분) 사이 "
            "09:05 매수창이 무방비로 열린다 (자문 §2.5-γ 반례 2)"
        )
        assert "ensure_watch_loop" in text, (
            "감시 루프 스폰 부재 — 부팅 1회 평가만으로는 장중 Σ 변화를 못 본다"
        )
