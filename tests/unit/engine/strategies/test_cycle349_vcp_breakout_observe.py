"""cycle349 — VCP 관측 ①(오전 후보 돌파선 거리) · ③(하루 돌파 사건 관측) Red + 확장 전 골든.

명세 = `_workspace/red/cycle349_vcp_observe_spec.md` (①=D1~D6, ③=E1~E3, 골든 G1·G2).
자문 = `_workspace/domain_consult/cycle347_vcp_zero_fills_cause.md`.

## 🔴 관측 전용 — 매매 행위 0

VCP 후보 집합·순서·매수 판정·파라미터는 한 글자도 바뀌면 안 된다. 그 주장은 차분 비교
(「훅 있음 vs 훅 raise 스텁」)가 아니라 **확장 전 HEAD(`2ef289b`) 코드로 뽑아 커밋한 골든**
(`fixtures/cycle349_golden.json`)과의 완전 일치로 잰다 — cycle348 에서 차분 비교는 두 쪽을
같이 바꾸는 돌연변이 2종을 놓쳤다. 골든 생성 스크립트는 리포 밖(scratchpad)에 있고,
HEAD 를 `git archive` 로 푼 트리에서 이 파일의 `run_g1`/`run_g2` 를 돌린 결과를 그대로 박았다.

골든은 **교차일 상태를 채운 인스턴스**로 뜬다(`seed_cross_day_state` — `prepare` 가 비우지 않는
`_cooldown_until`·`_position_setup`·`_prev_price`·`_vol_latch`). 새 인스턴스로 뜨면 그 필드들이
비어 있어 ① 헬퍼가 덮어써도 골든이 같게 나온다(verify 지적 1). 스냅샷에는 그 4필드와 G2 끝
`_candidates` 를 담는다. 골든 전용 유니버스(`GOLDEN_UNIVERSE`)는 쿨다운 후보 `T_K` 를 하나 더
갖는다 — 기존 세 후보의 경로(래치 BUY · 추격 상한 거부 · no_data 래치 BUY)를 지키면서 쿨다운
게이트를 태우려면 후보가 하나 더 필요하다.

### 적용 범위 — G1·G2 가 **지나지 않는** 것
- G1 은 `prepare` 한 번이다(틱 없음). G2 는 `check_buy_signal` 만 부른다.
- G2 가 지나는 매수 게이트 = 계좌 SOFT(미발동) · 후보 아님 · 창 밖(양 끝) · 쿨다운 · 당일 매수 ·
  래치(유지·재평가) · edge-crossing(전날 가격이 이미 위인 경우 포함) · 거래량 미달·미관측 · 추격 상한.
- 지나지 **않는** 것 = 예산(`calc_buy_quantity`·`_apply_budget_limit` — `check_buy_signal` 밖) ·
  래치 해제(`level_moved`·`stop_line`) · 보유·주문중·당일매도(`has_position`·`is_buy_pending`·
  `is_sold_today` — `T_HELD` 는 보유지만 틱이 없다) · `buy_disabled` · 최대 보유 수 · 일일 손실 한도.
  이 경로를 헬퍼가 오염시키면 골든은 못 잡는다 — 그 경로들은 이 사이클 이전과 같은 개별 테스트가 덮는다.

## 시계 규약 (freezegun 함정)

freezegun 은 naive `datetime.now()` 와 `datetime.now(KST)` 를 **9시간 어긋나게** 준다
(frozen 값을 naive 로는 그대로, aware 로는 UTC 로 해석). 운영 컨테이너(TZ=Asia/Seoul)에서는
둘이 같다. 이 파일은 frozen 값을 **KST 벽시계(naive)** 로 넣는다 — VCP 의 시각 판정(창 게이트·
D1 오전 판정·E2 창)은 naive 식이라 그대로 맞고, 날짜(`datetime.now(KST).date()`)는 naive
15:00 이전이면 같은 날이다. 16:25 저녁 prepare 는 aware 날짜가 다음 날로 넘어가지만 저녁
분기는 날짜를 쓰지 않는다(D1: 아무것도 하지 않는다).

⚠️ 따라서 인터페이스는 이렇게 고정한다(명세 「Red 확정 인터페이스」 절):
`run=`·watch `run_at`·`first_cross_at`·`first_tick_at`·`last_tick_at` = naive `datetime.now()` 의
`HH:MM:SS`(게이트와 같은 시계),
watch `date` = `datetime.now(KST).date()`.

## caplog 규약 (cycle252 T2)

행 수 단언은 전부 `levelno >= WARNING ∧ msg.startswith(마커 + " ")` 로 한정한다(`_warn_lines`).

## 돌연변이 → 죽이는 테스트

| 돌연변이 | 죽이는 테스트 |
|---|---|
| M1 훅이 `_prev_price` 를 쓰거나 조기 `return Signal.NONE` | `test_g2_golden_*` · `test_e2_observes_even_when_buy_disabled_and_leaves_prev_price` |
| M2 훅/①헬퍼의 자기 try 제거 | `test_e2_boom_watch_is_absorbed_and_g2_identical` · `test_d6_call_site_try_keeps_g1_when_helper_raises` · `test_d6_per_ticker_failure_skips_only_that_line` · `test_d6_helper_call_sites_are_wrapped_in_own_try` |
| M3 거리 분모 `base_high` / 부호 반대 | `test_d2_distance_denominator_sign_and_rounding` · `test_d1_morning_prepare_lines_match_literal` |
| M4 저녁 prepare 가 watch 교체·후보 줄 방출 | `test_d1_evening_prepare_emits_nothing_and_keeps_watch` · `test_d1_window_boundary_prepare` |
| M5 cap 제거 | `test_d4_reprepare_same_values_suppresses_candidate_lines` · `test_d4_cap_key_is_ticker_base_high_prev_close` · `test_f3_same_content_morning_reprepare_emits_summary_once` |
| M6 창 경계 `>`↔`>=` | `test_e2_window_boundaries` |
| M7 prepare 경로 — ① 헬퍼 쪽에서 `_candidates` 엔트리에 키 추가 | `test_g1_golden_*` |
| MA 틱 경로 — 훅이 `_candidates` 엔트리를 오염 | `test_g2_golden_*`(끝 상태 `candidates`) |
| MB ① 헬퍼가 `_cooldown_until` 을 비움(T_K 가 NONE→BUY) | `test_g1_golden_morning` · `test_g2_golden_*` |
| MC ① 헬퍼가 `_position_setup` 을 비움 | `test_g1_golden_morning` · `test_g2_golden_*` |
| MI ① 헬퍼가 `_prev_price`·`_vol_latch` 를 비움(T_B 09:19 가 NONE→BUY) | `test_g1_golden_morning` · `test_g2_golden_*` |
| M9a 요약 `crossed` 판정 `>=`→`>` (F1) | `test_e3_crossed_counts_tie_at_base_high` |
| Y4 `partial` 판정 `>`→`>=` | `test_e3_partial_boundary_at_entry_start` |
| `last_tick_at` 을 첫 틱에만 · `first_tick_at` 덮어쓰기 | `test_e2_window_boundaries` · `test_e3_observed_means_at_least_one_tick_not_full_window` |
| `not_retained` 분기 제거 · 판정 `<`→`<=` | `test_e3_summary_past_date_without_its_watch_is_not_retained` · `test_e3_summary_no_watch` |
| F3 요약 「직전과 같으면 생략」 제거 · 하루 전체 dedupe · 날짜 없는 키 · 좁은 키 · 생략이 watch 교체를 건너뜀 · 저녁 prepare 가 비교에 참여 | `test_f3_*` (①②⑤ · ③ · ④ · 키 4종 · ⑤ · ⑥) |
"""
from __future__ import annotations

import ast
import contextlib
import copy
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, StrategyConfig

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[4]
_VCP_PY = _REPO / "src" / "engine" / "strategies" / "vcp_breakout.py"
KST = timezone(timedelta(hours=9))
GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "cycle349_golden.json"

DIST_MARKER = "[vcp_breakout_distance]"
SUMMARY_MARKER = "[vcp_breakout_distance_summary]"

# ---------------------------------------------------------------------------
# 합성 시나리오 — 골든 생성 스크립트와 테스트가 **같은 함수**를 쓴다
# ---------------------------------------------------------------------------
#: 작은 EMA/베이스 파라미터로 시나리오를 결정론적으로 만든다(골든은 운영값 재현이 아니라
#: "확장 전후 산출이 같은가" 의 기준선이다). `effective_ema_long >= 30` 가드 때문에
#: ema_long 은 30 이상이어야 한다.
PARAMS: dict = {
    "ema_short": 10, "ema_mid": 20, "ema_long": 30, "long_ema_uptrend_days": 5,
    "daily_fetch_depth_mode": "full",
    "base_min_days": 10, "base_max_days": 20, "base_depth_pct": 0.30,
    "pullback_count_min": 1, "pullback_count_max": 4, "last_pullback_max": 0.15,
    "min_swing_atr_mult": 1.0, "volume_contraction_ratio": 1.0,
    "breakout_volume_mult": 1.2,
}

TRADE_DAY = date(2026, 9, 22)          # 화요일
LAST_BAR = date(2026, 9, 21)           # 전일(월) — 합성 일봉의 최신 봉

T_A = "900001"   # 통과 — 박스 최고가 = 베이스 첫 봉(20봉 전)
T_B = "900002"   # 통과 — 박스 최고가 동률 2봉(DESC idx 3·14) → 최신(idx 3) 채택
T_C = "900003"   # 통과 — DB ATR 불일치(>10%) 경로
T_D = "900004"   # 추세 필터 탈락(하락 추세) — G2 의 비후보 틱 종목
T_E = "900005"   # 베이스 탈락(마지막 10봉 +44% 급등, 깊이 > 30%)
T_F = "900006"   # pullback 탈락(평탄 드리프트 — swing 0)
T_G = "900007"   # 거래량 수축 탈락(마지막 5봉 급증)
T_H = "900008"   # 일봉 None
T_I = "900009"   # 일봉 30봉 — 가용 EMA 길이 20 < 30
T_J = "900010"   # 1단계 진입 차단(master block)
UNIVERSE = [T_A, T_B, T_C, T_D, T_E, T_F, T_G, T_H, T_I, T_J]
UNION = UNIVERSE + ["900011", "900012"]   # 시총·거래대금 컷 전
CANDIDATES = [T_A, T_B, T_C]

#: 골든(G1·G2) 전용 — 기본 유니버스(위)를 쓰는 리터럴 테스트와 섞지 않는다.
T_K = "900013"      # 통과(T_A 와 같은 일봉) — 교차일 쿨다운 D+3 중인 후보
T_HELD = "900020"   # 비후보 보유 종목(다른 날 매수) — `_position_setup` 만 남아 있다
GOLDEN_UNIVERSE = UNIVERSE + [T_K]

#: DB ATR 대역 — A=miss(None) / B=hit(588 대비 +2%) / C=mismatch(141 대비 −99%).
_DB_ATR = {T_A: None, T_B: 600, T_C: 1}


def _naive(hms: str, day: date = TRADE_DAY) -> str:
    """freezegun 에 넣을 KST 벽시계(naive) 문자열."""
    return f"{day.isoformat()} {hms}"


def _bar_dates(n: int, last: date = LAST_BAR) -> list[date]:
    """최신순(DESC) 영업일(주말 제외) n개."""
    out: list[date] = []
    d = last
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def _candles(chrono_closes: list[int], vols: list[int], *, highs: list[int] | None = None,
             last: date = LAST_BAR) -> list[dict]:
    """과거→최신 종가 배열로 KIS 원본 키 일봉(DESC, idx0=전일)을 만든다."""
    n = len(chrono_closes)
    ds = _bar_dates(n, last)
    rows = []
    for i in range(n):
        c = chrono_closes[n - 1 - i]
        h = highs[n - 1 - i] if highs else int(round(c * 1.01))
        lo = int(round(c * 0.99))
        rows.append({
            "stck_bsop_date": ds[i].strftime("%Y%m%d"),
            "stck_clpr": str(c), "stck_oprc": str(c),
            "stck_hgpr": str(h), "stck_lwpr": str(lo),
            "acml_vol": str(vols[n - 1 - i]),
        })
    return rows


def _uptrend(n: int, a: int, b: int) -> list[int]:
    return [int(round(a + (b - a) * i / (n - 1))) for i in range(n)]


def _base_contract(anchor: int) -> list[int]:
    """20봉 베이스 — 고점 → −12% → 반등 → −5% → 반등 → −2% → 마지막 상승."""
    pts = [1.00, 0.97, 0.94, 0.91, 0.88, 0.91, 0.94, 0.97, 0.99, 0.965,
           0.94, 0.955, 0.97, 0.985, 0.975, 0.965, 0.975, 0.985, 0.99, 0.995]
    return [int(round(anchor * p)) for p in pts]


def _base_c(anchor: int) -> list[int]:
    pts = [1.00, 0.96, 0.92, 0.89, 0.86, 0.88, 0.91, 0.95, 0.985, 0.97,
           0.955, 0.93, 0.945, 0.96, 0.975, 0.97, 0.962, 0.97, 0.978, 0.982]
    return [int(round(anchor * p)) for p in pts]


def build_series(*, today_bar_on: str | None = None) -> dict[str, list[dict] | None]:
    """종목별 합성 일봉. `today_bar_on=<ticker>` 면 그 종목 맨 앞에 **오늘 날짜** 부분봉
    (고가 99,999)을 끼운다 — `prepare` 의 `prev_idx=1` 슬라이스 이후 봉으로 거리를 재는지 본다."""
    series: dict[str, list[dict] | None] = {}
    series[T_A] = _candles(_uptrend(40, 6000, 10000) + _base_contract(10200),
                           [300_000] * 40 + [120_000] * 20)
    closes_b = _uptrend(40, 12000, 20000) + _base_contract(20400)
    highs_b = [int(round(c * 1.01)) for c in closes_b]
    tie_high = max(highs_b[40:]) + 150
    for desc_idx in (3, 14):
        highs_b[len(closes_b) - 1 - desc_idx] = tie_high
    series[T_B] = _candles(closes_b, [500_000] * 40 + [200_000] * 20, highs=highs_b)
    series[T_C] = _candles(_uptrend(40, 3000, 5000) + _base_c(5100),
                           [800_000] * 40 + [300_000] * 20)
    series[T_D] = _candles(_uptrend(60, 9000, 7000), [200_000] * 60)
    series[T_E] = _candles(_uptrend(50, 5000, 7000) + _uptrend(10, 7300, 10500),
                           [200_000] * 60)
    series[T_F] = _candles(_uptrend(40, 6000, 10000) + [10000 + 5 * i for i in range(20)],
                           [300_000] * 40 + [150_000] * 20)
    series[T_G] = _candles(_uptrend(40, 8000, 13000) + _base_contract(13300),
                           [400_000] * 20 + [100_000] * 20 + [100_000] * 15 + [900_000] * 5)
    series[T_H] = None
    series[T_I] = _candles(_uptrend(30, 6000, 9000), [300_000] * 30)
    series[T_J] = copy.deepcopy(series[T_A])   # 차단되므로 읽히지 않는다
    series[T_K] = copy.deepcopy(series[T_A])   # 골든 유니버스에서만 읽힌다
    if today_bar_on is not None:
        bar = {
            "stck_bsop_date": TRADE_DAY.strftime("%Y%m%d"),
            "stck_clpr": "10500", "stck_oprc": "10200", "stck_hgpr": "99999",
            "stck_lwpr": "10100", "acml_vol": "50000",
        }
        series[today_bar_on] = [bar] + list(series[today_bar_on] or [])
    return series


@contextlib.contextmanager
def prepare_env(series: dict | None = None):
    """prepare 의 외부 의존을 전부 대역으로. yield = 패치된 `scanner.ticker_prev_close`."""
    from src.engine import scanner as sc

    series = series if series is not None else build_series()
    names = {t: f"합성{t[-2:]}" for t in UNION + [T_K]}

    async def _fake_adapter(ticker, days=None, *, min_required=None):
        c = series.get(ticker)
        return copy.deepcopy(c) if c is not None else None

    async def _fake_db_atr(ticker, days=14):
        return _DB_ATR.get(ticker)

    with patch.object(sc, "ticker_names", names), \
            patch.object(sc, "ticker_prev_close", {}) as tpc, \
            patch("src.db.stock_master_daily.get_recent_daily_normalized", new=_fake_adapter), \
            patch("src.db.stock_master_daily.get_atr", new=_fake_db_atr):
        yield tpc


def make_strategy(params: dict | None = None, *, universe: list[str] | None = None,
                  blocked: str | None = T_J) -> VcpBreakoutStrategy:
    """유니버스·master block 을 인스턴스 대역으로 고정한 VCP 전략."""
    s = VcpBreakoutStrategy(StrategyConfig(
        strategy_id="vcp_breakout", name="VCP", weight=0.15,
        params=dict(params if params is not None else PARAMS),
    ))
    uni = list(UNIVERSE if universe is None else universe)
    union = list(UNION) + [t for t in uni if t not in UNION]   # 합집합 ⊇ 유니버스

    async def _fake_scan():
        s._scan_stage_counts = {"union_tickers": list(union), "trade_tickers": list(uni)}
        s._scan_stats["universe_union"] = len(union)
        s._scan_stats["universe_candidates"] = len(uni)
        s._scan_stats["mcap_pass"] = len(uni)
        s._scan_stats["universe_filtered"] = len(uni)
        return list(uni)

    async def _fake_block(tickers):
        if blocked is None or blocked not in tickers:
            return list(tickers), []
        kept = [t for t in tickers if t != blocked]
        return kept, [{"ticker": blocked, "name": f"합성{blocked[-2:]}",
                       "reason": "관리종목 (mang_issu_yn=Y)"}]

    s._scan_universe = _fake_scan
    s._apply_master_block_filter_in_prepare = _fake_block
    return s


def _jsonable(obj):
    """골든 비교용 직렬화 — 타입이 바뀌면(date→str 등) 값이 달라지도록 태그를 붙인다."""
    if isinstance(obj, datetime):
        return "datetime:" + obj.isoformat()
    if isinstance(obj, date):
        return "date:" + obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_jsonable(v) for v in obj)
    return obj


#: 교차일 상태 — `prepare` 가 **비우지 않는** 4필드(전날까지의 매매가 남긴 것). 골든 G1·G2 는
#: 새 인스턴스가 아니라 이 상태를 채운 인스턴스로 돈다. 새 인스턴스면 이 필드들이 전부 비어
#: 있어 ① 헬퍼가 덮어써도(`clear()` 등) 골든이 같게 나온다(verify 지적 1 — MB·MC·MI 생존).
SEED_COOLDOWN_UNTIL = TRADE_DAY + timedelta(days=3)
SEED_PREV_PRICE_B = 20_800          # T_B 돌파선 20,754 **위** — 전날 마지막 가격
SEED_LATCH_D = {                    # 어제 후보였다가 오늘 빠진 T_D 의 전일 무장 래치
    "armed_at": datetime(2026, 9, 21, 10, 0, tzinfo=KST),
    "armed_date": LAST_BAR,
    "base_high": 7_300,
    "base_low": 6_900,
}
SEED_SETUP_HELD = {"base_low": 48_000, "atr14": 1_250, "ema50": 49_500}


def seed_cross_day_state(s: VcpBreakoutStrategy) -> None:
    """prepare 전에 교차일 상태를 채운다 — 헬퍼가 이 중 하나라도 덮어쓰면 골든이 달라진다.

    - `_cooldown_until[T_K]` = D+3 — 쿨다운 중 후보. 지워지면 G2 의 T_K 틱이 NONE→BUY (MB)
    - `_position_setup[T_HELD]` + `state.positions[T_HELD]` — 비후보 보유. 지워지면 청산 셋업 소실 (MC)
    - `_prev_price[T_B]` = 돌파선 위 — 지워지면 G2 09:19 틱이 가짜 edge-crossing 이 되어 NONE→BUY (MI)
    - `_vol_latch[T_D]` = 전일 무장 — 비후보라 G2 에서 읽히지 않고 끝까지 남는다. 지워지면 끝 상태가 달라진다 (MI)
    """
    s._cooldown_until[T_K] = SEED_COOLDOWN_UNTIL
    s._prev_price[T_B] = SEED_PREV_PRICE_B
    s._vol_latch[T_D] = dict(SEED_LATCH_D)
    s._position_setup[T_HELD] = dict(SEED_SETUP_HELD)
    s.state.positions[T_HELD] = Position(
        ticker=T_HELD, buy_price=50_000, quantity=3, order_no="0000349",
        strategy_id="vcp_breakout", buy_date=date(2026, 9, 15),
    )


def g1_snapshot(s: VcpBreakoutStrategy, tpc: dict) -> dict:
    stats = {k: v for k, v in s._scan_stats.items() if k != "last_run_at"}
    return _jsonable({
        "candidates": s._candidates,
        "scanned": list(s._scanned_tickers),
        "scan_stats": stats,
        "funnel_steps": s._funnel_steps,
        "ticker_prev_close": dict(tpc),
        "bought_today": sorted(s._bought_today),
        "cooldown_until": s._cooldown_until,
        "prev_price": s._prev_price,
        "vol_latch": s._vol_latch,
        "position_setup": s._position_setup,
    })


async def run_g1(hms: str, *, distance_stub=None) -> dict:
    """G1 — 교차일 상태를 채운 인스턴스로 `hms`(KST 벽시계)에 prepare 1회.
    `distance_stub` 은 ① 헬퍼 대역."""
    s = make_strategy(universe=GOLDEN_UNIVERSE)
    seed_cross_day_state(s)
    s._bought_today.add("900099")   # prepare 가 비우는지(기존 동작)
    with prepare_env() as tpc, freeze_time(_naive(hms)):
        if distance_stub is not None:
            with patch.object(VcpBreakoutStrategy, "_observe_breakout_distance", distance_stub):
                await s.prepare()
        else:
            await s.prepare()
    return g1_snapshot(s, tpc)


#: G2 — (KST 벽시계, 종목, 현재가, 기록할 누적거래량|None). base_high: A·K 10302 · B 20754 · C 5151.
#: 거래량 문턱 = int(avg20 × 1.2): A·K 144,000 · B 240,000 · C 360,000.
G2_EVENTS: list[tuple[str, str, int, int | None]] = [
    ("09:04:59", T_A, 10_350, None),      # 창 밖(09:05 이전)
    ("09:05:00", T_A, 10_250, None),      # 창 안 — 돌파선 아래
    ("09:05:00", T_D, 7_000, None),       # 비후보(전일 래치 보유 — 읽히지 않고 남는다)
    ("09:10:00", T_A, 10_320, 143_999),   # 돌파 + 거래량 미달 → 래치 무장
    ("09:12:00", T_A, 10_280, None),      # 래치 유지(베이스 안)
    ("09:15:00", T_A, 10_400, 150_000),   # 거래량 충족 → BUY
    ("09:19:00", T_B, 20_760, 250_000),   # 돌파선 위지만 전날 가격(20,800)도 위 — edge 아님
    ("09:20:00", T_B, 20_700, None),      # 돌파선 아래
    ("09:21:00", T_B, 22_900, 250_000),   # 돌파 + 추격 상한(+10.3%) 초과 → 거부 + 래치
    ("09:22:00", T_B, 23_000, None),      # 래치 경로 재거부
    ("09:40:00", T_K, 10_320, 150_000),   # 돌파 + 거래량 충족이지만 쿨다운 중 → NONE
    ("10:00:00", T_C, 5_140, None),       # 돌파선 아래
    ("10:01:00", T_C, 5_151, None),       # 돌파(==base_high) + 미관측 → no_data + 래치
    ("14:30:00", T_C, 5_160, 360_000),    # 창 끝 경계(포함) — 래치 통과 → BUY
    ("14:30:00", T_A, 10_500, None),      # 당일 매수 종목
    ("14:30:01", T_B, 20_800, 250_000),   # 창 밖(14:30 초과)
]


async def play_g2(*, watch_factory=None) -> tuple[VcpBreakoutStrategy, list]:
    """G2 시나리오를 돌리고 (전략, 틱별 신호) 를 돌려준다 — 교차일 상태를 채운 인스턴스로
    07:45 prepare 후 `G2_EVENTS` 를 흘린다. `watch_factory` 는 ③ watch 대역(E2 never-raise)."""
    s = make_strategy(universe=GOLDEN_UNIVERSE)
    seed_cross_day_state(s)
    tick_volume.reset_for_test()
    signals: list = []
    try:
        with prepare_env():
            with freeze_time(_naive("07:45:00")):
                await s.prepare()
            if watch_factory is not None:
                s._breakout_watch = watch_factory()
            with freeze_time(_naive("09:00:00")) as frozen:
                for hms, ticker, price, vol in G2_EVENTS:
                    frozen.move_to(_naive(hms))
                    if vol is not None:
                        tick_volume.record_acml_vol(ticker, vol)
                    sig = s.check_buy_signal(ticker, price, price)
                    signals.append([hms, ticker, price, sig.name])
    finally:
        tick_volume.reset_for_test()
    return s, signals


async def run_g2(*, watch_factory=None) -> dict:
    """G2 — `play_g2` 의 틱별 신호 + 끝 상태 스냅샷(골든 비교 대상)."""
    s, signals = await play_g2(watch_factory=watch_factory)
    stats = {k: v for k, v in s._scan_stats.items() if k != "last_run_at"}
    return _jsonable({
        "signals": signals,
        "end": {
            "prev_price": s._prev_price,
            "vol_latch": s._vol_latch,
            "bought_today": sorted(s._bought_today),
            "scan_stats": stats,
            "gate_emit_capped": sorted([list(k) for k in s._gate_emit_capped]),
            "buy_signals": s.state.buy_signals,
            "position_setup": s._position_setup,
            "cooldown_until": s._cooldown_until,
            "candidates": s._candidates,
        },
    })


def _golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _series_without(ticker: str) -> dict:
    """후보 하나의 일봉을 None 으로 뺀 시리즈 — 요약 내용(n·tickers)을 바꾸는 가장 작은 변형.
    같은 목록으로 두 번 부르면 F3(직전과 같은 요약 생략)이 줄을 지워 다른 판정과 섞인다."""
    series = build_series()
    series[ticker] = None
    return series


def _warn_lines(caplog, marker: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(marker + " ")
    ]


def _parse(line: str) -> dict[str, str]:
    return dict(tok.split("=", 1) for tok in line.split() if "=" in tok)


async def _prepare_at(s: VcpBreakoutStrategy, hms: str, *, day: date = TRADE_DAY,
                      series: dict | None = None) -> None:
    with prepare_env(series), freeze_time(_naive(hms, day)):
        await s.prepare()


def _tick(s: VcpBreakoutStrategy, hms: str, ticker: str, price: int, *,
          day: date = TRADE_DAY):
    with freeze_time(_naive(hms, day)):
        return s.check_buy_signal(ticker, price, price)


def _need(obj, name: str):
    fn = getattr(obj, name, None)
    if fn is None:
        pytest.fail(f"미구현: {type(obj).__name__}.{name} 가 없다 (cycle349 — 명세 「Red 확정 인터페이스」)")
    return fn


class _BoomWatch(dict):
    """어떤 조회에도 터지는 watch — 훅·요약의 never-raise 와 **배선 여부**를 함께 잰다."""

    def __init__(self):
        super().__init__()
        self.touched = 0

    def _boom(self, *a, **k):
        self.touched += 1
        raise RuntimeError("boom watch (cycle349 test)")

    __getitem__ = _boom
    __contains__ = _boom
    __iter__ = _boom
    get = _boom
    keys = _boom
    items = _boom
    values = _boom

    def __bool__(self):
        return True


@pytest.fixture(autouse=True)
def _isolate_tick_volume():
    tick_volume.reset_for_test()
    yield
    tick_volume.reset_for_test()


# ###########################################################################
# 골든 — 확장 전 HEAD 산출과의 완전 일치 (지금 HEAD 에서 초록이어야 한다)
# ###########################################################################

async def test_g1_golden_morning_matches_pre_extension():
    """G1 — 07:45 prepare 의 `_candidates` 전체·`_scanned_tickers`·`_scan_stats`(last_run_at 제외)·
    `_funnel_steps`·`ticker_prev_close`·`_bought_today` 가 확장 전과 같다(M7 포함)."""
    assert await run_g1("07:45:00") == _golden()["g1_morning"]


async def test_g1_golden_evening_matches_pre_extension():
    """G1 — 16:25 저녁 재준비도 같은 산출(저녁 분기는 관측만 건너뛴다)."""
    assert await run_g1("16:25:00") == _golden()["g1_evening"]


async def test_g2_golden_matches_pre_extension():
    """G2 — 창 경계·돌파·래치·거래량 미달·추격 상한·no_data 를 섞은 틱 시퀀스의 매 틱 신호와
    끝 상태(`_prev_price`·`_vol_latch`·`_bought_today`·`_scan_stats`·`_gate_emit_capped`·
    `state.buy_signals`·`_position_setup`)가 확장 전과 같다(M1)."""
    assert await run_g2() == _golden()["g2"]


def test_golden_fixture_is_from_head_2ef289b():
    """골든의 출처 기록 — 재생성하면 이 값이 바뀌어야 한다(몰래 재생성 방지)."""
    meta = _golden()["_meta"]
    assert meta["source_commit"].startswith("2ef289b")
    assert meta["revision"] == 2, "교차일 상태를 채운 골든(v2)이어야 한다"
    assert set(_golden()) == {"_meta", "g1_morning", "g1_evening", "g2"}
    g1_keys = {"cooldown_until", "prev_price", "vol_latch", "position_setup"}
    assert g1_keys <= set(_golden()["g1_morning"])
    assert g1_keys | {"candidates"} <= set(_golden()["g2"]["end"])


# ###########################################################################
# ① D1 — 오전 판정 (게이트와 같은 식: naive now().time() <= entry_end)
# ###########################################################################

#: 합성 시나리오 07:45 prepare 가 남겨야 하는 줄 — 명세 D2/D3 식으로 손계산한 리터럴.
#: A: (10302−10149)/10149×100 = 1.5075… · B: (20754−20298)/20298×100 = 2.2465…(동률 → idx3) ·
#: C: (5151−5008)/5008×100 = 2.8554…
_EXPECTED_MORNING_LINES = [
    "[vcp_breakout_distance] run=07:45:00 ticker=900001 base_high=10302 prev_close=10149 "
    "dist_pct=+1.51 box_high_date=20260825 box_high_ago=20 base_low=8886 base_len=20",
    "[vcp_breakout_distance] run=07:45:00 ticker=900002 base_high=20754 prev_close=20298 "
    "dist_pct=+2.25 box_high_date=20260916 box_high_ago=4 base_low=17772 base_len=20",
    "[vcp_breakout_distance] run=07:45:00 ticker=900003 base_high=5151 prev_close=5008 "
    "dist_pct=+2.86 box_high_date=20260825 box_high_ago=20 base_low=4342 base_len=20",
]
_EXPECTED_MORNING_SUMMARY = (
    "[vcp_breakout_distance_summary] run=07:45:00 n=3 median_pct=2.25 within5=3 over10=0 "
    "tickers=900001,900002,900003"
)


async def test_d1_morning_prepare_lines_match_literal(caplog):
    """오전 prepare = 후보별 1줄(삽입 순서) + 요약 1줄, 전부 WARNING. 값은 손계산 리터럴과 일치
    (분모 = 전일 종가 · 부호 · 소수 2자리 · 동률이면 최신 봉)."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")

    assert _warn_lines(caplog, DIST_MARKER) == _EXPECTED_MORNING_LINES
    assert _warn_lines(caplog, SUMMARY_MARKER) == [_EXPECTED_MORNING_SUMMARY]


async def test_d1_evening_prepare_emits_nothing_and_keeps_watch(caplog):
    """저녁(16:25) 재준비는 줄 0 + watch 무접촉(같은 객체·같은 내용) — M4."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    watch = _need(s, "_breakout_watch")
    before = copy.deepcopy(watch)
    caplog.clear()

    await _prepare_at(s, "16:25:00")

    assert _warn_lines(caplog, DIST_MARKER) == []
    assert _warn_lines(caplog, SUMMARY_MARKER) == []
    assert s._breakout_watch is watch, "저녁 prepare 가 watch 를 교체했다(오전/저녁 혼동)"
    assert s._breakout_watch == before


@pytest.mark.parametrize("hms,emits", [("14:30:00", True), ("14:30:01", False)])
async def test_d1_window_boundary_prepare(caplog, hms, emits):
    """D1 경계 — 창 끝(14:30) **이하**면 오전, 초과면 저녁(게이트 `now_t > entry_end` 와 같은 식).

    양성 대조군 = 07:45 prepare 가 먼저 요약 1줄을 남긴다(없으면 부정 단언이 공허하다).
    두 번째 prepare 는 후보 하나를 뺀 목록이다 — 같은 목록이면 F3 생략이 줄을 지워 경계 판정과
    구분되지 않는다."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    assert len(_warn_lines(caplog, SUMMARY_MARKER)) == 1, "양성 대조군: 오전 prepare 요약 줄 부재"
    first_watch = _need(s, "_breakout_watch")

    await _prepare_at(s, hms, series=_series_without(T_C))
    assert list(s._candidates) == [T_A, T_B], "대조군: 두 번째 prepare 의 목록이 실제로 달라야 한다"
    summary = _warn_lines(caplog, SUMMARY_MARKER)
    if emits:
        assert len(summary) == 2 and f"run={hms} " in summary[1]
        assert _parse(summary[1])["tickers"] == f"{T_A},{T_B}"
        assert s._breakout_watch is not first_watch and s._breakout_watch["run_at"] == hms
    else:
        assert len(summary) == 1
        assert s._breakout_watch is first_watch


async def test_d1_uses_entry_end_param_not_literal(caplog):
    """오전 판정은 params 의 entry_end 를 읽는다 — 리터럴 14:30 하드코딩 금지."""
    s = make_strategy({**PARAMS, "entry_end": "10:00"})
    await _prepare_at(s, "09:59:00")
    assert len(_warn_lines(caplog, SUMMARY_MARKER)) == 1, "entry_end=10:00 이면 09:59 는 오전이다"
    await _prepare_at(s, "10:30:00")
    assert len(_warn_lines(caplog, SUMMARY_MARKER)) == 1, "entry_end=10:00 이면 10:30 은 저녁이다"


# ###########################################################################
# ① D2 — 후보별 줄의 값 (헬퍼 직접 호출)
# ###########################################################################

def _refs_entry(s: VcpBreakoutStrategy, ticker: str, *, base_high: int, prev_close: int,
                base_low: int = 9_000, base_len: int = 10,
                highs: list[int] | None = None) -> dict:
    """헬퍼 입력 한 종목분 — `_candidates` 와 refs 를 **서로 모순 없이** 같이 채운다
    (구현이 어느 쪽에서 읽든 같은 답이 나오게)."""
    n = len(highs) if highs is not None else max(base_len + 5, 12)
    ds = _bar_dates(n)
    hs = list(highs) if highs is not None else [base_high] + [base_high - 50] * (n - 1)
    candles = [{
        "stck_bsop_date": ds[i].strftime("%Y%m%d"),
        "stck_clpr": str(prev_close if i == 0 else base_high - 100),
        "stck_hgpr": str(hs[i]), "stck_lwpr": str(base_low),
        "stck_oprc": str(prev_close), "acml_vol": "100000",
    } for i in range(n)]
    base = {"high": base_high, "low": base_low, "length": base_len, "avg_volume_20": 100_000}
    s._candidates[ticker] = {
        "base_high": base_high, "base_low": base_low, "last_pullback_pct": 0.05,
        "atr14": 100, "ema50": 1, "ema150": 1, "ema200": 1,
        "prev_close": prev_close, "avg_volume_20": 100_000,
    }
    return {"candles": candles, "base": base}


def _call_distance(s: VcpBreakoutStrategy, refs: dict, hms: str = "07:45:00",
                   day: date = TRADE_DAY) -> None:
    fn = _need(s, "_observe_breakout_distance")
    with freeze_time(_naive(hms, day)):
        fn(refs)


def test_d2_distance_denominator_sign_and_rounding(caplog):
    """dist_pct = (base_high − prev_close) / **prev_close** × 100, 소수 2자리, 부호 명시 — M3."""
    s = make_strategy()
    refs = {
        "900101": _refs_entry(s, "900101", base_high=10_830, prev_close=9_870),   # +9.7264 → +9.73
        "900102": _refs_entry(s, "900102", base_high=9_500, prev_close=10_000),   # −5.00
        "900103": _refs_entry(s, "900103", base_high=11_000, prev_close=10_000),  # +10.00 (분모 base_high 면 9.09)
    }
    _call_distance(s, refs)
    got = {_parse(l)["ticker"]: _parse(l)["dist_pct"] for l in _warn_lines(caplog, DIST_MARKER)}
    assert got == {"900101": "+9.73", "900102": "-5.00", "900103": "+10.00"}


def test_d2_na_when_prev_close_nonpositive(caplog):
    """prev_close ≤ 0 → dist_pct=na, 요약 중앙값·within5·over10 집계에서 빠진다."""
    s = make_strategy()
    refs = {
        "900201": _refs_entry(s, "900201", base_high=10_000, prev_close=0),
        "900202": _refs_entry(s, "900202", base_high=10_300, prev_close=10_000),   # +3.00
    }
    _call_distance(s, refs)
    rows = {_parse(l)["ticker"]: _parse(l) for l in _warn_lines(caplog, DIST_MARKER)}
    assert rows["900201"]["dist_pct"] == "na"
    assert rows["900201"]["prev_close"] == "0"
    summary = _parse(_warn_lines(caplog, SUMMARY_MARKER)[0])
    assert summary["median_pct"] == "3.00"
    assert summary["within5"] == "1" and summary["over10"] == "0"
    assert summary["n"] == "2"


def test_d2_box_high_date_tie_picks_most_recent(caplog):
    """박스 창 안 동률 최고가 → 가장 최근(인덱스 최소) 봉. ago = 인덱스 + 1(전일 = 1)."""
    s = make_strategy()
    hs = [9_900, 9_950, 10_000, 9_800, 9_700, 9_600, 10_000, 9_500, 9_400, 9_300,
          9_200, 9_100, 9_000, 9_000, 9_000]
    refs = {"900301": _refs_entry(s, "900301", base_high=10_000, prev_close=9_900,
                                  base_len=10, highs=hs)}
    _call_distance(s, refs)
    row = _parse(_warn_lines(caplog, DIST_MARKER)[0])
    assert row["box_high_ago"] == "3"
    assert row["box_high_date"] == _bar_dates(15)[2].strftime("%Y%m%d")
    assert row["base_len"] == "10" and row["base_low"] == "9000"


def test_d2_box_high_searched_only_inside_base_window(caplog):
    """박스 창은 `candles[:base_len]` 뿐 — 창 밖 봉이 base_high 와 같아도 쓰지 않는다. 못 찾으면 na."""
    s = make_strategy()
    hs = [9_900] * 10 + [10_000] * 5         # base_high 는 창 밖(idx 10~14)에만 있다
    refs = {"900401": _refs_entry(s, "900401", base_high=10_000, prev_close=9_900,
                                  base_len=10, highs=hs)}
    _call_distance(s, refs)
    row = _parse(_warn_lines(caplog, DIST_MARKER)[0])
    assert row["box_high_date"] == "na" and row["box_high_ago"] == "na"


async def test_d2_measures_after_today_bar_slice(caplog):
    """오늘 날짜 부분봉이 끼면 prepare 는 `candles[1:]` 로 판정한다 — 거리·박스도 **슬라이스 뒤**
    일봉(전일 = candles[0])으로 잰다. 오늘봉(고가 99,999·종가 10,500)이 새면 값이 달라진다."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00", series=build_series(today_bar_on=T_A))
    lines = [l for l in _warn_lines(caplog, DIST_MARKER) if "ticker=900001 " in l]
    assert lines == [_EXPECTED_MORNING_LINES[0]]


# ###########################################################################
# ① D3 — run 요약 줄
# ###########################################################################

def test_d3_summary_median_odd(caplog):
    s = make_strategy()
    refs = {
        "900501": _refs_entry(s, "900501", base_high=10_123, prev_close=10_000),   # 1.23
        "900502": _refs_entry(s, "900502", base_high=10_830, prev_close=9_870),    # 9.7264
        "900503": _refs_entry(s, "900503", base_high=11_500, prev_close=10_000),   # 15.00
    }
    _call_distance(s, refs, "08:03:38")
    lines = _warn_lines(caplog, SUMMARY_MARKER)
    assert lines == [
        "[vcp_breakout_distance_summary] run=08:03:38 n=3 median_pct=9.73 within5=1 "
        "over10=1 tickers=900501,900502,900503"
    ]


def test_d3_summary_median_even_is_mean_of_middles(caplog):
    s = make_strategy()
    refs = {
        "900601": _refs_entry(s, "900601", base_high=10_200, prev_close=10_000),   # 2
        "900602": _refs_entry(s, "900602", base_high=10_400, prev_close=10_000),   # 4
        "900603": _refs_entry(s, "900603", base_high=11_200, prev_close=10_000),   # 12
        "900604": _refs_entry(s, "900604", base_high=12_000, prev_close=10_000),   # 20
    }
    _call_distance(s, refs)
    summary = _parse(_warn_lines(caplog, SUMMARY_MARKER)[0])
    assert summary["median_pct"] == "8.00"
    assert summary["within5"] == "2" and summary["over10"] == "2"
    assert summary["n"] == "4"


async def test_n0_early_return_emits_summary_and_empty_watch(caplog, fast_sleep):
    """유니버스 0종목 조기 반환 분기도 요약 1줄(n=0) + watch 를 빈 tickers 로 교체한다."""
    s = make_strategy(universe=[], blocked=None)
    await _prepare_at(s, "07:45:00")
    assert _warn_lines(caplog, DIST_MARKER) == []
    assert _warn_lines(caplog, SUMMARY_MARKER) == [
        "[vcp_breakout_distance_summary] run=07:45:00 n=0 median_pct=na within5=0 over10=0 tickers=-"
    ]
    watch = _need(s, "_breakout_watch")
    assert watch == {"date": TRADE_DAY, "run_at": "07:45:00", "tickers": {}}


# ###########################################################################
# ① D4 — 후보 줄 하루 1회 cap (키 = (ticker, base_high, prev_close))
# ###########################################################################

async def test_d4_reprepare_same_values_suppresses_candidate_lines(caplog):
    """07:55 재준비가 같은 값을 내면 후보 줄은 생략된다 — M5(후보 cap).

    요약 줄은 이 cap 밖이다. 같은 내용의 요약은 D3 개정(F3 — 직전 요약과 같으면 생략)으로 따로
    생략되며 그 규칙은 `test_f3_*` 가 잰다."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    await _prepare_at(s, "07:55:00")
    assert s._breakout_watch["run_at"] == "07:55:00", "대조군: 07:55 재준비가 오전 경로를 탔다"
    assert _warn_lines(caplog, DIST_MARKER) == _EXPECTED_MORNING_LINES


def test_d4_cap_key_is_ticker_base_high_prev_close(caplog):
    """값이 바뀐 종목만 다시 찍힌다(base_high 또는 prev_close). 새 종목도 찍힌다."""
    s = make_strategy()
    refs1 = {
        "900701": _refs_entry(s, "900701", base_high=10_300, prev_close=10_000),
        "900702": _refs_entry(s, "900702", base_high=20_600, prev_close=20_000),
    }
    _call_distance(s, refs1, "07:45:00")
    s._candidates.clear()
    refs2 = {
        "900701": _refs_entry(s, "900701", base_high=10_300, prev_close=10_000),   # 같음 → 생략
        "900702": _refs_entry(s, "900702", base_high=20_600, prev_close=19_900),   # prev 변경 → 찍힘
        "900703": _refs_entry(s, "900703", base_high=5_150, prev_close=5_000),     # 새 종목 → 찍힘
    }
    _call_distance(s, refs2, "07:55:00")
    tickers = [_parse(l)["ticker"] for l in _warn_lines(caplog, DIST_MARKER)]
    assert tickers == ["900701", "900702", "900702", "900703"]


def test_d4_cap_resets_on_next_kst_day(caplog):
    s = make_strategy()
    refs = {"900801": _refs_entry(s, "900801", base_high=10_300, prev_close=10_000)}
    _call_distance(s, refs, "07:45:00", TRADE_DAY)
    _call_distance(s, refs, "07:45:00", TRADE_DAY + timedelta(days=1))
    assert len(_warn_lines(caplog, DIST_MARKER)) == 2


def test_d4_cap_is_strategy_owned_kst_daily_cap():
    """cap 인스턴스는 전략 객체 소유 `KstDailyEmitCap` (모듈 전역 금지)."""
    from src.engine.daily_emit_cap import KstDailyEmitCap

    s1, s2 = make_strategy(), make_strategy()
    cap1 = _need(s1, "_breakout_distance_cap")
    assert isinstance(cap1, KstDailyEmitCap)
    assert cap1 is not s2._breakout_distance_cap


# ###########################################################################
# ① D5·D6 — 읽기 전용 · never-raise
# ###########################################################################

async def test_d6_call_site_try_keeps_g1_when_helper_raises():
    """헬퍼가 무엇을 던져도 prepare 는 확장 전과 같은 상태로 끝난다(G1 골든) — 호출부 자기 try (M2)."""
    stub = MagicMock(side_effect=RuntimeError("boom distance"))
    got = await run_g1("07:45:00", distance_stub=stub)
    assert stub.call_count >= 1, "① 헬퍼가 prepare 끝에서 호출되지 않았다"
    assert got == _golden()["g1_morning"]


def test_d6_per_ticker_failure_skips_only_that_line(caplog):
    """한 종목 계산 실패 = 그 종목 줄만 생략. 헬퍼는 예외를 던지지 않고 요약도 남긴다.

    실패 주입 = 그 종목 refs 엔트리가 어떤 조회에도 터진다(`_BoomWatch`) — 구현이 엔트리를
    어떻게 읽든(`["candles"]`·`.get`) 계산 불가가 확정이다."""
    s = make_strategy()
    refs = {
        "900901": _BoomWatch(),                                    # 계산 불가
        "900902": _refs_entry(s, "900902", base_high=10_300, prev_close=10_000),
    }
    s._candidates["900901"] = {"base_high": 10_000, "base_low": 9_000, "prev_close": 9_500,
                               "avg_volume_20": 1, "atr14": 1, "ema50": 1, "ema150": 1,
                               "ema200": 1, "last_pullback_pct": 0.0}
    _call_distance(s, refs)
    tickers = [_parse(l)["ticker"] for l in _warn_lines(caplog, DIST_MARKER)]
    assert tickers == ["900902"]
    summaries = _warn_lines(caplog, SUMMARY_MARKER)
    assert len(summaries) == 1 and "900902" in _parse(summaries[0])["tickers"]


def test_d6_helper_call_sites_are_wrapped_in_own_try():
    """AST — prepare 안 ① 헬퍼 호출은 2곳(정상 끝 · `if not tickers` 조기 반환)이고 둘 다
    `except Exception` 을 가진 **자기 try** 안이다. 정상 끝 호출은 `VCP 준비 완료` 로그 뒤다."""
    src = _VCP_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    prep = next(n for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "prepare")

    def _is_helper_call(n):
        return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "_observe_breakout_distance")

    calls = [n for n in ast.walk(prep) if _is_helper_call(n)]
    assert len(calls) == 2, f"① 헬퍼 호출 {len(calls)}곳 — 정상 끝 1 + 조기 반환 1 이어야 한다"

    def _enclosing_try(target):
        for t in ast.walk(prep):
            if isinstance(t, ast.Try) and any(n is target for s_ in t.body for n in ast.walk(s_)):
                if any(isinstance(h.type, ast.Name) and h.type.id == "Exception"
                       for h in t.handlers):
                    return t
        return None

    for c in calls:
        assert _enclosing_try(c) is not None, f"line {c.lineno}: 자기 try(except Exception) 밖"

    done_log = next(n for n in ast.walk(prep)
                    if isinstance(n, ast.Call) and any(
                        isinstance(a, ast.Constant) and isinstance(a.value, str)
                        and a.value.startswith("VCP 준비 완료") for a in n.args))
    assert max(c.lineno for c in calls) > done_log.lineno

    early_if = next(n for n in ast.walk(prep)
                    if isinstance(n, ast.If) and isinstance(n.test, ast.UnaryOp)
                    and isinstance(n.test.op, ast.Not) and isinstance(n.test.operand, ast.Name)
                    and n.test.operand.id == "tickers"
                    and any(isinstance(s_, ast.Return) for s_ in n.body))
    assert any(_is_helper_call(n) for s_ in early_if.body for n in ast.walk(s_)), (
        "`if not tickers:` 조기 반환 분기에서도 ① 헬퍼를 불러야 한다(n=0 요약)"
    )


# ###########################################################################
# ③ E1 — 관측 대상(watch)
# ###########################################################################

#: watch 엔트리의 관측 필드 초기값.
_FRESH_ENT = {"max": 0, "ticks": 0, "first_cross_at": None,
              "first_tick_at": None, "last_tick_at": None}


async def test_e1_morning_prepare_sets_watch_structure():
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    watch = _need(s, "_breakout_watch")
    assert watch == {
        "date": TRADE_DAY,
        "run_at": "07:45:00",
        "tickers": {
            T_A: {"base_high": 10_302, **_FRESH_ENT},
            T_B: {"base_high": 20_754, **_FRESH_ENT},
            T_C: {"base_high": 5_151, **_FRESH_ENT},
        },
    }
    assert list(watch["tickers"]) == list(s._candidates)
    assert all(watch["tickers"][t]["base_high"] == s._candidates[t]["base_high"]
               for t in s._candidates)


def test_e1_fresh_strategy_has_no_watch():
    """`__init__` 가 `_breakout_watch = None` 으로 시작한다(요약의 no_watch 근거)."""
    s = make_strategy()
    assert hasattr(s, "_breakout_watch"), "미구현: 초기값 None 인 `_breakout_watch` 속성"
    assert s._breakout_watch is None


async def test_e1_morning_reprepare_replaces_watch():
    """오전 재준비는 watch 를 **통째로** 교체한다(누적 관측 초기화 + run_at 갱신)."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    first = _need(s, "_breakout_watch")
    first["tickers"][T_A]["ticks"] = 7   # 누적 흔적

    await _prepare_at(s, "07:55:00")
    assert s._breakout_watch is not first
    assert s._breakout_watch["run_at"] == "07:55:00"
    assert s._breakout_watch["tickers"][T_A]["ticks"] == 0


# ###########################################################################
# ③ E2 — 틱 관측 훅
# ###########################################################################

def test_e2_hook_is_second_statement_of_check_buy_signal():
    """AST — 첫 문장(계좌 SOFT 게이트 if, cycle233 고정) **바로 다음**이
    `self._observe_breakout_tick(ticker, current_price)` 한 줄이고, 본문에 1회뿐이다."""
    tree = ast.parse(_VCP_PY.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "VcpBreakoutStrategy")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
              and n.name == "check_buy_signal")
    body = [s_ for s_ in fn.body
            if not (isinstance(s_, ast.Expr) and isinstance(s_.value, ast.Constant))]
    assert isinstance(body[0], ast.If), "첫 문장은 계좌 SOFT 게이트 if 그대로(cycle233)"
    second = body[1]
    assert isinstance(second, ast.Expr) and isinstance(second.value, ast.Call), (
        "두 번째 문장이 훅 호출 한 줄이 아니다"
    )
    call = second.value
    assert isinstance(call.func, ast.Attribute) and call.func.attr == "_observe_breakout_tick"
    assert isinstance(call.func.value, ast.Name) and call.func.value.id == "self"
    assert [a.id for a in call.args if isinstance(a, ast.Name)] == ["ticker", "current_price"]
    n_calls = sum(1 for n in ast.walk(fn) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "_observe_breakout_tick")
    assert n_calls == 1


async def test_e2_window_boundaries():
    """창 경계: 09:04:59 미관측 · 09:05:00 관측 · 14:30:00 관측 · 14:30:01 미관측 — M6."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    _tick(s, "09:04:59", T_A, 99_000)
    _tick(s, "09:05:00", T_A, 10_100)
    _tick(s, "14:30:00", T_A, 10_150)
    _tick(s, "14:30:01", T_A, 98_000)
    ent = s._breakout_watch["tickers"][T_A]
    assert ent["ticks"] == 2
    assert ent["max"] == 10_150
    assert ent["first_cross_at"] is None
    assert (ent["first_tick_at"], ent["last_tick_at"]) == ("09:05:00", "14:30:00")


async def test_e2_uses_entry_window_params():
    """창은 매 틱 params 에서 읽는다(entry_start/entry_end)."""
    s = make_strategy({**PARAMS, "entry_start": "10:00", "entry_end": "11:00"})
    await _prepare_at(s, "07:45:00")
    _tick(s, "09:30:00", T_A, 10_100)
    _tick(s, "10:30:00", T_A, 10_120)
    _tick(s, "11:30:00", T_A, 10_140)
    assert s._breakout_watch["tickers"][T_A]["ticks"] == 1


async def test_e2_non_candidate_tick_ignored():
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    before = copy.deepcopy(s._breakout_watch)
    _tick(s, "10:00:00", T_D, 7_000)
    _tick(s, "10:00:00", "999999", 1_000)
    assert s._breakout_watch == before


async def test_e2_first_cross_at_set_once_and_max_tracked():
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    _tick(s, "09:06:00", T_A, 10_000)
    _tick(s, "09:07:00", T_A, 10_302)      # == base_high → 최초 돌파
    _tick(s, "09:08:00", T_A, 10_200)
    _tick(s, "09:09:00", T_A, 10_400)
    ent = s._breakout_watch["tickers"][T_A]
    assert ent == {"base_high": 10_302, "max": 10_400, "ticks": 4, "first_cross_at": "09:07:00",
                   "first_tick_at": "09:06:00", "last_tick_at": "09:09:00"}


async def test_e2_observes_even_when_buy_disabled_and_leaves_prev_price():
    """훅은 매수 게이트들보다 **앞**이라 buy_disabled 여도 관측한다. 그리고 watch 말고는 아무것도
    건드리지 않는다 — `_prev_price` 에 흔적이 남으면 M1."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    s.state.buy_disabled = True
    sig = _tick(s, "10:00:00", T_A, 10_310)
    assert sig.name == "NONE"
    assert s._breakout_watch["tickers"][T_A]["ticks"] == 1
    assert s._breakout_watch["tickers"][T_A]["first_cross_at"] == "10:00:00"
    assert T_A not in s._prev_price
    assert s._vol_latch == {} and s._gate_emit_capped == set()


async def test_e2_date_mismatch_ignored():
    """watch date ≠ 오늘(KST) → 관측 안 함(어제 watch 에 오늘 틱이 섞이지 않는다)."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    before = copy.deepcopy(s._breakout_watch)
    _tick(s, "10:00:00", T_A, 10_400, day=TRADE_DAY + timedelta(days=1))
    assert s._breakout_watch == before


async def test_e2_nonpositive_price_ignored():
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    _tick(s, "10:00:00", T_A, 0)
    _tick(s, "10:00:01", T_A, -5)
    assert s._breakout_watch["tickers"][T_A]["ticks"] == 0


async def test_e2_boom_watch_is_absorbed_and_g2_identical():
    """훅 본체 never-raise — watch 조회가 터져도 G2 가 골든과 같다. 그리고 훅이 실제로 watch 를
    건드렸다(배선 증명) — 자기 try 를 빼면(M2) 예외가 on_tick 으로 샌다."""
    made: list[_BoomWatch] = []

    def _factory():
        w = _BoomWatch()
        made.append(w)
        return w

    got = await run_g2(watch_factory=_factory)
    assert made and made[0].touched > 0, "훅이 check_buy_signal 에서 watch 를 조회하지 않았다"
    assert got == _golden()["g2"]


# ###########################################################################
# ③ E3 — 하루 요약 (순수 읽기)
# ###########################################################################

def test_e3_summary_no_watch():
    """오늘인데 watch 가 없다 = 「관측 대상이 없어 모른다」(no_watch)."""
    s = make_strategy()
    fn = _need(s, "breakout_event_summary")
    with freeze_time(_naive("12:00:00")):
        assert fn(TRADE_DAY) == {"status": "no_watch", "date": "2026-09-22"}


async def test_e3_summary_past_date_without_its_watch_is_not_retained():
    """지난 날짜인데 이 프로세스가 그날 watch 를 갖고 있지 않다 = `not_retained` — 그날 관측됐는지
    이 프로세스는 모른다(그날 값의 정본은 그날 `daily_log_reports.metrics`). `no_watch`(오늘 대상이
    없었다)와 다른 사실이라 이름을 가른다(verify 지적 4). watch 가 있든 없든 같다."""
    yesterday = TRADE_DAY - timedelta(days=1)
    fresh = make_strategy()
    with freeze_time(_naive("12:00:00")):
        assert fresh.breakout_event_summary(yesterday) == {
            "status": "not_retained", "date": yesterday.isoformat(),
        }
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    with freeze_time(_naive("12:00:00")):
        assert s.breakout_event_summary(yesterday) == {
            "status": "not_retained", "date": yesterday.isoformat(),
        }
        # 대조군 — 같은 시각 오늘 날짜는 ok
        assert s.breakout_event_summary(TRADE_DAY)["status"] == "ok"


async def test_e3_summary_future_date_is_no_watch():
    """오늘 이후 날짜(= 아직 prepare 전)는 not_retained 가 아니라 no_watch."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    tomorrow = TRADE_DAY + timedelta(days=1)
    with freeze_time(_naive("12:00:00")):
        assert s.breakout_event_summary(tomorrow) == {
            "status": "no_watch", "date": tomorrow.isoformat(),
        }


async def test_e3_past_date_with_its_watch_is_ok():
    """자정을 넘겨도 그날 watch 를 아직 들고 있으면 ok — 날짜 비교가 먼저다."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    with freeze_time(_naive("00:30:00", TRADE_DAY + timedelta(days=1))):
        assert s.breakout_event_summary(TRADE_DAY)["status"] == "ok"


async def test_e3_summary_ok_structure():
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    _tick(s, "09:30:00", T_A, 10_250)       # 관측 · 미돌파
    _tick(s, "10:00:00", T_B, 20_800)       # 돌파
    _tick(s, "10:05:00", T_B, 21_000)
    before = copy.deepcopy(s._breakout_watch)

    got = s.breakout_event_summary(TRADE_DAY)

    assert got == {
        "status": "ok",
        "date": "2026-09-22",
        "run_at": "07:45:00",
        "window": "09:05-14:30",
        "partial": False,
        "candidates": 3,
        "observed": 2,
        "crossed": 1,
        "crossed_tickers": [T_B],
        "unobserved_tickers": [T_C],
        "per_ticker": {
            T_A: {"base_high": 10_302, "max": 10_250, "gap_pct": -0.5, "ticks": 1,
                  "first_cross_at": None,
                  "first_tick_at": "09:30:00", "last_tick_at": "09:30:00"},
            T_B: {"base_high": 20_754, "max": 21_000, "gap_pct": 1.19, "ticks": 2,
                  "first_cross_at": "10:00:00",
                  "first_tick_at": "10:00:00", "last_tick_at": "10:05:00"},
            T_C: {"base_high": 5_151, "max": 0, "gap_pct": None, "ticks": 0,
                  "first_cross_at": None, "first_tick_at": None, "last_tick_at": None},
        },
    }
    assert s._breakout_watch == before, "요약은 순수 읽기다"


async def test_e3_partial_when_run_after_entry_start():
    """창 안 재기동(run_at > entry_start)이면 partial=True."""
    s = make_strategy()
    await _prepare_at(s, "10:12:00")
    got = s.breakout_event_summary(TRADE_DAY)
    assert got["status"] == "ok" and got["run_at"] == "10:12:00"
    assert got["partial"] is True


@pytest.mark.parametrize("run_hms,partial", [("09:05:00", False), ("09:05:01", True)])
async def test_e3_partial_boundary_at_entry_start(run_hms, partial):
    """Y4 — partial = `run_at > entry_start`. 창 시작과 **같은** 시각의 prepare 는 창 전체를 보므로
    partial=False, 1초라도 늦으면 True."""
    s = make_strategy()
    await _prepare_at(s, run_hms)
    got = s.breakout_event_summary(TRADE_DAY)
    assert got["status"] == "ok" and got["run_at"] == run_hms
    assert got["partial"] is partial


async def test_e3_crossed_counts_tie_at_base_high():
    """F1(M9a) — 창 안 틱 하나가 **정확히** base_high 면 돌파다: crossed=1 · gap_pct=0.0.
    게이트가 `prev < base_high <= current_price` 라 동률도 돌파로 친다 — 요약이 `>` 로 세면
    그날 유일한 돌파가 0 으로 보고된다."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    _tick(s, "10:00:00", T_A, 10_302)       # == base_high(T_A)
    got = s.breakout_event_summary(TRADE_DAY)
    assert got["per_ticker"][T_A]["max"] == 10_302 and got["per_ticker"][T_A]["ticks"] == 1
    assert got["crossed"] == 1
    assert got["crossed_tickers"] == [T_A]
    assert got["per_ticker"][T_A]["gap_pct"] == 0.0


async def test_e3_never_raise_returns_error():
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    s._breakout_watch = _BoomWatch()
    assert s.breakout_event_summary(TRADE_DAY) == {"status": "error", "date": "2026-09-22"}


async def test_e3_g2_sequence_summary():
    """G2 시퀀스 뒤 요약 — 네 후보 모두 돌파 관측. 관측은 매수 게이트와 무관하다:
    B 는 09:19 에 이미 돌파선 위였지만 전날 가격도 위라 게이트는 edge 로 보지 않았고,
    K 는 쿨다운 중이라 매수 불가였지만 둘 다 관측으로는 돌파다(훅이 게이트들보다 앞이다)."""
    s, signals = await play_g2()
    assert [sig for *_, sig in signals].count("BUY") == 2, "대조군: G2 매수는 A·C 두 건"
    got = s.breakout_event_summary(TRADE_DAY)
    assert got["candidates"] == 4
    assert got["crossed"] == 4 and got["observed"] == 4
    assert got["crossed_tickers"] == [T_A, T_B, T_C, T_K]
    assert got["per_ticker"][T_A] == {"base_high": 10_302, "max": 10_500, "gap_pct": 1.92,
                                      "ticks": 5, "first_cross_at": "09:10:00",
                                      "first_tick_at": "09:05:00", "last_tick_at": "14:30:00"}
    assert got["per_ticker"][T_B]["ticks"] == 4 and got["per_ticker"][T_B]["max"] == 23_000
    assert got["per_ticker"][T_B]["first_cross_at"] == "09:19:00"
    assert got["per_ticker"][T_B]["last_tick_at"] == "09:22:00", "14:30:01 틱은 창 밖이다"
    assert got["per_ticker"][T_C]["first_cross_at"] == "10:01:00"
    assert got["per_ticker"][T_K]["first_cross_at"] == "09:40:00"


async def test_e3_observed_means_at_least_one_tick_not_full_window():
    """`observed` = 창 안 틱이 **최소 1개**다 — 창 전체를 봤다는 뜻이 아니다. 오전에 두 번 보이고
    끊긴 종목(장중 다른 전략 보유·매수 차단·구독 해제 등)도 observed 이고, 그 뒤 고가는 `max` 에
    없다(거짓 음성 가능). 끊긴 지점은 `last_tick_at` 으로만 읽힌다(verify 지적 2)."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    _tick(s, "09:10:00", T_A, 10_100)
    _tick(s, "09:20:00", T_A, 10_150)
    got = s.breakout_event_summary(TRADE_DAY)
    ent = got["per_ticker"][T_A]
    assert T_A not in got["unobserved_tickers"] and got["observed"] == 1
    assert ent["ticks"] == 2 and ent["max"] == 10_150 and ent["first_cross_at"] is None
    assert (ent["first_tick_at"], ent["last_tick_at"]) == ("09:10:00", "09:20:00")


# ###########################################################################
# ① D3 개정(F3) — 요약 줄은 「같은 KST 날짜의 직전 요약과 내용이 같으면」 생략
#   내용 = n · median_pct · within5 · over10 · tickers (run= 은 내용이 아니다)
#   후보 줄 cap(D4) · watch 교체(E1) · 저녁 무동작(D1)은 이 생략과 무관하게 그대로다.
# ###########################################################################

async def test_f3_same_content_morning_reprepare_emits_summary_once(caplog):
    """① 07:45 부팅 prepare 와 07:57 재준비(부팅 +600초)가 같은 목록이면 요약은 첫 줄 하나 — M5(요약)."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    await _prepare_at(s, "07:57:00")
    assert s._breakout_watch["run_at"] == "07:57:00", "대조군: 07:57 재준비가 오전 경로를 탔다"
    assert _warn_lines(caplog, SUMMARY_MARKER) == [_EXPECTED_MORNING_SUMMARY]


@pytest.mark.parametrize("universe", [[], [T_D, T_E, T_F]], ids=["early_return", "all_excluded"])
async def test_f3_zero_candidates_reprepare_60_times_emits_summary_once(caplog, fast_sleep, universe):
    """② 후보 0 인 날 `_reprepare_breakout_if_empty` 가 5분마다 prepare 를 부른다(09:05~14:00, 60회).
    요약은 첫 1줄뿐이다 — 유니버스 0(조기 반환)과 전원 탈락(정상 경로) 두 길 모두.
    watch 는 매번 교체되어 run_at 이 마지막 호출 시각이다(⑤)."""
    s = make_strategy(universe=universe, blocked=None)
    start = datetime(TRADE_DAY.year, TRADE_DAY.month, TRADE_DAY.day, 9, 5)
    times = [(start + timedelta(minutes=5 * i)).strftime("%H:%M:%S") for i in range(60)]
    with prepare_env(), freeze_time(_naive(times[0])) as frozen:
        for hms in times:
            frozen.move_to(_naive(hms))
            await s.prepare()
    assert s._candidates == {}
    assert s._breakout_watch == {"date": TRADE_DAY, "run_at": times[-1], "tickers": {}}
    assert _warn_lines(caplog, SUMMARY_MARKER) == [
        f"[vcp_breakout_distance_summary] run={times[0]} n=0 median_pct=na within5=0 over10=0 tickers=-"
    ]


async def test_f3_a_b_a_emits_three_summaries(caplog):
    """③ 「직전」 요약과만 비교한다 — A→B→A 는 세 줄 다 남는다(하루 전체 dedupe 가 아니다)."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")                                   # A
    await _prepare_at(s, "07:57:00", series=_series_without(T_C))      # B
    await _prepare_at(s, "08:03:00")                                   # A
    got = [_parse(l) for l in _warn_lines(caplog, SUMMARY_MARKER)]
    assert [(g["run"], g["n"], g["tickers"]) for g in got] == [
        ("07:45:00", "3", "900001,900002,900003"),
        ("07:57:00", "2", "900001,900002"),
        ("08:03:00", "3", "900001,900002,900003"),
    ]


async def test_f3_next_kst_day_same_content_emits_again(caplog):
    """④ 비교는 같은 KST 날짜 안에서만 — 다음 거래일의 같은 목록은 다시 찍힌다(그날 첫 요약)."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    await _prepare_at(s, "07:45:00", day=TRADE_DAY + timedelta(days=1))
    assert _warn_lines(caplog, SUMMARY_MARKER) == [_EXPECTED_MORNING_SUMMARY] * 2


async def test_f3_suppressed_summary_still_replaces_watch(caplog):
    """⑤ 요약을 생략해도 watch 는 매번 교체된다 — ③ 의 run_at 은 「마지막 오전 prepare」 다.
    생략 분기가 watch 교체보다 먼저 return 하면 07:45 watch 가 07:57 재준비 뒤에도 남아
    `run_at`·`partial` 이 거짓이 된다."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    first = s._breakout_watch
    first["tickers"][T_A]["ticks"] = 7   # 07:45 run 의 누적 흔적
    await _prepare_at(s, "07:57:00")

    assert s._breakout_watch is not first
    assert s._breakout_watch["run_at"] == "07:57:00"
    assert s._breakout_watch["tickers"][T_A]["ticks"] == 0
    assert s.breakout_event_summary(TRADE_DAY)["run_at"] == "07:57:00"
    # 전제 — 이 run 은 실제로 요약이 생략된 run 이다(아니면 위 단언은 E1 의 반복일 뿐이다).
    assert len(_warn_lines(caplog, SUMMARY_MARKER)) == 1


async def test_f3_evening_prepare_changed_content_emits_nothing_and_keeps_watch(caplog):
    """⑥ 저녁(16:20 재준비) prepare 는 요약 비교 **이전**에 빠진다 — 목록이 바뀌어도 줄 0 · watch 무접촉.
    같은 목록이면 F3 생략과 구분되지 않으므로 후보 하나를 뺀 목록으로 잰다."""
    s = make_strategy()
    await _prepare_at(s, "07:45:00")
    assert len(_warn_lines(caplog, SUMMARY_MARKER)) == 1, "양성 대조군: 오전 prepare 요약 줄 부재"
    watch = s._breakout_watch
    before = copy.deepcopy(watch)
    caplog.clear()

    await _prepare_at(s, "16:20:00", series=_series_without(T_C))

    assert list(s._candidates) == [T_A, T_B], "대조군: 저녁 목록이 실제로 달라야 한다"
    assert _warn_lines(caplog, DIST_MARKER) == []
    assert _warn_lines(caplog, SUMMARY_MARKER) == []
    assert s._breakout_watch is watch and s._breakout_watch == before


#: 내용 키 필드별 — (1회차 base_high 3개, 2회차 base_high 3개, 2회차 삽입 순서 뒤집기, 달라지는 필드).
#: 전일 종가는 전부 10,000 이라 dist_pct = base_high/100 − 100.
_F3_KEY_CASES = {
    "median_only": ([10_200, 10_400, 10_600], [10_200, 10_300, 10_600], False, "median_pct"),
    "within5_only": ([10_400, 10_600, 11_200], [10_550, 10_600, 11_200], False, "within5"),
    "over10_only": ([10_600, 10_900, 11_100], [10_600, 10_900, 10_950], False, "over10"),
    "tickers_only": ([10_200, 10_400, 10_600], [10_200, 10_400, 10_600], True, "tickers"),
}


@pytest.mark.parametrize("case", list(_F3_KEY_CASES))
def test_f3_content_key_covers_each_field(caplog, case):
    """내용 키 = n · median_pct · within5 · over10 · tickers — **어느 하나만** 바뀌어도 찍힌다.
    (n 은 tickers 와 함께만 바뀐다.) 각 케이스는 정확히 그 필드 하나만 다르게 만들었다(자기 검증)."""
    first, second, reverse, field = _F3_KEY_CASES[case]
    tickers = ["901001", "901002", "901003"]
    s = make_strategy()
    refs1 = {t: _refs_entry(s, t, base_high=bh, prev_close=10_000) for t, bh in zip(tickers, first)}
    _call_distance(s, refs1, "07:45:00")
    s._candidates.clear()
    pairs = list(zip(tickers, second))
    if reverse:
        pairs.reverse()
    refs2 = {t: _refs_entry(s, t, base_high=bh, prev_close=10_000) for t, bh in pairs}
    _call_distance(s, refs2, "07:57:00")

    lines = _warn_lines(caplog, SUMMARY_MARKER)
    assert len(lines) == 2, f"{field} 만 바뀐 요약이 생략됐다: {lines}"
    a, b = (_parse(l) for l in lines)
    assert {k for k in ("n", "median_pct", "within5", "over10", "tickers") if a[k] != b[k]} == {field}
