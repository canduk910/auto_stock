"""시장 유닛 결정 과정 차트 — `GET /api/market-unit/chart` (cycle456). **읽기 전용 — 매매에 쓰지 않는다.**

시장마다(코스피 종합 `0001` · 코스닥 종합 `1001`) 최근 `CHART_BARS` 봉의 지수 시세(시가·고가·저가·종가)와
60일선, 그 봉 기준 판정(위·아래 × 상승·하락 → 배수)을 돌려준다. 판정은 **운영 판정 함수
`market_unit.classify` 를 그대로** 부른다(봉마다 그 봉까지 마지막 80봉 — 새 판정식 금지).
봉 D 의 판정은 **다음 거래일**의 신규 진입에 쓰인다(엔진은 `bas_dd < 오늘` 의 마지막 봉을 본다).

- `decision` = 오늘 판정을 운영 로더 `market_unit.compute_snapshot(오늘, market=)` 로 다시 낸 값
  (신선도 판정 포함 — 직전 영업일 봉이 없으면 `stale_head` · m=1).
- `engine` = 엔진 메모리의 오늘 스냅샷(`StrategyBase._market_unit_snaps` · `_kq`) 그대로. 엔진이
  아직 계산하지 않았으면 `null`. `effective` = 결측 대체 규칙을 적용한 실제 배수
  (제 시장 ok → 그 값 · 아니면 다른 시장 ok → 그 값 · 둘 다 아니면 1). 규칙의 정본 =
  `StrategyBase._market_unit_view` — 이 라우트는 같은 규칙을 화면용으로 되풀이한다.
- `modes` = 축소 대상(`strategy_manifest.MARKET_UNIT_SCALE_IDS`)마다 엔진 파라미터 `market_unit_mode`.
인증은 최외곽 미들웨어 단일 지점이 맡는다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.db import _kst
from src.db import domestic_index
from src.engine import market_unit
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-unit", tags=["market-unit"])

CHART_BARS = 120
_FETCH_ROWS = CHART_BARS + market_unit.MIN_ROWS
MARKET_NAME_KO = {"kospi": "코스피 종합", "kosdaq": "코스닥 종합"}


def _bars_payload(bars: list[dict]) -> list[dict]:
    closes = [b["close"] for b in bars]
    out = []
    w = market_unit.MA_WINDOW
    for i, b in enumerate(bars):
        sma60 = sum(closes[i - w + 1:i + 1]) / w if i + 1 >= w else None
        c, reason = market_unit.classify(closes[:i + 1]) if i + 1 >= market_unit.MIN_ROWS else (None, "rows_short")
        out.append({
            "date": b["bas_dd"].isoformat(),
            "open": b.get("open"), "high": b.get("high"), "low": b.get("low"), "close": b["close"],
            "sma60": sma60,
            "sma60_prev": c.sma60_prev if c else None,
            "above": c.above if c else None,
            "rising": c.rising if c else None,
            "state": c.state if c else None,
            "m": c.m if c else None,
        })
    return out[-CHART_BARS:]


def _snap_dict(snap) -> "dict | None":
    if snap is None:
        return None
    bd = getattr(snap, "bar_date", None)
    eh = getattr(snap, "expected_head", None)
    return {
        "ok": bool(getattr(snap, "ok", False)),
        "state": getattr(snap, "state", None),
        "m": getattr(snap, "m", None),
        "reason": getattr(snap, "reason", None),
        "bar_date": bd.isoformat() if bd is not None else None,
        "expected_head": eh.isoformat() if eh is not None else None,
        "close": getattr(snap, "close", None),
        "sma60": getattr(snap, "sma60", None),
        "sma60_prev": getattr(snap, "sma60_prev", None),
        "above": getattr(snap, "above", None),
        "rising": getattr(snap, "rising", None),
    }


def _engine_side(today) -> "tuple[dict, dict]":
    """(시장별 엔진 오늘 스냅샷, 전략별 모드). 엔진·전략을 못 읽으면 스냅샷 None · 모드 None."""
    from src.engine import scheduler as _sched
    from src.engine.strategy_manifest import MARKET_UNIT_SCALE_IDS

    engine: dict = {m: None for m in market_unit.MARKETS}
    modes: dict = {}
    for sid in MARKET_UNIT_SCALE_IDS:
        try:
            strat = _sched.trading_scheduler.registry.get(sid)
        except Exception:
            strat = None
        if strat is None:
            modes[sid] = None
            continue
        try:
            modes[sid] = market_unit.normalize_mode(strat.config.params.get(market_unit.MODE_KEY))[0]
        except Exception:
            modes[sid] = None
        for mk in market_unit.MARKETS:
            if engine[mk] is not None:
                continue
            try:
                snaps = strat._market_unit_snaps_of(mk)
                engine[mk] = _snap_dict(snaps.get(today)) if isinstance(snaps, dict) else None
            except Exception:
                engine[mk] = None
    return engine, modes


def _effective(engine: dict) -> dict:
    out = {}
    for mk in market_unit.MARKETS:
        own = engine.get(mk)
        other_mk = next(o for o in market_unit.MARKETS if o != mk)
        other = engine.get(other_mk)
        if own is None and other is None:
            out[mk] = {"m": None, "fallback": "not_computed", "from_market": None}
        elif own and own.get("ok"):
            out[mk] = {"m": own["m"], "fallback": "-", "from_market": mk}
        elif other and other.get("ok"):
            out[mk] = {"m": other["m"], "fallback": "other_market", "from_market": other_mk}
        else:
            out[mk] = {"m": 1.0, "fallback": "none", "from_market": None}
    return out


@router.get("/chart", response_model=ApiResponse)
async def get_market_unit_chart() -> ApiResponse:
    today = _kst.today_kst()
    markets = {}
    for mk in market_unit.MARKETS:
        code = market_unit.INDEX_CODE_BY_MARKET[mk]
        bars = await domestic_index.get_recent_bars(code, limit=_FETCH_ROWS)
        bars = [b for b in bars if b["bas_dd"] < today]
        try:
            decision = _snap_dict(await market_unit.compute_snapshot(today, preview=True, market=mk))
        except Exception:
            logger.warning("[market_unit_chart] compute_snapshot 실패 market=%s", mk, exc_info=True)
            decision = None
        markets[mk] = {
            "index_code": code,
            "name": MARKET_NAME_KO.get(mk, mk),
            "rows": len(bars),
            "bars": _bars_payload(bars),
            "decision": decision,
        }
    try:
        engine, modes = _engine_side(today)
    except Exception:
        logger.warning("[market_unit_chart] 엔진 상태 읽기 실패", exc_info=True)
        engine, modes = {m: None for m in market_unit.MARKETS}, {}
    for mk in market_unit.MARKETS:
        markets[mk]["engine"] = engine.get(mk)
    effective = _effective(engine)
    for mk in market_unit.MARKETS:
        markets[mk]["effective"] = effective[mk]

    data = {
        "as_of": today.isoformat(),
        "markets": markets,
        "modes": modes,
        "rules": {
            "ma_window": market_unit.MA_WINDOW,
            "slope_lookback": market_unit.SLOPE_LOOKBACK,
            "min_rows": market_unit.MIN_ROWS,
            "multipliers": dict(market_unit.MULTIPLIERS),
        },
    }
    return ApiResponse(success=True, data=data, message="")
