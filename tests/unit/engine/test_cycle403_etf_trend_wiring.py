"""cycle403 Red — `etf_trend` 배선: 명부 8행 · 파생 집합 · 멀티데이 · 종목상태 그룹 · 카탈로그 · AI 튜닝 미편입 ·
DEFAULT_PARAMS 값 · 섀도 기본값 · 유니버스 SQL · 시드 마이그레이션 · 15:20 훅 통합 · 전략 파일 AST.

명세 정본 = `_workspace/cycle403_etf_trend_spec.md` §1 · §2(L1~L13) · §8 · §9 · §10-8 · §10-9

## Green 이 맞출 계약

- `src/engine/strategy_manifest.py` 명부 **끝** 행 = L2 그대로.
- `src/engine/param_catalog.py` — `_TURTLE4` 이름을 `_TURTLE_SIZED`(5전략, 명부 순서 무관 집합 비교)로 바꾸고
  별칭을 남기지 않는다. `STRATEGY_IDS[-1] == "etf_trend"`.
- `src/db/stock_master.py` — `async list_etf_trend_universe(min_market_cap_eok: int = 500) -> list[dict]`
  (행 = `ticker` · `name` · `hts_avls_eok`). `pg.fetch` 한 번으로 읽는다(테스트가 `pg.fetch` 를 바꿔 끼운다).
- `supabase/migrations/044_etf_trend_seed.sql` — 시드 1행, `ON CONFLICT (strategy_id) DO NOTHING`.
"""
from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SID = "etf_trend"
STRAT_REL = "src/engine/strategies/etf_trend.py"
MIGRATION = ROOT / "supabase" / "migrations" / "044_etf_trend_seed.sql"
KST = timezone(timedelta(hours=9))


def _cls():
    try:
        from src.engine.strategies.etf_trend import EtfTrendStrategy
    except ImportError as exc:  # pragma: no cover — Red 단계
        pytest.fail(f"[Red] {STRAT_REL} 미존재 — {exc}")
    return EtfTrendStrategy


# ===========================================================================
# §10-8 명부
# ===========================================================================
def test_manifest_has_eight_rows_with_etf_trend_last():
    from src.engine.strategy_manifest import STRATEGY_MANIFEST

    ids = [e.strategy_id for e in STRATEGY_MANIFEST]
    assert len(ids) == 8, f"[Red] 명부 {len(ids)}행 — etf_trend 등록 전"
    assert ids[-1] == SID, f"etf_trend 는 명부 끝(같은 틱 매수 우선순위 꼴찌): {ids}"
    assert ids[:7] == [
        "momentum", "volatility_breakout", "long_tail_volatility", "donchian_swing",
        "bull_flag_breakout", "vcp_breakout", "kojiro",
    ], "기존 7행 순서는 그대로"


def test_manifest_row_values_l2():
    from src.engine.strategy_manifest import STRATEGY_MANIFEST

    e = STRATEGY_MANIFEST[-1]
    assert e.strategy_id == SID
    assert e.cls is _cls()
    assert e.name == "ETF 추세"                       # L1
    assert e.enabled is False and e.weight == 0.0     # 시드 DB 가 실제 값을 싣는다
    assert e.eval_driver == "swing_poll"
    assert e.breakout_rank is None
    assert e.open_price_target is False
    assert e.close_at_1520 is True
    assert e.market_unit_policy == "scale"


def test_manifest_derived_sets_include_etf_trend():
    from src.engine import strategy_manifest as sm

    assert sm.SWING_POLL_IDS == ("donchian_swing", "kojiro", SID), "스윙 폴 순서 = donchian·kojiro 뒤"
    # cycle405 — donchian 이 15:20 시간 청산(20봉·250봉)으로 명부 순서대로 끼어든다.
    assert sm.CLOSE_AT_1520_IDS == ("volatility_breakout", "long_tail_volatility", "donchian_swing", SID)
    assert sm.MARKET_UNIT_SCALE_IDS[-1] == SID and len(sm.MARKET_UNIT_SCALE_IDS) == 5
    assert SID not in sm.BREAKOUT_IDS and SID not in sm.OPEN_PRICE_TARGET_IDS


def test_manifest_import_is_last_in_import_block():
    tree = ast.parse((ROOT / "src/engine/strategy_manifest.py").read_text(encoding="utf-8"))
    strat_imports = [
        n for n in tree.body
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src.engine.strategies.")
    ]
    assert strat_imports and strat_imports[-1].module == "src.engine.strategies.etf_trend", (
        "옛 import 순서를 보존하고 새 전략 import 는 블록 끝에 더한다(명세 §1)"
    )


def test_scheduler_registers_etf_trend_last():
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler()
    ids = [s.strategy_id for s in sched.registry.all()]
    assert ids[-1] == SID, ids
    s = sched.registry.get(SID)
    assert s.config.enabled is False and s.config.weight == 0.0


# ===========================================================================
# 멀티데이 · 종목상태 그룹 · 퍼널 순서
# ===========================================================================
def test_position_multiday_includes_etf_trend():
    from src.engine.strategy_base import Position

    assert SID in Position._MULTIDAY_STRATEGIES
    p = Position(ticker="990403", buy_price=10_000, quantity=1, order_no="O", strategy_id=SID,
                 buy_date=date.today() - timedelta(days=5))
    assert p.is_next_day is False, "멀티데이 — 「청산」 배지가 뜨면 안 된다"


def test_multiday_literal_stays_literal():
    """확장은 frozenset 리터럴에 멤버 추가로만(import-order 독립 단일 진실원)."""
    src = (ROOT / "src/engine/strategy_base.py").read_text(encoding="utf-8")
    m = re.search(r"_MULTIDAY_STRATEGIES:[^=]*=\s*frozenset\(\s*\{([^}]*)\}", src)
    assert m and '"etf_trend"' in m.group(1)


def test_status_exit_watch_group_is_swing():
    from src.engine import status_exit_watch as sew

    assert sew._GROUP.get(SID) == 3 == sew._SWING_GROUP, "스윙 폴 훅이 덮는 그룹(3)"


# ===========================================================================
# param_catalog — 등재 · _TURTLE_SIZED · 시장 유닛 적용 범위
# ===========================================================================
def test_catalog_strategy_ids_end_with_etf_trend():
    from src.engine import param_catalog as pc

    assert pc.STRATEGY_IDS[-1] == SID
    assert len(pc.STRATEGY_IDS) == 8


def test_catalog_turtle_sized_renamed_without_alias():
    from src.engine import param_catalog as pc
    from src.engine.strategy_manifest import MARKET_UNIT_SCALE_IDS

    assert hasattr(pc, "_TURTLE_SIZED"), "[Red] _TURTLE4 → _TURTLE_SIZED 개명 전"
    assert not hasattr(pc, "_TURTLE4"), "옛 이름 별칭을 남기지 않는다(명세 §1)"
    assert set(pc._TURTLE_SIZED) == {"donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro", SID}
    assert set(pc._TURTLE_SIZED) == set(MARKET_UNIT_SCALE_IDS)
    assert SID in pc.get_spec("market_unit_mode").applies_to


def test_catalog_covers_every_default_param_key():
    from src.engine import param_catalog as pc

    keys = set(_cls().DEFAULT_PARAMS)
    cat = set(pc.keys_for_strategy(SID))
    assert keys - cat == set(), f"카탈로그 미등재 키(PUT 통로가 막힌다): {sorted(keys - cat)}"
    assert cat - keys == set(), f"applies_to 에 etf_trend 를 넣었는데 DEFAULT_PARAMS 에 없는 키: {sorted(cat - keys)}"


# ===========================================================================
# L12 — DEFAULT_PARAMS 값 · AI 자동 튜닝 미편입
# ===========================================================================
#: 팀장 검토 MED-3 — donchian_period·long_ma_period·volume_period·atr_period·
#: channel_exit_period·atr_band_period 는 뺐다. leaf 가 재현 측정값(20·60·20·14·10·20)을
#: 상수로 고정해 PUT 해도 동작이 바뀌지 않는다.
L12_VALUES = {
    "volume_multiplier": 1.5,
    "atr_trail_mult": 1.8, "gap_skip_threshold": 3.0, "stop_atr": 2.0,
    "turtle_backstop_pct": -9.0, "breakeven_promote_atr": 1.5,
    "sizing_mode": "turtle", "risk_pct": 0.01, "position_ratio": 0.25, "max_positions": 4,
    "min_vol_floor_pct": 0.0, "min_market_cap": 50_000_000_000, "exchange": "KRX",
    "tradable_boards": ["main"],
    # 새 키
    "gap_over_line_pct": 4.0, "min_trade_amount_20d": 2_000_000_000, "min_price": 1_000,
    "max_price": 500_000, "atr_ratio_min": 0.01, "atr_ratio_max": 0.06,
    "min_bars": 100, "quality_window": 60, "daily_fetch_rows": 225, "cluster_corr_window": 120,
    "cluster_corr_min_obs": 60, "cluster_corr_threshold": 0.9, "breakout_fail_min_bars": 2,
    "breakout_fail_price_max_age_secs": 180,
    # 공통 키
    "max_lot_units": 2.0, "max_lot_ratio_mult": 2.5, "market_unit_mode": "shadow",
    "buy_paused": False, "order_exchange_clock_mode": "enforce", "after_market_exit_division": "44",
}
NEW_KEYS = (
    "gap_over_line_pct", "min_trade_amount_20d", "min_price", "max_price",
    "atr_ratio_min", "atr_ratio_max", "min_bars", "quality_window", "daily_fetch_rows",
    "cluster_corr_window", "cluster_corr_min_obs", "cluster_corr_threshold", "breakout_fail_min_bars",
    "breakout_fail_price_max_age_secs",
)
# `position_ratio` 는 7전략 공유 키라 이미 PARAM_RANGES 에 있다(전략별 제외 수단 없음) — 핸드백 「모호점」 참조.
IDENTITY_KEYS = (
    "max_positions", "risk_pct", "stop_atr", "atr_trail_mult", "turtle_backstop_pct",
    "breakeven_promote_atr", "max_lot_units", "max_lot_ratio_mult",
    "market_unit_mode", "buy_paused", "shadow_mode", "sizing_mode",
)


@pytest.mark.parametrize("key,want", sorted(L12_VALUES.items()))
def test_default_params_values(key, want):
    d = _cls().DEFAULT_PARAMS
    assert key in d, f"DEFAULT_PARAMS 에 {key} 없음"
    got = d[key]
    assert got == want and type(got) is type(want), f"{key}={got!r} (기대 {want!r})"


def test_shadow_mode_default_true_and_bool():
    d = _cls().DEFAULT_PARAMS
    assert d["shadow_mode"] is True, "L3 — 이 전략만 섀도로 시작(S1)"


def test_llm_and_loss_keys_match_donchian():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    d, ref = _cls().DEFAULT_PARAMS, DonchianSwingStrategy.DEFAULT_PARAMS
    for k in ("llm_gate_mode", "llm_gate_min_score", "llm_gate_daily_call_cap", "llm_gate_timeout_secs",
              "daily_loss_limit"):
        assert d.get(k) == ref[k], f"{k}: {d.get(k)!r} != donchian {ref[k]!r}"


def test_budget_invariant_and_boards():
    c = _cls()
    d = c.DEFAULT_PARAMS
    assert d["position_ratio"] * d["max_positions"] <= 1.0
    assert tuple(c.DEFAULT_TRADABLE_BOARDS) == ("main",)
    assert c._MARKET_UNIT_ATR_KEY == "atr", "시장 유닛 ATR 키 = 사이징 ATR 키(_candidates['atr'] = N)"


@pytest.mark.parametrize("key", NEW_KEYS + IDENTITY_KEYS)
def test_keys_not_ai_tunable(key):
    """L12 — 새 키·리스크 정체성 키는 PARAM_RANGES/INT_PARAMS 와 카탈로그 auto_tunable 에 없다."""
    from src.engine import param_catalog as pc
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert key not in PARAM_RANGES and key not in INT_PARAMS, f"{key} 가 AI 자동 튜닝 대상이다"
    spec = pc.get_spec(key)
    assert spec is not None, f"{key} 카탈로그 미등재"
    assert spec.auto_tunable is False


# ===========================================================================
# §4.1 유니버스 SQL — stock_master.list_etf_trend_universe
# ===========================================================================
def test_universe_signature():
    from src.db import stock_master as sm

    fn = getattr(sm, "list_etf_trend_universe", None)
    assert fn is not None, "[Red] stock_master.list_etf_trend_universe 미존재"
    assert inspect.iscoroutinefunction(fn)
    p = inspect.signature(fn).parameters["min_market_cap_eok"]
    assert p.default == 500


def _capture_universe(rows):
    import src.db.stock_master as sm

    with patch.object(sm, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = asyncio.run(sm.list_etf_trend_universe())
        calls = pg_mod.fetch.await_args_list
    return out, calls


def test_universe_sql_filters():
    rows = [{"ticker": "069500", "name": "KODEX 200", "hts_avls_eok": 100_000}]
    out, calls = _capture_universe(rows)
    assert len(calls) == 1, "한 번의 쿼리"
    sql, args = calls[0].args[0], calls[0].args[1:]
    for f in ("scty_grp_id_cd", "etf_txtn_type_cd", "etf_chas_erng_rt_dbnb", "etf_etn_ivst_heed_item_yn",
              "hts_avls_eok"):
        assert f in sql, f"SQL 에 {f} 판정이 없다"
    assert "EF" in sql or "EF" in args, "증권그룹코드 EF(ETF) 한정"
    assert 500 in args or "500" in sql, "시총 하한 500억"
    assert "'01'" in sql or "01" in args, "과세유형 01(국내주식형)"
    assert re.search(r"\[0-9\]|\\d", sql), "ticker 6자리 숫자 한정(정규식)"
    assert out and {"ticker", "name", "hts_avls_eok"} <= set(out[0])
    assert out[0]["ticker"] == "069500"


def test_universe_does_not_retype_group_code_literal():
    """cycle380 G6 — 그룹 코드는 etf_like 에서 가져온다(파이썬 리터럴 'EF' 금지)."""
    tree = ast.parse((ROOT / "src/db/stock_master.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "list_etf_trend_universe")
    lits = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and n.value == "EF"]
    assert lits == []


# ===========================================================================
# §9 시드 마이그레이션 (파일만 — 적용 금지)
# ===========================================================================
def test_seed_migration_file():
    assert MIGRATION.exists(), "[Red] supabase/migrations/044_etf_trend_seed.sql 미존재"
    sql = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))
    flat = " ".join(sql.split()).lower()
    assert "insert into strategy_config" in flat
    assert "'etf_trend'" in flat
    assert re.search(r"values\s*\(\s*'etf_trend'\s*,\s*false\s*,\s*0(\.0)?\s*,\s*'\{\}'::jsonb\s*\)", flat), flat
    assert "on conflict (strategy_id) do nothing" in flat
    assert "update " not in flat and "delete " not in flat and "drop " not in flat


def test_single_044_migration():
    files = sorted(p.name for p in (ROOT / "supabase" / "migrations").glob("044_*.sql"))
    assert files == ["044_etf_trend_seed.sql"], files


# ===========================================================================
# 전략 파일 AST — 게이트 첫 문장 · 관문 · 폴백 금지 · 순수 · TODO
# ===========================================================================
def _tree():
    p = ROOT / STRAT_REL
    if not p.exists():
        pytest.fail(f"[Red] {STRAT_REL} 미존재")
    return ast.parse(p.read_text(encoding="utf-8")), p.read_text(encoding="utf-8")


def _method(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "EtfTrendStrategy":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
                    return item
    pytest.fail(f"EtfTrendStrategy.{name} 없음")


def _body_no_doc(fn):
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body


def test_ast_gate_is_first_statement():
    tree, _ = _tree()
    first = _body_no_doc(_method(tree, "check_buy_signal"))[0]
    assert isinstance(first, ast.If)
    call = first.test
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    assert call.func.attr == "_account_soft_gate_blocked"


def test_ast_calc_never_falls_back_and_returns_through_gate():
    tree, _ = _tree()
    fn = _method(tree, "calc_buy_quantity")
    names = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    assert "_fallback_one_share" not in names, "1주 폴백 금지(L5)"
    for r in (n for n in ast.walk(fn) if isinstance(n, ast.Return)):
        v = r.value
        ok_zero = isinstance(v, ast.Constant) and v.value == 0
        ok_gate = (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                   and v.func.attr == "_apply_budget_limit")
        assert ok_zero or ok_gate, f"line {r.lineno}: 관문 밖 수량 반환"


@pytest.mark.parametrize("name", [
    "check_buy_signal", "calc_buy_quantity", "check_exit_signal", "check_force_clear",
    "get_effective_stop_price",
])
def test_ast_hot_path_is_sync_and_pure(name):
    tree, _ = _tree()
    fn = _method(tree, name)
    assert isinstance(fn, ast.FunctionDef), f"{name} 는 동기 함수"
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]


def test_ast_check_force_clear_wraps_everything():
    tree, _ = _tree()
    body = _body_no_doc(_method(tree, "check_force_clear"))
    assert len(body) == 1 and isinstance(body[0], ast.Try), "함수 전체 try/except — never-raise 계약"


def test_ast_shadow_gate_before_state_changes():
    tree, _ = _tree()
    fn = _method(tree, "check_buy_signal")
    src_lines = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    shadow = [n.lineno for n in src_lines if n.func.attr == "_shadow_buy_intercepted"]
    add = [n.lineno for n in src_lines if n.func.attr == "add"
           and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "_bought_today"]
    assert shadow, "섀도 관문 호출 없음"
    assert add and max(add) > max(shadow), "BUY 상태 변경(_bought_today.add)은 섀도 관문 뒤"


def test_force_clear_signal_is_trend_exit():
    """§12(cycle402 병합 반영) — L9 개정. force_clear_signal 은 TODO 없이 TREND_EXIT 를 바로 돌려준다."""
    from src.engine.strategy_base import Signal, resolve_force_clear_signal

    s = _cls()(__import__("src.engine.strategy_base", fromlist=["StrategyConfig"]).StrategyConfig(
        strategy_id=SID, name="ETF 추세", params={},
    ))
    assert s.force_clear_signal("990403") is Signal.TREND_EXIT
    assert resolve_force_clear_signal(s, "990403") is Signal.TREND_EXIT
    _, src = _tree()
    assert "TODO(cycle402" not in src, "병합 완료 — TODO 를 남기지 않는다(§12)"


def test_strategy_does_not_use_list_by_filter():
    tree, _ = _tree()
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and (
        (isinstance(n.func, ast.Attribute) and n.func.attr == "list_by_filter")
        or (isinstance(n.func, ast.Name) and n.func.id == "list_by_filter"))]
    assert calls == [], "ETF 를 사는 전략 — list_by_filter(exclude_etf_like=True) 대신 전용 유니버스"


def test_strategy_reads_scanner_via_local_import_only():
    """L10 — scanner 는 읽기만, 함수 지역 import(8영역 무접촉 · 순환 차단)."""
    tree, _ = _tree()
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    for n in top:
        mod = n.module if isinstance(n, ast.ImportFrom) else n.names[0].name
        assert mod not in ("src.engine.scanner",), "scanner 최상위 import 금지"


# ===========================================================================
# §10-9 통합 — 15:20 `_force_clear_main_only` 가 돌파선 아래 1종목만 판다
# ===========================================================================
@pytest.mark.asyncio
async def test_force_clear_main_only_sells_only_failed_breakout(monkeypatch):
    from src.engine import daily_emit_cap, scanner, scheduler, strategy_base
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import Position, Signal
    from tests.unit.engine._cycle369_support import Clock, frozen_datetime_class, kst

    _cls()
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    frozen = frozen_datetime_class(Clock(kst(15, 20, 30, day=date(2026, 9, 28))))
    for m_ in (mod, scheduler, strategy_base, daily_emit_cap):
        monkeypatch.setattr(m_, "datetime", frozen)   # naive·aware 같은 KST(15:20:30)
    sched = TradingScheduler()
    s = sched.registry.get(SID)
    assert s is not None, "[Red] etf_trend 미등록"
    s.config.enabled = True
    tick_at = datetime(2026, 9, 28, 15, 20, 0, tzinfo=KST)
    monkeypatch.setattr(scanner, "ticker_prices", {"990431": {"current_price": 9_900},
                                                   "990432": {"current_price": 10_100}})
    monkeypatch.setattr(scanner, "ticker_last_tick", {"990431": tick_at, "990432": tick_at})
    for t in ("990431", "990432"):
        s.state.positions[t] = Position(ticker=t, buy_price=10_000, quantity=3, order_no="O" + t,
                                        strategy_id=SID, buy_date=date(2026, 9, 23))
        s._breakout_line[t] = 10_000
        s._bars_since_buy[t] = 3
        s._entry_atr[t] = 200.0
    sell = AsyncMock()
    with patch.object(sched.order_engine, "execute_sell", new=sell), \
            patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched._force_clear_main_only()
    calls = [c for c in sell.await_args_list if c.args[2] == SID]
    # §12(cycle402 병합) — etf_trend 의 force_clear_signal 이 TREND_EXIT 를 돌려주므로
    # resolve_force_clear_signal 이 FORCE_CLEAR 대신 그 값을 쓴다.
    assert [(c.args[0], c.args[1]) for c in calls] == [("990431", Signal.TREND_EXIT)]
