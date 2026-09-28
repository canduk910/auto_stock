"""cycle387 Red — 종목 차트 신규 3파일의 범위·호출 경로 AST 가드 (G1~G7).

명세: `_workspace/red/cycle387_stock_chart_spec.md` §1.1 · §1.3 · §1.4 · §1.6 · §3.1(G1~G6)

왜 필요한가 — 이 기능은 **읽기 전용 KIS 시세 조회** 하나다. 그런데 KIS 호출 함수는 같은
`base.py` 안에 주문·잔고 경로(`kis_get`/`kis_post`/`kis_request`, 메인 계정 단일)와 시세 풀
경로(`kis_get_quote`, 보조 계정 라운드로빈 + 경로 화이트리스트)가 나란히 있다. 차트가 잘못된
쪽을 부르면 장중 더블클릭 폭주가 **주문 경로의 초당 한도**를 잡아먹는다. 이 파일은 그 경로
선택과 「매매 코드와 섞이지 않는다」를 소스 구조로 못박는다.

금기 준수(2026-09-05) — `git grep`/`git ls-files` 미사용(미추적 신규 파일을 못 본다) ·
`ast.dump` sha 핀 없음 · 주석·docstring 이 아니라 AST(import·호출·정의)만 센다.

RED: 신규 3파일 부재 → 읽기에서 FAIL. G5 는 현행 화이트리스트로 이미 초록(무변경 확인 가드).
"""

from __future__ import annotations

import ast
import sys
from datetime import timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
PERIOD_CHART = SRC / "api" / "period_chart.py"
CANDLE_MODEL = SRC / "models" / "candle_chart.py"
ROUTE = SRC / "routes" / "stock_chart.py"
NEW_FILES = (PERIOD_CHART, CANDLE_MODEL, ROUTE)

#: 주문·잔고(메인 계정) 경로 — 차트가 이름으로도 닿으면 안 된다.
FORBIDDEN_NAMES = {"kis_get", "kis_post", "kis_request", "_request"}
FORBIDDEN_MODULE_PREFIXES = ("src.api.order", "src.engine", "src.realtime", "src.auth")


def _read(path: Path) -> tuple[str, ast.Module]:
    assert path.exists(), f"{path.relative_to(ROOT)} 부재 (cycle387 Red)"
    text = path.read_text(encoding="utf-8")
    return text, ast.parse(text)


def _imports(tree: ast.AST) -> list[tuple[str, list[str], int]]:
    """(모듈, 가져온 이름들, 행) — 함수 안 지역 import 포함."""
    out: list[tuple[str, list[str], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, [], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            mod = ("." * node.level) + (node.module or "")
            out.append((mod, [a.name for a in node.names], node.lineno))
    return out


def _is_stdlib(module: str) -> bool:
    top = module.split(".")[0]
    return top in sys.stdlib_module_names


# ═════════════════════════════════════════════════════════════════════════════
# G1 — period_chart.py import 허용 목록
# ═════════════════════════════════════════════════════════════════════════════

def test_g1_period_chart_import_allowlist():
    """G1 — 표준 라이브러리 · `src.api.base`(kis_get_quote·KisApiError 만) ·
    `src.api.condition`(DAILY_PRICE_URL 만) · `src.db._kst` · `src.models.candle_chart` 뿐."""
    _, tree = _read(PERIOD_CHART)
    allowed_names = {
        "src.api.base": {"kis_get_quote", "KisApiError"},
        "src.api.condition": {"DAILY_PRICE_URL"},
    }
    allowed_any = {"src.db._kst", "src.models.candle_chart"}
    violations = []
    for mod, names, line in _imports(tree):
        if mod.startswith("."):
            violations.append(f"L{line}: 상대 import `{mod}` — 절대 경로만")
            continue
        if _is_stdlib(mod):
            continue
        if mod in allowed_any:
            continue
        if mod in allowed_names:
            if not names:
                violations.append(f"L{line}: `import {mod}` — 이름을 골라 가져온다({sorted(allowed_names[mod])})")
            extra = set(names) - allowed_names[mod]
            if extra:
                violations.append(f"L{line}: `{mod}` 에서 {sorted(extra)} — 허용 {sorted(allowed_names[mod])}")
            continue
        violations.append(f"L{line}: `{mod}` 는 허용 목록 밖")
    assert violations == [], "\n".join(violations)


def test_g1b_period_chart_never_touches_order_or_trading_paths():
    """G1b — `kis_get`·`kis_post`·`kis_request`·`_request` 이름 참조 0 · 매매·인증 모듈 import 0."""
    _, tree = _read(PERIOD_CHART)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    hit = (names | attrs) & FORBIDDEN_NAMES
    assert hit == set(), f"주문·잔고 경로 이름 참조: {sorted(hit)}"
    bad = [m for m, _, _ in _imports(tree) if m.startswith(FORBIDDEN_MODULE_PREFIXES)]
    assert bad == [], f"매매·인증 모듈 import: {bad}"


# ═════════════════════════════════════════════════════════════════════════════
# G2 — KIS 호출은 한 곳, 시장 J · 수정주가 0
# ═════════════════════════════════════════════════════════════════════════════

def test_g2_single_quote_pool_call_with_krx_adjusted_params():
    """G2 — `kis_get_quote(DAILY_PRICE_URL, "FHKST03010100", …)` 한 곳 · params 리터럴에
    `"FID_COND_MRKT_DIV_CODE": "J"` 와 `"FID_ORG_ADJ_PRC": "0"` · `get_tr_id` 0."""
    text, tree = _read(PERIOD_CHART)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "kis_get_quote"
    ]
    assert len(calls) == 1, f"kis_get_quote 호출 {len(calls)}곳 (기대 1)"
    call = calls[0]
    assert len(call.args) >= 2
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "DAILY_PRICE_URL"
    assert isinstance(call.args[1], ast.Constant) and call.args[1].value == "FHKST03010100"

    pairs = {}
    for d in (n for n in ast.walk(tree) if isinstance(n, ast.Dict)):
        for k, v in zip(d.keys, d.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value.startswith("FID_"):
                pairs.setdefault(k.value, []).append(v.value if isinstance(v, ast.Constant) else None)
    assert pairs.get("FID_COND_MRKT_DIV_CODE") == ["J"], "시장은 J(KRX 정규) 리터럴 — UN/NX 는 정규장 종가가 없다"
    assert pairs.get("FID_ORG_ADJ_PRC") == ["0"], "수정주가 0 리터럴(기존 3 함수와 같은 값)"
    code_names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    }
    assert "get_tr_id" not in code_names, "FH TR 은 get_tr_id 를 거치면 VH 로 깨진다(finance.py 규약)"


# ═════════════════════════════════════════════════════════════════════════════
# G3 — 라우트는 GET 하나, 매매 모듈 import 0
# ═════════════════════════════════════════════════════════════════════════════

_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route", "websocket"}


def test_g3_route_is_get_only_and_isolated_from_trading():
    """G3 — 라우트 데코레이터는 `get` 만 · `src.engine`·`scheduler`·`src.api.order` import 0."""
    _, tree = _read(ROUTE)
    methods = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for dec in fn.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Attribute) and target.attr in _ROUTE_METHODS:
                methods.append(target.attr)
    assert methods == ["get"], f"라우트 데코레이터 {methods} — 읽기 전용 GET 하나여야 한다"
    bad = [
        m for m, _, _ in _imports(tree)
        if m.startswith(("src.engine", "src.api.order", "src.realtime", "src.auth")) or "scheduler" in m
    ]
    assert bad == [], f"라우트가 매매 모듈을 import 한다: {bad}"


# ═════════════════════════════════════════════════════════════════════════════
# G4 — 상수 핀
# ═════════════════════════════════════════════════════════════════════════════

def test_g4_constants_pinned():
    """G4 — 명세 §1.4 표의 값. 폭주 방지 산수(초당 4건 이하 · 요청당 상한)의 근거다."""
    from src.api import period_chart as pc

    assert pc._KIS_MAX_ROWS == 100
    assert pc._MAX_CALLS_PER_FETCH == {"D": 15, "W": 4, "M": 2}
    assert pc._WINDOW_SLEEP_SECS >= 0.2, "초당 4건 이하 — 전역 초당 20건을 주문·잔고와 나눠 쓴다"
    assert pc._WINDOW_SLEEP_SECS == 0.25
    assert pc._FETCH_CONCURRENCY == 1
    assert pc._QUEUE_WAIT_SECS == 20.0
    assert pc._FETCH_TIME_BUDGET_SECS == 25.0
    assert pc._CACHE_TTL_SECS == 600
    assert pc._PARTIAL_CACHE_TTL_SECS == 60
    assert pc._CACHE_MAX_ENTRIES == 32
    assert pc._PROVISIONAL_CUTOFF == timedelta(hours=6), "daily_bar_finalize 의 06:00 경계와 같은 값"


# ═════════════════════════════════════════════════════════════════════════════
# G5 — 시세 풀 화이트리스트 무변경으로 충분하다
# ═════════════════════════════════════════════════════════════════════════════

def test_g5_daily_price_url_already_whitelisted_for_quote_pool():
    """G5 — `DAILY_PRICE_URL ∈ base._QUOTE_ALLOWED_PATHS` — base.py 를 건드리지 않아도 된다."""
    from src.api import base, condition

    assert condition.DAILY_PRICE_URL in base._QUOTE_ALLOWED_PATHS


# ═════════════════════════════════════════════════════════════════════════════
# G6 — 같은 이름 파일쌍 차단 (2026-09-19 덮어쓰기 사고 경로)
# ═════════════════════════════════════════════════════════════════════════════

def test_g6_new_file_basenames_distinct_and_unique_in_src():
    """G6 — 세 신규 파일이 존재하고 basename 이 서로 다르며 `src/` 안에서 유일하다.

    같은 이름 파일쌍(`routes/market_regime.py` ↔ `engine/market_regime.py`)이 병렬 작업의
    덮어쓰기 사고 경로였다(루트 CLAUDE.md 「병렬 작업」).
    """
    for p in NEW_FILES:
        assert p.exists(), f"{p.relative_to(ROOT)} 부재 (cycle387 Red)"
    names = [p.name for p in NEW_FILES]
    assert len(set(names)) == 3, names
    for name in names:
        same = sorted(str(p.relative_to(ROOT)) for p in SRC.rglob(name))
        assert len(same) == 1, f"`{name}` 이 src/ 에 {len(same)}개: {same}"


# ═════════════════════════════════════════════════════════════════════════════
# G7 — 매매 코드는 차트 모듈을 읽지 않는다 (명세 §6)
# ═════════════════════════════════════════════════════════════════════════════

def test_g7_trading_code_does_not_import_chart_modules():
    """G7 — `src/engine`·`src/realtime`·`src/auth` 어디도 `period_chart`·`stock_chart`·
    `candle_chart` 를 import 하지 않는다(차트 캐시·세마포어가 매매 경로에 끼지 않는다)."""
    for p in NEW_FILES:
        assert p.exists(), f"{p.relative_to(ROOT)} 부재 (cycle387 Red)"
    hits = []
    for d in ("engine", "realtime", "auth"):
        for f in sorted((SRC / d).rglob("*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for mod, names, line in _imports(tree):
                blob = " ".join([mod, *names])
                if any(k in blob for k in ("period_chart", "stock_chart", "candle_chart")):
                    hits.append(f"{f.relative_to(ROOT)}:L{line} {blob}")
    assert hits == [], "\n".join(hits)
