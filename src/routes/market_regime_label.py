"""6장세 라벨 라우트 — `GET /api/market-regime-label` (cycle410). **관찰 전용 — 매매에 쓰지 않는다.**

판정은 순수 leaf(`src/engine/market_regime_label.py`)가 하고, 읽기(`stock_master_daily` 의
`069500` 최근 400행)는 여기서만 한다. 오늘(KST) 날짜 봉은 버린다 — D 일 라벨은 D-1 종가까지다.

- 운영 DB 종가를 읽으므로 운영 엔진과 같은 재료다. ETF 보관소 종가(골든 테스트 기준)와는 2025-10 이후
  약 1% 다른 날이 있어 화면 값이 골든과 다를 수 있다.
- `basis_date` = 쓴 마지막 봉 날짜. 20:30 에 적재된 그날 봉은 다음 아침 확정 전까지 잠정이라
  장 마감 뒤 ~ 다음 아침에는 이 봉이 잠정값일 수 있다.
- `warmup_from` = 읽은 첫 봉 날짜. 상태는 이 날부터 걸어 오므로 시작점이 다르면 첫 구간이
  달라질 수 있다. `since_truncated=true` 면 `since` 는 하한일 뿐이다.
- 데이터 부족·나쁜 종가 = 200 + `success=false` + 사유(빈 화면으로 위장하지 않는다).
- 시장 유닛(`market_unit`)은 **운영 판정 함수 `market_unit.classify` 를 그대로** 부른다(새 판정식 금지 —
  오늘·history 날짜마다 그 날 이전 마지막 80봉). 운영 로더 `compute_snapshot` 과 같은 창이다
  (대조 테스트 MU2). 다만 신선도 판정(직전 영업일 봉이 없으면 m=1)은 휴장일 조회를 부르지 않으려고
  여기서 되풀이하지 않는다 — `basis_date` 로 보인다. `modes` = 축소 대상
  (`strategy_manifest.MARKET_UNIT_SCALE_IDS`)마다 운영 엔진 파라미터의 `market_unit_mode`.
인증은 최외곽 미들웨어 단일 지점이 맡는다.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter

from src.db import _kst
from src.db import stock_master_daily
from src.engine import market_regime_label as mrl
from src.engine import market_unit
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-regime-label", tags=["market-regime-label"])

_FETCH_ROWS = 400
_HISTORY_DAYS = 60
_UNIT_SOURCE = "db_recompute"


def _bar_date(raw) -> "date | None":
    if isinstance(raw, date):
        return raw if type(raw) is date else raw.date()
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _unit(closes: list) -> "market_unit.Classification | None":
    c, reason = market_unit.classify(closes[-market_unit.MIN_ROWS:])
    return c if reason == "ok" else None


def _read_modes() -> "dict[str, str | None]":
    """축소 대상 전략마다 운영 엔진의 `market_unit_mode`(정규화). 못 읽으면 None(모른다)."""
    from src.engine import scheduler as _sched
    from src.engine.strategy_manifest import MARKET_UNIT_SCALE_IDS

    modes: "dict[str, str | None]" = {}
    for sid in MARKET_UNIT_SCALE_IDS:
        try:
            strat = _sched.trading_scheduler.registry.get(sid)
            if strat is None:
                modes[sid] = None
                continue
            modes[sid] = market_unit.normalize_mode(strat.config.params.get(market_unit.MODE_KEY))[0]
        except Exception:
            modes[sid] = None
    return modes


@router.get("", response_model=ApiResponse)
async def get_market_regime_label() -> ApiResponse:
    today = _kst.today_kst()
    rows = await stock_master_daily.get_recent_daily(mrl.SOURCE_TICKER, _FETCH_ROWS)
    bars: list[tuple[date, object]] = []
    for row in rows or []:
        d = _bar_date(row.get("bas_dd"))
        if d is not None and d < today:
            bars.append((d, row.get("close_price")))
    bars.sort(key=lambda b: b[0])

    if len(bars) < mrl.WARMUP_CLOSES:
        return ApiResponse(
            success=False, data=None,
            message=f"069500 일봉이 {len(bars)}행뿐이라 장세를 매길 수 없다(필요 {mrl.WARMUP_CLOSES}행)",
        )

    dates = [d for d, _ in bars]
    closes = [c for _, c in bars]
    try:
        now = mrl.label_after_closes(closes)[-1]
        sess = mrl.session_labels(dates, closes)
    except ValueError as exc:
        logger.warning("[market_regime_label] 069500 종가 이상 — %s", exc)
        return ApiResponse(success=False, data=None, message=f"069500 종가 이상: {exc}")

    seq = [(d, p.label) for d, p in sess] + [(today, now.label)]
    k = len(seq) - 1
    while k > 0 and seq[k - 1][1] == now.label:
        k -= 1

    index = {d: i for i, d in enumerate(dates)}
    unit_now = _unit(closes)
    history = []
    for d, lb in seq[-_HISTORY_DAYS:]:
        i = index.get(d, len(closes))
        u = unit_now if d == today else _unit(closes[:i])
        history.append({"date": d.isoformat(), "label": lb, "m": u.m if u else None})

    data = {
        "today": {
            "date": today.isoformat(),
            "label": now.label,
            "direction": now.direction,
            "volatility": now.volatility,
            "slope_pct": now.slope_pct,
            "vol_pct": now.vol_pct,
            "basis_date": dates[-1].isoformat(),
        },
        "history": history,
        "market_unit": {
            "m": unit_now.m if unit_now else None,
            "state": unit_now.state if unit_now else None,
            "above_sma60": unit_now.above if unit_now else None,
            "sma60_rising": unit_now.rising if unit_now else None,
            "close": unit_now.close if unit_now else None,
            "sma60": unit_now.sma60 if unit_now else None,
            "basis_date": dates[-1].isoformat(),
            # 엔진 메모리 스냅샷(`StrategyBase._market_unit_snaps`)을 여는 공개 경로가 없다 —
            # 운영 DB 종가로 같은 판정 함수를 다시 부른 값임을 밝힌다.
            "source": _UNIT_SOURCE,
            "modes": _read_modes(),
        },
        "since": seq[k][0].isoformat(),
        "since_truncated": k == 0,
        "warmup_from": dates[0].isoformat(),
        "thresholds": {
            "ma_window": mrl.MA_WINDOW,
            "slope_lookback": mrl.SLOPE_LOOKBACK,
            "vol_window": mrl.VOL_WINDOW,
            "dir_enter_pct": mrl.DIR_ENTER * 100,
            "dir_exit_pct": mrl.DIR_EXIT * 100,
            "vol_high_pct": mrl.VOL_HIGH * 100,
            "vol_low_pct": mrl.VOL_LOW * 100,
        },
    }
    return ApiResponse(success=True, data=data, message="")
