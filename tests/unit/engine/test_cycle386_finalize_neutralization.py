"""cycle386 Red (G9 메타) — 부팅 「잠정 봉 확정」 중립화가 켜져 있고, 옵트아웃 마커만 실제 경로를 탄다.

## 왜
cycle386 은 `boot_manager.boot()` 의 prepare 앞에 DB(헤드·잠정 행 조회)·KIS(일봉 재수신)·upsert 를 끼워 넣는다.
`boot()` 를 도는 기존 테스트는 40여 파일이다. 중립화가 조용히 사라지면 그 테스트들이 실제 DB 풀을 찾거나
외부 네트워크 차단(2026-09-26 C2)에 걸려 **결과가 환경 속도에 묶인다** — 그 계열 사고가 이미 두 번 있었다
(cycle295 벽시계 게이트 59건 · 09-25 부팅 테스트 60초 타임아웃).

## 계약
- `tests/conftest.py` autouse `_neutralize_daily_bar_finalize` 가 `daily_bar_finalize.finalize_once` 를 빈 코루틴으로
  바꾼다. `spawn`·`wait_for_boot` 는 실제 것이다(배선은 돈다).
- `@pytest.mark.real_daily_bar_finalize` 가 붙은 테스트만 실제 `finalize_once` 를 본다.
- 마커 사용처는 아래 허용 목록뿐이다 — 새 파일이 마커를 붙이면(= 실제 DB·KIS 경로를 연다) 여기서 붉어진다.

## HEAD 기준
leaf 가 없어 런타임 3건은 RED(import 실패). 등재·픽스처 구조 2건은 이 Red 와 같은 변경에 들어 있어 초록이다.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_MARKER = "real_daily_bar_finalize"
_ALLOWED_MARKER_FILES = {
    "tests/conftest.py",
    "tests/unit/engine/test_cycle386_daily_bar_finalize.py",
    "tests/unit/engine/test_cycle386_finalize_neutralization.py",
    "tests/unit/engine/strategies/test_cycle386_prev_close_regression.py",
    "tests/integration/test_cycle386_provisional_predicate_pg.py",
}


def test_g9_1_marker_is_registered() -> None:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"{_MARKER}:' in text, "pyproject markers 에 등록이 없다 — filterwarnings=error 라 마커가 즉시 실패한다"


def test_g9_2_conftest_has_autouse_neutralizer_with_opt_out() -> None:
    src = (_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "_neutralize_daily_bar_finalize"), None)
    assert fn is not None, "conftest 에 `_neutralize_daily_bar_finalize` 가 없다"
    autouse = False
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and any(k.arg == "autouse" and isinstance(k.value, ast.Constant)
                                           and k.value.value is True for k in d.keywords):
            autouse = True
    assert autouse, "중립화 픽스처가 autouse 가 아니다 — 부팅 테스트가 실제 DB·KIS 로 나간다"
    seg = ast.get_source_segment(src, fn) or ""
    assert f'get_closest_marker("{_MARKER}")' in seg, "옵트아웃 마커 판정이 없다"
    assert '"finalize_once"' in seg, "중립화 대상이 `finalize_once` 가 아니다"


def test_g9_3_unmarked_test_sees_the_inert_finalize() -> None:
    from src.engine import daily_bar_finalize as dbf

    got = Path(inspect.getsourcefile(dbf.finalize_once) or "").resolve()
    assert got != Path(dbf.__file__).resolve(), (
        "마커 없는 테스트가 실제 `finalize_once` 를 본다 — conftest 중립화가 꺼졌다"
    )


@pytest.mark.real_daily_bar_finalize
def test_g9_4_marked_test_sees_the_real_finalize() -> None:
    from src.engine import daily_bar_finalize as dbf

    got = Path(inspect.getsourcefile(dbf.finalize_once) or "").resolve()
    assert got == Path(dbf.__file__).resolve(), "옵트아웃 마커가 듣지 않는다 — leaf 를 직접 검증할 수 없다"


@pytest.mark.asyncio
async def test_g9_5_unmarked_boot_touches_no_db_or_kis_via_finalize(monkeypatch) -> None:
    """마커 없는 `boot()` — spawn 은 돌고(배선 존재) 확정 경로의 DB·KIS 호출은 0."""
    import src.api.condition as cond
    import src.db.stock_master_daily as smd
    from src.engine import boot_manager
    from src.engine import daily_bar_finalize as dbf

    hits: list[str] = []

    def _rec(name):
        async def _f(*_a, **_k):
            hits.append(name)
            raise AssertionError(f"중립화된 부팅이 {name} 를 불렀다")
        return _f

    monkeypatch.setattr(smd, "list_provisional_rows", _rec("list_provisional_rows"), raising=False)
    monkeypatch.setattr(smd, "upsert_batch", _rec("upsert_batch"))
    monkeypatch.setattr(smd, "max_bas_dd", _rec("max_bas_dd"))
    monkeypatch.setattr(smd, "max_bas_dd_before", _rec("max_bas_dd_before"), raising=False)
    monkeypatch.setattr(cond, "fetch_daily_chart_ranged_with_summary",
                        _rec("fetch_daily_chart_ranged_with_summary"), raising=False)

    spawned: list[object] = []
    real_spawn = dbf.spawn

    def _counting_spawn(*a, **k):
        t = real_spawn(*a, **k)
        spawned.append(t)
        return t

    monkeypatch.setattr(dbf, "spawn", _counting_spawn)

    class _S:
        strategy_id = "vb"

        async def prepare(self, *a, **k):
            return None

    s = MagicMock()
    s._preissue_all_tokens = AsyncMock()
    s._load_strategy_config = AsyncMock()
    s._refresh_market_regime_and_persist = AsyncMock()
    s._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
    s.registry = MagicMock()
    s.registry.enabled = MagicMock(return_value=[_S()])
    summary = MagicMock(net_asset=1_000_000)
    with patch.object(boot_manager, "get_balance", AsyncMock(return_value=([], summary))), \
            patch.object(boot_manager, "token_manager") as tm, \
            patch.object(boot_manager, "get_daily_orders", AsyncMock(return_value=[])), \
            patch("src.db.stock_master.count_active", AsyncMock(return_value=100)), \
            patch.object(boot_manager, "emit_daily_head_staleness", AsyncMock()), \
            patch.object(boot_manager, "write_log", AsyncMock()):
        tm.get_token = AsyncMock()
        try:
            await asyncio.wait_for(boot_manager.boot(s), timeout=10)
        except asyncio.TimeoutError:
            pytest.fail("중립화된 부팅이 멈췄다")
        except Exception:
            pass
    for t in spawned:
        if t is not None:
            await asyncio.wait_for(asyncio.shield(t), timeout=5)

    assert len(spawned) == 1, f"부팅이 확정 태스크를 띄우지 않았다(배선 부재) — spawn {len(spawned)}회"
    assert hits == [], f"중립화된 부팅이 확정 경로의 DB·KIS 를 불렀다 — {hits}"


def test_g9_6_marker_usage_is_allowlisted() -> None:
    """마커 = 실제 DB·KIS 경로를 연다는 뜻이다. 새로 붙이는 곳은 이 목록에 의도적으로 더한다."""
    users = set()
    for p in (_ROOT / "tests").rglob("*.py"):
        if _MARKER in p.read_text(encoding="utf-8", errors="ignore"):
            users.add(p.relative_to(_ROOT).as_posix())
    assert users <= _ALLOWED_MARKER_FILES, f"허용 목록 밖에서 마커를 쓴다 — {sorted(users - _ALLOWED_MARKER_FILES)}"
    assert "tests/conftest.py" in users, "양성 대조군 — conftest 가 마커를 읽지 않는다"
