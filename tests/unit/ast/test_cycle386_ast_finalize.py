"""cycle386 Red (구조) — 잠정 봉 확정 leaf 의 배선·경계·불변식 (설계 §8-9 G5·G6·G7).

명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §8-3·8-4·8-5·8-7·8-9.

## 무엇을 잠그나
- G5(a) `boot_manager.boot` 안 순서 = `get_token` < `spawn` < `wait_for_boot` < `emit_daily_head_staleness`
  < prepare 루프. `wait_for_boot` 는 헤드 관측 **바로 앞** 문장이고 예산은 `BOOT_BUDGET_SECS` 이름으로 넘긴다.
  (M5 = 대기 줄 삭제·prepare 뒤로 이동)
- G5(b) leaf 의 import — 8영역·`scheduler`·`scanner`·`boot_manager`·strategies 0. 허용 = `src.db.stock_master_daily`
  · `src.db.system_config` · `src.db.positions` · `src.db._kst` · `src.api.condition`(함수 안 지연 import 만).
- G5(c) **「`stock_master_daily.updated_at` 을 바꾸는 쓰기는 `_UPSERT_DAILY_SQL` 하나뿐」** — 잠정 판정(§8-3)이
  `updated_at` = 「KIS 값을 받아 쓴 시각」에 기댄다. `src/` 전체(rglob + AST 문자열, docstring 제외)에서
  이 테이블에 쓰는 INSERT/UPDATE SQL 은 그 상수 하나여야 하고, 마이그레이션은 `updated_at` 을 UPDATE 하지도
  트리거를 걸지도 않는다(M8). 쓰는 순간을 찍는지는 `_candle_to_row` 런타임으로 확인한다.
- G5(d) 받는 구간 상한 = `P` — 런타임 증명은 `tests/unit/engine/test_cycle386_daily_bar_finalize.py::test_g2_10`.
- G6 상수 값과 관계 · G7 시각 불변식(부팅 기동 거부 20:00 + 하드캡 ≤ 20:30 적재 < 20:45 보조 토큰 창 − 10분).
- leaf 의 KST — naive `datetime.now()`·`date.today()`·`utcnow()` 0.

금기(2026-09-05 가드 설계 교훈): `ast.dump` sha 리터럴 핀 금지 · `git grep/ls-files` 금지(미추적 Green 파일을 못 본다)
· bare `git diff HEAD` 영구 가드 금지. 이 파일은 전부 파일 시스템 + AST 로만 잰다.

## HEAD 기준
leaf·배선이 없어 G5(a)(b)(e)·G6·G7(`HARD_CAP_SECS` 를 leaf 에서 읽는다)은 RED. G5(c)(src 스캔·마이그레이션·
`_candle_to_row`)는 HEAD 에서 이미 초록이다(영구 가드 — 돌연변이 M8 이 붉게 만든다).
"""
from __future__ import annotations

import ast
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_LEAF = _SRC / "engine" / "daily_bar_finalize.py"
_BOOT = _SRC / "engine" / "boot_manager.py"
_SMD = _SRC / "db" / "stock_master_daily.py"
_MIGRATIONS = _ROOT / "supabase" / "migrations"

_EIGHT_AREA_MODULES = (
    "src.engine.risk", "src.engine.order_engine", "src.engine.session", "src.engine.scanner",
    "src.engine.strategy_registry", "src.api.order", "src.realtime", "src.auth",
)
_FORBIDDEN_PREFIXES = _EIGHT_AREA_MODULES + (
    "src.engine.scheduler", "src.engine.boot_manager", "src.engine.strategies",
)
_ALLOWED_SRC_MODULES = {
    "src.db.stock_master_daily", "src.db.system_config", "src.db.positions", "src.db._kst",
    "src.api.condition",
}


def _leaf_src() -> str:
    assert _LEAF.exists(), "`src/engine/daily_bar_finalize.py` 가 없다 (cycle386 leaf 미구현)"
    return _LEAF.read_text(encoding="utf-8")


def _fn(tree: ast.AST, name: str) -> ast.AST:
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"`{name}` 함수를 찾지 못했다")


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _calls(fn: ast.AST, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and _call_name(n) == name]


# ===========================================================================
# G5(a) — 부팅 배선 순서
# ===========================================================================
def _boot_fn():
    src = _BOOT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    return src, _fn(tree, "boot")


def _prepare_loop_lineno(src: str, fn: ast.AST) -> int:
    for n in ast.walk(fn):
        if isinstance(n, ast.For):
            seg = ast.get_source_segment(src, n) or ""
            if "live_prepare_one(" in seg or "strategy.prepare()" in seg:
                return n.lineno
    raise AssertionError("prepare 루프를 찾지 못했다")


def test_g5_a1_boot_order_token_spawn_wait_head_prepare() -> None:
    src, fn = _boot_fn()
    tok = [c.lineno for c in _calls(fn, "get_token")]
    spawn = [c.lineno for c in _calls(fn, "spawn")]
    wait = [c.lineno for c in _calls(fn, "wait_for_boot")]
    head = [c.lineno for c in _calls(fn, "emit_daily_head_staleness")]
    assert spawn, "부팅이 확정 태스크를 띄우지 않는다(`daily_bar_finalize.spawn` 호출 없음)"
    assert wait, "부팅이 확정을 기다리지 않는다(`wait_for_boot` 호출 없음) — prepare 가 잠정 봉을 읽는다"
    assert len(spawn) == 1 and len(wait) == 1, f"spawn {len(spawn)}곳 · wait_for_boot {len(wait)}곳 — 각 1곳"
    loop = _prepare_loop_lineno(src, fn)
    assert tok and min(tok) < spawn[0], "spawn 이 토큰 사전 발급보다 앞이다 — 보조 풀이 준비되기 전이다"
    assert spawn[0] < wait[0] < min(head) < loop, (
        f"순서 = get_token({min(tok)}) < spawn({spawn[0]}) < wait_for_boot({wait[0]}) < "
        f"emit_daily_head_staleness({min(head)}) < prepare 루프({loop}) 이어야 한다"
    )


def test_g5_a2_wait_is_the_statement_right_before_the_head_observer() -> None:
    """대기와 prepare 사이에 다른 await 가 끼면 그만큼 확정이 prepare 뒤로 밀린 것과 같다."""
    src, fn = _boot_fn()
    body = fn.body
    idx = None
    for i, st in enumerate(body):
        if any(_call_name(c) == "emit_daily_head_staleness"
               for c in ast.walk(st) if isinstance(c, ast.Call)):
            idx = i
            break
    assert idx is not None and idx > 0, "헤드 관측 문장을 boot 최상위 본문에서 찾지 못했다"
    prev = body[idx - 1]
    assert any(_call_name(c) == "wait_for_boot" for c in ast.walk(prev) if isinstance(c, ast.Call)), (
        f"헤드 관측 바로 앞 문장이 `wait_for_boot` 가 아니다 — "
        f"{(ast.get_source_segment(src, prev) or '')[:120]!r}"
    )
    assert isinstance(prev, ast.Expr) and isinstance(prev.value, ast.Await), "wait_for_boot 는 await 되어야 한다"


def test_g5_a3_spawn_is_not_awaited_and_budget_is_named() -> None:
    """spawn 은 띄우기만 한다(설정·잔고·레짐과 겹쳐 돈다). 예산은 이름으로 넘긴다(리터럴 90 금지)."""
    _src, fn = _boot_fn()
    spawn = _calls(fn, "spawn")[0]
    awaited = {id(n.value) for n in ast.walk(fn) if isinstance(n, ast.Await)}
    assert id(spawn) not in awaited, "spawn 을 await 했다 — 겹쳐 돌리는 설계가 무너진다(부팅이 통째로 늘어난다)"
    kw = {k.arg: k.value for k in spawn.keywords}
    assert isinstance(kw.get("phase"), ast.Constant) and kw["phase"].value == "boot"
    wait = _calls(fn, "wait_for_boot")[0]
    bkw = {k.arg: k.value for k in wait.keywords}
    b = bkw.get("budget_secs")
    assert b is not None, "wait_for_boot(..., budget_secs=...) 키워드가 없다"
    name = b.attr if isinstance(b, ast.Attribute) else (b.id if isinstance(b, ast.Name) else None)
    assert name == "BOOT_BUDGET_SECS", f"예산은 `BOOT_BUDGET_SECS` 로 넘긴다 — {ast.dump(b)}"


# ===========================================================================
# G5(b) — leaf import 경계
# ===========================================================================
def _imports(tree: ast.AST) -> list[tuple[str, bool]]:
    """(모듈 이름, 모듈 최상위 여부) — `from src.db import x` 는 `src.db.x` 로 푼다."""
    top_level_nodes = set(id(n) for n in getattr(tree, "body", []))
    out: list[tuple[str, bool]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.append((a.name, id(n) in top_level_nodes))
        elif isinstance(n, ast.ImportFrom) and n.module:
            top = id(n) in top_level_nodes
            if n.module in ("src", "src.db", "src.api", "src.engine"):
                for a in n.names:
                    out.append((f"{n.module}.{a.name}", top))
            else:
                out.append((n.module, top))
    return out


def test_g5_b1_leaf_imports_stay_inside_the_allowed_set() -> None:
    tree = ast.parse(_leaf_src())
    src_mods = [(m, top) for m, top in _imports(tree) if m == "src" or m.startswith("src.")]
    bad = [m for m, _ in src_mods if any(m == p or m.startswith(p + ".") for p in _FORBIDDEN_PREFIXES)]
    assert not bad, f"leaf 가 금지 모듈을 import 한다 — {bad} (8영역·scheduler·scanner·boot_manager·strategies 0)"
    extra = sorted({m for m, _ in src_mods} - _ALLOWED_SRC_MODULES)
    assert not extra, f"허용 목록 밖 src import — {extra} (허용 = {sorted(_ALLOWED_SRC_MODULES)})"


def test_g5_b2_condition_is_imported_lazily() -> None:
    tree = ast.parse(_leaf_src())
    top = [m for m, is_top in _imports(tree) if is_top and m.startswith("src.api")]
    assert not top, f"`src.api.*` 를 모듈 최상위에서 import 한다 — {top} (함수 안 지연 import 만)"


# ===========================================================================
# G5(c) — updated_at 불변식
# ===========================================================================
def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _string_literals(tree: ast.AST) -> list[tuple[ast.AST, str]]:
    docs = _docstring_ids(tree)
    out: list[tuple[ast.AST, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            out.append((n, n.value))
        elif isinstance(n, ast.JoinedStr):
            out.append((n, "".join(v.value for v in n.values
                                   if isinstance(v, ast.Constant) and isinstance(v.value, str))))
    return out


_WRITE_RE = re.compile(r"\b(insert\s+into|update)\s+stock_master_daily\b", re.I | re.S)


def _daily_write_sqls() -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for path in sorted(_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "stock_master_daily" not in text:
            continue
        tree = ast.parse(text)
        for node, s in _string_literals(tree):
            if _WRITE_RE.search(s):
                found.append((path, getattr(node, "lineno", 0), s))
    return found


def test_g5_c1_only_the_upsert_writes_stock_master_daily() -> None:
    found = _daily_write_sqls()
    smd_tree = ast.parse(_SMD.read_text(encoding="utf-8"))
    upsert_node = None
    for n in smd_tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_UPSERT_DAILY_SQL"
                                             for t in n.targets):
            upsert_node = n.value
    assert isinstance(upsert_node, ast.Constant), "`_UPSERT_DAILY_SQL` 상수를 찾지 못했다"
    others = [(p.relative_to(_ROOT).as_posix(), ln) for p, ln, s in found
              if not (p == _SMD and s == upsert_node.value)]
    assert others == [], (
        "`stock_master_daily` 에 쓰는 SQL 이 `_UPSERT_DAILY_SQL` 말고도 있다 — 잠정 판정(`updated_at` = KIS 값을 "
        f"받아 쓴 시각)이 무너진다: {others}"
    )
    assert any(p == _SMD for p, _, _ in found), "양성 대조군 — 스캔이 upsert 조차 못 찾는다(공허)"


def test_g5_c2_upsert_sets_updated_at_from_the_write_moment() -> None:
    sql = None
    for n in ast.parse(_SMD.read_text(encoding="utf-8")).body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_UPSERT_DAILY_SQL"
                                             for t in n.targets):
            sql = n.value.value
    assert sql and re.search(r"updated_at\s*=\s*EXCLUDED\.updated_at", sql, re.I), (
        "ON CONFLICT 가 updated_at 을 갱신하지 않는다 — 다시 받아 쓴 봉이 옛 시각으로 남아 영원히 잠정이다"
    )


def test_g5_c3_candle_to_row_stamps_now(monkeypatch) -> None:
    import src.db.stock_master_daily as smd

    monkeypatch.setattr(smd, "now_kst_iso", lambda: "2026-09-29T07:46:00+09:00")
    row = smd._candle_to_row("005930", {"stck_bsop_date": "20260928", "stck_clpr": "100"})
    assert row["updated_at"] == datetime.fromisoformat("2026-09-29T07:46:00+09:00"), (
        f"updated_at 이 쓰는 순간이 아니다 — {row['updated_at']!r}"
    )


def test_g5_c4_migrations_never_touch_updated_at_nor_add_triggers() -> None:
    bad: list[str] = []
    for f in sorted(_MIGRATIONS.glob("*.sql")):
        sql = f.read_text(encoding="utf-8")
        for m in re.finditer(r"\bupdate\s+stock_master_daily\b(.*?);", sql, re.I | re.S):
            if re.search(r"\bupdated_at\b", m.group(1), re.I):
                bad.append(f"{f.name}: UPDATE ... updated_at")
        if re.search(r"create\s+(or\s+replace\s+)?(constraint\s+)?trigger\b[^;]*\bon\s+(public\.)?stock_master_daily\b",
                     sql, re.I | re.S):
            bad.append(f"{f.name}: TRIGGER ON stock_master_daily")
    assert bad == [], f"마이그레이션이 updated_at 의 뜻을 바꾼다 — {bad}"


# ===========================================================================
# G5(e) — leaf KST (naive 벽시계 0)
# ===========================================================================
def test_g5_e_leaf_has_no_naive_wall_clock() -> None:
    tree = ast.parse(_leaf_src())
    bad: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        attr = n.func.attr
        if attr == "now" and not n.args and not n.keywords:
            bad.append(f"L{n.lineno} now()")
        if attr in ("utcnow", "today"):
            bad.append(f"L{n.lineno} {attr}()")
        if attr == "time" and isinstance(n.func.value, ast.Name) and n.func.value.id in ("time", "_time"):
            bad.append(f"L{n.lineno} time.time()")
    assert bad == [], f"naive 벽시계 — {bad} (KST 명시 · 경과 시간은 monotonic)"


# ===========================================================================
# G6 — 상수 값과 관계
# ===========================================================================
def test_g6_1_constants_pinned() -> None:
    """🔁 backend-dev 리뷰 반영 재핀(값만) — `BG_WORKERS` 제거.

    코드가 읽지 않는 표기 상수였다(배경 일꾼 수는 `_run_workers` 가 0번 일꾼만 남기는
    것으로 정해진다 — `src/engine/CLAUDE.md` 가 이미 그렇게 적어 뒀다). 배경 보폭
    자체는 `BG_SLEEP_SECS` 하나로 충분히 고정된다.
    """
    from src.engine import daily_bar_finalize as d

    assert d.FINAL_BOUNDARY_TIME == time(6, 0), "확정 경계 = D+1일 06:00 (05:28 실측 + 32분)"
    assert d.WINDOW_CAL_DAYS == 21
    assert d.MAX_SPAN_CAL_DAYS == 130
    assert d.RANGE_PAD_CAL_DAYS == 10
    assert d.BOOT_WORKERS == 3
    assert d.BOOT_BUDGET_SECS == 90
    assert d.BG_SLEEP_SECS == 0.05
    assert d.HARD_CAP_SECS == 600
    assert not hasattr(d, "BG_WORKERS"), "`BG_WORKERS` 는 제거됐다 — 되살리지 않는다"


def test_g6_2_constant_relations() -> None:
    from src.engine import daily_bar_finalize as d

    assert d.WINDOW_CAL_DAYS + d.RANGE_PAD_CAL_DAYS <= d.MAX_SPAN_CAL_DAYS, (
        "창 + 여유가 한 호출 구간을 넘는다 — 첫 부팅의 옛 봉이 잘린다"
    )
    assert d.MAX_SPAN_CAL_DAYS <= 140, "130 달력일 ≈ 92영업일 — 140(100영업일)을 넘으면 KIS 100봉 한도에 앞이 잘린다"
    assert 1 <= d.BOOT_WORKERS <= 20, "전역 한도 20건/초(`base.py _rate_limit`)"
    assert 0 < d.BOOT_BUDGET_SECS < d.HARD_CAP_SECS


# ===========================================================================
# G7 — 시각 불변식 (20:45 보조 토큰 창과 겹칠 수 없다)
# ===========================================================================
def _at(t: time) -> datetime:
    return datetime.combine(date(2026, 9, 28), t)


def test_g7_1_latest_boot_plus_hard_cap_ends_before_the_evening_load() -> None:
    from src.engine import daily_bar_finalize as d
    from src.engine.scheduler import TIME_SESSION_START_CUTOFF, TIME_STOCK_MASTER_DAILY_LOAD

    end = _at(TIME_SESSION_START_CUTOFF) + timedelta(seconds=d.HARD_CAP_SECS)
    assert end <= _at(TIME_STOCK_MASTER_DAILY_LOAD), (
        f"가장 늦은 부팅(기동 거부 {TIME_SESSION_START_CUTOFF} 직전) + 하드캡 = {end.time()} 이 "
        f"20:30 적재({TIME_STOCK_MASTER_DAILY_LOAD})를 넘는다"
    )


def test_g7_2_finalize_can_never_overlap_the_quote_token_window() -> None:
    from src.engine import daily_bar_finalize as d
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH
    from src.engine.scheduler import TIME_SESSION_START_CUTOFF, TIME_STOCK_MASTER_DAILY_LOAD

    window_lo = _at(TIME_QUOTE_TOKEN_REFRESH) - timedelta(minutes=10)
    assert _at(TIME_STOCK_MASTER_DAILY_LOAD) < window_lo, (
        "20:30 적재가 보조 토큰 자연 재발급 문턱(T−10분) 뒤다 — test_cycle269 C9 와 같은 창"
    )
    end = _at(TIME_SESSION_START_CUTOFF) + timedelta(seconds=d.HARD_CAP_SECS)
    assert end < window_lo, f"확정이 끝나는 가장 늦은 시각({end.time()})이 토큰 창({window_lo.time()})에 닿는다"
