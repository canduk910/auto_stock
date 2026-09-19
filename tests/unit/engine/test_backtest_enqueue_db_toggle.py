"""Red — backtest enqueue 게이트 KIS_MCP DB 토글 인식 (결함 d, 2026-07-24).

근본 원인 (kojiro 실측 조사 中 규명):
    ``_enqueue_backtest_jobs`` (recommendation_engine.py:548) 가 활성 여부를
    **프로세스 시작 시 고정된 .env 값** (`engine.enabled` 정적 프로퍼티) 으로 읽는다.
    운영자가 Settings UI 로 DB 토글(`system_config.kis_mcp_enabled=true`) 을 켜도,
    프로세스 재시작 전엔 이 게이트가 여전히 False → 지원 3종(momentum/VB/donchian)
    backtest 가 매일 조용히 `skipped`("MCP 비활성"). 프로덕션 실측 = DB=true 인데
    `backtest_summary` 전 전략 공백.

시정 (Green, backend-dev):
    라인 548 `enabled = bool(getattr(engine, "enabled", False))`
    → `enabled = await engine.is_enabled_async()` (DB 우선 → .env fallback, 이미 구현됨).

Red 테스트 (T1-T4) — 기존 test_recommendation_backtest_hook.py /
test_backtest_engine_db_toggle.py mock 패턴 답습:

- T1 (핵심): is_enabled_async()=True + 정적 enabled=False → 지원 3종이 'MCP 비활성'
  skip 되지 않고 submit. 현행(정적 False 읽음)에선 skip → **Red**.
- T2 (회귀): is_enabled_async()=False → 지원 3종 'MCP 비활성' skipped + submit 0.
- T3 (회귀): _FALLBACK_STRATEGIES(kojiro/LTV/BFB/VCP) 는 enabled 무관 항상
  '로컬 백테스트 실행기 없음' skipped.
- T4 (회귀): DB 조회 예외 시 is_enabled_async 의 .env fallback 이 게이트에서도
  graceful — 예외 전파 없음.

테스트 더블:
    _db_insert_run / _db_update_status / _get_backtest_engine /
    _spawn_backtest_poll_task 모두 monkeypatch. run_for_strategy 는 mock 으로
    MCP 실호출 차단.
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼: enqueue 페이로드 (지원 3종 + 폴백 4종 = 7 전략)
# ---------------------------------------------------------------------------
SUPPORTED = ("momentum", "volatility_breakout", "donchian_swing")
FALLBACK = ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout", "kojiro")
ALL_STRATEGIES = SUPPORTED + FALLBACK


def _make_inserted_rows(target_date: date) -> list[dict]:
    """generate_recommendations() 가 _enqueue_backtest_jobs 로 넘기는 페이로드."""
    rows = []
    for sid in ALL_STRATEGIES:
        rows.append(
            {
                "id": f"rec-{sid}",
                "target_date": target_date.isoformat(),
                "strategy_id": sid,
                "current_params": {"buy_threshold": 29.0},
                "recommended_params": {"buy_threshold": 27.0},
            }
        )
    return rows


def _install_db_doubles(monkeypatch, target_mod):
    """_db_insert_run / _db_update_status 더블 설치 → (inserted, updates) 반환.

    target_mod = src.engine.backtest_orchestration (본체가 lookup 하는 실제 네임스페이스 —
    사이클 refactor B3 이관 후 recommendation_engine 재export patch 는 본체에 무영향).
    """
    inserted_rows: list[dict] = []
    update_records: list[dict] = []

    async def fake_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        row = {
            "id": f"run-{strategy_id}-{params_kind}",
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "params_snapshot": dict(params_snapshot),
            "status": "queued",
        }
        inserted_rows.append(row)
        return row

    async def fake_update_status(run_id, status, **kwargs):
        update_records.append({"run_id": run_id, "status": status, **kwargs})
        return {"id": run_id, "status": status}

    monkeypatch.setattr(target_mod, "_db_insert_run", fake_insert_run, raising=False)
    monkeypatch.setattr(target_mod, "_db_update_status", fake_update_status, raising=False)
    return inserted_rows, update_records


_SUPPORTED_RUN_IDS = {
    f"run-{s}-{k}" for s in SUPPORTED for k in ("current", "recommended")
}
_FALLBACK_RUN_IDS = {
    f"run-{s}-{k}" for s in FALLBACK for k in ("current", "recommended")
}


# ---------------------------------------------------------------------------
# T1 (핵심 Red): 정적 enabled=False 이지만 DB 토글(is_enabled_async)=True → submit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_uses_db_toggle_true_over_static_env_false(
    monkeypatch: pytest.MonkeyPatch,
):
    """T1: is_enabled_async()=True (DB 토글 ON) + 정적 engine.enabled=False 일 때
    지원 3종이 'MCP 비활성' skip 되지 않고 run_for_strategy 로 submit 되어야 한다.

    현행 게이트(라인 548, 정적 engine.enabled 읽음)는 False 를 읽어 전량 skip → Red.
    """
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt

    target = date(2026, 7, 24)
    recs = _make_inserted_rows(target)
    _inserted, update_records = _install_db_doubles(monkeypatch, _bt)

    submit_calls: list[tuple[str, str]] = []

    class FakeEngine:
        # 정적 .env (프로세스 시작 시 고정) — 게이트가 이 값을 읽으면 전량 skip
        enabled = False

        async def is_enabled_async(self):
            # Settings UI 로 켠 DB 토글 (kis_mcp_enabled=true)
            return True

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            submit_calls.append((strategy_id, kind))
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)

    spawn_calls: list = []
    monkeypatch.setattr(
        _bt, "_spawn_backtest_poll_task", lambda td: spawn_calls.append(td), raising=False
    )

    await rec_mod._enqueue_backtest_jobs(target, recs)

    # (1) 지원 3종 × 2 kind = 6 submit — 현행은 정적 False → skip → submit 0 → 실패(Red)
    submitted = set(submit_calls)
    expected = {(s, k) for s in SUPPORTED for k in ("current", "recommended")}
    assert submitted == expected, (
        f"DB 토글 ON 이면 지원 3종이 submit 되어야 함 (현행 정적 False skip 결함): 실제={submitted}"
    )

    # (2) 지원 3종은 'MCP 비활성' skipped 되면 안 됨
    mcp_disabled = [
        u
        for u in update_records
        if u["status"] == "skipped"
        and u["run_id"] in _SUPPORTED_RUN_IDS
        and "비활성" in u.get("error_message", "")
    ]
    assert mcp_disabled == [], f"DB 토글 ON 인데 지원 전략 비활성 skip 발생: {mcp_disabled}"

    # (3) 지원 3종은 running 전이 + poll 발화
    running_ids = {u["run_id"] for u in update_records if u["status"] == "running"}
    assert running_ids == _SUPPORTED_RUN_IDS
    assert spawn_calls == [target]


# ---------------------------------------------------------------------------
# T2 (회귀): is_enabled_async()=False → 지원 3종 'MCP 비활성' skipped + submit 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_skips_supported_when_db_toggle_false(
    monkeypatch: pytest.MonkeyPatch,
):
    """T2: is_enabled_async()=False 면 지원 3종은 'MCP 비활성' skipped, run_for_strategy 미호출."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt

    target = date(2026, 7, 24)
    recs = _make_inserted_rows(target)
    _inserted, update_records = _install_db_doubles(monkeypatch, _bt)

    submit_calls: list[str] = []

    class FakeEngine:
        enabled = False

        async def is_enabled_async(self):
            return False

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            submit_calls.append(strategy_id)
            return "job-should-not-be-called"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)

    spawn_calls: list = []
    monkeypatch.setattr(
        _bt, "_spawn_backtest_poll_task", lambda td: spawn_calls.append(td), raising=False
    )

    await rec_mod._enqueue_backtest_jobs(target, recs)

    # 지원 3종 × 2 kind = 6 row 가 'MCP 비활성' skipped
    mcp_disabled = [
        u
        for u in update_records
        if u["status"] == "skipped" and u["run_id"] in _SUPPORTED_RUN_IDS
    ]
    assert {u["run_id"] for u in mcp_disabled} == _SUPPORTED_RUN_IDS
    for u in mcp_disabled:
        assert "비활성" in u.get("error_message", ""), f"지원 skipped 사유: {u}"

    # run_for_strategy 호출 0 + poll 미발화
    assert submit_calls == []
    assert spawn_calls == []


# ---------------------------------------------------------------------------
# T3 (회귀): 폴백 4종은 enabled 무관 항상 '로컬 백테스트 실행기 없음' skipped
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_fallback_always_skipped_regardless_of_toggle(
    monkeypatch: pytest.MonkeyPatch,
):
    """T3: _FALLBACK_STRATEGIES(kojiro/LTV/BFB/VCP) 는 토글 ON 이어도 '로컬 백테스트 실행기 없음' skipped.

    (게이트 *전* 분기이므로 enabled 무관 — kojiro 포함 4종 검증.)
    """
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt

    target = date(2026, 7, 24)
    recs = _make_inserted_rows(target)
    _inserted, update_records = _install_db_doubles(monkeypatch, _bt)

    submit_calls: list[str] = []

    class FakeEngine:
        enabled = True  # 토글 ON — 그럼에도 폴백은 항상 skip

        async def is_enabled_async(self):
            return True

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            submit_calls.append(strategy_id)
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(_bt, "_spawn_backtest_poll_task", lambda td: None, raising=False)

    await rec_mod._enqueue_backtest_jobs(target, recs)

    # 폴백 4종 × 2 kind = 8 row 가 skipped + 사유 = 로컬 백테스트 실행기 없음
    fallback_skipped = [
        u
        for u in update_records
        if u["status"] == "skipped" and u["run_id"] in _FALLBACK_RUN_IDS
    ]
    assert {u["run_id"] for u in fallback_skipped} == _FALLBACK_RUN_IDS
    for u in fallback_skipped:
        msg = u.get("error_message", "")
        assert "실행기" in msg, f"폴백 skipped 사유: {u}"

    # 폴백 전략은 BacktestEngine.run_for_strategy 호출 0 (kojiro 포함)
    assert not (set(submit_calls) & set(FALLBACK)), (
        f"폴백 전략이 submit 됨(호출 금지): {set(submit_calls) & set(FALLBACK)}"
    )


# ---------------------------------------------------------------------------
# T4 (회귀): DB 조회 예외 시 게이트도 graceful (.env fallback, 예외 전파 없음)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_graceful_when_db_toggle_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    """T4: is_enabled_async() 의 DB 조회가 예외를 던져도 .env fallback 으로 graceful.

    실제 BacktestEngine.is_enabled_async() 를 사용 (DB 예외 흡수 → 생성자 .env 값).
    게이트에서 예외가 전파되지 않아야 하며, .env=True fallback 으로 지원 3종 submit.
    """
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt
    from src.db import system_config

    async def raising_get_db():
        raise RuntimeError("DB down")

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", raising_get_db)

    from src.engine.backtest_engine import BacktestEngine

    class _FakeClient:
        async def call_tool(self, name, params):
            return {}

    engine = BacktestEngine(client=_FakeClient(), enabled=True)  # .env = True

    # run_for_strategy 는 mock 으로 MCP 실호출 차단 (인스턴스 attr 로 shadow)
    submit_calls: list[tuple[str, str]] = []

    async def fake_run_for_strategy(strategy_id, params, days=90, kind="current", **kw):
        submit_calls.append((strategy_id, kind))
        return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(engine, "run_for_strategy", fake_run_for_strategy, raising=False)
    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: engine, raising=False)

    target = date(2026, 7, 24)
    recs = _make_inserted_rows(target)
    _inserted, _updates = _install_db_doubles(monkeypatch, _bt)
    monkeypatch.setattr(_bt, "_spawn_backtest_poll_task", lambda td: None, raising=False)

    # 예외 전파 없이 완료되어야 한다 (게이트 graceful)
    await rec_mod._enqueue_backtest_jobs(target, recs)

    # .env fallback=True → 지원 3종 submit
    submitted = set(submit_calls)
    expected = {(s, k) for s in SUPPORTED for k in ("current", "recommended")}
    assert submitted == expected, (
        f"DB 예외 시 .env(True) fallback 으로 지원 3종 submit 되어야 함: 실제={submitted}"
    )
