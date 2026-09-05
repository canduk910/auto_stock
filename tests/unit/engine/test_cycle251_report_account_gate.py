"""cycle251 Red — 20:10 리포트 스냅샷에 계좌 SOFT 게이트 관측 부착 (후속 G).

명세: `spec_cycle251_account_gate_observability.md` §1(G) · §2(T1~T5 · g251_1~g251_3).

## 왜 이 테스트가 필요한가

cycle233 SOFT Σ상한 **활성화 게이트(AND)** 의 한 축이 "장중 `age_secs <= 600`"
실측이다. 지금 그 값을 보는 유일한 채널은 `/api/portfolio/risk` 를 curl 로 찌르는
것뿐이고, 20:10 일일 리포트에는 아예 안 실린다 — 그래서 (a) OpenAI 프롬프트
(b) `daily_log_reports.metrics` JSONB (c) 20:20 Claude 루틴의 번들 어디에도
"그날 게이트가 신선했나 / 몇 번 타임아웃 났나"의 기록이 없다. cycle250 D+1
(`[account_risk_eval_timeout]` 0건 확인)도 같은 채널로 읽는다.

## 이 파일이 못박는 계약

- T1: `snapshot["account_gate"]` = `get_gate_state()` 8키 **+ `eval_timeouts_today`**,
      그리고 **원본 dict 의 복사본**(`is not`) — 스냅샷이 watcher 내부 상태를
      들고 있으면 metrics 직렬화 시점에 값이 바뀌거나 반대로 스냅샷을 통해
      내부가 오염된다.
- T2: `get_gate_state` 예외 → 키 **미부착** + 나머지 스냅샷 온전 + 예외 전파 0.
      (관측 부착 실패가 리포트 전체를 죽이면 안 된다 — 사이클 88 G-REJECT 동형)
- T3: `compute_over_cap_positions` 예외와 **독립**(두 try 블록이 별개).
- T4: **무발화** — `is_soft_gated()` 호출 0회 ∧ `_emit_cap` 불변(사이클 258 —
      `_emit_day` 는 `KstDailyEmitCap` 내부로 흡수돼 소멸, `_emit_cap._emitted`
      비교로 동일한 의도를 검증한다).
      `is_soft_gated()` 는 stale 시 `gate_stale` cap 을 소비하는 **쓰기 경로**다.
      리포트 빌더가 그걸 부르면 그날 장중 진짜 hang 이 났을 때 WARNING 이
      무음이 된다(cycle233 F1 / cycle239 R1 이 이미 한 번 고친 결함의 재현).
- T5: `collect_daily_log_metrics` 통합 — `metrics["portfolio_risk_snapshot"]
      ["account_gate"]["eval_timeouts_today"]` 가 실제 번들에 실린다.
- g251_1/2/3: 구조 봉인 (AST/텍스트).

RED 상태(구현 전): T1/T3/T5 는 `"account_gate"` 키 부재로 FAIL, T2/T4 는
현행에서도 통과(영구 가드), g251_1/g251_3 FAIL, g251_2 는 무접촉이라 통과.
"""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.engine import account_risk_watcher as arw
from src.engine import log_analysis_engine as lae

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
LAE_SRC = ROOT / "src" / "engine" / "log_analysis_engine.py"
WATCHER_SRC = ROOT / "src" / "engine" / "account_risk_watcher.py"
WATCHER_REL = "src/engine/account_risk_watcher.py"
CARD_TSX = ROOT / "frontend" / "src" / "components" / "PortfolioRiskCard.tsx"

_BUILDER = "_build_portfolio_risk_snapshot"

#: `get_gate_state()` 가 돌려주는 키 집합 (cycle239 4키 + 원 4키).
GATE_KEYS = {
    "level",
    "reasons",
    "open_risk_pct",
    "evaluated_at",
    "age_secs",
    "stale",
    "stale_max_secs",
    "effective_gated",
}


# ===========================================================================
# 픽스처 — `_build_portfolio_risk_snapshot` 의 하위 의존만 대역
# ===========================================================================
@pytest.fixture
def snapshot_deps(monkeypatch):
    """빌더의 lazy import 대상(잔고/registry/섹터)만 결정론 대역으로 바꾼다.

    `compute_portfolio_risk_snapshot` / `extract_hard_stop_pct` / 게이트 접근자는
    **실물 그대로** — 이 사이클이 검증하는 배선이 그 사이에 있다.
    """
    import src.api.balance as balance_mod
    import src.engine.sector_naming as sector_mod
    from src.engine.scheduler import trading_scheduler

    async def _fake_get_balance():
        return ([], SimpleNamespace(net_asset=100_000_000))

    async def _fake_resolve(_tickers):
        return {}

    fake_registry = SimpleNamespace(all=lambda: [])

    monkeypatch.setattr(balance_mod, "get_balance", _fake_get_balance)
    monkeypatch.setattr(sector_mod, "resolve_sector_names", _fake_resolve)
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)

    arw.reset_state_for_test()
    yield
    arw.reset_state_for_test()


def _gate_payload() -> dict:
    """`get_gate_state()` 형태의 고정 페이로드 (8키)."""
    return {
        "level": "warn",
        "reasons": ["open_risk_pct=5.10 >= warn_pct=5.00"],
        "open_risk_pct": 5.10,
        "evaluated_at": "2026-09-07T10:30:00+09:00",
        "age_secs": 42,
        "stale": False,
        "stale_max_secs": 900,
        "effective_gated": False,
    }


# ===========================================================================
# T1 — 정상: 8키 + eval_timeouts_today, 그리고 원본의 **복사본**
# ===========================================================================
async def test_t1_snapshot_when_gate_state_available_then_carries_eight_keys_plus_timeouts(
    snapshot_deps, monkeypatch
):
    origin = _gate_payload()  # 매 호출 같은 객체를 돌려준다 → 복사 여부 판별 가능
    monkeypatch.setattr(arw, "get_gate_state", lambda: origin)
    monkeypatch.setattr(arw, "_eval_timeout_count", lambda: 3)

    snapshot = await lae._build_portfolio_risk_snapshot()

    assert snapshot is not None
    assert "account_gate" in snapshot, (
        "Red — 스냅샷에 `account_gate` 키 미부착 (cycle251 후속 G 미구현)"
    )
    gate = snapshot["account_gate"]
    assert isinstance(gate, dict)

    missing = GATE_KEYS - set(gate)
    assert not missing, f"`get_gate_state()` 키 누락: {sorted(missing)}"
    for key, expected in origin.items():
        assert gate[key] == expected, f"{key} 값 불일치: {gate[key]!r} != {expected!r}"

    assert "eval_timeouts_today" in gate, (
        "cycle250 `_eval_timeout_count()` 병기 누락 — '몇 번 멈췄나'가 리포트에서 사라진다"
    )
    assert gate["eval_timeouts_today"] == 3
    assert isinstance(gate["eval_timeouts_today"], int)
    assert not isinstance(gate["eval_timeouts_today"], bool)

    assert gate is not origin, (
        "watcher 가 돌려준 dict 를 그대로 실었다 — 스냅샷은 **복사본**이어야 한다"
        "(`dict(get_gate_state())`). 같은 객체면 metrics 직렬화 전에 값이 바뀌거나 "
        "반대로 스냅샷을 통해 내부 상태가 오염된다."
    )
    # 원본 무변경 (부착이 watcher 상태를 건드리지 않는다)
    assert "eval_timeouts_today" not in origin


# ===========================================================================
# T2 — graceful: get_gate_state 예외 → 키 미부착 + 나머지 보존 + 전파 0
# ===========================================================================
async def test_t2_snapshot_when_gate_state_raises_then_key_absent_and_report_survives(
    snapshot_deps, monkeypatch
):
    def _boom():
        raise RuntimeError("watcher 일시 장애")

    monkeypatch.setattr(arw, "get_gate_state", _boom)

    snapshot = await lae._build_portfolio_risk_snapshot()  # 예외 전파 0

    assert snapshot is not None
    assert "account_gate" not in snapshot, (
        "게이트 조회 실패 시 키를 부착하면 안 된다 — 부분/거짓 값이 리포트에 실린다"
    )
    # 나머지 스냅샷은 온전
    for key in (
        "total_notional_won",
        "total_open_risk_won",
        "open_risk_pct_of_net",
        "concurrent_positions",
        "by_strategy",
        "by_sector",
        "top_sector",
        "over_cap_positions",
    ):
        assert key in snapshot, f"게이트 실패가 기존 키 `{key}` 를 삼켰다"


async def test_t2b_snapshot_when_eval_timeout_count_raises_then_key_absent(
    snapshot_deps, monkeypatch
):
    """cycle250 접근자 쪽이 던져도 같은 graceful 계약 (부분 dict 부착 금지)."""
    monkeypatch.setattr(arw, "get_gate_state", lambda: _gate_payload())

    def _boom():
        raise RuntimeError("counter 장애")

    monkeypatch.setattr(arw, "_eval_timeout_count", _boom)

    snapshot = await lae._build_portfolio_risk_snapshot()

    assert snapshot is not None
    assert "account_gate" not in snapshot or "eval_timeouts_today" in snapshot["account_gate"], (
        "`eval_timeouts_today` 없는 반쪽 dict 부착 금지 — 키가 있으면 항상 완전해야 한다"
    )
    assert "over_cap_positions" in snapshot


# ===========================================================================
# T3 — 순서/독립: over_cap 이 죽어도 account_gate 는 붙는다
# ===========================================================================
async def test_t3_snapshot_when_over_cap_raises_then_account_gate_still_attached(
    snapshot_deps, monkeypatch
):
    import src.engine.portfolio_risk as pr_mod

    def _boom(_strategies):
        raise RuntimeError("over_cap 계산 장애")

    monkeypatch.setattr(pr_mod, "compute_over_cap_positions", _boom)
    monkeypatch.setattr(arw, "get_gate_state", lambda: _gate_payload())
    monkeypatch.setattr(arw, "_eval_timeout_count", lambda: 0)

    snapshot = await lae._build_portfolio_risk_snapshot()

    assert snapshot is not None
    assert "over_cap_positions" not in snapshot, "over_cap 은 실패했으므로 미부착이 정상"
    assert "account_gate" in snapshot, (
        "두 관측이 같은 try 에 묶여 있다 — over_cap 실패가 게이트 관측까지 삼켰다 "
        "(§1 G: `over_cap_positions` try **다음**의 **별도** try)"
    )
    assert snapshot["account_gate"]["level"] == "warn"


# ===========================================================================
# T4 — 무발화: is_soft_gated 미호출 ∧ cap 상태 불변
# ===========================================================================
async def test_t4a_snapshot_when_built_then_is_soft_gated_never_called(
    snapshot_deps, monkeypatch
):
    spy = MagicMock(return_value=False)
    monkeypatch.setattr(arw, "is_soft_gated", spy)
    monkeypatch.setattr(arw, "get_gate_state", lambda: _gate_payload())
    monkeypatch.setattr(arw, "_eval_timeout_count", lambda: 0)

    await lae._build_portfolio_risk_snapshot()

    assert spy.call_count == 0, (
        "리포트 빌더가 `is_soft_gated()` 를 불렀다 — stale 이면 `gate_stale` cap 을 "
        "**선소비**해 그날 장중 진짜 hang 의 WARNING 이 무음이 된다 "
        "(cycle233 F1 / cycle239 R1 동형). 읽기 전용 `get_gate_state()` 만 쓴다."
    )


async def test_t4b_snapshot_when_gate_stale_then_emit_cap_untouched(snapshot_deps):
    """실물 접근자로 stale 상태를 만들어 cap 소비 여부를 직접 관측한다.

    `_gate_active=True` ∧ `_evaluated_mono=None` → `is_soft_gated()` 를 부르면
    `_emit_stale_release` 가 `gate_stale` 키를 소비한다. 빌더 호출 후에도
    비어 있으면 그 경로를 안 밟은 것이다(사이클 258 — 날짜 필드는
    `KstDailyEmitCap` 내부로 흡수돼 `_emit_cap._emitted` 비교만으로 충분하다).
    """
    arw._gate_active = True
    arw._evaluated_mono = None
    before_emitted = set(arw._emit_cap._emitted)
    assert before_emitted == set()

    snapshot = await lae._build_portfolio_risk_snapshot()

    assert snapshot is not None
    assert set(arw._emit_cap._emitted) == before_emitted, (
        f"`_emit_cap` 이 소비됐다 ({sorted(arw._emit_cap._emitted)}) — 관측 read 경로가 "
        "쓰기 경로(`is_soft_gated`)를 탔다"
    )
    # stale 이라도 `level` 은 마지막 평가값 보존 (동결 서명 — cycle239 계약)
    if "account_gate" in snapshot:
        assert snapshot["account_gate"]["stale"] is True
        assert snapshot["account_gate"]["effective_gated"] is False


# ===========================================================================
# T5 — 통합: collect_daily_log_metrics 번들에 실린다
# ===========================================================================
@pytest.fixture
def collect_deps(monkeypatch, snapshot_deps):
    """`collect_daily_log_metrics` 의 로그/거래 수집만 대역 — 스냅샷 빌더는 실물."""

    async def _fetch(start, end, limit=None):
        return []

    async def _high(start, end, *a, **k):
        return []

    async def _count(start, end):
        return {"WARNING": 0, "ERROR": 0, "CRITICAL": 0}

    async def _trades(d1, d2):
        return []

    async def _funnel():
        return {}

    async def _stages(_target_date):
        return {}

    monkeypatch.setattr(lae, "_fetch_logs_in_range", _fetch)
    monkeypatch.setattr(lae, "_fetch_high_severity_logs", _high)
    monkeypatch.setattr(lae, "_count_logs_by_level", _count)
    monkeypatch.setattr(lae, "get_trades_in_range", _trades)
    monkeypatch.setattr(lae, "get_request_metrics", lambda: {"total": 0})
    monkeypatch.setattr(lae, "_collect_strategy_funnel", _funnel)
    monkeypatch.setattr(lae, "_collect_strategy_funnel_stages", _stages)


async def test_t5_collect_metrics_when_built_then_bundle_carries_eval_timeouts_today(
    collect_deps,
):
    metrics = await lae.collect_daily_log_metrics(date(2026, 9, 4))

    snapshot = metrics.get("portfolio_risk_snapshot")
    assert snapshot is not None, "스냅샷 빌드 실패 — 하위 대역 누락"
    assert "account_gate" in snapshot, (
        "Red — 20:10 번들(`metrics.portfolio_risk_snapshot`)에 `account_gate` 미부착. "
        "이 dict 가 그대로 OpenAI 프롬프트 · daily_log_reports.metrics JSONB · "
        "20:20 Claude 루틴 번들이다."
    )
    gate = snapshot["account_gate"]
    assert "eval_timeouts_today" in gate
    assert isinstance(gate["eval_timeouts_today"], int)
    assert not (GATE_KEYS - set(gate)), f"8키 누락: {sorted(GATE_KEYS - set(gate))}"


# ===========================================================================
# g251_1 (AST) — 별도 try 블록 ∧ 읽기 전용 접근자만
# ===========================================================================
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _fn(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 부재")


def _call_count(node: ast.AST, name: str) -> int:
    """`name(...)` / `mod.name(...)` **정확 일치** 호출 수."""
    count = 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        if isinstance(fn, ast.Name) and fn.id == name:
            count += 1
        elif isinstance(fn, ast.Attribute) and fn.attr == name:
            count += 1
    return count


def _assigns_subscript_key(node: ast.AST, key: str) -> bool:
    """`x["key"] = ...` 대입이 이 서브트리에 있는가."""
    for sub in ast.walk(node):
        targets = []
        if isinstance(sub, ast.Assign):
            targets = sub.targets
        elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
            targets = [sub.target]
        for tgt in targets:
            if (
                isinstance(tgt, ast.Subscript)
                and isinstance(tgt.slice, ast.Constant)
                and tgt.slice.value == key
            ):
                return True
    return False


def _body_without_docstring(fn) -> list[ast.stmt]:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body


def test_g251_1a_builder_never_references_is_soft_gated():
    fn = _fn(_tree(LAE_SRC), _BUILDER)
    code = "\n".join(ast.unparse(stmt) for stmt in _body_without_docstring(fn))
    assert "is_soft_gated" not in code, (
        "`_build_portfolio_risk_snapshot` 본문에 `is_soft_gated` 식별자 — 그 함수는 "
        "stale 시 `gate_stale` cap 을 소비하는 **쓰기 경로**다. 관측은 무발화 "
        "`get_gate_state()` 만 쓴다 (설명은 docstring 에)."
    )


def test_g251_1b_builder_calls_read_only_accessors_exactly_once():
    fn = _fn(_tree(LAE_SRC), _BUILDER)
    got_state = _call_count(fn, "get_gate_state")
    got_count = _call_count(fn, "_eval_timeout_count")
    assert got_state == 1, f"`get_gate_state()` 호출이 정확히 1회여야 한다 (실측 {got_state})"
    assert got_count == 1, (
        f"`_eval_timeout_count()` 호출이 정확히 1회여야 한다 (실측 {got_count}) — "
        "cycle250 카운터 병기가 명세 §1 G 의 값 정의다"
    )


def test_g251_1c_gate_block_is_a_separate_try_from_over_cap():
    fn = _fn(_tree(LAE_SRC), _BUILDER)
    tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try)]
    assert tries, "빌더에 try 블록이 없다"

    gate_tries = [t for t in tries if _call_count(t, "get_gate_state") > 0]
    over_tries = [t for t in tries if _assigns_subscript_key(t, "over_cap_positions")]

    assert len(gate_tries) == 1, (
        f"`get_gate_state()` 를 감싸는 try 가 정확히 1개여야 한다 (실측 {len(gate_tries)}) — "
        "관측 실패는 반드시 흡수돼야 하고(리포트 생존), 중첩/중복은 귀인을 흐린다"
    )
    assert len(over_tries) == 1, (
        f"`over_cap_positions` 대입 try 가 정확히 1개여야 한다 (실측 {len(over_tries)})"
    )

    gate_try, over_try = gate_tries[0], over_tries[0]
    assert gate_try is not over_try, (
        "게이트 관측이 `over_cap_positions` 와 **같은** try 안에 있다 — 한쪽 실패가 "
        "다른 쪽을 삼킨다 (T3 가 행위로 같은 것을 잰다)"
    )
    assert gate_try not in ast.walk(over_try), "게이트 try 가 over_cap try 에 중첩됐다"
    assert over_try not in ast.walk(gate_try), "over_cap try 가 게이트 try 에 중첩됐다"
    assert _assigns_subscript_key(gate_try, "account_gate"), (
        "게이트 try 안에서 `snapshot[\"account_gate\"]` 대입이 보이지 않는다"
    )
    # tester 보강(cycle251 Verify) — 명세 §1 G "over_cap try **다음**" 순서 봉인
    # (뮤테이션 B9 순서 교환이 행위 테스트를 전부 통과해 탈출 — 배치는 명세 계약이다).
    assert gate_try.lineno > over_try.lineno, (
        f"게이트 try(L{gate_try.lineno})가 over_cap try(L{over_try.lineno}) **앞**에 있다 — "
        "명세 §1 G: `over_cap_positions` try 블록 **다음**에 별도 try"
    )


# ===========================================================================
# g251_2 (AST) — account_risk_watcher.get_gate_state 무접촉 봉인 (HEAD 대비)
# ===========================================================================

_ACCOUNT_GATE_KEYS = {
    "level", "reasons", "open_risk_pct", "evaluated_at",
    "age_secs", "stale", "stale_max_secs", "effective_gated",
}


def test_g251_2_get_gate_state_key_set_matches_frontend_contract():
    """`get_gate_state()` 8키 = 프론트 `AccountGate` 8필드 (리팩토링 리뷰 카드 #2 전환).

    종전 HEAD `ast.dump` 비교는 커밋 직후 공허해지고 편집 순간 영구 동결이 됐다.
    진짜 계약은 키 집합 — 리포트 `account_gate` 는 여기에 `eval_timeouts_today` 1키를
    더한 것이고(T1), 프론트 타입은 8필드 그대로다. 키가 늘면 세 곳을 함께 고친다.
    """
    from src.engine import account_risk_watcher as arw
    arw.reset_state_for_test()
    try:
        assert set(arw.get_gate_state()) == _ACCOUNT_GATE_KEYS
    finally:
        arw.reset_state_for_test()
    ts = (ROOT / "frontend" / "src" / "types" / "portfolio.ts").read_text(encoding="utf-8")
    iface = ts[ts.index("export interface AccountGate"):]
    iface = iface[: iface.index("}")]
    # 필수 필드만 대조 — 선택 필드(`?:`, 예: cycle256 이 선반영한 `eval_timeouts_today?`)는
    # 리포트 스냅샷 쪽 확장이라 `get_gate_state()` 8키 계약의 대상이 아니다.
    required = set(re.findall(r"^\s*([a-z_]+):", iface, re.M))
    optional = set(re.findall(r"^\s*([a-z_]+)\?:", iface, re.M))
    assert required == _ACCOUNT_GATE_KEYS, (
        f"프론트 AccountGate 필수 필드 {sorted(required)} ≠ 백엔드 8키 {sorted(_ACCOUNT_GATE_KEYS)}"
    )
    assert optional <= {"eval_timeouts_today"}, f"예상 밖 선택 필드: {sorted(optional)}"


# ===========================================================================
# g251_3 (텍스트) — 프론트 KST 표기 규약
# ===========================================================================
def test_g251_3_card_uses_intl_kst_not_local_getters():
    """CLAUDE.md KST 규칙 — `new Date(iso).getHours()` 브라우저 로컬타임 추출 금지."""
    assert CARD_TSX.exists(), f"{CARD_TSX} 부재"
    src = CARD_TSX.read_text(encoding="utf-8")

    for bad in ("getHours()", "getMinutes()"):
        assert bad not in src, (
            f"`PortfolioRiskCard.tsx` 에 `{bad}` — 브라우저 로컬타임 추출은 금지 "
            "(CI/EC2/사용자 브라우저 TZ 가 다르면 표시 시각이 조용히 어긋난다). "
            "`Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', ... })` 를 쓴다."
        )

    # cycle256 — KST 포맷터는 `utils/kst.ts` 단일 진실원으로 위임됐다. 카드는 그 유틸을 쓰고,
    # `timeZone: 'Asia/Seoul'` 리터럴은 유틸 파일에 있어야 한다(두 파일 중 어느 쪽에도 없으면 RED).
    kst_util = ROOT / "frontend" / "src" / "utils" / "kst.ts"
    util_src = kst_util.read_text(encoding="utf-8") if kst_util.exists() else ""
    assert re.search(r"timeZone\s*:\s*['\"]Asia/Seoul['\"]", src + util_src), (
        "`PortfolioRiskCard.tsx` 도 `utils/kst.ts` 도 `timeZone: 'Asia/Seoul'` 미사용 "
        "(`evaluated_at` HH:mm 표기는 KST 명시가 계약)"
    )
    assert ("formatKstHHMM" in src) or re.search(r"timeZone\s*:\s*['\"]Asia/Seoul['\"]", src), (
        "카드가 KST 유틸(`formatKstHHMM`)에 위임하지도, 직접 KST 를 명시하지도 않는다"
    )
