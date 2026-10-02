"""cycle401 (D-1) — `save_params` 가 행 없는 전략을 켜지 않는다.

결함: `strategy_config` 에 시드 행이 없는 전략의 파라미터를 저장하면 `save_params` 가
`enabled=True, weight=0.5` 행을 만들었다. 다음 재시작에 `_load_strategy_config` 가 그 값을
적용해, 손잡이 하나 저장한 새 전략이 켜지고 Σ 정규화로 자금을 받는다.

사용자 결정(10-02 R2, 자문 `_workspace/domain_consult/cycle398_refactor_cards_2_3.md` (b) 2-2):
- 행이 없으면 호출자(메모리를 가진 쪽)가 넘긴 현재 `enabled`·`weight` 를 그대로 적는다.
- 그 값이 없으면 `enabled=False, weight=0`.
- 행이 있으면 지금과 같다 — 넘긴 값으로 `enabled`·`weight` 를 덮지 않는다.

원칙: 「파라미터 저장이 켜고 끄기와 비중을 바꾸면 안 된다.」
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]


def _execute_args(pg_mod) -> tuple:
    """`save()` 가 보낸 (sid, enabled, weight, params, ts) 바인딩."""
    return pg_mod.execute.await_args.args[1:]


# ---------------------------------------------------------------------------
# DB 계층 — 행 없음
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_params_when_row_missing_then_writes_memory_enabled_and_weight():
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_params(
            "new_strat", {"foo": 1}, enabled=False, weight=0.0,
        )

    sid, enabled, weight, params, _ts = _execute_args(pg_mod)
    assert sid == "new_strat"
    assert enabled is False, "행이 없을 때 메모리 enabled=False 를 True 로 바꿨다 — 재시작에 켜진다"
    assert weight == 0.0
    assert params == {"foo": 1}


@pytest.mark.asyncio
async def test_save_params_when_row_missing_and_memory_enabled_then_keeps_enabled():
    """반대 방향 — 메모리에서 켜져 있는 전략(예: momentum 행이 사라진 경우)을 끄지 않는다.

    끄면 다음 재시작에 그 전략의 보유 손절이 멈춘다(루트 금기).
    """
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_params(
            "momentum", {"k": 2}, enabled=True, weight=0.3,
        )

    _sid, enabled, weight, _params, _ts = _execute_args(pg_mod)
    assert enabled is True
    assert weight == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_save_params_when_row_missing_and_no_memory_values_then_disabled_zero_weight():
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_params("new_strat", {"foo": 1})

    _sid, enabled, weight, params, _ts = _execute_args(pg_mod)
    assert enabled is False, "행도 메모리 값도 없는데 전략을 켰다 (옛 기본값 True 회귀)"
    assert weight == 0.0, "행도 메모리 값도 없는데 비중을 줬다 (옛 기본값 0.5 회귀)"
    assert params == {"foo": 1}


# ---------------------------------------------------------------------------
# DB 계층 — 행 있음: 지금과 같다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_params_when_row_exists_then_memory_values_do_not_override_row():
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"enabled": True, "weight": 0.25}])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_params(
            "donchian_swing", {"new": 2}, enabled=False, weight=0.9,
        )

    _sid, enabled, weight, params, _ts = _execute_args(pg_mod)
    assert enabled is True, "행이 있는데 넘긴 enabled 로 덮었다 — 파라미터 저장이 켜고 끄기를 바꿨다"
    assert weight == pytest.approx(0.25), "행이 있는데 넘긴 weight 로 덮었다"
    assert params == {"new": 2}


@pytest.mark.asyncio
async def test_save_params_when_row_exists_then_binding_identical_with_or_without_kwargs():
    """행 있음 경로는 키워드 인자 유무와 무관하게 같은 SQL·같은 바인딩(시각 제외)."""
    from src.db import strategy_config

    seen = []
    for kwargs in ({}, {"enabled": False, "weight": 0.0}):
        with patch.object(strategy_config, "pg", create=True) as pg_mod:
            pg_mod.fetch = AsyncMock(return_value=[{"enabled": False, "weight": 0.4}])
            pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
            await strategy_config.save_params("vcp_breakout", {"a": 1}, **kwargs)
        args = pg_mod.execute.await_args.args
        seen.append((args[0], args[1:5], pg_mod.fetch.await_args.args))
    assert seen[0] == seen[1]


# ---------------------------------------------------------------------------
# 라우트 — PUT /api/strategies/{id}/params 가 메모리 enabled·weight 를 넘긴다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_put_params_when_called_then_passes_memory_enabled_and_weight(monkeypatch):
    from src.routes import strategies as routes_mod

    strategy = SimpleNamespace(
        strategy_id="new_strat",
        config=SimpleNamespace(
            name="새 전략", enabled=False, weight=0.0, params={"position_ratio": 0.1},
        ),
    )
    monkeypatch.setattr(routes_mod, "trading_scheduler", SimpleNamespace(
        registry=SimpleNamespace(
            get=lambda sid: strategy if sid == "new_strat" else None,
            get_strategies_status=lambda: {},
        ),
    ))
    monkeypatch.setattr(routes_mod, "validate_params", lambda sid, cur, req: SimpleNamespace(
        errors=[], accepted=dict(req), warnings=[],
    ))
    calls: list = []

    async def _fake_save(strategy_id, params, **kwargs):
        calls.append({"sid": strategy_id, "params": copy.deepcopy(params), **kwargs})

    monkeypatch.setattr("src.db.strategy_config.save_params", _fake_save)

    resp = await routes_mod.update_params(
        "new_strat", routes_mod.ParamsRequest(params={"position_ratio": 0.2}),
    )

    assert resp.success is True
    assert len(calls) == 1
    assert calls[0]["enabled"] is False
    assert calls[0]["weight"] == 0.0
    assert calls[0]["params"] == {"position_ratio": 0.2}


# ---------------------------------------------------------------------------
# 구조 — src 의 모든 save_params 호출이 enabled=·weight= 를 넘긴다
# ---------------------------------------------------------------------------
def _save_params_calls() -> list[tuple[str, int, set[str]]]:
    out = []
    for path in sorted((_ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name == "save_params":
                out.append((
                    str(path.relative_to(_ROOT)), node.lineno,
                    {k.arg for k in node.keywords if k.arg},
                ))
    return out


def test_every_save_params_call_in_src_passes_memory_enabled_and_weight():
    calls = _save_params_calls()
    assert len(calls) >= 3, f"save_params 호출을 못 찾았다(스캔 공허): {calls}"
    missing = [(p, ln) for p, ln, kws in calls if not {"enabled", "weight"} <= kws]
    assert not missing, (
        f"메모리 enabled·weight 를 넘기지 않는 save_params 호출: {missing} — "
        "행이 없으면 그 전략이 False·0 으로 기록돼, 켜져 있던 전략이 재시작에 꺼질 수 있다"
    )
