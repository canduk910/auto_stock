"""cycle351 — 피라미딩(사다리 증량) 가상 기록(셰도) leaf.

**매매 행위 0 · 읽기 전용.** 이 모듈은 어떤 주문도 내지 않고, DB 에 아무것도 쓰지 않는다
(SELECT 만 허용). 실제 매매는 여전히 1랏 규약(`StrategyBase`) 그대로 돌아간다 — 이 leaf 는
"만약 사다리(피라미딩)를 켰다면 결과가 어땠을까"를 사후에 재현해 관찰 지표로만 남긴다.

## 모형 — 「앵커 위 덧씌우기」(§1)

가상 사다리는 **실제 청산(앵커)보다 늦게 나가지 않는다**. 실제 포지션의 청산(날짜·가격·시각)을
앵커로 두고, 그 위에 사다리만의 추가 매수와 사다리만의 더 조인 손절선만 모형화한다. 1랏과
공유되는 청산선(샹들리에·스테이지3·시간청산·채널)은 앵커가 이미 담고 있으므로 `virtual_R −
actual_R`(delta_R)은 모형 오차가 아니라 **사다리 효과만** 잰다.

**한계** — 「사다리가 1랏보다 오래 버티는 경우」(평단 기준 본전 승격이 늦게 켜져 앵커 이후까지
살아남는 경로)는 이 모형이 보지 못한다. 앵커에서 항상 멈추기 때문이다. 그 경우는 별도의
"자유 모드"(S0 과거 재현 스크립트, `_workspace/domain_consult/` 소관)가 잰다.

**손절선은 `_stop_floor` 래칫으로 조이기만 한다(§4-1, 독립 검증 지적 #17)** — 사다리 전용 선
(세트선·평단 backstop·평단 본전 승격·kojiro live ATR 「기존 2N 선」)은 하루 계산값이 전날보다
낮아져도(예: 새 트랜치로 평단이 올라 본전 승격 문턱이 고점을 다시 넘어 해제되는 경우) 이미
확정된 보호가 풀리지 않는다 — `overlay_ladder` 내부 `ratcheted_line`이 그날 값이 이전 최댓값보다
클 때만 갱신한다. kojiro(`be_atr` 제공)는 `avg − stop_atr×live_ATR` 항을 세트선과 함께 겨룬다.
donchian(`be_atr=None`)은 고정 N 에서 이 항이 항상 세트선에 덮여 필요 없다.

**본전 승격의 「다음 날부터」는 사다리에 유리한 근사다(§1-2, 독립 검증 지적 #17)** — 실제 kojiro
는 `on_tick` 의 `high_since_buy` 로 **그날** 무장하지만, 이 셰도는 하루 지연으로 근사한다. 대가는
작다(설계 §4-1도 "고점 먼저, 저가 나중"인 실장세와 이 근사 사이 차이를 인정한다) — 근사를 없애
같은 날 무장(고점 먼저 확인 → 저가로 손절 판정)으로 바꾸면 C8 이 명시한 계약("같은 날 고가로는
켜지지 않는다")과 충돌하고 §1-2 의 보수 순서 문서를 다시 써야 한다. 그래서 이번 사이클은 근사를
유지하고 이 사실만 명기한다(대안 — 설계 §4-1 재검토는 다음 사이클 후보).

**진입가 E 는 분할 체결 가중평균이 아니다(독립 검증 지적 #21, 한계로만 명기)** — `E = pair["buy_price"]`
는 `get_trade_pairs` 가 계산한 값이고, 한 주문이 여러 가격으로 나뉘어 체결되면 그 페어의 마지막
체결가 × 수량이다(`trade_history.py`, 실포지션 `pos.buy_price` 도 같은 방식이라 손절선 기준과는
맞는다). 크기는 보통 수 틱이라 이 사이클은 그대로 둔다 — 정확히 하려면 `buy_order_nos` 로 사후에
체결내역을 대조하거나 P-1(누적 체결) 배관 이후 가중평단 컬럼을 쓴다.

순수 코어(`overlay_ladder` · `no_add_flags` · `LadderConfig` · `LADDER_C`)는 표준 라이브러리만
쓰는 함수이고, async 어댑터(`build_pyramid_shadow`)만 DB(SELECT)·pandas·kojiro 지표를 (함수 안
지연 import 로) 읽는다. 대상 전략은 `kojiro`·`donchian_swing` 둘뿐이다(D-3).

이 모듈을 import 하는 프로덕션 모듈은 `src/engine/log_metrics_collector.py` 하나뿐이어야 한다
(§4-4 S1). leaf 최상단 import 는 표준 라이브러리 + `src.engine.daily_emit_cap` 까지다 — 그래야
S0 과거 재현 스크립트가 이 파일을 운영 컨테이너 `/tmp` 로 복사해 무수정으로 import 할 수 있다.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from src.engine.daily_emit_cap import KstDailyEmitCap

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 손절형 kind 집합(§1-4 `killed` 정의) — 이 밖의 kind 는 anchor · open 뿐이다.
# `existing_2n_live` = §4-1 「기존 2N 선」(kojiro live ATR, 독립 검증 지적 #17).
_LADDER_STOP_KINDS = frozenset({
    "gap", "set_line", "avg_backstop", "avg_breakeven", "stop_after_add", "existing_2n_live",
})

# `overlay_ladder` 출력 dict 의 계약 키(§1-4).
CORE_OUT_KEYS = frozenset({
    "tranches", "fills", "avg", "exit_idx", "exit_price", "exit_kind",
    "virtual_R", "base_R", "set_stop", "fixed_stop", "killed", "peak_risk_R",
})

MARKER_PREFIX = "[pyramid_shadow_close]"

# §2-1 — 대상 전략은 이 둘뿐이다(D-3, kojiro 는 실매매 대상, donchian 은 가상 기록만).
_STRATEGIES = ("kojiro", "donchian_swing")

# §2-2 — 진입 N 계산의 매수일 이전 봉 창 상한(kojiro, `strategies/kojiro.py::KOJIRO_FETCH_DAYS`
# 와 동일 값. import 는 하지 않는다 — 8영역/전략 파일 무접촉 규약).
_KOJIRO_FETCH_DAYS = 100

#: §2-2 — 운영 DB 조회값과 같은 폴백 상수(레지스트리 조회 실패·부재 시).
_FALLBACK_PARAMS: dict[str, dict] = {
    "kojiro": {
        "stop_atr": 2.0, "hard_stop_pct": -8.0, "breakeven_promote_atr": 1.5,
        "atr_period": 20, "risk_pct": 0.005,
    },
    "donchian_swing": {
        "stop_atr": 2.0, "turtle_backstop_pct": -9.0, "breakeven_promote_atr": 1.5,
        "atr_period": 14, "risk_pct": 0.01,
    },
}

#: §2-3 레코드 키 순서(고정 계약) — 콜렉터·마커·테스트가 이 순서를 참조한다.
RECORD_KEYS = (
    "strategy", "ticker", "buy_date", "entry_price", "n_entry", "r_unit", "status",
    "exit_date", "exit_price", "exit_time", "bars_through", "final", "actual_R", "virtual_R",
    "delta_R", "tranches", "add_dates", "add_prices", "set_stop", "fixed_stop", "v_exit_date",
    "v_exit_kind", "killed", "tranche_shares", "eligible", "add_stage", "add_macd",
    "params_source", "error",
)

_MAX_RECORDS = 50

# §2-5 — WARNING 마커 KST 하루 1회/포지션(strategy:ticker:buy_date). 모듈 전역
# `KstDailyEmitCap`(cycle349 `_vcp_breakout_events_cap` 선례).
_shadow_close_cap: KstDailyEmitCap = KstDailyEmitCap()

# 독립 검증 지적 #1·#18 — 판 날 21:30 까지 매도일 봉이 없는 청산(20:30 적재 자격 미달 ·
# 21:30 재기동으로 그날 정산을 놓친 경우)은 그대로 두면 영구히 final=0 이다. 매도일로부터
# 이 창(달력일, KIS chk-holiday 호출 금지 — 영업일 계산 대신 여유 있는 달력일 근사) 안이면
# 매일 밤 다시 확인해 봉이 생기는 첫 밤에 확정한다(D+1 정기 적재의 7일 증분 보정 창과 호환).
_CLOSE_FINALIZE_LOOKBACK_DAYS = 7

# 한 번 확정(`final=1`)된 청산은 dedup 키(`pair["pair_key"]`, 없으면 합성) → 확정된
# target_date 로 기억한다 — 값이 **오늘과 다르면** 다시 집지 않는다(마커·집계 중복 차단).
# 같은 날 반복 호출(20:05/20:20/21:30)은 값이 오늘과 같으므로 여전히 포함된다.
# 프로세스 수명 동안만 유효한 메모리 dedup — 재시작 시 최악 1회 중복 재확정 가능(관측 전용
# 기능이라 수용, 새 테이블 금지 제약).
_finalized_pairs: dict[str, date] = {}


def reset_finalized_pairs_for_test() -> None:
    """테스트 격리 전용 — `_finalized_pairs` 를 비운다."""
    _finalized_pairs.clear()


def _pair_dedup_key(sid: str, ticker: str, buy_date_obj: date, sell_date_obj: date, pair: dict) -> str:
    raw = pair.get("pair_key")
    if isinstance(raw, str) and raw:
        return raw
    return f"{sid}:{ticker}:{buy_date_obj.isoformat()}:{sell_date_obj.isoformat()}"


# ===========================================================================
# §1 — 순수 코어
# ===========================================================================
@dataclass(frozen=True)
class LadderConfig:
    """가상 사다리 설정(§1-1). `step_n` = 추가 눈금 간격(N 배수), `sizes` = 트랜치별 크기
    (유닛 배수, 길이 = 최대 트랜치 수), `gap_skip_mult` = 갭 스킵 배수."""

    step_n: float
    sizes: tuple[float, ...]
    gap_skip_mult: float = 1.05


#: §1-5 — 셰도가 쓰는 사다리는 이 상수 하나(C*). DB 키가 아니다 — 롤백 다이얼은 단계 4 소관.
LADDER_C = LadderConfig(step_n=1.0, sizes=(2.0 / 3.0, 2.0 / 3.0, 2.0 / 3.0), gap_skip_mult=1.05)


def no_add_flags(dates):
    """`bars` 와 같은 길이의 순수 헬퍼 — 다음 거래일까지 2일 이상 비면(≥3일 간격) 그날은
    추가 금지(§1-3). 마지막 봉은 다음 거래일을 모르므로 그 봉이 금요일일 때만 True
    (평일 휴장 전날은 셰도에서 판정 불가 — KIS `chk-holiday` 호출 금지)."""
    n = len(dates)
    if n == 0:
        return []
    flags = [(dates[i + 1] - dates[i]).days >= 3 for i in range(n - 1)]
    flags.append(dates[-1].weekday() == 4)
    return flags


def overlay_ladder(
    bars,
    entry_idx,
    entry_price,
    n_entry,
    *,
    cfg,
    stop_atr,
    hard_stop_pct,
    be_mult,
    be_atr,
    no_add,
    anchor_idx,
    anchor_price,
    anchor_add_allowed,
):
    """앵커 위 덧씌우기 모형의 순수 코어(§1-2~§1-4).

    `bars` = `(date, open, high, low, close)` 오름차순 시퀀스, `entry_idx` 부터 사용한다.
    실제 청산(앵커)이 있으면 그 봉·가격 위에서만 사다리를 평가하고, 사다리는 앵커보다
    늦게 나가지 않는다. 매매 행위 0 — 순수 계산.
    """
    N = float(n_entry)
    if not math.isfinite(N) or N <= 0:
        raise ValueError(f"n_entry 는 유한한 양수여야 한다: {n_entry!r}")

    r_unit = float(stop_atr) * N
    E = float(entry_price)
    sizes = list(cfg.sizes)
    n_bars = len(bars)

    fills: list[tuple[int, float, float]] = [(entry_idx, E, sizes[0])]
    last = E
    k = 1
    avg = E
    hsb = float(bars[entry_idx][2])

    def recalc_avg() -> float:
        total_sz = sum(sz for _, _, sz in fills)
        total_val = sum(p * sz for _, p, sz in fills)
        return total_val / total_sz if total_sz else E

    def line_for(be_val):
        set_line = last - float(stop_atr) * N
        backstop = avg * (1.0 + float(hard_stop_pct) / 100.0)
        candidates = {"set_line": set_line, "avg_backstop": backstop}
        if be_atr is not None and be_val is not None and math.isfinite(float(be_val)):
            # §4-1 "기존 2N 선" — kojiro live ATR(`be_atr`) 기반 avg(가중평단) − stop_atr×ATR.
            # donchian(be_atr=None)은 이 항이 없다 — 고정 N 에서는 항상 set_line 에 덮인다(§1-2).
            candidates["existing_2n_live"] = avg - float(stop_atr) * float(be_val)
        if be_mult and be_mult > 0:
            a_val = be_val if be_val is not None else N
            if hsb >= avg + float(be_mult) * a_val:
                candidates["avg_breakeven"] = avg
        best_kind = max(candidates, key=lambda kk: candidates[kk])
        return candidates[best_kind], best_kind

    stop_floor_value: float | None = None
    stop_floor_kind: str | None = None

    def ratcheted_line(be_val):
        """§4-1 `_stop_floor` 래칫(독립 검증 지적 #17) — 사다리 전용 선은 조이기만 한다.

        하루 계산값(`line_for`)이 이전에 확정된 선보다 낮아도(예: 추가로 평단이 올라 본전 승격
        문턱이 고점을 다시 넘어서 해제되는 경우) 이미 확정된 보호는 풀리지 않는다 — 값이 오를
        때만 갱신하고, 그 값의 kind 를 함께 기억한다.
        """
        nonlocal stop_floor_value, stop_floor_kind
        raw_line, raw_kind = line_for(be_val)
        if stop_floor_value is None or raw_line > stop_floor_value:
            stop_floor_value, stop_floor_kind = raw_line, raw_kind
        return stop_floor_value, stop_floor_kind

    def fixed_stop_val() -> float:
        return E - float(stop_atr) * N

    def peak_risk_at() -> float:
        line = (last - float(stop_atr) * N) if k >= 2 else fixed_stop_val()
        return sum(sz * (p - line) for _, p, sz in fills) / r_unit

    def apply_anchor_override(is_anchor_day, price, kind):
        if is_anchor_day and anchor_price is not None and anchor_price > price:
            return float(anchor_price), "anchor"
        return price, kind

    peak_risk_R = peak_risk_at()

    exit_idx = None
    exit_price = None
    exit_kind = None

    if anchor_idx is not None and anchor_idx == entry_idx:
        # §1 핵심 결정의 귀결 — 매수일에 실제로 청산됐으면 사다리도 그날 앵커가에 나간다.
        exit_idx = entry_idx
        exit_price = float(anchor_price)
        exit_kind = "anchor"
    else:
        d = entry_idx + 1
        while d < n_bars and exit_idx is None:
            _bar_date, o, h, lo, c = bars[d]
            o, h, lo = float(o), float(h), float(lo)
            is_anchor_day = anchor_idx is not None and d == anchor_idx
            be_val = be_atr[d - 1] if be_atr is not None else None

            # 1) 손절 먼저 (보수 순서, §1-2) — 래칫 §4-1
            if k >= 2:
                line, kind = ratcheted_line(be_val)
                triggered = False
                if o <= line:
                    cand_price, cand_kind = o, "gap"
                    triggered = True
                elif lo <= line:
                    cand_price, cand_kind = line, kind
                    triggered = True
                if triggered:
                    px, kk = apply_anchor_override(is_anchor_day, cand_price, cand_kind)
                    exit_idx, exit_price, exit_kind = d, px, kk

            # 2) 추가 — 손절로 안 나갔고 슬롯이 남아 있을 때만
            if exit_idx is None and k < len(sizes):
                allowed = (not no_add[d]) and not (is_anchor_day and not anchor_add_allowed)
                while allowed and exit_idx is None and k < len(sizes):
                    level = last + float(cfg.step_n) * N
                    if o >= level * float(cfg.gap_skip_mult):
                        break
                    if h >= level:
                        px_fill = max(level, o)
                        fills.append((d, px_fill, sizes[k]))
                        last = px_fill
                        k += 1
                        avg = recalc_avg()
                        peak_risk_R = max(peak_risk_R, peak_risk_at())
                        if k >= 2:
                            line2, _kind2 = ratcheted_line(be_val)
                            if lo <= line2:
                                px2, kk2 = apply_anchor_override(
                                    is_anchor_day, line2, "stop_after_add",
                                )
                                exit_idx, exit_price, exit_kind = d, px2, kk2
                                break
                    else:
                        break

            # 3) 앵커 날인데 아직 안 나갔으면 앵커가에 청산
            if exit_idx is None and is_anchor_day:
                exit_idx = d
                exit_price = float(anchor_price)
                exit_kind = "anchor"

            # 4) 고점 갱신 — 본전 승격은 다음 날부터 켜진다
            hsb = max(hsb, h)
            d += 1

        if exit_idx is None:
            exit_idx = n_bars - 1
            exit_price = float(bars[-1][4])
            exit_kind = "open"

    virtual_R = sum(sz * (exit_price - p) for _, p, sz in fills) / r_unit
    base_ref = float(anchor_price) if anchor_price is not None else float(bars[-1][4])
    base_R = (base_ref - E) / r_unit

    set_stop = (last - float(stop_atr) * N) if k >= 2 else None
    fixed_stop = fixed_stop_val()
    killed = 1 if (
        k >= 2
        and exit_kind in _LADDER_STOP_KINDS
        and (anchor_idx is None or exit_idx < anchor_idx)
    ) else 0

    return {
        "tranches": k,
        "fills": fills,
        "avg": avg,
        "exit_idx": exit_idx,
        "exit_price": exit_price,
        "exit_kind": exit_kind,
        "virtual_R": virtual_R,
        "base_R": base_R,
        "set_stop": set_stop,
        "fixed_stop": fixed_stop,
        "killed": killed,
        "peak_risk_R": peak_risk_R,
    }


# ===========================================================================
# §2 — 어댑터 (DB SELECT · pandas · kojiro 지표는 함수 안 지연 import)
# ===========================================================================
def _resolve_params(sid: str, params_by_sid) -> tuple[dict, str]:
    fallback = _FALLBACK_PARAMS.get(sid, {})
    raw = params_by_sid.get(sid) if isinstance(params_by_sid, dict) else None
    if isinstance(raw, dict) and raw:
        return {**fallback, **raw}, "registry"
    return dict(fallback), "fallback"


def _resolve_budget(sid: str, budget_by_sid):
    if not isinstance(budget_by_sid, dict):
        return None
    val = budget_by_sid.get(sid)
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    if not math.isfinite(val) or val <= 0:
        return None
    return val


def _compute_entry_atr(sid: str, prior_rows: list, sim_bars_rows: list, params: dict):
    """§2-2 진입 N — 매수일 **이전** 봉만 사용. kojiro = Wilder(최대 100봉 창),
    donchian = SMA(`StrategyBase._atr`) → `float(int(·))` 절삭. 실패는 (None, None)."""
    try:
        period = int(params.get("atr_period", 20 if sid == "kojiro" else 14))
    except (TypeError, ValueError):
        period = 20 if sid == "kojiro" else 14

    if sid == "kojiro":
        window = list(prior_rows[-_KOJIRO_FETCH_DAYS:])
        if len(window) < 2:
            return None, None
        try:
            import pandas as pd

            from src.engine.kojiro_indicators import atr as _kojiro_atr

            combined = window + list(sim_bars_rows)
            df = pd.DataFrame({
                "high": [float(r.get("high_price") or 0) for r in combined],
                "low": [float(r.get("low_price") or 0) for r in combined],
                "close": [float(r.get("close_price") or 0) for r in combined],
            })
            series = _kojiro_atr(df, period)
            n_entry = float(series.iloc[len(window) - 1])
            be_seq = [float(x) for x in series.iloc[len(window):].tolist()]
        except Exception:
            return None, None
        if not math.isfinite(n_entry):
            return None, None
        return n_entry, be_seq

    # donchian_swing
    if len(prior_rows) < 2:
        return None, None
    try:
        from src.engine.strategy_base import StrategyBase

        rev = list(reversed(prior_rows))
        highs = [float(r.get("high_price") or 0) for r in rev]
        lows = [float(r.get("low_price") or 0) for r in rev]
        closes = [float(r.get("close_price") or 0) for r in rev]
        atr_val = StrategyBase._atr(highs, lows, closes, period)
    except Exception:
        return None, None
    if not math.isfinite(atr_val):
        return None, None
    n_entry = float(int(atr_val)) if atr_val else 0.0
    return n_entry, None


def _safe_stage(en, pos: int):
    try:
        if pos < 0 or pos >= len(en):
            return None
        v = en["stage"].iloc[pos]
        if v is None:
            return None
        fv = float(v)
        if math.isnan(fv):
            return None
        return int(fv)
    except Exception:
        return None


def _safe_macd(en, pos: int):
    try:
        if pos <= 0 or pos >= len(en):
            return None
        m = float(en["macd3"].iloc[pos])
        s = float(en["macd3_sig"].iloc[pos])
        pm = float(en["macd3"].iloc[pos - 1])
        psg = float(en["macd3_sig"].iloc[pos - 1])
        if any(math.isnan(x) for x in (m, s, pm, psg)):
            return None
        if pm <= psg and m > s:
            return "gc"
        return "up" if m > s else "dn"
    except Exception:
        return None


def _compute_add_stage_macd(full_asc_rows: list, entry_idx_full: int, add_fills: list):
    """§2-3 — 추가 체결일 d 마다 d−1 완성봉의 kojiro 스테이지 · MACD3 상태. 기록만 한다
    (두 전략 공통, `kojiro_indicators.enrich` 를 그 종목 전 봉에 한 번 돌려 얻는다).
    실패 시 None(단언 없음, §2-3 해석 11)."""
    if not add_fills:
        return [], []
    try:
        import pandas as pd

        from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich

        df = pd.DataFrame({
            "high": [float(r.get("high_price") or 0) for r in full_asc_rows],
            "low": [float(r.get("low_price") or 0) for r in full_asc_rows],
            "close": [float(r.get("close_price") or 0) for r in full_asc_rows],
        })
        en = enrich(df, KojiroIndicatorConfig())
    except Exception:
        return [None] * len(add_fills), [None] * len(add_fills)

    stages = []
    macds = []
    for d_rel, _price, _size in add_fills:
        pos = entry_idx_full + d_rel - 1
        stages.append(_safe_stage(en, pos))
        macds.append(_safe_macd(en, pos))
    return stages, macds


def _blank_record(sid: str, ticker: str, buy_date_obj: date, entry_price: float, status) -> dict:
    return {
        "strategy": sid, "ticker": ticker, "buy_date": buy_date_obj.isoformat(),
        "entry_price": round(float(entry_price), 4), "n_entry": None, "r_unit": None,
        "status": status, "exit_date": None, "exit_price": None, "exit_time": None,
        "bars_through": None, "final": 0, "actual_R": None, "virtual_R": None,
        "delta_R": None, "tranches": None, "add_dates": [], "add_prices": [],
        "set_stop": None, "fixed_stop": None, "v_exit_date": None, "v_exit_kind": None,
        "killed": None, "tranche_shares": None, "eligible": None, "add_stage": [],
        "add_macd": [], "params_source": None, "error": None,
    }


def _sanitize(obj):
    """비유한(NaN/inf) float 을 None 으로 — `json.dumps(allow_nan=False)` 이 항상
    성공해야 한다(`daily_log_reports.metrics` JSONB, §2-3)."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


async def _build_record(
    sid: str, pair: dict, buy_date_obj: date, target_date: date,
    params_by_sid, budget_by_sid, daily_db,
) -> dict:
    ticker = str(pair.get("ticker") or "")
    status = pair.get("status")
    try:
        entry_price = float(pair.get("buy_price"))
    except (TypeError, ValueError):
        entry_price = 0.0
    rec = _blank_record(sid, ticker, buy_date_obj, entry_price, status)

    try:
        rows = await daily_db.get_recent_daily(ticker, 400)
    except Exception as exc:
        rec["error"] = f"daily_fetch_error:{type(exc).__name__}"
        logger.debug(
            "[pyramid_shadow_error] strategy=%s ticker=%s reason=daily_fetch",
            sid, ticker, exc_info=True,
        )
        return rec

    try:
        full_asc = sorted(
            (
                r for r in (rows or [])
                if isinstance(r, dict) and r.get("bas_dd") is not None
                and r["bas_dd"] <= target_date
            ),
            key=lambda r: r["bas_dd"],
        )
        entry_idx_full = None
        for i, r in enumerate(full_asc):
            if r["bas_dd"] == buy_date_obj:
                entry_idx_full = i
                break
        if entry_idx_full is None:
            rec["error"] = "no_entry_bar"
            return rec

        prior_rows = full_asc[:entry_idx_full]
        sim_bars_rows = full_asc[entry_idx_full:]

        params, params_source = _resolve_params(sid, params_by_sid)
        rec["params_source"] = params_source

        n_entry, be_atr_seq = _compute_entry_atr(sid, prior_rows, sim_bars_rows, params)
        if n_entry is None or not math.isfinite(n_entry) or n_entry <= 0:
            rec["error"] = "no_atr"
            return rec

        stop_atr = float(params.get("stop_atr", 2.0))
        hard_pct_key = "hard_stop_pct" if sid == "kojiro" else "turtle_backstop_pct"
        hard_pct = float(params.get(hard_pct_key, -8.0))
        be_mult = float(params.get("breakeven_promote_atr", 1.5))
        risk_pct = float(params.get("risk_pct", 0.005))
        r_unit = stop_atr * n_entry
        if not math.isfinite(r_unit) or r_unit == 0:
            rec["error"] = "no_atr"
            return rec

        rec["n_entry"] = round(n_entry, 4)
        rec["r_unit"] = round(r_unit, 4)

        sim_bars = [
            (
                r["bas_dd"], float(r.get("open_price") or 0), float(r.get("high_price") or 0),
                float(r.get("low_price") or 0), float(r.get("close_price") or 0),
            )
            for r in sim_bars_rows
        ]

        anchor_idx = None
        anchor_price = None
        anchor_add_allowed = True
        final = 0

        if status == "closed":
            sell_date_obj = date.fromisoformat(str(pair.get("sell_date")))
            try:
                sell_price = float(pair.get("sell_price"))
            except (TypeError, ValueError):
                sell_price = float("nan")
            sell_time = str(pair.get("sell_time") or "")
            found_idx = None
            for i, r in enumerate(sim_bars_rows):
                if r["bas_dd"] == sell_date_obj:
                    found_idx = i
                    break
            if found_idx is not None:
                anchor_idx = found_idx
                anchor_price = sell_price
                anchor_add_allowed = sell_time >= "09:30:00"
                final = 1
            actual_R = (sell_price - entry_price) / r_unit
            rec["exit_date"] = sell_date_obj.isoformat()
            rec["exit_price"] = round(sell_price, 4)
            rec["exit_time"] = pair.get("sell_time")
        else:
            last_close = sim_bars[-1][4] if sim_bars else entry_price
            actual_R = (last_close - entry_price) / r_unit

        dates_seq = [b[0] for b in sim_bars]
        no_add = no_add_flags(dates_seq)

        out = overlay_ladder(
            sim_bars, 0, entry_price, n_entry,
            cfg=LADDER_C, stop_atr=stop_atr, hard_stop_pct=hard_pct, be_mult=be_mult,
            be_atr=be_atr_seq, no_add=no_add,
            anchor_idx=anchor_idx, anchor_price=anchor_price,
            anchor_add_allowed=anchor_add_allowed,
        )

        virtual_R = out["virtual_R"]
        rec["bars_through"] = sim_bars_rows[-1]["bas_dd"].isoformat()
        rec["final"] = final
        rec["actual_R"] = round(actual_R, 4)
        rec["virtual_R"] = round(virtual_R, 4)
        # 독립 검증 지적 #19 — final=0 인 청산은 actual_R(실현 매도가 기준)과 virtual_R(앵커
        # 없이 마지막 봉 종가 기준)의 시점이 달라 delta_R 이 일봉 재현 오차와 사다리 효과를
        # 뒤섞는다. 같은 기준 시점이 없으므로 None 으로 둔다(§2-3).
        rec["delta_R"] = round(virtual_R - actual_R, 4) if (status != "closed" or final == 1) else None
        rec["tranches"] = out["tranches"]

        add_fills = out["fills"][1:]
        rec["add_dates"] = [sim_bars_rows[i]["bas_dd"].isoformat() for i, _p, _s in add_fills]
        rec["add_prices"] = [round(float(p), 4) for _i, p, _s in add_fills]
        rec["set_stop"] = round(out["set_stop"], 4) if out["set_stop"] is not None else None
        rec["fixed_stop"] = round(out["fixed_stop"], 4) if out["fixed_stop"] is not None else None
        rec["v_exit_date"] = sim_bars_rows[out["exit_idx"]]["bas_dd"].isoformat()
        rec["v_exit_kind"] = out["exit_kind"]
        rec["killed"] = out["killed"]

        budget = _resolve_budget(sid, budget_by_sid)
        if budget is not None:
            shares = math.floor(LADDER_C.sizes[0] * budget * risk_pct / n_entry)
            rec["tranche_shares"] = int(shares)
            rec["eligible"] = 1 if shares >= 2 else 0

        add_stage, add_macd = _compute_add_stage_macd(full_asc, entry_idx_full, add_fills)
        rec["add_stage"] = add_stage
        rec["add_macd"] = add_macd

        rec["error"] = None
    except Exception as exc:
        rec["error"] = f"compute_error:{type(exc).__name__}"
        logger.debug(
            "[pyramid_shadow_error] strategy=%s ticker=%s reason=compute", sid, ticker,
            exc_info=True,
        )
    return rec


def _format_marker_value(v):
    if v is None:
        return "None"
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v) if v else "-"
    return str(v)


def _emit_close_marker(rec: dict, now_kst: datetime) -> None:
    key = f"{rec.get('strategy')}:{rec.get('ticker')}:{rec.get('buy_date')}"
    fields = (
        ("strategy", rec.get("strategy")), ("ticker", rec.get("ticker")),
        ("buy_date", rec.get("buy_date")), ("exit_date", rec.get("exit_date")),
        ("v_exit_kind", rec.get("v_exit_kind")), ("actual_R", rec.get("actual_R")),
        ("virtual_R", rec.get("virtual_R")), ("delta_R", rec.get("delta_R")),
        ("tranches", rec.get("tranches")), ("add_dates", rec.get("add_dates")),
        ("set_stop", rec.get("set_stop")), ("fixed_stop", rec.get("fixed_stop")),
        ("killed", rec.get("killed")), ("tranche_shares", rec.get("tranche_shares")),
        ("eligible", rec.get("eligible")), ("add_stage", rec.get("add_stage")),
        ("add_macd", rec.get("add_macd")),
    )
    msg = MARKER_PREFIX + " " + " ".join(f"{k}={_format_marker_value(v)}" for k, v in fields)
    _shadow_close_cap.emit_once(key, logger.warning, msg, now=now_kst)


def _build_summary(records: list[dict], truncated: int) -> dict:
    ok = [r for r in records if r.get("error") is None]
    open_recs = [r for r in ok if r.get("status") == "open"]
    closed_recs = [r for r in ok if r.get("status") == "closed"]
    closed_final = [r for r in closed_recs if r.get("final") == 1]
    closed_nonfinal_n = sum(1 for r in closed_recs if r.get("final") != 1)
    killed_n = sum(1 for r in ok if r.get("killed") == 1)
    eligible_n = sum(1 for r in ok if r.get("eligible") == 1)
    deltas = [r["delta_R"] for r in closed_final if r.get("delta_R") is not None]
    delta_mean = round(sum(deltas) / len(deltas), 4) if deltas else None

    extra_notional = 0.0
    gap_notional = 0.0
    for r in open_recs:
        # 독립 검증 지적 #22 — 가상 사다리가 이미 세트선으로 나갔거나(`v_exit_kind != "open"`)
        # 사다리가 서지 않는 비적격(1주 폴백) 랏은 "지금 사다리 명목"에 포함하지 않는다.
        if r.get("v_exit_kind") != "open" or r.get("eligible") != 1:
            continue
        shares = r.get("tranche_shares")
        if shares is None:
            continue
        add_prices = r.get("add_prices") or []
        extra_notional += sum(shares * p for p in add_prices)
        tranches = r.get("tranches")
        actual_R = r.get("actual_R")
        r_unit = r.get("r_unit")
        entry_price = r.get("entry_price")
        if None in (tranches, actual_R, r_unit, entry_price):
            continue
        last_close = entry_price + actual_R * r_unit
        gap_notional += shares * tranches * last_close

    return {
        "open_n": len(open_recs),
        "closed_n": len(closed_recs),
        "closed_final_n": len(closed_final),
        "closed_nonfinal_n": closed_nonfinal_n,
        "killed_n": killed_n,
        "eligible_n": eligible_n,
        "delta_R_mean_closed_final": delta_mean,
        "extra_notional_won": round(extra_notional, 4),
        "gap_stress_won": round(gap_notional * 0.1, 4),
        "errors_n": sum(1 for r in records if r.get("error") is not None),
        "truncated": truncated,
    }


async def build_pyramid_shadow(
    target_date: date, *, params_by_sid: dict, budget_by_sid: dict,
    held_by_sid: dict[str, set] | None = None, now_kst: datetime | None = None,
) -> dict:
    """§2 — kojiro·donchian_swing 의 그날 대상 포지션(보유 + 그날 청산)에 가상 사다리를
    덧씌워 요약한다. 매매 행위 0, DB 는 SELECT 만. `get_trade_pairs` 예외는 전파한다
    (호출자인 콜렉터가 흡수) — 한 종목 일봉 예외는 그 레코드만 `error` 로 남기고 계속한다.

    **범위 = 보유 + (판 날 == target_date) + 최근 `_CLOSE_FINALIZE_LOOKBACK_DAYS`(7 달력일)
    안의 미확정 청산(독립 검증 지적 #1·#18)** — 판 날 21:30 까지 매도일 봉이 없으면(20:30 적재
    자격 미달·재기동으로 정산 누락) 그 청산은 최대 7일 동안 매일 밤 다시 확인되고, 봉이 생기는
    첫 밤에 확정(`final=1`)된다. 한 번 확정되면 `_finalized_pairs`(`pair_key` → 확정된
    target_date) 가 다음 날부터 재확인 대상에서 뺀다 — 같은 날 반복 호출(20:05/20:20/21:30)은
    여전히 포함된다(값이 오늘과 같으면 통과). 이 dedup 은 프로세스 메모리뿐이라 재시작 시
    최악 1회 중복 재확정이 가능하다(관측 전용 기능이라 수용).

    `held_by_sid`(독립 검증 지적 #20, 선택) — `{sid: {ticker, ...}}` 실보유 집합. 콜렉터가
    레지스트리 `state.positions` 에서 읽어 넘긴다(읽기만). open 페어의 ticker 가 그 안에
    없으면 유령 open(부분체결·`momentum` 폴백 오귀속 등으로 어긋난 `trade_history` 순수량)
    으로 보아 뺀다 — 청산 페어는 대상이 아니다. `sid` 자체가 없으면(판정 불가) fail-open
    으로 종전처럼 포함한다.
    """
    import src.db.stock_master_daily as daily_db
    import src.db.trade_history as trade_history_db

    records: list[dict] = []
    for sid in _STRATEGIES:
        pairs = await trade_history_db.get_trade_pairs(strategy=sid)
        for pair in pairs or []:
            if not isinstance(pair, dict):
                continue
            status = pair.get("status")
            buy_date_raw = pair.get("buy_date")
            if not buy_date_raw:
                continue
            try:
                buy_date_obj = date.fromisoformat(str(buy_date_raw))
            except Exception:
                continue
            if status == "open":
                if buy_date_obj > target_date:
                    continue
                # 독립 검증 지적 #20 — `get_trade_pairs` 의 순수량 open 페어가 실보유
                # (`state.positions`)와 어긋날 수 있다(부분체결·momentum 폴백 오귀속 등).
                # 그 전략의 실보유 집합을 알 때만(`sid in held_by_sid`) 대조하고 없으면
                # 유령 open 으로 보아 뺀다 — 판정 불가(그 전략 키 자체가 없음)는 fail-open.
                if isinstance(held_by_sid, dict) and sid in held_by_sid:
                    held_set = held_by_sid.get(sid) or set()
                    if str(pair.get("ticker") or "") not in held_set:
                        continue
            elif status == "closed":
                sell_date_raw = pair.get("sell_date")
                if not sell_date_raw:
                    continue
                try:
                    sell_date_obj = date.fromisoformat(str(sell_date_raw))
                except Exception:
                    continue
                # §2-1 확장(독립 검증 지적 #1·#18) — 판 날(days_since=0) 은 기존 그대로, 그
                # 이후 최근 N 달력일 안(1..LOOKBACK)은 "아직 확정 못 한 청산 재확인" 대상이다.
                # 미래 날짜(음수)·창 밖은 범위 밖. 이미 확정된 건은(오늘이 아니면) dedup 으로 제외.
                days_since = (target_date - sell_date_obj).days
                if days_since < 0 or days_since > _CLOSE_FINALIZE_LOOKBACK_DAYS:
                    continue
                pkey = _pair_dedup_key(sid, str(pair.get("ticker") or ""), buy_date_obj, sell_date_obj, pair)
                finalized_on = _finalized_pairs.get(pkey)
                if finalized_on is not None and finalized_on != target_date:
                    continue
            else:
                continue

            rec = await _build_record(
                sid, pair, buy_date_obj, target_date, params_by_sid, budget_by_sid, daily_db,
            )
            if rec.get("status") == "closed" and rec.get("final") == 1:
                pkey = _pair_dedup_key(
                    sid, str(pair.get("ticker") or ""), buy_date_obj,
                    date.fromisoformat(str(pair.get("sell_date"))), pair,
                )
                _finalized_pairs[pkey] = target_date
            records.append(_sanitize(rec))

    truncated = 0
    if len(records) > _MAX_RECORDS:
        records = records[:_MAX_RECORDS]
        truncated = 1

    summary = _build_summary(records, truncated)

    result = {
        "version": 1,
        "target_date": target_date.isoformat(),
        "ladder": {
            "step_n": LADDER_C.step_n,
            "sizes": [round(s, 4) for s in LADDER_C.sizes],
            "gap_skip_mult": LADDER_C.gap_skip_mult,
        },
        "summary": summary,
        "records": records,
        # 독립 검증 지적 — 21:30 LLM 프롬프트가 이 키를 실매매로 오독하지 않도록 명시한다.
        "_note": "가상 기록(피라미딩 셰도) — 실매매 아님. 매매 행위에 영향 없음.",
    }

    try:
        effective_now = now_kst if isinstance(now_kst, datetime) else datetime.now(KST)
        if effective_now.date() == target_date:
            for rec in records:
                if rec.get("status") == "closed" and rec.get("final") == 1:
                    _emit_close_marker(rec, effective_now)
    except Exception:
        logger.debug("[pyramid_shadow_error] 마커 emit 실패 graceful", exc_info=True)

    return _sanitize(result)
