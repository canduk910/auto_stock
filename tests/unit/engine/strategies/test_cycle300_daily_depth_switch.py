"""cycle300 (2026-09-18) — 일봉 읽기 100행 클램프 해제 + VCP 깊이 스위치.

무엇을 여는가
=============
cycle299 가 **적재** 깊이를 열었다(retention 390달력일 ≈261영업일 · VCP backfill target
225영업일). 그런데 **읽는 쪽**이 100행에서 막혀 있어 그 깊이가 전략에 닿지 않았다.
막고 있던 것은 두 겹이다.

1. `src/db/stock_master_daily.get_recent_daily` 의 `max(1, min(days, 100))`
   — 행을 돌려주는 읽기 4함수(`get_donchian_high`·`get_atr`·
   `get_recent_daily_with_fallback`·`get_recent_daily_normalized`)가 전부 경유하는 공통 관문.
2. `src/engine/strategies/vcp_breakout.py` 의 `KIS_DAILY_CANDLES_MAX = 100`.

왜 여는가 — 실효 EMA
====================
`effective_ema_long = min(ema_long, 보유 − long_ema_uptrend_days(20) − 5)` 이고, 그 뒤
`_check_trend_filter` 가 `ema_mid >= ema_long` 이면 `ema_mid = max(ema_short+1, ema_long−10)`
로 중기선을 다시 줄인다. 운영 DB VCP params(50/150/200)에서:

    보유 100봉 → 실효 정렬 50/ 65/ 75   (mid↔long 간격 10 = 정배열이 동전던지기)
    보유 225봉 → 실효 정렬 50/150/200   (간격 50)

`vcp_breakout.py` 주석이 앞쪽을 「추세필터 0건 결함」이라 부른다. G-300-7 이 이 표를
**실제 계산**으로 봉인한다.

어떻게 여는가 — 파라미터 스위치, 기본값은 꺼짐
==============================================
- 클램프 상한을 명명 상수 `_MAX_DAILY_ROWS` 로 올린다(`min()` 구조 자체는 유지 = 폭주 방어).
- VCP 전용 키 `daily_fetch_depth_mode` (`"cap100"` 기본 / `"full"`) 를 신설한다.
  기본값에서 `fetch_days` 는 **정확히 100** 으로 현행과 byte 동일하고, `"full"` 에서만
  `ema_long + base_max_days + 10` 을 요청한다. DB 에 있는 만큼만 오므로
  `effective_ema_long` 이 자연히 따라온다.
- 켜고 끄는 수단은 `PUT /api/strategies/vcp_breakout/params` 다(즉시 반영 + 영속).
  `strategy_config` SQL UPDATE 는 다음 재시작에서만 반영된다(cycle232 D6).

가드 매트릭스
=============
- G-300-1  `_MAX_DAILY_ROWS` 존재 + `get_recent_daily` 가 `max(1, min(days, 상수))` 유지
- G-300-2  클램프 상한 ≥ VCP full 요청(코드 기본값·운영 DB 값 양쪽) — 상향이 조용히 절단하지 않는다
- G-300-3  기본값 `fetch_days == 100` (현행 byte 동일 봉인) + `min_required == 100`
- G-300-4  `full` 에서 `fetch_days == ema_long + base_max_days + 10`
- G-300-5  `daily_fetch_depth_mode` ∉ `PARAM_RANGES`/`INT_PARAMS` (런타임 dict + 소스 리터럴 이중)
- G-300-6  다른 소비처 무영향 — 20/14/90/60/100 요청이 그대로 `LIMIT` 에 실린다
- G-300-7  실효 EMA 표 — 100봉 → 50/65/75 · 225봉 → 50/150/200
- G-300-8  미지 값·결측·비문자열은 전부 기본(`cap100`) 으로 낙하 (fail-safe = 현행 보존)
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

KST = timezone(timedelta(hours=9))
pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_DB_DAILY = _REPO_ROOT / "src" / "db" / "stock_master_daily.py"
_VCP = _REPO_ROOT / "src" / "engine" / "strategies" / "vcp_breakout.py"

KEY = "daily_fetch_depth_mode"

#: 운영 DB 의 VCP 추세 필터 값(2026-09-15 실측표). 코드 기본값(50/60/120)과 다르다.
_LIVE_EMA_SHORT = 50
_LIVE_EMA_MID = 150
_LIVE_EMA_LONG = 200
_UPTREND_DAYS = 20


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _kis_candles(n: int, *, base_close: int = 50_000) -> list[dict]:
    """KIS 원본 키 일봉(DESC, 최신 우선). 오늘 날짜 봉은 만들지 않는다."""
    today = datetime.now(KST).date()
    rows = []
    for i in range(n):
        dd = today - timedelta(days=i + 1)
        close = base_close - i * 20
        rows.append({
            "stck_bsop_date": dd.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_oprc": str(close - 50),
            "stck_hgpr": str(close + 200),
            "stck_lwpr": str(close - 200),
            "acml_vol": str(1_000_000 + i * 100),
            "acml_tr_pbmn": str(50_000_000_000),
            "prdy_ctrt": "1.0",
        })
    return rows


def _func_node(source: str, name: str) -> ast.AST:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 함수 정의를 찾지 못했다 (cycle300 미구현 또는 개명)")


def _make_vcp(**param_overrides):
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    return VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", params=dict(param_overrides))
    )


async def _capture_prepare_fetch(strategy, candles: list[dict]) -> dict:
    """`prepare()` 가 어댑터에 넘긴 `days`/`min_required` 를 캡처한다."""
    seen: dict = {}

    async def _fake_adapter(ticker, days=None, *, min_required=None):
        seen["days"] = days
        seen["min_required"] = min_required
        return list(candles)

    with patch.object(strategy, "_scan_universe", new=AsyncMock(return_value=["005930"])), \
            patch.object(strategy, "_apply_master_block_filter_in_prepare",
                         new=AsyncMock(return_value=(["005930"], []))), \
            patch("src.db.stock_master_daily.get_recent_daily_normalized",
                  new=_fake_adapter):
        await strategy.prepare()
    assert seen, "prepare 가 일봉 어댑터를 부르지 않았다"
    return seen


# ===========================================================================
# G-300-1 — 클램프 상수화 (min() 구조 유지)
# ===========================================================================
def test_g300_1_max_daily_rows_constant_exists():
    """`_MAX_DAILY_ROWS` 모듈 상수 존재 + 100 초과.

    무엇을 재는가: 100행 관문이 실제로 열렸는가. 이 상수가 없거나 100 이면 cycle299 가
    적재해 둔 깊이가 어느 소비처에도 닿지 못한다.
    """
    from src.db import stock_master_daily as smd

    assert hasattr(smd, "_MAX_DAILY_ROWS"), (
        "cycle300 — get_recent_daily 읽기 상한을 명명 상수 `_MAX_DAILY_ROWS` 로 올린다"
    )
    assert isinstance(smd._MAX_DAILY_ROWS, int) and not isinstance(smd._MAX_DAILY_ROWS, bool)
    assert smd._MAX_DAILY_ROWS > 100, (
        f"_MAX_DAILY_ROWS={smd._MAX_DAILY_ROWS} — 100 이하면 클램프가 열리지 않은 것이다"
    )


def test_g300_1b_get_recent_daily_keeps_min_max_clamp_shape():
    """`get_recent_daily` 가 `max(1, min(days, _MAX_DAILY_ROWS))` 형태를 유지한다.

    무엇을 재는가: **상한을 올리되 구조는 지운 적 없다**. `min()` 을 통째로 지우면
    호출자가 넘긴 어떤 수(오염된 DB 값·버그)도 그대로 `LIMIT` 에 실려 폭주한다.
    하한 `max(1, …)` 은 `LIMIT 0`/음수를 막는다.
    """
    source = _DB_DAILY.read_text(encoding="utf-8")
    node = _func_node(source, "get_recent_daily")

    found_min = False
    for sub in ast.walk(node):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                and sub.func.id == "min"):
            continue
        names = {n.id for a in sub.args for n in ast.walk(a) if isinstance(n, ast.Name)}
        if "days" in names and "_MAX_DAILY_ROWS" in names:
            found_min = True
    assert found_min, (
        "get_recent_daily 본체에 `min(days, _MAX_DAILY_ROWS)` 존재 의무 — "
        "클램프 구조 자체를 지우지 않는다(폭주 방어)"
    )

    found_max = any(
        isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "max"
        and any(isinstance(a, ast.Constant) and a.value == 1 for a in sub.args)
        for sub in ast.walk(node)
    )
    assert found_max, "하한 `max(1, …)` 존속 의무 (LIMIT 0/음수 차단)"


# ===========================================================================
# G-300-2 — 상한 ≥ VCP full 요청 (상향이 조용히 절단하지 않는다)
# ===========================================================================
@pytest.mark.parametrize(
    "ema_long,base_max,label",
    [
        (_LIVE_EMA_LONG, 75, "운영 DB(ema_long=200)"),
        (120, 75, "얕은 깊이 대조군(ema_long=120, cycle301 이전 코드 기본값)"),
    ],
)
def test_g300_2_clamp_covers_vcp_full_request(ema_long: int, base_max: int, label: str):
    """클램프 상한이 VCP full 요청(`ema_long + base_max_days + 10`)보다 크다.

    무엇을 재는가: 스위치를 켜도 **관문이 조용히 자르지 않는가**. 상한 < 요청이면
    `full` 모드가 이름만 full 이고 실제 행 수는 상한에 묶여 실효 EMA 가 또 어긋난다.
    """
    from src.db.stock_master_daily import _MAX_DAILY_ROWS

    requested = ema_long + base_max + 10
    assert _MAX_DAILY_ROWS >= requested, (
        f"{label}: full 요청 {requested}봉 > 클램프 상한 {_MAX_DAILY_ROWS} — "
        f"상향이 요청을 조용히 절단한다"
    )


def test_g300_2b_clamp_is_bounded_not_unlimited():
    """상한은 유한하고 retention 이 보유 가능한 영업일(≈261)보다 크다.

    무엇을 재는가: 무한대로 풀지 않았다는 것과, 그럼에도 DB 가 실제로 들고 있는
    깊이를 자르지 않는다는 것. 두 조건 사이가 이 상수의 정당한 자리다.
    """
    from src.db.stock_master_daily import _MAX_DAILY_ROWS, DAILY_RETENTION_DAYS

    # 환산 앵커 = 사이클196 실측 230 달력일 ⇄ 154 영업일.
    retained_trading = int(DAILY_RETENTION_DAYS * 154 / 230)
    assert _MAX_DAILY_ROWS >= retained_trading, (
        f"상한 {_MAX_DAILY_ROWS} < retention 보유 영업일 {retained_trading} — "
        f"DB 가 실제로 들고 있는 행을 관문이 자른다"
    )
    assert _MAX_DAILY_ROWS <= 1000, (
        f"상한 {_MAX_DAILY_ROWS} 가 과도하다 — 폭주 방어의 의미가 사라진다"
    )


# ===========================================================================
# G-300-3 — 기본값에서 현행 byte 동일 (fetch_days 정확히 100)
# ===========================================================================
@pytest.mark.asyncio
async def test_g300_3_default_mode_requests_exactly_100():
    """기본값(스위치 미설정)에서 `prepare` 가 요청하는 `fetch_days` 가 **정확히 100**.

    무엇을 재는가: 이 사이클의 배포가 **매매 행위를 바꾸지 않는다**는 봉인.
    운영 DB 값(ema_long=200)을 넣어도 기본 모드면 100 이어야 한다.
    """
    strat = _make_vcp(
        ema_short=_LIVE_EMA_SHORT, ema_mid=_LIVE_EMA_MID, ema_long=_LIVE_EMA_LONG,
        base_max_days=75, max_scan_stocks=10,
    )
    seen = await _capture_prepare_fetch(strat, _kis_candles(120))

    assert seen["days"] == 100, f"기본 모드 fetch_days={seen['days']} (기대 100)"
    assert seen["min_required"] == 100, (
        f"min_required={seen['min_required']} (기대 100) — KIS 폴백 문턱은 그대로 둔다. "
        "올리면 DB 가 100~224봉인 구간에서 폴백이 잦아지는데, KIS 단일 호출은 100봉이 "
        "상한이라 더 얕은 데이터로 바뀐다(개선이 아니라 퇴보)."
    )


@pytest.mark.asyncio
async def test_g300_3b_explicit_cap100_mode_requests_exactly_100():
    """명시 `"cap100"` 도 100 — 기본값과 같은 경로."""
    strat = _make_vcp(
        ema_long=_LIVE_EMA_LONG, base_max_days=75, max_scan_stocks=10,
        **{KEY: "cap100"},
    )
    seen = await _capture_prepare_fetch(strat, _kis_candles(120))
    assert seen["days"] == 100


# ===========================================================================
# G-300-4 — full 모드
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("ema_long,base_max", [(_LIVE_EMA_LONG, 75), (120, 75)])
async def test_g300_4_full_mode_requests_full_depth(ema_long: int, base_max: int):
    """`"full"` 에서 `fetch_days == ema_long + base_max_days + 10`.

    무엇을 재는가: 스위치가 실제로 깊이를 연다는 것. DB 에 있는 만큼만 오므로
    행 수가 모자라도 안전하고, `effective_ema_long` 이 그 실제 행 수를 따라간다.
    """
    strat = _make_vcp(
        ema_short=_LIVE_EMA_SHORT, ema_mid=_LIVE_EMA_MID, ema_long=ema_long,
        base_max_days=base_max, max_scan_stocks=10, **{KEY: "full"},
    )
    seen = await _capture_prepare_fetch(strat, _kis_candles(240))

    assert seen["days"] == ema_long + base_max + 10, (
        f"full 모드 fetch_days={seen['days']} (기대 {ema_long + base_max + 10})"
    )
    assert seen["min_required"] == 100, "full 모드도 KIS 폴백 문턱은 100 그대로"


# ===========================================================================
# G-300-5 — AI 야간 튜닝 차단 (런타임 dict + 소스 리터럴 이중)
# ===========================================================================
def test_g300_5_key_not_auto_tunable_runtime():
    """`daily_fetch_depth_mode` ∉ `PARAM_RANGES` / `INT_PARAMS` (런타임 dict).

    무엇을 재는가: AI 자문이 매일 밤 이 스위치를 뒤집지 못한다는 것. 읽기 깊이는
    추세 필터의 실효 EMA 를 통째로 바꾸므로 전략 정체성 축이다.
    """
    from src.engine import recommendation_engine as rec

    assert KEY not in rec.PARAM_RANGES, f"{KEY} 가 PARAM_RANGES 에 있다 (AI 튜닝 대상)"
    assert KEY not in rec.INT_PARAMS, f"{KEY} 가 INT_PARAMS 에 있다"


def test_g300_5b_key_not_auto_tunable_source_literal():
    """소스 리터럴 이중 확인 — 런타임 dict 가 다른 곳에서 변형돼도 잡는다."""
    source = (_REPO_ROOT / "src" / "engine" / "recommendation_engine.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ("PARAM_RANGES", "INT_PARAMS")
            for t in node.targets
        ):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id in ("PARAM_RANGES", "INT_PARAMS"):
            value = node.value
        if value is None:
            continue
        literals = [
            n.value for n in ast.walk(value)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        assert KEY not in literals, f"{KEY} 리터럴이 PARAM_RANGES/INT_PARAMS 에 박혀 있다"


def test_g300_5c_key_registered_for_put():
    """`DEFAULT_PARAMS` + `param_catalog` 양쪽 등재 — PUT 이 422 로 막히지 않는다.

    무엇을 재는가: 장중에 **끌 수 있는가**. `param_validation` 의 미지 키 판정은
    `key not in current_params or spec is None` 이라 둘 다 필요하다(한쪽만이면 422).
    """
    from src.engine import param_catalog as pc
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    assert KEY in VcpBreakoutStrategy.DEFAULT_PARAMS, "VCP DEFAULT_PARAMS 등재 의무"
    assert VcpBreakoutStrategy.DEFAULT_PARAMS[KEY] == "cap100", (
        "기본값은 현행 보존 쪽(cap100)"
    )

    spec = pc.SPEC_BY_KEY.get(KEY)
    assert spec is not None, "param_catalog 등재 의무 (없으면 PUT 이 unknown_key 422)"
    assert spec.applies_to == ("vcp_breakout",), spec.applies_to
    assert spec.editable is True
    assert spec.auto_tunable is False
    allowed = {c.value for c in (spec.choices or ())}
    assert allowed == {"cap100", "full"}, allowed


# ===========================================================================
# G-300-6 — 다른 소비처 무영향
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requested,label",
    [
        (20, "donchian 20일 신고가"),
        (15, "get_atr(14) → days+1"),
        (90, "매크로 ETF 레짐 _ETF_STAGE_LOOKBACK_DAYS"),
        (60, "LLM 매수평가 _BARS_FETCH_DAYS"),
        (100, "kojiro KOJIRO_FETCH_DAYS"),
    ],
)
async def test_g300_6_other_consumers_receive_same_row_count(requested: int, label: str):
    """100 이하를 요청하는 소비처는 클램프 상향 전후로 **같은 행 수**를 받는다.

    무엇을 재는가: 이 사이클이 VCP 밖으로 새지 않는다는 것. 클램프는 `min()` 이라
    요청이 상한보다 작으면 요청값이 그대로 `LIMIT` 에 실린다.
    """
    from src.db import stock_master_daily as smd

    captured: list = []

    async def _fake_fetch(sql, *args):
        captured.append(args)
        return []

    with patch.object(smd.pg, "fetch", new=_fake_fetch):
        await smd.get_recent_daily("005930", requested)

    assert captured, "pg.fetch 가 불리지 않았다"
    assert captured[0][1] == requested, (
        f"{label}: LIMIT {captured[0][1]} (요청 {requested}) — 클램프가 행 수를 바꿨다"
    )


@pytest.mark.asyncio
async def test_g300_6b_clamp_still_bounds_absurd_request():
    """상한을 넘는 요청은 여전히 잘린다(폭주 방어가 살아 있다)."""
    from src.db import stock_master_daily as smd

    captured: list = []

    async def _fake_fetch(sql, *args):
        captured.append(args)
        return []

    with patch.object(smd.pg, "fetch", new=_fake_fetch):
        await smd.get_recent_daily("005930", 999_999)
        await smd.get_recent_daily("005930", 0)

    assert captured[0][1] == smd._MAX_DAILY_ROWS, "상한 초과 요청은 상한으로 잘린다"
    assert captured[1][1] == 1, "0 이하 요청은 1 로 올린다"


# ===========================================================================
# G-300-7 — 실효 EMA 표 (실제 계산으로 봉인)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows,expected_long",
    [(100, 75), (225, 200)],
)
async def test_g300_7_effective_ema_long_table(rows: int, expected_long: int):
    """보유 행수 → `effective_ema_long` — 100봉이면 75, 225봉이면 200.

    무엇을 재는가: **왜 이 사이클을 하는가**의 숫자 근거. 100봉에서는 장기선이
    75 로 잘려 `ema_mid` 재축소까지 걸리고(아래 7b), 225봉에서 비로소 운영 DB 가
    설정한 200 이 그대로 산다.

    계산식 = `min(ema_long, available_len - long_ema_uptrend_days - 5)` (prepare 본문).
    """
    strat = _make_vcp(
        ema_short=_LIVE_EMA_SHORT, ema_mid=_LIVE_EMA_MID, ema_long=_LIVE_EMA_LONG,
        base_max_days=75, max_scan_stocks=10, long_ema_uptrend_days=_UPTREND_DAYS,
        **{KEY: "full"},
    )
    seen_eff: list[int] = []
    real_filter = type(strat)._check_trend_filter

    def _spy(self, candles, *, effective_ema_long=None):
        seen_eff.append(effective_ema_long)
        return real_filter(self, candles, effective_ema_long=effective_ema_long)

    with patch.object(type(strat), "_check_trend_filter", new=_spy):
        await _capture_prepare_fetch(strat, _kis_candles(rows))

    assert seen_eff and seen_eff[0] == expected_long, (
        f"보유 {rows}봉 → effective_ema_long={seen_eff[0] if seen_eff else None} "
        f"(기대 {expected_long})"
    )


@pytest.mark.parametrize(
    "effective_long,expected_periods",
    [
        (75, (50, 65, 75)),
        (200, (50, 150, 200)),
    ],
)
def test_g300_7b_effective_alignment_triplet(effective_long: int, expected_periods):
    """실효 정렬 3선 — 75 에서는 50/65/75, 200 에서는 50/150/200.

    무엇을 재는가: `ema_mid >= ema_long` 재축소(`max(ema_short+1, ema_long-10)`)가
    100봉 세계에서 중기선을 65 까지 끌어내려 **중기↔장기 간격이 10** 이 된다는 사실.
    그 간격에서는 정배열 판정이 사실상 동전던지기다.

    측정은 실제 `_check_trend_filter` 가 `_ema(...)` 에 넘긴 period 로 한다.
    """
    strat = _make_vcp(
        ema_short=_LIVE_EMA_SHORT, ema_mid=_LIVE_EMA_MID, ema_long=_LIVE_EMA_LONG,
        long_ema_uptrend_days=_UPTREND_DAYS,
    )
    periods: list[int] = []

    def _spy_ema(series, period):
        periods.append(period)
        return 0.0

    with patch.object(strat, "_ema", new=_spy_ema):
        strat._check_trend_filter(
            _kis_candles(effective_long + _UPTREND_DAYS + 5),
            effective_ema_long=effective_long,
        )

    assert tuple(periods[:3]) == expected_periods, (
        f"실효 정렬 {tuple(periods[:3])} (기대 {expected_periods})"
    )


# ===========================================================================
# G-300-8 — fail-safe (미지 값은 현행 보존 쪽으로)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "  ", "FULL_DEPTH", "off", "enforce", None, 1, [], 0])
async def test_g300_8_unknown_value_falls_back_to_cap100(bad):
    """미지 값·결측·비문자열은 전부 `cap100` 으로 낙하한다.

    무엇을 재는가: 오염된 DB 값이 **매매를 바꾸지 않는** 방향으로 떨어지는가.
    이 스위치의 안전 방향은 '현행 보존' 이다.
    """
    strat = _make_vcp(
        ema_long=_LIVE_EMA_LONG, base_max_days=75, max_scan_stocks=10, **{KEY: bad},
    )
    seen = await _capture_prepare_fetch(strat, _kis_candles(120))
    assert seen["days"] == 100, f"{bad!r} → fetch_days={seen['days']} (기대 100)"


@pytest.mark.asyncio
@pytest.mark.parametrize("ok", ["full", "FULL", " Full "])
async def test_g300_8b_full_value_is_case_and_space_insensitive(ok: str):
    """`"full"` 판정은 대소문자·공백 무시 정확 일치 (cycle272 관례 답습)."""
    strat = _make_vcp(
        ema_long=_LIVE_EMA_LONG, base_max_days=75, max_scan_stocks=10, **{KEY: ok},
    )
    seen = await _capture_prepare_fetch(strat, _kis_candles(240))
    assert seen["days"] == _LIVE_EMA_LONG + 75 + 10, f"{ok!r} → {seen['days']}"


# ===========================================================================
# 소스 봉인 — cap100 분기의 표현이 남아 있다
# ===========================================================================
def test_g300_9_cap100_branch_expression_survives():
    """기본 분기가 여전히 `min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)` 다.

    무엇을 재는가: 스위치를 다는 과정에서 **기본 경로를 다시 쓰지 않았다**는 것.
    기존 가드(cycle173 G-VCP-3 · cycle299 G-299-7b)가 같은 두 줄을 재고 있으므로
    여기서 깨지면 그쪽도 함께 붉어진다.
    """
    source = _VCP.read_text(encoding="utf-8")
    assert "KIS_DAILY_CANDLES_MAX = 100" in source
    assert "min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)" in source
